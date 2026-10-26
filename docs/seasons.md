# Seasons

Browse → Seasons is available to everyone on the website and in the native app.
Signed-in users can choose Create season from that page. The account owns the
name, inclusive start/end dates, minimum-games
setting, and share permission in the website's `seasons` table. The app uses the
same records through `/api/seasons`; saving on either platform updates both.

## Data and qualification

Only records attributed to the creator by `entered_by` are included. This rule
also applies to admins. Personal accounts use their own database; legacy accounts
use their attributed records in the shared database. Unattributed legacy records
are excluded. Selected stats sources, global date/location filters, and shared
stats-view parameters cannot broaden a season. Stored local game days determine
inclusion, matching the site's custom date filter.

Doubles divisions and other game formats have separate standings and ratings.
Vollis records in the legacy singles table and the Other table share one Vollis
group. Other formats remain separate. The default minimum reuses
`minimum_games_threshold`: `max(1, game_count // 30)` per standings group. A fixed
positive integer applies to each group instead. All players remain visible, with
below-minimum players showing the number of games still needed.

## Ratings and awards

Doubles reuses the site's season TrueSkill implementation. Other games use the
existing per-format rating engine and its eligibility rules. Invalid/incomplete
doubles rosters are excluded from ratings; win/loss records remain visible.
Ratings replay from neutral priors using only the creator's in-season games.

The highest published rating among qualified players earns the championship;
formats without ratings use win percentage. Equal values share the award.
Most improved uses final rating minus the rating after the player's first rated
playing day in that season. It requires a positive gain, at least two rated
playing days, and the same game minimum. The observer hooks in the existing
rating engines capture this baseline without changing the calculations.

The season's saved time zone determines whether its end day has passed. Active
seasons show leaders; completed seasons populate the account's champions board.
The board retains season names, dates, game formats, champions, win percentages,
and ratings. Results are recalculated after game corrections or season edits.
Deleting a season removes its board entry and link without deleting any games.

## Access and sharing

The directory and read-only season APIs are available without signing in. They
show seasons whose owners enabled sharing, plus the signed-in user's own private
seasons. The champions board follows the same visibility rules. Read responses
include `can_manage` so the app only shows editing and sharing controls to the
owner. Private seasons cannot be read by another account, including an admin.
Owner mutations require the existing validated account identity.
Session-based writes require a season CSRF token; Bearer writes use the app's
validated token. The owner can explicitly share a season, adding it to the public
directory and creating a random read-only link. Stopping sharing removes it from
the directory and public APIs and revokes the link. Re-enabling sharing creates
a different link. A shared page
includes that season's standings, awards, and scoped player game histories. It
never publishes another season, profile contact fields, or editing controls.
Shared pages are excluded from search indexing and set no-store/no-referrer.
Blocked or suspended authors are hidden. Account deletion removes seasons and
revokes their links along with the account's other data.

## Checks

Run `venv/bin/python -m unittest tests.test_seasons tests.test_game_ratings
 tests.test_private_accounts tests.test_account_lifecycle` (on one line).
`tests/SeasonTests.swift` in the app repository checks its date handling,
minimum-game validation, and decoding of real season API fixtures. Build the
native app with Xcode; browser/simulator interaction requires a cloud computer.

## Navigation and form behavior

A game selector shows one format at a time. Website selection changes immediately
and stays in the URL, shared links, browser history, and edit/cancel navigation.
The app retains content and the selected game while refreshing after navigation;
request tickets prevent older reads from overwriting a newer refresh or mutation.
Account changes immediately hide the previous account's content.

Sharing is an expandable control, and explanations are available on demand.
Forms retain a custom minimum when switching modes, bound the end date to the
start date, and prevent duplicate submissions. The app provides a Done control
for its numeric keyboard. New seasons open immediately after saving. Long
standings, game histories, season lists, and champions lists use the existing
25-row preview pattern; the remaining entries are available through Show all.

The website DOM checks render real templates using synthetic temporary accounts.
They cover dates, validation, mode changes, duplicate submissions, back navigation,
game selection, keyboard dismissal, clipboard fallback, and long lists. Run:

```sh
npm install --prefix /tmp/stats-season-dom --ignore-scripts --no-audit --no-fund --no-save linkedom@0.18.12
NODE_PATH=/tmp/stats-season-dom/node_modules node tests/test_season_controls.js
```

These checks run without a browser and do not verify rendered layout. Visual
browser and simulator checks still require a cloud computer.
