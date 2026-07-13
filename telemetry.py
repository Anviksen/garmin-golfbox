#!/usr/bin/env python3
"""
Telemetri-rapport: les `attempts`-loggen fra Supabase og vis en datadrevet FEILKØ –
hvilke baner som feiler (og hvorfor), sortert etter hyppighet. Dette er hvordan
«hele Norge» dekkes over tid: brukerne genererer utfallene, du fikser toppen av køen.

    python3 telemetry.py
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except Exception:
    pass

import central_registry


def main() -> None:
    if not central_registry.is_configured():
        print("Sentralbasen er ikke satt opp (SUPABASE_URL/ANON_KEY i .env).")
        return
    rows = central_registry.fetch_attempts()
    if not rows:
        print("Ingen telemetri ennå. Den fylles etter hvert som runder postes/testes.")
        return

    # rows er nyeste først → første forekomst per bane = siste utfall.
    # «matchet» = klubb+bane+tee resolvert (ville postet). «posted» = faktisk lagret.
    agg = {}
    for r in rows:
        key = (r.get("garmin_course") or "?").strip()
        a = agg.setdefault(key, {"n": 0, "posted": 0, "uncertain": 0,
                                 "last_ok": None, "last_reason": ""})
        a["n"] += 1
        if r.get("posted"):
            a["posted"] += 1
        if r.get("tee_uncertain"):
            a["uncertain"] += 1
        if a["last_ok"] is None:
            a["last_ok"] = bool(r.get("club_ok") and r.get("course_ok") and r.get("tee_ok"))
            a["last_reason"] = (r.get("reason") or "").strip()

    total = len(rows)
    baner = len(agg)
    ok_baner = sum(1 for a in agg.values() if a["last_ok"])
    print(f"Telemetri: {total} forsøk · {baner} distinkte baner · "
          f"{ok_baner}/{baner} matcher (klubb+bane+tee)\n")

    # Feilkø: baner der siste utfall IKKE matchet – sortert etter antall forsøk.
    failing = [(k, a) for k, a in agg.items() if not a["last_ok"]]
    failing.sort(key=lambda x: -x[1]["n"])
    if failing:
        print("🔴 FEILKØ (baner som ikke går gjennom – prioritert etter hyppighet):")
        for k, a in failing:
            print(f"    {a['n']:3d}×  {k[:40]:40}  {a['last_reason'][:80]}")
    else:
        print("✅ Ingen baner i feilkøen – alt siste-sett gikk gjennom.")

    # Best-effort tee som bør dobbeltsjekkes.
    uncertain = [(k, a) for k, a in agg.items() if a["last_ok"] and a["uncertain"]]
    if uncertain:
        print("\n🟡 Gikk gjennom, men på BEST-EFFORT tee (dobbeltsjekk anbefalt):")
        for k, a in sorted(uncertain, key=lambda x: -x[1]["n"]):
            print(f"    {a['n']:3d}×  {k[:40]}")


if __name__ == "__main__":
    main()
