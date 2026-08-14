// ============================================================
// contrast_core.js — 마킹한 랏들이 «무엇이 다른가»를 모델로.
//
// PURE. No DOM, no network, no `window` — same contract as `surprise_core.js`,
// so it COULD be driven under bare node the way the other cores are.
//
// 🔴 IT IS NOT. There is no `tests/contrast_harness.mjs` — this comment claimed one
// existed, which is a claim of coverage that does not exist and is worse than
// saying nothing. This panel is currently scored by nobody; writing that harness is
// outstanding work, not done work.
//
// 🔴 WHY THIS EXISTS AT ALL. Marking five lots used to produce 125 wafer maps
// stacked into 12,283px of vertical scroll and no comparison anywhere. A pile of
// pictures is not an answer to "what is different about these five" — it is the
// question restated once per wafer. THE OUTPUT OF MULTI-MARKING IS THE CONTRAST.
// One wafer deserves a picture; five lots deserve a ranked list of what separates
// them from everything else.
//
// ------------------------------------------------------------
// 🔴 THE LANDED CONTRACT — measured live against the running stack 2026-08-14,
// `GET /api/ledger/siblings?mode=contrast&scope=<axis>:<v>[,<v>…]`. ONE endpoint,
// two framings: `mode` is a parameter and there is deliberately no second route.
// `finding` is a parameter from the first line too.
//
//   -> { state, engine: "walk", mode, finding, generated_at, window,
//        scope: { declared, axis, axis_label, values[], relation, column,
//                 case:    {subjects, units, found_units, found_rate, found_rate_of},
//                 control: {…same…},
//                 excluded: [{bucket, label, subjects, state, message}] },
//        subject: {type, key, column, unit_label},
//        gates: [{id, label, basis, doc}],          // THE GATE AXIS, DECLARED
//        candidates: [ { candidate_key, predicate, field, value, axis, label,
//                        about, compare, unit,
//                        case:    {n, of, rate, attributed_of, rate_attributed, coverage},
//                        control: {…same…},
//                        enrichment, enrichment_ci: [lo, hi], enrichment_state,
//                        enrichment_basis, rate_delta, reason,
//                        evidence_refs: [{relation, key_column, key, population}],
//                        evidence_ref_count,
//                        gates: { <gate id>: {verdict, basis, reason, message, detail} },
//                        gate_summary: {code, passed, unknown, failed, bias_candidate} } ],
//        candidates_scored, candidates_considered, candidates_truncated,
//        fields: [{predicate, field, candidate_key, compare, value_type, leaves,
//                  attributed: {case: {n, of}, control: {n, of}},
//                  distinct_values, high_cardinality, numeric}],
//        walk: {state, applied, control_sampled, sample_step, control_subjects,
//               control_subjects_available, atoms_estimated, max_atoms, message, …},
//        mechanism: {state, config, origin, models[], …},
//        notes: [{note, at, fields, message}] }
//
// CHANGING WHAT THIS CONSUMES IS AN ESCALATION, NOT AN EDIT.
// ------------------------------------------------------------
//
// 🔴 THE THREE GATES ARE THE SERVER'S AND ARE NOT BUILT HERE. `body.gates` is the
// declared axis and every candidate carries its own verdicts. A fourth gate
// declared tomorrow becomes a fourth column with no line changing in this file.
//
// 🔴 AND TRUNCATION IS CONTENT, NOT A DETAIL. Measured live: 20 candidates
// returned, 37 scored, `candidates_truncated: true`. A panel that shows 20 and
// says nothing is read as "these are all of them" — which is a fake reduction of
// surprise, the one thing this project does not let a screen do. Same for
// `fields`: it carries the attribution coverage, and without it a candidate list
// looks more complete than it is.
// ============================================================

export const CONTRAST_MIN_MARKS = 1;

const strOrEmpty = (v) => (v === null || v === undefined ? '' : String(v));
const listOf = (v) => (Array.isArray(v) ? v : []);

function numOrNull(v) {
  if (v === null || v === undefined || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function intOrNull(v) {
  const n = numOrNull(v);
  return n === null ? null : Math.trunc(n);
}

//: The enrichment verdicts the wire uses, with a raw fallback. A state this file
//: has never heard of keeps its spelling rather than vanishing — that is the test
//: of the difference between a label map and a hardcoded list.
const ENRICHMENT_LABELS = {
  enriched: '많음',
  depleted: '적음',
  flat: '차이 없음',
  undeterminable: '판정 불가',
};

export const enrichmentLabel = (state) => ENRICHMENT_LABELS[strOrEmpty(state)] || strOrEmpty(state) || '미보고';

//: Gate verdicts. `unknown` is NOT a failure — 「실재✓ · 상류✓ · 기전 모름」 is
//: precisely the DOE candidate, and collapsing it into a fail would delete the
//: most interesting row on the screen.
const VERDICT_FACE = {
  pass: { glyph: '✓', word: '통과' },
  fail: { glyph: '✕', word: '불통과' },
  unknown: { glyph: '—', word: '미판정' },
};

export const verdictFace = (verdict) => VERDICT_FACE[strOrEmpty(verdict)] || VERDICT_FACE.unknown;

export function verdictOf(raw) {
  if (raw === null || raw === undefined) return 'unknown';
  if (typeof raw === 'string') return VERDICT_FACE[raw] ? raw : 'unknown';
  if (typeof raw === 'object') {
    const v = strOrEmpty(raw.verdict);
    return VERDICT_FACE[v] ? v : 'unknown';
  }
  return 'unknown';
}

/**
 * The scope the panel asks about — the MARKED SET, as the server spells it.
 *
 * 🔴 THE AXIS IS THE TABLE'S OWN. `row_axis.name` is `bond_lot` today and the
 * axis is switchable (`by=`), so a hardcoded axis would ask a question about a
 * different population than the one the reader marked.
 */
export function contrastScope(question, rowAxis) {
  const axis = strOrEmpty(rowAxis && rowAxis.name);
  const values = listOf(question && question.marked).map(strOrEmpty).filter(Boolean);
  return { axis, values, ok: Boolean(axis) && values.length >= CONTRAST_MIN_MARKS };
}

/**
 * The request. `mode` and `finding` are parameters — there is no second route.
 *
 * 🔴 `axes=` IS GONE, AND SO IS THE LIST IT CARRIED. A hardcoded `FACTOR_AXES`
 * lived here to keep wafer IDENTITIES out of the factor ranking while the engine
 * had no high-cardinality guard. The engine now refuses to rank an identity axis
 * at source — a `rank: false` flag plus a measured `high_cardinality_at`
 * threshold, both declarations — so the client-side copy is dead weight.
 * Verified equal by the server lane: with and without the eight explicit axes,
 * 18 factors out of 261 considered, identical list.
 *
 * 🔴 THE LESSON, KEPT BECAUSE THE SHAPE RECURS: a client-side copy of a server
 * declaration goes stale silently. An axis declared tomorrow would never have
 * entered that list and nobody would have been told. If this client ever needs an
 * axis list again it must READ one, not keep one — `axes[]` now carries `rank`
 * and `ranked` per axis, so the list is derivable from the declaration instead of
 * duplicated beside it.
 */
export function contrastQuery(question, rowAxis) {
  const scope = contrastScope(question, rowAxis);
  if (!scope.ok) return '';
  const parts = [
    'mode=contrast',
    `scope=${encodeURIComponent(`${scope.axis}:${scope.values.join(',')}`)}`,
  ];
  const finding = strOrEmpty(question && question.kind);
  if (finding) parts.push(`finding=${encodeURIComponent(finding)}`);
  const win = strOrEmpty(question && question.window);
  if (win) parts.push(`window=${encodeURIComponent(win)}`);
  return parts.join('&');
}

/** One side of a comparison, read without ever letting a null become a 0. */
function sideOf(raw) {
  const s = raw || {};
  return {
    n: intOrNull(s.n),
    of: intOrNull(s.of),
    rate: numOrNull(s.rate),
    attributedOf: intOrNull(s.attributed_of),
    rateAttributed: numOrNull(s.rate_attributed),
    coverage: numOrNull(s.coverage),
  };
}

/**
 * The declared gate axis — the panel's gate COLUMNS, in the server's order.
 *
 * An undeclared axis is stated as undeclared rather than filled in from here:
 * a client that invented the three gates would keep drawing them after the
 * server stopped declaring them.
 */
export function gateAxis(body) {
  const raw = listOf(body && body.gates);
  const gates = [];
  for (const g of raw) {
    if (typeof g === 'string') { gates.push({ id: g, label: g, basis: '', doc: '' }); continue; }
    const id = strOrEmpty(g && g.id);
    if (!id) continue;
    gates.push({
      id,
      label: strOrEmpty(g.label) || id,
      basis: strOrEmpty(g.basis),
      doc: strOrEmpty(g.doc),
    });
  }
  return { declared: gates.length > 0, gates };
}

/** One candidate's verdicts, in the declared gate order — never in a guessed one. */
function rowGates(row, gates) {
  const src = (row && row.gates && typeof row.gates === 'object') ? row.gates : {};
  return gates.map((gate) => {
    const raw = Object.prototype.hasOwnProperty.call(src, gate.id) ? src[gate.id] : undefined;
    const verdict = verdictOf(raw);
    return {
      id: gate.id,
      label: gate.label,
      verdict,
      // 🔴 THE SERVER'S SENTENCE, VERBATIM. This panel never paraphrases a gate.
      message: strOrEmpty(raw && raw.message),
      reason: strOrEmpty(raw && raw.reason),
      reported: raw !== undefined,
    };
  });
}

/**
 * The numeric comparison, for a `compare: "distribution"` candidate.
 *
 * 🔴 `state` IS THE SERVER'S AND SO IS `message`. Measured live: `purge_delay_s`
 * comes back `not_comparable` with 「평균이 0 이하 — 비율 척도 불가 (차이만 보고)」.
 * Any client-side guess at WHY a comparison failed ("표본이 적어…") is an invented
 * cause sitting on top of a stated one.
 */
function readNumeric(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const side = (s) => ({
    mean: numOrNull(s && s.mean),
    sd: numOrNull(s && s.sd),
    subjects: intOrNull(s && s.subjects),
  });
  const range = raw.range || {};
  return {
    effect: strOrEmpty(raw.effect),
    state: strOrEmpty(raw.state),
    message: strOrEmpty(raw.message),
    case: side(raw.case),
    control: side(raw.control),
    meanDelta: numOrNull(raw.mean_delta),
    // 🔴 THE STANDARDISED DIFFERENCE IS THE ONE THAT SURVIVES A FLAT RATIO.
    // `temp_C`: means 150 vs 145.5 — a ratio of 1.03, which reads as 「몰림 없음」,
    // while the standardised difference is 3.3σ. Reporting only the ratio would
    // call a real separation "no difference".
    stdDiff: numOrNull(raw.std_diff),
    min: numOrNull(range.min),
    max: numOrNull(range.max),
  };
}

export function readCandidate(raw, gates) {
  const c = raw || {};
  const ci = Array.isArray(c.enrichment_ci) ? c.enrichment_ci : [];
  const summary = c.gate_summary || {};
  return {
    key: strOrEmpty(c.candidate_key) || strOrEmpty(c.axis),
    predicate: strOrEmpty(c.predicate),
    field: strOrEmpty(c.field),
    value: strOrEmpty(c.value),
    axis: strOrEmpty(c.axis),
    label: strOrEmpty(c.label) || strOrEmpty(c.axis),
    about: strOrEmpty(c.about),
    compare: strOrEmpty(c.compare),
    unit: strOrEmpty(c.unit),
    case: sideOf(c.case),
    control: sideOf(c.control),
    enrichment: numOrNull(c.enrichment),
    ciLow: numOrNull(ci[0]),
    ciHigh: numOrNull(ci[1]),
    enrichmentState: strOrEmpty(c.enrichment_state),
    enrichmentBasis: strOrEmpty(c.enrichment_basis),
    rateDelta: numOrNull(c.rate_delta),
    // The server's word for WHY, kept as the wire spelled it.
    reason: strOrEmpty(c.reason),
    // 🔴 THE NUMERIC BLOCK — the whole finding for a `distribution` row. Without
    // it the client can only see the MEMBERSHIP rates (「50/50 have a reading」),
    // which is presence, not agreement. See `factorSentence`.
    numeric: readNumeric(c.numeric),
    evidenceCount: intOrNull(c.evidence_ref_count),
    evidenceShown: listOf(c.evidence_refs).length,
    gates: rowGates(c, gates),
    gateCode: strOrEmpty(summary.code),
    gatesPassed: intOrNull(summary.passed),
    gatesUnknown: intOrNull(summary.unknown),
    gatesFailed: intOrNull(summary.failed),
    biasCandidate: summary.bias_candidate === true,
  };
}

/**
 * The attribution coverage, per field.
 *
 * 🔴 THIS IS WHAT STOPS THE LIST LOOKING MORE COMPLETE THAN IT IS. A field whose
 * case attribution is 0/75 contributed nothing to the ranking, and a reader who
 * cannot see that will read its absence from the list as "no difference here".
 */
export function readFields(body) {
  return listOf(body && body.fields).map((f) => {
    const raw = f || {};
    const at = raw.attributed || {};
    const cs = at.case || {};
    const ct = at.control || {};
    const num = raw.numeric || null;
    return {
      key: strOrEmpty(raw.candidate_key) || `${strOrEmpty(raw.predicate)}:${strOrEmpty(raw.field)}`,
      predicate: strOrEmpty(raw.predicate),
      field: strOrEmpty(raw.field),
      compare: strOrEmpty(raw.compare),
      valueType: strOrEmpty(raw.value_type),
      leaves: intOrNull(raw.leaves),
      caseN: intOrNull(cs.n),
      caseOf: intOrNull(cs.of),
      controlN: intOrNull(ct.n),
      controlOf: intOrNull(ct.of),
      distinctValues: intOrNull(raw.distinct_values),
      highCardinality: raw.high_cardinality === true,
      // A numeric field the server has only summarised says so in its own words.
      numericState: strOrEmpty(num && num.state),
      numericMessage: strOrEmpty(num && num.message),
      caseMean: numOrNull(num && num.case_mean),
      controlMean: numOrNull(num && num.control_mean),
      // 🔴 A FIELD NOBODY COULD ATTRIBUTE ON THE CASE SIDE CONTRIBUTED NOTHING.
      blind: intOrNull(cs.n) === 0,
    };
  });
}

function readScope(body) {
  const s = (body && body.scope) || {};
  const pop = (raw) => {
    const p = raw || {};
    return {
      subjects: intOrNull(p.subjects),
      units: intOrNull(p.units),
      foundUnits: intOrNull(p.found_units),
      foundRate: numOrNull(p.found_rate),
      foundRateOf: intOrNull(p.found_rate_of),
    };
  };
  return {
    declared: s.declared === true,
    axis: strOrEmpty(s.axis),
    axisLabel: strOrEmpty(s.axis_label) || strOrEmpty(s.axis),
    values: listOf(s.values).map(strOrEmpty).filter(Boolean),
    relation: strOrEmpty(s.relation),
    case: pop(s.case),
    control: pop(s.control),
    // 🔴 WHO WAS LEFT OUT, AND WHETHER THE EXCLUSION EVEN RAN. A bucket sitting at
    // `discriminator_pending` means the rule is NOT applied — reading that as 0
    // excluded would overstate how clean the control group is.
    excluded: listOf(s.excluded).map((e) => ({
      bucket: strOrEmpty(e && e.bucket),
      label: strOrEmpty(e && e.label) || strOrEmpty(e && e.bucket),
      subjects: intOrNull(e && e.subjects),
      state: strOrEmpty(e && e.state),
      message: strOrEmpty(e && e.message),
    })),
  };
}

function readWalk(body) {
  const w = (body && body.walk) || {};
  return {
    state: strOrEmpty(w.state),
    applied: w.applied === true,
    // 🔴 A SAMPLED CONTROL GROUP CHANGES WHAT EVERY DENOMINATOR MEANS, and the
    // server says so in its own sentence. Dropping it would leave the rates
    // looking like they were computed over the whole fab.
    controlSampled: w.control_sampled === true,
    sampleStep: intOrNull(w.sample_step),
    controlSubjects: intOrNull(w.control_subjects),
    controlAvailable: intOrNull(w.control_subjects_available),
    atomsEstimated: intOrNull(w.atoms_estimated),
    maxAtoms: intOrNull(w.max_atoms),
    message: strOrEmpty(w.message),
  };
}

export function contrastState(body) {
  const s = strOrEmpty(body && body.state);
  return s || 'unknown';
}

/**
 * The whole panel.
 *
 * Every field is optional to this reader: a missing one renders as 미보고 rather
 * than as a 0 and never as a blank. That is what lets a partially-answered
 * response stay readable instead of looking broken.
 */
export function contrastModel({ body, question, rowAxis } = {}) {
  const asked = question || { marked: [] };
  const scope = contrastScope(asked, rowAxis);
  const gates = gateAxis(body);
  const candidates = listOf(body && body.candidates).map((c) => readCandidate(c, gates.gates));

  const scored = intOrNull(body && body.candidates_scored);
  const considered = intOrNull(body && body.candidates_considered);
  const shown = candidates.length;
  // 🔴 TRUNCATION IS DERIVED FROM THE NUMBERS AS WELL AS THE FLAG. A server that
  // returns fewer than it scored and forgets the flag must still be caught — the
  // whole point of this block is that a short list can never pass for a full one.
  const truncated = (body && body.candidates_truncated === true)
    || (scored !== null && shown < scored);

  const fields = readFields(body);
  return {
    state: contrastState(body),
    engine: strOrEmpty(body && body.engine),
    finding: strOrEmpty(body && body.finding),
    generatedAt: strOrEmpty(body && body.generated_at),
    question: asked,
    askedScope: scope,
    scope: readScope(body),
    subject: {
      type: strOrEmpty(body && body.subject && body.subject.type),
      // 🔴 THE AXIS WHOSE ROWS ARE SUBJECTS, ONE FOR ONE. `key` is `wafer` today
      // and it is what decides whether a pair of marks is a pair of SUBJECTS —
      // two marks on the lot axis resolve to fifty wafers, which the journey route
      // refuses. Read from the response rather than assumed, so the day the
      // subject becomes something else the door follows it.
      key: strOrEmpty(body && body.subject && body.subject.key),
      unitLabel: strOrEmpty(body && body.subject && body.subject.unit_label),
    },
    gates,
    candidates,
    shown,
    scored,
    considered,
    truncated,
    hidden: (scored !== null && shown < scored) ? scored - shown : null,
    fields,
    blindFields: fields.filter((f) => f.blind),
    walk: readWalk(body),
    notes: listOf(body && body.notes).map((n) => ({
      note: strOrEmpty(n && n.note),
      message: strOrEmpty(n && n.message),
    })),
  };
}

// ── text ─────────────────────────────────────────────────────

export function rateText(rate) {
  if (rate === null) return '미보고';
  return `${(rate * 100).toFixed(rate < 0.01 && rate > 0 ? 2 : 1)}%`;
}

export function countText(n) {
  if (n === null) return '미보고';
  return Number(n).toLocaleString('ko-KR');
}

/** `n/N`, and never a bare percentage — the denominator is half the number. */
export function fractionText(side) {
  if (!side || side.n === null || side.of === null) return '';
  return `${countText(side.n)}/${countText(side.of)}`;
}

export function enrichmentText(row) {
  if (!row) return '미보고';
  if (row.enrichment !== null) return `${row.enrichment.toFixed(2)}×`;
  // 🔴 AN ABSENT POINT ESTIMATE IS NOT A ZERO. `absent_from_control_population`
  // is an infinite ratio, and the interval is what carries the finding.
  if (row.ciLow !== null) return '∞×';
  return '미보고';
}

// ── 자연어 ───────────────────────────────────────────────────
//
// 🔴 THE PANEL HAD NO DEFINITIONS ON IT. Owner, 2026-08-14: 「대체 뭐가 같다는건지
// 다르단건지 모르겠음」, 「용어들이 뭔말임?」 — 걷기 · 근거 N건 · 실재 · 상류 ·
// 기전 · 배수 · 구간 were all undefined on screen. Every one of them is a term this
// project invented, and a reader who has to be told what a column means is reading
// a table that has not answered anything yet.
//
// So each factor row gets ONE SENTENCE that says the finding in words, and the
// numeric table stays underneath as support. The terse-copy rule still holds
// everywhere else: full sentences live ONLY in the factor head and the one legend
// line, and every other label stays a symbol or a noun form.

//: Counters, by subject type. A closed wire enum with a raw fallback — same
//: pattern as the bucket and heat label maps, not an ontology in the client.
const UNIT_COUNTER = { Wafer: '장', Lot: '개', Frame: '장' };

//: What a predicate DID, as a verb. The sentence has to read as an event, and
//: 「processed_with·eqp = X 였다」 is the jargon the owner objected to.
//:
//: The particle is chosen at render time, not baked in — see `particle` below.
const PREDICATE_VERB = {
  processed_with: { p: 'obj', yes: '지났다', no: '지나지 않았다' },
  observed: { p: 'subj', yes: '관측됐다', no: '관측되지 않았다' },
  measured: { p: 'inst', yes: '측정됐다', no: '측정되지 않았다' },
};
const DEFAULT_VERB = { p: 'subj', yes: '해당된다', no: '해당되지 않는다' };

const PARTICLES = { obj: ['을', '를'], subj: ['이', '가'], inst: ['으로', '로'] };

//: Digits whose Korean reading ends in a consonant: 영 0 · 일 1 · 삼 3 · 육 6 ·
//: 칠 7 · 팔 8. (2 이, 4 사, 5 오, 9 구 end in vowels.)
const CONSONANT_DIGITS = '013678';
//: Latin letters whose Korean reading ends in a consonant: 엘 · 엠 · 엔 · 알.
const CONSONANT_LETTERS = 'LMNR';

/**
 * 🔴 THE PARTICLE FOLLOWS THE SOUND, AND THE SOUND IS THE VALUE'S.
 *
 * Live output before this existed: 「이 레시피 버전(6)를 지났다」 — 6 reads 육,
 * which ends in a consonant, so it takes 을. Getting this wrong is exactly the
 * translated-sounding Korean the copy rule forbids, and the owner asked for this
 * panel to read as language.
 *
 * The particle attaches to what is SPOKEN last, which is the text inside the
 * parentheses — not the `)` character that literally precedes it.
 */
function endsInConsonant(word) {
  const s = strOrEmpty(word).trim();
  if (!s) return false;
  const ch = s[s.length - 1];
  const code = ch.charCodeAt(0);
  // Hangul syllable: the final-consonant index is the remainder mod 28.
  if (code >= 0xAC00 && code <= 0xD7A3) return (code - 0xAC00) % 28 !== 0;
  if (ch >= '0' && ch <= '9') return CONSONANT_DIGITS.indexOf(ch) >= 0;
  if (/[A-Za-z]/.test(ch)) return CONSONANT_LETTERS.indexOf(ch.toUpperCase()) >= 0;
  return false;
}

export function particle(word, kind) {
  const pair = PARTICLES[kind] || PARTICLES.subj;
  return endsInConsonant(word) ? pair[0] : pair[1];
}

//: 🔴 NOT A DICTIONARY OF EVERY FIELD — the quantities the walk ACTUALLY returns
//: today (measured 2026-08-14: pressure · temp · purge_delay · post_bond_queue).
//: P0-3 brings a declared label layer and this goes away; until then anything
//: unlisted degrades to its wire spelling AND SAYS SO on screen (`known: false`),
//: because a silent fallback to English machine text is the complaint itself.
const QUANTITY_NOUN = {
  pressure: '압력',
  temp: '온도',
  purge_delay: '퍼지 지연',
  post_bond_queue: '본딩 후 대기',
};
const PARAM_SOURCE = { params_setpoint: '설정', params_actual: '실측' };
const UNIT_TEXT = { MPa: 'MPa', C: '°C', s: '초', h: '시간', mm: 'mm', um: 'µm', pct: '%' };

/**
 * Read a wire field name into something a human can say.
 *
 * `params_actual.pressure_MPa` -> {label: '실측 압력', unit: 'MPa', known: true}
 * `params_actual.vacuum_assist` -> {label: 'params_actual.vacuum_assist', known: false}
 *
 * The unit is taken from the trailing `_<unit>` because that is how these names
 * are built — a general rule, not a per-field entry.
 */
export function fieldReading(field) {
  const raw = strOrEmpty(field);
  const dot = raw.indexOf('.');
  const prefix = dot > 0 ? raw.slice(0, dot) : '';
  let rest = dot > 0 ? raw.slice(dot + 1) : raw;
  let unit = '';
  const us = rest.lastIndexOf('_');
  if (us > 0 && UNIT_TEXT[rest.slice(us + 1)]) {
    unit = UNIT_TEXT[rest.slice(us + 1)];
    rest = rest.slice(0, us);
  }
  const quantity = QUANTITY_NOUN[rest] || '';
  const source = PARAM_SOURCE[prefix] || '';
  return {
    raw,
    unit,
    known: Boolean(quantity),
    label: quantity ? `${source ? `${source} ` : ''}${quantity}` : raw,
  };
}

//: Enough digits to be read, not enough to be noise.
//:
//: 🔴 THE FIRST DECIMAL SURVIVES ABOVE 100. Rounding `145.478` to `145` beside a
//: case mean of `150` made 「편차 기준 3.3σ」 look like an error — the reader
//: cannot see a 4.5 gap when one side has been rounded away. Trailing `.0` is
//: dropped so an exact 150 does not gain a fake precision digit.
function numText(v) {
  if (v === null) return '미보고';
  const a = Math.abs(v);
  if (a >= 100) return v.toFixed(1).replace(/\.0$/, '');
  if (a >= 1) return v.toFixed(2);
  return v.toFixed(3);
}

/**
 * 🔴 A DISTRIBUTION ROW COMPARES VALUES, NOT MEMBERSHIP.
 *
 * The defect this replaces: every row got the categorical template, so a numeric
 * field read 「마킹한 50장 전부(100%)가 params_setpoint.temp_C를 지났다」. Three
 * things wrong at once — you cannot 지나다 a temperature, the name is wire
 * spelling, and worst, 「100%」 there means EVERY WAFER HAS A READING, which a
 * reader takes as "they all ran at the same temperature". That is presence
 * reported as agreement, and the response said `compare: "distribution"` the
 * whole time.
 *
 * 🔴 AND THE RATIO ALONE CAN SAY THE OPPOSITE OF THE TRUTH. `temp_C` live: means
 * 150 vs 145.5, ratio 1.03 — which lands in `flat` and would print 「몰림 없음」 —
 * while the standardised difference is 3.3σ and the marked side has sd 0. So both
 * measures go in the sentence whenever the server computed them.
 */
function numericSentence(row, subject) {
  const f = fieldReading(row.field);
  const n = row.numeric;
  const u = f.unit ? ` ${f.unit}` : '';
  if (!n) return `${f.label} — 수치 대조 미보고`;

  const head = `마킹한 쪽 ${f.label} 평균 ${numText(n.case.mean)}${u}`
    + `, 나머지 ${numText(n.control.mean)}${u}`;

  // The server said it could not compare, and said why. Its sentence, verbatim.
  if (n.state !== 'compared') {
    return `${head} — ${n.message || '비교 불가 — 사유 미보고'}`;
  }

  const bits = [];
  if (row.enrichment !== null) {
    bits.push(`${row.enrichment >= 100 ? Math.round(row.enrichment) : row.enrichment.toFixed(2)}배`);
  }
  if (n.stdDiff !== null) {
    bits.push(`편차 기준 ${Math.abs(n.stdDiff).toFixed(1)}σ ${n.stdDiff > 0 ? '높음' : '낮음'}`);
  }
  return bits.length ? `${head} — ${bits.join(' · ')}` : head;
}

//: What a field IS, as a noun. Unknown fields keep their wire spelling rather than
//: vanishing — the sentence degrades to the raw field name and stays true.
//: Filled from the fields the live walk actually returns (measured 2026-08-14:
//: eqp · recipe.rev · recipe.id · chamber · step · method · class · basis ·
//: finding_kind · inferred · params_actual.*). An unlisted field degrades to its
//: wire spelling, which is honest but reads as English — so this map is worth
//: extending when a new field starts appearing, NOT worth pre-populating with
//: guesses about fields nobody has seen.
const FIELD_NOUN = {
  eqp: '이 장비',
  chamber: '이 챔버',
  recipe: '이 레시피',
  'recipe.id': '이 레시피',
  'recipe.rev': '이 레시피 버전',
  class: '이 분류',
  method: '이 검사 방식',
  finding_kind: '이 불량 종류',
  run_uid: '이 실행',
  step: '이 공정 단계',
  operator: '이 작업자',
  basis: '이 근거 등급',
  inferred: '이 추론 여부',
};

const counterOf = (subject) => UNIT_COUNTER[strOrEmpty(subject && subject.type)] || '개';

function pctText(rate) {
  if (rate === null) return '미보고';
  const p = rate * 100;
  return `${p >= 10 || p === 0 ? Math.round(p) : p.toFixed(1)}%`;
}

/** `4.1배 몰림(신뢰구간 3.6~4.6배)` — the multiple, in words. */
export function liftPhrase(row) {
  const ci = (row.ciLow !== null && row.ciHigh !== null)
    ? `(신뢰구간 ${row.ciLow >= 100 ? Math.round(row.ciLow) : row.ciLow.toFixed(1)}~${row.ciHigh >= 100 ? Math.round(row.ciHigh) : row.ciHigh.toFixed(1)}배)`
    : '';
  if (row.enrichmentState === 'flat') return '몰림 없음';
  // 🔴 THE SERVER'S REASON, NOT A BETTER-SOUNDING GUESS. This said 「표본이 적어
  // 판정 불가」, which is an INVENTED CAUSE: live, `purge_delay_s` is undeterminable
  // because 「평균이 0 이하 — 비율 척도 불가 (차이만 보고)」 — nothing to do with
  // sample size. A client replacing a true stated reason with a plausible false one
  // is the same defect family as the rest of tonight's, and the fix is to pass the
  // sentence through rather than to write a better guess.
  if (row.enrichmentState === 'undeterminable') {
    const said = strOrEmpty(row.numeric && row.numeric.message);
    return said ? `${said}${ci}` : `판정 불가 — 사유 미보고${ci}`;
  }
  // 🔴 NO POINT ESTIMATE IS NOT ZERO. `absent_from_control_population` means the
  // factor is missing from the other side entirely — an infinite ratio, and the
  // interval is the whole finding. Printing 「0배」 would invert it.
  if (row.enrichment === null) {
    if (row.enrichmentState === 'depleted') return `마킹한 쪽엔 아예 없음${ci}`;
    return `나머지엔 아예 없음${ci}`;
  }
  const x = row.enrichment >= 100 ? Math.round(row.enrichment) : row.enrichment.toFixed(1);
  if (row.enrichmentState === 'depleted') return `${x}배로 드묾${ci}`;
  return `${x}배 몰림${ci}`;
}

/**
 * ONE SENTENCE for one factor — the owner's own template.
 *
 * 「마킹한 25장 전부(100%)가 이 장비(SYN-BD-03)를 지났다 — 나머지는 859장 중
 *   208장(24%). 4.1배 몰림(신뢰구간 3.6~4.6배)」
 *
 * Every number in it is the same number the table below prints; this is a
 * rewording, never a second computation.
 */
export function factorSentence(row, subject) {
  // 🔴 THE RESPONSE SAYS WHICH KIND OF COMPARISON THIS IS, AND THE CLIENT WAS NOT
  // READING IT. `compare` is normalised in `readCandidate` and then ignored, so a
  // numeric field got the membership template: 「마킹한 50장 전부(100%)가
  // params_setpoint.temp_C를 지났다」. You cannot 지나다 a temperature — and the
  // 100% there means EVERY WAFER HAS A READING, which reads as "they all ran at
  // the same temperature". Presence printed as agreement.
  if (row.compare === 'distribution') return numericSentence(row, subject);

  const c = counterOf(subject);
  const v = PREDICATE_VERB[row.predicate] || DEFAULT_VERB;
  const noun = FIELD_NOUN[row.field] || row.field || '이 요인';
  const value = row.value ? `(${row.value})` : '';
  // The spoken tail is the value when there is one, otherwise the noun.
  const thing = `${noun}${value}${particle(row.value || noun, v.p)}`;

  let head;
  if (row.case.of === null || row.case.n === null) {
    head = `마킹한 쪽 귀속 미보고 — ${thing} ${v.yes}`;
  } else if (row.case.n === row.case.of && row.case.of > 0) {
    head = `마킹한 ${countText(row.case.of)}${c} 전부(100%)가 ${thing} ${v.yes}`;
  } else if (row.case.n === 0) {
    head = `마킹한 ${countText(row.case.of)}${c} 중 어느 것도 ${thing} ${v.no}`;
  } else {
    head = `마킹한 ${countText(row.case.of)}${c} 중 ${countText(row.case.n)}${c}`
      + `(${pctText(row.case.rate)})가 ${thing} ${v.yes}`;
  }

  const tail = (row.control.of === null || row.control.n === null)
    ? '나머지 쪽 귀속 미보고'
    : `나머지는 ${countText(row.control.of)}${c} 중 ${countText(row.control.n)}${c}(${pctText(row.control.rate)})`;

  return `${head} — ${tail}. ${liftPhrase(row)}`;
}

//: 🔴 THE GATE NAMES ARE THE PROJECT'S JARGON. 실재 · 상류 · 기전 mean nothing to
//: someone who did not design them, so the SYMBOL stays (it is the compact signal)
//: and the LABEL becomes the meaning. Keyed on the server's gate id, falling back
//: to the server's own label for a gate declared tomorrow.
const GATE_MEANING = {
  real: '우연 아님',
  upstream: '시간상 앞섬',
  mechanism: '물리 경로 있음',
};

export const gateMeaning = (id, served) => GATE_MEANING[strOrEmpty(id)] || strOrEmpty(served) || strOrEmpty(id);

/**
 * 공통점 / 차이점 / 그 외 — the split the owner asked for by name.
 *
 * 🔴 AND NOTHING IS DROPPED. A factor that is neither concentrated nor shared is
 * still shown, in its own group, because a list that quietly keeps only the
 * interesting rows is the fake reduction of surprise this project does not do.
 */
export function splitCandidates(candidates) {
  const differs = [];
  const common = [];
  const rest = [];
  for (const row of listOf(candidates)) {
    if (row.enrichmentState === 'enriched' || row.enrichmentState === 'depleted') differs.push(row);
    else if (row.case.of !== null && row.case.of > 0 && row.case.n === row.case.of) common.push(row);
    else rest.push(row);
  }
  return { differs, common, rest };
}

export function ciText(row) {
  if (!row || row.ciLow === null || row.ciHigh === null) return '';
  const fmt = (v) => (v >= 1000 ? v.toExponential(1) : v.toFixed(2));
  return `구간 ${fmt(row.ciLow)}–${fmt(row.ciHigh)}`;
}
