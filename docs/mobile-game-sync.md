# Phone saves and background sync

New doubles, Vollis, and other games are written atomically to the phone's
Application Support directory before the save confirmation appears. The local
record includes its account, complete request, permanent UUID, and upload status.
A failed disk write leaves the form intact. Previously verified accounts can
reopen offline; Face ID remains required when enabled.

Wins, losses, ties, game counts, and win percentages combine the last website
snapshot with local saves missing from that snapshot. Ratings remain the last
confirmed website values and are labeled as awaiting confirmation. Locally saved
games stay available across app restarts. This change covers new games; existing
edit and delete flows retain their current behavior.

The sync worker uploads serially and retries temporary failures with backoff.
It resumes on connection recovery and app activation. iOS may suspend the app;
remaining uploads resume when it can run again. Validation/authentication errors
stay visible and keep the local game. An older offline queue entry without a
server receipt is held for review rather than blindly replayed.

## Server contract

- `GET /api/mobile-sync` returns `{"version": 1}`. The phone checks this before
  uploading, so an app installed before the website update cannot accidentally
  send retries to an older server without duplicate protection.
- Game POSTs include `client_game_id`. The server records the authenticated owner,
  UUID, game type, request hash, and inserted ID in `mobile_game_receipts`, in the
  **same SQLite transaction** as the game. A repeated request returns its original
  receipt; reusing an ID with different details is rejected. Receipts survive
  game deletion so delayed retries cannot recreate deleted games.
- Stats, game lists, player details, and the doubles entry dashboard accept
  `X-Stats-Local-Snapshot: 1`. Responses include `synced_local_game_ids`. The phone
  only removes the corresponding local contribution from that exact snapshot.
  POST success alone never removes it from an older displayed snapshot.
- Combined-source snapshots copy owned games and receipts within one read
  transaction. Live reads check source revisions and reject a racing response.
  Prepared responses distinguish the mobile snapshot protocol from older clients.

Deploy the website support before distributing the updated iPhone app. No manual
schema migration is needed; receipts are created when the first mobile save is
committed. Do not prune receipts while a device might still retry an old save.

## Verification

Website regression coverage lives in `tests/test_mobile_game_sync.py` and the
existing game-location, source-selection, response-cache, and update-note tests.
It covers lost responses, simultaneous retries, separate rematches, rollback,
account isolation, deletion, and snapshot consistency.

The iPhone repository includes `LocalGamesTests.swift`, `LocalGameSyncTests.swift`,
`StatsFiltersTests.swift`, and `BrowseCacheTests.swift`. They exercise durable
saves, restart, local totals, ties, filters, disk failures, delayed confirmation,
one sync worker, retries, account switching, and stable refresh identities.
