(function () {
    'use strict';

    var VIEWPORT_DEFAULT = 'width=device-width, initial-scale=1.0, viewport-fit=cover';
    var resetTimer = null;

    function isTouchMobile() {
        if (window.matchMedia) {
            return window.matchMedia('(hover: none) and (pointer: coarse)').matches;
        }
        return 'ontouchstart' in window && window.innerWidth < 1024;
    }

    function isTextLikeField(el) {
        if (!el || !el.matches || !el.matches('input, textarea, select')) {
            return false;
        }
        var tag = el.tagName;
        if (tag === 'TEXTAREA' || tag === 'SELECT') {
            return true;
        }
        var type = (el.type || 'text').toLowerCase();
        return type !== 'hidden'
            && type !== 'checkbox'
            && type !== 'radio'
            && type !== 'file'
            && type !== 'button'
            && type !== 'submit'
            && type !== 'reset'
            && type !== 'range'
            && type !== 'color';
    }

    function viewportBaseContent(meta) {
        var original = (meta && meta.getAttribute('content')) || VIEWPORT_DEFAULT;
        return original
            .replace(/,?\s*maximum-scale=[^,]*/gi, '')
            .replace(/,?\s*user-scalable=[^,]*/gi, '')
            .replace(/,?\s*minimum-scale=[^,]*/gi, '')
            .trim() || VIEWPORT_DEFAULT;
    }

    function resetViewportZoom() {
        var meta = document.querySelector('meta[name="viewport"]');
        if (!meta) {
            return;
        }
        var base = viewportBaseContent(meta);
        clearTimeout(resetTimer);
        // Briefly lock scale, then restore so pinch-zoom still works.
        meta.setAttribute('content', base + ', maximum-scale=1');
        resetTimer = setTimeout(function () {
            meta.setAttribute('content', base);
        }, 300);
    }

    function maybeResetZoomAfterKeyboard() {
        if (isTextLikeField(document.activeElement)) {
            return;
        }
        resetViewportZoom();
        // Some iOS versions keep a stale visual viewport scale until a second tick.
        setTimeout(resetViewportZoom, 350);
    }

    if (!isTouchMobile()) {
        return;
    }

    document.addEventListener('focusout', function (e) {
        if (!isTextLikeField(e.target)) {
            return;
        }
        setTimeout(maybeResetZoomAfterKeyboard, 50);
        setTimeout(maybeResetZoomAfterKeyboard, 250);
    }, true);

    window.addEventListener('pageshow', function () {
        resetViewportZoom();
    });

    if (window.visualViewport) {
        var lastViewportHeight = window.visualViewport.height;
        window.visualViewport.addEventListener('resize', function () {
            var height = window.visualViewport.height;
            // Keyboard closing expands the visual viewport.
            if (height > lastViewportHeight + 60) {
                setTimeout(maybeResetZoomAfterKeyboard, 50);
                setTimeout(maybeResetZoomAfterKeyboard, 250);
            }
            lastViewportHeight = height;
        });
    }
})();
