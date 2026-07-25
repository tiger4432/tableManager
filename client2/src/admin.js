// Pipeline Admin Dashboard client logic
// 탭 축 = 파이프라인 생애주기: Overview / File Ingestion / Chain / Auto Update / Enrichment
// (구 메커니즘 7탭 폐지 — Outbox·Rules·Mappers는 Chain 탭으로, Workspaces는 File 탭으로 수렴.
//  Code Editor는 독립 탭 대신 각 탭의 편집 딥링크로 진입하는 공용 뷰. #editor URL 호환 유지)
import './tokens.css';
import { initTheme, getTheme } from './theme.js';

const isDevServer = window.location.port === '5173';
const API_BASE = isDevServer ? 'http://127.0.0.1:8080' : window.location.origin;

const byId = (id) => document.getElementById(id);

// ── State Cache ─────────────────────────────────────────────
let currentTab = 'overview'; // 'overview' | 'file' | 'chain' | 'autoupdate' | 'enrichment'

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
let linkedFailLogs = [];        // Auto Update 탭: 산출물 인제션 실패 (auto 대상 테이블 ∩ 최근 실패 100건)
let linkedFailTotalHint = false; // 실패 로그가 100건을 넘어 교집합이 하한치일 때 'N+' 표기
let enrichmentStatusData = null; // { rules, perRule:[{rule, missing}], totalMissing }

let selectedTxId = null;
let selectedFileId = null;
let selectedWorkspaceName = null;
let selectedChainName = null;
let selectedMapperFile = null;
let selectedAutoUpdateScript = null;
let selectedEnrichmentRule = null;
let activeEventInTx = null;

// Code Editor State (공용 뷰 — 딥링크로 진입)
let isMonacoLoaded = false;
let activeEditorFilePath = null;
let isEditorDirty = false;          // B2: Monaco 미저장 변경 추적
let suppressDirtyTracking = false;  // 프로그램틱 setValue 중 dirty 오탐 방지
let isInlineEditorActive = false;   // B1: 에디터 뷰 열림 여부 (자동 갱신/재선택 억제)
let pendingEditorOpen = null;       // Monaco 로딩 전 에디터 딥링크 대기 { path }
let scriptsListCache = null;        // /admin/scripts/list 캐시 (에디터 파일 피커용)

// UX State
let fetchSeq = 0;                   // 탭 전환/연타 fetch 레이스 가드 시퀀스
let fileSortKey = null;             // B3: 파일 로그 현재 페이지 내 클라이언트 정렬
let fileSortDir = 'asc';
let tabDefs = [];                   // switchTab()이 참조하는 탭 정의 (setupEventListeners에서 채움)
const AUTO_REFRESH_MS = 30000;      // 절제된 자동 갱신 주기 (Overview/File/Chain 탭 + 헬스 스트립)

// 구 탭 딥링크·북마크 호환: 구 메커니즘 탭 이름 → 신 파이프라인 탭
const TAB_ALIASES = {
  overview: 'overview',
  file: 'file',
  chain: 'chain',
  autoupdate: 'autoupdate',
  enrichment: 'enrichment',
  outbox: 'chain',      // 구 Outbox Failures 탭 (outbox fail = chain fail)
  workspace: 'file',    // 구 Workspaces 탭
  mapper: 'chain'       // 구 Mappers 탭
  // 'editor'는 라우터에서 별도 처리 (공용 에디터 뷰)
};

// ── DOM Elements ────────────────────────────────────────────
const tabOverviewBtn = byId('tab-overview-btn');
const tabFileBtn = byId('tab-file-btn');
const tabChainBtn = byId('tab-chain-btn');
const tabAutoUpdateBtn = byId('tab-autoupdate-btn');
const tabEnrichmentBtn = byId('tab-enrichment-btn');

const overviewWrapper = byId('overview-wrapper');
const fileTabWrapper = byId('file-tab-wrapper');
const chainTabWrapper = byId('chain-tab-wrapper');
const autoUpdateTabWrapper = byId('autoupdate-tab-wrapper');
const enrichmentTabWrapper = byId('enrichment-tab-wrapper');

const overviewGrid = byId('overview-grid');
const healthStripEl = byId('health-strip');
const statusFilterSelect = byId('status-filter');

const outboxListBody = byId('outbox-list-body');
const fileListBody = byId('file-list-body');
const workspaceListBody = byId('workspace-list-body');
const chainListBody = byId('chain-list-body');
const mapperListBody = byId('mapper-list-body');
const autoUpdateListBody = byId('autoupdate-list-body');
const autoLinkedBody = byId('autoupdate-linked-body');
const enrichmentListBody = byId('enrichment-list-body');

const outboxEmptyState = byId('outbox-empty');
const fileEmptyState = byId('file-empty');
const workspaceEmptyState = byId('workspace-empty');
const chainEmptyState = byId('chain-empty');
const mapperEmptyState = byId('mapper-empty');
const autoUpdateEmptyState = byId('autoupdate-empty');
const autoLinkedEmptyState = byId('autoupdate-linked-empty');
const enrichmentEmptyState = byId('enrichment-empty');

const lastRefreshedSpan = byId('last-refreshed');
const refreshBtn = byId('refresh-btn');
const reloadConfigsBtn = byId('reload-configs-btn');
const pageSizeSelect = byId('page-size-select');
const retryAllOutboxBtn = byId('retry-all-outbox-btn');
const retryAllFileBtn = byId('retry-all-file-btn');
const openEnrichmentBtn = byId('open-enrichment-btn');

const diagnosticsContent = byId('diagnostics-content');
const diagnosticsEmpty = byId('diagnostics-empty');
const diagnosticsEmptyText = byId('diagnostics-empty-text');
const diagnosticsTitle = byId('diagnostics-title');
const txEventsSelectorBlock = byId('tx-events-selector-block');
const txEventsList = byId('tx-events-list');
const tracebackTitle = byId('traceback-title');
const tracebackSeverity = byId('traceback-severity');
const tracebackViewer = byId('traceback-viewer');
const payloadTitle = byId('payload-title');
const payloadViewer = byId('payload-viewer');
const copyPayloadBtn = byId('copy-payload-btn');
const toastContainer = byId('toast-container');

// Pagination DOM Elements
const panelFooter = document.querySelector('.panel-footer');
const paginationInfo = byId('pagination-info');
const prevPageBtn = byId('prev-page-btn');
const nextPageBtn = byId('next-page-btn');
const pageIndicator = byId('page-indicator');

// Editor Specific DOM Elements (공용 뷰)
const editorContentWrapper = byId('editor-content-wrapper');
const editorFilePath = byId('editor-file-path');
const editorFilePicker = byId('editor-file-picker');
const saveCodeBtn = byId('save-code-btn');
const editorBackBtn = byId('editor-back-btn');

// Layout Elements (Overview 전폭 모드 전환용)
const leftPanelEl = document.querySelector('.left-panel');
const rightPanelEl = document.querySelector('.right-panel');
const splitResizerEl = byId('split-resizer');

// ── Initialize ──────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  setupEventListeners();
  initMonacoEditor();

  // 해시/쿼리 라우팅 적용 (기본 Overview) — switchTab이 fetchData + 스트립 갱신 수행
  applyRoute(true);

  // 절제된 자동 갱신: 백그라운드 탭·에디터 사용 중엔 건너뛴다 (감사 F2)
  setInterval(() => {
    if (document.hidden) return;
    if (currentTab !== 'overview') refreshHealthStrip(); // Overview에선 본문이 확장판이므로 스트립 생략
    if (isInlineEditorActive || isEditorDirty) return;
    if (currentTab === 'overview' || currentTab === 'file' || currentTab === 'chain') {
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

  // 브라우저 back/forward·수기 해시 변경 대응
  window.addEventListener('hashchange', () => applyRoute(false));
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

// 섹션 헤더 카운트 배지 갱신
function setSectionCount(id, value, tone) {
  const el = byId(id);
  if (!el) return;
  el.textContent = value;
  if (tone) el.dataset.tone = tone;
  else delete el.dataset.tone;
}

// mapper_module ("mappers.foo" / "pkg.mod") → 편집 가능한 파일 경로
function mapperModuleToPath(mod) {
  const p = mod || '';
  if (p.startsWith('mappers.')) return p.replace('mappers.', 'mappers/') + '.py';
  return `${p.replace(/\./g, '/')}.py`;
}

// ── 해시 라우터 (구 탭 딥링크 호환 포함) ───────────────────

function parseRoute() {
  let raw = (window.location.hash || '').replace(/^#/, '');
  if (!raw) raw = new URLSearchParams(window.location.search).get('tab') || '';
  const eq = raw.indexOf('=');
  const key = (eq >= 0 ? raw.slice(0, eq) : raw).toLowerCase();
  let value = null;
  if (eq >= 0) {
    try { value = decodeURIComponent(raw.slice(eq + 1)); } catch (e) { value = raw.slice(eq + 1); }
  }
  return { key, value };
}

function applyRoute(isInitial) {
  const { key, value } = parseRoute();
  if (key === 'editor') {
    // 구 Code Editor 탭 URL → 공용 에디터 뷰. #editor=<path>는 해당 파일 즉시 오픈.
    if (isInitial) switchTab('overview');
    openInlineEditor(value || null);
    return;
  }
  const tab = TAB_ALIASES[key] || 'overview';
  if (isInitial || tab !== currentTab) switchTab(tab);
}

// ── 레이아웃: Overview 전폭 모드 ───────────────────────────

function isEditorViewOpen() {
  return editorContentWrapper.style.display === 'flex';
}

function updatePanelLayout() {
  // Overview는 좌패널 전폭(우패널·리사이저 숨김). 단, 에디터 뷰가 열리면 우패널을 되살린다.
  const fullBleed = currentTab === 'overview' && !isEditorViewOpen();
  if (fullBleed) {
    if (!leftPanelEl.dataset.layoutSaved) {
      leftPanelEl.dataset.layoutSaved = '1';
      leftPanelEl.dataset.savedWidth = leftPanelEl.style.width || '';
      leftPanelEl.dataset.savedFlex = leftPanelEl.style.flex || '';
    }
    leftPanelEl.style.width = '';
    leftPanelEl.style.flex = '1 1 auto';
    splitResizerEl.style.display = 'none';
    rightPanelEl.style.display = 'none';
  } else {
    if (leftPanelEl.dataset.layoutSaved) {
      leftPanelEl.style.width = leftPanelEl.dataset.savedWidth;
      leftPanelEl.style.flex = leftPanelEl.dataset.savedFlex;
      delete leftPanelEl.dataset.layoutSaved;
    }
    splitResizerEl.style.display = 'block';
    rightPanelEl.style.display = 'flex';
  }
  healthStripEl.style.display = currentTab === 'overview' ? 'none' : 'grid';
}

// ── 탭 전환 본체 — 탭 버튼·헬스 카드·해시 라우터가 공용 ────

function switchTab(tabName, opts = {}) {
  const t = tabDefs.find(x => x.tab === tabName);
  if (!t) return;

  currentTab = t.tab;

  // Update Tab Button styles
  tabDefs.forEach(o => o.btn.classList.remove('active'));
  t.btn.classList.add('active');

  // Update Tab Wrapper Visibility
  tabDefs.forEach(o => o.wrapper.style.display = 'none');
  t.wrapper.style.display = 'block';

  // 딥링크 옵션: File 탭 상태 필터 프리셋 (헬스 카드 → 실패 필터)
  if (opts.statusFilter && statusFilterSelect) {
    statusFilterSelect.value = opts.statusFilter;
    filePage = 1;
  }

  // Controls visibility — 페이지네이션은 File 로그 / Chain 실패 목록 전용
  panelFooter.style.display = (t.tab === 'file' || t.tab === 'chain') ? 'flex' : 'none';
  if (pageSizeSelect) pageSizeSelect.value = String(t.tab === 'file' ? fileLimit : outboxLimit);

  // 인라인 에디터가 열려 있었어도 탭 전환은 뷰만 닫는다
  // (Monaco 내용은 유지 — 같은 파일을 다시 열면 미저장 변경이 보존됨)
  editorContentWrapper.style.display = 'none';
  isInlineEditorActive = false;
  if (editorBackBtn) editorBackBtn.style.display = 'none';
  clearDiagnostics();

  updatePanelLayout();
  history.replaceState(null, '', `#${t.tab}`);

  if (t.tab !== 'overview') refreshHealthStrip();
  fetchData();
}

// ── Event Listeners ────────────────────────────────────────

function setupEventListeners() {
  tabDefs = [
    { btn: tabOverviewBtn, tab: 'overview', wrapper: overviewWrapper },
    { btn: tabFileBtn, tab: 'file', wrapper: fileTabWrapper },
    { btn: tabChainBtn, tab: 'chain', wrapper: chainTabWrapper },
    { btn: tabAutoUpdateBtn, tab: 'autoupdate', wrapper: autoUpdateTabWrapper },
    { btn: tabEnrichmentBtn, tab: 'enrichment', wrapper: enrichmentTabWrapper }
  ];

  tabDefs.forEach(t => {
    t.btn.addEventListener('click', () => {
      if (currentTab === t.tab) return;
      switchTab(t.tab);
    });
  });

  // Pipeline Health 카드 딥링크: 해당 파이프라인 탭으로 이동
  const healthCardFile = byId('health-card-file');
  const healthCardChain = byId('health-card-chain');
  const healthCardAuto = byId('health-card-auto');
  const healthCardEnrichment = byId('health-card-enrichment');
  if (healthCardFile) {
    healthCardFile.addEventListener('click', () => {
      filePage = 1;
      switchTab('file', { statusFilter: 'FAILED' });
    });
  }
  if (healthCardChain) {
    healthCardChain.addEventListener('click', () => {
      outboxPage = 1;
      switchTab('chain');
    });
  }
  if (healthCardAuto) {
    healthCardAuto.addEventListener('click', () => {
      switchTab('autoupdate');
    });
  }
  if (healthCardEnrichment) {
    healthCardEnrichment.addEventListener('click', () => {
      switchTab('enrichment');
    });
  }

  // 생애 단계 섹션 접기/펼치기 (헤더 클릭 — 내부 액션 컨트롤 클릭은 제외)
  document.querySelectorAll('.section-header').forEach(h => {
    h.addEventListener('click', (e) => {
      if (e.target.closest('.section-actions')) return;
      const sec = h.closest('.stage-section');
      if (sec) sec.classList.toggle('collapsed');
    });
  });

  // Status filter change (File 탭 로그 섹션)
  statusFilterSelect.addEventListener('change', () => {
    filePage = 1;
    fetchData();
  });

  // 페이지 크기 선택 (B3): 활성 탭의 페이지네이션 목록 limit에 적용
  if (pageSizeSelect) {
    pageSizeSelect.addEventListener('change', () => {
      const n = parseInt(pageSizeSelect.value, 10) || 10;
      if (currentTab === 'file') {
        fileLimit = n;
        filePage = 1;
      } else if (currentTab === 'chain') {
        outboxLimit = n;
        outboxPage = 1;
      } else {
        return;
      }
      fetchData();
    });
  }

  // 파일 로그 헤더 클릭 정렬 (B3): 현재 페이지 내 클라이언트측 정렬
  document.querySelectorAll('#file-tab-wrapper th.sortable').forEach(th => {
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
    enrichmentStatusCache = null; // 수동 새로고침은 enrichment 캐시도 강제 만료
    if (currentTab !== 'overview') refreshHealthStrip();
    const ok = await fetchData();
    if (!ok) return; // 실패 토스트는 fetchData가 담당
    const messages = {
      overview: '♻️ 파이프라인 Overview를 새로고침했습니다.',
      file: '♻️ File Ingestion 현황을 새로고침했습니다.',
      chain: '♻️ Chain 파이프라인 현황을 새로고침했습니다.',
      autoupdate: '♻️ Auto Update 현황을 새로고침했습니다.',
      enrichment: '♻️ Enrichment 규칙 현황을 새로고침했습니다.'
    };
    showToast(messages[currentTab] || '♻️ 목록을 새로고침했습니다.', 'success');
  });

  // 일괄 재시도 — 섹션 헤더로 이동 (Chain 실패 / File 로그)
  if (retryAllOutboxBtn) {
    retryAllOutboxBtn.addEventListener('click', async () => {
      if (confirm('실패 상태인 모든 체인(아웃박스) 트랜잭션을 재실행하시겠습니까?')) {
        await retryAllFailed('outbox');
      }
    });
  }
  if (retryAllFileBtn) {
    retryAllFileBtn.addEventListener('click', async () => {
      if (confirm('실패 상태인 모든 파일 인제션 건을 재실행하시겠습니까?')) {
        await retryAllFailed('file');
      }
    });
  }

  if (openEnrichmentBtn) {
    openEnrichmentBtn.addEventListener('click', () => {
      window.location.href = '/enrichment.html';
    });
  }

  // Copy: 선택 종류는 상호배타이므로 탭이 아니라 선택 상태로 판별
  copyPayloadBtn.addEventListener('click', () => {
    let payloadToCopy = null;
    if (activeEventInTx) {
      payloadToCopy = activeEventInTx.payload;
    } else if (selectedFileId) {
      const log = fileData.find(e => e.id === selectedFileId)
        || linkedFailLogs.find(e => e.id === selectedFileId);
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
    } else if (selectedWorkspaceName) {
      payloadToCopy = workspaceData.find(w => w.name === selectedWorkspaceName);
    } else if (selectedChainName) {
      payloadToCopy = chainData.find(c => c.name === selectedChainName);
    } else if (selectedMapperFile) {
      payloadToCopy = mapperData.find(m => m.filename === selectedMapperFile);
    } else if (selectedAutoUpdateScript) {
      payloadToCopy = autoUpdateData.find(c => c.script_name === selectedAutoUpdateScript);
    } else if (selectedEnrichmentRule && enrichmentStatusData) {
      const pr = enrichmentStatusData.perRule.find(p => p.rule.name === selectedEnrichmentRule);
      if (pr) payloadToCopy = pr.rule;
    }

    if (payloadToCopy) {
      navigator.clipboard.writeText(JSON.stringify(payloadToCopy, null, 2))
        .then(() => showToast('📋 페이로드가 클립보드에 복사되었습니다.', 'success'))
        .catch(() => showToast('❌ 복사에 실패했습니다.', 'error'));
    } else {
      showToast('⚠️ 복사할 항목이 선택되지 않았습니다.', 'warning');
    }
  });

  // Pagination (File 로그 / Chain 실패 목록)
  prevPageBtn.addEventListener('click', () => {
    if (currentTab === 'chain' && outboxPage > 1) {
      outboxPage--;
      fetchData();
    } else if (currentTab === 'file' && filePage > 1) {
      filePage--;
      fetchData();
    }
  });

  nextPageBtn.addEventListener('click', () => {
    if (currentTab === 'chain') {
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

  // 에디터 파일 피커 (구 Code Editor 트리 대체 — 전체 스크립트 브라우즈)
  if (editorFilePicker) {
    editorFilePicker.addEventListener('change', () => {
      const p = editorFilePicker.value;
      if (!p) return;
      selectEditorFile(p); // dirty 가드 내장 — 취소 시 피커가 기존 파일로 복원됨
    });
  }

  // Initialize Split Panel Resizer Drag Logic
  if (splitResizerEl && leftPanelEl && rightPanelEl) {
    let isDragging = false;

    splitResizerEl.addEventListener('mousedown', (e) => {
      isDragging = true;
      document.body.classList.add('resizing-active');
      splitResizerEl.classList.add('dragging');
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

        leftPanelEl.style.width = `${leftWidth}px`;
        leftPanelEl.style.flex = 'none'; // flex-grow 간섭 차단

        if (window.monacoEditor) {
          window.monacoEditor.layout();
        }
      }
    });

    document.addEventListener('mouseup', () => {
      if (isDragging) {
        isDragging = false;
        document.body.classList.remove('resizing-active');
        splitResizerEl.classList.remove('dragging');

        if (window.monacoEditor) {
          window.monacoEditor.layout();
        }
      }
    });
  }
}

// ── Fetch (파이프라인 탭 단위 병렬 조회) ────────────────────
// - 레이스 가드: 탭 전환/연타 시 늦게 도착한 이전 요청 응답이 현재 탭 위에 렌더되는 것을 차단
// - options.silent: 자동 갱신 경로에서 실패 토스트 반복 방지
// - 반환값: 성공 여부 (Refresh 버튼이 실결과 토스트에 사용)
async function fetchData(options = {}) {
  const { silent = false } = options;
  const seq = ++fetchSeq;
  const tab = currentTab;
  const isStale = () => (seq !== fetchSeq || currentTab !== tab);
  try {
    if (tab === 'overview') {
      await fetchOverview(isStale);
      if (isStale()) return false;
    } else if (tab === 'file') {
      const statusVal = statusFilterSelect.value || 'ALL';
      const [logsRes, wsRes] = await Promise.all([
        fetch(`${API_BASE}/admin/file-ingestion/logs?status=${statusVal}&page=${filePage}&limit=${fileLimit}`),
        fetch(`${API_BASE}/admin/file-ingestion/workspaces`)
      ]);
      if (!logsRes.ok || !wsRes.ok) throw new Error('API fetch failed');
      const [logs, ws] = await Promise.all([logsRes.json(), wsRes.json()]);
      if (isStale()) return false;
      fileData = logs.data || [];
      fileTotal = logs.total || 0;
      workspaceData = ws.data || [];
      renderWorkspaceTable();
      renderFileTable();
    } else if (tab === 'chain') {
      const [obRes, rulesRes, mapRes] = await Promise.all([
        fetch(`${API_BASE}/admin/outbox/failed?page=${outboxPage}&limit=${outboxLimit}`),
        fetch(`${API_BASE}/admin/chain/rules`),
        fetch(`${API_BASE}/admin/mappers/list`)
      ]);
      if (!obRes.ok || !rulesRes.ok || !mapRes.ok) throw new Error('API fetch failed');
      const [ob, rules, maps] = await Promise.all([obRes.json(), rulesRes.json(), mapRes.json()]);
      if (isStale()) return false;
      outboxData = ob.data || [];
      outboxTotal = ob.total || 0;
      chainData = rules.data || [];
      mapperData = maps.data || [];
      renderChainTable();
      renderOutboxTable();
      renderMapperTable();
    } else if (tab === 'autoupdate') {
      const [stRes, failRes, wsRes] = await Promise.all([
        fetch(`${API_BASE}/admin/auto-update/status`),
        fetch(`${API_BASE}/admin/file-ingestion/failed?page=1&limit=100`),
        fetch(`${API_BASE}/admin/file-ingestion/workspaces`)
      ]);
      if (!stRes.ok) throw new Error('API fetch failed');
      const st = await stRes.json();
      const fails = failRes.ok ? await failRes.json() : { data: [], total: 0 };
      const ws = wsRes.ok ? await wsRes.json() : { data: [] };
      if (isStale()) return false;
      autoUpdateData = st.data || [];
      workspaceData = ws.data || [];
      // 산출물 인제션 연계 (감사 §1.2): auto-update 대상 테이블 ∩ 최근 실패 로그
      const autoTables = new Set(autoUpdateData.map(c => c.table_name));
      const failLogs = fails.data || [];
      linkedFailLogs = failLogs.filter(l => autoTables.has(l.table_name));
      linkedFailTotalHint = (fails.total || 0) > failLogs.length;
      renderAutoUpdateTable();
      renderLinkedFailTable();
    } else if (tab === 'enrichment') {
      const status = await fetchEnrichmentStatus();
      if (isStale()) return false;
      renderEnrichmentTable(status);
    }
    markRefreshed();
    return true;
  } catch (err) {
    if (isStale()) return false; // 무효화된 요청의 실패는 무음 처리
    console.error('Failed to fetch items', err);
    if (!silent) {
      const errorMsgs = {
        overview: '❌ 파이프라인 Overview 로드 실패',
        file: '❌ File Ingestion 현황 로드 실패',
        chain: '❌ Chain 파이프라인 현황 로드 실패',
        autoupdate: '❌ Auto Update 현황 로드 실패',
        enrichment: '❌ Enrichment 규칙 현황 로드 실패'
      };
      showToast(errorMsgs[tab] || '❌ 목록 로드 실패', 'error');
    }
    return false;
  }
}

// ── Renderers ──────────────────────────────────────────────

// Chain 탭 §오류: 실패 트랜잭션 목록 (Grouped by Transaction ID)
function renderOutboxTable() {
  outboxListBody.innerHTML = '';
  setSectionCount('chain-fail-count', outboxTotal, outboxTotal > 0 ? 'danger' : 'ok');

  if (outboxData.length === 0) {
    outboxEmptyState.style.display = 'flex';
    if (selectedTxId) clearDiagnostics();
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

// File 탭 §오류·실행: 파일 인제션 로그
function renderFileTable() {
  fileListBody.innerHTML = '';

  const statusFilterVal = statusFilterSelect.value;
  let tone = null;
  if (statusFilterVal === 'SUCCESS') tone = 'ok';
  else if (statusFilterVal === 'FAILED') tone = fileTotal > 0 ? 'danger' : 'ok';
  setSectionCount('file-log-count', fileTotal, tone);

  if (fileData.length === 0) {
    fileEmptyState.style.display = 'flex';
    if (selectedFileId) clearDiagnostics();
    updatePaginationFooter(0, 1, 1);
    return;
  }

  fileEmptyState.style.display = 'none';

  // B3: 현재 페이지 내 클라이언트측 정렬 (서버 정렬 파라미터는 이관 항목)
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
    const row = buildFileLogRow(log, { withStatus: true });
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

// 파일 로그 행 빌더 — File 탭 로그와 Auto Update 탭 산출물 실패 목록이 공용
function buildFileLogRow(log, { withStatus }) {
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
    ${withStatus ? `<td style="text-align: center;">${statusBadge}</td>` : ''}
    <td style="text-align: center; ${retryStyle}">${log.retry_count}</td>
    <td style="color: var(--text-muted); font-size: 0.85rem; font-family: var(--font-mono);" title="${log.created_at || ''}">${timeStr}</td>
    <td style="text-align: center;" onclick="event.stopPropagation()">
      ${retryBtnHtml}
    </td>
  `;

  row.addEventListener('click', () => {
    selectFileRow(log, row.parentElement || fileListBody);
  });

  const retryBtn = row.querySelector('.btn-retry-file');
  if (retryBtn) {
    retryBtn.addEventListener('click', async () => {
      if (confirm(`로그 ID #${log.id} 파일 인제션을 다시 재시도하시겠습니까?`)) {
        await retryFileIngestion(log.id);
      }
    });
  }

  return row;
}

// B3: 파일 로그 정렬 헤더 표시자(▲/▼) 갱신
function updateFileSortIndicators() {
  document.querySelectorAll('#file-tab-wrapper th.sortable').forEach(th => {
    const ind = th.querySelector('.sort-ind');
    if (!ind) return;
    ind.textContent = (th.dataset.key === fileSortKey)
      ? (fileSortDir === 'asc' ? ' ▲' : ' ▼')
      : '';
  });
}

// File 탭 §현황: Workspaces
function renderWorkspaceTable() {
  workspaceListBody.innerHTML = '';
  const noConfig = workspaceData.filter(w => !w.has_config).length;
  const withScripts = workspaceData.filter(w => (w.custom_scripts || []).length > 0).length;
  setSectionCount('workspace-count', workspaceData.length, noConfig > 0 ? 'warn' : null);
  const summaryEl = byId('workspace-summary');
  if (summaryEl) {
    summaryEl.textContent = workspaceData.length
      ? `config 누락 ${noConfig} · 커스텀 파서 ${withScripts}개`
      : '';
  }

  if (workspaceData.length === 0) {
    workspaceEmptyState.style.display = 'flex';
    if (selectedWorkspaceName) clearDiagnostics();
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

// Chain 탭 §현황: Chain Rules
function renderChainTable() {
  chainListBody.innerHTML = '';
  setSectionCount('chain-rule-count', chainData.length, null);

  if (chainData.length === 0) {
    chainEmptyState.style.display = 'flex';
    if (selectedChainName) clearDiagnostics();
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

// Chain 탭 §코드·수정: Mapper Modules
function renderMapperTable() {
  mapperListBody.innerHTML = '';
  setSectionCount('mapper-count', mapperData.length, null);

  if (mapperData.length === 0) {
    mapperEmptyState.style.display = 'flex';
    if (selectedMapperFile) clearDiagnostics();
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
      <td style="text-align: center;" onclick="event.stopPropagation()">
        <button class="glass-btn btn-primary btn-edit-mapper" style="padding: 4px 10px; font-size: 0.75rem;">🛠️ Edit</button>
      </td>
    `;

    row.addEventListener('click', () => {
      selectMapperRow(mapper);
    });

    const editBtn = row.querySelector('.btn-edit-mapper');
    editBtn.addEventListener('click', () => {
      openInlineEditor(`mappers/${mapper.filename}`);
    });

    mapperListBody.appendChild(row);
  });
}

// Auto Update 탭 §현황·실행: Collectors
function renderAutoUpdateTable() {
  autoUpdateListBody.innerHTML = '';
  const failCount = autoUpdateData.filter(c => c.last_status === 'FAIL').length;
  setSectionCount('autoupdate-count', autoUpdateData.length, failCount > 0 ? 'danger' : null);

  if (autoUpdateData.length === 0) {
    autoUpdateEmptyState.style.display = 'flex';
    if (selectedAutoUpdateScript) clearDiagnostics();
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

// Auto Update 탭 §오류: 산출물 인제션 실패 (수집기 SUCCESS ≠ 데이터 도착 — 감사 §1.2)
function renderLinkedFailTable() {
  autoLinkedBody.innerHTML = '';
  const suffix = linkedFailTotalHint && linkedFailLogs.length > 0 ? '+' : '';
  setSectionCount('autoupdate-linked-count', `${linkedFailLogs.length}${suffix}`,
    linkedFailLogs.length > 0 ? 'danger' : 'ok');

  if (linkedFailLogs.length === 0) {
    autoLinkedEmptyState.style.display = 'flex';
    return;
  }

  autoLinkedEmptyState.style.display = 'none';

  linkedFailLogs.forEach(log => {
    const row = buildFileLogRow(log, { withStatus: false });
    autoLinkedBody.appendChild(row);
  });

  if (selectedFileId && !isInlineEditorActive && currentTab === 'autoupdate') {
    const exists = linkedFailLogs.find(f => f.id === selectedFileId);
    if (exists) {
      selectFileRow(exists, autoLinkedBody);
    } else {
      clearDiagnostics();
    }
  }
}

// Enrichment 탭 §현황: 규칙 + 결손 카운트 (편집은 read-only 안내 — CRUD는 대안 이관)
function renderEnrichmentTable(status) {
  enrichmentStatusData = status;
  enrichmentListBody.innerHTML = '';
  setSectionCount('enrichment-rule-count', status.rules.length, null);
  const missEl = byId('enrichment-missing-count');
  if (missEl) {
    missEl.style.display = status.rules.length ? 'inline' : 'none';
    missEl.textContent = `결손 ${status.totalMissing}`;
    missEl.dataset.tone = status.totalMissing > 0 ? 'warn' : 'ok';
  }

  if (status.rules.length === 0) {
    enrichmentEmptyState.style.display = 'flex';
    if (selectedEnrichmentRule) clearDiagnostics();
    return;
  }

  enrichmentEmptyState.style.display = 'none';

  status.perRule.forEach(({ rule, missing }) => {
    const row = document.createElement('tr');
    row.className = `table-row ${selectedEnrichmentRule === rule.name ? 'active' : ''}`;
    row.dataset.name = rule.name;

    const missingBadge = missing == null
      ? `<span class="badge badge-warning">조회 실패</span>`
      : missing > 0
        ? `<span class="badge badge-warning" style="font-family: var(--font-mono);">${missing}</span>`
        : `<span class="badge badge-success" style="font-family: var(--font-mono);">0</span>`;

    row.innerHTML = `
      <td style="font-weight: bold; color: var(--color-primary);">${rule.name}</td>
      <td style="font-family: var(--font-mono); font-size: 0.82rem;">${rule.source_table || '-'} → ${rule.derived_table}</td>
      <td style="font-family: var(--font-mono); font-size: 0.82rem; color: var(--text-muted);">${(rule.target_fields || []).join(', ') || '-'}</td>
      <td style="text-align: center;">${missingBadge}</td>
      <td style="text-align: center;" onclick="event.stopPropagation()">
        <button class="glass-btn btn-primary btn-open-queue" style="padding: 4px 10px; font-size: 0.75rem;">🧩 Queue</button>
      </td>
    `;

    row.addEventListener('click', () => {
      selectEnrichmentRow(rule, missing);
    });

    row.querySelector('.btn-open-queue').addEventListener('click', () => {
      window.location.href = `/enrichment.html?rule=${encodeURIComponent(rule.name)}`;
    });

    enrichmentListBody.appendChild(row);
  });

  if (selectedEnrichmentRule && !isInlineEditorActive) {
    const pr = status.perRule.find(p => p.rule.name === selectedEnrichmentRule);
    if (pr) {
      selectEnrichmentRow(pr.rule, pr.missing);
    } else {
      clearDiagnostics();
    }
  }
}

// ── Overview 탭 (헬스 스트립 확장판 — 첫 화면) ─────────────

async function fetchOverview(isStale) {
  const [failedRes, wsRes, outboxRes, rulesRes, mappersRes, autoRes] = await Promise.all([
    fetch(`${API_BASE}/admin/file-ingestion/failed?page=1&limit=100`),
    fetch(`${API_BASE}/admin/file-ingestion/workspaces`),
    fetch(`${API_BASE}/admin/outbox/failed?page=1&limit=3`),
    fetch(`${API_BASE}/admin/chain/rules`),
    fetch(`${API_BASE}/admin/mappers/list`),
    fetch(`${API_BASE}/admin/auto-update/status`)
  ].map(p => p.catch(() => null)));

  const jsonOf = async (r) => (r && r.ok) ? r.json().catch(() => null) : null;
  const [failed, ws, outbox, rules, mappers, auto] = await Promise.all(
    [failedRes, wsRes, outboxRes, rulesRes, mappersRes, autoRes].map(jsonOf)
  );

  let enrich = null;
  try {
    enrich = await fetchEnrichmentStatus();
  } catch (e) { /* 카드에서 조회 실패 표기 */ }

  if (isStale()) return;

  // 전 소스 실패면 탭 에러 경로로 (개별 실패는 카드 단위 표기)
  if (!failed && !outbox && !auto && !enrich) {
    throw new Error('overview fetch failed');
  }

  renderOverview({ failed, ws, outbox, rules, mappers, auto, enrich });
}

function ovEventItem({ time, text, badge, badgeTone }) {
  const li = document.createElement('li');
  li.className = 'ov-event';
  if (time != null) {
    const t = document.createElement('span');
    t.className = 'ov-event-time';
    t.textContent = time;
    li.appendChild(t);
  }
  const tx = document.createElement('span');
  tx.className = 'ov-event-text';
  tx.textContent = text;
  tx.title = text;
  li.appendChild(tx);
  if (badge != null) {
    const b = document.createElement('span');
    b.className = `ov-event-badge ${badgeTone || ''}`;
    b.textContent = badge;
    li.appendChild(b);
  }
  return li;
}

function ovCard({ status, title, metrics, events, emptyText, onOpen, extraButtons }) {
  const card = document.createElement('article');
  card.className = 'ov-card';
  card.dataset.status = status;

  const head = document.createElement('div');
  head.className = 'ov-card-head';
  const dot = document.createElement('span');
  dot.className = 'health-dot';
  const titleEl = document.createElement('span');
  titleEl.className = 'ov-title';
  titleEl.textContent = title;
  head.appendChild(dot);
  head.appendChild(titleEl);

  (extraButtons || []).forEach(({ label, onClick }) => {
    const b = document.createElement('button');
    b.className = 'glass-btn btn-primary';
    b.style.cssText = 'padding: 4px 12px; font-size: 0.78rem;';
    b.textContent = label;
    b.addEventListener('click', (e) => {
      e.stopPropagation();
      onClick();
    });
    head.appendChild(b);
  });

  const openBtn = document.createElement('button');
  openBtn.className = 'glass-btn';
  openBtn.style.cssText = 'padding: 4px 12px; font-size: 0.78rem;';
  openBtn.textContent = '탭 열기 →';
  openBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    onOpen();
  });
  head.appendChild(openBtn);
  card.appendChild(head);

  const metricsEl = document.createElement('div');
  metricsEl.className = 'ov-metrics';
  metrics.forEach(({ value, label, tone }) => {
    const m = document.createElement('div');
    m.className = 'ov-metric';
    if (tone) m.dataset.tone = tone;
    const v = document.createElement('div');
    v.className = 'ov-metric-value';
    v.textContent = value;
    const l = document.createElement('div');
    l.className = 'ov-metric-label';
    l.textContent = label;
    m.appendChild(v);
    m.appendChild(l);
    metricsEl.appendChild(m);
  });
  card.appendChild(metricsEl);

  const list = document.createElement('ul');
  list.className = 'ov-events';
  if (events && events.length) {
    events.forEach(ev => list.appendChild(ovEventItem(ev)));
  } else {
    const line = document.createElement('li');
    line.className = 'ov-empty-line';
    line.textContent = emptyText || '표시할 최근 이벤트 없음';
    list.appendChild(line);
  }
  card.appendChild(list);

  card.addEventListener('click', onOpen);
  return card;
}

function renderOverview({ failed, ws, outbox, rules, mappers, auto, enrich }) {
  overviewGrid.innerHTML = '';

  // ① File Ingestion 카드
  {
    const total = failed ? (failed.total || 0) : null;
    const wsCount = ws ? (ws.data || []).length : null;
    const status = total == null ? 'loading' : (total > 0 ? 'danger' : 'ok');
    const events = (failed ? (failed.data || []).slice(0, 3) : []).map(l => ({
      time: formatTimestamp(l.created_at),
      text: `${l.filename} → ${l.table_name}`,
      badge: 'FAIL',
      badgeTone: 'danger'
    }));
    overviewGrid.appendChild(ovCard({
      status,
      title: 'File Ingestion',
      metrics: [
        { value: total == null ? '—' : total, label: '인제션 실패', tone: total > 0 ? 'danger' : (total === 0 ? 'ok' : null) },
        { value: wsCount == null ? '—' : wsCount, label: 'Workspaces' }
      ],
      events,
      emptyText: total == null ? '상태 조회 실패' : '최근 실패 없음 — 파이프라인 정상',
      onOpen: () => switchTab('file', total > 0 ? { statusFilter: 'FAILED' } : {})
    }));
  }

  // ② Chain 카드 (outbox fail = chain fail)
  {
    const total = outbox ? (outbox.total || 0) : null;
    const ruleCount = rules ? (rules.data || []).length : null;
    const mapperCount = mappers ? (mappers.data || []).length : null;
    const status = total == null ? 'loading' : (total > 0 ? 'danger' : 'ok');
    const events = (outbox ? (outbox.data || []).slice(0, 3) : []).map(tx => ({
      time: formatTimestamp(tx.failed_at),
      text: (tx.table_names || []).join(', ') || shortTxId(tx.transaction_id),
      badge: `재시도 ${tx.retry_count}`,
      badgeTone: 'danger'
    }));
    overviewGrid.appendChild(ovCard({
      status,
      title: 'Chain',
      metrics: [
        { value: total == null ? '—' : total, label: '실패 트랜잭션', tone: total > 0 ? 'danger' : (total === 0 ? 'ok' : null) },
        { value: ruleCount == null ? '—' : ruleCount, label: 'Rules' },
        { value: mapperCount == null ? '—' : mapperCount, label: 'Mappers' }
      ],
      events,
      emptyText: total == null ? '상태 조회 실패' : '실패 트랜잭션 없음 — 체인 정상',
      onOpen: () => switchTab('chain')
    }));
  }

  // ③ Auto Update 카드 (+ 산출물 인제션 연계 — 감사 §1.2 bonding_log 시나리오)
  {
    const collectors = auto ? (auto.data || []) : null;
    const failCount = collectors ? collectors.filter(c => c.last_status === 'FAIL').length : null;
    let linked = null;
    if (collectors && failed) {
      const autoTables = new Set(collectors.map(c => c.table_name));
      linked = (failed.data || []).filter(l => autoTables.has(l.table_name)).length;
    }
    let status = 'loading';
    if (collectors) {
      if (failCount > 0) status = 'danger';
      else if (linked > 0) status = 'warn';
      else status = 'ok';
    }
    const events = (collectors || [])
      .slice()
      .sort((a, b) => String(b.last_run || '').localeCompare(String(a.last_run || '')))
      .slice(0, 3)
      .map(c => ({
        time: formatTimestamp(c.last_run),
        text: c.script_name,
        badge: c.last_status || 'PENDING',
        badgeTone: c.last_status === 'SUCCESS' ? 'ok' : (c.last_status === 'FAIL' ? 'danger' : 'warn')
      }));
    overviewGrid.appendChild(ovCard({
      status,
      title: 'Auto Update',
      metrics: [
        { value: collectors == null ? '—' : collectors.length, label: '수집기' },
        { value: failCount == null ? '—' : failCount, label: '수집기 실패', tone: failCount > 0 ? 'danger' : (failCount === 0 ? 'ok' : null) },
        { value: linked == null ? '—' : linked, label: '산출물 인제션 실패', tone: linked > 0 ? 'warn' : (linked === 0 ? 'ok' : null) }
      ],
      events,
      emptyText: collectors == null ? '상태 조회 실패' : '등록된 수집기 없음',
      onOpen: () => switchTab('autoupdate')
    }));
  }

  // ④ Enrichment 카드
  {
    const status = enrich == null ? 'loading' : (enrich.totalMissing > 0 ? 'warn' : 'ok');
    const events = (enrich ? enrich.perRule.slice(0, 3) : []).map(({ rule, missing }) => ({
      time: null,
      text: rule.name,
      badge: missing == null ? '조회 실패' : `결손 ${missing}`,
      badgeTone: missing > 0 ? 'warn' : 'ok'
    }));
    overviewGrid.appendChild(ovCard({
      status,
      title: 'Enrichment',
      metrics: [
        { value: enrich == null ? '—' : enrich.rules.length, label: '규칙' },
        { value: enrich == null ? '—' : enrich.totalMissing, label: '결손 합계', tone: enrich && enrich.totalMissing > 0 ? 'warn' : (enrich ? 'ok' : null) }
      ],
      events,
      emptyText: enrich == null ? '상태 조회 실패' : '활성 규칙 없음',
      onOpen: () => switchTab('enrichment'),
      extraButtons: [{ label: '🧩 Queue', onClick: () => { window.location.href = '/enrichment.html'; } }]
    }));
  }
}

// ── Selection & Diagnostics ────────────────────────────────

// 좌측 목록 선택 상태 초기화 (선택 종류는 상호배타)
function clearSelections() {
  selectedTxId = null;
  selectedFileId = null;
  selectedWorkspaceName = null;
  selectedChainName = null;
  selectedMapperFile = null;
  selectedAutoUpdateScript = null;
  selectedEnrichmentRule = null;
  activeEventInTx = null;
}

// 한 탭 안에 여러 테이블이 공존하므로 하이라이트는 전 목록에서 걷어낸다
function clearRowHighlights() {
  [outboxListBody, fileListBody, workspaceListBody, chainListBody, mapperListBody,
    autoUpdateListBody, autoLinkedBody, enrichmentListBody].forEach(b => {
    if (b) b.querySelectorAll('.table-row.active').forEach(r => r.classList.remove('active'));
  });
}

// B1: 좌측 행 선택 시 인라인 에디터 뷰가 진단 패널과 스택되어 클립되던 결함 수리.
// 에디터 뷰가 열려 있으면 닫고 진행 — dirty면 사용자 확인(취소 시 행 선택 중단).
// Monaco 내용 자체는 유지되므로 같은 파일을 다시 열면 미저장 변경이 보존된다.
function ensureEditorViewClosed() {
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
  history.replaceState(null, '', `#${currentTab}`);
  updatePanelLayout();
  return true;
}

// Select Auto Update Row
function selectAutoUpdateRow(col) {
  if (!ensureEditorViewClosed()) return;
  clearSelections();
  selectedAutoUpdateScript = col.script_name;

  clearRowHighlights();
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

  const inlineEditBtn = byId('inline-edit-collector-btn');
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

// Select Transaction Row (Chain 탭 §오류)
function selectTxRow(tx, forceSelectEventId = null) {
  if (!ensureEditorViewClosed()) return;
  clearSelections();
  selectedTxId = tx.transaction_id;

  clearRowHighlights();
  outboxListBody.querySelectorAll('.table-row').forEach(r => {
    r.classList.toggle('active', r.dataset.txid === tx.transaction_id);
  });

  diagnosticsEmpty.style.display = 'none';
  diagnosticsContent.style.display = 'flex';

  diagnosticsTitle.textContent = '🔍 Chain Failure Diagnostics';
  tracebackTitle.textContent = 'Stack Trace / Error Reason';
  tracebackSeverity.textContent = 'CRITICAL';
  tracebackSeverity.className = 'badge-danger';
  tracebackSeverity.style.display = 'inline';

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

// Select File Row (File 탭 로그 / Auto Update 탭 산출물 실패 공용 — bodyEl로 하이라이트 대상 지정)
function selectFileRow(log, bodyEl = fileListBody) {
  if (!ensureEditorViewClosed()) return;
  clearSelections();
  selectedFileId = log.id;

  clearRowHighlights();
  if (bodyEl) {
    bodyEl.querySelectorAll('.table-row').forEach(r => {
      r.classList.toggle('active', parseInt(r.dataset.id, 10) === log.id);
    });
  }

  diagnosticsEmpty.style.display = 'none';
  diagnosticsContent.style.display = 'flex';
  txEventsSelectorBlock.style.display = 'none';

  diagnosticsTitle.textContent = '🔍 File Ingestion Diagnostics';
  tracebackTitle.textContent = 'Ingestion Error Message';
  tracebackSeverity.textContent = log.status || 'FAILED';
  tracebackSeverity.className = log.status === 'SUCCESS' ? 'badge badge-success' : 'badge badge-danger';
  tracebackSeverity.style.display = 'inline';

  tracebackViewer.textContent = log.error_message || 'No error traceback log captured (File ingested successfully).';

  // 관련 파서 스크립트 바로 열기 (수정 단계 딥링크 — 대상 테이블 워크스페이스의 커스텀 파서)
  const ws = workspaceData.find(w => w.table_name === log.table_name);
  if (ws && (ws.custom_scripts || []).length > 0) {
    payloadTitle.innerHTML = 'File Metadata / Log Details ' + ws.custom_scripts.map(s =>
      `<button class="glass-btn btn-primary btn-edit-parser" data-script="${s}" style="padding: 2px 8px; font-size: 0.72rem; margin-left: 8px;">🛠️ ${s}</button>`
    ).join('');
    payloadTitle.querySelectorAll('.btn-edit-parser').forEach(btn => {
      btn.addEventListener('click', () => {
        openInlineEditor(`ingestion_workspace/${ws.name}/scripts/${btn.dataset.script}`);
      });
    });
  } else {
    payloadTitle.textContent = 'File Metadata / Log Details';
  }

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

// Select Workspace Row (File 탭 §현황)
function selectWorkspaceRow(ws) {
  if (!ensureEditorViewClosed()) return;
  clearSelections();
  selectedWorkspaceName = ws.name;

  clearRowHighlights();
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

// Select Chain Rule Row (Chain 탭 §현황)
function selectChainRow(rule) {
  if (!ensureEditorViewClosed()) return;
  clearSelections();
  selectedChainName = rule.name;

  clearRowHighlights();
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

  const inlineEditBtn = byId('inline-edit-mapper-btn');
  if (inlineEditBtn) {
    inlineEditBtn.addEventListener('click', () => {
      openInlineEditor(mapperModuleToPath(rule.mapper_module));
    });
  }
}

// Select Mapper Row (Chain 탭 §코드·수정)
function selectMapperRow(mapper) {
  if (!ensureEditorViewClosed()) return;
  clearSelections();
  selectedMapperFile = mapper.filename;

  clearRowHighlights();
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

// Select Enrichment Rule Row (Enrichment 탭 §현황 — 편집은 read-only 안내)
function selectEnrichmentRow(rule, missing) {
  if (!ensureEditorViewClosed()) return;
  clearSelections();
  selectedEnrichmentRule = rule.name;

  clearRowHighlights();
  enrichmentListBody.querySelectorAll('.table-row').forEach(r => {
    r.classList.toggle('active', r.dataset.name === rule.name);
  });

  diagnosticsEmpty.style.display = 'none';
  diagnosticsContent.style.display = 'flex';
  txEventsSelectorBlock.style.display = 'none';

  diagnosticsTitle.textContent = '🧩 Enrichment Rule Details';
  tracebackTitle.textContent = '결손 현황 & 편집 안내';
  if (missing == null) {
    tracebackSeverity.textContent = '결손 조회 실패';
    tracebackSeverity.className = 'badge badge-warning';
  } else if (missing > 0) {
    tracebackSeverity.textContent = `결손 ${missing}건`;
    tracebackSeverity.className = 'badge badge-warning';
  } else {
    tracebackSeverity.textContent = '결손 없음';
    tracebackSeverity.className = 'badge badge-success';
  }
  tracebackSeverity.style.display = 'inline';

  const lines = [
    `규칙        : ${rule.name}`,
    `소스 → 파생 : ${rule.source_table || '-'} → ${rule.derived_table}`,
    `결정 키     : ${(rule.decision_key || []).join(', ') || '-'}`,
    `대상 필드   : ${(rule.target_fields || []).join(', ') || '-'}`,
    '',
    missing == null
      ? '결손 카운트 조회에 실패했습니다 (파생 테이블 blank 필터 조회 오류).'
      : missing > 0
        ? `대상 필드가 비어 있는 행이 ${missing}건 있습니다 — Queue에서 채우세요.`
        : '대상 필드가 모두 채워져 있습니다.'
  ];
  tracebackViewer.innerHTML = `<div style="color: var(--text-muted); line-height: 1.7; white-space: pre;">${lines.join('\n')}</div>` +
    `<div style="margin-top: 12px; color: var(--text-dim); line-height: 1.6;">✏️ 규칙 편집(read-only): 서버 <span style="font-family: var(--font-mono); color: var(--text);">server/config/enrichment_rules.json</span> 수기 편집 후 Reload Configs &amp; Code로 반영.<br>규칙 CRUD UI는 온보딩 위저드(대안 단계)로 이관.</div>`;

  payloadTitle.innerHTML = `Rule Configuration (read-only)
    <button id="enrichment-open-queue-btn" class="glass-btn btn-primary" style="padding: 2px 8px; font-size: 0.75rem; margin-left: 10px;">🧩 Queue 열기</button>`;
  payloadViewer.textContent = JSON.stringify(rule, null, 2);

  const queueBtn = byId('enrichment-open-queue-btn');
  if (queueBtn) {
    queueBtn.addEventListener('click', () => {
      window.location.href = `/enrichment.html?rule=${encodeURIComponent(rule.name)}`;
    });
  }
}

// Render error log traceback and payloads of Outbox Event (+ mapper 편집 딥링크)
function showEventDiagnostics(ev) {
  const errLog = ev.payload?.error_log || {};
  const reason = errLog.reason || 'No error traceback log captured.';
  tracebackViewer.textContent = reason;

  const cleanPayload = { ...ev.payload };
  delete cleanPayload.error_log;
  payloadViewer.textContent = JSON.stringify(cleanPayload, null, 2);

  // Chain 룰 연결: 이벤트 테이블과 매칭되는 룰의 mapper를 바로 연다 (수정 단계 딥링크)
  const rule = chainData.find(r => r.trigger_table === ev.table_name || r.target_table === ev.table_name);
  if (rule && rule.mapper_module) {
    payloadTitle.innerHTML = `Raw Event Payload / Details
      <button id="tx-edit-mapper-btn" class="glass-btn btn-primary" style="padding: 2px 8px; font-size: 0.72rem; margin-left: 8px;" title="rule: ${rule.name}">🛠️ Edit Mapper</button>`;
    const btn = byId('tx-edit-mapper-btn');
    if (btn) {
      btn.addEventListener('click', () => {
        openInlineEditor(mapperModuleToPath(rule.mapper_module));
      });
    }
  } else {
    payloadTitle.textContent = 'Raw Event Payload / Details';
  }
}

// Clear Diagnostics Panel
function clearDiagnostics() {
  clearSelections();

  diagnosticsContent.style.display = 'none';
  // B1: 인라인 에디터가 열려 있는 동안엔 빈 상태를 겹쳐 표시하지 않는다
  diagnosticsEmpty.style.display = isInlineEditorActive ? 'none' : 'flex';
  diagnosticsEmptyText.textContent = 'Select an item from the left list to view detailed configurations or diagnostics.';
  diagnosticsTitle.textContent = '🔍 Error & Event Diagnostics';

  txEventsSelectorBlock.style.display = 'none';
  txEventsList.innerHTML = '';
  tracebackViewer.textContent = '';
  payloadViewer.textContent = '';
  payloadTitle.textContent = 'Raw Event Payload / Details';
}

// Update Pagination Footer controls
function updatePaginationFooter(total, currentPage, maxPage) {
  const limit = currentTab === 'file' ? fileLimit : outboxLimit;
  const start = total === 0 ? 0 : (currentPage - 1) * limit + 1;
  const end = Math.min(currentPage * limit, total);

  paginationInfo.textContent = `Showing ${start}-${end} of ${total} items`;
  pageIndicator.textContent = `${currentPage} / ${maxPage}`;

  prevPageBtn.disabled = currentPage <= 1;
  nextPageBtn.disabled = currentPage >= maxPage;
}

// ── Retry APIs ─────────────────────────────────────────────

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
      if (currentTab !== 'chain') return;
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
    const stillFailed =
      (currentTab === 'file' && fileData.some(f => f.id === logId && f.status === 'FAILED')) ||
      (currentTab === 'autoupdate' && linkedFailLogs.some(f => f.id === logId));
    if (stillFailed) {
      showToast(`⚠️ 파일 인제션 ID #${logId} 재시도가 다시 실패했습니다. 오류 메시지를 확인하세요.`, 'warning');
      return;
    }
    showToast(`✅ 파일 인제션 ID #${logId} 재시도 완료 — ${result.message || '실패 목록에서 해제되었습니다.'}`, 'success');
  } catch (err) {
    console.error('Failed to retry file ingestion', logId, err);
    showToast('❌ 파일 인제션 재시도 요청 실패', 'error');
  }
}

// API Call: Retry all failed items (kind: 'outbox' | 'file' — 섹션 헤더 버튼이 명시)
async function retryAllFailed(kind) {
  try {
    if (kind === 'outbox') {
      const res = await fetch(`${API_BASE}/admin/outbox/retry-failed`, {
        method: 'POST'
      });
      if (!res.ok) throw new Error('Retry-all API returned error status');
      const result = await res.json();

      showToast(`🔄 ${result.message || '모든 실패 체인 트랜잭션이 초기화되었습니다.'}`, 'success');
      outboxPage = 1;
    } else {
      const res = await fetch(`${API_BASE}/admin/file-ingestion/retry-failed`, {
        method: 'POST'
      });
      if (!res.ok) throw new Error('Retry-all API returned error status');
      const result = await res.json();

      showToast(`🔄 ${result.message || '모든 실패 파일 인제션 건이 재실행되었습니다.'}`, 'success');
      filePage = 1;
    }
    fetchData();
    refreshHealthStrip();
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
    enrichmentStatusCache = null; // 규칙이 바뀌었을 수 있음
    scriptsListCache = null;      // 스크립트 목록도 최신화
    fetchData();
    refreshHealthStrip();
  } catch (err) {
    console.error('Failed to reload configs', err);
    showToast('❌ 시스템 핫-리로드 요청 실패', 'error');
  }
}

// ── Code Editor (공용 뷰 — 딥링크 진입) ─────────────────────

// Monaco Editor initialization
function initMonacoEditor() {
  if (typeof require === 'undefined') {
    console.warn('Monaco loader (require) is not defined yet. Retrying...');
    setTimeout(initMonacoEditor, 200);
    return;
  }
  require.config({ paths: { vs: 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.39.0/min/vs' } });
  require(['vs/editor/editor.main'], function () {
    window.monacoEditor = monaco.editor.create(byId('monaco-editor-container'), {
      value: '# Select a script file to start editing\n',
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
    // 에디터 딥링크(#editor / #editor=<path>)가 로딩 전에 요청됐다면 지금 연다
    if (pendingEditorOpen) {
      const p = pendingEditorOpen;
      pendingEditorOpen = null;
      openInlineEditor(p.path);
    }
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

// 에디터 파일 피커 (구 Code Editor 트리 대체) — /admin/scripts/list 캐시로 optgroup 구성
async function populateEditorPicker(force = false) {
  if (!editorFilePicker) return;
  if (!scriptsListCache || force) {
    try {
      const res = await fetch(`${API_BASE}/admin/scripts/list`);
      if (res.ok) {
        const result = await res.json();
        scriptsListCache = result.data || null;
      }
    } catch (e) { /* 피커 없이도 딥링크 편집은 동작 */ }
  }
  buildEditorPickerOptions();
}

function buildEditorPickerOptions() {
  if (!editorFilePicker) return;
  editorFilePicker.innerHTML = '<option value="">스크립트 선택…</option>';
  const d = scriptsListCache;
  if (!d) return;
  const groups = [
    ['Mappers', d.mappers || [], f => f.filename],
    ['Ingestion Parsers', d.ingestions || [], f => `${f.table_name} / ${f.filename}`],
    ['Auto Update Collectors', d.auto_updates || [], f => `${f.table_name} / ${f.filename}`]
  ];
  groups.forEach(([label, files, labelFn]) => {
    if (!files.length) return;
    const og = document.createElement('optgroup');
    og.label = label;
    files.forEach(f => {
      const o = document.createElement('option');
      o.value = f.path;
      o.textContent = labelFn(f);
      og.appendChild(o);
    });
    editorFilePicker.appendChild(og);
  });
  syncEditorPicker(activeEditorFilePath);
}

function syncEditorPicker(path) {
  if (!editorFilePicker) return;
  const has = path && Array.from(editorFilePicker.options).some(o => o.value === path);
  editorFilePicker.value = has ? path : '';
}

// Select a file and load its contents into Monaco Editor
async function selectEditorFile(path) {
  // B2: 편집 중인 동일 파일 재선택 — 서버 리로드로 미저장 변경을 덮어쓰지 않는다
  if (activeEditorFilePath === path && isEditorDirty) {
    syncEditorPicker(path);
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
      // 피커를 기존 파일로 복원하고 이동 취소
      syncEditorPicker(activeEditorFilePath);
      return;
    }
  }

  activeEditorFilePath = path;
  syncEditorPicker(path);

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
    if (isEditorViewOpen()) {
      history.replaceState(null, '', `#editor=${encodeURIComponent(path)}`);
    }
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

// 공용 에디터 뷰 열기 — path 없이 열면(구 #editor 딥링크) 피커로 브라우즈
function openInlineEditor(path = null) {
  if (!isMonacoLoaded) {
    pendingEditorOpen = { path };
    showToast('ℹ️ 코드 에디터 로딩 중 — 준비되면 자동으로 열립니다.', 'info');
    return;
  }

  // Diagnostics 뷰 가리기
  diagnosticsContent.style.display = 'none';
  diagnosticsEmpty.style.display = 'none';

  // 에디터 뷰 활성화
  editorContentWrapper.style.display = 'flex';
  isInlineEditorActive = true; // B1: 자동 갱신·재선택이 에디터 뷰를 덮지 않도록 표시
  updatePanelLayout();         // Overview 전폭 모드였다면 우패널을 되살린다

  // 제어 단추 상태 강제 매칭 보장
  if (editorBackBtn) {
    editorBackBtn.style.display = 'inline-flex';
  }
  if (saveCodeBtn) {
    saveCodeBtn.style.display = (path || activeEditorFilePath) ? 'inline-flex' : 'none';
  }

  populateEditorPicker();

  if (path) {
    selectEditorFile(path);
    history.replaceState(null, '', `#editor=${encodeURIComponent(path)}`);
  } else {
    history.replaceState(null, '', '#editor');
    syncEditorPicker(activeEditorFilePath);
    if (!activeEditorFilePath) {
      editorFilePath.textContent = 'Select a script file';
    }
  }

  if (window.monacoEditor) {
    setTimeout(() => {
      window.monacoEditor.layout();
    }, 100);
  }
}

function closeInlineEditor() {
  editorContentWrapper.style.display = 'none';
  isInlineEditorActive = false;

  if (editorBackBtn) {
    editorBackBtn.style.display = 'none';
  }

  history.replaceState(null, '', `#${currentTab}`);
  updatePanelLayout();

  if (currentTab === 'overview') {
    // Overview 전폭 모드 복귀 — 우패널 자체가 숨겨지므로 진단 복원 불필요
    diagnosticsContent.style.display = 'none';
    return;
  }

  diagnosticsContent.style.display = 'flex';

  // 선택 복원 (선택 종류는 상호배타)
  if (selectedTxId) {
    const tx = outboxData.find(t => t.transaction_id === selectedTxId);
    if (tx) { selectTxRow(tx, activeEventInTx ? activeEventInTx.id : null); return; }
  } else if (selectedFileId) {
    const log = fileData.find(f => f.id === selectedFileId)
      || linkedFailLogs.find(f => f.id === selectedFileId);
    if (log) {
      selectFileRow(log, currentTab === 'autoupdate' ? autoLinkedBody : fileListBody);
      return;
    }
  } else if (selectedWorkspaceName) {
    const ws = workspaceData.find(w => w.name === selectedWorkspaceName);
    if (ws) { selectWorkspaceRow(ws); return; }
  } else if (selectedChainName) {
    const rule = chainData.find(c => c.name === selectedChainName);
    if (rule) { selectChainRow(rule); return; }
  } else if (selectedMapperFile) {
    const m = mapperData.find(x => x.filename === selectedMapperFile);
    if (m) { selectMapperRow(m); return; }
  } else if (selectedAutoUpdateScript) {
    const col = autoUpdateData.find(c => c.script_name === selectedAutoUpdateScript);
    if (col) { selectAutoUpdateRow(col); return; }
  } else if (selectedEnrichmentRule && enrichmentStatusData) {
    const pr = enrichmentStatusData.perRule.find(p => p.rule.name === selectedEnrichmentRule);
    if (pr) { selectEnrichmentRow(pr.rule, pr.missing); return; }
  }
  // 복원할 선택이 없으면 빈 상태 표시 (스택 잔존 방지)
  clearDiagnostics();
}

// ── Enrichment 상태 (규칙 + 결손 카운트) — 스트립·탭·Overview 공용, 15s TTL 캐시 ──

let enrichmentStatusCache = null; // { ts, data }

async function fetchEnrichmentStatus(force = false) {
  const now = Date.now();
  if (!force && enrichmentStatusCache && (now - enrichmentStatusCache.ts) < 15000) {
    return enrichmentStatusCache.data;
  }
  const res = await fetch(`${API_BASE}/enrichment/rules`);
  if (!res.ok) throw new Error('enrichment rules fetch failed');
  const r = await res.json();
  const rules = r.rules || [];
  // 결손 카운트: 메인 페이지 배지(ui.js updateEnrichmentBadge)와 동일한
  // blank 필터 total 조회를 규칙별로 재사용 (limit=1 — total만 사용)
  const perRule = [];
  let totalMissing = 0;
  for (const rule of rules) {
    const filters = {};
    (rule.target_fields || []).forEach(f => { filters[f] = { type: 'blank' }; });
    let missing = null;
    try {
      const url = `${API_BASE}/tables/${encodeURIComponent(rule.derived_table)}/data` +
        `?skip=0&limit=1&filters=${encodeURIComponent(JSON.stringify(filters))}`;
      const cres = await fetch(url);
      if (cres.ok) {
        const cr = await cres.json();
        missing = cr.total || 0;
        totalMissing += missing;
      }
    } catch (e) { /* missing = null → 카드/배지에서 조회 실패 표기 */ }
    perRule.push({ rule, missing });
  }
  const data = { rules, perRule, totalMissing };
  enrichmentStatusCache = { ts: now, data };
  return data;
}

// ── Pipeline Health Strip (파이프라인 탭 상시 요약 — Overview에선 본문이 대체) ──
// 기존 API만 조합: /admin/file-ingestion/failed · /admin/outbox/failed
//                 · /admin/auto-update/status · /enrichment/rules (+blank 필터 카운트)
// 신규 서버 API 없음. 실패 시 카드만 '조회 실패'로 두고 무음 (본문 흐름 비방해).

function setHealthCard(key, status, main, sub) {
  const card = byId(`health-card-${key}`);
  if (!card) return;
  card.dataset.status = status;
  const mainEl = byId(`health-${key}-main`);
  const subEl = byId(`health-${key}-sub`);
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
    setHealthCard('file', 'danger', `실패 ${failedTotal}건`, '클릭 → File 탭 실패 필터로 이동');
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
      setHealthCard('chain', 'danger', `실패 트랜잭션 ${total}건`, '클릭 → Chain 탭 실패 목록으로 이동');
    } else {
      setHealthCard('chain', 'ok', '실패 0건', '체인 파이프라인 정상');
    }
  } catch (e) {
    setHealthCard('chain', 'loading', '—', '상태 조회 실패');
  }
}

async function refreshEnrichmentHealth() {
  try {
    const s = await fetchEnrichmentStatus();
    if (s.rules.length === 0) {
      setHealthCard('enrichment', 'loading', '규칙 없음', '활성 enrichment 규칙 없음');
      return;
    }
    if (s.totalMissing > 0) {
      setHealthCard('enrichment', 'warn', `결손 ${s.totalMissing}건`, `규칙 ${s.rules.length}개 · 클릭 → Enrichment 탭`);
    } else {
      setHealthCard('enrichment', 'ok', '결손 0건', `규칙 ${s.rules.length}개 · 모두 충족`);
    }
  } catch (e) {
    setHealthCard('enrichment', 'loading', '—', '상태 조회 실패');
  }
}
