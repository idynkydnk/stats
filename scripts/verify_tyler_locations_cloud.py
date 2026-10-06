"""Verify the cloud correction through the authenticated PythonAnywhere files API."""
import json
import os
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

username = os.environ['PA_USERNAME']
token = os.environ['PA_API_TOKEN']
revision = os.environ['EXPECTED_REVISION']
name = 'tyler-entered-locations-2026-10-05'
path = '/home/Idynkydnk/stats/backups/' + name + '/report.json'
request = Request('https://www.pythonanywhere.com/api/v0/user/' + username + '/files/path' + path,
                  headers={'Authorization': 'Token ' + token})

for attempt in range(30):
    try:
        with urlopen(request, timeout=20) as response:
            report = json.load(response)
        if report['migration'] == name and report['revision'] == revision:
            print(json.dumps(report, indent=2))
            if any(db['missing_tyler'] or db['noncanonical_clearwater'] for db in report['databases']):
                raise SystemExit('Cloud location verification failed')
            print('Cloud locations verified: no blank Tyler locations or alternate Clearwater names.')
            break
    except HTTPError as error:
        if error.code != 404:
            raise
    time.sleep(4)
else:
    raise SystemExit('No location correction report for the deployed revision')
