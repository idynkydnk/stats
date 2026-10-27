"""Fill the May 27–June 1, 2019 location gaps requested October 27, 2026."""
import json
import sqlite3


NAME = 'clearwater-may-2019-2026-10-27'
START = '2019-05-27'
END = '2019-06-01'
LOCATION = 'Clearwater Beach'
TABLES = ('games', 'vollis_games', 'other_games')


def _completed(conn):
    return (conn.execute("SELECT 1 FROM sqlite_master WHERE name='location_migrations'").fetchone()
            and conn.execute('SELECT 1 FROM location_migrations WHERE name=?', (NAME,)).fetchone())


def correct_database(conn):
    """Fill only missing locations once, retaining original rows for reversal."""
    if _completed(conn):
        return 0
    conn.row_factory = sqlite3.Row
    conn.execute('BEGIN IMMEDIATE')
    try:
        conn.execute('CREATE TABLE IF NOT EXISTS location_migrations (name TEXT PRIMARY KEY)')
        if _completed(conn):
            conn.commit()
            return 0
        conn.execute('''CREATE TABLE IF NOT EXISTS location_migration_audit (
            migration TEXT, game_key TEXT, before_json TEXT, new_location TEXT,
            PRIMARY KEY (migration, game_key))''')
        changed = 0
        for table in TABLES:
            rows = conn.execute(f'''SELECT * FROM {table}
                WHERE substr(game_date,1,10) BETWEEN ? AND ?
                AND trim(coalesce(location,''))='' ''', (START, END)).fetchall()
            for row in rows:
                conn.execute('INSERT INTO location_migration_audit VALUES (?,?,?,?)',
                             (NAME, f'{table}:{row["id"]}', json.dumps(dict(row)), LOCATION))
                conn.execute(f"UPDATE {table} SET location=?, updated_at=datetime('now') WHERE id=?",
                             (LOCATION, row['id']))
                changed += 1
        conn.execute('INSERT INTO location_migrations VALUES (?)', (NAME,))
        conn.commit()
        return changed
    except Exception:
        conn.rollback()
        raise


def migrate(site_database):
    """Correct only the shared history shown in the public location list."""
    with sqlite3.connect('file:' + str(site_database) + '?mode=rw', uri=True, timeout=30) as conn:
        return correct_database(conn)
