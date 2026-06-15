// Ingestion Outbox Admin Dashboard client logic
const isDevServer = window.location.port === '5173';
const API_BASE = isDevServer ? 'http://127.0.0.1:8080' : window.location.origin;

// State Cache
let currentTab = 'outbox'; // 'outbox', 'file', 'workspace', 'chain', 'mapper'
let outboxPage = 1;
let outboxLimit = 10;
let outboxData = [];
let outboxTotal = 0;

let filePage = 1;
let fileLimit = 10;
let fileData = [];
let fileTotal = 0;

let workspaceData = [];
let chainData = [];
let mapperData = [];

let selectedTxId = null;
let selectedFileId = null;
let selectedWorkspaceName = null;
let selectedChainName = null;
let selectedMapperFile = null;
let activeEventInTx = null;

// DOM Elements
const tabOutboxBtn = document.getElementById('tab-outbox-btn');
const tabFileBtn = document.getElementById('tab-file-btn');
const tabWorkspaceBtn = document.getElementById('tab-workspace-btn');
const tabChainBtn = document.getElementById('tab-chain-btn');
const tabMapperBtn = document.getElementById('tab-mapper-btn');

const outboxTableWrapper = document.getElementById('outbox-table-wrapper');
const fileTableWrapper = document.getElementById('file-table-wrapper');
const workspaceTableWrapper = document.getElementById('workspace-table-wrapper');
const chainTableWrapper = document.getElementById('chain-table-wrapper');
const mapperTableWrapper = document.getElementById('mapper-table-wrapper');

const statusFilterSelect = document.getElementById('status-filter');

const outboxListBody = document.getElementById('outbox-list-body');
const fileListBody = document.getElementById('file-list-body');
const workspaceListBody = document.getElementById('workspace-list-body');
const chainListBody = document.getElementById('chain-list-body');
const mapperListBody = document.getElementById('mapper-list-body');

const outboxEmptyState = document.getElementById('outbox-empty');
const fileEmptyState = document.getElementById('file-empty');
const workspaceEmptyState = document.getElementById('workspace-empty');
const chainEmptyState = document.getElementById('chain-empty');
const mapperEmptyState = document.getElementById('mapper-empty');

const totalCountSpan = document.getElementById('total-count');
const retryAllBtn = document.getElementById('retry-all-btn');
const refreshBtn = document.getElementById('refresh-btn');

const diagnosticsContent = document.getElementById('diagnostics-content');
const diagnosticsEmpty = document.getElementById('diagnostics-empty');
const diagnosticsEmptyText = document.getElementById('diagnostics-empty-text');
const diagnosticsTitle = document.getElementById('diagnostics-title');
const txEventsSelectorBlock = document.getElementById('tx-events-selector-block');
const txEventsList = document.getElementById('tx-events-list');
const tracebackTitle = document.getElementById('traceback-title');
const tracebackSeverity = document.getElementById('traceback-severity');
const tracebackViewer = document.getElementById('traceback-viewer');
const payloadTitle = document.getElementById('payload-title');
const payloadViewer = document.getElementById('payload-viewer');
const copyPayloadBtn = document.getElementById('copy-payload-btn');
const toastContainer = document.getElementById('toast-container');

// Pagination DOM Elements
const panelFooter = document.querySelector('.panel-footer');
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
  const tabs = [
    { btn: tabOutboxBtn, tab: 'outbox', wrapper: outboxTableWrapper },
    { btn: tabFileBtn, tab: 'file', wrapper: fileTableWrapper },
    { btn: tabWorkspaceBtn, tab: 'workspace', wrapper: workspaceTableWrapper },
    { btn: tabChainBtn, tab: 'chain', wrapper: chainTableWrapper },
    { btn: tabMapperBtn, tab: 'mapper', wrapper: mapperTableWrapper }
  ];

  tabs.forEach(t => {
    t.btn.addEventListener('click', () => {
      if (currentTab === t.tab) return;
      currentTab = t.tab;
      
      // Update Tab Button styles
      tabs.forEach(o => o.btn.classList.remove('active'));
      t.btn.classList.add('active');
      
      // Update Table Wrapper Visibility
      tabs.forEach(o => o.wrapper.style.display = 'none');
      t.wrapper.style.display = 'block';
      
      // Controls visibility
      statusFilterSelect.style.display = (t.tab === 'file') ? 'block' : 'none';
      retryAllBtn.style.display = (t.tab === 'outbox' || t.tab === 'file') ? 'block' : 'none';
      panelFooter.style.display = (t.tab === 'outbox' || t.tab === 'file') ? 'flex' : 'none';
      
      clearDiagnostics();
      fetchData();
    });
  });

  // Status filter change
  statusFilterSelect.addEventListener('change', () => {
    filePage = 1;
    fetchData();
  });

  // Actions
  refreshBtn.addEventListener('click', () => {
    fetchData();
    let message = '♻️ 실패 목록을 새로고침했습니다.';
    if (currentTab === 'file') {
      const statusVal = statusFilterSelect.value || 'ALL';
      if (statusVal === 'ALL') message = '♻️ 모든 파일 인제션 목록을 새로고침했습니다.';
      else if (statusVal === 'SUCCESS') message = '♻️ 성공 파일 인제션 목록을 새로고침했습니다.';
      else message = '♻️ 실패 파일 인제션 목록을 새로고침했습니다.';
    } else if (currentTab === 'workspace') {
      message = '♻️ 인제션 워크스페이스 목록을 새로고침했습니다.';
    } else if (currentTab === 'chain') {
      message = '♻️ 체인 룰 목록을 새로고침했습니다.';
    } else if (currentTab === 'mapper') {
      message = '♻️ 맵퍼 모듈 목록을 새로고침했습니다.';
    }
    showToast(message, 'success');
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
    } else if (currentTab === 'workspace' && selectedWorkspaceName) {
      payloadToCopy = workspaceData.find(w => w.name === selectedWorkspaceName);
    } else if (currentTab === 'chain' && selectedChainName) {
      payloadToCopy = chainData.find(c => c.name === selectedChainName);
    } else if (currentTab === 'mapper' && selectedMapperFile) {
      payloadToCopy = mapperData.find(m => m.filename === selectedMapperFile);
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

// Fetch lists depending on active tab
async function fetchData() {
  try {
    if (currentTab === 'outbox') {
      const res = await fetch(`${API_BASE}/admin/outbox/failed?page=${outboxPage}&limit=${outboxLimit}`);
      if (!res.ok) throw new Error('API fetch failed');
      const result = await res.json();
      outboxData = result.data || [];
      outboxTotal = result.total || 0;
      renderOutboxTable();
    } else if (currentTab === 'file') {
      const statusVal = statusFilterSelect.value || 'FAILED';
      const res = await fetch(`${API_BASE}/admin/file-ingestion/logs?status=${statusVal}&page=${filePage}&limit=${fileLimit}`);
      if (!res.ok) throw new Error('API fetch failed');
      const result = await res.json();
      fileData = result.data || [];
      fileTotal = result.total || 0;
      renderFileTable();
    } else if (currentTab === 'workspace') {
      const res = await fetch(`${API_BASE}/admin/file-ingestion/workspaces`);
      if (!res.ok) throw new Error('API fetch failed');
      const result = await res.json();
      workspaceData = result.data || [];
      renderWorkspaceTable();
    } else if (currentTab === 'chain') {
      const res = await fetch(`${API_BASE}/admin/chain/rules`);
      if (!res.ok) throw new Error('API fetch failed');
      const result = await res.json();
      chainData = result.data || [];
      renderChainTable();
    } else if (currentTab === 'mapper') {
      const res = await fetch(`${API_BASE}/admin/mappers/list`);
      if (!res.ok) throw new Error('API fetch failed');
      const result = await res.json();
      mapperData = result.data || [];
      renderMapperTable();
    }
  } catch (err) {
    console.error('Failed to fetch items', err);
    let errorMsg = '❌ 목록 로드 실패';
    if (currentTab === 'outbox') errorMsg = '❌ 아웃박스 실패 목록 로드 실패';
    else if (currentTab === 'file') errorMsg = '❌ 파일 인제션 목록 로드 실패';
    else if (currentTab === 'workspace') errorMsg = '❌ 인제션 워크스페이스 목록 로드 실패';
    else if (currentTab === 'chain') errorMsg = '❌ 체인 룰 목록 로드 실패';
    else if (currentTab === 'mapper') errorMsg = '❌ 맵퍼 모듈 목록 로드 실패';
    showToast(errorMsg, 'error');
  }
}

// Render outbox table rows (Grouped by Transaction ID)
function renderOutboxTable() {
  outboxListBody.innerHTML = '';
  totalCountSpan.textContent = outboxTotal;
  totalCountSpan.style.color = 'var(--color-danger)';

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

    row.addEventListener('click', () => {
      selectTxRow(tx);
    });

    const retryBtn = row.querySelector('.btn-retry-tx');
    retryBtn.addEventListener('click', async () => {
      if (confirm(`트랜잭션 [${tx.transaction_id}] 내의 모든 이벤트를 다시 재시도하시겠습니까?`)) {
        await retryTransaction(tx.transaction_id);
      }
    });

    outboxListBody.appendChild(row);
  });

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
  
  const statusFilterVal = statusFilterSelect.value;
  if (statusFilterVal === 'SUCCESS') {
    totalCountSpan.style.color = 'var(--color-success)';
  } else if (statusFilterVal === 'FAILED') {
    totalCountSpan.style.color = 'var(--color-danger)';
  } else {
    totalCountSpan.style.color = 'var(--text-main)';
  }

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

    row.addEventListener('click', () => {
      selectFileRow(log);
    });

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

// Render Workspace table rows
function renderWorkspaceTable() {
  workspaceListBody.innerHTML = '';
  totalCountSpan.textContent = workspaceData.length;
  totalCountSpan.style.color = 'var(--color-primary)';

  if (workspaceData.length === 0) {
    workspaceEmptyState.style.display = 'flex';
    clearDiagnostics();
    return;
  }

  workspaceEmptyState.style.display = 'none';

  workspaceData.forEach(ws => {
    const row = document.createElement('tr');
    row.className = `table-row ${selectedWorkspaceName === ws.name ? 'active' : ''}`;
    row.dataset.name = ws.name;

    const configBadge = ws.has_config 
      ? `<span class="badge badge-success">${ws.config_file}</span>` 
      : `<span class="badge badge-danger">None</span>`;
      
    const scriptCount = ws.custom_scripts.length;
    const scriptsBadge = scriptCount > 0 
      ? `<span class="badge badge-success" style="font-family: var(--font-mono);">${scriptCount} script(s)</span>` 
      : `<span class="badge badge-warning">None (Standard)</span>`;

    const rawFilesBadge = ws.raw_files_count > 0
      ? `<span class="badge badge-warning" style="font-family: var(--font-mono); font-weight: bold;">${ws.raw_files_count} file(s)</span>`
      : `<span class="badge badge-success" style="font-family: var(--font-mono);">0</span>`;

    row.innerHTML = `
      <td style="font-weight: bold; color: var(--color-primary);">${ws.name}</td>
      <td style="font-family: var(--font-mono); font-size: 0.85rem; font-weight: 500;">${ws.table_name}</td>
      <td style="text-align: center;">${configBadge}</td>
      <td style="text-align: center;">${scriptsBadge}</td>
      <td style="text-align: center;">${rawFilesBadge}</td>
    `;

    row.addEventListener('click', () => {
      selectWorkspaceRow(ws);
    });

    workspaceListBody.appendChild(row);
  });

  if (selectedWorkspaceName) {
    const exists = workspaceData.find(w => w.name === selectedWorkspaceName);
    if (exists) {
      selectWorkspaceRow(exists);
    } else {
      clearDiagnostics();
    }
  }
}

// Render Chain Rules table rows
function renderChainTable() {
  chainListBody.innerHTML = '';
  totalCountSpan.textContent = chainData.length;
  totalCountSpan.style.color = 'var(--color-primary)';

  if (chainData.length === 0) {
    chainEmptyState.style.display = 'flex';
    clearDiagnostics();
    return;
  }

  chainEmptyState.style.display = 'none';

  chainData.forEach(rule => {
    const row = document.createElement('tr');
    row.className = `table-row ${selectedChainName === rule.name ? 'active' : ''}`;
    row.dataset.name = rule.name;

    const isActive = rule.active !== false;
    const activeBadge = isActive
      ? `<span class="badge badge-success">ACTIVE</span>`
      : `<span class="badge badge-danger">DISABLED</span>`;

    row.innerHTML = `
      <td style="font-weight: bold; color: var(--color-primary);">${rule.name}</td>
      <td style="font-family: var(--font-mono); font-size: 0.85rem; font-weight: 500;">${rule.source_table}</td>
      <td style="font-family: var(--font-mono); font-size: 0.85rem; font-weight: 500;">${rule.target_table}</td>
      <td style="text-align: center;">${activeBadge}</td>
    `;

    row.addEventListener('click', () => {
      selectChainRow(rule);
    });

    chainListBody.appendChild(row);
  });

  if (selectedChainName) {
    const exists = chainData.find(c => c.name === selectedChainName);
    if (exists) {
      selectChainRow(exists);
    } else {
      clearDiagnostics();
    }
  }
}

// Render Mapper modules table rows
function renderMapperTable() {
  mapperListBody.innerHTML = '';
  totalCountSpan.textContent = mapperData.length;
  totalCountSpan.style.color = 'var(--color-primary)';

  if (mapperData.length === 0) {
    mapperEmptyState.style.display = 'flex';
    clearDiagnostics();
    return;
  }

  mapperEmptyState.style.display = 'none';

  mapperData.forEach(mapper => {
    const row = document.createElement('tr');
    row.className = `table-row ${selectedMapperFile === mapper.filename ? 'active' : ''}`;
    row.dataset.file = mapper.filename;

    const funcCount = mapper.functions.length;

    row.innerHTML = `
      <td style="font-weight: bold; color: #a6e3a1; word-break: break-all;">${mapper.filename}</td>
      <td style="font-family: var(--font-mono); font-size: 0.85rem; color: var(--text-muted);">${mapper.module_name}</td>
      <td style="text-align: center; font-weight: bold; color: var(--color-warning);">${funcCount}</td>
    `;

    row.addEventListener('click', () => {
      selectMapperRow(mapper);
    });

    mapperListBody.appendChild(row);
  });

  if (selectedMapperFile) {
    const exists = mapperData.find(m => m.filename === selectedMapperFile);
    if (exists) {
      selectMapperRow(exists);
    } else {
      clearDiagnostics();
    }
  }
}

// Select Transaction Row
function selectTxRow(tx, forceSelectEventId = null) {
  selectedTxId = tx.transaction_id;
  selectedFileId = null;
  selectedWorkspaceName = null;
  selectedChainName = null;
  selectedMapperFile = null;
  
  outboxListBody.querySelectorAll('.table-row').forEach(r => {
    r.classList.toggle('active', r.dataset.txid === tx.transaction_id);
  });

  diagnosticsEmpty.style.display = 'none';
  diagnosticsContent.style.display = 'flex';
  
  diagnosticsTitle.textContent = '🔍 Error & Event Diagnostics';
  tracebackTitle.textContent = 'Stack Trace / Error Reason';
  tracebackSeverity.textContent = 'CRITICAL';
  tracebackSeverity.className = 'badge-danger';
  tracebackSeverity.style.display = 'inline';
  payloadTitle.textContent = 'Raw Event Payload / Details';

  if (tx.events && tx.events.length > 1) {
    txEventsSelectorBlock.style.display = 'block';
    txEventsList.innerHTML = '';
    
    tx.events.forEach(ev => {
      const pill = document.createElement('button');
      pill.className = `tx-event-pill ${activeEventInTx && activeEventInTx.id === ev.id ? 'active' : ''}`;
      pill.textContent = `Event #${ev.id} (${ev.event_type} - ${ev.table_name})`;
      pill.addEventListener('click', () => {
        txEventsList.querySelectorAll('.tx-event-pill').forEach(p => p.classList.remove('active'));
        pill.classList.add('active');
        activeEventInTx = ev;
        showEventDiagnostics(ev);
      });
      txEventsList.appendChild(pill);
    });

    let targetEv = tx.events[0];
    if (forceSelectEventId) {
      const found = tx.events.find(e => e.id === forceSelectEventId);
      if (found) targetEv = found;
    }
    activeEventInTx = targetEv;
    
    const pills = txEventsList.querySelectorAll('.tx-event-pill');
    pills.forEach((p, idx) => {
      p.classList.toggle('active', tx.events[idx].id === targetEv.id);
    });

    showEventDiagnostics(targetEv);
  } else {
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
  selectedWorkspaceName = null;
  selectedChainName = null;
  selectedMapperFile = null;
  activeEventInTx = null;

  fileListBody.querySelectorAll('.table-row').forEach(r => {
    r.classList.toggle('active', parseInt(r.dataset.id, 10) === log.id);
  });

  diagnosticsEmpty.style.display = 'none';
  diagnosticsContent.style.display = 'flex';
  txEventsSelectorBlock.style.display = 'none';

  diagnosticsTitle.textContent = '🔍 File Ingestion Diagnostics';
  tracebackTitle.textContent = 'Ingestion Error Message';
  tracebackSeverity.textContent = log.status || 'FAILED';
  tracebackSeverity.className = log.status === 'SUCCESS' ? 'badge badge-success' : 'badge badge-danger';
  tracebackSeverity.style.display = 'inline';
  payloadTitle.textContent = 'File Metadata / Log Details';

  tracebackViewer.textContent = log.error_message || 'No error traceback log captured (File ingested successfully).';
  
  const fileMeta = {
    id: log.id,
    filename: log.filename,
    filepath: log.filepath,
    table_name: log.table_name,
    status: log.status,
    retry_count: log.retry_count,
    created_at: log.created_at,
    updated_at: log.updated_at
  };
  payloadViewer.textContent = JSON.stringify(fileMeta, null, 2);
}

// Select Workspace Row
function selectWorkspaceRow(ws) {
  selectedWorkspaceName = ws.name;
  selectedFileId = null;
  selectedTxId = null;
  selectedChainName = null;
  selectedMapperFile = null;
  activeEventInTx = null;

  workspaceListBody.querySelectorAll('.table-row').forEach(r => {
    r.classList.toggle('active', r.dataset.name === ws.name);
  });

  diagnosticsEmpty.style.display = 'none';
  diagnosticsContent.style.display = 'flex';
  txEventsSelectorBlock.style.display = 'none';

  diagnosticsTitle.textContent = '🔍 Ingestion Workspace Details';
  tracebackTitle.textContent = 'Custom Ingestion Scripts (.py)';
  tracebackSeverity.style.display = 'none';
  payloadTitle.textContent = 'config.json Configurations';

  if (ws.custom_scripts && ws.custom_scripts.length > 0) {
    tracebackViewer.textContent = ws.custom_scripts.map(s => `📄 ${s} (Active Custom Parser)`).join('\n');
  } else {
    tracebackViewer.textContent = 'No custom parser scripts found.\nUsing default schema-based ingestion pipeline parser.';
  }

  payloadViewer.textContent = JSON.stringify(ws, null, 2);
}

// Select Chain Row
function selectChainRow(rule) {
  selectedChainName = rule.name;
  selectedFileId = null;
  selectedTxId = null;
  selectedWorkspaceName = null;
  selectedMapperFile = null;
  activeEventInTx = null;

  chainListBody.querySelectorAll('.table-row').forEach(r => {
    r.classList.toggle('active', r.dataset.name === rule.name);
  });

  diagnosticsEmpty.style.display = 'none';
  diagnosticsContent.style.display = 'flex';
  txEventsSelectorBlock.style.display = 'none';

  diagnosticsTitle.textContent = '🔍 Chained Ingestion Rule Details';
  tracebackTitle.textContent = 'Rule Description';
  tracebackSeverity.textContent = rule.active !== false ? 'ACTIVE' : 'DISABLED';
  tracebackSeverity.className = rule.active !== false ? 'badge badge-success' : 'badge badge-danger';
  tracebackSeverity.style.display = 'inline';
  payloadTitle.textContent = 'Raw Chain Ingestion Rule Configuration';

  tracebackViewer.textContent = rule.description || 'No description provided for this chain rule.';
  payloadViewer.textContent = JSON.stringify(rule, null, 2);
}

// Select Mapper Row
function selectMapperRow(mapper) {
  selectedMapperFile = mapper.filename;
  selectedFileId = null;
  selectedTxId = null;
  selectedWorkspaceName = null;
  selectedChainName = null;
  activeEventInTx = null;

  mapperListBody.querySelectorAll('.table-row').forEach(r => {
    r.classList.toggle('active', r.dataset.file === mapper.filename);
  });

  diagnosticsEmpty.style.display = 'none';
  diagnosticsContent.style.display = 'flex';
  txEventsSelectorBlock.style.display = 'none';

  diagnosticsTitle.textContent = '🔍 Custom Mapper Module Details';
  tracebackTitle.textContent = 'Available Mapping Functions';
  tracebackSeverity.style.display = 'none';
  payloadTitle.textContent = 'Mapper Module AST Structure';

  if (mapper.functions && mapper.functions.length > 0) {
    tracebackViewer.textContent = mapper.functions.map(f => 
      `⚡ def ${f.name}(${f.arguments.join(', ')}):\n   """${f.summary || 'No docstring summary.'}"""`
    ).join('\n\n');
  } else {
    tracebackViewer.textContent = 'No functions found in this module.';
  }

  payloadViewer.textContent = JSON.stringify(mapper, null, 2);
}

// Render error log traceback and payloads of Outbox Event
function showEventDiagnostics(ev) {
  const errLog = ev.payload?.error_log || {};
  const reason = errLog.reason || 'No error traceback log captured.';
  tracebackViewer.textContent = reason;

  const cleanPayload = { ...ev.payload };
  delete cleanPayload.error_log;
  payloadViewer.textContent = JSON.stringify(cleanPayload, null, 2);
}

// Clear Diagnostics Panel
function clearDiagnostics() {
  selectedTxId = null;
  selectedFileId = null;
  selectedWorkspaceName = null;
  selectedChainName = null;
  selectedMapperFile = null;
  activeEventInTx = null;
  
  diagnosticsContent.style.display = 'none';
  diagnosticsEmpty.style.display = 'flex';
  diagnosticsEmptyText.textContent = 'Select an item from the left list to view detailed configurations or diagnostics.';
  
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
    
    showToast(`🔄 파일 인제션 ID #${logId}가 성공적으로 재실행되었습니다.`, 'success');
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
  
  setTimeout(() => {
    toast.style.animation = 'toastIn 0.3s cubic-bezier(0.4, 0, 0.2, 1) reverse forwards';
    setTimeout(() => {
      toast.remove();
    }, 300);
  }, 3000);
}
