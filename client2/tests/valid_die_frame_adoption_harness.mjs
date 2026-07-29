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
    console: { warn() {}, info() {}, error() {}, log() {} },
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

  // ══ F6 ══════════════════════════════════════════════════════════════════════════════
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
    const paintedScreenBefore = new Map(painted.map(k => [k, beforeReach.get(k)]));

    const orientBefore = { rot: S.currentRotation, side: S.currentSide,
                           sx: el.gridStartX.value, sy: el.gridStartY.value, inv: el.gridYInvert.checked };

    const res = await S.resolveValidDie({ valid_die_ref: { table: 'ref_tbl', map_id: 'TPL_1' } }, 'dt_map', 'HOME_1');

    // INV-F6-1 — the designation resolves instead of refusing on dimensions
    eq(`F6/${label}/basis`, 'ref', S.validDieBasis(res), `reason='${res.reason}'`);
    eq(`F6/${label}/grid-opened-at-reference-size`,
       [REF.grid_cols, REF.grid_rows],
       [parseInt(el.gridCols.value, 10), parseInt(el.gridRows.value, 10)]);

    // INV-F6-4 — rotation/side (and origin) are NOT adopted; the transform handles them
    eq(`F6/${label}/orientation-untouched`, orientBefore,
       { rot: S.currentRotation, side: S.currentSide,
         sx: el.gridStartX.value, sy: el.gridStartY.value, inv: el.gridYInvert.checked });

    // the physical spec IS adopted (that is what makes the index spaces agree)
    eq(`F6/${label}/phys-adopted`,
       [REF.phys_chip_x, REF.phys_chip_y, REF.phys_offset_x, REF.phys_offset_y],
       [parseFloat(el.physChipX.value), parseFloat(el.physChipY.value),
        parseFloat(el.physOffsetX.value), parseFloat(el.physOffsetY.value)]);

    // INV-F6-2 — no write left this path. Every request the resolution made is a READ.
    const writes = log.requests.filter(r => /wafer_map_metadata|updates|replace/i.test(r));
    eq(`F6/${label}/no-metadata-write`, [], writes);

    // KEY->VALUE: every mask key must be reachable by the target renderer after adoption,
    // and must NOT have been before. Two different functions, two directions — not a round trip.
    const afterReach = targetReachableKeys(S);
    const unreachableAfter = [...res.keys].filter(k => !afterReach.has(k));
    eq(`F6/${label}/mask-fully-reachable-after`, 0, unreachableAfter.length,
       unreachableAfter.slice(0, 6).join(' '));

    // THE MEASURE THIS DOMAIN ACTUALLY NEEDS: if the target had kept its own frame, which
    // SCREEN CELLS would the mask have marked valid? Physical keys are canvas-index relative,
    // so the same key names a different die in a different-sized grid — the mask would land
    // silently on the wrong dies rather than fail. This counts those dies.
    const screenBefore = new Set([...res.keys].map(k => beforeReach.get(k)).filter(Boolean));
    const screenAfter = new Set([...res.keys].map(k => afterReach.get(k)).filter(Boolean));
    const wrongDies = [...screenAfter].filter(s => !screenBefore.has(s)).length
                    + [...screenBefore].filter(s => !screenAfter.has(s)).length;
    eq(`F6/${label}/adoption-is-not-a-no-op`, true, wrongDies > 0,
       `keeping the old frame would have marked ${wrongDies} different screen dies valid`);
    evidence.push(`[F6/${label}] mask ${res.keys.size} keys — unreachable after adoption `
      + `${unreachableAfter.length}; keeping the ${wrongWxH(wrongFrame)} frame would have marked `
      + `${wrongDies} different screen dies valid (silently)`);

    // Trap 3 — painted cells keep their DIE (physical key), and we report where each moved.
    const keysUnchanged = painted.every(k => S.gridData[k] === 'A');
    eq(`F6/${label}/painted-keys-are-untouched`, true, keysUnchanged);
    let moved = 0; const samples = [];
    for (const k of painted) {
      const now = afterReach.get(k);
      if (now !== undefined && now !== paintedScreenBefore.get(k)) {
        moved++;
        if (samples.length < 4) samples.push(`${k}: screen ${paintedScreenBefore.get(k)} -> ${now}`);
      }
    }

    // ── THE COST OF ADOPTION, AND WHO SAYS IT ────────────────────────────────────────
    // Adoption can push painted cells outside the reference map's grid / valid dies. They
    // are NOT deleted — pushMapData's contrast gate refuses. But the operator learns that
    // at Push, far from the designation that caused it, unless adoption says so. Counted
    // by the SHIPPED classifier, the same one the Push gate uses: a second count here
    // would be the very divergence this asserts against.
    // 🔴 THE EXPECTATION IS INDEPENDENT, NOT THE CLASSIFIER'S OWN ANSWER. Comparing the
    //    toast against a fresh classifyUnsavableCells() call is SELF-COMPARISON: if the
    //    announcement counted a stale gridCells2D, so would the check, and both would agree
    //    on the same wrong number (measured: that mutation stayed green). After adoption the
    //    basis is 'ref', so `inside` <=> the physical key is in the mask, and every mask key
    //    is reachable (asserted above). So savable painted cells = |painted ∩ mask|, derived
    //    from res.keys and the paint set — neither of which touches gridCells2D.
    const savableExpected = painted.filter(k => res.keys.has(k)).length;
    const strandedExpected = painted.length - savableExpected;
    const u = S.classifyUnsavableCells();
    const stranded = u.offGrid.length + u.outsideRetained.length + u.outsideStray.length;
    evidence.push(`[F6/${label}] painted ${painted.length} cells — same die (physical key) for all; `
      + `screen position moved for ${moved}; unsavable after adoption ${stranded} `
      + `(offGrid ${u.offGrid.length} / outsideRetained ${u.outsideRetained.length} / stray ${u.outsideStray.length}); `
      + `independent expectation ${strandedExpected}`
      + (samples.length ? ` | ${samples.join(' ; ')}` : ''));

    // The fixture must actually strand cells, or the warning axis is unscored.
    eq(`F6/${label}/stranding-axis-is-live`, true, strandedExpected > 0);
    // The shipped classifier must agree with the independent count — this is what catches an
    // announcement that measured the wrong frame or the wrong mask.
    eq(`F6/${label}/classifier-matches-independent-count`, strandedExpected, stranded);
    // ...and the Push payload must be the complement, by the same arithmetic.
    let savableSeen = 0;
    S.eachSavableCell(() => { savableSeen++; });
    eq(`F6/${label}/push-payload-is-the-complement`, savableExpected, savableSeen);

    const adoptToast = log.toasts.filter(t => /격자를 참조 맵 규격으로 열었습니다/.test(t.msg));
    eq(`F6/${label}/announced-exactly-once`, 1, adoptToast.length);
    // It must be a WARNING, not the reassuring info line...
    eq(`F6/${label}/stranding-is-a-warning`, 'warning', adoptToast[0] && adoptToast[0].kind);
    // ...and it must NAME THE INDEPENDENTLY EXPECTED NUMBER.
    eq(`F6/${label}/stranding-count-is-named`, true,
       new RegExp(`칠해진 셀 ${strandedExpected}개`).test(adoptToast[0] ? adoptToast[0].msg : ''),
       `expected ${strandedExpected}; toast='${adoptToast[0] ? adoptToast[0].msg : '(none)'}'`);
    // ...and it must NOT still promise that Push will record these cells.
    eq(`F6/${label}/no-false-save-promise`, false,
       /⚡ Push가 이 규격과 셀 좌표를 함께 기록합니다/.test(adoptToast[0] ? adoptToast[0].msg : ''));
    eq(`F6/${label}/says-push-will-refuse`, true,
       /⚡ Push가 거절합니다/.test(adoptToast[0] ? adoptToast[0].msg : ''));

    // A: mask keys must be identical whichever way we get there — the reference's projection
    //    and the target's renderer must agree cell-for-cell (key -> screen cell -> key).
    let roundTripMismatch = 0;
    const cols = parseInt(el.gridCols.value, 10), rows = parseInt(el.gridRows.value, 10);
    for (const k of res.keys) {
      const [c, r] = afterReach.get(k).split(',').map(Number);
      const p = S.getPhysicalCoords(c, r, cols, rows, S.currentRotation, S.currentSide);
      if (`${p.x}_${p.y}` !== k) roundTripMismatch++;
    }
    eq(`F6/${label}/key-to-cell-to-key`, 0, roundTripMismatch);

    // isValidDieAt must now answer from the mask, not the circle
    const someMask = [...res.keys][0].split('_').map(Number);
    eq(`F6/${label}/mask-governs-inside`, true,
       S.isValidDieAt(someMask[0], someMask[1], false, res), 'a masked die stays valid even off-circle');
    eq(`F6/${label}/mask-excludes-unlisted`, false,
       S.isValidDieAt(9999, 9999, true, res), 'a die outside the mask is invalid even inside the circle');

    // the resize was announced (no new panel/modal — the existing toast channel)
    eq(`F6/${label}/resize-announced`, true,
       log.toasts.some(t => /격자를 참조 맵 규격으로 열었습니다/.test(t.msg)));
  }

  // The PRIMARY case from the user's scenario: a map with no painted cells (nothing to
  // strand) must adopt with ZERO friction — an info line, no warning, no cry-wolf number.
  // If this ever goes 'warning', the warning above stops meaning anything.
  {
    const cells = refCellsFor(REF_B);
    const { sandbox: S, el, log } = buildEnv(src, { refMeta: REF_B, refCells: cells });
    const res = await S.resolveValidDie({ valid_die_ref: { table: 'ref_tbl', map_id: 'TPL_1' } }, 'dt_map', 'HOME_1');
    eq('F6/empty-target/basis', 'ref', S.validDieBasis(res), `reason='${res.reason}'`);
    eq('F6/empty-target/grid-opened-at-reference-size', [REF_B.grid_cols, REF_B.grid_rows],
       [parseInt(el.gridCols.value, 10), parseInt(el.gridRows.value, 10)]);
    const u = S.classifyUnsavableCells();
    eq('F6/empty-target/nothing-stranded', 0,
       u.offGrid.length + u.outsideRetained.length + u.outsideStray.length);
    const t = log.toasts.filter(x => /격자를 참조 맵 규격으로 열었습니다/.test(x.msg));
    eq('F6/empty-target/announced-once', 1, t.length);
    eq('F6/empty-target/is-info-not-warning', 'info', t[0] && t[0].kind);
    eq('F6/empty-target/no-stranding-number', false, /칠해진 셀/.test(t[0] ? t[0].msg : ''));
    evidence.push('[F6/empty-target] no painted cells -> info toast, no warning, nothing stranded');
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
  ['M6 the stranded-cell warning is removed (silent adoption, false save promise kept)',
   s => s.replace(`  if (stranded === 0) {`, '  if (true) {')],
  ['M7 stranded cells counted by a partial predicate instead of the shipped classifier',
   s => s.replace('  const stranded = u.offGrid.length + u.outsideRetained.length + u.outsideStray.length;\n  const head =',
                  '  const stranded = u.offGrid.length;\n  const head =')],
  ['M8 the announcement runs BEFORE the mask lands (counts against the old valid-die basis)',
   s => s.replace('    const out = set(\'ref\', keys, \'\', ref);\n    // 마스크가 앉은 **뒤에야**',
                  '    if (adopted && !stale()) announceFrameAdoption(adopted, ref);\n    const out = set(\'ref\', keys, \'\', ref);\n    // 마스크가 앉은 **뒤에야**')],
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
