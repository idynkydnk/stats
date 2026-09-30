"""Personal iPhone accounts and request-local game storage.

Identity and tokens remain in the site database. Only an authenticated account
can select a private database; neither a URL nor a client-supplied ID can do so.
"""
import os
import hashlib
import time
from pathlib import Path
import re
import secrets
import sqlite3
import uuid

from flask import g, has_request_context, jsonify, request, session
from werkzeug.security import generate_password_hash


DATA_TABLES = {
    'games', 'vollis_games', 'other_games', 'players', 'tournaments',
    'doubles_player_last_played', 'deleted_records', 'sessions', 'trueskill_rankings',
}
GOOGLE_IOS_CLIENT_ID = '195048170299-63t84plh4cae8a7r5nk70d8l8hkr3t8p.apps.googleusercontent.com'
PRIVATE_ENDPOINTS = {
    'api_me', 'api_logout', 'api_years', 'api_network',
    'api_doubles_stats', 'api_doubles_player', 'api_doubles_list',
    'api_doubles_get', 'api_doubles_create', 'api_doubles_update', 'api_doubles_delete',
    'api_vollis_stats', 'api_vollis_player', 'api_vollis_list',
    'api_vollis_get', 'api_vollis_create', 'api_vollis_update', 'api_vollis_delete',
    'api_other_stats', 'api_other_player', 'api_other_list', 'api_other_game_types',
    'api_other_get', 'api_other_create', 'api_other_update', 'api_other_delete',
    'api_volleyball_stats', 'api_players', 'api_tournaments_list', 'api_tournaments_create',
    'api_doubles_players', 'api_vollis_players', 'api_todays_doubles_dashboard',
    'get_other_game_players', 'get_other_game_info', 'get_other_game_common_scores',
    'get_other_game_type', 'api_search_all_players', 'api_add_player',
    'api_update_player_info', 'api_rename_player', 'set_timezone',
    'private_delete_account', 'private_starter_stats',
}
PREVIEW_ENDPOINTS = {
    'api_years', 'api_network', 'api_doubles_stats', 'api_doubles_player',
    'api_doubles_list', 'api_doubles_get', 'api_vollis_stats', 'api_vollis_player',
    'api_vollis_list', 'api_vollis_get', 'api_other_stats', 'api_other_player',
    'api_other_list', 'api_other_get', 'api_other_game_types', 'api_volleyball_stats',
}
AUTH_ENDPOINTS = {'api_login', 'private_register', 'private_google', 'private_auth_config',
                  'private_apple', 'private_apple_challenge'}


def private_database():
    return getattr(g, 'private_database', None) if has_request_context() else None


def data_path(default):
    return private_database() or default


def connect_data(path, *args, **kwargs):
    return sqlite3.connect(data_path(path), *args, **kwargs)


def init_accounts(path):
    with sqlite3.connect(path) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS private_accounts (
            id TEXT PRIMARY KEY, username TEXT NOT NULL COLLATE NOCASE UNIQUE,
            google_subject TEXT UNIQUE, apple_subject TEXT UNIQUE,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')
        columns = {r[1] for r in conn.execute('PRAGMA table_info(private_accounts)')}
        if 'show_starter_stats' not in columns:
            conn.execute('ALTER TABLE private_accounts ADD COLUMN show_starter_stats INTEGER NOT NULL DEFAULT 1')
        if 'apple_subject' not in columns:
            conn.execute('ALTER TABLE private_accounts ADD COLUMN apple_subject TEXT')
            conn.execute('CREATE UNIQUE INDEX private_apple_subject ON private_accounts(apple_subject)')
        conn.execute('''CREATE TABLE IF NOT EXISTS private_auth_challenges (
            nonce_hash TEXT PRIMARY KEY, expires_at INTEGER NOT NULL
        )''')


def account_for_user(path, username):
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute('SELECT * FROM private_accounts WHERE username = ?',
                           (username or '',)).fetchone()
        return dict(row) if row else None


def provision_database(site_path, account_id):
    # Schema only: never copy rows, credentials, photos, or shared game history.
    if not re.fullmatch(r'[0-9a-f]{32}', account_id):
        raise ValueError('Invalid account ID')
    root = Path(os.environ.get('STATS_PRIVATE_DATA_DIR') or
                str(Path(site_path).resolve().parent / 'private_data'))
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination = root / (account_id + '.db')
    with sqlite3.connect(site_path) as source, sqlite3.connect(destination) as target:
        target.execute('BEGIN IMMEDIATE')
        for name, ddl in source.execute("SELECT name, sql FROM sqlite_master WHERE type='table'"):
            if name in DATA_TABLES and ddl:
                exists = target.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
                if not exists:
                    target.execute(ddl)
    os.chmod(destination, 0o600)
    return str(destination)


def create_account(path, username, password=None, google_subject=None, apple_subject=None):
    account_id = uuid.uuid4().hex
    with sqlite3.connect(path) as conn:
        # Serialize the case-insensitive name check, including legacy usernames.
        conn.execute('BEGIN IMMEDIATE')
        if conn.execute('SELECT 1 FROM site_users WHERE lower(username)=lower(?)', (username,)).fetchone():
            raise ValueError('That username is already taken.')
        conn.execute('INSERT INTO site_users (username, password_hash, is_admin) VALUES (?, ?, 0)',
                     (username, generate_password_hash(password or secrets.token_urlsafe(48))))
        conn.execute('INSERT INTO private_accounts (id, username, google_subject, apple_subject) VALUES (?, ?, ?, ?)',
                     (account_id, username, google_subject, apple_subject))
    return username


def register_private_accounts(app, service):
    site_path = service._stats_db_path()
    init_accounts(site_path)

    @app.before_request
    def scope_personal_account():
        preview = request.headers.get('X-Stats-Preview') == '1'
        if preview and (request.method != 'GET' or request.endpoint not in PREVIEW_ENDPOINTS):
            return jsonify(error="KT Stats is read-only."), 403
        if request.endpoint in AUTH_ENDPOINTS:
            return None
        authorization = request.headers.get('Authorization', '')
        username = None
        if authorization:
            if not authorization.startswith('Bearer '):
                return jsonify(error='Authentication required'), 401
            username = service.validate_auth_token(authorization[7:].strip())
            if not username:
                return jsonify(error='Please sign in again.'), 401
        elif request.headers.get('X-Stats-Account-Required') == '1' and not preview:
            return jsonify(error='Authentication required'), 401
        elif session.get('logged_in'):
            username = session.get('username')
        elif request.cookies.get('remember_token'):
            username = service.validate_auth_token(request.cookies['remember_token'])
        if preview:
            # Explicit public browsing never selects or modifies an account DB.
            return None
        if not username:
            return None
        user = service.adminfx.get_site_user(username)
        if user and not user.get('active', 1):
            session.clear()
            return jsonify(error='This account is inactive.'), 401
        account = account_for_user(site_path, username)
        if account:
            if request.endpoint not in PRIVATE_ENDPOINTS:
                return jsonify(error='This feature is not available for personal accounts.'), 403
            g.private_account = account
            g.private_database = provision_database(site_path, account['id'])
        if authorization:
            service.establish_user_session(username)

    @app.after_request
    def private_response(response):
        if private_database() or request.headers.get('X-Stats-Account-Required') == '1':
            response.headers['Cache-Control'] = 'no-store'
            response.vary.add('Authorization')
        return response

    def issue_session(username):
        user = service.adminfx.get_site_user(username)
        if not user or not user.get('active', 1):
            return jsonify(error='This account is inactive.'), 401
        session.clear()
        service.establish_user_session(username, login=True)
        return jsonify(token=service.create_auth_token(username), username=username,
                       is_admin=False, logged_in=True, is_private=True)

    @app.put('/api/account/starter-stats')
    def private_starter_stats():
        account = getattr(g, 'private_account', None)
        if not account:
            return jsonify(error='A personal account is required.'), 403
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or type(body.get('show_starter_stats')) is not bool:
            return jsonify(error='Choose whether to show starter stats.'), 400
        visible = body['show_starter_stats']
        with sqlite3.connect(site_path) as conn:
            conn.execute('UPDATE private_accounts SET show_starter_stats=? WHERE id=?',
                         (int(visible), account['id']))
        return jsonify(show_starter_stats=visible)

    def limited():
        return service.login_rate_limited(service._client_ip())

    def social_session(provider, subject):
        column = {'google': 'google_subject', 'apple': 'apple_subject'}[provider]
        with sqlite3.connect(site_path) as conn:
            row = conn.execute(f'SELECT username FROM private_accounts WHERE {column}=?', (subject,)).fetchone()
        if row:
            username = row[0]
        else:
            username = provider + '_' + uuid.uuid4().hex
            try:
                create_account(site_path, username, **{column: subject})
            except sqlite3.IntegrityError:
                with sqlite3.connect(site_path) as conn:
                    username = conn.execute(f'SELECT username FROM private_accounts WHERE {column}=?', (subject,)).fetchone()[0]
        service.clear_login_failures(service._client_ip())
        return issue_session(username)

    @app.post('/api/auth/register')
    def private_register():
        if limited():
            return jsonify(error='Too many attempts. Try again in a few minutes.'), 429
        service.record_login_failure(service._client_ip())
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify(error='Enter a username and password.'), 400
        username, password = body.get('username'), body.get('password')
        if not isinstance(username, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{3,40}', username):
            return jsonify(error='Use 3-40 letters, numbers, periods, underscores, or hyphens for your username.'), 400
        if not isinstance(password, str) or not 12 <= len(password) <= 256:
            return jsonify(error='Use a password with 12-256 characters.'), 400
        try:
            create_account(site_path, username, password=password)
        except (ValueError, sqlite3.IntegrityError):
            return jsonify(error='That username is already taken.'), 409
        return issue_session(username), 201

    @app.get('/api/auth/config')
    def private_auth_config():
        return jsonify(google_ios_client_id=os.environ.get('GOOGLE_IOS_CLIENT_ID', GOOGLE_IOS_CLIENT_ID))

    @app.post('/api/auth/google')
    def private_google():
        if limited():
            return jsonify(error='Too many attempts. Try again in a few minutes.'), 429
        service.record_login_failure(service._client_ip())
        client_id = os.environ.get('GOOGLE_IOS_CLIENT_ID', GOOGLE_IOS_CLIENT_ID)
        if not client_id:
            return jsonify(error='Google sign-in has not been configured yet. Please create an account or sign in with your password.'), 503
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict) or not isinstance(body.get('id_token'), str):
            return jsonify(error='Google sign-in could not be verified.'), 400
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.id_token import verify_oauth2_token
            claims = verify_oauth2_token(body['id_token'], Request(), client_id)
            subject = claims.get('sub')
            if not subject or claims.get('email_verified') is not True:
                raise ValueError('Unverified account')
        except (ValueError, TypeError):
            return jsonify(error='Google sign-in could not be verified. Please try again.'), 401
        except Exception:
            app.logger.exception('Google verification unavailable')
            return jsonify(error='Google sign-in is temporarily unavailable.'), 503
        return social_session('google', subject)

    @app.post('/api/auth/apple/challenge')
    def private_apple_challenge():
        if limited():
            return jsonify(error='Too many attempts. Try again in a few minutes.'), 429
        service.record_login_failure(service._client_ip())
        nonce = secrets.token_urlsafe(32)
        with sqlite3.connect(site_path) as conn:
            conn.execute('DELETE FROM private_auth_challenges WHERE expires_at < ?', (int(time.time()),))
            conn.execute('INSERT INTO private_auth_challenges VALUES (?, ?)',
                         (hashlib.sha256(nonce.encode()).hexdigest(), int(time.time()) + 600))
        return jsonify(nonce=nonce)

    @app.post('/api/auth/apple')
    def private_apple():
        import jwt
        if limited():
            return jsonify(error='Too many attempts. Try again in a few minutes.'), 429
        service.record_login_failure(service._client_ip())
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict) or not isinstance(body.get('id_token'), str) or not isinstance(body.get('nonce'), str):
            return jsonify(error='Apple sign-in could not be verified.'), 400
        nonce_hash = hashlib.sha256(body['nonce'].encode()).hexdigest()
        try:
            keys = jwt.PyJWKClient('https://appleid.apple.com/auth/keys', timeout=10)
            key = keys.get_signing_key_from_jwt(body['id_token'])
            claims = jwt.decode(body['id_token'], key.key, algorithms=['RS256'],
                                audience=os.environ.get('APPLE_IOS_CLIENT_ID', 'com.kt.stats'),
                                issuer='https://appleid.apple.com',
                                options={'require': ['exp', 'iat', 'sub', 'aud', 'iss', 'nonce']})
            if not secrets.compare_digest(str(claims['nonce']), nonce_hash):
                raise ValueError('Wrong nonce')
            with sqlite3.connect(site_path) as conn:
                consumed = conn.execute('DELETE FROM private_auth_challenges WHERE nonce_hash=? AND expires_at>=?',
                                        (nonce_hash, int(time.time()))).rowcount
            if consumed != 1:
                raise ValueError('Expired or reused challenge')
        except (jwt.InvalidTokenError, ValueError):
            return jsonify(error='Apple sign-in could not be verified. Please try again.'), 401
        except Exception:
            app.logger.exception('Apple verification unavailable')
            return jsonify(error='Apple sign-in is temporarily unavailable.'), 503
        return social_session('apple', claims['sub'])

    @app.delete('/api/account')
    def private_delete_account():
        account = getattr(g, 'private_account', None)
        if not account:
            return jsonify(error='A personal account is required.'), 403
        # Keep the identity tombstone so this username can never regain access
        # to old tokens or an in-flight request after account deletion.
        with sqlite3.connect(site_path) as conn:
            conn.execute('UPDATE site_users SET active=0, password_hash=? WHERE username=?',
                         (generate_password_hash(secrets.token_urlsafe(48)), account['username']))
            conn.execute('DELETE FROM auth_tokens WHERE lower(username)=lower(?)', (account['username'],))
        with sqlite3.connect(private_database()) as conn:
            for table in DATA_TABLES:
                if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                    conn.execute('DELETE FROM "' + table + '"')
        session.clear()
        return jsonify(ok=True)
