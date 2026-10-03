// The main grid's world tabs (lead 120450931 ②, the order at DESIGN_ORDERS «세상 서브탭»).
//
// Scores: the tab row is drawn only over a table `/tables` calls per-world, with the worlds as the server
// names them and the operating one marked and shown; a pick reads the table again in that world, and every
// read after it - sort, page, count, row jump - carries it; another table's requests are today's, byte for
// byte, even with a world left picked; a table switch drops the pick. It imports its subjects (`api.js`,
// `state.js`, `timeline.js`, `world_tabs.js`); the page around them is a small fake DOM. The two read sites
// in `main.js` (it imports stylesheets and cannot load in node) and the one in `value_suggest.js` (private)
// are counted as text - the census, W9.
//
// CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src');

// ── a DOM enough for the grid's modules to import, and for a part to be drawn and clicked. `switchTable`
//    stops inside the grid's own drawing on it (logged, caught), after the tabs and the schema read - so the
//    page reads are asked through `fetchData` directly. ──
function fakeNode(tag) {
  const node = {
    tagName: String(tag).toUpperCase(), children: [], _text: '', style: {}, dataset: {}, attrs: {}, value: '',
    checked: false, _on: {}, _classes: [],
    get className() { return node._classes.join(' '); },
    set className(v) { node._classes = String(v).split(/\s+/).filter(Boolean); },
    classList: {
      add(...n) { for (const x of n) if (!node._classes.includes(x)) node._classes.push(x); },
      remove(...n) { node._classes = node._classes.filter((c) => !n.includes(c)); },
      contains: (n) => node._classes.includes(n),
      toggle(n, on) { const want = on === undefined ? !node._classes.includes(n) : !!on; if (want) node.classList.add(n); else node.classList.remove(n); return want; },
    },
    set textContent(v) { node._text = String(v); node.children = []; },
    get textContent() { return node._text + node.children.map((c) => c.textContent).join(''); },
    set innerHTML(v) { node._text = String(v); node.children = []; },
    get innerHTML() { return node._text; },
    appendChild(c) { node.children.push(c); return c; },
    append(...items) { for (const i of items) if (i) node.children.push(i); },
    setAttribute(k, v) { node.attrs[String(k)] = String(v); },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(node.attrs, String(k)) ? node.attrs[String(k)] : null; },
    removeAttribute(k) { delete node.attrs[String(k)]; },
    hasAttribute(k) { return Object.prototype.hasOwnProperty.call(node.attrs, String(k)); },
    addEventListener(type, fn) { (node._on[type] ||= []).push(fn); },
    removeEventListener() {}, focus() {}, blur() {}, remove() {}, insertAdjacentHTML() {},
    querySelector: () => null, querySelectorAll: () => [],
  };
  return node;
}
const byId = new Map();
globalThis.window = { currentTable: null, addEventListener() {}, removeEventListener() {},
  location: { port: '', origin: 'http://box', href: 'http://box/', hash: '', search: '' },
  matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }) };
globalThis.document = {
  hidden: false, activeElement: null, body: fakeNode('body'),
  getElementById: (id) => { if (!byId.has(id)) byId.set(id, fakeNode('div')); return byId.get(id); },
  createElement: (tag) => fakeNode(tag), querySelector: () => null, querySelectorAll: () => [],
  addEventListener() {}, removeEventListener() {},
};
const walk = (n, out = []) => { out.push(n); for (const c of n.children || []) walk(c, out); return out; };

// ── the wire: `/tables` as the server shapes it (6bfb6d4be), every other read answered empty ──
const TABLES = ['dt_log', 'ledger_atom_rows'];
const PER_WORLD = { tables: TABLES, groups: {}, kinds: {}, map_key_columns: {}, per_world: ['ledger_atom_rows'],
  worlds: ['default', 'w1'], operating: 'w1' };
let answer = PER_WORLD;
let urls = [];
globalThis.fetch = async (url) => {
  const u = String(url);
  urls.push(u);
  const path = u.split('?')[0];
  const body = path.endsWith('/tables') ? answer
    : path.endsWith('/schema') ? { columns: ['a'], column_types: {}, kind: 'view', business_key: '', composite_key_source: [],
      virtual_columns: [], join_resolved_columns: [] }
      // `defer_total=true` answers `total: null`, as the server does - the count is its own read.
      : path.endsWith('/count') ? { total: 0 } : { data: [], total: u.includes('defer_total=true') ? null : 0 };
  return { ok: true, status: 200, json: async () => body, text: async () => '' };
};
const settle = async () => { for (let i = 0; i < 20; i += 1) await new Promise((r) => setImmediate(r)); };
const gridApi = {
  getFocusedCell: () => null, getColumnState: () => [], getColumns: () => [], getDisplayedRowAtIndex: () => null,
  getRowNode: () => null, getSelectedNodes: () => [], getSelectedRows: () => [], applyTransaction() {},
  refreshCells() {}, setGridOption() {}, redrawRows() {}, forEachNode() {}, getDisplayedRowCount: () => 0,
  ensureIndexVisible() {}, getEditingCells: () => [], stopEditing() {}, getColumn: () => null, applyColumnState() {},
  setFilterModel() {}, getFilterModel: () => ({}), onFilterChanged() {}, refreshHeader() {}, getGridOption: () => undefined,
  setColumnDefs() {}, sizeColumnsToFit() {}, deselectAll() {}, paginationGetCurrentPage: () => 0,
};

const REAL = {
  api: await import('../src/api.js'),
  state: await import('../src/state.js'),
  timeline: await import('../src/timeline.js'),
  tabs: await import('../src/world_tabs.js'),
};
const S = REAL.state.state;

function reset() {
  Object.assign(S, { currentTable: '', gridWorld: null, tableList: null, pageCache: new Map(), isLoadingMore: false,
    currentSkip: 0, serverSort: null, gridApi, currentTransactionId: null });
  urls = [];
}
const reads = () => urls.filter((u) => !u.endsWith('/tables') && !u.includes('/audit_logs') && !u.includes('/api/'));
const tabsOf = (host) => walk(host).filter((n) => n._classes.includes('world-tabs__tab')).map((n) => ({
  name: n.dataset.world, active: n.getAttribute('aria-selected') === 'true',
  marked: walk(n).some((c) => c._classes.includes('world-tabs__mark')) }));

async function seen(M) {
  reset();
  const host = fakeNode('div');
  M.api.seatWorldTabs(new M.tabs.WorldTabs(host, { doc: document, onPick: (name) => M.api.pickGridWorld(name) }));
  const out = {};
  // The list loads and boot opens the first table, a plain one.
  answer = PER_WORLD;
  try { await M.api.loadTables(); } catch (e) { /* switchTable walks further than this page goes */ }
  await settle();
  out.plainTabs = tabsOf(host).length;
  urls = [];
  try { await M.api.fetchData(true); } catch (e) { /* as above */ }
  await settle();
  out.plainBefore = reads();
  // A world left picked on a plain table (a stale seat) must not reach its requests.
  S.gridWorld = 'w1';
  urls = [];
  try { await M.api.fetchData(true); } catch (e) { /* as above */ }
  await settle();
  out.plainStale = reads();
  S.gridWorld = null;
  // The per-world table: the tabs, and its first read naming no world.
  urls = [];
  try { await M.api.switchTable('ledger_atom_rows'); } catch (e) { /* as above */ }
  try { await M.api.fetchData(true); } catch (e) { /* as above */ }
  await settle();
  out.tabs = tabsOf(host);
  out.opened = reads();
  // A pick: the default, by its name.
  urls = [];
  const tab = walk(host).find((n) => n.dataset && n.dataset.world === 'default');
  for (const fn of (tab && tab._on.click) || []) await fn({ target: tab });
  await settle();
  out.picked = { world: S.gridWorld, reads: reads(), tabs: tabsOf(host) };
  // Every read after it: a sort, a page, the count, a row jump.
  urls = [];
  S.serverSort = { colId: 'a', sort: 'asc' };
  try { await M.api.fetchData(true); } catch (e) { /* as above */ }
  S.currentSkip = 100;
  try { await M.api.fetchData(false); } catch (e) { /* as above */ }
  try { await M.timeline.navigatorStep3({ row_id: 'R1' }); } catch (e) { /* the jump walks further than this page */ }
  await settle();
  out.after = reads();
  // Back to the plain table: the pick dies, the tabs go, the requests are the first ones again.
  urls = [];
  S.serverSort = null;
  S.currentSkip = 0;
  try { await M.api.switchTable('dt_log'); } catch (e) { /* as above */ }
  out.backTabs = tabsOf(host).length;
  out.backWorld = S.gridWorld;
  urls = [];
  try { await M.api.fetchData(true); } catch (e) { /* as above */ }
  await settle();
  out.back = reads();
  // An answer from a server before the worlds: no tab anywhere.
  reset();
  answer = { tables: TABLES, groups: {}, kinds: {}, map_key_columns: {} };
  try { await M.api.loadTables(); } catch (e) { /* as above */ }
  try { await M.api.switchTable('ledger_atom_rows'); } catch (e) { /* as above */ }
  out.oldTabs = tabsOf(host).length;
  answer = PER_WORLD;
  return out;
}

// The seat itself, on the state module under test (a state.js copy carries its own state object).
async function seat(stateModule) {
  const sent = [];
  const keep = globalThis.fetch;
  globalThis.fetch = async (url) => { sent.push(String(url)); return { ok: true, json: async () => ({}) }; };
  try {
    const st = stateModule.state;
    st.tableList = { perWorld: ['ledger_atom_rows'] };
    st.gridWorld = 'w1';
    st.currentTable = 'dt_log';
    await stateModule.gridFetch('/tables/dt_log/data?skip=0');
    st.currentTable = 'ledger_atom_rows';
    await stateModule.gridFetch('/tables/ledger_atom_rows/data?skip=0');
    st.gridWorld = null;
    await stateModule.gridFetch('/tables/ledger_atom_rows/data?skip=0');
    st.tableList = null;
    st.gridWorld = null;
    st.currentTable = '';
  } finally {
    globalThis.fetch = keep;
  }
  return sent;
}

const callsIn = (file) => (readFileSync(join(SRC, file), 'utf8').match(/\bgridFetch\(/g) || []).length;

function suite(out, sent) {
  const names = [];
  const failures = [];
  const eq = (name, got, want) => {
    names.push(name);
    const g = JSON.stringify(got), w = JSON.stringify(want);
    if (g === w) { console.log(`  PASS ${name}`); return; }
    failures.push(name);
    console.log(`  FAIL ${name}\n        got  ${g}\n        want ${w}`);
  };
  const carry = (list, world) => list.length > 0 && list.every((u) => u.includes(`world=${world}`));
  eq('W0 the seat: a plain table never carries the picked world; a per-world one carries it when one is picked',
    sent, ['/tables/dt_log/data?skip=0', '/tables/ledger_atom_rows/data?skip=0&world=w1', '/tables/ledger_atom_rows/data?skip=0']);
  eq('W1 a plain table draws no tab row', out.plainTabs, 0);
  eq('W2 a world left picked does not reach a plain table: its reads are today\'s, byte for byte',
    [out.plainStale.length > 0, out.plainStale], [true, out.plainBefore]);
  eq('W3 a per-world table: the worlds as the server names them, the operating one marked and shown',
    out.tabs, [{ name: 'default', active: false, marked: false }, { name: 'w1', active: true, marked: true }]);
  eq('W4 ...and its first reads name no world (the operating one)',
    [out.opened.length > 0, out.opened.filter((u) => u.includes('world=')).length], [true, 0]);
  eq('W5 a pick reads the table again in that world, and shows it',
    [out.picked.world, carry(out.picked.reads, 'default'), out.picked.tabs.map((t) => t.active)],
    ['default', true, [true, false]]);
  eq('W6 every read after the pick carries it: sort, page, count, row jump',
    [carry(out.after, 'default'), out.after.some((u) => u.includes('/data/count')),
      out.after.some((u) => u.includes('target_row_id=R1')), out.after.some((u) => u.includes('skip=100'))],
    [true, true, true, true]);
  eq('W7 a switch drops the pick and the tabs; the plain table asks what it asked before',
    [out.backWorld, out.backTabs, out.back], [null, 0, out.plainBefore]);
  eq('W8 a server that names no per-world table: no tab row', out.oldTabs, 0);
  eq('W9 census: the grid\'s reads of the open table go through the seat - api 3 (schema, data, count), main 3 '
    + '(load all twice, export), timeline 1 (row jump), value_suggest 1 (column values)',
    { api: callsIn('api.js'), main: callsIn('main.js'), timeline: callsIn('timeline.js'), suggest: callsIn('value_suggest.js') },
    { api: 3, main: 3, timeline: 1, suggest: 1 });
  return { ran: names.length, names, failures };
}

console.log('\n[1] the world tabs over the grid');
const base = suite(await seen(REAL), await seat(REAL.state));
let ran = base.ran;
let failed = base.failures.length;

const swap = (text, from, to) => {
  if (!text.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`);
  return text.split(from).join(to);
};
const MUTANTS = [
  { id: 'G1', what: 'the seat sends the picked world on any table', catches: 'W0', file: 'state.js',
    mutate: (t) => swap(t, '  () => (tableIsPerWorld() ? state.gridWorld : null));', '  () => state.gridWorld);') },
  { id: 'G2', what: 'a switch keeps the picked world', catches: 'W7', file: 'api.js',
    mutate: (t) => swap(t, '  state.gridWorld = null;\n  drawWorldTabs();\n', '  drawWorldTabs();\n') },
  { id: 'G3', what: 'a switch does not redraw the tabs', catches: 'W3', file: 'api.js',
    mutate: (t) => swap(t, '  state.gridWorld = null;\n  drawWorldTabs();\n', '  state.gridWorld = null;\n') },
  { id: 'G4', what: 'a pick does not read again', catches: 'W5', file: 'api.js',
    mutate: (t) => swap(t, '  drawWorldTabs();\n  await fetchData(true);\n}', '  drawWorldTabs();\n}') },
  { id: 'G5', what: 'the page read goes round the seat', catches: 'W6', file: 'api.js',
    mutate: (t) => swap(t, '    const res = await gridFetch(url);\n    // ', '    const res = await fetch(url);\n    // ') },
  { id: 'G6', what: 'the list load drops per_world', catches: 'W3', file: 'api.js',
    mutate: (t) => swap(t, 'perWorld: data.per_world,', 'perWorld: undefined,') },
  { id: 'G7', what: 'the row jump goes round the seat', catches: 'W6', file: 'timeline.js',
    mutate: (t) => swap(t, '    const res = await gridFetch(url);\n    const result = await res.json();',
      '    const res = await fetch(url);\n    const result = await res.json();') },
  { id: 'G8', what: 'the operating world is not marked', catches: 'W3', file: 'world_tabs.js',
    mutate: (t) => swap(t, '      if (name === view.operating) {', '      if (false) {') },
  { id: 'G9', what: 'no tab is shown while none is picked', catches: 'W3', file: 'world_tabs.js',
    mutate: (t) => swap(t, 'const shown = view.current || view.operating;', 'const shown = view.current;') },
];
const KEY = { 'state.js': 'state', 'api.js': 'api', 'timeline.js': 'timeline', 'world_tabs.js': 'tabs' };
const scored = await scoreMutants(MUTANTS, async (m) => {
  const copy = (await loadWithProbe(join(SRC, m.file), { mutate: m.mutate })).module;
  if (m.file === 'state.js') return suite(await seen(REAL), await seat(copy));
  return suite(await seen({ ...REAL, [KEY[m.file]]: copy }), await seat(REAL.state));
}, { baselineRan: base.ran, baselineNames: base.names, title: '\n  [1] mutants - each must be caught by the check it names.' });
ran += MUTANTS.length;
failed += scored.wrong;

console.log(`\n${ran - failed} passed, ${failed} failed`);
console.log(`ASSERTIONS ${ran} ${failed}`);
if (failed) process.exit(1);
