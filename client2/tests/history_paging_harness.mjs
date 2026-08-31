// Harness — THE SIDEBAR TIMELINE READS A PAGE, AND SAYS SO WHEN IT IS ONE.
// Run: node client2/tests/history_paging_harness.mjs   (no node_modules — vm sandbox)
//
// WHAT WAS ACTUALLY WRONG. `GET /tables/{t}/rows/{id}/history` and its `/cells/{col}/history`
// sibling both ended in `.order_by(...).all()` with no LIMIT, so one click loaded a row's ENTIRE
// audit history: measured on a deep fixture at 300,019 rows / 119 MB / 18.9 s, against 200 rows
// / 73 KB / 10.6 ms paged. The server now answers with an envelope
// (`{logs, truncated, next_cursor, limit, returned}`) and the client had to be taught to read it.
//
// THE TWO FAILURES THIS FILE EXISTS FOR, AND NEITHER IS VISIBLE FROM AN EXIT CODE:
//
//   1. `state.cellRowHistoryData` STOPS BEING AN ARRAY. `loadHistory` used to do
//      `state.cellRowHistoryData = await res.json()`. Handed an envelope, that assignment puts
//      an OBJECT where `renderTimelineIncremental` and `appendHistoryLocally` call `.some()` and
//      `.unshift()` — so every live WebSocket update on the sidebar throws, on a screen that
//      otherwise looks fine. Section F pins the array contract by RUNNING those two functions
//      against the state a real load leaves behind, not by checking a type.
//
//   2. A CAPPED LIST PASSES FOR A COMPLETE ONE. This is the silent-wrong-answer class, not a
//      cosmetic one: an operator reading 200 entries and concluding that is the row's whole
//      history has been given a wrong answer, quickly. So `truncated` must reach the screen as
//      a thing the reader can SEE (section B), and `truncated: true` arriving without a usable
//      cursor must not paint a control with nowhere to go (A4).
//
//   3. PAGE 2 OF THE PREVIOUS ROW LANDING ON THIS ROW'S PAGE 1. The rows would all be real,
//      correctly formatted, and about a different row entirely. Section D drives exactly that
//      interleaving — a 더 보기 issued on row A, resolved after the operator has clicked row B.
//
//   4. THE GLOBAL TAB'S OWN COPY OF (1), WHICH REPORTS ITSELF AS A NETWORK ERROR.
//      `/audit_logs/recent` learned the same envelope on 2026-08-11 (`{groups, truncated,
//      next_cursor, …}`), so `state.globalHistoryData = await res.json()` stores an object where
//      `renderGlobalTimeline` calls `.forEach`. The TypeError is raised inside `loadHistory`'s
//      own try/catch, so the panel says "Failed to load global history log" — a working server
//      misreported as a dead one. Section H runs the real renderer against a real envelope.
//
// WHY IT EXECUTES RATHER THAN READS. Every claim above is about what happens ACROSS an await,
// and "the state is reset before the fetch" and "after it" are the same source shape. So the
// real `loadHistory`, `loadMoreHistory`, `readHistoryPage`, `renderTimeline`,
// `createHistoryMoreDom`, `renderTimelineIncremental` and `appendHistoryLocally` are sliced out
// of `timeline.js` and driven against a scripted `fetch` and a minimal document. Nothing here
// re-implements them; re-implementing would score this file against itself.
//
// 🔴 THE `state` IS THE REAL SINGLETON, imported from `client2/src/state.js`, not a model of it.
//    The contract under test is literally "the cursor lives BESIDE `cellRowHistoryData`, not on
//    it", so a harness carrying its own copy of that object would keep passing while the two
//    drifted. A renamed field breaks this file loudly, which is the point.
//
// MUTATION DISCIPLINE. Every `find` string must occur EXACTLY ONCE in `timeline.js`; `applyOnce`
// fails on 0 or >1 matches rather than proceeding. The corpus is UNCONDITIONAL (no `--mutate`
// flag — the build gate runs harnesses bare, and anything behind a flag is a thing it does not
// run) and its verdicts are counted as assertions, so a corpus that stops being applied sinks
// `ran` and blocks.
import { readFileSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = (f) => join(HERE, '..', 'src', f);
const TL0 = readFileSync(SRC('timeline.js'), 'utf8').replace(/\r\n/g, '\n');

function die(msg) {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  console.log('ASSERTIONS 0 1');
  process.exit(2);
}

// `state.js` reads `window.location.search` at module scope, so the global has to exist before
// the import. Set here rather than faked away, so the import is the real module.
globalThis.window = { location: { search: '' } };
const STATE_MOD = await import(pathToFileURL(SRC('state.js')).href);
const state = STATE_MOD.state;
if (!state || typeof state !== 'object') die('client2/src/state.js no longer exports `state`.');

// ── Extraction ──────────────────────────────────────────────────────────────────
function sliceBalanced(src, startIdx, open, close) {
  const i = src.indexOf(open, startIdx);
  if (i < 0) return null;
  let depth = 0;
  for (let j = i; j < src.length; j++) {
    const ch = src[j];
    if (ch === open) depth++;
    else if (ch === close) { depth--; if (depth === 0) return src.slice(startIdx, j + 1); }
  }
  return null;
}
// Anchored at a real declaration, never at a bare name — a bare name matches its own mentions
// in comments, which is how a sibling harness in this directory spent a round scoring the wrong
// function.
function fn(src, name) {
  const m = new RegExp(`(?:export\\s+)?(?:async\\s+)?function\\s+${name}\\s*\\(`).exec(src);
  if (!m) die(`function ${name} not found in timeline.js — renamed or reshaped.`);
  const body = sliceBalanced(src, m.index, '{', '}');
  if (!body) die(`unbalanced braces for ${name} in timeline.js`);
  return body.replace(/^export\s+/, '');
}

const WANTED = [
  'loadHistory', 'historyUrl', 'beginHistorySession', 'readHistoryPage',
  // `createHistoryEmptyDom` is sliced from source rather than stubbed because the claim under
  // test IS what it paints: two different facts that used to share one sentence. A stub would
  // score section I against the harness's own idea of the empty slot.
  'renderTimeline', 'createHistoryEmptyDom', 'renderHistoryMore', 'historyMoreLabel', 'createHistoryMoreDom',
  'markMoreFailed', 'markMoreLost', 'loadMoreHistory',
  'renderTimelineIncremental', 'createTimelineItemDom', 'appendHistoryLocally', 'formatVal',
  // The global tab, sliced for section H. `renderGlobalTimeline` is the function that dies when
  // the envelope is assigned where the array belongs, and `createGlobalTimelineItemDom` is what
  // actually paints an entry — stubbing the second would leave "the panel renders" asserted
  // against a stand-in rather than against the code that renders it.
  // `auditKind` and `auditVal` are what the 2c row calls while painting. Sliced in rather than
  // stubbed for the same reason as the two above: a stub would let the row render against the
  // harness's idea of a kind pill. Without them the slice throws and section H paints nothing --
  // which is exactly how this harness reported the change.
  'renderGlobalTimeline', 'createGlobalTimelineItemDom', 'auditKind', 'auditVal',
  // The 2c filter strip's helpers. `renderGlobalTimeline` calls all four while painting, so
  // leaving them out makes the slice throw and section H paint nothing.
  'auditFilterState', 'groupKindLabel', 'fillAuditFilterOptions', 'auditFilterPasses',
  // The 2c row now asks which table the transaction touched. Same story as every name
  // above it: the row calls it while painting, so leaving it out makes the slice throw
  // and section H paint nothing -- which is how this harness reported THAT change too.
  'auditTargetTable',
];

function applyOnce(src, find, replace, label) {
  const n = src.split(find).length - 1;
  if (n !== 1) die(`mutation anchor for "${label}" occurs ${n} times (need exactly 1). `
                 + `The corpus is measuring nothing until this is re-anchored.`);
  const out = src.replace(find, replace);
  if (out === src) die(`mutation "${label}" produced no change.`);
  if (out.includes(find)) die(`mutation "${label}" left the original text behind.`);
  return out;
}

// ── Scoring ─────────────────────────────────────────────────────────────────────
let pass = 0, fail = 0;
const failures = [];
function check(name, actual, expected) {
  const a = JSON.stringify(actual), e = JSON.stringify(expected);
  if (a === e) { pass++; return true; }
  fail++; failures.push(name);
  console.error(`  FAIL ${name}\n       expected ${e}\n       actual   ${a}`);
  return false;
}
function checkFn(name, actual, pred, describe) {
  if (pred(actual)) { pass++; return true; }
  fail++; failures.push(name);
  console.error(`  FAIL ${name}\n       expected ${describe}\n       actual   ${JSON.stringify(actual)}`);
  return false;
}

// ── A minimal document ──────────────────────────────────────────────────────────
// Only what the sliced code touches. `innerHTML =` drops children exactly as the real one does,
// which is what makes "a fresh load rebuilds the list" observable here at all.
function makeEl(tag) {
  const cls = new Set();
  const el = {
    tagName: String(tag).toUpperCase(),
    children: [],
    parentElement: null,
    dataset: {},
    style: {},
    disabled: false,
    type: '',
    _text: '',
    _html: '',
    _listeners: {},
    classList: {
      add: (...c) => c.forEach(x => cls.add(x)),
      remove: (...c) => c.forEach(x => cls.delete(x)),
      contains: (c) => cls.has(c),
    },
    get className() { return [...cls].join(' '); },
    set className(v) { cls.clear(); String(v).split(/\s+/).filter(Boolean).forEach(x => cls.add(x)); },
    get textContent() { return el._text; },
    set textContent(v) { el._text = String(v); el.children.forEach(c => (c.parentElement = null)); el.children = []; },
    get innerHTML() { return el._html; },
    set innerHTML(v) { el._html = String(v); el.children.forEach(c => (c.parentElement = null)); el.children = []; },
    get firstChild() { return el.children[0] || null; },
    addEventListener: (ev, f) => { (el._listeners[ev] = el._listeners[ev] || []).push(f); },
    appendChild: (c) => { c.parentElement = el; el.children.push(c); return c; },
    insertBefore: (c, ref) => {
      const i = ref ? el.children.indexOf(ref) : -1;
      if (ref && i < 0) throw new Error('insertBefore: reference node is not a child');
      c.parentElement = el;
      if (i < 0) el.children.push(c); else el.children.splice(i, 0, c);
      return c;
    },
    remove: () => {
      const p = el.parentElement;
      if (p) { const i = p.children.indexOf(el); if (i >= 0) p.children.splice(i, 1); }
      el.parentElement = null;
    },
    // This document does NOT parse `innerHTML` — it stores the string. Code that builds its
    // markup as a template and then reaches back into it to wire handlers
    // (`createGlobalTimelineItemDom` does exactly that) would get `null` and throw, which would
    // make the global panel untestable here for a reason that has nothing to do with the panel.
    // So a CLASS selector naming something present in this element's own markup yields a
    // detached stub node, memoised so two lookups of one selector are one node. It is a wiring
    // surface and nothing more: no assertion in this file reads a child that was never parsed.
    querySelector: (sel) => descend(el).find(n => matches(n, sel)) || markupStub(el, sel),
    querySelectorAll: (sel) => descend(el).filter(n => matches(n, sel)),
    click: () => (el._listeners.click || []).forEach(f => f({ target: el, stopPropagation() {}, closest: () => null })),
  };
  return el;
}
function descend(root) {
  const out = [];
  const walk = (n) => n.children.forEach(c => { out.push(c); walk(c); });
  walk(root);
  return out;
}
function matches(node, sel) {
  if (sel.startsWith('.')) return node.classList.contains(sel.slice(1));
  return false;
}
// See `querySelector` above. Only class selectors, only against this element's OWN markup, and
// only when nothing real matched — a lookup that would have found a parsed node never reaches it.
function markupStub(el, sel) {
  if (!sel.startsWith('.') || !el._html.includes(sel.slice(1))) return null;
  el._stubs = el._stubs || {};
  if (!el._stubs[sel]) {
    const stub = makeEl('div');
    stub.className = sel.slice(1);
    el._stubs[sel] = stub;
  }
  return el._stubs[sel];
}

// ── The driver ──────────────────────────────────────────────────────────────────
const API_BASE = 'http://x';

// The text every sandbox in this run is built from. Section G swaps it for a mutant so that the
// SAME sections re-run against the defect — a corpus that only mutated one entry point would
// score the mutation, not the assertions.
let UNDER_TEST = TL0;

// One scripted request queue. Every entry is consumed in order and the URL it was asked for is
// recorded, so "which endpoint, with which cursor" is scored rather than assumed.
function buildSandbox(src = UNDER_TEST) {
  const timeline = makeEl('ul');
  // The Row History tab button. Real, not a spy function, because the empty cell tab's way out
  // is `elements.tabRowBtn.click()` — it reuses the tab's own listener instead of copying the
  // switch — and only a node with a click dispatcher can score that.
  const tabRowBtn = makeEl('button');
  const requests = [];
  const responses = [];   // {status, body, hang} | {throws: true}
  const pending = [];     // resolvers for hung requests

  const fetchFake = (url) => {
    requests.push(url);
    const spec = responses.shift();
    if (!spec) return Promise.reject(new Error(`unscripted fetch: ${url}`));
    if (spec.throws) return Promise.reject(new Error('network down'));
    const res = {
      ok: spec.status >= 200 && spec.status < 300,
      status: spec.status,
      // `res.json()` is a SECOND await, and the session can move across it just as it can move
      // across the fetch. `onJson` is how a case puts an event in that window.
      json: async () => { if (spec.onJson) spec.onJson(); return spec.body; },
    };
    if (spec.hang) return new Promise(resolve => pending.push(() => resolve(res)));
    return Promise.resolve(res);
  };

  const ctx = {
    state,
    API_BASE,
    pageLimit: 1000,
    elements: { timeline, tabRowBtn, performanceLog: makeEl('div') },
    // `getElementById` returns null here on purpose: the 2c audit filter strip is static
    // markup that does not exist in this sandbox, and every reader of it is written to cope
    // with a missing control. Stubbing an element instead would score the filter path against
    // a stand-in the browser never sees.
    document: { createElement: makeEl, getElementById: () => null },
    fetch: fetchFake,
    Date,
    JSON,
    Array,
    encodeURIComponent,
    console: { error() {}, warn() {}, log() {} },
    // Reached only by branches these cases do not drive; declared so an accidental reach is a
    // loud throw rather than a silent global. (`renderGlobalTimeline` used to be one of these
    // and is now sliced from source — see WANTED. The function declaration overrides this
    // object's property, so nothing here can shadow the real one.)
    renderGlobalTimelineIncremental: () => { throw new Error('global incremental not under test'); },
    setTransactionFilter: () => {},
    navigateToLog: () => {},
    // Only reached from a group's expand handler, which no case here clicks.
    renderSubDetails: () => {},
  };
  vm.createContext(ctx);
  vm.runInContext(WANTED.map(n => fn(src, n)).join('\n\n'), ctx);
  return { ctx, timeline, tabRowBtn, requests, responses, pending };
}

function resetState() {
  state.currentTable = 't1';
  state.activeHistoryTab = 'row';
  state.selectedCell = { rowId: 'ROW-A', colId: 'COL-A', value: '', rowIndex: 0 };
  state.cellRowHistoryData = [];
  state.cellRowHistoryCursor = null;
  state.cellRowHistoryTruncated = false;
  state.cellRowHistoryLoaded = 0;
  state.cellRowHistoryRowTotal = null;
  state.cellRowHistoryRowTotalIsFloor = false;
  state.cellRowHistorySession = 0;
  state.currentTransactionId = null;
  state.globalHistoryData = [];
}

const log = (i, row = 'ROW-A', col = 'COL-A') => ({
  id: i, row_id: row, column_name: col, timestamp: new Date(1e12 + i * 1000).toISOString(),
  updated_by: 'user', source_name: 'user', old_value: 'a', new_value: 'b',
  transaction_id: null, is_row_deleted: false, table_name: 't1',
});
const page = (logs, cursor) => ({
  logs, truncated: cursor !== null, next_cursor: cursor, limit: 200, returned: logs.length,
});
// The CELL route's envelope. `row_history_total` is the audit count for the whole ROW and rides
// only here — on the row route the server sends `null`, because there `returned`/`truncated`
// already describe that same population. `row_history_truncated` says the count is a FLOOR (the
// server probes it capped), not an exact number.
const cellPage = (logs, cursor, rowTotal, floor = false) => ({
  ...page(logs, cursor), row_history_total: rowTotal, row_history_truncated: floor,
});
// `/audit_logs/recent`. Its list is `groups`, not `logs`, because each group carries a `logs`
// of its own — and `total_count` is the transaction's real size while `logs` holds only the
// representative the route ships, which is why a group is not just a list of rows.
const group = (txId, logs, total = logs.length, cols = ['COL-A']) => ({
  transaction_id: txId, total_count: total, summary_columns: cols, logs,
});
const recentPage = (groups, cursor = null) => ({
  groups, truncated: cursor !== null, next_cursor: cursor,
  limit_groups: 100, returned: groups.length,
});

const items = (tl) => tl.children.filter(c => c.classList.contains('timeline-item'));
const mores = (tl) => tl.children.filter(c => c.classList.contains('timeline-more'));
const moreBtn = (tl) => { const m = mores(tl)[0]; return m ? m.children[0] : null; };

// ════════════════════════════════════════════════════════════════════════════════
// A — the envelope, read once, in one place
// ════════════════════════════════════════════════════════════════════════════════
async function sectionA() {
  const R = buildSandbox().ctx.readHistoryPage;

  const env = R(page([log(1), log(2)], 'CUR1'));
  check('A1 envelope: the list is the `logs` field', env.logs.map(l => l.id), [1, 2]);
  check('A2 envelope: `next_cursor` is carried verbatim', env.nextCursor, 'CUR1');
  check('A3 envelope: truncated with a cursor is truncated', env.truncated, true);

  // 🔴 THE "CLICKABLE BUT DOES NOTHING" STATE, MADE UNREPRESENTABLE. A control painted for a
  // `truncated: true` that carries no position has nowhere to go, and it is cheaper to refuse
  // the state here than to defend against it at every place that reads the flag.
  const noCur = R({ logs: [log(1)], truncated: true, next_cursor: null });
  check('A4 truncated WITHOUT a cursor is not truncated', noCur.truncated, false);
  check('A4b ... and paints no cursor', noCur.nextCursor, null);
  check('A5 a cursor without truncated is not truncated',
    R({ logs: [log(1)], truncated: false, next_cursor: 'C' }).truncated, false);

  // A bare array is an UNPAGED server's answer, and "everything" is genuinely not truncated.
  const bare = R([log(1), log(2), log(3)]);
  check('A6 a bare array is read as a COMPLETE history',
    [bare.logs.length, bare.truncated, bare.nextCursor], [3, false, null]);

  check('A7 an empty page is empty, not a throw', R(page([], null)).logs, []);
  check('A8 a null body yields an empty list',
    [R(null).logs.length, R(null).truncated], [0, false]);
  check('A9 an empty-string cursor is no cursor', R({ logs: [], truncated: true, next_cursor: '' }).nextCursor, null);
  check('A10 a non-array `logs` yields an empty list', R({ logs: { 0: log(1) } }).logs, []);
  checkFn('A11 the result IS a plain Array', R(page([log(1)], null)).logs,
    v => Array.isArray(v), 'Array.isArray === true');
}

// ════════════════════════════════════════════════════════════════════════════════
// B — a fresh load: the array contract, and truncation on screen
// ════════════════════════════════════════════════════════════════════════════════
async function sectionB() {
  // -- truncated page --
  let S = buildSandbox();
  resetState();
  S.responses.push({ status: 200, body: page([log(1), log(2), log(3)], 'CUR1') });
  await S.ctx.loadHistory();

  // THE defect, scored directly: an envelope assigned where an array belongs.
  checkFn('B1 state.cellRowHistoryData is a plain Array after a load',
    state.cellRowHistoryData, v => Array.isArray(v), 'Array.isArray === true');
  check('B2 the rows on screen are the page', items(S.timeline).length, 3);
  check('B3 the cursor is stored verbatim, beside the list', state.cellRowHistoryCursor, 'CUR1');
  check('B3b the truncation flag is stored beside the list', state.cellRowHistoryTruncated, true);
  check('B3c the list itself carries no envelope fields',
    [state.cellRowHistoryData.truncated, state.cellRowHistoryData.next_cursor], [undefined, undefined]);
  check('B4 exactly one 더 보기 control', mores(S.timeline).length, 1);
  check('B4b ... and it is the LAST thing in the list',
    S.timeline.children[S.timeline.children.length - 1].classList.contains('timeline-more'), true);

  // 🔴 THE LABEL CARRIES THE FACT, NOT ONLY THE OFFER. `더 보기` alone answers "is this the
  // whole history?" by implication, and by implication is how a capped list passes for a
  // complete one. `일부만` is this client's existing word for a server-truncated list.
  check('B5 the control says the list is only part of the history',
    moreBtn(S.timeline).textContent.includes('일부만'), true);
  check('B5b ... and how much of it was paged in',
    moreBtn(S.timeline).textContent.includes('3건'), true);
  check('B5c ... and offers the page', moreBtn(S.timeline).textContent.includes('더 보기'), true);
  check('B6 the control is live', moreBtn(S.timeline).disabled, false);
  check('B7 the first request carries no cursor', S.requests[0].includes('cursor='), false);
  check('B7b ... and is the ROW endpoint on the row tab',
    S.requests[0], `${API_BASE}/tables/t1/rows/ROW-A/history`);

  // -- complete page: no control at all --
  S = buildSandbox();
  resetState();
  S.responses.push({ status: 200, body: page([log(1), log(2)], null) });
  await S.ctx.loadHistory();
  check('B8 a COMPLETE list carries no control', mores(S.timeline).length, 0);
  check('B8b ... and no cursor', state.cellRowHistoryCursor, null);
  check('B8c ... and its rows are all there', items(S.timeline).length, 2);

  // -- empty history --
  S = buildSandbox();
  resetState();
  S.responses.push({ status: 200, body: page([], null) });
  await S.ctx.loadHistory();
  check('B9 an empty history renders no control', mores(S.timeline).length, 0);

  // -- the cell tab hits the cell endpoint --
  S = buildSandbox();
  resetState();
  state.activeHistoryTab = 'cell';
  S.responses.push({ status: 200, body: page([log(1)], 'C') });
  await S.ctx.loadHistory();
  check('B10 the cell tab pages the CELL endpoint',
    S.requests[0], `${API_BASE}/tables/t1/rows/ROW-A/cells/COL-A/history`);

  // -- a bare array still renders (unpaged server) --
  S = buildSandbox();
  resetState();
  S.responses.push({ status: 200, body: [log(1), log(2)] });
  await S.ctx.loadHistory();
  check('B11 an unpaged server still renders, with no control',
    [items(S.timeline).length, mores(S.timeline).length], [2, 0]);
}

// ════════════════════════════════════════════════════════════════════════════════
// C — 더 보기 appends. It never replaces.
// ════════════════════════════════════════════════════════════════════════════════
async function sectionC() {
  const S = buildSandbox();
  resetState();
  S.responses.push({ status: 200, body: page([log(1), log(2)], 'CUR1') });
  await S.ctx.loadHistory();

  S.responses.push({ status: 200, body: page([log(3), log(4)], 'CUR2') });
  const btn = moreBtn(S.timeline);
  await S.ctx.loadMoreHistory(btn);

  check('C1 the rows already on screen survive the page', items(S.timeline).length, 4);
  check('C1b ... in order, oldest page last',
    state.cellRowHistoryData.map(l => l.id), [1, 2, 3, 4]);
  check('C2 the appended rows land ABOVE the control',
    S.timeline.children.map(c => c.classList.contains('timeline-more')),
    [false, false, false, false, true]);
  check('C3 the request carries the cursor verbatim',
    S.requests[1], `${API_BASE}/tables/t1/rows/ROW-A/history?cursor=CUR1`);
  check('C4 the next cursor replaces the spent one', state.cellRowHistoryCursor, 'CUR2');
  check('C5 the paged count grows', state.cellRowHistoryLoaded, 4);
  check('C5b ... and the label says so', btn.textContent.includes('4건'), true);
  check('C6 the control is live again', btn.disabled, false);

  // The last page: nothing further to page toward, so the control goes and its absence is the
  // "this is now the whole history" statement.
  S.responses.push({ status: 200, body: page([log(5)], null) });
  await S.ctx.loadMoreHistory(moreBtn(S.timeline));
  check('C7 the final page removes the control', mores(S.timeline).length, 0);
  check('C7b ... and keeps every row', items(S.timeline).length, 5);
  check('C7c ... and clears the cursor', state.cellRowHistoryCursor, null);

  // A cursor is opaque: it is handed back byte for byte, never rebuilt.
  const S2 = buildSandbox();
  resetState();
  const OPAQUE = 'MjAyNi0wOC0xMVQwNjozMzoyNi4yMDA1MzkrMDk6MDB8MjkyNDg1Nw';
  S2.responses.push({ status: 200, body: page([log(1)], OPAQUE) });
  await S2.ctx.loadHistory();
  S2.responses.push({ status: 200, body: page([log(2)], null) });
  await S2.ctx.loadMoreHistory(moreBtn(S2.timeline));
  check('C8 an opaque cursor round-trips untouched',
    S2.requests[1].endsWith(`?cursor=${OPAQUE}`), true);

  // A second click while the first page is in flight must not issue a second request.
  const S3 = buildSandbox();
  resetState();
  S3.responses.push({ status: 200, body: page([log(1)], 'C1') });
  await S3.ctx.loadHistory();
  S3.responses.push({ status: 200, body: page([log(2)], null), hang: true });
  const b3 = moreBtn(S3.timeline);
  const inflight = S3.ctx.loadMoreHistory(b3);
  check('C9 the control is disabled while its page is in flight', b3.disabled, true);
  check('C9b ... and says so', b3.textContent, '조회 중…');
  await S3.ctx.loadMoreHistory(b3);          // the double click
  check('C9c a second click issues no second request', S3.requests.length, 2);
  S3.pending.shift()();
  await inflight;
  check('C9d the in-flight page still lands', items(S3.timeline).length, 2);
}

// ════════════════════════════════════════════════════════════════════════════════
// D — a fresh load resets paging. The named defect, driven.
// ════════════════════════════════════════════════════════════════════════════════
async function sectionD() {
  // -- the cursor is retired BEFORE the new request, not after it lands --
  let S = buildSandbox();
  resetState();
  S.responses.push({ status: 200, body: page([log(1)], 'CUR-A') });
  await S.ctx.loadHistory();
  S.responses.push({ status: 200, body: page([log(9, 'ROW-B')], null), hang: true });
  state.selectedCell = { rowId: 'ROW-B', colId: 'COL-A', value: '', rowIndex: 1 };
  const load2 = S.ctx.loadHistory();
  check('D1 the previous row\'s cursor is gone before the new page arrives',
    state.cellRowHistoryCursor, null);
  check('D1b ... and so is its truncation flag', state.cellRowHistoryTruncated, false);
  check('D1c ... and its paged count', state.cellRowHistoryLoaded, 0);
  S.pending.shift()();
  await load2;
  check('D1d the new row renders its own page', state.cellRowHistoryData.map(l => l.row_id), ['ROW-B']);

  // -- THE DEFECT ITSELF: 더 보기 on row A, resolved after the operator clicked row B --
  S = buildSandbox();
  resetState();
  S.responses.push({ status: 200, body: page([log(1), log(2)], 'CUR-A') });
  await S.ctx.loadHistory();
  const btnA = moreBtn(S.timeline);
  S.responses.push({ status: 200, body: page([log(3), log(4)], 'CUR-A2'), hang: true });
  const moreA = S.ctx.loadMoreHistory(btnA);

  // ...the operator clicks another cell while page 2 is still out.
  state.selectedCell = { rowId: 'ROW-B', colId: 'COL-A', value: '', rowIndex: 1 };
  S.responses.push({ status: 200, body: page([log(9, 'ROW-B')], null) });
  await S.ctx.loadHistory();
  check('D2 row B shows its own single page', state.cellRowHistoryData.map(l => l.id), [9]);

  S.pending.shift()();
  await moreA;
  // 🔴 THE ROWS WOULD ALL BE REAL. That is what makes this defect invisible on screen: correctly
  // formatted audit entries, about a different row.
  check('D3 row A\'s page 2 is NOT appended to row B\'s list',
    state.cellRowHistoryData.map(l => l.id), [9]);
  check('D3b ... and nothing was added to the DOM either', items(S.timeline).length, 1);
  check('D3c ... and row A\'s cursor did not overwrite row B\'s', state.cellRowHistoryCursor, null);
  check('D3d ... and row B\'s paged count is its own', state.cellRowHistoryLoaded, 1);

  // -- a superseded FRESH load must not clobber the newer one either --
  S = buildSandbox();
  resetState();
  S.responses.push({ status: 200, body: page([log(1)], null), hang: true });
  const slow = S.ctx.loadHistory();
  state.selectedCell = { rowId: 'ROW-B', colId: 'COL-A', value: '', rowIndex: 1 };
  S.responses.push({ status: 200, body: page([log(9, 'ROW-B')], null) });
  await S.ctx.loadHistory();
  S.pending.shift()();
  await slow;
  check('D4 a superseded fresh load does not replace the newer list',
    state.cellRowHistoryData.map(l => l.id), [9]);

  // -- the BODY can arrive late too, and that is a separate window --
  // 🔴 THIS IS WHY THERE ARE TWO SESSION CHECKS AND NOT ONE. The first guards the fetch; by the
  //    time `res.json()` resolves the status line has long since arrived, so the first check has
  //    already passed and only a second one, after the body, can catch an operator who clicked
  //    away in between. Deleting the second check passes every other case in this file.
  S = buildSandbox();
  resetState();
  S.responses.push({ status: 200, body: page([log(1)], 'CUR-A') });
  await S.ctx.loadHistory();
  S.responses.push({
    status: 200, body: page([log(3), log(4)], null),
    // The only thing that moves this counter is a fresh `loadHistory()` — i.e. the operator
    // selecting another cell while the body was still being read.
    onJson: () => { state.cellRowHistorySession += 1; },
  });
  await S.ctx.loadMoreHistory(moreBtn(S.timeline));
  check('D6 a page whose BODY lands after the session moved is not appended',
    state.cellRowHistoryData.map(l => l.id), [1]);
  check('D6b ... and did not touch the DOM', items(S.timeline).length, 1);
  resetState();

  // -- no selection: the session retires rather than leaving a cursor behind --
  S = buildSandbox();
  resetState();
  S.responses.push({ status: 200, body: page([log(1)], 'CUR-A') });
  await S.ctx.loadHistory();
  state.selectedCell = null;
  await S.ctx.loadHistory();
  check('D5 losing the selection retires the cursor', state.cellRowHistoryCursor, null);
  check('D5b ... and the truncation flag with it', state.cellRowHistoryTruncated, false);
}

// ════════════════════════════════════════════════════════════════════════════════
// E — a failed page costs nothing that is already on screen
// ════════════════════════════════════════════════════════════════════════════════
async function sectionE() {
  // -- transport failure --
  let S = buildSandbox();
  resetState();
  S.responses.push({ status: 200, body: page([log(1), log(2)], 'CUR1') });
  await S.ctx.loadHistory();
  S.responses.push({ throws: true });
  let btn = moreBtn(S.timeline);
  await S.ctx.loadMoreHistory(btn);

  check('E1 a failed page keeps every row already on screen', items(S.timeline).length, 2);
  check('E1b ... and the list behind them', state.cellRowHistoryData.length, 2);
  check('E2 the control is NOT left disabled', btn.disabled, false);
  check('E2b ... it offers the retry', btn.textContent.includes('재시도'), true);
  check('E2c ... and shows it failed', btn.classList.contains('is-error'), true);
  check('E3 the cursor is untouched, so the retry has somewhere to go',
    state.cellRowHistoryCursor, 'CUR1');

  // the retry actually works
  S.responses.push({ status: 200, body: page([log(3)], null) });
  await S.ctx.loadMoreHistory(btn);
  check('E4 the retry lands', items(S.timeline).length, 3);
  check('E4b ... and re-asks the SAME cursor',
    S.requests[2], `${API_BASE}/tables/t1/rows/ROW-A/history?cursor=CUR1`);

  // -- a 5xx is a retry, not a lost position --
  S = buildSandbox();
  resetState();
  S.responses.push({ status: 200, body: page([log(1)], 'CUR1') });
  await S.ctx.loadHistory();
  S.responses.push({ status: 500, body: {} });
  btn = moreBtn(S.timeline);
  await S.ctx.loadMoreHistory(btn);
  check('E5 a 500 is a retry', btn.textContent.includes('재시도'), true);
  check('E5b ... and keeps the position', state.cellRowHistoryCursor, 'CUR1');

  // -- 400: the POSITION is gone. Retrying the same token can only fail again. --
  S = buildSandbox();
  resetState();
  S.responses.push({ status: 200, body: page([log(1), log(2)], 'BADCUR') });
  await S.ctx.loadHistory();
  S.responses.push({ status: 400, body: { detail: 'Invalid history cursor' } });
  btn = moreBtn(S.timeline);
  await S.ctx.loadMoreHistory(btn);

  check('E6 a 400 keeps the rows already on screen', items(S.timeline).length, 2);
  check('E6b the control does not offer the same cursor again',
    btn.textContent.includes('재시도'), false);
  check('E6c it offers a reload', btn.textContent.includes('새로고침'), true);
  check('E6d ... and says the position expired', btn.textContent.includes('위치 만료'), true);
  check('E6e ... and is still clickable', btn.disabled, false);

  // 🔴 CLICKING IT MUST START OVER, NOT RE-ASK. A control that loops on a dead cursor is the
  //    "looks clickable, does nothing" state wearing a label.
  S.responses.push({ status: 200, body: page([log(1)], null) });
  btn.click();
  await new Promise(r => setImmediate(r));
  check('E7 the reload asks page 1, with NO cursor',
    S.requests[2], `${API_BASE}/tables/t1/rows/ROW-A/history`);
  check('E7b ... and the list is rebuilt from it', items(S.timeline).length, 1);

  // -- a failed FRESH load still reports, and leaves no control --
  S = buildSandbox();
  resetState();
  S.responses.push({ throws: true });
  await S.ctx.loadHistory();
  check('E8 a failed fresh load paints no pager', mores(S.timeline).length, 0);
  check('E8b ... and says it failed', S.timeline.innerHTML.includes('Failed to load history'), true);
}

// ════════════════════════════════════════════════════════════════════════════════
// F — the array contract, run rather than typed
// ════════════════════════════════════════════════════════════════════════════════
async function sectionF() {
  const S = buildSandbox();
  resetState();
  S.responses.push({ status: 200, body: page([log(2), log(1)], 'CUR1') });
  await S.ctx.loadHistory();

  // These two are the functions that break FIRST and LOUDEST if the envelope is assigned where
  // the array belongs — and they break on a live WebSocket update, i.e. not while anyone is
  // looking at the code.
  const live = log(99);
  S.ctx.appendHistoryLocally(live);
  check('F1 appendHistoryLocally still unshifts into the list',
    state.cellRowHistoryData.map(l => l.id), [99, 2, 1]);
  check('F2 renderTimelineIncremental prepends it on screen', items(S.timeline).length, 3);
  checkFn('F2b ... at the TOP', 'the newest log heads the list',
    () => items(S.timeline)[0] === S.timeline.children[0], 'the first child IS the first item');
  check('F3 the 더 보기 control stays last',
    S.timeline.children[S.timeline.children.length - 1].classList.contains('timeline-more'), true);

  // A duplicate must still be rejected — the de-dupe reads the array too.
  S.ctx.appendHistoryLocally(live);
  check('F4 the de-dupe still works against the list', state.cellRowHistoryData.length, 3);

  // 🔴 THE PAGED COUNT IS NOT THE ARRAY LENGTH, ON PURPOSE. A live append is not something the
  //    pager fetched, so it must not inflate the number the control reports.
  check('F5 a live append does not move the paged count', state.cellRowHistoryLoaded, 2);
}

// ════════════════════════════════════════════════════════════════════════════════
// H — the GLOBAL tab, after `/audit_logs/recent` learned the envelope
// ════════════════════════════════════════════════════════════════════════════════
//
// 🔴 THIS IS THE SAME DEFECT AS SECTION B'S, ON THE OTHER TAB, AND IT FAILS MORE QUIETLY. The
//    route answered with a bare array until 2026-08-11; `state.globalHistoryData = await
//    res.json()` now stores an OBJECT, and `renderGlobalTimeline` calls `.forEach` on it. That
//    TypeError is thrown INSIDE `loadHistory`'s own try/catch, so the screen does not crash —
//    it says "Failed to load global history log", exactly as it would for a dead server. An
//    exit code sees nothing and an operator sees a network problem that is not there.
//
// A HALF-FLIPPED READ FAILS DIFFERENTLY AND JUST AS QUIETLY: opening `logs` instead of `groups`
// yields an empty array, so the panel renders "No database history recorded." over a database
// full of history. H2b is what tells those two apart from a working read, and neither is
// distinguishable from success by a count of assertions or by an exit code.
//
// H5 IS DELIBERATELY NOT ENOUGH ON ITS OWN. A bare array still renders, and a client that never
// learned the envelope passes that case — which is why the flip is scored on H2/H3, against a
// body only the flipped server sends.
//
// ⚠️ NOTHING BELOW MAY ASSUME THE THING IS A LIST. The defect this section exists for replaces
//    that array with an object, so a bare `.map`/`.find`/`items()[0]` here would throw before the
//    summary line printed — and a harness that dies without `ASSERTIONS` reports to the build gate
//    as DEAD, which is the disguise that gate was written to strip. A regression must arrive as a
//    clean red naming every assertion it broke. `txIds` and `entryHtml` exist only for that.
const txIds = (v) => Array.isArray(v) ? v.map(g => g.transaction_id) : `NOT AN ARRAY: ${typeof v}`;
const entryHtml = (tl, i) => { const el = items(tl)[i]; return el ? el.innerHTML : '(nothing rendered)'; };

async function sectionH() {
  let S = buildSandbox();
  resetState();
  state.activeHistoryTab = 'global';
  S.responses.push({ status: 200, body: recentPage([
    group('TX-1', [log(1)], 5),      // a bulk transaction: 5 rows, 1 representative log
    group('TX-2', [log(2)]),         // a single-cell edit
  ], 'RCUR1') });
  await S.ctx.loadHistory();

  check('H1 the flip did not move the request',
    S.requests[0], `${API_BASE}/audit_logs/recent?limit_groups=100`);
  checkFn('H2 state.globalHistoryData is a plain Array after a global load',
    state.globalHistoryData, v => Array.isArray(v), 'Array.isArray === true');
  check('H2b ... and holds the GROUPS, in the order they arrived',
    txIds(state.globalHistoryData), ['TX-1', 'TX-2']);
  check('H2c ... and carries no envelope field of its own',
    [state.globalHistoryData.truncated, state.globalHistoryData.next_cursor,
     state.globalHistoryData.groups, state.globalHistoryData.returned],
    [undefined, undefined, undefined, undefined]);

  // THE PANEL, RENDERED — by the real `renderGlobalTimeline` and the real item factory. "It
  // still renders" is the claim this whole change has to survive, and it is not a type check.
  check('H3 the panel painted one entry per group', items(S.timeline).length, 2);
  check('H3b ... reading the GROUP, not just its representative log',
    entryHtml(S.timeline, 0).includes('5건 변경'), true);
  check('H3c ... and the single-log group renders its column',
    entryHtml(S.timeline, 1).includes('COL-A'), true);
  check('H3d ... each tagged with its transaction',
    items(S.timeline).map(li => li.dataset.txId), ['TX-1', 'TX-2']);

  // The array contract, RUN. `appendHistoryLocally` is the WebSocket path, and on this tab it
  // calls `.find` and `.unshift` on `globalHistoryData` — so it is the second thing an envelope
  // assigned here would break, minutes after the load, with nobody looking at the code.
  let liveErr = null;
  try {
    S.ctx.appendHistoryLocally({ ...log(7), transaction_id: 'TX-3' }, true);
    S.ctx.appendHistoryLocally({ ...log(8), transaction_id: 'TX-1' }, true);
  } catch (e) { liveErr = String((e && e.message) || e); }
  check('H4 a live WebSocket log does not throw against the loaded list', liveErr, null);
  check('H4b ... one with no group on screen becomes a group, at the top',
    txIds(state.globalHistoryData), ['TX-3', 'TX-1', 'TX-2']);
  const tx1 = Array.isArray(state.globalHistoryData)
    ? state.globalHistoryData.find(g => g.transaction_id === 'TX-1') : null;
  check('H4c ... one for a known group joins it, newest first',
    tx1 ? tx1.logs.map(l => l.id) : null, [8, 1]);
  check('H4d ... and that group\'s count grows with it', tx1 ? tx1.total_count : null, 6);

  // -- a server that has NOT flipped still renders --
  S = buildSandbox();
  resetState();
  state.activeHistoryTab = 'global';
  S.responses.push({ status: 200, body: [group('TX-9', [log(9)])] });
  await S.ctx.loadHistory();
  check('H5 a bare array is still read, and still painted',
    [txIds(state.globalHistoryData), items(S.timeline).length], [['TX-9'], 1]);

  // -- an empty projection states itself --
  S = buildSandbox();
  resetState();
  state.activeHistoryTab = 'global';
  S.responses.push({ status: 200, body: recentPage([]) });
  await S.ctx.loadHistory();
  check('H6 an empty projection says so',
    S.timeline.innerHTML.includes('No database history recorded'), true);
  checkFn('H6b ... and still leaves an Array behind', state.globalHistoryData,
    v => Array.isArray(v) && v.length === 0, 'an empty Array');

  // -- a body whose list is under some OTHER name is empty, never an object --
  S = buildSandbox();
  resetState();
  state.activeHistoryTab = 'global';
  S.responses.push({ status: 200, body: { logs: [group('TX-X', [log(1)])], truncated: false, next_cursor: null } });
  await S.ctx.loadHistory();
  checkFn('H7 an unrecognised list name yields an Array, not a throw and not an object',
    state.globalHistoryData, v => Array.isArray(v) && v.length === 0, 'an empty Array');

  // -- and a genuinely failed load still reports as one --
  S = buildSandbox();
  resetState();
  state.activeHistoryTab = 'global';
  S.responses.push({ throws: true });
  await S.ctx.loadHistory();
  check('H8 a failed global load says it failed',
    S.timeline.innerHTML.includes('Failed to load global history'), true);
  resetState();
}

// ════════════════════════════════════════════════════════════════════════════════
// I — an empty cell tab is TWO facts, and it used to be one sentence
//
// 🔴 THE SILENT WRONG ANSWER THIS SECTION EXISTS FOR. Machine writes (parsers, chains, scripts)
//    record ONE audit row per ROW under the literal column name `ROW_UPDATE`, so the cell
//    route's `column_name == col` filter can never match them. Isolated `assy_qa` measurement
//    2026-08-11 (that workstation, NOT a production figure): 225,101 rows carry machine history
//    and not one per-column entry — on every one of them, every cell tab is empty while the row
//    tab is full. `No change history recorded.` told the operator those records did not exist.
//
// SO THE ASSERTION IS NOT "the message changed", IT IS "the two states are DISTINGUISHABLE and
// the one that can be escaped offers the escape". A screen that renders both as 기록 없음 passes
// any test that only checks the empty slot is non-empty.
// ════════════════════════════════════════════════════════════════════════════════
const emptyLi = (tl) => tl.children.find(c => c.classList.contains('timeline-empty')) || null;
const emptySlot = (tl) => {
  const li = emptyLi(tl);
  if (!li) return { text: null, note: null, action: null };
  const note = li.children.find(c => c.classList.contains('timeline-empty-note'));
  const action = li.children.find(c => c.tagName === 'BUTTON');
  return { text: li.textContent, note: note ? note.textContent : null, action };
};

async function sectionI() {
  // -- state 1: the row really has nothing --
  let S = buildSandbox();
  resetState();
  state.activeHistoryTab = 'cell';
  S.responses.push({ status: 200, body: cellPage([], null, 0) });
  await S.ctx.loadHistory();
  let slot = emptySlot(S.timeline);
  check('I1 no history anywhere reads as 기록 없음', slot.text, '기록 없음');
  check('I1b ... and offers nowhere to go', slot.action === undefined || slot.action === null, true);
  check('I1c ... and is not a pager', mores(S.timeline).length, 0);

  // -- state 2: the records exist and THIS SCREEN cannot show them --
  S = buildSandbox();
  resetState();
  state.activeHistoryTab = 'cell';
  S.responses.push({ status: 200, body: cellPage([], null, 225101) });
  await S.ctx.loadHistory();
  slot = emptySlot(S.timeline);
  check('I2 the two empty states are NOT the same text', slot.text === '기록 없음', false);
  check('I2b the cell is what is empty, and it says so', slot.note, '이 셀 기록 없음');
  checkFn('I2c the row-level count reaches the screen',
    slot.action && slot.action.textContent,
    t => typeof t === 'string' && t.includes('225') && t.includes('101') && t.includes('건'),
    'a label carrying the 225101 count (grouped per locale) and 건');
  check('I2d ... as the ROW history, named', slot.action.textContent.includes('행 이력'), true);
  check('I2e the count is stored beside the list, not on it',
    [state.cellRowHistoryRowTotal, state.cellRowHistoryData.row_history_total], [225101, undefined]);

  // The way out, in ONE action — and through the row tab's own button, so nothing here is a
  // second copy of the tab switch.
  let tabClicks = 0;
  S.tabRowBtn.addEventListener('click', () => { tabClicks++; });
  slot.action.click();
  check('I3 one click on the disclosure reaches the Row History tab', tabClicks, 1);

  // -- the count is a FLOOR when the server says it is --
  S = buildSandbox();
  resetState();
  state.activeHistoryTab = 'cell';
  S.responses.push({ status: 200, body: cellPage([], null, 1000, true) });
  await S.ctx.loadHistory();
  check('I4 a capped count is not presented as exact',
    emptySlot(S.timeline).action.textContent.includes('이상'), true);

  // -- and is NOT hedged when it is exact. A small count also pins the whole label with no
  //    locale grouping in the way.
  S = buildSandbox();
  resetState();
  state.activeHistoryTab = 'cell';
  S.responses.push({ status: 200, body: cellPage([], null, 3) });
  await S.ctx.loadHistory();
  check('I5 an exact count states the number plainly',
    emptySlot(S.timeline).action.textContent, '행 이력 3건 보기');

  // -- the ROW tab never shows the disclosure: it IS the destination, and the server sends
  //    `row_history_total: null` there --
  S = buildSandbox();
  resetState();
  state.activeHistoryTab = 'row';
  S.responses.push({ status: 200, body: page([], null) });
  await S.ctx.loadHistory();
  check('I6 the row tab does not point at itself', emptySlot(S.timeline).text, '기록 없음');

  // -- a count must not outlive the cell it described. Same sandbox, second cell: a disclosure
  //    reading "행 이력 12건" under a row that has none is confidently wrong, which is worse
  //    than the message that was missing. --
  S = buildSandbox();
  resetState();
  state.activeHistoryTab = 'cell';
  S.responses.push({ status: 200, body: cellPage([], null, 12) });
  await S.ctx.loadHistory();
  check('I7 precondition: the first cell discloses', emptySlot(S.timeline).note, '이 셀 기록 없음');
  state.selectedCell = { rowId: 'ROW-B', colId: 'COL-A', value: '', rowIndex: 1 };
  S.responses.push({ status: 200, body: cellPage([], null, 0) });
  await S.ctx.loadHistory();
  check('I7b a stale count does not follow the operator to the next cell',
    emptySlot(S.timeline).text, '기록 없음');

  // -- both states stay removable by a live log. `renderTimelineIncremental` finds the empty
  //    slot by `.timeline-empty`; a disclosure that dropped the class would sit above the first
  //    real record forever. --
  S = buildSandbox();
  resetState();
  state.activeHistoryTab = 'cell';
  S.responses.push({ status: 200, body: cellPage([], null, 7) });
  await S.ctx.loadHistory();
  check('I8 precondition: the disclosure is on screen', emptySlot(S.timeline).action !== undefined, true);
  S.ctx.renderTimelineIncremental(log(9));
  check('I8b a live log clears the disclosure', emptyLi(S.timeline), null);
  check('I8c ... and the record is what remains', items(S.timeline).length, 1);
  resetState();
}

// ════════════════════════════════════════════════════════════════════════════════
// G — the mutation corpus. Every defect must be CAUGHT; the controls must not fire.
// ════════════════════════════════════════════════════════════════════════════════
const MUTANTS = [
  { name: 'envelope assigned where the array belongs (the original defect)', defect: true,
    find: 'state.cellRowHistoryData = page.logs;',
    repl: 'state.cellRowHistoryData = page;' },
  // Re-anchored 2026-08-12: `readHistoryPage`'s return became a multi-line object when it
  // started carrying `row_history_total`. The CONTRACT is untouched — `truncated` still requires
  // a cursor — so this is the same mutant against the same line, spelled where the line now is.
  { name: 'truncated no longer requires a cursor', defect: true,
    find: '    truncated: !!(body && body.truncated) && !!nextCursor,',
    repl: '    truncated: !!(body && body.truncated),' },
  // ── The two empty states ────────────────────────────────────────────────────
  // Each of these puts the screen back exactly where it was before this round: an empty cell tab
  // that says the records do not exist, over a row that has 225,101 of them.
  { name: 'the reader drops the row-history count again', defect: true,
    find: '    rowHistoryTotal: typeof rowTotal === \'number\' ? rowTotal : null,',
    repl: '    rowHistoryTotal: null,' },
  { name: 'the two empty states collapse back into one', defect: true,
    find: "  if (state.activeHistoryTab !== 'cell' || !total || total <= 0) {",
    repl: '  if (true) {' },
  { name: 'a floor count is presented as an exact one', defect: true,
    find: '  btn.textContent = state.cellRowHistoryRowTotalIsFloor\n'
        + '    ? `행 이력 ${total.toLocaleString()}건 이상 보기`\n'
        + '    : `행 이력 ${total.toLocaleString()}건 보기`;',
    repl: '  btn.textContent = `행 이력 ${total.toLocaleString()}건 보기`;' },
  { name: 'the disclosure states the count but offers no way to the row tab', defect: true,
    find: '    elements.tabRowBtn?.click();',
    repl: '' },
  // NOT MUTATED, DELIBERATELY: the `cellRowHistoryRowTotal = null` reset in
  // `beginHistorySession`. Removing it changes nothing observable today — every path that
  // RENDERS the empty slot assigns the field first — so a "defect" mutant there would be one
  // this corpus can never catch, and a mutant nobody can catch is a red build, not coverage.
  // The reset stays in the source for the same reason the cursor's does: it is the envelope's
  // reset point, and the next path that renders without assigning must not inherit a count.
  { name: 'the paging session never advances', defect: true,
    find: '  state.cellRowHistorySession += 1;\n  return state.cellRowHistorySession;',
    repl: '  return state.cellRowHistorySession;' },
  { name: 'the pager replaces the list instead of appending', defect: true,
    find: '    state.cellRowHistoryData.push(log);',
    repl: '    state.cellRowHistoryData = [log];' },
  { name: 'the pager stops checking whether its session survived', defect: true,
    find: '  // The session moved on while this was in flight (another cell, another tab, a refresh). These\n'
        + '  // rows are real and they belong to a list that is no longer on screen.\n'
        + '  if (session !== state.cellRowHistorySession) return;',
    repl: '' },
  { name: 'a 400 becomes a retry on the same dead cursor', defect: true,
    find: '      markMoreLost(btn);',
    repl: '      markMoreFailed(btn);' },
  { name: 'a failed page leaves the control disabled', defect: true,
    find: "  btn.disabled = false;\n  btn.textContent = '조회 실패 · 재시도';",
    repl: "  btn.disabled = true;\n  btn.textContent = '조회 실패 · 재시도';" },
  { name: 'the control offers the page without stating the list is capped', defect: true,
    find: 'return `일부만 (${state.cellRowHistoryLoaded}건) · 더 보기`;',
    repl: 'return `더 보기`;' },
  { name: 'a complete list keeps a pager anyway', defect: true,
    find: '  if (!state.cellRowHistoryTruncated || !state.cellRowHistoryCursor) return;',
    repl: '  if (false) return;' },
  { name: 'the cursor is dropped from the page request', defect: true,
    find: "  if (cursor) url += `?cursor=${encodeURIComponent(cursor)}`;",
    repl: '  if (false) url += cursor;' },
  // THE FLIP, UNDONE — this is verbatim the code that shipped before the envelope landed. It
  // must be caught, and the reason it is worth a mutant of its own is that it does NOT crash:
  // the TypeError lands in `loadHistory`'s catch and the panel reports a failed fetch.
  { name: 'the global panel assigns the envelope where the array belongs', defect: true,
    find: "      const { logs: groups } = readHistoryPage(await res.json(), 'groups');\n"
        + '      state.globalHistoryData = groups;',
    repl: '      state.globalHistoryData = await res.json();' },
  // Half-flipped: the envelope is opened, under the wrong list name. The panel then declares an
  // empty history over a full database, which is a wrong answer wearing an empty state.
  { name: 'the global read opens the wrong list of the envelope', defect: true,
    find: "readHistoryPage(await res.json(), 'groups')",
    repl: 'readHistoryPage(await res.json())' },
  // Controls: real edits that change nothing observable. If either of these "fails", the
  // sections above are keyed on something other than the behaviour they claim to score.
  { name: 'CONTROL: a comment is reworded', defect: false,
    find: '// [History paging] Fetch the next page and APPEND it. Never replaces what is on screen.',
    repl: '// [History paging] fetch and append.' },
  { name: 'CONTROL: a local is renamed', defect: false,
    find: '  const cursor = state.cellRowHistoryCursor;',
    repl: '  const cursorToken = state.cellRowHistoryCursor;\n  const cursor = cursorToken;' },
];

async function sectionG() {
  for (const m of MUTANTS) {
    UNDER_TEST = applyOnce(TL0, m.find, m.repl, m.name);
    const before = { pass, fail, names: failures.length };
    const silent = console.error;
    console.error = () => {};
    let caught = false;
    try {
      await sectionA();
      await sectionB();
      await sectionC();
      await sectionD();
      await sectionE();
      await sectionF();
      await sectionH();
      await sectionI();
    } catch (e) {
      // A mutant that throws (a slice that no longer parses, a DOM operation that cannot apply)
      // is caught just as surely as one that fails an assertion.
      caught = true;
    } finally {
      console.error = silent;
      UNDER_TEST = TL0;
    }
    caught = caught || fail > before.fail;
    // The mutant run's own scores are not evidence about the product — the only thing carried
    // out of it is the VERDICT below. Roll the counters AND the failure names back.
    pass = before.pass; fail = before.fail; failures.length = before.names;
    check(`G/${m.defect ? 'defect' : 'control'}: ${m.name}`, caught, m.defect);
  }
}

// ── Run ─────────────────────────────────────────────────────────────────────────
await sectionA();
await sectionB();
await sectionC();
await sectionD();
await sectionE();
await sectionF();
await sectionH();
await sectionI();
const beforeG = { pass, fail };
await sectionG();

resetState();
const ran = pass + fail;
if (fail > 0) {
  console.error(`\n  ${fail} failing assertion(s):`);
  failures.forEach(n => console.error(`  ✗ ${n}`));
} else {
  console.log(`✓ history paging: ${beforeG.pass} behaviour assertions + ${MUTANTS.length} mutation verdicts`);
}
console.log(`ASSERTIONS ${ran} ${fail}`);
