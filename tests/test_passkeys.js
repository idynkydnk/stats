const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('static/js/passkeys.js', 'utf8');

function harness(action, {supported = true, cancel = false, failed = false, confirm = true} = {}) {
    const button = {dataset: {passkeyAction: action, id: 'aWQ'}, disabled: false, hidden: true};
    const help = {hidden: true};
    const status = {textContent: ''};
    const label = {value: 'My iPhone'};
    let click;
    const requests = [];
    const navigations = [];
    const calls = [];
    const panel = {
        dataset: {csrf: 'csrf-token'},
        querySelector: selector => selector === '#passkey-label' ? label : status,
        querySelectorAll: selector => selector === 'button' ? [button] : [help, button],
        addEventListener: (_, handler) => { click = handler; }
    };
    const bytes = new Uint8Array([0, 255, 239, 128]).buffer;
    const browserCredential = {
        id: 'credential-id', rawId: bytes, type: 'public-key',
        response: {clientDataJSON: bytes, attestationObject: bytes, authenticatorData: bytes,
            signature: bytes, userHandle: bytes, getTransports: () => ['internal']},
        getClientExtensionResults: () => ({})
    };
    const authenticate = async options => {
        calls.push(options);
        if (cancel) throw Object.assign(new Error('Canceled'), {name: 'NotAllowedError'});
        return browserCredential;
    };
    vm.runInNewContext(source, {
        Uint8Array, Array, JSON, Error,
        atob: value => Buffer.from(value, 'base64').toString('binary'),
        btoa: value => Buffer.from(value, 'binary').toString('base64'),
        window: {isSecureContext: supported, PublicKeyCredential: supported ? {} : null,
            confirm: () => confirm, location: {reload: () => navigations.push('reload'), assign: path => navigations.push(path)}},
        navigator: {credentials: {get: authenticate, create: authenticate}},
        document: {querySelectorAll: () => [panel], querySelector: () => ({checked: true})},
        fetch: async (url, options) => {
            requests.push({url, ...options, body: JSON.parse(options.body)});
            if (failed) return {ok: false, status: 403, json: async () => ({error: 'Sign in again.'})};
            return {ok: true, json: async () => url.endsWith('/options') ? {
                challenge: 'AP_vgA', user: action === 'register' ? {id: 'AP_vgA'} : undefined,
                excludeCredentials: [{id: 'AP_vgA'}], allowCredentials: [{id: 'AP_vgA'}]
            } : {redirect: '/stats/2026', ok: true}};
        }
    });
    return {button, help, status, requests, navigations, calls,
        click: () => click({target: {closest: () => button}})};
}
(async () => {
    for (const action of ['register', 'login']) {
        const h = harness(action);
        await h.click();
        assert.equal(h.requests.length, 2);
        assert.equal(h.requests[0].headers['X-CSRF-Token'], 'csrf-token');
        assert.equal(h.requests[0].credentials, 'same-origin');
        assert.deepEqual(Array.from(h.calls[0].publicKey.challenge), [0, 255, 239, 128]);
        assert.deepEqual(Array.from(h.calls[0].publicKey.excludeCredentials[0].id), [0, 255, 239, 128]);
        assert.equal(h.requests[1].body.credential.response.clientDataJSON, 'AP_vgA');
        assert.equal(h.requests[1].body.credential.response.userHandle, 'AP_vgA');
        if (action === 'register') {
            assert.deepEqual(Array.from(h.calls[0].publicKey.user.id), [0, 255, 239, 128]);
            assert.equal(h.requests[1].body.label, 'My iPhone');
        }
        assert.deepEqual(h.navigations, [action === 'register' ? 'reload' : '/stats/2026']);
        assert.equal(h.button.disabled, false);
    }
    const canceled = harness('login', {cancel: true});
    await canceled.click();
    assert.equal(canceled.requests.length, 1);
    assert.match(canceled.status.textContent, /email code/);
    assert.equal(canceled.button.disabled, false);
    const unsupported = harness('login', {supported: false});
    await unsupported.click();
    assert.equal(unsupported.requests.length, 0);
    assert.equal(unsupported.button.hidden, true);
    assert.match(unsupported.status.textContent, /email code/);
    const failed = harness('register', {failed: true});
    await failed.click();
    assert.equal(failed.calls.length, 0);
    assert.equal(failed.status.textContent, 'Sign in again.');
    const removed = harness('remove');
    await removed.click();
    assert.equal(removed.requests[0].body.id, 'aWQ');
    assert.deepEqual(removed.navigations, ['reload']);
    const declined = harness('remove', {confirm: false});
    await declined.click();
    assert.equal(declined.requests.length, 0);
    console.log('Passkey browser-script checks passed: encoding, setup, login, fallback, cancellation, and removal.');
})().catch(error => { console.error(error); process.exitCode = 1; });
