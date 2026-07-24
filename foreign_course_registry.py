#!/usr/bin/env python3
"""
Delt, verifisert stroke-index-database for UTENLANDSKE baner.

Samme mønster som course_matcher.py sin lærte klubb/bane/tee-base, bare for et
annet felt: stroke index (Hcp) per hull for baner utenfor Norge. Se
UTENLANDSKE_BANER_PLAN.md («Live-test funn 2») for hvorfor dette trengs – Garmin
sitt eget Hcp-felt kan i sjeldne tilfeller vise en annen rekkefølge enn banens
faktiske/nåværende kort (f.eks. etter en baneombygging), og siden GolfBox sitt
utenlandsskjema ikke har noen egen fasit å sjekke mot, er det den ENESTE
kilden vi poster fra.

Løsningen er identisk i ånd med den delte klubb/bane/tee-basen: FØRSTE gang et
menneske bekrefter riktig stroke-index-rekkefølge for en bane (mot en
troverdig ekstern kilde, f.eks. et nasjonalt forbund-koblet system), lagres
det her – lokalt (git-delt) og i den delte sentralbasen (nettverkseffekt,
se SENTRALISERING.md). Deretter er banen «kjent god» for ALLE fremtidige
runder på den banen, for alle brukere, helt automatisk – ingen manuelt
oppslag trengs igjen for den banen.

Nøkkel: Garmins courseGlobalId (stabilt per bane, følger med runde-data).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
DB_FILE = PROJECT_DIR / "foreign_hcp_db.json"


def load_db() -> dict:
    """Alle bekreftede baner: {str(courseGlobalId): {holeHandicaps, courseName,
    country, verifiedAgainst, verifiedBy, verifiedAt}}."""
    if not DB_FILE.exists():
        return {}
    try:
        data = json.loads(DB_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_db(db: dict) -> None:
    DB_FILE.write_text(
        json.dumps(db, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )


def get(course_global_id) -> dict | None:
    """Bekreftet oppføring for en bane, eller None hvis ikke verifisert ennå."""
    if course_global_id is None:
        return None
    return load_db().get(str(course_global_id))


def verify(course_global_id, course_name: str, country: str, hole_handicaps: str,
           verified_against: str, verified_by: str = "") -> dict | None:
    """Registrer en MENNESKE-bekreftet stroke-index-rekkefølge for en bane.

    hole_handicaps: samme 2-sifre-per-hull-format som Garmin selv bruker
    (f.eks. "150507031317090111120414180210160608"), men bekreftet riktig mot
    `verified_against` (f.eks. "caddee.se", "klubbens offisielle scorekort").
    Lagres lokalt (git-delt) og forsøkes delt til sentralbasen (best effort)."""
    if not course_global_id or not hole_handicaps:
        return None
    if len(hole_handicaps) % 2 or not hole_handicaps.isdigit():
        raise ValueError(
            f"hole_handicaps må være et partall sifre, kun tall (fikk {hole_handicaps!r})"
        )
    entry = {
        "courseName": course_name or "",
        "country": country or "",
        "holeHandicaps": hole_handicaps,
        "verifiedAgainst": verified_against or "",
        "verifiedBy": verified_by or "",
        "verifiedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    db = load_db()
    db[str(course_global_id)] = entry
    _save_db(db)
    _contribute(course_global_id, entry)
    return entry


def _contribute(course_global_id, entry: dict) -> None:
    """Send den bekreftede banen opp til den delte sentralbasen (best effort)."""
    try:
        import central_registry
        central_registry.contribute_foreign_hcp({"course_global_id": course_global_id, **entry})
    except Exception:
        pass


if __name__ == "__main__":
    db = load_db()
    print(f"Bekreftede utenlandske baner (foreign_hcp_db.json): {len(db)}")
    for cid, e in db.items():
        print(f"  {cid}: {e.get('courseName')} ({e.get('country')}) – "
              f"verifisert mot {e.get('verifiedAgainst')!r} {e.get('verifiedAt', '')}")
