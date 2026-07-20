#!/usr/bin/env python3
"""
Provisjonering: legg til ÉN ny bruker i multi-bruker-basen (Supabase `users`).

Interaktivt script – spør om alt som trengs (typisk hentet rett fra et
påmeldingsskjema, se SAMTYKKE_OG_PAMELDING.md), krypterer det som skal
krypteres (user_crypto.py), viser et sammendrag for bekreftelse, og setter inn
raden via user_store.py (service-role-nøkkelen). Poster INGENTING til
GolfBox/Garmin – rører kun databasen.

Garmin-innlogging gjøres NÅ AUTOMATISK i dette scriptet: oppgi personens
Garmin e-post/passord (fra skjemaet), så logger scriptet inn og fanger tokenet
selv. Passordet sendes KUN til Garmin sitt eget innloggingskall – det skrives
aldri til disk og forkastes fra minnet rett etter. Har kontoen MFA
(engangskode) på, spør scriptet om den interaktivt der og da – ha personen
tilgjengelig (telefon/SMS) hvis du ikke vet om de har det.

VIKTIG (uendret prinsipp): kjør dette ÉN bruker om gangen, aldri i loop/skript
mot flere Garmin-kontoer etter hverandre – se advarselen om Garmin-
ratelimiting i MULTIUSER_PLAN.md. Én innlogging her og nå er trygt; mange
etter hverandre er det som trigger Garmins bot-deteksjon.

Fungerer fortsatt uten Garmin-epost/passord (Enter for å hoppe over) – da kan
du i stedet oppgi filstien til et allerede fanget token (samme base64-tar-
format som secreten GARMIN_TOKENS_B64), for manuell/edge-case bruk.

Bekreft FØRST at personen har samtykket (vis dem samtykketeksten i
SAMTYKKE_OG_PAMELDING.md) før du kjører dette.

Bruk:
    python3 provision_user.py
"""

from __future__ import annotations

import base64
import getpass
import io
import secrets
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import user_crypto
import user_store

CONSENT_VERSION = "v2-garmin-passord-i-skjema"  # oppdater hvis samtykketeksten endres


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


def _login_garmin_and_capture_token(email: str, password: str) -> str | None:
    """Logg inn på Garmin med e-post/passord og fang det resulterende tokenet,
    pakket til samme base64-tar-format som ellers brukes (GARMIN_TOKENS_B64).

    Passordet brukes KUN i selve login()-kallet under – det skrives aldri til
    disk, og den kallende koden nuller ut variabelen sin rett etter dette
    returnerer. Kan spørre om en MFA-engangskode interaktivt hvis kontoen har
    det på."""
    try:
        from garminconnect import Garmin
    except ImportError:
        print("  ❌ Mangler 'garminconnect'. Kjør: pip install -r requirements.txt")
        return None

    with tempfile.TemporaryDirectory() as tmp:
        tokenstore = str(Path(tmp) / ".garminconnect")
        try:
            print("  Logger inn på Garmin ...")
            client = Garmin(
                email, password,
                prompt_mfa=lambda: input("  Engangskode (MFA) fra Garmin for denne kontoen: ").strip(),
            )
            client.login(tokenstore)  # lagrer friske tokens i tokenstore
        except Exception as e:
            print(f"  ❌ Garmin-innlogging feilet: {e}")
            return None

        tokendir = Path(tokenstore)
        if not tokendir.exists():
            print("  ❌ Innlogging så ut til å gå bra, men fant ingen tokens på disk etterpå.")
            return None

        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            tf.add(tokendir, arcname=".garminconnect")
        print("  ✅ Garmin-token hentet og fanget.")
        return base64.b64encode(buf.getvalue()).decode("ascii")


def _generate_ntfy_topic() -> str:
    """Lag et tilfeldig, ugjettbart ntfy-emne. Selve emnenavnet ER sikkerheten
    hos ntfy.sh (ingen kontoer/passord der - hvem som helst som kjenner
    emnenavnet kan lese/skrive til det) - MÅ derfor være tilfeldig, aldri
    forutsigbart (f.eks. IKKE basert på navn/e-post)."""
    return f"golfbox-{secrets.token_hex(8)}"


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
    print("Oppgi Garmin-epost for å logge inn og hente tokenet automatisk (anbefalt –")
    print("passordet lagres ALDRI, kun brukt momentant til selve innloggingen).")
    garmin_email = _ask("Garmin-epost (Enter for å hoppe over / bruke en fil i stedet)")
    if garmin_email:
        garmin_password = _ask_secret("Garmin-passord (brukes kun til dette ene forsøket)")
        garmin_tokens_b64 = _login_garmin_and_capture_token(garmin_email, garmin_password)
        garmin_password = None  # ute av variabelen så tidlig som råd er
        if garmin_tokens_b64 is None:
            print("  Fortsetter uten Garmin-token – kan legges til senere ved å kjøre "
                  "dette scriptet på nytt, eller oppdatere raden direkte.")
    else:
        garmin_tokens_b64 = _read_b64_file("Base64 Garmin-token (hvis allerede fanget manuelt)")

    print("\n--- GolfBox ---")
    golfbox_username = _ask("GolfBox-brukernavn")
    golfbox_password = _ask_secret("GolfBox-passord")
    golfbox_session_b64 = _read_b64_file(
        "Base64 GolfBox-økt (valgfritt – opprettes automatisk ved første kjøring uten)")
    marker_memberno = _ask("Markørens medlemsnummer (XX-XXXXX)")
    marker_name = _ask("Markørens navn (kun hvis medlemsnr mangler)")

    print("\n--- Varsling ---")
    notify_email = _ask("E-post for varsling (valgfritt)")
    ntfy_topic = None
    if _yes("Vil personen ha push-varsel på mobil? (ja/nei)"):
        ntfy_topic = _generate_ntfy_topic()
        print(f"\n  📱 Push-emne generert: {ntfy_topic}")
        print("     Send DENNE strengen til personen etterpå. De må selv installere")
        print("     ntfy-appen (gratis, ingen konto) og abonnere på akkurat dette")
        print("     emnet for faktisk å motta varsler – du kan ikke gjøre det for dem.")

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
