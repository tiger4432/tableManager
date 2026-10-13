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
    replaceChildren(...items) { node._text = ''; node.children = [...items]; },
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
  ws: await import('../src/websocket.js'),
  grid: await import('../src/grid.js'),
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
  out.left = await leftovers(M);
  return out;
}

// What a table switch leaves behind, and Discard (lead 10-12): the last table's filter, the label and the banner told
// only by the dropdown and boot, a discarded cell drawn from the value before the edit.
async function leftovers(M) {
  reset();
  const left = {};
  const filterOn = () => ({ row_id: { filterType: 'text', type: 'equals', filter: 'R1' } });
  let model = filterOn();
  const cleared = [];
  S.gridApi = { ...gridApi, getFilterModel: () => model,
    setFilterModel: (m) => { cleared.push(m); model = m || {}; setTimeout(() => { try { M.grid.gridFilterChanged(); } catch (e) { /* the chips */ } }, 5); } };
  const followed = [];
  M.api.seatTableFollower((table) => followed.push(table));
  S.currentTable = 'dt_log';
  try { await M.api.switchTable('ledger_atom_rows'); } catch (e) { /* as above */ }
  left.other = { cleared: cleared.slice(), model: Object.keys(model) };
  model = filterOn();
  cleared.length = 0;
  try { await M.api.switchTable('ledger_atom_rows'); } catch (e) { /* as above */ }
  left.same = { cleared: cleared.slice(), model: Object.keys(model) };
  // The drop on its own: it takes the grid's filterChanged (sent after a timer) and reads nothing; the next change reads.
  reset();
  let held = filterOn();
  S.gridApi = { ...gridApi, getFilterModel: () => held,
    setFilterModel: (m) => { held = m || {}; setTimeout(() => { try { M.grid.gridFilterChanged(); } catch (e) { /* the chips */ } }, 5); } };
  S.currentTable = 'dt_log';
  urls = [];
  try { await M.grid.dropGridFilters(); } catch (e) { /* as above */ }
  await new Promise((r) => setTimeout(r, 30));
  await settle();
  left.drop = { reads: reads().filter((u) => u.includes('/data?')).length, model: Object.keys(held) };
  urls = [];
  try { M.grid.gridFilterChanged(); } catch (e) { /* the chips */ }
  await settle();
  left.dropAfter = reads().filter((u) => u.includes('/data?')).length;
  S.gridApi = { ...gridApi, getFilterModel: () => model,
    setFilterModel: (m) => { cleared.push(m); model = m || {}; setTimeout(() => { try { M.grid.gridFilterChanged(); } catch (e) { /* the chips */ } }, 5); } };
  // Boot opens the first table; a history jump calls switchTable itself.
  followed.length = 0;
  S.currentTable = '';
  try { await M.api.loadTables(); } catch (e) { /* as above */ }
  try { await M.api.switchTable('ledger_atom_rows'); } catch (e) { /* as above */ }
  left.followed = followed.slice();
  M.api.seatTableFollower(null);
  // A stored 28.5 the grid holds since a Refresh; the edit was staged over the 28 from before it.
  const node = { data: { row_id: 'R1', data: { a: { value: 28.5, is_overwrite: true, priority_source: 'user' } } } };
  reset();
  S.gridApi = { ...gridApi, getRowNode: (id) => (id === 'R1' ? node : null) };
  S.currentTable = 'dt_log';
  S.pendingTxEdits = { R1_a: { rowId: 'R1', colId: 'a', newValue: 28.7, oldValue: 28, oldIsOverwrite: false,
    oldPrioritySource: null, data: node.data } };
  let atOnce = null;
  try {
    const going = M.api.discardPendingEdits();
    const cell = node.data.data.a;
    atOnce = { value: cell.value, is_overwrite: cell.is_overwrite, priority_source: cell.priority_source };
    await going;
  } catch (e) { /* as above */ }
  await settle();
  left.discard = { pending: Object.keys(S.pendingTxEdits).length,
    reads: reads().filter((u) => u.includes('/tables/dt_log/data?')).length };
  left.atOnce = atOnce;
  left.conflict = await conflicts(M);
  left.cacheTrip = await cacheTrip(M);
  left.addedRows = await addedRows(M);
  S.gridApi = gridApi;
  return left;
}

// A staged edit the server changed under it (lead 10-12, 18766: 28.9 staged, 29.7 saved by another, a broadcast drew
// 29.7 and Apply sent 28.9 over it unasked).
async function conflicts(M) {
  const out = {};
  const stage = () => {
    S.pendingTxEdits = { R1_a: { rowId: 'R1', colId: 'a', newValue: 28.9, oldValue: 28.5, oldIsOverwrite: false,
      oldPrioritySource: null, data: null } };
  };
  const serverRow = () => ({ row_id: 'R1', updated_at: '2026-10-12 12:00:00', data: { a: { value: 29.7 } } });
  let drawn = null;
  let updated = null;
  const node = { data: { row_id: 'R1', data: { a: { value: 28.9 } } } };
  // A read: the page comes back with the server's 29.7.
  reset();
  S.gridApi = { ...gridApi, getRowNode: (id) => (id === 'R1' ? node : null), flashCells() {},
    setGridOption: (key, value) => { if (key === 'rowData') drawn = value; },
    applyTransaction: (tx) => { updated = tx.update || null; return { update: tx.update || [], add: tx.add || [] }; } };
  S.currentTable = 'dt_log';
  stage();
  const keep = globalThis.fetch;
  globalThis.fetch = async (url) => ({ ok: true, status: 200, text: async () => '',
    json: async () => (String(url).includes('/data/count') ? { total: 1 } : { data: [serverRow()], total: null }) });
  try { await M.api.fetchData(true); } catch (e) { /* as above */ }
  await settle();
  const cellOf = (rows) => (rows && rows[0] && rows[0].data && rows[0].data.a ? rows[0].data.a.value : null);
  out.read = { drawn: cellOf(drawn), conflict: S.pendingTxEdits.R1_a && S.pendingTxEdits.R1_a.conflict };
  // The server still at the value the edit was made over: no conflict - the staged cell drawn all the same.
  globalThis.fetch = async (url) => ({ ok: true, status: 200, text: async () => '',
    json: async () => (String(url).includes('/data/count') ? { total: 1 }
      : { data: [{ ...serverRow(), data: { a: { value: 28.5 } } }], total: null }) });
  try { await M.api.fetchData(true); } catch (e) { /* as above */ }
  await settle();
  out.unmoved = { drawn: cellOf(drawn), conflict: S.pendingTxEdits.R1_a && S.pendingTxEdits.R1_a.conflict };
  // A broadcast with the same row.
  stage();
  try { M.ws.handleWebSocketMessage({ event: 'batch_row_upsert', table_name: 'dt_log', items: [serverRow()] }); } catch (e) { /* as above */ }
  out.broadcast = { drawn: cellOf(updated), conflict: S.pendingTxEdits.R1_a && S.pendingTxEdits.R1_a.conflict };
  // Apply: asked, then each answer. Apply reads the staged rows again first - the stub answers that read from `server`.
  const sent = [];
  const reread = [];
  let server = { R1: 29.7, R2: 4 };
  // A stub server for Apply: reads answer from `server`; PUTs are kept in `into` and answer as `put` says - nothing:
  // saved; a function: awaited first; a number: that status.
  const answering = (into, put) => async (url, init) => {
    if (init && init.method === 'PUT') {
      const body = JSON.parse(init.body);
      into.push(body.updates);
      if (typeof put === 'function') await put();
      if (typeof put === 'number') return { ok: false, status: put, text: async () => 'boom', json: async () => ({ detail: 'boom' }) };
      return { ok: true, status: 200, text: async () => '', json: async () => ({ change_count: 1 }) };
    }
    const filters = new URL(String(url), 'http://box').searchParams.get('filters');
    const ids = filters ? JSON.parse(filters).row_id.conditions.map((c) => c.filter) : [];
    reread.push(ids);
    const data = ids.filter((id) => id in server).map((id) => ({ row_id: id, updated_at: null, data: { a: { value: server[id] } } }));
    return { ok: true, status: 200, text: async () => '', json: async () => ({ data, total: null }) };
  };
  // An Apply that should end does, within half a second; false when it hangs.
  const finishes = (going) => Promise.race([going.then(() => true, () => true), new Promise((r) => setTimeout(() => r(false), 500))]);
  // The one time cap (15 s) cut at once, for the scenarios that ask what happens past it.
  const atOnce = async (run) => {
    const real = globalThis.setTimeout;
    globalThis.setTimeout = (fn, ms, ...rest) => real(fn, ms === 15000 ? 1 : ms, ...rest);
    try { return await run(); } finally { globalThis.setTimeout = real; }
  };
  globalThis.fetch = answering(sent);
  const line = document.getElementById('tx-conflict-line');
  const text = document.getElementById('tx-conflict-text');
  stage();
  try { await M.api.applyPendingEdits(); } catch (e) { /* as above */ }
  out.asked = { sent: sent.length, line: line.style.display, text: text.textContent, pending: Object.keys(S.pendingTxEdits).length };
  try { await M.api.applyPendingEdits('mine'); } catch (e) { /* as above */ }
  const asSent = (list) => list.map((updates) => updates.map(({ row_id, updates: u }) => ({ row_id, updates: u })));
  out.mine = { sent: asSent(sent), pending: Object.keys(S.pendingTxEdits).length, line: line.style.display };
  sent.length = 0;
  stage();
  S.pendingTxEdits.R2_a = { rowId: 'R2', colId: 'a', newValue: 5, oldValue: 4, data: null };
  node.data.data.a.value = 28.9;
  try { await M.api.applyPendingEdits(); } catch (e) { /* as above */ }
  try { await M.api.applyPendingEdits('server'); } catch (e) { /* as above */ }
  out.server = { sent: asSent(sent), cell: node.data.data.a.value, pending: Object.keys(S.pendingTxEdits).length };
  // A change no redraw brought (lead QA 10-12 5): nothing on the edit says so; Apply's own read finds it and asks.
  // The cached page still holds the value from before: the read puts the server's there too.
  sent.length = 0; reread.length = 0;
  stage();
  S.pageCache = new Map([[0, { data: [{ row_id: 'R1', data: { a: { value: 28.5 } } }], total: 1 }]]);
  try { await M.api.applyPendingEdits(); } catch (e) { /* as above */ }
  out.unseen = { sent: sent.length, reread: reread.slice(), conflict: S.pendingTxEdits.R1_a && S.pendingTxEdits.R1_a.conflict,
    cached: S.pageCache.has(0) ? S.pageCache.get(0).data[0].data.a.value : 'cache cleared' };
  S.pageCache = new Map();
  // Tx turned off while a cell is conflicted: Apply asks, so Tx comes back on (lead QA 10-12 3).
  const toggle = document.getElementById('tx-mode-toggle');
  stage();
  toggle.checked = false; S.txModeActive = false;
  try { await M.api.applyPendingEdits(); } catch (e) { /* as above */ }
  out.txBack = { checked: toggle.checked, active: S.txModeActive, sent: sent.length };
  // Two Keep mine clicks before the first PUT answers: one PUT (lead QA 10-12 4).
  // ...with nothing conflicted, so the second click has only the guard to stop it.
  sent.length = 0;
  server = { R1: 28.5, R2: 4 };
  stage();
  const log = document.getElementById('performance-log');
  const first = M.api.applyPendingEdits();
  const checking = log.textContent;
  const second = M.api.applyPendingEdits();
  const already = log.textContent;
  try { await Promise.all([first, second]); } catch (e) { /* as above */ }
  out.twice = sent.length;
  // ...and a read that never answers is cut at the cap: the request itself aborted, Apply stopped and saying so.
  let aborted = false;
  globalThis.fetch = (url, init) => new Promise((_, reject) => {
    if (init && init.signal) init.signal.addEventListener('abort', () => { aborted = true; reject(new Error('aborted')); });
  });
  stage();
  const cut = await atOnce(() => finishes(M.api.applyPendingEdits()));
  out.saying = [checking, already, { cut, aborted, said: log.textContent }];
  globalThis.fetch = answering(sent);
  server = { R1: 29.7, R2: 4 };
  // The question's count follows the conflicts, and it goes when they do (lead QA 10-12 6).
  S.pendingTxEdits = {
    R1_a: { rowId: 'R1', colId: 'a', newValue: 28.9, oldValue: 28.5, data: null },
    R2_a: { rowId: 'R2', colId: 'a', newValue: 5, oldValue: 3, data: null } };
  try { await M.api.applyPendingEdits(); } catch (e) { /* as above */ }
  const said = [text.textContent];
  M.api.overlayStagedEdits([{ row_id: 'R2', data: { a: { value: 3 } } }]);
  said.push(text.textContent, line.style.display);
  M.api.overlayStagedEdits([{ row_id: 'R1', data: { a: { value: 28.5 } } }]);
  said.push(line.style.display);
  out.follows = said;
  // A number spelled as text - a paste or a fill keeps the stored "29.50" - is the same as 29.5 (lead QA 10-12 7).
  S.currentColumnTypes = { a: 'number' };
  S.pendingTxEdits = { R1_a: { rowId: 'R1', colId: 'a', newValue: 30, oldValue: '29.50', data: null } };
  M.api.overlayStagedEdits([{ row_id: 'R1', data: { a: { value: 29.5 } } }]);
  out.spelled = S.pendingTxEdits.R1_a.conflict;
  // A text column: "1.10" and "1.1" are two values (lead re-QA F2).
  S.currentColumnTypes = { a: 'string' };
  S.pendingTxEdits = { R1_a: { rowId: 'R1', colId: 'a', newValue: 'x', oldValue: '1.10', data: null } };
  M.api.overlayStagedEdits([{ row_id: 'R1', updated_at: null, data: { a: { value: '1.1' } } }]);
  out.textSpelled = S.pendingTxEdits.R1_a.conflict;
  S.currentColumnTypes = {};
  // A row deleted: its staged edit goes and the bottom line says so - by a broadcast, and by Apply's read (9).
  stage();
  try { M.ws.handleWebSocketMessage({ event: 'batch_row_delete', table_name: 'dt_log', row_ids: ['R1'] }); } catch (e) { /* as above */ }
  out.deleted = { pending: Object.keys(S.pendingTxEdits).length, said: log.textContent.endsWith(' 1 row removed · 1 staged edit dropped (row deleted)') };
  sent.length = 0;
  server = { R2: 4 };
  stage();
  try { await M.api.applyPendingEdits(); } catch (e) { /* as above */ }
  out.goneOnRead = { pending: Object.keys(S.pendingTxEdits).length, sent: sent.length, said: log.textContent === 'Nothing applied · 1 staged edit dropped (row deleted)' };
  // An answer holds for what was asked (lead re-QA F1): another cell conflicts after the question - asked again; then sent.
  sent.length = 0;
  server = { R1: 29.7, R2: 4 };
  stage();
  S.pendingTxEdits.R2_a = { rowId: 'R2', colId: 'a', newValue: 20, oldValue: 4, data: null };
  try { await M.api.applyPendingEdits(); } catch (e) { /* as above */ }
  server = { R1: 29.7, R2: 7 };
  try { await M.api.applyPendingEdits('mine'); } catch (e) { /* as above */ }
  const reask = { sent: sent.length, text: text.textContent };
  try { await M.api.applyPendingEdits('mine'); } catch (e) { /* as above */ }
  const then = asSent(sent);
  // ...and a value that moved after the question is asked again too.
  sent.length = 0;
  server = { R1: 29.7, R2: 4 };
  stage();
  try { await M.api.applyPendingEdits(); } catch (e) { /* as above */ }
  server = { R1: 30.1, R2: 4 };
  try { await M.api.applyPendingEdits('server'); } catch (e) { /* as above */ }
  out.bound = { reask, then, moved: { sent: sent.length, text: text.textContent } };
  // An edit made while the PUT is out stays staged (lead re-QA F3): only what was sent is saved.
  let release = null;
  const putSent = [];
  server = { R1: 28.5, R2: 4 };
  globalThis.fetch = answering(putSent, () => new Promise((r) => { release = r; }));
  stage();
  const going = M.api.applyPendingEdits();
  for (let i = 0; i < 50 && !release; i += 1) await new Promise((r) => setImmediate(r));
  S.pendingTxEdits.R1_a.newValue = 29.1;
  S.pendingTxEdits.R2_a = { rowId: 'R2', colId: 'a', newValue: 20, oldValue: 4, data: null };
  if (release) release();
  try { await going; } catch (e) { /* as above */ }
  await new Promise((r) => setTimeout(r, 5));   // ...and still so a timer later
  out.putWindow = { sent: asSent(putSent), pending: Object.keys(S.pendingTxEdits).sort(), r1Over: S.pendingTxEdits.R1_a && S.pendingTxEdits.R1_a.oldValue };
  // Tx off, and the read again fails: Tx comes back on, the edit still staged (lead re-QA F4).
  globalThis.fetch = async () => ({ ok: false, status: 500, text: async () => 'boom', json: async () => ({ detail: 'boom' }) });
  stage();
  toggle.checked = false; S.txModeActive = false;
  try { await M.api.applyPendingEdits(); } catch (e) { /* as above */ }
  out.failedRead = { checked: toggle.checked, active: S.txModeActive, pending: Object.keys(S.pendingTxEdits).length };
  // An editor open at Apply (lead 10-13): the grid hands a changed value to handleCellEdit after a timeout, as AG Grid
  // fires cellValueChanged - so it goes with this Apply only if Apply closes the editor and waits for that.
  const editorSent = [];
  server = { R1: 28.5, R2: 4 };
  globalThis.fetch = answering(editorSent);
  const editorRow = { row_id: 'R1', data: { a: { value: 28.5 } } };
  const grid = S.gridApi;
  const openEditor = (typed) => {
    let open = true;
    S.gridApi = { ...grid, getEditingCells: () => (open ? [{ rowIndex: 0, column: { getColId: () => 'a' } }] : []),
      getDisplayedRowAtIndex: () => ({ data: editorRow }), getCellValue: () => editorRow.data.a.value,
      stopEditing() {
        if (!open) return;
        open = false;
        const old = editorRow.data.a.value;
        if (typed === old) return;
        editorRow.data.a.value = typed;
        setTimeout(() => M.api.handleCellEdit({ data: editorRow, colDef: { field: 'a' }, newValue: typed, oldValue: old }), 0);
      } };
  };
  S.pendingTxEdits = { R2_a: { rowId: 'R2', colId: 'a', newValue: 20, oldValue: 4, data: null } };
  openEditor(29.1);
  const changedDone = await finishes(M.api.applyPendingEdits());
  out.editorOpen = { finished: changedDone, sent: asSent(editorSent), pending: Object.keys(S.pendingTxEdits) };
  editorSent.length = 0;
  S.pendingTxEdits = { R2_a: { rowId: 'R2', colId: 'a', newValue: 21, oldValue: 4, data: null } };
  openEditor(editorRow.data.a.value);
  const sameDone = await finishes(M.api.applyPendingEdits());
  out.editorSame = { finished: sameDone, sent: asSent(editorSent) };
  // The lead's check of c3a3fd5cb (10-13), each through handleCellEdit as the grid makes an edit.
  const rowsById = { R1: { row_id: 'R1', data: { a: { value: 28.5 } } }, R2: { row_id: 'R2', data: { a: { value: 4 } } } };
  const fresh = () => {
    rowsById.R1.data.a.value = 28.5; rowsById.R2.data.a.value = 4;
    S.pendingTxEdits = {}; toggle.checked = true; S.txModeActive = true; S.currentColumnTypes = { a: 'number' };
  };
  const edit = (id, from, to) => M.api.handleCellEdit({ data: rowsById[id], colDef: { field: 'a' }, newValue: to, oldValue: from });
  S.gridApi = { ...grid, getRowNode: (id) => (rowsById[id] ? { data: rowsById[id] } : null) };
  const keepAlert = globalThis.alert;
  const keepConfirm = globalThis.confirm;
  globalThis.alert = () => {};
  globalThis.confirm = () => true;
  // 1: Take server on a cell whose server value went back to the value it was edited over - no conflict now, and not
  //    sent; two asked and one went back - both go.
  const backSent = [];
  globalThis.fetch = answering(backSent);
  fresh();
  await edit('R1', 28.5, 28.9);
  server = { R1: 29.7, R2: 4 };
  try { await M.api.applyPendingEdits(); } catch (e) { /* as above */ }
  server = { R1: 28.5, R2: 4 };
  try { await M.api.applyPendingEdits('server'); } catch (e) { /* as above */ }
  const one = { sent: asSent(backSent), pending: Object.keys(S.pendingTxEdits), drawn: rowsById.R1.data.a.value };
  backSent.length = 0;
  fresh();
  await edit('R1', 28.5, 28.9);
  await edit('R2', 4, 5);
  server = { R1: 29.7, R2: 6 };
  try { await M.api.applyPendingEdits(); } catch (e) { /* as above */ }
  server = { R1: 29.7, R2: 4 };
  try { await M.api.applyPendingEdits('server'); } catch (e) { /* as above */ }
  out.wentBack = { one, two: { sent: asSent(backSent), pending: Object.keys(S.pendingTxEdits), drawn: [rowsById.R1.data.a.value, rowsById.R2.data.a.value] } };
  // 2: Tx turned off to apply, and the cell edited again while that PUT is out - staged, not sent straight, not painted
  //    over by the batch's answer; Tx back on for it.
  // Every PUT is held until released - one sent straight (the code before) is held too, so nothing waits on another.
  const holds = [];
  const offSent = [];
  globalThis.fetch = answering(offSent, () => new Promise((r) => holds.push(r)));
  fresh();
  server = { R1: 28.5, R2: 4 };
  await edit('R1', 28.5, 28.9);
  toggle.checked = false;
  M.api.txToggled();
  for (let i = 0; i < 50 && !holds.length; i += 1) await new Promise((r) => setImmediate(r));
  edit('R1', 28.9, 29.1);
  for (let k = 0; k < 3; k += 1) { holds.splice(0).forEach((r) => r()); await settle(); }
  out.offApply = { sent: asSent(offSent), pending: Object.values(S.pendingTxEdits).map((e) => [e.rowId, e.newValue]),
    drawn: rowsById.R1.data.a.value, tx: [toggle.checked, S.txModeActive] };
  // 3: Tx turned off to apply, and the PUT refused - the edit still staged, Tx back on.
  globalThis.fetch = answering([], 500);
  fresh();
  await edit('R1', 28.5, 28.9);
  toggle.checked = false;
  M.api.txToggled();
  await settle();
  out.putRefused = { pending: Object.keys(S.pendingTxEdits), tx: [toggle.checked, S.txModeActive] };
  // 5: a PUT that never answers is cut at the cap - Apply ends, the edit still staged, Tx on.
  globalThis.fetch = answering([], () => new Promise(() => {}));
  fresh();
  await edit('R1', 28.5, 28.9);
  const putCut = await atOnce(() => finishes(M.api.applyPendingEdits()));
  out.putCut = { finished: putCut, pending: Object.keys(S.pendingTxEdits), tx: [toggle.checked, S.txModeActive] };
  globalThis.alert = keepAlert;
  globalThis.confirm = keepConfirm;
  S.currentColumnTypes = {};
  S.gridApi = grid;
  globalThis.fetch = keep;
  S.pendingTxEdits = {};
  return out;
}

// The page cache and the grid never share a row (lead QA 10-12 1): an edit made through handleCellEdit, a trip to
// another page and back - no conflict with itself; and a row with nothing staged edited on the page the cache gave back.
async function cacheTrip(M) {
  const out = {};
  const pages = { 0: [{ row_id: 'R1', data: { a: { value: 28.5 } } }, { row_id: 'R2', data: { a: { value: 4 } } }],
    100: [{ row_id: 'R3', data: { a: { value: 1 } } }] };
  let drawn = [];
  reset();
  S.viewMode = 'pagination';
  S.gridApi = { ...gridApi, setGridOption: (key, value) => { if (key === 'rowData') drawn = value; },
    getRowNode: (id) => { const row = drawn.find((r) => r.row_id === id); return row ? { data: row } : null; } };
  S.currentTable = 'dt_log';
  S.pendingTxEdits = {};
  S.txModeActive = true;
  const keep = globalThis.fetch;
  globalThis.fetch = async (url) => {
    const skip = Number(new URL(String(url), 'http://box').searchParams.get('skip') || 0);
    const data = JSON.parse(JSON.stringify(pages[skip] || []));
    return { ok: true, status: 200, text: async () => '', json: async () => (String(url).includes('/data/count') ? { total: 3 } : { data, total: null }) };
  };
  const go = async (skip, reset_) => { S.currentSkip = skip; try { await M.api.fetchData(reset_); } catch (e) { /* as above */ } await settle(); };
  const editCell = async (rowId, newValue) => {
    const row = drawn.find((r) => r.row_id === rowId);
    try { await M.api.handleCellEdit({ data: row, colDef: { field: 'a' }, newValue, oldValue: row.data.a.value }); } catch (e) { /* as above */ }
  };
  await go(0, true);
  await editCell('R1', 28.9);
  await go(100, false);
  await go(0, false);
  const r1 = drawn.find((r) => r.row_id === 'R1');
  out.staged = { drawn: r1 && r1.data.a.value, conflict: S.pendingTxEdits.R1_a && S.pendingTxEdits.R1_a.conflict };
  await editCell('R2', 5);
  await go(100, false);
  await go(0, false);
  out.again = S.pendingTxEdits.R2_a && S.pendingTxEdits.R2_a.conflict;
  globalThis.fetch = keep;
  S.pendingTxEdits = {};
  S.txModeActive = false;
  S.gridApi = gridApi;
  return out;
}

// A broadcast of a staged row the grid does not hold (it is on another page): added at the staged value, with its
// conflict - both ways a broadcast adds rows (lead QA 10-12 2).
async function addedRows(M) {
  const out = {};
  let added = null;
  reset();
  S.gridApi = { ...gridApi, getRowNode: () => null, flashCells() {},
    applyTransaction: (tx) => { added = tx.add || null; return { update: tx.update || [], add: tx.add || [] }; } };
  S.currentTable = 'dt_log';
  const stage = () => { S.pendingTxEdits = { R1_a: { rowId: 'R1', colId: 'a', newValue: 28.9, oldValue: 28.5, data: null } }; };
  const item = () => ({ row_id: 'R1', updated_at: '2026-10-12 12:00:00', data: { a: { value: 29.7 } } });
  const look = () => ({ drawn: added && added[0] ? added[0].data.a.value : null, conflict: S.pendingTxEdits.R1_a.conflict });
  stage();
  try { M.ws.handleWebSocketMessage({ event: 'batch_row_upsert', table_name: 'dt_log', items: [item()] }); } catch (e) { /* as above */ }
  out.upsert = look();
  stage(); added = null;
  try { M.ws.handleWebSocketMessage({ event: 'batch_row_create', table_name: 'dt_log', items: [item()] }); } catch (e) { /* as above */ }
  out.create = look();
  S.pendingTxEdits = {};
  S.gridApi = gridApi;
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
  eq('W10 a switch to another table drops the grid\'s filters; the same table switched again keeps them',
    [out.left.other, out.left.same], [{ cleared: [null], model: [] }, { cleared: [], model: ['row_id'] }]);
  const grid = readFileSync(join(SRC, 'main.js'), 'utf8');
  eq('W17 the drop takes the grid\'s own filterChanged, sent after a timer - no read of its own; the next filter change reads',
    [out.left.drop, out.left.dropAfter], [{ reads: 0, model: [] }, 1]);
  eq('W11 every way to a table tells the label and the banner - boot\'s first table and a jump alike; the page tells them nowhere else',
    [out.left.followed, (grid.match(/sourceLabel\.setRelation\(/g) || []).length, (grid.match(/redoBannerFollows\(/g) || []).length],
    [['dt_log', 'ledger_atom_rows'], 1, 2]);
  eq('W12 Discard reads the rows again - the server\'s value replaces a value that moved since the edit',
    out.left.discard, { pending: 0, reads: 1 });
  eq('W14 a read draws a staged cell at its staged value, and an edit the server moved under it says so',
    [out.left.conflict.read, out.left.conflict.unmoved],
    [{ drawn: 28.9, conflict: { server: 29.7, at: '2026-10-12 12:00:00' } }, { drawn: 28.9, conflict: null }]);
  eq('W15 a broadcast too - the same overlay',
    out.left.conflict.broadcast, { drawn: 28.9, conflict: { server: 29.7, at: '2026-10-12 12:00:00' } });
  eq('W16 Apply asks before a conflicted cell - Keep mine sends it, Take server draws the server value and sends the rest',
    [out.left.conflict.asked, out.left.conflict.mine, out.left.conflict.server],
    [{ sent: 0, line: '', text: '1 cell changed on the server since you edited', pending: 1 },
      { sent: [[{ row_id: 'R1', updates: { a: 28.9 } }]], pending: 0, line: 'none' },
      { sent: [[{ row_id: 'R2', updates: { a: 5 } }]], cell: 29.7, pending: 0 }]);
  const both = (re) => ['api.js', 'timeline.js'].map((f) => (readFileSync(join(SRC, f), 'utf8').match(re) || []).length);
  eq('W18 an edit, another page and back: no conflict with itself; a row the cache gave back, edited and left: none either; '
    + 'census - every cache write and cache read in api and timeline passes copyRows',
    [out.left.cacheTrip, both(/pageCache\.set\(/g), both(/pageCache\.set\(state\.currentSkip, \{ data: copyRows\(/g),
      both(/overlayStagedEdits\(cached\.data\)/g), both(/overlayStagedEdits\(copyRows\(cached\.data\)\)/g)],
    [{ staged: { drawn: 28.9, conflict: null }, again: null }, [1, 1], [1, 1], [0, 0], [1, 1]]);
  eq('W19 a broadcast of a staged row the grid does not hold adds it at the staged value, with its conflict - upsert and create',
    out.left.addedRows, { upsert: { drawn: 28.9, conflict: { server: 29.7, at: '2026-10-12 12:00:00' } },
      create: { drawn: 28.9, conflict: { server: 29.7, at: '2026-10-12 12:00:00' } } });
  eq('W20 Tx turned off while a cell is conflicted: Apply asks and Tx comes back on', out.left.conflict.txBack,
    { checked: true, active: true, sent: 0 });
  eq('W21 two Apply clicks before the first answers send one PUT', out.left.conflict.twice, 1);
  eq('W22 a change no redraw brought: Apply reads the staged rows again first, finds it, asks and sends nothing; '
    + 'the cached page takes the server\'s value too',
    out.left.conflict.unseen, { sent: 0, reread: [['R1']], conflict: { server: 29.7, at: null }, cached: 29.7 });
  eq('W23 the question\'s count follows the conflicts and it goes when they do',
    out.left.conflict.follows, ['2 cells changed on the server since you edited', '1 cell changed on the server since you edited', '', 'none']);
  eq('W24 a number spelled as text is the same number in a number column - "29.50" and 29.5 are no conflict', out.left.conflict.spelled, null);
  eq('W26 an answer holds for what was asked: a cell that conflicts after the question, or a server value that moved, is asked again; the next answer sends',
    out.left.conflict.bound, { reask: { sent: 0, text: '2 cells changed on the server since you edited' },
      then: [[{ row_id: 'R1', updates: { a: 28.9 } }, { row_id: 'R2', updates: { a: 20 } }]],
      moved: { sent: 0, text: '1 cell changed on the server since you edited' } });
  eq('W27 a text column keeps its spellings apart - "1.10" and "1.1" are a conflict', out.left.conflict.textSpelled, { server: '1.1', at: null });
  eq('W28 an edit made while the PUT is out stays staged; one edited again stays, now made over the value just saved',
    out.left.conflict.putWindow, { sent: [[{ row_id: 'R1', updates: { a: 28.9 } }]], pending: ['R1_a', 'R2_a'], r1Over: 28.9 });
  eq('W29 Tx off and the read again fails: Tx comes back on, the edit still staged', out.left.conflict.failedRead,
    { checked: true, active: true, pending: 1 });
  eq('W30 an editor open at Apply: Apply closes it and waits for the grid to hand the edit over, and its value goes with that Apply',
    out.left.conflict.editorOpen, { finished: true, sent: [[{ row_id: 'R2', updates: { a: 20 } }, { row_id: 'R1', updates: { a: 29.1 } }]], pending: [] });
  eq('W31 an editor left unchanged hands nothing over: Apply goes on without it', out.left.conflict.editorSame,
    { finished: true, sent: [[{ row_id: 'R2', updates: { a: 21 } }]] });
  eq('V1 the read again says itself on the bottom line; a second click says it is already applying; a read that never answers is cut at the one time cap - the request aborted, Apply stopped and saying so (queue_poll timedRead)',
    out.left.conflict.saying, ['Checking 1 row on the server\u2026', 'Already applying',
      { cut: true, aborted: true, said: 'Apply stopped: the staged rows did not answer in 15 s' }]);
  eq('W32 Take server on a cell whose server value went back to the value it was edited over: not sent, the edit gone, the cell at that value; two asked and one went back: both go (lead 10-13 1)',
    out.left.conflict.wentBack, { one: { sent: [], pending: [], drawn: 28.5 }, two: { sent: [], pending: [], drawn: [29.7, 4] } });
  eq('W33 Tx turned off to apply: the cell edited again while that PUT is out is staged, not sent straight nor painted over by the batch\'s answer; Tx back on for it (lead 10-13 2)',
    out.left.conflict.offApply, { sent: [[{ row_id: 'R1', updates: { a: 28.9 } }]], pending: [['R1', 29.1]], drawn: 29.1, tx: [true, true] });
  eq('W34 Tx turned off to apply and the PUT refused: the edit still staged, Tx back on (lead 10-13 3)',
    out.left.conflict.putRefused, { pending: ['R1_a'], tx: [true, true] });
  eq('W35 a PUT that never answers is cut at the one time cap: Apply ends, the edit still staged, Tx on (lead 10-13 5)',
    out.left.conflict.putCut, { finished: true, pending: ['R1_a'], tx: [true, true] });
  eq('W25 a deleted row\'s staged edit is dropped and the bottom line says so - a broadcast delete, and a row Apply\'s read no longer finds',
    [out.left.conflict.deleted, out.left.conflict.goneOnRead],
    [{ pending: 0, said: true }, { pending: 0, sent: 0, said: true }]);
  eq('W13 ...and at once puts the value from before the edit back, both halves - no staged value waits for the read',
    out.left.atOnce, { value: 28, is_overwrite: false, priority_source: null });
  eq('W9 census: the grid\'s reads of the open table go through the seat - api 6 (schema, data, count, Apply\'s read of the '
    + 'staged rows, load all, export - the last two moved from main for the count ㄱ-1), main 0, timeline 1 (row jump), '
    + 'value_suggest 1 (column values)',
    { api: callsIn('api.js'), main: callsIn('main.js'), timeline: callsIn('timeline.js'), suggest: callsIn('value_suggest.js') },
    { api: 6, main: 0, timeline: 1, suggest: 1 });
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
  { id: 'G3', what: 'a switch does not redraw the tabs', catches: 'W3 ', file: 'api.js',
    mutate: (t) => swap(t, '  state.gridWorld = null;\n  drawWorldTabs();\n', '  state.gridWorld = null;\n') },
  { id: 'G4', what: 'a pick does not read again', catches: 'W5', file: 'api.js',
    mutate: (t) => swap(t, '  drawWorldTabs();\n  await fetchData(true);\n}', '  drawWorldTabs();\n}') },
  { id: 'G5', what: 'the page read goes round the seat', catches: 'W6', file: 'api.js',
    mutate: (t) => swap(t, '    const res = await gridFetch(url);\n    // ', '    const res = await fetch(url);\n    // ') },
  { id: 'G6', what: 'the list load drops per_world', catches: 'W3 ', file: 'api.js',
    mutate: (t) => swap(t, 'perWorld: data.per_world,', 'perWorld: undefined,') },
  { id: 'G7', what: 'the row jump goes round the seat', catches: 'W6', file: 'timeline.js',
    // re-aimed (lead 87dfa71d7): the jump's refusal check now stands between the read and its body
    mutate: (t) => swap(t, '    const res = await gridFetch(url);\n\n    // 🔴 THE REFUSAL IS SHOWN',
      '    const res = await fetch(url);\n\n    // 🔴 THE REFUSAL IS SHOWN') },
  { id: 'G8', what: 'the operating world is not marked', catches: 'W3 ', file: 'world_tabs.js',
    mutate: (t) => swap(t, '      if (name === view.operating) {', '      if (false) {') },
  { id: 'G9', what: 'no tab is shown while none is picked', catches: 'W3 ', file: 'world_tabs.js',
    mutate: (t) => swap(t, 'const shown = view.current || view.operating;', 'const shown = view.current;') },
  { id: 'G10', what: 'a switch keeps the last table\'s filters - the code before', catches: 'W10', file: 'api.js',
    mutate: (t) => swap(t, '  if (leaving !== tableName) await dropGridFilters();\n', '') },
  { id: 'G11', what: 'the same table switched again loses its filters', catches: 'W10', file: 'api.js',
    mutate: (t) => swap(t, '  if (leaving !== tableName) await dropGridFilters();', '  await dropGridFilters();') },
  { id: 'G12', what: 'a switch tells the label and the banner nothing - only the dropdown and boot did', catches: 'W11', file: 'api.js',
    mutate: (t) => swap(t, '  if (tableFollower) tableFollower(tableName);\n', '') },
  { id: 'G13', what: 'Discard puts nothing back at once - the staged value stays until the read', catches: 'W13', file: 'api.js',
    mutate: (t) => swap(t, '    row.data[colId].value = oldValue;\n', '') },
  { id: 'G15', what: 'Discard puts the value back and not the pin', catches: 'W13', file: 'api.js',
    mutate: (t) => swap(t, '    row.data[colId].priority_source = oldPrioritySource ?? null;\n', '') },
  { id: 'G21', what: 'the drop takes no event - the timer\'s filterChanged reads the table (the flag before)', catches: 'W17', file: 'grid.js',
    mutate: (t) => swap(t, '  if (takeFilterChange) { takeFilterChange(); return; }\n', '') },
  { id: 'G16', what: 'a read draws the server value over a staged cell - the code before', catches: 'W14', file: 'api.js',
    mutate: (t) => swap(t, "    } else {\n      state.gridApi.setGridOption('rowData', overlayStagedEdits(result.data));\n    }",
      "    } else {\n      state.gridApi.setGridOption('rowData', result.data);\n    }") },
  { id: 'G17', what: 'a broadcast draws the server value over a staged cell - the code before', catches: 'W15', file: 'websocket.js',
    mutate: (t) => swap(t, '        update: overlayStagedEdits(updatedRows),', '        update: updatedRows,') },
  { id: 'G18', what: 'Apply sends a conflicted cell unasked - the code before', catches: 'W16', file: 'api.js',
    mutate: (t) => swap(t, '  if (conflicted.length && !answered) {\n', '  if (false) {\n') },
  { id: 'G22', what: 'the cache keeps the rows the grid draws - the code before', catches: 'W18', file: 'api.js',
    mutate: (t) => swap(t, '{ data: copyRows(result.data), count }', '{ data: result.data, count }') },
  { id: 'G23', what: 'a page from the cache hands the grid the cache\'s own rows', catches: 'W18', file: 'api.js',
    mutate: (t) => swap(t, 'overlayStagedEdits(copyRows(cached.data))', 'overlayStagedEdits(cached.data)') },
  { id: 'G24', what: 'a broadcast adds a row the grid does not hold round the overlay - the code before', catches: 'W19', file: 'websocket.js',
    mutate: (t) => swap(t, '        add: overlayStagedEdits(addedRows)\n', '        add: addedRows\n') },
  { id: 'G25', what: 'a create broadcast adds its rows round the overlay - the code before', catches: 'W19', file: 'websocket.js',
    mutate: (t) => swap(t, 'applyTransaction({ add: overlayStagedEdits(normalizedItems) })', 'applyTransaction({ add: normalizedItems })') },
  { id: 'G26', what: 'asking leaves Tx off', catches: 'W20', file: 'api.js',
    mutate: (t) => swap(t, '  if (elements.txModeToggle) elements.txModeToggle.checked = true;\n  state.txModeActive = true;\n', '') },
  { id: 'G27', what: 'a second Apply runs beside the first', catches: 'W21', file: 'api.js',
    mutate: (t) => swap(t, "  if (applying) { elements.performanceLog.textContent = 'Already applying'; return; }\n", '') },
  { id: 'G28', what: 'Apply reads nothing again - only a redraw finds a conflict (the code before)', catches: 'W22', file: 'api.js',
    mutate: (t) => swap(t, '    dropped = await rereadStagedRows();\n', '') },
  { id: 'G33', what: 'Apply\'s read leaves the cached pages stale (18766: a false conflict after another page and back)', catches: 'W22', file: 'api.js',
    mutate: (t) => swap(t, '    cached.data = cached.data.map((row) => (fresh.has(row.row_id) ? copyRow(fresh.get(row.row_id)) : row));\n', '') },
  { id: 'G34', what: 'an answer applies to whatever conflicts when it is pressed (the code before)', catches: 'W26', file: 'api.js',
    mutate: (t) => swap(t, "  const answered = within && (choice === 'server' || conflicted.length === 0 || conflicted.length === asked.size);", '  const answered = Boolean(choice);') },
  { id: 'G35', what: 'an answer holds for a cell whose server value moved after the question', catches: 'W26', file: 'api.js',
    mutate: (t) => swap(t, '\n    && sameCellValue(asked.get(keyOf(edit)), edit.conflict.server, edit.colId));', ');') },
  { id: 'G36', what: 'numbers by value in a text column too (the code before)', catches: 'W27', file: 'api.js',
    mutate: (t) => swap(t, "  if ((state.currentColumnTypes || {})[colId] === 'number') {", '  if (true) {') },
  { id: 'G37', what: 'a saved PUT clears every staged edit - one made while it was out is lost (the code before)', catches: 'W28', file: 'api.js',
    mutate: (t) => swap(t, '      delete state.pendingTxEdits[key];\n    }\n    // V1 instrument', '      delete state.pendingTxEdits[key];\n    }\n    state.pendingTxEdits = {};\n    // V1 instrument') },
  { id: 'G38', what: 'an edit made again while the PUT was out is marked saved', catches: 'W28', file: 'api.js',
    mutate: (t) => swap(t, '      if (edit.newValue !== value) {', '      if (false) {') },
  { id: 'G39', what: 'a failed read again leaves Tx off', catches: 'W29', file: 'api.js',
    mutate: (t) => swap(t, '    keepTxOn();\n    elements.performanceLog.textContent = `Apply stopped:', '    elements.performanceLog.textContent = `Apply stopped:') },
  { id: 'G40', what: 'the read again says nothing while it runs', catches: 'V1', file: 'api.js',
    mutate: (t) => swap(t, "  elements.performanceLog.textContent = `Checking ${unitText(rowsStaged, 'row')} on the server\u2026`;\n", '') },
  { id: 'G41', what: 'the read again has no time cap', catches: 'V1', file: 'api.js',
    mutate: (t) => swap(t, 'const rows = await timedRead(async (signal) => {', 'const rows = await (async (signal) => {').replace('    return read;\n  });\n', '    return read;\n  })(undefined);\n') },
  { id: 'G46', what: 'the read again\'s request carries a signal the cap never aborts', catches: 'V1', file: 'api.js',
    mutate: (t) => swap(t, '`&defer_total=true&filters=${encodeURIComponent(filters)}`, { signal });', '`&defer_total=true&filters=${encodeURIComponent(filters)}`, { signal: new AbortController().signal });') },
  { id: 'G42', what: 'Apply leaves an open editor open - its value misses this Apply (the code before)', catches: 'W30', file: 'api.js',
    mutate: (t) => swap(t, '    const handingOver = closeOpenEditor();\n    if (handingOver) await handingOver;\n', '') },
  { id: 'G43', what: 'Apply closes the editor but does not wait for the hand-over', catches: 'W30', file: 'api.js',
    mutate: (t) => swap(t, '    if (handingOver) await handingOver;\n', '') },
  { id: 'G44', what: 'Apply waits for a hand-over an unchanged editor never makes', catches: 'W31', file: 'api.js',
    mutate: (t) => swap(t, '  if (Object.is(read(), before)) { cellHandedOver.delete(key); return null; }\n', '') },
  { id: 'G45', what: 'an edit made again while the PUT was out is dropped a tick later', catches: 'W28', file: 'api.js',
    mutate: (t) => swap(t, '        edit.conflict = null;\n        continue;\n', '        edit.conflict = null;\n        setTimeout(() => { delete state.pendingTxEdits[key]; }, 0);\n        continue;\n') },
  { id: 'G47', what: 'Take server drops only the cells that still conflict - one whose server value went back goes as mine (the code before)', catches: 'W32', file: 'api.js',
    mutate: (t) => swap(t, '      if (!edit) continue;\n      const node = state.gridApi.getRowNode(edit.rowId);\n', '      if (!edit || !edit.conflict) continue;\n      const node = state.gridApi.getRowNode(edit.rowId);\n') },
  { id: 'G48', what: 'the toggle turns Tx off before Apply has sent (the code before)', catches: 'W33', file: 'api.js',
    mutate: (t) => swap(t, '  const pendingCount = Object.keys(state.pendingTxEdits).length;\n  if (elements.txModeToggle && !elements.txModeToggle.checked',
      '  const pendingCount = Object.keys(state.pendingTxEdits).length;\n  state.txModeActive = elements.txModeToggle.checked;\n  if (elements.txModeToggle && !elements.txModeToggle.checked') },
  { id: 'G49', what: 'a refused PUT leaves Tx off (the code before)', catches: 'W34', file: 'api.js',
    mutate: (t) => swap(t, "    keepTxOn();\n    console.error('Batch apply failed', err);", "    console.error('Batch apply failed', err);") },
  { id: 'G50', what: 'the PUT has no time cap', catches: 'W35', file: 'api.js',
    mutate: (t) => swap(t, '    const result = await timedRead(async (signal) => {', '    const result = await (async (signal) => {').replace('      return res.json();\n    });\n    state.pageCache.clear();', '      return res.json();\n    })(undefined);\n    state.pageCache.clear();') },

  { id: 'G29', what: 'the question keeps the count it was asked with', catches: 'W23', file: 'api.js',
    mutate: (t) => swap(t, '  if (askingConflicts) sayConflicts(conflictedEdits().length);\n  return out;', '  return out;') },
  { id: 'G30', what: 'numbers compared by spelling - the code before', catches: 'W24', file: 'api.js',
    mutate: (t) => swap(t, '    if (Number.isFinite(x) && Number.isFinite(y)) return x === y;\n', '') },
  { id: 'G31', what: 'a broadcast delete leaves the row\'s staged edit - the code before', catches: 'W25', file: 'websocket.js',
    mutate: (t) => swap(t, '${droppedText(dropStagedEditsOf(rowIds))}', '') },
  { id: 'G32', what: 'a row Apply\'s read no longer finds keeps its edit', catches: 'W25', file: 'api.js',
    mutate: (t) => swap(t, '  return dropStagedEditsOf(ids.filter((id) => !found.has(id)));', '  return 0;') },
  { id: 'G19', what: 'Take server still sends the conflicted cell', catches: 'W16', file: 'api.js',
    mutate: (t) => swap(t, '      delete state.pendingTxEdits[key];\n    }\n    state.gridApi.refreshCells({ force: true });\n', '    }\n    state.gridApi.refreshCells({ force: true });\n') },
  { id: 'G20', what: 'the server value compared with the staged one, not the one the edit was made over', catches: 'W14', file: 'api.js',
    mutate: (t) => swap(t, 'sameCellValue(cell.value, edit.oldValue, edit.colId)', 'sameCellValue(cell.value, edit.newValue, edit.colId)') },
  { id: 'G14', what: 'Discard reads nothing again - the code before, a value moved since stays stale', catches: 'W12', file: 'api.js',
    mutate: (t) => swap(t, "  elements.performanceLog.textContent = 'Pending updates discarded';\n  return rereadGrid();",
      "  elements.performanceLog.textContent = 'Pending updates discarded';\n  return Promise.resolve();") },
];
const KEY = { 'state.js': 'state', 'api.js': 'api', 'timeline.js': 'timeline', 'world_tabs.js': 'tabs', 'websocket.js': 'ws', 'grid.js': 'grid' };
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
