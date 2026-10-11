/* Immediate navigation feedback and bounded anonymous performance samples. */
(function () {
    'use strict';
    var samples = [];
    var status = document.createElement('div');
    status.className = 'sr-navigation-status';
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    status.hidden = true;
    status.textContent = 'Loading…';
    document.body.appendChild(status);
    function record(action, milliseconds) {
        if (Number.isFinite(milliseconds) && milliseconds >= 0) {
            samples.push({action: action, milliseconds: Math.round(milliseconds)});
            if (samples.length > 12) samples.shift();
        }
    }
    function flush() {
        if (!samples.length || !navigator.sendBeacon) return;
        var batch = samples.splice(0, 12);
        navigator.sendBeacon('/performance-sample', new Blob([JSON.stringify(batch)], {type: 'application/json'}));
    }
    function reset() { status.hidden = true; status.textContent = 'Loading…'; }
    window.addEventListener('pageshow', reset);
    window.addEventListener('pagehide', flush);
    document.addEventListener('visibilitychange', function () { if (document.hidden) flush(); });
    document.addEventListener('click', function (event) {
        var element = event.target.closest && event.target.closest('a, button, select');
        if (!element) return;
        var start = performance.now();
        requestAnimationFrame(function () { requestAnimationFrame(function () { record('tap', performance.now() - start); }); });
        if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        var link = element.closest('a[href]');
        if (!link || link.hasAttribute('download') || (link.target && link.target !== '_self')) return;
        var url = new URL(link.href, location.href);
        if (url.origin !== location.origin || (url.pathname === location.pathname && url.search === location.search)) return;
        // Wait for page-specific click handlers, including confirmation dialogs.
        queueMicrotask(function () {
            if (!event.defaultPrevented) { status.hidden = false; setTimeout(reset, 15000); }
        });
    });
    document.addEventListener('submit', function (event) {
        queueMicrotask(function () {
            if (!event.defaultPrevented) { status.textContent = event.target.method.toLowerCase() === 'get' ? 'Loading…' : 'Saving…'; status.hidden = false; setTimeout(reset, 15000); }
        });
    });
    window.addEventListener('load', function () {
        setTimeout(function () {
            var nav = performance.getEntriesByType('navigation')[0];
            if (!nav) return;
            record('navigation', nav.loadEventEnd - nav.startTime);
            record('server-wait', nav.responseStart - nav.requestStart);
            record('download', nav.responseEnd - nav.responseStart);
            record('render', nav.domContentLoadedEventEnd - nav.responseEnd);
        }, 0);
    });
    if (window.PerformanceObserver) {
        try {
            new PerformanceObserver(function (list) {
                list.getEntries().forEach(function (entry) { record('long-task', entry.duration); });
            }).observe({type: 'longtask', buffered: true});
        } catch (_) { /* Older browsers still report navigation and tap timing. */ }
    }
})();
