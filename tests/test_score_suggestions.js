const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const helper = fs.readFileSync('static/js/score-suggestions.js', 'utf8');
const expected = ['2', ...Array.from({length: 10}, (_, i) => String(20 + i))];

for (const template of ['add_game.html', 'add_vollis_game.html']) {
    const html = fs.readFileSync(`templates/${template}`, 'utf8');
    const field = {id: 'winner_score', value: '', handlers: {}, addEventListener(event, fn) { this.handlers[event] = fn; }};
    const list = {style: {}, addEventListener() {}};
    let shown;
    const context = {
        document: {getElementById: id => id === 'winner_score' ? field : list},
        showList: (_, __, items) => { shown = Array.from(items); },
        filterList: (_, __, items, predicate) => { shown = Array.from(items.filter(predicate)); },
    };
    vm.createContext(context);
    vm.runInContext(helper, context);
    const start = html.indexOf('function setupAutocomplete(');
    vm.runInContext(html.slice(start, html.indexOf('\n}', start) + 2), context);
    context.setupAutocomplete('winner_score', field => context.winnerScoreSuggestions(field.value, ['21', '15']));
    field.handlers.focus();
    assert.deepEqual(shown, ['21', '15']);
    field.value = '2'; field.handlers.input();
    assert.deepEqual(shown, expected, `${template}: typing 2 must show all prefix matches`);
    field.value = '20'; field.handlers.input();
    assert.deepEqual(shown, ['20']);
    field.value = ''; field.handlers.input();
    assert.deepEqual(shown, ['21', '15']);
}

const html = fs.readFileSync('templates/add_other_game.html', 'utf8');
let pending, shown;
const context = {
    document: {activeElement: null, getElementById: id => id === 'score_type' ? {value: 'individual'} : {style: {}, innerHTML: 'scores'}},
    fetchCommonScoresThen: callback => { pending = callback; },
    showScoreList: (_, scores) => { shown = Array.from(scores); },
};
vm.createContext(context);
vm.runInContext(helper, context);
vm.runInContext(html.slice(html.indexOf('let _currentScoreInput = null;'), html.indexOf('function getSelectedPlayers(')), context);
for (const id of ['winner_score', 'winner1_score', 'winner15_score']) {
    const field = {id, name: id, value: '2', getBoundingClientRect: () => ({bottom: 0, left: 0, width: 100})};
    context.document.activeElement = field;
    context.openCommonScoreDropdown(field);
    assert.deepEqual(shown, expected, `Other games ${id}: prefix choices must appear immediately`);
    field.value = ''; context.openCommonScoreDropdown(field);
    field.value = '2'; context.openCommonScoreDropdown(field);
    pending({winner_individual_scores: [21, 15]});
    assert.deepEqual(shown, expected, 'Late common-score results must respect the current typed prefix');
    context.document.activeElement = null;
    shown = [];
    pending({winner_individual_scores: [21, 15]});
    assert.deepEqual(shown, [], 'Late results must not reopen a blurred dropdown');
}
console.log('Winner score typing, clearing, dynamic fields, and delayed responses passed.');
