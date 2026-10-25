document.addEventListener('DOMContentLoaded', function () {
    const mode = document.getElementById('season-minimum-mode');
    const minimum = document.getElementById('season-minimum');
    const name = document.getElementById('season-name');
    const start = document.getElementById('season-start');
    const end = document.getElementById('season-end');
    function syncForm() {
        if (mode && minimum) {
            const fixed = mode.value === 'fixed';
            document.getElementById('season-fixed-minimum').hidden = !fixed;
            minimum.disabled = !fixed;
            minimum.required = fixed;
        }
        if (start && end) end.min = start.value;
    }
    if (mode) mode.addEventListener('change', syncForm);
    if (start && end) start.addEventListener('change', function () {
        syncForm();
        if (start.value && (!end.value || end.value < start.value)) end.value = start.value;
    });
    if (name) name.addEventListener('input', function () {
        name.setCustomValidity(name.value && !name.value.trim() ? 'Give the season a name.' : '');
    });
    syncForm();
    const error = document.getElementById('season-form-error');
    if (error) error.focus();

    const picker = document.getElementById('season-group');
    const groups = Array.from(document.querySelectorAll('[data-season-group]'));
    function selectGroup(value, push) {
        if (!picker || !groups.length) return;
        const selected = groups.some(group => group.dataset.seasonGroup === value) ? value : groups[0].dataset.seasonGroup;
        picker.value = selected;
        groups.forEach(group => { group.hidden = group.dataset.seasonGroup !== selected; });
        document.querySelectorAll('[data-season-group-link]').forEach(link => {
            const url = new URL(link.href, window.location.href);
            url.searchParams.set('group', selected);
            link.href = url.href;
        });
        document.querySelectorAll('[data-season-group-field]').forEach(field => { field.value = selected; });
        const share = document.getElementById('season-share-url');
        if (share) {
            const url = new URL(share.dataset.baseUrl, window.location.href);
            url.searchParams.set('group', selected);
            share.value = url.href;
        }
        if (push) {
            const url = new URL(window.location.href);
            url.searchParams.set('group', selected);
            url.searchParams.delete('sharing');
            window.history.pushState(null, '', url.href);
        }
    }
    if (picker) {
        picker.addEventListener('change', function () { selectGroup(picker.value, true); });
        picker.form.addEventListener('submit', function (event) {
            event.preventDefault();
            selectGroup(picker.value, true);
        });
    }
    function restoreGroup() {
        if (picker) selectGroup(new URL(window.location.href).searchParams.get('group') || groups[0].dataset.seasonGroup, false);
    }
    window.addEventListener('popstate', restoreGroup);
    restoreGroup();

    const menus = Array.from(document.querySelectorAll('[data-season-menu]'));
    if (new URL(window.location.href).searchParams.get('sharing') === '1') {
        const menu = menus.find(item => item.open);
        const action = menu && (menu.querySelector('[data-season-copy]') || menu.querySelector('button'));
        if (action) action.focus();
    }
    function closeMenus(restoreFocus) {
        menus.forEach(menu => {
            if (menu.open) {
                menu.open = false;
                if (restoreFocus) menu.querySelector('summary').focus();
            }
        });
    }
    document.addEventListener('click', function (event) {
        menus.forEach(menu => { if (!menu.contains(event.target)) menu.open = false; });
    });
    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && menus.some(menu => menu.open)) {
            event.preventDefault();
            closeMenus(true);
        }
    });

    document.querySelectorAll('[data-season-copy]').forEach(function (button) {
        button.setAttribute('aria-live', 'polite');
        button.addEventListener('click', async function () {
            if (button.disabled) return;
            const field = document.getElementById(button.dataset.seasonCopy);
            const link = field ? field.value : window.location.href;
            button.disabled = true;
            try {
                await navigator.clipboard.writeText(link);
                button.textContent = 'Copied!';
                setTimeout(function () { button.textContent = 'Copy link'; }, 2000);
            } catch (_) {
                // Keep a manual way to copy when clipboard permission is denied.
                if (field) { field.focus(); field.select(); }
                else { window.prompt('Copy this season link:', link); }
            } finally { button.disabled = false; }
        });
    });

    // Progressive enhancement: every row remains available without JavaScript.
    document.querySelectorAll('[data-season-expand]').forEach(button => {
        const container = document.getElementById(button.dataset.seasonExpand);
        if (!container) return;
        const items = Array.from(container.children);
        const label = button.textContent;
        items.forEach((item, index) => { if (index >= 25) item.classList.add('sr-hidden'); });
        button.hidden = false;
        button.addEventListener('click', function () {
            const expanding = button.getAttribute('aria-expanded') !== 'true';
            Array.from(container.children).forEach((item, index) => item.classList.toggle('sr-hidden', !expanding && index >= 25));
            button.setAttribute('aria-expanded', String(expanding));
            button.textContent = expanding ? 'Show less' : label;
            if (!expanding) container.scrollIntoView({ block: 'nearest' });
        });
    });

    const forms = Array.from(document.querySelectorAll('[data-season-form]'));
    const originalButtons = new Map();
    forms.forEach(form => {
        form.addEventListener('submit', function (event) {
            if (form.dataset.busy === '1') { event.preventDefault(); return; }
            if (form.hasAttribute('data-season-delete') && !window.confirm('Delete this season and disable its shared link? Your games will stay saved.')) {
                event.preventDefault(); return;
            }
            if (event.defaultPrevented) return;
            if (name && form.contains(name)) {
                name.value = name.value.trim();
                name.setCustomValidity(name.value ? '' : 'Give the season a name.');
                if (!form.reportValidity()) { event.preventDefault(); return; }
            }
            form.dataset.busy = '1';
            form.setAttribute('aria-busy', 'true');
            const submitter = event.submitter || form.querySelector('button[type="submit"]');
            // Disabled submitters are omitted from form data; preserve Start/Stop sharing.
            if (submitter && submitter.name) {
                const action = document.createElement('input');
                action.type = 'hidden'; action.name = submitter.name; action.value = submitter.value;
                action.setAttribute('data-season-submitter', '');
                form.appendChild(action);
            }
            form.querySelectorAll('button[type="submit"]').forEach(button => {
                originalButtons.set(button, button.innerHTML);
                button.disabled = true;
                if (button === submitter || !submitter) button.textContent = form.dataset.busyLabel || 'Saving…';
            });
        });
    });
    window.addEventListener('pageshow', function () {
        forms.forEach(form => {
            delete form.dataset.busy;
            form.removeAttribute('aria-busy');
            form.querySelectorAll('[data-season-submitter]').forEach(input => input.remove());
        });
        originalButtons.forEach((html, button) => { button.disabled = false; button.innerHTML = html; });
        originalButtons.clear();
        syncForm();
        restoreGroup();
    });
});
