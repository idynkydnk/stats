"""Read-only checks of the deployed recap code and worker."""
import hashlib
import json
import os
from pathlib import Path
import urllib.request

base = 'https://www.pythonanywhere.com/api/v0/user/' + os.environ['PA_USERNAME']
headers = {'Authorization': 'Token ' + os.environ['PA_API_TOKEN']}

def remote_file(name):
    req = urllib.request.Request(base + '/files/path/home/Idynkydnk/stats/' + name, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read()

for name in ['email_content.py', 'recap_weather.py', 'ios_api.py', 'stats.py', 'ai_auto_send_daemon.py', 'ai_worker_reload.py', 'data/app_updates.json']:
    remote = remote_file(name)
    assert hashlib.sha256(remote).digest() == hashlib.sha256(Path(name).read_bytes()).digest(), name + ' differs from pushed code'
    print('Deployed source matches:', name)

log = remote_file('ai_auto_send_daemon.log').decode(errors='replace')
# Report only lifecycle lines; keep player names, prompts, and job details private.
lines = [line for line in log.splitlines() if 'Application code changed; restarting' in line or 'AI auto-send daemon started' in line]
print('Latest worker lifecycle events:')
print('\n'.join(lines[-4:]))

url = 'https://idynkydnk.pythonanywhere.com/api/ai/recaps'
with urllib.request.urlopen(url, timeout=30) as response:
    assert response.status == 200
    data = json.load(response)
    assert isinstance(data, dict)
    print('Live app recap-list API: HTTP 200, valid JSON')

from recap_weather import recap_weather_context
result = recap_weather_context([{'location': 'Hermosa Beach', 'game_date': '2026-10-11 15:00:00', 'entered_timezone': 'America/Los_Angeles'}])
assert 'Weather source: Open-Meteo, Hermosa Beach' in result, result
assert '2026-10-11 at 15:00' in result, result
print('Hermosa game-time weather lookup: PASS')
print(result)
