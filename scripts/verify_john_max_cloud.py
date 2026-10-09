"""Read the correction audit from the deployment's authenticated server API."""
import json
import os
from urllib.request import Request, urlopen

path = '/home/Idynkydnk/stats/backups/john-russian-max-2026-10-09/report.json'
request = Request('https://www.pythonanywhere.com/api/v0/user/' + os.environ['PA_USERNAME'] + '/files/path' + path,
                  headers={'Authorization': 'Token ' + os.environ['PA_API_TOKEN']})
with urlopen(request, timeout=30) as response:
    report = json.load(response)
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
