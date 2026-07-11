#!/usr/bin/env python3
"""
Fest PRESISE koordinater på Golfbox-katalogen via OpenStreetMap Overpass.

I stedet for å geokode klubbnavn ett for ett (unøyaktig, tettstedssenter), henter
dette scriptet ALLE golfbane-polygonene i landet i ett kall – med presis posisjon
(banens senter) – og kobler dem til katalogen på navn.

Mye bedre presisjon og dekning enn navne-geokoding. Kjøres etter
build_golfbox_catalog.py:
    python3 enrich_catalog_osm.py
    GOLFBOX_COUNTRY=dk python3 enrich_catalog_osm.py   # annet land
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
COUNTRY = os.getenv("GOLFBOX_COUNTRY", "no").lower()
CATALOG_FILE = PROJECT_DIR / f"golfbox_catalog_{COUNTRY}.json"

# Bounding-box per land (sør, vest, nord, øst) – mye lettere enn område-oppslag.
_BBOX = {
    "no": (57.0, 4.0, 72.0, 32.0),
    "dk": (54.4, 7.8, 58.0, 15.4),
    "se": (55.0, 10.5, 69.2, 24.3),
    "fi": (59.6, 19.0, 70.2, 31.7),
    "is": (63.2, -24.7, 66.7, -13.2),
}
_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
_GENERIC = ("golfklubb", "golfpark", "golfbane", "golfclub", "golf", "klubb", "club", "gk", "il")


def core(name: str) -> str:
    s = (name or "").lower().replace("aa", "å")
    for w in _GENERIC:
        s = s.replace(w, " ")
    return "".join(ch for ch in s if ch.isalnum())


def fetch_osm_courses() -> list:
    """Hent alle golfbaner i landet fra Overpass (bbox): [{name, lat, lon}].
    Prøver flere Overpass-servere ved timeout."""
    s, w, n, e = _BBOX.get(COUNTRY, _BBOX["no"])
    query = f"""
    [out:json][timeout:180];
    (
      way["leisure"="golf_course"]({s},{w},{n},{e});
      relation["leisure"="golf_course"]({s},{w},{n},{e});
      node["leisure"="golf_course"]({s},{w},{n},{e});
    );
    out center tags;
    """
    data = urllib.parse.urlencode({"data": query}).encode()
    payload = None
    last_err = None
    for endpoint in _ENDPOINTS:
        try:
            print(f"  spør {endpoint.split('/')[2]} ...")
            req = urllib.request.Request(
                endpoint, data=data,
                headers={"User-Agent": "garmin-golfbox-catalog/1.0 (hobbyprosjekt)"},
            )
            with urllib.request.urlopen(req, timeout=180) as r:
                payload = json.loads(r.read().decode("utf-8"))
            break
        except Exception as ex:
            last_err = ex
            print(f"    (feilet: {ex} – prøver neste server)")
    if payload is None:
        raise RuntimeError(f"Alle Overpass-servere feilet. Siste: {last_err}")
    out = []
    for e in payload.get("elements", []):
        tags = e.get("tags", {})
        name = tags.get("name") or tags.get("official_name") or ""
        if not name:
            continue
        if "center" in e:
            lat, lon = e["center"]["lat"], e["center"]["lon"]
        elif "lat" in e:
            lat, lon = e["lat"], e["lon"]
        else:
            continue
        out.append({"name": name, "lat": float(lat), "lon": float(lon)})
    return out


def main() -> None:
    if not CATALOG_FILE.exists():
        print(f"Fant ikke {CATALOG_FILE.name}. Kjør build_golfbox_catalog.py først.")
        return

    print("Henter alle golfbaner fra OpenStreetMap (Overpass) ...")
    try:
        osm = fetch_osm_courses()
    except Exception as e:
        print(f"❌ Overpass-kall feilet: {e}")
        return
    print(f"Fant {len(osm)} golfbaner i OSM. Kobler til katalogen ...\n")

    # Bygg oppslag på kjernenavn.
    osm_by_core = {}
    for o in osm:
        osm_by_core.setdefault(core(o["name"]), o)

    data = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    clubs = data.get("clubs", [])
    hits = 0
    for club in clubs:
        cc = core(club.get("club", ""))
        match = osm_by_core.get(cc)
        if not match and cc:
            # delvis treff (kjernenavn inni hverandre, min. 4 tegn)
            for oc, o in osm_by_core.items():
                if len(oc) >= 4 and (oc in cc or cc in oc):
                    match = o
                    break
        if match:
            club["lat"], club["lon"] = match["lat"], match["lon"]
            club["osm_name"] = match["name"]
            hits += 1

    CATALOG_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    with_coords = sum(1 for c in clubs if c.get("lat") is not None)
    print(f"✅ Ferdig. Koblet {hits} klubber til OSM-baner. "
          f"{with_coords}/{len(clubs)} klubber har nå koordinater i {CATALOG_FILE.name}.")


if __name__ == "__main__":
    main()
