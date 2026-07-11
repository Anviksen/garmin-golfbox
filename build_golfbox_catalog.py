#!/usr/bin/env python3
"""
Bygg Golfbox-katalogen: alle klubber → baner → tee-er, på én gjennomkjøring.

Dette gir fasit-navnene (og GUID-er) for HELE Golfbox-porteføljen i landet du er
logget inn i. Kombinert med koordinat-læringen (course_db.json) blir dette den
sentrale referanse-basen for et produkt – og kan kjøres på hvert nordisk
Golfbox-portal (NO/DK/SE/IS/FI) for å dekke hele Norden.

Kjøres slik (bruker samme lagrede innlogging som resten):
    python3 build_golfbox_catalog.py

Tar noen minutter (drives gjennom skjemaet klubb for klubb). Skriver
golfbox_catalog.json.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

import golfbox_post as gp  # gjenbruk SCORE_URL, STATE_FILE, try_navigate_to_score

PROJECT_DIR = Path(__file__).resolve().parent

# Land-kode styrer hvilken Golfbox-portal + hvilken katalogfil vi bruker.
# Kjør f.eks.:  GOLFBOX_COUNTRY=dk python3 build_golfbox_catalog.py
# (krever at du er logget inn på det landets Golfbox – egen økt per land).
COUNTRY = os.getenv("GOLFBOX_COUNTRY", "no").lower()
_PORTALS = {
    "no": "https://www.golfbox.no",
    "dk": "https://www.golfbox.dk",
    "is": "https://www.golfbox.is",
    "fi": "https://www.golfbox.fi",
    "se": "https://www.golfbox.se",
}
_PATH = "/site/my_golfbox/score/whs/newWHSScore.asp"
SCORE_URL = os.getenv("GOLFBOX_SCORE_URL") or (_PORTALS.get(COUNTRY, _PORTALS["no"]) + _PATH)
CATALOG_FILE = PROJECT_DIR / f"golfbox_catalog_{COUNTRY}.json"


def _find_form_frame(ctx):
    for pg in list(ctx.pages):
        try:
            frames = pg.frames
        except Exception:
            continue
        for fr in frames:
            try:
                if fr.query_selector("#fld_Club"):
                    return fr
            except Exception:
                continue
    return None


def _options(fr, selector):
    return fr.eval_on_selector_all(
        selector,
        "els => els.map(e => ({value: e.value, text: e.textContent.trim()}))",
    )


def main() -> None:
    if not gp.STATE_FILE.exists():
        print("Ingen lagret Golfbox-innlogging. Kjør ⛳ / golfbox_post.py én gang først.")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(
            viewport={"width": 1400, "height": 950}, storage_state=str(gp.STATE_FILE)
        )
        page = ctx.new_page()
        try:
            page.goto(SCORE_URL, wait_until="domcontentloaded", timeout=20000)
        except Exception:
            pass

        print(f"Land: {COUNTRY.upper()} · portal: {SCORE_URL.split('/site')[0]}")
        print("Navigerer til score-skjemaet ...")
        fr = None
        deadline = time.time() + 180
        while time.time() < deadline:
            fr = _find_form_frame(ctx)
            if fr:
                break
            for pg in list(ctx.pages):
                if "golfbox" in (pg.url or "").lower():
                    try:
                        gp.try_navigate_to_score(pg)
                    except Exception:
                        pass
            time.sleep(3)

        if not fr:
            print("❌ Fant ikke skjemaet. Logg inn i vinduet og prøv igjen.")
            return

        clubs = _options(fr, "#fld_Club option")
        clubs = [c for c in clubs if c.get("value") and c.get("text")]
        print(f"Fant {len(clubs)} klubber. Henter baner og tee-er ...\n")

        catalog = []
        for i, club in enumerate(clubs, 1):
            try:
                fr.select_option("#fld_Club", value=club["value"])
                time.sleep(1.5)  # changeClub() laster baner
                courses = [c for c in _options(fr, "#fld_Course option")
                           if c.get("value") and c.get("text")]
                club_entry = {"club": club["text"], "guid": club["value"], "courses": []}
                for course in courses:
                    try:
                        fr.select_option("#fld_Course", value=course["value"])
                        time.sleep(1.0)  # changeCourse() laster tees
                        tees = [t for t in _options(fr, "#fld_Tee option") if t.get("text")]
                        club_entry["courses"].append(
                            {"course": course["text"], "tees": [t["text"] for t in tees]}
                        )
                    except Exception:
                        club_entry["courses"].append({"course": course["text"], "tees": []})
                catalog.append(club_entry)
                print(f"[{i}/{len(clubs)}] {club['text']}: {len(courses)} bane(r)")
                # Lagre underveis, så vi ikke mister alt hvis noe stopper.
                CATALOG_FILE.write_text(
                    json.dumps({"clubs": catalog}, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            except Exception as e:
                print(f"[{i}/{len(clubs)}] ⚠️ {club['text']}: {e}")

        print(f"\n✅ Ferdig. {len(catalog)} klubber lagret i {CATALOG_FILE}")
        browser.close()


if __name__ == "__main__":
    main()
