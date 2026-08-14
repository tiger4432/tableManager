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
// The THIRD question, and the one that has to be answered before the other two can
// be designed further (product owner, 2026-08-14: "구조가 너무 숨겨져 있어서 UI
// 어떻게 설계해야 할지 모르겠어"). Not an instance graph — the TYPE graph: which
// subject types are joined to which object kinds by which predicate, and how much
// data is on each join. Same page, same tokens, same anchors-only discipline.
import {
  STRUCTURE_VIEW, parseStructureQuery, structureModel,
} from './ontology_structure_core.js';
import { renderStructure } from './ontology_structure_view.js';
// The FOURTH question, and the one the owner calls 놀라움 장치 (화면 ①,
// SCENARIO_CONSOLE_BRIEF §0-ter): "무엇을 볼지 고르기 전에 이상한 게 눈에 들어와야
// 한다." No picker — every declared metric side by side over lots in production
// order, conditional formatting down the item axis, and a Spotfire-style global
// marking that carries into the charts and the three-axis maps. The reading is
// `surprise_core.js` and the DOM is `surprise_view.js`, neither of which touches
// `window`, so both are scored under bare node like the three above.
import {
  SURPRISE_VIEW, parseSurpriseQuery, surpriseQuery, surpriseModel, toggleMark,
} from './surprise_core.js';
import { renderSurprise } from './surprise_view.js';
// The floor under the three-axis maps — the REGISTERED frame declaration and the
// REAL valid-die mask, read through routes that are already deployed. Owner
// constraint 3: no invented circular grid, ever.
import { resolveFloors } from './surprise_axis.js';

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
// 🔴 THE RAW BODY, KEPT BESIDE THE NORMALISED ONE. `kindCatalog` is the shared
// reader and it deliberately does not carry `observation_table` — the console has
// no use for it. The structure view's kind-registry panel does ("kind별
// observed_by · 관측 테이블 · 건수"), and the honest way to get one field the
// shared reader drops is to keep the body, NOT to widen a reader two screens
// depend on for a field only one of them reads.
let kindsBody = null;

function loadKinds() {
  if (kindsPromise) return kindsPromise;
  kindsPromise = fetch(`${API_BASE}/api/ledger/kinds`)
    .then((res) => (res.ok ? res.json() : null))
    .catch(() => null)
    .then((body) => { kindsBody = body; return kindCatalog(body); });
  return kindsPromise;
}

// 🔴 THE STRUCTURE VIEW'S OWN SESSION GUARD — a THIRD counter, for the same
// reason the console has a second one. The three questions are independent and a
// shared counter would make one of them silently cancel another's answer.
let structureSession = 0;

/**
 * The type-level structure of the ledger.
 *
 * 🔴 PROPOSED SHAPE — NOT YET SERVED. The parallel server lane is building the
 * aggregate; the consumed shape is pinned in `ontology_structure_core.js`'s
 * header and changing it is an escalation, not an edit. A 404 renders the whole
 * frame with every panel saying what it does not know, which is what lets this
 * screen ship before the route does.
 */
async function runStructure(question) {
  const mount = byId('lt-structure');
  if (!mount) return;
  const mine = ++structureSession;

  const catalog = await loadKinds();
  if (mine !== structureSession) return;

  const paint = (body, notice) => renderStructure(document, mount,
    structureModel({ body, kinds: catalog, kindsBody, question }), notice);

  // The frame paints from the catalog alone first, so the kind registry is
  // readable while the aggregate is still in flight.
  paint(null, { tone: 'busy', title: '구조 집계 중…', detail: null });

  let res;
  try {
    res = await fetch(`${API_BASE}/api/ledger/structure`);
  } catch (err) {
    if (mine !== structureSession) return;
    paint(null, { tone: 'error', title: '서버에 닿지 못했습니다', detail: String((err && err.message) || err) });
    return;
  }
  if (mine !== structureSession) return;

  if (!res.ok) {
    const refusal = await readRefusal(res);
    if (mine !== structureSession) return;
    paint(null, {
      tone: res.status === 404 ? 'gap' : 'error',
      title: res.status === 404
        ? '구조 집계 API 미배포 — 화면만 준비됨'
        : `서버 거절 (${res.status})`,
      detail: refusal.text,
    });
    return;
  }

  let body;
  try {
    body = await res.json();
  } catch (err) {
    if (mine !== structureSession) return;
    paint(null, { tone: 'error', title: '응답을 읽지 못했습니다', detail: String((err && err.message) || err) });
    return;
  }
  if (mine !== structureSession) return;
  paint(body, null);
}

// 🔴 THE SURPRISE VIEW'S OWN SESSION GUARD — a FOURTH counter, same reason as
// the third: four independent questions, and a shared counter would make one
// silently cancel another's answer.
let surpriseSession = 0;
// The answered body, kept so MARKING can re-render without asking the server
// again. Marking is a selection, not a question — a refetch per checkbox would
// make a comparison of six lots cost six round trips, and the server would answer
// the identical aggregate every time.
let surpriseBody = null;
let surpriseAsked = { cols: [], marked: [] };
// The three-axis maps, per lot, and the valid-die floors they are drawn on.
// Both accumulate and are never cleared: a mask does not change while somebody
// reads a table, and re-marking a lot the reader already looked at must not cost
// a second round trip.
const axisMaps = Object.create(null);
const axisFloors = Object.create(null);
const axisInFlight = new Set();

function paintSurprise(catalog, notice) {
  const mount = byId('lt-surprise');
  if (!mount) return null;
  const model = surpriseModel({ body: surpriseBody, kinds: catalog, question: surpriseAsked });
  renderSurprise(document, mount, model, notice, { maps: axisMaps, floors: axisFloors });
  return model;
}

/**
 * The axis maps for one marked lot.
 *
 * 🔴 PROPOSED SHAPE — NOT YET SERVED (`surprise_map_core.js` header). A refusal
 * is STORED rather than retried, so a missing route shows the real wafer with
 * 「불량 좌표 미배포」 once instead of a panel that spins forever.
 *
 * 🔴 AND THE FLOOR IS RESOLVED FROM ROUTES THAT ARE DEPLOYED. Even with the
 * overlay route absent, an axis payload naming a `reference` gets a real
 * registered frame and a real valid-die mask under it — which is the whole of
 * the owner's third constraint that can be honoured today.
 */
async function loadAxisMap(rowId, catalog) {
  // 🔴 THE CACHE KEY CARRIES THE SLOT. One lot is 25 bonding frames with
  // different grids, so `row` alone would serve slot 3's picture under slot 7's
  // heading the moment the reader changed slots.
  const slot = surpriseAsked.slot || '';
  const key = `${rowId}|${slot}`;
  if (axisInFlight.has(key) || axisMaps[key]) return;
  axisInFlight.add(key);
  const parts = [`row=${encodeURIComponent(rowId)}`];
  if (slot) parts.push(`slot=${encodeURIComponent(slot)}`);
  if (surpriseAsked.finding) parts.push(`kind=${encodeURIComponent(surpriseAsked.finding)}`);
  let body = null;
  try {
    const res = await fetch(`${API_BASE}/api/ledger/lot_map?${parts.join('&')}`);
    body = res.ok ? await res.json() : null;
  } catch (err) {
    body = null;
  }
  // `{axes: []}` is the honest stand-in for "no answer": `lotAxisMaps` renders it
  // as ONE named refusal rather than three copies of the same sentence.
  axisMaps[key] = body && Array.isArray(body.axes) ? body : { axes: [] };
  axisInFlight.delete(key);
  try {
    await resolveFloors(axisMaps[key].axes, axisFloors);
  } catch (err) { /* a floor that will not resolve renders as its own refusal */ }
  paintSurprise(catalog, null);
}

function pumpAxisMaps(model, catalog) {
  if (!model) return;
  const slot = surpriseAsked.slot || '';
  for (const row of model.marked) {
    if (!axisMaps[`${row.row}|${slot}`]) loadAxisMap(row.row, catalog);
  }
}

/**
 * The surprise device.
 *
 * 🔴 PROPOSED SHAPE — NOT YET SERVED. The parallel server lane is building the
 * aggregate; the consumed shape is pinned in `surprise_core.js`'s header and
 * changing it is an escalation, not an edit. A 404 renders the whole frame — the
 * declared item axis from the kind catalog, every panel saying what it does not
 * know — which is what lets this screen ship before the route does.
 */
async function runSurprise(question) {
  const mount = byId('lt-surprise');
  if (!mount) return;
  const mine = ++surpriseSession;
  surpriseAsked = question;

  const catalog = await loadKinds();
  if (mine !== surpriseSession) return;

  const paint = (body, notice) => {
    surpriseBody = body;
    // The marked lots' axis maps are fetched off the MODEL, because the map is
    // keyed on the bonding `row` id and only the answer knows which row a marked
    // lot is. A pasted URL therefore lands with its maps already on their way.
    pumpAxisMaps(paintSurprise(catalog, notice), catalog);
  };

  // The frame paints from the catalog alone first, so the declared item axis is
  // readable while the aggregate is still in flight.
  paint(null, { tone: 'busy', title: '집계 중…', detail: null });

  const query = surpriseQuery(question);
  let res;
  try {
    res = await fetch(`${API_BASE}/api/ledger/lots?${query}`);
  } catch (err) {
    if (mine !== surpriseSession) return;
    paint(null, { tone: 'error', title: '서버에 닿지 못했습니다', detail: String((err && err.message) || err) });
    return;
  }
  if (mine !== surpriseSession) return;

  if (!res.ok) {
    const refusal = await readRefusal(res);
    if (mine !== surpriseSession) return;
    paint(null, {
      tone: res.status === 404 ? 'gap' : 'error',
      title: res.status === 404
        ? '랏 지표 집계 API 미배포 — 화면만 준비됨'
        : `서버 거절 (${res.status})`,
      detail: refusal.text,
    });
    return;
  }

  let body;
  try {
    body = await res.json();
  } catch (err) {
    if (mine !== surpriseSession) return;
    paint(null, { tone: 'error', title: '응답을 읽지 못했습니다', detail: String((err && err.message) || err) });
    return;
  }
  if (mine !== surpriseSession) return;
  paint(body, null);
}

/**
 * Re-render for a MARKING change — no fetch, no navigation.
 *
 * 🔴 THE URL STILL MOVES. `replaceState` keeps the marked set in the address bar
 * so the comparison the owner built pastes into a message, while the answer on
 * screen stays the one already fetched. A marking that navigated would refetch an
 * identical aggregate and lose the scroll position mid-comparison.
 */
function repaintSurprise() {
  const mount = byId('lt-surprise');
  if (!mount) return;
  if (window.history && window.history.replaceState) {
    window.history.replaceState(null, '', `?${surpriseQuery(surpriseAsked)}`);
  }
  loadKinds().then((catalog) => {
    pumpAxisMaps(paintSurprise(catalog, null), catalog);
  });
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

/**
 * Which of the page's questions the URL is asking.
 *
 * 🔴 ONE QUESTION = ONE URL, and that is why this is a branch on a parameter
 * rather than a tab with state. `?view=structure` is a different question about
 * the same ledger, so it is a different address — pasteable, back-buttonable, and
 * costing the page no control beyond the two anchors in the header.
 */
function switchViews(view) {
  const structure = view === STRUCTURE_VIEW;
  const surprise = view === SURPRISE_VIEW;
  const ask = !structure && !surprise;
  const show = (id, on) => {
    const node = byId(id);
    if (node) node.hidden = !on;
  };
  show('lt-structure', structure);
  show('lt-surprise', surprise);
  show('lt-console', ask);
  show('lt-result', ask);
  const rule = document.querySelector('.lt-section-rule');
  if (rule) rule.hidden = !ask;
  const box = document.querySelector('.lt-ask');
  // The lineage box stays visible in every view — it is how the operator leaves
  // this one — but outside the ask view its Enter NAVIGATES rather than renders,
  // because the panel it would render into is not on screen.
  if (box) box.hidden = false;
  const current = structure ? STRUCTURE_VIEW : (surprise ? SURPRISE_VIEW : 'ask');
  for (const a of document.querySelectorAll('[data-view-link]')) {
    a.classList.toggle('lt-view--on', a.getAttribute('data-view-link') === current);
  }
}

/** Enter in the lineage box, from a view that has no lineage panel on screen. */
function bindNavigatingAsk() {
  const box = byId('lt-query');
  if (!box) return;
  box.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    const asked = parseQuery(box.value);
    if (!asked.lot) return;
    // A real navigation — the lineage answer is a different question and
    // therefore a different URL.
    window.location.search = `?${traceQuery(asked)}`;
  });
  box.focus();
}

function boot() {
  initTheme();
  const params = new URLSearchParams(window.location.search);
  const structureAsked = parseStructureQuery(params);
  const view = structureAsked.view;
  const isStructure = view === STRUCTURE_VIEW;
  switchViews(view);

  if (view === SURPRISE_VIEW) {
    // 🔴 ONLY THE KIND CATALOG, NOT COVERAGE AND NOT THE CONSOLE — same rule the
    // structure view follows. A view that quietly issues another view's requests
    // makes every reading of "what does this screen cost" wrong.
    loadKinds();
    runSurprise(parseSurpriseQuery(params));

    // 🔴 ONE DELEGATED LISTENER ON THE MOUNT, BOUND ONCE. The mount survives every
    // re-render (the view clears its children, not the mount), so marking cannot
    // leak a listener per row per repaint — which on a few hundred lots and a few
    // dozen marks is the difference between a screen and a freeze.
    const mount = byId('lt-surprise');
    if (mount) {
      mount.addEventListener('change', (e) => {
        const target = e.target;
        if (!target || typeof target.getAttribute !== 'function') return;
        const lot = target.getAttribute('data-mark-lot');
        if (!lot) return;
        surpriseAsked = toggleMark(surpriseAsked, lot);
        repaintSurprise();
      });
    }
    bindNavigatingAsk();
    return;
  }

  if (isStructure) {
    // 🔴 ONLY THE KIND CATALOG IS FETCHED HERE, NOT COVERAGE AND NOT THE CONSOLE.
    // A view that quietly issues the other view's requests makes every reading of
    // "what does this screen cost" wrong, and the console's answer would be
    // rendered into a hidden mount where nobody could see it was stale.
    loadKinds();
    runStructure(structureAsked);
    bindNavigatingAsk();
    return;
  }

  // In flight from the first tick. Whichever path `run` takes below, the answer
  // to "which nothing is this" is already on its way.
  loadCoverage();
  // Same, for the second question. Started before anything is rendered so the
  // kind picker paints from the catalog rather than from a fallback.
  loadKinds();

  const input = byId('lt-query');
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
