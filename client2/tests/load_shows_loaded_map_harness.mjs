// Harness — 「맵을 로드하면 로드한 맵이 나온다」: `opts.restoreDraft` (2026-08-06).
//
// WHAT LANDED, AND WHY IT HAD NO SCORER. `e34d57d` gave `loadExistingMap` an
// `opts.restoreDraft` that defaults to FALSE, so the unsaved DOE/cell draft is applied only
// at page init (`restoreLastOpenMap`, the one caller that passes `true`). Before it, every
// load painted the operator's draft on top of the map they had just asked for — on a screen
// whose primary workflow is opening many maps in sequence. The commit shipped WITHOUT
// behaviour assertions and said so out loud. This file is that round.
// Run: node client2/tests/load_shows_loaded_map_harness.mjs   (no node_modules — vm sandbox)
//
// 🔴 THE FAILURE MODE IS AN OPERATOR'S UNSAVED WORK VANISHING, so "the flag was passed" is
//    not the thing to score. A version that passes `restoreDraft` and restores anyway would
//    satisfy every flag-shaped assertion. What is scored here is THE CANVAS: `gridData` must
//    hold the SERVER cells after a plain load and the SERVER ∪ DRAFT cells after a boot
//    restore, compared KEY BY VALUE against sets built in this file.
//
// ── WHY A NEW HOST, MEASURED RATHER THAN ASSUMED ────────────────────────────────────────
// The obvious candidate was `valid_die_dirty_guard_harness.mjs`: it already slices
// `loadExistingMap` + `restoreLastOpenMap` and stubs `localStorage`. Instrumented on
// 2026-08-06 it reports:
//     readRegistryScope reached ......... 84 times
//     restoreDoeDraftWithPrecedence ......  0 times  (on HEAD)
//     restoreDoeDraftWithPrecedence ...... 84 times  (on e34d57d^, the pre-change file)
// So that harness DOES reach the draft block — the reason it never calls the draft function
// is the very flag under test. It is still the wrong host, for two reasons that measurement
// also gives: its `restoreDoeDraftWithPrecedence` stub is an inert `() => ({false,false})`
// that no assertion reads, and every leg of it that carries CELLS dies inside the load's
// `try` on `LEGEND_PALETTE is not defined` and lands in the catch — so the server-cell axis,
// which is the whole of what this file compares, is unreachable there by construction.
//
// ⚠️ AND THAT IS WHY THIS FILE REFUSES TO SWALLOW. `loadExistingMap` wraps its body in one
//    big try/catch, so ANY unmodelled global in this sandbox becomes a silently aborted load
//    that still returns an object — a green run measuring nothing. Every load here goes
//    through `noSwallowed()`, which turns a recorded `console.error` into a HARNESS FAILURE
//    (exit 2), not into a quiet zero.
//
// ── WHAT IS REAL AND WHAT IS STUBBED, AND WHAT THE STUBS DO NOT MODEL ───────────────────
// REAL (sliced verbatim from map_editor.js): `loadExistingMap`, `restoreLastOpenMap`, the
// whole draft mechanism (`doeDraftKey` · `saveDoeDraft` · `readDoeDraft` ·
// `restoreDoeDraftWithPrecedence` · `applyDoeDraftRecord` · `applyDraftCells` ·
// `saveLegendToStorage` · `cellsDigest`), `getCurrentMapKey`, `recordLastOpenMap`,
// `setLoadedIdentity`, `unsavedWorkNotice`, `collectMapKeyFilterModel`,
// `scanCoordinateBounds`. `getMapIdFromMeta` is IMPORTED from `client2/src/map_key.js` —
// not stubbed — because the draft key is derived from it and section S is about that key.
// `localStorage` is a real store with a write log, so "byte-identical" is bytes.
//
// STUBBED, and what each does NOT model:
//   · `resolveDeclaredGridMeta` — always succeeds. Does not model the refusal exits; those
//     are owned by the load-path harnesses, and a refusal never reaches the draft block.
//   · `getCanvasCellFromDb` / `getDieIndex` — identity recorders `(frame,x,y) -> {c:x,r:y}`
//     and `(frame,c,r) -> {x:c,y:r}`. They do NOT model rotation, side, invertY or the
//     origin box; coordinate transformation is owned by `valid_die_head_parity_oracle` and
//     the overlay harnesses. What they buy here is that a server row's stored coordinate
//     lands on a PREDICTABLE `gridData` key, so "the canvas holds the server cells" is a
//     key→value comparison and not a resemblance. ⚠️ They take the FRAME as their leading
//     argument, matching the live signature: a recorder that kept the old shape would log a
//     frame as an x coordinate and silently collapse the cell set (measured defect class,
//     2026-08-06).
//   · `parseValidDieRef` — always `null`, so `resolveValidDie` is never reached. The fixture
//     declares no valid die; that axis has three harnesses of its own.
//   · `readRegistryScope` — returns `{ok:true, rows:[]}` (and `{ok:false}` for section F).
//     Section F exists because the FAILED-read branch restores the draft UNCONDITIONALLY,
//     with no `restoreDraft` gate at all, and that is deliberate (see the commit): there is
//     nothing loaded to be shown instead.
//   · The DOE half of a draft (`doe:{}` throughout). `applyDoeDraftRecord`'s normalizers
//     live in `split_registry_row.js`/`doe_bands.js`, which pull `transfer_plan.js` and a
//     `.css` import and cannot load under bare node. The draft's CELLS are the canvas and
//     the canvas is what the operator lost, so that is the axis scored here. `staleDraftKept`
//     is therefore driven through `hasCells`, not `hasDoe`.
//
// ── FIXTURE ACTIVITY (the negative controls in section P) ───────────────────────────────
// Server cells and draft cells are DISJOINT key sets with different values, and map A's key
// differs from map B's. If any of those collapsed, "the canvas holds the server cells" and
// "the canvas holds the draft cells" would be the same measurement and every green below
// would be evidence of nothing. P1–P6 assert that before anything else runs.
import { readFileSync } from 'node:fs';
import { loadWithProbe } from './lib/probe.mjs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';
import { getMapIdFromMeta } from '../src/map_key.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..', '..');
const SRC_PATH = join(ROOT, 'client2', 'src', 'map_editor.js');
const SRC = readFileSync(SRC_PATH, 'utf8').replace(/\r\n/g, '\n');
const verbose = process.argv.includes('--verbose');

// 🔴 THE REAL CONSOLE, CAPTURED AT LOAD. `buildEnv` installs a RECORDING console on
// `globalThis` so the two swallow points can be asserted on -- and that console ate this
// function's own message, leaving `exit 2` with no output at all. An instrument that goes
// blind under its own fault is worse than no instrument.
const OUT = console;
function die(msg) {
  OUT.error(`HARNESS FAILURE: ${msg}`);
  OUT.error('(This is not a passing result. Nothing was compared.)');
  process.exit(2);
}

// ── Extraction ──────────────────────────────────────────────────────────────────────────
// ⚠️ The body brace is found via the PARAMETER LIST, not `indexOf('{')`: `async function
//    loadExistingMap(opts = {})` has a brace in its default parameter and a naive scan
//    latches onto it and returns a truncated slice.
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

const SYMBOLS = [
  // the two doors under test
  'loadExistingMap', 'restoreLastOpenMap',
  // the draft mechanism, end to end and REAL — this is what an operator loses
  'doeDraftKey', 'cellsDigest', 'saveDoeDraft', 'readDoeDraft', 'clearDoeDraft',
  'saveLegendToStorage', 'applyDoeDraftRecord', 'applyDraftCells',
  'restoreDoeDraftWithPrecedence',
  // identity: the draft key is (table, mapKey), so the map key must be the real one
  'getCurrentMapKey', 'recordLastOpenMap', 'setLoadedIdentity',
  // the load's own steps that are pure over their arguments
  'collectMapKeyFilterModel', 'scanCoordinateBounds', 'gridDimNum', 'controlIsSilent',
  // the paint lock: `applyDraftCells` refuses to overwrite a protected cell
  'isOverlayLocked', 'isProtectedFCell',
  // the unsaved-work gate in front of the load door
  'unsavedWorkNotice',
];

const CONSTS = ['LAST_OPEN_KEY', 'DRAFT_VERSION'];

// ── Fixture ─────────────────────────────────────────────────────────────────────────────
const TABLE = 'bonding_map';
const TABLE_SCHEMA = { map_key_columns: ['lot_id'], column_types: { lot_id: 'text' } };
const META_A = { lot_id: 'LOT_A' };
const META_B = { lot_id: 'LOT_B' };
const MAPKEY_A = getMapIdFromMeta(META_A, TABLE_SCHEMA);
const MAPKEY_B = getMapIdFromMeta(META_B, TABLE_SCHEMA);

// The server's answer for map A. Anisotropic on purpose (x range != y range, neither starts
// at 0) so a stub that swapped or zeroed an axis would not land on the same key set.
const SERVER_ROWS_A = [
  { x: 2, y: 7, val: 'AA' },
  { x: 3, y: 7, val: 'AA' },
  { x: 5, y: 11, val: 'BB' },
];
const SERVER_CELLS_A = { '2_7': 'AA', '3_7': 'AA', '5_11': 'BB' };
// The operator's unsaved edits. DISJOINT keys, DIFFERENT value — see P1/P2.
const DRAFT_CELLS_A = { '9_1': 'ZZ', '10_2': 'ZZ' };
const MERGED_A = { ...SERVER_CELLS_A, ...DRAFT_CELLS_A };

const SERVER_ROWS_B = [{ x: 1, y: 4, val: 'CC' }];
const SERVER_CELLS_B = { '1_4': 'CC' };
const ROWS_BY_MAP = { [MAPKEY_A]: SERVER_ROWS_A, [MAPKEY_B]: SERVER_ROWS_B };

const GRID_META = { grid_cols: 20, grid_rows: 16, grid_start_x: 1, grid_start_y: 1,
  rotation: 0, side: 'front' };

const LEGEND_ROWS = (values) => values.map((v, i) => ({
  value: v, color: `#${i}${i}${i}`, desc: '', vocab: false,
  knobs: [], stack: '', mat_1h: [], mat_mid: [], mat_top: [],
}));

function makeInput(v) { return { value: String(v), checked: false, style: {}, dataset: {} }; }

// ── Sandbox ─────────────────────────────────────────────────────────────────────────────
/**
 * @param opts.meta          the meta-input dict in force (which map the screen is asking for)
 * @param opts.rows          what the server returns for the cell query
 * @param opts.gridData      what is on the canvas before the load
 * @param opts.registryOk    false -> the FAILED-read branch (section F)
 * @param opts.sentinelDraft true -> replace `restoreDoeDraftWithPrecedence` with a recording
 *                           stub that writes DRAFT_CELLS_A into gridData. Scores the CALL
 *                           SITE branch; sections C/F run the real one instead.
 * @param opts.store         a pre-seeded localStorage Map (carried between phases)
 */
async function buildEnv(src, opts = {}) {
  const toasts = [];
  const confirms = [];
  const alerts = [];
  const requests = [];
  const loadErrors = [];
  const draftCalls = [];        // every restoreDoeDraftWithPrecedence invocation, args verbatim
  const store = opts.store || new Map();
  const writeLog = [];          // [key, ...] in order, so "was it written" is not inferred
  let clock = 0;

  const metaInputs = Object.entries(opts.meta || META_A)
    .map(([col, val]) => ({ id: `meta-input-${col}`, value: String(val) }));

  const el = {
    gridCols: makeInput(GRID_META.grid_cols), gridRows: makeInput(GRID_META.grid_rows),
    gridStartX: makeInput(1), gridStartY: makeInput(1),
    gridYInvert: { checked: false },
    colMapX: makeInput('x'), colMapY: makeInput('y'), colMapVal: makeInput('val'),
    btnLoadMap: { disabled: false, textContent: '📂 Load Existing Map' },
    tableSelect: { value: TABLE, disabled: false, options: [{ value: TABLE }] },
    mapWorkspace: { scrollLeft: 0, scrollTop: 0 },
  };

  // 🔴 THE SYMBOLS ARE NO LONGER CUT OUT of map_editor.js and run in `vm`.
  //
  // THE `CONSTS` REPUBLISHING HACK IS GONE WITH IT, and it is worth saying why it existed:
  // `const` at script top level is LEXICAL, not a global property, so the sliced code could
  // read `LAST_OPEN_KEY` while `sandbox.LAST_OPEN_KEY` was `undefined` -- and seeding the boot
  // record under `undefined` made `restoreLastOpenMap` return in its second statement while
  // throwing nothing at all. That whole workaround was a cost of slicing. Imported, the consts
  // are simply in scope and the probe reads them.
  //
  // Retyped constants dropped: `LEGEND_PALETTE` (sentinels nothing here reads) and
  // `ROUTE_MATERIAL` (staged 'map_editor:material'; the product computes exactly that from
  // `ROUTES.MAP_EDITOR` -- same value, so the copy simply goes).
  //
  // Nine names are IMPORTS of the subject and no probe can reach an import binding, so they
  // come through the loader hook. `getMapIdFromMeta` is not among the stubs: this file already
  // imports the real one at the top, and that is the SAME module instance the subject sees.
  //
  // 🔴 TWO SWALLOW POINTS, BOTH RECORDED. `loadExistingMap`'s catch reports through
  //    `console.error`; `restoreLastOpenMap`'s own catch reports through `console.warn`
  //    ("last-open restore failed"). A harness that recorded only the first would read a
  //    boot restore that died in its opening statements as a boot restore that ran.
  globalThis.console = {
    log: (...a) => OUT.log(...a), info() {}, debug() {},
    warn(...a) {
      const s = a.map(x => String((x && x.stack) || x)).join(' ');
      if (s.includes('last-open restore failed')) loadErrors.push(s);
    },
    error(e) { loadErrors.push(String((e && e.stack) || (e && e.message) || e)); },
  };
  globalThis.setTimeout = (fn) => { void fn; return 0; };
  globalThis.clearTimeout = () => {};
  globalThis.confirm = (t) => { confirms.push(String(t)); return opts.approve !== false; };
  globalThis.alert = (t) => { alerts.push(String(t)); };
  globalThis.document = {
    querySelectorAll: (sel) => (sel === '[id^="meta-input-"]' ? metaInputs : []),
    getElementById: (id) => metaInputs.find(i => i.id === id) || null,
    addEventListener() {}, removeEventListener() {}, querySelector: () => null,
  };
  globalThis.window = globalThis.window || {
    location: { port: '', origin: '', protocol: 'http:', host: '', search: '' },
    addEventListener() {}, removeEventListener() {},
  };
  globalThis.localStorage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => { store.set(k, String(v)); writeLog.push(String(k)); },
    removeItem: (k) => { store.delete(k); },
  };

  // Everything the harness STAGES on the module. `state` is `Object.keys` of this, so a name
  // the module does not declare is a loud failure instead of a property nobody reads -- the
  // silent-no-op shape this round has already produced twice.
  const stage = {
    selectedTable: TABLE,
    tableSchema: TABLE_SCHEMA,
    currentRotation: 0,
    currentSide: 'front',
    // ── module state the load writes ──
    gridData: opts.gridData ? { ...opts.gridData } : {},
    gridCells2D: {},
    loadedFCells: new Set(),
    serverCellKeys: null,
    editorFrames: [],
    overlayLayers: [],
    overlayGeomSig: null,
    paintLockConfig: { enabled: false, blocking_values: [], from_overlay: [] },
    boundingBoxCache: {},
    loadedIdentity: null,
    legend: opts.legend ? opts.legend.map(l => ({ ...l })) : [],
    activeBrush: '',
    legendDirty: false,
    legendReplaceScope: null,
    legendConflict: null,
    legendSaveState: { status: 'idle', at: '', error: '' },
    draftBase: opts.draftBase || null,
    frameTouched: !!opts.frameTouched,
    framePushed: false,
    cellDraftTimer: null,
    validDie: { basis: 'circle', keys: null, reason: '', ref: null, raw: undefined },
    // ── the load body, stubbed to SUCCEED ────────────────────────────────────────────────
    // ③ always resolves, and it names the map key the META INPUTS resolve to — the same
    //    identity the draft key is built from, so the two cannot drift inside a case.
    resolveDeclaredGridMeta: async () => ({
      ok: true, gridMeta: GRID_META,
      mapKey: getMapIdFromMeta(Object.fromEntries(
        metaInputs.map(i => [i.id.replace('meta-input-', ''), i.value])), TABLE_SCHEMA),
    }),
    applyRoutedPreset: async () => {},
    promptCoordinateChoice: async () => 'meta',
    resolveGridFrame: () => ({
      cols: GRID_META.grid_cols, rows: GRID_META.grid_rows, startX: 1, startY: 1,
      invertY: false, rotation: 0, side: 'front',
    }),
    updateOrientationUI() {},
    clearOverlayLayers() {},
    parseValidDieRef: () => null,
    resolveValidDie: async () => { die('resolveValidDie was reached; the fixture declares no '
      + 'valid die, so this means parseValidDieRef stopped being consulted'); },
    isLockedValue: () => false,
    deriveLegendFromCellValues: (uniqueVals) => LEGEND_ROWS([...uniqueVals]),
    readRegistryScope: async () => (opts.registryOk === false
      ? { ok: false, error: 'harness: registry read refused' }
      : { ok: true, rows: [] }),
    applyRegistryRowsToLegend() {},
    seedEmptyDoe() {},
    renderLegendTable() {}, renderGridCanvas() {}, updateLegendCounts() {},
    renderValidDieChip() {},
    populateValidDieRefList() {}, renderValidDieKeyControl() {}, syncValidDieRefControls() {},
    restoreEditorState() {}, renderBreadcrumb() {},
    effortRoute: () => 'map_editor',
    switchTable: async () => {},
    // ⚠️ THE FRAME IS THE LEADING ARGUMENT, matching the live signature. These do not model
    //    rotation/side/invertY — see the header. `_frame` is unused on purpose.
    getCanvasCellFromDb: (_frame, x, y) => ({ c: Number(x), r: Number(y) }),
    getDieIndex: (_frame, c, r) => ({ x: c, y: r }),
    // 🔴 THE SERVER'S ANSWER DEPENDS ON WHICH MAP WAS ASKED FOR. A stub that returned one
    //    fixed row set would make "loading B" indistinguishable from "loading A", and
    //    section S — which is entirely about one map's slot surviving another map's load —
    //    would be comparing a screen against itself. The filter is decoded out of the URL
    //    the load actually built, not read from an option.
    fetch: (url) => {
      requests.push(String(url));
      const m = /filters=([^&]*)/.exec(String(url));
      let asked = null;
      try {
        const fm = JSON.parse(decodeURIComponent(m ? m[1] : '{}'));
        asked = getMapIdFromMeta(
          Object.fromEntries(Object.entries(fm).map(([c, f]) => [c, f.filter])), TABLE_SCHEMA);
      } catch (e) { void e; }
      const rows = (ROWS_BY_MAP[asked] || []).map(r => ({
        data: { x: { value: r.x }, y: { value: r.y }, val: { value: r.val } },
      }));
      return Promise.resolve({ ok: true, status: 200, json: async () => ({ data: rows }) });
    },
  };

  const { probe } = await loadWithProbe(SRC_PATH, {
    // `restoreDoeDraftWithPrecedence` is in SYMBOLS, but it is STAGED below rather than merely
    // called, and `state` already gives both a getter and a setter -- asking for it twice is
    // a duplicate key in the appended object, which the probe refuses outright.
    expose: [...SYMBOLS.filter(n => n !== 'restoreDoeDraftWithPrecedence'), ...CONSTS, 'el'],
    // 🔴 `restoreDoeDraftWithPrecedence` is staged AFTER the import (the ⑦ sentinel below
    //    wraps or replaces it), so it cannot come from `stage`. It has to be named here or
    //    the assignment lands on a property the module never reads -- which it did, and the
    //    draft block was then never reached.
    state: [...Object.keys(stage), 'restoreDoeDraftWithPrecedence'],
    stubs: {
      './config.js': { API_BASE: '/api', CURRENT_USER: 'tester' },
      './utils.js': {
        showToast: (msg, kind) => toasts.push({ msg: String(msg), kind }),
        // ⚠️ MONOTONIC, not fixed. A fixed timestamp would make a REWRITE of a draft slot
        //    byte-identical to the thing it replaced, and section S/D compare bytes.
        getLocalTimeString: () => `T${String(++clock).padStart(4, '0')}`,
      },
      './transfer_plan.js': { notifyLegendChanged: () => {}, notifyMapContext: () => {} },
      './split_registry_row.js': {
        registryFingerprint: (rows) => `REGFP:${JSON.stringify(rows)}`,
      },
      './effort_meter.js': { countNav: () => {} },
    },
    mutate: typeof src === 'function' ? src : undefined,
    tag: 'loadshows',
  });

  const sandbox = probe;
  Object.assign(sandbox.el, el);
  Object.assign(sandbox, stage);

  // ── ⑦'s SENTINEL. Replaces the real function with one that writes a KNOWN, DISJOINT cell
  //    set into the LIVE `gridData` (the load reassigns the binding, so it is read at call
  //    time, never captured). Argument order is pinned by recording all four positionally:
  //    a stub that drifted from the real signature is the third census axis this repository
  //    keeps paying for.
  if (opts.sentinelDraft) {
    sandbox.restoreDoeDraftWithPrecedence = (table, mapKey, serverFp, serverCellsFp) => {
      draftCalls.push({ table, mapKey, serverFp, serverCellsFp });
      Object.assign(sandbox.gridData, DRAFT_CELLS_A);
      return { restoredUnsavedEdits: true, staleDraftKept: false };
    };
  } else {
    const real = sandbox.restoreDoeDraftWithPrecedence;
    sandbox.restoreDoeDraftWithPrecedence = (table, mapKey, serverFp, serverCellsFp) => {
      draftCalls.push({ table, mapKey, serverFp, serverCellsFp });
      return real(table, mapKey, serverFp, serverCellsFp);
    };
  }

  return { S: sandbox, el, metaInputs, store, writeLog, toasts, confirms, alerts,
    requests, loadErrors, draftCalls };
}

/**
 * 🔴 THE ANTI-SWALLOW GUARD. `loadExistingMap` catches everything, so an unmodelled global
 *    would abort the load and still return an object — the assertions below would then be
 *    scoring an empty screen and calling it "the server cells". This turns that into a
 *    harness failure, which is the honest outcome.
 */
function noSwallowed(env, where) {
  if (env.loadErrors.length > 0) {
    die(`the load threw and its own catch swallowed it (${where}): `
      + JSON.stringify([...new Set(env.loadErrors)])
      + ' — the sandbox is missing something the load reads, so nothing below measured anything.');
  }
}

function setMeta(env, meta) {
  env.metaInputs.length = 0;
  Object.entries(meta).forEach(([col, val]) =>
    env.metaInputs.push({ id: `meta-input-${col}`, value: String(val) }));
}

/** Seed a draft the way the app does: through the REAL saveDoeDraft, at the REAL key. */
function seedDraftAs(env, meta, cells, baselineCellsFp) {
  setMeta(env, meta);
  const mapKey = getMapIdFromMeta(meta, TABLE_SCHEMA);
  env.S.gridData = { ...cells };
  env.S.draftBase = { table: TABLE, mapKey, registryFp: 'REGFP:[]', cellsFp: baselineCellsFp };
  env.S.saveDoeDraft();
  return { mapKey, key: env.S.doeDraftKey(TABLE, mapKey) };
}

// ── Cases ───────────────────────────────────────────────────────────────────────────────
// `isBaseline` gates the hard reachability abort ONLY. A mutant is *supposed* to be able to
// stop the draft block being called (that is `boot-restore-stops-asking-for-the-draft`), and
// aborting the process there would take the whole corpus down with it.
async function run(src, isBaseline = false) {
  const failures = [];
  const evidence = [];
  let compared = 0;
  const eq = (name, expected, actual, note) => {
    compared++;
    const a = JSON.stringify(actual), e = JSON.stringify(expected);
    if (a !== e) failures.push(`${name}: expected ${e}, got ${a}${note ? ` — ${note}` : ''}`);
  };

  // ══ P. FIXTURE ACTIVITY. Without these, every green below could be evidence of nothing. ══
  {
    const sKeys = Object.keys(SERVER_CELLS_A);
    const dKeys = Object.keys(DRAFT_CELLS_A);
    const overlap = sKeys.filter(k => dKeys.includes(k));
    eq('P1/server cells and draft cells are DISJOINT', [], overlap,
      'if they overlapped, "the canvas holds the server cells" and "…the draft cells" would '
      + 'be the same measurement');
    eq('P2/the draft actually carries cells', 2, dKeys.length);
    eq('P3/the server actually returns cells', 3, sKeys.length);
    eq('P4/map A and map B resolve to DIFFERENT keys', true, MAPKEY_A !== MAPKEY_B,
      'section S compares one map\'s draft slot across a load of the other');
    const env0 = await buildEnv(src, {});
    eq('P5/…and therefore to different draft slots', true,
      env0.S.doeDraftKey(TABLE, MAPKEY_A) !== env0.S.doeDraftKey(TABLE, MAPKEY_B));
    eq('P6/the draft key carries BOTH the table and the map', true,
      env0.S.doeDraftKey(TABLE, MAPKEY_A).includes(TABLE)
        && env0.S.doeDraftKey(TABLE, MAPKEY_A).includes(String(MAPKEY_A)),
      'a key that dropped the map component would make one map\'s load overwrite another\'s draft');
    evidence.push(`P/ mapKey A=${MAPKEY_A} B=${MAPKEY_B}; slot A=${env0.S.doeDraftKey(TABLE, MAPKEY_A)}`);
  }

  // ══ R. REACHABILITY. The host must genuinely execute the draft block. ═══════════════════
  // A harness that runs and scores nothing is worse than a named gap, so this is measured
  // twice: the sentinel is invoked (boot restore), and `draftBase` — the statement
  // IMMEDIATELY BEFORE the call — is established on a plain load, which is how we know the
  // plain-load zero is "the branch chose not to call" and not "the block was never reached".
  {
    const env = await buildEnv(src, { sentinelDraft: true });
    env.store.set(env.S.LAST_OPEN_KEY,
      JSON.stringify({ v: 1, table: TABLE, metaValues: META_A, at: 'T0' }));
    await env.S.restoreLastOpenMap();
    noSwallowed(env, 'R/boot restore');
    if (isBaseline && env.draftCalls.length === 0) {
      die('the draft block was NEVER reached under restoreDraft:true. This host scores '
        + 'nothing about the change and must not be reported as a test.');
    }
    // `|| {}` so a mutant that removes the call fails R1..R4 instead of crashing the corpus.
    const call = env.draftCalls[0] || {};
    eq('R1/boot restore reaches ⑦ exactly once', 1, env.draftCalls.length);
    eq('R2/…with (table, mapKey) in that order', { table: TABLE, mapKey: MAPKEY_A },
      { table: call.table, mapKey: call.mapKey },
      'a stub that drifted from the real signature would record a fingerprint as a table name');
    eq('R3/…and the CELL fingerprint is the just-loaded server state, computed independently',
      env.S.cellsDigest(SERVER_CELLS_A), call.serverCellsFp,
      'the precedence check is only meaningful if arg 4 is the baseline this load just read');
    eq('R4/…and the registry fingerprint is the read answer', 'REGFP:[]', call.serverFp);
    // ── R4b: THE POSITIVE TWIN OF S3, ADDED TO CLOSE A SURVIVING MUTANT ──────────────────
    // 🔴 S3 says the persist must NOT happen on a plain load. Nothing said it MUST happen
    //    anywhere, so deleting `if (!staleDraftKept) saveLegendToStorage()` on EVERY path was
    //    invisible to this file (mutant `the-persist-that-eats-the-draft-is-removed` survived
    //    the round that repaired the defect). A prohibition with no matching obligation scores
    //    "never" the same as "only where it is wrong".
    //    On THIS path `staleDraftKept` is legitimately `false` and the persist is correct and
    //    necessary: the boot restore has just replayed the operator's draft onto a canvas whose
    //    baseline fingerprints were established by THIS load, so the slot must be rewritten
    //    against that baseline — otherwise the next refresh reads a draft whose `cellsFp`
    //    predates the load and the precedence check rejects the operator's own edits as stale.
    // ⚠️ THE DRAFT KEY SPECIFICALLY, the same distinction S3 makes: `map_editor_last_open` is
    //    NOT a draft slot, it records WHICH map was open, and it must still be written here.
    //    Read from the SAME write log section S reads; nothing is inferred from the store's
    //    contents (a rewrite with identical bytes is a write, and a seed is not).
    eq('R4b/…and the boot restore DOES re-persist map A\'s own draft slot',
      [env.S.doeDraftKey(TABLE, MAPKEY_A)],
      [...new Set(env.writeLog)].filter(k => k.includes('draft')),
      'S3 forbids this persist on a plain load; without this twin, removing it EVERYWHERE '
      + 'also passes — and then a restored draft is never re-baselined');
    evidence.push(`R4b/ writes during the boot restore: ${JSON.stringify([...new Set(env.writeLog)])}`);
  }
  {
    const env = await buildEnv(src, { sentinelDraft: true });
    await env.S.loadExistingMap();
    noSwallowed(env, 'R/plain load');
    eq('R5/a plain load REACHES the block (draftBase is the statement just above ⑦)',
      { table: TABLE, mapKey: MAPKEY_A, cellsFp: env.S.cellsDigest(SERVER_CELLS_A) },
      env.S.draftBase
        ? { table: env.S.draftBase.table, mapKey: env.S.draftBase.mapKey,
            cellsFp: env.S.draftBase.cellsFp }
        : null,
      'if this were null the zero below would mean "unreached", not "not restored"');
    eq('R6/…and does NOT call ⑦', 0, env.draftCalls.length);
  }

  // ══ A. THE CANVAS AFTER A PLAIN LOAD — the product owner's sentence. ════════════════════
  {
    const env = await buildEnv(src, { sentinelDraft: true, gridData: { '99_99': 'STALE' } });
    await env.S.loadExistingMap();
    noSwallowed(env, 'A/plain load');
    eq('A1/the canvas is the SERVER cells, key for key', SERVER_CELLS_A, env.S.gridData,
      'THIS IS THE REPORTED DEFECT: any DRAFT_CELLS_A key here means the load painted the '
      + 'draft over the map the operator asked for');
    eq('A2/…no draft key reached the canvas', [],
      Object.keys(DRAFT_CELLS_A).filter(k => k in env.S.gridData));
    eq('A3/…and the pre-load canvas was replaced, not merged', false, '99_99' in env.S.gridData);
    eq('A4/…the unsaved chip is not lit by a load that restored nothing', false, env.S.legendDirty);
    eq('A5/…and no 초안 복구 toast was shown', [],
      env.toasts.filter(t => t.msg.includes('미저장 초안 복구')).map(t => t.msg));
  }
  {
    // 🔴 `quiet` MUST NOT IMPLY RESTORE. The commit refused to fold the two together; this is
    //    the assertion that makes that refusal falsifiable. `openMapFrame` loads quietly.
    const env = await buildEnv(src, { sentinelDraft: true });
    await env.S.loadExistingMap({ quiet: true });
    noSwallowed(env, 'A/quiet load');
    eq('A6/a QUIET load restores nothing — quiet is a display decision', 0, env.draftCalls.length);
    eq('A7/…and its canvas is the server cells', SERVER_CELLS_A, env.S.gridData);
  }
  {
    // allowEmpty is the other caller-side flag on this door; it must not imply restore either.
    const env = await buildEnv(src, { sentinelDraft: true });
    await env.S.loadExistingMap({ quiet: true, allowEmpty: true });
    noSwallowed(env, 'A/allowEmpty load');
    eq('A8/allowEmpty does not imply restore', 0, env.draftCalls.length);
  }

  // ══ B. THE CANVAS AFTER A BOOT RESTORE — the other half of the contract. ════════════════
  {
    const env = await buildEnv(src, { sentinelDraft: true });
    env.store.set(env.S.LAST_OPEN_KEY,
      JSON.stringify({ v: 1, table: TABLE, metaValues: META_A, at: 'T0' }));
    await env.S.restoreLastOpenMap();
    noSwallowed(env, 'B/boot restore');
    eq('B1/the canvas is SERVER ∪ DRAFT', MERGED_A, env.S.gridData,
      'a refresh is 「hand me back what I was doing」; losing the draft here is the mirror defect');
    eq('B2/…and the chip says unsaved, because the server has none of it', true, env.S.legendDirty);
  }

  // ══ C. THE SAME TWO PATHS THROUGH THE REAL DRAFT MACHINERY, NOT A SENTINEL. ═════════════
  // The sentinel scores the call-site branch. This scores what an operator actually stored:
  // a v4 record in localStorage, read back by the real `readDoeDraft`, applied by the real
  // `applyDraftCells` under the real fingerprint precedence.
  const realDraftRecord = (cells, cellsFp) => JSON.stringify({
    v: 4, at: 'T-op', registryFp: 'REGFP:[]', cellsFp, doe: {}, cells,
  });
  {
    const probe = await buildEnv(src, {});
    const baseFp = probe.S.cellsDigest(SERVER_CELLS_A);
    const slot = probe.S.doeDraftKey(TABLE, MAPKEY_A);

    const env = await buildEnv(src, {});
    env.store.set(slot, realDraftRecord(MERGED_A, baseFp));
    await env.S.loadExistingMap();
    noSwallowed(env, 'C/plain load, real draft');
    eq('C1/a plain load shows the server map even with a FRESH draft in storage',
      SERVER_CELLS_A, env.S.gridData);
    eq('C2/…the real ⑦ was not called', 0, env.draftCalls.length);

    const env2 = await buildEnv(src, {});
    env2.store.set(slot, realDraftRecord(MERGED_A, baseFp));
    env2.store.set(env2.S.LAST_OPEN_KEY,
      JSON.stringify({ v: 1, table: TABLE, metaValues: META_A, at: 'T0' }));
    await env2.S.restoreLastOpenMap();
    noSwallowed(env2, 'C/boot restore, real draft');
    eq('C3/a boot restore replays the stored draft over the server map', MERGED_A, env2.S.gridData);
    eq('C4/…and says so', true,
      env2.toasts.some(t => t.msg.includes('미저장 초안 복구') && t.msg.includes('셀 2개')));
    evidence.push(`C4/ toast: ${JSON.stringify(
      (env2.toasts.find(t => t.msg.includes('미저장 초안 복구')) || {}).msg || null)}`);
  }
  {
    // The precedence rule still holds at boot: a draft whose baseline no longer matches the
    // server is NOT applied and NOT discarded. This is what stops a stale draft from erasing
    // somebody else's save.
    const probe = await buildEnv(src, {});
    const slot = probe.S.doeDraftKey(TABLE, MAPKEY_A);
    const env = await buildEnv(src, {});
    env.store.set(slot, realDraftRecord(MERGED_A, 'STALE:0'));
    env.store.set(env.S.LAST_OPEN_KEY,
      JSON.stringify({ v: 1, table: TABLE, metaValues: META_A, at: 'T0' }));
    await env.S.restoreLastOpenMap();
    noSwallowed(env, 'C/stale draft');
    eq('C5/a STALE draft is not applied at boot either', SERVER_CELLS_A, env.S.gridData);
    eq('C6/…and it is not discarded', realDraftRecord(MERGED_A, 'STALE:0'), env.store.get(slot),
      '「적용하지 않되 버리지도 않는다」 — the persist is skipped while a stale draft is kept');
    eq('C7/…and the screen is told', true,
      env.toasts.some(t => t.msg.includes('초안보다 서버본이 최신')));
  }

  // ══ F. THE FAILED-READ BRANCH IS DELIBERATELY UNGATED. ══════════════════════════════════
  // There is no `restoreDraft` here and that is on purpose: the registry read failed, so
  // there is no loaded plan to show instead, and refusing would strand the work. Pinned
  // because it is the ONE exception to 「로드한 맵이 나온다」 and a future tidy-up would
  // "fix the inconsistency" and silently empty the screen.
  {
    const probe = await buildEnv(src, {});
    const slot = probe.S.doeDraftKey(TABLE, MAPKEY_A);
    const env = await buildEnv(src, { registryOk: false });
    env.store.set(slot, realDraftRecord(MERGED_A, probe.S.cellsDigest(SERVER_CELLS_A)));
    await env.S.loadExistingMap();
    noSwallowed(env, 'F/registry read failed');
    eq('F1/a FAILED registry read still surfaces the draft on a plain load', MERGED_A, env.S.gridData,
      'nothing was loaded to be shown instead; emptying the screen here loses the work');
    eq('F2/…and saving is put on hold, by name', 'unknown-server-state', env.S.legendSaveState.status);
    eq('F3/…and draftBase is NOT established — this screen is not from the server', null,
      env.S.draftBase);
  }

  // ══ S. SURVIVAL: EDIT MAP A, LOAD MAP B, A'S SLOT IS BYTE-IDENTICAL. ════════════════════
  // True today by construction (the slot is keyed by map), which is exactly why it is pinned:
  // a change to the key shape breaks it in silence and nothing else in this repository would
  // say so. Seeded through the REAL `saveDoeDraft` so the key under test is the product's.
  {
    const env = await buildEnv(src, { frameTouched: true });
    const baseFp = env.S.cellsDigest(SERVER_CELLS_A);
    const { key: slotA } = seedDraftAs(env, META_A, MERGED_A, baseFp);
    const snapshotA = env.store.get(slotA);
    eq('S0/the seed is a real draft carrying the operator\'s cells', MERGED_A,
      JSON.parse(snapshotA).cells);

    // now the operator opens a different map
    setMeta(env, META_B);
    env.S.legendDirty = true;                     // there IS unsaved work; the door will ask
    env.writeLog.length = 0;
    const r = await env.S.loadExistingMap();
    void r;
    noSwallowed(env, 'S/load map B');
    eq('S1/the load asked before discarding', 1, env.confirms.length);
    eq('S2/map A\'s draft slot is BYTE-IDENTICAL after loading map B', snapshotA,
      env.store.get(slotA),
      'THE FAILURE MODE IS AN OPERATOR\'S UNSAVED WORK VANISHING; the slot is keyed by map');
    const slotB = env.S.doeDraftKey(TABLE, MAPKEY_B);
    // S3 RE-DERIVED 2026-08-06. It used to require map B's slot to be WRITTEN during the load,
    // as a control proving S2 was not passing on a key shape that had lost its map component.
    // That write WAS the re-baseline persist, and the repair removes it: re-persisting a slot
    // from the server copy just read is exactly what destroyed map A's unsaved edits. So the
    // control has to buy its protection another way — S4 compares the two keys directly, and
    // D1-D3 below prove the slot still reads back as the operator's edits.
    eq('S3/NEGATIVE CONTROL — a plain load re-persists no draft slot at all', [],
      [...new Set(env.writeLog)].filter(k => k.startsWith('doe_draft') || k.includes('draft')),
      'a plain load must not re-baseline ANY draft slot; that persist is the deletion. '
      + '(`map_editor_last_open` is not a draft — it records WHICH map was open and must '
      + 'still be written, or a refresh forgets the map that was just loaded.)');
    eq('S4/…and the two slots are different strings', true, slotA !== slotB);
    evidence.push(`S/ writes during the load of B: ${JSON.stringify([...new Set(env.writeLog)])}`);
  }
  {
    // Same shape, one step further: A's slot still READS BACK as A's edits afterwards.
    const env = await buildEnv(src, { frameTouched: true });
    const baseFp = env.S.cellsDigest(SERVER_CELLS_A);
    const { key: slotA } = seedDraftAs(env, META_A, MERGED_A, baseFp);
    setMeta(env, META_B);
    await env.S.loadExistingMap({ quiet: true });
    noSwallowed(env, 'S/read-back');
    eq('S5/A\'s draft still reads back as A\'s edits', MERGED_A,
      env.S.readDoeDraft(TABLE, MAPKEY_A).cells);
    eq('S6/…and the canvas is map B\'s server cells', SERVER_CELLS_B, env.S.gridData);
    void slotA;
  }

  // ══ D. ⚠️ CHARACTERIZED DEFECT — LOADING A MAP EMPTIES **THAT MAP'S OWN** DRAFT SLOT. ════
  //
  // 🔴 THIS SECTION PINS WHAT THE CODE DOES, NOT WHAT IT SHOULD DO. It is here so the
  //    behaviour is measured rather than argued about, and so the repair has an acceptance
  //    test the day someone writes it. It is NOT an endorsement.
  //
  //    e34d57d's message says: "The draft is not deleted, only not applied -- it stays under
  //    its (table, mapKey) key for the next refresh." That holds for OTHER maps — section S
  //    proves it — and does NOT hold for the map being loaded. The load's registry block ends
  //        if (!staleDraftKept) saveLegendToStorage();   // -> saveDoeDraft(), cells included
  //    and with the restore skipped, `staleDraftKept` is hard-wired `false`, so the slot is
  //    re-persisted from the just-read SERVER state. That line was safe BEFORE the change for
  //    two reasons, and the change removed both: the draft had either been APPLIED (so
  //    re-persisting wrote it back unchanged) or been kept as STALE (so the persist was
  //    skipped). Consequence: 편집 → 📂 로드 → 새로고침 now recovers nothing. The refresh path
  //    the commit names as the safety net is the path this closes.
  //
  // 📏 MEASURED BOTH WAYS, 2026-08-06 (this same section, run against e34d57d^):
  //        pre-change  slot A after the load = 2_7 | 3_7 | 5_11 | 9_1 | 10_2   (edits kept)
  //        post-change slot A after the load = 2_7 | 3_7 | 5_11                (edits gone)
  //    ⚠️ THE SLOT IS REWRITTEN IN BOTH VERSIONS — `D1` is true before and after and on its
  //       own distinguishes nothing. `D2` is where the loss is, and D1 exists only to say
  //       out loud that a write happens at all (otherwise D2's value could be read as "the
  //       seed was never stored").
  // 🔴 WHEN THIS IS REPAIRED, D2/D3 GO RED AND THAT IS THE ACCEPTANCE TEST — the corpus
  //    already carries the candidate repair as a mutant. Invert them to MERGED_A and raise
  //    the floor; do not delete them.
  {
    const env = await buildEnv(src, { frameTouched: true });
    const baseFp = env.S.cellsDigest(SERVER_CELLS_A);
    const { key: slotA } = seedDraftAs(env, META_A, MERGED_A, baseFp);
    const snapshotA = env.store.get(slotA);

    env.S.legendDirty = true;
    await env.S.loadExistingMap();               // same map, plain load
    noSwallowed(env, 'D/re-load of the same map');

    const after = env.S.readDoeDraft(TABLE, MAPKEY_A).cells;
    const dropped = Object.keys(MERGED_A).filter(k => !(k in after));
    // D1-D3 INVERTED 2026-08-06: written to characterize the defect, now asserting the repair.
    // The defect was that a plain load re-persisted this map's own draft slot from the server
    // copy it had just read, deleting the operator's unsaved cells — and closing the very
    // refresh the change named as its safety net.
    eq('D1/a plain load leaves map A\'s own draft slot BYTE-IDENTICAL', true,
      env.store.get(slotA) === snapshotA,
      'the load re-persisted the slot, and that write is an operator\'s unsaved work');
    eq('D2/…so it drops none of the unsaved cells', [], dropped,
      'these cells existed only in the draft and the load overwrote them');
    // The IIFE is `async` now: building an env is an import, and the value has to be awaited
    // before `eq` compares it -- a Promise would compare unequal to MERGED_A and the failure
    // would read as a product defect rather than a harness one.
    const env2 = await buildEnv(src, { store: env.store });
    eq('D3/…and the next refresh still finds them', MERGED_A,
      JSON.parse(env2.store.get(slotA)).cells);
    evidence.push(`D/ slot A before=${Object.keys(JSON.parse(snapshotA).cells).join('|')}`
      + ` after=${Object.keys(JSON.parse(env.store.get(slotA)).cells).join('|')}`
      + ` dropped=${JSON.stringify(dropped)}`);
  }

  return { failures, compared, evidence };
}

// ── Mutation corpus ─────────────────────────────────────────────────────────────────────
// 🔴 AN ASSERTION WHOSE MUTANT HAS NOT BEEN RUN IS DECORATION. Every anchor is checked for
//    PRESENCE **and UNIQUENESS** before it is applied, and a mutant that survives is a
//    failure — a survivor is a rot suspect before it is a coverage hole (an anchor can stay
//    valid while the code it targeted moves out from under it).
const MUTANTS = [
  { name: 'restore-runs-unconditionally-again (THE PRE-CHANGE CODE)',
    from: `const restored = restoreDraft\n          ? restoreDoeDraftWithPrecedence(selectedTable, loadedMapKey, serverFp, serverCellsFp)\n          : { restoredUnsavedEdits: false, staleDraftKept: true };`,
    to: `const restored = restoreDoeDraftWithPrecedence(selectedTable, loadedMapKey, serverFp, serverCellsFp);` },
  // THE REPAIR ITSELF. `staleDraftKept: false` let the re-baseline persist run and delete
  // the operator's unsaved cells. This is the shipped defect of 2026-08-06 put back.
  { name: 'skipped-restore-reports-not-stale (the persist runs and eats the draft)',
    from: `          : { restoredUnsavedEdits: false, staleDraftKept: true };`,
    to: `          : { restoredUnsavedEdits: false, staleDraftKept: false };` },
  { name: 'restoreDraft-defaults-to-true',
    from: `  const restoreDraft = !!opts.restoreDraft;`,
    to: `  const restoreDraft = opts.restoreDraft !== false;` },
  { name: 'restore-folded-into-quiet (the overload the commit refused)',
    from: `  const restoreDraft = !!opts.restoreDraft;`,
    to: `  const restoreDraft = !!opts.quiet;` },
  { name: 'boot-restore-stops-asking-for-the-draft',
    from: `await loadExistingMap({ quiet: true, restoreDraft: true });`,
    to: `await loadExistingMap({ quiet: true });` },
  { name: 'the-flag-is-passed-but-ignored (restores anyway)',
    from: `const restored = restoreDraft\n          ?`,
    to: `const restored = (restoreDraft || true)\n          ?` },
  { name: 'draft-slot-loses-the-map-component',
    from: `function doeDraftKey(table, mapKey) { return \`map_doe_draft::\${table}::\${mapKey}\`; }`,
    to: `function doeDraftKey(table, mapKey) { void mapKey; return \`map_doe_draft::\${table}\`; }` },
  { name: 'draft-slot-loses-the-table-component',
    from: `function doeDraftKey(table, mapKey) { return \`map_doe_draft::\${table}::\${mapKey}\`; }`,
    to: `function doeDraftKey(table, mapKey) { void table; return \`map_doe_draft::\${mapKey}\`; }` },
  // ⚠️ THE FIRST VERSION OF THIS MUTANT SURVIVED, AND THE MUTATION WAS THE PROBLEM, NOT THE
  //    CODE. It gated `applyDoeDraftRecord` — the DOE half — and every draft in this file
  //    carries `doe:{}` (see the header: those normalizers cannot load under bare node), so
  //    the mutation was INERT and its green said "there was no mutation", not "caught". It is
  //    retargeted at the CELLS call, which is the half this fixture can see.
  { name: 'the-failed-read-branch-gets-gated-too',
    from: `        const hadDraftCells = (draft && draft.cells) ? applyDraftCells(draft.cells) > 0 : false;`,
    to: `        const hadDraftCells = false; void draft;` },
  { name: 'stale-precedence-dropped (a stale draft applies)',
    from: `    const cellsFresh = draft.cellsFp !== null && draft.cellsFp === serverCellsFp;`,
    to: `    const cellsFresh = draft.cellsFp !== null;` },
  { name: '⑦ gets its two fingerprints in the wrong order',
    // The `? ` prefix is load-bearing: without it the anchor also matches the FUNCTION
    // DEFINITION's parameter list 490 lines later, and a non-unique anchor is refused.
    from: `? restoreDoeDraftWithPrecedence(selectedTable, loadedMapKey, serverFp, serverCellsFp)`,
    to: `? restoreDoeDraftWithPrecedence(selectedTable, loadedMapKey, serverCellsFp, serverFp)` },
  // 🔴 NOT A DEFECT — THIS IS THE CANDIDATE REPAIR FOR THE DEFECT SECTION D CHARACTERIZES,
  //    and it is in the corpus so that D1/D2 are provably capable of noticing it. If the
  //    persist is what gets fixed, this mutant is the acceptance test and D1/D2 invert.
  { name: 'the-persist-that-eats-the-draft-is-removed (THE CANDIDATE REPAIR)',
    from: `        if (!staleDraftKept) saveLegendToStorage();`,
    to: `        void staleDraftKept;` },
];

// Controls: changes that must NOT be caught. Without them a corpus that catches everything
// (because the harness is broken, not because it is sharp) looks like a perfect score.
const CONTROLS = [
  { name: 'control/quiet is spelled differently, same meaning',
    from: `  const quiet = !!opts.quiet;`,
    to: `  const quiet = opts.quiet === true;` },
  { name: 'control/a console.debug string changes',
    from: `console.debug(\`[map] loaded \${selectedTable}`,
    to: `console.debug(\`[map] LOADED \${selectedTable}` },
];

function applyMutation(src, m) {
  const i = src.indexOf(m.from);
  if (i < 0) die(`mutation anchor is GONE: ${m.name}. An anchor that no longer matches makes `
    + `the mutant silently inert — this file's corpus is only worth its anchors.`);
  if (src.indexOf(m.from, i + 1) >= 0) die(`mutation anchor is NOT UNIQUE: ${m.name}`);
  return src.slice(0, i) + m.to + src.slice(i + m.from.length);
}

// ── Runner ──────────────────────────────────────────────────────────────────────────────
const base = await run(null, true);
if (verbose) base.evidence.forEach(e => console.log(`   · ${e}`));
base.failures.forEach(f => console.log(`✗ ${f}`));
console.log(`${base.failures.length === 0 ? '✓' : '✗'} baseline: ${base.compared} assertions, `
  + `${base.failures.length} failure(s)`);

let mutCompared = 0, mutFailed = 0;
for (const m of MUTANTS) {
  const r = await run(() => applyMutation(SRC, m));
  mutCompared++;
  if (r.failures.length === 0) {
    mutFailed++;
    console.log(`✗ mutant SURVIVED: ${m.name} — the assertions cannot tell this defect from `
      + `the shipped code. Suspect the mutation before you suspect the code.`);
  } else if (verbose) {
    console.log(`   · caught ${m.name} (${r.failures.length})`);
    r.failures.forEach(f => console.log(`       - ${f.split(':')[0]}`));
  }
}
for (const c of CONTROLS) {
  const r = await run(() => applyMutation(SRC, c));
  mutCompared++;
  if (r.failures.length > 0) {
    mutFailed++;
    console.log(`✗ ${c.name}: a behaviour-preserving change was reported as a defect — `
      + `the assertions are pinning spelling, not behaviour. First: ${r.failures[0]}`);
  }
}
console.log(`--- mutation check: ${mutCompared - mutFailed}/${mutCompared} `
  + `(${MUTANTS.length} defects, ${CONTROLS.length} controls) ---`);

const ran = base.compared + mutCompared;
const failed = base.failures.length + mutFailed;
console.log(`ASSERTIONS ${ran} ${failed}`);
process.exit(failed === 0 ? 0 : 1);
