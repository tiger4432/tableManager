// ═══════════════════════════════════════════════════════════════════════════════
// VIEW MODEL -- session + payload + verdict => exactly the strings and flags the screen shows.
// PURE. It does not know that a DOM exists; the composition root writes these strings into
// whatever elements the markup exposes.
//
// This file is where three MEASURED rules are enforced, rather than left to whoever writes the
// markup next:
//
// 🔴 1. NO PERCENTAGE REACHES THE VIEW. Not as a number, not as a tooltip, not as a sort key.
//       A coverage percentage was measured INVERTING the ranking: a correctly-oriented but
//       offset candidate scored 94% and ranked fourth, behind three wrongly-oriented ones. So
//       the screen carries two absolute counts and a margin in dies, and the denominator is
//       the point -- `일치 38 / 판별 40` and `일치 512 / 판별 528` are both "95%", and the
//       first is saying there are only forty dies of evidence here, which is the single most
//       decision-relevant fact on the screen. `assertNoRatio` below is a scorable statement of
//       this rule, not a comment about it.
//
// 🔴 2. A NUMERAL IS A CLAIM. In the COMPUTING and NOT-SCORABLE states every count renders
//       `미상`. Never `0`, never `-`, never a greyed-out figure. A `0` in an agreement column
//       is indistinguishable from a measured zero, and a measured zero would be a very loud
//       fact. This is the "plausible default impersonates a declaration" invariant applied to
//       the score column.
//
// 🔴 3. "NO ANSWER" IS NOT AN ERROR. Roughly half the map population cannot be aligned at all.
//       Anything styled as an error across half a population trains the operator to ignore the
//       styling, and then it also fails on the cases that are real. The three states get three
//       different tones -- neutral, plain, muted -- and none of them is danger red.
//
// NO DOM. NO TRANSPORT. NO MODULE-LEVEL MUTABLE STATE.
// ═══════════════════════════════════════════════════════════════════════════════

import { candidateGrid, candidateList, BADGE_WINNER, BADGE_STORED, INVERSION_FOOTNOTE } from './candidates.js';
import { VERDICT, REASON } from './verdict_bridge.js';
import { PHASE } from './session.js';

/** The four visible states. Three of them are named in the brief; WINNER is the fourth. */
export const VIEW_STATE = Object.freeze({
  IDLE: 'idle',
  COMPUTING: 'computing',
  SCORED_WINNER: 'scored_winner',
  SCORED_NO_WINNER: 'scored_no_winner',
  NOT_SCORABLE: 'not_scorable',
});

/** The one word for "a count we did not compute". Reused, not re-spelled. */
export const UNKNOWN = '미상';

// Vocabulary reused from what the system already says, so the screen does not grow synonyms
// for conditions that already have names.
export const WORDS = Object.freeze({
  alignUnavailable: '기준 없음',
  mappingUnavailable: '비교 불가',
  unknown: UNKNOWN,
  notDeclared: '선언 없음',
});

/**
 * @param {object} input
 * @param {object} input.session   from `createMapSession`
 * @param {object} input.verdict   from `verdict_bridge.decideVerdict`, or null while computing
 * @returns frozen view model
 */
export function buildViewModel(input) {
  const session = input.session;
  const verdict = input.verdict || null;
  const payload = session.payload || null;
  const state = resolveState(session, verdict);
  const numerals = state === VIEW_STATE.SCORED_WINNER || state === VIEW_STATE.SCORED_NO_WINNER;

  const scoringById = new Map();
  if (payload && Array.isArray(payload.per_candidate)) {
    for (const s of payload.per_candidate) {
      if (s && typeof s.candidate_id === 'string') scoringById.set(s.candidate_id, s);
    }
  }

  const storedId = payload && payload.stored_candidate_id ? payload.stored_candidate_id : null;
  const winnerId = state === VIEW_STATE.SCORED_WINNER && verdict ? verdict.winnerId : null;
  const selectedId = session.selectedCandidateId || winnerId || null;

  const cards = candidateList().map(c => buildCandidateCard({
    candidate: c, scoring: scoringById.get(c.id) || null,
    numerals, winnerId, storedId, selectedId, state,
  }));
  const cardById = new Map(cards.map(c => [c.id, c]));

  const vm = Object.freeze({
    state,
    numerals,
    headline: headlineFor(state, verdict),
    cause: causeFor(state, verdict, payload),
    // Aggregate exclusions, stated once and never shouted, never decorated per row.
    meta: metaLine(payload, numerals),
    picture: pictureModeFor(state),
    caption: captionFor(session, payload, selectedId),
    candidates: Object.freeze(cards),
    // Same eight, arranged as the operator's two motions: down is turning, across is flipping.
    grid: Object.freeze(candidateGrid().map(row => Object.freeze({
      rotation: row.rotation,
      degLabel: row.degLabel,
      cells: Object.freeze(row.cells.map(c => cardById.get(c.id))),
    }))),
    footnote: INVERSION_FOOTNOTE,
    selectedCandidateId: selectedId,
    // The two counts and the margin, for the summary strip under the grid.
    summary: summaryFor(selectedId, scoringById, verdict, numerals),
    secondMetric: secondMetricLine(payload, winnerId),
    confirm: confirmModel(session, selectedId, storedId, state),
    // Told out loud rather than assumed: nothing on the exploring path writes.
    writesSoFar: 0,
  });
  assertNoRatio(vm);
  return vm;
}

function resolveState(session, verdict) {
  if (session.phase === PHASE.IDLE) return VIEW_STATE.IDLE;
  if (session.phase === PHASE.COMPUTING) return VIEW_STATE.COMPUTING;
  if (session.phase === PHASE.FAILED) return VIEW_STATE.NOT_SCORABLE;
  if (!verdict) return VIEW_STATE.COMPUTING;
  if (verdict.kind === VERDICT.WINNER) return VIEW_STATE.SCORED_WINNER;
  if (verdict.kind === VERDICT.INDISTINGUISHABLE) return VIEW_STATE.SCORED_NO_WINNER;
  return VIEW_STATE.NOT_SCORABLE;
}

function buildCandidateCard(a) {
  const s = a.scoring;
  const badges = [];
  if (a.winnerId && a.candidate.id === a.winnerId) badges.push(BADGE_WINNER);
  if (a.storedId && a.candidate.id === a.storedId) badges.push(BADGE_STORED);
  const hasCounts = a.numerals && s
    && Number.isFinite(Number(s.agree)) && Number.isFinite(Number(s.discriminating));
  return Object.freeze({
    id: a.candidate.id,
    rotation: a.candidate.rotation,
    side: a.candidate.side,
    degLabel: a.candidate.degLabel,
    // Shown always, in mono: it is what the database holds and what every other screen
    // displays. Hiding it would make this screen speak a private language.
    storedLabel: a.candidate.id,
    agree: hasCounts ? Number(s.agree) : null,
    discriminating: hasCounts ? Number(s.discriminating) : null,
    countText: hasCounts ? agreementText(s.agree, s.discriminating) : UNKNOWN,
    badges: Object.freeze(badges),
    // Inert in COMPUTING and NOT-SCORABLE: listed so the operator can see the full set, but
    // there is nothing to select between.
    inert: !a.numerals,
    selected: a.selectedId === a.candidate.id,
  });
}

/** `일치 512 / 판별 528`. The denominator is not decoration; it is the evidence. */
export function agreementText(agree, discriminating) {
  return `일치 ${fmt(agree)} / 판별 ${fmt(discriminating)}`;
}

/** `Δ 47`. A die count is a physical quantity to a die engineer; a percentage point is not. */
export function marginText(marginDies) {
  return `Δ ${fmt(marginDies)}`;
}

function summaryFor(selectedId, scoringById, verdict, numerals) {
  if (!numerals) {
    return Object.freeze({ countText: UNKNOWN, marginText: UNKNOWN, hasNumerals: false });
  }
  const s = selectedId ? scoringById.get(selectedId) : null;
  const countText = s ? agreementText(s.agree, s.discriminating) : UNKNOWN;
  const margin = verdict && Number.isFinite(verdict.marginDies) ? verdict.marginDies : null;
  return Object.freeze({
    countText,
    // The NUMBER is carried beside the label so the composition root never has to parse a
    // formatted string back into a value -- re-reading your own output is how a display format
    // quietly becomes a data format.
    marginDies: margin,
    marginText: margin === null ? UNKNOWN : marginText(margin),
    hasNumerals: true,
  });
}

// ── LABELS ──────────────────────────────────────────────────────────────────────
// SHORT NOMINAL KOREAN. Labels are nouns, never sentences, and never assembled from a template
// plus a slot -- a template with a slot is how `~가 수행되었습니다` gets in almost by itself.
// The decoder emits a TOKEN and a COUNT; this table is the only place a word is chosen, and
// the composition root joins a label to a count with a separator rather than into a clause.
// Full sentences live in exactly one place on this screen, the confirm control, and the markup
// lane owns that string.
export const HEADLINE = Object.freeze({
  [VIEW_STATE.IDLE]: '대기',
  [VIEW_STATE.COMPUTING]: '채점 중',
  [VIEW_STATE.SCORED_WINNER]: '추천 있음',
  [VIEW_STATE.SCORED_NO_WINNER]: '구별 안 됨',
  [VIEW_STATE.NOT_SCORABLE]: '채점 불가',
});

// 🔴 THE TWO NO-WINNER CAUSES ARE DIFFERENT REPAIRS AND MUST NOT SHARE A LABEL.
//    `reference_no_values` means the reference carries no values to compare against -- the fix
//    is to plug a better reference. `reference_footprint_symmetric` means three candidates
//    genuinely occupy the same dies -- the fix is NOTHING, it is truly ambiguous. This file
//    used to render the symmetry wording for BOTH, which sends an operator to change a
//    reference that was never the problem.
export const CAUSE = Object.freeze({
  symmetric: '대칭 기준',
  reference_no_values: '기준 값 없음',
  no_reference: '기준 없음',
  thin_evidence: '판별 부족',
  no_thresholds: '기준값 없음',
  no_scorings: '점수 없음',
});

function headlineFor(state) {
  return HEADLINE[state] || HEADLINE[VIEW_STATE.COMPUTING];
}

/**
 * Returns a STRUCTURED cause, not a sentence: `{ token, count, detail }`.
 * `detail` is only ever the server's own refusal sentence, carried verbatim. This side never
 * composes a Korean equivalent when the payload already holds one -- a second copy of one
 * sentence is the two-spellings defect at its purest.
 */
function causeFor(state, verdict, payload) {
  const serverDetail = (verdict && verdict.refusalDetail)
    || (payload && payload.refusal_detail) || null;
  const reason = verdict ? verdict.reason : null;
  if (state === VIEW_STATE.NOT_SCORABLE) {
    // A server sentence always wins. It names which map is at fault and what to declare, and a
    // local equivalent would be a second spelling of one fact.
    if (serverDetail) return frozenCause(null, null, serverDetail);
    if (reason === REASON.NO_REFERENCE) return frozenCause(CAUSE.no_reference);
    if (reason === REASON.REFERENCE_NO_VALUES) return frozenCause(CAUSE.reference_no_values);
    if (reason === REASON.NO_THRESHOLDS) return frozenCause(CAUSE.no_thresholds);
    if (reason === REASON.TOO_FEW_DISCRIMINATING) {
      return frozenCause(CAUSE.thin_evidence, verdict.discriminating);
    }
    if (reason === REASON.NO_SCORINGS) return frozenCause(CAUSE.no_scorings);
    return frozenCause(CAUSE.no_reference);
  }
  if (state === VIEW_STATE.SCORED_NO_WINNER) {
    const n = verdict && Number.isFinite(verdict.tiedCount) ? verdict.tiedCount : null;
    if (reason === REASON.REFERENCE_FOOTPRINT_SYMMETRIC) return frozenCause(CAUSE.symmetric, n);
    if (reason === REASON.REFERENCE_NO_VALUES) return frozenCause(CAUSE.reference_no_values, n);
    if (reason === REASON.NO_REFERENCE) return frozenCause(CAUSE.no_reference, n);
    // MARGIN_TOO_SMALL with no more specific token: the candidates are close and we do not
    // know WHY. Saying nothing is the honest answer -- the headline already reports the tie,
    // and naming a cause we did not measure is how the operator gets sent to repair the wrong
    // thing. A null token renders as an empty cause line, not as a guess.
    return frozenCause(null, n);
  }
  return null;
}

function frozenCause(token, count, detail) {
  return Object.freeze({
    token: token || null,
    count: Number.isFinite(count) ? count : null,
    detail: detail || null,
  });
}

/** `맵 12개 중 5개 제외 (규격 미선언) · 채점 528다이 · 340ms` */
function metaLine(payload, numerals) {
  if (!payload) return '';
  const parts = [];
  const total = numOrNull(payload.map_count);
  const excluded = numOrNull(payload.excluded_map_count);
  if (total !== null && excluded !== null) {
    parts.push(excluded > 0
      ? `맵 ${total}개 중 ${excluded}개 제외 (${WORDS.notDeclared})`
      : `맵 ${total}개`);
  }
  const scored = numOrNull(payload.discriminating_dies);
  parts.push(numerals && scored !== null ? `채점 ${scored}다이` : `채점 ${UNKNOWN}`);
  const ms = numOrNull(payload.elapsed_ms);
  if (ms !== null) parts.push(`${ms}ms`);
  return parts.join(' · ');
}

function pictureModeFor(state) {
  switch (state) {
    case VIEW_STATE.COMPUTING: return 'skeleton';
    case VIEW_STATE.SCORED_WINNER:
    case VIEW_STATE.SCORED_NO_WINNER: return 'compare';
    case VIEW_STATE.NOT_SCORABLE: return 'alone';
    default: return 'empty';
  }
}

/**
 * The picture answers a different question depending on which source row has focus, and a
 * picture that silently changes its meaning is worse than no picture. So it is captioned,
 * always.
 */
function captionFor(session, payload, selectedId) {
  if (!payload) return '';
  const focused = session.focusedSourceId;
  if (focused === CROSS_SOURCE_ROW_ID) return '지금 보는 것: 출처 상호 일치';
  // Falls back to the source actually being drawn, not to the word "출처": the caption exists
  // because the picture answers a different question per focused row, and a caption that names
  // nothing is the failure it was added to prevent.
  const src = findSource(payload, focused)
    || (Array.isArray(payload.sources) ? payload.sources[0] : null);
  const name = src ? (src.label || src.id) : '출처';
  const cand = selectedId || (src && src.stored_candidate_id) || null;
  return cand
    ? `지금 보는 것: ${name} · ${cand} · 기준 대비`
    : `지금 보는 것: ${name} · 기준 대비`;
}

/** The cross-source row is the (N+1)th focusable row, not a new pane. */
export const CROSS_SOURCE_ROW_ID = '__cross_source__';

function findSource(payload, id) {
  if (!payload || !Array.isArray(payload.sources)) return null;
  return payload.sources.find(s => s && s.id === id) || null;
}

/**
 * The occupancy metric is computed but shown ONLY when it disagrees. A second metric that
 * agrees changes nothing and doubles the numerals on screen for zero decision value.
 */
function secondMetricLine(payload, winnerId) {
  if (!payload || !winnerId) return null;
  const other = payload.occupancy_winner_id || null;
  if (!other || other === winnerId) return null;
  return `두 지표가 다른 후보를 가리킵니다 - 값 일치는 ${winnerId}, 점유는 ${other}`;
}

/**
 * The single write. Two clauses on purpose: the first names the values, so a mis-click is
 * visible before it lands; the second names the consequence, so the operator knows what they
 * are underwriting. A wrong frame bakes an unverified rotation into stored coordinates and
 * nothing downstream looks wrong afterwards, which is why this one act gets friction at all.
 */
/**
 * The single write, as STRUCTURED VALUES rather than a composed sentence. The one full
 * sentence on this screen lives in the markup and the markup lane owns its wording; this
 * decoder supplies the eqp, the product and the chosen spelling that sentence names, so a
 * mis-click is visible before it lands without two lanes writing the same clause.
 */
function confirmModel(session, selectedId, storedId, state) {
  const enabled = (state === VIEW_STATE.SCORED_WINNER || state === VIEW_STATE.SCORED_NO_WINNER)
    && !!selectedId;
  const decision = session.decision || {};
  return Object.freeze({
    enabled,
    armed: session.armed === true && enabled,
    eqp: decision.eqp || null,
    product: decision.product || null,
    candidateId: selectedId || null,
    // Confirming an unchanged value is still a real act -- it is what records that a human
    // established the frame -- so the control must not read as a no-op.
    sameAsStored: !!selectedId && selectedId === storedId,
    note: selectedId && selectedId === storedId ? '현재 선언 동일' : '',
    // Enter must not be silently inert when nothing is marked.
    inertHint: state === VIEW_STATE.SCORED_NO_WINNER && !selectedId ? '후보 직접 선택' : '',
  });
}

/**
 * SCORABLE STATEMENT OF RULE 1. Walks the finished view model and throws if any string looks
 * like a ratio or any numeric field is a fraction between 0 and 1 under a ratio-ish name.
 * Called on every build, so a percentage cannot be introduced downstream without the shell
 * failing loudly the first time it renders.
 */
export function assertNoRatio(vm) {
  const bad = [];
  walk(vm, '', (path, value) => {
    if (typeof value === 'string' && /\d\s*%/.test(value)) bad.push(`${path} = ${value}`);
    if (/percent|pct|ratio|coverage|fitness|score_pct/i.test(path)) bad.push(`${path} (name)`);
  });
  if (bad.length > 0) {
    throw new Error(
      'a percentage reached the view model: ' + bad.join('; ')
      + '. Coverage ratios were measured inverting the ranking; carry counts and a margin.');
  }
  return true;
}

function walk(node, path, visit, seen) {
  const marks = seen || new Set();
  if (node === null || node === undefined) return;
  if (typeof node !== 'object') { visit(path, node); return; }
  if (marks.has(node)) return;
  marks.add(node);
  if (Array.isArray(node)) {
    node.forEach((v, i) => walk(v, `${path}[${i}]`, visit, marks));
    return;
  }
  for (const key of Object.keys(node)) {
    walk(node[key], path ? `${path}.${key}` : key, visit, marks);
  }
}

function fmt(n) {
  return Number.isFinite(Number(n)) ? String(Number(n)) : UNKNOWN;
}

function numOrNull(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}
