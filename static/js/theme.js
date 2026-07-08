// Theme handling: applies saved light/dark preference and powers the menu toggle.
// Loaded in <head> (tiny + blocking) so the theme applies before first paint.
(function() {
    try {
        if (localStorage.getItem('srTheme') === 'light') {
            document.documentElement.classList.add('sr-light');
        }
    } catch (e) { /* localStorage unavailable */ }

    function updateToggleLabels() {
        var isLight = document.documentElement.classList.contains('sr-light');
        document.querySelectorAll('.theme-toggle-link').forEach(function(link) {
            link.innerHTML = isLight
                ? '<i class="fas fa-moon"></i> Dark Mode'
                : '<i class="fas fa-sun"></i> Light Mode';
        });
    }

    window.srToggleTheme = function() {
        var isLight = document.documentElement.classList.toggle('sr-light');
        try { localStorage.setItem('srTheme', isLight ? 'light' : 'dark'); } catch (e) {}
        updateToggleLabels();
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', updateToggleLabels);
    } else {
        updateToggleLabels();
    }
})();
