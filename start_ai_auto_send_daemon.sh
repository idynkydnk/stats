#!/bin/bash
# Start the AI auto-send queue worker (for PythonAnywhere Always-on task).
#
# Always-on tasks do NOT inherit WSGI env vars. Put exports in the same Command
# box, then run this script. Example (one line):
#
#   export OPENAI_API_KEY='sk-...' && export SITE_BASE_URL='https://idynkydnk.pythonanywhere.com' && bash "$HOME/stats/start_ai_auto_send_daemon.sh"
#
# Prefer $HOME/stats (username case varies). Copy key values from your WSGI file:
#   /var/www/idynkydnk_pythonanywhere_com_wsgi.py

set -euo pipefail

# Resolve project dir from this script's location (not a hardcoded home path).
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# Fallback if someone copied only the .py next to a broken wrapper.
if [[ ! -f ai_auto_send_daemon.py ]]; then
  echo "ai_auto_send_daemon.py not found in $ROOT" >&2
  exit 1
fi

exec python3 ai_auto_send_daemon.py
