(function () {
    'use strict';
    function decode(value) {
        var text = value.replace(/-/g, '+').replace(/_/g, '/');
        return Uint8Array.from(atob(text), function (char) { return char.charCodeAt(0); });
    }
    function encode(value) {
        return btoa(Array.from(new Uint8Array(value), function (byte) {
            return String.fromCharCode(byte);
        }).join('')).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    }
    function optionsForBrowser(options) {
        options.challenge = decode(options.challenge);
        if (options.user) options.user.id = decode(options.user.id);
        ['excludeCredentials', 'allowCredentials'].forEach(function (field) {
            (options[field] || []).forEach(function (item) { item.id = decode(item.id); });
        });
        return options;
    }
    function credentialJSON(credential) {
        var response = {};
        ['clientDataJSON', 'attestationObject', 'authenticatorData', 'signature', 'userHandle'].forEach(function (field) {
            if (credential.response[field] != null) response[field] = encode(credential.response[field]);
        });
        if (credential.response.getTransports) response.transports = credential.response.getTransports();
        return {id: credential.id, rawId: encode(credential.rawId), type: credential.type, response: response,
            clientExtensionResults: credential.getClientExtensionResults()};
    }
    document.querySelectorAll('[data-passkeys]').forEach(function (panel) {
        var status = panel.querySelector('[data-passkey-status]');
        var supported = window.isSecureContext && window.PublicKeyCredential && navigator.credentials;
        var busy = false;
        if (supported) {
            panel.querySelectorAll('[data-passkey-help], [data-passkey-action="login"]').forEach(function (item) { item.hidden = false; });
        } else {
            status.textContent = 'Passkeys aren’t available in this browser. You can still use an email code to sign in.';
        }
        async function post(path, body) {
            var response = await fetch('/auth/passkeys/' + path, {
                method: 'POST', credentials: 'same-origin',
                headers: {'Content-Type': 'application/json', 'X-CSRF-Token': panel.dataset.csrf},
                body: JSON.stringify(body)
            });
            var result;
            try { result = await response.json(); } catch (_) { result = {}; }
            if (!response.ok) {
                throw new Error(result.error || (response.status === 403 ?
                    'Please reload this page and sign in again before managing passkeys.' :
                    response.status === 429 ? 'Too many attempts. Please wait five minutes.' :
                    'Couldn’t finish. Please try again, or sign in with email.'));
            }
            return result;
        }
        panel.addEventListener('click', async function (event) {
            var button = event.target.closest('[data-passkey-action]');
            if (!button || busy) return;
            var action = button.dataset.passkeyAction;
            if (!supported && action !== 'remove') return;
            if (action === 'remove' && !window.confirm('Remove this passkey from your Stats account? Email sign-in will still work.')) return;
            busy = true;
            panel.querySelectorAll('button').forEach(function (item) { item.disabled = true; });
            status.textContent = action === 'remove' ? 'Removing passkey…' : 'Follow your device’s prompt…';
            try {
                if (action === 'remove') {
                    await post('remove', {id: button.dataset.id});
                    window.location.reload();
                } else {
                    var remember = document.querySelector('input[name="remember_me"]');
                    var options = await post(action + '/options', {remember: !!(remember && remember.checked)});
                    var credential = await navigator.credentials[action === 'register' ? 'create' : 'get']({
                        publicKey: optionsForBrowser(options)
                    });
                    if (!credential) throw new Error('No passkey was selected. Try again or use an email code.');
                    var body = {credential: credentialJSON(credential)};
                    if (action === 'register') body.label = panel.querySelector('#passkey-label').value.trim() || 'My passkey';
                    var result = await post(action + '/verify', body);
                    if (action === 'register') window.location.reload();
                    else if (result.redirect && result.redirect.startsWith('/') && !result.redirect.startsWith('//')) window.location.assign(result.redirect);
                    else throw new Error('Please reload and try signing in again.');
                }
            } catch (error) {
                status.textContent = error.name === 'NotAllowedError' ?
                    'Passkey sign-in was canceled or unavailable. Try again, or use an email code.' :
                    error.name === 'InvalidStateError' ? 'This passkey is already saved. Try signing in with it.' :
                    error.message || 'Couldn’t use a passkey. Please try again or use email.';
            } finally {
                busy = false;
                panel.querySelectorAll('button').forEach(function (item) { item.disabled = false; });
            }
        });
    });
}());
