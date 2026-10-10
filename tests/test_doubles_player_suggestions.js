// Run with: node tests/test_doubles_player_suggestions.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const template = fs.readFileSync(require('node:path').join(__dirname, '../templates/add_game.html'), 'utf8');
const refresh = template.slice(template.indexOf('function refreshDoublesPlayersFromServer()'),
    template.indexOf('/** Put winner1'));
const startup = template.slice(template.indexOf("document.addEventListener('DOMContentLoaded', function()"),
    template.indexOf('function toggleAllGames()'));
const filtering = template.slice(template.indexOf('function setupAutocomplete('),
    template.indexOf("nameFields.forEach", template.indexOf('function setupAutocomplete(')));

async function checkRefresh(query, fail = false) {
    const handlers = {};
    const field = { id: 'winner1', value: query,
        addEventListener(type, handler) { handlers[type] = handler; },
        dispatchEvent(event) { handlers[event.type](); } };
    const list = { style: {}, addEventListener() {} };
    const roster = { options: [], appendChild(option) { this.options.push(option); } };
    let loaded, requested, shown;
    const names = [...Array.from({ length: 15 }, (_, i) => `Recent Player ${i}`), 'Trent Goldman'];
    const context = {
        allPlayers: ['John Moran'], nameFields: ['winner1', 'winner2', 'loser1', 'loser2'],
        Event: class { constructor(type) { this.type = type; } },
        document: { activeElement: field,
            getElementById: id => ({ players: roster, winner1: field, winner1List: list })[id],
            createElement: () => ({}),
            addEventListener(type, handler) { assert.equal(type, 'DOMContentLoaded'); loaded = handler; } },
        fetch: async (url, options) => {
            requested = { url, options };
            if (fail) throw new Error('offline');
            return { ok: true, json: async () => names };
        },
        setTimeout() {},
        showList: (_, __, items) => { shown = items; },
        filterList: (_, __, items, predicate) => { shown = items.filter(predicate); },
    };
    vm.createContext(context);
    vm.runInContext(refresh + filtering + startup, context);
    vm.runInContext("setupAutocomplete('winner1', function() { return allPlayers; });", context);
    loaded();
    await new Promise(resolve => setImmediate(resolve));
    assert.ok(requested.url.startsWith('/api/doubles_players?division='));
    assert.equal(requested.options.credentials, 'same-origin');
    if (fail) {
        assert.deepEqual(context.allPlayers, ['John Moran'], 'Network failure preserves existing names');
    } else {
        assert.deepEqual(context.allPlayers, names);
        assert.deepEqual(roster.options.map(option => option.value), names);
        assert.deepEqual(shown, query ? ['Trent Goldman'] : names,
            'Already focused fields refresh and search the full shared roster');
        assert.equal(field.value, query, 'Loading suggestions preserves typed input');
    }
}

(async () => {
    await checkRefresh('Trent');
    await checkRefresh('');
    await checkRefresh('Trent', true);
    console.log('Doubles loads shared suggestions on page open, refreshes active search, and preserves names offline.');
})().catch(error => { console.error(error); process.exitCode = 1; });
