"""Prepare common public pages after a deployment, before people open them."""
from datetime import date
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import urlopen


def fetch(url):
    # Reloads can briefly disconnect a worker or leave a request waiting while
    # another worker starts. Retry transient failures, but still fail the deploy
    # if a page stays unavailable. Never swallow missing pages or other 4xxs.
    for attempt in range(4):
        try:
            with urlopen(url, timeout=20) as response:
                response.read()
                if response.status != 200:
                    raise RuntimeError('Public page failed')
                return response.url
        except HTTPError as error:
            if error.code not in {502, 503, 504} or attempt == 3:
                raise
        except (TimeoutError, URLError):
            if attempt == 3:
                raise
        print('Retrying public page after a transient connection failure.', flush=True)
        time.sleep(2 * (attempt + 1))


def main():
    origin = 'https://' + os.environ['PA_DOMAIN']
    year = str(date.today().year)
    paths = ['/stats/' + year + '/', '/stats/All%20years/', '/games/' + year + '/',
             '/vollis_stats/' + year + '/', '/other_stats/' + year + '/',
             '/volleyball_stats/' + year + '/']
    for path in paths:
        destination = fetch(origin + path)
        if urlsplit(destination).netloc != urlsplit(origin).netloc:
            raise RuntimeError('Unexpected redirect host')
        fetch(destination)
        print('Prepared', path, flush=True)


if __name__ == '__main__':
    main()
