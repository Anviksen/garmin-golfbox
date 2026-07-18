#!/usr/bin/env python3
"""
Auto-sync – oppdag nye golfrunder og send dem til Golfbox automatisk.

Kjøres jevnlig (f.eks. hvert 5. minutt via GitHub Actions + cron-job.org):
  1. Logg inn på Garmin med lagret token (ingen passord/MFA).
  2. Hent oversikten og se om det har dukket opp nye runder siden sist.
  3. For hver NYE runde: oppdater lokal data, og kjør golfbox_post.py i auto-modus.
  4. Husk hva som er behandlet i data/posted.json (så vi aldri poster samme to ganger).

Første kjøring setter bare en «baseline» (markerer dagens runder som sett) og poster
INGENTING – slik at hele historikken din ikke blir sendt inn på én gang.

Kjøres slik:
    python3 auto_sync.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*a, **k):
        return None

try:
    from garminconnect import Garmin
except ImportError:
    print("Mangler garminconnect. pip install -r requirements.txt")
    raise SystemExit(1)

# Gjenbruk hjelpefunksjonene fra fetch-scriptet for å tolke oversikten.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_garmin import extract_scorecard_list, get_id  # noqa: E402

PROJECT_DIR = Path(__file__).resolve().parent
FETCH_SCRIPT = PROJECT_DIR / "fetch_garmin.py"
POST_SCRIPT = PROJECT_DIR / "golfbox_post.py"


@dataclass
class UserConfig:
    """Alt som er PER BRUKER i en synk-kjøring. I dag bygges det kun fra
    .env/GitHub-secrets via build_legacy_config() (én bruker = deg). Når multi-bruker
    kommer (se MULTIUSER_PLAN.md), bygges én UserConfig per rad fra Supabase, og
    sync_one_user() kalles i en løkke – selve synk-logikken under er allerede generell.

    VIKTIG: brukere må behandles STRENGT SEKVENSIELT (én om gangen i samme prosess).
    _apply_env() speiler cfg inn i os.environ, som både notify.py (samme prosess) og
    fetch_garmin.py/golfbox_post.py (subprosesser) leser fra – parallell kjøring for
    flere brukere ville race disse."""
    user_id: str = "local"
    label: str = "deg"                     # menneskelig navn til logglinjer
    tokenstore: str = "~/.garminconnect"
    golfbox_username: str | None = None
    golfbox_password: str | None = None
    marker_memberno: str | None = None
    marker_name: str | None = None
    notify_email: str | None = None
    ntfy_topic: str | None = None
    ntfy_server: str | None = None
    data_dir: Path = field(default_factory=lambda: PROJECT_DIR / "data")
    max_tee_wait: int = 12
    # Sant kun for dagens enkelt-bruker-drift: commit+push state til det (offentlige)
    # repoet. Multi-bruker-state hører hjemme i Supabase (user_round_state), ikke git
    # – se MULTIUSER_PLAN.md. Sett False for enhver fremtidig multi-bruker-config.
    persist_state_to_git: bool = True

    @property
    def state_file(self) -> Path:
        return self.data_dir / "posted.json"

    @property
    def log_file(self) -> Path:
        return self.data_dir / "auto_sync.log"


def build_legacy_config() -> UserConfig:
    """Bygger config fra dagens .env/GitHub-secrets – IDENTISK oppførsel som før
    denne refaktoreringen. Kall load_dotenv() FØR denne, ellers leses ikke .env
    lokalt (kun ekte env-variabler, som i skyen)."""
    return UserConfig(
        user_id="local",
        label="deg",
        tokenstore=os.getenv("GARMINTOKENS", "~/.garminconnect"),
        golfbox_username=os.getenv("GOLFBOX_USERNAME"),
        golfbox_password=os.getenv("GOLFBOX_PASSWORD"),
        marker_memberno=os.getenv("GOLFBOX_MARKER_MEMBERNO"),
        marker_name=os.getenv("GOLFBOX_MARKER_NAME"),
        notify_email=os.getenv("NOTIFY_EMAIL"),
        ntfy_topic=os.getenv("NTFY_TOPIC"),
        ntfy_server=os.getenv("NTFY_SERVER"),
        data_dir=PROJECT_DIR / "data",
        # Hvor mange kjøringer vi venter på at Garmin fyller inn tee-data før vi gir
        # opp og ber brukeren fullføre selv. Garmin kan bruke god stund på tee/rating,
        # så vi er rause: 12 × ~5 min ≈ 60 min. Runden postes automatisk så snart
        # tee-en dukker opp; først etter en time gir vi opp. Justerbart via env.
        max_tee_wait=int(os.getenv("GOLFBOX_TEE_WAIT_TRIES", "12")),
        persist_state_to_git=True,
    )


def _apply_env(cfg: UserConfig) -> None:
    """Speil cfg inn i os.environ for varigheten av DENNE brukerens kjøring. Gjør at
    fetch_garmin.py og golfbox_post.py (kalt som subprosess, arver os.environ) og
    notify.py (samme prosess, leser os.getenv ved hvert kall) automatisk bruker
    riktig bruker – uten å tre cfg gjennom hvert eneste kall. Trygt KUN fordi brukere
    behandles strengt sekvensielt, aldri parallelt/samtidig."""
    env_map = {
        "GARMINTOKENS": cfg.tokenstore,
        "GOLFBOX_USERNAME": cfg.golfbox_username,
        "GOLFBOX_PASSWORD": cfg.golfbox_password,
        "GOLFBOX_MARKER_MEMBERNO": cfg.marker_memberno,
        "GOLFBOX_MARKER_NAME": cfg.marker_name,
        "NOTIFY_EMAIL": cfg.notify_email,
        "NTFY_TOPIC": cfg.ntfy_topic,
        "NTFY_SERVER": cfg.ntfy_server,
        "GOLFBOX_DATA_DIR": str(cfg.data_dir),
    }
    for key, value in env_map.items():
        if value:
            os.environ[key] = str(value)
        else:
            os.environ.pop(key, None)

    # GOLFBOX_USER_ID (telemetri, se _log_attempt i golfbox_post.py): kun satt for
    # EKTE multi-bruker-kjøringer. "local" er ikke en gyldig UUID og ville feilet
    # castingen mot attempts.user_id i Supabase – legacy enkelt-bruker-modus skal
    # fortsatt logge med user_id=NULL, akkurat som før.
    if cfg.user_id != "local":
        os.environ["GOLFBOX_USER_ID"] = cfg.user_id
    else:
        os.environ.pop("GOLFBOX_USER_ID", None)


# Aktiv brukerkonfig for inneværende kjøring. Settes av sync_one_user() før noe annet
# skjer – modul-globalen finnes kun for at log()/load_state()/osv. slipper å ta cfg
# som parameter i hvert eneste kall (se docstring på UserConfig).
CFG: UserConfig = UserConfig()


def log(msg: str) -> None:
    prefix = f"[{CFG.label}]  " if CFG.user_id != "local" else ""
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {prefix}{msg}"
    print(line, flush=True)
    try:
        CFG.log_file.parent.mkdir(parents=True, exist_ok=True)
        with CFG.log_file.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_state() -> dict:
    if CFG.state_file.exists():
        try:
            data = json.loads(CFG.state_file.read_text(encoding="utf-8"))
            data.setdefault("seen", [])
            data.setdefault("posted", [])
            data.setdefault("needs_manual", [])
            data.setdefault("pending", {})  # {rid: antall vente-forsøk} for tee-data
            data.setdefault("garmin_fails", 0)          # påfølgende Garmin-feil
            data.setdefault("garmin_cooldown_until", None)  # ISO: hopp over til da
            return data
        except Exception:
            pass
    return {"seen": [], "posted": [], "needs_manual": [], "pending": {},
            "garmin_fails": 0, "garmin_cooldown_until": None, "_initialized": False}


def save_state(state: dict) -> None:
    CFG.state_file.parent.mkdir(parents=True, exist_ok=True)
    CFG.state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def garmin_summary_ids() -> list[int]:
    """Logg inn med lagret token og hent ID-ene til FERDIGE runder.

    VIKTIG: Garmin synker en runde LIVE mens den spilles (roundInProgress=True), med
    delvis score. En slik runde skal IKKE forsøkes postet – vi venter til du har trykket
    «save round» på klokka (roundInProgress=False). Da den ikke markeres som sett, blir den
    plukket opp automatisk når den er ferdigstilt."""
    client = Garmin()
    client.login(CFG.tokenstore)  # kun token – ingen passord/MFA
    summary = client.get_golf_summary(limit=50)
    ids, skipped = [], 0
    for sc in extract_scorecard_list(summary):
        if sc.get("roundInProgress"):
            skipped += 1
            continue  # runde spilles fortsatt – hopp over til den er lagret/ferdig
        sc_id = get_id(sc)
        if sc_id is not None:
            try:
                ids.append(int(sc_id))
            except (ValueError, TypeError):
                pass
    if skipped:
        log(f"⏭️  Hoppet over {skipped} runde(r) som spilles akkurat nå (roundInProgress).")
    return ids


def persist_state_now(msg: str) -> None:
    """Commit+push state UMIDDELBART (kun i skyen). Slik er en postet runde alltid
    «husket» i repoet, selv om jobben skulle dø før slutt-steget → aldri dobbel-posting.
    Lokalt (utenfor GitHub Actions) er dette en trygg no-op. Best effort – logger ved feil."""
    if not CFG.persist_state_to_git:
        return  # multi-bruker-state lagres i Supabase, ikke git – se MULTIUSER_PLAN.md
    if os.getenv("GITHUB_ACTIONS") != "true":
        return
    try:
        rel_state = str(CFG.state_file.relative_to(PROJECT_DIR))
        subprocess.run(["git", "config", "user.name", "auto-sync"], cwd=str(PROJECT_DIR), check=False)
        subprocess.run(["git", "config", "user.email", "auto-sync@users.noreply.github.com"],
                       cwd=str(PROJECT_DIR), check=False)
        subprocess.run(["git", "add", rel_state], cwd=str(PROJECT_DIR), check=False)
        # noe å committe?
        if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=str(PROJECT_DIR)).returncode != 0:
            subprocess.run(["git", "commit", "-m", msg], cwd=str(PROJECT_DIR), check=False)
            subprocess.run(["git", "pull", "--rebase", "--autostash"], cwd=str(PROJECT_DIR), check=False)
            subprocess.run(["git", "push"], cwd=str(PROJECT_DIR), check=False)
            log(f"   💾 State pushet umiddelbart ({msg}).")
    except Exception as e:
        log(f"   (umiddelbar state-push hoppet over: {e})")


def run(cmd: list[str], extra_env: dict | None = None) -> int:
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(cmd, cwd=str(PROJECT_DIR), env=env).returncode


def round_name(rid: int) -> str:
    """Slå opp banenavn for en runde-ID fra lokal data (for varsler)."""
    try:
        raw = json.loads((CFG.data_dir / "all_rounds.json").read_text(encoding="utf-8"))
        for r in raw.get("runder", []):
            s = r.get("summary", {})
            if s.get("id") == rid:
                return s.get("courseName") or str(rid)
    except Exception:
        pass
    return str(rid)


def sync_one_user(cfg: UserConfig) -> None:
    """Kjør én full synk-syklus for ÉN bruker. I dag kalt med build_legacy_config()
    (deg). En fremtidig multi-bruker-runner kaller denne i en løkke, én UserConfig per
    aktiv bruker fra Supabase – synk-logikken under er allerede generell."""
    global CFG
    CFG = cfg
    _apply_env(cfg)
    log("=== auto_sync start ===")

    state = load_state()

    # Backoff-vakt: fikk vi nylig push-back fra Garmin, hopper vi over til cooldown er
    # ute – slik at vi ALDRI maser videre og forverrer en evt. rate-limit-grense.
    cd = state.get("garmin_cooldown_until")
    if cd:
        try:
            if datetime.now(timezone.utc) < datetime.fromisoformat(cd):
                log(f"⏸️ Garmin-cooldown til {cd}. Hopper over (skåner Garmin). Ferdig.")
                return
        except Exception:
            pass

    try:
        ids = garmin_summary_ids()
    except Exception as e:
        # Garmin presser tilbake (429 / token-problem). Sett eskalerende pause og
        # varsle ved gjentatte feil – i stedet for å prøve igjen om 5 min.
        fails = int(state.get("garmin_fails", 0)) + 1
        wait_min = min(120, 30 * fails)   # 30 → 60 → 90 → 120 min
        until = (datetime.now(timezone.utc) + timedelta(minutes=wait_min)).isoformat()
        state["garmin_fails"] = fails
        state["garmin_cooldown_until"] = until
        save_state(state)
        log(f"❌ Garmin-innlogging/-henting feilet (feil #{fails}): {e}")
        log(f"   ⏸️ Cooldown {wait_min} min (til {until}) for ikke å forverre en grense.")
        if fails == 3:   # varsle én gang når det ser vedvarende ut
            try:
                import notify
                msg = ("Garmin-innlogging har feilet flere ganger på rad. Sannsynligvis "
                       "er tokenet utløpt/revokert – lag et nytt og oppdater "
                       "GARMIN_TOKENS_B64-secret. Roboten tar pauser og maser ikke videre.")
                if notify.is_push_configured():
                    notify._push("Golf-robot: Garmin-innlogging feiler", msg,
                                 tags="warning", priority="high")
                if notify.is_configured():
                    notify.send_email("Golf-robot: Garmin-innlogging feiler",
                                      "Hei!\n\n" + msg + "\n\nMvh, golf-roboten 🏌️")
            except Exception as ne:
                log(f"(kunne ikke varsle om Garmin-feil: {ne})")
        raise SystemExit(2)

    # Suksess → nullstill feilteller/cooldown hvis de var satt.
    if state.get("garmin_fails") or state.get("garmin_cooldown_until"):
        state["garmin_fails"] = 0
        state["garmin_cooldown_until"] = None
        save_state(state)

    log(f"Fant {len(ids)} runder i Garmin-oversikten.")

    # Første kjøring: sett baseline, post ingenting.
    if not state.get("_initialized"):
        state["seen"] = ids
        state["_initialized"] = True
        save_state(state)
        log(f"Baseline satt ({len(ids)} runder markert som sett). Ingen posting første gang.")
        return

    seen = set(state["seen"])
    new_ids = [i for i in ids if i not in seen]
    if not new_ids:
        log("Ingen nye runder. Ferdig.")
        return

    log(f"🆕 {len(new_ids)} ny(e) runde(r): {new_ids}")

    # Oppdater lokal data (henter detaljer for alle runder, inkl. de nye).
    log("Oppdaterer lokal data fra Garmin ...")
    if run([sys.executable, str(FETCH_SCRIPT)]) != 0:
        log("⚠️ fetch_garmin feilet – prøver likevel å poste med eksisterende data.")

    # Post hver nye runde til Golfbox i auto-modus.
    posted_now, review_now, manual_now, notpostable_now = [], [], [], []
    for rid in new_ids:
        name = round_name(rid)
        log(f"→ Sender runde {rid} ({name}) til Golfbox ...")
        _reason_file = CFG.data_dir / "last_reason.txt"
        try:
            _reason_file.unlink()  # nullstill så vi ikke arver forrige rundes grunn
        except Exception:
            pass
        rc = run([sys.executable, str(POST_SCRIPT), str(rid), "--auto"],
                 extra_env={"GOLFBOX_AUTO": "1"})
        try:
            reason = _reason_file.read_text(encoding="utf-8").strip()
        except Exception:
            reason = ""
        if rc in (0, 4):
            state["seen"].append(rid)
            state["posted"].append(rid)
            state["pending"].pop(str(rid), None)
            if rc == 4:
                review_now.append((name, reason or "tee valgt på skjønn"))
                log(f"   ✅ Runde {rid} lagret – men tee usikker, flagget for dobbeltsjekk.")
            else:
                posted_now.append((name, ""))
                log(f"   ✅ Runde {rid} lagret i Golfbox (til godkjennelse).")
            # Persister UMIDDELBART: en postet runde skal aldri kunne postes to ganger,
            # selv om jobben dør før slutt-steget.
            save_state(state)
            persist_state_now(f"auto-sync: postet runde {rid}")
        elif rc == 2:
            # Golfbox-økt utløpt – ingen vits å prøve flere nå. IKKE marker som sett,
            # så den prøves igjen ved neste kjøring etter at du har fornyet økten.
            log(f"   ⏸️ Golfbox-økt utløpt. Stopper. Runde {rid} prøves igjen senere.")
            break
        elif rc == 6:
            # Garmin har ikke fylt inn data ennå (tee/rating ELLER hull-score – begge
            # kommer med forsinkelse rett etter runden). IKKE marker som sett – vent og
            # prøv igjen neste kjøring, opp til et tak. Ingen mail ennå.
            tries = state["pending"].get(str(rid), 0) + 1
            state["pending"][str(rid)] = tries
            if tries >= CFG.max_tee_wait:
                state["seen"].append(rid)
                state["needs_manual"].append(rid)
                state["pending"].pop(str(rid), None)
                manual_now.append((name, reason or "Garmin fylte aldri inn tee/score-data"))
                log(f"   ⧗→⚠️ Runde {rid}: data kom aldri (etter {tries} forsøk). "
                    f"Flagger for manuell fullføring.")
            else:
                log(f"   ⧗ Runde {rid}: venter på Garmin-data (tee/score) "
                    f"(forsøk {tries}/{CFG.max_tee_wait}). Prøver igjen neste kjøring.")
        elif rc == 5:
            # Klubben finnes ikke i GolfBox (privat/utland/ikke-WHS) – ikke leverbar.
            state["seen"].append(rid)
            state["needs_manual"].append(rid)
            state["pending"].pop(str(rid), None)
            notpostable_now.append((name, reason or "klubben finnes ikke i GolfBox"))
            log(f"   ⛔ Runde {rid} – klubben finnes ikke i GolfBox. Kan ikke leveres.")
        else:
            # rc == 3: klubb OK, men bane/tee ikke bekreftet – KAN fullføres i web-appen.
            state["seen"].append(rid)
            state["needs_manual"].append(rid)
            state["pending"].pop(str(rid), None)
            manual_now.append((name, reason or "bane/tee ikke bekreftet"))
            log(f"   ⚠️ Runde {rid} matchet ikke helt (kode {rc}): {reason or '—'}. "
                f"Kan fullføres i web-appen.")

        # Lagre framgang etter HVER runde, så en evt. avbrutt kjøring (timeout midt i en
        # stor batch) aldri fører til at en allerede-postet runde behandles på nytt.
        save_state(state)

    save_state(state)

    # Varsling. E-post KUN ved unntak (som før – suksess-mail ville vært støy).
    # Push til mobil: BÅDE suksess (bekreftelse) OG problemer.
    try:
        import notify
        if (manual_now or review_now or notpostable_now) and notify.is_configured():
            if notify.notify_rounds(manual_now, review_now, posted_now, notpostable_now):
                log(f"📧 E-post sendt ({len(manual_now)} å fullføre, "
                    f"{len(review_now)} å dobbeltsjekke, {len(notpostable_now)} ikke leverbare).")
        if (posted_now or manual_now or review_now or notpostable_now) and notify.is_push_configured():
            if notify.notify_push(manual_now, review_now, posted_now, notpostable_now):
                log(f"📱 Push sendt ({len(posted_now)} lagt inn, "
                    f"{len(manual_now) + len(review_now) + len(notpostable_now)} trenger blikk).")
    except Exception as e:
        log(f"(varsling hoppet over: {e})")

    log("=== auto_sync ferdig ===")


def main() -> None:
    """Entry point for dagens enkelt-bruker-drift (lokalt og i GitHub Actions)."""
    load_dotenv(PROJECT_DIR / ".env")
    sync_one_user(build_legacy_config())


if __name__ == "__main__":
    main()
