// Harness — rendering `/schema`'s `virtual_columns` in the grid, the four write funnels that
// must NOT offer them, and (2026-07-31) which columns `/schema`'s `join_resolved_columns`
// takes `Blank`/`Not blank` away from.
//
// TWO ANNOUNCEMENTS, TWO QUESTIONS, AND THE SECOND IS WIDER. `virtual_columns` says "add this
// column"; `join_resolved_columns` says "the server resolves this column's value through a
// join". They differ on `kind: 'collide'` — a STORED, editable column that `isVirtualColumn`
// answers NO for and whose filter the server nonetheless evaluates against the joined
// COALESCE. Both kinds are fixtured below, because a client that keys the filter off the
// first announcement is silently wrong about every collide column.
// Run: node client2/tests/virtual_column_render_harness.mjs   (no node_modules — vm sandbox)
//
// WHAT IT SCORES. The REAL `loadSchema` (api.js), the REAL `buildColumnDefs` (grid.js), the
// REAL `getUnprotectedPushColumns` (push_columns.js — IMPORTED, not sliced; see `runPushGate`)
// and the REAL per-cell decision blocks of
// the four client write funnels (clipboard.js x3, ui.js x1), all lifted verbatim out of the
// source and evaluated in a vm sandbox — the same technique as
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
// `push` replaced `map: read('map_editor.js')`: the only thing this harness ever took from
// that file was Gate 4, and Gate 4 now lives in its own module. This file therefore no longer
// reads `map_editor.js` at all -- one fewer harness holding a text anchor into it.
const PRISTINE = {
  state: read('state.js'),
  api: read('api.js'),
  grid: read('grid.js'),
  clipboard: read('clipboard.js'),
  ui: read('ui.js'),
  push: read('push_columns.js')
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

// `join_resolved_columns` — the WIDER announcement: which columns the SERVER resolves
// through a join. It covers BOTH kinds, and covering both here is the point:
//
//   `virtual_only`  wafer_id, yield_pct — also in `virtual_columns`, built by the appended
//                   loop, read-only.
//   `collide`       core_lot, core_slot — STORED columns, in `currentColumns`, built by the
//                   ordinary loop, fully editable and writable, and NOT in
//                   `virtual_columns` at all. `isVirtualColumn` says no to these, which is
//                   exactly why the filter cannot be keyed off it.
//
// 🔴 THREE DIFFERENT LABELS ON PURPOSE. `unresolved_label` rides per declaration. If any
// site reads the first entry's label, or hardcodes '미상', the per-entry checks below go red.
const JRC_WAFER = { name: 'wafer_id', kind: 'virtual_only', rule: 'bonding_log_wafer_id',
  right_table: 'core_wafer_map', unresolved_label: '미상' };
const JRC_YIELD = { name: 'yield_pct', kind: 'virtual_only', rule: 'bonding_log_yield',
  right_table: 'core_wafer_map', unresolved_label: '미상' };
const JRC_LOT = { name: 'core_lot', kind: 'collide', rule: 'bonding_log_lot',
  right_table: 'core_wafer_map', unresolved_label: 'NO-LOT' };
const JRC_SLOT = { name: 'core_slot', kind: 'collide', rule: 'bonding_log_slot',
  right_table: 'core_wafer_map', unresolved_label: '슬롯미정' };

// The six AG-Grid text options that survive on a join-resolved column. Written out rather
// than imported: this file is the independent oracle, so deriving it from the constant under
// test would make it agree with itself.
const TRIMMED = ['contains', 'notContains', 'equals', 'notEqual', 'startsWith', 'endsWith'];

const SCHEMA = {
  table_name: 'bonding_log',
  columns: STORED.slice(),
  column_types: { pkg_id: 'string', core_lot: 'string', core_slot: 'number', bond_count: 'number' },
  business_key: 'pkg_id',
  composite_key_source: [],
  map_key_columns: [],
  map_push_ok: false,
  virtual_columns: [VC_WAFER, VC_YIELD],
  join_resolved_columns: [JRC_WAFER, JRC_YIELD, JRC_LOT, JRC_SLOT]
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

/** The real `loadSchema`, fed a stubbed `fetch`. Records what the search dropdown was offered.
 *
 * `offered` is the VALUE (what reaches `?cols=`) and `labels` the visible text, kept apart on
 * purpose: they are allowed to differ (the 🔗 marker rides the label), and a check that read
 * only one of them could not tell a decorated label from a corrupted column name. */
async function runLoadSchema(sources, response) {
  const offered = [];
  const labels = [];
  const s = withState(sources, {
    API_BASE: '/api',
    resetSuggestLearning: () => {},
    fetch: async () => ({ json: async () => response })
  });
  s.sandbox.elements = {
    performanceLog: { textContent: '' },
    searchCols: {
      innerHTML: '',
      appendChild: o => { offered.push(o.value); labels.push(o.textContent); }
    }
  };
  s.sandbox.document.createElement = () => ({ value: '', textContent: '' });
  vm.runInContext(fnFrom(sources.api, 'api.js', 'loadSchema')
    + '\n;globalThis.__loadSchema = loadSchema;', s.ctx, { filename: 'api.js#loadSchema' });
  await s.sandbox.__loadSchema('bonding_log');
  return { state: s.state, offered, labels };
}

/** The real `buildColumnDefs`, with the schema already in state. */
function runBuildColumnDefs(sources, schema, fillTargets = [['core_lot', '①'], ['core_slot', '②']]) {
  const s = withState(sources);
  Object.assign(s.state, {
    currentColumns: schema.columns.slice(),
    currentColumnTypes: schema.column_types,
    currentBusinessKey: schema.business_key,
    currentCompositeKeySources: schema.composite_key_source,
    currentVirtualColumns: schema.virtual_columns,
    currentJoinResolvedColumns: schema.join_resolved_columns || [],
    viewMode: 'pagination', allDataLoaded: true, currentSkip: 0, pendingTxEdits: {}
  });
  s.sandbox.isCellInRange = () => false;
  s.sandbox.SuggestCellEditor = function () {};
  // `buildColumnDefs` now asks the reference panel which columns the paste fills. That module
  // is not sliced in here (it owns async rule state), so the harness SUPPLIES the answer --
  // and supplies a non-empty one, because a stub returning nothing would leave the ①②
  // decoration unwalked and this harness green whatever it did.
  s.sandbox.fillTargetOrdinals = () => new Map(fillTargets);
  // `joinResolvedColumn` is NOT lifted here — it comes from the real state.js that
  // `withState` already ran, so the predicate under test is the shipped one.
  vm.runInContext([
    fnFrom(sources.grid, 'grid.js', 'rawCellValue'),
    fnFrom(sources.grid, 'grid.js', 'numericDisplayValue'),
    constFrom(sources.grid, 'grid.js', 'JOIN_RESOLVED_FILTER_OPTIONS'),
    fnFrom(sources.grid, 'grid.js', 'joinResolvedFilterDef'),
    // `buildColumnDefs` ends by delegating the mockup's column order and widths, so the
    // helper and its table have to come into the sandbox with it. Without them the slice
    // throws ReferenceError rather than scoring anything — which is how this harness
    // reported the change, loudly, instead of going quietly green.
    constFrom(sources.grid, 'grid.js', 'MOCKUP_COLUMN_LAYOUT'),
    fnFrom(sources.grid, 'grid.js', 'applyMockupLayout'),
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
    // Set so the funnels run with the announcement PRESENT. `core_lot` is announced
    // `collide` and must still be written: if anyone ever wires this list into a write
    // guard, 9a-9d go red here instead of in production. (`crud.refuse_virtual_join_columns`
    // is the refusal; this list is a UI marker and must never become a second one.)
    currentJoinResolvedColumns: schema.join_resolved_columns || [],
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
      // Mirrors crud.py's write-path skip list, which lost the three graph-sync names
      // on 2026-08-31 along with the branch that wrote them.
      s.sandbox.systemCols = ['created_at', 'updated_at', 'row_id', 'id', 'updated_by', '#'];
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

/**
 * The real Gate-4 push arithmetic, untouched by this round and asserted to stay that way.
 *
 * 🔴 IMPORTED, NOT SLICED. It used to be cut out of `map_editor.js` as text and re-run in a
 *    `vm` sandbox, which every other extraction here still has to do, because those functions
 *    read module globals. Gate 4 never did -- it takes a schema and three column names and
 *    returns a list -- so it now lives in `client2/src/push_columns.js` and is imported.
 *    What that buys is written down in the module's header; what it costs this file is
 *    nothing, because the mutant below still reaches it: the module's TEXT is imported as a
 *    `data:` URL, so `push` behaves exactly like the other entries in `sources`.
 *
 * ⚠️ The module must stay import-free for this to work -- a relative specifier cannot resolve
 *    inside a `data:` URL. If it ever gains one, this stops loading and every mutant becomes a
 *    throw, which scores as a kill.
 */
async function runPushGate(sources) {
  const url = 'data:text/javascript;base64,' + Buffer.from(sources.push, 'utf8').toString('base64');
  const mod = await import(url);
  return mod.getUnprotectedPushColumns;
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
// Safe: a def with NO filterParams is a real, expected answer (an unannounced column), so
// reaching through it must report a comparison rather than throw. A mutant that removes the
// options should be caught by a named check, not by an exception whose message says nothing
// about which decision broke.
const optsOf = def => (def && def.filterParams && def.filterParams.filterOptions) || null;
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
  // The search dropdown feeds `?cols=`, which the server scopes with the SAME binder
  // vocabulary it announces as `join_resolved_columns` — so every announced name is
  // searchable and belongs here. Stored columns keep their order and lead; the announced
  // names that are NOT already stored follow.
  check('1d search dropdown offers stored columns, then the announced ones',
    ls.offered, ['pkg_id', 'core_lot', 'core_slot', 'bond_count', 'wafer_id', 'yield_pct']);
  // 🔴 THE DE-DUPLICATION, which is the whole reason the wider announcement cannot be
  // appended wholesale. `core_lot`/`core_slot` are `collide` — STORED columns that the
  // announcement also names. Offering them twice would put two identical options in the
  // select that build the identical query.
  check('1e no name is offered twice',
    ls.offered.length, new Set(ls.offered).size);
  // 🔴 NEVER FABRICATED. An old server that announces nothing must get the pre-change
  // dropdown, not a client-invented list: a name the server has no expression for is
  // refused with 400, so inventing one would break search outright rather than widen it.
  const noJrcOffered = { ...SCHEMA };
  delete noJrcOffered.join_resolved_columns;
  check('1f absent announcement -> stored columns only',
    (await runLoadSchema(sources, noJrcOffered)).offered,
    ['pkg_id', 'core_lot', 'core_slot', 'bond_count']);
  check('1g empty announcement -> stored columns only',
    (await runLoadSchema(sources, { ...SCHEMA, join_resolved_columns: [] })).offered,
    ['pkg_id', 'core_lot', 'core_slot', 'bond_count']);
  // A malformed entry must be skipped, not turned into an option whose value is `undefined`.
  check('1h malformed announcement entries are skipped',
    (await runLoadSchema(sources, { ...SCHEMA,
      join_resolved_columns: [null, { kind: 'virtual_only' }, { name: '' }, JRC_WAFER] })).offered,
    ['pkg_id', 'core_lot', 'core_slot', 'bond_count', 'wafer_id']);
  // The VALUE is what reaches `?cols=`; the 🔗 marker rides the label only. A marker that
  // leaked into the value would be sent to the server as part of the column name.
  check('1i offered values carry no decoration',
    ls.offered.every(v => typeof v === 'string' && !v.includes('🔗')), true);
  // And the label DOES mark the joined ones — a stored column must not be dressed as joined,
  // which would tell an operator a writable column is read-only.
  check('1j only the join-resolved names are marked 🔗',
    ls.labels.filter(l => l.includes('🔗')), ['wafer_id 🔗', 'yield_pct 🔗']);

  // [2] an old server (no key at all) must land on `[]`, not `undefined`
  const noKey = { ...SCHEMA };
  delete noKey.virtual_columns;
  const lsOld = await runLoadSchema(sources, noKey);
  check('2a absent key -> []', lsOld.state.currentVirtualColumns, []);
  // and a non-array must not survive: `state.currentVirtualColumns.some(...)` runs inside
  // the write guards, where a throw is the one thing that must not happen.
  const bogus = await runLoadSchema(sources, { ...SCHEMA, virtual_columns: { a: 1 } });
  check('2b non-array key -> []', bogus.state.currentVirtualColumns, []);
  // Same discipline on the second announcement, and it matters MORE here: `[]` is what makes
  // the client fall back to the pre-change behaviour instead of enabling a filter against a
  // server that cannot honour it.
  check('2c join_resolved_columns is kept verbatim',
    ls.state.currentJoinResolvedColumns.map(e => `${e.name}:${e.kind}`),
    ['wafer_id:virtual_only', 'yield_pct:virtual_only', 'core_lot:collide', 'core_slot:collide']);
  const noJrc = { ...SCHEMA };
  delete noJrc.join_resolved_columns;
  check('2d absent join_resolved_columns -> []',
    (await runLoadSchema(sources, noJrc)).state.currentJoinResolvedColumns, []);
  check('2e non-array join_resolved_columns -> []',
    (await runLoadSchema(sources, { ...SCHEMA, join_resolved_columns: { a: 1 } }))
      .state.currentJoinResolvedColumns, []);

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
  check('3e2 fill targets wear the ordinal and the header class',
    [defOf(defs, 'core_lot').headerName, defOf(defs, 'core_lot').headerClass,
     defOf(defs, 'bond_count').headerName, defOf(defs, 'bond_count').headerClass],
    ['CORE_LOT ①', 'fill-target-header', 'BOND_COUNT', undefined]);
  check('3f virtual defs carry no cell editor',
    [defOf(defs, 'wafer_id').cellEditor, defOf(defs, 'yield_pct').cellEditor],
    [undefined, undefined]);
  check('3g virtual defs get the existing read-only class',
    defOf(defs, 'wafer_id').cellClass, 'cell-system-readonly');
  // ── [3h-3n] THE FILTER, which is what `join_resolved_columns` exists to decide ──────
  //
  // Filters here are SERVER-side (`fetchData` sends `getFilterModel()` as `?filters=`). The
  // server now resolves an announced column through `resolved_expression` and passes it as
  // `col_expr_override`, so a filter on one of these names genuinely narrows the query.
  check('3h announced virtual columns are FILTERABLE, as text',
    [defOf(defs, 'wafer_id').filter, defOf(defs, 'yield_pct').filter],
    ['agTextColumnFilter', 'agTextColumnFilter']);
  // `yield_pct` is declared `number`. It still gets the TEXT filter, because the server
  // documents that an override "is always treated as text" and casts it to String — a
  // numeric filter would send `greaterThan`/`inRange` and get lexical string comparison back.
  check('3h2 a number-declared virtual column gets text, NOT agNumberColumnFilter',
    defOf(defs, 'yield_pct').filter !== 'agNumberColumnFilter', true);
  check('3h3 blank/notBlank are gone from an announced virtual column',
    [optsOf(defOf(defs, 'wafer_id')), optsOf(defOf(defs, 'yield_pct'))], [TRIMMED, TRIMMED]);

  // The other half, and the failure mode worth naming: removing them from the WRONG set.
  // An unannounced stored column keeps AG-Grid's full default option list, which includes
  // Blank / Not blank — there it is a real question with a real answer.
  check('3i unannounced stored columns keep the filters they had',
    [defOf(defs, 'bond_count').filter, defOf(defs, 'pkg_id').filter],
    ['agNumberColumnFilter', 'agTextColumnFilter']);
  check('3i2 and keep the FULL option set (no filterParams -> AG-Grid defaults)',
    [defOf(defs, 'bond_count').filterParams, defOf(defs, 'pkg_id').filterParams],
    [undefined, undefined]);

  // [3j-3k] THE COLLIDE KIND. These are STORED columns: `isVirtualColumn` says no, they are
  // absent from `virtual_columns` entirely, and the ordinary column loop builds them. Only
  // the filter changes — a client that keys this off `isVirtualColumn` misses them silently.
  check('3j a collide column gets the trimmed text filter',
    [defOf(defs, 'core_lot').filter, optsOf(defOf(defs, 'core_lot'))],
    ['agTextColumnFilter', TRIMMED]);
  check('3j2 and is NOT in virtual_columns, so isVirtualColumn cannot reach it',
    SCHEMA.virtual_columns.some(v => v.name === 'core_lot'), false);
  // 🔴 The announcement is a UI marker, never a write guard. A collide column's value really
  // is stored, so it stays editable and keeps its numeric editor and its validation.
  check('3k a collide column stays EDITABLE',
    [defOf(defs, 'core_lot').editable, defOf(defs, 'core_slot').editable], [true, true]);
  check('3k2 a number collide column keeps its numeric CELL EDITOR while its filter is text',
    [defOf(defs, 'core_slot').cellEditor, defOf(defs, 'core_slot').filter],
    ['agNumberCellEditor', 'agTextColumnFilter']);

  // [3l] OLD SERVER. `virtual_columns` present, `join_resolved_columns` absent — a
  // pre-change server, which drops the condition and answers with an UNFILTERED page. The
  // old `filter: false` is the only honest answer there and must come back on its own.
  const oldServer = { ...SCHEMA };
  delete oldServer.join_resolved_columns;
  const oldDefs = runBuildColumnDefs(sources, oldServer);
  check('3l no announcement -> virtual columns go back to no filter at all',
    [defOf(oldDefs, 'wafer_id').filter, defOf(oldDefs, 'yield_pct').filter], [false, false]);
  check('3l2 and a stored column is untouched by the absence',
    [defOf(oldDefs, 'core_lot').filter, defOf(oldDefs, 'core_lot').filterParams],
    ['agTextColumnFilter', undefined]);

  // [3m-3n] THE LABEL IS PER DECLARATION. A site that renames it in config must see the new
  // name on screen, so nothing may hardcode '미상' or reuse the first entry's label.
  const tipOf = (d, f) => defOf(d, f).headerTooltip;
  check('3m each column carries ITS OWN label, not the first entry\'s',
    [tipOf(defs, 'wafer_id').includes('미상'), tipOf(defs, 'core_lot').includes('NO-LOT'),
     tipOf(defs, 'core_slot').includes('슬롯미정'), tipOf(defs, 'core_lot').includes('미상')],
    [true, true, true, false]);
  // The behavioural anti-hardcode test: change the labels in the fixture and the screen has
  // to follow. A literal '미상' in the source passes 3m and fails this.
  const renamedLabels = { ...SCHEMA, join_resolved_columns: SCHEMA.join_resolved_columns
    .map(e => ({ ...e, unresolved_label: `LBL-${e.name}` })) };
  const renamedDefs = runBuildColumnDefs(sources, renamedLabels);
  check('3n renaming the label in config moves it on screen',
    [tipOf(renamedDefs, 'wafer_id').includes('LBL-wafer_id'),
     tipOf(renamedDefs, 'core_lot').includes('LBL-core_lot'),
     tipOf(renamedDefs, 'wafer_id').includes('미상')],
    [true, true, false]);
  // A malformed/missing label must not print 'undefined' at the operator.
  const noLabel = { ...SCHEMA,
    join_resolved_columns: [{ name: 'wafer_id', kind: 'virtual_only' }] };
  const noLabelDefs = runBuildColumnDefs(sources, noLabel);
  check('3n2 a label-less entry still filters, and says nothing rather than "undefined"',
    [defOf(noLabelDefs, 'wafer_id').filter,
     tipOf(noLabelDefs, 'wafer_id').includes('undefined')],
    ['agTextColumnFilter', false]);

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

  // [10] Gate 4 arithmetic is untouched by the new key
  const gate = await runPushGate(sources);
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
  // ── the 2026-07-31 round: which columns lose blank/notBlank, and on whose say-so ──────
  ['leave blank/notBlank on a join-resolved column', s => ({ ...s,
    grid: sub(s.grid, `    filterParams: { filterOptions: JOIN_RESOLVED_FILTER_OPTIONS },\n`, ``,
      'keep-blank') })],
  // Both kinds, because the numeric hazard is identical on each: the server casts the
  // override to String, so a numeric predicate would be answered lexically.
  ['use a number filter on a numeric join-resolved column', s => ({ ...s,
    grid: sub(sub(s.grid,
      `      ...filterDef,\n      resizable: true,`,
      `      ...filterDef,\n      ...(isNumeric ? { filter: 'agNumberColumnFilter' } : {}),\n      resizable: true,`,
      'number-filter-virtual'),
      `      Object.assign(colDef, joinResolvedFilterDef(resolvedEntry, headerLabel));`,
      `      Object.assign(colDef, joinResolvedFilterDef(resolvedEntry, headerLabel));\n`
      + `      if (colType === 'number') colDef.filter = 'agNumberColumnFilter';`,
      'number-filter-stored') })],
  // The exact error the brief warned about: `isVirtualColumn` cannot see a collide column.
  ['key the filter off isVirtualColumn instead of the announcement', s => ({ ...s,
    grid: sub(s.grid, `    const resolvedEntry = joinResolvedColumn(col);\n\n    const colDef = {`,
      `    const resolvedEntry = null;\n\n    const colDef = {`, 'wrong-predicate') })],
  ['enable the filter even when the server never announced it', s => ({ ...s,
    grid: sub(s.grid, `    const filterDef = resolvedEntry\n      ? joinResolvedFilterDef(resolvedEntry, baseTooltip)\n      : { filter: false, floatingFilter: false, headerTooltip: baseTooltip };`,
      `    const filterDef = joinResolvedFilterDef(resolvedEntry || vc, baseTooltip);`,
      'old-server') })],
  ['hardcode the unresolved label instead of reading the entry', s => ({ ...s,
    grid: sub(s.grid, `    ? entry.unresolved_label : '';`, `    ? '미상' : '미상';`, 'hardcode') })],
  // 🔴 The design line the brief drew: this marker must never become a write guard.
  ['make the announcement decide editability', s => ({ ...s,
    grid: sub(s.grid, `      editable: !isSystem,`,
      `      editable: !isSystem && !resolvedEntry,`, 'write-guard') })],
  ['let the announcement replace the numeric cell editor', s => ({ ...s,
    grid: sub(s.grid, `    if (colType === 'number') {\n      colDef.cellEditor = 'agNumberCellEditor';`,
      `    if (colType === 'number' && !resolvedEntry) {\n      colDef.cellEditor = 'agNumberCellEditor';`,
      'editor') })],
  ['accept a non-array join_resolved_columns straight into state', s => ({ ...s,
    api: sub(s.api, `Array.isArray(data.join_resolved_columns)\n      ? data.join_resolved_columns : []`,
      `data.join_resolved_columns || []`, 'non-array-jrc') })],
  // ── the search dropdown (N4) ──────────────────────────────────────────────────
  // The regression: back to stored columns only, which is what this file asserted before
  // the server learned to scope `?cols=` by the announcement.
  ['drop the announced columns from the search dropdown', s => ({ ...s,
    api: sub(s.api, `        if (state.currentColumns.includes(entry.name)) return;\n        appendOption(entry.name, true);`,
      `        return;`, 'dropdown-stored-only') })],
  // Appending the WIDER announcement wholesale: every `collide` name is offered a second time.
  ['offer the announcement without differencing it against stored columns', s => ({ ...s,
    api: sub(s.api, `        if (state.currentColumns.includes(entry.name)) return;\n`, ``,
      'dropdown-dup') })],
  // Fabricating the list instead of reading the announcement — the exact thing the brief
  // forbade. `virtual_columns` is the NARROWER key and is the convenient wrong read.
  ['build the dropdown from virtual_columns instead of the announcement', s => ({ ...s,
    api: sub(s.api, `      state.currentJoinResolvedColumns.forEach(entry => {`,
      `      state.currentVirtualColumns.forEach(entry => {`, 'dropdown-wrong-list') })],
  // A malformed entry becoming an option whose value is `undefined`.
  ['let a malformed announcement entry reach the dropdown', s => ({ ...s,
    api: sub(s.api, `        if (!entry || typeof entry.name !== 'string' || entry.name === '') return;\n`,
      ``, 'dropdown-malformed') })],
  // The decoration leaking into the value, i.e. into `?cols=`.
  ['put the 🔗 marker in the option value rather than the label', s => ({ ...s,
    api: sub(s.api, `        option.value = col;`, `        option.value = joined ? \`\${col} 🔗\` : col;`,
      'dropdown-marker-in-value') })],
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
    push: sub(s.push, `  const cols = Array.isArray(schema && schema.columns) ? schema.columns : [];`,
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
      clipboard: r(s.clipboard), ui: r(s.ui), push: s.push };
  }],
  ['every full-line comment stripped from every sliced module', s => ({
    state: stripComments(s.state), api: stripComments(s.api), grid: stripComments(s.grid),
    clipboard: stripComments(s.clipboard), ui: stripComments(s.ui), push: stripComments(s.push)
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
// H1 protocol: the runner reads this line to tell "red with N assertions" from a crash.
console.log(`ASSERTIONS ${base.pass + base.fail} ${base.fail}`);
process.exit(bad ? 1 : 0);
