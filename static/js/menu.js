(function() {
    var menuToggle = document.getElementById('menu-toggle');
    var menuClose = document.getElementById('menu-close');
    var menuOverlay = document.getElementById('menu-overlay');
    var menuSidebar = document.getElementById('menu-sidebar');

    if (menuToggle && menuSidebar) {
        function openMenu() {
            menuOverlay.classList.add('active');
            menuSidebar.classList.add('active');
            menuToggle.classList.add('active');
            menuToggle.setAttribute('aria-expanded', 'true');
            if (menuClose) menuClose.focus();
        }
        function closeMenu() {
            menuOverlay.classList.remove('active');
            menuSidebar.classList.remove('active');
            menuToggle.classList.remove('active');
            menuToggle.setAttribute('aria-expanded', 'false');
            menuToggle.focus();
        }
        document.addEventListener('keydown', function(event) {
            if (!menuSidebar.classList.contains('active')) return;
            if (event.key === 'Escape') {
                event.preventDefault();
                closeMenu();
            }
            if (event.key === 'Tab') {
                var items = Array.from(menuSidebar.querySelectorAll('a[href], button, input, select, [tabindex="0"]')).filter(function(item) { return !item.disabled && item.getClientRects().length; });
                var first = items[0], last = items[items.length - 1];
                if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
                else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
            }
        });
        menuToggle.addEventListener('click', function() {
            if (menuSidebar.classList.contains('active')) closeMenu();
            else openMenu();
        });
        if (menuClose) menuClose.addEventListener('click', closeMenu);
        if (menuOverlay) menuOverlay.addEventListener('click', closeMenu);
        document.querySelectorAll('.menu-list a').forEach(function(link) {
            link.addEventListener('click', closeMenu);
        });
    }

    document.addEventListener('DOMContentLoaded', function() {
        var tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
        if (tz) {
            fetch('/api/set_timezone', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({timezone: tz})
            }).catch(function() {});
        }
    });
})();
