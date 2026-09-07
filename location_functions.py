"""Browse and edit locations without changing game results."""
import sqlite3

TABLES = {'doubles': 'games', 'vollis': 'vollis_games', 'other': 'other_games'}


def backfill_2011(conn):
    """Apply the historical correction once, preserving later manual edits."""
    with conn:
        conn.execute('CREATE TABLE IF NOT EXISTS location_migrations (name TEXT PRIMARY KEY)')
        if conn.execute("SELECT 1 FROM location_migrations WHERE name='2011-new-jersey'").fetchone():
            return 0
        count = 0
        for table in TABLES.values():
            count += conn.execute(
                f"UPDATE {table} SET location='New Jersey' WHERE strftime('%Y', game_date)='2011'"
            ).rowcount
        conn.execute("INSERT INTO location_migrations VALUES ('2011-new-jersey')")
    return count


def location_games(conn, year, location='', missing=False):
    conn.row_factory = sqlite3.Row
    result = []
    for kind, table in TABLES.items():
        clauses, params = [], []
        if year != 'All years':
            clauses.append("strftime('%Y', game_date)=?")
            params.append(year)
        if missing:
            clauses.append("TRIM(COALESCE(location, ''))=''")
        elif location:
            clauses.append('TRIM(location)=? COLLATE NOCASE')
            params.append(location)
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        for row in conn.execute(f'SELECT * FROM {table}' + where, params):
            game = dict(row)
            game['kind'] = kind
            game['key'] = f'{kind}:{row["id"]}'
            teams = []
            for side in ('winner', 'loser'):
                names = [str(value) for name, value in game.items()
                         if value and (name == side or
                                       name.startswith(side) and name[len(side):].isdigit())]
                teams.append(' / '.join(names))
            game['teams'] = ' vs '.join(teams)
            result.append(game)
    return sorted(result, key=lambda g: (g['game_date'], g['id']), reverse=True)


def assign_locations(conn, keys, location, username):
    """Validate the whole selection before updating; return doubles rows for sync."""
    if len(location) > 160:
        raise ValueError('Use a location of 160 characters or fewer.')
    selection = []
    for key in set(keys):
        kind, separator, raw_id = key.partition(':')
        if kind not in TABLES or not separator or not raw_id.isdigit():
            raise ValueError('Invalid game selection.')
        selection.append((kind, int(raw_id)))
    if not selection:
        raise ValueError('Select at least one game.')
    conn.row_factory = sqlite3.Row
    doubles = []
    with conn:
        for kind, game_id in selection:
            table = TABLES[kind]
            if not conn.execute(f'SELECT id FROM {table} WHERE id=?', (game_id,)).fetchone():
                raise ValueError('A selected game no longer exists. Reload and try again.')
            extra = ', updated_by=?' if kind == 'doubles' else ''
            params = [location, username, game_id] if kind == 'doubles' else [location, game_id]
            conn.execute(f"UPDATE {table} SET location=?, updated_at=datetime('now'){extra} WHERE id=?", params)
            if kind == 'doubles':
                doubles.append(dict(conn.execute('SELECT * FROM games WHERE id=?', (game_id,)).fetchone()))
    return len(selection), doubles
