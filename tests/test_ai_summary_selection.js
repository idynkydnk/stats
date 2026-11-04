const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const template = fs.readFileSync(path.join(__dirname, '../templates/ai_summary.html'), 'utf8');
const source = template.slice(template.indexOf('        function firstBrowseDay('), template.indexOf('        function selectNone('));
function card(day, checked = false) {
    const checkbox = { checked };
    const classes = new Set(checked ? ['selected'] : ['sr-hidden-game']);
    return { dataset: { gameDay: day }, checkbox,
        querySelector: () => checkbox,
        classList: { remove: name => classes.delete(name), add: name => classes.add(name),
            toggle: (name, on) => on ? classes.add(name) : classes.delete(name) } };
}
const cards = Array.from({ length: 65 }, () => card('2026-09-12'));
cards.push(card('2026-09-11', true));
cards.forEach((c, i) => { c.dataset.gameId = String(i); });
const tab = { querySelector: () => cards[0], querySelectorAll: () => cards };
let updates = 0;
const selectedGames = new Set(['doubles:65', 'other:0']);
const context = { selectedGames, selectionKey: c => 'doubles:' + c.dataset.gameId, currentTab: 'doubles', searchMode: false, searchRequestId: 0, selectAllIds: {doubles: cards.slice(0, 65).map(c => c.dataset.gameId)},
    showBrowseMode: () => { context.searchMode = false; },
    document: { getElementById: () => tab }, updateSelectedCount: () => { updates++; cards.forEach(c => { c.checkbox.checked = selectedGames.has('doubles:' + c.dataset.gameId); }); },
    visibleCards: () => cards.slice(0, 2) };
vm.createContext(context);
vm.runInContext(source, context);
context.selectAll();
assert.equal(cards.filter(c => c.checkbox.checked).length, 65);
assert.equal(cards[65].checkbox.checked, false, 'Older manually selected games must be cleared');
cards.forEach(c => { c.checkbox.checked = false; });
context.searchMode = true;
context.selectAll();
assert.equal(cards.filter(c => c.checkbox.checked).length, 65);
assert.equal(updates, 2);
context.searchMode = false;
cards.length = 0;
context.selectAll();
console.log('Select All covers the full latest day, clears older choices, and uses the same owned games during search, and handles empty lists.');

// Kyle can browse newer submissions and same-day games belonging to others.
context.selectAllIds = {doubles: ['own1', 'own2']};
cards.push(card('2026-09-24'), card('2026-09-23'), card('2026-09-23'), card('2026-09-23'));
['dan-new', 'own1', 'dan-same-day', 'own2'].forEach((id, i) => { cards[i].dataset.gameId = id; });
context.selectAll();
assert.deepEqual(cards.filter(c => c.checkbox.checked).map(c => c.dataset.gameId), ['own1', 'own2']);
context.selectAllIds = {doubles: []};
context.selectAll();
assert.equal(cards.filter(c => c.checkbox.checked).length, 0);
context.searchMode = true;
context.selectAll();
assert.equal(cards.filter(c => c.checkbox.checked).length, 0, 'Search must not select other users or older games');
console.log('Kyle browsing everyone preserves own-day Select All; search also respects ownership.');

assert(selectedGames.has('other:0'), 'Select All must preserve selections on other tabs');
const selectionSource = template.slice(template.indexOf('        function selectNone('), template.indexOf('        function toggleExpand('));
vm.runInContext(selectionSource, context);
context.selectNone();
assert(selectedGames.has('other:0'), 'Select None only clears the current tab');
// Exercise the actual shared selection and tab-switch code with a minimal DOM.
const state = { document: {
    querySelectorAll: () => [],
    querySelector: () => ({classList: {add() {}}}),
    getElementById: () => ({style: {}, value: ''}),
}, searchRequestId: 0, searchTimer: null, clearTimeout() {},
updateSearchPlaceholder() {}, showBrowseMode() {}, updateSelectedCount() {} };
vm.createContext(state);
vm.runInContext(template.slice(template.indexOf("let currentTab ="), template.indexOf('        const selectAllIds')), state);
vm.runInContext(template.slice(template.indexOf('        function switchTab('), template.indexOf('        function updateSelectedCount(')), state);
vm.runInContext(`
rememberSelection({dataset: {gameType: 'doubles', gameId: '1'}}, true);
switchTab('other');
rememberSelection({dataset: {gameType: 'other', gameId: '1'}}, true);
switchTab('doubles');
if (selectedGames.size !== 2 || !selectedGames.has('doubles:1') || !selectedGames.has('other:1')) throw Error('Tab selection lost');
`, state);
console.log('Cross-tab selections survive switching and colliding IDs.');
