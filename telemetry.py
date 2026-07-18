#!/usr/bin/env python3
"""
Telemetri-rapport: les `attempts`-loggen fra Supabase og vis en datadrevet FEILKØ –
hvilke baner som feiler (og hvorfor), sortert etter hyppighet. Dette er hvordan
«hele Norge» dekkes over tid: brukerne genererer utfallene, du fikser toppen av køen.

    python3 telemetry.py                  # alle brukere samlet (som før)
    python3 telemetry.py <navn-eller-id>   # kun én bruker (multi-bruker-feilsøking)
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except Exception:
    pass

import central_registry

try:
    import user_store
except Exception:
    user_store = None  # multi-bruker-oppslag er valgfritt - fungerer fint uten


def _load_user_labels() -> dict:
    """id -> visningsnavn, best effort. Tom dict hvis service-role ikke er satt
    opp (f.eks. et enkelt-bruker-oppsett uten multi-bruker-tabellene ennå)."""
    if user_store is None or not user_store.is_configured():
        return {}
    try:
        return {u["id"]: u.get("label", u["id"]) for u in user_store.list_users()}
    except Exception:
        return {}


def _resolve_user_filter(arg: str, labels: dict) -> str | None:
    """Slå opp en bruker fra CLI-argumentet: eksakt id, eller navn (case-insensitive
    delvis match). Returnerer id-en å filtrere på, eller None hvis ikke funnet."""
    if arg in labels:
        return arg
    arg_low = arg.lower()
    matches = [uid for uid, label in labels.items() if arg_low in label.lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"⚠️  «{arg}» matcher flere brukere ({', '.join(labels[m] for m in matches)}) "
              f"- bruk en mer presis del av navnet, eller selve id-en.")
        return None
    print(f"⚠️  Fant ingen bruker som matcher «{arg}».")
    return None


def main() -> None:
    if not central_registry.is_configured():
        print("Sentralbasen er ikke satt opp (SUPABASE_URL/ANON_KEY i .env).")
        return
    rows = central_registry.fetch_attempts()
    if not rows:
        print("Ingen telemetri ennå. Den fylles etter hvert som runder postes/testes.")
        return

    labels = _load_user_labels()

    if len(sys.argv) > 1:
        user_id = _resolve_user_filter(sys.argv[1], labels)
        if user_id is None:
            return
        rows = [r for r in rows if r.get("user_id") == user_id]
        print(f"Filtrert til bruker: {labels.get(user_id, user_id)}\n")
        if not rows:
            print("Ingen forsøk registrert for denne brukeren ennå.")
            return
    elif labels and any(r.get("user_id") for r in rows):
        # Ingen filter valgt, men vi HAR multi-bruker-data - vis en rask
        # oversikt over hvem som genererer hvor mange forsøk, til hjelp ved
        # feilsøking («hvem bør jeg spørre om denne banen?»).
        per_user = defaultdict(int)
        for r in rows:
            uid = r.get("user_id")
            per_user[labels.get(uid, "(enkelt-bruker/ukjent)") if uid else "(enkelt-bruker/ukjent)"] += 1
        print("👥 Forsøk per bruker:")
        for label, n in sorted(per_user.items(), key=lambda x: -x[1]):
            print(f"    {n:3d}×  {label}")
        print()

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
