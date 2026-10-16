// Forms work without JavaScript; this only prevents accidental double submits.
(function () {
    'use strict';
    document.querySelectorAll('form[data-busy-label]').forEach(function (form) {
        form.addEventListener('submit', function (event) {
            if (form.dataset.submitting) {
                event.preventDefault();
                return;
            }
            form.dataset.submitting = 'true';
            form.setAttribute('aria-busy', 'true');
            var button = event.submitter || form.querySelector('button[type="submit"], button');
            if (button) {
                // Keep named submitters enabled so their action is posted.
                button.dataset.originalLabel = button.textContent;
                button.textContent = form.dataset.busyLabel;
                button.setAttribute('aria-disabled', 'true');
            }
        });
    });
    window.addEventListener('pageshow', function () {
        document.querySelectorAll('form[data-busy-label]').forEach(function (form) {
            delete form.dataset.submitting;
            form.removeAttribute('aria-busy');
            form.querySelectorAll('[data-original-label]').forEach(function (button) {
                button.textContent = button.dataset.originalLabel;
                button.removeAttribute('aria-disabled');
                delete button.dataset.originalLabel;
            });
        });
    });
}());
