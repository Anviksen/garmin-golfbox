#!/usr/bin/env python3
"""
Liten klient for å trigge GitHub Actions-workflows manuelt fra admin-
dashbordet ("Kjør nå"-knappene). Samme mekanisme som cron-job.org allerede
bruker for å trigge auto-sync.yml (workflow_dispatch), bare kalt fra Python
i stedet for en ekstern cron-tjeneste.

Config i .env (IKKE i git – samme prinsipp som alle andre secrets her):
    GITHUB_PAT=github_pat_...     (fine-grained, KUN "Actions: Read and write"
                                    på dette ene repoet – minste privilegium,
                                    samme type token cron-job.org bruker)
    GITHUB_REPO=Anviksen/garmin-golfbox   (valgfritt, dette er default)

Uten GITHUB_PAT satt: is_configured() er False, og admin-dashbordet skjuler
"Kjør nå"-knappene i stedet for å vise en knapp som uansett ville feilet.
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

GITHUB_PAT = os.getenv("GITHUB_PAT", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "Anviksen/garmin-golfbox")

# Hvilke workflow-filer admin-dashbordet lov til å trigge – en bevisst
# allow-list (ikke fritekst workflow-navn fra brukerinput) som ekstra sikring.
ALLOWED_WORKFLOWS = {
    "auto-sync.yml": "Enkelt-bruker-sync (Garmin til Golfbox)",
    "multiuser-sync.yml": "Multi-bruker-sync (Garmin til Golfbox)",
    "process-signups.yml": "Behandle nye påmeldinger (onboarding)",
}


def is_configured() -> bool:
    return bool(GITHUB_PAT)


def trigger_workflow(workflow_file: str, ref: str = "main") -> tuple[bool, str]:
    """Trigg en workflow_dispatch-kjøring. Returnerer (ok, melding)."""
    if not is_configured():
        return False, "GITHUB_PAT er ikke satt i .env."
    if workflow_file not in ALLOWED_WORKFLOWS:
        return False, f"«{workflow_file}» er ikke i tillatt-lista (se ALLOWED_WORKFLOWS)."
    url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/{workflow_file}/dispatches"
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps({"ref": ref}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {GITHUB_PAT}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            if r.status == 204:
                return True, f"«{ALLOWED_WORKFLOWS[workflow_file]}» ble trigget."
            return False, f"Uventet svar (HTTP {r.status})."
    except urllib.error.HTTPError as e:
        return False, f"GitHub svarte med feil (HTTP {e.code}) – sjekk at GITHUB_PAT er gyldig."
    except Exception as e:
        return False, f"Kunne ikke trigge workflow – {e}"


if __name__ == "__main__":
    import sys
    if not is_configured():
        print("GITHUB_PAT er ikke satt i .env.")
    elif len(sys.argv) > 1:
        ok, msg = trigger_workflow(sys.argv[1])
        print(("✅ " if ok else "❌ ") + msg)
    else:
        print("Bruk: python3 github_actions.py <workflow-fil>")
        print("Tilgjengelige:", ", ".join(ALLOWED_WORKFLOWS))
