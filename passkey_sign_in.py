"""Discoverable WebAuthn credentials; private keys never leave the authenticator."""
from contextlib import contextmanager
import hashlib
import json
import secrets
import sqlite3
import time
from urllib.parse import urlsplit

from flask import abort, jsonify, redirect, render_template, request, session, url_for
try:
    from webauthn import (generate_authentication_options, generate_registration_options,
                          verify_authentication_response, verify_registration_response)
    from webauthn.helpers import bytes_to_base64url, base64url_to_bytes, options_to_json
    from webauthn.helpers.exceptions import WebAuthnException
    from webauthn.helpers.structs import (AuthenticatorSelectionCriteria,
        PublicKeyCredentialDescriptor, ResidentKeyRequirement, UserVerificationRequirement)
    PASSKEYS_AVAILABLE = True
except ImportError:
    PASSKEYS_AVAILABLE = False


@contextmanager
def database(path):
    conn = sqlite3.connect(path)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_passkeys(path):
    with database(path) as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS passkey_users (
                username TEXT PRIMARY KEY COLLATE NOCASE, handle BLOB NOT NULL UNIQUE);
            CREATE TABLE IF NOT EXISTS passkey_credentials (
                id BLOB PRIMARY KEY, username TEXT NOT NULL COLLATE NOCASE,
                public_key BLOB NOT NULL, sign_count INTEGER NOT NULL,
                label TEXT NOT NULL, created_at INTEGER NOT NULL, last_used INTEGER);
            CREATE INDEX IF NOT EXISTS passkey_owner ON passkey_credentials(username);
            CREATE TABLE IF NOT EXISTS passkey_challenges (
                id TEXT PRIMARY KEY, binding TEXT NOT NULL, kind TEXT NOT NULL,
                username TEXT, challenge BLOB NOT NULL, expires_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS passkey_attempts (binding TEXT, created_at INTEGER);
            CREATE INDEX IF NOT EXISTS passkey_attempt_time ON passkey_attempts(created_at);
            CREATE TRIGGER IF NOT EXISTS remove_deleted_user_passkeys AFTER DELETE ON site_users
            BEGIN
                DELETE FROM passkey_credentials WHERE username=OLD.username COLLATE NOCASE;
                DELETE FROM passkey_users WHERE username=OLD.username COLLATE NOCASE;
                DELETE FROM passkey_challenges WHERE username=OLD.username COLLATE NOCASE;
            END;
            CREATE TRIGGER IF NOT EXISTS remove_inactive_user_passkeys AFTER UPDATE OF active ON site_users
            WHEN NEW.active=0
            BEGIN
                DELETE FROM passkey_credentials WHERE username=NEW.username COLLATE NOCASE;
                DELETE FROM passkey_users WHERE username=NEW.username COLLATE NOCASE;
                DELETE FROM passkey_challenges WHERE username=NEW.username COLLATE NOCASE;
            END;
        ''')


def register_passkey_sign_in(app, service, path, finish):
    init_passkeys(path)

    def origin():
        # Never derive the relying party from untrusted Host/forwarded headers.
        value = app.config.get('PASSKEY_ORIGIN') or app.config.get('SITE_BASE_URL') or 'https://idynkydnk.pythonanywhere.com'
        parsed = urlsplit(value)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            abort(503, description='Passkey sign-in is not configured.')
        return parsed.scheme + '://' + parsed.netloc

    def current_user(recent=False):
        user = service.adminfx.get_site_user(session.get('username')) if session.get('logged_in') else None
        if not user or not user.get('active', 1):
            abort(401, description='Please sign in first.')
        if recent and time.time() - session.get('authenticated_at', 0) > 600:
            abort(403, description='Please sign in again before changing your passkeys.')
        return user

    def csrf():
        return session.setdefault('passkey_csrf', secrets.token_urlsafe(32))

    @app.context_processor
    def passkey_context():
        return {'passkey_csrf': csrf, 'passkeys_available': PASSKEYS_AVAILABLE}

    @app.before_request
    def protect_passkeys():
        if not (request.endpoint or '').startswith('passkey_'):
            return
        if not PASSKEYS_AVAILABLE:
            return jsonify(error='Passkeys are temporarily unavailable. Please sign in with email.'), 503
        if request.method == 'POST':
            if (request.content_length or 0) > 32768:
                return jsonify(error='Please try again.'), 400
            body = request.get_json(silent=True)
            if not isinstance(body, dict):
                return jsonify(error='Please try again.'), 400
            token = request.headers.get('X-CSRF-Token', '')
            if not token or not secrets.compare_digest(token.encode(), session.get('passkey_csrf', '').encode()):
                return jsonify(error='This page expired. Reload it and try again.'), 403
            if request.headers.get('Origin') != origin():
                return jsonify(error='Please open Stats directly to use a passkey.'), 403

    @app.after_request
    def protect_passkey_response(response):
        if (request.endpoint or '').startswith('passkey_'):
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    @app.get('/account/passkeys')
    def passkey_settings():
        if not session.get('logged_in'):
            return redirect(url_for('login', next='/account/passkeys'))
        user = current_user()
        with database(path) as conn:
            rows = conn.execute('SELECT id, label FROM passkey_credentials WHERE username=? ORDER BY created_at',
                                (user['username'],)).fetchall()
        return render_template('passkeys.html', csrf=csrf(),
            credentials=[{'id': bytes_to_base64url(row[0]), 'label': row[1]} for row in rows],
            recent=time.time() - session.get('authenticated_at', 0) <= 600)

    def issue(kind, username=None):
        now = int(time.time())
        binding = session.setdefault('passkey_binding', secrets.token_urlsafe(32))
        ip = hashlib.sha256(service._client_ip().encode()).hexdigest()
        challenge = secrets.token_bytes(32)
        identifier = secrets.token_urlsafe(32)
        with database(path) as conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('DELETE FROM passkey_attempts WHERE created_at<=?', (now - 300,))
            conn.execute('DELETE FROM passkey_challenges WHERE expires_at<=?', (now,))
            if conn.execute('SELECT COUNT(*) FROM passkey_attempts WHERE binding=?', (ip,)).fetchone()[0] >= 30:
                abort(429, description='Too many attempts. Please wait five minutes.')
            conn.execute('INSERT INTO passkey_attempts VALUES (?, ?)', (ip, now))
            conn.execute('DELETE FROM passkey_challenges WHERE binding=? AND kind=?', (binding, kind))
            conn.execute('INSERT INTO passkey_challenges VALUES (?, ?, ?, ?, ?, ?)',
                         (identifier, binding, kind, username, challenge, now + 300))
        session['passkey_' + kind] = identifier
        return challenge

    def consume(kind, username=None):
        identifier = session.pop('passkey_' + kind, None)
        with database(path) as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT challenge, expires_at, username FROM passkey_challenges WHERE id=? AND binding=? AND kind=?',
                (identifier, session.get('passkey_binding'), kind)).fetchone()
            conn.execute('DELETE FROM passkey_challenges WHERE id=? AND binding=?',
                         (identifier, session.get('passkey_binding')))
        if not row or row[1] <= time.time() or row[2] != username:
            abort(400, description='This passkey attempt expired. Please try again.')
        return row[0]

    @app.post('/auth/passkeys/register/options')
    def passkey_register_options():
        user = current_user(recent=True)
        with database(path) as conn:
            conn.execute('INSERT OR IGNORE INTO passkey_users VALUES (?, ?)', (user['username'], secrets.token_bytes(32)))
            handle = conn.execute('SELECT handle FROM passkey_users WHERE username=?', (user['username'],)).fetchone()[0]
            existing = conn.execute('SELECT id FROM passkey_credentials WHERE username=?', (user['username'],)).fetchall()
        if len(existing) >= 10:
            return jsonify(error='Remove an old passkey before adding another.'), 400
        options = generate_registration_options(rp_id=urlsplit(origin()).hostname, rp_name='Stats',
            user_id=handle, user_name=user.get('login_email') or user['username'],
            user_display_name=user.get('display_name') or user['username'],
            challenge=issue('register', user['username']),
            exclude_credentials=[PublicKeyCredentialDescriptor(id=row[0]) for row in existing],
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.REQUIRED,
                user_verification=UserVerificationRequirement.REQUIRED))
        return jsonify(json.loads(options_to_json(options)))

    @app.post('/auth/passkeys/register/verify')
    def passkey_register_verify():
        user = current_user(recent=True)
        challenge = consume('register', user['username'])
        body = request.get_json()
        label = body.get('label', 'My passkey')
        if not isinstance(label, str) or not label.strip() or len(label) > 80:
            return jsonify(error='Give your passkey a name of up to 80 characters.'), 400
        try:
            verified = verify_registration_response(credential=body.get('credential'),
                expected_challenge=challenge, expected_origin=origin(), expected_rp_id=urlsplit(origin()).hostname,
                require_user_verification=True)
            with database(path) as conn:
                conn.execute('BEGIN IMMEDIATE')
                active = conn.execute('SELECT active FROM site_users WHERE username=?', (user['username'],)).fetchone()
                if not active or not active[0]:
                    abort(401)
                if conn.execute('SELECT COUNT(*) FROM passkey_credentials WHERE username=?', (user['username'],)).fetchone()[0] >= 10:
                    abort(400)
                conn.execute('INSERT INTO passkey_credentials VALUES (?, ?, ?, ?, ?, ?, NULL)',
                    (verified.credential_id, user['username'], verified.credential_public_key,
                     verified.sign_count, label.strip(), int(time.time())))
        except (WebAuthnException, ValueError, TypeError, KeyError, AttributeError, sqlite3.IntegrityError):
            return jsonify(error='Couldn’t save this passkey. It may already be saved. Please try again.'), 400
        return jsonify(ok=True)

    @app.post('/auth/passkeys/login/options')
    def passkey_login_options():
        if session.get('logged_in') and not session.get('passkey_reauth'):
            return jsonify(error='You are already signed in.'), 400
        session['email_login_remember'] = request.get_json().get('remember') is True
        options = generate_authentication_options(rp_id=urlsplit(origin()).hostname,
            challenge=issue('login'), user_verification=UserVerificationRequirement.REQUIRED)
        return jsonify(json.loads(options_to_json(options)))

    @app.post('/auth/passkeys/login/verify')
    def passkey_login_verify():
        challenge = consume('login')
        credential = request.get_json().get('credential')
        try:
            if not isinstance(credential, dict):
                raise ValueError()
            identifier = base64url_to_bytes(credential['id'])
            with database(path) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute('BEGIN IMMEDIATE')
                saved = conn.execute('''SELECT c.*, u.handle FROM passkey_credentials c
                    JOIN passkey_users u ON u.username=c.username
                    JOIN site_users s ON s.username=c.username COLLATE NOCASE
                    WHERE c.id=? AND s.active=1''', (identifier,)).fetchone()
                if not saved or base64url_to_bytes(credential['response']['userHandle']) != saved['handle']:
                    raise ValueError()
                verified = verify_authentication_response(credential=credential,
                    expected_challenge=challenge, expected_origin=origin(), expected_rp_id=urlsplit(origin()).hostname,
                    credential_public_key=saved['public_key'], credential_current_sign_count=saved['sign_count'],
                    require_user_verification=True)
                conn.execute('UPDATE passkey_credentials SET sign_count=?, last_used=? WHERE id=?',
                             (verified.new_sign_count, int(time.time()), identifier))
                username = saved['username']
        except (WebAuthnException, ValueError, TypeError, KeyError, AttributeError):
            return jsonify(error='Couldn’t sign in with this passkey. Try again or use an email code.'), 400
        response = finish(username)
        # Reuse the established sign-in path, including permissions and remember cookies.
        response = app.make_response(response)
        if response.status_code == 303:
            destination = response.headers.pop('Location')
            response.set_data(json.dumps({'redirect': destination}))
            response.content_type = 'application/json'
            response.status_code = 200
        return response

    @app.post('/auth/passkeys/remove')
    def passkey_remove():
        user = current_user(recent=True)
        identifier = request.get_json().get('id')
        try:
            identifier = base64url_to_bytes(identifier)
        except (TypeError, ValueError, AttributeError):
            return jsonify(error='Choose a saved passkey.'), 400
        with database(path) as conn:
            conn.execute('DELETE FROM passkey_credentials WHERE id=? AND username=?', (identifier, user['username']))
        return jsonify(ok=True)
