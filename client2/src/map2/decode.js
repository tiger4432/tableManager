// ═══════════════════════════════════════════════════════════════════════════════
// DECODER -- the reference-view payload becomes the values layer 7 and the view model read.
//
// (MAP_ALIGNMENT_SPEC 0.2: the client does not score. Ruling 2026-08-05.)
//
// 🔴 THE CLIENT DOES NOT SCORE, SO THIS IS THE ONLY PLACE SCORES ENTER IT. That makes this
//    file the customs post, and it has exactly one job beyond shape-checking: NO PERCENTAGE
//    GETS THROUGH. Not as a field, not as a convenience, not as a tooltip number, not under a
//    different name. If a ratio exists anywhere in the client, somebody eventually renders it,
//    and a coverage ratio was MEASURED inverting the ranking -- a correctly oriented but
//    one-cell-offset candidate scored 94% and came 4th behind three wrongly oriented ones
//    (MAP_ALIGNMENT_SPEC section 3).
//
//    `view_model.assertNoRatio` already guards the far end. This guards the near end, and both
//    are needed: the view model can only see what it chose to render, while a payload field
//    nobody renders today is a field somebody renders next quarter.
//
// 🔴 IT THROWS RATHER THAN SANITISING. A silently dropped percentage leaves a server lane
//    believing its field is in use. The error names the JSON path, so the fix goes to the side
//    that can make it.
//
// ── THE INFERENCE IS GONE, BECAUSE THE WIRE NOW DECLARES IT ────────────────────
//
// Layer 7 must tell "the reference carries no values, so 8 candidates cannot be told apart"
// from "values were available and the candidates genuinely tie" -- section 4 is explicit that
// both end in no ranking and THE REPAIR DIFFERS. That needs a reference KIND.
//
// This file used to WORK THE KIND OUT from the floor cells and mark the guess as a guess.
// 🔴 DELETED 2026-08-05. The payload carries `reference.kind` explicitly -- `none` |
//    `occupancy` | `values`, verified on the wire (`server/map_alignment.py:684`). An
//    inference kept alongside a declaration is a second implementation of the same fact, and
//    the day the two disagree the screen is confident and wrong. `referenceKindSource` now
//    only ever says `declared` or `absent`; there is no third answer, because there is no
//    longer a third source.
//
// NO DOM. NO TRANSPORT. NO MODULE-LEVEL MUTABLE STATE. NO THRESHOLDS.
// ═══════════════════════════════════════════════════════════════════════════════

import { REF_NONE, REF_OCCUPANCY, REF_VALUES } from './verdict.js';
import { ASSUMED, CONFIRMED, DECLARED, DECLARATION_TOKENS } from './declaration.js';

/**
 * The three states of the borrowed-geometry offer, spelled exactly as
 * `server/map_alignment.py:792-794` spells them. Read off the wire, never derived: "there is
 * an offer" and "the offer was taken" are the server's answers, and a client that worked them
 * out from the excluded count would be a second implementation of the same question.
 */
export const ASSUMPTION_APPLIED = 'applied';
export const ASSUMPTION_AVAILABLE = 'available';
export const ASSUMPTION_UNAVAILABLE = 'unavailable';
const ASSUMPTION_STATES = new Set(
  [ASSUMPTION_APPLIED, ASSUMPTION_AVAILABLE, ASSUMPTION_UNAVAILABLE]);

/**
 * Provenance of `referenceKind`. `inferred` is RETIRED: it is still exported so the harness
 * that scores the before/after comparison keeps importing, but `decodeReferenceView` can no
 * longer produce it. Two answers only -- the wire said so, or there was nothing to read.
 */
export const KIND_DECLARED = 'declared';
export const KIND_INFERRED = 'inferred';
export const KIND_ABSENT = 'absent';

/**
 * THE AXIS THE RULING WAS MADE ON, in the server's own spelling
 * (`server/map_alignment.py:1255-1267`). Declared here because this is the file that branches
 * on them, the same discipline as the reference kinds in `verdict.js`.
 */
export const METRIC_OCCUPANCY = 'occupancy';
export const METRIC_VALUES = 'values';
export const METRIC_VALUES_WEIGHTED = 'values_weighted';
export const METRIC_INDEX = 'index';

/**
 * A CANDIDATE'S OWN STATE, in the server's own spelling (`server/map_alignment.py:1134-1139`).
 *
 * 🔴 THREE WORDS, NOT TWO, AND FOLDING THEM WAS THE BUG. `map_alignment.py:1132` says it from
 *    the other side: 「안 본 후보는 못 잰 후보가 아니다」. A frame excluded by the side
 *    declaration was never looked at; a frame whose transform was refused was looked at and
 *    could not be measured; a frame that scored 0 lost. The server sends all three apart, and
 *    the client used to read only the placeholder `0` every non-scored candidate carries -- so
 *    four frames nobody considered rendered as four frames that lost by 88 dies.
 */
export const CAND_SCORED = 'scored';
export const CAND_NOT_CONSIDERED = 'not_considered';
export const CAND_NOT_SCORABLE = 'not_scorable';
const CAND_UNMEASURED = new Set([CAND_NOT_CONSIDERED, CAND_NOT_SCORABLE]);

/**
 * WHETHER THE SERPENTINE WALK CAN BE PAINTED, AND WHEN IT CANNOT, WHY.
 *
 * 🔴 `cell_index` HAS TWO KINDS OF `null` AND THEY ARE NOT THE SAME FACT. An ELEMENT null says
 *    that row carried no number -- the die is in the walk and has no colour. The WHOLE FIELD
 *    null says the pool was clipped (`sources.truncated` says why), and a clipped pool is NOT
 *    a complete walk. The server split them deliberately; folding them lets a ramp that stops
 *    two thirds of the way across render as if it were the whole job, which is the picture an
 *    operator would confirm.
 *
 * 🔴 `pooled` IS A REFUSAL, NOT A DEGRADED PICTURE. Rank restarts at 1 per map, so two maps in
 *    one array are two independent walks; one ramp over both is confidently wrong in exactly
 *    the way this screen exists to stop. The server refuses the placement anchor for the same
 *    reason (`ANCHOR_MULTI_MAP`).
 *
 * `absent` mirrors the server's own `ruling.index_axis` token (`map_alignment.py:2680`): no row
 * carries a number, so there is nothing to offer and the control is not rendered at all.
 */
export const INDEX_WALK_READY = 'ready';
export const INDEX_WALK_ABSENT = 'absent';
export const INDEX_WALK_TRUNCATED = 'truncated';
export const INDEX_WALK_POOLED = 'pooled';
export const INDEX_WALK_INCONSISTENT = 'inconsistent';

/**
 * WHICH PAIR OF NUMBERS THE RULING STANDS ON. A MIRROR of `server/map_alignment.py:1473-1478`,
 * and it must stay one: the server picks the keys there, ranks on them, and names the axis in
 * `ruling.metric` precisely so this side does not have to guess.
 *
 * 🔴 READING `agreement` REGARDLESS OF THE METRIC IS A SECOND SCORING IMPLEMENTATION WEARING
 *    THE CLOTHES OF A FIELD ACCESS. Measured on the wire (`dt_map` / `SYN-IDX-FULL-R0` against
 *    `valid_die_ref:PRD-A_DT13`, 2026-08-06): the ruling said `metric: "index"`,
 *    `winner: "rot0_front"`, margin 87 over `index_agreement` 88/87 against 1/0 for every other
 *    frame -- while the screen rendered the OCCUPANCY column, 88/43 against 66/21 and 62/17,
 *    and reached its own conclusion off it. Same numbers, different question, and the screen
 *    was the only place the two ever disagreed.
 *
 * 🔴 AN UNRECOGNISED METRIC FALLS BACK TO OCCUPANCY, WHICH IS WHAT THE SERVER'S OWN `else`
 *    DOES. The token is still carried to the record verbatim (`ruling_metric`), so a new axis
 *    shows up in the log as itself rather than as nothing; what it must not do is leave this
 *    function with no keys at all and empty the eight.
 */
/**
 * 🔴 `total` IS THE DENOMINATOR AND `discriminating` IS NOT. This is the field that was missing,
 *    and its absence is what put full marks on screen for a candidate the server scored short.
 *
 *    On EVERY axis the server computes the discriminating count as a SUBSET OF THE NUMERATOR --
 *    `count_nonzero(member & varies)` (`map_alignment.py:2691`, `:2702-2704`, `:2711-2713`), where
 *    `member` is the agreement vector itself. So `discriminating <= agree` by construction, and
 *    the pair can never be read as "hits out of population". On the index axis the two are EQUAL
 *    whenever no single cell is matched by all eight frames, which is the ordinary case: measured
 *    on a 512-cell payload where the winner agreed on 300, all eight candidates rendered
 *    `일치 N / 판별 N`, i.e. full marks, eight times over.
 *
 *    The population each axis actually scored against, as the server ships it per candidate:
 *      · index      `index_total`   cells carrying a stored number (`map_alignment.py:2686`,
 *                                   candidate-independent BY DESIGN -- the server's own comment
 *                                   at :2683 says a per-candidate denominator makes the eight
 *                                   report eight different fractions)
 *      · values     `agreement`     the positional overlap, because a value is compared only
 *                                   where a cell landed on the reference (`:2631`)
 *      · occupancy  `placed`        the cells this candidate placed (`:2800`); `agreement` is
 *                                   `count_nonzero(member)` over exactly that array (`:2511`)
 *
 *    `discriminating` STAYS -- it is what `min_discriminating_dies` gates on and dropping it
 *    would silently change which runs rank. It is simply not a denominator and is no longer
 *    rendered as one.
 */
export function scoringKeysFor(metric) {
  if (metric === METRIC_INDEX) {
    return Object.freeze({ agree: 'index_agreement', discriminating: 'index_discriminating',
                           total: 'index_total' });
  }
  if (metric === METRIC_VALUES || metric === METRIC_VALUES_WEIGHTED) {
    return Object.freeze({ agree: 'value_agreement', discriminating: 'value_discriminating',
                           total: 'agreement' });
  }
  return Object.freeze({ agree: 'agreement', discriminating: 'discriminating',
                         total: 'placed' });
}

/**
 * Words that mean "a ratio", matched against the JSON path a WORD AT A TIME.
 *
 * 🔴 IT IS WORDS, NOT A SUBSTRING, AND THAT IS A BUG FIX RATHER THAN A REFINEMENT. This was
 *    `/percent|pct|ratio|coverage|fitness|_pp\b/i` tested against the whole path, and the word
 *    **decla-RATIO-n** contains `ratio`. The moment the payload grew a `declaration` block
 *    (2026-08-05) EVERY live response threw `RatioInPayloadError` naming six fields that are
 *    plain integer tallies. Measured, not reasoned: the harness's own good payload could not
 *    be decoded at all.
 *
 *    A guard that fires on honest names gets switched off within a week, and switching this
 *    one off is how a percentage gets into the client. So it is made precise instead: the path
 *    is split on `.`, `[n]`, `_` and camelCase humps, and each WORD is compared exactly.
 *    `coverage_pct` still dies (two hits), `agreementRatio` still dies, `declaration` lives.
 *
 * `score` is deliberately absent: it is not a ratio by itself.
 */
const RATIO_WORDS = new Set([
  'percent', 'percentage', 'percentages', 'pct', 'ratio', 'ratios',
  'coverage', 'fitness', 'pp',
]);

function pathWords(path) {
  return String(path)
    .replace(/\[\d+\]/g, '.')
    .split(/[.\-_\s]+/)
    .flatMap(seg => seg.replace(/([a-z0-9])([A-Z])/g, '$1 $2').split(/\s+/))
    .filter(Boolean)
    .map(w => w.toLowerCase());
}

function looksLikeARatio(path) {
  for (const w of pathWords(path)) if (RATIO_WORDS.has(w)) return true;
  return false;
}

/**
 * Fields whose value is a count of dies or maps. A non-integer here is a ratio in disguise.
 *
 * 🔴 KEYED ON FIELD NAMES, SO A RENAME SILENTLY NARROWS IT. When the wire renamed `agree` to
 *    `agreement` (2026-08-05), `agreement: 0.97` stopped throwing and started being quietly
 *    dropped by `intOrNull` as "not an integer" -- the screen would lose a candidate instead
 *    of the server hearing that its field was wrong. Both spellings are kept: the old ones
 *    cost nothing and a payload carrying either must be refused the same way.
 */
const COUNT_FIELDS = new Set([
  // current wire
  'agreement', 'discriminating', 'map_count', 'cell_count', 'excluded_total',
  'scored_cells', 'attested_maps', 'unattested_maps', 'distinct_seatings',
  // The index axis. Counts of dies by construction on the server side
  // (`int(np.count_nonzero(...))`, `map_alignment.py:1090-1094`), so a fraction arriving under
  // one of these names is the same defect `agreement: 0.97` was -- and it must be refused for
  // the same reason, not dropped as "not an integer" while a server lane believes its field
  // is in use.
  'index_agreement', 'index_discriminating', 'index_total', 'index_margin',
  // previous wire, kept so a stale producer is refused rather than silently trimmed
  'agree', 'excluded_map_count', 'discriminating_dies',
]);

/**
 * 🔴 `value_agreement` / `value_discriminating` / `value_margin` ARE DELIBERATELY ABSENT FROM
 *    THE SET ABOVE, AND THAT IS NOT AN OVERSIGHT. Under `values_weighted` the server emits them
 *    as FLOATS on purpose -- `float(w[member].sum())`, `map_alignment.py:1109-1112` -- because a
 *    weighted die count is not a whole number of dies. They are weighted DIES, not a ratio: the
 *    denominator is never divided out, and `map_alignment.py:1158-1160` refuses to `int()` the
 *    margin precisely so the threshold comparison keeps its fraction. Listing them here would
 *    make every weighted payload throw `RatioInPayloadError` on an honest measurement, which is
 *    how a guard that fires on honest names gets switched off within a week (see `RATIO_WORDS`).
 */

export class RatioInPayloadError extends Error {
  constructor(paths) {
    super(
      'a ratio reached the client from the reference-view payload: ' + paths.join('; ')
      + '. Coverage ratios were measured INVERTING the ranking, so counts and a margin in '
      + 'dies are carried instead. Fix the payload, not this check.');
    this.name = 'RatioInPayloadError';
    this.paths = Object.freeze(paths.slice());
  }
}

/**
 * Throws if anything in `payload` is a ratio, by name or by value-in-a-count-field.
 * Exported so a transport-level test can run it without building a whole decode.
 */
export function assertNoRatioInPayload(payload) {
  const bad = [];
  walk(payload, '', (path, value, leafName) => {
    if (looksLikeARatio(path)) bad.push(`${path} (name)`);
    else if (COUNT_FIELDS.has(leafName) && typeof value === 'number' && !Number.isInteger(value)) {
      bad.push(`${path} = ${value} (count field holding a fraction)`);
    } else if (typeof value === 'string' && /\d\s*%/.test(value)) {
      bad.push(`${path} = ${value}`);
    }
  });
  if (bad.length > 0) throw new RatioInPayloadError(bad);
  return true;
}

/**
 * Payload in, values out. Never throws on a MISSING field -- absence is a state the screen has
 * to show -- and always throws on a ratio, which is a state it must not.
 *
 * @param {object} payload  the `/map/align/reference` body (contract in `api.js`)
 * @returns frozen record; `scorings` is directly the first argument of `verdict.decideVerdict`
 */
export function decodeReferenceView(payload) {
  const p = (payload && typeof payload === 'object') ? payload : null;
  assertNoRatioInPayload(p);

  const rejected = [];
  const scorings = [];
  // THE AXIS FIRST, THEN THE NUMBERS. Read once, outside the loop: the ruling names one axis
  // for the whole run, and a per-candidate re-read is how eight candidates end up on seven.
  const rulingMetric = (p && p.ruling && p.ruling.metric != null)
    ? String(p.ruling.metric) : null;
  const keys = scoringKeysFor(rulingMetric);
  // 🔴 THE WIRE SAYS `frame`, THE SCREEN SAYS `candidate_id`, AND THEY ARE THE SAME STRING.
  //    `rot90_tr` is `candidates.candidateId(90, 'top_right')` exactly. The rename happens here
  //    and nowhere else -- one vocabulary crosses the customs post, and downstream keeps the
  //    spelling the database and every other screen already show.
  for (const raw of arr(p && p.candidates)) {
    const frame = raw && raw.frame != null ? String(raw.frame) : null;
    if (!frame) { rejected.push('candidates: no frame'); continue; }
    const state = raw.state != null && String(raw.state) !== '' ? String(raw.state) : null;
    // The server's own sentence about THIS frame -- `미채점 - 면 선언 제외`. Carried verbatim,
    // never re-spelled: it is the only thing that tells a frame nobody looked at from a frame
    // that was looked at and lost, and composing a Korean equivalent here would be the
    // two-spellings defect the refusal sentence already taught this screen.
    const reason = raw.reason != null && String(raw.reason) !== '' ? String(raw.reason) : null;
    // 🔴 A CANDIDATE THE SERVER DID NOT SCORE CARRIES PLACEHOLDER ZEROES, NOT MEASUREMENTS.
    //    `map_alignment.py:1078` writes `discriminating = 0` for every unscored candidate and
    //    `agreement` arrives the same way, so reading the numbers without reading the state
    //    turns "never considered" into "lost 0 to 88". Measured on the wire: the four back
    //    frames of `SYN-IDX-FULL-R0` arrive `not_considered` with `index_agreement: null` and
    //    a reason, and the screen drew them as `0 / 0` marked scored.
    //
    //    KEPT IN THE LIST, NOT DROPPED. A row nobody could score is carried with NULL counts
    //    and its state, so the screen can say what it is. (`alignment.sides` retired 2026-08-08,
    //    so nothing narrows the search today -- the discipline outlives its first producer.)
    if (state !== null && CAND_UNMEASURED.has(state)) {
      // 🔴 THE PLACEMENT SURVIVES THE MISSING COUNTS, AND IT HAS TO. A refusal is about the
      //    SCORE; the server places every row it could seat regardless of whether it could rank
      //    it (`map_alignment.py` `_candidate_rows`'s `placement`, which since 2026-08-08 also
      //    seats the ANCHOR-LESS rows off the search pivot and says so in `placement_basis`).
      //    Dropping the seat here emptied the picture on the ONE screen where the
      //    operator has no counts to fall back on and the picture is the whole diagnostic --
      //    measured: 0 of 4 source dies drawn in the `not_scorable` fixture.
      scorings.push(Object.freeze({
        candidate_id: frame, agree: null, discriminating: null, total: null, state, reason,
        placement: decodePlacement(raw && raw.placement, rejected, frame) }));
      continue;
    }
    // 🔴 NOT `intOrNull`. Under `values_weighted` the axis this ruling stands on is weighted
    //    dies and legitimately fractional (`map_alignment.py:1109`); demanding an integer here
    //    would drop all eight candidates on every weighted payload. The integrality of the
    //    COUNTING axes is enforced where it belongs -- `assertNoRatioInPayload` above, which
    //    has already run and thrown on a fractional `agreement` or `index_agreement`.
    const agree = numOrNull(raw[keys.agree]);
    const discriminating = numOrNull(raw[keys.discriminating]);
    if (agree === null || discriminating === null) {
      // Dropped, and SAID so. A scoring silently missing from the list would shrink the
      // denominator of "how many candidates tied" without anything on screen changing. The
      // AXIS is named too: on a four-axis payload "the numbers are missing" does not tell a
      // server lane which pair of fields it failed to send.
      rejected.push(`candidates ${frame}: ${keys.agree}/${keys.discriminating} not numbers`);
      continue;
    }
    // 🔴 ABSENT, NOT ZERO, AND NOT A REASON TO DROP THE ROW. A producer that predates this
    //    field ships counts without a population, and the honest screen for that is `미상` on
    //    the denominator -- not a rejected candidate (which would shrink the tie count) and not
    //    a `0` (which would read as "nothing was there to match", a claim nobody measured).
    const total = numOrNull(raw[keys.total]);
    scorings.push(Object.freeze({
      candidate_id: frame, agree, discriminating, total, state: state || CAND_SCORED, reason,
      // 🔴 THE PLACEMENT THE SCORING ACTUALLY USED. `_solve_shift` picks the translation
      //    that maximises overlap for THIS candidate, scores against it, and ships it here --
      //    so it is not decoration beside the counts, it is the coordinate frame those counts
      //    were measured in. Dropping it (which this decoder did until 2026-08-06) leaves the
      //    drawing path with no offset at all, and the overlay is painted at (0,0) whatever
      //    the server placed it at.
      //
      // ⚠️ NEVER RE-DERIVED ON THIS SIDE. Solving for an offset here would be a second
      //    placement implementation, and the two would agree only while the tie-breaking
      //    matched -- which is exactly how this bug hid: the old search broke ties toward the
      //    origin, so on a saturated map it returned (0,0) and the client's missing offset
      //    agreed with the scorer BY ACCIDENT.
      shift: decodeShift(raw && raw.shift, rejected, frame),
      // 🔴 THE SEAT ITSELF, NOT THE PARAMETERS TO REBUILD IT. `shift` above is only the
      //    translation the scorer solved; it says nothing about which way the map was turned,
      //    and the screen used to answer that second question by RECOMPOSING the frame from
      //    rotation/side/dims/start. That recomposition was wrong -- `grid_y_invert` inverts
      //    WHICH frames are mirrors (a source declaring it makes `rot0_front` a reflection and
      //    `rot0_back` rotation-only), and the client had the mirror set backwards, which is
      //    exactly the "symmetric map, only the back is displaced" report.
      //
      //    `placement` is the composition's RESULT (`map_alignment.py` `_candidate_rows`, the `placement` block). There is
      //    nothing left to compose, so there is nothing left to get wrong.
      placement: decodePlacement(raw && raw.placement, rejected, frame),
    }));
  }

  const ref = (p && p.reference && typeof p.reference === 'object') ? p.reference : null;
  // 🔴 `[x, y]` PAIRS, NOT `{x, y}`. Only the COUNT is taken here; whoever draws them reads
  //    index 0 and 1, and anything reaching for `.x` gets `undefined` and paints nothing.
  const referenceCells = arr(ref && ref.cells);
  const kind = resolveReferenceKind(ref);

  const srcBlock = (p && p.sources && typeof p.sources === 'object') ? p.sources : null;
  const sources = arr(srcBlock && srcBlock.maps).map(s => Object.freeze({
    id: s && s.map_id != null ? String(s.map_id) : null,
    label: s && s.map_id != null ? String(s.map_id) : null,
    // 🔴 WHAT IS WRITTEN DOWN, PLUS WHO WROTE IT. The raw frame alone is not evidence:
    //    `rotation: 0, side: "front"` is what the registrar emits with nobody looking, so a
    //    badge keyed on the string alone puts `현재` on maps nobody ever measured. The
    //    provenance token is the gate, and it travels beside the value.
    declaredFrame: s && s.declared_frame != null ? String(s.declared_frame) : null,
    declaredFrameSource: s && s.declared_frame_source != null ? String(s.declared_frame_source) : null,
    // 🔴 TWO FIELDS, NOT ONE, AND THE SERVER SPLITS THEM FOR A REASON. `geometry` is what THIS
    //    MAP SAYS ABOUT ITSELF; `geometry_basis` is what THIS RUN ACTUALLY STOOD ON
    //    (`map_alignment.geometry_basis_of`). Folding them together makes a borrowed geometry
    //    read as a declared one -- which is the impersonation this whole vocabulary exists to
    //    stop -- or makes the borrowing vanish. They travel separately all the way to the row.
    geometry: token(s && s.geometry, rejected, `sources.maps[].geometry (${s && s.map_id})`),
    geometryBasis: token(s && s.geometry_basis, rejected,
      `sources.maps[].geometry_basis (${s && s.map_id})`),
    cellCount: intOrNull(s && s.cell_count),
  }));

  const decl = (p && p.declaration && typeof p.declaration === 'object') ? p.declaration : null;

  return Object.freeze({
    present: !!p,
    state: p && p.state ? String(p.state) : null,
    refusalDetail: p && p.refusal ? String(p.refusal) : null,
    // 🔴 THE TALLY'S MEASUREMENTS, WHICH THE COMPOSED SENTENCE DOES NOT CARRY. `compose_refusal`
    //    lifts the reason LABELS out of this same list and joins them
    //    (`server/map_alignment.py:1062-1067`); it does not lift `example_detail`, and the
    //    detail is where the numbers are -- `소스 45x39 · 기준 44x39` for `grid_dims_differ`,
    //    the cell bbox versus the borrowed grid for `cells_outside_grid`. Reading only
    //    `excluded_total` left the operator a label with no measurement: "the grid differs"
    //    without which grid or by how much, which is the entire content of the message.
    //    Decoded as VALUES; the joining happens once, at the one slot that renders it.
    excluded: Object.freeze(arr(p && p.excluded).map(e => Object.freeze({
      reasonCode: e && e.reason_code != null ? String(e.reason_code) : null,
      // The server's own label. Never re-spelled here -- an unknown reason code still arrives
      // with the sentence that explains it, so a new server reason needs no client release.
      reason: e && e.reason != null ? String(e.reason) : null,
      count: intOrNull(e && e.count),
      exampleMapId: e && e.example_map_id != null ? String(e.example_map_id) : null,
      detail: e && e.example_detail != null && String(e.example_detail) !== ''
        ? String(e.example_detail) : null,
    }))),
    // 🔴 A COUNT PER FRAME, NOT A WINNER. The unit's maps can disagree about what is declared,
    //    and picking a winner among declarations is a JUDGEMENT -- the client must not make
    //    it. The server already counts only DECLARED-provenance maps into `frames`, and counts
    //    everything else in `unattestedMaps`, so a unanimous-looking tally with a nonzero
    //    unattested count still reads as what it is: partly unmeasured.
    // 🔴 `attested_maps` COUNTS `declared` ONLY, AND IT STAYS THAT WAY (lead PM ruling
    //    2026-08-06). The server's block is named "what is written down, not a decision", and
    //    on a confirmed map the count is literally true: nobody declared it. Folding
    //    `confirmed` in here would make the tally assert a measurement that was never taken,
    //    which is the same impersonation the token vocabulary exists to stop -- so a confirmed
    //    map is counted in `unattestedMaps` and these two numbers are carried unchanged.
    //
    // ⚠️ THE NUMBER STAYING TRUE IS NOT THE SAME AS THE SCREEN STAYING TRUE, AND THE SECOND
    //    HALF IS WHERE THE DEFECT WAS. "Unattested" rendered against a map whose frame a human
    //    confirmed is a false sentence to the operator -- the system knows something and the
    //    screen does not say it, which is exactly the shape of the dropped token. The fix is
    //    NOT in these counts: it is a third per-map state at the one place a map's own frame is
    //    shown (`main.adaptPayload` / `renderSources`). Aggregate honest, row honest, and
    //    neither borrowing the other's job.
    declaredFrameCounts: Object.freeze(Object.assign({}, (decl && decl.frames) || {})),
    attestedMaps: intOrNull(decl && decl.attested_maps),
    unattestedMaps: intOrNull(decl && decl.unattested_maps),
    // 🔴 `axis_sources` IS A TALLY KEYED ON THE TOKEN ITSELF (`map_alignment` `axis_tally`), so
    //    it GROWS A KEY when the vocabulary grows -- a confirmed unit arrives as
    //    `{rotation: {confirmed: N}}`. Copied wholesale rather than picked over on purpose: a
    //    decoder that lifted named keys would silently drop the new one, which is the defect
    //    this file's `token()` was already built to refuse one field over.
    axisSources: Object.freeze(Object.assign({}, (decl && decl.axis_sources) || {})),
    scorings: Object.freeze(scorings),
    referenceKind: kind.kind,
    referenceKindSource: kind.source,
    referenceState: ref && ref.state ? String(ref.state) : null,
    referenceCellCount: referenceCells.length,
    // The ruling the server made, carried through unchanged: the confirm write has to send it
    // back verbatim, and re-deriving it here would be the second scoring implementation.
    ruling: Object.freeze(Object.assign({}, (p && p.ruling) || {})),
    rulingWinnerId: p && p.ruling && p.ruling.winner ? String(p.ruling.winner) : null,
    // The axis, and the axis the counts above were actually read from -- one field, read once,
    // so no downstream consumer re-derives it and picks a different pair of numbers.
    rulingMetric,
    rulingScoringKeys: keys,
    // 🔴 THE THRESHOLDS THE RULING STOOD ON, WHICH ARE PER AXIS. `_rule_on` is handed
    //    `index_thresholds if metric == METRIC_INDEX else thresholds`
    //    (`map_alignment.py:1194`) because each axis counts a different thing and a shared
    //    dict would mean the same name measuring two quantities. So the pair that decided is
    //    the pair ON the ruling, not the one beside it -- and carrying it is what stops this
    //    side re-deciding the same evidence against a different bar.
    rulingThresholds: decodeThresholds(p && p.ruling),
    // 🔴 THE RULING'S OWN FACT ABOUT ITSELF -- "this verdict stands on a borrowed wafer". It
    //    lives ON the ruling rather than beside it (`map_alignment.py:547`) precisely so it
    //    cannot be separated from the answer it qualifies, and it is read `=== true`: a
    //    verdict may only be marked as assumed because the server said so.
    geometryAssumed: !!(p && p.ruling && p.ruling.geometry_assumed === true),
    assumption: decodeAssumption(p, rejected),
    // How many of the candidates the reference can actually tell apart, when the server
    // measured it. NULL when it did not -- an unmeasured count is reported as unmeasured and
    // never as zero, because zero would read as "none are blind", which is a claim.
    distinctSeatings: intOrNull(p && p.distinct_seatings),
    sources: Object.freeze(sources),
    // 🔴 THE WALK'S STATE, DECIDED HERE AND NOWHERE ELSE. Evaluated before `rejected` is
    //    frozen below, because a refusal appends its reason to that list -- a walk refused
    //    silently would leave the console saying the payload was clean.
    indexWalk: decodeIndexWalk(p, rejected),
    counts: Object.freeze({
      mapCount: intOrNull(srcBlock && srcBlock.map_count),
      excludedMapCount: intOrNull(p && p.excluded_total),
      discriminatingDies: intOrNull(p && p.stats && p.stats.scored_cells),
      // The server times in float milliseconds. Rounded, not dropped: `intOrNull` would call
      // 340.7 a non-integer and report the elapsed time as unmeasured, which is a lie about a
      // measurement that was taken.
      elapsedMs: msOrNull(p && p.stats && p.stats.elapsed_ms),
    }),
    rejected: Object.freeze(rejected),
  });
}

/**
 * The verdict layer's `context`, assembled from what was decoded rather than by hand at each
 * call site. Two call sites assembling this by hand is how they start disagreeing about what
 * "no reference" meant, which is the same failure the payload's own contract exists to avoid.
 */
export function verdictContext(decoded) {
  const d = decoded || {};
  return Object.freeze({
    refusalDetail: d.refusalDetail || null,
    // 🔴 WHETHER THE SERVER SCORED IS THE SERVER'S OWN WORD, NOT AN INFERENCE FROM ITS PROSE.
    //    `/view` attaches a `refusal` sentence to `state: "no_winner"` as well as to a real
    //    refusal, so without this the verdict layer reads "동점 - 판별 불가" as "I declined"
    //    and the whole screen empties. Carried verbatim; the verdict layer compares it to the
    //    payload's own spellings (`verdict.STATE_SCORED` / `STATE_NO_WINNER`).
    serverState: d.state || null,
    referenceKind: d.referenceKind || REF_NONE,
    distinctSeatings: d.distinctSeatings,
    // 🔴 THE SERVER'S DECISION, CARRIED TO THE LAYER THAT RENDERS IT. Without these three the
    //    screen re-decided the winner from `agree` alone and the server's ruling never arrived
    //    -- measured: `ruling.winner` was decoded into `rulingWinnerId` and read by NOTHING.
    //    A second ranking implementation is a second answer, and on the index axis it is a
    //    DIFFERENT one: the server breaks an agreement tie by step direction, which this side
    //    cannot see at all because `index_violations` is not in the per-candidate numbers it
    //    ranks on.
    rulingPresent: !!(d.ruling && Object.keys(d.ruling).length > 0),
    rulingWinnerId: d.rulingWinnerId || null,
    // 🔴 HOW THE SERVER DECIDED, WHICH IS A DIFFERENT CLAIM FROM WHO WON. `direction` means the
    //    die-margin comparison was DELIBERATELY SKIPPED (`map_alignment.py:3267`): violations
    //    are counted in STEPS and `min_margin_dies` is declared in DIES, so measuring one
    //    against the other would quietly change the meaning of a declaration nobody edited.
    //    The server reports the skip by name so this side can honour it instead of re-imposing
    //    a threshold in the wrong unit.
    decidedBy: (d.ruling && d.ruling.decided_by != null) ? String(d.ruling.decided_by) : null,
    // The evidence behind a direction ruling. `index_steps` is the denominator, so "0
    // violations" can be read as a measurement rather than as an absence of measuring.
    indexViolations: intOrNull(d.ruling && d.ruling.index_violations),
    indexSteps: intOrNull(d.ruling && d.ruling.index_steps),
  });
}

/**
 * THE OFFER, DECODED. A source map with no physical spec of its own can be scored by borrowing
 * the reference floor's wafer dimensions; the server emits the offer on every run where that
 * would help, whether or not anyone asked for it.
 *
 * 🔴 `requested` IS NOT `applied`. Asking is not the same as it having been possible: a request
 *    on a unit with no resolved floor comes back `unavailable`, and a screen that read its own
 *    request back as the state would report a borrowing that never happened. The state is the
 *    server's word; `requested` is only the echo of what was sent.
 * 🔴 THE BASIS IS CARRIED, NOT SUMMARISED. `{table, map_id}` names the floor the geometry would
 *    come from, and the offer is unusable without it: "borrow from somewhere" is not a claim an
 *    operator can make. An offer arriving with no basis is reported as such rather than shown as
 *    a nameless one.
 * 🔴 THE SENTENCE IS THE SERVER'S. `text` is composed by `compose_assumption_offer`, the same
 *    discipline as `refusal`, and this side never writes a Korean equivalent beside it.
 */
function decodeAssumption(p, rejected) {
  const a = (p && p.assumption && typeof p.assumption === 'object') ? p.assumption : null;
  const rawState = a && typeof a.state === 'string' ? a.state : null;
  if (rawState !== null && !ASSUMPTION_STATES.has(rawState)) {
    rejected.push(`assumption.state: unknown state '${rawState}'`);
  }
  const state = ASSUMPTION_STATES.has(rawState) ? rawState : ASSUMPTION_UNAVAILABLE;
  const b = (a && a.basis && typeof a.basis === 'object') ? a.basis : null;
  const basis = (b && b.table != null && b.map_id != null)
    ? Object.freeze({ table: String(b.table), mapId: String(b.map_id) })
    : null;
  if (state !== ASSUMPTION_UNAVAILABLE && !basis) {
    rejected.push(`assumption: state '${state}' with no basis to borrow from`);
  }
  const ids = arr(a && a.map_ids).map(v => String(v));
  return Object.freeze({
    state,
    applied: state === ASSUMPTION_APPLIED,
    // An OFFER is what an operator can act on: it can be taken, and it has not been.
    offered: state === ASSUMPTION_AVAILABLE && !!basis,
    requested: !!(a && a.requested === true),
    basis,
    // The server's count, not `map_ids.length`: two spellings of one number drift, and this one
    // is a claim about how many maps the borrowing touches.
    mapCount: intOrNull(a && a.map_count),
    mapIds: Object.freeze(ids),
    text: a && a.text ? String(a.text) : null,
  });
}

/**
 * THE TWO THRESHOLDS AS THE RULING RECORDS THEM, or NULL.
 *
 * 🔴 BOTH OR NEITHER, AND NEVER A DEFAULT. `verdict.js` refuses to rank without thresholds on
 *    purpose -- "a threshold invented in code is a plausible default impersonating a
 *    declaration" -- so a ruling carrying one of the two is carried as NOTHING rather than as a
 *    half-declaration the verdict layer would then complete with `Number(undefined)`. This is a
 *    DECLARATION READ OFF THE WIRE, not a default: the server read it from its own config and
 *    already applied it, and the numbers it applied it to are the ones decoded above.
 */
function decodeThresholds(ruling) {
  const margin = numOrNull(ruling && ruling.min_margin_dies);
  const discriminating = numOrNull(ruling && ruling.min_discriminating_dies);
  if (margin === null || discriminating === null) return null;
  return Object.freeze({ min_margin_dies: margin, min_discriminating_dies: discriminating });
}

/**
 * A PROVENANCE TOKEN OFF THE WIRE, checked against the vocabulary this client shares with
 * `server/map_overlay.py`. An unrecognised token is reported and dropped rather than passed on:
 * silently keeping one lets a word the two sides do not both know reach a badge, and every
 * server test stays green while the screen sorts it into whatever bucket happens to catch it.
 * That is the exact divergence `declaration.js` grew `assumed` to prevent.
 *
 * 🔴 IT HAPPENED ANYWAY, MEASURED 2026-08-06. The server added `confirmed` and this function
 *    rejected it on `sources.maps[].geometry` and `.geometry_basis`, returning `null` for both
 *    on every confirmed map. Not a crash, no red anywhere: the client harness pinned the six
 *    words as a LITERAL and the server's own vocabulary test names FIVE constants one by one,
 *    so neither could notice a seventh. The vocabulary is fixed above; what this note records
 *    is that being reported in `rejected` is not the same as anybody reading `rejected`.
 */
function token(value, rejected, where) {
  if (value === null || value === undefined || value === '') return null;
  const s = String(value);
  if (!DECLARATION_TOKENS.includes(s)) {
    rejected.push(`${where}: unknown provenance token '${s}'`);
    return null;
  }
  return s;
}

/**
 * A CANDIDATE'S PLACEMENT, as integer die counts, or null.
 *
 * `null` is a real answer and the common one: `map_alignment` ships `"shift": None` for every
 * candidate it did not score, and a candidate with no placement must not be drawn as though it
 * had been placed at the origin.
 *
 * 🔴 INTEGERS OR NOTHING. These are counts of dies, and the server produces them as such
 *    (`_solve_shift` searches an integer window). A fractional dx would seat every cell on a
 *    half-die and every membership test against the floor would miss, which is the silent
 *    all-miss failure `start_native_float` already cost this screen once. A malformed shift is
 *    REPORTED and dropped rather than coerced -- a placement we cannot read is not a placement.
 */
function decodeShift(raw, rejected, frame) {
  if (raw === null || raw === undefined) return null;
  if (typeof raw !== 'object') {
    rejected.push(`candidates ${frame}: shift is not an object`);
    return null;
  }
  const dx = intOrNull(raw.dx);
  const dy = intOrNull(raw.dy);
  if (dx === null || dy === null) {
    rejected.push(`candidates ${frame}: shift {dx, dy} are not both integers`);
    return null;
  }
  return Object.freeze({ dx, dy });
}

/**
 * A CANDIDATE'S SEAT, as the server shipped it, or null.
 *
 *     placed = anchorRef + linear * (cell - anchorSrc)
 *
 * transcribed from the producer's own sentence (`server/map_alignment.py` `_candidate_rows`, the `placement` block) rather than
 * re-derived. `linear` is a signed permutation matrix -- the composed rotation, side flip and
 * y-inversion of BOTH maps, already multiplied out -- so the reader has no composition order to
 * get wrong. Mirror-ness is `det(linear) === -1` and is deliberately NOT carried separately.
 *
 * 🔴 `anchorRef` ALREADY CARRIES THE SOLVED SHIFT (`map_alignment.py` `_candidate_rows`, the
 *    `placement` block, which adds the solved `(dx, dy)` into the seat it ships -- do not
 *    transcribe the retired closed form for it here, that is what a second copy is for).
 *    Adding `shift` on top of a placement is a DOUBLE APPLICATION -- the
 *    same arithmetic mistake `4947a65` fixed on the server, where an anchor was applied twice
 *    and the shift it solved was zero by construction. `placeCells` takes no shift argument.
 *
 * ⚠️ ABSENT IS NOT THE IDENTITY. `null` means this server did not place this candidate -- the
 *    transform refused this frame, or this producer predates the field. It NO LONGER means "the
 *    anchor declined": since 2026-08-08 an anchor-less unit is seated off the search pivot and
 *    carries `placement_basis: 'shift_search'`. A reader that substituted the
 *    identity here would draw the source unturned and unmoved on top of the floor, which is a
 *    plausible picture of a claim nobody made. The screen names the state instead (`배치 없음`).
 */
function decodePlacement(raw, rejected, frame) {
  if (raw === null || raw === undefined) return null;
  if (typeof raw !== 'object') {
    rejected.push(`candidates ${frame}: placement is not an object`);
    return null;
  }
  const linear = intPair2x2(raw.linear);
  const anchorSrc = intPair(raw.anchor_src);
  const anchorRef = intPair(raw.anchor_ref);
  if (!linear || !anchorSrc || !anchorRef) {
    rejected.push(`candidates ${frame}: placement {linear, anchor_src, anchor_ref} are not all integers`);
    return null;
  }
  // 🔴 THE DETERMINANT IS CHECKED, NOT ASSUMED. The eight candidates are signed permutation
  //    matrices, so |det| is 1. Anything else is not a frame of this lattice, and seating cells
  //    under it would spread or fold the map -- the server refuses the same shape for the same
  //    reason (`map_alignment.py` `start_for_placement`'s determinant refusal: 원점을 지어내지 않고 거절한다).
  const det = linear[0][0] * linear[1][1] - linear[0][1] * linear[1][0];
  if (det !== 1 && det !== -1) {
    rejected.push(`candidates ${frame}: placement.linear det ${det}, not a frame of the lattice`);
    return null;
  }
  return Object.freeze({
    linear: Object.freeze([Object.freeze(linear[0]), Object.freeze(linear[1])]),
    anchorSrc: Object.freeze(anchorSrc),
    anchorRef: Object.freeze(anchorRef),
    det,
  });
}

/** `[a, b]` of integers, or null. `intOrNull` already refuses a declared-looking `"3.5"`. */
function intPair(v) {
  if (!Array.isArray(v) || v.length !== 2) return null;
  const a = intOrNull(v[0]);
  const b = intOrNull(v[1]);
  return (a === null || b === null) ? null : [a, b];
}

/** `[[a11, a12], [a21, a22]]` of integers, or null. */
function intPair2x2(v) {
  if (!Array.isArray(v) || v.length !== 2) return null;
  const r0 = intPair(v[0]);
  const r1 = intPair(v[1]);
  return (r0 && r1) ? [r0, r1] : null;
}

/** True when this map was scored on geometry it does not itself declare. */
export function isAssumedGeometry(source) {
  return !!(source && source.geometryBasis === ASSUMED);
}

/** True when this map stood on its own declared geometry. Not the negation of the above --
 *  an excluded map stood on nothing at all and must not read as either. */
export function isDeclaredGeometry(source) {
  return !!(source && source.geometryBasis === DECLARED);
}

/**
 * True when this map was scored on geometry DERIVED UNDER A CONFIRMED MATCH.
 *
 * 🔴 A THIRD PREDICATE, NOT A WIDENING OF EITHER EXISTING ONE, AND THAT IS THE POINT OF THE
 *    ROUND. Widening `isDeclaredGeometry` would say somebody measured this map (false).
 *    Widening `isAssumedGeometry` would say it rests on an operator's unverified claim, when
 *    what it actually rests on is a match against a per-product valid-die map plus a recorded
 *    `confirmation_uid` -- re-checkable, which an assumption is not. Three states because the
 *    server ranks three, and a client with two buckets must round one of them off.
 */
export function isConfirmedGeometry(source) {
  return !!(source && source.geometryBasis === CONFIRMED);
}

/**
 * READ, NEVER DERIVE. `reference.kind` is on the wire; the old footprint-sniffing inference is
 * deleted. An unrecognised or absent kind is reported as `none`/`absent` rather than guessed:
 * "we do not know" is a state the screen can show, and a guess dressed as a declaration is not.
 */
function resolveReferenceKind(ref) {
  const declared = ref && typeof ref.kind === 'string' ? ref.kind : null;
  if (declared === REF_NONE || declared === REF_OCCUPANCY || declared === REF_VALUES) {
    return { kind: declared, source: KIND_DECLARED };
  }
  return { kind: REF_NONE, source: KIND_ABSENT };
}

/**
 * The serpentine walk, decoded once at the customs post. Returns a frozen record whose `state`
 * is ALREADY DECIDED -- no consumer re-inspects the raw fields, and no consumer paints without
 * reading `state` first.
 *
 * 🔴 THE PRECEDENCE IS PART OF THE CONTRACT, NOT AN IMPLEMENTATION DETAIL. `truncated` is
 *    tested before the shape checks and before `pooled`, because a clipped pool must refuse
 *    for the reason it was clipped rather than for whatever the clipping happened to break
 *    downstream. `map2_index_ramp_harness.mjs` pins the order.
 *
 * 🔴 RANKS ARE CARRIED VERBATIM. The server normalised each map's base to 1 with the same
 *    function the scorer used. This side does not shift, re-rank or densify them -- and it
 *    must not, because the shift is min->1 rather than a dense re-rank, so a sparse numbering
 *    stays sparse ON PURPOSE. The gaps are a finding (a renumbering, a skipped die), and
 *    closing them here would erase the one thing this picture can say that no number can.
 *
 * @param {object} payload  the raw served payload
 * @param {Array<string>} rejected  the decoder's soft-reject list, appended to in place
 */
export function decodeIndexWalk(payload, rejected) {
  const rej = Array.isArray(rejected) ? rejected : [];
  const p = (payload && typeof payload === 'object') ? payload : null;
  const src = (p && p.sources && typeof p.sources === 'object') ? p.sources : null;
  const axis = (p && p.ruling && p.ruling.index_axis != null)
    ? String(p.ruling.index_axis) : null;
  const cells = arr(src && src.cells);
  const truncated = !!(src && src.truncated === true);
  const numbered = intOrNull(p && p.stats && p.stats.source_indices_usable);

  const refuse = (state, reason) => {
    // 🔴 ONLY A SELF-CONTRADICTING PAYLOAD IS A REFUSED FIELD. `rejected` is rendered to the
    //    operator as `payload fields refused: ...`, so putting the ordinary absences in it
    //    makes every older server and every multi-map unit read as a broken wire. Measured on
    //    the shell harness the moment this was written the other way: a payload that simply
    //    predates the field printed `payload fields refused: sources.cell_index:
    //    field_not_served` on a screen where nothing was wrong. An unnumbered unit, a clipped
    //    pool and a pooled unit are all facts the payload states elsewhere and the legend says
    //    in its own words -- they are not defects, and a warning that fires on honest payloads
    //    is one nobody reads by the end of the week.
    if (reason && state === INDEX_WALK_INCONSISTENT) {
      rej.push(`sources.cell_index: ${reason}`);
    }
    return Object.freeze({
      state, reason: reason || null, axis, truncated, numbered,
      cellCount: cells.length,
      ranks: Object.freeze([]), mapOf: Object.freeze([]), rankMax: null,
    });
  };

  // The server's own word for "no row carries a number". Nothing to offer, so no control.
  if (axis === INDEX_WALK_ABSENT) return refuse(INDEX_WALK_ABSENT, null);

  const rawIdx = src ? src.cell_index : undefined;
  // A THIRD case, and it is not one of the two nulls: the field was never served at all (an
  // older server). Unpaintable like `absent` and named apart from it, because "nobody numbered
  // these dies" and "this build does not ship the numbers" are different repairs.
  if (rawIdx === undefined) return refuse(INDEX_WALK_ABSENT, 'field_not_served');

  // 🔴 WHOLE-FIELD null == THE POOL WAS CLIPPED. Not a walk. Never painted.
  if (rawIdx === null) {
    if (!truncated) {
      return refuse(INDEX_WALK_INCONSISTENT,
        'whole field null but sources.truncated is false -- the wire contradicts itself');
    }
    return refuse(INDEX_WALK_TRUNCATED, null);
  }

  if (!Array.isArray(rawIdx) || rawIdx.length !== cells.length) {
    return refuse(INDEX_WALK_INCONSISTENT,
      `length ${Array.isArray(rawIdx) ? rawIdx.length : 'n/a'} against ${cells.length} cells`);
  }
  const rawMap = src ? src.cell_map : undefined;
  if (!Array.isArray(rawMap) || rawMap.length !== cells.length) {
    return refuse(INDEX_WALK_INCONSISTENT,
      `cell_map length ${Array.isArray(rawMap) ? rawMap.length : 'n/a'} against ${cells.length} cells`);
  }

  // 🔴 TWO MAPS IN ONE ARRAY ARE TWO WALKS. One ramp over both is the confidently-wrong
  //    picture; rank restarts at 1 per map, so the second map's colours would repeat the
  //    first's while sitting somewhere else entirely.
  const owners = new Set();
  for (const m of rawMap) owners.add(Number(m));
  if (owners.size > 1) {
    return refuse(INDEX_WALK_POOLED, `${owners.size} maps pooled into one walk`);
  }

  const ranks = new Array(rawIdx.length);
  let rankMax = null;
  for (let i = 0; i < rawIdx.length; i++) {
    const v = rawIdx[i];
    // ELEMENT null: this die is in the walk and carries no number. Kept as null, never zero --
    // `Number(null) === 0` would paint it as rank 1, which is a number the row never held.
    if (v === null || v === undefined) { ranks[i] = null; continue; }
    const n = Number(v);
    if (!Number.isInteger(n) || n < 1) {
      return refuse(INDEX_WALK_INCONSISTENT, `rank ${JSON.stringify(v)} at cell ${i} is not a rank`);
    }
    ranks[i] = n;
    if (rankMax === null || n > rankMax) rankMax = n;
  }
  // Every element null with the axis not saying `absent`: still nothing to paint, and the
  // absence is the fact rather than an empty ramp.
  if (rankMax === null) return refuse(INDEX_WALK_ABSENT, 'no cell carries a rank');

  return Object.freeze({
    state: INDEX_WALK_READY, reason: null, axis, truncated, numbered,
    cellCount: cells.length,
    ranks: Object.freeze(ranks),
    mapOf: Object.freeze(rawMap.map(Number)),
    // The ramp's DOMAIN. Not a re-derivation of the rank and not the same number as
    // `numbered`: the numbering may be sparse, so the largest rank and the count of numbered
    // dies legitimately differ, and neither is computed from the other.
    rankMax,
  });
}

function arr(v) { return Array.isArray(v) ? v : []; }

function msOrNull(v) {
  if (v === null || v === undefined || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? Math.round(n) : null;
}

function intOrNull(v) {
  if (v === null || v === undefined || v === '') return null;
  const n = Number(v);
  return Number.isInteger(n) ? n : null;
}

/**
 * 🔴 `Number(null) === 0`, `Number('') === 0` AND `Number(false) === 0`, so the obvious spelling
 *    of this function turns THREE ways of saying "nothing was measured" into a measured zero --
 *    which is the exact defect this round exists to remove, reintroduced inside its own fix.
 *    Same trap `verdict.finiteOrNull` documents for thresholds and `view_model.numOrNull` for
 *    the worklist totals; spelled the same way here rather than a fourth way.
 */
function numOrNull(v) {
  if (v === null || v === undefined || v === '' || typeof v === 'boolean') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function walk(node, path, visit, seen) {
  const marks = seen || new Set();
  if (node === null || node === undefined) return;
  if (typeof node !== 'object') {
    const dot = path.lastIndexOf('.');
    visit(path, node, dot >= 0 ? path.slice(dot + 1) : path);
    return;
  }
  if (marks.has(node)) return;
  marks.add(node);
  if (Array.isArray(node)) {
    node.forEach((v, i) => walk(v, `${path}[${i}]`, visit, marks));
    return;
  }
  for (const k of Object.keys(node)) walk(node[k], path ? `${path}.${k}` : k, visit, marks);
}
