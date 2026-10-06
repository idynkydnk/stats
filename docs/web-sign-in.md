# Website Apple and Google sign-in

The login page supports Apple and Google alongside the existing password form.
Both providers use the same account lookup as the iPhone app: the verified
provider subject identifies the account, never the supplied name or email.
New users get personal accounts; existing app users keep their account and stats.

## Google configuration

In the Google Cloud project used by the iPhone app, create an OAuth client with
application type **Web application**. Add the website's exact origin (for example,
`https://idynkydnk.pythonanywhere.com`) under Authorized JavaScript origins.
Set `GOOGLE_WEB_CLIENT_ID` in the website server environment to that client ID.
The existing `GOOGLE_IOS_CLIENT_ID` continues to be used only by the app.
The website uses the Google Identity Services popup callback, so no web client
secret or Google redirect endpoint is needed.

[Google setup](https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid)
and [JavaScript reference](https://developers.google.com/identity/gsi/web/reference/js-reference).

## Apple configuration

In the same Apple Developer team as the iPhone app, create a Services ID and
enable Sign in with Apple. Associate it with the app's primary App ID
(`com.kt.stats` unless the app configuration has changed). This grouping is
required for Apple to identify the same person consistently on the app and web.
Register the website domain and the exact HTTPS return URL, for example
`https://idynkydnk.pythonanywhere.com/login`.

Set `APPLE_WEB_CLIENT_ID` to the Services ID and `APPLE_WEB_REDIRECT_URI` to the
registered return URL. The popup SDK returns the authorization to the login
page's JavaScript, which submits it to `/auth/apple`. The server verifies the
identity token against Apple's public keys; this flow does not exchange the
authorization code or store Apple refresh tokens.

[Apple environment setup](https://developer.apple.com/documentation/signinwithapple/configuring-your-environment-for-sign-in-with-apple)
and [webpage setup](https://developer.apple.com/documentation/signinwithapple/configuring-your-webpage-for-sign-in-with-apple).

Reload the website after setting the variables. A provider's button stays
disabled with an explanatory message until its configuration is present.
Do not reuse the iOS client ID as a website client ID.

On PythonAnywhere, the live environment settings are in the separate WSGI file
`/var/www/idynkydnk_pythonanywhere_com_wsgi.py`; the repository copy does not show
what is configured there. Set these variables before `load_application()` runs.
For local development, set them in the ignored `.env` file.

## Verification before release

Run `venv/bin/python -m unittest discover -s tests -p 'test_web_sign_in.py'`.
The tests cover signed identity tokens, browser-bound CSRF and nonce checks,
single-use challenges, provider audiences, cookie handling, and account reuse.
Run `node --test tests/test_web_sign_in.js` for provider button handling,
cancellation, SDK failures, and server errors.

With the production provider settings in place, sign in with each provider in
the app and then on the website. Confirm that both show the same personal stats.
Also check a new account, canceled/blocked popups, a narrow phone screen, password
login, logout, and Remember me. Each browser login challenge expires after ten
minutes; reloading the page starts a fresh one.

## Site update for the commit

Site-Update: Sign in with Apple or Google on the website
Use the same Apple or Google account on the website and iPhone app to access your stats.
