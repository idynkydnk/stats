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
const tab = { querySelector: () => cards[0], querySelectorAll: () => cards };
let updates = 0;
const context = { currentTab: 'doubles', searchMode: false,
    document: { getElementById: () => tab }, updateSelectedCount: () => updates++,
    visibleCards: () => cards.slice(0, 2) };
vm.createContext(context);
vm.runInContext(source, context);
context.selectAll();
assert.equal(cards.filter(c => c.checkbox.checked).length, 65);
assert.equal(cards[65].checkbox.checked, false, 'Older manually selected games must be cleared');
cards.forEach(c => { c.checkbox.checked = false; });
context.searchMode = true;
context.selectAll();
assert.equal(cards.filter(c => c.checkbox.checked).length, 2);
assert.equal(updates, 2);
context.searchMode = false;
cards.length = 0;
context.selectAll();
console.log('Select All covers the full latest day, clears older choices, and handles search and empty lists.');
