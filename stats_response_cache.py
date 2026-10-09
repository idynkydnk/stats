"""Private, bounded, cross-worker storage for prepared stats API responses.

Authorization and source selection must happen before lookup. SQLite triggers
track game/roster changes, including writes from imports and other workers.
Login activity and derived-rating writes must not invalidate prepared results.
"""
from contextlib import closing
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time

STATS_ENDPOINTS = {'api_doubles_stats', 'api_vollis_stats',
                   'api_other_stats', 'api_volleyball_stats'}
TTL = 1800
MAX_ENTRIES = 256
MAX_BYTES = 2 * 1024 * 1024
_known_schemas = {}


def _database_revision(path):
    stat = os.stat(path)
    # mode=rw never creates a missing source. Connections are short-lived and
    # read-only after the tracking table/triggers have been installed once.
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=rw', uri=True, timeout=0.2)) as conn:
        schema = conn.execute('PRAGMA schema_version').fetchone()[0]
        identity = (str(path), stat.st_ino)
        if _known_schemas.get(identity) != schema:
            with conn:
                conn.execute('''CREATE TABLE IF NOT EXISTS stats_cache_revision (
                    id INTEGER PRIMARY KEY CHECK(id=1), revision TEXT NOT NULL)''')
                conn.execute('INSERT OR IGNORE INTO stats_cache_revision VALUES (1, lower(hex(randomblob(16))))')
                tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                for table in ('games', 'vollis_games', 'other_games', 'players'):
                    if table not in tables:
                        continue
                    for action in ('INSERT', 'UPDATE', 'DELETE'):
                        conn.execute(f'''CREATE TRIGGER IF NOT EXISTS stats_cache_{table}_{action.lower()}
                            AFTER {action} ON {table} BEGIN
                            UPDATE stats_cache_revision SET revision=lower(hex(randomblob(16))) WHERE id=1;
                            END''')
            schema = conn.execute('PRAGMA schema_version').fetchone()[0]
            if len(_known_schemas) > 256:
                _known_schemas.clear()
            _known_schemas[identity] = schema
        revision = conn.execute('SELECT revision FROM stats_cache_revision WHERE id=1').fetchone()
        if revision is None:
            _known_schemas.pop(identity, None)
            raise sqlite3.OperationalError('Missing stats revision')
        return ('tracked', stat.st_ino, schema, revision[0])


def database_revisions(paths):
    revisions = []
    for path in paths:
        try:
            revisions.append(_database_revision(path))
            continue
        except (OSError, sqlite3.Error):
            pass
        # Read-only or temporarily busy source: safely fall back to file/WAL
        # revisions. This can cause extra misses, but never stale reuse.
        files = []
        for suffix in ('', '-wal'):
            try:
                stat = os.stat(str(path) + suffix)
                files.append((stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
            except FileNotFoundError:
                files.append(None)
        revisions.append(('file', files))
    return revisions


class StatsResponseCache:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.path = self.directory / 'responses.db'
        # A deployment must not reuse answers produced by old calculation code.
        root = Path(__file__).resolve().parent
        self.code_revision = [(name, (root / name).stat().st_mtime_ns) for name in (
            'stats_response_cache.py', 'account_stats_views.py', 'ios_api.py',
            'stats.py', 'stat_functions.py', 'vollis_functions.py',
            'other_functions.py', 'game_ratings.py', 'doubles_division.py',
            'stats_location_filter.py', 'time_display.py')]

    def _connect(self):
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.directory, 0o700)
        conn = sqlite3.connect(self.path, timeout=0.2)
        try:
            os.chmod(self.path, 0o600)
            conn.execute('''CREATE TABLE IF NOT EXISTS responses (
                key TEXT PRIMARY KEY, revisions TEXT NOT NULL,
                expires REAL NOT NULL, body BLOB NOT NULL)''')
        except BaseException:
            conn.close()
            raise
        return conn

    def prepare(self, databases, viewer, endpoint, arguments, division):
        paths = [str(Path(path).resolve()) for path, _ in databases]
        identity = [1, self.code_revision, date.today().isoformat(), viewer,
                    list(zip(paths, [number for _, number in databases])),
                    endpoint, arguments, division]
        key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        return key, paths, json.dumps(database_revisions(paths))

    def load(self, ticket):
        key, paths, revisions = ticket
        try:
            with closing(self._connect()) as conn:
                row = conn.execute('SELECT body FROM responses WHERE key=? AND revisions=? AND expires>?',
                                   (key, revisions, time.time())).fetchone()
            # Do not return a result if a source changed during the lookup.
            if row and json.dumps(database_revisions(paths)) == revisions:
                return bytes(row[0])
        except (OSError, sqlite3.Error):
            pass  # Caching must never prevent a normal stats request.
        return None

    def save(self, ticket, body):
        key, paths, revisions = ticket
        try:
            if len(body) > MAX_BYTES or json.dumps(database_revisions(paths)) != revisions:
                return
            with closing(self._connect()) as conn, conn:
                now = time.time()
                conn.execute('DELETE FROM responses WHERE expires<=?', (now,))
                conn.execute('INSERT OR REPLACE INTO responses VALUES (?, ?, ?, ?)',
                             (key, revisions, now + TTL, body))
                conn.execute('''DELETE FROM responses WHERE key IN (
                    SELECT key FROM responses ORDER BY expires DESC LIMIT -1 OFFSET ?)''', (MAX_ENTRIES,))
        except (OSError, sqlite3.Error):
            pass

    def clear(self):
        try:
            if self.path.exists():
                with closing(self._connect()) as conn, conn:
                    conn.execute('DELETE FROM responses')
        except (OSError, sqlite3.Error):
            pass
