#!/usr/bin/env python3
"""
Fase 3 – «Send til Golfbox».

Åpner Golfbox i en ekte nettleser, går til «Innlever score», og fyller inn alt vi
har fra en valgt Garmin-runde: dato, rundetype, bane/tee (beste treff), 9/18 hull
og alle hull-scorer. Deretter STOPPER den og lar vinduet stå åpent, slik at du selv
kan sjekke, legge til markør, og trykke «Lagre».

Innlogging: første gang logger du inn manuelt i vinduet som åpnes. Økten lagres i en
egen nettleserprofil (data/golfbox_profile/), så neste gang er du allerede innlogget.

Bruk:
    python3 golfbox_post.py <round_id>

Kalles normalt automatisk av «Send til Golfbox»-knappen i dashboardet.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import course_matcher  # universell koordinat-matcher (samme mappe)

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Mangler Playwright. Kjør: pip install -r requirements.txt && playwright install chromium")
    raise SystemExit(1)

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*a, **k):
        return None

PROJECT_DIR = Path(__file__).resolve().parent
STATE_FILE = PROJECT_DIR / "data" / "golfbox_state.json"
LOG_FILE = PROJECT_DIR / "data" / "golfbox_post.log"
COURSE_MAP_FILE = PROJECT_DIR / "golfbox_course_map.json"


def load_course_map() -> dict:
    """Manuell Garmin-navn -> GolfBox-navn (club/course/tee) for baner der
    auto-matchingen bommer. Nøkler som starter med '_' ignoreres."""
    if not COURSE_MAP_FILE.exists():
        return {}
    try:
        raw = json.loads(COURSE_MAP_FILE.read_text(encoding="utf-8"))
        return {k: v for k, v in raw.items() if not k.startswith("_") and isinstance(v, dict)}
    except Exception:
        return {}
API_BASE = os.getenv("DASHBOARD_URL", "http://127.0.0.1:8000")
SCORE_URL = "https://www.golfbox.no/site/my_golfbox/score/whs/newWHSScore.asp"


def log(msg: str) -> None:
    """Skriv til skjerm OG til data/golfbox_post.log (så knappe-kjøringer kan feilsøkes)."""
    line = f"{datetime.now().strftime('%H:%M:%S')}  {msg}"
    print(line, flush=True)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def get_round(round_id: str) -> dict:
    """Hent normalisert runde-data. Leser rett fra disk via backend-logikken,
    så scriptet virker uansett om dashboard-serveren kjører eller ei."""
    sys.path.insert(0, str(PROJECT_DIR))
    try:
        from backend.main import all_normalized
    except Exception as e:
        raise RuntimeError(f"Klarte ikke laste backend-logikken: {e}")
    rid = int(round_id)
    for r in all_normalized():
        if r.get("id") == rid:
            return r
    raise ValueError(f"Fant ikke runde {round_id} i data/. Har du synket fra Garmin?")


def iso_to_ddmmyyyy(iso: str | None) -> str | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%d.%m.%Y")
    except Exception:
        return None


def _fold(s: str) -> str:
    """Fold norske/nordiske spesialtegn til ASCII. Garmin stripper ofte æ/ø/å
    (f.eks. «Østmork» → «Ostmork»), mens GolfBox beholder dem – så vi folder
    BEGGE likt for at match skal treffe. Generelt for alle baner med æ/ø/å."""
    s = (s or "").lower()
    for a, b in (("æ", "ae"), ("ø", "o"), ("å", "a"),
                 ("ä", "a"), ("ö", "o"), ("ü", "u")):
        s = s.replace(a, b)
    s = s.replace("aa", "a")  # aa == å == a i norsk
    return s


def norm(s: str) -> str:
    return "".join(ch for ch in _fold(s) if ch.isalnum())


_GENERIC = ("golfklubb", "golfpark", "golfclub", "golfsearvi", "golf", "klubb", "club", "gk")


def core(s: str) -> str:
    """Kjernenavn uten generiske golf-ord (for klubb-/bane-match)."""
    s = _fold(s)
    for w in _GENERIC:
        s = s.replace(w, " ")
    return "".join(ch for ch in s if ch.isalnum())


def _options(fr, select_id):
    return fr.eval_on_selector_all(
        f"#{select_id} option",
        "els => els.map(e => ({value: e.value, text: e.textContent.trim()}))",
    )


def best_option_value(fr, select_id: str, target_text: str):
    """Finn value på det <option> som best matcher target_text."""
    options = _options(fr, select_id)
    t, tc = norm(target_text), core(target_text)
    if not t:
        return None
    # 1) eksakt navn
    for o in options:
        if norm(o["text"]) == t:
            return o["value"]
    # 2) eksakt kjernenavn (uten «golfklubb» osv.)
    if tc:
        for o in options:
            if core(o["text"]) and core(o["text"]) == tc:
                return o["value"]
    # 2b) delvis kjernenavn – f.eks. «Oustøen» (GolfBox) i «Oustøen Country Club»
    #     (Garmin). Min. 4 tegn for å unngå tilfeldige småtreff.
    if tc:
        for o in options:
            oc = core(o["text"])
            if oc and len(oc) >= 4 and (oc in tc or tc in oc):
                return o["value"]
    # 3) delvis treff (minst 3 tegn for å unngå tilfeldige småtreff)
    for o in options:
        ot = norm(o["text"])
        if ot and len(ot) >= 3 and (ot in t or t in ot):
            return o["value"]
    return None


def only_real_course(fr, select_id: str):
    """Hvis nedtrekket bare har ett reelt banevalg, returner value-en for det."""
    opts = [o for o in _options(fr, select_id) if o.get("value") and o.get("text", "").strip()]
    return opts[0]["value"] if len(opts) == 1 else None


def _read_golfbox_pars(fr, n: int):
    """Les par per hull (#holePar_1..N) fra score-skjemaet. [4,3,4,...] eller None-er."""
    try:
        return fr.evaluate(
            """(n) => {
                const out = [];
                for (let i = 1; i <= n; i++) {
                    const el = document.getElementById('holePar_' + i);
                    const v = el ? parseInt((el.textContent || '').trim()) : NaN;
                    out.push(isNaN(v) ? null : v);
                }
                return out;
            }""",
            n,
        )
    except Exception:
        return [None] * n


def garmin_par_sequence(rnd: dict, n_holes: int):
    """Bygg par-rekka [hull1, hull2, …] fra Garmin-runden."""
    by_num = {}
    for h in (rnd.get("holes") or []):
        num, par = h.get("number"), h.get("par")
        if num and par:
            by_num[int(num)] = int(par)
    return [by_num.get(i) for i in range(1, n_holes + 1)]


# Baner vi helst IKKE velger automatisk (kort-/spesialbaner) med mindre par matcher entydig.
_SHORT = ("kort", "korthull", "par3", "par 3", "akademi", "academy", "6-hull", "pitch")
_SPECIAL = ("tour", "dame", "herre", "senior", "junior", "vinter", "winter", "matchplay")


def _js_set_select(fr, sel_id: str, value: str) -> bool:
    """Sett verdi på et <select> via JS + fyr changeXxx() (robust, ingen timeout-heng)."""
    try:
        return bool(fr.evaluate(
            """({id, v}) => {
                const el = document.getElementById(id);
                if (!el) return false;
                el.value = v;
                el.dispatchEvent(new Event('change', {bubbles: true}));
                return el.value === v;
            }""",
            {"id": sel_id, "v": value},
        ))
    except Exception:
        return False


def _wait_select_stable(fr, sel_id: str, settle: float = 2.0, timeout: float = 12.0) -> None:
    """Vent til <select> sin valgte verdi har vært uendret i `settle` sek (AJAX ferdig)."""
    end = time.time() + timeout
    prev, since = "\x00", time.time()
    while time.time() < end:
        try:
            cur = fr.eval_on_selector(f"#{sel_id}", "el => el.value") or ""
        except Exception:
            cur = ""
        if cur == prev:
            if time.time() - since >= settle:
                return
        else:
            prev, since = cur, time.time()
        time.sleep(0.4)


def _wait_options_nonempty(fr, sel_id: str, timeout: float = 8.0) -> int:
    """Vent til <select> har minst én reell option (value != ''). GolfBox laster
    tees via async getTeeOptions() – lista er tom et øyeblikk etter banevalg.
    Returnerer antall reelle opsjoner (0 hvis den forblir tom = banen har ingen tees)."""
    end = time.time() + timeout
    n = 0
    while time.time() < end:
        n = len([o for o in _options(fr, sel_id) if o.get("value")])
        if n > 0:
            time.sleep(0.4)  # la den evt. laste ferdig flere
            n2 = len([o for o in _options(fr, sel_id) if o.get("value")])
            if n2 == n:
                return n
            n = n2
        else:
            time.sleep(0.4)
    return n


def _ensure_tees_loaded(fr, timeout: float = 8.0) -> int:
    """Sørg for at tee-lista er fylt. Hvis tom: re-trigg changeCourse() (dispatch
    'change' på fld_Course) for å tvinge en ny getTeeOptions(), og vent igjen.
    Generelt mot GolfBox' async-race der tees noen ganger ikke lastes."""
    n = _wait_options_nonempty(fr, "fld_Tee", timeout=timeout)
    if n > 0:
        return n
    try:  # dytt et nytt change-event på banevalget → GolfBox laster tees på nytt
        fr.eval_on_selector(
            "#fld_Course",
            "el => el.dispatchEvent(new Event('change', {bubbles: true}))")
    except Exception:
        pass
    return _wait_options_nonempty(fr, "fld_Tee", timeout=timeout)


def _pick_course(fr, value: str, text: str, timeout: float = 20.0) -> bool:
    """Velg bane robust: vent til klubbens AJAX er ferdig, velg, og re-assert til
    valget er stabilt (GolfBox nullstiller ellers til standardbanen)."""
    # 1) vent til bane-lista har roet seg etter changeClub sin GetCourses.
    _wait_select_stable(fr, "fld_Course", settle=2.0, timeout=12.0)
    end = time.time() + timeout
    while time.time() < end:
        # Finn value på nytt (ombygging kan gi nye/annen-casing verdier).
        val = value
        for o in _options(fr, "fld_Course"):
            if text and o.get("text", "").strip() == text:
                val = o["value"]
                break
        try:
            fr.select_option("#fld_Course", value=val, timeout=4000)
        except Exception:
            pass
        # Dytt GolfBox sin egen state så en evt. senere ombygging beholder valget.
        try:
            fr.evaluate(
                """() => {
                    try { ClubHasChanged = false; } catch (e) {}
                    const el = document.getElementById('fld_Course');
                    if (el) el.dispatchEvent(new Event('change', {bubbles: true}));
                }"""
            )
        except Exception:
            pass
        time.sleep(2.0)
        try:
            cur = fr.eval_on_selector(
                "#fld_Course", "el => (el.options[el.selectedIndex]||{}).text || ''") or ""
        except Exception:
            cur = ""
        if norm(cur) == norm(text):
            time.sleep(1.5)  # bekreft at det holder
            try:
                cur2 = fr.eval_on_selector(
                    "#fld_Course", "el => (el.options[el.selectedIndex]||{}).text || ''") or ""
            except Exception:
                cur2 = ""
            if norm(cur2) == norm(text):
                return True
    return False


def _pick_option(fr, sel_id: str, value: str, text: str, timeout: float = 15.0) -> bool:
    """Generisk robust valg: vent til nedtrekket er stabilt (async rebuild ferdig),
    velg, og re-assert til valget holder. Brukes for tee (og andre reset-utsatte felt)."""
    _wait_select_stable(fr, sel_id, settle=1.5, timeout=10.0)
    end = time.time() + timeout
    while time.time() < end:
        val = value
        for o in _options(fr, sel_id):
            if text and o.get("text", "").strip() == text:
                val = o["value"]
                break
        try:
            fr.select_option(f"#{sel_id}", value=val, timeout=4000)
        except Exception:
            pass
        try:
            fr.evaluate(
                "(id) => { const el = document.getElementById(id);"
                " if (el) el.dispatchEvent(new Event('change', {bubbles: true})); }",
                sel_id,
            )
        except Exception:
            pass
        time.sleep(1.5)
        try:
            cur = fr.eval_on_selector(
                f"#{sel_id}", "el => (el.options[el.selectedIndex]||{}).text || ''") or ""
        except Exception:
            cur = ""
        if text and norm(cur) == norm(text):
            time.sleep(1.0)
            try:
                cur2 = fr.eval_on_selector(
                    f"#{sel_id}", "el => (el.options[el.selectedIndex]||{}).text || ''") or ""
            except Exception:
                cur2 = ""
            if norm(cur2) == norm(text):
                return True
    return False


def _select_verified(fr, sel_id: str, value: str, tries: int = 5, settle: float = 1.8) -> bool:
    """Velg en <select>-verdi og VERIFISER at den sitter etter at GolfBox sin
    async changeXxx()-omlasting er ferdig. Velg på nytt hvis den ble nullstilt."""
    for _ in range(tries):
        try:
            fr.select_option(f"#{sel_id}", value=value, timeout=5000)
        except Exception:
            pass
        time.sleep(settle)  # vent til changeCourse()/AJAX har kjørt ferdig
        try:
            cur = fr.eval_on_selector(f"#{sel_id}", "el => el.value")
        except Exception:
            cur = None
        if cur == value:
            return True
    return False


def _score_course_name(text: str, n_holes: int, club_core: str, garmin_core: str) -> int:
    """Poengsett en bane KUN på navn/hull – rask, ingen skjema-endring."""
    low = text.lower()
    c = core(text)
    other = "9" if n_holes == 18 else "18"
    score = 0
    if any(w in low for w in _SHORT):
        score -= 800
    if any(w in low for w in _SPECIAL):
        score -= 200
    if str(n_holes) in low:
        score += 30
    if other in low and str(n_holes) not in low:
        score -= 300  # feil hull-antall
    if club_core and club_core in c:
        score += 40
    if garmin_core and (garmin_core in c or c in garmin_core):
        score += 25
    return score


# Farger på norsk + engelsk → normalisert norsk. For fler-løkke-baner som merkes
# med farge-kombinasjoner (Haga «BLÅ+RØD», o.l.).
_COLORS = {
    "rød": "rød", "roed": "rød", "red": "rød",
    "gul": "gul", "yellow": "gul",
    "blå": "blå", "bla": "blå", "blue": "blå",
    "grønn": "grønn", "gronn": "grønn", "green": "grønn",
    "hvit": "hvit", "white": "hvit",
    "svart": "svart", "black": "svart",
    "oransje": "oransje", "orange": "oransje",
}


def _color_set(text: str) -> set:
    """Fargene i et banenavn som et sett (språk-/rekkefølge-uavhengig)."""
    cleaned = "".join(ch if ch.isalpha() else " " for ch in (text or "").lower())
    return {_COLORS[tok] for tok in cleaned.split() if tok in _COLORS}


def choose_course(fr, targets, n_holes: int, garmin_pars=None, club_core: str = "",
                  garmin_course: str = ""):
    """Velg riktig bane innen valgt klubb – UTEN forhåndsspilling.
    Primær: navn/hull-scoring (utelukker kort-/dame-/tour-baner, foretrekker rett
    hull-antall + klubbnavn). Reserve ved tvil: par-sekvens-sjekk (robust JS).
    Returnerer (value, hvordan) eller (None, grunn)."""
    opts = [o for o in _options(fr, "fld_Course") if o.get("value") and o.get("text", "").strip()]
    if not opts:
        return None, "ingen baner"
    if len(opts) == 1:
        return opts[0]["value"], "eneste bane"

    # Farge-sett-match: fler-løkke-klubber der Garmin-navnet har en farge-kombinasjon
    # («Red/Blue») → finn GolfBox-banen med samme farge-SETT («Haga BLÅ+RØD»),
    # uavhengig av språk og rekkefølge. Generelt for alle farge-kombo-klubber.
    gset = _color_set(garmin_course)
    if len(gset) >= 2:
        exact = [o for o in opts if _color_set(o["text"]) == gset]
        if len(exact) == 1:
            return exact[0]["value"], "farge-sett"

    # Eksakt banenavn-treff på løkke-navnet (etter folding) → bruk det direkte. F.eks.
    # Garmin «... ~ Vestmork» mot GolfBox-banen «Vestmork», selv om andre baner med «9»
    # i navnet ellers ville scoret høyere for en 9-hullsrunde. Generelt for alle løkker.
    for _t in targets:
        tc = core(_t)
        if len(tc) >= 4:
            hit = [o for o in opts if core(o["text"]) == tc]
            if len(hit) == 1:
                return hit[0]["value"], "eksakt banenavn"

    gcore = core(garmin_course or "")
    ranked = sorted(
        ((_score_course_name(o["text"], n_holes, club_core, gcore), o) for o in opts),
        key=lambda x: x[0], reverse=True,
    )
    top_score, top_o = ranked[0]
    second = ranked[1][0] if len(ranked) > 1 else -10_000

    # Tydelig vinner på navn/hull → bruk den (rask, ingen probing).
    if top_score > 0 and (top_score - second) >= 40:
        return top_o["value"], "navn/hull"

    # Tvil → par-sekvens-sjekk (robust) på de mest sannsynlige kandidatene.
    # Begrens til topp 6 så en klubb med mange baner (Nordhaug: 69) ikke tar evigheter.
    gp = list(garmin_pars or [])
    if any(p for p in gp):
        best, best_key = None, (-1, -10_000)
        for sc, o in ranked[:6]:
            if sc <= -500:
                continue  # åpenbart kort-/feil bane, hopp over
            try:
                fr.select_option("#fld_Course", value=o["value"], timeout=4000)
            except Exception:
                continue
            _wait_options_nonempty(fr, "fld_Tee", timeout=6.0)
            tees = [t for t in _options(fr, "fld_Tee") if t.get("value")]
            if not tees:
                continue  # bane uten tees er ubrukelig (f.eks. «Narvesen»-placeholder) → hopp
            try:
                fr.select_option("#fld_Tee", value=tees[0]["value"], timeout=4000)
            except Exception:
                pass
            time.sleep(0.5)
            box = _read_golfbox_pars(fr, n_holes)
            if sum(1 for p in box if p) < n_holes:
                continue
            pm = sum(1 for a, b in zip(gp, box) if a and b and a == b)
            key = (pm, sc)
            if key > best_key:
                best, best_key = o, key
        if best is not None and best_key[0] >= n_holes - 2:
            return best["value"], f"par-match {best_key[0]}/{n_holes}"

    # Fortsatt tvil, men klar navne-leder → bruk den.
    if top_score > 0 and (top_score - second) >= 20:
        return top_o["value"], "navn/hull"

    # Siste utvei: er det nøyaktig ÉN «ordentlig» bane (ikke kort/dame/tour/placeholder)?
    # Da er den hovedbanen – f.eks. «Østmarka 18-hull» når man har spilt 9 hull der.
    # Trygt fordi vi bare gjør dette når det ikke finnes flere reelle alternativer.
    real = [o for _sc, o in ranked
            if not any(w in o["text"].lower() for w in _SHORT + _SPECIAL)]
    if len(real) == 1:
        return real[0]["value"], "hovedbane"
    return None, "flertydig"


def _select_club_for(fr, rnd: dict):
    """Velg riktig GolfBox-klubb for runden (koordinat/mapping). Returnerer club-tekst."""
    course_name = rnd.get("course", "") or ""
    override = load_course_map().get(course_name, {})
    if not (override.get("club") or "").strip():
        m = course_matcher.match(rnd.get("lat"), rnd.get("lon"), course_name)
        if m:
            override = {"club": m.get("club", "")}
    club_guess = (override.get("club") or "").strip() or course_name.split("~")[0].strip()
    club_val = (best_option_value(fr, "fld_Club", club_guess)
                or best_option_value(fr, "fld_Club", course_name))
    if club_val:
        try:
            fr.select_option("#fld_Club", value=club_val)
            time.sleep(2.0)
        except Exception:
            pass
    return club_guess


def inspect_course_form(fr, rnd: dict) -> None:
    """Diagnose: velg klubb + første bane/tee, og dump par-strukturen i skjemaet."""
    club = _select_club_for(fr, rnd)
    try:
        fr.select_option("#fld_HolesPlayed", value="18")
        fr.wait_for_selector("#ScoreHole_0", timeout=8000)
    except Exception:
        pass
    courses = [o for o in _options(fr, "fld_Course") if o.get("value") and o.get("text", "").strip()]
    log(f"🔎 INSPECT: klubb «{club}» → {len(courses)} baner: {[c['text'] for c in courses]}")
    if courses:
        try:
            fr.select_option("#fld_Course", value=courses[0]["value"])
            time.sleep(1.5)
            tees = [o for o in _options(fr, "fld_Tee") if o.get("value")]
            if tees:
                fr.select_option("#fld_Tee", value=tees[0]["value"])
                time.sleep(1.0)
            fr.wait_for_selector("#ScoreHole_0", timeout=8000)
        except Exception:
            pass
        try:
            info = fr.evaluate(
                """() => {
                    const out = {parCandidates: [], sample: ''};
                    document.querySelectorAll("*").forEach(e => {
                        const id = e.id || '', cl = (e.className && e.className.toString()) || '';
                        if (/par/i.test(id) || /par/i.test(cl)) {
                            const t = (e.textContent || e.value || '').trim().slice(0, 24);
                            if (out.parCandidates.length < 40)
                                out.parCandidates.push({id: id, cl: cl, tag: e.tagName, text: t});
                        }
                    });
                    const inp = document.getElementById('ScoreHole_0');
                    if (inp) { const t = inp.closest('table') || inp.parentElement;
                               out.sample = (t ? t.outerHTML : '').slice(0, 6000); }
                    return out;
                }"""
            )
            log("🔎 INSPECT par-kandidater: "
                + json.dumps(info.get("parCandidates", [])[:40], ensure_ascii=False))
            outdir = PROJECT_DIR / "data" / "golfbox_map"
            outdir.mkdir(parents=True, exist_ok=True)
            (outdir / "score_form.html").write_text(fr.content(), encoding="utf-8")
            (outdir / "score_table_sample.html").write_text(info.get("sample", ""), encoding="utf-8")
            log("🔎 INSPECT: lagret data/golfbox_map/score_form.html + score_table_sample.html")
        except Exception as e:
            log(f"🔎 INSPECT feilet: {e}")


_TEE_TRANS = {
    "red": "rød", "yellow": "gul", "white": "hvit", "blue": "blå", "green": "grønn",
    "black": "svart", "orange": "oransje", "gold": "gull",
    "mens": "herrer", "men": "herrer", "ladies": "damer", "women": "damer", "womens": "damer",
}


def _translate_tee(s: str) -> str:
    return _TEE_TRANS.get((s or "").strip().lower(), s)


def _read_rating_slope(fr):
    """Les CR/slope som GolfBox viser for valgt tee (norsk desimalkomma → punktum)."""
    def _val(sel):
        try:
            return (fr.eval_on_selector(sel, "el => el.value") or "").strip()
        except Exception:
            return ""
    r, s = _val("#fld_CourseRating"), _val("#fld_Slope")
    try:
        rating = float(r.replace(",", ".")) if r else None
    except Exception:
        rating = None
    try:
        slope = int(float(s)) if s else None
    except Exception:
        slope = None
    return rating, slope


def match_tee_by_rating(fr, g_rating, g_slope, n_holes=18):
    """Finn GolfBox-tee via RATING/slope – universelt, uavhengig av farge/tall.
    Returnerer (streng_value, streng_tekst, readings, nærmeste) der:
      streng_* = treff innen ~0,5 rating (trygt), ellers (None, '')
      readings = [(tekst, CR, slope), ...]
      nærmeste = (value, tekst, diff) – nærmeste kandidat uansett toleranse (best-effort)."""
    # GolfBox viser 18-hulls course rating i skjemaet, også når 9 hull er valgt. For en
    # 9-hullsrunde gir Garmin ~halv rating (f.eks. 31.9), så vi dobler Garmins rating før
    # sammenligning (31.9 → 63.8 ≈ GolfBox 61.8). Generelt for alle 9-hullsrunder.
    if n_holes == 9 and g_rating:
        g_rating = float(g_rating) * 2
    readings = []
    best, best_diff = None, 99.0
    if g_rating:
        for o in [o for o in _options(fr, "fld_Tee") if o.get("value")]:
            try:
                fr.select_option("#fld_Tee", value=o["value"], timeout=4000)
            except Exception:
                continue
            time.sleep(1.3)  # la updateStats() hente CR/slope for tee-en
            rating, slope = _read_rating_slope(fr)
            readings.append((o.get("text", "").strip(), rating, slope))
            if rating is None:
                continue
            diff = abs(rating - float(g_rating))
            if g_slope and slope:
                diff += abs(slope - int(g_slope)) * 0.02
            if diff < best_diff:
                best, best_diff = o, diff
    nearest = (best["value"], best.get("text", "").strip(), round(best_diff, 1)) if best else None
    if best is not None and best_diff <= 0.5:  # trygt treff
        return best["value"], best.get("text", "").strip(), readings, nearest
    return None, "", readings, nearest


def _round_n_holes(rnd: dict) -> int:
    """9 eller 18 hull – utledet fra ANTALL HULL MED SCORE (ikke max hull-nr, som
    ville gjort en back-nine-runde til 18; ikke Garmins >=18-terskel, som gjorde en
    18-runde med ett manglende hull til 9). ≥10 scorede hull → 18-hulls, ellers 9."""
    holes = rnd.get("holes") or []
    scored = sum(1 for h in holes if h.get("strokes") is not None)
    if not scored:
        scored = rnd.get("holesCompleted") or 0
    return 18 if scored >= 10 else 9


def fill_score_form(fr, rnd: dict, for_test: bool = False):
    """Fyll ut skjemaet i ramme `fr`. Returnerer (notater, status).
    status forteller hva som ble trygt matchet – brukes til å avgjøre auto-lagring.
    for_test=True hopper over score-fylling + markør (raskere; kun matching testes)."""
    notes: list[str] = []
    holes = rnd.get("holes", []) or []
    n_holes = _round_n_holes(rnd)
    status = {"club": False, "course": False, "tee": False, "holes": 0,
              "n_holes": n_holes, "marker": False, "tee_uncertain": False,
              "tee_no_source": False, "holes_missing": [], "scores_missing": False}

    # 1) Antall hull (bygger om score-tabellen)
    try:
        fr.select_option("#fld_HolesPlayed", value=str(n_holes))
        fr.wait_for_selector("#ScoreHole_0", timeout=8000)
        notes.append(f"Hull: {n_holes}")
    except Exception as e:
        notes.append(f"⚠️ Klarte ikke sette antall hull ({e})")

    # 2) Rundetype = Selskapsrunde (2)
    try:
        fr.select_option("#roundTypeSelect", value="2")
        notes.append("Rundetype: Selskapsrunde")
    except Exception:
        pass

    # 3) Dato
    ddmmyyyy = iso_to_ddmmyyyy(rnd.get("date"))
    if ddmmyyyy:
        try:
            fr.fill("#fld_ScoreDate", ddmmyyyy)
            fr.dispatch_event("#fld_ScoreDate", "change")
            notes.append(f"Dato: {ddmmyyyy}")
        except Exception as e:
            notes.append(f"⚠️ Dato feilet ({e})")

    # 4) KLUBB + bane. GolfBox viser kun baner for valgt klubb, så velg klubb først.
    course_name = rnd.get("course", "") or ""
    # Prioritet: 1) manuell mapping (navn) 2) koordinat-match 3) fuzzy navn.
    override = load_course_map().get(course_name, {})
    if not (override.get("club") or "").strip():
        m = course_matcher.match(rnd.get("lat"), rnd.get("lon"), course_name)
        if m:
            override = {
                "club": m.get("club", ""),
                "course": m.get("course", ""),
                "tee": m.get("tee", ""),
            }
            notes.append(f"📍 Koordinat-match ({m.get('distance_m', '?')} m): «{override['club']}»")
    club_guess = (override.get("club") or "").strip() or course_name.split("~")[0].strip()
    club_val = (
        best_option_value(fr, "fld_Club", club_guess)
        or best_option_value(fr, "fld_Club", course_name)
    )
    if club_val:
        try:
            current = fr.eval_on_selector("#fld_Club", "el => el.value")
            if current != club_val:
                fr.select_option("#fld_Club", value=club_val, timeout=10000)
                time.sleep(2.0)  # changeClub() laster banene til klubben
            status["club"] = True
            notes.append(f"Klubb: «{club_guess}»")
        except Exception as e:
            notes.append(f"⚠️ Klubb-valg feilet ({e})")
    else:
        key = core(club_guess)[:4]
        cand = [o["text"] for o in _options(fr, "fld_Club")
                if key and key in core(o.get("text", ""))] if key else []
        notes.append(
            f"❗ Fant ikke klubben «{club_guess}» – velg manuelt."
            + (f" Lignende i GolfBox: [{', '.join(cand[:8])}]" if cand
               else " (ingen lignende klubb i GolfBox)"))

    # Bane innen valgt klubb (mapping > delen etter « ~ » > hele navnet).
    course_part = (override.get("course") or "").strip() or (
        course_name.split("~")[-1].strip() if "~" in course_name else course_name
    )
    garmin_pars = garmin_par_sequence(rnd, n_holes)
    course_val, how = choose_course(
        fr, [course_part, course_name], n_holes, garmin_pars,
        core(club_guess), course_name
    )
    if course_val:
        course_text = ""
        for o in _options(fr, "fld_Course"):
            if o.get("value") == course_val:
                course_text = o.get("text", "").strip()
                break
        if _pick_course(fr, course_val, course_text):
            time.sleep(0.6)
            status["course"] = True
            notes.append(f"Bane: «{course_text or how}» ({how})")
        else:
            notes.append(f"⚠️ Bane «{course_text or how}» festet ikke i GolfBox – velg manuelt.")
    else:
        # Logg de faktiske banenavnene så vi ser hva GolfBox tilbyr for denne klubben.
        avail = ", ".join(
            o["text"] for o in _options(fr, "fld_Course") if o.get("text", "").strip()
        )
        notes.append(f"❗ Fant ikke banen «{course_part}» ({how}). Baner i GolfBox: [{avail}]")

    # 5) Tee settes HELT TIL SLUTT (se nederst) – GolfBox laster tee-lista på nytt
    #    asynkront etter bane-valg og kan ellers overskrive den til standard-tee.

    # 6) Hull-scorer (vent til tabellen er gjenoppbygd etter evt. bane-bytte)
    try:
        fr.wait_for_selector("#ScoreHole_0", timeout=8000)
    except Exception:
        pass
    if for_test:
        status["holes"] = status["n_holes"]  # antar OK i test (fylles ikke inn)
    else:
        scored = [h for h in holes if h.get("strokes") is not None]
        filled = 0
        if n_holes == 9:
            # 9-hulls: legg de spilte hullene i celle 0–8 i rekkefølge. Håndterer
            # back-nine (hull-nr 10–18) som ellers ville truffet feil/ikke-eksisterende celler.
            for idx, h in enumerate(scored[:9]):
                sel = f"#ScoreHole_{idx}"
                try:
                    fr.fill(sel, str(h["strokes"]))
                    fr.dispatch_event(sel, "keyup")
                    filled += 1
                except Exception:
                    pass
        else:
            # 18-hulls: hver score i sitt eget hull (celle = nr-1). Hull uten score
            # er et EKTE manglende hull (kan ikke auto-postes).
            for h in holes:
                num, strokes = h.get("number"), h.get("strokes")
                if not num or strokes is None:
                    continue
                sel = f"#ScoreHole_{num - 1}"
                try:
                    fr.fill(sel, str(strokes))
                    fr.dispatch_event(sel, "keyup")
                    filled += 1
                except Exception:
                    pass
        status["holes"] = filled
        notes.append(f"Hull-scorer fylt inn: {filled}/{n_holes}")
        # Ingen score i det hele tatt = Garmin har ikke synket scorene ennå (runden er
        # nettopp ferdig). Da VENTER vi (kode 6), akkurat som for manglende tee-data.
        if filled == 0:
            status["scores_missing"] = True
            notes.append("❗ Ingen hull-score fra Garmin ennå (synkes trolig straks) – venter.")
        # Kun for 18-hulls er et delvis manglende hull et reelt problem (for 9-hulls er
        # de «manglende» hullene bare de ni vi ikke spilte).
        elif n_holes == 18 and filled < n_holes:
            missing = [h.get("number") for h in holes if h.get("strokes") is None]
            status["holes_missing"] = missing
            notes.append(f"❗ Mangler score på hull {', '.join(map(str, missing))} "
                         f"(Garmin registrerte dem ikke) – fyll inn selv i web-appen.")

    # 7) Markør (fra .env). Hoppes over i test-modus (påvirker ikke matching).
    marker_no = None if for_test else os.getenv("GOLFBOX_MARKER_MEMBERNO")
    marker_name = None if for_test else os.getenv("GOLFBOX_MARKER_NAME")
    if marker_no:
        def _cur_guid() -> str:
            try:
                return (fr.eval_on_selector("#fld_MarkerMemberGUID", "el => el.value") or "").strip()
            except Exception:
                return ""

        def _do_marker_search() -> None:
            # Setter dropdown=Medlemsnr., nummer, låser mot reset, og kjører søket.
            try:
                fr.evaluate(
                    """(num) => {
                        try { window.DontResetMarker = true; } catch (e) {}
                        var dd = document.getElementById('markerChoiceDropdown');
                        if (dd) { dd.value = '1'; dd.dispatchEvent(new Event('change', {bubbles:true})); }
                        try { if (typeof markerDropdown !== 'undefined' && markerDropdown) markerDropdown.value = '1'; } catch (e) {}
                        var inp = document.getElementById('fld_MarkerMemberNumber');
                        if (inp) { inp.removeAttribute('disabled'); inp.value = num;
                                   inp.dispatchEvent(new Event('input', {bubbles:true})); }
                        var btn = document.getElementById('searchMarkerButton');
                        if (btn) btn.removeAttribute('disabled');
                        if (typeof searchMarker === 'function') { searchMarker(); }
                        else if (btn) { btn.click(); }
                    }""",
                    marker_no,
                )
            except Exception:
                pass

        # Golfbox laster «medspillere» asynkront når banen velges, og kan OVERSKRIVE
        # markøren vår. Vent til det har skjedd, sett markøren SIST, og forsvar den til
        # den står stabilt i et par sekunder.
        time.sleep(2.5)
        guid = ""
        for _attempt in range(6):
            _do_marker_search()
            # vent på at søket fyller GUID
            for _ in range(10):
                time.sleep(0.5)
                guid = _cur_guid()
                if guid:
                    break
            if not guid:
                continue
            # holder markøren seg (ingen asynkron overskriving) i ~2s?
            held = True
            for _ in range(4):
                time.sleep(0.5)
                if _cur_guid() != guid:
                    held = False
                    break
            if held:
                break

        err = ""
        if not guid:
            try:
                err = fr.eval_on_selector("#markerSearchErrorText", "el => el.textContent") or ""
            except Exception:
                err = ""
        status["marker"] = bool(guid)
        if status["marker"]:
            notes.append(f"Markør ({marker_no}): bekreftet ✓")
        else:
            notes.append(
                f"Markør ({marker_no}): IKKE bekreftet"
                + (f" – Golfbox sier: «{err.strip()}»" if err.strip() else "")
            )
    elif marker_name:
        try:
            fr.eval_on_selector(
                "#markerChoiceDropdown",
                "el => { el.value = '0'; el.dispatchEvent(new Event('change', {bubbles:true})); }",
            )
            fr.fill("#fld_MarkerMemberName", marker_name)
        except Exception:
            pass
        notes.append(f"Markør (navn): {marker_name} – trykk «Søk» for å bekrefte")
    else:
        notes.append("Markør: ikke satt – legg inn manuelt.")

    # 8) TEE – ALLTID fra Garmin-runden, satt HELT TIL SLUTT så GolfBox sin sene
    #    getTeeOptions-omlasting ikke overskriver den til standard-tee.
    # Forsvar banevalget: GolfBox kan ha revertert til standardbanen (f.eks.
    # «Narvesen Tour», som ikke har tees) under score-/markør-stegene. Re-asserter
    # valgt bane før vi leser tees – ellers leser vi feil banes (tomme) tee-liste.
    if course_val:
        try:
            cur_course = fr.eval_on_selector("#fld_Course", "el => el.value") or ""
        except Exception:
            cur_course = ""
        if cur_course != course_val:
            notes.append(f"↻ Bane hadde revertert – gjenvelger «{course_text}».")
            _pick_course(fr, course_val, course_text)
    _wait_select_stable(fr, "fld_Tee", settle=1.5, timeout=10.0)
    _ensure_tees_loaded(fr, timeout=8.0)  # tee-lista kan være tom pga async-race
    avail_tees = [o.get("text", "").strip() for o in _options(fr, "fld_Tee") if o.get("text", "").strip()]
    tee_target = str(rnd.get("teeBox") or (override.get("tee") or "").strip() or "")
    # Ga Garmin i det hele tatt et tee-signal? (Ofte None rett etter runden – Garmin
    # fyller tee/rating med forsinkelse.) Da er dette en VENT-sak, ikke en match-feil.
    status["tee_no_source"] = (not tee_target) and (rnd.get("teeBoxRating") is None)

    tee_val, tee_text, how_tee = None, "", ""
    # Kjør alltid rating-matchen for å ha readings/nearest til best-effort senere.
    r_val, r_text, tee_readings, tee_nearest = match_tee_by_rating(
        fr, rnd.get("teeBoxRating"), rnd.get("teeBoxSlope"), n_holes)

    # 0) EKSAKT etikett-treff (Garmin «56» == GolfBox «56»). Norske baner bruker
    #    meter-merker som tee-navn; en eksakt etikett er mer pålitelig enn Garmins
    #    utdaterte (2019) rating – så dette går FØR rating-match.
    if tee_target:
        _tl = tee_target.strip().lower()
        for o in _options(fr, "fld_Tee"):
            if o.get("value") and o.get("text", "").strip().lower() == _tl:
                tee_val, tee_text, how_tee = o["value"], o.get("text", "").strip(), "etikett-eksakt"
                break

    # 1) RATING-basert (universelt) som reserve.
    if not tee_val and r_val:
        tee_val, tee_text, how_tee = r_val, r_text, "rating"
    # 2) Etikett-match (med farge-oversettelse En↔No) som reserve.
    if not tee_val and tee_target:
        tv = (best_option_value(fr, "fld_Tee", tee_target)
              or best_option_value(fr, "fld_Tee", _translate_tee(tee_target)))
        if tv:
            tee_val = tv
            tee_text = next((o.get("text", "").strip() for o in _options(fr, "fld_Tee")
                             if o.get("value") == tv), "")
            how_tee = "etikett"
    # 3) Lært tee (override) som reserve.
    if not tee_val and (override.get("tee") or "").strip():
        tv = best_option_value(fr, "fld_Tee", override["tee"])
        if tv:
            tee_val, how_tee = tv, "lært"
            tee_text = next((o.get("text", "").strip() for o in _options(fr, "fld_Tee")
                             if o.get("value") == tv), "")
    # 4) Bare én reell tee? Da er den utvetydig – velg den.
    if not tee_val:
        real_tees = [o for o in _options(fr, "fld_Tee") if o.get("value")]
        if len(real_tees) == 1:
            tee_val, how_tee = real_tees[0]["value"], "eneste tee"
            tee_text = real_tees[0].get("text", "").strip()

    # 5) BEST-EFFORT (kombinasjon): fortsatt usikker → nærmeste rating, men FLAGG.
    #    Garmin sine ratinger kan avvike (utdaterte 2019-data), så dette kan bomme.
    #    Runden går til godkjenning, så markøren/du kan fange en feil tee.
    if not tee_val and tee_nearest and tee_nearest[2] <= 6.0:
        tee_val, tee_text = tee_nearest[0], tee_nearest[1]
        how_tee = f"best-effort Δ{tee_nearest[2]}"
        status["tee_uncertain"] = True

    if tee_val:
        if _pick_option(fr, "fld_Tee", tee_val, tee_text):
            status["tee"] = True
            warn = " ⚠️ DOBBELTSJEKK TEE" if status["tee_uncertain"] else ""
            notes.append(f"Tee: «{tee_text or tee_target}» ({how_tee}){warn}")
        else:
            notes.append(f"❗ Tee «{tee_text or tee_target}» festet ikke – velg manuelt.")
    else:
        crs = ", ".join(f"{t}=CR{cr}" for t, cr, _s in tee_readings) if tee_readings else ""
        notes.append(
            f"❗ Fant ikke tee (Garmin teeBox='{rnd.get('teeBox')}', "
            f"rating={rnd.get('teeBoxRating')}). GolfBox: [{crs or ', '.join(avail_tees)}]")

    return notes, status


def try_navigate_to_score(page) -> bool:
    """Prøv å klikke seg til «Innlever score» (Score → Innlever score), slik man
    gjør manuelt. Returnerer True hvis noe ble klikket."""
    direct = [
        "a[href*='newWHSScore']",
        "a[href*='score/whs']",
        "a:has-text('Innlever score')",
        "text=Innlever score",
        "button:has-text('Innlever score')",
    ]
    for fr in page.frames:
        for sel in direct:
            try:
                el = fr.query_selector(sel)
                if el:
                    el.click(timeout=4000)
                    return True
            except Exception:
                continue
    # «Innlever score» ikke synlig? Åpne «Score»-menyen først, prøv så igjen.
    for fr in page.frames:
        try:
            score = fr.query_selector("a:has-text('Score'), text=Score")
            if score:
                score.click(timeout=3000)
                time.sleep(1.2)
                el = fr.query_selector("a:has-text('Innlever score'), text=Innlever score")
                if el:
                    el.click(timeout=4000)
                    return True
        except Exception:
            continue
    return False


def _find_password_frame(page):
    """Returner (frame, passord-element) for et SYNLIG passordfelt.
    Skjulte modaler (før «GOLFBOX» er trykket) teller ikke."""
    for fr in page.frames:
        try:
            for pw in fr.query_selector_all("input[type='password']"):
                try:
                    if pw.is_visible():
                        return fr, pw
                except Exception:
                    continue
        except Exception:
            continue
    return None, None


def try_auto_login(page, username: str, password: str) -> bool:
    """Logg inn automatisk på norskgolf.no → GolfBox.
    To-trinns: 1) klikk «GolfBox» (åpner innloggingsmodulen) 2) fyll brukernavn/passord.
    Gjør at en utløpt økt fikser seg selv – ingen manuell handling. True = sendte inn."""
    if not username or not password:
        return False

    fr, pw = _find_password_frame(page)

    # Fase 1: ingen passordfelt synlig ennå → åpne GolfBox-innloggingen.
    if not pw:
        for f in page.frames:
            try:
                link = (
                    f.query_selector("a:has-text('GolfBox')")
                    or f.query_selector("a:has-text('Golfbox')")
                    or f.query_selector("button:has-text('GolfBox')")
                    or f.query_selector("a:has-text('Logg inn')")
                    or f.query_selector("[href*='golfbox' i]")
                )
                if link:
                    link.click(timeout=5000)
                    time.sleep(2)
                    break
            except Exception:
                continue
        # Neste runde i løkka finner passordfeltet og fyller det ut.
        return False

    # Fase 2: fyll inn brukernavn/passord i modulen (kun synlige felt).
    try:
        user = None
        for sel in (
            "input[type='email']",
            "input[name*='user' i]", "input[name*='email' i]", "input[name*='bruker' i]",
            "input[id*='user' i]", "input[id*='email' i]",
            "input[type='text']",
        ):
            for cand in fr.query_selector_all(sel):
                try:
                    if cand.is_visible():
                        user = cand
                        break
                except Exception:
                    continue
            if user:
                break
        if not user:
            return False
        user.fill(username)
        pw.fill(password)
        # Finn en SYNLIG «Logg inn»-knapp; ellers trykk Enter i passordfeltet.
        btn = None
        for sel in (
            "button:has-text('Logg inn')", "button[type='submit']",
            "input[type='submit']", "button:has-text('Logg')",
            "button:has-text('Login')", "a:has-text('Logg inn')",
        ):
            for cand in fr.query_selector_all(sel):
                try:
                    if cand.is_visible():
                        btn = cand
                        break
                except Exception:
                    continue
            if btn:
                break
        clicked = False
        if btn:
            try:
                btn.click(timeout=5000)
                clicked = True
            except Exception:
                clicked = False
        if not clicked:
            try:
                pw.press("Enter")
            except Exception:
                pass
        return True
    except Exception:
        return False


def dump_debug(page, label: str) -> None:
    """Lagre hjem-/mellomsiden så vi kan lese menyen om navigeringen feiler."""
    out = PROJECT_DIR / "data" / "golfbox_map"
    out.mkdir(parents=True, exist_ok=True)
    try:
        (out / f"{label}_page.html").write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(out / f"{label}.png"), full_page=True)
    except Exception:
        pass
    for i, fr in enumerate(page.frames):
        try:
            (out / f"{label}_frame_{i}.html").write_text(
                f"<!-- url: {fr.url} -->\n{fr.content()}", encoding="utf-8"
            )
        except Exception:
            pass


def _find_score_frame(ctx):
    for pg in list(ctx.pages):
        try:
            for fr in pg.frames:
                try:
                    if fr.query_selector("#fld_ScoreDate"):
                        return fr
                except Exception:
                    continue
        except Exception:
            continue
    return None


def open_score_form(ctx, gb_user=None, gb_pass=None, timeout: float = 150):
    """Logg inn (auto) om nødvendig og åpne WHS-score-skjemaet. Returner rammen
    eller None. Gjenbrukbar for test-harness (én innlogging, mange runder)."""
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    try:
        page.goto(SCORE_URL, wait_until="domcontentloaded", timeout=20000)
    except Exception:
        pass

    def _gb_pages():
        return [pg for pg in list(ctx.pages) if "golfbox" in (pg.url or "").lower()]

    deadline = time.time() + timeout
    last_nav, last_login, login_tries = time.time(), 0.0, 0
    while time.time() < deadline:
        fr = _find_score_frame(ctx)
        if fr:
            return fr
        if not _gb_pages() and gb_user and gb_pass and login_tries < 6 \
                and time.time() - last_login > 8:
            for pg in list(ctx.pages):
                if try_auto_login(pg, gb_user, gb_pass):
                    login_tries += 1
                    time.sleep(3)
                    try:
                        pg.goto(SCORE_URL, wait_until="domcontentloaded", timeout=15000)
                    except Exception:
                        pass
                    break
            last_login = time.time()
        gbp = _gb_pages()
        if gbp and time.time() - last_nav > 8:
            gb = gbp[-1]
            try:
                gb.bring_to_front()
            except Exception:
                pass
            if not try_navigate_to_score(gb):
                try:
                    gb.goto(SCORE_URL, wait_until="domcontentloaded", timeout=15000)
                except Exception:
                    pass
            last_nav = time.time()
        time.sleep(2)
    return None


def reopen_score_form(ctx, timeout: float = 40):
    """Last score-skjemaet på nytt (frisk, tom form) og returner rammen."""
    for pg in list(ctx.pages):
        if "golfbox" in (pg.url or "").lower():
            try:
                pg.goto(SCORE_URL, wait_until="domcontentloaded", timeout=15000)
            except Exception:
                pass
            break
    end = time.time() + timeout
    while time.time() < end:
        fr = _find_score_frame(ctx)
        if fr:
            time.sleep(1.0)
            return fr
        time.sleep(1)
    return None


def _log_attempt(rnd, sel, status, notes, posted) -> None:
    """Telemetri: send utfallet av forsøket til sentralbasen (best effort)."""
    try:
        import central_registry
        reason = next((n.strip() for n in reversed(notes)
                       if ("❗" in n or "⚠️" in n or "DOBBELTSJEKK" in n)), "")
        central_registry.log_attempt({
            "round_id": rnd.get("id"),
            "garmin_course": rnd.get("course", ""),
            "club": (sel or {}).get("club", ""), "club_ok": status.get("club", False),
            "course": (sel or {}).get("course", ""), "course_ok": status.get("course", False),
            "tee": (sel or {}).get("tee", ""), "tee_ok": status.get("tee", False),
            "tee_uncertain": status.get("tee_uncertain", False),
            "posted": posted,
            "reason": reason,
        })
    except Exception:
        pass


def main() -> None:
    if len(sys.argv) < 2:
        print("Bruk: python3 golfbox_post.py <round_id>")
        raise SystemExit(1)
    round_id = sys.argv[1]
    load_dotenv(PROJECT_DIR / ".env")

    # Auto-modus (for sky / bakgrunn): ingen skjerm, ingen manuell innlogging,
    # og lagre automatisk kun når alt er trygt matchet.
    auto = os.getenv("GOLFBOX_AUTO") == "1" or "--auto" in sys.argv
    headless = os.getenv("GOLFBOX_HEADLESS") == "1"  # egen bryter (skyen setter denne)
    auto_submit = os.getenv("GOLFBOX_AUTO_SUBMIT") == "1"
    gb_user = os.getenv("GOLFBOX_USERNAME")
    gb_pass = os.getenv("GOLFBOX_PASSWORD")

    log(f"=== Start: runde {round_id}{' [AUTO]' if auto else ''} ===")
    try:
        rnd = get_round(round_id)
    except Exception as e:
        log(f"❌ Klarte ikke hente runde-data: {e}")
        raise SystemExit(1)
    log(f"Runde: {rnd.get('course')} · {rnd.get('date', '')[:10]} · {rnd.get('strokes')} slag")

    if auto and not STATE_FILE.exists() and not (gb_user and gb_pass):
        log("❌ AUTO: ingen lagret økt OG ingen GOLFBOX_USERNAME/PASSWORD å logge inn med. "
            "Avslutter med kode 2.")
        raise SystemExit(2)

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=headless)
        except Exception as e:
            log(f"❌ Klarte ikke starte nettleser: {e}")
            raise SystemExit(1)
        ctx_args = {"viewport": {"width": 1400, "height": 950}}
        if STATE_FILE.exists():
            ctx_args["storage_state"] = str(STATE_FILE)
            log("Bruker lagret Golfbox-innlogging.")
        else:
            log("Ingen lagret innlogging – du logger inn manuelt denne ene gangen.")
        ctx = browser.new_context(**ctx_args)
        log("Nettleser åpnet.")
        page = ctx.new_page()

        # GolfBox kan åpne i en NY fane. Derfor følger vi alle faner i konteksten,
        # ikke bare den første, og leter etter skjemaet i hver fane sine rammer.
        log("Navigerer til Golfbox. Logg inn i vinduet hvis du blir bedt om det ...")
        try:
            page.goto(SCORE_URL, wait_until="domcontentloaded", timeout=20000)
        except Exception:
            pass
        if not STATE_FILE.exists() and not auto:
            log("FØRSTE GANG: 1) Logg inn på norskgolf.no. 2) Klikk deg inn i GolfBox "
                "(Min Golf / GolfBox). Så tar scriptet over automatisk og husker deg etterpå.")

        def find_score_frame():
            for pg in list(ctx.pages):
                try:
                    frames = pg.frames
                except Exception:
                    continue
                for fr in frames:
                    try:
                        if fr.query_selector("#fld_ScoreDate"):
                            return fr
                    except Exception:
                        continue
            return None

        def golfbox_pages():
            out = []
            for pg in list(ctx.pages):
                try:
                    if "golfbox" in (pg.url or "").lower():
                        out.append(pg)
                except Exception:
                    continue
            return out

        deadline = time.time() + (180 if auto else 300)
        target = None
        last_nav = time.time()
        last_log = 0.0
        last_login = 0.0
        login_tries = 0
        saved = False
        while time.time() < deadline:
            target = find_score_frame()
            if target:
                break

            if time.time() - last_log > 8:
                urls = " | ".join((p.url or "?") for p in ctx.pages)
                log(f"  venter på GolfBox … faner: {urls}")
                last_log = time.time()

            gb_pages = golfbox_pages()
            if not gb_pages and (gb_user and gb_pass) and login_tries < 5 \
                    and time.time() - last_login > 8:
                # Ikke inne i GolfBox ennå (økt utløpt / ny økt) – logg inn automatisk.
                for pg in list(ctx.pages):
                    if try_auto_login(pg, gb_user, gb_pass):
                        login_tries += 1
                        log(f"  logget inn automatisk (forsøk {login_tries}) …")
                        time.sleep(3)
                        try:
                            pg.goto(SCORE_URL, wait_until="domcontentloaded", timeout=15000)
                        except Exception:
                            pass
                        break
                last_login = time.time()

            gb_pages = golfbox_pages()
            if gb_pages:
                # Vi er inne i GolfBox (kanskje i en ny fane). Lagre økten.
                if not saved:
                    try:
                        ctx.storage_state(path=str(STATE_FILE))
                        saved = True
                        log("Innlogging lagret.")
                    except Exception:
                        pass
                # Klikk oss til «Innlever score» i GolfBox-fanen (direktelenke som reserve).
                if time.time() - last_nav > 8:
                    gb = gb_pages[-1]
                    try:
                        gb.bring_to_front()
                    except Exception:
                        pass
                    if try_navigate_to_score(gb):
                        log("  klikket meg mot «Innlever score» …")
                    else:
                        try:
                            gb.goto(SCORE_URL, wait_until="domcontentloaded", timeout=15000)
                            log("  prøvde direktelenke til score-skjemaet …")
                        except Exception:
                            pass
                    last_nav = time.time()
            time.sleep(2)

        if not target:
            if auto:
                log("❌ AUTO: fant ikke score-skjemaet (økt utløpt?). Avslutter med kode 2.")
                raise SystemExit(2)
            log("❌ Fant ikke score-skjemaet. Dumper alle faner så jeg kan lese menyen.")
            try:
                for i, pg in enumerate(ctx.pages):
                    dump_debug(pg, f"home{i}")
                log("   Lagret i data/golfbox_map/home*_*.html")
            except Exception:
                pass
            log("Vinduet står åpent – du kan navigere til «Innlever score» selv.")
            _idle(ctx)
            return

        log(f"Score-skjemaet funnet (ramme: {target.url}). Fyller ut ...")
        try:
            ctx.storage_state(path=str(STATE_FILE))  # oppdater/forny lagret økt
        except Exception:
            pass

        if os.getenv("GOLFBOX_INSPECT") == "1":
            inspect_course_form(target, rnd)
            log("🔎 INSPECT ferdig. Lukk vinduet.")
            return

        notes, status = fill_score_form(target, rnd)
        for n in notes:
            log("  " + n)

        safe = (
            status["club"] and status["course"] and status["tee"]
            and status["holes"] == status["n_holes"] and status["marker"]
        )

        if auto:
            posted = False
            if auto_submit and safe:
                posted = submit_score(target)
                if posted:
                    extra = " ⚠️ (tee valgt på skjønn – dobbeltsjekk før godkjenning!)" \
                        if status.get("tee_uncertain") else ""
                    log(f"✅ LAGRET i Golfbox – runden ligger nå til godkjennelse.{extra}")
                else:
                    log("⚠️ AUTO: lagringen ble ikke bekreftet. Flagges for manuell sjekk.")
            else:
                if not status["club"]:
                    _code = 5
                elif status.get("tee_no_source") or status.get("scores_missing"):
                    _code = 6
                else:
                    _code = 3
                reason = "auto-lagring av" if not auto_submit else "usikker match –"
                log(f"ℹ️ AUTO: {reason} ikke lagret. Runden er fylt ut, men trenger manuell "
                    f"sjekk (klubb={status['club']}, bane={status['course']}, "
                    f"tee={status['tee']}, markør={status['marker']}). Avslutter med kode {_code}.")
            _log_attempt(rnd, _read_selection(target), status, notes, posted)
            if posted:
                # kode 4 = lagret, men tee valgt på skjønn (bør dobbeltsjekkes)
                raise SystemExit(4 if status.get("tee_uncertain") else 0)
            # Ikke postet – skill kategoriene:
            #   kode 5 = klubben finnes ikke i GolfBox (ikke leverbar)
            #   kode 6 = Garmin har ikke tee-data ennå (VENT – prøv igjen senere)
            #   kode 3 = klubb OK, men bane/tee ikke bekreftet (kan fullføres)
            if not status["club"]:
                raise SystemExit(5)
            if status.get("tee_no_source") or status.get("scores_missing"):
                raise SystemExit(6)  # Garmin-data (tee/score) ikke klar ennå – vent
            raise SystemExit(3)

        log("✅ Ferdig utfylt. Sjekk bane/tee/markør i Golfbox og trykk «Lagre» selv. "
            "(Ingenting er sendt inn.)")
        # Auto-læring: mens vinduet er åpent følger vi med på hva DU velger av
        # klubb/bane/tee, og husker det for denne Garmin-banen til neste gang.
        _observe_and_idle(ctx, target, rnd)


def _read_selection(fr) -> dict:
    """Les valgt tekst i klubb-, bane- og tee-nedtrekkene."""
    try:
        return fr.evaluate(
            """() => {
                const t = id => { const el = document.getElementById(id);
                    if (!el || el.selectedIndex < 0) return '';
                    const o = el.options[el.selectedIndex];
                    return o ? o.textContent.trim() : ''; };
                return { club: t('fld_Club'), course: t('fld_Course'), tee: t('fld_Tee') };
            }"""
        ) or {}
    except Exception:
        return {}


def _save_learned_mapping(garmin_course: str, sel: dict) -> None:
    """Lagre Garmin-navn -> Golfbox klubb/bane/tee i golfbox_course_map.json."""
    if not garmin_course or not sel.get("club"):
        return
    entry = {
        "club": sel.get("club", ""),
        "course": sel.get("course", ""),
        "tee": sel.get("tee", ""),
    }
    try:
        raw = {}
        if COURSE_MAP_FILE.exists():
            raw = json.loads(COURSE_MAP_FILE.read_text(encoding="utf-8"))
        if raw.get(garmin_course) == entry:
            return  # allerede lært, ingen endring
        raw[garmin_course] = entry
        COURSE_MAP_FILE.write_text(
            json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        log(f"🧠 Lærte: «{garmin_course}» → klubb «{entry['club']}»"
            + (f", bane «{entry['course']}»" if entry["course"] else "")
            + (f", tee «{entry['tee']}»" if entry["tee"] else ""))
    except Exception:
        pass


def _observe_and_idle(ctx, fr, rnd) -> None:
    """Hold vinduet åpent, følg med på brukerens klubb/bane/tee-valg, og lær av det."""
    last = {}
    try:
        while ctx.pages:
            sel = _read_selection(fr)
            if sel.get("club") and sel.get("course"):
                last = sel
            time.sleep(2)
    except Exception:
        pass
    log(f"(observasjon slutt) valgt i skjemaet: {last} · koordinater: "
        f"{rnd.get('lat')}, {rnd.get('lon')}")
    if last.get("club"):
        # Lærings-sperre: lær kun hvis banen i skjemaet faktisk matcher runden.
        # Hindrer at feil/spesial-bane (f.eks. «... Damer - Tour») forurenser basen.
        cname = (last.get("course") or "").lower()
        n_holes = _round_n_holes(rnd)
        gpars = garmin_par_sequence(rnd, n_holes)
        box = _read_golfbox_pars(fr, n_holes)
        par_match = sum(1 for a, b in zip(gpars, box) if a and b and a == b)
        looks_wrong = any(w in cname for w in _SHORT) or any(w in cname for w in _SPECIAL)
        if looks_wrong or (any(gpars) and par_match < n_holes - 2):
            log(f"⚠️ Lærer IKKE «{last.get('course')}» – matcher ikke runden "
                f"(par {par_match}/{n_holes}). Velg riktig bane manuelt for å lære den.")
            return
        # Lær med KOORDINATER (skalerbart – matcher på posisjon neste gang).
        saved = course_matcher.learn(
            rnd.get("course", ""), rnd.get("lat"), rnd.get("lon"), last
        )
        if saved:
            log(f"🧠 Lærte (GPS): «{rnd.get('course', '')}» → klubb «{saved['club']}»"
                + (f", bane «{saved['course']}»" if saved.get("course") else "")
                + (f", tee «{saved['tee']}»" if saved.get("tee") else ""))
        # Backup: også navne-basert mapping.
        _save_learned_mapping(rnd.get("course", ""), last)


def _score_form_open(ctx) -> bool:
    """True hvis WHS-score-skjemaet (#cmdSave) fortsatt er åpent i en av fanene."""
    try:
        pages = list(ctx.pages)
    except Exception:
        return False
    for pg in pages:
        try:
            for f in pg.frames:
                try:
                    if f.query_selector("#cmdSave"):
                        return True
                except Exception:
                    continue
        except Exception:
            continue
    return False


def submit_score(fr) -> bool:
    """Trykk «Lagre», bekreft dialoger, og VERIFISER at lagringen faktisk landet.
    Suksess = score-skjemaet forsvinner (postback/redirect). Blir skjemaet stående
    (typisk validerings-avvisning), returneres False. Ingen dublett-risiko: auto_sync
    flagger da runden for manuell sjekk uten å prøve på nytt."""
    try:
        ctx = fr.page.context
    except Exception:
        ctx = None

    dialogs: list = []

    def _on_dialog(d):
        try:
            dialogs.append((d.type, d.message))
        except Exception:
            pass
        try:
            d.accept()
        except Exception:
            try:
                d.dismiss()
            except Exception:
                pass

    try:
        fr.page.on("dialog", _on_dialog)
    except Exception:
        pass

    try:
        fr.click("#cmdSave", timeout=5000)
    except Exception as e:
        log(f"  submit-feil: klarte ikke trykke «Lagre» ({e})")
        return False

    if ctx is None:
        time.sleep(4)
        return True  # kan ikke verifisere uten context – gammel oppførsel

    # Vent på bekreftelse: skjemaet forsvinner ved vellykket lagring.
    deadline = time.time() + 12
    while time.time() < deadline:
        time.sleep(1)
        if not _score_form_open(ctx):
            return True

    msg = next((m for (t, m) in dialogs if m), "")
    log("  ⚠️ Lagring IKKE bekreftet – score-skjemaet står fortsatt åpent"
        + (f" (GolfBox: «{msg.strip()}»)" if msg else "")
        + ". Runden flagges for manuell sjekk.")
    return False


def _idle(ctx) -> None:
    """Hold nettleseren åpen til brukeren lukker vinduet, og avslutt så rent."""
    try:
        while ctx.pages:
            time.sleep(1)
    except Exception:
        pass


if __name__ == "__main__":
    import traceback

    try:
        main()
    except SystemExit:
        raise
    except Exception:
        log("KRASJ:\n" + traceback.format_exc())
        raise
