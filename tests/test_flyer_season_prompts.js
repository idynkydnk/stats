// Run with: node tests/test_flyer_season_prompts.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../templates/create_flyer.html'), 'utf8');
const method = source.slice(source.indexOf('    function applyFetchedPrompts('),
                            source.indexOf('    function fetchPrompts('));
const context = {
    dirtyScene: true, dirtySolos: {}, soloPromptValues: {},
    scenePromptEl: {value: 'My sunset design.\n[CURRENT-YEAR DOUBLES STATS]Old year[/CURRENT-YEAR DOUBLES STATS]'},
    renderSoloPromptFields() {},
};
vm.runInNewContext(method, context);
function refresh(block, force = false) {
    context.applyFetchedPrompts({scene_prompt: 'Default design.\n' + block}, force);
    return context.scenePromptEl.value;
}

let prompt = refresh('[SEASON STATS]Winter: 2 wins[/SEASON STATS]');
assert(prompt.includes('My sunset design.'));
assert(prompt.includes('Winter: 2 wins'));
assert(!prompt.includes('Old year'));
assert(!prompt.includes('Default design.'));

prompt = refresh('[SEASON STATS]Summer: 3 wins[/SEASON STATS]');
assert(!prompt.includes('Winter: 2 wins'));
assert.equal(prompt.match(/\[SEASON STATS\]/g).length, 1);
assert(context.dirtyScene, 'Changing season preserves custom design edits');

prompt = refresh('[CURRENT-YEAR DOUBLES STATS]Year: 5 wins[/CURRENT-YEAR DOUBLES STATS]');
assert(!prompt.includes('SEASON STATS'));
assert(prompt.includes('Year: 5 wins'));

assert.equal(refresh(''), 'My sunset design.', 'A sport with no default stats removes stale stats');
assert.equal(refresh('[SEASON STATS]Winter[/SEASON STATS]', true),
             'Default design.\n[SEASON STATS]Winter[/SEASON STATS]');
assert(!context.dirtyScene, 'Reload defaults still replaces the design');
console.log('Flyer season prompt checks passed.');
