"""Read-only replay of saved public games, comparing result-only and scored ratings."""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import random
from statistics import NormalDist
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from doubles_skill import calculate_ratings


def game_tuple(game):
    return tuple(game[key] for key in ('id', 'game_date', 'winner1', 'winner2',
                                      'winner_score', 'loser1', 'loser2', 'loser_score'))


def valid_margin(game):
    names = game[2:4] + game[5:7]
    if len(set(names)) != 4 or any(not name or '?' in name for name in names):
        return None
    try:
        winner, loser = float(game[4]), float(game[7])
    except (TypeError, ValueError, OverflowError):
        return None
    if not (math.isfinite(winner) and math.isfinite(loser) and winner > loser >= 0):
        return None
    ratio = loser / winner
    return (1 - ratio) / (1 + ratio)


def replay(games, score_aware):
    predictions = {}
    rankings = calculate_ratings(
        games, score_aware=score_aware,
        prediction_observer=lambda index, probability: predictions.update({index: probability}))
    return rankings, predictions


def metrics(predictions):
    probabilities = list(predictions.values())
    if not probabilities:
        return dict(games=0, brier=None, log_loss=None, accuracy=None)
    count = len(probabilities)
    return dict(games=count,
                brier=sum((1 - p) ** 2 for p in probabilities) / count,
                log_loss=sum(-math.log(max(1e-15, p)) for p in probabilities) / count,
                accuracy=sum(1 if p > .5 else .5 if p == .5 else 0 for p in probabilities) / count)


def brier_interval(games, baseline, candidate):
    """Paired day-block bootstrap; negative difference favors score-aware ratings."""
    days = defaultdict(list)
    if baseline.keys() != candidate.keys():
        raise ValueError('Models did not predict the same games')
    for index, old in baseline.items():
        days[games[index][1][:10]].append((1 - candidate[index]) ** 2 - (1 - old) ** 2)
    blocks = [(sum(values), len(values)) for values in days.values()]
    if not blocks:
        return None
    rng = random.Random(2026)
    samples = []
    for _ in range(2000):
        sample = rng.choices(blocks, k=len(blocks))
        samples.append(sum(total for total, _ in sample) / sum(count for _, count in sample))
    samples.sort()
    return dict(playing_days=len(blocks), resamples=len(samples),
                lower=samples[49], upper=samples[1949])


def calibrate(by_year):
    points = []
    for year, games in sorted(by_year.items()):
        if year >= '2025':
            continue
        _, predictions = replay(games, False)
        for index, probability in predictions.items():
            margin = valid_margin(games[index])
            if margin is not None and 0 < probability < 1:
                points.append((NormalDist().inv_cdf(probability), margin))
    if len(points) < 2:
        return None
    mean_x = sum(x for x, _ in points) / len(points)
    mean_y = sum(y for _, y in points) / len(points)
    variance = sum((x - mean_x) ** 2 for x, _ in points)
    if not variance:
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in points) / variance
    return dict(games=len(points), through_year=2024,
                intercept=mean_y - slope * mean_x, slope=slope)


def standings(games, rankings, minimum):
    # Match the website's newest-first name order for ties, its record counting,
    # minimum-games rule and placement of winless players.
    records = {}
    for game in reversed(games):
        winners = list(dict.fromkeys(game[2:4]))
        losers = [p for p in dict.fromkeys(game[5:7]) if p not in winners]
        for names, won in ((winners, True), (losers, False)):
            for player in names:
                if '?' in player:
                    continue
                row = records.setdefault(player, dict(player=player, wins=0, losses=0))
                row['wins' if won else 'losses'] += 1
    ratings = {r['player']: r['rating'] for r in rankings}
    rows = [dict(row, rating=ratings.get(player, 0)) for player, row in records.items()
            if row['wins'] + row['losses'] >= minimum]
    return sorted(rows, key=lambda row: (row['wins'] == 0, -row['rating']))


def compare(history, year, published=None):
    by_year = defaultdict(list)
    seen = set()
    for game in sorted(history['games'], key=lambda g: (g['game_date'], g['id'])):
        if game.get('division', 'open') != 'open':
            raise ValueError("Supply only the public men's doubles history (division=open)")
        if game['id'] in seen:
            raise ValueError('Duplicate game ID in history')
        seen.add(game['id'])
        by_year[game['game_date'][:4]].append(game_tuple(game))
    games = by_year[year]
    if not games:
        raise ValueError('No games in requested year')
    old, old_predictions = replay(games, False)
    new, new_predictions = replay(games, True)
    minimum = max(1, len(games) // 30)
    old_rows, new_rows = standings(games, old, minimum), standings(games, new, minimum)
    if published is not None:
        if str(published['display_year']) != year or published['minimum_games'] != minimum:
            raise ValueError('Published standings have a different year or qualification minimum')
        actual = {r['name']: (r['rating'], r['wins'], r['losses']) for r in published['stats']}
        expected = {r['player']: (r['rating'], r['wins'], r['losses']) for r in old_rows}
        if actual != expected:
            raise ValueError('Result-only replay does not match published standings; refresh both snapshots')
        # Preserve the published order if rounded ratings tie.
        positions = {r['name']: i for i, r in enumerate(published['stats'])}
        old_rows.sort(key=lambda row: positions[row['player']])
    old_map = {r['player']: dict(r, rank=i) for i, r in enumerate(old_rows, 1)}
    changes = []
    for rank, row in enumerate(new_rows, 1):
        before = old_map[row['player']]
        changes.append(dict(player=row['player'], old_rank=before['rank'], new_rank=rank,
                            rank_change=before['rank'] - rank, old_rating=before['rating'],
                            new_rating=row['rating'], rating_change=round(row['rating'] - before['rating'], 2),
                            wins=row['wins'], losses=row['losses']))
    validation = {}
    for test_year in sorted({'2025', year}):
        if not by_year.get(test_year):
            continue
        test_games = by_year[test_year]
        if test_year == year:
            baseline, candidate = old_predictions, new_predictions
        else:
            _, baseline = replay(test_games, False)
            _, candidate = replay(test_games, True)
        validation[test_year] = dict(baseline=metrics(baseline), score_aware=metrics(candidate),
                                    brier_difference_95_percent=brier_interval(test_games, baseline, candidate))
    return dict(year=year, through=games[-1][1], games=len(games), minimum_games=minimum,
                scored_games=sum(valid_margin(g) is not None for g in games),
                published_baseline_verified=published is not None,
                calibration=calibrate(by_year), validation=validation, top20=changes[:20],
                leaving_top20=[r for r in changes[20:] if r['old_rank'] <= 20], all_qualified=changes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--history', type=Path, required=True)
    parser.add_argument('--standings', type=Path)
    parser.add_argument('--year', default='2026')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    history = args.history.read_bytes()
    published = json.loads(args.standings.read_text()) if args.standings else None
    report = compare(json.loads(history), args.year, published)
    report['history_sha256'] = hashlib.sha256(history).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
