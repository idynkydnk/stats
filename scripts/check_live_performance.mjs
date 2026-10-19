// Cloud-only browser measurements with real browser asset caching enabled.
import assert from 'node:assert/strict';
import { chromium, webkit } from 'playwright';
import { mkdir, writeFile } from 'node:fs/promises';

if (!process.env.GITHUB_ACTIONS) throw new Error('Run this browser check on GitHub Actions.');
const engine = process.env.BROWSER || 'chromium';
const browser = await ({ chromium, webkit }[engine]).launch();
const origin = 'https://idynkydnk.pythonanywhere.com';
const output = 'output/live-performance';
await mkdir(output, { recursive: true });
const reports = [], errors = [], interactions = [];
const paths = [
  ['standings', '/stats/2026/'], ['all-years', '/stats/All%20years/'],
  ['player', '/player/All%20years/Kyle%20Thomson/'], ['games', '/games/2026/'],
  ['vollis', '/vollis_stats/2026/'], ['other', '/other_stats/2026/'],
  ['volleyball', '/volleyball_stats/2026/'],
];

try {
  for (const width of [390, 1440]) {
    const context = await browser.newContext({ viewport: { width, height: 1000 },
      isMobile: width < 768, hasTouch: width < 768, colorScheme: 'dark' });
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
    page.on('pageerror', error => errors.push(String(error)));
    page.on('response', response => {
      if (response.url().startsWith(origin + '/static/') && response.status() >= 400) {
        errors.push(`Asset ${response.status()}: ${new URL(response.url()).pathname}`);
      }
    });
    page.on('request', req => { if (!['GET', 'HEAD'].includes(req.method())) errors.push('Unexpected write request'); });
    for (const [label, path] of paths) {
      let destination = origin + path;
      for (let visit = 0; visit < 4; visit++) {
        const response = await page.goto(destination, { waitUntil: 'load' });
        assert.equal(response.status(), 200, label);
        await page.waitForFunction(() => performance.getEntriesByType('navigation')[0].loadEventEnd > 0);
        destination = page.url();
        const timing = await page.evaluate(() => {
          const n = performance.getEntriesByType('navigation')[0];
          const resources = performance.getEntriesByType('resource');
          return { load_ms: Math.round(n.loadEventEnd), ttfb_ms: Math.round(n.responseStart - n.requestStart),
            dom_ready_ms: Math.round(n.domContentLoadedEventEnd), html_bytes: n.decodedBodySize,
            transfer_bytes: n.transferSize, server: n.serverTiming.map(t => ({ name: t.name, ms: t.duration })),
            assets_from_cache: resources.filter(r => r.transferSize === 0 && r.decodedBodySize > 0).length,
            slow_resources: resources.filter(r => new URL(r.name).origin === location.origin)
              .sort((a, b) => b.duration - a.duration).slice(0, 5)
              .map(r => ({ path: new URL(r.name).pathname, ms: Math.round(r.duration), bytes: r.transferSize })) };
        });
        reports.push({ engine, width, page: label, visit, page_cache: response.headers()['x-stats-page-cache'], ...timing });
      }
      if (label === 'player') {
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
        await page.screenshot({ path: `${output}/${engine}-${width}-player.png`, fullPage: false });
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
