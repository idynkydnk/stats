"""Run signed, read-only profiles in live web workers using CI's deploy secret."""
import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import statistics
import time
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='output/production-profile')
    args = parser.parse_args()
    origin = 'https://' + os.environ['PA_DOMAIN']
    secret = os.environ['DEPLOY_TOKEN']
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    pages = [('standings', '/stats/2026/'), ('all-years', '/stats/All%20years/'),
             ('player', '/player/All%20years/Kyle%20Thomson/'), ('games', '/games/2026/'),
             ('vollis', '/vollis_stats/2026/'), ('other', '/other_stats/2026/'),
             ('volleyball', '/volleyball_stats/2026/')]
    reports = []
    for label, path in pages:
        with urlopen(origin + path, timeout=60) as response:
            destination = response.url
            response.read()
        parts = urlsplit(destination)
        if parts.netloc != urlsplit(origin).netloc:
            raise RuntimeError('Unexpected redirect host')
        normal, profiles = [], []
        for visit in range(4):
            started = time.perf_counter()
            req = Request(destination, headers={'Cache-Control': 'no-cache'} if visit == 0 else {})
            with urlopen(req, timeout=60) as response:
                body = response.read()
                normal.append(dict(render_required=visit == 0, ms=round((time.perf_counter() - started) * 1000, 1),
                                   server_timing=response.headers.get('Server-Timing'),
                                   status=response.status, bytes=len(body)))
        for visit in range(3):
            timestamp = str(int(time.time()))
            target = unquote(parts.path) + ('?' + parts.query if parts.query else '')
            signed = hmac.new(secret.encode(), (timestamp + '\n' + target).encode(), hashlib.sha256).hexdigest()
            req = Request(destination, headers={'X-Stats-Profile': timestamp + ':' + signed})
            if visit == 0:
                req.add_header('Cache-Control', 'no-cache')
            with urlopen(req, timeout=60) as response:
                result = json.load(response)
            if result.get('status') != 200 or 'cumulative' not in result:
                raise RuntimeError('Profile failed for ' + label)
            profiles.append(dict(render_required=visit == 0, **result))
        reports.append(dict(page=label, normal=normal, profiles=profiles))
        (output / 'report.json').write_text(json.dumps(reports, indent=2))
        print(label, 'normal median ms:', statistics.median(row['ms'] for row in normal), flush=True)
    print('Saved anonymous production profiles.', flush=True)


if __name__ == '__main__':
    main()
