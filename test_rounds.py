#!/usr/bin/env python3
"""
Regresjons-harness: kjør TØRR-matching (klubb/bane/tee) over rundene dine mot live
GolfBox – uten å lagre noe. Logger inn ÉN gang og looper. Kjør etter hver
kodeendring for å se hele bildet og fange regresjoner.

    python3 test_rounds.py                    # én test per distinkt bane (raskest)
    python3 test_rounds.py --all              # alle runder (også duplikater)
    python3 test_rounds.py 372129446 372259590   # kun spesifikke runde-IDer

Rapport skrives også til data/test_rounds_report.txt.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except Exception:
    pass

import golfbox_post as gp

PROJECT_DIR = Path(__file__).resolve().parent


def _rounds():
    sys.path.insert(0, str(PROJECT_DIR))
    from backend.main import all_normalized
    return all_normalized()


def main() -> None:
    args = sys.argv[1:]
    want_all = "--all" in args
    ids = [int(a) for a in args if a.isdigit()]

    rounds = _rounds()
    if ids:
        rounds = [r for r in rounds if r.get("id") in ids]
    elif not want_all:
        seen, uniq = set(), []
        for r in rounds:
            key = (r.get("course") or "").strip().lower()
            if key and key not in seen:
                seen.add(key)
                uniq.append(r)
        rounds = uniq

    gb_user, gb_pass = os.getenv("GOLFBOX_USERNAME"), os.getenv("GOLFBOX_PASSWORD")
    headless = os.getenv("GOLFBOX_HEADLESS") == "1"
    print(f"Tester {len(rounds)} runder mot live GolfBox ...\n")

    rows = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx_args = {"viewport": {"width": 1400, "height": 950}}
        if gp.STATE_FILE.exists():
            ctx_args["storage_state"] = str(gp.STATE_FILE)
        ctx = browser.new_context(**ctx_args)

        print("Logger inn / åpner score-skjema ...")
        fr = gp.open_score_form(ctx, gb_user, gb_pass)
        if not fr:
            print("❌ Klarte ikke åpne score-skjemaet (økt utløpt / innlogging feilet).")
            browser.close()
            return
        try:
            ctx.storage_state(path=str(gp.STATE_FILE))
        except Exception:
            pass

        for i, rnd in enumerate(rounds, 1):
            name = (rnd.get("course") or "?")
            frm = fr if i == 1 else gp.reopen_score_form(ctx)
            if not frm:
                rows.append([rnd.get("id"), name, "?", "?", "?", "skjema tapt"])
                print(f"[{i}/{len(rounds)}] {name[:36]:36}  – skjema tapt")
                continue
            try:
                notes, status = gp.fill_score_form(frm, rnd, for_test=True)
            except Exception as e:
                rows.append([rnd.get("id"), name, "?", "?", "?", f"feil: {e}"])
                print(f"[{i}/{len(rounds)}] {name[:36]:36}  – feil: {e}")
                continue
            c = "✓" if status["club"] else "✗"
            b = "✓" if status["course"] else "✗"
            t = ("⚠" if status.get("tee_uncertain") else "✓") if status["tee"] else "✗"
            posts = status["club"] and status["course"] and status["tee"]
            reason = "" if posts else \
                next((n.strip() for n in reversed(notes) if "❗" in n or "⚠️" in n), "")
            if posts and status.get("tee_uncertain"):
                reason = next((n.strip() for n in reversed(notes) if "DOBBELTSJEKK" in n), "")
            rows.append([rnd.get("id"), name, c, b, t, reason])
            print(f"[{i}/{len(rounds)}] {name[:36]:36}  klubb {c}  bane {b}  tee {t}"
                  + (f"   → {reason[:90]}" if reason else ""))
        browser.close()

    posts = sum(1 for r in rows if r[2] == "✓" and r[3] == "✓" and r[4] in ("✓", "⚠"))
    solid = sum(1 for r in rows if r[2] == r[3] == r[4] == "✓")
    besteffort = sum(1 for r in rows if r[4] == "⚠")
    print(f"\n===== {posts}/{len(rows)} vil POSTES (klubb+bane+tee)  ·  "
          f"{solid} sikre, {besteffort} best-effort-tee (⚠ dobbeltsjekk) =====")
    stuck = [r for r in rows if not (r[2] == "✓" and r[3] == "✓" and r[4] in ("✓", "⚠"))]
    if stuck:
        print("Gjenstår:")
        for r in stuck:
            print(f"  • {r[1][:38]:38} (klubb {r[2]} bane {r[3]} tee {r[4]}) {r[5][:80]}")

    out = PROJECT_DIR / "data" / "test_rounds_report.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{r[0]}\t{r[2]}{r[3]}{r[4]}\t{r[1]}\t{r[5]}" for r in rows]
    out.write_text(
        f"Regresjons-rapport ({posts}/{len(rows)} vil postes · {solid} sikre · "
        f"{besteffort} best-effort)\n\n" + "\n".join(lines),
        encoding="utf-8",
    )
    print(f"\nRapport lagret: {out}")


if __name__ == "__main__":
    main()
