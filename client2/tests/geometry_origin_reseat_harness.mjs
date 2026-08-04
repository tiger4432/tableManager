/**
 * GEOMETRY MOVES THE ORIGIN BOX, SO THE CANVAS MOVES AND THE STORED COORDINATE DOES NOT.
 *
 *   node client2/tests/geometry_origin_reseat_harness.mjs
 *   node client2/tests/geometry_origin_reseat_harness.mjs --verbose
 *   node client2/tests/geometry_origin_reseat_harness.mjs --mutate
 *
 * WHAT IT SCORES. Rule 4 — "valid region / map geometry changes -> the CELL COORDINATE does
 * not". On a map with no declared valid-die reference the valid-die region IS the wafer
 * circle, so editing the geometry preset moves that region exactly the way designating a
 * reference does. Measured on 1e4f23c with the production frame of `dt_map/QERWER`, changing
 * the chip pitch 15 -> 12 moved `box.minC` 2 -> 0 and every one of 261 painted cells started
 * reading a coordinate two columns and two rows away from the one it was painted with. The
 * cell never left its canvas square; its NUMBER changed, and Push proceeded.
 *
 * THE ORACLE IS THE VALUE. Every cell is painted with its own stored coordinate as its value,
 * so a cell carries the answer it must still give. Matching cells by physical key cannot work
 * here — re-seating changes the key, which is the whole point of the operation — and an
 * earlier round produced a phantom 183/255 violation by trying.
 *
 * FIXTURE ACTIVITY IS ASSERTED, NOT ASSUMED (map-pm memory). A fixture whose origin box does
 * not move, or whose chipX equals its chipY, or whose `minC` is 0, cannot exhibit the defect
 * at all. Each case states the number that proves its own axis is live, and `fixture/*`
 * assertions fail if any of them goes flat.
 *
 * FIXTURES ARE PRODUCTION ROWS, copied from `wafer_map_metadata` on 2026-07-31 — the same maps
 * the user QA's against, including the two that carry `valid_die_ref`.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..', '..');
const SRC_PATH = join(ROOT, 'client2', 'src', 'map_editor.js');
const SRC = readFileSync(SRC_PATH, 'utf8');
// [1-b] The markup, for the two assertions that cannot be made against behaviour: a button
// deleted from the HTML leaves no trace in any event a fixture can dispatch, and a stale
// instruction in the explanatory <p> is invisible to every sandbox.
const HTML_PATH = join(ROOT, 'client2', 'map_editor.html');
const HTML = readFileSync(HTML_PATH, 'utf8').replace(/\r\n/g, '\n');
const verbose = process.argv.includes('--verbose');
const mutateOnly = process.argv.includes('--mutate');

const die = (msg) => { console.error(`HARNESS FAILURE: ${msg}`); process.exit(2); };

// [1-a 2026-08-04] The FIXED valid-die storage table. `parseValidDieRef` reads this module
// const since the load path was pinned, so a sandbox without it throws ReferenceError and the
// whole slice dies before comparing anything. EXTRACTED from the source, never re-typed:
// a copy that drifted would score the wrong table green. Same shape as the extraction in
// valid_die_authoring_harness.mjs — one spelling, three harnesses.
const VALID_DIE_TABLE = (() => {
  const m = /const\s+VALID_DIE_TABLE\s*=\s*'([^']*)'\s*;/.exec(SRC);
  if (!m) die('const VALID_DIE_TABLE not found in map_editor.js — the fixed storage table is gone or renamed.');
  return m[1];
})();

// ── Slicer (same shape as the sibling harnesses) ────────────────────────────────────────
function sliceFunction(source, name) {
  const decl = new RegExp(`(^|\\n)\\s*(?:async\\s+)?function\\s+${name}\\s*\\(`);
  const m = decl.exec(source);
  if (!m) return null;
  const start = m.index + (m[1] ? m[1].length : 0);
  let i = m.index + m[0].length - 1;
  let paren = 0;
  for (; i < source.length; i++) {
    if (source[i] === '(') paren++;
    else if (source[i] === ')') { paren--; if (paren === 0) { i++; break; } }
  }
  i = source.indexOf('{', i);
  if (i < 0) return null;
  let depth = 0;
  for (; i < source.length; i++) {
    if (source[i] === '{') depth++;
    else if (source[i] === '}') { depth--; if (depth === 0) return source.slice(start, i + 1); }
  }
  die(`unbalanced braces extracting '${name}'`);
}

const SYMBOLS = [
  'physNum', 'gridDimNum', 'withPhysFrame',
  // `physDeclaration` + `cellMetrics`: the cell's pixel size is now derived from the declared
  // chip pitch (equal mm-per-pixel on both axes) instead of from the canvas rectangle alone.
  // `renderGridCanvas` calls `cellMetrics`, which calls `physDeclaration` — omitting either
  // turns the render into a ReferenceError that reads as a 0-cell screen.
  'geometryIsAutoRegistered', 'markGeometryAutoRegistered', 'physDeclaration', 'cellMetrics',
  'getScreenShift', 'getTransformedPhysicalConfig', 'isCellInsideWaferFast',
  'getDieIndex', 'getCanvasCellFromDieIndex', 'getCanvasCellFromDb', 'getDbCoords',
  'getWaferBoundingBox',
  'validDieBasis', 'isValidDieAt',
  // THE ONE REACTION and the record it compares against.
  'seatingSnapshot', 'reseatCellsToStoredCoords',
  'frameFromMeta', 'currentFrame', 'resolveFrame', 'frameAxesKey',
  'frameDimBounds', 'frameDimError',
  'applyPresetObject', 'applyPhysicalGeometry',
  // The dropdown's registered handler, and the function that registers it.
  'loadSelectedPreset', 'initDOMElements',
  'parseValidDieRef', 'validDieChainError', 'validDieRefDisplay',
  // [rule 6] projectCellsToPhys now states its result in terms of the mm projection, so the
  // slice needs both. It died with a ReferenceError rather than going quietly green.
  'projectCellsToWaferMm', 'projectCellsToPhys',
  // [R5] `resolveValidDie` is now written in terms of five named steps. They are SLICED, not
  // stubbed: `fitGridToMask` is rule 1-b (the grid re-derived from the reference spec) and
  // `summariseReseat` reports the very re-seating this harness scores, so stubbing either
  // would make the designation cases measure the harness instead of the product. Omitting a
  // name is loud rather than silently green — the designation's refusal reason becomes
  // `<name> is not defined` and `fixture/*-mask-resolved` goes red.
  'resolveValidDie',
  'fitGridToMask', 'summariseReseat', 'resolveReferenceSpec',
  'deriveMaskKeys', 'diagnoseDesignationAlignment',
  // The real renderer runs; only the pixels are stubbed. It is what seeds the seating record,
  // so a harness that stubbed it could not score that the record is maintained at all.
  'renderGridCanvas', 'cellFillColor', 'isProtectedFCell',
  'eachSavableCell', 'classifyUnsavableCells', 'serverCellKeySet', 'pushBlockingCount',
];

// ── Production fixtures (wafer_map_metadata, 2026-07-31) ────────────────────────────────
// Defect axes live across the set: chipX != chipY (A2, DT_TEST, DTWWER), rot 90 (DT_TEST),
// non-zero offset (DTWWER/BASE_4E offsetX 0.1), negative start (DTWWER/BASE_4E), minC != 0.
const F = {
  QERWER: { cols: 23, rows: 23, startX: 1, startY: 1, invertY: false, rotation: 0, side: 'front',
            dia: 300, chipX: 15, chipY: 15, offX: 0, offY: 0, margin: 3 },
  A2: { cols: 23, rows: 23, startX: 1, startY: 1, invertY: false, rotation: 0, side: 'front',
        dia: 300, chipX: 14.3, chipY: 15.2, offX: 0, offY: 0, margin: 3 },
  DT_TEST_META: { grid_cols: 25, grid_rows: 25, grid_start_x: 1, grid_start_y: 1,
                  grid_y_invert: false, rotation: 90, side: 'front', phys_wafer_dia: 300,
                  phys_chip_x: 13.6, phys_chip_y: 13.7, phys_offset_x: 0, phys_offset_y: 0,
                  phys_edge_margin: 3 },
  DTWWER: { cols: 33, rows: 25, startX: -3, startY: -2, invertY: false, rotation: 0, side: 'front',
            dia: 300, chipX: 9.7, chipY: 13.8, offX: 0.1, offY: 0, margin: 3 },
  BASE_4E_META: { grid_cols: 33, grid_rows: 25, grid_start_x: -3, grid_start_y: -2,
                  grid_y_invert: false, rotation: 0, side: 'front', phys_wafer_dia: 300,
                  phys_chip_x: 9.7, phys_chip_y: 13.8, phys_offset_x: 0.1, phys_offset_y: 0,
                  phys_edge_margin: 3 },
};

// The two reference maps' OWN CELLS, as stored — `bonding_map` rows for DT_TEST and BASE_4E,
// read out of the production database on 2026-07-31. Real rows, not a generated circle: a
// generated set came out 329/461 against the real 326/262, which is a different fixture and
// would have made every number below incomparable to the ones the round was scored on.
const DT_TEST_CELLS =
   '9,1 10,1 11,1 12,1 13,1 7,2 8,2 9,2 10,2 11,2 12,2 13,2 14,2 15,2 5,3 6,3 7,3 8,3 9,3 10,3 '
 + '11,3 12,3 13,3 14,3 15,3 16,3 17,3 4,4 5,4 6,4 7,4 8,4 9,4 10,4 11,4 12,4 13,4 14,4 15,4 '
 + '16,4 17,4 18,4 3,5 4,5 5,5 6,5 7,5 8,5 9,5 10,5 11,5 12,5 13,5 14,5 15,5 16,5 17,5 18,5 19,5 '
 + '3,6 4,6 5,6 6,6 7,6 8,6 9,6 10,6 11,6 12,6 13,6 14,6 15,6 16,6 17,6 18,6 19,6 2,7 3,7 4,7 '
 + '5,7 6,7 7,7 8,7 9,7 10,7 11,7 12,7 13,7 14,7 15,7 16,7 17,7 18,7 19,7 20,7 2,8 3,8 4,8 5,8 '
 + '6,8 7,8 8,8 9,8 10,8 11,8 12,8 13,8 14,8 15,8 16,8 17,8 18,8 19,8 20,8 2,9 3,9 4,9 5,9 6,9 '
 + '7,9 8,9 9,9 10,9 11,9 12,9 13,9 14,9 15,9 16,9 17,9 18,9 19,9 20,9 2,10 3,10 4,10 5,10 6,10 '
 + '7,10 8,10 9,10 10,10 11,10 12,10 13,10 14,10 15,10 16,10 17,10 18,10 19,10 20,10 21,10 2,11 '
 + '3,11 4,11 5,11 6,11 7,11 8,11 9,11 10,11 11,11 12,11 13,11 14,11 15,11 16,11 17,11 18,11 '
 + '19,11 20,11 21,11 2,12 3,12 4,12 5,12 6,12 7,12 8,12 9,12 10,12 11,12 12,12 13,12 14,12 '
 + '15,12 16,12 17,12 18,12 19,12 20,12 21,12 2,13 3,13 4,13 5,13 6,13 7,13 8,13 9,13 10,13 '
 + '11,13 12,13 13,13 14,13 15,13 16,13 17,13 18,13 19,13 20,13 2,14 3,14 4,14 5,14 6,14 7,14 '
 + '8,14 9,14 10,14 11,14 12,14 13,14 14,14 15,14 16,14 17,14 18,14 19,14 20,14 2,15 3,15 4,15 '
 + '5,15 6,15 7,15 8,15 9,15 10,15 11,15 12,15 13,15 14,15 15,15 16,15 17,15 18,15 19,15 20,15 '
 + '3,16 4,16 5,16 6,16 7,16 8,16 9,16 10,16 11,16 12,16 13,16 14,16 15,16 16,16 17,16 18,16 '
 + '19,16 3,17 4,17 5,17 6,17 7,17 8,17 9,17 10,17 11,17 12,17 13,17 14,17 15,17 16,17 17,17 '
 + '18,17 19,17 4,18 5,18 6,18 7,18 8,18 9,18 10,18 11,18 12,18 13,18 14,18 15,18 16,18 17,18 '
 + '18,18 5,19 6,19 7,19 8,19 9,19 10,19 11,19 12,19 13,19 14,19 15,19 16,19 17,19 7,20 8,20 '
 + '9,20 10,20 11,20 12,20 13,20 14,20 15,20 9,21 10,21 11,21 12,21 13,21';
const BASE_4E_CELLS =
   '7,1 8,1 9,1 10,1 11,1 12,1 13,1 14,1 15,1 16,1 4,2 5,2 6,2 7,2 8,2 9,2 10,2 11,2 12,2 13,2 '
 + '14,2 15,2 16,2 17,2 18,2 19,2 2,3 3,3 4,3 5,3 6,3 7,3 8,3 9,3 10,3 11,3 12,3 13,3 14,3 15,3 '
 + '16,3 17,3 18,3 19,3 20,3 1,4 2,4 3,4 4,4 5,4 6,4 7,4 8,4 9,4 10,4 11,4 12,4 13,4 14,4 15,4 '
 + '16,4 17,4 18,4 19,4 20,4 21,4 1,5 2,5 3,5 4,5 5,5 6,5 7,5 8,5 9,5 10,5 11,5 12,5 13,5 14,5 '
 + '15,5 16,5 17,5 18,5 19,5 20,5 21,5 1,6 2,6 3,6 4,6 5,6 6,6 7,6 8,6 9,6 10,6 11,6 12,6 13,6 '
 + '14,6 15,6 16,6 17,6 18,6 19,6 20,6 21,6 1,7 2,7 3,7 4,7 5,7 6,7 7,7 8,7 9,7 10,7 11,7 12,7 '
 + '13,7 14,7 15,7 16,7 17,7 18,7 19,7 20,7 21,7 1,8 2,8 3,8 4,8 5,8 6,8 7,8 8,8 9,8 10,8 11,8 '
 + '12,8 13,8 14,8 15,8 16,8 17,8 18,8 19,8 20,8 21,8 1,9 2,9 3,9 4,9 5,9 6,9 7,9 8,9 9,9 10,9 '
 + '11,9 12,9 13,9 14,9 15,9 16,9 17,9 18,9 19,9 20,9 21,9 1,10 2,10 3,10 4,10 5,10 6,10 7,10 '
 + '8,10 9,10 10,10 11,10 12,10 13,10 14,10 15,10 16,10 17,10 18,10 19,10 20,10 21,10 1,11 2,11 '
 + '3,11 4,11 5,11 6,11 7,11 8,11 9,11 10,11 11,11 12,11 13,11 14,11 15,11 16,11 17,11 18,11 '
 + '19,11 20,11 21,11 1,12 2,12 3,12 4,12 5,12 6,12 7,12 8,12 9,12 10,12 11,12 12,12 13,12 14,12 '
 + '15,12 16,12 17,12 18,12 19,12 20,12 21,12 4,13 5,13 6,13 7,13 8,13 9,13 10,13 11,13 12,13 '
 + '13,13 14,13 15,13 16,13 17,13 18,13 19,13 6,14 7,14 8,14 9,14 10,14 11,14 12,14 13,14 14,14 '
 + '15,14 16,14 17,14';

function parseCells(s) {
  return s.trim().split(/\s+/).map(p => {
    const [x, y] = p.split(',').map(Number);
    return { x, y };
  });
}

// ── Sandbox ─────────────────────────────────────────────────────────────────────────────
function makeInput(v) {
  return { value: String(v), checked: false, textContent: '', disabled: false, style: {},
           classList: { add() {}, remove() {}, toggle() {} },
           querySelector: () => null, appendChild() {},
           addEventListener() {}, removeEventListener() {} };
}

// ═══════════════════════════════════════════════════════════════════════════════════════
// A DOM stub with REAL event dispatch, because the fixture has to start where the operator
// starts.
//
// 🔴 WHY THIS EXISTS. The first version of this harness called `applyPresetObject(...)` and
//    `reseatCellsToStoredCoords(...)` directly — both real, both downstream of the operator's
//    gesture, and both reachable whether or not anything is still WIRED to them. That scores
//    the plumbing and not the tap: delete `presetSelect.addEventListener('change', ...)` and
//    every assertion stays green while the product does nothing. It is the same shape as the
//    breakages `copy_header_count` and `company_roundtrip` sat in this week — a harness
//    reporting green about code it had stopped reaching.
//
// 🔴 SO `initDOMElements` IS SLICED AND RUN. It is the function that owns every listener
//    registration in this screen (`map_editor.js` :866-:1147), so running it is the only way
//    a fixture can dispatch `change` on `#preset-select` and have the shipped handler answer.
//    Elements are created on demand by id and remember their listeners.
// ⚠️ Unknown globals are NOT swallowed. `initDOMElements` names ~25 other functions; each is
//    stubbed EXPLICITLY below, so a rename still throws instead of quietly no-op'ing.
// ═══════════════════════════════════════════════════════════════════════════════════════
function makeDom(P) {
  const nodes = new Map();
  const paintSink = () => new Proxy({}, {
    get: (t, k) => (k in t ? t[k] : (t[k] = () => {})), set: (t, k, v) => (t[k] = v, true) });
  const make = (id) => {
    const listeners = new Map();
    return {
      id, value: '', checked: false, textContent: '', disabled: false, innerHTML: '',
      style: {}, dataset: {}, width: 0, height: 0,
      classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
      addEventListener(type, fn) {
        if (!listeners.has(type)) listeners.set(type, []);
        listeners.get(type).push(fn);
      },
      removeEventListener(type, fn) {
        const a = listeners.get(type) || [];
        const i = a.indexOf(fn);
        if (i >= 0) a.splice(i, 1);
      },
      // The fixture's only way in. Returns how many handlers ran, so a case can assert that
      // the gesture actually reached something.
      dispatchEvent(ev) {
        const a = (listeners.get(ev && ev.type) || []).slice();
        a.forEach(fn => fn(Object.assign({ target: this, preventDefault() {},
                                           stopPropagation() {} }, ev)));
        return a.length;
      },
      listenerCount(type) { return (listeners.get(type) || []).length; },
      querySelector: () => null, appendChild() {}, focus() {}, blur() {},
      getBoundingClientRect: () => ({ width: 700, height: 700, left: 0, top: 0 }),
      getContext: () => paintSink(),
    };
  };
  const byId = (id) => {
    if (!nodes.has(id)) nodes.set(id, make(id));
    return nodes.get(id);
  };
  // The panel's declared frame, written onto the real nodes before the wiring reads them.
  const seed = {
    'grid-cols': P.cols, 'grid-rows': P.rows,
    'grid-start-x': P.startX, 'grid-start-y': P.startY,
    'phys-wafer-dia': P.dia, 'phys-chip-x': P.chipX, 'phys-chip-y': P.chipY,
    'phys-offset-x': P.offX, 'phys-offset-y': P.offY, 'phys-edge-margin': P.margin,
  };
  Object.entries(seed).forEach(([id, v]) => { byId(id).value = String(v); });
  byId('grid-y-invert').checked = !!P.invertY;
  byId('show-annotations').checked = false;
  const document = {
    getElementById: byId,
    querySelectorAll: () => [],
    addEventListener() {}, removeEventListener() {},
  };
  return { document, byId };
}

function buildEnv(src, P, opts = {}) {
  const pieces = [];
  for (const name of SYMBOLS) {
    const code = sliceFunction(src, name);
    if (!code) die(`'${name}' is gone from map_editor.js — renamed or reshaped. Nothing compared.`);
    try { new vm.Script(code); }
    catch (e) { die(`slice of '${name}' does not parse: ${e && e.message}`); }
    pieces.push(code);
  }
  const log = { toasts: [], requests: [], warns: [] };
  const dom = makeDom(P);
  const el = {};
  const sandbox = {
    console: { warn: (m) => log.warns.push(String(m)), info() {}, error() {}, log() {}, debug() {} },
    el,
    document: dom.document,
    localStorage: { getItem: () => null, setItem() {} },
    COPY_HEADER_KEY: 'copyHeader',
    isOriginMode: false,
    // Everything `initDOMElements` names but this harness never fires. Listed one by one on
    // purpose: a rename must be a ReferenceError, not a silent no-op.
    fetchAndRenderPresets() {}, saveCustomPreset() {}, deleteCustomPreset() {},
    // `saveMapSpecOnly` is the 📐 규격만 저장 handler `initDOMElements` now wires (it replaced
    // the deleted 💾 SAVE). It is a stub for the same reason as its neighbours: this harness
    // executes the WIRING, not the metadata write path (scored by map_spec_only_save_harness).
    // `onValidDieRefChanged` is a stub the valid-die COMMIT cases below REPLACE WITH A COUNTER —
    // that is how "which gesture applies" is scored without running the applier.
    onValidDieRefChanged() {}, saveMapSpecOnly() {},
    populateValidDieRefList() {}, switchTable() {},
    // Key-datalist wiring (2026-07-31). `KEY_SUGGEST_DEBOUNCE_MS` is a VALUE, not a stub:
    // `initDOMElements` passes it to `debounce`, so a missing binding is a ReferenceError
    // here exactly as a missing function would be.
    populateOverlayKeyList() {}, onMetaInputSuggest() {}, KEY_SUGGEST_DEBOUNCE_MS: 120,
    renderMetadataInputs() {}, loadExistingMap: async () => ({}), countNav() {},
    effortRoute: () => '', handleAddOverlayClick() {}, clearOverlayLayers() {},
    renderOverlayList() {}, addLegendRowForPanel() {}, clearGrid() {}, fillGrid() {},
    pushMapData() {}, copyGridToExcel() {}, onMapGridPaste() {}, selectEdgeCells() {},
    autoPaintE1E2() {}, fillSelectedCells() {}, clearSelectedCells() {},
    fitGridToWorkspace() {}, initPlanSidebarResizer() {}, debounce: (f) => f,
    physFrameOverride: null,
    boundingBoxCache: {},
    cellsSeatedUnder: null,
    currentRotation: P.rotation,
    currentSide: P.side,
    gridData: {},
    gridCells2D: {},
    legend: [{ value: 'A', color: '#0a0' }],
    validDie: { basis: 'circle', keys: null, reason: '', ref: null, raw: undefined },
    validDieResolveSeq: 0,
    selectedTable: opts.table || 'bonding_map',
    loadedIdentity: null,
    tableSchema: { column_types: {} },
    API_BASE: '',
    OVERLAY_CELL_LIMIT: 2000,
    VALID_DIE_TABLE,
    // Paint constants the real renderer reads. Values are irrelevant here — only the
    // coordinate DECISIONS are scored — but they must exist or the renderer throws.
    UNLISTED_VALUE_FILL: '#10b981',
    overlayLayers: [], loadedFCells: new Set(), serverCellKeys: null,
    paintLockValues: null, currentHoverCell: null, lastSelectionBox: null,
    syncOverlayGeometry() {},
    getThemeColors: () => ({ outBg: '#eee', line: '#ccc', text: '#000', inBg: '#fff',
                             origin: '#f00', notch: '#00f', gridText: '#333', dim: '#999' }),
    performance: { now: () => 0 },
    // No ResizeObserver: `initDOMElements` guards on `window.ResizeObserver` being truthy.
    window: { devicePixelRatio: 1, addEventListener() {}, removeEventListener() {} },
    updateOrientationUI() {}, updateSideIndicator() {},
    scheduleRenderGridCanvas() {},
    updateLegendCounts() {},
    activeOverlayLayers: () => [], drawOverlayMarkers() {}, updateNotchPosition() {},
    isBoxDragging: false, dragType: null,
    getComputedStyle: () => ({ getPropertyValue: () => '#000' }),
    renderValidDieChip() {}, syncValidDieRefControls() {},
    // [1-a] The key control's SHAPE (<select> vs text input) is scored in
    // map_key_datalist_harness.mjs, which models a real DOM tree. Stubbed here so the
    // wiring executes without dragging that model in — this harness scores coordinates.
    renderValidDieKeyControl() {},
    showToast: (msg, kind) => log.toasts.push({ msg: String(msg), kind }),
    requestAnimationFrame(fn) { fn(); },
    isLockedValue: () => false,
    fetchMapKeySpec: async (t) => { log.requests.push(`spec:${t}`);
      return { ok: true, keyColumns: ['base'], columnTypes: {} }; },
    canonicalMapKey: (kc, k) => String(k),
    fetchServedBinding: async (t) => { log.requests.push(`binding:${t}`);
      return { x: 'x', y: 'y', keyColumns: ['base'], source: 'declared' }; },
    fetchGridMetaFor: async (t, k) => { log.requests.push(`meta:${t}/${k}`); return opts.refMeta || null; },
    buildKeyFilters: () => ({}),
    fetch: async (url) => {
      log.requests.push(`fetch:${String(url).split('?')[0]}`);
      const rows = (opts.refCells || []).map(c => ({ data: { x: { value: c.x }, y: { value: c.y } } }));
      return { ok: true, status: 200, json: async () => ({ data: rows }) };
    },
  };
  sandbox.serverPresets = opts.serverPresets || {};
  sandbox.VALID_DIE_TEMPLATE_PREFIX = 'valid-die-template:';
  sandbox.enterValidDieAuthoring = () => die('the authoring branch must not be reached');
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  try { vm.runInContext(pieces.join('\n'), sandbox); }
  catch (e) { die(`extracted sources did not evaluate: ${e && e.message}`); }
  // THE WIRING RUNS. From here on `el.*` are the same node objects `document.getElementById`
  // hands out, so dispatching on a node reaches the shipped handler.
  try { sandbox.initDOMElements(); }
  catch (e) { die(`initDOMElements threw — the wiring could not be executed: ${e && e.message}`); }
  return { S: sandbox, el, log, byId: dom.byId };
}

// The operator's gesture. Fails loudly when nothing is listening, which is the whole point of
// entering here rather than at the function the listener happens to call.
function fire(node, type, what) {
  const n = node.dispatchEvent({ type });
  if (n === 0) throw new Error(`nothing is listening for '${type}' on ${what} — the wiring is `
    + 'gone, and a fixture that called the handler directly would still have been green');
  return n;
}

// ── The value-encoded oracle ────────────────────────────────────────────────────────────
function frameNow(S) {
  const cols = parseInt(S.el.gridCols.value, 10) || 10;
  const rows = parseInt(S.el.gridRows.value, 10) || 10;
  const rot = S.currentRotation, side = S.currentSide;
  const r90 = (rot === 90 || rot === 270);
  return { cols, rows, rot, side, vc: r90 ? rows : cols, vr: r90 ? cols : rows,
           inv: !!S.el.gridYInvert.checked,
           sx: parseInt(S.el.gridStartX.value, 10) || 0,
           sy: parseInt(S.el.gridStartY.value, 10) || 0 };
}

// Paint every cell the editor calls valid with ITS OWN stored coordinate as the value.
function paintOracle(S) {
  const f = frameNow(S);
  const cfg = S.getTransformedPhysicalConfig(f.rot, f.side);
  S.gridData = {};
  for (let r = 0; r < f.vr; r++) for (let c = 0; c < f.vc; c++) {
    const p = S.getDieIndex(c, r, f.cols, f.rows, f.rot, f.side);
    const circle = S.isCellInsideWaferFast(c, r, f.vc, f.vr, cfg, 700, 700);
    if (!S.isValidDieAt(p.x, p.y, circle)) continue;
    const v = S.getDbCoords(c, r, f.cols, f.rows, f.rot, f.side, f.inv, f.sx, f.sy);
    S.gridData[`${p.x}_${p.y}`] = `${v.x},${v.y}`;
  }
  return Object.keys(S.gridData).length;
}

// What each cell reads NOW. Key -> { was (its painted value), now, seat }
function readBack(S) {
  const f = frameNow(S);
  const out = new Map();
  Object.keys(S.gridData).forEach(k => {
    const [px, py] = k.split('_').map(Number);
    const at = S.getCanvasCellFromDieIndex(px, py, f.cols, f.rows, f.rot, f.side);
    const v = S.getDbCoords(at.c, at.r, f.cols, f.rows, f.rot, f.side, f.inv, f.sx, f.sy);
    out.set(k, { was: S.gridData[k], now: `${v.x},${v.y}`, seat: `${at.c},${at.r}` });
  });
  return out;
}

// 🔴 A SURVIVORS-ONLY COUNT CANNOT SEE A DESTROYED CELL. `gridData` is keyed by physical key,
//    so a re-seat that maps two cells onto one key does not produce a disagreement — it
//    produces one FEWER cell, and iterating what is left reports that as 0/N. Every case hands
//    in the population it started with, and losing one is a failure on its own axis.
function disagreements(S, expected) {
  const rb = readBack(S);
  const bad = [];
  rb.forEach((v) => { if (v.was !== v.now) bad.push(`${v.was} -> ${v.now}`); });
  return { total: rb.size, bad, lost: (expected === undefined) ? 0 : expected - rb.size };
}

// Where on the canvas does the cell PAINTED with `value` sit right now?
function seatOfValue(S, value) {
  let hit = null;
  readBack(S).forEach((v) => { if (v.was === value) hit = v.seat; });
  return hit;
}

function boxOf(S) {
  const b = S.getWaferBoundingBox(S.currentRotation, S.currentSide);
  return { minC: b.minC, minR: b.minR, maxC: b.maxC, maxR: b.maxR };
}

// ── Scoring ─────────────────────────────────────────────────────────────────────────────
function run(src) {
  const failures = [];
  let compared = 0;
  const evidence = [];
  const eq = (name, expected, actual, note) => {
    compared++;
    const a = JSON.stringify(actual), e = JSON.stringify(expected);
    if (a !== e) failures.push(`${name}: expected ${e}, got ${a}${note ? ` — ${note}` : ''}`);
  };

  // ══ 1a. A TYPED PITCH EDIT, no declared valid die (the user's case) ═══════════════════
  {
    const { S } = buildEnv(src, F.QERWER, { table: 'dt_map' });
    const painted = paintOracle(S);
    S.renderGridCanvas();                       // this is what seeds the seating record
    eq('1a/render-seeds-the-record', true, !!S.cellsSeatedUnder,
       'without the record a listener has no pre-edit coordinate system to compare against');
    const before = boxOf(S);
    const seatBefore = seatOfValue(S, '9,1');

    // The operator types 12 over 15. `input`/`change` fire AFTER the DOM value changed, which
    // is why the record exists at all.
    S.el.physChipX.value = '12';
    S.el.physChipY.value = '12';
    fire(S.el.physChipX, 'input', '#phys-chip-x');
    fire(S.el.physChipY, 'input', '#phys-chip-y');
    const after = boxOf(S);
    const d = disagreements(S, painted);
    const seatAfter = seatOfValue(S, '9,1');

    eq('fixture/1a-population', 261, painted, 'the painted set is what the acceptance counted');
    eq('fixture/1a-origin-box-really-moves', true, before.minC !== after.minC,
       'if the box does not move the fixture cannot exhibit the defect at all');
    eq('fixture/1a-box-minC', [2, 0], [before.minC, after.minC]);
    eq('1a/stored-coordinates-hold', 0, d.bad.length,
       `${d.bad.length} of ${d.total} cells read a coordinate they were not painted with`);
    eq('1a/the-canvas-square-is-what-moves', true, seatBefore !== seatAfter,
       'rule 4 says the DB coordinate holds and the canvas is derived — nothing moving means '
       + 'something else got renumbered');
    evidence.push(`1a typed pitch 15->12: box.minC ${before.minC}->${after.minC}, `
      + `disagree ${d.bad.length}/${d.total}, cell "9,1" canvas seat ${seatBefore} -> ${seatAfter}`);
  }

  // ══ 1b. THE GEOMETRY PRESET, FROM THE DROPDOWN ═══════════════════════════════════════
  //     The operator's whole gesture is: pick an entry, the select fires `change`. Everything
  //     after that is the product's business —
  //       #preset-select change -> loadSelectedPreset -> applyPresetObject
  //         -> (writes the six phys inputs; reads and IGNORES the preset's rotation/side)
  //         -> applyPhysicalGeometry -> derives cols/rows -> reseatCellsToStoredCoords
  //         -> renderGridCanvas
  //     so the fixture sets the select's value and fires the event, and asserts nothing about
  //     which of those functions did the work.
  //
  //     The preset is a REAL row out of `server/config/maps.json`: `BASE_OFFSET` carries
  //     `phys_offset_x/y: 10` and `rotation: 270`. Both matter. Offsets feed `getScreenShift`
  //     and every earlier geometry fixture here used 0 -> 0, which killed that axis outright;
  //     the declared rotation is the case that would make the reaction REFUSE by design if
  //     `applyPresetObject` ever started applying orientation.
  {
    const PRESETS = {
      base_std: { name: 'BASE', phys_wafer_dia: 300, phys_chip_x: 11, phys_chip_y: 13,
                  phys_offset_x: 0, phys_offset_y: 0, phys_edge_margin: 3,
                  rotation: 0, side: 'front', is_custom: true },
      custom_1785446867113: { name: 'BASE_OFFSET', phys_wafer_dia: 300, phys_chip_x: 11,
                  phys_chip_y: 13, phys_offset_x: 10, phys_offset_y: 10, phys_edge_margin: 3,
                  rotation: 270, side: 'front', is_custom: true },
    };
    const BASE = { cols: 29, rows: 25, startX: 1, startY: 1, invertY: false,
                   rotation: 0, side: 'front', dia: 300, chipX: 11, chipY: 13,
                   offX: 0, offY: 0, margin: 3 };
    const { S } = buildEnv(src, BASE, { table: 'bonding_map', serverPresets: PRESETS });
    const painted = paintOracle(S);
    S.renderGridCanvas();
    const dimsBefore = `${S.el.gridCols.value}x${S.el.gridRows.value}`;
    const before = boxOf(S);
    const rotBefore = S.currentRotation;

    S.el.presetSelect.value = 'custom_1785446867113';
    fire(S.el.presetSelect, 'change', '#preset-select');

    const after = boxOf(S);
    const d = disagreements(S, painted);
    eq('fixture/1b-the-preset-really-moved-the-origin', true,
       before.minC !== after.minC || before.minR !== after.minR,
       'a preset that leaves the origin box where it was cannot score this rule at all');
    eq('fixture/1b-preset-declared-rotation-was-ignored', rotBefore, S.currentRotation,
       'BASE_OFFSET declares rotation 270. If it were applied, the reaction would refuse by '
       + 'design (rule 5) and this case would be asserting the wrong thing');
    eq('1b/stored-coordinates-hold', 0, d.bad.length,
       `${d.bad.length} of ${d.total} cells moved coordinate on a preset change`);
    eq('1b/preset-loses-no-cell', 0, d.lost,
       'a re-seat that maps two cells onto one key DESTROYS one, and a survivors-only count '
       + 'would report that as zero disagreements');
    evidence.push(`1b dropdown change -> BASE_OFFSET (offset 0,0 -> 10,10, rot 270 declared): `
      + `grid ${dimsBefore} -> ${S.el.gridCols.value}x${S.el.gridRows.value}, `
      + `box minC/minR ${before.minC}/${before.minR} -> ${after.minC}/${after.minR}, `
      + `rotation ${rotBefore} -> ${S.currentRotation}, painted ${painted}, `
      + `disagree ${d.bad.length}/${d.total}, lost ${d.lost}`);
  }

  // ══ 1c. TYPING IS NOT ONE EVENT ══════════════════════════════════════════════════════
  //     `input` fires per keystroke, so replacing "15" with "12" goes through "1" — and
  //     clearing the box first goes through "" , which `physNum` reads as the 2.5 default.
  //     Every intermediate state is a real geometry, gets a real reaction, and the reaction
  //     updates the record; the steps therefore have to COMPOSE. If any step compared against
  //     a record two states old, the coordinate would drift and never come back.
  {
    const { S } = buildEnv(src, F.QERWER, { table: 'dt_map' });
    const painted = paintOracle(S);
    S.renderGridCanvas();
    const seen = [];
    // '20' pushes the box OUT and '1'/'' pull it all the way in, so the steps do not all move
    // the origin the same way — a run whose intermediate boxes were identical would compose
    // trivially and prove nothing.
    for (const keystroke of ['20', '', '1', '12']) {
      S.el.physChipX.value = keystroke;
      S.el.physChipY.value = keystroke;
      fire(S.el.physChipX, 'input', '#phys-chip-x');
      fire(S.el.physChipY, 'input', '#phys-chip-y');
      seen.push(`${keystroke || '(empty)'}:minC${boxOf(S).minC}`);
    }
    const d = disagreements(S, painted);
    eq('fixture/1c-intermediates-differ', true, new Set(seen.map(s => s.split(':')[1])).size > 1,
       'every intermediate box was the same, so the steps composed trivially');
    eq('1c/every-keystroke-composes', 0, d.bad.length,
       `${d.bad.length} of ${d.total} cells drifted across four intermediate geometries`);
    evidence.push(`1c keystrokes ${seen.join(' ')} -> disagree ${d.bad.length}/${d.total}`);
  }

  // ══ 1d. THE GRID DIMENSIONS ARE A GEOMETRY EDIT TOO ══════════════════════════════════
  //     `COLS`/`ROWS` are the fourth place the origin box moves under the cells, and the one
  //     nobody had looked at: `map_editor.js` wired them to a clamp and a redraw while the six
  //     physical-spec inputs went through the reaction.
  //
  //     WHY IT DRIFTS — and why it is NOT simply "the box moved". Two things move together
  //     when a dimension changes, and the drift is their DIFFERENCE:
  //       · the origin box. `isCellInsideWaferFast` lays the wafer circle over a 700px canvas
  //         cut into `visualCols` columns, so the circle's radius in CELLS is constant
  //         (`effectiveRadius / chipX`) while its centre is `visualCols / 2`.
  //       · the die index itself. `getDieIndex` is wafer-centre relative
  //         (`colVisual - (visualCols - 1) / 2`, plus a parity term), so the KEY of a cell
  //         that keeps its canvas square changes too.
  //     When the two shift by the same amount they cancel and the coordinate holds with no
  //     reaction at all; when they do not, EVERY cell renumbers.
  //
  // 🔴 FIXTURE ACTIVITY, MEASURED (2026-07-31, sweep over the three production frames,
  //    +-1..+-3 on each axis): 16 of 36 dimension edits drift, and each of those 16 drifts
  //    100% of the map (261/261, 273/273, 461/461). The other 20 hold on their own, and there
  //    the reaction moves a MEASURED zero. An earlier draft of this case used COLS 33->35 and
  //    ROWS 25->27, and both of those are in the second group — the case was green before the
  //    fix existed. The two edits below are taken from the first group.
  //    ⚠️ `QERWER cols 23->22` drifts 261/261 with `box.minC` UNCHANGED at 2. "The box did not
  //       move" is therefore not a proof that there is nothing to react to.
  {
    // (i) the ROW axis, on the frame with anisotropic chip, non-zero offset and negative START
    const { S } = buildEnv(src, F.DTWWER, { table: 'bonding_map' });
    const painted = paintOracle(S);
    S.renderGridCanvas();
    const before = boxOf(S);
    const seatBefore = seatOfValue(S, '1,1');

    S.el.gridRows.value = '26';                 // 25 -> 26
    fire(S.el.gridRows, 'change', '#grid-rows');

    const after = boxOf(S);
    const d = disagreements(S, painted);
    const seatAfter = seatOfValue(S, '1,1');

    eq('fixture/1d-population', 461, painted, 'the DTWWER frame\'s own painted set');
    eq('fixture/1d-rows-really-moves-the-origin', true, before.minR !== after.minR,
       'an edit that leaves the origin box alone cannot score this rule');
    eq('fixture/1d-box-minR', [2, 3], [before.minR, after.minR]);
    eq('1d/rows-stored-coordinates-hold', 0, d.bad.length,
       `${d.bad.length} of ${d.total} cells read a coordinate they were not painted with`);
    eq('1d/rows-loses-no-cell', 0, d.lost,
       'two cells re-seated onto one key destroys one, and a survivors-only count reports '
       + 'that as zero disagreements');
    eq('1d/the-canvas-square-is-what-moves', true, seatBefore !== seatAfter,
       'rule 4: the DB coordinate holds and the canvas seat is derived');
    evidence.push(`1d ROWS 25->26 (DTWWER): box.minR ${before.minR}->${after.minR}, `
      + `painted ${painted}, disagree ${d.bad.length}/${d.total}, lost ${d.lost}, `
      + `cell "1,1" canvas seat ${seatBefore} -> ${seatAfter}`);
  }
  {
    // (ii) the COLUMN axis. A separate frame because DTWWER's column edits all fall in the
    //      self-cancelling group — scoring both axes on one frame would have scored one.
    const { S } = buildEnv(src, F.QERWER, { table: 'dt_map' });
    const painted = paintOracle(S);
    S.renderGridCanvas();
    const before = boxOf(S);
    // A value taken from the painted set, so the seat probe can never be null-vs-null (which
    // would satisfy "the seat moved" trivially in the wrong direction).
    const probeVal = Object.values(S.gridData)[0];
    const seatBefore = seatOfValue(S, probeVal);

    S.el.gridCols.value = '24';                 // 23 -> 24
    fire(S.el.gridCols, 'change', '#grid-cols');

    const after = boxOf(S);
    const d = disagreements(S, painted);
    const seatAfter = seatOfValue(S, probeVal);

    eq('fixture/1d2-population', 261, painted);
    eq('fixture/1d2-cols-really-moves-the-origin', true, before.minC !== after.minC);
    eq('fixture/1d2-box-minC', [2, 3], [before.minC, after.minC]);
    eq('fixture/1d2-seat-probe-exists', true, !!seatBefore,
       'a null-vs-null seat probe would make the seat assertion below meaningless');
    eq('1d2/cols-stored-coordinates-hold', 0, d.bad.length,
       `${d.bad.length} of ${d.total} cells read a coordinate they were not painted with`);
    eq('1d2/cols-loses-no-cell', 0, d.lost);
    eq('1d2/the-canvas-square-is-what-moves', true, seatBefore !== seatAfter);
    evidence.push(`1d2 COLS 23->24 (QERWER): box.minC ${before.minC}->${after.minC}, `
      + `painted ${painted}, disagree ${d.bad.length}/${d.total}, lost ${d.lost}, `
      + `cell "${probeVal}" canvas seat ${seatBefore} -> ${seatAfter}`);
  }
  // ══ 1e. A DIMENSION EDIT IS NOT AN ORIENTATION EDIT (rule 5 must not fire) ════════════
  //     `#grid-y-invert` sits in the SAME listener array as COLS/ROWS. It is rule 5 — it holds
  //     the die and moves the number — so the reaction must stay out of its path.
  {
    const { S } = buildEnv(src, F.DTWWER, { table: 'bonding_map' });
    const painted = paintOracle(S);
    S.renderGridCanvas();
    const keysBefore = Object.keys(S.gridData).sort().join('|');
    S.el.gridYInvert.checked = true;
    fire(S.el.gridYInvert, 'change', '#grid-y-invert');
    const keysAfter = Object.keys(S.gridData).sort().join('|');
    const d = disagreements(S, painted);
    eq('1e/y-invert-holds-the-die', true, keysBefore === keysAfter,
       'Y-invert must not re-seat: it renumbers, exactly like a rotation');
    eq('fixture/1e-y-invert-really-renumbers', true, d.bad.length > 0,
       'if flipping Y renumbered nothing this case would pass for the wrong reason');
    evidence.push(`1e Y-invert (rule 5, must not re-seat): keys moved `
      + `${keysBefore === keysAfter ? 0 : 'some'}, renumbered ${d.bad.length}/${d.total}`);
  }

  // ══ 2. THE SAME EDIT UNDER A DECLARED MASK ═══════════════════════════════════════════
  //     One reaction, both bases. Here it must move NOTHING, and that zero is measured, not
  //     assumed: the mask box translates with the cells, so the stored coordinate never moved.
  {
    const { S } = buildEnv(src, F.DTWWER, { table: 'bonding_map' });
    const refCells = parseCells(BASE_4E_CELLS);
    const keys = S.projectCellsToPhys(refCells, S.frameFromMeta(F.BASE_4E_META));
    S.validDie = { basis: 'ref', keys, reason: '', ref: { table: 'bonding_map', mapKey: 'BASE_4E' }, raw: null };
    S.boundingBoxCache = {};
    const painted = paintOracle(S);
    S.renderGridCanvas();
    const before = boxOf(S);
    const keysBefore = Object.keys(S.gridData).sort().join('|');

    S.el.physChipX.value = '8';
    fire(S.el.physChipX, 'input', '#phys-chip-x');
    const d = disagreements(S, painted);
    const keysAfter = Object.keys(S.gridData).sort().join('|');

    eq('fixture/2-mask-is-live', true, keys.size > 100 && S.validDieBasis() === 'ref');
    eq('fixture/2-mask-box-is-not-the-circle-box', true, before.minC > 0,
       'a mask whose bbox starts at column 0 cannot show a bbox-term defect');
    eq('2/mask-basis-stored-coordinates-hold', 0, d.bad.length);
    eq('2/mask-basis-moves-nothing', true, keysBefore === keysAfter,
       'under a declared mask the region translates with the cells, so the reaction is a '
       + 'MEASURED zero — a non-zero here means the pre-edit box was read on the wrong basis');
    evidence.push(`2 mask basis, chipX 9.7->8: mask ${keys.size} keys, box.minC ${before.minC}, `
      + `painted ${painted}, disagree ${d.bad.length}/${d.total}, keys moved ${keysBefore === keysAfter ? 0 : 'some'}`);
  }

  // ══ 5. ORIENTATION IS THE OPPOSITE OPERATION (rule 5) ════════════════════════════════
  //     Rotation holds the DIE and moves the number. The geometry reaction must not fire.
  {
    const { S } = buildEnv(src, F.QERWER, { table: 'dt_map' });
    paintOracle(S);
    S.renderGridCanvas();
    const counts = {};
    for (const rot of [90, 180, 270]) {
      const { S: T } = buildEnv(src, F.QERWER, { table: 'dt_map' });
      const painted = paintOracle(T);
      T.renderGridCanvas();
      const keysBefore = Object.keys(T.gridData).sort().join('|');
      T.currentRotation = rot;
      T.boundingBoxCache = {};
      // A rotation goes straight to the renderer — no geometry reaction anywhere on the path.
      // The guard inside the reaction is scored directly, so a future caller cannot smuggle
      // rule 4 onto rule 5's path.
      // Deliberately still a DIRECT call: no listener anywhere reaches the reaction on a
      // rotation, so there is no event to fire. Calling it by hand is the stronger test —
      // it asks the guard itself to refuse, so a future caller cannot smuggle rule 4 onto
      // rule 5's path.
      T.reseatCellsToStoredCoords(T.cellsSeatedUnder);
      T.renderGridCanvas();
      const keysAfter = Object.keys(T.gridData).sort().join('|');
      const d = disagreements(T, painted);
      counts[rot] = d.bad.length;
      eq(`5/rot${rot}-holds-the-die`, true, keysBefore === keysAfter,
         'rotation must not re-seat: the die stays and the number moves');
    }
    eq('fixture/5-rotation-really-renumbers', true,
       counts[90] > 0 && counts[180] > 0 && counts[270] > 0,
       'if rotation renumbered nothing this case would pass for the wrong reason');
    evidence.push(`5 rotation renumbering (rule 5, unchanged): 90:${counts[90]} `
      + `180:${counts[180]} 270:${counts[270]}`);
  }

  return { failures, compared, evidence };
}

// ── The designation path (async: resolveValidDie drives the network stubs) ───────────────
async function runDesignation(src) {
  const failures = [];
  let compared = 0;
  const evidence = [];
  const eq = (name, expected, actual, note) => {
    compared++;
    const a = JSON.stringify(actual), e = JSON.stringify(expected);
    if (a !== e) failures.push(`${name}: expected ${e}, got ${a}${note ? ` — ${note}` : ''}`);
  };

  const cases = [
    { label: '3/A2<-DT_TEST', panel: F.A2, refMeta: F.DT_TEST_META, refCount: 326, refCells: DT_TEST_CELLS,
      meta: { grid_cols: 23, grid_rows: 23, grid_start_x: 1, grid_start_y: 1,
              grid_y_invert: false, rotation: 0, side: 'front', phys_wafer_dia: 300,
              phys_chip_x: 14.3, phys_chip_y: 15.2, phys_offset_x: 0, phys_offset_y: 0,
              phys_edge_margin: 3, valid_die_ref: 'DT_TEST' },
      home: 'A2', expectDims: true },
    { label: '4/DTWWER<-BASE_4E', panel: F.DTWWER, refMeta: F.BASE_4E_META, refCount: 262, refCells: BASE_4E_CELLS,
      meta: { ...F.BASE_4E_META, valid_die_ref: { table: 'bonding_map', map_id: 'BASE_4E' } },
      home: 'DTWWER', expectDims: false },
  ];

  for (const c of cases) {
    // The rows the stubbed fetch will return: the reference map's own stored cells.
    const refCells = parseCells(c.refCells);
    eq(`fixture/${c.label}-ref-cell-count`, c.refCount, refCells.length,
       'the reference map\'s own production cell count — a mask of a different size is a '
       + 'different fixture');

    const { S } = buildEnv(src, c.panel, { table: 'bonding_map', refMeta: c.refMeta, refCells });
    const painted = paintOracle(S);
    S.renderGridCanvas();
    const dimsBefore = `${S.el.gridCols.value}x${S.el.gridRows.value}`;
    const keysBefore = Object.keys(S.gridData).sort().join('|');

    await S.resolveValidDie(c.meta, 'bonding_map', c.home);

    const dimsAfter = `${S.el.gridCols.value}x${S.el.gridRows.value}`;
    const d = disagreements(S, painted);
    const keysAfter = Object.keys(S.gridData).sort().join('|');
    const before = new Set(keysBefore.split('|'));
    let reseated = 0;
    keysAfter.split('|').forEach(k => { if (!before.has(k)) reseated++; });

    eq(`fixture/${c.label}-mask-resolved`, 'ref', S.validDieBasis(),
       `refusal reason: ${S.validDie && S.validDie.reason}`);
    eq(`fixture/${c.label}-population`, true, painted > 0);
    eq(`${c.label}/stored-coordinates-hold`, 0, d.bad.length,
       `${d.bad.length} of ${d.total} cells moved coordinate on designation`);
    // 🔴 "0 moved" in this round's acceptance means 0 COORDINATES moved, which is the line
    //    above. Canvas seats DO move here, and must: the mask redefines the origin box, so a
    //    cell that kept its square would be reading a different number. An earlier draft of
    //    this harness asserted the seats were unchanged and went red on 1e4f23c too — the
    //    assertion, not the code, was measuring the wrong thing.
    eq(`fixture/${c.label}-designation-really-re-seats`, true, reseated > 0,
       'if designating a reference re-seated nothing, this case would pass for the wrong reason');
    if (c.expectDims) {
      eq(`fixture/${c.label}-grid-re-derives`, true, dimsBefore !== dimsAfter,
         'rule 1-b: the grid follows the valid die\'s geometry');
    }
    evidence.push(`${c.label}: grid ${dimsBefore} -> ${dimsAfter}, painted ${painted}, `
      + `disagree ${d.bad.length}/${d.total}, canvas seats re-taken ${reseated}`);
  }
  return { failures, compared, evidence };
}

// ═══════════════════════════════════════════════════════════════════════════════════════
// [1-b] WHAT COMMITS THE VALID-DIE KEY — and, far more importantly, WHAT MUST NOT.
//
// THE COMPLAINT BEING SCORED, in the user's words: "타이핑하면서 중간에 바뀌는게 불편했던것."
// 🎯 APPLY existed to answer it and has now been deleted, because the key control became a
// real `<select>` and choosing an option IS the deliberate act the button was standing in for.
//
// 🔴 THE DANGER IS THE FALLBACK. The `<select>` is NOT always the control — it degrades to a
//    text input on `truncated`, on `unavailable`, and when the declared key is absent from the
//    list. Typing comes back there, and if application hung off `change` in that path the exact
//    complaint returns IN THE LEAST VISIBLE CIRCUMSTANCE. `change` on a text input is not a
//    commit: it also fires on BLUR, so tabbing away or clicking the canvas to look at something
//    would re-derive the grid and re-seat every cell. So the fallback commits on ENTER only.
//
// 🔴 WHY THIS IS SCORED AS A COUNTER ON THE WIRING, not as a source read. The whole question is
//    "which gesture reaches the applier", and only running `initDOMElements` and dispatching
//    real events can answer it. `onValidDieRefChanged` is REPLACED WITH A COUNTER after the
//    wiring runs: the applier itself is scored by `runDesignation` above, and re-running it here
//    would score the reaction rather than the trigger.
//
// 🔴 THE AXIS IS ACTIVE BY CONSTRUCTION. Six of these eight cases expect ZERO applications, so
//    an implementation that never applies at all would satisfy them — the two that expect ONE
//    (Enter, and the dropdown) are what makes the zeros mean something. Both are asserted.
//
// ⚠️ IME. In a Korean UI the Enter that COMMITS A HANGUL COMPOSITION is not the operator saying
//    "apply this" — it is the operator still typing. Reading it as a commit reintroduces the
//    complaint in the one language this screen is actually used in, so it is scored explicitly.
// ═══════════════════════════════════════════════════════════════════════════════════════
function runValidDieCommit(src) {
  const failures = [];
  let compared = 0;
  const evidence = [];
  const eq = (name, expected, actual, note) => {
    compared++;
    const a = JSON.stringify(actual), e = JSON.stringify(expected);
    if (a !== e) failures.push(`${name}: expected ${e}, got ${a}${note ? ` — ${note}` : ''}`);
  };

  // One environment, one wiring run, then every gesture is dispatched against it. Counters
  // replace the two stubs so both "did it apply" and "did it merely re-render" are visible.
  // ⚠️ WHY THE COUNTER CAN ONLY BE PUT ON `onValidDieRefChanged`. `initDOMElements` registers
  //    `renderValidDieKeyControl` BY REFERENCE (`addEventListener('input', renderValidDieKey
  //    Control)`), so replacing the sandbox binding afterwards cannot see it — the listener
  //    already holds the old function. The applier is different: it is called from INSIDE an
  //    arrow function, so the name resolves at call time and the swap is observed. Anything
  //    registered by reference is therefore scored by LISTENER COUNT instead, which is what
  //    `dispatchEvent` returns. (An earlier draft asserted a render counter here and went red
  //    against correct code — the assertion was measuring a binding that was never consulted.)
  const { S } = buildEnv(src, F.A2, { table: 'bonding_map' });
  let applies = 0;
  const seenKeyAtApply = [];
  S.onValidDieRefChanged = () => {
    applies++;
    seenKeyAtApply.push(S.el.validDieRefKey ? S.el.validDieRefKey.value : '<no input>');
  };

  const key = S.el.validDieRefKey;
  const sel = S.el.validDieRefSelect;
  eq('fixture/both-valid-die-controls-were-wired', true, !!key && !!sel,
     'initDOMElements did not bind the key control — nothing below would be dispatched at it');

  // A gesture, and what it cost. `dispatchEvent` is used directly rather than `fire` because
  // several of these deliberately have NO listener, and "nothing listened" is a passing answer
  // for them — the assertion is on the applier, not on the listener count.
  const gesture = (node, ev) => {
    const a0 = applies;
    const n = node.dispatchEvent(ev);
    return { applied: applies - a0, listeners: n };
  };

  // ── (a) TYPING. This is the complaint, verbatim. A listener DOES run here (the control has
  //    to re-decide select-vs-input as an unlisted key is typed), so this case distinguishes
  //    "wired but does not apply" from "not wired at all" — the latter would pass a bare
  //    zero-check while the control silently stopped re-shaping itself.
  const typed = gesture(key, { type: 'input' });
  eq('typing into the key field applies NOTHING', 0, typed.applied,
     'this is the exact defect the user reported');
  eq('...but a listener DID run on it (the control re-decides its shape)', 1, typed.listeners,
     'a zero here would mean the input path is simply unwired, and the zero above would be free');

  // ── (b) `change` — the trap. It LOOKS like a commit and is not: it also fires on blur, so
  //    clicking the canvas to check something would re-derive the grid under the operator.
  const changed = gesture(key, { type: 'change' });
  eq('`change` (= blur, or Enter) on the key field applies NOTHING', 0, changed.applied,
     'change fires when focus LEAVES; committing there is the pre-3-a behaviour returning');
  const blurred = gesture(key, { type: 'blur' });
  eq('blur on the key field applies NOTHING', 0, blurred.applied,
     'tabbing away mid-thought is not a decision to apply');

  // ── (c) A KEYSTROKE THAT IS NOT ENTER. Guards against "commit on any keydown", which passes
  //    the Enter case below while being keystroke-level application.
  const otherKey = gesture(key, { type: 'keydown', key: 'a' });
  eq('an ordinary keystroke applies NOTHING', 0, otherKey.applied);

  // ── (d) IME. `isComposing` and the legacy `keyCode === 229` both mean "still composing".
  const imeEnter = gesture(key, { type: 'keydown', key: 'Enter', isComposing: true });
  eq('Enter that COMMITS AN IME COMPOSITION applies NOTHING', 0, imeEnter.applied,
     'in a Korean UI this Enter is the operator still typing');
  const legacyIme = gesture(key, { type: 'keydown', key: 'Enter', keyCode: 229 });
  eq('...and the legacy keyCode 229 spelling of the same thing', 0, legacyIme.applied);

  // ── (e) ENTER. The one gesture in the fallback that IS a commit, and the reason every zero
  //    above is a measurement rather than a description of a dead control.
  key.value = 'TYPED_KEY';
  const enter = gesture(key, { type: 'keydown', key: 'Enter' });
  eq('Enter in the key field APPLIES, exactly once', 1, enter.applied,
     'without this the eight zeros above are satisfied by a control that does nothing');
  eq('...and the applier sees the value that was in the field', 'TYPED_KEY',
     seenKeyAtApply[seenKeyAtApply.length - 1]);

  // ── (f) THE DROPDOWN. Choosing an option is itself the deliberate act, so it applies at
  //    once — this is what made 🎯 APPLY redundant. The ORDER is the contract: the key input
  //    is the single source of truth and `onValidDieRefChanged` reads it, so writing the
  //    value must happen BEFORE the call or the previous key is what gets applied.
  sel.value = 'PICKED_FROM_LIST';
  const picked = gesture(sel, { type: 'change' });
  eq('choosing from the dropdown APPLIES, exactly once', 1, picked.applied,
     'this is what replaced the 🎯 APPLY button');
  eq('...and the key input already held the chosen value when the applier ran',
     'PICKED_FROM_LIST', seenKeyAtApply[seenKeyAtApply.length - 1],
     'apply-then-write applies the PREVIOUS key while the screen shows the new one');
  eq('...and the dropdown wrote through to the single source of truth',
     'PICKED_FROM_LIST', key.value);

  // ── (g) THE BUTTONS ARE GONE. Scored on the markup, because a leftover button in the HTML
  //    with no listener is not visible to any of the above.
  eq('the 🎯 APPLY button is gone from the markup', false, HTML.includes('btn-valid-die-apply'));
  eq('the 💾 SAVE button is gone from the markup', false, HTML.includes('btn-valid-die-save'));
  // The explanatory <p> named both buttons. A stale instruction is worse than none.
  eq('...and the explanatory text no longer names them', false,
     /🎯 APPLY|💾 SAVE/.test(HTML.slice(HTML.indexOf('valid-die-ref-list'),
       HTML.indexOf('phys-wafer-dia'))));

  evidence.push(`valid-die commit: input ${typed.applied}, change ${changed.applied}, `
    + `blur ${blurred.applied}, key'a' ${otherKey.applied}, IME-Enter ${imeEnter.applied}, `
    + `Enter ${enter.applied}, select-change ${picked.applied} (applications)`);
  return { failures, compared, evidence };
}

// ── Mutations: every green above is paired with a defect that must make it red ───────────
const CR = String.fromCharCode(13);
function toCrlf(s) { return s.split('\n').join(CR + '\n'); }

function once(src, find, repl) {
  // The source file is CRLF. Anchors are written with plain newlines so they stay readable
  // here; a literal search would miss every multi-line anchor and report it as "not found".
  if (src.indexOf(find) < 0 && src.indexOf(toCrlf(find)) >= 0) {
    find = toCrlf(find);
    repl = toCrlf(repl);
  }
  const i = src.indexOf(find);
  if (i < 0) die(`mutation anchor not found: ${find.slice(0, 70)}`);
  if (src.indexOf(find, i + 1) >= 0) die(`mutation anchor is not unique: ${find.slice(0, 70)}`);
  return src.slice(0, i) + repl + src.slice(i + find.length);
}

// REFLOW-PROOF VARIANT. Same discipline as `once` (must match, must match exactly once --
// a mutation that silently stops applying is a disarmed check, which is why both cases die
// loudly), but the anchor is a PATTERN, so a formatter that only moves line breaks and
// indentation inside the matched span cannot disarm it. Use this where the thing being
// mutated is a whole multi-line expression: matching its shape is not weaker than matching
// its exact text, because the replacement still removes precisely that expression. Do NOT
// use it to match less than the mutation changes -- a weaker mutation is worse than a
// brittle anchor. c0a3715 (formatter reflow) is why this exists: it re-indented one
// continuation line by two spaces and killed the orientation-guard mutant below.
function onceRe(src, re, repl) {
  const all = src.match(new RegExp(re.source, re.flags.includes('g') ? re.flags : re.flags + 'g'));
  if (!all || all.length === 0) die(`mutation anchor pattern matched nothing: ${re}`);
  if (all.length > 1) die(`mutation anchor pattern is not unique (${all.length} matches): ${re}`);
  return src.replace(new RegExp(re.source, re.flags.replace('g', '')), repl);
}

const MUTANTS = {
  // The defect exactly as 1e4f23c shipped it: nothing reacts to the origin box moving.
  'reaction-is-a-no-op': (s) => once(s,
    '  const now = seatingSnapshot();\n  if (now) cellsSeatedUnder = now;\n  if (!was || !now) return null;',
    '  const now = seatingSnapshot();\n  if (now) cellsSeatedUnder = now;\n  if (!was || !now) return null;\n  if (now) return null;'),
  // The frame window stops carrying the box, so the pre-edit coordinates are recovered on the
  // wrong basis. Only a declared mask can see this.
  'frame-window-drops-the-box': (s) => once(s,
    '  if (physFrameOverride && physFrameOverride.box && !(opts && opts.circleOnly)) {\n    return physFrameOverride.box;\n  }',
    '  if (false) {\n    return physFrameOverride.box;\n  }'),
  // Rule 4 fires on rule 5's path.
  // Anchored on the guard's SHAPE (its first term through its `return null;`) rather than
  // its exact text: the replacement still deletes the entire orientation guard, which is
  // the whole of what this mutant does.
  'orientation-guard-removed': (s) => onceRe(s,
    /if \(was\.rotation[\s\S]*?return null;/,
    'if (false) return null;'),
  // Deriving the grid from the new spec WITHOUT re-seating is the behaviour 94b9baa was
  // rejected for. Only the preset path (1b) sees it; the typed-pitch path calls the reaction
  // itself, which is exactly why both paths are scored.
  'derive-the-grid-but-do-not-re-seat': (s) => once(s,
    '  reseatCellsToStoredCoords(cellsSeatedUnder);\n\n  renderGridCanvas();',
    '\n  renderGridCanvas();'),
  // The valid-die path caches the seating record before `applyPresetObject` instead of reading
  // it at fire time, so the geometry leg gets applied twice.
  'designation-caches-the-record': (s) => once(
    once(s,
      '    if (!cellsSeatedUnder) cellsSeatedUnder = seatingSnapshot();',
      '    if (!cellsSeatedUnder) cellsSeatedUnder = seatingSnapshot();\n    const staleRecord = cellsSeatedUnder;'),
    '    const placed = reseatCellsToStoredCoords(cellsSeatedUnder);',
    '    const placed = reseatCellsToStoredCoords(staleRecord);'),
  // ── THE WIRING ITSELF. These two are the reason the fixtures moved up to the event: with
  //    the listener gone the product does nothing at all, and a fixture that called
  //    `applyPresetObject` / `reseatCellsToStoredCoords` by hand stays green through both.
  'preset-dropdown-is-not-wired': (s) => once(s,
    "    el.presetSelect.addEventListener('change', loadSelectedPreset);",
    '    // unwired'),
  'physical-inputs-are-not-wired': (s) => once(s,
    ["      input.addEventListener('change', onPhysicalGeometryEdit);",
     "      input.addEventListener('input', onPhysicalGeometryEdit);"].join('\n'),
    '      // unwired'),
  // The defect this round closed: COLS/ROWS clamp and redraw, and nothing reacts to the
  // origin box moving under the cells. 8 spaces of indent is what distinguishes this call
  // from the three other sites of the same reaction.
  // 🔴 CONTROL RUN, 2026-07-31. Two semantically identical mutants were put in this map and
  //    scored: a trailing space at this same call site, and a comment line appended at EOF.
  //    Both came back NOT CAUGHT (8/10), so the count below is discrimination and not
  //    decoration. `copy_header_count` was reporting 12/12 while separating 2 of 12, and a
  //    control mutant returning "CAUGHT" is what exposed it.
  'grid-dimension-edits-do-not-reseat': (s) => once(s,
    '        reseatCellsToStoredCoords(cellsSeatedUnder);',
    '        // no reaction'),

  // ── [1-b] THE VALID-DIE COMMIT GESTURE. Five defects, each of which restores some form of
  //    "it changed while I was typing" while leaving the screen looking correct.
  //
  //    The first is the regression proper: putting application back on `change`, which is the
  //    literal pre-3-a wiring and the shape the user complained about.
  'valid-die-key-commits-on-change': (s) => once(s,
    ["    el.validDieRefKey.addEventListener('keydown', (e) => {",
     "      if (!e || e.key !== 'Enter') return;",
     "      if (e.isComposing || e.keyCode === 229) return;",
     '      onValidDieRefChanged();',
     '    });'].join('\n'),
    "    el.validDieRefKey.addEventListener('change', onValidDieRefChanged);"),
  // Commit on ANY keydown. Passes the Enter case while being keystroke-level application —
  // the failure mode a fixture that only tested Enter would wave through.
  'valid-die-key-commits-on-every-keystroke': (s) => once(s,
    "      if (!e || e.key !== 'Enter') return;",
    '      if (!e) return;'),
  // The IME guard removed. Invisible to an ASCII-only fixture, and it is the Korean UI that
  // this screen actually runs in.
  'valid-die-ime-enter-commits': (s) => once(s,
    '      if (e.isComposing || e.keyCode === 229) return;',
    '      // no IME guard'),
  // The dropdown moves the value but never applies. This is the state the block was in
  // BEFORE this round, when 🎯 APPLY still existed — with the button deleted it means the
  // control silently does nothing, which is the most likely way to get this wrong.
  'valid-die-select-does-not-apply': (s) => once(s,
    ['      if (el.validDieRefKey) el.validDieRefKey.value = el.validDieRefSelect.value;',
     '      onValidDieRefChanged();'].join('\n'),
    '      if (el.validDieRefKey) el.validDieRefKey.value = el.validDieRefSelect.value;'),
  // Apply BEFORE writing the chosen value through. The applier reads the key input, so this
  // applies the PREVIOUS key while the screen shows the new one — value-correct-looking,
  // value-wrong. Caught only by asserting what the applier saw, not that it ran.
  'valid-die-select-applies-before-it-writes-the-key': (s) => once(s,
    ['      if (el.validDieRefKey) el.validDieRefKey.value = el.validDieRefSelect.value;',
     '      onValidDieRefChanged();'].join('\n'),
    ['      onValidDieRefChanged();',
     '      if (el.validDieRefKey) el.validDieRefKey.value = el.validDieRefSelect.value;'].join('\n')),
};

async function scoreMutant(name, src) {
  let out = { failures: [], evidence: [] };
  try { out = run(src); } catch (e) { return [`threw: ${String(e && e.message).slice(0, 80)}`]; }
  let des = { failures: [] };
  try { des = await runDesignation(src); } catch (e) { des = { failures: [`threw: ${String(e && e.message).slice(0, 80)}`] }; }
  let vdc = { failures: [] };
  try { vdc = runValidDieCommit(src); } catch (e) { vdc = { failures: [`threw: ${String(e && e.message).slice(0, 80)}`] }; }
  return out.failures.concat(des.failures, vdc.failures);
}

// ── main ────────────────────────────────────────────────────────────────────────────────
(async () => {
  const base = run(SRC);
  const des = await runDesignation(SRC);
  const vdc = runValidDieCommit(SRC);
  const failures = base.failures.concat(des.failures, vdc.failures);
  const compared = base.compared + des.compared + vdc.compared;
  const evidence = base.evidence.concat(des.evidence, vdc.evidence);

  if (!mutateOnly || verbose) {
    evidence.forEach(e => console.log('  ' + e));
  }
  console.log(`${failures.length === 0 ? '✓' : '✗'} baseline: ${compared} assertions, `
    + `${failures.length} failure(s)`);
  // H1 protocol: the runner reads this line to tell "red with N assertions" from a crash.
  console.log(`ASSERTIONS ${compared} ${failures.length}`);
  failures.forEach(f => console.log(`   ✗ ${f}`));

  let caught = 0;
  const total = Object.keys(MUTANTS).length;
  for (const [name, fn] of Object.entries(MUTANTS)) {
    const f = await scoreMutant(name, fn(SRC));
    const newOnes = f.filter(x => !failures.includes(x));
    if (newOnes.length > 0) caught++;
    else console.log(`   ✗ mutant '${name}' was NOT caught — the assertions above do not `
      + 'score what they claim to score');
    if (verbose) console.log(`   mutant '${name}': ${newOnes.length} new failure(s)`
      + (newOnes.length ? ` — ${newOnes[0].slice(0, 110)}` : ''));
  }
  console.log(`--- mutation check: ${caught}/${total} defects caught ---`);

  process.exit(failures.length === 0 && caught === total ? 0 : 1);
})();
