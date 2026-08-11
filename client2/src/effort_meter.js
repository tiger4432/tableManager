/**
 * effort_meter.js — V1 core-value instrument: "interaction score to completion".
 *
 * SSOT core value #1 is "minimum-effort correction". This module measures the raw
 * human effort spent completing one correction unit (= one successful
 * `PUT /tables/{t}/data/updates` batch, which the server already fences with a tx_id).
 *
 * Scoring (keystroke 1 / mouse 3 / context-losing screen move 5, lower is better) is
 * NOT applied here. We store RAW counts and let the server weight them at query time,
 * so a future change to the weights re-interprets historical data instead of
 * invalidating it.
 *
 * ── THIS IS THE ONLY COLLECTOR IN THE CODEBASE ──────────────────────────────────
 * Every page imports this file. Do NOT hand-roll a second set of counters, a second
 * route table, or a second session-id generator anywhere in client2/src. Duplicated
 * client-side constant lists have bitten this codebase repeatedly.
 *
 * ── Contract (owned by Lead PM — do not rename or re-shape) ─────────────────────
 *   startSession()               ensure a session_id (UUID) in sessionStorage
 *   countKey(n = 1)              keystrokes
 *   countMouse(n = 1)            mouse clicks
 *   countNav(fromRoute, toRoute) counts into `nav` or `nav_preserved`, never discards
 *   snapshot()                   -> { session_id, key, mouse, nav, nav_preserved }
 *                                -> `undefined` when nothing accumulated (see invariant 5)
 *                                MUST NOT reset
 *   commit()                     resets counters — ONLY after a batch commit succeeded
 *   commitIfRecorded(resBody)    commit() gated on the server's `effort_recorded` flag
 *
 *   installGlobalListeners()     page-wide passive key/mouse counting (idempotent)
 *   installNavLinkCounting(from) delegated <a href> nav counting (idempotent)
 *   routeFromHref() / currentRoute() / ROUTES / ROUTE_IDS  the ONE path<->route mapping
 *   getConfig()                  diagnostics: did the served config actually arrive?
 *                                also published as `window.__assyEffort.getConfig()` —
 *                                an export with no caller gets tree-shaken out of the
 *                                built bundle, and observability that only exists in
 *                                source is not observability.
 *
 * ── Invariants that are easy to break ───────────────────────────────────────────
 * 1. Reset ONLY on success. A failed save must keep accumulating: retry effort is real
 *    human effort. Resetting on attempt would make a failing save look cheap.
 * 2. Counters survive a reload in the same tab (sessionStorage) — a mid-correction
 *    reload does not restart the human's work. They die with the tab, as a session should.
 * 3. Default is COUNTED. If the served config is missing or unparseable, every
 *    transition scores as context-losing. Never fail open into "score 0": a missing
 *    entry only makes the score look worse, a wrong entry silently flatters it.
 * 3-bis. Classification never DISCARDS. An exempted transition still increments
 *    `nav_preserved` instead of vanishing, so the move survives in the data.
 *    Be precise about what that buys, because the stronger claim is false: the BUCKET
 *    (`nav` vs `nav_preserved`) is chosen HERE, at collection time, from the allowlist
 *    in force at that moment — changing the allowlist later does NOT re-bucket rows
 *    already written. What stays re-interpretable is the WEIGHTING: both buckets are
 *    raw counts scored at query time, so `weights.nav_preserved` can be raised later to
 *    re-score history. Discarding would have destroyed even that.
 * 4. Instrumentation is invisible. No UI, no badge, no toast, no preventDefault.
 *    It must never be able to break the page it measures — every storage and network
 *    access here is guarded.
 * 5. ABSENCE IS NOT ZERO, in both directions.
 *    - Nothing accumulated -> `snapshot()` returns undefined -> the `effort` key vanishes
 *      from the JSON body. An all-zero blob would be stored as a genuine, measured
 *      score-0 correction and would halve the baseline with a phantom.
 *    - The server did not record -> do not reset. A no-op save (a repeat PUT whose value
 *      already matches storage) returns 200 but writes no effort row; resetting there
 *      deletes the effort the attempt actually cost, so the two-attempt correction —
 *      the highest-friction event there is — would score the LOWEST in the dataset.
 */

import { API_BASE } from './config.js';

const STORAGE_KEY = 'assy.effort';

/**
 * Shared route-id vocabulary. Convention: `page` or `page:subcontext`.
 * Sub-contexts are free-form strings (e.g. 'map_editor:material'); keep them stable,
 * because the served allowlist is keyed on these exact ids.
 */
export const ROUTES = Object.freeze({
  GRID: 'grid',
  MAP_EDITOR: 'map_editor',
  ADMIN: 'admin',
  ENRICHMENT: 'enrichment',
  GRAPH: 'graph',
  TRACE: 'trace'
});

/**
 * The COMPLETE route-id vocabulary: every id a call site may pass to `countNav`, and
 * therefore the only ids a served allowlist entry may name.
 *
 * Why this list has to exist: the server validates the allowlist's SHAPE but owns no route
 * vocabulary, so it echoes an unrecognised entry back verbatim. Approving
 * `{"from":"doe","to":"dt_map"}` — the transition the SSOT itself names — exempts nothing,
 * because the real ids are `map_editor` and `map_editor:material`. Nothing fires, nothing
 * warns, and the effect of a typo is indistinguishable from the effect of it working.
 *
 * ⚠️ Adding a `countNav(x, 'grid:something')` call WITHOUT registering the id here makes any
 * allowlist entry naming it report as unknown and stay COUNTED. That direction is safe
 * (over-counting never flatters) and loud, but it is a real trap — register the id in the
 * same change as the call site.
 */
/*
 * ⚠️ `enrichment` AND `enrichment:rule` ARE KEPT DELIBERATELY, AND NEITHER HAS A LIVE CALL SITE
 *    (2026-08-11). `/enrichment.html` was deleted with the page; `enrichment:rule` lost its only
 *    caller when `5116f67` removed the 결손 badge. They stay for one reason and it is not
 *    sentiment: THIS LIST IS THE VALIDATOR FOR A SERVED ALLOWLIST, not a census of live
 *    navigations. An id removed from here does not stop anything being counted -- it makes any
 *    `context_preserving_transitions` entry naming it report as UNKNOWN and stay counted. Both
 *    directions were measured before leaving them in: the served list defaults to `[]` and no
 *    `server/config/effort_metric.json` exists, so nothing is exempt today and nothing can be
 *    un-exempted; and matching is exact against what `countNav` was actually passed, so an entry
 *    naming a dead route exempts nothing either way. Deleting them is therefore a housekeeping
 *    change to make with `src/enrichment.js` -- which is the only module that still names
 *    `ROUTES.ENRICHMENT` -- and that module is sliced by four gated harnesses. One decision, not
 *    two.
 */
export const ROUTE_IDS = Object.freeze([
  ROUTES.GRID,
  ROUTES.MAP_EDITOR,
  ROUTES.ADMIN,
  ROUTES.ENRICHMENT,                 // no live call site since the page was deleted — see above
  ROUTES.GRAPH,
  ROUTES.TRACE,
  'grid:table',                      // main.js      — table switch
  'grid:viewmode',                   // main.js      — pagination <-> infinite scroll
  'grid:log_jump',                   // timeline.js  — jump to a history entry
  'enrichment:rule',                 // no live call site since 5116f67 — see above
  `${ROUTES.MAP_EDITOR}:material`    // map_editor.js — material frame push/pop
]);

const KNOWN_ROUTE_IDS = new Set(ROUTE_IDS.map(id => id.toLowerCase()));

// ── Served config ───────────────────────────────────────────────────────────────
// Fetched from GET /api/effort/config, same discipline as paint-rules serving `binding`:
// the server is the single source of truth for the declaration.
let servedWeights = null;
let preservingSet = new Set(); // empty = everything counted (the safe default)
let rejectedTransitions = []; // [{ entry, reason }] — inert entries, reported loudly
let configLoaded = false;
let configPromise = null;

function normRoute(v) {
  return String(v == null ? '' : v).trim().toLowerCase();
}

/**
 * Accepts EXACTLY what the server accepts: `[{ from, to }, ...]`, both non-empty strings.
 *
 * The `"from>to"` string shorthand used to be tolerated here. It is not, any more: the
 * server (`effort_metric.resolve_context_preserving_transitions`) requires a dict and
 * drops anything else, so a string entry was honoured by the client and discarded by the
 * server — an author writes it, one side obeys it, the other ignores it, and nothing says
 * so. Being MORE permissive than the producer is not leniency, it is a second, undeclared
 * contract. Accept what the server accepts and reject the rest visibly.
 *
 * Every entry either lands in `preserving` (it will really exempt that transition) or in
 * `rejected` (it is inert). There is no third, silent outcome: an entry that exempts
 * nothing looks EXACTLY like an entry that works — the allowlist's whole effect is a
 * number that stays the same — so silence here is indistinguishable from success.
 *
 * Rejected entries stay rejected rather than being kept as literals: an unknown id can
 * never match a real transition anyway, and dropping keeps `getConfig().
 * context_preserving_transitions` an honest list of what is actually exempted.
 */
function parseTransitions(raw) {
  const preserving = new Set();
  const rejected = [];
  if (!Array.isArray(raw)) return { preserving, rejected };

  const reject = (entry, reason) => rejected.push({ entry, reason });

  for (const entry of raw) {
    if (typeof entry === 'string') {
      reject(entry, 'string form is not accepted (the server drops it) — use {"from": "...", "to": "..."}');
      continue;
    }
    if (!entry || typeof entry !== 'object' || Array.isArray(entry)) {
      reject(entry, 'malformed entry (expected a {from,to} object)');
      continue;
    }
    const from = entry.from, to = entry.to;
    if (typeof from !== 'string' || typeof to !== 'string') {
      reject(entry, 'malformed entry (from/to must both be strings)');
      continue;
    }

    const f = normRoute(from), t = normRoute(to);
    if (!f || !t) { reject(entry, 'malformed entry (empty from/to)'); continue; }
    // Wildcards can silently flatter a whole class of moves, and matching is exact, so a
    // retained "*>*" would be an inert literal that READS as a sweeping exemption.
    if (f.includes('*') || t.includes('*')) { reject(entry, 'wildcards are not supported'); continue; }

    const unknown = [];
    if (!KNOWN_ROUTE_IDS.has(f)) unknown.push(from);
    if (!KNOWN_ROUTE_IDS.has(t)) unknown.push(to);
    if (unknown.length) { reject(entry, `unknown route id: ${unknown.join(', ')}`); continue; }

    preserving.add(`${f}>${t}`);
  }
  return { preserving, rejected };
}

/** Only for live transitions from call sites — never for config entries (they get reasons). */
function transitionKey(from, to) {
  const f = normRoute(from), t = normRoute(to);
  if (!f || !t) return '';
  if (f.includes('*') || t.includes('*')) return '';
  return `${f}>${t}`;
}

/**
 * Console-loud, once per config load. The console is the only channel that reaches whoever
 * just edited the config; `getConfig().rejected_transitions` is the one that survives for
 * whoever inspects it later. Both, because either alone is missable.
 */
function reportRejected() {
  for (const r of rejectedTransitions) {
    try {
      console.error(
        `[effort_meter] context_preserving_transitions entry EXEMPTS NOTHING — ${r.reason}.`,
        'Entry:', r.entry,
        '| known route ids:', ROUTE_IDS.join(', ')
      );
    } catch (err) { /* instrumentation must never break the page */ }
  }
}

function loadConfig() {
  if (configPromise) return configPromise;
  configPromise = (async () => {
    try {
      const res = await fetch(`${API_BASE}/api/effort/config`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const cfg = await res.json();
      servedWeights = cfg && typeof cfg.weights === 'object' ? cfg.weights : null;
      const parsed = parseTransitions(cfg && cfg.context_preserving_transitions);
      preservingSet = parsed.preserving;
      rejectedTransitions = parsed.rejected;
      configLoaded = true;
      reportRejected();
    } catch (err) {
      // Fail CLOSED: an empty allowlist means every transition is counted.
      servedWeights = null;
      preservingSet = new Set();
      rejectedTransitions = [];
      configLoaded = false;
      // Say so. Failing closed is correct, but "the allowlist is empty" and "the config
      // never arrived" produce the SAME counting behaviour, so without this line the two
      // states are indistinguishable in the field — which is exactly the distinction
      // getConfig() exists to expose.
      try {
        console.warn(
          '[effort_meter] GET /api/effort/config failed — every screen move will be counted '
          + 'as context-losing (fail-closed, deliberate). Inspect window.__assyEffort.getConfig().',
          err
        );
      } catch (e) { /* instrumentation must never break the page */ }
    }
  })();
  return configPromise;
}

/**
 * Publish the diagnostics on `window` so they SURVIVE THE PRODUCTION BUILD.
 *
 * `getConfig` had no caller in `client2/src`, so the bundler tree-shook it out of the
 * built chunk (measured: `grep -c "loaded:"` was 0 in dist). An export that only exists in
 * source is not observability — in production you could not tell "the allowlist is empty"
 * from "the config fetch failed", the one distinction the fail-closed design depends on
 * being able to make. This assignment is a real reference, so it cannot be shaken out.
 *
 * Read-only diagnostics, no UI, guarded. Nothing in the app reads it back.
 */
function publishDiagnostics() {
  try {
    if (typeof window === 'undefined') return;
    window.__assyEffort = { getConfig, snapshot, ROUTE_IDS };
  } catch (err) { /* instrumentation must never break the page */ }
}

/**
 * Diagnostics only. Lets QA distinguish "config arrived and is empty" from "config failed",
 * and — via `rejected_transitions` — "this entry is exempting the transition" from "this
 * entry is a typo that exempts nothing while the config author believes otherwise".
 */
export function getConfig() {
  return {
    loaded: configLoaded,
    weights: servedWeights,
    context_preserving_transitions: Array.from(preservingSet),
    rejected_transitions: rejectedTransitions.map(r => ({ entry: r.entry, reason: r.reason })),
    known_routes: ROUTE_IDS.slice()
  };
}

// ── Session id ──────────────────────────────────────────────────────────────────
/**
 * `crypto.randomUUID` is secure-context gated and is therefore `undefined` in
 * production, which is served over plain HTTP on the intranet — the exact trap that
 * already killed `navigator.clipboard` here. `crypto.getRandomValues` is NOT gated,
 * so it is the real primary path.
 */
function newSessionId() {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID();
    }
  } catch (err) { /* secure-context gated — fall through */ }

  try {
    if (typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function') {
      const b = new Uint8Array(16);
      crypto.getRandomValues(b);
      b[6] = (b[6] & 0x0f) | 0x40; // version 4
      b[8] = (b[8] & 0x3f) | 0x80; // variant 10
      const h = Array.from(b, x => x.toString(16).padStart(2, '0'));
      return [
        h.slice(0, 4).join(''), h.slice(4, 6).join(''), h.slice(6, 8).join(''),
        h.slice(8, 10).join(''), h.slice(10, 16).join('')
      ].join('-');
    }
  } catch (err) { /* fall through */ }

  // Last resort. Not cryptographically strong, but a session id only needs to be unique.
  let out = '';
  for (let i = 0; i < 32; i++) {
    if (i === 8 || i === 12 || i === 16 || i === 20) out += '-';
    out += Math.floor(Math.random() * 16).toString(16);
  }
  return out;
}

// ── Counter storage ─────────────────────────────────────────────────────────────
// In-memory mirror + synchronous write-through to sessionStorage. Write-through is
// deliberate: countNav() is called immediately before `location.href = ...`, so the
// increment has to be durable before the document goes away. The payload is three
// integers, so the write cost is irrelevant next to the correctness it buys.
let mem = null;

function safeGet() {
  try {
    return sessionStorage.getItem(STORAGE_KEY);
  } catch (err) {
    return null; // private mode / storage disabled — degrade to in-memory
  }
}

function safeSet(value) {
  try {
    sessionStorage.setItem(STORAGE_KEY, value);
  } catch (err) { /* in-memory only; instrumentation must never break the page */ }
}

function toCount(v) {
  const n = Number(v);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 0;
}

function ensure() {
  if (mem) return mem;

  const raw = safeGet();
  if (raw) {
    try {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed.session_id === 'string' && parsed.session_id) {
        mem = {
          session_id: parsed.session_id,
          key: toCount(parsed.key),
          mouse: toCount(parsed.mouse),
          nav: toCount(parsed.nav),
          // Absent in entries written before the nav_preserved addendum -> 0.
          nav_preserved: toCount(parsed.nav_preserved)
        };
        return mem;
      }
    } catch (err) { /* corrupt entry — start a fresh session below */ }
  }

  mem = { session_id: newSessionId(), key: 0, mouse: 0, nav: 0, nav_preserved: 0 };
  flush();
  return mem;
}

function flush() {
  if (!mem) return;
  safeSet(JSON.stringify(mem));
}

// ── Public API ──────────────────────────────────────────────────────────────────

/** Ensure a session_id exists and kick off the served-config fetch. Safe to call repeatedly. */
export function startSession() {
  const s = ensure();
  loadConfig();
  publishDiagnostics();
  return s.session_id;
}

export function countKey(n = 1) {
  const inc = toCount(n);
  if (!inc) return;
  ensure().key += inc;
  flush();
}

export function countMouse(n = 1) {
  const inc = toCount(n);
  if (!inc) return;
  ensure().mouse += inc;
  flush();
}

/**
 * Count a screen/context move. Every move is counted; the classification only decides
 * WHICH bucket it lands in:
 *   - `nav`           context-LOSING (scored by the current weights)
 *   - `nav_preserved` declared context-preserving (currently scored 0)
 * Nothing is discarded, so revising the allowlist later re-interprets the existing
 * baseline instead of needing data we can never collect again.
 *
 * Call this BEFORE performing the navigation — for a real page load the "from" context
 * no longer exists afterwards. The write-through to sessionStorage is synchronous, so
 * the increment survives the unload.
 *
 * Bias note: if the config has not arrived yet, the transition lands in `nav`. That is
 * the intended direction — over-counting makes the score look worse, never better.
 */
export function countNav(fromRoute, toRoute) {
  const key = transitionKey(fromRoute, toRoute);
  if (!key) return;
  const s = ensure();
  if (preservingSet.has(key)) s.nav_preserved += 1;
  else s.nav += 1;
  flush();
}

/**
 * Read-only. MUST NOT reset — the caller may still fail and need to keep accumulating.
 *
 * Returns `undefined` when NOTHING has been accumulated since the last commit. Written as
 * `effort: snapshot()`, that makes `JSON.stringify` drop the key entirely, so the field is
 * ABSENT rather than an all-zero blob. That distinction is the whole point: the server
 * accepts an explicit zero as a MEASURED score-0 correction (deliberately — a genuine
 * zero-effort correction is meaningful), so a save carrying no accumulated interaction
 * would be filed as a real score of 0. Measured live: one real correction (score 37) plus
 * one such phantom in the same session reported `avg_score: 18.5` — the baseline halved.
 *
 * The guard lives HERE, not at the seven call sites, so an eighth call site written the
 * obvious way inherits it and cannot forget.
 *
 * The test is over the four RAW counts, not over the weighted score: a session whose only
 * activity was context-preserving navigation currently scores 0 but really did happen, and
 * dropping it would destroy the very counts that make `nav_preserved` re-scorable.
 */
export function snapshot() {
  const s = ensure();
  if (!s.key && !s.mouse && !s.nav && !s.nav_preserved) return undefined;
  return {
    session_id: s.session_id,
    key: s.key,
    mouse: s.mouse,
    nav: s.nav,
    nav_preserved: s.nav_preserved
  };
}

/**
 * Reset counters after a correction unit completed successfully.
 * The session_id is kept — the session outlives the individual correction.
 * ONLY call this on a confirmed-successful batch commit.
 */
export function commit() {
  const s = ensure();
  s.key = 0;
  s.mouse = 0;
  s.nav = 0;
  s.nav_preserved = 0;
  flush();
}

/**
 * `commit()` gated on the server having actually recorded an effort row.
 *
 * A 200 is NOT proof that the correction happened. A repeat PUT whose value already matches
 * storage returns `200 {change_count: 0, created_logs: []}` and writes no effort row,
 * because nothing was corrected. Committing on `res.ok` alone therefore ERASES the effort
 * that attempt cost — and the operator, seeing nothing change, redoes it properly with a
 * handful of keystrokes. The two-attempt correction, the highest-friction event in the
 * product and the exact thing this metric exists to detect, would then record the lowest
 * score in the dataset.
 *
 * @param {object|null} resBody parsed response body of the batch PUT
 * @returns {boolean} whether the counters were reset
 */
export function commitIfRecorded(resBody) {
  const recorded = resBody && typeof resBody === 'object' ? resBody.effort_recorded : undefined;
  if (typeof recorded === 'boolean') {
    if (recorded) commit();
    return recorded;
  }
  // Field absent — an older server, or a body we could not parse. Fall back to the previous
  // behaviour (reset on success) rather than never resetting: an unbounded counter would
  // bill a whole session's browsing to whichever save finally succeeds, which is its own
  // defect and a louder one than the no-op erasure this guard exists to prevent.
  commit();
  return true;
}

// ── Route resolution ────────────────────────────────────────────────────────────
/**
 * The ONE place that maps a URL path to a route id. Every page resolves links through
 * this, so the vocabulary cannot drift between pages.
 * Returns null for anything that is not a known screen (downloads, APIs, externals).
 */
const ROUTE_BY_PATH = Object.freeze({
  '/': ROUTES.GRID,
  '/index.html': ROUTES.GRID,
  '/map_editor.html': ROUTES.MAP_EDITOR,
  // `/enrichment.html` was here until 2026-08-11. The page is deleted, so that path now 404s and
  // a mapping for it would name a screen this build cannot serve. Removing the KEY is local by
  // construction -- this is a flat lookup and `routeFromHref` returns null for anything absent,
  // so no other path's resolution moves. The ROUTE ID itself (`ROUTES.ENRICHMENT`) is deliberately
  // NOT removed here; see the note on `ROUTE_IDS`.
  '/graph.html': ROUTES.GRAPH,
  '/admin.html': ROUTES.ADMIN,
  '/trace.html': ROUTES.TRACE
});

export function routeFromHref(href) {
  if (!href) return null;
  try {
    const u = new URL(href, window.location.href);
    if (u.origin !== window.location.origin) return null; // external — not our screen
    return ROUTE_BY_PATH[u.pathname] || null;
  } catch (err) {
    return null;
  }
}

/** Route id of the page currently loaded, or null if it is not a known screen. */
export function currentRoute() {
  return ROUTE_BY_PATH[window.location.pathname] || null;
}

// ── Page-wide passive collection ────────────────────────────────────────────────
let listenersInstalled = false;
let navLinkCountingInstalled = false;

/**
 * Count plain `<a href>` navigations away from this page. Delegated at the document
 * level so links added later are covered too, and idempotent.
 *
 * Never calls preventDefault — the navigation proceeds exactly as before. The counter
 * write is synchronous, so the increment is durable before the document unloads.
 * Downloads and non-screen targets resolve to null and are skipped: a file download is
 * not a screen move.
 */
export function installNavLinkCounting(fromRoute) {
  if (navLinkCountingInstalled) return;
  if (typeof document === 'undefined') return;
  navLinkCountingInstalled = true;

  document.addEventListener('click', (e) => {
    const a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
    if (!a) return;
    if (a.hasAttribute('download')) return;
    const to = routeFromHref(a.getAttribute('href'));
    if (!to) return;
    countNav(fromRoute, to);
  }, { capture: true, passive: true });
}

/**
 * Install document-level passive counters for keystrokes and mouse clicks.
 * Idempotent, and the single source of key/mouse counts on any page that calls it —
 * do NOT also call countKey/countMouse by hand on such a page or you will double-count.
 *
 * Counting choices, both biased away from flattering the score:
 *  - `mousedown` (capture), not `click`: one physical press = one count. A drag-select
 *    across a range produces no `click` event at all, but it is one real press.
 *  - every `keydown` including auto-repeat, EXCEPT a bare modifier press. A bare
 *    Shift/Ctrl/Alt/Meta is not an interaction on its own; the chord it belongs to is
 *    counted when its non-modifier key fires.
 */
export function installGlobalListeners() {
  if (listenersInstalled) return;
  if (typeof document === 'undefined') return;
  listenersInstalled = true;

  const BARE_MODIFIERS = new Set(['Shift', 'Control', 'Alt', 'Meta', 'AltGraph', 'CapsLock']);

  document.addEventListener('keydown', (e) => {
    if (BARE_MODIFIERS.has(e.key)) return;
    countKey(1);
  }, { capture: true, passive: true });

  document.addEventListener('mousedown', () => {
    countMouse(1);
  }, { capture: true, passive: true });
}
