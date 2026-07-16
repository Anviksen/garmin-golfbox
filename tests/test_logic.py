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


def main():
    for fn in [test_norm, test_colors, test_n_holes, test_datetime,
               test_gb_error, test_course_scoring]:
        fn()
    print(f"\n{'='*40}\n{_passed} bestått, {_failed} feilet")
    sys.exit(1 if _failed else 0)


if __name__ == "__main__":
    main()
