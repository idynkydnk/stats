"""Install the pinned passkey dependency in the web app's actual environment.

Run in deployment CI with its existing PythonAnywhere credentials. A temporary
cloud task runs the install, reports completion, and is removed in finally.
"""
import json
import base64
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import re
import shlex
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import uuid


def python_command(config):
    virtualenv = config.get('virtualenv_path')
    if virtualenv:
        return [virtualenv.rstrip('/') + '/bin/python'], []
    version = str(config['python_version']).removeprefix('python')
    if re.fullmatch(r'3\d{1,2}', version):
        version = '3.' + version[1:]
    if not re.fullmatch(r'3\.\d{1,2}', version):
        raise ValueError('Unrecognized website Python version')
    return ['python' + version], ['--user']


def main():
    username = os.environ['PA_USERNAME']
    domain = os.environ['PA_DOMAIN']
    token = os.environ['PA_API_TOKEN']
    base = 'https://www.pythonanywhere.com/api/v0/user/' + username

    def api(path, method='GET', data=None):
        encoded = urlencode(data).encode() if data is not None else None
        request = Request(base + path, data=encoded, method=method,
                          headers={'Authorization': 'Token ' + token})
        with urlopen(request, timeout=60) as response:
            raw = response.read()
            return json.loads(raw) if raw else None

    config = api('/webapps/' + domain + '/')
    executable, flags = python_command(config)
    pinned = next(line.strip() for line in Path('requirements.txt').read_text().splitlines()
                  if line.startswith('webauthn=='))
    home = '/home/Idynkydnk' if username.lower() == 'idynkydnk' else '/home/' + username
    report = home + '/.stats-passkeys-install-' + uuid.uuid4().hex + '.json'
    # The final sleep keeps the temporary task from restarting before CI deletes it.
    code = '\n'.join([
        'import importlib.metadata, json, pathlib, subprocess, sys, time',
        'result = {}',
        'try:',
        '    subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", ' + repr(pinned) + '] + ' + repr(flags) + ', check=True, timeout=300)',
        '    import webauthn',
        '    result = {"ok": True, "version": importlib.metadata.version("webauthn"), "python": sys.version.split()[0]}',
        'except Exception as error:',
        '    result = {"ok": False, "error": type(error).__name__}',
        'pathlib.Path(' + repr(report) + ').write_text(json.dumps(result))',
        'time.sleep(600)',
    ])
    def command(source):
        payload = base64.b64encode(source.encode()).decode()
        return shlex.join(executable + ['-c', 'import base64; exec(base64.b64decode(' + repr(payload) + '))'])

    task_endpoint = '/always_on/'
    try:
        task = api(task_endpoint, 'POST', {
            'command': command(code),
            'description': 'Temporary Stats passkey dependency installation', 'enabled': 'true',
        })
    except HTTPError as error:
        if error.code != 403:
            raise
        # Accounts without spare always-on capacity can run a scheduled install.
        # Delete this task as soon as its first result arrives; it must not recur.
        task_endpoint = '/schedule/'
        start = datetime.now(timezone.utc) + timedelta(minutes=2)
        scheduled_code = code.removesuffix('time.sleep(600)')
        task = api(task_endpoint, 'POST', {
            'command': command(scheduled_code),
            'description': 'Temporary Stats passkey dependency installation',
            'enabled': 'true', 'interval': 'daily', 'hour': start.hour, 'minute': start.minute,
        })
    task_id = task['id']
    print('Installation task:', json.dumps({key: value for key, value in task.items() if key in {'id', 'enabled', 'interval', 'hour', 'minute', 'timezone', 'next_run', 'last_run', 'logfile', 'log_file', 'state', 'status'}}), flush=True)
    print('Started temporary dependency install in website Python environment.', flush=True)
    try:
        deadline = time.monotonic() + 600
        next_diagnostic = time.monotonic() + 60
        while time.monotonic() < deadline:
            if time.monotonic() >= next_diagnostic:
                info = api(task_endpoint + str(task_id) + '/')
                print('Installation status:', json.dumps({key: value for key, value in info.items() if key in {'id', 'enabled', 'interval', 'hour', 'minute', 'timezone', 'next_run', 'last_run', 'logfile', 'log_file', 'state', 'status'}}), flush=True)
                next_diagnostic = time.monotonic() + 60
            try:
                result = api('/files/path' + report)
            except HTTPError as error:
                if error.code != 404:
                    raise
            else:
                if not result.get('ok'):
                    raise RuntimeError('Dependency installation failed: ' + result.get('error', 'unknown'))
                if result['version'] != pinned.split('==')[1]:
                    raise RuntimeError('Installed dependency version does not match requirements')
                print('Verified WebAuthn ' + result['version'] + ' in website Python ' + result['python'], flush=True)
                return
            time.sleep(10)
        raise TimeoutError('Cloud dependency installation did not finish within ten minutes')
    finally:
        api(task_endpoint + str(task_id) + '/', 'DELETE')
        try:
            api('/files/path' + report, 'DELETE')
        except HTTPError as error:
            if error.code != 404:
                raise
        print('Removed temporary installation task.', flush=True)


if __name__ == '__main__':
    main()
