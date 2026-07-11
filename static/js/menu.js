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
        }
        function closeMenu() {
            menuOverlay.classList.remove('active');
            menuSidebar.classList.remove('active');
            menuToggle.classList.remove('active');
            menuToggle.setAttribute('aria-expanded', 'false');
        }
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

    function checkNotifications() {
        var badge = document.getElementById('notification-badge');
        if (!badge) return;
        fetch('/api/notifications/count')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.count > 0) {
                    badge.textContent = data.count > 99 ? '99+' : data.count;
                    badge.style.display = 'inline-block';
                    badge.setAttribute('aria-label', data.count + ' unread notification' + (data.count !== 1 ? 's' : ''));
                } else {
                    badge.style.display = 'none';
                    badge.removeAttribute('aria-label');
                }
            })
            .catch(function() {});
    }

    document.addEventListener('DOMContentLoaded', function() {
        checkNotifications();
        var tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
        if (tz) {
            fetch('/api/set_timezone', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({timezone: tz})
            }).catch(function() {});
        }
    });
    window.addEventListener('pageshow', function(e) { if (e.persisted) checkNotifications(); });
    document.addEventListener('visibilitychange', function() { if (!document.hidden) checkNotifications(); });
})();
