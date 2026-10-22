/* Same-origin JSON APIs enforce authentication and reject cross-origin writes. */
(function () {
    'use strict';
    async function api(path, method, body) {
        const response = await fetch(path, {
            method: method || 'GET', credentials: 'same-origin', cache: 'no-store',
            headers: body === undefined ? {Accept: 'application/json'} : {'Content-Type': 'application/json', Accept: 'application/json'},
            body: body === undefined ? undefined : JSON.stringify(body)
        });
        let data;
        try { data = await response.json(); }
        catch (_) { throw new Error('The server could not complete this request. Please try again.'); }
        if (!response.ok) throw new Error(data.error || 'This request could not be completed.');
        return data;
    }
    function status(element, message, error) {
        element.textContent = message;
        element.classList.toggle('error', !!error);
    }
    function textElement(tag, text) {
        const element = document.createElement(tag);
        element.textContent = text;
        return element;
    }
    document.querySelectorAll('[data-ai-consent]').forEach(function (section) {
        const notice = section.querySelector('[data-consent-disclosure]');
        const output = section.querySelector('[data-consent-status]');
        const allow = section.querySelector('[data-consent-grant]');
        const withdraw = section.querySelector('[data-consent-withdraw]');
        let version;
        function show(data) {
            version = data.version;
            notice.textContent = data.disclosure;
            section.dataset.granted = data.granted ? 'true' : 'false';
            allow.disabled = data.granted;
            withdraw.disabled = !data.granted;
            status(output, data.granted ? 'AI sharing is on. You can turn it off at any time.' : 'AI sharing is off. Browsing and ordinary game tracking remain available.');
        }
        async function choose(granted) {
            if (!version) return;
            allow.disabled = withdraw.disabled = true;
            try { show(await api('/api/privacy/ai-consent', 'PUT', {version: version, granted: granted})); }
            catch (error) {
                status(output, error.message, true);
                allow.disabled = withdraw.disabled = false;
            }
        }
        allow.addEventListener('click', function () { choose(true); });
        withdraw.addEventListener('click', function () { choose(false); });
        api('/api/privacy/ai-consent').then(show).catch(function (error) {
            notice.textContent = 'The current privacy notice could not be loaded.';
            status(output, error.message, true);
        });
    });
    document.querySelectorAll('[data-content-report]').forEach(function (form) {
        const output = form.querySelector('[data-report-status]');
        const button = form.querySelector('button[type=submit]');
        form.addEventListener('submit', async function (event) {
            event.preventDefault();
            if (!form.reportValidity()) return;
            button.disabled = true;
            try {
                const result = await api('/api/content/report', 'POST', {
                    kind: form.dataset.kind, id: form.dataset.id, reason: form.elements.reason.value.trim()
                });
                status(output, result.message || 'Thank you. Your report is queued for review.');
                form.elements.reason.disabled = true;
            } catch (error) { status(output, error.message, true); button.disabled = false; }
        });
    });
    document.querySelectorAll('[data-block-author]').forEach(function (section) {
        const button = section.querySelector('[data-block-button]');
        const output = section.querySelector('[data-block-status]');
        button.addEventListener('click', async function () {
            button.disabled = true;
            try {
                await api('/api/content/blocked-users', 'POST', {username: section.dataset.blockAuthor});
                status(output, 'Author blocked. Manage your blocked list in Privacy and safety settings.');
            } catch (error) { status(output, error.message, true); button.disabled = false; }
        });
    });
    document.querySelectorAll('[data-blocked-users]').forEach(function (section) {
        const list = section.querySelector('[data-blocked-list]');
        const output = section.querySelector('[data-blocked-status]');
        function show(data) {
            list.replaceChildren();
            const users = data.users || [];
            status(output, users.length ? '' : 'No authors blocked.');
            users.forEach(function (user) {
                const item = document.createElement('li');
                item.append(textElement('span', user.display_name || user.username));
                const button = textElement('button', 'Unblock');
                button.type = 'button';
                button.addEventListener('click', async function () {
                    button.disabled = true;
                    try { show(await api('/api/content/blocked-users', 'DELETE', {username: user.username})); }
                    catch (error) { status(output, error.message, true); button.disabled = false; }
                });
                item.append(button); list.append(item);
            });
        }
        api('/api/content/blocked-users').then(show).catch(function (error) { status(output, error.message, true); });
    });
    document.querySelectorAll('[data-admin-reports]').forEach(function (section) {
        const list = section.querySelector('[data-reports-list]');
        const output = section.querySelector('[data-reports-status]');
        const refresh = section.querySelector('[data-reports-refresh]');
        async function load() {
            refresh.disabled = true;
            try {
                const data = await api('/api/admin/content-reports');
                list.replaceChildren();
                status(output, data.reports.length ? '' : 'No content reports.');
                data.reports.forEach(function (report) {
                    const card = document.createElement('article'); card.className = 'report-card';
                    card.append(textElement('h2', 'Report ' + report.id + ' · ' + report.status));
                    card.append(textElement('p', report.reason));
                    card.append(textElement('p', 'Author: ' + (report.author || 'Deleted account') + ' · ' + report.created_at));
                    if (report.kind === 'recap' || report.kind === 'flyer') {
                        const link = textElement('a', 'View reported ' + report.kind);
                        link.href = '/' + report.kind + '/' + encodeURIComponent(report.content_id) + '/';
                        link.target = '_blank'; link.rel = 'noopener'; card.append(link);
                    }
                    if (report.status === 'open') {
                        const actions = document.createElement('div'); actions.className = 'actions';
                        [['dismiss', 'Dismiss report'], ['hide', 'Remove content'], ['suspend', 'Suspend author']].forEach(function (pair) {
                            const button = textElement('button', pair[1]); button.type = 'button';
                            button.addEventListener('click', async function () {
                                if (pair[0] === 'suspend' && !window.confirm('Suspend this author and remove their shared content? They can still manage privacy and delete their account.')) return;
                                if (pair[0] === 'hide' && !window.confirm('Permanently remove this reported content?')) return;
                                button.disabled = true;
                                try { await api('/api/admin/content-reports/' + report.id, 'POST', {action: pair[0]}); await load(); }
                                catch (error) { status(output, error.message, true); button.disabled = false; }
                            });
                            actions.append(button);
                        });
                        card.append(actions);
                    }
                    list.append(card);
                });
            } catch (error) { status(output, error.message, true); }
            finally { refresh.disabled = false; }
        }
        refresh.addEventListener('click', load); load();
    });
}());
