"""Pure doubles skill replay, shared by standings and offline comparisons."""

def score_margin_multiplier(winner_score, loser_score, performance_difference):
    """Bounded score adjustment; expectation calibrated on pre-2025 doubles.

    Use the margin as a fraction of total points so target scores do not change
    its weight. Invalid/unscored games retain the result-only update.
    """
    import math
    try:
        winner_score, loser_score = float(winner_score), float(loser_score)
    except (TypeError, ValueError, OverflowError):
        return 1.0
    if not (math.isfinite(winner_score) and math.isfinite(loser_score)
            and winner_score > loser_score >= 0):
        return 1.0
    # The ratio form also avoids overflowing the sum of very large scores.
    ratio = loser_score / winner_score
    margin = (1 - ratio) / (1 + ratio)
    expected_margin = min(1.0, max(0.0, 0.153 + 0.028 * performance_difference))
    return 1.0 + max(-0.20, min(0.20, margin - expected_margin))


def calculate_ratings(games, rating_observer=None, *,
                      score_aware=True, prediction_observer=None):
    """Replay doubles chronologically, with an optional result-only comparison.

    The prediction observer receives (game index, winning team's probability)
    before that game's result or score is applied, for walk-forward evaluation.
    """
    import math
    from collections import defaultdict

    # TrueSkill default parameters
    INITIAL_MU = 25.0  # Mean skill
    INITIAL_SIGMA = 8.333  # Skill uncertainty
    BETA = 4.167  # Variance in performance
    TAU = 0.0833  # Dynamics factor (skill change)

    player_ratings = defaultdict(lambda: {
        'mu': INITIAL_MU,
        'sigma': INITIAL_SIGMA
    })

    # Process games chronologically
    for game_index, game in enumerate(games):
        # Get teams
        winners = [game[2], game[3]]  # winner1, winner2
        losers = [game[5], game[6]]   # loser1, loser2

        # Filter out players with question marks
        winners = [w for w in winners if '?' not in w]
        losers = [l for l in losers if '?' not in l]

        if not winners or not losers:
            continue

        # Calculate team ratings
        winner_team_mu = sum(player_ratings[w]['mu'] for w in winners)
        winner_team_sigma = math.sqrt(sum(player_ratings[w]['sigma']**2 for w in winners))

        loser_team_mu = sum(player_ratings[l]['mu'] for l in losers)
        loser_team_sigma = math.sqrt(sum(player_ratings[l]['sigma']**2 for l in losers))

        # Total uncertainty
        c = math.sqrt(winner_team_sigma**2 + loser_team_sigma**2 + 2 * BETA**2)

        # Team performance difference
        winner_team_performance = (winner_team_mu - loser_team_mu) / c
        loser_team_performance = (loser_team_mu - winner_team_mu) / c
        if prediction_observer is not None:
            prediction_observer(game_index, 0.5 * (1 + math.erf(winner_team_performance / math.sqrt(2))))
        score_multiplier = 1.0
        if score_aware and len(winners) == len(losers) == 2 and len(set(winners + losers)) == 4:
            score_multiplier = score_margin_multiplier(game[4], game[7], winner_team_performance)

        # Calculate v and w functions (simplified TrueSkill)
        winner_v = v_win(winner_team_performance)
        loser_v = v_lose(loser_team_performance)

        winner_w = w_win(winner_team_performance)
        loser_w = w_lose(loser_team_performance)

        # Update winner ratings
        for winner in winners:
            old_mu = player_ratings[winner]['mu']
            old_sigma = player_ratings[winner]['sigma']

            mu_multiplier = (old_sigma**2 + TAU**2) / c
            sigma_multiplier = (old_sigma**2 + TAU**2) / (c**2)

            player_ratings[winner]['mu'] = old_mu + mu_multiplier * winner_v * score_multiplier
            player_ratings[winner]['sigma'] = math.sqrt((old_sigma**2 + TAU**2) * (1 - sigma_multiplier * winner_w))

        # Update loser ratings
        for loser in losers:
            old_mu = player_ratings[loser]['mu']
            old_sigma = player_ratings[loser]['sigma']

            mu_multiplier = (old_sigma**2 + TAU**2) / c
            sigma_multiplier = (old_sigma**2 + TAU**2) / (c**2)

            player_ratings[loser]['mu'] = old_mu + mu_multiplier * loser_v * score_multiplier
            player_ratings[loser]['sigma'] = math.sqrt((old_sigma**2 + TAU**2) * (1 - sigma_multiplier * loser_w))
        if rating_observer is not None:
            for player in winners + losers:
                value = player_ratings[player]
                rating_observer(game_index, player, round(value['mu'] - 3 * value['sigma'], 2))

    # Count games per player and wins/losses
    player_game_counts = defaultdict(int)
    player_wins = defaultdict(int)
    player_losses = defaultdict(int)
    for game in games:
        winners = [game[2], game[3]]
        losers = [game[5], game[6]]

        winners = [w for w in winners if '?' not in w]
        losers = [l for l in losers if '?' not in l]

        for player in winners:
            player_game_counts[player] += 1
            player_wins[player] += 1
        for player in losers:
            player_game_counts[player] += 1
            player_losses[player] += 1

    # Convert to list and sort by conservative rating (mu - 3*sigma)
    all_rankings = []
    for player, rating_data in player_ratings.items():
        conservative_rating = rating_data['mu'] - 3 * rating_data['sigma']
        all_rankings.append({
            'player': player,
            'mu': round(rating_data['mu'], 2),
            'sigma': round(rating_data['sigma'], 2),
            'rating': round(conservative_rating, 2),
            'games_played': player_game_counts[player],
            'wins': player_wins[player],
            'losses': player_losses[player]
        })

    # Sort by conservative rating (highest first)
    all_rankings.sort(key=lambda x: x['rating'], reverse=True)

    return all_rankings

def v_win(t):
    """TrueSkill v function for winners"""
    import math
    from math import sqrt, pi, exp, erf

    # Standard normal PDF and CDF
    def phi(x):
        return (1.0 / sqrt(2 * pi)) * exp(-0.5 * x**2)

    def Phi(x):
        return 0.5 * (1 + erf(x / sqrt(2)))

    return phi(t) / Phi(t)

def v_lose(t):
    """TrueSkill v function for losers"""
    import math
    from math import sqrt, pi, exp, erf

    def phi(x):
        return (1.0 / sqrt(2 * pi)) * exp(-0.5 * x**2)

    def Phi(x):
        return 0.5 * (1 + erf(x / sqrt(2)))

    return -phi(t) / Phi(-t)

def w_win(t):
    """TrueSkill w function for winners"""
    v = v_win(t)
    return v * (v + t)

def w_lose(t):
    """TrueSkill w function for losers"""
    v = v_lose(t)
    return v * (v + t)
