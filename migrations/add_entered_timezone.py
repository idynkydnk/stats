#!/usr/bin/env python3
"""Add entered_timezone column to games, vollis_games, other_games. Run once."""
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
    for table in ('games', 'vollis_games', 'other_games'):
        try:
            cur.execute(f'ALTER TABLE {table} ADD COLUMN entered_timezone TEXT')
            print(f'{table}: added entered_timezone')
        except sqlite3.OperationalError as e:
            if 'duplicate column' in str(e).lower():
                print(f'{table}: entered_timezone already exists')
            else:
                raise
    conn.commit()
    conn.close()
    print('Done.')

if __name__ == '__main__':
    main()
