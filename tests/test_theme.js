// Run with: node tests/test_theme.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../static/js/theme.js'), 'utf8');
function boot(saved = {}, unavailable = false) {
    const values = { ...saved }, attributes = {}, classes = new Set(), events = {}, windowEvents = {};
    const controls = ['mode', 'palette', 'style'].map(name => ({ value: '', getAttribute: () => name }));
    const context = {
        document: {
            readyState: 'loading',
            documentElement: {
                classList: { toggle(name, enabled) { enabled ? classes.add(name) : classes.delete(name); } },
                setAttribute(name, value) { attributes[name] = value; }
            },
            addEventListener(name, fn) { events[name] = fn; },
            querySelectorAll(selector) { return selector === '[data-sr-appearance]' ? controls : []; }
        },
        window: { addEventListener(name, fn) { windowEvents[name] = fn; } },
        localStorage: {
            getItem(key) { if (unavailable) throw Error('blocked'); return values[key] ?? null; },
            setItem(key, value) { if (unavailable) throw Error('blocked'); values[key] = value; }
        }
    };
    vm.runInNewContext(source, context);
    return { values, attributes, classes, controls, events, windowEvents, context,
        change(name, value) { events.change({ target: { getAttribute: () => name, value } }); } };
}
const fresh = boot();
assert(fresh.classes.has('sr-light'), 'new visitors start in light mode before DOM ready');
assert.equal(fresh.attributes['data-sr-palette'], 'forest');
assert.equal(fresh.attributes['data-sr-style'], 'soft');
fresh.events.DOMContentLoaded();
assert.deepEqual(fresh.controls.map(control => control.value), ['light', 'forest', 'soft']);
const legacy = boot({ srTheme: 'light', srPalette: 'ocean', srStyle: 'classic' });
assert(legacy.classes.has('sr-light'), 'existing light preference applies before DOM ready');
assert.equal(legacy.attributes['data-sr-palette'], 'ocean');
assert.equal(legacy.attributes['data-sr-style'], 'classic');
legacy.events.DOMContentLoaded();
assert.equal(legacy.controls[0].value, 'light');
legacy.change('palette', 'forest');
legacy.change('style', 'soft');
assert(legacy.classes.has('sr-light'), 'palette and style must not reset mode');
const reload = boot(legacy.values);
assert.equal(reload.attributes['data-sr-palette'], 'forest');
assert.equal(reload.attributes['data-sr-style'], 'soft');
reload.context.window.srToggleTheme();
assert.equal(reload.values.srTheme, 'dark');
assert.equal(reload.attributes['data-sr-palette'], 'forest');
assert(!boot(reload.values).classes.has('sr-light'), 'saved dark mode overrides the light default');
reload.windowEvents.storage({ key: 'srPalette', newValue: 'violet' });
assert.equal(reload.attributes['data-sr-palette'], 'violet');
assert.equal(reload.controls[1].value, 'violet');
reload.windowEvents.storage({ key: null, newValue: null });
assert(reload.classes.has('sr-light'));
assert.equal(reload.attributes['data-sr-palette'], 'forest');
assert.equal(reload.attributes['data-sr-style'], 'soft');
assert.deepEqual(reload.controls.map(control => control.value), ['light', 'forest', 'soft']);
const invalid = boot({ srPalette: 'invalid', srStyle: 'invalid', srTheme: 'invalid' });
invalid.change('palette', 'invalid');
assert.equal(invalid.attributes['data-sr-palette'], 'forest');
assert.equal(invalid.attributes['data-sr-style'], 'soft');
assert(invalid.classes.has('sr-light'));
const blocked = boot({}, true);
assert(blocked.classes.has('sr-light'));
assert.equal(blocked.attributes['data-sr-palette'], 'forest');
assert.equal(blocked.attributes['data-sr-style'], 'soft');
blocked.change('palette', 'sunset');
blocked.change('mode', 'light');
assert.equal(blocked.attributes['data-sr-palette'], 'sunset');
assert(blocked.classes.has('sr-light'), 'controls still work when storage is blocked');
console.log('Appearance: defaults, persistence, legacy preferences, independent choices, cross-tab sync, and blocked storage pass.');
