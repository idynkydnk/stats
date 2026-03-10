#!/usr/bin/env python3
"""Create doubles_player_last_played table and backfill from existing games. Run once."""
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
    cur.execute('''
        CREATE TABLE IF NOT EXISTS doubles_player_last_played (
            player_name TEXT PRIMARY KEY,
            last_game_date TEXT NOT NULL
        )
    ''')
    print('doubles_player_last_played: table created or exists')
    cur.execute("SELECT COUNT(*) FROM doubles_player_last_played")
    if cur.fetchone()[0] > 0:
        print('Table already has rows; skipping backfill. To re-backfill, DELETE FROM doubles_player_last_played first.')
        conn.close()
        return
    cur.execute("SELECT game_date, winner1, winner2, loser1, loser2 FROM games ORDER BY game_date DESC")
    rows = cur.fetchall()
    for row in rows:
        game_date, w1, w2, l1, l2 = row[0], row[1], row[2], row[3], row[4]
        for name in (w1, w2, l1, l2):
            if name and isinstance(name, str) and name.strip():
                cur.execute(
                    "INSERT OR IGNORE INTO doubles_player_last_played (player_name, last_game_date) VALUES (?, ?)",
                    (name.strip(), game_date)
                )
    conn.commit()
    n = cur.execute("SELECT COUNT(*) FROM doubles_player_last_played").fetchone()[0]
    conn.close()
    print(f'Backfilled {n} players from {len(rows)} games. Done.')

if __name__ == '__main__':
    main()
