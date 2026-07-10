#!/usr/bin/env python3
"""Add full_body_photo_paths JSON column. Run once (safe to re-run)."""
import json
import os
import sqlite3

DB_PATHS = [
    '/home/Idynkydnk/stats/stats.db',
    os.path.join(os.path.dirname(os.path.dirname(__file__)), 'stats.db'),
]


def migrate(db_path):
    if not os.path.isfile(db_path):
        return False
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute('PRAGMA table_info(players)')
    cols = [row[1] for row in cur.fetchall()]
    if 'full_body_photo_paths' not in cols:
        cur.execute('ALTER TABLE players ADD COLUMN full_body_photo_paths TEXT')
        print(f'Added full_body_photo_paths column to {db_path}')
    cur.execute(
        'SELECT id, full_body_photo_path, full_body_photo_paths FROM players '
        'WHERE full_body_photo_path IS NOT NULL AND full_body_photo_path != ""'
    )
    for player_id, legacy_path, paths_json in cur.fetchall():
        if paths_json:
            continue
        cur.execute(
            'UPDATE players SET full_body_photo_paths = ?, full_body_photo_path = NULL WHERE id = ?',
            (json.dumps([legacy_path]), player_id),
        )
    conn.commit()
    conn.close()
    return True


if __name__ == '__main__':
    for path in DB_PATHS:
        migrate(path)
