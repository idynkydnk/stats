#!/usr/bin/env python3
"""
One-time script: add 1 hour to game_date and updated_at in all game tables.
Use this to fix games that were stored in server time (e.g. EST) during DST,
so they were 1 hour early. Run from project root: python fix_game_times_dst.py
"""
import os
import sqlite3

def get_database_path():
    if os.path.exists('/home/Idynkydnk/stats/stats.db'):
        return '/home/Idynkydnk/stats/stats.db'
    return 'stats.db'

def main():
    db = get_database_path()
    if not os.path.exists(db):
        print(f'Database not found: {db}')
        return
    conn = sqlite3.connect(db)
    cur = conn.cursor()

    updates = []

    # games: game_date, updated_at
    cur.execute("SELECT COUNT(*) FROM games")
    n = cur.fetchone()[0]
    if n > 0:
        cur.execute("""
            UPDATE games
            SET game_date = datetime(game_date, '+1 hour'),
                updated_at = datetime(updated_at, '+1 hour')
        """)
        updates.append(('games', cur.rowcount))

    # vollis_games: game_date, updated_at (vollis has 6 data cols: game_date, winner, winner_score, loser, loser_score, updated_at)
    cur.execute("SELECT COUNT(*) FROM vollis_games")
    n = cur.fetchone()[0]
    if n > 0:
        cur.execute("""
            UPDATE vollis_games
            SET game_date = datetime(game_date, '+1 hour'),
                updated_at = datetime(updated_at, '+1 hour')
        """)
        updates.append(('vollis_games', cur.rowcount))

    # other_games: game_date, updated_at
    cur.execute("SELECT COUNT(*) FROM other_games")
    n = cur.fetchone()[0]
    if n > 0:
        cur.execute("""
            UPDATE other_games
            SET game_date = datetime(game_date, '+1 hour'),
                updated_at = datetime(updated_at, '+1 hour')
        """)
        updates.append(('other_games', cur.rowcount))

    conn.commit()
    conn.close()

    if updates:
        print('Added 1 hour to game_date and updated_at:')
        for table, count in updates:
            print(f'  {table}: {count} row(s) updated')
    else:
        print('No game tables had rows to update.')

if __name__ == '__main__':
    main()
