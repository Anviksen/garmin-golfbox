#!/usr/bin/env python3
"""
Helautomatisk onboarding – «alternativ B» fra MULTIUSER_PLAN.md steg 6.

Google-skjemaet skriver rett til Supabase-tabellen `pending_signups` (via
Google Apps Script, se google_apps_script_signup.gs + WEBHOOK_ONBOARDING.md).
Dette scriptet plukker opp ÉN ventende påmelding (aldri flere per kjøring –
se rate-limit-advarselen i MULTIUSER_PLAN.md om Garmin-innlogging),
gjenbruker samme innlogging/kryptering/innsettings-logikk som den
interaktive `provision_user.py`, og:

  1. Logger inn på Garmin (IKKE-interaktivt – MFA feiler raskt og tydelig i
     stedet for å henge, se provision_user._mfa_not_supported).
  2. Krypterer og oppretter brukeren i `users` (samme som provision_user.py).
  3. Sletter pending_signups-raden UMIDDELBART ved suksess – fjerner
     klartekst-passordene fra basen for godt.
  4. Sender en velkomst-e-post til DEN NYE BRUKEREN (gjenbruker
     provision_user._send_welcome_email).
  5. Varsler EIEREN (deg) – push/e-post til DIN egen NTFY_TOPIC/NOTIFY_EMAIL
     fra env – om at en ny person ble lagt til (eller at det feilet, med
     årsak). Se AskUserQuestion-svar i chatten 24. juli 2026: eieren skal
     varsles hver gang, og nye brukere går rett i full automatikk fra første
     runde (ingen egen dry-run-fase for splitter nye kontoer).

Feiler innloggingen (feil passord, MFA, Garmin nede, osv.): raden markeres
`failed` med årsak (IKKE slettet – blir liggende til du følger opp manuelt,
enten ved å fikse og sette status tilbake til 'pending' i Supabase, eller
kjøre python3 provision_user.py selv og så slette raden). Prøves ALDRI
automatisk på nytt i påfølgende kjøringer (unngår evig loop mot en
permanent ødelagt påmelding, f.eks. feil passord).

Kjøres av .github/workflows/process-signups.yml på tidsplan.
"""

from __future__ import annotations

from datetime import datetime, timezone

import provision_user
import user_crypto
import user_store

MAX_SIGNUP_ATTEMPTS = 2  # se docstring – gir opp automatisk retry etter dette


def _owner_notify(subject: str, body: str, push_tags: str = "") -> None:
    """Varsle EIEREN (ikke den nye brukeren) – best effort, feiler aldri selve
    behandlingen om varslingen mislykkes."""
    try:
        import notify
        if notify.is_configured():
            notify.send_email(subject, body)
        if notify.is_push_configured():
            notify.send_push(subject[:60], body, tags=push_tags)
    except Exception as e:
        print(f"(eier-varsel hoppet over: {e})")


def _process_one(signup: dict) -> None:
    signup_id = signup["id"]
    label = signup.get("label") or "(uten navn)"
    attempts = signup.get("attempts", 0)

    if attempts >= MAX_SIGNUP_ATTEMPTS:
        print(f"  ⏭️  Hopper over {label} – nådde maks {MAX_SIGNUP_ATTEMPTS} forsøk "
              f"allerede (status skulle vært 'failed', ikke 'pending' – sjekk manuelt).")
        user_store.mark_pending_signup(
            signup_id, "failed",
            f"Nådde maks {MAX_SIGNUP_ATTEMPTS} forsøk – trenger manuell oppfølging."
        )
        return

    print(f"→ Behandler påmelding: {label} ...")
    user_store.increment_signup_attempts(signup_id, attempts)
    user_store.mark_pending_signup(signup_id, "processing")

    garmin_email = (signup.get("garmin_email") or "").strip()
    garmin_password = signup.get("garmin_password")
    golfbox_username = (signup.get("golfbox_username") or "").strip()
    golfbox_password = signup.get("golfbox_password")

    if not garmin_email or not garmin_password or not golfbox_username or not golfbox_password:
        reason = "Mangler Garmin- og/eller GolfBox-innlogging i påmeldingen."
        print(f"  ❌ {reason}")
        user_store.mark_pending_signup(signup_id, "failed", reason)
        _owner_notify(
            f"⚠️ Påmelding fra {label} kunne ikke behandles",
            f"{reason}\n\nSjekk pending_signups i Supabase (id={signup_id}).",
        )
        return

    garmin_tokens_b64 = provision_user._login_garmin_and_capture_token(
        garmin_email, garmin_password, interactive=False
    )
    garmin_password = None  # ute av minnet så tidlig som råd er
    signup["garmin_password"] = None

    if not garmin_tokens_b64:
        reason = "Garmin-innlogging feilet (feil passord, MFA kreves, eller Garmin nede)."
        print(f"  ❌ {reason}")
        user_store.mark_pending_signup(signup_id, "failed", reason)
        _owner_notify(
            f"⚠️ Påmelding fra {label} trenger manuell hjelp",
            f"{reason}\n\n"
            f"Kjør «python3 provision_user.py» manuelt for {label} "
            f"(e-post: {garmin_email}), eller rett feilen og sett status tilbake til "
            f"'pending' i pending_signups (id={signup_id}) for automatisk nytt forsøk.",
        )
        return

    ntfy_topic = provision_user._generate_ntfy_topic() if signup.get("wants_push") else None
    row = {
        "label": label,
        "active": True,
        "consent_at": datetime.now(timezone.utc).isoformat(),
        "consent_version": signup.get("consent_version") or provision_user.CONSENT_VERSION,
        "garmin_tokens_enc": user_crypto.encrypt(garmin_tokens_b64),
        "golfbox_username_enc": user_crypto.encrypt(golfbox_username),
        "golfbox_password_enc": user_crypto.encrypt(golfbox_password),
        "golfbox_session_enc": None,
        "golfbox_marker_memberno": signup.get("golfbox_marker_memberno"),
        "golfbox_marker_name": signup.get("golfbox_marker_name"),
        "notify_email": signup.get("notify_email"),
        "ntfy_topic": ntfy_topic,
    }
    golfbox_password = None  # ute av minnet – brukt ferdig i row over
    signup["golfbox_password"] = None

    result = user_store.create_user(row)
    if not result:
        reason = "Klarte å logge inn på Garmin, men kunne ikke opprette brukeren i Supabase."
        print(f"  ❌ {reason}")
        user_store.mark_pending_signup(signup_id, "failed", reason)
        _owner_notify(f"⚠️ Påmelding fra {label} feilet ved lagring", reason)
        return

    user_store.delete_pending_signup(signup_id)  # fjern klartekst-passord for godt
    print(f"  ✅ Bruker opprettet: {result.get('label')} (id={result.get('id')})")

    provision_user._send_welcome_email(label, signup.get("notify_email"), ntfy_topic)

    push_body = (
        f"{label} er lagt til automatisk. Runder postes fra første runde – "
        f"ingen ekstra sjekk av deg trengs, men si ifra hvis noe ser rart ut."
    )
    if ntfy_topic:
        push_body += f"\nntfy-emne (gitt til {label}): {ntfy_topic}"
    _owner_notify(f"✅ Ny bruker lagt til: {label}", push_body, push_tags="tada")


def main() -> None:
    if not user_store.is_configured():
        print("❌ SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY mangler. Se MULTIUSER_PLAN.md.")
        raise SystemExit(1)
    if not user_crypto.is_configured():
        print("❌ ENCRYPTION_KEY mangler. Se MULTIUSER_PLAN.md.")
        raise SystemExit(1)

    pending = user_store.list_pending_signups(limit=5)
    if not pending:
        print("Ingen ventende påmeldinger.")
        return

    print(f"{len(pending)} ventende påmelding(er) funnet – behandler KUN den eldste "
          f"(rate-limit-hensyn, se MULTIUSER_PLAN.md). Resten tas neste kjøring.")
    _process_one(pending[0])


if __name__ == "__main__":
    main()
