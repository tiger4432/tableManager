/**
 * 📐 표준 (metadata-less) load — origin coherence harness.
 *
 * Scores ONE claim, on the shipped branch, by executing it:
 *
 *     A cell is placed where its STORED coordinate says. `origin + db`, with the origin
 *     declared in the frame (`grid_start_x/y`) — never by renumbering the cell.
 *
 * THE DEFECT IT REPLACES. `loadExistingMap`'s `standard` branch set `startX = startY = 0`
 * and then subtracted `minX`/`minY` from every stored coordinate in the cell loop. Nothing
 * re-added them. Because `getDbCoords` (which produces `cellObj.x`, the value ⚡ Push
 * serializes) is the exact inverse of `getCanvasCellFromDb` (which the load places
 * with), the shifted number was BOTH what the screen stated and what Push wrote.
 *
 * 🔴 THE ORACLE IS NOT THE TRANSFORM. Every fixture row carries a value that ENCODES its own
 *    stored coordinate (`"x,y"`). The assertion compares, key by key, the coordinate Push
 *    would write for a cell against the coordinate written inside that cell's own value. No
 *    coordinate function participates in the expectation — which is the whole point, because
 *    injectivity/range/round-trip checks are self-comparisons of the same function and a
 *    uniform offset passes all three (map-pm memory).
 *
 * FIXTURE AXES, all live on purpose:
 *    minX = 3, minY = -2   both non-zero, DIFFERENT, and one negative — an axis swap or a
 *                          single shared offset cannot pass by coincidence
 *    cols = 13, rows = 9   not square, so a transposed read cannot pass on width
 *    asymmetric cell set   not a full rectangle
 *
 * Run:  node client2/tests/standard_frame_origin_harness.mjs [--mutate]
 * Read-only against client2/. Not gated by `npm run build`; run by hand, per round.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC_PATH = join(HERE, '..', 'src', 'map_editor.js');
// Line endings normalised — every mutation below matches a multi-line `\n` string, and on a
// CRLF checkout those matches silently MISS (measured 2026-07-30 on the sibling harness:
// 8 of 18 mutations went unapplied while the baseline stayed green).
const SRC0 = readFileSync(SRC_PATH, 'utf8').replace(/\r\n/g, '\n');

const die = (m) => { console.error(`HARNESS FAILURE: ${m}\n(Nothing was compared.)`); process.exit(2); };

// 🔴 THE PARAMETER LIST IS WALKED BEFORE THE BODY IS LOOKED FOR, and that is not a detail.
//    The sibling harnesses find the body by `indexOf('{')` after the `(` — which on
//    `loadExistingMap(opts = {})` lands on the DEFAULT VALUE's braces and returns a slice that
//    ends inside the signature. It fails as `Unexpected end of input` on the JOINED source,
//    naming nothing. Close the parens first, then take the next `{`.
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

// The load path and everything its coordinates pass through. A rename here is exit 2, never green.
const SYMBOLS = [
  'physNum', 'gridDimNum', 'withPhysFrame',
  'getScreenShift', 'getTransformedPhysicalConfig',
  'getDieIndex', 'getCanvasCellFromDb', 'getCanvasCellFromDieIndex', 'getDbCoords',
  'isCellInsideWaferFast', 'getWaferBoundingBox',
  'frameDimBounds', 'applyPhysicalGeometry', 'applyPresetObject',
  // The ONE reaction to "the origin box moved under the cells", and the record it
  // compares against. A geometry-preset edit and a valid-die designation reach the SAME
  // function, so a slice that omits it turns applyPhysicalGeometry into a ReferenceError
  // that loadExistingMap's catch reports as a 0-cell load.
  'seatingSnapshot', 'reseatCellsToStoredCoords',
  'validDieBasis', 'isValidDieAt',
  'renderGridCanvas', 'cellFillColor', 'isProtectedFCell',
  'eachSavableCell', 'classifyUnsavableCells', 'serverCellKeySet',
  // THE FUNCTION UNDER TEST. Sliced whole and executed — not modelled.
  'loadExistingMap',
  // ...and the seven named steps it is now written in terms of. They are module-scope
  // functions in the SAME file, so a slice of `loadExistingMap` alone would ReferenceError
  // its way into this harness's catch and be reported as a 0-cell load. Each takes what it
  // needs as an argument and returns a value — none touches module state — so nothing new
  // has to be declared in the sandbox below.
  'collectMapKeyFilterModel', 'scanCoordinateBounds', 'resolveDeclaredGridMeta',
  'promptCoordinateChoice', 'resolveGridFrame', 'deriveLegendFromCellValues',
  'restoreDoeDraftWithPrecedence',
];

// ── Fixture ────────────────────────────────────────────────────────────────────────────
const MIN_X = 3, MIN_Y = -2;
const SPAN_X = 13, SPAN_Y = 9;      // -> cols 13, rows 9 (13 != 9, so a transpose cannot pass)

function fixtureRows() {
  const rows = [];
  const push = (x, y) => rows.push({
    data: { x: { value: x }, y: { value: y }, val: { value: `${x},${y}` } },
  });
  for (let y = MIN_Y; y < MIN_Y + SPAN_Y; y++) {
    for (let x = MIN_X; x < MIN_X + SPAN_X; x++) {
      // asymmetric — a full rectangle makes several kinds of mis-indexing invisible
      if ((x * 3 + y * 7) % 5 !== 0) push(x, y);
    }
  }
  // The four extremes are forced in, so `minX/minY/maxX/maxY` really are the declared ones.
  const corners = [[MIN_X, MIN_Y], [MIN_X + SPAN_X - 1, MIN_Y],
                   [MIN_X, MIN_Y + SPAN_Y - 1], [MIN_X + SPAN_X - 1, MIN_Y + SPAN_Y - 1]];
  corners.forEach(([x, y]) => {
    if (!rows.some(r => r.data.x.value === x && r.data.y.value === y)) push(x, y);
  });
  return rows;
}

// ── Sandbox ────────────────────────────────────────────────────────────────────────────
function makeInput(v) {
  return { value: String(v), checked: false, textContent: '', disabled: false,
           querySelector: () => null, appendChild() {} };
}

function buildEnv(src, opts = {}) {
  const pieces = [];
  for (const name of SYMBOLS) {
    const code = sliceFunction(src, name);
    if (!code) die(`'${name}' is gone from map_editor.js — renamed or reshaped. Nothing compared.`);
    // Compiled one at a time so a slice that goes wrong NAMES ITSELF. A joined-source
    // `Unexpected end of input` says only that one of two dozen extractions is bad.
    try { new vm.Script(code); }
    catch (e) { die(`slice of '${name}' does not parse: ${e && e.message}`); }
    pieces.push(code);
  }

  const log = { toasts: [], alerts: [], requests: [] };
  const choice = opts.choice || 'standard';
  const panel = opts.panel || { cols: 10, rows: 10, startX: 0, startY: 0, invertY: false,
                                dia: 300, chipX: 11, chipY: 13, offX: 0, offY: 0, margin: 3 };

  // The choice modal has exactly three exits and all three are buttons. The harness picks one
  // by letting that button's listener fire — the real promise, the real cleanup.
  const choiceBtn = (which) => {
    const b = makeInput('');
    b.addEventListener = (type, fn) => {
      if (type === 'click' && which === choice) setTimeout(fn, 0);
    };
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
    gridCanvas: { getBoundingClientRect: () => ({ width: 700, height: 700 }) },
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
    // Where the cells on screen are currently seated. Module-level in the source; declared
    // here so a read of it is a value, not a ReferenceError.
    cellsSeatedUnder: null,
    currentRotation: 0, currentSide: 'front',
    gridData: {}, gridCells2D: {},
    legend: [], activeBrush: '', legendDirty: false,
    legendReplaceScope: null, legendConflict: null,
    legendSaveState: { status: 'idle', at: '', error: '' }, draftBase: null,
    validDie: { basis: 'circle', keys: null, reason: '', ref: null, raw: undefined },
    loadedFCells: new Set(), serverCellKeys: null, overlayLayers: [],
    loadedIdentity: null, selectedTable: 'dt_map',
    tableSchema: { column_types: { x: 'number', y: 'number', val: 'string' } },
    API_BASE: '', OVERLAY_CELL_LIMIT: 2000,
    LEGEND_PALETTE: ['#e11', '#1a1', '#11e', '#ee1', '#1ee', '#e1e'],
    paintLockValues: null, currentHoverCell: null, lastSelectionBox: null,
    isBoxDragging: false, dragType: null,
    performance: { now: () => 0 }, window: { devicePixelRatio: 1 },
    requestAnimationFrame(fn) { fn(); },
    getComputedStyle: () => ({ getPropertyValue: () => '#000' }),
    getThemeColors: () => ({ outBg: '#eee', line: '#ccc', lineStrong: '#bbb', text: '#000',
      inBg: '#fff', insideEmpty: '#eef', textEmpty: '#345', textOut: '#567', origin: '#f00',
      notch: '#00f', gridText: '#333', dim: '#999', waferEdge: '#111', wmFront: '#eef',
      wmBack: '#fed', accent: '#06c', danger: '#c00', dangerWeak: '#fdd', rangeFill: '#e3e',
      surface: '#fff', success: '#171', warning: '#850' }),
    // --- stubbed collaborators (each scored by its own harness) ----------------------
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
    // Routing is OFF here on purpose: this harness scores the origin, and F5c has its own.
    applyRoutedPreset: async () => null,
    fetchGridMetaFor: async () => (opts.gridMeta || null),
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
  return { sandbox, el, log };
}

// ── Scoring ────────────────────────────────────────────────────────────────────────────
let failures = [];
let compared = 0;
const eq = (name, expected, actual, note) => {
  compared++;
  const a = JSON.stringify(actual), e = JSON.stringify(expected);
  if (a !== e) failures.push(`${name}: expected ${e}, got ${a}${note ? ` — ${note}` : ''}`);
};
const evidence = [];

// THE PAYLOAD, not a model of it: `eachSavableCell` IS `pushMapData`'s iterator and
// `cellObj.x/.y` ARE the numbers it writes into the x/y columns.
const pushPayload = (S) => {
  const out = {};
  S.eachSavableCell((co, val) => { out[co.key] = { coord: `${co.x},${co.y}`, val }; });
  return out;
};

// The independent oracle: each cell's own value states the coordinate its DB row held.
const coordDisagreements = (payload) => Object.keys(payload)
  .filter(k => payload[k].coord !== payload[k].val)
  .map(k => `${k}: value says (${payload[k].val}) but Push would write (${payload[k].coord})`);

async function scoreAll(src, { verbose = false } = {}) {
  failures = []; compared = 0; evidence.length = 0;

  const rows = fixtureRows();

  // ══ 표준 — the branch this round fixes ═══════════════════════════════════════════════
  let round1 = null;
  let round1Meta = null;
  {
    const { sandbox: S, el, log } = buildEnv(src, { rows });
    const res = await S.loadExistingMap({ quiet: true });

    eq('std/loaded', rows.length, res && res.count);
    eq('std/no-alert', [], log.alerts);
    // The frame DECLARES the origin. This is the fix, stated on the control the operator sees
    // and the value `pushMapData` copies into `grid_start_x`/`grid_start_y`.
    eq('std/origin-declared-in-frame', [String(MIN_X), String(MIN_Y)],
       [String(el.gridStartX.value), String(el.gridStartY.value)],
       'the data minimum must be the frame origin, not folded into the cells');
    eq('std/grid-is-the-data-extent', [String(SPAN_X), String(SPAN_Y)],
       [String(el.gridCols.value), String(el.gridRows.value)]);
    eq('std/orientation-is-the-declared-default', [0, 'front'], [S.currentRotation, S.currentSide]);

    const payload = pushPayload(S);
    eq('std/every-cell-is-savable', rows.length, Object.keys(payload).length,
       'the 표준 branch installs a no-mask spec, so nothing may fall outside');
    // 🔴 THE ASSERTION OF THE ROUND, key by key against the value-encoded oracle.
    eq('std/placed-at-origin-plus-db', [], coordDisagreements(payload).slice(0, 8));
    eq('std/oracle-population-is-not-empty', true, Object.keys(payload).length > 0);
    // The axes are scored INDEPENDENTLY: assert both minima appear, so a fix that got one
    // axis right and swapped the other cannot pass on the aggregate.
    const coords = Object.values(payload).map(p => p.coord);
    const xs = coords.map(c => parseInt(c.split(',')[0], 10));
    const ys = coords.map(c => parseInt(c.split(',')[1], 10));
    eq('std/x-range-is-the-stored-range', [MIN_X, MIN_X + SPAN_X - 1], [Math.min(...xs), Math.max(...xs)]);
    eq('std/y-range-is-the-stored-range', [MIN_Y, MIN_Y + SPAN_Y - 1], [Math.min(...ys), Math.max(...ys)]);
    eq('std/axes-are-distinguishable', true, MIN_X !== MIN_Y,
       'if the two minima were equal an axis swap would pass by coincidence');

    round1 = payload;
    // 🔴 THE METADATA RECORD PUSH WOULD WRITE, built from the SAME controls `pushMapData`
    //    reads (`gridMeta` inside `buildPushGridMetadata`, which `pushMapData` calls;
    //    it was inline in that function until the R6 decomposition).
    //    Hard-coding the expected origin here instead would make the round-trip fixture
    //    disagree with itself under a defective source and report drift that Push never
    //    produced — measured: it did exactly that on the first draft of this harness.
    round1Meta = {
      grid_cols: parseInt(el.gridCols.value, 10), grid_rows: parseInt(el.gridRows.value, 10),
      grid_start_x: parseInt(el.gridStartX.value, 10), grid_start_y: parseInt(el.gridStartY.value, 10),
      grid_y_invert: !!el.gridYInvert.checked,
      rotation: S.currentRotation, side: S.currentSide,
      phys_wafer_dia: parseFloat(el.physWaferDia.value), phys_chip_x: parseFloat(el.physChipX.value),
      phys_chip_y: parseFloat(el.physChipY.value), phys_offset_x: parseFloat(el.physOffsetX.value),
      phys_offset_y: parseFloat(el.physOffsetY.value), phys_edge_margin: parseFloat(el.physEdgeMargin.value),
    };
    evidence.push(`[std] ${Object.keys(payload).length} cells loaded from stored x ${MIN_X}..`
      + `${MIN_X + SPAN_X - 1} / y ${MIN_Y}..${MIN_Y + SPAN_Y - 1}; frame origin `
      + `(${el.gridStartX.value},${el.gridStartY.value}); every Push coordinate equals the `
      + `coordinate its own row carried`);
  }

  // ══ ROUND TRIP — feed Push's own output back in as the next load's rows ═══════════════
  //
  // 🔴 THIS IS THE MEASUREMENT THAT DECIDES WHETHER THE ROUND NEEDS A MIGRATION. Under the
  //    defective source the first pass rewrote the coordinates; the question is whether a
  //    SECOND pass moves them again (cumulative — old data keeps degrading) or lands on a
  //    fixed point (one-time — the fix stops new corruption and old damage is a separate
  //    matter). Both metadata shapes are measured, because a Push writes a
  //    `wafer_map_metadata` record and the next load then takes the `meta` branch instead.
  {
    const back = Object.values(round1).map(p => {
      const [x, y] = p.coord.split(',').map(Number);
      // The VALUE still carries the ORIGINAL coordinate — that is what makes drift visible
      // across rounds even when the stored x/y has already moved.
      return { data: { x: { value: x }, y: { value: y }, val: { value: p.val } } };
    });
    // (a) metadata absent again -> the 표준 branch runs a second time
    {
      const { sandbox: S, el } = buildEnv(src, { rows: back });
      await S.loadExistingMap({ quiet: true });
      const p2 = pushPayload(S);
      const moved = Object.keys(p2).filter(k => !round1[k] || p2[k].coord !== round1[k].coord);
      eq('roundtrip/no-meta/second-pass-is-a-fixed-point', [], moved.slice(0, 6),
         'a second 표준 load must not move a coordinate the first one produced');
      eq('roundtrip/no-meta/origin-stable', [String(MIN_X), String(MIN_Y)],
         [String(el.gridStartX.value), String(el.gridStartY.value)]);
      evidence.push(`[roundtrip/no-meta] second 표준 load moved ${moved.length} of `
        + `${Object.keys(p2).length} coordinates`);
    }
    // (b) metadata present (what a Push leaves behind) -> the `meta` branch runs
    {
      const { sandbox: S } = buildEnv(src, { rows: back, gridMeta: round1Meta });
      await S.loadExistingMap({ quiet: true });
      const p2 = pushPayload(S);
      const moved = Object.keys(p2).filter(k => !round1[k] || p2[k].coord !== round1[k].coord);
      eq('roundtrip/meta/second-pass-is-a-fixed-point', [], moved.slice(0, 6));
      eq('roundtrip/meta/values-still-state-their-own-coordinate', [],
         coordDisagreements(p2).slice(0, 6));
      evidence.push(`[roundtrip/meta] reload under the pushed wafer_map_metadata moved `
        + `${moved.length} of ${Object.keys(p2).length} coordinates`);
    }
  }

  // ══ 현재 패널 — the OTHER choice, which the defect never touched ══════════════════════
  // A regression guard: the operator who types the true origin into the panel must get the
  // stored coordinates back, exactly as before this round.
  {
    const panel = { cols: SPAN_X, rows: SPAN_Y, startX: MIN_X, startY: MIN_Y, invertY: false,
                    dia: 600, chipX: 1, chipY: 1, offX: 0, offY: 0, margin: 3 };
    const { sandbox: S, el } = buildEnv(src, { rows, choice: 'current', panel });
    await S.loadExistingMap({ quiet: true });
    eq('current/panel-origin-kept', [String(MIN_X), String(MIN_Y)],
       [String(el.gridStartX.value), String(el.gridStartY.value)]);
    const payload = pushPayload(S);
    eq('current/placed-at-origin-plus-db', [], coordDisagreements(payload).slice(0, 8));
    eq('current/population-is-not-empty', true, Object.keys(payload).length > 0);
    evidence.push(`[current] ${Object.keys(payload).length} cells; panel-declared origin `
      + `(${MIN_X},${MIN_Y}) reproduces every stored coordinate`);
  }

  // ══ Structural: the shift must not come back anywhere on the load path ═══════════════
  {
    eq('structural/no-min-subtraction-on-load', true,
       !/xNum\s*=\s*xNum\s*-\s*minX/.test(src) && !/yNum\s*=\s*yNum\s*-\s*minY/.test(src),
       'renumbering a cell on load is the defect itself');
  }

  if (verbose) evidence.forEach(e => console.log('  ' + e));
  return { failures: failures.slice(), compared };
}

// ── Mutations ──────────────────────────────────────────────────────────────────────────
// ⚠️ ANCHORS ARE INDENTATION-SENSITIVE. `String.replace` with a string literal matches
//    verbatim, and a mutation that does not apply is reported as "MUTATION DID NOT APPLY"
//    — an unscored axis, not a failure. `FIXED_ORIGIN` now lives in the module-scope step
//    `resolveGridFrame` (4-space body indent) instead of inline in `loadExistingMap`
//    (6 spaces). `OLD_SHIFT` is unchanged: the cell-placement loop stayed inline precisely
//    so that D0/D2 can keep injecting code that reads `userChoice`, `minX` and `minY`.
const FIXED_ORIGIN = `    startX = minX;
    startY = minY;`;
const OLD_SHIFT = `            const cell = getCanvasCellFromDb(xNum, yNum, cols, rows, rotation, side, invertY, startX, startY);`;

const MUTATIONS = [
  // 🔴 THE DEFECT ITSELF, put back verbatim — the only self-check that is worth anything.
  ['D0 the shipped defect restored in full (startX=0 + the minX/minY subtraction)',
   s => s.replace(FIXED_ORIGIN, '    startX = 0;\n    startY = 0;')
         .replace(OLD_SHIFT,
                  `            if (userChoice === 'standard') {
              xNum = xNum - minX;
              yNum = yNum - minY;
            }
` + OLD_SHIFT)],
  ['D1 the origin goes back to 0 (the frame stops recording where the data starts)',
   s => s.replace(FIXED_ORIGIN, '    startX = 0;\n    startY = 0;')],
  ['D2 the cell-renumbering subtraction comes back on top of the declared origin',
   s => s.replace(OLD_SHIFT,
                  `            if (userChoice === 'standard') {
              xNum = xNum - minX;
              yNum = yNum - minY;
            }
` + OLD_SHIFT)],
  ['D3 the two axes are swapped (startX <- minY, startY <- minX)',
   s => s.replace(FIXED_ORIGIN, '    startX = minY;\n    startY = minX;')],
  ['D4 only the X axis is fixed (Y keeps the old zero origin)',
   s => s.replace(FIXED_ORIGIN, '    startX = minX;\n    startY = 0;')],
  ['D5 the origin is taken from the MAXIMUM instead of the minimum',
   s => s.replace(FIXED_ORIGIN, '    startX = maxX;\n    startY = maxY;')],
  // Placement is derived from the frame in ONE function; a second implementation is the
  // invariant-① violation this domain exists to stop.
  ['D6 the load stops applying the frame origin (getCanvasCellFromDb called with 0,0)',
   s => s.replace(OLD_SHIFT,
                  '            const cell = getCanvasCellFromDb(xNum, yNum, cols, rows, rotation, side, invertY, 0, 0);')],
];

const base = await scoreAll(SRC0, { verbose: true });
console.log(`\n${base.failures.length === 0 ? '✓' : '✗'} baseline: ${base.compared} assertions, `
  + `${base.failures.length} failure(s)`);
// H1 protocol: the runner reads this line to tell "red with N assertions" from a crash.
console.log(`ASSERTIONS ${base.compared} ${base.failures.length}`);
base.failures.forEach(f => console.log('   ✗ ' + f));

if (process.argv.includes('--mutate')) {
  console.log('\n── MUTATIONS (each must turn the harness RED) ──');
  let applied = 0, notApplied = 0, byAssertion = 0, byCrash = 0, stillGreen = 0;
  const crashed = [], green = [], skipped = [];
  for (const [name, apply] of MUTATIONS) {
    const mutated = apply(SRC0);
    if (mutated === SRC0) {
      console.log(`  ! ${name}: MUTATION DID NOT APPLY (harness bug — this axis is unscored)`);
      notApplied++; skipped.push(name); continue;
    }
    applied++;
    let r;
    try { r = await scoreAll(mutated); }
    catch (e) {
      console.log(`  ~ ${name} -> harness THREW (${e && e.message}) — red, but unnamed`);
      byCrash++; crashed.push(name); continue;
    }
    if (r.failures.length === 0) {
      console.log(`  ✗ ${name} -> STILL GREEN — this axis is unscored`);
      stillGreen++; green.push(name); continue;
    }
    byAssertion++;
    console.log(`  ✓ ${name} -> ${r.failures.length} failure(s): ${r.failures[0].split(':')[0]}`);
    // D0 is the shipped defect put back verbatim, so its full failure list is the round's
    // damage report — including whether the SECOND round trip moves anything, which is what
    // decides one-time vs cumulative and therefore whether a migration is owed.
    if (name.startsWith('D0')) {
      r.failures.forEach(f => console.log(`      · ${f.length > 220 ? f.slice(0, 220) + '…' : f}`));
    }
  }
  console.log(`\nmutations: ${MUTATIONS.length} declared · ${applied} applied · ${notApplied} did `
    + `not apply | caught by a NAMED assertion ${byAssertion} · caught only by a crash ${byCrash} `
    + `· undetected ${stillGreen}`);
  if (crashed.length) console.log(`  ~ unnamed (crash-only) detection: ${crashed.join(' | ')}`);
  if (skipped.length) console.log(`  ! did not apply: ${skipped.join(' | ')}`);
  if (green.length) console.log(`  ✗ undetected: ${green.join(' | ')}`);
  if (stillGreen > 0 || notApplied > 0) {
    console.log(`\n✗ ${stillGreen + notApplied} mutation(s) scored nothing.`);
    process.exit(1);
  }
}

process.exit(base.failures.length === 0 ? 0 : 1);
