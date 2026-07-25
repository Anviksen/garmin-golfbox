#!/usr/bin/env python3
"""
Admin-dashbord: én statisk HTML-rapport over hele multi-bruker-systemet –
hvor mange bruker det, hvordan går det, og hvor bør du bruke neste kodetime.

Bevisst IKKE en live nettside (se chat 25. juli 2026): dashbordet leser med
`SUPABASE_SERVICE_ROLE_KEY` (samme kraftige nøkkel som omgår alle RLS-sperrer
for `users`/`user_round_state`/`pending_signups`) – den skal ALDRI havne i
noe som kjører i en nettleser eller et offentlig repo. Dette scriptet kjøres
lokalt på Mac-en, genererer én HTML-fil, og åpner den i standard nettleser.
Ingen hemmeligheter (passord, tokens, service-role-nøkkelen selv) havner i
selve HTML-fila – kun aggregert, ikke-sensitiv statistikk.

Bruk:
    python3 admin_dashboard.py
"""

from __future__ import annotations

import webbrowser
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import central_registry
import foreign_course_registry
import telemetry
import user_store

OUT_FILE = Path(__file__).resolve().parent / "data" / "admin_dashboard.html"


# --- Ren aggregering (testbar uten nettverk) --------------------------------

def aggregate_user_rounds(round_states: list, users: list) -> list:
    """Per-bruker rundestatistikk. `round_states` = alle user_round_state-
    rader (alle brukere), `users` = fra user_store.list_users_admin().
    Returnerer én rad per bruker, sortert med flest runder øverst."""
    labels = {u["id"]: u for u in users}
    per_user = {}
    for rs in round_states:
        uid = rs.get("user_id")
        if uid not in per_user:
            u = labels.get(uid, {})
            per_user[uid] = {
                "label": u.get("label", uid), "active": u.get("active", True),
                "garmin_fails": u.get("garmin_fails", 0),
                "garmin_cooldown_until": u.get("garmin_cooldown_until"),
                "seen": 0, "posted": 0, "needs_manual": 0, "pending": 0,
            }
        status = rs.get("status", "seen")
        if status in per_user[uid]:
            per_user[uid][status] += 1

    rows = []
    for uid, stats in per_user.items():
        resolved = stats["posted"] + stats["needs_manual"]
        stats["total"] = stats["seen"] + stats["posted"] + stats["needs_manual"] + stats["pending"]
        stats["success_rate"] = round(100 * stats["posted"] / resolved) if resolved else None
        rows.append(stats)

    # Brukere med konto men INGEN runder ennå (nettopp onboardet) – ta med som 0-rad.
    for uid, u in labels.items():
        if uid not in per_user:
            rows.append({
                "label": u.get("label", uid), "active": u.get("active", True),
                "garmin_fails": u.get("garmin_fails", 0),
                "garmin_cooldown_until": u.get("garmin_cooldown_until"),
                "seen": 0, "posted": 0, "needs_manual": 0, "pending": 0,
                "total": 0, "success_rate": None,
            })

    rows.sort(key=lambda r: -r["total"])
    return rows


def aggregate_signup_funnel(signups: list) -> dict:
    """Onboarding-trakt fra pending_signups (ALLE statuser). `signups` skal
    komme fra user_store.list_pending_signups_admin() – har ALDRI passord."""
    counts = Counter(s.get("status", "pending") for s in signups)
    errors = Counter(
        (s.get("error_message") or "").strip()
        for s in signups if s.get("status") == "failed" and s.get("error_message")
    )
    return {
        "total": len(signups),
        "pending": counts.get("pending", 0),
        "processing": counts.get("processing", 0),
        "failed": counts.get("failed", 0),
        "top_errors": errors.most_common(10),
    }


def aggregate_foreign_courses(entries: dict) -> dict:
    """Grupper den verifiserte bane-cachen (foreign_course_registry) per land.
    Returnerer {land: [banenavn, ...]}, sortert land-vis."""
    by_country = {}
    for entry in entries.values():
        country = entry.get("country") or "(ukjent)"
        by_country.setdefault(country, []).append(entry.get("courseName", "?"))
    return {c: sorted(names) for c, names in sorted(by_country.items())}


# --- Henting + rendering -----------------------------------------------------

def _fmt_dt(iso: str | None) -> str:
    if not iso:
        return "–"
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%d.%m.%Y %H:%M")
    except Exception:
        return iso[:16]


def _esc(s) -> str:
    return (str(s) if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_html(user_rows: list, funnel: dict, course_outcomes: dict, foreign_by_country: dict) -> str:
    total_users = len(user_rows)
    active_users = sum(1 for r in user_rows if r["active"])
    total_rounds = sum(r["total"] for r in user_rows)
    total_posted = sum(r["posted"] for r in user_rows)
    total_needs_manual = sum(r["needs_manual"] for r in user_rows)
    global_rate = round(100 * total_posted / (total_posted + total_needs_manual)) \
        if (total_posted + total_needs_manual) else None

    failing = sorted(
        [(k, a) for k, a in course_outcomes.items() if not a["last_ok"]],
        key=lambda x: -x[1]["n"],
    )

    def _user_row(r: dict) -> str:
        rate = f"{r['success_rate']}%" if r["success_rate"] is not None else "–"
        fails = f"⚠️ {r['garmin_fails']}x" if r["garmin_fails"] else "–"
        active = "✅" if r["active"] else "⏸️"
        return (
            f"<tr><td>{_esc(r['label'])}</td><td>{active}</td>"
            f"<td>{r['total']}</td><td>{r['posted']}</td><td>{r['needs_manual']}</td>"
            f"<td>{r['pending']}</td><td>{rate}</td><td>{fails}</td></tr>"
        )

    user_table_rows = "".join(_user_row(r) for r in user_rows) \
        or "<tr><td colspan=8>Ingen brukere ennå.</td></tr>"

    failing_rows = "".join(
        f"<tr><td>{_esc(k)}</td><td>{a['n']}</td><td>{_esc(a['last_reason'])[:120]}</td></tr>"
        for k, a in failing[:20]
    ) or "<tr><td colspan=3>Ingen baner i feilkøen akkurat nå 🎉</td></tr>"

    error_rows = "".join(
        f"<tr><td>{n}×</td><td>{_esc(msg)}</td></tr>" for msg, n in funnel["top_errors"]
    ) or "<tr><td colspan=2>Ingen mislykkede påmeldinger.</td></tr>"

    foreign_rows = "".join(
        f"<tr><td>{_esc(country)}</td><td>{len(names)}</td><td>{_esc(', '.join(names))}</td></tr>"
        for country, names in foreign_by_country.items()
    ) or "<tr><td colspan=3>Ingen utenlandske baner bekreftet ennå.</td></tr>"

    generated = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")

    return f"""<!DOCTYPE html>
<html lang="no"><head><meta charset="utf-8">
<title>Garmin → GolfBox — admin-dashbord</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; background:#0f1420; color:#e6e9ef; margin:0; padding:32px; }}
  h1 {{ font-size:22px; margin-bottom:4px; }}
  .sub {{ color:#8a92a6; font-size:13px; margin-bottom:28px; }}
  .kpis {{ display:flex; gap:16px; flex-wrap:wrap; margin-bottom:32px; }}
  .kpi {{ background:#181f30; border-radius:10px; padding:16px 20px; min-width:140px; }}
  .kpi .n {{ font-size:26px; font-weight:700; }}
  .kpi .l {{ font-size:12px; color:#8a92a6; margin-top:2px; }}
  section {{ margin-bottom:36px; }}
  h2 {{ font-size:15px; color:#c7cbe0; border-bottom:1px solid #262c3d; padding-bottom:8px; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th, td {{ text-align:left; padding:7px 10px; border-bottom:1px solid #1e2432; }}
  th {{ color:#8a92a6; font-weight:600; font-size:11px; text-transform:uppercase; }}
  tr:hover td {{ background:#151b29; }}
</style></head>
<body>
  <h1>🏌️ Garmin → GolfBox — admin-dashbord</h1>
  <div class="sub">Generert {generated} · kjør <code>python3 admin_dashboard.py</code> på nytt for en fersk versjon</div>

  <div class="kpis">
    <div class="kpi"><div class="n">{active_users}/{total_users}</div><div class="l">Aktive brukere</div></div>
    <div class="kpi"><div class="n">{total_rounds}</div><div class="l">Runder totalt</div></div>
    <div class="kpi"><div class="n">{total_posted}</div><div class="l">Postet automatisk</div></div>
    <div class="kpi"><div class="n">{f"{global_rate}%" if global_rate is not None else "–"}</div><div class="l">Suksessrate</div></div>
    <div class="kpi"><div class="n">{funnel['pending']}</div><div class="l">Ventende påmeldinger</div></div>
  </div>

  <section>
    <h2>👥 Brukere</h2>
    <table>
      <tr><th>Navn</th><th>Aktiv</th><th>Runder</th><th>Postet</th><th>Trenger hjelp</th><th>Venter</th><th>Suksessrate</th><th>Garmin-feil</th></tr>
      {user_table_rows}
    </table>
  </section>

  <section>
    <h2>🔴 Feilkø (baner som ikke går gjennom – prioritert etter hyppighet)</h2>
    <table>
      <tr><th>Bane</th><th>Forsøk</th><th>Siste grunn</th></tr>
      {failing_rows}
    </table>
  </section>

  <section>
    <h2>📝 Onboarding-trakt</h2>
    <div class="kpis">
      <div class="kpi"><div class="n">{funnel['total']}</div><div class="l">Totalt sendt inn</div></div>
      <div class="kpi"><div class="n">{funnel['pending']}</div><div class="l">Venter på behandling</div></div>
      <div class="kpi"><div class="n">{funnel['failed']}</div><div class="l">Feilet (trenger deg)</div></div>
    </div>
    <table>
      <tr><th>Antall</th><th>Feilårsak</th></tr>
      {error_rows}
    </table>
  </section>

  <section>
    <h2>🌍 Bekreftede utenlandske baner (delt cache)</h2>
    <table>
      <tr><th>Land</th><th>Antall baner</th><th>Baner</th></tr>
      {foreign_rows}
    </table>
  </section>
</body></html>"""


def main() -> None:
    if not user_store.is_configured():
        print("❌ SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY mangler. Se MULTIUSER_PLAN.md.")
        raise SystemExit(1)

    print("Henter data fra Supabase ...")
    users = user_store.list_users_admin()
    round_states = user_store.get_all_round_states()
    signups = user_store.list_pending_signups_admin()
    attempts = central_registry.fetch_attempts() if central_registry.is_configured() else []

    # Bekreftet bane-cache: bruk lokal fil (alltid tilgjengelig) i stedet for
    # å kreve nettverk til sentralbasen for akkurat denne biten.
    foreign_entries = foreign_course_registry.load_db()

    user_rows = aggregate_user_rounds(round_states, users)
    funnel = aggregate_signup_funnel(signups)
    course_outcomes = telemetry.aggregate_course_outcomes(attempts)
    foreign_by_country = aggregate_foreign_courses(foreign_entries)

    html = render_html(user_rows, funnel, course_outcomes, foreign_by_country)
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(html, encoding="utf-8")
    print(f"✅ Dashbord skrevet til {OUT_FILE}")

    try:
        webbrowser.open(f"file://{OUT_FILE}")
    except Exception:
        print("(kunne ikke åpne nettleser automatisk – åpne fila manuelt)")


if __name__ == "__main__":
    main()
