import {
  WS_URL, WS_RECONNECT_BASE_MS, WS_RECONNECT_CEILING_MS, WS_RECONNECT_JITTER,
  WS_HEALTHY_SESSION_MS, WS_WAKE_MIN_GAP_MS
} from './config.js';
import { state } from './state.js';
import { elements } from './dom.js';
import { checkServerHealth, loadTables, fetchData } from './api.js';
import { showIngestionProgress, finishIngestionProgress, showToast, getLocalTimeString } from './utils.js';
import { updateSelectedCellUI, updatePageCacheOnUpsert, updatePageCacheOnDelete, notifyEnrichmentTableEvent } from './ui.js';
import { triggerHistoryReloadDebounced, appendHistoryLocally } from './timeline.js';
import { updateGridSortState, updateLoadedCount, updatePaginationUI } from './grid.js';

/**
 * Queue the next reconnect attempt and advance the backoff ladder.
 *
 * ONE PENDING RETRY AT A TIME, ENFORCED. The previous code called `setTimeout(initWebSocket, …)`
 * directly from `onclose` and kept no handle, so nothing could tell whether a retry was already
 * queued and nothing could cancel one. Both are needed now: the wake signal has to cancel the
 * wait rather than open a competing socket.
 *
 * Returns the delay actually scheduled (post-jitter), for the log line.
 */
function scheduleReconnect() {
  if (state.wsRetryTimer !== null) return 0;
  // Downward-only jitter: [0.75, 1.0] x the current rung. See WS_RECONNECT_JITTER in config.js
  // for why it is not the usual symmetric band.
  const waitMs = Math.round(state.wsReconnectDelay * (1 - WS_RECONNECT_JITTER * Math.random()));
  state.wsRetryTimer = setTimeout(() => {
    state.wsRetryTimer = null;
    initWebSocket();
  }, waitMs);
  state.wsReconnectDelay = Math.min(state.wsReconnectDelay * 2, WS_RECONNECT_CEILING_MS);
  return waitMs;
}

/**
 * A signal arrived saying the situation probably changed — retry NOW instead of waiting out
 * the rest of the backoff.
 *
 * WHY A SIGNAL AND NOT JUST A SHORTER TIMER. The common case is a person restarting the server
 * and then looking at the page. Regaining focus, or the machine coming back online, is strong
 * evidence the world changed, and acting on it makes that case fast WITHOUT probing harder in
 * the background — a page nobody is looking at keeps its ladder.
 *
 * REFUSES TO ACT when a socket is already OPEN or CONNECTING (0/1): the point is to shorten a
 * wait, never to open a second socket next to one that is still negotiating.
 */
function wakeNow(reason) {
  const readyState = state.ws ? state.ws.readyState : 3;
  if (readyState === 0 || readyState === 1) return false;   // CONNECTING / OPEN — nothing to do
  const now = Date.now();
  if (now - state.wsLastWakeAt < WS_WAKE_MIN_GAP_MS) return false;
  state.wsLastWakeAt = now;
  // The evidence says the situation changed, so the ladder's accumulated pessimism is stale.
  state.wsReconnectDelay = WS_RECONNECT_BASE_MS;
  if (state.wsRetryTimer !== null) {
    clearTimeout(state.wsRetryTimer);
    state.wsRetryTimer = null;
  }
  console.log(`[WebSocket] ${reason} — reconnecting now instead of waiting out the backoff.`);
  initWebSocket();
  return true;
}

/**
 * Attach the wake signals ONCE for the life of the page.
 *
 * Called from `initWebSocket`, which runs on every reconnect — hence the latch. Without it the
 * listener set would grow by two on every reconnect, and a page that had been offline a while
 * would fire dozens of wake handlers on a single tab-focus.
 */
function installWakeSignals() {
  if (state.wsWakeSignalsInstalled) return;
  state.wsWakeSignalsInstalled = true;
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') wakeNow('페이지가 다시 표시됨');
  });
  window.addEventListener('online', () => wakeNow('네트워크가 복구됨'));
}

// Initialize Real-time synchronization via WebSocket
export function initWebSocket() {
  installWakeSignals();

  // A retry queued by `scheduleReconnect` is superseded by the connection we are about to open.
  // (Harmless in the timer's own path, which nulls this before calling us — it matters when
  // `initWebSocket` is entered from anywhere else.)
  if (state.wsRetryTimer !== null) {
    clearTimeout(state.wsRetryTimer);
    state.wsRetryTimer = null;
  }

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

  // 🔴 **여기서 배지를 쓰는 것이 이 줄의 요점이다.** 종전에는 `onopen`/`onclose`가 오기
  //    전까지 배지가 index.html의 초기값 `WS: Connecting` 그대로였고, 그래서 화면이
  //    **「소켓을 만들지 않았다」와 「만들었고 협상 중이다」를 같은 글자로** 보여 줬다.
  //    2026-08-04 운영 사고에서 「Connecting에서 홀드」라는 신고가 이 둘 중 어느 쪽인지
  //    끝까지 갈리지 않아 진단이 몇 시간 늦어졌다. 초기값과 **다른 문자열**이어야 하고,
  //    시도 횟수가 붙어야 재시도가 도는지 멈췄는지도 같은 배지에서 읽힌다.
  state.wsAttempts = (state.wsAttempts || 0) + 1;
  elements.wsStatus.textContent = `WS: 연결 시도 ${state.wsAttempts}`;
  elements.wsStatus.className = 'status-badge';
  console.log(`[WebSocket] attempt ${state.wsAttempts} -> ${WS_URL}`);

  state.ws.onopen = async () => {
    elements.wsStatus.textContent = 'WS: CONNECTED';
    elements.wsStatus.className = 'status-badge online';
    document.querySelector('.status-ws').classList.add('active');
    // Reset the backoff on a successful connection. This is what stops a healthy session from
    // inheriting a stale interval, so it stays unconditional — but see the flap guard in
    // `onclose`, which takes the reset back if this connection dies on arrival.
    state.wsPrevReconnectDelay = state.wsReconnectDelay;
    state.wsReconnectDelay = WS_RECONNECT_BASE_MS;
    state.wsOpenedAt = Date.now();
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

    // FLAP GUARD. `onopen` resets the ladder unconditionally, which is right for a session that
    // actually worked and wrong for a server that ACCEPTS and immediately drops: that pattern
    // would pin the client at the base delay forever, paying a full handshake plus
    // `checkServerHealth()` plus `fetchData(true)` every second. A connection that did not
    // survive `WS_HEALTHY_SESSION_MS` proved nothing, so its reset is taken back and the ladder
    // resumes from the rung it was on.
    const openedAt = state.wsOpenedAt;
    state.wsOpenedAt = 0;
    if (openedAt && Date.now() - openedAt < WS_HEALTHY_SESSION_MS) {
      state.wsReconnectDelay = state.wsPrevReconnectDelay;
    }

    const waitMs = scheduleReconnect();
    console.log(`[WebSocket] Connection closed. Reconnecting in ${waitMs}ms...`);
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
