"""Season calculations from explicitly owned records; never from a browse snapshot."""
from collections import defaultdict
from contextlib import closing
from datetime import datetime
from pathlib import Path
import os
import sqlite3
from zoneinfo import ZoneInfo

from doubles_division import DIVISIONS
from game_ratings import match_teams, rate_matches
from other_game_outcomes import is_tied_game
from stat_functions import _calculate_trueskill_from_games, minimum_games_threshold

MINIMUM_EXPLANATION = (
    'Automatic uses the same rule as the site: divide the number of games in each '
    'season standings group by 30, round down, and use at least 1. For example, '
    '90 games means a player needs 3 games to qualify. It grows with participation, '
    'so a busy season asks for more games without making a quieter season too hard '
    'to qualify for. Choose a fixed minimum if your league needs a specific target.'
)
AWARDS_EXPLANATION = (
    'Ratings start fresh and use only this season’s games. Each game format has its own '
    'standings. The highest-rated qualifying player wins; formats without ratings use '
    'win percentage. Equal results share the award. Most improved is the largest positive '
    'rating gain from the end of a player’s first rated playing day to their latest, '
    'with at least two rated playing days and the season minimum. Awards become final '
    'after the end day; corrections to games or season settings update the results.'
)


def season_status(season, today=None):
    today = today or datetime.now(ZoneInfo(season['timezone'])).date().isoformat()
    if today < season['start_date']:
        return 'Upcoming'
    return 'Completed' if today > season['end_date'] else 'Active'


def owned_groups(site_path, season):
    """Resolve storage on the server and require original-entry attribution, even for admins."""
    from private_accounts import account_for_user
    account = account_for_user(site_path, season['owner'])
    path = Path(site_path).resolve()
    if account:
        root = Path(os.environ.get('STATS_PRIVATE_DATA_DIR') or str(path.resolve().parent / 'private_data'))
        path = root / (account['id'] + '.db')
    if not path.is_file():
        return {}
    groups = {}
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        for table in ('games', 'vollis_games', 'other_games'):
            columns = {r[1] for r in conn.execute(f'PRAGMA table_info({table})')}
            if not {'entered_by', 'game_date'} <= columns:
                continue
            rows = conn.execute(
                f'''SELECT * FROM {table} WHERE TRIM(entered_by)=? COLLATE NOCASE
                    AND substr(game_date,1,10) BETWEEN ? AND ? ORDER BY game_date, id''',
                (season['owner'], season['start_date'], season['end_date']))
            for row in rows:
                game = dict(row)
                if table == 'games':
                    division = game.get('division') or 'open'
                    key, title = 'doubles:' + division, DIVISIONS.get(division, 'Doubles')
                    winners = [game.get('winner1'), game.get('winner2')]
                    losers = [game.get('loser1'), game.get('loser2')]
                elif table == 'vollis_games':
                    key, title = 'other:volleyball:vollis', 'Vollis'
                    winners, losers = [game.get('winner')], [game.get('loser')]
                    game.update(game_name='Vollis', game_type='Volleyball',
                                winner1=game.get('winner'), loser1=game.get('loser'))
                else:
                    title = (game.get('game_name') or 'Other game').strip()
                    key = 'other:' + (game.get('game_type') or '').strip().casefold() + ':' + title.casefold()
                    winners = [game.get(f'winner{i}') for i in range(1, 16)]
                    losers = [game.get(f'loser{i}') for i in range(1, 16)]
                winners = [p.strip() for p in winners if isinstance(p, str) and p.strip()]
                losers = [p.strip() for p in losers if isinstance(p, str) and p.strip()]
                game.update(winners=winners, losers=losers, source=table,
                            key=table + ':' + str(game['id']), tied=is_tied_game(game))
                group = groups.setdefault(key, dict(id=key, title=title, games=[]))
                group['games'].append(game)
    for group in groups.values():
        group['games'].sort(key=lambda g: (g['game_date'], g['source'], g['id']))
    return groups


def _known(name):
    return '?' not in name and name.casefold() not in {'unknown', 'none', 'n/a'}


def group_standings(group, fixed_minimum):
    games = group['games']
    minimum = fixed_minimum if fixed_minimum is not None else minimum_games_threshold(len(games))
    players = {}
    for game in games:
        for side, rivals, won in ((game['winners'], game['losers'], True), (game['losers'], game['winners'], False)):
            for name in set(side):
                if not _known(name):
                    continue
                row = players.setdefault(name, dict(name=name, wins=0, losses=0, ties=0, games=0,
                                                    rating=None, first_rating=None, rating_gain=None))
                row['games'] += 1
                row['ties' if game['tied'] else 'wins' if won else 'losses'] += 1
    # Observer captures the player's end-of-first-day rating in a single replay.
    first_days, rated_days, baselines = {}, defaultdict(set), {}
    def observer_for(rated_games):
        def observe(index, player, rating):
            day = rated_games[index]['game_date'][:10]
            first_days.setdefault(player, day)
            rated_days[player].add(day)
            if first_days[player] == day:
                baselines[player] = rating
        return observe
    if group['id'].startswith('doubles:'):
        rated = [game for game in games if len(game['winners']) == len(game['losers']) == 2
                 and match_teams(dict(game, game_type='Volleyball', game_name='Doubles'))]
    else:
        rated = [game for game in games if match_teams(game)]
    if group['id'].startswith('doubles:'):
        tuples = [(g['id'], g['game_date'], *g['winners'], g.get('winner_score'), *g['losers'], g.get('loser_score')) for g in rated]
        ratings = {r['player']: r['rating'] for r in _calculate_trueskill_from_games(tuples, observer_for(rated))}
    else:
        ratings = {p: value['rating'] for p, value in rate_matches([match_teams(g) for g in rated], observer_for(rated)).items()}
    for name, row in players.items():
        row.update(win_pct=row['wins'] / row['games'], games_needed=max(0, minimum - row['games']),
                   qualified=row['games'] >= minimum, rating=ratings.get(name), first_rating=baselines.get(name))
        if name in ratings and len(rated_days[name]) >= 2:
            row['rating_gain'] = round(ratings[name] - baselines[name], 2)
    rows = sorted(players.values(), key=lambda r: (-(r['rating'] if r['rating'] is not None else -float('inf')),
                                                  -r['win_pct'], -r['games'], r['name'].casefold()))
    qualified = [r for r in rows if r['qualified']]
    metric = 'rating' if ratings else 'win_pct'
    contenders = [r for r in qualified if r[metric] is not None]
    champions = [r for r in contenders if r[metric] == max(p[metric] for p in contenders)] if contenders else []
    improved = [r for r in qualified if r['rating_gain'] is not None and r['rating_gain'] > 0]
    improved = [r for r in improved if r['rating_gain'] == max(p['rating_gain'] for p in improved)] if improved else []
    return dict(id=group['id'], title=group['title'], game_count=len(games), minimum_games=minimum,
                rating_enabled=bool(ratings), rated_games=len(rated), unrated_games=len(games) - len(rated),
                stats=qualified, rare_stats=[r for r in rows if not r['qualified']],
                champions=champions, most_improved=improved, award_metric=metric)


def season_results(site_path, season, player=None, group_id=None):
    groups = owned_groups(site_path, season)
    result = dict(groups=[group_standings(g, season['minimum_games'])
                          for g in sorted(groups.values(), key=lambda g: (not g['id'].startswith('doubles:'), g['title'].casefold()))])
    result['game_count'] = sum(g['game_count'] for g in result['groups'])
    if player is not None:
        group = next((g for g in result['groups'] if g['id'] == group_id), None)
        row = next((r for r in group['stats'] + group['rare_stats'] if r['name'] == player), None) if group else None
        if not row:
            return None
        # Only public sports fields: no author, contact details, comments, or external profile links.
        history = [dict(id=g['key'], day=g['game_date'][:10], winners=g['winners'], losers=g['losers'],
                        winner_score=g.get('winner_score'), loser_score=g.get('loser_score'),
                        result='Tie' if g['tied'] else 'Win' if player in g['winners'] else 'Loss')
                   for g in reversed(groups[group_id]['games']) if player in g['winners'] + g['losers']]
        result['player'] = dict(stats=row, group_title=group['title'], games=history)
    return result
