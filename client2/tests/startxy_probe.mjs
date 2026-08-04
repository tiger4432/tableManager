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
 *   F  metadata row exists but carries no start fields -> the panel's start survives (the
 *      pre-fix defect left the inputs as the string "undefined")
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
  ['physNum'], ['gridDimNum'], ['withPhysFrame'],
  ['getScreenShift'], ['getTransformedPhysicalConfig'],
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
  ['promptCoordinateChoice'], ['resolveGridFrame'], ['deriveLegendFromCellValues'],
  ['restoreDoeDraftWithPrecedence'],
  // The pure predicate the load consults before letting anything replace the valid-die
  // designation (user ruling 2026-08-04). Absent from older revisions this probe also slices,
  // which the per-entry `missing` tolerance above already covers; present from the carry fix
  // onward, where omitting it is a ReferenceError inside `loadExistingMap`'s own catch.
  ['parseValidDieRef'],
];

function makeInput(v) {
  return { value: String(v), checked: false, textContent: '', disabled: false,
           querySelector: () => null, appendChild() {} };
}

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
    physFrameOverride: null,
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

  // CASE F: metadata row exists but carries no grid_start_x/y (hand-written / older
  // schema). Pre-fix the inputs ended up as the string "undefined".
  {
    const { grid_start_x, grid_start_y, ...noStart } = META;
    const panel = { cols: 10, rows: 10, startX: 7, startY: 7, invertY: false,
                    dia: 300, chipX: 1, chipY: 1, offX: 0, offY: 0, margin: 3 };
    const { sandbox: S, el } = buildEnv(SRC, { rows, gridMeta: noStart, panel });
    const res = await S.loadExistingMap({ quiet: true });
    console.log(`F meta-no-start    start_after_load=(${el.gridStartX.value},${el.gridStartY.value})`
      + ` panel_had=(7,7) cells=${res && res.count}`);
    eq('F panel start_x survives a start-less metadata row', String(el.gridStartX.value), '7');
    eq('F panel start_y survives a start-less metadata row', String(el.gridStartY.value), '7');
  }

  console.log(`\n${failures.length ? 'FAIL' : 'PASS'} -- ${pass} passed, ${failures.length} failed`);
  // H1 protocol: the runner reads this line to tell "red with N assertions" from a crash.
  console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
  process.exit(failures.length ? 1 : 0);
}
run().catch(e => { console.error('PROBE THREW: ' + (e && e.stack || e)); process.exit(2); });
