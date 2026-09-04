// Mock harness - effort_meter.js (V1 instrument: interaction score to completion).
// Run: node client2/tests/effort_meter_harness.mjs   (no node_modules - vm sandbox)
//
// The module is loaded into a vm sandbox rather than imported, because config.js reads
// `window.location` and `import.meta.env` at module scope and cannot run in bare Node.
// Same approach as push_gate_harness.mjs.
//
// What is under test is the set of invariants that are cheap to break and expensive to
// discover later:
//   - reset happens ONLY on success (a failed save keeps accumulating)
//   - reset happens only when the SERVER RECORDED (a no-op save must not erase the effort)
//   - an empty snapshot is ABSENT, never an all-zero blob (absence != a measured zero)
//   - snapshot() never resets
//   - counters survive a reload in the same tab
//   - the served config fails CLOSED (missing/garbage config => everything counted)
//   - an allowlist entry naming a route that does not exist is LOUD, never silently inert
//   - session id generation works in an INSECURE context (production is plain HTTP)
import { readFileSync } from 'node:fs';
import { loadWithProbe } from './lib/probe.mjs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const SRC_PATH = join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'effort_meter.js');
// Normalized to LF. The mutation patches at the bottom match on multi-line strings, and the
// file's line endings are not stable across editors on Windows — without this, a CRLF file
// makes every multi-line mutation fail to apply. (loadMutated throws in that case rather
// than reporting a false pass, but the suite should not depend on the editor of the day.)
const rawSrc = readFileSync(SRC_PATH, 'utf8').replace(/\r\n/g, '\n');

// 🔴 THE MODULE IS IMPORTED NOW, NOT REWRITTEN AND EVALUATED. This file used to strip the ESM
// plumbing out of the source text -- replace the `./config.js` import with a literal, delete
// every `export `, append an `exports.*` block -- and run the result in `vm`. That measures the
// SHAPE OF THE LETTERS: add a SECOND import to effort_meter.js and the replacement above still
// matches its one target, the new `import` survives into the vm script, and the whole harness
// dies with a SyntaxError on correct code.
//
// `API_BASE` still has to be the harness's value rather than the real one, and it is a const
// that the subject IMPORTS, so no probe can reach it. It arrives through the loader hook,
// which redirects the copy's `./config.js` and leaves every other importer of that module
// alone.
//
// The globals below are installed per load rather than handed to a sandbox, because an
// imported module resolves them the way the browser does. `console` forwards `log` to the real
// one -- a recording console installed globally would swallow this harness's own output.
const REAL_CONSOLE = console;
const REAL_CRYPTO = globalThis.crypto;

let pass = 0, fail = 0;
const failures = [];
function ok(name, cond, detail = '') {
  if (cond) { pass++; console.log(`  PASS  ${name}`); }
  else { fail++; failures.push(name); console.log(`  FAIL  ${name} ${detail}`); }
}
function eq(name, actual, expected) {
  ok(name, Object.is(actual, expected), `(got ${JSON.stringify(actual)}, want ${JSON.stringify(expected)})`);
}

// --- minimal DOM/event stub -----------------------------------------------------
function makeDocument() {
  const handlers = {};
  return {
    addEventListener(type, fn) { (handlers[type] ||= []).push(fn); },
    _fire(type, ev) { (handlers[type] || []).forEach(fn => fn(ev)); },
    _count(type) { return (handlers[type] || []).length; }
  };
}

// --- storage stub ---------------------------------------------------------------
function makeStorage({ throwOnSet = false, throwOnGet = false } = {}) {
  const map = new Map();
  return {
    getItem(k) { if (throwOnGet) throw new Error('storage blocked'); return map.has(k) ? map.get(k) : null; },
    setItem(k, v) { if (throwOnSet) throw new Error('storage blocked'); map.set(k, String(v)); },
    _raw: map
  };
}

/**
 * Instantiate the module in a fresh sandbox. `storage` is shared across instantiations
 * to simulate a page reload inside the same tab.
 */
/** Records console output so "reported loudly" can be asserted instead of assumed. */
function makeConsole() {
  const errors = [];
  const warns = [];
  const fmt = (a) => a.map(x => {
    if (typeof x === 'string') return x;
    try { return JSON.stringify(x); } catch (e) { return String(x); }
  }).join(' ');
  return { errors, warns, log() {}, warn(...a) { warns.push(fmt(a)); }, error(...a) { errors.push(fmt(a)); } };
}

async function load({ storage, cryptoImpl, fetchImpl, origin = 'http://host',
                     pathname = '/index.html' } = {}, mutate) {
  const document = makeDocument();
  const consoleStub = makeConsole();
  const location = {
    origin, pathname, href: origin + pathname, port: '', protocol: 'http:', host: 'host'
  };
  globalThis.document = document;
  globalThis.window = { location };
  globalThis.location = location;
  globalThis.sessionStorage = storage || makeStorage();
  // `globalThis.crypto` is getter-only in node 22, so a plain assignment throws. The tests
  // that hand in a broken `crypto` are scoring the module's fallback, so the substitution has
  // to actually happen -- defineProperty rather than quietly skipping it.
  Object.defineProperty(globalThis, 'crypto', {
    value: cryptoImpl === undefined ? REAL_CRYPTO : cryptoImpl,
    configurable: true, writable: true,
  });
  globalThis.fetch = fetchImpl || (() => Promise.reject(new Error('no server')));
  globalThis.console = { ...consoleStub, log: (...a) => REAL_CONSOLE.log(...a) };

  // The api is the module's OWN public surface now. The hand-written `exports.*` block this
  // replaced had to be kept in step with the module by hand -- a list that falls behind is
  // how a renamed export goes unmeasured while the harness stays green.
  const { module } = await loadWithProbe(SRC_PATH, {
    stubs: { './config.js': { API_BASE: 'http://host/api-base' } },
    mutate: mutate || undefined,
    tag: 'effort',
  });
  return { api: module, document, sandbox: { window: globalThis.window },
           errors: consoleStub.errors, warns: consoleStub.warns };
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const V4_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const okCfg = (body) => () => Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
const tick = () => new Promise(r => setImmediate(r));

console.log('\n=== 1. session id + persistence ===');
{
  const storage = makeStorage();
  const { api } = await load({ storage });
  const id = api.startSession();
  ok('startSession returns a UUID-shaped id', UUID_RE.test(id), `(got ${id})`);
  eq('startSession is idempotent', api.startSession(), id);
  ok('persisted to sessionStorage', storage._raw.has('assy.effort'));

  api.countKey(3); api.countMouse(2);
  // Simulate a reload in the same tab: brand new module instance, same storage.
  const { api: api2 } = await load({ storage });
  const s = api2.snapshot();
  eq('session_id survives reload', s.session_id, id);
  eq('key count survives reload', s.key, 3);
  eq('mouse count survives reload', s.mouse, 2);
}

console.log('\n=== 2. counting + snapshot must not reset ===');
{
  const { api } = await load({});
  api.startSession();
  api.countKey(); api.countKey(); api.countMouse();
  eq('key=2', api.snapshot().key, 2);
  eq('mouse=1', api.snapshot().mouse, 1);
  eq('snapshot did NOT reset (2nd read identical)', api.snapshot().key, 2);
  eq('snapshot did NOT reset mouse', api.snapshot().mouse, 1);
  api.countKey(5);
  eq('countKey(n) adds n', api.snapshot().key, 7);
  api.countKey(0); api.countKey(-4); api.countKey('x');
  eq('non-positive / garbage increments ignored', api.snapshot().key, 7);
}

console.log('\n=== 2b. an empty snapshot is ABSENT, not a measured zero (F2) ===');
{
  // The server accepts an explicit zero as a MEASURED score-0 correction, on purpose. So a
  // save carrying no accumulated interaction files a genuine score of 0 and drags the
  // baseline down with a phantom (measured: one real score-37 correction + one of these in
  // the same session => avg_score 18.5). Absence is the contract's own "not measured".
  const { api } = await load({});
  api.startSession();
  eq('nothing accumulated => snapshot() is undefined', api.snapshot(), undefined);

  // This is the exact shape every call site writes. The KEY must vanish from the wire —
  // not be null, not be zeros.
  const body = JSON.stringify({ updates: [], effort: api.snapshot() });
  const parsed = JSON.parse(body);
  ok('`effort` key is absent from the JSON body', !('effort' in parsed), `(body was ${body})`);
  ok('  ...and the rest of the body is untouched', Array.isArray(parsed.updates));

  api.countKey(1);
  const withOne = JSON.parse(JSON.stringify({ effort: api.snapshot() }));
  eq('one keystroke => reported again', withOne.effort.key, 1);
  eq('  ...carrying the session id', typeof withOne.effort.session_id, 'string');

  api.commit();
  eq('after commit the next save reports absence again', api.snapshot(), undefined);
}
{
  // A session whose only activity was context-preserving navigation DID happen. It scores 0
  // under today's weights, but the raw count is precisely what makes the allowlist
  // re-scorable later — omitting it would destroy the thing nav_preserved exists to protect.
  const { api } = await load({ fetchImpl: okCfg({ context_preserving_transitions: [{ from: 'grid', to: 'trace' }] }) });
  api.startSession();
  await tick(); await tick();
  api.countNav('grid', 'trace');
  const s = api.snapshot();
  ok('a nav_preserved-only session is still REPORTED', !!s, '(snapshot was undefined)');
  eq('  ...with the raw count intact', s && s.nav_preserved, 1);
  eq('  ...and nav genuinely 0', s && s.nav, 0);
}

console.log('\n=== 3. commit resets ONLY on success ===');
{
  const { api } = await load({});
  const id = api.startSession();
  api.countKey(4); api.countMouse(3);

  // Failed save: caller does NOT call commit(). Counters must keep accumulating.
  const before = api.snapshot();
  eq('effort attached to the failed attempt', before.key, 4);
  api.countKey(2); // user retries -> more real effort
  eq('failed save keeps accumulating key', api.snapshot().key, 6);
  eq('failed save keeps accumulating mouse', api.snapshot().mouse, 3);

  // Successful save.
  api.commit();
  eq('commit empties every counter (snapshot goes absent)', api.snapshot(), undefined);
  api.countKey(1); // one more interaction, so the counters are readable again
  const after = api.snapshot();
  eq('counting resumes from 0: key', after.key, 1);
  eq('commit reset mouse', after.mouse, 0);
  eq('commit reset nav', after.nav, 0);
  eq('commit reset nav_preserved', after.nav_preserved, 0);
  eq('commit KEEPS session_id', after.session_id, id);
}

console.log('\n=== 3b. reset is gated on the server having RECORDED (F1) ===');
{
  // A repeat PUT whose value already matches storage returns 200 with change_count 0 and
  // writes no effort row, because no correction happened. Committing on res.ok alone
  // deletes the effort that attempt cost — and the operator, seeing nothing change, redoes
  // it properly with a handful of keys. The two-attempt correction (the highest-friction
  // event there is) would then record the LOWEST score in the dataset.
  const { api } = await load({});
  api.startSession();
  api.countKey(20); api.countMouse(5);

  const noop = { status: 'success', updated_count: 1, change_count: 0, created_logs: [], effort_recorded: false };
  eq('effort_recorded:false => did NOT reset', api.commitIfRecorded(noop), false);
  eq('  ...20 keystrokes survive the no-op save', api.snapshot().key, 20);
  eq('  ...5 clicks survive too', api.snapshot().mouse, 5);

  // The operator redoes it properly and this one really lands.
  api.countKey(3); api.countMouse(1);
  const s = api.snapshot();
  eq('the retry carries BOTH attempts: key', s.key, 23);
  eq('  ...and mouse', s.mouse, 6);
  eq('effort_recorded:true => reset', api.commitIfRecorded({ change_count: 1, effort_recorded: true }), true);
  eq('  ...counters cleared', api.snapshot(), undefined);
}
{
  // Older server, or a body we could not parse: fall back to the previous behaviour.
  // Never resetting would grow the counter without bound and bill a whole session's
  // browsing to whichever save finally succeeds — its own defect, and a louder one.
  const { api } = await load({});
  api.startSession();
  api.countKey(4);
  eq('field absent => falls back to resetting', api.commitIfRecorded({ change_count: 1 }), true);
  eq('  ...counters cleared', api.snapshot(), undefined);

  api.countKey(4);
  eq('null body => falls back to resetting', api.commitIfRecorded(null), true);
  eq('  ...counters cleared', api.snapshot(), undefined);

  api.countKey(4);
  eq('non-boolean flag is treated as absent, not as truthy', api.commitIfRecorded({ effort_recorded: 'yes' }), true);
  eq('  ...counters cleared', api.snapshot(), undefined);
}

console.log('\n=== 4. countNav classification (fail CLOSED) ===');
{
  // 4a. config never arrives -> everything counted
  const { api } = await load({ fetchImpl: () => Promise.reject(new Error('offline')) });
  api.startSession();
  await tick(); await tick();
  api.countNav('grid', 'map_editor');
  eq('config fetch failed => transition counted', api.snapshot().nav, 1);
  eq('getConfig reports not-loaded', api.getConfig().loaded, false);
}
{
  // 4b. HTTP 404 (endpoint not deployed yet) -> everything counted
  const { api } = await load({ fetchImpl: () => Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) }) });
  api.startSession();
  await tick(); await tick();
  api.countNav('grid', 'map_editor');
  eq('404 config => transition counted', api.snapshot().nav, 1);
}
{
  // 4c. served allowlist, string form
  const { api } = await load({
    fetchImpl: okCfg({ weights: { key: 1, mouse: 3, nav: 5 }, context_preserving_transitions: [{ from: 'grid', to: 'map_editor' }] })
  });
  api.startSession();
  await tick(); await tick();
  eq('config reports loaded', api.getConfig().loaded, true);
  api.countNav('grid', 'map_editor');
  eq('declared preserving => nav stays 0', api.snapshot().nav, 0);
  eq('declared preserving => nav_preserved counted, NOT discarded', api.snapshot().nav_preserved, 1);
  api.countNav('grid', 'admin');
  eq('undeclared => counted', api.snapshot().nav, 1);
  eq('undeclared does not touch nav_preserved', api.snapshot().nav_preserved, 1);
  api.countNav('GRID', ' Map_Editor ');
  eq('classification is case/space insensitive', api.snapshot().nav, 1);
  eq('  ...and lands in nav_preserved', api.snapshot().nav_preserved, 2);
  api.countNav('map_editor', 'grid');
  eq('direction matters (reverse not implied)', api.snapshot().nav, 2);
}
{
  // 4d. object form + garbage entries + wildcard must NOT be honoured
  const { api } = await load({
    fetchImpl: okCfg({
      context_preserving_transitions: [
        { from: 'grid', to: 'map_editor' },
        'grid>admin', 42, null, { from: 'x' }, { from: '*', to: '*' }
      ]
    })
  });
  api.startSession();
  await tick(); await tick();
  api.countNav('grid', 'map_editor');
  eq('object form honoured => 0', api.snapshot().nav, 0);
  api.countNav('grid', 'admin');
  eq('wildcard NOT honoured => counted', api.snapshot().nav, 1);
  eq('garbage entries dropped, not fatal', api.getConfig().context_preserving_transitions.length, 1);
}
{
  // 4e. race: countNav before the config response lands -> counted (biased safe)
  const { api } = await load({ fetchImpl: okCfg({ context_preserving_transitions: [{ from: 'grid', to: 'map_editor' }] }) });
  api.startSession();
  api.countNav('grid', 'map_editor'); // config still in flight
  eq('pre-config transition counted (never flatters)', api.snapshot().nav, 1);
}
{
  const { api } = await load({});
  api.startSession();
  api.countNav('', 'grid'); api.countNav('grid', null); api.countNav(undefined, undefined);
  eq('empty route ids are ignored, not counted as moves', api.snapshot(), undefined);
}

console.log('\n=== 4f. allowlist entries are validated against the route vocabulary (F3) ===');
{
  // The entry the SSOT literally names. No route id `doe` or `dt_map` exists — the real
  // ids are `map_editor` and `map_editor:material` — so this exempts nothing. Its EFFECT
  // (everything keeps counting) is identical to it working, which is why silence is fatal
  // here: the config author has no way to tell the two apart.
  const { api, errors } = await load({
    fetchImpl: okCfg({
      context_preserving_transitions: [
        { from: 'doe', to: 'dt_map' },
        { from: 'map_editor', to: 'map_editor:material' }
      ]
    })
  });
  api.startSession();
  await tick(); await tick();
  const cfg = api.getConfig();
  eq('the bogus entry is not in the active allowlist', cfg.context_preserving_transitions.length, 1);
  eq('the valid sub-context entry is', cfg.context_preserving_transitions[0], 'map_editor>map_editor:material');
  eq('the bogus entry is surfaced through getConfig()', cfg.rejected_transitions.length, 1);
  ok('  ...with a reason naming BOTH unknown ids',
     /doe/.test(cfg.rejected_transitions[0].reason) && /dt_map/.test(cfg.rejected_transitions[0].reason),
     JSON.stringify(cfg.rejected_transitions[0]));
  ok('  ...and reported to the console',
     errors.some(e => /doe/.test(e) && /EXEMPTS NOTHING/.test(e)), JSON.stringify(errors));
  ok('getConfig publishes the vocabulary so the author can fix it',
     cfg.known_routes.includes('map_editor:material') && cfg.known_routes.includes('grid:log_jump'));

  // Behaviour, not just diagnostics: the valid neighbour still works.
  api.countNav('map_editor', 'map_editor:material');
  eq('the valid entry still exempts', api.snapshot().nav_preserved, 1);
  eq('  ...and did not leak into nav', api.snapshot().nav, 0);
}
{
  // One bad half is enough to reject the entry, and neighbours must not be collateral.
  const { api } = await load({
    fetchImpl: okCfg({ context_preserving_transitions: [
      { from: 'grid', to: 'tracee' }, { from: 'grid', to: 'trace' }, { from: '*', to: '*' }
    ] })
  });
  api.startSession();
  await tick(); await tick();
  const cfg = api.getConfig();
  eq('one unknown half rejects the whole entry', cfg.context_preserving_transitions.join(','), 'grid>trace');
  eq('typo AND wildcard both reported', cfg.rejected_transitions.length, 2);
  ok('the wildcard is reported as a wildcard, not as an unknown route',
     cfg.rejected_transitions.some(r => /wildcard/.test(r.reason)), JSON.stringify(cfg.rejected_transitions));
  api.countNav('grid', 'tracee');
  eq('the typo transition keeps COUNTING (over-counting never flatters)', api.snapshot().nav, 1);
  api.countNav('grid', 'trace');
  eq('  ...while its correctly-spelled neighbour is exempt', api.snapshot().nav_preserved, 1);
}

console.log('\n=== 4g. accept EXACTLY what the server accepts (B-F5) ===');
{
  // The server (effort_metric.resolve_context_preserving_transitions) requires a dict and
  // drops everything else. Tolerating the "from>to" shorthand here meant an author could
  // write an entry that the client honoured and the server discarded — one side obeys, the
  // other ignores, and nothing says so.
  const { api, errors } = await load({
    fetchImpl: okCfg({
      context_preserving_transitions: ['grid>trace', { from: 'grid', to: 'trace' }]
    })
  });
  api.startSession();
  await tick(); await tick();
  const cfg = api.getConfig();
  eq('the object form is honoured', cfg.context_preserving_transitions.join(','), 'grid>trace');
  eq('the string shorthand is rejected', cfg.rejected_transitions.length, 1);
  ok('  ...with a reason that names the accepted form',
     /server drops it/.test(cfg.rejected_transitions[0].reason) && /"from"/.test(cfg.rejected_transitions[0].reason),
     JSON.stringify(cfg.rejected_transitions[0]));
  ok('  ...and reported to the console', errors.some(e => /EXEMPTS NOTHING/.test(e)));
}

console.log('\n=== 4h. the loaded/failed state is observable in a BUILT bundle (B-F3) ===');
{
  // getConfig() had no caller in client2/src, so the bundler shook it out of dist and the
  // one distinction the fail-closed design rests on became unobservable in production.
  // The window assignment is a real reference, so it cannot be shaken out.
  const { api, sandbox, warns } = await load({ fetchImpl: () => Promise.reject(new Error('offline')) });
  api.startSession();
  await tick(); await tick();
  ok('startSession publishes window.__assyEffort', !!sandbox.window.__assyEffort);
  eq('  ...exposing getConfig', typeof sandbox.window.__assyEffort.getConfig, 'function');
  eq('  ...and it reports the FAILED state, not an empty allowlist',
     sandbox.window.__assyEffort.getConfig().loaded, false);
  ok('  ...exposing the route vocabulary an author needs to fix a bad entry',
     Array.isArray(sandbox.window.__assyEffort.ROUTE_IDS));
  ok('a config failure is also announced on the console',
     warns.some(w => /api\/effort\/config failed/.test(w) && /fail-closed/.test(w)), JSON.stringify(warns));
}
{
  const { api, sandbox, warns } = await load({ fetchImpl: okCfg({ context_preserving_transitions: [] }) });
  api.startSession();
  await tick(); await tick();
  eq('a config that ARRIVED and is empty reports loaded:true', sandbox.window.__assyEffort.getConfig().loaded, true);
  eq('  ...and warns about nothing', warns.length, 0);
}

console.log('\n=== 5. insecure context (production is plain HTTP) ===');
{
  // crypto.randomUUID is secure-context gated and absent in production.
  const insecure = { getRandomValues: (b) => { for (let i = 0; i < b.length; i++) b[i] = (i * 37 + 11) & 0xff; return b; } };
  const { api } = await load({ cryptoImpl: insecure });
  const id = api.startSession();
  ok('getRandomValues fallback yields a valid v4 uuid', V4_RE.test(id), `(got ${id})`);
}
{
  // randomUUID present but throwing (some engines throw rather than omit it)
  const throwing = {
    randomUUID: () => { throw new Error('SecurityError'); },
    getRandomValues: (b) => { for (let i = 0; i < b.length; i++) b[i] = 0xab; return b; }
  };
  const { api } = await load({ cryptoImpl: throwing });
  ok('throwing randomUUID falls through', V4_RE.test(api.startSession()));
}
{
  // no crypto at all
  const { api } = await load({ cryptoImpl: null });
  const id = api.startSession();
  ok('no crypto => Math.random fallback still yields an id', UUID_RE.test(id), `(got ${id})`);
}

console.log('\n=== 6. instrumentation must never break the page ===');
{
  const { api } = await load({ storage: makeStorage({ throwOnSet: true }) });
  const id = api.startSession();
  ok('storage write blocked => still returns an id', !!id);
  api.countKey(2);
  eq('degrades to in-memory counting', api.snapshot().key, 2);
}
{
  const { api } = await load({ storage: makeStorage({ throwOnGet: true }) });
  api.startSession();
  api.countMouse(1);
  eq('storage read blocked => still counts', api.snapshot().mouse, 1);
}
{
  const storage = makeStorage();
  storage._raw.set('assy.effort', '{not json');
  const { api } = await load({ storage });
  ok('corrupt entry => fresh session, no throw', UUID_RE.test(api.startSession()));
}
{
  const storage = makeStorage();
  storage._raw.set('assy.effort', JSON.stringify({ session_id: 'abc', key: -5, mouse: 'x', nav: 2.7 }));
  const { api } = await load({ storage });
  const s = api.snapshot();
  eq('negative count sanitised to 0', s.key, 0);
  eq('non-numeric count sanitised to 0', s.mouse, 0);
  eq('fractional count floored', s.nav, 2);
  // Entries written before the nav_preserved addendum have no such key.
  eq('pre-addendum entry: nav_preserved defaults to 0', s.nav_preserved, 0);
  api.countNav('a', 'b');
  eq('pre-addendum entry still counts forward', api.snapshot().nav, 3);
}

console.log('\n=== 7. global listeners ===');
{
  const { api, document } = await load({});
  api.startSession();
  api.installGlobalListeners();
  api.installGlobalListeners(); // must be idempotent
  eq('keydown bound exactly once', document._count('keydown'), 1);
  eq('mousedown bound exactly once', document._count('mousedown'), 1);

  document._fire('keydown', { key: 'a' });
  document._fire('keydown', { key: 'Enter' });
  eq('keystrokes counted', api.snapshot().key, 2);
  document._fire('keydown', { key: 'Shift' });
  document._fire('keydown', { key: 'Control' });
  document._fire('keydown', { key: 'Meta' });
  eq('bare modifiers NOT counted', api.snapshot().key, 2);
  document._fire('keydown', { key: 'c', ctrlKey: true });
  eq('chord counts once (on the non-modifier key)', api.snapshot().key, 3);
  document._fire('keydown', { key: 'Backspace', repeat: true });
  eq('auto-repeat IS counted (never flatters)', api.snapshot().key, 4);

  document._fire('mousedown', {});
  document._fire('mousedown', {});
  eq('mousedown counted', api.snapshot().mouse, 2);
}

console.log('\n=== 8. route resolution + nav link counting ===');
{
  const { api, document } = await load({});
  api.startSession();
  eq('/ resolves to grid', api.routeFromHref('/'), 'grid');
  eq('/index.html resolves to grid', api.routeFromHref('/index.html'), 'grid');
  eq('/map_editor.html resolves', api.routeFromHref('/map_editor.html'), 'map_editor');
  eq('/admin.html resolves', api.routeFromHref('/admin.html'), 'admin');
  eq('relative href resolves', api.routeFromHref('admin.html?tab=chain'), 'admin');
  // The two above named /trace.html until 2026-09-04. Its KEY went with the page, and
  // these two score that: a retired screen must resolve to null, not to a route id no
  // navigation can reach. Without them the removal has no scorer at all.
  eq('a retired screen resolves to nothing (trace)', api.routeFromHref('/trace.html'), null);
  eq('a retired screen resolves to nothing (graph)', api.routeFromHref('/graph.html'), null);
  eq('api download path is not a screen', api.routeFromHref('/api/download/client'), null);
  eq('external origin is not a screen', api.routeFromHref('https://fonts.googleapis.com/x'), null);
  eq('garbage href is not fatal', api.routeFromHref('::::'), null);
  eq('currentRoute reflects pathname', api.currentRoute(), 'grid');

  api.installNavLinkCounting('grid');
  api.installNavLinkCounting('grid'); // idempotent
  eq('click bound exactly once', document._count('click'), 1);

  const anchor = (href, download = false) => ({
    getAttribute: () => href,
    hasAttribute: (a) => a === 'download' && download
  });
  const evt = (a) => ({ target: { closest: () => a } });

  document._fire('click', evt(anchor('/map_editor.html')));
  eq('anchor navigation counted', api.snapshot().nav, 1);
  document._fire('click', evt(anchor('/api/download/client', true)));
  eq('download anchor NOT counted as a screen move', api.snapshot().nav, 1);
  document._fire('click', evt(null));
  eq('non-anchor click does not count a nav', api.snapshot().nav, 1);
}

// ════════════════════════════════════════════════════════════════════════════════
// 8b. CALL-SITE WIRING (source-level, every page)
//
// The sections above prove the collector behaves. They cannot prove a page USES it.
// Two regressions live here and neither shows up in any behavioural test:
//   - a correction write path importing bare `commit` again (the F1 defect returning:
//     a 200 that recorded nothing would erase the effort it cost)
//   - a page never importing the collector at all (B-F1: grid->graph was counted while
//     graph->grid was not, so every round trip out to a read surface recorded half its
//     true cost — the flattering direction, on a baseline that cannot be recollected)
// The import clause is the chokepoint: you cannot call what you did not import.
// ════════════════════════════════════════════════════════════════════════════════
const SRC_DIR = join(dirname(fileURLToPath(import.meta.url)), '..', 'src');
const readSrc = (f) => readFileSync(join(SRC_DIR, f), 'utf8').replace(/\r\n/g, '\n');

/** Named bindings imported from effort_meter.js, by their EXPORTED name (aliases resolved). */
function effortImports(src) {
  const m = /import\s*\{([^}]*)\}\s*from\s*'\.\/effort_meter\.js'/.exec(src);
  if (!m) return null; // not wired at all
  return m[1].split(',').map(s => s.trim()).filter(Boolean).map(s => s.split(/\s+as\s+/)[0].trim());
}

// A correction write path: attaches `effort` and must gate its reset on the server.
const WRITE_PAGES = ['api.js', 'ui.js', 'clipboard.js', 'main.js', 'enrichment.js', 'map_editor.js'];
// A read surface: writes no corrections, so nothing carries `effort` — but LEAVING counts.
// `graph_viewer.js`/GRAPH and `trace.js`/TRACE were here until 2026-09-04 and went with
// the pages. Their two mutants below MOVED to `admin.js` rather than being deleted: what
// they score -- a read surface with no collector, and one counting itself as the wrong
// route -- is a property of the CLASS, and admin.js is the member that survived.
const READ_PAGES = [
  ['admin.js', 'ADMIN']
];

function auditWiring(srcOf) {
  const r = { bareCommit: [], missingGated: [], noEffortField: [], unwiredRead: [], missingInstall: [] };
  for (const f of WRITE_PAGES) {
    const s = srcOf(f);
    const imp = effortImports(s);
    if (!imp) { r.unwiredRead.push(f); continue; }
    if (imp.includes('commit')) r.bareCommit.push(f);
    if (!imp.includes('commitIfRecorded')) r.missingGated.push(f);
    if (!/effort:\s*\w*[Ss]napshot\(\)/.test(s)) r.noEffortField.push(f);
  }
  for (const [f, routeKey] of READ_PAGES) {
    const s = srcOf(f);
    const imp = effortImports(s);
    if (!imp) { r.unwiredRead.push(f); continue; }
    for (const need of ['startSession', 'installGlobalListeners', 'installNavLinkCounting']) {
      if (!imp.includes(need) || !new RegExp(`${need}\\(`).test(s)) r.missingInstall.push(`${f}:${need}`);
    }
    if (!new RegExp(`installNavLinkCounting\\(ROUTES\\.${routeKey}\\)`).test(s)) {
      r.missingInstall.push(`${f}:route=${routeKey}`);
    }
    // A read surface must not be inventing an effort payload — there is no correction here.
    if (/effort:\s*\w*[Ss]napshot\(\)/.test(s)) r.noEffortField.push(`${f} ATTACHES effort (should not)`);
  }
  return r;
}

console.log('\n=== 8b. call-site wiring across every page ===');
{
  const a = auditWiring(readSrc);
  eq('no correction path imports bare commit()', a.bareCommit.join(','), '');
  eq('every correction path imports commitIfRecorded', a.missingGated.join(','), '');
  eq('every correction path attaches `effort`', a.noEffortField.join(','), '');
  eq('no page is missing the collector entirely', a.unwiredRead.join(','), '');
  eq('every read surface installs listeners + its own nav route', a.missingInstall.join(','), '');
}
{
  // Mutations: this audit must FAIL against each regression it claims to catch.
  const mutate = (file, fn) => (f) => (f === file ? fn(readSrc(f)) : readSrc(f));

  const g1 = auditWiring(mutate('api.js', s => s.replace('commitIfRecorded } from', 'commit } from')));
  ok('audit catches a write path reverting to bare commit()',
     g1.bareCommit.includes('api.js') && g1.missingGated.includes('api.js'), JSON.stringify(g1));

  const g2 = auditWiring(mutate('admin.js',
    s => s.replace(/import\s*\{[^}]*\}\s*from\s*'\.\/effort_meter\.js';/, '')));
  ok('audit catches a page with no collector at all (B-F1)',
     g2.unwiredRead.includes('admin.js'), JSON.stringify(g2));

  const g3 = auditWiring(mutate('admin.js',
    s => s.replace('installNavLinkCounting(ROUTES.ADMIN)', 'installNavLinkCounting(ROUTES.GRID)')));
  ok('audit catches a page counting itself as the wrong route',
     g3.missingInstall.includes('admin.js:route=ADMIN'), JSON.stringify(g3));
}

console.log('\n=== 9. mutation check (does this harness actually detect a regression?) ===');
{
  // Re-run the two load-bearing invariants against deliberately broken sources.
  // If these "broken" builds still pass, the assertions above prove nothing.
  // The mutants are WHOLE MODULES now. One that fails to parse fails loudly instead of
  // counting as caught -- the failure mode that made the rewritten-source version measure
  // letter shapes. The "did it actually apply" guard is kept: a mutation whose target string
  // has drifted becomes a silent no-op, and the "broken" build then passes for the wrong
  // reason. (The probe refuses an unchanged source too; this keeps the local message.)
  async function loadMutated(mutate, fetchImpl) {
    const { api, sandbox } = await load({ fetchImpl }, (src) => {
      // Normalised to LF first, for the reason `rawSrc` is: the targets below are
      // multi-line strings, and the file's line endings are not stable across editors on
      // Windows. The probe hands over the bytes as they are ON DISK -- that is the whole
      // point of it -- so the normalisation that used to happen at read time happens here.
      const flat = src.replace(/\r\n/g, '\n');
      const mutated = mutate(flat);
      // A mutation whose target string has drifted becomes a silent no-op, and the
      // "broken" build then passes for the wrong reason. (The probe refuses an unchanged
      // source too; this keeps the local message.)
      if (mutated === flat) {
        throw new Error('mutation did not apply -- its target string is stale');
      }
      return mutated;
    });
    // Mutant H is detected by the ABSENCE of the published diagnostics object, so the window
    // the module published onto has to travel with the api. A module namespace is sealed, so
    // this is a plain copy of it rather than a property bolted onto the namespace.
    return Object.assign({}, api, { __sandboxWindow: sandbox.window });
  }

  // snapshot() is now absent-when-empty, so a defect can legitimately make it undefined.
  // Read through this rather than `.key` so a mutation reports as DETECTED instead of
  // crashing the suite (a crash is a pass in spirit, but it stops every later check).
  const snap = (m) => m.snapshot() || {};

  // Mutation A: make snapshot() reset (the classic mistake).
  const mA = await loadMutated(s => s.replace(
    '    nav_preserved: s.nav_preserved\n  };',
    '    nav_preserved: (s.key = 0, s.nav_preserved)\n  };'
  ));
  mA.startSession(); mA.countKey(3); mA.snapshot();
  ok('mutation A (snapshot resets) IS detected', snap(mA).key !== 3);

  // Mutation B: fail OPEN on config error (treat everything as context-preserving).
  const mB = await loadMutated(s => s.replace(
    'if (preservingSet.has(key)) s.nav_preserved += 1;',
    'if (!configLoaded || preservingSet.has(key)) s.nav_preserved += 1;'
  ));
  mB.startSession();
  await tick(); await tick();
  mB.countNav('grid', 'admin');
  ok('mutation B (fail-open config) IS detected', snap(mB).nav !== 1);

  // Mutation C: discard the exempted transition instead of bucketing it (the pre-addendum
  // behaviour). This is the one that could never be repaired later — the metric is not
  // retroactively computable, so a discarded transition is gone for good.
  const mC = await loadMutated(
    s => s.replace(
      'if (preservingSet.has(key)) s.nav_preserved += 1;\n  else s.nav += 1;',
      'if (preservingSet.has(key)) return;\n  s.nav += 1;'
    ),
    okCfg({ context_preserving_transitions: [{ from: 'grid', to: 'admin' }] })
  );
  mC.startSession();
  await tick(); await tick();
  mC.countNav('grid', 'admin');
  ok('mutation C (exempted transition discarded) IS detected', snap(mC).nav_preserved !== 1);

  // Mutation D: report the all-zero blob instead of omitting it (the F2 defect). The server
  // files that as a genuine, measured score-0 correction.
  const mD = await loadMutated(s => s.replace(
    '  if (!s.key && !s.mouse && !s.nav && !s.nav_preserved) return undefined;\n',
    ''
  ));
  mD.startSession();
  ok('mutation D (all-zero snapshot reported as measured) IS detected', mD.snapshot() !== undefined);

  // Mutation E: commit regardless of the server's flag (the F1 defect) — a no-op save
  // erases the effort it cost.
  const mE = await loadMutated(s => s.replace(
    '    if (recorded) commit();\n    return recorded;',
    '    commit();\n    return recorded;'
  ));
  mE.startSession(); mE.countKey(20); mE.countMouse(5);
  mE.commitIfRecorded({ change_count: 0, effort_recorded: false });
  ok('mutation E (commit ignores effort_recorded) IS detected', snap(mE).key !== 20);

  // Mutation F: accept unknown route ids (the F3 defect). The entry is inert either way —
  // what the fix buys is that it stops being SILENT, so that is what must break.
  const mF = await loadMutated(
    s => s.replace('if (unknown.length) { reject(', 'if (false) { reject('),
    okCfg({ context_preserving_transitions: [{ from: 'doe', to: 'dt_map' }] })
  );
  mF.startSession();
  await tick(); await tick();
  ok('mutation F (unknown route ids accepted silently) IS detected',
     mF.getConfig().rejected_transitions.length === 0);

  // Mutation G: tolerate the string shorthand again (the B-F5 defect) — the client would
  // honour an entry the server drops.
  const mG = await loadMutated(
    s => s.replace(
      "      reject(entry, 'string form is not accepted",
      "      { const _p = String(entry).split('>'); preserving.add(normRoute(_p[0]) + '>' + normRoute(_p[1])); continue; }\n"
      + "      reject(entry, 'string form is not accepted"
    ),
    okCfg({ context_preserving_transitions: ['grid>admin'] })
  );
  mG.startSession();
  await tick(); await tick();
  mG.countNav('grid', 'admin');
  ok('mutation G (string shorthand honoured again) IS detected', snap(mG).nav_preserved === 1);

  // Mutation H: drop the window publication (the B-F3 defect) — getConfig becomes
  // unreferenced and the bundler shakes it out of the built chunk.
  const mH = await loadMutated(s => s.replace('  publishDiagnostics();\n', ''));
  mH.startSession();
  ok('mutation H (diagnostics not published) IS detected', mH.__sandboxWindow.__assyEffort === undefined);
}

console.log(`\n=== RESULT: ${pass} passed, ${fail} failed ===`);
// H1 protocol: the runner reads this line to tell "red with N assertions" from a crash.
console.log(`ASSERTIONS ${pass + fail} ${fail}`);
if (fail) { console.log('failed: ' + failures.join(', ')); process.exit(1); }
