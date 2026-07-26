import { WS_URL } from './config.js';
import { state } from './state.js';
import { elements } from './dom.js';
import { checkServerHealth, loadTables, fetchData } from './api.js';
import { showIngestionProgress, finishIngestionProgress, showToast, getLocalTimeString } from './utils.js';
import { updateSelectedCellUI, updatePageCacheOnUpsert, updatePageCacheOnDelete, notifyEnrichmentTableEvent } from './ui.js';
import { triggerHistoryReloadDebounced, appendHistoryLocally } from './timeline.js';
import { updateGridSortState, updateLoadedCount, updatePaginationUI } from './grid.js';

// Initialize Real-time synchronization via WebSocket
export function initWebSocket() {
  if (state.ws) {
    try {
      state.ws.onopen = null;
      state.ws.onclose = null;
      state.ws.onerror = null;
      state.ws.onmessage = null;
      state.ws.close();
    } catch (e) { }
    state.ws = null;
  }

  state.ws = new WebSocket(WS_URL);

  state.ws.onopen = async () => {
    elements.wsStatus.textContent = 'WS: CONNECTED';
    elements.wsStatus.className = 'status-badge online';
    document.querySelector('.status-ws').classList.add('active');
    state.wsReconnectDelay = 1000; // Reset backoff delay on successful connection
    console.log('[WebSocket] Connected successfully. Syncing API health status...');

    // API 복구 감지 및 동기화 수행
    await checkServerHealth();

    // API가 살아있고 테이블 목록이 비어있다면 로드
    const tableSelectedVal = elements.tableSelect?.value;
    if (!tableSelectedVal) {
      await loadTables();
    } else if (state.currentTable) {
      // 오프라인 동안 유실된 데이터 동기화를 위해 현재 테이블 데이터 리로드
      fetchData(true);
    }
  };

  state.ws.onclose = () => {
    elements.wsStatus.textContent = 'WS: DISCONNECTED';
    elements.wsStatus.className = 'status-badge offline';
    document.querySelector('.status-ws').classList.remove('active');

    console.log(`[WebSocket] Connection closed. Reconnecting in ${state.wsReconnectDelay}ms...`);
    setTimeout(initWebSocket, state.wsReconnectDelay);

    // Exponential backoff: double the delay up to 30 seconds
    state.wsReconnectDelay = Math.min(state.wsReconnectDelay * 2, 30000);
  };

  state.ws.onerror = (err) => {
    console.error('WebSocket error', err);
  };

  state.ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      handleWebSocketMessage(msg);
    } catch (err) {
      console.error('WebSocket parsing error', err);
    }
  };
}

// Feature 2: WebSocket message processing for Real-time delta sync
export function handleWebSocketMessage(msg) {
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
    // 데모 수집기가 2~3분마다 도는 환경에서 이 알림이 가장 많이 쌓인다 →
    // **성공은 한 줄로 집계**하고(dedupeKey), 실패는 집계하지 않아 개별 사유가 남게 한다.
    showToast(
      message,
      status === 'SUCCESS' ? 'success' : 'error',
      status === 'SUCCESS' ? { dedupeKey: 'file_ingestion_completed' } : {},
    );

    // Finish floating progress bar
    finishIngestionProgress(msg.table_name, msg.filename, status, msg.error_msg);

    if (msg.table_name === state.currentTable) {
      state.pageCache.clear();
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
      if (state.activeHistoryTab !== 'global' && log.table_name !== state.currentTable) {
        return;
      }

      // Update currently focused cell UI if it matches the log
      if (state.selectedCell && log.row_id === state.selectedCell.rowId && log.column_name === state.selectedCell.colId) {
        state.selectedCell.value = log.new_value;
        updateSelectedCellUI();
      }

      appendHistoryLocally(log, false);
    });
  }

  // Enrichment 결손 배지: derived 테이블 이벤트는 source 테이블을 보는 중에도 도착하므로
  // currentTable 가드보다 앞에서 훅 (내부에서 관련 규칙 여부 판정, fire-and-forget)
  if (msg.event && msg.event.startsWith('batch_')) {
    notifyEnrichmentTableEvent(msg.table_name);
  }

  // 2. Perform table-specific data/grid updates
  if (msg.table_name !== state.currentTable) return;
  if (!state.gridApi) return;

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
      state.gridApi.applyTransaction({ add: normalizedItems });
      state.gridApi.refreshCells({ force: true });
      updateGridSortState();
      updateLoadedCount();
      elements.performanceLog.textContent = `⚡ Real-time created: ${items.length} rows added`;
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
      const rowNode = state.gridApi.getRowNode(rowId);

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
      const res = state.gridApi.applyTransaction({
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
      const flashNodes = allTargetRows.map(r => state.gridApi.getRowNode(r.row_id)).filter(Boolean);
      const flashColIds = Array.from(flashCols);

      if (flashNodes.length > 0 && flashColIds.length > 0) {
        state.gridApi.flashCells({
          rowNodes: flashNodes,
          columns: flashColIds,
          flashDelay: 1000
        });
      }

      // [강력한 화면 동기화] refreshCells 뿐만 아니라 redrawRows를 추가로 호출하여
      // AG-Grid가 강제 캐시 우회하고 완전히 해당 행들을 처음부터 다시 그리도록 지시
      if (flashNodes.length > 0) {
        state.gridApi.redrawRows({ rowNodes: flashNodes });
      }
      state.gridApi.refreshCells({ force: true });
      updateGridSortState();
      updateLoadedCount();

      elements.performanceLog.textContent = `⚡ Real-time synchronized: ${updatedRows.length} rows updated`;
    }
  } else if (event === 'batch_row_delete') {
    const rowIds = msg.row_ids || [];
    updatePageCacheOnDelete(rowIds);
    const deleteTx = rowIds.map(rid => ({ row_id: rid }));

    state.gridApi.applyTransaction({ remove: deleteTx });

    updateLoadedCount();
    elements.performanceLog.textContent = `🗑️ Real-time deleted: ${rowIds.length} rows removed`;

    if (state.selectedCell && rowIds.includes(state.selectedCell.rowId)) {
      state.selectedCell = null;
      updateSelectedCellUI();
      elements.timeline.innerHTML = '<li class="timeline-empty">Selected row deleted.</li>';
    }
  } else if (event === 'batch_refresh_required') {
    state.pageCache.clear();
    fetchData(true);
    if (window.triggerHistoryReloadDebounced) window.triggerHistoryReloadDebounced();
  }
}
