#!/usr/bin/env python3
"""
Fase 2 – Golf-dashboard backend (FastAPI).

Leser dataen som fetch_garmin.py har lagret i ../data, normaliserer den til et
ryddig format, og serverer den som et JSON-API. Serverer også frontend-siden.

Endepunkter:
    GET  /api/rounds            -> liste over alle runder (sortert nyeste først)
    GET  /api/rounds/{id}       -> full hull-for-hull scorecard for én runde
    GET  /api/stats             -> aggregert statistikk / trender over tid
    POST /api/sync              -> kjører fetch_garmin.py for å hente nye runder
    GET  /                      -> selve dashboardet (frontend)

Start slik (se README.md):
    uvicorn backend.main:app --reload --port 8000
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# --- Stier ------------------------------------------------------------------
PROJECT_DIR = Path(__file__).resolve().parent.parent
# GOLFBOX_DATA_DIR lar en multi-bruker-kjøring isolere hver brukers rundedata i
# egen mappe (samme mønster som fetch_garmin.py og golfbox_post.py) - uten
# dette leser get_round() i golfbox_post.py (via all_normalized() under) alltid
# fra det DELTE data/-repoet i stedet for den midlertidige per-bruker-mappa
# fetch_garmin.py faktisk skrev til. Default uendret for enkelt-bruker-drift.
DATA_DIR = Path(os.getenv("GOLFBOX_DATA_DIR", str(PROJECT_DIR / "data")))
ALL_ROUNDS = DATA_DIR / "all_rounds.json"
EXCLUDED_FILE = DATA_DIR / "excluded.json"
FRONTEND_DIR = PROJECT_DIR / "frontend"
FETCH_SCRIPT = PROJECT_DIR / "fetch_garmin.py"

app = FastAPI(title="Garmin Golf Dashboard")

# Håndtak til den pågående Golfbox-kjøringen (kun én om gangen).
_golfbox_proc = None


# --- Hjelpefunksjoner -------------------------------------------------------
def load_rounds() -> list[dict]:
    """Les inn all_rounds.json. Returnerer tom liste hvis fila ikke finnes ennå."""
    if not ALL_ROUNDS.exists():
        return []
    with ALL_ROUNDS.open(encoding="utf-8") as f:
        payload = json.load(f)
    return payload.get("runder", [])


def parse_pars(hole_pars: str | None) -> list[int]:
    """Gjør om par-strengen "535344..." til en liste [5,3,5,3,4,4,...].

    Garmin bruker ETT siffer per hull for par (3/4/5), i motsetning til
    handicap-strengen som bruker to sifre per hull."""
    if not hole_pars:
        return []
    return [int(c) for c in hole_pars if c.isdigit()]


def parse_hole_handicaps(hcp_str: str | None) -> list[int]:
    """Gjør om handicap-strengen "141812081006..." til en liste [14,18,12,8,10,6,...].

    Dette er hullets vanskelighetsgrad/stroke index (1=vanskeligst), IKKE
    spillerens handicap. Garmin/GolfBox bruker TO sifre per hull her (i
    motsetning til par-strengen over som bruker ett siffer per hull) – f.eks.
    "08" for hull med stroke index 8. Brukes for utenlandske runder, der
    GolfBox sitt frittekst-skjema krever stroke index per hull manuelt
    (norske baner har dette allerede lagret i GolfBox sin egen banedatabase)."""
    if not hcp_str or len(hcp_str) % 2:
        return []
    try:
        return [int(hcp_str[i:i + 2]) for i in range(0, len(hcp_str), 2)]
    except ValueError:
        return []


def get_detail_scorecard(detail) -> dict | None:
    """Grav ut selve scorecard-objektet fra detalj-strukturen."""
    if not isinstance(detail, dict):
        return None
    details = detail.get("scorecardDetails")
    if isinstance(details, list) and details:
        return details[0]
    return None


def normalize_round(entry: dict) -> dict:
    """Slå sammen summary + detail til ett ryddig runde-objekt for frontend."""
    summary = entry.get("summary", {}) or {}
    detail = entry.get("detail")
    sc_detail = get_detail_scorecard(detail)

    scorecard = (sc_detail or {}).get("scorecard", {}) if sc_detail else {}
    stats_round = ((sc_detail or {}).get("scorecardStats", {}) or {}).get("round", {}) if sc_detail else {}

    # Par per hull – helst fra detaljert banedata, ellers fra summary.
    hole_pars = summary.get("holePars")
    course_name = summary.get("courseName") or scorecard.get("courseName")
    course_id = scorecard.get("courseGlobalId")
    lat = lon = None
    longest_m = sc_detail.get("longestShotInMeters") if sc_detail else None
    # Land + stroke index (HCP) per hull – kun tilgjengelig via courseSnapshots
    # (ikke summary). Brukes for baner utenfor Norge (se UTENLANDSKE_BANER_PLAN.md):
    # `country` avgjør norsk/utenlandsk flyt, `hole_handicaps` fylles inn manuelt
    # i GolfBox sitt frittekst-skjema for utenlandske runder (norske baner har
    # dette allerede lagret i GolfBox sin egen banedatabase, så det trengs ikke der).
    country = None
    round_par = None
    hole_handicaps: list[int] = []
    if sc_detail:
        snaps = detail.get("courseSnapshots") if isinstance(detail, dict) else None
        if isinstance(snaps, list) and snaps:
            snap = snaps[0]
            hole_pars = snap.get("holePars", hole_pars)
            course_name = snap.get("name", course_name)
            course_id = snap.get("courseGlobalId", course_id)
            country = snap.get("country")
            round_par = snap.get("roundPar")
            # Garmin lagrer koordinater som heltall i mikrograder (÷ 1 000 000).
            if snap.get("lat") is not None:
                lat = snap["lat"] / 1_000_000
            if snap.get("lon") is not None:
                lon = snap["lon"] / 1_000_000
            # holeHandicaps ligger PER TEE (kan variere litt tee til tee), så match
            # på samme tee-navn som scorecard.teeBox. Fallback: første tee i lista
            # (bedre enn ingenting – flagges uansett for manuell dobbeltsjekk der
            # dette brukes, se golfbox_post.py sin utenlandsk-gren).
            tee_name = (scorecard.get("teeBox") or "").strip().lower()
            tees = snap.get("tees") or []
            tee_match = next(
                (t for t in tees if (t.get("name") or "").strip().lower() == tee_name),
                None,
            ) or (tees[0] if tees else None)
            if tee_match:
                hole_handicaps = parse_hole_handicaps(tee_match.get("holeHandicaps"))
    pars = parse_pars(hole_pars)

    # Fairway-utfall per hull fra detaljene.
    fairway_by_hole = {}
    for h in scorecard.get("holes", []) or []:
        fairway_by_hole[h.get("number")] = h.get("fairwayShotOutcome")

    # Bygg hull-lista.
    holes = []
    for h in summary.get("holes", []) or []:
        num = h.get("number")
        strokes = h.get("strokes")
        par = pars[num - 1] if num and num <= len(pars) else None
        hcp = hole_handicaps[num - 1] if num and num <= len(hole_handicaps) else None
        to_par = (strokes - par) if (strokes is not None and par) else None
        holes.append(
            {
                "number": num,
                "par": par,
                "hcp": hcp,
                "strokes": strokes,
                "toPar": to_par,
                "fairway": fairway_by_hole.get(num),
            }
        )

    total_par = sum(p for p in pars if p) or None
    strokes = summary.get("strokes")
    to_par = (strokes - total_par) if (strokes is not None and total_par) else None

    fairways_recorded = stats_round.get("fairwaysRecorded", 0) or 0
    fairways_hit = stats_round.get("fairwaysHit", 0) or 0
    fairways_left = stats_round.get("fairwaysLeft", 0) or 0
    fairways_right = stats_round.get("fairwaysRight", 0) or 0
    fairway_pct = round(100 * fairways_hit / fairways_recorded) if fairways_recorded else None

    # Scoring-miks (eagle+ / birdie / par / bogey / dobbel+).
    scoring = {
        "eagle": (stats_round.get("holesEagle", 0) or 0)
        + (stats_round.get("holesDoubleEagleOrUnder", 0) or 0),
        "birdie": stats_round.get("holesBirdie", 0) or 0,
        "par": stats_round.get("holesPar", 0) or 0,
        "bogey": stats_round.get("holesBogey", 0) or 0,
        "double": stats_round.get("holesOverBogey", 0) or 0,
    }

    return {
        "id": summary.get("id"),
        "course": course_name or "Ukjent bane",
        "courseId": course_id,
        "country": country,
        "roundPar": round_par or total_par,
        "lat": lat,
        "lon": lon,
        "date": summary.get("startTime"),
        "roundInProgress": bool(summary.get("roundInProgress")),
        "holesCompleted": summary.get("holesCompleted"),
        "strokes": strokes,
        "par": total_par,
        "toPar": to_par,
        "handicappedStrokes": summary.get("handicappedStrokes"),
        "scoreWithHandicap": summary.get("scoreWithHandicap"),
        "playerHandicap": scorecard.get("playerHandicap"),
        "teeBox": scorecard.get("teeBox"),
        "teeBoxRating": scorecard.get("teeBoxRating"),
        "teeBoxSlope": scorecard.get("teeBoxSlope"),
        "fairwaysHit": fairways_hit,
        "fairwaysLeft": fairways_left,
        "fairwaysRight": fairways_right,
        "fairwaysRecorded": fairways_recorded,
        "fairwayPct": fairway_pct,
        "longestDriveM": longest_m,
        "scoring": scoring,
        "holes": holes,
    }


def load_excluded() -> set:
    """Sett med runde-ID-er brukeren har valgt å skjule (f.eks. scramble)."""
    if EXCLUDED_FILE.exists():
        try:
            return set(json.loads(EXCLUDED_FILE.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()


def save_excluded(ids: set) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    EXCLUDED_FILE.write_text(json.dumps(sorted(ids)), encoding="utf-8")


def all_normalized() -> list[dict]:
    """Alle runder (nyeste først), hver merket med om den er ekskludert."""
    excluded = load_excluded()
    rounds = [normalize_round(r) for r in load_rounds()]
    for r in rounds:
        r["excluded"] = r.get("id") in excluded
    rounds.sort(key=lambda r: r.get("date") or "", reverse=True)
    return rounds


def active_rounds() -> list[dict]:
    """Kun runder som teller (ekskluderte er filtrert bort)."""
    return [r for r in all_normalized() if not r.get("excluded")]


# --- Handicap (estimert WHS-indeks) ----------------------------------------
def score_differential(r: dict) -> float | None:
    """WHS score-differanse for én 18-hulls runde: (113/slope) * (score - rating)."""
    slope = r.get("teeBoxSlope")
    rating = r.get("teeBoxRating")
    strokes = r.get("strokes")
    if not slope or rating is None or strokes is None:
        return None
    if (r.get("holesCompleted") or 0) < 18:
        return None
    return round((113 / slope) * (strokes - rating), 1)


# Offisiell WHS-tabell: antall differanser -> (antall beste som brukes, justering).
_WHS_TABLE = {
    3: (1, 2.0), 4: (1, 1.0), 5: (1, 0.0), 6: (2, 1.0), 7: (2, 0.0), 8: (2, 0.0),
    9: (3, 0.0), 10: (3, 0.0), 11: (3, 0.0), 12: (4, 0.0), 13: (4, 0.0), 14: (4, 0.0),
    15: (5, 0.0), 16: (5, 0.0), 17: (6, 0.0), 18: (6, 0.0), 19: (7, 0.0), 20: (8, 0.0),
}


def whs_index(diffs: list[float]) -> float | None:
    """Estimert handicap-indeks fra en liste differanser (eldst -> nyest)."""
    window = diffs[-20:]
    n = len(window)
    if n < 3:
        return None
    count, adjustment = _WHS_TABLE[min(n, 20)]
    lowest = sorted(window)[:count]
    return round(sum(lowest) / len(lowest) - adjustment, 1)


# --- API --------------------------------------------------------------------
@app.get("/api/rounds")
def api_rounds():
    """Lettvekts-liste (uten hull-detaljer) til oversikten."""
    rounds = all_normalized()
    summary = [{k: v for k, v in r.items() if k != "holes"} for r in rounds]
    return {"count": len(summary), "rounds": summary}


@app.get("/api/rounds/{round_id}")
def api_round(round_id: int):
    for r in all_normalized():
        if r.get("id") == round_id:
            return r
    raise HTTPException(status_code=404, detail="Runde ikke funnet")


@app.get("/api/stats")
def api_stats():
    """Aggregert statistikk og trender (eldst -> nyest for grafer)."""
    rounds = active_rounds()
    played = [r for r in rounds if r.get("toPar") is not None]

    # 18-hulls runder til trend (så tallene er sammenlignbare).
    full = [r for r in played if (r.get("holesCompleted") or 0) >= 18]
    trend = list(reversed(full))  # eldst først

    def avg(values):
        vals = [v for v in values if v is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    return {
        "totalRounds": len(rounds),
        "roundsPlayed": len(played),
        "bestToPar": min((r["toPar"] for r in full), default=None),
        "avgToPar18": avg([r["toPar"] for r in full]),
        "avgFairwayPct": avg([r["fairwayPct"] for r in played]),
        "trend": [
            {
                "id": r["id"],
                "date": r["date"],
                "course": r["course"],
                "toPar": r["toPar"],
                "strokes": r["strokes"],
                "fairwayPct": r["fairwayPct"],
            }
            for r in trend
        ],
    }


@app.post("/api/rounds/{round_id}/exclude")
def exclude_round(round_id: int):
    """Skjul en runde fra statistikk (f.eks. scramble)."""
    ex = load_excluded()
    ex.add(round_id)
    save_excluded(ex)
    return {"ok": True, "excluded": sorted(ex)}


@app.post("/api/rounds/{round_id}/include")
def include_round(round_id: int):
    """Ta en tidligere skjult runde tilbake i statistikken."""
    ex = load_excluded()
    ex.discard(round_id)
    save_excluded(ex)
    return {"ok": True, "excluded": sorted(ex)}


@app.get("/api/handicap")
def api_handicap():
    """Estimert WHS handicap-indeks og utvikling over tid.

    Beregnes fra 18-hulls runder (score, rating, slope). Merk: dette er et
    ESTIMAT – offisiell handicap ligger i Golfbox. Justert bruttoscore (net
    double bogey) og PCC er ikke med, så tallet kan avvike litt."""
    # Kronologisk (eldst -> nyest), kun runder med gyldig differanse.
    chrono = list(reversed(active_rounds()))
    diffs: list[float] = []
    trend = []
    for r in chrono:
        d = score_differential(r)
        if d is None:
            continue
        diffs.append(d)
        trend.append(
            {
                "date": r["date"],
                "course": r["course"],
                "differential": d,
                "index": whs_index(diffs),
            }
        )
    current = trend[-1]["index"] if trend else None
    best_diff = min(diffs) if diffs else None
    return {
        "currentIndex": current,
        "roundsUsed": len(diffs),
        "bestDifferential": best_diff,
        "trend": trend,
    }


@app.get("/api/insights")
def api_insights():
    """Aggregert innsikt: kart, hull-heatmap, scoring-DNA og fairway-dispersjon."""
    rounds = active_rounds()

    # --- 1) Kart: én markør per bane ---------------------------------------
    courses: dict = {}
    for r in rounds:
        key = r.get("courseId") or r.get("course")
        c = courses.setdefault(
            key,
            {
                "course": r["course"],
                "lat": r.get("lat"),
                "lon": r.get("lon"),
                "rounds": 0,
                "toPars": [],
            },
        )
        c["rounds"] += 1
        if c["lat"] is None and r.get("lat") is not None:
            c["lat"], c["lon"] = r["lat"], r["lon"]
        if r.get("toPar") is not None:
            c["toPars"].append(r["toPar"])

    map_points = []
    for c in courses.values():
        if c["lat"] is None or c["lon"] is None:
            continue
        map_points.append(
            {
                "course": c["course"],
                "lat": c["lat"],
                "lon": c["lon"],
                "rounds": c["rounds"],
                "bestToPar": min(c["toPars"]) if c["toPars"] else None,
                "avgToPar": round(sum(c["toPars"]) / len(c["toPars"]), 1) if c["toPars"] else None,
            }
        )

    # --- 2) Hull-heatmap: baner spilt >= 2 ganger --------------------------
    by_course: dict = {}
    for r in rounds:
        key = r.get("courseId") or r.get("course")
        by_course.setdefault(key, {"course": r["course"], "rounds": []})["rounds"].append(r)

    heatmaps = []
    for grp in by_course.values():
        rs = [x for x in grp["rounds"] if (x.get("holesCompleted") or 0) >= 18]
        if len(rs) < 2:
            continue
        holes = []
        for n in range(1, 19):
            strokes_list, pars = [], []
            for x in rs:
                h = next((hh for hh in x["holes"] if hh["number"] == n), None)
                if h and h.get("strokes") is not None:
                    strokes_list.append(h["strokes"])
                    if h.get("par"):
                        pars.append(h["par"])
            if strokes_list:
                par = round(sum(pars) / len(pars)) if pars else None
                avg = sum(strokes_list) / len(strokes_list)
                holes.append(
                    {
                        "number": n,
                        "par": par,
                        "avgStrokes": round(avg, 2),
                        "avgToPar": round(avg - par, 2) if par else None,
                    }
                )
        heatmaps.append({"course": grp["course"], "roundsCount": len(rs), "holes": holes})
    heatmaps.sort(key=lambda h: h["roundsCount"], reverse=True)

    # --- 3) Scoring-DNA: totalsum av hull-typer ----------------------------
    total_scoring = {"eagle": 0, "birdie": 0, "par": 0, "bogey": 0, "double": 0}
    for r in rounds:
        for k in total_scoring:
            total_scoring[k] += r.get("scoring", {}).get(k, 0)

    # --- 4) Fairway-dispersjon: venstre / truffet / høyre ------------------
    disp = {"left": 0, "hit": 0, "right": 0, "recorded": 0}
    for r in rounds:
        disp["left"] += r.get("fairwaysLeft", 0)
        disp["hit"] += r.get("fairwaysHit", 0)
        disp["right"] += r.get("fairwaysRight", 0)
        disp["recorded"] += r.get("fairwaysRecorded", 0)

    return {
        "map": map_points,
        "heatmaps": heatmaps,
        "scoring": total_scoring,
        "dispersion": disp,
    }


@app.post("/api/golfbox/{round_id}")
def golfbox_post(round_id: int):
    """Åpne Golfbox i nettleseren og fyll inn scoren fra en runde.

    Starter golfbox_post.py i bakgrunnen – en ekte nettleser åpnes på skrivebordet,
    fyller ut skjemaet, og lar deg sjekke + lagre selv. Endepunktet returnerer med
    en gang."""
    script = PROJECT_DIR / "golfbox_post.py"
    if not script.exists():
        raise HTTPException(status_code=500, detail="Fant ikke golfbox_post.py")
    # Bare én Golfbox-kjøring om gangen (flere samtidig kræsjer nettleseren).
    global _golfbox_proc
    if _golfbox_proc is not None and _golfbox_proc.poll() is None:
        return {
            "ok": False,
            "message": "En Golfbox-kjøring pågår allerede. Lukk nettleservinduet og vent "
            "til den er ferdig før du starter en ny runde.",
        }
    _golfbox_proc = subprocess.Popen(
        [sys.executable, str(script), str(round_id)], cwd=str(PROJECT_DIR)
    )
    return {
        "ok": True,
        "message": (
            "Golfbox åpnes i nettleseren (kan ta noen sekunder). Den fyller ut alt – sjekk "
            "bane/tee/markør og trykk «Lagre» selv. Ta én runde av gangen."
        ),
    }


@app.post("/api/sync")
def api_sync():
    """Kjør fetch_garmin.py for å hente nye runder fra Garmin Connect."""
    if not FETCH_SCRIPT.exists():
        raise HTTPException(status_code=500, detail="Fant ikke fetch_garmin.py")
    try:
        result = subprocess.run(
            [sys.executable, str(FETCH_SCRIPT)],
            cwd=str(PROJECT_DIR),
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Synk tok for lang tid (timeout).")

    output = (result.stdout or "") + (result.stderr or "")
    tail = "\n".join(output.strip().splitlines()[-25:])
    return JSONResponse(
        {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "output": tail,
        }
    )


# --- Frontend ---------------------------------------------------------------
@app.get("/")
def index():
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        return JSONResponse({"detail": "Frontend mangler."}, status_code=404)
    return FileResponse(index_file)


# Server øvrige statiske filer (om vi legger til flere senere).
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
