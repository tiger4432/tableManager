// ============================================================
// ledger_trace.js — 원장 혈통 추적 페이지 (ledger.html entry)
//
// The whole screen is ONE QUESTION AND ONE ANSWER:
//   GET /api/ledger/trace?lot=<lot>&slot=<slot>
//     -> {hops: [{from, to, predicate, state, rank, n, reason, occurred_at,
//                 event_id}], terminal_reason, generated_at}
//   (`server/ledger_trace_router.py` / `server/ledger_trace.py` — pinned shape;
//    changing what this consumes is an escalation, not an edit.)
//
// This file is the page entry and does three things: read the question (URL or
// the one input), fetch, hand the answer to the view. The reading of a hop is
// `ledger_trace_core.js`; the DOM is `ledger_trace_view.js`. Neither of those
// touches `window`, which is why both are scored under bare node by
// `tests/ledger_trace_harness.mjs` while this file is only read as text.
//
// 🔴 READ-ONLY SCREEN. It issues one GET and writes nothing, anywhere.
// ============================================================
import './tokens.css';
import { API_BASE } from './config.js';
import { initTheme } from './theme.js';
import { parseQuery, traceQuery, queryText, nodeText } from './ledger_trace_core.js';
import { renderTrace, renderNotice } from './ledger_trace_view.js';

const byId = (id) => document.getElementById(id);

// 🔴 THE SESSION GUARD. Two questions in flight resolve in whatever order the
// server answers, so without this a slow FIRST answer can land on top of a fast
// SECOND one and the screen shows the wrong lot's lineage under the right lot's
// title. Checked after BOTH awaits: the response and the body are two separate
// suspension points, and a check at only the first one passes every test that
// does not stall the body.
let session = 0;

/** The subject line — what the SERVER understood, not what was typed. */
function subjectOf(trace, asked) {
  const first = trace && Array.isArray(trace.hops) && trace.hops.length
    ? trace.hops[0].from : null;
  if (first) return nodeText(first);
  return asked.slot ? `${asked.lot} · 슬롯 ${asked.slot}` : String(asked.lot || '');
}

/**
 * Pull the server's own sentence out of a refusal.
 *
 * FastAPI wraps `HTTPException(detail=...)` as `{"detail": ...}`. The 503s this
 * route raises are operational facts about the box ("원장 테이블 … 없음 — 번역기
 * 미착지", "해결기 config 거절: …") and they are shown VERBATIM. A sentence
 * composed here would be indistinguishable from a real diagnosis while being
 * about nothing.
 */
async function refusalText(res) {
  try {
    const body = await res.json();
    if (body && body.detail !== undefined && body.detail !== null) {
      return typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    }
  } catch (err) { /* not JSON — fall through to the status line */ }
  return `HTTP ${res.status}`;
}

async function run(asked, { pushUrl = true } = {}) {
  const mount = byId('lt-result');
  if (!mount) return;

  if (!asked.lot) {
    renderNotice(document, mount, {
      tone: 'idle',
      title: '랏을 입력하세요',
      detail: '랏만 넣으면 랏 사슬만, 「랏/슬롯」이면 그 자리의 웨이퍼까지 따라갑니다.',
    });
    return;
  }

  const mine = ++session;
  const query = traceQuery(asked);
  if (pushUrl && window.history && window.history.replaceState) {
    // The answer becomes a link. No control needed for that, and it is how a
    // trace gets pasted into a message.
    window.history.replaceState(null, '', `?${query}`);
  }
  renderNotice(document, mount, { tone: 'busy', title: '조회 중…', detail: null });

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
    const detail = await refusalText(res);
    if (mine !== session) return;
    renderNotice(document, mount, {
      tone: 'error',
      title: res.status === 422 ? '질문을 읽지 못했습니다' : `서버 거절 (${res.status})`,
      detail,
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

  renderTrace(document, mount, trace, subjectOf(trace, asked));
}

function boot() {
  initTheme();

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
