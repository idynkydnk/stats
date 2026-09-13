"""The recap picker shows games entered by the signed-in user."""


def load_ai_summary_games(conn, game_type, username, query='', limit=50):
    from stat_functions import convert_ampm, _search_query_tokens, _multi_token_search_clause
    from vollis_functions import convert_vollis_ampm
    from other_functions import readable_games_data, MAX_OTHER_PLAYERS

    configs = {
        'doubles': ('games', ['winner1', 'winner2', 'loser1', 'loser2', 'comments'], convert_ampm),
        'vollis': ('vollis_games', ['winner', 'loser'], convert_vollis_ampm),
        'other': ('other_games', ['game_name', 'game_type', 'comment'] +
                  [f'{side}{i}' for side in ('winner', 'loser') for i in range(1, MAX_OTHER_PLAYERS + 1)],
                  readable_games_data),
    }
    table, text_columns, convert = configs[game_type]
    if not (username or '').strip():
        return []
    columns = {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}
    if 'entered_by' not in columns:
        return []
    owner_clause = 'TRIM(entered_by) = ? COLLATE NOCASE'
    params = [username.strip()]
    tokens = _search_query_tokens(query)
    if tokens:
        clause, search_params = _multi_token_search_clause(tokens, text_columns)
        rows = conn.execute(
            f'SELECT * FROM {table} WHERE {owner_clause} AND ({clause}) '
            'ORDER BY game_date DESC, id DESC LIMIT ?',
            params + search_params + [limit],
        ).fetchall()
    else:
        # Keep the whole latest day even when it exceeds the usual browse limit.
        rows = conn.execute(
            f'''WITH mine AS (SELECT * FROM {table} WHERE {owner_clause})
                SELECT * FROM mine
                WHERE id IN (SELECT id FROM mine ORDER BY game_date DESC, id DESC LIMIT ?)
                   OR substr(game_date, 1, 10) = (SELECT substr(MAX(game_date), 1, 10) FROM mine)
                ORDER BY game_date DESC, id DESC''',
            params + [limit],
        ).fetchall()
    return convert(rows)
