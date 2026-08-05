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
import { PHASE, BINDING_FALLBACK_GUESS, BINDING_NONE } from './session.js';

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
  // The worklist's three row states and the two aggregate badges. Nominal register, one word
  // each, and no row below the boundary gets a word of its own -- see `worklistModel`.
  unscorable: '채점 불가',
  confirmed: '확정됨',
  pending: '미확정',
  remaining: '잔여',
  thisSession: '이번 세션',
  maps: '맵',
  // The payload answered ONE alignment question and did not say which column pair it read.
  columnsUnstated: '컬럼 미표기',
  // A pre-filled pair nobody has agreed to. Marked everywhere it appears, never flattened.
  proposed: '제안',
  xColumn: 'x 컬럼',
  yColumn: 'y 컬럼',
  valueColumn: 'value 컬럼',
  targetTable: '대상 테이블',
  // One line, and it is a LABEL: the screen says the two metrics disagree, the console says
  // which candidate each one chose. Diagnosis is not a decision.
  metricConflict: '지표 불일치',
});

/**
 * WHICH COLUMN PAIR THE SCORINGS BELONG TO.
 *
 * 🔴 `UNSTATED` IS THE HONEST STATE TODAY, NOT A BUG IN THIS FILE. `dt_log` carries two
 *    coordinate pairs, the server picks one from its OWN overlay binding
 *    (`server/map_alignment.py:445-449`, used at `:468-479` and `:600-604`), the route takes no
 *    column parameter (`server/main.py:4160-4168`), and the response's `unit` block
 *    (`map_alignment.py:677`) echoes rule / decision_key / source_table / map_table and NO
 *    column names. So when the table offers more than one pair, the payload cannot say which
 *    one it read. Rendering that measurement under whichever pair the operator selected would
 *    assert an attribution nobody performed. It is named instead; the fix is two echoed fields
 *    on the wire.
 *
 * `UNAMBIGUOUS` is not a weaker `DECLARED`: with one pair available there is nothing to confuse
 * it with. Before a table's schema is known the screen is not claiming a pair at all.
 */
export const ATTRIBUTION = Object.freeze({
  UNAMBIGUOUS: 'unambiguous',
  DECLARED: 'declared',
  UNSTATED: 'unstated',
});

/**
 * What the run can answer AT ALL, which the value column decides.
 *
 * 🔴 OCCUPANCY IS MEASURED FLAT AND MUST NOT READ AS AN ORDINARY INCONCLUSIVE RUN. Eight
 *    candidates inside four points, and one production case has all eight occupying the SAME
 *    dies -- an 8-way tie on a question that value agreement settles by 374 dies. "We could not
 *    tell them apart" and "we were never able to tell them apart" are different sentences with
 *    different repairs: the second is repaired by naming a value column, the first by nothing.
 *    The payload already draws this line as `reference.kind`, so it is read there.
 */
export const EVIDENCE = Object.freeze({
  NONE: 'none',
  OCCUPANCY: 'occupancy',
  VALUES: 'values',
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
  const attribution = attributionFor(session, payload);
  const evidence = evidenceFor(session, payload);
  // A measured result exists AND it is safe to say whose it is. The second clause is not a
  // refinement of the first: with two coordinate pairs in play and nothing on the wire naming
  // which one was read, the counts are real and their owner is not known.
  const numerals = (state === VIEW_STATE.SCORED_WINNER || state === VIEW_STATE.SCORED_NO_WINNER)
    && attribution.state !== ATTRIBUTION.UNSTATED;

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
    attribution,
    evidence,
    // The three set-up controls, as OPTIONS AND A SELECTION -- never as composed labels. The
    // view joins a name to a separator; this layer only ever hands over values.
    question: questionModel(session, attribution),
    // One served page plus the server's own totals. Nothing here counts the loaded rows and
    // calls the answer a population.
    worklist: worklistModel(session),
    headline: headlineFor(state, verdict),
    cause: causeFor(state, verdict, payload, attribution, evidence),
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
    // FOR THE LOG ONLY. Nothing writes this to a node -- see `renderSecondMetric`.
    secondMetricDetail: secondMetricDetail(payload, winnerId),
    confirm: confirmModel(session, selectedId, storedId, state, attribution),
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
function causeFor(state, verdict, payload, attribution, evidence) {
  const serverDetail = (verdict && verdict.refusalDetail)
    || (payload && payload.refusal_detail) || null;
  const reason = verdict ? verdict.reason : null;
  // An unattributable answer outranks every scored cause: the counts may be perfect and still
  // belong to a column pair nobody named. Said with a token, never with an invented sentence.
  if (attribution && attribution.state === ATTRIBUTION.UNSTATED
      && state !== VIEW_STATE.COMPUTING && state !== VIEW_STATE.IDLE) {
    return frozenCause(WORDS.columnsUnstated, attribution.pairCount, serverDetail);
  }
  // 🔴 A TIE WITH NO VALUES IS NOT THE SAME EVENT AS A TIE WITH THEM. Occupancy alone was
  //    measured flat -- one production case has all eight candidates on the SAME dies -- so an
  //    inconclusive occupancy run must name its own thinness rather than borrowing the wording
  //    of a genuine ambiguity. The repairs differ: name a value column, versus nothing.
  if (evidence && evidence.occupancyOnly && state === VIEW_STATE.SCORED_NO_WINNER) {
    const tied = verdict && Number.isFinite(verdict.tiedCount) ? verdict.tiedCount : null;
    return frozenCause(CAUSE.reference_no_values, tied, serverDetail);
  }
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

// ── THE QUESTION ────────────────────────────────────────────────────────────────

/**
 * Three option lists and three selections. OPTIONS ARE VALUES WITH LABELS, never strings this
 * layer assembled: the view joins a name to a count with a separator, and a decoder that only
 * ever emits a value and a label cannot produce a template-plus-slot clause.
 *
 * 🔴 THE REFERENCE LIST ALWAYS CARRIES 기준 없음, AS ITS FIRST OPTION AND AS A REAL VALUE.
 *    The maps that need aligning are exactly the ones with no valid-die reference, so the
 *    commonest correct answer must not read as the empty state of a picker. Only references
 *    the catalog says RESOLVE are listed beside it -- the eight declared `valid_die_ref` rows
 *    that resolve zero times are not offered, because offering a name that cannot work teaches
 *    the operator to distrust the control.
 */
function questionModel(session, attribution) {
  const q = session.question || {};
  const cat = session.catalog || {};
  const cols = q.columns || {};
  const tables = Array.isArray(cat.tables) ? cat.tables : [];
  const names = (cat.columns && Array.isArray(cat.columns[q.mapTable])) ? cat.columns[q.mapTable] : [];
  const types = (cat.columnTypes && cat.columnTypes[q.mapTable]) || {};
  // 🔴 A COORDINATE IS A NUMBER, AND THE SCHEMA DECLARES WHICH COLUMNS ARE. `/tables/{t}/schema`
  //    serves `column_types`, and `dt_map` declares `graph_synced_at: datetime` beside
  //    `dt_x: number`. Offering a datetime as an x column is the same failure as offering a
  //    reference that cannot resolve -- it teaches the operator that the control lies. The
  //    filter rests on the DECLARATION, never on a name pattern, and if a table declares no
  //    numeric column at all nothing is filtered: then we do not know, rather than know it is
  //    empty. The VALUE column is NOT filtered -- `c_bn` is a bin code, declared `string`.
  const coordNames = numericOnly(names, types);
  const refList = (cat.references && Array.isArray(cat.references[q.mapTable]))
    ? cat.references[q.mapTable] : [];
  const proposed = q.bindingSource === BINDING_FALLBACK_GUESS;

  return Object.freeze({
    // THE PRIMITIVE TUPLE, carried as values. Nothing downstream reconstructs it from a name.
    mapTable: q.mapTable || null,
    xCol: cols.x || null,
    yCol: cols.y || null,
    valCol: cols.val || null,
    reference: q.reference || null,
    tables: Object.freeze(tables.map(t => option(t.table, t.label || t.table, t.table === q.mapTable))),
    // The table's REAL columns. No column name is written down in this file.
    xOptions: Object.freeze(coordNames.map(n => option(n, n, n === cols.x))),
    yOptions: Object.freeze(coordNames.map(n => option(n, n, n === cols.y))),
    // The value column leads with its own absence, because choosing nothing is a real choice
    // with a consequence, not an unfilled field.
    valueOptions: Object.freeze([option('', WORDS.notDeclared, !cols.val)].concat(
      names.map(n => option(n, n, n === cols.val)))),
    references: Object.freeze([option('', WORDS.alignUnavailable, !q.reference)].concat(
      refList.map(r => option(r.value, r.label || r.value, r.value === q.reference)))),
    askable: !!(q.mapTable && cols.x && cols.y),
    // 🔴 A PROPOSAL IS CARRIED AS A FLAG ALL THE WAY TO THE SCREEN. The view marks it; the
    //    confirm control refuses to rest on it. Flattening this into "the pair is set" is the
    //    exact failure this field exists to prevent.
    bindingIsGuess: proposed,
    bindingSource: q.bindingSource || BINDING_NONE,
    proposalWord: proposed ? WORDS.proposed : '',
    attributionState: attribution ? attribution.state : ATTRIBUTION.UNAMBIGUOUS,
  });
}

/** Declared-numeric columns, or every column when the table declares no numeric one. */
function numericOnly(names, types) {
  const numeric = names.filter(n => String(types[n] || '').toLowerCase() === 'number');
  return numeric.length > 0 ? numeric : names;
}

function option(value, label, selected) {
  return Object.freeze({ value: String(value), label: String(label), selected: selected === true });
}

/**
 * Can this answer be attributed to the pair the operator chose? Only when the table offers no
 * more than one pair, or when the payload said so itself.
 */
function attributionFor(session, payload) {
  const q = session.question || {};
  const cat = session.catalog || {};
  const names = (cat.columns && Array.isArray(cat.columns[q.mapTable])) ? cat.columns[q.mapTable] : [];
  const pairs = countCoordinatePairs(names);
  const echoed = payload && payload.answered_columns ? payload.answered_columns : null;
  if (echoed && echoed.x && echoed.y) {
    return frozenAttribution(ATTRIBUTION.DECLARED, echoed, pairs);
  }
  if (pairs <= 1) return frozenAttribution(ATTRIBUTION.UNAMBIGUOUS, null, pairs);
  return frozenAttribution(ATTRIBUTION.UNSTATED, null, pairs);
}

/**
 * How many x/y pairs this table could be read through. Counted from the SERVED column names,
 * so a table that grows a second pair becomes ambiguous without anyone editing this file.
 * A name is an x if it is `x` or ends in `_x`; the y for that pair is the same name with the
 * suffix swapped, and it must actually exist -- a lone `dt_x` is not a pair.
 */
export function countCoordinatePairs(columnNames) {
  const names = Array.isArray(columnNames) ? columnNames.map(String) : [];
  const has = new Set(names);
  let pairs = 0;
  for (const name of names) {
    const lower = name.toLowerCase();
    if (lower !== 'x' && !lower.endsWith('_x')) continue;
    const y = name.slice(0, name.length - 1) + (name.endsWith('X') ? 'Y' : 'y');
    if (has.has(y)) pairs++;
  }
  return pairs;
}

function frozenAttribution(state, columns, pairCount) {
  return Object.freeze({
    state,
    columns: columns ? Object.freeze({ x: columns.x, y: columns.y }) : null,
    pairCount: Number.isFinite(pairCount) ? pairCount : 0,
  });
}

/**
 * What the run could answer at all. Read off the payload's own `reference.kind`, never derived
 * from the shape of the cells -- an inference kept beside a declaration is a second
 * implementation of one fact, and the day they disagree the screen is confident and wrong.
 */
function evidenceFor(session, payload) {
  const kind = payload && payload.reference_kind ? payload.reference_kind : null;
  const asked = session.question && session.question.columns && session.question.columns.val;
  if (kind === EVIDENCE.VALUES) return frozenEvidence(EVIDENCE.VALUES, !!asked);
  if (kind === EVIDENCE.OCCUPANCY) return frozenEvidence(EVIDENCE.OCCUPANCY, !!asked);
  return frozenEvidence(EVIDENCE.NONE, !!asked);
}

function frozenEvidence(kind, valueColumnChosen) {
  return Object.freeze({
    kind,
    valueColumnChosen: valueColumnChosen === true,
    // A tie under occupancy-only evidence is a DIFFERENT statement from a tie under values,
    // and the view says which -- see `causeFor`.
    occupancyOnly: kind === EVIDENCE.OCCUPANCY,
  });
}

// ── THE WORKLIST ────────────────────────────────────────────────────────────────

/**
 * One served page, plus the server's OWN totals.
 *
 * 🔴 THE BADGES ARE NOT COUNTED FROM THE ROWS ON SCREEN. A page is not a population: counting
 *    the loaded rows would make `잔여 41건` mean "41 of them fit in the first page", which is a
 *    numeral making a claim nobody measured. When the server did not send a total, the badge
 *    reports `미상` -- the same rule the score columns follow.
 *
 * 🔴 ROWS BELOW THE BOUNDARY CARRY NO PER-ROW DECORATION. Roughly half the population lands
 *    there (320 of 668 metas are auto-registered and refused). Decorating half a list trains
 *    the eye past the decoration, after which it also fails on the cases that are real. One
 *    aggregate badge says how many, and the boundary says where they start.
 */
function worklistModel(session) {
  const wl = session.worklist || {};
  const rows = Array.isArray(wl.rows) ? wl.rows : [];
  const above = [];
  const below = [];
  for (const row of rows) {
    const unscorable = row.scorable === false || row.state === 'unscorable';
    // 🔴 THE LABEL IS THE SERVER'S OWN `unit_key`, NOT A STRING THIS FILE COMPOSES. The unit's
    //    identity is composed by `frame_confirmation.compose_unit_key` from the rule's declared
    //    decision key; re-joining the parts here with a separator of our choosing would be a
    //    second spelling of one identity, and the two would drift the day a rule gains a third
    //    key column. `key` is that same identity as a dict, and it is what the request takes.
    const keyDict = row.key && typeof row.key === 'object' ? row.key : null;
    const values = keyDict ? Object.keys(keyDict).map(k => keyDict[k]) : [];
    (unscorable ? below : above).push(Object.freeze({
      unitKey: row.unit_key == null ? '' : String(row.unit_key),
      keyDict,
      // Kept for the surfaces that still name the two axes of today's rule.
      eqp: row.eqp == null ? (values[0] == null ? '' : String(values[0])) : String(row.eqp),
      product: row.product == null ? (values[1] == null ? '' : String(values[1])) : String(row.product),
      state: unscorable ? 'unscorable' : (row.state === 'confirmed' ? 'confirmed' : 'pending'),
      // A word for the two states above the boundary; NOTHING for the ones below it.
      stateWord: unscorable ? '' : (row.state === 'confirmed' ? WORDS.confirmed : WORDS.pending),
      mapCount: numOrNull(row.map_count),
      // `confirmation` is a served record, so "confirmed" is read, never inferred from a badge.
      confirmed: !!row.confirmation,
      selected: !!session.decision
        && session.decision.__unitKey === (row.unit_key == null ? '' : String(row.unit_key)),
    }));
  }
  return Object.freeze({
    rows: Object.freeze(above),
    unscorableRows: Object.freeze(below),
    query: wl.query || '',
    served: wl.served === true,
    // Server totals only. `null` renders `미상`, never a page-local substitute.
    remaining: numOrNull(wl.remaining),
    unscorable: numOrNull(wl.unscorable),
    total: numOrNull(wl.total),
    confirmedThisSession: session.confirmedCount,
    // The boundary is a place, so it only exists when something is below it.
    boundaryVisible: below.length > 0,
    empty: wl.served === true && rows.length === 0,
    error: wl.error || null,
  });
}

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
  // 🔴 THE SCREEN GETS A LABEL; THE CONSOLE GETS THE WHOLE THING. This was a full sentence
  //    naming both candidates. Nothing on screen may run past one line, and the audience are
  //    administrators who read the console for diagnosis -- so the fact that the two metrics
  //    disagree is what changes the decision, and WHICH candidate each one picked is diagnosis.
  return WORDS.metricConflict;
}

/** The same fact, whole, for the log. Never rendered. */
function secondMetricDetail(payload, winnerId) {
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
function confirmModel(session, selectedId, storedId, state, attribution) {
  const q = session.question || {};
  const cols = q.columns || {};
  // 🔴 THE WRITE MAY NOT REST ON A PROPOSAL OR ON AN UNATTRIBUTED ANSWER. Reading stays
  //    frictionless -- a proposed pair still asks the question and still draws the picture --
  //    but a confirmation bakes an unverified rotation into stored coordinates and nothing
  //    downstream looks wrong afterwards. So the one act that cannot be taken back is the one
  //    act that requires the pair to have been agreed and the answer to have an owner.
  const restsOnGuess = q.bindingSource === BINDING_FALLBACK_GUESS
    || (attribution && attribution.state === ATTRIBUTION.UNSTATED);
  const enabled = (state === VIEW_STATE.SCORED_WINNER || state === VIEW_STATE.SCORED_NO_WINNER)
    && !!selectedId && !restsOnGuess;
  const decision = session.decision || {};
  return Object.freeze({
    enabled,
    // The primitive tuple the operator actually looked at, carried into the record.
    mapTable: q.mapTable || null,
    xCol: cols.x || null,
    yCol: cols.y || null,
    valCol: cols.val || null,
    reference: q.reference || null,
    restsOnGuess,
    armed: session.armed === true && enabled,
    eqp: decision.eqp || null,
    product: decision.product || null,
    candidateId: selectedId || null,
    // Confirming an unchanged value is still a real act -- it is what records that a human
    // established the frame -- so the control must not read as a no-op.
    sameAsStored: !!selectedId && selectedId === storedId,
    note: selectedId && selectedId === storedId ? '현재 선언 동일' : '',
    // Enter must not be silently inert when nothing is marked. Each reason gets its own words:
    // "pick one" and "agree to the columns first" are different instructions.
    inertHint: hintFor(state, selectedId, q, attribution),
  });
}

function hintFor(state, selectedId, question, attribution) {
  if (question.bindingSource === BINDING_FALLBACK_GUESS) return `${WORDS.proposed} · 컬럼 확인 필요`;
  if (question.bindingSource === BINDING_NONE) return '컬럼 선택 필요';
  if (attribution && attribution.state === ATTRIBUTION.UNSTATED) return WORDS.columnsUnstated;
  if (state === VIEW_STATE.SCORED_NO_WINNER && !selectedId) return '후보 직접 선택';
  return '';
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

/**
 * 🔴 `Number(null) === 0` AND `Number('') === 0`. This function used to hand both back as a
 *    measured zero, which is the exact defect class the verdict layer was hardened against: an
 *    absent count wearing the clothes of a declared one. It reached the worklist badges as
 *    `잔여 · 0건` on a response that had sent no total at all -- a numeral making a claim
 *    nobody measured. Absence is checked BEFORE the coercion, never after.
 */
function numOrNull(v) {
  if (v === null || v === undefined || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}
