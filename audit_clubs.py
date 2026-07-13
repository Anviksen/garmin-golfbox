#!/usr/bin/env python3
"""
Risiko-audit av ALLE klubbene i katalogen (offline – ingen nettleser, ingen spilling).

Kan ikke teste selve matchingen uten spilledata, men kan proaktivt flagge klubbene
som SANNSYNLIGVIS trenger ekstra oppmerksomhet:
  • flere baner  → bane-valget må skille dem (par/navn/farge/hull-logikk)
  • farge-kombo-baner (Haga-type) → håndteres, men verdt å vite
  • kun tall-tee-er → tee-matching avhenger av at Garmin sin rating stemmer (ellers
    best-effort/flagg), i motsetning til farge-tee-er som matcher direkte

    python3 audit_clubs.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
COUNTRY = os.getenv("GOLFBOX_COUNTRY", "no").lower()
CATALOG = PROJECT_DIR / f"golfbox_catalog_{COUNTRY}.json"

_COLORWORDS = ("rød", "gul", "blå", "grønn", "hvit", "svart", "oransje", "gull",
               "red", "yellow", "blue", "green", "white", "black")


def _is_number(s: str) -> bool:
    return any(ch.isdigit() for ch in s) and not any(c in s.lower() for c in _COLORWORDS)


def main() -> None:
    if not CATALOG.exists():
        print(f"Fant ikke {CATALOG.name}.")
        return
    clubs = json.loads(CATALOG.read_text(encoding="utf-8")).get("clubs", [])

    multi, colorcombo, numeric_tees = [], [], []
    single = 0
    for c in clubs:
        courses = c.get("courses", []) or []
        n = len(courses)
        if n <= 1:
            single += 1
        else:
            multi.append((c["club"], n))
        for co in courses:
            name = co.get("course", "")
            colors = [w for w in _COLORWORDS if w in name.lower()]
            if len(set(colors)) >= 2:
                colorcombo.append(f"{c['club']} → {name}")
            tees = co.get("tees", []) or []
            if tees and all(_is_number(str(t)) for t in tees):
                numeric_tees.append(c["club"])
                break

    print(f"KATALOG: {len(clubs)} klubber\n")
    print(f"✅ {single} klubber med ÉN bane (bane-valg trivielt)")
    print(f"⚠️  {len(multi)} klubber med FLERE baner (bane-valg må skille dem):")
    for club, n in sorted(multi, key=lambda x: -x[1]):
        print(f"      {n:2d} baner:  {club}")

    if colorcombo:
        print(f"\n🎨 {len(colorcombo)} farge-kombo-baner (håndteres av farge-sett-match):")
        for x in colorcombo[:20]:
            print(f"      {x}")
        if len(colorcombo) > 20:
            print(f"      … + {len(colorcombo) - 20} til")

    print(f"\n🔢 {len(set(numeric_tees))} klubber med KUN tall-tee-er "
          f"(tee via rating; best-effort+flagg hvis Garmin-rating avviker):")
    for club in sorted(set(numeric_tees))[:30]:
        print(f"      {club}")
    if len(set(numeric_tees)) > 30:
        print(f"      … + {len(set(numeric_tees)) - 30} til")

    print("\n— Merk: katalog-dataene for et fåtall klubber kan være ufullstendige "
          "(bygget via scraping). Ekte matching bekreftes først når en runde spilles "
          "der; sikkerhetsnettet garanterer at intet feil postes i mellomtiden.")


if __name__ == "__main__":
    main()
