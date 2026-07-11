#!/usr/bin/env python3
"""
Seed sentralbasen (engangs-opplasting).

Laster opp det du allerede har lokalt – lærte baner (course_db.json) OG katalogen
med koordinater (golfbox_catalog_no.json) – til Supabase, så den delte basen
starter med ~130 norske baner i stedet for tom.

Kjøres én gang etter at Supabase er satt opp (se SENTRALISERING.md):
    python3 seed_central.py
"""

from __future__ import annotations

import os

import course_matcher
import central_registry

COUNTRY = os.getenv("GOLFBOX_COUNTRY", "no").lower()


def main() -> None:
    if not central_registry.is_configured():
        print("Sentralbasen er ikke satt opp. Sett SUPABASE_URL / SUPABASE_ANON_KEY i .env "
              "(se SENTRALISERING.md).")
        return

    entries = []

    # 1) Lærte baner (presise, full info).
    for e in course_matcher.load_db():
        if e.get("lat") is not None and e.get("club"):
            entries.append({**e, "source": "learned"})

    # 2) Katalog-klubber med koordinater (klubb-nivå).
    for c in course_matcher.load_catalog():
        if c.get("lat") is not None and c.get("club"):
            entries.append({
                "lat": c["lat"], "lon": c["lon"], "club": c["club"],
                "course": "", "tee": "", "garmin_name": "",
                "country": COUNTRY, "source": "catalog",
            })

    print(f"Laster opp {len(entries)} baner til sentralbasen ...")
    ok = 0
    for e in entries:
        if central_registry.contribute(e):
            ok += 1
    print(f"✅ Ferdig. {ok}/{len(entries)} baner lastet opp til sentralbasen.")


if __name__ == "__main__":
    main()
