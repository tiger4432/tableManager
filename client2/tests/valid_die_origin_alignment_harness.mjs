/**
 * 🎯 Valid-die origin alignment — ON SCREEN, under every rotation / side / y-invert.
 *
 * SCORES ONE CLAIM, by executing the shipped branch (no model of it):
 *
 *     start_x / start_y is the minimum column / row of the VALID-DIE region, at every
 *     orientation. The origin — the cell that reads (0,0) when start_x/y is placed — is
 *     therefore pinned to the mask, and the mask and the numbering move together.
 *
 * THE DEFECT IT REPLACES. `getWaferBoundingBox` built the coordinate box from the CIRCLE
 * geometry alone (six physical params + cols/rows/rotation/side) and never consulted
 * `validDie`. The circle's bbox is (near-)invariant under rotation and flip; a real valid-die
 * region is not. So each rotation moved the mask relative to the number the screen printed in
 * it, and the number the screen prints is the number ⚡ Push writes.
 *
 * 🔴 WHAT IS MEASURED IS THE SCREEN. Every assertion below reads `gridCells2D` — the cell
 *    objects `renderGridCanvas` actually produced — and nothing else. `cellObj.inside` IS
 *    what the canvas paints as a valid die; `cellObj.x/.y` ARE the numbers `eachSavableCell`
 *    hands to `pushMapData`. No coordinate function participates in an expectation.
 *
 * 🔴 THE OTHER ORACLE IS THE ROW'S OWN VALUE. In the load round-trip every DB row carries
 *    `"x,y"` as its value, so the comparison is key-by-key against a number the transform
 *    never touched. Injectivity / range / round-trip are self-comparisons of one function and
 *    a uniform offset passes all three (map-pm memory).
 *
 * FIXTURE AXES, all live on purpose (asserted, not assumed — see `fixtureSelfCheck`):
 *    chipX 9 != chipY 11        pitch swap at rot 90/270 is a real difference
 *    cols 15 != rows 11         a transposed read cannot pass on width
 *    circle bbox minC/minR > 0  a dropped bbox term cannot hide behind a zero
 *    mask insets 3/0/1/2        left != right != top != bottom, so every rotation and the
 *                               side flip move the mask's minimum by a DIFFERENT amount
 *    startX 4 != startY -2      one negative; an axis swap or a shared offset cannot pass
 *
 * Run:  node client2/tests/valid_die_origin_alignment_harness.mjs [--mutate] [-v]
 * Read-only against client2/. Not gated by `npm run build`; run by hand, per round.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC_PATH = join(HERE, '..', 'src', 'map_editor.js');
// Line endings normalised — every mutation matches a multi-line `\n` string and on a CRLF
// checkout those matches silently MISS (measured 2026-07-30 on a sibling harness: 8 of 18
// mutations went unapplied while the baseline stayed green).
const SRC0 = readFileSync(SRC_PATH, 'utf8').replace(/\r\n/g, '\n');

const die = (m) => { console.error(`HARNESS FAILURE: ${m}\n(Nothing was compared.)`); process.exit(2); };

// 🔴 THE PARAMETER LIST IS WALKED BEFORE THE BODY IS LOOKED FOR. The older harness family
//    finds the body with `indexOf('{')` after the `(`, which on `loadExistingMap(opts = {})`
//    lands on the DEFAULT VALUE's braces and returns a slice ending inside the signature —
//    it then fails as `Unexpected end of input` naming nothing. Close the parens first.
function sliceFunction(source, name) {
  const decl = new RegExp(`(^|\\n)\\s*(?:async\\s+)?function\\s+${name}\\s*\\(`);
  const m = decl.exec(source);
  if (!m) return null;
  const start = m.index + (m[1] ? m[1].length : 0);
  let i = m.index + m[0].length - 1;   // at the '(' of the parameter list
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

// The coordinate path and everything it passes through. A rename here is exit 2, never green.
const SYMBOLS = [
  'physNum', 'gridDimNum', 'withPhysFrame',
  'physDeclaration', 'cellMetrics',   // see the note in geometry_origin_reseat_harness.mjs
  'getScreenShift', 'getTransformedPhysicalConfig', 'isCellInsideWaferFast',
  'getDieIndex', 'getCanvasCellFromDieIndex',
  'validDieBasis', 'isValidDieAt',
  'getWaferBoundingBox', 'getDbCoords', 'getCanvasCellFromDb',
  'computeNotchCell',
  'cellFillColor', 'isProtectedFCell', 'eachSavableCell', 'classifyUnsavableCells',
  'serverCellKeySet', 'getGridCellObject', 'pushBlockingCount',
  'applyPhysicalGeometry', 'applyPresetObject', 'frameDimBounds',
  // The ONE reaction to "the origin box moved under the cells", and the record it
  // compares against. A geometry-preset edit and a valid-die designation reach the SAME
  // function, so a slice that omits it turns applyPhysicalGeometry into a ReferenceError
  // that loadExistingMap's catch reports as a 0-cell load.
  'seatingSnapshot', 'reseatCellsToStoredCoords',
  // THE FUNCTIONS UNDER TEST. Sliced whole and executed — not modelled.
  'renderGridCanvas', 'loadExistingMap',
  // ...and the seven named steps `loadExistingMap` is now written in terms of. They are
  // module-scope functions in the SAME file, so slicing the orchestrator alone would
  // ReferenceError into its own catch and read as a 0-cell load. Each takes what it needs
  // as an argument and returns a value — none touches module state — so the sandbox below
  // needs nothing new declared.
  'collectMapKeyFilterModel', 'scanCoordinateBounds', 'resolveDeclaredGridMeta',
  'promptCoordinateChoice', 'resolveGridFrame', 'deriveLegendFromCellValues',
  'restoreDoeDraftWithPrecedence',
];

// ── Fixture constants ──────────────────────────────────────────────────────────────────
const COLS = 15, ROWS = 11;             // 15 != 11
const CHIP_X = 9, CHIP_Y = 11;          // 9 != 11 -> the rot 90/270 pitch swap is a real swap
const DIA = 116, MARGIN = 3;            // effective radius 55 -> the circle insets the grid
const START_X = 4, START_Y = -2;        // different, one negative
// Mask insets from the circle bbox, in canvas cells at rot 0 / front.
// All four differ, so no rotation and no flip can leave the minimum where the circle put it.
const INSET = { left: 3, right: 0, top: 1, bottom: 2 };

const ROTATIONS = [0, 90, 180, 270];
const SIDES = ['front', 'back'];
const INVERTS = [false, true];

// ── Sandbox ────────────────────────────────────────────────────────────────────────────
function makeInput(v) {
  return { value: String(v), checked: false, textContent: '', disabled: false, style: {},
           classList: { add() {}, remove() {}, toggle() {} },
           querySelector: () => null, appendChild() {},
           addEventListener() {}, removeEventListener() {} };
}

function buildEnv(src, opts = {}) {
  const pieces = [];
  for (const name of SYMBOLS) {
    const code = sliceFunction(src, name);
    if (!code) die(`'${name}' is gone from map_editor.js — renamed or reshaped. Nothing compared.`);
    // Compiled one at a time so a slice that goes wrong NAMES ITSELF.
    try { new vm.Script(code); }
    catch (e) { die(`slice of '${name}' does not parse: ${e && e.message}`); }
    pieces.push(code);
  }

  const log = { toasts: [], alerts: [], warns: [], resolveCalls: [] };
  const panel = opts.panel || {};
  const choice = opts.choice || 'meta';

  const choiceBtn = (which) => {
    const b = makeInput('');
    b.addEventListener = (type, fn) => { if (type === 'click' && which === choice) setTimeout(fn, 0); };
    b.removeEventListener = () => {};
    return b;
  };

  const el = {
    gridCols: makeInput(panel.cols === undefined ? COLS : panel.cols),
    gridRows: makeInput(panel.rows === undefined ? ROWS : panel.rows),
    gridStartX: makeInput(panel.startX === undefined ? START_X : panel.startX),
    gridStartY: makeInput(panel.startY === undefined ? START_Y : panel.startY),
    gridYInvert: { checked: !!panel.invertY },
    physWaferDia: { value: String(panel.dia === undefined ? DIA : panel.dia),
                    querySelector: () => null, appendChild() {} },
    physChipX: makeInput(panel.chipX === undefined ? CHIP_X : panel.chipX),
    physChipY: makeInput(panel.chipY === undefined ? CHIP_Y : panel.chipY),
    physOffsetX: makeInput(0), physOffsetY: makeInput(0),
    physEdgeMargin: makeInput(MARGIN),
    colMapX: makeInput('x'), colMapY: makeInput('y'), colMapVal: makeInput('val'),
    btnLoadMap: makeInput(''),
    choiceModal: { style: { display: 'none' } },
    btnChoiceStandard: choiceBtn('standard'),
    btnChoiceCurrent: choiceBtn('current'),
    btnChoiceCancel: choiceBtn('cancel'),
    gridCanvas: { getBoundingClientRect: () => ({ width: 700, height: 700 }),
                  classList: { add() {}, remove() {} } },
    waferCanvas: { width: 0, height: 0, getContext: () => new Proxy({}, {
      get: (t, k) => (k in t ? t[k] : (t[k] = () => {})), set: (t, k, v) => (t[k] = v, true) }) },
    showAnnotations: { checked: false },
    validDieRefKey: makeInput(''), validDieRefTable: makeInput(''), validDieRefList: null,
    sideIndicator: null, mapWorkspace: null, gridWrapper: null,
  };

  const sandbox = {
    console: { warn: (m) => log.warns.push(String(m)), info() {}, error() {}, log() {}, debug() {} },
    el,
    document: {
      querySelectorAll: (sel) => (sel === '[id^="meta-input-"]'
        ? [{ id: 'meta-input-map_id', value: 'M1' }] : []),
      getElementById: () => null,
      addEventListener() {}, removeEventListener() {},
    },
    setTimeout,
    alert: (m) => log.alerts.push(String(m)),
    physFrameOverride: null,
    boundingBoxCache: {},
    // Where the cells on screen are currently seated. Module-level in the source; declared
    // here so a read of it is a value, not a ReferenceError.
    cellsSeatedUnder: null,
    currentRotation: 0, currentSide: 'front',
    gridData: {}, gridCells2D: {},
    legend: [], activeBrush: '', legendDirty: false,
    legendReplaceScope: null, legendConflict: null,
    legendSaveState: { status: 'idle', at: '', error: '' }, draftBase: null,
    validDie: { basis: 'circle', keys: null, reason: '', ref: null, raw: undefined },
    validDieResolveSeq: 0,
    loadedFCells: new Set(), serverCellKeys: null, overlayLayers: [], activeOverlayLayers: [],
    loadedIdentity: null, selectedTable: 'dt_map',
    tableSchema: { column_types: { x: 'number', y: 'number', val: 'string' } },
    API_BASE: '', OVERLAY_CELL_LIMIT: 2000,
    LEGEND_PALETTE: ['#e11', '#1a1', '#11e', '#ee1', '#1ee', '#e1e'],
    UNLISTED_VALUE_FILL: '#10b981',
    paintLockValues: null, paintLockConfig: { enabled: false }, currentHoverCell: null,
    lastSelectionBox: null, isBoxDragging: false, dragType: null, isOriginMode: false,
    performance: { now: () => 0 }, window: { devicePixelRatio: 1 },
    requestAnimationFrame(fn) { fn(); },
    getComputedStyle: () => ({ getPropertyValue: () => '#000' }),
    getThemeColors: () => ({ outBg: '#eee', line: '#ccc', lineStrong: '#bbb', text: '#000',
      inBg: '#fff', insideEmpty: '#eef', textEmpty: '#345', textOut: '#567', origin: '#f00',
      notch: '#00f', gridText: '#333', dim: '#999', waferEdge: '#111', wmFront: '#eef',
      wmBack: '#fed', accent: '#06c', danger: '#c00', dangerWeak: '#fdd', rangeFill: '#e3e',
      surface: '#fff', success: '#171', warning: '#850' }),
    showToast: (msg, kind) => log.toasts.push({ msg: String(msg), kind }),
    updateOrientationUI() {}, updateSideIndicator() {}, updateLegendCounts() {},
    scheduleRenderGridCanvas() {}, renderLegendTable() {}, renderValidDieChip() {},
    syncValidDieRefControls() {}, syncOverlayGeometry() {}, drawOverlayMarkers() {},
    updateNotchPosition() {}, clearOverlayLayers() {}, seedEmptyDoe() {},
    applyRegistryRowsToLegend() {}, saveLegendToStorage() {}, notifyMapContext() {},
    recordLastOpenMap() {}, setLoadedIdentity() {}, applyDoeDraftRecord: () => false,
    applyDraftCells: () => 0, readDoeDraft: () => null, scheduleCellDraft() {},
    readRegistryScope: async () => ({ ok: true, rows: [] }),
    registryFingerprint: () => 'fp', cellsDigest: () => 'cd',
    declaredLegendRow: () => null, normalizeLegendItem: (o) => o,
    isLockedValue: () => false, getMapIdFromMeta: () => 'M1', getCurrentMapKey: () => 'M1',
    applyRoutedPreset: async () => null,
    fetchGridMetaFor: async () => (opts.gridMeta || null),
    // 🔴 THE ORDERING PROBE. The real `resolveValidDie` installs the mask; the only thing
    //    this round changed about the CALL is WHEN it runs. So the stub records how many
    //    cells `loadExistingMap` had already placed when it was reached. Non-zero = the mask
    //    landed after the cells, which is the ordering the user's sequencing forbids.
    resolveValidDie: async () => {
      log.resolveCalls.push({ cellsPlacedBefore: Object.keys(sandbox.gridData).length });
      if (opts.mask) {
        sandbox.validDieResolveSeq++;
        sandbox.validDie = { basis: 'ref', keys: opts.mask, reason: '',
                             ref: { table: 'dt_map', mapKey: 'TPL' }, raw: 'TPL' };
      }
      return sandbox.validDie;
    },
    fetch: async () => {
      const rows = opts.rows || [];
      return { ok: true, status: 200,
               json: async () => ({ data: rows, total: rows.length }) };
    },
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  try { vm.runInContext(pieces.join('\n'), sandbox); }
  catch (e) { die(`extracted sources did not evaluate: ${e && e.message}`); }
  return { sandbox, el, log };
}

// ── The mask, built once from the circle so it is a realistic subset ───────────────────
// Keys are PHYSICAL (`px_py`) — that is what `isValidDieAt` tests and what
// `projectCellsToPhys` produces in the app. Physical keys are rotation-invariant, so the
// same Set describes the same dies at every orientation. That is the whole point.
function buildMask(S) {
  const cfg = S.getTransformedPhysicalConfig(0, 'front');
  const circle = [];
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      if (S.isCellInsideWaferFast(c, r, COLS, ROWS, cfg, 700, 700)) circle.push({ c, r });
    }
  }
  if (circle.length === 0) die('fixture circle is empty — the wafer spec excludes every cell');
  const cMin = Math.min(...circle.map(p => p.c)), cMax = Math.max(...circle.map(p => p.c));
  const rMin = Math.min(...circle.map(p => p.r)), rMax = Math.max(...circle.map(p => p.r));
  const keys = new Set();
  let kept = 0;
  for (const { c, r } of circle) {
    if (c < cMin + INSET.left || c > cMax - INSET.right) continue;
    if (r < rMin + INSET.top || r > rMax - INSET.bottom) continue;
    const p = S.getDieIndex(c, r, COLS, ROWS, 0, 'front');
    keys.add(`${p.x}_${p.y}`);
    kept++;
  }
  return { keys, kept, circleBox: { minC: cMin, maxC: cMax, minR: rMin, maxR: rMax },
           circleCount: circle.length };
}

// ── Scoring ────────────────────────────────────────────────────────────────────────────
let failures = [];
let compared = 0;
const eq = (name, expected, actual, note) => {
  compared++;
  const a = JSON.stringify(actual), e = JSON.stringify(expected);
  if (a !== e) failures.push(`${name}: expected ${e}, got ${a}${note ? ` — ${note}` : ''}`);
};

// THE SCREEN. Every cell object `renderGridCanvas` produced, flattened.
const screenCells = (S) => {
  const out = [];
  Object.keys(S.gridCells2D || {}).forEach(rStr => {
    Object.keys(S.gridCells2D[rStr] || {}).forEach(cStr => {
      const co = S.gridCells2D[rStr][cStr];
      if (co) out.push(co);
    });
  });
  return out;
};

// THE PAYLOAD, not a model of it.
const pushPayload = (S) => {
  const out = {};
  S.eachSavableCell((co, val) => { out[co.key] = { coord: `${co.x},${co.y}`, val }; });
  return out;
};

// One orientation, rendered, reduced to what the screen shows.
function observe(src, mask, { rotation, side, invertY, startX = START_X, startY = START_Y }) {
  const { sandbox: S } = buildEnv(src, { panel: { startX, startY, invertY } });
  S.validDieResolveSeq = 1;
  S.validDie = { basis: 'ref', keys: mask, reason: '', ref: { table: 'dt_map', mapKey: 'TPL' }, raw: 'TPL' };
  S.currentRotation = rotation;
  S.currentSide = side;
  S.boundingBoxCache = {};
  S.renderGridCanvas();

  const cells = screenCells(S);
  const inMask = cells.filter(co => co.inside);
  if (inMask.length === 0) return { rotation, side, invertY, empty: true, cells, inMask };
  const xs = inMask.map(co => co.x), ys = inMask.map(co => co.y);
  const origins = cells.filter(co => co.isOrigin);
  return {
    rotation, side, invertY, empty: false, cells, inMask,
    count: inMask.length,
    minX: Math.min(...xs), maxX: Math.max(...xs),
    minY: Math.min(...ys), maxY: Math.max(...ys),
    // Canvas extent of the mask — "where the mask sits", in the units the canvas draws in.
    minC: Math.min(...inMask.map(co => co.c)), maxC: Math.max(...inMask.map(co => co.c)),
    minR: Math.min(...inMask.map(co => co.r)), maxR: Math.max(...inMask.map(co => co.r)),
    origins: origins.map(co => ({ c: co.c, r: co.r, x: co.x, y: co.y, inside: co.inside })),
    // key -> coordinate, for a cell-by-cell diff against another source
    coordByKey: Object.fromEntries(cells.map(co => [co.key, `${co.x},${co.y}`])),
  };
}

// ── Measurement for QA finding ① (reported, not asserted as a fix) ─────────────────────
// A valid-die reference whose projection is DISPLACED relative to this map's dies. The
// user's ruling is that a mismatch must show shifted, not block — but `pushMapData`'s
// contrast gate counts every painted cell the mask calls "not a die" and refuses, because
// `replace_map` would delete those rows. This measures how much of that refusal is caused
// by the origin being anchored on the circle rather than on the mask.
async function measureDisplacedReferenceGate(src, mask) {
  // 1) The map as an operator painted it, in an ALIGNED session: every die carries its own
  //    coordinate as its value, so the rows are exactly what the server would hold.
  const { sandbox: P } = buildEnv(src, {});
  P.validDieResolveSeq = 1;
  P.validDie = { basis: 'ref', keys: mask.keys, reason: '', ref: null, raw: 'TPL' };
  P.boundingBoxCache = {};
  P.renderGridCanvas();
  screenCells(P).filter(co => co.inside).forEach(co => { P.gridData[co.key] = `${co.x},${co.y}`; });
  P.renderGridCanvas();
  const rows = [];
  P.eachSavableCell((co, val) => rows.push({
    data: { x: { value: co.x }, y: { value: co.y }, val: { value: val } } }));

  // 2) Re-open it with a reference that projects 2 columns / 1 row away — the shape a frame
  //    difference produces (`projectCellsToPhys` resolves the reference in ITS OWN frame).
  const displaced = new Set([...mask.keys].map(k => {
    const [px, py] = k.split('_').map(Number);
    return `${px + 2}_${py + 1}`;
  }));
  const gridMeta = {
    grid_cols: COLS, grid_rows: ROWS, grid_start_x: START_X, grid_start_y: START_Y,
    grid_y_invert: false, rotation: 0, side: 'front',
    phys_wafer_dia: DIA, phys_chip_x: CHIP_X, phys_chip_y: CHIP_Y,
    phys_offset_x: 0, phys_offset_y: 0, phys_edge_margin: MARGIN, valid_die_ref: 'TPL',
  };
  const { sandbox: S } = buildEnv(src, { rows, gridMeta, mask: displaced });
  await S.loadExistingMap({ quiet: true });
  const u = S.classifyUnsavableCells();
  const nonEmpty = Object.keys(S.gridData).filter(k => (S.gridData[k] || '') !== '').length;
  return { rows: rows.length, nonEmpty, blocking: S.pushBlockingCount(u),
           offGrid: u.offGrid.length, outside: u.outsideRetained.length };
}

const combos = [];
for (const rotation of ROTATIONS) for (const side of SIDES) for (const invertY of INVERTS) {
  combos.push({ rotation, side, invertY });
}

function scoreAll(src, { verbose = false, reference = null } = {}) {
  failures = []; compared = 0;
  const evidence = [];

  // ── Fixture self-check: every defect axis is live, or nothing below proves anything ──
  const { sandbox: S0 } = buildEnv(src, {});
  const mask = buildMask(S0);
  {
    eq('fixture/chip-is-anisotropic', true, CHIP_X !== CHIP_Y,
       'chipX == chipY makes the rot 90/270 pitch swap invisible');
    eq('fixture/grid-is-not-square', true, COLS !== ROWS);
    eq('fixture/circle-bbox-is-inset', true, mask.circleBox.minC > 0 && mask.circleBox.minR > 0,
       'minC == 0 lets a dropped bbox term hide behind a zero');
    eq('fixture/mask-is-a-strict-subset', true, mask.kept > 0 && mask.kept < mask.circleCount);
    eq('fixture/mask-insets-are-asymmetric', true,
       new Set([INSET.left, INSET.right, INSET.top, INSET.bottom]).size >= 3,
       'equal insets would move the minimum by the same amount at every rotation');
    eq('fixture/origins-are-distinguishable', true, START_X !== START_Y && START_Y < 0);
    evidence.push(`[fixture] grid ${COLS}x${ROWS} chip ${CHIP_X}x${CHIP_Y} dia ${DIA} margin ${MARGIN}`
      + ` -> circle bbox c[${mask.circleBox.minC}..${mask.circleBox.maxC}]`
      + ` r[${mask.circleBox.minR}..${mask.circleBox.maxR}] (${mask.circleCount} cells);`
      + ` mask = circle minus L${INSET.left}/R${INSET.right}/T${INSET.top}/B${INSET.bottom}`
      + ` = ${mask.kept} dies`);
  }

  // ── THE ROUND'S ASSERTION, once per orientation ───────────────────────────────────
  const obs = {};
  const drift = [];
  for (const combo of combos) {
    const tag = `rot${combo.rotation}/${combo.side}/${combo.invertY ? 'invY' : 'y'}`;
    const o = observe(src, mask.keys, combo);
    obs[tag] = o;
    if (o.empty) { failures.push(`${tag}: the screen drew ZERO valid dies`); compared++; continue; }

    // ③ start_x / start_y IS the minimum column / row of the valid-die region.
    //    Read straight off the rendered cells: no transform participates in the expectation.
    eq(`${tag}/mask-min-x-is-start-x`, START_X, o.minX,
       'the leftmost die of the mask must read the declared origin column');
    eq(`${tag}/mask-min-y-is-start-y`, START_Y, o.minY,
       'the lowest-numbered die of the mask must read the declared origin row');
    // The mask must be the SAME set of dies at every orientation — rotation re-places dies on
    // the canvas, it does not create or destroy them. If this moves, the fixture is lying.
    eq(`${tag}/mask-population-is-invariant`, mask.kept, o.count);
    drift.push(`  ${tag.padEnd(22)} mask canvas c[${o.minC}..${o.maxC}] r[${o.minR}..${o.maxR}]`
      + ` reads x[${o.minX}..${o.maxX}] y[${o.minY}..${o.maxY}] · ${o.count} dies`);
  }

  // ④ THE ORIGIN CELL — "the point that reads (0,0) when start_x/y is placed".
  //    With start at (0,0) the mask's minimum must BE zero on both axes, and the cell the
  //    canvas paints as origin must sit on the mask's own minimum column and minimum row.
  //
  // ⚠️ The origin cell is NOT required to be a valid die, and asserting that was wrong: the
  //    mask is a rounded region, so the corner of its bounding box legitimately falls outside
  //    it (exactly as the circle's bbox corner always has). What must hold is that the corner
  //    is the mask's OWN corner — measured here by finding, on the screen, a die that reads
  //    x == 0 in the origin's canvas column and a die that reads y == 0 in its canvas row.
  for (const combo of combos) {
    const tag = `rot${combo.rotation}/${combo.side}/${combo.invertY ? 'invY' : 'y'}`;
    const o = observe(src, mask.keys, { ...combo, startX: 0, startY: 0 });
    if (o.empty) continue;
    eq(`${tag}/origin-cell-is-unique`, 1, o.origins.length);
    const org = o.origins[0] || {};
    eq(`${tag}/origin-cell-reads-0-0`, '0,0', `${org.x},${org.y}`);
    eq(`${tag}/mask-minimum-is-zero-on-both-axes`, [0, 0], [o.minX, o.minY]);
    eq(`${tag}/origin-column-carries-a-die-reading-x0`, true,
       o.inMask.some(co => co.c === org.c && co.x === 0),
       'the origin must stand on the mask\'s own leftmost column, not the circle\'s');
    eq(`${tag}/origin-row-carries-a-die-reading-y0`, true,
       o.inMask.some(co => co.r === org.r && co.y === 0),
       'the origin must stand on the mask\'s own minimum row, not the circle\'s');
  }

  // ── The three places the mask must NOT declare the coordinate system ────────────────
  // Each is a boundary the origin change had to respect; without these the fixture cannot
  // tell "the box follows the mask" from "the box follows the mask everywhere, always".
  {
    const { sandbox: S } = buildEnv(src, {});
    const circleBox = S.getWaferBoundingBox(0, 'front', { circleOnly: true });
    const seeRef = (keys, seq) => {
      S.validDieResolveSeq = seq;
      S.validDie = { basis: 'ref', keys, reason: '', ref: { table: 'dt_map', mapKey: 'TPL' }, raw: 'TPL' };
    };

    // (a) a resolved reference DOES move the box — otherwise (b)(c)(d) below are vacuous
    seeRef(mask.keys, 1);
    S.boundingBoxCache = {};
    const maskBox = S.getWaferBoundingBox(0, 'front');
    eq('boundary/reference-moves-the-box', true,
       JSON.stringify(maskBox) !== JSON.stringify(circleBox),
       'if the mask box equals the circle box the boundary tests below prove nothing');

    // (b) INSIDE A FRAME WINDOW the box is the circle. The window is solving the SOURCE map's
    //     coordinate system; feeding it this map's mask cuts the source with a foreign mask.
    //
    // 🔴 NO CACHE CLEAR HERE, and that is the assertion. `isValidDieAt` already refuses the
    //    mask inside a window, so the RESULT would be the circle either way — what the tag
    //    actually buys is a separate cache SLOT. Without it the window's circle-derived box
    //    lands on the mask's key (identical dims and physical spec, since the window's phys
    //    fields fall back to the DOM), and then either the window serves the mask's box or the
    //    next mask lookup serves the circle's. The 'V' entry is live right now, from `maskBox`.
    const windowBox = S.withPhysFrame(
      { cols: COLS, rows: ROWS, startX: 0, startY: 0, invertY: false, rotation: 0, side: 'front' },
      () => S.getWaferBoundingBox(0, 'front'));
    eq('boundary/frame-window-uses-the-circle', circleBox, windowBox,
       'overlay and valid-die resolution must be byte-identical to before this round');
    eq('boundary/frame-window-does-not-poison-the-mask-slot', maskBox,
       S.getWaferBoundingBox(0, 'front'),
       'a window that shares the mask\'s cache key hands the circle box back to the editor');

    // (c) THE AUTHORING CANVAS does not declare a coordinate system. Its mask is the whole
    //     grid, so adopting it would renumber every cell the moment authoring is entered.
    S.validDie = { basis: 'template', keys: mask.keys, reason: '', ref: null, raw: undefined };
    S.boundingBoxCache = {};
    eq('boundary/template-uses-the-circle', circleBox, S.getWaferBoundingBox(0, 'front'));

    // (d) A MASK WITH NO CELL ON THIS GRID falls back to the circle. An empty accumulator
    //     collapses to {0,0,0,0} and silently translates the entire coordinate system.
    seeRef(new Set(['999_999']), 2);
    S.boundingBoxCache = {};
    eq('boundary/off-grid-mask-falls-back-to-the-circle', circleBox, S.getWaferBoundingBox(0, 'front'),
       '미상은 0이 아니다 — an unplaceable mask must not move the origin');

    // (e) THE CACHE MUST NOT SERVE ONE REFERENCE'S BOX TO ANOTHER. Two masks of IDENTICAL
    //     cardinality and different extent, resolved in sequence, with no cache clear —
    //     which is exactly what 「유효 다이 맵」 재지정 does.
    const mirrored = new Set([...mask.keys].map(k => {
      const [px, py] = k.split('_').map(Number);
      return `${COLS - 1 - px}_${py}`;
    }));
    eq('boundary/mirrored-mask-has-the-same-cardinality', mask.keys.size, mirrored.size);
    const { sandbox: S2 } = buildEnv(src, {});
    S2.validDieResolveSeq = 1;
    S2.validDie = { basis: 'ref', keys: mask.keys, reason: '', ref: null, raw: 'A' };
    const boxA = S2.getWaferBoundingBox(0, 'front');
    S2.validDieResolveSeq = 2;                       // what resolveValidDie does on re-entry
    S2.validDie = { basis: 'ref', keys: mirrored, reason: '', ref: null, raw: 'B' };
    const boxB = S2.getWaferBoundingBox(0, 'front'); // NO cache clear — the tag must separate them
    eq('boundary/re-designation-gets-its-own-box', true,
       JSON.stringify(boxA) !== JSON.stringify(boxB),
       'a size-keyed cache tag serves the previous reference\'s origin to the new one');
    evidence.push(`[boundary] circle ${JSON.stringify(circleBox)} · mask ${JSON.stringify(maskBox)}`
      + ` · frame-window/template/off-grid all fall back to the circle`
      + ` · re-designation A${JSON.stringify(boxA)} -> B${JSON.stringify(boxB)}`);
  }

  // ── The counter-measurement: how many cells does the OLD basis move? ─────────────────
  // 🔴 If this is zero the fixture proved nothing — a defective source and a fixed one would
  //    be indistinguishable. Supplied by the caller as the observation of the defective source.
  if (reference) {
    let anyMoved = 0;
    const rows = [];
    for (const combo of combos) {
      const tag = `rot${combo.rotation}/${combo.side}/${combo.invertY ? 'invY' : 'y'}`;
      const a = obs[tag], b = reference[tag];
      if (!a || !b || a.empty || b.empty) continue;
      const moved = Object.keys(a.coordByKey).filter(k => b.coordByKey[k] !== a.coordByKey[k]);
      anyMoved += moved.length;
      rows.push(`  ${tag.padEnd(22)} circle-anchored numbering put the mask's minimum at `
        + `(${b.minX},${b.minY}); valid-die-anchored puts it at (${a.minX},${a.minY}) `
        + `-> ${moved.length} cells re-numbered`);
    }
    eq('counter/fixture-activates-the-defect', true, anyMoved > 0,
       'a fixture that reads the same under both bases scores nothing');
    evidence.push('[counter-measurement — circle-anchored vs valid-die-anchored]');
    rows.forEach(r => evidence.push(r));
  }

  // ── The load round-trip: origin + DB value, with the mask resolved FIRST ─────────────
  // Uses `loadExistingMap` itself. The rows' values encode their own stored coordinate.
  {
    const combo = { rotation: 90, side: 'back', invertY: true };   // the hardest corner
    const seed = observe(src, mask.keys, combo);
    if (seed.empty) die('round-trip seed produced no dies');
    // 1) paint every die, 2) read the coordinate the screen states, 3) make that the value.
    const rows = seed.inMask.map(co => ({
      data: { x: { value: co.x }, y: { value: co.y }, val: { value: `${co.x},${co.y}` } },
    }));
    const gridMeta = {
      grid_cols: COLS, grid_rows: ROWS, grid_start_x: START_X, grid_start_y: START_Y,
      grid_y_invert: combo.invertY, rotation: combo.rotation, side: combo.side,
      phys_wafer_dia: DIA, phys_chip_x: CHIP_X, phys_chip_y: CHIP_Y,
      phys_offset_x: 0, phys_offset_y: 0, phys_edge_margin: MARGIN,
      valid_die_ref: 'TPL',
    };
    const { sandbox: S, log } = buildEnv(src, { rows, gridMeta, mask: mask.keys });
    const res = S.loadExistingMap({ quiet: true });
    return Promise.resolve(res).then(() => {
      eq('load/rows-parsed', rows.length, Object.keys(S.gridData).length);
      eq('load/no-alert', [], log.alerts);
      // 🔴 THE ORDERING. The user's sequencing, verbatim: valid-die map -> origin -> cells.
      eq('load/valid-die-resolved-once', 1, log.resolveCalls.length);
      eq('load/valid-die-resolved-before-any-cell-was-placed', 0,
         log.resolveCalls.length ? log.resolveCalls[0].cellsPlacedBefore : -1,
         'placing cells under the circle box and then numbering them under the mask box '
         + 'silently moves every stored coordinate');
      const payload = pushPayload(S);
      eq('load/every-die-is-savable', rows.length, Object.keys(payload).length);
      const disagree = Object.keys(payload)
        .filter(k => payload[k].coord !== payload[k].val)
        .map(k => `${k}: row carried (${payload[k].val}) but Push would write (${payload[k].coord})`);
      eq('load/placed-at-origin-plus-db', [], disagree.slice(0, 8));
      eq('load/oracle-population-is-not-empty', true, Object.keys(payload).length > 0);
      evidence.push(`[round-trip] rot90/back/invY · ${rows.length} rows loaded through `
        + `loadExistingMap under wafer_map_metadata; every ⚡ Push coordinate equals the `
        + `coordinate its own row carried; mask resolved with `
        + `${log.resolveCalls[0] ? log.resolveCalls[0].cellsPlacedBefore : '?'} cells placed`);

      // ── Structural guards ────────────────────────────────────────────────────────────
      eq('structural/no-push-side-compensation', true,
         !/cellObj\.x\s*[+-]/.test(src) && !/xParsed\s*[+-]=/.test(src),
         'adjusting coordinates on the way out is the defect this round removes');
      eq('structural/render-does-not-re-derive-the-zero-cell', true,
         !/const c_zero = isXMirrored/.test(src),
         'the (0,0) cell must come from getCanvasCellFromDb, not a hand-written copy');
      eq('structural/notch-still-asks-for-the-circle', true,
         /getWaferBoundingBox\(rotation, side, \{ circleOnly: true \}\)/.test(src),
         'the clipboard frame fingerprint must not follow a mask that a network failure can change');
      // The deleted adoption machinery must stay deleted (94b9baa).
      const gone = ['storedCoordRepositionPlan', 'applyStoredCoordReposition', 'repositionRefusalReason',
                    'adoptionCoordinateCost', 'adoptedFrameOf', 'dbCoordsByPhysKey', 'adoptFrameSpec',
                    'announceFrameAdoption'];
      eq('structural/frame-adoption-stays-deleted', [], gone.filter(n => src.includes(n)));

      if (verbose) {
        console.log('  ── where the mask sits and what it reads ──');
        drift.forEach(d => console.log(d));
        evidence.forEach(e => console.log('  ' + e));
      }
      return { failures: failures.slice(), compared, obs, drift, evidence };
    });
  }
}

// ── Mutations ──────────────────────────────────────────────────────────────────────────
const TAG_LINE = '  const tag = maskDeclaresTheFrame ? `V${validDieResolveSeq}` : \'C\';';
const TAG_WINDOW = `    && !physFrameOverride
    && validDieBasis() === 'ref';`;
const ZERO_CELL = `  const zero = getCanvasCellFromDb(0, 0, cols, rows, currentRotation, currentSide, invertY, startX, startY);
  const hasZeroZero = (zero.c >= 0 && zero.c < visualCols) && (zero.r >= 0 && zero.r < visualRows);`;
const RESOLVE_FIRST = `    await resolveValidDie(loadedGridMeta, selectedTable, loadedMapKey || getCurrentMapKey());
    // 근거가 바뀌면 원점 상자도 바뀐다 — 위 동기화가 비운 캐시는 원 기준으로 다시 채워졌을
    // 수 있다. 태그가 키를 갈라 주지만, 여기서 한 번 더 비워 이전 맵의 항목을 남기지 않는다.
    boundingBoxCache = {};`;

const MUTATIONS = [
  // 🔴 THE SHIPPED DEFECT PUT BACK — the only self-check worth anything.
  ['D0 the shipped defect restored (the box never consults the mask)',
   s => s.replace(TAG_LINE, "  const tag = 'C';")],
  ['D1 the mask box is used but the frame window stops falling back to the circle',
   s => s.replace(TAG_WINDOW, `    && validDieBasis() === 'ref';`)],
  ['D2 the authoring canvas (template) starts declaring the coordinate system',
   s => s.replace(TAG_WINDOW,
                  `    && !physFrameOverride
    && validDieBasis() !== 'circle' && validDieBasis() !== 'refused';`)],
  ['D3 the cache tag stops distinguishing generations (same-size refs collide)',
   s => s.replace(TAG_LINE, "  const tag = maskDeclaresTheFrame ? 'V' : 'C';")],
  ['D4 only the column axis follows the mask (rows stay on the circle)',
   s => s.replace(`    ? { minC: mMinC, maxC: mMaxC, minR: mMinR, maxR: mMaxR }`,
                  `    ? { minC: mMinC, maxC: mMaxC, minR, maxR }`)],
  ['D5 the two axes are swapped in the mask box',
   s => s.replace(`    ? { minC: mMinC, maxC: mMaxC, minR: mMinR, maxR: mMaxR }`,
                  `    ? { minC: mMinR, maxC: mMaxR, minR: mMinC, maxR: mMaxC }`)],
  ['D6 the mask accumulator uses the circle predicate (mask box == circle box)',
   s => s.replace(`        if (isValidDieAt(p.x, p.y, circleInside)) {`,
                  `        if (circleInside) {`)],
  ['D7 the empty-mask fallback is removed (an off-grid mask collapses the origin to 0)',
   s => s.replace(`  const src = (useMask && maskCount > 0)`, `  const src = (useMask)`)],
  // The ordering the user stated in words.
  ['D8 the mask is resolved AFTER the cells are placed (the old call site)',
   s => s.replace(RESOLVE_FIRST, '')
         .replace(`    // [M4②] 홈 키를 함께 넘기는 이유(자기 참조 A→A 차단)와 \`setLoadedIdentity\`보다 앞선다는
    // 사실도 그 블록에 적혀 있다.
    renderGridCanvas();`,
                  `    await resolveValidDie(loadedGridMeta, selectedTable, loadedMapKey || getCurrentMapKey());
    renderGridCanvas();`)],
  // The duplicate derivation this round removed.
  ['D9 renderGridCanvas re-derives the (0,0) cell by hand again (the mirror-term copy)',
   s => s.replace(ZERO_CELL,
                  `  const box = getWaferBoundingBox(currentRotation, currentSide);
  const isXMirrored = (currentSide === 'back' && !isRotated90or270);
  const isYMirrored = (currentSide === 'back' && isRotated90or270);
  const c_zero = isXMirrored ? (box.maxC + startX) : (box.minC - startX);
  let r_zero = 0;
  if (!invertY) { r_zero = !isYMirrored ? (box.minR - startY) : (box.maxR + startY); }
  else { r_zero = !isYMirrored ? (box.maxR + startY) : (box.minR - startY); }
  const zero = { c: c_zero, r: r_zero };
  const hasZeroZero = (zero.c >= 0 && zero.c < visualCols) && (zero.r >= 0 && zero.r < visualRows);`)],
];

// ── Run ────────────────────────────────────────────────────────────────────────────────
const verbose = process.argv.includes('-v') || process.argv.includes('--verbose');
const doMutate = process.argv.includes('--mutate');

(async () => {
  // The defective source, observed first, so the counter-measurement has a reference.
  const defectiveSrc = SRC0.replace(TAG_LINE, "  const tag = 'C';");
  if (defectiveSrc === SRC0) die('the D0 mutation did not apply — the anchor text moved. Nothing compared.');
  const { sandbox: SD } = buildEnv(defectiveSrc, {});
  const maskD = buildMask(SD);
  const reference = {};
  for (const combo of combos) {
    reference[`rot${combo.rotation}/${combo.side}/${combo.invertY ? 'invY' : 'y'}`] =
      observe(defectiveSrc, maskD.keys, combo);
  }

  const base = await scoreAll(SRC0, { verbose: true, reference });

  // QA finding ① — reported, not claimed as fixed. The gate is `pushMapData`'s, not this
  // round's; what this round changes is how many cells reach it.
  const gateOld = await measureDisplacedReferenceGate(defectiveSrc, maskD);
  const { sandbox: SN } = buildEnv(SRC0, {});
  const gateNew = await measureDisplacedReferenceGate(SRC0, buildMask(SN));
  console.log('\n  ── QA finding ① · displaced valid-die reference vs the Push contrast gate ──');
  console.log(`  circle-anchored origin: ${gateOld.blocking} of ${gateOld.nonEmpty} painted cells `
    + `blocked (${gateOld.offGrid} off-grid, ${gateOld.outside} outside the mask)`);
  console.log(`  mask-anchored origin:   ${gateNew.blocking} of ${gateNew.nonEmpty} painted cells `
    + `blocked (${gateNew.offGrid} off-grid, ${gateNew.outside} outside the mask)`);

  console.log(`\nBASELINE: ${base.failures.length} failure(s) over ${base.compared} comparisons`);
  // H1 protocol: the runner reads this line to tell "red with N assertions" from a crash.
  console.log(`ASSERTIONS ${base.compared} ${base.failures.length}`);
  base.failures.forEach(f => console.log('  ✗ ' + f));
  if (base.failures.length > 0) process.exit(1);
  console.log('  ✓ shipped source is coherent');

  if (!doMutate) { console.log('\n(run with --mutate to score the fixture against injected defects)'); return; }

  console.log('\nMUTATIONS — each must be CAUGHT (a mutation that survives is a hole in the fixture):');
  let survivors = 0;
  for (const [name, mutate] of MUTATIONS) {
    const mutated = mutate(SRC0);
    if (mutated === SRC0) { console.log(`  ⚠ ${name} — DID NOT APPLY (anchor text moved)`); survivors++; continue; }
    let r;
    try { r = await scoreAll(mutated, { reference }); }
    catch (e) { console.log(`  ✓ ${name} — threw (${e && e.message})`); continue; }
    if (r.failures.length === 0) { console.log(`  ✗ ${name} — SURVIVED`); survivors++; }
    else console.log(`  ✓ ${name} — caught by ${r.failures.length}: ${r.failures[0].slice(0, 110)}`);
  }
  console.log(survivors === 0
    ? '\nAll mutations caught.'
    : `\n${survivors} mutation(s) survived — the fixture does not cover them.`);
  if (survivors > 0) process.exit(1);
})().catch(e => die(e && e.stack ? e.stack : String(e)));
