"""Read the cloud correction report without exposing account data."""
import json
import os
from urllib.request import Request, urlopen
path = '/home/Idynkydnk/stats/backups/restore-dan-tyler-ownership-20261103/report.json'
request = Request('https://www.pythonanywhere.com/api/v0/user/' + os.environ['PA_USERNAME'] + '/files/path' + path,
                  headers={'Authorization': 'Token ' + os.environ['PA_API_TOKEN']})
with urlopen(request, timeout=30) as response:
    report = json.load(response)
assert report['moved'] == {'dan': 145, 'tyler': 7}, report
print('Verified cloud ownership restoration:', report['moved'])
