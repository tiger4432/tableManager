// ═══════════════════════════════════════════════════════════════════════════════
// ORACLE -- AN INDEPENDENT EXPECTATION SET FOR LAYER (5) SCORING. NOT SHIPPING CODE.
//
// 🔴 THIS IS NOT THE CLIENT'S SCORER AND MUST NOT BECOME ONE. Ruling 2026-08-05: THE SERVER
//    SCORES. The candidate transform is the most subtle code in this system -- `map_overlay.
//    _frame_phys_params` flips offset signs per rotation and side, the mirrors cancel, and a
//    bounding box computed once instead of once per candidate misplaces the production row
//    `CORE_YINV` by (2,-1) -- so a JS re-spelling of it would be the second spelling of the
//    one function whose subtlety has already refuted two lead-PM claims in 24 hours. The
//    server also already holds the cells.
//
//    This file lives in `client2/tests/oracle/` on purpose -- a SUBDIRECTORY, because
//    `check_harnesses.mjs` discovers every `*.mjs` directly under `client2/tests/` and would
//    otherwise run this library as a harness, find no ASSERTIONS line, and block the build. Nothing under `client2/src/` imports it
//    and nothing may. Its output is DATA: the expectation set a contract-keeper lane can
//    score the server's scorer against, derived independently of it.
//
// WHAT AN ORACLE IS ALLOWED TO BE WEAKER AT, stated so nobody mistakes it for the real thing:
// its geometry is layer 4's `seatOf`, which is a faithful transcription of `cell_to_physical`
// but omits the two further terms production's `visual_to_cell` carries -- the bounding-box
// origin and the y-inversion. The bbox term is a per-candidate CONSTANT and is therefore
// absorbed by the shift solved below, so COUNTS, RANKING and MARGINS are unaffected and are
// what this oracle pins. The y-inversion is a REFLECTION and is not absorbed, so absolute
// `startX`/`startY` outputs are NOT pinned by this oracle on a map declaring inversion.
// `probeInvertY` measures which of the two situations a run is in rather than assuming.
//
// ── WHAT IS REUSED RATHER THAN RESPELLED ───────────────────────────────────────
//
// The eight candidates come from `../src/map2/candidates.js` (`candidateList`) and the
// transform from `../src/map2/seating.js` (`computeSeating`). Neither is re-derived here. A
// second enumeration or a second transform is defect class I6 -- "the second spelling of the
// same question always diverges" -- which this repository paid for three times in one day.
//
// ── FOUR CONSTRAINTS, EACH THE REASON FOR ITSELF ───────────────────────────────
//
// C1. EIGHT CANDIDATES, AND EACH IS SEATED AS A WHOLE FRAME. `candidateFrames` clones the
//     target's frame and overrides rotation/side, then hands the WHOLE frame to the seater.
//     It never seats once and composes transforms on top. That is not tidiness: in the
//     production path `map_overlay._frame_phys_params` flips the OFFSET SIGNS per
//     rotation/side and `PhysicalWaferEngine.get_cell_physical_mm` is odd in those arguments,
//     so a candidate's bounding box is MIRRORED rather than shared. Compose on one shared box
//     and the production row `CORE_YINV` lands (2,-1) out with nothing on screen to show for
//     it (spec section 2; fixture `server/tests/test_grid_y_invert_aliasing.py`).
//
//     `grid_y_invert` is deliberately NOT a candidate axis; it is carried through from the
//     target's own declaration. The licence for that WAS a measurement, not the spec sentence:
//     the harness enumerates all 16 (rotation x side x invert) tuples through the production
//     path and checks that the 8 emitted candidates realise every one of them UP TO A
//     TRANSLATION -- and translation is exactly what C2 solves.
//
// 🔴 THAT LICENCE IS WITHDRAWN, BY THE SAME MEASUREMENT. Measured 2026-09-03: the eight
//    candidates realise 8 of the 16, not 16, and the eight they miss are one whole Y parity
//    class -- rot{0,90,180,270}_front_inv«true» and rot{0,90,180,270}_back_inv«false». When
//    `side: back` left the candidate set on 2026-08-08 and the walk start corner took its
//    place, the front candidates kept covering (front,invF) and (back,invT) and nothing was
//    left to cover the other two. The sentence above stayed; the property it asserted did not.
//
// ⚠️ THE CONSEQUENCE IS NOT ONLY ABOUT `grid_y_invert`. The recovery fixture
//    `core_defect_map LOT-A/05` has `targetMetaTruth` rotation 270 / side back / invert false
//    -- which is IN the uncovered eight. So its recorded `truthCandidateId: 'rot90_tr'` names
//    a candidate that cannot reproduce it, and no repair to this file makes that fixture
//    green: a mirrored frame is not expressible in the current candidate space.
//    The start corner is NOT a mirror. On the server it moves the anchor and only in INDEX
//    mode (`map_alignment.py` ~3392: `_base = (_rf - _sf) if index_mode else (0, 0)`), so on a
//    coordinate-identified map `tl` and `tr` are twins there too, deliberately.
//    Open ruling, put to the Lead 2026-09-03: whether the candidate space must regain a way to
//    express a mirrored frame, or those fixtures state an unreachable truth and retire.
//
// C2. `start` IS SOLVED, NOT SEARCHED. Per candidate, the integer shift maximising agreement
//     is computed exactly: every offset with non-zero agreement is voted for by at least one
//     matching pair, so scanning the votes is a complete search of the offsets that could win
//     rather than a heuristic.
//
//     Turning that shift back into a `grid_start_x/y` correction needs d(seat)/d(start),
//     whose SIGN FLIPS PER TUPLE -- the old sentence `phys(start) = phys(0) + (-sx,-sy)`
//     holds for 4 of 16 (spec section 2.1). This module does not transcribe that table. It
//     PROBES the seater for it (`measureStartJacobian`), the same anti-drift device as
//     `declaration.noEvidenceValue`: ask the reader what it does instead of keeping a second
//     copy of the answer, which would drift the first time a default moved.
//
// C3. NO PERCENTAGES, EVER. Not as a field, not as a tiebreak, not as a sort key. Measured:
//     a coverage percentage INVERTS the ranking -- a correctly oriented but one-cell-offset
//     candidate scored 94% and came 4th behind three wrongly oriented ones (spec section 3).
//     `일치 512 / 판별 528` and `일치 38 / 판별 40` are the same percentage and are not the
//     same evidence: the second says there are 40 dies of evidence in the world, which is the
//     most decision-relevant fact available and the one a ratio destroys.
//
//     Enforced at runtime, not only in a test: every number leaving this module must be an
//     integer, checked before the result is returned. A ratio of two counts is almost never
//     an integer, so a percentage that sneaks back in as a field dies on the first call
//     rather than on the first wrong decision.
//
// C4. N-ARY, NOT PAIRWISE. N defect sources are seated onto ONE common frame: N seatings, not
//     N(N-1)/2 pairs, and therefore not N(N-1)/2 chances to disagree about what the common
//     frame is. `scoreSources` takes an array from the start; `scoreSource` is the same code
//     path for the single-source caller.
//
// ── WHAT REFUSES ───────────────────────────────────────────────────────────────
//
// A TRUNCATED layer refuses to be scored (spec section 3 rule 5, `OVERLAY_CELL_LIMIT`). A
// score over a truncated set is a confident number drawn from an incomplete population, which
// is worse than no number. `{ truncated: true }` produces a refusal, not a low score.
//
// NO DOM. NO FETCH. NO MODULE-LEVEL MUTABLE STATE. NO IMPORT OF `../config.js` (it reads
// `window.location.port` and `import.meta.env`, so importing it would make this module
// un-importable from node, which is the whole point). Caps and thresholds arrive in `config`.
// ═══════════════════════════════════════════════════════════════════════════════

import { candidateList, candidateId } from '../../src/map2/candidates.js';
import { computeSeating, seatKey } from '../../src/map2/seating.js';

/** Reference kinds. Only `values` can run the primary metric. */
export const REF_NONE = 'none';
export const REF_OCCUPANCY = 'occupancy';
export const REF_VALUES = 'values';

/** Refusal tokens. `verdict.js` maps them onto the honest-degradation vocabulary. */
export const REFUSE_TRUNCATED = 'truncated';
export const REFUSE_NO_CELLS = 'no_cells';
export const REFUSE_NO_FRAME = 'no_frame';
export const REFUSE_VOTE_CAP = 'vote_cap_exceeded';

/** The two axes that are searched. `grid_y_invert` is not one of them -- see C1. */
export const CANDIDATE_AXES = Object.freeze(['rotation', 'side']);

/**
 * The eight candidate frames. WHOLE frames -- see C1.
 *
 * Every axis other than rotation/side survives verbatim (dimensions, start, y-invert), which
 * is what makes each candidate's geometry get re-derived by the seater instead of inherited
 * from a neighbour.
 */
export function candidateFrames(frame) {
  const base = flatFrame(frame);
  return Object.freeze(candidateList().map(c => Object.freeze({
    id: c.id,
    rotation: c.rotation,
    side: c.side,
    frame: Object.freeze(Object.assign({}, base, { rotation: c.rotation, side: c.side })),
  })));
}

/**
 * Accepts either a Frame from `declaration.frameFromDeclaration` (whose flat fields already
 * carry the declared values) or a bare `{cols, rows, rotation, side, startX, startY,
 * invertY}`. Only the seven axes the seater reads are copied; nothing else is retained.
 */
function flatFrame(frame) {
  const f = frame || {};
  return {
    cols: numOr(f.cols, 0),
    rows: numOr(f.rows, 0),
    startX: numOr(f.startX, 0),
    startY: numOr(f.startY, 0),
    rotation: numOr(f.rotation, 0),
    side: f.side === 'back' ? 'back' : 'front',
    invertY: !!f.invertY,
  };
}

function numOr(v, dflt) {
  const n = Number(v);
  return Number.isFinite(n) ? n : dflt;
}

/** The candidate id a frame's own declaration names. Lets a caller show "현재 선언". */
export function storedCandidateId(frame) {
  const f = flatFrame(frame);
  return candidateId(f.rotation, f.side);
}

// ── probing the seater ─────────────────────────────────────────────────────────

/**
 * d(seat)/d(start), PROBED off the injected seater rather than transcribed -- see C2.
 *
 * Holding the STORED coordinate fixed is the right probe: the question is "if this map had
 * declared a different origin, where would this same stored cell land". Returns the two
 * columns plus whether the matrix is unimodular, which is the only shape a start correction
 * can be inverted from exactly.
 */
export function measureStartJacobian(seat, frame) {
  const base = flatFrame(frame);
  const probe = [{ x: base.startX, y: base.startY }];
  const at = (dsx, dsy) => {
    const s = seat(probe, Object.assign({}, base, { startX: base.startX + dsx, startY: base.startY + dsy }));
    const one = s.seats[0];
    return one ? [one.x, one.y] : null;
  };
  let p0, px, py;
  try { p0 = at(0, 0); px = at(1, 0); py = at(0, 1); } catch (e) { p0 = null; }
  if (!p0 || !px || !py) return Object.freeze({ dx: null, dy: null, invertible: false });
  const dx = Object.freeze([px[0] - p0[0], px[1] - p0[1]]);
  const dy = Object.freeze([py[0] - p0[0], py[1] - p0[1]]);
  const det = dx[0] * dy[1] - dx[1] * dy[0];
  return Object.freeze({ dx, dy, invertible: det === 1 || det === -1 });
}

/**
 * Does the seater model `grid_y_invert` at all? MEASURED, not assumed.
 *
 * 🔴 THIS IS NOT A RHETORICAL CHECK. Layer 4's `seatOf` is a faithful transcription of
 *    `cell_to_physical`, but the production stored-to-common path is
 *    `cell_to_physical(visual_to_cell(x, y))`, and `visual_to_cell` carries TWO further
 *    terms: the bounding-box origin and the y-inversion. The bbox term is a per-candidate
 *    CONSTANT, so it is absorbed by the shift C2 solves and cannot change a count. The
 *    y-inversion is a REFLECTION and is not absorbed by any translation. So a seater that
 *    drops it will seat a `grid_y_invert: true` map mirrored, and the candidate this module
 *    names would be a lie about which frame produced those numbers.
 *
 * Reporting it is the honest move: the count is still right (the mirrored reading is one of
 * the eight, per section 2's aliasing), but the LABEL on it would not be. A caller that sees
 * `honoursInvertY: false` on a map declaring inversion knows not to write the winner back.
 */
export function probeInvertY(seat, frame) {
  const base = flatFrame(frame);
  const probe = [{ x: base.startX, y: base.startY + 1 }];
  try {
    const a = seat(probe, Object.assign({}, base, { invertY: false })).seats[0];
    const b = seat(probe, Object.assign({}, base, { invertY: true })).seats[0];
    if (!a || !b) return false;
    return a.x !== b.x || a.y !== b.y;
  } catch (e) { return false; }
}

/**
 * Solve `J * dstart = shift` exactly. Integer arithmetic only; null when the Jacobian is not
 * unimodular or the shift is not in its image. A null is reported as a null and never as a
 * rounded guess -- a start that is almost right puts every cell in the wrong die.
 */
export function startCorrection(jacobian, shift) {
  if (!jacobian || !jacobian.invertible) return null;
  const [a, c] = jacobian.dx;
  const [b, d] = jacobian.dy;
  const det = a * d - c * b;
  const nx = shift[0] * d - shift[1] * b;
  const ny = -shift[0] * c + shift[1] * a;
  if (nx % det !== 0 || ny % det !== 0) return null;
  return Object.freeze([nx / det, ny / det]);
}

// ── cells ──────────────────────────────────────────────────────────────────────
//
// A cell is `[x, y]`, `[x, y, value]` or `{x, y, value}`. Values compare as TRIMMED STRINGS
// because the two sides of every measured pair store bins as text in one table and as a
// number in another, and `'3' !== 3` would report a perfect match as a total mismatch. Null
// and empty string are an ABSENT value, not a value equal to empty.
function cellValue(raw) {
  if (raw === undefined || raw === null) return null;
  const s = String(raw).trim();
  return s === '' ? null : s;
}

function normaliseCells(cells) {
  const out = [];
  let withValue = 0;
  for (const c of (cells || [])) {
    let x, y, v;
    if (Array.isArray(c)) { x = c[0]; y = c[1]; v = c.length > 2 ? c[2] : null; }
    else if (c && typeof c === 'object') { x = c.x; y = c.y; v = ('value' in c) ? c.value : null; }
    else continue;
    const xi = Number(x);
    const yi = Number(y);
    if (!Number.isInteger(xi) || !Number.isInteger(yi)) continue;
    const val = cellValue(v);
    if (val !== null) withValue++;
    out.push({ x: xi, y: yi, value: val });
  }
  return { cells: out, withValue };
}

// The token a die carries when the reference has no values: the footprint metric asks only
// "is something here", so occupancy is compared as a single shared value.
const OCCUPIED = 'occupied';

/**
 * Seat the reference once, in its OWN declared frame.
 *
 * The reference is PLUGGABLE (spec section 4) -- a valid-die map, another map's cells and
 * values, or nothing -- and it is a parameter rather than a hardcoded valid-die lookup
 * because the 320 maps that need alignment are exactly the ones with no valid-die map. Nailing
 * the reference to valid-die solves nothing for the population that needs solving.
 */
function prepareReference(reference, seat) {
  const empty = { kind: REF_NONE, byCoord: new Map(), refusal: null, id: null };
  if (!reference) return empty;
  const id = reference.id || null;
  if (reference.truncated) return { kind: REF_NONE, byCoord: new Map(), refusal: REFUSE_TRUNCATED, id };
  const { cells, withValue } = normaliseCells(reference.cells);
  if (cells.length === 0) return { kind: REF_NONE, byCoord: new Map(), refusal: REFUSE_NO_CELLS, id };
  if (!reference.frame) return { kind: REF_NONE, byCoord: new Map(), refusal: REFUSE_NO_FRAME, id };
  const seated = seat(cells, flatFrame(reference.frame));
  const byCoord = new Map();
  for (const s of seated.seats) byCoord.set(s.key, s.cell.value);
  return { kind: withValue > 0 ? REF_VALUES : REF_OCCUPANCY, byCoord, refusal: null, id };
}

/**
 * The exact argmax shift -- see C2. Ties break by smallest |dx|+|dy| then lexicographically:
 * deterministic, and it prefers the reading that moves the map least, which is the one an
 * operator would have to defend.
 */
function solveShift(seated, ref, maxVotePairs) {
  const useValues = ref.kind === REF_VALUES;
  const byValue = new Map();
  for (const [k, v] of ref.byCoord) {
    const token = useValues ? v : OCCUPIED;
    if (token === null) continue;
    let bucket = byValue.get(token);
    if (!bucket) { bucket = []; byValue.set(token, bucket); }
    const comma = k.indexOf(',');
    bucket.push([Number(k.slice(0, comma)), Number(k.slice(comma + 1))]);
  }
  let pairs = 0;
  for (const s of seated.seats) {
    const token = useValues ? s.cell.value : OCCUPIED;
    if (token === null) continue;
    const bucket = byValue.get(token);
    if (bucket) pairs += bucket.length;
  }
  if (pairs > maxVotePairs) return { shift: null, votes: 0, pairs };

  const votes = new Map();
  let bestCount = -1;
  for (const s of seated.seats) {
    const token = useValues ? s.cell.value : OCCUPIED;
    if (token === null) continue;
    const bucket = byValue.get(token);
    if (!bucket) continue;
    for (let i = 0; i < bucket.length; i++) {
      const k = seatKey(bucket[i][0] - s.x, bucket[i][1] - s.y);
      const n = (votes.get(k) || 0) + 1;
      votes.set(k, n);
      if (n > bestCount) bestCount = n;
    }
  }
  if (bestCount < 0) return { shift: Object.freeze([0, 0]), votes: 0, pairs };
  let chosen = null;
  for (const [k, n] of votes) {
    if (n !== bestCount) continue;
    const comma = k.indexOf(',');
    const dx = Number(k.slice(0, comma));
    const dy = Number(k.slice(comma + 1));
    if (chosen === null) { chosen = [dx, dy]; continue; }
    const a = Math.abs(dx) + Math.abs(dy);
    const b = Math.abs(chosen[0]) + Math.abs(chosen[1]);
    if (a < b || (a === b && (dx < chosen[0] || (dx === chosen[0] && dy < chosen[1])))) chosen = [dx, dy];
  }
  return { shift: Object.freeze(chosen), votes: bestCount, pairs };
}

/** One source. Same code path `scoreSources` uses; there is no second spelling of the body. */
export function scoreSource(args) {
  const a = args || {};
  return scoreSources({
    sources: [a.source], reference: a.reference, config: a.config, seat: a.seat,
  }).sources[0];
}

/**
 * N sources, ONE common frame, ONE reference. Returns counts. Ranks nothing.
 *
 * @param {object}    args
 * @param {Array}     args.sources    `[{ id, frame, cells, truncated? }, ...]`
 * @param {object?}   args.reference  `{ id, frame, cells, truncated? }` or null
 * @param {object}    [args.config]   `{ max_vote_pairs? }`. Decision thresholds are NOT read
 *                                    here -- they belong to layer 7, and a scorer that read a
 *                                    threshold would be ranking.
 * @param {Function}  [args.seat]     layer 4's `computeSeating(cells, frame)`. Injectable so a
 *                                    harness can substitute a production-faithful
 *                                    transcription; NOT a place for callers to bring geometry.
 */
export function scoreSources(args) {
  const a = args || {};
  const seat = typeof a.seat === 'function' ? a.seat : computeSeating;
  const config = a.config || {};
  const maxVotePairs = Number.isFinite(config.max_vote_pairs) ? config.max_vote_pairs : Infinity;

  const ref = prepareReference(a.reference, seat);
  const sources = (a.sources || []).map(src => scoreOne(src, ref, seat, maxVotePairs));

  const result = Object.freeze({
    reference: Object.freeze({
      id: ref.id, kind: ref.kind, cells: ref.byCoord.size, refusal: ref.refusal,
    }),
    sources: Object.freeze(sources),
  });
  assertIntegerCounts(result);
  return result;
}

function scoreOne(src, ref, seat, maxVotePairs) {
  const sourceId = (src && src.id) || null;
  const refuse = (token) => Object.freeze({
    sourceId, refusal: token, referenceKind: ref.kind,
    cells: 0, discriminatingDies: 0, distinctSeatings: 0,
    storedCandidateId: null, honoursInvertY: false, jacobian: null,
    candidates: Object.freeze([]),
  });

  if (!src) return refuse(REFUSE_NO_CELLS);
  if (src.truncated) return refuse(REFUSE_TRUNCATED);
  if (!src.frame) return refuse(REFUSE_NO_FRAME);
  if (ref.refusal) return refuse(ref.refusal);
  const { cells } = normaliseCells(src.cells);
  if (cells.length === 0) return refuse(REFUSE_NO_CELLS);

  const base = flatFrame(src.frame);
  const jac = measureStartJacobian(seat, base);
  const honoursInvertY = probeInvertY(seat, base);

  // ── pass 1: seat each candidate as a WHOLE frame, then solve its shift ───────
  const built = [];
  for (const cand of candidateFrames(base)) {
    const seated = seat(cells, cand.frame);
    const solved = ref.kind === REF_NONE
      ? { shift: Object.freeze([0, 0]), votes: 0, pairs: 0 }
      : solveShift(seated, ref, maxVotePairs);
    if (solved.shift === null) return refuse(REFUSE_VOTE_CAP);
    const placed = new Map();
    for (const s of seated.seats) placed.set(seatKey(s.x + solved.shift[0], s.y + solved.shift[1]), s.cell.value);
    built.push({ cand, seated, shift: solved.shift, placed });
  }

  // ── pass 2: the discriminating subset, computed ACROSS candidates ────────────
  // A reference die where all eight candidates propose the same thing carries zero
  // information (spec section 3 rule 3: a symmetric core cell is worth nothing). It is
  // computed AFTER the shifts are fixed, in that order deliberately: the alternative is an
  // iteration whose fixed point nobody could describe, and an undescribable fixed point is
  // how a scorer starts disagreeing with itself between runs.
  const discriminating = new Set();
  if (ref.kind !== REF_NONE) {
    for (const k of ref.byCoord.keys()) {
      let first = null;
      for (let i = 0; i < built.length; i++) {
        const got = built[i].placed.has(k) ? built[i].placed.get(k) : undefined;
        const token = got === undefined ? ' none' : (ref.kind === REF_VALUES ? String(got) : OCCUPIED);
        if (i === 0) first = token;
        else if (token !== first) { discriminating.add(k); break; }
      }
    }
  }

  // How many of the eight this reference can actually tell apart, as PLACED die sets. Fewer
  // than eight means some candidates are invisible to it -- a circle is invariant under all
  // of D4. MEASURED here rather than transcribed from the spec's "6 of 8", because that
  // number is a property of one reference and not of the method.
  const signatures = new Set();
  for (const b of built) signatures.add(Array.from(b.placed.keys()).sort().join('|'));

  const candidates = built.map((b) => {
    let occupancyOverlapDies = 0;
    let agreeAllDies = 0;
    let evaluatedDies = 0;
    let disc = 0;
    let agree = 0;
    for (const [k, v] of b.placed) {
      if (!ref.byCoord.has(k)) continue;
      occupancyOverlapDies++;
      const rv = ref.byCoord.get(k);
      const isDisc = discriminating.has(k);
      if (isDisc) disc++;
      if (ref.kind !== REF_VALUES || v === null || rv === null) continue;
      evaluatedDies++;
      if (v === rv) { agreeAllDies++; if (isDisc) agree++; }
    }
    const corr = startCorrection(jac, b.shift);
    return Object.freeze({
      // `candidate_id` / `agree` / `discriminating` are the names layer 7 and the view model
      // already use (`view_model.agreementText` renders `일치 <agree> / 판별
      // <discriminating>`). Emitting a second spelling of them here is exactly the defect
      // this file's header refuses, so the primary metric carries THEIR names and the
      // whole-set numbers get their own.
      candidate_id: b.cand.id,
      rotation: b.cand.rotation,
      side: b.cand.side,
      // Reported, never searched (C1) -- carried from the target's own declaration.
      invertY: base.invertY,
      // The primary metric: value agreement over the discriminating subset, in DIES.
      agree,
      discriminating: disc,
      // The same metric over every comparable die, kept because `agree/discriminating` alone
      // cannot tell "few dies of evidence" from "much evidence, mostly agreeing".
      agreeAllDies,
      evaluatedDies,
      // The secondary metric, measured flat across the eight (spec section 3). Computed
      // anyway; the CALLER decides what to show.
      occupancyOverlapDies,
      shift: b.shift,
      startCorrection: corr,
      startX: corr ? base.startX + corr[0] : base.startX,
      startY: corr ? base.startY + corr[1] : base.startY,
      seatedCells: b.seated.seatCount,
    });
  });

  return Object.freeze({
    sourceId,
    refusal: null,
    referenceKind: ref.kind,
    cells: cells.length,
    discriminatingDies: discriminating.size,
    distinctSeatings: signatures.size,
    storedCandidateId: storedCandidateId(base),
    // False means the seater does not model `grid_y_invert`; see `probeInvertY`.
    honoursInvertY,
    jacobian: jac,
    candidates: Object.freeze(candidates),
  });
}

/**
 * The runtime half of C3. Every number this module emits is a count or a lattice coordinate,
 * so every number must be an integer. Cheap, total, and it does not rely on anybody
 * remembering to write the test.
 */
function assertIntegerCounts(node, path) {
  const p = path || 'result';
  if (typeof node === 'number') {
    if (!Number.isInteger(node)) {
      throw new TypeError(
        `scoring emitted a non-integer at ${p}: ${node}. Scores are counts of dies, never `
        + 'ratios: a coverage percentage was measured INVERTING the ranking '
        + '(MAP_ALIGNMENT_SPEC section 3).');
    }
    return;
  }
  if (Array.isArray(node)) {
    for (let i = 0; i < node.length; i++) assertIntegerCounts(node[i], `${p}[${i}]`);
    return;
  }
  if (node && typeof node === 'object') {
    for (const k of Object.keys(node)) assertIntegerCounts(node[k], `${p}.${k}`);
  }
}

/**
 * The N-ary payoff made usable: every source's cells in the ONE common frame under a chosen
 * candidate and its solved shift. A caller comparing N sources cell-by-cell needs no further
 * transform and no pairwise composition -- which is the reason the common frame is the
 * physical frame rather than one of the maps.
 */
export function commonFrameCells(args) {
  const a = args || {};
  const seat = typeof a.seat === 'function' ? a.seat : computeSeating;
  const cand = candidateFrames(a.frame).find(c => c.id === a.candidateId);
  if (!cand) return Object.freeze([]);
  const shift = a.shift || [0, 0];
  const { cells } = normaliseCells(a.cells);
  const seated = seat(cells, cand.frame);
  return Object.freeze(seated.seats.map(s => Object.freeze({
    x: s.x + shift[0], y: s.y + shift[1], value: s.cell.value,
  })));
}
