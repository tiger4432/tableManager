/**
 * MAP EDITOR 2 -- THE RANK PICTURE: WHAT IT PAINTS, WHAT IT REFUSES TO PAINT, AND WHY IT
 * CANNOT BE SIMPLIFIED BACK INTO A GRADIENT.
 *
 * THIS HARNESS DOES NOT SLICE SOURCE. It `import`s every module it scores.
 *
 * 🔴 IT ASSERTS THE DRAWING, NOT THE PLUMBING. A test that checks the rank ARRIVED passes a
 *    version that receives it and paints every die one colour. So the assertions are on the
 *    fill strings `drawSeats` writes, scored by an INDEPENDENT colour oracle
 *    (`oracle/colour_difference_oracle.mjs`) that knows nothing about periods or bands.
 *
 * WHAT IS SCORED
 *   A. THE FILLS -- adjacent ranks are adjacent colours, a jump of ten is obviously not, at
 *      every real cell count (88, 266, 512, 1313 -- the reference floors this database holds).
 *   B. THE ANTI-GRADIENT MUTATION -- a monotone ramp is RUN and must FAIL section A at
 *      N >= 512. This is the assertion that stops someone "simplifying" the cyclic hue away:
 *      a gradient's local contrast is inversely proportional to N and dies on real wafers.
 *   C. BOTH THEMES -- minimum WCAG contrast against `--bg-inset` and against the composited
 *      floor wash, on LIGHT as well as dark. Light is the default and is the one that fails.
 *   D. 🔴 THE NEGATIVE CONTROL. The eight candidates are ISOMETRIES of the stored lattice, so
 *      every adjacency-based reading is blind to the frame -- asserted, because the first
 *      oracle written for this feature scored ONE value for all eight and nothing else noticed.
 *      What discriminates is orientation, and it must separate 8 of 8. If that count is ever 1,
 *      the fixture is proving nothing and this file must go red rather than green.
 *   E. THE TWO NULLS -- an element null (this die carries no number) and a whole-field null
 *      (the pool was clipped) are different facts with different outcomes.
 *   F. PRECEDENCE -- a clipped pool refuses AS clipped, ahead of whatever the clipping broke.
 *   G. NO RENORMALISATION -- ranks arrive normalised per map and are used verbatim, gaps and all.
 *   H. THE RANK RIDES ON THE CELL -- a dropped coordinate may not shift the numbering.
 *   I. ABSENT IS NOT A GREYED CONTROL.
 *
 * CONSOLE OUTPUT IS ASCII ONLY (cp949-safe): no emoji, no em-dash.
 */

import { indexColor, rampStops, rampGradientCss,
         INDEX_RAMP_PERIOD, INDEX_RAMP_CHROMA,
         INDEX_RAMP_BAND_FALLBACK } from '../src/map2/index_ramp.js';
import { decodeIndexWalk, decodeReferenceView,
         INDEX_WALK_READY, INDEX_WALK_ABSENT, INDEX_WALK_TRUNCATED,
         INDEX_WALK_POOLED, INDEX_WALK_INCONSISTENT } from '../src/map2/decode.js';
import { adaptPayload } from '../src/map2/main.js';
import { computeSeating, boundingBoxOf } from '../src/map2/seating.js';
import { deltaE00, contrastRatio, over } from './oracle/colour_difference_oracle.mjs';

let compared = 0;
const failures = [];
function ok(cond, what) { compared++; if (!cond) failures.push(what); }
function eq(actual, expected, what) {
  compared++;
  if (actual !== expected) {
    failures.push(`${what}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

// The two bands as `tokens.css` declares them. Restated here because a harness that read the
// stylesheet would pass whatever the stylesheet said, including a regression.
const LIGHT = { l0: 0.46, l1: 0.58 };
const DARK = { l0: 0.66, l1: 0.78 };
const BG_LIGHT = '#f3f5f8';
const BG_DARK = '#141c2c';
const FLOOR_LIGHT = over('#177245', 0.06, BG_LIGHT);
const FLOOR_DARK = over('#33d68f', 0.08, BG_DARK);

// The cell counts this database actually holds: PRD-A/DT13 88, TEST/TEST 425, 5N/BASE 425,
// CORE/1X 854, CORE/YINV 927, and a 1313-cell floor. Pinned as MEMBERS, not as a count.
const REAL_SIZES = [88, 266, 512, 1313];

const ADJACENT_MAX = 6;   // dE00: "adjacent ranks are adjacent colours"
const JUMP_MIN = 15;      // dE00: "a jump of ten looks different from a jump of one"

// ── A. the fills ────────────────────────────────────────────────────────────────
{
  for (const band of [LIGHT, DARK]) {
    const which = band === LIGHT ? 'light' : 'dark';
    for (const n of REAL_SIZES) {
      let worstAdjacent = 0, weakestJump = Infinity;
      for (let k = 1; k + 10 <= n; k++) {
        worstAdjacent = Math.max(worstAdjacent,
          deltaE00(indexColor(k, n, band), indexColor(k + 1, n, band)));
        weakestJump = Math.min(weakestJump,
          deltaE00(indexColor(k, n, band), indexColor(k + 10, n, band)));
      }
      ok(worstAdjacent < ADJACENT_MAX,
        `A1 ${which} N=${n}: adjacent ranks stay adjacent colours `
        + `(worst dE00 ${worstAdjacent.toFixed(2)} must be < ${ADJACENT_MAX})`);
      ok(weakestJump > JUMP_MIN,
        `A2 ${which} N=${n}: a jump of ten is visible `
        + `(weakest dE00 ${weakestJump.toFixed(2)} must be > ${JUMP_MIN})`);
    }
  }
  // The two ends are the scale the legend prints. They must not be the same colour.
  ok(deltaE00(indexColor(1, 266, LIGHT), indexColor(266, 266, LIGHT)) > 20,
    'A3 the ends of the ramp are plainly different colours');
  // What the prime period buys: ranks 64 apart are NOT a collision. At P=64 this measured 0.6.
  ok(deltaE00(indexColor(1, 1313, LIGHT), indexColor(65, 1313, LIGHT)) > 8,
    'A4 the near-wrap does not collide (a period sharing factors with a row width would)');
  // A die with no number has no colour. Never a substituted one.
  eq(indexColor(null, 266, LIGHT), null, 'A5 an unnumbered die gets null, not a colour');
  eq(indexColor(0, 266, LIGHT), null, 'A6 rank 0 is not a rank -- Number(null) must not paint');
  eq(indexColor(1.5, 266, LIGHT), null, 'A7 a non-integer rank is refused rather than rounded');
  // The legend bar is built FROM the ramp, so it cannot drift from the cells.
  const stops = rampStops(266, LIGHT);
  eq(stops[0].color, indexColor(1, 266, LIGHT), 'A8 the bar starts at the colour rank 1 is painted');
  eq(stops[stops.length - 1].color, indexColor(266, 266, LIGHT),
    'A9 and ends at the colour the largest rank is painted');
  ok(rampGradientCss(266, LIGHT).startsWith('linear-gradient(90deg, #'),
    'A10 the bar ships as one gradient value, not as a stylesheet literal');
}

// ── B. the anti-gradient mutation ───────────────────────────────────────────────
// A monotone ramp: hue sweeps ONCE across the whole range. This is the "simplification"
// somebody will reach for. It is RUN, and it must fail section A on real wafers.
function monotoneColor(rank, rankMax, band) {
  if (!Number.isInteger(rank) || rank < 1) return null;
  const t = (rank - 1) / Math.max(1, rankMax - 1);
  const L = band.l0 + (band.l1 - band.l0) * t;
  const H = 250 + t * 300;
  return oklchHex(L, INDEX_RAMP_CHROMA, H);
}
{
  const weakest = n => {
    let w = Infinity;
    for (let k = 1; k + 10 <= n; k++) {
      w = Math.min(w, deltaE00(monotoneColor(k, n, LIGHT), monotoneColor(k + 10, n, LIGHT)));
    }
    return w;
  };
  ok(weakest(512) < JUMP_MIN,
    `B1 a monotone ramp FAILS the jump-of-ten rule at N=512 (${weakest(512).toFixed(2)}) `
    + '-- if this ever passes, the cyclic period has been removed and nothing else would say so');
  ok(weakest(1313) < JUMP_MIN,
    `B2 and at N=1313 (${weakest(1313).toFixed(2)}), which is a real reference floor here`);
  // ... and the mutation is only meaningful because the shipped ramp passes the same test.
  let shipped = Infinity;
  for (let k = 1; k + 10 <= 1313; k++) {
    shipped = Math.min(shipped, deltaE00(indexColor(k, 1313, LIGHT), indexColor(k + 10, 1313, LIGHT)));
  }
  ok(shipped > JUMP_MIN,
    `B3 CONTROL: the shipped ramp passes at N=1313 (${shipped.toFixed(2)}) where the monotone `
    + 'one fails -- without this the mutation would only prove the threshold is unreachable');
}

// ── C. both themes ──────────────────────────────────────────────────────────────
{
  const minContrast = (band, bg, n) => {
    let m = Infinity;
    for (let k = 1; k <= n; k++) m = Math.min(m, contrastRatio(indexColor(k, n, band), bg));
    return m;
  };
  for (const n of REAL_SIZES) {
    ok(minContrast(LIGHT, BG_LIGHT, n) >= 3,
      `C1 N=${n}: LIGHT theme clears 3:1 against --bg-inset at every rank `
      + `(${minContrast(LIGHT, BG_LIGHT, n).toFixed(2)})`);
    ok(minContrast(DARK, BG_DARK, n) >= 3,
      `C2 N=${n}: DARK theme clears 3:1 against --bg-inset at every rank `
      + `(${minContrast(DARK, BG_DARK, n).toFixed(2)})`);
  }
  ok(minContrast(LIGHT, FLOOR_LIGHT, 266) >= 3,
    'C3 and against the composited floor wash on light, which is what the ramp sits on');
  ok(minContrast(DARK, FLOOR_DARK, 266) >= 3, 'C4 same on dark');
  // The fallback is the LIGHT band: a failure to resolve tokens must degrade toward the theme
  // that was measured hardest, not toward the one that only works on dark.
  eq(INDEX_RAMP_BAND_FALLBACK.l0, LIGHT.l0, 'C5 the no-token fallback is the light band');
  ok(minContrast(DARK, BG_LIGHT, 266) < 3,
    'C6 CONTROL: the dark band really does fail on the light background, so C1 is not vacuous');
}

// ── D. the negative control: what this picture can and cannot discriminate ──────
const BASE = {
  cols: 23, rows: 19, startX: 0, startY: 0, invertY: true,
  physWaferDia: 150, physChipX: 8.7, physChipY: 5.3,
  physEdgeMargin: 3, physOffsetX: 1.7, physOffsetY: -2.1,
};
const FRAMES = [];
for (const rotation of [0, 90, 180, 270]) for (const side of ['front', 'back']) {
  FRAMES.push({ id: `rot${rotation}_${side}`, rotation, side });
}
const frameOf = f => Object.assign({}, BASE, { rotation: f.rotation, side: f.side });

function serpentineRank(points) {
  const byRow = new Map();
  for (const p of points) {
    if (!byRow.has(p.y)) byRow.set(p.y, []);
    byRow.get(p.y).push(p.x);
  }
  const rows = [...byRow.keys()].sort((a, b) => a - b);
  const rank = new Map();
  let i = 1;
  rows.forEach((y, ri) => {
    const xs = [...new Set(byRow.get(y))].sort((a, b) => (ri % 2 === 1 ? b - a : a - b));
    for (const x of xs) rank.set(`${x},${y}`, i++);
  });
  return rank;
}
{
  const TRUTH = FRAMES.find(f => f.id === 'rot90_back');
  const tf = frameOf(TRUTH);
  const tbox = boundingBoxOf(tf);
  ok(!!tbox, 'D0 the fixture declares real geometry -- with no box it would prove nothing');
  // 🔴 THE FIXTURE'S DEFECT AXES ARE LIVE: anisotropic chip (a pitch swap can show), nonzero
  //    offsets (a bbox term can show), a quarter turn AND the back side, and invertY on.
  ok(BASE.physChipX !== BASE.physChipY, 'D0b anisotropic chip: the pitch-swap axis is live');
  ok(tbox.minC !== 0 || tbox.minR !== 0, 'D0c the bounding box is off the origin: the bbox term is live');

  const stored = [];
  for (let r = tbox.minR; r <= tbox.maxR; r++) {
    for (let c = tbox.minC; c <= tbox.maxC; c++) {
      stored.push({
        x: c - tbox.minC + tf.startX,
        y: tf.invertY ? (tbox.maxR - r) + tf.startY : r - tbox.minR + tf.startY,
      });
    }
  }
  const truthSeating = computeSeating(stored, tf, null);
  const rankAt = serpentineRank(truthSeating.seats.map(s => ({ x: s.x, y: s.y })));
  const rankOfCell = truthSeating.seats.map(s => rankAt.get(s.key));
  // A PARTIAL job -- the first 55% of the walk, which is how a DT lot actually arrives.
  const M = Math.round(stored.length * 0.55);
  const jobCells = [], jobRanks = [];
  stored.forEach((cell, i) => {
    if (rankOfCell[i] <= M) { jobCells.push(cell); jobRanks.push(rankOfCell[i]); }
  });

  const neighbour = new Set();
  const signatures = new Set();
  let truthSignature = null;
  for (const f of FRAMES) {
    const seating = computeSeating(jobCells, frameOf(f), null);
    const rankByKey = new Map();
    const seatByRank = new Map();
    seating.seats.forEach((s, i) => { rankByKey.set(s.key, jobRanks[i]); seatByRank.set(jobRanks[i], s); });

    const ds = [];
    for (const s of seating.seats) {
      for (const [dx, dy] of [[1, 0], [0, 1]]) {
        const nk = `${s.x + dx},${s.y + dy}`;
        if (!rankByKey.has(nk)) continue;
        ds.push(deltaE00(indexColor(rankByKey.get(s.key), M, LIGHT),
                         indexColor(rankByKey.get(nk), M, LIGHT)));
      }
    }
    ds.sort((a, b) => a - b);
    neighbour.add(ds[ds.length >> 1].toFixed(2));

    const b = seating.bounds;
    const first = seatByRank.get(1);
    const corner = `${first.y - b.minY <= b.maxY - first.y ? 'top' : 'bottom'}-`
                 + `${first.x - b.minX <= b.maxX - first.x ? 'left' : 'right'}`;
    let horiz = 0, vert = 0;
    for (let k = 1; k < M; k++) {
      const a = seatByRank.get(k), c = seatByRank.get(k + 1);
      if (!a || !c) continue;
      if (a.y === c.y && Math.abs(a.x - c.x) === 1) horiz++;
      else if (a.x === c.x && Math.abs(a.y - c.y) === 1) vert++;
    }
    const sig = `${corner}|${horiz >= vert ? 'rows' : 'cols'}`;
    signatures.add(sig);
    if (f.id === TRUTH.id) truthSignature = sig;
  }

  // 🔴 THE ASSERTION THAT SAVED THIS FEATURE FROM SHIPPING A DECORATION.
  eq(signatures.size, 8,
    'D1 the rank picture separates all eight candidates by ORIENTATION -- if this is ever 1, '
    + 'the fixture discriminates nothing and every other assertion here is vacuous');
  eq(truthSignature, 'top-left|rows',
    'D2 the correct frame is the unique one reading "rank 1 top-left, walk runs in rows" '
    + '-- which is exactly the sentence the legend prints');
  // And the blindness, asserted rather than believed: this is WHY the legend says what it says.
  eq(neighbour.size, 1,
    'D3 every adjacency-based reading is BLIND to the frame (the eight are isometries of the '
    + 'stored lattice). A later round must not read a local break as a frame fault');
}

// ── E/F/G/H/I. the wire, decoded ────────────────────────────────────────────────
function wire(patch) {
  const p = {
    state: 'scored',
    reference: { state: 'resolved', kind: 'occupancy', cells: [[0, 0]] },
    sources: {
      map_count: 1, cell_count: 4,
      cells: [[0, 0], [1, 0], [2, 0], [3, 0]],
      cell_index: [1, 2, null, 3],
      cell_map: [0, 0, 0, 0],
      truncated: false,
      maps: [{ map_id: 'M1', cell_count: 4 }],
    },
    candidates: [],
    ruling: { winner: null, index_axis: 'ranking' },
    stats: { source_indices_usable: 3 },
  };
  if (patch && patch.sources) p.sources = Object.assign({}, p.sources, patch.sources);
  if (patch && patch.ruling) p.ruling = Object.assign({}, p.ruling, patch.ruling);
  if (patch && patch.stats) p.stats = Object.assign({}, p.stats, patch.stats);
  return p;
}
const walkOf = patch => decodeIndexWalk(wire(patch), []);

{
  // E. the two nulls
  const ready = walkOf();
  eq(ready.state, INDEX_WALK_READY, 'E1 an element null does not stop the walk');
  eq(ready.ranks[2], null, 'E2 the unnumbered die keeps null -- it is IN the walk with no colour');
  eq(indexColor(ready.ranks[2], ready.rankMax, LIGHT), null, 'E3 and paints as an absence');
  eq(ready.rankMax, 3, 'E4 the ramp domain is the largest rank');

  const clipped = walkOf({ sources: { cell_index: null, truncated: true } });
  eq(clipped.state, INDEX_WALK_TRUNCATED,
    'E5 a WHOLE-FIELD null is a clipped pool, which is not a walk');
  eq(clipped.ranks.length, 0, 'E6 and it hands over no ranks at all, so nothing can paint it');
  ok(clipped.state !== ready.state,
    'E7 CONTROL: the two nulls reach different states -- folding them is the defect');

  // F. precedence: clipped refuses AS clipped, ahead of what the clipping broke
  const clippedAndPooled = walkOf({
    sources: { cell_index: null, truncated: true, cell_map: [0, 0, 1, 1] },
  });
  eq(clippedAndPooled.state, INDEX_WALK_TRUNCATED,
    'F1 a clipped pool refuses as clipped even when it is also pooled');
  const lying = walkOf({ sources: { cell_index: null, truncated: false } });
  eq(lying.state, INDEX_WALK_INCONSISTENT,
    'F2 whole-field null with truncated:false is the wire contradicting itself, named as such');

  eq(walkOf({ sources: { cell_map: [0, 0, 1, 1] } }).state, INDEX_WALK_POOLED,
    'F3 two maps in one array are two walks and one ramp over both is refused');
  eq(walkOf({ sources: { cell_index: [1, 2] } }).state, INDEX_WALK_INCONSISTENT,
    'F4 a short cell_index is refused rather than silently trimmed');
  eq(walkOf({ sources: { cell_map: [0, 0] } }).state, INDEX_WALK_INCONSISTENT,
    'F5 a short cell_map is refused too -- ownership is unconditional');
  eq(walkOf({ sources: { cell_index: [1, 2, 0, 3] } }).state, INDEX_WALK_INCONSISTENT,
    'F6 rank 0 is not a rank; a payload carrying one is refused, never painted as rank 1');

  // I. absent is not a greyed control
  eq(walkOf({ ruling: { index_axis: 'absent' } }).state, INDEX_WALK_ABSENT,
    'I1 the server saying `absent` means there is nothing to offer');
  const notServed = decodeIndexWalk({
    sources: { cells: [[0, 0]], maps: [] }, ruling: { index_axis: 'ranking' }, stats: {},
  }, []);
  eq(notServed.state, INDEX_WALK_ABSENT, 'I2 a server that ships no field at all is unpaintable');
  eq(notServed.reason, 'field_not_served',
    'I3 and it is NAMED apart from `absent` -- "nobody numbered these" and "this build does '
    + 'not serve numbers" are different repairs');
  eq(walkOf({ sources: { cell_index: [null, null, null, null] } }).state, INDEX_WALK_ABSENT,
    'I4 every element null is an absence, not an empty ramp');

  // 🔴 A CONTRADICTING PAYLOAD IS AUDIBLE; AN ORDINARY ABSENCE IS NOT. `rejected` reaches the
  //    operator as `payload fields refused: ...`, and a warning that fires on honest payloads
  //    is one nobody reads by the end of the week. This was measured going wrong: an older
  //    server that simply does not serve the field printed a refusal on a screen where nothing
  //    was wrong, and three shell harnesses caught it in their diagnostics.
  const rejBad = [];
  decodeIndexWalk(wire({ sources: { cell_index: [1, 2] } }), rejBad);
  ok(rejBad.some(r => /cell_index/.test(r)),
    'I5 a SELF-CONTRADICTING payload names itself in the decoder rejects');
  for (const [label, patch] of [
    ['a server that does not serve the field', { sources: { cell_index: undefined } }],
    ['a clipped pool', { sources: { cell_index: null, truncated: true } }],
    ['a multi-map unit', { sources: { cell_map: [0, 0, 1, 1] } }],
    ['a unit nobody numbered', { ruling: { index_axis: 'absent' } }],
  ]) {
    const rej = [];
    decodeIndexWalk(wire(patch), rej);
    eq(rej.length, 0, `I6 ${label} is not a refused field and must not print as one`);
  }
}

{
  // G. no renormalisation -- the coordinator's own example, verbatim
  const p = wire({
    sources: {
      cells: [[0, 0], [1, 0], [2, 0], [3, 0], [4, 0], [5, 0]],
      cell_index: [1, 2, null, 3, 1, 2],
      cell_map: [0, 0, 0, 0, 1, 1],
      cell_count: 6,
    },
  });
  eq(decodeIndexWalk(p, []).state, INDEX_WALK_POOLED,
    'G1 that example is TWO maps, so it is refused before any ramp sees it');

  // The single-map half of it: ranks are carried through untouched, gaps included.
  const sparse = walkOf({
    sources: { cell_index: [1, 4, null, 9] },
    stats: { source_indices_usable: 3 },
  });
  eq(sparse.state, INDEX_WALK_READY, 'G2 a SPARSE numbering is a valid walk');
  eq(JSON.stringify(sparse.ranks), JSON.stringify([1, 4, null, 9]),
    'G3 ranks are used VERBATIM -- not shifted, not re-ranked, not densified');
  eq(sparse.rankMax, 9,
    'G4 the ramp domain is the largest rank (9), NOT the count of numbered dies (3) -- the '
    + 'server shift is min->1 rather than a dense re-rank, so those are different numbers');
  eq(sparse.numbered, 3,
    'G5 and the coverage tally stays the server\'s own, so the legend can say both');
  ok(sparse.rankMax !== sparse.numbered,
    'G6 CONTROL: this fixture actually separates the two numbers, so G4/G5 are not vacuous');
}

{
  // H. the rank rides on the cell -- a dropped coordinate may not shift the numbering
  const raw = wire({
    sources: {
      cells: [[0, 0], ['nope', 0], [2, 0], [3, 0]],
      cell_index: [1, 2, 3, 4],
      cell_map: [0, 0, 0, 0],
    },
  });
  const adapted = adaptPayload(raw);
  const cells = adapted.sources[0].cells;
  eq(cells.length, 3, 'H1 the unreadable coordinate is dropped, as it always was');
  eq(JSON.stringify(cells.map(c => [c.x, c.rank])), JSON.stringify([[0, 1], [2, 3], [3, 4]]),
    'H2 and every surviving die keeps ITS OWN rank -- a parallel array would have shifted '
    + 'rank 3 onto x=2 and rank 4 onto x=3 while the picture still looked like a wafer');
  // ... and the rank survives seating, which is the road the painter reads it off.
  const seating = computeSeating(cells, Object.assign({}, BASE, { rotation: 0, side: 'front' }), null);
  eq(seating.seats[1].cell.rank, 3, 'H3 the rank arrives on the seat, so the painter reads it');
  eq(adapted.index_walk.state, INDEX_WALK_READY, 'H4 and the walk state travels with it');

  // A refused walk hands over no ranks, all the way through the adapter.
  const refusedAdapted = adaptPayload(wire({ sources: { cell_index: null, truncated: true } }));
  eq(refusedAdapted.index_walk.state, INDEX_WALK_TRUNCATED, 'H5 a clipped pool stays clipped');
  ok(refusedAdapted.sources[0].cells.every(c => c.rank === null),
    'H6 and not one cell carries a rank, so a checked box cannot paint a partial walk');

  // The decoder's own record carries the walk, so nothing downstream re-inspects the wire.
  eq(decodeReferenceView(raw).indexWalk.state, INDEX_WALK_READY,
    'H7 the walk is decoded at the customs post, once');
}

// A small guard on the module's own constants: the harness scores behaviour, but the period
// being a fraction of a typical row width would be a silent regression nothing else sees.
ok(INDEX_RAMP_PERIOD > 32 && INDEX_RAMP_PERIOD % 2 === 1,
  'Z1 the hue period is odd and long enough not to alias with a wafer row width');
ok(INDEX_RAMP_CHROMA > 0 && INDEX_RAMP_CHROMA < 0.4, 'Z2 chroma is a sane OKLCH chroma');

console.log(`ASSERTIONS ${compared} ${failures.length}`);
if (failures.length > 0) {
  console.log('\nFAILURES');
  for (const f of failures) console.log(`  - ${f}`);
}
process.exit(failures.length === 0 ? 0 : 1);

// ────────────────────────────────────────────────────────────────────────────────
// A local OKLCH -> hex, used ONLY by the monotone mutant in section B. Deliberately not
// imported from `index_ramp.js`: the mutant has to be able to survive that module being wrong.
function oklchHex(L, C, Hdeg) {
  const h = (Hdeg * Math.PI) / 180;
  const a = C * Math.cos(h), b = C * Math.sin(h);
  const toLinear = (cc) => {
    const l_ = L + 0.3963377774 * a + 0.2158037573 * b;
    const m_ = L - 0.1055613458 * a - 0.0638541728 * b;
    const s_ = L - 0.0894841775 * a - 1.2914855480 * b;
    const l = l_ ** 3, m = m_ ** 3, s = s_ ** 3;
    return [
      4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
      -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
      -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
    ][cc];
  };
  const bytes = [0, 1, 2].map(i => {
    const c = Math.max(0, Math.min(1, toLinear(i)));
    const srgb = c <= 0.0031308 ? c * 12.92 : 1.055 * Math.pow(c, 1 / 2.4) - 0.055;
    return Math.round(Math.max(0, Math.min(1, srgb)) * 255).toString(16).padStart(2, '0');
  });
  return `#${bytes.join('')}`;
}
