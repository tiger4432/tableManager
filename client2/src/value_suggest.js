/**
 * value_suggest.js — the CLIENT half of F3 value suggestion.
 *
 * Deliberately named after `server/value_suggest.py`: same feature, same name, so the
 * two halves of the seam are findable from each other. The server owns the lookup
 * (prefix predicate, `db_fold` collation, loose index scan, truncation reporting); this
 * file owns only the input surface and never re-derives any of that.
 *
 * ── WHY THIS EXISTS, IN ONE INEQUALITY ──────────────────────────────────────────
 * On the V1 effort instrument a keystroke costs 1. Typing a value in full costs N keys.
 * Typing a P-character prefix and pressing Enter costs P + 1. So the suggestion wins
 * whenever P <= N - 2, ties at P = N - 1, and never loses.
 *
 * That inequality holds ONLY IF THE ENTER THAT ACCEPTS THE CANDIDATE IS THE ENTER THAT
 * COMMITS THE CELL. If accepting and committing take two presses the cost becomes P + 2,
 * every use pays +1, short values genuinely regress, and the feature inverts. One Enter
 * is therefore the ACCEPTANCE CRITERION of this module, not a nicety.
 *
 * How the one-Enter property is actually obtained (and why it is not a race):
 * AG-Grid's `processCellKeyboardEvent` consults `colDef.suppressKeyboardEvent` BEFORE it
 * runs `cellCtrl.onKeyDown` — verified in `ag-grid-community@35` at
 * `processCellKeyboardEvent` -> `_isUserSuppressingKeyboardEvent(..., editing)`. So the
 * hook in `grid.js` calls `handleEditorKey()` here, this file writes the highlighted
 * candidate straight into the input, and then returns "let the grid proceed". AG-Grid's
 * own Enter handling (`onEnterKeyDown` -> `editSvc.stopEditing`) then reads the value via
 * `cellEditor.getValue()` (`_valueFromEditor`), which is `input.value` — already the
 * candidate. Accept and commit are literally the same event dispatch. There is no
 * "accept then commit" sequencing to get wrong, and nothing is deferred to a later tick.
 *
 * ── THE EMPTY PREFIX IS REFUSED HERE, ON PURPOSE ────────────────────────────────
 * The server's `min_prefix_length` defaults to 0, so an empty prefix is PERMITTED
 * server-side (and it is cheap — the loose scan makes it O(limit) seeks, not O(rows)).
 * This client still refuses it, and the reason is the acceptance criterion above: with no
 * prefix the list is an arbitrary `limit`-sized window over the column's whole value set,
 * so THE FIRST MATCH IS ARBITRARY. "Enter is right" would degrade to "Enter is a coin
 * flip", and an Enter that writes an arbitrary existing value is worse than no feature at
 * all. Two lesser reasons, both real: an empty prefix answers `truncated: true` on any
 * column with more than `limit` values, so the list would be a sample presented as a pick
 * list; and it would fire one request per cell the operator merely arrowed into.
 * Note the direction — we are STRICTER than the server, never looser, so raising
 * `min_prefix_length` operationally still works and is still obeyed (see `columnFloor`).
 *
 * ── NON-SUGGESTIBLE COLUMNS FALL BACK SILENTLY ──────────────────────────────────
 * The endpoint can legitimately answer "not a suggestion target" (undeclared column,
 * datetime, physically absent) as a 4xx, or "I cannot answer" as `unavailable_reason`
 * (index missing/invalid, statement timeout). In every one of those cases this editor
 * behaves EXACTLY like a plain text editor: no list, no toast, no error. A broken
 * dropdown on a column that cannot be suggested is worse than no dropdown.
 */

import { API_BASE } from './config.js';
import { state } from './state.js';

// ── Knobs ───────────────────────────────────────────────────────────────────────
/**
 * Client floor for opening the list. 1, not 0 — see the empty-prefix decision above.
 * The server's own `min_prefix_length` may be HIGHER; that is discovered at runtime and
 * respected (`columnFloor`), because there is no endpoint that publishes it.
 */
const MIN_PREFIX_LEN = 1;
/**
 * Trailing-edge debounce. Trailing, not leading: a leading edge fires on the first
 * character and then discards the refinements, which is the exact defect the config
 * watcher had to be repaired for (`CONFIG_GUIDE` §4.4). The window is short enough to
 * feel instant at typing speed and long enough that a fast typist's whole prefix is one
 * request.
 */
const DEBOUNCE_MS = 90;
/**
 * Values per response. 12, and the number is load-bearing in two independent ways.
 *
 * (1) THE ARITHMETIC BOUNDS THE USEFUL LIST LENGTH BY ITSELF. A candidate at position k
 *     costs k keys to reach (k-1 arrows + Enter). Full typing costs N. So a candidate past
 *     position N-1 is never worth arrowing to — typing another character of prefix is
 *     strictly cheaper. For the 12-character part numbers this grid actually holds, nothing
 *     beyond position ~11 can ever pay for itself, so asking for 20 was asking for values
 *     no operator could rationally select.
 *
 * (2) IT IS WHAT PUTS THE ENDPOINT UNDER THE 10 ms BUDGET. Measured on this database
 *     (2026-07-30, warm, PostgreSQL 18.3): the lookup costs
 *         t = 0.84 ms + 0.61 ms x (limit + 1)
 *     and the 0.61 ms per probe is 97% Python/SQLAlchemy/protocol and 3% database — so it
 *     is a function of the LIMIT WE ASK FOR and essentially independent of table size
 *     (12.4% spread across a 136x range in n, exponent -0.02). At limit 20 that is 15.3 ms
 *     median, over budget at every size; at 12 it is ~8.7 ms. The break-even is 14 probes.
 *     Consequence worth stating: this budget is ours to spend, not the database's to earn.
 *     Growing the table to 10^7 adds about 0.08 ms; asking for 50 values adds 23 ms.
 *
 * Cost of the change, stated: a shorter list is `truncated` more often, and a truncated
 * answer cannot be narrowed locally, so medium-selectivity prefixes issue one or two more
 * requests than they would have. Each is under budget, which is what the gate asks about.
 */
const REQUEST_LIMIT = 12;
/**
 * Rows visible before the list scrolls. Below `REQUEST_LIMIT` on purpose: scrolling by
 * arrow costs one key per row, so the rows past this point are already in the region where
 * typing more prefix wins. They stay reachable, just not free.
 * The pixel height is derived here rather than duplicated in CSS, so the row count and the
 * box that shows it cannot drift apart.
 */
const MAX_VISIBLE_ROWS = 8;
const ROW_HEIGHT_PX = 26;
/**
 * Consecutive 4xx answers for one column before suggestions are switched off for the
 * session. Bounded so an undeclared column costs a handful of tiny 400s (they raise in
 * `_resolve_target` before any SQL) rather than one per keystroke forever, while still
 * leaving room for a server `min_prefix_length` of up to this many characters.
 */
const MAX_REJECTS_BEFORE_DISABLE = 4;

// ── Session-scoped memory, keyed on (table, column) ─────────────────────────────
const colKey = (table, column) => `${table}\u0000${column}`;

/** Columns proven not to be suggestion targets. Never queried again this session. */
const disabledColumns = new Set();
/**
 * Minimum prefix length this column is believed to need. Learned from 400s: a rejection
 * at length L teaches "L is not enough", so the floor becomes L + 1 and a longer prefix
 * is allowed to retry. That distinguishes the two shapes of 400 without parsing prose:
 * a server `min_prefix_length` failure is a function of LENGTH and stops once the floor
 * is high enough, while an undeclared column keeps failing and trips the reject counter.
 */
const columnFloor = new Map();
const columnRejects = new Map();

/**
 * Last COMPLETE (`truncated: false`) result per column, used to narrow locally instead of
 * re-querying. Sound because the server's answer for a longer prefix is a subset of its
 * answer for a shorter one — but only when the fold agrees, so see `canNarrowLocally`.
 *
 * SCOPE: one cell edit. Dropped in `destroy()`, and that boundary was not an early choice
 * — it is a defect the browser found. The subset property holds against a SNAPSHOT of the
 * column's value set, and the set changes: the operator commits a new value, or another
 * operator's commit arrives as a `batch_row_*` delta. Measured live on the isolated stack:
 * "DEV" was committed to `inventory_master.category`, the next cell typed "DEV", and the
 * list did NOT offer it back — narrowing had served a set cached before that commit. The
 * operator enters a new value and the feature immediately stops knowing about it, which is
 * the one moment they would most expect it to.
 *
 * Invalidating unconditionally on teardown was chosen over the cleverer "invalidate only
 * when the committed value was absent from the cache": it costs one request per cell
 * (~9 ms) and needs no reasoning about what changed, while the clever version has to be
 * right about cancels, bulk fills and concurrent deltas to be safe. The entire measured
 * benefit is intra-edit anyway — six characters in one cell is where 6 requests become 1.
 *
 * What survives, stated plainly: within a single cell edit the set can still go stale if
 * another operator commits mid-typing. The consequence is a MISSING candidate, never a
 * wrong one, and the operator can always type the value out.
 */
const completeResults = new Map(); // colKey -> { prefix, values }

/** Diagnostics counter: how many network requests one typed prefix actually generated. */
const stats = { requests: 0, localNarrows: 0, aborted: 0, rejected: 0, unavailable: 0 };

export function getSuggestStats() {
  return { ...stats, disabled: Array.from(disabledColumns), floors: Object.fromEntries(columnFloor) };
}

export function resetSuggestStats() {
  stats.requests = 0;
  stats.localNarrows = 0;
  stats.aborted = 0;
  stats.rejected = 0;
  stats.unavailable = 0;
}

/**
 * Publish the diagnostics on `window` so they SURVIVE THE PRODUCTION BUILD — the same trap,
 * and the same fix, as `effort_meter.publishDiagnostics`. `getSuggestStats` and
 * `resetSuggestStats` have no caller inside `client2/src`, so the bundler tree-shakes them
 * out of the built chunk and the numbers exist only in source. Measured: during this
 * round's browser E2E `window.__assySuggest` was undefined and the request counts had to be
 * obtained by wrapping `fetch` by hand. An assignment to `window` is a real reference and
 * cannot be shaken out.
 *
 * Read-only, guarded, no UI. Nothing in the app reads it back — it exists so that "how many
 * requests did that prefix cost" and "is this column switched off, and at what floor" are
 * answerable in production instead of only in a test.
 */
try {
  if (typeof window !== 'undefined') {
    window.__assySuggest = { getSuggestStats, resetSuggestStats };
  }
} catch (err) { /* diagnostics must never break the page */ }

/**
 * ASCII-only guard on local narrowing. `db_fold` exists because this database's `lower()`
 * and JavaScript's `toLowerCase()` are DIFFERENT FUNCTIONS outside ASCII — the server
 * module records that `lower()` leaves U+00C4 alone where the host language does not. A-Z
 * -> a-z is the one mapping every implementation shares, so narrowing is exact for ASCII
 * prefixes and only for those. Anything else goes back to the server, which is the only
 * place that knows what "the same value" means here.
 */
const ASCII_ONLY = /^[\x20-\x7E]*$/;

function canNarrowLocally(cached, prefix) {
  if (!cached || !ASCII_ONLY.test(prefix) || !ASCII_ONLY.test(cached.prefix)) return false;
  return prefix.length >= cached.prefix.length
    && prefix.toLowerCase().startsWith(cached.prefix.toLowerCase());
}

// ── The one in-flight request ───────────────────────────────────────────────────
/**
 * Monotonic sequence + AbortController. Both, because they answer different questions:
 * the controller stops a request we no longer want from occupying the connection, and the
 * sequence stops a response that survived the abort race from overwriting a newer list.
 * An abort is not synchronous with respect to an already-queued microtask, so without the
 * sequence a slow answer for "AB" could still land after a fast answer for "ABC".
 */
let requestSeq = 0;
let inflight = null;

function abortInflight() {
  if (!inflight) return;
  stats.aborted += 1;
  try { inflight.abort(); } catch (err) { /* already settled */ }
  inflight = null;
}

/**
 * @returns {Promise<{values: string[], truncated: boolean, ok: boolean, permanent: boolean}>}
 *   `ok: false` means "no list" — the caller must fall back to plain typing SILENTLY.
 */
async function requestValues(table, column, prefix, limit) {
  const key = colKey(table, column);
  const url = `${API_BASE}/tables/${encodeURIComponent(table)}`
    + `/columns/${encodeURIComponent(column)}/values`
    + `?prefix=${encodeURIComponent(prefix)}&limit=${limit}`;

  abortInflight();
  const controller = typeof AbortController === 'function' ? new AbortController() : null;
  inflight = controller;
  const seq = ++requestSeq;
  stats.requests += 1;

  let res;
  try {
    res = await fetch(url, controller ? { signal: controller.signal } : undefined);
  } catch (err) {
    // Aborted, offline, or the server went away. Not a user-facing event.
    return { values: [], truncated: false, ok: false, permanent: false, seq };
  } finally {
    if (inflight === controller) inflight = null;
  }

  if (res.status === 400 || res.status === 404) {
    // "Not a suggestion target", or a prefix shorter than the server's own minimum.
    // Both arrive as 4xx and the detail is prose, so learn the boundary instead of
    // parsing it: raise the floor past this length, and count the rejection so an
    // undeclared column stops being asked.
    stats.rejected += 1;
    const floor = Math.max(columnFloor.get(key) || MIN_PREFIX_LEN, prefix.length + 1);
    columnFloor.set(key, floor);
    const n = (columnRejects.get(key) || 0) + 1;
    columnRejects.set(key, n);
    if (n >= MAX_REJECTS_BEFORE_DISABLE) disabledColumns.add(key);
    return { values: [], truncated: false, ok: false, permanent: true, seq };
  }
  if (!res.ok) return { values: [], truncated: false, ok: false, permanent: false, seq };

  let body;
  try {
    body = await res.json();
  } catch (err) {
    return { values: [], truncated: false, ok: false, permanent: false, seq };
  }

  // The endpoint refuses rather than guessing: an index that is absent, or present but
  // not `indisvalid AND indisready`, or a statement timeout, all come back as a NAMED
  // reason with NO values — precisely so a wrong-but-plausible short list is never served
  // as normal. Treat it as "no suggestions here", quietly. Not permanent: an index can be
  // built, and the next cell entry should find out.
  if (body && body.unavailable_reason) {
    stats.unavailable += 1;
    console.debug('[value_suggest] unavailable:', table, column, body.unavailable_reason);
    return { values: [], truncated: false, ok: false, permanent: false, seq };
  }

  columnRejects.delete(key);
  const values = Array.isArray(body && body.values) ? body.values.map(v => String(v)) : [];
  const truncated = !!(body && body.truncated);
  if (!truncated) completeResults.set(key, { prefix, values });
  return { values, truncated, ok: true, permanent: false, seq };
}

// ── The floating list ───────────────────────────────────────────────────────────
// Created lazily and reused. Lives on `document.body` at the established dropdown layer
// (z 1000, the same rung as `#custom-context-menu`) because an AG-Grid cell is
// `overflow: hidden` and the grid root clips: a list rendered inside the cell would be
// invisible past the cell's own 20-odd pixels of height.
let eList = null;

function ensureList() {
  if (eList && eList.isConnected) return eList;
  eList = document.createElement('div');
  eList.className = 'value-suggest-list';
  eList.setAttribute('role', 'listbox');
  eList.style.maxHeight = `${MAX_VISIBLE_ROWS * ROW_HEIGHT_PX + 8}px`;
  eList.style.display = 'none';
  document.body.appendChild(eList);
  return eList;
}

// ── Active editor registry ──────────────────────────────────────────────────────
/**
 * The keyboard hook in `grid.js` reaches the live editor through here rather than through
 * `api.getCellEditorInstances()`. Both work, but this one is an explicit seam with one
 * owner, and it stays correct if the column is later given a different editor: `active`
 * is null and the hook falls straight through to the pre-existing branches.
 */
let active = null;

export function isSuggestEditorActive() {
  return active !== null;
}

/**
 * Verdicts, deliberately three-valued:
 *   'suppress' — AG-Grid must NOT act on this key (the list consumed it)
 *   'accepted' — the candidate is already in the input; AG-Grid MUST act (this is the
 *                one-Enter path: the same event goes on to stop editing and commit)
 *   'pass'     — not ours; fall through to the pre-existing `suppressKeyboardEvent` logic
 */
export function handleEditorKey(event) {
  if (!active) return 'pass';
  return active.onKeyDown(event);
}

const ARROW_STEP = { ArrowDown: 1, ArrowUp: -1 };

export class SuggestCellEditor {
  init(params) {
    this.params = params;
    // The table comes from the state singleton rather than being plumbed through
    // `cellEditorParams`: `state.currentTable` IS the one answer to "which table is on
    // screen", and a second copy captured at column-build time would go stale the moment
    // the operator switches tables (columnDefs are rebuilt, but a captured string is not
    // obviously rebuilt to a reader).
    this.table = state.currentTable || '';
    this.column = params.column.getColId();
    this.values = [];
    this.truncated = false;
    this.highlight = -1;
    this.listOpen = false;
    this.debounceTimer = null;
    this.destroyed = false;

    this.eGui = document.createElement('div');
    this.eGui.className = 'value-suggest-editor';
    this.eInput = document.createElement('input');
    this.eInput.type = 'text';
    this.eInput.className = 'value-suggest-input';
    this.eInput.setAttribute('role', 'combobox');
    this.eInput.setAttribute('aria-autocomplete', 'list');
    this.eInput.setAttribute('aria-expanded', 'false');
    this.eGui.appendChild(this.eInput);

    // Mirror `SimpleCellEditor.initialiseEditor` exactly. This is not cosmetic: the
    // `eventKey.length === 1` branch is what makes the FIRST character of the prefix also
    // the keystroke that opens the editor. Without it the operator pays an extra key to
    // enter edit mode and the P + 1 arithmetic silently becomes P + 2.
    const startedEdit = params.cellStartedEdit;
    const eventKey = params.eventKey;
    let startValue = '';
    let selectAll = false;
    if (startedEdit && (eventKey === 'Backspace' || eventKey === 'Delete')) {
      startValue = '';
    } else if (startedEdit && eventKey && eventKey.length === 1) {
      // AG-Grid `processCharacter` calls preventDefault for custom editors, so the browser
      // will NOT insert this character. Seeding it here is what makes it count once.
      startValue = eventKey;
    } else {
      startValue = params.value === null || params.value === undefined ? '' : String(params.value);
      if (startedEdit && eventKey !== 'F2') selectAll = true;
    }
    this.eInput.value = startValue;
    this.selectAllOnAttach = selectAll;
    this.focusOnAttach = startedEdit;

    this.onInput = () => this.scheduleQuery();
    this.eInput.addEventListener('input', this.onInput);

    // Reposition rather than close: the operator is typing, and a list that vanishes
    // because a row scrolled under it reads as a bug. Passive — a scroll must never be
    // blocked by this.
    this.onViewportScroll = () => { if (this.listOpen) this.positionList(); };
    this.scrollTargets = [];
    const viewport = document.querySelector('.ag-body-viewport');
    if (viewport) this.scrollTargets.push(viewport);
    this.scrollTargets.push(window);
    for (const t of this.scrollTargets) {
      t.addEventListener('scroll', this.onViewportScroll, { passive: true });
    }
    window.addEventListener('resize', this.onViewportScroll, { passive: true });

    active = this;
    // A non-empty start value queries immediately: the operator typed a character to get
    // here, so the list should already be resolving by the time the caret appears.
    if (this.eInput.value.length >= MIN_PREFIX_LEN && !selectAll) this.scheduleQuery();
  }

  getGui() {
    return this.eGui;
  }

  afterGuiAttached() {
    if (!this.focusOnAttach) return;
    this.eInput.focus();
    if (this.selectAllOnAttach) this.eInput.select();
  }

  /** The grid's ONLY read of the edited value — see `_valueFromEditor`. */
  getValue() {
    return this.eInput.value;
  }

  isPopup() {
    return false;
  }

  destroy() {
    this.destroyed = true;
    if (this.debounceTimer) clearTimeout(this.debounceTimer);
    this.closeList();
    this.eInput.removeEventListener('input', this.onInput);
    for (const t of this.scrollTargets || []) {
      t.removeEventListener('scroll', this.onViewportScroll);
    }
    window.removeEventListener('resize', this.onViewportScroll);
    // Identity-checked: a fast Tab through cells constructs the next editor before the
    // previous one is destroyed, and an unconditional `active = null` would then blank a
    // LIVE editor's registration and lose the keyboard hook for that cell.
    if (active === this) active = null;
    // Drop the narrowing snapshot for this column — see `completeResults`. It has to happen
    // here rather than on commit, because a cancelled edit leaves the same doubt: the
    // operator may have typed a value they are about to enter somewhere else.
    completeResults.delete(colKey(this.table, this.column));
    abortInflight();
  }

  // ── Querying ─────────────────────────────────────────────────────────────────
  suggestible() {
    const key = colKey(this.table, this.column);
    if (!this.table || disabledColumns.has(key)) return false;
    return this.eInput.value.length >= Math.max(MIN_PREFIX_LEN, columnFloor.get(key) || 0);
  }

  scheduleQuery() {
    if (this.debounceTimer) clearTimeout(this.debounceTimer);
    const prefix = this.eInput.value;
    if (!this.suggestible()) { this.closeList(); return; }

    // Local narrowing: a COMPLETE result for a shorter prefix already contains every
    // value the server could return for this longer one, so refining costs zero
    // requests. This is what keeps a typed prefix at ~1 request instead of one per
    // character, and it is exact rather than approximate — but only for ASCII, because
    // outside ASCII only the database knows which values fold together.
    const cached = completeResults.get(colKey(this.table, this.column));
    if (canNarrowLocally(cached, prefix)) {
      stats.localNarrows += 1;
      const lower = prefix.toLowerCase();
      this.applyValues(cached.values.filter(v => v.toLowerCase().startsWith(lower)), false);
      return;
    }

    this.debounceTimer = setTimeout(() => {
      this.debounceTimer = null;
      this.runQuery(prefix);
    }, DEBOUNCE_MS);
  }

  /**
   * What the editor does while a request is outstanding, stated deliberately because it is
   * a real design choice and not an omission:
   *
   *  - If NO list is open yet: nothing at all. No spinner, no placeholder row. A
   *    well-indexed column answers in about 9 ms and a spinner for 9 ms is pure flicker.
   *    A column whose index is missing answers in ~200 ms (measured on `wafer_process`,
   *    which has no suggestion index today) and the list simply appears a beat later, which
   *    is how every autocomplete behaves.
   *  - If a list IS open: the PREVIOUS list stays on screen and keeps working — arrows,
   *    Enter and Tab all still act on it — and only a hairline marks that a refinement is
   *    in flight. Blanking the list on every keystroke would take a usable list away from
   *    the operator in exchange for nothing.
   *
   * Neither state can strand the operator, because a request never blocks a key: the input
   * is a plain text field and Enter commits whatever is in it whether an answer arrives or
   * not.
   */
  setPending(on) {
    if (!eList || !this.listOpen) return;
    if (on) eList.setAttribute('data-pending', '1');
    else eList.removeAttribute('data-pending');
  }

  async runQuery(prefix) {
    const table = this.table, column = this.column;
    this.setPending(true);
    const result = await requestValues(table, column, prefix, REQUEST_LIMIT);
    this.setPending(false);
    // Three guards, each closing a different way a stale answer could land: the editor
    // is gone, a newer request has been issued, or the operator has typed on since.
    if (this.destroyed || active !== this) return;
    if (result.seq !== requestSeq) return;
    if (this.eInput.value !== prefix) return;
    if (!result.ok) { this.closeList(); return; }
    this.applyValues(result.values, result.truncated);
  }

  applyValues(values, truncated) {
    this.values = values;
    this.truncated = truncated;
    if (values.length === 0) { this.closeList(); return; }
    // FIRST MATCH HIGHLIGHTED ON OPEN — this is what makes the common case Enter with no
    // arrow key at all, and it is the reason the cost is P + 1 rather than P + 1 + arrows.
    // An exact typed match wins over position, so an operator who typed a value that
    // happens to be a prefix of a longer one still commits their own text with Enter.
    const typed = this.eInput.value.toLowerCase();
    const exact = values.findIndex(v => v.toLowerCase() === typed);
    this.highlight = exact >= 0 ? exact : 0;
    this.openList();
  }

  // ── The list ─────────────────────────────────────────────────────────────────
  openList() {
    const el = ensureList();
    el.innerHTML = '';
    this.values.forEach((v, i) => {
      const row = document.createElement('div');
      row.className = 'value-suggest-row' + (i === this.highlight ? ' is-active' : '');
      row.setAttribute('role', 'option');
      row.setAttribute('aria-selected', i === this.highlight ? 'true' : 'false');
      const pfx = this.eInput.value;
      // Bold the matched head. Sliced by LENGTH off the raw value rather than by
      // re-matching, so a case-insensitive match still shows the STORED casing.
      const head = v.slice(0, pfx.length);
      const tail = v.slice(pfx.length);
      const b = document.createElement('b');
      b.textContent = head;
      row.appendChild(b);
      row.appendChild(document.createTextNode(tail));
      // Mousedown, not click, and preventDefault: a click on a body-level list would blur
      // the input first, AG-Grid would stop editing, and the row we are handling would be
      // gone before the click fired. Mouse selection stays available; it is just never the
      // only way, because a click costs 3 on the instrument against Enter's 1.
      row.addEventListener('mousedown', (e) => {
        e.preventDefault();
        this.highlight = i;
        this.acceptHighlight();
        this.params.stopEditing();
      });
      el.appendChild(row);
    });
    if (this.truncated) {
      // The endpoint reports truncation precisely so the list never claims to be the
      // whole set. Saying so is cheap; implying completeness is a wrong answer.
      const more = document.createElement('div');
      more.className = 'value-suggest-more';
      more.textContent = `상위 ${this.values.length}개만 표시 — 더 입력하면 좁혀집니다`;
      el.appendChild(more);
    }
    el.style.display = 'block';
    this.listOpen = true;
    this.eInput.setAttribute('aria-expanded', 'true');
    this.positionList();
    this.scrollHighlightIntoView();
  }

  closeList() {
    this.listOpen = false;
    this.highlight = -1;
    if (this.eInput) this.eInput.setAttribute('aria-expanded', 'false');
    if (eList) { eList.style.display = 'none'; eList.innerHTML = ''; }
  }

  positionList() {
    if (!eList || !this.listOpen) return;
    const cell = this.params.eGridCell;
    if (!cell) return;
    const r = cell.getBoundingClientRect();
    eList.style.minWidth = `${Math.max(r.width, 160)}px`;
    eList.style.left = `${Math.round(r.left)}px`;
    const below = window.innerHeight - r.bottom;
    const h = eList.offsetHeight;
    // Flip above only when there is genuinely no room below AND more room above, so the
    // list does not jump between sides as rows scroll.
    if (below < h + 8 && r.top > below) {
      eList.style.top = `${Math.round(r.top - h - 2)}px`;
    } else {
      eList.style.top = `${Math.round(r.bottom + 2)}px`;
    }
  }

  scrollHighlightIntoView() {
    if (!eList || this.highlight < 0) return;
    const row = eList.children[this.highlight];
    if (row && row.scrollIntoView) row.scrollIntoView({ block: 'nearest' });
  }

  moveHighlight(step) {
    if (!this.listOpen || this.values.length === 0) return;
    const next = Math.min(this.values.length - 1, Math.max(0, this.highlight + step));
    if (next === this.highlight) return;
    const prev = eList && eList.children[this.highlight];
    if (prev) { prev.classList.remove('is-active'); prev.setAttribute('aria-selected', 'false'); }
    this.highlight = next;
    const now = eList && eList.children[this.highlight];
    if (now) { now.classList.add('is-active'); now.setAttribute('aria-selected', 'true'); }
    this.scrollHighlightIntoView();
  }

  /** Writes the highlighted candidate into the input SYNCHRONOUSLY. Nothing is deferred. */
  acceptHighlight() {
    if (this.highlight < 0 || this.highlight >= this.values.length) return false;
    this.eInput.value = this.values[this.highlight];
    this.closeList();
    return true;
  }

  // ── The keyboard contract ────────────────────────────────────────────────────
  onKeyDown(event) {
    const key = event.key;

    // IME first, and unconditionally. Mid-composition Enter belongs to the IME: it
    // finalises the Hangul syllable. Hijacking it would substitute a candidate while the
    // operator was only closing a character, and this product is typed in Korean.
    // `keyCode === 229` is the pre-`isComposing` shape the same condition takes.
    const composing = event.isComposing === true || event.keyCode === 229;
    if (composing) {
      if (key === 'Enter' || key === 'Tab' || key === 'Escape' || ARROW_STEP[key]) return 'suppress';
      return 'pass';
    }

    if (ARROW_STEP[key] && !event.ctrlKey && !event.metaKey && !event.altKey) {
      if (this.listOpen) {
        event.preventDefault(); // or the caret jumps to the start/end of the input
        this.moveHighlight(ARROW_STEP[key]);
        return 'suppress';
      }
      // ArrowDown reopens a list dismissed with Escape, at no extra typing. ArrowUp does
      // not, so the operator who wants their own text keeps a direction that never
      // resurrects the list.
      if (key === 'ArrowDown' && this.suggestible()) {
        event.preventDefault();
        this.scheduleQuery();
        return 'suppress';
      }
      return 'pass';
    }

    if (key === 'Escape') {
      if (this.listOpen) {
        // Dismiss the LIST only. The typed text stays in the input, so the next Enter
        // commits what the operator actually typed. This is the escape hatch that makes
        // first-match-highlighted safe: without it, a new value that happens to be a
        // prefix of an existing one could not be entered at all.
        this.closeList();
        return 'suppress';
      }
      return 'pass'; // second Escape = AG-Grid's normal cancel-edit
    }

    if (key === 'Enter' || key === 'Tab') {
      // Ctrl+Enter is the pre-existing bulk fill. Accept the candidate into the input and
      // then PASS, so `grid.js`'s branch reads the accepted value out of `getValue()` and
      // fills the whole range with it — one press there too.
      if (key === 'Enter' && (event.ctrlKey || event.metaKey)) {
        this.acceptHighlight();
        return 'pass';
      }
      // The one-Enter path. `acceptHighlight` has already written the candidate, so
      // returning 'accepted' lets THIS SAME EVENT run AG-Grid's stopEditing, which reads
      // `getValue()`. Tab takes the identical path and then moves on, so the highlight
      // means one thing regardless of which key commits it.
      if (this.listOpen && this.acceptHighlight()) return 'accepted';
      return 'pass';
    }

    return 'pass';
  }
}
