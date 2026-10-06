// Share the current page, including its selected databases and filters.
document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-copy-stats-link]').forEach(function (button) {
        button.addEventListener('click', async function () {
            const label = button.querySelector('span');
            try {
                await navigator.clipboard.writeText(window.location.href);
                label.textContent = 'Copied!';
                setTimeout(function () { label.textContent = 'Copy link'; }, 2000);
            } catch (error) {
                // Clipboard access can be unavailable on HTTP or denied.
                window.prompt('Copy this link to share these stats:', window.location.href);
            }
        });
    });
});

function statsViewURL(path) {
    const url = new URL(path, window.location.href);
    const view = new URL(window.location.href).searchParams.get('view');
    if (view && url.origin === window.location.origin) url.searchParams.set('view', view);
    return url.pathname + url.search + url.hash;
}
