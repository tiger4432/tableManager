/**
 * MAP EDITOR 2 -- THE SCREEN DRAWS WHERE THE SERVER SEATED THE MAP.
 *
 * THE REPORT THIS EXISTS FOR (product owner, 2026-08-06):
 *   「좌우대칭 맵인데 front는 화면 안 틀어지고 back은 화면 틀어져 있음」 · 「x축 개수는 짝수」
 *   「x만큼 틀어진 게 아니라 x, y 다 틀어지는데」
 *
 * THE ARITHMETIC. The server ships the seat it scored at
 * (`map_alignment.py` `_candidate_rows`, the `placement` block):
 *
 *     placed = anchor_ref + linear * (cell - anchor_src)
 *
 * The screen used to RECOMPOSE that from a frame it built itself, seating cells at
 * `seatOf(frame, x, y) + shift`. `seatOf` is `A_frame * (c, r) + b_frame`, where `b_frame` is a
 * constant built out of `visualCols - 1`. So the displacement between the two is
 *
 *     T = b_frame - anchor_ref + linear * anchor_src + shift        (when A_frame == linear)
 *
 * and, because the shipped `shift` is the SAME (dx, dy) that `anchor_ref` already contains,
 * the shift cancels and T reduces to a constant that reads only the anchor pair and the grid
 * span:
 *
 *     T = b_frame - R + linear * A          R = reference top-left, A = source anchor
 *
 * 🔴 THAT IS WHY THE FRONT LOOKED FINE. On the front frames b = (0,0) and linear = I, so
 *    T = A - R -- which is ZERO whenever the source's anchor die and the reference's top-left
 *    die share a stored coordinate, the ordinary full-map case. On the back frames the MIRROR
 *    FLIPS THE SIGN of the anchor term while b is added unmirrored, so the two can no longer
 *    cancel and the whole overlay is translated. A left-right symmetric map hides the mirror
 *    itself, so all the operator can see is the translation -- which is exactly the report.
 *
 * WHAT IS SCORED
 *   A. THE SEATS, KEY BY KEY, against an INDEPENDENT oracle -- three lines of matrix arithmetic
 *      in this file that read the wire's `placement` and nothing else. It does not call
 *      `seatOf`, `localIndex`, `boundingBoxOf` or `physOf`, so a defect in any of them cannot
 *      be reproduced by the scorer (memory: an oracle that answers the same for two inputs is
 *      not an oracle).
 *   B. FRONT VERSUS BACK, SEPARATELY AND PER AXIS. The defect's front error is (0,0) by
 *      construction, so a front-only fixture proves nothing and this file says so out loud by
 *      asserting the front error IS zero on the old rule while a back error is not.
 *   C. HOW MANY RENDERED CELLS MOVE between the old rule and the shipped seat, per candidate
 *      and per axis. If that total is ever 0 the fixture has stopped activating the defect and
 *      this harness must go red rather than green.
 *   D. THE DOUBLE APPLICATION. `anchor_ref` already carries the solved shift; adding it again is
 *      the mirror image of the server defect `4947a65` fixed. Asserted as a REFUSAL: the seating
 *      function accepts no shift argument.
 *   E. ABSENT IS NOT THE IDENTITY. A candidate with no placement yields no seating and a named
 *      reason -- never an unturned, unmoved copy of the source drawn on top of the floor.
 *   F. NO ORIGIN AND NO BOX ARE READ. `start_x`, `start_y` and every physical parameter are
 *      varied over the payload and the drawn seats must not move by one cell.
 *
 * THE FIXTURE ACTIVATES THE DEFECT AXES AT ONCE -- an asymmetric blob (a symmetric one cannot
 * show a mirror defect), an EVEN x span as the operator reported, non-zero start on BOTH axes,
 * anisotropic chip pitch, and a bounding box whose minC and minR are both non-zero.
 *
 * CONSOLE OUTPUT IS ASCII ONLY (cp949-safe): no emoji, no em-dash.
 */

import { adaptPayload, seatingFor, floorSeating } from '../src/map2/main.js';
import { placeCells, compareSeatings } from '../src/map2/seating.js';
import { candidateList } from '../src/map2/candidates.js';

let compared = 0;
const failures = [];
function ok(cond, what) { compared++; if (!cond) failures.push(what); }
function eq(actual, expected, what) {
  compared++;
  if (actual !== expected) {
    failures.push(`${what}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

// ── THE SERVER'S LINEAR TABLE, TRANSCRIBED ──────────────────────────────────────
// `map_overlay.frame_linear_part`, term for term. It is here so the fixture ships
// the matrices a real server would ship for these eight ids -- attaching arbitrary matrices
// would make the old rule differ for a reason of my own making rather than the defect's.
const ROT_FWD = { 0: [[1, 0], [0, 1]], 90: [[0, 1], [-1, 0]],
                  180: [[-1, 0], [0, -1]], 270: [[0, -1], [1, 0]] };
const ROT_INV = { 0: [[1, 0], [0, 1]], 90: [[0, -1], [1, 0]],
                  180: [[-1, 0], [0, -1]], 270: [[0, 1], [-1, 0]] };
const sideMat = (side, rotated) => (String(side).toLowerCase() !== 'back'
  ? [[1, 0], [0, 1]]
  : (rotated ? [[1, 0], [0, -1]] : [[-1, 0], [0, 1]]));
const mul = (a, b) => [
  [a[0][0] * b[0][0] + a[0][1] * b[1][0], a[0][0] * b[0][1] + a[0][1] * b[1][1]],
  [a[1][0] * b[0][0] + a[1][1] * b[1][0], a[1][0] * b[0][1] + a[1][1] * b[1][1]]];

function linearPart(src, tgt) {
  const m1 = [[1, 0], [0, src.yInvert ? -1 : 1]];
  const m2 = mul(ROT_FWD[src.rotation], sideMat(src.side, src.rotation === 90 || src.rotation === 270));
  const m3 = mul(sideMat(tgt.side, tgt.rotation === 90 || tgt.rotation === 270), ROT_INV[tgt.rotation]);
  const m4 = [[1, 0], [0, tgt.yInvert ? -1 : 1]];
  return mul(m4, mul(m3, mul(m2, m1)));
}

// ── THE OLD RULE, TRANSCRIBED ───────────────────────────────────────────────────
// `main.framesFor` + `seating.computeSeating` as they stood before this round: an identity box
// (no physical parameters ever reached the frame, so `physOf` returned null), `startX/startY`
// defaulted to 0 from fields that do not exist, `invertY` suppressed, and the solved shift
// added on top. Kept here rather than in the source so the harness scores what the operator
// was actually looking at, and keeps scoring it after the source is repaired.
function legacySeat(frame, x, y, dims, shift) {
  const quarter = frame.rotation === 90 || frame.rotation === 270;
  const visualCols = quarter ? dims.rows : dims.cols;
  const visualRows = quarter ? dims.cols : dims.rows;
  let cm = x;                    // localIndex with start 0 and box.minC 0
  let rm = y;                    // ... and the invertY mirror suppressed
  if (frame.side === 'back') {
    if (quarter) rm = (visualRows - 1) - y;
    else cm = (visualCols - 1) - x;
  }
  let p;
  switch (frame.rotation) {
    case 90:  p = { x: rm, y: (visualCols - 1) - cm }; break;
    case 180: p = { x: (visualCols - 1) - cm, y: (visualRows - 1) - rm }; break;
    case 270: p = { x: (visualRows - 1) - rm, y: cm }; break;
    default:  p = { x: cm, y: rm };
  }
  return { x: p.x + shift.dx, y: p.y + shift.dy };
}

/** THE ORACLE. The producer's own sentence, and it reads nothing else. */
function oracleSeat(placement, x, y) {
  const L = placement.linear;
  const dx = x - placement.anchor_src[0];
  const dy = y - placement.anchor_src[1];
  return { x: placement.anchor_ref[0] + L[0][0] * dx + L[0][1] * dy,
           y: placement.anchor_ref[1] + L[1][0] * dx + L[1][1] * dy };
}

// ── THE FIXTURE ─────────────────────────────────────────────────────────────────
// A wafer-shaped blob, deliberately ASYMMETRIC: a symmetric map maps onto itself under the
// mirror, so every mirror defect would be invisible by construction. Stored coordinates start
// at x = 1 and y = 2 -- BOTH axes non-zero, because a y-clean fixture cannot show a y defect
// and the previous sweep's `(-start_x, 0)` figure was measured on one.
const START_X = 1;
const START_Y = 2;
// Row widths, top to bottom. Row 0 has 2 dies (an even x span, as the operator reported), and
// the left edge of each row is chosen so the blob leans right -- the asymmetry.
const ROWS = [
  { at: 3, w: 2 }, { at: 1, w: 6 }, { at: 0, w: 8 }, { at: 0, w: 8 },
  { at: 1, w: 7 }, { at: 2, w: 5 }, { at: 3, w: 3 },
];
const SRC_CELLS = [];
for (let r = 0; r < ROWS.length; r++) {
  for (let i = 0; i < ROWS[r].w; i++) {
    SRC_CELLS.push([START_X + ROWS[r].at + i, START_Y + r]);
  }
}
// The source's anchor: first in the walk, so minimum y then minimum x on that row.
const ANCHOR_SRC = [START_X + ROWS[0].at, START_Y];
// 🔴 THE REFERENCE'S TOP-LEFT EQUALS THE SOURCE'S ANCHOR. That is not a convenience -- it is
//    the condition under which the front error is exactly (0,0), and reproducing the operator's
//    "front is fine, back is wrong" split is the whole point of this fixture. Two maps of the
//    same product on the same grid share the die, so this is the ordinary case, not a contrived
//    one. Under it, the old rule's error is a pure function of the mirror.
const REF_TOP_LEFT = [ANCHOR_SRC[0], ANCHOR_SRC[1]];
// The residual the scorer solved. NON-ZERO on both axes, so a reader that dropped it or applied
// it twice is separable from one that applied it once.
const SHIFT = { dx: 3, dy: -2 };
const ANCHOR_REF = [REF_TOP_LEFT[0] + SHIFT.dx, REF_TOP_LEFT[1] + SHIFT.dy];

// Both maps declare `grid_y_invert` -- production carries it (`seating.js:192`) and it is the
// axis that INVERTS WHICH FRAMES ARE MIRRORS.
const SRC_AXES = { yInvert: true };
const REF_AXES = { rotation: 0, side: 'front', yInvert: true };

const FRAMES = candidateList().map(c => c.id);
function axesOf(id) {
  const m = /^rot(\d+)_(front|back)$/.exec(id);
  return { rotation: Number(m[1]), side: m[2] };
}

const PLACEMENTS = new Map(FRAMES.map(id => {
  const a = axesOf(id);
  return [id, { linear: linearPart({ ...a, yInvert: SRC_AXES.yInvert }, REF_AXES),
                anchor_src: ANCHOR_SRC, anchor_ref: ANCHOR_REF }];
}));

// THE TRUTH. The floor is the image of the source under ONE candidate, so that candidate scores
// 100% agreement and the fixture is a real alignment rather than a pile of numbers.
const TRUTH = 'rot90_back';
const FLOOR_CELLS = SRC_CELLS.map(([x, y]) => {
  const p = oracleSeat(PLACEMENTS.get(TRUTH), x, y);
  return [p.x, p.y];
});

function wire(overrides) {
  return {
    state: 'scored',
    reference: { state: 'resolved', kind: 'values', cells: FLOOR_CELLS },
    sources: { map_count: 1, cell_count: SRC_CELLS.length, cells: SRC_CELLS,
               maps: [{ map_id: 's1', cell_count: SRC_CELLS.length,
                        declared_frame: TRUTH, declared_frame_source: 'declared' }] },
    candidates: FRAMES.map(id => ({
      frame: id, state: 'scored', agreement: 10, discriminating: 20,
      shift: { ...SHIFT }, placement: PLACEMENTS.get(id),
    })),
    declaration: { frames: { [TRUTH]: 1 }, attested_maps: 1, unattested_maps: 0, axis_sources: {} },
    ruling: { winner: TRUTH, reason_code: null },
    excluded_total: 0, stats: { scored_cells: SRC_CELLS.length, elapsed_ms: 3 },
    ...(overrides || {}),
  };
}

const payload = adaptPayload(wire());
const source = payload.sources[0];
// The dimensions the OLD rule measured: `gridSpan` over the floor cells.
const DIMS = { cols: Math.max(...FLOOR_CELLS.map(c => c[0])) + 1,
               rows: Math.max(...FLOOR_CELLS.map(c => c[1])) + 1 };

console.log('MAP2 PLACEMENT SEAT HARNESS');
console.log(`fixture: ${SRC_CELLS.length} source dies, ${FLOOR_CELLS.length} floor dies, `
          + `start=(${START_X},${START_Y}), truth=${TRUTH}, shift=(${SHIFT.dx},${SHIFT.dy})`);
console.log(`         x span ${DIMS.cols} (even: ${DIMS.cols % 2 === 0}), `
          + `anchor_src=(${ANCHOR_SRC}), anchor_ref=(${ANCHOR_REF})`);

// ── A. THE SEATS MATCH THE ORACLE, KEY BY KEY ───────────────────────────────────
for (const id of FRAMES) {
  const { seating, reason } = seatingFor(payload, id, source.cells);
  eq(reason, null, `A0 ${id}: a shipped placement is not refused`);
  eq(seating.seatCount, SRC_CELLS.length, `A1 ${id}: every cell is seated`);
  let wrong = 0;
  for (const seat of seating.seats) {
    const want = oracleSeat(PLACEMENTS.get(id), seat.cell.x, seat.cell.y);
    if (seat.x !== want.x || seat.y !== want.y) wrong++;
  }
  eq(wrong, 0, `A2 ${id}: every seat is the seat the server shipped`);
}

// The floor is at its stored coordinates, untouched.
{
  const floor = floorSeating(payload);
  let wrong = 0;
  for (let i = 0; i < FLOOR_CELLS.length; i++) {
    if (floor.seats[i].x !== FLOOR_CELLS[i][0] || floor.seats[i].y !== FLOOR_CELLS[i][1]) wrong++;
  }
  eq(wrong, 0, 'A3 the floor sits at its stored coordinates, which is the space the score used');
  // And the fixture is a real alignment: the truth candidate covers the floor exactly.
  const cmp = compareSeatings(floor, seatingFor(payload, TRUTH, source.cells).seating);
  eq(cmp.agreeCount, SRC_CELLS.length, `A4 ${TRUTH} seats every die on a floor die`);
  eq(cmp.sourceOnlyCount, 0, 'A5 and none of them lands off the floor');
}

// ── B/C. FRONT VERSUS BACK, AND HOW MANY CELLS MOVE ─────────────────────────────
// 🔴 THE NUMBER THAT SAYS THIS FIXTURE IS WORTH ANYTHING. For each candidate, how many drawn
//    cells sit somewhere else under the old rule than under the shipped seat, and by how much
//    on each axis. A total of 0 means the defect axes are dead and the harness must go red.
console.log('\ncandidate      moved/total   dx      dy    (old rule vs shipped seat)');
const moves = new Map();
for (const id of FRAMES) {
  const a = axesOf(id);
  const placement = PLACEMENTS.get(id);
  let moved = 0;
  const dxs = new Set();
  const dys = new Set();
  for (const [x, y] of SRC_CELLS) {
    const old = legacySeat(a, x, y, DIMS, SHIFT);
    const want = oracleSeat(placement, x, y);
    if (old.x !== want.x || old.y !== want.y) moved++;
    dxs.add(old.x - want.x);
    dys.add(old.y - want.y);
  }
  const dx = dxs.size === 1 ? [...dxs][0] : null;   // null = not a translation at all
  const dy = dys.size === 1 ? [...dys][0] : null;
  moves.set(id, { moved, dx, dy });
  console.log(`  ${id.padEnd(12)} ${String(moved).padStart(3)}/${SRC_CELLS.length}`
            + `   ${dx === null ? 'mixed' : String(dx).padStart(5)}`
            + `  ${dy === null ? 'mixed' : String(dy).padStart(5)}`);
}

const totalMoved = [...moves.values()].reduce((s, m) => s + m.moved, 0);
console.log(`\ncells that move across all eight candidates: ${totalMoved} `
          + `of ${SRC_CELLS.length * FRAMES.length}`);
ok(totalMoved > 0, 'C1 the fixture activates the defect at all (0 would mean it proves nothing)');

// B. THE SPLIT THE OPERATOR REPORTED. Front frames whose linear part the old rule happened to
//    reproduce come out at zero error; the back frames do not.
eq(moves.get('rot0_front').moved, 0,
   'B1 rot0_front: the old rule and the shipped seat agree -- this is why the front looked fine');
ok(moves.get('rot0_back').moved > 0,
   'B2 rot0_back: the old rule is displaced -- this is what the operator sees on the back');
// 🔴 THE ASSERTION THAT WOULD HAVE CAUGHT THIS. Front error zero and back error non-zero, in the
//    SAME run, on the SAME fixture. A harness that only exercised the front would have been
//    green throughout the whole incident.
ok(moves.get('rot0_front').moved === 0 && moves.get('rot0_back').moved > 0,
   'B3 front and back are separated, and only the back moves');
// Both axes, because the operator corrected the report to say so.
const movedX = [...moves.values()].filter(m => m.dx !== 0).length;
const movedY = [...moves.values()].filter(m => m.dy !== 0).length;
console.log(`candidates displaced on x: ${movedX} of 8; on y: ${movedY} of 8`);
ok(movedX > 0, 'B4 the x axis is displaced on at least one candidate');
ok(movedY > 0, 'B5 the y axis is displaced too -- the report is not x-only');
// The quarter turns are where `grid_y_invert` inverts the mirror set, so the old rule is not
// even a translation there: it is a different linear map.
ok(moves.get(TRUTH).dx === null || moves.get(TRUTH).dy === null || moves.get(TRUTH).moved > 0,
   `B6 ${TRUTH} (the winner) is wrong under the old rule -- a perfect score drew displaced`);

// ── D. NO DOUBLE APPLICATION ────────────────────────────────────────────────────
// `anchor_ref` already contains the solved shift. The guard is structural: the seating function
// takes no shift, so a caller cannot add it a second time.
eq(placeCells.length, 2, 'D1 placeCells takes (cells, placement) and no shift argument');
{
  // And the seat it produces is the one-application seat, not the two-application one.
  const seat = seatingFor(payload, TRUTH, [{ x: ANCHOR_SRC[0], y: ANCHOR_SRC[1] }]).seating.seats[0];
  eq(seat.x, ANCHOR_REF[0], 'D2 the anchor die seats at anchor_ref exactly, on x');
  eq(seat.y, ANCHOR_REF[1], 'D3 the anchor die seats at anchor_ref exactly, on y');
  ok(seat.x !== ANCHOR_REF[0] + SHIFT.dx,
     'D4 and not at anchor_ref plus the shift again (the 4947a65 defect, mirrored)');
}

// ── E. ABSENT IS NOT THE IDENTITY ───────────────────────────────────────────────
{
  const noPlace = adaptPayload(wire({
    candidates: FRAMES.map(id => ({ frame: id, state: 'scored', agreement: 10,
                                    discriminating: 20, shift: { ...SHIFT } })),
  }));
  const { seating, reason } = seatingFor(noPlace, TRUTH, noPlace.sources[0].cells);
  eq(seating, null, 'E1 no placement on the wire seats nothing at all');
  eq(reason, '배치 없음', 'E2 and the absence has a name the screen can print');
}
{
  // A malformed placement is a placement we cannot read. Same outcome, not a coerced one.
  const bad = adaptPayload(wire({
    candidates: FRAMES.map(id => ({ frame: id, state: 'scored', agreement: 10,
      discriminating: 20, placement: { linear: [[2, 0], [0, 1]], anchor_src: ANCHOR_SRC,
                                       anchor_ref: ANCHOR_REF } })),
  }));
  eq(seatingFor(bad, TRUTH, bad.sources[0].cells).seating, null,
     'E3 a linear part with |det| != 1 is refused, not used to spread the map');
}

// ── F. NO ORIGIN AND NO BOX ARE READ ────────────────────────────────────────────
// 🔴 THE OWNER'S QUESTION, ANSWERED AS A MEASUREMENT. 「화면 틀어지는 게 오히려 유효다이 고유
//    start x,y 좌표 때문인 거 같은데」. The scorer applies no origin -- placement is a difference
//    from the anchor, in which start and box.minC cancel identically -- so the screen must apply
//    none either. Varied over the payload, the drawn seats must not move by one cell.
{
  const before = seatingFor(payload, TRUTH, source.cells).seating.seats.map(s => s.key).join(' ');
  const noisy = adaptPayload(wire({
    start_x: 7, start_y: -4, grid_start_x: 7, grid_start_y: -4,
    dims: { cols: 999, rows: 999 }, grid_y_invert: true,
    phys: { chip_x: 11.0, chip_y: 3.5, wafer_dia: 300, edge_margin: 20,
            offset_x: 4.25, offset_y: -1.75 },
  }));
  const after = seatingFor(noisy, TRUTH, noisy.sources[0].cells).seating.seats.map(s => s.key).join(' ');
  eq(after, before, 'F1 no start, no dims and no physical parameter moves a single drawn cell');
}

// ── SUMMARY ─────────────────────────────────────────────────────────────────────
console.log('');
for (const f of failures) console.log(`  FAIL ${f}`);
console.log(`ASSERTIONS ${compared} ${failures.length}`);
if (failures.length > 0) process.exitCode = 1;
