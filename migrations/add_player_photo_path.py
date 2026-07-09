#!/usr/bin/env python3
"""Add photo_path column to players table. Run once (safe to re-run)."""
import os
import sqlite3


def get_db():
    if os.path.exists('/home/Idynkydnk/stats/stats.db'):
        return '/home/Idynkydnk/stats/stats.db'
    return 'stats.db'


def main():
    conn = sqlite3.connect(get_db())
    cur = conn.cursor()
    cur.execute('PRAGMA table_info(players)')
    cols = [row[1] for row in cur.fetchall()]
    if 'photo_path' not in cols:
        cur.execute('ALTER TABLE players ADD COLUMN photo_path TEXT')
        conn.commit()
        print('Added photo_path column to players table.')
    else:
        print('photo_path column already exists.')
    conn.close()


if __name__ == '__main__':
    main()
