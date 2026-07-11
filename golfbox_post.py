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


def norm(s: str) -> str:
    # aa == å i norsk; behandle likt for bedre matching.
    s = (s or "").lower().replace("aa", "å")
    return "".join(ch for ch in s if ch.isalnum())


_GENERIC = ("golfklubb", "golfpark", "golfclub", "golfsearvi", "golf", "klubb", "club", "gk")


def core(s: str) -> str:
    """Kjernenavn uten generiske golf-ord (for klubb-/bane-match)."""
    s = (s or "").lower().replace("aa", "å")
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


def fill_score_form(fr, rnd: dict):
    """Fyll ut skjemaet i ramme `fr`. Returnerer (notater, status).
    status forteller hva som ble trygt matchet – brukes til å avgjøre auto-lagring."""
    notes: list[str] = []
    holes = rnd.get("holes", []) or []
    n_holes = 18 if (rnd.get("holesCompleted") or 0) >= 18 else 9
    status = {"club": False, "course": False, "tee": False, "holes": 0,
              "n_holes": n_holes, "marker": False}

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
                fr.select_option("#fld_Club", value=club_val)
                time.sleep(2.0)  # changeClub() laster banene til klubben
            status["club"] = True
            notes.append(f"Klubb: «{club_guess}»")
        except Exception as e:
            notes.append(f"⚠️ Klubb-valg feilet ({e})")
    else:
        notes.append(f"❗ Fant ikke klubben «{club_guess}» – velg manuelt.")

    # Bane innen valgt klubb (mapping > delen etter « ~ » > hele navnet).
    course_part = (override.get("course") or "").strip() or (
        course_name.split("~")[-1].strip() if "~" in course_name else course_name
    )
    course_val = (
        best_option_value(fr, "fld_Course", course_part)
        or best_option_value(fr, "fld_Course", course_name)
        or only_real_course(fr, "fld_Course")  # bare én bane i klubben? velg den.
    )
    if course_val:
        try:
            fr.select_option("#fld_Course", value=course_val)
            time.sleep(1.5)  # la changeCourse() laste tees/par
            status["course"] = True
            notes.append(f"Bane: «{course_part}»")
        except Exception as e:
            notes.append(f"⚠️ Bane-valg feilet ({e})")
    else:
        notes.append(f"❗ Fant ikke banen «{course_part}» – velg manuelt.")

    # 5) Tee (mapping > Garmin teeBox, f.eks. «54»)
    tee_target = str((override.get("tee") or "").strip() or rnd.get("teeBox") or "")
    if tee_target:
        tee_val = best_option_value(fr, "fld_Tee", tee_target)
        if tee_val:
            try:
                fr.select_option("#fld_Tee", value=tee_val)
                time.sleep(0.8)
                status["tee"] = True
                notes.append(f"Tee: {tee_target}")
            except Exception:
                notes.append(f"❗ Tee «{tee_target}» – velg manuelt.")
        else:
            notes.append(f"❗ Fant ikke tee «{tee_target}» – velg manuelt.")

    # 6) Hull-scorer (vent til tabellen er gjenoppbygd etter evt. bane-bytte)
    try:
        fr.wait_for_selector("#ScoreHole_0", timeout=8000)
    except Exception:
        pass
    filled = 0
    for h in holes:
        num = h.get("number")
        strokes = h.get("strokes")
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
    notes.append(f"Hull-scorer fylt inn: {filled}/{len(holes)}")

    # 7) Markør (fra .env). Settes via JavaScript så vi slipper synlighetskrav,
    #    så trykker vi «Søk» og venter på at markøren bekreftes (skjult GUID-felt).
    marker_no = os.getenv("GOLFBOX_MARKER_MEMBERNO")
    marker_name = os.getenv("GOLFBOX_MARKER_NAME")
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

    log(f"=== Start: runde {round_id}{' [AUTO]' if auto else ''} ===")
    try:
        rnd = get_round(round_id)
    except Exception as e:
        log(f"❌ Klarte ikke hente runde-data: {e}")
        raise SystemExit(1)
    log(f"Runde: {rnd.get('course')} · {rnd.get('date', '')[:10]} · {rnd.get('strokes')} slag")

    if auto and not STATE_FILE.exists():
        log("❌ AUTO: ingen lagret Golfbox-økt. Kan ikke logge inn uten skjerm. "
            "Forny økten (se guide). Avslutter med kode 2.")
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
        notes, status = fill_score_form(target, rnd)
        for n in notes:
            log("  " + n)

        safe = (
            status["club"] and status["course"] and status["tee"]
            and status["holes"] == status["n_holes"] and status["marker"]
        )

        if auto:
            if auto_submit and safe:
                if submit_score(target):
                    log("✅ LAGRET i Golfbox – runden ligger nå til godkjennelse.")
                    raise SystemExit(0)
                log("⚠️ AUTO: klarte ikke trykke Lagre. Avslutter med kode 3 (må sjekkes).")
                raise SystemExit(3)
            reason = "auto-lagring av" if not auto_submit else "usikker match –"
            log(f"ℹ️ AUTO: {reason} ikke lagret. Runden er fylt ut, men trenger manuell "
                f"sjekk (klubb={status['club']}, bane={status['course']}, tee={status['tee']}, "
                f"markør={status['marker']}). Avslutter med kode 3.")
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


def submit_score(fr) -> bool:
    """Trykk «Lagre» og bekreft eventuell dialog. Returnerer True ved suksess."""
    try:
        pg = fr.page
        pg.on("dialog", lambda d: d.accept())
    except Exception:
        pass
    try:
        fr.click("#cmdSave", timeout=5000)
        time.sleep(4)
        return True
    except Exception as e:
        log(f"  submit-feil: {e}")
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
