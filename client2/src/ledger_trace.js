// ============================================================
// ledger_trace.js — 원장 혈통 추적 페이지 (ledger.html entry)
//
// The whole screen is ONE QUESTION AND ONE ANSWER:
//   GET /api/ledger/trace?lot=<lot>&slot=<slot>
//     -> {hops: [{from, to, predicate, state, rank, n, reason, occurred_at,
//                 event_id}], terminal_reason, generated_at}
//
// plus ONE THING IT ASKS BEFORE ANY QUESTION IS TYPED — what can be asked at all:
//   GET /api/ledger/coverage
//     -> {state: "absent"|"empty"|"ready", lots, sources, occurred_at, sample}
//
// (`server/ledger_trace_router.py` / `server/ledger_trace.py` — pinned shapes;
//  changing what this consumes is an escalation, not an edit.)
//
// This file is the page entry and does three things: read the question (URL or
// the one input), fetch, hand the answer to the view. The reading of a hop is
// `ledger_trace_core.js`; the DOM is `ledger_trace_view.js`. Neither of those
// touches `window`, which is why both are scored under bare node by
// `tests/ledger_trace_harness.mjs` while this file is only read as text.
//
// 🔴 READ-ONLY SCREEN. Two GETs, and it writes nothing, anywhere.
// ============================================================
import './tokens.css';
import { API_BASE } from './config.js';
import { initTheme } from './theme.js';
import {
  parseQuery, traceQuery, queryText, nodeText, coverageState, nothingVerdict,
  refusalReading,
} from './ledger_trace_core.js';
import { renderTrace, renderNotice, renderCoverage } from './ledger_trace_view.js';
// The SECOND question this page answers — how often a finding kind happens, and
// what separates the wafers it happened to from the ones it did not. Same page,
// same tokens, same "a nothing is content" discipline; the reading is
// `case_control_core.js` and the DOM is `case_control_view.js`, neither of which
// touches `window`, so both are scored under bare node like the two above.
import {
  parseConsoleQuery, consoleQuery, kindCatalog, consoleModel,
} from './case_control_core.js';
import { renderConsole } from './case_control_view.js';

const byId = (id) => document.getElementById(id);

// 🔴 COVERAGE — "what can I ask", fetched ONCE per page load.
//
// It is not decoration on the empty state, it is the only thing that can tell
// FOUR different nothings apart. With zero atoms the walk answers
// `[unknown_subject] … 원장에 원자 0` for every lot — identical to a genuinely
// unknown lot on a full ledger — so an operator staring at a blank screen cannot
// distinguish "the migration never ran here" from "that lot does not exist".
// `GET /api/ledger/coverage` -> `{state, lots, sources, occurred_at, sample}`
// (pinned by the lead PM; changing what this consumes is an escalation).
//
// A server without the route leaves this at 'unknown' and the screen degrades to
// exactly what it was before — never to a claim about a box nobody measured.
let ledgerState = 'unknown';
let coveragePromise = null;

function loadCoverage() {
  if (coveragePromise) return coveragePromise;
  coveragePromise = fetch(`${API_BASE}/api/ledger/coverage`)
    .then((res) => (res.ok ? res.json() : null))
    .catch(() => null)
    .then((body) => {
      ledgerState = coverageState(body);
      return body;
    });
  return coveragePromise;
}

// 🔴 THE KIND CATALOG — "which defect kinds can I ask about", fetched ONCE per
// page load, exactly like coverage above.
//
// It is what makes the console GENERAL instead of a void screen with a
// parameter. The picker is built from this body; the atom count in it is what
// tells the operator which kinds actually have data, so a kind that is declared
// and never observed reads as declared-and-empty rather than as a dead console.
//
// 🔴 PROPOSED SHAPE — NOT YET SERVED. As of this round no route answers it
// (`server/ledger_trace_router.py` carries `/trace` and `/coverage` only) and
// the finding-kind vocabulary is not in `server/ledger/vocabulary.py` either.
// This client consumes:
//   GET /api/ledger/kinds
//     -> {state: "absent"|"empty"|"ready", default: "<kind>",
//         kinds: [{kind, label?, atoms, observed_by: [method], runs}]}
// CHANGING WHAT THIS CONSUMES IS AN ESCALATION, NOT AN EDIT — and so is the
// server lane answering a different shape. A 404 leaves the catalog at 'unknown'
// and the console degrades to the declared default kind, saying so out loud.
let kindsPromise = null;

function loadKinds() {
  if (kindsPromise) return kindsPromise;
  kindsPromise = fetch(`${API_BASE}/api/ledger/kinds`)
    .then((res) => (res.ok ? res.json() : null))
    .catch(() => null)
    .then((body) => kindCatalog(body));
  return kindsPromise;
}

// 🔴 THE SESSION GUARD. Two questions in flight resolve in whatever order the
// server answers, so without this a slow FIRST answer can land on top of a fast
// SECOND one and the screen shows the wrong lot's lineage under the right lot's
// title. Checked after EVERY await, not just the first: the response, the body
// and the coverage body are separate suspension points, and a check at only one
// of them passes every test that does not stall the others.
let session = 0;

/** The subject line — what the SERVER understood, not what was typed. */
function subjectOf(trace, asked) {
  const first = trace && Array.isArray(trace.hops) && trace.hops.length
    ? trace.hops[0].from : null;
  if (first) return nodeText(first);
  return asked.slot ? `${asked.lot} · 슬롯 ${asked.slot}` : String(asked.lot || '');
}

/**
 * Unwrap FastAPI's `{"detail": …}` and hand it to `refusalReading`, which is
 * where the reading lives so the harness can score it. This function is only the
 * await and the unwrap.
 */
async function readRefusal(res) {
  let detail = null;
  try {
    const body = await res.json();
    if (body && body.detail !== undefined && body.detail !== null) detail = body.detail;
  } catch (err) { /* not JSON — fall through to the status line */ }
  return refusalReading(detail, res.status);
}

/**
 * The empty state — the screen BEFORE a question, answering "what can I ask".
 *
 * It takes a session number of its own because the coverage body is an await
 * like any other: a slow one landing after the operator has already pressed
 * Enter would wipe their answer and put the sample list back.
 */
async function runEmpty(mount) {
  const mine = ++session;
  const body = await loadCoverage();
  if (mine !== session) return;
  renderCoverage(document, mount, body);
}

// 🔴 THE CONSOLE'S OWN SESSION GUARD. It is a SEPARATE counter from the lineage
// one on purpose: the two questions are independent, and sharing a counter would
// make asking a lot cancel the console's answer (and the reverse), which is a
// screen silently discarding a question the operator did ask.
let consoleSession = 0;

/**
 * The case-control answer for one finding kind.
 *
 * 🔴 PROPOSED SHAPE — NOT YET SERVED. The parallel server lane is building it.
 * This client consumes ONE call for BOTH analysis panels (the brief's
 * "둘째 엔드포인트 금지" — two endpoints would let 공통점 and 차이점 disagree
 * about the same population):
 *   GET /api/ledger/siblings?finding=<kind>&mode=contrast[&eqp&recipe&lot&from&to]
 *     -> {finding, generated_at,
 *         denominator: {basis: "inspection_run", methods: [...], runs: N},
 *         population:  {found: N, clean: N, unscanned: N},
 *         slices:   [{axis, key, found, denominator}],
 *         shared:   [{factor, in_found, of_found, in_base, of_base}],
 *         contrast: [{factor, found: {n, d}, clean: {n, d}}],
 *         facts:    [<measured|observed|processed_with atom>]}
 * Every field is optional to this client: a missing one renders as 미보고 or
 * 분모 없음, never as 0 and never as a blank. That is what lets the console ship
 * before the route does — and what makes a partially-answered response readable
 * instead of a screen that looks broken.
 */
async function runConsole(question) {
  const mount = byId('lt-console');
  if (!mount) return;
  const mine = ++consoleSession;

  const catalog = await loadKinds();
  if (mine !== consoleSession) return;

  // The frame paints from the catalog alone: the picker is usable while the
  // counts are still in flight, so the operator can change their mind without
  // waiting for an answer they already decided against.
  const kind = consoleModel({ catalog, body: null, question }).kind;
  const asked = { finding: kind, slices: question.slices };
  renderConsole(document, mount, consoleModel({ catalog, body: null, question: asked }),
    { tone: 'busy', title: '집계 중…', detail: null });

  const query = `${consoleQuery(asked)}&mode=contrast`;
  let res;
  try {
    res = await fetch(`${API_BASE}/api/ledger/siblings?${query}`);
  } catch (err) {
    if (mine !== consoleSession) return;
    renderConsole(document, mount, consoleModel({ catalog, body: null, question: asked }),
      { tone: 'error', title: '서버에 닿지 못했습니다', detail: String((err && err.message) || err) });
    return;
  }
  if (mine !== consoleSession) return;

  if (!res.ok) {
    const refusal = await readRefusal(res);
    if (mine !== consoleSession) return;
    // The panels still render, every one of them saying what it does not know.
    // The server's sentence goes out verbatim beneath — same rule as the
    // lineage refusal, and for the same reason.
    renderConsole(document, mount, consoleModel({ catalog, body: null, question: asked }), {
      tone: res.status === 404 ? 'gap' : 'error',
      title: res.status === 404
        ? '집계 API 미배포 — 화면만 준비됨'
        : `서버 거절 (${res.status})`,
      detail: refusal.text,
    });
    return;
  }

  let body;
  try {
    body = await res.json();
  } catch (err) {
    if (mine !== consoleSession) return;
    renderConsole(document, mount, consoleModel({ catalog, body: null, question: asked }),
      { tone: 'error', title: '응답을 읽지 못했습니다', detail: String((err && err.message) || err) });
    return;
  }
  if (mine !== consoleSession) return;

  renderConsole(document, mount, consoleModel({ catalog, body, question: asked }), null);
}

async function run(asked, { pushUrl = true } = {}) {
  const mount = byId('lt-result');
  if (!mount) return;

  if (!asked.lot) return runEmpty(mount);

  const mine = ++session;
  const query = traceQuery(asked);
  if (pushUrl && window.history && window.history.replaceState) {
    // The answer becomes a link. No control needed for that, and it is how a
    // trace gets pasted into a message.
    //
    // 🔴 AND IT CARRIES THE CONSOLE'S QUESTION ALONG. Both questions live in the
    // same URL because they live on the same page; overwriting the query string
    // with the lot alone would drop the finding kind the operator chose, and the
    // very next reload would put them back on the default kind with no way to
    // tell that their choice had been discarded.
    const keep = consoleQuery(consoleAsked);
    window.history.replaceState(null, '', `?${keep ? `${keep}&` : ''}${query}`);
  }
  renderNotice(document, mount, { tone: 'busy', title: '조회 중…', detail: null });

  // Started here and cached, so it costs one request per page load and is
  // settled long before the walk answers. It is awaited below rather than here:
  // the trace is what the operator asked for and must not queue behind it.
  const coverageReady = loadCoverage();

  let res;
  try {
    res = await fetch(`${API_BASE}/api/ledger/trace?${query}`);
  } catch (err) {
    if (mine !== session) return;
    renderNotice(document, mount, {
      tone: 'error', title: '서버에 닿지 못했습니다', detail: String(err && err.message || err),
    });
    return;
  }
  if (mine !== session) return;

  if (!res.ok) {
    const refusal = await readRefusal(res);
    if (mine !== session) return;
    await coverageReady;
    if (mine !== session) return;
    // 🔴 WHICH refusal this is comes from a STRUCTURED field, never from the
    // sentence. First choice is the refusal's own `state`; second is the coverage
    // state this page already fetched, for a server too old to send one. Reading a
    // state out of the prose would be the defect this screen already paid for
    // once, where the assumption/measurement distinction inverted because it was
    // read out of a sentence.
    //
    // 422 is the operator's typo, not the box's state, so it never consults either.
    const nothing = res.status === 422
      ? null
      : nothingVerdict(null, refusal.state === 'unknown' ? ledgerState : refusal.state);
    renderNotice(document, mount, {
      tone: nothing ? nothing.tone : 'error',
      title: nothing
        ? nothing.title
        : (res.status === 422 ? '질문을 읽지 못했습니다' : `서버 거절 (${res.status})`),
      // The server's own words, verbatim, underneath the diagnosis.
      detail: nothing && nothing.detail ? `${nothing.detail}\n${refusal.text}` : refusal.text,
    });
    return;
  }

  let trace;
  try {
    trace = await res.json();
  } catch (err) {
    if (mine !== session) return;
    renderNotice(document, mount, {
      tone: 'error', title: '응답을 읽지 못했습니다', detail: String(err && err.message || err),
    });
    return;
  }
  if (mine !== session) return;
  // 🔴 THE BODY, not just the state it set. `ledgerState` tells the answer WHICH
  // nothing it is; the body is what lets the one dead-end nothing — a lot the
  // ledger does not know — point at lots it does. It is the request the page
  // already made, so the way forward costs nothing extra and cannot go stale
  // against the state derived from the same body.
  const coverage = await coverageReady;
  if (mine !== session) return;

  renderTrace(document, mount, trace, subjectOf(trace, asked),
    nothingVerdict(trace, ledgerState, coverage));
}

// The console's question as the URL stated it, remembered so the lineage answer
// can keep it in the address bar (see `run`). Set once in `boot`, because every
// console navigation is a real link and therefore a fresh page.
let consoleAsked = { finding: '', slices: {} };

function boot() {
  initTheme();
  // In flight from the first tick. Whichever path `run` takes below, the answer
  // to "which nothing is this" is already on its way.
  loadCoverage();
  // Same, for the second question. Started before anything is rendered so the
  // kind picker paints from the catalog rather than from a fallback.
  loadKinds();

  const input = byId('lt-query');
  const params = new URLSearchParams(window.location.search);
  const fromUrl = { lot: (params.get('lot') || '').trim(), slot: (params.get('slot') || '').trim() || null };

  // 🔴 THE CONSOLE RUNS ON EVERY LOAD, WITH OR WITHOUT A LOT. It is this page's
  // entry point (the 현황판 answers "which defect, how often, over what"), and a
  // lot query is a drill-down BESIDE it, not instead of it. `finding` absent is
  // not a special case: `pickKind` resolves it against the catalog, so the
  // landing screen is whatever the vocabulary declares as its default.
  consoleAsked = parseConsoleQuery(params);
  runConsole(consoleAsked);

  if (input) {
    if (fromUrl.lot) input.value = queryText(fromUrl);
    // ONE control, and Enter is its whole contract. `change` is deliberately not
    // bound: it also fires on blur, so clicking away would re-issue a question
    // the operator did not ask again.
    input.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter') return;
      e.preventDefault();
      run(parseQuery(input.value));
    });
    input.focus();
  }

  run(fromUrl.lot ? fromUrl : { lot: '', slot: null }, { pushUrl: false });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot);
} else {
  boot();
}
