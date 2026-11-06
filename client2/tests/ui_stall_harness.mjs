// UI STALL — the page's own freeze said as one line (lead 11-06 ㄱ), scored. The subject is imported whole.
//   A  workOf: the marked slice a task spent most of its time in; none, null
//   B  the line: «UI 3.4s <what> <table> <rows>», the parts there are; nothing marked, «?»
//   C  markWork: a mark ends with its synchronous slice - before the next await's continuation
//   D  the watch: a long task under a second says nothing, one of a second says its line once; a stall the page cannot
//      draw goes quiet in one console line; without long tasks, the gap between two frames while shown
//   S  the seats: each heavy place the census found (11-06) marks its slice - by the AST, the call inside the function
// Run: node client2/tests/ui_stall_harness.mjs
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';

const SRC = (f) => fileURLToPath(new URL(`../src/${f}`, import.meta.url));
const X = await import('../src/ui_stall.js');
let passed = 0;
let failed = 0;
function ok(name, cond, saw) {
  if (cond) { passed++; console.log(`  ok   ${name}`); }
  else { failed++; console.log(`  FAIL ${name}${saw === undefined ? '' : `  saw: ${JSON.stringify(saw)}`}`); }
}
function die(msg) { console.log(`HARNESS FAILURE: ${msg}`); console.log(`ASSERTIONS ${passed} ${failed + 1}`); process.exit(1); }

const W = (name, start, end, table = null, rows = null) => ({ name, start, end, table, rows });
const LOG = [W('rows', 0, 50, 'dt_log', 40), W('ws batch_row_upsert', 100, 3500, 'dt_log', 500), W('fit widths', 3400, 3450)];

/** Every scored answer of a module, one value - a mutant is caught when it differs. */
async function answers(M) {
  const out = {};
  out.A = [M.workOf(30, 3400, LOG) && M.workOf(30, 3400, LOG).name, M.workOf(5000, 1200, LOG),
    M.workOf(3390, 1100, [W('open', 3000, null)]) && M.workOf(3390, 1100, [W('open', 3000, null)]).name];
  out.B = [M.uiStallLine(3400, LOG[1]), M.uiStallLine(1200, null), M.uiStallLine(2000, W('history', 0, 1)),
    M.uiStallLine(1050, W('rows', 0, 1, 'lot_event', 0))];
  // C: a mark's end is set before the code after an await runs
  let endAtAwait = 'unset';
  const before = performance.now();
  await (async () => {
    M.markWork('slice', 't', 1);
    await null;
    const mine = M.workOf(before, 0.0001 + performance.now() - before);
    endAtAwait = mine && mine.name === 'slice' ? mine.end !== null : 'not found';
  })();
  out.C = endAtAwait;
  // C2: a slice with more marks inside it than the log keeps still names the task by its own mark
  let outer = 'unset';
  await (async () => {
    const t0 = performance.now();
    M.markWork('ws batch_row_upsert', 'dt_log', 500);
    for (let i = 0; i < 300; i += 1) M.markWork('history widths', null, 1);
    const spent = performance.now() - t0 + 0.0001;
    const named = M.workOf(t0, spent);
    outer = named && named.name;
    await null;
  })();
  out.C2 = outer;
  // D: the watch over a fake long-task observer
  const said = [];
  let deliver = null;
  class Observer { constructor(fn) { deliver = (entries) => fn({ getEntries: () => entries }); } observe() {} }
  Observer.supportedEntryTypes = ['longtask'];
  new M.UiStallWatch({ view: { PerformanceObserver: Observer }, onStall: (s) => said.push(s), nowIso: () => '2026-11-06T09:00:00Z' });
  deliver([{ startTime: 10, duration: 999 }]);
  const under = said.length;
  deliver([{ startTime: 10, duration: 1000 }]);
  out.D = [under, said.length, said[0] && said[0].at, said[0] && /^UI 1\.0s /.test(said[0].line)];
  const warn = console.warn;
  let warned = 0;
  console.warn = () => { warned += 1; };
  let threw = false;
  try {
    let d2 = null;
    class O2 { constructor(fn) { d2 = (e) => fn({ getEntries: () => e }); } observe() {} }
    O2.supportedEntryTypes = ['longtask'];
    new M.UiStallWatch({ view: { PerformanceObserver: O2 }, onStall: () => { throw new Error('panel gone'); } });
    d2([{ startTime: 0, duration: 2000 }]);
  } catch { threw = true; }
  console.warn = warn;
  out.D2 = [threw, warned];
  // the gap between two frames, while shown and while hidden
  const frames = [];
  const doc = { hidden: false };
  const seen = [];
  new M.UiStallWatch({ view: { requestAnimationFrame: (fn) => frames.push(fn), document: doc }, onStall: (s) => seen.push(s.line) });
  const tick = (at) => frames.shift()(at);
  const T0 = 1e9;
  tick(T0); tick(T0 + 16); tick(T0 + 1416);
  doc.hidden = true; tick(T0 + 1432);
  doc.hidden = false; tick(T0 + 9000); tick(T0 + 9016);
  out.D3 = seen;
  return out;
}

const base = await answers(X);
console.log('\n── A · B · C · D ──────────────────────────────────────────────────');
ok('A1 a task is named by the slice it spent most of its time in', base.A[0] === 'ws batch_row_upsert', base.A[0]);
ok('A2 a task in no marked slice: none', base.A[1] === null, base.A[1]);
ok('A3 a slice not yet ended counts as running', base.A[2] === 'open', base.A[2]);
ok('B1 «UI 3.4s ws batch_row_upsert dt_log 500»', base.B[0] === 'UI 3.4s ws batch_row_upsert dt_log 500', base.B[0]);
ok('B2 nothing marked: «UI 1.2s ?»', base.B[1] === 'UI 1.2s ?', base.B[1]);
ok('B3 the parts there are: no table, no rows', base.B[2] === 'UI 2.0s history', base.B[2]);
ok('B4 a count of 0 rows is said', base.B[3] === 'UI 1.1s rows lot_event 0', base.B[3]);
ok('C1 a mark ends with its slice - ended before the code after an await runs', base.C === true, base.C);
ok('C2 300 marks inside one slice: the task still named by the slice\'s own mark', base.C2 === 'ws batch_row_upsert', base.C2);
ok('D1 under a second nothing; a second, its line once with its time', JSON.stringify(base.D) === JSON.stringify([0, 1, '2026-11-06T09:00:00Z', true]), base.D);
ok('D2 a stall that cannot be said: one console line, nothing thrown', JSON.stringify(base.D2) === '[false,1]', base.D2);
ok('D3 without long tasks: a frame gap of 1.4 s said, a hidden page\'s gap not', JSON.stringify(base.D3) === '["UI 1.4s ?"]', base.D3);

// S — the seats: each heavy place the census found marks its slice (AST: a markWork call inside the named function)
const req = createRequire(SRC('ui_stall.js'));
const { parseAst } = await import(pathToFileURL(req.resolve('rolldown/parseAst')).href);
const SEATS = [['websocket.js', 'initWebSocket'], ['api.js', 'fetchData'], ['api.js', 'applyStaged'], ['grid.js', 'renderGrid'],
  ['grid.js', 'fitColumnWidths'], ['grid.js', 'renderFilterBar'], ['clipboard.js', 'pasteText'], ['timeline.js', 'renderTimeline'],
  ['timeline.js', 'renderGlobalTimeline'], ['timeline.js', 'measureAuditTable'], ['main.js', 'init']];
function marksIn(file) {
  const ast = parseAst(readFileSync(SRC(file), 'utf8'), { sourceType: 'module' }, file);
  const found = new Map();
  const visit = (node, owner) => {
    if (!node || typeof node !== 'object') return;
    if (Array.isArray(node)) { for (const n of node) visit(n, owner); return; }
    const here = owner || (node.type === 'FunctionDeclaration' && node.id ? node.id.name : null);
    if (node.type === 'CallExpression' && node.callee.type === 'Identifier' && node.callee.name === 'markWork') {
      const k = here || '(top level)';
      found.set(k, (found.get(k) || 0) + 1);
    }
    for (const k of Object.keys(node)) if (k !== 'type') visit(node[k], here);
  };
  visit(ast.body, null);
  return found;
}
const byFile = new Map();
const missing = SEATS.filter(([file, fn]) => {
  if (!byFile.has(file)) byFile.set(file, marksIn(file));
  return !byFile.get(file).get(fn);
});
const total = [...byFile.values()].reduce((sum, m) => sum + [...m.values()].reduce((a, b) => a + b, 0), 0);
ok(`S1 every seat of the census marks its slice (${SEATS.length} seats)`, missing.length === 0, missing);
ok('S2 the census is real: marks found in its files', total >= SEATS.length, total);

const once = (from, to) => (src) => {
  const n = src.split(from).length - 1;
  if (n !== 1) die(`mutation anchor matched ${n} times: ${JSON.stringify(from)}`);
  return src.replace(from, to);
};
const DEFECTS = [
  ['M1 the first overlapping slice, not the longest', once('if (overlap > most) { most = overlap; best = work; }', 'if (overlap > most && !best) { most = overlap; best = work; }')],
  ['M2 a slice never ends', once('  queueMicrotask(() => { work.end = performance.now(); });\n', '')],
  ['M3 a second is not a stall', once('if (ms < UI_STALL_MS) return;', 'if (ms <= UI_STALL_MS) return;')],
  ['M4 nothing marked says nothing', once("if (!work) parts.push('?');", "if (!work) parts.push('');")],
  ['M5 the line throws out of the observer', once("    try { this.onStall({ line: uiStallLine(ms, workOf(start, ms)), at: this.nowIso() }); }\n    catch (err) { console.warn('[ui stall] a stall was not said:', err && err.message); }\n",
    '    this.onStall({ line: uiStallLine(ms, workOf(start, ms)), at: this.nowIso() });\n')],
  ['M6 a hidden page\'s frame gap said', once('if (doc && doc.hidden) last = null;', 'if (false) last = null;')],
  ['M7 a count of 0 rows dropped', once('if (isCount(work.rows))', 'if (work.rows)')],
  ['M8 an open slice let go when the log is full', once('if (works.length > KEEP && works[0].end !== null) works.shift();', 'if (works.length > KEEP) works.shift();')],
];
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
if (failed) die('the scorer already fails on the UNMUTATED module');
let caught = 0;
console.log('\n── defect mutants (each must be CAUGHT) ─────────────────────────────');
for (const [name, mutate] of DEFECTS) {
  let bad;
  try { bad = !same(await answers((await loadWithProbe(SRC('ui_stall.js'), { mutate, tag: 'uistall' })).module), base); }
  catch (e) { if (/did not mutate|unchanged/.test(String(e && e.message))) die(`${name}: ${e.message}`); bad = true; }
  if (bad) { caught++; console.log(`  caught  ${name}`); } else { failed++; console.log(`  ESCAPED ${name}  <- wrong`); }
}
console.log(`\n${passed} passed, ${failed} failed; ${caught}/${DEFECTS.length} defects caught.`);
console.log(`ASSERTIONS ${passed} ${failed}`);
if (failed) process.exit(1);
