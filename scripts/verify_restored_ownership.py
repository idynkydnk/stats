"""Read the cloud correction report without exposing account data."""
import json
import os
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
path = '/home/Idynkydnk/stats/backups/restore-dan-tyler-ownership-20261103/report.json'
request = Request('https://www.pythonanywhere.com/api/v0/user/' + os.environ['PA_USERNAME'] + '/files/path' + path,
                  headers={'Authorization': 'Token ' + os.environ['PA_API_TOKEN']})
for attempt in range(30):
    try:
        with urlopen(request, timeout=30) as response:
            report = json.load(response)
        break
    except HTTPError as error:
        if error.code != 404 or attempt == 29:
            raise
        time.sleep(4)
assert report['moved'] == {'dan': 145, 'tyler': 7}, report
print('Verified cloud ownership restoration:', report['moved'])
