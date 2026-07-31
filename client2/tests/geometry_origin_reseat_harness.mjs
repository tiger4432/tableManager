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
const verbose = process.argv.includes('--verbose');
const mutateOnly = process.argv.includes('--mutate');

const die = (msg) => { console.error(`HARNESS FAILURE: ${msg}`); process.exit(2); };

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
  'getScreenShift', 'getTransformedPhysicalConfig', 'isCellInsideWaferFast',
  'getDieIndex', 'getCanvasCellFromDieIndex', 'getCanvasCellFromDb', 'getDbCoords',
  'getWaferBoundingBox',
  'validDieBasis', 'isValidDieAt',
  // THE ONE REACTION and the record it compares against.
  'seatingSnapshot', 'reseatCellsToStoredCoords',
  'frameFromMeta', 'currentFrame', 'resolveFrame', 'frameAxesKey',
  'frameDimBounds', 'frameDimError',
  'applyPresetObject', 'applyPhysicalGeometry',
  'parseValidDieRef', 'validDieChainError', 'validDieRefDisplay', 'projectCellsToPhys',
  'resolveValidDie',
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
  const el = {
    gridCols: makeInput(P.cols), gridRows: makeInput(P.rows),
    gridStartX: makeInput(P.startX), gridStartY: makeInput(P.startY),
    gridYInvert: { checked: !!P.invertY },
    physWaferDia: { value: String(P.dia), querySelector: () => ({}), appendChild() {} },
    physChipX: makeInput(P.chipX), physChipY: makeInput(P.chipY),
    physOffsetX: makeInput(P.offX), physOffsetY: makeInput(P.offY),
    physEdgeMargin: makeInput(P.margin),
    showAnnotations: { checked: false },
    validDieRefKey: makeInput(''), validDieRefTable: makeInput(''), validDieRefList: null,
    gridCanvas: { getBoundingClientRect: () => ({ width: 700, height: 700 }) },
    waferCanvas: { width: 0, height: 0, getContext: () => new Proxy({}, {
      get: (t, k) => (k in t ? t[k] : (t[k] = () => {})), set: (t, k, v) => (t[k] = v, true) }) },
  };
  const sandbox = {
    console: { warn: (m) => log.warns.push(String(m)), info() {}, error() {}, log() {}, debug() {} },
    el,
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
    // Paint constants the real renderer reads. Values are irrelevant here — only the
    // coordinate DECISIONS are scored — but they must exist or the renderer throws.
    UNLISTED_VALUE_FILL: '#10b981',
    overlayLayers: [], loadedFCells: new Set(), serverCellKeys: null,
    paintLockValues: null, currentHoverCell: null, lastSelectionBox: null,
    syncOverlayGeometry() {},
    getThemeColors: () => ({ outBg: '#eee', line: '#ccc', text: '#000', inBg: '#fff',
                             origin: '#f00', notch: '#00f', gridText: '#333', dim: '#999' }),
    performance: { now: () => 0 },
    window: { devicePixelRatio: 1 },
    updateOrientationUI() {}, updateSideIndicator() {},
    scheduleRenderGridCanvas() {},
    updateLegendCounts() {},
    activeOverlayLayers: () => [], drawOverlayMarkers() {}, updateNotchPosition() {},
    isBoxDragging: false, dragType: null,
    getComputedStyle: () => ({ getPropertyValue: () => '#000' }),
    renderValidDieChip() {}, syncValidDieRefControls() {},
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
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  try { vm.runInContext(pieces.join('\n'), sandbox); }
  catch (e) { die(`extracted sources did not evaluate: ${e && e.message}`); }
  return { S: sandbox, el, log };
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

function disagreements(S) {
  const rb = readBack(S);
  const bad = [];
  rb.forEach((v) => { if (v.was !== v.now) bad.push(`${v.was} -> ${v.now}`); });
  return { total: rb.size, bad };
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
    if (typeof S.reseatCellsToStoredCoords === 'function') {
      S.reseatCellsToStoredCoords(S.cellsSeatedUnder);
    }
    const after = boxOf(S);
    const d = disagreements(S);
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

  // ══ 1b. THE GEOMETRY PRESET ITSELF (dropdown -> applyPresetObject) ════════════════════
  //     Same operation through the path the user named. The grid is re-derived here, so the
  //     re-placement has to run AFTER the derived dimensions are in force.
  {
    const { S } = buildEnv(src, F.QERWER, { table: 'dt_map' });
    const painted = paintOracle(S);
    S.renderGridCanvas();
    const dimsBefore = `${S.el.gridCols.value}x${S.el.gridRows.value}`;
    const before = boxOf(S);
    S.applyPresetObject({ name: 'test', phys_wafer_dia: 300, phys_chip_x: 12, phys_chip_y: 12,
                          phys_offset_x: 0, phys_offset_y: 0, phys_edge_margin: 3 });
    const dimsAfter = `${S.el.gridCols.value}x${S.el.gridRows.value}`;
    const d = disagreements(S);
    eq('fixture/1b-grid-really-re-derives', true, dimsBefore !== dimsAfter,
       'a preset that does not move the grid cannot score the ordering of derive vs re-seat');
    eq('fixture/1b-population', 261, painted);
    eq('1b/stored-coordinates-hold', 0, d.bad.length,
       `${d.bad.length} of ${d.total} cells moved coordinate on a preset change`);
    evidence.push(`1b preset chip 15->12: grid ${dimsBefore} -> ${dimsAfter}, `
      + `box.minC ${before.minC}->${boxOf(S).minC}, disagree ${d.bad.length}/${d.total}`);
  }

  // ══ 1c. TYPING IS NOT ONE EVENT ══════════════════════════════════════════════════════
  //     `input` fires per keystroke, so replacing "15" with "12" goes through "1" — and
  //     clearing the box first goes through "" , which `physNum` reads as the 2.5 default.
  //     Every intermediate state is a real geometry, gets a real reaction, and the reaction
  //     updates the record; the steps therefore have to COMPOSE. If any step compared against
  //     a record two states old, the coordinate would drift and never come back.
  {
    const { S } = buildEnv(src, F.QERWER, { table: 'dt_map' });
    paintOracle(S);
    S.renderGridCanvas();
    const seen = [];
    // '20' pushes the box OUT and '1'/'' pull it all the way in, so the steps do not all move
    // the origin the same way — a run whose intermediate boxes were identical would compose
    // trivially and prove nothing.
    for (const keystroke of ['20', '', '1', '12']) {
      S.el.physChipX.value = keystroke;
      S.el.physChipY.value = keystroke;
      if (typeof S.reseatCellsToStoredCoords === 'function') {
        S.reseatCellsToStoredCoords(S.cellsSeatedUnder);
      }
      seen.push(`${keystroke || '(empty)'}:minC${boxOf(S).minC}`);
    }
    const d = disagreements(S);
    eq('fixture/1c-intermediates-differ', true, new Set(seen.map(s => s.split(':')[1])).size > 1,
       'every intermediate box was the same, so the steps composed trivially');
    eq('1c/every-keystroke-composes', 0, d.bad.length,
       `${d.bad.length} of ${d.total} cells drifted across four intermediate geometries`);
    evidence.push(`1c keystrokes ${seen.join(' ')} -> disagree ${d.bad.length}/${d.total}`);
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
    if (typeof S.reseatCellsToStoredCoords === 'function') {
      S.reseatCellsToStoredCoords(S.cellsSeatedUnder);
    }
    const d = disagreements(S);
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
      paintOracle(T);
      T.renderGridCanvas();
      const keysBefore = Object.keys(T.gridData).sort().join('|');
      T.currentRotation = rot;
      T.boundingBoxCache = {};
      // A rotation goes straight to the renderer — no geometry reaction anywhere on the path.
      // The guard inside the reaction is scored directly, so a future caller cannot smuggle
      // rule 4 onto rule 5's path.
      if (typeof T.reseatCellsToStoredCoords === 'function') {
        T.reseatCellsToStoredCoords(T.cellsSeatedUnder);
      }
      T.renderGridCanvas();
      const keysAfter = Object.keys(T.gridData).sort().join('|');
      const d = disagreements(T);
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
    const d = disagreements(S);
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
  'orientation-guard-removed': (s) => once(s,
    "  if (was.rotation !== now.rotation || was.side !== now.side || was.invertY !== now.invertY\n      || was.startX !== now.startX || was.startY !== now.startY) return null;",
    '  if (false) return null;'),
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
};

async function scoreMutant(name, src) {
  let out = { failures: [], evidence: [] };
  try { out = run(src); } catch (e) { return [`threw: ${String(e && e.message).slice(0, 80)}`]; }
  let des = { failures: [] };
  try { des = await runDesignation(src); } catch (e) { des = { failures: [`threw: ${String(e && e.message).slice(0, 80)}`] }; }
  return out.failures.concat(des.failures);
}

// ── main ────────────────────────────────────────────────────────────────────────────────
(async () => {
  const base = run(SRC);
  const des = await runDesignation(SRC);
  const failures = base.failures.concat(des.failures);
  const compared = base.compared + des.compared;
  const evidence = base.evidence.concat(des.evidence);

  if (!mutateOnly || verbose) {
    evidence.forEach(e => console.log('  ' + e));
  }
  console.log(`${failures.length === 0 ? '✓' : '✗'} baseline: ${compared} assertions, `
    + `${failures.length} failure(s)`);
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
