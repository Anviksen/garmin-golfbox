#!/usr/bin/env python3
"""Full debug av matching for én runde – dumper ALLE noter + hva som faktisk står
valgt i skjemaet (klubb/bane/tee) til slutt. Poster ingenting.

    python3 debug_round.py 336115654
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except Exception:
    pass

import golfbox_post as gp


def _sel_text(fr, sel_id):
    try:
        val = fr.eval_on_selector(f"#{sel_id}", "el => el.value") or ""
    except Exception:
        val = ""
    txt = next((o.get("text", "").strip() for o in gp._options(fr, sel_id)
                if o.get("value") == val), "")
    return val, txt


def main() -> None:
    rid = sys.argv[1] if len(sys.argv) > 1 else "336115654"
    rnd = gp.get_round(rid)
    print("Runde:", rnd.get("course"), "| teeBox:", rnd.get("teeBox"),
          "| rating:", rnd.get("teeBoxRating"), "| slope:", rnd.get("teeBoxSlope"))
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
        notes, status = gp.fill_score_form(fr, rnd, for_test=True)
        cv, ct = _sel_text(fr, "fld_Course")
        tv, tt = _sel_text(fr, "fld_Tee")
        tees = [o.get("text", "").strip() for o in gp._options(fr, "fld_Tee") if o.get("value")]
        b.close()
    print("\n--- ALLE NOTER ---")
    for n in notes:
        print("  " + n)
    print("\n--- FAKTISK VALGT I SKJEMA ---")
    print(f"  Bane:  value={cv!r}  text={ct!r}")
    print(f"  Tee:   value={tv!r}  text={tt!r}")
    print(f"  Tee-liste nå: {tees}")
    print(f"  status: {status}")


if __name__ == "__main__":
    main()
