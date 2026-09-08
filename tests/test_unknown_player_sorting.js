// Run with: node tests/test_unknown_player_sorting.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = { window: {}, document: { addEventListener() {} } };
vm.createContext(context);
vm.runInContext(fs.readFileSync(require('node:path').join(__dirname, '../static/js/stats.js'), 'utf8'), context);

for (const nameKey of ['partner', 'opponent', 'player']) {
    const headers = ['rank', nameKey, 'winpct', 'wins', 'losses', 'games'].map((sort, cellIndex) => ({ dataset: { sort }, cellIndex }));
    function makeRow(name, games, wins, rank, hidden) {
        const classes = new Set(hidden ? ['sr-hidden'] : []);
        const cells = [rank, name, wins / games, wins, games - wins, games].map(value => ({
            textContent: String(value), dataset: { value: String(value) }, querySelector() { return null; },
        }));
        return { cells, dataset: { games: String(games) },
            classList: { contains: c => classes.has(c), add: c => classes.add(c), remove: c => classes.delete(c) },
            querySelector: () => cells[0] };
    }
    for (const direction of ['asc', 'desc']) {
        for (const column of [-1, 0, 1, 2, 3, 4, 5]) {
            let rows = [makeRow('??? ???', 1000, 1000, 1, false), makeRow('Alice', 1, 0, 2, false), makeRow('Bob', 10, 5, 3, true)];
            const tbody = { querySelectorAll: () => rows.slice(), appendChild(row) { rows = rows.filter(r => r !== row); rows.push(row); } };
            const table = { dataset: { collapseLimit: '2', winpctMinGames: '5' },
                querySelector: () => tbody, querySelectorAll: () => headers,
                classList: { contains: () => false } };
            context.sortTable(table, column, direction, column !== 1 && column !== -1);
            assert.equal(rows[2].cells[1].textContent, '??? ???');
            assert.equal(rows[2].classList.contains('sr-hidden'), true);
            assert.deepEqual(rows.map(r => Number(r.cells[0].textContent)), [1, 2, 3]);
            if (column === -1) assert.deepEqual(rows.map(r => r.cells[1].textContent), ['Alice', 'Bob', '??? ???']);
        }
    }
}
console.log('Unknown players stay last for all columns and directions.');
