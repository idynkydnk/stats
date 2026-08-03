#!/usr/bin/env python3
"""Always-on worker for AI summary / flyer jobs (PythonAnywhere).

Always-on Command (plain absolute path — no $HOME, no quotes, no API keys):

  bash /home/Idynkydnk/stats/start_ai_auto_send_daemon.sh

Or:

  python3 -u /home/Idynkydnk/stats/ai_auto_send_daemon.py

Env loading order:
  1. Process env / always_on_env.sh / .env (via start script + dotenv)
  2. PythonAnywhere WSGI file (same secrets as the web app)
"""
import os
import re
import sys
import time
import traceback

# Print before any project imports so Always-on logs show life even if imports fail.
print(f'{time.strftime("%Y-%m-%d %H:%M:%S")} daemon boot python={sys.version.split()[0]} argv={sys.argv!r}', flush=True)

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
print(f'{time.strftime("%Y-%m-%d %H:%M:%S")} daemon cwd={os.getcwd()}', flush=True)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, '.env'))
except (ImportError, ModuleNotFoundError):
    pass

try:
    import ai_auto_send_jobs as jobs
except Exception:
    print(f'{time.strftime("%Y-%m-%d %H:%M:%S")} FATAL import ai_auto_send_jobs:\n{traceback.format_exc()}', flush=True)
    raise

POLL_SECONDS = 5
LOG_PATH = os.path.join(ROOT, 'ai_auto_send_daemon.log')
_WSGI_ENV_RE = re.compile(
    r"""os\.environ\[\s*['\"]([A-Z0-9_]+)['\"]\s*\]\s*=\s*['\"]([^'\"]*)['\"]"""
)


def _log(msg):
    line = f'{time.strftime("%Y-%m-%d %H:%M:%S")} {msg}\n'
    try:
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(line)
    except OSError:
        pass
    print(line, end='', flush=True)


def _wsgi_candidate_paths():
    explicit = (os.environ.get('WSGI_ENV_FILE') or '').strip()
    paths = []
    if explicit:
        paths.append(explicit)
    paths.append('/var/www/idynkydnk_pythonanywhere_com_wsgi.py')
    home = os.path.expanduser('~')
    if home and home != '~':
        user = os.path.basename(home.rstrip('/'))
        if user:
            paths.append(f'/var/www/{user.lower()}_pythonanywhere_com_wsgi.py')
            paths.append(f'/var/www/{user}_pythonanywhere_com_wsgi.py')
    # Dedupe while preserving order
    seen = set()
    out = []
    for path in paths:
        if path and path not in seen:
            seen.add(path)
            out.append(path)
    return out


def _load_missing_env_from_wsgi():
    """Copy unset keys from the PA WSGI file so Always-on matches the web app."""
    loaded_from = None
    loaded_keys = []
    for path in _wsgi_candidate_paths():
        try:
            with open(path, encoding='utf-8') as f:
                text = f.read()
        except OSError:
            continue
        for key, value in _WSGI_ENV_RE.findall(text):
            if key in os.environ and str(os.environ.get(key, '')).strip():
                continue
            os.environ[key] = value
            loaded_keys.append(key)
        loaded_from = path
        break
    if loaded_from and loaded_keys:
        _log(f'Loaded {len(loaded_keys)} env vars from {loaded_from}')
    elif loaded_from:
        _log(f'Checked WSGI env at {loaded_from} (no missing keys to load)')
    return loaded_from


def _process_job(job):
    job_type = (job.get('job_type') or 'recap').strip() or 'recap'

    if job_type == 'flyer':
        from stats import run_flyer_job

        payload = job.get('payload') or {}
        players = payload.get('players') or []
        _log(
            f'processing flyer job #{job["id"]} user={job["username"]} '
            f'{job.get("game_type")} players={len(players)}'
        )
        result = run_flyer_job(username=job['username'], payload=payload)
        if result.get('success'):
            share_url = result.get('share_url') or ''
            share_id = result.get('share_id') or ''
            summary = 'Published flyer'
            if share_url:
                summary += f' — {share_url}'
            jobs.complete_job(
                job['id'], True,
                emails_sent=0,
                result_summary=summary,
                share_id=share_id,
            )
            _log(f'job #{job["id"]} completed: {summary}')
        else:
            err = (result.get('error') or 'Unknown error')[:500]
            jobs.complete_job(job['id'], False, error=err)
            _log(f'job #{job["id"]} failed: {err}')
        return

    from stats import run_ai_auto_send_job

    _log(
        f'processing job #{job["id"]} user={job["username"]} '
        f'{job["game_type"]} games={len(job["game_ids"])} style={job["prompt_style"]}'
    )
    result = run_ai_auto_send_job(
        username=job['username'],
        game_ids=job['game_ids'],
        game_type=job['game_type'],
        prompt_style=job['prompt_style'],
        custom_prompt=job.get('custom_prompt') or '',
        image_mode=job.get('image_mode') or 'none',
        image_details=job.get('image_details') or '',
        illustration_players=job.get('illustration_players') or [],
    )
    if result.get('success'):
        subject = result.get('subject') or 'Vball Summary'
        share_url = result.get('share_url') or ''
        share_id = result.get('share_id') or ''
        summary = f'Published "{subject}"'
        if share_url:
            summary += f' — {share_url}'
        jobs.complete_job(
            job['id'], True,
            emails_sent=0,
            result_summary=summary,
            share_id=share_id,
        )
        _log(f'job #{job["id"]} completed: {summary}')
    else:
        err = (result.get('error') or 'Unknown error')[:500]
        jobs.complete_job(job['id'], False, error=err)
        _log(f'job #{job["id"]} failed: {err}')


def main():
    os.environ.setdefault('SITE_BASE_URL', 'https://idynkydnk.pythonanywhere.com')
    _load_missing_env_from_wsgi()

    jobs.init_ai_auto_send_jobs_db()
    jobs.reset_stale_running_jobs()
    _log(f'AI auto-send daemon started (cwd={os.getcwd()})')

    if not (os.environ.get('OPENAI_API_KEY') or os.environ.get('GEMINI_API_KEY')):
        _log('WARNING: OPENAI_API_KEY / GEMINI_API_KEY not set — jobs will fail')
    else:
        provider = 'OPENAI_API_KEY' if os.environ.get('OPENAI_API_KEY') else 'GEMINI_API_KEY'
        _log(f'AI provider key present: {provider}')

    while True:
        jobs.touch_daemon_heartbeat()
        try:
            job = jobs.claim_next_pending_job()
            if job:
                try:
                    _process_job(job)
                except Exception:
                    err = traceback.format_exc()[-500:]
                    jobs.complete_job(job['id'], False, error=err)
                    _log(f'job #{job["id"]} crashed:\n{err}')
            else:
                time.sleep(POLL_SECONDS)
        except Exception:
            _log(f'daemon loop error:\n{traceback.format_exc()[-800:]}')
            time.sleep(POLL_SECONDS)


if __name__ == '__main__':
    main()
