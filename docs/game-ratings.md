# Ratings for individual games

Doubles keeps its existing rating system. Other games and Vollis use separate
TrueSkill histories within the selected season and location. Categories such as
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

We do not infer team membership or finishing order from a list of individual
losers. Unordered multiplayer rounds, rotating Kings/Queens and box drills,
unknown game formats, Uno, Ono 99, and incomplete/duplicate player rosters are
excluded from ratings. The original win/loss stats still include those records.
New formats should be reviewed before expanding the allowlist.

A rating is provisional until the player has at least 10 rated matches, 3 distinct
opponents, and sigma <= 6. These are display policy thresholds, not a claim of
statistical certainty. P marks provisional ratings; no eligible matches means
no rating. Tables retain win-percentage ordering until at least one player meets
these thresholds, then default to conservative rating order. The rating column
can also be sorted manually. Coverage counts disclose excluded results.
