#!/usr/bin/env python3
"""
Synk sentralbasen NED til den lokale matcheren.

Henter alle baner fra Supabase og fletter dem inn i course_db.json (dedup på
posisjon). Da får denne maskinen alle baner andre har lært – uten å lære dem selv.

Kjøres jevnlig (f.eks. før auto_sync, eller manuelt):
    python3 sync_registry.py
"""

from __future__ import annotations

import course_matcher
import central_registry


def main() -> None:
    if not central_registry.is_configured():
        print("Sentralbasen er ikke satt opp. Sett SUPABASE_URL / SUPABASE_ANON_KEY i .env "
              "(se SENTRALISERING.md).")
        return

    remote = central_registry.fetch_all()
    print(f"Sentralbasen har {len(remote)} baner. Fletter inn lokalt ...")

    local = course_matcher.load_db()
    added = 0
    for e in remote:
        lat, lon = e.get("lat"), e.get("lon")
        if lat is None or lon is None or not e.get("club"):
            continue
        dup = False
        for l in local:
            if l.get("lat") is None:
                continue
            if course_matcher.haversine_m(
                float(lat), float(lon), float(l["lat"]), float(l["lon"])
            ) < course_matcher.DEDUP_RADIUS_M:
                dup = True
                break
        if not dup:
            local.append({
                "garmin_name": e.get("garmin_name", ""),
                "country": e.get("country", ""),
                "lat": float(lat),
                "lon": float(lon),
                "club": e.get("club", ""),
                "course": e.get("course", ""),
                "tee": e.get("tee", ""),
            })
            added += 1

    course_matcher._save_db(local)
    print(f"✅ Synket. {added} nye baner lagt til. course_db.json har nå {len(local)} baner.")


if __name__ == "__main__":
    main()
