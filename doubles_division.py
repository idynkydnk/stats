"""Doubles categories and request-local selection."""
from flask import has_request_context, request, session

DIVISIONS = {'open': 'Doubles', 'women': "Women’s Doubles"}
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
    from stats_location_filter import STATS_ENDPOINTS
    if request.endpoint in ENTRY_ENDPOINTS:
        return entry_division()
    if request.method == 'GET' and request.endpoint in STATS_ENDPOINTS:
        return 'women' if request.args.get('division') == 'women' else 'open'
    return None


def ensure_division_column(conn):
    columns = {row[1] for row in conn.execute('PRAGMA table_info(games)')}
    if columns and 'division' not in columns:
        conn.execute("ALTER TABLE games ADD COLUMN division TEXT NOT NULL DEFAULT 'open'")
