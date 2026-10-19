const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('templates/partials/player_photo_modal.html', 'utf8');
const init = source.slice(source.indexOf('var pendingPageConfig = null;'), source.indexOf('    function openPlayerFromCard'));
const open = source.slice(source.indexOf('function openModal()'), source.indexOf('    function closeModal()'));
const triggers = [];
const avatar = {};
const context = {
  headerAvatarImg: null, headerAvatarFallback: null, faceFocus: null, modal: { hidden: true },
  document: { getElementById(id) { return id === 'player-avatar-img' ? avatar : { addEventListener(event, fn) { triggers.push(fn); } }; } },
  applyCropWhenReady(img, focus) { assert.equal(img, avatar); assert.equal(focus.z, 2); },
  addTitleEditButton() {}, bindEditTriggers() {}, relayoutHeaderAvatar() {}, relayoutModalPhotos() {},
  requestAnimationFrame(fn) { fn(); },
};
let loads = 0;
context.loadPlayer = cfg => { loads++; assert.equal(cfg.name, 'Example'); context.pendingPageConfig = null; };
vm.createContext(context);
vm.runInContext(open + '\n' + init, context);
context.initPage({ name: 'Example', photoUrl: '/large-original.jpg', faceFocus: { x: 30, y: 60, z: 2 } });
assert.equal(loads, 0, 'Navigation must not start editor downloads');
assert.equal(context.modal.hidden, true);
triggers[0]();
assert.equal(loads, 1, 'Opening must load original details/images');
assert.equal(context.modal.hidden, false);
context.openModal();
assert.equal(loads, 1, 'Reopening must retain edited state');
console.log('Photo editor downloads start only when opened; saved avatar crop still initializes.');
