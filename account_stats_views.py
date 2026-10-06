"""Selected databases are combined for browsing only; writes keep their owner."""
import os
from pathlib import Path
import secrets
import sqlite3
import tempfile
from urllib.parse import urlencode

from flask import abort, flash, g, has_request_context, jsonify, redirect, render_template, request, session, url_for
from itsdangerous import BadSignature, URLSafeSerializer

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
        conn.execute('BEGIN IMMEDIATE')
        columns = {row[1] for row in conn.execute('PRAGMA table_info(private_accounts)')}
        if 'share_stats' not in columns:
            conn.execute('ALTER TABLE private_accounts ADD COLUMN share_stats INTEGER NOT NULL DEFAULT 0')
        conn.execute('''CREATE TABLE IF NOT EXISTS account_stats_sources (
            viewer TEXT NOT NULL COLLATE NOCASE,
            owner TEXT NOT NULL COLLATE NOCASE,
            enabled INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY(viewer, owner)
        )''')
        from migrations.enable_existing_stats_sources import migrate
        migrate(conn)


def sources_for_user(path, username, admin=False):
    """Resolve authorization before preferences; never accept client database paths."""
    from private_accounts import account_for_user
    own = account_for_user(path, username) if username else None
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        selected = {r['owner'].casefold(): bool(r['enabled']) for r in conn.execute(
            'SELECT owner, enabled FROM account_stats_sources WHERE viewer=?', (username or '',))}
        group_member = conn.execute('SELECT 1 FROM stats_source_group WHERE username=?',
                                    (username or '',)).fetchone() is not None
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
        if not admin and (not group_member or not row['share_stats']):
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


def recap_authors_for_viewer(site_path):
    """Personal recap directories include the owner and optionally KT Stats."""
    account = getattr(g, 'private_account', None)
    if not account:
        return None
    username = account['username']
    authors = {username.casefold()}
    if any(source['owner'].casefold() == 'kyle' and source['enabled']
           for source in sources_for_user(site_path, username)):
        authors.add('kyle')
    return authors


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
    signer = URLSafeSerializer(app.secret_key, salt='shared-stats-view-v1')

    def current_user():
        return session.get('username') if session.get('logged_in') else None

    def share_selection(username, sources):
        from private_accounts import account_for_user
        own = account_for_user(site_path, username)
        # An admin's access to somebody's private stats is not permission to
        # publish them. Their owner must enable sharing first.
        selected = [source for source in sources if source['enabled']]
        for source in selected:
            if source['account_id'] is not None:
                account = account_for_user(site_path, source['owner'])
                if not account or not account['share_stats']:
                    return None
        return signer.dumps(dict(base=own['id'] if own else None,
                                 sources=[source['account_id'] for source in selected]))

    def read_selection(token):
        try:
            selection = signer.loads(token)
        except BadSignature:
            abort(404, description='This stats link is invalid or no longer available.')
        with sqlite3.connect(site_path) as conn:
            conn.row_factory = sqlite3.Row
            accounts = {row['id']: dict(row) for row in conn.execute('''
                SELECT a.*, a.rowid AS source_number FROM private_accounts a
                JOIN site_users u ON u.username=a.username COLLATE NOCASE
                WHERE u.active=1''')}

        def resolve(account_id, base=False):
            if account_id is None:
                return dict(owner='kyle', title='KT Stats', account_id=None, number=1, enabled=True)
            account = accounts.get(account_id)
            if not account or (not base and not account['share_stats']):
                abort(404, description='This stats link is no longer available.')
            source = dict(owner=account['username'], title=account['username'] + '’s stats',
                          account_id=account_id, number=account['source_number'] + 1, enabled=True)
            if not Path(_database_path(site_path, source)).is_file():
                abort(404, description='This stats link is no longer available.')
            return source

        return resolve(selection['base'], base=True), [resolve(value) for value in selection['sources']]

    @app.url_defaults
    def preserve_shared_stats(endpoint, values):
        if has_request_context() and endpoint in BROWSE_ENDPOINTS:
            token = getattr(g, 'stats_share_token', None)
            if token:
                values.setdefault('view', token)

    @app.context_processor
    def shared_stats_context():
        return dict(stats_share_token=getattr(g, 'stats_share_token', None),
                    stats_share_available=getattr(g, 'stats_share_available', False),
                    stats_shared_titles=getattr(g, 'stats_shared_titles', []),
                    stats_shared_read_only=getattr(g, 'stats_shared_read_only', False))

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
        token = request.args.get('view')
        if 'view' in request.args:
            # A share link is a read-only capability, never a login or a write
            # database selector. Reject malformed links instead of showing KT.
            if request.method != 'GET' or request.endpoint not in BROWSE_ENDPOINTS:
                return jsonify(error='Shared stats links are read-only.'), 403
            base, sources = read_selection(token)
            g.stats_share_token = token
            g.stats_share_available = True
            g.stats_shared_titles = [base['title']] + [source['title'] for source in sources]
            g.stats_shared_read_only = base['owner'].casefold() != (current_user() or '').casefold()
            if base['account_id'] is None and not sources:
                # Public KT links must also override a signed-in recipient's
                # personal database, without copying the whole public archive.
                g.private_database = None
                return
            g.stats_view_database = build_stats_view(site_path, _database_path(site_path, base), sources)
            return
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
        sources = sources_for_user(site_path, username, service.is_admin(username)) if username else []
        if not request.path.startswith('/api/'):
            token = share_selection(username, sources)
            g.stats_share_available = bool(token)
            if token:
                # Make copying the address bar work too. Keep every active
                # filter (including repeated query arguments) on the URL.
                args = list(request.args.items(multi=True)) + [('view', token)]
                return redirect(request.path + '?' + urlencode(args))
        if any(s['enabled'] for s in sources):
            g.stats_view_database = build_stats_view(site_path, private_database() or site_path, sources)

    @app.after_request
    def protect_share_link(response):
        if getattr(g, 'stats_share_token', None):
            response.headers['Referrer-Policy'] = 'same-origin'
            response.headers['Cache-Control'] = 'no-store'
        return response

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
            flash('Your choices were saved.', 'success')
            return redirect(url_for('stats_default'))
        session.setdefault('stats_sources_csrf', secrets.token_urlsafe(32))
        return render_template('stats_sources.html', **payload(username), csrf=session['stats_sources_csrf'])
