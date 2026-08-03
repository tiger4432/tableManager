// Harness — the keyboard contract of the [0b-a] value-suggestion cell editor.
// Run: node client2/tests/value_suggest_keys_harness.mjs   (no node_modules — vm sandbox)
//
// WHAT THIS PROVES, AND WHAT IT DOES NOT.
//
// It executes the REAL `SuggestCellEditor` from `client2/src/value_suggest.js` and the REAL
// `suppressKeyboardEvent` hook from `client2/src/grid.js` — both lifted verbatim from src,
// not re-implemented — against a MODEL of AG-Grid's keyboard pipeline. The model is the
// only re-implementation here, and it is faithful to
// `client2/node_modules/ag-grid-community/dist/ag-grid-community.js` at the four places
// that decide the outcome (cited inline at `agKeyDown` below). If AG-Grid ever changes that
// ordering, this harness keeps passing while the product breaks — so the browser
// keystroke count on the isolated stack remains the primary evidence and this is the
// regression net under it.
//
// THE ACCEPTANCE CRITERION. `full typing = N keys` versus `suggestion = P + 1`. The
// inequality only holds if the Enter that accepts the candidate IS the Enter that commits
// the cell. Every behavioural check below is therefore stated as a KEYSTROKE COUNT, using
// the same counting rule as `effort_meter.installGlobalListeners` (every keydown except a
// bare modifier), not as "the handler returned the right string".
//
// Every check is paired with a MUTATION: the same check re-runs against a deliberately
// defective variant of the same source, and the harness FAILS if the defect still passes.
// A check that cannot fail proves nothing. The sweep reports APPLIED separately from
// CAUGHT, because a mutation whose search string does not match is a silent disarm
// (cb8f01a: 8 of 18 mutations were not applying while the baseline stayed green).
//
// Line endings are normalised to LF at read time for exactly that reason.
//
// The sweep is UNCONDITIONAL — nothing here reads `process.argv`, so `npm run check:suggest-keys`
// always runs it and `prebuild` therefore gates every build on it. There is no `--mutate` flag
// to forget, unlike the valid-die harness.
//
// ── WHAT THIS HARNESS COULD NOT SEE, AND WHY THAT WAS STRUCTURAL ────────────────
//
// The first version of this file could not model either of the two HIGH defects the Escape
// contract had — not by omission, but because four of its stubs each made reality easier to
// satisfy than reality is. All four are now closed, and they are listed together because the
// pattern is the lesson:
//
//  1. THE ONLY SETTLING PRIMITIVE WAS "SETTLE EVERYTHING". `flush()` drained every timer and
//     then spun microtasks, so every dismissal path was tested in the QUIESCENT state and
//     there was no way to express "the answer came back after the operator acted". Scenario 10
//     had to hand-roll its own gate to get one late response — proof the technique existed and
//     was used exactly once. Now IN FLIGHT IS THE DEFAULT: every response is deferred, and the
//     ladder is `advance` (issue, do not answer) / `land` (answer, do not observe) / `deliver`
//     (answer and observe) / `flush` (settle). `land()` is what makes an abort genuinely too
//     late, which is the only faithful model of the H1 race.
//  2. THE STUB IGNORED `limit`. It hardcoded a 20-value cut, so with a five-value dataset
//     `truncated` was false in EVERY scenario — and the truncated regime (no caching, one
//     request per keystroke, a request outstanding on most of them) is production at
//     `REQUEST_LIMIT = 12` and is the regime the Escape defect lived in. The limit was asserted
//     only as a URL parameter, never as something that changed an answer.
//  3. `AbortController.abort()` SET A FLAG AND NOTHING ELSE, so the pending fetch resolved
//     anyway and `requestValues`'s catch branch was unreachable outside the hand-built gate.
//     It now rejects with an `AbortError`.
//  4. `isConnected` WAS STAMPED AT APPEND TIME, so `ensureList()`'s reuse test could diverge
//     from production. It is now derived from the parent chain — and reuse is exactly what lets
//     a stale `data-pending` attribute reappear on a later open.
//
// A harness whose answers can only arrive at a convenient moment cannot test dismissal.

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
const SUGGEST_PATH = join(HERE, '..', 'src', 'value_suggest.js');
const GRID_PATH = join(HERE, '..', 'src', 'grid.js');

const read = p => readFileSync(p, 'utf8').replace(/\r\n/g, '\n');

// ── Extraction ──────────────────────────────────────────────────────────────────

/** Balanced-brace slice of an arrow-function object property, e.g. `name: (p) => { ... }`. */
function extractArrowProp(src, name) {
  const re = new RegExp(`${name}\\s*:\\s*\\(([^)]*)\\)\\s*=>\\s*\\{`);
  const m = re.exec(src);
  if (!m) throw new Error(`property ${name} not found`);
  const open = src.indexOf('{', m.index + m[0].length - 1);
  let depth = 0;
  for (let j = open; j < src.length; j++) {
    const ch = src[j];
    if (ch === '{') depth++;
    else if (ch === '}') {
      depth--;
      if (depth === 0) return `function (${m[1]}) ${src.slice(open, j + 1)}`;
    }
  }
  throw new Error(`unbalanced braces for ${name}`);
}

/**
 * The module runs as a SCRIPT in the sandbox, so the ESM surface is textually flattened:
 * import lines are dropped (their two bindings are injected as globals instead) and the
 * `export` keyword is removed. Nothing inside a function body is touched — every assertion
 * below runs the real statements.
 */
function flattenModule(src) {
  return src
    .replace(/^import[\s\S]*?from\s+'[^']+';\s*$/gm, '')
    .replace(/^export\s+/gm, '');
}

// ── DOM / host stubs ────────────────────────────────────────────────────────────

/** Per-character advance used by the shrink-wrap width model below. */
const CHAR_PX = 8;
const ROW_CHROME_PX = 20;

class El {
  constructor(tag) {
    this.tagName = tag;
    this.className = '';
    this.style = {};
    this.attrs = {};
    this._children = [];
    this._parent = null;
    this._isRoot = false;
    this.listeners = {};
    this.value = '';
    this.textContent = '';
    this.offsetHeight = 100;
    this.selected = false;
    this.focused = false;
    // Overridable per element, so a test can put the cell wherever it likes on screen. The
    // right-hand edge of the viewport is not an exotic position — it is where the clamp
    // defect lived, and a fixed rect in the middle of the screen can never reach it.
    this._rect = { left: 10, top: 100, right: 160, bottom: 126, width: 150, height: 26 };
    this.classList = {
      add: c => { if (!this.className.includes(c)) this.className += ` ${c}`; },
      remove: c => { this.className = this.className.replace(c, '').trim(); },
      contains: c => this.className.includes(c)
    };
  }
  get children() { return this._children; }
  /**
   * Derived from the parent chain, not stamped at append time. `ensureList` reuses the
   * floating list only `if (eList && eList.isConnected)`, so a stub that answered this
   * wrongly would silently exercise a FRESH list where production reuses one — and reuse is
   * exactly what makes a stale `data-pending` attribute able to reappear on the next open.
   */
  get isConnected() {
    let n = this;
    while (n._parent) n = n._parent;
    return !!n._isRoot;
  }
  get innerHTML() { return ''; }
  set innerHTML(v) {
    if (v !== '') return;
    for (const c of this._children) c._parent = null;
    this._children = [];
  }
  setAttribute(k, v) { this.attrs[k] = v; }
  getAttribute(k) { return this.attrs[k]; }
  removeAttribute(k) { delete this.attrs[k]; }
  hasAttribute(k) { return k in this.attrs; }
  appendChild(c) { this._children.push(c); c._parent = this; return c; }
  addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); }
  removeEventListener(t, fn) {
    if (this.listeners[t]) this.listeners[t] = this.listeners[t].filter(f => f !== fn);
  }
  fire(t, ev) { for (const fn of this.listeners[t] || []) fn(ev || {}); }
  getBoundingClientRect() { return this._rect; }
  scrollIntoView() {}
  focus() { this.focused = true; }
  select() { this.selected = true; }
  /**
   * The list is SHRINK-WRAPPED around its widest row and then bounded by the inline
   * `min-width` / `max-width` that `positionList` writes. Modelled rather than stubbed to a
   * constant, because the horizontal clamp is only testable if the width can actually exceed
   * the viewport when the cap is missing. An explicit assignment still wins, for tests that
   * want a fixed number.
   */
  get offsetWidth() {
    if (this._offsetWidth !== undefined) return this._offsetWidth;
    const px = s => (typeof s === 'string' && s.endsWith('px') ? parseFloat(s) : NaN);
    let content = 0;
    for (const c of this._children) {
      content = Math.max(content, CHAR_PX * String(c.renderedText || '').length + ROW_CHROME_PX);
    }
    const min = px(this.style.minWidth);
    const max = px(this.style.maxWidth);
    let w = Math.max(content, isNaN(min) ? 0 : min);
    if (!isNaN(max)) w = Math.min(w, max);
    return Math.round(w);
  }
  set offsetWidth(v) { this._offsetWidth = v; }
  /** The rendered text as the operator sees it, through any wrapper elements. */
  get renderedText() {
    if (this._children.length === 0) return this.textContent || '';
    return this._children.map(c => c.renderedText).join('') + (this.textContent || '');
  }
}

// Deterministic timer queue — no wall clock anywhere in this harness.
let timerId = 0;
let timers = [];

/**
 * The clock, also deterministic. The module under test now EXPIRES what it learns from a
 * refusal (prefix floors, disabled columns, the unavailable cooldown), and expiry is not
 * testable against a wall clock without sleeping. `advanceClock` moves time by fiat.
 */
let clockMs = 1_700_000_000_000;
function advanceClock(ms) { clockMs += ms; }

/**
 * Every stubbed network response is registered here and DELIVERED ON DEMAND. See the
 * `advance` / `land` / `deliver` / `flush` ladder below for why that is the single most
 * important property of this harness.
 */
const NETS = new Set();

function makeSandbox({ dataset, tableName = 'bonding_map', onFetch }) {
  const body = new El('body');
  body._isRoot = true;
  const doc = {
    body,
    createElement: tag => new El(tag),
    createTextNode: t => { const n = new El('#text'); n.textContent = t; return n; },
    querySelector: () => null
  };
  const win = { innerHeight: 800, innerWidth: 1280, addEventListener() {}, removeEventListener() {} };

  /**
   * WHAT THE SERVER WOULD ANSWER — and it HONOURS `limit`.
   *
   * It used to hardcode `hits.slice(0, 20)` / `truncated: hits.length > 20`, which meant that
   * with a five-value dataset `truncated` was false in every single scenario. The production
   * regime at `REQUEST_LIMIT = 12` is the opposite one: a truncated answer is never cached, so
   * every keystroke issues a request and a request is outstanding on MOST of them. That is the
   * regime the Escape defect lived in, and the stub made it unreachable — the limit was only
   * ever asserted as a URL parameter, never as something that changed an answer.
   */
  const buildResponse = (url) => {
    const u = new URL(url, 'http://x');
    const prefix = u.searchParams.get('prefix') || '';
    const limit = Number(u.searchParams.get('limit')) || 20;
    const col = decodeURIComponent(u.pathname.split('/columns/')[1].split('/values')[0]);
    const pool = dataset[col];
    if (pool === undefined) {
      return { status: 400, ok: false, json: async () => ({ detail: 'not declared' }) };
    }
    if (pool === null) {
      return { status: 200, ok: true, json: async () => ({ values: [], truncated: false, unavailable_reason: 'index missing' }) };
    }
    const lower = prefix.toLowerCase();
    const hits = pool.filter(v => v.toLowerCase().startsWith(lower));
    return {
      status: 200, ok: true,
      json: async () => ({ values: hits.slice(0, limit), truncated: hits.length > limit })
    };
  };

  /**
   * IN FLIGHT IS THE DEFAULT. Nothing resolves until a test says so.
   *
   * The previous stub answered synchronously, so `flush()` could only ever observe a settled
   * world and every dismissal path was tested in the quiescent state. That is a STRUCTURAL
   * blind spot, not an omission: a harness where the answer can only arrive at a convenient
   * moment cannot express "the operator pressed Escape and the answer came back afterwards",
   * which is the whole of the defect. Scenario 10 had to hand-roll its own gate to get one
   * late response — proof the technique was available and used exactly once.
   */
  const net = { pending: [], issued: 0, landed: 0 };
  NETS.add(net);
  net.inFlight = () => net.pending.filter(e => !e.settled).length;
  net.land = () => {
    const q = net.pending;
    net.pending = [];
    let n = 0;
    for (const e of q) { if (e.land()) n += 1; }
    return n;
  };

  const fetchStub = (url, opts) => {
    // A scenario-supplied `onFetch` keeps full control, including its own gating.
    if (onFetch) {
      const r = onFetch(url);
      if (r) return Promise.resolve(r);
    }
    net.issued += 1;
    return new Promise((resolve, reject) => {
      const entry = { url, settled: false };
      entry.land = () => {
        if (entry.settled) return false;
        entry.settled = true;
        net.landed += 1;
        resolve(buildResponse(url));
        return true;
      };
      // A REAL abort rejection. The stub used to set a flag and let the request resolve
      // anyway, so `requestValues`'s catch branch — and with it every "the abort lost the
      // race" question — was only reachable through a hand-built gate.
      entry.abort = () => {
        if (entry.settled) return;
        entry.settled = true;
        const err = new Error('The user aborted a request.');
        err.name = 'AbortError';
        reject(err);
      };
      net.pending.push(entry);
      const signal = opts && opts.signal;
      if (signal) signal.__onAbort = entry.abort;
    });
  };

  const sandbox = {
    API_BASE: 'http://api',
    state: { currentTable: tableName, selectedCellsMap: {}, dragStartCell: null, dragEndCell: null,
             visibleColIndexMap: {}, txModeActive: false, pendingTxEdits: {} },
    document: doc,
    window: win,
    console: { debug() {}, warn() {}, error() {}, log() {} },
    fetch: fetchStub,
    AbortController: class {
      constructor() { this.signal = {}; }
      abort() {
        this.aborted = true;
        const onAbort = this.signal && this.signal.__onAbort;
        if (onAbort) onAbort();
      }
    },
    URL,
    Date: { now: () => clockMs },
    setTimeout: (fn) => { const id = ++timerId; timers.push({ id, fn }); return id; },
    clearTimeout: (id) => { timers = timers.filter(t => t.id !== id); },
    Math, JSON, String, Number, Array, Object, Set, Map, RegExp, Promise, Error, isNaN
  };
  sandbox.globalThis = sandbox;
  sandbox.__net = net;
  return sandbox;
}

// ── The settling ladder ─────────────────────────────────────────────────────────
// Four rungs, because the defects live BETWEEN them. `flush` (settle everything) is the only
// rung the harness used to have, and it is the one rung that cannot express a dismissal.
const microtasks = async (n = 12) => { for (let i = 0; i < n; i++) await new Promise(r => setImmediate(r)); };

/** Run every scheduled timer. Requests get ISSUED; no answer comes back. */
async function advance() {
  const q = timers;
  timers = [];
  for (const t of q) t.fn();
  await microtasks(4);
}

/**
 * Resolve every outstanding response WITHOUT letting the module observe it yet.
 * The answer is now in the microtask queue — the one place an abort cannot reach it, and
 * therefore the only faithful way to model "Escape came too late to stop the answer".
 * @returns {number} how many answers were released
 */
function land() {
  let n = 0;
  for (const net of NETS) n += net.land();
  return n;
}

/** Release every answer AND let the module act on it. */
async function deliver() {
  land();
  await microtasks(12);
}

/** Settle the world completely: timers, answers, and the timers those answers arm. */
async function flush() {
  for (let round = 0; round < 6; round++) {
    await advance();
    await deliver();
  }
}

// ── The AG-Grid model ───────────────────────────────────────────────────────────
/**
 * Faithful to ag-grid-community@35, at the four places that decide the outcome. Line
 * numbers are from `client2/node_modules/ag-grid-community/dist/ag-grid-community.js`
 * and may drift with a version bump; the function names will not.
 *
 *  1. `processKeyboardEvent` (~24553) returns early if `keyboardEvent.defaultPrevented`.
 *  2. `processCellKeyboardEvent` (~24564) consults `suppressKeyboardEvent` via
 *     `_isUserSuppressingKeyboardEvent(gos, event, node, column, editing)` FIRST, and only
 *     calls `cellCtrl.onKeyDown(event)` when it returns falsy. THIS is why writing the
 *     candidate into the input from inside the hook lands before the commit reads it.
 *  3. `CellKeyboardListenerFeature.onKeyDown` (~43454): ENTER -> `onEnterKeyDown`,
 *     ESCAPE -> `onEscapeKeyDown`, TAB -> `onTabKeyDown`, arrows -> `onNavigationKeyDown`
 *     which RETURNS EARLY while editing (~43485).
 *  4. `onEnterKeyDown` (~43534): editing and not Ctrl -> `editSvc.stopEditing(...)`, and
 *     `_valueFromEditor` (~42970) takes the value from `cellEditor.getValue()`.
 */
function makeGrid({ suppressKeyboardEvent, EditorCtor, cellValue, onCommit }) {
  const g = {
    keystrokes: 0,
    editing: false,
    editor: null,
    committed: [],        // every value the grid actually wrote
    cancelled: 0,
    focusMoved: 0,
    stored: cellValue
  };

  const BARE_MODIFIERS = new Set(['Shift', 'Control', 'Alt', 'Meta', 'AltGraph', 'CapsLock']);

  function makeEvent(key, opts = {}) {
    const ev = {
      key, ctrlKey: false, metaKey: false, altKey: false, shiftKey: false,
      isComposing: false, keyCode: 0, defaultPrevented: false,
      preventDefault() { this.defaultPrevented = true; },
      ...opts
    };
    return ev;
  }

  function startEdit(eventKey) {
    g.editor = new EditorCtor();
    g.editor.init({
      value: g.stored,
      eventKey,
      cellStartedEdit: true,
      column: { getColId: () => g.colId },
      colDef: {},
      node: {}, data: {}, rowIndex: 0,
      eGridCell: new El('div'),
      stopEditing: () => stopEdit(false),
      onKeyDown: () => {},
      api: {}
    });
    g.editor.afterGuiAttached();
    g.editing = true;
  }

  function stopEdit(cancel) {
    if (!g.editing) return;
    if (cancel) g.cancelled += 1;
    else {
      const v = g.editor.getValue();
      g.stored = v;
      g.committed.push(v);
      if (onCommit) onCommit(v);
    }
    g.editing = false;
    g.editor.destroy();
    g.editor = null;
  }

  /** One physical key press. Returns the event so a test can inspect defaultPrevented. */
  function key(k, opts = {}) {
    const ev = makeEvent(k, opts);
    if (!BARE_MODIFIERS.has(k)) g.keystrokes += 1; // effort_meter counting rule

    // (1) defaultPrevented short-circuit
    if (ev.defaultPrevented) return ev;

    // (2) suppressKeyboardEvent first
    const suppressed = suppressKeyboardEvent({
      event: ev, editing: g.editing, api: g.api, node: {}, colDef: {},
      column: { getColId: () => g.colId }, data: {}
    });
    if (suppressed) return ev;

    // (3)/(4) cellCtrl.onKeyDown
    if (k === 'Enter') {
      if (g.editing) {
        if (ev.ctrlKey || ev.metaKey) return ev; // applyBulkEdit branch, not modelled here
        stopEdit(false);
      } else {
        startEdit('Enter');
      }
    } else if (k === 'Escape') {
      if (g.editing) stopEdit(true);
    } else if (k === 'Tab') {
      if (g.editing) { stopEdit(false); g.focusMoved += 1; }
      else g.focusMoved += 1;
    } else if (k === 'ArrowDown' || k === 'ArrowUp' || k === 'ArrowLeft' || k === 'ArrowRight') {
      if (!g.editing) g.focusMoved += 1; // onNavigationKeyDown returns early while editing
    } else if (k.length === 1) {
      // `processCharacter` (~43624): starts the edit AND calls preventDefault for a custom
      // editor, so the browser does NOT insert this character — the editor seeds it from
      // `params.eventKey`. Already editing -> returns early, so the browser DOES insert.
      if (!g.editing) {
        startEdit(k);
        ev.preventDefault();
      } else {
        g.editor.eInput.value += k;
        g.editor.eInput.fire('input');
      }
    }
    return ev;
  }

  g.key = key;
  g.startEdit = startEdit;
  g.colId = 'pkg_id';
  return g;
}

// ── Loading ─────────────────────────────────────────────────────────────────────

/** The real `RANGE_ARROW_DELTA` declaration, lifted verbatim — the hook reads it. */
function extractConst(src, name) {
  const re = new RegExp(`const\\s+${name}\\s*=`);
  const m = re.exec(src);
  if (!m) throw new Error(`const ${name} not found`);
  const semi = src.indexOf(');', m.index);
  if (semi === -1) throw new Error(`const ${name}: no terminator`);
  return src.slice(m.index, semi + 2);
}

function load({ suggestSrc, gridSrc, dataset, tableName, onFetch }) {
  const sandbox = makeSandbox({ dataset, tableName, onFetch });
  const calls = { extendRange: 0, clearRange: 0, bulkFill: [] };
  sandbox.__calls = calls;
  // Collaborators the hook reaches for that are NOT under test here. Stubbed, and their
  // invocation is recorded so a check can assert the pre-existing keyboard-range branches
  // still fire (0b-c, committed at 883b680, must not regress).
  sandbox.extendRangeByKeyboard = () => { calls.extendRange += 1; return true; };
  sandbox.clearRangeSelection = () => { calls.clearRange += 1; };
  sandbox.applyValueToSelectedRange = v => { calls.bulkFill.push(v); };

  const ctx = vm.createContext(sandbox);
  // `class`/`const` at the top level of a vm SCRIPT are lexical, so they never become
  // properties of the context's global. The epilogue publishes exactly the module's export
  // surface — and only that surface, so a test cannot reach past it into a private.
  vm.runInContext(
    flattenModule(suggestSrc)
    + '\n;globalThis.__mod = { SuggestCellEditor, handleEditorKey, isSuggestEditorActive,'
    + ' getSuggestStats, resetSuggestStats, resetSuggestLearning };',
    ctx, { filename: 'value_suggest.js' });
  const hookSrc = extractArrowProp(gridSrc, 'suppressKeyboardEvent');
  vm.runInContext(
    `${extractConst(gridSrc, 'RANGE_ARROW_DELTA')}\nvar __hook = ${hookSrc};`,
    ctx, { filename: 'grid.js#suppressKeyboardEvent' });
  return {
    ctx,
    sandbox,
    calls,
    net: sandbox.__net,
    SuggestCellEditor: sandbox.__mod.SuggestCellEditor,
    hook: sandbox.__hook,
    stats: () => sandbox.__mod.getSuggestStats(),
    resetLearning: () => sandbox.__mod.resetSuggestLearning(),
    /** The ONE shared floating list, read out of the sandbox's document. */
    sharedList: () => sandbox.document.body.children
      .find(c => String(c.className).includes('value-suggest-list'))
  };
}

// ── Scoring ─────────────────────────────────────────────────────────────────────
let pass = 0, fail = 0;
let quiet = false;          // mutant runs are EXPECTED to fail; their noise is not evidence
const failures = [];

function check(name, actual, expected) {
  const a = JSON.stringify(actual), e = JSON.stringify(expected);
  if (a === e) { pass++; if (!quiet) console.log(`  ok   ${name}`); }
  else {
    fail++; failures.push(name);
    if (!quiet) console.error(`  FAIL ${name}\n       expected ${e}\n       actual   ${a}`);
  }
}

// ── Scenarios ───────────────────────────────────────────────────────────────────
// One realistic dataset. `pkg_id` values are 12 characters, which is what makes the
// arithmetic interesting: N = 12 against P + 1.
const DATASET = {
  pkg_id: ['TFBGA-296-A1', 'TFBGA-296-A2', 'TFBGA-296-B1', 'TQFP-064-C3', 'WLCSP-121-D0'],
  lot_id: ['K23A0011', 'K23A0012', 'K23A0013'],
  // MORE VALUES THAN `REQUEST_LIMIT`, so this column answers `truncated` for any short prefix.
  // It exists because the truncated regime is PRODUCTION at limit 12 and no scenario could
  // reach it while the stub ignored the limit: 40 values sharing 'WF0' means the answer is cut
  // at 12, never cached, and therefore re-asked on every keystroke.
  wafer_id: Array.from({ length: 40 }, (_, i) => `WF0${String(i + 1).padStart(3, '0')}`),
  // A long value on a column an operator types into near the right edge of the screen.
  long_note: ['NEEDS-REWORK-AFTER-PROBE-2ND-PASS-CONFIRMED-BY-QA-2026', 'NEEDS-HOLD'],
  // A column the endpoint refuses (undeclared) — the silent-fallback path.
  scratch: undefined,
  // A column the endpoint cannot answer for (index missing/invalid, timeout).
  legacy_note: null
};

/** Type a string one character at a time, letting each answer come back before the next key. */
async function typeInto(g, text) {
  for (const ch of text) { g.key(ch); await flush(); }
}

/**
 * Type WITHOUT letting any answer come back — timers run, requests are issued, nothing lands.
 * This is the state the operator is in for most of a typed prefix in the truncated regime, and
 * it is the state every dismissal path used to be untested in.
 */
async function typePending(g, text) {
  for (const ch of text) { g.key(ch); await advance(); }
}

/**
 * SCORE A — the full-typing baseline. N characters + one Enter to commit.
 * SCORE B — prefix + one Enter, where that single Enter both accepts and commits.
 */
async function scoreFullTyping(mod) {
  const g = makeGrid({ suppressKeyboardEvent: mod.hook, EditorCtor: mod.SuggestCellEditor, cellValue: '' });
  const target = 'TFBGA-296-A2';
  await typeInto(g, target);
  // The list is open on the typed text; Escape would be needed only if the exact match were
  // not the highlight. It IS (see `applyValues`), so Enter commits the same string.
  g.key('Enter');
  await flush();
  return { keystrokes: g.keystrokes, committed: g.committed, cancelled: g.cancelled };
}

async function scorePrefixEnter(mod, prefix = 'TFBGA-296-A2'.slice(0, 5)) {
  const g = makeGrid({ suppressKeyboardEvent: mod.hook, EditorCtor: mod.SuggestCellEditor, cellValue: '' });
  await typeInto(g, prefix);
  g.key('Enter');
  await flush();
  return { keystrokes: g.keystrokes, committed: g.committed, cancelled: g.cancelled };
}

/**
 * KEYS TO A COMPLETED COMMIT — the single number the acceptance criterion is about.
 *
 * Worth being explicit about why this exists next to `scorePrefixEnter`: counting
 * keystrokes ALONE does not catch the two-Enter defect. Under a mutant that accepts on
 * Enter but refuses to commit, the count after one Enter is still 6 — it is 6 keys that
 * achieved nothing. So the score has to be "keys until the grid actually wrote a value",
 * which is 6 when accept and commit are one press and 7 when they are two.
 * Bounded at 4 extra presses so a mutant that never commits terminates instead of hanging.
 */
async function scoreKeysToCommit(mod, prefix = 'TFBGA') {
  const g = makeGrid({ suppressKeyboardEvent: mod.hook, EditorCtor: mod.SuggestCellEditor, cellValue: '' });
  await typeInto(g, prefix);
  for (let i = 0; i < 4 && g.committed.length === 0; i++) {
    g.key('Enter');
    await flush();
  }
  return { keystrokes: g.keystrokes, committed: g.committed, presses: g.keystrokes - prefix.length };
}

async function runChecks(mod, { label = '', strict = true } = {}) {
  const results = {};

  // ── 1. THE ONE-ENTER PROPERTY, counted in keystrokes ──────────────────────────
  const full = await scoreFullTyping(mod);
  const pfx = await scorePrefixEnter(mod);
  results.fullKeys = full.keystrokes;
  results.fullCommitted = full.committed;
  results.prefixKeys = pfx.keystrokes;
  results.prefixCommitted = pfx.committed;

  if (strict) {
    check('full typing: 12 chars + Enter = 13 keystrokes', full.keystrokes, 13);
    check('full typing commits the typed value once', full.committed, ['TFBGA-296-A2']);
    // 'TFBGA' = 5 chars. P + 1 = 6. THE criterion: not 7.
    check('prefix+Enter: 5 chars + ONE Enter = 6 keystrokes', pfx.keystrokes, 6);
    check('ONE Enter both accepted and committed (single commit, no cancel)',
      { commits: pfx.committed.length, cancelled: pfx.cancelled }, { commits: 1, cancelled: 0 });
    check('the committed value is the highlighted candidate, not the typed prefix',
      pfx.committed[0], 'TFBGA-296-A1');
    check('measured saving equals the predicted N-(P+1)', full.keystrokes - pfx.keystrokes, 7);

    // The criterion, stated as ONE number: keys spent until the grid wrote a value.
    const toCommit = await scoreKeysToCommit(mod);
    results.keysToCommit = toCommit.keystrokes;
    results.enterPresses = toCommit.presses;
    check('KEYS TO A COMMITTED VALUE = P + 1 = 6 (not 7)', toCommit.keystrokes, 6);
    check('exactly ONE Enter press was spent', toCommit.presses, 1);
    check('and it wrote the candidate', toCommit.committed, ['TFBGA-296-A1']);
  }

  // ── 2. FIRST MATCH HIGHLIGHTED ON OPEN (no arrow key needed) ──────────────────
  {
    const g = makeGrid({ suppressKeyboardEvent: mod.hook, EditorCtor: mod.SuggestCellEditor, cellValue: '' });
    await typeInto(g, 'TFBGA');
    results.highlightOnOpen = g.editor ? g.editor.highlight : null;
    results.listLen = g.editor ? g.editor.values.length : 0;
    if (strict) {
      check('list opened with 3 matches', results.listLen, 3);
      check('highlight is index 0 before any arrow key', results.highlightOnOpen, 0);
      check('exactly zero arrow presses were needed', g.keystrokes, 5);
    }
    g.key('Enter'); await flush();
  }

  // ── 3. ARROWS MOVE THE HIGHLIGHT AND NOTHING ELSE ─────────────────────────────
  {
    const g = makeGrid({ suppressKeyboardEvent: mod.hook, EditorCtor: mod.SuggestCellEditor, cellValue: '' });
    await typeInto(g, 'TFBGA');
    const d1 = g.key('ArrowDown');
    g.key('ArrowDown');
    results.afterTwoDown = g.editor && g.editor.highlight;
    g.key('ArrowUp');
    results.afterOneUp = g.editor && g.editor.highlight;
    results.focusMovedDuringArrows = g.focusMoved;
    // preventDefault is the ONLY thing that stops the browser moving the caret to the
    // start/end of the input while the highlight moves. A DOM caret is not modelled here,
    // so this asserts the mechanism rather than its visible effect — without it, an arrow
    // that "works" (the highlight moves) still scrambles the text position.
    results.arrowConsumed = d1.defaultPrevented;
    g.key('Enter'); await flush();
    results.arrowCommitted = g.committed[0];
    if (strict) {
      check('two ArrowDown -> highlight 2', results.afterTwoDown, 2);
      check('one ArrowUp -> highlight 1', results.afterOneUp, 1);
      check('arrows never moved cell focus while editing', results.focusMovedDuringArrows, 0);
      check('the arrow event was consumed (preventDefault), so the caret cannot jump',
        results.arrowConsumed, true);
      check('Enter commits the arrowed-to candidate', results.arrowCommitted, 'TFBGA-296-A2');
      check('5 + 3 arrows + Enter = 9 keystrokes', g.keystrokes, 9);
    }
  }

  // ── 4. ESCAPE DISMISSES THE LIST AND LEAVES THE TYPED TEXT ────────────────────
  {
    const g = makeGrid({ suppressKeyboardEvent: mod.hook, EditorCtor: mod.SuggestCellEditor, cellValue: 'OLD' });
    await typeInto(g, 'TFBGA');
    g.key('Escape');
    results.escStillEditing = g.editing;
    results.escInputText = g.editor ? g.editor.eInput.value : null;
    results.escListOpen = g.editor ? g.editor.listOpen : null;
    results.escCancelled = g.cancelled;
    g.key('Enter'); await flush();
    results.escCommitted = g.committed[0];
    if (strict) {
      check('Escape did NOT cancel the edit', { editing: results.escStillEditing, cancelled: results.escCancelled },
        { editing: true, cancelled: 0 });
      check('Escape left the typed text intact', results.escInputText, 'TFBGA');
      check('Escape closed the list', results.escListOpen, false);
      check('the next Enter commits the TYPED text, not a candidate', results.escCommitted, 'TFBGA');
    }
  }

  // ── 4-bis. A SECOND ESCAPE IS STILL A CANCEL ──────────────────────────────────
  {
    const g = makeGrid({ suppressKeyboardEvent: mod.hook, EditorCtor: mod.SuggestCellEditor, cellValue: 'OLD' });
    await typeInto(g, 'TFBGA');
    g.key('Escape'); g.key('Escape');
    results.doubleEscCancelled = g.cancelled;
    results.doubleEscCommitted = g.committed.length;
    if (strict) {
      check('second Escape cancels the edit (nothing committed)',
        { cancelled: results.doubleEscCancelled, commits: results.doubleEscCommitted }, { cancelled: 1, commits: 0 });
    }
  }

  // ── 5. TAB STILL LEAVES THE FIELD ─────────────────────────────────────────────
  {
    const g = makeGrid({ suppressKeyboardEvent: mod.hook, EditorCtor: mod.SuggestCellEditor, cellValue: '' });
    await typeInto(g, 'TFBGA');
    g.key('Tab'); await flush();
    results.tabCommitted = g.committed;
    results.tabFocusMoved = g.focusMoved;
    results.tabKeys = g.keystrokes;
    if (strict) {
      check('Tab committed once and moved focus', { commits: results.tabCommitted.length, moved: results.tabFocusMoved },
        { commits: 1, moved: 1 });
      check('Tab accepted the highlighted candidate', results.tabCommitted[0], 'TFBGA-296-A1');
      check('Tab cost one key: 5 + Tab = 6', results.tabKeys, 6);
    }
  }

  // ── 6. CTRL+ENTER STILL REACHES THE PRE-EXISTING BULK-FILL BRANCH ─────────────
  {
    const g = makeGrid({ suppressKeyboardEvent: mod.hook, EditorCtor: mod.SuggestCellEditor, cellValue: '' });
    // The real branch calls `params.api.getCellEditorInstances()` then
    // `applyValueToSelectedRange(editingValue)`. Wire the api so the branch runs for real;
    // the sink is the recorded stub installed in `load`.
    g.api = {
      getCellEditorInstances: () => (g.editor ? [g.editor] : []),
      stopEditing: () => { g.editing = false; }
    };
    await typeInto(g, 'TFBGA');
    const ev = g.key('Enter', { ctrlKey: true });
    results.bulkValue = mod.calls.bulkFill[mod.calls.bulkFill.length - 1] ?? null;
    results.bulkSuppressed = ev.defaultPrevented;
    if (strict) {
      check('Ctrl+Enter reached the bulk-fill branch with the ACCEPTED candidate',
        results.bulkValue, 'TFBGA-296-A1');
      check('Ctrl+Enter was consumed by the grid hook (preventDefault)', results.bulkSuppressed, true);
    }
  }

  // ── 7. THE EMPTY PREFIX DOES NOT OPEN THE LIST ────────────────────────────────
  // Three ways an empty prefix is actually reached in the product, because only the third
  // and fourth reach the query path — the first two are refused earlier, and a test that
  // only used them would pass against a client floor of 0 and prove nothing.
  {
    const g = makeGrid({ suppressKeyboardEvent: mod.hook, EditorCtor: mod.SuggestCellEditor, cellValue: '' });
    const before = mod.stats().requests;
    g.key('Enter');            // (a) open the editor on an empty cell, no character typed
    await flush();
    results.emptyListOpen = g.editor ? g.editor.listOpen : null;
    results.emptyRequests = mod.stats().requests - before;

    // (b) the edit is STARTED by Backspace, so the editor opens with an empty input and
    // `init` runs its own first query — this is the path a floor of 0 would let through.
    const g2 = makeGrid({ suppressKeyboardEvent: mod.hook, EditorCtor: mod.SuggestCellEditor, cellValue: 'OLD' });
    const before2 = mod.stats().requests;
    g2.startEdit('Backspace');
    await flush();
    results.backspaceOpenRequests = mod.stats().requests - before2;
    results.backspaceListOpen = g2.editor ? g2.editor.listOpen : null;

    // (c) the operator types and then deletes back to empty — an `input` event with ''.
    const g3 = makeGrid({ suppressKeyboardEvent: mod.hook, EditorCtor: mod.SuggestCellEditor, cellValue: '' });
    await typeInto(g3, 'TF');
    const before3 = mod.stats().requests;
    g3.editor.eInput.value = '';
    g3.editor.eInput.fire('input');
    await flush();
    results.clearedRequests = mod.stats().requests - before3;
    results.clearedListOpen = g3.editor ? g3.editor.listOpen : null;

    if (strict) {
      check('empty prefix (opened on an empty cell): no list', results.emptyListOpen, false);
      check('empty prefix (opened on an empty cell): not one request issued', results.emptyRequests, 0);
      check('empty prefix (edit started by Backspace): no request, no list',
        { req: results.backspaceOpenRequests, open: results.backspaceListOpen }, { req: 0, open: false });
      check('empty prefix (deleted back to empty): no request, and the list closes',
        { req: results.clearedRequests, open: results.clearedListOpen }, { req: 0, open: false });
    }
  }

  // ── 8. A NON-SUGGESTIBLE COLUMN FALLS BACK TO PLAIN TYPING, SILENTLY ──────────
  {
    const g = makeGrid({ suppressKeyboardEvent: mod.hook, EditorCtor: mod.SuggestCellEditor, cellValue: '' });
    g.colId = 'scratch'; // 400 from the endpoint
    await typeInto(g, 'ABCD');
    results.rejectListOpen = g.editor ? g.editor.listOpen : null;
    g.key('Enter'); await flush();
    results.rejectCommitted = g.committed[0];
    results.rejectKeys = g.keystrokes;
    const st = mod.stats();
    results.rejectDisabled = st.disabled.some(k => k.includes('scratch'));
    if (strict) {
      check('refused column: no list ever opens', results.rejectListOpen, false);
      check('refused column: the typed text commits unchanged', results.rejectCommitted, 'ABCD');
      check('refused column: 4 chars + Enter = 5 keystrokes (identical to a plain editor)',
        results.rejectKeys, 5);
      check('refused column: suggestions switched off for the session', results.rejectDisabled, true);
    }
  }

  // ── 8-bis. `unavailable_reason` IS ALSO A SILENT FALLBACK ─────────────────────
  {
    const fresh = load({ suggestSrc: mod.suggestSrc, gridSrc: mod.gridSrc, dataset: DATASET });
    fresh.suggestSrc = mod.suggestSrc; fresh.gridSrc = mod.gridSrc;
    const g = makeGrid({ suppressKeyboardEvent: fresh.hook, EditorCtor: fresh.SuggestCellEditor, cellValue: '' });
    g.colId = 'legacy_note'; // 200 + unavailable_reason, values: []
    await typeInto(g, 'ABC');
    results.unavailListOpen = g.editor ? g.editor.listOpen : null;
    // The reason must be RECOGNISED, not merely tolerated. `values: []` alongside a reason
    // looks exactly like an honest empty result, so "no list appeared" cannot distinguish
    // the two. Two observables can: the counter, and — the part that actually matters —
    // whether an EMPTY answer got cached as a complete result. If it did, every longer
    // prefix would be narrowed locally from an empty set and the column would never be
    // asked again, so an index built five minutes later would never take effect.
    results.unavailCount = fresh.stats().unavailable;
    results.unavailRequests = fresh.stats().requests;
    results.unavailNarrows = fresh.stats().localNarrows;
    g.key('Enter'); await flush();
    results.unavailCommitted = g.committed[0];
    results.unavailDisabled = fresh.stats().disabled.some(k => k.includes('legacy_note'));
    results.unavailCooled = Object.keys(fresh.stats().cooldowns).some(k => k.includes('legacy_note'));
    if (strict) {
      check('unavailable column: no list', results.unavailListOpen, false);
      check('unavailable column: the typed text commits unchanged', results.unavailCommitted, 'ABC');
      check('unavailable column is NOT permanently disabled (an index can be built later)',
        results.unavailDisabled, false);
      // ONE, not three. This assertion used to read `3` — one request per typed character —
      // and it was DOCUMENTING THE DEFECT as if it were the contract: the expensive refusal
      // path was the one path with no backoff at all. See `UNAVAILABLE_COOLDOWN_MS`.
      check('the named reason was recognised, not read as an empty result',
        results.unavailCount, 1);
      check('and it is NOT cached as a complete empty result (narrowing must never serve it)',
        results.unavailNarrows, 0);
      check('the column went into cooldown, so 3 characters cost ONE request, not 3',
        { requests: results.unavailRequests, cooled: results.unavailCooled },
        { requests: 1, cooled: true });
    }
  }

  // ── 8-ter. THE WIRE LIMIT IS WHAT KEEPS THE ENDPOINT UNDER ITS TIME BUDGET ────
  {
    // Measured 2026-07-30: t = 0.84 ms + 0.61 ms x (limit + 1), essentially independent of
    // table size. limit 12 -> ~8.7 ms; limit 20 -> 15.3 ms, over the 10 ms gate at EVERY
    // size. So the limit on the wire is a latency contract, not a display preference, and
    // it is asserted on the wire rather than on the constant.
    const seen = [];
    const fresh = load({
      suggestSrc: mod.suggestSrc, gridSrc: mod.gridSrc, dataset: DATASET,
      onFetch: (url) => { seen.push(Number(new URL(url, 'http://x').searchParams.get('limit'))); return null; }
    });
    fresh.suggestSrc = mod.suggestSrc; fresh.gridSrc = mod.gridSrc;
    const g = makeGrid({ suppressKeyboardEvent: fresh.hook, EditorCtor: fresh.SuggestCellEditor, cellValue: '' });
    await typeInto(g, 'T');
    results.wireLimit = seen[0];
    const modelledMs = +(0.84 + 0.61 * (results.wireLimit + 1)).toFixed(2);
    results.modelledMs = modelledMs;
    if (strict) {
      check('the requested limit is 12', results.wireLimit, 12);
      check(`the modelled endpoint cost (${modelledMs} ms) is under the 10 ms gate`,
        modelledMs < 10, true);
    }
  }

  // ── 9. REQUESTS PER TYPED PREFIX ──────────────────────────────────────────────
  {
    // Fresh module so the complete-result cache starts empty for this column.
    const fresh = load({ suggestSrc: mod.suggestSrc, gridSrc: mod.gridSrc, dataset: DATASET });
    fresh.suggestSrc = mod.suggestSrc; fresh.gridSrc = mod.gridSrc;
    const g = makeGrid({ suppressKeyboardEvent: fresh.hook, EditorCtor: fresh.SuggestCellEditor, cellValue: '' });
    g.colId = 'lot_id';
    await typeInto(g, 'K23A00'); // 6 characters
    results.reqFor6Chars = fresh.stats().requests;
    results.localNarrows = fresh.stats().localNarrows;
    if (strict) {
      // First character -> one request, whose answer is COMPLETE (3 values, not truncated),
      // so every refinement narrows locally. One request for six characters.
      check('6 typed characters cost exactly 1 request', results.reqFor6Chars, 1);
      check('the other 5 refinements were served locally', results.localNarrows, 5);
    }
  }

  // ── 9-bis. THE NARROWING SNAPSHOT DIES WITH THE CELL EDIT ─────────────────────
  //
  // Found by browser E2E on the isolated stack, not by this harness: "DEV" was committed to
  // `inventory_master.category`, the very next cell typed "DEV", and the list did not offer
  // it back — local narrowing was still serving a value set cached before that commit. The
  // subset property is only sound against a snapshot, and the snapshot goes stale the
  // instant anyone commits a new value to the column.
  {
    // The dataset grows between the two edits, exactly as a commit makes it grow.
    const pool = ['K23A0011', 'K23A0012'];
    const fresh = load({
      suggestSrc: mod.suggestSrc, gridSrc: mod.gridSrc,
      dataset: { get lot_id() { return pool.slice(); } }
    });
    fresh.suggestSrc = mod.suggestSrc; fresh.gridSrc = mod.gridSrc;

    const g1 = makeGrid({ suppressKeyboardEvent: fresh.hook, EditorCtor: fresh.SuggestCellEditor, cellValue: '' });
    g1.colId = 'lot_id';
    await typeInto(g1, 'K23');            // caches a COMPLETE result for 'K23'
    g1.key('Enter'); await flush();        // editor torn down here

    pool.push('K23NEW');                   // stands in for the value just committed

    const g2 = makeGrid({ suppressKeyboardEvent: fresh.hook, EditorCtor: fresh.SuggestCellEditor, cellValue: '' });
    g2.colId = 'lot_id';
    await typeInto(g2, 'K23');
    results.afterCommitValues = g2.editor ? g2.editor.values.slice() : null;
    if (strict) {
      check('a value that appeared after the previous edit is offered in the next one',
        (results.afterCommitValues || []).includes('K23NEW'), true);
    }
  }

  // ── 10. A STALE RESPONSE CANNOT OVERWRITE A NEWER LIST ────────────────────────
  //
  // The scenario has to be chosen carefully or it tests the wrong guard. There are two
  // filters on a landing response: `result.seq !== requestSeq` (IDENTITY — is this the
  // answer to the newest question?) and `this.eInput.value !== prefix` (CONTENT — does the
  // answer still match what is typed?). The obvious "type T, then TQ, T answers late" case
  // is caught by the CONTENT filter alone, so it proves nothing about the identity guard.
  //
  // What only the identity guard catches: type forward and then BACK to the same prefix.
  // Now two distinct requests carry the SAME prefix string, the content filter cannot tell
  // them apart, and the older one must still lose. This is reachable in one keystroke
  // (Backspace) and the responses genuinely can differ — another operator's committed value
  // arrives through the very `batch_row_*` deltas this grid subscribes to.
  {
    let gate = null;
    let call = 0;
    const fresh = load({
      suggestSrc: mod.suggestSrc, gridSrc: mod.gridSrc, dataset: DATASET,
      onFetch: (url) => {
        const prefix = new URL(url, 'http://x').searchParams.get('prefix');
        if (prefix !== 'T') return null;
        const n = ++call;
        if (n === 1) {
          // The FIRST 'T' request is held open and released last.
          return new Promise(res => { gate = () => res({
            status: 200, ok: true,
            json: async () => ({ values: ['STALE-1'], truncated: true })
          }); });
        }
        return { status: 200, ok: true,
                 json: async () => ({ values: ['FRESH-2'], truncated: true }) };
      }
    });
    fresh.suggestSrc = mod.suggestSrc; fresh.gridSrc = mod.gridSrc;
    const g = makeGrid({ suppressKeyboardEvent: fresh.hook, EditorCtor: fresh.SuggestCellEditor, cellValue: '' });

    g.key('T');                       // request #1 for 'T', held; truncated so no narrowing
    let q = timers; timers = [];
    for (const t of q) t.fn();
    await new Promise(r => setImmediate(r));

    g.editor.eInput.value = 'TQ';     // request #2 for 'TQ'
    g.editor.eInput.fire('input');
    await flush();

    g.editor.eInput.value = 'T';      // Backspace -> request #3, prefix 'T' AGAIN
    g.editor.eInput.fire('input');
    await flush();
    const afterFresh = g.editor.values.slice();

    if (gate) gate();                 // request #1 finally answers, same prefix as #3
    await flush();
    results.newValues = afterFresh;
    results.staleValues = g.editor ? g.editor.values.slice() : null;
    if (strict) {
      check('the newest answer for the re-typed prefix is showing', results.newValues, ['FRESH-2']);
      check('the late answer for the SAME prefix from an older request did not replace it',
        results.staleValues, ['FRESH-2']);
    }
  }

  // ── 11. IME COMPOSITION OWNS ITS OWN ENTER ────────────────────────────────────
  {
    const g = makeGrid({ suppressKeyboardEvent: mod.hook, EditorCtor: mod.SuggestCellEditor, cellValue: '' });
    await typeInto(g, 'TFBGA');
    g.key('Enter', { isComposing: true });
    results.imeStillEditing = g.editing;
    results.imeCommitted = g.committed.length;
    g.key('Enter'); await flush();
    results.imeAfterCommit = g.committed[0];
    if (strict) {
      check('Enter mid-composition neither accepts nor commits',
        { editing: results.imeStillEditing, commits: results.imeCommitted }, { editing: true, commits: 0 });
      check('the following real Enter accepts and commits', results.imeAfterCommit, 'TFBGA-296-A1');
    }
  }

  // ── 12. LOCAL NARROWING IS ASCII-ONLY (db_fold disagreement) ──────────────────
  {
    const fresh = load({
      suggestSrc: mod.suggestSrc, gridSrc: mod.gridSrc,
      dataset: { pkg_id: ['ÄBC-1', 'äBC-2'] }
    });
    fresh.suggestSrc = mod.suggestSrc; fresh.gridSrc = mod.gridSrc;
    const g = makeGrid({ suppressKeyboardEvent: fresh.hook, EditorCtor: fresh.SuggestCellEditor, cellValue: '' });
    await typeInto(g, 'ÄB'); // U+00C4: PG lower() and JS toLowerCase() disagree
    results.nonAsciiRequests = fresh.stats().requests;
    results.nonAsciiNarrows = fresh.stats().localNarrows;
    if (strict) {
      check('a non-ASCII prefix is re-asked of the server, never narrowed locally',
        { requests: results.nonAsciiRequests, narrows: results.nonAsciiNarrows }, { requests: 2, narrows: 0 });
    }
  }

  // ── 13. destroy() MUST NOT UNREGISTER A LIVE SUCCESSOR ────────────────────────
  {
    const g = makeGrid({ suppressKeyboardEvent: mod.hook, EditorCtor: mod.SuggestCellEditor, cellValue: '' });
    const first = new mod.SuggestCellEditor();
    first.init({ value: '', eventKey: 'F2', cellStartedEdit: true,
      column: { getColId: () => 'pkg_id' }, colDef: {}, node: {}, data: {}, rowIndex: 0,
      eGridCell: new El('div'), stopEditing() {}, onKeyDown() {}, api: {} });
    const second = new mod.SuggestCellEditor();
    second.init({ value: '', eventKey: 'F2', cellStartedEdit: true,
      column: { getColId: () => 'pkg_id' }, colDef: {}, node: {}, data: {}, rowIndex: 0,
      eGridCell: new El('div'), stopEditing() {}, onKeyDown() {}, api: {} });
    // Give the live successor an OPEN list, so the predecessor's teardown has something to
    // destroy. `active` was already guarded; the shared floating list and the shared
    // in-flight request had the same exposure and were not. Driven through `second`'s own
    // input rather than through the grid model, because a grid keypress would construct a
    // THIRD editor and `second` would no longer be the live one.
    second.eInput.value = 'TFBGA';
    second.eInput.fire('input');
    await flush();

    // Read the SHARED list element out of the sandbox's document, not the instance flag:
    // `first.closeList()` blanks the shared DOM while leaving `second.listOpen` true, so an
    // assertion on the flag cannot see the damage. This is the observable the operator sees.
    const sharedList = () => mod.sandbox.document.body.children
      .find(c => String(c.className).includes('value-suggest-list'));
    const listState = () => {
      const el = sharedList();
      return el ? { display: el.style.display, rows: el.children.length } : null;
    };
    results.sharedListBefore = listState();

    first.destroy(); // the previous editor is torn down AFTER the next one registered
    results.stillActive = mod.sandbox.__mod.isSuggestEditorActive();
    results.sharedListAfter = listState();
    if (strict) {
      check('tearing down the previous editor leaves the live one registered',
        results.stillActive, true);
      check('the live successor really had a rendered list', results.sharedListBefore,
        { display: 'block', rows: 3 });
      check('and the predecessor\'s teardown did not blank it', results.sharedListAfter,
        { display: 'block', rows: 3 });
    }
    second.destroy();
  }

  // ── 14. THE TRUNCATED REGIME: A REQUEST IS OUTSTANDING ON MOST KEYSTROKES ──────
  //
  // This is the interlock that turned the Escape defect from rare into common, and it was
  // invisible here for a structural reason: the fetch stub ignored `limit` and hardcoded a
  // 20-value cut, so with a five-value dataset `truncated` was false in every scenario. At
  // `REQUEST_LIMIT = 12` production is the other regime — a truncated answer is never cached,
  // so refinement cannot be served locally and every keystroke issues a request.
  {
    const fresh = load({ suggestSrc: mod.suggestSrc, gridSrc: mod.gridSrc, dataset: DATASET });
    fresh.suggestSrc = mod.suggestSrc; fresh.gridSrc = mod.gridSrc;
    const g = makeGrid({ suppressKeyboardEvent: fresh.hook, EditorCtor: fresh.SuggestCellEditor, cellValue: '' });
    g.colId = 'wafer_id';                 // 40 values, all sharing 'WF0'
    await typeInto(g, 'WF0');
    results.truncRequests = fresh.stats().requests;
    results.truncNarrows = fresh.stats().localNarrows;
    results.truncFlag = g.editor ? g.editor.truncated : null;
    results.truncListLen = g.editor ? g.editor.values.length : 0;

    // And the consequence, measured as the race window itself: with a key pressed and no
    // answer back, a request IS outstanding at the moment the next key arrives.
    const g2 = makeGrid({ suppressKeyboardEvent: fresh.hook, EditorCtor: fresh.SuggestCellEditor, cellValue: '' });
    g2.colId = 'wafer_id';
    await typePending(g2, 'WF0');
    results.truncInFlight = fresh.net.inFlight();
    if (strict) {
      check('a truncated answer is reported as truncated and cut to the wire limit',
        { truncated: results.truncFlag, shown: results.truncListLen }, { truncated: true, shown: 12 });
      check('in the truncated regime every character costs a request (3 chars -> 3, 0 narrowed)',
        { requests: results.truncRequests, narrows: results.truncNarrows }, { requests: 3, narrows: 0 });
      check('so a request is still outstanding when the next key arrives', results.truncInFlight, 1);
    }
    g2.key('Escape'); g2.key('Escape'); await flush();
  }

  // ── 15. [HIGH] ESCAPE MEANS THE SAME THING AT EVERY MOMENT OF TYPING ──────────
  //
  // THE non-negotiable outcome, and it is stated as an EQUALITY BETWEEN TWO TIMINGS rather
  // than as two separate expectations — that is the only shape that can fail when one key has
  // two outcomes. Same operator keystrokes, same column, same everything; the only difference
  // is whether the answer got back before the Escape. Before the fix these two rows read
  // `{committed:['TFBGA-296-A1']}` and `{cancelled:1, committed:[]}`: write a value nobody
  // chose, or lose the typed text.
  {
    const runEscape = async (deliverFirst) => {
      const fresh = load({ suggestSrc: mod.suggestSrc, gridSrc: mod.gridSrc, dataset: DATASET });
      const g = makeGrid({ suppressKeyboardEvent: fresh.hook, EditorCtor: fresh.SuggestCellEditor, cellValue: 'OLD' });
      await typePending(g, 'TFB');
      if (deliverFirst) await deliver();          // SLOW operator / fast server: list is up
      const listWasUp = g.editor ? g.editor.listOpen : null;
      g.key('Escape');
      await flush();                              // whatever was in flight settles now
      const kept = g.editor ? g.editor.eInput.value : null;
      g.key('Enter');
      await flush();
      return { listWasUp, kept, editing: g.editing, cancelled: g.cancelled, committed: g.committed };
    };
    const slow = await runEscape(false);   // the answer is still in flight when Escape lands
    const fast = await runEscape(true);    // the answer arrived first, the list is on screen
    results.escSlow = slow;
    results.escFast = fast;
    if (strict) {
      check('the two timings really are different situations (list up / not up)',
        { slow: slow.listWasUp, fast: fast.listWasUp }, { slow: false, fast: true });
      check('ESCAPE HAS THE SAME OUTCOME IN BOTH',
        { editing: slow.editing, cancelled: slow.cancelled, committed: slow.committed, kept: slow.kept },
        { editing: fast.editing, cancelled: fast.cancelled, committed: fast.committed, kept: fast.kept });
      check('and that outcome is: the typed text survives and commits',
        { cancelled: slow.cancelled, committed: slow.committed }, { cancelled: 0, committed: ['TFB'] });
    }
  }

  // ── 15-bis. [HIGH] AN ANSWER THAT WAS ALREADY IN THE QUEUE CANNOT REOPEN THE LIST ─
  //
  // The abort is not the fix and this scenario is why. `land()` resolves the response WITHOUT
  // spinning microtasks, so when Escape is pressed the answer is already sitting in the
  // microtask queue — exactly where `abort()` cannot reach it, and exactly the reason the
  // sequence guard exists. Escape changes neither the input nor the sequence, so all three of
  // the original guards let this answer through: the list reopened with row 0 highlighted and
  // the NEXT ENTER WROTE A VALUE THE OPERATOR NEVER CHOSE. QA reproduced the full chain with
  // `COMMITTED=["DEVENV_ISO_PROBE_7f3c1a9e"]` against a typed "DEV".
  {
    const fresh = load({ suggestSrc: mod.suggestSrc, gridSrc: mod.gridSrc, dataset: DATASET });
    const g = makeGrid({ suppressKeyboardEvent: fresh.hook, EditorCtor: fresh.SuggestCellEditor, cellValue: 'OLD' });
    await typePending(g, 'TFB');
    results.lateHadInFlight = fresh.net.inFlight();
    land();                       // the answer exists; the module has NOT observed it yet
    g.key('Escape');              // ...so the abort is too late, by construction
    await flush();
    results.lateListOpen = g.editor ? g.editor.listOpen : null;
    results.lateHighlight = g.editor ? g.editor.highlight : null;
    g.key('Enter'); await flush();
    results.lateCommitted = g.committed;
    if (strict) {
      check('the answer really was in flight when Escape was pressed', results.lateHadInFlight, 1);
      check('a late answer does not reopen a dismissed list',
        { open: results.lateListOpen, highlight: results.lateHighlight }, { open: false, highlight: -1 });
      check('and the Enter after it commits the TYPED text, never the suggestion',
        results.lateCommitted, ['TFB']);
    }
  }

  // ── 15-ter. THE SECOND ESCAPE STILL CANCELS, WITH A REQUEST IN FLIGHT TOO ──────
  // The dismissal must be sticky enough to survive the answer landing, and no stickier: the
  // operator's way out of the edit cannot become unreachable.
  {
    const fresh = load({ suggestSrc: mod.suggestSrc, gridSrc: mod.gridSrc, dataset: DATASET });
    const g = makeGrid({ suppressKeyboardEvent: fresh.hook, EditorCtor: fresh.SuggestCellEditor, cellValue: 'OLD' });
    await typePending(g, 'TFB');
    g.key('Escape');
    await deliver();              // the answer lands BETWEEN the two Escapes
    g.key('Escape');
    await flush();
    results.pendingDoubleEsc = { cancelled: g.cancelled, commits: g.committed.length, editing: g.editing };
    if (strict) {
      check('Escape twice cancels the edit even when the answer arrived in between',
        results.pendingDoubleEsc, { cancelled: 1, commits: 0, editing: false });
    }
  }

  // ── 15-quater. THE TWO WAYS BACK TO THE LIST STILL WORK AFTER A DISMISSAL ─────
  // A dismissal that could not be undone would be a mode, and the operator would have to know
  // they were in it. Typing is the implicit way back; ArrowDown is the explicit one that the
  // module header promises and that `scheduleQuery`'s new early return would otherwise kill.
  {
    const fresh = load({ suggestSrc: mod.suggestSrc, gridSrc: mod.gridSrc, dataset: DATASET });
    const g = makeGrid({ suppressKeyboardEvent: fresh.hook, EditorCtor: fresh.SuggestCellEditor, cellValue: '' });
    await typeInto(g, 'TFB');
    g.key('Escape');
    g.key('G'); await flush();                     // typing brings it back
    results.reopenByTyping = g.editor ? { open: g.editor.listOpen, n: g.editor.values.length } : null;
    g.key('Escape');
    g.key('ArrowDown'); await flush();             // and so does the explicit reopen
    results.reopenByArrow = g.editor ? { open: g.editor.listOpen, highlight: g.editor.highlight } : null;
    if (strict) {
      check('typing after a dismissal brings the list back', results.reopenByTyping, { open: true, n: 3 });
      check('ArrowDown after a dismissal brings the list back, highlighted',
        results.reopenByArrow, { open: true, highlight: 0 });
    }
    g.key('Escape'); g.key('Escape'); await flush();
  }

  // ── 15-quinquies. THE THIRD TIMING: ESCAPE BEFORE THE DEBOUNCE EVEN FIRES ─────
  //
  // The earliest moment of typing, and the one the prescribed predicate ("a query is pending
  // or scheduled") would have had to reach through a second term. Here the query is SCHEDULED
  // and has not been issued, so the correct behaviour is that it never is: a dismissal must
  // cancel work that has not started, or the server is asked a question nobody is waiting for.
  {
    const fresh = load({ suggestSrc: mod.suggestSrc, gridSrc: mod.gridSrc, dataset: DATASET });
    const g = makeGrid({ suppressKeyboardEvent: fresh.hook, EditorCtor: fresh.SuggestCellEditor, cellValue: 'OLD' });
    g.key('T');                    // the editor opens and arms its debounce; no timer has fired
    g.key('Escape');
    await flush();
    results.preDebounceIssued = fresh.net.issued;
    results.preDebounceEditing = g.editing;
    results.preDebounceCancelled = g.cancelled;
    g.key('Enter'); await flush();
    results.preDebounceCommitted = g.committed;
    if (strict) {
      check('Escape before the debounce fires does not cancel the edit',
        { editing: results.preDebounceEditing, cancelled: results.preDebounceCancelled },
        { editing: true, cancelled: 0 });
      check('and the scheduled query is never issued at all', results.preDebounceIssued, 0);
      check('the typed character still commits', results.preDebounceCommitted, ['T']);
    }
  }

  // ── 16. [MEDIUM] THE EXPENSIVE REFUSAL PATH IS BOUNDED ────────────────────────
  //
  // Measured before the fix: 17 characters typed -> 17 requests, for the whole session. The
  // endpoint is a sync `def`, so every one of those holds an anyio worker thread AND a pooled
  // connection for its full duration (217 ms - 1.9 s on a column in this state), and aborting
  // the fetch closes the browser socket without cancelling a handler already inside
  // `db.execute`. The victims are UNRELATED requests failing on `pool_timeout`.
  {
    const fresh = load({ suggestSrc: mod.suggestSrc, gridSrc: mod.gridSrc, dataset: DATASET });
    fresh.suggestSrc = mod.suggestSrc; fresh.gridSrc = mod.gridSrc;
    const g = makeGrid({ suppressKeyboardEvent: fresh.hook, EditorCtor: fresh.SuggestCellEditor, cellValue: '' });
    g.colId = 'legacy_note';       // answers `unavailable_reason`
    await typeInto(g, 'ABCDEFGHIJKLMNOPQ');   // the same 17 characters
    results.cooldownRequests17 = fresh.stats().requests;
    g.key('Escape'); g.key('Escape'); await flush();

    // ...and it is a COOLDOWN, not a latch. An index built later must take effect.
    advanceClock(20000);           // > UNAVAILABLE_COOLDOWN_MS
    const g2 = makeGrid({ suppressKeyboardEvent: fresh.hook, EditorCtor: fresh.SuggestCellEditor, cellValue: '' });
    g2.colId = 'legacy_note';
    await typeInto(g2, 'ABC');
    results.cooldownRequestsAfter = fresh.stats().requests;
    if (strict) {
      check('17 characters on an unanswerable column cost ONE request, not 17',
        results.cooldownRequests17, 1);
      check('and after the cooldown expires the column is asked exactly once more',
        results.cooldownRequestsAfter, 2);
    }
    g2.key('Escape'); g2.key('Escape'); await flush();
  }

  // ── 17. [MEDIUM] A TRANSIENT REFUSAL IS RECOVERABLE ───────────────────────────
  //
  // A 404 is ONE OBSERVATION and this client cannot tell the server's from a proxy's. Before
  // the TTL, one transient 404 raised the prefix floor for the session and `suggestible()`
  // then refused to issue the very request that would have disproved it — unrecoverable by
  // construction, and invisible to the `table_config` hot reload this deployment relies on.
  {
    let refusing = true;
    const fresh = load({
      suggestSrc: mod.suggestSrc, gridSrc: mod.gridSrc, dataset: DATASET,
      onFetch: () => (refusing
        ? { status: 404, ok: false, json: async () => ({ detail: 'no such column' }) }
        : null)
    });
    fresh.suggestSrc = mod.suggestSrc; fresh.gridSrc = mod.gridSrc;

    const g = makeGrid({ suppressKeyboardEvent: fresh.hook, EditorCtor: fresh.SuggestCellEditor, cellValue: '' });
    await typeInto(g, 'TFBGA');           // 5 refusals: floor -> 6 AND the column disabled
    results.latchFloor = Object.values(fresh.stats().floors)[0] || 0;
    results.latchDisabled = fresh.stats().disabled.length;
    g.key('Escape'); g.key('Escape'); await flush();

    refusing = false;                     // the proxy is back / the route is mounted again

    const g2 = makeGrid({ suppressKeyboardEvent: fresh.hook, EditorCtor: fresh.SuggestCellEditor, cellValue: '' });
    await typeInto(g2, 'TFBGA');
    results.beforeTtlOpen = g2.editor ? g2.editor.listOpen : null;
    g2.key('Escape'); g2.key('Escape'); await flush();

    advanceClock(70000);                  // > LEARNED_TTL_MS
    const g3 = makeGrid({ suppressKeyboardEvent: fresh.hook, EditorCtor: fresh.SuggestCellEditor, cellValue: '' });
    await typeInto(g3, 'TFBGA');
    results.afterTtlOpen = g3.editor ? g3.editor.listOpen : null;
    results.afterTtlValues = g3.editor ? g3.editor.values.length : 0;
    if (strict) {
      // Floor 5, not 6: the 4th refusal switches the column off, so the 5th character is
      // never asked. The two latches interlock, and that is the intended shape.
      check('a run of 4xx does latch: the floor rose and the column was switched off',
        { floor: results.latchFloor, disabled: results.latchDisabled }, { floor: 5, disabled: 1 });
      check('the latch really holds while it is in force', results.beforeTtlOpen, false);
      check('but it EXPIRES, so the column recovers without a browser reload',
        { open: results.afterTtlOpen, n: results.afterTtlValues }, { open: true, n: 3 });
    }
    g3.key('Escape'); g3.key('Escape'); await flush();
  }

  // ── 17-bis. A SCHEMA READ RELEASES THE LATCHES IMMEDIATELY ────────────────────
  // `table_config` is hot-reloaded and the server honours a change from the next request. The
  // TTL bounds the damage; `resetSuggestLearning` — called from `loadSchema` — is what makes a
  // newly-declared column work at once instead of a minute later.
  {
    let refusing = true;
    const fresh = load({
      suggestSrc: mod.suggestSrc, gridSrc: mod.gridSrc, dataset: DATASET,
      onFetch: () => (refusing
        ? { status: 400, ok: false, json: async () => ({ detail: 'not a suggestion target' }) }
        : null)
    });
    fresh.suggestSrc = mod.suggestSrc; fresh.gridSrc = mod.gridSrc;
    const g = makeGrid({ suppressKeyboardEvent: fresh.hook, EditorCtor: fresh.SuggestCellEditor, cellValue: '' });
    await typeInto(g, 'TFBGA');
    g.key('Escape'); g.key('Escape'); await flush();
    results.beforeReloadDisabled = fresh.stats().disabled.length;

    refusing = false;
    fresh.resetLearning();                // what `loadSchema` now does on every /schema read
    results.afterReloadDisabled = fresh.stats().disabled.length;
    results.afterReloadFloors = Object.keys(fresh.stats().floors).length;

    const g2 = makeGrid({ suppressKeyboardEvent: fresh.hook, EditorCtor: fresh.SuggestCellEditor, cellValue: '' });
    await typeInto(g2, 'TFBGA');
    results.afterReloadOpen = g2.editor ? g2.editor.listOpen : null;
    if (strict) {
      check('the column was latched off before the reload', results.beforeReloadDisabled, 1);
      check('a schema read drops every learned refusal',
        { disabled: results.afterReloadDisabled, floors: results.afterReloadFloors }, { disabled: 0, floors: 0 });
      check('so a hot-reloaded declaration takes effect at once', results.afterReloadOpen, true);
    }
    g2.key('Escape'); g2.key('Escape'); await flush();
  }

  // ── 18. [MEDIUM] THE PENDING HAIRLINE IS WRITTEN ONLY BY THE LIST'S OWNER ─────
  //
  // Same class as M19, one write further on. `eList` is a SHARED singleton: `e14b1d0` guarded
  // `closeList`, the registration and the abort, and left `setPending` — a write to that same
  // element — ahead of the guard. Here a predecessor's debounce timer fires after a successor
  // has become the live editor, and its `setPending(true)` marks the SUCCESSOR's list as
  // refining when nothing is refining it.
  {
    const fresh = load({ suggestSrc: mod.suggestSrc, gridSrc: mod.gridSrc, dataset: DATASET });
    const mk = () => {
      const ed = new fresh.SuggestCellEditor();
      ed.init({ value: '', eventKey: 'F2', cellStartedEdit: true,
        column: { getColId: () => 'pkg_id' }, colDef: {}, node: {}, data: {}, rowIndex: 0,
        eGridCell: new El('div'), stopEditing() {}, onKeyDown() {}, api: {} });
      return ed;
    };
    const first = mk();
    first.eInput.value = 'TFB';
    first.eInput.fire('input');
    await flush();                         // the predecessor opens a list of its own...

    const second = mk();                   // ...and is superseded WITHOUT being destroyed, which
    second.eInput.value = 'TQ';            // is the M19 situation: `first.listOpen` is still true
    second.eInput.fire('input');
    await flush();                         // successor owns a settled, open list — nothing pending
    results.successorListOpen = second.listOpen;
    results.predecessorStillClaimsList = first.listOpen;
    const pendingMark = () => {
      const el = fresh.sharedList();
      return el ? el.hasAttribute('data-pending') : null;
    };
    results.markBeforeTimer = pendingMark();
    first.eInput.value = 'TFBG';           // the dead predecessor issues one more refinement
    first.eInput.fire('input');
    await advance();                       // its `runQuery` reaches `setPending(true)`
    results.markAfterTimer = pendingMark();
    if (strict) {
      check('the successor owns a settled open list', results.successorListOpen, true);
      check('and the predecessor still believes it owns one (the M19 situation)',
        results.predecessorStillClaimsList, true);
      check('nothing was marked as refining before the predecessor\'s query', results.markBeforeTimer, false);
      check('and a dead predecessor\'s query does not mark the successor\'s list either',
        results.markAfterTimer, false);
    }
    first.destroy(); second.destroy();
    await flush();
  }

  // ── 18-bis. A STALE ANSWER DOES NOT UN-MARK A REFINEMENT THAT IS STILL IN FLIGHT ─
  // The same-instance half: `setPending(false)` used to run BEFORE the guards, so the answer
  // to a question already superseded cleared the hairline belonging to the question that had
  // superseded it.
  {
    const fresh = load({ suggestSrc: mod.suggestSrc, gridSrc: mod.gridSrc, dataset: DATASET });
    const g = makeGrid({ suppressKeyboardEvent: fresh.hook, EditorCtor: fresh.SuggestCellEditor, cellValue: '' });
    g.colId = 'wafer_id';                      // truncated regime: nothing is served locally
    await typeInto(g, 'WF0');                  // a settled, open list
    g.editor.eInput.value = 'WF00';
    g.editor.eInput.fire('input');
    await advance();                           // request A in flight, hairline on
    const mark = () => {
      const el = fresh.sharedList();
      return el ? el.hasAttribute('data-pending') : null;
    };
    results.markWhilePending = mark();
    g.editor.eInput.value = 'WF001';
    g.editor.eInput.fire('input');             // request B is SCHEDULED, not yet issued
    // Order matters and this is the whole scenario: A's answer is released BEFORE B goes out,
    // so when `requestValues` aborts A the answer is already in the microtask queue and the
    // abort is a no-op. That is the only way a stale answer can actually reach `runQuery`.
    land();
    await advance();                           // B is issued now; A's answer is queued behind it
    await microtasks(12);                      // A resumes, and is stale
    results.markAfterStale = mark();
    results.staleStillPending = fresh.net.inFlight();
    if (strict) {
      check('a refinement in flight is marked', results.markWhilePending, true);
      check('the successor request really is still outstanding', results.staleStillPending, 1);
      check('and a stale answer landing does not un-mark it', results.markAfterStale, true);
    }
    g.key('Escape'); g.key('Escape'); await flush();
  }

  // ── 18-ter. THE HAIRLINE DOES NOT SURVIVE INTO THE NEXT OPEN ──────────────────
  // The list element is REUSED, so an attribute left set on close reappears as a phantom on
  // the next open — a list claiming a refinement is in flight when none is. `setPending`
  // cannot clear it once `listOpen` is false, so closing is the moment it stops being true.
  {
    const fresh = load({ suggestSrc: mod.suggestSrc, gridSrc: mod.gridSrc, dataset: DATASET });
    const g = makeGrid({ suppressKeyboardEvent: fresh.hook, EditorCtor: fresh.SuggestCellEditor, cellValue: '' });
    await typeInto(g, 'T');                    // one request; its COMPLETE answer is cached
    g.editor.eInput.value = 'X';               // not a refinement of 'T' — must go to the server
    g.editor.eInput.fire('input');
    await advance();                           // request in flight, list still up, hairline on
    const mark = () => {
      const el = fresh.sharedList();
      return el ? el.hasAttribute('data-pending') : null;
    };
    results.phantomBefore = mark();
    g.key('Escape');                           // closes the list while a request is in flight
    await flush();
    // Guarded rather than dereferenced: under a mutant that lets this Escape cancel the edit
    // the editor is gone, and a harness that THROWS there reports "threw" instead of naming the
    // assertion that failed. A named failure is the whole value of the applied/caught split.
    results.phantomEditorAlive = !!g.editor;
    if (g.editor) {
      g.editor.eInput.value = 'TF';            // a refinement of the cached 'T': served locally
      g.editor.eInput.fire('input');
      await advance();
    }
    results.phantomReopened = g.editor ? g.editor.listOpen : null;
    results.phantomInFlight = fresh.net.inFlight();
    results.phantomAfter = mark();
    if (strict) {
      check('the hairline is shown while the refinement is genuinely in flight', results.phantomBefore, true);
      check('the dismissal did not cancel the edit', results.phantomEditorAlive, true);
      check('the list reopens from the local cache with nothing in flight',
        { open: results.phantomReopened, inFlight: results.phantomInFlight }, { open: true, inFlight: 0 });
      check('and it does NOT claim a refinement is in flight', results.phantomAfter, false);
    }
    g.key('Escape'); g.key('Escape'); await flush();
  }

  // ── 19. [MEDIUM] THE LIST IS CLAMPED HORIZONTALLY, NOT ONLY VERTICALLY ────────
  //
  // The list is `position: fixed`, shrink-wrapped, and its container is `overflow-x: hidden`.
  // Vertical was clamped from the first version and horizontal was not, and on a string column
  // near the right edge the tail of a long value was then unreachable BY ANY MEANS — a page
  // cannot scroll to a fixed element and there was no scrollbar to drag. The operator could not
  // read the value Enter was about to write, which is the one thing the highlight is for.
  {
    const fresh = load({ suggestSrc: mod.suggestSrc, gridSrc: mod.gridSrc, dataset: DATASET });
    const VW = fresh.sandbox.window.innerWidth;          // 1280
    const cell = new El('div');
    cell._rect = { left: 1180, top: 300, right: 1280, bottom: 326, width: 100, height: 26 };
    const ed = new fresh.SuggestCellEditor();
    ed.init({ value: '', eventKey: 'F2', cellStartedEdit: true,
      column: { getColId: () => 'long_note' }, colDef: {}, node: {}, data: {}, rowIndex: 0,
      eGridCell: cell, stopEditing() {}, onKeyDown() {}, api: {} });
    ed.eInput.value = 'NEEDS-R';
    ed.eInput.fire('input');
    await flush();
    const el = fresh.sharedList();
    const px = s => (typeof s === 'string' && s.endsWith('px') ? parseFloat(s) : NaN);
    results.clampLeft = px(el && el.style.left);
    results.clampWidth = el ? el.offsetWidth : null;
    results.clampRight = results.clampLeft + results.clampWidth;
    results.clampRowText = el && el.children[0] ? el.children[0].renderedText : null;
    // ...and again in a viewport NARROWER than the value needs. A shrink-wrapped list with no
    // `max-width` simply grows past the edge, and `overflow-x: hidden` then makes the tail
    // unreadable by any means. A resize is not a contrived trigger: `onViewportScroll` is bound
    // to `resize` precisely so the list follows its cell.
    const NARROW = 420;
    fresh.sandbox.window.innerWidth = NARROW;
    cell._rect = { left: 320, top: 300, right: 420, bottom: 326, width: 100, height: 26 };
    ed.positionList();
    results.narrowLeft = px(el && el.style.left);
    results.narrowWidth = el ? el.offsetWidth : null;
    if (strict) {
      check('the list opened on the long value', results.clampRowText,
        'NEEDS-REWORK-AFTER-PROBE-2ND-PASS-CONFIRMED-BY-QA-2026');
      check('its right edge is inside the viewport', results.clampRight <= VW, true);
      check('its left edge is too', results.clampLeft >= 0, true);
      check('in a viewport narrower than the value, the list is capped to the viewport',
        results.narrowWidth <= NARROW, true);
      check('and it still starts on screen', results.narrowLeft >= 0, true);
    }
    ed.destroy();
    await flush();
  }

  return results;
}

// ── Baseline ────────────────────────────────────────────────────────────────────
const suggestSrc = read(SUGGEST_PATH);
const gridSrc = read(GRID_PATH);

console.log('\n=== BASELINE: real source ===');
const base = load({ suggestSrc, gridSrc, dataset: DATASET });
base.suggestSrc = suggestSrc;
base.gridSrc = gridSrc;
const baseResults = await runChecks(base, { strict: true });

console.log('\n--- the two instrument scores, from the same edit ---');
console.log(`  typed in full : ${baseResults.fullKeys} keystrokes -> ${JSON.stringify(baseResults.fullCommitted)}`);
console.log(`  prefix + Enter: ${baseResults.prefixKeys} keystrokes -> ${JSON.stringify(baseResults.prefixCommitted)}`);
console.log(`  saving        : ${baseResults.fullKeys - baseResults.prefixKeys} keystrokes`
  + ` (${(100 * (baseResults.fullKeys - baseResults.prefixKeys) / baseResults.fullKeys).toFixed(0)}%)`);

// ── Mutations ───────────────────────────────────────────────────────────────────
// Each entry names the file, the exact search string, the replacement, and the assertion
// it MUST break. `applied` is reported separately from `caught`: a mutation whose search
// string no longer matches proves nothing and must be visible as a failure.
const MUTATIONS = [
  {
    name: 'M1 two-Enter: the hook refuses to let the accepting Enter commit',
    file: 'grid',
    find: `if (verdict === 'accepted') return false;  // let THIS event commit the candidate`,
    repl: `if (verdict === 'accepted') return true;   // MUTANT: accept now, commit on a SECOND Enter`,
    breaks: 'prefix+Enter keystroke count and/or the single commit'
  },
  {
    name: 'M2 two-Enter, the other way: the editor consumes the Enter itself',
    file: 'suggest',
    find: `      if (this.listOpen && this.acceptHighlight()) return 'accepted';`,
    repl: `      if (this.listOpen && this.acceptHighlight()) return 'suppress';`,
    breaks: 'prefix+Enter commits nothing on the first press'
  },
  {
    name: 'M3 no first-match highlight on open',
    file: 'suggest',
    find: `    this.highlight = exact >= 0 ? exact : 0;`,
    repl: `    this.highlight = exact >= 0 ? exact : -1;`,
    breaks: 'Enter with no arrow key commits the prefix instead of the candidate'
  },
  {
    name: 'M4 Escape cancels the edit instead of dismissing the list',
    file: 'suggest',
    find: `      if (mine) {
        this.dismissSuggestions();
        return 'suppress';
      }`,
    repl: `      if (mine) {
        this.dismissSuggestions();
        return 'pass'; /* MUTANT: no dismiss-only step */
      }`,
    breaks: 'Escape-preserves-text'
  },
  {
    name: 'M5 Tab no longer leaves the field',
    file: 'suggest',
    find: `    if (key === 'Enter' || key === 'Tab') {`,
    repl: `    if (key === 'Tab' && this.listOpen) { this.acceptHighlight(); return 'suppress'; }
    if (key === 'Enter' || key === 'Tab') {`,
    breaks: 'Tab commits and moves focus'
  },
  {
    name: 'M6 empty prefix opens the list',
    file: 'suggest',
    find: `const MIN_PREFIX_LEN = 1;`,
    repl: `const MIN_PREFIX_LEN = 0;`,
    breaks: 'the empty-prefix refusal'
  },
  {
    name: 'M7 a 4xx no longer silences the column',
    file: 'suggest',
    find: `    if (n >= MAX_REJECTS_BEFORE_DISABLE) learn(disabledColumns, key, true);`,
    repl: `    /* MUTANT: never disable */`,
    breaks: 'refused column: suggestions switched off for the session'
  },
  {
    name: 'M8 `unavailable_reason` is treated as an empty-but-valid list',
    file: 'suggest',
    find: `  if (body && body.unavailable_reason) {`,
    repl: `  if (false && body && body.unavailable_reason) {`,
    breaks: 'unavailable column falls back silently'
  },
  {
    name: 'M9 no local narrowing — one request per character',
    file: 'suggest',
    find: `    if (canNarrowLocally(cached, prefix)) {`,
    repl: `    if (false && canNarrowLocally(cached, prefix)) {`,
    breaks: 'requests per typed prefix'
  },
  {
    name: 'M10 local narrowing ignores the ASCII fold restriction',
    file: 'suggest',
    find: `  if (!cached || !ASCII_ONLY.test(prefix) || !ASCII_ONLY.test(cached.prefix)) return false;`,
    repl: `  if (!cached) return false;`,
    breaks: 'non-ASCII prefixes are re-asked of the server'
  },
  {
    name: 'M11 the stale-response sequence guard is removed',
    file: 'suggest',
    find: `    if (result.seq !== requestSeq) return;`,
    repl: `    /* MUTANT: no sequence guard */`,
    breaks: 'a late answer for an older prefix must not replace the newer list'
  },
  {
    name: 'M12 the IME composition guard is removed',
    file: 'suggest',
    find: `    const composing = event.isComposing === true || event.keyCode === 229;`,
    repl: `    const composing = false;`,
    breaks: 'Enter mid-composition neither accepts nor commits'
  },
  {
    name: 'M13 destroy() unregisters unconditionally',
    file: 'suggest',
    find: `    if (wasActive) active = null;`,
    repl: `    active = null;`,
    breaks: 'the live successor editor stays registered'
  },
  {
    name: 'M14 Ctrl+Enter is swallowed instead of reaching bulk fill',
    file: 'suggest',
    find: `        this.acceptHighlight();
        return 'pass';`,
    repl: `        this.acceptHighlight();
        return 'suppress';`,
    breaks: 'Ctrl+Enter bulk fill'
  },
  {
    name: 'M15 arrows are not consumed, so the caret moves instead of the highlight',
    file: 'suggest',
    find: `        event.preventDefault(); // or the caret jumps to the start/end of the input
        this.moveHighlight(ARROW_STEP[key]);
        return 'suppress';`,
    repl: `        this.moveHighlight(ARROW_STEP[key]);
        return 'pass';`,
    breaks: 'arrows never move cell focus while editing'
  },
  {
    name: 'M16 the editor ignores the character that started the edit',
    file: 'suggest',
    find: `      startValue = eventKey;`,
    repl: `      startValue = '';`,
    breaks: 'every keystroke count (the first character would be lost)'
  },
  {
    name: 'M19 teardown blanks the shared list even when a live successor owns it',
    file: 'suggest',
    find: `    if (wasActive) this.closeList();`,
    repl: `    this.closeList();`,
    breaks: 'the live successor keeps its open list'
  },
  {
    name: 'M18 the narrowing snapshot outlives the cell edit (the defect E2E found)',
    file: 'suggest',
    find: `    completeResults.delete(colKey(this.table, this.column));`,
    repl: `    /* MUTANT: keep the snapshot across cells */`,
    breaks: 'a value committed in the previous edit is offered in the next one'
  },
  {
    name: 'M17 the wire limit goes back to 20, putting the endpoint over its 10 ms budget',
    file: 'suggest',
    find: `const REQUEST_LIMIT = 12;`,
    repl: `const REQUEST_LIMIT = 20;`,
    breaks: 'the requested limit and the modelled endpoint cost'
  },
  // ── The F3-fix round. One mutation per defect; a defect with none is unguarded. ──
  {
    name: 'M20 [HIGH] a dismissal is not a reason to drop a late answer (the list reopens)',
    file: 'suggest',
    find: `    if (this.eInput.value !== prefix) return;
    if (this.suppressUntilInput) return;`,
    repl: `    if (this.eInput.value !== prefix) return;
    /* MUTANT: no dismissal guard — a late answer reopens the list at highlight 0 */`,
    breaks: 'a late answer does not reopen a dismissed list, and the Enter after it'
  },
  {
    name: 'M21 [HIGH] Escape asks `listOpen` again, so RTT decides which of two outcomes',
    file: 'suggest',
    find: `      const mine = !this.suppressUntilInput
        && (this.suggestionsEngaged || this.listOpen || this.debounceTimer !== null);`,
    repl: `      const mine = this.listOpen; /* MUTANT: the pre-fix predicate */`,
    breaks: 'ESCAPE HAS THE SAME OUTCOME IN BOTH timings'
  },
  {
    name: 'M22 the dismissal is not cleared by typing, so the list never comes back',
    file: 'suggest',
    find: `      this.suppressUntilInput = false;
      this.scheduleQuery();`,
    repl: `      this.scheduleQuery(); /* MUTANT: the dismissal becomes a mode */`,
    breaks: 'typing after a dismissal brings the list back'
  },
  {
    name: 'M23 ArrowDown no longer clears the dismissal, killing the documented reopen',
    file: 'suggest',
    find: `        this.suppressUntilInput = false;
        this.scheduleQuery();
        return 'suppress';`,
    repl: `        this.scheduleQuery(); /* MUTANT: reopen silently does nothing */
        return 'suppress';`,
    breaks: 'ArrowDown after a dismissal brings the list back, highlighted'
  },
  {
    name: 'M24 Escape stops cancelling the pending query, so the answer still arrives',
    file: 'suggest',
    find: `    if (this.debounceTimer) { clearTimeout(this.debounceTimer); this.debounceTimer = null; }
    this.closeList();`,
    repl: `    this.closeList(); /* MUTANT: a scheduled query survives the dismissal */`,
    breaks: 'a dismissed editor issues nothing further (the phantom/in-flight counts)'
  },
  {
    name: 'M25 a truncated answer is cached as if it were the complete set',
    file: 'suggest',
    find: `  if (!truncated) completeResults.set(key, { prefix, values });`,
    repl: `  completeResults.set(key, { prefix, values }); /* MUTANT: narrow from a partial list */`,
    breaks: 'the truncated regime costs one request per character'
  },
  {
    name: 'M26 [MEDIUM] `unavailable_reason` gets no cooldown — one request per keystroke',
    file: 'suggest',
    find: `    learn(columnCooldown, key, body.unavailable_reason);`,
    repl: `    /* MUTANT: no backoff on the one refusal path that costs a pooled connection */`,
    breaks: '17 characters on an unanswerable column cost ONE request'
  },
  {
    name: 'M27 the cooldown is recorded but never consulted',
    file: 'suggest',
    find: `    if (recall(columnCooldown, key, UNAVAILABLE_COOLDOWN_MS)) return false;`,
    repl: `    /* MUTANT: cooldown ignored at the read site */`,
    breaks: '17 characters on an unanswerable column cost ONE request'
  },
  {
    name: 'M28 [MEDIUM] nothing a refusal teaches ever expires (the one-way latch is back)',
    file: 'suggest',
    find: `  if (nowMs() - entry.at >= ttlMs) { map.delete(key); return undefined; }`,
    repl: `  /* MUTANT: a single transient refusal lasts the whole session */`,
    breaks: 'a latched column recovers after the TTL'
  },
  {
    name: 'M29 [MEDIUM] a schema read no longer releases the latches (hot reload broken)',
    file: 'suggest',
    find: `  disabledColumns.clear();
  columnFloor.clear();
  columnRejects.clear();
  columnCooldown.clear();
  completeResults.clear();`,
    repl: `  /* MUTANT: a table_config hot reload cannot reach the client */`,
    breaks: 'a hot-reloaded declaration takes effect at once'
  },
  {
    name: 'M30 [MEDIUM] `setPending` writes to the shared list without owning it',
    file: 'suggest',
    find: `    if (active !== this || !eList || !this.listOpen) return;`,
    repl: `    if (!eList || !this.listOpen) return; /* MUTANT: the M19 class, one write on */`,
    breaks: 'a dead predecessor\'s query does not mark the successor\'s list'
  },
  {
    name: 'M31 [MEDIUM] the shared-DOM write goes back ahead of the guards',
    file: 'suggest',
    find: `    if (result.seq !== requestSeq) return;
    if (this.eInput.value !== prefix) return;`,
    repl: `    this.setPending(false); /* MUTANT: un-mark first, ask whether it is ours after */
    if (result.seq !== requestSeq) return;
    if (this.eInput.value !== prefix) return;`,
    breaks: 'a stale answer landing does not un-mark a refinement still in flight'
  },
  {
    name: 'M32 the pending hairline survives a close and reappears on the next open',
    file: 'suggest',
    find: `      eList.removeAttribute('data-pending');`,
    repl: `      /* MUTANT: a phantom hairline on a list with nothing in flight */`,
    breaks: 'the reopened list does not claim a refinement is in flight'
  },
  {
    name: 'M33 [MEDIUM] no horizontal clamp, so the list runs off the right edge',
    file: 'suggest',
    find: `    if (vw > 0 && left + w > vw - EDGE) left = vw - EDGE - w;
    if (left < EDGE) left = EDGE;`,
    repl: `    /* MUTANT: left is whatever the cell rect says */`,
    breaks: 'the list\'s right edge is inside the viewport'
  },
  {
    name: 'M34 [MEDIUM] the list may be wider than the viewport it has to fit in',
    file: 'suggest',
    find: `    const maxW = Math.max(160, vw - 2 * EDGE);`,
    repl: `    const maxW = 1e6; /* MUTANT: no width cap */`,
    breaks: 'the list is never wider than the viewport'
  }
];

console.log('\n=== MUTATION SWEEP ===');
let applied = 0, caught = 0, notApplied = [], escaped = [];
for (const m of MUTATIONS) {
  const target = m.file === 'grid' ? gridSrc : suggestSrc;
  if (!target.includes(m.find)) {
    notApplied.push(m.name);
    console.error(`  NOT APPLIED  ${m.name}\n    search string not found in ${m.file}`);
    continue;
  }
  applied++;
  const mutated = target.replace(m.find, m.repl);
  const mod = load({
    suggestSrc: m.file === 'suggest' ? mutated : suggestSrc,
    gridSrc: m.file === 'grid' ? mutated : gridSrc,
    dataset: DATASET
  });
  mod.suggestSrc = m.file === 'suggest' ? mutated : suggestSrc;
  mod.gridSrc = m.file === 'grid' ? mutated : gridSrc;

  const before = { pass, fail, failures: failures.length };
  let threw = null;
  quiet = true;
  try {
    await runChecks(mod, { strict: true });
  } catch (err) {
    threw = err;
  }
  quiet = false;
  const brokeSomething = fail > before.fail || threw !== null;
  const detectedBy = failures.slice(before.failures);
  // The mutant's own failures are EXPECTED — roll the score AND the failure list back so
  // they do not pollute the verdict. Only "was the defect detected" survives.
  pass = before.pass;
  fail = before.fail;
  failures.length = before.failures;

  if (brokeSomething) {
    caught++;
    const why = threw ? `threw: ${String(threw.message).slice(0, 70)}`
                      : `${detectedBy.length} assertion(s), first: ${detectedBy[0]}`;
    console.log(`  caught  ${m.name}
            by ${why}`);
  } else {
    escaped.push(m.name);
    console.error(`  ESCAPED ${m.name}\n    expected to break: ${m.breaks}`);
  }
}

// ── Verdict ─────────────────────────────────────────────────────────────────────
console.log('\n=== SUMMARY ===');
console.log(`  baseline assertions : ${pass} passed, ${fail} failed`);
// H1 protocol: the runner reads this line to tell "red with N assertions" from a crash.
console.log(`ASSERTIONS ${pass + fail} ${fail}`);
console.log(`  mutations declared  : ${MUTATIONS.length}`);
console.log(`  mutations APPLIED   : ${applied}`);
console.log(`  mutations CAUGHT    : ${caught}`);
if (notApplied.length) console.error(`  NOT APPLIED: ${notApplied.join(' | ')}`);
if (escaped.length) console.error(`  ESCAPED: ${escaped.join(' | ')}`);
if (failures.length) console.error(`  baseline failures: ${failures.join(' | ')}`);

const ok = fail === 0 && notApplied.length === 0 && escaped.length === 0 && applied === MUTATIONS.length;
console.log(ok ? '\nOK — one-Enter holds, and every declared defect is detected.\n'
              : '\nFAILED\n');
process.exit(ok ? 0 : 1);
