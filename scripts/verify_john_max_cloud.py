"""Read the correction audit from the deployment's authenticated server API."""
import json
import os
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

path = '/home/Idynkydnk/stats/backups/john-russian-max-2026-10-09/report.json'
base = 'https://www.pythonanywhere.com/api/v0/user/' + os.environ['PA_USERNAME']
headers = {'Authorization': 'Token ' + os.environ['PA_API_TOKEN']}
# Touching WSGI may leave old workers running; use the hosting reload API.
reload_request = Request(base + '/webapps/idynkydnk.pythonanywhere.com/reload/', data=b'', headers=headers)
with urlopen(reload_request, timeout=30) as response:
    print('Hosting reload status:', response.status)
request = Request(base + '/files/path' + path, headers=headers)
for attempt in range(24):
    try:
        with urlopen('https://idynkydnk.pythonanywhere.com/api/doubles/games?since=2026-10-09', timeout=30) as response:
            response.read()
        with urlopen(request, timeout=30) as response:
            report = json.load(response)
        break
    except HTTPError as error:
        if error.code not in (404, 502, 503):
            raise
        time.sleep(5)
else:
    raise SystemExit('Correction report was not produced after hosting reload')
print(json.dumps(report, indent=2))
assert report['correction'] == 'john-russian-max-2026-10-09'
assert sum(db['corrected'] for db in report['databases']) > 0, 'No matching games corrected'
for db in report['databases']:
    for game in db['games']:
        before, after = game['before'], game['after']
        assert before['game_date'].startswith('2026-10-09')
        for key, value in before.items():
            if isinstance(value, str) and value.strip().casefold() == 'russian max' and key.startswith(('winner', 'loser')):
                assert after[key] == 'Max Chicherin'
            elif key != 'updated_at':
                assert after[key] == value
print('Verified live correction and preservation of all other game details.')
