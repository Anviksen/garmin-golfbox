#!/usr/bin/env python3
"""
Provisjonering: legg til ÉN ny bruker i multi-bruker-basen (Supabase `users`).

Interaktivt script – spør om alt som trengs, krypterer det som skal krypteres
(user_crypto.py), viser et sammendrag for bekreftelse, og setter inn raden via
user_store.py (service-role-nøkkelen). Poster INGENTING til GolfBox/Garmin –
rører kun databasen.

Før du kjører dette for en venn (vis dem samtykketeksten i MULTIUSER_PLAN.md
FØRST), må du ha samlet inn:

  1. Garmin-token (KUN token, ALDRI passord – se prinsippet i MULTIUSER_PLAN.md).
     Logg inn med vedkommendes Garmin-konto i en EGEN, midlertidig tokenstore-
     mappe. Gjør dette sammen med dem, ÉN om gangen, ALDRI i loop/automatisk
     (se advarselen om Garmin-ratelimiting i MULTIUSER_PLAN.md):

         GARMINTOKENS=/tmp/venn_token python3 -c "
         from garminconnect import Garmin
         g = Garmin('deres.epost@example.com', 'deres-passord')
         g.login()
         print('OK – token lagret i /tmp/venn_token')"

     Pakk den til én base64-tekstfil (samme format som secreten GARMIN_TOKENS_B64):

         tar czf - -C /tmp venn_token | base64 > /tmp/venn_garmin.b64

     Slett /tmp/venn_token etterpå – passordet ble aldri lagret noe sted, kun
     brukt momentant i minnet for selve innloggingen.

  2. GolfBox-brukernavn + passord (skrives inn her, kryptert før lagring).

  3. Markørens (medspillerens) medlemsnummer.

Bruk:
    python3 provision_user.py
"""

from __future__ import annotations

import getpass
from datetime import datetime, timezone
from pathlib import Path

import user_crypto
import user_store

CONSENT_VERSION = "v1-enkel-samtykketekst"  # oppdater hvis samtykketeksten endres


def _ask(prompt: str, required: bool = False) -> str | None:
    while True:
        val = input(f"{prompt}: ").strip()
        if val:
            return val
        if not required:
            return None
        print("   (påkrevd – prøv igjen, eller Ctrl+C for å avbryte)")


def _ask_secret(prompt: str) -> str | None:
    val = getpass.getpass(f"{prompt}: ").strip()
    return val or None


def _read_b64_file(prompt: str) -> str | None:
    path = input(f"{prompt} (filsti, Enter for å hoppe over/legge til senere): ").strip()
    if not path:
        return None
    p = Path(path).expanduser()
    if not p.exists():
        print(f"   ⚠️  Fant ikke {p} – hopper over (kan legges til senere).")
        return None
    return p.read_text(encoding="utf-8").strip()


def _yes(prompt: str) -> bool:
    return _ask(prompt, required=True).lower() in ("ja", "j", "yes", "y")


def _mask(val: str | None) -> str:
    if not val:
        return "(ikke satt)"
    return f"(satt – {len(val)} tegn, kryptert)"


def main() -> None:
    if not user_store.is_configured():
        print("❌ SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY mangler i .env. "
              "Se MULTIUSER_PLAN.md steg 1.")
        raise SystemExit(1)
    if not user_crypto.is_configured():
        print("❌ ENCRYPTION_KEY mangler i .env. Se MULTIUSER_PLAN.md steg 1.")
        raise SystemExit(1)

    print("=== Ny bruker til garmin-golfbox (multi-bruker) ===\n")
    print("Bekreft FØRST at personen har samtykket (vis dem teksten i "
          "MULTIUSER_PLAN.md) og forstår at dette er best-effort, ikke en "
          "garantert tjeneste, og at det bruker en ikke-offisiell tilkobling "
          "mot Garmin.\n")
    if not _yes("Har personen samtykket? (ja/nei)"):
        print("Avbryter – ikke provisjoner uten samtykke.")
        raise SystemExit(1)

    label = _ask("Visningsnavn (til logger, f.eks. fornavn)", required=True)

    print("\n--- Garmin ---")
    garmin_tokens_b64 = _read_b64_file("Base64 Garmin-token")

    print("\n--- GolfBox ---")
    golfbox_username = _ask("GolfBox-brukernavn")
    golfbox_password = _ask_secret("GolfBox-passord")
    golfbox_session_b64 = _read_b64_file(
        "Base64 GolfBox-økt (valgfritt – opprettes automatisk ved første kjøring uten)")
    marker_memberno = _ask("Markørens medlemsnummer (XX-XXXXX)")
    marker_name = _ask("Markørens navn (kun hvis medlemsnr mangler)")

    print("\n--- Varsling ---")
    notify_email = _ask("E-post for varsling (valgfritt)")
    ntfy_topic = _ask("ntfy-emne for push (valgfritt, f.eks. golfbox-<tilfeldig>)")

    row = {
        "label": label,
        "active": True,
        "consent_at": datetime.now(timezone.utc).isoformat(),
        "consent_version": CONSENT_VERSION,
        "garmin_tokens_enc": user_crypto.encrypt(garmin_tokens_b64),
        "golfbox_username_enc": user_crypto.encrypt(golfbox_username),
        "golfbox_password_enc": user_crypto.encrypt(golfbox_password),
        "golfbox_session_enc": user_crypto.encrypt(golfbox_session_b64),
        "golfbox_marker_memberno": marker_memberno,
        "golfbox_marker_name": marker_name,
        "notify_email": notify_email,
        "ntfy_topic": ntfy_topic,
    }

    print("\n=== Sammendrag (verdier under er ALDRI vist i klartekst her) ===")
    print(f"  Visningsnavn:        {label}")
    print(f"  Garmin-token:        {_mask(row['garmin_tokens_enc'])}")
    print(f"  GolfBox-brukernavn:  {_mask(row['golfbox_username_enc'])}")
    print(f"  GolfBox-passord:     {_mask(row['golfbox_password_enc'])}")
    print(f"  GolfBox-økt:         {_mask(row['golfbox_session_enc'])}")
    print(f"  Markør medlemsnr:    {marker_memberno or '(ikke satt)'}")
    print(f"  Markør navn:         {marker_name or '(ikke satt)'}")
    print(f"  Varslings-e-post:    {notify_email or '(ikke satt)'}")
    print(f"  ntfy-emne:           {ntfy_topic or '(ikke satt)'}")

    if not row["garmin_tokens_enc"]:
        print("\n⚠️  Ingen Garmin-token satt – brukeren blir opprettet, men vil ikke "
              "hentes runder for før tokenet legges til (oppdater raden senere).")

    if not _yes("\nSe riktig ut – opprett brukeren? (ja/nei)"):
        print("Avbrutt – ingenting lagret.")
        raise SystemExit(0)

    result = user_store.create_user(row)
    if result:
        print(f"\n✅ Bruker opprettet: {result.get('label')}  (id={result.get('id')})")
    else:
        print("\n❌ Kunne ikke opprette bruker – se feilmelding over.")
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAvbrutt.")
        raise SystemExit(1)
