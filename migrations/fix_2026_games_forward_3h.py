#!/usr/bin/env python3
"""Move all 2026 games forward 3 hours and set timezone to America/New_York. Run once."""
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
    tz_val = 'America/New_York'
    for table in ('games', 'vollis_games', 'other_games'):
        cur.execute(
            f"""UPDATE {table}
               SET game_date = datetime(game_date, '+3 hours'),
                   updated_at = datetime(updated_at, '+3 hours'),
                   entered_timezone = ?
               WHERE strftime('%Y', game_date) = '2026'""",
            (tz_val,)
        )
        n = cur.rowcount
        print(f'{table}: updated {n} row(s)')
    conn.commit()
    conn.close()
    print('Done.')

if __name__ == '__main__':
    main()
