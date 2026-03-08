#!/usr/bin/env python3
"""Set entered_by for existing other_games rows that have it NULL.
Run once after add_entered_by_other_games.py. Set DEFAULT_USER to the username
who entered most historical games (e.g. 'kyle') so that user sees correct player order."""
import os
import sqlite3

DEFAULT_USER = 'kyle'  # Change if someone else entered the historical games

def get_db():
    if os.path.exists('/home/Idynkydnk/stats/stats.db'):
        return '/home/Idynkydnk/stats/stats.db'
    return 'stats.db'

def main():
    db = get_db()
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute("UPDATE other_games SET entered_by = ? WHERE entered_by IS NULL OR entered_by = ''", (DEFAULT_USER,))
    n = cur.rowcount
    conn.commit()
    conn.close()
    print(f'Backfilled entered_by = {DEFAULT_USER!r} for {n} row(s). Done.')

if __name__ == '__main__':
    main()
