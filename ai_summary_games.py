"""Recap visibility: Kyle can browse everyone; other users see their entries."""


def load_ai_summary_games(conn, game_type, username, query='', limit=50, game_ids=None):
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
    own_clause = 'TRIM(entered_by) = ? COLLATE NOCASE'
    showing_all = username.strip().casefold() == 'kyle'
    owner_clause = '1 = 1' if showing_all else own_clause
    params = [] if showing_all else [username.strip()]
    tokens = _search_query_tokens(query)
    if game_ids is not None:
        ids = list(dict.fromkeys(int(value) for value in game_ids))
        if not ids:
            return []
        placeholders = ','.join('?' for _ in ids)
        rows = conn.execute(
            f'SELECT * FROM {table} WHERE {owner_clause} AND id IN ({placeholders}) '
            'ORDER BY game_date DESC, id DESC', params + ids,
        ).fetchall()
    elif tokens:
        clause, search_params = _multi_token_search_clause(tokens, text_columns)
        rows = conn.execute(
            f'SELECT * FROM {table} WHERE {owner_clause} AND ({clause}) '
            'ORDER BY game_date DESC, id DESC LIMIT ?',
            params + search_params + [limit],
        ).fetchall()
    else:
        # Keep Kyle's own latest day available for the unchanged Select All action,
        # even when newer submissions from others fill the browse limit.
        own_day_clause = ''
        own_day_params = []
        if showing_all:
            own_day_clause = f"""OR ({own_clause} AND substr(game_date, 1, 10) =
                (SELECT substr(MAX(game_date), 1, 10) FROM {table} WHERE {own_clause}))"""
            own_day_params = [username.strip(), username.strip()]
        # Keep the whole latest visible day even when it exceeds the browse limit.
        rows = conn.execute(
            f'''WITH mine AS (SELECT * FROM {table} WHERE {owner_clause})
                SELECT * FROM mine
                WHERE id IN (SELECT id FROM mine ORDER BY game_date DESC, id DESC LIMIT ?)
                   OR substr(game_date, 1, 10) = (SELECT substr(MAX(game_date), 1, 10) FROM mine)
                {own_day_clause}
                ORDER BY game_date DESC, id DESC''',
            params + [limit] + own_day_params,
        ).fetchall()
    return convert(rows)


def load_ai_summary_selection(conn, game_type, username, game_ids):
    """Review only the selected, visible games without generating any AI content."""
    if game_type == 'other' and any(':' in str(value) for value in game_ids):
        from other_functions import readable_games_data
        games = readable_games_data(load_mixed_recap_rows(conn, game_ids, username))
    else:
        games = load_ai_summary_games(conn, game_type, username, game_ids=game_ids)
    if game_type == 'other':
        from other_functions import _other_stats_with_differential
        stats = _other_stats_with_differential(games)
    else:
        from email_content import session_stats_for_illustration
        stats = session_stats_for_illustration(game_type, games)
    return {'games': games, 'stats': stats}


def latest_owned_game_ids(conn, game_type, username):
    """Original browse Select All scope, independent of Kyle's wider visibility."""
    table = {'doubles': 'games', 'vollis': 'vollis_games', 'other': 'other_games'}[game_type]
    columns = {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}
    if 'entered_by' not in columns or not (username or '').strip():
        return []
    return [str(row[0]) for row in conn.execute(
        f"""SELECT id FROM {table} WHERE TRIM(entered_by) = ? COLLATE NOCASE
            AND substr(game_date, 1, 10) = (SELECT substr(MAX(game_date), 1, 10)
                FROM {table} WHERE TRIM(entered_by) = ? COLLATE NOCASE)""",
        [username.strip(), username.strip()],
    )]


def load_mixed_recap_rows(conn, game_ids, username=None):
    """Resolve type-qualified IDs into the shared team-game format."""
    groups = {}
    for value in game_ids:
        kind, separator, ident = str(value).partition(':')
        if not separator or kind not in ('doubles', 'vollis', 'other') or not ident.isdigit():
            raise ValueError('Invalid recap game selection.')
        groups.setdefault(kind, set()).add(int(ident))
    rows = []
    for kind, ids in groups.items():
        table = {'doubles': 'games', 'vollis': 'vollis_games', 'other': 'other_games'}[kind]
        params = sorted(ids)
        where = 'id IN (' + ','.join('?' for _ in params) + ')'
        if username is not None and username.strip().casefold() != 'kyle':
            where += ' AND TRIM(entered_by) = ? COLLATE NOCASE'
            params.append(username.strip())
        cursor = conn.execute(f'SELECT * FROM {table} WHERE {where}', params)
        columns = [column[0] for column in cursor.description]
        for row in cursor.fetchall():
            record = dict(zip(columns, row))
            record['id'] = f"{kind}:{record['id']}"
            if kind != 'other':
                record.update(game_type='Volleyball', game_name='Doubles' if kind == 'doubles' else 'Vollis',
                              comment=record.get('comments', ''), is_tie=False)
                if kind == 'vollis':
                    record.update(winner1=record.get('winner'), loser1=record.get('loser'))
            rows.append(record)
    return sorted(rows, key=lambda row: (row.get('game_date') or '', row['id']), reverse=True)
