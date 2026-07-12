(function () {
    'use strict';

    var VIEWPORT_DEFAULT = 'width=device-width, initial-scale=1.0';
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
            .trim() || VIEWPORT_DEFAULT;
    }

    function resetViewportZoom() {
        var meta = document.querySelector('meta[name="viewport"]');
        if (!meta) {
            return;
        }
        var base = viewportBaseContent(meta);
        clearTimeout(resetTimer);
        meta.setAttribute('content', base + ', maximum-scale=1');
        resetTimer = setTimeout(function () {
            meta.setAttribute('content', base);
        }, 150);
    }

    function maybeResetZoomAfterKeyboard() {
        if (isTextLikeField(document.activeElement)) {
            return;
        }
        resetViewportZoom();
    }

    if (!isTouchMobile()) {
        return;
    }

    document.addEventListener('focusout', function (e) {
        if (!isTextLikeField(e.target)) {
            return;
        }
        setTimeout(maybeResetZoomAfterKeyboard, 120);
    }, true);

    if (window.visualViewport) {
        var lastViewportHeight = window.visualViewport.height;
        window.visualViewport.addEventListener('resize', function () {
            var height = window.visualViewport.height;
            if (height > lastViewportHeight + 80) {
                setTimeout(maybeResetZoomAfterKeyboard, 120);
            }
            lastViewportHeight = height;
        });
    }
})();
