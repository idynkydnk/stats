"""Cloud location correction requested October 5, 2026.

Use recorded entry ownership, never player participation or local game IDs.
Retain the original rows in the same transaction as each correction.
"""
from collections import Counter
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile

NAME = 'tyler-entered-locations-2026-10-05'
TABLES = ('games', 'vollis_games', 'other_games')
CLEARWATER = {'clearwater, florida', 'clearwater beach'}


def _completed(conn):
    return (conn.execute("SELECT 1 FROM sqlite_master WHERE name='location_migrations'").fetchone()
            and conn.execute('SELECT 1 FROM location_migrations WHERE name=?', (NAME,)).fetchone())


def correct_database(conn, tyler_usernames, identity_database=False):
    """Apply once per database; preserve later manual corrections and new games."""
    if _completed(conn):
        return 0
    conn.row_factory = sqlite3.Row
    conn.execute('BEGIN IMMEDIATE')
    try:
        conn.execute('CREATE TABLE IF NOT EXISTS location_migrations (name TEXT PRIMARY KEY)')
        if _completed(conn):
            conn.commit()
            return 0
        conn.execute('''CREATE TABLE IF NOT EXISTS location_migration_audit (
            migration TEXT, game_key TEXT, before_json TEXT, new_location TEXT,
            PRIMARY KEY (migration, game_key))''')
        changed = 0
        for table in TABLES:
            columns = {row['name'] for row in conn.execute(f'PRAGMA table_info({table})')}
            if 'location' not in columns:
                continue
            for row in conn.execute(f'SELECT * FROM {table}').fetchall():
                old = (row['location'] or '').strip()
                owner = (row['entered_by'] or '').strip().casefold() if 'entered_by' in columns else ''
                new = ('The Oasis' if not old and owner in tyler_usernames else
                       'Clearwater Beach' if old.casefold() in CLEARWATER else None)
                if new is None or row['location'] == new:
                    continue
                conn.execute('INSERT INTO location_migration_audit VALUES (?,?,?,?)',
                             (NAME, f'{table}:{row["id"]}', json.dumps(dict(row)), new))
                timestamp = ", updated_at=datetime('now')" if 'updated_at' in columns else ''
                conn.execute(f'UPDATE {table} SET location=?{timestamp} WHERE id=?', (new, row['id']))
                changed += 1
        if identity_database:
            for row in conn.execute('SELECT username,last_location FROM site_users').fetchall():
                old = (row['last_location'] or '').strip()
                new = ('The Oasis' if row['username'].strip().casefold() in tyler_usernames else
                       'Clearwater Beach' if old.casefold() in CLEARWATER else None)
                if new is not None and row['last_location'] != new:
                    conn.execute('INSERT INTO location_migration_audit VALUES (?,?,?,?)',
                                 (NAME, 'user:' + row['username'], json.dumps(dict(row)), new))
                    conn.execute('UPDATE site_users SET last_location=? WHERE username=?', (new, row['username']))
        conn.execute('INSERT INTO location_migrations VALUES (?)', (NAME,))
        conn.commit()
        return changed
    except Exception:
        conn.rollback()
        raise


def migrate(site_database):
    """Correct the deployed shared and existing personal databases, then report."""
    site_database = Path(site_database).resolve()
    with sqlite3.connect(site_database) as conn:
        conn.row_factory = sqlite3.Row
        tyler_usernames = {'tyler'} | {
            row['username'].strip().casefold() for row in conn.execute('SELECT username,player_name FROM site_users')
            if (row['player_name'] or '').strip().casefold() == 'tyler weston'
        }
        accounts = (conn.execute('SELECT id,username FROM private_accounts').fetchall()
                    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='private_accounts'").fetchone() else [])
    private_root = Path(os.environ.get('STATS_PRIVATE_DATA_DIR') or site_database.parent / 'private_data')
    databases = [(site_database, 'KT Stats')] + [
        (private_root / (row['id'] + '.db'), row['username']) for row in accounts
        if (private_root / (row['id'] + '.db')).is_file()
    ]
    results = []
    for path, owner in databases:
        with sqlite3.connect('file:' + str(path) + '?mode=rw', uri=True, timeout=30) as conn:
            applied_now = correct_database(conn, tyler_usernames, path == site_database)
            changes = Counter()
            for row in conn.execute('SELECT game_key,new_location FROM location_migration_audit WHERE migration=?', (NAME,)):
                if not row[0].startswith('user:'):
                    changes[row[1]] += 1
            missing_tyler = noncanonical_clearwater = 0
            for table in TABLES:
                columns = {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}
                if 'location' not in columns:
                    continue
                noncanonical_clearwater += conn.execute(
                    f"SELECT count(*) FROM {table} WHERE lower(trim(location)) IN ('clearwater, florida','clearwater beach') AND location != 'Clearwater Beach'"
                ).fetchone()[0]
                if 'entered_by' in columns:
                    placeholders = ','.join('?' for _ in tyler_usernames)
                    missing_tyler += conn.execute(
                        f"SELECT count(*) FROM {table} WHERE lower(trim(entered_by)) IN ({placeholders}) AND trim(coalesce(location,''))=''",
                        sorted(tyler_usernames)).fetchone()[0]
            results.append(dict(owner=owner, applied_now=applied_now, corrected_locations=dict(changes),
                                missing_tyler=missing_tyler, noncanonical_clearwater=noncanonical_clearwater))
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=site_database.parent, text=True).strip()
    report = dict(migration=NAME, revision=revision, databases=results)
    destination = site_database.parent / 'backups' / NAME / 'report.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=destination.parent, delete=False) as output:
        json.dump(report, output, indent=2)
        temporary = output.name
    os.replace(temporary, destination)
    return report
