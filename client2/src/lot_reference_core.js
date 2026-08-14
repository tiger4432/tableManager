// ============================================================
// lot_reference_core.js — 랏 참조뷰(화면 ②)의 «읽기»
//
// SCENARIO_CONSOLE_BRIEF §0-quinquies R2. ONE QUESTION = ONE URL:
//   ledger.html?view=lot&lot=<lot>[&finding=<kind>]
// and it is a VIEW of the page that already exists — not a page, not a modal,
// not a mode. The three sibling views (`ask` / `surprise` / `structure`) are
// branches on the same parameter and this is the fourth.
//
// WHAT IT CONSUMES (R1, 랏 스코프 대조 — 병행 레인):
//   GET /api/ledger/lot?lot=<lot>&finding=<kind>
//     -> {state, generated_at, lot: {id, bucket}, summary[], gates[],
//         lineage: {subject, hops[], terminal_reason, anomalies[]},
//         factors[], coverage, investigations[]}
//
// 🔴 THE CONTRACT IS NOT LANDED YET, AND THAT IS WHY EVERY READ BELOW IS
// DEFENSIVE IN ONE DIRECTION ONLY: an ABSENT key renders as "the server did not
// say", never as "the server said no". The two are different facts and the whole
// value of this screen is that it does not confuse them. A field that arrives
// later starts rendering without a line changing here; a field that never
// arrives leaves a sentence saying so.
//
// 🔴 THIS FILE NEVER TOUCHES `window`. Scored under bare node by
// `client2/tests/lot_reference_harness.mjs`, same as the three cores beside it.
// ============================================================

// The lineage hop reading — INCLUDING `basis`, which is READ OFF THE FIELD and
// never derived from `state`. A convention-backed hop carries the SAME word
// (`resolved`) a fully measured one does; that axis landed at `4d9b912` and this
// consumes it rather than re-spelling it (owner instruction, R2).
import { traceChain, rateReading, axisTerm } from './case_control_core.js';
import { instantText } from './ledger_trace_core.js';
import { bucketLabel } from './surprise_core.js';

export { rateReading, instantText };

export const LOT_VIEW = 'lot';

/**
 * 🔴 THE ONE NUMERIC DOOR. `Number(null) === 0` and `Number('') === 0` — the
 * defect that painted 「검사 0회」 as a measurement on this page earlier today.
 * Defeated in ONE place rather than at every call site. A real 0 comes back as
 * 0; everything that is not a finite number comes back as null.
 */
export function numOrNull(v) {
  if (v === null || v === undefined || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

const strOrEmpty = (v) => (v === null || v === undefined ? '' : String(v));
const strOrNull = (v) => {
  const s = strOrEmpty(v);
  return s === '' ? null : s;
};

const STATES = new Set(['absent', 'empty', 'ready']);

export function lotState(body) {
  const s = body && body.state != null ? String(body.state) : '';
  return STATES.has(s) ? s : 'unknown';
}

// ── the question ─────────────────────────────────────────────

/**
 * What the URL is asking. `lot` is the whole subject scope of this view: with no
 * lot there is nothing to be a reference view OF, and the screen says that
 * rather than fetching a question with a hole in it.
 */
export function parseLotQuery(params) {
  const get = (k) => {
    const v = params && typeof params.get === 'function' ? params.get(k) : null;
    return v == null ? '' : String(v).trim();
  };
  return {
    view: get('view'),
    lot: get('lot'),
    slot: get('slot'),
    // 🔴 EMPTY, NOT 'void'. The kind is resolved against the SERVER's catalog by
    // `pickKind` downstream, exactly as the console does it. A literal default
    // spelled here would be the generalisation quietly dying in the client.
    finding: get('finding'),
  };
}

/** Write it back. Only non-empty parts, so the bare question stays short. */
export function lotQuery(question, omit) {
  const q = question || {};
  const parts = [`view=${encodeURIComponent(LOT_VIEW)}`];
  if (q.lot && omit !== 'lot') parts.push(`lot=${encodeURIComponent(q.lot)}`);
  if (q.slot && omit !== 'slot') parts.push(`slot=${encodeURIComponent(q.slot)}`);
  if (q.finding && omit !== 'finding') parts.push(`finding=${encodeURIComponent(q.finding)}`);
  return parts.join('&');
}

/** The request, which is NOT the address bar — `view` is the client's own. */
export function lotFetchQuery(question) {
  const q = question || {};
  const parts = [];
  if (q.lot) parts.push(`lot=${encodeURIComponent(q.lot)}`);
  if (q.slot) parts.push(`slot=${encodeURIComponent(q.slot)}`);
  if (q.finding) parts.push(`finding=${encodeURIComponent(q.finding)}`);
  return parts.join('&');
}

// ── the header ───────────────────────────────────────────────

/**
 * Lot identity and its bucket.
 *
 * The bucket is not decoration: `special_eval` lots are the ones the owner's
 * second constraint says must be SHOWN AND MARKED, and a reference view that
 * silently reads a special-evaluation lot as production would be answering about
 * a population it does not belong to. The word comes from `bucketLabel`, the one
 * spelling of that translation on this page.
 */
export function lotIdentity(body, question) {
  const raw = body && body.lot && typeof body.lot === 'object' ? body.lot : {};
  const asked = question && question.lot ? String(question.lot) : '';
  const bucket = raw.bucket && typeof raw.bucket === 'object' ? raw.bucket : {};
  const declared = 'bucket' in raw && raw.bucket !== null && raw.bucket !== undefined;
  return {
    id: strOrNull(raw.id) || (asked || null),
    // What the ADDRESS BAR asked, kept apart from what the server answered. A
    // server that answers about a different lot than the one asked is a defect
    // the reader must be able to see.
    asked: asked || null,
    slot: strOrNull(raw.slot) || (question && question.slot ? String(question.slot) : null),
    bucketId: strOrNull(bucket.id),
    // 🔴 ABSENT ≠ 'unknown bucket'. A response with no bucket key has not
    // classified this lot; one with `{id: 'unknown'}` has, and said so.
    bucketDeclared: declared,
    bucketText: declared ? bucketLabel(bucket.id, bucket.label) : null,
    countsTowardBaseline: bucket.counts_toward_baseline !== false,
    baselineDeclared: declared && 'counts_toward_baseline' in bucket,
  };
}

/**
 * The header's summary numbers — EVERY ONE OF THEM WITH ITS DENOMINATOR.
 *
 * 🔴 There is no path from this function to a bare numerator. `rateReading`
 * refuses without a denominator and carries the reason instead, which is the
 * console's rule ("분모 없는 숫자 출고 금지") applied to the one place on this
 * screen a reader glances at first.
 */
export function summaryRows(body) {
  const raw = body && Array.isArray(body.summary) ? body.summary : null;
  if (!raw) return { declared: false, rows: [] };
  const rows = [];
  for (const r of raw) {
    if (!r || typeof r !== 'object') continue;
    const term = strOrNull(r.term) || strOrNull(r.label);
    if (!term) continue;
    rows.push({
      key: strOrNull(r.id) || term,
      term,
      reading: rateReading(r.n, r.of, strOrNull(r.reason) || '분모 미보고'),
      // A note the server chose to attach. Rendered verbatim, never invented.
      note: strOrNull(r.note),
    });
  }
  return { declared: true, rows };
}

// ── attribution coverage (R1's N/M obligation) ───────────────

/**
 * 「이 축의 몇 건이 귀속됐는가」 — N of M, per axis.
 *
 * 🔴 THIS IS AN OBLIGATION, NOT A NICE-TO-HAVE (R1: "응답에 귀속 N/M 커버리지
 * 필드 의무(전 축)"). A contrast computed over 3 of 400 attributed events and one
 * computed over 400 of 400 are different claims, and a table that renders them
 * identically is the screen lying by omission. When the key is absent the panel
 * says the server did not report it — it does NOT assume full coverage.
 */
export function coverageRows(body) {
  const raw = body && body.coverage && typeof body.coverage === 'object' ? body.coverage : null;
  if (!raw) return { declared: false, overall: null, rows: [] };
  const axes = Array.isArray(raw.axes) ? raw.axes : [];
  const rows = [];
  for (const a of axes) {
    if (!a || typeof a !== 'object') continue;
    const axis = strOrEmpty(a.axis);
    if (axis === '') continue;
    rows.push({
      axis,
      term: axisTerm(axis) || axis,
      reading: rateReading(a.attributed, a.of, strOrNull(a.reason) || '귀속 분모 미보고'),
    });
  }
  return {
    declared: true,
    overall: ('attributed' in raw) || ('of' in raw)
      ? rateReading(raw.attributed, raw.of, strOrNull(raw.reason) || '귀속 분모 미보고')
      : null,
    rows,
  };
}

// ── lineage summary ──────────────────────────────────────────

/**
 * The walk, plus what was ODD about it.
 *
 * 🔴 THE HOPS GO THROUGH `traceChain`, WHICH IS THE READER THE CONSOLE ALREADY
 * USES. That is where `basis` is consumed off the field, where continuity breaks
 * are detected rather than bridged, and where a quantity is a PAIR. Re-reading
 * hops here would be a second spelling that can disagree with the first about
 * the same wire.
 *
 * 🔴 AND THE WALK IS ANY LENGTH. A wafer can visit DT twice; nothing here
 * indexes a fixed stage.
 */
export function lineageSummary(body) {
  const raw = body && body.lineage && typeof body.lineage === 'object'
    ? body.lineage
    : (body && body.trace && typeof body.trace === 'object' ? body.trace : null);
  const chain = traceChain({ trace: raw });
  return Object.assign({}, chain, { anomalies: pathAnomalies(raw) });
}

/**
 * 경로 특이점 뱃지 — 「DT 2회」, 「대기 31h」.
 *
 * 🔴 THERE IS NO LIST OF ANOMALY KINDS IN THIS FILE, AND THERE MUST NEVER BE
 * ONE. What counts as odd about a path is a DECLARATION (R7: "경로 특징 추출기는
 * 선언 — 회차·구간 체류·서열 서명, 하드코딩 금지"), so the badge is whatever the
 * server named. A new declared feature paints without a line changing here; a
 * kind spelled here would be the declaration quietly forked into the client.
 *
 * 🔴 ABSENT KEY ≠ EMPTY LIST. `anomalies: []` is the server SAYING it looked and
 * found none; no key at all is the server not having looked. Rendering the
 * second as the first would manufacture a clean bill of health — the exact shape
 * of 「없어서 0」을 「무해해서 0」으로 읽는 defect.
 */
export function pathAnomalies(lineage) {
  const raw = lineage && typeof lineage === 'object' ? lineage.anomalies : undefined;
  if (!Array.isArray(raw)) return { declared: false, items: [] };
  const items = [];
  for (const a of raw) {
    if (a === null || a === undefined) continue;
    if (typeof a === 'string') {
      items.push({ code: a, label: a, detail: null, severity: null, value: null });
      continue;
    }
    if (typeof a !== 'object') continue;
    const code = strOrNull(a.code) || strOrNull(a.id);
    const label = strOrNull(a.label) || code;
    if (!label) continue;
    items.push({
      code: code || label,
      label,
      detail: strOrNull(a.detail),
      // A word the server chose for how loud this is. Unknown words survive
      // under their raw spelling and get the neutral tone downstream.
      severity: strOrNull(a.severity),
      value: numOrNull(a.value),
      unit: strOrNull(a.unit),
    });
  }
  return { declared: true, items };
}

// ── the three gates ──────────────────────────────────────────

/**
 * 🔴 THE DEFAULT POSITION, AND THE ONLY PLACE THESE THREE MAY BE SPELLED.
 *
 * The gate axis is the SERVER's declaration (`body.gates`), exactly as the
 * finding kind is (`DEFAULT_FINDING_KIND = 'void'` is a default, not a special
 * case). A fourth gate declared tomorrow becomes a fourth column with no line
 * changing here. This constant is reached ONLY when the response declares no
 * gate axis at all, so the table has columns to be honest in.
 */
export const DEFAULT_GATES = [
  { id: 'real', label: '실재' },
  { id: 'upstream', label: '상류' },
  { id: 'mechanism', label: '기전' },
];

export const GATE_PASS = 'pass';
export const GATE_FAIL = 'fail';
export const GATE_UNKNOWN = 'unknown';

/**
 * The declared gate axis — the table's gate COLUMNS, in the server's order.
 */
export function gateAxis(body) {
  const raw = body && Array.isArray(body.gates) ? body.gates : null;
  if (!raw || raw.length === 0) return { declared: false, gates: DEFAULT_GATES.slice() };
  const gates = [];
  for (const g of raw) {
    if (typeof g === 'string') { gates.push({ id: g, label: g, note: null }); continue; }
    if (!g || typeof g !== 'object') continue;
    const id = strOrNull(g.id) || strOrNull(g.key);
    if (!id) continue;
    gates.push({ id, label: strOrNull(g.label) || id, note: strOrNull(g.note) });
  }
  return gates.length ? { declared: true, gates } : { declared: false, gates: DEFAULT_GATES.slice() };
}

/**
 * One gate's verdict for one row: pass / fail / unknown.
 *
 * 🔴 THREE STATES, AND THE THIRD IS NOT A WEAK SECOND. 「판정 못 함」 and
 * 「판정했고 통과 못 함」 are different facts about a hypothesis: the first is a
 * DOE candidate ("실재✓·상류✓·기전 모름"이 곧 DOE 후보 — brief 동작 3), the
 * second is a rejected explanation. Folding unknown into fail throws away the
 * output this machine exists to produce.
 *
 * 🔴 SO ABSENCE RESOLVES TO `unknown`, NEVER TO `fail`. `false` IS a judgement
 * and reads `fail`; `null`, `undefined` and a missing key are not, and read
 * `unknown`. There is no `Number()` and no truthiness test on this path — `0`
 * and `''` never reach here as booleans.
 */
export function gateState(raw) {
  if (raw === true) return GATE_PASS;
  if (raw === false) return GATE_FAIL;
  if (raw === null || raw === undefined) return GATE_UNKNOWN;
  if (typeof raw === 'object') return gateState(raw.state !== undefined ? raw.state : raw.passed);
  const s = String(raw).trim().toLowerCase();
  if (s === 'pass' || s === 'passed' || s === 'true' || s === 'yes') return GATE_PASS;
  if (s === 'fail' || s === 'failed' || s === 'false' || s === 'no') return GATE_FAIL;
  // 🔴 A WORD THIS FILE HAS NEVER HEARD OF FALLS TO `unknown`, NOT TO `pass`.
  // Same rule `hopVerdict` follows: a wire that grows a fourth word must not be
  // able to paint itself confident.
  return GATE_UNKNOWN;
}

/** The reason the server attached to a gate verdict, when it attached one. */
function gateReason(raw) {
  if (raw && typeof raw === 'object') return strOrNull(raw.reason) || strOrNull(raw.detail);
  return null;
}

/**
 * 🔴 A gate that reads `pass` but is BIAS rather than cause (R3: an
 * `observation_bias` model reached by the mechanism BFS) is flagged, not
 * promoted. The flag is the server's — this reads it, it does not infer it.
 */
function gateFlag(raw) {
  if (raw && typeof raw === 'object') return strOrNull(raw.flag) || strOrNull(raw.flag_label);
  return null;
}

export function rowGates(row, gates) {
  const src = row && row.gates && typeof row.gates === 'object' ? row.gates : {};
  const out = [];
  let passed = 0;
  let judged = 0;
  for (const gate of gates) {
    const has = Object.prototype.hasOwnProperty.call(src, gate.id);
    const raw = has ? src[gate.id] : undefined;
    const state = gateState(raw);
    if (state === GATE_PASS) passed += 1;
    if (state !== GATE_UNKNOWN) judged += 1;
    out.push({
      id: gate.id,
      label: gate.label,
      state,
      reason: gateReason(raw),
      flag: gateFlag(raw),
    });
  }
  return { cells: out, passed, judged, of: gates.length };
}

// ── the difference ranking (차이점 순위표 v1) ────────────────

/**
 * A row's 부류 — 범주 / 결측 / 수치 / 경로 / 혈통.
 *
 * 🔴 NO STRING MATCHING ON THE FAMILY NAME. Whether a family is a HOLE rather
 * than an answer ("결측은 빨강 = 답이 아니라 구멍") is a flag the server sets,
 * not a word this file recognises — matching `id === 'missing'` here would break
 * the moment the vocabulary spells it differently, and would break silently, in
 * the direction of painting a hole as a finding.
 */
export function rowFamily(row) {
  const raw = row && row.family !== undefined ? row.family : (row ? row.class : undefined);
  if (raw === null || raw === undefined || raw === '') {
    return { id: null, label: null, gap: false, declared: false };
  }
  if (typeof raw === 'string') {
    return { id: raw, label: raw, gap: false, declared: true };
  }
  if (typeof raw !== 'object') return { id: null, label: null, gap: false, declared: false };
  const id = strOrNull(raw.id) || strOrNull(raw.key);
  return {
    id,
    label: strOrNull(raw.label) || id,
    gap: raw.gap === true,
    declared: !!id,
  };
}

/**
 * One ranking row.
 *
 * 🔴 BOTH SIDES CARRY THEIR DENOMINATOR, and neither can reach the screen
 * without it. `found` is 「난 쪽」 and `clean_scanned` is 「안 난 쪽」; a null
 * `clean_scanned` is a REFUSAL WITH A REASON ("대조군 없음"), not a zero. This is
 * the same shape `factorRow` reads on the console, because R1 is the existing
 * contrast with a subject scope — one row shape, not two.
 */
export function rankRow(row, gates) {
  if (!row || typeof row !== 'object') return null;
  const axis = strOrEmpty(row.axis);
  const value = strOrEmpty(row.value);
  if (axis === '' && value === '') return null;
  const found = row.found && typeof row.found === 'object' ? row.found : {};
  const clean = row.clean_scanned && typeof row.clean_scanned === 'object' ? row.clean_scanned : null;
  return {
    axis,
    key: value || axis,
    label: strOrNull(row.label) || value || axis,
    term: axisTerm(axis) || axis,
    about: strOrNull(row.about),
    family: rowFamily(row),
    inFound: rateReading(found.n, found.of, '난 쪽 분모 없음'),
    inClean: clean ? rateReading(clean.n, clean.of, '안 난 쪽 분모 없음')
      : rateReading(null, null, '대조군 없음'),
    hasClean: !!clean,
    // 효과 크기는 R7의 축이다. 지금은 서버가 실으면 그대로 읽고, 안 실으면
    // 열 자체가 「미착지」로 선다 — 클라가 계산해 채우지 않는다.
    effect: numOrNull(row.enrichment),
    effectDeclared: row.enrichment !== undefined && row.enrichment !== null,
    gates: rowGates(row, gates),
    // 서버의 구조화된 사유. 산문 파싱 금지 (R-C).
    reason: strOrNull(row.reason),
    evidenceCount: numOrNull(row.evidence_ref_count),
  };
}

/**
 * Every ranking row, IN THE SERVER'S ORDER.
 *
 * 🔴 THE CLIENT DOES NOT SORT. Ranking is 설명력 순 — lexicographic over the gate
 * verdicts with effect size as the tiebreak — and that is R3's axis, computed
 * where the gates are computed. A client-side sort now would be a SECOND ranking
 * rule that disagrees with the server's the day R3 lands, and the reader would
 * have no way to tell which one they were looking at.
 */
export function rankRows(body, gates) {
  const raw = body && Array.isArray(body.factors) ? body.factors : null;
  if (!raw) return { declared: false, rows: [] };
  const rows = [];
  for (const r of raw) {
    const read = rankRow(r, gates);
    if (read) rows.push(read);
  }
  return { declared: true, rows };
}

// ── 조사 이력 ────────────────────────────────────────────────

/**
 * 「이 랏에 이미 물어본 질문과 그 답」.
 *
 * 🔴 EMPTY IS THE EXPECTED STATE TODAY AND IT MUST STILL BE A SENTENCE. The
 * write axis (R6, `collect_request`) has not landed, so nothing has been issued
 * against any lot. A panel that hides itself when empty would teach the operator
 * that this screen has no such section — and the whole point of the section is
 * 「같은 질문 두 번 사지 않기」, which only works if it is visibly always there.
 *
 * 🔴 AND THE TWO NOTHINGS ARE DIFFERENT. `investigations: []` means the server
 * looked and this lot has none; no key at all means the axis is not deployed.
 * Both render 「발급된 질문 없음」 — because both are true — but only the second
 * says why the machine cannot yet answer.
 */
export function investigationLog(body) {
  const raw = body && Array.isArray(body.investigations) ? body.investigations : null;
  if (!raw) return { declared: false, items: [] };
  const items = [];
  for (const r of raw) {
    if (!r || typeof r !== 'object') continue;
    const id = strOrNull(r.id) || strOrNull(r.request_id);
    const question = strOrNull(r.question) || strOrNull(r.summary);
    if (!id && !question) continue;
    items.push({
      id,
      kind: strOrNull(r.kind),
      kindLabel: strOrNull(r.kind_label) || strOrNull(r.kind),
      question,
      openedAt: r.opened_at ? instantText(r.opened_at) : null,
      // 열림/닫힘은 서버의 낱말. 이 파일은 상태 어휘를 모른다.
      state: strOrNull(r.state),
      stateLabel: strOrNull(r.state_label) || strOrNull(r.state),
      answer: strOrNull(r.answer),
      answeredAt: r.answered_at ? instantText(r.answered_at) : null,
      // 재발행 가드 3층의 ③ — 「알고도 다시 물었다」가 원장에 남은 자리.
      reissueOf: strOrNull(r.reissue_of),
      href: strOrNull(r.href),
    });
  }
  return { declared: true, items };
}

// ── the whole answer ─────────────────────────────────────────

/**
 * Everything the reference view renders, from one response and the question.
 *
 * `body === null` is not an error state: it is the frame painting before (or
 * without) an answer, and every section below knows how to say what it does not
 * know. That is what lets this screen land ahead of R1.
 */
export function lotModel({ body, question, kind } = {}) {
  const q = question || { lot: '', slot: '', finding: '' };
  const axis = gateAxis(body);
  return {
    question: q,
    // 🔴 EMPTY LOT IS CONTENT. "no lot in the URL" is a real state of this view
    // and it renders as an instruction, not as a blank screen or an error.
    asked: !!q.lot,
    state: lotState(body),
    answered: !!body,
    kind: kind || strOrNull(q.finding),
    generatedAt: body && body.generated_at ? instantText(body.generated_at) : null,
    identity: lotIdentity(body, q),
    summary: summaryRows(body),
    coverage: coverageRows(body),
    lineage: lineageSummary(body),
    gates: axis,
    rank: rankRows(body, axis.gates),
    investigations: investigationLog(body),
  };
}
