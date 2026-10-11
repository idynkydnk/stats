const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function setup() {
    const events = {}, microtasks = [], beacons = [];
    let status;
    const on = (name, fn) => { events[name] = fn; };
    const context = {
        URL, Blob, Number,
        location: {href: 'https://stats.test/games', origin: 'https://stats.test', pathname: '/games', search: ''},
        performance: {now: () => 25, getEntriesByType: () => []},
        requestAnimationFrame: fn => fn(), setTimeout: () => {},
        queueMicrotask: fn => microtasks.push(fn),
        navigator: {sendBeacon: (url, data) => beacons.push({url, data})},
        window: {addEventListener: on},
        document: {addEventListener: on, hidden: false,
            createElement: () => (status = {setAttribute() {}}), body: {appendChild() {}}},
    };
    vm.runInNewContext(fs.readFileSync('static/js/responsiveness.js', 'utf8'), context);
    return {events, beacons, get status() { return status; }, flush: () => { while (microtasks.length) microtasks.shift()(); }};
}

function click(state, href, extra = {}) {
    const link = {href, target: '', hasAttribute: () => false, closest: () => link};
    const event = {button: 0, defaultPrevented: false, target: link, ...extra};
    state.events.click(event);
    return event;
}

const state = setup();
click(state, 'https://stats.test/player/private-name?secret=never-log');
state.flush();
assert.equal(state.status.hidden, false, 'Normal navigation gives immediate feedback');
state.events.pageshow();
assert.equal(state.status.hidden, true, 'Back navigation resets the indicator');
for (const [url, modifiers] of [
    ['https://other.test/', {}], ['https://stats.test/games#history', {}],
    ['https://stats.test/players', {ctrlKey: true}], ['https://stats.test/players', {button: 1}],
]) {
    click(state, url, modifiers); state.flush();
    assert.equal(state.status.hidden, true, 'Non-navigation clicks do not leave a spinner');
}
const canceled = click(state, 'https://stats.test/players');
canceled.defaultPrevented = true;
state.flush();
assert.equal(state.status.hidden, true, 'Page-specific cancellation takes precedence');
state.events.submit({defaultPrevented: true, target: {method: 'post'}}); state.flush();
assert.equal(state.status.hidden, true, 'AJAX forms retain their own feedback');
state.events.submit({defaultPrevented: false, target: {method: 'get'}}); state.flush();
assert.equal(state.status.textContent, 'Loading…');
state.events.pageshow();
state.events.submit({defaultPrevented: false, target: {method: 'post'}}); state.flush();
assert.equal(state.status.textContent, 'Saving…');
state.events.pagehide();
assert.equal(state.beacons.length, 1);
state.beacons[0].data.text().then(body => {
    assert(!body.includes('private-name') && !body.includes('secret'));
    assert(JSON.parse(body).length <= 12);
    console.log('Navigation feedback, canceled actions, browser back, form methods, and anonymous timing passed.');
});
