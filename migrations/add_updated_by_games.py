#!/usr/bin/env python3
"""Add updated_by column to games table. Run once."""
import os
import sqlite3

def get_db():
    if os.path.exists('/home/Idynkydnk/stats/stats.db'):
        return '/home/Idynkydnk/stats/stats.db'
    return 'stats.db'

def main():
    db = get_db()
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    try:
        cur.execute('ALTER TABLE games ADD COLUMN updated_by TEXT')
        print('games: added updated_by')
    except sqlite3.OperationalError as e:
        if 'duplicate column' in str(e).lower():
            print('games: updated_by already exists')
        else:
            raise
    conn.commit()
    conn.close()
    print('Done.')

if __name__ == '__main__':
    main()
