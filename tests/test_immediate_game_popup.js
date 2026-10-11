// Run with: node tests/test_immediate_game_popup.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.join(__dirname, '..');
const template = fs.readFileSync(path.join(root, 'templates/add_game.html'), 'utf8');
const submit = template.slice(template.indexOf("document.getElementById('add-game-form').addEventListener('submit', async"),
    template.indexOf("document.addEventListener('DOMContentLoaded', function()", template.indexOf("addEventListener('submit', async")));

async function checkSave(response, rejects = false) {
    const calls = [];
    const form = { dataset: {}, action: '/add_game/?division=women', addEventListener(_, handler) { this.submit = handler; } };
    const fields = Object.fromEntries(['client_date', 'client_time', 'entered_timezone', 'winner1', 'winner2', 'loser1', 'loser2', 'winner_score', 'loser_score', 'location', 'comments', 'add-game-submit-btn'].map(id => [id, { value: id }]));
    fields.division = { selectedOptions: [{ textContent: 'Women’s Doubles' }] };
    fields['add-game-submit-btn'].textContent = 'Submit';
    let finish;
    const context = {
        document: { getElementById: id => id === 'add-game-form' ? form : fields[id] },
        Date, Intl, FormData: class { constructor(input) { assert.equal(input, form); } },
        nameFields: ['winner1', 'winner2', 'loser1', 'loser2'],
        fetch: (url, options) => {
            calls.push('save');
            assert.equal(url, form.action);
            assert.equal(options.headers.Accept, 'application/json');
            return new Promise((resolve, reject) => { finish = () => rejects ? reject(new Error('offline')) : resolve(response); });
        },
        clearAddGameForm: () => calls.push('clear'),
        showRematchBtn() {}, applyDoublesPlayerOrderAfterSave() {},
        window: {
            showSavedGamePopup: (receipt, pending) => {
                if (pending) {
                    assert.equal(receipt.title, 'Women’s Doubles');
                    assert.equal(receipt.winners, 'winner1 & winner2');
                    assert.equal(receipt.losers, 'loser1 & loser2');
                    for (const key of ['winner_score', 'loser_score', 'location']) assert.equal(receipt[key], key);
                    assert.equal(receipt.comment, 'comments');
                    calls.push('pending');
                } else {
                    assert.equal(receipt.title, 'Doubles');
                    calls.push('popup');
                }
            },
            showSavedGameError: message => { assert.ok(message); calls.push('error'); },
        },
        // Intentionally never resolves: showing the receipt must not await it.
        refreshTodaysDoublesDashboard: () => { calls.push('stats'); return new Promise(() => {}); },
    };
    vm.runInNewContext(submit, context);
    const event = { preventDefault() {} };
    const saving = form.submit(event);
    await form.submit(event);
    assert.deepEqual(calls, ['pending', 'save'], 'Popup opens before the request; repeated submit must not save twice');
    assert.equal(fields['add-game-submit-btn'].disabled, true);
    assert.equal(fields['add-game-submit-btn'].textContent, 'Submit');
    finish();
    await saving;
    assert.equal(fields['add-game-submit-btn'].disabled, false);
    assert.equal(form.dataset.saving, 'false');
    return calls;
}

function checkPopup() {
    const template = fs.readFileSync(path.join(root, 'templates/partials/saved_game_popup.html'), 'utf8');
    const script = template.split('<script>')[1].split('</script>')[0].replace(/\{% if saved_game %\}.*?\{% endif %\}/g, '');
    let dropdownOpen = false;
    let stopped = false;
    const field = {
        focus() {}, // Already focused after dialog.close(): no native focus event.
        dispatchEvent(event) { assert.equal(event.type, 'focus'); dropdownOpen = true; },
        scrollIntoView() {},
    };
    const content = ['title', 'winners', 'losers', 'winner_score', 'loser_score', 'location', 'comment']
        .map(key => ({ dataset: { savedGame: key } }));
    const listeners = {};
    const popup = { open: false, close() { this.open = false; }, showModal() { this.open = true; },
        getBoundingClientRect: () => ({ left: 0, right: 10, top: 0, bottom: 10 }),
        querySelectorAll: () => content, addEventListener(name, handler) { listeners[name] = handler; } };
    const add = { focus() {} };
    const done = { focus() {} };
    const heading = { focus() {} };
    const status = {};
    const elements = { 'saved-game-popup': popup, 'saved-game-add-another': add,
        'saved-game-close': done, 'saved-game-title': heading, 'saved-game-status': status };
    const context = { window: {}, Event: class { constructor(type) { this.type = type; } },
        document: { getElementById: id => elements[id],
            querySelector: () => field } };
    vm.runInNewContext(script, context);
    context.window.showSavedGamePopup({ winners: 'Alice & Bob' }, true);
    assert.equal(popup.open, true);
    assert.equal(heading.textContent, 'Saving game…');
    assert.equal(add.disabled, true);
    assert.equal(done.disabled, true);
    let cancelled = false;
    listeners.cancel({ preventDefault() { cancelled = true; } });
    assert.equal(cancelled, true, 'Escape must not hide an unfinished save');
    listeners.click({ target: popup, clientX: -1, clientY: -1 });
    done.onclick();
    add.onclick({});
    assert.equal(popup.open, true);
    context.window.showSavedGameError('Your entry is still here.');
    assert.equal(heading.textContent, 'Save not confirmed');
    assert.equal(status.textContent, 'Your entry is still here.');
    assert.equal(status.hidden, false);
    assert.equal(add.hidden, true);
    assert.equal(done.disabled, false);
    assert.equal(done.textContent, 'Back to game');
    done.onclick();
    assert.equal(popup.open, false);
    context.window.showSavedGamePopup({ title: 'Doubles' }, true);
    assert.equal(status.hidden, true, 'Retry clears the old error');
    assert.equal(add.hidden, false);
    context.window.showSavedGamePopup({ title: 'Doubles', winners: '<script>unsafe</script>', winner_score: 0 });
    assert.equal(heading.textContent, 'Game added');
    assert.equal(add.disabled, false);
    assert.equal(done.disabled, false);
    assert.equal(popup.open, true);
    assert.equal(content[1].textContent, '<script>unsafe</script>');
    assert.equal(content[3].textContent, 0);
    assert.equal(content[5].hidden, true);
    add.onclick({ stopPropagation() { stopped = true; } });
    // Model the page's outside-click handler, which closes lists if the click bubbles.
    if (!stopped) dropdownOpen = false;
    assert.equal(popup.open, false);
    assert.equal(dropdownOpen, true, 'Add another must leave the dropdown visible');
}

(async () => {
    assert.deepEqual(await checkSave({ ok: true, json: async () => ({ saved_game: { title: 'Doubles' } }) }), ['pending', 'save', 'clear', 'popup', 'stats']);
    assert.deepEqual(await checkSave({ ok: false, json: async () => ({ error: 'All fields required!' }) }), ['pending', 'save', 'error']);
    assert.deepEqual(await checkSave(null, true), ['pending', 'save', 'error']);
    assert.deepEqual(await checkSave({ ok: true, json: async () => { throw new Error('Invalid response'); } }), ['pending', 'save', 'error']);
    checkPopup();
    console.log('Popup opens before save; pending saves stay visible; failures preserve entry; confirmed saves enable Add another.');
})().catch(error => { console.error(error); process.exitCode = 1; });
