#!/usr/bin/env python3
"""
Fase 1 – Hent golf scorecard-data fra Garmin Connect.

Dette scriptet:
  1. Logger inn på Garmin Connect (med støtte for tofaktor / MFA).
  2. Henter oversikt over ALLE golfrunder du har spilt (scorecard summary).
  3. For hver runde henter det hull-for-hull detaljer og slag-for-slag (shot) data.
  4. Lagrer alt strukturert som JSON i mappen ./data.

Kjøres slik (se README.md for full oppskrift):
    python3 fetch_garmin.py

Innlogging: første gang brukes epost/passord fra .env. Tokenene lagres lokalt,
og senere kjøringer logger inn automatisk uten passord.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Demp bibliotekets egne feil-logger (slagdata-kall som ikke finnes gir mye støy).
logging.getLogger("garminconnect").setLevel(logging.CRITICAL)

# --- Tredjeparts biblioteker ------------------------------------------------
try:
    from dotenv import load_dotenv
except ImportError:
    print("Mangler 'python-dotenv'. Kjør:  pip install -r requirements.txt")
    sys.exit(1)

try:
    from garminconnect import Garmin
except ImportError:
    print("Mangler 'garminconnect'. Kjør:  pip install -r requirements.txt")
    sys.exit(1)


# --- Kataloger og filer -----------------------------------------------------
PROJECT_DIR = Path(__file__).resolve().parent
# GOLFBOX_DATA_DIR lar en fremtidig multi-bruker-kjøring isolere hver brukers data
# i egen mappe (f.eks. data/users/<id>/); default er uendret (data/) for dagens
# enkelt-bruker-drift.
DATA_DIR = Path(os.getenv("GOLFBOX_DATA_DIR", str(PROJECT_DIR / "data")))
SCORECARDS_DIR = DATA_DIR / "scorecards"   # detaljert hull-for-hull per runde
SHOTS_DIR = DATA_DIR / "shots"             # slag-for-slag per runde

# Hvor Garmin-innloggingstokenene lagres (så du slipper å logge inn hver gang).
TOKENSTORE = os.getenv("GARMINTOKENS", "~/.garminconnect")


def _write_json(path: Path, data) -> None:
    """Skriv data pent formatert som UTF-8 JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def login() -> Garmin:
    """Logg inn på Garmin Connect. Bruker lagrede tokens hvis de finnes,
    ellers epost/passord fra .env (med MFA-spørsmål ved behov)."""
    email = os.getenv("GARMIN_EMAIL")
    password = os.getenv("GARMIN_PASSWORD")

    # Forsøk 1: bruk allerede lagrede tokens (ingen passord nødvendig).
    try:
        client = Garmin()
        client.login(TOKENSTORE)
        print("✅ Logget inn med lagrede tokens.")
        return client
    except Exception:
        pass  # Ingen gyldige tokens ennå – logg inn med passord under.

    if not email or not password:
        print(
            "❌ Fant ingen lagrede tokens, og GARMIN_EMAIL / GARMIN_PASSWORD "
            "er ikke satt.\n   Lag en .env-fil (kopier fra .env.example) og "
            "fyll inn detaljene dine."
        )
        sys.exit(1)

    print("🔐 Logger inn på Garmin Connect ...")
    client = Garmin(
        email,
        password,
        prompt_mfa=lambda: input("Skriv inn engangskode (MFA) fra Garmin: ").strip(),
    )
    client.login(TOKENSTORE)   # lagrer tokens for neste gang
    print(f"✅ Innlogget. Tokens lagret i {TOKENSTORE}")
    return client


def extract_scorecard_list(summary) -> list:
    """Garmin returnerer sammendraget i litt ulike former avhengig av versjon.
    Denne funksjonen finner selve lista med runder uansett form."""
    if isinstance(summary, list):
        return summary
    if isinstance(summary, dict):
        for key in ("scorecardSummaries", "scorecardList", "items", "scorecards"):
            value = summary.get(key)
            if isinstance(value, list):
                return value
        # Noen ganger ligger runden rett i objektet:
        return [summary]
    return []


def get_id(scorecard: dict):
    """Finn scorecard-ID-en uansett hvilket feltnavn Garmin bruker."""
    for key in ("scorecardId", "id", "scoreCardId"):
        if scorecard.get(key) is not None:
            return scorecard[key]
    return None


def describe(scorecard: dict) -> str:
    """Kort lesbar beskrivelse av en runde til logg-utskrift."""
    course = scorecard.get("courseName") or scorecard.get("golfCourseName") or "Ukjent bane"
    when = scorecard.get("startTime") or scorecard.get("date") or "?"
    return f"{course} ({when})"


def main() -> None:
    load_dotenv(PROJECT_DIR / ".env")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    client = login()

    # --- 1) Hent oversikt over alle runder ---------------------------------
    print("\n⛳ Henter oversikt over golfrunder ...")
    summary = client.get_golf_summary(limit=200)
    _write_json(DATA_DIR / "summary.json", summary)

    scorecards = extract_scorecard_list(summary)
    print(f"   Fant {len(scorecards)} runde(r).")

    if not scorecards:
        print(
            "\n⚠️  Ingen runder funnet. Sjekk at rundene fra Approach S50 er "
            "synkronisert til Garmin Connect-appen først."
        )
        return

    # --- 2) Hent detaljer + slagdata per runde -----------------------------
    combined = []
    for i, sc in enumerate(scorecards, 1):
        sc_id = get_id(sc)
        label = describe(sc)
        print(f"\n[{i}/{len(scorecards)}] {label}  (ID={sc_id})")

        if sc_id is None:
            print("   ⚠️  Ingen ID – hopper over detaljer.")
            combined.append({"summary": sc, "detail": None, "shots": None})
            continue

        # Hull-for-hull detaljer
        detail = None
        try:
            detail = client.get_golf_scorecard(int(sc_id))
            _write_json(SCORECARDS_DIR / f"{sc_id}.json", detail)
            print("   ✅ Hull-for-hull detaljer lagret.")
        except Exception as e:
            print(f"   ⚠️  Klarte ikke hente detaljer: {e}")

        # Slag-for-slag (shot) data – krever at vi oppgir hvilke hull vi vil ha.
        # Prøver 18 hull først, faller tilbake til 9 hull for korte runder.
        shots = None
        hole_sets = [
            "1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18",
            "1,2,3,4,5,6,7,8,9",
        ]
        for holes in hole_sets:
            try:
                shots = client.get_golf_shot_data(int(sc_id), hole_numbers=holes)
                _write_json(SHOTS_DIR / f"{sc_id}.json", shots)
                print("   ✅ Slag-for-slag data lagret.")
                break
            except Exception:
                continue
        if shots is None:
            print("   ℹ️  Ingen slagdata for denne runden.")

        combined.append({"summary": sc, "detail": detail, "shots": shots})

    # --- 3) Lagre alt samlet i én fil --------------------------------------
    payload = {
        "hentet": datetime.now().isoformat(timespec="seconds"),
        "antall_runder": len(combined),
        "runder": combined,
    }
    _write_json(DATA_DIR / "all_rounds.json", payload)

    print("\n🎉 Ferdig!")
    print(f"   • Oversikt:        {DATA_DIR / 'summary.json'}")
    print(f"   • Per runde:       {SCORECARDS_DIR}/<id>.json")
    print(f"   • Slagdata:        {SHOTS_DIR}/<id>.json")
    print(f"   • Alt samlet:      {DATA_DIR / 'all_rounds.json'}")
    print(f"\n   Totalt {len(combined)} runder lagret i {DATA_DIR}")


if __name__ == "__main__":
    main()
