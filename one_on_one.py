"""Approved 1v1 volleyball formats, combined for browsing without moving games."""
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from flask import abort, request
from request_cache import request_cached

FORMATS = (
    'Vollis', 'Bump three touch full court', 'Bump two touch', 'Cut or high line',
    'Cut shots', 'Cut shots on two', 'Deep court', 'Full court pokey on two',
    'Half court cross court two touch only',
    'Half court diagonal long ways three touches hit only',
    'Half court diagonal long ways two touch only', 'Half court lefty only',
    'Half court long ways',
    'Half court long ways four touch no jump', 'Half court long ways net touch pull',
    'Half court long ways no jump', 'Half court long ways three touches hit only',
    'Half court long ways two touch only', 'Half court no jump lefty only',
    'Half court three touch back corner only',
    'Half court three touches must hit', 'Half court three touches only',
    'Half court two touch lefty only', 'Half court two touch only',
    'Italian short court', 'Mini court',
    'Offense defense no jump', 'Passing', 'Short court no jump',
    'Short court no jump two touch only', 'Short court three boxes',
    'Short court three touch', 'Short court three touch no jump',
    'Short court two boxes', 'Short court two touch only',
)
_CANONICAL = {name.casefold(): name for name in FORMATS}


def canonical_format(name):
    return _CANONICAL.get((name or '').strip().casefold())


def selected_format():
    value = request.args.get('format', '').strip()
    if value and not canonical_format(value):
        abort(400, 'Unknown 1v1 volleyball format')
    return canonical_format(value) or ''


def normalize_other(row):
    game = dict(row)
    name = canonical_format(game.get('game_name'))
    if not name or (game.get('game_type') or '').strip().casefold() != 'volleyball':
        return None
    sides = [[(game.get(f'{side}{i}') or '').strip() for i in range(1, 16)]
             for side in ('winner', 'loser')]
    sides = [[name for name in side if name] for side in sides]
    if any(len(side) != 1 for side in sides) or sides[0] == sides[1]:
        return None
    def score(side):
        if game.get(f'{side}_score') is not None:
            return game[f'{side}_score']
        return next((game.get(f'{side}{i}_score') for i in range(1, 16)
                     if (game.get(f'{side}{i}') or '').strip()), None)
    return dict(id=-game['id'], source_id=game['id'], source='other', game_name=name,
                winner=sides[0][0], loser=sides[1][0], winner_score=score('winner'),
                loser_score=score('loser'), game_date=game['game_date'],
                updated_at=game.get('updated_at'), entered_timezone=game.get('entered_timezone'),
                location=game.get('location'), comment=game.get('comment'),
                other_game=dict(game, winners=[dict(name=sides[0][0], score=game.get('winner1_score'))],
                                losers=[dict(name=sides[1][0], score=game.get('loser1_score'))]))


@request_cached
def games(year='All years', format_name=''):
    from vollis_functions import set_cur
    from other_functions import other_year_games_raw
    cur = set_cur()
    try:
        sql = 'SELECT * FROM vollis_games'
        args = ()
        if year != 'All years':
            sql += " WHERE strftime('%Y', game_date)=?"
            args = (str(year),)
        rows = cur.execute(sql, args)
        columns = [col[0] for col in cur.description]
        result = []
        for row in rows:
            game = dict(zip(columns, row))
            game.update(source='vollis', source_id=game['id'], game_name='Vollis')
            game['winner'] = game['winner'].strip()
            game['loser'] = game['loser'].strip()
            if game['winner'] and game['loser'] and game['winner'] != game['loser']:
                result.append(game)
    finally:
        cur.connection.close()
    result.extend(game for row in other_year_games_raw(year) if (game := normalize_other(row)))
    if format_name:
        result = [game for game in result if game['game_name'] == format_name]
    return sorted(result, key=lambda g: (g['game_date'] or '', g['source'], g['source_id']), reverse=True)


def years(format_name='', player=None):
    return sorted({str(g['game_date'])[:4] for g in games('All years', format_name)
                   if not player or player in (g['winner'], g['loser'])}, reverse=True) + ['All years']


@request_cached
def formats_by_total_games():
    """Order menu choices by all-time games, with alphabetical ties."""
    counts = Counter(g['game_name'] for g in games('All years', ''))
    return sorted(FORMATS, key=lambda name: (-counts[name], name.casefold()))


def rankings(rows, today=False):
    counts = defaultdict(lambda: [0, 0, 0])
    for g in rows:
        margin = (g.get('winner_score') or 0) - (g.get('loser_score') or 0)
        counts[g['winner']][0] += 1
        counts[g['loser']][1] += 1
        counts[g['winner']][2] += margin
        counts[g['loser']][2] -= margin
    result = [[name, w, l, w / (w + l)] + ([margin] if today else [])
              for name, (w, l, margin) in counts.items()]
    return sorted(result, key=lambda row: (-row[3], -row[1], row[0].casefold()))


def ratings(rows):
    from game_ratings import rate_matches
    # All rows here have passed the approved-format and one-player-per-side checks.
    ordered = sorted(rows, key=lambda g: (g['game_date'] or '', g['source'], g['source_id']))
    matches = [([g['winner']], [g['loser']]) for g in ordered
               if not any('?' in name or name.casefold() in {'unknown', 'none', 'n/a'}
                          for name in (g['winner'], g['loser']))]
    values = rate_matches(matches)
    return dict(ratings=values, rating_enabled=bool(values), rated_games=len(matches),
                unrated_games=len(rows) - len(matches), rating_sort=any(not r['provisional'] for r in values.values()))


def today_games(format_name=''):
    # Keep the existing volleyball session-day boundary.
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=15)).strftime('%Y-%m-%d')
    return [g for g in games('All years', format_name) if str(g['game_date']) > cutoff]


def standings(year, format_name=''):
    from stats_location_filter import active_location_filter
    rows = games(year, format_name)
    available = years(format_name)
    display_year = year
    previous = str(date.today().year - 1)
    if not rows and year == str(date.today().year) and previous in available and not any(active_location_filter()):
        display_year = previous
        rows = games(previous, format_name)
    info = ratings(rows)
    stats = rankings(rows)
    if info['rating_sort']:
        stats.sort(key=lambda r: info['ratings'].get(r[0], {}).get('rating', float('-inf')), reverse=True)
    today = today_games(format_name)
    return dict(year=year, display_year=display_year, showing_previous_year=display_year != year,
                all_years=available, stats=stats, rating_info=info,
                today_stats=rankings(today, today=True), today_games=today,
                format_name=format_name, one_on_one_formats=formats_by_total_games())


def tuples(rows, display=False):
    from time_display import format_game_time
    return [[g['id'], format_game_time(g['game_date'], g.get('entered_timezone')) if display else g['game_date'],
             g['winner'], g.get('winner_score'), g['loser'], g.get('loser_score'), g.get('updated_at'),
             g['game_name'], g['source'], g['source_id']] for g in rows]


def player_data(year, name, format_name=''):
    from vollis_functions import vollis_opponent_stats_by_year
    from stat_functions import player_matchup_min_games
    rows = [g for g in games(year, format_name) if name in (g['winner'], g['loser'])]
    minimum = player_matchup_min_games(len(rows))
    stats = next((r for r in rankings(rows) if r[0] == name), [name, 0, 0, 0])
    return dict(games=rows, stats=[stats + [len(rows)]],
                opponent_stats=vollis_opponent_stats_by_year(name, tuples(rows), minimum) if rows else [],
                winpct_min_games=minimum, all_years=years(format_name, name),
                format_name=format_name, one_on_one_formats=formats_by_total_games())


def api_stats(year):
    from ios_api import _card_stats, _ranking
    context = standings(year, selected_format())
    return dict(year=year, display_year=context['display_year'],
                showing_previous_year=context['showing_previous_year'], all_years=context['all_years'],
                stats=_card_stats(dict(stats=context['stats'], **context['rating_info']))['stats'],
                today_stats=[_ranking(r, rating_key='plus_minus') for r in context['today_stats']],
                today_game_count=len(context['today_games']), formats=context['one_on_one_formats'])


def api_games(year):
    import stats as S
    rows = games(year, selected_format())
    tokens = request.args.get('q', '').casefold().split()
    if tokens:
        rows = [g for g in rows if all(t in (' '.join(str(g.get(k) or '') for k in
                    ('game_date', 'game_name', 'winner', 'loser'))).casefold() for t in tokens)]
    total = len(rows)
    try:
        offset = max(0, int(request.args.get('offset', 0)))
        limit = min(200, max(1, int(request.args.get('limit', 50))))
    except ValueError:
        abort(400, 'Invalid page')
    page = [dict(g) for g in rows[offset:offset + limit]]
    for source, table in [('vollis', 'vollis_games'), ('other', 'other_games')]:
        editable = S._editable_game_ids(table, [g['source_id'] for g in page if g['source'] == source])
        for game in page:
            if game['source'] == source:
                game['can_edit'] = game['source_id'] in editable
    return dict(games=page, total=total, next_offset=offset + limit if offset + limit < total else None,
                all_years=years(selected_format()))


def api_player(year, name):
    from ios_api import _abs, _ranking, _S
    data = player_data(year, name, selected_format())
    # Player history uses the common two-side model in the app.
    history = [dict(g, winner1=g['winner'], loser1=g['loser']) for g in data['games']]
    return dict(name=name, year=year, all_years=data['all_years'], stats=_ranking(data['stats'][0][:4]),
                opponents=data['opponent_stats'], winpct_min_games=data['winpct_min_games'],
                games=history, photo_url=_abs(_S().player_avatar_context(name).get('player_photo_url')))
