# Page performance — October 9, 2026

## October 19 follow-up: cold and signed-in requests

The signed-in diagnostic uses a 15-minute token for the existing Kyle account,
issued by a temporary cloud task through the hosting API. No password or Flask
signing key leaves the server. Reports contain timings and code locations only;
browser state and signed-in screenshots are not saved. The task revokes its
token when the handshake file is removed, with a hard timeout as a fallback.
Authenticated profiler signatures bind the exact credentials as well as the
request path/query. Existing authorization still runs normally. The workflow
tests stats, player history, Add Game, Players, source settings and the dashboard.
First browser visits explicitly bypass completed-page reuse, separating cold
rendering from repeat measurements. All form submissions and optional writes
are blocked in the browser test.

The signed-in baseline found 2.04–2.57 seconds of application work for forced
standings/player/game renders, and 1.82–1.91 seconds on repeat Players requests.
The largest cause was a cross-filesystem rename: temporary combined databases
were built under `/tmp`, but the reusable cache lived on the home mount. Failed
publication rebuilt the entire combined database a second time. Publication now
copies into a staging file on the cache mount before atomic rename, reuses the
already-built result on publication failure, and batches inserts. Tests simulate
the production cross-device failure and verify reuse and edit invalidation.

Cold-path changes remove date formatting from standings counts, compile template
code before accepting traffic, and reuse the route/filter part of standings
links. Long standings send the first 20 rows per table as HTML and the rest as
compact data, materialized before sorting/search. Every record and Python's
display rounding are retained; a `full=1` link supports browsers without scripts.
Player matchup records are serialized in one operation rather than thousands of
individual template calls. Entry rosters reuse source-revision-scoped results
after checking current source permissions. Navigation locations are read only
when rendered. Dashboard account activity is aggregated once, recap-directory
setup runs once per request, and preview cards use lazy thumbnails.
Account activity timestamps no longer discard otherwise valid stats pages;
identity, permissions, source revisions and other session fields remain checked.

Shared styles, icon fonts and scripts now arrive inside the compressed page,
eliminating their first-visit network chains. This deliberately trades some
additional bytes on repeat HTML responses for fewer cold-visit round trips.
Original versioned assets remain available. The signed-in player editor waits
until opened before fetching original photos, AI images and version history.
The Players list uses lazy, bounded previews; original images remain available
for editing. Only previews of already-public static images bypass account work.

The first follow-up deployed as `588db57`. Its signed-in forced renders fell to
461 ms for standings, 574 ms for all years, 932 ms for the player page and 635 ms
for games. Players required 376–664 ms instead of 1,823–1,908 ms. Both cloud
browser engines passed, including complete standings and on-demand photo editing;
the temporary diagnostic token was revoked and the schedule removed. These
results still fell short of near-instant first visits, so profiling continued.

The next trace showed 20–30 repeated source-revision reads per stats request,
cache permissions/schema setup on every lookup, and about 80–100 ms copying each
combined snapshot from shared home storage. Disposable caches now default to a
secret-namespaced, mode-700 directory in local temporary storage (override with
`STATS_RESPONSE_CACHE_DIR`). Original databases remain in their existing durable
storage. Cache loss only causes regeneration. Each request reads global and sport
revisions together, then checks fresh revisions before publishing; edits during
rendering still prevent cache publication. Cache setup runs once per file inode.
Entry-page calculations use the owned database revision, with current receipts
and forms rendered each time. Calculation keys also retain display timezone.
Player profiles serialize together, and dashboard lists no longer query every
deleted recap job individually. Dashboard totals scan each game table once.

### Verified production results

The [final signed-in run](https://github.com/idynkydnk/stats/actions/runs/39314077425)
passed Chrome and WebKit at 390px and 1440px, including complete standings,
matchup sorting, every player profile record, and opening both profile editors.
Its temporary token was revoked and its scheduled task removed. First visits
forced a new HTML render, but could reuse authorized calculations and snapshots;
they are not a benchmark of rebuilding every cache after a data change.

| Signed-in page | Baseline Chrome first load | Final Chrome first load | Final WebKit first load |
| --- | ---: | ---: | ---: |
| Current standings | 2,347–2,354 ms | 554–707 ms | 939–1,098 ms |
| All years | 2,341–2,406 ms | 545–603 ms | 545–1,084 ms |
| Player history | 2,186–2,241 ms | 647–656 ms | 755–764 ms |
| Games | 2,404–2,971 ms | 492–565 ms | 524–568 ms |
| Add Game | 723–754 ms | 227–231 ms | 350–417 ms |
| Players | 5,220–5,651 ms | 827–876 ms | 974–983 ms |
| Dashboard | 895–1,063 ms | 417–514 ms | 493–502 ms |

Final repeat-load medians for the seven stats/history pages were 146–261 ms in
Chrome and 181–259 ms in WebKit. The separate unprofiled signed-in forced renders
required 327–558 ms of server work for standings/player/games, 110 ms for Add
Game, 334 ms for Players and 361 ms for the dashboard. These are cloud machines
with mobile-sized/desktop-sized viewports, not physical phones or a promise for
every network. The runs occurred sequentially, not under controlled identical
traffic/worker scheduling.

The [public browser run](https://github.com/idynkydnk/stats/actions/runs/39314078278)
also passed both engines. The [uncached public profiles](https://github.com/idynkydnk/stats/actions/runs/39314237429)
measured 92–172 ms of application work, versus 9–16 ms on prepared pages. One
first Chrome entry took 2.56 seconds, including 1.98 seconds before the redirect
completed and 384 ms in the final page's app handler. This timing cannot by
itself distinguish initial connection setup, queuing and worker startup. A
separate new connection from the development host took 465 ms to receive that
redirect, while its app handler took only 8 ms. Deployment preparation now uses
three concurrent requests instead of one, to reach multiple workers, and also
prepares the commonly used public all-years Kyle player page.

Remaining signed-in profiles still spent about 85 ms copying a prepared database,
and substantial time in source revision/identity queries and dashboard reads.
The Players page also retains the browser cost of a complete 729-card roster.
There is no evidence that the account's daily CPU quota was exhausted. For a
consistent near-instant first-visit target, the next infrastructure improvement
should address database/storage latency and proximity, not merely add workers.
PythonAnywhere's own [performance guidance](https://help.pythonanywhere.com/pages/MySiteIsSlow)
identifies its network filesystem and SQLite as sources of latency and recommends
a server database. Keeping SQLite on durable local SSD storage on another host
is another architectural option. No host, database service or plan was changed.

Local validation: 521 Python tests pass, including edit invalidation during
rendering, request-local revision reads, local cache isolation and timezone
separation, plus JavaScript checks for deferred photo editing and complete
sorting. Follow-up cache-directory permissions and deployment warmup checks pass.

## October 19: profiles from production workers

The signed, GET-only `Profile live page performance` workflow profiles real
public requests in the live web workers. It uses the existing deployment secret
to sign a specific path/query for 60 seconds. Reports include code locations,
call counts and timings, never response contents, SQL, credentials or locals.
Requests with cookies or Authorization are excluded. Ordinary requests have no
profiler overhead beyond checking whether the diagnostic header exists.

The [baseline run](https://github.com/idynkydnk/stats/actions/runs/39302034035)
confirmed repeated template rendering and Flask URL/context work dominate the
large warm HTML pages; database reads and account/roster labeling also cost time.
Three different live workers were observed. Unprofiled server times across four
repeat requests ranged from 78–1,151 ms for current standings, 275–3,165 ms for
all-years standings and 413–692 ms for the large player page. Profiling itself
adds overhead, so comparisons use the separate unprofiled requests.

The first correction reuses completed HTML in a private, bounded server cache
shared through the existing cache database, with a compressed memory front cache.
Identity, source permissions and current data revisions are checked before every
lookup. Keys include the full session, current account information, source titles,
filters, route, host, deployment contents and data revisions. Flash messages,
active recap jobs, changing sessions, errors, streaming responses and explicit
no-store requests are excluded. Browsers still receive `Cache-Control: no-store`.
Changes during rendering prevent publication. Combined views can skip snapshot
copying on a page hit. Public-only links no longer scan personal accounts/rosters;
identity reads are reused only within the current GET; Vollis navigation years
are cached by authorized revision; deployment timestamps are read once per worker.

Local repeat medians fell to about 1.3 ms for all three benchmark pages, with
identical HTML sizes. These local timings are not hosted end-to-end measurements.
Regression tests cover account/session/filter separation, revocation, changed
games and rosters, cross-worker reuse, flash messages, session changes, errors,
mid-render edits, explicit reloads and bounded private storage.

The [first post-deployment profile](https://github.com/idynkydnk/stats/actions/runs/39303030508)
measured 8–31 ms of unprofiled server work on prepared pages across all seven
routes, with one 188 ms warmup outlier. Every signed profile hit the page cache.
This rules out a host move as a prerequisite for fast repeat server responses.

The large player page now sends the first ten partner/opponent rows as HTML and
the complete remaining records as compact, safely escaped data. Sorting and Show
all materialize the remaining rows before operating, so totals, all opponents,
all partners, sorting tiers, links and percentage rounding remain complete.
The local sample shrank from 565,228 to 113,447 bytes (80% less initial HTML).
Timezone detection no longer sends an unchanged setting on every page visit.
Common public pages are warmed after each deployment. A rebuilt small local icon
bundle includes the previously missing passkey icon and retains earlier font
versions for browsers with cached stylesheets.

The new `Check live navigation performance` workflow keeps real HTTP asset
caching enabled and tests all matchup records through sorting and expansion in
cloud Chromium and WebKit. The older layout workflow intercepts every request,
which disables Playwright's HTTP cache; its numbers should not be presented as
repeat-browser asset-cache performance. It remains useful for layout checks.

The [browser follow-up](https://github.com/idynkydnk/stats/actions/runs/39303927507)
passed 112 page loads and all sorting/expansion checks (378 partners and 521
opponents) at 390px and 1440px in Chromium and WebKit, with no JavaScript errors.
Prepared repeat-load medians were 107–142 ms for current standings, 187–308 ms
for all-years standings, 113–172 ms for the player page, and 65–126 ms for the
remaining lists. These are unthrottled cloud-browser measurements, not cellular
or physical-device guarantees. First unprepared requests after a restart were
still slower (some took 2–3 seconds), so repeat medians must not hide cold work.

The final follow-up shares authorized calculation results between workers too,
with deployment/source/filter keys, bounded storage, copied results and original
expiry times. Stored pickle bytes are authenticated with an HMAC over both key
and payload before deserialization. Changed or substituted bytes are rejected.
Default and explicit doubles divisions now share a page key, without conflating
different filters or changing the order of repeated query values. Deployment
warmup retries transient network/reload failures and still fails on persistent
errors. This addresses a one-off warmup timeout observed during the browser run.

The [next production check](https://github.com/idynkydnk/stats/actions/runs/39305262215)
passed all 112 browser loads and interactions. Repeat medians across the seven
pages were 50–273 ms, with server medians of 9–24 ms. One first unprepared player
request took 851 ms; fresh WebKit standings visits still took about 1.2 seconds,
mostly waiting for separate asset downloads rather than server page generation.
The final asset change combines five shared scripts into one request and three
stylesheets into one, with content versions computed from the actual sources at
worker startup. Font and page-script preloads start those downloads earlier.
The existing source files remain available to other templates and cached pages.
All 508 Python tests pass, including source order, relative font paths,
conditional requests and immutable caching only for the matching bundle version.

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


## October 11: browsing and save responsiveness

Implemented across the website and `/Users/mila/stats ios`:

1. **Paged app game lists:** doubles, Vollis, and Other accept optional `limit`,
   `offset`, and `q`. The app requests 50 rows, shows the full matching count,
   and offers Load older games. Search covers all players (including all 15
   Other-game positions), the complete selected history, and the selected game.
   No-limit and incremental-sync requests retain their previous behavior.
2. **Reusable combined data:** authorized source selections reuse bounded raw
   snapshots. Source changes, selected accounts, schema changes, and deployment
   changes alter the key. Each request receives a separate writable copy; it
   never modifies the reusable snapshot. Sharing permissions are rechecked first.
3. **Broader calculation reuse:** website calculations reuse bounded copied results
   under the current source revision and filters. The server response cache also
   covers app player pages, including the player route parameters in its key.
   Authenticated HTML, flash messages, and form tokens are not cached.
4. **Incremental tournament checking:** saves revalidate only changed two-hour
   game groups. The full history still defines group boundaries, so historical
   edits, deletions, and groups spanning midnight remain correct. Sessions are
   published in one transaction, with no delete/reinsert when unchanged.
5. **Narrower refreshes:** server response and website calculation revisions distinguish doubles, Vollis,
   and Other. App game mutations mark only the affected sport's saved pages stale;
   legacy snapshots and uncertain mutations refresh conservatively. Account and
   source changes still invalidate everything. This release narrows by sport,
   not individual player/year, since rankings and all-years totals cross both.
6. **Background app work:** standings, game lists, player details, and library
   snapshots read/write away from the UI executor; response decoding and mutation
   cache maintenance also run in the background. Generation and request checks
   prevent canceled or old-account results from replacing current data.
7. **One Other-standings request:** `include_volleyball=1` returns the full native
   screen, using the same fallback year for every card. The app retains a fallback
   for older servers. Vollis uses the existing today-summary response instead of
   downloading an entire year as a fallback.
8. **Small previews:** recap/flyer lists use versioned JPEG previews up to 640px.
   Browsers lazy-load them; download/share buttons still use originals. Preview
   storage is bounded, original deletion immediately makes the preview unavailable,
   and the route can only read the existing public email/flyer image directories.
9. **Immediate feedback:** website navigation and ordinary form submissions show a
   small loading/saving message. Canceled, modified, same-page, download, external,
   and AJAX-handled actions retain their behavior. App Games and Flyers show loading
   states; recaps/flyers restore saved lists and keep them visible during refresh.
10. **Action measurements:** responses expose `Server-Timing`; a bounded 256-sample
    server buffer records endpoint timings and anonymous browser navigation, tap,
    long-task, response-wait, download, and document-ready measurements. Admins can
    read `/api/admin/performance`. Actions over one second also go to server logs.
    App logs under `stats.performance` distinguish screen loading, requests,
    network waits, and decoding, with server timings when present. Measurements
    omit account identifiers, player names, credentials, and URL query strings.

### Local measurements

Run `python scripts/benchmark_browsing_speed.py` with the project dependencies.
The script uses temporary synthetic databases only. The October 11 sample had
3,000 games and 1,000 valid tournament groups. Values are medians (five runs;
three for the old full tournament rebuild), with prepared caches warmed.

| Operation | Previous work | New work |
| --- | ---: | ---: |
| Combined data preparation | 15.68 ms rebuilding | 1.03 ms reusing |
| Game-list query and JSON | 9.35 ms for full history | 0.93 ms for first 50 |
| Game-list JSON size | 451,893 bytes | 7,595 bytes |
| Tournament update | 730.91 ms full rebuild | 17.38 ms with one changed group |

The benchmark checks identical tournament summaries. Paged histories retain
complete totals and deterministic newest-first ordering. These are local,
synthetic operation measurements, not live hosting, network, or phone timings.
Cold-cache requests still do their initial preparation. Browser tap measurements
approximate next-frame feedback; they are not a full INP implementation. The
server sample buffer is per worker, resets on restart, and is not a durable
analytics database; slow-action server logs support diagnosis across workers.

### Verification and release

Python checks cover pagination/search, account and sharing boundaries, mutation
invalidation, snapshot reuse, isolated player keys, incremental KOB results and
rollback, thumbnail path restrictions, and telemetry bounds. Swift cache checks
cover async persistence, pagination cursors, per-sport invalidation, and rejected
late responses. JavaScript checks cover normal and canceled navigation, browser
back, form feedback, and anonymous telemetry. An unsigned iPhone device build
passed. No cloud browser was available for fresh visual or live-device checks.
The full Python suite's existing image-prompt wording failure remains the one
previously documented above; it is unrelated to these changes.

Website commit note when committing this work:

    Site-Update: Faster browsing and game saves
    Stats and player pages reuse recent results, and saving games avoids repeating
    unchanged tournament checks. Recap and flyer lists use smaller pictures, and
    loading messages make it clearer when a page is opening.

The app note is `ios-2026-10-11-faster-browsing` in `data/app_updates.json`.

## October 11: page loading follow-up

The public deployment was still spending 522–1,024 ms generating current
standings on three consecutive requests; single all-years standings and player
requests took 1,582 ms and 1,321 ms inside the application. The homepage made
two redirects. Compression already worked, but versioned styles/scripts were
sent with `Cache-Control: no-cache`, requiring repeat validation. These were
HTTP measurements, not browser rendering or mobile-network measurements.

The follow-up changes:

- The game menu reads only names and categories, keeping the latest category
  per name, and reuses the result under the authorized data revision and filters.
  It no longer loads every column of every Other game just to build navigation.
- Today's games/results, game counts, location choices, and player year choices
  reuse revision-scoped calculations. Changes to games/players still invalidate
  the relevant results. Avatar metadata is fetched together and its connection
  is closed immediately. Personalized HTML and form tokens are still rendered
  separately for every request.
- Styles/scripts receive automatic content-derived versions and a one-year
  immutable cache policy only when the requested version matches. Unversioned
  files, old versions, uploads, and error responses do not receive that policy.
  Public static requests bypass account lookup and session-cookie refresh.
- The homepage and standings aliases redirect directly to the final shared
  standings address, preserving source selection and repeated filters.
- The existing theme code runs inline before styles load, preserving appearance
  without a blocking script download. Font Awesome is served locally, with
  only the used icons included. The CSS and three fonts total 16,305 bytes,
  versus 227,533 bytes for the upstream CSS and three WOFF2 fonts. Browsers
  only fetch fonts actually needed on each page. The upstream license is kept.

Run `python scripts/benchmark_page_loading.py` locally with project dependencies;
`--root PATH` selects another checkout. It backs up the local database into a
temporary directory and refuses to run where the production database path exists.
These October 11 results compare `bbcf2c6` with the follow-up, using the same local
data, signed-out share links, one initial request and five repeat requests per
page. Each request returned HTTP 200. Initial requests include template setup;
the pages are measured sequentially, so later pages can share prepared data.

| Page | Before initial | After initial | Before repeat median | After repeat median |
| --- | ---: | ---: | ---: | ---: |
| Current standings | 666 ms | 536 ms | 149 ms | 28 ms |
| All-years standings | 373 ms | 243 ms | 182 ms | 46 ms |
| Large all-years player | 303 ms | 207 ms | 219 ms | 96 ms |

These are local response-generation timings, not a prediction of live load times.
Regression checks cover content-version changes, upload caching exclusions,
cookie-free static delivery, icon coverage, one-hop redirects, repeated filters,
private/shared data boundaries, edited results, location/division isolation,
avatar fallback matching, and closed connections. The existing theme, sharing,
and navigation JavaScript checks pass. All 402 Python tests now pass. The stale
image-prompt test documented in earlier runs has been corrected to check the
current default and custom generation paths, including the location sent to the
image provider, whitespace trimming, and omission of blank locations. Production
prompt wording is unchanged. This test-only correction needs no player-facing
announcement (`Site-Update: none` if committed separately). A cloud browser was
not available for a fresh rendering check, and these changes have not been deployed.

Site update when committing this work:

    Site-Update: Faster page loading
    Standings and player pages do less repeated work. Returning visits reuse
    the site's styles and icons, and opening the homepage takes fewer steps.

## October 11: native app startup and repeat visits

The native app now keeps up to 12 decoded snapshots per cache, with a 16 MiB
estimated decoded-cost budget (four times the encoded size). Memory warnings
release them; protected, bounded disk snapshots still support reopening the app.
A recently visited screen avoids disk reading and JSON decoding. Each cache
keeps at most 48 disk snapshots; filenames, rather than absolute URLs, track the
inventory so `/var` and `/private/var` aliases cannot break eviction.

Game edits now write one small revision marker per affected cache rather than
opening, decoding and rewriting every saved page. Sport-specific changes keep
unrelated sports fresh. Older snapshots remain readable during refresh, and
revision changes reject late responses. Corrupt markers fail stale. Sign-out
and source changes still discard snapshots and decoded data.

Identical simultaneous GETs share a download, with separate keys for auth,
selected sources, preview/owned scope, filters and local data revisions.
Cancellation of one consumer does not cancel another consumer's request.
Year lists reuse results for five minutes; game catalogs for one minute.
Mutations invalidate these earlier. Navigation and Add share the catalog cache
when their request scopes match; owned entry defaults remain separate from
combined browsing. Metadata and form preloads wait until the visible browsing
screen's first load finishes. The root no longer repeats the app's session check.

Profile editing uses `GET /api/player-profile?name=...` to fetch one profile
without aggregating game histories or constructing the full roster. It returns
`{"player": <profile>}` or `{"player": null}` with HTTP 200 for an absent name;
a blank name gets HTTP 400. Optional history totals are omitted. Photo URLs,
traits, crop focus, nickname and editable fields follow `/api/players`.
The endpoint follows the same owned/combined authorization rules as the roster,
requires current source permission, and uses `Cache-Control: no-store`.
The app falls back to its previous roster lookup only if an older server returns
404. Deploying the website endpoint enables the smaller profile request.

Validation includes an unsigned iPhone build, Swift tests for decoded reuse,
memory eviction, durable invalidation, legacy snapshots, coalescing, cancellation,
retries and scope isolation, plus Python tests exercising the real profile
lookup/card builder through owned and combined account routing. All 405 Python
tests and the four targeted Swift test programs pass. These checks do not measure
launch/render times on a physical iPhone. The app needs a new build
installed before users receive its changes.

The app note is `ios-2026-10-11-faster-startup-and-return-visits` in
`data/app_updates.json`. Suggested commit notes for each repository:

    Site-Update: Faster iPhone browsing
    The app gives the screen you opened priority, reuses recently viewed pages,
    and avoids duplicate downloads. Player profiles need less data to open.
