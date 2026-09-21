# Ratings for individual games

Doubles keeps its existing rating system. Other games and Vollis use separate
TrueSkill-based histories within the selected season and location. Categories such as
Volleyball, Card games and Board games never combine ratings across game names.

The new engine uses the closed-form two-team, decisive-result TrueSkill update:
mu 25, sigma 25/3, beta 25/6, tau 25/300, and no draw margin. Every participant's
performance variance is included. Published rating is mu minus three sigma.
Results replay by original timestamp then game ID; no ratings are written to the
database or cached across requests, so edits and deletions take effect immediately.
The implementation was compared against trueskill 0.4.5 with draw_probability=0
for 200 matches each of 1v1, 2v2 and 3v3; maximum discrepancy was below 0.000001.
Reference: https://trueskill.readthedocs.io/en/latest/

Supported results:
- Fixed, equal-size volleyball sides, including No Jump, Coed, and Mixed doubles.
- Vollis head-to-head results.
- Head-to-head Backgammon, Scrabble, Sequence, Euchre, Gin Rummy, Otrio, Spot it!,
  Sushi go!, Catan, Tic-tac-toe and Ping pong. Sequence and Euchre also allow 2v2.

- Single-winner multiplayer Gin Rummy, Scrabble, Sequence, Catan, Spot it!,
  Sushi go! and Otrio.

For those individual multiplayer formats, compare the winner with each loser
using the same pre-game priors. Average the mean and variance changes over the
number of losers (including zero changes for nonparticipants in each comparison),
then apply the result once per player. This is a bounded pairwise approximation,
not an exact multiplayer TrueSkill posterior. An equal-strength winner receives
the same update regardless of field size; each loss receives a fraction of the
one-on-one adjustment. Dynamics variance is added once per round. Rated-game
counts increase once per participant; opponent counts include only actual
winner-loser comparisons. No comparison is made between losers, and they are
not treated as tied or as a team. Loser-list order cannot affect the result.

We do not infer team membership or finishing order from a list of individual
losers. Multiple-winner individual rounds, rotating Kings/Queens and box drills,
unknown game formats, Uno, Ono 99, and incomplete/duplicate player rosters are
excluded from ratings. The original win/loss stats still include those records.
New formats should be reviewed before expanding the allowlist.

A rating is provisional until the player has at least 10 rated matches, 3 distinct
opponents, and sigma <= 6. These are display policy thresholds, not a claim of
statistical certainty. Provisional status is used internally for default sorting
and is not displayed beside ratings; no eligible matches means no rating. Tables retain win-percentage ordering until at least one player meets
these thresholds, then default to conservative rating order. The rating column
can also be sorted manually. Coverage counts disclose excluded results.
