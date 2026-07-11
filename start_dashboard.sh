#!/usr/bin/env bash
# Starter golf-dashboardet lokalt.
# Kjør:  ./start_dashboard.sh   (eller: bash start_dashboard.sh)

cd "$(dirname "$0")" || exit 1

# Aktiver venv hvis den finnes
if [ -d ".venv" ]; then
  source .venv/bin/activate
fi

echo "⛳ Starter dashboard på http://localhost:8000"
echo "   (Trykk Ctrl-C for å stoppe.)"

# Åpne nettleseren automatisk etter et par sekunder (macOS)
( sleep 2 && open http://localhost:8000 ) &

uvicorn backend.main:app --port 8000
