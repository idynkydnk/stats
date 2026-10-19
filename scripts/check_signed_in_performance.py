"""CI-only live checks using a short-lived, automatically revoked account token.

The cloud task creates one 15-minute remember token for the existing Kyle account.
Only its random token travels through the authenticated host API into CI memory.
Passwords, application secrets and account/game data are never downloaded.
Deleting the handshake file ends the lease; a hard deadline revokes it even if
CI is interrupted. No web authentication bypass is installed.
"""
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import shlex
import subprocess
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit, unquote
from urllib.request import Request, urlopen
import uuid

from install_passkeys_cloud import python_command


def lease_code(report, deadline):
    return f'''
import hashlib, json, os, pathlib, secrets, sqlite3, time
from contextlib import closing
from datetime import datetime, timedelta
report = pathlib.Path({report!r})
deadline = {deadline!r}
if time.time() >= deadline:
    raise SystemExit(0)
db = '/home/Idynkydnk/stats/stats.db'
token = secrets.token_urlsafe(32)
digest = hashlib.sha256(token.encode()).hexdigest()
try:
    with closing(sqlite3.connect(db, timeout=10)) as conn, conn:
        user = conn.execute("SELECT username FROM site_users WHERE lower(username)='kyle' AND active=1").fetchone()
        if not user:
            raise RuntimeError('Requested account unavailable')
        conn.execute('INSERT INTO auth_tokens(username,token_hash,expires_at) VALUES(?,?,?)',
                     (user[0], digest, datetime.now() + timedelta(minutes=15)))
    fd = os.open(report, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as out:
        json.dump(dict(token=token), out)
    while time.time() < deadline and report.exists():
        time.sleep(2)
finally:
    with closing(sqlite3.connect(db, timeout=30)) as conn, conn:
        conn.execute('DELETE FROM auth_tokens WHERE token_hash=?', (digest,))
    report.unlink(missing_ok=True)
    pathlib.Path(str(report) + '.revoked').write_text('revoked')
time.sleep(600)
'''


def profile_pages(token):
    origin = 'https://' + os.environ['PA_DOMAIN']
    authorization = 'Bearer ' + token
    headers = {'Authorization': authorization}
    pages = [('standings', '/stats/2026/'), ('all-years', '/stats/All%20years/'),
             ('player', '/player/All%20years/Kyle%20Thomson/'), ('games', '/games/2026/'),
             ('add-game', '/add_game/'), ('sources', '/account/stats-sources/'),
             ('players', '/player_list/'), ('admin', '/admin/')]
    reports = []
    for label, path in pages:
        with urlopen(Request(origin + path, headers=headers), timeout=60) as response:
            destination = response.url
            response.read()
        parts = urlsplit(destination)
        if parts.netloc != urlsplit(origin).netloc or parts.path == '/login':
            raise RuntimeError('Account navigation failed: ' + label)
        normal, profiles = [], []
        for cold in (True, False, False):
            request_headers = dict(headers)
            if cold:
                request_headers['Cache-Control'] = 'no-cache'
            start = time.perf_counter()
            with urlopen(Request(destination, headers=request_headers), timeout=60) as response:
                body = response.read()
                normal.append(dict(render_required=cold, ms=round((time.perf_counter()-start)*1000, 1),
                                   server_timing=response.headers.get('Server-Timing'), status=response.status,
                                   bytes=len(body), page_cache=response.headers.get('X-Stats-Page-Cache')))
        for cold in (True, False):
            timestamp = str(int(time.time()))
            target = unquote(parts.path) + ('?' + parts.query if parts.query else '')
            target += '\nauth:' + hashlib.sha256(('\n' + authorization).encode()).hexdigest()
            signed = hmac.new(os.environ['DEPLOY_TOKEN'].encode(), (timestamp + '\n' + target).encode(), hashlib.sha256).hexdigest()
            request_headers = dict(headers, **{'X-Stats-Profile': timestamp + ':' + signed})
            if cold:
                request_headers['Cache-Control'] = 'no-cache'
            with urlopen(Request(destination, headers=request_headers), timeout=60) as response:
                result = json.load(response)
            if result.get('status') != 200 or 'cumulative' not in result:
                raise RuntimeError('Signed-in profile failed: ' + label)
            profiles.append(dict(render_required=cold, **result))
        reports.append(dict(page=label, normal=normal, profiles=profiles))
        Path('output/signed-in-performance/profiles.json').write_text(json.dumps(reports, indent=2))
        print('Profiled signed-in ' + label, flush=True)


def main():
    if not os.environ.get('GITHUB_ACTIONS'):
        raise SystemExit('Run the signed-in check on GitHub Actions.')
    base = 'https://www.pythonanywhere.com/api/v0/user/' + os.environ['PA_USERNAME']
    def api(path, method='GET', data=None):
        request = Request(base + path, method=method,
                          data=urlencode(data).encode() if data is not None else None,
                          headers={'Authorization': 'Token ' + os.environ['PA_API_TOKEN']})
        with urlopen(request, timeout=60) as response:
            body = response.read()
            return json.loads(body) if body else None
    config = api('/webapps/' + os.environ['PA_DOMAIN'] + '/')
    if os.environ.get('INSPECT_ONLY') == 'true':
        print('CPU quota:', api('/cpu/'), flush=True)
        for endpoint in ('/always_on/', '/schedule/'):
            for item in api(endpoint):
                if item.get('description') != 'Temporary signed-in performance check':
                    continue
                print('Temporary test task:', endpoint, {k: v for k, v in item.items()
                      if k in {'id', 'state', 'status', 'enabled', 'next_run', 'last_run', 'interval', 'hour', 'minute', 'timezone'}}, flush=True)
                print('Command length:', len(item.get('command', '')), flush=True)
                parts = shlex.split(item['command']) if '--lease' in item.get('command', '') else []
                if '--lease' in parts:
                    handshake = parts[parts.index('--lease') + 1]
                    if handshake.startswith('/home/Idynkydnk/.stats-performance-') and handshake.endswith('.json'):
                        for suffix in ('', '.revoked'):
                            try:
                                with urlopen(Request(base + '/files/path' + handshake + suffix, method='HEAD',
                                     headers={'Authorization': 'Token ' + os.environ['PA_API_TOKEN']}), timeout=30) as response:
                                    status = response.status
                            except HTTPError as error:
                                status = error.code
                            print('Handshake' + (suffix or '.ready') + ' HTTP:', status, flush=True)
                if str(item['id']) == os.environ.get('CLEANUP_TEST_TASK'):
                    api(endpoint + str(item['id']) + '/', 'DELETE')
                    print('Removed this check\'s requested temporary task:', item['id'], flush=True)
        return
    executable, _ = python_command(config)
    report = '/home/Idynkydnk/.stats-performance-' + uuid.uuid4().hex + '.json'
    deadline = time.time() + 900
    # Keep the host task command short; the script is already deployed with the
    # site. No credential is ever put in a command line or task description.
    command = shlex.join(executable + ['/home/Idynkydnk/stats/scripts/check_signed_in_performance.py',
                                      '--lease', report, str(deadline)])
    endpoint = '/always_on/'
    try:
        task = api(endpoint, 'POST', dict(command=command, description='Temporary signed-in performance check', enabled='true'))
    except HTTPError as error:
        if error.code != 403:
            raise
        endpoint = '/schedule/'
        start = datetime.now(timezone.utc) + timedelta(minutes=2)
        task = api(endpoint, 'POST', dict(command=command, description='Temporary signed-in performance check',
                   enabled='true', interval='daily', hour=start.hour, minute=start.minute))
    try:
        token = None
        print('Waiting for the temporary cloud credential task.', flush=True)
        diagnostic = 0
        while time.time() < deadline - 300:
            if time.time() > diagnostic:
                state = api(endpoint + str(task['id']) + '/')
                print('Cloud task:', {k: v for k, v in state.items() if k in {'id', 'state', 'status', 'next_run', 'last_run', 'enabled', 'timezone'}}, flush=True)
                diagnostic = time.time() + 60
            try:
                result = api('/files/path' + report)
                token = result['token']
                break
            except HTTPError as error:
                if error.code != 404:
                    raise
            time.sleep(5)
        if not token:
            raise TimeoutError('Temporary account token not ready')
        print('::add-mask::' + token, flush=True)
        Path('output/signed-in-performance').mkdir(parents=True, exist_ok=True)
        profile_pages(token)
        for browser in ('chromium', 'webkit'):
            subprocess.run(['node', 'scripts/check_live_performance.mjs'], check=True, timeout=180,
                           env=dict(os.environ, STATS_TEST_TOKEN=token, BROWSER=browser,
                                    FORCE_RENDER_FIRST='1',
                                    PERFORMANCE_OUTPUT='output/signed-in-performance/' + browser))
    finally:
        try:
            api('/files/path' + report, 'DELETE')
        except HTTPError as error:
            if error.code != 404:
                raise
        # Let the cloud process revoke its own token before removing the task.
        revoked = False
        # The task and files API can observe home storage changes at different
        # times. Allow propagation before treating revocation as unconfirmed.
        for _ in range(90):
            try:
                with urlopen(Request(base + '/files/path' + report + '.revoked',
                     headers={'Authorization': 'Token ' + os.environ['PA_API_TOKEN']}), timeout=30) as response:
                    revoked = response.read() == b'revoked'
                if revoked:
                    break
            except HTTPError as error:
                if error.code != 404:
                    raise
            time.sleep(2)
        if revoked or not token:
            api(endpoint + str(task['id']) + '/', 'DELETE')
            if revoked:
                api('/files/path' + report + '.revoked', 'DELETE')
                print('Verified temporary token revoked and cloud task removed.', flush=True)
            else:
                print('Removed cloud setup task; no test credential was received.', flush=True)
        else:
            # Leave the live process to its hard deadline; never kill it before
            # its finally block revokes the token. The token also expires in DB.
            raise RuntimeError('Revocation not confirmed; temporary task retains its hard expiry')


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    if len(sys.argv) == 4 and sys.argv[1] == '--lease':
        report, deadline = sys.argv[2], float(sys.argv[3])
        if not report.startswith('/home/Idynkydnk/.stats-performance-') or not report.endswith('.json'):
            raise SystemExit('Invalid temporary report path')
        if not time.time() < deadline <= time.time() + 905:
            raise SystemExit(0)
        exec(lease_code(report, deadline))
    else:
        main()
