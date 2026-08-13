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

async function run(asked, { pushUrl = true } = {}) {
  const mount = byId('lt-result');
  if (!mount) return;

  if (!asked.lot) return runEmpty(mount);

  const mine = ++session;
  const query = traceQuery(asked);
  if (pushUrl && window.history && window.history.replaceState) {
    // The answer becomes a link. No control needed for that, and it is how a
    // trace gets pasted into a message.
    window.history.replaceState(null, '', `?${query}`);
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
  await coverageReady;
  if (mine !== session) return;

  renderTrace(document, mount, trace, subjectOf(trace, asked),
    nothingVerdict(trace, ledgerState));
}

function boot() {
  initTheme();
  // In flight from the first tick. Whichever path `run` takes below, the answer
  // to "which nothing is this" is already on its way.
  loadCoverage();

  const input = byId('lt-query');
  const params = new URLSearchParams(window.location.search);
  const fromUrl = { lot: (params.get('lot') || '').trim(), slot: (params.get('slot') || '').trim() || null };

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
