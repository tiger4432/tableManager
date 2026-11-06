// GRID COLUMNS - the widths a table's columns open with, and hiding a column (owner 11-05).
// Run: node client2/tests/grid_columns_harness.mjs
//
//   W1 a column's fitted width: its widest value plus the cell's padding, up to the cap; never narrower than its header's
//      need, even past the cap; empty values say nothing
//   W2 renderGrid owes a fit: the first rows drawn after it set every data column's width once ('#', the checkboxes and
//      the pivot's held item column left out), none under its column's least (AG Grid then resizes none); the next rows
//      set none; a read with no rows keeps it owed
//   W3 fetchData pays it: a table's first read sets the widths
//   H1 setColumnsHidden hides or shows data columns only
//   H2 «N hidden ▾»: none hides it; it lists them, Show shows one, Show all every one; two on a page do not interfere
//   H3 the filter bar draws it with the grid's hidden data columns - not the pivot's held item column
//   H4 the header's popover has «Hide column»: it hides that column and closes; without a hide it has none
//   H5 a column no formula stands on (a system one, a pivot's item column): the same popover, its head alone
//   B1 the audit's Table cell breaks a name only after «_» «.» or at a space: each piece its own span
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
// a canvas whose text is 6 px a letter in the header's 600 weight and 7 px in a cell's font
doc.createElement = (tag) => {
  const el = make(tag);
  if (!el.getBoundingClientRect) el.getBoundingClientRect = rect;
  if (String(tag) === 'canvas') {
    const ctx = { font: '', measureText: (t) => ({ width: t.length * (ctx.font.startsWith('600') ? 6 : 7) }) };
    el.getContext = () => ctx;
  }
  return el;
};
const byId = new Map();
doc.getElementById = (id) => { if (!byId.has(id)) { const el = doc.createElement('div'); el.setAttribute('id', id); byId.set(id, el); } return byId.get(id); };
const gridCell = doc.createElement('div');
const query = doc.querySelector.bind(doc);
let cellDrawn = true;
doc.querySelector = (sel) => (sel === '#myGrid .ag-cell' ? (cellDrawn ? gridCell : null) : query(sel));
globalThis.document = doc;
globalThis.window = {
  location: { port: '', origin: 'http://box', href: 'http://box/', hash: '', search: '' },
  addEventListener() {}, removeEventListener() {},
  matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
};
// a cell pads 8 + 8 and draws a 1 px line; the cap is 200 px
const CAP = 200;
const PAD = 17;
globalThis.getComputedStyle = (el) => (el === gridCell
  ? { paddingLeft: '8px', paddingRight: '8px', borderLeftWidth: '0px', borderRightWidth: '1px', fontWeight: '400', fontSize: '12px',
    fontFamily: 'mono', getPropertyValue: () => '' }
  : { getPropertyValue: (name) => (name === '--grid-column-max' ? `${CAP}px` : '') });

const { state } = await import('../src/state.js');
const PIVOT = { column: 'itemid', value: 'value' };
const settle = async () => { for (let i = 0; i < 20; i += 1) await new Promise((r) => setTimeout(r, 0)); };
// the name, the cell's padding (32) and the sort arrow and filter mark (48)
const header = (word) => Math.ceil(word.length * 6.4) + 32 + 48;
const col = (id, { visible = true, headerName = id.toUpperCase(), def = {}, min = 120 } = {}) => ({
  getColId: () => id, getColDef: () => ({ headerName, ...def }), isVisible: () => visible, getMinWidth: () => min, getMaxWidth: () => null,
});
// the row number as renderGrid declares it: no sort, no filter, no floor of its own (owner 11-06)
const ROW_NUMBER = () => col('#', { headerName: '#', def: { sortable: false, filter: false }, min: 0 });

/** The long table «m» (lot, itemid, value) and a grid that holds rows and records what is asked of it. */
function stage({ cols, rows = [], pivotOn = false } = {}) {
  const calls = { widths: [], visible: [], urls: [] };
  let held = rows;
  state.currentTable = 'm';
  state.currentColumns = ['lot', 'itemid', 'value'];
  state.currentColumnTypes = { lot: 'string', itemid: 'string', value: 'number' };
  state.currentCompositeKeySources = ['lot', 'itemid'];
  state.currentBusinessKey = 'row_id';
  state.currentPivot = PIVOT;
  state.pivotOn = pivotOn;
  state.pivotView = pivotOn ? { ...PIVOT, keys: ['lot'], items: ['a'], items_more: 0 } : null;
  state.currentVirtualColumns = [];
  state.pendingTxEdits = {};
  state.serverSort = null;
  const columns = cols || [ROW_NUMBER(), col('ag-Grid-SelectionColumn'), col('lot'), col('itemid'), col('value')];
  state.gridApi = {
    getColumns: () => columns, getDisplayedRowCount: () => held.length,
    forEachNodeAfterFilterAndSort: (fn) => held.forEach((data, rowIndex) => fn({ data, rowIndex })),
    getCellValue: ({ rowNode, colKey }) => (colKey.getColId() === '#' ? rowNode.rowIndex + 1 : rowNode.data[colKey.getColId()]),
    setColumnWidths: (w) => calls.widths.push(w),
    setColumnsVisible: (ids, on) => calls.visible.push([ids, on]),
    setGridOption: (k, v) => { if (k === 'rowData') held = v; },
    getFilterModel: () => ({}), getColumnState: () => [], applyColumnState() {}, refreshCells() {}, getEditingCells: () => [],
    getFocusedCell: () => null, onSortChanged() {}, getColumnDefs: () => [], forEachNode() {}, showLoadingOverlay() {},
    hideOverlay() {}, ensureIndexVisible() {},
  };
  globalThis.fetch = async (url) => {
    calls.urls.push(String(url));
    const body = { data: [{ row_id: 'r1', lot: 'LOT-0000012-ABCDEFG', itemid: 'a', value: 3 }], total: 1, has_more: false };
    return { ok: true, status: 200, json: async () => body, text: async () => JSON.stringify(body) };
  };
  return calls;
}
const widthOf = (set, id) => (set.find((w) => w.key === id) || {}).newWidth;

async function suite(M) {
  const names = [];
  const fails = [];
  const say = (name, cond, detail) => {
    names.push(name);
    if (cond) { console.log(`  PASS ${name}`); return; }
    fails.push(name);
    console.log(`  FAIL ${name}${detail ? ' -- ' + detail : ''}`);
  };

  console.log('\n[W] widths');
  {
    const fit = M.grid.columnFitWidth;
    const len = (t) => t.length * 7;
    const got = [fit(50, ['ab', 'abcdefghij'], len, PAD, CAP), fit(50, ['a'], len, PAD, CAP), fit(50, ['x'.repeat(40)], len, PAD, CAP),
      fit(260, ['a'], len, PAD, CAP), fit(50, ['', null, undefined, 'abc'], len, PAD, CAP)];
    say('W1 widest value + padding, up to the cap; the header\'s need a floor even past the cap; empty values say nothing',
      JSON.stringify(got) === JSON.stringify([87, 50, CAP, 260, 50]), JSON.stringify(got));
  }
  {
    const calls = stage({ pivotOn: true });
    M.grid.renderGrid([]);
    M.grid.fitColumnWidths();
    const noRows = calls.widths.length;
    state.gridApi.setGridOption('rowData', [{ lot: 'LOT-0000012-ABCDEFG', itemid: 'a', value: 3 }, { lot: 'L1', itemid: 'b', value: 12345 }]);
    cellDrawn = false;
    M.grid.fitColumnWidths();
    const noCell = calls.widths.length;
    cellDrawn = true;
    M.grid.fitColumnWidths();
    M.grid.fitColumnWidths();
    const set = calls.widths[0] || [];
    // «#» (owner 11-06): its header no icons (6.4 with its spacing + 32), its numbers one digit past the widest («2» -> «00»)
    say('W2 owed by renderGrid: no rows or no cell drawn keep it owed; the first rows set the data columns and «#» once, none under its least',
      noRows === 0 && noCell === 0 && calls.widths.length === 1
        && JSON.stringify(set.map((w) => w.key)) === '["#","lot","value"]'
        && widthOf(set, 'lot') === 19 * 7 + PAD && header('VALUE') < 120 && widthOf(set, 'value') === 120
        && widthOf(set, '#') === Math.max(Math.ceil(6.4) + 32, 2 * 7 + PAD),
      JSON.stringify({ noRows, noCell, widths: calls.widths }));
  }
  {
    const calls = stage();
    M.grid.renderGrid([]);
    await M.api.fetchData(true);
    await settle();
    const first = calls.widths.length;
    await M.api.fetchData(true);
    await settle();
    say('W3 a table\'s first read sets the widths; the next read keeps them',
      first === 1 && calls.widths.length === 1 && widthOf(calls.widths[0], 'lot') === 19 * 7 + PAD,
      JSON.stringify({ first, widths: calls.widths }));
  }

  {
    // past a hundred rows the numbers are wider than «#»'s header: three digits, measured at four (4 x 7 + PAD)
    const calls = stage();
    M.grid.renderGrid([]);
    state.gridApi.setGridOption('rowData', Array.from({ length: 150 }, (_, i) => ({ lot: 'L' + i, itemid: 'a', value: i })));
    M.grid.fitColumnWidths();
    const set = calls.widths[0] || [];
    say('W4 «#» as wide as its widest number and one digit more - a page further on stays whole',
      widthOf(set, '#') === 4 * 7 + PAD, JSON.stringify(set));
  }

  console.log('\n[H] hiding');
  {
    const calls = stage({ pivotOn: true });
    M.grid.setColumnsHidden(['#', 'ag-Grid-SelectionColumn', 'lot', 'itemid', 'value'], true);
    M.grid.setColumnsHidden(['lot'], false);
    say('H1 data columns only, hidden or shown', JSON.stringify(calls.visible) === '[[["lot","value"],false],[["lot"],true]]',
      JSON.stringify(calls.visible));
  }
  {
    const shown = [];
    const mountA = doc.createElement('div');
    const mountB = doc.createElement('div');
    const a = new M.hidden.HiddenColumns(mountA, { doc, show: (ids) => shown.push(['a', ids]) });
    const b = new M.hidden.HiddenColumns(mountB, { doc, show: (ids) => shown.push(['b', ids]) });
    const emptyHidden = a.root.hidden;
    a.draw([{ id: 'lot', word: 'LOT' }, { id: 'value', word: 'VALUE' }]);
    b.draw([{ id: 'x', word: 'X' }]);
    a.button.dispatch('click');
    const rows = a.panel ? a.panel.querySelectorAll('.hidden-cols__row') : [];
    const words = [...rows].map((r) => r.querySelector('.hidden-cols__word').textContent);
    rows[1].querySelector('.hidden-cols__show').dispatch('click');
    a.panel.querySelector('.hidden-cols__all').dispatch('click');
    const twoSaid = a.button.textContent;
    a.draw([]);
    say('H2 none hides it and says nothing (no «0 hidden»); «2 hidden ▾» lists them; Show one, Show all; the other one untouched',
      emptyHidden === true && twoSaid === '2 hidden ▾' && a.root.hidden === true && a.button.textContent === '' && a.panel === null
        && JSON.stringify(words) === '["LOT","VALUE"]'
        && JSON.stringify(shown) === '[["a",["value"]],["a",["lot","value"]]]'
        && b.panel === null && b.button.textContent === '1 hidden ▾',
      JSON.stringify({ emptyHidden, twoSaid, after: a.button.textContent, words, shown, b: b.button.textContent }));
  }
  {
    stage({ pivotOn: true, cols: [col('#'), col('lot', { visible: false }), col('itemid', { visible: false }), col('value', { visible: false }), col('note')] });
    M.grid.renderFilterBar();
    // the last one in the bar: a module loaded again (a mutant) draws its own part beside the first's
    const open = [...document.getElementById('grid-filter-bar').querySelectorAll('.hidden-cols__open')].pop();
    say('H3 the filter bar says the grid\'s hidden data columns, not the pivot\'s held item column',
      open && open.textContent === '2 hidden ▾', open && open.textContent);
  }
  {
    const hid = [];
    const host = doc.createElement('div');
    const send = async () => ({ ok: true, body: {} });
    const pop = new M.formula.FormulaPopover(host, { doc, send, hide: (c) => hid.push(c) });
    await pop.open({ table: 'm', column: 'lot', columns: ['lot', 'value'] });
    const btn = pop.panel && pop.panel.querySelector('.formula-pop__hide');
    if (btn) btn.dispatch('click');
    const bare = new M.formula.FormulaPopover(doc.createElement('div'), { doc, send });
    await bare.open({ table: 'm', column: 'lot', columns: [] });
    say('H4 «Hide column» hides that column and closes; without a hide, none',
      btn && btn.textContent === 'Hide column' && JSON.stringify(hid) === '["lot"]' && pop.panel === null
        && bare.panel.querySelector('.formula-pop__hide') === null,
      JSON.stringify({ btn: Boolean(btn), hid, open: pop.panel !== null }));
  }
  {
    const hid = [];
    const asked = [];
    const send = async (req) => { asked.push(req); return { ok: true, body: {} }; };
    const pop = new M.formula.FormulaPopover(doc.createElement('div'), { doc, send, hide: (c) => hid.push(c) });
    await pop.open({ table: 'm', column: 'item:BOW', anchor: null, formula: false, word: 'BOW', columns: ['lot'] });
    const p = pop.panel;
    const title = p && p.querySelector('.formula-pop__title');
    const bare = p && !p.querySelector('.formula-pop__input') && !p.querySelector('.formula-pop__apply');
    const btn = p && p.querySelector('.formula-pop__hide');
    if (btn) btn.dispatch('click');
    say('H5 no formula stands on the column: the same popover, its head alone - «Hide column» hides it; no formula read',
      Boolean(title) && title.textContent === 'm · BOW' && bare && asked.length === 0 && JSON.stringify(hid) === '["item:BOW"]'
        && pop.panel === null, JSON.stringify({ title: title && title.textContent, bare, asked: asked.length, hid }));
  }

  console.log('\n[B] the audit\'s Table cell');
  {
    const g = { transaction_id: 'TX-1', total_count: 300, logs: [{ id: 1, row_id: 'abcdef0123456789', column_name: 'c', old_value: 'A',
      new_value: 'B', source_name: 'user', updated_by: 'kim', timestamp: '2026-11-05T01:00:00', business_key: 'K', table_name: 'dt_eqp.log_x' },
    { id: 2, row_id: 'r2', column_name: 'c', table_name: 'lot_event' }] };
    // the row is written as html: its li keeps the text and answers its queries with a node that takes listeners
    const htmlNode = () => { const node = { _html: '', style: {}, dataset: {}, classList: { add() {}, remove() {}, contains: () => false },
      set innerHTML(v) { node._html = String(v); }, get innerHTML() { return node._html; },
      querySelector: () => htmlNode(), querySelectorAll: () => [], addEventListener() {}, setAttribute() {}, appendChild: (c) => c };
    return node; };
    const create = doc.createElement;
    doc.createElement = (tag) => (tag === 'li' ? htmlNode() : create(tag));
    let html = '';
    try { html = M.timeline.createGlobalTimelineItemDom(g).innerHTML; } finally { doc.createElement = create; }
    const cell = (/<span class="audit-target-table"[^>]*>([\s\S]*?)<\/span><\/div>/.exec(html) || [])[1] || '';
    const pieces = [...cell.matchAll(/<span class="audit-tbl-piece">([^<]*)<\/span>(<wbr>)?/g)].map((m) => m[1] + (m[2] ? '|' : ''));
    say('B1 broken only after «_» «.» or at a space, each piece its own span',
      JSON.stringify(pieces) === '["dt_|","eqp.|","log_|","x","+1","…"]' && /data-wrap-ok/.test(html), JSON.stringify(pieces));
  }
  return { names, failures: fails, ran: names.length };
}

const M = {
  grid: await import('../src/grid.js'), api: await import('../src/api.js'), hidden: await import('../src/hidden_columns.js'),
  formula: await import('../src/formula_popover.js'), timeline: await import('../src/timeline.js'),
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
  { id: 'X1', what: 'no cap', catches: 'W1', file: 'grid.js', from: 'Math.min(cap, widest)', to: 'widest' },
  { id: 'X2', what: 'the cap cuts the header too', catches: 'W1', file: 'grid.js',
    from: 'Math.ceil(Math.max(header, Math.min(cap, widest)))', to: 'Math.ceil(Math.min(cap, Math.max(header, widest)))' },
  { id: 'X3', what: 'no padding', catches: 'W1', file: 'grid.js', from: 'measure(String(text)) + pad', to: 'measure(String(text))' },
  { id: 'X4', what: 'fitted on every read', catches: 'W2', file: 'grid.js', from: '  widthsOwed = false;\n  const cs', to: '  const cs' },
  { id: 'X5', what: 'renderGrid owes nothing', catches: 'W2', file: 'grid.js', from: '  widthsOwed = true;\n', to: '' },
  { id: 'X6', what: 'the gutter and checkbox columns fitted too', catches: 'W2', file: 'grid.js',
    from: "api.getColumns().filter((col) => isDataColumn(col.getColId()) || col.getColId() === '#').map", to: 'api.getColumns().map' },
  { id: 'X19', what: '«#» measured at its widest number, no digit more', catches: 'W4', file: 'grid.js',
    from: "'0'.repeat(digits + 1)", to: "'0'.repeat(digits)" },
  { id: 'X20', what: '«#» left at its 100', catches: 'W2', file: 'grid.js',
    from: " || col.getColId() === '#').map", to: ').map' },
  { id: 'X7', what: 'paid before the cell is drawn', catches: 'W2', file: 'grid.js', from: '  if (!cell) return;\n', to: '' },
  { id: 'X15', what: 'a width under its column\'s least is sent (AG Grid then resizes nothing)', catches: 'W2', file: 'grid.js',
    from: 'newWidth: Math.min(col.getMaxWidth() || Infinity, Math.max(col.getMinWidth() || 0, columnFitWidth(', to: 'newWidth: ((columnFitWidth(' },
  { id: 'X8', what: 'the read does not pay it', catches: 'W3', file: 'api.js', from: '    fitColumnWidths();\n', to: '' },
  { id: 'X9', what: 'hides the gutter too', catches: 'H1', file: 'grid.js', from: 'colIds.filter(isDataColumn)', to: 'colIds' },
  { id: 'X10', what: 'Show all shows the first only', catches: 'H2', file: 'hidden_columns.js',
    from: 'this.show(this.hidden.map((col) => col.id))', to: 'this.show([this.hidden[0].id])' },
  { id: 'X11', what: 'none still shows the chip', catches: 'H2', file: 'hidden_columns.js', from: 'this.root.hidden = !hidden.length;', to: '' },
  { id: 'X12', what: 'the bar counts every column', catches: 'H3', file: 'grid.js',
    from: '.filter((col) => isDataColumn(col.getColId()) && !col.isVisible())', to: '.filter((col) => !col.isVisible())' },
  { id: 'X16', what: 'none still says «0 hidden»', catches: 'H2', file: 'hidden_columns.js',
    from: "hidden.length ? `${hidden.length} hidden ▾` : ''", to: '`${hidden.length} hidden ▾`' },
  { id: 'X17', what: 'the hide-only popover draws the formula too', catches: 'H5', file: 'formula_popover.js',
    from: '    if (only !== null) { this.mount(panel); return; }\n', to: '' },
  { id: 'X18', what: 'the hide-only popover reads the formula', catches: 'H5', file: 'formula_popover.js',
    from: '    if (!formula) return;\n', to: "    if (!formula) { await this.send(formulaRequest('read', { table })); return; }\n" },
  { id: 'X13', what: 'Hide column leaves the popover open', catches: 'H4', file: 'formula_popover.js',
    from: '{ this.hide(column); this.close(); }', to: '{ this.hide(column); }' },
  { id: 'X14', what: 'the name breaks only at spaces', catches: 'B1', file: 'timeline.js',
    from: '/[^_.\\s]*[_.]|[^_.\\s]+|\\s+/g', to: '/[^\\s]+|\\s+/g' },
];
const scored = await scoreMutants(MUTANTS, async (mu) => quietly(async () => {
  const mutate = (t) => swap(t.replace(/\r\n/g, '\n'), mu.from, mu.to);
  const loaded = (await loadWithProbe(SRC(mu.file), { mutate, tag: `gc${mu.id}` })).module;
  const key = { 'grid.js': 'grid', 'api.js': 'api', 'hidden_columns.js': 'hidden', 'formula_popover.js': 'formula', 'timeline.js': 'timeline' }[mu.file];
  return suite({ ...M, [key]: loaded });
}), { baselineNames: base.names, title: '\n  [mutants] - each must be caught by the check it names.' });
pass += MUTANTS.length - scored.wrong;
for (let i = 0; i < scored.wrong; i += 1) failures.push(`mutant verdict ${i + 1}`);

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
