#!/usr/bin/env python3
"""Add nickname column to players table."""
import os
import sqlite3


def stats_db_path():
    if os.path.exists('/home/Idynkydnk/stats/stats.db'):
        return '/home/Idynkydnk/stats/stats.db'
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'stats.db')


def main():
    path = stats_db_path()
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute('PRAGMA table_info(players)')
    cols = [row[1] for row in cur.fetchall()]
    if 'nickname' not in cols:
        cur.execute('ALTER TABLE players ADD COLUMN nickname TEXT')
        conn.commit()
        print('Added players.nickname')
    else:
        print('players.nickname already exists')
    conn.close()


if __name__ == '__main__':
    main()
