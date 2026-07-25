// Ingestion Outbox Admin Dashboard client logic
import './tokens.css';
import { initTheme, getTheme } from './theme.js';

const isDevServer = window.location.port === '5173';
const API_BASE = isDevServer ? 'http://127.0.0.1:8080' : window.location.origin;

// State Cache
let currentTab = 'outbox'; // 'outbox', 'file', 'workspace', 'chain', 'mapper', 'autoupdate', 'editor'
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
let autoUpdateData = [];

let selectedTxId = null;
let selectedFileId = null;
let selectedWorkspaceName = null;
let selectedChainName = null;
let selectedMapperFile = null;
let selectedAutoUpdateScript = null;
let activeEventInTx = null;

// Code Editor State
let isMonacoLoaded = false;
let activeEditorFilePath = null;
let isEditorDirty = false;          // B2: Monaco 미저장 변경 추적
let suppressDirtyTracking = false;  // 프로그램틱 setValue 중 dirty 오탐 방지
let isInlineEditorActive = false;   // B1: 비-editor 탭에서 인라인 에디터 뷰 열림 여부

// UX State
let fetchSeq = 0;                   // 탭 전환/연타 fetch 레이스 가드 시퀀스
let fileSortKey = null;             // B3: 파일 로그 현재 페이지 내 클라이언트 정렬
let fileSortDir = 'asc';
let tabDefs = [];                   // switchTab()이 참조하는 탭 정의 (setupEventListeners에서 채움)
const AUTO_REFRESH_MS = 30000;      // 절제된 자동 갱신 주기 (Outbox/File 탭 + 헬스 스트립)

// DOM Elements
const tabOutboxBtn = document.getElementById('tab-outbox-btn');
const tabFileBtn = document.getElementById('tab-file-btn');
const tabWorkspaceBtn = document.getElementById('tab-workspace-btn');
const tabChainBtn = document.getElementById('tab-chain-btn');
const tabMapperBtn = document.getElementById('tab-mapper-btn');
const tabAutoUpdateBtn = document.getElementById('tab-autoupdate-btn');
const tabEditorBtn = document.getElementById('tab-editor-btn');

const outboxTableWrapper = document.getElementById('outbox-table-wrapper');
const fileTableWrapper = document.getElementById('file-table-wrapper');
const workspaceTableWrapper = document.getElementById('workspace-table-wrapper');
const chainTableWrapper = document.getElementById('chain-table-wrapper');
const mapperTableWrapper = document.getElementById('mapper-table-wrapper');
const autoUpdateTableWrapper = document.getElementById('autoupdate-table-wrapper');
const editorTreeWrapper = document.getElementById('editor-tree-wrapper');

const statusFilterSelect = document.getElementById('status-filter');

const outboxListBody = document.getElementById('outbox-list-body');
const fileListBody = document.getElementById('file-list-body');
const workspaceListBody = document.getElementById('workspace-list-body');
const chainListBody = document.getElementById('chain-list-body');
const mapperListBody = document.getElementById('mapper-list-body');
const autoUpdateListBody = document.getElementById('autoupdate-list-body');

const outboxEmptyState = document.getElementById('outbox-empty');
const fileEmptyState = document.getElementById('file-empty');
const workspaceEmptyState = document.getElementById('workspace-empty');
const chainEmptyState = document.getElementById('chain-empty');
const mapperEmptyState = document.getElementById('mapper-empty');
const autoUpdateEmptyState = document.getElementById('autoupdate-empty');

const totalCountSpan = document.getElementById('total-count');
const totalCountLabel = document.getElementById('total-count-label');
const lastRefreshedSpan = document.getElementById('last-refreshed');
const retryAllBtn = document.getElementById('retry-all-btn');
const refreshBtn = document.getElementById('refresh-btn');
const reloadConfigsBtn = document.getElementById('reload-configs-btn');
const pageSizeSelect = document.getElementById('page-size-select');

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

// Editor Specific DOM Elements
const editorTreeContainer = document.getElementById('editor-tree-container');
const editorContentWrapper = document.getElementById('editor-content-wrapper');
const editorFilePath = document.getElementById('editor-file-path');
const saveCodeBtn = document.getElementById('save-code-btn');
const editorBackBtn = document.getElementById('editor-back-btn');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  fetchData();
  setupEventListeners();
  initMonacoEditor();
  refreshHealthStrip();

  // 절제된 자동 갱신: 백그라운드 탭·에디터 사용 중엔 건너뛴다 (감사 F2)
  setInterval(() => {
    if (document.hidden) return;
    refreshHealthStrip();
    if (isInlineEditorActive || isEditorDirty || currentTab === 'editor') return;
    if (currentTab === 'outbox' || currentTab === 'file') {
      fetchData({ silent: true });
    }
  }, AUTO_REFRESH_MS);

  // B2: 페이지 이탈 시 미저장 코드 변경 보호
  window.addEventListener('beforeunload', (e) => {
    if (isEditorDirty) {
      e.preventDefault();
      e.returnValue = '';
    }
  });
});

// ── 공통 헬퍼 ──────────────────────────────────────────────

// 타임스탬프 단일 포맷: MM-DD HH:mm:ss (감사 P1 — toLocaleString/원시 문자열 혼재 해소)
function formatTimestamp(value) {
  if (!value) return '-';
  const s = String(value);
  // ISO("2026-07-25T13:30:00") / 원시("2026-07-25 13:30:00") 모두 슬라이스로 처리 (타임존 재해석 없음)
  if (/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/.test(s)) {
    return `${s.slice(5, 10)} ${s.slice(11, 19)}`;
  }
  const dt = new Date(s);
  if (!isNaN(dt.getTime())) {
    const p = n => String(n).padStart(2, '0');
    return `${p(dt.getMonth() + 1)}-${p(dt.getDate())} ${p(dt.getHours())}:${p(dt.getMinutes())}:${p(dt.getSeconds())}`;
  }
  return s;
}

// Transaction ID 축약 (감사 F8): head8… — 풀값은 title/클릭복사로
function shortTxId(txId) {
  const s = String(txId || '');
  if (s.startsWith('single_')) {
    return `single_${s.slice(7, 15)}…`;
  }
  return s.length > 12 ? `${s.slice(0, 8)}…` : s;
}

function markRefreshed() {
  if (!lastRefreshedSpan) return;
  const now = new Date();
  const p = n => String(n).padStart(2, '0');
  lastRefreshedSpan.textContent = `갱신 ${p(now.getHours())}:${p(now.getMinutes())}:${p(now.getSeconds())}`;
}

// 탭 전환 본체 — 탭 버튼 클릭과 헬스 카드 딥링크가 공용
function switchTab(tabName) {
  const t = tabDefs.find(x => x.tab === tabName);
  if (!t) return;

  currentTab = t.tab;

  // Update Tab Button styles
  tabDefs.forEach(o => o.btn.classList.remove('active'));
  t.btn.classList.add('active');

  // Update Table Wrapper Visibility
  tabDefs.forEach(o => o.wrapper.style.display = 'none');
  t.wrapper.style.display = 'block';

  // Controls visibility
  statusFilterSelect.style.display = (t.tab === 'file') ? 'block' : 'none';
  retryAllBtn.style.display = (t.tab === 'outbox' || t.tab === 'file') ? 'block' : 'none';
  panelFooter.style.display = (t.tab === 'outbox' || t.tab === 'file') ? 'flex' : 'none';
  // 감사 F6: editor 탭에서 직전 탭 Total 잔존 방지
  if (totalCountLabel) totalCountLabel.style.display = (t.tab === 'editor') ? 'none' : 'inline';
  if (pageSizeSelect) pageSizeSelect.value = String(t.tab === 'file' ? fileLimit : outboxLimit);

  if (t.tab === 'editor') {
    diagnosticsContent.style.display = 'none';
    diagnosticsEmpty.style.display = 'none';
    editorContentWrapper.style.display = 'flex';
    isInlineEditorActive = false;
    if (editorBackBtn) editorBackBtn.style.display = 'none';
    if (window.monacoEditor) {
      setTimeout(() => {
        window.monacoEditor.layout();
      }, 50);
    }
  } else {
    // 인라인 에디터가 열려 있었어도 탭 전환은 뷰만 닫는다
    // (Monaco 내용은 유지 — 같은 파일을 다시 열면 미저장 변경이 보존됨)
    editorContentWrapper.style.display = 'none';
    isInlineEditorActive = false;
    if (editorBackBtn) editorBackBtn.style.display = 'none';
    clearDiagnostics();
  }

  fetchData();
}

function setupEventListeners() {
  tabDefs = [
    { btn: tabOutboxBtn, tab: 'outbox', wrapper: outboxTableWrapper },
    { btn: tabFileBtn, tab: 'file', wrapper: fileTableWrapper },
    { btn: tabWorkspaceBtn, tab: 'workspace', wrapper: workspaceTableWrapper },
    { btn: tabChainBtn, tab: 'chain', wrapper: chainTableWrapper },
    { btn: tabMapperBtn, tab: 'mapper', wrapper: mapperTableWrapper },
    { btn: tabAutoUpdateBtn, tab: 'autoupdate', wrapper: autoUpdateTableWrapper },
    { btn: tabEditorBtn, tab: 'editor', wrapper: editorTreeWrapper }
  ];

  tabDefs.forEach(t => {
    t.btn.addEventListener('click', () => {
      if (currentTab === t.tab) return;
      switchTab(t.tab);
    });
  });

  // Pipeline Health 카드 딥링크: 해당 탭 + 필터로 이동
  const healthCardFile = document.getElementById('health-card-file');
  const healthCardChain = document.getElementById('health-card-chain');
  const healthCardAuto = document.getElementById('health-card-auto');
  const healthCardEnrichment = document.getElementById('health-card-enrichment');
  if (healthCardFile) {
    healthCardFile.addEventListener('click', () => {
      statusFilterSelect.value = 'FAILED';
      filePage = 1;
      switchTab('file');
    });
  }
  if (healthCardChain) {
    healthCardChain.addEventListener('click', () => {
      outboxPage = 1;
      switchTab('outbox');
    });
  }
  if (healthCardAuto) {
    healthCardAuto.addEventListener('click', () => {
      switchTab('autoupdate');
    });
  }
  if (healthCardEnrichment) {
    healthCardEnrichment.addEventListener('click', () => {
      window.location.href = '/enrichment.html';
    });
  }

  // Status filter change
  statusFilterSelect.addEventListener('change', () => {
    filePage = 1;
    fetchData();
  });

  // 페이지 크기 선택 (B3): 활성 탭(outbox/file)의 limit에 적용
  if (pageSizeSelect) {
    pageSizeSelect.addEventListener('change', () => {
      const n = parseInt(pageSizeSelect.value, 10) || 10;
      if (currentTab === 'file') {
        fileLimit = n;
        filePage = 1;
      } else {
        outboxLimit = n;
        outboxPage = 1;
      }
      fetchData();
    });
  }

  // 파일 로그 헤더 클릭 정렬 (B3): 현재 페이지 내 클라이언트측 정렬
  document.querySelectorAll('#file-table-wrapper th.sortable').forEach(th => {
    th.addEventListener('click', () => {
      const key = th.dataset.key;
      if (fileSortKey === key) {
        fileSortDir = fileSortDir === 'asc' ? 'desc' : 'asc';
      } else {
        fileSortKey = key;
        fileSortDir = 'asc';
      }
      updateFileSortIndicators();
      renderFileTable();
    });
  });

  // Actions — Refresh: fetch 완료 후 실제 결과로만 토스트 (감사 F3)
  refreshBtn.addEventListener('click', async () => {
    refreshHealthStrip();
    const ok = await fetchData();
    if (!ok) return; // 실패 토스트는 fetchData가 담당
    let message = '♻️ 목록을 새로고침했습니다.';
    if (currentTab === 'outbox') {
      message = '♻️ 아웃박스 실패 목록을 새로고침했습니다.';
    } else if (currentTab === 'file') {
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
    } else if (currentTab === 'autoupdate') {
      message = '♻️ Auto-Update 스케줄러 현황을 새로고침했습니다.';
    } else if (currentTab === 'editor') {
      message = '♻️ 스크립트 목록을 새로고침했습니다.';
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
    } else if (currentTab === 'autoupdate' && selectedAutoUpdateScript) {
      // 감사 F7: Auto Updates 탭 분기 누락으로 무피드백 no-op이던 것 수리
      payloadToCopy = autoUpdateData.find(c => c.script_name === selectedAutoUpdateScript);
    }

    if (payloadToCopy) {
      navigator.clipboard.writeText(JSON.stringify(payloadToCopy, null, 2))
        .then(() => showToast('📋 페이로드가 클립보드에 복사되었습니다.', 'success'))
        .catch(() => showToast('❌ 복사에 실패했습니다.', 'error'));
    } else {
      showToast('⚠️ 복사할 항목이 선택되지 않았습니다.', 'warning');
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

  reloadConfigsBtn.addEventListener('click', async () => {
    if (confirm('모든 인제션 파서 스크립트, 체인 룰 및 맵퍼 모듈 캐시를 디스크에서 새로고침하시겠습니까?')) {
      await reloadSystemConfigs();
    }
  });

  saveCodeBtn.addEventListener('click', async () => {
    if (!activeEditorFilePath) return;
    if (!window.monacoEditor) return;
    
    if (confirm(`'${activeEditorFilePath}' 스크립트의 코드 변경 사항을 저장하시겠습니까?\n저장 후 핫-리로드가 자동으로 전파됩니다.`)) {
      await saveScriptCode(activeEditorFilePath, window.monacoEditor.getValue());
    }
  });

  if (editorBackBtn) {
    editorBackBtn.addEventListener('click', () => {
      closeInlineEditor();
    });
  }

  // Initialize Split Panel Resizer Drag Logic
  const resizer = document.getElementById('split-resizer');
  const leftPanel = document.querySelector('.left-panel');
  const rightPanel = document.querySelector('.right-panel');

  if (resizer && leftPanel && rightPanel) {
    let isDragging = false;

    resizer.addEventListener('mousedown', (e) => {
      isDragging = true;
      document.body.classList.add('resizing-active');
      resizer.classList.add('dragging');
      e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
      if (!isDragging) return;

      const mainContainer = document.querySelector('main');
      if (mainContainer) {
        const containerRect = mainContainer.getBoundingClientRect();
        const offsetX = e.clientX - containerRect.left;

        // 최소 350px, 최대 컨테이너 전체너비 - 350px 범위 제한
        const minWidth = 350;
        const maxWidth = containerRect.width - 350;

        let leftWidth = offsetX;
        if (leftWidth < minWidth) leftWidth = minWidth;
        if (leftWidth > maxWidth) leftWidth = maxWidth;

        leftPanel.style.width = `${leftWidth}px`;
        leftPanel.style.flex = 'none'; // flex-grow 간섭 차단

        if (window.monacoEditor) {
          window.monacoEditor.layout();
        }
      }
    });

    document.addEventListener('mouseup', () => {
      if (isDragging) {
        isDragging = false;
        document.body.classList.remove('resizing-active');
        resizer.classList.remove('dragging');

        if (window.monacoEditor) {
          window.monacoEditor.layout();
        }
      }
    });
  }
}

// Fetch lists depending on active tab
// - 레이스 가드: 탭 전환/연타 시 늦게 도착한 이전 요청 응답이 현재 탭 위에 렌더되는 것을 차단
// - options.silent: 자동 갱신 경로에서 실패 토스트 반복 방지
// - 반환값: 성공 여부 (Refresh 버튼이 실결과 토스트에 사용)
async function fetchData(options = {}) {
  const { silent = false } = options;
  const seq = ++fetchSeq;
  const tab = currentTab;
  const isStale = () => (seq !== fetchSeq || currentTab !== tab);
  try {
    if (tab === 'outbox') {
      const res = await fetch(`${API_BASE}/admin/outbox/failed?page=${outboxPage}&limit=${outboxLimit}`);
      if (!res.ok) throw new Error('API fetch failed');
      const result = await res.json();
      if (isStale()) return false;
      outboxData = result.data || [];
      outboxTotal = result.total || 0;
      renderOutboxTable();
    } else if (tab === 'file') {
      const statusVal = statusFilterSelect.value || 'FAILED';
      const res = await fetch(`${API_BASE}/admin/file-ingestion/logs?status=${statusVal}&page=${filePage}&limit=${fileLimit}`);
      if (!res.ok) throw new Error('API fetch failed');
      const result = await res.json();
      if (isStale()) return false;
      fileData = result.data || [];
      fileTotal = result.total || 0;
      renderFileTable();
    } else if (tab === 'workspace') {
      const res = await fetch(`${API_BASE}/admin/file-ingestion/workspaces`);
      if (!res.ok) throw new Error('API fetch failed');
      const result = await res.json();
      if (isStale()) return false;
      workspaceData = result.data || [];
      renderWorkspaceTable();
    } else if (tab === 'chain') {
      const res = await fetch(`${API_BASE}/admin/chain/rules`);
      if (!res.ok) throw new Error('API fetch failed');
      const result = await res.json();
      if (isStale()) return false;
      chainData = result.data || [];
      renderChainTable();
    } else if (tab === 'mapper') {
      const res = await fetch(`${API_BASE}/admin/mappers/list`);
      if (!res.ok) throw new Error('API fetch failed');
      const result = await res.json();
      if (isStale()) return false;
      mapperData = result.data || [];
      renderMapperTable();
    } else if (tab === 'autoupdate') {
      const res = await fetch(`${API_BASE}/admin/auto-update/status`);
      if (!res.ok) throw new Error('API fetch failed');
      const result = await res.json();
      if (isStale()) return false;
      autoUpdateData = result.data || [];
      renderAutoUpdateTable();
    } else if (tab === 'editor') {
      const res = await fetch(`${API_BASE}/admin/scripts/list`);
      if (!res.ok) throw new Error('API fetch failed');
      const result = await res.json();
      if (isStale()) return false;
      renderEditorTree(result.data);
    }
    markRefreshed();
    return true;
  } catch (err) {
    if (isStale()) return false; // 무효화된 요청의 실패는 무음 처리
    console.error('Failed to fetch items', err);
    if (!silent) {
      let errorMsg = '❌ 목록 로드 실패';
      if (tab === 'outbox') errorMsg = '❌ 아웃박스 실패 목록 로드 실패';
      else if (tab === 'file') errorMsg = '❌ 파일 인제션 목록 로드 실패';
      else if (tab === 'workspace') errorMsg = '❌ 인제션 워크스페이스 목록 로드 실패';
      else if (tab === 'chain') errorMsg = '❌ 체인 룰 목록 로드 실패';
      else if (tab === 'mapper') errorMsg = '❌ 맵퍼 모듈 목록 로드 실패';
      else if (tab === 'autoupdate') errorMsg = '❌ Auto-Update 스케줄러 현황 로드 실패';
      else if (tab === 'editor') errorMsg = '❌ 스크립트 목록 로드 실패';
      showToast(errorMsg, 'error');
    }
    return false;
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

    const timeStr = formatTimestamp(tx.failed_at);
    const tablesJoined = tx.table_names.join(', ') || '-';
    const eventTypesJoined = tx.event_types.map(t =>
      `<span class="badge ${t === 'CREATE' ? 'badge-warning' : 'badge-danger'}" style="margin-right: 4px;">${t}</span>`
    ).join('');
    // 감사 F8: 풀 UUID → head8… 축약 + title 풀값 + 클릭 복사 (행 높이 정상화)
    const retryStyle = tx.retry_count > 0
      ? 'color: var(--warning); font-weight: 600;'
      : 'color: var(--text-dim);';

    row.innerHTML = `
      <td style="font-family: var(--font-mono); font-size: 0.8rem; font-weight: 600; color: var(--color-primary);">
        <span class="tx-id-chip" title="${tx.transaction_id}&#10;(클릭하여 전체 ID 복사)">${shortTxId(tx.transaction_id)}</span>
      </td>
      <td style="font-weight: 500;">${tablesJoined}</td>
      <td>${eventTypesJoined}</td>
      <td style="text-align: center; ${retryStyle}">${tx.retry_count}</td>
      <td style="color: var(--text-muted); font-size: 0.85rem; font-family: var(--font-mono);" title="${tx.failed_at || ''}">${timeStr}</td>
      <td style="text-align: center;" onclick="event.stopPropagation()">
        <button class="glass-btn btn-primary btn-retry-tx" data-txid="${tx.transaction_id}" style="padding: 4px 10px; font-size: 0.75rem;">Retry</button>
      </td>
    `;

    row.addEventListener('click', () => {
      selectTxRow(tx);
    });

    const idChip = row.querySelector('.tx-id-chip');
    idChip.addEventListener('click', (e) => {
      e.stopPropagation();
      navigator.clipboard.writeText(tx.transaction_id)
        .then(() => showToast(`📋 Transaction ID [${shortTxId(tx.transaction_id)}] 전체값이 복사되었습니다.`, 'info'))
        .catch(() => showToast('❌ 복사에 실패했습니다.', 'error'));
    });

    const retryBtn = row.querySelector('.btn-retry-tx');
    retryBtn.addEventListener('click', async () => {
      if (confirm(`트랜잭션 [${shortTxId(tx.transaction_id)}] 내의 모든 이벤트를 다시 재시도하시겠습니까?`)) {
        await retryTransaction(tx.transaction_id);
      }
    });

    outboxListBody.appendChild(row);
  });

  if (selectedTxId && !isInlineEditorActive) {
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

  // B3: 현재 페이지 내 클라이언트측 정렬 (서버 정렬 파라미터는 중안 이관)
  let viewData = fileData;
  if (fileSortKey) {
    const dir = fileSortDir === 'desc' ? -1 : 1;
    viewData = [...fileData].sort((a, b) => {
      const va = a[fileSortKey];
      const vb = b[fileSortKey];
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * dir;
      return String(va).localeCompare(String(vb)) * dir;
    });
  }

  viewData.forEach(log => {
    const row = document.createElement('tr');
    row.className = `table-row ${selectedFileId === log.id ? 'active' : ''}`;
    row.dataset.id = log.id;

    const timeStr = formatTimestamp(log.created_at);
    const statusBadge = `<span class="badge ${log.status === 'SUCCESS' ? 'badge-success' : 'badge-danger'}">${log.status || 'FAILED'}</span>`;
    const retryBtnHtml = log.status === 'SUCCESS'
      ? `<button class="glass-btn btn-primary" style="padding: 4px 10px; font-size: 0.75rem; opacity: 0.5; cursor: not-allowed;" disabled>Retry</button>`
      : `<button class="glass-btn btn-primary btn-retry-file" data-id="${log.id}" style="padding: 4px 10px; font-size: 0.75rem;">Retry</button>`;
    // 감사 P2: 파일명은 상태와 무관한 중립색(모노) — 상태색은 배지에만
    const retryStyle = log.retry_count > 0
      ? 'color: var(--warning); font-weight: 600;'
      : 'color: var(--text-dim);';

    row.innerHTML = `
      <td>${log.id}</td>
      <td style="font-weight: 500; color: var(--text); font-family: var(--font-mono); font-size: 0.85rem; word-break: break-all;">${log.filename}</td>
      <td style="font-weight: bold; color: var(--color-primary);">${log.table_name}</td>
      <td style="text-align: center;">${statusBadge}</td>
      <td style="text-align: center; ${retryStyle}">${log.retry_count}</td>
      <td style="color: var(--text-muted); font-size: 0.85rem; font-family: var(--font-mono);" title="${log.created_at || ''}">${timeStr}</td>
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

  if (selectedFileId && !isInlineEditorActive) {
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

// B3: 파일 로그 정렬 헤더 표시자(▲/▼) 갱신
function updateFileSortIndicators() {
  document.querySelectorAll('#file-table-wrapper th.sortable').forEach(th => {
    const ind = th.querySelector('.sort-ind');
    if (!ind) return;
    ind.textContent = (th.dataset.key === fileSortKey)
      ? (fileSortDir === 'asc' ? ' ▲' : ' ▼')
      : '';
  });
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

  if (selectedWorkspaceName && !isInlineEditorActive) {
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
      <td style="font-family: var(--font-mono); font-size: 0.85rem; font-weight: 500;">${rule.trigger_table}</td>
      <td style="font-family: var(--font-mono); font-size: 0.85rem; font-weight: 500;">${rule.target_table}</td>
      <td style="text-align: center;">${activeBadge}</td>
    `;

    row.addEventListener('click', () => {
      selectChainRow(rule);
    });

    chainListBody.appendChild(row);
  });

  if (selectedChainName && !isInlineEditorActive) {
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
      <td style="font-weight: 500; color: var(--text); font-family: var(--font-mono); font-size: 0.85rem; word-break: break-all;">${mapper.filename}</td>
      <td style="font-family: var(--font-mono); font-size: 0.85rem; color: var(--text-muted);">${mapper.module_name}</td>
      <td style="text-align: center; font-weight: bold; color: var(--color-warning);">${funcCount}</td>
    `;

    row.addEventListener('click', () => {
      selectMapperRow(mapper);
    });

    mapperListBody.appendChild(row);
  });
}

// Render Auto Update table rows
function renderAutoUpdateTable() {
  autoUpdateListBody.innerHTML = '';
  totalCountSpan.textContent = autoUpdateData.length;
  totalCountSpan.style.color = 'var(--color-primary)';

  if (autoUpdateData.length === 0) {
    autoUpdateEmptyState.style.display = 'flex';
    clearDiagnostics();
    return;
  }

  autoUpdateEmptyState.style.display = 'none';

  autoUpdateData.forEach(col => {
    const row = document.createElement('tr');
    row.className = `table-row ${selectedAutoUpdateScript === col.script_name ? 'active' : ''}`;
    row.dataset.script = col.script_name;
    row.dataset.table = col.table_name;

    const statusBadge = `<span class="badge ${
      col.last_status === 'SUCCESS' ? 'badge-success' : 
      col.last_status === 'FAIL' ? 'badge-danger' : 
      col.last_status === 'RUNNING' ? 'badge-warning' : 'badge-warning'
    }">${col.last_status || 'PENDING'}</span>`;

    row.innerHTML = `
      <td style="font-weight: bold; color: var(--color-primary);">${col.table_name}</td>
      <td style="font-weight: 500; color: var(--text); font-family: var(--font-mono); font-size: 0.85rem; word-break: break-all;">${col.script_name}</td>
      <td style="font-family: var(--font-mono); font-size: 0.85rem; text-align: center;">${col.cron_expression}</td>
      <td style="color: var(--text-muted); font-size: 0.85rem; font-family: var(--font-mono);" title="${col.next_run || ''}">${formatTimestamp(col.next_run)}</td>
      <td style="color: var(--text-muted); font-size: 0.85rem; font-family: var(--font-mono);" title="${col.last_run || ''}">${formatTimestamp(col.last_run)}</td>
      <td style="text-align: center;">${statusBadge}</td>
      <td style="text-align: center;" onclick="event.stopPropagation()">
        <button class="glass-btn btn-primary btn-run-now" data-table="${col.table_name}" data-script="${col.script_name}" style="padding: 4px 10px; font-size: 0.75rem;">Run Now</button>
      </td>
    `;

    row.addEventListener('click', () => {
      selectAutoUpdateRow(col);
    });

    const runBtn = row.querySelector('.btn-run-now');
    runBtn.addEventListener('click', async () => {
      if (confirm(`수집기 스크립트 '${col.script_name}'을 즉시 실행하시겠습니까?`)) {
        await runAutoUpdateNow(col.table_name, col.script_name);
      }
    });

    autoUpdateListBody.appendChild(row);
  });

  if (selectedAutoUpdateScript && !isInlineEditorActive) {
    const exists = autoUpdateData.find(c => c.script_name === selectedAutoUpdateScript);
    if (exists) {
      selectAutoUpdateRow(exists);
    } else {
      clearDiagnostics();
    }
  }
}

// B1: 좌측 행 선택 시 인라인 에디터 뷰가 진단 패널과 스택되어 클립되던 결함 수리.
// 에디터 뷰가 열려 있으면 닫고 진행 — dirty면 사용자 확인(취소 시 행 선택 중단).
// Monaco 내용 자체는 유지되므로 같은 파일을 다시 열면 미저장 변경이 보존된다.
function ensureEditorViewClosed() {
  if (currentTab === 'editor') return true;
  if (editorContentWrapper.style.display !== 'flex') return true;
  if (isEditorDirty) {
    const ok = confirm(
      '에디터에 저장하지 않은 코드 변경이 있습니다.\n' +
      '에디터를 닫고 선택한 항목의 상세를 표시할까요?\n' +
      '(같은 파일을 다시 열면 변경 내용은 유지됩니다)'
    );
    if (!ok) return false;
  }
  editorContentWrapper.style.display = 'none';
  isInlineEditorActive = false;
  if (editorBackBtn) editorBackBtn.style.display = 'none';
  return true;
}

// Select Auto Update Row
function selectAutoUpdateRow(col) {
  if (!ensureEditorViewClosed()) return;
  selectedAutoUpdateScript = col.script_name;
  selectedFileId = null;
  selectedTxId = null;
  selectedWorkspaceName = null;
  selectedChainName = null;
  selectedMapperFile = null;
  activeEventInTx = null;

  autoUpdateListBody.querySelectorAll('.table-row').forEach(r => {
    r.classList.toggle('active', r.dataset.script === col.script_name);
  });

  diagnosticsEmpty.style.display = 'none';
  diagnosticsContent.style.display = 'flex';
  txEventsSelectorBlock.style.display = 'none';

  diagnosticsTitle.textContent = '🔍 Auto-Update Collector Diagnostics';
  tracebackTitle.textContent = 'Last Collector Execution Error';
  tracebackSeverity.textContent = col.last_status || 'PENDING';
  tracebackSeverity.className = 
    col.last_status === 'SUCCESS' ? 'badge badge-success' : 
    col.last_status === 'FAIL' ? 'badge badge-danger' : 'badge badge-warning';
  tracebackSeverity.style.display = 'inline';
  payloadTitle.innerHTML = `Collector Config & Execution Metadata 
    <button id="inline-edit-collector-btn" class="glass-btn btn-primary" style="padding: 2px 8px; font-size: 0.75rem; margin-left: 10px;">🛠️ Edit Collector Script</button>`;

  tracebackViewer.textContent = col.last_error || 'No error traceback log captured (Last execution was successful).';
  payloadViewer.textContent = JSON.stringify(col, null, 2);

  const inlineEditBtn = document.getElementById('inline-edit-collector-btn');
  if (inlineEditBtn) {
    const scriptPath = `ingestion_workspace/${col.table_name}/auto_update/${col.script_name}`;
    inlineEditBtn.addEventListener('click', () => {
      openInlineEditor(scriptPath);
    });
  }
}

// API Call: Trigger Auto Update Run Now
async function runAutoUpdateNow(tableName, scriptName) {
  try {
    const res = await fetch(`${API_BASE}/admin/auto-update/run-now`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        table_name: tableName,
        script_name: scriptName
      })
    });
    if (!res.ok) throw new Error('Run Now API returned error status');
    showToast(`🔄 [${tableName}] 강제 수집 지시가 정상적으로 발행되었습니다.`, 'success');
    
    setTimeout(() => {
      fetchData();
    }, 1500);
  } catch (err) {
    console.error('Failed to trigger run-now', tableName, scriptName, err);
    showToast('❌ 강제 수집 구동 요청 실패', 'error');
  }
}

// Select Transaction Row
function selectTxRow(tx, forceSelectEventId = null) {
  if (!ensureEditorViewClosed()) return;
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
  if (!ensureEditorViewClosed()) return;
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
  if (!ensureEditorViewClosed()) return;
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
    tracebackViewer.innerHTML = '';
    ws.custom_scripts.forEach(s => {
      const div = document.createElement('div');
      div.style.marginBottom = '10px';
      div.style.display = 'flex';
      div.style.alignItems = 'center';
      div.style.justifyContent = 'space-between';
      div.style.borderBottom = '1px solid var(--border-color)';
      div.style.paddingBottom = '8px';
      div.innerHTML = `
        <span>📄 <strong style="color: var(--text); font-family: var(--font-mono);">${s}</strong> (Active Custom Parser)</span>
        <button class="glass-btn btn-primary btn-inline-edit-script" data-script="${s}" style="padding: 2px 8px; font-size: 0.75rem;">🛠️ Edit Parser</button>
      `;
      
      const btn = div.querySelector('.btn-inline-edit-script');
      btn.addEventListener('click', () => {
        const scriptPath = `ingestion_workspace/${ws.name}/scripts/${s}`;
        openInlineEditor(scriptPath);
      });
      tracebackViewer.appendChild(div);
    });
  } else {
    tracebackViewer.innerHTML = '<div style="color: var(--text-muted); line-height: 1.6;">No custom parser scripts found.<br>Using default schema-based ingestion pipeline parser.</div>';
  }

  payloadViewer.textContent = JSON.stringify(ws, null, 2);
}

// Select Chain Row
function selectChainRow(rule) {
  if (!ensureEditorViewClosed()) return;
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
  payloadTitle.innerHTML = `Raw Chain Ingestion Rule Configuration 
    <button id="inline-edit-mapper-btn" class="glass-btn btn-primary" style="padding: 2px 8px; font-size: 0.75rem; margin-left: 10px;">🛠️ Edit Mapper Code</button>`;

  tracebackViewer.textContent = rule.description || 'No description provided for this chain rule.';
  payloadViewer.textContent = JSON.stringify(rule, null, 2);

  const inlineEditBtn = document.getElementById('inline-edit-mapper-btn');
  if (inlineEditBtn) {
    let modulePath = rule.mapper_module || '';
    if (modulePath.startsWith('mappers.')) {
      modulePath = modulePath.replace('mappers.', 'mappers/') + '.py';
    } else {
      modulePath = `${modulePath.replace(/\./g, '/')}.py`;
    }
    inlineEditBtn.addEventListener('click', () => {
      openInlineEditor(modulePath);
    });
  }
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
  // B1: 인라인 에디터가 열려 있는 동안엔 빈 상태를 겹쳐 표시하지 않는다
  diagnosticsEmpty.style.display = isInlineEditorActive ? 'none' : 'flex';
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
// 감사 F1: 낙관적 제거 폐기 — 재조회로 실제 결과를 확정한다.
// (재시도는 상태를 PENDING으로 리셋 → 워커가 비동기 처리. 잠시 후 재조회해
//  FAILED 목록에 다시 나타나면 재실패로 판정해 행 잔존 + 경고를 표시)
async function retryTransaction(txId) {
  try {
    const res = await fetch(`${API_BASE}/admin/outbox/retry-failed?transaction_id=${txId}`, {
      method: 'POST'
    });
    if (!res.ok) throw new Error('Retry API returned error status');

    showToast(`🔄 트랜잭션 [${shortTxId(txId)}] 재시도 발행 — 잠시 후 결과를 확인합니다.`, 'info');

    setTimeout(async () => {
      await fetchData({ silent: true });
      refreshHealthStrip();
      if (currentTab !== 'outbox') return;
      const still = outboxData.find(t => t.transaction_id === txId);
      if (still) {
        showToast(`⚠️ 트랜잭션 [${shortTxId(txId)}] 이 재시도 후에도 실패 상태로 남아 있습니다. 오류를 확인하세요.`, 'warning');
      } else {
        showToast(`✅ 트랜잭션 [${shortTxId(txId)}] 이 실패 목록에서 해제되었습니다.`, 'success');
      }
    }, 3000);
  } catch (err) {
    console.error('Failed to retry transaction', txId, err);
    showToast('❌ 트랜잭션 재시도 요청 실패', 'error');
  }
}

// API Call: Retry single File Ingestion
// 감사 F1 준용: 재시도는 동기 처리이므로 즉시 재조회해 실제 상태로 피드백한다.
async function retryFileIngestion(logId) {
  try {
    const res = await fetch(`${API_BASE}/admin/file-ingestion/retry-failed?log_id=${logId}`, {
      method: 'POST'
    });
    if (!res.ok) throw new Error('Retry API returned error status');
    const result = await res.json().catch(() => ({}));

    await fetchData({ silent: true });
    refreshHealthStrip();
    if (currentTab === 'file') {
      const log = fileData.find(f => f.id === logId);
      if (log && log.status === 'FAILED') {
        showToast(`⚠️ 파일 인제션 ID #${logId} 재시도가 다시 실패했습니다. 오류 메시지를 확인하세요.`, 'warning');
        return;
      }
    }
    showToast(`✅ 파일 인제션 ID #${logId} 재시도 완료 — ${result.message || '실패 목록에서 해제되었습니다.'}`, 'success');
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
  // tokens.css 공통 토스트 계약(.toast.toast-{type})에 정렬 (구 .toast.{type}도 호환 유지됨)
  toast.className = `toast toast-${type}`;
  const icons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };
  toast.innerHTML = `
    <span style="font-size: 1.2rem;">${icons[type] || icons.success}</span>
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

// API Call: Reload system configurations and python modules cache
async function reloadSystemConfigs() {
  try {
    const res = await fetch(`${API_BASE}/admin/reload-configs`, {
      method: 'POST'
    });
    if (!res.ok) throw new Error('Reload configs API returned error status');
    showToast('🚀 시스템 설정 및 파이썬 코드가 성공적으로 핫-리로드되었습니다.', 'success');
    fetchData();
  } catch (err) {
    console.error('Failed to reload configs', err);
    showToast('❌ 시스템 핫-리로드 요청 실패', 'error');
  }
}

// --- Code Editor Core Logic ---

// Monaco Editor initialization
function initMonacoEditor() {
  if (typeof require === 'undefined') {
    console.warn('Monaco loader (require) is not defined yet. Retrying...');
    setTimeout(initMonacoEditor, 200);
    return;
  }
  require.config({ paths: { vs: 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.39.0/min/vs' } });
  require(['vs/editor/editor.main'], function () {
    window.monacoEditor = monaco.editor.create(document.getElementById('monaco-editor-container'), {
      value: '# Select a script file from the left explorer tree to start editing\n',
      language: 'python',
      // 페이지 테마(light/dark)에 따라 Monaco 기본 테마 매핑
      theme: getTheme() === 'dark' ? 'vs-dark' : 'vs',
      automaticLayout: true,
      fontSize: 15,
      minimap: { enabled: true }
    });
    isMonacoLoaded = true;
    // B2: 미저장 변경(dirty) 추적 — 프로그램틱 setValue는 suppressDirtyTracking으로 제외
    window.monacoEditor.onDidChangeModelContent(() => {
      if (suppressDirtyTracking) return;
      if (!isEditorDirty) {
        isEditorDirty = true;
        updateDirtyIndicator();
      }
    });
    console.log('Monaco Editor loaded successfully');
  });
}

// B2: dirty 상태 헬퍼 — 저장 버튼에 미저장 도트 표시
function updateDirtyIndicator() {
  if (!saveCodeBtn) return;
  saveCodeBtn.innerHTML = isEditorDirty
    ? '💾 Save Code <span style="color: var(--warning); line-height: 0;">●</span>'
    : '💾 Save Code';
}

function markEditorClean() {
  isEditorDirty = false;
  updateDirtyIndicator();
}

// 테마 토글 시 Monaco 에디터 테마 동기화 (theme.js 'themechange' 구독)
document.addEventListener('themechange', (e) => {
  if (window.monaco && isMonacoLoaded) {
    window.monaco.editor.setTheme(e.detail.theme === 'dark' ? 'vs-dark' : 'vs');
  }
});

// Render the editor left-side file tree
function renderEditorTree(data) {
  editorTreeContainer.innerHTML = '';
  
  if (!data) {
    editorTreeContainer.innerHTML = '<div class="empty-text">No scripts found.</div>';
    return;
  }

  // 1. Mappers Category
  const mappersFolder = createTreeFolder('Mappers', '📁');
  const mappersSub = mappersFolder.querySelector('.tree-file-list');
  if (data.mappers && data.mappers.length > 0) {
    data.mappers.forEach(file => {
      mappersSub.appendChild(createTreeFileItem(file));
    });
  } else {
    mappersSub.innerHTML = '<li style="padding: 4px 8px; font-size: 0.8rem; color: var(--text-muted);">No mappers</li>';
  }
  editorTreeContainer.appendChild(mappersFolder);

  // 2. Ingestions Category (Grouped by Table Name)
  const ingestionsFolder = createTreeFolder('Ingestion Parsers', '📥');
  const ingestionsSub = ingestionsFolder.querySelector('.tree-file-list');
  if (data.ingestions && data.ingestions.length > 0) {
    // Group by table
    const tableGroups = {};
    data.ingestions.forEach(file => {
      if (!tableGroups[file.table_name]) tableGroups[file.table_name] = [];
      tableGroups[file.table_name].push(file);
    });

    Object.keys(tableGroups).forEach(table => {
      const tableSubFolder = createTreeSubFolder(table);
      const listContainer = tableSubFolder.querySelector('.tree-file-list');
      tableGroups[table].forEach(file => {
        listContainer.appendChild(createTreeFileItem(file));
      });
      ingestionsSub.appendChild(tableSubFolder);
    });
  } else {
    ingestionsSub.innerHTML = '<li style="padding: 4px 8px; font-size: 0.8rem; color: var(--text-muted);">No parsers</li>';
  }
  editorTreeContainer.appendChild(ingestionsFolder);

  // 3. Auto Updates Category (Grouped by Table Name)
  const autoUpdatesFolder = createTreeFolder('Auto Update Collectors', '⏰');
  const autoUpdatesSub = autoUpdatesFolder.querySelector('.tree-file-list');
  if (data.auto_updates && data.auto_updates.length > 0) {
    const tableGroups = {};
    data.auto_updates.forEach(file => {
      if (!tableGroups[file.table_name]) tableGroups[file.table_name] = [];
      tableGroups[file.table_name].push(file);
    });

    Object.keys(tableGroups).forEach(table => {
      const tableSubFolder = createTreeSubFolder(table);
      const listContainer = tableSubFolder.querySelector('.tree-file-list');
      tableGroups[table].forEach(file => {
        listContainer.appendChild(createTreeFileItem(file));
      });
      autoUpdatesSub.appendChild(tableSubFolder);
    });
  } else {
    autoUpdatesSub.innerHTML = '<li style="padding: 4px 8px; font-size: 0.8rem; color: var(--text-muted);">No collectors</li>';
  }
  editorTreeContainer.appendChild(autoUpdatesFolder);
}

function createTreeFolder(title, emoji) {
  const folder = document.createElement('div');
  folder.className = 'tree-folder';
  folder.innerHTML = `
    <div class="tree-folder-title">
      <span>${emoji}</span>
      <span>${title}</span>
    </div>
    <ul class="tree-file-list"></ul>
  `;
  return folder;
}

function createTreeSubFolder(title) {
  const sub = document.createElement('div');
  sub.className = 'tree-subfolder';
  sub.innerHTML = `
    <div class="tree-subfolder-title">
      <span>📁</span>
      <span style="font-weight: 500;">${title}</span>
    </div>
    <ul class="tree-file-list"></ul>
  `;
  return sub;
}

function createTreeFileItem(file) {
  const item = document.createElement('li');
  item.className = `tree-file-item ${activeEditorFilePath === file.path ? 'active' : ''}`;
  item.dataset.path = file.path;
  item.innerHTML = `
    <span>📄</span>
    <span style="word-break: break-all;">${file.filename}</span>
  `;
  
  item.addEventListener('click', (e) => {
    e.stopPropagation();
    selectEditorFile(file.path);
  });
  
  return item;
}

// Select a file and load its contents into Monaco Editor
async function selectEditorFile(path) {
  // B2: 편집 중인 동일 파일 재선택 — 서버 리로드로 미저장 변경을 덮어쓰지 않는다
  if (activeEditorFilePath === path && isEditorDirty) {
    document.querySelectorAll('.tree-file-item').forEach(item => {
      item.classList.toggle('active', item.dataset.path === path);
    });
    editorFilePath.textContent = `📝 ${path}`;
    saveCodeBtn.style.display = 'inline-flex';
    updateDirtyIndicator();
    return;
  }

  // B2: 다른 파일로 이동 시 미저장 변경 보호 (무조건 setValue로 유실되던 결함 수리)
  if (isEditorDirty && activeEditorFilePath && activeEditorFilePath !== path) {
    const ok = confirm(
      `'${activeEditorFilePath}' 에 저장하지 않은 변경이 있습니다.\n버리고 다른 파일을 여시겠습니까?`
    );
    if (!ok) {
      // 트리 하이라이트를 기존 파일로 복원하고 이동 취소
      document.querySelectorAll('.tree-file-item').forEach(item => {
        item.classList.toggle('active', item.dataset.path === activeEditorFilePath);
      });
      return;
    }
  }

  activeEditorFilePath = path;

  // Highlight active item in tree
  document.querySelectorAll('.tree-file-item').forEach(item => {
    item.classList.toggle('active', item.dataset.path === path);
  });

  try {
    editorFilePath.textContent = '🔄 Loading file...';
    saveCodeBtn.style.display = 'none';

    const res = await fetch(`${API_BASE}/admin/scripts/code?path=${encodeURIComponent(path)}`);
    if (!res.ok) throw new Error('Failed to load file contents');
    const result = await res.json();

    if (window.monacoEditor) {
      suppressDirtyTracking = true;
      window.monacoEditor.setValue(result.code || '');
      suppressDirtyTracking = false;
      markEditorClean();
      const model = window.monacoEditor.getModel();
      if (model) {
        monaco.editor.setModelLanguage(model, 'python');
      }
    }

    editorFilePath.textContent = `📝 ${path}`;
    saveCodeBtn.style.display = 'inline-flex';
  } catch (err) {
    console.error('Failed to load code for file', path, err);
    editorFilePath.textContent = '❌ Failed to load file';
    showToast('❌ 파일 코드를 불러오지 못했습니다.', 'error');
  }
}

// Save modified code to server
async function saveScriptCode(path, code) {
  try {
    const res = await fetch(`${API_BASE}/admin/scripts/code`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        path: path,
        code: code
      })
    });
    if (!res.ok) throw new Error('Save API returned error status');

    markEditorClean(); // B2: 저장 성공 → dirty 해제
    showToast('💾 코드가 정상 저장 및 핫 리로드되었습니다.', 'success');
  } catch (err) {
    console.error('Failed to save code for file', path, err);
    showToast('❌ 코드 저장 중 오류 발생', 'error');
  }
}

// Inline Code Editor Navigation Helpers
function openInlineEditor(path) {
  if (!isMonacoLoaded) {
    showToast('⚠️ Monaco Editor가 아직 로딩 중입니다.', 'warning');
    return;
  }
  
  // Diagnostics 뷰 가리기
  diagnosticsContent.style.display = 'none';
  diagnosticsEmpty.style.display = 'none';
  
  // 에디터 뷰 활성화
  editorContentWrapper.style.display = 'flex';
  isInlineEditorActive = true; // B1: 자동 갱신·재선택이 에디터 뷰를 덮지 않도록 표시

  // 제어 단추 상태 강제 매칭 보장
  if (editorBackBtn) {
    editorBackBtn.style.display = 'inline-flex';
  }
  if (saveCodeBtn) {
    saveCodeBtn.style.display = 'inline-flex';
  }
  
  document.querySelectorAll('.tree-file-item').forEach(item => {
    item.classList.remove('active');
  });

  // 코드 로드 및 레이아웃 리사이즈 갱신
  selectEditorFile(path);
  
  if (window.monacoEditor) {
    setTimeout(() => {
      window.monacoEditor.layout();
    }, 100);
  }
}

function closeInlineEditor() {
  editorContentWrapper.style.display = 'none';
  diagnosticsContent.style.display = 'flex';
  isInlineEditorActive = false;

  if (editorBackBtn) {
    editorBackBtn.style.display = 'none';
  }

  if (currentTab === 'outbox' && selectedTxId) {
    const tx = outboxData.find(t => t.transaction_id === selectedTxId);
    if (tx) selectTxRow(tx, activeEventInTx ? activeEventInTx.id : null);
  } else if (currentTab === 'file' && selectedFileId) {
    const log = fileData.find(f => f.id === selectedFileId);
    if (log) selectFileRow(log);
  } else if (currentTab === 'workspace' && selectedWorkspaceName) {
    const ws = workspaceData.find(w => w.name === selectedWorkspaceName);
    if (ws) selectWorkspaceRow(ws);
  } else if (currentTab === 'chain' && selectedChainName) {
    const rule = chainData.find(c => c.name === selectedChainName);
    if (rule) selectChainRow(rule);
  } else if (currentTab === 'autoupdate' && selectedAutoUpdateScript) {
    const col = autoUpdateData.find(c => c.script_name === selectedAutoUpdateScript);
    if (col) selectAutoUpdateRow(col);
  } else {
    // 복원할 선택이 없으면 빈 상태 표시 (스택 잔존 방지)
    clearDiagnostics();
  }
}

// --- Pipeline Health Strip (소안 §C) ---------------------------------------
// 기존 API만 조합: /admin/file-ingestion/failed · /admin/outbox/failed
//                 · /admin/auto-update/status · /enrichment/rules (+blank 필터 카운트)
// 신규 서버 API 없음. 실패 시 카드만 '조회 실패'로 두고 무음 (본문 흐름 비방해).

function setHealthCard(key, status, main, sub) {
  const card = document.getElementById(`health-card-${key}`);
  if (!card) return;
  card.dataset.status = status;
  const mainEl = document.getElementById(`health-${key}-main`);
  const subEl = document.getElementById(`health-${key}-sub`);
  if (mainEl) mainEl.textContent = main;
  if (subEl) {
    subEl.textContent = sub;
    subEl.title = sub;
  }
}

let healthRefreshInFlight = false;
async function refreshHealthStrip() {
  if (healthRefreshInFlight) return; // 수동 Refresh + 30s 폴링 중첩 방지
  healthRefreshInFlight = true;
  try {
    await Promise.allSettled([
      refreshFileAndAutoHealth(),
      refreshChainHealth(),
      refreshEnrichmentHealth()
    ]);
  } finally {
    healthRefreshInFlight = false;
  }
}

// File 카드 + Auto Update 카드 (실패 로그 최근 100건을 공용으로 사용)
async function refreshFileAndAutoHealth() {
  let failedTotal = null;
  let failedLogs = [];
  try {
    const res = await fetch(`${API_BASE}/admin/file-ingestion/failed?page=1&limit=100`);
    if (res.ok) {
      const r = await res.json();
      failedTotal = r.total || 0;
      failedLogs = r.data || [];
    }
  } catch (e) { /* 아래에서 조회 실패 카드 처리 */ }

  if (failedTotal === null) {
    setHealthCard('file', 'loading', '—', '상태 조회 실패');
  } else if (failedTotal > 0) {
    setHealthCard('file', 'danger', `실패 ${failedTotal}건`, '클릭 → 실패 로그 필터로 이동');
  } else {
    setHealthCard('file', 'ok', '실패 0건', '파일 인제션 정상');
  }

  try {
    const res = await fetch(`${API_BASE}/admin/auto-update/status`);
    if (!res.ok) throw new Error('auto-update status fetch failed');
    const r = await res.json();
    const collectors = r.data || [];
    if (collectors.length === 0) {
      setHealthCard('auto', 'loading', '수집기 없음', '등록된 auto-update 설정 없음');
      return;
    }

    const failCount = collectors.filter(c => c.last_status === 'FAIL').length;
    // 감사 §1.2 실증 시나리오 연계: 수집기는 SUCCESS인데 산출물 파일 인제션이
    // 실패 중인 경우를 카드에서 즉시 노출 (auto-update 대상 테이블 ∩ 최근 실패 로그)
    const autoTables = new Set(collectors.map(c => c.table_name));
    const linkedFails = failedLogs.filter(l => autoTables.has(l.table_name)).length;
    const linkedSuffix = (failedTotal !== null && failedTotal > failedLogs.length) ? '+' : '';

    let status = 'ok';
    if (failCount > 0) status = 'danger';
    else if (linkedFails > 0) status = 'warn';

    const main = failCount > 0
      ? `수집기 실패 ${failCount}/${collectors.length}`
      : `수집기 ${collectors.length}개 정상`;
    const sub = linkedFails > 0
      ? `산출물 인제션 실패 ${linkedFails}${linkedSuffix}건`
      : `최근 실행 ${formatTimestamp(latestLastRun(collectors))}`;
    setHealthCard('auto', status, main, sub);
  } catch (e) {
    setHealthCard('auto', 'loading', '—', '상태 조회 실패');
  }
}

function latestLastRun(collectors) {
  const runs = collectors.map(c => c.last_run).filter(Boolean).sort();
  return runs.length ? runs[runs.length - 1] : null;
}

async function refreshChainHealth() {
  try {
    const res = await fetch(`${API_BASE}/admin/outbox/failed?page=1&limit=1`);
    if (!res.ok) throw new Error('chain health fetch failed');
    const r = await res.json();
    const total = r.total || 0;
    if (total > 0) {
      setHealthCard('chain', 'danger', `실패 트랜잭션 ${total}건`, '클릭 → Outbox 실패 목록으로 이동');
    } else {
      setHealthCard('chain', 'ok', '실패 0건', '체인 파이프라인 정상');
    }
  } catch (e) {
    setHealthCard('chain', 'loading', '—', '상태 조회 실패');
  }
}

async function refreshEnrichmentHealth() {
  try {
    const res = await fetch(`${API_BASE}/enrichment/rules`);
    if (!res.ok) throw new Error('enrichment rules fetch failed');
    const r = await res.json();
    const rules = r.rules || [];
    if (rules.length === 0) {
      setHealthCard('enrichment', 'loading', '규칙 없음', '활성 enrichment 규칙 없음');
      return;
    }
    // 결손 카운트: 메인 페이지 배지(ui.js updateEnrichmentBadge)와 동일한
    // blank 필터 total 조회를 규칙별로 재사용 (limit=1 — total만 사용)
    let missing = 0;
    for (const rule of rules) {
      const filters = {};
      (rule.target_fields || []).forEach(f => { filters[f] = { type: 'blank' }; });
      const url = `${API_BASE}/tables/${encodeURIComponent(rule.derived_table)}/data` +
        `?skip=0&limit=1&filters=${encodeURIComponent(JSON.stringify(filters))}`;
      const cres = await fetch(url);
      if (!cres.ok) continue;
      const cr = await cres.json();
      missing += cr.total || 0;
    }
    if (missing > 0) {
      setHealthCard('enrichment', 'warn', `결손 ${missing}건`, `규칙 ${rules.length}개 · 클릭 → Enrichment Queue`);
    } else {
      setHealthCard('enrichment', 'ok', '결손 0건', `규칙 ${rules.length}개 · 모두 충족`);
    }
  } catch (e) {
    setHealthCard('enrichment', 'loading', '—', '상태 조회 실패');
  }
}
