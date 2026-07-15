#!/usr/bin/env python3
"""Always-on worker for AI summary auto-send jobs (PythonAnywhere).

Run this as an Always-on task on PythonAnywhere:
  python3 /home/idynkydnk/stats/ai_auto_send_daemon.py

The task must have the same env vars as the web app (MAIL_*, GEMINI_API_KEY, etc.).
"""
import os
import sys
import time
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv()
except (ImportError, ModuleNotFoundError):
    pass

import ai_auto_send_jobs as jobs

POLL_SECONDS = 5
LOG_PATH = os.path.join(ROOT, 'ai_auto_send_daemon.log')


def _log(msg):
    line = f'{time.strftime("%Y-%m-%d %H:%M:%S")} {msg}\n'
    try:
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(line)
    except OSError:
        pass
    print(line, end='', flush=True)


def _process_job(job):
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
    )
    if result.get('success'):
        subject = result.get('subject') or 'Vball Summary'
        share_url = result.get('share_url') or ''
        summary = f'Published "{subject}"'
        if share_url:
            summary += f' — {share_url}'
        jobs.complete_job(
            job['id'], True,
            emails_sent=0,
            result_summary=summary,
        )
        _log(f'job #{job["id"]} completed: {summary}')
    else:
        err = (result.get('error') or 'Unknown error')[:500]
        jobs.complete_job(job['id'], False, error=err)
        _log(f'job #{job["id"]} failed: {err}')


def main():
    jobs.init_ai_auto_send_jobs_db()
    jobs.reset_stale_running_jobs()
    _log('AI auto-send daemon started')

    if not os.environ.get('GEMINI_API_KEY'):
        _log('WARNING: GEMINI_API_KEY is not set — jobs will fail')

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
