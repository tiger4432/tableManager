import { createGrid, ModuleRegistry, AllCommunityModule } from 'ag-grid-community';
import 'ag-grid-community/styles/ag-grid.css';
import 'ag-grid-community/styles/ag-theme-quartz.css';
import './style.css';

// Register AG-Grid Community Modules
ModuleRegistry.registerModules([AllCommunityModule]);

// Configuration
const isDevServer = window.location.port === '5173';
const API_BASE = isDevServer ? 'http://127.0.0.1:8080' : window.location.origin;
const WS_URL = isDevServer ? 'ws://127.0.0.1:8080/ws' : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`;

// State
const CURRENT_USER = import.meta.env.VITE_USER || 'web_client';
let gridApi = null;
let currentTable = '';
let currentColumns = [];
let currentColumnTypes = {};
let currentBusinessKey = '';          // 비즈니스 키 컬럼명 (예: 'pkg_id')
let currentCompositeKeySources = [];  // 조합 소스 컬럼 목록 (예: ['base', 'x', 'y'])
let ws = null;
let wsReconnectDelay = 1000; // Exponential Backoff initial delay
let selectedCell = null; // { rowId, colId, value, rowIndex }
let activeHistoryTab = 'global'; // 'global' | 'cell' | 'row'
let dragStartCell = null; // { rowIndex, colId }
let dragEndCell = null;   // { rowIndex, colId }
let selectedCellsMap = {}; // key: "rowIndex_colId" -> { rowIndex, colId, rowId }
let isDraggingRange = false;
let globalHistoryData = [];
let cellRowHistoryData = [];
const expandedTransactions = new Set();
const fetchingTransactions = new Set();
let currentTransactionId = null;
let colIdToIndexMap = {}; // Fast lookup cache for column indexes to avoid O(C) getColumns() in isCellInRange

// Lazy Loading state variables
let currentSkip = 0;
const pageLimit = 1000; // Chunk size
let isLoadingMore = false;
let hasMoreData = true;

// HistoryNavigator state variables
let isNavigating = false;
let navigationWatchdog = null;

// Client-Side Page Cache for Pagination
const pageCache = new Map();

// Elements
const tableSelect = document.getElementById('table-select');
const globalSearch = document.getElementById('global-search');
const searchCols = document.getElementById('search-cols');
const serverStatus = document.getElementById('server-status');
const wsStatus = document.getElementById('ws-status');
const exposedRowsCount = document.getElementById('exposed-rows');
const totalRowsCount = document.getElementById('total-rows');
const performanceLog = document.getElementById('performance-log');

const txFilterBanner = document.getElementById('tx-filter-banner');
const bannerTxId = document.getElementById('banner-tx-id');
const clearTxFilterBtn = document.getElementById('clear-tx-filter-btn');

const prevPageBtn = document.getElementById('prev-page-btn');
const nextPageBtn = document.getElementById('next-page-btn');
const pageInfo = document.getElementById('page-info');
const pageInput = document.getElementById('page-input');
const totalPagesSpan = document.getElementById('total-pages');

const tabGlobalBtn = document.getElementById('tab-global');
const tabCellBtn = document.getElementById('tab-cell');
const tabRowBtn = document.getElementById('tab-row');
const selectedCellInfo = document.getElementById('selected-cell-info');
const timeline = document.getElementById('timeline');
const refreshHistoryBtn = document.getElementById('refresh-history-btn');

const contextMenu = document.getElementById('custom-context-menu');
const sourcesModal = document.getElementById('sources-modal');
const modalCloseBtn = document.getElementById('modal-close-btn');

const txModeToggle = document.getElementById('tx-mode-toggle');
const txApplyBtn = document.getElementById('tx-apply-btn');
const txDiscardBtn = document.getElementById('tx-discard-btn');

let txModeActive = true;
let pendingTxEdits = {}; // key: row_id + "_" + col_name -> { rowId, colId, newValue, oldValue, oldIsOverwrite, data }
const sourcesList = document.getElementById('sources-list');
const modalMetaInfo = document.getElementById('modal-meta-info');

const refreshGridBtn = document.getElementById('refresh-grid-btn');
const addRowBtn = document.getElementById('add-row-btn');
const deleteRowBtn = document.getElementById('delete-row-btn');
const ingestFileBtn = document.getElementById('ingest-file-btn');
const smartPasteBtn = document.getElementById('smart-paste-btn');
const toolbarFileInput = document.getElementById('toolbar-file-input');
const copyHeaderToggle = document.getElementById('copy-header-toggle') || { checked: false };
const sortLatestToggle = document.getElementById('sort-latest-toggle');
const viewModeSelect = document.getElementById('view-mode-select');
const loadAllBtn = document.getElementById('load-all-btn');
const loadCsvBtn = document.getElementById('load-csv-btn');
const columnSelectorBtn = document.getElementById('column-selector-btn');
const columnSelectorDropdown = document.getElementById('column-selector-dropdown');
const columnListContainer = document.getElementById('column-list-container');
const colSelectAllBtn = document.getElementById('col-select-all-btn');
const colSelectNoneBtn = document.getElementById('col-select-none-btn');

// View Mode State
let viewMode = 'pagination'; // 'pagination' | 'infinite'
let allDataLoaded = false;
const isDesktop = new URLSearchParams(window.location.search).get('client') === 'desktop';

// Initialize Application
async function init() {
  // 웹 브라우저에서 접근 시, 백그라운드에서 로컬 데스크톱 앱(assymanager://) 호출
  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.get('client') !== 'desktop') {
    console.log('[Launcher] Triggering local desktop client launch via URI scheme...');
    const iframe = document.createElement('iframe');
    iframe.style.display = 'none';
    iframe.src = 'assymanager://open';
    document.body.appendChild(iframe);
    setTimeout(() => iframe.remove(), 1000);
  }

  // Load cached settings from localStorage
  const cachedCopyHeader = localStorage.getItem('copyHeader');
  if (cachedCopyHeader !== null && copyHeaderToggle && 'checked' in copyHeaderToggle) {
    copyHeaderToggle.checked = cachedCopyHeader === 'true';
  }
  const cachedSortLatest = localStorage.getItem('sortLatest');
  if (cachedSortLatest !== null) {
    sortLatestToggle.checked = cachedSortLatest === 'true';
  }

  setupEventListeners();
  setupClipboardHandlers();
  setupDragAndDrop();
  await checkServerHealth();
  await loadTables();
  initWebSocket();
}

// Event Listeners Setup
function setupEventListeners() {
  if (refreshHistoryBtn) {
    refreshHistoryBtn.addEventListener('click', () => {
      loadHistory();
    });
  }

  if (clearTxFilterBtn) {
    clearTxFilterBtn.addEventListener('click', () => {
      setTransactionFilter(null);
    });
  }

  if (prevPageBtn) {
    prevPageBtn.addEventListener('click', () => {
      if (currentSkip >= pageLimit) {
        currentSkip -= pageLimit;
        allDataLoaded = false;
        fetchData(false);
      }
    });
  }
  if (nextPageBtn) {
    nextPageBtn.addEventListener('click', () => {
      currentSkip += pageLimit;
      allDataLoaded = false;
      fetchData(false);
    });
  }

  if (pageInput) {
    const handlePageJump = () => {
      let targetPage = parseInt(pageInput.value, 10);
      const totalPages = parseInt(totalPagesSpan?.textContent || '1', 10);

      if (isNaN(targetPage) || targetPage < 1) {
        pageInput.value = Math.floor(currentSkip / pageLimit) + 1;
        return;
      }

      if (targetPage > totalPages) {
        targetPage = totalPages;
      }

      const newSkip = (targetPage - 1) * pageLimit;
      if (newSkip !== currentSkip || allDataLoaded) {
        currentSkip = newSkip;
        allDataLoaded = false;
        fetchData(false);
      } else {
        pageInput.value = targetPage;
      }
    };

    pageInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        handlePageJump();
        pageInput.blur();
      }
    });

    pageInput.addEventListener('blur', () => {
      handlePageJump();
    });
  }

  tableSelect.addEventListener('change', async (e) => {
    const table = e.target.value;
    if (table) {
      await switchTable(table);
    }
  });

  // Debounced search
  let searchTimeout;
  if (globalSearch) {
    globalSearch.addEventListener('input', () => {
      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(() => {
        fetchData(true);
      }, 300);
    });
  }

  if (searchCols) {
    searchCols.addEventListener('change', () => {
      fetchData(true);
    });
  }

  // History Tabs
  tabGlobalBtn.addEventListener('click', () => {
    tabGlobalBtn.classList.add('active');
    tabCellBtn.classList.remove('active');
    tabRowBtn.classList.remove('active');
    activeHistoryTab = 'global';
    loadHistory();
  });

  tabCellBtn.addEventListener('click', () => {
    tabCellBtn.classList.add('active');
    tabGlobalBtn.classList.remove('active');
    tabRowBtn.classList.remove('active');
    activeHistoryTab = 'cell';
    loadHistory();
  });

  tabRowBtn.addEventListener('click', () => {
    tabRowBtn.classList.add('active');
    tabGlobalBtn.classList.remove('active');
    tabCellBtn.classList.remove('active');
    activeHistoryTab = 'row';
    loadHistory();
  });

  // Transaction Mode listeners
  if (txModeToggle) {
    txModeToggle.addEventListener('change', () => {
      txModeActive = txModeToggle.checked;
      if (!txModeActive) {
        const pendingCount = Object.keys(pendingTxEdits).length;
        if (pendingCount > 0) {
          const confirmApply = confirm(`대기 중인 수정사항이 ${pendingCount}건 있습니다. 적용하시겠습니까?\n\n'확인'을 누르면 수정 사항을 일괄 적용하고,\n'취소'를 누르면 수정 사항을 모두 취소(Discard)합니다.`);
          if (confirmApply) {
            applyPendingTxEdits();
          } else {
            discardPendingTxEdits();
          }
        } else {
          updateTxModeUI();
          gridApi.refreshCells({ force: true });
        }
      } else {
        updateTxModeUI();
        gridApi.refreshCells({ force: true });
      }
    });
  }

  if (txApplyBtn) {
    txApplyBtn.addEventListener('click', () => {
      applyPendingTxEdits();
    });
  }

  if (txDiscardBtn) {
    txDiscardBtn.addEventListener('click', () => {
      discardPendingTxEdits();
    });
  }

  // Prevent accidental page leave with unsaved edits
  window.addEventListener('beforeunload', (e) => {
    if (Object.keys(pendingTxEdits).length > 0) {
      e.preventDefault();
      e.returnValue = '저장되지 않은 수정사항이 있습니다. 페이지를 벗어나시겠습니까?';
      return e.returnValue;
    }
  });

  // Refresh Grid
  if (refreshGridBtn) {
    refreshGridBtn.addEventListener('click', () => {
      if (!currentTable) return;
      performanceLog.textContent = 'Refreshing current page...';
      pageCache.clear();
      if (viewMode === 'infinite' || allDataLoaded) {
        allDataLoaded = false;
        hasMoreData = true;
        fetchData(true);
      } else {
        fetchData(false);
      }
      showToast('🔄 화면이 최신 데이터로 새로고침되었습니다.', 'success');
    });
  }

  // Add Empty Row
  addRowBtn.addEventListener('click', async () => {
    if (!currentTable) return;

    const countStr = prompt('Enter the number of empty rows to add:', '1');
    if (countStr === null) return; // Cancelled

    const count = parseInt(countStr.trim(), 10);
    if (isNaN(count) || count < 1) {
      alert('Please enter a valid number greater than or equal to 1.');
      return;
    }

    performanceLog.textContent = `Creating ${count} empty row(s)...`;
    try {
      const res = await fetch(`${API_BASE}/tables/${currentTable}/rows?count=${count}&user_name=${encodeURIComponent(CURRENT_USER)}`, {
        method: 'POST'
      });
      if (res.ok) {
        const result = await res.json();
        performanceLog.textContent = `${count} empty row(s) created successfully`;
        // History updates will be handled by the WebSocket stream
      } else {
        throw new Error('Create failed');
      }
    } catch (err) {
      console.error('Failed to create row(s)', err);
      performanceLog.textContent = '❌ Failed to create row(s)';
    }
  });

  // Delete Selected Rows Button
  deleteRowBtn.addEventListener('click', () => {
    deleteSelectedRows();
  });

  // Keyboard shortcuts inside the grid
  document.addEventListener('keydown', (e) => {
    const activeEl = document.activeElement;

    if (activeEl && activeEl.closest('#myGrid')) {
      const isEditing = activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA' || activeEl.hasAttribute('contenteditable') || activeEl.classList.contains('ag-input-field-input');

      if (!isEditing) {
        // Delete key inside the grid to clear selected cells
        if (e.key === 'Delete') {
          e.preventDefault();
          clearSelectedCells();
        }
        // Ctrl+C / Cmd+C inside the grid to copy selected cells
        else if ((e.ctrlKey || e.metaKey) && (e.key === 'c' || e.key === 'C')) {
          const rangeTsv = getRangeSelectedTSV();
          if (rangeTsv) {
            e.preventDefault();
            navigator.clipboard.writeText(rangeTsv).then(() => {
              performanceLog.textContent = '📋 Range copied to clipboard';
            }).catch(err => {
              console.error('Failed to copy via Clipboard API', err);
            });
          }
        }
        // Ctrl+A / Cmd+A inside the grid to select all cells
        else if ((e.ctrlKey || e.metaKey) && (e.key === 'a' || e.key === 'A')) {
          e.preventDefault();
          if (gridApi) {
            const allCols = gridApi.getColumns().map(c => c.getColId()).filter(c => c !== '#');
            const totalRows = gridApi.getDisplayedRowCount();
            if (allCols.length > 0 && totalRows > 0) {
              dragStartCell = { rowIndex: 0, colId: allCols[0] };
              dragEndCell = { rowIndex: totalRows - 1, colId: allCols[allCols.length - 1] };

              gridApi.refreshCells({ force: true });
              performanceLog.textContent = '📋 All cells selected';
            }
          }
        }
      }
    }
  });

  // Ingest File Button (Trigger file selector)
  if (ingestFileBtn) {
    ingestFileBtn.addEventListener('click', () => {
      toolbarFileInput.click();
    });
  }

  // Handle selected file(s) ingestion
  toolbarFileInput.addEventListener('change', async (e) => {
    if (!currentTable) return;
    const files = e.target.files;
    if (files.length === 0) return;

    performanceLog.textContent = `Uploading ${files.length} log file(s)...`;

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      performanceLog.textContent = `Uploading file [${file.name}] (${(file.size / 1024).toFixed(1)} KB)...`;

      const formData = new FormData();
      formData.append('file', file);

      try {
        const res = await fetch(`${API_BASE}/tables/${currentTable}/upload?user=${encodeURIComponent(CURRENT_USER)}`, {
          method: 'POST',
          body: formData
        });

        if (res.ok) {
          const resData = await res.json();
          const savedPath = resData.path || '';
          const savedFilename = savedPath.split(/[/\\]/).pop() || file.name;
          performanceLog.textContent = `✅ Successfully ingested [${file.name}]. Sync will refresh table shortly.`;
          showToast(`📤 파일 업로드 완료! (RAW 파일: ${savedFilename})`, 'success');
        } else {
          throw new Error('Upload failed');
        }
      } catch (err) {
        console.error('File ingestion failed', err);
        performanceLog.textContent = `❌ Ingestion failed for [${file.name}]`;
        showToast(`❌ [${file.name}] 파일 인제션에 실패했습니다.`, 'error');
      }
    }
    // Reset file input value
    toolbarFileInput.value = '';
  });

  // Smart Paste Button
  if (smartPasteBtn) {
    smartPasteBtn.addEventListener('click', () => {
      smartPasteViaIngestion();
    });
  }

  // Sort Toggle
  sortLatestToggle.addEventListener('change', () => {
    localStorage.setItem('sortLatest', sortLatestToggle.checked);
    fetchData(true);
  });

  // Copy Header Toggle
  if (copyHeaderToggle && typeof copyHeaderToggle.addEventListener === 'function') {
    copyHeaderToggle.addEventListener('change', () => {
      localStorage.setItem('copyHeader', copyHeaderToggle.checked);
    });
  }

  // Context Menu Item: Sources Management
  document.getElementById('menu-sources').addEventListener('click', () => {
    contextMenu.style.display = 'none';
    openSourcesModal();
  });

  // Context Menu Item: Delete selected rows
  document.getElementById('menu-delete').addEventListener('click', () => {
    contextMenu.style.display = 'none';
    deleteSelectedRows();
  });

  // Context Menu Item: Smart paste via parser
  document.getElementById('menu-smart-paste').addEventListener('click', () => {
    contextMenu.style.display = 'none';
    smartPasteViaIngestion();
  });

  // Close context menu on outside click
  document.addEventListener('click', (e) => {
    if (!e.target.closest('#custom-context-menu')) {
      contextMenu.style.display = 'none';
    }
  });

  // Block browser default context menu on AG-Grid container to prevent overlap
  const gridContainer = document.getElementById('myGrid');
  if (gridContainer) {
    gridContainer.addEventListener('contextmenu', (e) => {
      e.preventDefault();
    });
    gridContainer.addEventListener('mouseleave', () => {
      if (isDraggingRange) {
        isDraggingRange = false;
        commitDragSelection(gridApi);
        if (gridApi) {
          gridApi.refreshCells({ force: true });
        }
      }
    });
  }

  // Initialize native DOM mouse selection handlers for the grid
  setupNativeGridMouseHandlers();

  // Sources Modal Close Button
  modalCloseBtn.addEventListener('click', () => {
    sourcesModal.style.display = 'none';
  });

  // Close modal on background click
  sourcesModal.addEventListener('click', (e) => {
    if (e.target === sourcesModal) {
      sourcesModal.style.display = 'none';
    }
  });

  // ── 컬럼 토글 드롭다운 구현 ──
  if (columnSelectorBtn) {
    columnSelectorBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      const isVisible = columnSelectorDropdown.style.display === 'block';
      if (isVisible) {
        columnSelectorDropdown.style.display = 'none';
      } else {
        // 드롭다운 위치 조정 (버튼 하단에 배치)
        const rect = columnSelectorBtn.getBoundingClientRect();
        columnSelectorDropdown.style.top = `${rect.bottom + window.scrollY + 6}px`;
        columnSelectorDropdown.style.left = `${rect.left + window.scrollX}px`;
        columnSelectorDropdown.style.display = 'block';

        // 현재 컬럼 가시성 상태에 맞춰 리스트 렌더링
        renderColumnSelectorList();
      }
    });
  }

  // 드롭다운 및 버튼 영역 외부 클릭 시 드롭다운 닫기
  document.addEventListener('click', (e) => {
    if (columnSelectorDropdown && columnSelectorDropdown.style.display === 'block') {
      if (!e.target.closest('#column-selector-dropdown') && !e.target.closest('#column-selector-btn')) {
        columnSelectorDropdown.style.display = 'none';
      }
    }
  });

  // 컬럼 선택 드롭다운 내 체크박스 리스트 동적 렌더링 함수
  function renderColumnSelectorList() {
    if (!gridApi || !columnListContainer) return;
    columnListContainer.innerHTML = '';

    // AG-Grid의 모든 컬럼을 조회
    const columns = gridApi.getColumns() || [];
    
    columns.forEach(col => {
      const colId = col.getColId();
      // 번호 열('#')은 가시성 토글에서 제외
      if (colId === '#') return;

      const isVisible = col.isVisible();
      const headerName = col.getColDef().headerName || colId;

      const li = document.createElement('li');
      li.className = 'col-selector-item';

      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.className = 'col-selector-checkbox';
      checkbox.checked = isVisible;
      checkbox.id = `col-toggle-${colId}`;

      const label = document.createElement('label');
      label.className = 'col-selector-label';
      label.htmlFor = `col-toggle-${colId}`;
      label.textContent = headerName;

      // 항목 클릭 시 체크박스 토글 연동
      li.addEventListener('click', (evt) => {
        if (evt.target !== checkbox && evt.target !== label) {
          evt.stopPropagation();
          checkbox.checked = !checkbox.checked;
          gridApi.setColumnsVisible([colId], checkbox.checked);
        }
      });

      checkbox.addEventListener('change', () => {
        gridApi.setColumnsVisible([colId], checkbox.checked);
      });

      li.appendChild(checkbox);
      li.appendChild(label);
      columnListContainer.appendChild(li);
    });
  }

  // 전체 선택 버튼
  if (colSelectAllBtn) {
    colSelectAllBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (!gridApi) return;
      const columns = gridApi.getColumns() || [];
      const colIds = columns.map(c => c.getColId()).filter(id => id !== '#');
      gridApi.setColumnsVisible(colIds, true);
      renderColumnSelectorList();
    });
  }

  // 전체 해제 버튼
  if (colSelectNoneBtn) {
    colSelectNoneBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (!gridApi) return;
      const columns = gridApi.getColumns() || [];
      const colIds = columns.map(c => c.getColId()).filter(id => id !== '#');
      gridApi.setColumnsVisible(colIds, false);
      renderColumnSelectorList();
    });
  }

  // View Mode Change Handler
  if (viewModeSelect) {
    viewModeSelect.addEventListener('change', (e) => {
      viewMode = e.target.value;
      allDataLoaded = false;
      hasMoreData = true;
      updateViewModeUI();
      pageCache.clear();
      fetchData(true);
    });
  }

  // Load All Button Handler
  if (loadAllBtn) {
    loadAllBtn.addEventListener('click', async () => {
      if (!currentTable || isLoadingMore) return;

      isLoadingMore = true;
      performanceLog.textContent = '⚡ 1/3. Initializing bulk request...';
      const startTime = performance.now();

      const q = globalSearch ? globalSearch.value.trim() : '';
      const cols = searchCols ? searchCols.value : '';
      const sortLatest = sortLatestToggle.checked;
      const filterModel = gridApi ? gridApi.getFilterModel() : {};
      const filterStr = Object.keys(filterModel).length > 0 ? JSON.stringify(filterModel) : '';

      const baseApiUrl = `${API_BASE}/tables/${currentTable}/data`;
      let queryParams = `order_by=${sortLatest ? 'updated_at' : 'row_id'}&order_desc=${sortLatest}`;
      if (currentTransactionId) {
        queryParams += `&transaction_id=${currentTransactionId}`;
      }
      if (q) {
        queryParams += `&q=${encodeURIComponent(q)}`;
        if (cols) {
          queryParams += `&cols=${encodeURIComponent(cols)}`;
        }
      }
      if (filterStr) {
        queryParams += `&filters=${encodeURIComponent(filterStr)}`;
      }

      try {
        const chunkLimit = 3000; // 청크 단위로 분할 로드
        let accumulatedData = [];
        let totalRows = 0;
        let currentSkipOffset = 0;

        performanceLog.textContent = '⚡ 1/3. Fetching initial row chunk...';

        // 1. 첫 번째 청크 요청하여 전체 개수(total)와 첫 데이터를 받아옴
        const firstUrl = `${baseApiUrl}?skip=${currentSkipOffset}&limit=${chunkLimit}&${queryParams}`;
        const firstRes = await fetch(firstUrl);
        if (!firstRes.ok) throw new Error(`HTTP error! status: ${firstRes.status}`);
        const firstResult = await firstRes.json();

        accumulatedData = firstResult.data || [];
        totalRows = firstResult.total || 0;
        currentSkipOffset += accumulatedData.length;

        // 실시간 진행률 업데이트
        if (totalRows > 0) {
          const percent = Math.min(100, Math.floor((accumulatedData.length / totalRows) * 100));
          performanceLog.textContent = `⏳ 2/3. Fetching rows: ${percent}% (${accumulatedData.length} / ${totalRows})`;
        } else {
          performanceLog.textContent = `⏳ 2/3. Fetching rows: 100% (0 / 0)`;
        }

        // 2. 전체 데이터 개수가 첫 번째 수집량보다 많다면 루프를 돌며 추가 청크 수집
        while (accumulatedData.length < totalRows && currentSkipOffset < totalRows) {
          // 브라우저 렌더링 프레임 양보하여 UI 갱신 보장
          await new Promise(resolve => setTimeout(resolve, 5));

          const nextUrl = `${baseApiUrl}?skip=${currentSkipOffset}&limit=${chunkLimit}&${queryParams}`;
          const nextRes = await fetch(nextUrl);
          if (!nextRes.ok) throw new Error(`HTTP error! status: ${nextRes.status}`);
          const nextResult = await nextRes.json();

          const nextChunk = nextResult.data || [];
          if (nextChunk.length === 0) {
            // 더 이상 가져올 데이터가 없음 (서버 데이터 변동 가능성 대비 탈출)
            break;
          }

          accumulatedData = accumulatedData.concat(nextChunk);
          currentSkipOffset += nextChunk.length;

          const percent = Math.min(100, Math.floor((accumulatedData.length / totalRows) * 100));
          performanceLog.textContent = `⏳ 2/3. Fetching rows: ${percent}% (${accumulatedData.length} / ${totalRows})`;
        }

        const fetchEndTime = performance.now();
        const totalFetchTime = (fetchEndTime - startTime).toFixed(0);

        performanceLog.textContent = '🎨 3/3. Initializing cells & drawing grid...';
        await new Promise(resolve => setTimeout(resolve, 20)); // UI 반영을 위해 양보

        const renderStartTime = performance.now();

        allDataLoaded = true;
        hasMoreData = false;

        // 그리드 데이터 로드
        gridApi.setGridOption('rowData', accumulatedData);
        updateGridSortState();

        updateLoadedCount(accumulatedData.length);
        totalRowsCount.textContent = `Matches: ${totalRows}`;
        updateViewModeUI();

        const renderEndTime = performance.now();
        const renderTime = (renderEndTime - renderStartTime).toFixed(0);
        const totalTime = (renderEndTime - startTime).toFixed(0);

        performanceLog.textContent = `✅ Loaded ${accumulatedData.length} rows (Fetch Chunks: ${totalFetchTime}ms, Render: ${renderTime}ms | Total: ${totalTime}ms)`;
        showToast(`📥 전체 ${accumulatedData.length}개 행 로드 완료!`, 'success');
        isLoadingMore = false;
      } catch (err) {
        console.error('Failed to load all rows sequentially', err);
        performanceLog.textContent = '❌ Failed to load all rows';
        showToast('❌ 전체 데이터 로드 중 오류 발생', 'error');
        isLoadingMore = false;
      }
    });
  }


  // Load CSV Button Handler (Direct Download with Progress & Custom Filename / Native FileDialog)
  if (loadCsvBtn) {
    loadCsvBtn.addEventListener('click', async () => {
      if (!currentTable) return;

      // Determine default filename
      const now = new Date();
      const timestamp = now.getFullYear() +
        String(now.getMonth() + 1).padStart(2, '0') +
        String(now.getDate()).padStart(2, '0') + '_' +
        String(now.getHours()).padStart(2, '0') +
        String(now.getMinutes()).padStart(2, '0') +
        String(now.getSeconds()).padStart(2, '0');
      const defaultFilename = `${currentTable}_extract_${timestamp}.csv`;

      let fileHandle = null;
      let writableStream = null;
      let useFileSystemAccess = !isDesktop && (typeof window.showSaveFilePicker === 'function');

      if (useFileSystemAccess) {
        try {
          fileHandle = await window.showSaveFilePicker({
            suggestedName: defaultFilename,
            types: [{
              description: 'CSV Files (*.csv)',
              accept: {
                'text/csv': ['.csv']
              }
            }]
          });
        } catch (err) {
          // If user cancels the picker, abort the download completely
          if (err.name === 'AbortError') {
            console.log('[CSV Export] User cancelled file dialog picker.');
            return;
          }
          // For security or other errors in wrapping environment, fallback to standard prompt
          console.warn('[CSV Export] File System Access API failed, falling back to prompt:', err);
          useFileSystemAccess = false;
        }
      }

      let finalFilename = defaultFilename;
      if (!isDesktop && !useFileSystemAccess) {
        const filenameInput = prompt('저장할 CSV 파일명을 입력해주세요:', defaultFilename);
        if (filenameInput === null) return; // Cancelled by user

        finalFilename = filenameInput.trim();
        if (!finalFilename) {
          finalFilename = defaultFilename;
        }
        if (!finalFilename.toLowerCase().endsWith('.csv')) {
          finalFilename += '.csv';
        }
      }

      const q = globalSearch ? globalSearch.value.trim() : '';
      const cols = searchCols ? searchCols.value : '';
      const sortLatest = sortLatestToggle.checked;
      const filterModel = gridApi ? gridApi.getFilterModel() : {};
      const filterStr = Object.keys(filterModel).length > 0 ? JSON.stringify(filterModel) : '';

      let url = `${API_BASE}/tables/${currentTable}/export?`;
      url += `order_by=${sortLatest ? 'updated_at' : 'row_id'}&order_desc=${sortLatest}`;
      if (currentTransactionId) {
        url += `&transaction_id=${currentTransactionId}`;
      }
      if (q) {
        url += `&q=${encodeURIComponent(q)}`;
        if (cols) {
          url += `&cols=${encodeURIComponent(cols)}`;
        }
      }
      if (filterStr) {
        url += `&filters=${encodeURIComponent(filterStr)}`;
      }

      performanceLog.textContent = 'Connecting...';
      showToast('📄 CSV 다운로드를 시작합니다.', 'success');

      try {
        const response = await fetch(url);
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        const totalBytesHeader = response.headers.get('X-Estimated-Content-Length') || response.headers.get('Content-Length');
        const totalBytes = totalBytesHeader ? parseInt(totalBytesHeader, 10) : 0;

        const reader = response.body.getReader();
        let receivedBytes = 0;

        if (useFileSystemAccess && fileHandle) {
          writableStream = await fileHandle.createWritable();
        }

        const chunks = [];

        while (true) {
          const { done, value } = await reader.read();
          if (done) {
            break;
          }

          if (useFileSystemAccess && writableStream) {
            await writableStream.write(value);
          } else {
            chunks.push(value);
          }
          receivedBytes += value.length;

          if (totalBytes > 0) {
            let percent = Math.floor((receivedBytes / totalBytes) * 100);
            if (percent > 99) percent = 99;
            if (percent < 0) percent = 0;
            const kbReceived = (receivedBytes / 1024).toFixed(0);
            const kbTotal = (totalBytes / 1024).toFixed(0);
            performanceLog.textContent = `Downloading: ${percent}% (${kbReceived}K / ${kbTotal}K)`;
          } else {
            const kbReceived = (receivedBytes / 1024).toFixed(0);
            performanceLog.textContent = `Downloading: ${kbReceived}KB`;
          }
        }

        performanceLog.textContent = 'Processing...';

        if (useFileSystemAccess && writableStream) {
          await writableStream.close();
          const savedName = fileHandle.name;
          performanceLog.textContent = `CSV Saved: ${savedName}`;
          showToast(`📄 CSV 파일 저장 완료! (${savedName})`, 'success');
        } else {
          // Assemble chunks into a Blob
          const blob = new Blob(chunks, { type: 'text/csv;charset=utf-8;' });
          const blobUrl = URL.createObjectURL(blob);

          const link = document.createElement('a');
          link.href = blobUrl;
          link.download = finalFilename;
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
          URL.revokeObjectURL(blobUrl);

          performanceLog.textContent = `CSV Downloaded: ${finalFilename}`;
          showToast(`📄 CSV 파일 다운로드 완료! (${finalFilename})`, 'success');
        }
      } catch (err) {
        console.error('Failed to download CSV', err);
        if (writableStream) {
          try { await writableStream.abort(); } catch (e) { }
        }
        performanceLog.textContent = '❌ CSV Download Failed';
        showToast('❌ CSV 다운로드 중 오류 발생', 'error');
      }
    });
  }
}

// Check backend server status
async function checkServerHealth() {
  try {
    const res = await fetch(`${API_BASE}/tables`);
    if (res.ok) {
      serverStatus.textContent = 'API: ONLINE';
      serverStatus.className = 'status-badge online';
    } else {
      throw new Error();
    }
  } catch (err) {
    serverStatus.textContent = 'API: OFFLINE';
    serverStatus.className = 'status-badge offline';
    performanceLog.textContent = 'Error connecting to database server';
  }
}

// Load available tables
async function loadTables() {
  try {
    const res = await fetch(`${API_BASE}/tables`);
    const data = await res.json();
    tableSelect.innerHTML = '';

    if (data.tables && data.tables.length > 0) {
      data.tables.forEach(table => {
        const option = document.createElement('option');
        option.value = table;
        option.textContent = table;
        tableSelect.appendChild(option);
      });

      // Auto select first table
      const firstTable = data.tables[0];
      tableSelect.value = firstTable;
      await switchTable(firstTable);
    } else {
      tableSelect.innerHTML = '<option value="">No tables found</option>';
    }
  } catch (err) {
    console.error('Failed to load tables', err);
    tableSelect.innerHTML = '<option value="">Failed to load</option>';
  }
}

// Set or clear transaction filter context
function setTransactionFilter(txId) {
  currentTransactionId = txId;
  if (txId) {
    if (bannerTxId) bannerTxId.textContent = txId;
    if (txFilterBanner) txFilterBanner.style.display = 'flex';
  } else {
    if (bannerTxId) bannerTxId.textContent = '';
    if (txFilterBanner) txFilterBanner.style.display = 'none';
  }

  // Refresh history timeline highlights to match the new filter context
  const timelineItems = timeline.querySelectorAll('.timeline-item');
  timelineItems.forEach(li => {
    const itemTxId = li.dataset.txId || (li.querySelector('.filter-tx-btn')?.dataset.txId);
    if (itemTxId && itemTxId === currentTransactionId) {
      li.classList.add('active-tx-log');
    } else {
      li.classList.remove('active-tx-log');
    }
  });

  // Reload data from skip = 0
  fetchData(true);
}

// Switch current working table
async function switchTable(tableName) {
  currentTable = tableName;
  window.currentTable = tableName; // Expose globally for Desktop Wrapper
  performanceLog.textContent = `Switching to ${tableName}...`;

  // Clean selected cell info
  selectedCell = null;
  clearRangeSelection();
  updateSelectedCellUI();

  // Discard pending edits on table switch
  pendingTxEdits = {};
  txModeActive = true;
  if (txModeToggle) txModeToggle.checked = true;
  updateTxModeUI();

  // Reset transaction filter
  currentTransactionId = null;
  if (txFilterBanner) txFilterBanner.style.display = 'none';
  if (bannerTxId) bannerTxId.textContent = '';

  // Load Schema
  await loadSchema(tableName);
  // Re-create empty grid to bind new columns
  renderGrid([]);
  // Fetch initial chunk of data (reset skip to 0)
  await fetchData(true);

  // Reset active history tab to global when switching tables to avoid empty screen
  activeHistoryTab = 'global';
  tabGlobalBtn.classList.add('active');
  tabCellBtn.classList.remove('active');
  tabRowBtn.classList.remove('active');
  await loadHistory();
}

// Load table column schema
async function loadSchema(tableName) {
  try {
    const res = await fetch(`${API_BASE}/tables/${tableName}/schema`);
    const data = await res.json();
    currentColumns = data.columns || [];
    currentColumnTypes = data.column_types || {};
    currentBusinessKey = data.business_key || '';
    currentCompositeKeySources = data.composite_key_source || [];

    // Fill search columns dropdown
    if (searchCols) {
      searchCols.innerHTML = '<option value="">All Columns</option>';
      currentColumns.forEach(col => {
        if (col !== 'created_at' && col !== 'updated_at') {
          const option = document.createElement('option');
          option.value = col;
          option.textContent = col;
          searchCols.appendChild(option);
        }
      });
    }
  } catch (err) {
    console.error('Failed to load schema', err);
    performanceLog.textContent = 'Schema load error';
  }
}

// Apply AG-Grid client-side sorting configuration based on Sort Latest toggle
function updateGridSortState() {
  if (!gridApi) return;

  // Do not re-sort if Tx Mode is active to prevent staged rows from jumping
  if (txModeActive) {
    return;
  }

  // Do not re-sort if user is actively editing a cell to prevent the row from jumping away
  const editingCells = gridApi.getEditingCells();
  if (editingCells && editingCells.length > 0) {
    return;
  }

  const sortLatest = sortLatestToggle.checked;
  gridApi.applyColumnState({
    state: [
      { colId: 'updated_at', sort: sortLatest ? 'desc' : null },
      { colId: 'row_id', sort: sortLatest ? null : 'asc' }
    ],
    defaultState: { sort: null }
  });
}

// Update Loaded count slice text
function updateLoadedCount(forcedCount = null) {
  if (!gridApi) return;
  const displayedCount = gridApi.getDisplayedRowCount();

  if (viewMode === 'infinite') {
    exposedRowsCount.textContent = `Loaded: 1 - ${displayedCount}`;
  } else {
    const forced = forcedCount !== null ? forcedCount : displayedCount;
    const startRow = forced === 0 ? 0 : currentSkip + 1;
    const endRow = currentSkip + forced;

    if (startRow === endRow) {
      if (startRow === 0) {
        exposedRowsCount.textContent = `Loaded: 0`;
      } else {
        exposedRowsCount.textContent = `Loaded: ${startRow}`;
      }
    } else {
      exposedRowsCount.textContent = `Loaded: ${startRow} - ${endRow}`;
    }
  }
}

// Update View Mode UI controls visibility
function updateViewModeUI() {
  const paginationControls = document.querySelector('.pagination-controls');
  if (paginationControls) {
    paginationControls.style.display = (viewMode === 'pagination') ? 'flex' : 'none';
  }
}

// Update Pagination controls state
function updatePaginationUI(total) {
  const currentPage = Math.floor(currentSkip / pageLimit) + 1;
  const totalPages = Math.ceil(total / pageLimit) || 1;

  if (pageInput) {
    pageInput.value = currentPage;
    pageInput.max = totalPages;
  }
  if (totalPagesSpan) {
    totalPagesSpan.textContent = totalPages;
  }
  if (prevPageBtn) {
    prevPageBtn.disabled = (currentPage === 1);
  }
  if (nextPageBtn) {
    nextPageBtn.disabled = (currentPage >= totalPages);
  }
}

// Fetch row data and render inside AG-Grid (Handles Pagination)
async function fetchData(resetSkip = true) {
  if (!currentTable || isLoadingMore) return;

  if (resetSkip) {
    pageCache.clear();
    clearRangeSelection();
    currentSkip = 0;
    hasMoreData = true;
    allDataLoaded = false;
  } else {
    if (viewMode !== 'infinite' && pageCache.has(currentSkip)) {
      const cached = pageCache.get(currentSkip);
      gridApi.setGridOption('rowData', cached.data);
      updateGridSortState();
      updateLoadedCount(cached.data.length);
      totalRowsCount.textContent = `Matches: ${cached.total}`;
      updatePaginationUI(cached.total);
      performanceLog.textContent = `Loaded ${cached.data.length} rows from client cache`;
      return;
    }
  }

  isLoadingMore = true;
  performanceLog.textContent = 'Fetching data...';

  const startTime = performance.now();

  const q = globalSearch ? globalSearch.value.trim() : '';
  const cols = searchCols ? searchCols.value : '';
  const sortLatest = sortLatestToggle.checked;
  const filterModel = gridApi ? gridApi.getFilterModel() : {};
  const filterStr = Object.keys(filterModel).length > 0 ? JSON.stringify(filterModel) : '';

  let url = `${API_BASE}/tables/${currentTable}/data?skip=${currentSkip}&limit=${pageLimit}`;
  url += `&order_by=${sortLatest ? 'updated_at' : 'row_id'}&order_desc=${sortLatest}`;
  if (currentTransactionId) {
    url += `&transaction_id=${currentTransactionId}`;
  }
  if (q) {
    url += `&q=${encodeURIComponent(q)}`;
    if (cols) {
      url += `&cols=${encodeURIComponent(cols)}`;
    }
  }
  if (filterStr) {
    url += `&filters=${encodeURIComponent(filterStr)}`;
  }

  try {
    const res = await fetch(url);
    const result = await res.json();

    const fetchTime = (performance.now() - startTime).toFixed(1);

    if (result.data.length < pageLimit) {
      hasMoreData = false;
    }

    // Render rowData depending on View Mode
    if (viewMode === 'infinite') {
      if (resetSkip || currentSkip === 0) {
        gridApi.setGridOption('rowData', result.data);
      } else {
        gridApi.applyTransaction({ add: result.data });
      }
    } else {
      gridApi.setGridOption('rowData', result.data);
    }
    updateGridSortState();

    // Update Counts (Zero-lag counter concept)
    updateLoadedCount();
    totalRowsCount.textContent = `Matches: ${result.total}`;

    // Update Pagination UI
    updatePaginationUI(result.total);

    performanceLog.textContent = `Loaded ${result.data.length} rows in ${fetchTime}ms`;

    // Save to Cache
    if (viewMode !== 'infinite') {
      pageCache.set(currentSkip, { data: result.data, total: result.total });
    }

    isLoadingMore = false;
  } catch (err) {
    console.error('Failed to fetch data', err);
    performanceLog.textContent = 'Data fetch failed';
    isLoadingMore = false;
  }
}

// Ensure that the cell data structure exists as an object: { value, is_overwrite, sources, updated_by }
function ensureCellObject(dataObj, colId) {
  if (!dataObj) return;
  if (!dataObj.data) dataObj.data = {};
  
  const cell = dataObj.data[colId];
  if (typeof cell !== 'object' || cell === null) {
    // If it's a primitive (like string or number), wrap it in the expected CellData object format
    dataObj.data[colId] = {
      value: cell !== undefined ? cell : '',
      is_overwrite: false,
      sources: {},
      updated_by: 'system'
    };
  }
}

// Render grid layout using AG-Grid Core
// Helper to build column definitions dynamically based on schema
function buildColumnDefs() {
  // Build Column Definitions dynamically based on schema
  const columnDefs = currentColumns.map((col, index) => {
    const isSystem = ['created_at', 'updated_at', 'row_id', 'id', 'updated_by'].includes(col);
    const colTypes = currentColumnTypes || {};
    const colType = colTypes[col] || 'string';

    // 헤더명에 비즈니스 키 / 조합 소스 컬럼 아이콘 표시
    let headerLabel = col.toUpperCase();
    if (col === currentBusinessKey) {
      headerLabel = `${headerLabel}🗝️`;
    } else if (currentCompositeKeySources.includes(col)) {
      headerLabel = `${headerLabel}*`;
    }

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
      // Handle the nested structure of CellData: value inside data.col.value
      valueGetter: (params) => {
        if (col === 'row_id') return params.data.row_id;
        if (col === 'created_at') return params.data.created_at;
        if (col === 'updated_at') return params.data.updated_at;

        const cell = params.data.data?.[col];
        let val = '';
        if (cell && typeof cell === 'object') {
          val = cell.value !== undefined ? cell.value : '';
        } else {
          val = cell !== undefined ? cell : '';
        }

        if (colType === 'number' && val !== '' && val !== null && val !== undefined) {
          const parsed = Number(val);
          if (!isNaN(parsed)) {
            return parsed;
          }
        }
        return val;
      },
      // Essential for writing back to nested objects
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
        if (!txModeActive) {
          params.data.data[col].is_overwrite = true; // Mark as modified
        }
        return true;
      },
      // Styling rules
      cellClassRules: {
        'cell-system-readonly': () => isSystem,
        // Highlight dirty staged edits in dashed border
        'cell-dirty-tx': (params) => {
          if (isSystem) return false;
          if (!params.data) return false;
          const key = `${params.data.row_id}_${col}`;
          return pendingTxEdits.hasOwnProperty(key);
        },
        // Highlight cells modified by users in orange (matches PyQt Client styling)
        'cell-overwrite': (params) => {
          if (isSystem) return false;
          if (!params.data) return false;
          const key = `${params.data.row_id}_${col}`;
          if (pendingTxEdits.hasOwnProperty(key)) return false;
          const cell = params.data.data?.[col];
          return cell?.is_overwrite === true;
        },
        // Highlight selected range cell-by-cell dynamically
        'custom-range-selected': (params) => {
          return isCellInRange(params.node.rowIndex, col);
        }
      }
    };

    if (colType === 'number') {
      colDef.cellEditor = 'agNumberCellEditor';
    }

    // Style system columns slightly differently
    if (isSystem) {
      colDef.cellClass = 'cell-system-readonly';
    }

    return colDef;
  });

  // Prepend Row Number Column (Sequential 1,2,3,4...)
  columnDefs.unshift({
    headerName: '#',
    headerTooltip: 'Row Number',
    valueGetter: (params) => {
      const skip = (viewMode === 'pagination' && !allDataLoaded) ? currentSkip : 0;
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

// Render grid layout using AG-Grid Core (Updates columnDefs & rowData dynamically if instance exists)
function renderGrid(initialRows) {
  const columnDefs = buildColumnDefs();

  if (gridApi) {
    console.log('[Grid] Swapping grid options dynamically (columnDefs & rowData)...');
    gridApi.setGridOption('columnDefs', columnDefs);
    gridApi.setGridOption('rowData', initialRows);

    // Re-cache column ID to index map
    colIdToIndexMap = {};
    gridApi.getColumns().forEach((c, idx) => {
      colIdToIndexMap[c.getColId()] = idx;
    });

    updateGridSortState();
    return;
  }

  const gridDiv = document.querySelector('#myGrid');

  // Grid Configurations
  const gridOptions = {
    theme: 'legacy',
    columnDefs: columnDefs,
    rowData: initialRows,
    enableBrowserTooltips: true,
    suppressSortOnDataChange: true,
    getRowId: (params) => params.data?.row_id || params.data?.id, // Robust fallback
    defaultColDef: {
      width: 150,
      minWidth: 100,
      floatingFilter: true, // Display inline search box under each column header
      suppressKeyboardEvent: (params) => {
        const event = params.event;
        const key = event.key;

        // Ctrl + Enter during cell editing triggers bulk update for selected range
        if (params.editing && event.ctrlKey && key === 'Enter') {
          event.preventDefault();
          const editors = params.api.getCellEditorInstances();
          if (editors && editors.length > 0) {
            const editingValue = editors[0].getValue();
            params.api.stopEditing(true); // stopEditing(true) will cancel editor UI and save the value locally
            applyValueToSelectedRange(editingValue);
          }
          return true;
        }

        // Prevent Delete and Backspace from clearing cell content unless editing
        if (!params.editing && (key === 'Delete' || key === 'Backspace')) {
          return true;
        }
        return false;
      }
    },
    // Row selection configs
    rowSelection: 'multiple',
    onFilterChanged: () => {
      // Reload from skip = 0 when column filters change
      fetchData(true);
    },
    // Event: Selection/Focused cell change -> load History
    onCellFocused: (event) => {
      if (!event.column || event.rowIndex === null || event.rowIndex === undefined) return;
      const rowNode = event.api.getDisplayedRowAtIndex(event.rowIndex);
      if (!rowNode || !rowNode.data) return;

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

      selectedCell = { rowId, colId, value: val, rowIndex: event.rowIndex };
      updateSelectedCellUI();
      if (activeHistoryTab !== 'global') {
        loadHistory();
      }
    },

    // Feature 1: Cell Editing
    onCellValueChanged: async (event) => {
      await handleCellEdit(event);
    },
    // Feature 2: Custom context menu trigger on cell right-click
    onCellContextMenu: (event) => {
      event.event.preventDefault();
      if (!event.node || !event.node.data) return;

      const colId = event.column.getId();
      const rowId = event.node.data.row_id;
      const val = event.value;
      const rowIndex = event.node.rowIndex;

      // If right-clicked cell is outside current drag selection range, clear it
      if (dragStartCell && dragEndCell && !isCellInRange(rowIndex, colId)) {
        clearRangeSelection();
      }

      selectedCell = { rowId, colId, value: val, rowIndex };
      updateSelectedCellUI();

      // Only change node selection if range selection is not active
      if (!dragStartCell || !dragEndCell) {
        event.node.setSelected(true, true);
      }

      // Position and show custom menu
      contextMenu.style.left = `${event.event.clientX}px`;
      contextMenu.style.top = `${event.event.clientY}px`;
      contextMenu.style.display = 'block';
    },
    // infinite scroll body scroll listener
    onBodyScroll: (event) => {
      if (viewMode !== 'infinite') return;
      if (isLoadingMore || !hasMoreData || allDataLoaded) return;

      const viewport = document.querySelector('.ag-body-viewport');
      if (viewport) {
        const threshold = 150; // px
        const nearBottom = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight < threshold;
        if (nearBottom) {
          currentSkip += pageLimit;
          fetchData(false);
        }
      }
    }
  };

  gridApi = createGrid(gridDiv, gridOptions);

  // Cache column ID to index map to avoid getColumns().map() during cell rendering (O(1) lookup)
  colIdToIndexMap = {};
  gridApi.getColumns().forEach((c, idx) => {
    colIdToIndexMap[c.getColId()] = idx;
  });

  updateGridSortState();
}

// Update selected cell meta panel
function updateSelectedCellUI() {
  if (!selectedCell) {
    selectedCellInfo.innerHTML = 'Select a cell to view history';
    return;
  }

  const isSystem = ['created_at', 'updated_at', 'row_id'].includes(selectedCell.colId);
  selectedCellInfo.innerHTML = `
    <div><strong>Row ID:</strong> <span style="color:var(--color-secondary)">${selectedCell.rowId}</span></div>
    <div><strong>Column:</strong> <span style="color:var(--color-primary)">${selectedCell.colId.toUpperCase()}</span></div>
    <div><strong>Current Value:</strong> <code>${selectedCell.value !== null ? selectedCell.value : 'NULL'}</code></div>
    ${isSystem ? '<div style="color:var(--text-dim);margin-top:4px;font-style:italic">Read-only System Column</div>' : ''}
  `;
}

// Feature 1: Handle inline editing updates to DB
async function handleCellEdit(event) {
  const { data, colDef, newValue, oldValue } = event;
  const colId = colDef.field;
  const rowId = data.row_id;

  if (newValue === oldValue) return;

  // 이전 상태 복구를 위해 저장
  const oldCell = data.data?.[colId];
  const oldIsOverwrite = oldCell ? oldCell.is_overwrite : false;

  // --- 타입 검사 및 변환 추가 ---
  let finalValue = newValue;
  const colTypes = currentColumnTypes || {};
  const colType = colTypes[colId] || 'string';
  if (colType === 'number') {
    if (newValue === '' || newValue === null || newValue === undefined) {
      finalValue = null;
    } else {
      const parsedVal = Number(newValue);
      if (isNaN(parsedVal)) {
        alert(`컬럼 '${colId}'의 값 '${newValue}'은(는) 올바른 숫자 형식이 아닙니다.`);
        // Rollback grid value & overwrite status
        const latestNode = gridApi.getRowNode(rowId);
        const latestData = latestNode ? latestNode.data : data;
        if (latestData) {
          ensureCellObject(latestData, colId);
          latestData.data[colId].value = oldValue;
          latestData.data[colId].is_overwrite = oldIsOverwrite;
        }
        gridApi.refreshCells({ rowNodes: [latestNode].filter(Boolean), columns: [colId], force: true });
        performanceLog.textContent = '❌ Invalid number format';
        return;
      }
      finalValue = parsedVal;
    }
  }

  // Intercept and stage if Tx Mode is active
  if (txModeActive) {
    const key = `${rowId}_${colId}`;
    if (!pendingTxEdits[key]) {
      pendingTxEdits[key] = {
        rowId,
        colId,
        newValue: finalValue,
        oldValue: oldValue,
        oldIsOverwrite: oldIsOverwrite,
        data: data
      };
    } else {
      pendingTxEdits[key].newValue = finalValue;
    }

    const latestNode = gridApi.getRowNode(rowId);
    const latestData = latestNode ? latestNode.data : data;
    if (latestData) {
      ensureCellObject(latestData, colId);
      latestData.data[colId].value = finalValue;
    }

    updateTxModeUI();
    gridApi.refreshCells({ rowNodes: [latestNode].filter(Boolean), columns: [colId], force: true });
    return;
  }

  performanceLog.textContent = 'Saving edit...';
  const editStartTime = performance.now();

  // API body payload mapping to GeneralUpdateBatch
  const payload = {
    updates: [
      {
        row_id: rowId,
        updates: {
          [colId]: finalValue
        },
        source_name: 'user',
        updated_by: CURRENT_USER
      }
    ],
    silent: false
  };

  try {
    const res = await fetch(`${API_BASE}/tables/${currentTable}/data/updates`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      pageCache.clear();
      const result = await res.json();
      const saveTime = (performance.now() - editStartTime).toFixed(1);
      performanceLog.textContent = `Saved in ${saveTime}ms (${result.change_count} cell updated)`;

      // Safeguard against race conditions: Instead of applyTransaction (which resets all columns of the row to the passed reference),
      // we only modify the edited cell's properties in the latest data object and trigger refreshCells for that specific column.
      const latestNode = gridApi.getRowNode(rowId);
      const latestData = latestNode ? latestNode.data : data;

      ensureCellObject(latestData, colId);
      latestData.data[colId].value = finalValue;
      latestData.data[colId].is_overwrite = true;

      // Update updated_at timestamp locally to trigger sort update
      latestData.updated_at = getLocalTimeString();

      // Only refresh the edited cell and updated_at to prevent overwriting other cells (like business keys) before/after WebSocket sync.
      gridApi.refreshCells({
        rowNodes: [latestNode].filter(Boolean),
        columns: [colId, 'updated_at'],
        force: true
      });

      // Refresh current focused cell UI if active
      if (selectedCell && selectedCell.rowId === rowId && selectedCell.colId === colId) {
        selectedCell.value = finalValue;
        updateSelectedCellUI();
      }

      // History updates will be handled by the WebSocket stream
    } else {
      const errData = await res.json().catch(() => ({}));
      const errMsg = errData.detail || 'Save failed';
      throw new Error(errMsg);
    }
  } catch (err) {
    console.error('Cell update failed', err);
    alert(`수정 사항 저장 실패: ${err.message}`);
    performanceLog.textContent = '❌ Edit failed to save';

    // Rollback grid value & overwrite status
    const latestNode = gridApi.getRowNode(rowId);
    const latestData = latestNode ? latestNode.data : data;
    if (latestData) {
      ensureCellObject(latestData, colId);
      latestData.data[colId].value = oldValue;
      latestData.data[colId].is_overwrite = oldIsOverwrite;
    }
    gridApi.refreshCells({ rowNodes: [latestNode].filter(Boolean), columns: [colId], force: true });
  }
}

// Initialize Real-time synchronization via WebSocket
function initWebSocket() {
  if (ws) {
    try {
      ws.onopen = null;
      ws.onclose = null;
      ws.onerror = null;
      ws.onmessage = null;
      ws.close();
    } catch (e) { }
    ws = null;
  }

  ws = new WebSocket(WS_URL);

  ws.onopen = async () => {
    wsStatus.textContent = 'WS: CONNECTED';
    wsStatus.className = 'status-badge online';
    document.querySelector('.status-ws').classList.add('active');
    wsReconnectDelay = 1000; // Reset backoff delay on successful connection
    console.log('[WebSocket] Connected successfully. Syncing API health status...');

    // API 복구 감지 및 동기화 수행
    await checkServerHealth();

    // API가 살아있고 테이블 목록이 비어있다면 로드
    const tableSelectedVal = tableSelect?.value;
    if (!tableSelectedVal) {
      await loadTables();
    } else if (currentTable) {
      // 오프라인 동안 유실된 데이터 동기화를 위해 현재 테이블 데이터 리로드
      fetchData(true);
    }
  };

  ws.onclose = () => {
    wsStatus.textContent = 'WS: DISCONNECTED';
    wsStatus.className = 'status-badge offline';
    document.querySelector('.status-ws').classList.remove('active');

    console.log(`[WebSocket] Connection closed. Reconnecting in ${wsReconnectDelay}ms...`);
    setTimeout(initWebSocket, wsReconnectDelay);

    // Exponential backoff: double the delay up to 30 seconds
    wsReconnectDelay = Math.min(wsReconnectDelay * 2, 30000);
  };

  ws.onerror = (err) => {
    console.error('WebSocket error', err);
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      handleWebSocketMessage(msg);
    } catch (err) {
      console.error('WebSocket parsing error', err);
    }
  };
}

// Feature 2: WebSocket message processing for Real-time delta sync
function handleWebSocketMessage(msg) {
  if (msg.event === 'file_ingestion_progress') {
    showIngestionProgress(
      msg.table_name,
      msg.filename,
      msg.progress,
      msg.processed_rows,
      msg.total_rows
    );
    return;
  }

  if (msg.event === 'file_ingestion_completed') {
    const status = msg.status || 'SUCCESS';
    const message = msg.message || '파일 처리가 완료되었습니다.';
    showToast(message, status === 'SUCCESS' ? 'success' : 'error');

    // Finish floating progress bar
    finishIngestionProgress(msg.table_name, msg.filename, status, msg.error_msg);

    if (msg.table_name === currentTable) {
      pageCache.clear();
      fetchData(true);
      triggerHistoryReloadDebounced();
    }
    return;
  }

  // 1. Process and append audit logs to local history cache first (independent of currentTable check, especially for global history)
  const createdLogs = msg.created_logs || [];
  if (createdLogs.length > 0) {
    createdLogs.forEach(log => {
      // For non-global tabs ('cell' or 'row'), only process if the log belongs to the current table
      if (activeHistoryTab !== 'global' && log.table_name !== currentTable) {
        return;
      }

      // Update currently focused cell UI if it matches the log
      if (selectedCell && log.row_id === selectedCell.rowId && log.column_name === selectedCell.colId) {
        selectedCell.value = log.new_value;
        updateSelectedCellUI();
      }

      appendHistoryLocally(log, false);
    });
  }

  // 2. Perform table-specific data/grid updates
  if (msg.table_name !== currentTable) return;
  if (!gridApi) return;

  const event = msg.event;

  if (event === 'batch_row_create') {
    const items = msg.items || [];
    if (items.length > 0) {
      updatePageCacheOnUpsert(items);
      const nowStr = getLocalTimeString();
      const normalizedItems = items.map(item => ({
        ...item,
        created_at: item.created_at || nowStr,
        updated_at: item.updated_at || nowStr
      }));
      gridApi.applyTransaction({ add: normalizedItems });
      gridApi.refreshCells({ force: true });
      updateGridSortState();
      updateLoadedCount();
      performanceLog.textContent = `⚡ Real-time created: ${items.length} rows added`;
    }
  } else if (event === 'batch_row_upsert') {
    const items = msg.items || [];
    console.log('[WebSocket Sync] batch_row_upsert items received:', items);
    updatePageCacheOnUpsert(items);
    const updatedRows = [];
    const addedRows = [];
    const flashCols = new Set();
    items.forEach(item => {
      const rowId = item.row_id;
      const rowNode = gridApi.getRowNode(rowId);

      if (rowNode) {
        console.log(`[WebSocket Sync] Merging row ${rowId}. Old data pkg_id:`, rowNode.data?.data?.pkg_id?.value, 'New item data pkg_id:', item.data?.pkg_id?.value);
        // Row exists in client cache -> MERGE logic
        const oldRowData = rowNode.data;
        const newRowData = {
          ...oldRowData,
          created_at: item.created_at || oldRowData.created_at,
          updated_at: item.updated_at || oldRowData.updated_at,
          data: {
            ...oldRowData.data,
            ...item.data
          }
        };

        updatedRows.push(newRowData);

        // Track which columns changed for flash cells animation
        if (item.data) {
          Object.keys(item.data).forEach(col => flashCols.add(col));
        }
      } else {
        // Row doesn't exist -> Insert it
        const nowStr = getLocalTimeString();
        const newItem = {
          ...item,
          created_at: item.created_at || nowStr,
          updated_at: item.updated_at || nowStr
        };
        addedRows.push(newItem);
        if (item.data) {
          Object.keys(item.data).forEach(col => flashCols.add(col));
        }
      }
    });

    if (updatedRows.length > 0 || addedRows.length > 0) {
      // High-performance batch transaction update in AG-Grid
      const res = gridApi.applyTransaction({
        update: updatedRows,
        add: addedRows
      });
      console.log('[WebSocket Sync] applyTransaction output result:', {
        updatedCount: res.update?.length || 0,
        addedCount: res.add?.length || 0,
        failedCount: res.remove?.length || 0
      });

      // Trigger AG-Grid visual cell flashing micro-animation
      const allTargetRows = [...updatedRows, ...addedRows];
      const flashNodes = allTargetRows.map(r => gridApi.getRowNode(r.row_id)).filter(Boolean);
      const flashColIds = Array.from(flashCols);

      if (flashNodes.length > 0 && flashColIds.length > 0) {
        gridApi.flashCells({
          rowNodes: flashNodes,
          columns: flashColIds,
          flashDelay: 1000
        });
      }

      // [강력한 화면 동기화] refreshCells 뿐만 아니라 redrawRows를 추가로 호출하여
      // AG-Grid가 강제 캐시 우회하고 완전히 해당 행들을 처음부터 다시 그리도록 지시
      if (flashNodes.length > 0) {
        gridApi.redrawRows({ rowNodes: flashNodes });
      }
      gridApi.refreshCells({ force: true });
      updateGridSortState();
      updateLoadedCount();

      performanceLog.textContent = `⚡ Real-time synchronized: ${updatedRows.length} rows updated`;
    }
  } else if (event === 'batch_row_delete') {
    const rowIds = msg.row_ids || [];
    updatePageCacheOnDelete(rowIds);
    const deleteTx = rowIds.map(rid => ({ row_id: rid }));

    gridApi.applyTransaction({ remove: deleteTx });

    updateLoadedCount();
    performanceLog.textContent = `🗑️ Real-time deleted: ${rowIds.length} rows removed`;

    if (selectedCell && rowIds.includes(selectedCell.rowId)) {
      selectedCell = null;
      updateSelectedCellUI();
      timeline.innerHTML = '<li class="timeline-empty">Selected row deleted.</li>';
    }
  } else if (event === 'batch_refresh_required') {
    pageCache.clear();
    fetchData(true);
    triggerHistoryReloadDebounced();
  }
}


// Feature 3: Load audit log history from API
async function loadHistory() {
  if (activeHistoryTab === 'global') {
    timeline.innerHTML = '<li class="timeline-empty">Loading global history...</li>';
    try {
      const res = await fetch(`${API_BASE}/audit_logs/recent?limit_groups=100`);
      const logs = await res.json();
      globalHistoryData = logs;
      renderGlobalTimeline();
    } catch (err) {
      console.error('Failed to load global history', err);
      timeline.innerHTML = '<li class="timeline-empty" style="color:var(--color-danger)">Failed to load global history log</li>';
    }
    return;
  }

  if (!selectedCell) {
    timeline.innerHTML = '<li class="timeline-empty">Select a cell to view history</li>';
    return;
  }

  timeline.innerHTML = '<li class="timeline-empty">Loading history...</li>';

  const { rowId, colId } = selectedCell;
  let url = `${API_BASE}/tables/${currentTable}/rows/${rowId}/history`;

  if (activeHistoryTab === 'cell') {
    url = `${API_BASE}/tables/${currentTable}/rows/${rowId}/cells/${colId}/history`;
  }

  try {
    const res = await fetch(url);
    const logs = await res.json();
    cellRowHistoryData = logs || [];
    renderTimeline(cellRowHistoryData);
  } catch (err) {
    console.error('Failed to load history', err);
    timeline.innerHTML = '<li class="timeline-empty" style="color:var(--color-danger)">Failed to load history log</li>';
  }
}

// Helper to update client page cache in-place on real-time upsert/create events
function updatePageCacheOnUpsert(items) {
  if (!items || items.length === 0) return;
  const isSortLatest = sortLatestToggle && sortLatestToggle.checked;

  items.forEach(item => {
    let foundAnywhere = false;

    // 1. Find and merge inside cached pages
    for (const [skip, cached] of pageCache.entries()) {
      const idx = cached.data.findIndex(r => r.row_id === item.row_id);
      if (idx !== -1) {
        foundAnywhere = true;
        const oldRowData = cached.data[idx];
        cached.data[idx] = {
          ...oldRowData,
          created_at: item.created_at || oldRowData.created_at,
          updated_at: item.updated_at || oldRowData.updated_at,
          data: {
            ...oldRowData.data,
            ...item.data
          }
        };
      }
    }

    // 2. If not found in any page (new row)
    if (!foundAnywhere) {
      for (const [skip, cached] of pageCache.entries()) {
        cached.total += 1;

        // Prepend to skip=0 if sorted by updated_at descending
        if (skip === 0 && isSortLatest) {
          const nowStr = getLocalTimeString();
          const newItem = {
            ...item,
            created_at: item.created_at || nowStr,
            updated_at: item.updated_at || nowStr
          };

          if (!cached.data.some(r => r.row_id === newItem.row_id)) {
            cached.data.unshift(newItem);
            if (cached.data.length > pageLimit) {
              cached.data.pop();
            }
          }
        }
      }
    }
  });
}

// Helper to remove items from client page cache in-place on delete events
function updatePageCacheOnDelete(rowIds) {
  if (!rowIds || rowIds.length === 0) return;

  rowIds.forEach(rowId => {
    for (const [skip, cached] of pageCache.entries()) {
      const originalLength = cached.data.length;
      cached.data = cached.data.filter(r => r.row_id !== rowId);

      const removedCount = originalLength - cached.data.length;
      if (removedCount > 0) {
        cached.total -= removedCount;
      } else {
        cached.total -= 1;
      }
      if (cached.total < 0) cached.total = 0;
    }
  });
}

// Create single timeline list item DOM element
function createTimelineItemDom(log) {
  const li = document.createElement('li');
  li.className = 'timeline-item';
  li.style.cursor = 'pointer';

  const isUser = log.updated_by !== 'system';
  li.classList.add(isUser ? 'user-change' : 'system-change');
  if (log.is_row_deleted) {
    li.classList.add('deleted-row-log');
  }

  const isCurrentTx = log.transaction_id && log.transaction_id === currentTransactionId;
  if (isCurrentTx) {
    li.classList.add('active-tx-log');
  }

  const dateStr = new Date(log.timestamp).toLocaleString();

  li.innerHTML = `
    <div class="timeline-time">${dateStr}</div>
    <div class="timeline-card">
      <div class="timeline-user">
        <span class="user-tag">${log.updated_by}</span>
        <span class="source-tag">${log.source_name}</span>
      </div>
      <div class="timeline-changes">
        <div class="change-detail">
          <span class="change-field">${log.column_name}</span>
          <div class="change-values">
            <span class="val-old">${formatVal(log.old_value, true)}</span>
            <span class="val-arrow">→</span>
            <span class="val-new">${formatVal(log.new_value, false)}</span>
          </div>
        </div>
      </div>
      ${log.transaction_id ? `<div class="tx-tag" data-tx-id="${log.transaction_id}">Tx: ${log.transaction_id.slice(0, 8)}... <span class="filter-tx-btn" data-tx-id="${log.transaction_id}" title="Filter table by this transaction">🔍</span></div>` : ''}
    </div>
  `;

  li.addEventListener('click', (e) => {
    if (e.target.closest('.filter-tx-btn')) {
      e.stopPropagation();
      const txId = e.target.closest('.filter-tx-btn').dataset.txId;
      setTransactionFilter(txId);
    } else {
      navigateToLog(log);
    }
  });

  return li;
}

// Create global timeline group list item DOM element
function createGlobalTimelineItemDom(group) {
  const txId = group.transaction_id;
  const isSummary = group.total_count > 1;
  const baseLog = group.logs[0];
  if (!baseLog) return null;

  const li = document.createElement('li');
  li.className = 'timeline-item';
  if (txId) {
    li.dataset.txId = txId;
  }

  const isCurrentTx = txId && txId === currentTransactionId;
  if (isCurrentTx) {
    li.classList.add('active-tx-log');
  }

  const user = baseLog.updated_by || 'system';
  const isUser = user !== 'system';
  li.classList.add(isUser ? 'user-change' : 'system-change');

  const dateStr = new Date(baseLog.timestamp).toLocaleString();

  let displayTitle = '';
  let colorClass = '';

  if (isSummary) {
    const allDeletes = group.logs.every(log => log.column_name === 'DELETE');
    const allCreates = group.logs.every(log => log.column_name === 'CREATE');

    if (allDeletes) {
      displayTitle = `🗑️ [${user}] 님 | ${baseLog.table_name} | ${group.total_count}행 삭제`;
      colorClass = 'color-delete';
    } else if (allCreates) {
      displayTitle = `🆕 [${user}] 님 | ${baseLog.table_name} | ${group.total_count}행 생성`;
      colorClass = 'color-create';
    } else {
      displayTitle = `📦 [${user}] 님 | ${baseLog.table_name} | ${group.total_count}건 변경`;
      colorClass = baseLog.is_row_deleted ? 'color-deleted-row' : 'color-summary';
    }
  } else {
    const targetId = baseLog.business_key ? (baseLog.business_key.length > 10 ? baseLog.business_key.slice(0, 10) + '...' : baseLog.business_key) : baseLog.row_id.slice(0, 8);
    const col = baseLog.column_name;
    if (col === 'CREATE') {
      displayTitle = `🆕 [${user}] 님이 ${baseLog.table_name} (${targetId}) 생성`;
      colorClass = 'color-create';
    } else if (col === 'DELETE') {
      displayTitle = `🗑️ [${user}] 님이 ${baseLog.table_name} (${targetId}) 삭제`;
      colorClass = 'color-delete';
    } else if (col === 'ROW_UPDATE') {
      displayTitle = `🤖 [${user}] 님이 ${baseLog.table_name} (${targetId}) 자동 업데이트`;
      colorClass = baseLog.is_row_deleted ? 'color-deleted-row' : 'color-auto';
    } else {
      displayTitle = `🔄 [${user}] 님이 ${baseLog.table_name} (${targetId}) 의 ${col} 수정`;
      colorClass = baseLog.is_row_deleted ? 'color-deleted-row' : (baseLog.source_name === 'user' ? 'color-user-edit' : 'color-parser-edit');
    }
  }

  if (baseLog.is_row_deleted) {
    displayTitle = `❌ [삭제됨] ` + displayTitle;
  }

  const summaryColsText = group.summary_columns && group.summary_columns.length > 0
    ? (group.summary_columns.length > 5 ? group.summary_columns.slice(0, 5).join(', ') + ` 외 ${group.summary_columns.length - 5}건` : group.summary_columns.join(', '))
    : '';

  li.innerHTML = `
    <div class="timeline-time">${dateStr}</div>
    <div class="timeline-card ${colorClass} ${isSummary ? 'summary-card' : ''}">
      <div class="timeline-user">
        <span class="user-tag">${user}</span>
        <span class="source-tag">${baseLog.source_name || 'system'}</span>
      </div>
      <div class="timeline-changes">
        <div class="change-detail">
          <span class="change-title-text">${displayTitle}</span>
          ${summaryColsText ? `<div class="summary-columns-list">${summaryColsText}</div>` : ''}
          ${!isSummary ? `
          <div class="change-values">
            <span class="val-old">${formatVal(baseLog.old_value, true)}</span>
            <span class="val-arrow">→</span>
            <span class="val-new">${formatVal(baseLog.new_value, false)}</span>
          </div>` : ''}
        </div>
      </div>
      ${txId ? `<div class="tx-tag" data-tx-id="${txId}">Tx: ${txId.slice(0, 8)}... <span class="filter-tx-btn" data-tx-id="${txId}" title="Filter table by this transaction">🔍</span> ${isSummary ? '<span class="expand-indicator">▶</span>' : ''}</div>` : ''}
    </div>
    ${isSummary ? `<div class="tx-details-container" style="display: none;"></div>` : ''}
  `;

  if (isSummary) {
    const card = li.querySelector('.timeline-card');
    const detailsContainer = li.querySelector('.tx-details-container');
    const indicator = li.querySelector('.expand-indicator');

    const toggleExpand = async () => {
      const isExpanded = expandedTransactions.has(txId);
      if (isExpanded) {
        expandedTransactions.delete(txId);
        detailsContainer.style.display = 'none';
        indicator.style.transform = 'rotate(0deg)';
        indicator.textContent = '▶';
      } else {
        expandedTransactions.add(txId);
        detailsContainer.style.display = 'block';
        indicator.style.transform = 'rotate(90deg)';
        indicator.textContent = '▼';

        if (group.logs.length <= 1 && group.total_count > 1) {
          if (fetchingTransactions.has(txId)) return;
          fetchingTransactions.add(txId);
          detailsContainer.innerHTML = '<div class="loading-subdetails">Loading details...</div>';

          try {
            const res = await fetch(`${API_BASE}/audit_logs/transaction/${txId}`);
            const txDetail = await res.json();
            group.logs = txDetail.logs;
            fetchingTransactions.delete(txId);
            renderSubDetails(detailsContainer, group.logs);
          } catch (err) {
            console.error('Failed to load transaction details', err);
            detailsContainer.innerHTML = '<div class="error-subdetails">Failed to load details.</div>';
            fetchingTransactions.delete(txId);
          }
        } else {
          renderSubDetails(detailsContainer, group.logs);
        }
      }
    };

    card.addEventListener('click', (e) => {
      if (e.target.closest('.filter-tx-btn')) {
        e.stopPropagation();
        const targetTxId = e.target.closest('.filter-tx-btn').dataset.txId;
        setTransactionFilter(targetTxId);
      } else if (e.target.closest('.tx-tag') || e.target.closest('.expand-indicator')) {
        toggleExpand();
      } else {
        if (group.logs && group.logs.length > 0 && group.logs[0].row_id !== '_BATCH_') {
          navigateToLog(group.logs[0]);
        }
      }
    });

    card.addEventListener('dblclick', () => {
      toggleExpand();
    });
  } else {
    const card = li.querySelector('.timeline-card');
    card.addEventListener('click', (e) => {
      if (e.target.closest('.filter-tx-btn')) {
        e.stopPropagation();
        const targetTxId = e.target.closest('.filter-tx-btn').dataset.txId;
        setTransactionFilter(targetTxId);
      } else {
        if (baseLog.row_id !== '_BATCH_') {
          navigateToLog(baseLog);
        } else {
          performanceLog.textContent = '⚠️ Batch operations do not support cell positioning';
        }
      }
    });
  }

  return li;
}

// Prepend single item incrementally to cell/row history tab
function renderTimelineIncremental(log) {
  if (activeHistoryTab === 'cell') {
    if (!selectedCell || selectedCell.rowId !== log.row_id || selectedCell.colId !== log.column_name) return;
  } else if (activeHistoryTab === 'row') {
    if (!selectedCell || selectedCell.rowId !== log.row_id) return;
  } else {
    return;
  }

  const emptyLi = timeline.querySelector('.timeline-empty');
  if (emptyLi) {
    emptyLi.remove();
  }

  const li = createTimelineItemDom(log);
  timeline.insertBefore(li, timeline.firstChild);
}

// Prepend or update item incrementally to global history tab
function renderGlobalTimelineIncremental(log) {
  if (activeHistoryTab !== 'global') return;

  const emptyLi = timeline.querySelector('.timeline-empty');
  if (emptyLi) {
    emptyLi.remove();
  }

  const group = globalHistoryData.find(g => g.transaction_id === log.transaction_id);
  if (!group) return;

  let oldLi = null;
  if (log.transaction_id) {
    oldLi = timeline.querySelector(`li[data-tx-id="${log.transaction_id}"]`);
  }

  const newLi = createGlobalTimelineItemDom(group);
  if (!newLi) return;

  if (oldLi) {
    const isExpanded = expandedTransactions.has(log.transaction_id);
    if (isExpanded) {
      const detailsContainer = newLi.querySelector('.tx-details-container');
      const indicator = newLi.querySelector('.expand-indicator');
      if (detailsContainer) {
        detailsContainer.style.display = 'block';
        renderSubDetails(detailsContainer, group.logs);
      }
      if (indicator) {
        indicator.style.transform = 'rotate(90deg)';
        indicator.textContent = '▼';
      }
    }

    timeline.replaceChild(newLi, oldLi);
  } else {
    timeline.insertBefore(newLi, timeline.firstChild);
  }
}

// Render history logs in a vertical timeline UI card structure
function renderTimeline(logs) {
  timeline.innerHTML = '';

  if (!logs || logs.length === 0) {
    timeline.innerHTML = '<li class="timeline-empty">No change history recorded.</li>';
    return;
  }

  logs.forEach(log => {
    const li = createTimelineItemDom(log);
    timeline.appendChild(li);
  });
}

// Render overall table audit history logs (recent transactions)
function renderGlobalTimeline() {
  timeline.innerHTML = '';

  if (!globalHistoryData || globalHistoryData.length === 0) {
    timeline.innerHTML = '<li class="timeline-empty">No database history recorded.</li>';
    return;
  }

  globalHistoryData.forEach((group) => {
    const li = createGlobalTimelineItemDom(group);
    if (li) {
      timeline.appendChild(li);
    }
  });
}

function renderSubDetails(container, logs) {
  container.innerHTML = '';
  const ul = document.createElement('ul');
  ul.className = 'sub-timeline-list';

  logs.forEach(log => {
    const li = document.createElement('li');
    li.className = 'sub-timeline-item';

    const col = log.column_name;
    const val = formatVal(log.new_value);
    const bk = log.business_key;
    const targetId = bk ? (bk.length > 10 ? bk.slice(0, 10) + '...' : bk) : (log.row_id ? log.row_id.slice(0, 8) : '');

    let labelText = '';
    if (col === 'ROW_UPDATE') {
      labelText = `ROW_UPDATE: ${val} (ID: ${targetId})`;
    } else {
      labelText = `[${col}] ${val} (ID: ${targetId})`;
    }

    li.innerHTML = `
      <span class="sub-bullet">└</span>
      <span class="sub-log-text">${labelText}</span>
    `;

    li.addEventListener('click', (e) => {
      e.stopPropagation();
      if (log.row_id !== '_BATCH_') {
        navigateToLog(log);
      }
    });

    ul.appendChild(li);
  });

  container.appendChild(ul);
}

// Helper to get local time string in YYYY-MM-DD HH:MM:SS format
function getLocalTimeString(date = new Date()) {
  const pad = (n) => String(n).padStart(2, '0');
  const yyyy = date.getFullYear();
  const MM = pad(date.getMonth() + 1);
  const dd = pad(date.getDate());
  const hh = date.getHours();
  const mm = pad(date.getMinutes());
  const ss = pad(date.getSeconds());
  return `${yyyy}-${MM}-${dd} ${hh}:${mm}:${ss}`;
}

// Helper to format values
function formatVal(v, isOld = false) {
  if (v === null || v === undefined || v === '') {
    return isOld ? '비어있음' : '삭제됨';
  }
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

// Debounced History Loader
let historyDebounceTimeout = null;
function triggerHistoryReloadDebounced() {
  clearTimeout(historyDebounceTimeout);
  historyDebounceTimeout = setTimeout(() => {
    loadHistory();
  }, 300);
}

// Feature 3: Append single history log locally to prevent full API refresh on cell change
function appendHistoryLocally(log, skipRender = false) {
  if (!log) return;

  if (activeHistoryTab === 'global') {
    const existingGroup = globalHistoryData.find(g => g.transaction_id === log.transaction_id);
    if (existingGroup) {
      const isDuplicate = existingGroup.logs.some(l => {
        if (log.id && l.id && log.id === l.id) return true;
        const lTime = l.timestamp ? new Date(l.timestamp).getTime() : 0;
        const logTime = log.timestamp ? new Date(log.timestamp).getTime() : 0;
        return lTime === logTime && l.column_name === log.column_name && l.row_id === log.row_id;
      });
      if (!isDuplicate) {
        existingGroup.logs.unshift(log);
        existingGroup.total_count += 1;
        if (!existingGroup.summary_columns) {
          existingGroup.summary_columns = [];
        }
        if (log.column_name && !existingGroup.summary_columns.includes(log.column_name)) {
          existingGroup.summary_columns.push(log.column_name);
        }
      }
    } else {
      globalHistoryData.unshift({
        transaction_id: log.transaction_id,
        total_count: 1,
        summary_columns: log.column_name ? [log.column_name] : [],
        logs: [log]
      });
    }
    if (!skipRender) {
      renderGlobalTimelineIncremental(log);
    }
    return;
  }

  // Non-global tabs ('cell' or 'row')
  if (!selectedCell) return;

  if (activeHistoryTab === 'cell') {
    if (selectedCell.rowId !== log.row_id || selectedCell.colId !== log.column_name) return;
  } else if (activeHistoryTab === 'row') {
    if (selectedCell.rowId !== log.row_id) return;
  }

  // Store in cache if not duplicate
  const isDuplicate = cellRowHistoryData.some(l => {
    if (log.id && l.id && log.id === l.id) return true;
    const lTime = l.timestamp ? new Date(l.timestamp).getTime() : 0;
    const logTime = log.timestamp ? new Date(log.timestamp).getTime() : 0;
    return lTime === logTime && l.column_name === log.column_name && l.row_id === log.row_id;
  });
  if (!isDuplicate) {
    cellRowHistoryData.unshift(log);
  }

  if (!skipRender) {
    renderTimelineIncremental(log);
  }
}

// Range selection helper functions
function isCellInRange(rowIndex, colId) {
  const key = `${rowIndex}_${colId}`;
  if (selectedCellsMap[key]) return true;

  if (!dragStartCell || !dragEndCell) return false;
  if (!gridApi) return false;

  const startColIdx = colIdToIndexMap[dragStartCell.colId];
  const endColIdx = colIdToIndexMap[dragEndCell.colId];
  const colIdx = colIdToIndexMap[colId];

  if (startColIdx === undefined || endColIdx === undefined || colIdx === undefined) return false;

  const minColIdx = Math.min(startColIdx, endColIdx);
  const maxColIdx = Math.max(startColIdx, endColIdx);
  const minRowIdx = Math.min(dragStartCell.rowIndex, dragEndCell.rowIndex);
  const maxRowIdx = Math.max(dragStartCell.rowIndex, dragEndCell.rowIndex);

  return rowIndex >= minRowIdx && rowIndex <= maxRowIdx && colIdx >= minColIdx && colIdx <= maxColIdx;
}

function refreshRange(api, startCell, endCell) {
  if (!startCell || !endCell || !api) return;
  const startRow = startCell.rowIndex;
  const endRow = endCell.rowIndex;
  const minRow = Math.min(startRow, endRow);
  const maxRow = Math.max(startRow, endRow);

  const rowNodes = [];
  for (let r = minRow; r <= maxRow; r++) {
    const node = api.getDisplayedRowAtIndex(r);
    if (node) rowNodes.push(node);
  }

  const startColIdx = colIdToIndexMap[startCell.colId];
  const endColIdx = colIdToIndexMap[endCell.colId];
  if (startColIdx === undefined || endColIdx === undefined) return;

  const minColIdx = Math.min(startColIdx, endColIdx);
  const maxColIdx = Math.max(startColIdx, endColIdx);
  const allColumns = api.getColumns();
  const columns = allColumns.slice(minColIdx, maxColIdx + 1);

  api.refreshCells({ rowNodes, columns, force: true });
}

function refreshSelectedRangeDiff(api, startCell, prevEndCell, newEndCell) {
  if (!startCell || !newEndCell || !api) return;

  const startRow = startCell.rowIndex;
  const newEndRow = newEndCell.rowIndex;
  const prevEndRow = prevEndCell ? prevEndCell.rowIndex : newEndRow;

  const minRow = Math.min(startRow, prevEndRow, newEndRow);
  const maxRow = Math.max(startRow, prevEndRow, newEndRow);

  const rowNodes = [];
  for (let r = minRow; r <= maxRow; r++) {
    const node = api.getDisplayedRowAtIndex(r);
    if (node) rowNodes.push(node);
  }

  const startColIdx = colIdToIndexMap[startCell.colId];
  const newEndColIdx = colIdToIndexMap[newEndCell.colId];
  const prevEndColIdx = prevEndCell ? colIdToIndexMap[prevEndCell.colId] : newEndColIdx;

  if (startColIdx === undefined || newEndColIdx === undefined) {
    api.refreshCells({ force: true });
    return;
  }

  const minColIdx = Math.min(startColIdx, prevEndColIdx, newEndColIdx);
  const maxColIdx = Math.max(startColIdx, prevEndColIdx, newEndColIdx);

  const allColumns = api.getColumns();
  const columns = allColumns.slice(minColIdx, maxColIdx + 1);

  api.refreshCells({ rowNodes, columns, force: true });
}

function clearRangeSelection() {
  dragStartCell = null;
  dragEndCell = null;
  isDraggingRange = false;
  selectedCellsMap = {};
  if (gridApi) {
    gridApi.refreshCells({ force: true });
  }
}

// Helper to commit current drag selection to selectedCellsMap
function commitDragSelection(api) {
  if (!dragStartCell || !dragEndCell || !api) {
    return;
  }

  const allCols = api.getColumns().map(c => c.getColId());
  const startColIdx = allCols.indexOf(dragStartCell.colId);
  const endColIdx = allCols.indexOf(dragEndCell.colId);

  if (startColIdx !== -1 && endColIdx !== -1) {
    const minCol = Math.min(startColIdx, endColIdx);
    const maxCol = Math.max(startColIdx, endColIdx);
    const minRow = Math.min(dragStartCell.rowIndex, dragEndCell.rowIndex);
    const maxRow = Math.max(dragStartCell.rowIndex, dragEndCell.rowIndex);

    // Exclude helper columns (like '#' or checkbox selection columns)
    const targetCols = allCols.filter((colId, idx) => idx >= minCol && idx <= maxCol && colId !== '#' && !/^\d+$/.test(colId));

    for (let r = minRow; r <= maxRow; r++) {
      const node = api.getDisplayedRowAtIndex(r);
      if (!node || !node.data) continue;
      const rowId = node.data.row_id;

      targetCols.forEach(colId => {
        const key = `${r}_${colId}`;
        selectedCellsMap[key] = { rowIndex: r, colId, rowId };
      });
    }
  }
}

// Parse coords from native element inside AG-Grid
function getCellCoordsFromElement(el) {
  if (!el) return null;
  const cellEl = el.closest('.ag-cell');
  if (!cellEl) return null;
  const colId = cellEl.getAttribute('col-id');
  if (!colId) return null;
  
  const rowEl = el.closest('.ag-row');
  if (!rowEl) return null;
  const rowIndexStr = rowEl.getAttribute('row-index');
  if (rowIndexStr === null) return null;
  const rowIndex = parseInt(rowIndexStr, 10);
  
  return { rowIndex, colId };
}

function setupNativeGridMouseHandlers() {
  const gridContainer = document.getElementById('myGrid');
  if (!gridContainer) return;

  gridContainer.addEventListener('mousedown', (e) => {
    // Only capture left click
    if (e.button !== 0) return;

    const coords = getCellCoordsFromElement(e.target);
    if (!coords) return;
    if (coords.colId === '#') return;

    const isCtrl = e.ctrlKey || e.metaKey;
    const isShift = e.shiftKey;

    isDraggingRange = true;
    dragStartCell = { rowIndex: coords.rowIndex, colId: coords.colId };
    dragEndCell = { rowIndex: coords.rowIndex, colId: coords.colId };

    // Prevent default browser drag selection behavior to avoid swallowing mouseup
    e.preventDefault();

    if (!isCtrl && !isShift) {
      selectedCellsMap = {};
      if (gridApi) {
        gridApi.refreshCells({ force: true });
      }
    }

    if (gridApi) {
      refreshRange(gridApi, dragStartCell, dragEndCell);
    }
  });

  gridContainer.addEventListener('mousemove', (e) => {
    if (!isDraggingRange || !dragStartCell) return;

    // Safety check: if buttons state is not left-clicked, release dragging range
    if (e.buttons !== 1) {
      isDraggingRange = false;
      if (gridApi) {
        commitDragSelection(gridApi);
        gridApi.refreshCells({ force: true });
      }
      return;
    }

    const coords = getCellCoordsFromElement(e.target);
    if (!coords) return;
    if (coords.colId === '#') return;

    if (dragEndCell.rowIndex !== coords.rowIndex || dragEndCell.colId !== coords.colId) {
      const prevEnd = dragEndCell;
      dragEndCell = { rowIndex: coords.rowIndex, colId: coords.colId };

      if (gridApi) {
        try {
          refreshSelectedRangeDiff(gridApi, dragStartCell, prevEnd, dragEndCell);
        } catch (err) {
          gridApi.refreshCells({ force: true });
        }
      }
    }
  });

  // Attach global mouseup listener to document to guarantee it's committed
  document.addEventListener('mouseup', (e) => {
    if (isDraggingRange) {
      isDraggingRange = false;

      const isCtrl = e.ctrlKey || e.metaKey;
      const coords = getCellCoordsFromElement(e.target);
      
      let isSingleClick = false;
      if (dragStartCell && dragEndCell) {
        isSingleClick = (dragStartCell.rowIndex === dragEndCell.rowIndex && dragStartCell.colId === dragEndCell.colId);
      }

      if (isSingleClick && isCtrl && dragStartCell) {
        const key = `${dragStartCell.rowIndex}_${dragStartCell.colId}`;
        if (selectedCellsMap[key]) {
          delete selectedCellsMap[key];
        } else {
          const rowNode = gridApi?.getDisplayedRowAtIndex(dragStartCell.rowIndex);
          const rowId = rowNode?.data?.row_id;
          selectedCellsMap[key] = { rowIndex: dragStartCell.rowIndex, colId: dragStartCell.colId, rowId };
        }
        dragStartCell = null;
        dragEndCell = null;
      } else {
        if (gridApi) {
          commitDragSelection(gridApi);
        }
      }

      const oldStart = dragStartCell;
      const oldEnd = dragEndCell;
      dragStartCell = null;
      dragEndCell = null;

      if (gridApi) {
        if (oldStart && oldEnd) {
          refreshRange(gridApi, oldStart, oldEnd);
        }
        gridApi.refreshCells({ force: true });
      }
    }
  });
}

function getRangeSelectedTSV() {
  if (!gridApi) return '';

  let selectedCells = [];

  const allCols = gridApi.getColumns().map(c => c.getColId());

  // 1. Prioritize active drag bounds if present
  if (dragStartCell && dragEndCell) {
    const startColIdx = allCols.indexOf(dragStartCell.colId);
    const endColIdx = allCols.indexOf(dragEndCell.colId);
    if (startColIdx !== -1 && endColIdx !== -1) {
      const minCol = Math.min(startColIdx, endColIdx);
      const maxCol = Math.max(startColIdx, endColIdx);
      const minRow = Math.min(dragStartCell.rowIndex, dragEndCell.rowIndex);
      const maxRow = Math.max(dragStartCell.rowIndex, dragEndCell.rowIndex);
      
      for (let r = minRow; r <= maxRow; r++) {
        for (let c = minCol; c <= maxCol; c++) {
          selectedCells.push({ rowIndex: r, colId: allCols[c] });
        }
      }
    }
  } 
  
  // 2. Fallback: If no active drag bounds, look into selectedCellsMap
  if (selectedCells.length === 0) {
    selectedCells = Object.values(selectedCellsMap);
  }

  // 3. Fallback: If still empty, use current focused cell
  if (selectedCells.length === 0) {
    const focusedCell = gridApi.getFocusedCell();
    if (focusedCell) {
      selectedCells.push({ rowIndex: focusedCell.rowIndex, colId: focusedCell.column.getId() });
    } else {
      return '';
    }
  }

  let minRow = Infinity;
  let maxRow = -Infinity;
  let minColIdx = Infinity;
  let maxColIdx = -Infinity;

  selectedCells.forEach(cell => {
    const cIdx = allCols.indexOf(cell.colId);
    if (cIdx !== -1) {
      if (cell.rowIndex < minRow) minRow = cell.rowIndex;
      if (cell.rowIndex > maxRow) maxRow = cell.rowIndex;
      if (cIdx < minColIdx) minColIdx = cIdx;
      if (cIdx > maxColIdx) maxColIdx = cIdx;
    }
  });

  if (minRow === Infinity || minColIdx === Infinity) return '';

  // Exclude helper columns (like '#' or checkbox selection columns) to ensure clean grid output structure
  const colsToCopy = allCols.filter((colId, idx) => {
    if (idx < minColIdx || idx > maxColIdx) return false;
    if (colId === '#' || /^\d+$/.test(colId)) return false;
    return currentColumns.includes(colId) || ['row_id', 'created_at', 'updated_at'].includes(colId);
  });
  if (colsToCopy.length === 0) return '';

  let tsvRows = [];

  const toggleEl = document.getElementById('copy-header-toggle');
  const includeHeaders = toggleEl && toggleEl.checked;
  if (includeHeaders) {
    const headerRow = colsToCopy.map(colId => {
      const col = gridApi.getColumn(colId);
      if (col) {
        const colDef = col.getColDef();
        return colDef.headerName || colId;
      }
      return colId;
    });
    tsvRows.push(headerRow.join('\t'));
  }

  for (let r = minRow; r <= maxRow; r++) {
    const rowNode = gridApi.getDisplayedRowAtIndex(r);
    if (!rowNode || !rowNode.data) continue;

    let rowVals = [];
    colsToCopy.forEach(col => {
      const key = `${r}_${col}`;
      if (!selectedCellsMap[key] && (!dragStartCell || !dragEndCell || !isCellInRange(r, col))) {
        rowVals.push('');
        return;
      }

      let val = '';
      if (col === 'row_id') val = rowNode.data.row_id;
      else if (col === 'created_at') val = rowNode.data.created_at;
      else if (col === 'updated_at') val = rowNode.data.updated_at;
      else {
        const cell = rowNode.data.data?.[col];
        if (cell && typeof cell === 'object') {
          val = cell.value !== undefined ? cell.value : '';
        } else {
          val = cell !== undefined ? cell : '';
        }
      }
      rowVals.push(String(val).replace(/\t/g, ' ').replace(/\n/g, ' '));
    });
    tsvRows.push(rowVals.join('\t'));
  }

  return tsvRows.join('\n');
}

// Clipboard Operations (Feature: Smart Copy & Paste)
function setupClipboardHandlers() {
  // 1. Paste handler
  document.addEventListener('paste', async (e) => {
    if (!gridApi) return;

    const activeEl = document.activeElement;
    if (activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA' || activeEl.hasAttribute('contenteditable') || activeEl.classList.contains('ag-input-field-input'))) {
      return;
    }

    // Determine target cells from selection map or drag bounds
    let targetCells = Object.values(selectedCellsMap);
    const focusedCell = gridApi.getFocusedCell();

    if (targetCells.length === 0) {
      if (dragStartCell && dragEndCell) {
        // Fallback to drag bounds
        const allCols = gridApi.getColumns().map(c => c.getColId());
        const startColIdx = colIdToIndexMap[dragStartCell.colId];
        const endColIdx = colIdToIndexMap[dragEndCell.colId];
        if (startColIdx !== undefined && endColIdx !== undefined) {
          const minCol = Math.min(startColIdx, endColIdx);
          const maxCol = Math.max(startColIdx, endColIdx);
          const minRow = Math.min(dragStartCell.rowIndex, dragEndCell.rowIndex);
          const maxRow = Math.max(dragStartCell.rowIndex, dragEndCell.rowIndex);
          
          const targetCols = allCols.filter((_, idx) => idx >= minCol && idx <= maxCol && _ !== '#');
          for (let r = minRow; r <= maxRow; r++) {
            targetCols.forEach(colId => {
              targetCells.push({ rowIndex: r, colId });
            });
          }
        }
      } else if (focusedCell) {
        targetCells.push({ rowIndex: focusedCell.rowIndex, colId: focusedCell.column.getId() });
      }
    }

    if (targetCells.length === 0) return;

    e.preventDefault();
    const clipboardText = e.clipboardData.getData('text/plain');
    if (!clipboardText) return;

    // Parse TSV clipboard
    const rows = clipboardText.replace(/\r\n/g, '\n').split('\n').filter(r => r.length > 0);
    const parsedMatrix = rows.map(r => r.split('\t').map(c => c.trim()));
    if (parsedMatrix.length === 0) return;

    performanceLog.textContent = 'Processing paste updates...';

    const batchUpdates = [];
    const updateMapByRow = {};
    const allCols = gridApi.getColumns().map(c => c.getColId());

    try {
      const isSingleVal = (parsedMatrix.length === 1 && parsedMatrix[0].length === 1);

      if (isSingleVal) {
        // 1x1 Single value clipboard ➡️ Fill all target cells
        const val = parsedMatrix[0][0];

        targetCells.forEach(cell => {
          const { rowIndex, colId } = cell;
          const isSystem = ['created_at', 'updated_at', 'row_id', 'id', 'updated_by', '#'].includes(colId);
          if (isSystem) return;

          const rowNode = gridApi.getDisplayedRowAtIndex(rowIndex);
          if (!rowNode || !rowNode.data) return;
          const rowId = rowNode.data.row_id;
          if (!rowId) return;

          if (!updateMapByRow[rowId]) {
            updateMapByRow[rowId] = { rowNode, updates: {} };
          }

          const colTypes = currentColumnTypes || {};
          const colType = colTypes[colId] || 'string';
          let castedVal = val;
          if (colType === 'number') {
            if (val === '' || val === null || val === undefined) {
              castedVal = null;
            } else {
              const parsedVal = Number(val);
              if (isNaN(parsedVal)) {
                alert(`컬럼 '${colId}'의 값 '${val}'은(는) 올바른 숫자 형식이 아닙니다.`);
                throw new Error(`Invalid number format`);
              }
              castedVal = parsedVal;
            }
          }
          updateMapByRow[rowId].updates[colId] = castedVal;
        });
      } else {
        // MxN Matrix clipboard ➡️ Standard offset paste starting from top-left anchor cell
        // Find anchor (top-left) cell
        let anchorRow = Infinity;
        let anchorColIdx = Infinity;
        let anchorColId = '';

        if (focusedCell) {
          anchorRow = focusedCell.rowIndex;
          anchorColId = focusedCell.column.getColId();
          anchorColIdx = allCols.indexOf(anchorColId);
        } else {
          targetCells.forEach(cell => {
            const idx = colIdToIndexMap[cell.colId];
            if (cell.rowIndex < anchorRow) {
              anchorRow = cell.rowIndex;
            }
            if (idx !== undefined && idx < anchorColIdx) {
              anchorColIdx = idx;
              anchorColId = cell.colId;
            }
          });
        }

        if (anchorRow === Infinity || anchorColIdx === Infinity) return;

        parsedMatrix.forEach((rowValues, rOffset) => {
          const targetRowIndex = anchorRow + rOffset;
          const rowNode = gridApi.getDisplayedRowAtIndex(targetRowIndex);
          if (!rowNode || !rowNode.data) return;
          const rowId = rowNode.data.row_id;

          rowValues.forEach((val, cOffset) => {
            const targetColIndex = anchorColIdx + cOffset;
            if (targetColIndex >= allCols.length) return;

            const colId = allCols[targetColIndex];
            const isSystem = ['created_at', 'updated_at', 'row_id', 'id', 'updated_by', '#'].includes(colId);
            if (isSystem) return;

            if (!updateMapByRow[rowId]) {
              updateMapByRow[rowId] = { rowNode, updates: {} };
            }

            const colTypes = currentColumnTypes || {};
            const colType = colTypes[colId] || 'string';
            let castedVal = val;
            if (colType === 'number') {
              if (val === '' || val === null || val === undefined) {
                castedVal = null;
              } else {
                const parsedVal = Number(val);
                if (isNaN(parsedVal)) {
                  alert(`컬럼 '${colId}'의 값 '${val}'은(는) 올바른 숫자 형식이 아닙니다.`);
                  throw new Error(`Invalid number format`);
                }
                castedVal = parsedVal;
              }
            }
            updateMapByRow[rowId].updates[colId] = castedVal;
          });
        });
      }

      // Populate batchUpdates array
      Object.keys(updateMapByRow).forEach(rowId => {
        const item = updateMapByRow[rowId];
        if (Object.keys(item.updates).length > 0) {
          batchUpdates.push({
            row_id: rowId,
            updates: item.updates,
            source_name: 'user',
            updated_by: CURRENT_USER
          });

          // Stage edits in pendingTxEdits if Tx Mode is active, and update local grid row node data in-place
          const oldRowData = item.rowNode.data;
          if (txModeActive) {
            Object.keys(item.updates).forEach(col => {
              const key = `${rowId}_${col}`;
              if (!pendingTxEdits[key]) {
                const oldValue = oldRowData.data?.[col]?.value !== undefined ? oldRowData.data[col].value : '';
                const oldIsOverwrite = oldRowData.data?.[col]?.is_overwrite === true;
                pendingTxEdits[key] = {
                  rowId,
                  colId: col,
                  newValue: item.updates[col],
                  oldValue: oldValue,
                  oldIsOverwrite: oldIsOverwrite,
                  data: oldRowData
                };
              } else {
                pendingTxEdits[key].newValue = item.updates[col];
              }

              // Update in-place on latest row data
              const latestNode = gridApi.getRowNode(rowId);
              const latestData = latestNode ? latestNode.data : oldRowData;
              if (latestData) {
                ensureCellObject(latestData, col);
                latestData.data[col].value = item.updates[col];
              }
            });
          }
        }
      });

      if (txModeActive) {
        if (batchUpdates.length > 0) {
          updateTxModeUI();
          gridApi.refreshCells({ force: true });
          performanceLog.textContent = `Staged clipboard paste: ${Object.keys(pendingTxEdits).length} total pending edits`;
        }
        return;
      }

      if (batchUpdates.length > 0) {
        const res = await fetch(`${API_BASE}/tables/${currentTable}/data/updates`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ updates: batchUpdates })
        });

        if (res.ok) {
          pageCache.clear();
          const result = await res.json();
          performanceLog.textContent = `Pasted successfully: ${batchUpdates.length} rows updated`;

          // Fast-apply local data values by updating latest node data in-place
          batchUpdates.forEach(update => {
            const rowNode = gridApi.getRowNode(update.row_id);
            if (rowNode) {
              const latestData = rowNode.data;
              if (latestData) {
                Object.keys(update.updates).forEach(col => {
                  ensureCellObject(latestData, col);
                  latestData.data[col].value = update.updates[col];
                  latestData.data[col].is_overwrite = true;
                });
                latestData.updated_at = getLocalTimeString();
              }
            }
          });

          // Force sort update to push modified rows to the top
          updateGridSortState();
          gridApi.refreshCells({ force: true });

          // Sync selected cell UI if inside pasted range
          if (selectedCell) {
            const matchedUpdate = batchUpdates.find(u => u.row_id === selectedCell.rowId);
            if (matchedUpdate && matchedUpdate.updates[selectedCell.colId] !== undefined) {
              selectedCell.value = matchedUpdate.updates[selectedCell.colId];
              updateSelectedCellUI();
            }
          }
        } else {
          const errData = await res.json().catch(() => ({}));
          const errMsg = errData.detail || 'Paste batch update failed';
          throw new Error(errMsg);
        }
      }
    } catch (err) {
      console.error('Failed to paste updates', err);
      alert(`붙여넣기 저장 실패: ${err.message}`);
      performanceLog.textContent = '❌ Smart paste failed to save';
    }
  });

  // 2. Copy handler
  document.addEventListener('copy', (e) => {
    if (!gridApi) return;

    const activeEl = document.activeElement;
    if (activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA' || activeEl.hasAttribute('contenteditable') || activeEl.classList.contains('ag-input-field-input'))) {
      return;
    }

    // 1순위: 커스텀 드래그 선택 범위가 존재할 경우 범위 복사 실행
    const rangeTsv = getRangeSelectedTSV();
    if (rangeTsv) {
      e.preventDefault();
      e.clipboardData.setData('text/plain', rangeTsv);
      performanceLog.textContent = '📋 Range copied to clipboard';
      return;
    }

    // 2순위 (Fallback): 선택된 행 단위 복사 실행
    const selectedNodes = gridApi.getSelectedNodes();
    if (selectedNodes.length === 0) return;

    e.preventDefault();
    const columns = gridApi.getColumns().map(c => c.getColId()).filter(c => {
      if (c === '#' || /^\d+$/.test(c)) return false;
      return currentColumns.includes(c) || ['row_id', 'created_at', 'updated_at'].includes(c);
    });

    // Headers copy setting check
    const includeHeaders = copyHeaderToggle.checked;
    const lines = [];

    if (includeHeaders) {
      lines.push(columns.map(c => c.toUpperCase()).join('\t'));
    }

    selectedNodes.forEach(node => {
      if (!node.data) return;
      const rowCells = columns.map(col => {
        if (col === 'row_id') return node.data.row_id;
        if (col === 'created_at') return node.data.created_at;
        if (col === 'updated_at') return node.data.updated_at;

        const cell = node.data.data?.[col];
        if (cell && typeof cell === 'object') {
          return cell.value !== undefined ? cell.value : '';
        }
        return cell !== undefined ? cell : '';
      });
      lines.push(rowCells.join('\t'));
    });

    e.clipboardData.setData('text/plain', lines.join('\n'));
    performanceLog.textContent = `📋 Copied ${selectedNodes.length} rows to clipboard`;
  });
}

// Drag and Drop Log Ingestion
function setupDragAndDrop() {
  const dropOverlay = document.getElementById('drop-overlay');
  const dropTableName = document.getElementById('drop-table-name');

  if (!dropOverlay) return;

  let dragCounter = 0;

  window.addEventListener('dragenter', (e) => {
    e.preventDefault();
    if (!currentTable) return;

    // Only trigger for files
    if (e.dataTransfer.types.includes('Files')) {
      dragCounter++;
      dropTableName.textContent = currentTable;
      dropOverlay.style.display = 'flex';
      // Force layout calculation
      dropOverlay.offsetHeight;
      dropOverlay.classList.add('active');
    }
  });

  window.addEventListener('dragover', (e) => {
    e.preventDefault();
  });

  window.addEventListener('dragleave', (e) => {
    e.preventDefault();
    if (!currentTable) return;

    if (e.dataTransfer.types.includes('Files')) {
      dragCounter--;
      if (dragCounter === 0) {
        dropOverlay.classList.remove('active');
        setTimeout(() => {
          if (!dropOverlay.classList.contains('active')) {
            dropOverlay.style.display = 'none';
          }
        }, 300);
      }
    }
  });

  window.addEventListener('drop', async (e) => {
    e.preventDefault();
    dragCounter = 0;
    dropOverlay.classList.remove('active');
    dropOverlay.style.display = 'none';

    if (!currentTable) return;

    const files = e.dataTransfer.files;
    if (files.length === 0) return;

    performanceLog.textContent = `Uploading ${files.length} log file(s)...`;

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      performanceLog.textContent = `Uploading file [${file.name}] (${(file.size / 1024).toFixed(1)} KB)...`;

      const formData = new FormData();
      formData.append('file', file);

      try {
        const res = await fetch(`${API_BASE}/tables/${currentTable}/upload?user=${encodeURIComponent(CURRENT_USER)}`, {
          method: 'POST',
          body: formData
        });

        if (res.ok) {
          performanceLog.textContent = `✅ Successfully ingested [${file.name}]. Sync will refresh table shortly.`;
        } else {
          throw new Error('Upload failed');
        }
      } catch (err) {
        console.error('File ingestion failed', err);
        performanceLog.textContent = `❌ Ingestion failed for [${file.name}]`;
      }
    }
  });
}

// HistoryNavigator (4-Step Jump Sequence)
async function navigateToLog(log) {
  if (isNavigating) {
    performanceLog.textContent = '⚠️ Already navigating, please wait...';
    return;
  }

  isNavigating = true;
  performanceLog.textContent = `🔍 Navigating to ${log.table_name}:${log.row_id} in Transaction ${log.transaction_id}...`;

  // Set 5s watchdog safety net (mimics PyQt 10s guard timer)
  if (navigationWatchdog) clearTimeout(navigationWatchdog);
  navigationWatchdog = setTimeout(() => {
    releaseNavigationGuard('❌ Navigation Timeout');
  }, 5000);

  const targetTable = log.table_name;
  const targetTx = log.transaction_id;

  // Step 1: Switch table/tab if different
  if (currentTable !== targetTable) {
    tableSelect.value = targetTable;
    await switchTable(targetTable);
  }

  // Set the transaction filter context automatically
  if (targetTx) {
    currentTransactionId = targetTx;
    if (bannerTxId) bannerTxId.textContent = targetTx;
    if (txFilterBanner) txFilterBanner.style.display = 'flex';

    // Highlight timeline items
    const timelineItems = timeline.querySelectorAll('.timeline-item');
    timelineItems.forEach(li => {
      const itemTxId = li.dataset.txId || (li.querySelector('.filter-tx-btn')?.dataset.txId);
      if (itemTxId && itemTxId === currentTransactionId) {
        li.classList.add('active-tx-log');
      } else {
        li.classList.remove('active-tx-log');
      }
    });
  } else {
    currentTransactionId = null;
    if (bannerTxId) bannerTxId.textContent = '';
    if (txFilterBanner) txFilterBanner.style.display = 'none';

    // Clear highlights
    const timelineItems = timeline.querySelectorAll('.timeline-item');
    timelineItems.forEach(li => {
      li.classList.remove('active-tx-log');
    });
  }

  // Give browser event loop 50ms to stabilize layout
  setTimeout(() => {
    navigatorStep3(log);
  }, 50);
}

// Step 2: Check local caching or decide server target jump
function navigatorStep2(log) {
  if (!gridApi) {
    releaseNavigationGuard('❌ Grid not initialized');
    return;
  }

  const rowNode = gridApi.getRowNode(log.row_id);
  if (rowNode) {
    // Cache Hit -> directly scroll (Step 4)
    navigatorFinalScroll(rowNode, log.column_name);
  } else {
    // Check if row exists in any of the cached pages
    for (const [skip, cached] of pageCache.entries()) {
      const found = cached.data.some(r => (r.row_id || r.id) === log.row_id);
      if (found) {
        currentSkip = skip;
        gridApi.setGridOption('rowData', cached.data);
        updateGridSortState();
        updateLoadedCount(cached.data.length);
        totalRowsCount.textContent = `Matches: ${cached.total}`;
        updatePaginationUI(cached.total);

        setTimeout(() => {
          const node = gridApi.getRowNode(log.row_id);
          if (node) {
            navigatorFinalScroll(node, log.column_name);
          } else {
            releaseNavigationGuard('❌ Failed to locate row in cached page');
          }
        }, 50);
        return;
      }
    }

    // Cache Miss -> request server target jump (Step 3)
    navigatorStep3(log);
  }
}

// Step 3: Fetch target row via API parameter
async function navigatorStep3(log) {
  performanceLog.textContent = '🌐 Requesting target position from server...';

  const q = globalSearch ? globalSearch.value.trim() : '';
  const cols = searchCols ? searchCols.value : '';
  const sortLatest = sortLatestToggle.checked;
  const filterModel = gridApi ? gridApi.getFilterModel() : {};
  const filterStr = Object.keys(filterModel).length > 0 ? JSON.stringify(filterModel) : '';

  let url = `${API_BASE}/tables/${currentTable}/data?target_row_id=${log.row_id}&limit=${pageLimit}`;
  url += `&order_by=${sortLatest ? 'updated_at' : 'row_id'}&order_desc=${sortLatest}`;
  if (currentTransactionId) {
    url += `&transaction_id=${currentTransactionId}`;
  }
  if (q) {
    url += `&q=${encodeURIComponent(q)}`;
    if (cols) url += `&cols=${encodeURIComponent(cols)}`;
  }
  if (filterStr) {
    url += `&filters=${encodeURIComponent(filterStr)}`;
  }

  try {
    const res = await fetch(url);
    const result = await res.json();

    if (result.target_offset === -1 || result.data.length === 0) {
      releaseNavigationGuard('❌ Target row does not match active search/transaction filters');
      return;
    }

    // Load returned chunk page to local grid
    gridApi.setGridOption('rowData', result.data);
    updateGridSortState();

    // Update skip counter
    currentSkip = result.calculated_skip !== null ? result.calculated_skip : 0;

    // Update Counts (Zero-lag counter concept)
    updateLoadedCount(result.data.length);
    totalRowsCount.textContent = `Matches: ${result.total}`;

    // Update Pagination UI
    updatePaginationUI(result.total);

    // Save to Cache
    pageCache.set(currentSkip, { data: result.data, total: result.total });

    // Check if target node loaded successfully
    setTimeout(() => {
      const rowNode = gridApi.getRowNode(log.row_id);
      if (rowNode) {
        navigatorFinalScroll(rowNode, log.column_name);
      } else {
        releaseNavigationGuard('❌ Failed to locate row after server fetch');
      }
    }, 20); // 20ms layout sync delay

  } catch (err) {
    console.error('Jump fetch error', err);
    releaseNavigationGuard('❌ Server fetch error');
  }
}

// Step 4: Scroll and Focus Column Cell
function navigatorFinalScroll(rowNode, columnName) {
  try {
    // 1. Ensure visible
    gridApi.ensureNodeVisible(rowNode, 'middle');

    // 2. Select row
    rowNode.setSelected(true, true);

    // 3. Focus Cell
    gridApi.setFocusedCell(rowNode.rowIndex, columnName);

    // 4. Trigger flash micro-animation
    gridApi.flashCells({
      rowNodes: [rowNode],
      columns: [columnName],
      flashDelay: 1000
    });

    // 5. Sync details panel manually
    selectedCell = {
      rowId: rowNode.data.row_id,
      colId: columnName,
      value: rowNode.data.data?.[columnName]?.value ?? '',
      rowIndex: rowNode.rowIndex
    };
    updateSelectedCellUI();

    performanceLog.textContent = `🎯 Jumped to ${columnName} at Row ${rowNode.data.row_id}`;

    // Finalize
    releaseNavigationGuard();
  } catch (err) {
    console.error('Final scroll error', err);
    releaseNavigationGuard('❌ Scroller positioning error');
  }
}

// Helper: Navigation Locker Release
function releaseNavigationGuard(errorMessage = '') {
  isNavigating = false;
  if (navigationWatchdog) {
    clearTimeout(navigationWatchdog);
    navigationWatchdog = null;
  }
  if (errorMessage) {
    performanceLog.textContent = errorMessage;
  }
}

// Feature 2: Open Cell Sources Dialog Modal
// Helper: get selected cells range or single focused cell
function getSelectedCells() {
  if (!gridApi) return [];
  const cells = [];
  const allCols = gridApi.getColumns().map(c => c.getColId());
  const systemCols = ['created_at', 'updated_at', 'row_id', 'id', 'updated_by', '#'];

  if (dragStartCell && dragEndCell) {
    const startColIdx = allCols.indexOf(dragStartCell.colId);
    const endColIdx = allCols.indexOf(dragEndCell.colId);
    if (startColIdx !== -1 && endColIdx !== -1) {
      const minColIdx = Math.min(startColIdx, endColIdx);
      const maxColIdx = Math.max(startColIdx, endColIdx);
      const minRowIdx = Math.min(dragStartCell.rowIndex, dragEndCell.rowIndex);
      const maxRowIdx = Math.max(dragStartCell.rowIndex, dragEndCell.rowIndex);

      for (let r = minRowIdx; r <= maxRowIdx; r++) {
        for (let cIdx = minColIdx; cIdx <= maxColIdx; cIdx++) {
          const colId = allCols[cIdx];
          if (systemCols.includes(colId) || /^\d+$/.test(colId)) continue;

          const rowNode = gridApi.getDisplayedRowAtIndex(r);
          if (rowNode && rowNode.data) {
            const rowId = rowNode.data.row_id;
            cells.push({ rowId, colId, rowIndex: r });
          }
        }
      }
    }
  } else {
    // Focused cell fallback
    const focusedCell = gridApi.getFocusedCell();
    if (focusedCell) {
      const colId = focusedCell.column.getId();
      if (!systemCols.includes(colId) && !/^\d+$/.test(colId)) {
        const rowNode = gridApi.getDisplayedRowAtIndex(focusedCell.rowIndex);
        if (rowNode && rowNode.data) {
          cells.push({ rowId: rowNode.data.row_id, colId, rowIndex: focusedCell.rowIndex });
        }
      }
    } else if (selectedCell) {
      cells.push({ rowId: selectedCell.rowId, colId: selectedCell.colId, rowIndex: selectedCell.rowIndex });
    }
  }
  return cells;
}

// Feature 2: Open Cell Sources Dialog Modal
async function openSourcesModal() {
  const cells = getSelectedCells();
  if (cells.length === 0) return;

  if (cells.length > 1) {
    const cols = Array.from(new Set(cells.map(c => c.colId)));
    const rows = Array.from(new Set(cells.map(c => c.rowIndex)));
    modalMetaInfo.innerHTML = `
      <div><strong>Selected Range:</strong> <span style="color:var(--color-secondary)">${cells.length} cells (${rows.length} rows × ${cols.length} cols)</span></div>
      <div><strong>Columns:</strong> <span style="color:var(--color-primary)">${cols.map(c => c.toUpperCase()).join(', ')}</span></div>
    `;
  } else {
    const { rowId, colId } = cells[0];
    modalMetaInfo.innerHTML = `
      <div><strong>Row ID:</strong> <span style="color:var(--color-secondary)">${rowId}</span></div>
      <div><strong>Column:</strong> <span style="color:var(--color-primary)">${colId.toUpperCase()}</span></div>
    `;
  }
  sourcesList.innerHTML = '<tr><td colspan="3" style="text-align:center">Loading sources...</td></tr>';
  sourcesModal.style.display = 'flex';

  await refreshSourcesList();
}

// Fetch and render source details inside table
async function refreshSourcesList() {
  const cells = getSelectedCells();
  if (cells.length === 0) return;

  if (cells.length === 1) {
    const { rowId, colId } = cells[0];
    try {
      const res = await fetch(`${API_BASE}/tables/${currentTable}/${rowId}/${colId}/sources`);
      if (!res.ok) throw new Error('Failed to fetch sources');

      const data = await res.json();
      const sources = data.sources || {};
      const manualPriority = data.manual_priority_source;

      sourcesList.innerHTML = '';
      const sourceNames = Object.keys(sources);

      if (sourceNames.length === 0) {
        sourcesList.innerHTML = '<tr><td colspan="3" style="text-align:center;color:var(--text-dim)">No source data available.</td></tr>';
        return;
      }

      sourceNames.forEach(sourceName => {
        const sourceVal = sources[sourceName];
        const isPinned = manualPriority === sourceName;

        let displayVal = sourceVal;
        let titleAttr = '';
        if (sourceVal && typeof sourceVal === 'object') {
          displayVal = sourceVal.value !== undefined ? sourceVal.value : '';
          if (sourceVal.timestamp || sourceVal.updated_by) {
            const timeStr = sourceVal.timestamp ? new Date(sourceVal.timestamp).toLocaleString() : 'N/A';
            const userStr = sourceVal.updated_by || 'system';
            titleAttr = `title="Updated by ${userStr} at ${timeStr}"`;
          }
        }

        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${sourceName}</td>
          <td><code ${titleAttr}>${displayVal !== null ? displayVal : 'NULL'}</code></td>
          <td>
            <button class="action-btn pin-btn ${isPinned ? 'active' : ''}" title="Pin this value">${isPinned ? '📌 Pinned' : '📍 Pin'}</button>
            <button class="action-btn del-btn" title="Delete this source">🗑️ Delete</button>
          </td>
        `;

        // Bind Pin Action
        tr.querySelector('.pin-btn').addEventListener('click', async () => {
          const nextPriority = isPinned ? null : sourceName; // Toggle pin
          performanceLog.textContent = 'Updating cell priority...';
          try {
            const pinRes = await fetch(`${API_BASE}/tables/${currentTable}/${rowId}/${colId}/priority`, {
              method: 'PUT',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                source_name: nextPriority,
                updated_by: CURRENT_USER
              })
            });

            if (pinRes.ok) {
              performanceLog.textContent = 'Cell priority updated successfully';
              pageCache.clear();
              await fetchData(false);
              await refreshSourcesList();
            } else {
              throw new Error('Priority update failed');
            }
          } catch (err) {
            console.error(err);
            performanceLog.textContent = '❌ Failed to pin source';
          }
        });

        // Bind Delete Action
        tr.querySelector('.del-btn').addEventListener('click', async () => {
          if (!confirm(`Are you sure you want to delete source [${sourceName}] data for this cell?`)) return;

          performanceLog.textContent = 'Deleting cell source...';
          try {
            const delRes = await fetch(`${API_BASE}/tables/${currentTable}/${rowId}/${colId}/sources/${sourceName}`, {
              method: 'DELETE'
            });

            if (delRes.ok) {
              performanceLog.textContent = 'Cell source deleted successfully';
              pageCache.clear();
              await fetchData(false);
              await refreshSourcesList();
            } else {
              throw new Error('Source deletion failed');
            }
          } catch (err) {
            console.error(err);
            performanceLog.textContent = '❌ Failed to delete cell source';
          }
        });

        sourcesList.appendChild(tr);
      });
    } catch (err) {
      console.error(err);
      sourcesList.innerHTML = '<tr><td colspan="3" style="text-align:center;color:var(--color-danger)">Failed to load sources.</td></tr>';
    }
  } else {
    // Batch Mode
    try {
      const res = await fetch(`${API_BASE}/tables/${currentTable}/cells/sources/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          updates: cells.map(c => ({ row_id: c.rowId, column_name: c.colId }))
        })
      });
      if (!res.ok) throw new Error('Failed to query batch sources');

      const cellSourcesList = await res.json();

      const uniqueSources = new Set();
      const sourceValuesMap = {};
      const sourcePinnedCount = {};

      cellSourcesList.forEach(cellData => {
        const sources = cellData.sources || {};
        const manualPriority = cellData.manual_priority_source;

        Object.keys(sources).forEach(srcName => {
          uniqueSources.add(srcName);
          if (!sourceValuesMap[srcName]) {
            sourceValuesMap[srcName] = [];
          }
          let srcVal = sources[srcName];
          let valStr = srcVal;
          if (srcVal && typeof srcVal === 'object') {
            valStr = srcVal.value !== undefined ? srcVal.value : '';
          }
          sourceValuesMap[srcName].push(valStr);

          if (manualPriority === srcName) {
            sourcePinnedCount[srcName] = (sourcePinnedCount[srcName] || 0) + 1;
          }
        });
      });

      sourcesList.innerHTML = '';
      const sourceNames = Array.from(uniqueSources);

      if (sourceNames.length === 0) {
        sourcesList.innerHTML = '<tr><td colspan="3" style="text-align:center;color:var(--text-dim)">No source data available in selected cells.</td></tr>';
        return;
      }

      sourceNames.forEach(sourceName => {
        const values = sourceValuesMap[sourceName] || [];
        const pinnedCount = sourcePinnedCount[sourceName] || 0;
        const isPinnedAll = pinnedCount === cells.length;

        const uniqueVals = Array.from(new Set(values));
        let valText = '';
        if (uniqueVals.length === 0) {
          valText = 'N/A';
        } else if (uniqueVals.length === 1) {
          valText = String(uniqueVals[0]);
        } else {
          valText = `Multiple Values (${uniqueVals.length} types)`;
        }

        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${sourceName}</td>
          <td><code>${valText}</code></td>
          <td>
            <button class="action-btn pin-btn ${isPinnedAll ? 'active' : ''}" title="Pin this source for all selected cells">${isPinnedAll ? '📌 Pinned' : '📍 Pin'}</button>
            <button class="action-btn del-btn" title="Delete this source from all selected cells">🗑️ Delete</button>
          </td>
        `;

        // Bind batch Pin Action
        tr.querySelector('.pin-btn').addEventListener('click', async () => {
          const nextPriority = isPinnedAll ? null : sourceName;
          performanceLog.textContent = `Batch updating cell priority to [${sourceName}]...`;
          try {
            const pinRes = await fetch(`${API_BASE}/tables/${currentTable}/cells/priority/batch`, {
              method: 'PUT',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                updates: cells.map(c => ({ row_id: c.rowId, column_name: c.colId })),
                source_name: nextPriority,
                updated_by: CURRENT_USER
              })
            });

            if (pinRes.ok) {
              performanceLog.textContent = 'Batch cell priority updated successfully';
              pageCache.clear();
              await fetchData(false);
              await refreshSourcesList();
            } else {
              throw new Error('Batch priority update failed');
            }
          } catch (err) {
            console.error(err);
            performanceLog.textContent = '❌ Failed to batch pin source';
          }
        });

        // Bind batch Delete Action
        tr.querySelector('.del-btn').addEventListener('click', async () => {
          if (!confirm(`Are you sure you want to delete source [${sourceName}] from all ${cells.length} selected cells?`)) return;

          performanceLog.textContent = `Batch deleting source [${sourceName}]...`;
          try {
            const delRes = await fetch(`${API_BASE}/tables/${currentTable}/cells/sources/delete/batch`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                cells: cells.map(c => ({ row_id: c.rowId, column_name: c.colId })),
                source_name: sourceName
              })
            });

            if (delRes.ok) {
              performanceLog.textContent = 'Batch cell sources deleted successfully';
              pageCache.clear();
              await fetchData(false);
              await refreshSourcesList();
            } else {
              throw new Error('Batch source deletion failed');
            }
          } catch (err) {
            console.error(err);
            performanceLog.textContent = '❌ Failed to batch delete source';
          }
        });

        sourcesList.appendChild(tr);
      });
    } catch (err) {
      console.error(err);
      sourcesList.innerHTML = '<tr><td colspan="3" style="text-align:center;color:var(--color-danger)">Failed to query sources for selected cells.</td></tr>';
    }
  }
}

// Feature 2: Delete selected rows batch
async function deleteSelectedRows() {
  if (!gridApi) return;
  const selectedNodes = gridApi.getSelectedNodes();
  if (selectedNodes.length === 0) {
    alert('No rows selected for deletion');
    return;
  }

  const rowIds = selectedNodes.map(node => node.data.row_id).filter(Boolean);
  if (rowIds.length === 0) return;

  if (!confirm(`Are you sure you want to permanently delete the selected ${rowIds.length} rows?`)) return;

  performanceLog.textContent = 'Deleting selected rows...';
  try {
    const res = await fetch(`${API_BASE}/tables/${currentTable}/rows/batch_delete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        row_ids: rowIds,
        user_name: CURRENT_USER
      })
    });

    if (res.ok) {
      pageCache.clear();
      const result = await res.json();
      performanceLog.textContent = `Deleted ${result.deleted_count} rows successfully`;
      // History updates will be handled by the WebSocket stream
      // WebSocket event batch_row_delete will handle removing from grid cache
    } else {
      throw new Error('Batch delete request failed');
    }
  } catch (err) {
    console.error(err);
    performanceLog.textContent = '❌ Failed to delete selected rows';
  }
}

// Feature: Clear selected cells in range or single focused cell
async function clearSelectedCells() {
  if (!gridApi || !currentTable) return;

  let cellsToClear = []; // Array of { rowIndex, colId }
  const selectedCells = Object.values(selectedCellsMap);

  if (selectedCells.length > 0) {
    cellsToClear = selectedCells;
  } else if (dragStartCell && dragEndCell) {
    const allCols = gridApi.getColumns().map(c => c.getColId());
    const startColIdx = allCols.indexOf(dragStartCell.colId);
    const endColIdx = allCols.indexOf(dragEndCell.colId);
    if (startColIdx !== -1 && endColIdx !== -1) {
      const minColIdx = Math.min(startColIdx, endColIdx);
      const maxColIdx = Math.max(startColIdx, endColIdx);
      const minRowIdx = Math.min(dragStartCell.rowIndex, dragEndCell.rowIndex);
      const maxRowIdx = Math.max(dragStartCell.rowIndex, dragEndCell.rowIndex);

      for (let r = minRowIdx; r <= maxRowIdx; r++) {
        for (let cIdx = minColIdx; cIdx <= maxColIdx; cIdx++) {
          cellsToClear.push({ rowIndex: r, colId: allCols[cIdx] });
        }
      }
    }
  } else {
    // Single focused cell
    const focusedCell = gridApi.getFocusedCell();
    if (focusedCell) {
      cellsToClear.push({ rowIndex: focusedCell.rowIndex, colId: focusedCell.column.getId() });
    }
  }

  if (cellsToClear.length === 0) return;

  const systemCols = ['created_at', 'updated_at', 'row_id', 'id', 'updated_by', '#'];
  const updateMapByRow = {};

  cellsToClear.forEach(cell => {
    // Skip system columns
    if (systemCols.includes(cell.colId) || /^\d+$/.test(cell.colId)) return;

    const rowNode = gridApi.getDisplayedRowAtIndex(cell.rowIndex);
    if (!rowNode || !rowNode.data) return;
    const rowId = rowNode.data.row_id;
    if (!rowId) return;

    if (!updateMapByRow[rowId]) {
      updateMapByRow[rowId] = {
        row_id: rowId,
        updates: {},
        rowNode: rowNode
      };
    }

    const colType = (currentColumnTypes || {})[cell.colId] || 'string';
    const clearValue = colType === 'number' ? null : '';
    updateMapByRow[rowId].updates[cell.colId] = clearValue;
  });

  const updatesArray = [];

  Object.keys(updateMapByRow).forEach(rowId => {
    const item = updateMapByRow[rowId];
    if (Object.keys(item.updates).length > 0) {
      if (txModeActive) {
        // Stage edits in pendingTxEdits
        Object.keys(item.updates).forEach(colId => {
          const key = `${rowId}_${colId}`;
          if (!pendingTxEdits[key]) {
            const oldValue = item.rowNode.data.data?.[colId]?.value !== undefined ? item.rowNode.data.data[colId].value : '';
            const oldIsOverwrite = item.rowNode.data.data?.[colId]?.is_overwrite === true;
            pendingTxEdits[key] = {
              rowId,
              colId,
              newValue: item.updates[colId],
              oldValue: oldValue,
              oldIsOverwrite: oldIsOverwrite,
              data: item.rowNode.data
            };
          } else {
            pendingTxEdits[key].newValue = item.updates[colId];
          }

          // Update in-place on latest row data
          const latestNode = gridApi.getRowNode(rowId);
          const latestData = latestNode ? latestNode.data : item.rowNode.data;
          if (latestData) {
            ensureCellObject(latestData, colId);
            latestData.data[colId].value = item.updates[colId];
          }
        });
      } else {
        updatesArray.push({
          row_id: rowId,
          updates: item.updates,
          source_name: 'user',
          updated_by: CURRENT_USER
        });
      }
    }
  });

  if (txModeActive) {
    if (Object.keys(updateMapByRow).length > 0) {
      if (selectedCell && updateMapByRow[selectedCell.rowId] && updateMapByRow[selectedCell.rowId].updates[selectedCell.colId] !== undefined) {
        selectedCell.value = updateMapByRow[selectedCell.rowId].updates[selectedCell.colId];
        updateSelectedCellUI();
      }

      updateTxModeUI();
      gridApi.refreshCells({ force: true });
      setupBeforeUnloadWarning();
      performanceLog.textContent = `Staged cell clear: ${Object.keys(pendingTxEdits).length} total pending edits`;
    }
    return;
  }

  if (updatesArray.length === 0) return;

  performanceLog.textContent = `Clearing ${updatesArray.reduce((acc, cur) => acc + Object.keys(cur.updates).length, 0)} cells...`;
  const startTime = performance.now();

  try {
    const res = await fetch(`${API_BASE}/tables/${currentTable}/data/updates`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        updates: updatesArray,
        silent: false
      })
    });

    if (res.ok) {
      pageCache.clear();
      const result = await res.json();
      const saveTime = (performance.now() - startTime).toFixed(1);
      performanceLog.textContent = `Cleared cells in ${saveTime}ms (${result.change_count} cells updated)`;

      // Apply grid local updates on the latest nodes directly
      updatesArray.forEach(item => {
        const rowNode = gridApi.getRowNode(item.row_id);
        if (rowNode) {
          const latestData = rowNode.data;
          if (latestData) {
            if (!latestData.data) latestData.data = {};
            Object.keys(item.updates).forEach(colId => {
              if (!latestData.data[colId]) latestData.data[colId] = {};
              latestData.data[colId].value = item.updates[colId];
              latestData.data[colId].is_overwrite = true;
            });
            latestData.updated_at = getLocalTimeString();
          }
        }
      });

      if (selectedCell && updateMapByRow[selectedCell.rowId] && updateMapByRow[selectedCell.rowId].updates[selectedCell.colId] !== undefined) {
        selectedCell.value = updateMapByRow[selectedCell.rowId].updates[selectedCell.colId];
        updateSelectedCellUI();
      }

      // Append database generated history logs locally
      // History updates will be handled by the WebSocket stream
    } else {
      const errData = await res.json().catch(() => ({}));
      const errMsg = errData.detail || 'Cell clearing failed';
      throw new Error(errMsg);
    }
  } catch (err) {
    console.error('Failed to clear cells', err);
    alert(`셀 내용 비우기 실패: ${err.message}`);
    performanceLog.textContent = '❌ Cell clearing failed';
  }
}

// Bulk update all selected range cells to a new value (Ctrl + Enter feature)
async function applyValueToSelectedRange(newValue) {
  if (!gridApi) return;

  let cellsToUpdate = Object.values(selectedCellsMap);
  if (cellsToUpdate.length === 0) {
    if (!dragStartCell || !dragEndCell) return;

    const allCols = gridApi.getColumns().map(c => c.getColId());
    const startIdx = colIdToIndexMap[dragStartCell.colId];
    const endIdx = colIdToIndexMap[dragEndCell.colId];
    if (startIdx === undefined || endIdx === undefined) return;

    const minColIdx = Math.min(startIdx, endIdx);
    const maxColIdx = Math.max(startIdx, endIdx);
    const minRow = Math.min(dragStartCell.rowIndex, dragEndCell.rowIndex);
    const maxRow = Math.max(dragStartCell.rowIndex, dragEndCell.rowIndex);

    const targetCols = allCols.filter((_, idx) => idx >= minColIdx && idx <= maxColIdx && _ !== '#');
    for (let rIdx = minRow; rIdx <= maxRow; rIdx++) {
      targetCols.forEach(colId => {
        cellsToUpdate.push({ rowIndex: rIdx, colId });
      });
    }
  }

  if (cellsToUpdate.length === 0) return;

  const updatesArray = [];
  const updateMapByRow = {};

  // Gather row nodes in range
  cellsToUpdate.forEach(cell => {
    const { rowIndex, colId } = cell;
    // System columns cannot be modified
    const isSystem = ['created_at', 'updated_at', 'row_id', 'id', 'updated_by', '#'].includes(colId);
    if (isSystem) return;

    const rowNode = gridApi.getDisplayedRowAtIndex(rowIndex);
    if (!rowNode || !rowNode.data) return;
    const rowId = rowNode.data.row_id;

    if (!updateMapByRow[rowId]) {
      updateMapByRow[rowId] = { rowNode, updates: {} };
    }
    updateMapByRow[rowId].updates[colId] = newValue;
  });

  // Apply updates
  Object.keys(updateMapByRow).forEach(rowId => {
    const item = updateMapByRow[rowId];
    if (txModeActive) {
      // Stage edits in pendingTxEdits
      Object.keys(item.updates).forEach(colId => {
        const key = `${rowId}_${colId}`;
        if (!pendingTxEdits[key]) {
          const oldValue = item.rowNode.data.data?.[colId]?.value !== undefined ? item.rowNode.data.data[colId].value : '';
          const oldIsOverwrite = item.rowNode.data.data?.[colId]?.is_overwrite === true;
          pendingTxEdits[key] = {
            rowId,
            colId,
            newValue: item.updates[colId],
            oldValue: oldValue,
            oldIsOverwrite: oldIsOverwrite,
            data: item.rowNode.data
          };
        } else {
          pendingTxEdits[key].newValue = item.updates[colId];
        }

        // Update in-place on latest row data
        const latestNode = gridApi.getRowNode(rowId);
        const latestData = latestNode ? latestNode.data : item.rowNode.data;
        if (latestData) {
          ensureCellObject(latestData, colId);
          latestData.data[colId].value = item.updates[colId];
        }
      });
    } else {
      updatesArray.push({
        row_id: rowId,
        updates: item.updates,
        source_name: 'user',
        updated_by: CURRENT_USER
      });
    }
  });

  if (txModeActive) {
    if (Object.keys(updateMapByRow).length > 0) {
      if (selectedCell && updateMapByRow[selectedCell.rowId] && updateMapByRow[selectedCell.rowId].updates[selectedCell.colId] !== undefined) {
        selectedCell.value = updateMapByRow[selectedCell.rowId].updates[selectedCell.colId];
        updateSelectedCellUI();
      }

      updateTxModeUI();
      gridApi.refreshCells({ force: true });
      setupBeforeUnloadWarning();
      performanceLog.textContent = `Staged range value edit: ${Object.keys(pendingTxEdits).length} total pending edits`;
    }
    return;
  }

  if (updatesArray.length === 0) return;

  performanceLog.textContent = `Updating ${updatesArray.reduce((acc, cur) => acc + Object.keys(cur.updates).length, 0)} cells...`;
  const startTime = performance.now();

  try {
    const res = await fetch(`${API_BASE}/tables/${currentTable}/data/updates`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        updates: updatesArray,
        silent: false
      })
    });

    if (res.ok) {
      pageCache.clear();
      const result = await res.json();
      const saveTime = (performance.now() - startTime).toFixed(1);
      performanceLog.textContent = `Updated range cells in ${saveTime}ms (${result.change_count} cells updated)`;

      // Apply grid local updates on the latest nodes directly
      updatesArray.forEach(item => {
        const rowNode = gridApi.getRowNode(item.row_id);
        if (rowNode) {
          const latestData = rowNode.data;
          if (latestData) {
            Object.keys(item.updates).forEach(colId => {
              ensureCellObject(latestData, colId);
              latestData.data[colId].value = item.updates[colId];
              latestData.data[colId].is_overwrite = true;
            });
            latestData.updated_at = getLocalTimeString();
          }
        }
      });

      if (selectedCell && updateMapByRow[selectedCell.rowId] && updateMapByRow[selectedCell.rowId].updates[selectedCell.colId] !== undefined) {
        selectedCell.value = updateMapByRow[selectedCell.rowId].updates[selectedCell.colId];
        updateSelectedCellUI();
      }

      updateGridSortState();
      gridApi.refreshCells({ force: true });
    } else {
      const errData = await res.json().catch(() => ({}));
      const errMsg = errData.detail || 'Save failed';
      throw new Error(errMsg);
    }
  } catch (err) {
    console.error('Bulk cell update failed', err);
    alert(`범위 수정 사항 저장 실패: ${err.message}`);
    performanceLog.textContent = '❌ Range edit failed to save';
  }
}

// Feature 2: Smart Paste Parser via Form Upload
async function smartPasteViaIngestion() {
  try {
    let selectedText = '';
    let selectedType = 'text/plain';
    let fileExt = 'txt';

    // Check if navigator.clipboard.read is supported (for rich types like HTML)
    if (navigator.clipboard && navigator.clipboard.read) {
      const items = await navigator.clipboard.read().catch(err => {
        console.warn('Clipboard read error, falling back to readText()', err);
        return null;
      });

      if (items && items.length > 0) {
        const item = items[0];
        // Filter readable text-based formats
        const textTypes = item.types.filter(t => t.startsWith('text/') || t.includes('json') || t.includes('csv'));

        if (textTypes.length === 0) {
          alert('Clipboard does not contain any readable text format.');
          return;
        }

        if (textTypes.length === 1) {
          selectedType = textTypes[0];
          const blob = await item.getType(selectedType);
          selectedText = await blob.text();
        } else {
          // Show rich glassmorphic selection modal for multiple formats
          const chosen = await showClipboardTypeModal(textTypes);
          if (!chosen) {
            performanceLog.textContent = 'Smart paste cancelled';
            return; // Cancelled by user
          }
          selectedType = chosen;
          const blob = await item.getType(selectedType);
          selectedText = await blob.text();
        }
      } else {
        // Fallback to plain text if read() failed or returned nothing
        selectedText = await navigator.clipboard.readText();
        selectedType = 'text/plain';
      }
    } else {
      // Fallback to plain text if navigator.clipboard.read is not supported
      selectedText = await navigator.clipboard.readText();
      selectedType = 'text/plain';
    }

    if (!selectedText.trim()) {
      alert('Clipboard is empty or does not contain text.');
      return;
    }

    // Map mime types to extensions
    if (selectedType === 'text/html') fileExt = 'html';
    else if (selectedType === 'text/rtf') fileExt = 'rtf';
    else if (selectedType === 'application/json' || selectedType === 'text/json') fileExt = 'json';
    else if (selectedType === 'text/csv') fileExt = 'csv';
    else fileExt = 'txt';

    performanceLog.textContent = `Uploading ${selectedType} clipboard data for parsing...`;

    // Build log file representation via Blob
    const blob = new Blob([selectedText], { type: selectedType });
    const file = new File([blob], `web_smart_paste_${Date.now()}.${fileExt}`, { type: selectedType });

    const formData = new FormData();
    formData.append('file', file);

    const res = await fetch(`${API_BASE}/tables/${currentTable}/upload?user=${encodeURIComponent(CURRENT_USER)}`, {
      method: 'POST',
      body: formData
    });

    if (res.ok) {
      const resData = await res.json();
      const savedPath = resData.path || '';
      const savedFilename = savedPath.split(/[/\\]/).pop() || file.name;
      performanceLog.textContent = '📋 Clipboard uploaded to parser. Automatic reload will trigger soon.';
      showToast(`📋 스마트 붙여넣기 완료! (포맷: ${selectedType.split('/')[1].toUpperCase()}, 파일: ${savedFilename})`, 'success');
    } else {
      showToast('❌ 스마트 붙여넣기 전송에 실패했습니다.', 'error');
      throw new Error('Smart paste upload failed');
    }
  } catch (err) {
    console.error('Smart paste error', err);
    performanceLog.textContent = '❌ Failed to upload smart paste data';
    showToast('❌ 스마트 붙여넣기 중 오류가 발생했습니다.', 'error');
  }
}

// Glassmorphism selection modal for clipboard data types
function showClipboardTypeModal(types) {
  return new Promise((resolve) => {
    // 1. Create overlay container
    const overlay = document.createElement('div');
    overlay.id = 'clipboard-type-modal-overlay';
    Object.assign(overlay.style, {
      position: 'fixed',
      top: '0',
      left: '0',
      width: '100vw',
      height: '100vh',
      backgroundColor: 'rgba(11, 14, 20, 0.7)',
      backdropFilter: 'blur(12px)',
      webkitBackdropFilter: 'blur(12px)',
      zIndex: '9999',
      display: 'flex',
      justifyContent: 'center',
      alignItems: 'center',
      opacity: '0',
      transition: 'opacity 0.2s cubic-bezier(0.4, 0, 0.2, 1)'
    });

    // 2. Map mime-types to user friendly labels & icons
    const typeConfigs = {
      'text/plain': { label: 'Plain Text (일반 텍스트)', icon: '📋', color: '#89b4fa' },
      'text/html': { label: 'HTML Table (엑셀 표 서식 포함)', icon: '🌐', color: '#a6e3a1' },
      'text/rtf': { label: 'Rich Text Format (RTF 서식)', icon: '📝', color: '#f9e2af' },
      'text/csv': { label: 'Comma Separated (CSV)', icon: '📊', color: '#f5c2e7' },
      'application/json': { label: 'JSON Data Object', icon: '⚙️', color: '#cba6f7' }
    };

    // 3. Create modal container card
    const card = document.createElement('div');
    Object.assign(card.style, {
      background: 'rgba(20, 26, 38, 0.88)',
      border: '1px solid rgba(255, 255, 255, 0.08)',
      borderRadius: '16px',
      padding: '28px',
      width: '420px',
      boxShadow: '0 20px 40px rgba(0, 0, 0, 0.6), inset 0 1px 0 rgba(255, 255, 255, 0.05)',
      display: 'flex',
      flexDirection: 'column',
      gap: '20px',
      transform: 'scale(0.92)',
      transition: 'transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1)'
    });

    // 4. Modal Header
    const header = document.createElement('div');
    header.innerHTML = `
      <h3 style="font-family: 'Outfit', sans-serif; font-size: 1.35rem; font-weight: 600; color: #cdd6f4; margin-bottom: 6px;">📋 Paste Clipboard Type</h3>
      <p style="font-family: 'Outfit', sans-serif; font-size: 0.85rem; color: #7f849c; line-height: 1.45;">클립보드에 여러 포맷의 데이터가 감지되었습니다.<br>파싱을 위해 전송할 데이터 타입을 선택하세요.</p>
    `;
    card.appendChild(header);

    // 5. Buttons Container
    const btnContainer = document.createElement('div');
    Object.assign(btnContainer.style, {
      display: 'flex',
      flexDirection: 'column',
      gap: '10px'
    });

    types.forEach(type => {
      const cfg = typeConfigs[type] || { label: type, icon: '📄', color: '#cdd6f4' };
      const btn = document.createElement('button');

      Object.assign(btn.style, {
        background: 'rgba(255, 255, 255, 0.03)',
        border: '1px solid rgba(255, 255, 255, 0.06)',
        borderRadius: '10px',
        padding: '12px 16px',
        color: '#cdd6f4',
        fontFamily: "'Outfit', sans-serif",
        fontSize: '0.92rem',
        fontWeight: '500',
        textAlign: 'left',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        gap: '12px',
        transition: 'all 0.15s ease',
        outline: 'none'
      });

      btn.innerHTML = `
        <span style="font-size: 1.25rem; background: rgba(255,255,255,0.02); padding: 4px; border-radius: 6px; display: flex; align-items: center; justify-content: center;">${cfg.icon}</span>
        <div style="display: flex; flex-direction: column;">
          <span style="color: ${cfg.color}; font-weight: 600;">${cfg.label.split(' (')[0]}</span>
          <span style="font-size: 0.72rem; color: #7f849c; margin-top: 1px;">${type}</span>
        </div>
      `;

      btn.addEventListener('mouseenter', () => {
        btn.style.background = 'rgba(255, 255, 255, 0.08)';
        btn.style.borderColor = cfg.color;
        btn.style.transform = 'translateX(4px)';
        btn.style.boxShadow = `0 4px 15px ${cfg.color}15`;
      });
      btn.addEventListener('mouseleave', () => {
        btn.style.background = 'rgba(255, 255, 255, 0.03)';
        btn.style.borderColor = 'rgba(255, 255, 255, 0.06)';
        btn.style.transform = 'none';
        btn.style.boxShadow = 'none';
      });

      btn.addEventListener('click', () => {
        closeModal(type);
      });

      btnContainer.appendChild(btn);
    });

    card.appendChild(btnContainer);

    // 6. Cancel Button
    const cancelBtn = document.createElement('button');
    Object.assign(cancelBtn.style, {
      background: 'transparent',
      border: '1px solid rgba(255, 255, 255, 0.08)',
      borderRadius: '10px',
      padding: '10px',
      color: '#7f849c',
      fontFamily: "'Outfit', sans-serif",
      fontSize: '0.88rem',
      fontWeight: '500',
      cursor: 'pointer',
      transition: 'all 0.15s ease',
      outline: 'none'
    });
    cancelBtn.textContent = 'Cancel (취소)';
    cancelBtn.addEventListener('mouseenter', () => {
      cancelBtn.style.background = 'rgba(243, 139, 168, 0.1)';
      cancelBtn.style.color = '#f38ba8';
      cancelBtn.style.borderColor = 'rgba(243, 139, 168, 0.2)';
    });
    cancelBtn.addEventListener('mouseleave', () => {
      cancelBtn.style.background = 'transparent';
      cancelBtn.style.color = '#7f849c';
      cancelBtn.style.borderColor = 'rgba(255, 255, 255, 0.08)';
    });
    cancelBtn.addEventListener('click', () => {
      closeModal(null);
    });
    card.appendChild(cancelBtn);

    overlay.appendChild(card);
    document.body.appendChild(overlay);

    requestAnimationFrame(() => {
      overlay.style.opacity = '1';
      card.style.transform = 'scale(1)';
    });

    function closeModal(val) {
      overlay.style.opacity = '0';
      card.style.transform = 'scale(0.92)';
      setTimeout(() => {
        overlay.remove();
        resolve(val);
      }, 200);
    }
  });
}

// Premium Toast Notification Helper
function showToast(message, type = 'info') {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;

  let icon = 'ℹ️';
  if (type === 'success') icon = '✅';
  else if (type === 'error') icon = '❌';
  else if (type === 'warning') icon = '⚠️';

  toast.innerHTML = `
    <span style="font-size: 1.1rem;">${icon}</span>
    <span>${message}</span>
  `;

  container.appendChild(toast);

  // Auto remove toast after 5 seconds
  setTimeout(() => {
    // Force inline styles to bypass any browser CSS cache or animation forwards lock
    toast.style.transition = 'opacity 0.35s ease, transform 0.35s ease';
    toast.style.animation = 'none';
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(-20px) scale(0.9)';

    setTimeout(() => {
      toast.remove();
      if (container.children.length === 0) {
        container.remove();
      }
    }, 400);
  }, 5000);
}
window.showToast = showToast; // Expose globally for Desktop Wrapper

// Helper to strip user prefix and unique UUID suffixes from filename in client
function getCleanFilename(filename) {
  if (!filename) return '';
  // 1. Strip user prefix: user(username)_
  let clean = filename.replace(/^user\([^)]+\)_/, '');
  // 2. Strip hex suffix before extension: _[0-9a-fA-F]{8}
  const lastDotIdx = clean.lastIndexOf('.');
  if (lastDotIdx !== -1) {
    let name = clean.slice(0, lastDotIdx);
    const ext = clean.slice(lastDotIdx);
    name = name.replace(/_[0-9a-fA-F]{8}$/, '');
    clean = name + ext;
  } else {
    clean = clean.replace(/_[0-9a-fA-F]{8}$/, '');
  }
  return clean;
}

// Floating Ingestion Progress Widget Helper
function showIngestionProgress(tableName, filename, progress, processedRows, totalRows) {
  let container = document.getElementById('ingestion-progress-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'ingestion-progress-container';
    document.body.appendChild(container);
  }

  // Normalize filename on client side for robust matching and cleaner display
  const cleanFilename = getCleanFilename(filename);
  const safeFilename = cleanFilename.replace(/[^a-zA-Z0-9]/g, '_');
  const cardId = `progress-${tableName}-${safeFilename}`;
  let card = document.getElementById(cardId);

  if (!card) {
    card = document.createElement('div');
    card.id = cardId;
    card.className = 'progress-card';
    container.appendChild(card);
  }

  // If already marked as success, error, or in auto-dismiss status, do not overwrite back to processing
  if (card.classList.contains('status-success') ||
    card.classList.contains('status-error') ||
    card.classList.contains('status-auto-dismiss')) {
    return;
  }

  const p = parseInt(progress, 10) || 0;
  const pr = parseInt(processedRows, 10) || 0;
  const tr = parseInt(totalRows, 10) || 0;

  card.innerHTML = `
    <div class="progress-header">
      <span class="progress-title">📤 파일 파싱 및 적재 중</span>
      <span class="progress-percent">${p}%</span>
    </div>
    <div class="progress-filename" title="${cleanFilename}">${cleanFilename}</div>
    <div class="progress-bar-container">
      <div class="progress-bar" style="width: ${p}%;"></div>
    </div>
    <div class="progress-stats">${pr.toLocaleString()} / ${tr.toLocaleString()} 행 처리됨</div>
  `;

  // Defensive Double Guard: Autocomplete and dismiss if reached 100% or processedRows >= totalRows
  const isComplete = p >= 100 || (tr > 0 && pr >= tr);
  if (isComplete) {
    card.classList.add('status-auto-dismiss');
    card.classList.add('status-success');

    const title = card.querySelector('.progress-title');
    if (title) title.textContent = '✅ 파일 적재 완료';
    const percent = card.querySelector('.progress-percent');
    if (percent) percent.textContent = '100%';
    const bar = card.querySelector('.progress-bar');
    if (bar) bar.style.width = '100%';
    const stats = card.querySelector('.progress-stats');
    if (stats) stats.textContent = '적재 성공 및 정합성 검증 완료';

    // Auto remove after 2.5 seconds
    setTimeout(() => {
      card.style.transition = 'opacity 0.35s ease, transform 0.35s ease';
      card.style.animation = 'none';
      card.style.opacity = '0';
      card.style.transform = 'translateY(20px) scale(0.9)';

      setTimeout(() => {
        card.remove();
        const container = document.getElementById('ingestion-progress-container');
        if (container && container.children.length === 0) {
          container.remove();
        }
      }, 400);
    }, 2500);
  }
}

function finishIngestionProgress(tableName, filename, status, errorMsg = null) {
  const cleanFilename = getCleanFilename(filename);
  const safeFilename = cleanFilename.replace(/[^a-zA-Z0-9]/g, '_');
  const cardId = `progress-${tableName}-${safeFilename}`;
  const card = document.getElementById(cardId);
  if (!card) return;

  // Prevent double trigger if already in dismissal transition
  if (card.classList.contains('status-success') ||
    card.classList.contains('status-error') ||
    card.classList.contains('status-auto-dismiss')) {
    return;
  }

  card.classList.add('status-auto-dismiss'); // Mark to avoid duplicate timers

  if (status === 'SUCCESS') {
    card.classList.add('status-success');
    const title = card.querySelector('.progress-title');
    if (title) title.textContent = '✅ 파일 적재 완료';
    const percent = card.querySelector('.progress-percent');
    if (percent) percent.textContent = '100%';
    const bar = card.querySelector('.progress-bar');
    if (bar) bar.style.width = '100%';
    const stats = card.querySelector('.progress-stats');
    if (stats) stats.textContent = '적재 성공 및 정합성 검증 완료';
  } else {
    card.classList.add('status-error');
    const title = card.querySelector('.progress-title');
    if (title) title.textContent = '❌ 파일 적재 실패';
    const bar = card.querySelector('.progress-bar');
    if (bar) bar.style.width = '100%';
    const stats = card.querySelector('.progress-stats');
    if (stats) stats.textContent = errorMsg ? errorMsg.slice(0, 50) : '처리 중 예외 발생';
  }

  // Auto remove after 2.5s
  setTimeout(() => {
    // Force inline styles to bypass any browser CSS cache or animation forwards lock
    card.style.transition = 'opacity 0.35s ease, transform 0.35s ease';
    card.style.animation = 'none';
    card.style.opacity = '0';
    card.style.transform = 'translateY(20px) scale(0.9)';

    setTimeout(() => {
      card.remove();
      const container = document.getElementById('ingestion-progress-container');
      if (container && container.children.length === 0) {
        container.remove();
      }
    }, 400);
  }, 2500);
}

// Global mouseup handling for drag range selection completion
document.addEventListener('mouseup', () => {
  if (isDraggingRange) {
    isDraggingRange = false;
    if (gridApi && dragStartCell && dragEndCell) {
      refreshRange(gridApi, dragStartCell, dragEndCell);
    }
  }
});

// Transaction Mode Helpers
function updateTxModeUI() {
  const pendingCount = Object.keys(pendingTxEdits).length;
  if (txModeActive) {
    txModeToggle.checked = true;
    if (pendingCount > 0) {
      txApplyBtn.style.display = 'inline-block';
      txApplyBtn.textContent = `Apply (${pendingCount})`;
      txDiscardBtn.style.display = 'inline-block';
      performanceLog.textContent = `Tx Mode active: ${pendingCount} edits pending`;
    } else {
      txApplyBtn.style.display = 'none';
      txDiscardBtn.style.display = 'none';
      performanceLog.textContent = 'Tx Mode active (No pending edits)';
    }
  } else {
    txModeToggle.checked = false;
    txApplyBtn.style.display = 'none';
    txDiscardBtn.style.display = 'none';
    performanceLog.textContent = 'Ready';
  }
}

async function applyPendingTxEdits() {
  const pendingCount = Object.keys(pendingTxEdits).length;
  if (pendingCount === 0) return;

  performanceLog.textContent = 'Applying batch transaction updates...';
  const applyStartTime = performance.now();

  const grouped = {};
  Object.values(pendingTxEdits).forEach(edit => {
    if (!grouped[edit.rowId]) {
      grouped[edit.rowId] = {};
    }
    grouped[edit.rowId][edit.colId] = edit.newValue;
  });

  const updates = Object.keys(grouped).map(rowId => ({
    row_id: rowId,
    updates: grouped[rowId],
    source_name: 'user',
    updated_by: CURRENT_USER
  }));

  const payload = {
    updates: updates,
    silent: false
  };

  try {
    const res = await fetch(`${API_BASE}/tables/${currentTable}/data/updates`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      pageCache.clear();
      const result = await res.json();
      const saveTime = (performance.now() - applyStartTime).toFixed(1);

      // Update cell is_overwrite status locally on the latest nodes directly
      Object.values(pendingTxEdits).forEach(edit => {
        const { rowId, colId, newValue, data } = edit;
        const latestNode = gridApi.getRowNode(rowId);
        const latestData = latestNode ? latestNode.data : data;
        if (latestData) {
          ensureCellObject(latestData, colId);
          latestData.data[colId].value = newValue;
          latestData.data[colId].is_overwrite = true;
          latestData.updated_at = getLocalTimeString();
        }
      });

      pendingTxEdits = {};
      txModeActive = txModeToggle.checked;
      updateTxModeUI();
      updateGridSortState();
      gridApi.refreshCells({ force: true });

      performanceLog.textContent = `Applied batch updates in ${saveTime}ms (${result.change_count} cells updated)`;
    } else {
      const errData = await res.json().catch(() => ({}));
      const errMsg = errData.detail || 'Save failed';
      throw new Error(errMsg);
    }
  } catch (err) {
    console.error('Batch apply failed', err);
    alert(`일괄 적용 실패: ${err.message}`);
    performanceLog.textContent = '❌ Batch apply failed';
  }
}

function discardPendingTxEdits() {
  const pendingCount = Object.keys(pendingTxEdits).length;
  if (pendingCount === 0) return;

  Object.values(pendingTxEdits).forEach(edit => {
    const { rowId, colId, oldValue, oldIsOverwrite, data } = edit;
    const latestNode = gridApi.getRowNode(rowId);
    const latestData = latestNode ? latestNode.data : data;
    if (latestData) {
      ensureCellObject(latestData, colId);
      latestData.data[colId].value = oldValue;
      latestData.data[colId].is_overwrite = oldIsOverwrite;
    }
  });

  pendingTxEdits = {};
  txModeActive = txModeToggle.checked;
  updateTxModeUI();
  updateGridSortState();
  gridApi.refreshCells({ force: true });
  performanceLog.textContent = 'Pending updates discarded';
}

// Start Application
init();
console.log('AssyManager Client Bundle Loaded. Version Hash Buster: 019ee29f-b2fb-727e');

