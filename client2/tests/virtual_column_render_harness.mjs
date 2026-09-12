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
// Run: node client2/tests/virtual_column_render_harness.mjs
//
// WHAT IT SCORES. The REAL `loadSchema` (api.js), the REAL `buildColumnDefs` (grid.js), the REAL
// `getUnprotectedPushColumns` (push_columns.js) and the REAL write funnels -- the paste and copy
// handlers `setupClipboardHandlers` registers, plus `clearSelectedCells` and
// `applyValueToSelectedRange`. All of them IMPORTED, driven on a stub page, and asked the one
// question this file exists for: which columns reached the request.
//
// 🔴 C-88, 2026-09-13: IT USED TO CUT THEM OUT AS TEXT AND RUN THE PIECES IN `vm`. The owner's
// standing rule is 「잘라쓰기 하니스 절대 금지」 and the reason this file recorded for the
// exception -- 「those modules import config.js, which touches window at module scope, so they
// cannot be imported in node」 -- had stopped being true: `config.js` is guarded and its own
// comment warns against putting the bare read back. The cost of the slice was measured twice in
// two days: it went RED on correct code (C-85's new helper was an unbound name in the sandbox,
// C-84 moved a mutation anchor), which is the disease the ban describes -- a harness scoring the
// shape of the letters instead of the behaviour. The numbers did not move across the conversion:
// 66 assertions, 28 defect mutants, 2 controls, same expectations.
//
// THE FIXTURE IS THE ANNOUNCEMENT. There is no live `server/config/virtual_join_rules.json`
// on this box (only `.sample`), so nothing announces anything here and a harness that read the
// real config would score an empty list and pass vacuously. The schema RESPONSE is therefore
// supplied by the harness itself, shaped from the sample declaration
// (`bonding_log` <- `core_wafer_map`, expose `wafer_id`, label `미상`) plus a `number`-typed
// sibling — because a `number` virtual column carrying a string is the whole point.
//
// EVERY CHECK IS PAIRED WITH A MUTANT. Each defect mutant names ONE FILE; the probe builds a
// whole module from it (byte-identical copy + appended probe), so a mutant that fails to parse
// fails loudly rather than scoring as caught. CONTROL mutants (a consistent rename of locals, and
// stripping every comment line) must ESCAPE: if a control is caught, some check is reading source
// text rather than behaviour, and its green means nothing.
//
// 🔴 A MUTATION WHOSE ANCHOR HAS ROTTED STOPS THE RUN (exit 2) instead of reading as a pass --
// `sub()` counts its occurrences and dies on anything but the expected number.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { loadWithProbe } from './lib/probe.mjs';
import { makeDoc, makeNode } from './lib/board_dom.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..', '..');
const SRC = join(ROOT, 'client2', 'src');

function die(msg) {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  process.exit(2);
}

// ── the page these modules run on ───────────────────────────────────────────────
//
// 🔴 ONE DOCUMENT, GLOBAL, because that is what `dom.js` reads. The modules take their
//    elements from `document.getElementById`, so a stub handed in as a parameter would be a
//    second page nobody looks at.
const doc = makeDoc('light');
const nodes = new Map();
const listeners = new Map();
doc.getElementById = (id) => {
  if (!nodes.has(id)) nodes.set(id, makeNode(doc, 'div'));
  return nodes.get(id);
};
doc.querySelector = () => null;
doc.querySelectorAll = () => [];
doc.addEventListener = (type, fn) => {
  if (!listeners.has(type)) listeners.set(type, []);
  listeners.get(type).push(fn);
};
doc.removeEventListener = () => {};
doc.activeElement = null;
doc.hidden = false;
globalThis.document = doc;
globalThis.alert = () => {};
// `clipboard.js` asks `e.target instanceof Element` to tell a sidebar copy from a grid copy.
// Node has no `Element`, and a missing global would throw INSIDE the handler -- so the class
// exists and this harness's fake events are deliberately not instances of it, which is the
// truthful answer for an event that did not come from the reference sidebar.
globalThis.Element = class Element {};

// ── the server, as far as these paths reach it ──────────────────────────────────
//
// Every write funnel PUTs to `/tables/<t>/data/updates` with `{updates: [{row_id, updates}]}`,
// so 「which columns reached the batch」 is read off the REQUEST rather than off a sliced
// block's local variable. That is the whole point of the conversion: the question is now asked
// of the code that runs.
let schemaBody = null;
let writes = [];
globalThis.fetch = async (url, opts = {}) => {
  const method = String(opts.method || 'GET').toUpperCase();
  if (method !== 'GET' && opts && typeof opts.body === 'string') {
    try { writes.push(JSON.parse(opts.body)); } catch (e) { /* not ours */ }
  }
  return {
    ok: true, status: 200,
    json: async () => (String(url).endsWith('/schema') ? schemaBody : { data: [], total: 0 }),
    text: async () => '',
  };
};
const writtenColumns = () => {
  const out = [];
  for (const body of writes) {
    for (const row of (body && body.updates) || []) {
      for (const col of Object.keys((row && row.updates) || {})) {
        if (!out.includes(col)) out.push(col);
      }
    }
  }
  return out;
};

// ── the modules under test ──────────────────────────────────────────────────────
//
// 🔴 C-88. THIS FILE USED TO CUT ITS SUBJECTS OUT AS TEXT AND RUN THEM IN `vm`. The owner's
//    standing rule is 「잘라쓰기 하니스 절대 금지」, and the reason this file gave for it --
//    「config.js touches window at module scope, so node cannot import these」 -- had stopped
//    being true: `config.js` is guarded (`typeof window !== 'undefined'`) and its own comment
//    warns against putting the bare read back. Two harnesses landed in the meantime that import
//    `grid.js` whole. The slice measured the SHAPE OF THE LETTERS: it went red twice in two days
//    on CORRECT code (a new helper name, a moved mutation anchor), which is the disease.
//
// A mutant is now a WHOLE module (`lib/probe.mjs`: byte-identical copy + appended probe), so a
// mutant that fails to parse fails loudly instead of scoring as caught.
//
// 🔵 THAT WALL IS OPEN (C-91, 판정 346). A probe copy of `state.js` does carry its own `state`
//    object -- measured -- but the other subjects can be POINTED AT IT: `spec.stubs` overrides the
//    names a subject imports from `./state.js`, and an explicit export beats the stub's `export *`.
//    So the controls now cover SIX files. The mechanism was in `probe.mjs` the whole time; what was
//    missing was this composition, which is the same finding C-93 made about the board loaders --
//    twice in one night, 「there is no mechanism」 turned out to mean 「nobody had used it」.
// ⚠️ THE STUB LIST IS PER SUBJECT, and that is not ceremony: `probe.mjs` REFUSES a stub for a name
//    the subject does not import, because a stub nobody reads is a harness believing it intervened.
//    Measured: `grid.js` does not import `isVirtualColumn`, and the refusal said so by name.
const FILE = {
  state: join(SRC, 'state.js'), api: join(SRC, 'api.js'), grid: join(SRC, 'grid.js'),
  clipboard: join(SRC, 'clipboard.js'), ui: join(SRC, 'ui.js'),
  push: join(SRC, 'push_columns.js'),
};

// What each subject takes from `./state.js`. 🔴 NOT a memory of it -- it is READ from the file, so
// a subject that starts importing one more name cannot silently stop being covered by the control.
const STATE_IMPORTS = {};
for (const key of ['api', 'grid', 'clipboard', 'ui', 'push']) {
  const text = readFileSync(FILE[key], 'utf8');
  const found = /import\s*\{([^}]*)\}\s*from\s*'\.\/state\.js'/.exec(text);
  STATE_IMPORTS[key] = found
    ? found[1].split(',').map((piece) => piece.trim().split(/\s+as\s+/)[0]).filter(Boolean)
    : [];
}

// `buildColumnDefs` asks the reference panel which columns a paste fills. That module owns async
// rule state, so the answer is STUBBED -- and stubbed NON-EMPTY, because a stub returning nothing
// would leave the ①② decoration unwalked and this harness green whatever it did.
let FILL_TARGETS = [['core_lot', '①'], ['core_slot', '②']];
const GRID_STUBS = {
  './enrichment_reference_view.js': { fillTargetOrdinals: () => new Map(FILL_TARGETS) },
};

const REAL = {
  state: await import('../src/state.js'),
  api: await import('../src/api.js'),
  grid: (await loadWithProbe(FILE.grid, { stubs: GRID_STUBS, tag: 'vcrgrid' })).module,
  clipboard: await import('../src/clipboard.js'),
  ui: await import('../src/ui.js'),
  push: await import('../src/push_columns.js'),
};

/** One bundle, with the named files replaced by mutants. `state` is never substituted.
 *
 * ⚠️ A TRANSFORM THAT CHANGES NOTHING LEAVES THE REAL MODULE IN PLACE. The probe refuses a
 *    mutate that returns the source unchanged -- rightly, for a DEFECT, where an unchanged
 *    source would score as 「caught」 having proved nothing. A CONTROL is the other case: 「rename
 *    every local」 has nothing to rename in `push_columns.js`, and that is not a failure, it is
 *    a file the control does not reach. Defects cannot slip through this door: `sub()` dies
 *    when its anchor count is wrong, before the probe is ever asked.
 */
async function bundleOf(mutations, tag) {
  const out = { ...REAL };
  // 🔵 C-91. `state.js` first, because everything else has to be pointed at ITS object.
  let stateStub = null;
  if (mutations.state) {
    const source = readFileSync(FILE.state, 'utf8').replace(/\r\n/g, '\n');
    if (mutations.state(source) !== source) {
      out.state = (await loadWithProbe(FILE.state, { mutate: mutations.state, tag })).module;
      stateStub = out.state;
    }
  }
  for (const key of Object.keys(mutations)) {
    if (key === 'state') continue;
    const source = readFileSync(FILE[key], 'utf8').replace(/\r\n/g, '\n');
    const mutated = mutations[key](source) !== source;
    if (!mutated && !stateStub) continue;
    const spec = { tag };
    if (mutated) spec.mutate = mutations[key];
    const stubs = key === 'grid' ? { ...GRID_STUBS } : {};
    if (stateStub && STATE_IMPORTS[key].length) {
      // Only the names THIS subject imports. The probe refuses the rest, by name.
      stubs['./state.js'] = Object.fromEntries(
        STATE_IMPORTS[key].map((name) => [name, stateStub[name]]));
    }
    if (Object.keys(stubs).length) spec.stubs = stubs;
    out[key] = (await loadWithProbe(FILE[key], spec)).module;
  }
  return out;
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

// ── staging ─────────────────────────────────────────────────────────────────────

let state = REAL.state.state;
// 🔵 C-91. The suite stages the state of the BUNDLE it is scoring. With a mutated `state.js` in
//    play that is a different object, and staging the real one would leave the mutant on a page
//    nobody filled -- which is exactly how a substituted singleton scores nothing.
const useState = (bundle) => { state = bundle.state.state; };

/** The shared `state`, put back to a known page before every runner. */
function stage(schema, extra = {}) {
  Object.assign(state, {
    currentTable: 'bonding_log',
    currentColumns: schema ? schema.columns.slice() : [],
    currentColumnTypes: schema ? schema.column_types : {},
    currentBusinessKey: schema ? schema.business_key : '',
    currentCompositeKeySources: schema ? schema.composite_key_source : [],
    currentVirtualColumns: schema ? schema.virtual_columns : [],
    currentJoinResolvedColumns: (schema && schema.join_resolved_columns) || [],
    viewMode: 'pagination', allDataLoaded: true, currentSkip: 0,
    pendingTxEdits: {}, txModeActive: false, selectedCellsMap: {},
    visibleColIndexMap: {}, dragStartCell: null, dragEndCell: null,
    smartPasteArmedUntil: 0, pageCache: new Map(),
  }, extra);
  writes = [];
  return state;
}

const rowOf = (i) => ({ row_id: `R${i}`, table_name: 'bonding_log', data: {},
                        created_at: null, updated_at: null });

function gridApiFor(colIds) {
  const cols = colIds.slice();
  return {
    getFocusedCell: () => null,
    getColumnState: () => cols.map((c) => ({ colId: c, hide: false })),
    getColumns: () => cols.map((c) => ({ getColId: () => c, isVisible: () => true })),
    getDisplayedRowAtIndex: (i) => (i === 0 ? { data: rowOf(0), id: 'R0' } : null),
    getRowNode: (id) => ({ data: rowOf(0), id }),
    getSelectedNodes: () => [{ data: rowOf(0), id: 'R0' }],
    applyTransaction() {}, refreshCells() {}, setGridOption() {}, redrawRows() {},
    forEachNode() {}, getDisplayedRowCount: () => 1, ensureIndexVisible() {},
    getEditingCells: () => [], stopEditing() {}, getColumn: () => null,
    applyColumnState() {}, setFilterModel() {}, getFilterModel: () => ({}),
    onFilterChanged() {}, refreshHeader() {}, getGridOption: () => undefined,
  };
}

/** The REAL `loadSchema`, fed a stubbed fetch. Records what the search dropdown was offered.
 *
 * `offered` is the VALUE (what reaches `?cols=`) and `labels` the visible text, kept apart on
 * purpose: they are allowed to differ (the 🔗 marker rides the label), and a check that read
 * only one of them could not tell a decorated label from a corrupted column name. */
async function runLoadSchema(sources, response) {
  stage(null);
  schemaBody = response;
  const select = doc.getElementById('search-cols');
  select.children.length = 0;
  select.innerHTML = '';
  await sources.api.loadSchema('bonding_log');
  // 🔴 THE APPENDED OPTIONS, WHICH IS THE QUESTION. `loadSchema` writes the 「All Columns」
  //    placeholder through `innerHTML` and appends the rest -- so what this reads is exactly
  //    what the code OFFERED, with the static placeholder no more counted here than it was
  //    when this harness recorded `appendChild` calls in a sandbox.
  const options = select.children.filter((c) => c.tagName === 'OPTION');
  return {
    state,
    offered: options.map((o) => o.value),
    labels: options.map((o) => o.textContent),
  };
}

/** The REAL `buildColumnDefs`, with the schema already in state. */
function runBuildColumnDefs(sources, schema, fillTargets = [['core_lot', '①'], ['core_slot', '②']]) {
  stage(schema);
  FILL_TARGETS = fillTargets;
  return sources.grid.buildColumnDefs();
}

/**
 * The four write funnels and the two copy predicates, DRIVEN. Each returns the column ids that
 * actually reached an update batch (or the copied block), given the grid columns a selection
 * covered.
 *
 * 🔴 C-88: these used to be arrow BODIES cut out of their handlers. Now the paste and copy
 *    handlers are the ones `setupClipboardHandlers` registers -- captured off the document stub
 *    and fired -- and clear/bulk-fill are the exported functions themselves. What is scored is
 *    what the operator's keystroke reaches.
 */
function runWriteFunnels(sources, schema) {
  const select = (colIds) => {
    const map = {};
    for (const colId of colIds) map[`0_${colId}`] = { rowIndex: 0, colId };
    return map;
  };
  const prepare = (colIds) => {
    stage(schema, {
      gridApi: gridApiFor(colIds),
      selectedCellsMap: select(colIds),
      visibleColIndexMap: Object.fromEntries(colIds.map((c, i) => [c, i])),
    });
  };
  const pasteHandler = () => {
    listeners.clear();
    sources.clipboard.setupClipboardHandlers();
    const fn = (listeners.get('paste') || [])[0];
    if (!fn) die('no paste listener: setupClipboardHandlers did not register one');
    return fn;
  };
  const copyHandler = () => {
    listeners.clear();
    sources.clipboard.setupClipboardHandlers();
    const fn = (listeners.get('copy') || [])[0];
    if (!fn) die('no copy listener: setupClipboardHandlers did not register one');
    return fn;
  };
  const clipboardEvent = (text) => {
    let written = '';
    return {
      event: {
        preventDefault() {}, stopPropagation() {},
        clipboardData: {
          getData: () => text,
          setData: (_type, value) => { written = value; },
          items: [], files: [],
        },
      },
      taken: () => written,
    };
  };
  const tsvColumns = (tsv) => (tsv ? String(tsv).split('\n')[0].split('\t') : []);

  return {
    async paste1x1(colIds) {
      prepare(colIds);
      const clip = clipboardEvent('7');
      await pasteHandler()(clip.event);
      return writtenColumns();
    },
    async pasteMxN(colIds) {
      prepare(colIds);
      // A row as wide as the selection is what makes this the MxN branch rather than the 1x1
      // fill -- the two differ only in the shape of what was copied.
      const clip = clipboardEvent(colIds.map(() => '7').join('\t'));
      await pasteHandler()(clip.event);
      return writtenColumns();
    },
    async clear(colIds) {
      prepare(colIds);
      await sources.clipboard.clearSelectedCells();
      return writtenColumns();
    },
    async bulkFill(colIds) {
      prepare(colIds);
      await sources.ui.applyValueToSelectedRange('7');
      return writtenColumns();
    },
    async copyRange(colIds) {
      prepare(colIds);
      // The header row names the columns that survived, which is exactly what is being asked.
      doc.getElementById('copy-header-toggle').checked = true;
      const clip = clipboardEvent('');
      await copyHandler()(clip.event);
      doc.getElementById('copy-header-toggle').checked = false;
      return tsvColumns(clip.taken()).map((c) => c.toLowerCase());
    },
    async copyRows(colIds) {
      // The ROW copy is the fallback the copy handler takes when no cell range is selected.
      prepare(colIds);
      state.selectedCellsMap = {};
      doc.getElementById('copy-header-toggle').checked = true;
      const clip = clipboardEvent('');
      await copyHandler()(clip.event);
      doc.getElementById('copy-header-toggle').checked = false;
      return tsvColumns(clip.taken()).map((c) => c.toLowerCase());
    },
  };
}

/**
 * The real Gate-4 push arithmetic, untouched by this round and asserted to stay that way.
 * 🔴 IMPORTED, like everything else here now (C-88). It was already the one function this file
 *    did not slice, and its module stays import-free so a probe copy of it needs no stubs.
 */
async function runPushGate(sources) {
  return sources.push.getUnprotectedPushColumns;
}

// ── scoring ─────────────────────────────────────────────────────────────────────

let quiet = false;
// 🔴 THE SUBJECTS LOG, AND A MUTANT RUN IS EXPECTED TO BE NOISY. That noise is not evidence --
//    `loadSchema` prints its own failure when a mutant feeds it a non-array -- so it is muted
//    while the sweep scores, exactly as the vm sandbox used to mute its own console. The
//    harness's OWN lines still print: they go through `console.log` here, guarded by `quiet`.
const realConsole = { log: console.log, error: console.error, warn: console.warn };
for (const key of ['log', 'error', 'warn']) {
  console[key] = (...args) => { if (!quiet) realConsole[key](...args); };
}
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
  useState(sources);
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
  check('9a MxN paste skips virtual columns', await w.pasteMxN(span), ['core_lot', 'bond_count']);
  check('9b 1x1 fill skips virtual columns', await w.paste1x1(span), ['core_lot', 'bond_count']);
  check('9c delete-to-clear skips virtual columns', await w.clear(span), ['core_lot', 'bond_count']);
  check('9d bulk fill skips virtual columns', await w.bulkFill(span), ['core_lot', 'bond_count']);
  // The axis is alive: with nothing announced the same span writes everything.
  const w0 = runWriteFunnels(sources, { ...SCHEMA, virtual_columns: [] });
  check('9e with no announcement the same span is fully writable', await w0.pasteMxN(span), span);

  // [9f-9g] COPY, the other side of the same coin. These predicates run INSIDE a
  // min..max index window, so a visible column they reject is deleted from the MIDDLE of the
  // copied block and everything to its right shifts one place left — the user gets a
  // rectangle that is not the one they selected, with no message. Rendering the column is
  // what made this predicate load-bearing, so it is scored here rather than assumed.
  check('9f range copy keeps virtual columns in place',
    await w.copyRange(['core_lot', 'wafer_id', 'bond_count']), ['core_lot', 'wafer_id', 'bond_count']);
  check('9g row copy keeps them too',
    await w.copyRows(['row_id', 'core_lot', 'wafer_id', '#']), ['row_id', 'core_lot', 'wafer_id']);

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
  // 🔵 C-91. THE PROOF THAT THE SUBSTITUTION REACHES THE SUBJECTS. A control that escapes proves
  //    nothing about it -- it escapes whether the copy was wired in or quietly skipped. This
  //    mutant lives in `state.js` and must be CAUGHT by the write funnels, which are OTHER files:
  //    if they are still reading the real singleton, the announcement is still honoured and this
  //    passes. It is the reason the wall is written as open rather than merely claimed open.
  ['state.js: the announcement stops being recognised, so every write funnel offers it', 'state',
    (t) => sub(t, '  return list.some(vc => vc && vc.name === colId);',
      '  return false;', 'state-blind')],
  ['merge the names into currentColumns', 'api', (t) => sub(t, 'state.currentColumns = data.columns || [];',
      'state.currentColumns = (data.columns || []).concat((data.virtual_columns || []).map(v => v.name));',
      'merge')],
  ['announce them as editable', 'grid', (t) => sub(t, `      field: col,\n      editable: false,`,
      `      field: col,\n      editable: true,`, 'editable')],
  ['coerce the unresolved label with a bare Number()', 'grid', (t) => sub(t, `    const parsed = Number(val);\n    if (!isNaN(parsed)) {\n      return parsed;\n    }`,
      `    return Number(val);`, 'coerce')],
  ['drop the guard that keeps Number("") from becoming 0', 'grid', (t) => sub(t, `  if (val !== '' && val !== null && val !== undefined) {`,
      `  if (val !== null && val !== undefined) {`, 'empty-guard')],
  ['fall back to the default sort comparator', 'grid', (t) => sub(t, `      ...(isNumeric ? {`, `      ...(false ? {`, 'comparator')],
  // ── the 2026-07-31 round: which columns lose blank/notBlank, and on whose say-so ──────
  ['leave blank/notBlank on a join-resolved column', 'grid', (t) => sub(t, `    filterParams: { filterOptions: JOIN_RESOLVED_FILTER_OPTIONS },\n`, ``,
      'keep-blank')],
  // Both kinds, because the numeric hazard is identical on each: the server casts the
  // override to String, so a numeric predicate would be answered lexically.
  ['use a number filter on a numeric join-resolved column', 'grid', (t) => sub(sub(t,
      `      ...filterDef,\n      resizable: true,`,
      `      ...filterDef,\n      ...(isNumeric ? { filter: 'agNumberColumnFilter' } : {}),\n      resizable: true,`,
      'number-filter-virtual'),
      `      Object.assign(colDef, joinResolvedFilterDef(resolvedEntry, headerLabel));`,
      `      Object.assign(colDef, joinResolvedFilterDef(resolvedEntry, headerLabel));\n`
      + `      if (colType === 'number') colDef.filter = 'agNumberColumnFilter';`,
      'number-filter-stored')],
  // The exact error the brief warned about: `isVirtualColumn` cannot see a collide column.
  ['key the filter off isVirtualColumn instead of the announcement', 'grid', (t) => sub(t, `    const resolvedEntry = joinResolvedColumn(col);\n\n    const colDef = {`,
      `    const resolvedEntry = null;\n\n    const colDef = {`, 'wrong-predicate')],
  ['enable the filter even when the server never announced it', 'grid', (t) => sub(t, `    const filterDef = resolvedEntry\n      ? joinResolvedFilterDef(resolvedEntry, baseTooltip)\n      : { filter: false, floatingFilter: false, headerTooltip: baseTooltip };`,
      `    const filterDef = joinResolvedFilterDef(resolvedEntry || vc, baseTooltip);`,
      'old-server')],
  ['hardcode the unresolved label instead of reading the entry', 'grid', (t) => sub(t, `    ? entry.unresolved_label : '';`, `    ? '미상' : '미상';`, 'hardcode')],
  // 🔴 The design line the brief drew: this marker must never become a write guard.
  // ⚠️ C-84 moved this anchor: editability now also asks whether the CATALOGUE calls the table a
  //    view (`!viewTable`). That is a different question — a table-level fact the server states —
  //    and the mutant still says the same thing: the join ANNOUNCEMENT must not decide writability.
  ['make the announcement decide editability', 'grid', (t) => sub(t, `      editable: !isSystem && !viewTable,`,
      `      editable: !isSystem && !viewTable && !resolvedEntry,`, 'write-guard')],
  ['let the announcement replace the numeric cell editor', 'grid', (t) => sub(t, `    if (colType === 'number') {\n      colDef.cellEditor = 'agNumberCellEditor';`,
      `    if (colType === 'number' && !resolvedEntry) {\n      colDef.cellEditor = 'agNumberCellEditor';`,
      'editor')],
  ['accept a non-array join_resolved_columns straight into state', 'api', (t) => sub(t, `Array.isArray(data.join_resolved_columns)\n      ? data.join_resolved_columns : []`,
      `data.join_resolved_columns || []`, 'non-array-jrc')],
  // ── the search dropdown (N4) ──────────────────────────────────────────────────
  // The regression: back to stored columns only, which is what this file asserted before
  // the server learned to scope `?cols=` by the announcement.
  ['drop the announced columns from the search dropdown', 'api', (t) => sub(t, `        if (state.currentColumns.includes(entry.name)) return;\n        appendOption(entry.name, true);`,
      `        return;`, 'dropdown-stored-only')],
  // Appending the WIDER announcement wholesale: every `collide` name is offered a second time.
  ['offer the announcement without differencing it against stored columns', 'api', (t) => sub(t, `        if (state.currentColumns.includes(entry.name)) return;\n`, ``,
      'dropdown-dup')],
  // Fabricating the list instead of reading the announcement — the exact thing the brief
  // forbade. `virtual_columns` is the NARROWER key and is the convenient wrong read.
  ['build the dropdown from virtual_columns instead of the announcement', 'api', (t) => sub(t, `      state.currentJoinResolvedColumns.forEach(entry => {`,
      `      state.currentVirtualColumns.forEach(entry => {`, 'dropdown-wrong-list')],
  // A malformed entry becoming an option whose value is `undefined`.
  ['let a malformed announcement entry reach the dropdown', 'api', (t) => sub(t, `        if (!entry || typeof entry.name !== 'string' || entry.name === '') return;\n`,
      ``, 'dropdown-malformed')],
  // The decoration leaking into the value, i.e. into `?cols=`.
  ['put the 🔗 marker in the option value rather than the label', 'api', (t) => sub(t, `        option.value = col;`, `        option.value = joined ? \`\${col} 🔗\` : col;`,
      'dropdown-marker-in-value')],
  ['let a colliding name produce a second def', 'grid', (t) => sub(t, `    if (state.currentColumns.includes(col)) return;`, ``, 'collide')],
  ['accept a malformed announcement entry', 'grid', (t) => sub(t, `    if (!vc || typeof vc.name !== 'string' || vc.name === '') return;`, ``,
      'malformed')],
  // The trailing line disambiguates the two paste branches, whose guards differ only in
  // indentation (and the shallower one is a substring of the deeper one).
  ['let the MxN paste target a virtual column', 'clipboard', (t) => sub(t,
      `            if (isVirtualColumn(colId)) return;\n\n            if (!updateMapByRow[rowId]) {`,
      `            if (!updateMapByRow[rowId]) {`, 'paste-mxn')],
  ['let the 1x1 fill target a virtual column', 'clipboard', (t) => sub(t,
      `          if (isVirtualColumn(colId)) return;\n\n          const rowNode = state.gridApi.getDisplayedRowAtIndex(rowIndex);`,
      `          const rowNode = state.gridApi.getDisplayedRowAtIndex(rowIndex);`, 'paste-1x1')],
  ['let delete-to-clear target a virtual column', 'clipboard', (t) => sub(t, `    if (isVirtualColumn(cell.colId)) return;`, ``, 'clear')],
  ['let the bulk fill target a virtual column', 'ui', (t) => sub(t, `    if (isVirtualColumn(colId)) return;`, ``, 'bulk-fill')],
  ['make the push gate count announced columns', 'push', (t) => sub(t, `  const cols = Array.isArray(schema && schema.columns) ? schema.columns : [];`,
      `  const cols = (Array.isArray(schema && schema.columns) ? schema.columns : [])\n`
      + `    .concat((Array.isArray(schema && schema.virtual_columns) ? schema.virtual_columns : []).map(v => v.name));`,
      'push-gate')],
  ['drop a virtual column out of the middle of a copied range', 'clipboard', (t) => sub(t,
      `    return state.currentColumns.includes(colId)\n      || isVirtualColumn(colId)\n`,
      `    return state.currentColumns.includes(colId)\n`, 'copy-range')],
  ['drop it out of a row copy', 'clipboard', (t) => sub(t,
      `      return state.currentColumns.includes(c)\n        || isVirtualColumn(c)\n`,
      `      return state.currentColumns.includes(c)\n`, 'copy-rows')],
  ['accept a non-array virtual_columns straight into state', 'api', (t) => sub(t, `Array.isArray(data.virtual_columns) ? data.virtual_columns : []`,
      `data.virtual_columns || []`, 'non-array')]
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

// 🔵 C-91. A CONTROL NOW APPLIES TO ALL SIX. `state.js` joined the day the composition above was
//    written; before that its copy was 「a page nobody is on」, which read as a wall and was not one.
const SUBSTITUTABLE = ['state', 'api', 'grid', 'clipboard', 'ui', 'push'];
const everyFile = (fn) => Object.fromEntries(SUBSTITUTABLE.map((key) => [key, fn]));

const CONTROLS = [
  ['consistent rename of locals across every module',
    everyFile((t) => RENAMES.reduce((acc, [re, to]) => acc.replace(re, to), t))],
  ['every full-line comment stripped from every module', everyFile(stripComments)],
];

// ── run ─────────────────────────────────────────────────────────────────────────

const base = await suite(REAL);
console.log(`\n[baseline] ${base.pass} passed, ${base.fail} failed`);

let caught = 0, escaped = 0;
const escapedNames = [];
console.log(`\n── defect mutants (each must be CAUGHT) ────────────────────────────`);
quiet = true;
for (const [name, key, mutate] of DEFECTS) {
  let r;
  try { r = await suite(await bundleOf({ [key]: mutate }, 'vcrd')); }
  catch (e) { r = { fail: 1, failed: [`threw: ${e && e.message}`] }; }
  if (r.fail > 0) { caught++; console.log(`  caught  ${name}  (${r.failed[0]})`); }
  else { escaped++; escapedNames.push(name); console.log(`  ESCAPED ${name}`); }
}

let controlsCaught = 0;
const controlsCaughtNames = [];
console.log(`\n── control mutants (each must ESCAPE) ──────────────────────────────`);
for (const [name, mutations] of CONTROLS) {
  let r;
  try { r = await suite(await bundleOf(mutations, 'vcrc')); }
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
