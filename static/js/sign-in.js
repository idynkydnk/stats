(() => {
    'use strict';
    const config = JSON.parse(document.getElementById('sr-sign-in-config').textContent);
    const apple = document.getElementById('sr-apple-button');
    const googleButton = document.getElementById('sr-google-button');
    const googlePlaceholder = document.getElementById('sr-google-placeholder');
    const error = document.getElementById('sr-social-error');
    const status = document.getElementById('sr-social-status');
    const region = document.getElementById('sr-social-login');
    let busy = false;
    let appleReady = false;

    function showError(message) {
        error.textContent = message;
        error.hidden = false;
    }

    function setBusy(value) {
        busy = value;
        region.setAttribute('aria-busy', String(value));
        apple.disabled = value || !appleReady;
        googleButton.inert = value;
        status.textContent = value ? 'Signing in…' : '';
    }

    async function finish(provider, payload) {
        const response = await fetch(config[provider + '_url'], {
            method: 'POST',
            credentials: 'same-origin',
            headers: {'Content-Type': 'application/json', 'X-CSRF-Token': config.csrf},
            body: JSON.stringify({
                ...payload,
                next: config.next,
                remember_me: document.getElementById('remember_me').checked
            })
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'Sign-in did not finish. Please try again.');
        window.location.assign(result.next);
    }

    function loadSDK(src, ready, provider) {
        const script = document.createElement('script');
        script.src = src;
        script.async = true;
        script.onload = () => {
            try { ready(); }
            catch (_) { showError(provider + ' sign-in could not load. Reload the page or use your password.'); }
        };
        script.onerror = () => showError(provider + ' sign-in could not load. Reload the page or use your password.');
        document.head.appendChild(script);
    }

    if (config.google_client_id) {
        loadSDK('https://accounts.google.com/gsi/client', () => {
            google.accounts.id.initialize({
                client_id: config.google_client_id,
                nonce: config.nonce,
                auto_select: false,
                callback: async (result) => {
                    if (busy) return;
                    error.hidden = true;
                    setBusy(true);
                    try { await finish('google', {id_token: result.credential}); }
                    catch (failure) {
                        showError(failure.message || 'Google sign-in did not finish. Please try again.');
                        setBusy(false);
                    }
                }
            });
            googleButton.hidden = false;
            google.accounts.id.renderButton(googleButton, {
                type: 'standard', theme: 'outline', size: 'large', text: 'continue_with',
                width: Math.min(400, region.clientWidth)
            });
            googlePlaceholder.hidden = true;
        }, 'Google');
    }

    if (config.apple_client_id && config.apple_redirect_uri) {
        loadSDK('https://appleid.cdn-apple.com/appleauth/static/jsapi/appleid/1/en_US/appleid.auth.js', () => {
            AppleID.auth.init({
                clientId: config.apple_client_id,
                scope: 'name email',
                redirectURI: config.apple_redirect_uri,
                state: config.csrf,
                nonce: config.nonce,
                usePopup: true
            });
            appleReady = true;
            apple.disabled = busy;
        }, 'Apple');

        apple.addEventListener('click', async () => {
            if (busy) return;
            error.hidden = true;
            setBusy(true);
            try {
                const result = await AppleID.auth.signIn();
                const name = result.user && result.user.name;
                await finish('apple', {
                    id_token: result.authorization.id_token,
                    state: result.authorization.state,
                    full_name: name ? [name.firstName, name.lastName].filter(Boolean).join(' ') : undefined
                });
            } catch (failure) {
                if (!failure || !['popup_closed_by_user', 'user_cancelled_authorize'].includes(failure.error)) {
                    showError((failure && failure.message) || 'Apple sign-in did not finish. Please try again and allow the sign-in popup.');
                }
                setBusy(false);
            }
        });
    }
})();
