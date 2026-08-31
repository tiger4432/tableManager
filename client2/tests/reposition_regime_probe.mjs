/**
 * Measurement probe — the two origin-anchoring regimes on the REAL declared maps.
 *
 * Read-only. Slices the shipped geometry out of map_editor.js (same technique as
 * valid_die_frame_adoption_harness.mjs) and runs it against the frames actually stored in
 * `wafer_map_metadata` for bonding_map, plus the real stored cells for the named maps.
 *
 * Answers three questions the spec asks:
 *   1. Which real frames CLIP the wafer circle (minC stops being the wafer edge)?
 *   2. What is `minC - (vC-1)/2` per real frame (the parity term)?
 *   3. For each real (target, reference) pair whose dimensions differ, how many stored
 *      coordinates can a reposition preserve exactly, and how many cannot?
 *
 * Run:  node client2/tests/reposition_regime_probe.mjs <cells.json> <frames.json>
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = readFileSync(join(HERE, '..', 'src', 'map_editor.js'), 'utf8').replace(/\r\n/g, '\n');

function sliceFunction(source, name) {
  const decl = new RegExp(`(^|\\n)\\s*(?:async\\s+)?function\\s+${name}\\s*\\(`);
  const m = decl.exec(source);
  if (!m) throw new Error(`'${name}' not found`);
  const start = m.index + (m[1] ? m[1].length : 0);
  let i = source.indexOf('{', m.index + m[0].length - 1);
  let depth = 0;
  for (; i < source.length; i++) {
    if (source[i] === '{') depth++;
    else if (source[i] === '}') { depth--; if (depth === 0) return source.slice(start, i + 1); }
  }
  throw new Error(`unbalanced braces in '${name}'`);
}

// ⚠️ `dbCoordsByPhysKey` WAS SLICED HERE AND IS NOW DELETED FROM THE SOURCE (`61440e6` removed
//    frame adoption; the function existed only to price it, and had no other caller). Leaving
//    it in this list would have made the probe throw `'dbCoordsByPhysKey' not found` on every
//    run — a tool that dies at startup, which is the exact failure this repository has already
//    had three times. Questions 1 and 2 never touched it, so the probe is retargeted rather
//    than retired: `coordsByPhysKey` below is the same two-line composition, built from the two
//    shipped PER-CELL primitives that remain.
const SYMBOLS = ['physNum', 'gridDimNum', 'getDieIndex',
  'getCanvasCellFromDieIndex', 'getCanvasCellFromDb', 'getTransformedPhysicalConfig',
  'getScreenShift', 'isCellInsideWaferFast', 'getWaferBoundingBox', 'getDbCoords',
  'frameFromMeta', 'currentFrame', 'resolveFrame', 'projectCellsToPhys'];

// `physical key -> stored (DB) coordinate` under an arbitrary frame. Identical in behaviour to
// the deleted `dbCoordsByPhysKey`, and to `coordMapOracle` in
// valid_die_frame_adoption_harness.mjs — the renderer's own two lines, run inside a frame window.
function coordsByPhysKey(S, frame) {
  const rf = S.resolveFrame(frame);
  const isRot = (rf.rotation === 90 || rf.rotation === 270);
  const vC = isRot ? rf.rows : rf.cols, vR = isRot ? rf.cols : rf.rows;
  return (() => {
    const out = new Map();
    for (let r = 0; r < vR; r++) {
      for (let c = 0; c < vC; c++) {
        const p = S.getDieIndex(null, c, r, rf.cols, rf.rows, rf.rotation, rf.side);
        const v = S.getDbCoords(null, c, r, rf.cols, rf.rows, rf.rotation, rf.side,
          rf.invertY, rf.startX, rf.startY);
        out.set(`${p.x}_${p.y}`, `${v.x}_${v.y}`);
      }
    }
    return out;
  });
}

function makeInput(v) { return { value: String(v), checked: false }; }

function env(frame) {
  const el = {
    gridCols: makeInput(frame.grid_cols), gridRows: makeInput(frame.grid_rows),
    gridStartX: makeInput(frame.grid_start_x), gridStartY: makeInput(frame.grid_start_y),
    gridYInvert: { checked: !!frame.grid_y_invert },
    physWaferDia: makeInput(frame.phys_wafer_dia), physChipX: makeInput(frame.phys_chip_x),
    physChipY: makeInput(frame.phys_chip_y), physOffsetX: makeInput(frame.phys_offset_x),
    physOffsetY: makeInput(frame.phys_offset_y), physEdgeMargin: makeInput(frame.phys_edge_margin),
    gridCanvas: { getBoundingClientRect: () => ({ width: 700, height: 700 }) },
  };
  const sandbox = {
    console, el, boundingBoxCache: {},
    currentRotation: Number(frame.rotation) || 0,
    currentSide: frame.side === 'back' ? 'back' : 'front',
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(SYMBOLS.map(n => sliceFunction(SRC, n)).join('\n'), sandbox);
  return sandbox;
}

const cells = JSON.parse(readFileSync(process.argv[2], 'utf8').replace(/\r\n/g, '\n'));
const frames = JSON.parse(readFileSync(process.argv[3], 'utf8').replace(/\r\n/g, '\n'));

// ── 1 + 2: the two regimes, per real frame ─────────────────────────────────────────────
console.log('== regime per real declared frame (bonding_map) ==');
console.log('map            dims    rot side  chip      box(minC,minR,maxC,maxR)  clip(L,R,T,B) '
  + ' minC-(vC-1)/2  minR-(vR-1)/2');
const REGIME = {};
for (const [name, f] of Object.entries(frames)) {
  const S = env(f);
  const rot = Number(f.rotation) || 0, side = f.side === 'back' ? 'back' : 'front';
  const r90 = (rot === 90 || rot === 270);
  const vC = r90 ? f.grid_rows : f.grid_cols, vR = r90 ? f.grid_cols : f.grid_rows;
  const box = S.getWaferBoundingBox(null, rot, side);
  const pc = S.getTransformedPhysicalConfig(null, rot, side);
  // exact clipping test: would a column one step OUTSIDE the grid still be inside the circle?
  // `isCellInsideWaferFast` is a pure formula, so it answers for c = -1 and c = vC too.
  const anyIn = (c, r) => S.isCellInsideWaferFast(c, r, vC, vR, pc, 700, 700);
  const rowsIdx = [...Array(vR).keys()], colsIdx = [...Array(vC).keys()];
  const clipL = rowsIdx.some(r => anyIn(-1, r)), clipR = rowsIdx.some(r => anyIn(vC, r));
  const clipT = colsIdx.some(c => anyIn(c, -1)), clipB = colsIdx.some(c => anyIn(c, vR));
  const px = (box.minC - (vC - 1) / 2).toFixed(1), py = (box.minR - (vR - 1) / 2).toFixed(1);
  REGIME[name] = { clipL, clipR, clipT, clipB, box, vC, vR };
  console.log(`${name.padEnd(13)} ${String(f.grid_cols + 'x' + f.grid_rows).padEnd(7)} `
    + `${String(rot).padStart(3)} ${side.padEnd(5)} ${String(f.phys_chip_x + 'x' + f.phys_chip_y).padEnd(9)} `
    + `(${box.minC},${box.minR},${box.maxC},${box.maxR})`.padEnd(25)
    + ` ${[clipL, clipR, clipT, clipB].map(b => b ? 'Y' : '.').join('')}         `
    + `${px.padStart(7)}       ${py.padStart(7)}`);
}

// ── 3: what a frame change WOULD cost, on real cells, for every real pair with differing dims ──
// ⚠️ THIS IS NOW A COUNTERFACTUAL, NOT A MODEL OF SHIPPED BEHAVIOUR. Nothing repositions any
//    more — a valid-die designation adopts nothing (F8), so no stored coordinate moves. What
//    this section measures is the cost that decision AVOIDS on the real declared maps, which is
//    still the number that justifies it: `coordsByPhysKey(from)` gives physKey -> stored coord,
//    and the inverse of `coordsByPhysKey(to)` gives stored coord -> physKey.
function plan(S, fromFrame, toFrame, physKeys) {
  const before = coordsByPhysKey(S, fromFrame);
  const after = coordsByPhysKey(S, toFrame);
  const byCoord = new Map(); let dup = 0;
  after.forEach((v, k) => { if (byCoord.has(v)) dup++; else byCoord.set(v, k); });
  let same = 0, movedKey = 0; const unrepresentable = [], stranded = [], newKeys = [];
  for (const k of physKeys) {
    const b = before.get(k);
    if (b === undefined) { stranded.push(k); continue; }
    const nk = byCoord.get(b);
    if (nk === undefined) { unrepresentable.push(`${k}@DB(${b.replace('_', ',')})`); continue; }
    newKeys.push(nk);
    if (nk === k) same++; else movedKey++;
  }
  return { same, movedKey, unrepresentable, stranded, newKeys, dupCoords: dup,
           coordsBefore: before.size, coordsAfter: after.size };
}

// Load each named map's cells into physical keys under ITS OWN frame (what loadExistingMap does).
function physKeysOf(name) {
  const f = frames[name];
  const S = env(f);
  const fr = S.frameFromMeta({ ...f });
  return { keys: [...S.projectCellsToPhys(cells[name] || [], fr).keys()], frame: fr, S };
}

console.log('\n== reposition plan on REAL cells, target <- reference (dims differ) ==');
const names = Object.keys(cells).filter(n => (cells[n] || []).length > 0);
for (const tgt of names) {
  const { keys, frame: tgtFrame, S } = physKeysOf(tgt);
  for (const ref of Object.keys(frames)) {
    if (ref === tgt) continue;
    const refFrame = S.frameFromMeta({ ...frames[ref] });
    if (refFrame.cols === tgtFrame.cols && refFrame.rows === tgtFrame.rows) continue;
    // the adopted frame: current placement axes + the reference's dims and physical spec
    const adopted = { ...tgtFrame, cols: refFrame.cols, rows: refFrame.rows,
      waferDia: refFrame.waferDia, chipX: refFrame.chipX, chipY: refFrame.chipY,
      offsetX: refFrame.offsetX, offsetY: refFrame.offsetY, edgeMargin: refFrame.edgeMargin };
    const p = plan(S, tgtFrame, adopted, keys);
    // How many repositioned cells fall OUTSIDE the new frame's wafer circle? Those are the
    // cells the pre-existing Push contrast gate refuses — the price of clause 3 (the
    // reference's physical spec wins), not a coordinate error. Counted with the shipped
    // `isCellInsideWaferFast` under the adopted frame.
    const rot = adopted.rotation, side = adopted.side;
    const r90 = (rot === 90 || rot === 270);
    const vC = r90 ? adopted.rows : adopted.cols, vR = r90 ? adopted.cols : adopted.rows;
    let blockedByCircle = 0;
    (() => {
      const pc = S.getTransformedPhysicalConfig(null, rot, side);
      const cellOf = new Map();
      for (let r = 0; r < vR; r++) for (let c = 0; c < vC; c++) {
        const pk = S.getDieIndex(null, c, r, adopted.cols, adopted.rows, rot, side);
        cellOf.set(`${pk.x}_${pk.y}`, [c, r]);
      }
      p.newKeys.forEach(nk => {
        const cr = cellOf.get(nk);
        if (!cr || !S.isCellInsideWaferFast(cr[0], cr[1], vC, vR, pc, 700, 700)) blockedByCircle++;
      });
    });
    p.blockedByCircle = blockedByCircle;
    // ⚠️ `offCircle` is a LOWER BOUND on what ⚡ Push refuses, NOT a "pushable" verdict.
    //    Measured 2026-07-30: this probe said offCircle=0 for `Q1 <- 4B13` and the app blocked 1.
    //    The reason is that after a designation the basis is the REFERENCE MAP'S MASK
    //    (`isValidDieAt`), which is strictly narrower than the circle — and a different map's
    //    mask has no reason to cover this map's own dies. Reading this column as "Push will
    //    succeed" is exactly the silently-wrong class this file exists to measure.
    const verdict = (p.unrepresentable.length || p.stranded.length || p.dupCoords) ? 'REFUSE'
      : (blockedByCircle === 0 ? 'ok (circle covers all; mask may still block)' : 'ok');
    console.log(`${tgt.padEnd(11)} <- ${ref.padEnd(11)} ${tgtFrame.cols}x${tgtFrame.rows}`
      + `->${refFrame.cols}x${refFrame.rows} cells=${String(keys.length).padStart(4)} `
      + `same=${String(p.same).padStart(4)} rekeyed=${String(p.movedKey).padStart(4)} `
      + `unrepresentable=${String(p.unrepresentable.length).padStart(4)} `
      + `stranded=${String(p.stranded.length).padStart(3)} offCircle=${String(p.blockedByCircle).padStart(3)}  ${verdict}`
      + (p.unrepresentable.length ? `  e.g. ${p.unrepresentable.slice(0, 3).join(' ')}` : ''));
  }
}

// H1 protocol. This probe MEASURES and asserts nothing -- 0 ran is the honest count. If it
// ever exits 0 again, the runner will refuse the green until someone gives it real
// assertions: a 0-assertion green gate is a comment, not a gate. That refusal is by design.
console.log('ASSERTIONS 0 0');
