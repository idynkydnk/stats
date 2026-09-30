# Personal iPhone accounts

New accounts start with an empty, private game history and a separate read-only
preview of KT Stats. Visitors can browse that preview before signing
in. Personal accounts can switch between KT Stats and their own, or choose
Hide KT Stats. This saves a per-account visibility preference; no shared or
personal records are deleted. More offers a toggle to show the preview again.
Add always uses personal game data. Username/password,
Google, and Apple sign-in all provision personal accounts. Existing website
accounts retain their shared website access. These are distinct sign-in methods;
accounts are not automatically merged based on email addresses.

## Server deployment

Deploy the website changes and install `requirements.txt` before distributing
the updated app. The app verifies account scope before opening the main screens
and cannot sign in against an older server without this update.

The server creates `private_accounts` and `private_auth_challenges` in its
existing identity database. New personal databases are created under
`private_data/`, alongside the site database, or at `STATS_PRIVATE_DATA_DIR`.
This directory must be writable by the web worker and must not be served as
static files. Include it in secure server backups. No games, players, photos,
or credentials are copied from the shared database: only game-table schemas
are copied. Future schema migrations must also cover existing personal databases.

Private-account requests can use only the explicitly listed personal API routes.
An explicit `X-Stats-Preview: 1` request can read only allowlisted public stats
endpoints. Preview writes and privileged routes are rejected. Normal authenticated
requests always select the personal database regardless of preview preferences.
Game queries, player queries, ratings, tournaments, and deletion markers use the
authenticated account's database. In-memory stats caching is bypassed for these
requests. Personal games are not written into the shared activity log. Shared
AI publishing, public links, public photos, and admin tools are unavailable in
personal accounts. The website's public shared stats remain public.

## Google sign-in

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
