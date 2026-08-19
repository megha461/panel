#!/usr/bin/env bash
# Runs the engine API and the web app together.
# API on 8040, web on 5193 — every lower port is already claimed by another
# project in ~/.claude/launch.json.
set -euo pipefail
cd "$(dirname "$0")"

.venv/bin/python -m uvicorn panel.api.app:app --port 8040 --reload &
API_PID=$!
trap 'kill "$API_PID" 2>/dev/null || true' EXIT INT TERM

cd web
exec npm run dev
