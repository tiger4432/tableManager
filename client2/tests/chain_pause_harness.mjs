// CHAIN PAUSE — the emergency stop's control (lead 668fa004c), scored.
//
// The subject is imported (owner 2026-09-02: 잘라쓰기 하니스 절대 금지). What is scored:
//   ① the state line's three shapes the lead named — running · paused · requested paused while
//      the worker still runs — plus the reverse and an unreadable state
//   ② the route each button sends, and that Pause asks once before it sends
//   ③ two instances on one page do not interfere, and a re-read keeps a reason being typed
// Run: node client2/tests/chain_pause_harness.mjs
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import * as BASELINE from '../src/chain_pause.js';

const SRC_PATH = fileURLToPath(new URL('../src/chain_pause.js', import.meta.url));
let passed = 0;
let failed = 0;
function ok(name, cond, saw) {
  if (cond) { passed++; console.log(`  ok   ${name}`); }
  else { failed++; console.log(`  FAIL ${name}${saw === undefined ? '' : `  saw: ${JSON.stringify(saw)}`}`); }
}
function die(msg) { console.log(`HARNESS FAILURE: ${msg}`); console.log(`ASSERTIONS ${passed} ${failed + 1}`); process.exit(1); }

// ── a DOM just big enough: the part builds, sets text, listens and is clicked ───────────
function makeDoc() {
  const doc = {
    createElement(tag) {
      const el = {
        tagName: String(tag).toUpperCase(), className: '', children: [], parentNode: null,
        attrs: {}, listeners: {}, _text: '', value: '', disabled: false, type: '', placeholder: '',
        get textContent() { return this._text + this.children.map((c) => c.textContent).join(' '); },
        set textContent(v) { this._text = String(v); this.children = []; },
        appendChild(c) { c.parentNode = this; this.children.push(c); return c; },
        setAttribute(k, v) { this.attrs[k] = String(v); },
        getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
        addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); },
        fire(type) { (this.listeners[type] || []).forEach((fn) => fn({ target: this })); },
        click() { if (!this.disabled) this.fire('click'); },
      };
      el.ownerDocument = doc;
      return el;
    },
  };
  return doc;
}
const find = (el, cls) => {
  if (!el) return null;
  if (String(el.className).split(' ').includes(cls)) return el;
  for (const c of el.children) { const hit = find(c, cls); if (hit) return hit; }
  return null;
};
const tick = async () => { for (let i = 0; i < 5; i++) await Promise.resolve(); };

const X = BASELINE;
const PAUSED = { read: true, paused: { by: 'operator', at: '2026-09-26T21:03:12', reason: 'bad join' } };
const RUNNING = { read: true, paused: null };
const W = (status) => ({ status, detail: `worker says ${status}` });

console.log('\n── A. THE STATE LINE — the shapes the lead named ─────────────────────');
{
  const run = X.chainPauseView(RUNNING, W('ok'));
  ok('A1 nothing requested: Running, the button pauses, no worker line', run.state === 'running'
    && run.line === 'Running' && run.action === 'pause' && run.worker === null, run);
  const both = X.chainPauseView(PAUSED, W('paused'));
  ok('A2 paused and taken: who, when (server time) and why on one line; the button resumes',
    both.state === 'paused' && both.action === 'resume' && both.worker === null
      && both.line === 'Paused by operator at 2026-09-26 21:03:12 (server time) · bad join', both);
  const notYet = X.chainPauseView(PAUSED, W('ok'));
  ok('A3 requested but the worker still runs: both are said, in the worker\'s own word',
    notYet.line === both.line && notYet.worker && notYet.worker.text === 'Worker: ok · not paused yet'
      && notYet.worker.title === 'worker says ok', notYet);
  const lingering = X.chainPauseView(RUNNING, W('paused'));
  ok('A4 resumed but the worker still paused: both are said', lingering.state === 'running'
    && lingering.worker && lingering.worker.text.startsWith('Worker: paused'), lingering);
  const unread = X.chainPauseView({ read: false, reason: 'Server is older than this screen' }, null);
  ok('A5 an unreadable state says why and still offers Pause — pausing is safe from any state',
    unread.state === 'unknown' && unread.action === 'pause' && unread.line.includes('older than'), unread);
  const blind = X.chainPauseView(PAUSED, null);
  ok('A6 an unread worker invents no worker line', blind.worker === null, blind);
  const bare = X.chainPauseView({ read: true, paused: { by: 'operator' } }, null);
  ok('A7 no time and no reason given: none drawn', bare.line === 'Paused by operator', bare.line);
}

console.log('\n── B. THE ROUTE EACH BUTTON SENDS ───────────────────────────────────');
{
  ok('B1 pause sends its reason to the pause route', JSON.stringify(X.pauseRequest('pause', ' bad join '))
    === JSON.stringify({ path: '/admin/chain/pause', body: { reason: 'bad join' } }), X.pauseRequest('pause', ' bad join '));
  ok('B2 resume goes to the resume route', X.pauseRequest('resume', 'x').path === '/admin/chain/resume');

  const doc = makeDoc();
  const host = doc.createElement('div');
  const sent = [];
  const part = new X.ChainPauseControl(host, { doc, send: async (req) => { sent.push(req); return { ok: true }; } });
  part.render(X.chainPauseView(RUNNING, W('ok')));
  const input = find(host, 'chain-pause-reason');
  input.value = 'bad join';
  input.fire('input');
  find(host, 'chain-pause-go').click();
  ok('B3 pressing Pause asks first — nothing is sent yet', sent.length === 0
    && find(host, 'chain-pause-ask') !== null, sent);
  find(host, 'chain-pause-confirm').click();
  await tick();
  ok('B4 confirming sends once, to the pause route, with the typed reason',
    sent.length === 1 && sent[0].path === '/admin/chain/pause' && sent[0].body.reason === 'bad join', sent);

  const sent2 = [];
  const other = new X.ChainPauseControl(doc.createElement('div'), { doc, send: async (r) => { sent2.push(r); return { ok: true }; } });
  other.render(X.chainPauseView(RUNNING, null));
  find(other.root, 'chain-pause-go').click();
  find(other.root, 'chain-pause-cancel').click();
  ok('B5 Cancel sends nothing and puts the Pause button back', sent2.length === 0
    && find(other.root, 'chain-pause-go') !== null && find(other.root, 'chain-pause-ask') === null);

  const sent3 = [];
  const paused = new X.ChainPauseControl(doc.createElement('div'), { doc, send: async (r) => { sent3.push(r); return { ok: true }; } });
  paused.render(X.chainPauseView(PAUSED, W('paused')));
  ok('B6 a paused chain offers Resume and no Pause', find(paused.root, 'chain-pause-resume') !== null
    && find(paused.root, 'chain-pause-go') === null);
  find(paused.root, 'chain-pause-resume').click();
  await tick();
  ok('B7 Resume sends once, to the resume route', sent3.length === 1 && sent3[0].path === '/admin/chain/resume', sent3);

  const refused = new X.ChainPauseControl(doc.createElement('div'), { doc,
    send: async () => ({ ok: false, error: 'Admin token rejected (HTTP 401)' }) });
  refused.render(X.chainPauseView(PAUSED, null));
  find(refused.root, 'chain-pause-resume').click();
  await tick();
  ok('B8 a refusal stays on the line, in the words it came with',
    find(refused.root, 'chain-pause-said').textContent === 'Admin token rejected (HTTP 401)');
}

console.log('\n── C. TWO INSTANCES · A RE-READ ─────────────────────────────────────');
{
  const doc = makeDoc();
  const a = new X.ChainPauseControl(doc.createElement('div'), { doc, send: async () => ({ ok: true }) });
  const b = new X.ChainPauseControl(doc.createElement('div'), { doc, send: async () => ({ ok: true }) });
  const view = X.chainPauseView(RUNNING, W('ok'));
  a.render(view);
  b.render(view);
  find(a.root, 'chain-pause-go').click();
  ok('C1 asking in one instance does not ask in the other', find(a.root, 'chain-pause-ask') !== null
    && find(b.root, 'chain-pause-ask') === null);
  const input = find(b.root, 'chain-pause-reason');
  input.value = 'typing';
  input.fire('input');
  b.render(X.chainPauseView(RUNNING, W('ok')));
  ok('C2 the page\'s re-read keeps the reason being typed — the same input, the same text',
    find(b.root, 'chain-pause-reason') === input && input.value === 'typing');
  a.render(X.chainPauseView(PAUSED, W('paused')));
  ok('C3 a new state reaches the instance it is given to only', find(a.root, 'chain-pause-line').textContent.startsWith('Paused')
    && find(b.root, 'chain-pause-line').textContent === 'Running');
}

// ── mutants ─────────────────────────────────────────────────────────────────────────
const swap = (from, to) => (src) => {
  if (!src.includes(from)) die(`mutation anchor stopped matching: ${JSON.stringify(from)}`);
  return src.replace(from, to);
};
const DEFECTS = [
  ['M1 a pause the worker has not taken reads as a stopped chain',
    swap("worker: word && word !== 'paused' ? said(`Worker: ${word} · not paused yet`) : null };", 'worker: null };')],
  ['M2 the paused state offers Pause instead of Resume',
    swap("return { state: 'paused', tone: 'warn', action: 'resume',", "return { state: 'paused', tone: 'warn', action: 'pause',")],
  ['M3 Pause sends without asking',
    swap('() => this._confirm(true));', "() => this._fire('pause'));")],
  ['M4 the reason is not sent',
    swap("body: { reason: String(reason || '').trim() } };", 'body: {} };')],
  ['M5 Resume sends to the pause route',
    swap("? { path: RESUME_ROUTE, body: {} }", "? { path: PAUSE_ROUTE, body: {} }")],
  ['M6 an unreadable state hides Pause',
    swap("return { state: 'unknown', tone: '', action: 'pause',", "return { state: 'unknown', tone: '', action: 'resume',")],
  ['M7 every re-read redraws the controls and wipes the reason being typed',
    swap('if (key !== this.drawn) this._drawControls(key);', 'this._drawControls(key);')],
  ['M8 the time is drawn without saying whose clock it is',
    swap(' (server time)', '')],
];
const CONTROLS = [
  ['a local rename', (src) => src.replace(/\bconfirming\b/g, 'asking')],
  ['comments stripped', (src) => src.split('\n').filter((l) => !l.trim().startsWith('//')
    && !l.trim().startsWith('*') && !l.trim().startsWith('/*')).join('\n')],
];

/** The same questions as above, asked of a (possibly mutated) module. true = something is wrong. */
async function verdict(M) {
  const v = (r, w) => M.chainPauseView(r, w);
  if (!(v(PAUSED, W('ok')).worker)) return true;
  if (v(PAUSED, W('paused')).action !== 'resume') return true;
  if (v({ read: false }, null).action !== 'pause') return true;
  if (!v(PAUSED, null).line.includes('(server time)')) return true;
  if (M.pauseRequest('resume').path !== '/admin/chain/resume') return true;
  if (M.pauseRequest('pause', 'r').body.reason !== 'r') return true;
  const doc = makeDoc();
  const sent = [];
  const part = new M.ChainPauseControl(doc.createElement('div'), { doc, send: async (r) => { sent.push(r); return { ok: true }; } });
  part.render(M.chainPauseView(RUNNING, null));
  const input = find(part.root, 'chain-pause-reason');
  input.value = 'x';
  input.fire('input');
  part.render(M.chainPauseView(RUNNING, null));
  if (find(part.root, 'chain-pause-reason') !== input) return true;
  find(part.root, 'chain-pause-go').click();
  await tick();
  if (sent.length !== 0) return true;
  return false;
}

if (await verdict(BASELINE)) die('the scorer already fails on the UNMUTATED module');
async function score(list, mustCatch, heading) {
  console.log(`\n── ${heading} ─────────────────────────────`);
  let hit = 0;
  for (const [name, mutate] of list) {
    let bad;
    try { bad = await verdict((await loadWithProbe(SRC_PATH, { mutate, tag: 'chainpause' })).module); }
    catch (e) { if (/did not mutate|unchanged/.test(String(e && e.message))) die(`${name}: ${e.message}`); bad = true; }
    if (bad === mustCatch) { hit++; console.log(`  ${mustCatch ? 'caught ' : 'escaped'} ${name}`); }
    else { failed++; console.log(`  ${mustCatch ? 'ESCAPED' : 'CAUGHT '} ${name}  <- wrong`); }
  }
  return hit;
}
const caught = await score(DEFECTS, true, 'defect mutants (each must be CAUGHT)');
const escaped = await score(CONTROLS, false, 'control mutants (each must ESCAPE)');
console.log(`\n${passed} passed, ${failed} failed; ${caught}/${DEFECTS.length} defects caught; `
  + `${escaped}/${CONTROLS.length} controls escaped.`);
console.log(`ASSERTIONS ${passed} ${failed}`);
if (failed) process.exit(1);
