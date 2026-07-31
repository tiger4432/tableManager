export const state = {
  gridApi: null,
  currentTable: '',
  currentColumns: [],
  currentColumnTypes: {},
  currentBusinessKey: '',          // 비즈니스 키 컬럼명 (예: 'pkg_id')
  currentCompositeKeySources: [],  // 조합 소스 컬럼 목록 (예: ['base', 'x', 'y'])
  // [Virtual join] `/schema`'s `virtual_columns`, verbatim. Entries are
  // `{name, type, editable:false, right_table, rule, unresolved_label}`.
  //
  // 🔴 DELIBERATELY NOT MERGED INTO `currentColumns`. That list means "columns this table
  // STORES", and four consumers read it as exactly that: `api.js`'s search dropdown (the
  // SQL cannot reach a virtual name), `clipboard.js`'s copy predicates, `grid.js`'s
  // editability, and — through `/schema.columns` rather than this list —
  // `map_editor.js:getUnprotectedPushColumns`, which counts unprotected data columns a
  // ⚡ Push would destroy. A virtual column cannot be lost by a push because it is not
  // stored, so counting it there would downgrade or block a push for no reason.
  // Keeping the two lists apart is what makes each of those answers stay right.
  currentVirtualColumns: [],
  ws: null,
  wsReconnectDelay: 1000,
  selectedCell: null, // { rowId, colId, value, rowIndex }
  activeHistoryTab: 'global',
  dragStartCell: null,
  dragEndCell: null,
  selectedCellsMap: {}, // key: "rowIndex_colId"
  isDraggingRange: false,
  globalHistoryData: [],
  cellRowHistoryData: [],
  expandedTransactions: new Set(),
  fetchingTransactions: new Set(),
  currentTransactionId: null,
  colIdToIndexMap: {},
  currentSkip: 0,
  isLoadingMore: false,
  hasMoreData: true,
  isNavigating: false,
  navigationWatchdog: null,
  pageCache: new Map(),
  txModeActive: true,
  pendingTxEdits: {}, // key: row_id + "_" + col_name -> { rowId, colId, newValue, oldValue, oldIsOverwrite, data }
  viewMode: 'pagination', // 'pagination' | 'infinite'
  allDataLoaded: false,
  isDesktop: new URLSearchParams(window.location.search).get('client') === 'desktop',
  dragRefreshPending: false,
  visibleColIndexMap: {}, // key: colId -> visibleIndex
  // Smart paste latch. `navigator.clipboard` is undefined on the plain-HTTP intranet, so the
  // ONLY way to read the clipboard is a native `paste` event - which a button click cannot
  // produce (`document.execCommand('paste')` is blocked in web content). This timestamp is
  // the window during which the next `paste` event is routed to the parser instead of to the
  // normal cell-range paste. 0 = not armed. Consumed on use, expires on its own otherwise.
  smartPasteArmedUntil: 0,
  // The table that was on screen when the latch was armed. If it changed before the paste
  // landed the upload is refused - this path INGESTS, and a file in the wrong table is a
  // data error rather than a cosmetic one.
  smartPasteArmedTable: ''
};

/**
 * [Virtual join] Is this grid column id a join-attached column rather than a stored one?
 *
 * WHY A PREDICATE AND NOT A LIST MEMBERSHIP TEST AT EACH SITE. Every write funnel in this
 * client answers "may I write this grid column?" with its own hardcoded system-name array
 * (`clipboard.js` x3, `ui.js`). Those arrays are name lists and a virtual column's name is
 * site-specific, so it cannot join them. This is the one place that knows the answer.
 *
 * 🔴 THIS IS NOT THE ENFORCEMENT. The server refuses a write to a virtual column in
 * `crud.refuse_virtual_join_columns`, at the single funnel every write path converges on.
 * This predicate only stops the client OFFERING a write that would come back 400 — and the
 * refusal is BATCH-LEVEL, so one pasted block overlapping a virtual column would lose the
 * whole paste, not just the cell it could not have written anyway.
 */
export function isVirtualColumn(colId) {
  const list = state.currentVirtualColumns;
  if (!Array.isArray(list) || list.length === 0) return false;
  return list.some(vc => vc && vc.name === colId);
}

export function updateVisibleColIndexMap() {
  if (!state.gridApi) return;
  const colState = state.gridApi.getColumnState() || [];
  const indexMap = {};
  let visibleIdx = 0;
  colState.forEach(c => {
    if (!c.hide) {
      indexMap[c.colId] = visibleIdx;
      visibleIdx++;
    }
  });
  state.visibleColIndexMap = indexMap;
}
