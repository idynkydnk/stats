"""Preserve the person who entered a game independently of later edits."""


def ensure_game_entry_owner(conn, table):
    if table not in {'games', 'vollis_games'}:
        raise ValueError('Unsupported game table')
    columns = {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}
    if not columns or 'entered_by' in columns:
        return
    conn.execute(f'ALTER TABLE {table} ADD COLUMN entered_by TEXT')
    if table == 'games' and 'updated_by' in columns:
        # Older doubles games only recorded the last editor; preserve the available
        # attribution once, before any future edits can change it.
        conn.execute('UPDATE games SET entered_by = updated_by')
