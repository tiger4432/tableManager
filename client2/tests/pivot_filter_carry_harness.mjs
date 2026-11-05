// PIVOT FILTER CARRY - «Pivot» pressed keeps the key and item column filters and drops the rest, both ways (owner 11-05
// ㄴ · ㄱ). Run: node client2/tests/pivot_filter_carry_harness.mjs
//
//   C1 the split: keys and the item column kept; the value column's, another column's and an item's «item:<v>» dropped
//   D1 the drop leaves the kept part on and reads nothing     D2 nothing to drop: no change, no wait
//   S1 long -> pivot: all off while the columns change, then lot and itemid on - one read, carrying them with pivot=true,
//      «Filters dropped: VALUE»
//   S2 pivot -> long: lot and itemid kept, «item:a» dropped by its header word        S3 staged edits: refused, nothing moved
//   H1 the pivot's columns hold the item column hidden; the next long defs show it again; the ones after leave it unsaid
//   H2 that hidden column holds no data in the pivot (no range, paste or column chooser reaches it); in the long view it does
//   H3 its filter in the pivot keeps its model and passes every group row (the server filtered); in the long view, today's
//   F1 a filterChanged with the filters the last read went out with (a column swap's) reads nothing; a changed one reads
//   F2 while a switch holds the reads, a filterChanged reads nothing; released, it reads
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { makeDoc } from './lib/board_dom.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = (name) => path.join(HERE, '..', 'src', name);

const doc = makeDoc('light');
doc.addEventListener = () => {};
doc.removeEventListener = () => {};
const rect = () => ({ left: 0, right: 0, top: 0, bottom: 0, width: 0, height: 0 });
const make = doc.createElement.bind(doc);
doc.createElement = (tag) => { const el = make(tag); if (!el.getBoundingClientRect) el.getBoundingClientRect = rect; return el; };
const byId = new Map();
doc.getElementById = (id) => { if (!byId.has(id)) { const el = doc.createElement('div'); el.setAttribute('id', id); byId.set(id, el); } return byId.get(id); };
globalThis.document = doc;
globalThis.window = {
  location: { port: '', origin: 'http://box', href: 'http://box/', hash: '', search: '' },
  addEventListener() {}, removeEventListener() {},
  matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
};

const { state } = await import('../src/state.js');
const log = () => document.getElementById('performance-log');
const PIVOT = { column: 'itemid', value: 'value' };
const ANSWER = { pivot: { ...PIVOT, keys: ['lot'], items: ['a', 'b'], items_more: 0 },
  data: [{ lot: 'L1', cells: { a: { value: 1, row_id: 'r1' } } }], total: 1, has_more: false };
const settle = async () => { for (let i = 0; i < 20; i += 1) await new Promise((r) => setTimeout(r, 0)); };

/** The long table «m» (lot, itemid, value) with a pivot, and a grid that answers like AG Grid: setFilterModel says
 *  filterChanged after a timer. */
function stage(grid, model, { pivotOn = false, staged = {} } = {}) {
  let held = { ...model };
  const calls = { setFilterModel: [], defs: [], urls: [], order: [] };
  state.currentTable = 'm';
  state.currentColumns = ['lot', 'itemid', 'value'];
  state.currentColumnTypes = { lot: 'string', itemid: 'string', value: 'number' };
  state.currentCompositeKeySources = ['lot', 'itemid'];
  state.currentBusinessKey = 'row_id';
  state.currentPivot = PIVOT;
  state.pivotOn = pivotOn;
  state.pivotView = pivotOn ? ANSWER.pivot : null;
  state.currentVirtualColumns = [];
  state.pendingTxEdits = staged;
  state.serverSort = null;
  state.gridApi = {
    getFilterModel: () => held,
    setFilterModel: (m) => { calls.setFilterModel.push(m); calls.order.push(m ? Object.keys(m).join('+') : 'none'); held = { ...(m || {}) }; setTimeout(() => { try { grid.gridFilterChanged(); } catch (e) { /* the chips */ } }, 5); },
    setGridOption: (k, v) => { if (k === 'columnDefs') { calls.defs.push(v); calls.order.push('columns'); } },
    getColumns: () => [], getColumnState: () => [], applyColumnState() {}, refreshCells() {}, getEditingCells: () => [],
    getDisplayedRowCount: () => 0, getFocusedCell: () => null, onSortChanged() {}, getColumnDefs: () => [],
    forEachNode() {}, showLoadingOverlay() {}, hideOverlay() {}, ensureIndexVisible() {}, setColumnsVisible() {},
  };
  globalThis.fetch = async (url) => {
    calls.urls.push(String(url));
    const body = String(url).includes('pivot=true') ? ANSWER : { data: [], total: 0, has_more: false };
    return { ok: true, status: 200, json: async () => body, text: async () => JSON.stringify(body) };
  };
  log().textContent = '';
  return { calls, model: () => held };
}
const dataReads = (calls) => calls.urls.filter((u) => /\/tables\/m\/data\?/.test(u));
const filtersOf = (url) => Object.keys(JSON.parse(new URL(url).searchParams.get('filters') || '{}')).sort();
const defOf = (defs, col) => (defs || []).find((d) => d.field === col);

async function suite(M) {
  const names = [];
  const fails = [];
  const say = (name, cond, detail) => {
    names.push(name);
    if (cond) { console.log(`  PASS ${name}`); return; }
    fails.push(name);
    console.log(`  FAIL ${name}${detail ? ' -- ' + detail : ''}`);
  };
  const f = (filter) => ({ filterType: 'text', type: 'equals', filter });

  console.log('\n[C] the split');
  const split = M.pivot.carriedFilters({ lot: f('L1'), itemid: f('a'), value: f('3'), note: f('x'), 'item:a': f('1') }, PIVOT, ['lot', 'itemid']);
  say('C1 keys and the item column kept; the value column\'s, another\'s and an item\'s dropped',
    JSON.stringify(Object.keys(split.keep)) === '["lot","itemid"]' && JSON.stringify(split.dropped) === '["value","note","item:a"]'
      && JSON.stringify(split.dropped.map(M.pivot.headerWord)) === '["VALUE","NOTE","a"]', JSON.stringify(split));

  console.log('\n[D] the drop');
  {
    const s = stage(M.grid, { lot: f('L1'), value: f('3') });
    await M.grid.dropGridFilters({ lot: f('L1') });
    await settle();
    say('D1 the drop leaves the kept part on and reads nothing',
      JSON.stringify(s.calls.setFilterModel) === JSON.stringify([{ lot: f('L1') }]) && dataReads(s.calls).length === 0,
      JSON.stringify({ set: s.calls.setFilterModel, reads: dataReads(s.calls).length }));
  }
  {
    const s = stage(M.grid, { lot: f('L1') });
    const t0 = Date.now();
    await M.grid.dropGridFilters({ lot: f('L1') });
    say('D2 nothing to drop: no change and no wait', s.calls.setFilterModel.length === 0 && Date.now() - t0 < 200,
      JSON.stringify({ set: s.calls.setFilterModel.length, ms: Date.now() - t0 }));
  }

  console.log('\n[S] the switch');
  {
    const s = stage(M.grid, { lot: f('L1'), itemid: f('a'), value: f('3') });
    await M.api.setGridPivot(true);
    await settle();
    const read = dataReads(s.calls)[0];
    say('S1 long -> pivot: lot and itemid kept, the read carries them with pivot=true, the value column named',
      JSON.stringify(Object.keys(s.model())) === '["lot","itemid"]' && read && read.includes('pivot=true')
        && JSON.stringify(filtersOf(read)) === '["itemid","lot"]' && log().textContent === 'Filters dropped: VALUE'
        && dataReads(s.calls).length === 1 && s.calls.order.slice(0, 3).join(' ') === 'none columns lot+itemid',
      JSON.stringify({ model: Object.keys(s.model()), read, reads: dataReads(s.calls).length, order: s.calls.order, log: log().textContent }));
  }
  {
    const s = stage(M.grid, { lot: f('L1'), itemid: f('a'), 'item:a': f('1') }, { pivotOn: true });
    await M.api.setGridPivot(false);
    await settle();
    const read = dataReads(s.calls)[0];
    say('S2 pivot -> long: lot and itemid kept, an item\'s filter named by its header word',
      JSON.stringify(Object.keys(s.model())) === '["lot","itemid"]' && read && !read.includes('pivot=true')
        && JSON.stringify(filtersOf(read)) === '["itemid","lot"]' && log().textContent === 'Filters dropped: a'
        && dataReads(s.calls).length === 1 && s.calls.order.slice(0, 3).join(' ') === 'none columns lot+itemid',
      JSON.stringify({ model: Object.keys(s.model()), read, reads: dataReads(s.calls).length, order: s.calls.order, log: log().textContent }));
  }
  {
    const s = stage(M.grid, { lot: f('L1'), value: f('3') }, { staged: { r1_value: { rowId: 'r1', colId: 'value' } } });
    await M.api.setGridPivot(true);
    await settle();
    say('S3 staged edits: refused as today, nothing moved',
      state.pivotOn === false && s.calls.setFilterModel.length === 0 && dataReads(s.calls).length === 0
        && log().textContent === 'Apply or discard the staged edits first',
      JSON.stringify({ pivotOn: state.pivotOn, set: s.calls.setFilterModel.length, log: log().textContent }));
  }

  console.log('\n[H] the hidden item column');
  {
    stage(M.grid, {}, { pivotOn: true });
    const pivotDefs = M.grid.buildColumnDefs();
    state.pivotOn = false;
    state.pivotView = null;
    const longDefs = M.grid.buildColumnDefs();
    const laterDefs = M.grid.buildColumnDefs();
    const hideOf = (defs) => { const d = defOf(defs, 'itemid'); return d ? ('hide' in d ? d.hide : 'unsaid') : 'absent'; };
    say('H1 the pivot holds the item column hidden; the next long defs show it; the ones after leave it unsaid',
      JSON.stringify([hideOf(pivotDefs), hideOf(longDefs), hideOf(laterDefs), hideOf([defOf(pivotDefs, 'lot')].filter(Boolean))])
        === '[true,false,"unsaid","absent"]' && 'hide' in defOf(pivotDefs, 'lot') === false,
      JSON.stringify([hideOf(pivotDefs), hideOf(longDefs), hideOf(laterDefs)]));
    const held = defOf(pivotDefs, 'itemid').filter;
    const filter = held && held.name === 'HeldColumnFilter' ? new M.pivot.HeldColumnFilter() : null;
    const model = f('a');
    const seen = filter ? (() => { filter.init({}); filter.setModel(model); const on = [filter.getModel() === model, filter.isFilterActive(),
      filter.doesFilterPass({ data: { data: {} } })]; filter.setModel(null); return [...on, filter.isFilterActive()]; })() : null;
    say('H3 in the pivot its filter keeps its model and passes every group row; in the long view, today\'s; keys keep theirs',
      JSON.stringify(seen) === '[true,true,true,false]' && defOf(longDefs, 'itemid').filter === 'agTextColumnFilter'
        && defOf(pivotDefs, 'lot').filter === 'agTextColumnFilter',
      JSON.stringify({ seen, long: defOf(longDefs, 'itemid').filter, lot: defOf(pivotDefs, 'lot').filter }));
  }
  {
    const S = M.st.state;
    Object.assign(S, { currentPivot: PIVOT, pivotOn: true });
    const inPivot = [M.st.isDataColumn('itemid'), M.st.isDataColumn('lot'), M.st.isDataColumn('item:a')];
    S.pivotOn = false;
    const inLong = M.st.isDataColumn('itemid');
    say('H2 the hidden item column holds no data in the pivot; keys and items do; in the long view it does',
      JSON.stringify([...inPivot, inLong]) === '[false,true,true,true]', JSON.stringify([...inPivot, inLong]));
  }

  console.log('\n[F] a filterChanged');
  {
    const s = stage(M.grid, { lot: f('L1') });
    await M.api.fetchData(true);
    await settle();
    const before = dataReads(s.calls).length;
    M.grid.gridFilterChanged();
    await settle();
    const same = dataReads(s.calls).length - before;
    state.gridApi.setFilterModel({ lot: f('L2') });
    await new Promise((r) => setTimeout(r, 30));
    await settle();
    const changed = dataReads(s.calls).length - before - same;
    say('F1 a filterChanged with the last read\'s filters reads nothing; a changed one reads once',
      before === 1 && same === 0 && changed === 1, JSON.stringify({ before, same, changed }));
  }
  {
    const s = stage(M.grid, { lot: f('L1') });
    const release = M.grid.holdFilterReads();
    s.model().lot = f('L3');
    M.grid.gridFilterChanged();
    await settle();
    const held = dataReads(s.calls).length;
    release();
    release();
    M.grid.gridFilterChanged();
    await settle();
    say('F2 held (a switch on its way): a changed filter reads nothing; released once (twice is once), it reads',
      held === 0 && dataReads(s.calls).length === 1, JSON.stringify({ held, after: dataReads(s.calls).length }));
  }
  return { ran: names.length, names, failures: fails };
}

const M = {
  pivot: await import('../src/grid_pivot.js'), grid: await import('../src/grid.js'),
  api: await import('../src/api.js'), st: await import('../src/state.js'),
};
const base = await suite(M);
let pass = base.ran - base.failures.length;
const failures = [...base.failures];

const { loadWithProbe } = await import('./lib/probe.mjs');
const { scoreMutants } = await import('./lib/mutation_scorer.mjs');
const swap = (text, from, to) => {
  if (!text.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`);
  return text.split(from).join(to);
};
const quietly = async (fn) => {
  const say = console.log;
  console.log = () => {};
  try { return await fn(); } finally { console.log = say; }
};
const MUTANTS = [
  { id: 'X1', what: 'the item column\'s filter is dropped', catches: 'C1', file: 'grid_pivot.js',
    from: 'const kept = [...pivotKeys(pivot, keySources), pivot.column];', to: 'const kept = pivotKeys(pivot, keySources);' },
  { id: 'X2', what: 'the drop drops all, keep or not', catches: 'D1', file: 'grid.js', from: '    api.setFilterModel(keep);', to: '    api.setFilterModel(null);' },
  { id: 'X3', what: 'nothing to drop still sets the model and waits', catches: 'D2', file: 'grid.js',
    from: 'JSON.stringify(api.getFilterModel() || {}) === JSON.stringify(keep || {})', to: '!Object.keys(api.getFilterModel() || {}).length' },
  { id: 'X4', what: 'the switch drops every filter, as before', catches: 'S1', file: 'api.js', from: '  await dropGridFilters(keep);', to: '  await dropGridFilters();' },
  { id: 'X5', what: 'the dropped ones are not named', catches: 'S1', file: 'api.js',
    from: "  if (dropped.length) elements.performanceLog.textContent = `Filters dropped: ${dropped.map(headerWord).join(', ')}`;", to: '' },
  { id: 'X6', what: 'the item column is not hidden in the pivot', catches: 'H1', file: 'grid.js',
    from: '      ...(col === held || col === lastHeld ? { hide: col === held } : {}),', to: '' },
  { id: 'X7', what: 'the long view does not show the item column again', catches: 'H1', file: 'grid.js',
    from: 'col === held || col === lastHeld ?', to: 'col === held ?' },
  { id: 'X8', what: 'the hidden item column counts as data in the pivot', catches: 'H2', file: 'state.js',
    from: "\n  && !(pivotShown() && colId === state.currentPivot.column);", to: ';' },
  { id: 'X10', what: 'the kept filters are set before the columns change (the item column\'s kind changes and loses it)', catches: 'S1',
    file: 'api.js', from: '    await dropGridFilters();\n    applyWriteGuards();', to: '    await dropGridFilters(keep);\n    applyWriteGuards();' },
  { id: 'X11', what: 'the held filter filters the group rows by their item column', catches: 'H3', file: 'grid_pivot.js',
    from: '  doesFilterPass() { return true; }', to: '  doesFilterPass() { return false; }' },
  { id: 'X12', what: 'the hidden item column keeps today\'s filter in the pivot', catches: 'H3', file: 'grid.js',
    from: '      filter: col === held ? HeldColumnFilter\n        : filterable', to: '      filter: filterable' },
  { id: 'X13', what: 'the hold is not read (the switch\'s own filterChanged reads too)', catches: 'F2', file: 'grid.js',
    from: '  if (!filterReadsHeld && (narrowingParams', to: '  if ((narrowingParams' },
  { id: 'X14', what: 'a second release lets go of another hold', catches: 'F2', file: 'grid.js',
    from: '  return () => { if (!released) { released = true; filterReadsHeld -= 1; } };', to: '  return () => { filterReadsHeld -= 1; };' },
  { id: 'X9', what: 'a filterChanged reads again with the filters as they were (a column swap reads twice)', catches: 'F1', file: 'grid.js',
    from: "  if (!filterReadsHeld && (narrowingParams({ gridApi: state.gridApi }).get('filters') || '') !== state.readFilters) fetchData(true);",
    to: '  if (!filterReadsHeld) fetchData(true);' },
];
const scored = await scoreMutants(MUTANTS, async (mu) => quietly(async () => {
  const mutate = (t) => swap(t, mu.from, mu.to);
  const loaded = (await loadWithProbe(SRC(mu.file), { mutate, tag: `pfc${mu.id}` })).module;
  const key = { 'grid_pivot.js': 'pivot', 'grid.js': 'grid', 'api.js': 'api', 'state.js': 'st' }[mu.file];
  return suite({ ...M, [key]: loaded });
}), { baselineNames: base.names, title: '\n  [mutants] - each must be caught by the check it names.' });
pass += MUTANTS.length - scored.wrong;
for (let i = 0; i < scored.wrong; i += 1) failures.push(`mutant verdict ${i + 1}`);

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
