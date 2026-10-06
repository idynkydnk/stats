# Personal iPhone accounts

Every non-Kyle account owns a separate game database. New accounts start empty;
existing accounts are migrated by `entered_by`, never by player participation or
last editor. Missing or unknown entry ownership remains with KT Stats. Passwords,
usernames, active status, and sign-in tokens remain in the identity database.
Tournaments are not part of personal storage or this migration.

Stats to include changes a browsing preference, never stored game ownership.
Kyle can include individual users as admin. A one-time startup migration captures
the active existing users in `stats_source_group`, checks every source for them,
and enables their sharing. Later restarts preserve each user's saved choices.
Existing group members can include KT Stats and accounts whose owners share
their stats. Revoking sharing immediately removes non-admin access even if a
viewer previously selected it. New accounts, including Google and Apple sign-ups,
can include only KT Stats, enabled by default, alongside their own games. They
cannot discover or select Dan, Tyler, or other users through the source picker,
even when those users share with the existing group. New accounts' own sharing
starts off. Public visitors see only KT Stats unless given an explicit stats link.
The group is captured before personal-database separation when needed; separation
also applies the group's sharing default to newly created personal databases.

Combined views recalculate stats and ratings from the selected game histories.
A request-local, data-only snapshot keeps authentication tables out of the view.
External game IDs are namespaced above 2^32 so overlapping personal IDs cannot
collide; external games are read-only in that view, including for Kyle. Saves,
edits, deletes, add-screen lookups, and AI selection stay in the signed-in owner's
database. Authenticated browsing uses selected sources by default, including older app
builds. The updated app sends `X-Stats-Combined: 1` for browsing and
`X-Stats-Owned: 1` for add-screen lookups. Existing signed-in
`X-Stats-Preview: 1` reads also use the user's selected combined view, while
signed-out previews remain KT-only.

## Backup and cloud migration

Stop website and AI writers during migration. Run from the deployed repository:

```sh
python migrations/separate_existing_accounts.py --database /home/Idynkydnk/stats/stats.db
python migrations/separate_existing_accounts.py --database /home/Idynkydnk/stats/stats.db --apply
```

The first command is a read-only ownership report. Applying first creates and
integrity-checks SQLite backups of the identity database and every existing
personal database under `backups/before-personal-databases-*`. Account moves use
attached databases in rollback-journal transactions: inserts, source removals,
and completion markers commit together per account. Conflicting IDs stop that
account's transaction without overwriting games. Re-running skips completed
accounts. Original game IDs, scores, dates, comments, entry ownership, division,
and associated player metadata are retained. Derived rankings are cleared.

Back up `private_data/` (or `STATS_PRIVATE_DATA_DIR`) and uploaded/generated media
alongside the identity database. Never serve personal database files publicly.
Future schema migrations must explicitly cover all existing personal databases;
ordinary requests no longer run schema provisioning on an existing file.

Deploy the backend and run the migration before distributing the updated app.
Verify Kyle's combined totals, each user's owned-only totals, read-only foreign
games, new game writes, source toggles, and sharing revocation before ending
maintenance. For rollback, stop writers, restore the matching backup databases
and backend code together; preserve any games saved after migration separately.

## Google sign-in

Social account display names are saved separately from their stable login keys.
Google names come from verified profile claims and are refreshed on sign-in,
including for existing accounts. Apple names come from the native authorization's
full-name field after token and nonce verification. The iPhone app requests that
field and keeps it in Keychain until sign-in succeeds so a failed request can be
retried. Later sign-ins without a name never clear the saved name. Display names
do not link accounts, change game ownership, or grant roster access. Duplicate
names remain separate accounts. A linked roster name still takes precedence in
the account header. Source lists and shared stats links use the same name rules
for current users too: linked roster name first, then a saved profile name or a
unique roster match. The shared public database always remains “KT Stats”.

If no name was supplied or saved, labels say “Google account” or “Apple account”
instead of exposing the generated login key. Existing Google users get their name
on their next Google sign-in; an Apple name cannot be recovered if the provider
does not supply it again.

The local iPhone project's older Google configuration identifies the OAuth iOS
client below for the matching bundle ID `com.kt.stats`. The code uses this public
client ID and its reversed URL scheme; no Google client secret goes in the app.

`195048170299-63t84plh4cae8a7r5nk70d8l8hkr3t8p.apps.googleusercontent.com`

Before release, confirm that this client still exists in Google Cloud, its iOS
bundle ID is correct, and the consent screen permits the intended users. A real
Google sign-in on a device is still required to verify the external configuration.
To replace it, set `GOOGLE_IOS_CLIENT_ID` on the server and update the corresponding
reversed URL scheme in the app's `Info.plist`. Setting the environment variable
to an empty string disables Google sign-in on the server.

The app uses the system authentication browser with state and PKCE. The server
verifies the Google ID token's signature, issuer, expiry, audience, and verified
email through google-auth, and identifies the account by Google's subject ID.

Reference: [Google's native OAuth flow](https://developers.google.com/identity/protocols/oauth2/native-app).

## Apple sign-in

Enable Sign in with Apple for `com.kt.stats` in the Apple Developer account and
regenerate the app's provisioning profile before a signed device/TestFlight build.
The app entitlement and native Apple button are included. The server expects
`com.kt.stats` as the token audience; `APPLE_IOS_CLIENT_ID` overrides that value
for another bundle ID.

The server issues a ten-minute, single-use nonce and verifies Apple's token
signature with Apple's signing keys, including issuer, audience, expiry, and
nonce. Accounts use Apple's stable subject ID, so Hide My Email is supported.
Test completion and cancellation on a signed device before release. Apple token
revocation and developer server notifications are not integrated in this change;
include that lifecycle work in the App Store release review.

Reference: [Apple user verification](https://developer.apple.com/documentation/signinwithapple/verifying-a-user).

## Verification

Run `venv/bin/python -m unittest tests.test_private_accounts` for registration,
private storage, account isolation, inactive accounts, cache isolation, Google
verification, and Apple's signature/nonce/audience/replay checks. Provider tests
do not contact live identity providers.

Test two new accounts on devices: save games in each, switch accounts, sign out,
relaunch, and confirm neither account shows the other's games or shared history.
Check password sign-in plus Google and Apple sign-in. The app offers personal
account deletion under More; it removes private data and revokes local sessions,
retaining an inactive identity marker to prevent reuse of old access.
