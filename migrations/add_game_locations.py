"""Add game locations and the per-user last-location preference.

The web app also runs this migration defensively at startup. This script is
provided for deployments that apply schema changes explicitly.
"""

import os
import sqlite3


def migrate(db_path):
    conn = sqlite3.connect(db_path)
    try:
        for table in ('games', 'vollis_games', 'other_games'):
            columns = {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}
            if columns and 'location' not in columns:
                conn.execute(f'ALTER TABLE {table} ADD COLUMN location TEXT')

        user_columns = {row[1] for row in conn.execute('PRAGMA table_info(site_users)')}
        if user_columns and 'last_location' not in user_columns:
            conn.execute('ALTER TABLE site_users ADD COLUMN last_location TEXT')
        conn.commit()
    finally:
        conn.close()


if __name__ == '__main__':
    path = os.environ.get('STATS_DB_PATH', 'stats.db')
    migrate(path)
    print(f'Game location migration complete: {path}')
