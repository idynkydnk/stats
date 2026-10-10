"""Complete entry rosters without changing the database used to save games."""
from pathlib import Path
import re
import sqlite3

from account_stats_views import _database_path, sources_for_user
from player_identity import unique_player_names
from private_accounts import private_database


def entry_player_names(site_path, ordered_names, username, admin=False, women_only=False):
    """Keep recent names first, then append names from every enabled source."""
    paths = [private_database() or site_path]
    paths.extend(_database_path(site_path, source)
                 for source in sources_for_user(site_path, username, admin)
                 if source['enabled'])
    names = []
    for path in dict.fromkeys(paths):
        if not Path(path).is_file():
            continue
        with sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True) as conn:
            for table in ('games',) if women_only else ('players', 'games', 'vollis_games', 'other_games'):
                columns = {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}
                slots = ['full_name'] if table == 'players' and 'full_name' in columns else [
                    column for column in sorted(columns) if re.fullmatch(r'(winner|loser)\d*', column)]
                if women_only and 'division' not in columns:
                    continue
                where = " WHERE division='women'" if women_only else ''
                if slots:
                    query = ' UNION '.join(f'SELECT "{column}" FROM {table}{where}' for column in slots)
                    names.extend(row[0] for row in conn.execute(query) if isinstance(row[0], str) and row[0].strip())
    return unique_player_names([*ordered_names, *sorted(names, key=str.casefold)])
