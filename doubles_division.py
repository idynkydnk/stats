"""Doubles categories and request-local selection."""
from flask import has_request_context, request, session

DIVISIONS = {'open': 'Men’s Doubles', 'women': "Women’s Doubles"}
STATS_ENDPOINTS = {'index', 'stats', 'stats_default', 'stats_by_date', 'games', 'games_default',
                   'player_stats', 'player_network', 'player_network_default',
                   'api_doubles_stats', 'api_doubles_player', 'api_doubles_list', 'api_network'}
ENTRY_ENDPOINTS = {'add_game', 'add_game_voice', 'api_todays_doubles_dashboard', 'api_doubles_players'}


def default_division(username):
    return 'women' if (username or '').strip().casefold() == 'jen' else 'open'


def entry_division(username=None):
    if has_request_context():
        data = request.get_json(silent=True) if request.is_json else request.form
        value = (data or {}).get('division') or request.args.get('division')
        if value in DIVISIONS:
            return value
        username = username or session.get('username')
    return default_division(username)


def active_doubles_division():
    if not has_request_context():
        return None
    if request.endpoint in ENTRY_ENDPOINTS:
        return entry_division()
    if request.method == 'GET' and request.endpoint in STATS_ENDPOINTS:
        value = request.args.get('division')
        return value if value in DIVISIONS else default_division(session.get('username'))
    return None


def ensure_division_column(conn):
    columns = {row[1] for row in conn.execute('PRAGMA table_info(games)')}
    if columns and 'division' not in columns:
        conn.execute("ALTER TABLE games ADD COLUMN division TEXT NOT NULL DEFAULT 'open'")
