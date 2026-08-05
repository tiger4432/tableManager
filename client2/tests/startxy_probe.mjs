/**
 * START_X/START_Y REGRESSION PROBE -- guards fix aee05b1 and its neighbors: on map load the
 * DECLARED grid_start_x/y must be preserved, never forced to the loaded cells' bounding box,
 * and a FAILED spec read must not be treated as a missing declaration.
 *
 * Executes the real `loadExistingMap` (plus its coordinate/geometry callees) sliced out of
 * map_editor.js, against a fixture whose painted cells deliberately do NOT span the declared
 * region: declared frame 21x21 starting (1,-6), painted bbox min (5,-1), dx=4 dy=5 so an
 * axis swap cannot pass by coincidence.
 *
 * The oracle, per case (all values measured on the shipped source at landing time):
 *   A  stored metadata declares start      -> the declaration wins, verbatim
 *   B  no metadata, user picks "standard"  -> the frame is DERIVED from the data (bbox) --
 *                                             that is the design, not the defect
 *   C  no metadata, user keeps the panel   -> the panel wins, verbatim
 *   D  counterfactual: forcing start to the bbox moves 41 of 46 cells to a DIFFERENT
 *      physical die and would persist a different grid_start -- proof the axis is live
 *   E  metadata EXISTS but this read failed (HTTP 500) -> the load REFUSES (0 cells, a
 *      toast) instead of degrading to "no declaration" (the pre-aee05b1 defect adopted the
 *      bbox and silently rewrote the frame)
 *   F  metadata row EXISTS but its START is unreadable -> the load does NOT refuse: it routes
 *      to the SAME coordinate-choice modal a map with no spec row reaches, and the operator's
 *      pick decides the frame (F1 standard / F2 current / F3 cancel).
 *   G  the same, spelled `grid_start_x: null` -- the `Number(null) === 0` trap. This is the
 *      DANGEROUS spelling: it produces no NaN, so the screen looks correct while every cell
 *      sits on a different die (measured pre-guard: 44 of 44 moved, 0 toasts, and Push
 *      persisted `grid_start_x: 0`). The key-absent spelling at least collapsed loudly.
 *
 * WHY F IS A MODAL AND E IS A REFUSAL -- the two look alike and are not. E does not know what
 * the declaration says, so a chosen frame would OVERWRITE a real one on Push. F has read the
 * declaration and knows it has no origin; there is nothing to overwrite that was ever there.
 *
 * THE LOAD-SIDE HALF OF PUSH HONESTY. `readGridFrameControls` used to read the START boxes with
 * `parseInt(v, 10) || 0`, and that `|| 0` is the exact expression that persisted the original
 * defect's 0. F/G therefore assert that after the modal the boxes hold a READABLE INTEGER --
 * never '', never 'undefined', never 'null' -- because that property is what made the fold at
 * push time a no-op instead of a fabrication, and it is asserted on the load path rather than
 * assumed from it.
 *   H  the box was ALREADY empty when the operator answered ⚙️ 현재 패널. F/G cannot reach this:
 *      they pass a panel that states a start, so the fold has nothing to invent. Measured on
 *      the shipped source, this case wrote the fabricated 0 BACK INTO THE BOX and loaded 46
 *      cells under it. The reader now answers `null` for a box that said nothing and all three
 *      of its consumers refuse (2026-08-05); F/G's "readable integer" assertions and this one
 *      are the two halves of the same claim.
 *   A2/A3/B/C  [D4] where the frame CAME FROM, recorded on the START boxes' dataset and
 *      carried into `wafer_map_metadata` as `frame_chosen_from`. Before it, B's and C's rows
 *      were byte-identical to A's -- a frame nobody declared, indistinguishable forever from
 *      one somebody did.
 *
 * Usage: node startxy_probe.mjs [path-to-map_editor.js]   (default: the live src, so the
 * discovery runner can execute it bare; the argument remains for probing other commits.)
 * Exit: 0 green | 1 an assertion failed | 2 probe failure (nothing was measured).
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC_PATH = process.argv[2] || path.join(HERE, '..', 'src', 'map_editor.js');
const SRC = readFileSync(SRC_PATH, 'utf8').replace(/\r\n/g, '\n');

const die = (m) => { console.error(`PROBE FAILURE: ${m}\n(Nothing was measured.)`); process.exit(2); };

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

// Superset across commits. Each entry is the list of ACCEPTED SPELLINGS -- 35e84c3 renamed
// four coordinate functions, and a probe that slices two revisions cannot use one spelling.
const WANTED = [
  ['physNum'], ['gridDimNum'], ['getScreenShift'], ['getTransformedPhysicalConfig'],
  ['getDieIndex', 'getPhysicalCoords'],
  ['getCanvasCellFromDb', 'getCellFromVisualCoords'],
  ['getCanvasCellFromDieIndex', 'getCellFromPhysicalCoords'],
  ['getDbCoords', 'getVisualCoords'],
  // Absent before the isotropic-cell round; the per-entry `missing` tolerance covers the
  // older revisions this probe also slices.
  // [D1] `physDeclaration` now asks whether the geometry on screen was AUTO-REGISTERED
  // (synthesized, never measured) before reporting a chip pitch as declared. Same
  // per-entry `missing` tolerance: older revisions this probe slices do not have it.
  ['geometryIsAutoRegistered'], ['markGeometryAutoRegistered'],
  // [2b] `physDeclaration` no longer spells "did this control say anything" inline: that
  // question is now shared with the grid-frame reader, so it is one function and it is here.
  ['controlIsSilent'],
  ['physDeclaration'], ['cellMetrics'],
  ['isCellInsideWaferFast'], ['getWaferBoundingBox'],
  ['frameDimBounds'], ['applyPhysicalGeometry'], ['applyPresetObject'],
  ['seatingSnapshot'], ['reseatCellsToStoredCoords'],
  ['validDieBasis'], ['isValidDieAt'],
  ['renderGridCanvas'], ['cellFillColor'], ['isProtectedFCell'],
  ['eachSavableCell'], ['classifyUnsavableCells'], ['serverCellKeySet'],
  ['loadExistingMap'],
  // The seven named steps `loadExistingMap` is written in terms of as of the R4
  // decomposition. Absent at older commits — which is exactly what the per-entry `missing`
  // tolerance above is for, since a pre-R4 `loadExistingMap` is self-contained and runs
  // without them. Each takes what it needs as an argument and returns a value (no module
  // state), so nothing new has to be declared in the sandbox.
  ['collectMapKeyFilterModel'], ['scanCoordinateBounds'], ['resolveDeclaredGridMeta'],
  // [2b/D4] `resolveGridFrame`'s `current` branch no longer re-spells the control read: it calls
  // the SAME `readGridFrameControls` the two writers call, over the SAME blank-box predicate
  // (`gridFrameControlNum`), and it records which choice produced the frame (`markFrameChosen`).
  // Absent from older revisions this probe also slices — the per-entry `missing` tolerance covers
  // that; present from this round on, where omitting one is a ReferenceError into the catch.
  ['gridFrameControlNum'], ['readGridFrameControls'], ['markFrameChosen'], ['frameChosenFrom'],
  ['promptCoordinateChoice'], ['resolveGridFrame'], ['deriveLegendFromCellValues'],
  ['restoreDoeDraftWithPrecedence'],
  // The pure predicate the load consults before letting anything replace the valid-die
  // designation (user ruling 2026-08-04). Absent from older revisions this probe also slices,
  // which the per-entry `missing` tolerance above already covers; present from the carry fix
  // onward, where omitting it is a ReferenceError inside `loadExistingMap`'s own catch.
  ['parseValidDieRef'],
];

// `dataset` is REAL here, not a stub, because two provenance markers live in it and a fixture
// without it turns both writers into silent no-ops — `markGeometryAutoRegistered` and
// `markFrameChosen` both bail on `!input.dataset`. A harness whose fixture disables the thing
// it scores reads green while proving nothing.
function makeInput(v) {
  return { value: String(v), checked: false, textContent: '', disabled: false,
           dataset: {}, querySelector: () => null, appendChild() {} };
}

/** [D4] What the START boxes say about where this frame came from. `undefined` = the map's own
 *  declaration (no choice happened). Read off BOTH axes, because the product writes both and a
 *  one-axis read would let the other axis's write rot unnoticed. */
const chosenMark = (el) => {
  const x = el.gridStartX.dataset.frameChosen;
  const y = el.gridStartY.dataset.frameChosen;
  return x === y ? x : `SPLIT(${x}/${y})`;
};

function buildEnv(src, opts = {}) {
  const pieces = [];
  const missing = [];
  for (const spellings of WANTED) {
    let code = null, used = null;
    for (const name of spellings) { code = sliceFunction(src, name); if (code) { used = name; break; } }
    if (!code) { missing.push(spellings[0]); continue; }
    try { new vm.Script(code); } catch (e) { die(`slice of '${used}' does not parse: ${e && e.message}`); }
    pieces.push(code);
  }
  if (!pieces.some(p => /function\s+loadExistingMap/.test(p))) die('loadExistingMap not found');
  // `parseValidDieRef` pins its lookup table to this module const, so its slice is not
  // self-contained without it. Read from the source rather than retyped, and TOLERATED when
  // absent — this probe also slices revisions from before the const existed, the same
  // tolerance the `missing` list above provides for the functions.
  const vdTable = /^const VALID_DIE_TABLE = .*;$/m.exec(src);
  if (vdTable) pieces.unshift(vdTable[0]);

  const log = { toasts: [], alerts: [], requests: [] };
  const choice = opts.choice || 'standard';
  const panel = opts.panel || { cols: 10, rows: 10, startX: 0, startY: 0, invertY: false,
                                dia: 300, chipX: 11, chipY: 13, offX: 0, offY: 0, margin: 3 };
  const choiceBtn = (which) => {
    const b = makeInput('');
    b.addEventListener = (type, fn) => { if (type === 'click' && which === choice) setTimeout(fn, 0); };
    b.removeEventListener = () => {};
    return b;
  };
  const el = {
    gridCols: makeInput(panel.cols), gridRows: makeInput(panel.rows),
    gridStartX: makeInput(panel.startX), gridStartY: makeInput(panel.startY),
    gridYInvert: { checked: panel.invertY },
    physWaferDia: { value: String(panel.dia), querySelector: () => null, appendChild() {} },
    physChipX: makeInput(panel.chipX), physChipY: makeInput(panel.chipY),
    physOffsetX: makeInput(panel.offX), physOffsetY: makeInput(panel.offY),
    physEdgeMargin: makeInput(panel.margin),
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
  };
  const sandbox = {
    console: { warn() {}, info() {}, error() {}, log() {}, debug() {} },
    el,
    document: {
      querySelectorAll: (sel) => (sel === '[id^="meta-input-"]'
        ? [{ id: 'meta-input-map_id', value: 'M1' }] : []),
      addEventListener() {}, removeEventListener() {},
    },
    setTimeout,
    alert: (m) => log.alerts.push(String(m)),
    boundingBoxCache: {},
    cellsSeatedUnder: null,
    currentRotation: 0, currentSide: 'front',
    gridData: {}, gridCells2D: {},
    legend: [], activeBrush: '', legendDirty: false,
    legendReplaceScope: null, legendConflict: null,
    legendSaveState: { status: 'idle', at: '', error: '' }, draftBase: null,
    validDie: { basis: 'circle', keys: null, reason: '', ref: null, raw: undefined },
    validDieResolveSeq: 0,
    loadedFCells: new Set(), serverCellKeys: null, overlayLayers: [],
    loadedIdentity: null, selectedTable: 'dt_map',
    tableSchema: { column_types: { x: 'number', y: 'number', val: 'string' } },
    API_BASE: '', OVERLAY_CELL_LIMIT: 2000,
    LEGEND_PALETTE: ['#e11', '#1a1', '#11e', '#ee1', '#1ee', '#e1e'],
    paintLockValues: null, currentHoverCell: null, lastSelectionBox: null,
    isBoxDragging: false, dragType: null, isOriginMode: false,
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
    applyDraftCells: () => 0, readDoeDraft: () => null,
    readRegistryScope: async () => ({ ok: true, rows: [] }),
    registryFingerprint: () => 'fp', cellsDigest: () => 'cd',
    activeOverlayLayers: () => [],
    declaredLegendRow: () => null,
    normalizeLegendItem: (o) => o,
    isLockedValue: () => false,
    getMapIdFromMeta: () => 'M1',
    getCurrentMapKey: () => 'M1',
    applyRoutedPreset: async () => null,
    fetchGridMetaFor: async () => {
      if (opts.metaThrows) throw new Error('맵 규격 조회 실패 (HTTP 500)');
      return opts.gridMeta || null;
    },
    resolveValidDie: async () => sandbox.validDie,
    fetch: async (url) => {
      log.requests.push(String(url).split('?')[0]);
      const rows = opts.rows || [];
      return { ok: true, status: 200,
               json: async () => ({ data: rows, total: opts.total === undefined ? rows.length : opts.total }) };
    },
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  try { vm.runInContext(pieces.join('\n'), sandbox); }
  catch (e) { die(`extracted sources did not evaluate: ${e && e.message}`); }
  return { sandbox, el, log, missing };
}

const pushPayload = (S) => {
  const out = {};
  if (typeof S.eachSavableCell !== 'function') return out;   // absent at old commits
  S.eachSavableCell((co, val) => { out[co.key] = { coord: `${co.x},${co.y}`, val }; });
  return out;
};
const disagreements = (p) => Object.keys(p).filter(k => p[k].coord !== p[k].val);

// -- Fixture: painted cells do NOT span the declared region --------------------------------
//  declared frame : 21 x 21, start (1, -6)          <- the operator's declaration
//  painted cells  : x 5..12, y -1..5                <- bbox min (5, -1), != declared start
//  dx = 4, dy = 5  -> different per axis, so an axis swap cannot pass by coincidence
const DECL = { cols: 21, rows: 21, sx: 1, sy: -6 };
const DATA = { x0: 5, x1: 12, y0: -1, y1: 5 };

function fixtureRows() {
  const rows = [];
  for (let y = DATA.y0; y <= DATA.y1; y++) {
    for (let x = DATA.x0; x <= DATA.x1; x++) {
      if ((x * 3 + y * 7) % 5 === 0) continue;     // asymmetric on purpose
      rows.push({ data: { x: { value: x }, y: { value: y }, val: { value: `${x},${y}` } } });
    }
  }
  [[DATA.x0, DATA.y0], [DATA.x1, DATA.y0], [DATA.x0, DATA.y1], [DATA.x1, DATA.y1]].forEach(([x, y]) => {
    if (!rows.some(r => r.data.x.value === x && r.data.y.value === y)) {
      rows.push({ data: { x: { value: x }, y: { value: y }, val: { value: `${x},${y}` } } });
    }
  });
  return rows;
}

const META = {
  grid_cols: DECL.cols, grid_rows: DECL.rows,
  grid_start_x: DECL.sx, grid_start_y: DECL.sy,
  grid_y_invert: false, rotation: 0, side: 'front',
  // mask-neutral vocabulary so every cell is savable and the oracle population is full
  phys_wafer_dia: 300, phys_chip_x: 1, phys_chip_y: 1,
  phys_offset_x: 0, phys_offset_y: 0, phys_edge_margin: 3,
};

let pass = 0; const failures = [];
const eq = (name, actual, expected) => {
  const a = JSON.stringify(actual), e = JSON.stringify(expected);
  if (a === e) { pass++; console.log(`  ok   ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name}\n       expected ${e}\n       actual   ${a}`); }
};

async function run() {
  const rows = fixtureRows();
  const N = rows.length;

  // CASE A: stored wafer_map_metadata declares start (1,-6); painted bbox is (5,-1)
  {
    const { sandbox: S, el, missing } = buildEnv(SRC, { rows, gridMeta: META });
    if (missing.length) console.log(`  (symbols absent at this commit: ${missing.join(', ')})`);
    const res = await S.loadExistingMap({ quiet: true });
    const p = pushPayload(S);
    console.log(`A meta-declared   start_after_load=(${el.gridStartX.value},${el.gridStartY.value})`
      + ` declared=(${DECL.sx},${DECL.sy}) data_bbox_min=(${DATA.x0},${DATA.y0})`
      + ` grid=${el.gridCols.value}x${el.gridRows.value} cells=${res && res.count}`);
    eq('A declared start_x wins over the data bbox', String(el.gridStartX.value), String(DECL.sx));
    eq('A declared start_y wins over the data bbox', String(el.gridStartY.value), String(DECL.sy));
    eq('A declared cols preserved', String(el.gridCols.value), String(DECL.cols));
    eq('A declared rows preserved', String(el.gridRows.value), String(DECL.rows));
    eq('A every fixture cell loaded', res && res.count, N);
    eq('A every loaded cell is savable', Object.keys(p).length, N);
    eq('A push round-trips every stored coordinate', disagreements(p).length, 0);
    // [D4] Nobody was asked anything: this map declares its own frame, so no choice happened
    // and the row must stay indistinguishable from... itself. This is the assertion that makes
    // the two below MEAN something — without it, marking every frame would also pass.
    eq('A a declared frame carries NO choice marker', chosenMark(el), undefined);
  }

  // CASE A2: the marker is BIDIRECTIONAL. A stale 'panel' left on the panel from a previous map
  // must be cleared by loading a map that declares its own frame — otherwise the previous map's
  // choice is attributed to this one's declaration, which is the same defect pointed backwards.
  // (`markGeometryAutoRegistered` learned this the same way; see map_editor.js:5636.)
  {
    const { sandbox: S, el } = buildEnv(SRC, { rows, gridMeta: META });
    el.gridStartX.dataset.frameChosen = 'panel';
    el.gridStartY.dataset.frameChosen = 'panel';
    await S.loadExistingMap({ quiet: true });
    eq('A2 a stale choice marker is CLEARED by a declared frame', chosenMark(el), undefined);
  }

  // CASE A3: ...and a marker the ROW carries is carried back onto the screen, so that a second
  // push does not quietly promote a chosen frame to a declared one on its way through.
  {
    const { sandbox: S, el } = buildEnv(SRC,
      { rows, gridMeta: { ...META, frame_chosen_from: 'panel' } });
    await S.loadExistingMap({ quiet: true });
    eq('A3 a stored choice marker survives the round trip', chosenMark(el), 'panel');
  }

  // CASE B: no metadata, panel says (1,-6), user picks "standard" -- the standard frame is
  // DERIVED from the data, so the bbox here is the design, not the defect.
  {
    const panel = { cols: DECL.cols, rows: DECL.rows, startX: DECL.sx, startY: DECL.sy,
                    invertY: false, dia: 300, chipX: 1, chipY: 1, offX: 0, offY: 0, margin: 3 };
    const { sandbox: S, el } = buildEnv(SRC, { rows, choice: 'standard', panel });
    const res = await S.loadExistingMap({ quiet: true });
    const p = pushPayload(S);
    console.log(`B no-meta/standard start_after_load=(${el.gridStartX.value},${el.gridStartY.value})`
      + ` grid=${el.gridCols.value}x${el.gridRows.value} cells=${res && res.count}`);
    eq('B standard frame derives start_x from the data', String(el.gridStartX.value), String(DATA.x0));
    eq('B standard frame derives start_y from the data', String(el.gridStartY.value), String(DATA.y0));
    eq('B standard frame derives cols from the data span', String(el.gridCols.value), String(DATA.x1 - DATA.x0 + 1));
    eq('B standard frame derives rows from the data span', String(el.gridRows.value), String(DATA.y1 - DATA.y0 + 1));
    eq('B every fixture cell loaded', res && res.count, N);
    eq('B push round-trips every stored coordinate', disagreements(p).length, 0);
    // [D4] These numbers came out of the DATA, under a question somebody answered. The phys
    // marker alone cannot say that — it says "the registrar wrote this", and the registrar was
    // never here.
    eq('B a bbox-derived frame is marked as chosen from the data', chosenMark(el), 'data');
  }

  // CASE C: no metadata, panel says (1,-6), user keeps the current panel
  {
    const panel = { cols: DECL.cols, rows: DECL.rows, startX: DECL.sx, startY: DECL.sy,
                    invertY: false, dia: 300, chipX: 1, chipY: 1, offX: 0, offY: 0, margin: 3 };
    const { sandbox: S, el } = buildEnv(SRC, { rows, choice: 'current', panel });
    const res = await S.loadExistingMap({ quiet: true });
    const p = pushPayload(S);
    console.log(`C no-meta/current  start_after_load=(${el.gridStartX.value},${el.gridStartY.value})`
      + ` cells=${res && res.count}`);
    eq('C panel start_x preserved', String(el.gridStartX.value), String(DECL.sx));
    eq('C panel start_y preserved', String(el.gridStartY.value), String(DECL.sy));
    eq('C every fixture cell loaded', res && res.count, N);
    eq('C push round-trips every stored coordinate', disagreements(p).length, 0);
    // 🔴 [D4] THE ROW THIS ROUND IS ABOUT. Measured before the fix: this payload was
    //    BYTE-IDENTICAL to case A's — a frame nobody declared, permanently indistinguishable
    //    from one somebody did, and it accumulates.
    eq('C a panel frame is marked as chosen from the panel', chosenMark(el), 'panel');
  }

  // CASE D: counterfactual sensitivity, measured on the axis that actually moves. The
  // stored-coordinate round trip is BLIND to `start`; what a forced start really moves is
  // (i) which physical die each cell sits on and (ii) the number Push persists.
  {
    const seats = async (meta) => {
      const { sandbox: S, el } = buildEnv(SRC, { rows, gridMeta: meta });
      await S.loadExistingMap({ quiet: true });
      return { keys: new Set(Object.keys(S.gridData)),
               persisted: `${el.gridStartX.value},${el.gridStartY.value}` };
    };
    const declared = await seats(META);
    const forced = await seats({ ...META, grid_start_x: DATA.x0, grid_start_y: DATA.y0 });
    let same = 0;
    declared.keys.forEach(k => { if (forced.keys.has(k)) same++; });
    const moved = declared.keys.size - same;
    console.log(`D counterfactual   declared (${DECL.sx},${DECL.sy}) vs forced-to-bbox`
      + ` (${DATA.x0},${DATA.y0}): ${moved} of ${declared.keys.size} cells move; persisted`
      + ` (${declared.persisted}) vs (${forced.persisted})`);
    eq('D oracle population is the full fixture', declared.keys.size, N);
    eq('D forcing start to the bbox moves cells to DIFFERENT physical dies', moved, 41);
    eq('D declared load persists the declared start', declared.persisted, `${DECL.sx},${DECL.sy}`);
    eq('D forced load persists the forced start (the counterfactual is live)',
      forced.persisted, `${DATA.x0},${DATA.y0}`);
  }

  // CASE E: the declaration EXISTS on the server, but this one read failed (HTTP 500).
  // aee05b1: a failed spec read is NOT a missing declaration -- the load must refuse, not
  // degrade to the bbox and offer to overwrite the frame.
  {
    const panel = { cols: DECL.cols, rows: DECL.rows, startX: DECL.sx, startY: DECL.sy,
                    invertY: false, dia: 300, chipX: 1, chipY: 1, offX: 0, offY: 0, margin: 3 };
    const { sandbox: S, el, log } = buildEnv(SRC, { rows, gridMeta: META, metaThrows: true,
                                                    choice: 'standard', panel });
    const res = await S.loadExistingMap({ quiet: true });
    console.log(`E meta-read-500    start_after_load=(${el.gridStartX.value},${el.gridStartY.value})`
      + ` grid=${el.gridCols.value}x${el.gridRows.value} cells=${res && res.count}`
      + ` toasts=${log.toasts.length}`);
    eq('E start_x untouched by the failed read', String(el.gridStartX.value), String(DECL.sx));
    eq('E start_y untouched by the failed read', String(el.gridStartY.value), String(DECL.sy));
    eq('E cols untouched by the failed read', String(el.gridCols.value), String(DECL.cols));
    eq('E rows untouched by the failed read', String(el.gridRows.value), String(DECL.rows));
    eq('E load REFUSED (0 cells), not degraded to "no declaration"', (res && res.count) || 0, 0);
    eq('E the refusal is told (>= 1 toast)', log.toasts.length >= 1, true);
  }

  // CASES F/G: the metadata row EXISTS but its START is unreadable (hand-written row, older
  // schema, or the deprecated cell-level `grid_metadata` blob this loader still falls back
  // to). Lead ruling 2026-08-05: that map goes to the SAME modal as a map with no spec row.
  //
  // The panel deliberately carries dims and a start that match NEITHER the metadata row
  // (21x21 @ 1,-6) NOR the data bbox (8x7 @ 5,-1). Without that the "current" case cannot
  // tell "the panel won" from "the dropped metadata won" -- a fixture that leaves those
  // equal proves nothing about which one was read.
  const UNREADABLE = (() => {
    const { grid_start_x, grid_start_y, ...noStart } = META;
    return {
      F: { label: 'F key-absent', meta: noStart },
      G: { label: 'G start=null', meta: { ...META, grid_start_x: null, grid_start_y: null } },
    };
  })();
  const PANEL_F = { cols: 17, rows: 19, startX: 2, startY: -4, invertY: false,
                    dia: 300, chipX: 1, chipY: 1, offX: 0, offY: 0, margin: 3 };
  const nanKeys = (S) => Object.keys(S.gridData).filter(k => /NaN/.test(k)).length;
  // The `|| 0` in `readGridFrameControls` turns anything unreadable into a persisted 0.
  // A box holding a readable integer is what stops it; assert the box, not the intent.
  const readableInt = (v) => /^-?\d+$/.test(String(v));

  for (const k of ['F', 'G']) {
    const { label, meta } = UNREADABLE[k];

    // F1/G1 -- the operator picks 📐 표준: the frame is derived from the data, and the
    // map OPENS. Before the fix this returned a refusal and loaded 0 cells.
    {
      const { sandbox: S, el, log } = buildEnv(SRC, { rows, gridMeta: meta,
                                                      choice: 'standard', panel: PANEL_F });
      const res = await S.loadExistingMap({ quiet: true });
      const p = pushPayload(S);
      console.log(`${label}/standard  start_after_load=(${el.gridStartX.value},${el.gridStartY.value})`
        + ` grid=${el.gridCols.value}x${el.gridRows.value} cells=${res && res.count}`
        + ` gridData=${Object.keys(S.gridData).length} nan=${nanKeys(S)} toasts=${log.toasts.length}`);
      eq(`${k}1 the map OPENS instead of refusing`, res && res.count, N);
      eq(`${k}1 standard frame derives start_x from the data`, String(el.gridStartX.value), String(DATA.x0));
      eq(`${k}1 standard frame derives start_y from the data`, String(el.gridStartY.value), String(DATA.y0));
      eq(`${k}1 standard frame derives cols from the data span`, String(el.gridCols.value), String(DATA.x1 - DATA.x0 + 1));
      // ⚠️ ONE assertion, not two. `nanKeys === 0` alone passes VACUOUSLY on the refusing
      //    build (0 cells means 0 NaN keys), so it would have proved nothing. Joined to the
      //    square count it discriminates in both directions: the refusing build reads 0/0,
      //    and a fix that opens the map while collapsing cells reads 1/1.
      eq(`${k}1 all cells landed on N distinct NON-NaN squares`,
        `${Object.keys(S.gridData).length} squares / ${nanKeys(S)} NaN`, `${N} squares / 0 NaN`);
      // Same reason the START box check carries its VALUE: `readableInt` alone is true on the
      // refusing build too, because that build never touches the box.
      eq(`${k}1 START X,Y readable by Push's parseInt`,
        `${el.gridStartX.value},${el.gridStartY.value} `
        + `${readableInt(el.gridStartX.value) && readableInt(el.gridStartY.value) ? 'readable' : 'UNREADABLE'}`,
        `${DATA.x0},${DATA.y0} readable`);
      eq(`${k}1 push round-trips every stored coordinate`, disagreements(p).length, 0);
      // Does NOT discriminate pre/post fix on its own — the refusal toasts too. It is here so
      // that a future silent modal is caught: being asked without being told why is worse
      // than the refusal was.
      eq(`${k}1 the operator is told WHY they are being asked (>= 1 toast)`, log.toasts.length >= 1, true);
    }

    // F2/G2 -- the operator keeps the panel. The panel wins VERBATIM, and none of the
    // dropped row's own dims leak in: half a declaration under a chosen origin is a frame
    // nobody declared and nobody chose.
    {
      const { sandbox: S, el } = buildEnv(SRC, { rows, gridMeta: meta,
                                                 choice: 'current', panel: PANEL_F });
      const res = await S.loadExistingMap({ quiet: true });
      console.log(`${label}/current   start_after_load=(${el.gridStartX.value},${el.gridStartY.value})`
        + ` grid=${el.gridCols.value}x${el.gridRows.value} cells=${res && res.count}`
        + ` nan=${nanKeys(S)}`);
      eq(`${k}2 the map OPENS instead of refusing`, res && res.count, N);
      eq(`${k}2 panel start_x wins verbatim`, String(el.gridStartX.value), String(PANEL_F.startX));
      eq(`${k}2 panel start_y wins verbatim`, String(el.gridStartY.value), String(PANEL_F.startY));
      eq(`${k}2 panel cols win — the dropped row's grid_cols does NOT leak in`,
        String(el.gridCols.value), String(PANEL_F.cols));
      eq(`${k}2 panel rows win — the dropped row's grid_rows does NOT leak in`,
        String(el.gridRows.value), String(PANEL_F.rows));
      eq(`${k}2 all cells landed on N distinct NON-NaN squares`,
        `${Object.keys(S.gridData).length} squares / ${nanKeys(S)} NaN`, `${N} squares / 0 NaN`);
      // ⚠️ The four "panel wins" assertions above and this one do NOT discriminate pre/post
      //    fix: the refusing build also leaves the panel untouched. `${k}2 the map OPENS` is
      //    this block's discriminator; these pin that opening it did not move the panel.
      eq(`${k}2 START X,Y readable by Push's parseInt`,
        `${el.gridStartX.value},${el.gridStartY.value} `
        + `${readableInt(el.gridStartX.value) && readableInt(el.gridStartY.value) ? 'readable' : 'UNREADABLE'}`,
        `${PANEL_F.startX},${PANEL_F.startY} readable`);
    }

    // F3/G3 -- Escape/취소. Proves the MODAL is what was reached: a refusal returns
    // `{error:true, metaUnconfirmed:true}` and never sets `cancelled`.
    {
      const { sandbox: S, el } = buildEnv(SRC, { rows, gridMeta: meta,
                                                 choice: 'cancel', panel: PANEL_F });
      const res = await S.loadExistingMap({ quiet: true });
      console.log(`${label}/cancel    start_after_load=(${el.gridStartX.value},${el.gridStartY.value})`
        + ` cancelled=${res && res.cancelled} metaUnconfirmed=${res && res.metaUnconfirmed}`);
      eq(`${k}3 the modal was reached (cancel, not a refusal)`, res && res.cancelled === true, true);
      eq(`${k}3 the refusal path was NOT taken`, !!(res && res.metaUnconfirmed), false);
      eq(`${k}3 a cancelled load leaves the panel start alone`,
        `${el.gridStartX.value},${el.gridStartY.value}`, `${PANEL_F.startX},${PANEL_F.startY}`);
    }
  }

  // ── CASE H: A BLANK START BOX IS NOT A ZERO ────────────────────────────────────────────
  //
  // 🔴 Measured on the shipped source: with START X cleared and the operator picking ⚙️ 현재 패널,
  //    `parseInt('') || 0` in `resolveGridFrame`'s `current` branch resolved to 0, the load wrote
  //    that 0 BACK INTO THE BOX, and ⚡ Push then persisted `grid_start_x: 0`. The screen was
  //    perfect throughout: the box showed a number, the cells showed coordinates, and every one
  //    of them was on a different die from the one the row stated.
  //
  // The refusal is scored on THREE facts, because any one alone passes on a build that is wrong
  // in some other way: the load must not proceed (`cancelled`), the box must still be EMPTY (a
  // build that refuses after writing the 0 back has already fabricated it), and the operator must
  // be told which box (a silent refusal on the read path is its own defect).
  //
  // ⚠️ AND THE COUNTERFACTUAL, so the fixture is not proving something vacuous: the same panel
  //    with START X = 0 TYPED IN must still load. Otherwise "refuses when blank" would be
  //    satisfied by a build that simply refuses, and a declared zero is a legitimate origin.
  {
    const BLANK = { ...PANEL_F, startX: '' };
    const { sandbox: S, el, log } = buildEnv(SRC, { rows, gridMeta: UNREADABLE.F.meta,
                                                    choice: 'current', panel: BLANK });
    const res = await S.loadExistingMap({ quiet: true });
    console.log(`H blank-START/current  start_after_load=(${JSON.stringify(el.gridStartX.value)},`
      + `${el.gridStartY.value}) cells=${res && res.count} cancelled=${res && res.cancelled}`
      + ` toasts=${log.toasts.length}`);
    eq('H a blank START box refuses the choice instead of resolving to 0',
      res && res.cancelled === true, true);
    eq('H no cell was placed under a fabricated origin', (res && res.count) || 0, 0);
    eq('H the blank box was NOT back-filled with a fabricated 0',
      String(el.gridStartX.value), '');
    // ⚠️ `/START X/` ALONE PASSES ON THE BROKEN BUILD and I measured it doing so: the modal's own
    //    "맵 규격에 START X,Y가 없습니다" toast contains that substring, so the assertion matched
    //    a message about something else entirely. The refusal has to be identified by what makes
    //    it a refusal — the box is EMPTY — not by a word it happens to share with its neighbour.
    eq('H the operator is told WHICH box is empty and that it is empty',
      log.toasts.some(t => t.kind === 'error' && /START X/.test(t.msg) && /비어 있/.test(t.msg)),
      true);

    // the counterfactual — a TYPED zero is a declaration and must still open the map
    const ZERO = { ...PANEL_F, startX: 0 };
    const { sandbox: S0, el: el0 } = buildEnv(SRC, { rows, gridMeta: UNREADABLE.F.meta,
                                                     choice: 'current', panel: ZERO });
    const res0 = await S0.loadExistingMap({ quiet: true });
    console.log(`H' typed-zero/current   start_after_load=(${el0.gridStartX.value},`
      + `${el0.gridStartY.value}) cells=${res0 && res0.count}`);
    eq(`H' a TYPED zero still opens the map (the refusal is about silence, not about 0)`,
      res0 && res0.count, N);
    eq(`H' ...and the typed zero wins verbatim`, String(el0.gridStartX.value), '0');
    eq(`H' ...and it is still marked as a panel frame`, chosenMark(el0), 'panel');
  }

  console.log(`\n${failures.length ? 'FAIL' : 'PASS'} -- ${pass} passed, ${failures.length} failed`);
  // H1 protocol: the runner reads this line to tell "red with N assertions" from a crash.
  console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
  process.exit(failures.length ? 1 : 0);
}
run().catch(e => { console.error('PROBE THREW: ' + (e && e.stack || e)); process.exit(2); });
