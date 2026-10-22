"""Prepare an ordinary, isolated review account; dry-run unless --apply is given.

Run on the deployed server after its normal schema startup. No emails are sent,
no admin role is granted, and no authentication or consent checks are bypassed.
"""
import argparse
from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def inspect_target(database, username, email):
    from web_sign_in import normalize_email
    email = normalize_email(email)
    if not re.fullmatch(r'appreview[-_a-zA-Z0-9]{0,50}', username):
        raise ValueError('Use an appreview-prefixed account name.')
    database = Path(database).resolve(strict=True)
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {'site_users', 'private_accounts', 'private_deleted_accounts',
                    'stats_source_group', 'account_stats_sources', 'games', 'players'}
        if not required <= tables:
            raise ValueError('Start the updated website first to initialize its account schema.')
        if conn.execute('SELECT 1 FROM site_users WHERE username=? COLLATE NOCASE OR login_email=? COLLATE NOCASE',
                        (username, email)).fetchone():
            raise ValueError('The username or email is already in use; existing accounts are never overwritten.')
    return str(database), email


def create_review_account(database, username, email, password):
    from private_accounts import create_account, account_for_user, provision_database
    from web_sign_in import set_login_email
    from create_games_database import create_game
    database, email = inspect_target(database, username, email)
    if not isinstance(password, str) or len(password) < 20:
        raise ValueError('Use a generated password of at least 20 characters.')
    create_account(database, username, password=password)
    # This is the same explicit email assignment available in the admin tools.
    # Use a dedicated address controlled by the operator, not another player's.
    set_login_email(database, username, email)
    account = account_for_user(database, username)
    with sqlite3.connect(database) as conn:
        conn.execute("UPDATE site_users SET display_name='App Review', first_name='App', last_name='Review' WHERE username=?", (username,))
        conn.execute('UPDATE private_accounts SET share_stats=0 WHERE id=?', (account['id'],))
    private_path = provision_database(database, account['id'])
    names = ['Review Alex', 'Review Blair', 'Review Casey', 'Review Drew']
    with sqlite3.connect(private_path) as conn:
        for name in names:
            conn.execute('INSERT INTO players(full_name) VALUES (?)', (name,))
        conn.commit()
        for days_ago, score in ((7, 16), (3, 19), (1, 18)):
            create_game(conn, (
                str(date.today() - timedelta(days=days_ago)), names[0], names[1], 21,
                names[2], names[3], score, datetime.now().isoformat(sep=' '),
                'Fictional sample game for App Review.', 'America/Los_Angeles', username, 'Sample Court',
            ))
    return {'username': username, 'password': password, 'email': email,
            'instructions': 'Login > Use my existing password. Enter this username and password. '
                            'Sample players and games are fictional and isolated. AI permission starts off.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    parser.add_argument('--email', required=True, help='Dedicated email or alias controlled by the operator')
    parser.add_argument('--username', default='appreview-20261021')
    parser.add_argument('--credentials-file', help='New private file outside the repository; never printed')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    database, email = inspect_target(args.database, args.username, args.email)
    if not args.apply:
        print('Dry run: target schema and unused account identifiers verified. No data changed.')
        print('Add --apply --credentials-file /protected/path/review.json to create the isolated account.')
        return
    if not args.credentials_file:
        parser.error('--apply requires --credentials-file')
    destination = Path(args.credentials_file).expanduser().resolve()
    if destination == ROOT or ROOT in destination.parents:
        parser.error('Save credentials outside the repository.')
    # Reserve a new 0600 file before changing any account data. Never overwrite
    # credentials from an earlier run, and never print the generated password.
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    password = secrets.token_urlsafe(24)
    with os.fdopen(descriptor, 'w') as output:
        output.write(json.dumps({'username': args.username, 'password': password,
                                 'email': email, 'status': 'provisioning'}, indent=2))
    result = create_review_account(database, args.username, email, password)
    destination.write_text(json.dumps({**result, 'status': 'created'}, indent=2) + '\n')
    print('Created ordinary private review account with three fictional games. Credentials are in the protected file.')


if __name__ == '__main__':
    main()
