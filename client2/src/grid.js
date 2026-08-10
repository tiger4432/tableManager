import { createGrid } from 'ag-grid-community';
import { pageLimit } from './config.js';
import { state, updateVisibleColIndexMap, joinResolvedColumn } from './state.js';
import { elements } from './dom.js';
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
import { refreshReferenceForSelection } from './enrichment_reference_view.js';

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
 * Visible column ids in visible order, '#' (the row-number gutter) excluded.
 * Ordered by the index map's VALUES rather than trusting key insertion order, so it
 * cannot silently disagree with `visibleColIndexMap` after a column move.
 */
function visibleRangeColIds() {
  const map = state.visibleColIndexMap || {};
  const ids = Object.keys(map).filter(id => id !== '#');
  if (ids.length > 0) return ids.sort((a, b) => map[a] - map[b]);
  if (!state.gridApi) return [];
  return (state.gridApi.getColumnState() || [])
    .filter(c => !c.hide && c.colId !== '#')
    .map(c => c.colId);
}

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
export function buildColumnDefs() {
  const columnDefs = state.currentColumns.map((col, index) => {
    const isSystem = ['created_at', 'updated_at', 'row_id', 'id', 'updated_by', 'is_graph_synced', 'needs_graph_rollback', 'graph_synced_at'].includes(col);
    const colTypes = state.currentColumnTypes || {};
    const colType = colTypes[col] || 'string';

    // 헤더명에 비즈니스 키 / 조합 소스 컬럼 아이콘 표시
    let headerLabel = col.toUpperCase();
    if (col === state.currentBusinessKey) {
      headerLabel = `${headerLabel}🗝️`;
    } else if (state.currentCompositeKeySources.includes(col)) {
      headerLabel = `${headerLabel}*`;
    }

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
      filter: colType === 'number' ? 'agNumberColumnFilter' : 'agTextColumnFilter',
      resizable: true,
      checkboxSelection: index === 0,
      headerCheckboxSelection: index === 0,
      valueGetter: (params) => {
        if (col === 'row_id') return params.data.row_id;
        if (col === 'created_at') return params.data.created_at;
        if (col === 'updated_at') return params.data.updated_at;

        const val = rawCellValue(params.data, col);

        // 그래프 동기화 컬럼 가시성 향상 이모지 매핑
        if (col === 'is_graph_synced') {
          return (val === true || String(val).toLowerCase() === 'true') ? '🟢 Synced' : '🔴 Pending';
        }
        if (col === 'needs_graph_rollback') {
          return (val === true || String(val).toLowerCase() === 'true') ? '⚠️ Rollback' : '➖';
        }

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
    const filterDef = resolvedEntry
      ? joinResolvedFilterDef(resolvedEntry, baseTooltip)
      : { filter: false, headerTooltip: baseTooltip };

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
    defaultColDef: {
      width: 150,
      minWidth: 100,
      floatingFilter: true,
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
