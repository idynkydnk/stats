"""Back up and move attributed games to each existing non-Kyle account.

Run during maintenance with web/AI writers stopped:
    python migrations/separate_existing_accounts.py --database /path/stats.db --apply
The default is a read-only ownership report. Unknown entrants stay with KT Stats.
"""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from private_accounts import init_accounts, provision_database
from account_stats_views import GAME_TABLES, init_stats_views

MIGRATION = 'separate-existing-accounts-v1'


def backup_databases(path):
    path = Path(path).resolve()
    root = path.parent / 'backups' / ('before-personal-databases-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    root.mkdir(mode=0o700, parents=True)
    private_root = Path(os.environ.get('STATS_PRIVATE_DATA_DIR') or path.parent / 'private_data')
    files = [path] + sorted(private_root.glob('*.db'))
    for src in files:
        destination = root / ('stats.db' if src == path else 'private_data/' + src.name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect('file:' + str(src) + '?mode=ro', uri=True) as source, sqlite3.connect(destination) as target:
            source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Backup integrity check failed')
        destination.chmod(0o600)
    (root / 'manifest.json').write_text(json.dumps({'created_at': datetime.now().isoformat(), 'source': str(path), 'databases': len(files)}, indent=2))
    return str(root)


def ownership_report(path):
    with sqlite3.connect('file:' + str(Path(path).resolve()) + '?mode=ro', uri=True) as conn:
        users = conn.execute("SELECT username FROM site_users WHERE lower(trim(username)) != 'kyle'").fetchall()
        report = {}
        for (user,) in users:
            report[user] = {}
            for table in GAME_TABLES:
                cols = {r[1] for r in conn.execute('PRAGMA table_info(' + table + ')')}
                report[user][table] = conn.execute('SELECT count(*) FROM ' + table + ' WHERE trim(entered_by)=? COLLATE NOCASE', (user,)).fetchone()[0] if 'entered_by' in cols else 0
        return report


def migrate(path):
    path = str(Path(path).resolve())
    # No schema or identity changes happen until a verified backup exists.
    backup = backup_databases(path)
    init_accounts(path)
    init_stats_views(path)
    with sqlite3.connect(path) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS personal_database_migrations (
            migration TEXT NOT NULL, username TEXT NOT NULL COLLATE NOCASE,
            completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            counts_json TEXT NOT NULL, PRIMARY KEY(migration, username)
        )''')
        users = conn.execute("SELECT username FROM site_users WHERE lower(trim(username)) != 'kyle'").fetchall()
    moved = {}
    for (username,) in users:
        with sqlite3.connect(path) as conn:
            prior = conn.execute('SELECT counts_json FROM personal_database_migrations WHERE migration=? AND username=?', (MIGRATION, username)).fetchone()
            if prior:
                moved[username] = {'already_migrated': True}
                continue
            account = conn.execute('SELECT id FROM private_accounts WHERE username=?', (username,)).fetchone()
            account_id = account[0] if account else uuid.uuid4().hex
        destination = provision_database(path, account_id)
        # ATTACH uses rollback journals: the move and marker commit together.
        # Refuse WAL mode because it cannot atomically commit across files.
        with sqlite3.connect(path, timeout=30) as conn:
            conn.execute('ATTACH DATABASE ? AS personal', (destination,))
            for db in ('main', 'personal'):
                if conn.execute('PRAGMA ' + db + '.journal_mode').fetchone()[0].lower() == 'wal':
                    raise RuntimeError('Stop writers and use rollback journal mode before migrating')
            conn.execute('BEGIN IMMEDIATE')
            if not account:
                # Startup may capture the existing group before its personal
                # databases are created. Preserve that rollout's sharing default.
                group_member = conn.execute('SELECT 1 FROM stats_source_group WHERE username=?', (username,)).fetchone() is not None
                conn.execute('INSERT INTO private_accounts (id,username,share_stats) VALUES (?,?,?)',
                             (account_id, username, int(group_member)))
            counts = {}
            names = set()
            for table in GAME_TABLES:
                cols = [r[1] for r in conn.execute('PRAGMA main.table_info(' + table + ')')]
                if 'entered_by' not in cols:
                    counts[table] = 0
                    continue
                # Refuse silent overwrites: IDs and complete game data are retained.
                quoted = ','.join('"' + c + '"' for c in cols)
                where = 'trim(entered_by)=? COLLATE NOCASE'
                rows = conn.execute('SELECT ' + quoted + ' FROM main.' + table + ' WHERE ' + where, (username,)).fetchall()
                for row in rows:
                    record = dict(zip(cols, row))
                    for col, value in record.items():
                        if (col.startswith('winner') or col.startswith('loser')) and ('score' not in col) and value:
                            names.add(str(value).strip().casefold())
                conn.execute('INSERT INTO personal.' + table + ' (' + quoted + ') SELECT ' + quoted + ' FROM main.' + table + ' WHERE ' + where, (username,))
                counts[table] = len(rows)
                conn.execute('DELETE FROM main.' + table + ' WHERE ' + where, (username,))
            # Copy only the players in this person's games, with their existing metadata.
            cols = [r[1] for r in conn.execute('PRAGMA main.table_info(players)')]
            if cols:
                quoted = ','.join('"' + c + '"' for c in cols)
                known = {r[0].strip().casefold() for r in conn.execute('SELECT full_name FROM personal.players') if r[0]}
                for row in conn.execute('SELECT ' + quoted + ' FROM main.players').fetchall():
                    record = dict(zip(cols, row))
                    name = (record.get('full_name') or '').strip().casefold()
                    if name in names and name not in known:
                        # Let the personal DB assign player IDs to avoid collisions with earlier personal use.
                        copied_cols = [c for c in cols if c != 'id']
                        conn.execute('INSERT INTO personal.players (' + ','.join('"' + c + '"' for c in copied_cols) + ') VALUES (' + ','.join('?' for _ in copied_cols) + ')', [record[c] for c in copied_cols])
                        known.add(name)
            # Persist an initial combined view for Kyle; all future changes remain preferences.
            conn.execute('INSERT INTO account_stats_sources VALUES (?,?,1) ON CONFLICT(viewer,owner) DO NOTHING', ('kyle', username))
            conn.execute('INSERT INTO account_stats_sources VALUES (?,?,1) ON CONFLICT(viewer,owner) DO NOTHING', (username, 'kyle'))
            for db in ('main', 'personal'):
                for table in ('trueskill_rankings', 'doubles_player_last_played', 'sessions'):
                    if conn.execute('SELECT 1 FROM ' + db + '.sqlite_master WHERE name=?', (table,)).fetchone():
                        conn.execute('DELETE FROM ' + db + '.' + table)
            conn.execute('INSERT INTO personal_database_migrations (migration,username,counts_json) VALUES (?,?,?)', (MIGRATION, username, json.dumps(counts)))
            conn.commit()
            for db in ('main', 'personal'):
                if conn.execute('PRAGMA ' + db + '.integrity_check').fetchone()[0] != 'ok':
                    raise RuntimeError('Post-migration integrity check failed')
            moved[username] = counts
    return dict(backup=backup, moved=moved)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', default='stats.db')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    print(json.dumps(migrate(args.database) if args.apply else ownership_report(args.database), indent=2))
