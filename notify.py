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

Uten disse er varsling en trygg no-op.

    python3 notify.py            # sender en test-e-post
"""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except Exception:
    pass


def is_configured() -> bool:
    return bool(os.getenv("GMAIL_USER") and os.getenv("GMAIL_APP_PASSWORD"))


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
    if not is_configured():
        print("❌ Ikke konfigurert. Sett GMAIL_USER og GMAIL_APP_PASSWORD i .env.")
    else:
        ok = send_email("Test – Garmin→GolfBox varsling",
                        "Dette er en testmelding. Varslingen virker! 🏌️")
        print("✅ Test-e-post sendt!" if ok else "❌ Kunne ikke sende (sjekk app-passord).")
