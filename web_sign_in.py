"""Browser sign-in using the same provider subjects and accounts as the iPhone app."""
import hashlib
import os
import secrets
import sqlite3
import time
from urllib.parse import unquote, urlsplit

from flask import has_request_context, jsonify, request, session, url_for

from account_names import clean_display_name


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


def provider_config():
    return {
        'google_client_id': os.environ.get('GOOGLE_WEB_CLIENT_ID', '').strip(),
        'apple_client_id': os.environ.get('APPLE_WEB_CLIENT_ID', '').strip(),
        'apple_redirect_uri': os.environ.get('APPLE_WEB_REDIRECT_URI', '').strip(),
    }


def register_web_sign_in(app, service, site_path, social_session):
    @app.context_processor
    def login_context():
        if request.endpoint != 'login':
            return {}
        config = provider_config()
        nonce = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        expires = int(time.time()) + 600
        session['web_sign_in'] = {'nonce': nonce, 'csrf': csrf, 'expires': expires}
        with sqlite3.connect(site_path) as conn:
            conn.execute('DELETE FROM private_auth_challenges WHERE expires_at < ?', (int(time.time()),))
            conn.execute('INSERT INTO private_auth_challenges VALUES (?, ?)',
                         (hashlib.sha256(nonce.encode()).hexdigest(), expires))
        config.update(nonce=nonce, csrf=csrf,
                      next=safe_login_next(request.values.get('next')),
                      google_url=url_for('web_social_login', provider='google'),
                      apple_url=url_for('web_social_login', provider='apple'))
        return {'web_sign_in': config}

    @app.after_request
    def protect_login_response(response):
        if request.endpoint in {'login', 'web_social_login'}:
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
            response.headers['Cross-Origin-Opener-Policy'] = 'same-origin-allow-popups'
        return response

    @app.post('/auth/<provider>', endpoint='web_social_login')
    def web_social_login(provider):
        import jwt
        from google.auth.exceptions import GoogleAuthError, TransportError

        if provider not in {'google', 'apple'}:
            return jsonify(error='Unknown sign-in provider.'), 404
        ip = service._client_ip()
        if service.login_rate_limited(ip):
            return jsonify(error='Too many attempts. Try again in a few minutes.'), 429
        service.record_login_failure(ip)
        body = request.get_json(silent=True)
        challenge = session.get('web_sign_in') or {}
        csrf = request.headers.get('X-CSRF-Token', '')
        if (not challenge or not secrets.compare_digest(csrf.encode(), challenge['csrf'].encode()) or
                challenge['expires'] < int(time.time())):
            return jsonify(error='This sign-in page expired. Reload the page and try again.'), 403
        if not isinstance(body, dict) or not isinstance(body.get('id_token'), str):
            return jsonify(error='Sign-in could not be verified. Please try again.'), 400
        config = provider_config()
        audience = config[provider + '_client_id']
        if not audience or (provider == 'apple' and not config['apple_redirect_uri']):
            return jsonify(error=f'{provider.title()} sign-in is not available on the website yet. Please use your password or the app.'), 503
        try:
            if provider == 'google':
                from google.auth.transport.requests import Request
                from google.oauth2.id_token import verify_oauth2_token
                claims = verify_oauth2_token(body['id_token'], Request(), audience)
                if claims.get('email_verified') is not True:
                    raise ValueError('Unverified Google account')
                full_name = clean_display_name(claims.get('name')) or ' '.join(
                    part for part in (clean_display_name(claims.get('given_name')),
                                      clean_display_name(claims.get('family_name'))) if part)
            else:
                if not secrets.compare_digest(str(body.get('state', '')), challenge['csrf']):
                    raise ValueError('Wrong Apple state')
                keys = jwt.PyJWKClient('https://appleid.apple.com/auth/keys', timeout=10)
                key = keys.get_signing_key_from_jwt(body['id_token'])
                claims = jwt.decode(body['id_token'], key.key, algorithms=['RS256'],
                                    audience=audience, issuer='https://appleid.apple.com',
                                    options={'require': ['exp', 'iat', 'sub', 'aud', 'iss', 'nonce']})
                full_name = clean_display_name(body.get('full_name'))
            if (not isinstance(claims.get('sub'), str) or not claims['sub'] or
                    not secrets.compare_digest(str(claims.get('nonce', '')), challenge['nonce'])):
                raise ValueError('Wrong identity or nonce')
            with sqlite3.connect(site_path) as conn:
                consumed = conn.execute(
                    'DELETE FROM private_auth_challenges WHERE nonce_hash=? AND expires_at>=?',
                    (hashlib.sha256(challenge['nonce'].encode()).hexdigest(), int(time.time()))).rowcount
            if consumed != 1:
                raise ValueError('Expired or reused challenge')
        except TransportError:
            app.logger.exception('Website %s verification unavailable', provider)
            return jsonify(error='Sign-in is temporarily unavailable. Please try again.'), 503
        except (jwt.InvalidTokenError, GoogleAuthError, ValueError, TypeError):
            return jsonify(error='Sign-in could not be verified. Reload the page and try again.'), 401
        except Exception:
            app.logger.exception('Website %s verification unavailable', provider)
            return jsonify(error='Sign-in is temporarily unavailable. Please try again.'), 503

        def complete(username):
            user = service.adminfx.get_site_user(username)
            if not user or not user.get('active', 1):
                return jsonify(error='This account is inactive.'), 401
            session.clear()
            session.permanent = True
            service.establish_user_session(username, login=True)
            response = jsonify(next=safe_login_next(body.get('next')))
            if body.get('remember_me') is True:
                response.set_cookie('remember_token', service.create_auth_token(username),
                                    max_age=90 * 24 * 60 * 60, secure=request.is_secure,
                                    httponly=True, samesite='Lax')
            else:
                response.delete_cookie('remember_token', secure=request.is_secure,
                                       httponly=True, samesite='Lax')
            return response

        return social_session(provider, claims['sub'], full_name, complete=complete)
