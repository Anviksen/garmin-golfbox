#!/usr/bin/env python3
"""Raske enhetstester for den RENE logikken – ingen nettleser, ingen nettverk.

Kjør:  python3 tests/test_logic.py
Dekker navne-normalisering, farge-matching, hull-antall, dato/tid-omregning,
GolfBox-feiltekst og bane-scoring. Fanger regresjoner på sekunder.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import golfbox_post as gp  # noqa: E402
import foreign_course_registry as fcr  # noqa: E402
from backend.main import parse_hole_handicaps  # noqa: E402

_passed = 0
_failed = 0


def check(name, got, want):
    global _passed, _failed
    if got == want:
        _passed += 1
    else:
        _failed += 1
        print(f"  ✗ {name}\n      fikk:  {got!r}\n      ville: {want!r}")


def check_true(name, cond):
    check(name, bool(cond), True)


# --- Navne-normalisering (æ/ø/å-folding, aa→a) ---
def test_norm():
    check("core Østmork==Ostmork", gp.core("Østmork"), gp.core("Ostmork"))
    check("core Grønmo==Gronmo", gp.core("Grønmo"), gp.core("Gronmo"))
    check("core Bærum folder ae", gp.core("Bærum"), "baerum")
    check("norm dropper ikke-alfanum", gp.norm("Haga ~ Red/Blue"), "hagaredblue")
    check_true("core fjerner golfklubb", "klubb" not in gp.core("Losby Golfklubb"))


# --- Farge-multisett (samme løkke to ganger + vanlige kombos) ---
def test_colors():
    check("Red/Red -> multiset", gp._color_multiset("Haga ~ Red/Red"), ("rød", "rød"))
    check("Blue/Red -> multiset", gp._color_multiset("Haga ~ Blue/Red"), ("blå", "rød"))
    check("RØD+RØD == Red/Red", gp._color_multiset("Haga RØD+RØD"),
          gp._color_multiset("Haga ~ Red/Red"))
    check("BLÅ+RØD == Blue/Red", gp._color_multiset("Haga BLÅ+RØD"),
          gp._color_multiset("Blue/Red"))
    check("ingen farge -> tom", gp._color_multiset("Oslo Golfklubb"), ())


# --- Hull-antall fra scorede hull ---
def _rnd(scored_numbers, total=18):
    holes = [{"number": i + 1, "strokes": (4 if (i + 1) in scored_numbers else None)}
             for i in range(total)]
    return {"holes": holes}


def test_n_holes():
    check("18 scoret -> 18", gp._round_n_holes(_rnd(range(1, 19))), 18)
    check("17 scoret -> 18", gp._round_n_holes(_rnd(range(1, 18))), 18)
    check("10 scoret -> 18", gp._round_n_holes(_rnd(range(1, 11))), 18)
    check("9 scoret -> 9", gp._round_n_holes(_rnd(range(1, 10))), 9)
    check("back-nine 9 scoret -> 9", gp._round_n_holes(_rnd(range(10, 19))), 9)
    check("5 scoret -> 9", gp._round_n_holes(_rnd([1, 2, 3, 4, 5])), 9)


# --- Dato/tid i norsk tid ---
def test_datetime():
    check("UTC->norsk dato", gp.iso_to_ddmmyyyy("2026-07-16T10:04:41.000Z"), "16.07.2026")
    check("UTC->norsk tid (sommer +2)", gp.iso_to_hhmm("2026-07-16T10:04:41.000Z"), "12:04")
    check("vinter +1", gp.iso_to_hhmm("2026-01-15T10:00:00.000Z"), "11:00")
    check("None dato", gp.iso_to_ddmmyyyy(None), None)


# --- GolfBox-feiltekst oversettes ---
def test_gb_error():
    t = gp._friendly_golfbox_error("returnmsg:strokes_contains_too_many_not_played_holes_between_played_holes")
    check_true("gappy-feil oversatt", "hull-mønsteret" in t)
    check("ukjent tekst beholdes", gp._friendly_golfbox_error("Noe helt annet"), "Noe helt annet")


# --- Bane-scoring: rett løkke vinner ---
def test_course_scoring():
    gcore = gp.core("Losby Golfklubb ~ Vestmork")
    club = gp.core("Losby")
    vest = gp._score_course_name("Vestmork", 9, club, gcore)
    ost = gp._score_course_name("Østmork", 9, club, gcore)
    check_true("Vestmork scorer høyere enn Østmork", vest > ost)
    short = gp._score_course_name("Vestmork Korthullsbane", 9, club, gcore)
    check_true("korthullsbane straffes", short < vest)


def test_holes_decision():
    h = lambda nums: _rnd(nums)["holes"]
    check_true("1-13 sammenhengende", gp._holes_contiguous(h(range(1, 14))))
    check_true("full 18 sammenhengende", gp._holes_contiguous(h(range(1, 19))))
    check("gappy 1+10-18 ikke sammenh", gp._holes_contiguous(h([1] + list(range(10, 19)))), False)
    check("back-nine ikke sammenh fra 1", gp._holes_contiguous(h(range(10, 19))), False)
    check_true("10/18 postbar", gp._holes_postable(10, 18))
    check_true("18/18 postbar", gp._holes_postable(18, 18))
    check("9/18 ikke postbar", gp._holes_postable(9, 18), False)
    check_true("9/9 postbar", gp._holes_postable(9, 9))


# --- Utenlandske baner: landdeteksjon (se UTENLANDSKE_BANER_PLAN.md) ---
def test_foreign_detection():
    check("Spania -> utenlandsk", gp._is_foreign_round({"country": "Spain"}), True)
    check("Norge -> norsk", gp._is_foreign_round({"country": "Norway"}), False)
    check("norge (små bokstaver) -> norsk", gp._is_foreign_round({"country": "norway"}), False)
    check("mangler country -> norsk (bakoverkompatibelt)", gp._is_foreign_round({}), False)
    check("tom country -> norsk", gp._is_foreign_round({"country": ""}), False)
    check("None country -> norsk", gp._is_foreign_round({"country": None}), False)
    check("Sverige -> utenlandsk", gp._is_foreign_round({"country": "Sweden"}), True)


# --- Utenlandske baner: stroke index (HCP) per hull, ekte Garmin-data (Santa
# Clara Golf Club Marbella, cachet i data/scorecards/356502765.json) ---
def test_hole_handicaps():
    real = "141812081006040216010503090717111513"
    got = parse_hole_handicaps(real)
    check("18 hull dekodet", len(got), 18)
    check("er en permutasjon av 1-18", sorted(got), list(range(1, 19)))
    check("hull 1 = stroke index 14", got[0], 14)
    check("hull 10 = stroke index 1 (vanskeligst)", got[9], 1)
    check("None -> tom liste", parse_hole_handicaps(None), [])
    check("tom streng -> tom liste", parse_hole_handicaps(""), [])
    check("odde lengde -> tom liste (korrupt data, ikke gjett)", parse_hole_handicaps("123"), [])


# --- Utenlandske baner: automatiske sunnhetssjekker (se "Live-test funn 2/3"
# i UTENLANDSKE_BANER_PLAN.md – fanger korrupt/umulig data helt automatisk,
# uten å kjenne fasiten for banen) ---
def test_valid_hcp_set():
    good = [{"hcp": v} for v in [14, 18, 12, 8, 10, 6, 4, 2, 16, 1, 5, 3, 9, 7, 17, 11, 15, 13]]
    check_true("gyldig 1-18-permutasjon godkjennes", gp._valid_hcp_set(good))
    dup = [{"hcp": 1}, {"hcp": 1}, {"hcp": 2}]
    check("duplikat stroke index avvises", gp._valid_hcp_set(dup), False)
    out_of_range = [{"hcp": 0}, {"hcp": 19}]
    check("utenfor 1-18 avvises", gp._valid_hcp_set(out_of_range), False)
    check_true("ingen hcp-data i det hele tatt -> ingenting å sjekke", gp._valid_hcp_set([{"hcp": None}]))
    check_true("tom liste -> ingenting å sjekke", gp._valid_hcp_set([]))


def test_plausible_cr_slope():
    check_true("normal CR/Slope godkjennes (Torreby Gul)", gp._plausible_cr_slope(72, 69.7, 131))
    check("slope under 55 avvises (umulig)", gp._plausible_cr_slope(72, 70, 40), False)
    check("slope over 155 avvises (umulig)", gp._plausible_cr_slope(72, 70, 200), False)
    check("CR langt fra par avvises", gp._plausible_cr_slope(72, 30, 130), False)
    check("ikke-tall avvises", gp._plausible_cr_slope(72, "abc", 130), False)
    check("None avvises", gp._plausible_cr_slope(72, None, None), False)


def test_decode_hole_handicaps():
    check("speiler backend.main sin dekoding",
          gp._decode_hole_handicaps("150507031317090111120414180210160608"),
          parse_hole_handicaps("150507031317090111120414180210160608"))


# --- Delt, verifisert stroke-index-cache (foreign_course_registry.py) ---
def test_foreign_course_registry():
    import tempfile
    from pathlib import Path

    orig_file = fcr.DB_FILE
    with tempfile.TemporaryDirectory() as tmp:
        fcr.DB_FILE = Path(tmp) / "foreign_hcp_db_test.json"
        try:
            check("ukjent bane -> None", fcr.get(999999), None)
            saved = fcr.verify(
                course_global_id=28088, course_name="Torreby Golfklubb", country="Sweden",
                hole_handicaps="150501091707131103180804021612140610",
                verified_against="caddee.se", verified_by="test",
            )
            check_true("verify() returnerer oppføring", saved is not None)
            got = fcr.get(28088)
            check_true("get() finner nylig verifisert bane", got is not None)
            check("holeHandicaps lagret riktig", (got or {}).get("holeHandicaps"),
                  "150501091707131103180804021612140610")
            check("get(str) og get(int) samme resultat", fcr.get("28088"), fcr.get(28088))
            threw = False
            try:
                fcr.verify(1, "x", "y", "ikketall", "z")
            except ValueError:
                threw = True
            check_true("ugyldig hole_handicaps kaster feil (ikke stille feil)", threw)
        finally:
            fcr.DB_FILE = orig_file


def main():
    for fn in [test_norm, test_colors, test_n_holes, test_datetime,
               test_gb_error, test_course_scoring, test_holes_decision,
               test_foreign_detection, test_hole_handicaps, test_valid_hcp_set,
               test_plausible_cr_slope, test_decode_hole_handicaps,
               test_foreign_course_registry]:
        fn()
    print(f"\n{'='*40}\n{_passed} bestått, {_failed} feilet")
    sys.exit(1 if _failed else 0)


if __name__ == "__main__":
    main()
