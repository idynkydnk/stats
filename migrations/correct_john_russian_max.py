"""Correct John Moran's October 9 games using the identity confirmed by Kyle."""
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile

NAME = 'john-russian-max-2026-10-09'
DAY = '2026-10-09'
TARGET = 'Max Chicherin'
TABLES = ('games', 'vollis_games', 'other_games')


def correct_database(conn, usernames, personal=False):
    conn.row_factory = sqlite3.Row
    conn.execute('BEGIN IMMEDIATE')
    try:
        conn.execute('''CREATE TABLE IF NOT EXISTS player_correction_audit (
            correction TEXT, game_key TEXT, before_json TEXT,
            PRIMARY KEY(correction, game_key))''')
        for table in TABLES:
            columns = {r['name'] for r in conn.execute(f'PRAGMA table_info({table})')}
            if 'game_date' not in columns:
                continue
            slots = sorted(c for c in columns if re.fullmatch(r'(winner|loser)\d*', c))
            for row in conn.execute(f'SELECT * FROM {table} WHERE substr(game_date,1,10)=?', (DAY,)).fetchall():
                owner = (row['entered_by'] or '').strip().casefold() if 'entered_by' in columns else ''
                if not personal and owner not in usernames:
                    continue
                replacements = [c for c in slots if (row[c] or '').strip().casefold() == 'russian max']
                if not replacements:
                    continue
                key = f'{table}:{row["id"]}'
                if conn.execute('SELECT 1 FROM player_correction_audit WHERE correction=? AND game_key=?', (NAME, key)).fetchone():
                    continue
                if any((row[c] or '').strip().casefold() == TARGET.casefold() for c in slots):
                    raise ValueError(f'{key} already contains {TARGET}; refusing duplicate player')
                conn.execute('INSERT INTO player_correction_audit VALUES (?,?,?)', (NAME, key, json.dumps(dict(row))))
                assignments = ', '.join(f'{c}=?' for c in replacements)
                if 'updated_at' in columns:
                    assignments += ", updated_at=datetime('now')"
                conn.execute(f'UPDATE {table} SET {assignments} WHERE id=?', [TARGET] * len(replacements) + [row['id']])
        changes = [dict(r) for r in conn.execute('SELECT game_key,before_json FROM player_correction_audit WHERE correction=?', (NAME,))]
        # Rebuild just the affected suggestion entries from actual doubles history.
        if changes and conn.execute("SELECT 1 FROM sqlite_master WHERE name='doubles_player_last_played'").fetchone():
            for name in (TARGET, 'Russian Max'):
                latest = conn.execute('''SELECT max(game_date) FROM games WHERE
                    lower(trim(winner1))=lower(?) OR lower(trim(winner2))=lower(?) OR
                    lower(trim(loser1))=lower(?) OR lower(trim(loser2))=lower(?)''', (name,) * 4).fetchone()[0]
                conn.execute('DELETE FROM doubles_player_last_played WHERE lower(trim(player_name))=lower(?)', (name,))
                if latest:
                    conn.execute('INSERT INTO doubles_player_last_played(player_name,last_game_date) VALUES (?,?)', (name, latest))
        verified = []
        for change in changes:
            table, row_id = change['game_key'].split(':')
            after = dict(conn.execute(f'SELECT * FROM {table} WHERE id=?', (row_id,)).fetchone())
            verified.append(dict(game_key=change['game_key'], before=json.loads(change['before_json']), after=after))
        conn.commit()
        return verified
    except Exception:
        conn.rollback()
        raise


def migrate(site_database):
    site_database = Path(site_database).resolve()
    destination = site_database.parent / 'backups' / NAME / 'report.json'
    if destination.exists():
        return
    with sqlite3.connect(site_database) as conn:
        usernames = {r[0].strip().casefold() for r in conn.execute(
            "SELECT username FROM site_users WHERE lower(trim(player_name))='john moran'")}
        if not usernames:
            raise ValueError('John Moran account not found')
        accounts = [(r[0], r[1]) for r in conn.execute('SELECT id,username FROM private_accounts')
                    if r[1].strip().casefold() in usernames]
    private_root = Path(os.environ.get('STATS_PRIVATE_DATA_DIR') or site_database.parent / 'private_data')
    databases = [(site_database, 'KT Stats', False)] + [
        (private_root / (account_id + '.db'), username, True) for account_id, username in accounts]
    results = []
    for path, owner, personal in databases:
        if not path.is_file():
            continue
        with sqlite3.connect('file:' + str(path) + '?mode=rw', uri=True, timeout=30) as conn:
            changes = correct_database(conn, usernames, personal)
            results.append(dict(owner=owner, corrected=len(changes), games=changes))
    report = dict(correction=NAME, databases=results)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=destination.parent, delete=False) as output:
        json.dump(report, output, indent=2)
        temporary = output.name
    os.replace(temporary, destination)
    return report
