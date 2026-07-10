"""Detached worker for AI summary auto-send (spawned from the web app).

PythonAnywhere WSGI workers tear down daemon threads when a request ends, so
generation must run in a separate process that outlives the HTTP response.
"""
import json
import os
import sys


ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main():
    if len(sys.argv) < 2:
        print('Usage: ai_auto_send_worker.py <json-job>', file=sys.stderr)
        sys.exit(1)
    job = json.loads(sys.argv[1])
    from stats import run_ai_auto_send_job

    run_ai_auto_send_job(
        username=job.get('username', 'unknown'),
        game_ids=job['game_ids'],
        game_type=job.get('game_type', 'doubles'),
        prompt_style=job.get('prompt_style', 'announcer'),
        custom_prompt=job.get('custom_prompt', ''),
    )


if __name__ == '__main__':
    main()
