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

/**
 * Provenance of `referenceKind`. `inferred` is RETIRED: it is still exported so the harness
 * that scores the before/after comparison keeps importing, but `decodeReferenceView` can no
 * longer produce it. Two answers only -- the wire said so, or there was nothing to read.
 */
export const KIND_DECLARED = 'declared';
export const KIND_INFERRED = 'inferred';
export const KIND_ABSENT = 'absent';

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
  // previous wire, kept so a stale producer is refused rather than silently trimmed
  'agree', 'excluded_map_count', 'discriminating_dies',
]);

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
  // 🔴 THE WIRE SAYS `frame`, THE SCREEN SAYS `candidate_id`, AND THEY ARE THE SAME STRING.
  //    `rot90_front` is `candidates.candidateId(90, 'front')` exactly. The rename happens here
  //    and nowhere else -- one vocabulary crosses the customs post, and downstream keeps the
  //    spelling the database and every other screen already show.
  for (const raw of arr(p && p.candidates)) {
    const frame = raw && raw.frame != null ? String(raw.frame) : null;
    if (!frame) { rejected.push('candidates: no frame'); continue; }
    const agree = intOrNull(raw.agreement);
    const discriminating = intOrNull(raw.discriminating);
    if (agree === null || discriminating === null) {
      // Dropped, and SAID so. A scoring silently missing from the list would shrink the
      // denominator of "how many candidates tied" without anything on screen changing.
      rejected.push(`candidates ${frame}: agreement/discriminating not integers`);
      continue;
    }
    scorings.push(Object.freeze({ candidate_id: frame, agree, discriminating }));
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
    cellCount: intOrNull(s && s.cell_count),
  }));

  const decl = (p && p.declaration && typeof p.declaration === 'object') ? p.declaration : null;

  return Object.freeze({
    present: !!p,
    state: p && p.state ? String(p.state) : null,
    refusalDetail: p && p.refusal ? String(p.refusal) : null,
    // 🔴 A COUNT PER FRAME, NOT A WINNER. The unit's maps can disagree about what is declared,
    //    and picking a winner among declarations is a JUDGEMENT -- the client must not make
    //    it. The server already counts only DECLARED-provenance maps into `frames`, and counts
    //    everything else in `unattestedMaps`, so a unanimous-looking tally with a nonzero
    //    unattested count still reads as what it is: partly unmeasured.
    declaredFrameCounts: Object.freeze(Object.assign({}, (decl && decl.frames) || {})),
    attestedMaps: intOrNull(decl && decl.attested_maps),
    unattestedMaps: intOrNull(decl && decl.unattested_maps),
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
    // How many of the candidates the reference can actually tell apart, when the server
    // measured it. NULL when it did not -- an unmeasured count is reported as unmeasured and
    // never as zero, because zero would read as "none are blind", which is a claim.
    distinctSeatings: intOrNull(p && p.distinct_seatings),
    sources: Object.freeze(sources),
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
    referenceKind: d.referenceKind || REF_NONE,
    distinctSeatings: d.distinctSeatings,
  });
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
