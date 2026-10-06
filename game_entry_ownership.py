"""Preserve the person who entered a game independently of later edits."""


def editable_game_ids(conn, table, game_ids, username, admin=False):
    """Only the original entrant or an admin can edit a game."""
    if table not in {'games', 'vollis_games', 'other_games'}:
        raise ValueError('Unsupported game table')
    # Combined-view IDs cannot be edited through the owner database.
    ids = {i for i in game_ids if 0 < i < (1 << 32)}
    username = (username or '').strip()
    if not username or not ids:
        return set()
    if admin:
        return ids
    columns = {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}
    if 'entered_by' not in columns:
        return set()
    owned = set()
    # Keep large yearly lists below SQLite's parameter limit.
    ids_list = list(ids)
    for start in range(0, len(ids_list), 500):
        batch = ids_list[start:start + 500]
        placeholders = ','.join('?' for _ in batch)
        owned.update(row[0] for row in conn.execute(
            f'SELECT id FROM {table} WHERE id IN ({placeholders}) '
            'AND TRIM(entered_by) = ? COLLATE NOCASE', [*batch, username]))
    return owned


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
