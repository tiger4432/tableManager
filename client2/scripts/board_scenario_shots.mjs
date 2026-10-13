// The Board's scenario in the built page on a live box (lead 10-13: «헤드리스 한 번(1280x800, 스샷 넷: A·B·C·D)»): one
// headless Chrome serves client2/dist and hands /api to the box, the page opens the save board_scenario_live.mjs wrote
// (--save), the start row picks the bonding wafer the way a person does, then A's first die cell, B's first core wafer,
// C's first step are pressed in turn - a screenshot after each and one of D. Chrome is closed at the end.
//
//   node client2/scripts/board_scenario_shots.mjs --scenario <saved.json> --out <dir> [--api http://127.0.0.1:18766]
// CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
import { readFileSync, writeFileSync, existsSync, mkdtempSync, rmSync, mkdirSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const argOf = (k, d) => (process.argv.includes(k) ? process.argv[process.argv.indexOf(k) + 1] : d);
const API = argOf('--api', 'http://127.0.0.1:18766');
const OUT = argOf('--out', null);
const scenario = JSON.parse(readFileSync(argOf('--scenario', ''), 'utf8'));
const DIST = path.join(HERE, '..', 'dist');
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const ORIGIN = 'http://board.test';
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.png': 'image/png', '.json': 'application/json' };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
mkdirSync(OUT, { recursive: true });

const profile = mkdtempSync(path.join(tmpdir(), 'board-shots-'));
const port = 9800 + Math.floor(Math.random() * 100);
const proc = spawn(CHROME, ['--headless=new', '--hide-scrollbars', `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, '--window-size=1280,800', 'about:blank'], { stdio: 'ignore' });
let target;
for (let i = 0; i < 75 && !target; i += 1) {
  await sleep(200);
  try { target = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((t) => t.type === 'page'); } catch { /* not up yet */ }
}
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((ok) => ws.addEventListener('open', ok));
let id = 0;
const waiting = new Map();
const thrown = [];
const asked = [];
const send = (method, params = {}) => new Promise((ok) => { id += 1; waiting.set(id, ok); ws.send(JSON.stringify({ id, method, params })); })
  .then((m) => { if (m.error) throw new Error(`${method}: ${m.error.message}`); return m.result; });
ws.addEventListener('message', async (e) => {
  const m = JSON.parse(e.data);
  if (m.id && waiting.has(m.id)) { waiting.get(m.id)(m); waiting.delete(m.id); return; }
  if (m.method === 'Runtime.exceptionThrown') thrown.push(String((m.params.exceptionDetails.exception || {}).description || m.params.exceptionDetails.text).slice(0, 200));
  if (m.method !== 'Fetch.requestPaused') return;
  const { requestId, request } = m.params;
  const u = new URL(request.url);
  const fulfil = (status, type, body) => send('Fetch.fulfillRequest', { requestId, responseCode: status, responseHeaders: [{ name: 'Content-Type', value: type }], body: Buffer.from(body).toString('base64') }).catch(() => {});
  if (u.origin !== ORIGIN) { send('Fetch.failRequest', { requestId, errorReason: 'BlockedByClient' }).catch(() => {}); return; }
  if (u.pathname.startsWith('/api/')) {
    if (u.pathname.includes('/subgraph')) asked.push(u.search);
    try {
      const r = await fetch(API + u.pathname + u.search, { method: request.method });
      fulfil(r.status, r.headers.get('content-type') || 'application/json', Buffer.from(await r.arrayBuffer()));
    } catch (err) { fulfil(502, 'text/plain', String(err)); }
    return;
  }
  const file = path.join(DIST, decodeURIComponent(u.pathname));
  if (existsSync(file) && path.extname(file)) fulfil(200, MIME[path.extname(file)] || 'application/octet-stream', readFileSync(file));
  else fulfil(404, 'text/plain', '');
});
const evaluate = async (expression) => {
  const r = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(`in page: ${(r.exceptionDetails.exception || {}).description || r.exceptionDetails.text}`);
  return r.result.value;
};
const until = async (expression, ms = 60000) => { const t0 = Date.now(); while (!(await evaluate(expression))) { if (Date.now() - t0 > ms) throw new Error(`timed out: ${expression}`); await sleep(200); } await sleep(800); };
const shot = async (name) => { const r = await send('Page.captureScreenshot', { format: 'png' }); writeFileSync(path.join(OUT, name), Buffer.from(r.data, 'base64')); console.log(`shot ${name}`); };

try {
  await send('Page.enable');
  await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1280, height: 800, deviceScaleFactor: 1, mobile: false });
  await send('Fetch.enable', { patterns: [{ urlPattern: '*', requestStage: 'Request' }] });
  await send('Page.addScriptToEvaluateOnNewDocument', { source: `try { localStorage.setItem('testbed:visuals', ${JSON.stringify(JSON.stringify(scenario.kept))}); } catch (e) {}` });
  await send('Page.navigate', { url: `${ORIGIN}/testbed.html` });
  const { A, B, C, D } = scenario.ids;
  const inPanel = (pid, sel) => `document.querySelector('[data-panel="${pid}"]') && document.querySelector('[data-panel="${pid}"]').querySelectorAll('${sel}')`;
  await until("document.querySelector('.tb-start__type') && document.querySelector('.tb-start__type').options.length > 0");
  // The start: the type, the key typed, «+» - the start row's own controls.
  await evaluate(`(() => { const s = document.querySelector('.tb-start__type'); s.value = 'wafer'; s.dispatchEvent(new Event('change', { bubbles: true }));
    const i = document.querySelector('.tb-start .wk-input'); i.value = ${JSON.stringify(scenario.wafer)}; i.dispatchEvent(new Event('input', { bubbles: true })); return true; })()`);
  // The key's line in the list picked (a mousedown, as the list takes it), then «+».
  await until(`[...document.querySelectorAll('.tb-start .wk-searchitem')].some((n) => n.textContent.startsWith(${JSON.stringify(scenario.wafer)}))`);
  await evaluate(`(() => { const it = [...document.querySelectorAll('.tb-start .wk-searchitem')].find((n) => n.textContent.startsWith(${JSON.stringify(scenario.wafer)})); it.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true })); return true; })()`);
  await sleep(300);
  await evaluate(`(() => { const b = document.querySelector('.tb-start .wk-basketadd[data-sign="+"]'); b.click(); return true; })()`);
  await until(`(${inPanel(A, 'rect[data-cell]')} || []).length > 0`);
  const t0 = asked.length;
  await evaluate(`(() => { const r = ${inPanel(A, 'rect[data-cell]')}[0]; r.dispatchEvent(new MouseEvent('click', { bubbles: true })); return r.getAttribute('data-cell'); })()`);
  await shot('A_map_die_pressed.png');
  await until(`[...(${inPanel(B, 'th.sf-table__row')} || [])].some((t) => t.textContent.startsWith('SYN-'))`);
  const core = await evaluate(`(() => { const t = [...${inPanel(B, 'th.sf-table__row')}].find((x) => x.textContent.startsWith('SYN-')); t.dispatchEvent(new MouseEvent('click', { bubbles: true })); return t.textContent; })()`);
  await shot('B_core_wafer_pressed.png');
  await until(`[...(${inPanel(C, 'th.sf-table__row')} || [])].some((t) => t.textContent !== '(Empty)')`);
  const step = await evaluate(`(() => { const t = [...${inPanel(C, 'th.sf-table__row')}].find((x) => x.textContent !== '(Empty)'); t.dispatchEvent(new MouseEvent('click', { bubbles: true })); return t.textContent; })()`);
  await shot('C_step_pressed.png');
  await until(`(${inPanel(D, 'canvas')} || []).length > 0`);
  await sleep(2000);
  await shot('D_trend.png');
  const status = await evaluate("[...document.querySelectorAll('.sf-status, .tb-status, footer')].map((n) => n.textContent).join(' | ').slice(0, 300)");
  console.log(`core wafer ${core} · step ${step} · walks after the die press ${asked.length - t0} · all walks ${asked.length}`);
  console.log(`status: ${status}`);
  console.log(`page errors: ${thrown.length ? thrown.join(' / ') : 'none'}`);
} catch (err) {
  console.log(`stopped: ${String(err.message).slice(0, 200)}`);
  try { await shot('stopped.png'); } catch { /* no page */ }
  console.log(`walks asked ${asked.length}: ${asked.slice(-3).join(' | ').slice(0, 300)}`);
  console.log(`page errors: ${thrown.length ? thrown.join(' / ') : 'none'}`);
  try { console.log(`start row: ${await evaluate("(document.querySelector('.tb-start') || {}).textContent")}`); } catch { /* none */ }
} finally {
  try { ws.close(); } catch { /* gone */ }
  proc.kill();
  await sleep(1000);
  try { rmSync(profile, { recursive: true, force: true }); } catch { /* left */ }
}
process.exit(0);
