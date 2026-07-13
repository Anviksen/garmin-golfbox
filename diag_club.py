#!/usr/bin/env python3
"""Diagnose: velg en klubb og list ALLE baner + tees (live fra GolfBox).

    python3 diag_club.py "Østmarka"

Poster ingenting. Viser for hver bane hvilke tees GolfBox faktisk tilbyr,
så vi ser om en bane mangler tees (ekte tomt) eller om det er en match-feil.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except Exception:
    pass

import golfbox_post as gp


def main() -> None:
    term = (sys.argv[1] if len(sys.argv) > 1 else "Østmarka").lower()
    gb_user, gb_pass = os.getenv("GOLFBOX_USERNAME"), os.getenv("GOLFBOX_PASSWORD")
    with sync_playwright() as p:
        b = p.chromium.launch(headless=os.getenv("GOLFBOX_HEADLESS") == "1")
        ca = {"viewport": {"width": 1400, "height": 950}}
        if gp.STATE_FILE.exists():
            ca["storage_state"] = str(gp.STATE_FILE)
        ctx = b.new_context(**ca)
        fr = gp.open_score_form(ctx, gb_user, gb_pass)
        if not fr:
            print("❌ Kunne ikke åpne skjema (økt utløpt?)")
            b.close()
            return

        # Velg klubb som matcher term
        clubs = [o for o in gp._options(fr, "fld_Club") if o.get("value")]
        club = next((o for o in clubs if term in o["text"].lower()), None)
        if not club:
            print(f"Fant ingen klubb med «{term}». Klubber: {[c['text'] for c in clubs][:20]}")
            b.close()
            return
        print(f"Klubb: {club['text']}")
        gp._pick_course  # noqa
        fr.select_option("#fld_Club", value=club["value"])
        gp._wait_select_stable(fr, "fld_Course", settle=2.0, timeout=12.0)

        courses = [o for o in gp._options(fr, "fld_Course") if o.get("value")]
        print(f"{len(courses)} bane(r):\n")
        for c in courses:
            fr.select_option("#fld_Course", value=c["value"])
            gp._wait_select_stable(fr, "fld_Tee", settle=1.2, timeout=8.0)
            gp._ensure_tees_loaded(fr, timeout=8.0)
            tees = [o.get("text", "").strip() for o in gp._options(fr, "fld_Tee") if o.get("value")]
            # les rating for hver tee
            reads = []
            for t in [o for o in gp._options(fr, "fld_Tee") if o.get("value")]:
                fr.select_option("#fld_Tee", value=t["value"])
                time.sleep(0.3)
                r, s = gp._read_rating_slope(fr)
                reads.append(f"{t['text'].strip()}={r}/{s}")
            print(f"  • {c['text'].strip():40} tees=[{', '.join(reads) if reads else 'INGEN'}]")
        b.close()


if __name__ == "__main__":
    main()
