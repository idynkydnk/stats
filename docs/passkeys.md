# Website passkey sign-in

Sign in with email, then open **Account → Passkeys / Face ID** to add a
passkey. Users can name and remove their saved passkeys. Setup and removal
require a sign-in within the last ten minutes; older sessions show a sign-in
link. On subsequent visits, choose **Sign in with a passkey**. The device or
password manager chooses Face ID, Touch ID, a PIN, or another supported form
of verification. Email codes remain available.

## Deployment

The deployment workflow installs the pinned WebAuthn dependency in the website’s
configured Python environment before deploying when requirements or the installer
change. It uses the existing hosting API credentials and deletes its temporary
installation task after verifying the installed version. For manual deployment,
install requirements before reloading (python -m pip install -r requirements.txt).
If WebAuthn is missing, email sign-in stays available and passkey controls stay
hidden until the dependency is installed.

The expected HTTPS origin comes from Flask's PASSKEY_ORIGIN configuration,
then SITE_BASE_URL, defaulting to https://idynkydnk.pythonanywhere.com.
The relying-party ID is that origin's hostname. Never derive it from request
headers or change it casually: passkeys belong to the original domain.
Use the canonical site address for registration and sign-in.

On startup, tables and cleanup triggers are added to the existing account
database. Back up that database as usual; no private keys are stored there.
Inactive or deleted accounts lose their passkeys, including when modified by
admin tools. Email remains the recovery path. Logging out does not delete
website passkeys; users can remove them from Account.

## Verification

Run the Python tests in tests/test_passkey_sign_in.py, tests/test_web_sign_in.py,
tests/test_email_app_sign_in.py, and tests/test_private_accounts.py with unittest.
Run node tests/test_passkeys.js for the browser-script checks.

The Python tests generate an EC credential and sign assertions, exercising the
actual WebAuthn verifier (including origin, challenge, signature and user
verification checks). They also cover session binding, expiry, replay, removal,
account isolation, account deletion, and rate limiting.

Before release, use a cloud browser with a virtual WebAuthn authenticator to
check registration and login end to end. Then check on an iPhone in Safari:
add a passkey, log out, sign back in with Face ID, cancel a prompt, recover with
email, and remove a passkey. Check narrow-screen layout, keyboard focus, and
an unsupported browser. No local browser or desktop automation was used.

## Site update for the release commit

Site-Update: Sign in with Face ID using a passkey
Add a passkey from the Account menu, then sign in with Face ID, Touch ID, or your device’s screen lock. You can manage saved passkeys and still use email codes whenever you need them.
