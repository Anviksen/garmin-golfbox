#!/usr/bin/env python3
"""
Send en EKTE test-varsling (e-post + push) til én bestemt bruker fra
multi-bruker-basen – uten å måtte vente på at de spiller en ekte golfrunde.

Nyttig for å bekrefte at varslings-kjeden (Supabase -> dekryptering ->
per-bruker env -> notify.py) faktisk fungerer for en gitt bruker, og som
generelt feilsøkingsverktøy når noen sier «jeg fikk ikke varsel».

Poster INGENTING til GolfBox/Garmin – rører kun varsling.

Bruk:
    python3 test_user_notify.py <navn-eller-id>
"""

from __future__ import annotations

import os
import sys

import notify
import user_crypto
import user_store


def _find_user(arg: str) -> dict | None:
    """Slå opp én FULL brukerrad fra navn (delvis, case-insensitive) eller id."""
    users = user_store.get_active_users()
    for u in users:
        if u.get("id") == arg:
            return u
    arg_low = arg.lower()
    matches = [u for u in users if arg_low in (u.get("label") or "").lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"⚠️  «{arg}» matcher flere: {', '.join(u['label'] for u in matches)} "
              f"– bruk et mer presist navn, eller selve id-en.")
        return None
    print(f"⚠️  Fant ingen aktiv bruker som matcher «{arg}».")
    return None


def main() -> None:
    if not user_store.is_configured():
        print("❌ SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY mangler i .env.")
        raise SystemExit(1)
    if not user_crypto.is_configured():
        print("❌ ENCRYPTION_KEY mangler i .env.")
        raise SystemExit(1)
    if len(sys.argv) < 2:
        print("Bruk: python3 test_user_notify.py <navn-eller-id>")
        raise SystemExit(1)

    user_row = _find_user(sys.argv[1])
    if user_row is None:
        raise SystemExit(1)

    label = user_row.get("label")
    notify_email = user_row.get("notify_email")
    ntfy_topic = user_row.get("ntfy_topic")
    ntfy_server = user_row.get("ntfy_server")

    if not notify_email and not ntfy_topic:
        print(f"⚠️  {label} har verken e-post eller ntfy-emne registrert – ingenting å teste.")
        raise SystemExit(1)

    # Speil INN akkurat denne brukerens varslingsfelt – samme mønster som
    # auto_sync._apply_env(), men vi rører ikke Garmin/GolfBox-creds her siden
    # dette scriptet ikke poster noe, kun tester varslingsveien.
    for key, val in (("NOTIFY_EMAIL", notify_email),
                      ("NTFY_TOPIC", ntfy_topic),
                      ("NTFY_SERVER", ntfy_server)):
        if val:
            os.environ[key] = val
        else:
            os.environ.pop(key, None)

    print(f"Sender testvarsel til {label} "
          f"(e-post: {notify_email or '(ikke satt)'}, "
          f"ntfy: {ntfy_topic or '(ikke satt)'}) ...\n")

    sent_any = False

    if notify_email:
        if notify.is_configured():
            ok = notify.send_email(
                f"Test – varsling for {label}",
                f"Hei {label}!\n\nDette er en test-e-post for å bekrefte at "
                f"varsling fungerer for akkurat din bruker i garmin-golfbox.\n\n"
                f"Mvh, golf-roboten 🏌️")
            print(f"  {'✅' if ok else '❌'} E-post {'sendt' if ok else 'feilet'}.")
            sent_any = sent_any or ok
        else:
            print("  ℹ️  E-post IKKE sendt – GMAIL_USER/GMAIL_APP_PASSWORD er ikke satt "
                  "opp lokalt (delt avsender-konto, samme for alle brukere).")

    if ntfy_topic:
        if notify.is_push_configured():
            ok = notify._push(f"Test-varsel: {label}",
                              f"📱 Push virker for {label}! Du får varsel her fra nå.",
                              tags="golf")
            print(f"  {'✅' if ok else '❌'} Push {'sendt' if ok else 'feilet'}.")
            sent_any = sent_any or ok
        else:
            print("  ⚠️  Push IKKE sendt – noe er feil med NTFY_TOPIC-verdien for denne brukeren.")

    if sent_any:
        print(f"\n✅ Minst ett varsel sendt. Be {label} bekrefte at de faktisk mottok det – "
              f"push krever at de har abonnert på riktig ntfy-emne i appen selv.")
    else:
        print("\n❌ Ingenting ble sendt – se feilmeldingene over.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
