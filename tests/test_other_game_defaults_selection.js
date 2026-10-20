const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const template = fs.readFileSync('templates/add_other_game.html', 'utf8');
const source = template.slice(template.indexOf("setupAutocomplete('game_name'"), template.indexOf('// Game type: on select')).replaceAll("{{ url_for('add_vollis_game') | tojson }}", JSON.stringify('/add_vollis_game/'));
let select, applied;
const requests = [];
const field = {value: 'No jump', setCustomValidity(message) { this.validationMessage = message; }};
const type = {value: ''};
let resolveInfo;
const context = {
    isOneOnOne: false, allGameNames: [], gameEntryDefaults: {'no jump': {game_type: 'Volleyball', score_type: 'team'}},
    setupAutocomplete: (_, __, callback) => {select = callback;},
    fetch: url => { requests.push(url); return new Promise(resolve => {resolveInfo = resolve;}); },
    window: {location: {href: ''}},
    document: {getElementById: id => id === 'game_type' ? type : ({addEventListener: () => {}})},
    applyGameInfo: data => {applied = data;}, updateClearVisibility: () => {}, setTimeout: () => {},
};
vm.runInNewContext(source, context);
select(field);
assert.equal(type.value, 'Volleyball');
assert.equal(applied.score_type, 'team');
assert.equal(requests.some(url => url.includes('other_game_info')), false, 'Known game must fill before any network response');
field.value = ' vOlLiS ';
const requestsBeforeVollis = requests.length;
select(field);
assert.equal(context.window.location.href, '/add_vollis_game/');
assert.equal(requests.length, requestsBeforeVollis, 'Vollis must use its own entry form and history');
field.value = 'New game';
select(field);
assert.equal(requests.at(-1), '/api/other_game_info/New%20game');
field.value = 'No jump';
resolveInfo({json: () => ({game_type: 'Old response', score_type: 'individual'})});
setImmediate(() => {
    assert.equal(type.value, 'Volleyball', 'Stale response must not replace current selection');
    context.isOneOnOne = true;
    context.allGameNames = ['Vollis', 'Italian short court'];
    context.gameEntryDefaults['italian short court'] = {game_type: 'Old category', score_type: 'team'};
    field.value = '  italian SHORT court  ';
    select(field);
    assert.equal(field.value, 'Italian short court');
    assert.equal(field.validationMessage, '');
    assert.equal(type.value, 'Volleyball');
    assert.equal(applied.score_type, 'team');
    assert.equal(context.window.location.href, '/add_vollis_game/', 'Non-Vollis selection stays on the current form');
    field.value = '  New lefty format  ';
    select(field);
    assert.equal(field.value, 'New lefty format');
    assert.equal(field.validationMessage, '');
    assert.equal(type.value, 'Volleyball');
    assert.equal(requests.at(-1), '/api/other_game_info/New%20lefty%20format');
    console.log('Known defaults apply immediately; unknown games fetch; stale responses are ignored.');
});
