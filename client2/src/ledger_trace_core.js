// ============================================================
// ledger_trace_core.js — how one `GET /api/ledger/trace` hop reads on screen.
//
// PURE. No DOM, no network, no imports. It runs under bare node, so
// `tests/ledger_trace_harness.mjs` scores THESE functions rather than a copy of
// them.
//
// 🔴 THIS MODULE DECIDES NOTHING ABOUT THE LEDGER. The server resolved every hop
// (`server/ledger_trace.py`, THE resolver) and shipped `state` / `reason` /
// `predicate` with it. Everything here maps that answer onto words and tones. If
// a rule about which claim wins ever appears in this file, it is a second
// resolver and it is wrong — take it back to the server lane.
//
// WHAT IT MUST MAKE VISIBLE (product brief, slice 1 layer 3):
//   1. a hop resting on a CONVENTION must not look like one resting on a
//      measurement — `hopBasis` is the whole of that distinction, and since
//      server 5bacdfc it READS THE WIRE'S `basis` FIELD instead of deriving it.
//      It is underivable: an undisputed convention-backed hop is `resolved`, the
//      same word a fully measured one gets;
//   2. `unresolvable` is CONTENT, not an error — `hopVerdict` gives it a name
//      ("뿌리", "주장 없음") and never an error tone;
//   3. `candidate` means NOBODY declared a winner and `contested` means one was
//      declared over a live dissent — two different facts, two labels, and the
//      count is in both.
// ============================================================

// ── the question each predicate asks ─────────────────────────
// The server's walk is a list of QUESTIONS (`trace()` docstring: has_wafer ->
// which wafer sits here, derived_from -> where did this lot come from, slot_map
// -> where was this position in the parent). Rendering the predicate name would
// make the operator translate; rendering the question does not.
export const PREDICATE_QUESTION = {
  has_wafer: '이 자리의 웨이퍼는?',
  derived_from: '이 랏의 부모 랏은?',
  slot_map: '부모 랏에서 이 자리는?',
  register: '원장이 이 랏을 아는가?',
};

// Tag -> the name of THAT KIND of gap. `unresolvable` covers five very different
// situations and calling them all "미해결" throws away what the server took the
// trouble to say. Unknown tags fall back, never guess.
export const GAP_LABEL = {
  no_claim: '주장 없음',
  unknown_subject: '원장에 없음',
  unusable_payload: '답 없는 원자',
  no_slot_map: '대응 없음',
};

// Terminal tags. `[root]` and `[dead_end]` are the two the operator acts on
// differently: a root is the end of a chain that WAS recorded, a dead end is a
// lot whose parentage nobody wrote down.
export const TERMINAL_VERDICT = {
  root: { tone: 'end', label: '뿌리 도달' },
  dead_end: { tone: 'gap', label: '혈통 미상' },
  unknown_subject: { tone: 'gap', label: '원장에 없는 랏' },
  broken: { tone: 'gap', label: '부모 미상' },
  cycle: { tone: 'contested', label: '순환' },
  depth_cap: { tone: 'truncated', label: '깊이 한계' },
};

// ── the question the operator asks ───────────────────────────

/**
 * "LOT" | "LOT/02" | "LOT 02" -> {lot, slot}.
 *
 * ONE box, not two, and the split rule is spelled here so it is testable and so
 * the screen can echo back what it understood. A misparse that nobody can see is
 * the reason this returns the pair instead of building a URL directly.
 */
export function parseQuery(text) {
  const raw = String(text == null ? '' : text).trim();
  if (!raw) return { lot: '', slot: null };

  let lot = raw;
  let slot = null;
  const slash = raw.lastIndexOf('/');
  if (slash > 0) {
    lot = raw.slice(0, slash).trim();
    slot = raw.slice(slash + 1).trim();
  } else {
    // index of the whitespace run that starts the LAST token
    const ws = raw.search(/\s+\S+$/);
    if (ws > 0) {
      lot = raw.slice(0, ws).trim();
      slot = raw.slice(ws).trim();
    }
  }
  if (!lot) { lot = raw; slot = null; }        // "/02" is a lot named "/02", not a slot
  if (slot === '') slot = null;
  return { lot, slot };
}

/** {lot, slot} -> the query string of `GET /api/ledger/trace`. */
export function traceQuery({ lot, slot }) {
  const parts = [`lot=${encodeURIComponent(String(lot == null ? '' : lot))}`];
  if (slot !== null && slot !== undefined && String(slot) !== '') {
    parts.push(`slot=${encodeURIComponent(String(slot))}`);
  }
  return parts.join('&');
}

/** {lot, slot} -> the text that reproduces it in the one input box. */
export function queryText({ lot, slot }) {
  const l = String(lot == null ? '' : lot);
  return (slot === null || slot === undefined || String(slot) === '') ? l : `${l}/${slot}`;
}

// ── reading one hop ──────────────────────────────────────────

const TAG_RE = /^\[([a-z_]+)\]/;

/** The machine-readable prefix the server writes first in every `reason`. */
export function reasonTag(reason) {
  const m = TAG_RE.exec(String(reason == null ? '' : reason));
  return m ? m[1] : null;
}

// ── what the WINNER rests on — A FIELD, NOT A READING OF THE SENTENCE ────────
//
// 🔴 `basis` CANNOT BE INFERRED FROM `state`, AND THAT IS WHY THE SERVER SHIPPED
// IT (5bacdfc). A convention-backed hop nothing disputes reads `resolved` — the
// same word a fully measured one gets. There is no state string, and no
// combination of them, that separates an assumption from an utterance.
//
// 🔴 AND IT CANNOT BE READ OUT OF `reason` EITHER. `_with_basis` appends the
// WINNER's label, but a `contested` / `candidate` sentence ALSO names the LOSERS'
// labels inline:
//   `[contested] class=2 observation 답 LOT-A · 하위 계급 반대 1종
//    (LOT-B(convention:slot_preserving)) · 1순위 LOT-A · basis=pair_field`
// The convention there belongs to the claim that LOST, and an anywhere-match
// reads it as "this hop rests on an assumption" — the exact inversion of what the
// screen exists to show. The field says `{kind: 'measured', name: 'pair_field'}`,
// and the field is the winner's.
//
// So: the wire's `basis` is CONSUMED, never derived. `hop.basis === null` is the
// server SAYING there is no declared basis and is taken at its word.

//: The kinds `server/ledger_trace.py::BASIS_KINDS` declares.
//:   convention — a declared ASSUMPTION not present in the source row. Class 3.
//:   measured   — the source uttered it; the translator only reshaped it. Class 2.
const BASIS_CONVENTION = 'convention';
const BASIS_MEASURED = 'measured';

//: 🔴 THE LEGACY READING, AND IT IS ONLY REACHED WHEN THE WIRE HAS NO `basis` KEY
//: AT ALL. `basis` is unversioned and ungated by design, so a client running
//: against a server older than 5bacdfc would otherwise silently stop marking
//: assumptions — the one thing P1 exists to prevent. ANCHORED AT THE END, which
//: is the whole of its correctness: the inline losers' labels are always followed
//: by ` · 1순위 …` and cannot reach `$`. A `null` basis never comes here; only an
//: ABSENT key does.
const BASIS_SUFFIX = /\s·\s(convention:|basis=)([^\s·()]+)$/;

function basisFromReason(reason) {
  const m = BASIS_SUFFIX.exec(String(reason == null ? '' : reason));
  if (!m) return null;
  return { kind: m[1] === 'convention:' ? BASIS_CONVENTION : BASIS_MEASURED, name: m[2] };
}

/**
 * What the WINNING claim of this hop rests on, or null. THE HOP, not its reason.
 *
 * Null has two causes the server deliberately does not tell apart — no winner, or
 * a winner with no declared derivation — and a client treating null as "not
 * convention-backed" is correct in both (`hop_basis` docstring).
 */
export function hopBasis(hop) {
  if (!hop || typeof hop !== 'object') return null;
  if ('basis' in hop) {
    const b = hop.basis;
    if (!b || typeof b !== 'object') return null;
    const name = b.name == null ? '' : String(b.name);
    if (name === '') return null;
    return { kind: b.kind == null ? '' : String(b.kind), name };
  }
  return basisFromReason(hop.reason);
}

/** Does this hop rest on a declared ASSUMPTION? ONE spelling of that question. */
export function isConvention(basis) {
  return !!basis && basis.kind === BASIS_CONVENTION;
}

/**
 * 'convention' -> 가정, 'measured' -> 근거. The WORD is the point (`_basis_label`).
 *
 * 🔴 A kind this screen does not know reads as NEITHER — same rule as
 * `hopVerdict`'s default branch, for the same reason. 근거 is the confident word
 * here, and a wire that grows a third kind must not be able to claim it.
 */
export function basisLabel(basis) {
  if (!basis) return null;
  if (basis.kind === BASIS_CONVENTION) return { text: `가정 · ${basis.name}`, kind: BASIS_CONVENTION };
  if (basis.kind === BASIS_MEASURED) return { text: `근거 · ${basis.name}`, kind: BASIS_MEASURED };
  return { text: `? · ${basis.name}`, kind: 'unknown' };
}

/**
 * One hop -> {state, tag, tone, label}.
 *
 * `tone` drives colour and shape; `label` is what the operator reads. NOTE the
 * default branch: an unrecognised `state` falls to 'gap', never to 'ok'. A wire
 * that grows a fifth state must not be able to paint itself confident.
 *
 * 🔴 THREE WORDS IN THE MIDDLE, NOT TWO, AND THEY ARE NOT DEGREES OF EACH OTHER
 * (server `HOP_STATES`):
 *
 *   resolved   n == 1. Nothing disagreed.
 *   contested  the top class was unanimous and a LOWER class dissents — a winner
 *              was DECLARED over a live contradiction. The ranking is not in
 *              doubt; the contradiction is.
 *   candidate  the top class is split k ways. NOTHING declared a winner; only the
 *              tiebreak separated them. A hop that is BOTH reads `candidate`.
 *
 * So `contested` shares neither word: it is not 확정 (something disagreed, and
 * says so) and it is not 이견 (a winner was declared, and says so). Its label
 * carries both halves and its tone is the disagreement one, because the fact the
 * operator must not miss is the dissent.
 */
export function hopVerdict(hop) {
  const state = hop && hop.state ? String(hop.state) : 'unresolvable';
  const tag = reasonTag(hop && hop.reason);
  const n = Number(hop && hop.n);
  if (state === 'resolved') return { state, tag, tone: 'ok', label: '확정' };
  if (state === 'contested') {
    // `n` counts the distinct answers in contention; `contested` means the top
    // class held exactly one of them, so the rest are the dissent — the same
    // count the server's own sentence prints as `하위 계급 반대 N종`.
    return {
      state, tag, tone: 'contested',
      label: Number.isFinite(n) && n > 1 ? `확정 · 반대 ${n - 1}종` : '확정 · 반대',
    };
  }
  if (state === 'candidate') {
    return {
      state, tag, tone: 'contested',
      label: Number.isFinite(n) && n > 1 ? `이견 ${n}종` : '이견',
    };
  }
  // unresolvable — CONTENT, not a failure. `[root]` is a successful ending.
  if (tag === 'root') return { state: 'unresolvable', tag, tone: 'end', label: '뿌리' };
  return {
    state: 'unresolvable', tag, tone: 'gap',
    label: (tag && GAP_LABEL[tag]) || '미해결',
  };
}

/** `terminal_reason` -> {tone, label, tag}. Same rule: unknown tags degrade. */
export function terminalVerdict(terminalReason) {
  const tag = reasonTag(terminalReason);
  const known = tag ? TERMINAL_VERDICT[tag] : null;
  return { tag, tone: known ? known.tone : 'gap', label: known ? known.label : '중단' };
}

// ── nodes and answers ────────────────────────────────────────

/** The identity a node carries, whatever kind it is. */
export function nodeId(node) {
  if (!node || typeof node !== 'object') return null;
  const keys = node.keys && typeof node.keys === 'object' ? node.keys : {};
  if (keys.lot != null) return String(keys.lot);
  if (keys.wafer != null) return String(keys.wafer);
  for (const v of Object.values(keys)) if (v != null) return String(v);
  return null;
}

/** "CL-…-A8 · 슬롯 2" / "WF.010702" / "—". */
export function nodeText(node) {
  const id = nodeId(node);
  if (id === null) return '—';
  const slot = node && node.slot != null && String(node.slot) !== '' ? String(node.slot) : null;
  return slot === null ? id : `${id} · 슬롯 ${slot}`;
}

/** The question this hop asked, in words. */
export function hopQuestion(hop) {
  const predicate = hop && hop.predicate ? String(hop.predicate) : '';
  return PREDICATE_QUESTION[predicate] || `${predicate || '?'} ?`;
}

/**
 * The ANSWER, as the thing the question asked for — not as the whole node.
 *
 * `slot_map`'s `to` is the parent lot carrying the parent slot; the answer is
 * the SLOT. Rendering the node there would answer "which lot" to a question
 * about position.
 */
export function hopAnswer(hop) {
  const to = hop && hop.to;
  if (!to) return null;
  const predicate = hop && hop.predicate ? String(hop.predicate) : '';
  if (predicate === 'slot_map') {
    const slot = to.slot != null && String(to.slot) !== '' ? String(to.slot) : null;
    return slot === null ? null : `슬롯 ${slot}`;
  }
  const id = nodeId(to);
  return id === null ? null : id;
}

/** The lot the answer lands in, when that is not the answer itself (slot_map). */
export function hopAnswerContext(hop) {
  const to = hop && hop.to;
  if (!to) return null;
  return (hop && hop.predicate === 'slot_map') ? nodeId(to) : null;
}

/**
 * The server's ISO instant, made readable WITHOUT moving the clock.
 *
 * 🔴 NEVER `new Date(iso).toLocaleString()`. `server/ledger_trace.py` renders
 * every instant in a DECLARED zone precisely so the same atom reads the same
 * everywhere; re-rendering it in the viewer's machine zone would put that
 * correctness back on whoever's laptop is open, silently, with the offset
 * removed from the screen so nobody could tell. This only swaps the `T` for a
 * space and drops sub-second noise — the offset stays visible.
 */
export function instantText(iso) {
  if (!iso) return '';
  const s = String(iso);
  const t = s.indexOf('T');
  if (t < 0) return s;
  const date = s.slice(0, t);
  let rest = s.slice(t + 1);
  const dot = rest.indexOf('.');
  if (dot >= 0) {
    const zoneAt = rest.slice(dot).search(/[+\-Z]/);
    rest = rest.slice(0, dot) + (zoneAt >= 0 ? rest.slice(dot + zoneAt) : '');
  }
  return `${date} ${rest}`;
}

// ── the whole answer, counted ────────────────────────────────

/**
 * The one-glance summary: how long the chain is, and how much of it rests on
 * something nobody measured.
 *
 * `convention` is the number that justifies the screen. 127 of the first 878
 * real atoms exist only because of a declared convention; a trace that does not
 * count them hands the operator a conclusion dressed as an observation.
 *
 * 🔴 `contested` GETS ITS OWN BUCKET AND IS NEVER FOLDED INTO 확정. Folding it
 * there would say the chain agrees where it does not; folding it into 이견 would
 * say nobody declared a winner where one was declared. It is a third fact and it
 * is counted as one.
 *
 * 🔴 AND `convention` IS COUNTED OFF THE FIELD, AT THE WINNER. Five of the eleven
 * probe hops carry the substring `convention:`; only three REST on one.
 */
export function summarize(trace) {
  const hops = trace && Array.isArray(trace.hops) ? trace.hops : [];
  const out = {
    total: hops.length, resolved: 0, contested: 0, candidate: 0, unresolvable: 0,
    convention: 0, lots: 0,
  };
  const lots = new Set();
  for (const hop of hops) {
    const v = hopVerdict(hop);
    if (v.state === 'resolved') out.resolved += 1;
    else if (v.state === 'contested') out.contested += 1;
    else if (v.state === 'candidate') out.candidate += 1;
    else out.unresolvable += 1;
    if (isConvention(hopBasis(hop))) out.convention += 1;
    const from = nodeId(hop && hop.from);
    if (from !== null) lots.add(from);
  }
  out.lots = lots.size;
  return out;
}

// ── what can be asked at all, and WHICH nothing this is ──────
//
// 🔴 THE ROUND THIS SECTION EXISTS FOR. The product owner ran the screen against
// a database with no `ledger_events` table and got a blank. Correct, and useless:
// FOUR unrelated situations painted the same nothing, and an operator could not
// tell a deployment problem from a data boundary.
//
//   absent   the table was never migrated onto this box  -> a DEPLOYMENT fact
//   empty    the table is there, the backfill never ran  -> an OPERATIONS fact
//   unknown  the lot is not in the ledger                -> a DATA boundary
//   no line. the lot IS registered, nobody claimed a parent -> a CONTENT fact
//
// 🔴 AND TWO OF THEM ARE INDISTINGUISHABLE FROM THE TRACE ALONE. With zero atoms
// `ledger_trace.py`'s walk finds `cur_lot not in lots_with_atoms` for EVERY lot,
// so an empty ledger answers `[unknown_subject] … 원장에 원자 0` — byte for byte
// the answer a genuinely unknown lot gets on a full ledger. The only thing that
// separates them is `GET /api/ledger/coverage`'s `state`. That is why the state
// is an ARGUMENT here and not something this file tries to infer.
//
// 🔴 AND IT IS INFERRED FROM THE `state` AND THE `[tag]` PREFIX, NEVER FROM THE
// PROSE. The last round measured what prose-reading costs: `reason.includes(
// 'convention:')` INVERTS the assumption/measurement distinction because the
// losers' labels are in the same sentence — which is why that distinction is now
// a FIELD (`basis`) and not a reading at all. The same trap is live here — the
// unknown-subject sentence and the root sentence both talk about atoms being
// absent — so section K scores that a changed sentence under an unchanged tag
// cannot change the verdict.

//: The pinned `state` values of `GET /api/ledger/coverage`.
const COVERAGE_STATES = new Set(['absent', 'empty', 'ready']);

/**
 * The wire's `state`, or 'unknown'.
 *
 * 🔴 An unrecognised state degrades to 'unknown', NEVER to 'ready' — the same
 * rule as `hopVerdict`'s default branch, for the same reason. 'ready' is the one
 * value that makes the screen say "ask me anything"; a wire that grows a fourth
 * state, or a server too old to carry this route at all, must not be able to
 * claim it.
 */
export function coverageState(coverage) {
  const s = coverage && coverage.state ? String(coverage.state) : '';
  return COVERAGE_STATES.has(s) ? s : 'unknown';
}

/**
 * The empty state as words: what this ledger can answer, or why it cannot.
 *
 * 'unknown' falls back to the hint this screen shipped with, which is what a
 * server without the coverage route gets. Degrading to the old screen is the
 * only honest answer there — the alternative is a claim about a box we did not
 * measure.
 */
export function coverageVerdict(coverage) {
  const state = coverageState(coverage);
  if (state === 'absent') {
    return {
      state, tone: 'error',
      title: '원장이 이 DB에 설치되지 않았습니다',
      detail: '마이그레이션 미실행 · 런북 6항',
    };
  }
  if (state === 'empty') {
    return {
      state, tone: 'gap',
      title: '원장이 비어 있습니다 — 백필 미실행',
      detail: '테이블 있음 · 원자 0건',
    };
  }
  if (state === 'ready') {
    return { state, tone: 'ok', title: '무엇을 물을 수 있나', detail: null };
  }
  return {
    state, tone: 'idle',
    title: '랏을 입력하세요',
    detail: '랏만 넣으면 랏 사슬만, 「랏/슬롯」이면 그 자리의 웨이퍼까지.',
  };
}

/**
 * A refusal body, read as `{state, text}`.
 *
 * `detail` is what FastAPI wrapped: `HTTPException(detail=...)` arrives as
 * `{"detail": ...}`. Since the server lane's ruling R-2026-08-13-C the
 * absent-relation 503 carries a STRUCTURED detail —
 *
 *   {reason: "ledger_relation_absent", state: "absent", relation: "…",
 *    message: "원장 테이블 … 없음 — 마이그레이션 미실행 (…)"}
 *
 * 🔴 AND `state` IS THE SAME WORD `GET /coverage` USES, which the route says in
 * its own docstring. So the screen branches on `state` and never on `message`:
 * the message is prose for a human and the server lane may reword it whenever it
 * likes. It goes out as `text` to be printed verbatim — a diagnosis that hides
 * what the server said cannot be checked against the server.
 *
 * An older server sends a bare string; then `state` is 'unknown' and the caller
 * falls back to the coverage it already fetched.
 */
export function refusalReading(detail, status) {
  if (detail && typeof detail === 'object') {
    const message = typeof detail.message === 'string' && detail.message !== ''
      ? detail.message : JSON.stringify(detail);
    return { state: coverageState(detail), text: message };
  }
  if (typeof detail === 'string' && detail !== '') return { state: 'unknown', text: detail };
  return { state: 'unknown', text: `HTTP ${status == null ? '?' : status}` };
}

/**
 * The coverage numbers, each one NULL when the wire did not carry it.
 *
 * 🔴 A missing count renders as nothing, never as 0. "0 lots" is a measurement
 * ("the backfill has not run") and an absent field is not one; printing the
 * second as the first is how a screen states a fact nobody established.
 */
export function coverageFacts(coverage) {
  const lots = Number(coverage && coverage.lots);
  const sources = coverage && Array.isArray(coverage.sources)
    ? coverage.sources.filter((s) => s != null && String(s) !== '').map(String)
    : [];
  const range = coverage && coverage.occurred_at && typeof coverage.occurred_at === 'object'
    ? coverage.occurred_at : {};
  return {
    lots: Number.isFinite(lots) ? lots : null,
    sources,
    from: range.from ? instantText(range.from) : null,
    to: range.to ? instantText(range.to) : null,
  };
}

/**
 * The sample lots, as the links they already are.
 *
 * The answer to this screen's question IS a URL (`?lot=…&slot=…`), so a sample
 * needs no control and no handler — it is the same link a trace gets pasted into
 * a message as. `query` is built by `traceQuery`, the one place the query string
 * is spelled, so a sample cannot drift from what Enter sends.
 */
export function coverageSamples(coverage) {
  const list = coverage && Array.isArray(coverage.sample) ? coverage.sample : [];
  const out = [];
  for (const entry of list) {
    if (!entry || typeof entry !== 'object') continue;
    const lot = entry.lot == null ? '' : String(entry.lot);
    if (!lot) continue;
    const slot = entry.slot == null || String(entry.slot) === '' ? null : String(entry.slot);
    out.push({ lot, slot, text: queryText({ lot, slot }), query: traceQuery({ lot, slot }) });
  }
  return out;
}

/**
 * Did the walk actually MOVE — did any hop name a parent lot?
 *
 * 🔴 KEYED ON THE ANSWER, NOT ON THE STATE WORD, AND THAT IS A REPAIR. `trace()`
 * steps to the parent whenever the resolution produced one — it follows
 * `res.answer`, which is non-null for `contested` and `candidate` hops exactly as
 * it is for `resolved` ones. Keyed on `state === 'resolved'` this said "no
 * lineage claim" about a chain that really walked, whenever the ONE lineage step
 * happened to be disputed; `contested` arriving made a second state wrong the
 * same way. `to` is the walk's own record of having moved, so it cannot go stale
 * the next time the vocabulary widens.
 */
function hasLineageStep(trace) {
  const hops = trace && Array.isArray(trace.hops) ? trace.hops : [];
  return hops.some((h) => h && h.predicate === 'derived_from' && nodeId(h.to) !== null);
}

/**
 * WHICH of the four nothings this is, or null when the answer is a real chain.
 *
 * `ledgerState` is `coverageState(...)` — the DEPLOYMENT facts outrank anything
 * the walk can say, because on an absent or empty ledger the walk's sentence is
 * true and misleading at the same time ("원장에 원자 0" is about the lot when the
 * ledger is full, and about the ledger when it is not).
 *
 * `title: null` on `unknown_lot` is deliberate and not a stub: the gap hop and
 * the terminal block ALREADY say that lot is not in the ledger, and a headline
 * repeating it would be a second sentence about the same fact. The kind is still
 * named so the caller — and the harness — can tell it apart from a real chain.
 *
 * 🔴 AND `samples` IS WHY THAT IS NOT THE WHOLE ANSWER. The sentence was right
 * and the SCREEN was still a dead end: an operator who mistypes a lot reads
 * "원장에 없음", correctly, and has nowhere to go — which is the 「막연하다」
 * report on this very axis, one row further along. `coverage` is the body the
 * page already fetched to tell the four nothings apart, so the way forward costs
 * no request; it is the same list the empty state offers, spelled by the same
 * function, so a lot that is offered here answers when it is clicked.
 *
 * ONLY `unknown_lot` gets it, and that is a rule rather than an omission:
 *   * `ledger_absent` / `ledger_empty` — there is nothing findable to point at,
 *     and a list of lots on a ledger with zero atoms would be a claim that they
 *     exist (the same prohibition `renderCoverage` already holds for counts).
 *   * `no_lineage_claim` — that lot WAS found. Offering alternatives there
 *     answers a question the operator did not ask.
 * An absent `coverage` yields an empty list, never an invented one.
 */
export function nothingVerdict(trace, ledgerState, coverage) {
  const state = ledgerState == null ? 'unknown' : String(ledgerState);
  if (state === 'absent') {
    return {
      kind: 'ledger_absent', tone: 'error',
      title: '원장이 이 DB에 설치되지 않았습니다',
      detail: '마이그레이션 미실행 · 런북 6항',
    };
  }
  if (state === 'empty') {
    return {
      kind: 'ledger_empty', tone: 'gap',
      title: '원장이 비어 있습니다 — 백필 미실행',
      detail: '이 랏이 없는 게 아니라 원장이 비었다 · 원자 0건',
    };
  }

  const tag = reasonTag(trace && trace.terminal_reason);
  if (tag === 'unknown_subject') {
    return {
      kind: 'unknown_lot', tone: 'gap', title: null, detail: null,
      samples: coverageSamples(coverage),
    };
  }
  // `[root]` is a successful ending when the walk got somewhere. On the FIRST
  // hop it means the opposite of a traversal: the ledger registered this lot and
  // nobody ever claimed a parent for it. `[dead_end]` keeps its own label (혈통
  // 미상) — there the register atom is missing too, which is a different fact.
  if (tag === 'root' && !hasLineageStep(trace)) {
    return {
      kind: 'no_lineage_claim', tone: 'gap',
      title: '등재됐으나 혈통 주장 없음',
      detail: 'register 있음 · derived_from 원자 0건',
    };
  }
  return null;
}
