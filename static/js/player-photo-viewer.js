(function () {
    'use strict';
    if (window.playerPhotoViewer) return;
    var dialog = document.createElement('dialog');
    dialog.className = 'sr-photo-viewer';
    dialog.setAttribute('aria-label', 'Full-screen photo');
    dialog.innerHTML = '<div class="sr-photo-viewer-stage"><img alt="" draggable="false"></div>' +
        '<div class="sr-photo-viewer-tools"><button type="button" data-action="out" aria-label="Zoom out">−</button>' +
        '<button type="button" data-action="reset">Reset</button><button type="button" data-action="in" aria-label="Zoom in">+</button>' +
        '<button type="button" data-action="close" autofocus>Close</button></div>' +
        '<p class="sr-photo-viewer-hint">Pinch to zoom · drag to move</p>';
    document.body.appendChild(dialog);
    var stage = dialog.querySelector('.sr-photo-viewer-stage');
    var photo = stage.querySelector('img');
    var pointers = new Map();
    var scale = 1, x = 0, y = 0, opener, previousOverflow;
    function render() {
        var maxX = Math.max(0, (photo.clientWidth * scale - stage.clientWidth) / 2);
        var maxY = Math.max(0, (photo.clientHeight * scale - stage.clientHeight) / 2);
        x = Math.max(-maxX, Math.min(maxX, x));
        y = Math.max(-maxY, Math.min(maxY, y));
        photo.style.transform = 'translate(' + x + 'px,' + y + 'px) scale(' + scale + ')';
    }
    function reset() { scale = 1; x = y = 0; render(); }
    function zoom(next, cx, cy) {
        next = Math.max(1, Math.min(8, next));
        var rect = stage.getBoundingClientRect();
        var px = (cx == null ? rect.width / 2 : cx - rect.left) - rect.width / 2;
        var py = (cy == null ? rect.height / 2 : cy - rect.top) - rect.height / 2;
        x = px - (px - x) * next / scale;
        y = py - (py - y) * next / scale;
        scale = next;
        render();
    }
    function open(img, trigger) {
        if (!img || !img.getAttribute('src') || dialog.open) return;
        opener = trigger || img;
        photo.src = img.currentSrc || img.src;
        photo.alt = img.alt || 'Player photo';
        previousOverflow = document.body.style.overflow;
        document.body.style.overflow = 'hidden';
        dialog.showModal();
        reset();
    }
    window.playerPhotoViewer = { open: open };
    photo.addEventListener('load', reset);
    window.addEventListener('resize', function () { if (dialog.open) render(); });
    dialog.addEventListener('close', function () {
        pointers.clear();
        photo.removeAttribute('src');
        document.body.style.overflow = previousOverflow;
        if (opener && opener.isConnected) opener.focus({ preventScroll: true });
    });
    dialog.addEventListener('click', function (event) {
        var action = event.target.dataset.action;
        if (action === 'close') dialog.close();
        if (action === 'reset') reset();
        if (action === 'in') zoom(scale * 1.5);
        if (action === 'out') zoom(scale / 1.5);
    });
    stage.addEventListener('pointerdown', function (event) {
        if (event.button !== 0) return;
        pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
        stage.setPointerCapture(event.pointerId);
        event.preventDefault();
    });
    stage.addEventListener('pointermove', function (event) {
        if (!pointers.has(event.pointerId)) return;
        var before = Array.from(pointers.values());
        var old = pointers.get(event.pointerId);
        pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
        var after = Array.from(pointers.values());
        if (before.length === 2) {
            var oldDistance = Math.hypot(before[0].x - before[1].x, before[0].y - before[1].y);
            var newDistance = Math.hypot(after[0].x - after[1].x, after[0].y - after[1].y);
            var cx = (before[0].x + before[1].x) / 2;
            var cy = (before[0].y + before[1].y) / 2;
            if (oldDistance > 0) zoom(scale * newDistance / oldDistance, cx, cy);
            x += (after[0].x + after[1].x) / 2 - cx;
            y += (after[0].y + after[1].y) / 2 - cy;
        } else if (before.length === 1) {
            x += event.clientX - old.x;
            y += event.clientY - old.y;
        }
        render();
    });
    ['pointerup', 'pointercancel', 'lostpointercapture'].forEach(function (type) {
        stage.addEventListener(type, function (event) { pointers.delete(event.pointerId); });
    });
    stage.addEventListener('wheel', function (event) {
        event.preventDefault();
        zoom(scale * Math.exp(-event.deltaY * 0.01), event.clientX, event.clientY);
    }, { passive: false });
    stage.addEventListener('dblclick', function (event) {
        if (scale > 1) reset(); else zoom(3, event.clientX, event.clientY);
    });
    var selector = '#modal-ai-image-preview, .sr-ai-character-version img, img.edit-ai-character, img.edit-player-photo';
    function prepare() {
        document.querySelectorAll(selector).forEach(function (img) {
            img.tabIndex = 0;
            img.setAttribute('role', 'button');
            img.setAttribute('aria-label', 'View ' + (img.alt || 'photo') + ' full screen');
        });
    }
    prepare();
    new MutationObserver(prepare).observe(document.body, { childList: true, subtree: true });
    document.addEventListener('click', function (event) {
        if (event.target.matches(selector)) open(event.target);
    });
    document.addEventListener('keydown', function (event) {
        if (event.target.matches(selector) && (event.key === 'Enter' || event.key === ' ')) {
            event.preventDefault();
            open(event.target);
        }
    });
    // A tap views the face; moving or using two fingers continues to edit its crop.
    var frame = document.getElementById('face-crop-frame');
    if (frame) {
        frame.tabIndex = 0;
        frame.setAttribute('role', 'button');
        frame.setAttribute('aria-label', 'View face photo full screen');
        var tap = null;
        frame.addEventListener('pointerdown', function (event) {
            if (!event.isPrimary || event.button !== 0) { tap = null; return; }
            tap = { x: event.clientX, y: event.clientY, id: event.pointerId };
        });
        frame.addEventListener('pointermove', function (event) {
            if (tap && Math.hypot(event.clientX - tap.x, event.clientY - tap.y) > 6) tap = null;
        });
        frame.addEventListener('pointercancel', function () { tap = null; });
        frame.addEventListener('pointerup', function (event) {
            if (tap && tap.id === event.pointerId) open(frame.querySelector('img'), frame);
            tap = null;
        });
        frame.addEventListener('keydown', function (event) {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault(); open(frame.querySelector('img'), frame);
            }
        });
    }
})();
