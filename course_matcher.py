#!/usr/bin/env python3
"""
Universell koordinat-matcher: kobler en Garmin-bane (GPS-posisjon) til riktig
Golfbox klubb/bane/tee – uavhengig av hva banen heter.

Kjernen i den skalerbare løsningen: koordinatene kommer fra Garmin (vi henter dem
allerede per runde). Når én bruker bekrefter hvilken Golfbox-klubb en posisjon
tilhører, lagres det i referanse-databasen (course_db.json) med koordinater. Alle
senere runder – uansett bruker og uansett Garmin-navn – matcher da på POSISJON.

Fungerer verden over. For nå er «destinasjonen» Golfbox (Norden); andre nasjonale
systemer kan legges til senere uten å endre matcheren.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
DB_FILE = PROJECT_DIR / "course_db.json"
CATALOG_FILE = PROJECT_DIR / os.getenv("GOLFBOX_CATALOG_FILE", "golfbox_catalog_no.json")

# Hvor nær en LÆRT bane må være for å regnes som treff (meter, presis).
MATCH_RADIUS_M = 700
# Hvor nær to oppføringer må være for å regnes som SAMME bane (dedup, meter).
DEDUP_RADIUS_M = 250
# Radius for GEOKODET katalog (klubb-nivå). Stram nok til å unngå nabo-klubber
# i tette områder, men romslig nok for grovere geokoding.
CATALOG_RADIUS_M = 1500


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Avstand i meter mellom to GPS-punkter."""
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def load_db() -> list:
    if DB_FILE.exists():
        try:
            data = json.loads(DB_FILE.read_text(encoding="utf-8"))
            return data.get("courses", []) if isinstance(data, dict) else list(data)
        except Exception:
            return []
    return []


def _save_db(courses: list) -> None:
    DB_FILE.write_text(
        json.dumps({"courses": courses}, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def load_catalog() -> list:
    """Geokodet Golfbox-katalog (klubb-nivå, valgfri): [{club, lat, lon, ...}]."""
    if CATALOG_FILE.exists():
        try:
            data = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
            return data.get("clubs", []) if isinstance(data, dict) else list(data)
        except Exception:
            return []
    return []


def match(lat, lon, name: str = "", max_meters: float = MATCH_RADIUS_M):
    """Finn nærmeste Golfbox-bane for en posisjon.
    Prioritet: 1) LÆRT base (presis) 2) geokodet katalog (grovere, klubb-nivå).
    Returnerer oppføringen ({club, course, tee, ...}) + avstand, eller None."""
    if lat is None or lon is None:
        return None
    lat, lon = float(lat), float(lon)

    # 1) Presise, lærte oppføringer (course_db) – har klubb + bane + tee.
    best, best_d = None, float("inf")
    for e in load_db():
        elat, elon = e.get("lat"), e.get("lon")
        if elat is None or elon is None:
            continue
        d = haversine_m(lat, lon, float(elat), float(elon))
        if d < best_d:
            best, best_d = e, d
    if best is not None and best_d <= max_meters:
        return {**best, "distance_m": round(best_d), "source": "learned"}

    # 2) Geokodet katalog (klubb-nivå) – grovere posisjon, bredere radius.
    cbest, cbest_d = None, float("inf")
    for c in load_catalog():
        clat, clon = c.get("lat"), c.get("lon")
        if clat is None or clon is None:
            continue
        d = haversine_m(lat, lon, float(clat), float(clon))
        if d < cbest_d:
            cbest, cbest_d = c, d
    if cbest is not None and cbest_d <= CATALOG_RADIUS_M:
        return {
            "club": cbest.get("club", ""),
            "course": "",
            "tee": "",
            "distance_m": round(cbest_d),
            "source": "catalog",
        }
    return None


def learn(garmin_name: str, lat, lon, sel: dict, country: str = "") -> dict | None:
    """Lagre/oppdater en Golfbox-oppføring for en posisjon (fra brukerens valg).
    sel = {club, course, tee}. Returnerer oppføringen som ble lagret, eller None."""
    if not sel.get("club") or lat is None or lon is None:
        return None
    lat, lon = float(lat), float(lon)
    entry = {
        "garmin_name": garmin_name,
        "country": country,
        "lat": lat,
        "lon": lon,
        "club": sel.get("club", ""),
        "course": sel.get("course", ""),
        "tee": sel.get("tee", ""),
    }
    courses = load_db()
    for e in courses:
        if e.get("lat") is None or e.get("lon") is None:
            continue
        if haversine_m(lat, lon, float(e["lat"]), float(e["lon"])) < DEDUP_RADIUS_M:
            e.update(entry)  # oppdater eksisterende bane
            _save_db(courses)
            _contribute(entry)
            return entry
    courses.append(entry)  # ny bane
    _save_db(courses)
    _contribute(entry)
    return entry


def _contribute(entry: dict) -> None:
    """Send den lærte banen opp til den delte sentralbasen (best effort)."""
    try:
        import central_registry

        e = dict(entry)
        e.setdefault("source", "learned")
        central_registry.contribute(e)
    except Exception:
        pass


if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 3:
        # Test: python3 course_matcher.py <lat> <lon>
        m = match(float(sys.argv[1]), float(sys.argv[2]))
        if m:
            print(f"Match ({m.get('source')}, {m.get('distance_m')} m): "
                  f"{m.get('club')} / {m.get('course','')} / tee {m.get('tee','')}")
        else:
            print("Ingen match innenfor radius.")
    else:
        db = load_db()
        cat = load_catalog()
        cat_coords = sum(1 for c in cat if c.get("lat") is not None)
        print(f"Lærte baner (course_db): {len(db)}")
        print(f"Katalog med koordinater:  {cat_coords}/{len(cat)}")
        print("\nTest en posisjon:  python3 course_matcher.py <lat> <lon>")
