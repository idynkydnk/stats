# Doubles skill ratings

Year, custom-season and all-time doubles standings use the existing result-based
skill calculation with a small score-margin adjustment. Website standings,
player profiles and the iPhone API share this engine. Daily ratings retain their
separate 80% result / 20% point-share calculation.

For each game, first compute the existing pre-game team skill difference divided
by its combined uncertainty (`t`). For a valid score, compute:

```
margin = (winner points - loser points) / (winner points + loser points)
expected winning margin = clamp(0.153 + 0.028 * t, 0, 1)
multiplier = 1 + clamp(margin - expected winning margin, -0.20, 0.20)
```

Multiply both sides' existing mean-skill changes by this multiplier. Winners
still gain estimated skill and losers still lose it; the adjustment is bounded
to 80–120% of that game's original change given the same prior ratings. The
uncertainty update remains result-based: points are not counted as extra games.
The displayed rating remains `mu - 3 * sigma`, rounded to two decimals. Its total
change is not itself capped at 20%, since uncertainty also affects that number.

The expectation is conditional on the recorded winning side winning, not an
unconditional signed score prediction. A favorite is expected to win more
comfortably, so the same score earns a smaller multiplier for a favorite than an
underdog. Both partner and opponent skill enter the pre-game team comparison.
Normalized margins give equivalent scores the same weight across target scores.

Missing, nonnumeric, nonfinite, tied, reversed or negative scores use the normal
result-only update. Incomplete or duplicate rosters also receive no score
adjustment; their existing result handling is preserved. Each game is replayed
once, in timestamp then ID order. Qualification and daily ratings are unchanged.
The adjustment is a heuristic extension of the existing implementation, not an
exact score-based TrueSkill posterior.

## Calibration and comparison

The expectation coefficients were fitted to 5,718 valid scored games with four
distinct known players from the public men's doubles history for 2011–2024,
downloaded October 26, 2026. Each calendar year starts from the existing priors;
the result-only model predicts each game before updating from it. Least squares
gave intercept 0.152541 and slope 0.027776, rounded to three decimals. The 20%
cap is a conservative design choice, not a fitted optimum. These coefficients
are shared across doubles divisions; predictive benefit has only been evaluated
on the public men's history, not women's or private leagues.

The fixed formula was then evaluated on 2025 and 2026, with each game predicted
using only earlier games in that year. Both Brier score and log loss improved
slightly in 2025 and 2026; winner-pick accuracy declined in 2025 and rose in 2026.
This is limited retrospective evidence, not proof of better future rankings.
The comparison script also reports uncertainty using a paired bootstrap grouped
by playing day, so games from the same session are not treated as independent.

Reproduce from saved public API responses (the script makes no network requests
and does not write to the game database):

```
venv/bin/python scripts/compare_doubles_ratings.py \
  --history output/score-aware-ratings-2026/history.json \
  --standings output/score-aware-ratings-2026/standings.json \
  --year 2026 --output output/score-aware-ratings-2026/comparison.json
```

The comparison requires result-only replay to match every published qualifying
player's rating and record before reporting changes. It applies the site's
minimum-games rule and reports the new top 20 plus any players leaving it.

Legacy persisted result-only rankings are not reused. The existing authorized,
revision-scoped calculation and response caches serve the new ratings; their
deployment namespaces change when the calculation code changes.
