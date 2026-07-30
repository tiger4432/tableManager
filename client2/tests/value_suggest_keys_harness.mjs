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

class El {
  constructor(tag) {
    this.tagName = tag;
    this.className = '';
    this.style = {};
    this.attrs = {};
    this._children = [];
    this.listeners = {};
    this.value = '';
    this.textContent = '';
    this.isConnected = false;
    this.offsetHeight = 100;
    this.selected = false;
    this.focused = false;
    this.classList = {
      add: c => { if (!this.className.includes(c)) this.className += ` ${c}`; },
      remove: c => { this.className = this.className.replace(c, '').trim(); },
      contains: c => this.className.includes(c)
    };
  }
  get children() { return this._children; }
  get innerHTML() { return ''; }
  set innerHTML(v) { if (v === '') this._children = []; }
  setAttribute(k, v) { this.attrs[k] = v; }
  getAttribute(k) { return this.attrs[k]; }
  removeAttribute(k) { delete this.attrs[k]; }
  hasAttribute(k) { return k in this.attrs; }
  appendChild(c) { this._children.push(c); c.isConnected = this.isConnected; return c; }
  addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); }
  removeEventListener(t, fn) {
    if (this.listeners[t]) this.listeners[t] = this.listeners[t].filter(f => f !== fn);
  }
  fire(t, ev) { for (const fn of this.listeners[t] || []) fn(ev || {}); }
  getBoundingClientRect() { return { left: 10, top: 100, right: 160, bottom: 126, width: 150, height: 26 }; }
  scrollIntoView() {}
  focus() { this.focused = true; }
  select() { this.selected = true; }
  // The rendered row text as the operator sees it: <b>head</b> + tail.
  get renderedText() {
    if (this._children.length === 0) return this.textContent;
    return this._children.map(c => c.textContent).join('') + (this.textContent || '');
  }
}

// Deterministic timer queue — no wall clock anywhere in this harness.
let timerId = 0;
let timers = [];

function makeSandbox({ dataset, tableName = 'bonding_map', onFetch }) {
  const body = new El('body');
  body.isConnected = true;
  const doc = {
    body,
    createElement: tag => new El(tag),
    createTextNode: t => { const n = new El('#text'); n.textContent = t; return n; },
    querySelector: () => null
  };
  const win = { innerHeight: 800, addEventListener() {}, removeEventListener() {} };

  const fetchStub = async (url) => {
    if (onFetch) {
      const r = onFetch(url);
      if (r) return r;
    }
    const u = new URL(url, 'http://x');
    const prefix = u.searchParams.get('prefix') || '';
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
      json: async () => ({ values: hits.slice(0, 20), truncated: hits.length > 20 })
    };
  };

  const sandbox = {
    API_BASE: 'http://api',
    state: { currentTable: tableName, selectedCellsMap: {}, dragStartCell: null, dragEndCell: null,
             visibleColIndexMap: {}, txModeActive: false, pendingTxEdits: {} },
    document: doc,
    window: win,
    console: { debug() {}, warn() {}, error() {}, log() {} },
    fetch: fetchStub,
    AbortController: class { constructor() { this.signal = {}; } abort() { this.aborted = true; } },
    URL,
    setTimeout: (fn) => { const id = ++timerId; timers.push({ id, fn }); return id; },
    clearTimeout: (id) => { timers = timers.filter(t => t.id !== id); },
    Math, JSON, String, Number, Array, Object, Set, Map, RegExp, Promise, Error, isNaN
  };
  sandbox.globalThis = sandbox;
  return sandbox;
}

async function flush() {
  for (let round = 0; round < 6; round++) {
    const q = timers;
    timers = [];
    for (const t of q) t.fn();
    for (let i = 0; i < 12; i++) await new Promise(r => setImmediate(r));
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
    + ' getSuggestStats, resetSuggestStats };',
    ctx, { filename: 'value_suggest.js' });
  const hookSrc = extractArrowProp(gridSrc, 'suppressKeyboardEvent');
  vm.runInContext(
    `${extractConst(gridSrc, 'RANGE_ARROW_DELTA')}\nvar __hook = ${hookSrc};`,
    ctx, { filename: 'grid.js#suppressKeyboardEvent' });
  return {
    ctx,
    sandbox,
    calls,
    SuggestCellEditor: sandbox.__mod.SuggestCellEditor,
    hook: sandbox.__hook,
    stats: () => sandbox.__mod.getSuggestStats()
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
  // A column the endpoint refuses (undeclared) — the silent-fallback path.
  scratch: undefined,
  // A column the endpoint cannot answer for (index missing/invalid, timeout).
  legacy_note: null
};

/** Type a string one character at a time, exactly as a human would. */
async function typeInto(g, text) {
  for (const ch of text) { g.key(ch); await flush(); }
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
    if (strict) {
      check('unavailable column: no list', results.unavailListOpen, false);
      check('unavailable column: the typed text commits unchanged', results.unavailCommitted, 'ABC');
      check('unavailable column is NOT permanently disabled (an index can be built later)',
        results.unavailDisabled, false);
      check('the named reason was recognised, not read as an empty result',
        results.unavailCount, 3);
      check('an unavailable answer is never cached, so every keystroke re-asks',
        { requests: results.unavailRequests, narrows: results.unavailNarrows }, { requests: 3, narrows: 0 });
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
    find: `        this.closeList();
        return 'suppress';
      }
      return 'pass'; // second Escape = AG-Grid's normal cancel-edit`,
    repl: `        this.closeList();
        return 'pass';
      }
      return 'pass'; // MUTANT: no dismiss-only step`,
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
    find: `    if (n >= MAX_REJECTS_BEFORE_DISABLE) disabledColumns.add(key);`,
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
