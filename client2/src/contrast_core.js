// ============================================================
// contrast_core.js — 마킹한 랏들이 «무엇이 다른가»를 모델로.
//
// PURE. No DOM, no network, no `window` — same contract as `surprise_core.js`,
// so `tests/contrast_harness.mjs` drives it under bare node.
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

/** The request. `mode` and `finding` are parameters — there is no second route. */
export function contrastQuery(question, rowAxis) {
  const scope = contrastScope(question, rowAxis);
  if (!scope.ok) return '';
  const parts = ['mode=contrast', `scope=${encodeURIComponent(`${scope.axis}:${scope.values.join(',')}`)}`];
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

export function ciText(row) {
  if (!row || row.ciLow === null || row.ciHigh === null) return '';
  const fmt = (v) => (v >= 1000 ? v.toExponential(1) : v.toFixed(2));
  return `구간 ${fmt(row.ciLow)}–${fmt(row.ciHigh)}`;
}
