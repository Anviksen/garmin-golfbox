#!/usr/bin/env python3
"""
Service-role-klient for multi-bruker-tabellene (`users`, `user_round_state`) i
Supabase.

ADSKILT fra central_registry.py med vilje: den bruker den offentlige anon-nøkkelen
for den delte bane-basen/telemetrien (courses/attempts – trygt åpne, ingen
persondata). `users`/`user_round_state` er derimot låst med RLS PÅ og INGEN
policies (se supabase_multiuser_schema.sql) – kun SUPABASE_SERVICE_ROLE_KEY
kommer til. Bruk ALDRI den nøkkelen i noe som kan havne i en nettleser, logg,
eller offentlig kode.

Config i .env / GitHub-secrets:
    SUPABASE_URL=https://xxxx.supabase.co             (samme som for courses/attempts)
    SUPABASE_SERVICE_ROLE_KEY=...                      (Project Settings -> API Keys
                                                         i Supabase – IKKE anon-nøkkelen)

Merk: denne modulen krypterer INGENTING selv – den flytter bare ferdig-krypterte
rader til/fra Supabase. Krypter/dekrypter med user_crypto.py FØR/ETTER kall hit.
"""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except Exception:
    pass

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


def is_configured() -> bool:
    return bool(SUPABASE_URL and SERVICE_KEY)


def _headers(extra: dict | None = None) -> dict:
    h = {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


def create_user(row: dict) -> dict | None:
    """Sett inn én ny brukerrad. `row` skal ha *_enc-feltene allerede kryptert
    (se user_crypto.py/provision_user.py) – denne funksjonen krypterer
    INGENTING selv. Returnerer den innsatte raden (inkl. generert id) ved
    suksess, None ved feil (logger årsak, kaster ikke)."""
    if not is_configured():
        print("❌ Service-role-tilgang er ikke satt opp "
              "(SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY i .env).")
        return None
    try:
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/users",
            data=json.dumps(row).encode("utf-8"),
            headers=_headers({"Prefer": "return=representation"}),
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            result = json.loads(r.read().decode("utf-8"))
            return result[0] if isinstance(result, list) and result else None
    except Exception as e:
        print(f"❌ Kunne ikke opprette bruker – {e}")
        return None


def list_users(active_only: bool = False) -> list:
    """Hent brukere UTEN å dekryptere noe (kun rå metadata) – til oversikt/debug."""
    if not is_configured():
        return []
    url = f"{SUPABASE_URL}/rest/v1/users?select=id,label,active,created_at"
    if active_only:
        url += "&active=eq.true"
    try:
        req = urllib.request.Request(url, headers=_headers())
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"(kunne ikke liste brukere – {e})")
        return []


def get_active_users() -> list:
    """Hent FULLE rader (inkl. *_enc-felt) for alle aktive brukere. KUN for
    runneren (run_all_users.py) – dekrypter aldri disse feltene noe annet sted
    enn i minnet under én kjøring, og skriv dem aldri til disk eller logg."""
    if not is_configured():
        return []
    url = f"{SUPABASE_URL}/rest/v1/users?select=*&active=eq.true&order=id.asc"
    try:
        req = urllib.request.Request(url, headers=_headers())
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"(kunne ikke hente aktive brukere – {e})")
        return []


def update_user(user_id: str, fields: dict) -> bool:
    """Oppdater én eller flere kolonner på én bruker (f.eks. friske
    tokens/økt etter en kjøring, eller garmin_fails/garmin_cooldown_until).
    `fields` skal ha *_enc-verdier allerede kryptert – krypterer ingenting selv."""
    if not is_configured() or not fields:
        return False
    try:
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/users?id=eq.{user_id}",
            data=json.dumps(fields).encode("utf-8"),
            headers=_headers({"Prefer": "return=minimal"}),
            method="PATCH",
        )
        with urllib.request.urlopen(req, timeout=30):
            return True
    except Exception as e:
        print(f"(kunne ikke oppdatere bruker {user_id} – {e})")
        return False


def get_round_state(user_id: str) -> list:
    """Hent alle user_round_state-rader for én bruker."""
    if not is_configured():
        return []
    url = f"{SUPABASE_URL}/rest/v1/user_round_state?select=*&user_id=eq.{user_id}"
    try:
        req = urllib.request.Request(url, headers=_headers())
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"(kunne ikke hente rundetilstand for {user_id} – {e})")
        return []


def upsert_round_state(rows: list) -> bool:
    """Sett inn/oppdater user_round_state-rader – upsert på (user_id,
    garmin_round_id), som er tabellens primærnøkkel (se
    supabase_multiuser_schema.sql)."""
    if not is_configured() or not rows:
        return False
    try:
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/user_round_state",
            data=json.dumps(rows).encode("utf-8"),
            headers=_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30):
            return True
    except Exception as e:
        print(f"(kunne ikke lagre rundetilstand – {e})")
        return False


if __name__ == "__main__":
    if not is_configured():
        print("Ikke konfigurert. Sett SUPABASE_URL og SUPABASE_SERVICE_ROLE_KEY i .env "
              "(se MULTIUSER_PLAN.md).")
    else:
        users = list_users()
        print(f"{len(users)} bruker(e) i basen:")
        for u in users:
            status = "aktiv" if u.get("active") else "inaktiv"
            print(f"  • {u.get('label')}  ({status})  id={u.get('id')}")
