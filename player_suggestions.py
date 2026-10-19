"""Complete entry rosters without changing the database used to save games."""
from pathlib import Path
from contextlib import closing
import re
import sqlite3
from flask import has_request_context, request

from account_stats_views import _database_path, sources_for_user
from player_identity import unique_player_names
from private_accounts import private_database


def entry_player_names(site_path, ordered_names, username, admin=False, women_only=False):
    """Keep recent names first, then append names from every enabled source."""
    paths = [private_database() or site_path]
    paths.extend(_database_path(site_path, source)
                 for source in sources_for_user(site_path, username, admin)
                 if source['enabled'])
    paths = tuple(dict.fromkeys(str(Path(path).resolve()) for path in paths if Path(path).is_file()))
    if has_request_context() and request.method == 'GET':
        from prepared_calculations import reuse_calculation
        from stats_snapshot_cache import source_revision
        # Re-resolve permissions on every request before any shared lookup.
        # Keep this revision separate from the owned database used to save games.
        names = reuse_calculation(_source_player_names, (paths, women_only), {},
                                  revision=source_revision([(path, 0) for path in paths]))
    else:
        names = _source_player_names(paths, women_only)
    return unique_player_names([*ordered_names, *names])


def _source_player_names(paths, women_only):
    names = []
    for path in paths:
        with closing(sqlite3.connect(Path(path).as_uri() + '?mode=ro', uri=True)) as conn:
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
    return unique_player_names(sorted(names, key=str.casefold))
