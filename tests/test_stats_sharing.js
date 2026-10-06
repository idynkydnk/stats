const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

let ready, click, copied, fallback;
const label = {textContent: 'Copy link'};
const button = {
    addEventListener: (event, callback) => { click = callback; },
    querySelector: () => label,
};
const context = vm.createContext({
    URL,
    document: {
        addEventListener: (event, callback) => { ready = callback; },
        querySelectorAll: () => [button],
    },
    window: {
        location: {
            href: 'https://stats.example/stats/2026/?view=signed-token&location=Beach&division=womens',
            origin: 'https://stats.example',
        },
        prompt: (message, url) => { fallback = url; },
    },
    navigator: {clipboard: {writeText: async url => { copied = url; }}},
    setTimeout: () => {},
});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../static/js/stats-sharing.js'), 'utf8'), context);

(async function () {
    ready();
    await click();
    assert.equal(copied, context.window.location.href);
    assert.equal(label.textContent, 'Copied!');
    context.navigator.clipboard.writeText = async () => { throw new Error('Denied'); };
    await click();
    assert.equal(fallback, context.window.location.href);
    assert.equal(context.statsViewURL('/api/search_all_players?q=Dan'),
        '/api/search_all_players?q=Dan&view=signed-token');
    assert.equal(context.statsViewURL('/player/2026/Dan/#games'),
        '/player/2026/Dan/?view=signed-token#games');
    console.log('Stats links preserve the selected view, filters, and clipboard fallback.');
})().catch(error => { console.error(error); process.exitCode = 1; });
