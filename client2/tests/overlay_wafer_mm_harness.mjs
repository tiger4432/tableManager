/**
 * [Map rule 6] Overlay by WF-internal PHYSICAL POSITION -- harness.
 *
 * Scores ONE claim, on the shipped branch, by executing it:
 *
 *     A source cell is drawn on the target cell that PHYSICALLY CONTAINS it -- across a
 *     different chip pitch, a different grid size, a different rotation and a different
 *     side -- and when the target cell is coarser, every source cell that lands in it is
 *     kept as a positioned item. Nothing is collapsed to a representative.
 *
 * THE DEFECT IT REPLACES. `getDieIndex` counts CELLS, not millimetres. The overlay
 * projected die index -> die index, which is only correct when both maps share a pitch.
 * A gate refused the case where the grid dims differed, so the usual 7mm-over-15mm pair was
 * refused rather than drawn -- but two maps that declare the SAME dims with DIFFERENT pitch
 * passed that gate. Measured on the fixture below (same 20x30 dims, 7x5mm vs 15x10mm):
 * the shipped projection agreed with physical truth on 4 of 600 cells.
 *
 * 🔴 THE ORACLE IS NOT THE TRANSFORM. Every expectation comes from a millimetre model
 *    written from the geometry -- a cell is a mm rectangle, a wafer is a mm circle, and the
 *    target cell for a point is found by SCANNING every target cell and testing containment.
 *    There is no parity term and no division in it. The implementation, by contrast, works
 *    in cell indices with a parity half-cell and a floor division. A defect shared by both
 *    would have to be a defect of geometry, not of arithmetic.
 *    (The oracle is itself anchored: A1 checks it reproduces `getWaferBoundingBox`, a
 *     quantity that predates this round and is already load-bearing for stored coordinates.)
 *
 * FIXTURE AXES, all live on purpose -- an axis that is dead cannot fail:
 *    chipX != chipY in BOTH maps, with DIFFERENT ratios per axis (15/7 vs 10/5)
 *                          -> an axis swap cannot pass by coincidence
 *    source rot 90 + back  -> the pitch swap AND the back sign flip both participate
 *    target rot 0  + front
 *    src 42x59 (even x ODD) vs tgt 20x30 (even x even)
 *                          -> the parity half-cell DIFFERS on Y. Dropping it is a half-cell
 *                             shift on every cell, which is exactly what A8 measures.
 *    startX != startY, one negative, invertY differs
 *    fan-in is real: measured max 6 source cells into one target cell
 *
 * Run:  node client2/tests/overlay_wafer_mm_harness.mjs
 * Read-only against client2/. Mutation sweep is unconditional -- there is no flag to forget.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC_PATH = join(HERE, '..', 'src', 'map_editor.js');
// Line endings normalised -- every mutation below matches a `\n` string, and on a CRLF
// checkout those matches silently MISS while the baseline stays green.
const SRC0 = readFileSync(SRC_PATH, 'utf8').replace(/\r\n/g, '\n');

const die = (m) => { console.error(`HARNESS FAILURE: ${m}\n(Nothing was compared.)`); process.exit(2); };

function sliceFunction(source, name) {
  const decl = new RegExp(`(^|\\n)\\s*(?:async\\s+)?function\\s+${name}\\s*\\(`);
  const m = decl.exec(source);
  if (!m) die(`symbol not found: ${name} (renamed? this harness must be updated, never skipped)`);
  const start = m.index + (m[1] ? m[1].length : 0);
  let i = m.index + m[0].length - 1;
  let paren = 0;
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

// The coordinate core plus the rule-6 additions. A rename here is exit 2, never green.
const SYMBOLS = [
  'physNum', 'gridDimNum', 'withPhysFrame',
  'getTransformedPhysicalConfig', 'getScreenShift',
  'getDieIndex', 'getCanvasCellFromDieIndex',
  'dieIndexToWaferMm', 'waferMmToDieCell', 'frameDieLattice',
  'getCanvasCellFromDb', 'getDbCoords',
  'isCellInsideWaferFast', 'getWaferBoundingBox',
  'validDieBasis', 'isValidDieAt',
  'frameFromMeta', 'currentFrame', 'resolveFrame', 'frameAxesKey',
  'projectCellsToWaferMm', 'projectCellsToPhys',
  'seatWaferMmInFrame', 'canvasSeatKeys',
  // [2b] `physDeclaration` no longer spells "did this control say anything" inline: that
  // question is now shared with the grid-frame reader, so it is one function and it is here.
  'controlIsSilent',
  'geometryIsAutoRegistered', 'physDeclaration', 'frameDimBounds', 'frameDimError',
  'reseatOverlayLayer',
];

const inp = (v) => ({ value: String(v) });

function makeSandbox(src) {
  const body = SYMBOLS.map(n => sliceFunction(src, n)).join('\n\n');
  const ctx = {
    console, Math, Number, String, Array, Object, Map, Set, JSON, parseInt, parseFloat,
    physFrameOverride: null,
    boundingBoxCache: {},
    // NOT reset by setScreen on purpose: if the cache key were incomplete, a stale key set
    // would survive a frame change and the assertions below would see it.
    seatKeyCache: { key: '', sets: null },
    currentRotation: 0,
    currentSide: 'front',
    validDie: { basis: 'circle', keys: null, reason: '', ref: null, raw: undefined },
    validDieResolveSeq: 0,
    el: {
      physWaferDia: inp(300), physChipX: inp(2.5), physChipY: inp(2.5),
      physOffsetX: inp(0), physOffsetY: inp(0), physEdgeMargin: inp(3),
      gridCols: inp(10), gridRows: inp(10), gridStartX: inp(0), gridStartY: inp(0),
      gridYInvert: { checked: false },
    },
  };
  vm.createContext(ctx);
  try { vm.runInContext(body, ctx); } catch (e) { die(`sandbox did not evaluate: ${e.message}`); }
  return ctx;
}

// Put a frame on the fake screen controls -- "what the canvas currently declares".
function setScreen(ctx, f) {
  const e = ctx.el;
  e.gridCols.value = String(f.cols); e.gridRows.value = String(f.rows);
  e.gridStartX.value = String(f.startX); e.gridStartY.value = String(f.startY);
  e.gridYInvert.checked = !!f.invertY;
  ctx.currentRotation = f.rotation; ctx.currentSide = f.side;
  e.physWaferDia.value = String(f.waferDia);
  e.physChipX.value = String(f.chipX); e.physChipY.value = String(f.chipY);
  e.physOffsetX.value = String(f.offsetX); e.physOffsetY.value = String(f.offsetY);
  e.physEdgeMargin.value = String(f.edgeMargin);
  ctx.boundingBoxCache = {};
}

// ── Fixture ────────────────────────────────────────────────────────────────────────────
const SRC = {
  cols: 42, rows: 59, startX: 1, startY: 2, invertY: false,
  rotation: 90, side: 'back',
  waferDia: 300, chipX: 7, chipY: 5, offsetX: 0.7, offsetY: -0.4, edgeMargin: 3,
};
const TGT = {
  cols: 20, rows: 30, startX: 3, startY: -2, invertY: true,
  rotation: 0, side: 'front',
  waferDia: 300, chipX: 15, chipY: 10, offsetX: 1.5, offsetY: 2.0, edgeMargin: 3,
};

// ── The independent millimetre oracle ──────────────────────────────────────────────────
// A frame's SCREEN axes, in millimetres. Written from the geometry: at 90/270 the screen x
// axis IS the physical y axis, so the pitch that governs it is the other one.
function screenAxes(f) {
  const rot90 = (f.rotation === 90 || f.rotation === 270);
  const Px = rot90 ? f.chipY : f.chipX;
  const Py = rot90 ? f.chipX : f.chipY;
  const oox = (f.side === 'back') ? -f.offsetX : f.offsetX;
  const ooy = f.offsetY;
  let Ox, Oy;
  if (f.rotation === 0)        { Ox =  oox; Oy = -ooy; }
  else if (f.rotation === 90)  { Ox =  ooy; Oy =  oox; }
  else if (f.rotation === 180) { Ox = -oox; Oy =  ooy; }
  else                         { Ox = -ooy; Oy = -oox; }
  return { Px, Py, Ox, Oy, visualCols: rot90 ? f.rows : f.cols, visualRows: rot90 ? f.cols : f.rows };
}
// The mm rectangle a screen cell occupies, relative to the WAFER CENTRE.
function cellRectMm(f, c, r) {
  const a = screenAxes(f);
  return {
    x0: (c - a.visualCols / 2) * a.Px + a.Ox, x1: (c + 1 - a.visualCols / 2) * a.Px + a.Ox,
    y0: (r - a.visualRows / 2) * a.Py + a.Oy, y1: (r + 1 - a.visualRows / 2) * a.Py + a.Oy,
  };
}
const cellCentreMm = (f, c, r) => {
  const R = cellRectMm(f, c, r);
  return { x: (R.x0 + R.x1) / 2, y: (R.y0 + R.y1) / 2 };
};
// A cell is on the wafer iff all four of its corners are inside the effective radius.
// In millimetres the edge-exclusion boundary is a CIRCLE; the ellipse in the shipped
// pixel-space test is the same statement after the pixel scaling.
function insideMm(f, c, r) {
  const R = cellRectMm(f, c, r);
  const rad = f.waferDia / 2 - f.edgeMargin;
  for (const [x, y] of [[R.x0, R.y0], [R.x1, R.y0], [R.x0, R.y1], [R.x1, R.y1]])
    if (x * x + y * y > rad * rad) return false;
  return true;
}
function oracleBox(f) {
  const a = screenAxes(f);
  let minC = Infinity, maxC = -Infinity, minR = Infinity, maxR = -Infinity;
  for (let r = 0; r < a.visualRows; r++) for (let c = 0; c < a.visualCols; c++) {
    if (!insideMm(f, c, r)) continue;
    if (c < minC) minC = c; if (c > maxC) maxC = c;
    if (r < minR) minR = r; if (r > maxR) maxR = r;
  }
  return { minC, maxC, minR, maxR };
}

// 🔴 SCREEN mm -> WAFER mm. Two maps can only be compared in a frame that belongs to the
//    wafer, not to a viewer: the fixture's source is drawn rotated 90 and mirrored while
//    the target is not, so "3mm to the right" means different physical places on the two
//    screens. Rotation and side are DISPLAY attributes; the die they show is at one place.
//    (This is the one part of the oracle that restates a table the implementation also
//     owns. It stays honest here because the two frames have DIFFERENT rotation and side --
//     a wrong entry displaces the source cloud relative to the target cloud instead of
//     cancelling, which is what A2 counts.)
function screenToWaferMm(f, X, Y) {
  let x, y;
  if (f.rotation === 0)        { x =  X; y =  Y; }
  else if (f.rotation === 90)  { x =  Y; y = -X; }
  else if (f.rotation === 180) { x = -X; y = -Y; }
  else                         { x = -Y; y =  X; }
  if (f.side === 'back') x = -x;
  return { x, y };
}
const cellCentreWaferMm = (f, c, r) => {
  const m = cellCentreMm(f, c, r);
  return screenToWaferMm(f, m.x, m.y);
};
// The wafer-frame mm rectangle of a screen cell: the axis-aligned box of its four mapped
// corners. The map is a signed axis permutation, so the box is exact, not a bound.
function cellRectWaferMm(f, c, r) {
  const R = cellRectMm(f, c, r);
  const pts = [[R.x0, R.y0], [R.x1, R.y0], [R.x0, R.y1], [R.x1, R.y1]]
    .map(([X, Y]) => screenToWaferMm(f, X, Y));
  return {
    x0: Math.min(...pts.map(p => p.x)), x1: Math.max(...pts.map(p => p.x)),
    y0: Math.min(...pts.map(p => p.y)), y1: Math.max(...pts.map(p => p.y)),
  };
}
// BRUTE FORCE: which target cell contains this wafer-mm point. No division, no parity,
// no lattice reference -- every cell is asked in turn.
function containingCell(f, mm) {
  const a = screenAxes(f);
  for (let r = 0; r < a.visualRows; r++) for (let c = 0; c < a.visualCols; c++) {
    const R = cellRectWaferMm(f, c, r);
    if (mm.x >= R.x0 && mm.x < R.x1 && mm.y >= R.y0 && mm.y < R.y1) return { c, r };
  }
  return null;
}

// Source rows exactly as a REST fetch hands them over, with each row's own truth recorded.
function buildSourceRows(ctx, f) {
  setScreen(ctx, f);
  const box = ctx.getWaferBoundingBox(null, f.rotation, f.side);
  const a = screenAxes(f);
  const rows = [], truth = new Map();
  for (let r = 0; r < a.visualRows; r++) for (let c = 0; c < a.visualCols; c++) {
    if (!insideMm(f, c, r)) continue;
    // Stored coordinate, restated from the spec: dbX = c - box.minC + start_x
    const dbX = c - box.minC + f.startX;
    const dbY = f.invertY ? (box.maxR - r + f.startY) : (r - box.minR + f.startY);
    rows.push({ x: dbX, y: dbY, val: `${dbX},${dbY}` });   // the value ENCODES its own identity
    truth.set(`${dbX},${dbY}`, cellCentreWaferMm(f, c, r));
  }
  return { rows, truth };
}

// The die key each target canvas cell answers to.
function targetKeyIndex(ctx, f) {
  setScreen(ctx, f);
  const a = screenAxes(f);
  const byKey = new Map();
  for (let r = 0; r < a.visualRows; r++) for (let c = 0; c < a.visualCols; c++) {
    const p = ctx.getDieIndex(null, c, r, f.cols, f.rows, f.rotation, f.side);
    byKey.set(`${p.x}_${p.y}`, { c, r });
  }
  return byKey;
}

// ── Assertions ─────────────────────────────────────────────────────────────────────────
function runAll(src) {
  const fails = [];
  let ran = 0;   // H1 protocol: how many assertions actually executed, crash-distinguishable
  const ok = (cond, name, detail) => { ran++; if (!cond) fails.push(`${name}${detail ? ` -- ${detail}` : ''}`); };
  const ctx = makeSandbox(src);

  // A1 -- the oracle is anchored to a quantity that predates this round.
  for (const [name, f] of [['source', SRC], ['target', TGT]]) {
    setScreen(ctx, f);
    const code = ctx.getWaferBoundingBox(null, f.rotation, f.side);
    const orc = oracleBox(f);
    ok(code.minC === orc.minC && code.maxC === orc.maxC && code.minR === orc.minR && code.maxR === orc.maxR,
      `A1 oracle anchor (${name})`, `code ${JSON.stringify(code)} vs oracle ${JSON.stringify(orc)}`);
  }

  const { rows, truth } = buildSourceRows(ctx, SRC);
  ok(rows.length > 1500, 'A1b fixture size', `only ${rows.length} source cells`);

  // Seat the layer through the shipped path, with the canvas showing the TARGET.
  setScreen(ctx, TGT);
  const layer = { mmItems: ctx.projectCellsToWaferMm(rows, SRC) };
  ctx.reseatOverlayLayer(layer);
  const keyIndex = targetKeyIndex(ctx, TGT);
  setScreen(ctx, TGT);

  // A2 -- key by key: the cell the code seats it in IS the cell that physically contains it.
  let placed = 0, wrong = 0, unseated = 0;
  const seatOf = new Map();          // "dbX,dbY" -> {c,r}
  layer.items.forEach((list, key) => {
    const cell = keyIndex.get(key);
    list.forEach(it => { if (cell) seatOf.set(`${it.srcX},${it.srcY}`, cell); });
  });
  truth.forEach((mm, id) => {
    const want = containingCell(TGT, mm);
    const got = seatOf.get(id);
    if (!want) return;
    if (!got) { unseated++; return; }
    if (got.c === want.c && got.r === want.r) placed++; else wrong++;
  });
  ok(wrong === 0, 'A2 physical containment', `${wrong} source cells seated on the wrong target cell`);
  ok(unseated === 0, 'A2b every source cell reached a target cell', `${unseated} unseated`);
  ok(placed > 1500, 'A2c comparison actually ran', `only ${placed} compared`);

  // A3 -- LIST THEM ALL: no source cell is discarded, and the fan-in matches the oracle.
  let itemTotal = 0;
  layer.items.forEach(list => { itemTotal += list.length; });
  ok(itemTotal === rows.length, 'A3 nothing discarded',
    `${itemTotal} items for ${rows.length} source cells`);
  const wantFan = new Map();
  truth.forEach(mm => {
    const t = containingCell(TGT, mm); if (!t) return;
    const k = `${t.c}_${t.r}`; wantFan.set(k, (wantFan.get(k) || 0) + 1);
  });
  let fanMismatch = 0, maxFan = 0;
  wantFan.forEach((n, k) => { if (n > maxFan) maxFan = n; });
  layer.items.forEach((list, key) => {
    const cell = keyIndex.get(key); if (!cell) return;
    if ((wantFan.get(`${cell.c}_${cell.r}`) || 0) !== list.length) fanMismatch++;
  });
  ok(fanMismatch === 0, 'A3b fan-in matches the oracle', `${fanMismatch} target cells disagree`);
  ok(maxFan > 1, 'A3c fixture actually produces fan-in', `max fan-in ${maxFan} -- N:1 is not exercised`);
  ok(layer.fanout === maxFan, 'A3d reported fanout', `layer says ${layer.fanout}, oracle says ${maxFan}`);

  // A3e -- NO REPRESENTATIVE. A cell with several items must not answer with one value.
  let representative = 0;
  layer.items.forEach((list, key) => {
    if (list.length > 1 && layer.cells.get(key) !== null) representative++;
  });
  ok(representative === 0, 'A3e no representative value',
    `${representative} multi-value cells expose a single value (that is the discard)`);

  // A4 -- THE REMAINDER IS CARRIED AND IT IS CORRECT.
  // Rebuild the absolute mm from (target cell's low corner) + (in-chip remainder) and compare
  // to the source cell's own oracle position.
  let remBad = 0, remChecked = 0, remZero = 0;
  setScreen(ctx, TGT);
  const TGT_L = ctx.frameDieLattice(TGT);
  layer.items.forEach((list, key) => {
    const i = key.indexOf('_');
    const ix = Number(key.slice(0, i)), iy = Number(key.slice(i + 1));
    const base = ctx.dieIndexToWaferMm(ix, iy, TGT_L);
    list.forEach(it => {
      remChecked++;
      if (it.rx === 0 && it.ry === 0) remZero++;
      const rebuiltX = base.mmX - TGT.chipX / 2 + it.rx;
      const rebuiltY = base.mmY - TGT.chipY / 2 + it.ry;
      const t = truth.get(`${it.srcX},${it.srcY}`);
      if (!t) { remBad++; return; }
      if (Math.abs(rebuiltX - t.x) > 1e-9 || Math.abs(rebuiltY - t.y) > 1e-9) remBad++;
      if (!(it.rx >= 0 && it.rx < TGT.chipX && it.ry >= 0 && it.ry < TGT.chipY)) remBad++;
    });
  });
  ok(remBad === 0, 'A4 remainder reconstructs the absolute position', `${remBad} of ${remChecked} wrong`);
  ok(remChecked === rows.length, 'A4b every item carries a remainder', `${remChecked} vs ${rows.length}`);
  ok(remZero < remChecked, 'A4c remainder is not identically zero', `all ${remZero} are zero`);

  // A5 -- the remainder is an ABSOLUTE LENGTH, so it is pitch-dependent. Carrying an in-chip
  //       coordinate across maps WITHOUT going back through absolute mm must be wrong; this
  //       records how wrong, so nobody "optimises" the mm round trip away later.
  {
    setScreen(ctx, SRC);
    const s = ctx.waferMmToDieCell(37.0, 21.0, ctx.frameDieLattice(SRC));
    setScreen(ctx, TGT);
    const t = ctx.waferMmToDieCell(37.0, 21.0, ctx.frameDieLattice(TGT));
    ok(Math.abs(s.rx - t.rx) > 1e-9 || Math.abs(s.ry - t.ry) > 1e-9,
      'A5 in-chip position is pitch-dependent',
      `same point gives the same remainder in a ${SRC.chipX}mm and a ${TGT.chipX}mm chip`);
  }

  // A6..A8 -- DISCRIMINATION. Interpret with a deliberately wrong frame and COUNT the cells
  //           that move. A zero here means the fixture proves nothing.
  const seatWith = (frameOverrides) => {
    const f = { ...TGT, ...frameOverrides };
    setScreen(ctx, f);
    const l = { mmItems: ctx.projectCellsToWaferMm(rows, SRC) };
    ctx.reseatOverlayLayer(l);
    setScreen(ctx, TGT);
    const m = new Map();
    l.items.forEach((list, key) => list.forEach(it => m.set(`${it.srcX},${it.srcY}`, key)));
    return m;
  };
  const baseSeat = new Map();
  layer.items.forEach((list, key) => list.forEach(it => baseSeat.set(`${it.srcX},${it.srcY}`, key)));
  const diffCount = (m) => {
    let n = 0; baseSeat.forEach((k, id) => { if (m.get(id) !== k) n++; });
    return n;
  };
  const dSrcPitch = diffCount(seatWith({ chipX: SRC.chipX, chipY: SRC.chipY }));
  ok(dSrcPitch > 0, 'A6 pitch discriminates', 'reading the target with the SOURCE pitch changes 0 cells');
  const dSwap = diffCount(seatWith({ chipX: TGT.chipY, chipY: TGT.chipX }));
  ok(dSwap > 0, 'A7 axis swap discriminates', 'swapping target chipX/chipY changes 0 cells');
  const dParity = diffCount(seatWith({ rows: TGT.rows + 1 }));
  ok(dParity > 0, 'A8 parity discriminates', 'flipping target row parity changes 0 cells');

  // A9 -- IDENTITY IS PRESERVED. Source frame == target frame must reproduce the old path
  //       exactly: one item per cell, on the same key `projectCellsToPhys` produces.
  {
    const { rows: idRows } = buildSourceRows(ctx, TGT);
    setScreen(ctx, TGT);
    const l = { mmItems: ctx.projectCellsToWaferMm(idRows, TGT) };
    ctx.reseatOverlayLayer(l);
    const old = ctx.projectCellsToPhys(idRows, TGT);
    ok(l.fanout === 1, 'A9 identity has no fan-in', `fanout ${l.fanout}`);
    ok(l.cellCount === old.size, 'A9b identity cell count', `${l.cellCount} vs old ${old.size}`);
    let miss = 0;
    old.forEach((v, k) => { const it = l.items.get(k); if (!it || it.length !== 1 || it[0].val !== v) miss++; });
    ok(miss === 0, 'A9c identity agrees with the die-index path key by key', `${miss} keys differ`);
    ok(l.outside === 0, 'A9d identity reports nothing outside the grid',
      `${l.outside} of ${idRows.length} reported outside -- this is the stale 0<=px<cols predicate`);
    setScreen(ctx, TGT);
  }

  // A9e -- the canvas key set must FOLLOW the frame. It is cached (a full grid sweep per
  //        layer per keystroke in the spec inputs is not affordable), and a cache keyed on
  //        too little hands back the previous grid's set -- so "outside the grid" would be
  //        counted against a grid that is no longer on screen.
  {
    const same = (a, b) => a.size === b.size && [...a].every(k => b.has(k));
    setScreen(ctx, TGT);
    const kA = ctx.canvasSeatKeys().all;
    const other = { ...TGT, rows: TGT.rows + 1 };
    setScreen(ctx, other);
    const kB = ctx.canvasSeatKeys().all;
    setScreen(ctx, TGT);
    const kA2 = ctx.canvasSeatKeys().all;
    ok(!same(kA, kB), 'A9e canvas key set follows the frame',
      'a 30-row and a 31-row grid answer with the same key set (stale cache)');
    ok(same(kA, kA2), 'A9f returning to a frame returns its own set', 'the set did not come back');
  }

  // ══ QA round: four fixes. Each scores the SHIPPED behaviour and, in the same breath,
  //    reproduces the defect it replaced -- a fix whose fixture cannot show the old failure
  //    has not been scored, it has been asserted.

  // A12 -- THE PITCH GUARD READS A FACT, NOT A DEFAULTED VALUE.
  //        `physNum` ends `return v || dflt`, so by the time a guard sees its output,
  //        "absent" / "unparseable" / "declared 0" / "really that value" are one number.
  //        Every row below is a source frame that declares a grid but not a usable pitch.
  {
    const BAD = [
      ['absent',      undefined],
      ['empty',       ''],
      ['unparseable', 'abc'],
      ['zero',        0],
    ];
    let oldPassed = 0, newRefused = 0, worstDamage = 0;
    for (const [label, decl] of BAD) {
      const badSrc = { ...SRC, chipX: decl, chipY: decl };
      setScreen(ctx, TGT);                       // the canvas is the 15x10mm target

      // (a) DEFECT REPRODUCTION -- the old guard shape, verbatim: read resolveFrame's output.
      const resolved = ctx.resolveFrame(badSrc);
      const oldGuardPasses = (resolved.chipX > 0) && (resolved.chipY > 0);
      if (oldGuardPasses) oldPassed++;
      ok(oldGuardPasses, `A12 defect reproduces (${label})`,
        'the old guard already refused this, so the fix is not being scored');

      // (b) how wrong it was: seat the cells with that defaulted pitch.
      const l = { mmItems: ctx.projectCellsToWaferMm(rows, badSrc) };
      ctx.reseatOverlayLayer(l);
      const seat = new Map();
      l.items.forEach((list, key) => list.forEach(it => seat.set(`${it.srcX},${it.srcY}`, key)));
      let wrongNow = 0;
      baseSeat.forEach((k, id) => { if (seat.get(id) !== k) wrongNow++; });
      if (wrongNow > worstDamage) worstDamage = wrongNow;

      // (c) THE FIX -- the guard reads where the value came from.
      // The frame is an ARGUMENT now, so the window IS the argument. `withPhysFrame` still
      // sets the binding, but `physDeclaration` no longer reads it -- wrapping would leave
      // this driving state nothing consults.
      const facts = {
        x: ctx.physDeclaration(badSrc, 'chipX', ctx.el.physChipX),
        y: ctx.physDeclaration(badSrc, 'chipY', ctx.el.physChipY),
      };
      const refused = !(facts.x.value > 0) || !(facts.y.value > 0)
        || facts.x.source !== 'frame' || facts.y.source !== 'frame';
      if (refused) newRefused++;
      ok(refused, `A12 guard refuses (${label})`,
        `source=${facts.x.source} value=${facts.x.value} -- a declared grid with no declared pitch got through`);
    }
    ok(oldPassed === BAD.length, 'A12b every bad declaration passed the old guard', `${oldPassed}/${BAD.length}`);
    ok(newRefused === BAD.length, 'A12c every bad declaration is refused now', `${newRefused}/${BAD.length}`);
    ok(worstDamage > 400, 'A12d the defect was material', `worst case moved only ${worstDamage} cells`);
    // A negative pitch was the ONLY thing the old guard caught -- it must still be caught.
    const neg = ctx.physDeclaration({ ...SRC, chipX: -7 }, 'chipX', ctx.el.physChipX);
    ok(!(neg.value > 0), 'A12e negative pitch still refused', `${neg.value}`);
    // ...and a properly declared pitch must NOT be refused, or the guard is just "always no".
    const good = ctx.physDeclaration(SRC, 'chipX', ctx.el.physChipX);
    ok(good.value === SRC.chipX && good.source === 'frame', 'A12f a declared pitch passes',
      `value=${good.value} source=${good.source} -- the guard refuses everything`);
    setScreen(ctx, TGT);

    // A12g -- the SHIPPED guard must be wired to the fact, not to the defaulted number.
    //         `addOverlayLayer` is async and does REST, so it is not executed here; this reads
    //         its source. 🔴 Comments are stripped first -- a sibling harness has a permanent
    //         false red because an ordering assertion matched a symbol inside a comment.
    const addSrc = sliceFunction(src, 'addOverlayLayer')
      .split('\n').map(ln => ln.replace(/\/\/.*$/, '')).join('\n');
    ok(/physDeclaration\s*\(/.test(addSrc), 'A12g the overlay gate calls physDeclaration',
      'the gate is reading a value that has already been defaulted');
    ok(!/resolveFrame[^\n]*\.chipX\s*>\s*0/.test(addSrc), 'A12h the gate does not test resolveFrame output',
      'the old shape is back');
    ok(/frameDimError\s*\(/.test(addSrc), 'A12i the overlay path applies the dimension bound',
      'a 1024x1024 metadata row would sweep the grid on the UI thread');
  }

  // A13 -- SOURCE GRID DIMS ARE BOUNDED. The dims-match refusal went away with rule 6; the
  //        SANITY bound must not have gone with it. A 1024x1024 metadata row opens a frame
  //        window and sweeps the grid synchronously with no way to cancel.
  {
    const b = ctx.frameDimBounds();
    ok(ctx.frameDimError({ cols: 1024, rows: 1024 }) !== '', 'A13 oversize dims refused', '1024x1024 accepted');
    ok(ctx.frameDimError({ cols: 0, rows: 10 }) !== '', 'A13b zero dims refused');
    ok(ctx.frameDimError({ cols: 45.5, rows: 10 }) !== '', 'A13c non-integer dims refused');
    ok(ctx.frameDimError({ cols: -3, rows: 10 }) !== '', 'A13d negative dims refused');
    ok(ctx.frameDimError(SRC) === '' && ctx.frameDimError(TGT) === '',
      'A13e the fixture frames are inside the domain', 'the fixture itself would be refused');
    ok(b.max <= 100, 'A13f the bound is the editor domain', `max=${b.max}`);
  }

  // A14 -- `outside` COUNTS THE POPULATION ITS SENTENCE NAMES.
  //        The chip says "excluded from import". Import (rule 3) skips cells whose canvas
  //        cell is not `inside` -- wafer circle / valid-die mask -- NOT merely "off the grid".
  //        Counting grid membership reported 0 while import silently skipped.
  {
    setScreen(ctx, TGT);
    const sets = ctx.canvasSeatKeys();
    ok(sets.inside.size < sets.all.size, 'A14 the two populations actually differ',
      `inside ${sets.inside.size} == all ${sets.all.size}; this fixture cannot show the defect`);
    const l = { mmItems: ctx.projectCellsToWaferMm(rows, SRC) };
    ctx.reseatOverlayLayer(l);
    let byInside = 0, byAll = 0;
    l.items.forEach((list, key) => {
      if (!sets.inside.has(key)) byInside += list.length;
      if (!sets.all.has(key)) byAll += list.length;      // DEFECT REPRODUCTION: the old population
    });
    ok(l.outside === byInside, 'A14b outside is counted against the import population',
      `layer says ${l.outside}, the inside-set says ${byInside}`);
    ok(byInside > byAll, 'A14c defect reproduces -- the grid-membership count under-reports',
      `inside-based ${byInside} vs grid-based ${byAll}: the old number was not smaller`);
    ok(/가져오기/.test(l.seatNote) || l.outside === 0, 'A14d the sentence names import');

    // A14e -- and the set must honour the TARGET's OWN valid-die mask, because import does.
    //         `isValidDieAt` answers with the bare circle whenever a frame window is open
    //         (a source map must not be cut by this map's mask), so computing these keys
    //         inside a window would silently drop the mask. The seat frame IS the screen, so
    //         no window is needed -- this assertion is what holds that.
    const circleInside = new Set(sets.inside);
    const carved = new Set([...circleInside].slice(0, Math.floor(circleInside.size / 2)));
    ctx.validDie = { basis: 'ref', keys: carved, reason: '', ref: { table: 't', mapKey: 'k' }, raw: 't:k' };
    ctx.validDieResolveSeq++;
    const masked = ctx.canvasSeatKeys();
    ok(masked.inside.size === carved.size, 'A14e the seat keys honour the target valid-die mask',
      `mask has ${carved.size} cells, inside set has ${masked.inside.size} -- the mask was dropped`);
    ok(masked.inside.size < circleInside.size, 'A14f the mask actually carves something',
      'the mask equals the circle; this cannot discriminate');
    ok(masked.all.size === sets.all.size, 'A14g the mask does not change grid membership');
    ctx.validDie = { basis: 'circle', keys: null, reason: '', ref: null, raw: undefined };
    ctx.validDieResolveSeq++;
    ok(ctx.canvasSeatKeys().inside.size === circleInside.size,
      'A14h dropping the mask restores the circle set (the cache tracks the mask generation)');
  }

  // A15 -- DUPLICATE SOURCE ROWS AT IDENTICAL PITCH.
  //        Same coordinate twice with the SAME value carries no information -- collapsing it
  //        keeps a 1:1 map importable (the pre-round code kept the last value). Same
  //        coordinate with DIFFERENT values is a conflict, not a pitch fan-out, and the note
  //        must not blame the cell size.
  {
    setScreen(ctx, TGT);
    const { rows: idRows } = buildSourceRows(ctx, TGT);
    const one = idRows[10];

    const twice = idRows.concat([{ x: one.x, y: one.y, val: one.val }]);
    const lDup = { mmItems: ctx.projectCellsToWaferMm(twice, TGT) };
    ctx.reseatOverlayLayer(lDup);
    ok(lDup.dupCollapsed === 1, 'A15 an identical duplicate row is collapsed', `${lDup.dupCollapsed}`);
    ok(lDup.fanout === 1, 'A15b defect reproduces -- without the collapse this is fanout 2',
      `fanout ${lDup.fanout}`);
    ok(lDup.multiCells === 0, 'A15c and no cell is marked multi-valued', `${lDup.multiCells}`);
    let stillImportable = 0;
    lDup.cells.forEach(v => { if (v !== null) stillImportable++; });
    ok(stillImportable === lDup.cellCount, 'A15d a 1:1 map stays fully importable',
      `${stillImportable} of ${lDup.cellCount}`);

    const conflicting = idRows.concat([{ x: one.x, y: one.y, val: `${one.val}-OTHER` }]);
    const lCon = { mmItems: ctx.projectCellsToWaferMm(conflicting, TGT) };
    ctx.reseatOverlayLayer(lCon);
    ok(lCon.conflictCells === 1, 'A15e a value conflict on one coordinate is counted', `${lCon.conflictCells}`);
    ok(lCon.fanCells === 0, 'A15f and it is NOT reported as pitch fan-out', `fanCells ${lCon.fanCells}`);
    ok(lCon.dupCollapsed === 0, 'A15g a differing value is never collapsed', `${lCon.dupCollapsed}`);
    ok(!/타깃 셀이 더 굵어/.test(lCon.seatNote), 'A15h the note does not blame the cell size',
      `note: ${lCon.seatNote}`);
    ok(/중복/.test(lCon.seatNote), 'A15i the note names the real reason', `note: ${lCon.seatNote}`);
    setScreen(ctx, TGT);
  }

  // A16 -- the inside predicate is CANVAS-SIZE INVARIANT. `canvasSeatKeys` evaluates it at
  //        700x700 while the renderer uses the real canvas; if that were not the same verdict,
  //        the count above could not promise what import will do.
  {
    setScreen(ctx, TGT);
    const pc = ctx.getTransformedPhysicalConfig(null, TGT.rotation, TGT.side);
    const at = (w, h) => {
      const v = [];
      for (let r = 0; r < TGT.rows; r++) for (let c = 0; c < TGT.cols; c++)
        v.push(ctx.isCellInsideWaferFast(c, r, TGT.cols, TGT.rows, pc, w, h));
      return v;
    };
    const base700 = at(700, 700);
    let differ = 0;
    for (const [w, h] of [[200, 200], [431, 431], [1024, 1024], [1600, 1600], [900, 380]]) {
      const v = at(w, h);
      for (let i = 0; i < v.length; i++) if (v[i] !== base700[i]) differ++;
    }
    ok(differ === 0, 'A16 inside predicate is canvas-size invariant', `${differ} verdicts differ`);
    ok(base700.filter(Boolean).length < base700.length, 'A16b some cells really are outside',
      'every cell is inside; A14 could not discriminate');
  }

  // A10 -- STORED TARGET COORDINATES DID NOT MOVE.
  //        Snapshot the coordinate ⚡Push would serialise for every canvas cell, run the whole
  //        overlay projection + seating, snapshot again, compare key by key. The frame window
  //        opens the SOURCE spec during the projection; a leaked `finally` or a contaminated
  //        bounding-box cache slot would show up here and nowhere else.
  {
    setScreen(ctx, TGT);
    const snap = () => {
      const m = new Map();
      const a = screenAxes(TGT);
      for (let r = 0; r < a.visualRows; r++) for (let c = 0; c < a.visualCols; c++) {
        const d = ctx.getDbCoords(null, c, r, TGT.cols, TGT.rows, TGT.rotation, TGT.side, TGT.invertY, TGT.startX, TGT.startY);
        m.set(`${c}_${r}`, `${d.x},${d.y}`);
      }
      return m;
    };
    const before = snap();                       // this also populates the bbox cache
    const l = { mmItems: ctx.projectCellsToWaferMm(rows, SRC) };
    ctx.reseatOverlayLayer(l);
    const after = snap();
    let moved = 0, firstMove = '';
    before.forEach((v, k) => {
      if (after.get(k) !== v) { moved++; if (!firstMove) firstMove = `${k}: ${v} -> ${after.get(k)}`; }
    });
    ok(before.size === after.size, 'A10 snapshot size', `${before.size} vs ${after.size}`);
    ok(before.size > 400, 'A10b snapshot actually covers the canvas', `${before.size} cells`);
    ok(moved === 0, 'A10c stored target coordinates unmoved', `${moved} cells moved, e.g. ${firstMove}`);
    ok(ctx.physFrameOverride === null, 'A10d frame window closed', 'physFrameOverride leaked');
  }

  // A18 -- THE FRAME REACHES `getCanvasCellFromDb`, ON THE BRANCH WHERE THAT IS OBSERVABLE.
  //
  // 🔴 WHY THIS EXISTS. `getCanvasCellFromDb` reads exactly three terms off the origin box:
  //    `minC` always, `minR` when `!invertY`, `maxR` when `invertY`. It never reads `maxC`.
  //    Measured on this fixture, the SOURCE box and the SCREEN box are
  //        source {minC:1, maxC:57, minR:1, maxR:41}
  //        screen {minC:1, maxC:28, minR:1, maxR:18}
  //    -- they differ ONLY in their max terms, and every projection above runs `invertY:false`,
  //    where the only terms read are `minC` and `minR`, which are 1 on both sides. So a mutant
  //    that makes this function ignore its frame entirely changed NOTHING anywhere in this file
  //    and survived. The code was never blind; THE FIXTURE WAS. Same class as `minC == 0`
  //    killing a bbox axis: an axis that cannot move cannot fail.
  //
  // 🔴 SO THE SOURCE FRAME IS INVERTED HERE, which puts `maxR` on the read path -- 41 against
  //    18, twenty-three rows apart. The claim is scored as a ROUND TRIP through the inverse
  //    pair under ONE frame while the screen shows another: `getDbCoords` and
  //    `getCanvasCellFromDb` must agree about WHICH box they are on. If either one silently
  //    falls back to the screen, the trip does not close.
  // ⚠️ This is not the symmetric-break blind spot. A symmetric shift of BOTH functions still
  //    round-trips; that is scored by the absolute-coordinate assertions elsewhere in the
  //    suite. What this catches is the two of them DISAGREEING about the frame, which is
  //    precisely what dropping the argument on one side produces.
  {
    setScreen(ctx, TGT);
    const srcInv = { ...SRC, invertY: true };
    const a = screenAxes(srcInv);
    // The axis must be live: if the two boxes agreed on the term this branch reads, the
    // round trip below would close even with the frame dropped, and prove nothing.
    const boxFrame = ctx.getWaferBoundingBox(srcInv, srcInv.rotation, srcInv.side);
    const boxScreen = ctx.getWaferBoundingBox(null, srcInv.rotation, srcInv.side);
    ok(boxFrame.maxR !== boxScreen.maxR, 'A18 fixture activates the axis (maxR differs)',
      `source maxR=${boxFrame.maxR} screen maxR=${boxScreen.maxR} -- equal means this check is inert`);

    let broke = 0, first = '';
    for (let r = 0; r < a.visualRows; r++) for (let c = 0; c < a.visualCols; c++) {
      const db = ctx.getDbCoords(srcInv, c, r, srcInv.cols, srcInv.rows, srcInv.rotation,
        srcInv.side, true, srcInv.startX, srcInv.startY);
      const back = ctx.getCanvasCellFromDb(srcInv, db.x, db.y, srcInv.cols, srcInv.rows,
        srcInv.rotation, srcInv.side, true, srcInv.startX, srcInv.startY);
      if (back.c !== c || back.r !== r) {
        broke++;
        if (!first) first = `(${c},${r}) -> db(${db.x},${db.y}) -> (${back.c},${back.r})`;
      }
    }
    ok(broke === 0, 'A18b the inverted round trip closes under the SOURCE frame',
      `${broke} of ${a.visualCols * a.visualRows} cells did not return, e.g. ${first} `
      + `-- the two halves of the inverse pair are reading different origin boxes`);
  }

  return { fails, ran, stats: { rows: rows.length, cells: layer.cellCount, maxFan, dSrcPitch, dSwap, dParity } };
}

// ── Baseline ───────────────────────────────────────────────────────────────────────────
const base = runAll(SRC0);
console.log('― rule 6 overlay by physical position ―');
console.log(`fixture: ${base.stats.rows} source cells -> ${base.stats.cells} target cells, max fan-in ${base.stats.maxFan}`);
console.log(`discrimination: wrong pitch moves ${base.stats.dSrcPitch} cells; axis swap ${base.stats.dSwap}; parity flip ${base.stats.dParity}`);
// H1 protocol: the runner reads this line to tell "red with N assertions" from a crash.
console.log(`ASSERTIONS ${base.ran} ${base.fails.length}`);
if (base.fails.length) {
  console.error(`BASELINE RED -- ${base.fails.length} failed:`);
  base.fails.forEach(f => console.error(`  x ${f}`));
  process.exit(1);
}
console.log('baseline: all assertions passed');

// ── Mutation sweep ─────────────────────────────────────────────────────────────────────
// 🔴 Put the defect back and confirm the harness actually goes red. A green suite that
//    cannot fail has measured nothing. APPLIED and CAUGHT are reported separately because a
//    mutation whose pattern no longer matches is a SILENT hole, not a pass.
const MUTATIONS = [
  // ① THE DEFECT THIS ROUND ACTUALLY HIT. Rebuilding mm from the ROUNDED die index instead of
  //    the pre-rounding value drops the offset's sub-cell residual. It looks harmless.
  ['mm rebuilt from the rounded die index (sub-cell residual lost)',
    'mm: (chipX > 0 && chipY > 0) ? { mmX: p.xCells * chipX, mmY: p.yCells * chipY } : null,',
    'mm: (chipX > 0 && chipY > 0) ? { mmX: p.x * chipX, mmY: p.y * chipY } : null,'],
  ['getDieIndex reports the rounded value as the continuous one',
    'return { x: xp, y: yp, xCells: xRot, yCells: yRot };',
    'return { x: xp, y: yp, xCells: xp, yCells: yp };'],
  ['axes swapped when the die index is turned into mm',
    'mm: (chipX > 0 && chipY > 0) ? { mmX: p.xCells * chipX, mmY: p.yCells * chipY } : null,',
    'mm: (chipX > 0 && chipY > 0) ? { mmX: p.xCells * chipY, mmY: p.yCells * chipX } : null,'],
  ['lattice reference discarded (back to a bare centred lattice)',
    'ix0: p.x, iy0: p.y, ux0: p.xCells, uy0: p.yCells,',
    'ix0: 0, iy0: 0, ux0: 0, uy0: 0,'],
  ['remainder thrown away',
    'rx: (dx - nx + 0.5) * L.chipX, ry: (dy - ny + 0.5) * L.chipY,',
    'rx: 0, ry: 0,'],
  ['remainder left in cell units instead of mm',
    'rx: (dx - nx + 0.5) * L.chipX, ry: (dy - ny + 0.5) * L.chipY,',
    'rx: (dx - nx + 0.5), ry: (dy - ny + 0.5),'],
  ['quotient off by half a cell (round -> floor)',
    'const nx = Math.round(dx);\n  const ny = Math.round(dy);',
    'const nx = Math.floor(dx);\n  const ny = Math.floor(dy);'],
  ['representative value chosen for a multi-value cell',
    'cells.set(key, list.length === 1 ? list[0].val : null);',
    'cells.set(key, list[0].val);'],
  ['fan-out collapsed -- last source cell wins',
    'if (!list) { seated.set(key, [entry]); return; }',
    'seated.set(key, [entry]); return;'],
  ['seated with a pitch that is not the target pitch',
    'const L = frameDieLattice(f);',
    'const L = frameDieLattice({ ...f, chipX: f.chipX * 0.5 });'],
  ['seat key cache never invalidates (incomplete cache key)',
    'const ck = `${frameAxesKey(f)}|${basis}|${validDieResolveSeq}`;',
    "const ck = 'one-slot-for-every-frame';"],
  ['overlay gate stops calling physDeclaration (reads the defaulted number again)',
    `const pitchFacts = (frame) => withPhysFrame(frame, () => ({
    x: physDeclaration(frame, 'chipX', el.physChipX),
    y: physDeclaration(frame, 'chipY', el.physChipY),
  }));`,
    `const pitchFacts = (frame) => ({
    x: { value: resolveFrame(frame || currentFrame()).chipX, source: 'frame' },
    y: { value: resolveFrame(frame || currentFrame()).chipY, source: 'frame' },
  });`],
  ['physDeclaration folds absence into the screen value silently',
    "return read(domEl ? domEl.value : null, 'screen') || { value: null, source: 'absent' };",
    "return { value: parseFloat(domEl ? domEl.value : '0') || 2.5, source: 'frame' };"],
  ['outside counted against grid membership again',
    'if (!seatKeys.inside.has(key)) outside += list.length;',
    'if (!seatKeys.all.has(key)) outside += list.length;'],
  // RE-POINTED 2026-08-06 (frame-as-argument). Same defect, new spelling: opening the window
  // is now PASSING a frame, so the mutant passes the source frame where the seat keys must
  // use the screen -- the target's own mask is suspended and lost, exactly as before.
  ['seat keys computed inside a frame window (target mask lost)',
    'if (isValidDieAt(physFrameOverride, p.x, p.y, isCellInsideWaferFast(c, r, visualCols, visualRows, physConfig, 700, 700))) {',
    'if (isValidDieAt(f, p.x, p.y, isCellInsideWaferFast(c, r, visualCols, visualRows, physConfig, 700, 700))) {'],
  ['identical duplicate rows no longer collapsed',
    'if (twin && twin.val === entry.val) { duplicates++; return; }',
    'if (false) { duplicates++; return; }'],
  ['a differing value on the same coordinate is collapsed too (a value is discarded)',
    'if (twin && twin.val === entry.val) { duplicates++; return; }',
    'if (twin) { duplicates++; return; }'],
  ['coordinate conflict reported as pitch fan-out',
    'if (spots.size > 1) fanCells++;',
    'fanCells++;'],
  ['dimension sanity bound removed with the spec gate',
    'const errs = [bad(frame.cols, \'grid_cols\'), bad(frame.rows, \'grid_rows\')].filter(Boolean);',
    'const errs = [];'],
  ['stale grid-membership predicate restored (0 <= px < cols)',
    'if (!seatKeys.inside.has(key)) outside += list.length;',
    'if (!(Number(key.split("_")[0]) >= 0 && Number(key.split("_")[0]) < seat.cols && Number(key.split("_")[1]) >= 0 && Number(key.split("_")[1]) < seat.rows)) outside += list.length;'],
  // ② The source spec must actually reach the projection. If it does not, every source cell is
  //    interpreted with the TARGET's spec -- the canvas still draws, which is why this needs a
  //    scorer rather than an eye.
  //
  // 🔴 RE-POINTED 2026-08-06, and the reason matters more than the edit. This mutant used to
  //    close the frame WINDOW (`physFrameOverride = frame || null` -> `= null`). It went INERT
  //    the moment the frame stopped being module state: `withPhysFrame` still assigns the
  //    binding, but nothing this harness scores reads it any more, so nulling it changed
  //    nothing and the mutant SURVIVED at 20/21. The anchor still applied -- presence and
  //    uniqueness both passed -- so only the survivor accounting caught it. A mutant can rot
  //    while its anchor stays perfectly valid, and that is a third failure mode beside "stale"
  //    and "not unique". The DEFECT it names has not changed at all; its spelling has, from
  //    "the window never opens" to "the frame never reaches the call".
  // ③ The mutant that found A18's blind spot, kept so the spot cannot re-open. It survived at
  //    21/21 before A18 existed: `getCanvasCellFromDb` reads only `minC`, plus `minR` or `maxR`
  //    by branch, and every other check here runs the `!invertY` branch where the source and
  //    screen boxes agree. The anchor carries the `const c =` line because
  //    `getWaferBoundingBox(frame, rotation, side)` alone appears in `getDbCoords` too and the
  //    uniqueness guard would (correctly) refuse it.
  ['getCanvasCellFromDb drops its frame (origin box taken from the screen)',
    '  const box = getWaferBoundingBox(frame, rotation, side);\n\n  const c = dbX - startX + box.minC;',
    '  const box = getWaferBoundingBox(null, rotation, side);\n\n  const c = dbX - startX + box.minC;'],
  ['frame never reaches the projection (source read with the target spec)',
    "    const chipX = physNum(f, 'chipX', el.physChipX, 2.5);\n    const chipY = physNum(f, 'chipY', el.physChipY, 2.5);",
    "    const chipX = physNum(null, 'chipX', el.physChipX, 2.5);\n    const chipY = physNum(null, 'chipY', el.physChipY, 2.5);"],
];

// ── Anchor validation, BEFORE a single mutant is scored ────────────────────────────────
// Hoisted out of the sweep, and given the sibling harnesses' verdict (`die` -> exit 2,
// "nothing was compared") rather than a plain exit 1. Three things were wrong with catching
// this at the bottom, and only the first one was ever caught at all:
//
// 🔴 IT REFUSED LATE. The tally below did stop the build on a vanished anchor, but only after
//    the whole sweep had run and the `ASSERTIONS` line had already been printed green, with
//    the reason buried under twenty lines of CAUGHT. And it exited 1, which the runner reads
//    as "this harness is red" -- indistinguishable from a real assertion failure. A mutant
//    that was never introduced is neither: the harness is BROKEN, and that is exit 2.
// 🔴 UNIQUENESS WAS NOT CHECKED AT ALL, and that is the half that bites a refactor.
//    `String.replace` with a string pattern takes the FIRST match and reports nothing. An
//    anchor that stops being unique -- which is exactly what threading a new argument
//    through many similar call sites can do -- lands the mutant somewhere nobody chose, and
//    it is then "caught" for a reason that has nothing to do with the defect it names. A
//    fake catch reads identically to a real one.
// 🔴 AN UNAPPLIED MUTANT IS NOT A CAUGHT MUTANT. Re-point a stale anchor; never delete the
//    mutant to get the build green. The mutant is the only evidence the check above it can
//    fail at all.
//
// Measured when this guard was added: 21 declared anchors, all present, all unique. It is a
// no-op on this tree ON PURPOSE -- a guard installed after the round that needs it is a
// guard that was not there when it mattered.
for (const [name, from] of MUTATIONS) {
  const i = SRC0.indexOf(from);
  if (i < 0) {
    die(`mutation anchor not found: ${name}\n  pattern: ${from.slice(0, 90)}\n`
      + `  The source moved under this mutant. Re-point it -- do not drop it.`);
  }
  if (SRC0.indexOf(from, i + 1) >= 0) {
    die(`mutation anchor is not unique: ${name}\n  pattern: ${from.slice(0, 90)}\n`
      + `  \`replace\` takes the first match, so this mutant would be applied at a site `
      + `nobody chose and could be "caught" for the wrong reason. Lengthen the anchor.`);
  }
}

let applied = 0, caught = 0;
for (const [name, from, to] of MUTATIONS) {
  applied++;
  const mutated = SRC0.replace(from, to);
  let red = false, why = '';
  try {
    const r = runAll(mutated);
    red = r.fails.length > 0;
    why = r.fails[0] || '';
  } catch (e) { red = true; why = `threw: ${e.message}`; }
  if (red) { caught++; console.log(`  v CAUGHT: ${name}  (${why})`); }
  else console.log(`  x SURVIVED: ${name}`);
}
console.log(`mutations: ${caught}/${applied} caught (${MUTATIONS.length} declared)`);
if (applied !== MUTATIONS.length) { console.error('a declared mutation no longer applies -- the harness has a silent hole'); process.exit(1); }
if (caught !== applied) process.exit(1);
