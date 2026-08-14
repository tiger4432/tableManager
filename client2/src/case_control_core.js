// ============================================================
// case_control_core.js — how a case-control question about ONE finding kind
// reads on screen.
//
// PURE. No DOM, no network. It runs under bare node, so
// `tests/case_control_harness.mjs` scores THESE functions rather than a copy of
// them — the same discipline `ledger_trace_core.js` is held to.
//
// 🔴 THIS MODULE DECIDES NOTHING ABOUT THE LEDGER. The server counts the
// populations and computes the contrast; everything here maps that answer onto
// words, tones and — above all — onto the refusal to print a number without the
// denominator it came from.
//
// WHAT IT MUST MAKE VISIBLE (product owner, 2026-08-14):
//
//   Q1  🔴 NO NUMBER WITHOUT ITS DENOMINATOR. `rateReading` is the whole of that
//       rule: it CANNOT return a percentage without a denominator, it returns a
//       refusal instead. A screen that prints "4.2%" with nothing under it is
//       the defect this console exists to retire.
//
//   Q2  🔴 THE POPULATION IS THREE COUNTS, NOT TWO. found / clean-scanned /
//       never-scanned. Never-scanned is NEITHER, and it is NOT in the
//       denominator — folding it into clean would inflate every denominator on
//       the screen and deflate every rate, silently. `populationSplit` keeps it
//       out of `denominator` and hands it back as its own number.
//
//   Q3  🔴 VOID IS A DEFAULT VALUE, NEVER A BRANCH. `DEFAULT_FINDING_KIND` is
//       the single place the string appears in this client, and it appears as a
//       FALLBACK, never in a comparison. Grep this whole module for `'void'`:
//       one hit, one line, and it is an assignment. If a second one ever
//       appears next to `===`, the kind picker has become a lie and the
//       generalisation the owner asked for is gone.
//
//   Q4  🔴 「분모 없음 — 대조 불가」 IS CONTENT, NOT AN ERROR STATE. A finding
//       kind whose signature declares no `observed_by` method has no
//       inspection_run to divide by, and that is a FACT ABOUT THE KIND, not a
//       failure of the console. Same discipline as `nothingVerdict`'s four
//       nothings.
// ============================================================

// Reused rather than re-spelled. 가정 vs 근거, and the instant that never moves
// the clock, are already decided for this page — a second spelling here would
// let the two screens disagree about what an assumption looks like.
import { basisLabel, isConvention, instantText, nodeId, nodeText } from './ledger_trace_core.js';

export { basisLabel, isConvention, instantText };

// ─────────────────────────────────────────────────────────────
// 🔴 THE ONE APPEARANCE OF THE WORD. It is a fallback for the first paint,
// before the catalog answers, and for a server too old to carry the catalog at
// all. Every other kind decision in this file goes through `pickKind`, which
// prefers what the OPERATOR asked for, then what the CATALOG declares, then the
// catalog's first row — three data-driven answers ahead of this constant.
// ─────────────────────────────────────────────────────────────
export const DEFAULT_FINDING_KIND = 'void';

//: The pinned `state` values of the kind catalog, same vocabulary as
//: `GET /api/ledger/coverage`. Anything else degrades to 'unknown' and NEVER to
//: 'ready' — a server that cannot be read must not be able to claim it has data.
const CATALOG_STATES = new Set(['absent', 'empty', 'ready']);

//: The slice axes the 현황판 offers. An axis the wire does not carry simply does
//: not appear; the list is here so the ORDER on screen is stable and so an
//: unknown axis from the wire still renders under its own raw name rather than
//: being dropped.
//:
//: 🔴 `class` IS AN AXIS LIKE THE OTHERS, AND IT LEADS. The defect's class
//: (interfacial / bulk / edge for a void) is what the operator is actually
//: contrasting on — 「계면 보이드만 이 장비에 몰림」 is the finding, and it is
//: invisible if class is folded into the total. It arrives inside the `observed`
//: atom this console already receives (`MI_LEDGER_SCHEMA_PROPOSAL` §6-quater:
//: `{finding_kind: void, class: interfacial, …}`), so it costs no second query.
//:
//: 🔴 AND ITS VALUES ARE NEVER HARDCODED — same rule, same reason as
//: `finding_kind`. The set is CLOSED PER KIND and declared in the vocabulary
//: signature, so switching kinds must switch the class list. A literal list of
//: void's classes in this file would be the generalisation lost a second time,
//: one level down.
export const SLICE_AXES = [
  { axis: 'class', term: '클래스' },
  { axis: 'eqp', term: '설비' },
  { axis: 'recipe', term: '레시피' },
  { axis: 'lot', term: '랏' },
  { axis: 'window', term: '기간' },
];

const AXIS_TERM = new Map(SLICE_AXES.map((a) => [a.axis, a.term]));

/**
 * A number, or null — and `null` INPUT IS NULL OUTPUT.
 *
 * 🔴 THIS EXISTS BECAUSE `Number(null) === 0`. Every "is this field reported?"
 * check in this file was written as `Number.isFinite(Number(v))`, and that reads
 * an explicitly-null field — the exact way a server says "I did not count this" —
 * as a MEASURED ZERO. The console's whole discipline is that an absent count is
 * not a zero, and the idiom it was built on quietly inverted it: a slice with a
 * null denominator rendered 「검사 0회」, and a response carrying no
 * `denominator` object rendered 「분모 0」 as if someone had counted.
 *
 * `''` goes the same way: an empty string is not a count either.
 */
function numOrNull(v) {
  if (v === null || v === undefined || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/** The Korean term for a slice axis, or the axis name itself. Never a guess. */
export function axisTerm(axis) {
  const key = axis == null ? '' : String(axis);
  return AXIS_TERM.get(key) || key || '?';
}

// ── the question the operator asks ───────────────────────────

//: The URL parameters that narrow the question. `finding` is the SUBJECT and is
//: handled separately; these are the slices, and they are listed once so the
//: reader, the writer and the "remove this slice" link cannot drift apart.
export const SLICE_PARAMS = ['class', 'eqp', 'recipe', 'lot', 'from', 'to'];

/**
 * `URLSearchParams` -> the console's question.
 *
 * `finding` may be absent — that is the landing screen, and `pickKind` resolves
 * it against the catalog rather than this function guessing.
 */
export function parseConsoleQuery(params) {
  const get = (k) => {
    if (!params) return '';
    const v = typeof params.get === 'function' ? params.get(k) : params[k];
    return v == null ? '' : String(v).trim();
  };
  const slices = {};
  for (const key of SLICE_PARAMS) {
    const v = get(key);
    if (v !== '') slices[key] = v;
  }
  return { finding: get('finding'), slices };
}

/**
 * The console's question -> a query string. ONE spelling, so a slice link, the
 * kind picker and the fetch cannot disagree about what was asked.
 *
 * `omit` drops one slice — that is how a slice chip becomes a "remove me" link
 * without a control: the answer to this screen is a URL, so undoing a filter is
 * a URL too.
 */
export function consoleQuery({ finding, slices } = {}, omit) {
  const parts = [];
  const kind = finding == null ? '' : String(finding);
  if (kind !== '') parts.push(`finding=${encodeURIComponent(kind)}`);
  const bag = slices && typeof slices === 'object' ? slices : {};
  for (const key of SLICE_PARAMS) {
    if (key === omit) continue;
    const v = bag[key];
    if (v == null || String(v) === '') continue;
    parts.push(`${key}=${encodeURIComponent(String(v))}`);
  }
  return parts.join('&');
}

/** The same question with ONE slice added — how a 현황판 row becomes a link. */
export function withSlice(question, key, value) {
  const slices = Object.assign({}, (question && question.slices) || {});
  slices[key] = String(value == null ? '' : value);
  return { finding: (question && question.finding) || '', slices };
}

// ── the kind catalog — what can be asked at all ──────────────

/**
 * The catalog's `state`, or 'unknown'.
 *
 * Same degradation rule as `coverageState`: an unrecognised state, or no
 * catalog at all, is 'unknown' and never 'ready'.
 */
export function catalogState(body) {
  const s = body && body.state ? String(body.state) : '';
  return CATALOG_STATES.has(s) ? s : 'unknown';
}

/**
 * The registered finding kinds, each with the atom count that tells the
 * operator whether it has data at all.
 *
 * 🔴 `atoms` IS NULL WHEN THE WIRE DID NOT CARRY IT, NEVER 0. "0 observations"
 * is a measurement — this kind is declared and nothing was ever seen — and an
 * absent field is not one. The same prohibition `coverageFacts` already holds.
 *
 * 🔴 `hasDenominator` IS READ OFF `observed_by`, WHICH IS THE KIND'S SIGNATURE.
 * A kind observed by a declared inspection method has an `inspection_run`
 * population to divide by; a kind nobody declared a method for (an OM operator
 * happening to look) does not, and the contrast panel says so as CONTENT.
 */
export function kindCatalog(body) {
  const state = catalogState(body);
  const rows = body && Array.isArray(body.kinds) ? body.kinds : [];
  const kinds = [];
  for (const row of rows) {
    if (!row || typeof row !== 'object') continue;
    const kind = row.kind == null ? '' : String(row.kind);
    if (kind === '') continue;
    const methods = Array.isArray(row.observed_by)
      ? row.observed_by.filter((m) => m != null && String(m) !== '').map(String)
      : [];
    // 🔴 THE KIND'S OWN CLASS SET, FROM THE KIND'S OWN SIGNATURE. Closed and
    // add-only per `MI_LEDGER_SCHEMA_PROPOSAL` §6-quater, and per KIND — void's
    // interfacial/bulk/edge is not crack's set. Read here so the console's class
    // axis follows the picker automatically: change the kind, change the list.
    // An empty array means the kind declares no classes, which is a fact about
    // the kind and renders as no class axis at all — not as a missing feature.
    const classes = Array.isArray(row.classes)
      ? row.classes.filter((c) => c != null && String(c) !== '').map(String)
      : [];
    kinds.push({
      kind,
      label: row.label == null || String(row.label) === '' ? kind : String(row.label),
      atoms: numOrNull(row.atoms),
      methods,
      classes,
      runs: numOrNull(row.runs),
      // 🔴 THE SERVER'S FIELD, NOT A RE-DERIVATION. This read `methods.length > 0`
      // for one round, and the two answers agreed — which is exactly what made it
      // dangerous rather than safe. `server/finding_kinds.py` owns the rule
      // ("does this kind have an inspection_run population"), and a second
      // implementation of it here is a copy of the same truth that can drift the
      // day the server's rule grows a clause the count cannot express. That is
      // the defect shape this whole console spent the day removing.
      //
      // The fallback is for a server too old to send the field, and it degrades
      // to the count rather than to `true`: a kind that cannot be judged must not
      // be able to claim it has a denominator.
      hasDenominator: typeof row.has_denominator === 'boolean'
        ? row.has_denominator
        : methods.length > 0,
    });
  }
  const declaredDefault = body && body.default != null ? String(body.default) : '';
  return { state, kinds, defaultKind: declaredDefault };
}

/**
 * WHICH kind this screen is about.
 *
 * 🔴 FOUR SOURCES, IN ORDER, AND THE CONSTANT IS LAST. What the operator asked
 * for wins; then what the catalog declares as its default; then the catalog's
 * first row; and only with no catalog at all does `DEFAULT_FINDING_KIND` speak.
 * That ordering is the generalisation: swap the fixture's kinds and the console
 * follows without a line changing.
 *
 * An asked-for kind is honoured even when the catalog does not list it — the
 * catalog can be stale, and refusing to ask would hide data that exists. The
 * screen says so instead (`kindStanding`).
 */
export function pickKind(catalog, asked) {
  const want = asked == null ? '' : String(asked).trim();
  if (want !== '') return want;
  const cat = catalog && typeof catalog === 'object' ? catalog : null;
  if (cat && cat.defaultKind) return cat.defaultKind;
  if (cat && Array.isArray(cat.kinds) && cat.kinds.length) return cat.kinds[0].kind;
  return DEFAULT_FINDING_KIND;
}

/** Is the chosen kind one the catalog knows? Content, not an error. */
export function kindStanding(catalog, kind) {
  const kinds = catalog && Array.isArray(catalog.kinds) ? catalog.kinds : [];
  const row = kinds.find((k) => k.kind === kind) || null;
  if (row) return { known: true, row };
  if (catalogState(catalog) !== 'ready') return { known: false, row: null, reason: null };
  return { known: false, row: null, reason: '어휘 미등재 종류 — 카탈로그에 없음' };
}

// ── 🔴 THE RULE THIS FILE EXISTS FOR ─────────────────────────

/**
 * A count over a denominator, or a REFUSAL. There is no third answer, and there
 * is no way to get a percentage out of this function without handing it one.
 *
 * 🔴 THE REFUSAL IS THE PRODUCT. `{ok: false}` carries the reason so the screen
 * can print 「분모 없음 — 대조 불가」 WITH why, instead of an empty cell that
 * reads like a zero. A denominator of 0 is also a refusal, and a different one:
 * nothing was inspected, so the rate is undefined rather than missing.
 *
 * `text` is built here rather than in the view so exactly one string exists per
 * rate and the harness can score it.
 */
export function rateReading(numerator, denominator, reason) {
  const n = numOrNull(numerator);
  const d = numOrNull(denominator);
  if (n === null) {
    return { ok: false, n: null, d, rate: null,
      why: reason || '건수 미보고', text: '—' };
  }
  if (d === null) {
    return { ok: false, n, d: null, rate: null,
      why: reason || '분모 없음', text: `${n}건 · 분모 없음` };
  }
  if (d <= 0) {
    return { ok: false, n, d, rate: null,
      why: reason || '검사 0회 — 율 정의 안 됨', text: `${n}/${d}` };
  }
  const rate = n / d;
  return { ok: true, n, d, rate, text: `${percentText(rate)} · ${n}/${d}` };
}

/**
 * A rate as a percentage, with enough places to stay honest at low rates.
 *
 * 🔴 A DEFECT RATE IS SMALL BY CONSTRUCTION. Rounding 0.4% to 0% prints "no
 * defects" over six of them; that is the number lying, not the number being
 * tidy. So below 10% it keeps two decimals, and a non-zero rate can never
 * render as 0.
 */
export function percentText(rate) {
  const r = Number(rate);
  if (!Number.isFinite(r)) return '—';
  const pct = r * 100;
  if (pct === 0) return '0%';
  if (pct < 0.01) return '<0.01%';
  if (pct < 10) return `${pct.toFixed(2)}%`;
  if (pct < 100) return `${pct.toFixed(1)}%`;
  return `${Math.round(pct)}%`;
}

/**
 * The denominator itself, as a statement about the KIND.
 *
 * 🔴 THREE STANDINGS, AND THE MIDDLE ONE IS THE HONEST DEGRADATION. `present`
 * means the kind declares an observation method and the server counted the
 * runs. `undeclared` means the kind's signature carries no `observed_by`, so
 * there is no run population to divide by and never will be — that is CONTENT.
 * `unreported` means the kind should have one and this response did not carry
 * it, which is a gap in the answer, not in the kind.
 */
export function denominatorReading(body, kindRow) {
  // 🔴 THE SERVER SAYS WHICH STANDING THIS IS, AND IT SAYS WHY. `denominator` is
  // `{state: "ready"|"absent", basis, methods, reason, message}` and the reason is a
  // STRUCTURED word (`no_observed_by_declared`, `no_runs_for_methods`,
  // `run_relation_absent`), never something to be read out of the message. The
  // message is the server's prose and goes out verbatim — a diagnosis that hides
  // what the server said cannot be checked against the server.
  const den = body && body.denominator && typeof body.denominator === 'object'
    ? body.denominator : null;
  const methods = den && Array.isArray(den.methods)
    ? den.methods.filter((m) => m != null && String(m) !== '').map(String)
    : (kindRow && Array.isArray(kindRow.methods) ? kindRow.methods : []);
  const scanned = body && body.populations && body.populations.scanned
    ? numOrNull(body.populations.scanned.count) : null;

  if (den && String(den.state) === 'ready') {
    return {
      standing: 'present',
      runs: scanned,
      methods,
      reason: null,
      basis: den.basis ? String(den.basis) : 'inspection_run',
      title: scanned === null ? '분모 있음' : `분모 ${scanned}`,
      detail: `${den.basis ? String(den.basis) : 'inspection_run'}${methods.length ? ` · ${methods.join(' · ')}` : ''}`,
    };
  }
  if (den) {
    return {
      standing: 'undeclared', runs: null, methods, basis: null,
      reason: den.reason == null ? null : String(den.reason),
      title: '분모 없음 — 대조 불가',
      // The server's own sentence. It already distinguishes "this kind declares no
      // observation method" from "the run table is not deployed" from "no runs in
      // this window", which is three facts one client sentence would flatten.
      detail: den.message == null || String(den.message) === ''
        ? '검사 모집단이 정의되지 않음' : String(den.message),
    };
  }
  // The kind itself says there is nothing to divide by.
  if (kindRow && kindRow.hasDenominator === false) {
    return {
      standing: 'undeclared', runs: null, methods: [], basis: null, reason: null,
      title: '분모 없음 — 대조 불가',
      detail: '이 종류는 observed_by 미선언 — 검사 모집단이 정의되지 않음',
    };
  }
  return {
    standing: 'unreported', runs: null, methods, basis: null, reason: null,
    title: '분모 없음 — 대조 불가',
    detail: '응답에 denominator 없음',
  };
}

// ── 🔴 THE POPULATION IS THREE COUNTS ────────────────────────

/**
 * found / clean-scanned / never-scanned, and the denominator that is NOT their
 * sum.
 *
 * 🔴 NEVER-SCANNED IS NEITHER, AND IT IS OUTSIDE THE DENOMINATOR. A wafer
 * nobody inspected is not evidence of absence; adding it to `clean` would make
 * every rate on this screen smaller by exactly the amount of inspection that
 * did not happen — a coverage gap rendered as a quality improvement. So:
 *
 *     denominator = found + clean          (the inspected population)
 *     unscanned                            (its own number, its own line)
 *     total = found + clean + unscanned    (the reachable population)
 *
 * Each count is null when the wire did not carry it, and a null count makes the
 * denominator null too rather than a smaller number that looks measured.
 */
export function populationSplit(body) {
  // 🔴 THE WIRE'S OWN NAMES (`server/ledger_siblings.py::_populations`):
  //   populations: {found, scanned, clean_scanned, never_scanned, universe}
  // each `{count, unit}` and each ABSENT when the server could not establish it.
  // `clean_scanned` is `scanned - found`, computed there, so this file does not
  // re-derive it — a second spelling of that subtraction is how the two layers
  // start disagreeing about what "clean" means.
  const pop = body && body.populations && typeof body.populations === 'object'
    ? body.populations : {};
  const count = (slot) => (slot && typeof slot === 'object' ? numOrNull(slot.count) : null);
  const found = count(pop.found);
  const clean = count(pop.clean_scanned);
  const unscanned = count(pop.never_scanned);
  // 🔴 THE DENOMINATOR IS `scanned`, WHICH THE SERVER COUNTED — not `found + clean`
  // added up here. They are the same number by construction and that is exactly why
  // adding them here would be undetectable when it stopped being true.
  const scanned = count(pop.scanned);
  const denominator = scanned !== null ? scanned
    : ((found === null || clean === null) ? null : found + clean);
  const universe = count(pop.universe);
  const total = universe !== null ? universe
    : ((denominator === null || unscanned === null) ? null : denominator + unscanned);
  // 🔴 RUNS THAT SCANNED SOMETHING OUTSIDE THE DECLARED POPULATION. Live on this
  // box: 2,500 of them. They are inside `scanned` and outside `universe`, so the
  // three counts do NOT close against the total and a reader who adds them up
  // gets a discrepancy with no explanation. The server names it; the screen shows
  // it rather than letting the arithmetic quietly fail to balance.
  const outside = pop.scanned_outside_universe && typeof pop.scanned_outside_universe === 'object'
    ? pop.scanned_outside_universe : null;
  return {
    found, clean, unscanned, denominator, total,
    outsideUniverse: outside ? {
      count: numOrNull(outside.count),
      message: outside.message == null ? null : String(outside.message),
    } : null,
    unit: (pop.found && pop.found.unit) || (body && body.finding && body.finding.population_unit) || null,
    rate: rateReading(found, denominator),
  };
}

/**
 * The three counts as the three rows the panel renders. ONE list, so the order
 * and the words cannot drift between the panel and the harness.
 *
 * 🔴 `unscanned` CARRIES `inDenominator: false` AND THE PANEL PRINTS IT. The
 * number alone does not say it was excluded, and a reader who assumes it was
 * included reads every rate on the screen wrong.
 */
export function populationRows(split) {
  const s = split || {};
  return [
    { key: 'found', term: '발견', n: s.found, inDenominator: true,
      note: '이 종류가 관측된 검사' },
    { key: 'clean', term: '깨끗-스캔됨', n: s.clean, inDenominator: true,
      note: '검사했고 0건' },
    { key: 'unscanned', term: '미스캔', n: s.unscanned, inDenominator: false,
      note: '검사 안 함 — 분모 제외' },
  ];
}

// -- the factor rows: ONE list from the server, three framings on screen -----
//
// 🔴 THE SERVER RETURNS ONE `factors` LIST AND EVERY ROW CARRIES BOTH SIDES
// (`server/ledger_siblings.py::_score`: "Both denominators, on every row"). The
// 현황판 groups it by axis, 공통점 reads the found side against the clean one,
// and 차이점 reads the same rows through each row's OWN `enrichment_state`. That
// is why this console makes ONE call: three panels off three re-readings of one
// answer cannot disagree with each other about the same population.

//: The server's verdict words (`ENRICHED, FLAT, DEPLETED, UNDETERMINABLE`).
//: CONSUMED, never re-derived — the ranking is an interval lower bound computed
//: from counts this client does not have, and a second spelling of it here would
//: be a second statistician.
export const ENRICHMENT_LABEL = {
  enriched: { text: '농축', tone: 'up' },
  depleted: { text: '희박', tone: 'down' },
  flat: { text: '차이 없음', tone: 'flat' },
  undeterminable: { text: '판정 불가', tone: 'gap' },
};

/**
 * One `factors[]` row, read.
 *
 * 🔴 BOTH SIDES GO THROUGH `rateReading`, SO NEITHER CAN REACH THE SCREEN
 * WITHOUT ITS DENOMINATOR. `found` is `{n, of, rate}` and `clean_scanned` is the
 * same or `null` — null meaning there IS no clean population to compare against,
 * which is a refusal with a reason and not a zero.
 */
export function factorRow(row) {
  if (!row || typeof row !== 'object') return null;
  const axis = row.axis == null ? '' : String(row.axis);
  const value = row.value == null ? '' : String(row.value);
  if (axis === '' || value === '') return null;
  const found = row.found && typeof row.found === 'object' ? row.found : {};
  const clean = row.clean_scanned && typeof row.clean_scanned === 'object'
    ? row.clean_scanned : null;
  const state = row.enrichment_state == null ? 'undeterminable' : String(row.enrichment_state);
  const ci = Array.isArray(row.enrichment_ci) ? row.enrichment_ci.map(numOrNull) : null;
  const refs = Array.isArray(row.evidence_refs) ? row.evidence_refs : [];
  return {
    axis,
    key: value,
    label: row.label == null || String(row.label) === '' ? value : String(row.label),
    term: axisTerm(axis),
    // `about` is a BADGE and never a filter (`ledger_siblings.AttributionSource`):
    // "process" describes what made the part, "inspection" describes the scan that
    // looked at it. Both are real findings and they are DIFFERENT findings — a
    // console that cannot tell them apart reports a scanner artefact as a cause.
    about: row.about == null ? null : String(row.about),
    inFound: rateReading(found.n, found.of, '난 쪽 분모 없음'),
    inClean: clean ? rateReading(clean.n, clean.of, '안 난 쪽 분모 없음')
      : rateReading(null, null, '대조군 없음'),
    hasClean: !!clean,
    enrichment: numOrNull(row.enrichment),
    ci: ci && ci.length === 2 ? ci : null,
    state,
    verdict: ENRICHMENT_LABEL[state] || { text: state, tone: 'gap' },
    // The server's structured word for WHY there is no verdict — never its prose.
    reason: row.reason == null ? null : String(row.reason),
    evidenceRefs: refs.map((r) => (r && r.key != null ? String(r.key) : null)).filter(Boolean),
    evidenceCount: numOrNull(row.evidence_ref_count),
  };
}

/** Every factor the answer carried, in the order the server ranked them. */
export function factorRows(body) {
  const raw = body && Array.isArray(body.factors) ? body.factors : [];
  const out = [];
  for (const row of raw) {
    const read = factorRow(row);
    if (read) out.push(read);
  }
  return out;
}

/**
 * The 현황판: the same rows, grouped by axis.
 *
 * ⚠️ EACH ROW'S FRACTION IS «SHARE OF THE FOUND POPULATION», NOT A DEFECT RATE.
 * `found.of` is the found count, so `5/6` reads "five of the six defects went
 * through B-3" — it is NOT "B-3 has a 4.2% void rate", which would need B-3's own
 * inspected count and the response does not carry one. The panel labels the
 * column accordingly; calling it a rate here would be the screen inventing a
 * denominator, which is the one thing this console exists not to do.
 */
export function sliceRows(body, declaredClasses) {
  const rows = factorRows(body);
  const coverage = axisCoverage(body);
  const byAxis = new Map();
  for (const row of rows) {
    if (!byAxis.has(row.axis)) byAxis.set(row.axis, []);
    byAxis.get(row.axis).push(Object.assign({}, row, { rate: row.inFound }));
  }

  // 🔴 A DECLARED CLASS THE ANSWER NEVER MENTIONED IS STILL WORTH SEEING, AND IT
  // IS NOT A ZERO. The class set is CLOSED per kind, so "which of this kind's
  // classes did not show up" is information — but rendering it as `0` would claim
  // someone counted and found none.
  const declared = Array.isArray(declaredClasses) ? declaredClasses : [];
  if (declared.length) {
    const present = new Set((byAxis.get('class') || []).map((r) => r.key));
    const missing = declared.filter((c) => !present.has(c));
    if (missing.length) {
      if (!byAxis.has('class')) byAxis.set('class', []);
      for (const key of missing) {
        byAxis.get('class').push({
          axis: 'class', key, label: key, term: axisTerm('class'), declared: true,
          inFound: rateReading(null, null, '미보고 — 이 조회에 없음'),
          rate: rateReading(null, null, '미보고 — 이 조회에 없음'),
          hasClean: false, state: 'undeterminable',
          verdict: ENRICHMENT_LABEL.undeterminable, evidenceRefs: [],
        });
      }
    }
  }

  // 🔴 THE AXIS NAME COMES FROM THE SERVER WHEN THE SERVER SENT ONE. `axes[]`
  // declares `bond_eqp` -> 「본딩 장비」 and `scan_recipe` -> 「검사 레시피」, which
  // this client cannot know and must not invent; `SLICE_AXES` only fixes the
  // ORDER of the ones it has an opinion about.
  const group = (axis, rows2) => {
    const cov = coverage.get(axis) || null;
    return {
      axis,
      term: cov && cov.label ? cov.label : axisTerm(axis),
      about: cov ? cov.about : null,
      coveredFound: cov ? cov.coveredFound : null,
      coveredClean: cov ? cov.coveredClean : null,
      rows: rows2,
    };
  };
  const out = [];
  for (const spec of SLICE_AXES) {
    if (byAxis.has(spec.axis)) { out.push(group(spec.axis, byAxis.get(spec.axis))); byAxis.delete(spec.axis); }
  }
  for (const [axis, rows2] of byAxis) out.push(group(axis, rows2));
  return out;
}

/**
 * 공통점: what the found cases share, beside the clean-side rate that says
 * whether sharing it is surprising.
 *
 * 🔴 「6건 중 5건」 IS NOT A FINDING UNTIL THE OTHER SIDE IS BESIDE IT. If 83% of
 * the CLEAN packages also went through B-3, then 5-of-6 is what chance predicts.
 * Server order is kept (ranked by found rate in `intersection`), and NOTHING is
 * dropped here — a `flat` factor belongs in 공통점 precisely because it is the
 * decoy the second column exposes.
 */
export function sharedRows(body) {
  return factorRows(body);
}

/**
 * 차이점: the same rows, read through each row's OWN verdict.
 *
 * 🔴 THE DROP AND THE RANK ARE THE SERVER'S, READ OFF FIELDS. `flat` rows are
 * dropped because the row SAYS it is flat; the order is the interval's lower
 * bound the row CARRIES. `undeterminable` is KEPT — it is a missing judgement,
 * not a judgement of "no difference", and hiding it would make an unmeasurable
 * factor look like a measured non-finding (`ledger_siblings`, the decoy filter).
 */
export function contrastRows(body) {
  // 🔴 ONLY `flat` IS DROPPED — the server's rule exactly (`ledger_siblings`: the decoy
  // filter keeps `undeterminable`). A row whose clean side the server could not
  // establish is a MISSING judgement, not a judgement of "no difference", and dropping
  // it would make an unmeasurable factor look like a measured non-finding.
  const rows = factorRows(body).filter((r) => r.state !== 'flat');
  return rows.slice().sort((a, b) => {
    const al = a.ci ? a.ci[0] : null;
    const bl = b.ci ? b.ci[0] : null;
    if (al === bl) return (b.inFound.n || 0) - (a.inFound.n || 0);
    if (al === null) return 1;
    if (bl === null) return -1;
    return bl - al;
  });
}

/**
 * Per-axis attribution coverage — how much of each population the axis could
 * actually be computed over.
 *
 * 🔴 A FACTOR'S DENOMINATOR AND ITS AXIS'S COVERAGE ARE NOT THE SAME NUMBER, AND
 * THE DIFFERENCE IS INVISIBLE WITHOUT THIS. Live on this box the `bond_eqp` axis
 * covers 44,399 of 46,899 found packages — 2,500 defective packages have NO
 * bonding attribution at all — yet every `bond_eqp` factor row still divides by
 * 46,899. So a factor that is present in EVERY attributable package reads 94.7%,
 * not 100%, and the missing 5.3% is a data gap being rendered as a measured
 * absence. The axis header says the coverage so the reader can tell the two
 * apart.
 */
export function axisCoverage(body) {
  const axes = body && Array.isArray(body.axes) ? body.axes : [];
  const out = new Map();
  for (const ax of axes) {
    if (!ax || typeof ax !== 'object' || ax.name == null) continue;
    const cov = ax.covered && typeof ax.covered === 'object' ? ax.covered : null;
    out.set(String(ax.name), {
      name: String(ax.name),
      label: ax.label == null || String(ax.label) === '' ? String(ax.name) : String(ax.label),
      about: ax.about == null ? null : String(ax.about),
      source: ax.source == null ? null : String(ax.source),
      coveredFound: cov ? numOrNull(cov.found) : null,
      coveredClean: cov ? numOrNull(cov.clean_scanned) : null,
    });
  }
  return out;
}

/** Anything the server wanted to say about this answer that is not a number. */
export function noteRows(body) {
  const notes = body && Array.isArray(body.notes) ? body.notes : [];
  const out = [];
  for (const n of notes) {
    if (!n || typeof n !== 'object') continue;
    const note = n.note == null ? '' : String(n.note);
    if (note === '') continue;
    out.push({
      note,
      // The server's sentence when it wrote one, its structured word otherwise.
      text: n.message == null || String(n.message) === '' ? note : String(n.message),
      relation: n.relation == null ? null : String(n.relation),
    });
  }
  return out;
}

// ── 🔴 THE UNIFIED FACT CHIP — ONE RENDERER, NOT THREE ───────
//
// `measured` (MI said a number), `observed` (an inspection said a finding) and
// `processed_with` (a step said an equipment/recipe) are ONE VOCABULARY by
// construction — that is what the ontology bought. Three renderers would let
// them drift into three screens, and a reader comparing an MI number against a
// process condition would be comparing two layouts.
//
// So one reading, one chip, and the PREDICATE is a field on it rather than a
// branch in the caller.

//: 🔴 THE READING TABLE — WHICH FIELD IS THE NAME AND WHICH IS THE VALUE, PER
//: PREDICATE, AS DATA. This is what makes ONE renderer possible instead of
//: three. The three atoms do not carry the same field names —
//:
//:   measured        {quantity, value, unit, eqp, method, recipe, frame,
//:                    die_x, die_y, inchip_x, inchip_y, structure?, stat?, n?}
//:   observed        {finding_kind, severity_word?, zone?|{frame,die_x,die_y},
//:                    note?}
//:   processed_with  {step, eqp, recipe:{recipe_id,rev}, chamber?,
//:                    params_actual:{…}}   (+ signature `step_family`)
//:
//: (`docs/architecture/MI_LEDGER_SCHEMA_PROPOSAL.md` §measured/§observed,
//:  `docs/architecture/PHYSICS_ONTOLOGY_SETUP.md` §processed_with)
//:
//: — but they answer the SAME three questions: what kind of statement is this,
//: what is it about, what did it say. A predicate this table does not know still
//: renders, under its own name, through the same generic path: a chip that
//: disappears because the vocabulary grew is worse than one that reads oddly.
export const FACT_SPEC = {
  measured: { term: '계측', name: 'quantity', value: 'value' },
  observed: { term: '관측', name: 'finding_kind', value: 'severity_word' },
  processed_with: { term: '공정', name: 'step', value: null },
};

//: Payload keys that are NEVER meta chips — they were already consumed as the
//: name, the value, the unit, or they are free text the reader gets verbatim.
const CONSUMED_KEYS = new Set([
  'quantity', 'value', 'unit', 'finding_kind', 'severity_word', 'step', 'note',
]);

//: Payload keys whose Korean term is fixed for every predicate. Anything not
//: here keeps its wire name — a qualifier the vocabulary grows tomorrow shows up
//: as itself rather than vanishing.
//:
//: 🔴 `class` READS 「클래스」 AND NOTHING STRONGER. It is a CLASSIFICATION, not a
//: verdict (§6-quater: "class ≠ 판정 … 「합격인가」는 여전히 저장 금지"). Words
//: like 등급 or 판정 would make a claim about what the ledger is forbidden to
//: hold, on a screen whose whole discipline is not overstating what was said.
const META_TERM = {
  class: '클래스',
  eqp: '설비', equipment: '설비', recipe: '레시피', method: '방법', chamber: '챔버',
  step: '스텝', step_family: '구분', lot: '랏', wafer: '웨이퍼', frame: '프레임',
  zone: '영역', structure: '구조', stat: '통계', n: 'n',
};

/**
 * One fact atom -> the chip. ONE function for all three predicates.
 *
 * Every field is null when the wire did not carry it, and the view omits nulls
 * rather than printing a dash — an absent qualifier is not a measured absence.
 *
 * 🔴 THE SPEAKER BADGE IS NOT OPTIONAL. The product owner's acceptance criterion
 * is denominator + evidence + speaker on every number, and a fact chip is a
 * number. `speaker` is WHO said it (`source.who`); `evidence` is what it can be
 * checked against (`source.raw_ref` / `event_id`); `basis` is WHAT IT RESTS ON
 * (측정 vs 가정), read off the FIELD by the same function the lineage screen's
 * hop chips use — one spelling of 가정, so the two screens cannot disagree about
 * what an assumption looks like.
 *
 * 🔴 `note` IS RENDERED AND NEVER PARSED. It is the observer's own words
 * (R-C: 산문 파싱 금지); a screen that greps it for severity invents a
 * measurement out of a sentence.
 */
export function factChip(fact) {
  if (!fact || typeof fact !== 'object') return null;
  const predicate = fact.predicate == null ? '' : String(fact.predicate);
  const spec = FACT_SPEC[predicate] || null;
  const term = spec ? spec.term : (predicate || '사실');

  // The payload may arrive flattened onto the atom or nested under `payload` /
  // `qualifiers`. Both are read; neither is required.
  const payload = Object.assign(
    {},
    fact.payload && typeof fact.payload === 'object' ? fact.payload : {},
    fact.qualifiers && typeof fact.qualifiers === 'object' ? fact.qualifiers : {},
    fact);

  const name = spec && spec.name ? firstText(payload[spec.name]) : null;
  const value = spec && spec.value ? firstText(payload[spec.value]) : null;
  const unit = firstText(payload.unit);

  const meta = [];
  const push = (key, raw) => {
    const text = valueText(raw);
    if (text === null) return;
    meta.push({ key, term: META_TERM[key] || key, text });
  };
  // Declared order first, so two chips of the same predicate line up. `class`
  // leads: on an `observed` chip it is the thing the operator is contrasting on,
  // and it arrives in the SAME utterance as the finding (§6-quater ①) — same
  // atom, same speaker, no second lookup.
  const ORDERED = ['class', 'eqp', 'equipment', 'recipe', 'method', 'chamber', 'step_family'];
  for (const key of ORDERED) {
    if (key in payload && !(spec && spec.name === key)) push(key, payload[key]);
  }
  const seen = new Set(ORDERED);
  for (const [key, raw] of Object.entries(payload)) {
    if (seen.has(key) || CONSUMED_KEYS.has(key)) continue;
    if (key === 'predicate' || key === 'subject' || key === 'payload' || key === 'qualifiers') continue;
    if (key === 'source' || key === 'basis' || key === 'occurred_at' || key === 'event_id') continue;
    if (spec && (key === spec.name || key === spec.value)) continue;
    push(key, raw);
  }

  const subject = fact.subject ? nodeId(fact.subject) : null;
  return {
    predicate,
    term,
    name: name || null,
    value,
    unit,
    subject,
    meta,
    // 🔴 Verbatim. The observer's sentence is content, not a field to mine.
    note: firstText(payload.note),
    at: fact.occurred_at ? instantText(fact.occurred_at) : null,
    speaker: speakerBadge(fact),
    evidence: evidenceRef(fact),
    basis: basisLabel(factBasis(fact)),
  };
}

/**
 * A payload value as one line of text. Objects get the two shapes the ontology
 * actually declares — `recipe: {recipe_id, rev}` and `params_actual: {…}` —
 * and anything else is JSON rather than `[object Object]`, because a chip that
 * renders a shape nobody anticipated as a placeholder hides that data arrived.
 */
export function valueText(raw) {
  if (raw == null) return null;
  if (typeof raw === 'string') return raw.trim() === '' ? null : raw.trim();
  if (typeof raw === 'number' || typeof raw === 'boolean') return String(raw);
  if (Array.isArray(raw)) {
    const parts = raw.map(valueText).filter((s) => s !== null);
    return parts.length ? parts.join(' · ') : null;
  }
  if (typeof raw === 'object') {
    if (raw.recipe_id != null) {
      const rev = raw.rev == null || String(raw.rev) === '' ? '' : `@${raw.rev}`;
      return `${raw.recipe_id}${rev}`;
    }
    const parts = [];
    for (const [k, v] of Object.entries(raw)) {
      const t = valueText(v);
      if (t !== null) parts.push(`${k}=${t}`);
    }
    return parts.length ? parts.join(' · ') : null;
  }
  return null;
}

/**
 * What this fact can be CHECKED against. `raw_ref` is the row in the source
 * system; `event_id` is the atom in the ledger. Both are printed when present —
 * "evidence" in the acceptance criterion means a reader can go look.
 */
export function evidenceRef(fact) {
  const source = fact && fact.source && typeof fact.source === 'object' ? fact.source : {};
  const raw = firstText(source.raw_ref, fact && fact.raw_ref);
  const event = firstText(fact && fact.event_id);
  if (!raw && !event) return null;
  return { rawRef: raw, eventId: event, text: [raw, event].filter(Boolean).join(' · ') };
}

/** `basis` off the FIELD, exactly as the lineage screen reads it. Never prose. */
function factBasis(fact) {
  const b = fact && fact.basis;
  if (!b || typeof b !== 'object') return null;
  const name = b.name == null ? '' : String(b.name);
  if (name === '') return null;
  return { kind: b.kind == null ? '' : String(b.kind), name };
}

/**
 * WHO said this. Absent is 'unknown' and renders as 「출처 미상」 — an unattributed
 * number is exactly the thing the acceptance criterion forbids shipping, so the
 * screen says the attribution is missing rather than hiding that it is.
 */
export function speakerBadge(fact) {
  const source = fact && fact.source && typeof fact.source === 'object' ? fact.source : null;
  // `source.who` is the envelope's declared field
  // (`MI_LEDGER_SCHEMA_PROPOSAL.md`: `source{who, translator_ver, raw_ref}`).
  // A bare string `source` is accepted too — an older emitter, not a new spelling.
  const who = firstText(
    source && source.who,
    typeof (fact && fact.source) === 'string' ? fact.source : null,
    fact && fact.speaker);
  if (!who) return { kind: 'unknown', text: '출처 미상' };
  const ver = firstText(source && source.translator_ver);
  return { kind: 'source', text: ver ? `${who} · ${ver}` : who, who, translatorVer: ver };
}

function firstText(...vals) {
  for (const v of vals) {
    if (v == null) continue;
    const s = String(v).trim();
    if (s !== '') return s;
  }
  return null;
}

/** The facts of one case, as chips. Nulls dropped, order preserved. */
export function factChips(facts) {
  const list = Array.isArray(facts) ? facts : [];
  const out = [];
  for (const f of list) {
    const chip = factChip(f);
    if (chip) out.push(chip);
  }
  return out;
}

// ── 🔴 THE TRANSFER WALK — 보이드 → 본딩 → DT → 코어 ────────────────────
//
// The owner's acceptance sentence walks a defective package back to the core
// wafer its die was picked from. It LOOKS like four legs, and that is exactly
// the trap: four legs is what the common case looks like, not what the structure
// is (`PHYSICS_ONTOLOGY_SETUP §2-bis`, `4dff09f`).
//
// 🔴 EVERY MOVE OF A CHIP IS ONE `transferred` EVENT, AND THE WALK IS JOINED BY
// LOCATION CONTINUITY — NOT BY STAGE NAME:
//
//     event N's `to`  ==  event N+1's `from`,  in time order
//
// So the chain is a LIST OF ANY LENGTH. A wafer that visits DT twice, a
// carrier-to-carrier re-transfer, a rework return — all of them are the same
// walk with more hops in it. Any code here that assumes "DT happens once", or
// that indexes a fixed stage, is a defect at that line: it would render a
// two-DT wafer as a one-DT wafer and the operator would never know a hop was
// dropped.
//
// 🔴 DT IS A SELECTIVE TRANSFER, WHICH IS WHY HOPS CARRY QUANTITIES. Dies are
// picked off a core wafer onto a carrier and only some of what was loaded moves
// on; the rest stays as inventory. An arrow without numbers is not a thinner
// picture, it is the WRONG one — on screen it is indistinguishable from "the
// whole wafer went through". So a hop's quantity is a PAIR, 「12개 중 8개」, and
// it goes through `rateReading` like every other number on this console: there
// is no path to rendering the numerator alone.
//
// 🔴 AND `transferred` IS NOT `processed_with`. Conditions and movement are two
// different claims about the same run, and the screen keeps them apart — the
// fact chips carry conditions, this panel carries movement.

/**
 * A quantity pair — moved of loaded — or null.
 *
 * `remainder` is the container's inflow minus outflow (the owner's 「사용 칩
 * 잔량」) and is null unless both sides are real. A remainder computed against a
 * missing denominator would be a number about nothing.
 */
export function quantityPair(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const moved = numOrNull(raw.moved != null ? raw.moved
    : (raw.consumed != null ? raw.consumed : raw.n));
  const of = numOrNull(raw.of != null ? raw.of : raw.loaded);
  if (moved === null && of === null) return null;
  const declared = numOrNull(raw.remainder);
  return {
    moved,
    of,
    reading: rateReading(moved, of, '모집단 수 미보고'),
    verb: raw.verb == null || String(raw.verb) === '' ? null : String(raw.verb),
    unit: raw.unit == null || String(raw.unit) === '' ? null : String(raw.unit),
    // The server's own remainder when it carried one — it knows the container's
    // whole inflow/outflow ledger and this hop is only one movement out of it.
    remainder: declared !== null ? declared
      : ((moved === null || of === null) ? null : of - moved),
    remainderFrom: declared !== null ? 'server' : 'hop',
  };
}

function endpointOf(node) {
  if (node == null) return null;
  if (typeof node === 'string') return { id: node, text: node, kind: null };
  if (typeof node !== 'object') return null;
  const id = nodeId(node);
  if (id === null) return null;
  return {
    id,
    text: nodeText(node),
    // A label the server chose for this location ("DT lot D slot 5"). Rendered
    // when present, never invented — the walk does not know what a DT is.
    kind: node.kind == null || String(node.kind) === '' ? null : String(node.kind),
  };
}

/**
 * One `transferred` hop, read.
 *
 * 🔴 `basis` IS READ OFF THE FIELD BY THE SAME FUNCTION THE LINEAGE HOPS USE.
 * Two `resolved` hops can rest on different things — a convention-backed one
 * carries the SAME state word a measured one does — so it is not derivable from
 * the state and is not re-derived here. That axis landed already (`4d9b912`);
 * this consumes it.
 */
export function transferHop(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const from = endpointOf(raw.from);
  const to = endpointOf(raw.to);
  return {
    from,
    to,
    // The server's word for what this move was, when it has one. NOT a stage this
    // client assumes: the walk is joined by continuity, and the label is a
    // caption on it.
    label: raw.label == null || String(raw.label) === '' ? null : String(raw.label),
    predicate: raw.predicate == null ? null : String(raw.predicate),
    state: to && to.id ? 'resolved' : 'unresolvable',
    reason: raw.reason == null ? null : String(raw.reason),
    basis: basisLabel(hopBasisField(raw)),
    quantity: quantityPair(raw.quantity),
    at: raw.occurred_at ? instantText(raw.occurred_at) : null,
    eventId: raw.event_id == null || String(raw.event_id) === ''
      ? null : String(raw.event_id),
  };
}

function hopBasisField(hop) {
  const b = hop && hop.basis;
  if (!b || typeof b !== 'object') return null;
  const name = b.name == null ? '' : String(b.name);
  if (name === '') return null;
  return { kind: b.kind == null ? '' : String(b.kind), name };
}

/**
 * The whole transfer walk — ANY number of hops.
 *
 * 🔴 CONTINUITY IS CHECKED AND A BREAK IS SHOWN. The walk's own rule is that
 * hop N's `to` is hop N+1's `from`; when it is not, the two hops are not a
 * chain and rendering them adjacent would assert a connection nobody recorded.
 * `continuous: false` on the second hop is how the screen says so — and the
 * check costs one comparison, where the alternative is a picture that quietly
 * bridges a gap.
 *
 * `terminal` is where the walk STOPPED and why, which is the honest ending for
 * a chain that does not reach the core wafer. Die-level binding is projection
 * work and is not in today's scope; a chain that ends at lot level is a real
 * answer, and it says so rather than looking finished.
 */
export function traceChain(body) {
  const trace = body && body.trace && typeof body.trace === 'object' ? body.trace : null;
  const raw = trace && Array.isArray(trace.hops) ? trace.hops : [];
  const hops = [];
  for (const r of raw) {
    const hop = transferHop(r);
    if (hop) hops.push(hop);
  }
  // Continuity, hop to hop. The FIRST hop has nothing before it, so it is
  // continuous by definition rather than by check.
  for (let i = 0; i < hops.length; i += 1) {
    if (i === 0) { hops[i].continuous = true; continue; }
    const prevTo = hops[i - 1].to;
    const from = hops[i].from;
    hops[i].continuous = !!(prevTo && from && prevTo.id === from.id);
  }
  const breaks = hops.filter((h) => h.continuous === false).length;
  return {
    subject: trace && trace.subject ? nodeText(trace.subject) : null,
    hops,
    breaks,
    // How many DISTINCT containers the walk passed through. Rendered because a
    // wafer that visits DT twice must be visibly different from one that visits
    // once, and the hop count alone does not say that.
    stops: new Set(hops.map((h) => (h.to ? h.to.id : null)).filter(Boolean)).size,
    terminal: trace && trace.terminal_reason != null && String(trace.terminal_reason) !== ''
      ? String(trace.terminal_reason) : null,
    // Null when the response carried no trace at all — which is not the same as
    // a trace that ran and stopped, and must not render as one.
    present: !!trace,
  };
}

// ── the whole console answer, assembled ──────────────────────

/**
 * Everything the console renders, from the catalog body and the siblings body.
 *
 * 🔴 ONE CALL FEEDS BOTH ANALYSIS PANELS. 공통점 and 차이점 are two framings of
 * the same response (`shared` and `contrast` off one `GET`), which is the brief's
 * "둘째 엔드포인트 금지" — two endpoints would let the panels disagree about the
 * same population.
 */
export function consoleModel({ catalog, body, question }) {
  const cat = catalog || { state: 'unknown', kinds: [], defaultKind: '' };
  const kind = pickKind(cat, question && question.finding);
  const standing = kindStanding(cat, kind);
  const denominator = denominatorReading(body, standing.row);
  const split = populationSplit(body);
  // The class vocabulary of THIS kind, from the catalog. Empty when the kind
  // declares none — the axis then simply does not exist for it.
  const classes = standing.row && Array.isArray(standing.row.classes) ? standing.row.classes : [];
  return {
    kind,
    kindLabel: standing.row ? standing.row.label : kind,
    standing,
    catalog: cat,
    classes,
    question: { finding: kind, slices: (question && question.slices) || {} },
    denominator,
    split,
    rows: populationRows(split),
    slices: sliceRows(body, classes),
    trace: traceChain(body),
    notes: noteRows(body),
    shared: sharedRows(body),
    contrast: contrastRows(body),
    facts: factChips(body && body.facts),
    // The contrast panel is drawable only when there IS a clean population to
    // contrast against. When there is not, the panel renders the REASON — the
    // honest degradation, as content.
    contrastable: denominator.standing === 'present' && split.clean !== null,
    generatedAt: body && body.generated_at ? instantText(body.generated_at) : null,
  };
}
