// Harness — NOTHING IN STARTUP CAN LEAVE THE PAGE WITHOUT A WEBSOCKET.
// Run: node client2/tests/startup_socket_gate_harness.mjs   (needs client2/node_modules: the
//      real api.js pulls ag-grid-community through grid.js, exactly as the page does)
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
// So the real boot order (`startup.js`), the real `checkServerHealth`/`loadTables` (api.js) and
// the real `initWebSocket`/`scheduleReconnect`/`wakeNow` (websocket.js) are driven against a
// fake socket and a fake `fetch` on a virtual clock. The scored quantity is a literal
// `new WebSocket('ws://…/ws')` — the same event whose absence the user read in the Network tab.
// Nothing here re-implements the code under test; re-implementing it would score this file
// against itself.
//
// HOW THE SUBJECTS ARE REACHED (C-110, 2026-09-16). They are IMPORTED, whole. Until this round
// the harness read main.js, api.js and websocket.js as TEXT, regex-sliced twelve functions out
// of them and evaluated the fragments in `vm` with a hand-written sandbox of every collaborator
// the fragments named. That measured the shape of the letters, not the behaviour: every
// module-level name main.js gained (`installAuditFilters`, `initGridSourceLabel`,
// `redoBannerFollows` …) made all 24 section-C scenarios throw ReferenceError on CORRECT code,
// and each time this file grew a stub and an anchor. The owner's rule (CLAUDE.md, 2026-09-02):
// a harness imports its subject; if the subject cannot be imported, THAT is the defect.
//   · The boot order was the one thing that lived in a file node cannot import (main.js seats
//     the whole page). It is now `src/startup.js`, which main.js calls and this file imports.
//   · api.js and websocket.js import under node already. They are loaded through the probe
//     bridge (`lib/probe.mjs`) rather than a bare `import` for two reasons that `export` cannot
//     serve: every scenario needs a FRESH module (the hung-REST scenario leaves the
//     `tablesLoadInFlight` latch holding a promise that never settles, which would poison the
//     next scenario), and the mutation sweep needs the WHOLE module mutated, not a fragment.
//     The probe copies the file byte-for-byte, appends an accessor, and asserts on every load
//     that the copy begins with the subject's own bytes — nothing is cut.
//   · Sibling modules the subjects import are redirected to stubs ONLY where the question
//     being scored does not run through them (`state` and `elements` so each scenario has its
//     own; the grid, history, toast and reference-view collaborators of `switchTable`). The
//     probe refuses a stub for a name the subject does not import, so a stub cannot go stale
//     silently.
//   · `switchTable` is api.js-internal and runs FOR REAL now, so the damage of a duplicate
//     bootstrap is measured at its doors: one `/schema` fetch and one `renderGrid` per run.
//   VERIFIED 2026-09-16: with the order extracted, a new name in main.js cannot touch this
//   harness — main.js is not read here at all. Measured with a module-level
//   `let c110ScratchState = 0;` and `export function c110ScratchProbe() {…}` appended to
//   main.js (then restored byte-for-byte): 111 passed, 9/9 caught, 3/3 escaped — identical
//   to the untouched tree. Under the sliced version the same edit was the C-110 defect.
//
// MUTATION DISCIPLINE. Every `find` string is required to occur EXACTLY ONCE in its file;
// `applyOnce` fails on 0 or >1 matches rather than proceeding, and the mutated text is re-read
// to confirm the mutation is present and the original gone before anything is scored. This
// directory has twice had a mutation land on its first match inside a COMMENT and silently
// score a different function. The mutant is then loaded as a WHOLE module through the probe,
// which itself refuses a `mutate` that changed nothing.
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { loadWithProbe, readSourceText } from './lib/probe.mjs';
import * as CFG from '../src/config.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = (f) => join(HERE, '..', 'src', f);
const PATHS = { startup: SRC('startup.js'), api: SRC('api.js'), ws: SRC('websocket.js') };
// LF text for the anchor checks — the same normalisation the probe hands to `mutate`, so an
// anchor written with a bare `\n` means the same thing in every worktree.
const TEXT = { startup: readSourceText(PATHS.startup).text,
               api: readSourceText(PATHS.api).text,
               ws: readSourceText(PATHS.ws).text };

function die(msg) {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  console.log('ASSERTIONS 0 1');
  process.exit(2);
}

// The reconnect tuning is IMPORTED from config.js, not regex-lifted out of it.
for (const k of ['WS_RECONNECT_BASE_MS', 'WS_RECONNECT_CEILING_MS']) {
  if (typeof CFG[k] !== 'number') die(`config.js does not export a numeric ${k}`);
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
                      // lands while startup's own `loadTables()` is still in flight — that
                      // overlap is the ordering hazard the latch exists for, and a fixture
                      // where the socket opened last would never exercise it.

const noop = () => {};
const mkEl = () => ({
  textContent: '', className: '', innerHTML: '', value: '', checked: false, style: {},
  appendChild(o) { this.value = this.value || o.value; },
  classList: { add: noop, remove: noop },
});

// The globals the subjects reach for by bare name. Each scenario installs its own fakes and
// puts the originals back, so the probe (which runs between scenarios) never sees a fake clock.
const REAL = {
  fetch: globalThis.fetch, WebSocket: globalThis.WebSocket,
  setTimeout: globalThis.setTimeout, clearTimeout: globalThis.clearTimeout,
  console: globalThis.console, dateNow: Date.now, random: Math.random,
};
function installGlobals(fakes) {
  globalThis.fetch = fakes.fetch;
  globalThis.WebSocket = fakes.WebSocket;
  globalThis.setTimeout = fakes.setTimeout;
  globalThis.clearTimeout = fakes.clearTimeout;
  globalThis.console = fakes.console;
  Date.now = fakes.dateNow;
  Math.random = () => 0;
  globalThis.document = fakes.document;
  globalThis.window = fakes.window;
  globalThis.localStorage = { getItem: () => null, setItem: noop };
}
function restoreGlobals() {
  globalThis.fetch = REAL.fetch;
  globalThis.WebSocket = REAL.WebSocket;
  globalThis.setTimeout = REAL.setTimeout;
  globalThis.clearTimeout = REAL.clearTimeout;
  globalThis.console = REAL.console;
  Date.now = REAL.dateNow;
  Math.random = REAL.random;
  delete globalThis.document;
  delete globalThis.window;
  delete globalThis.localStorage;
}

/**
 * `restMode` decides what `fetch` does. The DOM handles listed in `missing` resolve to null,
 * which is the mechanism behind reproduction #2 above. `mut` carries an optional whole-module
 * mutation per subject (`{ startup, api, ws }`), each a `(text) => text`.
 */
async function drive(mut, {
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
  let gridRebuilds = 0, fetchDataCalls = 0, restSettled = 0;

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

  const cache = {};
  const elements = new Proxy({}, { get(_, k) {
    if (typeof k !== 'string') return undefined;
    if (missing.includes(k)) return null;          // the getter resolves to null — see #2
    return cache[k] || (cache[k] = mkEl());
  } });

  // What a healthy server answers, by route. `switchTable` runs for real now, so the schema
  // and data reads it makes after `/tables` have to be answered too; the shapes are the
  // minimum those readers consume. In every failure mode all routes fail alike, as before.
  const okBody = (url) => {
    if (/\/schema$/.test(url)) return { columns: ['pkg_id'], column_types: {}, kind: 'table',
      business_key: 'pkg_id', composite_key_source: [], virtual_columns: [], join_resolved_columns: [] };
    if (/\/data\?/.test(url)) return { data: [], total: 0 };
    return { tables: ['bonding_map', 'dt_log'] };
  };
  const fetchFake = (url) => new Promise((resolve, reject) => {
    restCalls.push({ t: now, url });
    if (restMode === 'hang') return;                                    // never settles, ever
    rawSchedule(() => {
      restSettled++;
      if (restMode === 'reject') return reject(new TypeError('Failed to fetch'));
      if (restMode === 'http500') return resolve({ ok: false, status: 500, json: async () => ({}) });
      if (restMode === 'badjson') return resolve({ ok: true, status: 200, json: async () => { throw new SyntaxError('Unexpected token <'); } });
      resolve({ ok: true, status: 200, json: async () => okBody(url) });
    }, REST_MS);
  });

  // A fresh `state` per scenario, with the containers `switchTable`/`fetchData` mutate and a
  // grid handle that accepts what they hand it. The reconnect fields start where state.js
  // starts them (base delay, no socket, no timer).
  const state = {
    ws: null, wsRetryTimer: null, wsOpenedAt: 0, wsLastWakeAt: 0, wsWakeSignalsInstalled: false,
    wsReconnectDelay: CFG.WS_RECONNECT_BASE_MS, wsPrevReconnectDelay: CFG.WS_RECONNECT_BASE_MS,
    // The connect watchdog's state. This harness's fake socket always resolves, so the
    // watchdog never trips here — the hang it exists for is scored in
    // `ws_connect_watchdog_harness.mjs`. Present because the real code reads them.
    wsConnectWatchdog: null, wsConnectingSince: 0, wsWatchdogTrips: 0,
    currentTable: '', currentTransactionId: null, pendingTxEdits: {}, pageCache: new Map(),
    currentColumns: [], currentSkip: 0, isLoadingMore: false, viewMode: 'pagination',
    gridApi: { setGridOption: noop, applyTransaction: noop, getFilterModel: () => ({}) },
  };

  const fakes = {
    fetch: fetchFake, WebSocket: FakeWebSocket, setTimeout: rawSchedule, clearTimeout: clearFake,
    console: { log: noop, warn: noop, error: (...a) => errors.push(a.map(String).join(' ')) },
    dateNow: () => now,
    document: {
      createElement: () => mkEl(),
      getElementById: () => null,
      querySelector: () => ({ classList: { add: noop, remove: noop } }),
      addEventListener: noop,
      get visibilityState() { return 'visible'; },
    },
    window: { addEventListener: noop, location: { search: '', pathname: '/', origin: 'http://localhost' } },
  };

  // ── the subjects, whole ───────────────────────────────────────────────────────
  // Loaded BEFORE the fake globals go in: the probe and node's own loader run here.
  let api, ws;
  const apiLoad = await loadWithProbe(PATHS.api, {
    stubs: {
      './config.js': { API_BASE: 'http://127.0.0.1:8080' },
      './state.js': { state },
      './dom.js': { elements },
      // Collaborators OUTSIDE the question being scored — what `switchTable` calls once the
      // table list is in. `renderGrid` is counted rather than run: two bootstraps mean two
      // grid teardowns, and that is the door the damage is measured at.
      './clipboard.js': { clearRangeSelection: noop },
      './ui.js': { updateSelectedCellUI: noop, updateTxModeUI: noop },
      './write_guard.js': { applyWriteGuards: noop },
      './grid.js': { renderGrid: () => { gridRebuilds++; }, updateGridSortState: noop,
                     updateLoadedCount: noop, updatePaginationUI: noop, applyFillTargetHeaders: noop,
                     sortQueryTail: () => '' },
      './timeline.js': { loadHistory: async () => {} },
      './utils.js': { showToast: noop, getLocalTimeString: () => '' },
      './value_suggest.js': { resetSuggestLearning: noop },
      './enrichment_reference_view.js': { syncReferenceViewRule: async () => {} },
      './match_count.js': { setMatchCount: noop },
    },
    mutate: mut.api, tag: 'sgapi',
  });
  api = apiLoad.module;
  const wsLoad = await loadWithProbe(PATHS.ws, {
    stubs: {
      './config.js': { WS_URL: 'ws://127.0.0.1:8080/ws' },
      './state.js': { state },
      './dom.js': { elements },
      // The socket's bootstrap runs THIS scenario's api.js, so `onopen` and startup share one
      // latch — which is the overlap section D scores.
      './api.js': { checkServerHealth: (...a) => api.checkServerHealth(...a),
                    loadTables: (...a) => api.loadTables(...a),
                    fetchData: () => { fetchDataCalls++; } },
    },
    mutate: mut.ws, tag: 'sgws',
  });
  ws = wsLoad.module;
  const bootLoad = await loadWithProbe(PATHS.startup, {
    stubs: {
      './websocket.js': { initWebSocket: (...a) => ws.initWebSocket(...a) },
      './api.js': { checkServerHealth: (...a) => api.checkServerHealth(...a),
                    loadTables: (...a) => api.loadTables(...a) },
    },
    mutate: mut.startup, tag: 'sgboot',
  });
  const boot = bootLoad.module;

  const flush = () => new Promise(r => setImmediate(r));

  let settled = 'pending', rejection = null;
  installGlobals(fakes);
  try {
    // `startup()` IS NOT AWAITED. Awaiting it would hang the harness on the very scenario that
    // matters most (`restMode: 'hang'`) and, worse, would make the socket look reachable only
    // because the harness waited for something the browser never waits for. `prepare` and
    // `tableChosen` are main.js's business (listeners, parts); the order is what is scored.
    boot.startup({ prepare: noop, tableChosen: noop })
      .then(() => { settled = 'fulfilled'; }, e => { settled = 'rejected'; rejection = e; });
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
      api.loadTables();
      let g2 = 0;
      while (timers.length && g2++ < 10000) {
        timers.sort((a, b) => a.at - b.at || a.seq - b.seq);
        const t = timers.shift();
        if (t.at > horizonMs) break;
        now = t.at; t.fn(); await flush();
      }
      await flush();
    }
  } finally {
    restoreGlobals();
  }

  return {
    wsAttempts, errors, restCalls, restSettled, gridRebuilds, fetchDataCalls, settled, rejection,
    // One `switchTable` run = one `/schema` read. Counted at the door, since the function
    // itself is api.js-internal and runs for real.
    switchTableCalls: restCalls.filter(c => /\/schema$/.test(c.url)).length,
    onopenRejections: onopenRejections.map(e => (e && e.message) || String(e)),
    wsAttemptCount: wsAttempts.length,
    firstWsAttemptAt: wsAttempts.length ? wsAttempts[0].t : null,
    wsUrls: [...new Set(wsAttempts.map(a => a.url))],
    serverBadge: cache.serverStatus ? cache.serverStatus.textContent : null,
    tablePicker: cache.tableSelect ? cache.tableSelect.value : null,
  };
}

// ── The checks ──────────────────────────────────────────────────────────────────
async function runChecks(mut, { strict = true } = {}) {
  const r = {};

  // ── A. THE FLOOR: A SOCKET IS ATTEMPTED, WHATEVER STARTUP DOES ───────────────
  //   Every one of these is a way startup can fail to reach its own last statement. The
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
      const run = await drive(mut, opts);
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
    const hung = await drive(mut, { restMode: 'hang' });
    r.hungWsAt = hung.firstWsAttemptAt;
    r.hungRestSettled = hung.restSettled;
    const okRun = await drive(mut, { restMode: 'ok' });
    r.okWsAt = okRun.firstWsAttemptAt;

    if (strict) {
      check('B: with REST hung forever, the socket was still attempted', hung.wsAttemptCount >= 1, true);
      check('B: ...and it happened with ZERO REST calls settled', hung.restSettled, 0);
      check('B: ...and startup is indeed still pending (the fixture really is stuck)', hung.settled, 'pending');
      checkFn('B: on a healthy start the socket is attempted before the first REST round trip returns',
        okRun.firstWsAttemptAt, v => v !== null && v < REST_MS, `< ${REST_MS}ms (the REST latency)`);
    }
  }

  // ── C. A CATCH BLOCK MUST NOT BE ABLE TO THROW ───────────────────────────────
  //   Scored directly on the two functions rather than only through startup, so the property
  //   is pinned where it lives. Every subset of the handles their catches touch.
  {
    const HANDLE_SETS = [
      [], ['serverStatus'], ['performanceLog'], ['tableSelect'],
      ['serverStatus', 'performanceLog'], ['serverStatus', 'tableSelect'],
      ['performanceLog', 'tableSelect'], ['serverStatus', 'performanceLog', 'tableSelect'],
    ];
    r.catchSafe = true;
    for (const missing of HANDLE_SETS) {
      for (const restMode of ['reject', 'http500', 'badjson']) {
        const run = await drive(mut, { restMode, missing });
        const label = `[${missing.join(',') || 'all present'}] / ${restMode}`;
        if (run.settled === 'rejected') r.catchSafe = false;
        if (strict) {
          checkFn(`C: startup does not reject — ${label}`,
            run.settled, v => v !== 'rejected',
            `not "rejected" (got ${run.rejection && run.rejection.message})`);
          checkFn(`C: the failure is still REPORTED, not swallowed — ${label}`,
            run.errors.length, v => v >= 1, '>= 1 console.error');
          // 🔴 A COUNT CANNOT SAY *WHICH* REPORT SURVIVED. `>= 1` was enough only while this
          //    scenario produced exactly one console.error; the moment `loadTables` began
          //    reporting its own failure too (2026-09-06, the res.ok round), deleting the
          //    health report left the count at 1 and mutant M7 walked straight through.
          //    So the health failure is asserted BY NAME. `[health]` is a tag, not a
          //    sentence -- pinning wording is what reddens a harness on a copy edit.
          if (restMode === 'http500') {
            checkFn(`C: and the HEALTH failure specifically is named — ${label}`,
              run.errors.filter(e => e.includes('[health]')).length, v => v >= 1,
              'an error mentioning [health]');
          }
          // The SOCKET's bootstrap runs the same two functions. A catch that throws breaks the
          // reconnect path too, silently — `onopen`'s rejection belongs to nobody.
          check(`C: the socket's own onopen bootstrap does not reject either — ${label}`,
            run.onopenRejections, []);
        }
      }
    }
  }

  // ── D. THE ORDERING THE MOVE COULD HAVE BROKEN ───────────────────────────────
  //   `onopen` bootstraps the table list when it finds the picker empty. With the socket
  //   started first, that fires WHILE startup's own `loadTables()` is in flight. Two concurrent
  //   bootstraps would mean two `switchTable` runs — two schema loads, two grid rebuilds.
  {
    const run = await drive(mut, { restMode: 'ok' });
    r.switchTableCalls = run.switchTableCalls;
    r.gridRebuilds = run.gridRebuilds;
    r.tablePicker = run.tablePicker;
    r.serverBadge = run.serverBadge;

    if (strict) {
      check('D: the overlapping bootstraps collapse into ONE switchTable (one schema load, one grid rebuild)',
        [run.switchTableCalls, run.gridRebuilds], [1, 1]);
      check('D: ...and the table list actually got loaded (the run is not vacuous)', run.tablePicker, 'bonding_map');
      check('D: a healthy start reports the API online', run.serverBadge, 'API: ONLINE');
      checkFn('D: the socket connected exactly once on a healthy start',
        run.wsAttemptCount, v => v === 1, 'exactly 1 attempt');
    }

    const offline = await drive(mut, { restMode: 'reject', serverUp: false, horizonMs: 60000 });
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
    const run = await drive(mut, { restMode: 'ok', extraLoads: 2 });
    r.loadsAfterExtra = run.switchTableCalls;
    if (strict) {
      check('E: two later sequential loadTables() calls each run (the latch clears)', run.switchTableCalls, 3);
    }
  }

  // ── F. THE RECONNECT LADDER THAT JUST LANDED STILL WORKS ─────────────────────
  //   Starting the socket earlier must not cost the retry behaviour. A refused socket has to
  //   keep retrying on a rising interval, from inside the new call site.
  {
    const run = await drive(mut, { restMode: 'reject', serverUp: false, horizonMs: 120000 });
    const gaps = [];
    for (let i = 1; i < run.wsAttempts.length; i++) gaps.push(run.wsAttempts[i].t - run.wsAttempts[i - 1].t);
    r.retryAttempts = run.wsAttempts.length;
    r.retryGaps = gaps.slice(0, 5);
    r.ladderRises = gaps.slice(0, 3).every((g, i) => i === 0 || g >= gaps[i - 1]);
    const CEIL = CFG.WS_RECONNECT_CEILING_MS;
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
const NO_MUTATION = { startup: undefined, api: undefined, ws: undefined };
console.log('=== BASELINE (the code as it stands) ===');
const base = await runChecks(NO_MUTATION, { strict: true });
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
// catches hardened, moving the socket back to the end of startup is survivable on the
// catch-throws scenarios (they no longer throw), and with the socket started first, a throwing
// catch no longer costs the socket. M9 is the combination — the code as it actually shipped —
// and it is the one that reproduces the LIVE symptom on the catch-throws path.
const SITE_SOCKET_LAST = [
  { file: 'startup',
    find: '  initWebSocket();\n\n  prepare();',
    repl: '  prepare();' },
  { file: 'startup',
    // The CLAIM: the socket back at the last statement of startup, after both awaits.
    find: '  tableChosen();\n}',
    repl: '  tableChosen();\n  initWebSocket();\n}' },
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
  { name: 'M1 socket moved back to the LAST statement of startup (half of the original defect)',
    sites: SITE_SOCKET_LAST },

  { name: 'M2 checkServerHealth\'s catch writes its badges unguarded (catch can throw again)',
    sites: [SITE_HEALTH_CATCH_UNGUARDED] },

  { name: 'M3 loadTables\'s catch writes #table-select unguarded (catch can throw again)',
    sites: [{ file: 'api',
      find: '    if (elements.tableSelect) elements.tableSelect.innerHTML = \'<option value="">Failed to load</option>\';',
      repl: '    elements.tableSelect.innerHTML = \'<option value="">Failed to load</option>\';' }] },

  { name: 'M4 the loadTables de-dupe latch is bypassed (onopen races startup)',
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
    const src = { ...TEXT };
    const touched = new Set();
    let bad = null;
    for (let i = 0; i < m.sites.length && !bad; i++) {
      const s = m.sites[i];
      const a = applyOnce(src[s.file], s.find, s.repl);
      if (!a.ok) { bad = `site ${i + 1}/${m.sites.length} (${s.file}.js): ${a.why}`; break; }
      src[s.file] = a.src;
      touched.add(s.file);
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

    // The mutant is handed to the probe as a WHOLE-MODULE `mutate`, one per touched file. The
    // probe re-checks that the text actually changed and dies otherwise.
    const mut = { startup: undefined, api: undefined, ws: undefined };
    for (const f of touched) mut[f] = () => src[f];

    const before = { pass, fail, n: failures.length };
    quiet = true;
    let threw = null;
    try { await runChecks(mut, { strict: true }); }
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
