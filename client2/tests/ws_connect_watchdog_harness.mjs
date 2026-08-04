// Harness — a WebSocket stuck in CONNECTING is failed on a bound, so the reconnect ladder can
// do its job. And a slow-but-real connect is NOT killed, because that is the worse failure.
// Run: node client2/tests/ws_connect_watchdog_harness.mjs   (no node_modules — vm sandbox)
//
// WHAT WAS ACTUALLY WRONG (production 2026-08-04). Reaching the app as `localhost` resolves to
// the IPv6 loopback first while the server binds IPv4 only, and the socket then enters
// CONNECTING and NEVER LEAVES: no `onopen`, no `onclose`, no `onerror`. The same server by its
// external IP connects normally. The server-side cause is fixed elsewhere; this file is about
// the client surviving it, because any blackholed route reproduces it — a proxy that neither
// completes nor rejects an Upgrade, a firewall that drops, a half-open NAT.
//
// WHY THE HANG IS WORSE THAN A FAILURE. Every recovery path in `websocket.js` is driven by
// `onclose`. Measured against the UNPATCHED source with the fake socket below:
//     connection attempts        : 1
//     retries SCHEDULED by code  : 0
//     timers outstanding at end  : 0
//     badge at end               : "WS: 연결 시도 1"
// and five wake signals spread over four minutes changed none of those numbers, because
// `wakeNow` refuses to act while readyState is CONNECTING. The 5s ceiling, the wake signals and
// the flap guard are all bypassed by a socket that simply never resolves. The page is inert.
//
// WHY A SIBLING RATHER THAN AN EXTENSION. `ws_reconnect_backoff_harness.mjs` scores the LADDER
// and sweeps 13 mutants through a 120-sample restart sweep; this scores the BOUND, and the two
// need opposite fixtures (that one's fake socket always resolves in single-digit ms, which is
// exactly the case in which a watchdog can never fire). They do share the slicing discipline,
// and both had to learn the same lesson about `setTimeout`: see `watchdogIds` below.
//
// MUTATION DISCIPLINE. Every `find` string below was verified to occur EXACTLY ONCE in its
// file; `applyOnce` fails on 0 or >1 matches rather than proceeding, and re-reads the mutated
// text to confirm the mutation is still present in what it hands to the checks. This directory
// has twice had a mutation land on its first match inside a COMMENT and silently score a
// different function.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
const WS_PATH = join(HERE, '..', 'src', 'websocket.js');
const CFG_PATH = join(HERE, '..', 'src', 'config.js');

const WS0 = readFileSync(WS_PATH, 'utf8').replace(/\r\n/g, '\n');
const CFG0 = readFileSync(CFG_PATH, 'utf8').replace(/\r\n/g, '\n');

function die(msg) {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  process.exit(2);
}

// ── The measurements this file is calibrated against ────────────────────────────
// Live stack, 2026-08-04. These are the numbers the bound has to be defensible against, and
// they are named rather than inlined so an assertion that cites one says which one.
const MEASURED_HANDSHAKE_MAX_MS = 4.15;    // WS handshake vs live :8080, median 2.54ms
const MEASURED_STARTUP_MAX_MS = 3094;      // server lifespan startup, n=324, median 12ms
const FAIL_MS = 3;                         // ECONNREFUSED, rounded up from 0.49ms median / 2.71ms max
const OPEN_MS = 5;                         // handshake, rounded up from the 4.15ms max

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
// Anchored at a real declaration, never at a bare name.
function fn(src, name) {
  const m = new RegExp(`(?:export\\s+)?(?:async\\s+)?function\\s+${name}\\s*\\(`).exec(src);
  if (!m) die(`function ${name} not found in websocket.js — renamed or reshaped.`);
  const body = sliceBalanced(src, m.index, '{', '}');
  if (!body) die(`unbalanced braces for ${name}`);
  return body.replace(/^export\s+/, '');
}
// A tunable's declared VALUE, read out of config.js. Anchored at `export const <NAME> =` so a
// mention in a comment cannot be mistaken for the declaration.
function cfgNumber(src, name) {
  const m = new RegExp(`export\\s+const\\s+${name}\\s*=\\s*([0-9.]+)\\s*;`).exec(src);
  if (!m) die(`\`export const ${name}\` not found in config.js — renamed, moved, or no longer a literal.`);
  return Number(m[1]);
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
// `behaviour(createdAt)` decides what the socket about to be created does. Returning
// `{kind:'hang'}` models the production defect: readyState stays 0 and NO callback is ever
// scheduled, so the socket is genuinely inert rather than slow.
const ALWAYS_HANGS = () => ({ kind: 'hang' });

async function drive(wsSrc, cfgSrc, {
  behaviour = ALWAYS_HANGS, horizonMs = 300000, rand = () => 0, signals = [], startVisible = true,
} = {}) {
  let now = 0, seq = 0;
  const timers = [];
  const events = [];
  let openedAt = null, openCount = 0;
  const listeners = { visibilitychange: [], online: [] };
  let visibility = startVisible ? 'visible' : 'hidden';

  // TWO SCHEDULERS ON PURPOSE, same split as the sibling harness: `rawSchedule` is the fake
  // socket's own latency, `setTimeoutFake` is what the CODE UNDER TEST gets.
  //
  // AND THE CODE'S TIMERS ARE NOT ALL THE SAME KIND. `initWebSocket` now arms a watchdog per
  // attempt as well as queueing retries, and conflating the two made the sibling harness report
  // the ladder as `8000,1000,8000,2000,...`. Watchdog timers are identified by IDENTITY — the
  // ids that were ever the live `state.wsConnectWatchdog` — and never by their delay, because
  // classifying on `ms === WS_CONNECT_TIMEOUT_MS` would silently reclassify ladder rungs the
  // moment the two constants were tuned to the same number.
  const scheduledRaw = [];
  const watchdogIds = new Set();
  const codePending = new Set();
  const rawSchedule = (f, ms) => { const id = ++seq; timers.push({ at: now + (ms || 0), seq: id, fn: f }); return id; };
  const setTimeoutFake = (f, ms) => {
    const id = rawSchedule(f, ms);
    scheduledRaw.push({ id, ms });
    codePending.add(id);
    return id;
  };
  const clearTimeoutFake = id => {
    codePending.delete(id);
    const i = timers.findIndex(t => t.seq === id);
    if (i >= 0) timers.splice(i, 1);
  };

  class FakeWebSocket {
    constructor(url) {
      this.url = url; this.readyState = 0; this._dead = false;
      const plan = behaviour(now);
      events.push({ t: now, kind: 'attempt', plan: plan.kind });
      if (plan.kind === 'hang') return;   // <- NOTHING is scheduled. This is the whole defect.
      if (plan.kind === 'open') {
        rawSchedule(() => {
          if (this._dead) return;
          this.readyState = 1; openedAt = now; openCount++;
          events.push({ t: now, kind: 'open' });
          this.onopen && this.onopen();
        }, plan.afterMs === undefined ? OPEN_MS : plan.afterMs);
        return;
      }
      rawSchedule(() => {
        if (this._dead) return;
        this.readyState = 3;
        events.push({ t: now, kind: 'refused' });
        this.onerror && this.onerror(new Error('ECONNREFUSED'));
        this.onclose && this.onclose();
      }, plan.afterMs === undefined ? FAIL_MS : plan.afterMs);
    }
    // A BROWSER DOES FIRE A CLOSE EVENT WHEN YOU CLOSE A CONNECTING SOCKET, asynchronously.
    // Modelling that is what makes "detach the handlers BEFORE closing" a scoreable property
    // rather than a stylistic preference: without the detach this event lands on the real
    // `onclose`, which overwrites the badge that just said WHY the attempt died and re-enters
    // the reconnect path for a second time on one failure.
    close() {
      if (this._dead) return;
      this._dead = true; this.readyState = 3;
      rawSchedule(() => {
        events.push({ t: now, kind: 'close-event', observed: !!this.onclose });
        this.onclose && this.onclose();
      }, 0);
    }
  }

  const badge = { textContent: '', className: '' };
  const badgeTrace = [];
  const calls = { checkServerHealth: 0, loadTables: 0, fetchData: [] };

  const sandbox = {
    WebSocket: FakeWebSocket,
    WS_URL: 'ws://localhost:8080/ws',
    WS_RECONNECT_BASE_MS: cfgNumber(cfgSrc, 'WS_RECONNECT_BASE_MS'),
    WS_RECONNECT_CEILING_MS: cfgNumber(cfgSrc, 'WS_RECONNECT_CEILING_MS'),
    WS_RECONNECT_JITTER: cfgNumber(cfgSrc, 'WS_RECONNECT_JITTER'),
    WS_HEALTHY_SESSION_MS: cfgNumber(cfgSrc, 'WS_HEALTHY_SESSION_MS'),
    WS_WAKE_MIN_GAP_MS: cfgNumber(cfgSrc, 'WS_WAKE_MIN_GAP_MS'),
    WS_CONNECT_TIMEOUT_MS: cfgNumber(cfgSrc, 'WS_CONNECT_TIMEOUT_MS'),
    WS_CONNECT_STALE_MS: cfgNumber(cfgSrc, 'WS_CONNECT_STALE_MS'),
    state: {
      ws: null, wsReconnectDelay: cfgNumber(cfgSrc, 'WS_RECONNECT_BASE_MS'),
      wsRetryTimer: null, wsOpenedAt: 0,
      wsPrevReconnectDelay: cfgNumber(cfgSrc, 'WS_RECONNECT_BASE_MS'),
      wsLastWakeAt: 0, wsWakeSignalsInstalled: false,
      wsConnectWatchdog: null, wsConnectingSince: 0, wsWatchdogTrips: 0,
      currentTable: 'bonding_map', pageCache: new Map(),
    },
    elements: { get wsStatus() { return badge; }, tableSelect: { value: 'bonding_map' } },
    document: {
      querySelector: () => ({ classList: { add() {}, remove() {} } }),
      addEventListener: (ev, f) => { (listeners[ev] || (listeners[ev] = [])).push(f); },
      get visibilityState() { return visibility; },
    },
    window: { addEventListener: (ev, f) => { (listeners[ev] || (listeners[ev] = [])).push(f); } },
    console: { log() {}, error() {}, warn() {} },
    setTimeout: setTimeoutFake,
    clearTimeout: clearTimeoutFake,
    Date: { now: () => now },
    Math: Object.assign(Object.create(Math), { random: () => rand() }),
    JSON, Set, Map, Object, Array, Number, String, Promise, Error,
    checkServerHealth: async () => { calls.checkServerHealth++; },
    loadTables: async () => { calls.loadTables++; },
    fetchData: reset => { calls.fetchData.push({ t: now, reset }); },
  };
  vm.createContext(sandbox);
  try {
    vm.runInContext([
      fn(wsSrc, 'scheduleReconnect'),
      fn(wsSrc, 'clearConnectWatchdog'),
      fn(wsSrc, 'abandonConnectingSocket'),
      fn(wsSrc, 'armConnectWatchdog'),
      fn(wsSrc, 'wakeNow'),
      fn(wsSrc, 'installWakeSignals'),
      fn(wsSrc, 'initWebSocket'),
      'globalThis.__go = initWebSocket;',
    ].join('\n\n'), sandbox);
  } catch (e) {
    die(`the sliced reconnect code does not evaluate: ${e && e.message}`);
  }

  // THE TWO STRUCTURAL INVARIANTS, sampled wherever the code is at rest.
  //
  //   `maxRetryPending`  — exactly one reconnect is ever queued. A teardown that produced two
  //                        retries would be invisible to an attempt count (both retries fire and
  //                        both connect); it is only visible as two timers coexisting.
  //   `maxArmedWhileIdle`— no watchdog outlives its socket. This is the assertion that "the
  //                        watchdog must be cleared on open and on close" reduces to: a timer
  //                        armed at a moment when nothing is CONNECTING belongs to a socket that
  //                        is already gone, and it will fire against whichever socket is current
  //                        by then.
  let maxRetryPending = 0, maxArmedWhileIdle = 0;
  const sample = () => {
    if (sandbox.state.wsConnectWatchdog !== null) watchdogIds.add(sandbox.state.wsConnectWatchdog);
    const live = [...codePending];
    const retries = live.filter(id => !watchdogIds.has(id)).length;
    if (retries > maxRetryPending) maxRetryPending = retries;
    const connecting = !!(sandbox.state.ws && sandbox.state.ws.readyState === 0);
    if (!connecting) {
      const armed = live.filter(id => watchdogIds.has(id)).length;
      if (armed > maxArmedWhileIdle) maxArmedWhileIdle = armed;
    }
  };

  const flush = () => new Promise(r => setImmediate(r));
  const pending = [...signals].sort((a, b) => a.at - b.at);
  sandbox.__go();
  await flush();
  sample();

  let guard = 0;
  while (now <= horizonMs && guard++ < 200000) {
    const nextTimer = timers.length ? Math.min(...timers.map(t => t.at)) : Infinity;
    const nextSignal = pending.length ? pending[0].at : Infinity;
    if (nextTimer === Infinity && nextSignal === Infinity) break;
    // The horizon is a wall, not a loop condition — see the sibling harness for the fixture this
    // silently rescued when it was only checked at the top of the loop.
    if (Math.min(nextTimer, nextSignal) > horizonMs) break;
    if (nextSignal <= nextTimer) {
      const s = pending.shift();
      now = s.at;
      if (s.type === 'visible') { visibility = 'visible'; (listeners.visibilitychange || []).forEach(f => f()); }
      else if (s.type === 'hidden') { visibility = 'hidden'; (listeners.visibilitychange || []).forEach(f => f()); }
      else if (s.type === 'online') { (listeners.online || []).forEach(f => f()); }
      await flush();
      sample();
      continue;
    }
    timers.sort((a, b) => a.at - b.at || a.seq - b.seq);
    const t = timers.shift();
    codePending.delete(t.seq);
    now = t.at;
    t.fn();
    await flush();
    sample();
    badgeTrace.push({ t: now, text: badge.textContent, cls: badge.className });
  }
  return {
    events, calls, openedAt, openCount, badgeTrace, maxRetryPending, maxArmedWhileIdle,
    retryDelays: scheduledRaw.filter(s => !watchdogIds.has(s.id)).map(s => s.ms),
    watchdogArms: scheduledRaw.filter(s => watchdogIds.has(s.id)).map(s => s.ms),
    attempts: events.filter(e => e.kind === 'attempt').map(e => e.t),
    closeEventsObserved: events.filter(e => e.kind === 'close-event' && e.observed).length,
    trips: sandbox.state.wsWatchdogTrips,
    finalDelay: sandbox.state.wsReconnectDelay,
    finalWatchdog: sandbox.state.wsConnectWatchdog,
    badgeStates: [...new Set(badgeTrace.map(b => b.text))].filter(Boolean),
  };
}

// ── The checks ──────────────────────────────────────────────────────────────────
async function runChecks(wsSrc, cfgSrc, { strict = true } = {}) {
  const r = {};
  const TIMEOUT = cfgNumber(cfgSrc, 'WS_CONNECT_TIMEOUT_MS');
  const STALE = cfgNumber(cfgSrc, 'WS_CONNECT_STALE_MS');
  const BASE = cfgNumber(cfgSrc, 'WS_RECONNECT_BASE_MS');
  const CEIL = cfgNumber(cfgSrc, 'WS_RECONNECT_CEILING_MS');
  r.timeout = TIMEOUT; r.stale = STALE;

  // ── A. THE HANG IS FAILED, AND THE LADDER TAKES OVER ─────────────────────────
  //   The headline. Against the unpatched source this run produced 1 attempt and 0 retries.
  {
    const run = await drive(wsSrc, cfgSrc, { behaviour: ALWAYS_HANGS, horizonMs: 300000 });
    r.hangAttempts = run.attempts.length;
    r.hangTrips = run.trips;
    r.hangRetries = run.retryDelays.length;
    r.hangLadder = run.retryDelays.slice(0, 6);
    r.hangSecondAttempt = run.attempts[1];
    r.hangLadderRises = run.retryDelays.slice(0, 4).every((g, i) => i === 0 || g > run.retryDelays[i - 1]);
    r.hangLadderCapped = run.retryDelays.every(g => g <= CEIL);

    if (strict) {
      // THE DEFECT, STATED AS A NUMBER. One attempt and nothing else is what shipped.
      checkFn('a socket that never resolves is retried instead of hanging forever',
        r.hangAttempts, v => v >= 20, '>= 20 attempts in 300s (the defect produced exactly 1)');
      checkFn('...because the watchdog failed each stuck attempt', r.hangTrips, v => v >= 20,
        '>= 20 watchdog trips');
      // The ladder is not re-implemented by the watchdog — it is HANDED to it.
      check('the second attempt lands one bound plus one base delay after the first',
        r.hangSecondAttempt, TIMEOUT + BASE);
      check('the ordinary backoff runs on top of the watchdog', r.hangLadderRises, true);
      check('...and is still clamped at the reconnect ceiling', r.hangLadderCapped, true);
    }
  }

  // ── B. EXACTLY ONE RETRY PER TEARDOWN ────────────────────────────────────────
  //   The requirement that makes the teardown safe. A synthetic close racing the real one is
  //   invisible in an attempt count and visible only here.
  {
    const run = await drive(wsSrc, cfgSrc, { behaviour: ALWAYS_HANGS, horizonMs: 300000 });
    r.retriesPerTrip = run.retryDelays.length - run.trips;
    r.maxRetryPending = run.maxRetryPending;
    r.closeEventsObserved = run.closeEventsObserved;

    if (strict) {
      check('every watchdog trip queues exactly one retry — not two', r.retriesPerTrip, 0);
      check('...and two reconnect timers never coexist', r.maxRetryPending, 1);
      // The mechanism behind the above: the handlers are detached BEFORE `close()`, so the
      // close event the browser then delivers lands on nothing.
      check('the synthetic close is never observed by the socket\'s own onclose',
        r.closeEventsObserved, 0);
    }
  }

  // ── C. THE BOUND DOES NOT KILL A SLOW-BUT-REAL CONNECT ───────────────────────
  //   THE NEGATIVE, and the one that matters most: killing a connection that was about to
  //   succeed converts a working page into a permanent reconnect loop, which is worse than the
  //   bug. Swept rather than sampled once, and the sweep deliberately includes the slowest real
  //   latency ever recorded on this stack.
  {
    const latencies = [0, 1, 50, 500, 1000, 2000, MEASURED_STARTUP_MAX_MS,
                       MEASURED_STARTUP_MAX_MS + OPEN_MS, 5000, 7000, TIMEOUT - 1];
    const survived = [];
    for (const afterMs of latencies) {
      const run = await drive(wsSrc, cfgSrc, {
        behaviour: () => ({ kind: 'open', afterMs }), horizonMs: 120000,
      });
      survived.push({ afterMs, trips: run.trips, opens: run.openCount, attempts: run.attempts.length });
    }
    r.slowConnectsKilled = survived.filter(s => s.trips > 0).map(s => s.afterMs);
    r.slowConnectsOpened = survived.filter(s => s.opens === 1 && s.attempts === 1).length;
    r.slowSweepSize = survived.length;

    // And the positive edge: just OUTSIDE the bound it is killed, so the bound is a real bound.
    const outside = await drive(wsSrc, cfgSrc, {
      behaviour: () => ({ kind: 'open', afterMs: TIMEOUT + 1 }), horizonMs: 120000,
    });
    r.justOutsideTrips = outside.trips;
    r.justOutsideAttempts = outside.attempts.length;

    if (strict) {
      check('no connect inside the bound is killed — including the slowest real one on record',
        r.slowConnectsKilled, []);
      check('...and each of them opened on its first attempt', r.slowConnectsOpened, r.slowSweepSize);
      checkFn('the sweep really covered a spread of latencies (the fixture is alive)',
        r.slowSweepSize, v => v >= 10, '>= 10 sampled latencies');
      // Without this the block above passes for a watchdog that never fires at all.
      checkFn('a connect just outside the bound IS killed', r.justOutsideTrips, v => v >= 1,
        '>= 1 trip');
      checkFn('...and retried', r.justOutsideAttempts, v => v >= 2, '>= 2 attempts');
    }
  }

  // ── D. NO TIMER OUTLIVES ITS SOCKET ──────────────────────────────────────────
  //   "Cleared on open and on close." A watchdog still armed when nothing is CONNECTING belongs
  //   to a socket that is already gone, and will fire against whatever is current by then.
  {
    const hung = await drive(wsSrc, cfgSrc, { behaviour: ALWAYS_HANGS, horizonMs: 120000 });
    const refused = await drive(wsSrc, cfgSrc, {
      behaviour: () => ({ kind: 'refuse' }), horizonMs: 300000,
    });
    const opened = await drive(wsSrc, cfgSrc, {
      behaviour: () => ({ kind: 'open' }), horizonMs: 120000,
    });
    r.armedWhileIdleHang = hung.maxArmedWhileIdle;
    r.armedWhileIdleRefuse = refused.maxArmedWhileIdle;
    r.armedWhileIdleOpen = opened.maxArmedWhileIdle;
    r.refuseTrips = refused.trips;
    r.refuseAttempts = refused.attempts.length;
    // The load-bearing one: a healthy session must still be alive long after the bound elapsed.
    r.healthyAttempts = opened.attempts.length;
    r.healthyOpens = opened.openCount;
    r.healthyTrips = opened.trips;
    r.healthyWatchdog = opened.finalWatchdog;

    if (strict) {
      check('a hang leaves no watchdog armed once nothing is connecting', r.armedWhileIdleHang, 0);
      check('a refusing server leaves none either (cleared on close)', r.armedWhileIdleRefuse, 0);
      check('and an open connection leaves none (cleared on open)', r.armedWhileIdleOpen, 0);
      // A socket that resolves on its own never reaches the watchdog at all.
      check('a server that REFUSES never trips the watchdog', r.refuseTrips, 0);
      checkFn('...across a run that really did retry many times (the fixture is alive)',
        r.refuseAttempts, v => v >= 20, '>= 20 attempts in 300s');
      // 120000ms is 15x the bound: if the watchdog outlived its socket, this connection dies.
      check('a healthy connection survives far beyond the bound', r.healthyAttempts, 1);
      check('...still open, never torn down', [r.healthyOpens, r.healthyTrips], [1, 0]);
      check('...and holds no armed watchdog', r.healthyWatchdog, null);
    }
  }

  // ── E. THE BADGE SAYS WHICH FAILURE THIS IS ──────────────────────────────────
  //   Today's incident was prolonged by a badge that could not distinguish two states, and a
  //   watchdog firing is not the same as a server refusing. The attempt counter shipped in
  //   c80abf6 is the pattern being followed.
  {
    const hung = await drive(wsSrc, cfgSrc, { behaviour: ALWAYS_HANGS, horizonMs: 60000 });
    const refused = await drive(wsSrc, cfgSrc, {
      behaviour: () => ({ kind: 'refuse' }), horizonMs: 60000,
    });
    const noResponse = s => /응답 없음/.test(s);
    const disconnected = s => /DISCONNECTED/.test(s);

    r.hangSaysNoResponse = hung.badgeStates.filter(noResponse).length;
    // NOTHING EVER CLOSED IN THIS RUN. A page reporting "DISCONNECTED" for a socket that was
    // never connected and never closed is the exact ambiguity being removed — and it is also
    // what appears the moment the teardown stops detaching handlers before closing.
    r.hangSaysDisconnected = hung.badgeStates.filter(disconnected).length;
    r.hangSaysConnected = hung.badgeStates.filter(s => /CONNECTED/.test(s) && !disconnected(s)).length;
    // The other direction: a refusal must NOT borrow the watchdog's words.
    r.refuseSaysNoResponse = refused.badgeStates.filter(noResponse).length;
    r.refuseSaysDisconnected = refused.badgeStates.filter(disconnected).length;
    r.hangBadgeSample = hung.badgeStates.filter(noResponse).slice(0, 3);
    r.hangBadgeOffline = hung.badgeTrace.filter(b => noResponse(b.text))
      .every(b => /offline/.test(b.cls));

    if (strict) {
      // A COUNTER, NOT A CONSTANT: the badge has to say whether retries are still running, which
      // is the half of c80abf6 that made the last report readable.
      checkFn('the badge distinguishes "no response" and counts the trips',
        r.hangSaysNoResponse, v => v >= 3, '>= 3 distinct counted states');
      check('a hang never claims the connection was DISCONNECTED — it never connected',
        r.hangSaysDisconnected, 0);
      check('...and never claims it is CONNECTED', r.hangSaysConnected, 0);
      check('a REFUSING server still reads DISCONNECTED, not "no response"',
        [r.refuseSaysDisconnected, r.refuseSaysNoResponse], [1, 0]);
      check('the no-response badge is styled as a failure', r.hangBadgeOffline, true);
    }
  }

  // ── F. A WAKE SIGNAL AGAINST A STALE `CONNECTING` ────────────────────────────
  //   `wakeNow` refuses to act on a CONNECTING socket, which is right for one that is
  //   negotiating and wrong for one that has been "negotiating" for seconds. Both halves are
  //   scored, because getting either one wrong is a defect: too eager churns a live handshake,
  //   too shy makes focus and `online` no-ops for the whole bound.
  {
    // FRESH_SIGNAL_AT LANDS 100ms AFTER THE SECOND ATTEMPT, NOT 100ms AFTER PAGE LOAD.
    // At t=100 the wake THROTTLE refuses first (`wsLastWakeAt` starts at 0, so 100 - 0 < 500),
    // and a fixture that fires there scores the throttle while claiming to score the staleness
    // guard — W9 escaped exactly that way. At 9100 the throttle is long satisfied and the
    // staleness guard is the only thing that can refuse.
    const STALE_SIGNAL_AT = 3000;
    const FRESH_SIGNAL_AT = 9100;
    const woken = await drive(wsSrc, cfgSrc, {
      behaviour: ALWAYS_HANGS, horizonMs: 60000, startVisible: false,
      signals: [{ at: STALE_SIGNAL_AT, type: 'visible' }],
    });
    r.wokeAStaleConnecting = woken.attempts.includes(STALE_SIGNAL_AT);
    r.attemptsAtWakeInstant = woken.attempts.filter(t => t === STALE_SIGNAL_AT).length;
    r.wokenMaxRetryPending = woken.maxRetryPending;

    const online = await drive(wsSrc, cfgSrc, {
      behaviour: ALWAYS_HANGS, horizonMs: 60000,
      signals: [{ at: STALE_SIGNAL_AT, type: 'online' }],
    });
    r.onlineWokeAStaleConnecting = online.attempts.includes(STALE_SIGNAL_AT);

    // The other half. The second attempt begins at TIMEOUT + BASE, so at FRESH_SIGNAL_AT that
    // socket has been CONNECTING for 100ms — 10x under WS_CONNECT_STALE_MS and ~24x over the
    // slowest real handshake. That is a live negotiation, and it must be left alone rather than
    // replaced by a second socket.
    const fresh = await drive(wsSrc, cfgSrc, {
      behaviour: ALWAYS_HANGS, horizonMs: 60000, startVisible: false,
      signals: [{ at: FRESH_SIGNAL_AT, type: 'visible' }],
    });
    r.disturbedAFreshConnecting = fresh.attempts.includes(FRESH_SIGNAL_AT);
    r.freshFirstTwoAttempts = fresh.attempts.slice(0, 2);

    // And the throttle still governs, so a hang plus frantic alt-tabbing is not a retry loop.
    const spam = await drive(wsSrc, cfgSrc, {
      behaviour: ALWAYS_HANGS, horizonMs: 30000,
      signals: Array.from({ length: 200 }, (_, i) => ({ at: 5000 + i * 10, type: 'visible' })),
    });
    r.attemptsUnderSignalSpam = spam.attempts.length;
    r.spamMaxRetryPending = spam.maxRetryPending;

    if (strict) {
      check('regaining focus breaks a socket that has been CONNECTING for seconds',
        r.wokeAStaleConnecting, true);
      check('...opening exactly one socket, not two', r.attemptsAtWakeInstant, 1);
      check('...and never leaving two retries queued', r.wokenMaxRetryPending, 1);
      check('the `online` event does the same', r.onlineWokeAStaleConnecting, true);
      // The guard rail on all of the above.
      check('a socket that is negotiating RIGHT NOW is left alone',
        r.disturbedAFreshConnecting, false);
      check('...so that run still shows the watchdog doing the work instead',
        r.freshFirstTwoAttempts, [0, TIMEOUT + BASE]);
      checkFn('200 rapid focus events against a hang do not become 200 attempts',
        r.attemptsUnderSignalSpam, v => v <= 25, '<= 25 attempts');
      check('...and never queue a second retry', r.spamMaxRetryPending, 1);
    }
  }

  // ── G. THE BOUND IS THE NUMBER IT IS ARGUED TO BE ────────────────────────────
  //   A bound is only defensible relative to the measurements, so the measurements are asserted
  //   against directly. Behaviour checks alone would accept a 100ms bound in a world where the
  //   fixtures happened not to include a slow connect.
  {
    r.headroomOverStartup = TIMEOUT / MEASURED_STARTUP_MAX_MS;
    r.headroomOverHandshake = TIMEOUT / MEASURED_HANDSHAKE_MAX_MS;
    r.staleHeadroomOverHandshake = STALE / MEASURED_HANDSHAKE_MAX_MS;

    if (strict) {
      checkFn('the bound clears the slowest real latency on this stack with room to spare',
        r.headroomOverStartup, v => v >= 2, `>= 2x the measured ${MEASURED_STARTUP_MAX_MS}ms startup max`);
      checkFn('...and is enormous next to a real handshake', r.headroomOverHandshake,
        v => v >= 500, `>= 500x the measured ${MEASURED_HANDSHAKE_MAX_MS}ms handshake max`);
      // The other side of the trade: the bound is dead time the user stares at.
      checkFn('the bound is not so generous that the hang stays a user-visible outage',
        TIMEOUT, v => v <= 15000, '<= 15000ms');
      checkFn('the wake staleness window clears a real handshake by orders of magnitude',
        r.staleHeadroomOverHandshake, v => v >= 100,
        `>= 100x the measured ${MEASURED_HANDSHAKE_MAX_MS}ms handshake max`);
      // If the wake could not act before the watchdog, the stale-CONNECTING branch is dead code.
      checkFn('a wake signal can act well before the watchdog would', STALE, v => v < TIMEOUT / 2,
        `< ${TIMEOUT / 2}ms (half the bound)`);
    }
  }

  return r;
}

// ── Baseline ────────────────────────────────────────────────────────────────────
console.log('=== BASELINE ===');
const base = await runChecks(WS0, CFG0, { strict: true });
console.log(`  bound ${base.timeout}ms | wake-stale ${base.stale}ms | a permanent hang now yields `
  + `${base.hangAttempts} attempts / ${base.hangTrips} trips in 300s (unpatched: 1 / 0)`);
console.log(`  badge states on a hang: ${JSON.stringify(base.hangBadgeSample)}`);
console.log(`  ${pass} passed, ${fail} failed`);
if (fail > 0) {
  console.error(`BASELINE RED — ${fail} failed: ${failures.join(' | ')}`);
  console.log(`ASSERTIONS ${pass + fail} ${fail}`);
  process.exit(1);
}

// ── Mutants (must be CAUGHT) / controls (must ESCAPE) ───────────────────────────
const MUTATIONS = [
  {
    name: 'W1 [HIGH] the watchdog is never armed — the production hang comes straight back',
    file: 'ws',
    find: `  // Armed before the handlers are attached, so the attempt is never in flight unwatched.
  armConnectWatchdog(state.ws);`,
    repl: `  /* mutant: nothing bounds the attempt */;`,
    breaks: 'a socket that never resolves is failed and retried',
  },
  {
    name: 'W2 [HIGH] the teardown closes without detaching, so the real onclose races it',
    file: 'ws',
    // `sock.` rather than `state.ws.`: the identical five lines exist in `initWebSocket`'s
    // replacement path against `state.ws`, and an anchor that matched both would be refused.
    find: `    sock.onopen = null;
    sock.onclose = null;
    sock.onerror = null;
    sock.onmessage = null;
    sock.close();`,
    repl: `    sock.close();`,
    breaks: 'the badge keeps saying WHY the attempt died instead of being overwritten',
  },
  {
    name: 'W3 [HIGH] the watchdog is not cleared on open — the timer outlives its socket',
    file: 'ws',
    find: `    clearConnectWatchdog();   // reached OPEN — the bound has been met, disarm before anything else`,
    repl: `    /* mutant: the watchdog outlives the open */;`,
    breaks: 'no watchdog is left armed once a connection is established',
  },
  {
    name: 'W4 [HIGH] the watchdog is not cleared on close — one leaks per failed attempt',
    file: 'ws',
    find: `    clearConnectWatchdog();   // the attempt resolved on its own — this timer has nothing left to do`,
    repl: `    /* mutant: the watchdog outlives the close */;`,
    breaks: 'no watchdog is left armed after a socket resolves on its own',
  },
  {
    name: 'W5 [HIGH] the teardown queues no retry, so the ladder still never advances',
    file: 'ws',
    // ANCHORED THROUGH THE LOG LINE BELOW IT. Bare `const waitMs = scheduleReconnect();` occurs
    // TWICE in websocket.js — here and in `onclose` — and `applyOnce` refused it, which is the
    // whole point of that refusal: taking the first match would have scored the close path while
    // claiming to score the watchdog.
    find: `    const waitMs = scheduleReconnect();
    console.warn(\`[WebSocket] connect watchdog trip \${state.wsWatchdogTrips} \``,
    repl: `    const waitMs = 0;
    console.warn(\`[WebSocket] connect watchdog trip \${state.wsWatchdogTrips} \``,
    breaks: 'a torn-down attempt is handed to the backoff ladder',
  },
  {
    name: 'W6 [HIGH] the bound collapses, killing connects that were about to succeed',
    file: 'cfg',
    find: `export const WS_CONNECT_TIMEOUT_MS = 8000;`,
    repl: `export const WS_CONNECT_TIMEOUT_MS = 100;`,
    breaks: 'a slow-but-real connect is never killed',
  },
  {
    name: 'W7 [HIGH] the bound becomes effectively infinite — the hang returns',
    file: 'cfg',
    find: `export const WS_CONNECT_TIMEOUT_MS = 8000;
// How long a socket must have been CONNECTING before a WAKE SIGNAL is allowed to abandon it.`,
    repl: `export const WS_CONNECT_TIMEOUT_MS = 86400000;
// How long a socket must have been CONNECTING before a WAKE SIGNAL is allowed to abandon it.`,
    breaks: 'the bound is short enough for the hang to be a bounded outage',
  },
  {
    name: 'W8 [HIGH] a wake signal can never break a stale CONNECTING (the shipped refusal)',
    file: 'cfg',
    find: `export const WS_CONNECT_STALE_MS = 1000;`,
    repl: `export const WS_CONNECT_STALE_MS = 86400000;`,
    breaks: 'focus and `online` can break a socket stuck in CONNECTING',
  },
  {
    name: 'W9 [MEDIUM] a wake signal churns a socket that is negotiating right now',
    file: 'ws',
    find: `  if (readyState === 0 && stuckMs < WS_CONNECT_STALE_MS) return false;   // negotiating right now`,
    repl: `  if (readyState === 0 && stuckMs < 0) return false;`,
    breaks: 'a live handshake is left alone rather than replaced by a second socket',
  },
  {
    name: 'W10 [HIGH] the badge stops distinguishing a hang from a server refusing',
    file: 'ws',
    find: `    elements.wsStatus.textContent = \`WS: 응답 없음 \${state.wsWatchdogTrips}회\`;`,
    repl: `    elements.wsStatus.textContent = 'WS: DISCONNECTED';`,
    breaks: 'the badge names the failure the watchdog found',
  },
  {
    name: 'W11 [MEDIUM] the trip counter never advances, so the badge cannot show progress',
    file: 'ws',
    find: `    state.wsWatchdogTrips += 1;`,
    repl: `    ;`,
    breaks: 'the badge counts the trips the way the attempt counter counts attempts',
  },
  {
    name: 'W12 [MEDIUM] the watchdog is armed but its handle is dropped, so nothing can cancel it',
    file: 'ws',
    find: `  state.wsConnectWatchdog = setTimeout(() => {`,
    repl: `  setTimeout(() => {`,
    breaks: 'the watchdog is cancellable, so it can be cleared on open and on close',
  },
];

const CONTROLS = [
  {
    // DECLARED A CONTROL, NOT A MUTATION, because nothing can catch it and saying otherwise
    // would give this file a permanent hole it reported as coverage. Every exit from CONNECTING
    // disarms the timer via `clearConnectWatchdog`, and `clearTimeout` removes it from the queue
    // outright — so the callback is unreachable against a socket that is stale or resolved. It
    // is kept because a future edit that misses one clearing site turns this guard into the only
    // thing standing between a leaked timer and a killed live connection. (Same reasoning as
    // control C3 in `ws_reconnect_backoff_harness.mjs`.)
    name: 'K1 control: the watchdog callback\'s defence-in-depth guard is currently unreachable',
    file: 'ws',
    find: `    if (state.ws !== sock || sock.readyState !== 0) return;`,
    repl: `    if (false) return;`,
  },
  {
    // Also equivalent, and worth recording: `initWebSocket`'s replacement path nulls `state.ws`
    // on entry anyway, so clearing it here is redundant with that. It stays because leaving a
    // closed socket in `state.ws` makes `wakeNow`'s readyState read depend on a socket nobody
    // owns any more.
    name: 'K2 control: nulling state.ws in the teardown is redundant with the replacement path',
    file: 'ws',
    find: `  state.ws = null;
  console.warn(\`[WebSocket] \${reason} — abandoning the attempt.\`);`,
    repl: `  console.warn(\`[WebSocket] \${reason} — abandoning the attempt.\`);`,
  },
  {
    name: 'K3 control: a comment-only edit above the bound in config.js',
    file: 'cfg',
    find: `// ── The connect watchdog ─────`,
    repl: `// MUTANT-CONTROL: this comment changes nothing. ── The connect watchdog ─────`,
  },
  {
    name: 'K4 control: a consistent local rename inside armConnectWatchdog',
    file: 'ws',
    find: `function armConnectWatchdog(sock) {
  clearConnectWatchdog();
  state.wsConnectingSince = Date.now();`,
    repl: `function armConnectWatchdog(pendingSocket) {
  const sock = pendingSocket;
  clearConnectWatchdog();
  state.wsConnectingSince = Date.now();`,
  },
];

function countOf(s, needle) {
  let n = 0, i = -1;
  while ((i = s.indexOf(needle, i + 1)) >= 0) n++;
  return n;
}
function applyOnce(src, find, repl) {
  const n = countOf(src, find);
  if (n !== 1) return { ok: false, why: `search string occurs ${n} time(s), needs exactly 1`, src };
  const out = src.replace(find, repl);
  if (out === src) return { ok: false, why: 'replacement was a no-op', src };
  return { ok: true, src: out };
}

async function sweep(list, expectCaught, heading) {
  console.log(`\n=== ${heading} ===`);
  let applied = 0, caught = 0;
  const notApplied = [], wrong = [];
  for (const m of list) {
    const target = m.file === 'cfg' ? CFG0 : WS0;
    const a = applyOnce(target, m.find, m.repl);
    if (!a.ok) { notApplied.push(m.name); console.error(`  NOT APPLIED  ${m.name}\n    ${a.why}`); continue; }
    // CONFIRM THE MUTATED STATE, NOT MERELY THE OUTCOME. A mutation a later pass repairs proves
    // nothing, and a mutation that never landed proves less than nothing — it reads as coverage.
    if (!a.src.includes(m.repl)) {
      notApplied.push(m.name);
      console.error(`  NOT APPLIED  ${m.name}\n    the replacement is not present in the mutated text`);
      continue;
    }
    if (!m.repl.includes(m.find) && countOf(a.src, m.find) !== 0) {
      notApplied.push(m.name);
      console.error(`  NOT APPLIED  ${m.name}\n    the ORIGINAL text is still present after mutation`);
      continue;
    }
    applied++;

    const before = { pass, fail, n: failures.length };
    quiet = true;
    try {
      await runChecks(m.file === 'cfg' ? WS0 : a.src, m.file === 'cfg' ? a.src : CFG0, { strict: true });
    } catch (e) {
      failures.push(`${m.name}: threw ${e && e.message}`);
      fail++;
    }
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
      console.error(`  ${expectCaught ? 'ESCAPED' : 'WRONGLY CAUGHT'} ${m.name}\n    ${
        m.breaks ? `nothing scored: ${m.breaks}` : newFails.join(' | ')}`);
    }
  }
  return { applied, caught, notApplied, wrong };
}

const mut = await sweep(MUTATIONS, true, 'MUTATION SWEEP (these must be CAUGHT)');
const ctl = await sweep(CONTROLS, false, 'CONTROL SWEEP (these must ESCAPE)');

console.log(`\n=== SUMMARY ===`);
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
console.log('\nOK — a socket that never resolves is failed on a bound and handed to the ladder, '
  + 'and a slow-but-real connect is left alone.');
