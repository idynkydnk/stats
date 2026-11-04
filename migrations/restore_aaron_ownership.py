"""Restore 5 backup-verified games to their personal accounts, atomically."""
import json
import os
from pathlib import Path
import sqlite3

NAME = 'restore-aaron-ownership-20261103'


def migrate(path):
    path = Path(path).resolve()
    records = json.loads(Path(__file__).with_suffix('.json').read_text())
    root = Path(os.environ.get('STATS_PRIVATE_DATA_DIR') or path.parent / 'private_data')
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('CREATE TABLE IF NOT EXISTS ownership_restoration_audit (migration TEXT, game_id INTEGER, owner TEXT, before_json TEXT, PRIMARY KEY(migration,game_id))')
        if conn.execute('SELECT count(*) FROM ownership_restoration_audit WHERE migration=?', (NAME,)).fetchone()[0] == len(records):
            return
        paths = {}
        for owner in ('aaron',):
            accounts = conn.execute('SELECT id FROM private_accounts WHERE lower(username)=?', (owner,)).fetchall()
            if len(accounts) != 1:
                raise ValueError('Expected one personal account for ' + owner)
            destination = root / (accounts[0]['id'] + '.db')
            if not destination.is_file():
                raise ValueError('Missing personal database for ' + owner)
            paths[owner] = destination
        # Back up both databases before moving anything.
        backup = path.parent / 'backups' / NAME
        backup.mkdir(parents=True, exist_ok=True)
        for label, source in [('stats', path), *paths.items()]:
            target = backup / (label + '.db')
            if not target.exists():
                with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
                    src.backup(dst)
                    assert dst.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        for owner, destination in paths.items():
            conn.execute('ATTACH DATABASE ? AS ' + owner, (str(destination),))
        for db in ('main', 'aaron'):
            if conn.execute('PRAGMA '+db+'.journal_mode').fetchone()[0].lower() == 'wal':
                raise ValueError('Rollback journal mode required for atomic move')
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('CREATE TABLE IF NOT EXISTS deleted_records (id INTEGER PRIMARY KEY, kind TEXT NOT NULL, record_id INTEGER NOT NULL, deleted_at TEXT NOT NULL)')
        for item in records:
            game_id, owner = item['id'], item['owner']
            if conn.execute('SELECT 1 FROM ownership_restoration_audit WHERE migration=? AND game_id=?', (NAME, game_id)).fetchone():
                continue
            row = conn.execute('SELECT * FROM main.games WHERE id=?', (game_id,)).fetchone()
            if row is None or [row[k] for k in ('winner1','winner2','loser1','loser2')] != item['players'] or (row['entered_by'] or '').lower() != 'kyle':
                raise ValueError('Source game changed: ' + str(game_id))
            record = dict(row)
            conn.execute('INSERT INTO ownership_restoration_audit VALUES (?,?,?,?)', (NAME, game_id, owner, json.dumps(record)))
            record['entered_by'] = owner
            record['updated_at'] = conn.execute("SELECT datetime('now')").fetchone()[0]
            cols = ','.join('"'+c+'"' for c in record)
            conn.execute('INSERT INTO '+owner+'.games ('+cols+') VALUES ('+','.join('?' for _ in record)+')', list(record.values()))
            conn.execute('DELETE FROM main.games WHERE id=?', (game_id,))
            conn.execute("INSERT INTO deleted_records(kind,record_id,deleted_at) VALUES ('doubles_game',?,datetime('now'))", (game_id,))
        for db in ('main', 'aaron'):
            for table in ('trueskill_rankings', 'doubles_player_last_played', 'sessions'):
                if conn.execute('SELECT 1 FROM '+db+'.sqlite_master WHERE name=?', (table,)).fetchone():
                    conn.execute('DELETE FROM '+db+'.'+table)
        conn.commit()
        (backup / 'report.json').write_text(json.dumps({'migration':NAME,'moved':{'aaron':5}}, indent=2))
