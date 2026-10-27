const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const template = fs.readFileSync(require('node:path').join(__dirname, '../templates/add_other_game.html'), 'utf8');
const slice = (start, end) => template.slice(template.indexOf(start), template.indexOf(end));
const fields = {};
const pending = new Map();
const requests = [];
let selectFormat;
let shown = [];
let layout;
let displayScores = [];
const context = {
    isOneOnOne: true, allPlayers: ['Saved player', 'Opponent'], allGameNames: ['Italian short court', 'Half court long ways'],
    cachedPlayerOrder: null, cachedPlayerOrderGame: null, gameEntryDefaults: {},
    Map, Number, Math, Array, Event: class { constructor(type) { this.type = type; } },
    window: {updateOtherGameOutcome() {}},
    document: {activeElement: null, getElementById: id => fields[id]},
    fetch(url) {
        requests.push(url);
        return new Promise(resolve => pending.set(url, data => resolve({ok: true, json: async () => data})));
    },
    setupAutocomplete(id, getItems, onSelect) { selectFormat = onSelect; },
    updateClearVisibility() {},
    applyGameInfo(info) { layout = info; fields.score_type.value = info.score_type; },
    getSelectedPlayers: () => [],
    showList: (field, list, items) => { shown = items; },
    showScoreList(list, scores) { displayScores = Array.from(scores); list.innerHTML = scores.join(','); },
    setTimeout(fn) { fn(); },
};
function field(id, value = '') {
    const handlers = {};
    return fields[id] = {id, value, style: {}, innerHTML: '',
        setCustomValidity() {}, addEventListener(event, fn) { handlers[event] = fn; },
        focus() { context.document.activeElement = this; handlers.focus?.(); },
        dispatchEvent(event) { handlers[event.type]?.(); },
        getBoundingClientRect: () => ({bottom: 20, left: 0, width: 100})};
}
for (const id of ['game_name', 'game_type', 'winner1', 'winner1List', 'score_type', 'winner_score', 'loser_score', 'common_score_dropdown']) field(id);
vm.createContext(context);
vm.runInContext(fs.readFileSync(require('node:path').join(__dirname, '../static/js/score-suggestions.js'), 'utf8'), context);
vm.runInContext(slice('function getPlayerListForAutocomplete()', '\nfunction showScoreList'), context);
vm.runInContext(slice('function setupPlayerAutocomplete(', '\nfunction apply2v2Layout'), context);
vm.runInContext(slice('// Populate Winner immediately', "\ndocument.getElementById('game_name').addEventListener('input'").replace(/{{.*?}}/g, "'/vollis'"), context);
vm.runInContext(slice('let _currentScoreInput', '\nfunction getSelectedPlayers'), context);
vm.runInContext("setupPlayerAutocomplete(document.getElementById('winner1'), document.getElementById('winner1List'));", context);
const settle = () => new Promise(resolve => setImmediate(resolve));
(async () => {
    fields.game_name.value = 'Italian short court';
    selectFormat(fields.game_name);
    assert.equal(context.document.activeElement, fields.winner1, 'Winner focuses before requests resolve');
    assert.deepEqual(shown, ['Saved player', 'Opponent'], 'Existing roster appears immediately');
    assert.equal(layout.score_type, 'team');
    assert.ok(!requests.some(url => url.includes('other_game_info')), '1v1 never waits for layout settings');
    pending.get('/api/other_game_players/Italian%20short%20court')(['Recent player', 'Opponent']);
    await settle();
    assert.deepEqual(shown, ['Recent player', 'Opponent'], 'Focused empty dropdown refreshes in place');
    fields.winner1.value = 'Opp';
    fields.winner1.dispatchEvent(new context.Event('input'));
    assert.deepEqual(shown, ['Opponent']);

    fields.winner_score.value = '11';
    fields.loser_score.focus();
    const count = requests.length;
    vm.runInContext("openCommonScoreDropdown(document.getElementById('loser_score'));", context);
    assert.deepEqual(displayScores, [9,8,7,6,5,4,3,2,1,0]);
    assert.equal(requests.length, count, 'Loser scores appear while common-score request is still pending');
    fields.winner_score.value = '15';
    vm.runInContext("openCommonScoreDropdown(document.getElementById('loser_score'));", context);
    assert.equal(displayScores[0], 13);

    fields.winner_score.value = '';
    fields.winner_score.focus();
    vm.runInContext("openCommonScoreDropdown(document.getElementById('winner_score'));", context);
    assert.equal(requests.filter(url => url.includes('other_game_common_scores')).length, 1, 'Prefetch and focus share a request');
    fields.game_name.value = 'Half court long ways';
    selectFormat(fields.game_name);
    fields.winner_score.focus();
    vm.runInContext("openCommonScoreDropdown(document.getElementById('winner_score'));", context);
    pending.get('/api/other_game_common_scores/Half%20court%20long%20ways?one_on_one=1')({winner_scores: [11,12,16]});
    await settle();
    assert.deepEqual(displayScores, [11,12,16]);
    pending.get('/api/other_game_common_scores/Italian%20short%20court?one_on_one=1')({winner_scores: [15,21]});
    await settle();
    assert.deepEqual(displayScores, [11,12,16], 'Late scores from previous format cannot replace current suggestions');
    fields.winner_score.value = '2';
    vm.runInContext("openCommonScoreDropdown(document.getElementById('winner_score'));", context);
    assert.ok(displayScores.includes('21') && displayScores.includes('29'), 'Typed scores remain available');
    console.log('1v1: immediate players, format defaults, background refresh, score ranking, countdown, typing, and stale responses passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
