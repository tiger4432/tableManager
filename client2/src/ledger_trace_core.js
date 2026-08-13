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
//      measurement — `hopBasis` is the whole of that distinction;
//   2. `unresolvable` is CONTENT, not an error — `hopVerdict` gives it a name
//      ("뿌리", "주장 없음") and never an error tone;
//   3. `candidate` means something disagreed — the count is in the label.
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

// 🔴 ANCHORED AT THE END, AND THAT IS NOT A DETAIL.
//
// `server/ledger_trace.py::_with_basis` APPENDS the winning claim's basis label
// to the reason, so the winner's label is always the suffix. But a `candidate`
// reason ALSO carries the losers' labels inline —
//   `[candidate] ... 하위 계급 반대 1종 (LOT-B(convention:slot_preserving)) · 1순위 LOT-A`
// — and there the convention belongs to the claim that LOST. A last-match or
// anywhere-match regex reads that as "this hop rests on an assumption", which is
// the exact inversion of what the screen exists to show: the assumption is what
// was overruled. The inline labels are always followed by ` · 1순위 …`, so they
// cannot reach `$`. `ledger_trace_harness.mjs` section C pins both directions.
const BASIS_SUFFIX = /\s·\s(convention:|basis=)([^\s·()]+)$/;

/**
 * What the WINNING claim of this hop rests on, or null.
 *
 * `{kind: 'convention'}` — a declared ASSUMPTION (the server ranks it class 3,
 * inference, by the ontology owner's 2026-08-13 ruling). `{kind: 'basis'}` — a
 * derivation the source actually uttered. The two must never render the same.
 */
export function hopBasis(reason) {
  const m = BASIS_SUFFIX.exec(String(reason == null ? '' : reason));
  if (!m) return null;
  return { kind: m[1] === 'convention:' ? 'convention' : 'basis', name: m[2] };
}

/** 'convention' -> 가정, 'basis' -> 근거. The WORD is the point (server `_basis_label`). */
export function basisLabel(basis) {
  if (!basis) return null;
  return basis.kind === 'convention'
    ? { text: `가정 · ${basis.name}`, kind: 'convention' }
    : { text: `근거 · ${basis.name}`, kind: 'basis' };
}

/**
 * One hop -> {state, tag, tone, label}.
 *
 * `tone` drives colour and shape; `label` is what the operator reads. NOTE the
 * default branch: an unrecognised `state` falls to 'gap', never to 'ok'. A wire
 * that grows a fifth state must not be able to paint itself confident.
 */
export function hopVerdict(hop) {
  const state = hop && hop.state ? String(hop.state) : 'unresolvable';
  const tag = reasonTag(hop && hop.reason);
  if (state === 'resolved') return { state, tag, tone: 'ok', label: '확정' };
  if (state === 'candidate') {
    const n = Number(hop && hop.n);
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
 */
export function summarize(trace) {
  const hops = trace && Array.isArray(trace.hops) ? trace.hops : [];
  const out = {
    total: hops.length, resolved: 0, candidate: 0, unresolvable: 0,
    convention: 0, lots: 0,
  };
  const lots = new Set();
  for (const hop of hops) {
    const v = hopVerdict(hop);
    if (v.state === 'resolved') out.resolved += 1;
    else if (v.state === 'candidate') out.candidate += 1;
    else out.unresolvable += 1;
    const basis = hopBasis(hop && hop.reason);
    if (basis && basis.kind === 'convention') out.convention += 1;
    const from = nodeId(hop && hop.from);
    if (from !== null) lots.add(from);
  }
  out.lots = lots.size;
  return out;
}
