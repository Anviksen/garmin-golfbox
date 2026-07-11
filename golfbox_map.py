#!/usr/bin/env python3
"""
Fase 3, steg 1 – Kartlegg Golfbox score-skjema.

Dette scriptet åpner en ekte nettleser. DU logger inn i Golfbox og navigerer til
«Min GolfBox» → «Innlever score» slik at du ser score-skjemaet. Deretter trykker
du ENTER i terminalen, og scriptet lagrer hele siden (inkludert alle iframes) som
HTML + et skjermbilde i mappa data/golfbox_map/.

Da kan vi lese de eksakte feltene og knappene, og bygge selve innsendings-scriptet
uten å gjette.

Kjøres slik (se README.md):
    python3 golfbox_map.py
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Mangler Playwright. Kjør:")
    print("  pip install -r requirements.txt")
    print("  playwright install chromium")
    raise SystemExit(1)

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*a, **k):
        return None

PROJECT_DIR = Path(__file__).resolve().parent
OUT = PROJECT_DIR / "data" / "golfbox_map"

START_URL = "https://golfbox.golf/"


def dump(page, label: str) -> None:
    """Lagre hovedside + alle iframes som HTML, pluss et skjermbilde."""
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{label}_page.html").write_text(page.content(), encoding="utf-8")
    try:
        page.screenshot(path=str(OUT / f"{label}.png"), full_page=True)
    except Exception as e:
        print(f"  (klarte ikke ta skjermbilde: {e})")

    frames = page.frames
    print(f"  Fant {len(frames)} ramme(r) på siden.")
    for i, fr in enumerate(frames):
        try:
            html = fr.content()
        except Exception as e:
            html = f"<!-- klarte ikke lese ramme: {e} -->"
        (OUT / f"{label}_frame_{i}.html").write_text(
            f"<!-- frame #{i} url: {fr.url} -->\n{html}", encoding="utf-8"
        )
    print(f"  Lagret HTML + skjermbilde i {OUT}")


def main() -> None:
    load_dotenv(PROJECT_DIR / ".env")
    user = os.getenv("GOLFBOX_USERNAME")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()
        page.goto(START_URL, wait_until="domcontentloaded")

        print("\n" + "=" * 70)
        print("🌐 Nettleser åpnet på Golfbox.")
        if user:
            print(f"   (Brukernavn {user} ligger i .env – men logg inn manuelt her.)")
        print("\n   GJØR DETTE I NETTLESER-VINDUET:")
        print("   1. Logg inn i Golfbox.")
        print("   2. Gå til «Min GolfBox» → «Innlever score».")
        print("   3. Velg en bane/tee slik at selve scorekort-skjemaet vises")
        print("      (gjerne kryss av «Tast inn hullscorer»).")
        print("\n   Kom så tilbake hit og trykk ENTER for å lagre skjemaet.")
        print("=" * 70)
        input("\n>>> Trykk ENTER når score-skjemaet vises i nettleseren ... ")

        print("\n💾 Lagrer score-skjemaet ...")
        dump(page, "innlever_score")

        print("\n✅ Ferdig! Send meg beskjed, så leser jeg filene i data/golfbox_map/")
        input(">>> Trykk ENTER for å lukke nettleseren ... ")
        browser.close()


if __name__ == "__main__":
    main()
