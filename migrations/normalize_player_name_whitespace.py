#!/usr/bin/env python3
"""Canonicalize legacy player names without losing any games.

This migration removes leading/trailing whitespace from player columns in all
game tables, then rebuilds the doubles last-played cache. It is idempotent and
keeps every game row and score intact.
"""

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from player_identity import canonical_player_name


PLAYER_COLUMNS = {
    'games': ('winner1', 'winner2', 'loser1', 'loser2'),
    'vollis_games': ('winner', 'loser'),
    'other_games': tuple(
        [f'winner{i}' for i in range(1, 16)]
        + [f'loser{i}' for i in range(1, 16)]
    ),
}


def _table_columns(conn, table):
    return {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}


def normalize_player_names(conn):
    """Normalize player columns and return changed row IDs by table."""
    changed = {table: [] for table in PLAYER_COLUMNS}
    with conn:
        for table, configured_columns in PLAYER_COLUMNS.items():
            available = _table_columns(conn, table)
            columns = [column for column in configured_columns if column in available]
            if not columns or 'id' not in available:
                continue
            rows = conn.execute(
                f"SELECT id, {', '.join(columns)} FROM {table}"
            ).fetchall()
            for row in rows:
                values = list(row[1:])
                normalized = [canonical_player_name(value) for value in values]
                if values == normalized:
                    continue
                assignments = ', '.join(f'{column} = ?' for column in columns)
                conn.execute(
                    f'UPDATE {table} SET {assignments} WHERE id = ?',
                    (*normalized, row[0]),
                )
                changed[table].append(row[0])

        _rebuild_doubles_last_played(conn)
    return changed


def _rebuild_doubles_last_played(conn):
    if not {'games', 'doubles_player_last_played'}.issubset(
        row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    ):
        return
    conn.execute('DELETE FROM doubles_player_last_played')
    rows = conn.execute(
        'SELECT game_date, winner1, winner2, loser1, loser2 '
        'FROM games ORDER BY game_date DESC'
    ).fetchall()
    for game_date, *names in rows:
        for name in names:
            name = canonical_player_name(name)
            if name:
                conn.execute(
                    'INSERT OR IGNORE INTO doubles_player_last_played '
                    '(player_name, last_game_date) VALUES (?, ?)',
                    (name, game_date),
                )


def _database_path(value=None):
    if value:
        return Path(value)
    production = Path('/home/Idynkydnk/stats/stats.db')
    return production if production.exists() else Path('stats.db')


def _backup(path):
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup = path.with_name(f'{path.name}.before-player-name-normalization-{stamp}.bak')
    shutil.copy2(path, backup)
    return backup


def _sync_doubles_rows(conn, game_ids):
    if not game_ids:
        return {'updated': 0, 'failed': 0, 'not_configured': 0}
    try:
        from supabase_games import update_game
    except ImportError:
        return {'updated': 0, 'failed': 0, 'not_configured': len(game_ids)}
    conn.row_factory = sqlite3.Row
    report = {'updated': 0, 'failed': 0, 'not_configured': 0}
    for game_id in game_ids:
        row = conn.execute('SELECT * FROM games WHERE id = ?', (game_id,)).fetchone()
        result = update_game(game_id, dict(row))
        key = 'updated' if result is True else 'failed' if result is False else 'not_configured'
        report[key] += 1
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', help='SQLite database path')
    parser.add_argument('--no-backup', action='store_true')
    parser.add_argument('--no-supabase', action='store_true')
    args = parser.parse_args()

    path = _database_path(args.database)
    if not path.exists():
        raise SystemExit(f'Database not found: {path}')
    backup = None if args.no_backup else _backup(path)
    conn = sqlite3.connect(path)
    try:
        changed = normalize_player_names(conn)
        sync = (
            {'updated': 0, 'failed': 0, 'not_configured': 0}
            if args.no_supabase
            else _sync_doubles_rows(conn, changed['games'])
        )
    finally:
        conn.close()

    if backup:
        print(f'Backup: {backup}')
    print('Changed rows: ' + ', '.join(f'{table}={len(ids)}' for table, ids in changed.items()))
    if not args.no_supabase:
        print('Supabase: ' + ', '.join(f'{key}={value}' for key, value in sync.items()))


if __name__ == '__main__':
    main()
