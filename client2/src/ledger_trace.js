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
  parseConsoleQuery, consoleQuery, kindCatalog, consoleModel, pickKind,
} from './case_control_core.js';
import { renderConsole } from './case_control_view.js';
// The FIFTH question, and the one the brief calls 화면 ② (§0-quinquies R2): ONE
// lot, and everything known about why it is odd — 혈통 요약 · 차이점 순위표(세
// 관문) · 조사 이력. Not a page and not a modal: `?view=lot&lot=…` is a different
// question about the same ledger, so it is a different address. The reading is
// `lot_reference_core.js` and the DOM is `lot_reference_view.js`, neither of
// which touches `window`, so both are scored under bare node like the four above.
import {
  LOT_VIEW, parseLotQuery, lotQuery, lotFetchQuery, lotModel,
} from './lot_reference_core.js';
import { renderLotReference } from './lot_reference_view.js';
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
  SURPRISE_VIEW, parseSurpriseQuery, surpriseQuery, lotsQuery, surpriseModel, toggleMark,
  newestPage, WAFER_CAP,
} from './surprise_core.js';
import { renderSurprise, updateMarks } from './surprise_view.js';
// The floor under the three-axis maps — the REGISTERED frame declaration and the
// REAL valid-die mask, read through routes that are already deployed. Owner
// constraint 3: no invented circular grid, ever.
import { resolveFloors } from './surprise_axis.js';
// 🔴 ONE FUNCTION DECIDES WHICH FRAMES EXIST, AND BOTH CALLERS READ IT. The strip
// renderer and this loader used to have separate ideas of what to fetch — the
// renderer walked every matched frame while the loader fetched one map per marked
// lot — so the strip showed 25 pending entries that nothing was ever going to
// fill. `mapWants` is the renderer's own computation, exported for the loader.
import { mapWants } from './surprise_map_core.js';
// 🔴 THE ANSWER TO MULTI-MARKING. Marking five lots produced 125 wafer maps and
// 12,283px of scroll with no comparison anywhere — a pile of pictures restates
// the question once per wafer instead of answering it. One wafer deserves a
// picture; several lots deserve a ranked contrast. Same page, same marking
// gesture, no second route: `mode` and `finding` are parameters on the endpoint
// the console already talks to.
import { contrastQuery, contrastModel } from './contrast_core.js';
import { renderContrast } from './contrast_view.js';
// The SEVENTH question: two wafers, and where their journeys stopped being the
// same one. Entered by marking a pair in the trend table — there is deliberately
// no nav link, because a journey with no scope is an address with no answer.
import {
  JOURNEY_VIEW, parseJourneyQuery, journeyFetchQuery, journeyModel,
} from './journey_core.js';
import { renderJourney } from './journey_view.js';

const byId = (id) => document.getElementById(id);

// ════════════════════════════════════════════════════════════
// THE IN-PAGE ROUTER
//
// 🔴 ONE QUESTION = ONE URL. THAT WAS NEVER "ONE QUESTION = ONE PAGE LOAD".
// The principle was implemented as `<a href="?…">` and one `location.search =`,
// which means the browser threw the document away on every click: view switch,
// column add/drop, slot pick, kind pick, slice pick, lot open. The product owner
// used the screen and reported it as unusable — 「막 뭐 누를 때마다 새로고침되는데」
// (2026-08-14). Marking, scroll and the table's horizontal scroll all died on
// every click, and a 103-column table cannot be read that way.
//
// So the address bar still moves — every control is still a real, copyable,
// back-buttonable URL, and a pasted link still renders its view in a cold tab —
// but the ONLY thing that reloads the document is F5:
//
//   anchor click  -> preventDefault + pushState + render()
//   Enter in box  -> pushState + render()
//   marking       -> replaceState + repaint (a selection, not a question)
//   back/forward  -> popstate + render()
//
// A link that LEAVES the console (`/index.html`, another origin, target=_blank,
// download, a modified click) is a real navigation and is left alone — the guard
// is on pathname/origin, not on a list of hrefs, so an anchor added tomorrow in
// any view module is routed without that module knowing this file exists.
// ════════════════════════════════════════════════════════════

//: Which view the address bar is on right now, in the same spelling
//: `parseStructureQuery` yields ('' = the ask view). Read by the ask box, and by
//: the click handler to decide whether a click is a change of question (scroll to
//: top) or a change of detail within the same question (hold the scroll).
let currentView = '';
//: The lot view's question as the URL stated it, so a lot typed in the box while
//: that view is up keeps the finding kind the URL is already carrying.
let currentLotAsked = null;

//: Where the reader was, to be re-applied after the paints of the current
//: navigation. Null means "this navigation is a new question — start at the top".
let pendingScroll = null;

//: 🔴 AND WHERE THEY WERE SIDEWAYS. After the transpose this is the expensive one:
//: lots run left to right, so a reader comparing the newest lots is a hundred
//: columns from the left edge. It is held in a variable rather than re-read off
//: the DOM each time because a view paints TWICE — the busy frame has no columns,
//: so reading the position off it would forget the reader between the frame and
//: the answer, which is exactly what was measured happening.
let tableScrollLeft = 0;

function holdScroll() { pendingScroll = window.pageYOffset || 0; }

//: The position WE last wrote, so the scroll listener below can tell our own
//: restore apart from the reader moving. `scrollTo` reports asynchronously, so a
//: boolean flag flipped around the call would already be false by then.
let scrollWeSet = null;

/**
 * Re-apply the held scroll after a paint.
 *
 * Called after EVERY paint of a navigation, not once: a view paints twice (the
 * frame with 「집계 중…」, then the answer), and the second paint changes the
 * document height, so a single restore lands on a page that is about to grow.
 *
 * 🔴 AND IT MUST STOP WHEN THE READER TAKES OVER. The surprise view keeps
 * painting long after its navigation — every axis map that lands repaints the
 * mount — so a hold that never expired would yank the reader back to where they
 * were a minute ago each time a wafer arrived. `releaseScrollOnUserScroll` below
 * is what ends it.
 */
function settleScroll() {
  if (pendingScroll === null) return;
  if ((window.pageYOffset || 0) !== pendingScroll) {
    scrollWeSet = pendingScroll;
    window.scrollTo(0, pendingScroll);
  }
}

function releaseScrollOnUserScroll() {
  window.addEventListener('scroll', () => {
    const y = window.pageYOffset || 0;
    // Our own restore landing — not the reader.
    if (scrollWeSet !== null && y === scrollWeSet) { scrollWeSet = null; return; }
    pendingScroll = null;
    scrollWeSet = null;
  }, { passive: true });
}

function currentParams() {
  return new URLSearchParams(window.location.search);
}

function viewOf(params) {
  return parseStructureQuery(params).view;
}

/**
 * Go to a URL on this page WITHOUT reloading it.
 *
 * `keepScroll` is the difference between "same question, more detail" (adding a
 * column, picking a slot — the reader is mid-read and must not be thrown to the
 * top) and "a different question" (a view switch — the top is where the new
 * answer starts).
 *
 * A browser that refuses `pushState` (file://, an ancient shell) falls back to a
 * real navigation rather than to a dead control.
 */
function go(url, { keepScroll = false } = {}) {
  const next = String(url || '?');
  if (!window.history || !window.history.pushState) {
    window.location.href = next;
    return;
  }
  try {
    // Stamp where the CURRENT entry was, so Back returns to the same place
    // rather than to the top of a screen the reader had scrolled through.
    window.history.replaceState({ scrollY: window.pageYOffset || 0 }, '', window.location.href);
    window.history.pushState({ scrollY: 0 }, '', next);
  } catch (err) {
    window.location.href = next;
    return;
  }
  if (keepScroll) holdScroll();
  else {
    // A different question starts at the top — of both axes.
    pendingScroll = null;
    tableScrollLeft = 0;
    window.scrollTo(0, 0);
  }
  render(currentParams());
}

/**
 * Every anchor on the page, decided per click.
 *
 * 🔴 DELEGATED ON `document`, BOUND ONCE. The views clear and rebuild their
 * mounts on every repaint, so a listener per anchor would leak one per anchor per
 * repaint — and the structure view's anchors live in a module this lane must not
 * edit. One listener at the document is what routes them all without touching a
 * single view file.
 */
function onDocumentClick(e) {
  if (e.defaultPrevented || e.button !== 0) return;
  if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
  const start = e.target;
  const a = start && typeof start.closest === 'function' ? start.closest('a[href]') : null;
  if (!a) return;
  // SVG anchors carry an SVGAnimatedString `href`; the attribute is read as text
  // for every anchor so this function never depends on which namespace it is in.
  if (a.hasAttribute('download')) return;
  const target = a.getAttribute('target');
  if (target && target !== '_self') return;
  const raw = a.getAttribute('href');
  if (!raw) return;
  if (raw.charAt(0) === '#') return; // a fragment is the browser's own job
  let u;
  try { u = new URL(raw, window.location.href); } catch (err) { return; }
  // 🔴 LEAVING THE CONSOLE STAYS A REAL NAVIGATION. `← 그리드` is a different
  // document and must load like one.
  if (u.origin !== window.location.origin) return;
  if (u.pathname !== window.location.pathname) return;
  e.preventDefault();
  go(`${u.pathname}${u.search}${u.hash}`, { keepScroll: viewOf(new URLSearchParams(u.search)) === currentView });
}

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

  const paint = (body, notice) => {
    renderStructure(document, mount,
      structureModel({ body, kinds: catalog, kindsBody, question }), notice);
    settleScroll();
  };

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

// 🔴 THE JOURNEY VIEW'S OWN SESSION GUARD — a SEVENTH counter, same reason as the
// six others: independent questions, and a shared counter would let one answer
// silently cancel another's.
let journeySession = 0;

/**
 * Two wafers, and where their journeys diverged.
 *
 * 🔴 A 422 HERE IS A SCREEN, NOT AN ERROR STRING, AND IT MUST NOT GO THROUGH
 * `readRefusal`. That helper flattens the detail to `{state, text}`, which throws
 * away `arity_resolved`, `subjects` and `axis` — the exact fields the refusal
 * panel renders by name. Live, one marked wafer answers:
 *
 *   {reason: "scope_is_not_a_pair", arity_required: 2, arity_resolved: 1,
 *    subjects: ["SYN-BW-101-06"], axis: "wafer", message: "여정 대조는 주어 2개 전용…"}
 *
 * so the screen can say 「해결된 주어 1 / 필요 2」 and name the wafer. Flattened,
 * that becomes a generic 「서버 거절 (422)」 and the reader learns nothing about
 * what to do next — which is the whole content of this particular refusal.
 */
async function runJourney(question) {
  const mount = byId('lt-journey');
  if (!mount) return;
  const mine = ++journeySession;

  const paint = (body, refusal, notice) => {
    renderJourney(document, mount, journeyModel({ body, question, refusal }), notice);
    settleScroll();
  };

  // No scope in the address is a real state of this view and it costs no request.
  const query = journeyFetchQuery(question);
  if (!query) {
    paint(null, null, null);
    return;
  }

  paint(null, null, { tone: 'busy', title: '여정 대조 중…', detail: null });

  let res;
  try {
    res = await fetch(`${API_BASE}/api/ledger/journey?${query}`);
  } catch (err) {
    if (mine !== journeySession) return;
    paint(null, null, { tone: 'error', title: '서버에 닿지 못했습니다', detail: String((err && err.message) || err) });
    return;
  }
  if (mine !== journeySession) return;

  if (!res.ok) {
    // The RAW detail, with the status merged in — see the note above.
    let detail = null;
    try {
      const body = await res.json();
      if (body && body.detail && typeof body.detail === 'object') detail = body.detail;
    } catch (err) { /* not JSON — fall through to the generic notice below */ }
    if (mine !== journeySession) return;
    if (detail) {
      paint(null, { ...detail, status: res.status }, null);
      return;
    }
    paint(null, null, {
      tone: res.status === 404 ? 'gap' : 'error',
      title: res.status === 404 ? '여정 대조 API 미배포 — 화면만 준비됨' : `서버 거절 (${res.status})`,
      detail: null,
    });
    return;
  }

  let body;
  try {
    body = await res.json();
  } catch (err) {
    if (mine !== journeySession) return;
    paint(null, null, { tone: 'error', title: '응답을 읽지 못했습니다', detail: String((err && err.message) || err) });
    return;
  }
  if (mine !== journeySession) return;
  paint(body, null, null);
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

// 🔴 THE CONTRAST PANEL'S OWN SESSION GUARD — a SIXTH counter, same reason as the
// five above: it is an independent question and a shared counter would let one
// answer silently cancel another's.
let contrastSession = 0;
let contrastBody = null;
let contrastNotice = null;
//: The scope the panel has already asked about, so a repaint does not re-ask.
//: This is also what makes `paintSurprise -> pumpContrast -> paintSurprise`
//: terminate rather than loop.
let contrastKey = '';
//: What the last paint was given, so an answer arriving out of band can repaint
//: without the caller having to hold the catalog.
let lastCatalog = null;
let lastSurpriseNotice = null;

/**
 * The contrast panel, built as a detached node and handed to the surprise
 * renderer — which stays a pure function of the model it was given.
 */
/**
 * The A-vs-B reading, built from the TABLE DATA ALREADY ON SCREEN.
 *
 * 🔴 NO SECOND FETCH FOR THIS HALF. Both lots' metrics are already in the answer
 * the table was drawn from, so comparing them costs nothing and is instant — the
 * owner clicks two lots and the comparison is there before any walk returns.
 *
 * Null unless EXACTLY two are marked: the pair framing is v1 and a three-lot
 * selection must say so rather than quietly rendering the first two.
 */
function pairOf(model) {
  if (!model || model.marked.length !== 2) return null;
  const [a, b] = model.marked;
  const readingOf = (row, col) => {
    const hit = row.cells.find((c) => c.column.key === col.key);
    return hit ? hit.reading : null;
  };
  return {
    // The axis these two marks are ON — the journey door needs it to know whether
    // a pair of marks is a pair of SUBJECTS. See `renderPair`.
    axis: model.rowAxis.name,
    a: { lot: a.lot, row: a.row, bucket: a.bucketLabel, seq: a.seq, universe: a.universe },
    b: { lot: b.lot, row: b.row, bucket: b.bucketLabel, seq: b.seq, universe: b.universe },
    metrics: model.columns.map((col) => ({
      key: col.key,
      label: col.kindLabel,
      agg: col.aggLabel,
      valueKind: col.valueKind,
      a: readingOf(a, col),
      b: readingOf(b, col),
    })),
  };
}

function contrastNodeFor(model) {
  if (!model) return null;
  if (!contrastQuery(surpriseAsked, model.rowAxis)) return null;
  const node = document.createElement('div');
  renderContrast(document, node,
    contrastModel({ body: contrastBody, question: surpriseAsked, rowAxis: model.rowAxis }),
    contrastNotice, pairOf(model));
  return node;
}

/**
 * Ask for the contrast when the MARKED SET changes.
 *
 * 🔴 THE SCOPE IS THE MARKING. That is the whole gesture — mark, and the answer
 * appears in the same screen. `contrastKey` is what keeps a repaint (a map
 * landing, a column edit) from re-asking a question already answered.
 */
function pumpContrast(model) {
  if (!model) return;
  const query = contrastQuery(surpriseAsked, model.rowAxis);
  if (!query) {
    // Marking cleared — drop the answer rather than leaving a stale contrast
    // under an empty selection.
    contrastKey = '';
    contrastBody = null;
    contrastNotice = null;
    return;
  }
  if (query === contrastKey) return;
  contrastKey = query;
  runContrast(query);
}

async function runContrast(query) {
  const mine = ++contrastSession;
  contrastBody = null;
  contrastNotice = { tone: 'busy', title: '대조 걷는 중…', detail: null };
  repaintFromCache();

  let res;
  try {
    res = await fetch(`${API_BASE}/api/ledger/siblings?${query}`);
  } catch (err) {
    if (mine !== contrastSession) return;
    contrastNotice = { tone: 'error', title: '서버에 닿지 못했습니다', detail: String((err && err.message) || err) };
    repaintFromCache();
    return;
  }
  if (mine !== contrastSession) return;

  if (!res.ok) {
    const refusal = await readRefusal(res);
    if (mine !== contrastSession) return;
    contrastNotice = {
      tone: res.status === 404 ? 'gap' : 'error',
      title: res.status === 404 ? '대조 API 미배포 — 화면만 준비됨' : `서버 거절 (${res.status})`,
      detail: refusal.text,
    };
    repaintFromCache();
    return;
  }

  let body;
  try {
    body = await res.json();
  } catch (err) {
    if (mine !== contrastSession) return;
    contrastNotice = { tone: 'error', title: '응답을 읽지 못했습니다', detail: String((err && err.message) || err) };
    repaintFromCache();
    return;
  }
  if (mine !== contrastSession) return;
  contrastBody = body;
  contrastNotice = null;
  repaintFromCache();
}

function repaintFromCache() {
  return paintSurprise(lastCatalog, lastSurpriseNotice);
}

function paintSurprise(catalog, notice) {
  const mount = byId('lt-surprise');
  if (!mount) return null;
  lastCatalog = catalog;
  lastSurpriseNotice = notice;
  // 🔴 THE TABLE'S HORIZONTAL SCROLL IS STATE TOO, and after the transpose it is
  // the most expensive state on the screen: lots run sideways, so a reader
  // comparing the newest ten lots is a hundred columns from the left edge. A
  // repaint that reset it would undo the reader's position on every marking tick.
  const before = mount.querySelector('.sx-tablewrap');
  // Only LEARN a position from a table that could actually hold one. The busy
  // frame is a table with no columns and reads back 0 — believing it is how the
  // reader's place got thrown away between the frame and the answer.
  if (before && before.scrollWidth > before.clientWidth) tableScrollLeft = before.scrollLeft;
  const model = surpriseModel({ body: surpriseBody, kinds: catalog, question: surpriseAsked });
  const contrastNode = contrastNodeFor(model);
  // 🔴 THE RIGHT RAIL IS A DECIDED LAYOUT, NOT A FLOATING CHOICE. The body carries
  // the flag because the rail is `position: fixed` and the page has to give back
  // the width it occupies — a fixed panel over unshifted content would sit on top
  // of the rightmost (newest) lots, which are exactly the ones being compared.
  document.body.classList.toggle('has-contrast', Boolean(contrastNode));
  renderSurprise(document, mount, model, notice, { maps: axisMaps, floors: axisFloors },
    contrastNode);
  if (tableScrollLeft) {
    const after = mount.querySelector('.sx-tablewrap');
    if (after) after.scrollLeft = tableScrollLeft;
  }
  settleScroll();
  // Asked AFTER the paint, and guarded by `contrastKey`, so this cannot recurse:
  // the repaint it triggers finds the key unchanged and stops.
  pumpContrast(model);
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
async function loadAxisMap(rowId, slot, catalog) {
  // 🔴 THE SLOT IS A PARAMETER, NOT A READ OF `surpriseAsked`. One lot is many
  // bonding frames, and the strip asks for a SPECIFIC one per entry — a loader
  // that took the address bar's slot instead would fetch the same frame N times
  // and leave the other N-1 entries pending forever.
  //
  // 🔴 AND THE CACHE KEY CARRIES IT. `row` alone would serve slot 3's picture
  // under slot 7's heading.
  const key = `${rowId}|${slot || ''}`;
  if (axisInFlight.has(key) || axisMaps[key]) return;
  axisInFlight.add(key);
  const parts = [`row=${encodeURIComponent(rowId)}`];
  if (slot) parts.push(`slot=${encodeURIComponent(slot)}`);
  if (surpriseAsked.kind) parts.push(`kind=${encodeURIComponent(surpriseAsked.kind)}`);
  // The same axis the table was read under — `/lot_map` resolves `row` against it,
  // so omitting it would look the row up on a different axis than it came from.
  if (surpriseAsked.by) parts.push(`by=${encodeURIComponent(surpriseAsked.by)}`);
  let body = null;
  try {
    const res = await fetch(`${API_BASE}/api/ledger/lot_map?${parts.join('&')}`);
    body = res.ok ? await res.json() : null;
  } catch (err) {
    body = null;
  }
  // `{axes: []}` is the honest stand-in for "no answer": `lotAxisMaps` renders it
  // as ONE named refusal rather than three copies of the same sentence.
  axisMaps[key] = body && Array.isArray(body.projections) ? body : { projections: [] };
  axisInFlight.delete(key);
  try {
    await resolveFloors(axisMaps[key].projections, axisFloors);
  } catch (err) { /* a floor that will not resolve renders as its own refusal */ }
  // Repaint, then ask what the strip wants NEXT. `mapWants` hands back a bounded
  // batch, so this is what walks a 25-frame lot to completion instead of firing
  // 25 requests at once.
  pumpAxisMaps(paintSurprise(catalog, null), catalog);
}

/**
 * Fetch whatever the strip is still waiting for.
 *
 * 🔴 IT ASKS THE RENDERER, IT DOES NOT GUESS. Iterating `model.marked` was the
 * defect: one marked lot is many bonding frames, so one map per marked lot left
 * every other entry 「불러오는 중…」 forever. `mapWants` runs the strip's own
 * layout and returns the `{row, slot}` pairs it has no body for — one function
 * decides which frames exist and both callers read it.
 */
function pumpAxisMaps(model, catalog) {
  if (!model) return;
  for (const want of mapWants(model, axisMaps)) {
    loadAxisMap(want.row, want.slot, catalog);
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

  // 🔴 THE REQUEST IS NOT THE ADDRESS BAR. `mark` and `slot` are the client's own
  // (which rows are emphasised, and which slot the maps are of) and sending them
  // to `/lots` would be asking the server a question it does not answer.
  const query = lotsQuery(question);
  let res;
  try {
    res = await fetch(`${API_BASE}/api/ledger/lots${query ? `?${query}` : ''}`);
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

  // 🔴 THE NEWEST-END CAP, APPLIED AFTER THE COUNT IS KNOWN. The route pages from
  // the OLDEST end, so a newest-N needs `offset = total - N` and the total only
  // arrives with a response. The first request is therefore a counting request;
  // it costs one extra round trip on entering the wafer axis and nothing after,
  // because paging from here carries `limit`/`offset` in the URL.
  const page = newestPage(question,
    body && body.row_axis && body.row_axis.name,
    body && body.populations && body.populations.rows_total, WAFER_CAP);
  if (page) {
    const capped = { ...question, limit: page.limit, offset: page.offset };
    let res2;
    try {
      res2 = await fetch(`${API_BASE}/api/ledger/lots?${lotsQuery(capped)}`);
    } catch (err) {
      // The uncapped body is already in hand; showing it beats showing nothing.
      if (mine !== surpriseSession) return;
      paint(body, null);
      return;
    }
    if (mine !== surpriseSession) return;
    if (res2.ok) {
      let body2 = null;
      try { body2 = await res2.json(); } catch (err) { body2 = null; }
      if (mine !== surpriseSession) return;
      if (body2) {
        surpriseAsked = capped;
        // The cap is part of the question, so it belongs in the address bar —
        // `replaceState`, not push: the reader did not navigate, the screen bounded
        // itself and is saying so.
        if (window.history && window.history.replaceState) {
          window.history.replaceState({ scrollY: window.pageYOffset || 0 }, '',
            `?${surpriseQuery(capped)}`);
        }
        paint(body2, null);
        return;
      }
    }
  }
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
  // A tick of a checkbox must leave the reader exactly where they were — both
  // axes. `paintSurprise` restores the table's horizontal scroll; this holds the
  // page's vertical one across the rebuild.
  holdScroll();
  if (window.history && window.history.replaceState) {
    window.history.replaceState({ scrollY: window.pageYOffset || 0 }, '',
      `?${surpriseQuery(surpriseAsked)}`);
  }
  loadKinds().then((catalog) => {
    // 🔴 THE FAST PATH. A mark patches the table in place instead of rebuilding
    // it; a full render here is what made 2,600 columns hang the renderer.
    const mount = byId('lt-surprise');
    const root = mount && mount.querySelector('.sx');
    const model = surpriseModel({ body: surpriseBody, kinds: catalog, question: surpriseAsked });
    const patched = root && updateMarks(document, root, model,
      { maps: axisMaps, floors: axisFloors }, contrastNodeFor(model));
    if (!patched) {
      pumpAxisMaps(paintSurprise(catalog, null), catalog);
      return;
    }
    lastCatalog = catalog;
    settleScroll();
    pumpAxisMaps(model, catalog);
    pumpContrast(model);
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

// 🔴 THE REFERENCE VIEW'S OWN SESSION GUARD — a FIFTH counter, same reason as
// the four above. Five independent questions; a shared counter would let one
// silently cancel another's answer.
let lotSession = 0;

/**
 * Everything known about ONE lot — 화면 ② (brief §0-quinquies R2).
 *
 * 🔴 PROPOSED SHAPE — NOT YET SERVED. R1 (랏 스코프 대조 + 귀속 N/M 커버리지) is
 * being built in a parallel lane; the consumed shape is pinned in
 * `lot_reference_core.js`'s header and changing it is an escalation, not an edit.
 *
 * 🔴 A 404 IS CONTENT HERE, NOT AN ERROR SCREEN. The whole frame paints — four
 * sections, every one of them saying what it does not know — because that is
 * what lets this screen land ahead of the route, and because 「배포 안 됨」 and
 * 「이 랏은 깨끗함」 must never look the same.
 */
async function runLot(question) {
  const mount = byId('lt-lot');
  if (!mount) return;
  const mine = ++lotSession;

  const catalog = await loadKinds();
  if (mine !== lotSession) return;

  // The kind is resolved against the SERVER's catalog, never against a literal
  // here — `finding=<kind>` is the generalisation and `void` is a default that
  // lives in the catalog, not in this client.
  const kind = pickKind(catalog, question.finding);
  const paint = (body, notice) => {
    renderLotReference(document, mount, lotModel({ body, question, kind }), notice);
    settleScroll();
  };

  // No lot in the address is a real state of this view and it costs no request.
  if (!question.lot) {
    paint(null, null);
    return;
  }

  paint(null, { tone: 'busy', title: '랏 대조 집계 중…', detail: null });

  const asked = Object.assign({}, question, { finding: kind });
  let res;
  try {
    res = await fetch(`${API_BASE}/api/ledger/lot?${lotFetchQuery(asked)}`);
  } catch (err) {
    if (mine !== lotSession) return;
    paint(null, { tone: 'error', title: '서버에 닿지 못했습니다', detail: String((err && err.message) || err) });
    return;
  }
  if (mine !== lotSession) return;

  if (!res.ok) {
    const refusal = await readRefusal(res);
    if (mine !== lotSession) return;
    paint(null, {
      tone: res.status === 404 ? 'gap' : 'error',
      title: res.status === 404
        ? '랏 스코프 대조 API 미배포 — 화면만 준비됨'
        : `서버 거절 (${res.status})`,
      detail: refusal.text,
    });
    return;
  }

  let body;
  try {
    body = await res.json();
  } catch (err) {
    if (mine !== lotSession) return;
    paint(null, { tone: 'error', title: '응답을 읽지 못했습니다', detail: String((err && err.message) || err) });
    return;
  }
  if (mine !== lotSession) return;
  paint(body, null);
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
  settleScroll();
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
  const paint = (body, notice) => {
    renderConsole(document, mount, consoleModel({ catalog, body, question: asked }), notice);
    settleScroll();
  };
  paint(null, { tone: 'busy', title: '집계 중…', detail: null });

  const query = `${consoleQuery(asked)}&mode=contrast`;
  let res;
  try {
    res = await fetch(`${API_BASE}/api/ledger/siblings?${query}`);
  } catch (err) {
    if (mine !== consoleSession) return;
    paint(null, { tone: 'error', title: '서버에 닿지 못했습니다', detail: String((err && err.message) || err) });
    return;
  }
  if (mine !== consoleSession) return;

  if (!res.ok) {
    const refusal = await readRefusal(res);
    if (mine !== consoleSession) return;
    // The panels still render, every one of them saying what it does not know.
    // The server's sentence goes out verbatim beneath — same rule as the
    // lineage refusal, and for the same reason.
    paint(null, {
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
    paint(null, { tone: 'error', title: '응답을 읽지 못했습니다', detail: String((err && err.message) || err) });
    return;
  }
  if (mine !== consoleSession) return;

  paint(body, null);
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
    window.history.replaceState({ scrollY: window.pageYOffset || 0 }, '',
      `?${keep ? `${keep}&` : ''}${query}`);
  }
  const notice = (n) => { renderNotice(document, mount, n); settleScroll(); };
  notice({ tone: 'busy', title: '조회 중…', detail: null });

  // Started here and cached, so it costs one request per page load and is
  // settled long before the walk answers. It is awaited below rather than here:
  // the trace is what the operator asked for and must not queue behind it.
  const coverageReady = loadCoverage();

  let res;
  try {
    res = await fetch(`${API_BASE}/api/ledger/trace?${query}`);
  } catch (err) {
    if (mine !== session) return;
    notice({ tone: 'error', title: '서버에 닿지 못했습니다', detail: String(err && err.message || err) });
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
    notice({
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
    notice({ tone: 'error', title: '응답을 읽지 못했습니다', detail: String(err && err.message || err) });
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
// can keep it in the address bar (see `run`). Re-read on every in-page navigation
// (`render`), because a console navigation is no longer a fresh page.
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
  const lot = view === LOT_VIEW;
  const journey = view === JOURNEY_VIEW;
  const ask = !structure && !surprise && !lot && !journey;
  const show = (id, on) => {
    const node = byId(id);
    if (node) node.hidden = !on;
  };
  show('lt-structure', structure);
  show('lt-surprise', surprise);
  show('lt-lot', lot);
  show('lt-journey', journey);
  show('lt-console', ask);
  show('lt-result', ask);
  const rule = document.querySelector('.lt-section-rule');
  if (rule) rule.hidden = !ask;
  const box = document.querySelector('.lt-ask');
  // The lineage box stays visible in every view — it is how the operator leaves
  // this one — but outside the ask view its Enter NAVIGATES rather than renders,
  // because the panel it would render into is not on screen.
  if (box) box.hidden = false;
  const current = structure ? STRUCTURE_VIEW
    : (surprise ? SURPRISE_VIEW
      : (lot ? LOT_VIEW : (journey ? JOURNEY_VIEW : 'ask')));
  for (const a of document.querySelectorAll('[data-view-link]')) {
    a.classList.toggle('lt-view--on', a.getAttribute('data-view-link') === current);
  }
}

/**
 * Answer whatever the address bar is currently asking — WITHOUT reloading.
 *
 * This is the whole of what a page load used to do, minus the page load. It is
 * called on first boot, on every routed anchor click, on Enter in the lineage
 * box, and on back/forward. Every branch keeps the rule the four views were
 * written under: a view fetches ONLY its own question, so "what does this screen
 * cost" stays readable.
 */
function render(params) {
  const view = viewOf(params);
  currentView = view;
  switchViews(view);

  if (view === SURPRISE_VIEW) {
    loadKinds();
    runSurprise(parseSurpriseQuery(params));
    return;
  }

  if (view === LOT_VIEW) {
    loadKinds();
    currentLotAsked = parseLotQuery(params);
    runLot(currentLotAsked);
    return;
  }

  if (view === STRUCTURE_VIEW) {
    loadKinds();
    runStructure(parseStructureQuery(params));
    return;
  }

  // 🔴 NO `loadKinds()` HERE. This view asks the catalog nothing, and a view that
  // quietly issues another view's requests makes every reading of "what does this
  // screen cost" wrong — the same rule the other three follow.
  if (view === JOURNEY_VIEW) {
    runJourney(parseJourneyQuery(params));
    return;
  }

  // ── the ask view ──
  // In flight from the first tick. Whichever path `run` takes below, the answer
  // to "which nothing is this" is already on its way.
  loadCoverage();
  // Same, for the second question. Started before anything is rendered so the
  // kind picker paints from the catalog rather than from a fallback.
  loadKinds();

  const fromUrl = {
    lot: (params.get('lot') || '').trim(),
    slot: (params.get('slot') || '').trim() || null,
  };

  // 🔴 THE CONSOLE RUNS ON EVERY LOAD, WITH OR WITHOUT A LOT. It is this page's
  // entry point (the 현황판 answers "which defect, how often, over what"), and a
  // lot query is a drill-down BESIDE it, not instead of it. `finding` absent is
  // not a special case: `pickKind` resolves it against the catalog, so the
  // landing screen is whatever the vocabulary declares as its default.
  consoleAsked = parseConsoleQuery(params);
  runConsole(consoleAsked);

  const input = byId('lt-query');
  // Only overwritten when the URL names a lot — otherwise a half-typed lot would
  // be wiped by a click on a slice chip beside the box.
  if (input && fromUrl.lot) input.value = queryText(fromUrl);

  run(fromUrl.lot ? fromUrl : { lot: '', slot: null }, { pushUrl: false });
}

/**
 * Enter in the lineage box.
 *
 * BOUND ONCE, and it reads the CURRENT view rather than being re-bound per view —
 * re-binding on every in-page navigation would stack one listener per navigation
 * and fire the question N times on the Nth Enter.
 *
 * Where a typed lot lands is the current view's business: the two type-level
 * views have no lot of their own, so a lot means "show me its lineage"; the
 * reference view IS about a lot, so a lot typed there means "the same question
 * about a different lot"; and in the ask view the lineage panel is already on
 * screen, so it renders in place and the answer's URL is written by `run`.
 */
function bindAskBox() {
  const box = byId('lt-query');
  if (!box) return;
  box.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    const asked = parseQuery(box.value);
    if (!asked.lot) return;
    if (currentView === LOT_VIEW) {
      go(`?${lotQuery({
        lot: asked.lot,
        slot: asked.slot,
        finding: currentLotAsked ? currentLotAsked.finding : '',
      })}`);
      return;
    }
    if (currentView === STRUCTURE_VIEW || currentView === SURPRISE_VIEW
      || currentView === JOURNEY_VIEW) {
      go(`?${traceQuery(asked)}`);
      return;
    }
    run(asked);
  });
  box.focus();
}

/**
 * 🔴 ONE DELEGATED LISTENER ON THE MOUNT, BOUND ONCE — and now bound in `boot`
 * rather than in the surprise branch, because the surprise view is entered and
 * left many times per page load instead of once. The mount survives every
 * re-render (the view clears its children, not the mount), so marking cannot leak
 * a listener per row per repaint — which on a few hundred lots and a few dozen
 * marks is the difference between a screen and a freeze.
 */
function bindMarking() {
  const mount = byId('lt-surprise');
  if (!mount) return;
  mount.addEventListener('change', (e) => {
    const target = e.target;
    if (!target || typeof target.getAttribute !== 'function') return;
    const lot = target.getAttribute('data-mark-lot');
    if (!lot) return;
    surpriseAsked = toggleMark(surpriseAsked, lot);
    repaintSurprise();
  });
}

function boot() {
  initTheme();
  // The browser's own scroll restore races our fetches — it fires before the
  // answer exists, so it lands on a short page and is then wrong. `popstate`
  // carries the position instead, applied after each paint.
  if (window.history && 'scrollRestoration' in window.history) {
    try { window.history.scrollRestoration = 'manual'; } catch (err) { /* not settable */ }
  }
  document.addEventListener('click', onDocumentClick);
  window.addEventListener('popstate', (e) => {
    pendingScroll = e && e.state && typeof e.state.scrollY === 'number' ? e.state.scrollY : 0;
    render(currentParams());
  });
  releaseScrollOnUserScroll();
  bindAskBox();
  bindMarking();
  render(currentParams());
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot);
} else {
  boot();
}
