#!/usr/bin/env python3
"""
Sentral base-klient (Supabase) – den delte bane-databasen.

Lar alle brukere lese fra og bidra til SAMME base: når én bruker lærer en ny bane,
sendes den opp hit og forbedrer matchingen for alle (nettverkseffekten).

Konfigureres via .env:
    SUPABASE_URL=https://xxxx.supabase.co
    SUPABASE_ANON_KEY=eyJ...
    (valgfritt) SUPABASE_TABLE=courses

Er den ikke konfigurert, er alle funksjoner trygge no-ops – lokal drift fortsetter.
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
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY", "")
TABLE = os.getenv("SUPABASE_TABLE", "courses")

_FIELDS = ("lat", "lon", "club", "course", "tee", "garmin_name", "country", "source")


def is_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def _headers(extra: dict | None = None) -> dict:
    h = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


def fetch_all() -> list:
    """Hent alle baner fra sentralbasen. Tom liste hvis ikke konfigurert / feil."""
    if not is_configured():
        return []
    url = f"{SUPABASE_URL}/rest/v1/{TABLE}?select={','.join(_FIELDS)}"
    try:
        req = urllib.request.Request(url, headers=_headers())
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"(sentralbase: kunne ikke lese – {e})")
        return []


def contribute(entry: dict) -> bool:
    """Send én bane opp til sentralbasen (best effort)."""
    if not is_configured() or not entry.get("club"):
        return False
    if entry.get("lat") is None or entry.get("lon") is None:
        return False
    row = {k: entry.get(k) for k in _FIELDS}
    row["source"] = row.get("source") or "learned"
    row["country"] = row.get("country") or "no"
    try:
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/{TABLE}",
            data=json.dumps(row).encode("utf-8"),
            headers=_headers({"Prefer": "return=minimal"}),
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30):
            return True
    except Exception as e:
        print(f"(sentralbase: kunne ikke bidra – {e})")
        return False


_ATTEMPT_FIELDS = (
    "round_id", "garmin_course", "club", "club_ok", "course", "course_ok",
    "tee", "tee_ok", "tee_uncertain", "posted", "reason", "country", "user_id",
)


def fetch_attempts(limit: int = 2000) -> list:
    """Hent telemetri-loggen (attempts) – nyeste først."""
    if not is_configured():
        return []
    url = (f"{SUPABASE_URL}/rest/v1/attempts?select=*"
           f"&order=created_at.desc&limit={limit}")
    try:
        req = urllib.request.Request(url, headers=_headers())
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"(telemetri: kunne ikke lese – {e})")
        return []


def log_attempt(data: dict) -> bool:
    """Telemetri: logg utfallet av ett poste-forsøk til `attempts`-tabellen.
    Datadrevet feilkø – best effort, feiler stille hvis ikke konfigurert."""
    if not is_configured():
        return False
    row = {k: data.get(k) for k in _ATTEMPT_FIELDS}
    row["country"] = row.get("country") or "no"
    try:
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/attempts",
            data=json.dumps(row).encode("utf-8"),
            headers=_headers({"Prefer": "return=minimal"}),
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15):
            return True
    except Exception:
        return False


if __name__ == "__main__":
    if not is_configured():
        print("Sentralbasen er IKKE konfigurert. Sett SUPABASE_URL og SUPABASE_ANON_KEY i .env.")
    else:
        rows = fetch_all()
        print(f"Sentralbasen ({SUPABASE_URL}) har {len(rows)} baner.")
