// Ingestion Outbox Admin Dashboard client logic
const isDevServer = window.location.port === '5173';
const API_BASE = isDevServer ? 'http://127.0.0.1:8080' : window.location.origin;

// State Cache
let currentTab = 'outbox'; // 'outbox' or 'file'
let outboxPage = 1;
let outboxLimit = 10;
let outboxData = [];
let outboxTotal = 0;

let filePage = 1;
let fileLimit = 10;
let fileData = [];
let fileTotal = 0;

let selectedTxId = null;
let selectedFileId = null;
let activeEventInTx = null;

// DOM Elements
const tabOutboxBtn = document.getElementById('tab-outbox-btn');
const tabFileBtn = document.getElementById('tab-file-btn');
const outboxTableWrapper = document.getElementById('outbox-table-wrapper');
const fileTableWrapper = document.getElementById('file-table-wrapper');
const statusFilterSelect = document.getElementById('status-filter');

const outboxListBody = document.getElementById('outbox-list-body');
const fileListBody = document.getElementById('file-list-body');
const outboxEmptyState = document.getElementById('outbox-empty');
const fileEmptyState = document.getElementById('file-empty');

const totalCountSpan = document.getElementById('total-count');
const retryAllBtn = document.getElementById('retry-all-btn');
const refreshBtn = document.getElementById('refresh-btn');

const diagnosticsContent = document.getElementById('diagnostics-content');
const diagnosticsEmpty = document.getElementById('diagnostics-empty');
const txEventsSelectorBlock = document.getElementById('tx-events-selector-block');
const txEventsList = document.getElementById('tx-events-list');
const tracebackViewer = document.getElementById('traceback-viewer');
const payloadViewer = document.getElementById('payload-viewer');
const copyPayloadBtn = document.getElementById('copy-payload-btn');
const toastContainer = document.getElementById('toast-container');

// Pagination DOM Elements
const paginationInfo = document.getElementById('pagination-info');
const prevPageBtn = document.getElementById('prev-page-btn');
const nextPageBtn = document.getElementById('next-page-btn');
const pageIndicator = document.getElementById('page-indicator');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  fetchData();
  setupEventListeners();
});

function setupEventListeners() {
  // Tabs
  tabOutboxBtn.addEventListener('click', () => {
    if (currentTab === 'outbox') return;
    currentTab = 'outbox';
    tabOutboxBtn.classList.add('active');
    tabFileBtn.classList.remove('active');
    outboxTableWrapper.style.display = 'block';
    fileTableWrapper.style.display = 'none';
    statusFilterSelect.style.display = 'none';
    clearDiagnostics();
    fetchData();
  });

  tabFileBtn.addEventListener('click', () => {
    if (currentTab === 'file') return;
    currentTab = 'file';
    tabFileBtn.classList.add('active');
    tabOutboxBtn.classList.remove('active');
    fileTableWrapper.style.display = 'block';
    outboxTableWrapper.style.display = 'none';
    statusFilterSelect.style.display = 'block';
    clearDiagnostics();
    fetchData();
  });

  // Status filter change
  statusFilterSelect.addEventListener('change', () => {
    filePage = 1;
    fetchData();
  });

  // Actions
  refreshBtn.addEventListener('click', () => {
    fetchData();
    showToast('♻️ 실패 목록을 새로고침했습니다.', 'success');
  });

  retryAllBtn.addEventListener('click', async () => {
    const targetName = currentTab === 'outbox' ? '아웃박스 이벤트' : '파일 인제션';
    if (confirm(`실패 상태인 모든 ${targetName} 건을 재실행하시겠습니까?`)) {
      await retryAllFailed();
    }
  });

  copyPayloadBtn.addEventListener('click', () => {
    let payloadToCopy = null;
    if (currentTab === 'outbox' && activeEventInTx) {
      payloadToCopy = activeEventInTx.payload;
    } else if (currentTab === 'file' && selectedFileId) {
      const log = fileData.find(e => e.id === selectedFileId);
      if (log) {
        payloadToCopy = {
          id: log.id,
          filename: log.filename,
          filepath: log.filepath,
          table_name: log.table_name,
          retry_count: log.retry_count,
          created_at: log.created_at
        };
      }
    }

    if (payloadToCopy) {
      navigator.clipboard.writeText(JSON.stringify(payloadToCopy, null, 2))
        .then(() => showToast('📋 페이로드가 클립보드에 복사되었습니다.', 'success'))
        .catch(() => showToast('❌ 복사에 실패했습니다.', 'error'));
    }
  });

  // Pagination
  prevPageBtn.addEventListener('click', () => {
    if (currentTab === 'outbox' && outboxPage > 1) {
      outboxPage--;
      fetchData();
    } else if (currentTab === 'file' && filePage > 1) {
      filePage--;
      fetchData();
    }
  });

  nextPageBtn.addEventListener('click', () => {
    if (currentTab === 'outbox') {
      const maxPage = Math.ceil(outboxTotal / outboxLimit) || 1;
      if (outboxPage < maxPage) {
        outboxPage++;
        fetchData();
      }
    } else if (currentTab === 'file') {
      const maxPage = Math.ceil(fileTotal / fileLimit) || 1;
      if (filePage < maxPage) {
        filePage++;
        fetchData();
      }
    }
  });
}

// Fetch list of failed items depending on active tab
async function fetchData() {
  try {
    if (currentTab === 'outbox') {
      const res = await fetch(`${API_BASE}/admin/outbox/failed?page=${outboxPage}&limit=${outboxLimit}`);
      if (!res.ok) throw new Error('API fetch failed');
      const result = await res.json();
      
      outboxData = result.data || [];
      outboxTotal = result.total || 0;
      renderOutboxTable();
    } else {
      const statusVal = statusFilterSelect.value || 'FAILED';
      const res = await fetch(`${API_BASE}/admin/file-ingestion/logs?status=${statusVal}&page=${filePage}&limit=${fileLimit}`);
      if (!res.ok) throw new Error('API fetch failed');
      const result = await res.json();
      
      fileData = result.data || [];
      fileTotal = result.total || 0;
      renderFileTable();
    }
  } catch (err) {
    console.error('Failed to fetch failed items', err);
    showToast('❌ 실패 목록 로드 실패', 'error');
  }
}

// Render outbox table rows (Grouped by Transaction ID)
function renderOutboxTable() {
  outboxListBody.innerHTML = '';
  totalCountSpan.textContent = outboxTotal;

  if (outboxData.length === 0) {
    outboxEmptyState.style.display = 'flex';
    clearDiagnostics();
    updatePaginationFooter(0, 1, 1);
    return;
  }

  outboxEmptyState.style.display = 'none';

  outboxData.forEach(tx => {
    const row = document.createElement('tr');
    row.className = `table-row ${selectedTxId === tx.transaction_id ? 'active' : ''}`;
    row.dataset.txid = tx.transaction_id;
    
    // Parse time
    let timeStr = tx.failed_at || '';
    if (timeStr) {
      const dt = new Date(timeStr);
      timeStr = dt.toLocaleString();
    }

    const tablesJoined = tx.table_names.join(', ') || '-';
    const eventTypesJoined = tx.event_types.map(t => 
      `<span class="badge ${t === 'CREATE' ? 'badge-warning' : 'badge-danger'}" style="margin-right: 4px;">${t}</span>`
    ).join('');

    row.innerHTML = `
      <td style="font-family: var(--font-mono); font-size: 0.8rem; font-weight: bold; color: var(--color-primary); word-break: break-all;">${tx.transaction_id}</td>
      <td style="font-weight: 500;">${tablesJoined}</td>
      <td>${eventTypesJoined}</td>
      <td style="text-align: center; font-weight: bold; color: var(--color-warning);">${tx.retry_count}</td>
      <td style="color: var(--text-muted); font-size: 0.85rem;">${timeStr}</td>
      <td style="text-align: center;" onclick="event.stopPropagation()">
        <button class="glass-btn btn-primary btn-retry-tx" data-txid="${tx.transaction_id}" style="padding: 4px 10px; font-size: 0.75rem;">Retry</button>
      </td>
    `;

    // Row selection click listener
    row.addEventListener('click', () => {
      selectTxRow(tx);
    });

    // Individual retry click listener
    const retryBtn = row.querySelector('.btn-retry-tx');
    retryBtn.addEventListener('click', async () => {
      if (confirm(`트랜잭션 [${tx.transaction_id}] 내의 모든 이벤트를 다시 재시도하시겠습니까?`)) {
        await retryTransaction(tx.transaction_id);
      }
    });

    outboxListBody.appendChild(row);
  });

  // Restore diagnostics selection if selected tx still exists in fetched chunk
  if (selectedTxId) {
    const exists = outboxData.find(t => t.transaction_id === selectedTxId);
    if (exists) {
      selectTxRow(exists, activeEventInTx ? activeEventInTx.id : null);
    } else {
      clearDiagnostics();
    }
  }

  const maxPage = Math.ceil(outboxTotal / outboxLimit) || 1;
  updatePaginationFooter(outboxTotal, outboxPage, maxPage);
}

// Render file ingestion table rows
function renderFileTable() {
  fileListBody.innerHTML = '';
  totalCountSpan.textContent = fileTotal;

  if (fileData.length === 0) {
    fileEmptyState.style.display = 'flex';
    clearDiagnostics();
    updatePaginationFooter(0, 1, 1);
    return;
  }

  fileEmptyState.style.display = 'none';

  fileData.forEach(log => {
    const row = document.createElement('tr');
    row.className = `table-row ${selectedFileId === log.id ? 'active' : ''}`;
    row.dataset.id = log.id;
    
    // Parse time
    let timeStr = log.created_at || '';
    if (timeStr) {
      const dt = new Date(timeStr);
      timeStr = dt.toLocaleString();
    }

    const statusBadge = `<span class="badge ${log.status === 'SUCCESS' ? 'badge-success' : 'badge-danger'}">${log.status || 'FAILED'}</span>`;
    const retryBtnHtml = log.status === 'SUCCESS'
      ? `<button class="glass-btn btn-primary" style="padding: 4px 10px; font-size: 0.75rem; opacity: 0.5; cursor: not-allowed;" disabled>Retry</button>`
      : `<button class="glass-btn btn-primary btn-retry-file" data-id="${log.id}" style="padding: 4px 10px; font-size: 0.75rem;">Retry</button>`;

    row.innerHTML = `
      <td>${log.id}</td>
      <td style="font-weight: 500; color: #a6e3a1; word-break: break-all;">${log.filename}</td>
      <td style="font-weight: bold; color: var(--color-primary);">${log.table_name}</td>
      <td style="text-align: center;">${statusBadge}</td>
      <td style="text-align: center; font-weight: bold; color: var(--color-warning);">${log.retry_count}</td>
      <td style="color: var(--text-muted); font-size: 0.85rem;">${timeStr}</td>
      <td style="text-align: center;" onclick="event.stopPropagation()">
        ${retryBtnHtml}
      </td>
    `;

    // Row selection click listener
    row.addEventListener('click', () => {
      selectFileRow(log);
    });

    // Individual retry click listener
    const retryBtn = row.querySelector('.btn-retry-file');
    if (retryBtn) {
      retryBtn.addEventListener('click', async () => {
        if (confirm(`로그 ID #${log.id} 파일 인제션을 다시 재시도하시겠습니까?`)) {
          await retryFileIngestion(log.id);
        }
      });
    }

    fileListBody.appendChild(row);
  });

  // Restore diagnostics selection if selected file still exists in fetched chunk
  if (selectedFileId) {
    const exists = fileData.find(f => f.id === selectedFileId);
    if (exists) {
      selectFileRow(exists);
    } else {
      clearDiagnostics();
    }
  }

  const maxPage = Math.ceil(fileTotal / fileLimit) || 1;
  updatePaginationFooter(fileTotal, filePage, maxPage);
}

// Select Transaction Row
function selectTxRow(tx, forceSelectEventId = null) {
  selectedTxId = tx.transaction_id;
  selectedFileId = null;
  
  // Highlight row in list
  const rows = outboxListBody.querySelectorAll('.table-row');
  rows.forEach(r => {
    if (r.dataset.txid === tx.transaction_id) {
      r.classList.add('active');
    } else {
      r.classList.remove('active');
    }
  });

  // Diagnostics view toggle
  diagnosticsEmpty.style.display = 'none';
  diagnosticsContent.style.display = 'flex';

  if (tx.events && tx.events.length > 1) {
    // Show events selector block
    txEventsSelectorBlock.style.display = 'block';
    txEventsList.innerHTML = '';
    
    tx.events.forEach(ev => {
      const pill = document.createElement('button');
      pill.className = `tx-event-pill ${activeEventInTx && activeEventInTx.id === ev.id ? 'active' : ''}`;
      pill.textContent = `Event #${ev.id} (${ev.event_type} - ${ev.table_name})`;
      pill.addEventListener('click', () => {
        // Toggle pill active
        txEventsList.querySelectorAll('.tx-event-pill').forEach(p => p.classList.remove('active'));
        pill.classList.add('active');
        activeEventInTx = ev;
        showEventDiagnostics(ev);
      });
      txEventsList.appendChild(pill);
    });

    // Auto-select event
    let targetEv = tx.events[0];
    if (forceSelectEventId) {
      const found = tx.events.find(e => e.id === forceSelectEventId);
      if (found) targetEv = found;
    }
    activeEventInTx = targetEv;
    
    // Highlight the selected pill
    const pills = txEventsList.querySelectorAll('.tx-event-pill');
    pills.forEach((p, idx) => {
      if (tx.events[idx].id === targetEv.id) {
        p.classList.add('active');
      }
    });

    showEventDiagnostics(targetEv);
  } else {
    // Hide events selector block
    txEventsSelectorBlock.style.display = 'none';
    activeEventInTx = tx.events[0] || null;
    if (activeEventInTx) {
      showEventDiagnostics(activeEventInTx);
    }
  }
}

// Select File Row
function selectFileRow(log) {
  selectedFileId = log.id;
  selectedTxId = null;
  activeEventInTx = null;

  // Highlight row in list
  const rows = fileListBody.querySelectorAll('.table-row');
  rows.forEach(r => {
    if (parseInt(r.dataset.id, 10) === log.id) {
      r.classList.add('active');
    } else {
      r.classList.remove('active');
    }
  });

  // Diagnostics view toggle
  diagnosticsEmpty.style.display = 'none';
  diagnosticsContent.style.display = 'flex';
  txEventsSelectorBlock.style.display = 'none';

  tracebackViewer.textContent = log.error_message || 'No error traceback log captured.';
  
  // Render clean file metadata
  const fileMeta = {
    id: log.id,
    filename: log.filename,
    filepath: log.filepath,
    table_name: log.table_name,
    retry_count: log.retry_count,
    created_at: log.created_at,
    updated_at: log.updated_at
  };
  payloadViewer.textContent = JSON.stringify(fileMeta, null, 2);
}

// Render error log traceback and payloads of Outbox Event
function showEventDiagnostics(ev) {
  const errLog = ev.payload?.error_log || {};
  const reason = errLog.reason || 'No error traceback log captured.';
  tracebackViewer.textContent = reason;

  // Render raw payload without error_log to keep it clean
  const cleanPayload = { ...ev.payload };
  delete cleanPayload.error_log;
  payloadViewer.textContent = JSON.stringify(cleanPayload, null, 2);
}

// Clear Diagnostics Panel
function clearDiagnostics() {
  selectedTxId = null;
  selectedFileId = null;
  activeEventInTx = null;
  diagnosticsContent.style.display = 'none';
  diagnosticsEmpty.style.display = 'flex';
  txEventsSelectorBlock.style.display = 'none';
  txEventsList.innerHTML = '';
  tracebackViewer.textContent = '';
  payloadViewer.textContent = '';
}

// Update Pagination Footer controls
function updatePaginationFooter(total, currentPage, maxPage) {
  const limit = currentTab === 'outbox' ? outboxLimit : fileLimit;
  const start = total === 0 ? 0 : (currentPage - 1) * limit + 1;
  const end = Math.min(currentPage * limit, total);

  paginationInfo.textContent = `Showing ${start}-${end} of ${total} items`;
  pageIndicator.textContent = `${currentPage} / ${maxPage}`;

  prevPageBtn.disabled = currentPage <= 1;
  nextPageBtn.disabled = currentPage >= maxPage;
}

// API Call: Retry single Outbox Transaction
async function retryTransaction(txId) {
  try {
    const res = await fetch(`${API_BASE}/admin/outbox/retry-failed?transaction_id=${txId}`, {
      method: 'POST'
    });
    if (!res.ok) throw new Error('Retry API returned error status');
    
    showToast(`🔄 트랜잭션 [${txId}] 이 재처리 목록으로 리셋되었습니다.`, 'success');
    
    // Smooth remove from cache
    outboxData = outboxData.filter(t => t.transaction_id !== txId);
    outboxTotal = Math.max(0, outboxTotal - 1);
    if (selectedTxId === txId) {
      clearDiagnostics();
    }
    renderOutboxTable();
  } catch (err) {
    console.error('Failed to retry transaction', txId, err);
    showToast('❌ 트랜잭션 재시도 요청 실패', 'error');
  }
}

// API Call: Retry single File Ingestion
async function retryFileIngestion(logId) {
  try {
    const res = await fetch(`${API_BASE}/admin/file-ingestion/retry-failed?log_id=${logId}`, {
      method: 'POST'
    });
    if (!res.ok) throw new Error('Retry API returned error status');
    const result = await res.json();
    
    showToast(`🔄 파일 인제션 ID #${logId}가 성공적으로 재실행되었습니다.`, 'success');
    
    // Refresh list to fetch updated status
    fetchData();
  } catch (err) {
    console.error('Failed to retry file ingestion', logId, err);
    showToast('❌ 파일 인제션 재시도 요청 실패', 'error');
  }
}

// API Call: Retry all failed items in the current tab
async function retryAllFailed() {
  try {
    if (currentTab === 'outbox') {
      const res = await fetch(`${API_BASE}/admin/outbox/retry-failed`, {
        method: 'POST'
      });
      if (!res.ok) throw new Error('Retry-all API returned error status');
      const result = await res.json();
      
      showToast(`🔄 ${result.message || '모든 실패 아웃박스 건이 초기화되었습니다.'}`, 'success');
      outboxPage = 1;
      fetchData();
    } else {
      const res = await fetch(`${API_BASE}/admin/file-ingestion/retry-failed`, {
        method: 'POST'
      });
      if (!res.ok) throw new Error('Retry-all API returned error status');
      const result = await res.json();
      
      showToast(`🔄 ${result.message || '모든 실패 파일 인제션 건이 재실행되었습니다.'}`, 'success');
      filePage = 1;
      fetchData();
    }
  } catch (err) {
    console.error('Failed to retry all failed items', err);
    showToast('❌ 일괄 재시도 요청 실패', 'error');
  }
}

// Show feedback toasts
function showToast(message, type = 'success') {
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <span style="font-size: 1.2rem;">${type === 'success' ? '✅' : '❌'}</span>
    <span class="toast-message">${message}</span>
  `;
  
  toastContainer.appendChild(toast);
  
  // Remove toast after animation
  setTimeout(() => {
    toast.style.animation = 'toastIn 0.3s cubic-bezier(0.4, 0, 0.2, 1) reverse forwards';
    setTimeout(() => {
      toast.remove();
    }, 300);
  }, 3000);
}
