// DOM behavior checks; never opens a browser. Install linkedom in a temporary
// directory and use NODE_PATH=<that directory>/node_modules when running this.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');
const { execFileSync } = require('node:child_process');
const { parseHTML } = require('linkedom');
const root = path.resolve(__dirname, '..');
const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'season-controls-'));

function setup(page, url) {
    const { document, Event } = parseHTML(fs.readFileSync(path.join(folder, page + '.html'), 'utf8'));
    const windowEvents = {};
    const state = { copied: [], confirm: true, focused: null, selected: null, prompts: [], clipboardDenied: false };
    const win = {
        location: { href: url },
        history: { pushState(_, __, target) { win.location.href = target; } },
        addEventListener(type, callback) { windowEvents[type] = callback; },
        confirm: () => state.confirm,
        prompt: (...args) => state.prompts.push(args),
    };
    // Linkedom provides DOM/events; these standard browser control APIs are
    // supplied here because it does not implement form submission or layout.
    for (const select of document.querySelectorAll('select')) {
        Object.defineProperty(select, 'form', { get: () => select.closest('form') });
        Object.defineProperty(select, 'value', {
            get: () => (select.querySelector('option[selected]') || select.querySelector('option'))?.value,
            set: value => select.querySelectorAll('option').forEach(option => {
                if (option.value === value) option.setAttribute('selected', '');
                else option.removeAttribute('selected');
            }),
        });
    }
    // The DOM library double-encodes percent escapes in its href getter.
    // Use the browser's standard URL resolution for link navigation checks.
    for (const link of document.querySelectorAll('a[href]')) {
        Object.defineProperty(link, 'href', {
            get: () => new URL(link.getAttribute('href'), win.location.href).href,
            set: value => link.setAttribute('href', value),
        });
    }
    for (const button of document.querySelectorAll('button')) {
        Object.defineProperty(button, 'value', {
            get: () => button.getAttribute('value') || '',
            set: value => button.setAttribute('value', value),
        });
    }
    for (const element of document.querySelectorAll('*')) {
        element.focus = () => { state.focused = element; };
        element.select = () => { state.selected = element; };
        element.scrollIntoView = () => {};
        element.setCustomValidity = message => { element.validationMessage = message; };
    }
    for (const form of document.querySelectorAll('form')) {
        form.reportValidity = () => !Array.from(form.querySelectorAll('input')).some(input => input.validationMessage);
    }
    for (const cell of document.querySelectorAll('th, td')) {
        Object.defineProperty(cell, 'cellIndex', { get: () => Array.from(cell.parentNode.children).indexOf(cell) });
    }
    for (const row of document.querySelectorAll('tr')) {
        Object.defineProperty(row, 'cells', { get: () => Array.from(row.children) });
    }
    const sandbox = {
        document, window: win, URL, Map, Array,
        navigator: { clipboard: { async writeText(value) { if (state.clipboardDenied) throw Error('denied'); state.copied.push(value); } } },
        setTimeout: () => {},
    };
    vm.runInNewContext(fs.readFileSync(path.join(root, 'static/js/seasons.js'), 'utf8'), sandbox);
    if (page !== 'form') vm.runInNewContext(fs.readFileSync(path.join(root, 'static/js/stats.js'), 'utf8'), sandbox);
    document.dispatchEvent(new Event('DOMContentLoaded'));
    function dispatch(element, type, props = {}) {
        const event = new Event(type, { bubbles: true, cancelable: true });
        Object.assign(event, props);
        element.dispatchEvent(event);
        return event;
    }
    return { document, state, win, windowEvents, dispatch, byId: id => document.getElementById(id) };
}

async function run() {
    execFileSync(path.join(root, 'venv/bin/python'), [path.join(__dirname, 'season_ui_fixtures.py'), folder], { cwd: root, stdio: 'pipe' });
    const form = setup('form', 'https://stats.test/seasons/new/');
    const mode = form.byId('season-minimum-mode');
    const minimum = form.byId('season-minimum');
    assert.equal(minimum.disabled, true);
    assert.equal(form.byId('season-fixed-minimum').hidden, true);
    mode.value = 'fixed'; form.dispatch(mode, 'change');
    minimum.value = '12';
    assert.equal(minimum.disabled, false); assert.equal(minimum.required, true);
    mode.value = 'automatic'; form.dispatch(mode, 'change');
    mode.value = 'fixed'; form.dispatch(mode, 'change');
    assert.equal(minimum.value, '12', 'Switching modes retains the custom minimum');
    form.byId('season-start').value = '2026-06-10';
    form.byId('season-end').value = '2026-06-01';
    form.dispatch(form.byId('season-start'), 'change');
    assert.equal(form.byId('season-end').min, '2026-06-10');
    assert.equal(form.byId('season-end').value, '2026-06-10');
    form.byId('season-name').value = '  ';
    form.dispatch(form.byId('season-name'), 'input');
    assert(form.byId('season-name').validationMessage);
    const editor = form.document.querySelector('[data-season-form]');
    const save = editor.querySelector('button[type="submit"]');
    assert.equal(form.dispatch(editor, 'submit', { submitter: save }).defaultPrevented, true);
    assert.equal(save.disabled, false);
    form.byId('season-name').value = ' Summer '; form.dispatch(form.byId('season-name'), 'input');
    assert.equal(form.dispatch(editor, 'submit', { submitter: save }).defaultPrevented, false);
    assert.equal(form.byId('season-name').value, 'Summer');
    assert.equal(save.disabled, true);
    assert.equal(form.dispatch(editor, 'submit', { submitter: save }).defaultPrevented, true);
    form.windowEvents.pageshow();
    assert.equal(save.disabled, false); assert.equal(editor.hasAttribute('aria-busy'), false);
    assert.equal(save.textContent, 'Create season');

    const detail = setup('detail', 'https://stats.test/seasons/example/?group=doubles%3Awomen');
    const picker = detail.byId('season-group');
    const groups = Array.from(detail.document.querySelectorAll('[data-season-group]'));
    assert.equal(groups.filter(g => !g.hidden).length, 1);
    assert.equal(groups.find(g => !g.hidden).dataset.seasonGroup, 'doubles:women');
    picker.value = 'doubles:open'; detail.dispatch(picker, 'change');
    assert.equal(new URL(detail.win.location.href).searchParams.get('group'), 'doubles:open');
    assert.equal(groups.find(g => !g.hidden).dataset.seasonGroup, 'doubles:open');
    assert.equal(new URL(detail.document.querySelector('[data-season-group-link]').href).searchParams.get('group'), 'doubles:open');
    assert.equal(new URL(detail.byId('season-share-url').value).searchParams.get('group'), 'doubles:open');
    detail.win.location.href = 'https://stats.test/seasons/example/?group=doubles%3Awomen';
    detail.windowEvents.popstate();
    assert.equal(picker.value, 'doubles:women');
    assert.equal(groups.find(g => !g.hidden).dataset.seasonGroup, 'doubles:women');
    const rare = detail.document.querySelector('[data-season-group="doubles:open"] .season-qualification table');
    const ratingHeader = rare.querySelector('[data-sort="rating"]');
    detail.dispatch(ratingHeader, 'click');
    assert.equal(ratingHeader.getAttribute('aria-sort'), 'ascending');
    assert.equal(rare.querySelectorAll('tbody .sr-hidden').length, 35);
    assert(Array.from(rare.querySelectorAll('tbody tr')).every(row => row.cells[0].textContent === '—'), 'Sorting does not rank unqualified players');
    const menu = detail.document.querySelector('[data-season-menu]');
    menu.open = true; detail.dispatch(menu.querySelector('input'), 'click');
    assert.equal(menu.open, true);
    detail.dispatch(menu, 'keydown', { key: 'Escape' });
    assert.equal(menu.open, false); assert(detail.state.focused === menu.querySelector('summary'), 'Escape returns focus to the Share control');
    menu.open = true; detail.dispatch(detail.document.body, 'click'); assert.equal(menu.open, false);
    const copy = detail.document.querySelector('[data-season-copy]');
    detail.dispatch(copy, 'click'); await new Promise(setImmediate);
    assert.equal(detail.state.copied[0], detail.byId('season-share-url').value);
    detail.state.clipboardDenied = true; detail.dispatch(copy, 'click'); await new Promise(setImmediate);
    assert(detail.state.selected === detail.byId('season-share-url'), 'Denied clipboard access selects the link for manual copying');
    const shareForm = menu.querySelector('form'); const stop = shareForm.querySelector('button');
    detail.dispatch(shareForm, 'submit', { submitter: stop });
    assert.equal(shareForm.querySelector('[data-season-submitter]').value, 'stop', 'Stopping sharing survives disabling its submit button');
    detail.windowEvents.pageshow();
    assert.equal(shareForm.querySelector('[data-season-submitter]'), null); assert.equal(stop.disabled, false);
    const deletion = detail.document.querySelector('[data-season-delete]');
    detail.state.confirm = false;
    assert.equal(detail.dispatch(deletion, 'submit', { submitter: deletion.querySelector('button') }).defaultPrevented, true);
    assert.equal(deletion.dataset.busy, undefined);

    const player = setup('player', 'https://stats.test/seasons/example/?group=doubles%3Aopen&player=B');
    const list = player.byId('season-player-games'); const more = player.document.querySelector('[data-season-expand]');
    assert.equal(list.children.length, 60);
    assert.equal(Array.from(list.children).filter(row => !row.classList.contains('sr-hidden')).length, 25);
    player.dispatch(more, 'click');
    assert.equal(list.querySelectorAll('.sr-hidden').length, 0); assert.equal(more.getAttribute('aria-expanded'), 'true');
    player.dispatch(more, 'click');
    assert.equal(list.querySelectorAll('.sr-hidden').length, 35); assert.equal(more.getAttribute('aria-expanded'), 'false');
    console.log('Season forms, date bounds, duplicate submits, browser back, format selection, sharing, keyboard dismissal, and long lists passed.');
}
run().finally(() => fs.rmSync(folder, { recursive: true, force: true })).catch(error => { console.error(error); process.exitCode = 1; });
