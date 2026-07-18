#!/usr/bin/env python3
"""
Multi-bruker-runner – henter aktive brukere fra Supabase og kjører
`auto_sync.sync_one_user()` for HVER, STRENGT SEKVENSIELT.

Dette er et NYTT, separat script. Det erstatter IKKE dagens enkelt-bruker-
workflow (.github/workflows/auto-sync.yml kjører fortsatt
`build_legacy_config()` som før, helt uendret). Kjør dette manuelt inntil
multi-bruker-fasen er bevist trygg – se MULTIUSER_PLAN.md for veien videre til
en egen skyjobb.

For hver aktiv bruker:
  1. Dekrypter creds/token/økt fra `users`-raden (kun i minnet, aldri på disk
     ukryptert utenom i en midlertidig mappe som slettes uansett utfall).
  2. Materialiser til en isolert temp-mappe: Garmin-tokenstore (tar+base64,
     samme format som GARMIN_TOKENS_B64-secreten), `golfbox_state.json`, og en
     `posted.json` rekonstruert fra `user_round_state` + `garmin_fails`/
     `garmin_cooldown_until` fra brukerraden.
  3. Kall `auto_sync.sync_one_user(cfg)`.
  4. Uansett utfall (også ved SystemExit eller uventet feil): les tilbake
     eventuelt oppdaterte tokens/økt/state, krypter, skriv til Supabase.
  5. Rydd temp-mappa. Én brukers feil stopper ALDRI de andre.

VIKTIG – les før første kjøring:
  - STRENGT sekvensielt. Aldri asyncio/threading/multiprocessing her – se
    UserConfig-docstring i auto_sync.py for hvorfor (Garmin-fingerprinting-
    risiko, og os.environ er prosess-globalt/deles mellom "samtidige" kall).
  - Sjekk at GOLFBOX_AUTO_SUBMIT ikke er satt til "1" i miljøet ditt før første
    test (`echo $GOLFBOX_AUTO_SUBMIT` skal være tomt). Er den satt, fyller
    OG LAGRER golfbox_post.py ekte runder – for en testbruker som peker på en
    ekte, allerede aktiv GolfBox-konto (f.eks. din egen testrad) risikerer det
    å lage en DUPLIKAT innsending ved siden av det den vanlige skyjobben
    allerede har postet. Se MULTIUSER_PLAN.md for en trygg test-fremgangsmåte.

Kjøres slik:
    python3 run_all_users.py
"""

from __future__ import annotations

import base64
import io
import json
import tarfile
import tempfile
from pathlib import Path

import auto_sync
import user_crypto
import user_store


def _log(label: str, msg: str) -> None:
    print(f"[{label}] {msg}", flush=True)


def _materialize_garmin_tokens(b64_tar: str | None, temp_home: Path) -> str:
    """Pakk ut Garmin-tokenstore i en midlertidig 'hjemme'-mappe. Returnerer
    stien tokenstore-mappen faktisk havner på – tar-arkivet er laget med
    `tar czf - -C ~ .garminconnect`, så innholdet ligger under
    <temp_home>/.garminconnect etter utpakking, akkurat som ~/.garminconnect
    lokalt/i skyen."""
    tokendir = temp_home / ".garminconnect"
    if b64_tar:
        temp_home.mkdir(parents=True, exist_ok=True)
        raw = base64.b64decode(b64_tar)
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tf:
            tf.extractall(temp_home)
    return str(tokendir)


def _dematerialize_garmin_tokens(temp_home: Path) -> str | None:
    """Pakk tokenstore-mappa sammen igjen til samme base64-tar-format som
    inn – garminconnect kan ha friske/roterte tokens på disk etter en kjøring."""
    tokendir = temp_home / ".garminconnect"
    if not tokendir.exists():
        return None
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        tf.add(tokendir, arcname=".garminconnect")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _materialize_golfbox_session(b64_session: str | None, dest_path: Path) -> None:
    if not b64_session:
        return
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(base64.b64decode(b64_session))


def _dematerialize_golfbox_session(path: Path) -> str | None:
    if not path.exists():
        return None
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _db_rows_to_state(rows: list, user_row: dict) -> dict:
    """Bygg posted.json-formatet `auto_sync.sync_one_user()` forventer, fra
    user_round_state-rader + garmin_fails/cooldown fra users-raden.
    `_initialized=False` for en helt ny bruker (ingen rader ennå) – da setter
    sync_one_user en baseline første kjøring i stedet for å poste alt på én
    gang, akkurat som i enkelt-bruker-flyten."""
    state = {
        "seen": [], "posted": [], "needs_manual": [], "pending": {},
        "garmin_fails": user_row.get("garmin_fails") or 0,
        "garmin_cooldown_until": user_row.get("garmin_cooldown_until"),
        "_initialized": bool(rows),
    }
    for r in rows:
        rid = r["garmin_round_id"]
        status = r["status"]
        if status == "pending":
            state["pending"][str(rid)] = r.get("attempts", 0)
            continue
        state["seen"].append(rid)
        if status == "posted":
            state["posted"].append(rid)
        elif status == "needs_manual":
            state["needs_manual"].append(rid)
    return state


def _state_to_db_rows(user_id: str, state: dict) -> list:
    """Motsatt vei: bygg user_round_state-rader fra en posted.json-state.
    Rekkefølgen betyr noe – posted/needs_manual overstyrer plain 'seen' for
    samme runde-id (en runde er ALDRI i to av disse samtidig i praksis, men
    denne rekkefølgen er trygg uansett siden senere skriv vinner)."""
    rows: dict = {}
    for rid in state.get("seen", []):
        rows[rid] = {"user_id": user_id, "garmin_round_id": rid, "status": "seen", "attempts": 0}
    for rid in state.get("posted", []):
        rows[rid] = {"user_id": user_id, "garmin_round_id": rid, "status": "posted", "attempts": 0}
    for rid in state.get("needs_manual", []):
        rows[rid] = {"user_id": user_id, "garmin_round_id": rid, "status": "needs_manual", "attempts": 0}
    for rid_str, tries in state.get("pending", {}).items():
        rid = int(rid_str)
        rows[rid] = {"user_id": user_id, "garmin_round_id": rid, "status": "pending", "attempts": tries}
    return list(rows.values())


def run_one_user(user_row: dict) -> None:
    label = user_row.get("label") or str(user_row.get("id"))
    user_id = user_row["id"]
    _log(label, "=== starter ===")

    garmin_tokens_b64 = user_crypto.decrypt(user_row.get("garmin_tokens_enc"))
    golfbox_username = user_crypto.decrypt(user_row.get("golfbox_username_enc"))
    golfbox_password = user_crypto.decrypt(user_row.get("golfbox_password_enc"))
    golfbox_session_b64 = user_crypto.decrypt(user_row.get("golfbox_session_enc"))

    if not garmin_tokens_b64:
        _log(label, "⏭️  Ingen Garmin-token registrert ennå – hopper over.")
        return

    with tempfile.TemporaryDirectory(prefix=f"golfbox_{user_id}_") as tmp:
        tmp_path = Path(tmp)
        home_dir = tmp_path / "home"
        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        tokenstore = _materialize_garmin_tokens(garmin_tokens_b64, home_dir)
        _materialize_golfbox_session(golfbox_session_b64, data_dir / "golfbox_state.json")

        round_state_rows = user_store.get_round_state(user_id)
        state = _db_rows_to_state(round_state_rows, user_row)
        (data_dir / "posted.json").write_text(json.dumps(state), encoding="utf-8")

        cfg = auto_sync.UserConfig(
            user_id=user_id,
            label=label,
            tokenstore=tokenstore,
            golfbox_username=golfbox_username,
            golfbox_password=golfbox_password,
            marker_memberno=user_row.get("golfbox_marker_memberno"),
            marker_name=user_row.get("golfbox_marker_name"),
            notify_email=user_row.get("notify_email"),
            ntfy_topic=user_row.get("ntfy_topic"),
            ntfy_server=user_row.get("ntfy_server"),
            data_dir=data_dir,
            persist_state_to_git=False,  # multi-bruker-state -> Supabase, ikke git
        )

        try:
            auto_sync.sync_one_user(cfg)
        except SystemExit as e:
            _log(label, f"(avsluttet med kode {e.code} – normal flyt for enkelte utfall)")
        except Exception as e:
            _log(label, f"❌ Uventet feil under kjøring: {e}")

        # Uansett utfall: synkroniser det som endret seg tilbake til Supabase,
        # slik at neste kjøring starter der denne slapp.
        try:
            final_state = json.loads((data_dir / "posted.json").read_text(encoding="utf-8"))
        except Exception:
            final_state = state  # ingenting nytt å lagre – bruk det vi startet med

        rows = _state_to_db_rows(user_id, final_state)
        if rows:
            user_store.upsert_round_state(rows)

        updates = {
            "garmin_fails": final_state.get("garmin_fails", 0),
            "garmin_cooldown_until": final_state.get("garmin_cooldown_until"),
        }
        new_tokens = _dematerialize_garmin_tokens(home_dir)
        if new_tokens and new_tokens != garmin_tokens_b64:
            updates["garmin_tokens_enc"] = user_crypto.encrypt(new_tokens)
        new_session = _dematerialize_golfbox_session(data_dir / "golfbox_state.json")
        if new_session and new_session != golfbox_session_b64:
            updates["golfbox_session_enc"] = user_crypto.encrypt(new_session)
        user_store.update_user(user_id, updates)

    _log(label, "=== ferdig ===")


def main() -> None:
    if not user_store.is_configured():
        print("❌ SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY mangler i .env.")
        raise SystemExit(1)
    if not user_crypto.is_configured():
        print("❌ ENCRYPTION_KEY mangler i .env.")
        raise SystemExit(1)

    users = user_store.get_active_users()
    print(f"Fant {len(users)} aktiv(e) bruker(e).")
    for user_row in users:
        try:
            run_one_user(user_row)
        except Exception as e:
            # Siste skanse: selv en feil i selve orkestreringen (ikke bare i
            # sync_one_user) skal aldri stoppe de andre brukerne.
            _log(user_row.get("label", "?"), f"❌ Uventet feil (hopper til neste bruker): {e}")


if __name__ == "__main__":
    main()
