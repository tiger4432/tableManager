// Harness — NOTHING IN STARTUP CAN LEAVE THE PAGE WITHOUT A WEBSOCKET.
// Run: node client2/tests/startup_socket_gate_harness.mjs   (no node_modules — vm sandbox)
//
// WHAT WAS ACTUALLY WRONG (user report 2026-08-04: "웹소켓이 안 붙는다", and the Network tab
// showed NO /ws request at all — not a failed one, none). `init()` in main.js ended:
//
//     await checkServerHealth();
//     await loadTables();
//     initWebSocket();          // <- last statement
//
// The entire reconnect ladder lives INSIDE `initWebSocket`, so anything that stopped `init()`
// short of that line cost the page its live channel for the whole session AND every retry that
// would have recovered it. `init()` was called bare (`init();`), so the rejection was unhandled
// and named nothing.
//
// THREE WAYS IT REPRODUCED, and the middle one is the interesting one:
//   1. `fetch` REJECTS with every DOM handle present  -> socket still opened. Both callees do
//      catch. This path was NOT the defect, and a harness that only tested it would have
//      declared the code fine.
//   2. THE CATCH BLOCK ITSELF THROWS. Both catches wrote DOM handles unguarded
//      (`elements.performanceLog.textContent`, `elements.tableSelect.innerHTML`). A null handle
//      turns a HANDLED outage into an UNHANDLED rejection at the exact moment the code was
//      being careful. Measured precedent in this repo: two `elements` getters named ids that
//      had never existed in index.html at any point in git history.
//   3. `fetch` NEVER SETTLES (hung backend, or the corporate proxy this project has already
//      been bitten by). `await` on a forever-pending promise does not reject, does not throw,
//      and logs NOTHING — which matches the reported symptom exactly: no /ws, no console error.
//
// WHY THIS HARNESS EXECUTES RATHER THAN READS. "The socket is not gated on unrelated work" is a
// statement about REACHABILITY UNDER FAILURE, and reachability is invisible to a source-shape
// assertion — `initWebSocket()` at the top and at the bottom of a function are the same shape.
// So the real `init` (main.js), the real `checkServerHealth`/`loadTables` (api.js) and the real
// `initWebSocket`/`scheduleReconnect`/`wakeNow` (websocket.js) are sliced out and driven against
// a fake socket and a fake `fetch` on a virtual clock. The scored quantity is a literal
// `new WebSocket('ws://…/ws')` — the same event whose absence the user read in the Network tab.
// Nothing here re-implements the code under test; re-implementing it would score this file
// against itself.
//
// MUTATION DISCIPLINE. Every `find` string is required to occur EXACTLY ONCE in its file;
// `applyOnce` fails on 0 or >1 matches rather than proceeding, and the mutated text is re-read
// to confirm the mutation is present and the original gone before anything is scored. This
// directory has twice had a mutation land on its first match inside a COMMENT and silently
// score a different function.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = (f) => join(HERE, '..', 'src', f);
const MAIN0 = readFileSync(SRC('main.js'), 'utf8').replace(/\r\n/g, '\n');
const API0 = readFileSync(SRC('api.js'), 'utf8').replace(/\r\n/g, '\n');
const WS0 = readFileSync(SRC('websocket.js'), 'utf8').replace(/\r\n/g, '\n');
const CFG0 = readFileSync(SRC('config.js'), 'utf8').replace(/\r\n/g, '\n');

function die(msg) {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  console.log('ASSERTIONS 0 1');
  process.exit(2);
}

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
// in comments, which is how a sibling harness spent a round scoring the wrong function.
function fn(src, name, where) {
  const m = new RegExp(`(?:export\\s+)?(?:async\\s+)?function\\s+${name}\\s*\\(`).exec(src);
  if (!m) die(`function ${name} not found in ${where} — renamed or reshaped.`);
  const body = sliceBalanced(src, m.index, '{', '}');
  if (!body) die(`unbalanced braces for ${name} in ${where}`);
  return body.replace(/^export\s+/, '');
}
function cfgNumber(src, name) {
  const m = new RegExp(`export\\s+const\\s+${name}\\s*=\\s*([0-9.]+)\\s*;`).exec(src);
  if (!m) die(`\`export const ${name}\` not found in config.js — renamed, moved, or no longer a literal.`);
  return Number(m[1]);
}
// The de-dupe latch is module state, not a function, so it is carried across by DECLARATION and
// its presence is required: if the binding disappears the slice would silently run against an
// undeclared global and the latch assertions would score nothing.
function latchDecl(src) {
  const m = /^let\s+tablesLoadInFlight\s*=\s*null\s*;$/m.exec(src);
  if (!m) die('`let tablesLoadInFlight = null;` not found in api.js — the loadTables de-dupe latch '
            + 'is gone or reshaped. Its assertions below would score nothing.');
  return m[0];
}

// ── Scoring ─────────────────────────────────────────────────────────────────────
let pass = 0, fail = 0, quiet = false;
const failures = [];
function check(name, actual, expected) {
  const a = JSON.stringify(actual), e = JSON.stringify(expected);
  if (a === e) { pass++; return true; }
  fail++; failures.push(name);
  if (!quiet) console.error(`  FAIL ${name}\n       expected ${e}\n       actual   ${a}`);
  return false;
}
function checkFn(name, actual, pred, describe) {
  if (pred(actual)) { pass++; return true; }
  fail++; failures.push(name);
  if (!quiet) console.error(`  FAIL ${name}\n       expected ${describe}\n       actual   ${JSON.stringify(actual)}`);
  return false;
}

// ── The driver ──────────────────────────────────────────────────────────────────
const OPEN_MS = 5;    // measured localhost WS handshake: median 2.54ms, max 4.15ms (rounded up)
const FAIL_MS = 3;    // measured ECONNREFUSED: median 0.49ms, max 2.71ms (rounded up)
const REST_MS = 20;   // a REST round trip, deliberately SLOWER than the handshake so `onopen`
                      // lands while `init()`'s own `loadTables()` is still in flight — that
                      // overlap is the ordering hazard the latch exists for, and a fixture
                      // where the socket opened last would never exercise it.

/**
 * `restMode` decides what `fetch` does. The DOM handles listed in `missing` resolve to null,
 * which is the mechanism behind reproduction #2 above.
 */
async function drive(mainSrc, apiSrc, wsSrc, cfgSrc, {
  restMode = 'ok', missing = [], serverUp = true, horizonMs = 400000, extraLoads = 0,
} = {}) {
  let now = 0, seq = 0;
  const timers = [];
  const rawSchedule = (f, ms) => { const id = ++seq; timers.push({ at: now + (ms || 0), seq: id, fn: f }); return id; };
  const clearFake = id => { const i = timers.findIndex(t => t.seq === id); if (i >= 0) timers.splice(i, 1); };

  const wsAttempts = [];       // every `new WebSocket(url)` — THE quantity the user could not see
  const errors = [];           // console.error text — "do not silence real errors"
  const restCalls = [];
  // `onopen` IS ASYNC AND ITS REJECTION IS NOBODY'S. The browser drops it as an unhandled
  // rejection; here it must be captured rather than allowed to kill the harness process, or the
  // very mutation that reintroduces a throwing catch takes the scorer down before it can score
  // it. It is RECORDED, not discarded — the socket's own bootstrap
  // (`checkServerHealth` + `loadTables`) failing is a real defect and is asserted on below.
  const onopenRejections = [];
  let switchTableCalls = 0, fetchDataCalls = 0, restSettled = 0;

  const callHandler = (h, arg) => {
    if (!h) return;
    let out;
    try { out = h(arg); } catch (e) { onopenRejections.push(e); return; }
    if (out && typeof out.catch === 'function') out.catch(e => onopenRejections.push(e));
  };

  class FakeWebSocket {
    constructor(url) {
      this.url = url; this.readyState = 0; this._dead = false;
      wsAttempts.push({ t: now, url });
      if (serverUp) {
        rawSchedule(() => {
          if (this._dead) return;
          this.readyState = 1;
          callHandler(this.onopen);
        }, OPEN_MS);
      } else {
        rawSchedule(() => {
          if (this._dead) return;
          this.readyState = 3;
          callHandler(this.onerror, new Error('ECONNREFUSED'));
          callHandler(this.onclose);
        }, FAIL_MS);
      }
    }
    close() { this._dead = true; this.readyState = 3; }
  }

  const noop = () => {};
  const mkEl = () => ({
    textContent: '', className: '', innerHTML: '', value: '', checked: false, style: {},
    appendChild(o) { this.value = this.value || o.value; },
    classList: { add: noop, remove: noop },
  });
  const cache = {};
  const elements = new Proxy({}, { get(_, k) {
    if (typeof k !== 'string') return undefined;
    if (missing.includes(k)) return null;          // the getter resolves to null — see #2
    return cache[k] || (cache[k] = mkEl());
  } });

  const fetchFake = (url) => new Promise((resolve, reject) => {
    restCalls.push({ t: now, url });
    if (restMode === 'hang') return;                                    // never settles, ever
    rawSchedule(() => {
      restSettled++;
      if (restMode === 'reject') return reject(new TypeError('Failed to fetch'));
      if (restMode === 'http500') return resolve({ ok: false, status: 500, json: async () => ({}) });
      if (restMode === 'badjson') return resolve({ ok: true, status: 200, json: async () => { throw new SyntaxError('Unexpected token <'); } });
      resolve({ ok: true, status: 200, json: async () => ({ tables: ['bonding_map', 'dt_log'] }) });
    }, REST_MS);
  });

  const sandbox = {
    WebSocket: FakeWebSocket,
    WS_URL: 'ws://127.0.0.1:8080/ws',
    WS_RECONNECT_BASE_MS: cfgNumber(cfgSrc, 'WS_RECONNECT_BASE_MS'),
    WS_RECONNECT_CEILING_MS: cfgNumber(cfgSrc, 'WS_RECONNECT_CEILING_MS'),
    WS_RECONNECT_JITTER: cfgNumber(cfgSrc, 'WS_RECONNECT_JITTER'),
    WS_HEALTHY_SESSION_MS: cfgNumber(cfgSrc, 'WS_HEALTHY_SESSION_MS'),
    WS_WAKE_MIN_GAP_MS: cfgNumber(cfgSrc, 'WS_WAKE_MIN_GAP_MS'),
    WS_CONNECT_TIMEOUT_MS: cfgNumber(cfgSrc, 'WS_CONNECT_TIMEOUT_MS'),
    WS_CONNECT_STALE_MS: cfgNumber(cfgSrc, 'WS_CONNECT_STALE_MS'),
    API_BASE: 'http://127.0.0.1:8080',
    CURRENT_USER: 'tester',
    state: {
      ws: null, wsRetryTimer: null, wsOpenedAt: 0, wsLastWakeAt: 0, wsWakeSignalsInstalled: false,
      wsReconnectDelay: cfgNumber(cfgSrc, 'WS_RECONNECT_BASE_MS'),
      wsPrevReconnectDelay: cfgNumber(cfgSrc, 'WS_RECONNECT_BASE_MS'),
      // The connect watchdog's state. This harness's fake socket always resolves, so the
      // watchdog never trips here — the hang it exists for is scored in
      // `ws_connect_watchdog_harness.mjs`. These are present because the sliced code reads them.
      wsConnectWatchdog: null, wsConnectingSince: 0, wsWatchdogTrips: 0,
      currentTable: '', pendingTxEdits: {}, pageCache: new Map(), gridApi: null,
    },
    elements,
    localStorage: { getItem: () => null, setItem: noop },
    document: {
      createElement: () => mkEl(),
      getElementById: () => null,
      querySelector: () => ({ classList: { add: noop, remove: noop } }),
      addEventListener: noop,
      get visibilityState() { return 'visible'; },
    },
    window: { addEventListener: noop, location: { search: '', pathname: '/', origin: 'http://localhost' } },
    console: { log: noop, warn: noop, error: (...a) => errors.push(a.map(String).join(' ')) },
    fetch: fetchFake,
    setTimeout: rawSchedule, clearTimeout: clearFake,
    Date: { now: () => now },
    Math: Object.assign(Object.create(Math), { random: () => 0 }),
    JSON, Set, Map, Object, Array, Number, String, Boolean, Promise, Error, TypeError, SyntaxError,
    // Collaborators OUTSIDE the question being scored. `switchTable` is counted rather than
    // sliced because the damage a duplicate bootstrap does is measured at its door: two
    // `switchTable` runs mean two schema loads and two grid teardowns.
    switchTable: async (t) => { switchTableCalls++; sandbox.state.currentTable = t; },
    fetchData: () => { fetchDataCalls++; },
    initTheme: noop, startSession: noop, installGlobalListeners: noop, installNavLinkCounting: noop,
    ROUTES: { GRID: 'grid' }, setupEventListeners: noop, initTraceEntry: noop,
    setupClipboardHandlers: noop, registerSmartPasteHandler: noop, smartPasteFromPasteEvent: noop,
    setupDragAndDrop: noop, clearRangeSelection: noop, updateSelectedCellUI: noop,
    updateTxModeUI: noop, renderGrid: noop, refreshTraceEntry: noop,
    // `init` installs the reference panel's keyboard isolation (main.js). Outside the question
    // scored here, but its absence made every `init` slice die with a ReferenceError.
    installReferenceKeyboardIsolation: noop,
    // `init` installs the 2c audit filters too. A missing stub here does not fail quietly:
    // the ReferenceError rejects `init` and takes the socket gate's whole section C red,
    // which is the harness doing its job.
    installAuditFilters: noop,
    // And it now stands up the grid's two assembled parts (the ledger-source label and the
    // re-translate menu, main.js). Same story as the two above: outside the question scored
    // here, and their absence rejected `init` with a ReferenceError in all 26 scenarios of
    // section C -- which is how this line came to be written. They return null so the
    // `if (sourceLabel)` / `if (rescopeMenu)` calls after the awaits stay out of the way.
    initGridSourceLabel: () => null,
    // The re-translate moved to the header banner, so the name `init()` calls moved with it --
    // and the banner needs to hear about selection, which is a third call from the same line.
    initRedoBanner: () => null,
    registerSelectionListener: noop,
    resetSuggestLearning: noop, loadSchema: async () => {}, loadHistory: async () => {},
    showIngestionProgress: noop, finishIngestionProgress: noop, showToast: noop,
    getLocalTimeString: () => '', updatePageCacheOnUpsert: noop, updatePageCacheOnDelete: noop,
    triggerHistoryReloadDebounced: noop, appendHistoryLocally: noop,
    updateGridSortState: noop, updateLoadedCount: noop, updatePaginationUI: noop,
  };
  vm.createContext(sandbox);

  try {
    vm.runInContext([
      latchDecl(apiSrc),
      fn(apiSrc, 'setBadge', 'api.js'),
      fn(apiSrc, 'checkServerHealth', 'api.js'),
      fn(apiSrc, 'loadTablesOnce', 'api.js'),
      fn(apiSrc, 'loadTables', 'api.js'),
      fn(wsSrc, 'scheduleReconnect', 'websocket.js'),
      fn(wsSrc, 'clearConnectWatchdog', 'websocket.js'),
      fn(wsSrc, 'abandonConnectingSocket', 'websocket.js'),
      fn(wsSrc, 'armConnectWatchdog', 'websocket.js'),
      fn(wsSrc, 'wakeNow', 'websocket.js'),
      fn(wsSrc, 'installWakeSignals', 'websocket.js'),
      fn(wsSrc, 'initWebSocket', 'websocket.js'),
      fn(mainSrc, 'init', 'main.js'),
      'globalThis.__init = init; globalThis.__loadTables = loadTables;',
    ].join('\n\n'), sandbox);
  } catch (e) {
    die(`the sliced startup code does not evaluate: ${e && e.message}`);
  }

  const flush = () => new Promise(r => setImmediate(r));

  // `init()` IS NOT AWAITED. Awaiting it would hang the harness on the very scenario that
  // matters most (`restMode: 'hang'`) and, worse, would make the socket look reachable only
  // because the harness waited for something the browser never waits for.
  let settled = 'pending', rejection = null;
  sandbox.__init().then(() => { settled = 'fulfilled'; },
                          e => { settled = 'rejected'; rejection = e; });
  await flush();

  let guard = 0;
  while (guard++ < 200000) {
    if (timers.length === 0) break;
    const next = Math.min(...timers.map(t => t.at));
    if (next > horizonMs) break;                    // the horizon is a wall, not a loop condition
    timers.sort((a, b) => a.at - b.at || a.seq - b.seq);
    const t = timers.shift();
    now = t.at;
    t.fn();
    await flush();
  }

  // Sequential extra loads exist to prove the latch RELEASES. A latch that never clears looks
  // identical to a correct one in the concurrent case.
  for (let i = 0; i < extraLoads; i++) {
    sandbox.__loadTables();
    let g2 = 0;
    while (timers.length && g2++ < 10000) {
      timers.sort((a, b) => a.at - b.at || a.seq - b.seq);
      const t = timers.shift();
      if (t.at > horizonMs) break;
      now = t.at; t.fn(); await flush();
    }
    await flush();
  }

  return {
    wsAttempts, errors, restCalls, restSettled, switchTableCalls, fetchDataCalls, settled, rejection,
    onopenRejections: onopenRejections.map(e => (e && e.message) || String(e)),
    wsAttemptCount: wsAttempts.length,
    firstWsAttemptAt: wsAttempts.length ? wsAttempts[0].t : null,
    wsUrls: [...new Set(wsAttempts.map(a => a.url))],
    serverBadge: cache.serverStatus ? cache.serverStatus.textContent : null,
    tablePicker: cache.tableSelect ? cache.tableSelect.value : null,
  };
}

// ── The checks ──────────────────────────────────────────────────────────────────
async function runChecks(mainSrc, apiSrc, wsSrc, cfgSrc, { strict = true } = {}) {
  const r = {};

  // ── A. THE FLOOR: A SOCKET IS ATTEMPTED, WHATEVER STARTUP DOES ───────────────
  //   Every one of these is a way `init()` can fail to reach its own last statement. The
  //   scored quantity is a literal `new WebSocket(...)` — the request the Network tab showed
  //   none of.
  {
    const SCENARIOS = [
      ['healthy',                    { restMode: 'ok' }],
      ['REST rejects',               { restMode: 'reject' }],
      ['REST answers 500',           { restMode: 'http500' }],
      ['REST body is not JSON',      { restMode: 'badjson' }],
      // #2 — the catch block itself throws. THE PATH MOST LIKELY TO BE MISSED, and the one a
      // plain-rejection test cannot reach: with every handle present, `restMode:'reject'`
      // above is fully handled and the socket opens even on the OLD code.
      ['catch throws: #performance-log absent', { restMode: 'reject', missing: ['performanceLog'] }],
      ['catch throws: #server-status absent',   { restMode: 'reject', missing: ['serverStatus'] }],
      ['catch throws: #table-select absent',    { restMode: 'badjson', missing: ['tableSelect'] }],
      ['catch throws: both badges absent',      { restMode: 'reject', missing: ['performanceLog', 'serverStatus'] }],
      // #3 — never settles. No rejection, no log, nothing to see.
      ['REST never settles (hung backend/proxy)', { restMode: 'hang' }],
    ];
    r.scenarios = {};
    for (const [label, opts] of SCENARIOS) {
      const run = await drive(mainSrc, apiSrc, wsSrc, cfgSrc, opts);
      r.scenarios[label] = { ws: run.wsAttemptCount, settled: run.settled, errs: run.errors.length };
      if (strict) {
        checkFn(`A: a socket is attempted — ${label}`, run.wsAttemptCount, v => v >= 1, '>= 1 `new WebSocket(...)`');
        check(`A: the socket targets the /ws endpoint — ${label}`, run.wsUrls, ['ws://127.0.0.1:8080/ws']);
      }
    }
  }

  // ── B. INDEPENDENCE, NOT LUCK OF ORDERING ────────────────────────────────────
  //   "A socket eventually appeared" is not the property. The property is that the socket does
  //   not WAIT on REST work: it must be attempted before the first REST call has even settled.
  {
    const hung = await drive(mainSrc, apiSrc, wsSrc, cfgSrc, { restMode: 'hang' });
    r.hungWsAt = hung.firstWsAttemptAt;
    r.hungRestSettled = hung.restSettled;
    const okRun = await drive(mainSrc, apiSrc, wsSrc, cfgSrc, { restMode: 'ok' });
    r.okWsAt = okRun.firstWsAttemptAt;

    if (strict) {
      check('B: with REST hung forever, the socket was still attempted', hung.wsAttemptCount >= 1, true);
      check('B: ...and it happened with ZERO REST calls settled', hung.restSettled, 0);
      check('B: ...and `init` is indeed still pending (the fixture really is stuck)', hung.settled, 'pending');
      checkFn('B: on a healthy start the socket is attempted before the first REST round trip returns',
        okRun.firstWsAttemptAt, v => v !== null && v < REST_MS, `< ${REST_MS}ms (the REST latency)`);
    }
  }

  // ── C. A CATCH BLOCK MUST NOT BE ABLE TO THROW ───────────────────────────────
  //   Scored directly on the two functions rather than only through `init`, so the property is
  //   pinned where it lives. Every subset of the handles their catches touch.
  {
    const HANDLE_SETS = [
      [], ['serverStatus'], ['performanceLog'], ['tableSelect'],
      ['serverStatus', 'performanceLog'], ['serverStatus', 'tableSelect'],
      ['performanceLog', 'tableSelect'], ['serverStatus', 'performanceLog', 'tableSelect'],
    ];
    r.catchSafe = true;
    for (const missing of HANDLE_SETS) {
      for (const restMode of ['reject', 'http500', 'badjson']) {
        const run = await drive(mainSrc, apiSrc, wsSrc, cfgSrc, { restMode, missing });
        const label = `[${missing.join(',') || 'all present'}] / ${restMode}`;
        if (run.settled === 'rejected') r.catchSafe = false;
        if (strict) {
          checkFn(`C: startup does not reject — ${label}`,
            run.settled, v => v !== 'rejected',
            `not "rejected" (got ${run.rejection && run.rejection.message})`);
          checkFn(`C: the failure is still REPORTED, not swallowed — ${label}`,
            run.errors.length, v => v >= 1, '>= 1 console.error');
          // The SOCKET's bootstrap runs the same two functions. A catch that throws breaks the
          // reconnect path too, silently — `onopen`'s rejection belongs to nobody.
          check(`C: the socket's own onopen bootstrap does not reject either — ${label}`,
            run.onopenRejections, []);
        }
      }
    }
  }

  // ── D. THE ORDERING THE MOVE COULD HAVE BROKEN ───────────────────────────────
  //   `onopen` bootstraps the table list when it finds the picker empty. With the socket now
  //   started first, that fires WHILE `init()`'s own `loadTables()` is in flight. Two concurrent
  //   bootstraps would mean two `switchTable` runs — two schema loads, two grid rebuilds.
  {
    const run = await drive(mainSrc, apiSrc, wsSrc, cfgSrc, { restMode: 'ok' });
    r.switchTableCalls = run.switchTableCalls;
    r.tablePicker = run.tablePicker;
    r.serverBadge = run.serverBadge;

    if (strict) {
      check('D: the overlapping bootstraps collapse into ONE switchTable', run.switchTableCalls, 1);
      check('D: ...and the table list actually got loaded (the run is not vacuous)', run.tablePicker, 'bonding_map');
      check('D: a healthy start reports the API online', run.serverBadge, 'API: ONLINE');
      checkFn('D: the socket connected exactly once on a healthy start',
        run.wsAttemptCount, v => v === 1, 'exactly 1 attempt');
    }

    const offline = await drive(mainSrc, apiSrc, wsSrc, cfgSrc, { restMode: 'reject', serverUp: false, horizonMs: 60000 });
    r.offlineBadge = offline.serverBadge;
    if (strict) {
      check('D: a failed start reports the API offline', offline.serverBadge, 'API: OFFLINE');
    }
  }

  // ── E. THE LATCH RELEASES ────────────────────────────────────────────────────
  //   A latch that is never cleared is indistinguishable from a correct one in the concurrent
  //   case, and it would freeze the table list for the rest of the session — including the
  //   reconnect bootstrap this whole round exists to protect.
  {
    const run = await drive(mainSrc, apiSrc, wsSrc, cfgSrc, { restMode: 'ok', extraLoads: 2 });
    r.loadsAfterExtra = run.switchTableCalls;
    if (strict) {
      check('E: two later sequential loadTables() calls each run (the latch clears)', run.switchTableCalls, 3);
    }
  }

  // ── F. THE RECONNECT LADDER THAT JUST LANDED STILL WORKS ─────────────────────
  //   Starting the socket earlier must not cost the retry behaviour. A refused socket has to
  //   keep retrying on a rising interval, from inside the new call site.
  {
    const run = await drive(mainSrc, apiSrc, wsSrc, cfgSrc, { restMode: 'reject', serverUp: false, horizonMs: 120000 });
    const gaps = [];
    for (let i = 1; i < run.wsAttempts.length; i++) gaps.push(run.wsAttempts[i].t - run.wsAttempts[i - 1].t);
    r.retryAttempts = run.wsAttempts.length;
    r.retryGaps = gaps.slice(0, 5);
    r.ladderRises = gaps.slice(0, 3).every((g, i) => i === 0 || g >= gaps[i - 1]);
    const CEIL = cfgNumber(cfgSrc, 'WS_RECONNECT_CEILING_MS');
    r.maxGap = gaps.length ? Math.max(...gaps) : 0;

    if (strict) {
      checkFn('F: a refused socket keeps retrying from the new call site',
        run.wsAttempts.length, v => v >= 10, '>= 10 attempts within the horizon');
      check('F: the retry interval rises — this is still a backoff', r.ladderRises, true);
      checkFn('F: and it never exceeds the declared ceiling',
        r.maxGap, v => v <= CEIL + FAIL_MS, `<= ${CEIL + FAIL_MS}ms`);
    }
  }

  return r;
}

// ── Baseline ────────────────────────────────────────────────────────────────────
console.log('=== BASELINE (the code as it stands) ===');
const base = await runChecks(MAIN0, API0, WS0, CFG0, { strict: true });
console.log(`  socket attempted in every startup scenario : ${
  Object.entries(base.scenarios).map(([k, v]) => `${k}=${v.ws}`).join(', ')}`);
console.log(`  hung-REST run: first /ws at t=${base.hungWsAt}ms with ${base.hungRestSettled} REST calls settled`);
console.log(`  healthy run: switchTable x${base.switchTableCalls}, picker="${base.tablePicker}", badge="${base.serverBadge}"`);
console.log(`  refused socket: ${base.retryAttempts} attempts, first gaps ${JSON.stringify(base.retryGaps)}`);

// ── Mutations ───────────────────────────────────────────────────────────────────
function countOf(src, needle) {
  let n = 0, i = 0;
  for (;;) { const j = src.indexOf(needle, i); if (j < 0) break; n++; i = j + 1; }
  return n;
}
function applyOnce(src, find, repl) {
  const n = countOf(src, find);
  if (n === 0) return { ok: false, why: `anchor not found: ${JSON.stringify(find.slice(0, 90))}` };
  if (n !== 1) return { ok: false, why: `anchor occurs ${n}x, must be unique: ${JSON.stringify(find.slice(0, 90))}` };
  return { ok: true, src: src.replace(find, repl) };
}

// Every mutation is a LIST OF SITES, possibly spanning files. Two of the defects this round
// removes are independent, and modelling either one alone understates the other: with the
// catches hardened, moving the socket back to the end of `init()` is survivable on the
// catch-throws scenarios (they no longer throw), and with the socket started first, a throwing
// catch no longer costs the socket. M9 is the combination — the code as it actually shipped —
// and it is the one that reproduces the LIVE symptom on the catch-throws path.
const SITE_SOCKET_LAST = [
  { file: 'main',
    find: '  initWebSocket();\n\n  // Load cached settings from localStorage',
    repl: '  // Load cached settings from localStorage' },
  { file: 'main',
    // The tail of `init()` is what this site anchors on, and it has moved once already
    // (two setRelation calls landed after the awaits). If it moves again this site goes
    // INERT and says so out loud, which is the whole point of anchoring on the code.
    find: '    redoBanner.setBusinessKey(state.currentBusinessKey);\n  }\n}',
    repl: '    redoBanner.setBusinessKey(state.currentBusinessKey);\n  }\n  initWebSocket();\n}' },
];
const SITE_HEALTH_CATCH_UNGUARDED = {
  file: 'api',
  find: "    setBadge(elements.serverStatus, 'API: OFFLINE', 'status-badge offline');\n"
      + "    setBadge(elements.performanceLog, 'Error connecting to database server');",
  repl: "    elements.serverStatus.textContent = 'API: OFFLINE';\n"
      + "    elements.serverStatus.className = 'status-badge offline';\n"
      + "    elements.performanceLog.textContent = 'Error connecting to database server';",
};

const MUTATIONS = [
  { name: 'M1 socket moved back to the LAST statement of init() (half of the original defect)',
    sites: SITE_SOCKET_LAST },

  { name: 'M2 checkServerHealth\'s catch writes its badges unguarded (catch can throw again)',
    sites: [SITE_HEALTH_CATCH_UNGUARDED] },

  { name: 'M3 loadTables\'s catch writes #table-select unguarded (catch can throw again)',
    sites: [{ file: 'api',
      find: '    if (elements.tableSelect) elements.tableSelect.innerHTML = \'<option value="">Failed to load</option>\';',
      repl: '    elements.tableSelect.innerHTML = \'<option value="">Failed to load</option>\';' }] },

  { name: 'M4 the loadTables de-dupe latch is bypassed (onopen races init)',
    sites: [{ file: 'api',
      find: '  if (tablesLoadInFlight) return tablesLoadInFlight;',
      repl: '  if (false && tablesLoadInFlight) return tablesLoadInFlight;' }] },

  { name: 'M5 the latch is never released (table list frozen for the session)',
    sites: [{ file: 'api',
      find: '  } finally {\n    tablesLoadInFlight = null;\n  }',
      repl: '  } finally {\n    /* leak */\n  }' }] },

  { name: 'M6 setBadge refuses to write (a guard that guards everything)',
    sites: [{ file: 'api',
      find: 'function setBadge(el, text, className) {\n  if (!el) return false;',
      repl: 'function setBadge(el, text, className) {\n  if (el) return false;' }] },

  { name: 'M7 the health failure is swallowed again (no console.error)',
    sites: [{ file: 'api',
      find: "    console.error('[health] server health check failed', err);\n", repl: '' }] },

  { name: 'M8 loadTables swallows its failure again (no console.error)',
    sites: [{ file: 'api',
      find: "    console.error('Failed to load tables', err);\n", repl: '' }] },

  // THE LIVE INCIDENT, REASSEMBLED. Socket last AND a catch that throws on a null handle. This
  // is the shape that produced "no /ws request at all" in the Network tab, and the one a
  // plain-rejection test cannot reach.
  { name: 'M9 the pre-round code: socket LAST + unguarded catch (the reported incident)',
    sites: [...SITE_SOCKET_LAST, SITE_HEALTH_CATCH_UNGUARDED] },
];

// Controls must ESCAPE. A harness that catches everything is not measuring the property, it is
// measuring "the file changed".
const CONTROLS = [
  { name: 'C1 reworded log message in loadTables',
    sites: [{ file: 'api',
      find: "console.error('Failed to load tables', err);",
      repl: "console.error('Could not load the table list', err);" }] },
  { name: 'C2 reworded thrown message for a non-ok /tables response',
    sites: [{ file: 'api',
      find: 'throw new Error(`/tables responded ${res.status}`);',
      repl: 'throw new Error(`/tables returned HTTP ${res.status}`);' }] },
  { name: 'C3 the offline badge text is translated',
    sites: [{ file: 'api',
      find: "setBadge(elements.performanceLog, 'Error connecting to database server');",
      repl: "setBadge(elements.performanceLog, '데이터베이스 서버에 연결할 수 없습니다');" }] },
];

async function sweep(list, expectCaught, heading) {
  console.log(`\n=== ${heading} ===`);
  let applied = 0, caught = 0;
  const notApplied = [], wrong = [];
  for (const m of list) {
    // Sites are applied cumulatively, each to the text the previous one produced, so a
    // multi-site mutation in ONE file cannot have its second anchor invalidated by its first.
    const src = { main: MAIN0, api: API0, ws: WS0 };
    let bad = null;
    for (let i = 0; i < m.sites.length && !bad; i++) {
      const s = m.sites[i];
      const a = applyOnce(src[s.file], s.find, s.repl);
      if (!a.ok) { bad = `site ${i + 1}/${m.sites.length} (${s.file}.js): ${a.why}`; break; }
      src[s.file] = a.src;
    }
    // CONFIRM THE MUTATED STATE, NOT MERELY THE OUTCOME. A mutation a later site repaired, or
    // one whose anchor survived, would score green and prove nothing. Re-checked against the
    // FINAL text, after every site has landed.
    for (let i = 0; i < m.sites.length && !bad; i++) {
      const s = m.sites[i];
      if (s.repl !== '' && !src[s.file].includes(s.repl))
        bad = `site ${i + 1} (${s.file}.js): the replacement is absent from the final mutated text`;
      else if (!s.repl.includes(s.find) && countOf(src[s.file], s.find) !== 0)
        bad = `site ${i + 1} (${s.file}.js): the ORIGINAL text is still present after mutation`;
    }
    if (bad) { notApplied.push(m.name); console.error(`  NOT APPLIED  ${m.name}\n    ${bad}`); continue; }
    applied++;

    const mainS = src.main, apiS = src.api, wsS = src.ws;

    const before = { pass, fail, n: failures.length };
    quiet = true;
    let threw = null;
    try { await runChecks(mainS, apiS, wsS, CFG0, { strict: true }); }
    catch (e) { threw = e; failures.push(`${m.name}: threw ${e && e.message}`); fail++; }
    quiet = false;
    const newFails = failures.slice(before.n);
    pass = before.pass; fail = before.fail; failures.length = before.n;

    const wasCaught = newFails.length > 0;
    if (wasCaught === expectCaught) {
      if (wasCaught) caught++;
      console.log(`  ${wasCaught ? 'caught ' : 'escaped'} ${m.name}\n            by ${
        wasCaught ? `${newFails.length} assertion(s), first: ${newFails[0]}` : 'no detector fired'}`);
    } else {
      wrong.push(m.name);
      console.error(`  ${expectCaught ? 'ESCAPED' : 'WRONGLY CAUGHT'} ${m.name}\n    ${newFails.join(' | ') || '(nothing fired)'}`);
    }
  }
  return { applied, caught, notApplied, wrong };
}

const mut = await sweep(MUTATIONS, true, 'MUTATION SWEEP (these must be CAUGHT)');
const ctl = await sweep(CONTROLS, false, 'CONTROL SWEEP (these must ESCAPE)');

console.log('\n=== SUMMARY ===');
console.log(`  baseline assertions : ${pass} passed, ${fail} failed`);
console.log(`ASSERTIONS ${pass + fail} ${fail}`);
console.log(`  mutations declared  : ${MUTATIONS.length}`);
console.log(`  mutations APPLIED   : ${mut.applied}`);
console.log(`  mutations CAUGHT    : ${mut.caught}`);
console.log(`  controls APPLIED    : ${ctl.applied}`);
console.log(`  controls ESCAPED    : ${ctl.applied - ctl.wrong.length} of ${CONTROLS.length} (must be all)`);
if (mut.notApplied.length) console.error(`  NOT APPLIED: ${mut.notApplied.join(' | ')}`);
if (mut.wrong.length) console.error(`  ESCAPED (must not): ${mut.wrong.join(' | ')}`);
if (ctl.notApplied.length) console.error(`  CONTROLS NOT APPLIED: ${ctl.notApplied.join(' | ')}`);
if (ctl.wrong.length) console.error(`  CONTROLS WRONGLY CAUGHT: ${ctl.wrong.join(' | ')}`);

const bad = fail > 0
  || mut.applied !== MUTATIONS.length || mut.caught !== MUTATIONS.length
  || ctl.applied !== CONTROLS.length || ctl.wrong.length > 0;
if (bad) process.exit(1);
console.log('\nOK — no failure in REST startup, including a catch block that throws and a fetch that never settles, can leave the page without a socket.');
