export const state = {
  gridApi: null,
  currentTable: '',
  currentColumns: [],
  currentColumnTypes: {},
  currentBusinessKey: '',          // 비즈니스 키 컬럼명 (예: 'pkg_id')
  currentCompositeKeySources: [],  // 조합 소스 컬럼 목록 (예: ['base', 'x', 'y'])
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
