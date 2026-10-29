// STALL LINE — the admin header's last freeze (owner 10-29 «ㄴ», A 63a69b97a), scored.
//
// The subject is imported whole (owner 2026-09-02: 잘라쓰기 하니스 절대 금지). What is scored:
//   A  stallOf: /health not read keeps what is drawn (undefined) · no freeze yet (null) · a freeze ({line, at})
//   B  the line drawn as the server wrote it, with its time; null hides it; a read without the key leaves it; two lines apart
// Run: node client2/tests/stall_line_harness.mjs
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import * as BASELINE from '../src/stall_line.js';
import { localShort } from '../src/server_time.js';

const SRC_PATH = fileURLToPath(new URL('../src/stall_line.js', import.meta.url));
let passed = 0;
let failed = 0;
function ok(name, cond, saw) {
  if (cond) { passed++; console.log(`  ok   ${name}`); }
  else { failed++; console.log(`  FAIL ${name}${saw === undefined ? '' : `  saw: ${JSON.stringify(saw)}`}`); }
}
function die(msg) { console.log(`HARNESS FAILURE: ${msg}`); console.log(`ASSERTIONS ${passed} ${failed + 1}`); process.exit(1); }

function makeDoc() {
  const doc = {
    createElement(tag) {
      return { tagName: String(tag).toUpperCase(), className: '', children: [], hidden: false, _text: '',
        get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); },
        set textContent(v) { this._text = String(v); this.children = []; },
        appendChild(c) { this.children.push(c); return c; } };
    },
  };
  return doc;
}
const part = (root, cls) => root.children.find((c) => c.className === cls);

const LINE = 'STALL 14s L12 T40/40 G6 D9/11s C97 slot2:61 ING dt_log';
const AT = '2026-10-29T01:23:45+00:00';
const X = BASELINE;

console.log('\n── A. WHAT /health SAYS ────────────────────────────────────────────');
{
  ok('A1 a freeze: its line and time', JSON.stringify(X.stallOf({ stall: { line: LINE, at: AT } })) === JSON.stringify({ line: LINE, at: AT }));
  ok('A2 none since the server started: null', X.stallOf({ stall: null }) === null);
  ok('A3 /health not read: undefined (what is drawn stays)', X.stallOf(null) === undefined && X.stallOf(undefined) === undefined);
  ok('A4 a /health without the key (an older server): undefined', X.stallOf({ status: 'ok' }) === undefined);
  ok('A5 an empty line is no freeze', X.stallOf({ stall: { line: '', at: AT } }) === null);
}

console.log('\n── B. THE HEADER LINE ──────────────────────────────────────────────');
{
  const doc = makeDoc();
  const mount = doc.createElement('div');
  const s = new X.StallLine(mount, { doc });
  ok('B1 its own div in the mount, hidden until a freeze is said', mount.children.length === 1 && s.root.hidden === true);
  s.render(X.stallOf({ stall: { line: LINE, at: AT } }));
  ok('B2 the line as the server wrote it, whole', part(s.root, 'stall-line__text').textContent === LINE && s.root.hidden === false);
  ok('B3 ...with its time and its name', part(s.root, 'stall-line__at').textContent === localShort(AT)
    && part(s.root, 'stall-line__label').textContent === X.LAST_STALL);
  s.render(X.stallOf(null));
  ok('B4 a /health that was not read leaves it', part(s.root, 'stall-line__text').textContent === LINE && s.root.hidden === false);
  s.render(X.stallOf({ stall: { line: 'STALL 36s+ L3 T40/40 G1 D2/3s C40 slot1:12', at: AT } }));
  ok('B5 a newer freeze replaces it - a «+» still on, no ING cell', part(s.root, 'stall-line__text').textContent === 'STALL 36s+ L3 T40/40 G1 D2/3s C40 slot1:12');
  s.render(X.stallOf({ stall: null }));
  ok('B6 none since a restart hides it', s.root.hidden === true);
  const m2 = doc.createElement('div');
  const t = new X.StallLine(m2, { doc });
  t.render(X.stallOf({ stall: { line: LINE, at: AT } }));
  ok('B7 two lines apart', s.root.hidden === true && t.root.hidden === false && m2.children[0] !== mount.children[0]);
}

const swap = (from, to) => (src) => {
  if (!src.includes(from)) die(`mutation anchor stopped matching: ${JSON.stringify(from)}`);
  return src.replace(from, to);
};
const DEFECTS = [
  ['M1 a /health not read clears the line', swap("!('stall' in health)) return undefined;", "!('stall' in health)) return null;")],
  ['M2 the line drawn in the screen\'s own words', swap('this.text.textContent = stall ? stall.line : \'\';', 'this.text.textContent = stall ? stall.line.split(\' \')[0] : \'\';')],
  ['M3 «not read» hides it', swap('    if (stall === undefined) return;\n', '')],
  ['M4 its time dropped', swap("this.at.textContent = stall && stall.at ? localShort(stall.at) : '';", "this.at.textContent = '';")],
];
const CONTROLS = [
  ['a local rename', (src) => src.replace(/\bhealth\b/g, 'body')],
  ['comments stripped', (src) => src.split('\n').filter((l) => !l.trim().startsWith('//')
    && !l.trim().startsWith('*') && !l.trim().startsWith('/*')).join('\n')],
];

function verdict(M) {
  if (M.stallOf(null) !== undefined || M.stallOf({ stall: null }) !== null) return true;
  const doc = makeDoc();
  const s = new M.StallLine(doc.createElement('div'), { doc });
  s.render(M.stallOf({ stall: { line: LINE, at: AT } }));
  if (part(s.root, 'stall-line__text').textContent !== LINE || part(s.root, 'stall-line__at').textContent !== localShort(AT)) return true;
  s.render(undefined);
  if (s.root.hidden) return true;
  return false;
}

if (verdict(BASELINE)) die('the scorer already fails on the UNMUTATED module');
async function score(list, mustCatch, heading) {
  console.log(`\n── ${heading} ─────────────────────────────`);
  let hit = 0;
  for (const [name, mutate] of list) {
    let bad;
    try { bad = verdict((await loadWithProbe(SRC_PATH, { mutate, tag: 'stallline' })).module); }
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
