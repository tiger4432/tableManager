/**
 * grid_view_readonly -- a table the catalogue calls a VIEW offers no write control, and a cell
 * with no layering marker draws no badge.
 *
 * WHY THIS EXISTS (C-84). The main grid made every stored column editable (`editable: !isSystem`)
 * and the three write funnels guarded per COLUMN only, so on a relation the server serves as a
 * view the operator could open an editor, paste, clear or bulk-fill and meet the server's 400 in
 * the cell. The catalogue now says which it is (`/tables/<n>/schema.kind`, S-187), so the client
 * can stop offering the write instead of discovering it is refused.
 *
 * WHAT IT SCORES:
 *   P  the predicate: only the word 'view' is a view. '' (old server / not yet read) is NOT
 *   A  the wire: `loadSchema` records `kind`, and only when the server sent a string
 *   B  edit entry: on a view every column is `editable: false`; on a table nothing changed
 *   C  the three write funnels (paste, clear, bulk fill) issue NO write on a view -- and DO
 *      issue one on a table, so C is not vacuous -- and each says why on screen
 *   D  a cell carrying no marker draws no badge, and a cell carrying one still does
 *   E  the two source rows draw no pin/delete when the caller says the table is not writable
 *
 * 🔴 NOT INFERRED FROM THE DATA SHAPE. A view cell is `{value}` only -- and so is a page of an
 *    ordinary table nobody has overwritten. Reading the shape would turn a healthy table
 *    read-only, which is a proxy standing in for a property. The answer comes off the catalogue.
 *
 * 🔴 SIX SEATS, ONE PREDICATE, ONE FIXTURE. That is the point of the gate: the same staged
 *    schema is asked at every seat, because a per-seat answer is how two spellings of one rule
 *    start to diverge (criterion ④).
 *
 * IT IMPORTS ITS SUBJECTS. Mutants are whole modules (`lib/probe.mjs`); one file is swapped per
 * run and the rest stay real, which is also why a `state.js` mutant is scored through P (its copy
 * carries its own state object and the real modules cannot see it).
 *
 * CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
 */
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(HERE, '..', 'src');
const FILE = (name) => path.join(SRC, name);

// ── the DOM the modules touch, whole enough to be believed ──────────────────────────────
const nodes = new Map();
function fakeNode(id) {
  return {
    id, innerHTML: '', textContent: '', value: '', checked: false,
    style: {}, dataset: {}, classList: { add() {}, remove() {}, contains: () => false },
    children: [],
    appendChild(c) { this.children.push(c); return c; },
    addEventListener() {}, removeEventListener() {},
    querySelector: () => null, querySelectorAll: () => [],
    setAttribute() {}, getAttribute: () => null, hasAttribute: () => false,
    focus() {}, blur() {}, remove() {}, insertAdjacentHTML() {},
  };
}
const listeners = new Map();
globalThis.document = {
  hidden: false, activeElement: null, body: fakeNode('body'),
  getElementById: (id) => {
    if (!nodes.has(id)) nodes.set(id, fakeNode(id));
    return nodes.get(id);
  },
  createElement: () => fakeNode('created'),
  querySelector: () => null, querySelectorAll: () => [],
  addEventListener: (type, fn) => {
    if (!listeners.has(type)) listeners.set(type, []);
    listeners.get(type).push(fn);
  },
  removeEventListener() {},
};
const log = () => document.getElementById('performance-log');

// ── the wire, measured 2026-09-13 on the live box (PID 43720) ───────────────────────────
//    `/tables/ledger_events/schema` -> `kind: "view"`; `/tables/dt_log/schema` -> `"table"`.
const COLUMNS = ['id', 'qty', 'note', 'created_at', 'updated_at'];
const schemaBody = (kind) => {
  const body = {
    table_name: 't', columns: COLUMNS.slice(),
    column_types: { id: 'string', qty: 'number', note: 'string' },
    business_key: 'id', composite_key_source: [],
    virtual_columns: [], join_resolved_columns: [],
  };
  if (kind !== undefined) body.kind = kind;
  return body;
};
const rowData = () => ({
  row_id: 'R0', created_at: null, updated_at: null,
  data: { id: { value: 'R0' }, qty: { value: 1 }, note: { value: 'x' } },
});

// ── the fetch spy: every write is counted, every read answers the staged schema ──────────
let staged = schemaBody('view');
let writes = [];
globalThis.fetch = async (url, opts = {}) => {
  const method = String(opts.method || 'GET').toUpperCase();
  if (method !== 'GET') writes.push({ url: String(url), method });
  return {
    ok: true, status: 200,
    json: async () => (String(url).endsWith('/schema') ? staged : { data: [], total: 0 }),
    text: async () => '',
  };
};

let pass = 0, fail = 0, quiet = false;
const failedNames = [];
function ok(cond, name) {
  if (cond) { pass++; if (!quiet) console.log(`  OK   ${name}`); }
  else { fail++; failedNames.push(name); if (!quiet) console.log(`  BAD  ${name}`); }
  return !!cond;
}

const REAL = {
  state: await import('../src/state.js'),
  api: await import('../src/api.js'),
  grid: await import('../src/grid.js'),
  clipboard: await import('../src/clipboard.js'),
  ui: await import('../src/ui.js'),
  rows: await import('../src/source_rows.js'),
};
const realState = REAL.state.state;

/** Stage a table of the given kind through the REAL `loadSchema`, and hand back the grid api. */
async function stageThrough(api, kind) {
  staged = schemaBody(kind);
  realState.currentTable = 't';
  realState.pageCache = new Map();
  await api.loadSchema('t');
  realState.selectedCellsMap = { '0_note': { rowIndex: 0, colId: 'note' } };
  realState.dragStartCell = null;
  realState.dragEndCell = null;
  realState.txModeActive = false;
  realState.pendingTxEdits = {};
  realState.visibleColIndexMap = Object.fromEntries(COLUMNS.map((c, i) => [c, i]));
  realState.smartPasteArmedUntil = 0;
  realState.gridApi = {
    getFocusedCell: () => null,
    getColumnState: () => COLUMNS.map((c) => ({ colId: c, hide: false })),
    getColumns: () => COLUMNS.map((c) => ({ getColId: () => c })),
    getDisplayedRowAtIndex: (i) => (i === 0 ? { data: rowData(), id: 'R0' } : null),
    getRowNode: () => ({ data: rowData() }),
    getSelectedNodes: () => [],
    applyTransaction() {}, refreshCells() {}, setGridOption() {}, redrawRows() {},
    forEachNode() {}, getDisplayedRowCount: () => 1, ensureIndexVisible() {},
    getEditingCells: () => [], stopEditing() {}, getColumn: () => null,
    applyColumnState() {}, setFilterModel() {}, getFilterModel: () => ({}),
    onFilterChanged() {}, refreshHeader() {}, getGridOption: () => undefined,
  };
  return realState;
}

/** Run one funnel and report how many writes it issued. */
async function countWrites(run) {
  writes = [];
  log().textContent = '';
  try { await run(); } catch (e) { /* a funnel may walk further than this stub goes */ }
  return { writes: writes.filter((w) => w.method !== 'GET').length, note: log().textContent };
}

function pasteEvent(text) {
  return {
    preventDefault() {}, stopPropagation() {},
    clipboardData: { getData: () => text, items: [], files: [] },
  };
}

async function funnelRuns(M, kind) {
  await stageThrough(M.api, kind);
  listeners.clear();
  M.clipboard.setupClipboardHandlers();
  const onPaste = (listeners.get('paste') || [])[0];
  const paste = onPaste
    ? await countWrites(() => onPaste(pasteEvent('9')))
    : { writes: -1, note: 'NO PASTE LISTENER' };

  await stageThrough(M.api, kind);
  const clear = await countWrites(() => M.clipboard.clearSelectedCells());

  await stageThrough(M.api, kind);
  const fill = await countWrites(() => M.ui.applyValueToSelectedRange('9'));
  return { paste, clear, fill };
}

async function suite(M) {
  const before = { pass, fail };

  // ── P: the predicate itself, on the state object of the module under test ─────────────
  const S = M.state;
  S.state.currentTableKind = 'view';
  ok(S.tableIsView() === true, 'P1 the word `view` is a view');
  S.state.currentTableKind = 'table';
  ok(S.tableIsView() === false, 'P2 a table is not');
  S.state.currentTableKind = '';
  ok(S.tableIsView() === false,
    'P3 NOT ANNOUNCED is not a view -- an old server must not make a table read-only');

  // ── A: the wire ──────────────────────────────────────────────────────────────────────
  await stageThrough(M.api, 'view');
  ok(realState.currentTableKind === 'view', 'A1 loadSchema records the served kind');
  await stageThrough(M.api, 'table');
  ok(realState.currentTableKind === 'table', 'A2 ... including `table`');
  await stageThrough(M.api, undefined);
  ok(realState.currentTableKind === '',
    'A3 a schema with no `kind` leaves it empty, not undefined and not a view');
  await stageThrough(M.api, { not: 'a string' });
  ok(realState.currentTableKind === '',
    'A4 a non-string `kind` is refused -- only a string the server spelled counts');

  // ── B: edit entry ────────────────────────────────────────────────────────────────────
  await stageThrough(M.api, 'view');
  const viewDefs = M.grid.buildColumnDefs().filter((d) => d.field);
  ok(viewDefs.length > 0 && viewDefs.every((d) => d.editable === false),
    `B1 on a view EVERY column is editable:false -- ${viewDefs.filter(d => d.editable !== false).length} were not`);
  await stageThrough(M.api, 'table');
  const tableDefs = M.grid.buildColumnDefs().filter((d) => d.field);
  const systemish = ['created_at', 'updated_at', 'row_id', 'id', 'updated_by'];
  ok(tableDefs.some((d) => !systemish.includes(d.field) && d.editable === true),
    'B2 on a table the data columns are still editable -- no regression');
  ok(tableDefs.filter((d) => systemish.includes(d.field)).every((d) => d.editable === false),
    'B3 ... and a system column stays read-only, as before');

  // ── C: the three write funnels ────────────────────────────────────────────────────────
  const onView = await funnelRuns(M, 'view');
  ok(onView.paste.writes === 0, `C1 a paste into a view writes nothing -- ${onView.paste.writes} request(s)`);
  ok(onView.clear.writes === 0, `C2 delete-to-clear writes nothing -- ${onView.clear.writes} request(s)`);
  ok(onView.fill.writes === 0, `C3 bulk fill writes nothing -- ${onView.fill.writes} request(s)`);
  const NOTE = REAL.state.VIEW_READ_ONLY_NOTE;
  ok(onView.paste.note === NOTE && onView.clear.note === NOTE && onView.fill.note === NOTE,
    'C4 each refusal says WHY, in one spelling -- a silent no-op is a failure with no subtitle');

  const onTable = await funnelRuns(M, 'table');
  ok(onTable.paste.writes > 0, `C5 the same paste on a TABLE does write -- ${onTable.paste.writes} request(s)`);
  ok(onTable.clear.writes > 0, `C6 ... and so does the clear -- ${onTable.clear.writes} request(s)`);
  ok(onTable.fill.writes > 0, `C7 ... and the bulk fill -- ${onTable.fill.writes} request(s)`);

  // ── D: no marker, no badge ───────────────────────────────────────────────────────────
  await stageThrough(M.api, 'view');
  const noteDef = M.grid.buildColumnDefs().find((d) => d.field === 'note');
  const rules = (noteDef && noteDef.cellClassRules) || {};
  const paintNames = Object.keys(rules).filter((k) => k !== 'custom-range-selected');
  const bare = { data: { row_id: 'R0', data: { note: { value: 'x' } } }, node: { rowIndex: 0 } };
  ok(paintNames.length > 0 && paintNames.every((k) => rules[k](bare) !== true),
    `D1 a cell with no marker draws no badge -- rules [${paintNames.join(', ')}]`);
  const marked = {
    data: { row_id: 'R0', data: { note: { value: 'x', priority_source: 'user', is_overwrite: true } } },
    node: { rowIndex: 0 },
  };
  ok(paintNames.some((k) => rules[k](marked) === true),
    'D2 a cell that DOES carry a marker still draws one -- D1 is not vacuous');

  // ── E: the source rows ───────────────────────────────────────────────────────────────
  const hasBtns = (html) => /class="[^"]*pin-btn/.test(html) || /class="[^"]*del-btn/.test(html);
  ok(!hasBtns(M.rows.sourceRowHtml('excel', { value: 1 }, { isPinned: false, writable: false })),
    'E1 one cell`s row draws no pin/delete when the table is not writable');
  ok(hasBtns(M.rows.sourceRowHtml('excel', { value: 1 }, { isPinned: false, writable: true })),
    'E2 ... and draws both when it is');
  ok(!hasBtns(M.rows.sourceRowAllHtml('excel', ['a'], { isPinnedAll: false, writable: false })),
    'E3 the selection`s row likewise');
  ok(hasBtns(M.rows.sourceRowAllHtml('excel', ['a'], { isPinnedAll: false, writable: true })),
    'E4 ... and likewise draws both when writable');
  ok(!hasBtns(M.rows.sourceRowHtml('excel', { value: 1 }, { isPinned: false })),
    'E5 a caller that says NOTHING gets no write control -- the quiet half is the safe one');

  return { pass: pass - before.pass, fail: fail - before.fail };
}

console.log('-- the real modules ------------------------------------------------');
await suite(REAL);

// -- mutants ---------------------------------------------------------------------------
// Each names the FILE it edits; the rest of the bundle stays real.
const DEFECTS = [
  ['state.js: any announced kind counts as a view', 'state',
    s => s.replace("  return state.currentTableKind === 'view';", '  return !!state.currentTableKind;')],
  ['api.js: the kind is taken without checking it is a string', 'api',
    s => s.replace("    state.currentTableKind = typeof data.kind === 'string' ? data.kind : '';",
                   "    state.currentTableKind = data.kind || '';")],
  ['api.js: the kind is not recorded at all', 'api',
    s => s.replace("    state.currentTableKind = typeof data.kind === 'string' ? data.kind : '';\n", '')],
  ['grid.js: edit entry is offered on a view again', 'grid',
    s => s.replace('      editable: !isSystem && !viewTable,', '      editable: !isSystem,')],
  ['clipboard.js: the paste guard is gone', 'clipboard',
    s => s.replace('    if (tableIsView()) {\n      e.preventDefault();\n'
                   + '      elements.performanceLog.textContent = VIEW_READ_ONLY_NOTE;\n      return;\n    }\n', '')],
  ['clipboard.js: the clear guard is gone', 'clipboard',
    s => s.replace('  if (tableIsView()) { elements.performanceLog.textContent = VIEW_READ_ONLY_NOTE; return; }\n', '')],
  ['ui.js: the bulk-fill guard is gone', 'ui',
    s => s.replace('  if (tableIsView()) { elements.performanceLog.textContent = VIEW_READ_ONLY_NOTE; return; }\n', '')],
  ['clipboard.js: the refusal is silent', 'clipboard',
    s => s.replace('      elements.performanceLog.textContent = VIEW_READ_ONLY_NOTE;\n', '')],
  ['source_rows.js: a caller that omits the flag gets the controls', 'rows',
    s => s.replace('  const actions = writable\n', '  const actions = writable !== false\n')],
];
const CONTROLS = [
  ['grid.js: a local rename', 'grid',
    s => s.replace('  const viewTable = tableIsView();', '  const isAView = tableIsView();')
          .replace('      editable: !isSystem && !viewTable,', '      editable: !isSystem && !isAView,')],
  ['state.js: comments stripped', 'state',
    s => s.split('\n').filter(l => !/^\s*(\/\/|\*|\/\*)/.test(l)).join('\n')],
];

const FILES = { state: 'state.js', api: 'api.js', grid: 'grid.js', clipboard: 'clipboard.js', ui: 'ui.js', rows: 'source_rows.js' };

async function scoreMutant(key, mutate, tag) {
  try {
    const mod = (await loadWithProbe(FILE(FILES[key]), { mutate, tag })).module;
    const bundle = { ...REAL, [key]: mod };
    return await suite(bundle);
  } catch (e) {
    const m = String(e && e.message);
    if (/did not mutate|unchanged/.test(m)) {
      quiet = false;
      console.error(`\nan anchor no longer matches: ${m}`);
      process.exit(2);
    }
    return { pass: 0, fail: 1 };
  }
}

const base = { pass, fail };
failedNames.length = 0;

quiet = true;
let caught = 0; const escapedNames = [];
console.log('\n-- defect mutants (each must be CAUGHT) ----------------------------');
for (const [name, key, mutate] of DEFECTS) {
  const r = await scoreMutant(key, mutate, 'viewro');
  if (r.fail > 0) { caught++; console.log(`  caught  ${name}`); }
  else { escapedNames.push(name); console.log(`  ESCAPED ${name}`); }
}

let controlsCaught = 0;
console.log('\n-- control mutants (each must ESCAPE) ------------------------------');
for (const [name, key, mutate] of CONTROLS) {
  const r = await scoreMutant(key, mutate, 'viewroc');
  if (r.fail === 0) console.log(`  escaped ${name}`);
  else { controlsCaught++; console.log(`  CAUGHT  ${name}  <- a check is reading source text`); }
}
quiet = false;

if (base.fail) console.error(`\nfailed:\n  ${failedNames.join('\n  ')}`);
if (escapedNames.length) console.error(`\ndefects that escaped:\n  ${escapedNames.join('\n  ')}`);

const bad = base.fail + escapedNames.length + controlsCaught;
console.log(`\n${base.pass} passed, ${base.fail} failed; ${caught}/${DEFECTS.length} defects `
  + `caught, ${escapedNames.length} escaped; ${CONTROLS.length - controlsCaught}/`
  + `${CONTROLS.length} controls escaped.`);
console.log(`ASSERTIONS ${base.pass + base.fail} ${base.fail}`);
process.exit(bad ? 1 : 0);
