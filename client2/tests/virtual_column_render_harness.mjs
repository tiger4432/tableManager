// Harness — rendering `/schema`'s `virtual_columns` in the grid, and the four write funnels
// that must NOT offer them.
// Run: node client2/tests/virtual_column_render_harness.mjs   (no node_modules — vm sandbox)
//
// WHAT IT SCORES. The REAL `loadSchema` (api.js), the REAL `buildColumnDefs` (grid.js), the
// REAL `getUnprotectedPushColumns` (map_editor.js) and the REAL per-cell decision blocks of
// the four client write funnels (clipboard.js x3, ui.js x1), all lifted verbatim out of the
// source and evaluated in a vm sandbox — the same technique as `push_gate_harness.mjs` and
// `value_suggest_keys_harness.mjs`, and for the same reason: those modules import `config.js`,
// which touches `window` at module scope, so they cannot be imported in node.
//
// THE FIXTURE IS THE ANNOUNCEMENT. There is no live `server/config/virtual_join_rules.json`
// on this box (only `.sample`), so nothing announces anything here and a harness that read the
// real config would score an empty list and pass vacuously. The schema RESPONSE is therefore
// supplied by the harness itself, shaped from the sample declaration
// (`bonding_log` <- `core_wafer_map`, expose `wafer_id`, label `미상`) plus a `number`-typed
// sibling — because a `number` virtual column carrying a string is the whole point.
//
// EVERY CHECK IS PAIRED WITH A MUTANT. The suite re-runs against deliberately defective
// sources and FAILS if a defect still passes — a check that cannot fail proves nothing. It
// also runs CONTROL mutants (a consistent rename of locals, and stripping every comment line)
// which must ESCAPE: if a control is caught, some check is reading source text rather than
// behaviour, and its green means nothing.
//
// EXTRACTION ANCHORS ARE THE ONE PLACE SOURCE TEXT IS READ, and this file exits 2 — loudly,
// not green — when one stops matching. A harness that goes quiet because it lost the code is
// worse than no harness.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..', '..');
const SRC = join(ROOT, 'client2', 'src');

function die(msg) {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  process.exit(2);
}

const read = f => readFileSync(join(SRC, f), 'utf8').replace(/\r\n/g, '\n');
const PRISTINE = {
  state: read('state.js'),
  api: read('api.js'),
  grid: read('grid.js'),
  clipboard: read('clipboard.js'),
  ui: read('ui.js'),
  map: read('map_editor.js')
};

// ── extraction ──────────────────────────────────────────────────────────────────

function balanced(src, from, open, close) {
  const i = src.indexOf(open, from);
  if (i < 0) return null;
  let depth = 0;
  for (let j = i; j < src.length; j++) {
    if (src[j] === open) depth++;
    else if (src[j] === close) { depth--; if (depth === 0) return { start: i, end: j }; }
  }
  return null;
}

/** A named function declaration, verbatim, with any `export` prefix dropped. */
function fnFrom(src, label, name) {
  const m = new RegExp(`(?:export\\s+)?(?:async\\s+)?function\\s+${name}\\s*\\(`).exec(src);
  if (!m) die(`function ${name} not found in ${label}`);
  const b = balanced(src, m.index, '{', '}');
  if (!b) die(`unbalanced braces for ${name} in ${label}`);
  return src.slice(m.index, b.end + 1).replace(/^export\s+/, '');
}

function constFrom(src, label, name) {
  const m = new RegExp(`(?:export\\s+)?const\\s+${name}\\s*=`).exec(src);
  if (!m) die(`const ${name} not found in ${label}`);
  let depth = 0;
  for (let j = m.index; j < src.length; j++) {
    const ch = src[j];
    if (ch === '[' || ch === '{') depth++;
    else if (ch === ']' || ch === '}') depth--;
    else if (ch === ';' && depth === 0) return src.slice(m.index, j + 1).replace(/^export\s+/, '');
  }
  die(`no terminator for const ${name} in ${label}`);
}

/**
 * The BODY of an arrow callback, wrapped as a function of `params`.
 *
 * The four write funnels are straight-line blocks inside large handlers, so the alternative
 * to slicing them is re-typing the guard chain here — and a harness that re-types the
 * predicate under test scores itself. `return;` inside a sliced block therefore means
 * "this cell was skipped", exactly as it does in the app.
 */
function arrowBodyFrom(src, label, anchor, params, after = 0) {
  const at = src.indexOf(anchor, after);
  if (at < 0) die(`anchor not found in ${label}: ${JSON.stringify(anchor)}`);
  const b = balanced(src, at, '{', '}');
  if (!b) die(`unbalanced braces after anchor in ${label}: ${JSON.stringify(anchor)}`);
  return `function (${params}) ${src.slice(b.start, b.end + 1)}`;
}

// ── fixtures ────────────────────────────────────────────────────────────────────

const STORED = ['pkg_id', 'core_lot', 'core_slot', 'bond_count', 'created_at', 'updated_at'];

// Shaped from `virtual_join_rules.json.sample` (`bonding_log_wafer_id`). `yield_pct` is the
// number-typed sibling the sample has no example of and this client must survive.
const VC_WAFER = {
  name: 'wafer_id', type: 'string', editable: false,
  right_table: 'core_wafer_map', rule: 'bonding_log_wafer_id', unresolved_label: '미상'
};
const VC_YIELD = {
  name: 'yield_pct', type: 'number', editable: false,
  right_table: 'core_wafer_map', rule: 'bonding_log_yield', unresolved_label: '미상'
};

const SCHEMA = {
  table_name: 'bonding_log',
  columns: STORED.slice(),
  column_types: { pkg_id: 'string', core_lot: 'string', core_slot: 'number', bond_count: 'number' },
  business_key: 'pkg_id',
  composite_key_source: [],
  map_key_columns: [],
  map_push_ok: false,
  virtual_columns: [VC_WAFER, VC_YIELD]
};

const cell = v => ({
  value: v, is_overwrite: false, is_collision_merge: false,
  sources: { virtual_join: v }, updated_by: 'system', priority_source: 'virtual_join'
});

// ── sandboxes ───────────────────────────────────────────────────────────────────

function baseGlobals() {
  return {
    // The sandboxed code logs; a mutant run is EXPECTED to be noisy and that noise is not
    // evidence, so it is muted while the sweep is scoring.
    console: {
      log: (...a) => { if (!quiet) console.log(...a); },
      error: (...a) => { if (!quiet) console.error(...a); },
      warn: (...a) => { if (!quiet) console.warn(...a); }
    },
    URLSearchParams, JSON, Number, String, Object, Array, Math, isNaN,
    Promise, Set, Map, Date, RegExp, Error,
    window: { location: { search: '' } },
    alert: () => {},
    document: {
      createElement: () => ({ set textContent(v) { this._t = v; }, get textContent() { return this._t; } }),
      querySelector: () => null
    }
  };
}

/** state.js verbatim: the `state` singleton and `isVirtualColumn` come from the real module. */
function withState(sources, extra = {}) {
  const sandbox = Object.assign(baseGlobals(), extra);
  const ctx = vm.createContext(sandbox);
  vm.runInContext(
    sources.state.replace(/^export\s+/gm, '')
    + '\n;globalThis.__state = state; globalThis.__isVirtualColumn = isVirtualColumn;',
    ctx, { filename: 'state.js' });
  return { ctx, sandbox, state: sandbox.__state, isVirtualColumn: sandbox.__isVirtualColumn };
}

/** The real `loadSchema`, fed a stubbed `fetch`. Records what the search dropdown was offered. */
async function runLoadSchema(sources, response) {
  const offered = [];
  const s = withState(sources, {
    API_BASE: '/api',
    resetSuggestLearning: () => {},
    fetch: async () => ({ json: async () => response })
  });
  s.sandbox.elements = {
    performanceLog: { textContent: '' },
    searchCols: { innerHTML: '', appendChild: o => offered.push(o.value) }
  };
  s.sandbox.document.createElement = () => ({ value: '', textContent: '' });
  vm.runInContext(fnFrom(sources.api, 'api.js', 'loadSchema')
    + '\n;globalThis.__loadSchema = loadSchema;', s.ctx, { filename: 'api.js#loadSchema' });
  await s.sandbox.__loadSchema('bonding_log');
  return { state: s.state, offered };
}

/** The real `buildColumnDefs`, with the schema already in state. */
function runBuildColumnDefs(sources, schema) {
  const s = withState(sources);
  Object.assign(s.state, {
    currentColumns: schema.columns.slice(),
    currentColumnTypes: schema.column_types,
    currentBusinessKey: schema.business_key,
    currentCompositeKeySources: schema.composite_key_source,
    currentVirtualColumns: schema.virtual_columns,
    viewMode: 'pagination', allDataLoaded: true, currentSkip: 0, pendingTxEdits: {}
  });
  s.sandbox.isCellInRange = () => false;
  s.sandbox.SuggestCellEditor = function () {};
  vm.runInContext([
    fnFrom(sources.grid, 'grid.js', 'rawCellValue'),
    fnFrom(sources.grid, 'grid.js', 'numericDisplayValue'),
    fnFrom(sources.grid, 'grid.js', 'buildColumnDefs'),
    'globalThis.__defs = buildColumnDefs();'
  ].join('\n\n'), s.ctx, { filename: 'grid.js#buildColumnDefs' });
  return s.sandbox.__defs;
}

/**
 * The four write funnels. Each returns the column ids that actually reached an update batch,
 * given a list of grid column ids the user's selection covered.
 */
function runWriteFunnels(sources, schema) {
  const s = withState(sources);
  Object.assign(s.state, {
    currentColumns: schema.columns.slice(),
    currentColumnTypes: schema.column_types,
    currentVirtualColumns: schema.virtual_columns,
    txModeActive: false, pendingTxEdits: {}, selectedCellsMap: {}, visibleColIndexMap: {}
  });
  s.state.gridApi = {
    getDisplayedRowAtIndex: i => ({ data: { row_id: `R${i}`, data: {} } }),
    getRowNode: id => ({ data: { row_id: id, data: {} } })
  };
  s.sandbox.CURRENT_USER = 'harness';
  s.sandbox.ensureCellObject = (d, c) => { if (!d.data[c]) d.data[c] = { value: '' }; };

  const clip = sources.clipboard;
  const singleAt = clip.indexOf('const val = parsedMatrix[0][0];');
  if (singleAt < 0) die('anchor not found in clipboard.js: the 1x1 paste branch');

  vm.runInContext([
    `var __paste1x1 = ${arrowBodyFrom(clip, 'clipboard.js', 'targetCells.forEach(cell => {', 'cell', singleAt)};`,
    `var __pasteMxN = ${arrowBodyFrom(clip, 'clipboard.js', 'rowValues.forEach((val, cOffset) => {', 'val, cOffset')};`,
    `var __clear = ${arrowBodyFrom(clip, 'clipboard.js', 'cellsToClear.forEach(cell => {', 'cell')};`,
    `var __bulkFill = ${arrowBodyFrom(sources.ui, 'ui.js', 'cellsToUpdate.forEach(cell => {', 'cell')};`,
    // the two READ predicates, which decide the SHAPE of a copied block
    `var __copyRange = ${arrowBodyFrom(clip, 'clipboard.js', 'visibleCols.filter((colId, idx) => {', 'colId, idx')};`,
    `var __copyRows = ${arrowBodyFrom(clip, 'clipboard.js', '.map(c => c.getColId()).filter(c => {', 'c')};`
  ].join('\n\n'), s.ctx, { filename: 'write-funnels' });

  const written = () => Object.keys(s.sandbox.updateMapByRow)
    .flatMap(r => Object.keys(s.sandbox.updateMapByRow[r].updates));
  const reset = () => { s.sandbox.updateMapByRow = {}; };

  return {
    paste1x1(colIds) {
      reset(); s.sandbox.val = '7';   // numeric-safe: the span includes a `number` column
      colIds.forEach(colId => s.sandbox.__paste1x1({ rowIndex: 0, colId }));
      return written();
    },
    pasteMxN(colIds) {
      reset();
      s.sandbox.visibleCols = colIds.slice();
      s.sandbox.anchorColVisibleIdx = 0;
      s.sandbox.rowId = 'R0';
      // the MxN branch resolves its row ONCE, outside the per-cell block it is sliced from
      s.sandbox.rowNode = { data: { row_id: 'R0', data: {} } };
      colIds.forEach((_, i) => s.sandbox.__pasteMxN('7', i));
      return written();
    },
    clear(colIds) {
      reset();
      s.sandbox.systemCols = ['created_at', 'updated_at', 'row_id', 'id', 'updated_by', '#',
        'is_graph_synced', 'needs_graph_rollback', 'graph_synced_at'];
      colIds.forEach(colId => s.sandbox.__clear({ rowIndex: 0, colId }));
      return written();
    },
    bulkFill(colIds) {
      reset(); s.sandbox.newValue = '7';
      colIds.forEach(colId => s.sandbox.__bulkFill({ rowIndex: 0, colId }));
      return written();
    },
    copyRange(colIds) {
      s.sandbox.minColIdx = 0;
      s.sandbox.maxColIdx = colIds.length - 1;
      return colIds.filter((colId, idx) => s.sandbox.__copyRange(colId, idx));
    },
    copyRows(colIds) {
      return colIds.filter(c => s.sandbox.__copyRows(c));
    }
  };
}

/** The real Gate-4 push arithmetic, untouched by this round and asserted to stay that way. */
function runPushGate(sources) {
  const ctx = vm.createContext(baseGlobals());
  vm.runInContext([
    constFrom(sources.map, 'map_editor.js', 'PUSH_SYSTEM_COLUMNS'),
    fnFrom(sources.map, 'map_editor.js', 'getUnprotectedPushColumns'),
    'globalThis.__g = getUnprotectedPushColumns;'
  ].join('\n\n'), ctx, { filename: 'map_editor.js#gate4' });
  return ctx.__g;
}

// ── scoring ─────────────────────────────────────────────────────────────────────

let quiet = false;
function makeScorer() {
  const st = { pass: 0, fail: 0, failed: [] };
  st.check = (name, actual, expected) => {
    const a = JSON.stringify(actual), e = JSON.stringify(expected);
    if (a === e) { st.pass++; if (!quiet) console.log(`  ok   ${name}`); }
    else {
      st.fail++; st.failed.push(name);
      if (!quiet) console.error(`  FAIL ${name}\n       expected ${e}\n       actual   ${a}`);
    }
  };
  return st;
}

const defOf = (defs, field) => defs.find(d => d.field === field);
const getVal = (def, data) => def.valueGetter({ data, node: { rowIndex: 0 } });

async function suite(sources) {
  const t = makeScorer();
  const { check } = t;

  // [1] loadSchema keeps the list WITHOUT merging it
  const ls = await runLoadSchema(sources, SCHEMA);
  check('1a currentVirtualColumns holds both entries',
    ls.state.currentVirtualColumns.map(v => v.name), ['wafer_id', 'yield_pct']);
  check('1b currentColumns is untouched by the announcement',
    ls.state.currentColumns, STORED);
  // The search dropdown feeds `?cols=` into SQL over the left table. A virtual name there is
  // a search that can only return nothing.
  check('1c search dropdown offers stored columns only',
    ls.offered, ['pkg_id', 'core_lot', 'core_slot', 'bond_count']);

  // [2] an old server (no key at all) must land on `[]`, not `undefined`
  const noKey = { ...SCHEMA };
  delete noKey.virtual_columns;
  const lsOld = await runLoadSchema(sources, noKey);
  check('2a absent key -> []', lsOld.state.currentVirtualColumns, []);
  // and a non-array must not survive: `state.currentVirtualColumns.some(...)` runs inside
  // the write guards, where a throw is the one thing that must not happen.
  const bogus = await runLoadSchema(sources, { ...SCHEMA, virtual_columns: { a: 1 } });
  check('2b non-array key -> []', bogus.state.currentVirtualColumns, []);

  // [3] the defs: stored ones first and unchanged, virtual ones appended
  const defs = runBuildColumnDefs(sources, SCHEMA);
  check('3a row-number column still leads', defs[0].headerName, '#');
  check('3b column order: stored, then virtual',
    defs.slice(1).map(d => d.field), STORED.concat(['wafer_id', 'yield_pct']));
  check('3c checkbox still on the first STORED column',
    [defOf(defs, 'pkg_id').checkboxSelection, !!defOf(defs, 'wafer_id').checkboxSelection],
    [true, false]);
  check('3d virtual defs are not editable',
    [defOf(defs, 'wafer_id').editable, defOf(defs, 'yield_pct').editable], [false, false]);
  check('3e stored data column stays editable', defOf(defs, 'bond_count').editable, true);
  check('3f virtual defs carry no cell editor',
    [defOf(defs, 'wafer_id').cellEditor, defOf(defs, 'yield_pct').cellEditor],
    [undefined, undefined]);
  check('3g virtual defs get the existing read-only class',
    defOf(defs, 'wafer_id').cellClass, 'cell-system-readonly');
  // Filters are SERVER-side here (`fetchData` sends `getFilterModel()` as `?filters=`) and
  // the server drops a condition for a column its model has not got. A filter UI on a virtual
  // column would therefore leave the page unfiltered while the on-screen rows looked filtered.
  check('3h virtual columns offer no filter at all',
    [defOf(defs, 'wafer_id').filter, defOf(defs, 'yield_pct').filter], [false, false]);
  check('3i stored columns keep the filters they had',
    [defOf(defs, 'bond_count').filter, defOf(defs, 'pkg_id').filter],
    ['agNumberColumnFilter', 'agTextColumnFilter']);

  // [4] THE VALUE DOMAIN: a `number` virtual column carrying the unresolved label
  const yieldDef = defOf(defs, 'yield_pct');
  const waferDef = defOf(defs, 'wafer_id');
  check('4a numeric value is displayed as a number',
    getVal(yieldDef, { data: { yield_pct: cell('97.5') } }), 97.5);
  check('4b the label survives verbatim on a NUMBER column',
    getVal(yieldDef, { data: { yield_pct: cell('미상') } }), '미상');
  // The three ways a naive `Number(val)` loses: NaN, and `Number('')`/`Number(null)` === 0.
  check('4c the label is not coerced to NaN or 0',
    [Number.isNaN(getVal(yieldDef, { data: { yield_pct: cell('미상') } })),
     getVal(yieldDef, { data: { yield_pct: cell('미상') } }) === 0], [false, false]);
  check('4d an empty cell does not become 0',
    getVal(yieldDef, { data: { yield_pct: cell('') } }), '');
  check('4e a missing cell (attach failed) does not throw',
    getVal(yieldDef, { data: {} }), '');
  check('4f a string virtual column passes values through',
    getVal(waferDef, { data: { wafer_id: cell('CW-0007') } }), 'CW-0007');

  // [5] the virtual getter and the stored getter are the SAME reader, not two
  // (the parent asked for this to be confirmed rather than assumed)
  const storedNum = defOf(defs, 'bond_count');
  const sameOn = raw => {
    const row = { data: { bond_count: cell(raw), yield_pct: cell(raw) } };
    return [getVal(storedNum, row), getVal(yieldDef, row)];
  };
  ['97.5', '0', '', '미상', 'abc'].forEach(raw => {
    const [a, b] = sameOn(raw);
    check(`5 same reader on ${JSON.stringify(raw)}`, a, b);
  });

  // [6] sorting a number column whose domain contains a string
  const cmp = yieldDef.comparator;
  check('6a a number column installs a comparator', typeof cmp, 'function');
  const sorted = [50, '미상', 10, '미상', 90].slice().sort(cmp);
  check('6b unresolved rows form one block at the end', sorted, [10, 50, 90, '미상', '미상']);
  // The control that makes 6b mean something: AG-Grid's default ending is
  // `a > b ? 1 : a < b ? -1 : 0`, and BOTH are false for (number, string) — every unresolved
  // row ties with every number. Asserted here so a future "the default is fine" is refuted
  // by this file rather than by production.
  const agDefault = (a, b) => (a > b ? 1 : (a < b ? -1 : 0));
  check('6c the default comparator really does tie a number with the label',
    agDefault(50, '미상'), 0);
  check('6d a string virtual column installs none (default is already right)',
    waferDef.comparator, undefined);

  // [7] the header marker and what its tooltip has to answer
  check('7a marker joins the existing header vocabulary',
    [defOf(defs, 'wafer_id').headerName, defOf(defs, 'pkg_id').headerName],
    ['WAFER_ID🔗', 'PKG_ID🗝️']);
  const tip = defOf(defs, 'wafer_id').headerTooltip;
  check('7b tooltip names the right table AND the rule',
    [tip.includes('core_wafer_map'), tip.includes('bonding_log_wafer_id')], [true, true]);

  // [8] malformed / colliding announcements must not become columns
  const junk = { ...SCHEMA, virtual_columns: [{}, { name: '' }, null, VC_WAFER] };
  check('8a malformed entries are dropped, the good one survives',
    runBuildColumnDefs(sources, junk).slice(1).map(d => d.field),
    STORED.concat(['wafer_id']));
  // The server de-duplicates against its own final column list; if a stale state ever gets
  // past that, the STORED def must win — it is the editable, writable, copyable one.
  const collide = { ...SCHEMA, virtual_columns: [{ ...VC_WAFER, name: 'bond_count' }] };
  const cd = runBuildColumnDefs(sources, collide);
  check('8b a name already stored yields no second def',
    cd.slice(1).map(d => d.field), STORED);
  check('8c and that column stays editable', defOf(cd, 'bond_count').editable, true);

  // [9] THE WRITE FUNNELS. Grid presence — not `currentColumns` — is what puts a column in
  // front of these, so not merging the names is NOT what protects them.
  const w = runWriteFunnels(sources, SCHEMA);
  const span = ['core_lot', 'wafer_id', 'bond_count', 'yield_pct'];
  check('9a MxN paste skips virtual columns', w.pasteMxN(span), ['core_lot', 'bond_count']);
  check('9b 1x1 fill skips virtual columns', w.paste1x1(span), ['core_lot', 'bond_count']);
  check('9c delete-to-clear skips virtual columns', w.clear(span), ['core_lot', 'bond_count']);
  check('9d bulk fill skips virtual columns', w.bulkFill(span), ['core_lot', 'bond_count']);
  // The axis is alive: with nothing announced the same span writes everything.
  const w0 = runWriteFunnels(sources, { ...SCHEMA, virtual_columns: [] });
  check('9e with no announcement the same span is fully writable', w0.pasteMxN(span), span);

  // [9f-9g] COPY, the other side of the same coin. These predicates run INSIDE a
  // min..max index window, so a visible column they reject is deleted from the MIDDLE of the
  // copied block and everything to its right shifts one place left — the user gets a
  // rectangle that is not the one they selected, with no message. Rendering the column is
  // what made this predicate load-bearing, so it is scored here rather than assumed.
  check('9f range copy keeps virtual columns in place',
    w.copyRange(['core_lot', 'wafer_id', 'bond_count']), ['core_lot', 'wafer_id', 'bond_count']);
  check('9g row copy keeps them too',
    w.copyRows(['row_id', 'core_lot', 'wafer_id', '#']), ['row_id', 'core_lot', 'wafer_id']);

  // [10] map_editor Gate 4 arithmetic is untouched by the new key
  const gate = runPushGate(sources);
  const bare = { columns: ['pkg_id', 'base', 'x', 'y', 'leg', 'created_at', 'updated_at'],
    business_key: 'pkg_id', composite_key_source: ['base', 'x', 'y'], map_key_columns: ['base'] };
  const announced = { ...bare, virtual_columns: [VC_WAFER, VC_YIELD] };
  check('10a a clean map table stays clean when a join announces columns',
    gate(announced, 'x', 'y', 'leg'), gate(bare, 'x', 'y', 'leg'));
  check('10b and that answer is still the empty list', gate(announced, 'x', 'y', 'leg'), []);
  const dirty = { ...bare, columns: bare.columns.concat(['metro_eqp']), virtual_columns: [VC_WAFER] };
  check('10c a real unprotected column is still named, and only it',
    gate(dirty, 'x', 'y', 'leg'), ['metro_eqp']);

  return t;
}

// ── mutants ─────────────────────────────────────────────────────────────────────

// A mutation that does not apply is a SILENT DISARM: the mutant run is then just the
// baseline, it passes, and the escape is reported as a real one. A mutation that applies
// MORE than once is the same defect wearing the other face — the `1x1 paste` search string
// was a substring of the `MxN` one, so removing one guard removed both and the 1x1 check was
// never the thing being scored. Both are refused here.
const sub = (src, from, to, label, times = 1) => {
  const n = src.split(from).length - 1;
  if (n !== times) {
    die(`mutation "${label}" applies ${n} time(s), expected ${times} — `
      + `${JSON.stringify(from.slice(0, 60))}`);
  }
  return src.split(from).join(to);
};

// DEFECTS: each must be CAUGHT. Every one of them is a thing this round actually decided.
const DEFECTS = [
  ['merge the names into currentColumns', s => ({ ...s,
    api: sub(s.api, 'state.currentColumns = data.columns || [];',
      'state.currentColumns = (data.columns || []).concat((data.virtual_columns || []).map(v => v.name));',
      'merge') })],
  ['announce them as editable', s => ({ ...s,
    grid: sub(s.grid, `      field: col,\n      editable: false,`,
      `      field: col,\n      editable: true,`, 'editable') })],
  ['coerce the unresolved label with a bare Number()', s => ({ ...s,
    grid: sub(s.grid, `    const parsed = Number(val);\n    if (!isNaN(parsed)) {\n      return parsed;\n    }`,
      `    return Number(val);`, 'coerce') })],
  ['drop the guard that keeps Number("") from becoming 0', s => ({ ...s,
    grid: sub(s.grid, `  if (val !== '' && val !== null && val !== undefined) {`,
      `  if (val !== null && val !== undefined) {`, 'empty-guard') })],
  ['fall back to the default sort comparator', s => ({ ...s,
    grid: sub(s.grid, `      ...(isNumeric ? {`, `      ...(false ? {`, 'comparator') })],
  ['offer a filter the server will silently ignore', s => ({ ...s,
    grid: sub(s.grid, `      filter: false,\n      resizable: true,`,
      `      filter: isNumeric ? 'agNumberColumnFilter' : 'agTextColumnFilter',\n      resizable: true,`,
      'filter') })],
  ['let a colliding name produce a second def', s => ({ ...s,
    grid: sub(s.grid, `    if (state.currentColumns.includes(col)) return;`, ``, 'collide') })],
  ['accept a malformed announcement entry', s => ({ ...s,
    grid: sub(s.grid, `    if (!vc || typeof vc.name !== 'string' || vc.name === '') return;`, ``,
      'malformed') })],
  // The trailing line disambiguates the two paste branches, whose guards differ only in
  // indentation (and the shallower one is a substring of the deeper one).
  ['let the MxN paste target a virtual column', s => ({ ...s,
    clipboard: sub(s.clipboard,
      `            if (isVirtualColumn(colId)) return;\n\n            if (!updateMapByRow[rowId]) {`,
      `            if (!updateMapByRow[rowId]) {`, 'paste-mxn') })],
  ['let the 1x1 fill target a virtual column', s => ({ ...s,
    clipboard: sub(s.clipboard,
      `          if (isVirtualColumn(colId)) return;\n\n          const rowNode = state.gridApi.getDisplayedRowAtIndex(rowIndex);`,
      `          const rowNode = state.gridApi.getDisplayedRowAtIndex(rowIndex);`, 'paste-1x1') })],
  ['let delete-to-clear target a virtual column', s => ({ ...s,
    clipboard: sub(s.clipboard, `    if (isVirtualColumn(cell.colId)) return;`, ``, 'clear') })],
  ['let the bulk fill target a virtual column', s => ({ ...s,
    ui: sub(s.ui, `    if (isVirtualColumn(colId)) return;`, ``, 'bulk-fill') })],
  ['make the push gate count announced columns', s => ({ ...s,
    map: sub(s.map, `  const cols = Array.isArray(schema && schema.columns) ? schema.columns : [];`,
      `  const cols = (Array.isArray(schema && schema.columns) ? schema.columns : [])\n`
      + `    .concat((Array.isArray(schema && schema.virtual_columns) ? schema.virtual_columns : []).map(v => v.name));`,
      'push-gate') })],
  ['drop a virtual column out of the middle of a copied range', s => ({ ...s,
    clipboard: sub(s.clipboard,
      `    return state.currentColumns.includes(colId)\n      || isVirtualColumn(colId)\n`,
      `    return state.currentColumns.includes(colId)\n`, 'copy-range') })],
  ['drop it out of a row copy', s => ({ ...s,
    clipboard: sub(s.clipboard,
      `      return state.currentColumns.includes(c)\n        || isVirtualColumn(c)\n`,
      `      return state.currentColumns.includes(c)\n`, 'copy-rows') })],
  ['accept a non-array virtual_columns straight into state', s => ({ ...s,
    api: sub(s.api, `Array.isArray(data.virtual_columns) ? data.virtual_columns : []`,
      `data.virtual_columns || []`, 'non-array') })]
];

// CONTROLS: each must ESCAPE. If one is caught, a check is reading source text.
// Locals only, and deliberately NOT the names this file extracts by (`rawCellValue`,
// `numericDisplayValue`, `buildColumnDefs`, `loadSchema`, `getUnprotectedPushColumns`,
// `isVirtualColumn`) — renaming an extraction anchor is not a control, it is the anchor
// moving, and this harness answers that with exit 2 rather than with a verdict.
const RENAMES = [
  [/\bvc\b/g, 'entry'], [/\bisNumeric\b/g, 'numericType'],
  [/\bunresolved\b/g, 'labelText'], [/\bvirt\b/g, 'joinMeta']
];
const stripComments = src => src.split('\n').filter(l => !/^\s*\/\//.test(l)).join('\n');

const CONTROLS = [
  ['consistent rename of locals across every sliced module', s => {
    const r = t => RENAMES.reduce((acc, [re, to]) => acc.replace(re, to), t);
    return { state: r(s.state), api: r(s.api), grid: r(s.grid),
      clipboard: r(s.clipboard), ui: r(s.ui), map: s.map };
  }],
  ['every full-line comment stripped from every sliced module', s => ({
    state: stripComments(s.state), api: stripComments(s.api), grid: stripComments(s.grid),
    clipboard: stripComments(s.clipboard), ui: stripComments(s.ui), map: stripComments(s.map)
  })]
];

// ── run ─────────────────────────────────────────────────────────────────────────

const base = await suite(PRISTINE);
console.log(`\n[baseline] ${base.pass} passed, ${base.fail} failed`);

let caught = 0, escaped = 0;
const escapedNames = [];
console.log(`\n── defect mutants (each must be CAUGHT) ────────────────────────────`);
quiet = true;
for (const [name, mutate] of DEFECTS) {
  let r;
  try { r = await suite(mutate(PRISTINE)); }
  catch (e) { r = { fail: 1, failed: [`threw: ${e && e.message}`] }; }
  if (r.fail > 0) { caught++; console.log(`  caught  ${name}  (${r.failed[0]})`); }
  else { escaped++; escapedNames.push(name); console.log(`  ESCAPED ${name}`); }
}

let controlsCaught = 0;
const controlsCaughtNames = [];
console.log(`\n── control mutants (each must ESCAPE) ──────────────────────────────`);
for (const [name, mutate] of CONTROLS) {
  let r;
  try { r = await suite(mutate(PRISTINE)); }
  catch (e) { r = { fail: 1, failed: [`threw: ${e && e.message}`] }; }
  if (r.fail === 0) console.log(`  escaped ${name}`);
  else { controlsCaught++; controlsCaughtNames.push(`${name} (${r.failed[0]})`); console.log(`  CAUGHT  ${name}  (${r.failed[0]})`); }
}
quiet = false;

if (escapedNames.length) console.error(`\ndefects that escaped:\n  ${escapedNames.join('\n  ')}`);
if (controlsCaughtNames.length) console.error(`\ncontrols that were caught (a check is reading source text):\n  ${controlsCaughtNames.join('\n  ')}`);

const bad = base.fail + escaped + controlsCaught;
console.log(`\n${base.pass} passed, ${base.fail} failed; `
  + `${caught}/${DEFECTS.length} defects caught, ${escaped} escaped; `
  + `${CONTROLS.length - controlsCaught}/${CONTROLS.length} controls escaped.`);
process.exit(bad ? 1 : 0);
