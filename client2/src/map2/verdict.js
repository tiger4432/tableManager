// ═══════════════════════════════════════════════════════════════════════════════
// LAYER (7) VERDICT -- scores in, a decision out. Nothing else.
//
// (MAP_ALIGNMENT_SPEC 0.2 layer 7, sections 3 and 4.)
//
// 🔴 THE ONE RULE THIS FILE EXISTS FOR: when the margin is small, DO NOT RANK.
//    "항상 순위를 내는 도구는 무능을 인정하는 도구보다 나쁘다" -- three independent lenses
//    reached that conclusion the same day. A forced first place is a tool telling an operator
//    that something wrong is right, and the screen looks identical either way.
//
// DROP-IN FOR `verdict_placeholder.js`. Same three verdict tokens, same five reason tokens,
// same argument order, same frozen record shape -- so `verdict_bridge.js` changes exactly one
// import line, which is the entire reason that bridge exists. What is ADDED is described
// under "TWO CAUSES" below, and nothing is removed.
//
// ── TWO CAUSES, AND THE REASON THEY MUST NOT BE ONE ────────────────────────────
//
// Section 4: 「기준이 부족하다」 and 「후보가 진짜 비슷하다」 are different facts. Both end in
// "no ranking", and THE REPAIR IS DIFFERENT:
//
//   REFERENCE_NO_VALUES          the reference carries occupancy only. A wafer outline is a
//                                circle and a circle is invariant under all of D4, so a
//                                candidate cannot be told from its mirror by footprint alone.
//                                REPAIR: supply a reference that carries VALUES -- another
//                                map of the same wafer will do, and for the 320 maps with no
//                                valid-die map that is the only thing that will.
//
//   REFERENCE_FOOTPRINT_SYMMETRIC  values WERE available and the candidates still tie. The
//                                reference is not weak; these orientations genuinely put the
//                                same values on the same dies. REPAIR: a different reference
//                                map, or accept that this scope cannot be settled from data.
//
// Collapsing them into one message ("기준 발자국이 대칭입니다") sends an operator to fix the
// wrong thing. `blindCandidates` carries the measured count of candidates the reference
// cannot separate -- MEASURED by layer 5 from the actual die sets, never the spec's "6 of 8",
// which is a property of one reference and not of the method.
//
// ── BOTH THRESHOLDS, AND NEITHER SUBSTITUTING FOR THE OTHER ────────────────────
//
//   min_discriminating_dies   is there enough evidence to decide at all
//   min_margin_dies           is the winner far enough ahead of the runner-up
//
// A large margin over 3 discriminating dies is not a decision, and 500 discriminating dies
// with a 1-die margin is not a decision either. Both are evaluated, both are reported
// whichever fired, and `reasons` lists every one that fired so a caller cannot read one as
// standing in for the other.
//
// PASSED IN, ALWAYS. There is no default threshold here and there must not be one: a
// threshold invented in code is a plausible default impersonating a declaration (I4), which
// is the failure class this whole round is about. Absent thresholds produce NOT_SCORABLE.
//
// NO RATIO IS COMPUTED ANYWHERE IN THIS FILE. Not as an intermediate, not for sorting. The
// margin is a count of dies, because a die is a physical quantity to a die engineer and a
// percentage point is not.
//
// NO DOM. NO TRANSPORT. NO MODULE-LEVEL MUTABLE STATE.
// ═══════════════════════════════════════════════════════════════════════════════

// Reference kinds. Declared HERE and imported by the decoder, not the other way round: this
// module is the one that branches on them, and a token defined next to its only consumer
// cannot drift away from it.
//
// 🔴 THE CLIENT DOES NOT SCORE (ruling, 2026-08-05). The candidate transform lives on the
//    server, which already holds the cells; a JS re-spelling of `_frame_phys_params` would be
//    a second implementation of the one function whose subtlety has refuted two lead-PM
//    claims in 24 hours. So these tokens describe what the PAYLOAD says its reference was,
//    and this file never computes one.
export const REF_NONE = 'none';
export const REF_OCCUPANCY = 'occupancy';
export const REF_VALUES = 'values';

export const VERDICT = Object.freeze({
  WINNER: 'winner',
  INDISTINGUISHABLE: 'indistinguishable',
  NOT_SCORABLE: 'not_scorable',
});

// Reason CODES, not sentences. The composition root turns a code into Korean; the server's own
// refusal sentence is passed through verbatim and is never re-spelled on this side.
//
// The first five are byte-identical to `verdict_placeholder.REASON` and are unchanged. The
// rest are the section 4 causes and the layer 5 refusals, which had nowhere to go before.
export const REASON = Object.freeze({
  NO_THRESHOLDS: 'no_thresholds',
  NO_SCORINGS: 'no_scorings',
  TOO_FEW_DISCRIMINATING: 'too_few_discriminating',
  MARGIN_TOO_SMALL: 'margin_too_small',
  SERVER_REFUSED: 'server_refused',
  // added -- section 4's two causes, kept apart because the repair differs
  NO_REFERENCE: 'no_reference',
  REFERENCE_NO_VALUES: 'reference_no_values',
  REFERENCE_FOOTPRINT_SYMMETRIC: 'reference_footprint_symmetric',
  // added -- layer 5 refused to score at all
  SOURCE_REFUSED: 'source_refused',
});

/**
 * The existing honest-degradation vocabulary, mapped rather than extended.
 *
 * These four words are already load-bearing elsewhere (`bonding_plan.STATUS_NOT_DECLARED`,
 * `bonding_plan.BINDING_MAPPING_UNAVAILABLE`, `connected(align_unavailable)` at
 * `bonding_plan.py:762`, and `column_filter`'s `미상`). A consumer downgrading on our verdict
 * needs a word it already understands; inventing a sixth would be a contract change dressed
 * up as a message (`config_resolve_report.py:404` says exactly this).
 *
 * 🔴 THIS IS A MAPPING, NOT A NEW VOCABULARY. If a consumer disagrees with a row here, the
 *    row moves -- no new token is minted.
 */
export const DEGRADATION = Object.freeze({
  [REASON.NO_REFERENCE]: 'align_unavailable',
  [REASON.SERVER_REFUSED]: 'mapping_unavailable',
  [REASON.SOURCE_REFUSED]: 'mapping_unavailable',
  [REASON.NO_THRESHOLDS]: 'not_declared',
  [REASON.NO_SCORINGS]: 'align_unavailable',
  [REASON.TOO_FEW_DISCRIMINATING]: 'align_unavailable',
  [REASON.MARGIN_TOO_SMALL]: '미상',
  [REASON.REFERENCE_NO_VALUES]: '미상',
  [REASON.REFERENCE_FOOTPRINT_SYMMETRIC]: '미상',
});

/** The word a consumer should degrade to for a verdict, or null when there is nothing to say. */
export function degradationFor(verdict) {
  if (!verdict || !verdict.reason) return null;
  return DEGRADATION[verdict.reason] || null;
}

/**
 * @param {Array<{candidate_id:string, agree:number, discriminating:number}>} scorings
 * @param {{min_margin_dies:number, min_discriminating_dies:number}} thresholds  PASSED IN.
 * @param {object} [context]
 *        `refusalDetail`     a server sentence, passed through verbatim
 *        `referenceKind`     `scoring.REF_NONE|REF_OCCUPANCY|REF_VALUES`
 *        `distinctSeatings`  how many of the candidates the reference can tell apart
 *        `sourceRefusal`     layer 5's refusal token, if it refused
 */
export function decideVerdict(scorings, thresholds, context) {
  const ctx = context || {};

  const detail = ctx.refusalDetail ? String(ctx.refusalDetail) : '';
  if (detail) return frozen(VERDICT.NOT_SCORABLE, REASON.SERVER_REFUSED, { refusalDetail: detail });
  if (ctx.sourceRefusal) {
    return frozen(VERDICT.NOT_SCORABLE, REASON.SOURCE_REFUSED, { refusalDetail: String(ctx.sourceRefusal) });
  }
  // A reference that is absent is not a low score; it is a different question. Section 4:
  // 「기준이 없으면 계산은 되고 순위는 안 낸다」.
  if (ctx.referenceKind === REF_NONE) return frozen(VERDICT.NOT_SCORABLE, REASON.NO_REFERENCE, {});

  const usable = (Array.isArray(scorings) ? scorings : []).filter(isScorable);
  if (usable.length === 0) return frozen(VERDICT.NOT_SCORABLE, REASON.NO_SCORINGS, {});

  const minMargin = finiteOrNull(thresholds && thresholds.min_margin_dies);
  const minDiscriminating = finiteOrNull(thresholds && thresholds.min_discriminating_dies);
  if (minMargin === null || minDiscriminating === null) {
    return frozen(VERDICT.NOT_SCORABLE, REASON.NO_THRESHOLDS, {});
  }

  // Rank by agreement over the discriminating subset. `candidate_id` is the tiebreak so the
  // order is total and stable -- two candidates on identical counts must not swap places
  // between two renders of the same payload.
  const ranked = usable.slice().sort((a, b) => (
    b.agree - a.agree || String(a.candidate_id).localeCompare(String(b.candidate_id))
  ));
  const rankedIds = Object.freeze(ranked.map(s => s.candidate_id));
  const top = ranked[0];
  const runnerUp = ranked[1] || null;
  const marginDies = runnerUp ? top.agree - runnerUp.agree : top.agree;
  const discriminating = top.discriminating;

  const blind = blindCandidates(ctx, usable.length);

  // Both thresholds are evaluated. `reasons` carries every one that fired so that a reader
  // cannot mistake one for the other; `reason` is the first, for the single-slot consumers.
  const reasons = [];
  if (discriminating < minDiscriminating) reasons.push(REASON.TOO_FEW_DISCRIMINATING);
  if (marginDies < minMargin) reasons.push(REASON.MARGIN_TOO_SMALL);

  const shared = {
    rankedIds, discriminating, marginDies, minMargin, minDiscriminating,
    blindCandidates: blind, reasons: Object.freeze(reasons.slice()),
  };

  if (reasons.includes(REASON.TOO_FEW_DISCRIMINATING)) {
    // There is not enough evidence to decide at all -- a different state from "the evidence
    // is good and the candidates tie". Kept as NOT_SCORABLE because the shipped view already
    // names this quantity in that state (`view_model.causeFor`), and because "we scored"
    // would be a claim about evidence that does not exist.
    return frozen(VERDICT.NOT_SCORABLE, REASON.TOO_FEW_DISCRIMINATING, shared);
  }

  if (reasons.includes(REASON.MARGIN_TOO_SMALL)) {
    // Scored, and the honest answer is that these are not distinguishable. Not an error, and
    // no candidate carries a badge -- the ABSENCE of a mark is the answer.
    const tiedCount = ranked.filter(s => top.agree - s.agree < minMargin).length;
    const cause = ctx.referenceKind === REF_OCCUPANCY
      ? REASON.REFERENCE_NO_VALUES
      : REASON.REFERENCE_FOOTPRINT_SYMMETRIC;
    return frozen(VERDICT.INDISTINGUISHABLE, cause,
      Object.assign({}, shared, { tiedCount, reasons: Object.freeze(reasons.concat([cause]))
      }));
  }

  return frozen(VERDICT.WINNER, null, Object.assign({}, shared, { winnerId: top.candidate_id }));
}

/**
 * Convenience over a whole `scoring.scoreSources` result: one verdict per source, with the
 * context filled from what layer 5 measured rather than from what a caller remembered to pass.
 * A context assembled by hand at each call site is how two callers start disagreeing about
 * what "no reference" meant.
 */
export function decideForSources(scoringResult, thresholds, context) {
  const res = scoringResult || {};
  const base = context || {};
  return Object.freeze((res.sources || []).map(s => Object.freeze({
    sourceId: s.sourceId,
    verdict: decideVerdict(s.candidates, thresholds, Object.assign({}, base, {
      referenceKind: s.referenceKind,
      distinctSeatings: s.distinctSeatings,
      sourceRefusal: s.refusal || null,
    })),
  })));
}

/**
 * How many candidates the reference cannot separate, MEASURED. `distinctSeatings` is the
 * number of distinct die-sets the candidates produce; anything beyond the first in a group is
 * blind. Null when layer 5 did not report it -- an unmeasured count is reported as unmeasured,
 * never as zero.
 */
function blindCandidates(ctx, candidateCount) {
  const d = Number(ctx.distinctSeatings);
  if (!Number.isFinite(d) || d <= 0) return null;
  return Math.max(0, candidateCount - d);
}

function isScorable(s) {
  return !!s
    && Number.isFinite(Number(s.agree))
    && Number.isFinite(Number(s.discriminating))
    && typeof s.candidate_id === 'string';
}

/**
 * 🔴 `Number(null) === 0` AND `Number('') === 0`, SO THE OBVIOUS SPELLING OF THIS FUNCTION
 *    TURNS A MISSING THRESHOLD INTO A THRESHOLD OF ZERO -- and a threshold of zero means
 *    "always rank", which is the exact behaviour the no-default rule exists to prevent. That
 *    is I4 (a plausible default impersonating a declaration) living inside the guard against
 *    I4. Measured, not reasoned: with `finiteOrNull = v => Number.isFinite(Number(v)) ? ... `,
 *    `decideVerdict(scorings, null, ctx)` returns a WINNER instead of `no_thresholds`.
 *    `verdict_placeholder.js:102-105` carries that spelling today -- reported, not silently
 *    diverged from.
 */
function finiteOrNull(v) {
  if (v === null || v === undefined || v === '' || typeof v === 'boolean') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function frozen(kind, reason, extra) {
  return Object.freeze({
    kind,
    reason: reason || null,
    winnerId: extra.winnerId || null,
    rankedIds: extra.rankedIds || Object.freeze([]),
    marginDies: Number.isFinite(extra.marginDies) ? extra.marginDies : null,
    discriminating: Number.isFinite(extra.discriminating) ? extra.discriminating : null,
    minMargin: Number.isFinite(extra.minMargin) ? extra.minMargin : null,
    minDiscriminating: Number.isFinite(extra.minDiscriminating) ? extra.minDiscriminating : null,
    tiedCount: Number.isFinite(extra.tiedCount) ? extra.tiedCount : null,
    refusalDetail: extra.refusalDetail || null,
    // added by this module; absent on the placeholder, so a consumer must tolerate null
    blindCandidates: Number.isFinite(extra.blindCandidates) ? extra.blindCandidates : null,
    reasons: extra.reasons || Object.freeze([]),
    degrade: reason ? (DEGRADATION[reason] || null) : null,
  });
}
