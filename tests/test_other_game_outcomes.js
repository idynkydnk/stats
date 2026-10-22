// Run with: node tests/test_other_game_outcomes.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const fields = [];
function playerField(name) {
    const clear = {setAttribute(key, value) {this[key] = value;}};
    return {name, parentElement: {querySelector: () => clear},
        setAttribute(key, value) {this[key] = value;}, clear};
}
for (const side of ['winner', 'loser']) {
    fields.push(playerField(side + '1'), playerField(side + '_score'));
}
const handlers = {};
const form = {addEventListener(event, callback) {handlers[event] = callback;}, querySelectorAll(selector) {
    return fields.filter(field => field.name.startsWith(selector.includes('winner') ? 'winner' : 'loser'));
}};
const resultField = {dataset: {oneOnOne: '0'}};
const gameType = {value: 'Board game'};
const result = {value: '0', setCustomValidity(message) {this.validationMessage = message;}, reportValidity() {this.reported = true;}, closest: selector => selector === 'form' ? form : resultField, addEventListener(_, fn) {this.change = fn;}};
const clear = {addEventListener(_, fn) {this.click = fn;}};
const help = {};
const elements = {score_type: {value: 'team'}, winner_score: {value: '1'}, loser_score: {value: '1'}, is_tie: result, game_type: gameType, 'tie-help': help, 'clear-form-btn': clear,
    'add-winner-btn': {}, 'add-loser-btn': {}};
let mutation;
vm.runInNewContext(fs.readFileSync('static/js/other-game-outcomes.js', 'utf8'), {
    window: {},
    document: {getElementById: id => elements[id]},
    MutationObserver: class {constructor(callback) {mutation = callback;} observe(target) {assert.equal(target, form);}},
});
assert.equal(fields[0].placeholder, 'Winner 1');
assert.equal(help.hidden, true);
result.value = '1';
result.change();
assert.equal(help.hidden, false);
assert.equal(fields[0].placeholder, 'Side 1 player 1');
assert.equal(fields[1].placeholder, 'Side 1 Score');
assert.equal(fields[2]['aria-label'], 'Side 2 player 1');
assert.equal(fields[0].clear['aria-label'], 'Clear side 1 player 1');
assert.equal(elements['add-loser-btn'].textContent, '+ Add Side 2 Player');
fields.push(playerField('loser3'));
mutation();
assert.equal(fields[4].placeholder, 'Side 2 player 3', 'New player rows retain tie labels');
clear.click();
assert.equal(result.value, '0');
assert.equal(help.hidden, true);
assert.equal(fields[4].placeholder, 'Loser 3');
assert.equal(elements['add-winner-btn'].textContent, '+ Add Winner');
result.value = '1';
result.change();
gameType.value = ' Beach VoLlEyBaLl ';
handlers.change();
assert.equal(resultField.hidden, true, 'Volleyball has no tie option');
assert.equal(result.value, '0', 'Switching to volleyball clears a prior tie');
assert.equal(fields[0].placeholder, 'Winner 1');
gameType.value = 'Board game';
handlers.input();
assert.equal(resultField.hidden, false);
assert.equal(result.value, '0', 'Returning to a board game does not restore a stale tie');
let prevented = false;
handlers.submit({preventDefault() {prevented = true;}});
assert.equal(prevented, true, 'Equal team scores require choosing Tie before submission');
assert.match(result.validationMessage, /Choose Tie/);
result.value = '1';
result.change();
assert.equal(result.validationMessage, '');
prevented = false;
handlers.submit({preventDefault() {prevented = true;}});
assert.equal(prevented, false, 'Explicit 1–1 tie can submit');
resultField.dataset.oneOnOne = '1';
gameType.value = '';
handlers.input();
assert.equal(resultField.hidden, true, '1v1 keeps ties hidden even while the game type is blank');
assert.equal(result.value, '0');
clear.click();
assert.equal(resultField.hidden, true, 'Clearing a 1v1 form never reveals ties');
console.log('Tie labels update existing and newly added players, and Clear form resets the result.');
