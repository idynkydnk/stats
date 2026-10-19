"""Compile shared templates before traffic and avoid rebuilding repeated URL parts."""
from pathlib import Path
from urllib.parse import quote

from flask import g, url_for
from jinja2 import FileSystemBytecodeCache


class OptionalBytecodeCache(FileSystemBytecodeCache):
    def load_bytecode(self, bucket):
        try:
            super().load_bytecode(bucket)
        except OSError:
            pass

    def dump_bytecode(self, bucket):
        try:
            super().dump_bytecode(bucket)
        except OSError:
            pass


def player_stats_url(year, name):
    # url_for still owns routing, deployment prefixes and current view/filter
    # defaults. Only the varying path component is quoted here, once per row.
    patterns = g.setdefault('player_url_patterns', {})
    year = str(year)
    if year not in patterns:
        patterns[year] = url_for('player_stats', year=year, name='__STATS_PLAYER_NAME__')
    return patterns[year].replace('__STATS_PLAYER_NAME__', quote(str(name), safe=''))


def matchup_records(rows, name_key):
    return [[row[name_key], row['win_percentage'], row['wins'], row['losses'],
             row['total_games'], int(bool(row['meets_min'])), row['sample_tier'],
             format(row['win_percentage'] * 100, '.0f')] for row in rows]


def register_template_delivery(app):
    app.jinja_env.globals['player_stats_url'] = player_stats_url
    app.jinja_env.filters['matchup_records'] = matchup_records
    app.jinja_env.filters['standings_records'] = lambda rows: [
        list(row) + [format(row[4], '.2f'), format(row[3] * 100, '.0f')] for row in rows]
    directory = Path(app.extensions['stats_response_cache'].directory) / 'templates'
    try:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        app.jinja_env.bytecode_cache = OptionalBytecodeCache(str(directory))
    except OSError:
        pass
    # Compilation stores template code only, never rendered content. Every
    # worker shares bytecode checked against Jinja's source checksum. Do this
    # after filters/extensions are registered and before accepting requests.
    for name in app.jinja_env.list_templates(extensions=['html']):
        app.jinja_env.get_template(name)
