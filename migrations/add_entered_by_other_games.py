#!/usr/bin/env python3
"""Add entered_by column to other_games. Run once."""
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
        cur.execute('ALTER TABLE other_games ADD COLUMN entered_by TEXT')
        print('other_games: added entered_by')
    except sqlite3.OperationalError as e:
        if 'duplicate column' in str(e).lower():
            print('other_games: entered_by already exists')
        else:
            raise
    conn.commit()
    conn.close()
    print('Done.')

if __name__ == '__main__':
    main()
