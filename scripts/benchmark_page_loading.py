"""Measure local HTML generation using a disposable backup, never the source DB.

Run with project dependencies: python scripts/benchmark_page_loading.py
Use --root to compare another checkout. These are not network/browser timings.
"""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import statistics
import sys
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    if Path('/home/Idynkydnk/stats/stats.db').exists():
        raise SystemExit('Run locally: production path resolution would bypass the temporary database.')
    with tempfile.TemporaryDirectory(prefix='stats-page-timing-') as directory:
        with closing(sqlite3.connect((root / 'stats.db').as_uri() + '?mode=ro', uri=True)) as source:
            with closing(sqlite3.connect(Path(directory) / 'stats.db')) as target:
                source.backup(target)
        os.chdir(directory)
        os.environ['PYTHON_DOTENV_DISABLED'] = '1'
        os.environ['STATS_PRIVATE_DATA_DIR'] = directory + '/private_data'
        sys.path.insert(0, str(root))
        import stats
        client = stats.app.test_client()
        results = []
        for path in ['/stats/2026/', '/stats/All%20years/', '/player/All%20years/Kyle%20Thomson/']:
            url = client.get(path).location or path
            elapsed = []
            for _ in range(6):
                started = time.perf_counter()
                response = client.get(url, follow_redirects=True)
                elapsed.append((time.perf_counter() - started) * 1000)
                if response.status_code != 200:
                    raise RuntimeError(f'{path}: HTTP {response.status_code}')
            results.append(dict(path=path, first_ms=round(elapsed[0], 1),
                                repeat_median_ms=round(statistics.median(elapsed[1:]), 1),
                                html_bytes=len(response.data)))
        print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
