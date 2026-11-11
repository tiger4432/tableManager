// The collector on the bench, in real Chrome (lead 11-07): the extension loaded unpacked, a template run on the fake
// webmail (opens in place, a hidden pane holding the last body, items that never open, a list that loads as it scrolls)
// and on the fake board (links, a Next button that moves the page). The counts are the bench's own (serve.py,
// webmail.js head): webmail 200 items, ids with id % 11 == 8 never open (18); board 5 pages x 20 posts.
//
//   P   picking on the page: a list item names its alike siblings, a column inside an item reads every item's own
//   T   a template saved and read back is the same template (sys_templates + sys_template_fields), a column taken out gone
//   W1  webmail: written 182 · not opened 18 · no key 0 · every row's content is its own item (reader id = item id)
//   W2  the same run again: nothing written, the 182 skipped unopened, the 18 tried again
//   R   Retry these on W1's 18 kept items: only they are opened again, 18 kept again, nothing written, ended at its count
//   W3  (paused a while mid-run: the count holds, then goes on) webmail with the pane closed after each read (hidden one of the bench's four ways in turn): the same counts
//   B1  board: written 100 · 5 pages · every row's content is its own post (post number = the listed number)
//   S   --who NAME: the key signs in as NAME (sign-in on) · --refused: NAME may not edit bench_mail - the whole run refused
//       with the server's sentence, nothing written · --webmail-only: P T W1 only
//   M   --mutant: the before/after comparison off -> rows read from the previous item's body (W1 red)
//   F   the frame bench (tests/frame_bench, owner 11-09): the list, clicks, content and Next inside a frame of the same
//       address on another path, Next loading the frame anew; a title and a body under two parents whose common one holds
//       the list, two mails in a row sharing a title. Picking in the frame names it · ↑ widens to the parent, ↓ narrows ·
//       Shift+click adds an area · a preview with no table or key · a run: written 36 over 3 pages, every row its own mail,
//       the frame the same frame (frameId) after its reloads · Delete on the panel card: the template's two tables'
//       rows gone, the collected rows and the run log kept. --frame-only: F alone
//       Hidden copies (a tab not open): the list, a body tab and Next have hidden copies under the same selector - the
//       shown one is read; two bodies shown, the one the click changed.
//       --ext-mutant frame: every message to the top frame (F red) · delete: the columns' rows left (D red) · shown:
//       a hidden copy counts as shown (F red)
//
// Chrome 137+ ignores --load-extension, so the extension is loaded over the DevTools pipe (Extensions.loadUnpacked).
// The product is a recording fake unless --server <address> --key <key> name a real one.
//
//   node browser_collector/tests/bench_run.mjs [--bench <tools/browser_bench dir>] [--port 8095] [--server URL --key KEY] [--mutant] [--shots DIR]
//        [--frame-only] [--ext-mutant frame|delete|shown]
import { spawn } from 'node:child_process';
import { cpSync, mkdtempSync, readFileSync, writeFileSync, rmSync, existsSync, mkdirSync } from 'node:fs';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Product } from '../lib/product.js';
import { patternOf } from '../lib/address.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const EXT = path.join(HERE, '..');
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const arg = (name, none = null) => { const i = process.argv.indexOf(name); return i > 0 ? process.argv[i + 1] : none; };
const BENCH_DIR = arg('--bench', path.join(HERE, '..', '..', 'tools', 'browser_bench'));
const BENCH_PORT = arg('--port', '8095');   // another lane's bench pages may hold 8095 - a different page version
const BENCH = `http://127.0.0.1:${BENCH_PORT}`;
const MUTANT = process.argv.includes('--mutant');
if (arg('--server') && !arg('--key')) throw new Error('--server needs --key - an empty key would ask as nobody');
const WHO = arg('--who');
const REFUSED = process.argv.includes('--refused');
const WEBMAIL_ONLY = process.argv.includes('--webmail-only') || REFUSED;
const SHOTS = arg('--shots');
const FRAME_ONLY = process.argv.includes('--frame-only');
const CROSS_ONLY = process.argv.includes('--cross-only');
const EXT_MUTANT = arg('--ext-mutant');
// --ext-mutant: one change to the extension copy - its anchor, its replacement
const EXT_MUTANTS = {
  frame: ['background.js', "  if (frame === '') return [0];", '  return [0];'],
  delete: ['background.js', '[[TABLES.fields, () => fieldRowsOf(p, t.name)], [TABLES.templates,', '[[TABLES.templates,'],
  shown: ['lib/open_check.js', 'return shown(el, win); });', 'return true; });'],
  settle: ['lib/page_dom.js', 'if (this.late && !(await waitStill(', 'if (false && !(await waitStill('],
  sticky: ['lib/page_dom.js', 'this.late = !o.opened;', 'this.late = this.late || !o.opened;'],
};
const pause = (ms) => new Promise((r) => setTimeout(r, ms));

let pass = 0;
const failures = [];
function eq(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { pass++; console.log(`  PASS ${name}`); } else { failures.push(name); console.log(`  FAIL ${name}\n        got  ${g}\n        want ${w}`); }
}

// ── a recording product ──────────────────────────────────────────────────────────────────
/** The keys the fake upserts on - the declarations' (server/declarations/table_config.json) and the bench tables'. */
const FAKE_KEYS = { sys_templates: ['template'], sys_template_fields: ['template', 'column'], sys_collect_runs: ['run_id'],
  sys_collect_misses: ['run_id', 'seq'], bench_mail: ['mail_id'], bench_mail_closed: ['mail_id'], bench_board: ['post_no'] };

function fakeProduct() {
  const tables = new Map();
  let made = 0;
  const rowsOf = (t) => { if (!tables.has(t)) tables.set(t, []); return tables.get(t); };
  const server = createServer((req, res) => {
    const u = new URL(req.url, 'http://x');
    const send = (code, body) => { res.writeHead(code, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(body)); };
    if (u.pathname === '/auth/me') return send(200, { user: 'bench', is_admin: false, sso: true });
    const gone = /^\/tables\/([^/]+)\/rows\/batch_delete$/.exec(u.pathname);
    const m = /^\/tables\/([^/]+)\/data(\/updates)?$/.exec(u.pathname);
    if (!m && !gone) return send(404, { detail: 'Not Found' });
    const table = decodeURIComponent((m || gone)[1]);
    if (req.method === 'GET') {
      const f = JSON.parse(u.searchParams.get('filters') || '{}');
      const data = rowsOf(table).filter((r) => Object.entries(f).every(([c, spec]) => spec.values.map(String).includes(String(r[c]))));
      return send(200, { data: data.map((r) => ({ row_id: r._id, data: Object.fromEntries(Object.entries(r).map(([c, v]) => [c, { value: v }])) })) });   // the real /data shape
    }
    let body = '';
    req.on('data', (c) => { body += c; });
    req.on('end', () => {
      const batch = JSON.parse(body);
      if (gone) { tables.set(table, rowsOf(table).filter((r) => !batch.row_ids.includes(r._id))); return send(200, { deleted: batch.row_ids.length }); }
      const keys = FAKE_KEYS[table] || [];
      for (const u2 of batch.updates) {
        const had = keys.length && rowsOf(table).find((r) => keys.every((k) => String(r[k]) === String(u2.updates[k])));
        if (had) Object.assign(had, u2.updates, { _source: u2.source_name });
        else rowsOf(table).push({ ...u2.updates, _source: u2.source_name, _id: String(++made) });
      }
      return send(200, { updated: batch.updates.length });
    });
    return undefined;
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve({ server, tables, url: `http://127.0.0.1:${server.address().port}` })));
}

// ── Chrome over the DevTools pipe ────────────────────────────────────────────────────────
function openChrome(profile) {
  const proc = spawn(CHROME, ['--headless=new', '--remote-debugging-pipe', '--enable-unsafe-extension-debugging', '--no-first-run',
    '--no-default-browser-check', `--user-data-dir=${profile}`, '--window-size=1920,1080', 'about:blank'], { stdio: ['ignore', 'ignore', 'ignore', 'pipe', 'pipe'] });
  const out = proc.stdio[3];
  const inn = proc.stdio[4];
  let id = 0;
  const waiting = new Map();
  let buf = '';
  inn.on('data', (chunk) => {
    buf += chunk.toString('utf8');
    for (let i = buf.indexOf('\0'); i >= 0; i = buf.indexOf('\0')) {
      const msg = JSON.parse(buf.slice(0, i));
      buf = buf.slice(i + 1);
      if (msg.id && waiting.has(msg.id)) { const w = waiting.get(msg.id); waiting.delete(msg.id); if (msg.error) w.reject(new Error(msg.error.message)); else w.resolve(msg.result); }
    }
  });
  const send = (method, params = {}, sessionId = undefined) => new Promise((resolve, reject) => {
    id += 1;
    waiting.set(id, { resolve, reject });
    out.write(`${JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) })}\0`);
  });
  return { proc, send };
}

async function page(chrome, url) {
  const { targetId } = await chrome.send('Target.createTarget', { url });
  const { sessionId } = await chrome.send('Target.attachToTarget', { targetId, flatten: true });
  const evaluate = async (expression) => {
    const r = await chrome.send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }, sessionId);
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception ? r.exceptionDetails.exception.description : r.exceptionDetails.text);
    return r.result.value;
  };
  for (let i = 0; ; i += 1) {         // the target answers before its page has loaded
    const at = await evaluate('location.href + " " + document.readyState').catch(() => '');
    if (at.startsWith(url) && at.endsWith('complete')) break;
    if (i > 100) throw new Error(`${url} did not load - ${at}`);
    await pause(200);
  }
  return { targetId, sessionId, evaluate };
}

async function shot(chrome, p, file, width, height) {
  if (!SHOTS) return;
  await chrome.send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false }, p.sessionId);
  const { data } = await chrome.send('Page.captureScreenshot', { format: 'png' }, p.sessionId);
  mkdirSync(SHOTS, { recursive: true });
  writeFileSync(path.join(SHOTS, file), Buffer.from(data, 'base64'));
}

// ── the templates ────────────────────────────────────────────────────────────────────────
const field = (column, base, selector, read = 'text', regex = '') => ({ column, base, selector, read, regex });
const WEBMAIL = {
  name: 'Bench webmail', address: `127.0.0.1:${BENCH_PORT}/webmail.html*`, frame: '', listArea: '#mail-list', item: '.mail-item', clickTarget: '',
  opens: 'in_place', content: '#reader', waitSeconds: 3, close: '', next: { how: 'scroll', selector: '' }, endSeconds: 3, max: 0,
  pair: null, pairText: '', keys: ['mail_id'], table: 'bench_mail',
  fields: [field('mail_id', 'item', '', '@data-id'), field('was_unread', 'item', '', '@class', '\\b(unread)\\b'),
    field('subject', 'content', '.reader-subject'), field('sender', 'content', '.reader-from'), field('received', 'content', '.reader-date'),
    field('reader_id', 'content', '.reader-id'), field('body', 'content', '.reader-body')],
};
const BOARD = {
  name: 'Bench board', address: `127.0.0.1:${BENCH_PORT}/board*`, frame: '', listArea: '', item: '.post-row', clickTarget: '.post-title a',
  opens: 'new_tab', content: '#post', waitSeconds: 5, close: '', next: { how: 'button', selector: '#next-page' }, endSeconds: 5, max: 0,
  pair: null, pairText: '', keys: ['post_no'], table: 'bench_board',
  fields: [field('post_no', 'item', '.post-no'), field('title', 'content', '.post-title'), field('author', 'content', '.post-author'),
    field('date', 'content', '.post-date'), field('read_no', 'content', '.post-no'), field('body', 'content', '.post-body')],
};

/** A table's rows as the product holds them - the recording fake's, or the real server's own answer. */
async function tableRows(product, name) {
  if (product) return product.tables.get(name) || [];
  return (await new Product({ server: arg('--server'), key: arg('--key') }).rows(name, {}, { limit: 5000 })).rows;
}

let shotsDone = false;     // the running shots are the first webmail run's
/** The tab's frames as [frameId, address]. */
const framesIn = (ext, tabId) => ext.evaluate(`chrome.scripting.executeScript({ target: { tabId: ${tabId}, allFrames: true }, func: () => location.href }).then((rs) => rs.map((r) => [r.frameId, r.result]))`);
async function runOn(chrome, ext, url, t, { pauseCheck = null, frames = null } = {}) {
  const tab = await page(chrome, url);
  await pause(1500);
  const tabId = await ext.evaluate(`chrome.tabs.query({}).then((ts) => ts.find((x) => x.url === ${JSON.stringify(url)}).id)`);
  await ext.evaluate(`window.__done = null; window.__last = null; window.__seen || (window.__seen = chrome.runtime.onMessage.addListener((m) => { if (m.type === 'run.progress') { window.__last = m; if (m.done) window.__done = m.tally; } }), true)`);
  if (frames) frames.before = await framesIn(ext, tabId);
  await ext.evaluate(`chrome.runtime.sendMessage({ type: 'run.start', tabId: ${tabId}, t: ${JSON.stringify(t)} })`);
  const end = Date.now() + 15 * 60 * 1000;
  let shotTaken = false;
  for (;;) {
    const done = await ext.evaluate('window.__done');
    if (done) {
      if (frames) frames.after = await framesIn(ext, tabId);
      await chrome.send('Target.closeTarget', { targetId: tab.targetId });
      return done;
    }
    if (!shotTaken && !shotsDone && t === WEBMAIL) { shotsDone = true; await pause(25000); await shot(chrome, tab, 'bench_webmail_running.png', 1920, 1080); await shot(chrome, ext, 'panel_running.png', 400, 800); shotTaken = true; }
    if (pauseCheck && !pauseCheck.done) {
      pauseCheck.done = true;
      await pause(6000);
      const runId = await ext.evaluate('window.__last && window.__last.runId');
      await ext.evaluate(`chrome.runtime.sendMessage({ type: 'run.pause', runId: '${runId}', on: true })`);
      for (let i = 0; i < 60 && !(await ext.evaluate('Boolean(window.__last && window.__last.tally.paused)')); i += 1) await pause(500);
      const r1 = await ext.evaluate('window.__last.tally.paused ? window.__last.tally.read : -1');
      await pause(4000);
      const r2 = await ext.evaluate('window.__last.tally.paused ? window.__last.tally.read : -2');
      await ext.evaluate(`chrome.runtime.sendMessage({ type: 'run.pause', runId: '${runId}', on: false })`);
      pauseCheck.held = r1 >= 0 && r1 === r2;
    }
    if (Date.now() > end) throw new Error(`${t.name}: no end in 15 minutes`);
    await pause(1000);
  }
}

// ── the frame bench ──────────────────────────────────────────────────────────────────────
/** tests/frame_bench served: the host page at /app/, its frame at /api/v2/mail?page=N - one address. */
function frameBench() {
  const files = { '/app/': 'host.html', '/api/v2/mail': 'mail.html' };
  const server = createServer((req, res) => {
    const f = files[new URL(req.url, 'http://x').pathname];
    if (!f) { res.writeHead(404); res.end(); return; }
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(readFileSync(path.join(HERE, 'frame_bench', f)));
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve({ server, url: `http://127.0.0.1:${server.address().port}` })));
}

/** The frame on another port (another origin): /x/?delay=MS is host.html whose frame is the other server's mail page. */
async function crossBench() {
  const other = await frameBench();
  const server = createServer((req, res) => {
    const u = new URL(req.url, 'http://x');
    if (u.pathname !== '/x/') { res.writeHead(404); res.end(); return; }
    const src = `${other.url}/api/v2/mail?${new URLSearchParams({ page: '1', delay: '150', ...Object.fromEntries(u.searchParams) })}`;
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(readFileSync(path.join(HERE, 'frame_bench', 'host.html'), 'utf8').replace('src="/api/v2/mail?page=1"', `src="${src}"`));
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  return { server, other, url: `http://127.0.0.1:${server.address().port}`, close: () => { server.close(); other.server.close(); } };
}

/** X - list and content in one frame of another origin, two content areas; each case's kept reasons as the panel says them. */
async function crossCases(chrome, ext, cb) {
  const frameHost = cb.other.url.replace('http://', '');
  const base = {
    name: 'Bench cross mail', address: `${cb.url.replace('http://', '')}/x/*`, frame: `${frameHost}/api/v2/mail*`, listArea: '.mail-list', item: 'li.mail-item',
    clickTarget: '', opens: 'in_place', content: '#reader-head, div.reader-body-pane', waitSeconds: 3, close: '', next: { how: 'button', selector: '.next-page' },
    endSeconds: 3, max: 0, pair: null, pairText: '', keys: ['mail_id'], table: '',
    fields: [field('mail_id', 'item', '', '@data-id'), field('title', 'content', '.reader-title'), field('reader_id', 'content', '.reader-id')],
  };
  const cases = [
    ['X1 two areas, opens in 0.15 s', 150, {}],
    ['X2 two areas, opens in 4 s (wait 3 s)', 4000, {}],
    ['X6 two areas, opens in 5 s (wait 3 s)', 5000, {}],
    ['X7 two areas, opens in 7 s (wait 3 s) - past twice the wait', 7000, {}],
    ['X8 one mail (#5) opens in 4 s among ones in 0.15 s', '150&slow=5', {}],
    ['X3 one area that two mails in a row share (the title)', 150, { content: '#reader-head' }],
    ['X4 frame pattern of the same port as the page', 150, { frame: `${cb.url.replace('http://', '')}/api/v2/mail*` }],
    ['X5 no frame pattern (the top page)', 150, { frame: '' }],
  ];
  const said = [];
  const got = {};
  for (const [label, delay, over] of cases) {
    const t = { ...base, ...over, table: `bench_cross_${said.length + 1}` };
    const began = Date.now();
    const r = await runOn(chrome, ext, `${cb.url}/x/?delay=${delay}`, t);
    const seconds = Math.round((Date.now() - began) / 1000);
    const tails = {};
    for (const m of r.misses) tails[m.detail] = (tails[m.detail] || 0) + 1;
    // a written row whose content is another mail's: the reader's id is not the item's
    const rows = await tableRows(cb.product, t.table);
    const wrong = rows.filter((x) => String(x.reader_id) !== String(x.mail_id)).map((x) => `${x.mail_id}<-${x.reader_id}`);
    const line = `${label}: written ${r.written} · kept ${r.misses.length} · ended ${r.ended}${r.detail ? ` (${r.detail})` : ''} · reasons ${JSON.stringify(tails)}`
      + ` · rows ${rows.length} · another mail's content ${wrong.length} ${JSON.stringify(wrong.slice(0, 12))} · ${seconds} s`;
    got[label.slice(0, 2)] = { rows: rows.length, wrong: wrong.length, kept: r.misses.length, seconds };
    console.log(`cross: ${line}`);
    said.push(line);
  }
  eq('X every case measured', said.length, cases.length);
  eq('X1 opens in time - 36 rows, each its own mail', [got.X1.rows, got.X1.wrong], [36, 0]);
  eq('X2 X6 opens later than the wait - no row holds the mail before it; every mail kept or its own',
    [got.X2.wrong, got.X2.rows + got.X2.kept, got.X6.wrong, got.X6.rows + got.X6.kept], [0, 36, 0, 36]);
  eq('X8 one slow mail kept, the ones after it written and their own, not each held a wait (under 60 s)',
    [got.X8.kept, got.X8.rows, got.X8.wrong, got.X8.seconds < 60], [1, 35, 0, true]);
}

async function frameCases(chrome, ext, ask, fb) {
  const host = fb.url.replace('http://', '');
  const FRAME = {
    name: 'Bench frame mail', address: `${host}/app/*`, frame: `${host}/api/v2/mail*`, listArea: '.mail-list', item: '.mail-item', clickTarget: '',
    opens: 'in_place', content: '', waitSeconds: 3, close: '', next: { how: 'button', selector: '.next-page' }, endSeconds: 3, max: 0,
    pair: null, pairText: '', keys: ['mail_id'], table: 'bench_frame_mail',
    fields: [field('mail_id', 'item', '', '@data-id'), field('title', 'content', '.reader-title'), field('reader_id', 'content', '.reader-id'),
      field('body', 'content', '.reader-text')],
  };
  const url = `${fb.url}/app/`;
  const tab = await page(chrome, url);
  const inFrame = (expr) => tab.evaluate(`(() => { const d = document.getElementById('app').contentDocument; return ${expr}; })()`);
  for (let i = 0; !(await inFrame("d.readyState === 'complete' && d.querySelectorAll('#mail-list .mail-item').length === 12")); i += 1) {
    if (i > 50) throw new Error('the frame did not load');
    await pause(200);
  }
  await pause(1000);
  const tabId = await ext.evaluate(`chrome.tabs.query({}).then((ts) => ts.find((x) => x.url === ${JSON.stringify(url)}).id)`);
  await ext.evaluate('window.__picked = null; chrome.runtime.onMessage.addListener((m) => { if (m.type === "pick.done") window.__picked = m; }); true');
  // a pick as a person's: the mouse over the element in the frame, the keys from the side panel, a click (Shift held or not)
  const pickIn = async (kind, t, selector, { keys = [], shift = false } = {}) => {
    await pause(500);         // the panel's unpick of the pick before - it stops every frame's picking
    await ext.evaluate('window.__picked = null');
    await ask({ type: 'tab.pick', tabId, kind, t });
    const [x, y] = await tab.evaluate(`(() => { const f = document.getElementById('app'); const o = f.getBoundingClientRect();
      const r = f.contentDocument.querySelector(${JSON.stringify(selector)}).getBoundingClientRect(); return [o.left + r.left + r.width / 2, o.top + r.top + r.height / 2]; })()`);
    await chrome.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y }, tab.sessionId);
    await pause(200);
    for (const key of keys) await ask({ type: 'tab.pick.key', tabId, key });
    for (const type of ['mousePressed', 'mouseReleased']) {
      await chrome.send('Input.dispatchMouseEvent', { type, x, y, button: 'left', clickCount: 1, modifiers: shift ? 8 : 0 }, tab.sessionId);
    }
    for (let i = 0; i < 50 && !(await ext.evaluate('window.__picked')); i += 1) await pause(100);
    return (await ext.evaluate('window.__picked')) || {};      // none: a red cell, not a crash
  };
  const item = await pickIn('item', { ...FRAME, item: '', fields: [] }, '.mail-subject');
  const widened = await pickIn('item', { ...FRAME, item: '', fields: [] }, '.mail-subject', { keys: ['ArrowUp'] });
  console.log(`frame: item ${JSON.stringify(item)} · item after one ↑ «${widened.selector}»`);
  eq('F a list item picked inside the frame - its frame named (the pattern the panel writes), its 12 alike siblings',
    [item.frame ? patternOf(item.frame) : null, item.count, await inFrame(`d.querySelector('#mail-list').querySelectorAll(${JSON.stringify(item.selector)}).length`)], [FRAME.frame, 12, 12]);
  eq('F ↑ on a list item\'s subject is the item - the same pick', [widened.selector, widened.count], [item.selector, item.count]);
  await inFrame("(d.querySelector('#mail-list .mail-item').click(), true)");     // a mail open, so the content area has a size
  await pause(600);
  const t = { ...FRAME, item: item.selector };
  const head = await pickIn('content', t, '.reader-title', { keys: ['ArrowUp'] });
  const bodyPane = await pickIn('content', t, '.reader-text', { keys: ['ArrowUp'], shift: true });
  const narrowed = await pickIn('content', t, '.reader-text', { keys: ['ArrowUp', 'ArrowDown'] });
  console.log(`frame: content ${head.selector} + ${bodyPane.selector} (add ${bodyPane.add}) · ↑↓ «${narrowed.selector}»`);
  eq('F ↑ widens the content pick to the parent - the title\'s box', [head.selector, head.add], ['#reader-head', false]);
  eq('F Shift+click adds an area - the body\'s box, said added; its selector names the three tabs (two hidden), not the one by its place',
    [bodyPane.selector, bodyPane.add, await inFrame(`d.querySelectorAll(${JSON.stringify(bodyPane.selector)}).length`)], ['div.reader-body-pane', true, 3]);
  eq('F ↓ narrows back to the element under the mouse', await inFrame(`d.querySelector(${JSON.stringify(narrowed.selector)}) === d.querySelector('.reader-text')`), true);
  const content = `${head.selector}, ${bodyPane.selector}`;          // the panel's merge of an added area

  await inFrame("([...d.querySelectorAll('.mail-item')].pop().click(), true)");   // the last mail open - the first five each change it
  await pause(600);
  const preview = await ask({ type: 'tab.preview', tabId, t: { ...t, content, table: '', keys: [] }, room: 5 });
  eq('F a preview with no table or key - not asked, five rows read, each its own mail', [preview.unchecked, (preview.rows || []).length,
    (preview.rows || []).filter((r) => r.cells.reader_id === r.cells.mail_id && r.cells.title !== null).length, (preview.misses || []).length], [true, 5, 5, 0]);
  await chrome.send('Target.closeTarget', { targetId: tab.targetId });

  const ft = { ...t, content };
  const frames = {};
  const f1 = await runOn(chrome, ext, url, ft, { frames });
  const rows = await tableRows(fb.product, ft.table);
  const mailFrame = (list) => (list || []).find(([, href]) => href.includes('/api/v2/mail')) || [];
  console.log(`frame: written ${f1.written} · pages ${f1.pages} · kept ${f1.misses.length} · ended ${f1.ended} · frames ${JSON.stringify(frames)}`);
  eq('F a run in the frame - written 36 over 3 pages (Next loads the frame anew), nothing kept, to the last page',
    [f1.written, f1.pages, f1.misses.length, f1.ended], [36, 3, 0, 'last page']);
  eq('F every row is its own mail - the id, the title (shared by two in a row) and the body read after opening',
    rows.filter((r) => r.reader_id !== r.mail_id || r.title !== `Thread ${Math.ceil(Number(r.mail_id) / 2)}` || r.body !== `Body of mail ${r.mail_id}`).length, 0);
  eq('F the frame is the same frame after its reloads - one frameId, page 1 then page 3',
    [mailFrame(frames.before)[0] === mailFrame(frames.after)[0] && mailFrame(frames.before)[0] > 0, (mailFrame(frames.before)[1] || '').endsWith('page=1'),
      (mailFrame(frames.after)[1] || '').endsWith('page=3')], [true, true, true]);

  // D - Delete on the panel's card, its confirm line, then Delete
  await ask({ type: 'template.save', t: ft });
  await ext.evaluate('location.reload(), true');
  const card = `[...document.querySelectorAll('.card')].find((c) => c.querySelector('.name').textContent === ${JSON.stringify(ft.name)})`;
  for (let i = 0; i < 100 && !(await ext.evaluate(`Boolean(${card})`).catch(() => false)); i += 1) await pause(200);   // the list read
  const press = (within, label) => ext.evaluate(`(() => { const c = ${within}; const b = c && [...c.querySelectorAll('button')].find((x) => x.textContent === ${JSON.stringify(label)}); if (b) b.click(); return Boolean(b); })()`);
  const asked = [await press(card, 'Delete'), await ext.evaluate(`(${card})?.querySelector('.alert .say')?.textContent ?? null`)];
  await press(`(${card})?.querySelector('.alert')`, 'Delete');
  for (let i = 0; i < 50 && (await ext.evaluate(`Boolean(${card})`)); i += 1) await pause(100);
  const left = async (table) => (await tableRows(fb.product, table)).filter((r) => r.template === ft.name).length;
  eq('D Delete asks once - the template, its columns and what stays', asked,
    [true, `Delete template ${ft.name} and its ${ft.fields.length} columns? Rows already collected stay`]);
  eq('D the template gone from the panel and from both tables; the collected rows and its run log stay',
    [await ext.evaluate(`Boolean(${card})`), await left('sys_templates'), await left('sys_template_fields'), (await tableRows(fb.product, ft.table)).length, await left('sys_collect_runs') > 0],
    [false, 0, 0, 36, true]);
}

// ── the run ──────────────────────────────────────────────────────────────────────────────
const profile = mkdtempSync(path.join(tmpdir(), 'collector-bench-'));
let extDir = EXT;
if (EXT_MUTANT) {
  if (!EXT_MUTANTS[EXT_MUTANT]) throw new Error(`--ext-mutant ${EXT_MUTANT}: none of ${Object.keys(EXT_MUTANTS)}`);
  extDir = mkdtempSync(path.join(tmpdir(), 'collector-ext-mutant-'));
  cpSync(EXT, extDir, { recursive: true, filter: (src) => !src.includes(`${path.sep}tests`) });
  const [file, from, to] = EXT_MUTANTS[EXT_MUTANT];
  const p = path.join(extDir, file);
  const text = readFileSync(p, 'utf8').replace(/\r\n/g, '\n');
  if (!text.includes(from)) throw new Error(`--ext-mutant ${EXT_MUTANT}: its anchor is not in ${file}`);
  writeFileSync(p, text.replace(from, to));
}
if (MUTANT) {
  extDir = mkdtempSync(path.join(tmpdir(), 'collector-ext-mutant-'));
  cpSync(EXT, extDir, { recursive: true, filter: (src) => !src.includes(`${path.sep}tests`) });
  const p = path.join(extDir, 'lib', 'open_check.js');
  const text = readFileSync(p, 'utf8');
  const from = "if (after === before) return 'content did not change';";
  if (!text.includes(from)) throw new Error('mutant anchor missing');
  writeFileSync(p, text.replace(from, ''));
}
let bench = null;
const product = arg('--server') ? null : await fakeProduct();
const chrome = openChrome(profile);
try {
  if (!FRAME_ONLY) try { await fetch(`${BENCH}/`); } catch {
    if (!existsSync(path.join(BENCH_DIR, 'serve.py'))) throw new Error(`no bench at ${BENCH_DIR}`);
    bench = spawn('C:/Users/kk980/anaconda3/envs/assy_manager/python.exe', [path.join(BENCH_DIR, 'serve.py'), BENCH_PORT], { stdio: 'ignore' });
    await pause(1500);
  }
  const { id } = await chrome.send('Extensions.loadUnpacked', { path: extDir });
  const ext = await page(chrome, `chrome-extension://${id}/panel/panel.html`);
  await ext.evaluate(`chrome.storage.local.set(${JSON.stringify({ server: arg('--server') || product.url, key: arg('--key') || 'bench-key' })})`);

  const ask = (msg) => ext.evaluate(`chrome.runtime.sendMessage(${JSON.stringify(msg)}).then((a) => a.ok ? a.value : { error: a.error })`);
  if (CROSS_ONLY) {
    const cb = await crossBench();
    try { await crossCases(chrome, ext, { ...cb, product }); } finally { cb.close(); }
  } else if (FRAME_ONLY) {
    const fb = await frameBench();
    try { await frameCases(chrome, ext, ask, { ...fb, product }); } finally { fb.server.close(); }
  } else {
  if (!REFUSED) {             // a person who may not edit the table may not save its template either
  await ask({ type: 'template.save', t: { ...WEBMAIL, fields: [...WEBMAIL.fields, field('dropped', 'item', '.mail-from')] } });
  const saved = await ask({ type: 'template.save', t: WEBMAIL });      // saved again without «dropped»
  const listed = await ask({ type: 'templates.list' });
  const back = listed.ok && listed.templates.find((x) => x.name === WEBMAIL.name);
  eq('T a template saved and read back is the same template', [saved.ok, back ? { ...back, pair: null, pairText: '' } : listed], [true, WEBMAIL]);
  }

  if (WHO) {
    const me = await ask({ type: 'whoami' });
    eq(`S the key signs in as ${WHO}`, [me.ok, me.user], [true, WHO]);
  }
  if (REFUSED) {
    const rowsBefore = (await tableRows(product, 'bench_mail')).length;
    const w = await runOn(chrome, ext, `${BENCH}/webmail.html`, WEBMAIL);
    eq('S not allowed - the whole run refused with the server sentence, nothing written',
      [w.ended, w.detail, w.written, (await tableRows(product, 'bench_mail')).length - rowsBefore],
      ['refused', `${WHO} may not edit the table bench_mail - an administrator adds the name to access.edit.allow in table_config.json`, 0, 0]);
    await shot(chrome, ext, 'panel_refused.png', 400, 800);
  } else {
  // P - picking: a click on the page, as a person's, through the overlay
  const mailTab = await page(chrome, `${BENCH}/webmail.html`);
  await pause(1500);
  const mailTabId = await ext.evaluate(`chrome.tabs.query({}).then((ts) => ts.find((x) => x.url === '${BENCH}/webmail.html').id)`);
  await ext.evaluate('window.__picked = null; chrome.runtime.onMessage.addListener((m) => { if (m.type === "pick.done") window.__picked = m; }); true');
  const pickAt = async (kind, t, selector) => {
    await ext.evaluate('window.__picked = null');
    await ask({ type: 'tab.pick', tabId: mailTabId, kind, t });
    const at = await mailTab.evaluate(`(() => { const r = document.querySelectorAll(${JSON.stringify(selector)})[2].getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })()`);
    for (const type of ['mouseMoved', 'mousePressed', 'mouseReleased']) {
      await chrome.send('Input.dispatchMouseEvent', { type, x: at[0], y: at[1], button: 'left', clickCount: 1 }, mailTab.sessionId);
    }
    for (let i = 0; i < 50 && !(await ext.evaluate('window.__picked')); i += 1) await pause(100);
    return ext.evaluate('window.__picked');
  };
  const base = { ...WEBMAIL, item: '', fields: [] };
  const item = await pickAt('item', base, '.mail-item');
  console.log(`picked item: ${JSON.stringify(item)}`);
  const named = await mailTab.evaluate(`[...document.querySelector('#mail-list').querySelectorAll(${JSON.stringify(item.selector)})].length + ' of ' + document.querySelectorAll('.mail-item').length`);
  const subject = await pickAt('column', { ...base, item: item.selector }, '.mail-subject');
  console.log(`picked subject: ${JSON.stringify(subject)}`);
  const read = await mailTab.evaluate(`(() => { const items = [...document.querySelector('#mail-list').querySelectorAll(${JSON.stringify(item.selector)})];
    return items.filter((el) => { const s = el.querySelector(${JSON.stringify(subject.selector)}); return s && s.innerText === el.querySelector('.mail-subject').innerText; }).length; })()`);
  console.log(`picked: item «${item.selector}» (${named}) · subject «${subject.selector}» base ${subject.base}`);
  eq('P a list item picked names its alike siblings - every item on the page, the third clicked', [named.split(' of ')[0] === named.split(' of ')[1], item.count], [true, Number(named.split(' of ')[1])]);
  eq('P a column picked inside an item is read before opening and reads every item own', [subject.base, read], ['item', Number(named.split(' of ')[1])]);
  await chrome.send('Target.closeTarget', { targetId: mailTab.targetId });

  const w1 = await runOn(chrome, ext, `${BENCH}/webmail.html`, WEBMAIL);
  await shot(chrome, ext, 'panel_done.png', 400, 800);
  const mailRows = await tableRows(product, 'bench_mail');
  const count = (tally, r) => tally.misses.filter((m) => m.reason === r).length;
  console.log(`webmail: written ${w1.written} · skipped ${w1.skipped} · not opened ${count(w1, 'not_opened')} · no key ${count(w1, 'no_key')} · refused ${count(w1, 'refused')} · ended ${w1.ended}`);
  eq('W1 webmail - written 182, not opened 18 (id % 11 == 8), no key 0, refused 0, to the end of the list',
    [w1.written, count(w1, 'not_opened'), count(w1, 'no_key'), count(w1, 'refused'), w1.ended], [182, 18, 0, 0, 'last page']);
  eq('W1 the ones not opened are exactly id % 11 == 8', w1.misses.filter((m) => m.reason === 'not_opened').map((m) => Number(m.cells.mail_id)).sort((a, b) => a - b),
    Array.from({ length: 200 }, (_, i) => i + 1).filter((i) => i % 11 === 8));
  {
    eq('W1 every row is its own item - the reader id read after opening is the item id read before', mailRows.filter((r) => r.reader_id !== r.mail_id).length, 0);
    console.log(`webmail: was_unread on ${mailRows.filter((r) => r.was_unread === 'unread').length} of ${mailRows.length} rows · layer «${mailRows[0] && mailRows[0]._source}»`);
  }
  if (!MUTANT && !WEBMAIL_ONLY) {
    const w2 = await runOn(chrome, ext, `${BENCH}/webmail.html`, WEBMAIL);
    eq('W2 the same run again - nothing written, 182 skipped unopened, the 18 tried again', [w2.written, w2.skipped, count(w2, 'not_opened')], [0, 182, 18]);
    const kept = w1.misses.filter((m) => m.reason === 'not_opened');
    const rt = await runOn(chrome, ext, `${BENCH}/webmail.html`, { ...WEBMAIL, only: kept.map((m) => m.cells), max: kept.length });
    eq('R Retry these - only the 18 kept opened again, kept again, nothing written, ended at its count',
      [rt.read, count(rt, 'not_opened'), rt.written, rt.ended], [18, 18, 0, 'limit']);
    const held = {};
    const w3 = await runOn(chrome, ext, `${BENCH}/webmail.html`, { ...WEBMAIL, close: '#reader-close', table: 'bench_mail_closed' }, { pauseCheck: held });
    eq('W3 a pause holds the count between batches, and the run goes on after', held.held, true);
    eq('W3 closed after each read - written 182, not opened 18', [w3.written, count(w3, 'not_opened'), count(w3, 'no_key')], [182, 18, 0]);
    eq('W3 every row is its own item', (await tableRows(product, 'bench_mail_closed')).filter((r) => r.reader_id !== r.mail_id).length, 0);
    const b1 = await runOn(chrome, ext, `${BENCH}/board`, BOARD);
    console.log(`board: written ${b1.written} · pages ${b1.pages} · kept ${b1.misses.length} · ended ${b1.ended}`);
    eq('B1 board - written 100 over 5 pages, nothing kept', [b1.written, b1.pages, b1.misses.length, b1.ended], [100, 5, 0, 'last page']);
    eq('B1 every row is its own post', (await tableRows(product, 'bench_board')).filter((r) => r.read_no !== r.post_no).length, 0);
    const runs = await tableRows(product, 'sys_collect_runs');
    const misses = await tableRows(product, 'sys_collect_misses');
    eq('L the run log (one row per run id) - five runs, their counts, and the 72 kept items with their reasons and sentences', [runs.length, runs.map((r) => Number(r.written)).sort((a, b) => a - b),
      misses.length, [...new Set(misses.map((m) => m.reason))], [...new Set(misses.map((m) => m.detail))].sort()], [5, [0, 0, 100, 182, 182], 72, ['not_opened'], ['content did not change in 3 s', 'content not shown in 3 s']]);
    const fb = await frameBench();
    try { await frameCases(chrome, ext, ask, { ...fb, product }); } finally { fb.server.close(); }
  }
  }
  }
} finally {
  chrome.proc.kill();
  if (bench) bench.kill();
  if (product) product.server.close();
  // a killed Chrome's children hold its cache a moment longer - try again, then say what stayed
  for (const dir of [profile, ...(extDir !== EXT ? [extDir] : [])]) {
    for (let i = 0; ; i += 1) {
      await pause(800);
      try { rmSync(dir, { recursive: true, force: true }); break; } catch (e) { if (i === 9) { console.log(`left ${dir} - ${e.code}`); break; } }
    }
  }
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
