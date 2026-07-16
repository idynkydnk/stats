/**
 * Shared client-side search: space/comma-separated tokens must all match
 * (same behavior as server-side _search_query_tokens / _multi_token_search_clause).
 */
(function (global) {
    'use strict';

    function tokens(query) {
        if (!query) return [];
        return String(query)
            .toLowerCase()
            .trim()
            .split(/[\s,]+/)
            .filter(Boolean);
    }

    function matches(haystack, query) {
        var parts = tokens(query);
        if (!parts.length) return true;
        var text = String(haystack || '').toLowerCase();
        for (var i = 0; i < parts.length; i++) {
            if (text.indexOf(parts[i]) === -1) return false;
        }
        return true;
    }

    /**
     * Bind an input to filter cards with data-search attributes.
     * opts: { input, container, cardSelector, countEl, noResultsEl, countNoun }
     */
    function bindCardSearch(opts) {
        var input = opts.input;
        var container = opts.container;
        if (!input || !container) return;

        var cardSelector = opts.cardSelector || '[data-search]';
        var countEl = opts.countEl || null;
        var noResultsEl = opts.noResultsEl || null;
        var countNoun = opts.countNoun || 'game';

        function run() {
            var query = input.value;
            var cards = container.querySelectorAll(cardSelector);
            var visible = 0;
            for (var i = 0; i < cards.length; i++) {
                var card = cards[i];
                var ok = matches(card.getAttribute('data-search') || '', query);
                card.style.display = ok ? '' : 'none';
                if (ok) visible++;
            }
            if (countEl) {
                var noun = countNoun + (visible === 1 ? '' : 's');
                countEl.textContent = visible + ' ' + noun;
            }
            if (noResultsEl) {
                noResultsEl.style.display = visible === 0 ? 'block' : 'none';
            }
        }

        input.addEventListener('input', run);
        if (input.value) run();
    }

    global.srSearch = {
        tokens: tokens,
        matches: matches,
        bindCardSearch: bindCardSearch,
    };
})(window);
