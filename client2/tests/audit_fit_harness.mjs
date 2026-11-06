// AUDIT FIT — the Global history's Table column width, measured once a frame (owner 11-06 «가만히 있어도 굳음», lead 11-06).
//
// The subject is imported whole (owner 2026-09-02: 잘라쓰기 하니스 절대 금지). What is scored, through the path a live
// message takes (websocket.js gives each created log to appendHistoryLocally; websocket.js itself cannot load in node):
//   A  a message of 500 logs: nothing measured while they land, one frame asked, one layout in it, the widest piece
//   B  a row drawn later only widens the column · the panel hidden measures nothing · shown again (a width change), all
// A layout is counted where the page would force one: a read of a drawn size after a write to the drawn tree.
// Run: node client2/tests/audit_fit_harness.mjs
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';

let passed = 0;
let failed = 0;
function ok(name, cond, saw) {
  if (cond) { passed++; console.log(`  ok   ${name}`); }
  else { failed++; console.log(`  FAIL ${name}${saw === undefined ? '' : `  saw: ${JSON.stringify(saw)}`}`); }
}
function die(msg) { console.log(`HARNESS FAILURE: ${msg}`); console.log(`ASSERTIONS ${passed} ${failed + 1}`); process.exit(1); }

// ── the page: the timeline list and its box, as node stubs; every write to the drawn tree and every read of a drawn
//    size goes on one tape ──
const page = { tape: [], frames: [], resized: null, shown: true };
const CHAR_PX = 7;
const PAD = { paddingLeft: '6.8px', paddingRight: '6.8px', borderRightWidth: '1px' };
const need = (piece) => Math.ceil(piece.length * CHAR_PX + 6.8 + 6.8 + 1);
const cell = {};
const view = { getComputedStyle: () => { page.tape.push('read'); return PAD; } };
const doc = { defaultView: view };
const piecesOf = (html) => [...String(html).matchAll(/<span class="audit-tbl-piece">([^<]*)<\/span>/g)].map(([, text]) => ({
  ownerDocument: doc, closest: () => cell, get offsetWidth() { page.tape.push('read'); return text.length * CHAR_PX; } }));
// A Table cell's name: one line while the box holds names whole (.audit-tbl-whole), else as wide as its widest piece.
const namesOf = (html) => [...String(html).matchAll(/<span class="audit-target-table"[^>]*>(.*?)<\/span><\/div>/g)].map(([, inner]) => {
  const pieces = [...inner.matchAll(/<span class="audit-tbl-piece">([^<]*)<\/span>/g)].map(([, text]) => text);
  return { ownerDocument: doc, closest: () => cell, get offsetWidth() { page.tape.push('read');
    return (box.whole ? pieces.join('').length : Math.max(0, ...pieces.map((p) => p.length))) * CHAR_PX; } };
});

function element(tag) {
  const node = {
    tagName: String(tag).toUpperCase(), ownerDocument: doc, dataset: {}, style: {}, _html: '', _classes: [],
    get className() { return this._classes.join(' '); },
    set className(v) { this._classes = String(v).split(/\s+/).filter(Boolean); },
    classList: { add: (...n) => { for (const x of n) if (!node._classes.includes(x)) node._classes.push(x); }, remove() {}, contains: () => false },
    set innerHTML(v) { this._html = String(v); }, get innerHTML() { return this._html; },
    set textContent(v) { this._html = String(v); }, get textContent() { return this._html; },
    get isConnected() { return list.children.includes(this); },
    querySelector() { return element('div'); },
    querySelectorAll(sel) { return sel === '.audit-tbl-piece' ? piecesOf(this._html) : sel === '.audit-target-table' ? namesOf(this._html) : []; },
    appendChild(c) { return c; }, append() {}, setAttribute() {}, getAttribute: () => null, addEventListener() {},
  };
  return node;
}
const list = {
  children: [],
  get firstChild() { return this.children[0] || null; },
  querySelector(sel) {
    const tx = /data-tx-id="([^"]*)"/.exec(sel);
    return tx ? this.children.find((c) => c.dataset.txId === tx[1]) || null : null;
  },
  insertBefore(n) { page.tape.push('write'); this.children.unshift(n); return n; },
  replaceChild(n, old) { page.tape.push('write'); this.children[this.children.indexOf(old)] = n; return old; },
  appendChild(n) { page.tape.push('write'); this.children.push(n); return n; },
};
const props = new Map();
const box = {
  ownerDocument: doc,
  style: { setProperty: (k, v) => { page.tape.push('write'); page.widthWrites += 1; props.set(k, v); }, getPropertyValue: (k) => props.get(k) || '' },
  getClientRects: () => (page.shown ? [{}] : []),
  querySelectorAll: (sel) => list.children.flatMap((c) => c.querySelectorAll(sel)),
  whole: false,
  classList: { add: (c) => { page.tape.push('write'); if (c === 'audit-tbl-whole') box.whole = true; },
    remove: (c) => { page.tape.push('write'); if (c === 'audit-tbl-whole') box.whole = false; } },
};
const CAP = '160px';
globalThis.getComputedStyle = () => { page.tape.push('read'); return { getPropertyValue: (k) => (k === '--audit-table-max' ? CAP : '') }; };
globalThis.document = { createElement: element, getElementById: (id) => ({ timeline: list, 'timeline-container': box })[id] || null,
  createDocumentFragment: () => element('#fragment'), addEventListener() {} };
globalThis.window = { addEventListener() {} };
globalThis.requestAnimationFrame = (fn) => { page.frames.push(fn); return page.frames.length; };
globalThis.ResizeObserver = class { constructor(fn) { page.resized = fn; } observe() {} };

const { state } = await import('../src/state.js');
const SRC_PATH = fileURLToPath(new URL('../src/timeline.js', import.meta.url));

/** A layout the page forces: a read straight after a write. */
const layouts = (tape) => tape.filter((t, i) => t === 'read' && tape[i - 1] === 'write').length;
const runFrames = () => { const asked = page.frames.splice(0); for (const fn of asked) fn(); return asked.length; };
const width = () => props.get('--audit-tbl-w') || '';
const log = (i, table) => ({ id: i, transaction_id: `tx${i}`, table_name: table, column_name: 'value', row_id: `row-${i}`,
  old_value: 'a', new_value: 'b', timestamp: '2026-11-06T09:00:00Z', updated_by: 'system' });
const WIDE = 'w'.repeat(30);
const message = () => Array.from({ length: 500 }, (_, i) => log(i, i === 137 ? `pfab_${WIDE}` : `lot_${'n'.repeat(i % 9 + 1)}`));

/** One page from scratch, the module given 500 logs of one message, then later rows, the panel hidden and shown. */
async function drive(T) {
  page.tape = []; page.frames = []; page.resized = null; page.shown = true;
  list.children = []; props.clear();
  state.activeHistoryTab = 'global';
  state.globalHistoryData = [];
  for (const l of message()) T.appendHistoryLocally(l, false);
  const r = { inReads: page.tape.filter((t) => t === 'read').length, asked: page.frames.length };
  r.frames = runFrames();
  r.layouts = layouts(page.tape);
  r.width = width();
  page.tape = []; page.widthWrites = 0;
  T.appendHistoryLocally(log(900, 'lot_short'), false);
  runFrames();
  r.narrowWrites = page.widthWrites;
  r.narrowReads = page.tape.filter((t) => t === 'read').length;
  r.afterNarrow = width();
  T.appendHistoryLocally(log(901, `pfab_${WIDE}xx`), false);
  runFrames();
  r.afterWide = width();
  page.shown = false;
  page.tape = [];
  T.appendHistoryLocally(log(902, `pfab_${WIDE}xxxx`), false);
  runFrames();
  r.hiddenReads = page.tape.filter((t) => t === 'read').length;
  r.afterHidden = width();
  page.shown = true;
  list.children = list.children.filter((c) => !/pfab_/.test(c.innerHTML));
  if (page.resized) page.resized();
  runFrames();
  r.afterShown = width();
  return r;
}

const X = await import('../src/timeline.js');
const base = await drive(X);
console.log('\n── A. ONE MESSAGE OF 500 LOGS ──────────────────────────────────────');
ok('A1 nothing measured while the logs land', base.inReads === 0, base.inReads);
ok('A2 one frame asked for the 500', base.asked === 1 && base.frames === 1, [base.asked, base.frames]);
ok('A3 two layouts for the message - the names held whole, then broken', base.layouts === 2, base.layouts);
ok('A4 the column as wide as the widest piece when a whole name is past the cap', base.width === `${need(WIDE)}px`, base.width);
console.log('\n── B. LATER ROWS · THE PANEL HIDDEN ─────────────────────────────────');
ok('B1 a narrower row keeps the width, nothing written to it', base.afterNarrow === base.width && base.narrowWrites === 0, [base.afterNarrow, base.narrowWrites]);
ok('B1b ...and only its own name read - the cap, the name whole and its two pieces (a size and a style each), not the whole panel',
  base.narrowReads === 7, base.narrowReads);
ok('B2 a wider row widens it', base.afterWide === `${need(`${WIDE}xx`)}px`, base.afterWide);
ok('B3 hidden: nothing read, the width kept', base.hiddenReads === 0 && base.afterHidden === base.afterWide, [base.hiddenReads, base.afterHidden]);
ok('B4 shown again: all measured, narrower now the wide rows are gone - the widest whole name under the cap',
  base.afterShown === `${need('lot_nnnnnnnnn')}px`, base.afterShown);

const once = (from, to) => (src) => {
  const n = src.split(from).length - 1;
  if (n !== 1) die(`mutation anchor matched ${n} times: ${JSON.stringify(from)}`);
  return src.replace(from, to);
};
const DEFECTS = [
  ['M1 measured at every row (as ccc862c55 drew it)', once('  if (!auditFitFrame) auditFitFrame = requestAnimationFrame(measureAuditTable);\n',
    '  measureAuditTable();\n')],
  ['M2 a frame asked for every row', once('if (!auditFitFrame) auditFitFrame = requestAnimationFrame', 'auditFitFrame = requestAnimationFrame')],
  ['M3 a row drawn narrows the column too', once('(all ? need !== held : need > held)', '(need !== held)')],
  ['M4 a hidden panel measured', once('  if (!box || !box.getClientRects().length) { auditFitAll = true; return; }\n', '  if (!box) return;\n')],
  ['M5 every row measures the whole panel', once('const roots = all ? [box] : rows;', 'const roots = [box];')],
  ['M6 the names not held whole for their reading', once("  box.classList.add('audit-tbl-whole'); // each name on one line for this reading\n", '')],
];
const CONTROLS = [
  ['a local rename', (src) => src.replace(/\bauditFitRows\b/g, 'rowsDrawn')],
];
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
let caught = 0;
let escaped = 0;
async function score(list_, mustCatch, heading) {
  console.log(`\n── ${heading} ─────────────────────────────`);
  let hit = 0;
  for (const [name, mutate] of list_) {
    let bad;
    try { bad = !same(await drive((await loadWithProbe(SRC_PATH, { mutate, tag: 'auditfit' })).module), base); }
    catch (e) { if (/did not mutate|unchanged/.test(String(e && e.message))) die(`${name}: ${e.message}`); bad = true; }
    if (bad === mustCatch) { hit++; console.log(`  ${mustCatch ? 'caught ' : 'escaped'} ${name}`); }
    else { failed++; console.log(`  ${mustCatch ? 'ESCAPED' : 'CAUGHT '} ${name}  <- wrong`); }
  }
  return hit;
}
if (failed) die('the scorer already fails on the UNMUTATED module');
caught = await score(DEFECTS, true, 'defect mutants (each must be CAUGHT)');
escaped = await score(CONTROLS, false, 'control mutants (each must ESCAPE)');
console.log(`\n${passed} passed, ${failed} failed; ${caught}/${DEFECTS.length} defects caught; ${escaped}/${CONTROLS.length} controls escaped.`);
console.log(`ASSERTIONS ${passed} ${failed}`);
if (failed) process.exit(1);
