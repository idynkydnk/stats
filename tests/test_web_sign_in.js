const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../static/js/sign-in.js'), 'utf8');

function setup(overrides = {}) {
    const config = {
        google_client_id: 'google-web', apple_client_id: 'apple-web',
        apple_redirect_uri: 'https://stats.example/login', nonce: 'browser-nonce', csrf: 'browser-csrf',
        google_url: '/auth/google', apple_url: '/auth/apple', next: '/stats/2026', ...overrides
    };
    const elements = new Map();
    const scripts = [];
    const sent = [];
    const redirects = [];
    const state = {google: null, apple: null, result: {ok: true, next: config.next}};
    function element(id) {
        if (!elements.has(id)) elements.set(id, {
            textContent: '', hidden: false, disabled: true, checked: true, clientWidth: 300,
            events: {}, setAttribute() {},
            addEventListener(name, callback) { this.events[name] = callback; }
        });
        return elements.get(id);
    }
    element('sr-sign-in-config').textContent = JSON.stringify(config);
    const context = {
        document: {getElementById: element, createElement: () => ({}), head: {appendChild: script => scripts.push(script)}},
        window: {location: {assign: next => redirects.push(next)}},
        google: {accounts: {id: {
            initialize: options => { state.google = options; },
            renderButton: () => {}
        }}},
        AppleID: {auth: {
            init: options => { state.apple = options; },
            signIn: async () => {
                if (state.appleFailure) throw state.appleFailure;
                return {authorization: {id_token: 'apple-token', state: config.csrf}, user: {name: {firstName: 'Alex', lastName: 'Player'}}};
            }
        }},
        fetch: async (url, options) => {
            sent.push({url, options, body: JSON.parse(options.body)});
            return {ok: state.result.ok, json: async () => state.result};
        }
    };
    vm.runInNewContext(source, context);
    return {config, element, scripts, sent, redirects, state};
}

test('Google sends the browser challenge and Remember me choice, then redirects', async () => {
    const page = setup();
    page.scripts.find(s => s.src.includes('accounts.google.com')).onload();
    assert.equal(page.state.google.nonce, page.config.nonce);
    assert.equal(page.element('sr-google-placeholder').hidden, true);
    page.element('remember_me').checked = false;
    await page.state.google.callback({credential: 'google-token'});
    assert.equal(page.sent[0].url, '/auth/google');
    assert.equal(page.sent[0].options.headers['X-CSRF-Token'], page.config.csrf);
    assert.deepEqual(page.sent[0].body, {id_token: 'google-token', next: '/stats/2026', remember_me: false});
    assert.deepEqual(page.redirects, ['/stats/2026']);
});

test('Apple popup passes state, nonce, and first-sign-in name to the server', async () => {
    const page = setup();
    page.scripts.find(s => s.src.includes('appleid')).onload();
    assert.equal(page.element('sr-apple-button').disabled, false);
    assert.equal(page.state.apple.nonce, page.config.nonce);
    assert.equal(page.state.apple.state, page.config.csrf);
    assert.equal(page.state.apple.usePopup, true);
    await page.element('sr-apple-button').events.click();
    assert.equal(page.sent[0].body.full_name, 'Alex Player');
    assert.equal(page.sent[0].body.state, page.config.csrf);
    assert.deepEqual(page.redirects, ['/stats/2026']);
});

test('Apple cancellation restores the button without creating a session', async () => {
    const page = setup();
    page.scripts.find(s => s.src.includes('appleid')).onload();
    page.state.appleFailure = {error: 'popup_closed_by_user'};
    await page.element('sr-apple-button').events.click();
    assert.equal(page.element('sr-apple-button').disabled, false);
    assert.equal(page.element('sr-social-error').hidden, true);
    assert.equal(page.sent.length, 0);
});

test('Verification failures are visible and leave sign-in available to retry', async () => {
    const page = setup();
    page.scripts.forEach(script => script.onload());
    page.state.result = {ok: false, error: 'Reload the page and try again.'};
    await page.state.google.callback({credential: 'rejected-token'});
    assert.equal(page.element('sr-social-error').textContent, page.state.result.error);
    assert.equal(page.element('sr-social-error').hidden, false);
    assert.equal(page.element('sr-apple-button').disabled, false);
    assert.equal(page.element('sr-google-button').inert, false);
    assert.equal(page.redirects.length, 0);
});

test('Missing configuration loads no providers; failed SDK shows a useful error', () => {
    const disabled = setup({google_client_id: '', apple_client_id: ''});
    assert.equal(disabled.scripts.length, 0);
    assert.equal(disabled.element('sr-apple-button').disabled, true);
    const page = setup();
    page.scripts[0].onerror();
    assert.match(page.element('sr-social-error').textContent, /Reload the page or use your password/);
});
