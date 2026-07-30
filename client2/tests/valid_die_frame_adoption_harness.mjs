/**
 * F6 + F5c harness — executes the NEW branches of map_editor.js in a vm sandbox.
 *
 * Read-only against client2/. Functions are sliced out of the source text (same technique as
 * contracts/map_seam/client_harness.mjs) and evaluated with DOM/network stubs, so the branch
 * that ships is the branch that is scored.
 *
 * Run:  node client2/tests/valid_die_frame_adoption_harness.mjs [--mutate]
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
const SRC0 = readFileSync(SRC_PATH, 'utf8');

const die = (m) => { console.error(`HARNESS FAILURE: ${m}\n(Nothing was compared.)`); process.exit(2); };

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
  'physNum', 'gridDimNum', 'withPhysFrame',
  'getPhysicalCoords', 'getCellFromPhysicalCoords', 'getCellFromVisualCoords',
  'getTransformedPhysicalConfig', 'getScreenShift', 'isCellInsideWaferFast', 'getWaferBoundingBox',
  'frameFromMeta', 'currentFrame', 'resolveFrame', 'frameAxesKey',
  'adoptFrameSpec',                       // F6 — the new adoption primitive
  'applyPresetObject', 'applyPhysicalGeometry',
  'applyRoutedPreset',                    // F5c — the new routing consumer
  'parseValidDieRef', 'validDieBasis', 'isValidDieAt', 'validDieChainError', 'validDieRefDisplay',
  'projectCellsToPhys', 'resolveValidDie',
  // The stranded-cell announcement and the ONE classifier it must share with the Push gate.
  // `renderGridCanvas` is sliced too, NOT modelled: `classifyUnsavableCells`'s domain is
  // whatever the real renderer put in `gridCells2D`, and that domain is wider than the visual
  // grid (it draws to -1x..2x). A harness that re-derived "off the grid" by hand measured 190
  // where the shipped classifier measures 27 — the exact divergence this round forbids.
  'announceFrameAdoption', 'classifyUnsavableCells', 'eachSavableCell', 'serverCellKeySet',
  'renderGridCanvas', 'getVisualCoords', 'cellFillColor', 'isProtectedFCell',
  // [P0-1] the coordinate-cost measurement the guard is built on, and the ONE definition
  // of "this many cells make Push refuse" (MEDIUM-1).
  'dbCoordsByPhysKey', 'adoptedFrameOf', 'adoptionCoordinateCost', 'pushBlockingCount',
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
// getPhysicalCoords and the whole offset term would then be unscored (a fixture that kills its
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
// C — THE PURE P0-1 SHAPE, and the reason it needs its own fixture. Identical physical spec,
//     grid ONE larger. Measured on the shipped functions: every stored coordinate moves by one
//     (`DB(-2,-2) -> DB(-3,-3)`) and NOT ONE CELL IS LOST — so a guard that only counted lost
//     cells, or one that compared physical keys, would let this through in silence. A and B
//     both lose cells, which is why they cannot score that axis.
const REF_C = {
  grid_cols: 46, grid_rows: 46, grid_start_x: 0, grid_start_y: 0, grid_y_invert: false,
  rotation: 0, side: 'front',
  phys_wafer_dia: PANEL_BEFORE.dia, phys_chip_x: PANEL_BEFORE.chipX, phys_chip_y: PANEL_BEFORE.chipY,
  phys_offset_x: PANEL_BEFORE.offX, phys_offset_y: PANEL_BEFORE.offY,
  phys_edge_margin: PANEL_BEFORE.margin,
};
// D — a dimension change that moves NOTHING (45x45 -> 47x47 with a larger diameter; measured
//     moved=0 lost=0). The guard must ALLOW it: the judgement is coordinate movement, not
//     "the dimensions differ". Without this fixture an over-strict guard passes unnoticed.
const REF_D = { ...REF_C, grid_cols: 47, grid_rows: 47, phys_wafer_dia: 320 };

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
  const el = {
    gridCols: makeInput(PANEL_BEFORE.cols), gridRows: makeInput(PANEL_BEFORE.rows),
    gridStartX: makeInput(PANEL_BEFORE.startX), gridStartY: makeInput(PANEL_BEFORE.startY),
    gridYInvert: { checked: PANEL_BEFORE.invertY },
    physWaferDia: { value: String(PANEL_BEFORE.dia), querySelector: () => ({}), appendChild() {} },
    physChipX: makeInput(PANEL_BEFORE.chipX), physChipY: makeInput(PANEL_BEFORE.chipY),
    physOffsetX: makeInput(PANEL_BEFORE.offX), physOffsetY: makeInput(PANEL_BEFORE.offY),
    physEdgeMargin: makeInput(PANEL_BEFORE.margin),
    gridCanvas: { getBoundingClientRect: () => ({ width: 700, height: 700 }) },
    // Paint sink: every 2D-context method is a no-op, every property writable. The render
    // loop's DECISIONS (getPhysicalCoords / isValidDieAt / isCellInsideWaferFast) are real.
    waferCanvas: { width: 0, height: 0, getContext: () => new Proxy({}, {
      get: (t, k) => (k in t ? t[k] : (t[k] = () => {})), set: (t, k, v) => (t[k] = v, true) }) },
    showAnnotations: { checked: false },
    validDieRefKey: makeInput(''), validDieRefTable: makeInput(''), validDieRefList: null,
  };
  const sandbox = {
    // `debug` was MISSING, and that is not a cosmetic gap: the [1e] zero-stranded path
    // calls console.debug, so the PRIMARY case (an empty target adopts silently) threw
    // `console.debug is not a function`, got classified as an internal error, and the three
    // F6/empty-target assertions have been RED — i.e. unscored — since that path landed.
    console: { warn() {}, info() {}, error() {}, log() {}, debug() {} },
    el,
    physFrameOverride: null,
    boundingBoxCache: {},
    currentRotation: PANEL_BEFORE.rotation,
    currentSide: PANEL_BEFORE.side,
    gridData: {},
    validDie: { basis: 'circle', keys: null, reason: '', ref: null, raw: undefined },
    validDieResolveSeq: 0,
    selectedTable: 'dt_map',
    loadedIdentity: null,
    tableSchema: { column_types: {} },
    API_BASE: '',
    OVERLAY_CELL_LIMIT: 2000,
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
    showToast: (msg, kind) => log.toasts.push({ msg: String(msg), kind }),
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
      return { ok: true, status: 200, json: async () => ({ data: (opts.refCells || []).map(c => ({ data: { x: { value: c.x }, y: { value: c.y } } })) }) };
    },
  };
  // Drives the "adoption could not take" path: the cols input still READS (so nothing throws
  // and the branch is reached honestly) but swallows the write. The post-adoption re-check is
  // then the only thing between the user and a mask built in a different index space.
  if (opts.freezeGridCols) {
    const frozen = String(PANEL_BEFORE.cols);
    el.gridCols = { get value() { return frozen; }, set value(_v) { /* write swallowed */ } };
  }
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

// helper: enumerate every physical key the TARGET renderer will look up, given its frame
function targetReachableKeys(S) {
  const cols = parseInt(S.el.gridCols.value, 10), rows = parseInt(S.el.gridRows.value, 10);
  const rot = S.currentRotation, side = S.currentSide;
  const r90 = (rot === 90 || rot === 270);
  const vc = r90 ? rows : cols, vr = r90 ? cols : rows;
  const out = new Map();
  for (let r = 0; r < vr; r++) for (let c = 0; c < vc; c++) {
    const p = S.getPhysicalCoords(c, r, cols, rows, rot, side);
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

  // ══ F6 + [P0-1] a target that already holds cells REFUSES the adoption ══════════════
  let movedSomewhere = 0;
  for (const [label, REF] of [['A(stored==derived)', REF_A], ['B(stored!=derived)', REF_B]]) {
    const cells = refCellsFor(REF);
    const { sandbox: S, el, log } = buildEnv(src, { refMeta: REF, refCells: cells });

    // What the mask would be if the reference were read with the WRONG frame (the target's
    // pre-adoption panel). If this equals the correct mask, the fixture scores nothing.
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

    const res = await S.resolveValidDie({ valid_die_ref: { table: 'ref_tbl', map_id: 'TPL_1' } }, 'dt_map', 'HOME_1');

    // ── THE GUARD ────────────────────────────────────────────────────────────────────
    eq(`F6/${label}/P0-1/refused`, 'refused', S.validDieBasis(res), `reason='${res.reason}'`);
    eq(`F6/${label}/P0-1/reason-names-the-coordinates`, true,
       /저장될 좌표가 함께 움직입니다/.test(res.reason || ''), res.reason);
    eq(`F6/${label}/P0-1/reason-offers-the-route`, true,
       /📂 Load/.test(res.reason || ''), res.reason);
    eq(`F6/${label}/P0-1/no-mask-was-built`, null, res.keys);
    // nothing on the editor moved — not the dimensions, not the physical spec
    eq(`F6/${label}/P0-1/frame-untouched`, frameBefore,
       { cols: el.gridCols.value, rows: el.gridRows.value,
         chipX: el.physChipX.value, chipY: el.physChipY.value,
         rot: S.currentRotation, side: S.currentSide });
    // ...and the Push payload is byte-identical, key -> value
    eq(`F6/${label}/P0-1/push-payload-unchanged`, payloadBefore, pushPayload(S));
    // INV-F6-2 still holds: every request was a READ
    eq(`F6/${label}/no-metadata-write`, [],
       log.requests.filter(r => /wafer_map_metadata|updates|replace/i.test(r)));

    // ── NEGATIVE CONTROL: what the refusal prevented ─────────────────────────────────
    // A fresh sandbox, the same paint set, and adoption FORCED through `adoptFrameSpec`.
    // The damage is counted by the shipped Push iterator — NOT by `adoptionCoordinateCost`,
    // because scoring the guard against its own arithmetic is self-comparison.
    const { sandbox: F } = buildEnv(src, { refMeta: REF, refCells: cells });
    painted.forEach(k => { F.gridData[k] = 'A'; });
    const fBefore = pushPayload(F);
    F.adoptFrameSpec(F.frameFromMeta(REF));
    const fAfter = pushPayload(F);
    let movedCoords = 0, droppedCoords = 0;
    const samples = [];
    Object.keys(fBefore).forEach(k => {
      if (!(k in fAfter)) { droppedCoords++; return; }
      if (fAfter[k] !== fBefore[k]) {
        movedCoords++;
        if (samples.length < 3) samples.push(`${k}: DB(${fBefore[k].replace('_', ',')}) -> DB(${fAfter[k].replace('_', ',')})`);
      }
    });
    // Both fixtures must lose SOMETHING under forced adoption, or the guard's refusal here is
    // vacuous. Which axis is live differs and that is worth stating: A only DROPS cells (the
    // new frame cannot address those dies), B genuinely MOVES 60 Push coordinates while
    // keeping the die — the silent-corruption shape P0-1 is about. The cross-fixture
    // assertion below requires the moving axis to be live in at least one.
    eq(`F6/${label}/P0-1/negative-control-is-live`, true, movedCoords + droppedCoords > 0,
       'if forced adoption changed no Push coordinate at all, this fixture proves nothing');
    movedSomewhere += movedCoords;
    // and the contrast gate really is blind to it — the reason the guard has to exist
    const uForced = F.classifyUnsavableCells();
    evidence.push(`[F6/${label}] P0-1 negative control: forcing the adoption moves `
      + `${movedCoords} Push coordinates and drops ${droppedCoords}; the contrast gate sees `
      + `blocking=${F.pushBlockingCount(uForced)} `
      + `(offGrid ${uForced.offGrid.length} / outsideRetained ${uForced.outsideRetained.length}); `
      + `guard refused, payload unchanged for all ${Object.keys(payloadBefore).length} cells`
      + (samples.length ? ` | ${samples.join(' ; ')}` : ''));
  }

  // The MOVING axis — the same die serialized at a different DB coordinate — must be live in
  // at least one fixture, or this whole block only ever scored the dropping axis (which the
  // Push contrast gate already caught before this round).
  eq('F6/P0-1/moving-axis-is-live-somewhere', true, movedSomewhere > 0,
     `total Push coordinates that forced adoption moves across both fixtures: ${movedSomewhere}`);

  // ══ C — MOVED BUT NOTHING LOST: the axis A and B cannot score ═══════════════════════
  {
    const cells = refCellsFor(REF_C);
    const { sandbox: S, el } = buildEnv(src, { refMeta: REF_C, refCells: cells });
    const reach = targetReachableKeys(S);
    [...reach.keys()].forEach(k => { S.gridData[k] = 'A'; });
    const payloadBefore = pushPayload(S);
    const dims = [el.gridCols.value, el.gridRows.value];

    // the cost, measured by the shipped Push iterator on a FORCED adoption (independent of
    // `adoptionCoordinateCost`, which is the thing under test)
    const { sandbox: F } = buildEnv(src, { refMeta: REF_C, refCells: cells });
    [...reach.keys()].forEach(k => { F.gridData[k] = 'A'; });
    const fBefore = pushPayload(F);
    F.adoptFrameSpec(F.frameFromMeta(REF_C));
    const fAfter = pushPayload(F);
    let moved = 0, dropped = 0; const sample = [];
    Object.keys(fBefore).forEach(k => {
      if (!(k in fAfter)) { dropped++; return; }
      if (fAfter[k] !== fBefore[k]) {
        moved++;
        if (sample.length < 2) sample.push(`${k}: DB(${fBefore[k].replace('_', ',')}) -> DB(${fAfter[k].replace('_', ',')})`);
      }
    });
    // The axis this fixture exists for: coordinates MOVE. (`dropped` here is a different
    // population — cells the new PHYSICAL SPEC puts outside the wafer circle, so
    // `eachSavableCell` stops emitting them. The guard's `lost` term is about grid
    // REACHABILITY, and that it is 0 here is asserted below through the shipped reason text,
    // which omits the "덮지도 못합니다" clause exactly when nothing is unreachable.)
    eq('F6/C/P0-1/fixture-moves-coordinates', true, moved > 0,
       `moved=${moved} (dropped-from-payload ${dropped}) — this fixture makes the MOVED axis live`);

    const res = await S.resolveValidDie({ valid_die_ref: { table: 'ref_tbl', map_id: 'TPL_1' } }, 'dt_map', 'HOME_1');
    eq('F6/C/P0-1/refused', 'refused', S.validDieBasis(res), `reason='${res.reason}'`);
    eq('F6/C/P0-1/reason-names-the-coordinates', true,
       /저장될 좌표가 함께 움직입니다/.test(res.reason || ''), res.reason);
    eq('F6/C/P0-1/reason-does-not-claim-cells-are-unreachable', false,
       /덮지도 못합니다/.test(res.reason || ''), 'nothing is lost here — the reason must not say so');
    eq('F6/C/P0-1/frame-untouched', dims, [el.gridCols.value, el.gridRows.value]);
    eq('F6/C/P0-1/push-payload-unchanged', payloadBefore, pushPayload(S));
    evidence.push(`[F6/C] 45x45 -> 46x46, identical physical spec: forcing it moves ${moved} `
      + `Push coordinates and loses ${dropped}${sample.length ? ` | ${sample.join(' ; ')}` : ''}`);
  }

  // ══ D — a dimension change that MOVES NOTHING must still be allowed ═════════════════
  // The guard judges coordinate movement, not "the dimensions differ". An over-strict guard
  // would take the feature away from a case that is provably safe.
  {
    const cells = refCellsFor(REF_D);
    const { sandbox: S, el } = buildEnv(src, { refMeta: REF_D, refCells: cells });
    const reach = targetReachableKeys(S);
    [...reach.keys()].forEach(k => { S.gridData[k] = 'A'; });
    const payloadBefore = pushPayload(S);

    const res = await S.resolveValidDie({ valid_die_ref: { table: 'ref_tbl', map_id: 'TPL_1' } }, 'dt_map', 'HOME_1');
    eq('F6/D/dimensions-really-differ', true,
       String(el.gridCols.value) === String(REF_D.grid_cols) && REF_D.grid_cols !== PANEL_BEFORE.cols,
       'the adoption must actually have changed the dimensions, or this case is vacuous');
    eq('F6/D/allowed', 'ref', S.validDieBasis(res), `reason='${res.reason}'`);
    // ...and the reason it is safe, stated as a measurement: no cell that is still in the
    // payload changed its coordinate. (Membership of the payload DOES change — the adopted
    // diameter moves the circle mask, which is the `outsideRetained` population the
    // announcement already reports. The guard is about coordinate IDENTITY, not membership.)
    const after = pushPayload(S);
    const shared = Object.keys(payloadBefore).filter(k => k in after);
    const movedAnyway = shared.filter(k => after[k] !== payloadBefore[k]);
    eq('F6/D/no-shared-cell-changed-its-coordinate', [], movedAnyway.slice(0, 8));
    eq('F6/D/the-shared-population-is-not-empty', true, shared.length > 0);
    evidence.push(`[F6/D] 45x45 -> ${REF_D.grid_cols}x${REF_D.grid_rows} (dia 320): adopted; of `
      + `${Object.keys(payloadBefore).length} payload cells ${shared.length} are still savable and `
      + `NONE moved — that is why a differing dimension is allowed here`);
  }

  // ══ THE PRIMARY CASE — an EMPTY target still adopts, with zero friction ═════════════
  //
  // This is the user's own scenario ("기존 프레임이 없으면 어떻게 됨?"): a map with no stored
  // cells has no coordinate to move, so the guard does not fire and the feature is intact.
  // Every assertion about the ADOPTION ITSELF lives here now — it is the only path on which
  // adoption still happens.
  //
  // ⚠️ These three assertions used to be RED for a reason that had nothing to do with the
  //    code: the sandbox's console stub had no `debug`, so the [1e] zero-stranded branch threw
  //    and was reported as an internal error. So "the primary case adopts" was UNVERIFIED at
  //    HEAD. `debug` is stubbed now, and the expectation is corrected to the shipped [1e]
  //    contract: zero stranded cells produce NO toast at all (a console.debug line instead).
  for (const [label, REF] of [['A', REF_A], ['B', REF_B]]) {
    const cells = refCellsFor(REF);
    const { sandbox: S, el, log } = buildEnv(src, { refMeta: REF, refCells: cells });
    const orientBefore = { rot: S.currentRotation, side: S.currentSide,
                           sx: el.gridStartX.value, sy: el.gridStartY.value, inv: el.gridYInvert.checked };
    const wrongFrame = S.currentFrame();
    const beforeReach = targetReachableKeys(S);

    const res = await S.resolveValidDie({ valid_die_ref: { table: 'ref_tbl', map_id: 'TPL_1' } }, 'dt_map', 'HOME_1');

    // INV-F6-1 — the designation resolves instead of refusing on dimensions
    eq(`F6/empty-${label}/basis`, 'ref', S.validDieBasis(res), `reason='${res.reason}'`);
    eq(`F6/empty-${label}/grid-opened-at-reference-size`, [REF.grid_cols, REF.grid_rows],
       [parseInt(el.gridCols.value, 10), parseInt(el.gridRows.value, 10)]);
    // INV-F6-4 — rotation/side (and origin) are NOT adopted; the transform handles them
    eq(`F6/empty-${label}/orientation-untouched`, orientBefore,
       { rot: S.currentRotation, side: S.currentSide,
         sx: el.gridStartX.value, sy: el.gridStartY.value, inv: el.gridYInvert.checked });
    // the physical spec IS adopted (that is what makes the index spaces agree)
    eq(`F6/empty-${label}/phys-adopted`,
       [REF.phys_chip_x, REF.phys_chip_y, REF.phys_offset_x, REF.phys_offset_y],
       [parseFloat(el.physChipX.value), parseFloat(el.physChipY.value),
        parseFloat(el.physOffsetX.value), parseFloat(el.physOffsetY.value)]);
    eq(`F6/empty-${label}/no-metadata-write`, [],
       log.requests.filter(r => /wafer_map_metadata|updates|replace/i.test(r)));

    // KEY->VALUE: every mask key must be reachable by the target renderer after adoption.
    const afterReach = targetReachableKeys(S);
    const unreachableAfter = [...res.keys].filter(k => !afterReach.has(k));
    eq(`F6/empty-${label}/mask-fully-reachable-after`, 0, unreachableAfter.length,
       unreachableAfter.slice(0, 6).join(' '));
    // and adoption is not a no-op: keeping the old frame would have marked OTHER dies valid
    const screenBefore = new Set([...res.keys].map(k => beforeReach.get(k)).filter(Boolean));
    const screenAfter = new Set([...res.keys].map(k => afterReach.get(k)).filter(Boolean));
    const wrongDies = [...screenAfter].filter(s => !screenBefore.has(s)).length
                    + [...screenBefore].filter(s => !screenAfter.has(s)).length;
    eq(`F6/empty-${label}/adoption-is-not-a-no-op`, true, wrongDies > 0,
       `keeping the old frame would have marked ${wrongDies} different screen dies valid`);
    // key -> screen cell -> key must close
    let roundTripMismatch = 0;
    const cols = parseInt(el.gridCols.value, 10), rows = parseInt(el.gridRows.value, 10);
    for (const k of res.keys) {
      const [c, r] = afterReach.get(k).split(',').map(Number);
      const p = S.getPhysicalCoords(c, r, cols, rows, S.currentRotation, S.currentSide);
      if (`${p.x}_${p.y}` !== k) roundTripMismatch++;
    }
    eq(`F6/empty-${label}/key-to-cell-to-key`, 0, roundTripMismatch);
    // the mask, not the circle, governs
    const someMask = [...res.keys][0].split('_').map(Number);
    eq(`F6/empty-${label}/mask-governs-inside`, true,
       S.isValidDieAt(someMask[0], someMask[1], false, res), 'a masked die stays valid even off-circle');
    eq(`F6/empty-${label}/mask-excludes-unlisted`, false,
       S.isValidDieAt(9999, 9999, true, res), 'a die outside the mask is invalid even inside the circle');

    // nothing stranded, and therefore [1e]: no toast at all
    const u = S.classifyUnsavableCells();
    eq(`F6/empty-${label}/nothing-stranded`, [0, 0],
       [S.pushBlockingCount(u), u.outsideStray.length]);
    eq(`F6/empty-${label}/happy-path-is-silent`, [],
       log.toasts.filter(x => /격자를 참조 맵 규격으로 열었습니다/.test(x.msg)).map(x => x.kind));
    evidence.push(`[F6/empty-${label}] adopted ${wrongWxH(wrongFrame)} -> `
      + `${REF.grid_cols}x${REF.grid_rows}; mask ${res.keys.size} keys, all reachable; `
      + `${wrongDies} dies would have been marked wrong under the old frame; no toast`);
  }

  // ══ [MEDIUM-1] ONE quantity for "this many cells make Push refuse" ══════════════════
  //
  // `announceFrameAdoption` used to sum offGrid + outsideRetained + outsideStray and then say
  // "Push가 거절합니다" about that total, while `pushMapData` refuses on offGrid +
  // outsideRetained. Measured: the toast said 4 and the Push alert said 2 for one grid, and
  // the stray cells went to a DIFFERENT dialog with different guidance.
  //
  // 🔴 AND THE STRAY AXIS IS LIVE HERE. Everywhere else in this harness `serverCellKeys` is
  //    `null`, which forces `stray = 0` by construction — that is exactly why the old
  //    `classifier-matches-independent-count` assertion could never tell the two sums apart.
  //    This case declares a served set, so cells outside the circle that the server never
  //    sent classify as stray and the two sums genuinely differ.
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
    const blocking = EXPECT_BLOCKING;
    eq('MEDIUM-1/stray-axis-is-live', true, EXPECT_STRAY > 0,
       'everywhere else in this harness serverCellKeys is null, which forces stray to 0');

    log.toasts.length = 0;
    // 🔴 The domain is WIPED on purpose. `announceFrameAdoption` promises to render before it
    //    counts (its own comment: the order is part of the rule). With `gridCells2D` empty, an
    //    announcement that skips that render classifies every painted cell as offGrid and the
    //    numbers below come out 5/0 instead of 1/2 — so the render is scored independently
    //    rather than by comparing the toast to a second call of the same classifier.
    S.gridCells2D = {};
    S.announceFrameAdoption({ before: '45x45', after: '41x51' }, { table: 'ref_tbl', mapKey: 'TPL_1' });
    const t = log.toasts.find(x => /격자를 참조 맵 규격으로 열었습니다/.test(x.msg));
    eq('MEDIUM-1/announced', true, !!t);
    // the refusal claim names `blocking`, and ONLY blocking
    eq('MEDIUM-1/refusal-claim-names-blocking', true,
       new RegExp(`칠해진 셀 ${blocking}개`).test(t ? t.msg : ''), t ? t.msg : '(none)');
    eq('MEDIUM-1/refusal-claim-does-not-name-the-total', false,
       new RegExp(`칠해진 셀 ${EXPECT_BLOCKING + EXPECT_STRAY}개`).test(t ? t.msg : ''));
    // stray gets its own sentence, and it does NOT claim a refusal
    eq('MEDIUM-1/stray-has-its-own-sentence', true,
       new RegExp(`추가로 ${EXPECT_STRAY}개`).test(t ? t.msg : ''), t ? t.msg : '(none)');
    eq('MEDIUM-1/stray-sentence-says-it-does-not-block', true,
       /저장을 막지는/.test(t ? t.msg : ''));
    evidence.push(`[MEDIUM-1] blocking=${blocking} stray=${u.outsideStray.length} `
      + `(offGrid ${u.offGrid.length} / outsideRetained ${u.outsideRetained.length}); `
      + `toast names ${blocking} as the refusal cause and ${u.outsideStray.length} separately`);
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

  // Adoption that CANNOT take must refuse with its reason — never proceed with a mask built
  // in a different index space (that is the silent-wrong-answer shape this domain exists for).
  {
    const { sandbox: S } = buildEnv(src, { refMeta: REF_B, refCells: refCellsFor(REF_B), freezeGridCols: true });
    const res = await S.resolveValidDie({ valid_die_ref: 'TPL_1' }, 'dt_map', 'HOME_1');
    eq('F6/adoption-failed/refused', 'refused', S.validDieBasis(res));
    eq('F6/adoption-failed/has-reason', true, /격자 규격을 참조 맵에 맞추지 못했습니다/.test(res.reason), res.reason);
    eq('F6/adoption-failed/no-mask', null, res.keys);
  }

  // A crash must not wear the costume of an honest refusal. `refuse` guarantees "a refusal
  // carries a non-empty reason", and a raw `ReferenceError: x is not defined` satisfies that
  // guarantee while explaining nothing — worse, it reads as a DATA problem, so the operator
  // goes and edits map data to fix a program defect. Measured this round: the reason string
  // was literally `announceFrameAdoption is not defined`.
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

  // Stale generation must not touch the editor frame.
  {
    const { sandbox: S, el } = buildEnv(src, { refMeta: REF_B, refCells: refCellsFor(REF_B) });
    const before = [el.gridCols.value, el.gridRows.value];
    const p = S.resolveValidDie({ valid_die_ref: 'TPL_1' }, 'dt_map', 'HOME_1');
    S.validDieResolveSeq++;                 // a newer resolution starts while this one awaits
    await p;
    eq('F6/stale/frame-untouched', before, [el.gridCols.value, el.gridRows.value],
       'a superseded resolution must never resize the grid the user is looking at');
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
    eq('F5c/ok/orientation-written', [180, 'back'], [S.currentRotation, S.currentSide],
       'a routed preset declares the whole spec — unlike F6 adoption, rotation/side are part of it');
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
const MUTATIONS = [
  ['M1 adoptFrameSpec drops the explicit dimension write (derived dims win)',
   s => s.replace(`  if (el.gridCols && frame.cols !== undefined) el.gridCols.value = frame.cols;
  if (el.gridRows && frame.rows !== undefined) el.gridRows.value = frame.rows;`,
                  '  // mutated: dimensions left at the derived value')],
  ['M2 adoptFrameSpec also adopts rotation/side',
   s => s.replace('  applyPresetObject(preset);\n  // 파생 치수를',
                  '  preset.rotation = frame.rotation; preset.side = frame.side;\n  applyPresetObject(preset);\n  // 파생 치수를')],
  ['M3 the post-adoption re-check is removed (proceed regardless)',
   s => s.replace(`      if (refResolved.cols !== hereResolved.cols || refResolved.rows !== hereResolved.rows) {
        return refuse(ref,
          \`격자 규격을 참조 맵에 맞추지 못했습니다 — 참조 \${refResolved.cols}x\${refResolved.rows} \`
          + \`vs 현재 \${hereResolved.cols}x\${hereResolved.rows}.\`);
      }`, '      // mutated: no re-check')],
  ['M4 adoptFrameSpec is not called at all (the old refusal)',
   s => s.replace('      adoptFrameSpec(refFrame);', '      // mutated: no adoption')],
  ['M5 the stale-generation guard before adoption is removed',
   s => s.replace('      if (stale()) return validDie;\n      const before =', '      const before =')],
  ['M6 the stranded-cell warning is removed (silent adoption)',
   s => s.replace('  if (blocking === 0 && stray === 0) {', '  if (true) {')],
  ['M7 the adoption announcement re-derives the blocking sum instead of sharing it',
   s => s.replace('  const blocking = pushBlockingCount(u);', '  const blocking = u.offGrid.length;')],
  ['M7b pushBlockingCount folds stray in (the measured 4-vs-2 divergence, put back)',
   s => s.replace('  return u.offGrid.length + u.outsideRetained.length;\n}',
                  '  return u.offGrid.length + u.outsideRetained.length + u.outsideStray.length;\n}')],
  // ── [P0-1] the guard, put back defective four different ways ─────────────────────────
  ['P1a the guard is removed entirely (adoption proceeds over stored cells)',
   s => s.replace('      if (cost.moved > 0 || cost.lost > 0) {', '      if (false) {')],
  ['P1b the guard looks only at dropped cells, not moved ones (the silent shift survives)',
   s => s.replace('      if (cost.moved > 0 || cost.lost > 0) {', '      if (cost.lost > 0) {')],
  ['P1c the guard refuses on any dimension change (an EMPTY map loses the feature)',
   s => s.replace('      const cost = adoptionCoordinateCost(refFrame);',
                  '      const cost = { moved: 1, lost: 0, kept: 0, sample: null };')],
  ['P1d the cost is measured in PHYSICAL KEYS — the unit that cannot see this defect',
   s => s.replace('        out.set(`${p.x}_${p.y}`, `${v.x}_${v.y}`);',
                  '        out.set(`${p.x}_${p.y}`, `${p.x}_${p.y}`);')],
  // ⚠️ M8 ("the announcement runs BEFORE the mask lands") is DELETED, not silently dropped.
  //    After the P0-1 guard, every path that both adopts AND strands cells refuses instead, so
  //    the announcement is only reachable on the empty-target path where nothing is stranded
  //    either way — the ordering has no observable consequence left to score, and a mutation
  //    that stays green is a lie about coverage. The ordering RULE still stands in the source
  //    comment; what changed is that no fixture can put it under load. Recorded in the round
  //    report so it is a known gap, not a forgotten one.
  //    (M9 below is still scored: the MEDIUM-1 case wipes `gridCells2D` before calling the
  //     announcement, so an announcement that skips its own render counts an empty domain.)
  ['M9 announceFrameAdoption skips its synchronous render (counts a stale gridCells2D)',
   s => s.replace('function announceFrameAdoption(adopted, ref) {\n  renderGridCanvas();',
                  'function announceFrameAdoption(adopted, ref) {')],
  ['M9b the catch passes any raw e.message off as an operator reason (crash as refusal)',
   s => s.replace(`    const internal = !!e && (e.name === 'TypeError' || e.name === 'ReferenceError'
      || e.name === 'RangeError' || e.name === 'SyntaxError');`,
                  '    const internal = false;')],
  ['M9c the catch labels EVERY failure internal (real data errors relabelled as defects)',
   s => s.replace(`    const internal = !!e && (e.name === 'TypeError' || e.name === 'ReferenceError'
      || e.name === 'RangeError' || e.name === 'SyntaxError');`,
                  '    const internal = true;')],
  ['M10 applyRoutedPreset applies on any status',
   s => s.replace("  if (status !== 'ok' || !resp.preset) {", '  if (false) {')],
  ['M11 applyRoutedPreset applies the preset before checking the status',
   s => s.replace("  const status = resp && resp.status ? String(resp.status) : '';",
                  "  if (resp && resp.preset) applyPresetObject(resp.preset);\n  const status = resp && resp.status ? String(resp.status) : '';")],
];

const base = await scoreAll(SRC0, { verbose: true });
console.log(`\n${base.failures.length === 0 ? '✓' : '✗'} baseline: ${base.compared} assertions, `
  + `${base.failures.length} failure(s)`);
base.failures.forEach(f => console.log('   ✗ ' + f));

if (process.argv.includes('--mutate')) {
  console.log('\n── MUTATIONS (each must turn the harness RED) ──');
  let blind = 0;
  for (const [name, apply] of MUTATIONS) {
    const mutated = apply(SRC0);
    if (mutated === SRC0) { console.log(`  ! ${name}: MUTATION DID NOT APPLY (harness bug)`); blind++; continue; }
    let r;
    try { r = await scoreAll(mutated); }
    catch (e) { console.log(`  ✓ ${name} -> harness threw (${e && e.message})`); continue; }
    if (r.failures.length === 0) { console.log(`  ✗ ${name} -> STILL GREEN — this axis is unscored`); blind++; }
    else console.log(`  ✓ ${name} -> ${r.failures.length} failure(s): ${r.failures[0].split(':')[0]}`);
  }
  if (blind > 0) { console.log(`\n✗ ${blind} mutation(s) went undetected.`); process.exit(1); }
}

process.exit(base.failures.length === 0 ? 0 : 1);
