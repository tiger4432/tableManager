// Harness — the reconnect ladder wakes the page up promptly when a LOCAL server comes back,
// and still refuses to hammer one that never does.
// Run: node client2/tests/ws_reconnect_backoff_harness.mjs   (no node_modules — vm sandbox)
//
// WHAT WAS ACTUALLY WRONG (user report 2026-08-04: "포트 비어도 소켓 켜지는거 느림").
// `onclose` scheduled `setTimeout(initWebSocket, state.wsReconnectDelay)` and then doubled the
// delay up to a 30000ms ceiling, and `state.wsReconnectDelay` was reset ONLY in `onopen`. So a
// server that had been down for about a minute left the browser pinned at a 30s interval, and
// the page then sat idle for up to 30s after the server was healthy again.
//
// THE NUMBER IS NOT AN OPINION. Measured on the live stack, 2026-08-04:
//   · server lifespan startup, n=324 real process starts in `server/server.log`:
//     median 12ms, p90 22ms, p99 195ms, max 3094ms;
//   · WebSocket handshake against the live :8080 once it is accepting: median 2.54ms, max 4.15ms;
//   · a retry against a down server costs one ECONNREFUSED: median 0.49ms, max 2.71ms.
// The client was waiting up to 30s for something ready in under a second, and `server.log`
// records the consequence: of 164 restarts where a browser reconnected, 20.7% stalled >= 5s
// and 10.4% stalled >= 25s.
//
// WHY THIS HARNESS EXECUTES RATHER THAN READS. The defect is entirely in SCHEDULING, and
// scheduling is invisible to a source-shape assertion: `Math.min(d * 2, 5000)` and
// `Math.min(d * 2, 30000)` are the same shape and differ only in the behaviour they produce
// over time. So the real `initWebSocket`/`scheduleReconnect`/`wakeNow` are sliced out of
// `websocket.js` and driven against a fake WebSocket on a VIRTUAL CLOCK. Nothing about the
// ladder is re-implemented here — re-implementing it would score this file against itself.
//
// THE FAKE SOCKET IS CALIBRATED FROM THE LIVE MEASUREMENTS ABOVE, ROUNDED UP (3ms to refuse,
// 5ms to complete a handshake) so the model never flatters the client.
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
const FAIL_MS = 3;   // rounded up from the measured 0.49ms median / 2.71ms max ECONNREFUSED
const OPEN_MS = 5;   // rounded up from the measured 2.54ms median / 4.15ms max handshake

// `rand` is injectable so the ladder can be scored two ways: with jitter pinned to its WORST
// case (rand=0 => the full rung, the true upper bound) and with it live (storm de-sync).
async function drive(wsSrc, cfgSrc, {
  serverUpAt = Infinity, horizonMs = 300000, hasTable = true,
  rand = () => 0, dropAfterMs = null, signals = [], startVisible = true,
} = {}) {
  let now = 0, seq = 0;
  const timers = [];
  const events = [];
  let openedAt = null, openCount = 0;
  const listeners = { visibilitychange: [], online: [] };
  let visibility = startVisible ? 'visible' : 'hidden';

  // TWO SCHEDULERS ON PURPOSE. `rawSchedule` is the harness's own (the fake socket's connect
  // and drop latencies); `setTimeoutFake` is the one handed to the CODE UNDER TEST, and it
  // records the delay it was asked for.
  //
  // The distinction is load-bearing. An observed attempt-to-attempt gap is NOT the scheduled
  // delay: it also contains the failed connect that preceded it (FAIL_MS) and, after a healthy
  // session, the whole time the socket was alive. Scoring the ceiling against observed gaps
  // reported 5003 > 5000 and called correct code broken — so the ladder and ceiling assertions
  // read `scheduled`, which is the quantity the ceiling is actually about.
  //
  // NOT EVERY `setTimeout` THE CODE MAKES IS A RECONNECT. Since the connect watchdog landed,
  // `initWebSocket` also arms an 8000ms timer per attempt, and counting that as a ladder rung
  // reported the ladder as `8000,1000,8000,2000,...` and failed five correct assertions
  // (`no scheduled delay ever exceeds the ceiling` against a ceiling of 5000). So every timer
  // is recorded WITH ITS ID, and the ids that were ever the live `state.wsConnectWatchdog` are
  // subtracted at read time. Identified by IDENTITY, never by its delay: classifying on
  // `ms === WS_CONNECT_TIMEOUT_MS` would silently reclassify ladder rungs the moment someone
  // tuned the two constants to the same number.
  const scheduledRaw = [];
  const watchdogIds = new Set();
  // How many reconnect timers the CODE has outstanding simultaneously. The contract is "exactly
  // one reconnect is ever queued", and that is invisible to attempt counts: a raced timer and a
  // legitimately-rescheduled one produce the same attempts, just at different instants.
  const codePending = new Set();
  let maxCodePending = 0;
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
      const up = now >= serverUpAt;
      events.push({ t: now, kind: 'attempt', up });
      if (up) {
        rawSchedule(() => {
          if (this._dead) return;
          this.readyState = 1; openedAt = now; openCount++;
          events.push({ t: now, kind: 'open' });
          this.onopen && this.onopen();
          // A flapping server: accepted, then dropped almost immediately.
          if (dropAfterMs !== null) rawSchedule(() => {
            if (this._dead) return;
            this.readyState = 3;
            events.push({ t: now, kind: 'dropped' });
            this.onclose && this.onclose();
          }, dropAfterMs);
        }, OPEN_MS);
      } else {
        rawSchedule(() => {
          if (this._dead) return;
          this.readyState = 3;
          events.push({ t: now, kind: 'refused' });
          this.onerror && this.onerror(new Error('ECONNREFUSED'));
          this.onclose && this.onclose();
        }, FAIL_MS);
      }
    }
    close() { this._dead = true; this.readyState = 3; }
  }

  const badge = { textContent: '', className: '' };
  const badgeTrace = [];
  const calls = { checkServerHealth: 0, loadTables: 0, fetchData: [] };
  const listenerAdds = { document: 0, window: 0 };

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
    state: {
      ws: null, wsReconnectDelay: cfgNumber(cfgSrc, 'WS_RECONNECT_BASE_MS'),
      wsRetryTimer: null, wsOpenedAt: 0,
      wsPrevReconnectDelay: cfgNumber(cfgSrc, 'WS_RECONNECT_BASE_MS'),
      wsLastWakeAt: 0, wsWakeSignalsInstalled: false,
      // The connect watchdog's state. This harness's fake socket always resolves in single-digit
      // milliseconds, so the watchdog never trips here — the hang it exists for is scored in
      // `ws_connect_watchdog_harness.mjs`. These fields are present because the sliced code
      // reads and writes them, not because this file measures them.
      wsConnectWatchdog: null, wsConnectingSince: 0, wsWatchdogTrips: 0,
      currentTable: hasTable ? 'bonding_map' : '', pageCache: new Map(),
    },
    elements: { get wsStatus() { return badge; }, tableSelect: { value: hasTable ? 'bonding_map' : '' } },
    document: {
      querySelector: () => ({ classList: { add() {}, remove() {} } }),
      addEventListener: (ev, f) => { listenerAdds.document++; (listeners[ev] || (listeners[ev] = [])).push(f); },
      get visibilityState() { return visibility; },
    },
    window: {
      addEventListener: (ev, f) => { listenerAdds.window++; (listeners[ev] || (listeners[ev] = [])).push(f); },
    },
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

  const flush = () => new Promise(r => setImmediate(r));
  // Sampled at every point where the code is at rest, which is where an invariant like "exactly
  // one reconnect is queued" is actually meaningful. `noteWatchdog` must run FIRST so the timer
  // armed during the step just taken is already excluded when the retry count is read.
  const sample = () => {
    if (sandbox.state.wsConnectWatchdog !== null) watchdogIds.add(sandbox.state.wsConnectWatchdog);
    const retries = [...codePending].filter(id => !watchdogIds.has(id)).length;
    if (retries > maxCodePending) maxCodePending = retries;
  };
  const pending = [...signals].sort((a, b) => a.at - b.at);
  sandbox.__go();
  await flush();
  sample();

  let guard = 0;
  while (now <= horizonMs && guard++ < 200000) {
    const nextTimer = timers.length ? Math.min(...timers.map(t => t.at)) : Infinity;
    const nextSignal = pending.length ? pending[0].at : Infinity;
    if (nextTimer === Infinity && nextSignal === Infinity) break;
    // THE HORIZON IS A WALL, NOT A LOOP CONDITION. Checking `now <= horizonMs` at the top of
    // the loop only tests where the clock ALREADY is, so a timer scheduled far beyond the
    // horizon still fired and dragged `now` with it. That silently rescued a bad fixture: a
    // "healthy session" 10.8M ms long ran to completion inside a 120s horizon and made the
    // flap guard look correct under a mutation that had broken it.
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
    badgeTrace.push({ t: now, text: badge.textContent });
    t.fn();
    await flush();
    sample();
  }
  const scheduled = scheduledRaw.filter(s => !watchdogIds.has(s.id)).map(s => s.ms);
  return {
    events, calls, openedAt, openCount, badgeTrace, listenerAdds, scheduled, maxCodePending,
    attempts: events.filter(e => e.kind === 'attempt').map(e => e.t),
    finalDelay: sandbox.state.wsReconnectDelay,
    finalTimer: sandbox.state.wsRetryTimer,
  };
}

// ── The checks ──────────────────────────────────────────────────────────────────
async function runChecks(wsSrc, cfgSrc, { strict = true } = {}) {
  const r = {};
  const CEIL = cfgNumber(cfgSrc, 'WS_RECONNECT_CEILING_MS');
  const BASE = cfgNumber(cfgSrc, 'WS_RECONNECT_BASE_MS');
  r.ceiling = CEIL;
  r.base = BASE;

  // ── A. THE WAKE-UP GAP, WHICH IS THE WHOLE COMPLAINT ─────────────────────────
  //   Swept over many instants at which the server could become ready, because the gap depends
  //   entirely on WHERE in the ladder the restart lands. A single sample is worthless here: a
  //   restart landing exactly on a retry instant reads ~5ms even under a 30s ceiling.
  //   Jitter is pinned to its worst case (rand=0 => full rung) so this measures the true bound.
  {
    const gaps = [];
    for (let T = 0; T <= 120000; T += 1000) {
      const run = await drive(wsSrc, cfgSrc, { serverUpAt: T, horizonMs: T + 400000 });
      gaps.push(run.openedAt - T);
    }
    r.worstGap = Math.max(...gaps);
    gaps.sort((a, b) => a - b);
    r.medianGap = gaps[gaps.length >> 1];
    r.gapsOver5s = gaps.filter(g => g >= 5000).length;
    r.gapsOver10s = gaps.filter(g => g >= 10000).length;
    r.sampleCount = gaps.length;

    if (strict) {
      // THE HEADLINE BOUND. A local server that is ready must not leave the page dark longer
      // than the ceiling (plus the one handshake it then has to do).
      checkFn('worst observed wake-up gap stays within the declared ceiling',
        r.worstGap, v => v <= CEIL + OPEN_MS + FAIL_MS,
        `<= ${CEIL + OPEN_MS + FAIL_MS}ms (ceiling ${CEIL} + handshake)`);
      // The ceiling is only a bound; assert the number it is actually set to, so raising it
      // back to an internet-scale value is a red build and not a silent regression.
      checkFn('the ceiling is a LOCAL-service number, not an internet-scale one',
        CEIL, v => v <= 8000, '<= 8000ms');
      checkFn('no sampled restart instant stalls 10s or more',
        r.gapsOver10s, v => v === 0, '0 of the sampled instants');
      checkFn('the median wake-up gap is small',
        r.medianGap, v => v <= CEIL, `<= ${CEIL}ms`);
      checkFn('the sweep actually sampled a spread of restart instants (fixture is alive)',
        r.sampleCount, v => v >= 100, '>= 100 samples');
    }
  }

  // ── B. THE BACKOFF STILL EXISTS ──────────────────────────────────────────────
  //   The fix must not become "retry at a fixed short interval forever". A server that never
  //   comes back has to be probed on a RISING interval that then holds at the ceiling.
  {
    const run = await drive(wsSrc, cfgSrc, { serverUpAt: Infinity, horizonMs: 300000 });
    const d = run.scheduled;               // what the code ASKED for, jitter pinned to worst case
    r.ladder = d.slice(0, 6);
    r.maxGap = Math.max(...d);
    r.steadyGap = d[d.length - 1];
    r.attemptsIn300s = run.attempts.length;
    r.ladderRises = d.slice(0, 4).every((g, i) => i === 0 || g > d[i - 1]);
    r.neverExceedsCeiling = d.every(g => g <= CEIL);

    if (strict) {
      check('the first retry is at the base delay', r.ladder[0], BASE);
      check('the delay grows — this is still a backoff, not a fixed interval', r.ladderRises, true);
      check('no scheduled delay ever exceeds the ceiling', r.neverExceedsCeiling, true);
      check('the ladder settles AT the ceiling', r.steadyGap, CEIL);
      // A down server is probed on a bounded budget. Stated as a range: too few means the stall
      // came back, too many means the backoff stopped protecting the server.
      checkFn('a permanently-down server is probed on a bounded budget over 5 minutes',
        r.attemptsIn300s, v => v >= 20 && v <= 400, 'between 20 and 400 attempts in 300s');
    }
  }

  // ── C. `onopen` RESETS THE LADDER ────────────────────────────────────────────
  //   The reset is the only thing keeping a healthy session off a stale interval.
  {
    const run = await drive(wsSrc, cfgSrc, { serverUpAt: 100000, horizonMs: 400000 });
    r.delayAfterOpen = run.finalDelay;
    r.refusalsBeforeOpen = run.events.filter(e => e.kind === 'refused').length;
    r.noTimerLeftPending = run.finalTimer === null;
    if (strict) {
      check('after a successful open the delay is back at the base', r.delayAfterOpen, BASE);
      // Fixture activity: if the ladder had NOT climbed first, the reset would be vacuous.
      checkFn('...and the ladder had genuinely climbed before it (the fixture is not self-satisfying)',
        r.refusalsBeforeOpen, v => v >= 4, '>= 4 refused attempts before the open');
      check('no reconnect timer is left pending once connected', r.noTimerLeftPending, true);
    }
  }

  // ── D. THE RECONNECT DATA RELOAD ─────────────────────────────────────────────
  //   `fetchData(true)` exists because deltas are missed while offline. Faster reconnects make
  //   it fire more often, so what matters is that it fires ONLY on success and exactly once.
  {
    const run = await drive(wsSrc, cfgSrc, { serverUpAt: 100000, horizonMs: 400000 });
    r.fetchCalls = run.calls.fetchData.length;
    r.fetchResetFlag = run.calls.fetchData.map(c => c.reset);
    r.healthCalls = run.calls.checkServerHealth;
    r.failedAttempts = run.events.filter(e => e.kind === 'refused').length;
    const noTable = await drive(wsSrc, cfgSrc, { serverUpAt: 100000, horizonMs: 400000, hasTable: false });
    r.fetchWithoutTable = noTable.calls.fetchData.length;
    r.loadTablesWithoutTable = noTable.calls.loadTables;

    if (strict) {
      check('the reconnect reload fires exactly once per successful reconnect', r.fetchCalls, 1);
      check('...and it is the resetting form, which is why the missed deltas are recovered',
        r.fetchResetFlag, [true]);
      // The load-bearing half: a FAILED attempt must not pay for a data reload.
      check('a failed connection attempt triggers no data reload at all',
        r.fetchCalls - 1, 0);
      checkFn('...and the run really did contain failed attempts (the fixture is alive)',
        r.failedAttempts, v => v >= 4, '>= 4 refused attempts');
      check('health is checked once, on the open', r.healthCalls, 1);
      check('with no table selected it loads the table list instead of reloading rows',
        [r.fetchWithoutTable, r.loadTablesWithoutTable], [0, 1]);
    }
  }

  // ── E. THE STATUS BADGE TELLS THE TRUTH ──────────────────────────────────────
  //   A page that is retrying is not a page that is connected, and it must not read as
  //   connected while a socket is merely pending.
  {
    const run = await drive(wsSrc, cfgSrc, { serverUpAt: 100000, horizonMs: 400000 });
    const isConnected = s => /CONNECTED/.test(s) && !/DISCONNECTED/.test(s);
    r.connectedBeforeOpen = run.badgeTrace.filter(b => b.t < run.openedAt && isConnected(b.text)).length;
    r.badgeStatesSeen = [...new Set(run.badgeTrace.map(b => b.text))].filter(Boolean);
    r.badgeSaidDisconnected = r.badgeStatesSeen.some(s => /DISCONNECTED/.test(s));
    if (strict) {
      check('the badge never reads CONNECTED while a socket is only pending', r.connectedBeforeOpen, 0);
      check('the badge does say DISCONNECTED while retrying', r.badgeSaidDisconnected, true);
    }
  }

  // ── F. WAKING ON A SIGNAL ────────────────────────────────────────────────────
  //   The common case: someone restarts the server, then looks at the page. Regaining focus
  //   must collapse the remaining wait instead of racing it.
  {
    // The tab is focused 100ms after the server comes back, while the ladder is at its ceiling
    // and the queued retry is still seconds away. (The earlier 61s/70s pair was written against
    // the OLD 30s ceiling and is stale: under a 5s ceiling the timer already won at 70s, which
    // showed up as a NEGATIVE wake gap.)
    const READY_AT = 60000, SIGNAL_AT = 60100;
    const woken = await drive(wsSrc, cfgSrc, {
      serverUpAt: READY_AT, horizonMs: 400000, startVisible: false,
      signals: [{ at: SIGNAL_AT, type: 'visible' }],
    });
    r.wakeGapOnSignal = woken.openedAt - SIGNAL_AT;

    const notWoken = await drive(wsSrc, cfgSrc, { serverUpAt: READY_AT, horizonMs: 400000 });
    r.gapWithoutSignal = notWoken.openedAt - READY_AT;

    const online = await drive(wsSrc, cfgSrc, {
      serverUpAt: READY_AT, horizonMs: 400000,
      signals: [{ at: SIGNAL_AT, type: 'online' }],
    });
    r.wakeGapOnOnline = online.openedAt - SIGNAL_AT;

    // A signal while the socket is HEALTHY must not churn the connection.
    const healthy = await drive(wsSrc, cfgSrc, {
      serverUpAt: 0, horizonMs: 60000,
      signals: [{ at: 10000, type: 'visible' }, { at: 20000, type: 'online' },
                { at: 30000, type: 'visible' }],
    });
    r.opensWhileHealthy = healthy.openCount;
    r.attemptsWhileHealthy = healthy.attempts.length;

    // Rapid alt-tabbing must not become an unthrottled retry loop.
    const spam = await drive(wsSrc, cfgSrc, {
      serverUpAt: Infinity, horizonMs: 30000,
      signals: Array.from({ length: 200 }, (_, i) => ({ at: 5000 + i * 10, type: 'visible' })),
    });
    r.attemptsUnderSignalSpam = spam.attempts.length;

    // Listeners are attached once for the life of the page, not once per reconnect.
    const many = await drive(wsSrc, cfgSrc, { serverUpAt: Infinity, horizonMs: 120000 });
    r.listenerAdds = many.listenerAdds.document + many.listenerAdds.window;
    r.reconnectsInThatRun = many.attempts.length;

    // A wake signal arriving mid-wait must REPLACE the queued retry, not run alongside it.
    // t=19000 sits between the ladder's 17015 and 22018 attempts, so a retry really is pending.
    const raced = await drive(wsSrc, cfgSrc, {
      serverUpAt: Infinity, horizonMs: 60000, signals: [{ at: 19000, type: 'visible' }],
    });
    r.maxQueuedAcrossSignal = raced.maxCodePending;
    r.queuedDuringPlainRun = notWoken.maxCodePending;
    // The concurrent-timer count alone does NOT see a raced timer here, because
    // `scheduleReconnect`'s re-entry guard declines to queue a second one — so the stale timer
    // simply survives and fires at ITS old instant. What that looks like is a ladder that was
    // never really restarted, so THAT is what gets measured: the attempt after the wake must
    // land one base delay later, not wherever the pre-wake schedule had put it.
    const wakeIdx = raced.attempts.findIndex(t => t >= 19000);
    r.attemptAtWake = wakeIdx >= 0 ? raced.attempts[wakeIdx] : null;
    r.gapAfterWake = (wakeIdx >= 0 && raced.attempts[wakeIdx + 1] !== undefined)
      ? raced.attempts[wakeIdx + 1] - raced.attempts[wakeIdx] : null;

    if (strict) {
      check('a wake signal replaces the queued retry instead of racing it — one timer, never two',
        r.maxQueuedAcrossSignal, 1);
      check('...and an ordinary run never queues two either', r.queuedDuringPlainRun, 1);
      check('the wake really does retry at the moment of the signal', r.attemptAtWake, 19000);
      checkFn('...and the ladder restarts from the base after it, rather than the stale schedule '
        + 'surviving', r.gapAfterWake, v => v !== null && v <= BASE + 50,
        `<= ${BASE + 50}ms after the wake attempt`);
      checkFn('regaining focus reconnects promptly instead of waiting out the backoff',
        r.wakeGapOnSignal, v => v >= 0 && v <= 100, '<= 100ms after the signal');
      checkFn('the `online` event does the same', r.wakeGapOnOnline, v => v >= 0 && v <= 100,
        '<= 100ms after the signal');
      // FIXTURE ACTIVITY. Without this the wake check could pass simply because the timer was
      // about to fire anyway — the signal must be doing the work.
      checkFn('...and without the signal that same restart really would have stalled',
        r.gapWithoutSignal, v => v > 1000, '> 1000ms, i.e. the signal was load-bearing');
      check('signals on a healthy socket do not churn the connection', r.opensWhileHealthy, 1);
      check('...and open no extra sockets', r.attemptsWhileHealthy, 1);
      // 200 events over 2s, throttled at WS_WAKE_MIN_GAP_MS, plus the ordinary ladder over the
      // 30s window. The bound is what makes 200-in-becomes-200-out impossible, not a tight fit.
      checkFn('200 rapid focus events do not become 200 connection attempts',
        r.attemptsUnderSignalSpam, v => v <= 25, '<= 25 attempts');
      check('the wake listeners are installed exactly once for the page', r.listenerAdds, 2);
      checkFn('...across a run that reconnected many times (the latch is being exercised)',
        r.reconnectsInThatRun, v => v >= 5, '>= 5 attempts in that run');
    }
  }

  // ── G. THE FLAP GUARD ────────────────────────────────────────────────────────
  //   A server that ACCEPTS and immediately drops is the one case where `onopen`'s
  //   unconditional reset turns the backoff off: each cycle would cost a full handshake plus
  //   `checkServerHealth()` plus `fetchData(true)`, forever, at the base delay.
  {
    const flap = await drive(wsSrc, cfgSrc, { serverUpAt: 0, horizonMs: 120000, dropAfterMs: 10 });
    r.flapAttempts = flap.attempts.length;
    r.flapFetches = flap.calls.fetchData.length;
    r.flapMaxGap = flap.scheduled.length ? Math.max(...flap.scheduled) : 0;
    r.flapLastGap = flap.scheduled.length ? flap.scheduled[flap.scheduled.length - 1] : 0;

    // The mirror: a HEALTHY session that ends must still get the fast retry.
    //
    // 5000ms is a FIXED number and deliberately not `WS_HEALTHY_SESSION_MS * 3`. Deriving the
    // fixture from the constant under mutation made the fixture scale with the mutant, so
    // raising the threshold to an hour moved the "healthy" session to three hours and the
    // check could never fail. A fixture must be anchored to the real world (a 5s session is
    // healthy by any reasonable reading), not to the value it is scoring.
    // THE LADDER MUST HAVE CLIMBED FIRST. With `serverUpAt: 0` the socket opens on the very
    // first attempt, so the rung at open is still the base — and the flap guard's "restore the
    // previous rung" is then indistinguishable from "reset to base", whichever is wrong. The
    // server therefore stays down until 30s so the ladder is at its ceiling when the healthy
    // session begins.
    const HEALTHY_SESSION_FIXTURE_MS = 5000;
    const healthy = await drive(wsSrc, cfgSrc, {
      serverUpAt: 30000, horizonMs: 120000, dropAfterMs: HEALTHY_SESSION_FIXTURE_MS,
    });
    // Measured as the LAST delay the code scheduled — i.e. the one that follows a healthy
    // session's close, not the ladder climb that preceded it. An attempt-to-attempt gap would
    // also contain the entire lifetime of the session, which is why this first read 4005ms and
    // looked like a defect in the guard.
    r.healthyRetryGap = healthy.scheduled.length ? healthy.scheduled[healthy.scheduled.length - 1] : null;
    r.healthyLadderDidClimb = healthy.scheduled.some(d => d >= CEIL);

    if (strict) {
      checkFn('a flapping server backs off instead of being hammered at the base delay',
        r.flapLastGap, v => v >= CEIL * 0.7, `>= ${Math.round(CEIL * 0.7)}ms by the end`);
      checkFn('...so the per-cycle data reload is bounded too',
        r.flapFetches, v => v <= 40, '<= 40 reloads in 120s of flapping');
      // The mirror. The guard must not punish a genuinely healthy session that simply ended.
      checkFn('a session that WAS healthy still gets the fast first retry when it ends',
        r.healthyRetryGap, v => v !== null && v <= BASE + 20, `<= ${BASE + 20}ms`);
      // Without this the check above passes vacuously: if the ladder never climbed, "reset to
      // base" and "restore the previous rung" are the same number.
      check('...and the ladder had climbed to the ceiling before that session (fixture is alive)',
        r.healthyLadderDidClimb, true);
    }
  }

  // ── H. MANY TABS DO NOT RETRY IN LOCKSTEP ────────────────────────────────────
  //   A reconnect storm is a real failure mode; jitter is what prevents it. Scored with LIVE
  //   randomness (the other blocks pin it to the worst case on purpose).
  {
    const fire = [], sched = [];
    for (let tab = 0; tab < 24; tab++) {
      let s = tab * 7919 + 13;                      // deterministic per-tab stream
      const rand = () => ((s = (s * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff);
      const run = await drive(wsSrc, cfgSrc, { serverUpAt: Infinity, horizonMs: 60000, rand });
      fire.push(run.attempts);
      sched.push(run.scheduled);
    }
    // How many distinct instants does the 6th attempt land on across 24 tabs?
    const sixth = fire.map(a => a[5]).filter(v => v !== undefined);
    r.tabsMeasured = sixth.length;
    r.distinctSixthInstants = new Set(sixth).size;
    r.jitterSpreadMs = sixth.length ? Math.max(...sixth) - Math.min(...sixth) : 0;
    // And the bound must survive the jitter: no SCHEDULED delay may exceed the ceiling. Read
    // from `scheduled` for the same reason as section B — an observed attempt gap carries the
    // preceding failed connect and would report 5003 against a correct 5000.
    r.jitteredNeverExceedsCeiling = sched.every(d => d.every(g => g <= CEIL));
    r.jitterActuallyVaried = new Set(sched.flat()).size;

    if (strict) {
      checkFn('24 tabs measured (the fixture is alive)', r.tabsMeasured, v => v >= 20, '>= 20 tabs');
      checkFn('tabs do not converge on one retry instant', r.distinctSixthInstants,
        v => v >= 15, '>= 15 distinct instants out of 24 tabs');
      checkFn('...and they are spread over a meaningful window', r.jitterSpreadMs,
        v => v >= CEIL * 0.15, `>= ${Math.round(CEIL * 0.15)}ms of spread`);
      check('jitter never pushes a scheduled gap above the ceiling',
        r.jitteredNeverExceedsCeiling, true);
      // Guards the check above from passing because jitter silently stopped happening.
      checkFn('...and jitter really did vary the delays (not a constant masquerading as a bound)',
        r.jitterActuallyVaried, v => v >= 20, '>= 20 distinct scheduled delays across 24 tabs');
    }
  }

  return r;
}

// ── Baseline ────────────────────────────────────────────────────────────────────
console.log('=== BASELINE ===');
const base = await runChecks(WS0, CFG0, { strict: true });
console.log(`  ceiling ${base.ceiling}ms | ladder ${base.ladder.join(',')} | worst wake-up gap `
  + `${base.worstGap}ms | median ${base.medianGap}ms | attempts in 300s ${base.attemptsIn300s}`);
console.log(`  ${pass} passed, ${fail} failed`);
if (fail > 0) {
  console.error(`BASELINE RED — ${fail} failed: ${failures.join(' | ')}`);
  console.log(`ASSERTIONS ${pass + fail} ${fail}`);
  process.exit(1);
}

// ── Mutants (must be CAUGHT) / controls (must ESCAPE) ───────────────────────────
const MUTATIONS = [
  {
    name: 'M1 [HIGH] the ceiling goes back to the internet-scale 30s (the reported defect)',
    file: 'cfg',
    find: `export const WS_RECONNECT_CEILING_MS = 5000;`,
    repl: `export const WS_RECONNECT_CEILING_MS = 30000;`,
    breaks: 'a local server that is ready wakes the page within seconds',
  },
  {
    name: 'M2 [HIGH] the ladder stops being clamped, so it grows without bound',
    file: 'ws',
    find: `  state.wsReconnectDelay = Math.min(state.wsReconnectDelay * 2, WS_RECONNECT_CEILING_MS);`,
    repl: `  state.wsReconnectDelay = state.wsReconnectDelay * 2;`,
    breaks: 'the wait is bounded by the ceiling however long the outage lasts',
  },
  {
    name: 'M3 [HIGH] `onopen` stops resetting the ladder — a healthy session inherits a stale interval',
    file: 'ws',
    find: `    state.wsReconnectDelay = WS_RECONNECT_BASE_MS;
    state.wsOpenedAt = Date.now();`,
    repl: `    state.wsOpenedAt = Date.now();`,
    breaks: 'a reconnected session starts over at the base delay',
  },
  {
    name: 'M4 [HIGH] the reconnect data reload is dropped, so deltas missed while offline stay missed',
    file: 'ws',
    // ANCHORED ON THE COMMENT ABOVE THE CALL. Bare `      fetchData(true);` occurs TWICE in
    // websocket.js — the reconnect reload and the ingestion-completed reload — so it is exactly
    // the non-unique anchor that has twice scored the wrong function in this directory.
    find: `      // 오프라인 동안 유실된 데이터 동기화를 위해 현재 테이블 데이터 리로드
      fetchData(true);
    }`,
    repl: `      /* mutant: the reconnect reload is gone */;
    }`,
    breaks: 'a reconnect reloads the table that was on screen',
  },
  {
    name: 'M5 [HIGH] the reload is downgraded to the non-resetting form (stale cache survives)',
    file: 'ws',
    find: `      // 오프라인 동안 유실된 데이터 동기화를 위해 현재 테이블 데이터 리로드
      fetchData(true);`,
    repl: `      // 오프라인 동안 유실된 데이터 동기화를 위해 현재 테이블 데이터 리로드
      fetchData(false);`,
    breaks: 'the reconnect reload clears the page cache',
  },
  {
    // The CONNECTING half of this refusal is now conditional (a socket stuck for longer than
    // `WS_CONNECT_STALE_MS` may be broken by a wake signal — see `ws_connect_watchdog_harness`),
    // but the OPEN half is absolute and is what this scores: a working socket is never churned.
    name: 'M6 [HIGH] the wake signal fires even while a socket is OPEN (double sockets)',
    file: 'ws',
    find: `  if (readyState === 1) return false;                       // OPEN — there is no wait to shorten`,
    repl: `  if (readyState === 999) return false;`,
    breaks: 'a signal on a healthy socket does not churn the connection',
  },
  {
    name: 'M7 [HIGH] the wake throttle is removed — rapid focus events become a retry loop',
    file: 'ws',
    find: `  if (now - state.wsLastWakeAt < WS_WAKE_MIN_GAP_MS) return false;`,
    repl: `  if (now - state.wsLastWakeAt < 0) return false;`,
    breaks: 'rapid alt-tabbing cannot turn the wake signal into unthrottled retries',
  },
  {
    // Removing the cancel from `wakeNow` ALONE is an equivalent mutant: `initWebSocket` clears
    // the same handle on entry, so behaviour is unchanged (that redundancy is recorded as
    // control C3). To score the invariant rather than one of its two guards, this mutation
    // removes BOTH cancels — which is the state in which an early reconnect genuinely races
    // the queued one and leaves a second timer outstanding.
    name: 'M8 [HIGH] nothing cancels the pending timer, so an early reconnect races it',
    file: 'ws',
    find: `  if (state.wsRetryTimer !== null) {
    clearTimeout(state.wsRetryTimer);
    state.wsRetryTimer = null;
  }
  console.log(\`[WebSocket] \${reason} — reconnecting now instead of waiting out the backoff.\`);`,
    repl: `  console.log(\`[WebSocket] \${reason} — reconnecting now instead of waiting out the backoff.\`);`,
    also: {
      // Anchored through the comment line that now follows this block. The bare cancel block
      // occurs TWICE (here and in `wakeNow`), and the `if (state.ws) {` that used to disambiguate
      // it is no longer adjacent — `clearConnectWatchdog()` sits between them since the connect
      // watchdog landed. A non-unique anchor is refused by `applyOnce` rather than guessed.
      find: `  if (state.wsRetryTimer !== null) {
    clearTimeout(state.wsRetryTimer);
    state.wsRetryTimer = null;
  }

  // The outgoing socket's watchdog goes with it.`,
      repl: `  // The outgoing socket's watchdog goes with it.`,
    },
    breaks: 'an early reconnect replaces the queued retry instead of racing it',
  },
  {
    name: 'M9 [HIGH] the wake listeners are re-attached on every reconnect',
    file: 'ws',
    find: `  if (state.wsWakeSignalsInstalled) return;
  state.wsWakeSignalsInstalled = true;`,
    repl: `  if (false) return;`,
    breaks: 'the wake listeners are installed exactly once for the page',
  },
  {
    name: 'M10 [HIGH] the flap guard is removed — an accept-then-drop server is hammered forever',
    file: 'ws',
    find: `    if (openedAt && Date.now() - openedAt < WS_HEALTHY_SESSION_MS) {
      state.wsReconnectDelay = state.wsPrevReconnectDelay;
    }`,
    repl: `    if (false) { state.wsReconnectDelay = state.wsPrevReconnectDelay; }`,
    breaks: 'a flapping server backs off instead of retrying at the base delay forever',
  },
  {
    name: 'M11 [MEDIUM] the flap guard over-reaches and punishes a genuinely healthy session',
    file: 'cfg',
    find: `export const WS_HEALTHY_SESSION_MS = 1000;`,
    repl: `export const WS_HEALTHY_SESSION_MS = 3600000;`,
    breaks: 'a long healthy session still gets the fast first retry when it ends',
  },
  {
    name: 'M12 [MEDIUM] jitter is removed — many tabs retry in lockstep',
    file: 'cfg',
    find: `export const WS_RECONNECT_JITTER = 0.25;`,
    repl: `export const WS_RECONNECT_JITTER = 0;`,
    breaks: 'open tabs are de-synchronised so they cannot storm the server together',
  },
  {
    name: 'M13 [MEDIUM] jitter becomes symmetric, so the ceiling stops being a real bound',
    file: 'ws',
    find: `  const waitMs = Math.round(state.wsReconnectDelay * (1 - WS_RECONNECT_JITTER * Math.random()));`,
    repl: `  const waitMs = Math.round(state.wsReconnectDelay * (1 + WS_RECONNECT_JITTER * (2 * Math.random() - 1)));`,
    breaks: 'the declared ceiling is a true upper bound on the scheduled gap',
  },
];

const CONTROLS = [
  {
    // DECLARED A CONTROL ON PURPOSE, AFTER TRYING IT AS A MUTANT AND FAILING TO CATCH IT.
    // `scheduleReconnect`'s re-entry guard is defence-in-depth: the current call graph reaches
    // it only from `onclose`, and `initWebSocket` nulls a replaced socket's handlers before
    // closing it, so exactly one `onclose` fires per socket and the guard never trips. It is
    // kept because a second caller is a plausible future edit, and it is recorded HERE rather
    // than as an uncatchable mutation — declaring a mutation nothing can catch is how a
    // harness ends up with a permanent hole it reports as coverage.
    name: 'C3 control: the re-entry guard in scheduleReconnect is currently unreachable',
    file: 'ws',
    find: `  if (state.wsRetryTimer !== null) return 0;`,
    repl: `  if (false) return 0;`,
  },
  {
    name: 'C1 control: a comment-only edit in config.js',
    file: 'cfg',
    find: `// ── WebSocket reconnect tuning ─────`,
    repl: `// MUTANT-CONTROL: this comment changes nothing. ── WebSocket reconnect tuning ─────`,
  },
  {
    name: 'C2 control: a consistent local rename inside scheduleReconnect',
    file: 'ws',
    find: `  state.wsRetryTimer = setTimeout(() => {
    state.wsRetryTimer = null;
    initWebSocket();
  }, waitMs);`,
    repl: `  const scheduledFor = waitMs;
  state.wsRetryTimer = setTimeout(() => {
    state.wsRetryTimer = null;
    initWebSocket();
  }, scheduledFor);`,
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
    let a = applyOnce(target, m.find, m.repl);
    if (!a.ok) { notApplied.push(m.name); console.error(`  NOT APPLIED  ${m.name}\n    ${a.why}`); continue; }
    // A GUARD THAT LIVES IN TWO PLACES NEEDS BOTH SITES REMOVED, or the mutation is equivalent
    // and proves only that the redundancy is real. `also` is that second site, held to the same
    // uniqueness rule as the first. (M8 escaped for exactly this reason until it was wired up:
    // `initWebSocket` re-clears the handle that `wakeNow` had stopped clearing.)
    if (m.also) {
      const b = applyOnce(a.src, m.also.find, m.also.repl);
      if (!b.ok) {
        notApplied.push(m.name);
        console.error(`  NOT APPLIED  ${m.name}\n    second site: ${b.why}`);
        continue;
      }
      if (!b.src.includes(m.also.repl)) {
        notApplied.push(m.name);
        console.error(`  NOT APPLIED  ${m.name}\n    second site: replacement absent after edit`);
        continue;
      }
      a = b;
    }
    // Confirm the MUTATED STATE, not merely the outcome.
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
console.log('\nOK — a local server that comes back wakes the page within the ceiling, and one that never does is still backed off.');
