#!/bin/bash
# Start the AI auto-send queue worker (for PythonAnywhere Always-on task).
#
# Always-on Command — use a plain absolute path (no $HOME, no quotes):
#
#   bash /home/Idynkydnk/stats/start_ai_auto_send_daemon.sh
#
# Or skip this wrapper:
#
#   python3 -u /home/Idynkydnk/stats/ai_auto_send_daemon.py
#
# Secrets are loaded from, in order:
#   1. always_on_env.sh  (optional; server-only, gitignored)
#   2. .env              (optional; server-only, gitignored)
#   3. WSGI file         (Python fallback in ai_auto_send_daemon.py)

set -uo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT" || exit 1

if [[ ! -f ai_auto_send_daemon.py ]]; then
  echo "ai_auto_send_daemon.py not found in $ROOT" >&2
  exit 1
fi

# Optional server-only env files (never commit these). Failures are non-fatal.
if [[ -f always_on_env.sh ]]; then
  # shellcheck disable=SC1091
  source ./always_on_env.sh || echo "WARNING: always_on_env.sh failed to source" >&2
fi
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source ./.env || echo "WARNING: .env failed to source" >&2
  set +a
fi

export SITE_BASE_URL="${SITE_BASE_URL:-https://idynkydnk.pythonanywhere.com}"

# Prefer project venv if present (web app deps often live there).
PYTHON=python3
for candidate in \
  "$ROOT/venv/bin/python" \
  "$ROOT/.venv/bin/python" \
  "$HOME/.virtualenvs/stats/bin/python" \
  "$HOME/.virtualenvs/venv/bin/python"
do
  if [[ -x "$candidate" ]]; then
    PYTHON="$candidate"
    break
  fi
done

echo "Starting AI daemon with: $PYTHON (cwd=$ROOT)" >&2
exec "$PYTHON" -u ai_auto_send_daemon.py
