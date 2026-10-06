"""Selected databases are combined for browsing only; writes keep their owner."""
import os
from pathlib import Path
import secrets
import sqlite3
import tempfile

from flask import g, has_request_context, jsonify, redirect, render_template, request, session, url_for

GAME_TABLES = ('games', 'vollis_games', 'other_games')
SOURCE_ID_STRIDE = 1 << 32
PERSONAL_WEB_ENDPOINTS = {
    'index', 'stats', 'stats_default', 'stats_by_date', 'games', 'games_default',
    'vollis_stats', 'vollis_stats_default', 'vollis_games', 'vollis_games_default',
    'other_stats', 'other_stats_default', 'other_games', 'other_games_default',
    'other_games_by_name', 'player_stats', 'vollis_player_stats', 'other_player_stats',
    'single_game_stats', 'single_game_stats_with_year', 'volleyball_stats',
    'volleyball_stats_default', 'volleyball_player_stats', 'game_name_stats',
    'game_name_stats_with_year', 'player_game_stats', 'player_list',
    'login', 'logout', 'static', 'add_game', 'add_vollis_game', 'add_other_game',
    'edit_stats', 'edit_games', 'edit_games_default', 'edit_vollis_games',
    'edit_vollis_games_default', 'edit_other_games', 'edit_other_games_default',
    'update', 'update_vollis_game', 'update_other_game', 'delete_game',
    'delete_vollis_game', 'delete_other_game', 'add_player', 'edit_player',
    'get_players', 'get_vollis_players', 'get_other_players',
    'api_delete_games', 'api_delete_player',
}
BROWSE_ENDPOINTS = {
    'api_years', 'api_doubles_stats', 'api_doubles_player', 'api_doubles_list',
    'api_doubles_get', 'api_vollis_stats', 'api_vollis_player', 'api_vollis_list',
    'api_vollis_get', 'api_other_stats', 'api_other_player', 'api_other_list',
    'api_other_get', 'api_other_game_types', 'api_volleyball_stats', 'api_players',
    'api_search_all_players',
} | (PERSONAL_WEB_ENDPOINTS - {
    'login', 'logout', 'static', 'add_game', 'add_vollis_game', 'add_other_game',
    'edit_stats', 'edit_games', 'edit_games_default', 'edit_vollis_games',
    'edit_vollis_games_default', 'edit_other_games', 'edit_other_games_default',
    'update', 'update_vollis_game', 'update_other_game', 'delete_game',
    'delete_vollis_game', 'delete_other_game', 'add_player', 'edit_player',
    'get_players', 'get_vollis_players', 'get_other_players', 'api_delete_games', 'api_delete_player',
})


def init_stats_views(path):
    with sqlite3.connect(path) as conn:
        columns = {row[1] for row in conn.execute('PRAGMA table_info(private_accounts)')}
        if 'share_stats' not in columns:
            conn.execute('ALTER TABLE private_accounts ADD COLUMN share_stats INTEGER NOT NULL DEFAULT 0')
        conn.execute('''CREATE TABLE IF NOT EXISTS account_stats_sources (
            viewer TEXT NOT NULL COLLATE NOCASE,
            owner TEXT NOT NULL COLLATE NOCASE,
            enabled INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY(viewer, owner)
        )''')


def sources_for_user(path, username, admin=False):
    """Resolve authorization before preferences; never accept client database paths."""
    from private_accounts import account_for_user
    own = account_for_user(path, username) if username else None
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        selected = {r['owner'].casefold(): bool(r['enabled']) for r in conn.execute(
            'SELECT owner, enabled FROM account_stats_sources WHERE viewer=?', (username or '',))}
        rows = conn.execute('''SELECT a.rowid AS source_number, a.* FROM private_accounts a
            JOIN site_users u ON u.username=a.username COLLATE NOCASE WHERE u.active=1
            ORDER BY a.username COLLATE NOCASE''').fetchall()
    sources = []
    if own:
        sources.append(dict(owner='kyle', title='KT Stats', enabled=selected.get('kyle', bool(own['show_starter_stats'])), number=1, account_id=None))
    for row in rows:
        owner = row['username']
        if username and owner.casefold() == username.casefold():
            continue
        if not admin and not row['share_stats']:
            continue
        sources.append(dict(owner=owner, title=owner + "’s stats", enabled=selected.get(owner.casefold(), False),
                            number=row['source_number'] + 1, account_id=row['id']))
    return sources


def _database_path(site_path, source):
    # Browsing never creates somebody else's missing database.
    if source['account_id'] is None:
        return site_path
    root = Path(os.environ.get('STATS_PRIVATE_DATA_DIR') or str(Path(site_path).resolve().parent / 'private_data'))
    return str(root / (source['account_id'] + '.db'))


def build_stats_view(site_path, own_path, sources):
    """Ephemeral data-only snapshot. External IDs cannot collide with owned IDs."""
    from private_accounts import DATA_TABLES
    fd, snapshot = tempfile.mkstemp(prefix='stats-view-', suffix='.db')
    os.close(fd)  # mkstemp uses 0600; no identity tables are copied.
    try:
        with sqlite3.connect('file:' + str(site_path) + '?mode=ro', uri=True) as schema, sqlite3.connect(snapshot) as target:
            for name, ddl in schema.execute("SELECT name, sql FROM sqlite_master WHERE type='table'"):
                if name in DATA_TABLES and ddl:
                    target.execute(ddl)
            # Owner first: their player metadata wins when names overlap.
            databases = [(own_path, 0)] + [(_database_path(site_path, s), s['number']) for s in sources if s['enabled']]
            names = set()
            for path, namespace in databases:
                if not Path(path).is_file():
                    continue
                with sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True) as source:
                    source.row_factory = sqlite3.Row
                    for table in (*GAME_TABLES, 'players'):
                        dest_cols = {r[1] for r in target.execute('PRAGMA table_info("' + table + '")')}
                        if not dest_cols or not source.execute("SELECT 1 FROM sqlite_master WHERE name=? AND type='table'", (table,)).fetchone():
                            continue
                        cols = [r[1] for r in source.execute('PRAGMA table_info("' + table + '")') if r[1] in dest_cols]
                        quoted = ','.join('"' + c + '"' for c in cols)
                        for row in source.execute('SELECT ' + quoted + ' FROM "' + table + '"'):
                            values = dict(row)
                            if table == 'players':
                                name = (values.get('full_name') or '').strip().casefold()
                                if name in names:
                                    continue
                                names.add(name)
                            if namespace and values.get('id') is not None:
                                if not 0 < values['id'] < SOURCE_ID_STRIDE:
                                    raise ValueError('Game ID outside supported range')
                                values['id'] += namespace * SOURCE_ID_STRIDE
                            target.execute('INSERT INTO "' + table + '" (' + quoted + ') VALUES (' + ','.join('?' for _ in cols) + ')',
                                           [values[c] for c in cols])
        return snapshot
    except BaseException:
        os.unlink(snapshot)
        raise


def register_stats_views(app, service, site_path):
    def current_user():
        return session.get('username') if session.get('logged_in') else None

    def payload(username):
        from private_accounts import account_for_user
        own = account_for_user(site_path, username)
        visible_sources = [{k: source[k] for k in ('owner', 'title', 'enabled')}
                           for source in sources_for_user(site_path, username, service.is_admin(username))]
        return dict(sources=visible_sources,
                    share_stats=bool(own and own['share_stats']), is_private=bool(own))

    @app.before_request
    def combine_selected_stats():
        from private_accounts import private_database
        # Foreign game IDs are view-only, including for admins.
        if request.method != 'GET' or request.endpoint in {'update', 'update_vollis_game', 'update_other_game', 'delete_game', 'delete_vollis_game', 'delete_other_game'}:
            if any(isinstance(v, int) and v >= SOURCE_ID_STRIDE for v in (request.view_args or {}).values()):
                return jsonify(error='This game belongs to another database and is read-only here.'), 403
            return
        if request.endpoint not in BROWSE_ENDPOINTS:
            return
        if request.path.startswith('/api/') and request.headers.get('X-Stats-Owned') == '1' and request.headers.get('X-Stats-Combined') != '1' and request.headers.get('X-Stats-Preview') != '1':
            return
        username = current_user()
        # Preview without authentication remains Kyle-only.
        if not username:
            return
        sources = sources_for_user(site_path, username, service.is_admin(username))
        if any(s['enabled'] for s in sources):
            g.stats_view_database = build_stats_view(site_path, private_database() or site_path, sources)

    @app.teardown_request
    def remove_stats_view(error):
        snapshot = g.pop('stats_view_database', None)
        if snapshot:
            try:
                os.unlink(snapshot)
            except FileNotFoundError:
                pass

    @app.route('/api/account/stats-sources', methods=['GET', 'PUT'])
    def account_stats_sources():
        username = current_user()
        if not username:
            return jsonify(error='Authentication required'), 401
        if request.method == 'PUT':
            body = request.get_json(silent=True)
            if not isinstance(body, dict) or not isinstance(body.get('owner'), str) or type(body.get('enabled')) is not bool:
                return jsonify(error='Choose a stats source and whether to include it.'), 400
            available = {s['owner'].casefold(): s['owner'] for s in payload(username)['sources']}
            owner = available.get(body['owner'].casefold())
            if owner is None:
                return jsonify(error='This database is not shared with you.'), 403
            with sqlite3.connect(site_path) as conn:
                conn.execute('INSERT INTO account_stats_sources VALUES (?, ?, ?) ON CONFLICT(viewer,owner) DO UPDATE SET enabled=excluded.enabled',
                             (username, owner, int(body['enabled'])))
                if owner.casefold() == 'kyle':
                    conn.execute('UPDATE private_accounts SET show_starter_stats=? WHERE username=?', (int(body['enabled']), username))
        return jsonify(payload(username))

    @app.put('/api/account/stats-sharing')
    def account_stats_sharing():
        from private_accounts import private_database
        username = current_user()
        if not username or not private_database():
            return jsonify(error='A personal account is required.'), 403
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or type(body.get('share_stats')) is not bool:
            return jsonify(error='Choose whether to share your stats.'), 400
        with sqlite3.connect(site_path) as conn:
            conn.execute('UPDATE private_accounts SET share_stats=? WHERE username=?', (int(body['share_stats']), username))
        return jsonify(payload(username))

    @app.route('/account/stats-sources/', methods=['GET', 'POST'])
    def stats_sources_page():
        username = current_user()
        if not username:
            return redirect(url_for('login'))
        if request.method == 'POST':
            token = session.get('stats_sources_csrf', '')
            if not token or not secrets.compare_digest(token, request.form.get('csrf', '')):
                return 'Please reload and try again.', 400
            available = payload(username)['sources']
            chosen = set(request.form.getlist('owner'))
            if chosen - {s['owner'] for s in available}:
                return 'This database is not shared with you.', 403
            with sqlite3.connect(site_path) as conn:
                for source in available:
                    conn.execute('INSERT INTO account_stats_sources VALUES (?, ?, ?) ON CONFLICT(viewer,owner) DO UPDATE SET enabled=excluded.enabled',
                                 (username, source['owner'], int(source['owner'] in chosen)))
                conn.execute('UPDATE private_accounts SET show_starter_stats=?, share_stats=? WHERE username=?',
                             (int('kyle' in chosen), int(request.form.get('share_stats') == 'on'), username))
            return redirect(url_for('stats_sources_page'))
        session.setdefault('stats_sources_csrf', secrets.token_urlsafe(32))
        return render_template('stats_sources.html', **payload(username), csrf=session['stats_sources_csrf'])
