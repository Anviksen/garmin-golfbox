#!/usr/bin/env python3
"""
E-postvarsling – si fra når en runde trenger brukerens oppmerksomhet.

Universelt varslings-lag: hver bruker får en e-post når en runde ikke kunne
matches helt automatisk (fullfør på sekunder), eller ble lagret på best-effort tee
(dobbeltsjekk). Slik blir «feil» til «nesten ferdig – bekreft her» i stedet for
stille bortfall.

Config i .env / GitHub-secrets:
    GMAIL_USER=din@gmail.com
    GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx   (Google-app-passord, ikke vanlig passord)
    NOTIFY_EMAIL=mottaker@epost.no            (valgfri – default = GMAIL_USER)
    NTFY_TOPIC=golfbox-xxxxxxxx               (valgfri – push til mobil via ntfy.sh)
    NTFY_SERVER=https://ntfy.sh               (valgfri – default = https://ntfy.sh)

Uten disse er varsling en trygg no-op.

    python3 notify.py            # sender en test-e-post + test-push
"""

from __future__ import annotations

import os
import smtplib
import ssl
import urllib.request
from email.message import EmailMessage
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except Exception:
    pass


def is_configured() -> bool:
    return bool(os.getenv("GMAIL_USER") and os.getenv("GMAIL_APP_PASSWORD"))


def is_push_configured() -> bool:
    return bool(os.getenv("NTFY_TOPIC"))


def _push(title: str, message: str, tags: str = "", priority: str = "default") -> bool:
    """Send én push til mobilen via ntfy.sh. Best effort. Tittelen holdes ASCII
    (HTTP-headere tåler ikke æøå/emoji trygt); meldingskroppen kan ha norske tegn."""
    topic = os.getenv("NTFY_TOPIC")
    if not topic:
        return False
    server = os.getenv("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    headers = {"Title": title, "Priority": priority}
    if tags:
        headers["Tags"] = tags  # emoji via ntfy sine kortkoder, f.eks. "white_check_mark"
    try:
        req = urllib.request.Request(
            f"{server}/{topic}", data=message.encode("utf-8"),
            headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15):
            return True
    except Exception as e:
        print(f"(push: kunne ikke sende – {e})")
        return False


def notify_push(needs_manual: list, review: list, posted: list,
                not_postable: list | None = None) -> bool:
    """Push til mobil: én bekreftelse ved suksess + én ved noe som trenger et blikk."""
    not_postable = not_postable or []
    sent = False
    if posted:
        names = ", ".join(n for n, _ in posted)
        sent = _push("Runde lagt inn i GolfBox",
                     f"✅ {names} – ligger til godkjenning.",
                     tags="golf,white_check_mark") or sent
    problems = []
    if needs_manual:
        problems.append("🔴 Fullfør: " + ", ".join(n for n, _ in needs_manual))
    if review:
        problems.append("🟡 Dobbeltsjekk tee: " + ", ".join(n for n, _ in review))
    if not_postable:
        problems.append("⛔ Kan ikke leveres: " + ", ".join(n for n, _ in not_postable))
    if problems:
        sent = _push("Golf: trenger et blikk", "\n".join(problems),
                     tags="warning", priority="high") or sent
    return sent


def send_email(subject: str, body: str) -> bool:
    """Send en e-post via Gmail SMTP. Best effort – returnerer True ved suksess."""
    user = os.getenv("GMAIL_USER")
    pw = (os.getenv("GMAIL_APP_PASSWORD") or "").replace(" ", "")  # app-passord uten mellomrom
    to = os.getenv("NOTIFY_EMAIL") or user
    if not (user and pw and to):
        return False
    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx, timeout=20) as s:
            s.login(user, pw)
            s.send_message(msg)
        return True
    except Exception as e:
        print(f"(varsling: kunne ikke sende e-post – {e})")
        return False


def notify_rounds(needs_manual: list, review: list, posted: list,
                  not_postable: list | None = None) -> bool:
    """Bygg og send et oppsummerings-varsel. Listene er (navn, grunn)-tupler:
      needs_manual – klubb OK, men bane/tee ikke bekreftet (KAN fullføres i web-appen)
      review       – lagt inn, men tee på skjønn (DOBBELTSJEKK)
      not_postable – klubben finnes ikke i GolfBox (ingen handling mulig)
      posted       – lagt inn automatisk (bare til info)
    Sender kun hvis noe krever/fortjener et blikk."""
    not_postable = not_postable or []
    if not (needs_manual or review or not_postable):
        return False
    lines = []
    if needs_manual:
        lines.append("🔴 Nesten i mål – fullfør i web-appen (åpne dashbordet → "
                     "«Send til Golfbox» på runden; den fyller inn alt, du bekrefter "
                     "bane/tee og lagrer):")
        for name, why in needs_manual:
            lines.append(f"   • {name}" + (f"  ({why})" if why else ""))
        lines.append("")
    if review:
        lines.append("🟡 Lagt inn i GolfBox, men tee valgt på skjønn – DOBBELTSJEKK "
                     "før du godkjenner:")
        for name, why in review:
            lines.append(f"   • {name}" + (f"  ({why})" if why else ""))
        lines.append("")
    if not_postable:
        lines.append("⛔ Kan ikke leveres – disse banene finnes ikke i GolfBox "
                     "(privat bane / utland / ikke WHS). Ingenting du kan gjøre:")
        for name, why in not_postable:
            lines.append(f"   • {name}" + (f"  ({why})" if why else ""))
        lines.append("")
    if posted:
        lines.append(f"✅ La automatisk inn {len(posted)} runde(r) (ligger til "
                     f"godkjennelse i GolfBox): " + ", ".join(n for n, _ in posted))
    body = ("Hei!\n\nOppdatering fra Garmin → GolfBox:\n\n"
            + "\n".join(lines)
            + "\n\nMvh, din golf-robot 🏌️")
    n = len(needs_manual) + len(review)
    if n:
        subject = f"Golf: {n} runde(r) trenger et blikk"
    else:
        subject = f"Golf: {len(not_postable)} runde(r) kan ikke leveres"
    return send_email(subject, body)


if __name__ == "__main__":
    if is_configured():
        ok = send_email("Test – Garmin→GolfBox varsling",
                        "Dette er en testmelding. Varslingen virker! 🏌️")
        print("✅ Test-e-post sendt!" if ok else "❌ Kunne ikke sende (sjekk app-passord).")
    else:
        print("ℹ️ E-post ikke konfigurert (GMAIL_USER/GMAIL_APP_PASSWORD).")
    if is_push_configured():
        ok = _push("Golf-robot test", "📱 Push virker! Du får varsel her fra nå.",
                   tags="golf")
        print("✅ Test-push sendt!" if ok else "❌ Push feilet (sjekk NTFY_TOPIC).")
    else:
        print("ℹ️ Push ikke konfigurert (NTFY_TOPIC mangler).")
