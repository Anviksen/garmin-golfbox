#!/usr/bin/env python3
"""Feilsøk: finn «GolfBox»-knappen på norskgolf.no + sjekk at credentials er lastet."""
from __future__ import annotations

import os
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except Exception:
    pass

u, p = os.getenv("GOLFBOX_USERNAME"), os.getenv("GOLFBOX_PASSWORD")
print(f"GOLFBOX_USERNAME satt: {bool(u)} · GOLFBOX_PASSWORD satt: {bool(p)}")

out = Path(__file__).resolve().parent / "data" / "golfbox_map"
out.mkdir(parents=True, exist_ok=True)

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=False)
    page = b.new_context(viewport={"width": 1400, "height": 950}).new_page()
    page.goto("https://www.norskgolf.no/", wait_until="domcontentloaded", timeout=30000)
    time.sleep(5)

    # Skriv ut alle klikkbare elementer som nevner "golf" / "logg".
    els = page.query_selector_all("a, button")
    print(f"\n{len(els)} lenker/knapper totalt. Relevante:")
    for e in els:
        try:
            txt = (e.inner_text() or "").strip().replace("\n", " ")
            href = e.get_attribute("href") or ""
            hay = (txt + " " + href).lower()
            if any(w in hay for w in ("golfbox", "golf box", "logg", "login", "min golf")):
                tag = e.evaluate("el => el.tagName.toLowerCase()")
                print(f"  <{tag}> text={txt!r}  href={href!r}")
        except Exception:
            continue

    (out / "norskgolf_home.html").write_text(page.content(), encoding="utf-8")
    page.screenshot(path=str(out / "norskgolf_home.png"), full_page=True)
    print(f"\nLagret HTML + skjermbilde i {out}")
    print("Lukk nettleservinduet når du er ferdig.")
    try:
        page.wait_for_event("close", timeout=0)
    except Exception:
        pass
