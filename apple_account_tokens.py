"""Server-only Sign in with Apple authorization exchange and token revocation."""
import os
from pathlib import Path
import sqlite3
import time

from cryptography.fernet import Fernet, InvalidToken
import jwt
import requests


class AppleAccountError(Exception):
    """Safe message only; never put upstream responses or credentials in logs."""


def client_id():
    return os.environ.get('APPLE_IOS_CLIENT_ID', 'com.kt.stats')


def _cipher():
    try:
        return Fernet(os.environ['APPLE_TOKEN_ENCRYPTION_KEY'].encode())
    except (KeyError, ValueError) as exc:
        raise AppleAccountError('Apple sign-in is temporarily unavailable. Please try again later.') from exc


def _client_secret():
    try:
        team = os.environ['APPLE_TEAM_ID']
        key_id = os.environ['APPLE_KEY_ID']
        private_key = os.environ.get('APPLE_PRIVATE_KEY')
        if not private_key:
            private_key = Path(os.environ['APPLE_PRIVATE_KEY_PATH']).read_text()
        now = int(time.time())
        return jwt.encode({'iss': team, 'iat': now, 'exp': now + 300,
                           'aud': 'https://appleid.apple.com', 'sub': client_id()},
                          private_key.replace('\\n', '\n'), algorithm='ES256', headers={'kid': key_id})
    except (KeyError, ValueError, TypeError, OSError, jwt.PyJWTError) as exc:
        raise AppleAccountError('Apple sign-in is temporarily unavailable. Please try again later.') from exc


def _post(endpoint, fields):
    try:
        response = requests.post('https://appleid.apple.com/auth/' + endpoint,
                                 data={'client_id': client_id(), 'client_secret': _client_secret(), **fields},
                                 timeout=(5, 15), allow_redirects=False)
    except requests.RequestException as exc:
        raise AppleAccountError('Apple could not be reached. Please try again.') from exc
    if response.status_code != 200:
        raise AppleAccountError('Apple could not complete this request. Please sign in with Apple again and retry.')
    return response


def exchange_code(code, subject, nonce_hash):
    """Bind the authorization code to the separately verified native identity."""
    cipher = _cipher()  # Check storage configuration before consuming the code.
    if not isinstance(code, str) or not 1 <= len(code) <= 4096:
        raise AppleAccountError('Please update the app and sign in with Apple again.')
    response = _post('token', {'grant_type': 'authorization_code', 'code': code})
    try:
        body = response.json()
        token = body['id_token']
        key = jwt.PyJWKClient('https://appleid.apple.com/auth/keys', timeout=10).get_signing_key_from_jwt(token)
        claims = jwt.decode(token, key.key, algorithms=['RS256'], audience=client_id(),
                            issuer='https://appleid.apple.com',
                            options={'require': ['exp', 'iat', 'sub', 'aud', 'iss']})
        if claims['sub'] != subject or claims.get('nonce') != nonce_hash:
            raise ValueError('Mismatched identity')
        refresh = body['refresh_token']
        if not isinstance(refresh, str) or not refresh:
            raise ValueError('Missing refresh token')
        return cipher.encrypt(refresh.encode()).decode()
    except (ValueError, KeyError, TypeError, jwt.PyJWTError) as exc:
        raise AppleAccountError('Apple sign-in could not be verified. Please try again.') from exc


def save_token(path, username, encrypted_token):
    with sqlite3.connect(path) as conn:
        conn.execute('INSERT INTO apple_account_tokens(username, encrypted_refresh_token) VALUES (?, ?) '
                     'ON CONFLICT(username) DO UPDATE SET encrypted_refresh_token=excluded.encrypted_refresh_token',
                     (username, encrypted_token))


def revoke_account_token(path, username):
    """Return False when no usable token remains; callers must still delete data.

    Missing credentials and unreadable stored ciphertext require manual Apple
    disconnection after local deletion (TN3194). Server configuration or Apple
    transport failures remain retryable rather than being reported as revocation.
    """
    with sqlite3.connect(path) as conn:
        row = conn.execute('SELECT encrypted_refresh_token FROM apple_account_tokens WHERE username=?', (username,)).fetchone()
    if not row or not isinstance(row[0], str) or not row[0]:
        return False
    cipher = _cipher()  # A missing/malformed server key is a configuration error.
    try:
        refresh = cipher.decrypt(row[0].encode()).decode()
    except (InvalidToken, UnicodeError):
        return False
    if not refresh:
        return False
    # Apple's endpoint returns 200 for both newly and previously revoked tokens.
    _post('revoke', {'token': refresh, 'token_type_hint': 'refresh_token'})
    return True
