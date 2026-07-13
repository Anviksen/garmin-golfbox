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
# Hvor mange kjøringer vi venter på at Garmin fyller inn tee-data før vi gir opp
# og ber brukeren fullføre selv. 4 × 10 min ≈ 40 min maks. Justerbart via env.
MAX_TEE_WAIT = int(os.getenv("GOLFBOX_TEE_WAIT_TRIES", "4"))


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
            data.setdefault("pending", {})  # {rid: antall vente-forsøk} for tee-data
            return data
        except Exception:
            pass
    return {"seen": [], "posted": [], "needs_manual": [], "pending": {},
            "_initialized": False}


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


def round_name(rid: int) -> str:
    """Slå opp banenavn for en runde-ID fra lokal data (for varsler)."""
    try:
        raw = json.loads((PROJECT_DIR / "data" / "all_rounds.json").read_text(encoding="utf-8"))
        for r in raw.get("runder", []):
            s = r.get("summary", {})
            if s.get("id") == rid:
                return s.get("courseName") or str(rid)
    except Exception:
        pass
    return str(rid)


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
    posted_now, review_now, manual_now, notpostable_now = [], [], [], []
    for rid in new_ids:
        name = round_name(rid)
        log(f"→ Sender runde {rid} ({name}) til Golfbox ...")
        rc = run([sys.executable, str(POST_SCRIPT), str(rid), "--auto"],
                 extra_env={"GOLFBOX_AUTO": "1"})
        if rc in (0, 4):
            state["seen"].append(rid)
            state["posted"].append(rid)
            state["pending"].pop(str(rid), None)
            if rc == 4:
                review_now.append((name, "tee valgt på skjønn"))
                log(f"   ✅ Runde {rid} lagret – men tee usikker, flagget for dobbeltsjekk.")
            else:
                posted_now.append((name, ""))
                log(f"   ✅ Runde {rid} lagret i Golfbox (til godkjennelse).")
        elif rc == 2:
            # Golfbox-økt utløpt – ingen vits å prøve flere nå. IKKE marker som sett,
            # så den prøves igjen ved neste kjøring etter at du har fornyet økten.
            log(f"   ⏸️ Golfbox-økt utløpt. Stopper. Runde {rid} prøves igjen senere.")
            break
        elif rc == 6:
            # Garmin har ikke tee-data ennå (fylles med forsinkelse). IKKE marker som
            # sett – vent og prøv igjen neste kjøring, opp til et tak. Ingen mail ennå.
            tries = state["pending"].get(str(rid), 0) + 1
            state["pending"][str(rid)] = tries
            if tries >= MAX_TEE_WAIT:
                state["seen"].append(rid)
                state["needs_manual"].append(rid)
                state["pending"].pop(str(rid), None)
                manual_now.append((name, "Garmin fylte aldri inn tee-data"))
                log(f"   ⧗→⚠️ Runde {rid}: tee-data kom aldri (etter {tries} forsøk). "
                    f"Flagger for manuell fullføring.")
            else:
                log(f"   ⧗ Runde {rid}: venter på Garmin sin tee-data "
                    f"(forsøk {tries}/{MAX_TEE_WAIT}). Prøver igjen neste kjøring.")
        elif rc == 5:
            # Klubben finnes ikke i GolfBox (privat/utland/ikke-WHS) – ikke leverbar.
            state["seen"].append(rid)
            state["needs_manual"].append(rid)
            state["pending"].pop(str(rid), None)
            notpostable_now.append((name, "klubben finnes ikke i GolfBox"))
            log(f"   ⛔ Runde {rid} – klubben finnes ikke i GolfBox. Kan ikke leveres.")
        else:
            # rc == 3: klubb OK, men bane/tee ikke bekreftet – KAN fullføres i web-appen.
            state["seen"].append(rid)
            state["needs_manual"].append(rid)
            state["pending"].pop(str(rid), None)
            manual_now.append((name, "bane/tee ikke bekreftet"))
            log(f"   ⚠️ Runde {rid} matchet ikke helt (kode {rc}). Kan fullføres i web-appen.")

    save_state(state)

    # Varsle brukeren hvis noe krever et blikk.
    if manual_now or review_now or notpostable_now:
        try:
            import notify
            if notify.is_configured() and notify.notify_rounds(
                    manual_now, review_now, posted_now, notpostable_now):
                log(f"📧 Varsel sendt ({len(manual_now)} å fullføre, "
                    f"{len(review_now)} å dobbeltsjekke, {len(notpostable_now)} ikke leverbare).")
        except Exception as e:
            log(f"(varsling hoppet over: {e})")

    log("=== auto_sync ferdig ===")


if __name__ == "__main__":
    main()
