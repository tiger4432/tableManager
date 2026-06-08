// Ingestion Outbox Admin Dashboard client logic
const isDevServer = window.location.port === '5173';
const API_BASE = isDevServer ? 'http://127.0.0.1:8080' : window.location.origin;

// State Cache
let failedEvents = [];
let selectedEventId = null;

// DOM Elements
const outboxListBody = document.getElementById('outbox-list-body');
const totalCountSpan = document.getElementById('total-count');
const retryAllBtn = document.getElementById('retry-all-btn');
const refreshBtn = document.getElementById('refresh-btn');
const tableEmptyState = document.getElementById('table-empty');

const diagnosticsContent = document.getElementById('diagnostics-content');
const diagnosticsEmpty = document.getElementById('diagnostics-empty');
const tracebackViewer = document.getElementById('traceback-viewer');
const payloadViewer = document.getElementById('payload-viewer');
const copyPayloadBtn = document.getElementById('copy-payload-btn');
const toastContainer = document.getElementById('toast-container');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  fetchFailedOutbox();
  setupEventListeners();
});

function setupEventListeners() {
  refreshBtn.addEventListener('click', () => {
    fetchFailedOutbox();
    showToast('♻️ 실패 아웃박스 목록을 새로고침했습니다.', 'success');
  });

  retryAllBtn.addEventListener('click', async () => {
    if (confirm('실패 상태인 모든 이벤트를 재실행 상태(PENDING)로 리셋하시겠습니까?')) {
      await retryAllFailed();
    }
  });

  copyPayloadBtn.addEventListener('click', () => {
    if (!selectedEventId) return;
    const ev = failedEvents.find(e => e.id === selectedEventId);
    if (ev) {
      navigator.clipboard.writeText(JSON.stringify(ev.payload, null, 2))
        .then(() => showToast('📋 페이로드가 클립보드에 복사되었습니다.', 'success'))
        .catch(() => showToast('❌ 복사에 실패했습니다.', 'error'));
    }
  });
}

// Fetch list of failed outbox rows
async function fetchFailedOutbox() {
  try {
    const res = await fetch(`${API_BASE}/admin/outbox/failed`);
    if (!res.ok) throw new Error('API fetch failed');
    const result = await res.json();
    
    failedEvents = result.data || [];
    renderOutboxTable();
  } catch (err) {
    console.error('Failed to load failed outboxes', err);
    showToast('❌ 실패 아웃박스 목록 로드 실패', 'error');
  }
}

// Render outbox table rows
function renderOutboxTable() {
  outboxListBody.innerHTML = '';
  totalCountSpan.textContent = failedEvents.length;

  if (failedEvents.length === 0) {
    tableEmptyState.style.display = 'flex';
    clearDiagnostics();
    return;
  }

  tableEmptyState.style.display = 'none';

  failedEvents.forEach(ev => {
    const row = document.createElement('tr');
    row.className = `table-row ${selectedEventId === ev.id ? 'active' : ''}`;
    row.dataset.id = ev.id;
    
    // Parse time
    let timeStr = ev.created_at || '';
    if (timeStr) {
      const dt = new Date(timeStr);
      timeStr = dt.toLocaleString();
    }

    const txId = ev.payload?.transaction_id || '-';

    row.innerHTML = `
      <td>${ev.id}</td>
      <td style="font-weight: 500; color: #f38ba8;">${ev.table_name}</td>
      <td><span class="badge ${ev.event_type === 'CREATE' ? 'badge-warning' : 'badge-danger'}">${ev.event_type}</span></td>
      <td style="text-align: center; font-weight: bold; color: var(--color-warning);">${ev.retry_count}</td>
      <td style="font-family: var(--font-mono); font-size: 0.8rem; opacity: 0.85;">${txId}</td>
      <td style="color: var(--text-muted); font-size: 0.85rem;">${timeStr}</td>
      <td style="text-align: center;" onclick="event.stopPropagation()">
        <button class="glass-btn btn-primary btn-retry-row" data-id="${ev.id}" style="padding: 4px 10px; font-size: 0.75rem;">Retry</button>
      </td>
    `;

    // Row selection click listener
    row.addEventListener('click', () => {
      selectEventRow(ev.id);
    });

    // Individual retry click listener
    const retryBtn = row.querySelector('.btn-retry-row');
    retryBtn.addEventListener('click', async () => {
      if (confirm(`Event ID #${ev.id} 레코드를 다시 재시도하시겠습니까?`)) {
        await retrySingleEvent(ev.id);
      }
    });

    outboxListBody.appendChild(row);
  });

  // Restore diagnostics selection if selected row still exists
  if (selectedEventId) {
    const exists = failedEvents.some(e => e.id === selectedEventId);
    if (exists) {
      showDiagnostics(selectedEventId);
    } else {
      clearDiagnostics();
    }
  }
}

// Select Event Row
function selectEventRow(id) {
  selectedEventId = id;
  
  // Highlight row in list
  const rows = outboxListBody.querySelectorAll('.table-row');
  rows.forEach(r => {
    if (parseInt(r.dataset.id, 10) === id) {
      r.classList.add('active');
    } else {
      r.classList.remove('active');
    }
  });

  showDiagnostics(id);
}

// Render error log traceback and payloads
function showDiagnostics(id) {
  const ev = failedEvents.find(e => e.id === id);
  if (!ev) return;

  diagnosticsEmpty.style.display = 'none';
  diagnosticsContent.style.display = 'flex';

  // Extract traceback/reason
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
  selectedEventId = null;
  diagnosticsContent.style.display = 'none';
  diagnosticsEmpty.style.display = 'flex';
  tracebackViewer.textContent = '';
  payloadViewer.textContent = '';
}

// API Call: Retry Single Outbox Event
async function retrySingleEvent(id) {
  try {
    const res = await fetch(`${API_BASE}/admin/outbox/retry-failed?event_id=${id}`, {
      method: 'POST'
    });
    if (!res.ok) throw new Error('Retry API returned error status');
    
    showToast(`🔄 Event ID #${id}가 재처리 목록으로 리셋되었습니다.`, 'success');
    
    // Smooth remove from UI list
    failedEvents = failedEvents.filter(e => e.id !== id);
    if (selectedEventId === id) {
      clearDiagnostics();
    }
    renderOutboxTable();
  } catch (err) {
    console.error('Failed to retry event', id, err);
    showToast('❌ 재시도 초기화 요청 실패', 'error');
  }
}

// API Call: Retry All Failed Outbox Events
async function retryAllFailed() {
  try {
    const res = await fetch(`${API_BASE}/admin/outbox/retry-failed`, {
      method: 'POST'
    });
    if (!res.ok) throw new Error('Retry-all API returned error status');
    const result = await res.json();
    
    showToast(`🔄 ${result.message || '모든 실패 건이 초기화되었습니다.'}`, 'success');
    fetchFailedOutbox();
  } catch (err) {
    console.error('Failed to retry all failed outbox', err);
    showToast('❌ 일괄 재시도 초기화 요청 실패', 'error');
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
