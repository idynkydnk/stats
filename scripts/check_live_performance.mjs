// Cloud-only browser measurements with real browser asset caching enabled.
import assert from 'node:assert/strict';
import { chromium, webkit } from 'playwright';
import { mkdir, writeFile } from 'node:fs/promises';

if (!process.env.GITHUB_ACTIONS) throw new Error('Run this browser check on GitHub Actions.');
const engine = process.env.BROWSER || 'chromium';
const browser = await ({ chromium, webkit }[engine]).launch();
const origin = 'https://idynkydnk.pythonanywhere.com';
const output = process.env.PERFORMANCE_OUTPUT || 'output/live-performance';
const signedIn = Boolean(process.env.STATS_TEST_TOKEN);
await mkdir(output, { recursive: true });
const reports = [], errors = [], interactions = [];
const paths = [
  ['standings', '/stats/2026/'], ['all-years', '/stats/All%20years/'],
  ['player', '/player/All%20years/Kyle%20Thomson/'], ['games', '/games/2026/'],
  ['vollis', '/vollis_stats/2026/'], ['other', '/other_stats/2026/'],
  ['volleyball', '/volleyball_stats/2026/'],
];
if (signedIn) paths.push(['add-game', '/add_game/'], ['players', '/player_list/'],
  ['sources', '/account/stats-sources/'], ['admin', '/admin/']);

try {
  for (const width of [390, 1440]) {
    const context = await browser.newContext({ viewport: { width, height: 1000 },
      isMobile: width < 768, hasTouch: width < 768, colorScheme: 'dark' });
    if (signedIn) await context.addCookies([{ name: 'remember_token', value: process.env.STATS_TEST_TOKEN,
      url: origin, httpOnly: true, secure: true, sameSite: 'Lax' }]);
    // Routing every request disables Playwright's browser HTTP cache. Block the
    // site's optional writes in JS instead, leaving genuine asset reuse enabled.
    await context.addInitScript(() => {
      const originalFetch = window.fetch.bind(window);
      window.fetch = (input, options = {}) => {
        const method = options.method || (input instanceof Request ? input.method : 'GET');
        if (!['GET', 'HEAD'].includes(method.toUpperCase())) return Promise.resolve(new Response(null, { status: 204 }));
        return originalFetch(input, options);
      };
      navigator.sendBeacon = () => true;
      document.addEventListener('submit', event => event.preventDefault(), true);
    });
    const page = await context.newPage();
    const requestPaths = [];
    page.on('pageerror', error => errors.push(String(error)));
    page.on('response', response => {
      if (response.url().startsWith(origin + '/static/') && response.status() >= 400) {
        errors.push(`Asset ${response.status()}: ${new URL(response.url()).pathname}`);
      }
    });
    page.on('request', req => {
      requestPaths.push(new URL(req.url()).pathname);
      if (!['GET', 'HEAD'].includes(req.method())) errors.push('Unexpected write request');
    });
    for (const [label, path] of paths) {
      let destination = origin + path;
      let originalHTML;
      requestPaths.length = 0;
      for (let visit = 0; visit < 4; visit++) {
        const forceRender = process.env.FORCE_RENDER_FIRST === '1' && visit === 0;
        await page.setExtraHTTPHeaders(forceRender ? { 'Cache-Control': 'no-cache' } : {});
        const response = await page.goto(destination, { waitUntil: 'load' });
        originalHTML = await response.text();
        assert.equal(response.status(), 200, label);
        if (signedIn) assert.ok(await page.locator('.menu-account-status').filter({ hasText: 'Signed in as' }).count(), 'Signed-in account chrome');
        await page.waitForFunction(() => performance.getEntriesByType('navigation')[0].loadEventEnd > 0);
        if (await page.evaluate(() => PerformanceObserver.supportedEntryTypes.includes('paint'))) {
          await page.waitForFunction(() => performance.getEntriesByName('first-contentful-paint').length > 0);
        }
        destination = page.url();
        const timing = await page.evaluate(() => {
          const n = performance.getEntriesByType('navigation')[0];
          const resources = performance.getEntriesByType('resource');
          return { load_ms: Math.round(n.loadEventEnd), ttfb_ms: Math.round(n.responseStart - n.requestStart),
            first_paint_ms: performance.getEntriesByName('first-contentful-paint').length ? Math.round(performance.getEntriesByName('first-contentful-paint')[0].startTime) : null,
            dom_ready_ms: Math.round(n.domContentLoadedEventEnd), html_bytes: n.decodedBodySize,
            transfer_bytes: n.transferSize, server: n.serverTiming.map(t => ({ name: t.name, ms: t.duration })),
            assets_from_cache: resources.filter(r => r.transferSize === 0 && r.decodedBodySize > 0).length,
            slow_resources: resources.filter(r => new URL(r.name).origin === location.origin)
              .sort((a, b) => b.duration - a.duration).slice(0, 5)
              .map(r => ({ path: new URL(r.name).pathname, ms: Math.round(r.duration), bytes: r.transferSize })) };
        });
        reports.push({ engine, width, page: label, visit, signed_in: signedIn, render_required: forceRender,
          page_cache: response.headers()['x-stats-page-cache'], ...timing });
      }
      if (label === 'standings' || label === 'all-years') {
        const counts = await page.evaluate(html => {
          const source = new DOMParser().parseFromString(html, 'text/html');
          const originals = Array.from(source.querySelectorAll('.sr-standings-table'));
          const live = Array.from(document.querySelectorAll('.sr-standings-table'));
          return originals.map((table, index) => {
            const payload = source.getElementById(table.dataset.standingsRows);
            const records = payload ? JSON.parse(payload.textContent) : [];
            const actual = Array.from(live[index].tBodies[0].rows);
            if (actual.length !== table.tBodies[0].rows.length + records.length) throw new Error('Incomplete standings');
            for (const [name, wins, losses, fraction, rating, ratingLabel, percentageLabel] of records) {
              const row = actual.find(row => row.cells[1].textContent === name);
              if (!row || Number(row.cells[3].dataset.value) !== wins || Number(row.cells[4].dataset.value) !== losses
                  || Number(row.cells[5].dataset.value) !== fraction || Number(row.cells[2].dataset.value) !== rating
                  || row.cells[2].textContent !== ratingLabel || row.cells[5].textContent !== percentageLabel + '%'
                  || new URL(row.cells[1].querySelector('a').href).search !== new URL(table.dataset.playerUrl, location.href).search) {
                throw new Error('Standings value/link changed');
              }
            }
            return actual.length;
          });
        }, originalHTML);
        for (let index = 0; index < counts.length; index++) {
          const table = page.locator('.sr-standings-table').nth(index);
          await table.locator('th[data-sort="wins"]').click();
          assert.equal(await table.locator('tbody tr').count(), counts[index]);
        }
        interactions.push({ width, page: label, complete_standings: true, counts });
      }
      if (label === 'player') {
        if (signedIn && originalHTML.includes('pendingPageConfig = cfg')) {
          assert.ok(!requestPaths.some(path => path.startsWith('/api/player_ai_image/')), 'Closed editor must not load AI history');
          await page.locator('#player-avatar-trigger').click();
          await page.waitForFunction(() => !document.getElementById('player-photo-modal').hidden);
          assert.equal(await page.locator('#player-detail-name').inputValue(), 'Kyle Thomson');
          await page.locator('.sr-photo-modal-backdrop').click({ position: { x: 2, y: 2 } });
          assert.equal(await page.locator('#player-photo-modal').isVisible(), false);
          interactions.push({ width, photo_editor_opens_on_demand: true });
        }
        const original = await page.evaluate(() => ['partner', 'opponent'].map(kind => {
          const tbody = document.getElementById(kind + '-tbody');
          const deferred = document.getElementById(kind + '-extra-rows');
          const records = deferred ? JSON.parse(deferred.textContent) : [];
          return { kind, initial: tbody.rows.length, records, total: tbody.rows.length + records.length };
        }));
        for (const { kind, initial, records, total } of original) {
          assert.ok(initial <= 10, 'Only visible rows are built initially');
          if (!records.length) continue;
          const table = page.locator(`#${kind}-tbody`).locator('..');
          // Sort before expansion: all hidden records must participate too.
          await table.locator('th[data-sort="wins"]').click();
          assert.equal(await page.locator(`#${kind}-tbody tr`).count(), total);
          assert.equal(await page.locator(`#${kind}-tbody tr:not(.sr-hidden)`).count(), 10);
          const actual = await page.locator(`#${kind}-tbody`).evaluate(tbody => Array.from(tbody.rows).map(row => ({
            name: row.cells[1].textContent, percentage: row.cells[2].textContent,
            wins: Number(row.cells[3].dataset.value), losses: Number(row.cells[4].dataset.value),
            games: Number(row.dataset.games), href: row.cells[1].querySelector('a').href })));
          for (const [name, , wins, losses, games, , , percentage] of records) {
            const row = actual.find(row => row.name === name);
            assert.ok(row, name);
            assert.deepEqual([row.wins, row.losses, row.games, row.percentage], [wins, losses, games, percentage + '%']);
            assert.equal(new URL(row.href).searchParams.get('view'), new URL(page.url()).searchParams.get('view'));
          }
          const button = page.locator(`[onclick="toggleRows('${kind}-tbody', this)"]`);
          await button.click();
          assert.equal(await page.locator(`#${kind}-tbody tr:not(.sr-hidden)`).count(), total);
          await button.click();
          assert.equal(await page.locator(`#${kind}-tbody tr:not(.sr-hidden)`).count(), 10);
          interactions.push({ width, kind, total, complete_sort_and_expand: true });
        }
        if (!signedIn) await page.screenshot({ path: `${output}/${engine}-${width}-player.png`, fullPage: false });
      }
    }
    await context.close();
  }
  assert.deepEqual(errors, [], 'Browser errors');
} finally {
  await writeFile(`${output}/report.json`, JSON.stringify({ engine, reports, interactions, errors }, null, 2));
  await browser.close();
}
for (const [label] of paths) {
  const values = reports.filter(r => r.page === label && r.visit > 0).map(r => r.load_ms).sort((a, b) => a - b);
  console.log(`${label}: repeat median ${values[Math.floor(values.length / 2)]} ms`);
}
