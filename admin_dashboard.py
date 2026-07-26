#!/usr/bin/env python3
"""
Admin-dashbord: lokal server med oversikt over hele multi-bruker-systemet –
hvor mange bruker det, hvordan går det, hvor bør du bruke neste kodetime, og
noen trygge handlingsknapper (prøv påmelding på nytt, av/på-bryter for
brukere, send velkomst-e-post på nytt, trigg en skyjobb manuelt).

Bevisst en LOKAL server, ikke en hostet nettside (se chat 25. juli 2026):
dashbordet leser med `SUPABASE_SERVICE_ROLE_KEY` (samme kraftige nøkkel som
omgår alle RLS-sperrer for `users`/`user_round_state`/`pending_signups`) –
den skal ALDRI havne i noe klientside-JS eller et offentlig repo. Ved å
holde alt server-side i denne Python-prosessen (kun bundet til 127.0.0.1 –
ikke synlig for andre på nettverket ditt) kan vi likevel ha ekte,
klikkbare knapper: nettleseren snakker bare med DENNE lokale serveren, som
gjør de faktiske Supabase/GitHub-kallene selv.

Bruk:
    python3 admin_dashboard.py
    (åpner http://127.0.0.1:8877/ automatisk i nettleseren, Ctrl+C for å stoppe)
"""

from __future__ import annotations

import http.server
import json as _json
import webbrowser
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import central_registry
import foreign_course_registry
import github_actions
import provision_user
import telemetry
import user_store

PORT = 8877


# --- Ren aggregering (testbar uten nettverk) --------------------------------

def filter_since(rows: list, since: str | None, field: str = "created_at") -> list:
    """Behold kun rader fra og med `since` (en 'YYYY-MM-DD'-streng). `since`
    er None/tom -> ingen filtrering (vis alt). Brukt til dashbordets
    dato-filter – IKKE en sletting, bare en VISNING (se chat 26. juli 2026:
    mye reell test-/utviklingsdata før lansering skal ikke se ut som en høy
    feilrate i produksjon, uten å faktisk slette den ekte historikken)."""
    if not since:
        return rows
    try:
        cutoff = datetime.fromisoformat(since).replace(tzinfo=timezone.utc)
    except ValueError:
        return rows
    out = []
    for r in rows:
        ts = r.get(field)
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt >= cutoff:
            out.append(r)
    return out


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
                "id": uid, "label": u.get("label", uid), "active": u.get("active", True),
                "garmin_fails": u.get("garmin_fails", 0),
                "garmin_cooldown_until": u.get("garmin_cooldown_until"),
                "created_at": u.get("created_at"),
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
                "id": uid, "label": u.get("label", uid), "active": u.get("active", True),
                "garmin_fails": u.get("garmin_fails", 0),
                "garmin_cooldown_until": u.get("garmin_cooldown_until"),
                "created_at": u.get("created_at"),
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
    failed_rows = [s for s in signups if s.get("status") == "failed"]
    return {
        "total": len(signups),
        "pending": counts.get("pending", 0),
        "processing": counts.get("processing", 0),
        "failed": counts.get("failed", 0),
        "failed_rows": failed_rows,
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


def aggregate_recent_activity(attempts: list, limit: int = 20) -> list:
    """De siste N forsøkene på tvers av ALLE brukere (attempts er allerede
    nyeste-først fra central_registry.fetch_attempts())."""
    return attempts[:limit]


def build_alerts(user_rows: list, funnel: dict, failing: list) -> list:
    """«Trenger din oppmerksomhet nå»-lista – det admin-dashbordet finnes
    for. Ren funksjon (testbar), tar allerede-aggregerte data inn."""
    alerts = []
    now = datetime.now(timezone.utc)
    for r in user_rows:
        if r.get("garmin_cooldown_until"):
            try:
                until = datetime.fromisoformat(r["garmin_cooldown_until"].replace("Z", "+00:00"))
                if until > now:
                    alerts.append(f"🥶 {r['label']} er i Garmin-cooldown til {until.strftime('%d.%m %H:%M')}.")
            except Exception:
                pass
        if r.get("garmin_fails", 0) >= 3:
            alerts.append(f"⚠️ {r['label']} har {r['garmin_fails']} Garmin-innloggingsfeil på rad.")
    if funnel["failed"]:
        alerts.append(f"📝 {funnel['failed']} påmelding(er) trenger manuell oppfølging.")
    if failing:
        alerts.append(f"🔴 {len(failing)} bane(r) i feilkøen ({failing[0][0]} flest, {failing[0][1]['n']}×).")
    return alerts


# --- Rendering ---------------------------------------------------------------

def _esc(s) -> str:
    return (str(s) if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _fmt_dt(iso: str | None) -> str:
    if not iso:
        return "–"
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%d.%m.%Y %H:%M")
    except Exception:
        return str(iso)[:16]


def render_html(user_rows: list, funnel: dict, course_outcomes: dict,
                 foreign_by_country: dict, recent: list, since: str | None = None) -> str:
    total_users = len(user_rows)
    active_users = sum(1 for r in user_rows if r["active"])
    total_posted = sum(r["posted"] for r in user_rows)
    total_needs_manual = sum(r["needs_manual"] for r in user_rows)
    global_rate = round(100 * total_posted / (total_posted + total_needs_manual)) \
        if (total_posted + total_needs_manual) else None

    failing = sorted(
        [(k, a) for k, a in course_outcomes.items() if not a["last_ok"]],
        key=lambda x: -x[1]["n"],
    )
    alerts = build_alerts(user_rows, funnel, failing)
    needs_attention = len(alerts)

    # --- Brukere: én kompakt "Runder"-celle i stedet for fire kolonner ------
    def _round_summary(r: dict) -> str:
        if r["total"] == 0:
            return '<span class="muted">Ingen runder ennå</span>'
        parts = [f"{r['posted']} postet"]
        if r["needs_manual"]:
            parts.append(f"{r['needs_manual']} trenger hjelp")
        if r["pending"]:
            parts.append(f"{r['pending']} venter")
        return f"<strong>{r['total']}</strong><div class='muted small'>{' · '.join(parts)}</div>"

    def _user_row(r: dict) -> str:
        rate = f"{r['success_rate']}%" if r["success_rate"] is not None else "–"
        badge = '<span class="pill ok">aktiv</span>' if r["active"] else '<span class="pill off">pauset</span>'
        if r["garmin_fails"]:
            badge += f'<div class="muted small">⚠️ {r["garmin_fails"]}× Garmin-feil</div>'
        toggle_label = "Pause" if r["active"] else "Aktiver"
        return (
            f"<tr><td>{_esc(r['label'])}<div class='muted small'>Ble med {_fmt_dt(r.get('created_at'))}</div></td>"
            f"<td>{badge}</td>"
            f"<td>{_round_summary(r)}</td>"
            f"<td>{rate}</td>"
            f"<td class='actions'>"
            f"<button class='btn small' onclick=\"toggleUser('{r['id']}', {str(not r['active']).lower()})\">{toggle_label}</button> "
            f"<button class='btn small ghost' onclick=\"resendWelcome('{r['id']}')\">Velkomst-e-post</button>"
            f"</td></tr>"
        )

    user_table_rows = "".join(_user_row(r) for r in user_rows) \
        or "<tr><td colspan=5>Ingen brukere ennå.</td></tr>"

    failing_rows = "".join(
        f"<tr><td>{_esc(k)}</td><td>{a['n']}</td><td>{_esc(a['last_reason'])[:110]}</td>"
        f"<td><code>{_esc(a.get('round_id', ''))}</code></td></tr>"
        for k, a in failing[:20]
    ) or "<tr><td colspan=4>Ingen baner i feilkøen akkurat nå 🎉</td></tr>"

    def _signup_row(s: dict) -> str:
        return (
            f"<tr><td>{_esc(s.get('label'))}</td><td>{_fmt_dt(s.get('created_at'))}</td>"
            f"<td>{_esc(s.get('error_message'))[:100]}</td>"
            f"<td class='actions'><button class='btn small' onclick=\"retrySignup('{s['id']}')\">Prøv på nytt</button></td></tr>"
        )
    failed_signup_rows = "".join(_signup_row(s) for s in funnel["failed_rows"]) \
        or "<tr><td colspan=4>Ingen mislykkede påmeldinger.</td></tr>"

    foreign_rows = "".join(
        f"<tr><td>{_esc(country)}</td><td>{len(names)}</td><td>{_esc(', '.join(names))}</td></tr>"
        for country, names in foreign_by_country.items()
    ) or "<tr><td colspan=3>Ingen utenlandske baner bekreftet ennå.</td></tr>"

    recent_rows = "".join(
        f"<tr><td>{_fmt_dt(a.get('created_at'))}</td><td>{_esc(a.get('garmin_course'))}</td>"
        f"<td>{'✅' if a.get('posted') else '—'}</td><td>{_esc(a.get('reason'))[:90]}</td></tr>"
        for a in recent
    ) or "<tr><td colspan=4>Ingen aktivitet registrert ennå.</td></tr>"

    alerts_html = (
        "".join(f'<div class="alert">{_esc(a)}</div>' for a in alerts)
        if alerts else '<div class="alert ok">✅ Ingen ting trenger oppmerksomhet akkurat nå. Alt kjører som det skal.</div>'
    )

    workflow_buttons = "".join(
        f'<button class="btn" onclick="triggerWorkflow(\'{fname}\')">▶ {label}</button>'
        for fname, label in github_actions.ALLOWED_WORKFLOWS.items()
    ) if github_actions.is_configured() else (
        '<div class="muted">Sett GITHUB_PAT i .env for å kunne trigge skyjobber herfra '
        '(se WEBHOOK_ONBOARDING.md).</div>'
    )

    generated = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")

    return f"""<!DOCTYPE html>
<html lang="no"><head><meta charset="utf-8">
<title>Garmin → GolfBox — admin</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, "SF Pro Text", Segoe UI, Roboto, sans-serif;
          background:#0b0f18; color:#e6e9ef; margin:0; padding:0 0 60px; }}
  header {{ position:sticky; top:0; z-index:10; background:#0d1220ee; backdrop-filter:blur(6px);
            border-bottom:1px solid #1a2233; padding:16px 32px 0; }}
  h1 {{ font-size:17px; margin:0 0 2px; display:flex; align-items:center; gap:8px; font-weight:600; }}
  .sub {{ color:#69708a; font-size:11.5px; margin-bottom:14px; }}
  .sub code {{ background:#181f30; padding:1px 6px; border-radius:4px; }}
  .chips {{ display:flex; gap:10px; margin-bottom:14px; }}
  .chip {{ display:flex; align-items:baseline; gap:6px; background:#141a29; border:1px solid #1f2638;
           border-radius:9px; padding:7px 13px; font-size:12px; }}
  .chip b {{ font-size:15px; }}
  .chip.warn {{ border-color:#4a2e22; }}
  .chip.warn b {{ color:#f0a878; }}
  .chip.good b {{ color:#7fd99a; }}
  nav {{ display:flex; gap:4px; }}
  nav button {{ background:none; border:none; color:#7a8299; font-size:13px; padding:10px 16px;
                cursor:pointer; border-bottom:2px solid transparent; font-family:inherit; }}
  nav button:hover {{ color:#c7cbe0; }}
  nav button.active {{ color:#e6e9ef; border-bottom-color:#3d6fe0; font-weight:600; }}
  main {{ padding:24px 32px; }}
  .tab {{ display:none; }}
  .tab.active {{ display:block; }}
  section {{ margin-bottom:30px; }}
  h2 {{ font-size:13px; color:#c7cbe0; margin:0 0 12px; font-weight:600; }}
  table {{ width:100%; border-collapse:collapse; font-size:12.5px; }}
  th, td {{ text-align:left; padding:9px 10px; border-bottom:1px solid #171d2b; vertical-align:middle; }}
  th {{ color:#7a8299; font-weight:600; font-size:10.5px; text-transform:uppercase; letter-spacing:.03em; }}
  tr:hover td {{ background:#111726; }}
  code {{ background:#181f30; padding:1px 6px; border-radius:4px; font-size:11.5px; }}
  .pill {{ display:inline-block; padding:2px 9px; border-radius:20px; font-size:11px; font-weight:600; }}
  .pill.ok {{ background:#132818; color:#7fd99a; }}
  .pill.off {{ background:#241a17; color:#e0a071; }}
  .btn {{ background:#1e2942; color:#dfe4f2; border:1px solid #2c3a5c; border-radius:7px;
          padding:6px 13px; font-size:12.5px; cursor:pointer; }}
  .btn:hover {{ background:#28365a; }}
  .btn.small {{ padding:4px 10px; font-size:11.5px; }}
  .btn.ghost {{ background:transparent; border-color:#2c3346; color:#9aa3ba; }}
  .actions {{ white-space:nowrap; }}
  .muted {{ color:#7a8299; }}
  .muted.small {{ font-size:11px; margin-top:2px; }}
  .alerts {{ display:flex; flex-direction:column; gap:6px; }}
  .alert {{ background:#241a17; border:1px solid #4a2e22; color:#f0c4a8; border-radius:8px;
            padding:10px 14px; font-size:13px; }}
  .alert.ok {{ background:#132018; border-color:#1e3a28; color:#8fd9ab; }}
  .toast {{ position:fixed; bottom:20px; right:20px; background:#1e2942; border:1px solid #2c3a5c;
            border-radius:8px; padding:12px 18px; font-size:13px; display:none; max-width:340px; }}
  .toast.show {{ display:block; }}
  .controls-row {{ display:flex; gap:10px; flex-wrap:wrap; }}
  .date-filter {{ display:flex; align-items:center; gap:7px; margin-left:auto; font-size:12px; }}
  .date-filter input[type=date] {{ background:#141a29; border:1px solid #1f2638; color:#e6e9ef;
            border-radius:7px; padding:5px 9px; font-size:12px; font-family:inherit; }}
</style></head>
<body>
<header>
  <h1>🏌️ Garmin → GolfBox</h1>
  <div class="sub">Generert {generated} · {"viser fra " + _esc(since) if since else "viser ALL historikk"} · oppdater siden for ferske tall</div>
  <div class="chips">
    <div class="chip {'warn' if needs_attention else 'good'}"><b>{needs_attention}</b> trenger oppmerksomhet</div>
    <div class="chip"><b>{f"{global_rate}%" if global_rate is not None else "–"}</b> suksessrate</div>
    <div class="chip"><b>{active_users}/{total_users}</b> aktive brukere</div>
    <div class="date-filter">
      <span class="muted">Viser fra</span>
      <input type="date" id="since-input" value="{_esc(since) if since else ''}">
      <button class="btn small" onclick="applySinceFilter()">Bruk</button>
      {'<button class="btn small ghost" onclick="showAllData()">Vis alt</button>' if since else ''}
    </div>
  </div>
  <nav>
    <button class="tab-btn active" data-tab="oversikt" onclick="showTab('oversikt')">Oversikt</button>
    <button class="tab-btn" data-tab="brukere" onclick="showTab('brukere')">Brukere</button>
    <button class="tab-btn" data-tab="feilsok" onclick="showTab('feilsok')">Feilsøk</button>
    <button class="tab-btn" data-tab="onboarding" onclick="showTab('onboarding')">Onboarding</button>
    <button class="tab-btn" data-tab="baner" onclick="showTab('baner')">Baner</button>
    <button class="tab-btn" data-tab="kontroller" onclick="showTab('kontroller')">Kontroller</button>
  </nav>
</header>

<main>
  <div class="tab active" id="tab-oversikt">
    <section>
      <h2>Trenger din oppmerksomhet</h2>
      <div class="alerts">{alerts_html}</div>
    </section>
  </div>

  <div class="tab" id="tab-brukere">
    <section>
      <h2>👥 Brukere</h2>
      <table>
        <tr><th>Navn</th><th>Status</th><th>Runder</th><th>Suksessrate</th><th></th></tr>
        {user_table_rows}
      </table>
    </section>
  </div>

  <div class="tab" id="tab-feilsok">
    <section>
      <h2>🔴 Feilkø (baner som ikke går gjennom – prioritert etter hyppighet)</h2>
      <table>
        <tr><th>Bane</th><th>Forsøk</th><th>Siste grunn</th><th>Debug</th></tr>
        {failing_rows}
      </table>
    </section>
    <section>
      <h2>🕒 Siste aktivitet</h2>
      <table>
        <tr><th>Tidspunkt</th><th>Bane</th><th>Postet</th><th>Grunn</th></tr>
        {recent_rows}
      </table>
    </section>
  </div>

  <div class="tab" id="tab-onboarding">
    <section>
      <h2>📝 Onboarding</h2>
      <div class="chips">
        <div class="chip"><b>{funnel['total']}</b> sendt inn totalt</div>
        <div class="chip"><b>{funnel['pending']}</b> venter på behandling</div>
        <div class="chip {'warn' if funnel['failed'] else 'good'}"><b>{funnel['failed']}</b> feilet</div>
      </div>
      <table>
        <tr><th>Navn</th><th>Sendt inn</th><th>Feilårsak</th><th></th></tr>
        {failed_signup_rows}
      </table>
    </section>
  </div>

  <div class="tab" id="tab-baner">
    <section>
      <h2>🌍 Bekreftede utenlandske baner (delt cache)</h2>
      <table>
        <tr><th>Land</th><th>Antall baner</th><th>Baner</th></tr>
        {foreign_rows}
      </table>
    </section>
  </div>

  <div class="tab" id="tab-kontroller">
    <section>
      <h2>🎛 Kjør en skyjobb nå (utenom tidsplan)</h2>
      <div class="controls-row">{workflow_buttons}</div>
    </section>
  </div>
</main>

  <div class="toast" id="toast"></div>

<script>
function showTab(name) {{
  document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  document.querySelector('.tab-btn[data-tab="' + name + '"]').classList.add('active');
  sessionStorage.setItem('activeTab', name);
}}
(function() {{
  const last = sessionStorage.getItem('activeTab');
  if (last) showTab(last);
}})();
function toast(msg) {{
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 4000);
}}
async function post(path, body) {{
  try {{
    const r = await fetch(path, {{ method: 'POST', headers: {{'Content-Type':'application/json'}}, body: JSON.stringify(body) }});
    const j = await r.json();
    toast(j.message || (j.ok ? 'OK' : 'Feilet'));
    if (j.ok) setTimeout(() => location.reload(), 900);
  }} catch (e) {{ toast('Nettverksfeil: ' + e); }}
}}
function retrySignup(id) {{ post('/api/retry-signup', {{id: id}}); }}
function resendWelcome(id) {{ post('/api/resend-welcome', {{id: id}}); }}
function toggleUser(id, active) {{
  if (!active && !confirm('Sette brukeren på pause? Runder deres postes ikke lenger automatisk.')) return;
  post('/api/toggle-user', {{id: id, active: active}});
}}
function triggerWorkflow(name) {{
  if (!confirm('Kjøre "' + name + '" nå, utenom vanlig tidsplan?')) return;
  post('/api/trigger-workflow', {{workflow: name}});
}}
function applySinceFilter() {{
  const val = document.getElementById('since-input').value;
  window.location.href = '/?since=' + (val || 'all');
}}
function showAllData() {{ window.location.href = '/?since=all'; }}
</script>
</body></html>"""


def build_dashboard_html(since: str | None) -> str:
    """Hent ALT fra Supabase + lokal fil, filtrer på dato, aggreger, render.
    Kalles på hver GET / – alltid ferske tall, ingen egen cache-logikk å
    holde styr på.

    `since`: 'YYYY-MM-DD' -> vis kun runder/aktivitet/påmeldinger FRA OG MED
    den datoen (ren VISNING, se filter_since() – sletter ingenting). None ->
    vis alt, uansett alder (brukes av "Vis alt"-knappen)."""
    users = user_store.list_users_admin()
    # user_round_state har `updated_at`, IKKE `created_at` (se
    # supabase_multiuser_schema.sql) - feil feltnavn her ville stille
    # filtrert bort ALLE runder uansett dato, fanget av test_filter_since.
    round_states = filter_since(user_store.get_all_round_states(), since, field="updated_at")
    signups = filter_since(user_store.list_pending_signups_admin(), since)
    attempts = filter_since(
        central_registry.fetch_attempts() if central_registry.is_configured() else [], since
    )
    foreign_entries = foreign_course_registry.load_db()

    user_rows = aggregate_user_rounds(round_states, users)
    funnel = aggregate_signup_funnel(signups)
    course_outcomes = telemetry.aggregate_course_outcomes(attempts)
    foreign_by_country = aggregate_foreign_courses(foreign_entries)
    recent = aggregate_recent_activity(attempts)

    return render_html(user_rows, funnel, course_outcomes, foreign_by_country, recent, since)


# --- Lokal server -------------------------------------------------------------

class _Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, code: int, content_type: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, ok: bool, message: str) -> None:
        self._send(200, "application/json", _json.dumps({"ok": ok, "message": message}).encode("utf-8"))

    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler sin navnekonvensjon)
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            qs = parse_qs(parsed.query)
            raw_since = qs.get("since", [None])[0]
            if raw_since is None:
                # Ingen ?since= i det hele tatt (første besøk) -> standard er
                # "i dag", se chat 26. juli 2026 (mye reell test-/utviklings-
                # data fra før lansering skal ikke se ut som produksjonstall).
                since = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            elif raw_since == "all":
                since = None
            else:
                since = raw_since
            try:
                html = build_dashboard_html(since)
                self._send(200, "text/html; charset=utf-8", html.encode("utf-8"))
            except Exception as e:
                self._send(500, "text/plain; charset=utf-8", f"Feil ved bygging av dashbord: {e}".encode("utf-8"))
        else:
            self._send(404, "text/plain", b"Not found")

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = _json.loads(raw or b"{}")
        except Exception:
            payload = {}

        try:
            if self.path == "/api/retry-signup":
                ok = user_store.reset_pending_signup(payload.get("id", ""))
                self._json(ok, "Nullstilt – prøves igjen ved neste kjøring av onboarding-jobben."
                           if ok else "Kunne ikke nullstille – se terminalen.")
            elif self.path == "/api/toggle-user":
                ok = user_store.set_user_active(payload.get("id", ""), bool(payload.get("active")))
                self._json(ok, "Oppdatert." if ok else "Kunne ikke oppdatere – se terminalen.")
            elif self.path == "/api/resend-welcome":
                u = user_store.get_user_contact(payload.get("id", ""))
                if not u:
                    self._json(False, "Fant ikke brukeren.")
                else:
                    provision_user._send_welcome_email(
                        u.get("label", ""), u.get("notify_email"), u.get("ntfy_topic")
                    )
                    self._json(True, f"Velkomst-e-post forsøkt sendt til {u.get('label', '')}.")
            elif self.path == "/api/trigger-workflow":
                ok, msg = github_actions.trigger_workflow(payload.get("workflow", ""))
                self._json(ok, msg)
            else:
                self._send(404, "application/json", b'{"ok": false, "message": "ukjent endepunkt"}')
        except Exception as e:
            self._json(False, f"Uventet feil: {e}")

    def log_message(self, fmt: str, *args) -> None:  # litt renere terminal-output
        print(f"  [{self.address_string()}] {fmt % args}")


def main() -> None:
    if not user_store.is_configured():
        print("❌ SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY mangler. Se MULTIUSER_PLAN.md.")
        raise SystemExit(1)

    url = f"http://127.0.0.1:{PORT}/"
    httpd = http.server.HTTPServer(("127.0.0.1", PORT), _Handler)  # kun localhost - ikke synlig på nettverket
    print(f"🖥  Admin-dashbord kjører på {url}  (Ctrl+C for å stoppe)")
    if not github_actions.is_configured():
        print("   ℹ️  GITHUB_PAT ikke satt – «Kjør nå»-knappene er skjult. Se WEBHOOK_ONBOARDING.md.")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStoppet.")


if __name__ == "__main__":
    main()
