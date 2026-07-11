#!/usr/bin/env python3
"""
Geokod Golfbox-katalogen: gjør klubbnavn → GPS-koordinater via OpenStreetMap
(Nominatim), og fester koordinatene på golfbox_catalog_<land>.json.

Da kan koordinat-matcheren finne riktig klubb for HELE landet – ikke bare banene
du har spilt. (Presise, lærte GPS-oppføringer har fortsatt førsteprioritet.)

Kjøres slik (respekterer Nominatim: 1 spørring/sek):
    python3 geocode_catalog.py
    GOLFBOX_COUNTRY=dk python3 geocode_catalog.py   # for et annet land

Trygt å avbryte og starte igjen – den hopper over klubber som alt har koordinater.
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
COUNTRY = os.getenv("GOLFBOX_COUNTRY", "no").lower()
CATALOG_FILE = PROJECT_DIR / f"golfbox_catalog_{COUNTRY}.json"

_COUNTRY_NAME = {"no": "Norge", "dk": "Danmark", "is": "Island", "fi": "Finland", "se": "Sverige"}
_UA = "garmin-golfbox-catalog/1.0 (personlig hobbyprosjekt)"
_GENERIC = ("golfklubb", "golfpark", "golfbane", "golf", "klubb", "gk", "il", "club")


def _core(name: str) -> str:
    s = (name or "").lower()
    for w in _GENERIC:
        s = s.replace(w, " ")
    return " ".join(s.split()).strip()


def _query(q: str):
    url = (
        "https://nominatim.openstreetmap.org/search?q="
        + urllib.parse.quote(q)
        + f"&format=jsonv2&limit=1&countrycodes={COUNTRY}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        pass
    return None, None


def geocode(name: str):
    """Slå opp klubbnavn → (lat, lon). Prøver flere varianter for høyere treffrate."""
    country = _COUNTRY_NAME.get(COUNTRY, "")
    core = _core(name)
    variants = [
        f"{name}, {country}",
        name,
        f"{core} golfbane, {country}" if core else "",
        f"{core} golf, {country}" if core else "",
    ]
    for v in variants:
        if not v.strip():
            continue
        lat, lon = _query(v)
        if lat is not None:
            return lat, lon
        time.sleep(1.1)  # respekter Nominatim mellom variantene også
    return None, None


def main() -> None:
    if not CATALOG_FILE.exists():
        print(f"Fant ikke {CATALOG_FILE.name}. Kjør build_golfbox_catalog.py først.")
        return

    data = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    clubs = data.get("clubs", [])
    todo = [c for c in clubs if c.get("lat") is None]
    print(f"{len(clubs)} klubber, {len(todo)} mangler koordinater. Geokoder ...\n")

    found = 0
    for i, club in enumerate(clubs, 1):
        if club.get("lat") is not None:
            continue
        name = club.get("club", "")
        lat, lon = geocode(name)
        if lat is not None:
            club["lat"], club["lon"] = lat, lon
            found += 1
            print(f"[{i}/{len(clubs)}] {name} → {lat:.5f}, {lon:.5f}")
        else:
            print(f"[{i}/{len(clubs)}] {name} → ikke funnet (fylles av læring senere)")
        # Lagre underveis + respekter Nominatim (1 spørring/sek).
        CATALOG_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        time.sleep(1.1)

    # Sikkerhets-opprydding: nuller ut klubber som deler NØYAKTIG samme koordinat
    # (da har en bred søkevariant truffet feil sted – feil koord er verre enn ingen).
    from collections import defaultdict

    by_coord = defaultdict(list)
    for c in clubs:
        if c.get("lat") is not None:
            by_coord[(c["lat"], c["lon"])].append(c)
    dropped = 0
    for coord, group in by_coord.items():
        if len(group) > 1:
            for c in group:
                c["lat"], c["lon"] = None, None
                dropped += 1
            print(f"  ⚠️ Fjernet kollisjon: {', '.join(g['club'] for g in group)}")
    if dropped:
        CATALOG_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    with_coords = sum(1 for c in clubs if c.get("lat") is not None)
    print(f"\n✅ Ferdig. {with_coords}/{len(clubs)} klubber har pålitelige koordinater "
          f"i {CATALOG_FILE.name}."
          + (f" ({dropped} kollisjoner fjernet)" if dropped else ""))


if __name__ == "__main__":
    main()
