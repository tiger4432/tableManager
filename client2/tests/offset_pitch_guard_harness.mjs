/**
 * 📐 phys_offset_x/y — SEMANTICS, the drift it causes, and the pitch guard that stops it.
 *
 * Scores FOUR claims by executing the shipped code:
 *
 *  S. THE SEMANTICS ARE NOT IN DISPUTE. `phys_offset_x/y` displaces the DIE LATTICE, in
 *     physical millimetres, against a wafer circle that stays nailed to the canvas centre.
 *     The canonical statement is the server's — `PhysicalWaferEngine.get_cell_physical_mm`,
 *     `x_mm = (c - cc) * chip_x + off_x` — combined with the per-rotation frame mapping in
 *     `map_overlay._frame_phys_params`. This group re-states that table INDEPENDENTLY (it is
 *     transcribed below, not imported and not derived from any client function) and compares
 *     it to what `getScreenShift` answers, for all 4 rotations x 2 sides.
 *
 *  P. AN OFFSET OF ONE PITCH IS A RE-LABELLING, NOT A NEW GEOMETRY. The die lattice is
 *     periodic in the offset with period = chip pitch: `off += chip_x` puts canvas cell `c`
 *     exactly where cell `c+1` used to sit. Scored per cell: same wafer-mm, index shifted by
 *     exactly 1. This is WHY a cap at one pitch loses no expressible geometry.
 *
 *  D. THE DEFECT THE USER REPORTED. The origin box is scanned over the DECLARED grid only
 *     (`getWaferBoundingBox`: `r < visualRows`, `c < visualCols`) — and the server's
 *     `WaferMapCoordinateTransformer.get_wafer_bounding_box` scans exactly the same window,
 *     so the client is not free to widen it. But `renderGridCanvas` EXTENDS the lattice to
 *     cover the canvas (`startC`/`endC`), so past a certain offset the dies inside the circle
 *     keep appearing at c < 0 while the box stops at 0. The gap between the two is the
 *     distance the ORIGIN walks away from the valid dies — and every stored coordinate moves
 *     with it. Scored per cell against an UNBOUNDED scan of the render's own predicate.
 *
 *  G. THE GUARD. On `change` (never on `input`, which would cut "12" down to "1" mid-typing),
 *     an offset larger than its axis's chip pitch is clamped to that pitch and one toast is
 *     raised. Inside the cap the control is left byte-identical and nothing moves. A frame
 *     that ARRIVED from the server is never rewritten (invariant 3) — only what the operator
 *     commits by hand is capped.
 *
 * 🔴 THE ORACLES ARE NOT THE TRANSFORM.
 *      S compares against a hand-transcribed copy of the SERVER's table.
 *      P compares a lattice against ITSELF one pitch later — the equality asserted is between
 *        two independent evaluations, and the index shift is asserted to be exactly 1, so a
 *        transform that ignored the offset entirely (shift 0) fails.
 *      D compares the shipped bounded box against an unbounded scan of `isCellInsideWaferFast`
 *        — the predicate the RENDER LOOP calls, not the box function under test.
 *      G enters through `dispatchEvent` on the real node, so an unwired guard is red.
 *
 * FIXTURE AXES, all live on purpose (map-pm memory: a dead axis proves nothing):
 *    chipX 11 != chipY 13   — an axis swap in the guard or in the shift table cannot pass
 *    rot 90/270 + back      — the pitch swap and the back-side x negation both fire
 *    box.minC = 2 != 0      — a dropped bbox term cannot pass
 *    startX 1, startY 1     — production BASE_OFFSET (server/config/maps.json)
 *
 * Run:  node client2/tests/offset_pitch_guard_harness.mjs [--mutate] [--verbose]
 * Read-only against client2/. Exit: 0 green | 1 a check failed | 2 harness failure.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC_PATH = join(HERE, '..', 'src', 'map_editor.js');
// CRLF normalised — every multi-line anchor below is written with plain newlines and would
// silently MISS on a CRLF checkout (measured on the sibling harness: 8 of 18 unapplied).
const SRC0 = readFileSync(SRC_PATH, 'utf8').replace(/\r\n/g, '\n');

const die = (m) => { console.error(`HARNESS FAILURE: ${m}\n(Nothing was compared.)`); process.exit(2); };

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

// The coordinate stack, plus the wiring that registers the guard. `initDOMElements` is what
// makes group G an EXECUTION of the shipped listener rather than a re-implementation of it.
const SYMBOLS = [
  'physNum', 'gridDimNum', 'withPhysFrame',
  'getScreenShift', 'getTransformedPhysicalConfig', 'isCellInsideWaferFast',
  'getDieIndex', 'getCanvasCellFromDieIndex', 'getCanvasCellFromDb', 'getDbCoords',
  'getWaferBoundingBox', 'frameDieLattice', 'dieIndexToWaferMm',
  'validDieBasis', 'isValidDieAt',
  'seatingSnapshot', 'reseatCellsToStoredCoords',
  'frameFromMeta', 'currentFrame', 'resolveFrame', 'frameAxesKey',
  'frameDimBounds', 'frameDimError',
  'applyPresetObject', 'applyPhysicalGeometry',
  'loadSelectedPreset', 'initDOMElements',
  'parseValidDieRef', 'validDieChainError', 'validDieRefDisplay',
  'projectCellsToWaferMm', 'projectCellsToPhys',
  'resolveValidDie', 'fitGridToMask', 'summariseReseat', 'resolveReferenceSpec',
  'deriveMaskKeys', 'diagnoseDesignationAlignment',
  'renderGridCanvas', 'cellFillColor', 'isProtectedFCell',
  'eachSavableCell', 'classifyUnsavableCells', 'serverCellKeySet', 'pushBlockingCount',
];

// ── Fixture: production BASE_OFFSET (server/config/maps.json, custom_1785446789091) ──────
const P0 = { cols: 29, rows: 25, startX: 1, startY: 1, invertY: false,
             rotation: 0, side: 'front',
             dia: 300, chipX: 11, chipY: 13, offX: 0, offY: 0, margin: 3 };

// ── DOM ─────────────────────────────────────────────────────────────────────────────────
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
      dispatchEvent(ev) {
        const a = (listeners.get(ev && ev.type) || []).slice();
        a.forEach(fn => fn(Object.assign({ target: this, preventDefault() {},
                                           stopPropagation() {} }, ev)));
        return a.length;
      },
      querySelector: () => null, appendChild() {}, focus() {}, blur() {},
      getBoundingClientRect: () => ({ width: 700, height: 700, left: 0, top: 0 }),
      getContext: () => paintSink(),
    };
  };
  const byId = (id) => {
    if (!nodes.has(id)) nodes.set(id, make(id));
    return nodes.get(id);
  };
  const seed = {
    'grid-cols': P.cols, 'grid-rows': P.rows,
    'grid-start-x': P.startX, 'grid-start-y': P.startY,
    'phys-wafer-dia': P.dia, 'phys-chip-x': P.chipX, 'phys-chip-y': P.chipY,
    'phys-offset-x': P.offX, 'phys-offset-y': P.offY, 'phys-edge-margin': P.margin,
  };
  Object.entries(seed).forEach(([id, v]) => { byId(id).value = String(v); });
  byId('grid-y-invert').checked = !!P.invertY;
  byId('show-annotations').checked = false;
  return { document: { getElementById: byId, querySelectorAll: () => [],
                       addEventListener() {}, removeEventListener() {} }, byId };
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
  const log = { toasts: [], warns: [], requests: [] };
  const dom = makeDom(P);
  const el = {};
  const sandbox = {
    console: { warn: (m) => log.warns.push(String(m)), info() {}, error() {}, log() {}, debug() {} },
    el, document: dom.document,
    localStorage: { getItem: () => null, setItem() {} },
    COPY_HEADER_KEY: 'copyHeader',
    isOriginMode: false,
    // Everything `initDOMElements` names but this harness never fires — stubbed one by one so
    // a rename is a ReferenceError, never a silent no-op.
    fetchAndRenderPresets() {}, saveCustomPreset() {}, deleteCustomPreset() {},
    onValidDieRefChanged() {}, populateValidDieRefList() {}, switchTable() {},
    populateOverlayKeyList() {}, onMetaInputSuggest() {}, KEY_SUGGEST_DEBOUNCE_MS: 120,
    renderMetadataInputs() {}, loadExistingMap: async () => ({}), countNav() {},
    effortRoute: () => '', handleAddOverlayClick() {}, clearOverlayLayers() {},
    renderOverlayList() {}, addLegendRowForPanel() {}, clearGrid() {}, fillGrid() {},
    pushMapData() {}, copyGridToExcel() {}, onMapGridPaste() {}, selectEdgeCells() {},
    autoPaintE1E2() {}, fillSelectedCells() {}, clearSelectedCells() {},
    fitGridToWorkspace() {}, initPlanSidebarResizer() {}, debounce: (f) => f,
    physFrameOverride: null, boundingBoxCache: {}, cellsSeatedUnder: null,
    currentRotation: P.rotation, currentSide: P.side,
    gridData: {}, gridCells2D: {},
    legend: [{ value: 'A', color: '#0a0' }],
    validDie: { basis: 'circle', keys: null, reason: '', ref: null, raw: undefined },
    validDieResolveSeq: 0,
    selectedTable: 'bonding_map', loadedIdentity: null,
    tableSchema: { column_types: {} },
    API_BASE: '', OVERLAY_CELL_LIMIT: 2000, UNLISTED_VALUE_FILL: '#10b981',
    overlayLayers: [], loadedFCells: new Set(), serverCellKeys: null,
    paintLockValues: null, currentHoverCell: null, lastSelectionBox: null,
    syncOverlayGeometry() {},
    getThemeColors: () => ({ outBg: '#eee', line: '#ccc', text: '#000', inBg: '#fff',
                             origin: '#f00', notch: '#00f', gridText: '#333', dim: '#999' }),
    performance: { now: () => 0 },
    window: { devicePixelRatio: 1, addEventListener() {}, removeEventListener() {} },
    updateOrientationUI() {}, updateSideIndicator() {}, scheduleRenderGridCanvas() {},
    updateLegendCounts() {},
    activeOverlayLayers: () => [], drawOverlayMarkers() {}, updateNotchPosition() {},
    isBoxDragging: false, dragType: null,
    getComputedStyle: () => ({ getPropertyValue: () => '#000' }),
    renderValidDieChip() {}, syncValidDieRefControls() {},
    showToast: (msg, kind) => log.toasts.push({ msg: String(msg), kind }),
    requestAnimationFrame(fn) { fn(); },
    isLockedValue: () => false,
    fetchMapKeySpec: async () => ({ ok: true, keyColumns: ['base'], columnTypes: {} }),
    canonicalMapKey: (kc, k) => String(k),
    fetchServedBinding: async () => ({ x: 'x', y: 'y', keyColumns: ['base'], source: 'declared' }),
    fetchGridMetaFor: async () => null,
    buildKeyFilters: () => ({}),
    fetch: async () => ({ ok: true, status: 200, json: async () => ({ data: [] }) }),
    serverPresets: opts.serverPresets || {},
    VALID_DIE_TEMPLATE_PREFIX: 'valid-die-template:',
    enterValidDieAuthoring: () => die('the authoring branch must not be reached'),
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  try { vm.runInContext(pieces.join('\n'), sandbox); }
  catch (e) { die(`extracted sources did not evaluate: ${e && e.message}`); }
  try { sandbox.initDOMElements(); }
  catch (e) { die(`initDOMElements threw — the wiring could not be executed: ${e && e.message}`); }
  return { S: sandbox, el, log, byId: dom.byId };
}

// The operator's gesture. Zero listeners is a failure, not a silent pass.
function fire(node, type, what) {
  const n = node.dispatchEvent({ type });
  if (n === 0) throw new Error(`nothing is listening for '${type}' on ${what} — the wiring is gone`);
  return n;
}

// ── Group S oracle: the SERVER's table, transcribed ─────────────────────────────────────
// server/map_overlay.py::_frame_phys_params  (docstring table, verified there for 8 combos)
//   rot   (chip_x, chip_y)   (off_x, off_y)        oox = -off_x when side == 'back'
//    0      (cx, cy)          ( oox,  ooy)
//    90     (cy, cx)          ( ooy, -oox)
//   180     (cx, cy)          (-oox, -ooy)
//   270     (cy, cx)          (-ooy,  oox)
// and server/utils/physical_wafer_engine.py::get_cell_physical_mm
//   x_mm = (c - cc) * chip_x + off_x     -> +off_x moves a cell RIGHT  -> screen shiftX = +off_x/chip_x
//   y_mm = (cr - r) * chip_y + off_y     -> +off_y moves a cell UP     -> screen shiftY = -off_y/chip_y
function serverFrameShift(rot, side, cx, cy, offX, offY) {
  const oox = (side === 'back') ? -offX : offX;
  const ooy = offY;
  let fx, fy, fcx, fcy;
  if (rot === 90) { fcx = cy; fcy = cx; fx = ooy; fy = -oox; }
  else if (rot === 180) { fcx = cx; fcy = cy; fx = -oox; fy = -ooy; }
  else if (rot === 270) { fcx = cy; fcy = cx; fx = -ooy; fy = oox; }
  else { fcx = cx; fcy = cy; fx = oox; fy = ooy; }
  return { shiftX: fx / fcx, shiftY: -fy / fcy };
}

// ── Group D oracle: the RENDER's own predicate, scanned without the grid's walls ─────────
function unboundedInsideBox(S, P) {
  const isRot = (P.rotation === 90 || P.rotation === 270);
  const vc = isRot ? P.rows : P.cols;
  const vr = isRot ? P.cols : P.rows;
  const cfg = S.getTransformedPhysicalConfig(P.rotation, P.side);
  let minC = 1e9, maxC = -1e9, minR = 1e9, maxR = -1e9, n = 0;
  const PAD = 120;
  for (let r = -PAD; r < vr + PAD; r++) {
    for (let c = -PAD; c < vc + PAD; c++) {
      if (!S.isCellInsideWaferFast(c, r, vc, vr, cfg, 700, 700)) continue;
      n++;
      if (c < minC) minC = c; if (c > maxC) maxC = c;
      if (r < minR) minR = r; if (r > maxR) maxR = r;
    }
  }
  return { minC, maxC, minR, maxR, n };
}

// ── Scoring ─────────────────────────────────────────────────────────────────────────────
const near = (a, b) => Math.abs(a - b) < 1e-9;

function run(src) {
  const failures = [];
  const evidence = [];
  let compared = 0;
  const eq = (name, got, want) => {
    compared++;
    if (String(got) !== String(want)) failures.push(`${name}: got ${got}, want ${want}`);
  };
  const eqf = (name, got, want) => {
    compared++;
    if (!near(got, want)) failures.push(`${name}: got ${got}, want ${want}`);
  };

  // ── S. the shift table matches the server's, all 8 combos ─────────────────────────────
  {
    const OFFX = 7, OFFY = 3;   // both non-zero and DIFFERENT: an axis swap cannot pass
    for (const rot of [0, 90, 180, 270]) {
      for (const side of ['front', 'back']) {
        const { S } = buildEnv(src, { ...P0, rotation: rot, side, offX: OFFX, offY: OFFY });
        const cfg = S.getTransformedPhysicalConfig(rot, side);
        const got = S.getScreenShift(cfg, 1.0, 1.0);
        const want = serverFrameShift(rot, side, P0.chipX, P0.chipY, OFFX, OFFY);
        eqf(`S/${rot}/${side}/shiftX`, got.shiftX, want.shiftX);
        eqf(`S/${rot}/${side}/shiftY`, got.shiftY, want.shiftY);
        evidence.push(`S rot=${String(rot).padStart(3)} ${side.padEnd(5)} `
          + `shift=(${got.shiftX.toFixed(4)}, ${got.shiftY.toFixed(4)}) cells   server=`
          + `(${want.shiftX.toFixed(4)}, ${want.shiftY.toFixed(4)})`);
      }
    }
    // And the absolute mm, against the server's own formula, at rot 0 front where the frame
    // axes ARE the physical axes. A sign table that cancelled itself would still be caught.
    for (const offX of [0, 5, 11]) {
      const { S } = buildEnv(src, { ...P0, offX });
      const L = S.frameDieLattice({ cols: P0.cols, rows: P0.rows, rotation: 0, side: 'front' });
      for (const c of [10, 14, 18]) {
        const p = S.getDieIndex(c, 12, P0.cols, P0.rows, 0, 'front');
        const mm = S.dieIndexToWaferMm(p.x, p.y, L);
        const want = (c - (P0.cols - 1) / 2) * P0.chipX + offX;   // server's get_cell_physical_mm
        eqf(`S/mm/off${offX}/c${c}`, mm.mmX, want);
      }
    }
  }

  // ── P. one pitch of offset re-labels the SAME lattice ─────────────────────────────────
  {
    const a = buildEnv(src, { ...P0, offX: 0 }).S;
    const b = buildEnv(src, { ...P0, offX: P0.chipX }).S;
    const La = a.frameDieLattice({ cols: P0.cols, rows: P0.rows, rotation: 0, side: 'front' });
    const Lb = b.frameDieLattice({ cols: P0.cols, rows: P0.rows, rotation: 0, side: 'front' });
    const mmA = new Set();
    let shifts = new Set();
    for (let c = 0; c < P0.cols; c++) {
      const pa = a.getDieIndex(c, 12, P0.cols, P0.rows, 0, 'front');
      const pb = b.getDieIndex(c, 12, P0.cols, P0.rows, 0, 'front');
      shifts.add(pb.x - pa.x);
      mmA.add(a.dieIndexToWaferMm(pa.x, pa.y, La).mmX.toFixed(6));
      // the SAME canvas cell, one pitch later, sits where the NEXT cell used to sit
      const paNext = a.getDieIndex(c + 1, 12, P0.cols, P0.rows, 0, 'front');
      eqf(`P/cell${c}/mm-equals-next-cell-before`,
        b.dieIndexToWaferMm(pb.x, pb.y, Lb).mmX,
        a.dieIndexToWaferMm(paNext.x, paNext.y, La).mmX);
    }
    eq('P/index-shift-is-exactly-one-everywhere', [...shifts].join(','), '1');
    // the SET of occupied mm positions is unchanged (bar the one column that falls off each end)
    let overlap = 0;
    for (let c = 0; c < P0.cols; c++) {
      const pb = b.getDieIndex(c, 12, P0.cols, P0.rows, 0, 'front');
      if (mmA.has(b.dieIndexToWaferMm(pb.x, pb.y, Lb).mmX.toFixed(6))) overlap++;
    }
    eq('P/mm-set-overlap', overlap, P0.cols - 1);
    evidence.push(`P off 0 -> ${P0.chipX}mm: every die index +1, ${overlap}/${P0.cols} mm positions identical`);
  }

  // ── D. the drift: bounded box vs the lattice the render actually draws ────────────────
  {
    // Physical die keys spanning the wafer. Fixed set, compared key -> value.
    const DIES = [];
    for (let ix = -4; ix <= 4; ix++) for (let iy = -3; iy <= 3; iy++) DIES.push([ix, iy]);
    const storedFor = (S, P) => {
      const out = new Map();
      DIES.forEach(([ix, iy]) => {
        const at = S.getCanvasCellFromDieIndex(ix, iy, P.cols, P.rows, P.rotation, P.side);
        const v = S.getDbCoords(at.c, at.r, P.cols, P.rows, P.rotation, P.side,
          P.invertY, P.startX, P.startY);
        out.set(`${ix}_${iy}`, `${v.x},${v.y}`);
      });
      return out;
    };
    const base = buildEnv(src, { ...P0, offX: 0 });
    const ref = storedFor(base.S, { ...P0, offX: 0 });

    // (a) INSIDE the cap the box follows the lattice exactly — drift 0 at every step.
    for (const offX of [0, 2, 5, 10, 11]) {
      const P = { ...P0, offX };
      const { S } = buildEnv(src, P);
      const box = S.getWaferBoundingBox(0, 'front');
      const t = unboundedInsideBox(S, P);
      eq(`D/in-cap/off${offX}/minC-follows-the-lattice`, box.minC, t.minC);
      eq(`D/in-cap/off${offX}/minR-follows-the-lattice`, box.minR, t.minR);
      evidence.push(`D off=${String(offX).padStart(3)}mm (${(offX / P0.chipX).toFixed(2)} pitch)  `
        + `box.minC=${box.minC}  lattice.minC=${t.minC}  drift=${box.minC - t.minC}`);
    }

    // (b) BEYOND the cap it stops following, and every stored coordinate moves with it.
    for (const [offX, wantDrift] of [[33, 1], [50, 3], [80, 6]]) {
      const P = { ...P0, offX };
      const { S } = buildEnv(src, P);
      const box = S.getWaferBoundingBox(0, 'front');
      const t = unboundedInsideBox(S, P);
      eq(`D/beyond/off${offX}/drift`, box.minC - t.minC, wantDrift);
      // per-cell, key -> value: how many stored coordinates read differently, and by how much
      const now = storedFor(S, P);
      let moved = 0;
      const deltas = new Set();
      ref.forEach((v, k) => {
        if (now.get(k) !== v) {
          moved++;
          deltas.add(Number(now.get(k).split(',')[0]) - Number(v.split(',')[0]));
        }
      });
      eq(`D/beyond/off${offX}/every-stored-x-moved`, moved, ref.size);
      // 🔴 UNIFORM is the whole danger. A single shared offset passes injectivity, range and
      //    round-trip alike (map-pm memory) — the map still looks perfect on screen and every
      //    row in the database is wrong by the same amount. So the claim scored here is not
      //    "some cells moved" but "the entire coordinate system was silently re-numbered".
      compared++;
      if (deltas.size !== 1) failures.push(`D/beyond/off${offX}/shift-is-uniform: ${[...deltas].join(',')}`);
      compared++;
      if ([...deltas][0] === 0) failures.push(`D/beyond/off${offX}/shift-is-non-zero`);
      evidence.push(`D off=${offX}mm  drift=${box.minC - t.minC} cell(s)  `
        + `${moved}/${ref.size} stored coordinates shifted, uniformly by ${[...deltas].join(',')}`);
    }
  }

  // ── G. the guard, entered through the real node ───────────────────────────────────────
  {
    // (a) OVER the pitch, committed with `change` -> clamped to the pitch, one toast.
    const g = buildEnv(src, { ...P0 });
    const ox = g.byId('phys-offset-x');
    const oy = g.byId('phys-offset-y');
    ox.value = '50';
    oy.value = '-40';
    fire(ox, 'change', '#phys-offset-x');
    eq('G/over/offsetX-clamped-to-chipX', ox.value, String(P0.chipX));
    eq('G/over/offsetY-clamped-to-chipY-signed', oy.value, String(-P0.chipY));
    eq('G/over/one-toast', g.log.toasts.length, 1);
    compared++;
    if (!/OFFSET/.test(g.log.toasts[0] ? g.log.toasts[0].msg : ''))
      failures.push(`G/over/toast-names-the-control: ${JSON.stringify(g.log.toasts[0])}`);
    evidence.push(`G over-cap: 50 -> ${ox.value}, -40 -> ${oy.value}, toast="${
      (g.log.toasts[0] || {}).msg || ''}"`);

    // (b) INSIDE the cap nothing is touched — not the value, not its spelling, no toast.
    //     `10.0` must stay `10.0`: rewriting it to `10` would be a silent edit of the frame.
    const h = buildEnv(src, { ...P0 });
    const hx = h.byId('phys-offset-x');
    hx.value = '10.0';
    fire(hx, 'change', '#phys-offset-x');
    eq('G/in-cap/value-untouched', hx.value, '10.0');
    eq('G/in-cap/no-toast', h.log.toasts.length, 0);

    // (c) EXACTLY at the pitch is allowed — the cap is the budget, not one step inside it.
    const i2 = buildEnv(src, { ...P0 });
    const ix2 = i2.byId('phys-offset-x');
    ix2.value = String(P0.chipX);
    fire(ix2, 'change', '#phys-offset-x');
    eq('G/at-cap/value-untouched', ix2.value, String(P0.chipX));
    eq('G/at-cap/no-toast', i2.log.toasts.length, 0);

    // (d) TYPING is not cut short. `input` fires per keystroke; a guard there would turn a
    //     half-typed "50" into "11" under the cursor.
    const j = buildEnv(src, { ...P0 });
    const jx = j.byId('phys-offset-x');
    jx.value = '50';
    fire(jx, 'input', '#phys-offset-x');
    eq('G/input/typing-not-clamped', jx.value, '50');
    eq('G/input/no-toast', j.log.toasts.length, 0);

    // (e) A DECLARED frame is never rewritten. The preset path carries the server's own
    //     numbers, and silently capping them would re-interpret that map's stored coordinates
    //     (invariant 3). Fixture: an offset deliberately over the pitch.
    const k = buildEnv(src, { ...P0 });
    k.S.applyPresetObject({ phys_wafer_dia: 300, phys_chip_x: 11, phys_chip_y: 13,
      phys_offset_x: 50, phys_offset_y: 40, phys_edge_margin: 3, rotation: 0, side: 'front' });
    eq('G/declared/preset-offset-not-rewritten', k.byId('phys-offset-x').value, '50');
    eq('G/declared/no-toast', k.log.toasts.filter(t => /OFFSET/.test(t.msg)).length, 0);

    // (f) SHRINKING THE CHIP re-arms the guard on an offset that used to be legal.
    const m = buildEnv(src, { ...P0, offX: 10 });
    const mc = m.byId('phys-chip-x');
    mc.value = '4';
    fire(mc, 'change', '#phys-chip-x');
    eq('G/chip-shrunk/offset-re-capped', m.byId('phys-offset-x').value, '4');

    // (g) THE CLAMP PRESERVES STORED COORDINATES. The reaction to the origin box moving is
    //     already wired (rule 4); this asserts the guard runs BEFORE it, so the cells are
    //     re-seated under the capped frame and not under the refused one.
    const n = buildEnv(src, { ...P0, offX: 0 });
    n.S.renderGridCanvas();
    const f0 = { cols: P0.cols, rows: P0.rows, rot: 0, side: 'front' };
    const cfg0 = n.S.getTransformedPhysicalConfig(0, 'front');
    n.S.gridData = {};
    const painted = new Map();
    for (let r = 0; r < P0.rows; r++) for (let c = 0; c < P0.cols; c++) {
      const p = n.S.getDieIndex(c, r, f0.cols, f0.rows, 0, 'front');
      if (!n.S.isCellInsideWaferFast(c, r, f0.cols, f0.rows, cfg0, 700, 700)) continue;
      const v = n.S.getDbCoords(c, r, f0.cols, f0.rows, 0, 'front', false, P0.startX, P0.startY);
      n.S.gridData[`${p.x}_${p.y}`] = `${v.x},${v.y}`;
      painted.set(`${p.x}_${p.y}`, `${v.x},${v.y}`);
    }
    const nx = n.byId('phys-offset-x');
    nx.value = '50';
    fire(nx, 'change', '#phys-offset-x');
    eq('G/reseat/offset-clamped', nx.value, String(P0.chipX));
    let lost = 0, movedCells = 0;
    painted.forEach((was, k2) => {
      const cur = Object.prototype.hasOwnProperty.call(n.S.gridData, k2) ? n.S.gridData[k2] : null;
      if (cur === null) { lost++; return; }
      const [px, py] = k2.split('_').map(Number);
      const at = n.S.getCanvasCellFromDieIndex(px, py, f0.cols, f0.rows, 0, 'front');
      const v = n.S.getDbCoords(at.c, at.r, f0.cols, f0.rows, 0, 'front', false,
        P0.startX, P0.startY);
      if (`${v.x},${v.y}` !== was) movedCells++;
    });
    eq('G/reseat/no-cell-destroyed', lost, 0);
    eq('G/reseat/stored-coordinates-preserved', movedCells, 0);
    evidence.push(`G re-seat: ${painted.size} painted cells, ${lost} lost, `
      + `${movedCells} reading a different stored coordinate after the clamp`);
  }

  return { failures, compared, evidence };
}

// ── Mutation controls ───────────────────────────────────────────────────────────────────
const toCrlf = (s) => s.replace(/\n/g, '\r\n');
function once(src, find, repl) {
  if (src.indexOf(find) < 0 && src.indexOf(toCrlf(find)) >= 0) {
    find = toCrlf(find); repl = toCrlf(repl);
  }
  const i = src.indexOf(find);
  if (i < 0) die(`mutation anchor not found: ${find.slice(0, 70)}`);
  if (src.indexOf(find, i + 1) >= 0) die(`mutation anchor is not unique: ${find.slice(0, 70)}`);
  return src.slice(0, i) + repl + src.slice(i + find.length);
}

const MUTANTS = {
  // 🔴 THE DEFECT VERSION PUT BACK. If this survives, group G proves nothing.
  'guard-removed': (s) => once(s,
    "    if (!ev || ev.type === 'change') {",
    '    if (false) {'),
  'guard-clamps-to-zero': (s) => once(s,
    '    const next = v > 0 ? pitch : -pitch;',
    '    const next = 0;'),
  // chipX != chipY in the fixture, so this is a real discrimination and not decoration.
  'guard-uses-chipX-for-both-axes': (s) => once(s,
    "        clampOffsetToPitch(el.physOffsetY, el.physChipY, 'OFFSET Y', 'CHIP Y'),",
    "        clampOffsetToPitch(el.physOffsetY, el.physChipX, 'OFFSET Y', 'CHIP Y'),"),
  'guard-drops-the-sign': (s) => once(s,
    '    const next = v > 0 ? pitch : -pitch;',
    '    const next = pitch;'),
  // Off-by-one on the boundary: exactly one pitch is the budget the grid derivation grants.
  'guard-rejects-exactly-one-pitch': (s) => once(s,
    '    if (Math.abs(v) <= pitch) return null;',
    '    if (Math.abs(v) < pitch) return null;'),
  // Fights the operator mid-keystroke.
  'guard-also-runs-on-input': (s) => once(s,
    "    if (!ev || ev.type === 'change') {",
    '    if (true) {'),
  // Silent: clamps but says nothing.
  'guard-is-silent': (s) => once(s,
    '      if (capped.length > 0) {',
    '      if (false) {'),
  // ORDER. The re-seat moved AHEAD of the clamp, so the cells are re-seated under the frame
  // that was about to be refused and nothing re-seats them under the capped one.
  // (Note the shape: DUPLICATING the re-seat instead of moving it is harmless and was
  //  measured to be — the reaction re-reads `cellsSeatedUnder` each time and the two steps
  //  compose. Only the MOVE is a defect, so only the move is scored.)
  'clamp-runs-after-the-reseat': (s) => once(
    once(s,
      'const onPhysicalGeometryEdit = (ev) => {',
      'const onPhysicalGeometryEdit = (ev) => {\n    reseatCellsToStoredCoords(cellsSeatedUnder);'),
    '    reseatCellsToStoredCoords(cellsSeatedUnder);\n    scheduleRenderGridCanvas();',
    '    scheduleRenderGridCanvas();'),
  // The SEMANTICS side: a sign slip in the shift table. Group S must catch it.
  'shift-table-drops-the-back-negation': (s) => once(s,
    "  if (currentSide === 'back') {\n    origOffsetX = -origOffsetX;\n  }",
    "  if (false) {\n    origOffsetX = -origOffsetX;\n  }"),
  'shift-table-swaps-rot90-axes': (s) => once(s,
    '    shiftX = (origOffsetY / chipY) * cellW;\n    shiftY = (origOffsetX / chipX) * cellH;',
    '    shiftX = (origOffsetX / chipX) * cellW;\n    shiftY = (origOffsetY / chipY) * cellH;'),
  // CONTROL: a semantically inert edit. If this comes back CAUGHT the counts above are noise.
  'CONTROL-comment-only': (s) => s + '\n// inert\n',
};

// ── main ────────────────────────────────────────────────────────────────────────────────
const mutateOnly = process.argv.includes('--mutate');
const verbose = process.argv.includes('--verbose');

const base = run(SRC0);
if (verbose || !mutateOnly) base.evidence.forEach(e => console.log('  ' + e));
console.log(`${base.failures.length === 0 ? '✓' : '✗'} baseline: ${base.compared} assertions, `
  + `${base.failures.length} failure(s)`);
console.log(`ASSERTIONS ${base.compared} ${base.failures.length}`);
base.failures.forEach(f => console.log(`   ✗ ${f}`));

if (process.argv.includes('--mutate')) {
  console.log('\n  MUTATION CONTROLS — a surviving mutant means the check above it is inert.\n');
  let caught = 0;
  const names = Object.keys(MUTANTS);
  for (const name of names) {
    let out;
    try { out = run(MUTANTS[name](SRC0)); }
    catch (e) { out = { failures: [`threw: ${String(e && e.message).slice(0, 90)}`] }; }
    const isControl = name.startsWith('CONTROL');
    const killed = out.failures.length > 0;
    if (killed !== isControl) caught++;
    console.log(`  ${killed ? 'CAUGHT   ' : 'SURVIVED '} ${name}`
      + (killed ? `  (${out.failures.length} failure(s), first: ${out.failures[0]})` : ''));
  }
  console.log(`\n  ${caught}/${names.length} scored as intended.`);
  if (caught !== names.length) process.exit(1);
}

process.exit(base.failures.length === 0 ? 0 : 1);
