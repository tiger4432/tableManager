import { createGrid } from 'ag-grid-community';
import { pageLimit } from './config.js';
import { state, updateVisibleColIndexMap, joinResolvedColumn, visibleRangeColIds } from './state.js';
import { elements } from './dom.js';
// 🔴 닫는 방법은 Re-translate 드롭다운과 «같은 한 벌»입니다. 둘째가 나왔을 때 두 번째를
//    그리지 않는 것이 이 저장소의 상설입니다.
import { watchForDismiss } from './dropdown.js';
import { handleCellEdit, fetchData } from './api.js';
import { loadHistory } from './timeline.js';
import {
  isCellInRange,
  refreshRange,
  refreshSelectedRangeDiff,
  commitDragSelection,
  clearRangeSelection
} from './clipboard.js';
import { applyValueToSelectedRange, updateSelectedCellUI } from './ui.js';
import { SuggestCellEditor, handleEditorKey, isSuggestEditorActive } from './value_suggest.js';
import { refreshReferenceForSelection, fillTargetOrdinals } from './enrichment_reference_view.js';

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
    if (colId === '#') return false;
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

// Apply AG-Grid client-side sorting configuration based on Sort Latest toggle
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

  const sortLatest = elements.sortLatestToggle.checked;
  state.gridApi.applyColumnState({
    state: [
      { colId: 'updated_at', sort: sortLatest ? 'desc' : null },
      { colId: 'row_id', sort: sortLatest ? null : 'asc' }
    ],
    defaultState: { sort: null }
  });
}

// Update Loaded count slice text
export function updateLoadedCount(forcedCount = null) {
  if (!state.gridApi) return;
  const displayedCount = state.gridApi.getDisplayedRowCount();

  if (state.viewMode === 'infinite') {
    elements.exposedRowsCount.textContent = `Loaded: 1 - ${displayedCount}`;
  } else {
    const forced = forcedCount !== null ? forcedCount : displayedCount;
    const startRow = forced === 0 ? 0 : state.currentSkip + 1;
    const endRow = state.currentSkip + forced;

    if (startRow === endRow) {
      if (startRow === 0) {
        elements.exposedRowsCount.textContent = `Loaded: 0`;
      } else {
        elements.exposedRowsCount.textContent = `Loaded: ${startRow}`;
      }
    } else {
      elements.exposedRowsCount.textContent = `Loaded: ${startRow} - ${endRow}`;
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
export function updatePaginationUI(total) {
  const currentPage = Math.floor(state.currentSkip / pageLimit) + 1;
  const totalPages = Math.ceil(total / pageLimit) || 1;

  if (elements.pageInput) {
    elements.pageInput.value = currentPage;
    elements.pageInput.max = totalPages;
  }
  if (elements.totalPagesSpan) {
    elements.totalPagesSpan.textContent = totalPages;
  }
  if (elements.prevPageBtn) {
    elements.prevPageBtn.disabled = (currentPage === 1);
  }
  if (elements.nextPageBtn) {
    elements.nextPageBtn.disabled = (currentPage >= totalPages);
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
  const body = conditions.map(clause).join(` ${model?.operator || 'AND'} `);
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
  if (badge) {
    // Saying it is the whole point. A column that scrolled out of view with nothing on
    // screen to say so reads as a column that is GONE, and the next question is asked of
    // the table config rather than of the scrollbar.
    badge.textContent = count > 0 ? `+${count}열 →` : '';
    badge.title = count > 0 ? '가로 스크롤로 갈 수 있습니다' : '';
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
      const remove = document.createElement('button');
      remove.type = 'button';
      // Phase 0: the banner's own close button, not a private one that looks like it.
      remove.className = 'clear-banner-btn';
      remove.textContent = '✕';
      remove.title = `${colId.toUpperCase()} 필터 해제`;
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
    // 🔴 스트립의 자기 div «안»입니다 (조립식). 그런데 그 안에 position 을 가진 조상을 두면
    //    스트립의 `overflow: hidden` 이 판을 잘라 내고, 잘린 판은 «보이지도 눌리지도» 않습니다.
    //    그래서 자리는 헤더 좌표로 «JS 가» 씁니다.
    chipsPanel.className = 'dropdown-panel filter-chips-panel';
    bar.appendChild(chipsPanel);
  }
  chipsPanel.replaceChildren(...all);
  const anchor = more.getBoundingClientRect();
  const origin = (chipsPanel.offsetParent || document.body).getBoundingClientRect();
  chipsPanel.style.top = `${Math.round(anchor.bottom - origin.top + 6)}px`;
  // 오른쪽 끝을 버튼에 맞춥니다. 왼쪽에 맞추면 좁은 창에서 판이 화면 밖으로 나갑니다.
  const width = chipsPanel.getBoundingClientRect().width;
  const wanted = anchor.right - origin.left - width;
  const rightmost = (document.documentElement.clientWidth || 0) - origin.left - width - 8;
  chipsPanel.style.left = `${Math.round(Math.max(8, Math.min(wanted, rightmost)))}px`;
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
    more.textContent = '접기';
    more.title = '한 줄로 접기';
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
  more.textContent = `+${hidden.length} 필터`;
  more.title = '눌러서 펼치기';
  more.style.display = hidden.length ? '' : 'none';
}

// Ensure that the cell data structure exists as an object: { value, is_overwrite, sources, updated_by }
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
  const hint = label ? `\n미해결 행 보기: 필터를 Equals로 두고 '${label}' 입력` : '';
  return {
    filter: 'agTextColumnFilter',
    filterParams: { filterOptions: JOIN_RESOLVED_FILTER_OPTIONS },
    headerTooltip: `${baseTooltip}${hint}`
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

let selectionListener = null;

/** 선택이 바뀔 때 불릴 함수 하나. 화면이 자기 부품을 연결합니다. */
export function registerSelectionListener(fn) { selectionListener = fn || null; }

export function buildColumnDefs() {
  // Read ONCE per build, not per column: it is the same Map for every column and the rule
  // must not be able to change halfway down the list.
  const fillTargets = fillTargetOrdinals();
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
  const shown = state.currentColumns.filter((col) => !retired.includes(col));
  const columnDefs = shown.map((col, index) => {
    const isSystem = ['created_at', 'updated_at', 'row_id', 'id', 'updated_by'].includes(col);
    const colTypes = state.currentColumnTypes || {};
    const colType = colTypes[col] || 'string';

    // 헤더명에 비즈니스 키 / 조합 소스 컬럼 아이콘 표시
    let headerLabel = col.toUpperCase();
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

    // [Virtual join] A STORED column can still be join-resolved — `kind: 'collide'`, where
    // the same name exists on both sides and the server fills it from the right table
    // wherever the stored value is blank. It is NOT in `currentVirtualColumns` (that list
    // answers "which columns must the grid ADD"), so `isVirtualColumn` says no here and
    // would miss it. Only its FILTER changes; it stays editable, writable and copyable,
    // because the value really is stored.
    const resolvedEntry = joinResolvedColumn(col);

    const colDef = {
      headerName: headerLabel,
      headerTooltip: headerLabel,
      field: col,
      editable: !isSystem,
      sortable: true,
      // A system column is not editable and is not filterable either. Until now only the
      // first half was said, and `defaultColDef.floatingFilter` then put a filter box under
      // `ROW_ID`/`CREATED_AT` — a second vocabulary in which read-only still means
      // queryable. `filter: false` is what AG-Grid reads to skip the floating row, and
      // `floatingFilter: false` says the same thing where a reader looks for it.
      filter: isSystem ? false : (colType === 'number' ? 'agNumberColumnFilter' : 'agTextColumnFilter'),
      floatingFilter: !isSystem,
      headerClass: fillOrdinal ? 'fill-target-header' : undefined,
      resizable: true,
      checkboxSelection: index === 0,
      headerCheckboxSelection: index === 0,
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

        let finalVal = params.newValue;
        if (colType === 'number') {
          if (params.newValue === '' || params.newValue === null || params.newValue === undefined) {
            finalVal = null;
          } else {
            const parsed = Number(params.newValue);
            if (isNaN(parsed)) {
              alert(`컬럼 '${col}'의 값 '${params.newValue}'은(는) 올바른 숫자 형식이 아닙니다.`);
              return false;
            }
            finalVal = parsed;
          }
        }

        params.data.data[col].value = finalVal;
        if (!state.txModeActive) {
          params.data.data[col].is_overwrite = true;
          params.data.data[col].priority_source = 'user';
        }
        return true;
      },
      cellClassRules: {
        'cell-system-readonly': () => isSystem,
        'cell-dirty-tx': (params) => {
          if (isSystem) return false;
          if (!params.data) return false;
          const key = `${params.data.row_id}_${col}`;
          return state.pendingTxEdits.hasOwnProperty(key);
        },
        'cell-collision-merge': (params) => {
          if (isSystem) return false;
          if (!params.data) return false;
          const key = `${params.data.row_id}_${col}`;
          if (state.pendingTxEdits.hasOwnProperty(key)) return false;
          const cell = params.data.data?.[col];
          return cell?.priority_source === 'collision_merge';
        },
        'cell-overwrite': (params) => {
          if (isSystem) return false;
          if (!params.data) return false;
          const key = `${params.data.row_id}_${col}`;
          if (state.pendingTxEdits.hasOwnProperty(key)) return false;
          const cell = params.data.data?.[col];
          return cell?.priority_source === 'user';
        },
        'custom-range-selected': (params) => {
          return isCellInRange(params.node.rowIndex, col);
        }
      }
    };

    // Applied AFTER the literal so it overrides `filter`/`headerTooltip`, and BEFORE the
    // editor selection below so it cannot touch it: a collide column's storage is still
    // numeric when it is declared `number`, so it keeps `agNumberCellEditor` and its
    // numeric write validation. Only the filter becomes text, because only the filter is
    // evaluated against the joined value.
    if (resolvedEntry) {
      Object.assign(colDef, joinResolvedFilterDef(resolvedEntry, headerLabel));
    }

    if (colType === 'number') {
      colDef.cellEditor = 'agNumberCellEditor';
    } else if (!isSystem && colType === 'string') {
      // [0b-a] Prefix suggestions, on STRING columns only.
      //
      // Scoping, deliberately narrow: `number` keeps `agNumberCellEditor` because that
      // editor carries the numeric validation this grid's `valueSetter` depends on, and
      // `datetime` is refused by the endpoint itself (`_resolve_target` raises rather than
      // inventing a datetime canonicalisation). The server DOES support numeric prefixes
      // (`_numeric_values`), so widening later is a change to this predicate and nothing
      // else — but it would mean re-implementing number validation inside the editor,
      // which is a separate round.
      colDef.cellEditor = SuggestCellEditor;
    }

    if (isSystem) {
      colDef.cellClass = 'cell-system-readonly';
    }

    return colDef;
  });

  // ── [Virtual join] The columns a VERIFIED join ADDS to this table's read payload ──────
  //
  // APPENDED, NOT MERGED. These names come from `/schema`'s separate `virtual_columns` key
  // and stay out of `state.currentColumns` (see the note on that field in state.js). They go
  // LAST so the stored columns keep their positions and `checkboxSelection: index === 0`
  // keeps pointing at the same column it always did.
  //
  // The payload cell shape is identical to a stored cell — `attach` fills the same keys
  // `fetch_and_merge_metadata` does — so these defs read cells through the same
  // `rawCellValue`/`numericDisplayValue` the stored defs use, not through a second reader.
  //
  // 🔴 `editable: false` IS NOT THE ENFORCEMENT. The server refuses the write
  // (`crud.refuse_virtual_join_columns`); this only stops the grid offering an edit that
  // would come back 400. The paste/clear/bulk-fill funnels do not read `editable` at all,
  // which is why they carry their own `isVirtualColumn` guard.
  (Array.isArray(state.currentVirtualColumns) ? state.currentVirtualColumns : []).forEach(vc => {
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
    const unresolved = typeof vc.unresolved_label === 'string' ? vc.unresolved_label : '';
    const rightTable = vc.right_table || '?';
    const baseTooltip = `${col.toUpperCase()} — '${rightTable}' 조인 컬럼 (읽기 전용)\n`
      + `값을 고치려면 '${rightTable}' 테이블에서 수정하세요. 선언: ${vc.rule || '?'}`;

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
      cellClassRules: {
        // The other four stored-column rules are deliberately absent, not forgotten:
        // `cell-dirty-tx` keys on `pendingTxEdits`, which a column that cannot be edited
        // never enters; `cell-overwrite`/`cell-collision-merge` test `priority_source`
        // against 'user'/'collision_merge' and `attach` stamps 'virtual_join', so both would
        // be permanently false. Range highlighting is the one that still means something —
        // these cells ARE selectable and copyable.
        'custom-range-selected': (params) => isCellInRange(params.node.rowIndex, col)
      }
    });
  });

  columnDefs.unshift({
    headerName: '#',
    headerTooltip: 'Row Number',
    valueGetter: (params) => {
      const skip = (state.viewMode === 'pagination' && !state.allDataLoaded) ? state.currentSkip : 0;
      return skip + params.node.rowIndex + 1;
    },
    width: 100,
    minWidth: 90,
    maxWidth: 150,
    pinned: 'left',
    suppressMovable: true,
    sortable: false,
    filter: false,
    resizable: false,
    editable: false,
    cellClass: 'cell-system-readonly'
  });

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
  const canvas = headerLabelWidth.canvas || (headerLabelWidth.canvas = document.createElement('canvas'));
  const context = canvas.getContext('2d');
  if (!context) return 0;
  const family = getComputedStyle(document.body).getPropertyValue('--font-sans').trim() || 'sans-serif';
  // Matches `#myGrid .ag-header-cell-text` in style.css. Uppercase because the header is
  // transformed there, and the transform changes the measured width.
  context.font = `600 10.5px ${family}`;
  const text = String(label).toUpperCase();
  return Math.ceil(context.measureText(text).width + text.length * 0.4);
}

function applyMockupLayout(columnDefs) {
  columnDefs.forEach(def => {
    const mockupWidth = MOCKUP_COLUMN_LAYOUT[def.field];
    if (!mockupWidth) return;
    const width = Math.max(mockupWidth, headerLabelWidth(def.headerName) + HEADER_CHROME_PX);
    def.width = width; def.minWidth = Math.min(width, def.minWidth ?? width);
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
  //
  // The checkbox re-application went with the sort. `buildColumnDefs` sets
  // `checkboxSelection: index === 0` against the schema order, and that is now the rendered
  // order, so re-deriving it here could only ever disagree with itself.
  return columnDefs;
}

// Render grid layout using AG-Grid Core
export function renderGrid(initialRows) {
  const columnDefs = buildColumnDefs();

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

  const gridOptions = {
    theme: 'legacy',
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
      width: 150,
      minWidth: 100,
      floatingFilter: true,
      // 🔴 NO `suppressFilterButton` HERE, DELIBERATELY. The 2b order asked for it and the
      // line was removed after measuring what it would cost: the funnel is the ONLY route to
      // the operator list, and `joinResolvedFilterDef` writes a header tooltip that tells the
      // operator to "필터를 Equals 로 두고" — suppressing it deletes the path the screen's own
      // instruction depends on. (It was also inert as written: AG-Grid 35 reads
      // `colDef.suppressFloatingFilterButton`, not this key, so the line did nothing and the
      // next reader would have spent a day on "why doesn't this work".)
      suppressKeyboardEvent: (params) => {
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
    },
    rowSelection: 'multiple',
    // 선택이 바뀌었다는 «신호»만 냅니다. 누가 듣는지는 화면이 정합니다 --
    // 이 파일이 배너를 알면 그리드가 헤더를 아는 것이 됩니다.
    onSelectionChanged: () => { if (selectionListener) selectionListener(); },
    onGridReady: (event) => {
      state.gridApi = event.api;
      updateVisibleColIndexMap();
    },
    onColumnMoved: () => {
      updateVisibleColIndexMap();
    },
    onColumnVisible: () => {
      updateVisibleColIndexMap();
    },
    onColumnPinned: () => {
      updateVisibleColIndexMap();
    },
    onColumnEverythingChanged: () => {
      updateVisibleColIndexMap();
    },
    onFilterChanged: () => {
      fetchData(true);
      renderFilterBar();
    },
    // The `+N열 →` count is a fact about the VIEWPORT, so it is re-measured by everything
    // that can move the viewport's right edge: the first paint, a sidebar drag, a column
    // resize (which `sizeColumnsToFit` also raises), and horizontal scrolling.
    onFirstDataRendered: () => {
      renderFilterBar();
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
      if (!['row_id', 'created_at', 'updated_at', '#'].includes(debugColId)) {
        const cellObj = rowNode.data.data?.[debugColId];
        console.log(`%c[Grid Debug] Clicked Cell Info`, 'color: #00f0ff; font-weight: bold; font-size: 1.1rem;');
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
      refreshReferenceForSelection();
      if (state.activeHistoryTab !== 'global') {
        loadHistory();
      }
    },
    onCellMouseDown: (event) => {
      if (event.event.button !== 0) return;
      if (event.column.getColId() === '#') return;

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
        if (!isCtrl) {
          clearRangeSelection();
        }

        state.isDraggingRange = true;
        state.dragStartCell = { rowIndex: currRow, colId: currCol };
        state.dragEndCell = { rowIndex: currRow, colId: currCol };

        refreshRange(event.api, state.dragStartCell, state.dragEndCell);
      }
    },
    onCellMouseOver: (event) => {
      if (event.event && event.event.buttons !== undefined && event.event.buttons !== 1) {
        if (state.isDraggingRange) {
          state.isDraggingRange = false;
          commitDragSelection(event.api);
          event.api.refreshCells({ force: true });
        }
        return;
      }

      if (!state.isDraggingRange || !state.dragStartCell) return;
      if (event.column.getColId() === '#') return;

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
    onCellMouseUp: (event) => {
      if (state.isDraggingRange) {
        state.isDraggingRange = false;
        
        const isCtrl = event.event.ctrlKey || event.event.metaKey;
        const isSingleClick = (state.dragStartCell.rowIndex === state.dragEndCell.rowIndex && state.dragStartCell.colId === state.dragEndCell.colId);
        
        if (isSingleClick && isCtrl) {
          const key = `${state.dragStartCell.rowIndex}_${state.dragStartCell.colId}`;
          if (state.selectedCellsMap[key]) {
            delete state.selectedCellsMap[key];
          } else {
            const rowNode = event.api.getDisplayedRowAtIndex(state.dragStartCell.rowIndex);
            const rowId = rowNode?.data?.row_id;
            state.selectedCellsMap[key] = { rowIndex: state.dragStartCell.rowIndex, colId: state.dragStartCell.colId, rowId };
          }
          state.dragStartCell = null;
          state.dragEndCell = null;
        } else {
          commitDragSelection(event.api);
        }

        const oldStart = state.dragStartCell;
        const oldEnd = state.dragEndCell;
        state.dragStartCell = null;
        state.dragEndCell = null;
        
        if (oldStart && oldEnd) {
          refreshRange(event.api, oldStart, oldEnd);
        }
        event.api.refreshCells({ force: true });
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
        if (nearBottom) {
          state.currentSkip += pageLimit;
          fetchData(false);
        }
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
