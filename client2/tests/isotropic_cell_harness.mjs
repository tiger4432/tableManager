/**
 * 🎯 Equal millimetres-per-pixel on both canvas axes — and what that must NOT move.
 *
 * SCORES FOUR CLAIMS, by executing the shipped `renderGridCanvas` (no model of it) and
 * reading the CANVAS CALLS it actually made:
 *
 *   ① CIRCULARITY. The wafer outline is a CIRCLE: its rendered pixel radii are equal on both
 *      axes, at every canvas aspect and every chip-pitch ratio. Measured from the `ellipse()`
 *      arguments the render passed to the 2D context, not from a formula re-derived here.
 *
 *   ② VALUE NEUTRALITY, PER CELL. Every die's key -> coordinate -> value is byte-identical to
 *      what the pre-change geometry produced. The comparison is key-by-key over the whole
 *      screen; a count is not evidence (four differently-misread frames produced the same
 *      854-cell total this week while disagreeing on 341/108/41/284 individual dies).
 *      The DIFFERENTIAL against a plausible misreading is reported alongside, and asserted
 *      non-zero: if a wrong frame moved zero dies, the fixture proves nothing.
 *
 *   ③ THE SCREEN AND THE MASK AGREE. Every cell the render painted as a valid die lies inside
 *      the effective-radius ellipse the render DREW. This is the assertion that catches a
 *      centring error: `isCellInsideWaferFast` is deliberately untouched and answers in pure
 *      mm, so if the lattice and the circle stop sharing a centre, only this notices.
 *
 *   ④ OFF THE DECLARED GRID IS NOT THE MAP. Cells drawn to fill the canvas margin are not
 *      registered, not counted, not savable, not writable, and not painted like a declared
 *      cell. All five are scored separately, because four of them are silent.
 *
 * FIXTURE AXES, all live on purpose (asserted in `fixtureSelfCheck`, never assumed):
 *    chipX 9 != chipY 11        a pitch swap is a real difference; a square pitch would make
 *                               the whole defect axis invisible
 *    cols 15 != rows 11         a transposed read cannot pass on width
 *    startX 4 != startY -2      one negative; an axis swap or a shared offset cannot pass
 *    invertY on, rotation 270   the brief's "other terms are non-zero" — the round that
 *                               skipped these shipped a bbox defect a zero would have hidden
 *    canvas 900x380             non-square, so `padX`/`padY` are BOTH exercised across the
 *                               aspect sweep and neither can be silently zero
 *
 * Run:  node client2/tests/isotropic_cell_harness.mjs [--mutate] [-v]
 * Read-only against client2/. Executed by client2/scripts/check_harnesses.mjs.
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

const SYMBOLS = [
  'physNum', 'gridDimNum', 'withPhysFrame',
  // [2b] `physDeclaration` no longer spells "did this control say anything" inline: that
  // question is now shared with the grid-frame reader, so it is one function and it is here.
  'controlIsSilent',
  'geometryIsAutoRegistered', 'markGeometryAutoRegistered', 'physDeclaration', 'frameFromMeta',
  'cellMetrics',                                   // THE function under test
  'getScreenShift', 'getTransformedPhysicalConfig', 'isCellInsideWaferFast',
  'getDieIndex', 'getCanvasCellFromDieIndex',
  'validDieBasis', 'isValidDieAt',
  'getWaferBoundingBox', 'getDbCoords', 'getCanvasCellFromDb',
  'cellFillColor', 'isProtectedFCell', 'eachSavableCell',
  'seatingSnapshot', 'getGridCellObject',
  'renderGridCanvas', 'getGridCellFromMouseEvent', 'handleCellClick',
];

// ── Fixture ────────────────────────────────────────────────────────────────────────────
const COLS = 15, ROWS = 11;
const CHIP_X = 9, CHIP_Y = 11;
const DIA = 116, MARGIN = 3;
const START_X = 4, START_Y = -2;

// Distinct sentinel colours, one per theme token. The render's own `cellFillColor` decides
// which one a cell gets, so reading the recorded fillStyle back is reading the render's
// verdict — not re-deriving it here.
const TOK = {
  outBg: '#T-outBg', line: '#T-line', lineStrong: '#T-lineStrong',
  insideEmpty: '#T-insideEmpty', textEmpty: '#T-textEmpty', textOut: '#T-textOut',
  waferEdge: '#T-waferEdge', wmFront: '#T-wmFront', wmBack: '#T-wmBack',
  accent: '#T-accent', danger: '#T-danger', dangerWeak: '#T-dangerWeak',
  rangeFill: '#T-rangeFill', surface: '#T-surface', success: '#T-success', warning: '#T-warning',
};

function makeInput(v) {
  // [D1] `dataset` is REAL here, not a stub object shared between inputs: the auto-registered
  // mark lives on the chip inputs' dataset, and a shared object would make "mark chipX" look
  // like "mark chipY" too — the joint condition would then pass for free.
  return { value: String(v), checked: false, textContent: '', disabled: false, style: {},
           dataset: {},
           classList: { add() {}, remove() {}, toggle() {} },
           querySelector: () => null, appendChild() {},
           addEventListener() {}, removeEventListener() {} };
}

// A 2D context that RECORDS. Fill/stroke styles are real properties, so every recorded rect
// carries the colour the render chose for it.
function recordingCtx(rec) {
  const st = { fillStyle: '', strokeStyle: '', lineWidth: 1, font: '', textAlign: '', textBaseline: '' };
  const noop = () => {};
  // 🔴 The colour is read at `stroke()`, NOT at `ellipse()`. The shipped order is
  //    beginPath -> ellipse -> strokeStyle = ... -> stroke, so tagging at `ellipse()` time
  //    records the PREVIOUS path's colour and every ellipse lookup misses. Measured: the
  //    first draft of this harness reported "no wafer ellipse" on all 16 cases while the
  //    render had drawn 2 each.
  let pending = null;
  return {
    save: noop, restore: noop, scale: noop, clearRect: noop, moveTo: noop, lineTo: noop,
    fill: noop, setLineDash: noop,
    beginPath: () => { pending = null; },
    stroke: () => { if (pending) { pending.color = st.strokeStyle; pending = null; } },
    fillText: noop, measureText: () => ({ width: 0 }), arc: (...a) => rec.arcs.push(a),
    ellipse: (cx, cy, rx, ry) => { pending = { cx, cy, rx, ry, color: null }; rec.ellipses.push(pending); },
    fillRect: (x, y, w, h) => rec.fillRects.push({ x, y, w, h, color: st.fillStyle }),
    strokeRect: (x, y, w, h) => rec.strokeRects.push({ x, y, w, h, color: st.strokeStyle, lw: st.lineWidth }),
    get fillStyle() { return st.fillStyle; }, set fillStyle(v) { st.fillStyle = v; },
    get strokeStyle() { return st.strokeStyle; }, set strokeStyle(v) { st.strokeStyle = v; },
    get lineWidth() { return st.lineWidth; }, set lineWidth(v) { st.lineWidth = v; },
    get font() { return st.font; }, set font(v) { st.font = v; },
    get textAlign() { return st.textAlign; }, set textAlign(v) { st.textAlign = v; },
    get textBaseline() { return st.textBaseline; }, set textBaseline(v) { st.textBaseline = v; },
  };
}

function buildEnv(src, opts = {}) {
  const pieces = [];
  for (const name of SYMBOLS) {
    const code = sliceFunction(src, name);
    if (!code) die(`'${name}' is gone from map_editor.js — renamed or reshaped. Nothing compared.`);
    try { new vm.Script(code); }
    catch (e) { die(`slice of '${name}' does not parse: ${e && e.message}`); }
    pieces.push(code);
  }
  const p = opts.panel || {};
  const rec = { ellipses: [], arcs: [], fillRects: [], strokeRects: [] };
  const canvas = opts.canvas || { w: 700, h: 700 };
  const el = {
    gridCols: makeInput(p.cols === undefined ? COLS : p.cols),
    gridRows: makeInput(p.rows === undefined ? ROWS : p.rows),
    gridStartX: makeInput(p.startX === undefined ? START_X : p.startX),
    gridStartY: makeInput(p.startY === undefined ? START_Y : p.startY),
    gridYInvert: { checked: !!p.invertY },
    physWaferDia: { value: String(p.dia === undefined ? DIA : p.dia),
                    querySelector: () => null, appendChild() {} },
    // `chipX: null` is how an UNDECLARED pitch arrives (loadExistingMap assigns the meta
    // value straight onto .value, and a null meta field lands as the empty string).
    physChipX: makeInput(p.chipX === undefined ? CHIP_X : (p.chipX === null ? '' : p.chipX)),
    physChipY: makeInput(p.chipY === undefined ? CHIP_Y : (p.chipY === null ? '' : p.chipY)),
    // [D1] `autoRegistered: true` puts the panel in the state `loadExistingMap` leaves it in
    // after loading a metadata row that carries `auto_registered: true` — the synthesized
    // numbers are IN the inputs (that is the whole difficulty), and only the mark says they
    // were never measured.
    physOffsetX: makeInput(p.offsetX || 0), physOffsetY: makeInput(p.offsetY || 0),
    physEdgeMargin: makeInput(p.margin === undefined ? MARGIN : p.margin),
    gridCanvas: { getBoundingClientRect: () => ({ width: canvas.w, height: canvas.h, left: 0, top: 0 }),
                  classList: { add() {}, remove() {} } },
    waferCanvas: { width: 0, height: 0, getContext: () => recordingCtx(rec),
                   getBoundingClientRect: () => ({ width: canvas.w, height: canvas.h, left: 0, top: 0 }) },
    showAnnotations: { checked: false },
    cellAspectNote: { style: { display: 'none' }, textContent: '' },
    gridStatusCoords: { textContent: '' },
    btnSetOrigin: { classList: { add() {}, remove() {} }, style: {} },
  };
  const sandbox = {
    console: { warn() {}, info() {}, error() {}, log() {}, debug() {} },
    el,
    document: { querySelectorAll: () => [], getElementById: () => null,
                addEventListener() {}, removeEventListener() {} },
    setTimeout, physFrameOverride: null, boundingBoxCache: {}, cellsSeatedUnder: null,
    currentRotation: p.rotation || 0, currentSide: p.side || 'front',
    gridData: opts.gridData || {}, gridCells2D: {}, legend: opts.legend || [],
    activeBrush: opts.activeBrush === undefined ? 'A' : opts.activeBrush,
    validDie: { basis: 'circle', keys: null, reason: '', ref: null, raw: undefined },
    validDieResolveSeq: 0, loadedFCells: new Set(),
    overlayLayers: [], activeOverlayLayers: [],
    UNLISTED_VALUE_FILL: '#T-unlisted',
    paintLockValues: null, paintLockConfig: { enabled: false }, currentHoverCell: null,
    lastSelectionBox: null, isBoxDragging: false, dragType: null, isOriginMode: false,
    isRightDrag: false,
    performance: { now: () => 0 }, window: { devicePixelRatio: 1 },
    getComputedStyle: () => ({ getPropertyValue: () => '#000' }),
    getThemeColors: () => TOK,
    // `isProtectedFCell` reaches this on every edit path. Without it, the ④d mutation run
    // aborts on a ReferenceError BEFORE its own assertions execute — it still reads as
    // "caught", but by the wrong thing, and the claim goes unscored.
    isOverlayLocked: () => false,
    syncOverlayGeometry() {}, drawOverlayMarkers() {}, updateNotchPosition() {},
    updateLegendCounts() {}, scheduleRenderGridCanvas() {}, scheduleCellDraft() {},
    rec, canvas,
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  try { vm.runInContext(pieces.join('\n'), sandbox); }
  catch (e) { die(`extracted sources did not evaluate: ${e && e.message}`); }
  // [D1] Applied through the PRODUCT's own writer, never by poking the dataset here. A
  // fixture that set the key itself would still pass if `markGeometryAutoRegistered` wrote
  // somewhere the reader does not look — the two halves have to meet in the product.
  if (p.autoRegistered) sandbox.markGeometryAutoRegistered(true);
  return { sandbox, el, rec };
}

// ── Scoring ────────────────────────────────────────────────────────────────────────────
let failures = [];
let compared = 0;
const VERBOSE = process.argv.includes('-v');
function ok(cond, name, detail) {
  compared++;
  if (!cond) failures.push(`${name}${detail ? ` — ${detail}` : ''}`);
  else if (VERBOSE) console.log(`  ok  ${name}`);
}
const eq = (name, expected, actual, note) => {
  compared++;
  const a = JSON.stringify(actual), e = JSON.stringify(expected);
  if (a !== e) failures.push(`${name}: expected ${e}, got ${a}${note ? ` — ${note}` : ''}`);
  else if (VERBOSE) console.log(`  ok  ${name}`);
};

const EPS = 1e-6;
const near = (a, b, eps = 1e-6) => Math.abs(a - b) <= eps;

// Every cell object the render produced, flattened. THE SCREEN.
const screenCells = (S) => {
  const out = [];
  Object.keys(S.gridCells2D || {}).forEach(rS =>
    Object.keys(S.gridCells2D[rS] || {}).forEach(cS => {
      const co = S.gridCells2D[rS][cS];
      if (co) out.push(co);
    }));
  return out;
};

// key -> "x,y=value". A per-cell fingerprint of the screen; NEVER a count.
const cellMap = (S) => {
  const m = {};
  screenCells(S).forEach(co => { m[co.key] = `${co.x},${co.y}|${co.inside ? 'in' : 'out'}|${S.gridData[co.key] || ''}`; });
  return m;
};

// THE PAYLOAD, not a model of it.
const payload = (S) => {
  const out = {};
  S.eachSavableCell((co, val) => { out[co.key] = `${co.x},${co.y}=${val}`; });
  return out;
};

function render(src, opts) {
  const env = buildEnv(src, opts);
  env.sandbox.renderGridCanvas();
  return env;
}

// ── ① CIRCULARITY, across canvas aspects x pitch ratios ────────────────────────────────
const ASPECTS = [
  { w: 700, h: 700, tag: '700x700' },
  { w: 900, h: 380, tag: '900x380' },
  { w: 380, h: 900, tag: '380x900' },
  { w: 1280, h: 520, tag: '1280x520' },
];
const PITCHES = [
  { chipX: 9, chipY: 11, tag: '9x11' },
  { chipX: 11, chipY: 9, tag: '11x9' },
  { chipX: 2.5, chipY: 2.5, tag: '2.5x2.5' },
  { chipX: 7, chipY: 3, tag: '7x3' },
];

function scoreCircularity(src, evidence) {
  for (const a of ASPECTS) {
    for (const pit of PITCHES) {
      const { rec } = render(src, { canvas: a, panel: { chipX: pit.chipX, chipY: pit.chipY } });
      const outer = rec.ellipses.find(e => e.color === TOK.waferEdge);
      const eff = rec.ellipses.find(e => e.color === TOK.success);
      if (!outer || !eff) {
        ok(false, `① ${a.tag} pitch ${pit.tag}: the render drew no wafer ellipse`,
           `recorded ${rec.ellipses.length} ellipse(s)`);
        continue;
      }
      // The pixel extents on both axes, straight off the draw call.
      ok(near(outer.rx, outer.ry, 1e-9),
         `① ${a.tag} pitch ${pit.tag}: outer wafer circle is round`,
         `rx ${outer.rx.toFixed(4)} vs ry ${outer.ry.toFixed(4)} (ratio ${(outer.rx / outer.ry).toFixed(6)})`);
      ok(near(eff.rx, eff.ry, 1e-9),
         `① ${a.tag} pitch ${pit.tag}: effective-radius circle is round`,
         `rx ${eff.rx.toFixed(4)} vs ry ${eff.ry.toFixed(4)} (ratio ${(eff.rx / eff.ry).toFixed(6)})`);
      evidence.push(`  ${a.tag.padEnd(9)} pitch ${pit.tag.padEnd(8)} outer rx/ry = `
        + `${outer.rx.toFixed(2)}/${outer.ry.toFixed(2)} ratio ${(outer.rx / outer.ry).toFixed(6)}`
        + `   eff ${eff.rx.toFixed(2)}/${eff.ry.toFixed(2)} ratio ${(eff.rx / eff.ry).toFixed(6)}`);
    }
  }
}

// ── ③ The lattice and the drawn circle share a centre ──────────────────────────────────
// Read entirely off the recorded draw calls: the cell rectangles the render filled, and the
// ellipse it stroked. If `padX`/`padY` were dropped or halved, the grid slides off the circle
// and cells the mask calls valid stop being under it.
function scoreScreenMaskAgreement(src, tag, opts) {
  const { sandbox: S, rec } = render(src, opts);
  const eff = rec.ellipses.find(e => e.color === TOK.success);
  if (!eff) { ok(false, `③ ${tag}: no effective-radius ellipse recorded`); return; }

  // A cell's own rectangle, as drawn (step 1 of the loop is the first fillRect at that spot).
  const byXY = new Map();
  rec.fillRects.forEach(f => { const k = `${f.x.toFixed(4)}_${f.y.toFixed(4)}`; if (!byXY.has(k)) byXY.set(k, f); });
  const cells = [...byXY.values()];
  ok(cells.length > 0, `③ ${tag}: the render filled at least one cell rectangle`);

  let insideDrawn = 0, escaped = [];
  for (const f of cells) {
    if (f.color === TOK.outBg) continue;              // the render's own verdict: not a die
    insideDrawn++;
    const corners = [[f.x, f.y], [f.x + f.w, f.y], [f.x, f.y + f.h], [f.x + f.w, f.y + f.h]];
    for (const [x, y] of corners) {
      const d = ((x - eff.cx) / eff.rx) ** 2 + ((y - eff.cy) / eff.ry) ** 2;
      if (d > 1 + 1e-6) { escaped.push(`(${x.toFixed(1)},${y.toFixed(1)}) d=${d.toFixed(4)}`); break; }
    }
  }
  ok(insideDrawn > 0, `③ ${tag}: at least one cell was painted as a valid die`,
     `${cells.length} cell rects, none of them a die — the fixture cannot score this claim`);
  eq(`③ ${tag}: every painted die lies inside the DRAWN effective circle`, [], escaped.slice(0, 8),
     `${escaped.length} of ${insideDrawn} escaped`);
}

// ── ④ Off the declared grid ────────────────────────────────────────────────────────────
function scoreOffGrid(src, tag, opts) {
  const { sandbox: S, rec, el } = render(src, opts);
  const cols = opts.panel && opts.panel.cols !== undefined ? opts.panel.cols : COLS;
  const rows = opts.panel && opts.panel.rows !== undefined ? opts.panel.rows : ROWS;
  const rot90 = (S.currentRotation === 90 || S.currentRotation === 270);
  const vCols = rot90 ? rows : cols, vRows = rot90 ? cols : rows;

  // ④a NOT REGISTERED. The domain of `eachSavableCell` is `gridCells2D`, so this one line
  //    is what makes the other four true.
  const off = screenCells(S).filter(co => co.c < 0 || co.c >= vCols || co.r < 0 || co.r >= vRows);
  eq(`④a ${tag}: no off-grid cell object is registered`, [], off.slice(0, 8).map(co => `c${co.c},r${co.r}`),
     `${off.length} registered`);

  // ④b NOT DRAWN LIKE A DECLARED CELL. Declared cells always get a fill; filler cells get a
  //    lattice stroke and no fill. Compare the two populations by coordinate, not by count.
  const metrics = S.cellMetrics(Math.floor(opts.canvas.w), Math.floor(opts.canvas.h), vCols, vRows,
    S.getTransformedPhysicalConfig(null, S.currentRotation, S.currentSide));
  const shift = S.getScreenShift(S.getTransformedPhysicalConfig(null, S.currentRotation, S.currentSide),
    metrics.cellW, metrics.cellH);
  const originX = shift.shiftX + metrics.padX, originY = shift.shiftY + metrics.padY;
  const toCell = (f) => ({ c: Math.round((f.x - originX) / metrics.cellW),
                           r: Math.round((f.y - originY) / metrics.cellH) });
  const filled = new Set();
  rec.fillRects.forEach(f => {
    if (!near(f.w, metrics.cellW, 1e-6) || !near(f.h, metrics.cellH, 1e-6)) return;
    const { c, r } = toCell(f);
    filled.add(`${c}_${r}`);
  });
  const filledOffGrid = [...filled].filter(k => {
    const [c, r] = k.split('_').map(Number);
    return c < 0 || c >= vCols || r < 0 || r >= vRows;
  });
  eq(`④b ${tag}: no off-grid cell is FILLED (declared cells always are)`, [], filledOffGrid.slice(0, 8),
     `${filledOffGrid.length} filled off-grid`);

  const strokedOffGrid = new Set();
  rec.strokeRects.forEach(f => {
    if (!near(f.w, metrics.cellW, 1e-6) || !near(f.h, metrics.cellH, 1e-6)) return;
    const { c, r } = toCell(f);
    if (c < 0 || c >= vCols || r < 0 || r >= vRows) strokedOffGrid.add(`${c}_${r}`);
  });

  // ④c NOT COUNTED / NOT SAVED. Paint every physical key the wafer covers — including the
  //    off-grid ones — and check the payload holds only declared coordinates.
  const declaredKeys = new Set();
  for (let r = 0; r < vRows; r++) for (let c = 0; c < vCols; c++) {
    declaredKeys.add(`${S.getDieIndex(null, c, r, cols, rows, S.currentRotation, S.currentSide).x}_`
      + `${S.getDieIndex(null, c, r, cols, rows, S.currentRotation, S.currentSide).y}`);
  }
  for (let r = -3; r < vRows + 3; r++) for (let c = -3; c < vCols + 3; c++) {
    const p = S.getDieIndex(null, c, r, cols, rows, S.currentRotation, S.currentSide);
    S.gridData[`${p.x}_${p.y}`] = 'A';
  }
  S.renderGridCanvas();
  const pay = payload(S);
  const strays = Object.keys(pay).filter(k => !declaredKeys.has(k));
  eq(`④c ${tag}: the save payload holds no undeclared coordinate`, [], strays.slice(0, 8),
     `${strays.length} stray of ${Object.keys(pay).length} saved`);

  return { offGridStroked: strokedOffGrid.size, metrics, vCols, vRows };
}

// ④d NOT WRITABLE. The mouse path is the only way a human creates a cell, and it is scored by
//    calling it — the click is delivered at real pixel coordinates inside the margin.
function scoreOffGridNotWritable(src, tag, opts) {
  const { sandbox: S } = render(src, opts);
  const cols = COLS, rows = ROWS;
  const rot90 = (S.currentRotation === 90 || S.currentRotation === 270);
  const vCols = rot90 ? rows : cols, vRows = rot90 ? cols : rows;
  const cfg = S.getTransformedPhysicalConfig(null, S.currentRotation, S.currentSide);
  const m = S.cellMetrics(Math.floor(opts.canvas.w), Math.floor(opts.canvas.h), vCols, vRows, cfg);
  const sh = S.getScreenShift(cfg, m.cellW, m.cellH);
  const oX = sh.shiftX + m.padX, oY = sh.shiftY + m.padY;

  // A point in the LEFT margin and one in the TOP margin, whichever exists for this canvas.
  const probes = [];
  if (m.padX > 1) probes.push({ where: 'left margin', x: oX - m.cellW / 2, y: oY + m.cellH / 2 });
  if (m.padX > 1) probes.push({ where: 'right margin', x: oX + vCols * m.cellW + m.cellW / 2, y: oY + m.cellH / 2 });
  if (m.padY > 1) probes.push({ where: 'top margin', x: oX + m.cellW / 2, y: oY - m.cellH / 2 });
  if (m.padY > 1) probes.push({ where: 'bottom margin', x: oX + m.cellW / 2, y: oY + vRows * m.cellH + m.cellH / 2 });
  ok(probes.length > 0, `④d ${tag}: the fixture actually has a margin to click in`,
     `padX ${m.padX.toFixed(2)} padY ${m.padY.toFixed(2)} — with no margin this claim is unscored`);

  for (const p of probes) {
    const cell = S.getGridCellFromMouseEvent({ clientX: p.x, clientY: p.y, button: 0, buttons: 1 });
    eq(`④d ${tag}: a click in the ${p.where} resolves to no cell`, null, cell,
       cell ? `got c${cell.c},r${cell.r} key ${cell.key}` : '');
    const before = JSON.stringify(S.gridData);
    S.handleCellClick(cell, { button: 0, buttons: 1 });
    eq(`④d ${tag}: a click in the ${p.where} writes nothing`, before, JSON.stringify(S.gridData));
  }

  // ...and the same call INSIDE the grid still works, or the assertion above is vacuous.
  const inside = S.getGridCellFromMouseEvent({ clientX: oX + m.cellW / 2, clientY: oY + m.cellH / 2, button: 0, buttons: 1 });
  ok(inside !== null, `④d ${tag}: a click INSIDE the declared grid still resolves to a cell`,
     'the null above would otherwise prove only that the hit test is broken');
}

// ── ② Per-cell value neutrality + the differential ─────────────────────────────────────
// The "before" is produced by putting the DEFECT BACK: `cellMetrics` forced to its
// pre-change, anisotropic form. Same source, same fixture, one function's body swapped.
// Re-pointed 2026-08-04 (wafer-anchored scale): the isotropic scale is now `min(sGrid, sWafer)`
// and the old one-line anchor no longer matches. A `find` string that no longer matches is a
// SILENT HOLE, not a pass -- `applyMutation` refuses a non-1 match count for exactly that
// reason, and it is what caught this.
const ANISOTROPIC_REVERT = {
  find: `  const sGrid = Math.min(width / (visualCols * chipX), height / (visualRows * chipY));`,
  repl: `  return anisotropicFallback;\n  const sGrid = Math.min(width / (visualCols * chipX), height / (visualRows * chipY));`,
};

function scoreValueNeutrality(src, evidence) {
  const opts = {
    canvas: { w: 900, h: 380 },
    panel: { rotation: 270, invertY: true, startX: START_X, startY: START_Y,
             chipX: CHIP_X, chipY: CHIP_Y, offsetX: 2.5, offsetY: -1.5 },
  };
  // Paint every cell with its own visual coordinate, so the comparison is against a number
  // the geometry never touched (the row's own value is the second oracle).
  const seed = (S) => {
    screenCells(S).forEach(co => { S.gridData[co.key] = `${co.x},${co.y}`; });
    S.renderGridCanvas();
  };

  const before = buildEnv(applyMutation(src, ANISOTROPIC_REVERT, 'anisotropic revert'), opts);
  before.sandbox.renderGridCanvas(); seed(before.sandbox);
  const after = buildEnv(src, opts);
  after.sandbox.renderGridCanvas(); seed(after.sandbox);

  const A = cellMap(before.sandbox), B = cellMap(after.sandbox);
  const keys = [...new Set([...Object.keys(A), ...Object.keys(B)])].sort();
  const moved = keys.filter(k => A[k] !== B[k]);
  eq('② every die is key-for-key identical to the pre-change geometry', [], moved.slice(0, 10),
     `${moved.length} of ${keys.length} dies differ`);
  eq('② the save payload is identical to the pre-change geometry',
     JSON.stringify(payload(before.sandbox)), JSON.stringify(payload(after.sandbox)));
  ok(keys.length > 100, '② the fixture actually seats a meaningful number of dies',
     `only ${keys.length} — too few to prove anything`);

  // THE DIFFERENTIAL. A plausible misreading that keeps the SAME cell count: the two chip
  // pitches swapped. If this moved zero dies, the fixture's pitch axis is dead and the
  // agreement above is worth nothing.
  const wrong = buildEnv(src, { ...opts, panel: { ...opts.panel, chipX: CHIP_Y, chipY: CHIP_X } });
  wrong.sandbox.renderGridCanvas(); seed(wrong.sandbox);
  const W = cellMap(wrong.sandbox);
  const wKeys = [...new Set([...Object.keys(B), ...Object.keys(W)])];
  const differ = wKeys.filter(k => B[k] !== W[k]);
  ok(differ.length > 0, '② a swapped pitch moves at least one die (the fixture axis is live)',
     'zero dies moved — a wrong frame is indistinguishable here, so nothing above is evidence');
  evidence.push(`  per-cell: ${keys.length} dies compared, ${moved.length} changed by this round`);
  evidence.push(`  differential vs swapped pitch (${CHIP_X}x${CHIP_Y} -> ${CHIP_Y}x${CHIP_X}): `
    + `${differ.length} of ${wKeys.length} dies read differently`);
  evidence.push(`  cell counts: before ${Object.keys(A).length}, after ${Object.keys(B).length}, `
    + `misread ${Object.keys(W).length}`);
}

// ── Undeclared pitch ───────────────────────────────────────────────────────────────────
function scoreUndeclaredPitch(src) {
  for (const [tag, panel] of [
    ['both blank', { chipX: null, chipY: null }],
    ['x blank', { chipX: null, chipY: CHIP_Y }],
    ['y blank', { chipX: CHIP_X, chipY: null }],
  ]) {
    const { sandbox: S, el, rec } = render(src, { canvas: { w: 900, h: 380 }, panel });
    const vCols = COLS, vRows = ROWS;
    const m = S.cellMetrics(900, 380, vCols, vRows,
      S.getTransformedPhysicalConfig(null, S.currentRotation, S.currentSide));
    eq(`undeclared pitch (${tag}): no aspect is invented`, false, m.isotropic);
    // ...and the fallback is TODAY'S arithmetic, to the bit.
    eq(`undeclared pitch (${tag}): cellW falls back to width/visualCols`, 900 / vCols, m.cellW);
    eq(`undeclared pitch (${tag}): cellH falls back to height/visualRows`, 380 / vRows, m.cellH);
    eq(`undeclared pitch (${tag}): no letterboxing`, [0, 0], [m.padX, m.padY]);
    ok(el.cellAspectNote.style.display === '' && /미상/.test(el.cellAspectNote.textContent),
       `undeclared pitch (${tag}): the screen says 미상`,
       `display=${JSON.stringify(el.cellAspectNote.style.display)} text=${JSON.stringify(el.cellAspectNote.textContent)}`);
  }
  // ...and it goes away again when the pitch IS declared.
  const { el } = render(src, { canvas: { w: 900, h: 380 }, panel: {} });
  eq('declared pitch: the 미상 note is hidden', 'none', el.cellAspectNote.style.display);
}

// ── Fixture self-check ─────────────────────────────────────────────────────────────────
function fixtureSelfCheck(src) {
  ok(CHIP_X !== CHIP_Y, 'fixture: chip pitch is anisotropic (a square pitch kills the defect axis)');
  ok(COLS !== ROWS, 'fixture: cols != rows');
  ok(START_X !== START_Y && (START_X < 0 || START_Y < 0), 'fixture: start coords differ and one is negative');
  const box = render(src, { panel: {} }).sandbox.getWaferBoundingBox(null, 0, 'front');
  ok(box.minC > 0 || box.minR > 0, 'fixture: the circle bbox has a non-zero minimum (a dropped bbox term cannot hide)',
     `minC ${box.minC} minR ${box.minR}`);
  // The isotropic branch is actually TAKEN — otherwise every claim below scores the fallback.
  const { sandbox: S } = render(src, { canvas: { w: 900, h: 380 }, panel: {} });
  const m = S.cellMetrics(900, 380, COLS, ROWS, S.getTransformedPhysicalConfig(null, 0, 'front'));
  ok(m.isotropic === true, 'fixture: the isotropic branch is the one being executed');
  ok(m.padX > 1 || m.padY > 1, 'fixture: the fixture actually produces a margin to test',
     `padX ${m.padX.toFixed(3)} padY ${m.padY.toFixed(3)}`);
  ok(!near(m.cellW, m.cellH, 1e-6), 'fixture: cells really are rectangular (the intended outcome)',
     `cellW ${m.cellW.toFixed(3)} cellH ${m.cellH.toFixed(3)}`);
}

// ══ [D1] AUTO-REGISTERED GEOMETRY IS NOT A DECLARATION ═══════════════════════════════════
//
// THE RULING (user, 2026-08-04): a synthesized metadata row does not declare geometry, and
// `auto_registered` is the thing that says so. Two writers emit the mask-neutral synthetic
// spec — the server's `synthesize_grid_meta()` on ingestion, and the editor's own `[fix C]`
// for a map with no spec at all. Both write chip 1x1 to mean "no circle", not "a 1mm die".
//
// 🔴 WHY THE FLAG AND NOT THE VALUE. 1 is a LEGAL pitch (this database holds a real 5x5 map),
//    so a value used as a marker can never be told apart from a measurement. Measured on the
//    live database: 320 of 668 registered maps carry chip 1x1, and ALL 320 carry the flag —
//    there are ZERO flagless 1x1 rows, so the legacy fallback this could have needed is
//    provably dead code and is not written.
//
// 🔴 THE FIXTURE'S WHOLE DIFFICULTY: the synthesized numbers ARE in the inputs. A fixture that
//    emptied the chip fields would be scoring the pre-existing 'absent' path and would pass
//    against a build that ignores the flag completely. So every case below holds a perfectly
//    readable pitch and differs ONLY in the mark.
function scoreAutoRegistered(src) {
  const panel = { chipX: 1, chipY: 1, dia: 300, cols: 13, rows: 13 };

  // (a) FLAGGED: readable numbers, but they are not a declaration.
  const flagged = render(src, { canvas: { w: 700, h: 700 }, panel: { ...panel, autoRegistered: true } });
  const dxF = flagged.sandbox.physDeclaration(null, 'chipX', flagged.el.physChipX);
  const dyF = flagged.sandbox.physDeclaration(null, 'chipY', flagged.el.physChipY);
  eq('D1/a a flagged chipX is reported as NOT declared',
    { value: null, source: 'auto_registered' }, dxF);
  eq('D1/a ...and chipY the same (the mark covers the whole spec)',
    { value: null, source: 'auto_registered' }, dyF);
  eq('D1/a the input still visibly holds the number — the mark is the only difference',
    '1', String(flagged.el.physChipX.value),
    'if the fixture emptied the field it would be scoring the old absent path');

  // (b) THE SAME NUMBERS WITHOUT THE FLAG ARE A REAL DECLARATION. This is the discrimination
  //     that makes (a) mean something: a build keyed on the VALUE passes (a) and fails here.
  const bare = render(src, { canvas: { w: 700, h: 700 }, panel });
  eq('D1/b chip 1x1 with NO flag is still a declaration', 'screen',
    bare.sandbox.physDeclaration(null, 'chipX', bare.el.physChipX).source,
    '1 is a legal pitch; only the flag may reclassify it');
  eq('D1/b ...and its value survives', 1,
    bare.sandbox.physDeclaration(null, 'chipX', bare.el.physChipX).value);

  // (c) A FLAGGED SPEC WITH ANISOTROPIC NUMBERS. The mark is about provenance, not shape —
  //     scored so nobody "optimises" the rule back into a 1x1 value check.
  const aniso = render(src, { canvas: { w: 700, h: 700 },
    panel: { ...panel, chipX: 1, chipY: 8, autoRegistered: true } });
  eq('D1/c the mark reclassifies a 1x8 spec too (provenance, not shape)', 'auto_registered',
    aniso.sandbox.physDeclaration(null, 'chipY', aniso.el.physChipY).source);
  const anisoBare = render(src, { canvas: { w: 700, h: 700 }, panel: { ...panel, chipX: 1, chipY: 8 } });
  eq('D1/c ...while an UNFLAGGED 1x8 stays the real anisotropic declaration it is', 'screen',
    anisoBare.sandbox.physDeclaration(null, 'chipY', anisoBare.el.physChipY).source);

  // (d) WHAT THE OPERATOR SEES. `cellMetrics` falls back, and the note says WHY in its own
  //     words — "Chip X/Y 미선언" would be read as false by anyone looking at the inputs.
  const mF = flagged.sandbox.cellMetrics(700, 700, 13, 13,
    flagged.sandbox.getTransformedPhysicalConfig(null, 0, 'front'));
  eq('D1/d a flagged spec does NOT anchor the canvas to a wafer', false, mF.isotropic);
  eq('D1/d ...and does not claim a wafer anchor either', false, mF.waferAnchored);
  ok(/자동 등록/.test(flagged.el.cellAspectNote.textContent),
    'D1/d the note names AUTO-REGISTRATION as the reason',
    `note: ${JSON.stringify(flagged.el.cellAspectNote.textContent)}`);
  ok(!/Chip X\/Y 미선언/.test(flagged.el.cellAspectNote.textContent),
    'D1/d ...and does not say the fields are empty, because they are not');
  eq('D1/d the note is visible', '', flagged.el.cellAspectNote.style.display);

  // (e) THE RECLASSIFICATION IS VISIBLE IN PIXELS, and in the direction the census predicts.
  //     Before: the synthetic 300mm diameter anchored the scale, so a 13x13 grid at 1mm pitch
  //     rendered as a speck inside a canvas-filling circle. After: the grid fills the canvas.
  const mBare = bare.sandbox.cellMetrics(700, 700, 13, 13,
    bare.sandbox.getTransformedPhysicalConfig(null, 0, 'front'));
  ok(mBare.cellW < 5, 'D1/e fixture: unflagged, the synthetic diameter really does shrink the grid',
     `cellW ${mBare.cellW.toFixed(3)}px`);
  ok(mF.cellW > 40, 'D1/e flagged, the grid fills the canvas instead',
     `cellW ${mF.cellW.toFixed(3)}px`);
  ok(mF.cellW / mBare.cellW > 10,
     'D1/e the axis is ACTIVE — the two paths differ by more than a rounding',
     `${mBare.cellW.toFixed(3)} -> ${mF.cellW.toFixed(3)} px per cell`);

  // (f) THE MARK IS CLEARABLE, and clearing it restores a declaration. Without this a build
  //     that marks everything forever would pass every case above.
  flagged.sandbox.markGeometryAutoRegistered(false);
  eq('D1/f clearing the mark makes the same numbers a declaration again', 'screen',
    flagged.sandbox.physDeclaration(null, 'chipX', flagged.el.physChipX).source,
    'the operator typing a real pitch must not stay reclassified');

  // (g) THE FRAME WINDOW. Overlays read the SOURCE map's spec through `physFrameOverride`,
  //     so the mark has to travel on the frame object or the source's synthetic 1mm pitch is
  //     read as real and every marker is placed against it.
  const inFrame = bare.sandbox.physDeclaration({ chipX: 1, chipY: 1, autoRegistered: true }, 'chipX', bare.el.physChipX);
  eq('D1/g a flagged SOURCE FRAME is not declared either', 'auto_registered', inFrame.source);
  const inFrameBare = bare.sandbox.physDeclaration({ chipX: 1, chipY: 1 }, 'chipX', bare.el.physChipX);
  eq('D1/g ...and an unflagged frame still declares', 'frame', inFrameBare.source);
  // The frame window must not be answered by the SCREEN's mark: those are different maps.
  bare.sandbox.markGeometryAutoRegistered(true);
  const screenMarkedFrameNot = bare.sandbox.physDeclaration({ chipX: 7, chipY: 9 }, 'chipX', bare.el.physChipX);
  eq('D1/g the SOURCE frame answers for the source, not the screen behind it', 'frame',
    screenMarkedFrameNot.source,
    'reading the screen mark inside a frame window would reclassify a real source spec');
  bare.sandbox.markGeometryAutoRegistered(false);

  // (h) THE FLAG HAS TO SURVIVE THE WHITELIST. `frameFromMeta` rebuilds the frame key by key,
  //     so a stored `auto_registered: true` reaches the overlay path only if it is copied
  //     across explicitly. It was not, before this round.
  const fm = bare.sandbox.frameFromMeta({
    grid_cols: 13, grid_rows: 13, phys_chip_x: 1, phys_chip_y: 1, auto_registered: true });
  eq('D1/h frameFromMeta carries the mark onto the frame', true, fm.autoRegistered,
    'dropped here, the source map\'s synthetic 1mm pitch is read as a real one');
  const fmNo = bare.sandbox.frameFromMeta({ grid_cols: 13, grid_rows: 13, phys_chip_x: 7 });
  eq('D1/h ...and does not invent it for a normal metadata row', false, fmNo.autoRegistered);

  // (i) BOTH AXES CARRY THE MARK. Scored so that the write to the second input is load-bearing
  //     — an unread write rots silently, and the two halves would then disagree unnoticed.
  const half = render(src, { canvas: { w: 700, h: 700 }, panel: { ...panel, autoRegistered: true } });
  delete half.el.physChipY.dataset.autoRegistered;
  eq('D1/i a mark on only one axis does NOT reclassify the spec', 'screen',
    half.sandbox.physDeclaration(null, 'chipX', half.el.physChipX).source,
    'the mark belongs to the spec, so half a mark is not one');
}

// ── Mutation plumbing ──────────────────────────────────────────────────────────────────
// 🔴 THE ANCHOR MUST BE UNIQUE. A `replace` on a non-unique string lands on the FIRST match,
//    which in this file has already once been inside a COMMENT — the harness then scored a
//    different function and reported green. So uniqueness is asserted, not hoped for.
function applyMutation(src, mut, name) {
  const n = src.split(mut.find).length - 1;
  if (n !== 1) die(`mutation anchor for '${name}' matches ${n} times, not 1. `
    + `A non-unique anchor lands on the first match and scores the wrong code.`);
  const out = src.replace(mut.find, mut.repl);
  if (out === src) die(`mutation '${name}' produced an identical source — nothing was injected`);
  // CONFIRM THE MUTATED STATE, not merely that something changed: later code in this file has
  // repaired an injected defect before, and a green run then meant "there was no mutation".
  if (out.split(mut.repl).length - 1 !== 1) die(`mutation '${name}': the replacement is not present exactly once`);
  return out;
}

const MUTATIONS = [
  ['① the cell metric goes back to filling the canvas per axis (the shipped defect)', ANISOTROPIC_REVERT],
  // ── [D1] Five ways to get the auto-registration rule wrong. ──────────────────────────
  // The rule is not applied at all — the shipped state before this round, in which a
  // synthesized 1mm pitch and a measured one are byte-identical to every reader.
  ['D1 the rule is not applied (synthetic geometry reads as declared)', {
    find: `  if ((key === 'chipX' || key === 'chipY') && geometryIsAutoRegistered(frame)) {\n    return { value: null, source: 'auto_registered' };\n  }`,
    repl: `  // rule removed`,
  }],
  // 🔴 THE MOST IMPORTANT ONE. This is the MAGIC-NUMBER version of the same feature — key the
  //    rule on the chip VALUE being 1x1 instead of on the flag. It satisfies every case that
  //    only looks at flagged maps, and it is wrong: 1 is a legal pitch, so it silently
  //    swallows a real 1mm declaration. Only the unflagged-1x1 discrimination catches it.
  ['D1 the rule keys on the VALUE 1x1 instead of the flag (the sentinel that is also a datum)', {
    find: `  if ((key === 'chipX' || key === 'chipY') && geometryIsAutoRegistered(frame)) {`,
    repl: `  if ((key === 'chipX' || key === 'chipY') && parseFloat(el.physChipX.value) === 1 && parseFloat(el.physChipY.value) === 1) {`,
  }],
  // The frame window answers with the SCREEN's mark. Opening an auto-registered map would
  // then reclassify every OTHER map overlaid onto it — provenance leaking across maps.
  ['D1 the frame window is answered by the screen mark', {
    find: `  if (frame) return frame.autoRegistered === true;`,
    repl: `  if (frame && frame.autoRegistered === true) return true;`,
  }],
  // The mark is dropped by the frame builder's whitelist — where it actually was, before.
  ['D1 frameFromMeta drops the mark (the overlay path stops seeing it)', {
    find: `    autoRegistered: meta.auto_registered === true,`,
    repl: `    autoRegistered: false,`,
  }],
  // The screen keeps the generic wording, which reads as false when the inputs hold numbers.
  ['D1 the note stops naming auto-registration as the reason', {
    find: `      notes.push(geometryIsAutoRegistered(physFrameOverride)\n        ? '기하 규격 미선언 (자동 등록된 합성 규격) — 칩 크기를 잰 적이 없어 웨이퍼 원을 그리지 않습니다'\n        : '셀 종횡비 미상 (Chip X/Y 미선언) — 원이 찌그러져 보입니다');`,
    repl: `      notes.push('셀 종횡비 미상 (Chip X/Y 미선언) — 원이 찌그러져 보입니다');`,
  }],
  // Only one axis is marked. The second write becomes dead, and the two halves can then
  // diverge without anyone noticing.
  ['D1 only one axis gets the mark', {
    find: `  [el.physChipX, el.physChipY].forEach(input => {`,
    repl: `  [el.physChipX].forEach(input => {`,
  }],
  ['③ the grid stops being centred (padX dropped from the render origin)', {
    find: `  const originX = shiftX + padX;\n  const originY = shiftY + padY;`,
    repl: `  const originX = shiftX;\n  const originY = shiftY + padY;`,
  }],
  ['④ off-grid cells are registered again (the guard removed)', {
    find: `      const onGrid = (c >= 0 && c < visualCols && r >= 0 && r < visualRows);\n      if (!onGrid) {`,
    repl: `      const onGrid = (c >= 0 && c < visualCols && r >= 0 && r < visualRows);\n      if (false) {`,
  }],
  ['④d the mouse path admits off-grid coordinates again', {
    find: `  if (c < 0 || c >= visualCols || r < 0 || r >= visualRows) return null;\n\n  if (gridCells2D[r]?.[c]) return gridCells2D[r][c];`,
    repl: `  if (gridCells2D[r]?.[c]) return gridCells2D[r][c];`,
  }],
  ['undeclared pitch is invented from the defaulted number', {
    find: `  const dx = physDeclaration(physFrameOverride, 'chipX', el.physChipX);\n  const dy = physDeclaration(physFrameOverride, 'chipY', el.physChipY);`,
    repl: `  const dx = { value: physNum(physFrameOverride, 'chipX', el.physChipX, 2.5) };\n  const dy = { value: physNum(physFrameOverride, 'chipY', el.physChipY, 2.5) };`,
  }],
];

// ── Run ────────────────────────────────────────────────────────────────────────────────
function scoreAll(src) {
  failures = []; compared = 0;
  const evidence = [];
  fixtureSelfCheck(src);
  scoreCircularity(src, evidence);
  scoreValueNeutrality(src, evidence);
  for (const a of [{ w: 900, h: 380, tag: '900x380' }, { w: 380, h: 900, tag: '380x900' }, { w: 700, h: 700, tag: '700x700' }]) {
    scoreScreenMaskAgreement(src, a.tag, { canvas: a, panel: {} });
    scoreScreenMaskAgreement(src, `${a.tag} rot270 invertY`, { canvas: a, panel: { rotation: 270, invertY: true, offsetX: 2.5, offsetY: -1.5 } });
    const r = scoreOffGrid(src, a.tag, { canvas: a, panel: {} });
    scoreOffGrid(src, `${a.tag} rot270`, { canvas: a, panel: { rotation: 270, invertY: true } });
    scoreOffGridNotWritable(src, a.tag, { canvas: a, panel: {} });
    if (a.tag !== '700x700') {
      ok(r.offGridStroked > 0, `④ ${a.tag}: the margin really is filled with lattice cells`,
         'nothing was stroked off-grid — the canvas would show an empty band');
      evidence.push(`  ${a.tag}: ${r.offGridStroked} off-grid lattice cells drawn to fill the canvas, `
        + `0 registered / 0 filled / 0 saved / 0 writable`);
    }
  }
  scoreUndeclaredPitch(src);
  scoreAutoRegistered(src);
  return evidence;
}

const evidence = scoreAll(SRC0);

console.log('\n── circularity (rendered pixel radii, straight off the draw call) ──');
evidence.filter(l => l.includes('rx/ry')).forEach(l => console.log(l));
console.log('\n── per-cell + off-grid ──');
evidence.filter(l => !l.includes('rx/ry')).forEach(l => console.log(l));

if (failures.length > 0) {
  console.error(`\n✗ ${failures.length} failure(s):`);
  failures.forEach(f => console.error(`   ${f}`));
}

// ── THE FLOOR. Every mutation must be caught, or the harness is decoration. ─────────────
console.log('\n── mutation floor (each defect injected, then scored) ──');
let uncaught = [];
for (const [name, mut] of MUTATIONS) {
  const mutated = applyMutation(SRC0, mut, name);
  let caught = false, threw = '';
  try { scoreAll(mutated); caught = failures.length > 0; }
  // A throw is a red too, but it is REPORTED: a mutation caught only by an exception may be
  // stopping the run before the assertion written for it ever executes.
  catch (e) { caught = true; threw = ` [threw: ${e && e.message}]`; }
  // ATTRIBUTION, not just a tick. "Something went red" is a weaker claim than "the assertion
  // written for this defect went red" — an injected defect that trips only a neighbouring
  // check leaves its own claim unscored.
  const why = failures.slice(0, 3).map(f => f.split(':')[0].split(' — ')[0]);
  console.log(`  ${caught ? '✓ caught' : '✗ MISSED'}  ${name}`
    + (caught ? `\n              first red: ${why.join(' | ')}  (${failures.length} total)${threw}` : ''));
  if (!caught) uncaught.push(name);
}
// Restore the real scoring for the verdict.
failures = []; compared = 0;
scoreAll(SRC0);
uncaught.forEach(n => failures.push(`MUTATION NOT CAUGHT: ${n} — this harness does not score it`));
compared += MUTATIONS.length;

console.log(`\nASSERTIONS ${compared} ${failures.length}`);
if (failures.length > 0) {
  console.error(`\n✗ ${failures.length} failure(s):`);
  failures.forEach(f => console.error(`   ${f}`));
  process.exit(1);
}
console.log('✓ all green');
