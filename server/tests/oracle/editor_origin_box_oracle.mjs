// THE ORIGIN BOX, READ OUT OF THE EDITOR ITSELF.
//
// Run: node server/tests/oracle/editor_origin_box_oracle.mjs <request.json> [> answer.json]
//
// WHY THIS EXISTS. `server/map_alignment.start_from_placement` has to produce the origin that
// makes `client2/src/map_editor.js` redraw a confirmed map on the dies the alignment put it on.
// The number it needs depends on the editor's ORIGIN BOX, and that box has two branches
// (`getWaferBoundingBox`, `map_editor.js:1942-2006`) — the wafer circle, or the valid-die mask.
// Four coordinate formulas in `map_alignment.py` have already been derived by hand and shipped
// wrong; the most recent was right in 4 of 32 combinations and the worked example that checked
// it landed in those 4. So the answer is not derived here. It is READ BACK from the editor's
// own functions, sliced out of the shipped source and run.
//
// 🔴 THIS FILE MUST NOT CONTAIN ANY GEOMETRY. Every number it emits comes out of a function
//    sliced from `map_editor.js`. If you find yourself writing `- box.minC` here, stop: that is
//    the fifth transcription, and it is the thing this file exists to make unnecessary.
// 🔴 `client2/**` IS READ-ONLY FOR THE SERVER LANE, which is why this lives under `server/tests`
//    even though it slices a client file. It reads; it never writes there.
// ⚠️ THE SLICE LIST IS THE FRAGILE PART. A rename in `map_editor.js` makes this die loudly
//    (`ORACLE FAILURE`), never quietly green — see `client2/tests/valid_die_head_parity_oracle.mjs`,
//    which carries the same discipline and the accepted-spellings list that goes with it.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC_PATH = join(HERE, '..', '..', '..', 'client2', 'src', 'map_editor.js');

function die(msg) {
  console.error(`ORACLE FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was measured.)');
  process.exit(2);
}

function sliceBalanced(src, startIdx) {
  const i = src.indexOf('{', startIdx);
  if (i < 0) return null;
  let depth = 0;
  for (let j = i; j < src.length; j++) {
    if (src[j] === '{') depth++;
    else if (src[j] === '}') { depth--; if (depth === 0) return src.slice(startIdx, j + 1); }
  }
  return null;
}

// Newest spelling first, the way the parity oracle does it: a rename must not silently
// disable the measurement.
const NEEDED = [
  ['physNum'], ['gridDimNum'], ['getScreenShift'], ['getTransformedPhysicalConfig'],
  ['getDieIndex', 'getPhysicalCoords'],
  ['isCellInsideWaferFast'], ['validDieBasis'], ['isValidDieAt'],
  ['getWaferBoundingBox'], ['getCanvasCellFromDb'], ['getDbCoords'],
];

function buildSandbox(src) {
  const parts = [];
  for (const aliases of NEEDED) {
    let hit = null;
    for (const name of aliases) {
      const m = new RegExp(`(?:async\\s+)?function\\s+${name}\\s*\\(`).exec(src);
      if (m) { hit = { name, index: m.index }; break; }
    }
    if (!hit) die(`none of [${aliases.join(', ')}] found in map_editor.js`);
    const out = sliceBalanced(src, hit.index);
    if (!out) die(`unbalanced braces for ${hit.name}`);
    parts.push(out);
  }
  const ctx = {
    console,
    el: {},
    currentRotation: 0,
    currentSide: 'front',
    validDie: null,
    boundingBoxCache: {},
    validDieResolveSeq: 0,
  };
  vm.createContext(ctx);
  try { vm.runInContext(parts.join('\n\n'), ctx); } catch (e) {
    die(`sandbox evaluation failed - ${e && e.message ? e.message : e}`);
  }
  return ctx;
}

const inputStub = (v) => ({ value: String(v) });

// Seat the screen controls on one map. This is the ONLY state the sliced functions read.
function seat(ctx, m) {
  ctx.el = {
    physWaferDia: inputStub(m.phys.dia), physEdgeMargin: inputStub(m.phys.em),
    physChipX: inputStub(m.phys.chipX), physChipY: inputStub(m.phys.chipY),
    physOffsetX: inputStub(m.phys.offX), physOffsetY: inputStub(m.phys.offY),
    gridCols: inputStub(m.cols), gridRows: inputStub(m.rows),
    gridStartX: inputStub(m.startX), gridStartY: inputStub(m.startY),
    gridYInvert: { checked: !!m.invertY },
  };
  ctx.currentRotation = m.rot;
  ctx.currentSide = m.side;
  // A new generation, and an empty cache. `resolveValidDie` does exactly this on every
  // designation, and skipping it is how a box measured under the previous mask survives
  // into the next answer (map_editor.js, the cache note above `boundingBoxCache = {}`).
  ctx.validDieResolveSeq += 1;
  ctx.boundingBoxCache = {};
}

const CIRCLE_STATE = { basis: 'circle', keys: null, reason: '', ref: null, raw: undefined };
const maskState = (keys) => ({ basis: 'ref', keys, reason: '', ref: { table: 'valid_die_ref', mapKey: 'F' }, raw: 'F' });

// Stored (x, y) -> the die the editor draws it on, under whatever is currently seated.
const seatsOf = (ctx, m, stored) => vm.runInContext(`(function (m, stored) {
  return stored.map(function (p) {
    var cell = getCanvasCellFromDb(null, p[0], p[1], m.cols, m.rows, m.rot, m.side,
                                   !!m.invertY, m.startX, m.startY);
    var d = getDieIndex(null, cell.c, cell.r, m.cols, m.rows, m.rot, m.side);
    return [d.x, d.y];
  });
})`, ctx)(m, stored);

const boxOf = (ctx, m) => vm.runInContext(
  `(function (m) { var b = getWaferBoundingBox(null, m.rot, m.side); `
  + `return [b.minC, b.maxC, b.minR, b.maxR]; })`, ctx)(m);

// ── run ────────────────────────────────────────────────────────────────────────
const reqPath = process.argv[2];
if (!reqPath) die('usage: editor_origin_box_oracle.mjs <request.json>');
const req = JSON.parse(readFileSync(reqPath, 'utf8'));
const ctx = buildSandbox(readFileSync(SRC_PATH, 'utf8'));

// The mask, built the way `resolveValidDie` builds it: the REFERENCE map's stored cells, put
// through the reference's OWN frame (`projectCellsToPhys(cells, refFrame)`), keyed by die.
// The reference is read under the circle branch on purpose - inside a frame window
// `isValidDieAt` answers with the circle, so a reference never masks itself.
seat(ctx, req.ref);
ctx.validDie = CIRCLE_STATE;
const refSeats = seatsOf(ctx, req.ref, req.ref.cells);
const maskKeys = new Set(refSeats.map(([x, y]) => `${x}_${y}`));

const out = { ref: { box: boxOf(ctx, req.ref), seats: refSeats, mask_size: maskKeys.size },
              cases: [] };

for (const c of req.cases) {
  seat(ctx, c);
  ctx.validDie = CIRCLE_STATE;
  const boxCircle = boxOf(ctx, c);
  const seatsCircle = seatsOf(ctx, c, c.stored || []);

  seat(ctx, c);
  ctx.validDie = maskState(maskKeys);
  const basis = vm.runInContext('validDieBasis()', ctx);
  const boxMask = boxOf(ctx, c);
  const seatsMask = seatsOf(ctx, c, c.stored || []);

  out.cases.push({ name: c.name, basis, box_circle: boxCircle, box_mask: boxMask,
                   seats_circle: seatsCircle, seats_mask: seatsMask });
}

process.stdout.write(JSON.stringify(out));
