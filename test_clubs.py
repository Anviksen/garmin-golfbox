#!/usr/bin/env python3
"""
Klubb-dekning / koordinat-kvalitet (rask, uten nettleser).

Navne-matching av katalog-klubbene er trivielt (navnene kom FRA GolfBox). Den ekte
risikoen er koordinatene: klubber som MANGLER koordinater (må stole på navn alene),
og klubber som ligger så nær hverandre at GPS kan «snappe» til feil naboklubb.

Denne rapporten flagger begge – proaktivt, for hele landet, uten å spille en runde.

    python3 test_clubs.py
    GOLFBOX_COUNTRY=dk python3 test_clubs.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import course_matcher as cm

PROJECT_DIR = Path(__file__).resolve().parent
COUNTRY = os.getenv("GOLFBOX_COUNTRY", "no").lower()
CATALOG = PROJECT_DIR / f"golfbox_catalog_{COUNTRY}.json"


def main() -> None:
    if not CATALOG.exists():
        print(f"Fant ikke {CATALOG.name}.")
        return
    clubs = json.loads(CATALOG.read_text(encoding="utf-8")).get("clubs", [])
    with_coords = [c for c in clubs if c.get("lat") is not None]
    missing = [c for c in clubs if c.get("lat") is None]

    print(f"Katalog: {len(clubs)} klubber · {len(with_coords)} med koordinater · "
          f"{len(missing)} uten\n")

    # 1) Klubber uten koordinater – matcher kun på navn (GPS kan ikke hjelpe).
    if missing:
        print(f"⚠️  {len(missing)} klubber UTEN koordinater (kun navne-match):")
        for c in sorted(missing, key=lambda x: x["club"]):
            print(f"    • {c['club']}")
        print()

    # 2) Nær-kollisjoner: klubber innenfor matche-radius av en annen klubb.
    #    Der kan en runde uten egne koordinater «snappe» til feil naboklubb
    #    (sikringen i course_matcher krever da navne-slektskap eller <400 m).
    radius = cm.CATALOG_RADIUS_M
    pairs = []
    for i, a in enumerate(with_coords):
        for b in with_coords[i + 1:]:
            d = cm.haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
            if d <= radius:
                pairs.append((round(d), a["club"], b["club"]))
    pairs.sort()
    if pairs:
        print(f"⚠️  {len(pairs)} klubb-par ligger < {radius} m fra hverandre "
              f"(GPS-forvekslings-risiko):")
        for d, a, b in pairs:
            print(f"    • {d:4d} m:  {a}  ↔  {b}")
        print("\n    (Sikringen håndterer dette når navnene er ulike, men verdt å kjenne til.)")
    else:
        print(f"✅ Ingen klubber ligger nærmere enn {radius} m av hverandre.")

    print(f"\nOppsummering: {len(with_coords)}/{len(clubs)} klubber har presis GPS. "
          f"De {len(missing)} uten er avhengige av navne-match (som regel greit siden "
          f"Garmin-navnet ofte er likt), men læres presist første gang de spilles.")


if __name__ == "__main__":
    main()
