/**
 * F8 + F5c harness — executes the valid-die designation path of map_editor.js in a vm sandbox.
 *
 * Read-only against client2/. Functions are sliced out of the source text (same technique as
 * contracts/map_seam/client_harness.mjs) and evaluated with DOM/network stubs, so the branch
 * that ships is the branch that is scored.
 *
 * Run:  node client2/tests/valid_die_frame_adoption_harness.mjs [--mutate]
 *
 * ⚠️ THE FILE NAME IS NOW HISTORICAL. It was written for F6, where a valid-die designation
 *    ADOPTED the reference map's grid dimensions and physical spec. `61440e6` removed that on
 *    the user's instruction — 「그리드 크기가 달라도 좌표는 db값 그대로 보존하고 화면 표기
 *    밀리게 그냥 보여주기」 — and this harness was rewritten to score the contract that replaced
 *    it. The name is kept so the round history stays greppable; what it scores is F8:
 *
 *      A valid-die designation ADOPTS NOTHING. Not the dimensions, not the physical spec,
 *      not the orientation. A reference grid of a different size produces a mask drawn in
 *      the REFERENCE's index space, which therefore appears OFFSET on screen, and NO STORED
 *      COORDINATE MOVES. The difference is stated once as an info toast.
 *
 *    The reason a smaller change was not possible: there is no stored coordinate to preserve.
 *    `gridData` is `physical key -> value`; the DB x/y is derived at Push time from the cell's
 *    canvas position under the CURRENT frame. So "preserve the coordinate" has exactly one
 *    implementation — leave the cell where it is — and that means touching no frame axis.
 *
 * NOT gated by `npm run build` — that runner only discovers client_harness.mjs under
 * contracts/ (contract-keeper's). Same standing as its siblings here
 * (valid_die_authoring_harness.mjs, push_gate_harness.mjs): run by hand, per round.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC_PATH = join(HERE, '..', 'src', 'map_editor.js');
// 🔴 LINE ENDINGS ARE NORMALISED, AND THAT IS NOT COSMETIC. Every mutation below finds its
//    target by matching a multi-line source string written with `\n`. The repo stores these
//    files with CRLF and `core.autocrlf=true`, so on a plain checkout the working copy has
//    `\r\n` and those matches silently MISS — `mutation did not apply`. Measured 2026-07-30:
//    8 of 18 mutations went undetected that way while the baseline stayed green, which is the
//    exact "unscored axis reported as passing" failure this harness exists to prevent.
const SRC0 = readFileSync(SRC_PATH, 'utf8').replace(/\r\n/g, '\n');

const die = (m) => { console.error(`HARNESS FAILURE: ${m}\n(Nothing was compared.)`); process.exit(2); };

// [1-a 2026-08-04] The FIXED valid-die storage table. `parseValidDieRef` reads this module
// const since the load path was pinned, so a sandbox without it throws ReferenceError and the
// whole slice dies before comparing anything. EXTRACTED from the source, never re-typed:
// a copy that drifted would score the wrong table green. Same shape as the extraction in
// valid_die_authoring_harness.mjs — one spelling, three harnesses.
const VALID_DIE_TABLE = (() => {
  const m = /const\s+VALID_DIE_TABLE\s*=\s*'([^']*)'\s*;/.exec(SRC0);
  if (!m) die('const VALID_DIE_TABLE not found in map_editor.js — the fixed storage table is gone or renamed.');
  return m[1];
})();

function sliceFunction(source, name) {
  const decl = new RegExp(`(^|\\n)\\s*(?:async\\s+)?function\\s+${name}\\s*\\(`);
  const m = decl.exec(source);
  if (!m) return null;
  const start = m.index + (m[1] ? m[1].length : 0);
  let i = source.indexOf('{', m.index + m[0].length - 1);
  if (i < 0) return null;
  let depth = 0;
  for (; i < source.length; i++) {
    if (source[i] === '{') depth++;
    else if (source[i] === '}') { depth--; if (depth === 0) return source.slice(start, i + 1); }
  }
  die(`unbalanced braces extracting '${name}'`);
}

// Every symbol the new branches actually run. A missing one is a rename -> exit 2, never green.
const SYMBOLS = [
  'physNum', 'gridDimNum', 'getDieIndex', 'getCanvasCellFromDieIndex', 'getCanvasCellFromDb',
  // [2b] `physDeclaration` no longer spells "did this control say anything" inline: that
  // question is now shared with the grid-frame reader, so it is one function and it is here.
  'controlIsSilent',
  'geometryIsAutoRegistered', 'markGeometryAutoRegistered', 'physDeclaration', 'cellMetrics',   // see the note in geometry_origin_reseat_harness.mjs
  'getTransformedPhysicalConfig', 'getScreenShift', 'isCellInsideWaferFast', 'getWaferBoundingBox',
  'frameFromMeta', 'currentFrame', 'resolveFrame', 'frameAxesKey',
  // [H5] the reference-dimension ceiling and the ONE place its bound is defined
  // (`applyPhysicalGeometry` reads the same function, so a mutation there moves both).
  'frameDimBounds', 'frameDimError',
  'applyPresetObject', 'applyPhysicalGeometry',
  // The ONE reaction to "the origin box moved under the cells", and the record it
  // compares against. A geometry-preset edit and a valid-die designation reach the SAME
  // function, so a slice that omits it turns applyPhysicalGeometry into a ReferenceError
  // that loadExistingMap's catch reports as a 0-cell load.
  'seatingSnapshot', 'reseatCellsToStoredCoords',
  'applyRoutedPreset',                    // F5c — the routing consumer
  'parseValidDieRef', 'validDieBasis', 'isValidDieAt', 'validDieChainError', 'validDieRefDisplay',
  // [rule 6] projectCellsToPhys is now STATED IN TERMS OF the mm projection -- both or neither.
  // Omitting the sibling throws before assertion one, and a runner that only knows red/green
  // reports that as "still red" while ~200 assertions run zero times.
  'projectCellsToWaferMm', 'projectCellsToPhys', 'resolveValidDie',
  // [R5] the five named steps `resolveValidDie` is now written in terms of. Every mutation
  // below still anchors INSIDE `resolveValidDie` itself (the truncation demotion, the H5
  // ceiling, the alignment toast, the catch's internal/data split) — those blocks stayed
  // inline precisely because H5d and N6 inject code into their scope. These five are the
  // parts that could leave; a missing name here is a ReferenceError the catch reports as an
  // internal error, i.e. RED, never a silent green.
  'fitGridToMask', 'summariseReseat', 'resolveReferenceSpec',
  'deriveMaskKeys', 'diagnoseDesignationAlignment',
  // The Push-gate classifier. `renderGridCanvas` is sliced too, NOT modelled:
  // `classifyUnsavableCells`'s domain is whatever the real renderer put in `gridCells2D`, and
  // that domain is wider than the visual grid (it draws to -1x..2x). A harness that re-derived
  // "off the grid" by hand measured 190 where the shipped classifier measures 27.
  'classifyUnsavableCells', 'eachSavableCell', 'serverCellKeySet',
  'renderGridCanvas', 'getDbCoords', 'cellFillColor', 'isProtectedFCell',
  // The ONE definition of "this many cells make Push refuse".
  'pushBlockingCount',
];

// ── Fixtures ────────────────────────────────────────────────────────────────────────────
// The defect axes must be LIVE or the fixture proves nothing (map-pm memory):
//   anisotropic chip (chipX != chipY) -> a rot-90 pitch swap defect can appear
//   rotation 90 + side back           -> the mirror/rotation composition is exercised
//   grid_start != 0, offsets != 0     -> the bbox/start terms cannot cancel silently
const PANEL_BEFORE = {   // the target map's frame as the editor holds it (CORE-like 7x7)
  cols: 45, rows: 45, startX: 0, startY: 0, invertY: false,
  rotation: 0, side: 'front',
  dia: 300, chipX: 7, chipY: 7, offX: 0, offY: 0, margin: 3,
};
// A — realistic reference: stored dims EQUAL what applyPhysicalGeometry derives (29x25)
// Offsets are ONE FULL CHIP PITCH on each axis on purpose: a sub-cell offset rounds away in
// getDieIndex and the whole offset term would then be unscored (a fixture that kills its
// own defect axis — map-pm memory). At one pitch the shift is exactly +-1 cell and shows up.
const REF_A = {
  grid_cols: 29, grid_rows: 25, grid_start_x: 3, grid_start_y: 2, grid_y_invert: true,
  rotation: 90, side: 'back',
  phys_wafer_dia: 300, phys_chip_x: 11, phys_chip_y: 13,
  phys_offset_x: 11.0, phys_offset_y: 13.0, phys_edge_margin: 3,
};
// B — stored dims DIVERGE from the derived value (a bbox-opened or ingestion-registered map).
//     This is the fixture that makes the explicit dimension write load-bearing.
const REF_B = { ...REF_A, grid_cols: 41, grid_rows: 51 };
// C — THE WORST SHAPE FOR A DIMENSION ADOPTION, and the reason it needs its own fixture.
//     Identical physical spec, grid ONE larger, ODD -> EVEN. Measured on the shipped
//     primitives: adopting this frame moves EVERY stored coordinate by one
//     (`DB(-2,-2) -> DB(-3,-3)`) while LOSING NOT ONE CELL — so the Push contrast gate, which
//     only counts cells that leave the grid or the circle, is blind to it end to end. A and B
//     both lose cells, which is why they cannot score that axis. This is the fixture that
//     states what F8's "adopt nothing" is worth.
const REF_C = {
  grid_cols: 46, grid_rows: 46, grid_start_x: 0, grid_start_y: 0, grid_y_invert: false,
  rotation: 0, side: 'front',
  phys_wafer_dia: PANEL_BEFORE.dia, phys_chip_x: PANEL_BEFORE.chipX, phys_chip_y: PANEL_BEFORE.chipY,
  phys_offset_x: PANEL_BEFORE.offX, phys_offset_y: PANEL_BEFORE.offY,
  phys_edge_margin: PANEL_BEFORE.margin,
};

// ── Sandbox ─────────────────────────────────────────────────────────────────────────────
function makeInput(v) { return { value: String(v), checked: false, querySelector: () => null, appendChild() {} }; }

function buildEnv(src, opts = {}) {
  const pieces = [];
  for (const name of SYMBOLS) {
    const code = sliceFunction(src, name);
    if (!code) die(`'${name}' is gone from map_editor.js — renamed or reshaped. Nothing compared.`);
    pieces.push(code);
  }
  const log = { toasts: [], requests: [], renders: 0, legendCounts: 0 };
  // `opts.panel` lets a case declare its own target frame (fixture E needs the real
  // 4MAIN_TRIM shape: 33x25 with a negative origin). Default is PANEL_BEFORE.
  const P = opts.panel || PANEL_BEFORE;
  const el = {
    gridCols: makeInput(P.cols), gridRows: makeInput(P.rows),
    gridStartX: makeInput(P.startX), gridStartY: makeInput(P.startY),
    gridYInvert: { checked: P.invertY },
    physWaferDia: { value: String(P.dia), querySelector: () => ({}), appendChild() {} },
    physChipX: makeInput(P.chipX), physChipY: makeInput(P.chipY),
    physOffsetX: makeInput(P.offX), physOffsetY: makeInput(P.offY),
    physEdgeMargin: makeInput(P.margin),
    gridCanvas: { getBoundingClientRect: () => ({ width: 700, height: 700 }) },
    // Paint sink: every 2D-context method is a no-op, every property writable. The render
    // loop's DECISIONS (getDieIndex / isValidDieAt / isCellInsideWaferFast) are real.
    waferCanvas: { width: 0, height: 0, getContext: () => new Proxy({}, {
      get: (t, k) => (k in t ? t[k] : (t[k] = () => {})), set: (t, k, v) => (t[k] = v, true) }) },
    showAnnotations: { checked: false },
    validDieRefKey: makeInput(''), validDieRefTable: makeInput(''), validDieRefList: null,
  };
  // 🔴 THE DOM FRAME CONTROLS ARE THE ASSERTION SURFACE, so they are ordinary writable
  //    objects. F8's contract is that nothing writes to them on this path; a stub that
  //    swallowed writes would make that contract untestable by construction.
  const sandbox = {
    // `debug` was MISSING, and that is not a cosmetic gap: the [1e] zero-stranded path
    // calls console.debug, so the PRIMARY case (an empty target adopts silently) threw
    // `console.debug is not a function`, got classified as an internal error, and the three
    // F6/empty-target assertions have been RED — i.e. unscored — since that path landed.
    console: { warn() {}, info() {}, error() {}, log() {}, debug() {} },
    el,
    boundingBoxCache: {},
    // Where the cells on screen are currently seated. Module-level in the source; declared
    // here so a read of it is a value, not a ReferenceError.
    cellsSeatedUnder: null,
    currentRotation: P.rotation,
    currentSide: P.side,
    gridData: {},
    validDie: { basis: 'circle', keys: null, reason: '', ref: null, raw: undefined },
    validDieResolveSeq: 0,
    selectedTable: 'dt_map',
    loadedIdentity: null,
    tableSchema: { column_types: {} },
    API_BASE: '',
    OVERLAY_CELL_LIMIT: 2000,
    VALID_DIE_TABLE,
    // --- the REAL renderer runs; only the pixels are stubbed ------------------------
    // gridCells2D is the domain classifyUnsavableCells reads, so it must be built by the
    // shipped loop, not by the harness. Everything below is paint, not decision.
    gridCells2D: {},
    legend: [{ value: 'A', color: '#0a0' }],
    overlayLayers: [], loadedFCells: new Set(), serverCellKeys: null,
    paintLockValues: null, currentHoverCell: null, lastSelectionBox: null,
    syncOverlayGeometry() {}, getThemeColors: () => ({ outBg: '#eee', line: '#ccc', text: '#000',
      inBg: '#fff', origin: '#f00', notch: '#00f', gridText: '#333', dim: '#999' }),
    performance: { now: () => 0 },
    window: { devicePixelRatio: 1 },
    updateOrientationUI() {}, updateSideIndicator() {},
    scheduleRenderGridCanvas() { log.renders++; },
    updateLegendCounts() { log.legendCounts++; },
    activeOverlayLayers: () => [], drawOverlayMarkers() {}, updateNotchPosition() {},
    isBoxDragging: false, dragType: null,
    getComputedStyle: () => ({ getPropertyValue: () => '#000' }),
    renderValidDieChip() {}, syncValidDieRefControls() {},
    // 🔴 THE THIRD ARGUMENT IS KEPT. Selecting a notice by GREPPING ITS TEXT pins wording,
    //    and wording is the thing a UI round is allowed to change -- this file went red on
    //    sixteen assertions the day the sentence was rewritten, none of which was about the
    //    sentence. `dedupeKey` is the notice's IDENTITY and it survives a copy edit.
    showToast: (msg, kind, opts) => log.toasts.push({ msg: String(msg), kind,
                                                      key: opts && opts.dedupeKey }),
    requestAnimationFrame(fn) { fn(); },
    // --- network (all stubbed; every call is counted) ---
    fetchMapKeySpec: async (t) => { log.requests.push(`spec:${t}`); return { ok: true, keyColumns: ['map_id'], columnTypes: {} }; },
    canonicalMapKey: (kc, k) => String(k),
    fetchServedBinding: async (t) => { log.requests.push(`binding:${t}`); return { x: 'x', y: 'y', keyColumns: ['map_id'], source: 'declared' }; },
    fetchGridMetaFor: async (t, k) => {
      log.requests.push(`meta:${t}/${k}`);
      // A PROGRAMMER error, not a data/network one — the class the catch must name as internal.
      if (opts.injectInternalError) { const err = new ReferenceError('someHelper is not defined'); throw err; }
      // An expected, authored failure — its message must still pass through verbatim.
      if (opts.injectDataError) { throw new Error('메타 조회가 서버에서 거부됐습니다 (HTTP 503)'); }
      return opts.refMeta || null;
    },
    buildKeyFilters: () => ({}),
    fetch: async (url) => {
      log.requests.push(`fetch:${String(url).split('?')[0]}`);
      if (String(url).includes('preset-routing')) {
        return { ok: opts.routingHttpOk !== false, status: opts.routingHttpOk === false ? 500 : 200,
                 json: async () => opts.routingBody };
      }
      // Invariant ④: a truncated response must be DEMOTED TO A FAILURE, never masked from.
      // `opts.truncate` returns OVERLAY_CELL_LIMIT + 1 rows, which is exactly what the server
      // sends when the real row count exceeds the limit the client asked for.
      const rowsOut = (opts.refCells || []).map(c => ({ data: { x: { value: c.x }, y: { value: c.y } } }));
      if (opts.truncate) {
        while (rowsOut.length <= sandbox.OVERLAY_CELL_LIMIT) rowsOut.push(rowsOut[0]);
      }
      return { ok: true, status: 200, json: async () => ({ data: rowsOut }) };
    },
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  try { vm.runInContext(pieces.join('\n'), sandbox); }
  catch (e) { die(`extracted sources did not evaluate: ${e && e.message}`); }
  return { sandbox, el, log };
}

// ── Scoring ─────────────────────────────────────────────────────────────────────────────
let failures = [];
let compared = 0;
const eq = (name, expected, actual, note) => {
  compared++;
  const a = JSON.stringify(actual), e = JSON.stringify(expected);
  if (a !== e) failures.push(`${name}: expected ${e}, got ${a}${note ? ` — ${note}` : ''}`);
};
const evidence = [];

const wrongWxH = (f) => `${f.cols}x${f.rows}`;

// ── An INDEPENDENT oracle: `physical key -> stored (DB) coordinate`, under any frame ───────
//
// 🔴 It is built from the two shipped PER-CELL primitives (`getDieIndex` /
//    `getDbCoords`) under the frame window. It used to be independent of
//    `dbCoordsByPhysKey`; that function is now DELETED (it existed only for the adoption cost
//    and the reposition plan), so this is the only implementation left and the harness owns it.
//    That is the correct ownership: it models what the SOURCE no longer does, which is exactly
//    what a negative control has to be made of.
function coordMapOracle(S, frame) {
  const rf = S.resolveFrame(frame);
  const isRot = (rf.rotation === 90 || rf.rotation === 270);
  const vc = isRot ? rf.rows : rf.cols, vr = isRot ? rf.cols : rf.rows;
  // [2026-08-06] The frame is an ARGUMENT now, so this oracle opens its window by PASSING
  // `rf`. It used to wrap the loop in `withPhysFrame(rf, …)` and call both functions with no
  // frame at all, which was correct while they read the module binding.
  //
  // 🔴 THIS WENT INERT DURING THE FRAME REFACTOR AND THE FIXTURE'S OWN CONTROL CAUGHT IT.
  //    Once the two functions took the frame as an argument, passing nothing meant "read the
  //    screen" — so `coordMapOracle(from)` and `coordMapOracle(to)` built the SAME map and
  //    `oracleValuedRekeyed` returned 0 for every pair. Nothing threw and no coordinate
  //    assertion moved; the only thing that noticed was
  //    `F6/C/adoption-would-have-moved-every-coordinate`, whose entire job is to refuse a
  //    negative control that has stopped being negative. An oracle that answers the same
  //    thing for both inputs is not a lenient oracle, it is no oracle at all.
  const m = new Map();
  for (let r = 0; r < vr; r++) for (let c = 0; c < vc; c++) {
    const p = S.getDieIndex(rf, c, r, rf.cols, rf.rows, rf.rotation, rf.side);
    const v = S.getDbCoords(rf, c, r, rf.cols, rf.rows, rf.rotation, rf.side,
                                rf.invertY, rf.startX, rf.startY);
    m.set(`${p.x}_${p.y}`, `${v.x}_${v.y}`);
  }
  return m;
}

// ── THE NEGATIVE CONTROL, and the harness's model of the behaviour that was REMOVED ────────
//
// F6 adopted the reference's dimensions AND physical spec while leaving the placement axes
// (rotation / side / origin / y-invert) alone. `adoptedFrameOf` was the source's statement of
// that set; it is deleted, so the harness states it here. This frame is NEVER applied to a
// sandbox — it is only ever handed to the oracle to answer "how far would the coordinates
// have moved if we had adopted?". A fixture whose answer is 0 proves nothing.
function hypotheticalAdoptedFrame(S, refFrame) {
  const rf = S.resolveFrame(refFrame);
  return {
    ...S.currentFrame(),
    cols: rf.cols, rows: rf.rows,
    waferDia: rf.waferDia, chipX: rf.chipX, chipY: rf.chipY,
    offsetX: rf.offsetX, offsetY: rf.offsetY, edgeMargin: rf.edgeMargin,
  };
}

// How many VALUED cells would have to change their physical key for their stored coordinate to
// survive a frame change. MUST be called while the DOM frame is still the "from" frame.
function oracleValuedRekeyed(S, fromFrame, toFrame) {
  const b = coordMapOracle(S, fromFrame), a = coordMapOracle(S, toFrame);
  const inv = new Map();
  a.forEach((coord, key) => { if (!inv.has(coord)) inv.set(coord, key); });
  let n = 0;
  Object.keys(S.gridData).forEach(k => {
    if ((S.gridData[k] || '') === '') return;          // eachSavableCell's empty test
    const coord = b.get(k);
    if (coord === undefined) return;
    const nk = inv.get(coord);
    if (nk === undefined || nk === k) return;
    n++;
  });
  return n;
}

// The OTHER cost, and the one no reposition could ever have paid: stored coordinates the new
// frame cannot express at all. F6's plan called these `unrepresentable` and refused on them;
// the only alternatives were dropping the cell (deletion) or renumbering it (re-coordination),
// both forbidden. Counted here so a fixture can state what F8 never has to face.
function oracleUnrepresentable(S, fromFrame, toFrame) {
  const b = coordMapOracle(S, fromFrame), a = coordMapOracle(S, toFrame);
  const reachableCoords = new Set(a.values());
  let n = 0;
  Object.keys(S.gridData).forEach(k => {
    const coord = b.get(k);
    if (coord === undefined) return;
    if (!reachableCoords.has(coord)) n++;
  });
  return n;
}

// helper: enumerate every physical key the TARGET renderer will look up, given its frame
function targetReachableKeys(S) {
  const cols = parseInt(S.el.gridCols.value, 10), rows = parseInt(S.el.gridRows.value, 10);
  const rot = S.currentRotation, side = S.currentSide;
  const r90 = (rot === 90 || rot === 270);
  const vc = r90 ? rows : cols, vr = r90 ? cols : rows;
  const out = new Map();
  for (let r = 0; r < vr; r++) for (let c = 0; c < vc; c++) {
    const p = S.getDieIndex(null, c, r, cols, rows, rot, side);
    out.set(`${p.x}_${p.y}`, `${c},${r}`);
  }
  return out;
}

// Reference cells: a deterministic, asymmetric pattern in the reference map's stored x/y space.
function refCellsFor(ref) {
  const cells = [];
  for (let yv = ref.grid_start_y; yv < ref.grid_start_y + 9; yv++) {
    for (let xv = ref.grid_start_x; xv < ref.grid_start_x + 13; xv++) {
      if ((xv * 3 + yv * 7) % 5 !== 0) cells.push({ x: xv, y: yv });   // asymmetric, not a full rect
    }
  }
  return cells;
}

async function scoreAll(src, { verbose = false } = {}) {
  failures = []; compared = 0; evidence.length = 0;

  // The Push payload's own coordinates: physical key -> the `x_y` pair `pushMapData` would
  // serialize for that cell. `eachSavableCell` IS the payload's iterator and `cellObj.x/.y`
  // ARE the values it writes, so this is the payload, not a model of it.
  //
  // 🔴 THIS UNIT OF COMPARISON IS THE WHOLE POINT. The previous version of this block
  //    compared PHYSICAL KEYS and required adoption to succeed — and a physical key is
  //    preserved by construction while the DB coordinate moves. A harness that defines
  //    "the same die" by physical key cannot see P0-1 at all (QA, 2026-07-30).
  const pushPayload = (S) => {
    S.renderGridCanvas();
    const out = {};
    S.eachSavableCell((co) => { out[co.key] = `${co.x}_${co.y}`; });
    return out;
  };

  // ── the two halves of the F8 invariant ────────────────────────────────────────────────
  // 🔴 BOTH must be asserted on the SAME fixture. An assertion that only checks the screen
  //    passes a data change; one that only checks the payload passes a rendering bug.
  //
  // DATA half — `stored coordinate -> value` over EVERY non-empty cell, under the frame given.
  // Total and mask-independent: unlike `pushPayload` it does not drop cells the circle
  // excludes, so it cannot hide a moved coordinate behind a membership change.
  const storedData = (S, frame) => {
    const coordOf = coordMapOracle(S, frame);
    const out = {};
    Object.keys(S.gridData).forEach(k => {
      if ((S.gridData[k] || '') === '') return;
      const c = coordOf.get(k);
      out[c === undefined ? `unaddressable:${k}` : c] = S.gridData[k];
    });
    return out;
  };
  // SCREEN half — `stored coordinate -> screen cell`, built by the REAL renderer. If this is
  // unchanged across a dimension adoption then nothing was re-derived and the fixture is dead.
  const coordToScreen = (S) => {
    S.renderGridCanvas();
    const out = {};
    Object.keys(S.gridCells2D).forEach(rS => Object.keys(S.gridCells2D[rS]).forEach(cS => {
      const co = S.gridCells2D[rS][cS];
      if (!co || (S.gridData[co.key] || '') === '') return;
      out[`${co.x}_${co.y}`] = `${cS},${rS}`;
    }));
    return out;
  };
  const diffCount = (a, b) => {
    const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
    let n = 0;
    keys.forEach(k => { if (a[k] !== b[k]) n++; });
    return n;
  };

  // ── [ⓐ 2026-09-03] WHAT "THE SPEC IS ADOPTED AND THE GRID IS DERIVED" IS SCORED AS ──
  //
  // Owner ruling: 「규격 격자가 당연히 맞지」. A designation takes the reference's PHYSICAL
  // spec and re-derives cols/rows from it. It does NOT copy the dimensions the reference
  // declared -- that was ⓑ, and it was discarded.
  //
  // 🔴 THE DERIVATION FORMULA IS NOT RESTATED HERE. A harness that recomputes
  //    `ceil(2r/chip)+2` holds a COPY of the code and goes red the day the code is refactored
  //    without being wrong. What is scored instead is (a) pure assignment -- the six physical
  //    values equal the reference's -- and (b) the property that actually MEANS "derived":
  //    two references that declare DIFFERENT dimensions but carry the SAME spec must land on
  //    the SAME grid. `REF_B` is `{...REF_A, grid_cols: 41, grid_rows: 51}`, so the pair is
  //    already in the fixtures and the comparison needs no formula at all.
  const specOfEl = (el) => [el.physChipX.value, el.physChipY.value, el.physOffsetX.value,
                            el.physOffsetY.value, el.physWaferDia.value,
                            el.physEdgeMargin.value].map(String);
  const specOfMeta = (m) => [m.phys_chip_x, m.phys_chip_y, m.phys_offset_x, m.phys_offset_y,
                             m.phys_wafer_dia, m.phys_edge_margin].map(String);
  const gridOfEl = (el) => [String(el.gridCols.value), String(el.gridRows.value)];
  // A's grid, stashed by the loop below so B can be compared against it.
  let gridFromSharedSpec = null;

  // 🛑 THE THIRTEEN COORDINATE ASSERTIONS BELOW ARE KNOWN RED AND ARE BEING LEFT ALONE.
  //
  //    「맵 에디터 동작은 소유자가 «정상»으로 판정함 (2026-09-03). 이 단언들은 그 판정과
  //     맞지 않으나, 무엇으로 바꿀지는 «파지 않기로» 결정됨」
  //
  // ⚠️ THIS IS NOT THE "retire what can never be green" CASE. That one applies when the
  //    SUBJECT no longer exists -- the five deleted names in `split_registry_harness.mjs` are
  //    that shape, and an absence check took their place. Here the subject exists and runs;
  //    what stopped is the DIGGING. So they are neither retired nor rewritten: rewriting them
  //    would mean choosing what the contract is, and that is exactly the decision that was
  //    called off.
  //
  //    Three explanations of the numbers were produced in one day and all three were withdrawn
  //    (direction, then arguments, then causation), every one of them a fault in the measuring
  //    rather than in the product. What survived is recorded in `task/axis_and_material_report.md`:
  //    the five facts stated without interpretation, the exact 290/290 round trip, and the
  //    off-grid count agreeing with the product's own log.

  // ══ F8 — a target that already holds cells is DESIGNATED, and nothing moves ══════════
  //
  // ⚠️ THIS BLOCK USED TO ASSERT A REFUSAL. F6 refused here because adopting the reference's
  //    frame would have re-coordinated the painted cells; twelve assertions scored that refusal
  //    and the exact wording of its reason. `61440e6` removed the adoption, so there is nothing
  //    left to refuse: the designation succeeds, the mask is drawn offset, and no coordinate
  //    moves. Six of those twelve are INVERTED below (`not-refused`, `mask-was-built`) because
  //    "this designation does not refuse" is the decision the user actually made and it must go
  //    red if a refusal ever comes back. The other six scored the wording of a sentence that no
  //    longer exists and were DELETED — an assertion that scores a path which no longer exists
  //    is not evidence of anything.
  let wouldHaveMovedSomewhere = 0;
  for (const [label, REF] of [['A(stored==derived)', REF_A], ['B(stored!=derived)', REF_B]]) {
    const cells = refCellsFor(REF);
    const { sandbox: S, el, log } = buildEnv(src, { refMeta: REF, refCells: cells });

    // What the mask would be if the reference were read with the PANEL's frame instead of its
    // own. If this equals the correct mask, the fixture scores nothing.
    const wrongFrame = S.currentFrame();
    const maskWrong = new Set(S.projectCellsToPhys(cells, wrongFrame).keys());
    const maskRight = new Set(S.projectCellsToPhys(cells, S.frameFromMeta(REF)).keys());
    const symDiff = [...maskRight].filter(k => !maskWrong.has(k)).length
                  + [...maskWrong].filter(k => !maskRight.has(k)).length;
    eq(`F6/${label}/fixture-is-live`, true, symDiff > 0,
       `reading the reference with the wrong frame must move cells; symmetric difference = ${symDiff}`);
    evidence.push(`[F6/${label}] wrong-frame reinterpretation moves ${symDiff} of ${maskRight.size} mask cells`);

    // Paint the target: cells loaded under the OLD frame, keyed by physical coords.
    const beforeReach = targetReachableKeys(S);
    const painted = [...beforeReach.keys()].filter((_, i) => i % 7 === 0);
    painted.forEach(k => { S.gridData[k] = 'A'; });

    const frameBefore = { cols: el.gridCols.value, rows: el.gridRows.value,
                          chipX: el.physChipX.value, chipY: el.physChipY.value,
                          rot: S.currentRotation, side: S.currentSide };
    const payloadBefore = pushPayload(S);
    // MASK-INDEPENDENT snapshot: `stored coordinate -> value` over every non-empty cell,
    // savable or not. Captured as a VALUE, so a frame that moves shows up as a difference.
    const storedBefore = storedData(S, S.currentFrame());
    // The negative control, measured BEFORE anything runs and with the source's own per-cell
    // primitives: what F6's adoption would have cost. Two different costs, and A and B do not
    // activate the same one — A's adopted frame cannot ADDRESS those dies at all (so nothing
    // "moves", it is simply lost), B genuinely re-keys. Both are reported.
    const hypo = hypotheticalAdoptedFrame(S, S.frameFromMeta(REF));
    const wouldMove = oracleValuedRekeyed(S, S.currentFrame(), hypo);
    const wouldBeLost = oracleUnrepresentable(S, S.currentFrame(), hypo);

    const res = await S.resolveValidDie({ valid_die_ref: { table: 'ref_tbl', map_id: 'TPL_1' } }, 'dt_map', 'HOME_1');

    // ── INVERTED (was `P0-1/refused`): the designation SUCCEEDS on a painted target ──────
    // The user asked for this twice. A differing reference grid is a fact to be shown, not a
    // reason to withhold the feature — so this assertion goes red the moment a refusal on this
    // path comes back, which is the whole point of inverting rather than deleting it.
    eq(`F6/${label}/F8/not-refused`, 'ref', S.validDieBasis(res), `reason='${res.reason}'`);
    eq(`F6/${label}/F8/no-reason-was-needed`, '', res.reason || '');
    // ── INVERTED (was `P0-1/no-mask-was-built`) ─────────────────────────────────────────
    eq(`F6/${label}/F8/mask-was-built`, true, !!res.keys && res.keys.size > 0,
       `reason='${res.reason}'`);
    // NOTHING in the canvas moved.
    eq(`F6/${label}/F8/gridData-byte-identical`, {},
       Object.fromEntries(Object.keys(S.gridData).filter(k => S.gridData[k] !== 'A').map(k => [k, S.gridData[k]])));
    eq(`F6/${label}/F8/gridData-key-set-unchanged`, painted.length, Object.keys(S.gridData).length);
    // ── [ⓐ] REPLACES `F8/frame-untouched`, WHICH ASSERTED THE OPPOSITE ────────────────
    // Retiring it without a replacement would leave the adoption UNSCORED, so this is a swap.
    eq(`F6/${label}/a/spec-adopted-from-the-reference`, specOfMeta(REF), specOfEl(el));
    // Orientation and origin are still NOT adopted -- that half of the old assertion survives
    // and the transform handles rotation/side on its own.
    eq(`F6/${label}/a/orientation-untouched`, { rot: frameBefore.rot, side: frameBefore.side },
       { rot: S.currentRotation, side: S.currentSide });
    // 🔴 THE DISCRIMINANT, AND IT IS THE PAIR THAT MAKES IT ONE. A and B carry the SAME
    //    physical spec and declare DIFFERENT dimensions (29x25 vs 41x51). Under ⓐ they must
    //    land on the same grid; under ⓑ they would land on their own declarations. On A alone
    //    the two rules agree -- its declaration happens to equal what its spec derives, which
    //    is exactly what `stored==derived` names -- so A cannot decide this and B can.
    if (label.startsWith('A')) {
      gridFromSharedSpec = gridOfEl(el);
      eq(`F6/${label}/a/this-fixture-cannot-tell-the-two-rules-apart`, true,
         String(REF.grid_cols) === gridFromSharedSpec[0]
         && String(REF.grid_rows) === gridFromSharedSpec[1],
         'A is the `stored==derived` fixture; if this ever fails the pair below stops being a '
         + 'discriminant and B alone would be scoring an accident');
    } else {
      eq(`F6/${label}/a/grid-follows-the-SPEC-not-the-declaration`,
         gridFromSharedSpec, gridOfEl(el),
         `B declares ${REF.grid_cols}x${REF.grid_rows} and A declares 29x25 on the SAME spec, `
         + 'so under ⓐ both must land on A\'s grid');
      eq(`F6/${label}/a/and-the-two-declarations-really-differ`, true,
         String(REF.grid_cols) !== gridFromSharedSpec[0]
         || String(REF.grid_rows) !== gridFromSharedSpec[1],
         'if B declared what A derives, the assertion above would be vacuous');
    }
    // ══ [F8] THE WHOLE CONTRACT, IN ONE ASSERTION ═════════════════════════════════════
    // The user asked for exactly one guarantee: a valid-die designation changes NO DB
    // coordinate. The payload's key SET may legitimately shrink — a mask is allowed to put
    // cells outside the valid dies, and `pushMapData`'s `blocking` gate refuses on those
    // rather than deleting them. What may never happen is a key that survives with a
    // DIFFERENT x/y, because that is the silent re-coordination this domain exists to stop.
    // A dimension write sneaking back into `adoptFrameSpec` turns this list non-empty.
    const payloadAfterF8 = pushPayload(S);
    const coordDrift = Object.keys(payloadBefore)
      .filter(k => k in payloadAfterF8 && payloadAfterF8[k] !== payloadBefore[k])
      .slice(0, 8)
      .map(k => `${k}: DB(${payloadBefore[k].replace('_', ',')}) -> DB(${payloadAfterF8[k].replace('_', ',')})`);
    eq(`F6/${label}/F8/no-coordinate-changed`, [], coordDrift);
    eq(`F6/${label}/F8/domain-is-not-empty`, true,
       Object.keys(payloadBefore).filter(k => k in payloadAfterF8).length > 0,
       'if no key survives the mask the assertion above is vacuous');
    // 🔴 CLOSING THE GAP THE LINE ABOVE LEAVES, and it is new. `coordDrift` can only compare
    //    keys present in BOTH payloads, so a coordinate that moved AND left the payload in the
    //    same step would not appear in it. `storedData` is MASK-INDEPENDENT — it walks every
    //    non-empty cell in `gridData` regardless of savability — so it cannot hide a moved
    //    coordinate behind a membership change. This is the assertion the deleted D fixture was
    //    probing at from the other side (D varied the reference DIAMETER, whose adoption moves
    //    the circle without moving a coordinate).
    //
    // ⚠️ AND NOT `payload-key-set-unchanged`, WHICH IS WHAT I FIRST WROTE HERE. It went red on
    //    three fixtures and it was right to: applying a mask legitimately CHANGES which cells
    //    are savable, in both directions — a masked die is valid even off-circle, an unmasked
    //    one is invalid even inside it. That membership change is the designation doing its job.
    //    What must never change is a coordinate's IDENTITY, which is what is asserted instead.
    eq(`F6/${label}/F8/stored-coordinates-preserved-total`,
       storedBefore, storedData(S, S.currentFrame()));
    eq(`F6/${label}/F8/that-population-is-not-empty`, true, Object.keys(storedBefore).length > 0);
    eq(`F6/${label}/F8/membership-did-change`, true,
       Object.keys(payloadBefore).length !== Object.keys(payloadAfterF8).length
       || Object.keys(payloadAfterF8).some(k => !(k in payloadBefore)),
       'a mask that changed no cell\'s savability would make the two assertions above vacuous');
    // INV-F6-2 still holds: every request was a READ
    eq(`F6/${label}/no-metadata-write`, [],
       log.requests.filter(r => /wafer_map_metadata|updates|replace/i.test(r)));

    // ── THE NOTICE — stated once, and it must not claim anything changed ────────────────
    // An offset mask leaves no visible cause (the grid looks fine, only the mask is wrong), so
    // silence would make the operator suspect the data. One info toast, no dialog: reads stay
    // frictionless (UI discipline).
    const notices = log.toasts.filter(x => x.key === 'valid_die_frame_differs');
    eq(`F6/${label}/F8/notice-shown-exactly-once`, 1, notices.length,
       JSON.stringify(log.toasts.map(x => x.msg.slice(0, 44))));
    eq(`F6/${label}/F8/notice-is-info-not-error`, ['info'], notices.map(x => x.kind));
    // ── [ⓐ] REPLACES `notice-says-nothing-changed` ────────────────────────────────
    // That sentence asserted the thing the ruling left OPEN, and a screen must not guarantee
    // what has not been decided. What it says now is what is decided: the two grids, and which
    // one is in use.
    //
    // ⚠️ CONDITIONAL, AND THAT IS THE POINT. The grid half only appears when the reference's
    //    DECLARATION and its DERIVED value differ. On fixture A they are the same numbers
    //    (`stored==derived`), so there is nothing to report and the notice must NOT invent a
    //    difference -- the source says as much: 「파생으로 같아졌다면 말할 것이 없다」.
    const msg0 = notices[0] ? notices[0].msg : '';
    if (String(REF.grid_cols) === gridFromSharedSpec[0]
        && String(REF.grid_rows) === gridFromSharedSpec[1]) {
      eq(`F6/${label}/a/notice-does-NOT-report-a-grid-difference-there-is-none`, false,
         /규격 파생/.test(msg0), msg0);
    } else {
      eq(`F6/${label}/a/notice-names-both-grids-and-which-was-used`, true,
         msg0.includes(`${REF.grid_cols}x${REF.grid_rows}`)
         && msg0.includes(gridFromSharedSpec.join('x')) && /규격 적용/.test(msg0), msg0);
    }
    // 🔴 and it names NO cell population. F6's announcement counted cells it had moved; if any
    //    such count reappears it means something moved again.
    eq(`F6/${label}/F8/notice-counts-no-cells`, false,
       /셀 \d+개/.test(notices[0] ? notices[0].msg : ''), notices[0] && notices[0].msg);

    // ── NEGATIVE CONTROL: what "adopt nothing" is worth on this fixture ────────────────
    // Measured by the oracle, not by a source function — the adoption it models is deleted.
    wouldHaveMovedSomewhere += wouldMove;
    eq(`F6/${label}/F8/negative-control-is-live`, true, wouldMove + wouldBeLost > 0,
       `if adoption would have cost this fixture nothing (moved ${wouldMove}, lost ${wouldBeLost}) `
       + 'it proves nothing about F8');
    evidence.push(`[F6/${label}] designated, ${res.keys ? res.keys.size : 0} mask keys; `
      + `${Object.keys(storedBefore).length} stored coordinates byte-identical (mask-independent) `
      + `and all ${Object.keys(payloadBefore).length} shared Push coordinates unmoved. Had the `
      + `frame been adopted (F6): ${wouldMove} valued cells re-keyed, ${wouldBeLost} stored `
      + `coordinates with no cell at all in the new frame`);
  }

  // The MOVING axis — the same die serialized at a DIFFERENT coordinate, which the Push contrast
  // gate cannot see — must be live in at least one fixture. A only activates the LOSING axis
  // (which that gate does catch), so without this the block would score the cheaper half only.
  eq('F6/F8/moving-axis-is-live-somewhere', true, wouldHaveMovedSomewhere > 0,
     `valued cells that adoption would have re-keyed across both fixtures: ${wouldHaveMovedSomewhere}`);

  // ══ C — THE CASE THE PUSH GATE IS BLIND TO: every coordinate moves, no cell is lost ══════
  //
  // Identical physical spec, grid one larger, ODD -> EVEN. This is the fixture A/B cannot
  // supply: under F6's adoption every stored coordinate shifted by one and NOT ONE CELL left
  // the grid or the circle, so `classifyUnsavableCells` reported nothing and the corruption
  // reached `replace_map` in silence. It is the strongest statement of what "adopt nothing" buys.
  //
  // ⚠️ WHAT THIS BLOCK USED TO ASSERT. `clause3/grid-opened-at-reference-size` required the
  //    editor grid to become 46x46, and seven `clause4/*` assertions scored the reposition
  //    machine that was needed to survive it. All of that is gone. The ones below are the
  //    INVERSIONS — the grid must NOT move, the screen must NOT be re-derived, and the toast
  //    must NOT claim a cell was moved — because each marks a real decision that has to go red
  //    if it is ever reversed. Three announcement assertions (the oracle count, the saved
  //    count, the one-number rule) scored a sentence that no longer exists and were deleted.
  {
    const cells = refCellsFor(REF_C);
    const { sandbox: S, el, log } = buildEnv(src, { refMeta: REF_C, refCells: cells });
    const reach = targetReachableKeys(S);
    [...reach.keys()].forEach(k => { S.gridData[k] = 'A'; });
    // Declare a served set and an F-lock so the "all three caches migrate together" axis is
    // LIVE. Everywhere else `serverCellKeys` is null, which makes that axis unscorable.
    const paintedKeys = Object.keys(S.gridData);
    const servedSample = paintedKeys.slice(0, 40);
    S.serverCellKeys = { table: 'dt_map', mapKey: 'HOME_1', keys: new Set(servedSample) };
    S.loadedIdentity = { table: 'dt_map', mapKey: 'HOME_1' };
    const fLock = paintedKeys.slice(0, 5);
    fLock.forEach(k => S.loadedFCells.add(k));

    const frameBefore = S.currentFrame();
    const dataBefore = storedData(S, frameBefore);
    const screenBefore = coordToScreen(S);
    const payloadBefore = pushPayload(S);
    const dimsBefore = [el.gridCols.value, el.gridRows.value];
    const physBefore = [el.physChipX.value, el.physChipY.value,
                        el.physOffsetX.value, el.physOffsetY.value, el.physWaferDia.value];

    // THE NEGATIVE CONTROL — what adopting this reference would have cost, by the oracle.
    const wouldMove = oracleValuedRekeyed(S, frameBefore,
      hypotheticalAdoptedFrame(S, S.frameFromMeta(REF_C)));
    eq('F6/C/adoption-would-have-moved-every-coordinate', true, wouldMove > 0,
       `wouldMove=${wouldMove} — if this were 0 the fixture could not score F8 at all`);

    const res = await S.resolveValidDie({ valid_die_ref: { table: 'ref_tbl', map_id: 'TPL_1' } }, 'dt_map', 'HOME_1');

    eq('F6/C/allowed', 'ref', S.validDieBasis(res), `reason='${res.reason}'`);
    // ── [ⓐ] THIS FIXTURE'S DECLARATION CAN NEVER BE DERIVED, WHICH IS WHY IT IS HERE ──
    // C declares 46x46 -- EVEN -- and the derivation forces its result odd, so no physical
    // spec whatever can produce it. ⓑ would have opened the grid at 46x46; ⓐ cannot, ever.
    eq('F6/C/a/declared-dimensions-NOT-copied', true,
       String(el.gridCols.value) !== String(REF_C.grid_cols)
       || String(el.gridRows.value) !== String(REF_C.grid_rows),
       `declared ${REF_C.grid_cols}x${REF_C.grid_rows} · editor `
       + `${el.gridCols.value}x${el.gridRows.value}`);
    eq('F6/C/a/reference-really-is-a-different-size', true,
       REF_C.grid_cols !== parseInt(dimsBefore[0], 10),
       'if the reference matched the panel the assertion above would be vacuous');
    // ⚠️ The spec comparison is TRUE HERE BUT NOT DISCRIMINATING: C was built with the
    //    panel's own physical spec, so "adopted" and "untouched" are the same six numbers.
    //    It is kept because it must not become false, and the discrimination is carried by
    //    the A/B pair above and by [ⓐ/independence] below.
    eq('F6/C/a/spec-adopted-from-the-reference', specOfMeta(REF_C), specOfEl(el));
    eq('F6/C/a/and-the-spec-comparison-is-not-a-discriminant-here', physBefore,
       [String(REF_C.phys_chip_x), String(REF_C.phys_chip_y), String(REF_C.phys_offset_x),
        String(REF_C.phys_offset_y), String(REF_C.phys_wafer_dia)],
       'C shares the panel spec by construction; if that ever stops being true this fixture '
       + 'starts scoring adoption and the note above is wrong');

    // ── DATA half: not one stored coordinate changed meaning ──────────────────────────
    const frameAfter = S.currentFrame();
    const dataAfter = storedData(S, frameAfter);
    eq('F6/C/F8/stored-coordinates-preserved', dataBefore, dataAfter);
    eq('F6/C/F8/nothing-became-unaddressable', [],
       Object.keys(dataAfter).filter(k => k.startsWith('unaddressable:')).slice(0, 6));
    eq('F6/C/F8/population-is-not-empty', true, Object.keys(dataBefore).length > 0);
    // 🔴 MOVED HERE 2026-09-03, NOT REPLACED. It used to sit below as
    //    `F8/screen-position-NOT-re-derived` among the assertions about the FRAME, and under
    //    ⓐ its literal claim is false -- the grid changed, so screen positions are re-derived.
    //    But what it was really scoring is 「화면 표기 밀리게 그냥 보여주기」: the cells do not
    //    move, the mask lands offset around them. That is the SAME subject as the two
    //    assertions directly above, and the ruling that decides it -- may a stored coordinate
    //    be re-based -- has not been made. Replacing it in place would have removed it from
    //    the set that ruling is about, and it would have been decided without it.
    const screenAfter = coordToScreen(S);
    const screenMoves = diffCount(screenBefore, screenAfter);
    eq('F6/C/coord/screen-position-unmoved', 0, screenMoves);


    // ── the three caches: untouched, because nothing had to migrate ───────────────────
    // A migration that drops keys turns served rows into "never served" and the cleanup path
    // then offers to delete live rows (invariants ③/④). No migration is the safest form of that.
    eq('F6/C/F8/serverCellKeys-still-resolves', true, S.serverCellKeySet() !== null);
    eq('F6/C/F8/serverCellKeys-size-preserved', servedSample.length, S.serverCellKeySet().size);
    eq('F6/C/F8/loadedFCells-size-preserved', fLock.length, S.loadedFCells.size);
    const strayServed = [...S.serverCellKeySet()].filter(k => !(k in S.gridData));
    eq('F6/C/F8/serverCellKeys-track-gridData', [], strayServed.slice(0, 6));
    const strayF = [...S.loadedFCells].filter(k => !(k in S.gridData));
    eq('F6/C/F8/loadedFCells-track-gridData', [], strayF.slice(0, 6));

    // ── the Push payload: values sit at the same coordinates ─────────────────────────
    const payloadAfter = pushPayload(S);
    const coordVal = (p) => { const o = {}; Object.keys(p).forEach(k => { o[p[k]] = S.gridData[k]; }); return o; };
    const cvB = coordVal(payloadBefore), cvA = coordVal(payloadAfter);
    const clash = Object.keys(cvA).filter(c => c in cvB && cvA[c] !== cvB[c]);
    eq('F6/C/F8/payload-coordinate-values-agree', [], clash.slice(0, 6));

    // ── INVERTED (was `clause4/announced` + `announcement-is-not-an-error`) ───────────
    // The toast is no longer an adoption announcement; it is the offset notice. Its kind can
    // now be pinned to 'info' outright — F6 could not, because a stranded population pushed the
    // same sentence onto the warning branch. Nothing is stranded when nothing is adopted.
    const t = log.toasts.find(x => x.key === 'valid_die_frame_differs');
    eq('F6/C/F8/offset-notice-announced', true, !!t,
       JSON.stringify(log.toasts.map(x => x.msg.slice(0, 44))));
    eq('F6/C/F8/offset-notice-is-info', 'info', t && t.kind);
    // ── [ⓐ] REPLACES `notice-says-nothing-changed` ────────────────────────────────
    // It said the coordinates were kept. That is the question the ruling left open, so the
    // notice no longer claims it and neither does this.
    eq('F6/C/a/notice-names-the-grid-it-used', true,
       /규격 적용/.test(t ? t.msg : ''), t ? t.msg : '(none)');
    eq('F6/C/a/notice-makes-no-promise-about-coordinates', false,
       /좌표는 하나도|그대로입니다/.test(t ? t.msg : ''), t ? t.msg : '(none)');
    // ── [ⓐ] REPLACES `notice-claims-no-cell-moved` ───────────────────────────────────
    // 🔴 THE RULE IT CAME FROM SURVIVES; ITS SIGN FLIPS. Invariant ⑥ was "one number for one
    //    quantity", and F8 sharpened it to "no cell count at all, because no cell moved".
    //    Under ⓐ cells DO move, and the Lead's ruling is that a screen which says nothing
    //    about that is as wrong as one that guarantees the opposite: an absent sentence reads
    //    as "there was nothing to say". So the count must BE there -- and it must still be ONE
    //    number per quantity, which is what this now scores: the re-seated count and the
    //    off-grid count are named separately and neither is a percentage or a range.
    eq('F6/C/a/notice-reports-the-reseat-as-a-count', true,
       /셀 \d+칸 재배치/.test(t ? t.msg : ''), t ? t.msg : '(none)');
    eq('F6/C/a/and-the-off-grid-population-has-its-own-number', true,
       /새 격자 밖 \d+칸/.test(t ? t.msg : ''), t ? t.msg : '(none)');
    eq('F6/C/a/no-percentage-anywhere', false, /%/.test(t ? t.msg : ''), t ? t.msg : '(none)');
    // ...and the two numbers it DOES carry are the two grid sizes, so the operator can see
    // WHICH ONE WAS USED rather than only that they differ.
    eq('F6/C/a/notice-names-both-grids', true,
       /46x46/.test(t ? t.msg : '') && /45x45/.test(t ? t.msg : ''), t ? t.msg : '(none)');

    evidence.push(`[F6/C] ${dimsBefore.join('x')} panel <- ${REF_C.grid_cols}x${REF_C.grid_rows} `
      + `reference (identical physical spec, ODD -> EVEN, so the declaration can NEVER be `
      + `derived): designated; grid now ${gridOfEl(el).join('x')}, `
      + `${Object.keys(dataBefore).length} stored coordinates before, ${screenMoves} screen `
      + `positions changed, serverCellKeys ${servedSample.length} and loadedFCells `
      + `${fLock.length} untouched. ⓑ would have opened it at ${REF_C.grid_cols}x`
      + `${REF_C.grid_rows}, which ${wouldMove} valued cells would have paid for`);
  }

  // ══ E — THE SHAPE REAL DATA TAKES, WITH ALL THREE CACHES DECLARED ═══════════════════
  //
  // Modelled on `bonding_map/4MAIN_TRIM` (33x25, grid_start -4/-3, chip 9.7x13.8, 449 cells,
  // stored x -4..24) against a 29x25 reference. Measured against the live DB with
  // `reposition_regime_probe.mjs` (2026-07-30): under F6's adoption its own 449 cells left 11
  // stored coordinates with NO CELL in the new frame, and 53 in a 27x21 one — coordinates that
  // could only be dropped or renumbered. F8 does not produce that population at all, and this
  // fixture states the number that is no longer at risk.
  //
  // ⚠️ THIS BLOCK USED TO ASSERT A REFUSAL and two properties of `storedCoordRepositionPlan`.
  //    The plan is deleted; the four refusal assertions are INVERTED (this designation is
  //    allowed and builds a mask), and the two plan assertions are DELETED with the function —
  //    the harness's own oracle now carries the liveness number, which is where a negative
  //    control belongs once the thing it models is gone.
  //
  // 🔴 IT ALSO ABSORBS THE OLD G2 POPULATION, which is why G2 is gone rather than merely red.
  //    G2 existed to hold up the `served` term of the reposition plan's `loadBearing` predicate.
  //    With no plan there is no predicate — but the POPULATION it built is still the sharpest
  //    one available for F8: keys the server sent whose value is now `''` (the state
  //    `deleteLegendRow` leaves behind). Those rows are invisible to `gridData` value checks and
  //    are exactly what `replace_map` would delete if `serverCellKeys` ever shrank silently
  //    (invariants ③/④). So they are asserted here instead of being thrown away with G2.
  {
    const TGT = { cols: 33, rows: 25, startX: -4, startY: -3, invertY: false,
                  rotation: 0, side: 'front',
                  dia: 300, chipX: 9.7, chipY: 13.8, offX: 0.1, offY: 0, margin: 3 };
    const REF_E = { grid_cols: 29, grid_rows: 25, grid_start_x: 1, grid_start_y: 1,
                    grid_y_invert: false, rotation: 0, side: 'back',
                    phys_wafer_dia: 300, phys_chip_x: 11, phys_chip_y: 13,
                    phys_offset_x: 0, phys_offset_y: 0, phys_edge_margin: 3 };
    const { sandbox: S, el, log } = buildEnv(src, { refMeta: REF_E, refCells: refCellsFor(REF_E),
                                                    panel: TGT });
    const reach = [...targetReachableKeys(S).keys()];
    // A MIXED population on purpose. All blank (old G2) makes every payload assertion vacuous;
    // all valued (old E) makes the `served`-only axis redundant, because the value already
    // holds each key up. One in seven carries a value; the rest are the legend-deletion state.
    const valued = [];
    reach.forEach((k, i) => {
      if (i % 7 === 0) { S.gridData[k] = 'A'; valued.push(k); }
      else S.gridData[k] = '';
    });
    S.serverCellKeys = { table: 'dt_map', mapKey: 'HOME_1', keys: new Set(reach) };
    S.loadedIdentity = { table: 'dt_map', mapKey: 'HOME_1' };
    const fLock = reach.slice(0, 5);
    fLock.forEach(k => S.loadedFCells.add(k));

    const dimsBefore = [el.gridCols.value, el.gridRows.value];
    const physBefore = [el.physChipX.value, el.physChipY.value, el.physWaferDia.value];
    const gridBefore = Object.keys(S.gridData).length;
    const servedBefore = S.serverCellKeySet().size;
    const payloadBefore = pushPayload(S);
    const storedBefore = storedData(S, S.currentFrame());

    // ── THE NEGATIVE CONTROL, and the reason this fixture is not just another A/B ──────
    // Two DIFFERENT costs, and the second is the one no reposition could ever have paid.
    const hypo = hypotheticalAdoptedFrame(S, S.frameFromMeta(REF_E));
    const wouldRekey = oracleValuedRekeyed(S, S.currentFrame(), hypo);
    const wouldBeLost = oracleUnrepresentable(S, S.currentFrame(), hypo);
    eq('F6/E/adoption-would-have-stranded-coordinates', true, wouldBeLost > 0,
       `wouldBeLost=${wouldBeLost} — stored coordinates the adopted frame cannot express at all; `
       + 'if 0, this fixture is just another A/B and scores nothing extra');
    eq('F6/E/loss-is-partial-not-wholesale', true, wouldBeLost < reach.length,
       `most cells WOULD have survived (${reach.length - wouldBeLost} of ${reach.length}); a `
       + 'fixture where everything fails cannot distinguish a partial loss from a total one');

    const res = await S.resolveValidDie({ valid_die_ref: { table: 'ref_tbl', map_id: 'TPL_1' } }, 'dt_map', 'HOME_1');

    // ── INVERTED (was `E/refused` and its two reason assertions) ──────────────────────
    eq('F6/E/F8/not-refused', 'ref', S.validDieBasis(res), `reason='${res.reason}'`);
    // ── INVERTED (was `E/no-mask`) ───────────────────────────────────────────────────
    eq('F6/E/F8/mask-was-built', true, !!res.keys && res.keys.size > 0, `reason='${res.reason}'`);
    // ── [ⓐ] REPLACES `F8/frame-untouched` and `F8/physical-spec-untouched` ───────────
    // E's reference declares 29x25 on an 11x13 spec while the panel is 33x25 on its own, so
    // this fixture watches the adoption change BOTH halves.
    eq('F6/E/a/spec-adopted-from-the-reference', specOfMeta(REF_E), specOfEl(el));
    eq('F6/E/a/grid-left-the-panel-value', true,
       gridOfEl(el)[0] !== String(dimsBefore[0]) || gridOfEl(el)[1] !== String(dimsBefore[1]),
       `panel ${dimsBefore[0]}x${dimsBefore[1]} · after ${gridOfEl(el).join('x')} — if these `
       + 'were equal the adoption would be unobservable on this fixture');
    eq('F6/E/F8/gridData-key-count-untouched', gridBefore, Object.keys(S.gridData).length);
    eq('F6/E/F8/every-value-survived', valued.length,
       Object.keys(S.gridData).filter(k => (S.gridData[k] || '') !== '').length);

    // ── the G2 axis, restated for F8: the served set must not shrink ─────────────────
    // 🔴 THIS IS THE ONE THAT COSTS ROWS. A served key that stops being served reads as
    //    "never sent by the server", and `replace_map` deletes exactly those rows. Under F6 a
    //    migration could drop them; under F8 nothing migrates, so the assertion is that the set
    //    is IDENTICAL, not merely the same size.
    eq('F6/E/F8/served-set-size-intact', servedBefore, S.serverCellKeySet().size);
    eq('F6/E/F8/served-set-tracks-gridData', [],
       [...S.serverCellKeySet()].filter(k => !(k in S.gridData)).slice(0, 6));
    eq('F6/E/F8/served-only-blank-rows-are-live-here', true,
       [...S.serverCellKeySet()].filter(k => (S.gridData[k] || '') === '' && !S.loadedFCells.has(k)).length > 0,
       'if every served key carried a value or an F-lock this axis would be redundant');
    eq('F6/E/F8/loadedFCells-intact', fLock.length, S.loadedFCells.size);

    // ── and the payload: not one coordinate moved, not one key entered or left ───────
    const payloadAfter = pushPayload(S);
    const drift = Object.keys(payloadBefore)
      .filter(k => k in payloadAfter && payloadAfter[k] !== payloadBefore[k]).slice(0, 8)
      .map(k => `${k}: DB(${payloadBefore[k].replace('_', ',')}) -> DB(${payloadAfter[k].replace('_', ',')})`);
    eq('F6/E/F8/no-coordinate-changed', [], drift);
    // MASK-INDEPENDENT, so a coordinate cannot move out of the payload and out of sight in the
    // same step (see the same pairing on A/B).
    eq('F6/E/F8/stored-coordinates-preserved-total', storedBefore,
       storedData(S, S.currentFrame()));
    eq('F6/E/F8/payload-is-not-empty', true, Object.keys(payloadBefore).length > 0);
    eq('F6/E/F8/notice-shown-exactly-once', 1,
       log.toasts.filter(x => x.key === 'valid_die_frame_differs').length,
       JSON.stringify(log.toasts.map(x => x.msg.slice(0, 44))));

    evidence.push(`[F6/E] 33x25(start -4,-3) panel <- 29x25 reference, the 4MAIN_TRIM shape: `
      + `${reach.length} keys of which ${valued.length} carry a value and all ${servedBefore} are `
      + `served (legend-deletion state). Designated; grid still ${dimsBefore.join('x')}, `
      + `${Object.keys(payloadBefore).length} Push coordinates byte-identical, served set still `
      + `${S.serverCellKeySet().size}. Had F6's adoption run, ${wouldRekey} valued cells would `
      + `have been re-keyed and ${wouldBeLost} stored coordinates would have had NO cell in the `
      + `new frame — droppable or renumberable only, both forbidden`);
  }

  // ⚠️ FIXTURES DELETED WITH THE BEHAVIOUR THEY SCORED, recorded here so the assertion count
  //    drop is explicable rather than merely smaller:
  //
  //    D (45x45 <- 47x47, dia 320) — existed to prove the P0-1 guard was not OVER-STRICT: a
  //      dimension change that moved nothing had to be allowed anyway. There is no guard left to
  //      be over-strict. Its other axis — a reference whose DIAMETER differs, so adoption would
  //      change circle membership WITHOUT moving a coordinate — is covered by
  //      `F8/stored-coordinates-preserved-total` on A/B/E, which is mask-independent and
  //      therefore sees a coordinate move whether or not membership changed with it.
  //      (I first wrote `payload-key-set-unchanged` there and it went red on three fixtures,
  //      correctly: applying a mask is SUPPOSED to change which cells are savable.)
  //
  //    G1 (blank-valued population vs the announced count) — existed because C and E could not
  //      tell `plan.moves.size` from `plan.rekeyedWithValue`, a hundredfold gap inside one
  //      announced sentence. The announcement carries no count now; `F6/C/F8/notice-claims-no-
  //      cell-moved` asserts that no count may ever return.
  //
  //    G2 (the `served` term of the reposition plan's `loadBearing`) — the predicate is gone
  //      with the plan. Its POPULATION was too valuable to lose and now lives in E above.

  // ══ [H5] the reference's DIMENSIONS have a ceiling, and it refuses instead of clamping ══
  //
  // ⚠️ THE RATIONALE CHANGED WHEN THE ADOPTION WENT, AND THE GUARD SURVIVED ON THE OTHER HALF.
  //    F6 needed this because adopting a four-digit dimension ran four full-grid map builds and
  //    a synchronous render. Nothing is adopted now — but `projectCellsToPhys(cells, refFrame)`
  //    still opens a frame window on the REFERENCE's dimensions, and `getWaferBoundingBox`
  //    scans `visualCols x visualRows` inside it to find `minC/minR/maxR`. A 1024x1024 metadata
  //    row is still a 1,048,576-cell scan with no cancel. And the correctness half is now the
  //    stronger one: `frameDimError` also rejects 0, negatives and non-integers, which
  //    `gridDimNum`/`parseInt` would otherwise read as a DIFFERENT frame than the reference
  //    declared — a mask built in an index space nobody chose, which is this domain's whole
  //    failure mode. Both halves are scored below.
  {
    const { sandbox: S } = buildEnv(src, {});
    const f = (c, r) => ({ cols: c, rows: r });
    eq('H5/bound-is-the-editors-own-declared-domain', [1, 100],
       [S.frameDimBounds().min, S.frameDimBounds().max],
       'map_editor.html declares min="1" max="100" on #grid-cols/#grid-rows');
    eq('H5/in-range-is-accepted', '', S.frameDimError(f(45, 45)));
    eq('H5/upper-bound-inclusive', '', S.frameDimError(f(100, 100)));
    eq('H5/four-digit-cols-rejected', true, /grid_cols=1024/.test(S.frameDimError(f(1024, 25))));
    eq('H5/four-digit-rows-rejected', true, /grid_rows=2048/.test(S.frameDimError(f(29, 2048))));
    eq('H5/zero-rejected', true, /grid_cols=0/.test(S.frameDimError(f(0, 25))),
       "gridDimNum's `ov || dflt` silently reads 0 as the default 10, so a 0-dimension reference "
       + 'would build its mask in a 10-wide index space it never declared');
    eq('H5/negative-rejected', true, /grid_rows=-3/.test(S.frameDimError(f(29, -3))));
    eq('H5/non-integer-rejected', true, /grid_cols=45\.5/.test(S.frameDimError(f(45.5, 45))),
       'parseInt reads 45 while the DOM gets 45.5');
    eq('H5/error-names-the-allowed-range', true, /1~100 정수/.test(S.frameDimError(f(1024, 25))));
  }
  // ...and end to end: it refuses BEFORE a single reference cell is fetched.
  {
    const BIG = { ...REF_C, grid_cols: 1024, grid_rows: 1024 };
    const { sandbox: S, el, log } = buildEnv(src, { refMeta: BIG, refCells: refCellsFor(REF_C) });
    [...targetReachableKeys(S).keys()].forEach(k => { S.gridData[k] = 'A'; });
    const before = [el.gridCols.value, el.gridRows.value];
    const gridBefore = Object.keys(S.gridData).length;
    const res = await S.resolveValidDie({ valid_die_ref: { table: 'ref_tbl', map_id: 'TPL_1' } }, 'dt_map', 'HOME_1');
    eq('H5/resolve/refused', 'refused', S.validDieBasis(res), `reason='${res.reason}'`);
    eq('H5/resolve/reason-names-the-dimension', true,
       /grid_cols=1024/.test(res.reason || ''), res.reason);
    eq('H5/resolve/reason-is-not-an-internal-error', false, /내부 오류/.test(res.reason || ''),
       'a hostile metadata row is a DATA problem, not a program defect');
    eq('H5/resolve/nothing-was-clamped', before, [el.gridCols.value, el.gridRows.value]);
    eq('H5/resolve/gridData-untouched', gridBefore, Object.keys(S.gridData).length);
    eq('H5/resolve/no-mask', null, res.keys);
    // 🔴 the guard sits before the CELL fetch — that is what keeps the 4x full-grid traversal
    //    and the synchronous render from ever starting.
    eq('H5/resolve/no-reference-cells-were-fetched', [],
       log.requests.filter(r => /^fetch:/.test(r)));
    evidence.push(`[H5] a 1024x1024 wafer_map_metadata row is refused by name before any cell is `
      + `read (requests: ${log.requests.join(', ')}); the editor frame stays ${before.join('x')}`);
  }

  // ══ THE EMPTY TARGET — it adopts nothing EITHER, and that is the sharper statement ═══
  //
  // The user's own scenario ("기존 프레임이 없으면 어떻게 됨?"). F6 treated this as the path
  // where adoption was safe: a map with no stored cells has no coordinate to lose, so the whole
  // feature lived here. F8 removes the adoption unconditionally, and THIS is where that is
  // hardest to argue and therefore most worth pinning — there is no data at risk, the "obviously
  // better" adopting design looks free, and a future round will re-derive it from first
  // principles exactly as this one did. It must go red when that happens.
  //
  // ⚠️ Three assertions per fixture are INVERSIONS of what F6 asserted here
  //    (`grid-opened-at-reference-size`, `phys-adopted`, `adoption-is-not-a-no-op`). None was
  //    deleted: each marked a real decision, and each now states its opposite.
  let emptyGridFromSharedSpec = null;
  for (const [label, REF] of [['A', REF_A], ['B', REF_B]]) {
    const cells = refCellsFor(REF);
    const { sandbox: S, el, log } = buildEnv(src, { refMeta: REF, refCells: cells });
    const orientBefore = { rot: S.currentRotation, side: S.currentSide,
                           sx: el.gridStartX.value, sy: el.gridStartY.value, inv: el.gridYInvert.checked };
    const wrongFrame = S.currentFrame();
    const dimsBefore = [parseInt(el.gridCols.value, 10), parseInt(el.gridRows.value, 10)];
    const physBefore = [parseFloat(el.physChipX.value), parseFloat(el.physChipY.value),
                        parseFloat(el.physOffsetX.value), parseFloat(el.physOffsetY.value)];
    const beforeReach = targetReachableKeys(S);

    const res = await S.resolveValidDie({ valid_die_ref: { table: 'ref_tbl', map_id: 'TPL_1' } }, 'dt_map', 'HOME_1');

    // the designation resolves instead of refusing on dimensions (unchanged since F6)
    eq(`F6/empty-${label}/basis`, 'ref', S.validDieBasis(res), `reason='${res.reason}'`);
    // ── [ⓐ] REPLACES `F8/grid-NOT-opened-at-reference-size` ───────────────────────────
    // Same pair, same discriminant as the painted loop: this one reuses REF_A and REF_B, which
    // share a spec and declare different dimensions. A cannot tell ⓐ from ⓑ (its declaration
    // IS what its spec derives) and B can.
    eq(`F6/empty-${label}/a/reference-really-is-a-different-size`, true,
       REF.grid_cols !== dimsBefore[0] || REF.grid_rows !== dimsBefore[1],
       'if the reference matched the panel the assertion above would be vacuous');
    if (label === 'A') {
      emptyGridFromSharedSpec = [String(el.gridCols.value), String(el.gridRows.value)];
      eq(`F6/empty-${label}/a/this-fixture-cannot-tell-the-two-rules-apart`, true,
         String(REF.grid_cols) === emptyGridFromSharedSpec[0]
         && String(REF.grid_rows) === emptyGridFromSharedSpec[1],
         'A is the `stored==derived` reference; if this fails the B comparison below stops '
         + 'being a discriminant');
    } else {
      eq(`F6/empty-${label}/a/grid-follows-the-SPEC-not-the-declaration`,
         emptyGridFromSharedSpec, [String(el.gridCols.value), String(el.gridRows.value)],
         `B declares ${REF.grid_cols}x${REF.grid_rows} on A's spec, so under ⓐ it must land `
         + 'where A landed');
      eq(`F6/empty-${label}/a/and-the-two-declarations-really-differ`, true,
         String(REF.grid_cols) !== emptyGridFromSharedSpec[0]
         || String(REF.grid_rows) !== emptyGridFromSharedSpec[1],
         'if B declared what A derives, the assertion above would be vacuous');
    }
    // rotation/side (and origin) are NOT adopted — unchanged since F6, the transform handles them
    eq(`F6/empty-${label}/orientation-untouched`, orientBefore,
       { rot: S.currentRotation, side: S.currentSide,
         sx: el.gridStartX.value, sy: el.gridStartY.value, inv: el.gridYInvert.checked });
    // ── [ⓐ] REPLACES `F8/phys-NOT-adopted`, WHICH SAID THE OPPOSITE ──────────────────
    // 🔴 THE PHYSICAL SPEC IS THE HALF THAT LOOKS HARMLESS AND IS NOT, and that is now the
    //    reason to WATCH it rather than to forbid it. Chip pitch and offsets feed
    //    `getWaferBoundingBox`, whose `minC/minR/maxR` the DB coordinate is computed from -- so
    //    this is the write that carries the whole consequence of ⓐ, and if it ever silently
    //    stops happening the grid stops following the spec with it.
    eq(`F6/empty-${label}/a/spec-adopted-from-the-reference`,
       [REF.phys_chip_x, REF.phys_chip_y, REF.phys_offset_x, REF.phys_offset_y].map(String),
       [el.physChipX.value, el.physChipY.value,
        el.physOffsetX.value, el.physOffsetY.value].map(String));
    eq(`F6/empty-${label}/a/reference-physical-spec-really-differs`, true,
       REF.phys_chip_x !== physBefore[0] || REF.phys_chip_y !== physBefore[1],
       'if the reference shared the panel spec the assertion above would be vacuous');
    eq(`F6/empty-${label}/no-metadata-write`, [],
       log.requests.filter(r => /wafer_map_metadata|updates|replace/i.test(r)));

    // 🔴 A NAMED GATE BEFORE THE KEY-LEVEL BLOCK. Without it, three mutations (M1 / M4 / P1c —
    //    all of which make this path refuse) were "caught" by the harness THROWING on
    //    `[...res.keys]` with `res.keys === null`. Red is red, but a crash is a weaker signal
    //    than a named failure: it stops the whole run, so every later assertion goes unscored and
    //    the report cannot say WHICH invariant the mutation broke.
    eq(`F6/empty-${label}/mask-was-built`, true, !!res.keys,
       `no mask exists, so the key-level assertions below have no domain; reason='${res.reason}'`);
    if (!res.keys) {
      evidence.push(`[F6/empty-${label}] no mask was built — key-level assertions skipped `
        + `(reason: ${res.reason})`);
      continue;
    }

    // KEY->VALUE: every mask key must be reachable by the target renderer.
    const afterReach = targetReachableKeys(S);
    const unreachableAfter = [...res.keys].filter(k => !afterReach.has(k));
    eq(`F6/empty-${label}/mask-fully-reachable-after`, 0, unreachableAfter.length,
       unreachableAfter.slice(0, 6).join(' '));
    // ── INVERTED (was `adoption-is-not-a-no-op`) ──────────────────────────────────────
    // F6 asserted that adoption CHANGED which screen dies the mask marks — that was the proof
    // it had taken effect. The target's index space is untouched now, so that number must be
    // exactly 0. But 0 alone would also be what a designation that did nothing at all produces,
    // so the real statement is the one below it: the mask keys come from the REFERENCE's frame,
    // and reading the same cells through the panel's frame yields a DIFFERENT key set. That
    // difference IS the offset the user asked to see, and it is invariant ① in assertion form —
    // one transform implementation, the reference's own spec swapped in through the frame window.
    const screenBefore = new Set([...res.keys].map(k => beforeReach.get(k)).filter(Boolean));
    const screenAfter = new Set([...res.keys].map(k => afterReach.get(k)).filter(Boolean));
    const dieShift = [...screenAfter].filter(s => !screenBefore.has(s)).length
                   + [...screenBefore].filter(s => !screenAfter.has(s)).length;
    eq(`F6/empty-${label}/F8/target-index-space-unmoved`, 0, dieShift,
       'the designation must not change which screen die any physical key lands on');
    const maskViaPanel = new Set(S.projectCellsToPhys(cells, wrongFrame).keys());
    const offsetKeys = [...res.keys].filter(k => !maskViaPanel.has(k)).length
                     + [...maskViaPanel].filter(k => !res.keys.has(k)).length;
    eq(`F6/empty-${label}/F8/mask-read-through-the-reference-frame`, true, offsetKeys > 0,
       `reading the same reference cells through the PANEL frame yields ${offsetKeys} different `
       + 'keys; if 0, the mask could have been built either way and nothing here is scored');
    // key -> screen cell -> key must close
    // ⚠️ `afterReach.get(k)` IS GUARDED, and the guard is not defensive noise. Mutation N2
    //    (adopt the physical spec but not the dimensions) moves the target's reachable set, so
    //    a mask key stops resolving and this loop threw — the mutation was caught by a CRASH.
    //    A crash aborts the run, so every later assertion goes unscored and the report cannot
    //    say which invariant broke. Counting the miss instead keeps the failure NAMED.
    let roundTripMismatch = 0;
    const cols = parseInt(el.gridCols.value, 10), rows = parseInt(el.gridRows.value, 10);
    for (const k of res.keys) {
      const at = afterReach.get(k);
      if (at === undefined) { roundTripMismatch++; continue; }
      const [c, r] = at.split(',').map(Number);
      const p = S.getDieIndex(null, c, r, cols, rows, S.currentRotation, S.currentSide);
      if (`${p.x}_${p.y}` !== k) roundTripMismatch++;
    }
    eq(`F6/empty-${label}/key-to-cell-to-key`, 0, roundTripMismatch);
    // the mask, not the circle, governs
    const someMask = [...res.keys][0].split('_').map(Number);
    eq(`F6/empty-${label}/mask-governs-inside`, true,
       S.isValidDieAt(null, someMask[0], someMask[1], false, res), 'a masked die stays valid even off-circle');
    eq(`F6/empty-${label}/mask-excludes-unlisted`, false,
       S.isValidDieAt(null, 9999, 9999, true, res), 'a die outside the mask is invalid even inside the circle');

    // an empty target cannot strand anything — nothing is painted to strand
    const u = S.classifyUnsavableCells();
    eq(`F6/empty-${label}/nothing-stranded`, [0, 0],
       [S.pushBlockingCount(u), u.outsideStray.length]);
    // ...and the ONE toast is the offset notice. The dimension difference is a fact about the
    // screen, not about the data, so it is stated on an empty target too — otherwise the
    // operator sees an offset mask on a fresh map with no cause given at all.
    eq(`F6/empty-${label}/F8/only-the-offset-notice`, 1, log.toasts.length,
       JSON.stringify(log.toasts.map(x => `${x.kind}:${x.msg.slice(0, 40)}`)));
    eq(`F6/empty-${label}/F8/notice-is-info`, ['info'], log.toasts.map(x => x.kind));
    evidence.push(`[F6/empty-${label}] panel ${wrongWxH(wrongFrame)} stays ${wrongWxH(wrongFrame)} `
      + `against a ${REF.grid_cols}x${REF.grid_rows} reference; mask ${res.keys.size} keys, all `
      + `reachable, ${offsetKeys} of them different from what the panel frame would have produced `
      + `(that difference is the offset); 0 screen dies moved; 1 info toast`);
  }

  // ══ [MEDIUM-1] ONE quantity for "this many cells make Push refuse" ══════════════════
  //
  // `announceFrameAdoption` used to sum offGrid + outsideRetained + outsideStray and say
  // "Push가 거절합니다" about that total, while `pushMapData` refuses on offGrid +
  // outsideRetained. Measured: the toast said 4 and the Push alert said 2 for one grid.
  //
  // ⚠️ FIVE OF THIS BLOCK'S ASSERTIONS ARE DELETED, NOT INVERTED, AND THE SPLIT IS THE POINT.
  //    They scored the SECOND consumer's sentence — the adoption announcement — which went with
  //    `announceFrameAdoption`. With one consumer left there is no divergence to have, so
  //    "the toast names blocking and not the total" describes nothing and its inverse would
  //    describe nothing either. What survives is the DEFINITION: `pushBlockingCount` still
  //    excludes stray, `pushMapData` still reads it, and the M7b mutation still scores it.
  //
  // 🔴 THE STRAY AXIS IS LIVE HERE AND NOWHERE ELSE. Everywhere else in this harness
  //    `serverCellKeys` is `null`, which forces `stray = 0` by construction. This case declares
  //    a served set, so cells outside the circle that the server never sent classify as stray
  //    and the two sums genuinely differ — without it M7b would fold stray in unnoticed.
  {
    const { sandbox: S, log } = buildEnv(src, { refMeta: REF_B, refCells: refCellsFor(REF_B) });
    S.renderGridCanvas();
    const inside = [], outside = [];
    Object.keys(S.gridCells2D).forEach(r => Object.keys(S.gridCells2D[r]).forEach(c => {
      const co = S.gridCells2D[r][c];
      if (!co) return;
      (co.inside ? inside : outside).push(co.key);
    }));
    // three cells the server DID send (one of them off-circle -> outsideRetained) and two
    // off-circle cells it never sent (-> outsideStray). Both sums are then non-zero AND unequal.
    const served = new Set([inside[0], inside[1], outside[0]]);
    [inside[0], inside[1], outside[0], outside[1], outside[2]].forEach(k => { S.gridData[k] = 'A'; });
    S.serverCellKeys = { table: 'dt_map', mapKey: 'HOME_1', keys: served };
    S.loadedIdentity = { table: 'dt_map', mapKey: 'HOME_1' };
    S.selectedTable = 'dt_map';

    // 🔴 THE EXPECTATIONS ARE DERIVED FROM THE FIXTURE, NOT FROM `pushBlockingCount`.
    //    Asserting the toast against `pushBlockingCount(u)` is self-comparison: fold stray
    //    into that function and both sides move together (measured — that mutation stayed
    //    green). The fixture states its own truth: of the five painted cells, two are inside
    //    (savable), one is outside AND proven served (-> outsideRetained -> blocks), and two
    //    are outside AND proven never served (-> stray -> does NOT block).
    const EXPECT_BLOCKING = 1;
    const EXPECT_STRAY = 2;
    const u = S.classifyUnsavableCells();
    eq('MEDIUM-1/classification-matches-the-fixture',
       { offGrid: 0, retained: EXPECT_BLOCKING, stray: EXPECT_STRAY },
       { offGrid: u.offGrid.length, retained: u.outsideRetained.length, stray: u.outsideStray.length });
    eq('MEDIUM-1/blocking-count-excludes-stray', EXPECT_BLOCKING, S.pushBlockingCount(u));
    eq('MEDIUM-1/stray-axis-is-live', true, EXPECT_STRAY > 0,
       'everywhere else in this harness serverCellKeys is null, which forces stray to 0');
    // ...and a designation does not touch that classification either — the F8 path never calls
    // the classifier at all, so a served set cannot be silently re-partitioned by one.
    const res = await S.resolveValidDie({ valid_die_ref: { table: 'ref_tbl', map_id: 'TPL_1' } }, 'dt_map', 'HOME_1');
    eq('MEDIUM-1/designation-does-not-reclassify', 'ref', S.validDieBasis(res), `reason='${res.reason}'`);
    const u2 = S.classifyUnsavableCells();
    // 🔴 THIS ONE BELONGS TO THE COORDINATE QUESTION, NOT TO THIS SECTION. It reads
    //    "a designation does not re-partition the served set", and under ⓐ the grid changes,
    //    so which cells fall outside the valid dies changes with it. Whether that is correct is
    //    the SAME open ruling as `stored-coordinates-preserved` -- may a designation re-base
    //    what a cell's coordinate means. Left red and named, rather than re-aimed to whatever
    //    the code happens to produce today, which would decide the question by writing down
    //    the answer.
    eq('MEDIUM-1/coord/classification-survives-a-designation',
       EXPECT_BLOCKING, S.pushBlockingCount(u2));
    evidence.push(`[MEDIUM-1] blocking=${EXPECT_BLOCKING} stray=${u.outsideStray.length} `
      + `(offGrid ${u.offGrid.length} / outsideRetained ${u.outsideRetained.length}); `
      + `pushBlockingCount excludes stray, and a valid-die designation leaves the partition at `
      + `blocking=${S.pushBlockingCount(u2)}`);
  }

  // INV-F6-3 — a map with NO valid_die_ref behaves exactly as before: nothing is adopted.
  {
    const { sandbox: S, el, log } = buildEnv(src, { refMeta: REF_B, refCells: refCellsFor(REF_B) });
    const before = [el.gridCols.value, el.gridRows.value, el.physChipX.value, el.physChipY.value];
    const res = await S.resolveValidDie({}, 'dt_map', 'HOME_1');
    eq('F6/no-ref/basis', 'circle', S.validDieBasis(res));
    eq('F6/no-ref/frame-untouched', before,
       [el.gridCols.value, el.gridRows.value, el.physChipX.value, el.physChipY.value]);
    eq('F6/no-ref/no-requests', [], log.requests);
    eq('F6/no-ref/silent', [], log.toasts);
  }

  // INV-F6-4 — a genuinely unresolvable reference still refuses WITH ITS REASON, and does
  // not fall back to the circle or adopt anything.
  {
    const { sandbox: S, el } = buildEnv(src, { refMeta: null });   // reference has no spec
    const before = [el.gridCols.value, el.gridRows.value];
    const res = await S.resolveValidDie({ valid_die_ref: 'TPL_1' }, 'dt_map', 'HOME_1');
    eq('F6/unresolvable/basis', 'refused', S.validDieBasis(res));
    eq('F6/unresolvable/has-reason', true, /규격/.test(res.reason), res.reason);
    eq('F6/unresolvable/frame-untouched', before, [el.gridCols.value, el.gridRows.value]);
  }

  // Chain guard still fires BEFORE any adoption (a 2-hop reference must not resize the grid).
  {
    const REF = { ...REF_B, valid_die_ref: 'OTHER' };
    const { sandbox: S, el } = buildEnv(src, { refMeta: REF, refCells: refCellsFor(REF_B) });
    const before = [el.gridCols.value, el.gridRows.value];
    const res = await S.resolveValidDie({ valid_die_ref: 'TPL_1' }, 'dt_map', 'HOME_1');
    eq('F6/chain/refused', 'refused', S.validDieBasis(res));
    eq('F6/chain/frame-untouched', before, [el.gridCols.value, el.gridRows.value]);
  }

  // ⚠️ `F6/adoption-failed/*` (3 assertions) IS DELETED, NOT INVERTED, and it is the cleanest
  //    delete in this pass. It drove a `freezeGridCols` sandbox whose `el.gridCols` swallowed
  //    writes, so the post-adoption re-check could be shown to catch an adoption that did not
  //    take. Nothing writes to `el.gridCols` on this path any more, so "the write did not land"
  //    is not a state that can exist — there is no proposition left to invert. The sandbox hook
  //    went with it: a stub that swallows frame writes would make F8's whole contract
  //    (`frame-untouched`) untestable by construction.

  // ══ INVARIANT ④ — a TRUNCATED reference is demoted to a failure, never masked from ══════
  //
  // 🔴 NEW. This branch is live in `resolveValidDie` and nothing scored it. A mask built from a
  //    truncated row set is SMALLER than the true valid-die set, and that difference does not
  //    appear on screen — the dies simply are not marked, and the operator reads the map as
  //    having fewer valid dies than it has. Same class as the offset mask, except silent.
  {
    const { sandbox: S, el } = buildEnv(src, { refMeta: REF_B, refCells: refCellsFor(REF_B),
                                               truncate: true });
    const before = [el.gridCols.value, el.gridRows.value];
    const res = await S.resolveValidDie({ valid_die_ref: 'TPL_1' }, 'dt_map', 'HOME_1');
    eq('F6/truncated/refused', 'refused', S.validDieBasis(res), `reason='${res.reason}'`);
    eq('F6/truncated/reason-names-the-truncation', true, /절단/.test(res.reason || ''), res.reason);
    eq('F6/truncated/reason-names-the-limit', true,
       new RegExp(`${S.OVERLAY_CELL_LIMIT}행`).test(res.reason || ''), res.reason);
    eq('F6/truncated/no-mask', null, res.keys,
       'a partial mask is worse than none: it marks real valid dies invalid, invisibly');
    eq('F6/truncated/frame-untouched', before, [el.gridCols.value, el.gridRows.value]);
  }

  // A crash must not wear the costume of an honest refusal. `refuse` guarantees "a refusal
  // carries a non-empty reason", and a raw `ReferenceError: x is not defined` satisfies that
  // guarantee while explaining nothing — worse, it reads as a DATA problem, so the operator
  // goes and edits map data to fix a program defect. Measured when this harness was written:
  // a symbol left out of the extraction list made the chip's reason literally
  // `announceFrameAdoption is not defined` — formally "a non-empty reason", and useless.
  {
    const { sandbox: S } = buildEnv(src, { injectInternalError: true });
    const res = await S.resolveValidDie({ valid_die_ref: 'TPL_1' }, 'dt_map', 'HOME_1');
    eq('F6/internal-error/refused', 'refused', S.validDieBasis(res));
    eq('F6/internal-error/named-as-internal', true, /내부 오류/.test(res.reason), res.reason);
    eq('F6/internal-error/says-not-a-data-problem', true, /데이터의 문제가 아니라/.test(res.reason));
    // The raw detail is preserved, not swallowed — the evidence must survive (PRIMITIVES §1).
    eq('F6/internal-error/keeps-the-raw-detail', true, /someHelper is not defined/.test(res.reason));
    evidence.push(`[F6/internal-error] reason = "${res.reason.slice(0, 110)}…"`);
  }
  // ...and an EXPECTED failure must still pass its authored message through unchanged, so the
  // classification cannot quietly relabel real data failures as program defects.
  {
    const { sandbox: S } = buildEnv(src, { injectDataError: true });
    const res = await S.resolveValidDie({ valid_die_ref: 'TPL_1' }, 'dt_map', 'HOME_1');
    eq('F6/data-error/refused', 'refused', S.validDieBasis(res));
    eq('F6/data-error/not-relabelled-internal', false, /내부 오류/.test(res.reason), res.reason);
    eq('F6/data-error/message-verbatim', true, /HTTP 503/.test(res.reason));
  }

  // Stale generation must not touch the editor frame — nor SPEAK.
  //
  // 🔴 THE SECOND ASSERTION IS NEW AND IT IS THE ONLY ONE WITH TEETH LEFT. F6's stale guard was
  //    scored by the frame: a superseded resolution that ran to completion resized the grid.
  //    Nothing resizes the grid now, so `frame-untouched` passes even with the guard deleted —
  //    it went from an assertion to a decoration without anyone touching it. What a stale
  //    resolution can still do is TALK: announce an offset for a reference the user has already
  //    navigated away from, about a grid difference that no longer exists on screen. That is the
  //    observable the guard now protects, and mutation M5 puts it under load.
  {
    const { sandbox: S, el, log } = buildEnv(src, { refMeta: REF_B, refCells: refCellsFor(REF_B) });
    const before = [el.gridCols.value, el.gridRows.value];
    const p = S.resolveValidDie({ valid_die_ref: 'TPL_1' }, 'dt_map', 'HOME_1');
    S.validDieResolveSeq++;                 // a newer resolution starts while this one awaits
    await p;
    eq('F6/stale/frame-untouched', before, [el.gridCols.value, el.gridRows.value],
       'a superseded resolution must never resize the grid the user is looking at');
    eq('F6/stale/silent', [], log.toasts.map(x => x.msg.slice(0, 44)),
       'a superseded resolution must not narrate a screen the user has already left');
    // ...and the same designation on a LIVE generation does speak, or the assertion above
    // would pass for a resolution that simply never got that far.
    {
      const { sandbox: L, log: liveLog } = buildEnv(src, { refMeta: REF_B, refCells: refCellsFor(REF_B) });
      await L.resolveValidDie({ valid_die_ref: 'TPL_1' }, 'dt_map', 'HOME_1');
      eq('F6/stale/the-live-generation-does-speak', 1, liveLog.toasts.length,
         JSON.stringify(liveLog.toasts.map(x => x.msg.slice(0, 44))));
    }
  }

  // == O - THE ALIGNMENT ALARM WATCHES THE ORIGIN CELL, NOT THE GRID SIZE ==============
  //
  // SPECIMEN, real data: `MID_01 <- 4MAIN_DT`. Both grids are 23x23 and the physical specs
  // match, so the OLD guard - which compared dimensions - said nothing at all, while the
  // starts (1,1) vs (-4,-3) put the mask 5 columns and 4 rows off. Equal size is not equal
  // alignment; what decides whether the same DB coordinate names the same die is the ORIGIN.
  //
  // The predicate is built from `projectCellsToPhys` - the same function that builds the mask
  // itself - applied to the single cell DB(0,0) under each frame. Physical keys, not canvas
  // columns: a reference that differs only by ROTATION really does overlap (the physical key
  // is rotation-invariant) while its canvas column does not, so a canvas comparison would
  // raise a false alarm. That case is asserted below too.
  const ALIGN_PANEL = { cols: 23, rows: 23, startX: -4, startY: -3, invertY: false,
                        rotation: 0, side: 'front',
                        dia: 300, chipX: 11, chipY: 13, offX: 0, offY: 0, margin: 3 };
  const ALIGN_META = { grid_cols: 23, grid_rows: 23, grid_y_invert: false,
                       rotation: 0, side: 'front',
                       phys_wafer_dia: 300, phys_chip_x: 11, phys_chip_y: 13,
                       phys_offset_x: 0, phys_offset_y: 0, phys_edge_margin: 3 };
  const alignNotices = (log) => log.toasts.filter(t => t.key === 'valid_die_frame_differs');

  // -- O1: the specimen. Equal dimensions, different origin -> the alarm MUST fire ---------
  {
    const REF = { ...ALIGN_META, grid_start_x: 1, grid_start_y: 1 };
    const { sandbox: S, el, log } = buildEnv(src, { refMeta: REF, refCells: refCellsFor(REF),
                                                    panel: ALIGN_PANEL });
    [...targetReachableKeys(S).keys()].forEach(k => { S.gridData[k] = 'A'; });
    const payloadBefore = pushPayload(S);

    // THE AXIS THE OLD GUARD WATCHED IS DEAD ON THIS FIXTURE - that is the point of it.
    eq('O/specimen/dimensions-are-EQUAL', true,
       REF.grid_cols === ALIGN_PANEL.cols && REF.grid_rows === ALIGN_PANEL.rows,
       'if the dimensions differed the old guard would have fired and this fixture would '
       + 'score nothing new');
    // ...and the misalignment is real: the mask lands on different dies than an aligned
    // reference would. Measured with the shipped projector, both frames.
    const maskRight = new Set(S.projectCellsToPhys(refCellsFor(REF), S.frameFromMeta(REF)).keys());
    const maskHere = new Set(S.projectCellsToPhys(refCellsFor(REF), S.currentFrame()).keys());
    const symDiff = [...maskRight].filter(k => !maskHere.has(k)).length
                  + [...maskHere].filter(k => !maskRight.has(k)).length;
    eq('O/specimen/misalignment-is-real', true, symDiff > 0,
       `the reference read under the two frames differs by ${symDiff} cells`);

    const res = await S.resolveValidDie({ valid_die_ref: { table: 'ref_tbl', map_id: 'TPL_1' } },
                                        'dt_map', 'HOME_1');
    eq('O/specimen/still-designated', 'ref', S.validDieBasis(res), `reason='${res.reason}'`);

    const notes = alignNotices(log);
    eq('O/specimen/alarm-fired-exactly-once', 1, notes.length,
       JSON.stringify(log.toasts.map(t => t.msg.slice(0, 60))));
    eq('O/specimen/alarm-tracks-the-actual-misalignment', symDiff > 0 ? 1 : 0, notes.length);
    eq('O/specimen/alarm-is-info', ['info'], notes.map(t => t.kind));
    // The offset is MEASURED and named -- as a screen movement in 칸/행, not as the origin gap.
    // 🔴 THE TWO ARE DIFFERENT QUANTITIES AND THE SOURCE SAYS SO: the origin gap is a fact
    //    about frame alignment, the screen shift is how far the cells actually moved. A live
    //    case had (1,1) and (-3,-2) for the same designation. So this asserts the shape of the
    //    screen term rather than a transcribed pair -- pinning the pair here would be a second
    //    copy of a number the product computes.
    eq('O/specimen/a/alarm-names-a-measured-screen-shift', true,
       /화면 \d+칸·\d+행 이동|화면 이동 없음/.test(notes[0] ? notes[0].msg : ''),
       notes[0] && notes[0].msg);
    eq('O/specimen/alarm-names-both-origins', true,
       /1,1/.test(notes[0] ? notes[0].msg : '') && /-4,-3/.test(notes[0] ? notes[0].msg : ''),
       notes[0] && notes[0].msg);
    // It is an ALARM, not a refusal, and not a screen move (item 4 is a separate round).
    // Only keys present in BOTH: applying a mask legitimately changes which cells are
    // savable (the F8 blocks above assert that at length). What may never change is a
    // surviving key's COORDINATE.
    const payloadAfterO = pushPayload(S);
    eq('O/specimen/no-surviving-coordinate-moved', [],
       Object.keys(payloadBefore)
         .filter(k => k in payloadAfterO && payloadAfterO[k] !== payloadBefore[k]).slice(0, 6));
    eq('O/specimen/shared-population-is-not-empty', true,
       Object.keys(payloadBefore).filter(k => k in payloadAfterO).length > 0);
    // ── [ⓐ] REPLACES `O/specimen/frame-untouched` ─────────────────────────────────────
    // This is the fixture that shows the ruling's consequence at its sharpest: the reference
    // and the panel carry an IDENTICAL physical spec and both DECLARE 23x23, yet 23x23 is not
    // what that spec derives. Under ⓐ the editor sits on the derived value, and the two maps
    // stop sharing an index space even though nothing about them differs.
    eq('O/specimen/a/origin-untouched',
       [String(ALIGN_PANEL.startX), String(ALIGN_PANEL.startY)],
       [el.gridStartX.value, el.gridStartY.value].map(String));
    eq('O/specimen/a/grid-left-the-declared-value', true,
       String(el.gridCols.value) !== String(ALIGN_META.grid_cols)
       || String(el.gridRows.value) !== String(ALIGN_META.grid_rows),
       `declared ${ALIGN_META.grid_cols}x${ALIGN_META.grid_rows} · editor `
       + `${el.gridCols.value}x${el.gridRows.value}`);
    eq('O/specimen/a/and-the-spec-was-identical-on-both-sides', true,
       ALIGN_META.phys_chip_x === ALIGN_PANEL.chipX
       && ALIGN_META.phys_chip_y === ALIGN_PANEL.chipY
       && ALIGN_META.phys_wafer_dia === ALIGN_PANEL.dia,
       'if the two specs differed, the grid moving would be unremarkable; it is remarkable '
       + 'BECAUSE they are the same six numbers');
    evidence.push(`[O/specimen] MID_01-shaped 23x23 start(-4,-3) <- 4MAIN_DT-shaped 23x23 `
      + `start(1,1): dimensions EQUAL so the old guard was silent; the origin cell differs and `
      + `the alarm names 5\uce78\u00b74\ud589. ${symDiff} mask cells land on a different die; `
      + `${Object.keys(payloadBefore).length} Push coordinates unmoved`);
  }

  // -- O2: an ALIGNED reference must stay SILENT (a false alarm is its own defect) ---------
  {
    const REF = { ...ALIGN_META, grid_start_x: ALIGN_PANEL.startX, grid_start_y: ALIGN_PANEL.startY };
    const { sandbox: S, log } = buildEnv(src, { refMeta: REF, refCells: refCellsFor(REF),
                                                panel: ALIGN_PANEL });
    const res = await S.resolveValidDie({ valid_die_ref: { table: 'ref_tbl', map_id: 'TPL_1' } },
                                        'dt_map', 'HOME_1');
    eq('O/aligned/designated', 'ref', S.validDieBasis(res), `reason='${res.reason}'`);
    // ── [ⓐ] SPLIT. It expected TOTAL silence; under ⓐ that is the wrong test, and the
    //    fixture is the reason why: the reference and the panel share one physical spec and
    //    both DECLARE 23x23, but 23x23 is not what that spec derives (29x25 is). So they are
    //    aligned in ORIGIN and not in GRID, and the notice must say the second while staying
    //    quiet about the first. One assertion could not express that -- it read the two as one
    //    fact and called the whole notice a false alarm.
    const alignedMsg = (alignNotices(log)[0] || { msg: '' }).msg;
    eq('O/aligned/a/no-ORIGIN-term-the-origins-do-match', false,
       /최솟값|START/.test(alignedMsg), alignedMsg || '(none)');
    eq('O/aligned/a/but-the-grid-difference-IS-reported', true,
       /규격 파생/.test(alignedMsg) && /규격 적용/.test(alignedMsg),
       'the operator saved 23x23 and the editor opened 29x25 ― that has to be said');
    // ...and silence is CORRECT here, by the same measured property used on the other two.
    const cellsA = refCellsFor(REF);
    const symDiffA = (() => {
      const a = new Set(S.projectCellsToPhys(cellsA, S.frameFromMeta(REF)).keys());
      const b = new Set(S.projectCellsToPhys(cellsA, S.currentFrame()).keys());
      return [...a].filter(k => !b.has(k)).length + [...b].filter(k => !a.has(k)).length;
    })();
    eq('O/aligned/alarm-tracks-the-actual-misalignment', 0, symDiffA,
       'an aligned reference must read identically under either frame, or the silence above '
       + 'is luck rather than correctness');
  }

  // -- O3: THE ALARM'S GENERAL PROPERTY, on a rotation-only difference -------------------
  //
  // I FIRST WROTE THIS BLOCK ASSERTING SILENCE, ON THE REASONING THAT THE PHYSICAL KEY IS
  // ROTATION-INVARIANT SO A ROTATION-ONLY REFERENCE MUST OVERLAP. The harness said otherwise
  // and the harness was right: `getCanvasCellFromDb` anchors DB coordinates on
  // `getWaferBoundingBox(null, rotation, side)`, whose bounding box is itself rotation-dependent, so
  // the DB -> physical mapping is NOT rotation-invariant even though canvas -> physical is.
  // A reference stored at 90 really does name a different die by DB(0,0), and the mask really
  // does land offset. Measured below rather than assumed.
  //
  // So the assertion is the PROPERTY, applied to all three fixtures: the alarm fires exactly
  // when the reference, read under this map's frame instead of its own, would land on a
  // different set of dies. That is the definition of "the mask appears offset", it is computed
  // with the shipped projector, and it makes both a missed alarm and a false one go red.
  {
    const REF = { ...ALIGN_META, grid_start_x: ALIGN_PANEL.startX, grid_start_y: ALIGN_PANEL.startY,
                  rotation: 90 };
    const { sandbox: S, log } = buildEnv(src, { refMeta: REF, refCells: refCellsFor(REF),
                                                panel: ALIGN_PANEL });
    eq('O/rot-only/axis-is-live', true, REF.rotation !== ALIGN_PANEL.rotation);
    const cells = refCellsFor(REF);
    const maskRight = new Set(S.projectCellsToPhys(cells, S.frameFromMeta(REF)).keys());
    const maskHere = new Set(S.projectCellsToPhys(cells, S.currentFrame()).keys());
    const symDiff = [...maskRight].filter(k => !maskHere.has(k)).length
                  + [...maskHere].filter(k => !maskRight.has(k)).length;
    const res = await S.resolveValidDie({ valid_die_ref: { table: 'ref_tbl', map_id: 'TPL_1' } },
                                        'dt_map', 'HOME_1');
    eq('O/rot-only/designated', 'ref', S.validDieBasis(res), `reason='${res.reason}'`);
    eq('O/rot-only/alarm-tracks-the-actual-misalignment', symDiff > 0 ? 1 : 0,
       alignNotices(log).length,
       `${symDiff} of ${maskRight.size} mask cells land on a different die under this map's frame`);
    evidence.push(`[O/rot-only] identical origin and spec, reference stored at rot 90: `
      + `${symDiff} of ${maskRight.size} mask cells land on a different die, and the alarm `
      + `fired ${alignNotices(log).length} time(s) — DB -> physical is NOT rotation-invariant, `
      + `because the bounding box that anchors it is not`);
  }

  // == P - A GEOMETRY PRESET DOES NOT MOVE THE SCREEN (specimen: aa123_a + 4A) ========
  //
  // THE DEFECT THIS BLOCK REPLACES. `applyPresetObject` ended with
  //        if (preset.rotation !== undefined) currentRotation = preset.rotation;
  //        if (preset.side !== undefined) currentSide = preset.side;
  //    and ALL FIVE stored presets declare rot 0 / front. Applying any of them to a rotated
  //    or back-side map reset the orientation, `getDieIndex` reads both, and every
  //    cell's physical key - hence the coordinate Push writes - changed. Measured on
  //    `aa123_a` + `4A`: byte-identical physical spec, unchanged grid, unchanged bounding
  //    box, 173 of 187 dies renumbered, and Push proceeded, because the contrast gate counts
  //    only cells that leave the grid or the circle and none did.
  //
  // THE FIXTURE'S PANEL ALREADY CARRIES 4A's PHYSICAL SPEC, and that is the whole design.
  //    If the panel's chip/diameter differed, applying 4A would legitimately move coordinates
  //    (a different pitch is a different bounding box) and "nothing moved" would be false for
  //    a reason that has nothing to do with orientation. Identical spec isolates the ONE axis
  //    under test - which is also exactly the shape the specimen had.
  {
    // The real preset, copied from server/config/maps.json (`custom_1784890104442`).
    const PRESET_4A = { name: '4A', phys_wafer_dia: 300.0, phys_chip_x: 11.0, phys_chip_y: 13.0,
                        phys_offset_x: 0.0, phys_offset_y: 0.0, phys_edge_margin: 3.0,
                        rotation: 0, side: 'front', is_custom: true };
    // 29x25 is what `applyPhysicalGeometry` derives from that spec, so the preset's own call
    // to it cannot change the dimensions either. rot 90 + back keeps BOTH writes live.
    const PANEL_4A = { cols: 29, rows: 25, startX: 2, startY: 1, invertY: false,
                       rotation: 90, side: 'back',
                       dia: PRESET_4A.phys_wafer_dia, chipX: PRESET_4A.phys_chip_x,
                       chipY: PRESET_4A.phys_chip_y, offX: 0, offY: 0, margin: 3 };
    const { sandbox: S, el, log } = buildEnv(src, { panel: PANEL_4A });
    [...targetReachableKeys(S).keys()].forEach(k => { S.gridData[k] = 'A'; });

    const payloadBefore = pushPayload(S);
    const dimsBefore = [el.gridCols.value, el.gridRows.value].map(String);
    const physBefore = [el.physWaferDia.value, el.physChipX.value, el.physChipY.value,
                        el.physOffsetX.value, el.physOffsetY.value, el.physEdgeMargin.value].map(String);

    // -- THE NEGATIVE CONTROL, run by doing what the deleted lines did ----------------
    // Not a model: the two writes are literally performed, the REAL renderer re-runs, and the
    // REAL Push iterator is read. If this number were 0 the fixture would prove nothing.
    S.currentRotation = PRESET_4A.rotation; S.currentSide = PRESET_4A.side;
    S.boundingBoxCache = {};
    const payloadCtl = pushPayload(S);
    const wouldMove = Object.keys(payloadBefore)
      .filter(k => k in payloadCtl && payloadCtl[k] !== payloadBefore[k]).length;
    const wouldLeave = Object.keys(payloadBefore).filter(k => !(k in payloadCtl)).length;
    eq('P/negative-control-is-live', true, wouldMove + wouldLeave > 0,
       `writing the preset's orientation moves ${wouldMove} and strands ${wouldLeave} of `
       + `${Object.keys(payloadBefore).length} Push coordinates; at 0 this fixture is dead`);
    // put the operator's orientation back and confirm the screen returns to where it was
    S.currentRotation = PANEL_4A.rotation; S.currentSide = PANEL_4A.side;
    S.boundingBoxCache = {};
    eq('P/control-is-reversible', payloadBefore, pushPayload(S),
       'if restoring the orientation did not restore the payload the comparison below is unsound');

    // -- now the shipped path --------------------------------------------------------
    S.applyPresetObject(PRESET_4A);
    const payloadAfter = pushPayload(S);

    eq('P/orientation-untouched', [PANEL_4A.rotation, PANEL_4A.side],
       [S.currentRotation, S.currentSide]);
    eq('P/preset-really-declares-a-different-orientation', true,
       PRESET_4A.rotation !== PANEL_4A.rotation && PRESET_4A.side !== PANEL_4A.side);
    eq('P/no-coordinate-moved', [],
       Object.keys(payloadBefore)
         .filter(k => k in payloadAfter && payloadAfter[k] !== payloadBefore[k])
         .slice(0, 8)
         .map(k => `${k}: DB(${payloadBefore[k].replace('_', ',')}) -> DB(${payloadAfter[k].replace('_', ',')})`));
    eq('P/no-cell-left-the-payload', [],
       Object.keys(payloadBefore).filter(k => !(k in payloadAfter)).slice(0, 8));
    eq('P/payload-is-not-empty', true, Object.keys(payloadBefore).length > 0);
    // the GEOMETRY half did apply - a preset that applies nothing at all would pass the above
    eq('P/geometry-applied', physBefore,
       [el.physWaferDia.value, el.physChipX.value, el.physChipY.value,
        el.physOffsetX.value, el.physOffsetY.value, el.physEdgeMargin.value].map(String));
    eq('P/dimensions-unchanged', dimsBefore, [el.gridCols.value, el.gridRows.value].map(String));

    // -- the ignored declaration is stated once, and it claims nothing moved ----------
    const notes = log.toasts.filter(t => /\ubc29\ud5a5\(.*\)\uc740 \uc801\uc6a9\ud558\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4/.test(t.msg));
    eq('P/ignored-orientation-stated-once', 1, notes.length,
       JSON.stringify(log.toasts.map(t => t.msg.slice(0, 44))));
    eq('P/notice-is-info', ['info'], notes.map(t => t.kind));
    eq('P/notice-names-the-screen-orientation', true,
       /90\u00b0 \u00b7 \ub4b7\uba74/.test(notes[0] ? notes[0].msg : ''), notes[0] && notes[0].msg);
    eq('P/notice-claims-no-cell-moved', true,
       /\uc88c\ud45c\ub3c4 \uadf8\ub300\ub85c/.test(notes[0] ? notes[0].msg : ''), notes[0] && notes[0].msg);

    evidence.push(`[P] aa123_a-shaped map (29x25, rot 90 - back, chip 11x13) + preset 4A `
      + `(rot 0 - front, IDENTICAL physical spec): ${Object.keys(payloadBefore).length} Push `
      + `coordinates, 0 moved and 0 stranded. Had the two orientation writes stayed, `
      + `${wouldMove} would have been renumbered and ${wouldLeave} would have left the payload`);
  }

  // A preset whose declared orientation MATCHES the screen says nothing - the notice is about
  // a declaration being ignored, and nothing is ignored when the two already agree. Without
  // this, the toast would fire on the ordinary rot-0 case, which is most of them.
  {
    const { sandbox: S, log } = buildEnv(src);          // PANEL_BEFORE is rot 0 / front
    S.applyPresetObject({ name: 'CORE', phys_chip_x: 7, phys_chip_y: 7, rotation: 0, side: 'front' });
    eq('P/agreeing-orientation-is-silent', [],
       log.toasts.filter(t => /\ubc29\ud5a5\(.*\)\uc740 \uc801\uc6a9\ud558\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4/.test(t.msg)).map(t => t.msg));
    eq('P/agreeing-orientation-left-the-screen-alone', [0, 'front'], [S.currentRotation, S.currentSide]);
  }
  // A preset that declares NO orientation at all (the standard branch's no-mask spec is one)
  // is silent too - there is nothing to report.
  {
    const { sandbox: S, log } = buildEnv(src, { panel: { ...PANEL_BEFORE, rotation: 270, side: 'back' } });
    S.applyPresetObject({ phys_wafer_dia: 300, phys_chip_x: 1, phys_chip_y: 1,
                          phys_offset_x: 0, phys_offset_y: 0, phys_edge_margin: 3 });
    eq('P/undeclared-orientation-is-silent', [],
       log.toasts.filter(t => /\ubc29\ud5a5\(.*\)\uc740 \uc801\uc6a9\ud558\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4/.test(t.msg)).map(t => t.msg));
    eq('P/undeclared-orientation-left-the-screen-alone', [270, 'back'], [S.currentRotation, S.currentSide]);
  }

  // ══ F5c ═════════════════════════════════════════════════════════════════════════════
  const OK_BODY = {
    table: 'dt_map', map_key: 'L1', canonical_map_key: 'L1', status: 'ok',
    preset_key: 'core_std',
    preset: { name: 'CORE', phys_wafer_dia: 300, phys_chip_x: 11, phys_chip_y: 13,
              phys_offset_x: 1, phys_offset_y: 2, phys_edge_margin: 3, rotation: 180, side: 'back' },
    matched_by: { stage: 'pattern', rule: 'r1', lot: 'L', product_code: null },
    lookup: { declared: false, status: 'not_declared', product_code: null }, detail: '',
  };
  {
    const { sandbox: S, el, log } = buildEnv(src, { routingBody: OK_BODY });
    const r = await S.applyRoutedPreset('dt_map', 'L1');
    eq('F5c/ok/applied', 'ok', r && r.status);
    eq('F5c/ok/phys-written', [300, 11, 13, 1, 2, 3],
       [parseFloat(el.physWaferDia.value), parseFloat(el.physChipX.value), parseFloat(el.physChipY.value),
        parseFloat(el.physOffsetX.value), parseFloat(el.physOffsetY.value), parseFloat(el.physEdgeMargin.value)]);
    // ── INVERTED. It used to read `orientation-written` and expect [180,'back'] ────────
    // 🔴 That assertion scored the two writes in `applyPresetObject` that renumbered 173 of
    //    187 dies on `aa123_a` + preset `4A`. Orientation is the operator's — it belongs to
    //    the rotate/flip controls — so a preset, routed or chosen, applies GEOMETRY ONLY.
    //    The inverse is asserted rather than the assertion deleted: the write coming back is
    //    exactly what has to go red.
    eq('F5c/ok/orientation-NOT-written', [0, 'front'], [S.currentRotation, S.currentSide],
       'a geometry preset states geometry; rotation/side stay with the operator');
    eq('F5c/ok/orientation-axis-is-live', true,
       OK_BODY.preset.rotation !== 0 || OK_BODY.preset.side !== 'front',
       'if the routed preset declared the screen orientation the assertion above is vacuous');
    eq('F5c/ok/ignored-orientation-is-stated-once', 1,
       log.toasts.filter(t => /방향\(.*\)은 적용하지 않았습니다/.test(t.msg)).length,
       JSON.stringify(log.toasts.map(t => t.msg.slice(0, 44))));
    eq('F5c/ok/one-request', 1, log.requests.filter(x => /preset-routing/.test(x)).length);
    eq('F5c/ok/announced', true, log.toasts.some(t => /규격을 라우팅했습니다/.test(t.msg)));
  }
  // INV-F5c-1 — nothing is applied for any non-ok status, and a miss is not shouted.
  for (const st of ['not_declared', 'no_match', 'meta_present', 'unresolvable', 'preset_missing']) {
    const body = { ...OK_BODY, status: st, preset_key: null, preset: null };
    const { sandbox: S, el, log } = buildEnv(src, { routingBody: body });
    const before = [el.physChipX.value, el.physChipY.value, el.gridCols.value, S.currentRotation, S.currentSide];
    const r = await S.applyRoutedPreset('dt_map', 'L1');
    eq(`F5c/${st}/not-applied`, null, r);
    eq(`F5c/${st}/panel-untouched`, before,
       [el.physChipX.value, el.physChipY.value, el.gridCols.value, S.currentRotation, S.currentSide]);
    eq(`F5c/${st}/not-shouted`, [], log.toasts);
  }
  // INV-F5c-2, client half. The server answers `meta_present` with a null preset, but the
  // client must not depend on that: a non-ok status that STILL carries a preset body must
  // apply nothing. Status is the gate; the presence of a body is not permission.
  for (const st of ['meta_present', 'no_match', 'preset_missing']) {
    const body = { ...OK_BODY, status: st, preset_key: 'core_std' };   // preset body left in place
    const { sandbox: S, el, log } = buildEnv(src, { routingBody: body });
    const before = [el.physChipX.value, el.physChipY.value, S.currentRotation, S.currentSide];
    eq(`F5c/${st}-with-body/not-applied`, null, await S.applyRoutedPreset('dt_map', 'L1'));
    eq(`F5c/${st}-with-body/panel-untouched`, before,
       [el.physChipX.value, el.physChipY.value, S.currentRotation, S.currentSide]);
    eq(`F5c/${st}-with-body/not-shouted`, [], log.toasts);
  }

  // A malformed 'ok' with no preset body must also apply nothing (server contract says it
  // cannot happen — the client must not depend on that).
  {
    const { sandbox: S, el, log } = buildEnv(src, { routingBody: { ...OK_BODY, preset: null } });
    const before = el.physChipX.value;
    eq('F5c/ok-without-preset/not-applied', null, await S.applyRoutedPreset('dt_map', 'L1'));
    eq('F5c/ok-without-preset/panel-untouched', before, el.physChipX.value);
    eq('F5c/ok-without-preset/not-shouted', [], log.toasts);
  }
  // HTTP failure = "could not check", and the fallback is today's behaviour, silently.
  {
    const { sandbox: S, el, log } = buildEnv(src, { routingHttpOk: false });
    const before = el.physChipX.value;
    eq('F5c/http-fail/not-applied', null, await S.applyRoutedPreset('dt_map', 'L1'));
    eq('F5c/http-fail/panel-untouched', before, el.physChipX.value);
    eq('F5c/http-fail/not-shouted', [], log.toasts);
  }
  // No identity = no request at all.
  {
    const { sandbox: S, log } = buildEnv(src, { routingBody: OK_BODY });
    eq('F5c/no-key/no-request', null, await S.applyRoutedPreset('dt_map', ''));
    eq('F5c/no-key/zero-requests', 0, log.requests.length);
    eq('F5c/no-table/zero-requests', null, await S.applyRoutedPreset('', 'L1'));
  }

  // ══ Structural: the call site (INV-F5c-2 / INV-F5c-3) ═══════════════════════════════
  // Executing loadExistingMap is out of reach here (it drives the whole editor), so the
  // guard is asserted on the source. Stated as structural on purpose — the browser E2E
  // network log is what actually proves the request count.
  {
    const calls = (src.match(/\bapplyRoutedPreset\s*\(/g) || []).length - 1;   // minus the declaration
    eq('F5c/call-site/exactly-one', 1, calls);
    eq('F5c/call-site/guarded-by-absent-meta', true,
       /if \(!loadedGridMeta\) \{\s*\n\s*await applyRoutedPreset\(/.test(src),
       'the routing call must sit inside `if (!loadedGridMeta)` — stored spec > routing');
  }

  if (verbose) evidence.forEach(e => console.log('  ' + e));
  return { failures: failures.slice(), compared };
}

// ── Mutations: put a defective version back and require the harness to go RED ────────────
//
// ⚠️ TWENTY-ONE MUTATIONS WERE REMOVED WITH THE CODE THEY DESCRIBED, AND THAT IS THE POINT.
//    A mutation whose search string no longer occurs reports `MUTATION DID NOT APPLY` — a
//    line that scrolls past looking like any other. A mutation that applies to code nothing
//    asserts on reports `STILL GREEN`. This repository has been bitten by both (`cb8f01a`, and
//    again this week when a rename made a search string stop matching and a run reported 18 of
//    19 applied). So a mutation that no longer describes a defect is deleted WITH its
//    assertion, never left in the list to inflate the count:
//
//      M1 M2 M4        adoptFrameSpec's dimension write / rotation adoption / the call itself
//      M3              the post-adoption dimension re-check
//      M6 M7 M9        announceFrameAdoption's stranded warning, blocking sum, and render order
//      P1a P1b P1c P1j the reposition guard and its `loadBearing` predicate
//      P1e P1f P1g P1h P1i  plan/apply, the self-comparison, the two cache migrations, silence
//      P1d             the coordinate-cost unit (lived inside dbCoordsByPhysKey)
//      H2a H2b H2c H2d the announced count
//      H4a H4b         the refusal wording
//
//    M5 is RETARGETED rather than deleted: the stale guard still exists, but the thing it
//    guards changed from "do not resize the grid" to "do not narrate a screen the user left".
//    Six mutations are NEW (N1..N6) because F8 introduced defects of its own that nothing
//    described — chiefly that the adoption can simply be put back.
const MUTATIONS = [
  // ── [N] the F8 contract itself: every way the adoption can come back ──────────────────
  ['N1 the designation adopts the reference dimensions again (F6, restored)',
   s => s.replace(`      dimsDiffer = { here: \`\${hereResolved.cols}x\${hereResolved.rows}\`,`,
                  `      if (el.gridCols) el.gridCols.value = refResolved.cols;
      if (el.gridRows) el.gridRows.value = refResolved.rows;
      boundingBoxCache = {};
      dimsDiffer = { here: \`\${hereResolved.cols}x\${hereResolved.rows}\`,`)],
  ['N2 the designation adopts the reference PHYSICAL spec only (dimensions left alone)',
   s => s.replace(`      dimsDiffer = { here: \`\${hereResolved.cols}x\${hereResolved.rows}\`,`,
                  `      applyPresetObject({ phys_chip_x: refResolved.chipX, phys_chip_y: refResolved.chipY,
        phys_offset_x: refResolved.offsetX, phys_offset_y: refResolved.offsetY,
        phys_wafer_dia: refResolved.waferDia });
      boundingBoxCache = {};
      dimsDiffer = { here: \`\${hereResolved.cols}x\${hereResolved.rows}\`,`)],
  ['N3 the mask is built with the PANEL frame instead of the reference frame (invariant ①)',
   s => s.replace('    const keys = new Set(projectCellsToPhys(cells, refFrame).keys());',
                  '    const keys = new Set(projectCellsToPhys(cells, currentFrame()).keys());')],
  ['N4 the offset goes UNANNOUNCED (an offset mask with no visible cause)',
   s => s.replace('    if ((originDiffer || dimsDiffer) && !stale()) {', '    if (false) {')],
  ['N5 a differing grid REFUSES again (the behaviour the user reversed, twice)',
   s => s.replace(`      dimsDiffer = { here: \`\${hereResolved.cols}x\${hereResolved.rows}\`,
                     there: \`\${refResolved.cols}x\${refResolved.rows}\` };`,
                  `      return refuse(ref, \`격자 치수가 다릅니다 — 참조 \${refResolved.cols}x\${refResolved.rows}\`);`)],
  ['N6 truncation is masked from instead of demoted to a failure (invariant ④)',
   s => s.replace('    if (rows.length > OVERLAY_CELL_LIMIT) {', '    if (false) {')],
  // ── the stale generation guard, RETARGETED to what it now protects ────────────────────
  //
  // 🔴 IT REMOVES BOTH COPIES, AND MEASURING THAT WAS A FINDING. There are two stale checks on
  //    this path — an early `return` inside the dimension branch and a `!stale()` on the toast —
  //    and they are REDUNDANT: removing either one alone leaves the run silent, so the first
  //    version of this mutation reported STILL GREEN. Neither copy is independently scored,
  //    which is worth knowing; what IS scored is the guard, so the mutation removes the guard.
  ['M5 the stale-generation guard is removed (a superseded resolution narrates a screen the user left)',
   s => s
     .replace('    if (oHere.x !== oThere.x || oHere.y !== oThere.y) {\n      if (stale()) return validDie;\n',
              '    if (oHere.x !== oThere.x || oHere.y !== oThere.y) {\n')
     .replace('      // \ub0a1\uc740 \ud574\uc11d\uc740 \ud654\uba74\uc744 \uac74\ub4dc\ub9ac\uc9c0 \uc54a\ub294\ub2e4 \u2014 \uc774\uc81c \ud654\uba74\uc744 \ubc14\uafb8\uc9c0 \uc54a\uc73c\ubbc0\ub85c \ud1a0\uc2a4\ud2b8\ub3c4 \ub0b4\uc9c0 \uc54a\ub294\ub2e4.\n      if (stale()) return validDie;\n',
              '')
     .replace('    if ((originDiffer || dimsDiffer) && !stale()) {', '    if (originDiffer || dimsDiffer) {')],

  // ── [MEDIUM-1] the ONE definition of "this many cells make Push refuse" ────────────────
  ['M7b pushBlockingCount folds stray in (the measured 4-vs-2 divergence, put back)',
   s => s.replace('  return u.offGrid.length + u.outsideRetained.length;\n}',
                  '  return u.offGrid.length + u.outsideRetained.length + u.outsideStray.length;\n}')],
  // ── [H5] the reference dimension ceiling ──────────────────────────────────────────────
  ['H5a the ceiling is removed (a hostile metadata row reaches getWaferBoundingBox)',
   s => s.replace('    const dimErr = frameDimError(refFrame);', "    const dimErr = '';")],
  ['H5b frameDimBounds raises the ceiling past the editor\'s declared domain (input max="100")',
   s => s.replace('function frameDimBounds() { return { min: 1, max: 100 }; }',
                  'function frameDimBounds() { return { min: 1, max: 10000 }; }')],
  ['H5c the ceiling accepts non-integers and 0 (parseInt/gridDimNum divergence returns)',
   s => s.replace('  const bad = (n, name) => (!Number.isInteger(n) || n < b.min || n > b.max) ? `${name}=${n}` : \'\';',
                  '  const bad = (n, name) => (n > b.max) ? `${name}=${n}` : \'\';')],
  // Placement, not presence: the refusal still happens and still names the dimension, but a
  // hostile metadata row has already made the editor read the reference map's rows.
  ['H5d the dimension guard is moved AFTER the reference cell fetch (the read happens anyway)',
   s => s
     .replace('    const dimErr = frameDimError(refFrame);', "    const dimErr = '';")
     .replace('    const cells = [];\n    rows.forEach(row => {',
              '    const lateErr = frameDimError(refFrame);\n'
              + '    if (lateErr) return refuse(ref, `${ref.table} · ${ref.mapKey}: ${lateErr}`);\n'
              + '    const cells = [];\n    rows.forEach(row => {')],
  // ── the catch: a crash must not wear the costume of an honest refusal ─────────────────
  ['M9b the catch passes any raw e.message off as an operator reason (crash as refusal)',
   s => s.replace(`    const internal = !!e && (e.name === 'TypeError' || e.name === 'ReferenceError'
      || e.name === 'RangeError' || e.name === 'SyntaxError');`,
                  '    const internal = false;')],
  ['M9c the catch labels EVERY failure internal (real data errors relabelled as defects)',
   s => s.replace(`    const internal = !!e && (e.name === 'TypeError' || e.name === 'ReferenceError'
      || e.name === 'RangeError' || e.name === 'SyntaxError');`,
                  '    const internal = true;')],
  // -- [O] the alignment alarm: the axis it watches, and every way it can go blind ------
  ['O1 the origin axis is removed (the dimension-only guard, restored)',
   s => s.replace('    if (oHere.x !== oThere.x || oHere.y !== oThere.y) {', '    if (false) {')],
  ['O2 the origin difference is computed but never announced (silent again at the toast)',
   s => s.replace('    if ((originDiffer || dimsDiffer) && !stale()) {',
                  '    if (dimsDiffer && !stale()) {')],
  ['O3 the origins are compared as DECLARED STARTS instead of through the projector',
   s => s.replace('    const oHere = originPhysOf(currentFrame());\n    const oThere = originPhysOf(refFrame);',
                  '    const oHere = { x: hereResolved.startX, y: hereResolved.startY };\n'
                  + '    const oThere = { x: refResolved.startX, y: refResolved.startY };')],
  ['O4 the dimension axis is dropped when the origin axis is added (one blind spot for another)',
   s => s.replace('    if (refResolved.cols !== hereResolved.cols || refResolved.rows !== hereResolved.rows) {',
                  '    if (false) {')],
  ['O5 the alarm fires on every designation (a false alarm on an aligned reference)',
   s => s.replace('    if (oHere.x !== oThere.x || oHere.y !== oThere.y) {', '    if (true) {')],
  // -- [P] the two orientation writes, and every way they can come back ----------------
  //
  // The anchor is the line that REPLACED them. If `applyPresetObject` is reshaped so that
  // `const declaredRot` no longer appears verbatim, these report MUTATION DID NOT APPLY
  // rather than passing silently.
  ['P1 applyPresetObject writes the preset rotation again (half the aa123_a defect)',
   s => s.replace('  const declaredRot = (preset.rotation === undefined || preset.rotation === null)',
                  '  if (preset.rotation !== undefined) currentRotation = preset.rotation;\n'
                  + '  const declaredRot = (preset.rotation === undefined || preset.rotation === null)')],
  ['P2 applyPresetObject writes the preset side again (the other half)',
   s => s.replace('  const declaredRot = (preset.rotation === undefined || preset.rotation === null)',
                  '  if (preset.side !== undefined) currentSide = preset.side;\n'
                  + '  const declaredRot = (preset.rotation === undefined || preset.rotation === null)')],
  ['P3 both writes restored verbatim (the shipped defect, put back)',
   s => s.replace('  const declaredRot = (preset.rotation === undefined || preset.rotation === null)',
                  '  if (preset.rotation !== undefined) currentRotation = preset.rotation;\n'
                  + '  if (preset.side !== undefined) currentSide = preset.side;\n'
                  + '  const declaredRot = (preset.rotation === undefined || preset.rotation === null)')],
  ['P4 the ignored declaration goes unstated (a preset silently drops what it declared)',
   s => s.replace('  if (ignoredRot !== null || ignoredSide !== null) {', '  if (false) {')],
  ['P5 the notice fires whenever an orientation is declared, agreeing or not (toast on every preset)',
   s => s.replace('  if (ignoredRot !== null || ignoredSide !== null) {',
                  '  if (declaredRot !== null || declaredSide !== null) {')],
  // ── F5c ───────────────────────────────────────────────────────────────────────────────
  ['M10 applyRoutedPreset applies on any status',
   s => s.replace("  if (status !== 'ok' || !resp.preset) {", '  if (false) {')],
  ['M11 applyRoutedPreset applies the preset before checking the status',
   s => s.replace("  const status = resp && resp.status ? String(resp.status) : '';",
                  "  if (resp && resp.preset) applyPresetObject(resp.preset);\n  const status = resp && resp.status ? String(resp.status) : '';")],
];

const base = await scoreAll(SRC0, { verbose: true });
console.log(`\n${base.failures.length === 0 ? '✓' : '✗'} baseline: ${base.compared} assertions, `
  + `${base.failures.length} failure(s)`);
// H1 protocol: the runner reads this line to tell "red with N assertions" from a crash.
console.log(`ASSERTIONS ${base.compared} ${base.failures.length}`);
base.failures.forEach(f => console.log('   ✗ ' + f));

if (process.argv.includes('--mutate')) {
  console.log('\n── MUTATIONS (each must turn the harness RED) ──');
  // 🔴 APPLIED IS COUNTED SEPARATELY FROM CAUGHT, AND CAUGHT IS SPLIT BY HOW.
  //    A mutation that did not apply scores nothing while looking like a passing line, and a
  //    mutation "caught" by the harness THROWING is a weaker signal than a named assertion: the
  //    crash aborts the run, so every later assertion in that pass went unscored and the report
  //    cannot say which invariant broke. Both are reported as their own number so neither hides
  //    inside a total.
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
  }
  console.log(`\nmutations: ${MUTATIONS.length} declared · ${applied} applied · ${notApplied} did `
    + `not apply | caught by a NAMED assertion ${byAssertion} · caught only by a crash ${byCrash} `
    + `· undetected ${stillGreen}`);
  if (byCrash > 0) console.log(`  ~ unnamed (crash-only) detection: ${crashed.join(' | ')}`);
  if (skipped.length) console.log(`  ! did not apply: ${skipped.join(' | ')}`);
  if (green.length) console.log(`  ✗ undetected: ${green.join(' | ')}`);
  if (stillGreen > 0 || notApplied > 0) {
    console.log(`\n✗ ${stillGreen + notApplied} mutation(s) scored nothing.`);
    process.exit(1);
  }
}

process.exit(base.failures.length === 0 ? 0 : 1);
