/**
 * 🎯 TWO claims about the drawing path, both reported from PRODUCTION on 2026-08-04, both
 *    scored by executing the shipped code and reading the canvas calls it actually made.
 *
 *   ⓦ THE WAFER IS THE ANCHOR. A wafer is the same physical object every time, so its
 *      on-screen size must not be a function of how somebody gridded it. THE HEADLINE, and it
 *      is a single number: several maps with different cols/rows/pitch but the SAME declared
 *      diameter must produce THE SAME circle radius in pixels, to the pixel. Everything else
 *      under ⓦ exists to stop that constant from being bought with something worse:
 *        - the anchor is `phys_wafer_dia`, NOT `effectiveRadius` -- otherwise the same wafer
 *          declared with a different edge margin renders at a different size, and "the same
 *          wafer looks the same" stops being literally true;
 *        - an UNDECLARED diameter falls back to the old grid-anchored rule and SAYS SO. No
 *          default diameter is substituted: an invented physical value that then governs the
 *          whole render is the exact substitution class that produces a perfectly aligned
 *          screen with every value wrong;
 *        - and NO DECLARED CELL EVER LEAVES THE CANVAS. This is not cosmetic. In
 *          `renderGridCanvas` the off-canvas `continue` sits AHEAD of the `gridCells2D`
 *          registration, so a cell pushed off the canvas is never registered, never in
 *          `eachSavableCell`'s domain, and therefore silently absent from the save payload.
 *          That is why the scale is `min(sGrid, sWafer)` and not `sWafer`, and the mutation
 *          sweep puts the bare `sWafer` back and counts the dies it loses.
 *
 *   ⓜ THE MARKER FOLLOWS ITS CELL'S PROPORTIONS. Regression from `941060f`: the overlay
 *      marker radius was `Math.max(1.5, Math.min(cellW, cellH) * 0.13)`, so the SHORTER axis
 *      took the marker hostage the moment cells became genuinely rectangular. Scored as a
 *      RATIO across pitch ratios, never as one fixture's pixel count -- a marker visible at
 *      1:1 and invisible at 1:9 is the defect, and only a ratio can say that. The same `min`
 *      thinking gated the multi-source spread on BOTH axes clearing 10px, so a thin cell also
 *      lost the fan-out and collapsed 6 source chips into one hollow dot.
 *
 * WHAT MUST NOT MOVE, asserted here because this file edits the same painter:
 *   - the value-colour contract (fill = the value's declared legend colour, ring = the layer
 *     colour, an unlisted value gets NO fill, a multi-source dot that cannot be spread stays
 *     hollow even when its items agree);
 *   - a SQUARE cell renders exactly what it rendered before -- same primitive (`arc`, not
 *     `ellipse`), same radius, same centre. Square pitch is the production majority, so the
 *     live-regression fix must be a no-op there.
 *
 * FIXTURE AXES, all live on purpose and asserted in `fixtureSelfCheck`:
 *    chipX != chipY on every marker case      a square pitch makes the whole defect invisible
 *    pitch ratios 1:1 .. 1:30, both ways      the claim is about the RATIO, so it is swept
 *    cols != rows, startX != startY (one -ve) a transposed or shared-offset read cannot pass
 *    canvas 900x380 (non-square)              padX and padY are both exercised
 *    one grid that OVERFLOWS the wafer        the `min(sGrid, sWafer)` branch is executed
 *
 * Run:  node client2/tests/marker_shape_wafer_anchor_harness.mjs [-v]
 * Read-only against client2/. Mutation sweep is unconditional -- there is no flag to forget.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC_PATH = join(HERE, '..', 'src', 'map_editor.js');
// Line endings normalised -- every mutation below matches a multi-line `\n` string and on a
// CRLF checkout those matches silently MISS while the baseline stays green.
const SRC0 = readFileSync(SRC_PATH, 'utf8').replace(/\r\n/g, '\n');
const VERBOSE = process.argv.includes('-v');

const die = (m) => { console.error(`HARNESS FAILURE: ${m}\n(Nothing was compared.)`); process.exit(2); };

function sliceFunction(source, name) {
  const decl = new RegExp(`(^|\\n)\\s*(?:async\\s+)?function\\s+${name}\\s*\\(`);
  const m = decl.exec(source);
  if (!m) die(`'${name}' is gone from map_editor.js -- renamed or reshaped. Nothing compared.`);
  const start = m.index + (m[1] ? m[1].length : 0);
  let i = m.index + m[0].length - 1, paren = 0;
  for (; i < source.length; i++) {
    if (source[i] === '(') paren++;
    else if (source[i] === ')') { paren--; if (paren === 0) { i++; break; } }
  }
  i = source.indexOf('{', i);
  if (i < 0) die(`no body for ${name}`);
  let depth = 0;
  for (; i < source.length; i++) {
    if (source[i] === '{') depth++;
    else if (source[i] === '}') { depth--; if (depth === 0) return source.slice(start, i + 1); }
  }
  die(`unbalanced braces extracting '${name}'`);
}

const SYMBOLS = [
  // [2b] `physDeclaration` no longer spells "did this control say anything" inline: that
  // question is now shared with the grid-frame reader, so it is one function and it is here.
  'controlIsSilent',
  'physNum', 'gridDimNum', 'withPhysFrame', 'geometryIsAutoRegistered', 'physDeclaration',
  'cellMetrics',                                       // THE function under test (ⓦ)
  'getScreenShift', 'getTransformedPhysicalConfig', 'isCellInsideWaferFast',
  'getDieIndex', 'getCanvasCellFromDieIndex',
  'validDieBasis', 'isValidDieAt',
  'getWaferBoundingBox', 'getDbCoords', 'getCanvasCellFromDb',
  'cellFillColor', 'isProtectedFCell', 'eachSavableCell',
  'seatingSnapshot', 'getGridCellObject',
  'declaredLegendRow', 'legendColorForValue', 'overlayMarkerFill',
  'markerAxisRadius', 'paintOverlayDot', 'drawOverlayMarkers',   // THE functions under test (ⓜ)
  'renderGridCanvas', 'getGridCellFromMouseEvent', 'handleCellClick',
];

const TOK = {
  outBg: '#T-outBg', line: '#T-line', lineStrong: '#T-lineStrong',
  insideEmpty: '#T-insideEmpty', textEmpty: '#T-textEmpty', textOut: '#T-textOut',
  waferEdge: '#T-waferEdge', wmFront: '#T-wmFront', wmBack: '#T-wmBack',
  accent: '#T-accent', danger: '#T-danger', dangerWeak: '#T-dangerWeak',
  rangeFill: '#T-rangeFill', surface: '#T-surface', success: '#T-success', warning: '#T-warning',
};
const LAYER_COLOR = '#T-layer';
const HALO = '#ffffff';

const MAP_LEGEND = [
  { value: '1', color: '#10b981', desc: 'good' },
  { value: 'F', color: '#ef4444', desc: 'fail' },
];
const UNLISTED_VAL = 'ZZ9';                            // declared by neither legend source

function makeInput(v) {
  return { value: String(v), checked: false, textContent: '', disabled: false, style: {},
           classList: { add() {}, remove() {}, toggle() {} },
           querySelector: () => null, appendChild() {},
           addEventListener() {}, removeEventListener() {} };
}

// A 2D context that RECORDS every path primitive together with the styles in force when it was
// painted. `arc` and `ellipse` are recorded SEPARATELY: "the painter drew a circle" and "the
// painter drew an ellipse" are different claims and a recorder that folds them cannot tell a
// square-cell no-op from a silently reverted one.
function recordingCtx(rec) {
  const st = { fillStyle: '', strokeStyle: '', lineWidth: 1, font: '', textAlign: '', textBaseline: '' };
  const noop = () => {};
  let pending = null;
  return {
    save: noop, restore: noop, scale: noop, clearRect: noop, moveTo: noop, lineTo: noop,
    setLineDash: noop, fillText: noop, measureText: () => ({ width: 0 }),
    beginPath: () => { pending = null; },
    arc: (cx, cy, r) => { pending = { kind: 'arc', cx, cy, rx: r, ry: r, fill: null, strokes: [] };
                          rec.paths.push(pending); },
    ellipse: (cx, cy, rx, ry) => { pending = { kind: 'ellipse', cx, cy, rx, ry, fill: null, strokes: [] };
                                   rec.paths.push(pending); },
    fill: () => { if (pending) pending.fill = st.fillStyle; },
    stroke: () => { if (pending) pending.strokes.push(st.strokeStyle); },
    fillRect: (x, y, w, h) => rec.fillRects.push({ x, y, w, h, color: st.fillStyle }),
    strokeRect: (x, y, w, h) => rec.strokeRects.push({ x, y, w, h, color: st.strokeStyle }),
    get fillStyle() { return st.fillStyle; }, set fillStyle(v) { st.fillStyle = v; },
    get strokeStyle() { return st.strokeStyle; }, set strokeStyle(v) { st.strokeStyle = v; },
    get lineWidth() { return st.lineWidth; }, set lineWidth(v) { st.lineWidth = v; },
    get font() { return st.font; }, set font(v) { st.font = v; },
    get textAlign() { return st.textAlign; }, set textAlign(v) { st.textAlign = v; },
    get textBaseline() { return st.textBaseline; }, set textBaseline(v) { st.textBaseline = v; },
  };
}

function buildEnv(src, opts = {}) {
  const pieces = SYMBOLS.map(n => {
    const code = sliceFunction(src, n);
    try { new vm.Script(code); } catch (e) { die(`slice of '${n}' does not parse: ${e && e.message}`); }
    return code;
  });
  const p = opts.panel || {};
  const rec = { paths: [], fillRects: [], strokeRects: [] };
  const canvas = opts.canvas || { w: 900, h: 380 };
  const blankable = (v) => (v === null ? '' : v);
  const el = {
    gridCols: makeInput(p.cols === undefined ? 15 : p.cols),
    gridRows: makeInput(p.rows === undefined ? 11 : p.rows),
    gridStartX: makeInput(p.startX === undefined ? 4 : p.startX),
    gridStartY: makeInput(p.startY === undefined ? -2 : p.startY),
    gridYInvert: { checked: !!p.invertY },
    physWaferDia: makeInput(blankable(p.dia === undefined ? 200 : p.dia)),
    physChipX: makeInput(blankable(p.chipX === undefined ? 9 : p.chipX)),
    physChipY: makeInput(blankable(p.chipY === undefined ? 11 : p.chipY)),
    physOffsetX: makeInput(p.offsetX || 0), physOffsetY: makeInput(p.offsetY || 0),
    physEdgeMargin: makeInput(p.margin === undefined ? 3 : p.margin),
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
    gridData: opts.gridData || {}, gridCells2D: {},
    legend: MAP_LEGEND.map(r => ({ ...r })),
    overlayContract: { valueColumnCandidates: [], defaultLegend: [] },
    activeBrush: 'A',
    validDie: { basis: 'circle', keys: null, reason: '', ref: null, raw: undefined },
    validDieResolveSeq: 0, loadedFCells: new Set(),
    overlayLayers: [], activeOverlayLayers: opts.layers || [],
    UNLISTED_VALUE_FILL: '#T-unlisted',
    paintLockValues: null, paintLockConfig: { enabled: false }, currentHoverCell: null,
    lastSelectionBox: null, isBoxDragging: false, dragType: null, isOriginMode: false,
    isRightDrag: false,
    performance: { now: () => 0 }, window: { devicePixelRatio: 1 },
    getComputedStyle: () => ({ getPropertyValue: () => '#000' }),
    getThemeColors: () => TOK,
    isOverlayLocked: () => false,
    syncOverlayGeometry() {}, updateNotchPosition() {},
    updateLegendCounts() {}, scheduleRenderGridCanvas() {}, scheduleCellDraft() {},
    rec, canvas,
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  try { vm.runInContext(pieces.join('\n'), sandbox); }
  catch (e) { die(`extracted sources did not evaluate: ${e && e.message}`); }
  return { sandbox, el, rec };
}

// ── Scoring ───────────────────────────────────────────────────────────────────────────────
let failures = [], compared = 0;
function ok(cond, name, detail) {
  compared++;
  if (!cond) failures.push(`${name}${detail ? ` -- ${detail}` : ''}`);
  else if (VERBOSE) console.log(`  ok  ${name}`);
}
const eq = (name, expected, actual, note) => {
  compared++;
  const a = JSON.stringify(actual), e = JSON.stringify(expected);
  if (a !== e) failures.push(`${name}: expected ${e}, got ${a}${note ? ` -- ${note}` : ''}`);
  else if (VERBOSE) console.log(`  ok  ${name}`);
};
const near = (a, b, eps = 1e-9) => Math.abs(a - b) <= eps;

function render(src, opts) {
  const env = buildEnv(src, opts);
  env.sandbox.renderGridCanvas();
  return env;
}
const metricsOf = (S, canvas, vCols, vRows) =>
  S.cellMetrics(Math.floor(canvas.w), Math.floor(canvas.h), vCols, vRows,
                S.getTransformedPhysicalConfig(S.currentRotation, S.currentSide));

// THE PAYLOAD, not a model of it.
const payload = (S) => { const out = {}; S.eachSavableCell((co, val) => { out[co.key] = val; }); return out; };

// ══ ⓦ THE WAFER IS THE ANCHOR ═════════════════════════════════════════════════════════════

const DIA = 200;
const CANVAS = { w: 900, h: 380 };
// THE "BEFORE" for every neutrality comparison: the shipped source with the wafer anchor taken
// back out, so the old grid-fitting rule governs. Same file, same fixture, one expression
// swapped -- never a re-implementation of the old rule here, which would only compare this
// harness against itself.
const GRID_ANCHOR_REVERT = {
  find: `  const s = Math.min(sGrid, sWafer);`,
  repl: `  const s = sGrid;`,
};
// Every one of these fits INSIDE the wafer envelope, so the wafer governs the scale in all of
// them. cols/rows/pitch all differ; two are anisotropic; one is rotated.
const SAME_WAFER_GRIDS = [
  { tag: '20x20 @6.0x6.0', cols: 20, rows: 20, chipX: 6, chipY: 6 },
  { tag: '40x40 @3.0x3.0', cols: 40, rows: 40, chipX: 3, chipY: 3 },
  { tag: '15x25 @8.0x4.0', cols: 15, rows: 25, chipX: 8, chipY: 4 },
  { tag: '33x21 @5.0x9.0', cols: 33, rows: 21, chipX: 5, chipY: 9 },
  { tag: '61x61 @3.4x3.4', cols: 61, rows: 61, chipX: 3.4, chipY: 3.4 },
  { tag: '21x33 @9.0x5.0 rot270', cols: 21, rows: 33, chipX: 9, chipY: 5, rotation: 270 },
];
const waferRing = (rec) => rec.paths.find(p => p.strokes.includes(TOK.waferEdge));
const effRing = (rec) => rec.paths.find(p => p.strokes.includes(TOK.success));

function scoreWaferConstant(src, evidence) {
  const radii = [];
  for (const g of SAME_WAFER_GRIDS) {
    const { rec } = render(src, { canvas: CANVAS, panel: { ...g, dia: DIA, margin: 3 } });
    const outer = waferRing(rec);
    if (!outer) { ok(false, `ⓦ1 ${g.tag}: the render drew no wafer edge circle`); continue; }
    radii.push({ tag: g.tag, rx: outer.rx, ry: outer.ry });
    evidence.push(`  ${g.tag.padEnd(24)} outer radius ${outer.rx.toFixed(4)} px`);
  }
  ok(radii.length === SAME_WAFER_GRIDS.length, 'ⓦ1 every fixture produced a circle to compare');

  // THE HEADLINE, and it is one number.
  const first = radii[0];
  const off = radii.filter(r => !near(r.rx, first.rx, 1e-9) || !near(r.ry, first.ry, 1e-9))
                   .map(r => `${r.tag}=${r.rx.toFixed(4)}`);
  eq(`ⓦ1 THE HEADLINE: the same declared ${DIA}mm wafer is the same pixel radius in every grid`,
     [], off, `baseline ${first.rx.toFixed(4)} px from ${first.tag}; ${radii.length} grids compared`);

  // FIXTURE ACTIVITY. If the grids did not actually differ in what the OLD rule keyed on,
  // ⓦ1 would pass on a sweep that never varied anything.
  const spans = new Set(SAME_WAFER_GRIDS.map(g => `${g.cols * g.chipX}x${g.rows * g.chipY}`));
  ok(spans.size >= 4, 'ⓦ1b the fixture grids really do differ in extent (the old rule keyed on this)',
     `only ${spans.size} distinct spans: ${[...spans].join(', ')}`);
  const dims = new Set(SAME_WAFER_GRIDS.map(g => `${g.cols}x${g.rows}`));
  ok(dims.size === SAME_WAFER_GRIDS.length, 'ⓦ1c ...and every grid has distinct dimensions',
     `${dims.size} distinct of ${SAME_WAFER_GRIDS.length}`);
}

// ⓦ2 THE ANCHOR IS THE DIAMETER, NOT THE EFFECTIVE RADIUS.
function scoreAnchorIsDiameter(src, evidence) {
  const seen = [];
  for (const margin of [1, 3, 7, 12]) {
    const { rec } = render(src, { canvas: CANVAS, panel: { dia: DIA, margin, cols: 20, rows: 20, chipX: 6, chipY: 6 } });
    const outer = waferRing(rec), eff = effRing(rec);
    if (!outer || !eff) { ok(false, `ⓦ2 margin ${margin}: no circle recorded`); continue; }
    seen.push({ margin, outer: outer.rx, eff: eff.rx });
  }
  const base = seen[0];
  const moved = seen.filter(s => !near(s.outer, base.outer, 1e-9)).map(s => `margin ${s.margin}=${s.outer.toFixed(4)}`);
  eq('ⓦ2 edge margin does not move the wafer circle (the anchor is the DIAMETER)', [], moved,
     `edge margin is a process parameter, not the wafer -- anchoring on effectiveRadius would `
   + `render the same physical wafer at different sizes`);
  // ...and the fixture axis is live: the EFFECTIVE circle must move, or ⓦ2 proves nothing.
  const effSpread = new Set(seen.map(s => s.eff.toFixed(6)));
  ok(effSpread.size === seen.length, 'ⓦ2b the fixture axis is live (the effective circle DOES move)',
     `${effSpread.size} distinct effective radii across ${seen.length} margins -- with a dead axis, `
   + `anchoring on effectiveRadius would be indistinguishable here`);
  seen.forEach(s => evidence.push(`  edge margin ${String(s.margin).padStart(2)}mm  outer ${s.outer.toFixed(4)}  eff ${s.eff.toFixed(4)}`));
}

// ⓦ3 AN UNDECLARED DIAMETER IS NOT INVENTED.
function scoreUndeclaredDiameter(src, evidence) {
  // 🔴 The two grids must differ in SPAN, not merely in dimensions. The first draft used
  //    20x20@6mm and 40x40@3mm -- both 120x120mm, so the grid-fitting scale was identical and
  //    ⓦ3d compared 475 against 475. A fixture that cannot tell the two rules apart proves
  //    nothing about which one ran.
  const grids = [{ cols: 20, rows: 20, chipX: 6, chipY: 6 }, { cols: 30, rows: 30, chipX: 6, chipY: 6 }];
  const radii = [];
  for (const g of grids) {
    const { sandbox: S, el, rec } = render(src, { canvas: CANVAS, panel: { ...g, dia: null } });
    const outer = waferRing(rec);
    radii.push(outer ? outer.rx : NaN);
    const m = metricsOf(S, CANVAS, g.cols, g.rows);
    eq(`ⓦ3 dia blank (${g.cols}x${g.rows}): the scale is NOT wafer-anchored`, false, m.waferAnchored);
    // ...and it is TODAY'S arithmetic, to the bit. A substituted 300 would make this fail,
    // because `sWafer` would have won on this fixture.
    const sGrid = Math.min(CANVAS.w / (g.cols * g.chipX), CANVAS.h / (g.rows * g.chipY));
    ok(near(m.cellW, g.chipX * sGrid, 1e-9) && near(m.cellH, g.chipY * sGrid, 1e-9),
       `ⓦ3b dia blank (${g.cols}x${g.rows}): the cell falls back to the grid-fitting scale`,
       `cellW ${m.cellW} vs ${g.chipX * sGrid}, cellH ${m.cellH} vs ${g.chipY * sGrid} -- a `
     + `substituted default diameter would silently govern the whole render`);
    ok(el.cellAspectNote.style.display === '' && /지름 미선언/.test(el.cellAspectNote.textContent),
       `ⓦ3c dia blank (${g.cols}x${g.rows}): the screen says the diameter is undeclared`,
       `display=${JSON.stringify(el.cellAspectNote.style.display)} text=${JSON.stringify(el.cellAspectNote.textContent)}`);
  }
  // The fallback IS the old behaviour: the circle varies with the grid again. If these agreed,
  // a substituted diameter would be indistinguishable from an honest fallback.
  ok(!near(radii[0], radii[1], 1e-6),
     'ⓦ3d dia blank: the circle varies with the grid again (that is what the note is warning about)',
     `${radii[0]} vs ${radii[1]} -- equal radii here would mean a diameter was substituted after all`);
  evidence.push(`  dia undeclared -> grid-anchored, radius ${radii[0].toFixed(2)} vs ${radii[1].toFixed(2)} px (varies, and the screen says so)`);

  // ...and the note goes away when the diameter IS declared.
  const { el: el2 } = render(src, { canvas: CANVAS, panel: { dia: DIA, cols: 20, rows: 20, chipX: 6, chipY: 6 } });
  eq('ⓦ3e dia declared: the note is hidden', 'none', el2.cellAspectNote.style.display);
}

// ⓦ4 NO DECLARED CELL EVER LEAVES THE CANVAS -- and therefore none leaves the save payload.
//    The overflow fixture is where this can actually fail, so it is scored there too.
const OVERFLOW_GRID = { tag: '40x40 @8.0x8.0 (320mm grid on a 200mm wafer)',
                        cols: 40, rows: 40, chipX: 8, chipY: 8 };
function scoreNothingLeavesTheCanvas(src, evidence) {
  const cases = [...SAME_WAFER_GRIDS, OVERFLOW_GRID];
  for (const g of cases) {
    const opts = { canvas: CANVAS, panel: { ...g, dia: DIA, margin: 3 } };
    const { sandbox: S } = render(src, opts);
    const rot90 = (S.currentRotation === 90 || S.currentRotation === 270);
    const vCols = rot90 ? g.rows : g.cols, vRows = rot90 ? g.cols : g.rows;
    const m = metricsOf(S, CANVAS, vCols, vRows);
    ok(m.padX >= -1e-9 && m.padY >= -1e-9,
       `ⓦ4 ${g.tag}: the declared grid fits the canvas (padX/padY >= 0)`,
       `padX ${m.padX.toFixed(3)} padY ${m.padY.toFixed(3)} -- a negative pad pushes declared `
     + `cells past the off-canvas 'continue', which sits AHEAD of the gridCells2D registration`);

    // THE CONSEQUENCE, measured rather than argued. The off-canvas `continue` kills
    // REGISTRATION, so registration is what is scored: `gridCells2D` is the domain of
    // `eachSavableCell`, and a cell missing from it cannot be counted, saved or clicked.
    // (The payload itself is a strict subset -- `eachSavableCell` also drops cells outside
    // the wafer circle -- so scoring the payload directly would confuse the wafer mask with
    // the canvas bound. The payload gets its own, stronger assertion below: byte-identity
    // against the pre-change render.)
    const missing = [];
    for (let r = 0; r < vRows; r++) for (let c = 0; c < vCols; c++) {
      if (!(S.gridCells2D[r] && S.gridCells2D[r][c])) missing.push(`c${c},r${r}`);
    }
    eq(`ⓦ4b ${g.tag}: every declared cell is registered (none pushed off the canvas)`, [],
       missing.slice(0, 8), `${missing.length} of ${vCols * vRows} declared cells never reached `
     + `gridCells2D -- they are outside eachSavableCell's domain, so their values vanish on save`);

    // ⓦ4b2 PAYLOAD NEUTRALITY. Paint every declared coordinate, then require the saved set to
    //      be byte-identical to what the PRE-CHANGE (grid-anchored) render produced. This is
    //      the claim that the anchor is a display decision and nothing else.
    const seed = (env) => {
      const T = env.sandbox;
      for (let r = 0; r < vRows; r++) for (let c = 0; c < vCols; c++) {
        const p = T.getDieIndex(c, r, g.cols, g.rows, T.currentRotation, T.currentSide);
        T.gridData[`${p.x}_${p.y}`] = `${p.x},${p.y}`;
      }
      T.gridCells2D = {}; T.renderGridCanvas();
      return payload(T);
    };
    const after = seed(buildEnv(src, opts));
    // 🔴 The "before" is reverted out of the PRISTINE source, never out of `src`. During the
    //    mutation sweep `src` is already mutated and no longer contains the anchor expression,
    //    so a nested revert would abort the whole run on a missing pattern -- the harness would
    //    read as "caught" while this claim went unscored, which is the disguise the runner's
    //    own ASSERTIONS line exists to strip.
    const before = seed(buildEnv(applyMutation(SRC0, GRID_ANCHOR_REVERT, 'grid-anchor revert'), opts));
    eq(`ⓦ4b2 ${g.tag}: the save payload is identical to the pre-change geometry`,
       JSON.stringify(before), JSON.stringify(after),
       `${Object.keys(before).length} vs ${Object.keys(after).length} dies saved`);
    ok(Object.keys(after).length > 50, `ⓦ4b3 ${g.tag}: the payload comparison is not vacuous`,
       `only ${Object.keys(after).length} dies saved`);
  }
  // The overflow branch is EXECUTED, not merely available: the grid governs there and the
  // circle is smaller than the anchored constant. If it never fired, the `min` is untested.
  const { rec: recA } = render(src, { canvas: CANVAS, panel: { ...SAME_WAFER_GRIDS[0], dia: DIA, margin: 3 } });
  const { rec: recO } = render(src, { canvas: CANVAS, panel: { ...OVERFLOW_GRID, dia: DIA, margin: 3 } });
  const rA = waferRing(recA).rx, rO = waferRing(recO).rx;
  ok(rO < rA - 1e-6, 'ⓦ4c the overflow branch really fires (a grid bigger than the wafer takes the scale)',
     `anchored ${rA.toFixed(3)} vs overflow ${rO.toFixed(3)} -- equal means min(sGrid, sWafer) was never exercised`);
  evidence.push(`  grid larger than the wafer: circle ${rO.toFixed(2)} px < anchored ${rA.toFixed(2)} px, `
    + `and 0 declared dies lost (the grid governs, honestly)`);
}

// ══ ⓜ THE MARKER FOLLOWS ITS CELL'S PROPORTIONS ═══════════════════════════════════════════

const FRAC = 0.13;                       // the shipped fraction; the ratio claim is 2 * FRAC
const item = (v, rx, ry) => ({ val: v, rx, ry, mmX: 0, mmY: 0, srcX: 0, srcY: 0 });
const seatAxes = { xc: 1, yc: 0, xr: 0, yr: 1 };

// One marker's extent, straight off the recorded path.
function markerExtent(rec) {
  const p = rec.paths.filter(q => q.strokes.includes(LAYER_COLOR));
  if (p.length === 0) return null;
  const minX = Math.min(...p.map(q => q.cx - q.rx)), maxX = Math.max(...p.map(q => q.cx + q.rx));
  const minY = Math.min(...p.map(q => q.cy - q.ry)), maxY = Math.max(...p.map(q => q.cy + q.ry));
  return { w: maxX - minX, h: maxY - minY, n: p.length, paths: p };
}

// Drive the SHIPPED marker painter at a given cell size and read what it drew.
function paintOne(S, cellW, cellH, list, opts = {}) {
  S.activeOverlayLayers = [{ color: LAYER_COLOR, items: new Map([['0_0', list]]),
                             seatAxes: opts.noSeat ? null : seatAxes,
                             seatChip: opts.noSeat ? null : (opts.chip || { x: 10, y: 10 }) }];
  S.rec.paths.length = 0;
  S.drawOverlayMarkers(S.el.waferCanvas.getContext(), '0_0', 0, 0, cellW, cellH);
  return markerExtent(S.rec);
}

// The pitch-ratio sweep. Cells are given DIRECTLY so the claim is about the marker rule and
// nothing else; the wiring from `cellMetrics` to here is scored separately in ⓜ5.
const RATIOS = [
  { tag: '1:1',  w: 30,   h: 30 },
  { tag: '1:3',  w: 14,   h: 42 },
  { tag: '3:1',  w: 42,   h: 14 },
  { tag: '1:9',  w: 13,   h: 117 },
  { tag: '9:1',  w: 117,  h: 13 },
];
// Below the floor on one axis -- the marker must still exist and must still not spill.
const EXTREME = [
  { tag: '1:9 thin',   w: 3.89,  h: 35 },
  { tag: '9:1 thin',   w: 35,    h: 3.89 },
  { tag: '1:30 thin',  w: 1.17,  h: 35 },
];

function scoreMarkerRatio(src, evidence) {
  const { sandbox: S } = buildEnv(src, {});
  for (const c of RATIOS) {
    const e = paintOne(S, c.w, c.h, [item('1', 1, 1)]);
    if (!e) { ok(false, `ⓜ1 ${c.tag}: no marker was drawn at all`); continue; }
    // THE CLAIM, as a ratio on EACH axis. Not a pixel count: a pixel count passes on one
    // fixture and says nothing about the next aspect.
    ok(near(e.w / c.w, 2 * FRAC, 1e-9), `ⓜ1 ${c.tag}: the marker fills the same fraction of the cell WIDTH`,
       `${(e.w / c.w).toFixed(6)} vs ${(2 * FRAC).toFixed(6)} (cell ${c.w}x${c.h}, marker ${e.w.toFixed(3)}x${e.h.toFixed(3)})`);
    ok(near(e.h / c.h, 2 * FRAC, 1e-9), `ⓜ1b ${c.tag}: ...and of the cell HEIGHT`,
       `${(e.h / c.h).toFixed(6)} vs ${(2 * FRAC).toFixed(6)}`);
    evidence.push(`  cell ${String(c.w).padStart(6)}x${String(c.h).padEnd(6)} (${c.tag.padEnd(4)})`
      + ` -> marker ${e.w.toFixed(2).padStart(7)}x${e.h.toFixed(2).padEnd(7)}`
      + ` = ${(e.w / c.w * 100).toFixed(1)}%W / ${(e.h / c.h * 100).toFixed(1)}%H`);
  }
  // ⓜ2 THE FLOOR NEVER SPILLS. A marker wider than its own cell sits on the neighbour and is
  //    read as the neighbour's value.
  for (const c of EXTREME) {
    const e = paintOne(S, c.w, c.h, [item('1', 1, 1)]);
    ok(e !== null, `ⓜ2 ${c.tag}: a marker is drawn at all`,
       `cell ${c.w}x${c.h} -- the shipped defect drew NOTHING here (the anchor left the cell and `
     + `the 'cx < x0' guard broke out)`);
    if (!e) continue;
    ok(e.w <= c.w + 1e-9, `ⓜ2b ${c.tag}: the marker does not spill past its cell WIDTH`,
       `marker ${e.w.toFixed(3)} in a ${c.w} cell`);
    ok(e.h <= c.h + 1e-9, `ⓜ2c ${c.tag}: ...nor past its cell HEIGHT`,
       `marker ${e.h.toFixed(3)} in a ${c.h} cell`);
    evidence.push(`  cell ${String(c.w).padStart(6)}x${String(c.h).padEnd(6)} (${c.tag.padEnd(10)})`
      + ` -> marker ${e.w.toFixed(2).padStart(7)}x${e.h.toFixed(2).padEnd(7)} (floor bound, still inside the cell)`);
  }
}

// ⓜ3 A SQUARE CELL IS UNTOUCHED. Same primitive, same radius, same centre as the old formula.
function scoreSquareCellUnchanged(src) {
  const { sandbox: S } = buildEnv(src, {});
  for (const side of [30, 12, 8, 60]) {
    const e = paintOne(S, side, side, [item('1', 1, 1)]);
    if (!e) { ok(false, `ⓜ3 square ${side}: nothing drawn`); continue; }
    const oldR = Math.max(1.5, Math.min(side, side) * FRAC);         // THE PRE-CHANGE FORMULA
    const OLD_INSET = 1.5;
    eq(`ⓜ3 square ${side}px: still an arc, not an ellipse`, 'arc', e.paths[0].kind);
    ok(near(e.paths[0].rx, oldR, 1e-9) && near(e.paths[0].ry, oldR, 1e-9),
       `ⓜ3b square ${side}px: same radius as before the change`, `${e.paths[0].rx} vs ${oldR}`);
    // 🔴 THE INSET IS THE ONE HONEST EXCEPTION, and it is stated rather than averaged away.
    //    It is `min(1.5, cell * 0.1)`, so at 15px and above it IS the old fixed 1.5 and the
    //    dot is byte-identical; below 15px it shrinks, which is precisely the change that
    //    stops the anchor walking out of a thin cell and drawing nothing at all. Scored as
    //    two separate claims so the boundary cannot drift unnoticed.
    if (side >= 15) {
      ok(near(e.paths[0].cx, side - oldR - OLD_INSET, 1e-9),
         `ⓜ3c square ${side}px (>= 15): byte-identical centre -- this round is a no-op here`,
         `${e.paths[0].cx} vs ${side - oldR - OLD_INSET}`);
    } else {
      const shift = Math.abs(e.paths[0].cx - (side - oldR - OLD_INSET));
      ok(shift <= OLD_INSET + 1e-9 && e.paths[0].cx - e.paths[0].rx >= -1e-9,
         `ⓜ3c square ${side}px (< 15): the centre moves at most one old inset, and stays in the cell`,
         `moved ${shift.toFixed(4)}px; left edge at ${(e.paths[0].cx - e.paths[0].rx).toFixed(4)}`);
    }
  }
}

// ⓜ4 THE MULTI-SOURCE SPREAD COMES BACK ON A THIN CELL.
function scoreSpread(src, evidence) {
  const { sandbox: S } = buildEnv(src, {});
  const chip = { x: 10, y: 10 };
  const three = [item('1', 1, 1), item('1', 5, 5), item('1', 9, 9)];
  const CASES = [
    { tag: 'wide and short   35.0 x 3.9', w: 35, h: 3.9, spreadAxis: 'x' },
    { tag: 'thin and tall     3.9 x 35.0', w: 3.9, h: 35, spreadAxis: 'y' },
    { tag: 'square           35.0 x 35.0', w: 35, h: 35, spreadAxis: 'x' },
  ];
  for (const c of CASES) {
    const e = paintOne(S, c.w, c.h, three, { chip });
    ok(e !== null && e.n === 3, `ⓜ4 ${c.tag}: all three source chips are drawn separately`,
       `${e ? e.n : 0} dot(s) -- collapsing them makes a cell holding 3 chips look like one holding 1`);
    if (!e || e.n !== 3) continue;
    const key = c.spreadAxis === 'x' ? 'cx' : 'cy';
    const positions = new Set(e.paths.map(p => p[key].toFixed(6)));
    ok(positions.size === 3, `ⓜ4b ${c.tag}: ...at three distinct positions along the roomy axis`,
       `${positions.size} distinct ${key}: ${[...positions].join(', ')}`);
    evidence.push(`  ${c.tag} -> ${e.n} dots, ${positions.size} distinct ${key}`);
  }
  // ⓜ4b2 THE SPREAD DOTS ARE SIZED PER AXIS TOO. Counting dots and positions leaves the
  //      spread branch's own radius unscored -- the `min` defect can be put back there alone
  //      and every assertion above still passes. Cell 60x20 clears the 1.2px floor on both
  //      axes (1.2 / 0.10 = 12px), so this reads the ratio and not the floor.
  {
    const SPREAD_FRAC = 0.10;
    const e = paintOne(S, 60, 20, three, { chip });
    ok(e !== null && e.n === 3, 'ⓜ4b2 the sizing fixture spreads at all');
    if (e && e.n === 3) {
      const bad = e.paths.filter(p => !near(p.rx / 60, SPREAD_FRAC, 1e-9) || !near(p.ry / 20, SPREAD_FRAC, 1e-9))
                         .map(p => `${p.rx.toFixed(3)}x${p.ry.toFixed(3)}`);
      eq('ⓜ4b3 every spread dot follows its cell on BOTH axes', [], bad,
         `expected ${(60 * SPREAD_FRAC).toFixed(3)}x${(20 * SPREAD_FRAC).toFixed(3)} in a 60x20 cell`);
      evidence.push(`  spread dot size in a 60x20 cell -> ${e.paths[0].rx.toFixed(2)}x${e.paths[0].ry.toFixed(2)} `
        + `= ${(e.paths[0].rx / 60 * 100).toFixed(1)}%W / ${(e.paths[0].ry / 20 * 100).toFixed(1)}%H (half-extents)`);
    }
  }

  // ⓜ4c PURE WIDENING. Every cell that spread under the old rule still spreads. A fix that
  //     traded one collapse for another would pass ⓜ4 and still be a regression.
  const regressed = [];
  for (let w = 2; w <= 60; w += 2) for (let h = 2; h <= 60; h += 2) {
    const oldRoomy = (w >= 10 && h >= 10);
    if (!oldRoomy) continue;
    const e = paintOne(S, w, h, three, { chip });
    if (!e || e.n !== 3) regressed.push(`${w}x${h}`);
  }
  eq('ⓜ4c the new rule is a pure widening (nothing that spread before stopped)', [],
     regressed.slice(0, 8), `${regressed.length} cell sizes lost their spread`);
  // ...and it really did widen, or ⓜ4c is a tautology.
  let gained = 0;
  for (let w = 2; w <= 60; w += 2) for (let h = 2; h <= 60; h += 2) {
    if (w >= 10 && h >= 10) continue;
    const e = paintOne(S, w, h, three, { chip });
    if (e && e.n === 3) gained++;
  }
  ok(gained > 0, 'ⓜ4d ...and it actually widened (cells that used to collapse now spread)',
     'zero cells changed -- the roomy rule did not move');
  evidence.push(`  spread rule: 0 cell sizes lost the fan-out, ${gained} gained it`);
}

// ⓜ5 THE WIRING. The rule above is worth nothing if the render does not hand it the real cell.
//    Scored by running the WHOLE render with a live marker painter on a real overlay cell.
function scoreWiring(src, evidence) {
  // Both cell dimensions must clear the visibility floor (>= 1.5 / 0.13 = 11.54px), or ⓜ5c is
  // scoring the floor rather than the ratio. Cell here is 12.5 x 25.0 px.
  const panel = { cols: 20, rows: 10, chipX: 7, chipY: 14, dia: DIA, margin: 3 };
  const probe = render(src, { canvas: CANVAS, panel });
  const anyKey = Object.values(probe.sandbox.gridCells2D)
    .flatMap(row => Object.values(row)).map(co => co.key)[0];
  ok(!!anyKey, 'ⓜ5 the render seated at least one cell to hang an overlay on');
  if (!anyKey) return;
  const layer = { color: LAYER_COLOR, items: new Map([[anyKey, [item('1', 1, 1)]]]),
                  seatAxes, seatChip: { x: panel.chipX, y: panel.chipY } };
  const { sandbox: S, rec } = render(src, { canvas: CANVAS, panel, layers: [layer] });
  const m = metricsOf(S, CANVAS, panel.cols, panel.rows);
  ok(m.cellW >= 1.5 / FRAC && m.cellH >= 1.5 / FRAC,
     'ⓜ5b2 the wiring fixture clears the visibility floor on both axes',
     `cell ${m.cellW.toFixed(3)}x${m.cellH.toFixed(3)} -- below ${(1.5 / FRAC).toFixed(2)}px the floor `
   + `binds and ⓜ5c would score the floor instead of the ratio`);
  const e = markerExtent(rec);
  ok(e !== null, 'ⓜ5b a marker reached the canvas through the real render');
  if (!e) return;
  ok(near(e.w / m.cellW, 2 * FRAC, 1e-9) && near(e.h / m.cellH, 2 * FRAC, 1e-9),
     'ⓜ5c the marker drawn by the REAL render follows the real cell on both axes',
     `cell ${m.cellW.toFixed(3)}x${m.cellH.toFixed(3)}, marker ${e.w.toFixed(3)}x${e.h.toFixed(3)}`);
  ok(!near(m.cellW, m.cellH, 1e-6), 'ⓜ5d the fixture cell really is rectangular here',
     `${m.cellW} x ${m.cellH} -- a square cell cannot score ⓜ5c`);
  evidence.push(`  real render, pitch ${panel.chipX}x${panel.chipY}: cell `
    + `${m.cellW.toFixed(2)}x${m.cellH.toFixed(2)} -> marker ${e.w.toFixed(2)}x${e.h.toFixed(2)}`);
}

// ⓜ6 THE VALUE-COLOUR CONTRACT DID NOT MOVE. This file edits that painter, so it re-scores it.
function scoreColourNotRegressed(src) {
  const { sandbox: S } = buildEnv(src, {});
  const one = paintOne(S, 30, 12, [item('1', 1, 1)]);
  eq('ⓜ6 a single listed value is filled with ITS legend colour', '#10b981', one.paths[0].fill);
  ok(one.paths[0].strokes.includes(LAYER_COLOR), 'ⓜ6b ...and ringed with the LAYER colour',
     JSON.stringify(one.paths[0].strokes));
  ok(one.paths[0].strokes.includes(HALO), 'ⓜ6c ...with the white halo between them');

  const unl = paintOne(S, 30, 12, [item(UNLISTED_VAL, 1, 1)]);
  eq('ⓜ6d an unlisted value gets NO fill at all', null, unl.paths[0].fill);

  // A multi-source dot that CANNOT be spread (no seating) stays hollow even when its items
  // agree -- the rule the value-colour round established, unchanged by the shape work.
  const agree = paintOne(S, 30, 12, [item('1', 1, 1), item('1', 2, 2)], { noSeat: true });
  eq('ⓜ6e a multi-source dot that cannot spread is one dot', 1, agree.n);
  eq('ⓜ6f ...and it stays hollow even when its items agree', null, agree.paths[0].fill);

  // When it CAN be spread, each dot answers for exactly one chip and so may be filled.
  const spread = paintOne(S, 30, 30, [item('1', 1, 1), item('F', 9, 9)]);
  eq('ⓜ6g a spread dot answers for one chip, so it takes that chip\'s colour',
     ['#10b981', '#ef4444'], spread.paths.map(p => p.fill).sort());
}

// ── Fixture self-check ────────────────────────────────────────────────────────────────────
function fixtureSelfCheck(src) {
  ok(RATIOS.some(c => c.w !== c.h), 'fixture: the ratio sweep contains anisotropic cells');
  ok(RATIOS.filter(c => c.w !== c.h).length >= 4,
     'fixture: and several of them, both ways round (one anisotropic case cannot show a ratio)');
  ok(SAME_WAFER_GRIDS.some(g => g.chipX !== g.chipY),
     'fixture: the wafer sweep contains an anisotropic pitch');
  ok(SAME_WAFER_GRIDS.some(g => g.rotation === 270), 'fixture: and a rotated frame');
  ok(CANVAS.w !== CANVAS.h, 'fixture: the canvas is non-square (padX and padY are both live)');
  // The isotropic branch is the one being executed -- otherwise every ⓦ claim scores the fallback.
  const { sandbox: S } = render(src, { canvas: CANVAS, panel: { ...SAME_WAFER_GRIDS[0], dia: DIA } });
  const m = metricsOf(S, CANVAS, 20, 20);
  ok(m.isotropic === true, 'fixture: the isotropic branch is executing');
  ok(m.waferAnchored === true, 'fixture: ...and the wafer anchor is the one governing it');
}

// ── Mutation plumbing ─────────────────────────────────────────────────────────────────────
// 🔴 THE ANCHOR MUST BE UNIQUE. A `replace` on a non-unique string lands on the FIRST match,
//    which in this file has already once been inside a COMMENT -- the harness then scored a
//    different function and reported green. So uniqueness is asserted, not hoped for, and the
//    MUTATED STATE is confirmed rather than merely "something changed": later code here has
//    repaired an injected defect before, and a green run then meant "there was no mutation".
function applyMutation(src, mut, name) {
  const n = src.split(mut.find).length - 1;
  if (n !== 1) die(`mutation anchor for '${name}' matches ${n} times, not 1. `
    + `A non-unique anchor lands on the first match and scores the wrong code.`);
  const out = src.replace(mut.find, mut.repl);
  if (out === src) die(`mutation '${name}' produced an identical source -- nothing was injected`);
  if (out.split(mut.repl).length - 1 !== 1) die(`mutation '${name}': the replacement is not present exactly once`);
  return out;
}

const MUTATIONS = [
  ['ⓜ THE SHIPPED DEFECT, PUT BACK: the shorter axis sizes the marker', {
    find: `  const rx = markerAxisRadius(cellW, 0.13, 1.5);\n  const ry = markerAxisRadius(cellH, 0.13, 1.5);`,
    repl: `  const rx = Math.max(1.5, Math.min(cellW, cellH) * 0.13);\n  const ry = rx;`,
  }],
  ['ⓜ the spread is gated on BOTH axes again (a thin cell loses its fan-out)', {
    find: `    const roomy = list.length > 1 && (cellW >= 10 || cellH >= 10) && layer.seatAxes && layer.seatChip;`,
    repl: `    const roomy = list.length > 1 && cellW >= 10 && cellH >= 10 && layer.seatAxes && layer.seatChip;`,
  }],
  ['ⓜ the spread dots go back to the shorter axis', {
    find: `      const rrx = markerAxisRadius(cellW, 0.10, 1.2);\n      const rry = markerAxisRadius(cellH, 0.10, 1.2);`,
    repl: `      const rrx = Math.max(1.2, Math.min(cellW, cellH) * 0.10);\n      const rry = rrx;`,
  }],
  ['ⓜ the half-cell cap is dropped (the floor spills onto the neighbouring cell)', {
    find: `  return Math.min(cellPx / 2, Math.max(floorPx, cellPx * frac));`,
    repl: `  return Math.max(floorPx, cellPx * frac);`,
  }],
  ['ⓜ the inset goes back to a fixed 1.5px (a thin cell draws nothing at all)', {
    find: `  const insetX = Math.min(1.5, cellW * 0.1);\n  const insetY = Math.min(1.5, cellH * 0.1);`,
    repl: `  const insetX = 1.5;\n  const insetY = 1.5;`,
  }],
  ['ⓜ the painter ignores the second radius (every marker is a circle again)', {
    find: `  if (radX !== ry && typeof ctx.ellipse === 'function') ctx.ellipse(cx, cy, radX, ry, 0, 0, 2 * Math.PI);`,
    repl: `  if (false) ctx.ellipse(cx, cy, radX, ry, 0, 0, 2 * Math.PI);`,
  }],
  ['ⓦ THE REPORTED DEFECT, PUT BACK: the grid anchors the scale again', GRID_ANCHOR_REVERT],
  ['ⓦ the grid-fitting bound is dropped (declared cells fall off the canvas and off the payload)', {
    find: `  const s = Math.min(sGrid, sWafer);\n  const cellW = chipX * s;`,
    repl: `  const s = sWafer === Infinity ? sGrid : sWafer;\n  const cellW = chipX * s;`,
  }],
  ['ⓦ the anchor becomes the EFFECTIVE radius (edge margin resizes the same wafer)', {
    find: `  const sWafer = waferAnchored ? (Math.min(width, height) * 0.94) / dd.value : Infinity;`,
    repl: `  const sWafer = waferAnchored ? (Math.min(width, height) * 0.94) / (dd.value - 2 * physNum('edgeMargin', el.physEdgeMargin, 3.0)) : Infinity;`,
  }],
  ['ⓦ an undeclared diameter is invented from the defaulted number', {
    find: `  const dd = physDeclaration('waferDia', el.physWaferDia);`,
    repl: `  const dd = { value: physNum('waferDia', el.physWaferDia, 300) };`,
  }],
  // [D1] The anchor gained a `} ` prefix when the aspect clause above it grew a third case
  // (auto-registered geometry gets its own sentence, because "Chip X/Y 미선언" reads as false
  // when the inputs visibly hold a number). The mutation is unchanged — only the text it
  // anchors on moved, and the harness refused to run rather than silently matching nothing.
  ['ⓦ the screen stops saying the diameter is undeclared', {
    find: `    } else if (!waferAnchored) notes.push('웨이퍼 지름 미선언 — 원 크기가 격자에 따라 달라집니다');`,
    repl: `    } else if (false) notes.push('웨이퍼 지름 미선언 — 원 크기가 격자에 따라 달라집니다');`,
  }],
];

// ── Run ───────────────────────────────────────────────────────────────────────────────────
function scoreAll(src) {
  failures = []; compared = 0;
  const ev = { wafer: [], marker: [] };
  fixtureSelfCheck(src);
  scoreWaferConstant(src, ev.wafer);
  scoreAnchorIsDiameter(src, ev.wafer);
  scoreUndeclaredDiameter(src, ev.wafer);
  scoreNothingLeavesTheCanvas(src, ev.wafer);
  scoreMarkerRatio(src, ev.marker);
  scoreSquareCellUnchanged(src);
  scoreSpread(src, ev.marker);
  scoreWiring(src, ev.marker);
  scoreColourNotRegressed(src);
  return ev;
}

const ev = scoreAll(SRC0);
console.log('\n── ⓦ the wafer anchors the scale (radii straight off the draw call) ──');
ev.wafer.forEach(l => console.log(l));
console.log('\n── ⓜ the marker follows its cell (extents straight off the draw call) ──');
ev.marker.forEach(l => console.log(l));

if (failures.length > 0) {
  console.error(`\n✗ BASELINE RED -- ${failures.length} failure(s):`);
  failures.forEach(f => console.error(`   ${f}`));
}

console.log('\n── mutation floor (each defect injected, then scored) ──');
const uncaught = [];
for (const [name, mut] of MUTATIONS) {
  const mutated = applyMutation(SRC0, mut, name);
  let caught = false, threw = '';
  try { scoreAll(mutated); caught = failures.length > 0; }
  // A throw is a red too, but it is REPORTED: a mutation caught only by an exception may be
  // stopping the run before the assertion written for it ever executes.
  catch (e) { caught = true; threw = ` [threw: ${e && e.message}]`; }
  // ATTRIBUTION WITH ITS EVIDENCE, not just a tick and a name. "Something went red" is a
  // weaker claim than "the assertion written for this defect went red, and here is the
  // measurement it made" -- and the measurement is the only place the DAMAGE shows up
  // (how many dies the defect loses, how many pixels the marker loses).
  const evidence = failures.slice(0, 2).join('\n                 ') || '(threw before asserting)';
  console.log(`  ${caught ? '✓ caught' : '✗ MISSED'}  ${name}`
    + (caught ? `\n              red (${failures.length} total)${threw}: ${evidence}` : ''));
  if (!caught) uncaught.push(name);
}

failures = []; compared = 0;
scoreAll(SRC0);
uncaught.forEach(n => failures.push(`MUTATION NOT CAUGHT: ${n} -- this harness does not score it`));
compared += MUTATIONS.length;

console.log(`\nASSERTIONS ${compared} ${failures.length}`);
if (failures.length > 0) {
  console.error(`\n✗ ${failures.length} failure(s):`);
  failures.forEach(f => console.error(`   ${f}`));
  process.exit(1);
}
console.log('✓ all green');
