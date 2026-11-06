// STATUS DOT — the head bar's status button (lead 11-05 ③, mockup v3), scored.
//
// The subject is imported whole (owner 2026-09-02: 잘라쓰기 하니스 절대 금지). What is scored:
//   A  statusOf: an offline badge first · a stall within STALL_RECENT_MS · the page's own · a chain running · a badge not
//      read · all well
//   B  the button drawn from its panel's badges and the stall: tone, word, title; a stall not read keeps what is drawn
// Run: node client2/tests/status_dot_harness.mjs
import { register } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';

// stall_line.js opens with its stylesheet's import - answered with an empty module, the modules as they ship
register(pathToFileURL(fileURLToPath(new URL('./lib/css_loader.mjs', import.meta.url))).href);
const BASELINE = await import('../src/status_dot.js');

const SRC_PATH = fileURLToPath(new URL('../src/status_dot.js', import.meta.url));
let passed = 0;
let failed = 0;
function ok(name, cond, saw) {
  if (cond) { passed++; console.log(`  ok   ${name}`); }
  else { failed++; console.log(`  FAIL ${name}${saw === undefined ? '' : `  saw: ${JSON.stringify(saw)}`}`); }
}
function die(msg) { console.log(`HARNESS FAILURE: ${msg}`); console.log(`ASSERTIONS ${passed} ${failed + 1}`); process.exit(1); }

const NOW = Date.parse('2026-11-06T09:00:00Z');
const ago = (ms) => ({ line: 'STALL 14s L12 T40/40 G6 D9/11s C97', at: new Date(NOW - ms).toISOString() });
const ON = (text) => ({ text, cls: 'status-badge online' });
const OFF = (text) => ({ text, cls: 'status-badge offline' });
const NEUTRAL = (text) => ({ text, cls: 'status-badge' });
const WELL = [ON('API: ONLINE'), ON('WS: CONNECTED'), ON('CHAIN: OK')];
const RUNNING = [ON('API: ONLINE'), ON('WS: CONNECTED'), ON('CHAIN: RUNNING')];
const said = (X, badges, stall, ui = null) => JSON.stringify(X.statusOf(badges, stall, NOW, ui));
const is = (tone, word) => JSON.stringify({ tone, word });

/** A panel of three badges and a button with its word span - the markup index.html gives, as node stubs. */
function makePage(badges) {
  const node = (tag, cls = '') => ({ tagName: tag.toUpperCase(), className: cls, children: [], hidden: false, dataset: {}, title: '',
    _text: '', get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); },
    set textContent(v) { this._text = String(v); this.children = []; },
    appendChild(c) { this.children.push(c); return c; },
    querySelector(sel) { return this.querySelectorAll(sel)[0] || null; },
    querySelectorAll(sel) { const cls = sel.replace(/^\./, ''); const out = [];
      const walk = (n) => { for (const c of n.children) { if (c.className.split(' ').includes(cls)) out.push(c); walk(c); } }; walk(this); return out; } });
  const doc = { createElement: (tag) => node(tag), defaultView: {} };
  const button = node('button', 'status-btn');
  button.appendChild(node('span', 'status-btn__dot'));
  button.appendChild(node('span', 'status-btn__word'));
  const panel = node('div', 'status-panel');
  const row = panel.appendChild(node('div', 'status-indicators'));
  const drawn = badges.map((b) => { const e = row.appendChild(node('span', b.cls)); e.textContent = b.text; return e; });
  return { doc, button, panel, drawn, word: () => button.querySelector('.status-btn__word').textContent };
}

const X = BASELINE;
console.log('\n── A. WHAT THE BUTTON SAYS ─────────────────────────────────────────');
{
  ok('A1 all well, no stall: a dot, no word', said(X, WELL, null) === is('ok', ''));
  ok('A2 a badge offline: that badge, said as «API · OFFLINE»', said(X, [OFF('API: OFFLINE'), ...WELL.slice(1)], null) === is('bad', 'API · OFFLINE'));
  ok('A3 ...before a stall a minute old and a chain running', said(X, [OFF('WS: DISCONNECTED'), ...RUNNING.slice(0, 1), RUNNING[2]], ago(60000))
    === is('bad', 'WS · DISCONNECTED'));
  ok('A4 a stall a minute old: STALL', said(X, WELL, ago(60000)) === is('busy', 'STALL'));
  ok('A5 a stall eleven minutes old: all well again', said(X, WELL, ago(11 * 60000)) === is('ok', ''));
  ok('A6 the stall\'s edge: a millisecond inside is STALL, at it is not',
    said(X, WELL, ago(X.STALL_RECENT_MS - 1)) === is('busy', 'STALL') && said(X, WELL, ago(X.STALL_RECENT_MS)) === is('ok', ''));
  ok('A7 a stall with no time it can read is not recent', said(X, WELL, { line: 'STALL 3s', at: 'yesterday' }) === is('ok', ''));
  ok('A8 a chain running: «CHAIN · RUNNING»', said(X, RUNNING, null) === is('busy', 'CHAIN · RUNNING'));
  ok('A9 a recent stall before a chain running', said(X, RUNNING, ago(60000)) === is('busy', 'STALL'));
  ok('A10 a badge not read yet: a grey dot, no word', said(X, [ON('API: ONLINE'), ON('WS: CONNECTED'), NEUTRAL('CHAIN: ?')], null) === is('unknown', ''));
  ok('A11 the recent window is ten minutes', X.STALL_RECENT_MS === 10 * 60 * 1000);
  ok('A12 the page froze a minute ago: «UI STALL»', said(X, RUNNING, null, ago(60000)) === is('busy', 'UI STALL'));
  ok('A13 ...after the server\'s stall and an offline badge', said(X, WELL, ago(60000), ago(30000)) === is('busy', 'STALL')
    && said(X, [OFF('WS: DISCONNECTED'), ...WELL.slice(0, 1), WELL[2]], null, ago(30000)) === is('bad', 'WS · DISCONNECTED'));
  ok('A14 the page froze eleven minutes ago: all well again', said(X, WELL, null, ago(11 * 60000)) === is('ok', ''));
}

console.log('\n── B. THE BUTTON DRAWN ─────────────────────────────────────────────');
{
  const p = makePage(RUNNING);
  const dot = new X.StatusDot(p.button, p.panel, { doc: p.doc, now: () => NOW });
  ok('B1 drawn from the panel\'s badges at once', p.button.dataset.tone === 'busy' && p.word() === 'CHAIN · RUNNING');
  ok('B2 its title the badges\' words', p.button.title === 'API: ONLINE · WS: CONNECTED · CHAIN: RUNNING', p.button.title);
  ok('B3 the server\'s stall line and the page\'s added to its panel, hidden', p.panel.children.length === 3
    && p.panel.children.slice(1).every((c) => c.className === 'stall-line' && c.hidden === true)
    && p.panel.children[2].children[0].textContent === X.LAST_UI_STALL);
  dot.setStall(ago(60000));
  ok('B4 a stall said: STALL, its line shown', p.word() === 'STALL' && p.panel.children[1].hidden === false);
  dot.setStall(undefined);
  ok('B5 a /health not read keeps it', p.word() === 'STALL');
  dot.setStall(null);
  ok('B6 none since a restart: back to the chain', p.word() === 'CHAIN · RUNNING' && p.panel.children[1].hidden === true);
  p.drawn[0].className = 'status-badge offline';
  p.drawn[0].textContent = 'API: OFFLINE';
  dot.draw();
  ok('B7 a badge gone offline, drawn again: said', p.button.dataset.tone === 'bad' && p.word() === 'API · OFFLINE');
  dot.setUiStall(ago(60000));
  ok('B9 the page froze: its line shown under «Last UI stall», the button says it after an offline badge',
    p.panel.children[2].hidden === false && p.word() === 'API · OFFLINE');
  const q = makePage(WELL);
  void new X.StatusDot(q.button, q.panel, { doc: q.doc, now: () => NOW });
  ok('B8 two buttons apart', q.word() === '' && q.button.dataset.tone === 'ok' && p.word() === 'API · OFFLINE');
}

const swap = (from, to) => (src) => {
  if (!src.includes(from)) die(`mutation anchor stopped matching: ${JSON.stringify(from)}`);
  return src.replace(from, to);
};
const DEFECTS = [
  ['M1 an offline badge not seen', swap('/\\boffline\\b/.test(b.cls)', '/\\boff\\b/.test(b.cls)')],
  ['M2 the recent window an hour', swap('10 * 60 * 1000', '60 * 60 * 1000')],
  ['M3 the window\'s edge counted in', swap('now - at.getTime() < STALL_RECENT_MS', 'now - at.getTime() <= STALL_RECENT_MS')],
  ['M4 a chain running not said', swap('/:\\s*RUNNING$/', '/:\\s*RUN$/')],
  ['M5 a stall before an offline badge', swap("  const bad = badges.find((b) => /\\boffline\\b/.test(b.cls));\n  if (bad) return { tone: 'bad', word: wordOf(bad.text) };\n",
    '')],
  ['M6 a /health not read clears the stall', swap('    if (stall === undefined) return;\n', '')],
  ['M7 the word said in the badge\'s own spelling', swap(".replace(/:\\s*/, ' · ')", '')],
  ['M8 the page\'s freeze not said', swap("  if (recent(uiStall, now)) return { tone: 'busy', word: 'UI STALL' };\n", '')],
];
const CONTROLS = [
  ['a local rename', (src) => src.replace(/\bbadges\b/g, 'seen')],
  ['comments stripped', (src) => src.split('\n').filter((l) => !l.trim().startsWith('//')
    && !l.trim().startsWith('*') && !l.trim().startsWith('/*')).join('\n')],
];

function verdict(M) {
  if (said(M, WELL, null) !== is('ok', '') || said(M, [OFF('API: OFFLINE'), ...RUNNING.slice(1)], ago(60000)) !== is('bad', 'API · OFFLINE')) return true;
  if (said(M, WELL, ago(11 * 60000)) !== is('ok', '') || said(M, WELL, ago(M.STALL_RECENT_MS)) !== is('ok', '')) return true;
  if (said(M, RUNNING, null) !== is('busy', 'CHAIN · RUNNING')) return true;
  if (said(M, RUNNING, null, ago(60000)) !== is('busy', 'UI STALL')) return true;
  const p = makePage(WELL);
  const dot = new M.StatusDot(p.button, p.panel, { doc: p.doc, now: () => NOW });
  dot.setStall(ago(60000));
  dot.setStall(undefined);
  return p.word() !== 'STALL';
}

if (verdict(BASELINE)) die('the scorer already fails on the UNMUTATED module');
async function score(list, mustCatch, heading) {
  console.log(`\n── ${heading} ─────────────────────────────`);
  let hit = 0;
  for (const [name, mutate] of list) {
    let bad;
    try { bad = verdict((await loadWithProbe(SRC_PATH, { mutate, tag: 'statusdot' })).module); }
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
