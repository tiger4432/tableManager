import { API_BASE, WS_URL, CURRENT_USER, pageLimit } from './config.js';
import { state } from './state.js';
import { elements } from './dom.js';
import { clearRangeSelection } from './clipboard.js';
import { updateSelectedCellUI, updateTxModeUI, updateEnrichmentBadge } from './ui.js';
import { renderGrid, updateGridSortState, updateLoadedCount, updatePaginationUI, ensureCellObject } from './grid.js';
import { loadHistory } from './timeline.js';
import { getLocalTimeString } from './utils.js';
import { refreshTraceEntry } from './trace_launch.js';

// Check backend server status
export async function checkServerHealth() {
  try {
    const res = await fetch(`${API_BASE}/tables`);
    if (res.ok) {
      elements.serverStatus.textContent = 'API: ONLINE';
      elements.serverStatus.className = 'status-badge online';
    } else {
      throw new Error();
    }
  } catch (err) {
    elements.serverStatus.textContent = 'API: OFFLINE';
    elements.serverStatus.className = 'status-badge offline';
    elements.performanceLog.textContent = 'Error connecting to database server';
  }
}

// Load available tables
export async function loadTables() {
  try {
    const res = await fetch(`${API_BASE}/tables`);
    const data = await res.json();
    elements.tableSelect.innerHTML = '';

    if (data.tables && data.tables.length > 0) {
      data.tables.forEach(table => {
        const option = document.createElement('option');
        option.value = table;
        option.textContent = table;
        elements.tableSelect.appendChild(option);
      });

      // Auto select first table
      const firstTable = data.tables[0];
      elements.tableSelect.value = firstTable;
      await switchTable(firstTable);
    } else {
      elements.tableSelect.innerHTML = '<option value="">No tables found</option>';
    }
  } catch (err) {
    console.error('Failed to load tables', err);
    elements.tableSelect.innerHTML = '<option value="">Failed to load</option>';
  }
}

// Switch current working table
export async function switchTable(tableName) {
  state.currentTable = tableName;
  window.currentTable = tableName; // Expose globally for Desktop Wrapper
  elements.performanceLog.textContent = `Switching to ${tableName}...`;

  // Clean selected cell info
  state.selectedCell = null;
  clearRangeSelection();
  updateSelectedCellUI();

  // Discard pending edits on table switch
  state.pendingTxEdits = {};
  state.txModeActive = true;
  if (elements.txModeToggle) elements.txModeToggle.checked = true;
  updateTxModeUI();

  // Reset transaction filter
  state.currentTransactionId = null;
  if (elements.txFilterBanner) elements.txFilterBanner.style.display = 'none';
  if (elements.bannerTxId) elements.bannerTxId.textContent = '';

  // Load Schema
  await loadSchema(tableName);
  // Re-create empty grid to bind new columns
  renderGrid([]);
  // Fetch initial chunk of data (reset skip to 0)
  await fetchData(true);

  // Reset active history tab to global when switching tables to avoid empty screen
  state.activeHistoryTab = 'global';
  elements.tabGlobalBtn.classList.add('active');
  elements.tabCellBtn.classList.remove('active');
  elements.tabRowBtn.classList.remove('active');
  await loadHistory();

  // Enrichment 결손 배지: fire-and-forget (테이블 전환을 블로킹하지 않음, 실패 무음)
  updateEnrichmentBadge();

  // G2 추적 진입점: 현재 테이블의 그래프 매핑 여부 재판정 (fire-and-forget, 실패 무음)
  refreshTraceEntry();
}

// Load table column schema
export async function loadSchema(tableName) {
  try {
    const res = await fetch(`${API_BASE}/tables/${tableName}/schema`);
    const data = await res.json();
    state.currentColumns = data.columns || [];
    state.currentColumnTypes = data.column_types || {};
    state.currentBusinessKey = data.business_key || '';
    state.currentCompositeKeySources = data.composite_key_source || [];

    // Fill search columns dropdown
    if (elements.searchCols) {
      elements.searchCols.innerHTML = '<option value="">All Columns</option>';
      state.currentColumns.forEach(col => {
        if (col !== 'created_at' && col !== 'updated_at') {
          const option = document.createElement('option');
          option.value = col;
          option.textContent = col;
          elements.searchCols.appendChild(option);
        }
      });
    }
  } catch (err) {
    console.error('Failed to load schema', err);
    elements.performanceLog.textContent = 'Schema load error';
  }
}

// Fetch row data and render inside AG-Grid (Handles Pagination)
export async function fetchData(resetSkip = true) {
  if (!state.currentTable || state.isLoadingMore) return;

  if (resetSkip) {
    state.pageCache.clear();
    clearRangeSelection();
    state.currentSkip = 0;
    state.hasMoreData = true;
    state.allDataLoaded = false;
  } else {
    if (state.viewMode !== 'infinite' && state.pageCache.has(state.currentSkip)) {
      const cached = state.pageCache.get(state.currentSkip);
      state.gridApi.setGridOption('rowData', cached.data);
      updateGridSortState();
      updateLoadedCount(cached.data.length);
      elements.totalRowsCount.textContent = `Matches: ${cached.total}`;
      updatePaginationUI(cached.total);
      elements.performanceLog.textContent = `Loaded ${cached.data.length} rows from client cache`;
      return;
    }
  }

  state.isLoadingMore = true;
  elements.performanceLog.textContent = 'Fetching data...';

  const startTime = performance.now();

  const q = elements.globalSearch ? elements.globalSearch.value.trim() : '';
  const cols = elements.searchCols ? elements.searchCols.value : '';
  const sortLatest = elements.sortLatestToggle.checked;
  const filterModel = state.gridApi ? state.gridApi.getFilterModel() : {};
  const filterStr = Object.keys(filterModel).length > 0 ? JSON.stringify(filterModel) : '';

  let url = `${API_BASE}/tables/${state.currentTable}/data?skip=${state.currentSkip}&limit=${pageLimit}`;
  url += `&order_by=${sortLatest ? 'updated_at' : 'row_id'}&order_desc=${sortLatest}`;
  if (state.currentTransactionId) {
    url += `&transaction_id=${state.currentTransactionId}`;
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
      state.hasMoreData = false;
    }

    // Render rowData depending on View Mode
    if (state.viewMode === 'infinite') {
      if (resetSkip || state.currentSkip === 0) {
        state.gridApi.setGridOption('rowData', result.data);
      } else {
        state.gridApi.applyTransaction({ add: result.data });
      }
    } else {
      state.gridApi.setGridOption('rowData', result.data);
    }
    updateGridSortState();

    // Update Counts (Zero-lag counter concept)
    updateLoadedCount();
    elements.totalRowsCount.textContent = `Matches: ${result.total}`;

    // Update Pagination UI
    updatePaginationUI(result.total);

    elements.performanceLog.textContent = `Loaded ${result.data.length} rows in ${fetchTime}ms`;

    // Save to Cache
    if (state.viewMode !== 'infinite') {
      state.pageCache.set(state.currentSkip, { data: result.data, total: result.total });
    }

    state.isLoadingMore = false;
  } catch (err) {
    console.error('Failed to fetch data', err);
    elements.performanceLog.textContent = 'Data fetch failed';
    state.isLoadingMore = false;
  }
}

// Handle inline editing updates to DB
export async function handleCellEdit(event) {
  const { data, colDef, newValue, oldValue } = event;
  const colId = colDef.field;
  const rowId = data.row_id;

  if (newValue === oldValue) return;

  // 이전 상태 복구를 위해 저장
  const oldCell = data.data?.[colId];
  const oldIsOverwrite = oldCell ? oldCell.is_overwrite : false;
  const oldPrioritySource = oldCell ? oldCell.priority_source : null;

  // --- 타입 검사 및 변환 추가 ---
  let finalValue = newValue;
  const colTypes = state.currentColumnTypes || {};
  const colType = colTypes[colId] || 'string';
  if (colType === 'number') {
    if (newValue === '' || newValue === null || newValue === undefined) {
      finalValue = null;
    } else {
      const parsedVal = Number(newValue);
      if (isNaN(parsedVal)) {
        alert(`컬럼 '${colId}'의 값 '${newValue}'은(는) 올바른 숫자 형식이 아닙니다.`);
        // Rollback grid value & overwrite status
        const latestNode = state.gridApi.getRowNode(rowId);
        const latestData = latestNode ? latestNode.data : data;
        if (latestData) {
          ensureCellObject(latestData, colId);
          latestData.data[colId].value = oldValue;
          latestData.data[colId].is_overwrite = oldIsOverwrite;
          latestData.data[colId].priority_source = oldPrioritySource;
        }
        state.gridApi.refreshCells({ rowNodes: [latestNode].filter(Boolean), columns: [colId], force: true });
        elements.performanceLog.textContent = '❌ Invalid number format';
        return;
      }
      finalValue = parsedVal;
    }
  }

  // Intercept and stage if Tx Mode is active
  if (state.txModeActive) {
    const key = `${rowId}_${colId}`;
    if (!state.pendingTxEdits[key]) {
      state.pendingTxEdits[key] = {
        rowId,
        colId,
        newValue: finalValue,
        oldValue: oldValue,
        oldIsOverwrite: oldIsOverwrite,
        data: data
      };
    } else {
      state.pendingTxEdits[key].newValue = finalValue;
    }

    const latestNode = state.gridApi.getRowNode(rowId);
    const latestData = latestNode ? latestNode.data : data;
    if (latestData) {
      ensureCellObject(latestData, colId);
      latestData.data[colId].value = finalValue;
    }

    updateTxModeUI();
    state.gridApi.refreshCells({ rowNodes: [latestNode].filter(Boolean), columns: [colId], force: true });
    return;
  }

  elements.performanceLog.textContent = 'Saving edit...';
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
    const res = await fetch(`${API_BASE}/tables/${state.currentTable}/data/updates`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      state.pageCache.clear();
      const result = await res.json();
      const saveTime = (performance.now() - editStartTime).toFixed(1);
      elements.performanceLog.textContent = `Saved in ${saveTime}ms (${result.change_count} cell updated)`;

      const latestNode = state.gridApi.getRowNode(rowId);
      const latestData = latestNode ? latestNode.data : data;

      ensureCellObject(latestData, colId);
      latestData.data[colId].value = finalValue;
      latestData.data[colId].is_overwrite = true;
      latestData.data[colId].priority_source = 'user';

      // Update updated_at timestamp locally to trigger sort update
      latestData.updated_at = getLocalTimeString();

      state.gridApi.refreshCells({
        rowNodes: [latestNode].filter(Boolean),
        columns: [colId, 'updated_at'],
        force: true
      });

      // Refresh current focused cell UI if active
      if (state.selectedCell && state.selectedCell.rowId === rowId && state.selectedCell.colId === colId) {
        state.selectedCell.value = finalValue;
        updateSelectedCellUI();
      }
    } else {
      const errData = await res.json().catch(() => ({}));
      const errMsg = errData.detail || 'Save failed';
      throw new Error(errMsg);
    }
  } catch (err) {
    console.error('Cell update failed', err);
    alert(`수정 사항 저장 실패: ${err.message}`);
    elements.performanceLog.textContent = '❌ Edit failed to save';

    // Rollback grid value & overwrite status
    const latestNode = state.gridApi.getRowNode(rowId);
    const latestData = latestNode ? latestNode.data : data;
    if (latestData) {
      ensureCellObject(latestData, colId);
      latestData.data[colId].value = oldValue;
      latestData.data[colId].is_overwrite = oldIsOverwrite;
      latestData.data[colId].priority_source = oldPrioritySource;
    }
    state.gridApi.refreshCells({ rowNodes: [latestNode].filter(Boolean), columns: [colId], force: true });
  }
}

// Add Empty Rows
export async function addRows(count) {
  if (!state.currentTable) return;
  elements.performanceLog.textContent = `Creating ${count} empty row(s)...`;
  try {
    const res = await fetch(`${API_BASE}/tables/${state.currentTable}/rows?count=${count}&user_name=${encodeURIComponent(CURRENT_USER)}`, {
      method: 'POST'
    });
    if (res.ok) {
      elements.performanceLog.textContent = `${count} empty row(s) created successfully`;
    } else {
      throw new Error('Create failed');
    }
  } catch (err) {
    console.error('Failed to create row(s)', err);
    elements.performanceLog.textContent = '❌ Failed to create row(s)';
  }
}

// Delete selected rows batch
export async function deleteSelectedRows() {
  if (!state.gridApi) return;
  const selectedNodes = state.gridApi.getSelectedNodes();
  if (selectedNodes.length === 0) {
    alert('No rows selected for deletion');
    return;
  }

  const rowIds = selectedNodes.map(node => node.data.row_id).filter(Boolean);
  if (rowIds.length === 0) return;

  if (!confirm(`Are you sure you want to permanently delete the selected ${rowIds.length} rows?`)) return;

  elements.performanceLog.textContent = 'Deleting selected rows...';
  try {
    const res = await fetch(`${API_BASE}/tables/${state.currentTable}/rows/batch_delete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        row_ids: rowIds,
        user_name: CURRENT_USER
      })
    });

    if (res.ok) {
      state.pageCache.clear();
      const result = await res.json();
      elements.performanceLog.textContent = `Deleted ${result.deleted_count} rows successfully`;
    } else {
      throw new Error('Batch delete request failed');
    }
  } catch (err) {
    console.error(err);
    elements.performanceLog.textContent = '❌ Failed to delete selected rows';
  }
}
