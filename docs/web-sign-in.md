# Website email sign-in

The website uses one email flow for sign-in and account creation. Enter an email,
then enter the four-digit code. Existing linked accounts retain their username,
permissions, and stats. A new email creates a personal account only after the
code is verified and the user supplies both first and last names. Apple and
Google buttons, browser SDKs, and `/auth/<provider>` endpoints have been removed. The iPhone authentication endpoints remain supported.

## Email delivery

Use the existing `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USE_TLS`, `MAIL_USERNAME`,
`MAIL_PASSWORD`, and `MAIL_DEFAULT_SENDER` settings. No OAuth website configuration
is needed. Codes use Flask-Mail directly and go only to the requested address;
recap copy recipients, subscriptions, and update-email recipients are not used.
Keep SMTP timeouts bounded in the hosting environment. A delivery error displays
a retry message without signing in or creating an account.

## Existing accounts

On first startup, `site_users.login_email` is populated only from explicitly
saved `player_name` links with a single valid player email. There is no match by
first name, nickname, or suggested update recipient. These email links are
snapshots: subsequent public player edits cannot change account access.

Existing users without a saved email are asked to add one after signing in with
their current password. Remembered browser sessions also receive the prompt on
their next page visit. They verify the new email with a code before it is linked
to their original account; usernames, permissions, and stats stay unchanged.
This does not interrupt native app or API requests. No administrator needs to
collect those addresses in advance. An address linked to another account is
rejected, and a submitted username or name cannot claim an old account.

New email signups verify their email first, then enter required first and last
names. No account is created until both steps are complete. All-lowercase and
all-uppercase name components are capitalized, including hyphenated and
apostrophized names; intentional mixed capitalization such as McDonald is kept.
Both name parts and the combined display name are stored. The verified email
proof expires after ten minutes and can only finish one signup.

The name screen also offers an existing-account path for users who started with
an email that is not yet linked. A user with neither a remembered session nor a
working password must contact Kyle to recover the old account; a typed name
alone never grants access to somebody else's stats.

In Admin → Site users, **Sign-in email** remains available for verified account
support. Saving it invalidates outstanding codes for the old and new address.
An email already linked to another account is rejected. Saving a blank email
removes email sign-in and causes the user to be prompted again. Player edits and
Site updates recipient selections do not change login access. Inactive or
ambiguous accounts are blocked after code verification instead of reassigned.

Older social accounts did not retain provider email claims. Their next successful
iPhone provider sign-in saves a verified provider email if no login email is
already set. Apple Hide My Email uses the relay address Apple supplies. Provider
subjects remain the identity keys; matching an email never merges social accounts.
Conflicting email associations fail closed on the website.

## iPhone email sign-in

The native app uses `GET /api/auth/email` to begin, then posts JSON actions
(`send`, `verify`, `resend`, `change`, `signup`, or legacy `password`) to the same
endpoint. All field values are strings. Each response carries `step`, `csrf`,
`email`, and `enrolling`; errors keep the current step and include `error`.
Completed sign-ins return `step: complete` and a bearer `token`. The app verifies
that token with `/api/me` before storing it in Keychain or displaying account data.

This is the same handler as browser sign-in: email normalization, challenge
storage, expiry, retry limits, name validation, and account lookup are shared.
Native sign-in owns a dedicated ephemeral cookie jar and includes the returned
CSRF token on every POST. Cookies from this flow never authenticate normal app
requests. An existing bearer token can be supplied on the initial GET to enroll
an email. Invalid bearer credentials are rejected instead of falling back to
another session. `/api/me` includes `needs_login_email`, prompting signed-in app
users to verify an email before returning to their stats. Previous app versions
remain compatible with the existing auth endpoints.

Deploy this server update before distributing the new app build. The app shows
a retry message if email sign-in is unavailable. No real emails are sent by the
automated tests; `tests/test_email_app_sign_in.py` covers the native JSON flow.

## Security and verification

Four-digit codes expire after five minutes and permit at most three verification
attempts per code, plus a shared limit of six incorrect attempts per email per
hour across browsers, IPs, and resends.
Only keyed hashes are stored, with a random challenge bound to the browser
session. CSRF validation applies to all forms. Successful verification consumes
the code and resolves the existing account or stores a short-lived signup proof.
Finishing signup atomically consumes that proof and creates the account. Email
enrollment binds the code to the authenticated original account and rechecks
that account before saving; it cannot overwrite a newly assigned email.
Resending replaces that browser's previous code. Delivery and verification
limits live in SQLite so they persist across workers and restarts. Email sends
are limited to one per minute and five per hour per address, and twenty per hour
per IP. Verification and password attempts have separate per-IP limits.

Login pages are not cached; redirects remain on-site. Remember me uses the
existing 90-day HttpOnly, SameSite cookie (Secure on HTTPS). The flow works
without JavaScript and supports mobile code autofill and pasted codes.

Run:

    venv/bin/python -m unittest tests.test_web_sign_in tests.test_private_accounts tests.test_google_app_sign_in tests.test_site_updates
    node --test tests/test_web_sign_in.js

Tests use temporary databases and intercepted email; they never send real codes.
Before release, confirm a real delivery with an explicitly authorized recipient
and check the page on a cloud browser at phone and desktop sizes.

## Site update for the commit

Site-Update: Sign in with an email code
Sign in with your email and a four-digit code. Existing users can add their email when they sign in, and new users enter their first and last names with capitalization tidied automatically.
