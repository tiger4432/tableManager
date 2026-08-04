// Harness — the unsaved-work guard: which gestures mark a frame unsaved, which DOORS ask
// before discarding it, and what the prompt names when it fires (2026-08-04).
//
// THE SECOND DOOR (round 2, same day). Closing the back-navigation path did not close the one
// the user actually reported: 📂 Load Existing Map. `loadExistingMap` discards the declaration
// in its first three statements, unconditionally, and nothing asked first. The predicate had
// been spelled TWICE — once in `popMapFrame` and, by omission, not at all in the load — which
// is how one door came to protect the work and the other to throw it away. There is now ONE
// spelling (`unsavedWorkNotice`) and cases J1–J7 hold the second door to it. The mutant
// `the-load-door-spells-its-own-predicate` exists because a copy is the failure mode, not a
// hypothetical: it plants the most plausible second spelling and requires it to be caught.
// Run: node client2/tests/valid_die_dirty_guard_harness.mjs   (no node_modules — vm sandbox)
//
// THE LIVE REGRESSION THIS REPRODUCES. `popMapFrame` guarded unsaved work with
//   `!framePushed && frameTouched && gridData && Object.keys(gridData).length > 0`
// and `frameTouched` was set in exactly two places: `persistLegend` and `scheduleCellDraft`.
// Choosing a valid-die reference goes through NEITHER. So applying one changed the screen and
// changed what a later save would write, while the frame stayed marked CLEAN — and the next
// frame pop threw it away with no prompt at all. The 💾 SAVE button used to make the
// persistence step visible; it was removed and the guard was not moved with it.
//
// WHY THIS IS ITS OWN FILE, AND WHAT IT DOES NOT SCORE. `map_spec_only_save_harness` owns the
// 📐 규격만 저장 REQUEST SHAPE (read-modify-write, unmodelled fields, the response bound) and
// `valid_die_origin_alignment_harness` / `valid_die_head_parity_oracle` own what a declaration
// RESOLVES TO on the canvas. Neither has an opinion about frame dirtiness, and bolting this
// onto either would put two unrelated failure classes behind one exit code. `resolveValidDie`
// is therefore a RECORDER here, not a stub that fakes an answer this harness grades: what is
// under test is the marking, so the assertions read the recorder ("the apply was invoked with
// this declaration") and the flags, never a resolved mask.
//
// THE FOUR THINGS THAT CAN GO SILENTLY WRONG, AND HOW EACH IS MADE FALSIFIABLE.
//
//   1. A GESTURE IS LEFT UNMARKED. There are two applying gestures — the `<select>` `change`
//      and the key input's Enter — and one unmarked path reproduces the whole bug in a corner.
//      Scored by EXECUTING THE REAL LISTENER BODIES: the two wiring blocks are sliced out of
//      `initDOMElements` verbatim and run against recording controls, then the events are
//      fired. A harness that called `onValidDieRefChanged()` directly would pass even if the
//      `<select>` were wired to nothing.
//
//   2. MARKING SPREADS TO MERE VIEWING. That was the previous complaint ([fix E]) and it must
//      not come back. Scored in both shapes: a load followed straight by a pop, and a load of
//      a NON-EMPTY map followed by a pop — the second is the exact case [fix E] closed, and
//      the cell-count term this change removes is the thing that used to (accidentally) cover
//      it. Also scored for the IME Enter, which is not a gesture at all.
//
//   3. CLEARING BACK TO 원 기하 IS MISSED. Setting a declaration and removing one are the same
//      kind of edit, and the empty case is the one that looks like "nothing happened". Scored
//      as its own axis with `validDie.raw` non-empty going in.
//
//   4. THE PROMPT NAMES THE WRONG WRITER. Two writers exist; ⚡ Push is `replace_map`, a full
//      cell rewrite. For a declaration-only change 📐 규격만 저장 is the cheaper correct
//      answer, and a prompt that names only the expensive one is how people learn to push for
//      everything. Scored as the TEXT of the confirm, in both directions — cells dirty must
//      still name Push — and END TO END: apply, spec-save, pop, and the pop must be silent,
//      because a prompt that repeats after the user did what it said is a prompt that lied.
//
// FIXTURE ACTIVITY. The declaration used is an OBJECT ref (`{table, map_id}`) with a table
// that differs from the control's, and `validDieRefFromControls` is the real function — so
// the "did the user change it" comparison is live rather than trivially true. The spec-save
// leg is anisotropic and rotated (`chip_x !== chip_y`, rot 90, `cols !== rows`) for the same
// reason `map_spec_only_save_harness` is: a square isotropic fixture cannot show a swap
// defect at all, so a number it produced would be an artefact of the symmetry.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..', '..');
const SRC_PATH = join(ROOT, 'client2', 'src', 'map_editor.js');
const SRC = readFileSync(SRC_PATH, 'utf8');
const CFG = readFileSync(join(ROOT, 'client2', 'src', 'config.js'), 'utf8');
const verbose = process.argv.includes('--verbose');

function die(msg) {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  process.exit(2);
}

// ── Extraction ──────────────────────────────────────────────────────────────────────────
// ⚠️ THE BODY BRACE IS FOUND VIA THE PARAMETER LIST, NOT VIA `indexOf('{')`. `async function
//    loadExistingMap(opts = {})` has a brace in its DEFAULT PARAMETER, and the naive scan
//    latches onto that one, balances it immediately, and returns a truncated slice that dies
//    with "Unexpected token 'async'". The sibling harnesses get away with the naive form only
//    because none of them slices a function with a destructured or object default.
function sliceFunction(src, name) {
  const m = new RegExp(`(?:^|\\n)(?:async\\s+)?function\\s+${name}\\s*\\(`).exec(src);
  if (!m) die(`function ${name} is gone from map_editor.js — renamed or reshaped.`);
  const start = m.index + (m[0].startsWith('\n') ? 1 : 0);
  let paren = 0, open = -1;
  for (let j = src.indexOf('(', start); j < src.length; j++) {
    if (src[j] === '(') paren++;
    else if (src[j] === ')') { paren--; if (paren === 0) { open = src.indexOf('{', j); break; } }
  }
  if (open < 0) die(`could not find the body of ${name}`);
  let depth = 0;
  for (let j = open; j < src.length; j++) {
    if (src[j] === '{') depth++;
    else if (src[j] === '}') { depth--; if (depth === 0) return src.slice(start, j + 1); }
  }
  return die(`unbalanced braces for ${name}`);
}

/**
 * Slice a balanced `{...}` statement block starting at a HEAD line, e.g. `if (el.foo) {`.
 * This is how the event wiring is scored: those listeners live inside `initDOMElements`,
 * a function that touches the whole page, and re-typing them here would let this harness
 * grade a wiring the product does not have.
 * The head must be UNIQUE — a first-match slice has twice landed on a different construct in
 * this file, once inside a comment.
 */
function sliceBlock(src, head) {
  const i = src.indexOf(head);
  if (i < 0) die(`wiring block head is gone from map_editor.js: ${head}`);
  if (src.indexOf(head, i + 1) >= 0) die(`wiring block head is not unique: ${head}`);
  const open = src.indexOf('{', i);
  let depth = 0;
  for (let j = open; j < src.length; j++) {
    if (src[j] === '{') depth++;
    else if (src[j] === '}') { depth--; if (depth === 0) return src.slice(i, j + 1); }
  }
  return die(`unbalanced braces for wiring block ${head}`);
}

const KEY_WIRING_HEAD = '  if (el.validDieRefKey) {';
const SELECT_WIRING_HEAD = '  if (el.validDieRefSelect) {';

const SYMBOLS = [
  // ── the ONE predicate. Both doors call it; a second spelling is the defect class. ──
  'unsavedWorkNotice',
  // ── the guard and the gateways that feed it ──
  'persistLegend', 'scheduleCellDraft', 'setLoadedIdentity', 'clearGrid', 'popMapFrame',
  // ── the SECOND door: replacing this map with another one ──
  // `collectMapKeyFilterModel` is real, not stubbed, because the gate's POSITION relative to
  // it is a contract: a prompt raised after the filter has been collected is a prompt about a
  // state that already started changing, and case J6 discriminates the two orders.
  'collectMapKeyFilterModel', 'scanCoordinateBounds', 'syncValidDieRefControls',
  'loadExistingMap', 'restoreLastOpenMap',
  // ── the declaration path ──
  'validDieRefDisplay', 'validDieRefFromControls', 'onValidDieRefChanged',
  // ── the cheaper writer the reworded prompt names, sliced so the end-to-end leg is real ──
  'physNum', 'gridDimNum', 'getScreenShift', 'getTransformedPhysicalConfig', 'getDieIndex',
  'readGridFrameControls', 'applyValidDieRef', 'validDieRefForPush', 'validDieRefPayload',
  'mergeStoredGridMeta', 'geometryIsAutoRegistered', 'markGeometryAutoRegistered',
  'buildPushGridMetadata', 'serverCellKeySet', 'classifyUnsavableCells', 'fetchGridMetaFor',
  'saveMapSpecOnly',
];

// ── Fixture ─────────────────────────────────────────────────────────────────────────────
const FRAME = { cols: 25, rows: 21 };
const PHYS = { dia: 300, chipX: 14.3, chipY: 9.7, offX: 1.7, offY: -2.4, margin: 3 };
const ROT = 90;
const SIDE = 'front';
// A declaration whose TABLE is not the control's default, so `validDieRefFromControls`'s
// "did the user touch the key" comparison is exercised rather than trivially satisfied.
const STORED_REF = { table: 'valid_die_ref', map_id: 'VD_MASK_A' };

function makeInput(v) { return { value: String(v), checked: false, style: {}, dataset: {} }; }

/** A control that records its listeners, so the real handler bodies can be fired. */
function makeControl(v) {
  const listeners = {};
  return {
    value: String(v), style: {}, dataset: {},
    addEventListener(type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
    __fire(type, ev) { (listeners[type] || []).forEach(fn => fn(ev)); },
    __listenerTypes() { return Object.keys(listeners).sort(); },
  };
}

function cfgNumber(name) {
  const m = new RegExp(`export\\s+const\\s+${name}\\s*=\\s*([0-9.]+)\\s*;`).exec(CFG);
  if (!m) die(`\`export const ${name}\` is gone from config.js`);
  return Number(m[1]);
}

// ── The carry ruling's extra slice ───────────────────────────────────────────────────────
// 🔴 `resolveValidDie` IS A RECORDER FOR EVERY LEG EXCEPT K, AND THAT IS WHY K NEEDED MORE.
//    The K cases score the user ruling 「고유 메타를 가진 맵을 불러오기 전까지 유효 다이영역
//    초기화 금지」, and the clear that survived three repair rounds does not live in
//    `loadExistingMap` at all — it arrives through the resolver: an undeclared map makes
//    `parseValidDieRef` answer null, `resolveValidDie` takes its `set('circle', …)` branch,
//    and `set` ends by calling `syncValidDieRefControls()`, which blanks the key control.
//    A recorder cannot reproduce that, so a K leg on a recorder would go green on code that
//    still blanks the box. `opts.realResolve` therefore runs the REAL resolver, the real
//    `parseValidDieRef`, the real `syncValidDieRefControls` and the real `validDieRefDisplay`
//    against a real control object — the whole chain from the load to the blanked box.
// ⚠️ WHAT IS STILL STUBBED UNDER `realResolve`, AND WHY THAT IS NOT A HOLE. The resolver's
//    reference LOOKUP (`resolveReferenceSpec`) and the placement machinery it drives
//    (`applyPresetObject` · `fitGridToMask` · `reseatCellsToStoredCoords`) are stubbed. What
//    a declaration RESOLVES TO on the canvas is owned by `valid_die_origin_alignment_harness`
//    and `valid_die_head_parity_oracle`; duplicating it here would put two unrelated failure
//    classes behind one exit code. What K scores is WHICH declaration is in force after a
//    load and WHAT THE CONTROL SHOWS — and every step of that is real.
const RESOLVE_SYMBOLS = ['parseValidDieRef', 'validDieBasis', 'resolveValidDie'];

// ── Sandbox ─────────────────────────────────────────────────────────────────────────────
function buildEnv(src, opts = {}) {
  const confirms = [];
  const alerts = [];
  const toasts = [];
  const applies = [];     // every `resolveValidDie` invocation, with the declaration it carried
  const requests = [];
  const seatedUnderBasis = [];   // the valid-die basis in force as each cell was placed
  // The map key filter lives in DOM inputs that `collectMapKeyFilterModel` finds by id prefix.
  // `metaFilter: {}` therefore means "no map key entered", which is what case J6 needs.
  const metaValues = (opts.metaFilter !== undefined) ? opts.metaFilter : { lot_id: 'LOT_9' };
  const metaInputs = Object.entries(metaValues).map(([col, val]) => ({
    id: `meta-input-${col}`, value: String(val),
  }));
  const el = {
    gridCols: makeInput(FRAME.cols), gridRows: makeInput(FRAME.rows),
    gridStartX: makeInput(1), gridStartY: makeInput(1),
    gridYInvert: { checked: false },
    physWaferDia: makeInput(PHYS.dia),
    physChipX: makeInput(PHYS.chipX), physChipY: makeInput(PHYS.chipY),
    physOffsetX: makeInput(PHYS.offX), physOffsetY: makeInput(PHYS.offY),
    physEdgeMargin: makeInput(PHYS.margin),
    validDieRefKey: makeControl(opts.controlKey !== undefined ? opts.controlKey : ''),
    validDieRefSelect: makeControl(''),
    validDieRefList: { innerHTML: '' },
    mapWorkspace: { scrollLeft: 0, scrollTop: 0 },
    btnSaveMapSpec: { disabled: false, textContent: '📐 규격만 저장' },
    // The load door's own controls. `btnLoadMap.textContent` is a witness for "did anything
    // start happening": the load flips it to '📂 Loading...' before it issues its request, so
    // a declined prompt that left it alone provably aborted before any side effect.
    btnLoadMap: { disabled: false, textContent: '📂 Load Existing Map' },
    colMapX: makeInput('x'), colMapY: makeInput('y'), colMapVal: makeInput('val'),
    tableSelect: { value: 'bonding_map', disabled: false, options: [{ value: 'bonding_map' }] },
  };

  const sandbox = {
    AbortController,
    setTimeout: (fn) => { void fn; return 0; },   // the cell draft's debounce is not under test
    clearTimeout: () => {},
    setImmediate,
    MAP_SPEC_SAVE_TIMEOUT_MS: cfgNumber('MAP_SPEC_SAVE_TIMEOUT_MS'),
    console: { warn() {}, log() {}, error() {}, info() {}, debug() {} },
    JSON, Math, Number, Object, Array, String, Boolean, Set, Map, parseInt, parseFloat,
    isNaN, encodeURIComponent, Promise,
    el,
    API_BASE: '/api',
    CURRENT_USER: 'tester',
    selectedTable: 'bonding_map',
    currentRotation: ROT,
    currentSide: SIDE,
    physFrameOverride: null,
    // ── the state under test ──
    frameTouched: false,
    framePushed: false,
    legendDirty: false,
    gridData: opts.gridData ? { ...opts.gridData } : {},
    gridCells2D: {},
    editorFrames: [{ marker: 'PARENT_FRAME' }],
    loadedIdentity: { table: 'bonding_map', mapKey: 'MAP_UNDER_EDIT' },
    legendReplaceScope: null,
    serverCellKeys: null,
    loadedFCells: new Set(),
    cellDraftTimer: null,
    validDie: opts.validDie
      ? { ...opts.validDie }
      : { basis: 'circle', keys: null, reason: '', ref: null, raw: undefined },
    ROUTE_MATERIAL: 'map_editor:material',
    getCurrentMapKey: () => 'MAP_UNDER_EDIT',
    effortRoute: () => 'map_editor',
    countNav() {},
    renderBreadcrumb() {},
    notifyMapContext() {},
    restoreEditorState() {},
    renderGridCanvas() {},
    updateLegendCounts() {},
    notifyLegendChanged() {},
    saveLegendToStorage() {},
    saveDoeDraft() {},
    populateValidDieRefList() {},
    renderValidDieKeyControl() {},
    syncValidDieRefControls() {},
    showToast: (msg, kind) => toasts.push({ msg: String(msg), kind }),
    confirm: (text) => { confirms.push(String(text)); return opts.approve !== false; },
    alert: (text) => { alerts.push(String(text)); },
    // Only what `collectMapKeyFilterModel` and `restoreLastOpenMap` reach for.
    document: {
      querySelectorAll: (sel) => (sel === '[id^="meta-input-"]' ? metaInputs : []),
      getElementById: (id) => metaInputs.find(i => i.id === id) || null,
    },
    localStorage: {
      getItem: () => (opts.lastOpen === undefined
        ? JSON.stringify({ v: 1, table: 'bonding_map', metaValues: { lot_id: 'LOT_9' } })
        : opts.lastOpen),
    },
    // ── the load body past the gate. Stubbed to a SHORT, fully determined path so that
    //    "the load actually proceeded" is a measurement rather than a swallowed exception.
    //    What the load DOES with the map is scored by the load-path harnesses; what is under
    //    test here is the door in front of it.
    //    The exit chosen is the load's OWN documented refusal at step ③ ("확인 실패는 선언
    //    없음이 아니다"): it is reached only AFTER the gate, the [M4①] clear, the filter
    //    collection, the button-label flip and the request, so every one of those is
    //    observable, and it ends the call deterministically instead of in a swallowed throw.
    // Stubbed for every leg but K5, which slices the real one to score clear site 1 of 3.
    switchTable: async () => {},
    fetchPaintRules: async () => {},
    fillColumnDropdowns() {},
    renderMetadataInputs() {},
    dropColumnValueCache() {},
    mapKeyListCache: new Map(),
    applyRoutedPreset: async () => {},
    // `opts.declaredMeta` opens the load PAST step ③, which is where the K cases live: the
    // exit above is before `resolveValidDie` is ever reached, so it can say nothing about who
    // owns the designation afterwards. `undefined` keeps the short refusal every other leg uses.
    resolveDeclaredGridMeta: async () => (opts.declaredMeta === undefined
      ? { ok: false, refusal: { count: 0, refused: true } }
      : { ok: true, gridMeta: opts.declaredMeta, mapKey: 'MAP_B' }),
    clearOverlayLayers() {},
    renderValidDieChip() {},
    tableSchema: null,
    overlayLayers: [],
    boundingBoxCache: {},
    // ── the rest of the load body, past step ③. Owned by the load-path harnesses. ────────
    promptCoordinateChoice: async () => 'meta',
    resolveGridFrame: () => ({
      cols: FRAME.cols, rows: FRAME.rows, startX: 1, startY: 1,
      invertY: false, rotation: ROT, side: SIDE,
    }),
    updateOrientationUI() {},
    isLockedValue: () => false,
    deriveLegendFromCellValues: () => [],
    readRegistryScope: async () => ({ ok: true, rows: [] }),
    applyRegistryRowsToLegend() {},
    registryFingerprint: () => 'fp',
    cellsDigest: () => 'cd',
    restoreDoeDraftWithPrecedence: () => ({ restoredUnsavedEdits: false, staleDraftKept: false }),
    readDoeDraft: () => null,
    applyDoeDraftRecord: () => false,
    applyDraftCells: () => 0,
    recordLastOpenMap() {},
    seedEmptyDoe() {},
    renderLegendTable() {},
    legend: [], activeBrush: '', draftBase: null, legendConflict: null, legendSaveState: null,
    // ── what `resolveValidDie`'s `set` reaches for. Placement is scored elsewhere. ───────
    validDieResolveSeq: 0,
    cellsSeatedUnder: null,
    seatingSnapshot: () => ({}),
    reseatCellsToStoredCoords: () => [],
    summariseReseat: () => ({ netMoved: 0, note: '' }),
    applyPresetObject() {},
    fitGridToMask: () => null,
    resolveReferenceSpec: async () => ({ ok: false, reason: '참조 맵을 찾지 못했습니다(하네스 고정)' }),
    // ORDERING WITNESS. Every seating records the COORDINATE it was asked about and the
    // valid-die basis in force at that instant, so "the designation is settled before the
    // placement loop" is a measurement rather than a comment.
    // ⚠️ The placement loop is not the only caller: `resolveValidDie`'s `set` probes the same
    //    function twice (`wasSeat`/`nowSeat`) around the moment it swaps the basis, at the
    //    frame's START coordinate. Those two entries are kept rather than filtered out — they
    //    are the clearest evidence in the list that the swap happened where it claims to.
    getCanvasCellFromDb: (x, y) => {
      seatedUnderBasis.push(`${x},${y}:${sandbox.validDieBasis ? sandbox.validDieBasis() : '?'}`);
      return { c: Number(x) || 0, r: Number(y) || 0 };
    },
    // THE RECORDER. It writes back `validDie.raw` exactly as `resolveValidDie`'s own `set`
    // does (`raw` is the declaration original), because the NEXT gesture's "did the user
    // change it" comparison reads that field — a recorder that dropped it would make the
    // clearing case unreachable. It resolves no mask: masks are scored elsewhere.
    resolveValidDie: async (meta, table, homeKey) => {
      applies.push({
        ref: (meta && 'valid_die_ref' in meta) ? meta.valid_die_ref : null,
        table, homeKey,
      });
      sandbox.validDie = {
        ...sandbox.validDie,
        raw: (meta && 'valid_die_ref' in meta) ? meta.valid_die_ref : undefined,
      };
    },
    fetch: (url, init) => {
      const method = (init && init.method) ? init.method : 'GET';
      requests.push({ method, url: String(url), body: init && init.body ? init.body : null });
      if (method === 'PUT') return Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
      if (String(url).indexOf('wafer_map_metadata') < 0) {
        // the cell table read the load door issues. `opts.cellRows` fills it so the placement
        // loop actually runs — case K7 needs a cell to be seated in order to witness the
        // basis in force at that moment.
        const data = opts.cellRows || [];
        return Promise.resolve({ ok: true, status: 200, json: async () => ({ data }) });
      }
      return Promise.resolve({
        ok: true, status: 200,
        json: async () => ({ data: [{ data: { grid_metadata: { value: JSON.stringify({
          grid_cols: FRAME.cols, grid_rows: FRAME.rows, grid_start_x: 1, grid_start_y: 1,
          rotation: ROT, side: SIDE,
        }) } } }] }),
      });
    },
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);

  const names = SYMBOLS
    .concat(opts.realResolve ? RESOLVE_SYMBOLS : [])
    .concat(opts.realSwitch ? ['switchTable'] : []);
  const pieces = names.map(n => sliceFunction(src, n));
  const vd = /^const VALID_DIE_TABLE = .*;$/m.exec(src);
  if (!vd) die('const VALID_DIE_TABLE is gone from map_editor.js');
  pieces.unshift(vd[0]);
  const lok = /^const LAST_OPEN_KEY = .*;$/m.exec(src);
  if (!lok) die('const LAST_OPEN_KEY is gone from map_editor.js');
  pieces.unshift(lok[0]);
  // The wiring, verbatim. Wrapped in a function only so it can be invoked on demand.
  pieces.push(`function __wireValidDieControls() {\n`
    + sliceBlock(src, KEY_WIRING_HEAD) + '\n'
    + sliceBlock(src, SELECT_WIRING_HEAD) + '\n}');
  try { vm.runInContext(pieces.join('\n\n'), sandbox); }
  catch (e) { die(`extracted sources did not evaluate: ${e && e.message}`); }
  sandbox.__wireValidDieControls();

  // Under `realResolve` the sliced declaration has overwritten the recorder, so `applies` is
  // re-attached as a WRAPPER: the real body still runs, and "was the resolver reached at all"
  // stays measurable. That question is the whole of clear site 3 — an undeclared map must not
  // reach it, a declaring map must.
  if (opts.realResolve) {
    const real = sandbox.resolveValidDie;
    sandbox.resolveValidDie = async (meta, table, homeKey) => {
      applies.push({
        ref: (meta && 'valid_die_ref' in meta) ? meta.valid_die_ref : null,
        table, homeKey,
      });
      return real(meta, table, homeKey);
    };
  }

  return { S: sandbox, el, confirms, alerts, toasts, applies, requests, seatedUnderBasis };
}

const flush = () => new Promise(r => setImmediate(r));

/** Fire the `<select>` gesture: the browser sets the value, then dispatches `change`. */
async function pickFromSelect(env, value) {
  env.el.validDieRefSelect.value = String(value);
  env.el.validDieRefSelect.__fire('change', {});
  await flush(); await flush();
}

/** Fire the fallback input's gesture: type, then Enter. */
async function typeAndEnter(env, value, ev = {}) {
  env.el.validDieRefKey.value = String(value);
  env.el.validDieRefKey.__fire('keydown', { key: 'Enter', ...ev });
  await flush(); await flush();
}

// ── Cases ───────────────────────────────────────────────────────────────────────────────
async function run(src) {
  const failures = [];
  const evidence = [];
  let compared = 0;
  const eq = (name, expected, actual, note) => {
    compared++;
    const a = JSON.stringify(actual), e = JSON.stringify(expected);
    if (a !== e) failures.push(`${name}: expected ${e}, got ${a}${note ? ` — ${note}` : ''}`);
  };

  // ── A. THE REPORTED REGRESSION, BOTH GESTURES. ────────────────────────────────────────
  // The map has NO painted cells, which is the shape the removed cell-count term silenced by
  // construction: a template map, or a map being declared before it is filled.
  for (const [label, gesture] of [
    ['select', (env) => pickFromSelect(env, 'VD_MASK_A')],
    ['enter', (env) => typeAndEnter(env, 'VD_MASK_A')],
  ]) {
    const env = buildEnv(src);
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');   // a clean baseline, as a load gives
    eq(`A[${label}]/baseline is clean after the load`,
      { touched: false, pushed: false }, { touched: env.S.frameTouched, pushed: env.S.framePushed });

    await gesture(env);

    // The apply really happened — otherwise a "marked" flag would be measuring nothing.
    eq(`A[${label}]/the declaration was applied`, [STORED_REF], env.applies.map(a => a.ref),
      'the gesture must reach resolveValidDie; a flag set without an apply is not this feature');
    eq(`A[${label}]/the frame is marked unsaved`, true, env.S.frameTouched);

    const popped = env.S.popMapFrame();
    eq(`A[${label}]/the pop prompted exactly once`, 1, env.confirms.length,
      'THIS IS THE REGRESSION: 0 here means the selection is discarded in silence');
    eq(`A[${label}]/approved pop still returns`, true, popped);
    evidence.push(`A[${label}] confirm text: ${JSON.stringify(env.confirms[0] || null)}`);
  }

  // ── B. DECLINING KEEPS THE USER PUT — the frame must NOT be popped. ───────────────────
  {
    const env = buildEnv(src, { approve: false });
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    await pickFromSelect(env, 'VD_MASK_A');
    const popped = env.S.popMapFrame();
    eq('B/declining returns false', false, popped);
    eq('B/declining leaves the frame stack intact', 1, env.S.editorFrames.length);
  }

  // ── C. CLEARING BACK TO 원 기하 IS AN EDIT TOO. ───────────────────────────────────────
  // Going in, the map ALREADY carries a declaration, and the control shows it — so the empty
  // selection is a real change rather than a no-op.
  {
    const env = buildEnv(src, {
      validDie: { basis: 'ref', keys: null, reason: '', ref: null, raw: STORED_REF },
      controlKey: STORED_REF.map_id,
    });
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    await pickFromSelect(env, '');
    eq('C/the clear was applied as 해제 (no declaration)', [null], env.applies.map(a => a.ref),
      'an empty selection must mean 원 기하 exactly as an empty input does');
    eq('C/the clear marks the frame unsaved', true, env.S.frameTouched);
    env.S.popMapFrame();
    eq('C/the pop prompted', 1, env.confirms.length,
      'clearing is the case most likely to be missed — it looks like nothing happened');
    eq('C/the 해제 toast still fires', true,
      env.toasts.some(t => t.msg.indexOf('유효 다이 지정을 해제했습니다') >= 0));
  }

  // ── D. A MERELY-VIEWED MAP GOES BACK IN SILENCE. [fix E] must not regress. ────────────
  // Two shapes, because the cell-count term this change removes used to be what (accidentally)
  // covered the second one.
  {
    const env = buildEnv(src, { gridData: {} });
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    env.S.popMapFrame();
    eq('D1/viewing an empty map is silent', 0, env.confirms.length);
  }
  {
    const env = buildEnv(src, {
      gridData: { '3_4': 'A1', '5_6': 'B2', '7_8': 'A1' },
      validDie: { basis: 'ref', keys: null, reason: '', ref: null, raw: STORED_REF },
      controlKey: STORED_REF.map_id,
    });
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    // Nothing is touched: the map is opened, its valid-die designation is looked at, and the
    // user leaves. This is the exact complaint [fix E] closed.
    env.S.popMapFrame();
    eq('D2/viewing a NON-EMPTY map with a declaration is silent', 0, env.confirms.length,
      'this is the [fix E] complaint; removing the cell-count term must not bring it back');
    eq('D2/...and no apply was invoked by merely looking', 0, env.applies.length);
  }
  {
    // The IME Enter is not a gesture: confirming a Korean composition must not apply anything,
    // and therefore must not dirty the frame either.
    const env = buildEnv(src);
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    await typeAndEnter(env, 'VD_MASK_A', { isComposing: true });
    eq('D3/an IME-composition Enter applies nothing', 0, env.applies.length);
    eq('D3/...and leaves the frame clean', false, env.S.frameTouched);
    env.S.popMapFrame();
    eq('D3/...so the pop is silent', 0, env.confirms.length);
  }
  {
    // A non-Enter keystroke in the input is typing, not a commit.
    const env = buildEnv(src);
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    env.el.validDieRefKey.value = 'VD_MA';
    env.el.validDieRefKey.__fire('keydown', { key: 'A' });
    await flush();
    eq('D4/typing without Enter applies nothing', 0, env.applies.length);
    eq('D4/...and leaves the frame clean', false, env.S.frameTouched);
  }

  // ── E. THE CELL-COUNT TERM. `clearGrid` empties gridData and IS an edit. ──────────────
  {
    const env = buildEnv(src, { gridData: { '3_4': 'A1', '5_6': 'B2' } });
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    env.S.clearGrid();                       // approve:true -> the clear goes through
    eq('E/clearGrid emptied the grid', 0, Object.keys(env.S.gridData).length);
    eq('E/clearGrid marked the frame', true, env.S.frameTouched);
    const confirmsBefore = env.confirms.length;
    env.S.popMapFrame();
    eq('E/clearing every value still prompts on the way back', confirmsBefore + 1, env.confirms.length,
      'the old `gridData` non-empty term made "delete everything" the one edit that vanished silently');
  }

  // ── F. WHICH WRITER THE PROMPT NAMES. ────────────────────────────────────────────────
  {
    const env = buildEnv(src);
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    await pickFromSelect(env, 'VD_MASK_A');
    env.S.popMapFrame();
    const text = env.confirms[0] || '';
    eq('F1/a declaration-only edit names 📐 규격만 저장', true, text.indexOf('📐 규격만 저장') >= 0,
      'Push rewrites every cell for a change that touched none');
    eq('F1/...and does NOT name ⚡ Push', false, text.indexOf('⚡ Push') >= 0,
      'naming the expensive option only is how people learn to push for everything');
    eq('F1/...and the declaration did not light the cell/legend draft flag', false, env.S.legendDirty,
      'legendDirty is what the plan head shows as unsaved plan work; a declaration is not that');
  }
  {
    const env = buildEnv(src, { gridData: { '3_4': 'A1' } });
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    env.S.scheduleCellDraft();               // a real cell write went through the draft gateway
    env.S.popMapFrame();
    const text = env.confirms[0] || '';
    eq('F2/a cell edit still names ⚡ Push', true, text.indexOf('⚡ Push') >= 0);
    eq('F2/...and does not offer the spec-only writer for it', false, text.indexOf('📐 규격만 저장') >= 0,
      '📐 규격만 저장 writes no cells, so offering it for a cell edit would lose the cells');
  }
  {
    // Both kinds of edit at once: the cell edit dominates, because the spec writer cannot
    // carry cells.
    const env = buildEnv(src, { gridData: { '3_4': 'A1' } });
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    await pickFromSelect(env, 'VD_MASK_A');
    env.S.persistLegend();
    env.S.popMapFrame();
    eq('F3/declaration + legend edit names ⚡ Push', true,
      (env.confirms[0] || '').indexOf('⚡ Push') >= 0);
  }

  // ── G. A PUSHED FRAME IS CLEAN; AN EDIT AFTER THE PUSH IS NOT. ───────────────────────
  {
    const env = buildEnv(src, { gridData: { '3_4': 'A1' } });
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    env.S.scheduleCellDraft();
    env.S.framePushed = true;                // what pushMapData sets on a recorded success
    env.S.popMapFrame();
    eq('G1/a pushed frame goes back in silence', 0, env.confirms.length);
  }
  {
    const env = buildEnv(src, { gridData: { '3_4': 'A1' } });
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    env.S.framePushed = true;
    await pickFromSelect(env, 'VD_MASK_A');  // ...and THEN the declaration changes
    eq('G2/an apply after a push re-arms the guard', false, env.S.framePushed,
      'the screen again holds something the server does not have');
    env.S.popMapFrame();
    eq('G2/...so the pop prompts', 1, env.confirms.length);
  }

  // ── H. END TO END: the prompt must not repeat after the user does what it says. ──────
  {
    const env = buildEnv(src);
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    await pickFromSelect(env, 'VD_MASK_A');
    eq('H/the frame is unsaved before the save', true, env.S.frameTouched);

    await env.S.saveMapSpecOnly();           // the writer the prompt names (confirm approved)
    const writes = env.requests.filter(r => r.method === 'PUT');
    eq('H/the spec save issued exactly one write', 1, writes.length);
    eq('H/...and it carried the declaration', STORED_REF,
      JSON.parse(JSON.parse(writes[0].body).updates[0].updates.grid_metadata).valid_die_ref,
      'if the save did not persist the ref, clearing the guard below would be a lie');
    eq('H/the guard is cleared by the cheaper writer', false, env.S.frameTouched);

    const before = env.confirms.length;
    env.S.popMapFrame();
    eq('H/the pop after the spec save is silent', before, env.confirms.length,
      'a prompt that asks again after the user did exactly what it said is a prompt that lied');
  }
  {
    // ...but the spec save must NOT clear a frame that also holds cell work — it writes no
    // cells, so those are still unsaved.
    const env = buildEnv(src, { gridData: { '3_4': 'A1' } });
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    await pickFromSelect(env, 'VD_MASK_A');
    env.S.scheduleCellDraft();
    await env.S.saveMapSpecOnly();
    eq('H2/a frame with cell work stays unsaved after a spec-only save', true, env.S.frameTouched);
    const before = env.confirms.length;
    env.S.popMapFrame();
    eq('H2/...and still prompts', before + 1, env.confirms.length);
    eq('H2/...naming ⚡ Push, because the cells are what is left', true,
      (env.confirms[env.confirms.length - 1] || '').indexOf('⚡ Push') >= 0);
  }

  // ── I. THE WIRING ITSELF. Both gestures must be bound, and blur must NOT be. ─────────
  {
    const env = buildEnv(src);
    eq('I/the key input binds focus + input + keydown, and NOT change',
      ['focus', 'input', 'keydown'], env.el.validDieRefKey.__listenerTypes(),
      'a `change` here fires on blur — leaving the box would re-seat the whole map (3-a)');
    eq('I/the select binds change', ['change'], env.el.validDieRefSelect.__listenerTypes());
  }
  {
    // The `<select>` must copy its value into the key input BEFORE applying — the key input is
    // the single source of truth and `onValidDieRefChanged` reads it, so a reversed order
    // applies the PREVIOUS value.
    const env = buildEnv(src, { controlKey: 'OLD_KEY' });
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    await pickFromSelect(env, 'VD_MASK_A');
    eq('I/the select writes the key input before applying', 'VD_MASK_A', env.el.validDieRefKey.value);
    eq('I/...so the applied declaration is the NEW one', [STORED_REF], env.applies.map(a => a.ref));
  }

  // ── J. THE SECOND DOOR: 📂 Load Existing Map. ────────────────────────────────────────
  // `loadExistingMap` discards the declaration in its first three statements, unconditionally
  // ([M4①]). That clearing is CORRECT and stays — whichever way a load ends, a mask from the
  // previous map must never assert itself over a different one. What was missing is that an
  // UNSAVED declaration was thrown away without asking. The frame here holds NO cells, which
  // is the everyday shape: declare the valid-die map, then load a different map.

  // J1 — the user's report, and what declining must do.
  {
    const env = buildEnv(src, { approve: false });
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    await pickFromSelect(env, 'VD_MASK_A');
    const before = JSON.stringify(env.S.validDie);

    const r = await env.S.loadExistingMap();

    eq('J1/the load asked before discarding', 1, env.confirms.length,
      'THIS IS THE USER REPORT: 0 here means 📂 Load silently releases the selection');
    // Declining must abort as completely as `popMapFrame` does — not merely return early.
    eq('J1/declining left the declaration APPLIED, byte for byte', before,
      JSON.stringify(env.S.validDie),
      'a partial clear is the same data loss with an extra dialog in front of it');
    eq('J1/...and left the key control showing it', 'VD_MASK_A', env.el.validDieRefKey.value);
    eq('J1/...and issued no request', [], env.requests.map(q => q.method));
    eq('J1/...and reports itself cancelled, so the nav instrument does not count a move',
      { count: 0, cancelled: true }, r);
    eq('J1/...and the frame is still marked unsaved', true, env.S.frameTouched);
    // 🔴 NO ASSERTION ON `btnLoadMap.textContent` HERE. It reads like a witness for "nothing
    //    started" and is not one: every exit path of the load restores the label, so it says
    //    the same thing whether the gate ran or not. It was written, measured against the
    //    corpus below, tripped by zero mutants, and removed. An assertion no defect can
    //    falsify is decoration that inflates the count.
  }

  // J1b — the OTHER thing the load destroys. Same decline, with cells on screen: `gridData`
  // is emptied inside the load's try block, so "declining aborts completely" has to cover it
  // too, not just the declaration.
  {
    const env = buildEnv(src, {
      approve: false,
      gridData: { '3_4': 'A1', '5_6': 'B2', '7_8': 'A1' },
    });
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    await pickFromSelect(env, 'VD_MASK_A');
    await env.S.loadExistingMap();
    eq('J1b/declining left the painted cells alone',
      { '3_4': 'A1', '5_6': 'B2', '7_8': 'A1' }, env.S.gridData);
    eq('J1b/...and the loaded-cell protection set', 0, env.S.loadedFCells.size);
  }

  // J2 — accepting loads, and the load leaves the designation ALONE on the way in.
  // ⚠️ THIS CASE USED TO ASSERT THE OPPOSITE. It read "the [M4①] clear ran — no mask survives
  //    into the next map" and required the key control to come back blank. That is the exact
  //    behaviour the user ruled out on 2026-08-04 (「고유 메타를 가진 맵을 불러오기 전까지 유효
  //    다이영역 초기화 금지」), so the assertion is inverted rather than deleted: the load in
  //    this leg ends at the step-③ refusal, and a refused load must return the screen the user
  //    left, not a screen nobody chose.
  {
    const env = buildEnv(src);
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    await pickFromSelect(env, 'VD_MASK_A');
    await env.S.loadExistingMap();

    eq('J2/accepting asked once', 1, env.confirms.length);
    eq('J2/...and the designation the user set is still in force after a refused load',
      { basis: 'circle', raw: STORED_REF },
      { basis: env.S.validDie.basis, raw: env.S.validDie.raw },
      'the wipe used to run in the first three statements, before a byte had been read');
    eq('J2/...and the key control still shows it', 'VD_MASK_A', env.el.validDieRefKey.value);
    eq('J2/...and the load actually went out', ['GET'], env.requests.map(q => q.method));
  }

  // J3 — `quiet` is the non-interactive flag this file already uses, and it stays silent.
  {
    const env = buildEnv(src, { approve: false });
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    await pickFromSelect(env, 'VD_MASK_A');
    await env.S.loadExistingMap({ quiet: true });
    eq('J3/a quiet load never prompts', 0, env.confirms.length,
      'openMapFrame snapshots this frame before calling; popMapFrame asks on the way back');
    eq('J3/...and proceeds', ['GET'], env.requests.map(q => q.method));
  }

  // J4 — BOOT RESTORE, executed rather than assumed. The frame is forced dirty on purpose:
  // that is stronger than the real boot state, and it proves the silence comes from `quiet`
  // rather than from the frame happening to be clean at that moment.
  {
    const env = buildEnv(src, { approve: false });
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    await pickFromSelect(env, 'VD_MASK_A');
    await env.S.restoreLastOpenMap();
    eq('J4/boot restore prompts zero times', 0, env.confirms.length,
      'there is no user edit at boot to protect, and a dialog on page load is not a guard');
    eq('J4/...and it did restore', ['GET'], env.requests.map(q => q.method));
  }

  // J5 — a merely-viewed map loads without a prompt, same rule as D2.
  {
    const env = buildEnv(src, {
      approve: false,
      gridData: { '3_4': 'A1', '5_6': 'B2' },
      validDie: { basis: 'ref', keys: null, reason: '', ref: null, raw: STORED_REF },
      controlKey: STORED_REF.map_id,
    });
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    await env.S.loadExistingMap();
    eq('J5/loading over a merely-VIEWED map is frictionless', 0, env.confirms.length,
      'reads stay frictionless; a stored declaration is not unsaved work');
    eq('J5/...and it loaded', ['GET'], env.requests.map(q => q.method));
  }

  // J6 — THE GATE'S POSITION. With no map key entered, the load's own `hasFilter` branch
  // raises an `alert`. If the gate sat after `collectMapKeyFilterModel`, that alert would come
  // FIRST and the prompt would never appear. Order is therefore readable as two counters.
  {
    const env = buildEnv(src, { approve: false, metaFilter: {} });
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    await pickFromSelect(env, 'VD_MASK_A');
    await env.S.loadExistingMap();
    eq('J6/the unsaved-work prompt comes first', 1, env.confirms.length);
    eq('J6/...before anything else with a side effect has run', [], env.alerts,
      'a prompt raised after collection is a prompt about a state that already started moving');
  }

  // J7 — the wording. Same writer advice as the back door (one function decides), different
  // first sentence, because replacing this map is not the same act as leaving it.
  {
    const env = buildEnv(src, { approve: false });
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    await pickFromSelect(env, 'VD_MASK_A');
    await env.S.loadExistingMap();
    const loadText = env.confirms[0] || '';
    eq('J7/it says what actually happens — the edit is replaced, not left behind', true,
      loadText.indexOf('다른 맵을 불러오면') >= 0 && loadText.indexOf('사라집니다') >= 0);
    eq('J7/...and it does not say 돌아가기, which is the other door', false,
      loadText.indexOf('돌아가기') >= 0);
    eq('J7/a declaration-only edit names the cheap writer here too', true,
      loadText.indexOf('📐 규격만 저장') >= 0);

    // Now the same frame with cell work, and the advice must flip in BOTH doors identically.
    env.S.scheduleCellDraft();
    await env.S.loadExistingMap();
    eq('J7/a cell edit names ⚡ Push at the load door', true,
      (env.confirms[1] || '').indexOf('⚡ Push') >= 0);
    env.S.popMapFrame();
    const popText = env.confirms[2] || '';
    eq('J7/...and the two doors give the SAME advice line for the SAME state', true,
      popText.indexOf('· 셀 값이 바뀌었습니다 — [⚡ Push]로 저장하십시오.') >= 0
        && (env.confirms[1] || '').indexOf('· 셀 값이 바뀌었습니다 — [⚡ Push]로 저장하십시오.') >= 0,
      'two spellings of this question is exactly how the two doors came to disagree');
  }

  // ══ K. THE CARRY RULING ═══════════════════════════════════════════════════════════════
  // 「고유 메타를 가진 맵을 불러오기 전까지 유효 다이영역 초기화 금지」 (user, 2026-08-04).
  //
  // THE WORKFLOW IS SET-THEN-LOAD. The user picks the valid-die designation and THEN opens
  // the map it applies to. The code assumed the reverse — that the map being opened brings
  // its own — and threw the designation away on the way in, at three separate sites.
  //
  // 🔴 WHY THIS LEG NEEDS THE REAL RESOLVER (measured, not assumed). Suppressing the two
  //    DIRECT wipes leaves the user's exact case still broken. Measured on the shipped file,
  //    with the designation seated and a map with no metadata loaded:
  //      · as shipped .................. control "VD_MASK_A" -> ""   BLANKED
  //      · direct wipe suppressed ...... control "VD_MASK_A" -> ""   BLANKED  (still!)
  //      · direct wipe + resolver ...... control "VD_MASK_A" -> "VD_MASK_A"  SURVIVED
  //    The second line is the whole reason this leg exists. The third clear does not live in
  //    `loadExistingMap`: `parseValidDieRef` answers null, `resolveValidDie` runs
  //    `set('circle', null, '', null)`, and `set` ends with `syncValidDieRefControls()`. A
  //    leg built on the recorder would report the third line while the product did the first.
  const CARRIED = { basis: 'ref', keys: new Set(['0_0', '1_0', '0_1']), reason: '',
    ref: { table: 'valid_die_ref', mapKey: 'VD_MASK_A' }, raw: STORED_REF };
  const carryOpts = (extra) => ({
    realResolve: true, validDie: CARRIED, controlKey: 'VD_MASK_A', ...extra,
  });
  const designation = (env) => ({
    control: env.el.validDieRefKey.value,
    basis: env.S.validDie.basis,
    keys: env.S.validDie.keys ? env.S.validDie.keys.size : null,
    raw: env.S.validDie.raw,
  });
  const CARRIED_SHAPE = { control: 'VD_MASK_A', basis: 'ref', keys: 3, raw: STORED_REF };
  // A metadata row that is real and complete and says NOTHING about valid-die. This is the
  // case QA found undecidable in the ruling as written: it reaches the same `set('circle')`
  // branch as a map with no row at all.
  const SILENT_META = {
    grid_cols: FRAME.cols, grid_rows: FRAME.rows, grid_start_x: 1, grid_start_y: 1,
    rotation: ROT, side: SIDE,
  };

  // K1 — THE USER'S EXACT CASE. Designation set, then a map with NO metadata is loaded.
  {
    const env = buildEnv(src, carryOpts({ declaredMeta: null }));
    const r = await env.S.loadExistingMap({ quiet: true });
    eq('K1/the designation survives a load of a map with no metadata',
      CARRIED_SHAPE, designation(env),
      'THIS IS THE REPORTED DEFECT: the control came back blank');
    eq('K1/...and the resolver was never asked to replace it', [], env.applies,
      'an undeclared map has nothing to replace it with, so it must not reach the resolver');
    eq('K1/...and the load itself succeeded', 0, r.count);
    evidence.push(`K1 designation after load: ${JSON.stringify(designation(env))}`);
  }

  // K2 — THE DECIDABILITY RULING. A metadata row exists and is silent about valid-die.
  // Ruled: silence is not a declaration. It leaves the user's choice standing, exactly as a
  // missing row does — the user is mid-setup, matching geometry by hand.
  {
    const env = buildEnv(src, carryOpts({ declaredMeta: SILENT_META }));
    await env.S.loadExistingMap({ quiet: true });
    eq('K2/a metadata row that is silent about valid-die does not replace the designation',
      CARRIED_SHAPE, designation(env),
      'having a row is not the same as declaring a valid die — the ruling turns on the key');
    eq('K2/...and it too never reached the resolver', [], env.applies);
  }

  // K3 — THE ONE CASE WHERE REPLACEMENT IS CORRECT. The loaded map declares its own.
  // ⚠️ What the declaration RESOLVES TO is not scored here (the reference lookup is stubbed to
  //    fail, so the basis lands on `refused`). What is scored is WHICH declaration is in force
  //    afterwards: the loaded map's, not the carried one.
  {
    const OWN = { table: 'valid_die_ref', map_id: 'VD_OWN_B' };
    const env = buildEnv(src, carryOpts({
      declaredMeta: { ...SILENT_META, valid_die_ref: OWN },
      // Cells, so the placement loop runs: the replacement has to be settled BEFORE it.
      cellRows: [
        { data: { x: { value: 7 }, y: { value: 3 }, val: { value: 'A1' } } },
        { data: { x: { value: 8 }, y: { value: 3 }, val: { value: 'B2' } } },
      ],
    }));
    await env.S.loadExistingMap({ quiet: true });
    // Read left to right: the resolver probed START under the carried basis, swapped, probed
    // START again under the new one, and only then were the two cells seated.
    eq('K3/the replacement was settled before a single cell was seated',
      ['1,1:ref', '1,1:refused', '7,3:refused', '8,3:refused'], env.seatedUnderBasis,
      'seeing the CARRIED basis here means the cells sat under one origin box and are read '
      + 'back under another — the silent coordinate shift, with the mask arriving late');
    eq('K3/a loaded map\'s own declaration replaces the carried designation',
      { control: 'VD_OWN_B', raw: OWN }, { control: env.el.validDieRefKey.value, raw: env.S.validDie.raw },
      'this is the one case where replacement is correct, and it must not be suppressed too');
    eq('K3/...via exactly one resolver call carrying THAT declaration', [OWN],
      env.applies.map(a => a.ref));
    eq('K3/...and the carried mask is gone', true, env.S.validDie.keys === null);
  }

  // K4 — an UNREADABLE declaration is still a declaration. `parseValidDieRef` is explicit
  // that only null/absence means "선언 없음", and keeping the previous mask under a broken
  // declaration is the wrong-answer-indistinguishable-from-right state this file refuses.
  {
    const env = buildEnv(src, carryOpts({
      declaredMeta: { ...SILENT_META, valid_die_ref: 12345 },
    }));
    await env.S.loadExistingMap({ quiet: true });
    eq('K4/an unreadable declaration replaces the designation and refuses',
      { basis: 'refused', raw: 12345 },
      { basis: env.S.validDie.basis, raw: env.S.validDie.raw });
    eq('K4/...and says so out loud', true,
      env.toasts.some(t => t.msg.indexOf('유효 다이 맵을 해석하지 못했습니다') >= 0),
      'a silent fallback to circle geometry is how a typo becomes a wrong mask');
  }

  // K5 — CLEAR SITE 1 OF 3: the bare table switch. No load at all. This is how the user
  // finally pinned the defect down: changing the table alone reset the designation.
  {
    const env = buildEnv(src, carryOpts({ realSwitch: true }));
    await env.S.switchTable('dt_map');
    eq('K5/switching tables does not reset the designation', CARRIED_SHAPE, designation(env),
      'no map was loaded, so nothing has declared anything to replace it with');
    eq('K5/...and the switch really ran', 'dt_map', env.S.selectedTable);
    eq('K5/...and it still dropped the identity pin', null, env.S.loadedIdentity);
  }

  // K6 — THE FAILURE EXITS. A load that fails must not leave a state nobody chose. The
  // strongest one is the no-map-key exit: it returns before `gridData` is cleared, so the
  // cells are still on screen and the old wipe stripped the designation from under them.
  {
    const env = buildEnv(src, carryOpts({
      metaFilter: {}, gridData: { '3_4': 'A1', '5_6': 'B2' },
    }));
    const r = await env.S.loadExistingMap({ quiet: true });
    eq('K6a/the no-map-key exit is a complete no-op for the designation',
      CARRIED_SHAPE, designation(env));
    eq('K6a/...and leaves the cells it never touched', { '3_4': 'A1', '5_6': 'B2' }, env.S.gridData);
    eq('K6a/...and issued no request', [], env.requests.map(q => q.method));
    eq('K6a/...and reports itself cancelled', { count: 0, cancelled: true }, r);
  }
  {
    // The step-③ refusal: the spec could not be confirmed. `gridData` IS cleared by then, so
    // the screen holds no cells and the user's own designation — chosen state, not stale state.
    const env = buildEnv(src, carryOpts({}));   // declaredMeta undefined -> {ok:false}
    await env.S.loadExistingMap({ quiet: true });
    eq('K6b/the spec-refusal exit keeps the designation too', CARRIED_SHAPE, designation(env));
    eq('K6b/...on an empty grid', {}, env.S.gridData);
  }

  // K7 — ORDERING. A carried designation moves where cells land (`getWaferBoundingBox` keys
  // the origin box off `basis === 'ref'`), so it has to be settled BEFORE the placement loop,
  // exactly as a declared one is. Measured at the moment each cell is seated.
  {
    const env = buildEnv(src, carryOpts({
      declaredMeta: SILENT_META,
      cellRows: [
        { data: { x: { value: 7 }, y: { value: 3 }, val: { value: 'A1' } } },
        { data: { x: { value: 8 }, y: { value: 3 }, val: { value: 'B2' } } },
      ],
    }));
    await env.S.loadExistingMap({ quiet: true });
    eq('K7/every cell was seated with the carried designation already in force',
      ['7,3:ref', '8,3:ref'], env.seatedUnderBasis,
      'a mask that lands after placement means the cells sat under one origin box and are '
      + 'read back under another — the silent coordinate shift this file exists to prevent');
    eq('K7/...and the designation is still the carried one afterwards',
      CARRIED_SHAPE, designation(env));
  }

  return { failures, compared, evidence };
}

// ── Mutants ─────────────────────────────────────────────────────────────────────────────
function once(src, find, repl) {
  const CR = String.fromCharCode(13);
  const toCrlf = (s) => s.split('\n').join(CR + '\n');
  if (src.indexOf(find) < 0 && src.indexOf(toCrlf(find)) >= 0) {
    find = toCrlf(find); repl = toCrlf(repl);
  }
  const i = src.indexOf(find);
  if (i < 0) die(`mutation anchor not found: ${find.slice(0, 70)}`);
  if (src.indexOf(find, i + 1) >= 0) die(`mutation anchor is not unique: ${find.slice(0, 70)}`);
  return src.slice(0, i) + repl + src.slice(i + find.length);
}

// ⚠️ EVERY ANCHOR BELOW IS MULTI-LINE OR CARRIES ITS OWN COMMENT TAIL. `  frameTouched = true;`
//    ALONE IS NOT UNIQUE in map_editor.js — `persistLegend` and `scheduleCellDraft` each spell
//    it — and a first-match replace would mutate a function this harness scores differently,
//    coming back as a hole that reads like coverage.
const MUTANTS = {
  // ── THE REPORTED REGRESSION, RESTORED EXACTLY. This mutant IS today's shipped code. ──
  'the-declaration-path-marks-nothing': (s) => once(s,
    ['  frameTouched = true;',
     '  framePushed = false;',
     '  if (key === \'\') {'].join('\n'),
    '  if (key === \'\') {'),
  // Half of it: marked, but the guard stays disarmed after a Push.
  'the-declaration-path-leaves-framePushed-set': (s) => once(s,
    ['  frameTouched = true;',
     '  framePushed = false;',
     '  if (key === \'\') {'].join('\n'),
    ['  frameTouched = true;',
     '  if (key === \'\') {'].join('\n')),
  // Marked in the wrong place: `resolveValidDie` is on the LOAD path too, so this is the
  // [fix E] complaint coming back — viewing a map would prompt.
  'the-mark-migrates-into-the-clearing-branch-only': (s) => once(s,
    ['  frameTouched = true;',
     '  framePushed = false;',
     '  if (key === \'\') {'].join('\n'),
    ['  if (key === \'\') {',
     '    frameTouched = true;',
     '    framePushed = false;'].join('\n')),
  // ── THE GUARD PREDICATE — now ONE function, so these mutate BOTH doors at once ──
  // The cell-count term, restored. Catches the empty-map declaration and `clearGrid`.
  'the-guard-requires-cells': (s) => once(s,
    '  if (framePushed || !frameTouched) return null;',
    '  if (framePushed || !frameTouched || !gridData || Object.keys(gridData).length === 0) return null;'),
  // The edit predicate is dropped, which is what made mere VIEWING prompt before [fix E].
  'the-guard-drops-the-edit-predicate': (s) => once(s,
    '  if (framePushed || !frameTouched) return null;',
    '  if (framePushed) return null;'),
  // The guard never fires at all.
  'the-guard-is-disarmed': (s) => once(s,
    '  if (framePushed || !frameTouched) return null;',
    '  return null;'),
  // A pushed frame is treated as dirty — the guard nags after a successful save.
  'the-guard-ignores-the-push': (s) => once(s,
    '  if (framePushed || !frameTouched) return null;',
    '  if (!frameTouched) return null;'),
  // Declining no longer keeps the user put.
  'declining-the-prompt-pops-anyway': (s) => once(s,
    '    `\\n[확인] 저장하지 않고 돌아가기\\n[취소] 이 화면에 남기`\n  )) return false;',
    '    `\\n[확인] 저장하지 않고 돌아가기\\n[취소] 이 화면에 남기`\n  )) { /* popped anyway */ }'),
  // ── THE PROMPT'S CONTENT ──
  // The advice names only the expensive writer, in both doors at once.
  'the-prompt-names-only-push': (s) => once(s,
    ['  return legendDirty',
     '    ? `· 셀 값이 바뀌었습니다 — [⚡ Push]로 저장하십시오.\\n`',
     '    : `· 셀은 하나도 바뀌지 않았습니다 — [📐 규격만 저장]이면 충분합니다.\\n`;'].join('\n'),
    '  return `· 이 맵을 [⚡ Push]로 저장하지 않았습니다.\\n`;'),
  // ...and the reverse: the cheap writer is offered for a CELL edit, which would lose cells.
  'the-prompt-offers-spec-only-for-cell-edits': (s) => once(s,
    ['  return legendDirty',
     '    ? `· 셀 값이 바뀌었습니다 — [⚡ Push]로 저장하십시오.\\n`',
     '    : `· 셀은 하나도 바뀌지 않았습니다 — [📐 규격만 저장]이면 충분합니다.\\n`;'].join('\n'),
    '  return `· 셀은 하나도 바뀌지 않았습니다 — [📐 규격만 저장]이면 충분합니다.\\n`;'),
  // ── THE SECOND DOOR ──
  // TODAY'S SHIPPED CODE, RESTORED EXACTLY: the load discards the declaration with no
  // question at all. This mutant IS the user's report.
  'the-load-door-has-no-guard': (s) => once(s,
    ['  if (!quiet) {',
     '    const notice = unsavedWorkNotice();',
     '    if (notice && !confirm(',
     '      `다른 맵을 불러오면 지금 화면의 편집이 사라집니다.\\n\\n` + notice +',
     '      `\\n[확인] 저장하지 않고 불러오기\\n[취소] 이 화면에 남기`',
     '    )) return { count: 0, cancelled: true };',
     '  }'].join('\n'),
    '  /* no guard */'),
  // The gate runs, but AFTER the map-key filter has been collected — so it is a dialog raised
  // about a state that already started changing, and the load's own `hasFilter` alert beats it.
  // ⚠️ RE-POINTED 2026-08-04. This mutant used to reinsert the block after the [M4①] wipe's
  //    last line. That wipe was DELETED by the carry ruling (clear site 2 of 3), so the anchor
  //    is gone; the landing spot moved to the next side effect on the same path rather than
  //    the mutant being dropped, because "the gate must come before anything with an effect"
  //    is still the contract and J6 is still what discriminates it.
  'the-load-gate-runs-after-the-clear': (s) => {
    const BLOCK = ['  if (!quiet) {',
      '    const notice = unsavedWorkNotice();',
      '    if (notice && !confirm(',
      '      `다른 맵을 불러오면 지금 화면의 편집이 사라집니다.\\n\\n` + notice +',
      '      `\\n[확인] 저장하지 않고 불러오기\\n[취소] 이 화면에 남기`',
      '    )) return { count: 0, cancelled: true };',
      '  }'].join('\n');
    const moved = once(s, BLOCK, '  /* moved below */');
    const LANDING = ['  el.btnLoadMap.textContent = \'📂 Loading...\';',
      '  el.btnLoadMap.disabled = true;'].join('\n');
    return once(moved, LANDING, BLOCK + '\n' + LANDING);
  },
  // The gate is there but non-interactive callers get it too — a dialog on page load.
  'the-load-gate-prompts-even-when-quiet': (s) => once(s,
    '  if (!quiet) {\n    const notice = unsavedWorkNotice();',
    '  if (true) {\n    const notice = unsavedWorkNotice();'),
  // Declining no longer aborts: the prompt appears and the load proceeds regardless.
  'declining-the-load-loads-anyway': (s) => once(s,
    '    )) return { count: 0, cancelled: true };\n  }',
    '    )) { /* loaded anyway */ }\n  }'),
  // ⚠️ THE POINT OF THIS ROUND. The load door spells the question a SECOND time instead of
  //    asking the shared one — which is exactly how the two doors came to disagree. The copy
  //    here is the pre-[fix E-2] predicate, the shape a second author would most plausibly
  //    write, and it is wrong for a declaration on a map with no cells.
  'the-load-door-spells-its-own-predicate': (s) => once(s,
    '  if (!quiet) {\n    const notice = unsavedWorkNotice();',
    ['  if (!quiet) {',
     '    const notice = (!framePushed && frameTouched && gridData',
     '      && Object.keys(gridData).length > 0)',
     '      ? `· 셀 값이 바뀌었습니다 — [⚡ Push]로 저장하십시오.\\n` : null;'].join('\n')),
  // ── THE END-TO-END LEG ──
  // The cheaper writer does not clear the guard, so the prompt repeats after the user obeys it.
  'the-spec-save-does-not-clear-the-guard': (s) => once(s,
    '    if (!legendDirty) frameTouched = false;\n    syncValidDieRefControls();',
    '    syncValidDieRefControls();'),
  // ...and the opposite: it clears unconditionally, throwing away the fact that CELLS are
  // still unsaved — this write does not carry a single cell.
  'the-spec-save-clears-the-guard-unconditionally': (s) => once(s,
    '    if (!legendDirty) frameTouched = false;\n    syncValidDieRefControls();',
    '    frameTouched = false;\n    syncValidDieRefControls();'),
  // ── THE WIRING ──
  // The select copies its value AFTER applying, so the PREVIOUS declaration is what lands.
  'the-select-applies-before-it-writes-the-key': (s) => once(s,
    ['      if (el.validDieRefKey) el.validDieRefKey.value = el.validDieRefSelect.value;',
     '      onValidDieRefChanged();'].join('\n'),
    ['      onValidDieRefChanged();',
     '      if (el.validDieRefKey) el.validDieRefKey.value = el.validDieRefSelect.value;'].join('\n')),
  // The IME guard is dropped: confirming a Korean composition becomes an apply.
  'the-ime-composition-enter-applies': (s) => once(s,
    '      if (e.isComposing || e.keyCode === 229) return;',
    '      /* IME guard dropped */'),
  // A `change` listener on the input, which fires on BLUR — leaving the box would re-seat the
  // map and dirty the frame. That is the behaviour 3-a removed.
  'the-key-input-regains-a-change-listener': (s) => once(s,
    '    el.validDieRefKey.addEventListener(\'input\', renderValidDieKeyControl);',
    ['    el.validDieRefKey.addEventListener(\'input\', renderValidDieKeyControl);',
     '    el.validDieRefKey.addEventListener(\'change\', onValidDieRefChanged);'].join('\n')),
  // ══ THE CARRY RULING — one mutant per clear site, so a future round cannot re-add one ══
  //    silently. Each RESTORES the shipped-today code at that site, verbatim, and nothing else.
  //
  // ⚠️ CLEAR SITE 1 OF 3 — the bare table switch. Restoring this alone reproduces the symptom
  //    the user pinned the whole defect down with: change the table, designation gone.
  'the-table-switch-clears-the-designation-again': (s) => once(s,
    ['    // 새 테이블의 자동완성 캐시를 버려 다음 포커스에서 다시 읽게 한다 — 전환 중에 그 테이블에',
     '    // 맵이 추가됐을 수 있고, 자동완성이 없는 것보다 **없는 맵을 제안하는 것**이 나쁘다.',
     '    mapKeyListCache.delete(tableName);'].join('\n'),
    ['    validDie = { basis: \'circle\', keys: null, reason: \'\', ref: null, raw: undefined };',
     '    renderValidDieChip();',
     '    syncValidDieRefControls();',
     '    mapKeyListCache.delete(tableName);'].join('\n')),
  // ⚠️ CLEAR SITE 2 OF 3 — the wipe in the load's first statements, restored verbatim.
  'the-load-wipes-the-designation-on-the-way-in': (s) => once(s,
    '  const { filterModel, hasFilter } = collectMapKeyFilterModel();   // ①',
    ['  validDie = { basis: \'circle\', keys: null, reason: \'\', ref: null, raw: undefined };',
     '  renderValidDieChip();',
     '  syncValidDieRefControls();',
     '  const { filterModel, hasFilter } = collectMapKeyFilterModel();   // ①'].join('\n')),
  // ⚠️ CLEAR SITE 3 OF 3 — THE ONE THAT SURVIVES NAIVE FIXES. The guard is dropped and the
  //    resolver is called unconditionally again, so an undeclared map reaches
  //    `set('circle', …)` and `set` blanks the control on its way out. Three repair rounds
  //    died here; if the K cases cannot see this mutant they are not scoring the defect.
  'the-load-lets-an-undeclared-map-reset-the-designation': (s) => once(s,
    ['    if (parseValidDieRef(loadedGridMeta, selectedTable) !== null) {',
     '      await resolveValidDie(loadedGridMeta, selectedTable, loadedMapKey || getCurrentMapKey());',
     '    }'].join('\n'),
    '    await resolveValidDie(loadedGridMeta, selectedTable, loadedMapKey || getCurrentMapKey());'),
  // The predicate is re-spelled as "does this map have a metadata ROW", which is the most
  // plausible wrong reading of 「고유 메타를 가진 맵」 — and it is wrong for exactly the case
  // QA flagged as undecidable: a row that says nothing about valid-die.
  'the-guard-asks-whether-a-metadata-row-exists': (s) => once(s,
    '    if (parseValidDieRef(loadedGridMeta, selectedTable) !== null) {',
    '    if (loadedGridMeta) {'),
  // The guard is inverted: the one case where replacement IS correct is the one suppressed.
  'the-guard-suppresses-the-declaration-that-should-win': (s) => once(s,
    '    if (parseValidDieRef(loadedGridMeta, selectedTable) !== null) {',
    '    if (parseValidDieRef(loadedGridMeta, selectedTable) === null) {'),
  // The resolver runs, but after the placement loop — the ordering the load path was built to
  // guarantee. Cells sit under one origin box and are read back under another.
  'the-resolution-lands-after-the-cells-are-placed': (s) => {
    const CALL = ['    if (parseValidDieRef(loadedGridMeta, selectedTable) !== null) {',
      '      await resolveValidDie(loadedGridMeta, selectedTable, loadedMapKey || getCurrentMapKey());',
      '    }'].join('\n');
    const moved = once(s, CALL, '    /* moved below */');
    return once(moved,
      '    // Auto detect legend from unique values',
      CALL + '\n    // Auto detect legend from unique values');
  },
  // ── NEGATIVE CONTROL. A comment-only edit must ESCAPE. A corpus that "catches" this is
  //    keying on source text rather than behaviour, and its caught column means nothing.
  '__control_comment_only': (s) => once(s,
    '  // [fix E] Prompt only when this frame was actually edited since it opened AND the',
    '  // [fix E] (reworded control mutant) prompt only on a real edit that was not pushed,'),
};

// ── main ────────────────────────────────────────────────────────────────────────────────
(async () => {
  const base = await run(SRC);
  if (verbose) base.evidence.forEach(e => console.log('  ' + e));
  console.log(`${base.failures.length === 0 ? '✓' : '✗'} baseline: ${base.compared} assertions, `
    + `${base.failures.length} failure(s)`);
  console.log(`ASSERTIONS ${base.compared} ${base.failures.length}`);
  base.failures.forEach(f => console.log(`   ✗ ${f}`));

  let caught = 0, total = 0;
  for (const [name, fn] of Object.entries(MUTANTS)) {
    const isControl = name.startsWith('__control');
    let f = [];
    try { f = (await run(fn(SRC))).failures; }
    catch (e) { f = [`threw: ${String(e && e.message).slice(0, 80)}`]; }
    const newOnes = f.filter(x => !base.failures.includes(x));
    if (isControl) {
      if (newOnes.length > 0) {
        console.log(`   ✗ CONTROL '${name}' was CAUGHT — the assertions are keying on source `
          + 'text, not on behaviour, and the caught count below is decoration');
        base.failures.push(`control mutant '${name}' was caught`);
      } else if (verbose) console.log(`   control '${name}': escaped, as required`);
      continue;
    }
    total++;
    if (newOnes.length > 0) caught++;
    else console.log(`   ✗ mutant '${name}' was NOT caught — the assertions above do not score `
      + 'what they claim to score');
    if (verbose) {
      console.log(`   mutant '${name}': ${newOnes.length} new failure(s)`);
      newOnes.forEach(x => console.log(`       · ${x}`));
    }
  }
  console.log(`--- mutation check: ${caught}/${total} defects caught ---`);
  process.exit(base.failures.length === 0 && caught === total ? 0 : 1);
})();
