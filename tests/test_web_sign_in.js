const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/js/sign-in.js'), 'utf8');

function setup() {
    const button = {
        textContent: 'Send a new code', name: 'action', value: 'resend', disabled: false,
        dataset: {}, attributes: {},
        setAttribute(name, value) { this.attributes[name] = value; },
        removeAttribute(name) { delete this.attributes[name]; }
    };
    const form = {
        dataset: {busyLabel: 'Sending…'}, attributes: {}, events: {},
        addEventListener(name, handler) { this.events[name] = handler; },
        setAttribute(name, value) { this.attributes[name] = value; },
        removeAttribute(name) { delete this.attributes[name]; },
        querySelector() { return button; }, querySelectorAll() { return [button]; }
    };
    const events = {};
    vm.runInNewContext(source, {
        document: {querySelectorAll: () => [form]},
        window: {addEventListener(name, handler) { events[name] = handler; }}
    });
    return {form, button, events};
}

test('resend submits its action and prevents accidental duplicate requests', () => {
    const {form, button} = setup();
    let prevented = false;
    const event = {submitter: button, preventDefault() { prevented = true; }};
    form.events.submit(event);
    assert.equal(prevented, false);
    assert.equal(button.disabled, false);
    assert.equal(button.value, 'resend');
    assert.equal(button.textContent, 'Sending…');
    form.events.submit(event);
    assert.equal(prevented, true);
});

test('back navigation restores a usable form and allows another submission', () => {
    const {form, button, events} = setup();
    form.events.submit({submitter: button});
    events.pageshow();
    assert.equal(button.textContent, 'Send a new code');
    assert.equal(form.attributes['aria-busy'], undefined);
    assert.equal(button.attributes['aria-disabled'], undefined);
    let prevented = false;
    form.events.submit({preventDefault() { prevented = true; }});
    assert.equal(prevented, false);
});
