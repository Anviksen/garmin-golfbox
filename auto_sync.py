#!/usr/bin/env python3
"""
Auto-sync – oppdag nye golfrunder og send dem til Golfbox automatisk.

Kjøres jevnlig (f.eks. hvert 5. minutt via GitHub Actions + cron-job.org):
  1. Logg inn på Garmin med lagret token (ingen passord/MFA).
  2. Hent oversikten og se om det har dukket opp nye runder siden sist.
  3. For hver NYE runde: oppdater lokal data, og kjør golfbox_post.py i auto-modus.
  4. Husk hva som er behandlet i data/posted.json (så vi aldri poster samme to ganger).

Første kjøring setter bare en «baseline» (markerer dagens runder som sett) og poster
INGENTING – slik at hele historikken din ikke blir sendt inn på én gang.

Kjøres slik:
    python3 auto_sync.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*a, **k):
        return None

try:
    from garminconnect import Garmin
except ImportError:
    print("Mangler garminconnect. pip install -r requirements.txt")
    raise SystemExit(1)

# Gjenbruk hjelpefunksjonene fra fetch-scriptet for å tolke oversikten.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_garmin import extract_scorecard_list, get_id  # noqa: E402

PROJECT_DIR = Path(__file__).resolve().parent
STATE_FILE = PROJECT_DIR / "data" / "posted.json"
LOG_FILE = PROJECT_DIR / "data" / "auto_sync.log"
FETCH_SCRIPT = PROJECT_DIR / "fetch_garmin.py"
POST_SCRIPT = PROJECT_DIR / "golfbox_post.py"
TOKENSTORE = os.getenv("GARMINTOKENS", "~/.garminconnect")


def log(msg: str) -> None:
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
    print(line, flush=True)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            data.setdefault("seen", [])
            data.setdefault("posted", [])
            data.setdefault("needs_manual", [])
            return data
        except Exception:
            pass
    return {"seen": [], "posted": [], "needs_manual": [], "_initialized": False}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def garmin_summary_ids() -> list[int]:
    """Logg inn med lagret token og hent ID-ene til de siste rundene."""
    client = Garmin()
    client.login(TOKENSTORE)  # kun token – ingen passord/MFA
    summary = client.get_golf_summary(limit=50)
    ids = []
    for sc in extract_scorecard_list(summary):
        sc_id = get_id(sc)
        if sc_id is not None:
            try:
                ids.append(int(sc_id))
            except (ValueError, TypeError):
                pass
    return ids


def run(cmd: list[str], extra_env: dict | None = None) -> int:
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(cmd, cwd=str(PROJECT_DIR), env=env).returncode


def main() -> None:
    load_dotenv(PROJECT_DIR / ".env")
    log("=== auto_sync start ===")

    state = load_state()

    try:
        ids = garmin_summary_ids()
    except Exception as e:
        log(f"❌ Garmin-innlogging/-henting feilet (token utløpt?): {e}")
        raise SystemExit(2)

    log(f"Fant {len(ids)} runder i Garmin-oversikten.")

    # Første kjøring: sett baseline, post ingenting.
    if not state.get("_initialized"):
        state["seen"] = ids
        state["_initialized"] = True
        save_state(state)
        log(f"Baseline satt ({len(ids)} runder markert som sett). Ingen posting første gang.")
        return

    seen = set(state["seen"])
    new_ids = [i for i in ids if i not in seen]
    if not new_ids:
        log("Ingen nye runder. Ferdig.")
        return

    log(f"🆕 {len(new_ids)} ny(e) runde(r): {new_ids}")

    # Oppdater lokal data (henter detaljer for alle runder, inkl. de nye).
    log("Oppdaterer lokal data fra Garmin ...")
    if run([sys.executable, str(FETCH_SCRIPT)]) != 0:
        log("⚠️ fetch_garmin feilet – prøver likevel å poste med eksisterende data.")

    # Post hver nye runde til Golfbox i auto-modus.
    for rid in new_ids:
        log(f"→ Sender runde {rid} til Golfbox ...")
        rc = run([sys.executable, str(POST_SCRIPT), str(rid), "--auto"],
                 extra_env={"GOLFBOX_AUTO": "1"})
        if rc == 0:
            state["seen"].append(rid)
            state["posted"].append(rid)
            log(f"   ✅ Runde {rid} lagret i Golfbox (til godkjennelse).")
        elif rc == 2:
            # Golfbox-økt utløpt – ingen vits å prøve flere nå. IKKE marker som sett,
            # så den prøves igjen ved neste kjøring etter at du har fornyet økten.
            log(f"   ⏸️ Golfbox-økt utløpt. Stopper. Runde {rid} prøves igjen senere. "
                f"Forny Golfbox-innloggingen (se guide).")
            break
        else:
            # rc == 3 (fylt, men ikke trygt å lagre) eller annen feil: marker som sett
            # så vi ikke maser, men flagg for manuell håndtering.
            state["seen"].append(rid)
            state["needs_manual"].append(rid)
            log(f"   ⚠️ Runde {rid} kunne ikke lagres automatisk (kode {rc}). "
                f"Flagget for manuell sjekk.")

    save_state(state)
    log("=== auto_sync ferdig ===")


if __name__ == "__main__":
    main()
