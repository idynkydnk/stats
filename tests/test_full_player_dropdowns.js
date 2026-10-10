const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

for (const [template, fields] of [
    ['add_game.html', ['winner1', 'winner2', 'loser1', 'loser2']],
    ['add_vollis_game.html', ['winner', 'loser']],
    ['add_other_game.html', ['winner1', 'loser1', 'winner15', 'loser15']],
]) {
    const html = fs.readFileSync(`templates/${template}`, 'utf8');
    assert.ok(html.includes("filename='js/player-suggestions.js'"));
    const start = html.indexOf('function showList(');
    const source = html.slice(start, html.indexOf('\n}', start) + 2);
    const players = Array.from({length: 40}, (_, i) => `Player ${i}`);
    const list = {style: {}, rows: [], appendChild(row) {this.rows.push(row.textContent);}};
    const context = {
        nameFields: fields,
        document: {querySelectorAll: () => [], createElement: () => ({})},
        requestAnimationFrame: callback => callback(),
    };
    vm.createContext(context);
    vm.runInContext(fs.readFileSync('static/js/player-suggestions.js', 'utf8'), context);
    vm.runInContext(source, context);
    for (const id of fields) {
        list.rows = [];
        context.showList({id, value: ''}, list, players);
        assert.deepEqual(list.rows, players.slice(0, 8), `${template} ${id} must show eight players`);
        assert.equal(list.style.display, 'block');
        list.rows = [];
        context.showList({id, value: 'Player 39'}, list, players);
        assert.deepEqual(list.rows, ['Player 39'], 'Search must include players beyond the first eight');
        list.rows = [];
        context.showList({id, value: ' t '}, list,
            ['Stanton Smith', 'Matt', 'Trent Linguen', 'Tyler Weston', 'Taylor', 'Tom', 'Ted', 'Tim', 'Tony', 'Toby', 'Alice']);
        assert.deepEqual(list.rows, ['Trent Linguen', 'Tyler Weston', 'Taylor', 'Tom', 'Ted', 'Tim', 'Tony', 'Toby'],
            'Prefix matches must fill the eight slots before substring matches');
        list.rows = [];
        context.showList({id, value: 'T'}, list, ['Stanton Smith', 'Matt', 'Trent Linguen', 'Tyler Weston', 'Alice']);
        assert.deepEqual(list.rows, ['Trent Linguen', 'Tyler Weston', 'Stanton Smith', 'Matt']);
        list.rows = [];
        context.showList({id, value: 'No match'}, list, players);
        assert.deepEqual(list.rows, []);
        assert.equal(list.style.display, 'none');
    }
}
console.log('All player dropdowns search the full roster, show eight entries, and rank starts-with matches first.');
