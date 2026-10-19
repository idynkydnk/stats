"""Prepare common public pages after a deployment, before people open them."""
from datetime import date
import os
from urllib.parse import urlsplit
from urllib.request import urlopen


def main():
    origin = 'https://' + os.environ['PA_DOMAIN']
    year = str(date.today().year)
    paths = ['/stats/' + year + '/', '/stats/All%20years/', '/games/' + year + '/',
             '/vollis_stats/' + year + '/', '/other_stats/' + year + '/',
             '/volleyball_stats/' + year + '/']
    for path in paths:
        with urlopen(origin + path, timeout=60) as response:
            destination = response.url
            response.read()
        if urlsplit(destination).netloc != urlsplit(origin).netloc:
            raise RuntimeError('Unexpected redirect host')
        with urlopen(destination, timeout=60) as response:
            response.read()
            if response.status != 200:
                raise RuntimeError('Public page failed')
        print('Prepared', path, flush=True)


if __name__ == '__main__':
    main()
