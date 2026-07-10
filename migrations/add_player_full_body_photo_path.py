#!/usr/bin/env python3
"""Add full_body_photo_path column to players table. Run once (safe to re-run)."""
import sqlite3
import os

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
    if 'full_body_photo_path' not in cols:
        cur.execute('ALTER TABLE players ADD COLUMN full_body_photo_path TEXT')
        conn.commit()
        print(f'Added full_body_photo_path column to {db_path}')
    else:
        print(f'full_body_photo_path column already exists in {db_path}')
    conn.close()
    return True


if __name__ == '__main__':
    for path in DB_PATHS:
        migrate(path)
