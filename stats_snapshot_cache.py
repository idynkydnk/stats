"""Reuse combined raw data; each request gets its own disposable writable copy."""
from datetime import date
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import time

from stats_response_cache import database_revisions

# Deployment reloads workers; these files do not need network filesystem stats
# for every calculation in every request.
_CODE_REVISION = [Path(__file__).stat().st_mtime_ns,
                  Path(__file__).with_name('account_stats_views.py').stat().st_mtime_ns]


def source_revision(databases, tables=None):
    return json.dumps([_CODE_REVISION, date.today().isoformat(), databases,
                       database_revisions([path for path, _ in databases], tables)], sort_keys=True)


def prepared_snapshot(directory, databases, build):
    directory = Path(directory) / 'snapshots'
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    revision = source_revision(databases)
    key = hashlib.sha256(revision.encode()).hexdigest()
    cached = directory / (key + '.db')
    # One bounded lock file, shared by workers; never serve a partial build.
    with open(directory / 'build.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not cached.exists():
            snapshot = build()
            if source_revision(databases) != revision:
                return snapshot  # Source changed; never publish this as reusable.
            os.replace(snapshot, cached)
        fd, snapshot = tempfile.mkstemp(prefix='stats-view-', suffix='.db')
        os.close(fd)
        try:
            shutil.copyfile(cached, snapshot)
        except BaseException:
            os.unlink(snapshot)
            raise
        os.utime(cached, None)
        files = sorted(directory.glob('*.db'), key=lambda p: p.stat().st_mtime, reverse=True)
        size = 0
        for index, path in enumerate(files):
            size += path.stat().st_size
            if index >= 16 or size > 128 * 1024 * 1024 or path.stat().st_mtime < time.time() - 1800:
                path.unlink(missing_ok=True)
        return snapshot
