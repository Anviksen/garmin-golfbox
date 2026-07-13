#!/usr/bin/env python3
"""
Test varsling for én runde – UTEN å poste noe til GolfBox.

Kjører tørr-matching (klubb/bane/tee) og sender akkurat det varselet brukeren
ville fått: «fullfør selv» (matchet ikke) eller «dobbeltsjekk» (best-effort tee).
Trygt: ingenting lagres i GolfBox.

    python3 test_notify.py 359548347     # Larvik  → dobbeltsjekk-varsel
    python3 test_notify.py 372259436     # Grønmo  → fullfør-varsel
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
import notify


def main() -> None:
    if len(sys.argv) < 2:
        print("Bruk: python3 test_notify.py <round_id>")
        return
    rid = sys.argv[1]
    rnd = gp.get_round(rid)
    name = rnd.get("course", "?")
    gb_user, gb_pass = os.getenv("GOLFBOX_USERNAME"), os.getenv("GOLFBOX_PASSWORD")
    headless = os.getenv("GOLFBOX_HEADLESS") == "1"

    print(f"Tester matching for «{name}» (poster INGENTING) ...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx_args = {"viewport": {"width": 1400, "height": 950}}
        if gp.STATE_FILE.exists():
            ctx_args["storage_state"] = str(gp.STATE_FILE)
        ctx = browser.new_context(**ctx_args)
        fr = gp.open_score_form(ctx, gb_user, gb_pass)
        if not fr:
            print("❌ Kunne ikke åpne score-skjemaet (økt utløpt?).")
            browser.close()
            return
        notes, status = gp.fill_score_form(fr, rnd, for_test=True)
        browser.close()

    matched = status["club"] and status["course"] and status["tee"]
    if matched and status.get("tee_uncertain"):
        print(f"→ Matcher, men best-effort tee. Sender «dobbeltsjekk»-varsel ...")
        ok = notify.notify_rounds([], [(name, "tee valgt på skjønn")], [])
    elif matched:
        print("→ Matcher fullt. Ingen varsel nødvendig (alt ville gått automatisk).")
        return
    else:
        reason = next((n.strip() for n in reversed(notes) if "❗" in n or "⚠️" in n),
                      "kunne ikke matches automatisk")
        print(f"→ Matcher ikke ({reason[:70]}). Sender «fullfør selv»-varsel ...")
        ok = notify.notify_rounds([(name, "kunne ikke matches automatisk")], [], [])

    print("✅ Varsel sendt – sjekk e-posten!" if ok
          else "❌ Kunne ikke sende (sjekk GMAIL_USER/GMAIL_APP_PASSWORD i .env).")


if __name__ == "__main__":
    main()
