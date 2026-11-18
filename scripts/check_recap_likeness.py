"""Generate a detached recap preview on the host; never publish it or send email.

API keys stay on the website server. CI receives only this recap's generated
images, saved character references, scene prompt and review. A one-shot marker
and deadline prevent a restarted host task from generating another paid image.
"""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import shlex
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import uuid

MODELS = {'gpt-image-2', 'gpt-image-2.5-sunburst', 'gpt-image-2.6-sunburst'}


def render(prefix, deadline, share_id, model):
    if not re.fullmatch(r'/home/Idynkydnk/\.stats-recap-check-[a-f0-9]{32}', prefix):
        raise ValueError('Invalid preview destination')
    if model not in MODELS or not re.fullmatch(r'[A-Za-z0-9_-]{6,80}', share_id):
        raise ValueError('Invalid preview input')
    if not time.time() < deadline <= time.time() + 1205:
        return
    try:
        claim = os.open(prefix + '-claimed', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return
    os.close(claim)
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    sys.path.insert(0, str(root))
    files = []
    result = {'ok': False, 'model': model, 'files': files}

    def save_file(name, raw):
        path = Path(prefix + '-' + name)
        path.write_bytes(raw)
        path.chmod(0o600)
        files.append(name)

    try:
        from ai_auto_send_daemon import _load_missing_env_from_wsgi
        _load_missing_env_from_wsgi()
        # Set before importing email_content, matching its environment settings.
        os.environ['OPENAI_IMAGE_MODEL'] = model
        os.environ['OPENAI_RECAP_IMAGE_MODEL'] = model
        os.environ['OPENAI_IMAGE_RETRIES'] = '1'
        from unittest.mock import patch
        import base64
        import email_content as content
        from stats import app, _stats_db_path, _load_games_and_players_for_recap
        import admin_functions
        from private_accounts import ai_account_context
        from flask import session
        row = admin_functions.get_ai_recap_page(share_id)
        if not row:
            raise ValueError('Recap not found')
        generate = content._generate_image_bytes
        calls = []

        def capture_image(prompt, api_key, **kwargs):
            if not calls:
                for index, part in enumerate(kwargs.get('reference_parts') or []):
                    inline = part.get('inline_data') or {}
                    if inline.get('data'):
                        ext = 'png' if 'png' in inline.get('mime_type', '') else 'jpg'
                        save_file(f'reference-{index}.{ext}', base64.b64decode(inline['data']))
            calls.append(prompt)
            raw, mime = generate(prompt, api_key, **kwargs)
            save_file(f'candidate-{len(calls)}.png', raw)
            return raw, mime

        def save_preview(raw, ext):
            save_file('selected.' + ext, raw)
            return 'preview-only', prefix + '-selected.' + ext

        with app.test_request_context('/'):
            session['username'] = row['username']
            session['logged_in'] = True
            with ai_account_context(app, _stats_db_path(), row['username']):
                game_type = row.get('game_type') or 'doubles'
                games, players, game_name, location, weather = _load_games_and_players_for_recap(
                    game_type, json.loads(row['game_ids_json']), include_weather=True,
                )
                with patch.object(content, '_save_email_image', save_preview), patch.object(
                    content, '_generate_image_bytes', capture_image,
                ):
                    started = time.monotonic()
                    preview = content.generate_email_hero_image(
                        content.require_ai_api_key(), game_type, games, players,
                        game_name=game_name, image_details=row.get('image_details') or '',
                        visual_source=row.get('custom_prompt') or row.get('image_details') or '',
                        location=location, weather_games=weather,
                    )
        result.update(ok=True, seconds=round(time.monotonic() - started, 1),
                      prompt=preview[2], scene=preview[4], image_calls=len(calls))
    except Exception as error:
        # Provider exceptions contain no request headers. Redact any configured
        # key anyway before copying the failure to a short-lived CI artifact.
        message = str(error)
        for key in ('OPENAI_API_KEY', 'GEMINI_API_KEY', 'SECRET_KEY'):
            if os.environ.get(key):
                message = message.replace(os.environ[key], '[redacted]')
        result.update(error=message[:1500], error_type=type(error).__name__)
    Path(prefix + '-report.json').write_text(json.dumps(result, indent=2))
    Path(prefix + '-report.json').chmod(0o600)
    while time.time() < deadline:
        time.sleep(5)


def main():
    if not os.environ.get('GITHUB_ACTIONS'):
        raise SystemExit('Run this paid preview manually through GitHub Actions.')
    from install_passkeys_cloud import python_command
    share_id, model = os.environ['RECAP_SHARE_ID'], os.environ['RECAP_TEST_MODEL']
    if model not in MODELS or not re.fullmatch(r'[A-Za-z0-9_-]{6,80}', share_id):
        raise ValueError('Invalid preview input')
    base = 'https://www.pythonanywhere.com/api/v0/user/' + os.environ['PA_USERNAME']

    def api(path, method='GET', data=None, raw=False):
        req = Request(base + path, method=method,
                      data=urlencode(data).encode() if data is not None else None,
                      headers={'Authorization': 'Token ' + os.environ['PA_API_TOKEN']})
        with urlopen(req, timeout=60) as response:
            body = response.read()
        return body if raw else json.loads(body) if body else None

    config = api('/webapps/' + os.environ['PA_DOMAIN'] + '/')
    executable, _ = python_command(config)
    prefix = '/home/Idynkydnk/.stats-recap-check-' + uuid.uuid4().hex
    deadline = time.time() + 1050
    command = shlex.join(executable + ['/home/Idynkydnk/stats/scripts/check_recap_likeness.py',
                                      '--render', prefix, str(deadline), share_id, model])
    endpoint = '/always_on/'
    task_data = dict(command=command, description='Temporary recap likeness preview', enabled='true')
    try:
        task = api(endpoint, 'POST', task_data)
    except HTTPError as error:
        if error.code != 403:
            raise
        endpoint = '/schedule/'
        start = datetime.now(timezone.utc) + timedelta(minutes=2)
        task = api(endpoint, 'POST', dict(task_data, interval='daily', hour=start.hour, minute=start.minute))
    output = Path('output/recap-likeness-preview')
    output.mkdir(parents=True, exist_ok=True)
    files = []
    try:
        print('Started detached preview task:', task['id'], flush=True)
        while time.time() < deadline - 60:
            try:
                report = api('/files/path' + prefix + '-report.json')
                break
            except HTTPError as error:
                if error.code != 404:
                    raise
            time.sleep(10)
        else:
            raise TimeoutError('Preview did not finish before its deadline')
        (output / 'report.json').write_text(json.dumps(report, indent=2))
        files = report.get('files') or []
        if any(not re.fullmatch(r'(reference-\d+\.(png|jpg)|candidate-\d+\.png|selected\.(png|jpg))', name)
               for name in files):
            raise ValueError('Invalid preview filename')
        for name in files:
            (output / name).write_bytes(api('/files/path' + prefix + '-' + name, raw=True))
        print(json.dumps({k: report[k] for k in ('ok', 'model', 'seconds', 'image_calls', 'error') if k in report}), flush=True)
        if not report['ok']:
            raise RuntimeError('Image preview failed; see report artifact')
    finally:
        api(endpoint + str(task['id']) + '/', 'DELETE')
        for name in files + ['report.json', 'claimed']:
            try:
                api('/files/path' + prefix + '-' + name, 'DELETE')
            except HTTPError as error:
                if error.code != 404:
                    raise
        print('Removed temporary preview task and files.', flush=True)


if __name__ == '__main__':
    if len(sys.argv) == 6 and sys.argv[1] == '--render':
        render(sys.argv[2], float(sys.argv[3]), sys.argv[4], sys.argv[5])
    else:
        main()
