"""Request-local location filtering for read-only statistics queries.

Temporary views affect only the connection opened for a stats read. Existing
queries (including ranking and aggregate queries) therefore use the same subset,
without changing stored games or leaking a filter to another request.
"""
from flask import has_request_context, request

STATS_ENDPOINTS = {
    'index', 'stats', 'stats_default', 'stats_by_date', 'games', 'games_default',
    'vollis_stats', 'vollis_stats_default', 'vollis_games', 'vollis_games_default',
    'other_stats', 'other_stats_default', 'other_games', 'other_games_default',
    'other_games_by_name', 'player_stats', 'vollis_player_stats', 'other_player_stats',
    'player_network', 'player_network_default', 'single_game_stats',
    'single_game_stats_with_year', 'volleyball_stats', 'volleyball_stats_default',
    'volleyball_player_stats', 'game_name_stats', 'game_name_stats_with_year',
    'player_game_stats',
}


def active_location_filter():
    if not has_request_context() or request.method != 'GET' or request.endpoint not in STATS_ENDPOINTS:
        return '', False
    return request.args.get('location', '').strip(), request.args.get('missing') == '1'


def filter_stats_connection(conn, table):
    from doubles_division import active_doubles_division
    location, missing = active_location_filter()
    if table not in {'games', 'vollis_games', 'other_games'}:
        raise ValueError('Unknown game table')
    clauses = []
    if location or missing:
        value = conn.execute('SELECT quote(?)', (location,)).fetchone()[0]
        clauses.append("TRIM(COALESCE(location, ''))=''" if missing else f'TRIM(location)={value} COLLATE NOCASE')
    division = active_doubles_division() if table == 'games' else None
    if division:
        columns = {row[1] for row in conn.execute('PRAGMA main.table_info(games)')}
        if 'division' in columns:
            value = conn.execute('SELECT quote(?)', (division,)).fetchone()[0]
            clauses.append(f"COALESCE(division, 'open')={value}")
        elif division == 'women':
            clauses.append('0')
    if clauses:
        conn.execute(f'CREATE TEMP VIEW {table} AS SELECT * FROM main.{table} WHERE ' + ' AND '.join(clauses))
