"""Browser email-code sign-in, with durable single-use challenges."""
import hashlib
import hmac
import re
import uuid
import secrets
import sqlite3
from time import time
from urllib.parse import unquote, urlsplit

from flask import abort, flash, has_request_context, redirect, render_template, request, session, url_for
from flask_mail import Message
from werkzeug.security import generate_password_hash
from account_names import clean_signup_name



def safe_login_next(value):
    """Only redirect to local paths, including after password sign-in."""
    if not isinstance(value, str):
        return '/'
    decoded = unquote(value)
    if ('\\' in decoded or any(ord(char) < 32 or ord(char) == 127 for char in decoded)):
        return '/'
    try:
        parts = urlsplit(decoded)
    except ValueError:
        return '/'
    if parts.scheme or parts.netloc:
        # Existing protected pages pass request.url, so preserve same-origin links.
        if not has_request_context():
            return '/'
        origin = urlsplit(request.host_url)
        if parts.scheme != origin.scheme or parts.netloc != origin.netloc:
            return '/'
        original = urlsplit(value)
        value = original.path or '/'
        if original.query:
            value += '?' + original.query
        if original.fragment:
            value += '#' + original.fragment
        return safe_login_next(value)
    return value if decoded.startswith('/') and not decoded.startswith('//') else '/'


CODE_TTL = 300
MAX_ATTEMPTS = 3


def normalize_email(value):
    if not isinstance(value, str):
        raise ValueError('Enter a valid email address.')
    value = value.strip().lower()
    if len(value) > 254 or not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}", value):
        raise ValueError('Enter a valid email address.')
    return value


def init_email_sign_in(path):
    with sqlite3.connect(path) as conn:
        conn.execute('BEGIN IMMEDIATE')
        columns = {row[1] for row in conn.execute('PRAGMA table_info(site_users)')}
        if 'login_email' not in columns:
            conn.execute('ALTER TABLE site_users ADD COLUMN login_email TEXT COLLATE NOCASE')
            # Snapshot only explicit, saved account/player links. Never guess an
            # identity from a first name, nickname, or a public email recipient.
            player_columns = {row[1] for row in conn.execute('PRAGMA table_info(players)')}
            if 'player_name' in columns and {'full_name', 'email'} <= player_columns:
                for username, player in conn.execute('SELECT username, player_name FROM site_users').fetchall():
                    addresses = set()
                    for (raw,) in conn.execute('SELECT email FROM players WHERE lower(trim(full_name))=lower(trim(?))', (player,)):
                        try:
                            addresses.add(normalize_email(raw))
                        except ValueError:
                            pass
                    if len(addresses) == 1:
                        conn.execute('UPDATE site_users SET login_email=? WHERE username=?', (addresses.pop(), username))
        for column in ('first_name', 'last_name'):
            if column not in columns:
                conn.execute(f'ALTER TABLE site_users ADD COLUMN {column} TEXT')
        # Deliberately not unique: a duplicate legacy mapping must fail closed,
        # not silently choose one account (especially an administrator).
        conn.execute('CREATE INDEX IF NOT EXISTS site_user_login_email ON site_users(login_email)')
        conn.execute('''CREATE TABLE IF NOT EXISTS web_email_codes (
            id TEXT PRIMARY KEY, email TEXT NOT NULL, code_hash TEXT NOT NULL,
            expires_at INTEGER NOT NULL, attempts INTEGER NOT NULL DEFAULT 0
        )''')
        code_columns = {row[1] for row in conn.execute('PRAGMA table_info(web_email_codes)')}
        for column, kind in (('link_username', 'TEXT'), ('verified_at', 'INTEGER')):
            if column not in code_columns:
                conn.execute(f'ALTER TABLE web_email_codes ADD COLUMN {column} {kind}')
        conn.execute('''CREATE TABLE IF NOT EXISTS web_login_events (
            kind TEXT NOT NULL, key_hash TEXT NOT NULL, created_at INTEGER NOT NULL
        )''')
        conn.execute('CREATE INDEX IF NOT EXISTS web_login_events_lookup ON web_login_events(kind, key_hash, created_at)')


def set_login_email(path, username, email):
    """Explicit admin-managed identity binding, separate from update recipients."""
    email = normalize_email(email) if (email or '').strip() else None
    with sqlite3.connect(path) as conn:
        conn.execute('BEGIN IMMEDIATE')
        if email and conn.execute('SELECT 1 FROM site_users WHERE login_email=? AND lower(username)!=lower(?)',
                                  (email, username)).fetchone():
            raise ValueError('That email is already linked to another account.')
        user = conn.execute('SELECT login_email FROM site_users WHERE lower(username)=lower(?)', (username,)).fetchone()
        if not user:
            raise ValueError('Account not found.')
        conn.execute('UPDATE site_users SET login_email=? WHERE lower(username)=lower(?)', (email, username))
        conn.execute('DELETE FROM web_email_codes WHERE email IN (?, ?)', (user[0], email))


def register_web_sign_in(app, service, site_path):
    init_email_sign_in(site_path)

    @app.context_processor
    def email_admin_context():
        if request.endpoint == 'admin_dashboard':
            return {'login_email_csrf': session.setdefault('login_email_admin_csrf', secrets.token_urlsafe(32))}
        return {}

    @app.post('/admin/users/email')
    def admin_login_email():
        if not session.get('logged_in') or not service.is_admin(session.get('username')):
            abort(403)
        csrf = request.form.get('csrf', '')
        if not csrf or not secrets.compare_digest(csrf.encode(), session.get('login_email_admin_csrf', '').encode()):
            abort(403)
        username = request.form.get('username', '').strip()
        try:
            set_login_email(site_path, username, request.form.get('email', ''))
        except ValueError as exc:
            flash(str(exc), 'error')
        else:
            service.log_activity('Changed sign-in email', target=username,
                                 summary=f'Updated email sign-in for {username}')
            flash(f'Sign-in email saved for {username}.', 'success')
        return redirect(url_for('admin_dashboard', _anchor='users'), code=303)

    def digest(value):
        key = app.secret_key
        if isinstance(key, str):
            key = key.encode()
        return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()

    def enrollment_user():
        if not session.get('logged_in'):
            return None
        user = service.adminfx.get_site_user(session.get('username'))
        return user if user and user.get('active', 1) and not user.get('login_email') else None

    @app.before_request
    def prompt_for_missing_email():
        # Prompt browser visits, including restored sessions, without interrupting
        # native app/API requests or asset downloads. Login itself stays public.
        if (request.method == 'GET' and request.endpoint and
                request.endpoint not in {'login', 'logout', 'static'} and
                not request.path.startswith('/api/') and
                'text/html' in request.headers.get('Accept', '') and enrollment_user()):
            session['email_login_next'] = safe_login_next(request.full_path.rstrip('?'))
            return redirect(url_for('login'))

    def render(error=None, status=200):
        csrf = session.setdefault('email_login_csrf', secrets.token_urlsafe(32))
        with sqlite3.connect(site_path) as conn:
            conn.row_factory = sqlite3.Row
            pending = conn.execute('SELECT email, expires_at, verified_at FROM web_email_codes WHERE id=?',
                                   (session.get('email_login_id'),)).fetchone()
        return render_template('login.html', csrf=csrf, pending=pending,
                               signup=bool(pending and pending['verified_at'] is not None),
                               enrolling=enrollment_user(),
                               remember=session.get('email_login_remember', True),
                               error=error), status

    def finish(username):
        user = service.adminfx.get_site_user(username)
        if not user or not user.get('active', 1):
            return render('This account is unavailable. Please contact Kyle for help.', 403)
        destination = safe_login_next(session.get('email_login_next'))
        remember = session.get('email_login_remember', True)
        session.clear()
        session.permanent = True
        service.establish_user_session(username, login=True)
        service.log_activity('Logged in', summary='Website sign-in', username=username)
        service.clear_login_failures(service._client_ip())
        if not user.get('login_email'):
            session['email_login_next'] = destination
            session['email_login_remember'] = remember
            return redirect(url_for('login'), code=303)
        response = redirect(destination, code=303)
        if remember:
            response.set_cookie('remember_token', service.create_auth_token(username),
                                max_age=90 * 24 * 60 * 60, secure=request.is_secure,
                                httponly=True, samesite='Lax')
        else:
            response.delete_cookie('remember_token', secure=request.is_secure,
                                   httponly=True, samesite='Lax')
        return response

    def rate_limit(conn, kind, key, maximum, window, now):
        key_hash = digest(kind + ':' + key)
        count = conn.execute('SELECT COUNT(*) FROM web_login_events WHERE kind=? AND key_hash=? AND created_at>?',
                             (kind, key_hash, now - window)).fetchone()[0]
        return count >= maximum

    def record(conn, kind, key, now):
        conn.execute('INSERT INTO web_login_events VALUES (?, ?, ?)', (kind, digest(kind + ':' + key), now))

    def login():
        if request.method == 'GET':
            session['email_login_next'] = safe_login_next(request.args.get('next', session.get('email_login_next')))
            if session.get('logged_in'):
                return render() if enrollment_user() else redirect(session['email_login_next'])
            username = service.validate_auth_token(request.cookies.get('remember_token')) if request.cookies.get('remember_token') else None
            if username:
                service.establish_user_session(username)
                return render() if enrollment_user() else redirect(session['email_login_next'])
            return render()
        csrf = request.form.get('csrf', '')
        if not csrf or not secrets.compare_digest(csrf.encode(), session.get('email_login_csrf', '').encode()):
            return render('This page expired. Please try again.', 403)
        action = request.form.get('action', 'send')
        if action == 'change':
            with sqlite3.connect(site_path) as conn:
                conn.execute('DELETE FROM web_email_codes WHERE id=?', (session.pop('email_login_id', None),))
            return redirect(url_for('login', password='1') if request.form.get('password_start') == '1' else url_for('login'), code=303)
        now = int(time())
        ip = service._client_ip()
        if action == 'password':
            # A quiet fallback keeps older accounts without an email accessible.
            with sqlite3.connect(site_path) as conn:
                conn.execute('BEGIN IMMEDIATE')
                conn.execute('DELETE FROM web_login_events WHERE created_at<=?', (now - 3600,))
                limited = rate_limit(conn, 'password', ip, 10, 300, now)
                if not limited:
                    record(conn, 'password', ip, now)
            if limited:
                return render('Too many attempts. Try again in five minutes.', 429)
            username = request.form.get('username', '').strip()
            if not service.verify_password(username, request.form.get('password', '')):
                return render('The username or password is incorrect.', 401)
            session['email_login_remember'] = request.form.get('remember_me') == 'on'
            return finish(service.adminfx.get_site_user(username)['username'])
        if action == 'signup':
            try:
                first_name = clean_signup_name(request.form.get('first_name'))
                last_name = clean_signup_name(request.form.get('last_name'))
            except ValueError as exc:
                return render(str(exc), 400)
            error = None
            with sqlite3.connect(site_path) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute('BEGIN IMMEDIATE')
                proof = conn.execute('SELECT * FROM web_email_codes WHERE id=?', (session.get('email_login_id'),)).fetchone()
                if not proof or proof['verified_at'] is None or proof['expires_at'] <= now or proof['link_username']:
                    error = 'Please verify your email again before creating your account.'
                    if proof and proof['expires_at'] <= now:
                        conn.execute('DELETE FROM web_email_codes WHERE id=?', (proof['id'],))
                else:
                    users = conn.execute('SELECT username, active FROM site_users WHERE login_email=?', (proof['email'],)).fetchall()
                    if len(users) > 1 or (users and not users[0]['active']):
                        error = 'We couldn’t open this account. Please contact Kyle for help.'
                    elif users:
                        username = users[0]['username']
                    else:
                        username = 'email_' + uuid.uuid4().hex
                        conn.execute('INSERT INTO site_users (username, password_hash, is_admin, login_email, display_name, first_name, last_name) VALUES (?, ?, 0, ?, ?, ?, ?)',
                                     (username, generate_password_hash(secrets.token_urlsafe(48)), proof['email'],
                                      first_name + ' ' + last_name, first_name, last_name))
                        conn.execute('INSERT INTO private_accounts (id, username) VALUES (?, ?)', (uuid.uuid4().hex, username))
                    conn.execute('DELETE FROM web_email_codes WHERE id=?', (proof['id'],))
            return render(error, 400) if error else finish(username)
        if action in {'send', 'resend'}:
            if action == 'resend':
                with sqlite3.connect(site_path) as conn:
                    row = conn.execute('SELECT email, link_username, verified_at FROM web_email_codes WHERE id=?', (session.get('email_login_id'),)).fetchone()
                if not row or row[2] is not None:
                    return render('Enter your email to get a new code.', 400)
                owner = enrollment_user()
                if row[1] and (not owner or owner['username'] != row[1]):
                    return render('Please sign in again before adding your email.', 403)
                email = row[0]
            else:
                try:
                    email = normalize_email(request.form.get('email'))
                except ValueError as exc:
                    return render(str(exc), 400)
                session['email_login_remember'] = request.form.get('remember_me') == 'on'
            owner = enrollment_user()
            link_username = owner['username'] if owner else None
            code = f'{secrets.randbelow(10000):04d}'
            identifier = secrets.token_urlsafe(32)
            with sqlite3.connect(site_path) as conn:
                conn.execute('BEGIN IMMEDIATE')
                conn.execute('DELETE FROM web_login_events WHERE created_at<=?', (now - 3600,))
                conn.execute('DELETE FROM web_email_codes WHERE expires_at<=?', (now,))
                limited = (rate_limit(conn, 'email', email, 1, 60, now) or
                           rate_limit(conn, 'email', email, 5, 3600, now) or
                           rate_limit(conn, 'send', ip, 20, 3600, now))
                if not limited:
                    record(conn, 'email', email, now)
                    record(conn, 'send', ip, now)
                    conn.execute('INSERT INTO web_email_codes (id, email, code_hash, expires_at, link_username) VALUES (?, ?, ?, ?, ?)',
                                 (identifier, email, digest(identifier + ':' + code), now + CODE_TTL, link_username))
            if limited:
                return render('Please wait a minute before requesting another code. If you have requested several, try again in an hour.', 429)
            try:
                service.mail.send(Message(
                    subject=f'{code} is your Stats sign-in code', recipients=[email],
                    body=f'Your Stats sign-in code is:\n\n{code}\n\nEnter this code on the sign-in page. It expires in 5 minutes and can only be used once.\n\nIf you did not request this code, you can ignore this email. Do not share the code with anyone.'))
            except Exception:
                # SMTP exceptions can contain recipient data; never log the code.
                app.logger.error('Unable to deliver a website sign-in code')
                with sqlite3.connect(site_path) as conn:
                    conn.execute('DELETE FROM web_email_codes WHERE id=?', (identifier,))
                return render('We couldn’t send your code. Please wait a minute and try again.', 503)
            with sqlite3.connect(site_path) as conn:
                conn.execute('DELETE FROM web_email_codes WHERE id=?', (session.get('email_login_id'),))
            session['email_login_id'] = identifier
            return redirect(url_for('login'), code=303)
        if action != 'verify':
            return render('Please try again.', 400)
        code = request.form.get('code', '').strip().replace(' ', '')
        identifier = session.get('email_login_id', '')
        error = None
        status = 400
        username = None
        with sqlite3.connect(site_path) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('DELETE FROM web_login_events WHERE created_at<=?', (now - 3600,))
            challenge = conn.execute('SELECT * FROM web_email_codes WHERE id=?', (identifier,)).fetchone()
            if rate_limit(conn, 'verify', ip, 30, 300, now):
                error, status = 'Too many attempts. Try again in five minutes.', 429
            elif not challenge or challenge['expires_at'] <= now:
                error = 'This code has expired. Request a new code below.'
            elif challenge['verified_at'] is not None:
                error = 'Your email is already verified. Add your name to finish.'
            elif rate_limit(conn, 'wrong_email', challenge['email'], 6, 3600, now):
                error, status = 'Too many incorrect codes for this email. Try again in an hour.', 429
            elif challenge['attempts'] >= MAX_ATTEMPTS:
                error, status = 'Too many incorrect codes. Request a new code below.', 429
            else:
                record(conn, 'verify', ip, now)
                conn.execute('UPDATE web_email_codes SET attempts=attempts+1 WHERE id=?', (identifier,))
                if not re.fullmatch(r'[0-9]{4}', code) or not secrets.compare_digest(challenge['code_hash'], digest(identifier + ':' + code)):
                    record(conn, 'wrong_email', challenge['email'], now)
                    error = 'That code isn’t correct. Check your email and try again.'
                else:
                    users = conn.execute('SELECT username, active FROM site_users WHERE login_email=?', (challenge['email'],)).fetchall()
                    if challenge['link_username']:
                        owner = conn.execute('SELECT username, active, login_email FROM site_users WHERE username=?', (challenge['link_username'],)).fetchone()
                        if (not session.get('logged_in') or session.get('username') != challenge['link_username'] or
                                not owner or not owner['active'] or owner['login_email']):
                            error, status = 'Please sign in again before adding your email.', 403
                        elif users:
                            error, status = 'This email is already used by another account. Use a different email or contact Kyle for help.', 409
                        else:
                            username = owner['username']
                            conn.execute('UPDATE site_users SET login_email=? WHERE username=?', (challenge['email'], username))
                        conn.execute('DELETE FROM web_email_codes WHERE id=?', (identifier,))
                    elif len(users) > 1 or (users and not users[0]['active']):
                        error, status = 'We couldn’t open this account. Please contact Kyle for help.', 403
                        conn.execute('DELETE FROM web_email_codes WHERE id=?', (identifier,))
                    elif users:
                        username = users[0]['username']
                        conn.execute('DELETE FROM web_email_codes WHERE id=?', (identifier,))
                    else:
                        # Verification is single-use; keep only a short-lived
                        # browser-bound proof for the required name step.
                        conn.execute('UPDATE web_email_codes SET verified_at=?, expires_at=? WHERE id=?', (now, now + 600, identifier))
        if error:
            return render(error, status)
        return finish(username) if username else redirect(url_for('login'), code=303)

    app.extensions['email_login'] = login

    @app.after_request
    def protect_login_response(response):
        if request.endpoint == 'login':
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Referrer-Policy'] = 'no-referrer'
        return response
