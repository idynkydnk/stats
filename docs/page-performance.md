# Page performance — October 9, 2026

Measured before and after the readability/performance changes using the Flask
test client and a temporary SQLite backup of the local data (9,945 doubles,
501 Vollis, 739 other games). The original database was not changed. Website
requests used a Kyle session and followed the normal shared-view redirect.
Each route was requested three times, clearing the stats caches before its first
request. These are local response-generation times, including HTML/JSON creation;
they do not measure hosting, network transfer, image downloads, or device rendering.
Timings are illustrative samples, not production latency guarantees.

Baseline website revision: `251c632`. All comparison responses returned HTTP 200.
The player sample has 7,816 games; the new app requests its first 30, while the old
app downloaded the whole history. Both use the full history for aggregates.

| Request | Before first request | After first request | Before repeat average | After repeat average |
| --- | ---: | ---: | ---: | ---: |
| Website: 2026 standings | 1355 ms | 717 ms | 1001 ms | 227 ms |
| Website: all-years standings | 3160 ms | 476 ms | 965 ms | 248 ms |
| Website: large doubles player | 2707 ms | 502 ms | 2501 ms | 312 ms |
| Website: all-years games | 1092 ms | 285 ms | 1006 ms | 263 ms |
| Website: Vollis standings | 1113 ms | 413 ms | 1101 ms | 377 ms |
| Website: Other standings | 1982 ms | 480 ms | 1951 ms | 450 ms |
| Website: Volleyball standings | 1734 ms | 502 ms | 1698 ms | 463 ms |
| App API: doubles standings | 279 ms | 300 ms | 32 ms | 129 ms |
| App API: large doubles player (first 30 games) | 1836 ms | 393 ms | 1752 ms | 470 ms |
| App API: Vollis standings | 235 ms | 217 ms | 30 ms | 35 ms |
| App API: Other standings | 1095 ms | 327 ms | 27 ms | 34 ms |
| App API: Volleyball standings | 791 ms | 256 ms | 29 ms | 36 ms |

The largest player page fell from 11,734,698 to 658,940 bytes of HTML (94.4%
smaller). Its app response fell from 2,520,240 to 142,819 bytes (94.3% smaller).
Older app versions still receive the complete history for compatibility.

## Changes and correctness boundaries

- Doubles standings count games without formatting an unused history or computing
  unused summary tiles.
- Website and new app player histories format/render only the requested page;
  totals, ratings, partners, opponents, streaks, and recent form remain complete.
- Other-game pages reuse one scoped history read and one formatting pass per
  request. Rating cards share that read while rating each game type separately.
- Navigation reads raw game names/categories and batches game-year lookups,
  avoiding per-link database connections and unnecessary date formatting.
- The app stores player pages in a bounded, separate cache. Keys include account,
  data selection revision, game type, year, division, and player. Game/profile/photo
  mutations mark it stale; sign-in/out and data selection changes clear it.
  Pull to refresh forces a fetch; saved results remain readable during refresh.

Regression checks cover complete totals across page boundaries, newest-first
ordering, invalid/out-of-range parameters, preserved share/location/division
filters, older-client responses, request-local reuse, changed results, and closed
read connections. Swift checks cover payload/cursor persistence, cache expiry,
account/year/division/source isolation, mutation invalidation, and legacy payloads.

## Validation limits

An unsigned iPhone device build passed. No cloud browser or simulator was
available, so visual inspection, large-text device rendering, and real hosted
first-paint measurements remain unverified. The full Python suite has one existing
failure in `test_location_is_in_default_and_custom_image_prompts`; it also fails
unchanged at `251c632`, because it expects the old “LOCATION CONTEXT” prompt wording.


## Live cloud-browser follow-up

The October 9 mobile regression came from a 480px minimum table width. It has
been removed. Rankings reserve room for every numeric column; below 360px,
names occupy their own row. No metric is hidden or clipped. The iPhone table
also avoids horizontal scrolling and falls back to labeled, wrapping stats
when a screen or larger text cannot fit the regular row.

[Cloud browser run](https://github.com/idynkydnk/stats/actions/runs/38020663272)
checked seven public live page types at 320, 375, 390, 430, 768, and 1440 pixels
in Chromium and WebKit (84 page visits). This pre-deployment run applied the
candidate stylesheet over the live responses. All returned 200, with no page
or standings overflow and no clipped numeric cells. Today's sorting was checked
for all five metrics, and its light appearance was checked too. Screenshots
revealed one further small-screen rank stacking issue, corrected before release.

Sample median full-load times in Chromium: current standings 760ms, all-years
standings 1478ms, all-years player 935ms, games 620ms, Vollis 522ms, Other 672ms,
and Volleyball 670ms. WebKit medians were 738–1372ms. These are unthrottled
cloud-runner measurements, not cellular-device guarantees. The check is available
as the manual “Check live mobile and desktop layout” workflow; leave candidate
preview off to verify the actual deployment. Screenshots/reports last seven days.

The iPhone correction passed an unsigned device build. Follow-up native
[cloud simulator checks](https://github.com/idynkydnk/ios_stats/actions/runs/38021837786)
passed 18 scenarios (180 metric checks): 320/375/390-point widths, default through
the largest accessibility text size, long names, and large records. Screenshots
confirmed complete values without horizontal scrolling; the largest text wraps
vertically. These use the production standings component with controlled test
data, rather than a signed-in live-data session or a physical TestFlight device.
