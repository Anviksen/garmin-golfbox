#!/usr/bin/env python3
"""
Rydd koordinat-kollisjoner i golfbox_catalog_<land>.json.

To eller flere klubber som deler NØYAKTIG samme koordinat er en feil (fra geokoding
/ OSM-berikelse der ulike klubber matchet samme punkt). Feil koordinat er verre enn
ingen (kan gi GPS-«snapping» til feil naboklubb), så vi nuller de kolliderte – da
faller de trygt til navne-match, og kan re-geokodes/OSM-berikes senere.

    python3 clean_catalog_coords.py
    GOLFBOX_COUNTRY=dk python3 clean_catalog_coords.py
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
COUNTRY = os.getenv("GOLFBOX_COUNTRY", "no").lower()
CATALOG = PROJECT_DIR / f"golfbox_catalog_{COUNTRY}.json"


def main() -> None:
    if not CATALOG.exists():
        print(f"Fant ikke {CATALOG.name}.")
        return
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    clubs = data.get("clubs", [])

    by_coord = defaultdict(list)
    for c in clubs:
        if c.get("lat") is not None and c.get("lon") is not None:
            by_coord[(round(c["lat"], 4), round(c["lon"], 4))].append(c)

    dropped = 0
    for coord, group in by_coord.items():
        if len(group) > 1:
            print(f"⚠️  Kollisjon @ {coord}: " + ", ".join(g["club"] for g in group)
                  + "  → nuller koordinater")
            for c in group:
                c["lat"], c["lon"] = None, None
                c.pop("osm_name", None)
                dropped += 1

    if dropped:
        CATALOG.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    with_coords = sum(1 for c in clubs if c.get("lat") is not None)
    print(f"\n✅ Ferdig. {dropped} kolliderte koordinater nullet. "
          f"{with_coords}/{len(clubs)} klubber har nå koordinater.")
    if dropped:
        print("Tips: kjør `python3 geocode_catalog.py` for å prøve å re-geokode de nullede "
              "(én og én, uten kollisjon), evt. la dem læres presist ved spill.")


if __name__ == "__main__":
    main()
