"""Account labels are separate from stable login and game ownership keys."""
import re
import unicodedata


def ensure_display_name_column(conn):
    columns = {row[1] for row in conn.execute('PRAGMA table_info(site_users)')}
    if 'display_name' not in columns:
        conn.execute('ALTER TABLE site_users ADD COLUMN display_name TEXT')


def clean_display_name(value):
    if not isinstance(value, str):
        return None
    value = ' '.join(value.split())
    if not value or len(value) > 200 or any(
        char in '<>' or unicodedata.category(char).startswith('C') for char in value
    ):
        return None
    return value


def account_label(username, display_name=None):
    if display_name:
        return display_name
    match = re.fullmatch(r'(google|apple)_[0-9a-f]{32}', username, re.IGNORECASE)
    if match:
        return match[1].title() + ' account'
    return username


def user_display_name(username, user, players):
    """Prefer a linked player, then a provider name or an unambiguous roster match."""
    username = (username or '').strip()
    if not username:
        return ''
    by_name = {player['name'].casefold(): player['name'] for player in players}
    stored = (user.get('player_name') or '').strip()
    if stored:
        return by_name.get(stored.casefold(), stored)
    if user.get('display_name'):
        return user['display_name']
    label = account_label(username)
    if label != username:
        return label
    key = username.casefold()
    if key in by_name:
        return by_name[key]
    matches = {
        player['name'].casefold(): player['name'] for player in players
        if player['name'].split()[0].casefold() == key
        or (player.get('nickname') or '').strip().casefold() == key
    }
    if len(matches) == 1:
        return next(iter(matches.values()))
    return username.title() if username.islower() or username.isupper() else username


def database_display_names(conn):
    """Resolve labels once from the identity database, never a combined game view."""
    columns = {row[1] for row in conn.execute('PRAGMA table_info(players)')}
    players = []
    if 'full_name' in columns:
        nickname = 'nickname' if 'nickname' in columns else "''"
        players = [dict(name=row[0].strip(), nickname=row[1]) for row in conn.execute(
            f"SELECT full_name, {nickname} FROM players WHERE TRIM(COALESCE(full_name, '')) != ''")]
    cursor = conn.execute('SELECT * FROM site_users')
    fields = [column[0] for column in cursor.description]
    users = [dict(zip(fields, row)) for row in cursor]
    return {user['username'].casefold(): user_display_name(user['username'], user, players)
            for user in users}
