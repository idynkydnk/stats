(function () {
    function canShareFile(file) {
        return !!(navigator.share && navigator.canShare && file && navigator.canShare({ files: [file] }));
    }

    async function loadBlob(url) {
        var res = await fetch(url, { credentials: 'same-origin' });
        if (!res.ok) throw new Error('Could not load picture');
        return await res.blob();
    }

    async function saveToPhotos(btn) {
        var downloadUrl = btn.getAttribute('data-download') || '';
        var imageUrl = btn.getAttribute('data-image') || downloadUrl;
        var name = btn.getAttribute('data-filename') || 'flyer.jpg';
        if (!downloadUrl && !imageUrl) return;
        btn.disabled = true;
        try {
            var blob = await loadBlob(downloadUrl || imageUrl);
            var type = blob.type || 'image/jpeg';
            if (type.indexOf('image/') !== 0) type = 'image/jpeg';
            var file = new File([blob], name, { type: type });
            if (canShareFile(file)) {
                await navigator.share({ files: [file] });
                return;
            }
            if (imageUrl) window.open(imageUrl, '_blank', 'noopener');
        } catch (err) {
            if (err && err.name === 'AbortError') return;
            if (imageUrl) window.open(imageUrl, '_blank', 'noopener');
        } finally {
            btn.disabled = false;
        }
    }

    document.querySelectorAll('[data-flyer-save]').forEach(function (btn) {
        btn.addEventListener('click', function () {
            saveToPhotos(btn);
        });
    });
})();
