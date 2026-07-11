#!/usr/bin/env python3
"""
Rask sjekk av dataen du hentet med fetch_garmin.py.
Skriver ut en lesbar oppsummering av rundene og et hull-for-hull-eksempel,
slik at du kan bekrefte at Approach S50-dataen kom korrekt gjennom.

Kjøres slik:
    python3 inspect_data.py
"""

import json
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data" / "all_rounds.json"


def num(*values):
    """Returner første verdi som ikke er None."""
    for v in values:
        if v is not None:
            return v
    return "?"


def main() -> None:
    if not DATA.exists():
        print(f"Fant ikke {DATA}. Kjør 'python3 fetch_garmin.py' først.")
        return

    payload = json.loads(DATA.read_text(encoding="utf-8"))
    runder = payload.get("runder", [])
    print(f"📦 {payload.get('antall_runder', len(runder))} runder hentet "
          f"{payload.get('hentet', '')}\n")

    for r in runder:
        s = r.get("summary", {}) or {}
        course = num(s.get("courseName"), s.get("golfCourseName"), "Ukjent bane")
        when = num(s.get("startTime"), s.get("date"))
        score = num(s.get("scorecardTotalScore"), s.get("totalScore"), s.get("strokes"))
        print(f"• {when}  —  {course}  —  total: {score}")

    # Vis hull-for-hull for den første runden som har detaljer
    print("\n— Hull-for-hull eksempel (første runde med detaljer) —")
    for r in runder:
        detail = r.get("detail")
        if not detail:
            continue
        print(json.dumps(detail, ensure_ascii=False, indent=2)[:3000])
        print("\n(Vist forkortet – full data ligger i data/scorecards/)")
        break
    else:
        print("Ingen detaljert hull-data funnet.")


if __name__ == "__main__":
    main()
