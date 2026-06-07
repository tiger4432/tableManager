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
let ws = null;
let selectedCell = null; // { rowId, colId, value, rowIndex }
let activeHistoryTab = 'global'; // 'global' | 'cell' | 'row'
let dragStartCell = null; // { rowIndex, colId }
let dragEndCell = null;   // { rowIndex, colId }
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
const copyHeaderToggle = document.getElementById('copy-header-toggle');
const sortLatestToggle = document.getElementById('sort-latest-toggle');
const viewModeSelect = document.getElementById('view-mode-select');
const loadAllBtn = document.getElementById('load-all-btn');
const loadCsvBtn = document.getElementById('load-csv-btn');

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
  if (cachedCopyHeader !== null) {
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
  copyHeaderToggle.addEventListener('change', () => {
    localStorage.setItem('copyHeader', copyHeaderToggle.checked);
  });

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
  }

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
          try { await writableStream.abort(); } catch (e) {}
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

// Render grid layout using AG-Grid Core
function renderGrid(initialRows) {
  const gridDiv = document.querySelector('#myGrid');
  
  // Destroy existing grid if exists
  if (gridApi) {
    gridApi.destroy();
    gridApi = null;
  }
  
  // Build Column Definitions dynamically based on schema
  const columnDefs = currentColumns.map((col, index) => {
    const isSystem = ['created_at', 'updated_at', 'row_id', 'id', 'updated_by'].includes(col);
    const colTypes = currentColumnTypes || {};
    const colType = colTypes[col] || 'string';
    
    const colDef = {
      headerName: col.toUpperCase(),
      field: col,
      editable: !isSystem,
      sortable: true,
      filter: true,
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
        if (!params.data.data) params.data.data = {};
        if (!params.data.data[col]) params.data.data[col] = {};
        
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
  
  // Grid Configurations
  const gridOptions = {
    theme: 'legacy',
    columnDefs: columnDefs,
    rowData: initialRows,
    suppressSortOnDataChange: true,
    getRowId: (params) => params.data?.row_id || params.data?.id, // Robust fallback
    defaultColDef: {
      flex: 1,
      minWidth: 120,
      floatingFilter: true, // Display inline search box under each column header
      suppressKeyboardEvent: (params) => {
        const event = params.event;
        const key = event.key;
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
    // Range selection mouse drag event handling
    onCellMouseDown: (event) => {
      if (event.event.button !== 0) return;
      if (event.column.getColId() === '#') return;

      const isShift = event.event.shiftKey;
      const currRow = event.rowIndex;
      const currCol = event.column.getColId();

      if (isShift) {
        if (dragStartCell) {
          dragEndCell = { rowIndex: currRow, colId: currCol };
        } else {
          dragStartCell = { rowIndex: currRow, colId: currCol };
          dragEndCell = { rowIndex: currRow, colId: currCol };
        }
        isDraggingRange = false;
      } else {
        isDraggingRange = true;
        dragStartCell = { rowIndex: currRow, colId: currCol };
        dragEndCell = { rowIndex: currRow, colId: currCol };
      }
      
      event.api.refreshCells({ force: true });
    },
    onCellMouseOver: (event) => {
      if (!isDraggingRange || !dragStartCell) return;
      if (event.column.getColId() === '#') return;

      const currRow = event.rowIndex;
      const currCol = event.column.getColId();

      if (dragEndCell.rowIndex !== currRow || dragEndCell.colId !== currCol) {
        dragEndCell = { rowIndex: currRow, colId: currCol };
        event.api.refreshCells({ force: true });
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
        if (!data.data) data.data = {};
        if (!data.data[colId]) data.data[colId] = {};
        data.data[colId].value = oldValue;
        data.data[colId].is_overwrite = oldIsOverwrite;
        gridApi.applyTransaction({ update: [data] });
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

    if (!data.data) data.data = {};
    if (!data.data[colId]) data.data[colId] = {};
    data.data[colId].value = finalValue;
    
    // Trigger local update and refresh (do not update updated_at to prevent sort key changes)
    gridApi.applyTransaction({ update: [data] });
    
    updateTxModeUI();
    gridApi.refreshCells({ force: true });
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

      // Update cell is_overwrite status in local row data structure to trigger CSS highlight
      if (!data.data) data.data = {};
      if (!data.data[colId]) data.data[colId] = {};

      data.data[colId].value = finalValue;
      data.data[colId].is_overwrite = true;
      
      // Update updated_at timestamp locally to trigger sort update
      data.updated_at = getLocalTimeString();

      // Re-apply row transaction locally to trigger cellClassRules refresh
      gridApi.applyTransaction({ update: [data] });

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
    if (!data.data) data.data = {};
    if (!data.data[colId]) data.data[colId] = {};
    data.data[colId].value = oldValue;
    data.data[colId].is_overwrite = oldIsOverwrite;
    gridApi.applyTransaction({ update: [data] });
  }
}

// Initialize Real-time synchronization via WebSocket
function initWebSocket() {
  if (ws) {
    ws.close();
  }

  ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    wsStatus.textContent = 'WS: CONNECTED';
    wsStatus.className = 'status-badge online';
    document.querySelector('.status-ws').classList.add('active');
  };

  ws.onclose = () => {
    wsStatus.textContent = 'WS: DISCONNECTED';
    wsStatus.className = 'status-badge offline';
    document.querySelector('.status-ws').classList.remove('active');

    // Reconnect in 3s (matches PySide6 retry interval)
    setTimeout(initWebSocket, 3000);
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
  // 1. Process and append audit logs to local history cache first (independent of currentTable check, especially for global history)
  const createdLogs = msg.created_logs || [];
  if (createdLogs.length > 0) {
    let updatedHistory = false;
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
      
      appendHistoryLocally(log, true);
      updatedHistory = true;
    });
    
    if (updatedHistory) {
      if (activeHistoryTab === 'global') {
        renderGlobalTimeline();
      } else if (selectedCell) {
        renderTimeline(cellRowHistoryData);
      }
    }
  }

  // 2. Perform table-specific data/grid updates
  if (msg.table_name !== currentTable) return;
  if (!gridApi) return;

  const event = msg.event;

  if (event === 'batch_row_create') {
    const items = msg.items || [];
    if (items.length > 0) {
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
    const updatedRows = [];
    const addedRows = [];
    const flashCols = new Set();
    items.forEach(item => {
      const rowId = item.row_id;
      const rowNode = gridApi.getRowNode(rowId);

      if (rowNode) {
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

      // Update totals and force cell re-render
      gridApi.refreshCells({ force: true });
      updateGridSortState();
      updateLoadedCount();

      performanceLog.textContent = `⚡ Real-time synchronized: ${updatedRows.length} rows updated`;
    }
  } else if (event === 'batch_row_delete') {
    const rowIds = msg.row_ids || [];
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
    // Large bulk updates -> do not refresh grid to prevent UI disruption, only update cache and history
    if (createdLogs.length === 0) {
      triggerHistoryReloadDebounced();
    }
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

// Render history logs in a vertical timeline UI card structure
function renderTimeline(logs) {
  timeline.innerHTML = '';
  
  if (!logs || logs.length === 0) {
    timeline.innerHTML = '<li class="timeline-empty">No change history recorded.</li>';
    return;
  }
  
  logs.forEach(log => {
    const li = document.createElement('li');
    li.className = 'timeline-item';
    li.style.cursor = 'pointer'; // Make timeline cards clickable
    
    // Add type tag (e.g., user vs system)
    const isUser = log.updated_by !== 'system';
    li.classList.add(isUser ? 'user-change' : 'system-change');
    if (log.is_row_deleted) {
      li.classList.add('deleted-row-log');
    }
    
    // Highlight if active transaction context
    const isCurrentTx = log.transaction_id && log.transaction_id === currentTransactionId;
    if (isCurrentTx) {
      li.classList.add('active-tx-log');
    }
    
    // Format timestamp
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
    
    // Feature 1.5: Bind click to jump navigator sequence
    li.addEventListener('click', (e) => {
      if (e.target.closest('.filter-tx-btn')) {
        e.stopPropagation();
        const txId = e.target.closest('.filter-tx-btn').dataset.txId;
        setTransactionFilter(txId);
      } else {
        navigateToLog(log);
      }
    });
    
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
  
  globalHistoryData.forEach((group, index) => {
    const txId = group.transaction_id;
    const isSummary = group.total_count > 1;
    const baseLog = group.logs[0];
    if (!baseLog) return;
    
    const li = document.createElement('li');
    li.className = 'timeline-item';
    if (txId) {
      li.dataset.txId = txId;
    }
    
    // Highlight if active transaction context
    const isCurrentTx = txId && txId === currentTransactionId;
    if (isCurrentTx) {
      li.classList.add('active-tx-log');
    }
    
    // Add tag styling based on creator/type
    const user = baseLog.updated_by || 'system';
    const isUser = user !== 'system';
    li.classList.add(isUser ? 'user-change' : 'system-change');
    
    // Format timestamp
    const dateStr = new Date(baseLog.timestamp).toLocaleString();
    
    // Determine title text and color styling
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
      
    // HTML structure for card
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
    
    // Interactions
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
          
          // Check if we need to load detailed logs
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
    
    timeline.appendChild(li);
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
      renderGlobalTimeline();
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
    renderTimeline(cellRowHistoryData);
  }
}

// Range selection helper functions
function isCellInRange(rowIndex, colId) {
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

function clearRangeSelection() {
  dragStartCell = null;
  dragEndCell = null;
  isDraggingRange = false;
}

function getRangeSelectedTSV() {
  if (!dragStartCell || !dragEndCell || !gridApi) return '';

  const allCols = gridApi.getColumns().map(c => c.getColId());
  const startColIdx = allCols.indexOf(dragStartCell.colId);
  const endColIdx = allCols.indexOf(dragEndCell.colId);

  if (startColIdx === -1 || endColIdx === -1) return '';

  const minColIdx = Math.min(startColIdx, endColIdx);
  const maxColIdx = Math.max(startColIdx, endColIdx);
  const minRowIdx = Math.min(dragStartCell.rowIndex, dragEndCell.rowIndex);
  const maxRowIdx = Math.max(dragStartCell.rowIndex, dragEndCell.rowIndex);

  // Exclude non-business/non-system UI helper columns (like '#' or ag-grid selection '0' column)
  const colsToCopy = allCols.slice(minColIdx, maxColIdx + 1).filter(c => {
    if (c === '#' || /^\d+$/.test(c)) return false;
    return currentColumns.includes(c) || ['row_id', 'created_at', 'updated_at'].includes(c);
  });
  if (colsToCopy.length === 0) return '';

  let tsvRows = [];

  // Copy Header 토글 상태 확인 및 헤더 한 행 삽입
  const includeHeaders = copyHeaderToggle && copyHeaderToggle.checked;
  if (includeHeaders) {
    tsvRows.push(colsToCopy.map(c => c.toUpperCase()).join('\t'));
  }

  for (let r = minRowIdx; r <= maxRowIdx; r++) {
    const rowNode = gridApi.getDisplayedRowAtIndex(r);
    if (!rowNode || !rowNode.data) continue;

    let rowVals = [];
    colsToCopy.forEach(col => {
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
      // Sanitize tab and newline characters in string
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
    const activeEl = document.activeElement;
    if (!gridApi || !activeEl || !activeEl.closest('#myGrid')) return;

    const focusedCell = gridApi.getFocusedCell();
    if (!focusedCell) return;

    e.preventDefault();
    const clipboardText = e.clipboardData.getData('text/plain');
    if (!clipboardText) return;

    // Parse TSV clipboard
    const rows = clipboardText.replace(/\r\n/g, '\n').split('\n').filter(r => r.length > 0);
    const parsedMatrix = rows.map(r => r.split('\t').map(c => c.trim()));
    if (parsedMatrix.length === 0) return;

    performanceLog.textContent = 'Processing paste updates...';
    
    // Target columns configuration
    const allCols = gridApi.getColumns().map(c => c.getColId());
    const startColIndex = allCols.indexOf(focusedCell.column.getColId());
    const startRowIndex = focusedCell.rowIndex;

    const batchUpdates = [];
    const localUpdates = [];

    try {
      parsedMatrix.forEach((rowValues, rOffset) => {
        const targetRowIndex = startRowIndex + rOffset;
        const rowNode = gridApi.getDisplayedRowAtIndex(targetRowIndex);
        if (!rowNode || !rowNode.data) return;

        const rowId = rowNode.data.row_id;
        const rowUpdates = {};
        let hasUpdate = false;

        rowValues.forEach((val, cOffset) => {
          const targetColIndex = startColIndex + cOffset;
          if (targetColIndex >= allCols.length) return;

          const colId = allCols[targetColIndex];
          const isSystem = ['created_at', 'updated_at', 'row_id', 'id', 'updated_by'].includes(colId);
          if (isSystem) return;

          // --- 타입 검사 및 변환 추가 ---
          const colTypes = currentColumnTypes || {};
          const colType = colTypes[colId] || 'string';
          if (colType === 'number') {
            if (val === '' || val === null || val === undefined) {
              rowUpdates[colId] = null;
            } else {
              const parsedVal = Number(val);
              if (isNaN(parsedVal)) {
                alert(`컬럼 '${colId}'의 값 '${val}'은(는) 올바른 숫자 형식이 아닙니다.`);
                throw new Error(`컬럼 '${colId}'의 값 '${val}'은(는) 올바른 숫자 형식이 아닙니다.`);
              }
              rowUpdates[colId] = parsedVal;
            }
          } else {
            rowUpdates[colId] = val;
          }
          hasUpdate = true;
        });

        if (hasUpdate) {
          batchUpdates.push({
            row_id: rowId,
            updates: rowUpdates,
            source_name: 'user',
            updated_by: CURRENT_USER
          });

          // Prepare local cache structure updates
          const oldRowData = rowNode.data;
          if (txModeActive) {
            // Stage edits in pendingTxEdits
            Object.keys(rowUpdates).forEach(col => {
              const key = `${rowId}_${col}`;
              if (!pendingTxEdits[key]) {
                const oldValue = oldRowData.data?.[col]?.value !== undefined ? oldRowData.data[col].value : '';
                const oldIsOverwrite = oldRowData.data?.[col]?.is_overwrite === true;
                pendingTxEdits[key] = {
                  rowId,
                  colId: col,
                  newValue: rowUpdates[col],
                  oldValue: oldValue,
                  oldIsOverwrite: oldIsOverwrite,
                  data: oldRowData
                };
              } else {
                pendingTxEdits[key].newValue = rowUpdates[col];
              }
            });

            const newRowData = {
              ...oldRowData,
              data: { ...oldRowData.data }
            };
            Object.keys(rowUpdates).forEach(col => {
              if (!newRowData.data[col]) newRowData.data[col] = {};
              newRowData.data[col].value = rowUpdates[col];
            });
            localUpdates.push(newRowData);
          } else {
            const newRowData = {
              ...oldRowData,
              data: { ...oldRowData.data },
              updated_at: getLocalTimeString()
            };
            Object.keys(rowUpdates).forEach(col => {
              if (!newRowData.data[col]) newRowData.data[col] = {};
              newRowData.data[col].value = rowUpdates[col];
              newRowData.data[col].is_overwrite = true;
            });
            localUpdates.push(newRowData);
          }
        }
      });

      if (txModeActive) {
        if (localUpdates.length > 0) {
          gridApi.applyTransaction({ update: localUpdates });
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
          
          // Fast-apply local data values
          gridApi.applyTransaction({ update: localUpdates });
          
          // Force sort update to push modified rows to the top
          updateGridSortState();

          // Sync selected cell UI if inside pasted range
          if (selectedCell) {
            const matchedUpdate = batchUpdates.find(u => u.row_id === selectedCell.rowId);
            if (matchedUpdate && matchedUpdate.updates[selectedCell.colId] !== undefined) {
              selectedCell.value = matchedUpdate.updates[selectedCell.colId];
              updateSelectedCellUI();
            }
          }

          // History updates will be handled by the WebSocket stream
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
    const activeEl = document.activeElement;
    if (!gridApi || !activeEl || !activeEl.closest('#myGrid')) return;

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
  const allCols = gridApi.getColumns().map(c => c.getColId());

  // 1. Check if range selection exists
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
  const rowsToUpdate = [];

  Object.keys(updateMapByRow).forEach(rowId => {
    const item = updateMapByRow[rowId];
    if (Object.keys(item.updates).length > 0) {
      updatesArray.push({
        row_id: rowId,
        updates: item.updates,
        source_name: 'user',
        updated_by: CURRENT_USER
      });

      const data = item.rowNode.data;
      if (!data.data) data.data = {};
      
      Object.keys(item.updates).forEach(colId => {
        if (!data.data[colId]) data.data[colId] = {};
        data.data[colId].value = item.updates[colId];
        data.data[colId].is_overwrite = true;
      });

      data.updated_at = getLocalTimeString();
      rowsToUpdate.push(data);
    }
  });

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

      // Apply grid local updates
      gridApi.applyTransaction({ update: rowsToUpdate });
      
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

// Feature 2: Smart Paste Parser via Form Upload
async function smartPasteViaIngestion() {
  try {
    const clipboardText = await navigator.clipboard.readText();
    if (!clipboardText.trim()) {
      alert('Clipboard is empty or does not contain text.');
      return;
    }

    performanceLog.textContent = 'Uploading clipboard text for parsing...';

    // Build log file representation via Blob
    const blob = new Blob([clipboardText], { type: 'text/plain' });
    const file = new File([blob], `web_smart_paste_${Date.now()}.log`, { type: 'text/plain' });

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
      showToast(`📋 스마트 붙여넣기 완료! (RAW 파일: ${savedFilename})`, 'success');
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
    toast.classList.add('hide');
    setTimeout(() => {
      toast.remove();
      if (container.children.length === 0) {
        container.remove();
      }
    }, 300);
  }, 5000);
}
window.showToast = showToast; // Expose globally for Desktop Wrapper

// Global mouseup handling for drag range selection completion
document.addEventListener('mouseup', () => {
  if (isDraggingRange) {
    isDraggingRange = false;
    if (gridApi) {
      gridApi.refreshCells({ force: true });
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
      
      // Update cell is_overwrite status locally
      Object.values(pendingTxEdits).forEach(edit => {
        const { data, colId, newValue } = edit;
        if (!data.data) data.data = {};
        if (!data.data[colId]) data.data[colId] = {};
        data.data[colId].value = newValue;
        data.data[colId].is_overwrite = true;
        data.updated_at = getLocalTimeString();
        gridApi.applyTransaction({ update: [data] });
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
    const { data, colId, oldValue, oldIsOverwrite } = edit;
    if (!data.data) data.data = {};
    if (!data.data[colId]) data.data[colId] = {};
    data.data[colId].value = oldValue;
    data.data[colId].is_overwrite = oldIsOverwrite;
    gridApi.applyTransaction({ update: [data] });
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
