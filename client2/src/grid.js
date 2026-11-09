import { createGrid } from 'ag-grid-community';
import { FormulaHeader } from './formula_popover.js';
import { pageLimit, API_BASE } from './config.js';
import { state, updateVisibleColIndexMap, joinResolvedColumn, visibleRangeColIds, isDataColumn, pivotShown } from './state.js';
import { pivotColumns, itemOf, isNewPivotRow, headerWord, HeldColumnFilter, carryColumns, carryText } from './grid_pivot.js';
import { ENTERED, ROW, GROUP, ITEM, dropPlace } from './grid_order.js';
import { PERSON, ROLES, lookOf, isColour, lookStyle, hasPickedColour } from './grid_look.js';
import { setDisabledReason } from './disabled_reason.js';
import { unitText } from './ui_words.js';
// C-107. 「쓸 수 있나」는 한 규칙이 답합니다 — 편집 진입도 쓰기의 문입니다.
import { writeRefusal, cellToSend, sayStopped } from './write_guard.js';
import { elements } from './dom.js';
import { pagingView } from './match_count.js';
import { narrowingParams } from './narrowing.js';
// 🔴 닫는 방법은 Re-translate 드롭다운과 «같은 한 벌»입니다. 둘째가 나왔을 때 두 번째를
//    그리지 않는 것이 이 저장소의 상설입니다.
import { watchForDismiss, placeUnder } from './dropdown.js';
import { handleCellEdit, fetchData, readColumnValues, writePlace } from './api.js';
import { ValueFilter, ValueFloatingFilter, setWords } from './value_filter.js';
import { loadHistory } from './timeline.js';
import {
  isCellInRange,
  refreshRange,
  refreshSelectedRangeDiff,
  commitDragSelection,
  clearRangeSelection,
  endRangeGesture
} from './clipboard.js';
import { applyValueToSelectedRange, updateSelectedCellUI } from './ui.js';
import { SuggestCellEditor, handleEditorKey, isSuggestEditorActive } from './value_suggest.js';
import { refreshReferenceForSelection, fillTargetOrdinals, syncReferenceViewRule } from './enrichment_reference_view.js';
import { ledgerColumnDef } from './grid_ledger_column.js';
import { columnTypeParts } from './grid_image_column.js';
import { ImagePreview } from './image_preview.js';
import { HiddenColumns } from './hidden_columns.js';
import { localStamp, NO_TIME } from './server_time.js';
import { ABSENT, isBlank } from './absent.js';
import { markWork } from './ui_stall.js';
import { chainTipLines } from './flow_strip.js';

// ── [0b-c] Keyboard range selection (Shift+Arrow) ───────────────────────────────
// The bulk-fill engine already existed: `applyValueToSelectedRange` (ui.js) does the
// write, and Ctrl+Enter while editing already routes into it (see suppressKeyboardEvent
// below). What was missing was a way to SELECT the range without a mouse — and on the
// interaction-effort metric a mouse press costs 3 points against a keystroke's 1, so a
// bulk fill that still needs a drag gives most of its saving straight back.
//
// This deliberately reuses the EXISTING selection model rather than adding a second one:
// the anchor lives in `state.dragStartCell`, the moving end in `state.dragEndCell`, and
// `isCellInRange` / `refreshSelectedRangeDiff` (clipboard.js) already render exactly that
// rectangle. Nothing here invents a new range representation.
//
// Why it does NOT materialise into `state.selectedCellsMap`: that is precisely what
// Shift+CLICK does not do either (see onCellMouseDown), and `applyValueToSelectedRange`
// reads the map FIRST and only falls back to the rectangle. Committing on every arrow
// press would leave a stale keyboard rectangle in the map that then WINS over a later
// Shift+click rectangle — the user would see one selection and overwrite another.
// Matching Shift+click keeps one behaviour, not two.
const RANGE_ARROW_DELTA = Object.freeze({
  ArrowUp: { r: -1, c: 0 },
  ArrowDown: { r: 1, c: 0 },
  ArrowLeft: { r: 0, c: -1 },
  ArrowRight: { r: 0, c: 1 }
});


/**
 * Extend (or seed) the keyboard range rectangle by one cell.
 * @returns {boolean} true when the event was consumed and AG-Grid must not also act.
 */
function extendRangeByKeyboard(api, key) {
  const delta = RANGE_ARROW_DELTA[key];
  if (!delta || !api) return false;

  const cols = visibleRangeColIds();
  if (cols.length === 0) return false;

  // First Shift+Arrow of a selection: the anchor is wherever focus already is, so the
  // user never has to click to establish a starting point.
  if (!state.dragStartCell || !state.dragEndCell) {
    const focused = api.getFocusedCell();
    if (!focused || !focused.column) return false;
    const colId = focused.column.getColId();
    if (!isDataColumn(colId)) return false;
    state.dragStartCell = { rowIndex: focused.rowIndex, colId };
    state.dragEndCell = { rowIndex: focused.rowIndex, colId };
  }

  const prevEnd = { rowIndex: state.dragEndCell.rowIndex, colId: state.dragEndCell.colId };

  const lastRow = Math.max(0, api.getDisplayedRowCount() - 1);
  const nextRow = Math.min(lastRow, Math.max(0, prevEnd.rowIndex + delta.r));

  const currentColIdx = cols.indexOf(prevEnd.colId);
  const baseColIdx = currentColIdx === -1 ? 0 : currentColIdx;
  const nextColId = cols[Math.min(cols.length - 1, Math.max(0, baseColIdx + delta.c))];

  // Clamped against an edge. Consume the event anyway: letting AG-Grid handle it would
  // move focus out of the rectangle and the anchor would be lost mid-selection.
  if (nextRow === prevEnd.rowIndex && nextColId === prevEnd.colId) return true;

  state.dragEndCell = { rowIndex: nextRow, colId: nextColId };
  state.isDraggingRange = false;

  refreshSelectedRangeDiff(api, state.dragStartCell, prevEnd, state.dragEndCell);

  // Follow the growing edge. Convenience only — a scroll failure must never break the
  // selection that already succeeded.
  try {
    api.ensureIndexVisible(nextRow);
    api.ensureColumnVisible(nextColId);
  } catch (err) { /* non-fatal */ }

  return true;
}

// 🔴 MODULE LEVEL, AND ONLY SO IT CAN BE IMPORTED BY A HARNESS THAT DOES NOT RUN AG-GRID.
//    It used to be an arrow inside `renderGrid`'s `gridOptions`, which meant the only way to
//    reach it was to build a grid — so the harness sliced it out of this file as TEXT, and
//    every import the file gained broke that harness while the code was correct.
// ⚠️ THE MOVE HAS ZERO DEGREES OF FREEDOM, and that was checked before making it: every name
//    this body closes over is already module level — `RANGE_ARROW_DELTA`, `extendRangeByKeyboard`,
//    `state`, `clearRangeSelection`, `applyValueToSelectedRange`, `handleEditorKey`,
//    `isSuggestEditorActive`. No `renderGrid` local (`gridDiv`, `gridOptions`, `columnDefs`,
//    `initialRows`) appears in it — measured, zero occurrences. So this is a move, not a change.
// 🔴 `export` is the RESULT, not the point. The point is that the behaviour stops being
//    reachable only through a live grid.
export function suppressKeyboardEvent(params) {
  const event = params.event;
  const key = event.key;

  // ── [0b-a] Suggestion list keys, FIRST and while editing ────────────────
  // This hook is the deterministic ordering primitive for the one-Enter property.
  // AG-Grid's `processCellKeyboardEvent` consults `suppressKeyboardEvent` BEFORE it
  // runs `cellCtrl.onKeyDown`, and `onKeyDown`'s Enter branch is what calls
  // `stopEditing` -> `cellEditor.getValue()`. So an 'accepted' verdict here means the
  // candidate is ALREADY in the input by the time the very same event dispatch
  // commits the cell: accept and commit are one press, not two, and the ordering is
  // guaranteed by the framework's own sequence rather than by a timer or a
  // microtask. Returning false is therefore not "giving up" — it is the commit.
  if (params.editing && isSuggestEditorActive()) {
    const verdict = handleEditorKey(event);
    if (verdict === 'suppress') return true;   // the list consumed the key
    if (verdict === 'accepted') return false;  // let THIS event commit the candidate
    // 'pass' falls through to the pre-existing branches below, unchanged.
  }

  if (params.editing && event.ctrlKey && key === 'Enter') {
    event.preventDefault();
    const editors = params.api.getCellEditorInstances();
    if (editors && editors.length > 0) {
      const editingValue = editors[0].getValue();
      params.api.stopEditing(true);
      applyValueToSelectedRange(editingValue);
    }
    return true;
  }

  // [0b-c] Shift+Arrow grows the bulk-fill rectangle with no mouse involved.
  // Ctrl/Alt are excluded so this never shadows a browser or grid chord.
  if (!params.editing && event.shiftKey && !event.ctrlKey && !event.metaKey
      && !event.altKey && RANGE_ARROW_DELTA[key]) {
    event.preventDefault();
    return extendRangeByKeyboard(params.api, key);
  }

  // A PLAIN arrow collapses the range, and this is a data-safety guard rather than
  // tidiness: without it a rectangle selected by Shift+Arrow stays live after the
  // user has arrowed away from it, and the next Ctrl+Enter writes the typed value
  // into cells they no longer believe are selected. The mouse path already behaves
  // this way (a plain mousedown calls clearRangeSelection); the keyboard path has
  // to match it or the two disagree about what is selected.
  if (!params.editing && !event.shiftKey && RANGE_ARROW_DELTA[key]
      && (state.dragStartCell || Object.keys(state.selectedCellsMap).length > 0)) {
    clearRangeSelection();
    return false; // AG-Grid still moves focus — only the rectangle is dropped
  }

  // Escape abandons a keyboard range the same way it abandons an edit.
  if (!params.editing && key === 'Escape'
      && (state.dragStartCell || Object.keys(state.selectedCellsMap).length > 0)) {
    clearRangeSelection();
    return false;
  }

  if (!params.editing && (key === 'Delete' || key === 'Backspace')) {
    return true;
  }
  return false;
}


// Apply AG-Grid client-side sorting configuration based on Sort Latest toggle
/**
 * A-6. THE SORT THE SERVER IS BEING ASKED FOR — spelled ONCE.
 *
 * 🔴 IT WAS SPELLED TWICE. `api.fetchData` and `timeline.navigatorStep3` each wrote
 *    `order_by=${sortLatest ? 'updated_at' : 'row_id'}&order_desc=${sortLatest}` by hand. Two
 *    copies of one decision is criterion ④, and the day a header sort became a server sort
 *    they would have diverged silently: the grid would show one order and a row jump would
 *    compute its offset in another, which is a wrong scroll position with nothing on screen
 *    saying so. Both callers now ask here.
 */
export function sortParams() {
  if (state.serverSort) {
    return { orderBy: state.serverSort.colId, orderDesc: !!state.serverSort.desc };
  }
  // a table that reads in its entered order - rows, and in pivot view groups and items (owner 11-06)
  if (state.currentOrder === ENTERED) return { orderBy: ENTERED, orderDesc: false };
  // a pivot view's groups in key order - its rows have no updated_at of their own (owner 10-22)
  if (pivotShown()) return { orderBy: 'row_id', orderDesc: false };
  const sortLatest = elements.sortLatestToggle.checked;
  return { orderBy: sortLatest ? 'updated_at' : 'row_id', orderDesc: sortLatest };
}

/** «Sort latest» is not this table's when it reads in its entered order - off, and why (owner 11-06). */
export const SORT_LATEST_ENTERED_NOTE = 'This table reads in the order its rows were entered';
export function drawOrder() {
  setDisabledReason(elements.sortLatestToggle, state.currentOrder === ENTERED ? SORT_LATEST_ENTERED_NOTE : '');
}

/** A row or an item can be dragged to a place: the table reads in its entered order as it is, not under a header sort,
 *  and it can be written. A place is written at once, staged edits or not - it moves a row, it edits no cell. */
const placing = () => state.currentOrder === ENTERED && !state.serverSort && !writeRefusal();

/** The rows shown, in order, each with its order key and what a place is written on (a group: its first row_id). */
function shownRows() {
  const rows = [];
  for (let i = 0; i < state.gridApi.getDisplayedRowCount(); i += 1) {
    const node = state.gridApi.getDisplayedRowAtIndex(i);
    if (node && node.data) rows.push(node);
  }
  return rows;
}

/** Another page before / after the rows shown - a drop at that edge cannot say its place. */
function pageEdges() {
  const paged = state.viewMode === 'pagination' && !state.allDataLoaded;
  return { openStart: paged && state.currentSkip > 0, openEnd: Boolean(state.hasMoreData) };
}

/** A row dropped (AG Grid's rowDragEnd): its place between the rows it lands among, written; the row moved there. */
function dropRow(event) {
  if (!placing() || !event.node || !event.node.data) return;
  const nodes = shownRows();
  const keyOf = (node) => node.data.order_key;
  if (nodes.some((node) => !keyOf(node))) return sayStopped(SAVE_NEW_ROWS_FIRST_NOTE);
  const from = nodes.indexOf(event.node);
  const dropped = dropPlace(nodes.map(keyOf), from, event.overIndex, pageEdges());
  if (!dropped) return;
  if (dropped.refused) return sayStopped(dropped.refused);
  const data = event.node.data;
  const pivoted = pivotShown();
  writePlace(pivoted ? GROUP : ROW, pivoted ? data.first : data.row_id, dropped.place).then((written) => {
    if (!written) return;
    data.order_key = dropped.place;
    state.gridApi.applyTransaction({ remove: [data] });
    state.gridApi.applyTransaction({ add: [data], addIndex: event.overIndex });
  });
}
/** A new pivot row has no place until its first value makes its long rows. */
export const SAVE_NEW_ROWS_FIRST_NOTE = 'Save the new rows before moving rows';

/** An item column moved by its header (columnMoved, finished): its place between the item columns it lands among. */
function dropItem(event) {
  const item = event.column && itemOf(event.column.getColId());
  if (!event.finished || event.source !== 'uiColumnMoved' || item === null || !placing() || !pivotShown()) return;
  const places = (state.pivotView && state.pivotView.item_places) || {};
  const shown = state.pivotView.items;
  const now = state.gridApi.getAllGridColumns().map((col) => itemOf(col.getColId())).filter((name) => name !== null);
  const to = now.indexOf(item);
  const dropped = dropPlace(shown.map((name) => (places[name] || {}).order_key), shown.indexOf(item), to,
    { openEnd: Boolean(state.pivotView.items_more) });
  if (!dropped) return;
  if (dropped.refused) { sayStopped(dropped.refused); state.gridApi.setGridOption('columnDefs', buildColumnDefs()); return; }
  writePlace(ITEM, places[item].first, dropped.place).then((written) => {
    if (written) {
      places[item] = { ...places[item], order_key: dropped.place };
      state.pivotView.items = now;
    } else {
      state.gridApi.setGridOption('columnDefs', buildColumnDefs());
    }
  });
}

/** The same pair as a query tail, so no caller re-spells the parameter names either. */
export function sortQueryTail() {
  const { orderBy, orderDesc } = sortParams();
  return `&order_by=${encodeURIComponent(orderBy)}&order_desc=${orderDesc}`;
}

/**
 * A-6. Does the grid hold the WHOLE table right now? Only then is a local sort already the
 * whole-table sort.
 *
 * 🔴 `allDataLoaded` ALONE IS NOT THE ANSWER, and reading it as one shipped a defect for one
 *    round. That flag is set by the 「Load All」 button and by nothing else — a 907-row table
 *    that arrives complete in its first page never sets it. Measured in the browser: sorting
 *    that table's header fired two requests it did not need, for rows the grid already had.
 * 🔴 `hasMoreData` IS THE FACT: the last fetch came back short of `pageLimit`, so there is no
 *    page after this one. What it does NOT say is whether there is a page BEFORE this one —
 *    page 35 of 35 is also "no more data" and is emphatically not the table. In pagination
 *    that is what `currentSkip === 0` adds; in infinite scrolling every earlier page is still
 *    in the grid, so being at the end IS holding everything.
 */
export function holdsWholeTable() {
  if (state.allDataLoaded) return true;
  if (state.hasMoreData) return false;
  return state.viewMode === 'infinite' || state.currentSkip === 0;
}

// 🔴 RE-ENTRANCY. `updateGridSortState` calls `applyColumnState`, which raises `sortChanged`;
//    without this the handler below would treat the grid's own repaint as an operator action
//    and fetch again, forever. AG-Grid's `source` already tells them apart
//    (`uiColumnSorted` vs `api`) and the handler checks it — this flag is the second lock,
//    because the cost of the first one being wrong in some version is an infinite fetch loop.
let applyingSortState = false;

// A table's filters die with it (lead 10-12): the grid keeps a filter across a columnDefs swap for a column id it still
// has, and ROW_ID is on every table - the last table's filter ran the next one's reads to 0 rows. Dropping them reads
// nothing of its own: the switch's first read, after the new columns, is the table's, and its renderGrid draws the chips
// again. AG Grid says filterChanged after a timer (18766, lead 80172956e: the read went out with the schema read), so
// the drop waits for that one event and takes it - with a time cap, so a grid that never says it cannot hold the switch.
// A pivot switch puts some back after its columns change (owner 11-05 ㄴ): `keep` is the model set; the model already
// that is no change.
const FILTER_DROP_WAIT_MS = 1000;
let takeFilterChange = null;
export function dropGridFilters(keep = null) {
  const api = state.gridApi;
  if (!api || JSON.stringify(api.getFilterModel() || {}) === JSON.stringify(keep || {})) return Promise.resolve();
  return new Promise((done) => {
    const timer = setTimeout(() => { takeFilterChange = null; done(); }, FILTER_DROP_WAIT_MS);
    takeFilterChange = () => { clearTimeout(timer); takeFilterChange = null; done(); };
    api.setFilterModel(keep);
  });
}

/** The grid's filterChanged: a read of the narrowed table, and the chips - unless it is the drop's own event. */
export function gridFilterChanged() {
  if (takeFilterChange) { takeFilterChange(); return; }
  // a column swap says filterChanged when columns that had a filter go, the filters as they were (a pivot switch's): the
  // rows on screen were read with them
  if (!filterReadsHeld && (narrowingParams({ gridApi: state.gridApi }).get('filters') || '') !== state.readFilters) fetchData(true);
  renderFilterBar();
}

/** A pivot switch changes the columns and sets its filters, and the grid says filterChanged on its own timers for both:
 *  held, those read nothing - the switch reads once itself. -> the release, once its read is out. */
let filterReadsHeld = 0;
export function holdFilterReads() {
  filterReadsHeld += 1;
  let released = false;
  return () => { if (!released) { released = true; filterReadsHeld -= 1; } };
}

export function updateGridSortState() {
  if (!state.gridApi) return;

  // Do not re-sort if Tx Mode is active to prevent staged rows from jumping
  if (state.txModeActive) {
    return;
  }

  // Do not re-sort if user is actively editing a cell to prevent the row from jumping away
  const editingCells = state.gridApi.getEditingCells();
  if (editingCells && editingCells.length > 0) {
    return;
  }

  // 🔴 THE HEADER MUST KEEP SAYING WHAT THE SERVER WAS ASKED. This runs after every fetch and
  //    used to blank every sort but the toggle's two (`defaultState: { sort: null }`), so a
  //    header sort that now CAUSES a fetch would have had its own arrow wiped by the response
  //    it asked for — the operator would press, the rows would change, and the indicator would
  //    jump back to 최신순.
  const { orderBy, orderDesc } = sortParams();
  applyingSortState = true;
  try {
    state.gridApi.applyColumnState({
      state: [{ colId: orderBy, sort: orderDesc ? 'desc' : 'asc' }],
      defaultState: { sort: null }
    });
  } finally {
    applyingSortState = false;
  }
}

/** The system columns every table carries - drawn read-only, not filtered (row_id is), and left out of the gallery's values. */
const SYSTEM_COLUMNS = Object.freeze(['created_at', 'updated_at', 'row_id', 'id', 'updated_by']);
export const isSystemColumn = (col) => SYSTEM_COLUMNS.includes(col);

/** The rows the grid holds, in its filter's and sort's order - what the gallery shows (lead 77ffe5cb6: no rows of its own).
 *  `cell(column)` is the grid's own text of that cell (its column's getter and formatter - row_id · created_at live beside `data`). */
export function gridRowsInOrder() {
  const out = [];
  if (state.gridApi) state.gridApi.forEachNodeAfterFilterAndSort((node) => { if (node.data) out.push({ id: node.id, data: node.data,
    cell: (column) => state.gridApi.getCellValue({ rowNode: node, colKey: column, useFormatter: true }),
    value: (column) => state.gridApi.getCellValue({ rowNode: node, colKey: column }) }); });
  return out;
}

/** The grid's filter on these columns set to these values, its other filters kept - the gallery's «Filter grid to this cell»
 *  (lead 3589216b9: the grid's own filter model, no filter of the gallery's). A blank value is the blank filter. */
export function filterGridTo(pairs) {
  const api = state.gridApi;
  if (!api) return;
  const model = { ...(api.getFilterModel() || {}) };
  for (const { column, value } of pairs) {
    const number = (state.currentColumnTypes || {})[column] === 'number';
    const filterType = number ? 'number' : 'text';
    model[column] = isBlank(value) ? { filterType, type: 'blank' } : { filterType, type: 'equals', filter: number ? Number(value) : String(value) };
  }
  api.setFilterModel(model);
}

/** The next page added to the rows held (infinite scrolling's one step) - the grid near its bottom and the gallery's «Load more».
 *  -> false when there is none to add or one is on its way. */
export function appendNextRows() {
  if (state.isLoadingMore || !state.hasMoreData || state.allDataLoaded) return false;
  state.currentSkip += pageLimit;
  fetchData(false);
  return true;
}

/** That row brought into view and picked in the grid - the gallery's «Show in grid». */
export function showGridRow(id) {
  const api = state.gridApi;
  const node = api && api.getRowNode(String(id));
  if (!node) return false;
  api.ensureNodeVisible(node, 'middle');
  api.deselectAll();
  node.setSelected(true);
  return true;
}

// Update Loaded count slice text
export function updateLoadedCount(forcedCount = null) {
  if (!state.gridApi) return;
  const displayedCount = state.gridApi.getDisplayedRowCount();

  if (state.viewMode === 'infinite') {
    elements.exposedRowsCount.textContent = `1 - ${displayedCount}`;
  } else {
    const forced = forcedCount !== null ? forcedCount : displayedCount;
    const startRow = forced === 0 ? 0 : state.currentSkip + 1;
    const endRow = state.currentSkip + forced;

    if (startRow === endRow) {
      if (startRow === 0) {
        elements.exposedRowsCount.textContent = `0`;
      } else {
        elements.exposedRowsCount.textContent = `${startRow}`;
      }
    } else {
      elements.exposedRowsCount.textContent = `${startRow} - ${endRow}`;
    }
  }
}

// Update View Mode UI controls visibility
export function updateViewModeUI() {
  const paginationControls = document.querySelector('.pagination-controls');
  if (paginationControls) {
    paginationControls.style.display = (state.viewMode === 'pagination') ? 'flex' : 'none';
  }
}

// Update Pagination controls state
//
// 🔴 「몇 쪽인가」는 `match_count.js` 가 답합니다. 여기서 `Math.ceil(total / pageLimit) || 1` 을
//    직접 쓰면 «아직 안 센 표»(total = null)가 「1쪽뿐」이 되어 다음 버튼이 꺼집니다 --
//    세는 동안 다음 쪽으로 못 갑니다. 「모른다」와 「1쪽뿐」은 다른 상태입니다.
export function updatePaginationUI(count, shown) {
  const view = pagingView(count, state.currentSkip, pageLimit, shown);

  if (elements.pageInput) {
    elements.pageInput.value = view.currentPage;
    // 모르는 동안은 상한을 «걸지 않습니다». 1 로 두면 입력이 1쪽에 묶입니다.
    if (view.totalPages === null) elements.pageInput.removeAttribute('max');
    else elements.pageInput.max = view.totalPages;
  }
  if (elements.totalPagesSpan) {
    elements.totalPagesSpan.textContent = view.totalPagesText;
  }
  if (elements.prevPageBtn) {
    elements.prevPageBtn.disabled = view.prevDisabled;
  }
  if (elements.nextPageBtn) {
    elements.nextPageBtn.disabled = view.nextDisabled;
  }
}

// ── The filter bar: what is narrowing the grid, and what is off to the right ─────────────
//
// ONE strip carrying two conditional facts, and `display: none` whenever it has neither.
// A permanent band above the grid would be a new region, which the screen's constitution
// forbids; a band that appears only when there is something to read is the existing
// `#tx-filter-banner` pattern, reused rather than reinvented.

let clearAllWired = false;
let chipsMoreWired = false;
// Whether the operator has opened the fold. Module-level like `clearAllWired` above, because
// this module is the screen's own strip and not one of the mountable parts.
let chipsOpen = false;
// 펼쳐졌을 때 칩이 사는 판. 스트립의 자기 div «안»에 있지만 위치 조상은 헤더입니다.
let chipsPanel = null;
let chipsDetach = null;
// The strip's «N hidden» part, born with the strip's first draw.
let hiddenPart = null;

/** Hides or shows data columns - the column chooser, a header's «Hide column» and «N hidden» all come here (owner 11-05). */
export function setColumnsHidden(colIds, hidden) {
  if (state.gridApi) state.gridApi.setColumnsVisible(colIds.filter(isDataColumn), !hidden);
}

/** The data columns hidden now, in the grid's order, by their header words. */
const hiddenColumns = (api) => (api ? api.getColumns() || [] : [])
  .filter((col) => isDataColumn(col.getColId()) && !col.isVisible())
  .map((col) => ({ id: col.getColId(), word: col.getColDef().headerName || col.getColId() }));
// Below this the truncated chip is a sliver that names nothing, and `+N 필터` alone says more.
const READABLE_CHIP_PX = 90;

/**
 * One active filter as the operator would say it: `<COLUMN> <type> <value>`.
 *
 * The value is read off the MODEL, never off the input. AG-Grid's combined conditions
 * (`operator: 'AND'` with a `conditions` array) have no single input to read, and a
 * renderer that special-cased "one condition" vs "two" would be carrying an arity branch
 * that the model already answers by its own length.
 */
function filterChipText(colId, model) {
  const conditions = (Array.isArray(model?.conditions) && model.conditions.length)
    ? model.conditions
    : [model || {}];
  const clause = (m) => {
    const from = m.filter ?? m.dateFrom ?? '';
    const to = m.filterTo ?? m.dateTo ?? '';
    const value = String(to) !== '' ? `${from}~${to}` : String(from);
    return value === '' ? String(m.type || '') : `${m.type} ${value}`;
  };
  // ⇲ = the SERVER resolves this predicate through a join. It is a fact about the FILTER,
  // not about the column, which is why it is keyed off `joinResolvedColumn` and not off
  // `isVirtualColumn`: a `collide` column is stored, carries no 🔗 in its header, and its
  // filter still runs against the joined COALESCE rather than against storage.
  const mark = joinResolvedColumn(colId) ? '⇲' : '';
  const body = model?.filterType === 'set' ? setWords(model) : conditions.map(clause).join(` ${model?.operator || 'AND'} `);
  return `${colId.toUpperCase()}${mark} ${body}`.trim();
}

/**
 * How many columns sit past the right edge of the body viewport right now.
 *
 * Measured against the horizontal pixel range rather than counted off a column list,
 * because "pushed off" is a question about the VIEWPORT and the answer changes on scroll,
 * on a sidebar drag and on a column resize without any column list changing. Pinned
 * columns are excluded: they are never unreachable, so counting them would report an
 * obstacle that does not exist.
 */
function offscreenColumnCount(api) {
  if (!api || typeof api.getHorizontalPixelRange !== 'function') return 0;
  const range = api.getHorizontalPixelRange();
  if (!range) return 0;
  return (api.getAllDisplayedColumns() || []).filter(col => {
    if (typeof col.getPinned === 'function' && col.getPinned()) return false;
    return (col.getLeft() + col.getActualWidth()) > range.right + 1;
  }).length;
}

/**
 * The `+N열 →` end of the strip, plus the strip's own visibility.
 *
 * Split from `renderFilterBar` because this one runs on every scroll frame and rebuilding
 * the chips there would throw away the operator's DOM sixty times a second.
 */
export function updateOffscreenIndicator() {
  const bar = elements.gridFilterBar;
  if (!bar) return;
  const count = offscreenColumnCount(state.gridApi);
  const badge = elements.offscreenCols;
  // Written only when the count moves: this runs on every scroll frame, and the same words written again there
  // re-styled the grid's section each frame (lead 10-09). The badge holds the count it last said.
  if (badge && badge.dataset.count !== String(count)) {
    badge.dataset.count = String(count);
    // Saying it is the whole point. A column that scrolled out of view with nothing on
    // screen to say so reads as a column that is GONE, and the next question is asked of
    // the table config rather than of the scrollbar.
    badge.textContent = count > 0 ? `+${unitText(count, 'col')} →` : '';
    badge.title = count > 0 ? 'Scroll right to reach them' : '';
    badge.style.display = count > 0 ? '' : 'none';
  }
  // 🔴 THE BAR IS NO LONGER TOGGLED HERE. It now also holds the Tx filter banner, whose
  // display is written from FOUR places (ui.js, timeline.js x2, api.js); a visibility rule
  // that only counted chips hid the Tx banner whenever no column filter happened to be on.
  // The bar draws nothing of its own -- no background, no border -- so an empty one is
  // already invisible, and the condition that could disagree with its contents is gone.
}

/** Rebuild the chips from `getFilterModel()`, then re-measure the right-hand end. */
export function renderFilterBar() {
  const bar = elements.gridFilterBar;
  if (!bar) return;
  markWork('filters', state.currentTable);
  const api = state.gridApi;
  const model = api ? (api.getFilterModel() || {}) : {};
  const colIds = Object.keys(model);
  const chips = elements.filterChips;

  if (chips) {
    chips.replaceChildren();
    // 판이 열려 있으면 그 안의 칩도 «옛것»입니다. 안 지우면 새 칩과 옛 칩이 둘 다 남습니다.
    if (chipsPanel) chipsPanel.replaceChildren();
    colIds.forEach(colId => {
      const chip = document.createElement('span');
      chip.className = 'filter-chip';
      const label = document.createElement('span');
      label.className = 'filter-chip-label';
      label.textContent = filterChipText(colId, model[colId]);
      // The chip may be cut to fit the header's one row; its whole value is its title (lead bfb62503e).
      label.title = label.textContent;
      label.setAttribute('data-clip-ok', '');
      const remove = document.createElement('button');
      remove.type = 'button';
      // Phase 0: the banner's own close button, not a private one that looks like it.
      remove.className = 'clear-banner-btn';
      remove.textContent = '✕';
      remove.title = `Clear the ${colId.toUpperCase()} filter`;
      remove.addEventListener('click', () => {
        // `setColumnFilterModel` is async in AG-Grid 33+ and synchronous before it. Wrapping
        // in `Promise.resolve` means the refresh lands AFTER the model actually changed on
        // either version, instead of racing it on one of them.
        Promise.resolve(api.setColumnFilterModel(colId, null))
          .then(() => api.onFilterChanged());
      });
      chip.append(label, remove);
      chips.appendChild(chip);
    });
  }

  const more = elements.filterChipsMore;
  if (more && !chipsMoreWired) {
    chipsMoreWired = true;
    more.addEventListener('click', () => setChipsOpen(!chipsOpen));
  }

  const clearAll = elements.filterClearAll;
  if (clearAll) {
    // Shown from the SECOND chip on. With one filter its ✕ already is "clear everything",
    // and two controls doing the identical thing is the duplication this screen keeps out.
    clearAll.style.display = colIds.length > 1 ? '' : 'none';
    if (!clearAllWired) {
      clearAllWired = true;
      clearAll.addEventListener('click', () => {
        if (!state.gridApi) return;
        Promise.resolve(state.gridApi.setFilterModel(null))
          .then(() => state.gridApi.onFilterChanged());
      });
    }
  }

  if (!hiddenPart) hiddenPart = new HiddenColumns(bar, { doc: document, show: (ids) => setColumnsHidden(ids, false) });
  hiddenPart.draw(hiddenColumns(api));

  foldFilterChips();
  updateOffscreenIndicator();
}

/**
 * Fold the chips that do not fit on one row behind a `+N`, or show them all when opened.
 *
 * 🔴 The widths are read BEFORE anything is hidden. Hiding a chip pulls every chip after it
 *    back into the row, so a loop that hid as it measured would call those "fitting" and fold
 *    exactly one of them however many overflow.
 *
 * Kept out of `updateOffscreenIndicator` on purpose: that one runs on every scroll frame, and
 * re-measuring the strip sixty times a second to answer a question only a RESIZE can change is
 * work with nothing to report. `onGridSizeChanged` is where the width actually moves.
 */
/** 펼침을 켜고 끕니다. 바깥 클릭과 Esc 는 드롭다운과 «같은 함수»가 답니다.
 *
 * 🔴 「안쪽」의 경계는 «바»입니다 -- 판도 「+N 필터」 버튼도 그 안에 있으므로 뱃지의 ✕ 를
 *    눌러도 닫히지 않고, 버튼을 다시 누르는 것이 «바깥 클릭»으로 세어지지도 않습니다.
 */
export function setChipsOpen(next) {
  chipsOpen = !!next;
  if (chipsDetach) { chipsDetach(); chipsDetach = null; }
  if (chipsOpen) {
    chipsDetach = watchForDismiss(document, elements.gridFilterBar, () => setChipsOpen(false));
  }
  foldFilterChips();
}

/** 펼친 판을 버튼 «아래»에 앉힙니다. 칩은 «옮겨» 옵니다 -- 다시 그리면 개별 ✕ 를 다시
 *  배선해야 하고, 그러면 이미 도는 것을 두 벌로 만드는 셈입니다. */
function showChipsPanel(all, bar, more) {
  if (!bar) return;
  if (!chipsPanel) {
    chipsPanel = document.createElement('div');
    // 스트립의 자기 div 에서 태어나고, placeUnder 가 body 로 옮겨 «+N» 밑에 둡니다(헤더 배율 밖, 소유자 10-09).
    // 판 안을 누른 것은 placedFrom 을 거쳐 여전히 스트립 «안»입니다.
    chipsPanel.className = 'glass-dropdown-panel filter-chips-panel';
    bar.appendChild(chipsPanel);
  }
  chipsPanel.replaceChildren(...all);
  // 오른쪽 끝을 버튼에 맞춥니다. 왼쪽에 맞추면 좁은 창에서 판이 화면 밖으로 나갑니다.
  placeUnder(chipsPanel, more);
}

/** 칩을 스트립으로 돌려놓고 판을 치웁니다. 판만 숨기면 다음 접힘이 «빈 스트립»을 잽니다. */
function hideChipsPanel(chips, all) {
  if (!chipsPanel) return;
  chips.append(...all);
  chipsPanel.remove();
  chipsPanel = null;
}

export function foldFilterChips() {
  const chips = elements.filterChips;
  const more = elements.filterChipsMore;
  const bar = elements.gridFilterBar;
  if (!chips || !more) return;
  // 🔴 칩은 접힘일 땐 «스트립»에, 펼침일 땐 «아래 판»에 삽니다. 어디에 있든 모읍니다 --
  //    한 곳만 보면 리사이즈로 다시 불렸을 때 판을 통째로 «비워» 버립니다.
  const all = Array.from(chips.children)
    .concat(chipsPanel ? Array.from(chipsPanel.children) : []);
  all.forEach(chip => { chip.style.display = ''; });

  // 🔴 How wide a chip may be. A chip may never reach past the bar, because the bar clips and
  //    the ✕ is at the chip's RIGHT end -- a chip that overruns loses its delete control
  //    entirely, and that filter can then only be cleared by clearing all of them. The label's
  //    ellipsis, already configured, does the rest once the chip is allowed to be narrow.
  if (chipsOpen && all.length) {
    more.textContent = 'Fold';
    more.title = 'Fold to one line';
    more.style.display = '';
    showChipsPanel(all, bar, more);
    return;
  }
  hideChipsPanel(chips, all);
  if (!all.length && chipsOpen) {
    chipsOpen = false;
    if (chipsDetach) { chipsDetach(); chipsDetach = null; }
  }
  // Folded, a chip may use this span, which is where it is clipped -- and `100%` of the span is
  // a question CSS answers at draw time, so it cannot go stale the way a measured number can.
  chips.style.setProperty('--chip-cap', '100%');
  // Back to the left first. A strip left scrolled from the opened state keeps that offset even
  // under `overflow: hidden`, and then every chip measures from where it was scrolled TO -- the
  // ones pushed off the left read as fitting and the fold folds nothing.
  chips.scrollLeft = 0;

  const box = chips.getBoundingClientRect();
  const barBox = bar ? bar.getBoundingClientRect() : box;
  // The room is what is VISIBLE, which on a tight header is less than this span's own box: the
  // span keeps its basis and the bar clips the overhang. Measuring the span alone would call a
  // chip "fitting" while the operator sees it sliced down the middle with no ellipsis to say so.
  const room = Math.max(0, Math.min(box.right, barBox.right) - box.left);
  // 🔴 Measured against THE STRIP, in the strip's own coordinates. `offsetLeft` is
  //    relative to the nearest positioned ancestor -- here the header, not this span -- so
  //    comparing it with `clientWidth` compares a page coordinate (1142) with a width (229)
  //    and every chip reads as overflowing. Live measurement, 2026-09-02: that folded ALL of
  //    them and the strip showed a count with nothing to count.
  const ends = all.map(chip => chip.getBoundingClientRect().right - box.left);
  // Under the cap the first chip always fits, so what is left to decide is whether the strip is
  // wide enough to read one in at all. Below that, `+N 필터` says more than a sliver of a chip.
  const hidden = room < READABLE_CHIP_PX
    ? all.slice()
    : all.filter((chip, i) => ends[i] > room + 1);
  hidden.forEach(chip => { chip.style.display = 'none'; });
  // Said, not swallowed: a filter that is hiding rows with nothing on screen to name it reads
  // as data that is GONE, and the next question gets asked of the table instead of the strip.
  more.textContent = `+${unitText(hidden.length, 'filter')}`;
  more.title = 'Click to unfold';
  more.style.display = hidden.length ? '' : 'none';
}

// Ensure that the cell data structure exists as an object. THE FIELD LIST IS THE ONE BELOW, and
// it is written out because the previous version of this line was not: it documented a cell as
// { value, is_overwrite, sources, updated_by } and named NEITHER field the paint rule reads.
// Measured 2026-09-06: of the five sites that mark a cell as user-overwritten, the three that
// set only `is_overwrite` are the three whose author had this sentence in front of them. A
// comment that lists a shape is read as the shape.
export function ensureCellObject(dataObj, colId) {
  if (!dataObj) return;
  if (!dataObj.data) dataObj.data = {};
  
  const cell = dataObj.data[colId];
  if (typeof cell !== 'object' || cell === null) {
    dataObj.data[colId] = {
      value: cell !== undefined ? cell : '',
      is_overwrite: false,
      is_collision_merge: false,
      sources: {},
      updated_by: 'system',
      priority_source: null
    };
  }
}

// 🔴 THE ONE PLACE THAT SAYS "A PERSON OVERWROTE THIS CELL", AND IT SAYS IT IN FULL.
//    The colour rules read `written_by` (grid_look.lookOf - «Written by person», a rule every table has) and the
//    server reads `priority_source`, NEVER `is_overwrite`, so a site that sets only `is_overwrite` leaves a real
//    overwrite drawn as an untouched cell until the next read. Measured 2026-09-06 across the five marking sites: two set both, three
//    set only `is_overwrite`, and the split is invisible on a cell that ALREADY carried a
//    'user' pin, because these patches merge -- it shows on a cell's FIRST overwrite, through
//    paste, range-write, or a transaction commit.
//    Adding the missing line at those three would come back at the fourth site, so the fact
//    has one writer instead. `PRIORITY_SOURCE_USER` is exported for the same reason: the rule
//    that reads this value and the code that writes it now share one spelling, so they cannot
//    drift apart in silence.
// ⚠️ NOT the rollback direction. Discard (api.js `discardPendingEdits`) restores both halves it staged, then reads the
//    rows again so the server's flag and pin replace them (lead 10-12).
export const PRIORITY_SOURCE_USER = 'user';

export function markCellOverwritten(dataObj, colId, value) {
  ensureCellObject(dataObj, colId);
  const cell = dataObj && dataObj.data ? dataObj.data[colId] : null;
  if (!cell) return;
  if (value !== undefined) cell.value = value;
  cell.is_overwrite = true;
  cell.priority_source = PRIORITY_SOURCE_USER;
  cell.written_by = PERSON;
}

// The raw stored value behind one grid cell, in the shape the row payload uses.
// Extracted so the stored-column and the virtual-column value getters read a cell the SAME
// way rather than each carrying its own copy of the unwrap: `attach` (server) fills a joined
// cell with the identical `{value, is_overwrite, sources, updated_by, priority_source}` keys
// `fetch_and_merge_metadata` uses, so one reader is correct for both.
function rawCellValue(rowData, colId) {
  const cell = (rowData && rowData.data) ? rowData.data[colId] : undefined;
  if (cell && typeof cell === 'object') {
    return cell.value !== undefined ? cell.value : '';
  }
  return cell !== undefined ? cell : '';
}

// The ONE numeric-display rule for a `number` column.
//
// 🔴 IT DELIBERATELY DOES NOT COERCE. A virtual join column carries its rule's
// `unresolved_label` ('미상' by default) on every row where the right table had no match or
// an empty value — so a column whose declared type is `number` genuinely does contain a
// string, by design. `Number('미상')` is NaN and the guard returns the ORIGINAL value, so the
// label reaches the cell intact instead of becoming NaN or 0. (`''`/`null`/`undefined` are
// excluded up front for the same reason: `Number('')` and `Number(null)` are both 0, which
// would turn an empty cell into a displayed zero.)
function numericDisplayValue(val) {
  if (val !== '' && val !== null && val !== undefined) {
    const parsed = Number(val);
    if (!isNaN(parsed)) {
      return parsed;
    }
  }
  return val;
}

// ── 시각 셀 — 「어느 순간인가」는 `server_time.js` 하나가 답하고, 값에서 offset 은 안 떨어진다 ──
//
// C-85 (소유자 그리드 실물). `ledger_events.occurred_at` 이 `2026-05-12 15:00:00+00:00` 으로
// 보였다. 서버는 시각을 «offset 단 ISO» 로 낸다(`to_local_str`) — 그런데 이 그리드에는
// datetime 갈래가 «아예 없었다»: `valueGetter` 가 `number` 하나만 모양 잡고 나머지는 그대로
// 흘린다. 그래서 UTC 숫자가 보는 사람의 벽시계인 «척» 셀에 앉았다.
//
// 🔴 표시«만» 바꾼다. 그 갈라짐이 이 자리의 전부다:
//    valueFormatter  AG-Grid 가 «그릴 때»만 읽는다             -> 보는 쪽 zone
//    valueGetter     서버가 준 글자를 그대로 낸다              -> 편집기 시작값 · valueSetter
//    clipboard.js    `copiedText` 를 지난다                    -> 복사도 보이는 글자 (소유자 11-07 이 원문 복사를 뒤집음:
//                    «yyyy-mm-dd hh:mm:ss» · Asia/Seoul. 붙여 넣으면 서버가 offset 없는 시각을 같은 zone 으로 읽어 같은 순간)
//    로컬 글자를 «값»으로 만들면, 안 고치고 커밋한 셀이 offset 없는 문자열을 되보내고
//    순간이 보는 사람의 zone 만큼 «움직인다» — 「자막 단 실패」 부류다
//
// ⚠️ 파싱은 `server_time.js` 에만 있다. 자르는 것이 C-77 에서 화면 «셋»의 offset 을 떨어뜨렸다.
const SYSTEM_TIME_COLUMNS = Object.freeze(['created_at', 'updated_at']);

/** 이 컬럼이 «시각»인가 — 선언된 `datetime` 이거나 봉투의 시각 둘. */
function isTimeColumn(col, colType) {
  return colType === 'datetime' || SYSTEM_TIME_COLUMNS.includes(col);
}

/**
 * 시각 셀의 «표시». 값은 손대지 않는다.
 *
 * 🔴 순간을 못 만들면 «받은 것»을 그대로 그린다. 한 줄이 둘에 답한다:
 *    빈 칸은 «빈 칸»으로 남는다 — `NO_TIME`('-') 을 그리면 이 그리드가 다른 컬럼에서 안 그리는
 *      글자를 시각 컬럼에만 지어내는 것이고, 편집 가능한 빈 셀이 «값이 있는 척»을 한다
 *    못 읽는 글자는 «자기 글자»로 남는다 — '-' 로 덮으면 운영자가 그것을 «잃고», 부재와 못 읽음이
 *      같은 모양이 된다. `numericDisplayValue` 가 NaN 에서 원본을 돌려주는 것과 같은 이유다
 * ⚠️ `val` 이 빈 값인지 «먼저 묻는 갈래»를 두지 않는다 — 실측(변이 하나): 그 갈래를 지워도 답이
 *    한 개도 안 바뀐다. `localStamp('')` 가 이미 `NO_TIME` 이라 아래 한 줄이 같은 답을 낸다.
 */
function timeCellFormatter(params) {
  const val = params ? params.value : undefined;
  const shown = localStamp(val);
  return shown === NO_TIME ? val : shown;
}

/** What a copy carries for a cell's value - a time column's as the cell shows it, any other's as sent (owner 11-07). */
export function copiedText(col, value) {
  return isTimeColumn(col, (state.currentColumnTypes || {})[col] || 'string') ? timeCellFormatter({ value }) : value;
}

// ── [Virtual join] The filter a JOIN-RESOLVED column gets ───────────────────────────────
//
// ONE helper for BOTH shapes `/schema.join_resolved_columns` announces: `virtual_only`
// (nothing stored at all) and `collide` (stored and editable, but whose filter the server
// still evaluates against the joined value). They need the identical answer, and a second
// copy of it is a second thing to forget when one of them moves.
//
// 🔴 ALWAYS TEXT, even for a column declared `number`. Not a preference — the server's
// contract: `main.get_column_filter_condition` states "an override is always treated as
// text" and does `cast(col_expr_override, String)` with `is_numeric = False`. An
// `agNumberColumnFilter` would send `greaterThan`/`inRange`, the server would evaluate them
// as STRING comparisons on that cast, and `'10' > '9'` is false lexically — a wrong answer
// wearing the costume of a working filter. Text is also what keeps the one query that
// matters expressible: the resolved value's domain is the right table's values PLUS
// `unresolved_label`, so `equals <label>` is the only way to ask for the unresolved rows,
// and no numeric predicate can express it.
//
// 🔴 `blank`/`notBlank` REMOVED. The resolved value is a COALESCE whose last arm is
// `unresolved_label`, which `virtual_join_config` guarantees is a non-empty string. So no
// row in such a column is ever blank: `blank` matches NOTHING and `notBlank` matches
// EVERYTHING, on every row, forever. Offering them is the UI making a claim it cannot keep
// — an operator reads `Matches: 0` as "there are none" rather than "this control does
// nothing". Measured on the live table before removal: blank -> 0 of 15,489, notBlank ->
// 15,489 of 15,489, while `equals` on the label returned the 4,052 unresolved rows.
//
// The six that remain are AG-Grid 35's `DEFAULT_TEXT_FILTER_OPTIONS` minus those two,
// written out rather than derived because AG-Grid does not export the default list.
const JOIN_RESOLVED_FILTER_OPTIONS = [
  'contains', 'notContains', 'equals', 'notEqual', 'startsWith', 'endsWith'
];

function joinResolvedFilterDef(entry, baseTooltip) {
  // 🔴 The label is READ OFF THE ENTRY and never written into this file. It rides per
  // declaration (`virtual_join_rules.json`), so a site that renames it must see the new
  // name here on the next /schema — a hardcoded '미상' would be provably wrong there.
  const label = (entry && typeof entry.unresolved_label === 'string' && entry.unresolved_label)
    ? entry.unresolved_label : '';
  // Removing `Blank` without saying what replaced it just moves the dead end. This rides
  // the header tooltip that already exists on both paths rather than adding any control.
  const hint = label ? `\nUnresolved rows: filter Equals '${label}'` : '';
  return {
    ...valueFilterDef('text', JOIN_RESOLVED_FILTER_OPTIONS),
    headerTooltip: `${baseTooltip}${hint}`
  };
}

/** A column's one filter (lead 11-06 ㄱ: one filter door per column, no exception) - Pick · Paste list · Condition, a
 *  `kind` of 'text' or 'number', the Condition's `options` and the floating cell's first type. */
function valueFilterDef(kind, options = null, defaultOption = null) {
  return {
    filter: ValueFilter,
    floatingFilterComponent: ValueFloatingFilter,
    filterParams: { kind, ...(options ? { options } : {}), ...(defaultOption ? { defaultOption } : {}), readValues: readColumnValues },
  };
}

// Helper to build column definitions dynamically based on schema
/**
 * Re-apply the column defs once the reference rule has arrived.
 *
 * `buildColumnDefs` runs while `loadTable` is still fetching the rules, so at that moment
 * `fillTargetOrdinals()` is legitimately empty and no header can carry ①②. This is the
 * second pass. It is a no-op on tables with no rule, because the defs come out identical.
 */
export function applyFillTargetHeaders() {
  if (!state.gridApi) return;
  state.gridApi.setGridOption('columnDefs', buildColumnDefs());
}

/** Read the table's reference rule, then give the headers their ①② -- the ONE pairing of the
 *  two. A table load and a row pick after an unread rule list both come through here.
 *  Fire-and-forget: `.catch` keeps a failed read from becoming an unhandled rejection. */
export function syncReferenceRule() {
  return syncReferenceViewRule().then(applyFillTargetHeaders).catch(() => {});
}

let selectionListener = null;
let formulaOpener = null;

/** What a press on a header's fx mark opens - the page hands it (the popover is the page's part). */
export function registerFormulaOpener(fn) { formulaOpener = fn || null; }

/** 선택이 바뀔 때 불릴 함수 하나. 화면이 자기 부품을 연결합니다. */
export function registerSelectionListener(fn) { selectionListener = fn || null; }

// the item column the last defs held hidden for a pivot's filter - the next defs that do not hold it show it again
let lastHeld = null;
export function buildColumnDefs() {
  // Read ONCE per build, not per column: it is the same Map for every column and the rule
  // must not be able to change halfway down the list.
  const fillTargets = fillTargetOrdinals();
  // the rules that write each column, from the Flow strip's walk (lead 11-08) - only for the table it walked
  const chainWriters = state.flowColumns && state.flowColumns.table === state.currentTable ? state.flowColumns.columns : {};
  // C-84. 표의 «종류»도 한 번만 읽는다 — 컬럼마다 물으면 목록 중간에서 답이 바뀔 수 있다.
  const viewTable = Boolean(writeRefusal());
  // 🔴 은퇴한 기능의 잔해는 «만들지 않습니다» (숨기는 것이 아니라). 그래프 동기화는 서버가
  //    은퇴시켰고(`/graph/mapping-summary` -> 410 Gone), `main.js` 의 GRAPH_SYNC_RETIRED 는
  //    켤 경로가 없는 «리터럴»입니다.
  //
  //    🔴 2026-08-31 정정 -- 이 주석이 «반대로» 말하고 있었습니다. 그때는 서버가 셋을 실어
  //       보냈고, 그래서 「push_columns.js 에서 빼면 게이트가 이것을 파괴 대상으로 센다」가
  //       참이었습니다. 이제 서버가 «안 보냅니다» (main.py 의 system_cols 와 crud.py 의
  //       skip 목록에서 같은 날 빠졌습니다) -- 그래서 push_columns.js 에서도 뺐습니다.
  //       실측: 어느 표도 셋을 `column_types` 에 선언하지 «않으므로»(0) 게이트 입력에
  //       애초에 안 들어가고, 답이 안 바뀝니다.
  //    ⚠️ 아래 필터는 «남겨 둡니다». 새 클라가 옛 서버를 볼 수 있는 배포 중에는 셋이 아직
  //       올 수 있고, 그때 이것이 마지막 방어선입니다. DB 컬럼 44개 표 삭제는 «별도 판정»입니다.
  const retired = ['is_graph_synced', 'needs_graph_rollback', 'graph_synced_at'];
  // the item column a pivot view holds for its filter is hidden, and shown again by the next defs that do not hold it - a
  // grid keeps a column's hide across defs that leave it unsaid (owner 11-05 ㄴ)
  const held = pivotShown() ? state.currentPivot.column : null;
  // pivoted (owner 10-22): the keys, then one column per item
  const shown = pivotShown() ? pivotColumns(state.pivotView, state.currentPivot, state.currentCompositeKeySources)
    : state.currentColumns.filter((col) => !retired.includes(col));
  // a pivot row's carried columns (owner 11-06): read-only, not sorted or filtered - one value or «N values»
  const carried = pivotShown() ? carryColumns(state.pivotView, state.currentPivot) : [];
  const columnDefs = shown.map((col, index) => {
    const isSystem = isSystemColumn(col);
    const isCarried = carried.includes(col);
    // ROW_ID alone among them is filterable (owner 10-02, lead e67ef53f3): finding a row by its id
    // is the question. It stays read-only, and the other system columns stay unfilterable.
    const filterable = (!isSystem || col === 'row_id') && !isCarried;
    const colTypes = state.currentColumnTypes || {};
    const colType = colTypes[col] || 'string';

    // 헤더명에 비즈니스 키 / 조합 소스 컬럼 아이콘 표시
    let headerLabel = headerWord(col);
    if (col === state.currentBusinessKey) {
      headerLabel = `${headerLabel}🗝️`;
    } else if (state.currentCompositeKeySources.includes(col)) {
      headerLabel = `${headerLabel}*`;
    }

    // [2b] The paste order, on the columns the paste lands in. The panel already numbers its
    // own columns ①②; without the same numbers over here the operator has to hold the
    // mapping in their head, which is the thing this screen exists to stop.
    const fillOrdinal = fillTargets.get(col);
    if (fillOrdinal) headerLabel = `${headerLabel} ${fillOrdinal}`;
    // its built index (owner 10-15): a small mark on the header, and an equal index alone makes the filter equals
    const indexed = (state.currentColumnIndexes || {})[col] || [];
    const indexWords = indexed.map((kind) => (kind === 'search' ? 'partial' : kind));
    // its formula, as /schema says it (B 72acf1fd1) - the header draws an fx mark beside the name
    const formula = isSystem ? null : (state.currentFormulas || {})[col] || null;
    // a rule writes it (the walk's answer): a chain mark, or on a formula's column its fx mark says it - the tip says which
    const chainTip = chainTipLines(chainWriters[col]);

    // [Virtual join] A STORED column can still be join-resolved — `kind: 'collide'`, where
    // the same name exists on both sides and the server fills it from the right table
    // wherever the stored value is blank. It is NOT in `currentVirtualColumns` (that list
    // answers "which columns must the grid ADD"), so `isVirtualColumn` says no here and
    // would miss it. Only its FILTER changes; it stays editable, writable and copyable,
    // because the value really is stored.
    const resolvedEntry = joinResolvedColumn(col);

    const colDef = {
      headerName: headerLabel,
      headerTooltip: [indexWords.length ? `${headerLabel} · index: ${indexWords.join(', ')}` : headerLabel, ...chainTip].join('\n'),
      field: col,
      ...(col === held || col === lastHeld ? { hide: col === held } : {}),
      // C-84. 뷰면 «편집 진입 자체»가 없다 — 서버 400 을 셀에서 만나게 두지 않는다.
      // a pivot view's keys name a group, not a row (owner 10-22): its items are written, its keys are typed only on a new
      // row (owner 10-23)
      editable: !isSystem && !viewTable && !isCarried
        && (pivotShown() && itemOf(col) === null ? (params) => isNewPivotRow(params.data && params.data.row_id) : true),
      sortable: !isCarried,
      // A system column is not editable and, except ROW_ID, not filterable either.
      // `filter: false` is what AG-Grid reads to skip the floating row, and
      // `floatingFilter: false` says the same thing where a reader looks for it.
      ...(col === held ? { filter: HeldColumnFilter }
        : filterable ? valueFilterDef(colType === 'number' ? 'number' : 'text', null,
          colType !== 'number' && indexed.includes('equal') && !indexed.includes('search') ? 'equals' : null) : { filter: false }),
      floatingFilter: filterable,
      headerClass: [fillOrdinal ? 'fill-target-header' : '', chainTip.length && !formula ? 'chain-written-header' : '',
        ...indexed.map((kind) => `idx-${kind}`)]
        .filter(Boolean).join(' ') || undefined,
      // its formula (owner 10-28 option A): the name and an fx mark inside the header's own text, the mark opens it
      ...(formula ? { headerComponentParams: { innerHeaderComponent: FormulaHeader, innerHeaderComponentParams: {
        formula, open: (anchor) => { if (formulaOpener) formulaOpener(col, anchor); } } } } : {}),
      resizable: true,
      // C-85. 시각은 보는 쪽 zone 으로 «그리고», 값은 서버가 준 원문 그대로 둔다.
      valueFormatter: isTimeColumn(col, colType) ? timeCellFormatter : undefined,
      // a carried cell whose long rows hold more than one value says how many (owner 11-06)
      ...(isCarried ? { valueFormatter: (params) => carryText(params.data && params.data.data && params.data.data[col])
        || (isTimeColumn(col, colType) ? timeCellFormatter(params) : params.value) } : {}),
      valueGetter: (params) => {
        if (col === 'row_id') return params.data.row_id;
        if (col === 'created_at') return params.data.created_at;
        if (col === 'updated_at') return params.data.updated_at;

        const val = rawCellValue(params.data, col);

        return colType === 'number' ? numericDisplayValue(val) : val;
      },
      valueSetter: (params) => {
        if (isSystem) return false;
        ensureCellObject(params.data, col);

        const finalVal = cellToSend(col, params.newValue);

        params.data.data[col].value = finalVal;
        if (!state.txModeActive) {
          markCellOverwritten(params.data, col);
        }
        return true;
      },
      // A staged cell the server changed since the edit says what it holds now, and since when (lead 10-12).
      tooltipValueGetter: (params) => {
        const edit = params.data ? state.pendingTxEdits[`${params.data.row_id}_${col}`] : null;
        if (!edit || !edit.conflict) return undefined;
        const { server, at } = edit.conflict;
        return `Server: ${isBlank(server) ? ABSENT : server}${at ? ` · ${localStamp(at)}` : ''}`;
      },
      // a picked colour's value for look-colour / look-line-colour (grid_look.lookStyle - both always said)
      cellStyle: (params) => lookStyle(isSystem ? null : cellLookOf(params.data, col)),
      cellClassRules: {
        'cell-system-readonly': () => isSystem,
        // its look (owner 11-06, lead L2): a rule's or a hand's fill, a line rule's edge (owner 11-08 2ㄱ - who wrote it,
        // by the rules every table has), the hand's mark
        ...Object.fromEntries(ROLES.map(([word]) => [`look-${word}`, (params) => !isSystem && cellLookOf(params.data, col)?.role === word])),
        ...Object.fromEntries(ROLES.map(([word]) => [`look-line-${word}`, (params) => !isSystem && cellLookOf(params.data, col)?.line === word])),
        // a colour a person picked (owner 11-09): its value on the cell's own style (cellStyle below)
        'look-colour': (params) => !isSystem && isColour(cellLookOf(params.data, col)?.role),
        'look-line-colour': (params) => !isSystem && isColour(cellLookOf(params.data, col)?.line),
        // a carried cell reads as read-only; one whose long rows hold more than one value says «N values», dim (owner 11-06)
        'pivot-carry': () => isCarried,
        'pivot-carry-many': (params) => isCarried && Boolean(carryText(params.data && params.data.data && params.data.data[col])),
        'cell-dirty-tx': (params) => {
          if (isSystem) return false;
          if (!params.data) return false;
          const key = `${params.data.row_id}_${col}`;
          return state.pendingTxEdits.hasOwnProperty(key);
        },
        // The server changed this cell since the edit was staged: Apply asks before sending it (lead 10-12).
        'cell-tx-conflict': (params) => {
          if (isSystem || !params.data) return false;
          const edit = state.pendingTxEdits[`${params.data.row_id}_${col}`];
          return Boolean(edit && edit.conflict);
        },
        'custom-range-selected': (params) => {
          return isCellInRange(params.node.rowIndex, col);
        }
      }
    };

    // Applied AFTER the literal so it overrides `filter`/`headerTooltip`, and BEFORE the
    // editor selection below so it cannot touch it: a collide column declared `number` keeps
    // the number column's editor. Only the filter becomes text, because only the filter is
    // evaluated against the joined value.
    if (resolvedEntry) {
      Object.assign(colDef, joinResolvedFilterDef(resolvedEntry, headerLabel));
    }

    if (colType === 'number') {
      // a text box, not a number box (owner 10-31 ㄱ): the number box handed 1e999 and letters over as a blank and the
      // cell was erased; typed text goes through cellToSend and the server takes it or folds it, and the toast says so
      colDef.cellEditor = 'agTextCellEditor';
      // and the text as typed: the grid's own number parsing would turn 1e999 into Infinity before cellToSend
      colDef.valueParser = (params) => params.newValue;
    } else if (!isSystem && colType === 'string') {
      // [0b-a] Prefix suggestions, on STRING columns only.
      //
      // Scoping, deliberately narrow: not `number` (no suggestions there, a plain text box above), and not
      // `datetime`, which the endpoint refuses itself (`_resolve_target` raises rather than inventing a datetime
      // canonicalisation). The server DOES support numeric prefixes (`_numeric_values`), so widening later is a
      // change to this predicate and nothing else.
      colDef.cellEditor = SuggestCellEditor;
    }
    // (lead 191912ce2) an image column: its cells preview on a dwell and open from their mark; a link column's
    // value opens in a new tab (owner 11-04).
    Object.assign(colDef, columnTypeParts(colType));

    if (isSystem) {
      colDef.cellClass = 'cell-system-readonly';
    }

    return colDef;
  });

  // ── [Virtual join] The columns a VERIFIED join ADDS to this table's read payload ──────
  //
  // APPENDED, NOT MERGED. These names come from `/schema`'s separate `virtual_columns` key
  // and stay out of `state.currentColumns` (see the note on that field in state.js). They go
  // LAST so the stored columns keep their positions.
  //
  // The payload cell shape is identical to a stored cell — `attach` fills the same keys
  // `fetch_and_merge_metadata` does — so these defs read cells through the same
  // `rawCellValue`/`numericDisplayValue` the stored defs use, not through a second reader.
  //
  // 🔴 `editable: false` IS NOT THE ENFORCEMENT. The server refuses the write
  // (`crud.refuse_virtual_join_columns`); this only stops the grid offering an edit that
  // would come back 400. The paste/clear/bulk-fill funnels do not read `editable` at all,
  // which is why they carry their own `isVirtualColumn` guard.
  (!pivotShown() && Array.isArray(state.currentVirtualColumns) ? state.currentVirtualColumns : []).forEach(vc => {
    // A malformed entry must not become a def: AG-Grid would take `field: undefined` and
    // render a permanently empty column with no way to tell what it is.
    if (!vc || typeof vc.name !== 'string' || vc.name === '') return;
    const col = vc.name;
    // The server already filters its announcement against its own final column list, so this
    // can only fire on a stale/!=-server state. Two defs with the same `field` would give
    // AG-Grid a duplicate colId, and the STORED one must win — it is the editable, writable,
    // copyable one.
    if (state.currentColumns.includes(col)) return;

    const isNumeric = vc.type === 'number';
    const isTime = vc.type === 'datetime';
    const unresolved = typeof vc.unresolved_label === 'string' ? vc.unresolved_label : '';
    const rightTable = vc.right_table || '?';
    const baseTooltip = `${col.toUpperCase()} — join column from '${rightTable}' (read-only)\n`
      + `Edit the value in '${rightTable}'. Rule: ${vc.rule || '?'}`;

    // 🔴 KEYED OFF `join_resolved_columns`, NOT off `vc` — even though `vc` carries an
    // `unresolved_label` too and would have been the convenient read. The announcement is
    // the server saying "I can resolve and filter this name"; `virtual_columns` only says
    // "add this column". A server that announces the second and not the first is a
    // PRE-CHANGE server, and on that server a filter on this name contributes no condition
    // and the page comes back unfiltered — the exact defect `filter: false` existed to
    // prevent. So when the announcement is absent we keep the old, safe behaviour.
    const resolvedEntry = joinResolvedColumn(col);
    // `floatingFilter: false` rides with `filter: false` below for the same reason it does on
    // a system column: the two keys must move together or the grid draws a box that cannot
    // narrow anything. On this branch the box would be empty of capability, not merely
    // disabled.
    //
    // 🔴 THE COMMENT SITS ABOVE THE TERNARY, NOT INSIDE IT. `virtual_column_render_harness`
    // mutation-tests this file by quoting these three lines verbatim; a comment between the
    // `?` and the `:` splits the quote and the mutant silently stops applying, which is a
    // green harness that compares nothing. Prose goes where it cannot break the anchor.
    const filterDef = resolvedEntry
      ? joinResolvedFilterDef(resolvedEntry, baseTooltip)
      : { filter: false, floatingFilter: false, headerTooltip: baseTooltip };

    columnDefs.push({
      // 🔗 joins the existing header vocabulary (🗝️ business key, * composite source) rather
      // than adding a second explanation mechanism. The tooltip is where `right_table` and
      // `rule` land: the server's write refusal says "fix it in the join source" without
      // naming which table, and this is the only place that answer exists on screen.
      headerName: `${col.toUpperCase()}🔗`,
      field: col,
      editable: false,
      sortable: true,
      // ✅ FILTERABLE. This column carried `filter: false` until 2026-07-31, on the grounds
      // that `main.get_column_filter_condition` ended its resolution with
      // `if not hasattr(table_model, col_name): return None` — an unknown name contributed
      // no condition, the page came back UNFILTERED, and only the client-side row model
      // trimmed what was on screen, so the rows looked filtered while `Matches:` and the
      // page count stayed at the unfiltered totals.
      //
      // 🔴 THAT JUSTIFICATION IS GONE, not weakened. The server now resolves these columns
      // itself: `apply_column_filters` binds the column to `resolved_expression` and passes
      // it as `col_expr_override`, and a column it knows is virtual but cannot build an
      // expression for is now a 400 rather than a silent unfiltered 200. So `?filters=` on
      // this name genuinely narrows the query, and `Matches:` is the count of the narrowed
      // query. Leaving `filter: false` here would have kept a working server capability
      // unreachable from the UI, which is its own kind of lie.
      //
      // The client-side row model still re-filters the page it holds, and that stays
      // correct: `valueGetter` reads the cell the SERVER attached — already COALESCEd,
      // label included — so both sides evaluate the same displayed value and the second
      // pass is idempotent.
      //
      // `headerTooltip` rides in here too: it is where the `equals <label>` hint lands, and
      // composing it in one place keeps the hint from drifting from the option list it
      // exists to explain.
      ...filterDef,
      resizable: true,
      // C-85 ④. 읽기 전용 컬럼도 «같은 함수»다 — 두 자리가 갈라지면 같은 순간이 두 글자다.
      valueFormatter: isTime ? timeCellFormatter : undefined,
      valueGetter: (params) => {
        const val = rawCellValue(params.data, col);
        return isNumeric ? numericDisplayValue(val) : val;
      },
      // Sorting a `number` virtual column, where some rows carry the label.
      //
      // AG-Grid's default comparator ends in `a > b ? 1 : a < b ? -1 : 0`, and BOTH
      // comparisons are false for (number, '미상') — JS coerces the string to NaN. So every
      // unresolved row compares EQUAL to every number and the sort silently scatters them
      // through the result. This keeps them in one block instead, always at the bottom of an
      // ascending sort (AG-Grid inverts the result for descending, so they lead there).
      // Only installed for `number`: on a `string` column the label is just another string
      // and the default comparator is already right.
      ...(isNumeric ? {
        comparator: (a, b) => {
          const au = (a === unresolved), bu = (b === unresolved);
          if (au || bu) return (au && bu) ? 0 : (au ? 1 : -1);
          if (a === b) return 0;
          return (a < b) ? -1 : ((a > b) ? 1 : 0);
        }
      } : {}),
      // Same grey a system column gets. Reusing the existing class rather than inventing a
      // "virtual" one: to the operator the fact is identical — this cell cannot be typed in.
      cellClass: 'cell-system-readonly',
      ...columnTypeParts(vc.type),
      cellClassRules: {
        // The other stored-column rules are deliberately absent, not forgotten:
        // `cell-dirty-tx` keys on `pendingTxEdits`, which a column that cannot be edited
        // never enters; the looks judge a stored cell (`lookTarget`), and `attach` stamps
        // 'virtual_join', which no writer word names. Range highlighting is the one that still
        // means something — these cells ARE selectable and copyable.
        'custom-range-selected': (params) => isCellInRange(params.node.rowIndex, col)
      }
    });
  });

  // 소유자 「맨 끝」(cdf11b222). 답은 라벨의 것이고, 이 표의 답이 아니면 열을 안 세웁니다.
  const ledger = pivotShown() ? null : ledgerColumnDef(state.ledgerAnswer, state.currentTable);
  if (ledger) {
    // 범위 선택은 다른 열과 «같은 규칙»입니다 — 안 달면 끌어 잡은 직사각형에 이 열만 구멍이 납니다.
    ledger.cellClassRules = { 'custom-range-selected': (params) => isCellInRange(params.node.rowIndex, ledger.colId) };
    columnDefs.push(ledger);
  }

  columnDefs.unshift({
    // Its id is said: without one AG-Grid numbers it ('1' - measured 10-22), and every `'#'` test missed it.
    colId: '#',
    headerName: '#',
    headerTooltip: 'Row Number',
    valueGetter: (params) => {
      if (isNewPivotRow(params.data && params.data.row_id)) return 'not saved';
      const skip = (state.viewMode === 'pagination' && !state.allDataLoaded) ? state.currentSkip : 0;
      return skip + params.node.rowIndex + 1;
    },
    initialWidth: 100,
    // no floor of its own (the grid's default is 100): the fit sizes it to its numbers, and nobody drags it (resizable false)
    minWidth: 0,
    maxWidth: 150,
    pinned: 'left',
    suppressMovable: true,
    sortable: false,
    filter: false,
    resizable: false,
    editable: false,
    // a table read in its entered order: its rows (in pivot view its groups) dragged by this cell (owner 11-06) - on no
    // other table: a handle AG Grid hides still takes its room, and the number beside it was drawn as a dot (box, 11-07)
    ...(state.currentOrder === ENTERED ? { rowDrag: (params) => placing() && Boolean(params.data && params.data.order_key) } : {}),
    cellClass: 'cell-system-readonly'
  });

  lastHeld = held;
  return applyMockupLayout(columnDefs);
}

// ── Mockup 2b column layout (order + widths) ─────────────────────────────────────────────
//
// The order's measurement table fixes these to the pixel, so they are a contract rather than
// a preference: `dt_cell_key 176 · dt_job 210 · dt_eqp 70 · dt_index 58 · product 100 ·
// dt_lot 112 · dt_slot 58 · dt_x 44 · dt_y 44 · core_wafer 150`, with `c_bn`, `event_time`
// and `core_product` pushed past the right edge at a 640px sidebar.
//
// 🔴 APPLIED BY NAME, NEVER BY POSITION, AND ONLY TO NAMES THAT APPEAR. `/schema` decides
// which columns a table has; this decides how the ones it names are laid out. A table that
// shares none of these names is untouched and keeps the default width — which is what makes
// this a layout declaration rather than a hardcoded screen. The widths are the mockup's
// measurements; the COLUMNS are still the server's.
//
// The two fill targets are in here at their mockup widths (`dt_lot 112`, `dt_slot 58`) on
// purpose: they are the columns a reference-grid paste lands in, so their width is part of
// the same contract as the ①② marking in the panel.
const MOCKUP_COLUMN_LAYOUT = Object.freeze({
  dt_cell_key: 176, dt_job: 210, dt_eqp: 70, dt_index: 58, product: 100,
  dt_lot: 112, dt_slot: 58, dt_x: 44, dt_y: 44, core_wafer: 150,
  c_bn: 90, event_time: 150, core_product: 110
});

// The header chrome a column spends before any text: cell padding plus the sort/menu icons.
// Measured off the live grid rather than assumed -- `dt_slot` at 58px and `dt_eqp` at 70px
// both reported exactly 32px less usable text width than their column width.
const HEADER_CHROME_PX = 32;
/** The sort arrow and the filter mark a header shows beside its name, 24 px each with their gap (measured 11-05 on a
 *  sorted column): without their room a sorted or filtered name was cut. A column that neither sorts nor filters has none. */
const HEADER_ICON_PX = 24;
/** A formula column's fx mark beside its name: the mark (two glyphs at --fs-tag, --space-1 each side) and its gap. */
const FORMULA_MARK_PX = 28;

/**
 * How wide the header label needs the column to be, so it is not truncated.
 *
 * 🔴 THE MOCKUP'S WIDTHS ARE MINIMUMS, NOT FINAL VALUES. The mockup measured them against
 * ITS OWN labels (`Slot`), and the owner ruled the labels come from the live schema
 * (`DT_SLOT`). Both cannot hold at once, and the standing rule decides which yields:
 * 「작은 글씨는 없느니만 못하다 · 가독성이 기능」 — a truncated column name is not a narrow
 * column, it is an absent one. So width gives way to the name.
 *
 * ONE RULE FOR THE WHOLE CLASS, not a special case for the column that happened to be
 * noticed: `DT_EQP` was truncated too, and it carries no ordinal.
 *
 * `measureText` cannot see `letter-spacing`, so it is added back per character.
 */
function headerLabelWidth(label) {
  if (!label) return 0;
  const css = getComputedStyle(document.body);
  const family = css.getPropertyValue('--font-body').trim() || 'sans-serif';
  // Matches `#myGrid .ag-header-cell-text` in style.css (its size the token, not a copy: 10.5 here against the drawn 11
  // cut «CORE_WAFER…», 11-05). Uppercase because the header is transformed there, and the transform changes the width.
  return textWidth(String(label).toUpperCase(), `600 ${css.getPropertyValue('--fs-tag').trim() || '11px'} ${family}`, 0.4);
}

/** A text's px in a font; `spacing` adds back the letter-spacing `measureText` cannot see. */
function textWidth(text, font, spacing = 0) {
  const canvas = textWidth.canvas || (textWidth.canvas = document.createElement('canvas'));
  const context = canvas.getContext('2d');
  if (!context) return 0;
  context.font = font;
  return Math.ceil(context.measureText(text).width + text.length * spacing);
}

/** The width a column's header needs whole: its name, the header's icons and a formula column's fx mark. */
const headerNeed = (def) => headerLabelWidth(def.headerName) + HEADER_CHROME_PX
  + HEADER_ICON_PX * ((def.sortable === false ? 0 : 1) + (def.filter === false ? 0 : 1))
  + (def.headerComponentParams ? FORMULA_MARK_PX : 0);

/** A column's fitted width (owner 11-05): its widest value plus the cell's padding, up to `cap`; never narrower than its
 *  header's need - the name is never cut, the cap is for long values. `measure` gives a text's px. */
export function columnFitWidth(header, texts, measure, pad, cap) {
  let widest = 0;
  for (const text of texts) if (text != null && text !== '') widest = Math.max(widest, measure(String(text)) + pad);
  return Math.ceil(Math.max(header, Math.min(cap, widest)));
}

// renderGrid drew new columns (a table opened, the pivot turned) and the first rows drawn after it set their widths, once:
// a re-read, a page, a window or side panel resize keep them, and so does a width the operator dragged (owner 11-05).
let widthsOwed = false;

/** The stored cell a grid cell is - {rowId, column, cell} - or null: in pivot view an item's cell is its long row's
 *  value cell; a pivot's keys and carried cells are no one row's. */
export function lookTarget(rowData, col) {
  if (!rowData) return null;
  const cell = rowData.data && rowData.data[col];
  if (!pivotShown()) return { rowId: rowData.row_id, column: col, cell };
  return itemOf(col) !== null && cell && cell.row_id && state.pivotView
    ? { rowId: cell.row_id, column: state.pivotView.value, cell } : null;
}

const cellLookOf = (rowData, col) => {
  const at = lookTarget(rowData, col);
  return at && lookOf(state.looks, at.rowId, at.column, at.cell);
};

/** The columns' widths from the rows drawn, when renderGrid owes them - asked by the grid's own row events only. */
export function fitColumnWidths() {
  const api = state.gridApi;
  if (!widthsOwed || !api || !api.getDisplayedRowCount()) return;
  const cell = document.querySelector('#myGrid .ag-cell');
  if (!cell) return;
  markWork('fit widths', state.currentTable, api.getDisplayedRowCount());
  widthsOwed = false;
  const cs = getComputedStyle(cell);
  const pad = ['paddingLeft', 'paddingRight', 'borderLeftWidth', 'borderRightWidth'].reduce((sum, k) => sum + (parseFloat(cs[k]) || 0), 0);
  // the drag handle beside the row number, as drawn (hidden or not, it takes its room)
  const handle = document.querySelector('#myGrid .ag-row-drag');
  const drag = handle ? handle.getBoundingClientRect().width + (parseFloat(getComputedStyle(handle).marginRight) || 0) : 0;
  const font = `${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
  const cap = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--grid-column-max')) || Infinity;
  const nodes = [];
  api.forEachNodeAfterFilterAndSort((node) => nodes.push(node));
  // within each column's least and most: AG Grid resizes all or none, so one width under its least moved nothing (measured)
  const texts = (col) => {
    const seen = new Set(nodes.map((rowNode) => api.getCellValue({ rowNode, colKey: col, useFormatter: true })));
    if (col.getColId() !== '#') return seen;
    // the row number (owner 11-06: «#» as wide as its numbers) - one digit past the widest, so the pages after this one fit
    const digits = Math.max(0, ...[...seen].filter((n) => n != null && n !== '').map((n) => String(n).length));
    return new Set([...seen, '0'.repeat(digits + 1)]);
  };
  api.setColumnWidths(api.getColumns().filter((col) => isDataColumn(col.getColId()) || col.getColId() === '#').map((col) => ({
    key: col.getColId(),
    newWidth: Math.min(col.getMaxWidth() || Infinity, Math.max(col.getMinWidth() || 0, columnFitWidth(headerNeed(col.getColDef()),
      texts(col), (text) => textWidth(text, font), pad + (col.getColDef().rowDrag ? drag : 0), cap))),
  })));
}

function applyMockupLayout(columnDefs) {
  columnDefs.forEach(def => {
    const mockupWidth = MOCKUP_COLUMN_LAYOUT[def.field];
    if (!mockupWidth) return;
    const width = Math.max(mockupWidth, headerNeed(def));
    def.initialWidth = width; def.minWidth = Math.min(width, def.minWidth ?? width);
  });
  // △소유자: 「그리드 컬럼 순서 table config 의 display col 순서 그대로」.
  //
  // 🔴 NO REORDERING HERE ANY MORE. `/schema` already answers in the table config's declared
  // order (measured on `dt_log`: dt_event_id · dt_job_id · event_time · dt_index · dt_lot …),
  // so the mockup's sequence was a SECOND opinion about column order laid on top of the one
  // the operator maintains. Two places deciding one thing is how they drift; the config wins
  // because it is the one an operator can change without touching this file.
  //
  // The widths above stay: those are keyed BY NAME and apply wherever the column happens to
  // sit, so they are a statement about a column, not about the sequence.
  return columnDefs;
}

// Render grid layout using AG-Grid Core
// The chip strip folded again whenever the header leaves it another width - the grid's own size events do not fire while
// the gallery holds its place (lead 3589216b9). The bar's width is the header's leftover (flex-basis 0), not its chips'.
let chipBarWatch = null;

export function renderGrid(initialRows) {
  markWork('columns', state.currentTable, Array.isArray(initialRows) ? initialRows.length : null);
  const columnDefs = buildColumnDefs();
  widthsOwed = true;
  const bar = elements.gridFilterBar;
  if (!chipBarWatch && bar && typeof ResizeObserver === 'function') {
    chipBarWatch = new ResizeObserver(() => foldFilterChips());
    chipBarWatch.observe(bar);
  }

  if (state.gridApi) {
    console.log('[Grid] Swapping grid options dynamically (columnDefs & rowData)...');
    state.gridApi.setGridOption('columnDefs', columnDefs);
    state.gridApi.setGridOption('rowData', initialRows);

    state.colIdToIndexMap = {};
    state.gridApi.getColumns().forEach((c, idx) => {
      state.colIdToIndexMap[c.getColId()] = idx;
    });

    updateVisibleColIndexMap();
    updateGridSortState();
    // A table swap replaces the column set, so both halves of the strip are stale: the
    // chips belong to a filter model that no longer applies and the off-screen count was
    // measured against the previous table's widths.
    renderFilterBar();
    return;
  }

  const gridDiv = document.querySelector('#myGrid');
  // (lead 191912ce2) the grid's one image preview, in its own div; image cells reach it through `context`.
  const previewMount = document.createElement('div');
  previewMount.className = 'image-preview-mount';
  document.body.appendChild(previewMount);
  const imagePreview = new ImagePreview(previewMount, { doc: document, base: API_BASE });

  const gridOptions = {
    theme: 'legacy',
    context: { imagePreview },
    columnDefs: columnDefs,
    rowData: initialRows,
    enableBrowserTooltips: false,
    suppressColumnVirtualization: false,
    suppressRowHoverHighlight: true,
    suppressSortOnDataChange: true,
    getRowId: (params) => params.data?.row_id || params.data?.id,
    // ── Mockup 2b metrics (the order's measurement table is canonical) ──────────────────
    // 30 / 28 / 28 instead of the quartz theme's defaults (~48 header, ~41 row). This is the
    // difference between a screen that shows 24 rows and one that shows 16, which on a
    // correction surface is the difference between seeing the pattern and scrolling for it.
    headerHeight: 30,
    floatingFiltersHeight: 28,
    rowHeight: 28,
    defaultColDef: {
      // initial, not width: a width in the defs is laid again on every defs refresh (the reference rule's header pass) and
      // undid the fitted widths (owner 11-05, measured on the box); an initial width is only a new column's
      initialWidth: 150,
      minWidth: 100,
      floatingFilter: true,
      // 🔴 NO `suppressFilterButton` HERE, DELIBERATELY. The 2b order asked for it and the
      // line was removed after measuring what it would cost: the funnel is the ONLY route to
      // the operator list, and `joinResolvedFilterDef` writes a header tooltip that tells the
      // operator to "필터를 Equals 로 두고" — suppressing it deletes the path the screen's own
      // instruction depends on. (It was also inert as written: AG-Grid 35 reads
      // `colDef.suppressFloatingFilterButton`, not this key, so the line did nothing and the
      // next reader would have spent a day on "why doesn't this work".)
      suppressKeyboardEvent,
    },
    // The checkboxes in the grid's own column, pinned left - not on a data column, which the column selector can hide
    // (owner 10-22 「전체 선택하는 체크버튼 ... 다 나오게」). A click still selects its row, as 'multiple' did.
    rowSelection: { mode: 'multiRow', checkboxes: true, headerCheckbox: true, enableClickSelection: true },
    selectionColumnDef: { pinned: 'left', lockPinned: true, suppressMovable: true, resizable: false, sortable: false },
    // 선택이 바뀌었다는 «신호»만 냅니다. 누가 듣는지는 화면이 정합니다 --
    // 이 파일이 배너를 알면 그리드가 헤더를 아는 것이 됩니다.
    onSelectionChanged: () => { if (selectionListener) selectionListener(); },
    onGridReady: (event) => {
      state.gridApi = event.api;
      updateVisibleColIndexMap();
    },
    onColumnMoved: (event) => {
      updateVisibleColIndexMap();
      dropItem(event);
    },
    onRowDragEnd: (event) => dropRow(event),
    onColumnVisible: () => {
      updateVisibleColIndexMap();
      renderFilterBar();
    },
    onColumnPinned: () => {
      updateVisibleColIndexMap();
    },
    onColumnEverythingChanged: () => {
      updateVisibleColIndexMap();
    },
    onFilterChanged: () => gridFilterChanged(),
    // A-6. A HEADER SORT IS A QUESTION ABOUT THE TABLE, NOT ABOUT THE PAGE.
    //
    // 🔴 Until this existed, clicking a header re-ordered the rows the grid happened to hold
    //    and drew the ordinary sort arrow over the result. Measured on a 34,939-row table:
    //    DT_LOT descending put SYN-DT-103 on top, the table's real maximum SYN-DT-CORE sat on
    //    page 22 of 35, and two clicks fired ZERO requests. The operator asked for the largest
    //    value and was shown the largest value on page one, with nothing to tell them apart.
    onSortChanged: (event) => {
      // The grid re-applying its own state after a fetch is not the operator sorting.
      if (applyingSortState) return;
      if (event && event.source && event.source !== 'uiColumnSorted') return;
      // 🔴 WHEN EVERYTHING IS LOADED THE LOCAL SORT IS ALREADY THE WHOLE-TABLE SORT, and
      //    asking the server would be a round trip that changes nothing. Measured: a 907-row
      //    table (under one page) sorts to its true maximum today, with zero requests.
      if (holdsWholeTable()) { state.serverSort = null; return; }
      const sorted = state.gridApi.getColumnState().find(c => c.sort);
      // The column id IS the declared column name (`field: col` for both plain and 🔗 join
      // columns), so the name on the wire is one the table declares — the server's 422 for an
      // unknown name is unreachable from this control, not merely unlikely.
      const next = sorted ? { colId: sorted.colId, desc: sorted.sort === 'desc' } : null;
      const before = state.serverSort;
      if ((before && before.colId) === (next && next.colId)
          && (before && before.desc) === (next && next.desc)) return;
      state.serverSort = next;
      // The cached pages were built under the OLD order; keeping them would page the operator
      // back into it.
      state.pageCache.clear();
      fetchData(true);
    },
    // The `+N열 →` count is a fact about the VIEWPORT, so it is re-measured by everything
    // that can move the viewport's right edge: the first paint, a sidebar drag, a column
    // resize, and horizontal scrolling.
    onFirstDataRendered: () => {
      // the grid's very first rows land before its first cells are drawn - the fit they owe is paid here
      fitColumnWidths();
      renderFilterBar();
    },
    // every later row set (a read, a page, a table opened): the fit renderGrid owes is paid here, once (lead 11-08 ㄱ)
    // A row of the same id takes its new data as an update: AG Grid reruns a cell's class rules, but its cellStyle (a
    // picked colour, grid_look.lookStyle) only when its value changed - a look changed on a cell that did not (a rule's
    // colour, a colour back to a role) kept the colour drawn before (measured 11-09). A forced refresh draws it again -
    // only while a picked colour is asked or still drawn (a table without one reads as before, lead 11-09).
    onRowDataUpdated: (e) => {
      fitColumnWidths();
      if (hasPickedColour(state.looks) || gridDiv.querySelector('.ag-cell[style*="--look-"]')) e.api.refreshCells({ force: true, suppressFlash: true });
    },
    onGridSizeChanged: () => {
      // The strip's right edge moved, so how many chips fit moved with it.
      foldFilterChips();
      updateOffscreenIndicator();
    },
    onColumnResized: () => {
      updateOffscreenIndicator();
    },
    onCellFocused: (event) => {
      if (!event.column || event.rowIndex === null || event.rowIndex === undefined) return;
      const rowNode = event.api.getDisplayedRowAtIndex(event.rowIndex);
      if (!rowNode || !rowNode.data) return;

      const debugColId = event.column.getId();
      const debugRowId = rowNode.data.row_id;
      if (!['row_id', 'created_at', 'updated_at'].includes(debugColId) && isDataColumn(debugColId)) {
        const cellObj = rowNode.data.data?.[debugColId];
        console.log(`%c[Grid Debug] Clicked Cell Info`, 'color: #00f0ff; font-weight: bold;');
        console.log(`- Row ID: ${debugRowId}`);
        console.log(`- Col ID: ${debugColId}`);
        console.log(`- Priority Source:`, cellObj?.priority_source);
        console.log(`- Is Overwrite:`, cellObj?.is_overwrite);
        console.log(`- Raw Value:`, cellObj?.value);
        console.log(`- Sources:`, cellObj?.sources);
        console.log(`- Full Cell Object:`, cellObj);
      }

      const colId = event.column.getId();
      const rowId = rowNode.data.row_id;

      let val = '';
      if (colId === 'row_id') val = rowNode.data.row_id;
      else if (colId === 'created_at') val = rowNode.data.created_at;
      else if (colId === 'updated_at') val = rowNode.data.updated_at;
      else {
        const cell = rowNode.data.data?.[colId];
        val = cell && typeof cell === 'object' ? (cell.value !== undefined ? cell.value : '') : (cell !== undefined ? cell : '');
      }

      state.selectedCell = { rowId, colId, value: val, rowIndex: event.rowIndex };
      updateSelectedCellUI();
      refreshReferenceForSelection(syncReferenceRule);
      if (state.activeHistoryTab !== 'global') {
        loadHistory();
      }
    },
    onCellMouseDown: (event) => {
      if (event.event.button !== 0) return;
      if (!isDataColumn(event.column.getColId())) return;

      const isShift = event.event.shiftKey;
      const isCtrl = event.event.ctrlKey || event.event.metaKey;
      const currRow = event.rowIndex;
      const currCol = event.column.getColId();

      const oldEnd = state.dragEndCell;

      if (isShift) {
        if (state.dragStartCell) {
          state.dragEndCell = { rowIndex: currRow, colId: currCol };
        } else {
          state.dragStartCell = { rowIndex: currRow, colId: currCol };
          state.dragEndCell = { rowIndex: currRow, colId: currCol };
        }
        state.isDraggingRange = false;
        refreshSelectedRangeDiff(event.api, state.dragStartCell, oldEnd, state.dragEndCell);
      } else {
        // a Ctrl press adds to the selection so far: a plain rectangle (one clicked cell too) joins the ctrl-clicked ones
        if (isCtrl) commitDragSelection(event.api);
        else clearRangeSelection();

        state.isDraggingRange = true;
        state.rangeAdding = isCtrl;
        state.dragStartCell = { rowIndex: currRow, colId: currCol };
        state.dragEndCell = { rowIndex: currRow, colId: currCol };

        refreshRange(event.api, state.dragStartCell, state.dragEndCell);
      }
    },
    onCellMouseOver: (event) => {
      if (event.event && event.event.buttons !== undefined && event.event.buttons !== 1) {
        endRangeGesture(event.api);   // the button let go outside the window
        return;
      }

      if (!state.isDraggingRange || !state.dragStartCell) return;
      if (!isDataColumn(event.column.getColId())) return;

      const currRow = event.rowIndex;
      const currCol = event.column.getColId();

      if (state.dragEndCell.rowIndex !== currRow || state.dragEndCell.colId !== currCol) {
        const prevEnd = state.dragEndCell;
        state.dragEndCell = { rowIndex: currRow, colId: currCol };

        if (!state.dragRefreshPending) {
          state.dragRefreshPending = true;
          const api = event.api;
          requestAnimationFrame(() => {
            try {
              refreshSelectedRangeDiff(api, state.dragStartCell, prevEnd, state.dragEndCell);
            } catch (err) {
              api.refreshCells({ force: true });
            } finally {
              state.dragRefreshPending = false;
            }
          });
        }
      }
    },
    onCellValueChanged: async (event) => {
      await handleCellEdit(event);
    },
    onCellContextMenu: (event) => {
      event.event.preventDefault();
      if (!event.node || !event.node.data) return;

      const colId = event.column.getId();
      const rowId = event.node.data.row_id;
      const val = event.value;
      const rowIndex = event.node.rowIndex;

      if (state.dragStartCell && state.dragEndCell && !isCellInRange(rowIndex, colId)) {
        clearRangeSelection();
      }

      state.selectedCell = { rowId, colId, value: val, rowIndex };
      updateSelectedCellUI();

      if (!state.dragStartCell || !state.dragEndCell) {
        event.node.setSelected(true, true);
      }

      const contextMenu = elements.contextMenu;
      if (contextMenu) {
        contextMenu.style.left = `${event.event.clientX}px`;
        contextMenu.style.top = `${event.event.clientY}px`;
        contextMenu.style.display = 'block';
      }
    },
    onBodyScroll: (event) => {
      // A box fixed beside a cell would float off it once the cell moves.
      imagePreview.leave();
      // Ahead of the infinite-scroll early return on purpose: a HORIZONTAL scroll changes
      // how many columns are off the right edge in every view mode, and returning first
      // would leave the count frozen at whatever it was on load in `pagination` mode.
      updateOffscreenIndicator();

      if (state.viewMode !== 'infinite') return;
      if (state.isLoadingMore || !state.hasMoreData || state.allDataLoaded) return;

      const viewport = document.querySelector('.ag-body-viewport');
      if (viewport) {
        const threshold = 150;
        const nearBottom = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight < threshold;
        if (nearBottom) appendNextRows();
      }
    }
  };

  state.gridApi = createGrid(gridDiv, gridOptions);

  const originalApplyTx = state.gridApi.applyTransaction.bind(state.gridApi);
  state.gridApi.applyTransaction = (tx) => {
    console.log('[Debug applyTransaction] Called with tx:', tx);
    console.trace('[Debug applyTransaction] Call stack trace:');
    return originalApplyTx(tx);
  };

  state.colIdToIndexMap = {};
  state.gridApi.getColumns().forEach((c, idx) => {
    state.colIdToIndexMap[c.getColId()] = idx;
  });

  updateGridSortState();
}
