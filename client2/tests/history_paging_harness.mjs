// Harness — THE SIDEBAR TIMELINE READS A PAGE, AND SAYS SO WHEN IT IS ONE.
// Run: node client2/tests/history_paging_harness.mjs   (no node_modules)
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
// `createHistoryMoreDom`, `renderTimelineIncremental` and `appendHistoryLocally` are RUN,
// against a scripted `fetch` and a minimal document. Nothing here re-implements them;
// re-implementing would score this file against itself.
//
// 🔴 C-58 — AND THEY ARE NO LONGER CUT OUT TO DO IT. Until today this file lifted 24 function
//    bodies out of `timeline.js` by regex and evaluated them in a `vm`, which measures the shape
//    of the letters rather than the behaviour (owner's standing rule, 2026-09-02). Its own
//    comments recorded the bill three separate times: adding ONE import to `timeline.js` made
//    this file throw on code that was CORRECT, and a new callee missing from the WANTED list
//    made section H paint nothing at all — 「전부 코드가 맞는데 빨개집니다」, in this very file.
//
//    The module is now loaded WHOLE through `lib/probe.mjs`: its source is copied byte for byte,
//    a probe object naming what this harness calls is APPENDED after the last line, and the copy
//    is imported. Nothing is removed, so every reason the ban exists is gone — a new import still
//    runs, a new `const` is still in scope, a new callee is still in the same file. WANTED stops
//    being a list of things to CUT and becomes a list of things to REACH, and a name that is not
//    there throws loudly instead of quietly resolving to undefined.
//    ⚠️ A bridge, not a destination: the destination is `timeline.js` small enough that the names
//       this file drives are simply exported. That is not this round.
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
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';
import { loadWithProbe } from './lib/probe.mjs';
// 🔴 THE BASE URL IS THE PRODUCT'S OWN. It was a literal here, which was fine while the subject
//    was a fragment handed its constants — but the subject now imports `config.js` itself, and a
//    second literal would be this harness asserting against its own idea of the route rather
//    than against the one the screen builds.
import { API_BASE } from '../src/config.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = (f) => join(HERE, '..', 'src', f);
const TIMELINE_PATH = SRC('timeline.js');

// 🔴 THE REAL CONSOLE, CAPTURED BEFORE ANYTHING IS SILENCED — and then the global one is
//    replaced, because the subject writes to it now.
//
//    While this file sliced, the `vm` handed the fragments a no-op console and this harness kept
//    the real one; loading the module WHOLE means `timeline.js` reports its own failures to
//    whatever `console` is. Sections E and H drive a dead server ON PURPOSE, so a correct run
//    printed 40 lines of the subject's stack traces around its own verdict — an instrument whose
//    output is mostly someone else's noise gets read less carefully, and this file's whole job is
//    to be read when it goes red.
//
// ⚠️ `OUT` is captured FIRST and every line this file prints goes through it, so silencing the
//    global cannot silence the harness. `lib/probe.mjs` does exactly the same thing for exactly
//    the same reason — it once had its own failure swallowed by a harness's recording console,
//    and exited 2 with no output at all.
const OUT = console;
globalThis.console = { log() {}, error() {}, warn() {}, info() {}, debug() {}, trace() {} };
// Set while a mutant runs: its assertion failures ARE the catch, so they are not printed.
let quiet = false;

function die(msg) {
  OUT.error(`HARNESS FAILURE: ${msg}`);
  OUT.error('(This is not a passing result. Nothing was compared.)');
  OUT.log('ASSERTIONS 0 1');
  process.exit(2);
}

// `state.js` reads `window.location.search` at module scope, so the global has to exist before
// the import. Set here rather than faked away, so the import is the real module.
//
// 🔴 C-58: IT NEEDS `addEventListener` NOW, AND THAT IS THE CONVERSION SHOWING ITS WORK.
//    `utils.js` registers a focus listener at module scope behind `typeof window !== 'undefined'`.
//    While this file sliced, `utils.js` was imported at the TOP — before this line ran — so the
//    guard saw no window and the registration never happened. Loading `timeline.js` WHOLE runs
//    its import graph after this line, so the branch the browser takes is the branch taken here.
//    A stub that answers `window` but not `window.addEventListener` is a browser that does not
//    exist; this one is shaped like the real thing rather than like the subset one path needed.
globalThis.window = {
  location: { search: '' },
  addEventListener() {}, removeEventListener() {},
};
const STATE_MOD = await import(pathToFileURL(SRC('state.js')).href);
// 🔴 The module is imported here as well, for the constants THIS FILE reads while building
//    fixtures. Retyping 'ledger_batch' would put a second author on a server word, which is
//    the exact thing the subject refuses to do.
// ⚠️ C-58: the SUBJECT no longer needs them handed to it — it imports them itself. This
//    import stays because the harness's own fixtures are built from them.
const TIMELINE_MOD = await import(pathToFileURL(SRC('timeline.js')).href);
const ABSENT_MOD = await import(pathToFileURL(SRC('absent.js')).href);
const state = STATE_MOD.state;
if (!state || typeof state !== 'object') die('client2/src/state.js no longer exports `state`.');

// ── The names this harness REACHES ──────────────────────────────────────────────
// 🔴 C-58: this list used to be the CUT LIST — every name here was carved out of the source and
//    the rest of the file thrown away, so a function that started calling a helper not on this
//    list threw, and a green run and a dead run looked alike. It is now `spec.expose`: the whole
//    module is loaded and these are the handles onto it. A name that no longer exists throws on
//    evaluation, which is the loud failure — a probe that quietly returned undefined would let a
//    renamed function score green.
const WANTED = [
  'loadHistory', 'historyUrl', 'beginHistorySession', 'readHistoryPage',
  // `createHistoryEmptyDom` is REACHED rather than stubbed because the claim under test IS
  // what it paints: two different facts that used to share one sentence. A stub would score
  // section I against the harness's own idea of the empty slot.
  'renderTimeline', 'createHistoryEmptyDom', 'renderHistoryMore', 'historyMoreLabel', 'createHistoryMoreDom',
  'markMoreFailed', 'markMoreLost', 'loadMoreHistory',
  // The pane declarations themselves. A pager that takes a pane has to be driven with
  // ONE -- and with the one belonging to THIS module copy, which is why it is read off
  // `S.ctx` at each call site rather than aliased once at the top of the section.
  'HISTORY_PANES',
  'renderTimelineIncremental', 'createTimelineItemDom', 'appendHistoryLocally', 'formatVal',
  // The global tab, for section H. `renderGlobalTimeline` is the function that dies when the
  // envelope is assigned where the array belongs, and `createGlobalTimelineItemDom` is what
  // actually paints an entry — stubbing the second would leave "the panel renders" asserted
  // against a stand-in rather than against the code that renders it.
  // `auditKind` and `auditVal` are what the 2c row calls while painting, named here for the
  // same reason as the two above: a stub would let the row render against the harness's idea
  // of a kind pill.
  // ⚠️ C-58: naming a callee here is no longer LOAD-BEARING — the whole module is loaded, so a
  //    function it calls is in the file whether or not this list mentions it. These names are
  //    here because the harness CALLS them directly. The three notes below record the rounds
  //    that were lost to the old rule, and are kept as the reason the rule went.
  'renderGlobalTimeline', 'createGlobalTimelineItemDom', 'auditKind', 'auditVal',
  // The 2c filter strip's helpers, called directly by cases in section H.
  // ⚰️ Until C-58, leaving them out made the SLICE throw and section H paint nothing.
  'auditFilterState', 'groupKindLabel', 'fillAuditFilterOptions', 'auditFilterPasses',
  // ⚰️ The 2c row asks which table the transaction touched. Leaving it out used to make the
  //    slice throw and section H paint nothing -- which is how this harness reported THAT
  //    change: as its own breakage, on product code that was correct.
  'auditTargetTable',
  // ⚰️ C-55. The row asks the receipt reader for its one line -- the THIRD time this file
  //    recorded the same breakage. 🔴 그리고 이것이 그 금지의 실물이었습니다: 대상 코드는
  //    «맞는데» 잘라낸 조각이 새 이름을 못 찾아 섹션 H 가 통째로 0 을 그렸습니다
  //    (소유자 상설 2026-09-02: 잘라쓰기 하니스 절대 금지 — 「전부 코드가 맞는데 빨개집니다」).
  //    C-58 이 그 세 번을 끝냈습니다 — 이제 새 이름은 «파일 안에 그대로» 있습니다.
  'ledgerReceiptLine',
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
  if (!quiet) OUT.error(`  FAIL ${name}\n       expected ${e}\n       actual   ${a}`);
  return false;
}
function checkFn(name, actual, pred, describe) {
  if (pred(actual)) { pass++; return true; }
  fail++; failures.push(name);
  if (!quiet) OUT.error(`  FAIL ${name}\n       expected ${describe}\n       actual   ${JSON.stringify(actual)}`);
  return false;
}

// ── A minimal document ──────────────────────────────────────────────────────────
// Only what the subject touches. `innerHTML =` drops children exactly as the real one does,
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
//
// 🔴 THE SUBJECT IS ONE LOADED MODULE, AND THE SANDBOX IS WHAT IT LOOKS AT. Slicing gave every
//    sandbox its own copy of the code; a loaded module has one. So what varies per sandbox is
//    the WORLD — the scripted `fetch` and the document `dom.js` reads its elements out of — and
//    a sandbox claims that world when one of its functions is called. The cases in this file
//    interleave awaits WITHIN one sandbox (section D is built on exactly that) and never across
//    two, which is what makes one live world correct rather than a race.
let CURRENT = null;

// `timeline.js` reaches `document` and `fetch` as GLOBALS at call time, never at load time, so
// these are installed once and delegate to whichever sandbox is live.
// `getElementById` answers only the three ids `dom.js` maps to nodes this harness owns. Every
// other id is null ON PURPOSE: the 2c audit filter strip is static markup that does not exist
// here, and every reader of it is written to cope with a missing control — stubbing one would
// score the filter path against a stand-in the browser never sees.
globalThis.document = {
  createElement: makeEl,
  getElementById: (id) => {
    if (!CURRENT) return null;
    if (id === 'timeline') return CURRENT.timeline;
    if (id === 'tab-row') return CURRENT.tabRowBtn;
    if (id === 'performance-log') return CURRENT.performanceLog;
    return null;
  },
  addEventListener() {},
  querySelector: () => null,
};
globalThis.fetch = (...args) => {
  if (!CURRENT) throw new Error('fetch before any sandbox was built');
  return CURRENT.fetchFake(...args);
};

// The mutation applied to the subject's source, or null for the product as it stands. Section G
// swaps it so the SAME sections re-run against the defect — a corpus that only mutated one entry
// point would score the mutation, not the assertions.
let UNDER_TEST = null;

// One load per distinct source text. The subject holds no per-run module state (its only
// module-level `let` is a debounce timer no case here arms), so a sandbox can be a fresh WORLD
// over an already-loaded module — which is what keeps 19 mutants × 8 sections at 20 loads
// instead of 600.
const LOADED = new Map();
async function subjectFor(spec) {
  const key = spec ? spec.name : '__base__';
  if (!LOADED.has(key)) {
    const opts = { expose: WANTED };
    if (spec) {
      opts.tag = key.replace(/\W+/g, '_').slice(0, 40);
      opts.mutate = (text) => applyOnce(text, spec.find, spec.repl, spec.name);
    }
    LOADED.set(key, (await loadWithProbe(TIMELINE_PATH, opts)).probe);
  }
  return LOADED.get(key);
}

// One scripted request queue. Every entry is consumed in order and the URL it was asked for is
// recorded, so "which endpoint, with which cursor" is scored rather than assumed.
async function buildSandbox() {
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

  // 🔴 THE SEVEN NAMES THE `vm` USED TO CARRY ARE GONE, AND THAT IS THE WHOLE POINT.
  //    `escapeHtml`, `saysTruncated`, `LEDGER_BATCH_COLUMN`, `NO_TRANSACTION_BUCKET`,
  //    `isCount`, `API_BASE` and `pageLimit` had to be handed in because sliced code cannot
  //    resolve an import — and each one was a place where this harness could quietly become
  //    the second author of a product fact. The module imports them itself now. So does every
  //    name that has not been thought of yet, which is the difference between a list that has
  //    to be maintained and one that does not.
  //
  // ⚠️ The four the vm stubbed (`renderGlobalTimelineIncremental`, `setTransactionFilter`,
  //    `navigateToLog`, `renderSubDetails`) are the REAL ones now. They sit on branches no case
  //    here drives; if one is ever reached it does the real thing rather than a stand-in's
  //    thing, which is strictly the better failure.
  const sandbox = { timeline, tabRowBtn, performanceLog: makeEl('div'),
    fetchFake, requests, responses, pending };
  const subject = await subjectFor(UNDER_TEST);
  // Every call CLAIMS the world first, so a case that holds two sandboxes reads the right one.
  const ctx = {};
  // 🔴 C-63. NO CALL MAY STALL THE GATE. The response queue is POSITIONAL, so a mutant that
  //    changes which requests are issued also changes which scripted response each call gets —
  //    and a `hang: true` meant for a call that never happened can be consumed by a call that IS
  //    awaited, whose promise then nobody can resolve. Measured while closing the four throwing
  //    mutants: the suite hung on `await sectionG()` with no output at all.
  // ⚠️ A stall is the WORST instrument failure, worse than the crash this round is removing: a
  //    crash names a line, a stall names nothing and the build waits forever. So a call that does
  //    not settle becomes a rejection that SAYS WHICH CALL, and the corpus reports it by name.
  //    The base run settles in milliseconds, so this can only fire on a defect.
  const CALL_TIMEOUT_MS = 5000;
  for (const name of WANTED) {
    ctx[name] = (...args) => {
      CURRENT = sandbox;
      const out = subject[name](...args);
      if (!out || typeof out.then !== 'function') return out;
      // ⚠️ NOT `unref`ed. An unreferenced timer lets node see an empty event loop and exit with
      //    「unsettled top-level await」 — which is the stall wearing a different hat: no verdict,
      //    no name, no assertion count. The timer must hold the loop open long enough to reject.
      let timer;
      const stalled = new Promise((_, reject) => {
        timer = setTimeout(
          () => reject(new Error(`${name}() never settled (${CALL_TIMEOUT_MS}ms)`)), CALL_TIMEOUT_MS);
      });
      return Promise.race([out, stalled]).finally(() => clearTimeout(timer));
    };
  }
  CURRENT = sandbox;
  sandbox.ctx = ctx;
  // 🔴 A DATA EXPORT CANNOT COME THROUGH `ctx`. Every WANTED name is wrapped there as a
  //    CALLABLE (the stall guard above), so `ctx.HISTORY_PANES` is that wrapper and
  //    `.global` off it is `undefined` -- which falls through to `loadMoreHistory`'s
  //    default pane and pages the WRONG TAB while every assertion still runs. Measured
  //    while writing section J: the calls issued no request at all and the failures read
  //    like a broken pager. The panes come off the module copy itself, and off THIS one.
  sandbox.panes = subject.HISTORY_PANES;
  return sandbox;
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

// 🔴 C-63. TOTAL, BECAUSE THE DEFECT THIS FILE EXISTS FOR PUTS AN OBJECT WHERE THE LIST IS.
//    B1 names that (Array.isArray), and every OTHER assertion that reads the list by id must
//    fail against it rather than die on `.map is not a function` -- a crash ends the section
//    before B1's verdict can be believed, and gets banked as 『caught』.
const listIds = (v, field = 'id') => (Array.isArray(v)
  ? v.map(l => l[field])
  : `NOT A LIST: ${JSON.stringify(v)}`);
// 🔴 C-63. ONE TOTAL READER FOR 「what does this control say / is it live」.
//    A control that is NOT THERE is a fact some assertion above already names by number
//    (B4 counts the 더 보기 controls; I2c says the disclosure carries the row count). Every
//    assertion that then describes its WORDING must fail against its absence rather than
//    dereference it — a crash ends the section before the naming assertion is believed, and
//    the corpus banks the crash as 「the mutant was caught」. It was not caught; the harness
//    stopped. Four of nineteen mutants were being scored that way until this round.
// ⚠️ The stand-in strings are deliberately not empty: `''.includes(x)` is false for every x,
//    so an empty string would make 「absent」 and 「says the wrong thing」 the same failure text.
const textOf = (el) => (el && typeof el.textContent === 'string' ? el.textContent : '(NO ELEMENT)');
const says = (el, word) => textOf(el).includes(word);
// A request that was never issued is a fact the assertion above it names by URL; reading it
// as a string here would end the section instead.
const urlAt = (S, i) => (typeof S.requests[i] === 'string' ? S.requests[i] : '(NO REQUEST)');

/**
 * Park a call the case believes is now IN FLIGHT, and keep a broken belief from stalling.
 *
 * 🔴 C-63. THE SUBJECT MAY NOT HAVE ISSUED THE REQUEST AT ALL. Under the envelope defect the
 *    timeline paints nothing, so there is no 더 보기 control, so `loadMoreHistory(null)`
 *    returns without fetching — and the `hang: true` the case scripted for it is STILL IN THE
 *    QUEUE. The next call the case awaits directly then consumes that hang and waits on a
 *    resolver this case has already walked past: the whole gate stops, with no verdict and no
 *    assertion count. Measured while closing this round.
 * 🔵 An async function runs to its first `await`, so `fetch` — and therefore the resolver in
 *    `pending` — has already happened by the time the promise is handed back. An empty
 *    `pending` here means nothing went out, full stop.
 * ⚠️ The premise that failed (「a page is in flight」) is exactly what the assertions below
 *    describe, so this un-hangs the queue and lets them FAIL BY NAME. It never asserts
 *    anything itself — an instrument that scores its own repairs is scoring itself.
 */
function parked(S, promise) {
  if (S.pending.length === 0) for (const spec of S.responses) spec.hang = false;
  return promise;
}

/**
 * Release the request a case parked, then wait for the call that was waiting on it.
 *
 * 🔴 C-63. A MUTANT CHANGES WHICH REQUESTS ARE ISSUED, so the hung one a case scripted may
 *    never exist. `S.pending.shift()()` then called `undefined` and ended the section on a
 *    crash, which the corpus banked as 「the mutant was caught」. And the obvious repair is
 *    WORSE than the crash: awaiting a promise nobody can resolve stalls the whole gate, and a
 *    stalled gate reports nothing at all — measured, on the first attempt at this round.
 *    So: release what is actually pending, and only wait when there was something to release.
 * ⚠️ The rejection is RETURNED rather than thrown. Whether the late page took the screen down
 *    is a fact worth asserting by name (D2b), not a reason to stop reading the others.
 */
async function releaseAndAwait(S, promise) {
  const release = S.pending.shift();
  if (!release) {
    promise.catch(() => {});
    // Nothing went out, so there is nothing to wait for. `parked` above has already taken the
    //    hang back out of the queue — one author for that repair, not two.
    return { released: false, error: null };
  }
  release();
  try { await promise; return { released: true, error: null }; }
  catch (err) { return { released: true, error: err }; }
}
const enabled = (el) => (el ? el.disabled === false : '(NO ELEMENT)');
const hasClass = (el, cls) => (el ? el.classList.contains(cls) : '(NO ELEMENT)');

const items = (tl) => tl.children.filter(c => c.classList.contains('timeline-item'));
const mores = (tl) => tl.children.filter(c => c.classList.contains('timeline-more'));
const moreBtn = (tl) => { const m = mores(tl)[0]; return m ? m.children[0] : null; };

// ════════════════════════════════════════════════════════════════════════════════
// A — the envelope, read once, in one place
// ════════════════════════════════════════════════════════════════════════════════
async function sectionA() {
  const R = (await buildSandbox()).ctx.readHistoryPage;

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

  // 🔴 THE SHAPE IS ASKED, NOT ASSUMED, AND THIS IS THE CASE THAT CAN TELL.
  //    Every other body here carries a bool, where `!!body.truncated` and
  //    `saysTruncated(...) === true` agree - so the whole corpus passed with the field read
  //    as a bare truthy value, which is right on this route only because of what it sends
  //    TODAY. The walk route already answers with an axis object that arrives on EVERY
  //    response and is truthy even when nothing was cut; feeding that shape here is what
  //    separates "asked" from "assumed" and what makes the mutant in section G catchable.
  const axes = R({ logs: [log(1)], next_cursor: 'CUR9',
    truncated: { depth: false, nodes: false, edges: false, reason: null } });
  check('A5b an object that says nothing was cut is NOT truncated', axes.truncated, false);
  check('A5c ... and one that names a reason IS',
    R({ logs: [log(1)], next_cursor: 'CUR9',
      truncated: { nodes: true, reason: 'nodes' } }).truncated, true);

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
  let S = await buildSandbox();
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
  // 🔴 C-63. WHAT THE ENVELOPE DEFECT DOES IS ALREADY NAMED — by B2 two lines up: with the
  //    envelope assigned where the array belongs, `renderTimeline` paints NOTHING and B2 says
  //    so, by number. What was wrong is that B4b reached into the empty list first and died on
  //    `undefined.classList`, so the section ended before B2's verdict could be believed and a
  //    CRASH was banked as 「the mutant was caught」. A throw says the harness stopped, not that
  //    it noticed. So no assertion is added here — the dereference is removed.
  check('B4b ... and it is the LAST thing in the list',
    hasClass(S.timeline.children[S.timeline.children.length - 1], 'timeline-more'), true);

  // 🔴 THE LABEL CARRIES THE FACT, NOT ONLY THE OFFER. `더 보기` alone answers "is this the
  // whole history?" by implication, and by implication is how a capped list passes for a
  // complete one. `일부만` is this client's existing word for a server-truncated list.
  // 🔴 C-63. READ ONCE, AND TOTAL. `moreBtn` answers null when there is no control, and B4 above
  //    is the assertion that SAYS there is one — so these four describe the control's wording and
  //    state, and a missing control must make them fail rather than end the section on a
  //    dereference. Four separate `moreBtn(...)` calls also let the four disagree about which
  //    control they meant, which is the same defect one layer down.
  const more = moreBtn(S.timeline);
  check('B5 the control says the list is only part of the history', says(more, '일부만'), true);
  check('B5b ... and how much of it was paged in', says(more, '3건'), true);
  check('B5c ... and offers the page', says(more, '더 보기'), true);
  check('B6 the control is live', enabled(more), true);
  check('B7 the first request carries no cursor', urlAt(S, 0).includes('cursor='), false);
  check('B7b ... and is the ROW endpoint on the row tab',
    S.requests[0], `${API_BASE}/tables/t1/rows/ROW-A/history`);

  // -- complete page: no control at all --
  S = await buildSandbox();
  resetState();
  S.responses.push({ status: 200, body: page([log(1), log(2)], null) });
  await S.ctx.loadHistory();
  check('B8 a COMPLETE list carries no control', mores(S.timeline).length, 0);
  check('B8b ... and no cursor', state.cellRowHistoryCursor, null);
  check('B8c ... and its rows are all there', items(S.timeline).length, 2);

  // -- empty history --
  S = await buildSandbox();
  resetState();
  S.responses.push({ status: 200, body: page([], null) });
  await S.ctx.loadHistory();
  check('B9 an empty history renders no control', mores(S.timeline).length, 0);

  // -- the cell tab hits the cell endpoint --
  S = await buildSandbox();
  resetState();
  state.activeHistoryTab = 'cell';
  S.responses.push({ status: 200, body: page([log(1)], 'C') });
  await S.ctx.loadHistory();
  check('B10 the cell tab pages the CELL endpoint',
    S.requests[0], `${API_BASE}/tables/t1/rows/ROW-A/cells/COL-A/history`);

  // -- a bare array still renders (unpaged server) --
  S = await buildSandbox();
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
  const S = await buildSandbox();
  resetState();
  S.responses.push({ status: 200, body: page([log(1), log(2)], 'CUR1') });
  await S.ctx.loadHistory();

  S.responses.push({ status: 200, body: page([log(3), log(4)], 'CUR2') });
  const btn = moreBtn(S.timeline);
  await S.ctx.loadMoreHistory(btn);

  check('C1 the rows already on screen survive the page', items(S.timeline).length, 4);
  check('C1b ... in order, oldest page last',
    listIds(state.cellRowHistoryData), [1, 2, 3, 4]);
  check('C2 the appended rows land ABOVE the control',
    S.timeline.children.map(c => c.classList.contains('timeline-more')),
    [false, false, false, false, true]);
  check('C3 the request carries the cursor verbatim',
    S.requests[1], `${API_BASE}/tables/t1/rows/ROW-A/history?cursor=CUR1`);
  check('C4 the next cursor replaces the spent one', state.cellRowHistoryCursor, 'CUR2');
  check('C5 the paged count grows', state.cellRowHistoryLoaded, 4);
  check('C5b ... and the label says so', says(btn, '4건'), true);
  check('C6 the control is live again', enabled(btn), true);

  // The last page: nothing further to page toward, so the control goes and its absence is the
  // "this is now the whole history" statement.
  S.responses.push({ status: 200, body: page([log(5)], null) });
  await S.ctx.loadMoreHistory(moreBtn(S.timeline));
  check('C7 the final page removes the control', mores(S.timeline).length, 0);
  check('C7b ... and keeps every row', items(S.timeline).length, 5);
  check('C7c ... and clears the cursor', state.cellRowHistoryCursor, null);

  // A cursor is opaque: it is handed back byte for byte, never rebuilt.
  const S2 = await buildSandbox();
  resetState();
  const OPAQUE = 'MjAyNi0wOC0xMVQwNjozMzoyNi4yMDA1MzkrMDk6MDB8MjkyNDg1Nw';
  S2.responses.push({ status: 200, body: page([log(1)], OPAQUE) });
  await S2.ctx.loadHistory();
  S2.responses.push({ status: 200, body: page([log(2)], null) });
  await S2.ctx.loadMoreHistory(moreBtn(S2.timeline));
  check('C8 an opaque cursor round-trips untouched',
    urlAt(S2, 1).endsWith(`?cursor=${OPAQUE}`), true);

  // A second click while the first page is in flight must not issue a second request.
  const S3 = await buildSandbox();
  resetState();
  S3.responses.push({ status: 200, body: page([log(1)], 'C1') });
  await S3.ctx.loadHistory();
  S3.responses.push({ status: 200, body: page([log(2)], null), hang: true });
  const b3 = moreBtn(S3.timeline);
  const inflight = parked(S3, S3.ctx.loadMoreHistory(b3));
  check('C9 the control is disabled while its page is in flight', enabled(b3), false);
  check('C9b ... and says so', textOf(b3), '조회 중…');
  await S3.ctx.loadMoreHistory(b3);          // the double click
  check('C9c a second click issues no second request', S3.requests.length, 2);
  // 🔴 C-63. TOTAL, AND IT MUST NOT BE ABLE TO HANG. With the envelope defect there is no
  //    control to click, so no page was ever in flight and `pending` is empty — C9c above says
  //    that by number. Calling `undefined` ended the section on a crash; awaiting a promise that
  //    nobody can resolve would be worse still, because a STALLED gate reports nothing at all.
  await releaseAndAwait(S3, inflight);
  check('C9d the in-flight page still lands', items(S3.timeline).length, 2);
}

// ════════════════════════════════════════════════════════════════════════════════
// D — a fresh load resets paging. The named defect, driven.
// ════════════════════════════════════════════════════════════════════════════════
async function sectionD() {
  // -- the cursor is retired BEFORE the new request, not after it lands --
  let S = await buildSandbox();
  resetState();
  S.responses.push({ status: 200, body: page([log(1)], 'CUR-A') });
  await S.ctx.loadHistory();
  S.responses.push({ status: 200, body: page([log(9, 'ROW-B')], null), hang: true });
  state.selectedCell = { rowId: 'ROW-B', colId: 'COL-A', value: '', rowIndex: 1 };
  const load2 = parked(S, S.ctx.loadHistory());
  check('D1 the previous row\'s cursor is gone before the new page arrives',
    state.cellRowHistoryCursor, null);
  check('D1b ... and so is its truncation flag', state.cellRowHistoryTruncated, false);
  check('D1c ... and its paged count', state.cellRowHistoryLoaded, 0);
  await releaseAndAwait(S, load2);
  check('D1d the new row renders its own page', listIds(state.cellRowHistoryData, 'row_id'), ['ROW-B']);

  // -- THE DEFECT ITSELF: 더 보기 on row A, resolved after the operator clicked row B --
  S = await buildSandbox();
  resetState();
  S.responses.push({ status: 200, body: page([log(1), log(2)], 'CUR-A') });
  await S.ctx.loadHistory();
  const btnA = moreBtn(S.timeline);
  S.responses.push({ status: 200, body: page([log(3), log(4)], 'CUR-A2'), hang: true });
  const moreA = parked(S, S.ctx.loadMoreHistory(btnA));

  // ...the operator clicks another cell while page 2 is still out.
  state.selectedCell = { rowId: 'ROW-B', colId: 'COL-A', value: '', rowIndex: 1 };
  S.responses.push({ status: 200, body: page([log(9, 'ROW-B')], null) });
  await S.ctx.loadHistory();
  check('D2 row B shows its own single page', listIds(state.cellRowHistoryData), [9]);

  const late = await releaseAndAwait(S, moreA);
  // 🔴 C-63. THE LATE PAGE IS CAUGHT SO THE FACTS BELOW GET TO SPEAK. With the session check
  //    removed, row A's page 2 tries to splice itself into a list that was rebuilt for row B and
  //    the insert dies — in this stub AND in a real browser, which raises `NotFoundError` on the
  //    same call. So the stub is not being strict for its own sake and is not loosened. What
  //    changes is that the crash becomes a NAMED assertion instead of ending the section: 「the
  //    superseded page did not take the screen down」 is its own fact, and the three below it —
  //    which are what this section exists to say — now run whatever happened here.
  check('D2b the superseded page does not crash the list it landed on',
    late.error === null ? null : late.error.message, null);
  // 🔴 THE ROWS WOULD ALL BE REAL. That is what makes this defect invisible on screen: correctly
  // formatted audit entries, about a different row.
  check('D3 row A\'s page 2 is NOT appended to row B\'s list',
    listIds(state.cellRowHistoryData), [9]);
  check('D3b ... and nothing was added to the DOM either', items(S.timeline).length, 1);
  check('D3c ... and row A\'s cursor did not overwrite row B\'s', state.cellRowHistoryCursor, null);
  check('D3d ... and row B\'s paged count is its own', state.cellRowHistoryLoaded, 1);

  // -- a superseded FRESH load must not clobber the newer one either --
  S = await buildSandbox();
  resetState();
  S.responses.push({ status: 200, body: page([log(1)], null), hang: true });
  const slow = parked(S, S.ctx.loadHistory());
  state.selectedCell = { rowId: 'ROW-B', colId: 'COL-A', value: '', rowIndex: 1 };
  S.responses.push({ status: 200, body: page([log(9, 'ROW-B')], null) });
  await S.ctx.loadHistory();
  await releaseAndAwait(S, slow);
  check('D4 a superseded fresh load does not replace the newer list',
    listIds(state.cellRowHistoryData), [9]);

  // -- the BODY can arrive late too, and that is a separate window --
  // 🔴 THIS IS WHY THERE ARE TWO SESSION CHECKS AND NOT ONE. The first guards the fetch; by the
  //    time `res.json()` resolves the status line has long since arrived, so the first check has
  //    already passed and only a second one, after the body, can catch an operator who clicked
  //    away in between. Deleting the second check passes every other case in this file.
  S = await buildSandbox();
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
    listIds(state.cellRowHistoryData), [1]);
  check('D6b ... and did not touch the DOM', items(S.timeline).length, 1);
  resetState();

  // -- no selection: the session retires rather than leaving a cursor behind --
  S = await buildSandbox();
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
  let S = await buildSandbox();
  resetState();
  S.responses.push({ status: 200, body: page([log(1), log(2)], 'CUR1') });
  await S.ctx.loadHistory();
  S.responses.push({ throws: true });
  let btn = moreBtn(S.timeline);
  await S.ctx.loadMoreHistory(btn);

  check('E1 a failed page keeps every row already on screen', items(S.timeline).length, 2);
  check('E1b ... and the list behind them', state.cellRowHistoryData.length, 2);
  check('E2 the control is NOT left disabled', enabled(btn), true);
  check('E2b ... it offers the retry', says(btn, '재시도'), true);
  check('E2c ... and shows it failed', hasClass(btn, 'is-error'), true);
  check('E3 the cursor is untouched, so the retry has somewhere to go',
    state.cellRowHistoryCursor, 'CUR1');

  // the retry actually works
  S.responses.push({ status: 200, body: page([log(3)], null) });
  await S.ctx.loadMoreHistory(btn);
  check('E4 the retry lands', items(S.timeline).length, 3);
  check('E4b ... and re-asks the SAME cursor',
    S.requests[2], `${API_BASE}/tables/t1/rows/ROW-A/history?cursor=CUR1`);

  // -- a 5xx is a retry, not a lost position --
  S = await buildSandbox();
  resetState();
  S.responses.push({ status: 200, body: page([log(1)], 'CUR1') });
  await S.ctx.loadHistory();
  S.responses.push({ status: 500, body: {} });
  btn = moreBtn(S.timeline);
  await S.ctx.loadMoreHistory(btn);
  check('E5 a 500 is a retry', says(btn, '재시도'), true);
  check('E5b ... and keeps the position', state.cellRowHistoryCursor, 'CUR1');

  // -- 400: the POSITION is gone. Retrying the same token can only fail again. --
  S = await buildSandbox();
  resetState();
  S.responses.push({ status: 200, body: page([log(1), log(2)], 'BADCUR') });
  await S.ctx.loadHistory();
  S.responses.push({ status: 400, body: { detail: 'Invalid history cursor' } });
  btn = moreBtn(S.timeline);
  await S.ctx.loadMoreHistory(btn);

  check('E6 a 400 keeps the rows already on screen', items(S.timeline).length, 2);
  check('E6b the control does not offer the same cursor again',
    says(btn, '재시도'), false);
  check('E6c it offers a reload', says(btn, '새로고침'), true);
  check('E6d ... and says the position expired', says(btn, '위치 만료'), true);
  check('E6e ... and is still clickable', enabled(btn), true);

  // 🔴 CLICKING IT MUST START OVER, NOT RE-ASK. A control that loops on a dead cursor is the
  //    "looks clickable, does nothing" state wearing a label.
  S.responses.push({ status: 200, body: page([log(1)], null) });
  // Guarded: E6c/E6d/E6e above are the assertions that say the control is there and what it
  // offers. With no control there is nothing to click, E7 then finds no third request, and the
  // fact is reported by the assertion that describes it rather than by a dereference.
  if (btn) btn.click();
  await new Promise(r => setImmediate(r));
  check('E7 the reload asks page 1, with NO cursor',
    urlAt(S, 2), `${API_BASE}/tables/t1/rows/ROW-A/history`);
  check('E7b ... and the list is rebuilt from it', items(S.timeline).length, 1);

  // -- a failed FRESH load still reports, and leaves no control --
  S = await buildSandbox();
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
  const S = await buildSandbox();
  resetState();
  S.responses.push({ status: 200, body: page([log(2), log(1)], 'CUR1') });
  await S.ctx.loadHistory();

  // These two are the functions that break FIRST and LOUDEST if the envelope is assigned where
  // the array belongs — and they break on a live WebSocket update, i.e. not while anyone is
  // looking at the code.
  const live = log(99);
  // 🔴 C-63. THE SUBJECT ITSELF THROWS HERE UNDER THE ENVELOPE DEFECT — `.some is not a
  //    function` — and that IS the production symptom this section was written for: every live
  //    WebSocket update on the sidebar dies, on a screen that otherwise looks fine. It is a fact
  //    worth SAYING, so it is caught and named. Letting it end the section instead meant the
  //    corpus banked a crash as 「the mutant was caught」, and F1..F5 below — which are what this
  //    section exists to assert — never ran at all.
  let liveFailure = null;
  try { S.ctx.appendHistoryLocally(live); } catch (err) { liveFailure = err; }
  check('F0 a live update does not throw on the state a load left behind',
    liveFailure === null ? null : liveFailure.message, null);
  check('F1 appendHistoryLocally still unshifts into the list',
    listIds(state.cellRowHistoryData), [99, 2, 1]);
  check('F2 renderTimelineIncremental prepends it on screen', items(S.timeline).length, 3);
  checkFn('F2b ... at the TOP', 'the newest log heads the list',
    () => items(S.timeline)[0] === S.timeline.children[0], 'the first child IS the first item');
  check('F3 the 더 보기 control stays last',
    hasClass(S.timeline.children[S.timeline.children.length - 1], 'timeline-more'), true);

  // A duplicate must still be rejected — the de-dupe reads the array too, so it dies on the
  // same defect F0 names. Caught for the same reason: F4 below is the assertion with the words.
  try { S.ctx.appendHistoryLocally(live); } catch { /* named by F0 */ }
  check('F4 the de-dupe still works against the list',
    Array.isArray(state.cellRowHistoryData) ? state.cellRowHistoryData.length : 'NOT A LIST', 3);

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

// ════════════════════════════════════════════════════════════════════════════════
// J — the GLOBAL tab pages, through the pager the other tab already had
//
// 🔴 WHY THIS IS A SECTION AND NOT A LINE. Until 판정 473 the route published `next_cursor` and
//    accepted none, so this module stated 「일부만」 as a fact and REFUSED to draw a control that
//    could not move. The route takes a cursor now, and the temptation is a second pager: this
//    list renders differently (filtered client-side, redrawn whole), and a copy written for that
//    difference would start life without the three states the first one has — transport failed,
//    position expired, session moved on. Each of those cost a round to get right.
//
//    So the pager is ONE function reading a PANE DECLARATION, and this section drives the new
//    pane through the same states sections C and D drive the old one through. A cell left out of
//    that table reads as a pass, so none is.
//
// ⚠️ THE REFUSAL WAS NOT DELETED, IT NARROWED (J2). `truncated` without a usable cursor is still
//    a control with nowhere to go, and still draws as a fact — the rule A4 pins for the other tab.
// ════════════════════════════════════════════════════════════════════════════════
async function sectionJ() {
  // -- J1: a capped global list carries the control, and the control states the fact first --
  let S = await buildSandbox();
  resetState();
  state.activeHistoryTab = 'global';
  S.responses.push({ status: 200, body: recentPage(
    [group('TX-1', [log(1)]), group('TX-2', [log(2)])], 'GCUR1') });
  await S.ctx.loadHistory();
  const b1 = moreBtn(S.timeline);
  check('J1 a capped global list carries the pager', mores(S.timeline).length, 1);
  check('J1b ... and it states the fact before it offers the page',
    b1 ? b1.textContent : null, '일부만 (2건) · 더 보기');
  check('J1c ... and the position to resume from was kept', state.globalHistoryCursor, 'GCUR1');
  check('J1d ... and the paged count is its own number', state.globalHistoryLoaded, 2);

  // -- J2: truncated with NO cursor is a fact with nowhere to go, and draws as one --
  S = await buildSandbox();
  resetState();
  state.activeHistoryTab = 'global';
  S.responses.push({ status: 200, body: { ...recentPage([group('TX-1', [log(1)])]),
    truncated: true, next_cursor: null } });
  await S.ctx.loadHistory();
  check('J2 truncated with no cursor draws no control', mores(S.timeline).length, 0);
  check('J2b ... and says so as a fact instead',
    S.timeline.children.some(c => textOf(c) === '일부만 (1건)'), true);

  // -- J3: the page is FETCHED with the cursor and APPENDED, and the count follows --
  S = await buildSandbox();
  resetState();
  state.activeHistoryTab = 'global';
  S.responses.push({ status: 200, body: recentPage([group('TX-1', [log(1)])], 'GCUR1') });
  await S.ctx.loadHistory();
  S.responses.push({ status: 200, body: recentPage([group('TX-2', [log(2)])], 'GCUR2') });
  await S.ctx.loadMoreHistory(moreBtn(S.timeline), S.panes.global);
  check('J3 the page was asked for at the recent route, carrying the cursor',
    urlAt(S, 1), `${API_BASE}/audit_logs/recent?limit_groups=100&cursor=GCUR1`);
  check('J3b ... and the groups were APPENDED, not replaced',
    txIds(state.globalHistoryData), ['TX-1', 'TX-2']);
  check('J3c ... the panel shows both', items(S.timeline).length, 2);
  check('J3d ... the cursor advanced', state.globalHistoryCursor, 'GCUR2');
  check('J3e ... and the control counts what was paged in',
    (moreBtn(S.timeline) || {}).textContent, '일부만 (2건) · 더 보기');

  // -- J4: the last page takes the control away, because a complete list carries none --
  S.responses.push({ status: 200, body: recentPage([group('TX-3', [log(3)])]) });
  await S.ctx.loadMoreHistory(moreBtn(S.timeline), S.panes.global);
  check('J4 the last page removes the control', mores(S.timeline).length, 0);
  check('J4b ... and the rows it brought are still there',
    txIds(state.globalHistoryData), ['TX-1', 'TX-2', 'TX-3']);

  // -- J5: a 400 is a POSITION problem, so retrying the same token is the trap --
  S = await buildSandbox();
  resetState();
  state.activeHistoryTab = 'global';
  S.responses.push({ status: 200, body: recentPage([group('TX-1', [log(1)])], 'GCUR1') });
  await S.ctx.loadHistory();
  S.responses.push({ status: 400, body: { detail: 'bad cursor' } });
  await S.ctx.loadMoreHistory(moreBtn(S.timeline), S.panes.global);
  const b5 = moreBtn(S.timeline);
  check('J5 a 400 turns the pager into the one move that recovers',
    b5 ? [b5.textContent, b5.disabled, b5.dataset.mode] : null,
    ['위치 만료 · 새로고침', false, 'reload']);
  check('J5b ... and the rows already on screen are untouched',
    txIds(state.globalHistoryData), ['TX-1']);

  // -- J6: a transport failure says nothing about the position, so the cursor stays good --
  S = await buildSandbox();
  resetState();
  state.activeHistoryTab = 'global';
  S.responses.push({ status: 200, body: recentPage([group('TX-1', [log(1)])], 'GCUR1') });
  await S.ctx.loadHistory();
  S.responses.push({ throws: true });
  await S.ctx.loadMoreHistory(moreBtn(S.timeline), S.panes.global);
  const b6 = moreBtn(S.timeline);
  check('J6 a failed page offers a retry and stays live',
    b6 ? [b6.textContent, enabled(b6), b6.dataset.mode] : null,
    ['조회 실패 · 재시도', true, undefined]);
  check('J6b ... on the same cursor, which is still good', state.globalHistoryCursor, 'GCUR1');

  // -- J7: PAGE 2 OF A LIST THAT IS NO LONGER ON SCREEN. Those rows are real and they belong to
  //    a view the operator has already left; section D drives the same interleaving on the other
  //    tab, and this pane carries a session token for exactly this.
  S = await buildSandbox();
  resetState();
  state.activeHistoryTab = 'global';
  S.responses.push({ status: 200, body: recentPage([group('TX-1', [log(1)])], 'GCUR1') });
  await S.ctx.loadHistory();
  S.responses.push({ status: 200, body: recentPage([group('TX-OLD', [log(9)])], 'GCUR9'),
                    hang: true });
  const inFlight = parked(S,
    S.ctx.loadMoreHistory(moreBtn(S.timeline), S.panes.global));
  // ...the operator reloads the tab while that page is still out.
  S.responses.push({ status: 200, body: recentPage([group('TX-NEW', [log(5)])], 'GCUR5') });
  await S.ctx.loadHistory();
  await releaseAndAwait(S, inFlight);
  check('J7 a page from a replaced session is dropped',
    txIds(state.globalHistoryData), ['TX-NEW']);
  check('J7b ... and the live list keeps its own cursor', state.globalHistoryCursor, 'GCUR5');
  resetState();
}

async function sectionH() {
  let S = await buildSandbox();
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
  S = await buildSandbox();
  resetState();
  state.activeHistoryTab = 'global';
  S.responses.push({ status: 200, body: [group('TX-9', [log(9)])] });
  await S.ctx.loadHistory();
  check('H5 a bare array is still read, and still painted',
    [txIds(state.globalHistoryData), items(S.timeline).length], [['TX-9'], 1]);

  // -- an empty projection states itself --
  S = await buildSandbox();
  resetState();
  state.activeHistoryTab = 'global';
  S.responses.push({ status: 200, body: recentPage([]) });
  await S.ctx.loadHistory();
  check('H6 an empty projection says so',
    S.timeline.innerHTML.includes('No database history recorded'), true);
  checkFn('H6b ... and still leaves an Array behind', state.globalHistoryData,
    v => Array.isArray(v) && v.length === 0, 'an empty Array');

  // -- a body whose list is under some OTHER name is empty, never an object --
  S = await buildSandbox();
  resetState();
  state.activeHistoryTab = 'global';
  S.responses.push({ status: 200, body: { logs: [group('TX-X', [log(1)])], truncated: false, next_cursor: null } });
  await S.ctx.loadHistory();
  checkFn('H7 an unrecognised list name yields an Array, not a throw and not an object',
    state.globalHistoryData, v => Array.isArray(v) && v.length === 0, 'an empty Array');

  // -- and a genuinely failed load still reports as one --
  S = await buildSandbox();
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
  let S = await buildSandbox();
  resetState();
  state.activeHistoryTab = 'cell';
  S.responses.push({ status: 200, body: cellPage([], null, 0) });
  await S.ctx.loadHistory();
  let slot = emptySlot(S.timeline);
  check('I1 no history anywhere reads as 기록 없음', slot.text, '기록 없음');
  check('I1b ... and offers nowhere to go', slot.action === undefined || slot.action === null, true);
  check('I1c ... and is not a pager', mores(S.timeline).length, 0);

  // -- state 2: the records exist and THIS SCREEN cannot show them --
  S = await buildSandbox();
  resetState();
  state.activeHistoryTab = 'cell';
  S.responses.push({ status: 200, body: cellPage([], null, 225101) });
  await S.ctx.loadHistory();
  slot = emptySlot(S.timeline);
  check('I2 the two empty states are NOT the same text', slot.text === '기록 없음', false);
  check('I2b the cell is what is empty, and it says so', slot.note, '이 셀 기록 없음');
  checkFn('I2c the row-level count reaches the screen',
    textOf(slot.action),
    t => typeof t === 'string' && t.includes('225') && t.includes('101') && t.includes('건'),
    'a label carrying the 225101 count (grouped per locale) and 건');
  // 🔴 C-63. TOTAL, and I2c above is the assertion that NAMES the loss. Two mutants (the reader
  //    dropping the row-history count, and the two empty states collapsing into one) take the
  //    disclosure off the screen entirely; I2c is written to fail on that, but I2d used to
  //    dereference `slot.action` first and throw, so the run ended before the naming assertion
  //    could be believed — the verdict said 「caught」 about a harness that had crashed.
  check('I2d ... as the ROW history, named', says(slot.action, '행 이력'), true);
  check('I2e the count is stored beside the list, not on it',
    [state.cellRowHistoryRowTotal, state.cellRowHistoryData.row_history_total], [225101, undefined]);

  // The way out, in ONE action — and through the row tab's own button, so nothing here is a
  // second copy of the tab switch.
  let tabClicks = 0;
  S.tabRowBtn.addEventListener('click', () => { tabClicks++; });
  // 🔴 C-63. GUARDED, AND I3 IS STILL THE ASSERTION THAT SPEAKS. Two mutants take the disclosure
  //    off the screen (I2c above fails and names that); clicking `undefined` used to end the
  //    section here, and the crash was banked as 「caught」. With no disclosure there is no click,
  //    so `tabClicks` stays 0 and I3 fails — by name, saying which way out is gone.
  if (slot.action) slot.action.click();
  check('I3 one click on the disclosure reaches the Row History tab', tabClicks, 1);

  // -- the count is a FLOOR when the server says it is --
  S = await buildSandbox();
  resetState();
  state.activeHistoryTab = 'cell';
  S.responses.push({ status: 200, body: cellPage([], null, 1000, true) });
  await S.ctx.loadHistory();
  check('I4 a capped count is not presented as exact',
    says(emptySlot(S.timeline).action, '이상'), true);

  // -- and is NOT hedged when it is exact. A small count also pins the whole label with no
  //    locale grouping in the way.
  S = await buildSandbox();
  resetState();
  state.activeHistoryTab = 'cell';
  S.responses.push({ status: 200, body: cellPage([], null, 3) });
  await S.ctx.loadHistory();
  check('I5 an exact count states the number plainly',
    textOf(emptySlot(S.timeline).action), '행 이력 3건 보기');

  // -- the ROW tab never shows the disclosure: it IS the destination, and the server sends
  //    `row_history_total: null` there --
  S = await buildSandbox();
  resetState();
  state.activeHistoryTab = 'row';
  S.responses.push({ status: 200, body: page([], null) });
  await S.ctx.loadHistory();
  check('I6 the row tab does not point at itself', emptySlot(S.timeline).text, '기록 없음');

  // -- a count must not outlive the cell it described. Same sandbox, second cell: a disclosure
  //    reading "행 이력 12건" under a row that has none is confidently wrong, which is worse
  //    than the message that was missing. --
  S = await buildSandbox();
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
  S = await buildSandbox();
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
  //
  // Re-anchored again 2026-09-07: the field is no longer read as a bare truthy value. The wire
  // carries `truncated` in five shapes and this route's bool was right by luck, so the reader
  // now asks `saysTruncated` whether the answer SAYS it was cut. THE CLAIM THIS MUTANT MAKES IS
  // UNCHANGED — it removes `&& nextCursor`, and the corpus must still catch that — so this is
  // the same mutant re-spelled, NOT a weaker one. (A relaxed anchor would have been the quiet
  // way out and would have left the cursor rule unmeasured from here on.)
  { name: 'truncated no longer requires a cursor', defect: true,
    find: '    truncated: saysTruncated(body && body.truncated) === true && !!nextCursor,',
    repl: '    truncated: saysTruncated(body && body.truncated) === true,' },
  // 🔴 AND THE NEW HALF OF THE SAME LINE. Going back to the bare truthy read is a defect
  // the day this route answers with the axis object, and nothing else in this corpus would
  // notice — the bool it sends today makes both spellings agree.
  { name: 'the shape is assumed again instead of asked', defect: true,
    find: '    truncated: saysTruncated(body && body.truncated) === true && !!nextCursor,',
    repl: '    truncated: !!(body && body.truncated) && !!nextCursor,' },
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
    // Re-anchored 2026-09-17: the pager reads its session off the PANE, so both tabs are
    // guarded by this one line instead of one each.
    find: '  // The session moved on while this was in flight (another cell, another tab, a refresh). These\n'
        + '  // rows are real and they belong to a list that is no longer on screen.\n'
        + '  if (session !== pane.session()) return;',
    repl: '' },
  { name: 'a 400 becomes a retry on the same dead cursor', defect: true,
    find: '      markMoreLost(btn);',
    repl: '      markMoreFailed(btn);' },
  { name: 'a failed page leaves the control disabled', defect: true,
    find: "  btn.disabled = false;\n  btn.textContent = '조회 실패 · 재시도';",
    repl: "  btn.disabled = true;\n  btn.textContent = '조회 실패 · 재시도';" },
  { name: 'the control offers the page without stating the list is capped', defect: true,
    // Re-anchored 2026-09-17: the label is what the PANE declares, not what the function
    // types. Same claim, same words, one line up the file.
    find: '    label: () => `일부만 (${state.cellRowHistoryLoaded}건) · 더 보기`,',
    repl: '    label: () => `더 보기`,' },
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
    // Re-anchored 2026-09-06: the read was SPLIT so truncation could be taken from the body
    // rather than from `readHistoryPage`'s collapse (F-12). The mutant is unchanged -- it still
    // puts the envelope where the array belongs. This harness died loudly instead of scoring
    // nothing, which is the only reason the split was noticed.
    find: "      const body = await res.json();\n"
        + "      const page = readHistoryPage(body, 'groups');\n"
        + '      state.globalHistoryData = page.logs;',
    repl: '      state.globalHistoryData = await res.json();' },
  // Half-flipped: the envelope is opened, under the wrong list name. The panel then declares an
  // empty history over a full database, which is a wrong answer wearing an empty state.
  { name: 'the global read opens the wrong list of the envelope', defect: true,
    find: "readHistoryPage(body, 'groups')",
    repl: 'readHistoryPage(body)' },
  // ── the global pane, added 2026-09-17. Its states are section J; these are the defects
  //    that make each of them fail, so none of that section can pass by being unreachable.
  { name: 'the global control is drawn with no position to page from', defect: true,
    find: '    if (state.globalHistoryCursor) {',
    repl: '    if (true) {' },
  { name: 'the global page is requested without its cursor', defect: true,
    find: "    url: (cursor) => `${API_BASE}/audit_logs/recent?limit_groups=100`\n"
        + '      + `&cursor=${encodeURIComponent(cursor)}`,',
    repl: '    url: () => `${API_BASE}/audit_logs/recent?limit_groups=100`,' },
  { name: 'the global page replaces the list instead of appending', defect: true,
    find: '      page.logs.forEach(group => state.globalHistoryData.push(group));',
    repl: '      state.globalHistoryData = page.logs.slice();' },
  { name: 'a fresh global load does not open a new session', defect: true,
    find: '      state.globalHistorySession += 1;',
    repl: '      state.globalHistorySession += 0;' },
  { name: 'the global count is read off the array live updates grow', defect: true,
    find: '      state.globalHistoryLoaded = page.logs.length;',
    repl: '      state.globalHistoryLoaded = 0;' },

  // Controls: real edits that change nothing observable. If either of these "fails", the
  // sections above are keyed on something other than the behaviour they claim to score.
  { name: 'CONTROL: a comment is reworded', defect: false,
    find: '// [History paging] Fetch the next page and APPEND it. Never replaces what is on screen.',
    repl: '// [History paging] fetch and append.' },
  { name: 'CONTROL: a local is renamed', defect: false,
    find: '  const cursor = pane.cursor();',
    repl: '  const cursorToken = pane.cursor();\n  const cursor = cursorToken;' },
];

async function sectionG() {
  for (const m of MUTANTS) {
    // 🔴 THE MUTANT IS A WHOLE MODULE NOW, NOT A FRAGMENT. `applyOnce` still refuses an anchor
    //    that matches 0 or >1 times, and the probe refuses a `mutate` that changed nothing — so
    //    a mutant that stopped being applied EXITS, rather than scoring as caught. And a mutant
    //    that no longer parses fails at load, loudly, instead of looking like a catch.
    UNDER_TEST = m;
    const before = { pass, fail, names: failures.length };
    // A mutant run's assertion failures are expected — they ARE the catch — so they are not
    // printed. The flag replaces the old swap of `console.error`: this file no longer reaches
    // the global console at all, because the subject now writes to it too.
    quiet = true;
    let caught = false;
    let threw = null;
    try {
      await sectionA();
      await sectionB();
      await sectionC();
      await sectionD();
      await sectionE();
      await sectionF();
      await sectionH();
      await sectionI();
      await sectionJ();
    } catch (e) {
      // A mutant that throws while RUNNING (a DOM operation that cannot apply, a value that is
      // no longer the shape its reader expects) is caught as surely as one that fails an
      // assertion — the defect stopped the screen.
      // 🔴 BUT IT IS REPORTED SEPARATELY, because before C-58 the commonest throw was the SLICE
      //    failing to parse — the harness losing its subject, scored as a catch. That failure
      //    mode is gone (the probe loads a whole module and exits loudly if a mutation did not
      //    apply), and naming the remaining throws is how it stays gone.
      caught = true;
      threw = e;
    } finally {
      quiet = false;
      UNDER_TEST = null;
    }
    caught = caught || fail > before.fail;
    // The mutant run's own scores are not evidence about the product — the only thing carried
    // out of it is the VERDICT below. Roll the counters AND the failure names back.
    pass = before.pass; fail = before.fail; failures.length = before.names;
    check(`G/${m.defect ? 'defect' : 'control'}: ${m.name}`, caught, m.defect);
    if (threw) OUT.log(`  ⚠️ THROWN, not asserted — ${m.name}: ${threw.message}`);
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
await sectionJ();
const beforeG = { pass, fail };
await sectionG();

resetState();
const ran = pass + fail;
if (fail > 0) {
  OUT.error(`\n  ${fail} failing assertion(s):`);
  failures.forEach(n => OUT.error(`  ✗ ${n}`));
} else {
  OUT.log(`✓ history paging: ${beforeG.pass} behaviour assertions + ${MUTANTS.length} mutation verdicts`);
}
OUT.log(`ASSERTIONS ${ran} ${fail}`);
