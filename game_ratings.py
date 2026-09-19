"""Two-side TrueSkill ratings, isolated by game and requested season/location.

Uses the closed-form Gaussian update for a decisive result between two teams
(Microsoft's TrueSkill model, mu=25, sigma=25/3, beta=25/6, tau=25/300).
No inferred ordering among individual losers and no cross-game rating pooling.
"""
import math
from collections import defaultdict

HEAD_TO_HEAD_GAMES = {'backgammon', 'scrabble', 'sequence', 'euchre', 'gin rummy',
                      'otrio', 'spot it!', 'sushi go!', 'catan', 'tic-tac-toe', 'ping pong'}
ROTATING_GAMES = {'kings', 'coed kings/queens', 'vollis kings', 'one dollar wednesdays',
                  'name that tune', 'short court three boxes', 'short court two boxes', 'four corners'}


def match_teams(game):
    name = (game.get('game_name') or '').strip().casefold()
    category = (game.get('game_type') or '').strip().casefold()
    volleyball = category == 'volleyball' and name not in ROTATING_GAMES
    if not volleyball and name not in HEAD_TO_HEAD_GAMES:
        return None
    sides = []
    for side in ('winner', 'loser'):
        names = [game.get(f'{side}{i}') for i in range(1, 16)]
        names = [n.strip() for n in names if isinstance(n, str) and n.strip()]
        if not names or any('?' in n or n.casefold() in {'unknown', 'none', 'n/a'} for n in names):
            return None
        sides.append(names)
    winners, losers = sides
    if len(set(winners + losers)) != len(winners + losers):
        return None
    # Only formats whose team membership is unambiguous from this schema.
    if len(winners) != len(losers):
        return None
    if not volleyball and len(winners) > 1 and not (name in {'sequence', 'euchre'} and len(winners) == 2):
        return None
    return winners, losers


def rate_matches(matches):
    ratings = defaultdict(lambda: (25.0, 25.0 / 3))
    counts, opponents = defaultdict(int), defaultdict(set)
    for winners, losers in matches:
        players = winners + losers
        prior = {p: (ratings[p][0], ratings[p][1] ** 2 + (25 / 300) ** 2) for p in players}
        c = math.sqrt(sum(v for _, v in prior.values()) + len(players) * (25 / 6) ** 2)
        t = (sum(prior[p][0] for p in winners) - sum(prior[p][0] for p in losers)) / c
        # erfc avoids cancellation for upsets; asymptotic inverse Mills ratio
        # keeps extreme negative tails finite.
        if t < -10:
            x = -t
            v = x + 1 / x - 2 / x**3 + 10 / x**5 - 74 / x**7
        else:
            v = math.exp(-t * t / 2) / math.sqrt(2 * math.pi) / (0.5 * math.erfc(-t / math.sqrt(2)))
        w = min(1.0, max(0.0, v * (v + t)))
        for side, rivals, sign in ((winners, losers, 1), (losers, winners, -1)):
            for p in side:
                mu, variance = prior[p]
                ratings[p] = (mu + sign * variance / c * v,
                              math.sqrt(max(1e-12, variance * (1 - variance / c**2 * w))))
                counts[p] += 1
                opponents[p].update(rivals)
    return {p: {'rating': round(mu - 3 * sigma, 2), 'mu': mu, 'sigma': sigma,
                'rated_games': counts[p], 'opponents': len(opponents[p]),
                'provisional': counts[p] < 10 or len(opponents[p]) < 3 or sigma > 6}
            for p, (mu, sigma) in ratings.items()}


def summarize_games(games):
    matches = []
    for game in sorted(games, key=lambda g: (g.get('game_date') or '', g['id'])):
        teams = match_teams(game)
        if teams:
            matches.append(teams)
    ratings = rate_matches(matches)
    return {'ratings': ratings, 'rating_enabled': bool(ratings),
            'rated_games': len(matches), 'unrated_games': len(games) - len(matches),
            'rating_sort': any(not r['provisional'] for r in ratings.values())}


def attach_other_ratings(card, year):
    from other_functions import set_cur
    cur = set_cur()
    try:
        sql = 'SELECT * FROM other_games WHERE game_name=?'
        args = [card['game_name']]
        if year != 'All years':
            sql += " AND strftime('%Y',game_date)=?"
            args.append(str(year))
        rows = cur.execute(sql, args).fetchall()
        card.update(summarize_games([dict(row) for row in rows]))
    finally:
        cur.connection.close()
    if card['rating_sort']:
        for key in ('stats', 'rare_stats'):
            card[key] = sorted(card.get(key, []), key=lambda row: (
                -card['ratings'].get(row[0], {}).get('rating', -math.inf), row[0]))
    return card


def vollis_ratings(year):
    from vollis_functions import set_cur
    cur = set_cur()
    try:
        sql = 'SELECT id, game_date, winner, loser FROM vollis_games'
        args = []
        if year != 'All years':
            sql += " WHERE strftime('%Y',game_date)=?"
            args.append(str(year))
        rows = cur.execute(sql, args).fetchall()
    finally:
        cur.connection.close()
    games = [dict(id=r[0], game_date=r[1], winner1=r[2], loser1=r[3],
                  game_name='Vollis', game_type='Volleyball') for r in rows]
    return summarize_games(games)
