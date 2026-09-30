// Apply saved appearance before first paint; keep the existing light/dark preference.
(function() {
    var root = document.documentElement;
    var choices = {
        mode: { key: 'srTheme', values: ['dark', 'light'], fallback: 'dark' },
        palette: { key: 'srPalette', values: ['ocean', 'forest', 'sunset', 'violet'], fallback: 'ocean' },
        style: { key: 'srStyle', values: ['classic', 'soft', 'sharp'], fallback: 'classic' }
    };
    var current = {};

    function apply(name, value) {
        var choice = choices[name];
        current[name] = choice.values.indexOf(value) >= 0 ? value : choice.fallback;
        if (name === 'mode') root.classList.toggle('sr-light', current[name] === 'light');
        else root.setAttribute('data-sr-' + name, current[name]);
    }

    Object.keys(choices).forEach(function(name) {
        var value;
        try { value = localStorage.getItem(choices[name].key); } catch (e) {}
        apply(name, value);
    });

    function syncControls() {
        document.querySelectorAll('[data-sr-appearance]').forEach(function(control) {
            control.value = current[control.getAttribute('data-sr-appearance')];
        });
        document.querySelectorAll('.theme-toggle-link').forEach(function(link) {
            link.innerHTML = current.mode === 'light'
                ? '<i class="fas fa-moon"></i> Dark Mode'
                : '<i class="fas fa-sun"></i> Light Mode';
        });
    }

    function save(name, value) {
        if (!choices[name] || choices[name].values.indexOf(value) < 0) return;
        apply(name, value);
        try { localStorage.setItem(choices[name].key, value); } catch (e) {}
        syncControls();
    }

    window.srToggleTheme = function() {
        save('mode', current.mode === 'light' ? 'dark' : 'light');
    };

    document.addEventListener('change', function(event) {
        var name = event.target.getAttribute('data-sr-appearance');
        if (name) save(name, event.target.value);
    });

    // Keep appearance in step when another tab changes it or clears saved settings.
    window.addEventListener('storage', function(event) {
        Object.keys(choices).forEach(function(name) {
            if (event.key === null || event.key === choices[name].key) apply(name, event.newValue);
        });
        syncControls();
    });

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', syncControls);
    else syncControls();
})();
