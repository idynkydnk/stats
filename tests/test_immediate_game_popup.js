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
    const fields = Object.fromEntries(['client_date', 'client_time', 'entered_timezone', 'winner1', 'winner2', 'loser1', 'loser2', 'add-game-submit-btn'].map(id => [id, { value: id }]));
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
        window: { showSavedGamePopup: receipt => { assert.equal(receipt.title, 'Doubles'); calls.push('popup'); } },
        // Intentionally never resolves: showing the receipt must not await it.
        refreshTodaysDoublesDashboard: () => { calls.push('stats'); return new Promise(() => {}); },
        alert: message => { assert.ok(message); calls.push('error'); },
    };
    vm.runInNewContext(submit, context);
    const event = { preventDefault() {} };
    const saving = form.submit(event);
    await form.submit(event);
    assert.deepEqual(calls, ['save'], 'Repeated submit must not save twice');
    assert.equal(fields['add-game-submit-btn'].disabled, true);
    finish();
    await saving;
    assert.equal(fields['add-game-submit-btn'].disabled, false);
    assert.equal(form.dataset.saving, 'false');
    return calls;
}

function checkAddAnother() {
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
    const popup = { open: false, close() { this.open = false; }, showModal() { this.open = true; },
        querySelectorAll: () => content, addEventListener() {} };
    const add = {};
    const context = { window: {}, Event: class { constructor(type) { this.type = type; } },
        document: { getElementById: id => id === 'saved-game-popup' ? popup : id === 'saved-game-add-another' ? add : {},
            querySelector: () => field } };
    vm.runInNewContext(script, context);
    context.window.showSavedGamePopup({ title: 'Doubles', winners: '<script>unsafe</script>', winner_score: 0 });
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
    assert.deepEqual(await checkSave({ ok: true, json: async () => ({ saved_game: { title: 'Doubles' } }) }), ['save', 'clear', 'popup', 'stats']);
    assert.deepEqual(await checkSave({ ok: false, json: async () => ({ error: 'All fields required!' }) }), ['save', 'error']);
    assert.deepEqual(await checkSave(null, true), ['save', 'error']);
    checkAddAnother();
    console.log('Receipt appears before stats refresh; failures preserve entry; Add another opens dropdown.');
})().catch(error => { console.error(error); process.exitCode = 1; });
