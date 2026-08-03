#!/bin/bash
# Start the AI auto-send queue worker (for PythonAnywhere Always-on task).
#
# Always-on Command should be ONLY this (one short line — no API keys here):
#
#   bash "$HOME/stats/start_ai_auto_send_daemon.sh"
#
# Secrets are loaded from, in order:
#   1. always_on_env.sh  (optional; server-only, gitignored)
#   2. .env              (optional; server-only, gitignored)
#   3. WSGI file         (Python fallback in ai_auto_send_daemon.py)
#
# Do NOT paste OPENAI_API_KEY into the Always-on Command box — long keys get
# truncated/mangled there, which leaves the task stuck on "Starting".

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ ! -f ai_auto_send_daemon.py ]]; then
  echo "ai_auto_send_daemon.py not found in $ROOT" >&2
  exit 1
fi

# Optional server-only env files (never commit these).
if [[ -f always_on_env.sh ]]; then
  # shellcheck disable=SC1091
  source ./always_on_env.sh
fi
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source ./.env
  set +a
fi

# Sensible default for share links if nothing else set it.
export SITE_BASE_URL="${SITE_BASE_URL:-https://idynkydnk.pythonanywhere.com}"

exec python3 ai_auto_send_daemon.py
