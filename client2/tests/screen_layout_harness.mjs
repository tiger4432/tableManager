#!/usr/bin/env node
// Every screen, opened in real Chrome before a screen commit lands (lead 1343e5cca; owner 10-09 「이런 잘림 같은 ui
// 요소는 사전에 차단하면 안 됨?」). Each html entry in the built dist is opened at each size, driven through its states,
// and measured in the page:
//   clip      an element that clips (overflow hidden/clip) holds more than it shows - a letter's box crosses its
//             side - and neither it nor an element around it carries data-clip-ok (a cut made on purpose)
//   overflow  the page scrolls sideways, or a visible element outside every clipping box sits off the screen
//   panel     a panel a header button opens hangs right under it (its top, and its left or right edge, within TOL),
//             on screen, its first control takes a click, and none of its rows breaks into two lines (data-wrap-ok
//             on a panel that wraps on purpose)
//   text      visible text says [object ...], undefined or NaN
//   size      a button half again taller than the other items of its line, its letters no larger than theirs
//   columns   a table row whose long text cell runs past three lines while a short cell beside it leaves more than
//             half its width empty (owner 10-09: a narrow Source beside a wide Last)
//   words     a word broken between two of its letters (lead 10-09: a rule name in four pieces); data-wrap-ok on text
//             broken on purpose. A break after - or / is the browser's own, and letters outside a-z 0-9 _ are not read
//   answers   a GET the fixtures do not answer, or a screen that could not be driven
//   cells     what one screen asks of itself after one of its states (CELLS): the grid's header message - a press on
//             the button beside it reaches the button, and its title is its whole sentence (lead 10-09)
// One line per finding: entry · size · state · element path · what. Sizes: 1920x950, 1536x864, 1280x720.
// Chrome hands every request here (DevTools Fetch). Files come from dist, GETs from fixtures/screens_answers.json
// (capture_screens.py), the two queues from fixtures/chain_states.json; no request reaches a server of ours. A GET with
// no answer is a red line - an unanswered screen draws empty and measures nothing. Other methods are refused and
// counted; a page that leaves (a link, Log out) is answered 204 and stays. Another origin's file (the fonts, the
// admin's editor) is fetched as the page asks: without the editor the admin page stops booting, without the fonts
// every width is measured in another face.
// --mutate: the five that leaked on 10-08/09, and the ledger table's hand widths (owner 10-09), are built back one at a
// time (vite, a temp folder) and each must be red.
//   node client2/tests/screen_layout_harness.mjs [--mutate] [--only <entry.html>] [--shots <dir>]
import { spawn } from 'node:child_process';
import { readFileSync, existsSync, mkdtempSync, rmSync, readdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const CLIENT = path.resolve(HERE, '..');
const FIX = path.join(HERE, 'fixtures');
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const ORIGIN = 'http://screens.test';
const SIZES = [[1920, 950], [1536, 864], [1280, 720]];
const RULES = ['clip', 'overflow', 'panel', 'text', 'size', 'columns', 'words'];
const TOL = 12;
const argOf = (k) => (process.argv.includes(k) ? process.argv[process.argv.indexOf(k) + 1] : null);
const only = argOf('--only');
const shots = argOf('--shots');
const MUTATE = process.argv.includes('--mutate');
// A made-up admin token so the admin page reads one and asks the answers below; it never leaves this Chrome.
const TOKEN = 'screens-test';

const ANSWERS = JSON.parse(readFileSync(path.join(FIX, 'screens_answers.json'), 'utf8')).answers;
const STATES = JSON.parse(readFileSync(path.join(FIX, 'chain_states.json'), 'utf8')).states;
// The two queues, one row per chain state - the server's shapes (66b330480, the slot's waiting_for_table); the first
// row's table has a long name.
const LONG_TABLE = 'wafer_process_inspection_result_by_lot_and_slot';
const tableOf = (i) => (i === 0 ? LONG_TABLE : 'dt_log');
const QUEUE = {
  '/outbox/queue/rows': {
    generated_at: '2026-10-08 20:00:00', clock: 'server', rules_known: ['dt_log_to_dt_map'],
    listed: { cap: 200, next_cursor: null }, population: 'processed_chain=false',
    rows: STATES.map((s, i) => ({ outbox_id: 300 + i, event_type: 'EDIT', table_name: tableOf(i), created_at: '2026-10-08 19:59:00',
      waiting_seconds: 60, owner: 'chain', chain_state: s.chain_state, broadcast_state: 'pending',
      rules: [{ name: 'dt_log_to_dt_map', will_fire: true }] })),
  },
  '/admin/chain/queue': {
    waiting: STATES.length, oldest_waiting_seconds: 60, waiting_by_owner: [], retried_among_waiting: 0,
    loop_seen_via: 'this_process', generated_at: '2026-10-08T20:00:00+09:00', now_running: [],
    waiting_transactions: STATES.map((s, i) => ({ transaction_id: `tx-${i}-0000-0000`, events: 1, rows: 1, tables: [tableOf(i)],
      waiting_seconds: 60, cancel: { key: `tx:${i}` }, chain_state: s.chain_state, slot_pid: 4242 })),
  },
};
const answerOf = (u) => {
  for (const [p, body] of Object.entries(QUEUE)) if (u.pathname === p) return { status: 200, type: 'application/json', body };
  const a = ANSWERS[u.pathname + u.search];
  return a && a.same_as ? ANSWERS[a.same_as] : a || null;
};
// Cells one screen asks of itself after one of its states, at every size; each answers null or why it is red.
const CELLS = [
  { entry: 'index.html', after: 'loaded', rule: 'beside the message', expr: `(() => {
  const log = document.getElementById('performance-log');
  if (!log || !log.getClientRects().length) return 'no header message on the page';
  const r = log.getBoundingClientRect();
  const mid = (r.top + r.bottom) / 2, centre = (r.left + r.right) / 2;
  const near = [...document.querySelectorAll('header button, header select, header input, header a[href]')]
    .filter((b) => b.getClientRects().length && getComputedStyle(b).visibility === 'visible')
    .map((b) => ({ b, box: b.getBoundingClientRect() })).filter((x) => x.box.width && x.box.top <= mid && x.box.bottom >= mid);
  const at = (x) => (x.box.left + x.box.right) / 2;
  const left = near.filter((x) => at(x) < centre).sort((p, q) => at(q) - at(p))[0];
  const right = near.filter((x) => at(x) > centre).sort((p, q) => at(p) - at(q))[0];
  if (!left && !right) return 'no control beside the header message';
  for (const x of [left, right].filter(Boolean)) {
    for (const px of [x.box.left + 2, at(x), x.box.right - 2]) {
      const hit = document.elementFromPoint(px, (x.box.top + x.box.bottom) / 2);
      if (!hit || !(hit === x.b || x.b.contains(hit))) {
        return \`a press on «\${(x.b.textContent || x.b.title || '').trim().slice(0, 24)}» at x \${Math.round(px)} reaches \${hit ? hit.tagName.toLowerCase() + (hit.id ? '#' + hit.id : '') : 'nothing'}\`;
      }
    }
  }
  return null;
})()` },
  { entry: 'index.html', after: 'loaded', rule: 'message title', expr: `(() => {
  const log = document.getElementById('performance-log');
  if (!log) return 'no header message on the page';
  const t = log.textContent;
  if (!t.trim()) return 'the header message is empty';
  if (getComputedStyle(log).pointerEvents === 'none') return 'the header message takes no pointer, so its title never shows';
  return log.title === t ? null : \`its title «\${log.title.slice(0, 30)}» is not its sentence «\${t.slice(0, 30)}»\`;
})()` },
];
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.json': 'application/json',
  '.png': 'image/png', '.woff2': 'font/woff2', '.woff': 'font/woff', '.ttf': 'font/ttf', '.txt': 'text/plain', '.ico': 'image/x-icon' };
const sleep = (ms) => new Promise((ok) => setTimeout(ok, ms));

async function openChrome() {
  if (!existsSync(CHROME)) throw new Error(`no Chrome at ${CHROME} - the screens cannot be opened`);
  const port = 9300 + Math.floor(Math.random() * 500);
  const profile = mkdtempSync(path.join(tmpdir(), 'screens-'));
  const proc = spawn(CHROME, ['--headless=new', '--hide-scrollbars', `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`,
    '--window-size=1920,950', 'about:blank'], { stdio: 'ignore' });
  let target;
  for (let i = 0; i < 75 && !target; i += 1) {
    await sleep(200);
    try { target = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((t) => t.type === 'page'); } catch { /* not up yet */ }
  }
  if (!target) { proc.kill(); throw new Error('Chrome did not answer on its DevTools port'); }
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((ok) => ws.addEventListener('open', ok));
  let id = 0;
  const waiting = new Map();
  const handlers = [];
  ws.addEventListener('message', (e) => {
    const m = JSON.parse(e.data);
    if (m.id && waiting.has(m.id)) { waiting.get(m.id)(m); waiting.delete(m.id); return; }
    for (const h of handlers) h(m);
  });
  const send = (method, params = {}) => new Promise((ok) => { id += 1; waiting.set(id, ok); ws.send(JSON.stringify({ id, method, params })); })
    .then((m) => { if (m.error) throw new Error(`${method}: ${m.error.message}`); return m.result; });
  const close = () => { try { ws.close(); } catch { /* gone */ } proc.kill(); setTimeout(() => rmSync(profile, { recursive: true, force: true }), 1500); };
  return { send, on: (h) => handlers.push(h), close };
}

// One Chrome page that serves `dist` and the answers; `log` collects what was refused or unanswered.
async function servePage(chrome, dist) {
  const log = { missing: new Set(), refused: [], left: [], thrown: [], outside: new Set(), last: Date.now(), opening: false };
  chrome.on(async (m) => {
    if (m.method === 'Page.javascriptDialogOpening') { chrome.send('Page.handleJavaScriptDialog', { accept: false }).catch(() => {}); return; }
    if (m.method === 'Runtime.exceptionThrown') { log.thrown.push((m.params.exceptionDetails.exception || {}).description || m.params.exceptionDetails.text); return; }
    if (m.method !== 'Fetch.requestPaused') return;
    const { requestId, request, resourceType } = m.params;
    const u = new URL(request.url);
    log.last = Date.now();
    const reply = (status, type, body) => chrome.send('Fetch.fulfillRequest', { requestId, responseCode: status,
      responseHeaders: [{ name: 'Content-Type', value: type }], body: Buffer.from(body).toString('base64') }).catch(() => {});
    if (u.origin !== ORIGIN) {
      log.outside.add(u.origin);
      if (request.method === 'GET') chrome.send('Fetch.continueRequest', { requestId }).catch(() => {});
      else chrome.send('Fetch.failRequest', { requestId, errorReason: 'BlockedByClient' }).catch(() => {});
      return;
    }
    if (request.method !== 'GET' && request.method !== 'HEAD') { log.refused.push(`${request.method} ${u.pathname}`); chrome.send('Fetch.failRequest', { requestId, errorReason: 'BlockedByClient' }).catch(() => {}); return; }
    if (resourceType === 'Document') {
      if (!log.opening) { log.left.push(u.pathname + u.search); reply(204, 'text/plain', ''); return; }
      log.opening = false;
    }
    const file = path.join(dist, decodeURIComponent(u.pathname));
    if (path.extname(u.pathname) && existsSync(file)) { reply(200, MIME[path.extname(file)] || 'application/octet-stream', readFileSync(file)); return; }
    if (resourceType === 'Other' && u.pathname === '/favicon.ico') { reply(404, 'text/plain', ''); return; }
    const a = answerOf(u);
    if (!a) { log.missing.add(u.pathname + u.search); reply(404, 'application/json', JSON.stringify({ detail: 'no answer in screens_answers.json' })); return; }
    reply(a.status, a.type || 'application/json', typeof a.body === 'string' ? a.body : JSON.stringify(a.body));
  });
  await chrome.send('Page.enable');
  await chrome.send('Runtime.enable');
  await chrome.send('Fetch.enable', { patterns: [{ urlPattern: '*', requestStage: 'Request' }] });
  await chrome.send('Page.addScriptToEvaluateOnNewDocument', { source: `try { localStorage.setItem('assy.adminToken', '${TOKEN}'); } catch (e) {}` });
  return log;
}

const evaluate = async (chrome, expression) => {
  const r = await chrome.send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(`in page: ${(r.exceptionDetails.exception || {}).description || r.exceptionDetails.text}`);
  return r.result.value;
};
// Quiet: no request for `quiet` ms (a poll may keep coming; `most` caps the wait), then the fonts.
async function settle(chrome, log, quiet = 700, most = 8000) {
  const t0 = Date.now();
  while (Date.now() - t0 < most && Date.now() - log.last < quiet) await sleep(100);
  await evaluate(chrome, 'document.fonts.ready.then(() => true)');
}

// ---- in the page: window.__screens = { measure, openNext, close }. Lines are {rule, path, what}.
function screensLib(TOL) {
  const css = (el) => getComputedStyle(el);
  const shown = (el) => {
    if (!el || !el.isConnected) return false;
    const s = css(el);
    if (s.display === 'none' || s.visibility !== 'visible' || Number(s.opacity) === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const pathOf = (el) => {
    const parts = [];
    for (let e = el; e && e !== document.body && parts.length < 4; e = e.parentElement) {
      let p = e.tagName.toLowerCase();
      if (e.id) { parts.unshift(`${p}#${e.id}`); break; }
      const cls = [...e.classList].slice(0, 2).join('.');
      if (cls) p += `.${cls}`;
      parts.unshift(p);
    }
    return parts.join(' > ');
  };
  const clips = (s) => /hidden|clip/.test(s.overflowX) || /hidden|clip/.test(s.overflowY);
  const scrolls = (s) => /auto|scroll/.test(s.overflowX) || /auto|scroll/.test(s.overflowY);
  const ownText = (el) => [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
  const hasText = (el) => ownText(el) || [...el.querySelectorAll('*')].some(ownText);
  const label = (el) => (el.textContent || el.getAttribute('aria-label') || el.title || '').trim().replace(/\s+/g, ' ').slice(0, 30);
  const wait = (ms) => new Promise((ok) => setTimeout(ok, ms));
  const textBeyond = (el) => {
    const b = el.getBoundingClientRect();
    const k = el.offsetWidth ? b.width / el.offsetWidth : 1;
    const left = b.left + el.clientLeft * k, top = b.top + el.clientTop * k;
    const right = left + el.clientWidth * k, bottom = top + el.clientHeight * k;
    let dx = 0, dy = 0;
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      if (!n.textContent.trim()) continue;
      const range = document.createRange();
      range.selectNodeContents(n);
      for (const r of range.getClientRects()) {
        if (!r.width) continue;
        dx = Math.max(dx, r.right - right, left - r.left);
        dy = Math.max(dy, r.bottom - bottom, top - r.top);
      }
    }
    return [dx, dy];
  };
  const readerOnly = (el, s) => el.clientWidth <= 1 || el.clientHeight <= 1 || (s.clip && s.clip !== 'auto');

  function measure(scopeSel) {
    const lines = [];
    const W = innerWidth, H = innerHeight;
    const scope = scopeSel ? document.querySelector(scopeSel) : document.body;
    if (!scope) return lines;
    const all = [scope, ...scope.querySelectorAll('*')].filter(shown);
    for (const el of all) {
      const s = css(el);
      if (s.display === 'inline' || s.display === 'contents' || !clips(s) || scrolls(s) || el.closest('[data-clip-ok]') || !hasText(el)) continue;
      if (readerOnly(el, s)) continue;
      if (el.scrollWidth - el.clientWidth <= 1 && el.scrollHeight - el.clientHeight <= 1) continue;
      // Held more than it shows; cut is where a glyph's box crosses the box it is drawn in (screen px, any zoom).
      const [dx, dy] = textBeyond(el);
      if (dx > 1 || dy > 1) {
        lines.push({ rule: 'clip', path: pathOf(el), what: [dx > 1 && `${Math.round(dx)} px of text past its side`, dy > 1 && `${Math.round(dy)} px past its top or bottom`]
          .filter(Boolean).join(', ') + `: «${el.textContent.trim().replace(/\s+/g, ' ').slice(0, 40)}»` });
      }
    }
    if (!scopeSel) {
      const sw = document.scrollingElement.scrollWidth - W;
      if (sw > 1) lines.push({ rule: 'overflow', path: 'page', what: `scrolls sideways by ${sw} px` });
    }
    const inBox = (el) => {
      for (let e = el.parentElement; e && e !== document.body && e !== document.documentElement; e = e.parentElement) {
        const s = css(e);
        if (clips(s) || scrolls(s)) return true;
      }
      return false;
    };
    const off = [];
    for (const el of all) {
      if (off.some((o) => o.contains(el)) || inBox(el) || readerOnly(el, css(el))) continue;
      const r = el.getBoundingClientRect();
      const placed = /fixed|absolute/.test(css(el).position);
      const by = Math.max(-r.left, r.right - W, placed ? r.bottom - H : 0, placed ? -r.top : 0);
      if (by > 1) { off.push(el); lines.push({ rule: 'overflow', path: pathOf(el), what: `${Math.round(by)} px off the screen` }); }
    }
    const bad = /\[object [A-Za-z]+\]|\bundefined\b|\bNaN\b/;
    const walker = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      const m = n.textContent.match(bad);
      if (m && shown(n.parentElement)) lines.push({ rule: 'text', path: pathOf(n.parentElement), what: `says «${m[0]}»` });
    }
    for (const el of scope.querySelectorAll('input, textarea')) {
      const m = String(el.value || '').match(bad);
      if (m && shown(el)) lines.push({ rule: 'text', path: pathOf(el), what: `holds «${m[0]}»` });
    }
    // size: a button against the other items of its line - the line is the button's bar (its widest ancestor still
    // one line high): its other controls by their box, or, when it stands alone among words, the words by their letters
    // (a flex row stretches a text box to the button beside it). Odd: half again taller, its letters no larger.
    // A button with no words is an icon, the size of its icon.
    const isButton = (e) => e.matches('button, [role="button"]');
    const isControl = (e) => e.matches('button, [role="button"], input, select, textarea') || (e.matches('a[href]') && css(e).display !== 'inline');
    const median = (xs) => xs.sort((x, y) => x - y)[Math.floor(xs.length / 2)];
    const textBox = (el) => {
      let top = Infinity, bottom = -Infinity;
      for (const n of el.childNodes) {
        if (n.nodeType !== 3 || !n.textContent.trim()) continue;
        const range = document.createRange();
        range.selectNodeContents(n);
        const r = range.getBoundingClientRect();
        if (r.height) { top = Math.min(top, r.top); bottom = Math.max(bottom, r.bottom); }
      }
      return bottom > top ? { top, bottom, height: bottom - top } : null;
    };
    for (const b of all.filter((e) => isButton(e) && e.textContent.trim())) {
      const r = b.getBoundingClientRect();
      let bar = b.parentElement;
      while (bar && bar.parentElement && bar.parentElement !== document.body && bar.parentElement.getBoundingClientRect().height < r.height * 3) bar = bar.parentElement;
      if (!bar) continue;
      const mid = (x) => (x.top + x.bottom) / 2;
      const items = [];
      for (const e of bar.querySelectorAll('*')) {
        if (e === b || b.contains(e) || e.contains(b) || !shown(e)) continue;
        if (isControl(e)) {
          if (!e.parentElement.closest('button, [role="button"]')) items.push({ box: e.getBoundingClientRect(), font: parseFloat(css(e).fontSize), control: true });
          continue;
        }
        if (e.closest('button, [role="button"]')) continue;
        const t = textBox(e);
        if (t) items.push({ box: t, font: parseFloat(css(e).fontSize) });
      }
      const near = items.filter((x) => mid(x.box) >= r.top && mid(x.box) <= r.bottom);
      // The other controls of the line when it has any; its text when the button stands alone among words.
      const line = near.some((x) => x.control) ? near.filter((x) => x.control) : near;
      if (!line.length) continue;
      const h = median(line.map((x) => x.box.height));
      const f = median(line.map((x) => x.font));
      const font = parseFloat(css(b).fontSize);
      if (r.height > h * 1.5 && font <= f) {
        lines.push({ rule: 'size', path: pathOf(b), what: `«${label(b)}» ${Math.round(r.height)} px high at ${font} px letters, its line ${Math.round(h)} px at ${f} px` });
      }
    }
    // columns: one line per table - a row where a cell runs past three lines while a neighbouring column is more than
    // half empty all the way down (its widest cell decides; a column as wide as its longest word is not slack)
    const tables = new Map();
    for (const tr of scope.querySelectorAll('tr, [role="row"]')) {
      if (!shown(tr)) continue;
      const table = tr.closest('table, [role="table"], [role="grid"], [role="treegrid"]') || tr.parentElement;
      const cells = [...tr.children].filter(shown).map((c) => {
        const b = c.getBoundingClientRect();
        const s = css(c);
        const left = b.left + parseFloat(s.paddingLeft);
        const width = b.width - parseFloat(s.paddingLeft) - parseFloat(s.paddingRight);
        const tops = new Set();
        let right = left;
        const walker = document.createTreeWalker(c, NodeFilter.SHOW_TEXT);
        for (let n = walker.nextNode(); n; n = walker.nextNode()) {
          if (!n.textContent.trim()) continue;
          const range = document.createRange();
          range.selectNodeContents(n);
          for (const r of range.getClientRects()) if (r.width) { tops.add(Math.round(r.top)); right = Math.max(right, r.right); }
        }
        return { c, lines: tops.size, width, empty: width - (right - left) };
      });
      if (!tables.has(table)) tables.set(table, []);
      tables.get(table).push(cells);
    }
    for (const [table, rows] of tables) {
      const empty = (i) => Math.min(...rows.filter((r) => r[i] && r[i].lines > 0).map((r) => r[i].empty));
      for (const cells of rows) {
        const t = cells.findIndex((x) => x.lines > 3);
        if (t < 0) continue;
        const l = cells.findIndex((x, i) => i !== t && x.lines > 0 && empty(i) > x.width / 2);
        if (l < 0) continue;
        lines.push({ rule: 'columns', path: pathOf(table), what: `«${label(cells[t].c)}» runs to ${cells[t].lines} lines while the column of «${label(cells[l].c)}» leaves ${Math.round(empty(l))} of ${Math.round(cells[l].width)} px empty` });
        break;
      }
    }
    // words: in a text that runs over lines, two letters of one word on two lines
    const letter = /\w/;
    const texts = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT);
    for (let n = texts.nextNode(); n; n = texts.nextNode()) {
      const t = n.textContent;
      if (t.trim().length < 2 || !shown(n.parentElement) || n.parentElement.closest('[data-wrap-ok]')) continue;
      const whole = document.createRange();
      whole.selectNodeContents(n);
      if (new Set([...whole.getClientRects()].filter((r) => r.width).map((r) => Math.round(r.top))).size < 2) continue;
      let prev = null;
      for (let i = 0; i < t.length; i += 1) {
        const one = document.createRange();
        one.setStart(n, i);
        one.setEnd(n, i + 1);
        const box = [...one.getClientRects()].find((r) => r.width);
        if (!box) continue;
        if (prev && prev.i === i - 1 && box.top > prev.box.top + prev.box.height / 2 && letter.test(t[i - 1]) && letter.test(t[i])) {
          const from = t.lastIndexOf(' ', i) + 1;
          const to = t.indexOf(' ', i) < 0 ? t.length : t.indexOf(' ', i);
          lines.push({ rule: 'words', path: pathOf(n.parentElement), what: `«${t.slice(from, to).slice(0, 40)}» breaks between «${t[i - 1]}» and «${t[i]}»` });
          break;
        }
        prev = { box, i };
      }
    }
    return lines;
  }

  // Every button in a <header>, and every [aria-haspopup], pressed in turn: what appears positioned is its panel.
  const keyOf = (b) => `${pathOf(b)}|${label(b)}`;
  const openers = () => [...document.querySelectorAll('header button, header [role="button"], [aria-haspopup]')].filter((b) => shown(b) && !b.disabled);
  const floating = () => [...document.querySelectorAll('body *')].filter((e) => /absolute|fixed/.test(css(e).position) && shown(e));
  const pressed = new Set();
  let open = null;
  async function openNext() {
    const b = openers().find((x) => !pressed.has(keyOf(x)));
    if (!b) return null;
    const key = keyOf(b);
    pressed.add(key);
    const before = new Set(floating());
    b.click();
    await wait(450);
    const now = openers().find((x) => keyOf(x) === key) || b;
    const boxed = (el) => { for (let e = el.parentElement; e && e !== document.body; e = e.parentElement) { if (scrolls(css(e))) return true; } return false; };
    const fresh = floating().filter((e) => !before.has(e) && !boxed(e) && !e.closest('[aria-live]'));
    const panel = fresh.find((e) => !fresh.some((o) => o !== e && o.contains(e))
      && e.getBoundingClientRect().width > 40 && e.getBoundingClientRect().height > 20);
    if (!panel) return { opener: key, panel: null, lines: [] };
    const a = now.getBoundingClientRect(), p = panel.getBoundingClientRect();
    const lines = [];
    const below = p.top - a.bottom;
    const edge = Math.min(Math.abs(p.left - a.left), Math.abs(p.right - a.right));
    const atMargin = p.left <= TOL || p.right >= innerWidth - TOL;
    if (below < -1 || below > TOL) lines.push({ rule: 'panel', path: pathOf(panel), what: `top ${Math.round(below)} px under «${label(now)}»` });
    if (edge > TOL && !atMargin) lines.push({ rule: 'panel', path: pathOf(panel), what: `no edge meets «${label(now)}» (nearest ${Math.round(edge)} px)` });
    if (p.left < 0 || p.right > innerWidth || p.bottom > innerHeight) lines.push({ rule: 'panel', path: pathOf(panel), what: `off the screen, opened by «${label(now)}»` });
    const first = panel.querySelector('button:not([disabled]), a[href], input, select, label, [role="menuitem"]');
    if (first && shown(first)) {
      const f = first.getBoundingClientRect();
      const hit = document.elementFromPoint(f.left + f.width / 2, f.top + f.height / 2);
      if (!(hit === first || first.contains(hit))) lines.push({ rule: 'panel', path: pathOf(first), what: `first control covered by ${hit ? pathOf(hit) : 'nothing'}` });
    }
    // A row of the panel is one line (owner 10-09: the header's panels came out narrower and their rows broke in two);
    // a panel that wraps on purpose says so with data-wrap-ok.
    if (!panel.closest('[data-wrap-ok]')) {
      for (const el of panel.querySelectorAll('*')) {
        if (!shown(el)) continue;
        const tops = new Set();
        for (const n of el.childNodes) {
          if (n.nodeType !== 3 || !n.textContent.trim()) continue;
          const range = document.createRange();
          range.selectNodeContents(n);
          for (const r of range.getClientRects()) if (r.width) tops.add(Math.round(r.top));
        }
        if (tops.size > 1) lines.push({ rule: 'panel', path: pathOf(el), what: `«${label(el)}» breaks into ${tops.size} lines in the panel «${label(now)}» opened` });
      }
    }
    panel.setAttribute('data-screens-open', '');
    open = { key, panel };
    return { opener: key, panel: pathOf(panel), lines };
  }
  async function close() {
    if (!open) return true;
    const { key, panel } = open;
    open = null;
    panel.removeAttribute('data-screens-open');
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await wait(150);
    if (shown(panel)) { document.body.click(); await wait(150); }
    const again = openers().find((x) => keyOf(x) === key);
    if (shown(panel) && again) { again.click(); await wait(200); }
    return !shown(panel);
  }
  window.__screens = { measure, openNext, close };
  return true;
}

// ---- the states each entry is driven through, in order; every entry ends with its header's panels opened.
// A wait that runs out leaves its state unreached: the drive loop says it under «answers», with the step, so a green
// line is never a state the gate did not get to (lead 10-10 - the walk page passed once with every wait run out).
const waitsRunOut = [];
const until = async (chrome, test, most = 10000) => {
  const held = await evaluate(chrome, `new Promise((ok) => { const t0 = Date.now();
  const tick = () => { let v = false; try { v = (${test}); } catch (e) {} if (v || Date.now() - t0 > ${most}) ok(Boolean(v)); else setTimeout(tick, 150); }; tick(); })`);
  if (!held) waitsRunOut.push(`waited ${most} ms and it never held: ${test}`);
  return held;
};
const GRID_LOADED = `/^Loaded/.test((document.querySelector('#performance-log') || {}).textContent || '')`;
const press = (c, words) => evaluate(c, `(() => { const b = [...document.querySelectorAll('button')].find((x) => x.textContent.trim() === ${JSON.stringify(words)} && !x.disabled);
  if (b) b.click(); return Boolean(b); })()`);
const choose = (c, sel, pick) => evaluate(c, `(() => { const s = document.querySelectorAll(${JSON.stringify(sel)})[${pick[0]}]; if (!s) return false;
  const o = [...s.options].find((x, i) => ${pick[1]}); if (!o) return false; s.value = o.value; s.dispatchEvent(new Event('change', { bubbles: true })); return true; })()`);
// PICK A NODE's box (lead bccbdd601): focused, it lists the first nodes; a press on row i picks it.
const pickRow = async (c, i) => {
  // The box shows once the type's first answer names its key (hidden while it loads, and a hidden box takes no focus).
  await until(c, "document.querySelector('.wk-search .wk-cell') && !document.querySelector('.wk-search .wk-cell').hidden");
  await evaluate(c, `(() => { const b = document.querySelector('.wk-search input'); if (b) { b.focus(); b.click(); } return Boolean(b); })()`);
  await until(c, `document.querySelectorAll('.wk-searchitem').length > ${i}`);
  return evaluate(c, `(() => { const r = document.querySelectorAll('.wk-searchitem')[${i}]; if (!r) return false;
    r.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window })); return true; })()`);
};
// A basket's +: the picked node into Positive (+) or Negative (−) (lead bc63378e5).
const basket = (c, sign) => evaluate(c, `(() => { const b = document.querySelector('.wk-basket[data-sign="${sign}"] .wk-basketadd');
  if (b && !b.disabled) b.click(); return Boolean(b); })()`);
const DRIVE = {
  'walk.html': [
    ['a wafer walked, Table', async (c) => {
      await choose(c, '.wk-select', [0, "x.textContent.trim() === 'wafer'"]);
      await pickRow(c, 0);
      await sleep(300);
      await basket(c, '+');
      await press(c, 'Walk');
      await until(c, "document.querySelector('.wk-main table, .wk-main svg, .wk-main canvas')");
    }],
    ['Graph', (c) => press(c, 'Graph').then(() => sleep(1500))],
    // Compare (lead 10-09, demo ③): picked from the declaration, then a second subject in the Negative basket and Walk -
    // a + column and a - column, its whose labels whole.
    ['Compare, a + and a - start', async (c) => {
      await press(c, 'Compare');
      await until(c, "document.querySelector('.cmp-select')");
      await choose(c, '.cmp-select', [0, "x.value === 'recipe'"]);
      await choose(c, '.cmp-select', [1, "x.value === 'processed_with'"]);
      await choose(c, '.cmp-select', [2, "x.value === 'step'"]);
      await pickRow(c, 1);
      await sleep(300);
      await basket(c, '−');
      await press(c, 'Walk');
      await until(c, "document.querySelector('.cmp-table')");
    }],
    // The table walked from a + and a - start (lead 55f854fc5 ②): a zone per sign.
    ['Table, a zone per sign', async (c) => {
      await press(c, 'Table');
      await press(c, 'Walk');
      await until(c, "document.querySelectorAll('.wk-zone').length > 1");
    }],
  ],
  'index.html': [
    ['loaded', (c) => until(c, GRID_LOADED, 15000)],
    // One filter at a time, each one's load waited out: typed together, which half-set the grid's debounce sent
    // depended on the clock and the answers held only some (application QA 4bd46df68: red in one run of four).
    ['three filters', async (c, log) => {
      for (const [col, v] of [['subject_type', 'die'], ['predicate', 'in_container'], ['object_kind', 'entity_ref']]) {
        await evaluate(c, `(() => {
          const input = [...document.querySelectorAll('.ag-floating-filter input')].find((i) => i.closest('[col-id]') && i.closest('[col-id]').getAttribute('col-id') === ${JSON.stringify(col)});
          if (!input) return false;
          Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, ${JSON.stringify(v)});
          input.dispatchEvent(new Event('input', { bubbles: true }));
          return true; })()`);
        await sleep(900);
        await settle(c, log);
        await until(c, GRID_LOADED);
      }
    }],
    ['row picked, Queue tab', (c) => evaluate(c, `(() => {
      const cell = document.querySelector('.ag-center-cols-container .ag-row[row-index="0"] .ag-cell');
      if (cell) for (const t of ['mousedown', 'mouseup', 'click']) cell.dispatchEvent(new MouseEvent(t, { bubbles: true, cancelable: true, view: window }));
      const tab = document.getElementById('tab-queue'); if (tab) tab.click();
      return true; })()`)],
    // Dragged to 500 px: wider than the six columns' least widths or not, every cell whole (the box rolls).
    ['side panel dragged to 500 px', (c) => evaluate(c, `(() => {
      const bar = document.getElementById('main-split-resizer'); const box = document.querySelector('.main-layout'); if (!bar || !box) return false;
      const x = box.getBoundingClientRect().right - 500;
      const at = (t) => (t === 'mousedown' ? bar : document).dispatchEvent(new MouseEvent(t, { bubbles: true, clientX: x, clientY: 300 }));
      at('mousedown'); at('mousemove'); at('mouseup');
      return true; })()`).then(() => sleep(600))],
    // At the panel's floor the queue rolls sideways inside its own box, its columns whole (lead 10-09).
    ['side panel at its narrowest', (c) => evaluate(c, `(() => {
      const bar = document.getElementById('main-split-resizer'); if (!bar) return false;
      const at = (t) => (t === 'mousedown' ? bar : document).dispatchEvent(new MouseEvent(t, { bubbles: true, clientX: innerWidth, clientY: 300 }));
      at('mousedown'); at('mousemove'); at('mouseup');
      return true; })()`).then(() => sleep(600))],
  ],
  'admin.html': [
    ['Overview', async () => true],
    ['Overview, every row unfolded', (c) => evaluate(c, `(() => {
      for (const row of document.querySelectorAll('.ov-row[aria-expanded="false"]')) row.click();
      return true; })()`).then(() => sleep(800))],
    // The Retry row with «Include files that went in» turned on (lead a4d135a06).
    ['File Ingestion, files that went in included', (c) => evaluate(c, `(() => {
      location.hash = '#file';
      return true; })()`).then(() => sleep(1500)).then(() => evaluate(c, `(() => {
      const box = document.querySelector('.folder-retry-include-box'); if (!box) return false;
      box.checked = true; box.dispatchEvent(new Event('change', { bubbles: true }));
      return true; })()`))],
    // The other tabs, each by its address (lead 10-09: the File tab showed two defects the first time it was opened).
    ...[['Tables', 'tables'], ['Chain', 'chain'], ['Auto Update', 'autoupdate'], ['Retroactive', 'retroactive']]
      .map(([name, hash]) => [name, (c) => evaluate(c, `location.hash = '#${hash}'; true`).then(() => sleep(1500))]),
    ['Ontology Explorer', (c) => evaluate(c, "location.hash = '#ontology'; true").then(() => sleep(1500))],
  ],
};

async function runScreens(dist, label, one = only) {
  const entries = readdirSync(dist).filter((n) => n.endsWith('.html')).sort().filter((n) => !one || n === one);
  const found = [];
  const chrome = await openChrome();
  try {
    const log = await servePage(chrome, dist);
    for (const [w, h] of SIZES) {
      await chrome.send('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: 1, mobile: false });
      for (const entry of entries) {
        const size = `${w}x${h}`;
        log.missing.clear(); log.refused.length = 0; log.left.length = 0; log.thrown.length = 0; log.outside.clear();
        log.opening = true;
        await chrome.send('Page.navigate', { url: `${ORIGIN}/${entry}` });
        await sleep(300);
        await settle(chrome, log);
        await evaluate(chrome, `(${screensLib})(${TOL})`);
        const add = (state, lines) => { for (const l of lines) found.push({ entry, size, state, ...l }); };
        const panels = [];
        try {
        const states = DRIVE[entry] || [['loaded', async () => true]];
        let state = 'loaded';
        waitsRunOut.length = 0;
        for (const [name, step] of states) {
          state = name;
          await step(chrome, log);
          add(state, waitsRunOut.splice(0).map((what) => ({ rule: 'answers', path: entry, what })));
          await settle(chrome, log);
          add(state, await evaluate(chrome, 'window.__screens.measure()'));
          for (const cell of CELLS.filter((c) => c.entry === entry && c.after === state)) {
            const why = await evaluate(chrome, cell.expr);
            if (why) add(state, [{ rule: cell.rule, path: '#performance-log', what: why }]);
          }
          if (shots) writeFileSync(path.join(shots, `${entry}_${size}_${state.replace(/[^a-z0-9]+/gi, '-')}.png`),
            Buffer.from((await chrome.send('Page.captureScreenshot', { format: 'png' })).data, 'base64'));
        }
        for (let i = 0; i < 60; i += 1) {
          const opened = await evaluate(chrome, 'window.__screens.openNext()');
          if (!opened) break;
          if (!opened.panel) continue;
          panels.push(opened.opener.split('|')[1]);
          await settle(chrome, log, 400, 3000);
          add(`${state}, «${opened.opener.split('|')[1]}» open`, [...opened.lines, ...await evaluate(chrome, "window.__screens.measure('[data-screens-open]')")]);
          if (shots) writeFileSync(path.join(shots, `${entry}_${size}_panel-${opened.opener.split('|')[1].replace(/[^a-z0-9]+/gi, '-')}.png`),
            Buffer.from((await chrome.send('Page.captureScreenshot', { format: 'png' })).data, 'base64'));
          await evaluate(chrome, 'window.__screens.close()');
        }
        } catch (err) {
          found.push({ entry, size, state: 'driving', rule: 'answers', path: entry, what: `could not be driven: ${err.message}` });
        }
        console.log(`  ${label} ${entry} ${size}: ${panels.length} panels opened${panels.length ? ` - ${panels.map((p) => `«${p}»`).join(' ')}` : ''}`);
        for (const u of log.missing) found.push({ entry, size, state: 'answers', rule: 'answers', path: u, what: 'no answer in screens_answers.json' });
        if (log.refused.length) console.log(`  ${label} ${entry} ${size}: ${log.refused.length} non-GET refused (${[...new Set(log.refused)].join(', ')})`);
        for (const t of new Set(log.thrown)) console.log(`  ${label} ${entry} ${size}: threw ${String(t).split('\n').slice(0, 2).join(' | ')}`);
        if (log.outside.size) console.log(`  ${label} ${entry} ${size}: fetched from ${[...log.outside].join(', ')}`);
        if (log.left.length) console.log(`  ${label} ${entry} ${size}: stayed on the page when it asked to leave for ${[...new Set(log.left)].join(', ')}`);
      }
    }
  } finally {
    chrome.close();
  }
  return { entries, found };
}

let ran = 0;
let failed = 0;
const t0 = Date.now();
const { entries, found } = await runScreens(path.join(CLIENT, 'dist'), 'dist');
for (const entry of entries) {
  for (const [w, h] of SIZES) {
    for (const rule of [...RULES, 'answers', ...CELLS.filter((c) => c.entry === entry).map((c) => c.rule)]) {
      ran += 1;
      const mine = found.filter((f) => f.entry === entry && f.size === `${w}x${h}` && f.rule === rule);
      if (mine.length) failed += 1;
      console.log(`${mine.length ? '✗' : '✓'} ${entry} ${w}x${h} ${rule}${mine.length ? ` - ${mine.length}` : ''}`);
      const times = new Map();
      for (const f of mine) { const k = `${f.entry} · ${f.size} · ${f.state} · ${f.path} · ${f.what}`; times.set(k, (times.get(k) || 0) + 1); }
      for (const [k, n] of times) console.log(`    ${k}${n > 1 ? ` (x${n})` : ''}`);
    }
  }
}
console.log(`screens: ${entries.length} entries x ${SIZES.length} sizes in ${Math.round((Date.now() - t0) / 1000)} s`);

// The five that leaked on 10-08/09, each built back into a temp folder (the source is not touched) and opened on its
// screen: its line must turn red. A find that is no longer in the file is an error, not an escape.
const MUTANTS = [
  // A panel left inside the header is placed in the header's zoomed px (10-08).
  { name: 'Replay chain panel placed inside the zoomed header', entry: 'index.html', rule: 'panel', at: 'redo-panel', says: /under/,
    file: 'src/dropdown.js', edits: [['    doc.body.appendChild(panel);\n', '']] },
  // Options and Menu hung from their buttons by CSS inside the header: narrowed by its zoom, their rows in two (10-09).
  { name: 'Options and Menu drawn inside the zoomed header, their rows in two', entry: 'index.html', rule: 'panel', at: '',
    says: /breaks into/, file: 'src/main.js', edits: [
      ['      if (!isVisible) placeUnder(elements.settingsDropdown, elements.settingsMenuBtn);\n', ''],
      ['      if (!isVisible) placeUnder(elements.navDropdown, elements.navMenuBtn);\n', '']] },
  // A rule name in a 48px column, broken letter by letter (lead 10-09; owner 09-23 「접지말고」).
  { name: 'the Rules column back at 48px, its names broken anywhere', entry: 'index.html', rule: 'words', at: 'queue-rule-name',
    file: 'src/style.css', edits: [
      ['minmax(var(--queue-rules-w, 48px), 1fr)', 'minmax(48px, 1fr)'],
      ['                   flex: none; white-space: nowrap; }', '                   flex: 0 1 auto; min-width: 0; overflow-wrap: anywhere; }']] },
  // The header message laid over the button beside it, and its title no longer following its text (lead 10-09).
  { name: 'the header message laid over the button beside it', entry: 'index.html', rule: 'beside the message', at: 'performance-log',
    file: 'src/style.css', edits: [['.app-header #performance-log { flex: 0 1 auto; min-width: 0; pointer-events: auto; }',
      '.app-header #performance-log { flex: 0 1 auto; min-width: 0; pointer-events: auto; position: absolute; inset: 0 0 auto 0; z-index: 5; }']] },
  { name: 'the header message title not following its text', entry: 'index.html', rule: 'message title', at: 'performance-log',
    file: 'src/main.js', edits: [['      followTitle(elements.performanceLog);\n', '']] },
  { name: 'State column back at a fixed 96px', entry: 'index.html', rule: 'clip', at: 'queue-cell',
    file: 'src/style.css', edits: [['max(96px, var(--queue-state-w, 96px))', '96px']] },
  { name: 'the why beside its tag, cut at the cell', entry: 'index.html', rule: 'clip', at: 'queue-line-state-why',
    file: 'src/base.css', edits: [
      [':where(.queue-line-state) { display: flex; flex-direction: column; align-items: flex-start;', ':where(.queue-line-state) { display: flex; align-items: center;'],
      [':where(.queue-line-state-why) { white-space: normal; overflow-wrap: anywhere; min-width: 0; }',
        ':where(.queue-line-state-why) { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }']] },
  { name: 'the chain state object drawn as text', entry: 'index.html', rule: 'text', at: 'queue',
    file: 'src/chain_queue_panel.js', edits: [["const token = chainState && chainState.state ? String(chainState.state) : '';", "const token = chainState ? String(chainState) : '';"]] },
  { name: 'the Overview queue Refresh boxed at the base button height', entry: 'admin.html', rule: 'size', at: 'chain-queue-refresh',
    file: 'admin.html', edits: [['    .ov-show-all,\n    .chain-queue-panel .chain-queue-refresh,\n    #file-list-body .admin-btn,\n',
      '    .ov-show-all,\n    #file-list-body .admin-btn,\n']] },
  // A file row's Retry boxed at the base button height again, 36 px in its 14 px line (lead a4d135a06's round).
  { name: 'a file row Retry boxed at the base button height', entry: 'admin.html', rule: 'size', at: 'file-list-body',
    file: 'admin.html', edits: [['    #file-list-body .admin-btn,\n    #mapper-list-body .admin-btn,\n',
      '    #mapper-list-body .admin-btn,\n']] },
  // The admin tabs round (lead 10-09): what the gate found when it first opened Tables, Chain, Auto Update, Retroactive.
  { name: 'the Chain and Auto Update row buttons boxed at the base button height', entry: 'admin.html', rule: 'size',
    at: 'mapper-list-body', file: 'admin.html', edits: [['    #mapper-list-body .admin-btn,\n    #autoupdate-linked-body .admin-btn,\n    #retry-all-outbox-btn {\n',
      '    #retry-all-outbox-btn {\n']] },
  { name: 'the Backfill column back at 220px beside the collector names', entry: 'admin.html', rule: 'columns', at: 'sec-collectors',
    file: 'admin.html', edits: [['<th title="Run the collector once per day from a start day (KST)">Backfill</th>',
      '<th style="width: 220px;" title="Run the collector once per day from a start day (KST)">Backfill</th>']] },
  { name: 'the path face breaking the server sentences between any two letters', entry: 'admin.html', rule: 'words', at: 'cfg-path',
    file: 'admin.html', edits: [['      color: var(--text-dim);\n      overflow-wrap: anywhere;\n    }\n',
      '      color: var(--text-dim);\n      word-break: break-all;\n    }\n']] },
  { name: 'the Retroactive list line cut without saying so', entry: 'admin.html', rule: 'clip', at: 'retroactive-sub',
    file: 'admin.html', edits: [['<span class="section-summary" id="retroactive-sub" data-clip-ok></span>',
      '<span class="section-summary" id="retroactive-sub"></span>']] },
  { name: 'the ledger sources table back on its hand widths (Source 150px, the timestamp the rest)', entry: 'admin.html',
    rule: 'columns', at: 'ledger-sources', file: 'src/ledger_sources_panel.js', edits: [
      ["      if (fit) th.className = 'cell-fit';", "      th.style.width = { Source: '150px', State: '130px', Refused: '70px' }[label] || '';"],
      ["    if (fit) td.className = 'cell-fit';", '']] },
];
async function buildMutant(m) {
  const { build } = await import('vite');
  const out = mkdtempSync(path.join(tmpdir(), 'screens-mutant-'));
  const target = path.join(CLIENT, m.file).replace(/\\/g, '/');
  const hits = new Map(m.edits.map(([a]) => [a, 0]));
  const swap = (code) => {
    for (const [a, b] of m.edits) if (code.includes(a)) { hits.set(a, hits.get(a) + 1); code = code.split(a).join(b); }
    return code;
  };
  const mine = (id) => id.split('?')[0].replace(/\\/g, '/') === target;
  await build({ root: CLIENT, configFile: path.join(CLIENT, 'vite.config.js'), logLevel: 'silent', build: { outDir: out, emptyOutDir: true },
    plugins: [{ name: 'screens-mutant', enforce: 'pre', transform: (code, id) => (mine(id) ? swap(code) : null),
      transformIndexHtml: { order: 'pre', handler: (html, ctx) => (mine(ctx.filename) ? swap(html) : html) } }] });
  for (const [a, n] of hits) if (!n) throw new Error(`mutant «${m.name}»: «${a.slice(0, 60)}» is not in ${m.file}`);
  return out;
}
if (MUTATE) {
  for (const m of MUTANTS) {
    ran += 1;
    const out = await buildMutant(m);
    try {
      const got = (await runScreens(out, 'mutant', m.entry)).found
        .filter((f) => f.rule === m.rule && f.path.includes(m.at) && (!m.says || m.says.test(f.what)));
      if (!got.length) failed += 1;
      console.log(`${got.length ? '✓' : '✗'} mutant «${m.name}» ${got.length ? `red: ${got[0].path} · ${got[0].what}` : `ESCAPED - no ${m.rule} line at ${m.at}`}`);
    } finally {
      rmSync(out, { recursive: true, force: true });
    }
  }
}
console.log(`ASSERTIONS ${ran} ${failed}`);
process.exit(failed ? 1 : 0);
