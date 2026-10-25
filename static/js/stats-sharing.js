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
    const current = new URL(window.location.href);
    if (url.origin === window.location.origin) {
        for (const key of ['view', 'start_date', 'end_date']) {
            const value = current.searchParams.get(key);
            if (value && !url.searchParams.has(key)) url.searchParams.set(key, value);
        }
    }
    return url.pathname + url.search + url.hash;
}
