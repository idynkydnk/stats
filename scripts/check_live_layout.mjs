// Run only on a cloud runner: never launches a browser on the user's computer.
import { chromium, webkit } from 'playwright';
import { mkdir, readFile, writeFile } from 'node:fs/promises';

if (!process.env.GITHUB_ACTIONS) throw new Error('Run this browser check on GitHub Actions.');
const candidate = process.env.CANDIDATE === 'true';
const engine = process.env.BROWSER || 'chromium';
const browser = await ({ chromium, webkit }[engine]).launch();
const origin = 'https://idynkydnk.pythonanywhere.com';
const out = 'output/live-layout';
await mkdir(out, { recursive: true });
const css = await readFile('static/css/stats.css', 'utf8');
const pages = [
  ['doubles', '/stats/2026/'],
  ['all-years', '/stats/All%20years/'],
  ['player', '/player/All%20years/Kyle%20Thomson/'],
  ['games', '/games/2026/'],
  ['vollis', '/vollis_stats/2026/'],
  ['other', '/other_stats/2026/'],
  ['volleyball', '/volleyball_stats/2026/'],
];
const reports = [];
const failures = [];
try {
  for (const width of [320, 360, 375, 390, 430, 768, 1440]) {
    const context = await browser.newContext({ viewport: { width, height: 1000 }, deviceScaleFactor: 1,
      isMobile: width < 768, hasTouch: width < 768, colorScheme: 'dark' });
    // Reading only: don't let visits set timezone or submit any other changes.
    await context.route('**/*', async route => {
      const request = route.request();
      if (!['GET', 'HEAD'].includes(request.method())) return route.abort();
      if (candidate && new URL(request.url()).pathname === '/static/css/stats.css') {
        return route.fulfill({ status: 200, contentType: 'text/css', body: css });
      }
      return route.continue();
    });
    const page = await context.newPage();
    await page.addInitScript(() => {
      window.qaLCP = 0;
      try { new PerformanceObserver(list => { for (const entry of list.getEntries()) window.qaLCP = entry.startTime; })
        .observe({ type: 'largest-contentful-paint', buffered: true }); } catch (_) {}
    });
    for (const [name, path] of pages) {
      const response = await page.goto(origin + path, { waitUntil: 'load', timeout: 60000 });
      await page.evaluate(() => document.fonts.ready);
      const todayFixture = name === 'doubles' && await page.evaluate(() => {
        if (document.querySelector('#today-stats-tbody')) return false;
        const season = document.querySelector('#sr-table');
        if (!season) return false;
        // The live day can have no games. Still check all five numeric columns
        // using the season's actual row markup, with a clearly marked fixture.
        const table = season.cloneNode(true);
        table.id = 'qa-today-table';
        table.querySelector('th[data-sort="rating"]').innerHTML = 'Rating <span class="sr-sort-arrow">▼</span>';
        const header = document.createElement('th');
        header.className = 'sr-numeric'; header.dataset.sort = 'plusminus'; header.textContent = '+/-';
        table.querySelector('thead tr').append(header);
        const body = table.querySelector('tbody'); body.id = 'today-stats-tbody';
        const row = body.querySelector('tr');
        body.replaceChildren(row);
        row.querySelector('.sr-rating').textContent = '100.00';
        row.querySelector('.sr-win').textContent = '12';
        row.querySelector('.sr-loss').textContent = '34';
        row.querySelector('.sr-winpct').textContent = '100%';
        const differential = document.createElement('td');
        differential.className = 'sr-numeric'; differential.textContent = '-137';
        row.append(differential);
        season.before(table);
        return true;
      });
      const checkLayout = () => page.evaluate(() => {
        const issues = [];
        const tables = [...document.querySelectorAll('.sr-table:has(th[data-column="player"])')];
        for (const [i, table] of tables.entries()) {
          const wrap = table.parentElement;
          if (wrap.scrollWidth > wrap.clientWidth + 1) issues.push(`table ${i} scrolls ${wrap.scrollWidth - wrap.clientWidth}px`);
          for (const cell of table.querySelectorAll('th, td')) {
            if (!cell.getClientRects().length) continue;
            const rect = cell.getBoundingClientRect();
            if (rect.left < -1 || rect.right > innerWidth + 1) issues.push(`offscreen ${cell.textContent.trim().slice(0, 25)}`);
            // Range bounds detect clipped/overlapping numbers, not just table overflow.
            if (cell.matches('td.sr-numeric')) {
              const range = document.createRange(); range.selectNodeContents(cell);
              const text = range.getBoundingClientRect();
              if (text.left < rect.left - 1 || text.right > rect.right + 1) issues.push(`number doesn't fit: ${cell.textContent.trim()}`);
            }
          }
        }
        if (document.documentElement.scrollWidth > innerWidth + 1) issues.push('page has horizontal overflow');
        return { issues: [...new Set(issues)], tables: tables.length, today: !!document.querySelector('#today-stats-tbody'),
          headers: tables[0] ? [...tables[0].querySelectorAll('th')].map(el => el.textContent.trim().slice(0, 12)) : [] };
      });
      const layout = await checkLayout();
      if (name === 'doubles') {
        if (width >= 360 && width <= 430) {
          // Use the actual standings markup with the names from the reported
          // regression, independently of who currently qualifies for this table.
          const names = await page.evaluate(() => {
            const table = document.querySelector('#sr-table');
            if (!table) return { issues: ['Missing season standings for name check'] };
            const row = table.querySelector('tbody tr');
            if (!row) return { issues: ['Missing player row for name check'] };
            const issues = [];
            const measurements = [];
            for (const name of ['James Lightner', 'Matt Sokolowski']) {
              const fixture = row.cloneNode(true);
              fixture.querySelector('.sr-player a').textContent = name;
              fixture.dataset.qaName = name;
              row.parentElement.prepend(fixture);
              const link = fixture.querySelector('.sr-player a');
              const range = document.createRange(); range.selectNodeContents(link);
              const bounds = range.getBoundingClientRect();
              const lineHeight = parseFloat(getComputedStyle(link).lineHeight);
              if (bounds.height > lineHeight + 1) issues.push(`${name} wraps at ${innerWidth}px`);
              const cell = link.closest('td').getBoundingClientRect();
              measurements.push({ name, cellWidth: cell.width, textHeight: bounds.height, lineHeight });
              if (bounds.left < cell.left || bounds.right > cell.right) issues.push(`${name} exceeds its column`);
            }
            return { issues, measurements };
          });
          if (names.issues.length) failures.push({ width, ...names });
          await page.evaluate(() => {
            document.documentElement.classList.add('sr-light');
            document.documentElement.dataset.srPalette = 'sunset';
          });
          const screenshotCrop = await page.addStyleTag({ content: '#sr-table tbody tr:nth-child(n+13) { display: none !important; }' });
          await page.locator('#sr-table').screenshot({ path: `${out}/${engine}-${width}-player-names-light.png`, animations: 'disabled' });
          await screenshotCrop.evaluate(el => el.remove());
          await page.evaluate(() => {
            document.querySelectorAll('[data-qa-name]').forEach(row => row.remove());
            document.documentElement.classList.remove('sr-light');
            document.documentElement.dataset.srPalette = 'ocean';
            window.scrollTo(0, 0);
          });
        }
        if ([320, 375, 1440].includes(width)) await page.screenshot({ path: `${out}/${engine}-${width}-doubles.png`, animations: 'disabled' });
        await page.evaluate(() => document.documentElement.classList.add('sr-light'));
        const light = await checkLayout();
        if (light.issues.length) failures.push({ width, theme: 'light', ...light });
        if ([320, 375, 1440].includes(width)) await page.screenshot({ path: `${out}/${engine}-${width}-doubles-light.png`, animations: 'disabled' });
        await page.evaluate(() => document.documentElement.classList.remove('sr-light'));
      }
      const performance = await page.evaluate(() => {
        const n = performance.getEntriesByType('navigation')[0];
        return { ttfb: Math.round(n.responseStart - n.requestStart), load: Math.round(n.loadEventEnd),
          lcp: Math.round(window.qaLCP), htmlBytes: n.decodedBodySize,
          resources: performance.getEntriesByType('resource').length };
      });
      const report = { engine, candidate, width, page: name, status: response.status(), todayFixture, ...layout, performance };
      reports.push(report);
      if (response.status() !== 200 || layout.issues.length) failures.push(report);
      if (name === 'doubles' && !layout.today) failures.push({ width, error: 'No live today stats to verify' });
      if (name !== 'doubles' && [375, 1440].includes(width)) {
        await page.screenshot({ path: `${out}/${engine}-${width}-${name}.png`, fullPage: false, animations: 'disabled' });
      }
      if (name === 'doubles' && !todayFixture) {
        for (const sort of ['wins', 'losses', 'winpct', 'plusminus', 'rating']) {
          const header = page.locator(`#today-stats-tbody`).locator('..').locator(`th[data-sort="${sort}"]`);
          if (await header.count()) { await header.click(); const sorted = await checkLayout();
            if (sorted.issues.length) failures.push({ width, sort, ...sorted }); }
        }
      }
    }
    await context.close();
  }
} finally {
  await browser.close();
  await writeFile(`${out}/report.json`, JSON.stringify({ reports, failures }, null, 2));
  console.log(JSON.stringify({ reports, failures }, null, 2));
}
if (failures.length) process.exitCode = 1;
