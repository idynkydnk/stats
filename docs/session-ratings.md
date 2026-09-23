# Doubles daily ratings

Today's Stats, date-specific doubles stats, and doubles recap crowns use a
score-aware daily performance rating. Season/all-time skill ratings are separate.
Daily ratings do not estimate opponent strength or carry over earlier days.

For each player and game:

- Result is 1 for a win or 0 for a loss.
- Point share is their team's points divided by both teams' combined points.
- Game performance is 80% result plus 20% point share.

The published rating is `100 * (sum(game performance) + 1) / (games played + 2)`.
This is a 0–100 scale with two neutral games (performance 0.5 each) as a
small-sample adjustment. It reduces the advantage of a brief unbeaten appearance
without imposing a minimum game count. It does not guarantee a full-session
player always outranks a short appearance.

Winning matters most; larger winning margins and closer losses improve ratings.
With equal records and game counts, average point share breaks the tie. Each game
has equal weight regardless of target score. Unscored or invalid scores contribute
a neutral 0.5 point share while retaining the recorded win/loss. Question-mark
players are excluded from ratings, as before.

All games are aggregated together. Reordering games, changing their timestamps,
or adding games involving entirely different players cannot change a player's
rating. Published ratings are rounded to two decimals; equal published ratings
share the recap crown.

Regression examples:

- September 23, 2026: Chow, Goshow and Ben each went 4–2 in the six-game
  rotation. Point differentials were +18, +14 and −4. They rank in that order,
  including when the order of play is reversed.
- September 20, 2026: Chow's 7–1 full session outranks Sam's 1–0 late appearance.
