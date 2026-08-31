// Pipeline Admin Dashboard client logic
// 탭 축 = 파이프라인 생애주기: Overview / File Ingestion / Chain / Auto Update / Enrichment
// (구 메커니즘 7탭 폐지 — Outbox·Rules·Mappers는 Chain 탭으로, Workspaces는 File 탭으로 수렴.
//  Code Editor는 독립 탭 대신 각 탭의 편집 딥링크로 진입하는 공용 뷰. #editor URL 호환 유지)
import './tokens.css';
import { initTheme, getTheme } from './theme.js';
// [전역 토스트] 자체 구현을 폐기하고 공용(utils.js)으로 일원화한다 —
// 구 admin 구현도 setTimeout 단독 수명이라 백그라운드 탭에서 동일하게 누적됐다.
import { showToast } from './utils.js';
// Enrichment 결손 카운트는 큐를 세는 것이다. 그 요청의 유일한 철자 (ui.js·enrichment.js 공용).
import { queueQuery } from './enrichment_queue.js';
// [V1 effort instrument] The ONE collector (effort_meter.js). Admin is an operations
// surface, not a correction surface, so nothing here carries an `effort` payload. What it
// must do is count LEAVING: grid -> admin was already counted while admin -> grid was not,
// so every trip through here recorded half its true cost. Under-counting the return leg
// flatters the score, on a baseline that cannot be collected twice.
import { ROUTES, startSession, installGlobalListeners, installNavLinkCounting } from './effort_meter.js';
// [F9] 「내 config가 먹었는가」. The view model lives in its own DOM-free module so the
// contract harness can score it: the server composes the operator-facing sentence and this
// page renders `detail` VERBATIM. Nothing here decides what counts as ineffective.
import {
  buildConfigResolveView, buildDryRunView, CHROME, fetchFailureLine,
} from './config_resolve_view.js';
// [Queue 25] 소급 적용(retroactive/backfill). 같은 규율의 두 번째 표면 — 서버가 문장을 만들고
// 여기서는 그대로 렌더한다. 특히 **숫자는 서버가 붙인 라벨과 함께가 아니면 화면에 나오지
// 않는다**: 다섯 중 넷은 요청 경로에서 정확할 수 없고, 그 한정어가 라벨 안에 들어 있다.
import {
  buildOperationsView, buildCountView, buildRunView, buildConfirmLines, buildActionsView,
  resolveCount, paramEntries, paramsKey, RETRO_CHROME, buildRunsView,
} from './retroactive_view.js';
// [원장 선언] 구조 맵을 admin이 호스트한다(브리프 §6-1 + 소유자 판정). 이 파일은 배선만
// 한다 — 지도의 리더도, 편집기도 자기 모듈이 소유한다.
import { initOntologyExplorer, refreshOntologyExplorer } from './ontology_explorer.js';
import { takeRescopeHandoff } from './rescope_handoff.js';

const isDevServer = window.location.port === '5173';
const API_BASE = isDevServer ? 'http://127.0.0.1:8080' : window.location.origin;

const byId = (id) => document.getElementById(id);

// ── Admin token (C1 access control) ──────────────────────────
// The server gates /admin/* behind a shared secret it reads from
// ASSY_ADMIN_TOKEN at startup. There is no login screen and no user model by
// design: this page asks for the one token, keeps it, and attaches it as a
// header. Every /admin/* call in this file goes through adminFetch() - `grep
// "fetch(\`${API_BASE}/admin/"` must return nothing, or that call site is
// unauthenticated and will 401 in production while working on an
// unconfigured server.
//
// When the server has no token configured the gated routes answer normally, so
// nothing prompts and this is invisible. The prompt appears only on a rejection
// the GATE issued, which is exactly the first load against a locked server.
const ADMIN_TOKEN_HEADER = 'X-Admin-Token';
const ADMIN_TOKEN_KEY = 'assy.adminToken';

function getAdminToken() {
  try { return localStorage.getItem(ADMIN_TOKEN_KEY) || ''; } catch (e) { return ''; }
}

function storeAdminToken(value) {
  try {
    if (value) localStorage.setItem(ADMIN_TOKEN_KEY, value);
    else localStorage.removeItem(ADMIN_TOKEN_KEY);
  } catch (e) { /* private mode / storage disabled: token lives for this page only */ }
}

// Bumped every time the stored token changes. A response that was already in
// flight when the token changed is stale evidence: it says nothing about the
// NEW token, so it must not trigger a second prompt. Without this the "one
// prompt for seven concurrent requests" property is timing luck - with a
// realistic multi-second modal, responses arriving after it closed produced
// extra prompts that accused a perfectly correct token of being wrong.
let adminTokenGeneration = 0;
// Set when the operator dismisses the prompt. Re-prompting on every 30s refresh
// forever is not a fix, it is a trap; they can reload the page to be asked again.
let adminTokenDeclined = false;
let tokenPromptInFlight = null;

/** True only for rejections the admin GATE issued.
 *
 * Status alone is not enough: `_resolve_admin_script_path` answers 403 when an
 * isolated server refuses a write into the live mappers/ tree, which has nothing
 * to do with the token. Treating that as an auth failure made the page demand a
 * token and then OVERWRITE the correct stored one with whatever was retyped.
 * The server marks its own rejections with `WWW-Authenticate: X-Admin-Token`.
 */
function isGateRejection(res) {
  if (res.status !== 401 && res.status !== 403) return false;
  const challenge = res.headers && res.headers.get
    ? (res.headers.get('WWW-Authenticate') || '') : '';
  return challenge.toLowerCase().includes(ADMIN_TOKEN_HEADER.toLowerCase());
}

function askForAdminToken(message) {
  if (!tokenPromptInFlight) {
    tokenPromptInFlight = new Promise((resolve) => {
      // Deferred a tick so sibling handlers from the same Promise.all attach to
      // this promise before the modal blocks the thread.
      setTimeout(() => {
        const entered = window.prompt(message, '');
        tokenPromptInFlight = null;
        if (entered === null) {
          // Cancel. Do NOT clear the stored token - the previous code turned a
          // cancel into storeAdminToken('') and DELETED a working token.
          adminTokenDeclined = true;
          showToast('관리자 토큰 입력을 취소했습니다. 새로고침하면 다시 물어봅니다.', 'warning');
          resolve('');
          return;
        }
        const value = entered.trim();
        if (value) {
          storeAdminToken(value);
          adminTokenGeneration += 1;
        }
        resolve(value);
      }, 0);
    });
  }
  return tokenPromptInFlight;
}

function withAdminToken(init) {
  const token = getAdminToken();
  if (!token) return init;
  const next = Object.assign({}, init || {});
  // Header only, never a query parameter: query strings are written to the
  // server's access log, headers are not.
  next.headers = Object.assign({}, (init && init.headers) || {},
    { [ADMIN_TOKEN_HEADER]: token });
  return next;
}

/** fetch() for /admin/* — attaches the token, and re-asks once if the GATE rejects it. */
async function adminFetch(url, init) {
  const generationAtSend = adminTokenGeneration;
  let res = await fetch(url, withAdminToken(init));

  // 503 = the server has no token configured and this route refuses to run
  // without one. The body names the variable and says to restart; surfacing it
  // here is the whole point of the 503 split, and the call sites would otherwise
  // show a generic "저장 중 오류 발생".
  if (res.status === 503) {
    try {
      const body = await res.clone().json();
      if (body && body.detail) showToast(body.detail, 'error', { ttl: 12000 });
    } catch (e) { /* not a JSON body - let the caller report it */ }
    return res;
  }

  if (!isGateRejection(res)) return res;

  // Someone else already replaced the token while this was in flight. Retry
  // silently with the new one instead of accusing it of being wrong.
  if (adminTokenGeneration !== generationAtSend) {
    return fetch(url, withAdminToken(init));
  }

  if (adminTokenDeclined) return res;

  const message = getAdminToken()
    ? '관리자 토큰이 거부되었습니다. 다시 입력해 주세요.'
    : '관리자 토큰을 입력하세요.';
  const token = await askForAdminToken(message);
  // Retry once only. A second rejection returns to the caller so the page shows
  // its own error instead of looping the operator on a modal.
  if (token) res = await fetch(url, withAdminToken(init));
  return res;
}

// ── State Cache ─────────────────────────────────────────────
let currentTab = 'overview'; // 'overview' | 'file' | 'chain' | 'autoupdate' | 'enrichment' | 'ontology'

let outboxPage = 1;
let outboxLimit = 10;
let outboxData = [];
let outboxTotal = 0;

let filePage = 1;
let fileLimit = 10;
let fileData = [];
let activeIngestionData = []; // [Heavy Lane P1] 진행 중 인제션 스냅샷
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
  ontology: 'ontology',
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
const tabOntologyBtn = byId('tab-ontology-btn');

const overviewWrapper = byId('overview-wrapper');
const fileTabWrapper = byId('file-tab-wrapper');
const chainTabWrapper = byId('chain-tab-wrapper');
const autoUpdateTabWrapper = byId('autoupdate-tab-wrapper');
const enrichmentTabWrapper = byId('enrichment-tab-wrapper');
const ontologyTabWrapper = byId('ontology-tab-wrapper');
const ontologyExplorerRoot = byId('ontology-explorer-root');

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

// [Heavy Lane P1] 진행 중 인제션 섹션
const activeIngestionSection = byId('sec-active-ingestions');
const activeIngestionBody = byId('active-ingestion-body');
const activeIngestionWarning = byId('active-ingestion-warning');

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
  // [V1 effort instrument] Before any listener can fire. Invisible — no UI, no badge.
  startSession();
  installGlobalListeners();
  installNavLinkCounting(ROUTES.ADMIN);
  setupEventListeners();
  initMonacoEditor();
  initConfigResolveLine();
  initRetroactiveLine();
  refreshRunning();
  scheduleRunsPoll();
  initOntologyExplorer({
    root: ontologyExplorerRoot,
    apiBase: API_BASE,
    adminFetch,
    showToast,
  });

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

/** 🔴 THE MAP ADDRESSES ITSELF WITH QUERY PARAMS, AND THAT PROPERTY IS THE ONE BEING PRESERVED.
 *
 * Every filter and every edge selection on the declaration map is an `<a href>` carrying
 * `?view=structure&layer=…&edge=…` — that is its 「컨트롤 0개 추가」 property, and it is the
 * reason the map has no state to get out of sync with its URL.
 *
 * ⚰️ 2026-08-25 그 협상은 «끝났습니다». 원장 선언 탭이 메뉴에서 빠지면서 admin 은
 *    `view=structure` 를 더 이상 알아보지 않습니다 — 그 주소로 들어오면 Overview 가 뜹니다.
 *    윗 문단은 그 탭이 있던 동안 왜 호스트가 충돌을 흡수했는지의 기록으로 남깁니다.
 */
// ⚰️ 2026-08-25 `mapQuestionFromLocation()` 이 여기 있었고, `?view=structure` 를 원장 선언
// 탭의 «주소»로 알아보는 자리였다. 그 탭이 메뉴에서 빠졌으므로 라우터도 그 주소를 모른다 --
// 지금 그 링크로 들어오면 아래 기본 갈래를 타 Overview 가 뜬다. 그 주소를 만들던 화면
// (`ledger.html`)은 이미 없고, 지도의 앵커를 아는 유일한 곳이 그 탭이었다.
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

// 좌패널 전폭으로 도는 탭 — 우패널의 진단·에디터를 쓰지 않고 자기 본문이 넓어야 하는 것들.
// (원장 선언 지도가 여기 있었다. 2026-08-25 탭과 함께 빠졌다.)
const FULL_BLEED_TABS = ['overview', 'ontology'];

function updatePanelLayout() {
  // 전폭 탭은 우패널·리사이저를 숨긴다. 단, 에디터 뷰가 열리면 우패널을 되살린다.
  const fullBleed = FULL_BLEED_TABS.includes(currentTab) && !isEditorViewOpen();
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
  healthStripEl.style.display = FULL_BLEED_TABS.includes(currentTab) ? 'none' : 'grid';
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
  if (t.tab === 'ontology') history.replaceState(null, '', '#ontology');
  else history.replaceState(null, '', `#${t.tab}`);

  if (!FULL_BLEED_TABS.includes(t.tab)) refreshHealthStrip();
  if (t.tab === 'ontology') refreshOntologyExplorer();
  else fetchData();
}

// ── Event Listeners ────────────────────────────────────────

function setupEventListeners() {
  tabDefs = [
    { btn: tabOverviewBtn, tab: 'overview', wrapper: overviewWrapper },
    { btn: tabFileBtn, tab: 'file', wrapper: fileTabWrapper },
    { btn: tabChainBtn, tab: 'chain', wrapper: chainTabWrapper },
    { btn: tabAutoUpdateBtn, tab: 'autoupdate', wrapper: autoUpdateTabWrapper },
    { btn: tabEnrichmentBtn, tab: 'enrichment', wrapper: enrichmentTabWrapper },
    { btn: tabOntologyBtn, tab: 'ontology', wrapper: ontologyTabWrapper }
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
      const [logsRes, wsRes, activeRes] = await Promise.all([
        adminFetch(`${API_BASE}/admin/file-ingestion/logs?status=${statusVal}&page=${filePage}&limit=${fileLimit}`),
        adminFetch(`${API_BASE}/admin/file-ingestion/workspaces`),
        adminFetch(`${API_BASE}/admin/file-ingestion/active`).catch(() => null)
      ]);
      if (!logsRes.ok || !wsRes.ok) throw new Error('API fetch failed');
      const [logs, ws] = await Promise.all([logsRes.json(), wsRes.json()]);
      // [Heavy Lane P1] 진행 목록은 보조 정보 — 조회 실패해도 본문 흐름 비방해
      let active = { data: [] };
      if (activeRes && activeRes.ok) {
        try { active = await activeRes.json(); } catch (e) { /* keep empty */ }
      }
      if (isStale()) return false;
      fileData = logs.data || [];
      fileTotal = logs.total || 0;
      workspaceData = ws.data || [];
      activeIngestionData = active.data || [];
      renderActiveIngestions();
      renderWorkspaceTable();
      renderFileTable();
    } else if (tab === 'chain') {
      const [obRes, rulesRes, mapRes] = await Promise.all([
        adminFetch(`${API_BASE}/admin/outbox/failed?page=${outboxPage}&limit=${outboxLimit}`),
        adminFetch(`${API_BASE}/admin/chain/rules`),
        adminFetch(`${API_BASE}/admin/mappers/list`)
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
        adminFetch(`${API_BASE}/admin/auto-update/status`),
        adminFetch(`${API_BASE}/admin/file-ingestion/failed?page=1&limit=100`),
        adminFetch(`${API_BASE}/admin/file-ingestion/workspaces`)
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

// [Heavy Lane P1] 경과 시간 포맷: 45s / 7m 32s / 1h 5m
function formatElapsed(sec) {
  if (sec == null || isNaN(sec)) return '-';
  const s = Math.max(0, Math.floor(sec));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

// [Heavy Lane P1] 진행 중 항목이 있는 동안만 도는 경량 갱신 타이머 (5s, File 탭 표시 중 한정).
// 서버 부하는 인메모리 스냅샷 조회 1회 — 진행 목록이 비면 자동 소멸.
let activeRefreshTimer = null;
function scheduleActiveRefresh() {
  if (activeRefreshTimer) return;
  activeRefreshTimer = setTimeout(async () => {
    activeRefreshTimer = null;
    if (document.hidden || currentTab !== 'file' || !activeIngestionData.length) return;
    try {
      const res = await adminFetch(`${API_BASE}/admin/file-ingestion/active`);
      if (res.ok) {
        const r = await res.json();
        activeIngestionData = r.data || [];
        renderActiveIngestions();
      }
    } catch (e) { /* 보조 정보 — 무음 */ }
  }, 5000);
}

// File 탭 §진행 중: Active Ingestions (진행률 바 + heavy 배지 + 재기동 경고)
// 항목이 없으면 섹션 자체를 숨긴다. 갱신: File 탭 fetch(30s/수동) + 활성 시 5s 경량 타이머.
function renderActiveIngestions() {
  if (!activeIngestionSection) return;
  const items = activeIngestionData;
  if (!items.length) {
    activeIngestionSection.style.display = 'none';
    return;
  }
  scheduleActiveRefresh();
  activeIngestionSection.style.display = '';
  setSectionCount('active-ingestion-count', items.length, 'warn');
  const heavyCount = items.filter(i => i.lane === 'heavy').length;
  const summaryEl = byId('active-ingestion-summary');
  if (summaryEl) summaryEl.textContent = heavyCount ? `heavy ${heavyCount}건 포함` : '';

  // [P1 재기동 경고] 체크포인트(P2) 도입 전 운영 안전장치 — 표시만, 서버측 차단 없음
  const maxProg = Math.max(...items.map(i => i.progress || 0));
  activeIngestionWarning.style.display = '';
  activeIngestionWarning.textContent =
    `⚠️ 인제션 진행 중 ${items.length}건 — 지금 서버를 재기동하면 진행 중 파일은 처음부터 재처리됩니다` +
    (items.length === 1 ? ` (${maxProg}% 진행)` : '');

  activeIngestionBody.innerHTML = '';
  items.forEach(item => {
    const row = document.createElement('tr');
    row.className = 'table-row';
    const laneBadge = item.lane === 'heavy'
      ? `<span class="badge badge-warning" style="font-weight: bold;">HEAVY</span>`
      : `<span class="badge badge-success">normal</span>`;
    const pct = Math.max(0, Math.min(item.progress || 0, 100));
    const statusNote = item.status === 'QUEUED' ? ' 대기' : '';
    const rowsText = (item.total_rows != null)
      ? `${(item.processed_rows || 0).toLocaleString()} / ${item.total_rows.toLocaleString()}`
      : ((item.processed_rows || 0) > 0 ? item.processed_rows.toLocaleString() : '-');
    row.innerHTML = `
      <td style="font-family: var(--font-mono); font-size: 0.85rem; color: var(--text); word-break: break-all;">${item.filename}</td>
      <td style="font-weight: bold; color: var(--color-primary);">${item.table_name}</td>
      <td style="text-align: center;">${laneBadge}</td>
      <td>
        <div style="display: flex; align-items: center; gap: 8px;">
          <div style="flex: 1; height: 6px; border-radius: 3px; background: var(--bg-inset); border: 1px solid var(--border); overflow: hidden;">
            <div style="width: ${pct}%; height: 100%; background: var(--accent); transition: width 0.4s;"></div>
          </div>
          <span style="font-family: var(--font-mono); font-size: 0.78rem; color: var(--text-muted); min-width: 46px; text-align: right;">${pct}%${statusNote}</span>
        </div>
      </td>
      <td style="text-align: center; font-family: var(--font-mono); font-size: 0.8rem; color: var(--text-muted);">${rowsText}</td>
      <td style="text-align: center; font-family: var(--font-mono); font-size: 0.8rem; color: var(--text-muted);">${formatElapsed(item.elapsed_seconds)}</td>
    `;
    activeIngestionBody.appendChild(row);
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
function chainRuleIsActive(rule) {
  return rule && rule.enabled !== false && rule.active !== false;
}

function chainRuleCapabilities(rule) {
  const badges = [];
  badges.push(`<span class="badge badge-muted">${rule.is_batch ? 'BATCH' : 'ROW'}</span>`);
  if (rule.allow_chain_trigger) badges.push('<span class="badge badge-warning">CASCADE</span>');
  if (rule.allow_map_metadata_upsert) badges.push('<span class="badge badge-warning">MAP META</span>');
  if (rule.allow_replace_map) badges.push('<span class="badge badge-danger">REPLACE MAP</span>');
  return badges.join('');
}

function chainRuleNarrative(rule) {
  const lines = [];
  lines.push(`Trigger: ${rule.trigger_table || '-'} → ${rule.target_table || '-'}`);
  lines.push(rule.is_batch ? 'Batch mapper: one transaction group at a time.' : 'Row mapper: one event at a time.');
  if (rule.source_table && rule.source_table !== rule.trigger_table) {
    lines.push(`Reads source rows from ${rule.source_table}.`);
  }
  if (rule.allow_chain_trigger) lines.push('Consumes chain-created events (cycle-checked at config load).');
  if (rule.allow_map_metadata_upsert) lines.push('May register metadata only for its own target map before cells are written.');
  if (rule.allow_replace_map) lines.push('May replace a mapper-declared, validated map scope.');
  if (!chainRuleIsActive(rule)) lines.push('Disabled: this rule is not evaluated by the worker.');
  return lines.join('\n');
}

function renderChainTable() {
  chainListBody.innerHTML = '';
  const activeCount = chainData.filter(chainRuleIsActive).length;
  setSectionCount('chain-rule-count', `${activeCount}/${chainData.length}`, activeCount ? 'ok' : 'danger');

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

    const isActive = chainRuleIsActive(rule);
    const activeBadge = isActive
      ? `<span class="badge badge-success">ACTIVE</span>`
      : `<span class="badge badge-danger">DISABLED</span>`;
    const mapper = [rule.mapper_module, rule.mapper_function].filter(Boolean).join('.');
    const source = rule.trigger_table || '-';
    const target = rule.target_table || '-';
    const sourceNote = rule.source_table && rule.source_table !== source
      ? `reads ${rule.source_table}` : 'uses trigger rows';

    row.innerHTML = `
      <td><div class="chain-rule-name">${rule.name || '-'}</div><div class="chain-rule-mapper">${mapper || 'built-in mapper'}</div></td>
      <td><div class="chain-flow"><span>${source}</span><span class="chain-flow-arrow">→</span><span>${target}</span></div><div class="chain-flow-note">${sourceNote}</div></td>
      <td><div class="chain-capabilities">${chainRuleCapabilities(rule)}</div></td>
      <td><div class="chain-capabilities">${[
        rule.allow_map_metadata_upsert ? '<span class="badge badge-warning">META UPSERT</span>' : '',
        rule.allow_replace_map ? '<span class="badge badge-danger">SCOPED REPLACE</span>' : '',
        !rule.allow_map_metadata_upsert && !rule.allow_replace_map ? '<span class="badge badge-muted">UPSERT ONLY</span>' : '',
      ].join('')}</div></td>
      <td><div class="chain-state">${activeBadge}<span class="chain-state-note">${rule.allow_chain_trigger ? 'cascade allowed' : 'source-only'}</span></div></td>
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
    // 서버가 active 필드를 아직 내려주지 않는 과도기엔 활성으로 간주 (기존 동작 보존)
    const isActive = col.active !== false;

    const row = document.createElement('tr');
    row.className = `table-row ${selectedAutoUpdateScript === col.script_name ? 'active' : ''}${isActive ? '' : ' row-inactive'}`;
    row.dataset.script = col.script_name;
    row.dataset.table = col.table_name;

    const statusBadge = `<span class="badge ${
      col.last_status === 'SUCCESS' ? 'badge-success' :
      col.last_status === 'FAIL' ? 'badge-danger' :
      col.last_status === 'RUNNING' ? 'badge-warning' : 'badge-warning'
    }">${col.last_status || 'PENDING'}</span>`;

    const inactiveBadge = isActive ? '' :
      '<span class="badge badge-muted" style="margin-left: 8px; flex: none;">비활성</span>';

    row.innerHTML = `
      <td style="font-weight: bold; color: var(--color-primary);">${col.table_name}</td>
      <td style="font-weight: 500; color: var(--text); font-family: var(--font-mono); font-size: 0.85rem; word-break: break-all;">${col.script_name}${inactiveBadge}</td>
      <td style="font-family: var(--font-mono); font-size: 0.85rem; text-align: center;">${col.cron_expression}</td>
      <td style="color: var(--text-muted); font-size: 0.85rem; font-family: var(--font-mono);" title="${col.next_run || ''}">${formatTimestamp(col.next_run)}</td>
      <td style="color: var(--text-muted); font-size: 0.85rem; font-family: var(--font-mono);" title="${col.last_run || ''}">${formatTimestamp(col.last_run)}</td>
      <td style="text-align: center;">${statusBadge}</td>
      <td class="au-live" style="text-align: center;" onclick="event.stopPropagation()">
        <label class="au-switch" title="${isActive ? '클릭 → 수집기 비활성화 (스케줄 중단)' : '클릭 → 수집기 활성화 (스케줄 재개)'}">
          <input type="checkbox" class="au-active-toggle" ${isActive ? 'checked' : ''} aria-label="수집기 스케줄 활성 토글">
          <span class="au-slider"></span>
        </label>
      </td>
      <td class="au-live" style="text-align: center;" onclick="event.stopPropagation()">
        <button class="glass-btn btn-primary btn-run-now" data-table="${col.table_name}" data-script="${col.script_name}"
          style="padding: 4px 10px; font-size: 0.75rem;"
          title="${isActive ? '즉시 1회 수집 실행' : '비활성 수집기도 수동 실행은 가능합니다'}">Run Now</button>
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

    const activeToggle = row.querySelector('.au-active-toggle');
    activeToggle.addEventListener('change', () => {
      toggleCollectorActive(col, activeToggle);
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
    `;

    row.addEventListener('click', () => {
      selectEnrichmentRow(rule, missing);
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

// ── 재교정률 한 줄 (Overview 상단) ───────────────────────────
// 사람이 같은 셀을 두 번 이상 고친 비율. 낮을수록 좋다.
//
// 이 한 줄은 Overview 자동 갱신 루프에 **태우지 않는다**. 출처인 /dashboard/summary 는
// 테이블마다 count(*)를 도는 무거운 엔드포인트라(실측 ~1.5s, bonding_map 176만행 단독 0.5s)
// AUTO_REFRESH_MS 주기에 얹으면 관리 화면 전체가 그 비용을 계속 문다.
// 대신 별도 간격으로 한 번씩, 본문 렌더를 막지 않고(await 하지 않고) 갱신한다.
const RECORRECTION_MIN_INTERVAL_MS = 5 * 60 * 1000;
let recorrectionLastAt = 0;

function renderRecorrection(stat) {
  const line = byId('recorrection-line');
  const valueEl = byId('recorrection-value');
  const subEl = byId('recorrection-sub');
  if (!line || !valueEl || !subEl) return;

  if (!stat || stat.rate_pct == null) {
    valueEl.textContent = '—';
    line.dataset.tone = 'muted';
    subEl.textContent = stat && stat.unavailable_reason
      ? stat.unavailable_reason
      : `최근 ${stat ? stat.window_days : 7}일간 사람이 고친 셀 없음`;
    return;
  }

  const { rate_pct: rate, measured_cells: cells, recorrected_cells: recorr, window_days: days } = stat;
  valueEl.textContent = `${rate.toFixed(1)}%`;
  // 분모는 항상 함께 — 표본이 작으면 읽는 사람이 스스로 알아채야 한다.
  subEl.textContent =
    `최근 ${days}일 · 사람이 고친 셀 ${cells.toLocaleString()}개 중 ${recorr.toLocaleString()}개를 두 번 이상 고침`
    + (cells < 100 ? ' · 표본이 작아 추세로 읽지 말 것' : '');
  line.dataset.tone = cells < 100 ? 'muted' : (rate >= 10 ? 'danger' : (rate >= 5 ? 'warn' : ''));
}

// ── 교정 공수 한 줄 (재교정률 바로 아래) ────────────────────
// 한 교정을 끝내기까지의 상호작용 점수(키 1 · 클릭 3 · 화면이동 5). 낮을수록 좋다.
//
// 커버리지(measured_ratio)를 값과 **분리하지 않는** 이유: 이 수치는 클라이언트가 보내 줄
// 때만 쌓인다. 서버는 기록 예외를 삼키므로, 수집이 통째로 죽어도 어디에도 빨간 불이 켜지지
// 않는다 — 화면에 커버리지가 없으면 "표본이 없다"와 "계기가 죽었다"가 똑같이 대시(—)로
// 보인다. 그 구별이 전부인 이유는 기준선을 잴 창이 **한 번뿐**이기 때문이다.
function renderEffort(stat) {
  const line = byId('effort-line');
  const valueEl = byId('effort-value');
  const subEl = byId('effort-sub');
  if (!line || !valueEl || !subEl) return;

  const days = stat && stat.window_days != null ? stat.window_days : 7;
  const ratio = stat ? stat.measured_ratio : null;
  const covText = ratio == null ? '커버리지 미상' : `커버리지 ${(ratio * 100).toFixed(0)}%`;

  if (!stat || stat.avg_score == null) {
    valueEl.textContent = '—';
    // 사유가 있으면 사유를 그대로 적는다. 원인 없는 대시는 정상(표본 없음)과 장애(수집
    // 중단)를 섞어버리고, 이 계기에서 그 둘은 정반대 대응을 요구한다.
    if (!stat) {
      // 응답에 effort 필드 자체가 없다 = 구 서버이거나 계약이 어긋난 것. "교정이 없었다"고
      // 적으면 서버가 말하지 않은 것을 대신 지어내는 것이 된다.
      line.dataset.tone = 'muted';
      subEl.textContent = '서버가 이 계기를 보고하지 않음 (/dashboard/summary 응답에 effort 없음)';
    } else if (stat.unavailable_reason) {
      line.dataset.tone = 'danger';
      subEl.textContent = `집계 실패: ${stat.unavailable_reason}`;
    } else if (ratio === 0) {
      // 사람이 고친 교정은 있는데 계측된 것이 0건 = 수집 중단. 이 한 줄이 그 감지기다.
      line.dataset.tone = 'danger';
      subEl.textContent = `⚠ 최근 ${days}일 사람 교정은 있으나 계측 0건 — 수집이 끊겼는지 확인`;
    } else {
      line.dataset.tone = 'muted';
      subEl.textContent = `최근 ${days}일간 사람이 고친 교정 없음`;
    }
    return;
  }

  const { avg_score: score, tx_count: txs, session_count: sessions } = stat;
  valueEl.textContent = `${score.toFixed(1)}점`;
  const lowCoverage = ratio != null && ratio < 0.5;
  subEl.textContent =
    `최근 ${days}일 · 세션 ${(sessions || 0).toLocaleString()}개 평균 · 교정 ${(txs || 0).toLocaleString()}건 계측(${covText})`
    + (ratio == null ? ' · 커버리지를 알 수 없어 대표값으로 읽지 말 것'
       : lowCoverage ? ' · 커버리지가 낮아 대표값으로 읽지 말 것' : '');
  line.dataset.tone = (ratio == null || lowCoverage) ? 'warn' : '';
}

// 두 줄(재교정률 · 교정 공수)은 같은 /dashboard/summary 응답에서 나온다 — 요청은 한 번이고,
// 위의 스로틀이 두 줄을 함께 덮는다.
async function refreshCoreValueLines(force = false) {
  const now = Date.now();
  if (!force && now - recorrectionLastAt < RECORRECTION_MIN_INTERVAL_MS) return;
  recorrectionLastAt = now;
  try {
    const res = await adminFetch(`${API_BASE}/dashboard/summary`);
    if (!res.ok) throw new Error(`dashboard summary ${res.status}`);
    const data = await res.json();
    renderRecorrection(data.recorrection || null);
    // `effort` 자체가 없으면(구 서버) 사유를 지어내지 않는다 — 서버가 안 준 것과 서버가
    // "집계 실패"라고 말한 것은 다른 상태다.
    renderEffort(data.effort || null);
  } catch (e) {
    // 보조 지표다 — 실패해도 Overview 본문 흐름을 방해하지 않는다.
    renderRecorrection({ rate_pct: null, window_days: 7, unavailable_reason: '조회 실패' });
    renderEffort({ avg_score: null, window_days: 7, unavailable_reason: '조회 실패' });
  }
}

// ── 설정 반영 한 줄 (Overview 상단, 세 번째 줄) — F9 ─────────
//
// 「내 config가 먹었는가」에 답하는 자리. `POST /admin/reload-configs`는 캐시를 갈아끼우고
// **아무것도 반환하지 않는** 쓰기 전용 버튼이었고, 그 공백이 실제 결함을 숨기고 있었다:
// `candidate_for` 선언 없이 `auto_confirm: true`를 켜면 규칙은 경고 한 줄만 남기고 조용히
// 비활성이 된다(라이브가 그 상태였다). `GET /admin/config/resolve`가 그 사실을 문장으로
// 돌려주고, 이 절이 그것을 화면에 옮긴다.
//
// 🔴 이 파일은 「효과 없음」을 스스로 판정하지 않는다. 서버가 사유를 명명하고 사람이 읽을
//    문장을 만들며, 여기서는 `detail`을 **그대로** 렌더한다. 사유별로 문장을 짓기 시작하면
//    U6에서 6종을 삭제한 하드코딩 사본 계급이 그대로 재발한다. 렌더 규칙과 그 채점은
//    `config_resolve_view.js` + `contracts/config_resolve_report/client_harness.mjs`.
//
// 이 조회는 **DB 질의 0건**(설정 파일만 읽는다)이라 재교정률 두 줄과 달리 비싸지 않다.
// 그래도 30초 자동 갱신에 매번 태울 이유는 없어서 1분 스로틀을 둔다. 설정이 바뀌는
// 유일한 계기(Reload Configs)에서는 force로 즉시 다시 읽는다.
const CONFIG_RESOLVE_MIN_INTERVAL_MS = 60 * 1000;
// Stamped only after a SUCCESSFUL read (see below) - a failed attempt must not buy silence.
let configResolveLastAt = 0;
// The token generation the last attempt ran under. When it moves, the token was replaced, and
// that is a changed cause rather than a timer tick: the next refresh is let through.
let configResolveTokenGeneration = 0;
let configResolveView = null;
let configResolveRaw = '';
// 문제가 있을 때 클릭 없이 보이게 하되 **한 번만** — 운영자가 접은 것을 자동 갱신이
// 30초마다 다시 펴면 그 펼침은 곧 무시당한다.
let configResolveAutoOpened = false;
// 드라이런 결과는 규칙 이름으로 들고 있는다: 자동 갱신이 블록을 다시 그려도 방금 얻은
// 측정값이 사라지지 않아야 한다. (설정이 바뀌면 낡은 측정이므로 통째로 버린다.)
const dryRunByRule = new Map();

const cfgText = (node) => (node && typeof node.text === 'string' ? node.text : '');

function cfgEl(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text != null) el.textContent = text;
  return el;
}

function cfgChip(text, tone) {
  const el = cfgEl('span', 'cfg-chip', text);
  if (tone) el.dataset.tone = tone;
  return el;
}

function initConfigResolveLine() {
  const hint = byId('config-resolve-hint');
  if (hint) hint.textContent = CHROME.DETAIL_HINT;
}

/** What a failing response says about ITSELF, for `fetchFailureLine`.
 *
 * `isGateRejection` is the load-bearing part and it is REUSED, not re-derived: a 401 is only
 * ours if it carries `WWW-Authenticate: X-Admin-Token`, and a proxy answering the port with its
 * own `Basic realm=...` must not be reported as a bad token. That test already exists at the
 * top of this file for the same reason and a second copy of it would drift from the first.
 */
function failureFactOf(res) {
  return {
    status: res.status,
    gate: isGateRejection(res),
    server: (res.headers && res.headers.get ? res.headers.get('Server') : '') || '',
  };
}

async function refreshConfigResolve(force = false) {
  const now = Date.now();
  // A token that ARRIVED since the last attempt is a changed cause, not a timer tick. Without
  // this, the operator does exactly what the failure line told them to do and the line goes on
  // saying it for the rest of the window - which reads as "it did not work".
  const tokenChanged = adminTokenGeneration !== configResolveTokenGeneration;
  if (!force && !tokenChanged
      && now - configResolveLastAt < CONFIG_RESOLVE_MIN_INTERVAL_MS) return;
  configResolveTokenGeneration = adminTokenGeneration;
  // Stays null until a response actually arrives, which is what lets the catch below tell
  // "nothing is listening" apart from "the server answered, and the answer was 404".
  let failure = null;
  try {
    const res = await adminFetch(`${API_BASE}/admin/config/resolve`);
    failure = failureFactOf(res);
    if (!res.ok) throw new Error(`config resolve ${res.status}`);
    const raw = await res.text();
    // 여기서 시각을 찍는다 — **읽기에 성공한 뒤**. 스로틀은 성공적인 폴링이 화면을 계속
    // 다시 그리는 것을 막으려고 있는 것이고, 실패는 그 일을 하지 않았다. 실패가 시각을
    // 찍으면 실패한 시도가 침묵 1분을 사 버려서, 원인이 해소돼도 화면이 그대로다.
    configResolveLastAt = now;
    // 바뀐 게 없으면 다시 그리지 않는다. 설정은 거의 안 바뀌는데 갱신 주기는 계속 도므로,
    // 매번 다시 그리면 운영자가 펼쳐 둔 참조뷰가 읽는 도중에 접힌다.
    if (raw === configResolveRaw && configResolveView) return;
    configResolveRaw = raw;
    // 보고서가 달라졌다 = 방금 얻은 드라이런 수치는 낡은 설정에 대한 측정이다.
    dryRunByRule.clear();
    configResolveView = buildConfigResolveView(JSON.parse(raw));
    renderConfigResolve();
  } catch (e) {
    // A failed read is NOT "the config is fine" - it leaves a dash and a reason. Which reason
    // matters: a 404 is not a failure to reach the server, it is the server saying it does not
    // have this feature, and the hand that fixes that is on a different thing (restart) than
    // the one that fixes a refused connection, a rejected token, or a proxy that answered
    // instead of us. `fetchFailureLine` owns that split so the dry-run below gets it from the
    // same place.
    console.error('[ConfigResolve] resolve report fetch failed', failure, e);
    configResolveView = null;
    renderConfigResolveFailure(fetchFailureLine(failure, CHROME.FETCH_FAILED));
  }
}

// Stays quiet and muted on failure: no auto-open, no toast, no modal. Only the words change.
function renderConfigResolveFailure(text) {
  const line = byId('config-resolve-summary');
  const valueEl = byId('config-resolve-value');
  const subEl = byId('config-resolve-sub');
  const body = byId('config-resolve-body');
  if (!line || !valueEl || !subEl) return;
  valueEl.textContent = '―';
  subEl.textContent = text;
  line.dataset.tone = 'muted';
  if (body) body.textContent = '';
}

function renderConfigResolve() {
  const view = configResolveView;
  const line = byId('config-resolve-summary');
  const valueEl = byId('config-resolve-value');
  const subEl = byId('config-resolve-sub');
  const body = byId('config-resolve-body');
  if (!view || !line || !valueEl || !subEl || !body) return;

  // 헤드라인: 모집단 카운트를 **서버 어휘 그대로** 적는다. 비어 있는 모집단은 muted —
  // 0건인 rejected가 붉게 보이면 그 색은 곧 의미를 잃는다.
  valueEl.textContent = '';
  view.totals.forEach((total) => {
    valueEl.appendChild(cfgChip(`${cfgText(total.label)} ${total.count.text}`,
      total.count.value > 0 ? total.tone : 'muted'));
  });
  subEl.textContent = view.titles.map(cfgText).join(' · ');
  line.dataset.tone = view.tone;

  body.textContent = '';
  if (view.empty) {
    body.appendChild(cfgEl('div', 'cfg-detail', cfgText(view.emptyText)));
    return;
  }
  view.domains.forEach((domain) => body.appendChild(cfgDomainEl(domain)));

  const block = byId('config-resolve');
  if (block && !configResolveAutoOpened && view.tone) {
    block.open = true;
    configResolveAutoOpened = true;
  }
}

/** 「먹었는가」 보고서를 임의의 컨테이너에 그린다 — 원장 선언 편집기가 저장 응답의 `resolve`를
 *  이 함수로 그린다. **두 번째 판정기를 만들지 않기** 위해 렌더러도 하나로 둔다: 같은 보고서가
 *  두 곳에서 다르게 보이면 어느 쪽이 맞는지 화면이 대답하지 못한다. */
function renderResolveInto(container, view) {
  if (!container || !view) return;
  if (view.empty) {
    container.appendChild(cfgEl('div', 'cfg-detail', cfgText(view.emptyText)));
    return;
  }
  view.domains.forEach((domain) => container.appendChild(cfgDomainEl(domain)));
}

function cfgDomainEl(domain) {
  const card = cfgEl('article', 'cfg-domain');
  card.appendChild(cfgEl('div', 'cfg-domain-title', cfgText(domain.title)));

  if (domain.sources.length) {
    const group = cfgEl('div');
    group.appendChild(cfgEl('div', 'cfg-group-label', cfgText(domain.sourcesLabel)));
    domain.sources.forEach((src) => {
      const row = cfgEl('div', 'cfg-row');
      if (src.tone) row.dataset.tone = src.tone;
      const head = cfgEl('div', 'cfg-row-head');
      head.appendChild(cfgEl('span', 'cfg-subject', cfgText(src.key)));
      head.appendChild(cfgEl('span', 'cfg-path', cfgText(src.path)));
      row.appendChild(head);
      row.appendChild(cfgEl('div', 'cfg-detail', cfgText(src.detail)));
      group.appendChild(row);
    });
    card.appendChild(group);
  }

  if (domain.settings.length) {
    const group = cfgEl('div');
    group.appendChild(cfgEl('div', 'cfg-group-label', cfgText(domain.settingsLabel)));
    domain.settings.forEach((setting) => {
      const row = cfgEl('div', 'cfg-row');
      const head = cfgEl('div', 'cfg-row-head');
      head.appendChild(cfgEl('span', 'cfg-subject', cfgText(setting.key)));
      head.appendChild(cfgEl('span', 'cfg-jsonval', `= ${cfgText(setting.value)}`));
      head.appendChild(cfgChip(cfgText(setting.origin), 'muted'));
      if (setting.declared) {
        head.appendChild(cfgEl('span', 'cfg-path',
          `${cfgText(setting.declaredLabel)} ${cfgText(setting.declared)}`));
      }
      row.appendChild(head);
      row.appendChild(cfgEl('div', 'cfg-detail', cfgText(setting.detail)));
      row.appendChild(cfgEl('div', 'cfg-path', cfgText(setting.path)));
      group.appendChild(row);
    });
    card.appendChild(group);
  }

  domain.populations.forEach((pop) => card.appendChild(cfgPopulationEl(pop)));
  return card;
}

function cfgPopulationEl(pop) {
  const wrap = cfgEl('div', 'cfg-pop');
  const head = cfgEl('div', 'cfg-pop-head');
  head.appendChild(cfgChip(`${cfgText(pop.label)} ${pop.count.text}`,
    pop.count.value > 0 ? pop.tone : 'muted'));
  wrap.appendChild(head);
  pop.entries.forEach((entry) => wrap.appendChild(cfgEntryEl(entry, pop.tone)));
  return wrap;
}

function cfgEntryEl(entry, tone) {
  const row = cfgEl('div', 'cfg-row');
  const head = cfgEl('div', 'cfg-row-head');
  if (entry.scope) head.appendChild(cfgChip(cfgText(entry.scope), 'muted'));
  if (entry.subject) head.appendChild(cfgEl('span', 'cfg-subject', cfgText(entry.subject)));
  // 사유·경고는 서버 어휘를 **데이터로** 받아 그대로 칩에 적는다. 색은 항목이 들어간
  // 모집단에서 오지 사유 단어에서 오지 않는다 — 사유별 분기는 이 계약이 금지하는 것이다.
  if (entry.reason) head.appendChild(cfgChip(cfgText(entry.reason), tone));
  entry.warnings.forEach((w) => head.appendChild(cfgChip(cfgText(w), 'warn')));
  row.appendChild(head);
  if (entry.detail) row.appendChild(cfgEl('div', 'cfg-detail', cfgText(entry.detail)));
  if (entry.views.length) row.appendChild(cfgViewsEl(entry));
  if (entry.measure) row.appendChild(cfgMeasureEl(entry.measure));
  return row;
}

function cfgViewsEl(entry) {
  const details = document.createElement('details');
  details.className = 'cfg-views';
  details.open = entry.viewsOpen;
  const summary = document.createElement('summary');
  summary.textContent = `${CHROME.VIEWS} ${entry.views.length} ▾`;
  details.appendChild(summary);
  entry.views.forEach((view) => {
    const box = cfgEl('div', 'cfg-view');
    if (view.warnings.length || view.narrow) box.dataset.tone = 'warn';
    const head = cfgEl('div', 'cfg-row-head');
    head.appendChild(cfgEl('span', 'cfg-subject', cfgText(view.label)));
    view.warnings.forEach((w) => head.appendChild(cfgChip(cfgText(w), 'warn')));
    box.appendChild(head);
    if (view.detail) box.appendChild(cfgEl('div', 'cfg-detail', cfgText(view.detail)));
    details.appendChild(box);
  });
  return details;
}

function cfgMeasureEl(rule) {
  const wrap = cfgEl('div');
  const btn = cfgEl('button', 'glass-btn cfg-btn', CHROME.MEASURE);
  btn.type = 'button';
  btn.title = CHROME.MEASURE_HINT;
  // 결과는 이 host 안에서만 교체한다 — 블록 전체를 다시 그리면 운영자가 펼쳐 둔 참조뷰가
  // 자기 클릭 때문에 접힌다.
  const host = cfgEl('div');
  btn.addEventListener('click', () => runAutoConfirmDryRun(rule, btn, host));
  wrap.appendChild(btn);
  wrap.appendChild(host);
  const cached = dryRunByRule.get(rule);
  if (cached) host.appendChild(cfgDryRunEl(cached));
  return wrap;
}

function cfgDryRunEl(cached) {
  const box = cfgEl('div', 'cfg-dryrun');
  if (!cached.ok) {
    box.appendChild(cfgEl('div', 'cfg-detail', cached.failure || CHROME.MEASURE_FAILED));
    return box;
  }
  const view = cached.view;
  if (view.reason) {
    const head = cfgEl('div', 'cfg-row-head');
    head.appendChild(cfgChip(cfgText(view.reason), 'warn'));
    box.appendChild(head);
  }
  box.appendChild(cfgEl('div', 'cfg-detail', cfgText(view.detail)));
  if (view.refused.length) {
    const line = cfgEl('div', 'cfg-dryrun-refused');
    line.appendChild(cfgEl('span', 'cfg-group-label', cfgText(view.refusedLabel)));
    view.refused.forEach((item) => {
      line.appendChild(cfgChip(`${cfgText(item.word)} ${item.count.text}`, 'muted'));
    });
    box.appendChild(line);
  }
  return box;
}

// 읽기 전용 계기다 — `apply`는 이 라우트에 존재하지 않고, 서버가 끝에서 구조적으로
// rollback한다. 그래서 확인 대화상자 없이 클릭 한 번이다(「읽기 무마찰」).
// 다만 큐를 걷는 분석 질의라 자동으로는 절대 돌리지 않는다: 운영자가 물어볼 때만 센다.
async function runAutoConfirmDryRun(rule, btn, host) {
  const label = btn.textContent;
  btn.disabled = true;
  btn.textContent = CHROME.MEASURING;
  // Same states as the report above, for the same reason: this route landed in the same commit,
  // so an old process 404s here too, and the same proxy answers the same port. One classifier,
  // not two.
  let failure = null;
  try {
    const res = await adminFetch(
      `${API_BASE}/admin/enrichment/auto-confirm/dry-run?rule=${encodeURIComponent(rule)}`);
    failure = failureFactOf(res);
    if (!res.ok) throw new Error(`dry-run ${res.status}`);
    dryRunByRule.set(rule, { ok: true, view: buildDryRunView(await res.json()) });
  } catch (e) {
    console.error('[ConfigResolve] auto-confirm dry-run failed', failure, e);
    dryRunByRule.set(rule, {
      ok: false, view: null, failure: fetchFailureLine(failure, CHROME.MEASURE_FAILED),
    });
  } finally {
    btn.disabled = false;
    btn.textContent = label;
    host.textContent = '';
    host.appendChild(cfgDryRunEl(dryRunByRule.get(rule)));
  }
}

// ── 소급 적용 한 줄 (Overview 상단, 네 번째 줄) — [Queue 25] ──────────────────────────
//
// 「규칙보다 오래된 데이터에 그 규칙을 지금 적용하면 몇 건인가, 그리고 실행」. 다섯 연산 전부
// 이미 CLI로 존재했고 어드민에는 **화면이 없었다**. 새 페이지도 새 탭도 새 모달도 만들지
// 않는다 — F9의 「설정 반영」 줄이 자리잡은 그 방식 그대로 Overview 상단의 한 줄이고, 펼치면
// 제자리에서 열린다.
//
// 🔴 이 절은 「몇 건인가」의 뜻을 스스로 판정하지 않는다. 다섯 중 넷은 요청 경로에서 정확한
//    수를 낼 수 없고(그게 곧 드라이런 전수 스캔이다), 서버가 그 사실을 `count_kind`(exact /
//    sample / upper_bound)와 **라벨 자체**("회수할 셀 (최대)")와 `detail` 문장 셋으로 말한다.
//    그래서 렌더 규칙은 기계적이다: **숫자는 서버가 붙인 라벨과 함께가 아니면 그리지 않는다.**
//    판정과 채점은 `retroactive_view.js` + `client2/tests/retroactive_view_harness.mjs`.
//
// 목록 조회(`/admin/retroactive/operations`)는 **DB 질의 0건**(설정만 읽는다)이고 서버 재시작
// 전까지 바뀌지 않는다. 그래서 30초 폴링에 태우지 않는다 — 페이지당 한 번, 그리고 **원인이
// 바뀌었을 때** 다시 읽는다(토큰이 새로 들어왔다 · Reload Configs를 눌렀다). 타이머보다 이쪽이
// 싸고, 「왜 지금 다시 읽었나」에 답할 수 있다.
let retroactiveView = null;
let retroactiveLoaded = false;
let retroactiveInFlight = false;
// The token generation the last attempt ran under. A token that ARRIVED since then is a changed
// cause, not a retry — without this the operator does what the failure line told them to do and
// the line goes on saying it. (Same reason `configResolveTokenGeneration` exists.)
let retroactiveTokenGeneration = -1;
// 목록 원문. F9의 `configResolveRaw`와 **같은 이유**로 들고 있는다(`:1648` 참조): 내용이 그대로면
// 다시 그리지 않는다. 안 그러면 운영자가 펼쳐 둔 「버튼이 덮지 않는 것」이 읽는 도중에 접힌다.
let retroactiveRaw = '';
// 🔴 연산당 **레코드 하나**. 카운트·파라미터·큐 응답·진행 중 여부가 전부 여기 있고, 화면은
//    이 레코드의 순수 함수다. 앞선 판본은 카운트를 연산 id로만 캐시하고 파라미터를 **다른 맵**에
//    뒀으며 「실행 중」은 DOM 노드에만 있었다 — 그래서 ① 측정한 파라미터와 보낼 파라미터가 어긋나도
//    아무도 몰랐고 ② 버튼 줄을 다시 만드는 코드 경로가 진행 중이라는 사실을 잊었다. 두 결함은
//    같은 실수의 두 얼굴이라 치료도 하나다: **상태는 레코드에만 있고 렌더는 그것을 읽기만 한다.**
//    판정 함수는 `retroactive_view.js`의 `resolveCount`/`buildActionsView`이고 node에서 채점된다.
const retroStateByOp = new Map();

function retroState(op) {
  let state = retroStateByOp.get(op);
  if (!state) {
    state = { params: {}, count: null, run: null, runFailure: null, busy: null, cliOpen: false };
    retroStateByOp.set(op, state);
  }
  return state;
}

// ═══════════════════════════════════════════════════════════════════════════
// 도는 것들 — 목록 하나, 줄마다 [무엇] [진행] [ × ]. 소유자 1순위 화면.
//
// 🔴 이 화면의 존재 이유는 «하나만 끊기»입니다. 백필이 서버를 무겁게 만드는데 백필만 못 꺼서
//    서버를 통째로 내리는 일이 운영에서 잦았습니다. × 는 프로세스를 죽이지 «않고» 값만
//    세우며, 작업이 다음 배치 «전»에 그것을 보고 스스로 멈춥니다.
//
// 🔴 판정은 전부 `retroactive_view.buildRunsView` 에 있습니다. 여기서는 «그린 것»만 합니다 --
//    무엇이 막대를 받는지, 어디에 × 가 붙는지를 이 파일이 다시 정하면 두 곳이 어긋납니다.
// ═══════════════════════════════════════════════════════════════════════════

let runsView = null;
let runsInFlight = false;

/** 두 출처를 «같이» 읽습니다. 한쪽이 실패해도 다른 쪽은 그립니다 -- 부분이 전부보다 낫습니다. */
async function refreshRunning() {
  if (runsInFlight) return;
  runsInFlight = true;
  try {
    const [runsRes, ingestRes] = await Promise.all([
      adminFetch(`${API_BASE}/admin/retroactive/runs?limit=50`).catch(() => null),
      adminFetch(`${API_BASE}/admin/file-ingestion/active`).catch(() => null),
    ]);
    const runs = runsRes && runsRes.ok ? (await runsRes.json().catch(() => null)) : null;
    const ingest = ingestRes && ingestRes.ok ? (await ingestRes.json().catch(() => null)) : null;
    // 🔴 «못 읽은 것»과 «없는 것»을 가릅니다. 실패를 빈 배열로 접으면 화면이
    //    「도는 작업 없음」이라고 «거짓»을 말합니다.
    const failed = [];
    if (!runs) failed.push('실행 목록');
    if (!ingest) failed.push('파일 인제션');
    const cancellable = {};
    for (const op of (retroactiveView && retroactiveView.operations) || []) {
      if (op && op.op) cancellable[op.op] = op.cancellable === true;
    }
    runsView = buildRunsView(
      { runs: (runs && runs.runs) || [], ingestions: (ingest && ingest.data) || [] },
      Date.now(), cancellable);
    runsView.failedSources = failed;
    renderRunning();
  } finally {
    runsInFlight = false;
  }
}

// 🔴 이 목록은 «지금»을 말하는 화면이라 스스로 따라가야 합니다. 사람이 새로고침을 눌러야
//    안다면 「지금 뭐가 도나」에 답하는 것이 아닙니다 (소유자 관측: 「새로고침 해야하네」).
//    박자는 «목록이 정합니다» -- 도는 것이 있으면 촘촘히, 없으면 느리게. 조용할 때 촘촘히
//    두드리면 아무 일도 없는 서버를 하루 종일 깨우는 것이 됩니다.
const RUNS_POLL_BUSY_MS = 3000;
const RUNS_POLL_IDLE_MS = 30000;
let runsTimer = null;

function scheduleRunsPoll() {
  if (runsTimer) clearTimeout(runsTimer);
  // «빈 목록»과 «아직 안 읽음»은 다릅니다. 안 읽었으면 빨리 한 번 더 갑니다.
  const busy = !runsView || !runsView.empty;
  runsTimer = setTimeout(() => {
    // 숨은 탭·다른 탭에서는 쉽니다 -- 옆의 공용 자동 갱신이 지키는 것과 같은 규칙입니다.
    // 그리고 다시 돌아왔을 때를 위해 «타이머는 계속 돕니다».
    const p = (!document.hidden && currentTab === 'overview')
      ? refreshRunning() : Promise.resolve();
    p.then(scheduleRunsPoll, scheduleRunsPoll);
  }, busy ? RUNS_POLL_BUSY_MS : RUNS_POLL_IDLE_MS);
}

/** × — 값만 세웁니다. 목록에서 «안 지웁니다». */
async function requestRunCancel(runId) {
  try {
    const res = await adminFetch(`${API_BASE}/admin/retroactive/runs/${encodeURIComponent(runId)}/cancel`,
      { method: 'POST' });
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      showToast((body && body.detail) || `cancel refused (${res.status})`, 'error');
      return;
    }
  } catch (e) {
    showToast('could not send the cancel request', 'error');
    return;
  }
  // 서버가 값을 세웠고, 실제로 멈추는 것은 그다음입니다. 목록을 다시 읽어 «멈추는 중»을 보입니다.
  refreshRunning();
}

function renderRunning() {
  const valueEl = byId('running-value');
  const subEl = byId('running-sub');
  const body = byId('running-body');
  if (!valueEl || !subEl || !body) return;
  const view = runsView;
  body.textContent = '';
  if (!view) {
    valueEl.textContent = '—';
    subEl.textContent = '…';
    return;
  }
  valueEl.textContent = String(view.rows.length);
  // 접힌 줄이 「열지 말지」를 정합니다: 몇 개가 도는지와 가장 오래된 것.
  // 🔴 「가장 오래」는 «최댓값»입니다. 마지막 줄을 집으면 목록 순서가 바뀌는 날 조용히
  //    다른 수를 말합니다 — 접힌 줄만 보고 끊을지 정하는 화면이라 그 한 수가 판단입니다.
  const oldestMinutes = view.rows.reduce((max, r) => {
    const m = r.progress && typeof r.progress.elapsedMinutes === 'number'
      ? r.progress.elapsedMinutes : null;
    return m === null ? max : (max === null ? m : Math.max(max, m));
  }, null);
  const oldest = oldestMinutes === null ? null : `${oldestMinutes}m`;
  subEl.textContent = view.empty ? 'idle' : (oldest ? `oldest ${oldest}` : '');
  if (view.failedSources && view.failedSources.length) {
    // 🔴 못 읽은 출처를 «이름 대어» 말합니다. 안 말하면 그만큼이 「없는 것」이 됩니다.
    subEl.textContent += ` · ${view.failedSources.join(', ')} unreachable`;
  }
  if (view.empty) return;

  const list = document.createElement('div');
  list.className = 'running-list';
  for (const row of view.rows) {
    const line = document.createElement('div');
    line.className = 'running-row' + (row.moving ? '' : ' is-waiting');
    line.setAttribute('data-run-id', row.id);

    const what = document.createElement('span');
    what.className = 'running-what';
    what.textContent = cfgText(row.what) + (cfgText(row.detail) ? ` · ${cfgText(row.detail)}` : '');
    line.appendChild(what);

    const prog = document.createElement('span');
    prog.className = 'running-progress';
    if (row.progress.mode === 'bar') {
      const bar = document.createElement('span');
      bar.className = 'running-bar';
      const fill = document.createElement('span');
      fill.className = 'running-bar__fill';
      fill.style.width = `${row.progress.percent}%`;
      bar.appendChild(fill);
      prog.appendChild(bar);
      const pct = document.createElement('span');
      pct.className = 'running-pct';
      pct.textContent = `${row.progress.percent}%`;
      prog.appendChild(pct);
    } else {
      // 🔴 폭을 «주장하지 않는» 막대. 전체를 모르는데 찬 막대를 그리면 그 폭이 곧 거짓말이고,
      //    글자로 「처리 N」이라 적으면 소유자 지적대로 막대가 있는데 말을 또 하는 것입니다.
      //    움직임이 「도는 중」을, 수가 「어디까지」를 말합니다.
      const bar = document.createElement('span');
      // 🔴 움직임이 「도는 중」입니다. 기다리는 줄은 «빈 궤도»로 앉습니다 — 글자는 안 늘립니다.
      bar.className = 'running-bar is-unknown' + (row.moving ? '' : ' is-waiting');
      const fill = document.createElement('span');
      fill.className = 'running-bar__fill';
      bar.appendChild(fill);
      prog.appendChild(bar);
      const t = document.createElement('span');
      t.className = 'running-pct';
      t.textContent = row.progress.text;
      prog.appendChild(t);
    }
    if (row.progress.elapsed) {
      const el = document.createElement('span');
      el.className = 'running-elapsed';
      el.textContent = ` · ${row.progress.elapsed}`;
      prog.appendChild(el);
    }
    line.appendChild(prog);

    const act = document.createElement('span');
    act.className = 'running-act';
    if (row.stopping) {
      // 🔴 말 대신 «색»입니다 (소유자 지시). 줄이 흐려지고 막대가 멈춥니다 — 그리고 «남습니다».
      line.className += ' is-stopping';
      line.title = 'stopping after the current batch';
    } else if (row.cancel) {
      const btn = document.createElement('button');
      btn.className = 'glass-btn running-x';
      btn.textContent = '×';
      btn.title = 'stop this one — the server keeps running';
      btn.addEventListener('click', () => requestRunCancel(row.id));
      act.appendChild(btn);
    }
    // 🔴 못 멈추는 것에는 «아무것도» 안 그립니다. 죽은 × 는 화면이 하는 거짓말입니다.
    line.appendChild(act);
    list.appendChild(line);
  }
  body.appendChild(list);
}

function initRetroactiveLine() {
  const hint = byId('retroactive-hint');
  if (hint) hint.textContent = RETRO_CHROME.HINT;
  adoptRescopeHandoff();
}

/**
 * 그리드가 «고른 범위»를 넘겨 놓았으면 그것을 받아 이 블록의 파라미터로 앉힙니다.
 *
 * 🔴 «한 번만» 먹습니다 (`takeRescopeHandoff` 가 읽으면서 지웁니다). 남겨 두면 다음에
 *    어드민을 열었을 때 «지금 고른 적 없는» 범위가 채워져 있고, 운영자는 그것을 자기가
 *    고른 것으로 읽습니다 -- 이 화면이 반복해서 막아 온 부류의 «쓰기» 판입니다.
 * 🔴 여기서 드라이런을 «자동으로 돌리지 않습니다». 채워 넣기까지가 넘김이고, 미리보기를
 *    누르는 것은 사람입니다 (지시서: 드라이런이 «먼저», 그리고 그건 사람의 한 걸음).
 */
function adoptRescopeHandoff() {
  const got = takeRescopeHandoff();
  if (!got) return;
  const state = retroState(got.op);
  const params = got.params || {};
  Object.keys(params).forEach((key) => {
    const value = params[key];
    if (value !== undefined && value !== null && value !== '') state.params[key] = String(value);
  });
  // 넘어온 것은 «파라미터»이지 측정이 아닙니다. 들고 있던 수가 있으면 그건 다른 범위의
  // 것이므로 버립니다 -- 안 버리면 새 범위 옆에 옛 수가 붙어 있게 됩니다.
  state.count = null;
  const block = byId('retroactive');
  if (block) block.open = true;
  refreshRetroactiveOperations(true);
}

/** 이 연산이 **선언한** 파라미터만, 비어 있지 않은 것만. 판정은 뷰 모델이 소유한다 —
 *  서버가 재시작하며 파라미터를 개명·삭제하면 맵에 남은 옛 키가 400을 부르는데, 그 필드는
 *  이미 화면에 없어서 운영자는 이유를 알 수 없다. 선언에서 유도하면 그 경로가 사라진다. */
function retroParamEntries(op, opView) {
  return paramEntries(retroState(op), opView);
}

async function refreshRetroactiveOperations(force = false) {
  const tokenChanged = adminTokenGeneration !== retroactiveTokenGeneration;
  if (retroactiveInFlight) return;
  if (!force && !tokenChanged && retroactiveLoaded) return;
  retroactiveInFlight = true;
  retroactiveTokenGeneration = adminTokenGeneration;
  let failure = null;
  try {
    const res = await adminFetch(`${API_BASE}/admin/retroactive/operations`);
    failure = failureFactOf(res);
    if (!res.ok) throw new Error(`retroactive operations ${res.status}`);
    const raw = await res.text();
    retroactiveLoaded = true;
    // 목록이 **달라졌을 때만** 다시 그린다 — F9가 `:1648`에서 같은 이유로 하는 것과 같은 가드다
    // (그쪽 주석: 「매번 다시 그리면 운영자가 펼쳐 둔 참조뷰가 읽는 도중에 접힌다」). 이 목록은
    // 서버 재시작 전까지 바뀌지 않으므로 사실상 매번 같은 원문이 온다.
    if (raw === retroactiveRaw && retroactiveView) return;
    retroactiveRaw = raw;
    retroactiveView = buildOperationsView(JSON.parse(raw));
    // 🔴 진행 목록의 × 는 이 목록의 `cancellable` 로만 그려집니다. 이것이 «늦게» 오므로
    //    도착하면 다시 그립니다 — 안 그러면 첫 로드에서 × 가 영원히 안 보입니다.
    refreshRunning();
    // 목록이 실제로 달라졌다 = 설정이 바뀌었다 = 들고 있던 측정은 낡은 선언에 대한 것이다.
    // 큐 응답(run_id)은 남긴다: 그것은 선언이 아니라 **일어난 일**이고, 설정이 바뀌었다고
    // 방금 큐에 들어간 실행이 없던 일이 되지 않는다.
    retroStateByOp.forEach((state) => { state.count = null; });
    renderRetroactive();
  } catch (e) {
    // 실패는 「연산이 없다」가 아니다 — 대시와 사유를 남긴다. 어느 사유인지가 중요하고,
    // 그 가름(응답 없음 / 404=구버전 프로세스 / 게이트 거부 / 앞단이 대신 응답)은 F9가 이미
    // 소유하고 있다. 여기서 두 번째 분류기를 쓰지 않는다.
    console.error('[Retroactive] operations fetch failed', failure, e);
    retroactiveView = null;
    retroactiveLoaded = false;
    renderRetroactiveFailure(fetchFailureLine(failure, RETRO_CHROME.LIST_FAILED));
  } finally {
    retroactiveInFlight = false;
  }
}

// 실패해도 조용하다: 자동 펼침 없음, 토스트 없음, 모달 없음. 문구만 바뀐다.
function renderRetroactiveFailure(text) {
  const line = byId('retroactive-summary');
  const valueEl = byId('retroactive-value');
  const subEl = byId('retroactive-sub');
  const body = byId('retroactive-body');
  if (!line || !valueEl || !subEl) return;
  valueEl.textContent = '―';
  subEl.textContent = text;
  line.dataset.tone = 'muted';
  if (body) body.textContent = '';
}

function renderRetroactive() {
  const view = retroactiveView;
  const valueEl = byId('retroactive-value');
  const subEl = byId('retroactive-sub');
  const body = byId('retroactive-body');
  if (!view || !valueEl || !subEl || !body) return;

  valueEl.textContent = '';
  valueEl.appendChild(cfgChip(`${cfgText(view.operationsLabel)} ${view.total.text}`,
    view.total.value > 0 ? '' : 'muted'));
  // 헤드라인은 연산 이름을 그대로 나열한다. 이 줄에는 요약할 「상태」가 없다 — 도구함에
  // 없는 판정을 지어내는 것이 목록보다 나쁘다.
  subEl.textContent = view.titles.map(cfgText).join(' · ');

  body.textContent = '';
  if (view.empty) {
    body.appendChild(cfgEl('div', 'cfg-detail', cfgText(view.emptyText)));
    return;
  }
  view.operations.forEach((op) => body.appendChild(retroOperationEl(op)));
}

/** 한 연산 카드만 제자리에서 갈아 끼운다.
 *
 * 🔴 비동기 핸들러가 **DOM 참조를 await 너머로 들고 가지 않게** 하는 것이 요점이다. 앞선 판본은
 *    `btn`과 `host`를 클로저에 담아 갔고, 그 사이 목록이 다시 그려지면 둘 다 문서에서 떨어져
 *    나간 노드가 됐다 — 큐 응답이 아무 데도 안 붙고 화면의 버튼은 활성으로 되살아났다.
 *    이제 핸들러는 레코드만 고치고 이 함수를 부른다. 화면은 레코드에서 다시 유도된다.
 */
function renderRetroOperation(opId) {
  const view = retroactiveView;
  const body = byId('retroactive-body');
  if (!view || !body) return;
  const opView = view.operations.find((o) => o.op === opId);
  const card = body.querySelector(`article.retro-op[data-op="${CSS.escape(opId)}"]`);
  if (!opView || !card) return;
  card.parentElement.replaceChild(retroOperationEl(opView), card);
}

function retroOperationEl(op) {
  const card = cfgEl('article', 'cfg-domain retro-op');
  card.dataset.op = op.op;
  if (op.tone) card.dataset.tone = op.tone;

  const head = cfgEl('div', 'cfg-row-head');
  head.appendChild(cfgEl('span', 'cfg-domain-title', cfgText(op.label)));
  card.appendChild(head);
  // 「무엇이 빠져 있는가」 — 이 문장이 없으면 버튼 다섯 개는 지시 대상 없는 동사 다섯 개다.
  if (op.whatIsMissing) card.appendChild(cfgEl('div', 'cfg-detail', cfgText(op.whatIsMissing)));

  // 이 연산이 무엇을 지우고 어떤 단위로 커밋되는가 — 둘 다 서버 문자열이고 그대로 적는다.
  // 다섯 중 하나(고아 스윕)만 삭제이고 중단 시 통째로 롤백된다. 확인 문구 하나로 다섯을
  // 덮으면 그 하나가 틀리므로, 사실은 각 행이 자기 것을 들고 있는다.
  if (op.deletes) card.appendChild(retroFactEl(op.deletesLabel, op.deletes, 'danger'));
  if (op.commit) card.appendChild(retroFactEl(op.commitLabel, op.commit, ''));

  if (op.params.length) card.appendChild(retroParamsEl(op));

  card.appendChild(retroActionsEl(op));

  // 결과 영역은 레코드에서 유도된다 — 두 버튼이 같은 host를 서로 지우던 자리가 없어졌다.
  // 측정과 큐 응답은 **다른 사실**이라 둘 다 남는다: 하나는 증거고 하나는 일어난 일이다.
  const state = retroState(op.op);
  const resolved = resolveCount(state, op);
  if (resolved.count) card.appendChild(retroCountEl(resolved.count, resolved.stale));
  if (state.run) card.appendChild(retroQueuedEl(state.run));
  if (state.runFailure) card.appendChild(cfgEl('div', 'cfg-dryrun', state.runFailure));

  card.appendChild(retroCliEl(op));
  return card;
}

function retroFactEl(label, value, tone) {
  const row = cfgEl('div', 'retro-fact');
  row.appendChild(cfgChip(cfgText(label), tone || 'muted'));
  row.appendChild(cfgEl('span', 'cfg-path', cfgText(value)));
  return row;
}

function retroParamsEl(op) {
  const wrap = cfgEl('div', 'retro-params');
  wrap.appendChild(cfgEl('div', 'cfg-group-label', cfgText(op.paramsLabel)));
  const state = retroState(op.op);
  op.params.forEach((param) => {
    const field = cfgEl('label', 'retro-field');
    const name = cfgEl('span', 'cfg-subject', cfgText(param.name));
    field.appendChild(name);
    if (param.required) field.appendChild(cfgChip(cfgText(param.requiredLabel), 'muted'));
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'retro-input';
    input.dataset.param = param.key;
    input.value = state.params[param.key] || '';
    input.addEventListener('input', () => {
      const wasStale = resolveCount(state, op).stale;
      state.params[param.key] = input.value;
      // 카드를 통째로 다시 그리면 타이핑 중에 포커스가 날아가므로, **측정의 유효성이 실제로
      // 뒤집힌 타이핑에서만** 다시 그린다 — 한 글자 고쳤다 되돌리면 측정은 다시 유효해지고
      // 그 전이도 화면에 나와야 한다. 판정은 `resolveCount` 하나가 한다.
      if (!state.count || resolveCount(state, op).stale === wasStale) return;
      const caret = input.selectionStart;
      renderRetroOperation(op.op);
      retroFocusParam(op.op, param.key, caret);
    });
    field.appendChild(input);
    // 서버가 준 help는 **입력칸 안(placeholder)이 아니라 아래 줄**에 둔다. placeholder는
    // 폭에 잘리고 타이핑을 시작하면 사라진다 — 「자르지 말고 줄을 하나 더 써라」.
    // 없으면 비워 둔다: 여기서 지어내면 그 순간 클라가 파라미터의 뜻을 자기가 정한다.
    if (param.help) field.appendChild(cfgEl('span', 'retro-help cfg-path', cfgText(param.help)));
    wrap.appendChild(field);
  });
  return wrap;
}

/** 재렌더 뒤 커서를 원래 칸으로 돌려놓는다. 입력칸은 `data-param`으로 자기를 밝힌다. */
function retroFocusParam(opId, paramKey, caret) {
  const target = document.querySelector(
    `article.retro-op[data-op="${CSS.escape(opId)}"] input[data-param="${CSS.escape(paramKey)}"]`);
  if (!target) return;
  target.focus();
  try { target.setSelectionRange(caret, caret); } catch (e) { /* not a text input */ }
}

/** 🔴 두 버튼의 상태는 **레코드에서 유도**된다. 이 함수는 그 결과를 DOM에 옮기기만 한다 —
 *  판정(진행 중인가 · 낡은 측정인가 · 거부 상태인가)은 전부 `buildActionsView`에 있고 node에서
 *  채점된다. 어떤 재렌더 경로를 타든 같은 레코드에서 같은 답이 나오므로, 다시 그리는 코드가
 *  「실행 중이었다」를 잊을 방법이 없다. */
function retroActionsEl(op) {
  const wrap = cfgEl('div', 'retro-actions');
  const actions = buildActionsView(op, retroState(op.op));

  const countBtn = cfgEl('button', 'glass-btn cfg-btn', cfgText(actions.count.label));
  countBtn.type = 'button';
  countBtn.disabled = actions.count.disabled;
  countBtn.addEventListener('click', () => runRetroactiveCount(op));
  wrap.appendChild(countBtn);

  const runBtn = cfgEl('button', 'glass-btn btn-primary cfg-btn', cfgText(actions.run.label));
  runBtn.type = 'button';
  runBtn.disabled = actions.run.disabled;
  // 서버가 `blocked_reason`을 카운트와 **따로** 실어 보내는 이유가 이것이다 — 눌러 보고 워커
  // 로그에서 거절을 발견하는 것이 아니라, 누르기 전에 알 수 있어야 한다.
  if (actions.run.blocked) {
    runBtn.title = `${cfgText(actions.run.blockedLabel)}: ${cfgText(actions.run.blocked)}`;
  }
  runBtn.addEventListener('click', () => runRetroactiveRun(op));
  wrap.appendChild(runBtn);
  return wrap;
}

function retroCliEl(op) {
  const state = retroState(op.op);
  const details = document.createElement('details');
  details.className = 'cfg-views';
  // 펼침 상태도 레코드에 있다 — 카드를 다시 그린다고 운영자가 열어 둔 것이 접히면 안 된다.
  details.open = state.cliOpen;
  details.addEventListener('toggle', () => { state.cliOpen = details.open; });
  const summary = document.createElement('summary');
  summary.textContent = `${cfgText(op.cliOnlyLabel)} ${op.cliOnly.length} ▾`;
  details.appendChild(summary);
  const box = cfgEl('div', 'cfg-view');
  const head = cfgEl('div', 'cfg-row-head');
  head.appendChild(cfgChip(cfgText(op.cliLabel), 'muted'));
  head.appendChild(cfgEl('span', 'cfg-path', cfgText(op.cli)));
  box.appendChild(head);
  // 버튼은 각 연산의 흔한 형태만 덮는다. 나머지가 무엇인지는 서버가 목록으로 말해 주고,
  // 그것을 감추면 이 다섯 줄이 전부인 것처럼 읽힌다.
  op.cliOnly.forEach((item) => box.appendChild(cfgEl('div', 'cfg-detail', cfgText(item))));
  details.appendChild(box);
  return details;
}

function retroCountEl(cached, stale) {
  const box = cfgEl('div', 'cfg-dryrun');
  if (!cached.ok) {
    box.appendChild(cfgEl('div', 'cfg-detail', cached.failure || RETRO_CHROME.COUNT_FAILED));
    return box;
  }
  const view = cached.view;
  // 🔴 입력이 바뀌었으면 이 상자는 **지금 보낼 요청의 것이 아니다.** 지우지 않고 그렇게 적는다 —
  // 「inv를 재보니 594였고 지금은 lot_alias를 묻고 있다」가 운영자가 잃지 말아야 할 맥락이다.
  // 확인 대화상자에는 애초에 실리지 않는다(`buildConfirmLines`가 구조적으로 막는다).
  if (stale) {
    box.dataset.tone = 'stale';
    box.appendChild(cfgEl('div', 'cfg-detail retro-stale', RETRO_CHROME.STALE));
  } else if (view.truncated) {
    box.dataset.tone = 'warn';
  }

  const head = cfgEl('div', 'retro-count-head');
  // 🔴 숫자는 서버 라벨과 한 쌍으로만 나온다. 라벨이 없으면 숫자도 없다 — 맨숫자는 「답」으로
  // 읽히고, 다섯 중 넷에서 그것은 답이 아니다(`detail` 문장 안에 여전히 들어 있다).
  // 그리고 이 두 가지가 **쓰기 결정이 딛고 있는 사실**이므로 주변 산문보다 작아서는 안 된다.
  if (view.affectedLabel && view.affected) {
    head.appendChild(cfgEl('span', 'retro-count-label', cfgText(view.affectedLabel)));
    head.appendChild(cfgEl('span', 'retro-count-value', view.affected.text));
  }
  // 「이 수는 어떤 종류의 수인가」 — 서버 어휘 그대로. 색은 종류에서 오지 값에서 오지 않는다.
  if (view.kind) {
    const kindChip = cfgChip(cfgText(view.kind), view.kindTone);
    kindChip.classList.add('retro-kind');
    kindChip.title = cfgText(view.kindLabel);
    head.appendChild(kindChip);
  }
  // 표본이 예산까지 찼는가 — 테두리 색 하나에만 맡기지 않는다. 색은 확인 대화상자에 못 간다.
  if (view.truncatedLabel && view.truncatedValue) {
    head.appendChild(cfgEl('span', 'cfg-path', cfgText(view.truncatedLabel)));
    head.appendChild(cfgEl('span', 'cfg-jsonval', cfgText(view.truncatedValue)));
  }
  if (view.blocked) {
    head.appendChild(cfgChip(cfgText(view.blockedLabel), 'danger'));
    head.appendChild(cfgChip(cfgText(view.blocked), 'danger'));
  }
  if (head.childNodes.length) box.appendChild(head);

  if (view.detail) box.appendChild(cfgEl('div', 'cfg-detail', cfgText(view.detail)));
  if (view.why) box.appendChild(cfgEl('div', 'cfg-detail', cfgText(view.why)));
  // 서버가 **라벨을 붙여 준** 두 번째 숫자만 나온다(R1의 회수 후보처럼). `affected`에 더하지
  // 않는 것이 핵심이다 — 더하면 「쓰기 연산」의 수에 「절대 쓰지 않는 것」의 수가 섞인다.
  // 쌍마다 자기 상자를 갖는다: 구분자 없는 한 줄에서는 값이 다음 라벨에 붙어 읽힌다.
  if (view.extras.length) {
    const line = cfgEl('div', 'retro-extras');
    view.extras.forEach((extra) => {
      const pairEl = cfgEl('span', 'retro-extra');
      pairEl.appendChild(cfgEl('span', 'cfg-path', cfgText(extra.label)));
      pairEl.appendChild(cfgChip(extra.count.text, 'muted'));
      line.appendChild(pairEl);
    });
    box.appendChild(line);
  }
  return box;
}

function retroQueuedEl(view) {
  const box = cfgEl('div', 'cfg-dryrun');
  box.dataset.tone = 'ok';
  const head = cfgEl('div', 'cfg-row-head');
  head.appendChild(cfgChip(cfgText(view.queuedLabel), 'ok'));
  if (view.statusWord) head.appendChild(cfgChip(cfgText(view.statusWord), 'muted'));
  head.appendChild(cfgEl('span', 'cfg-path',
    `${cfgText(view.runIdLabel)} ${cfgText(view.runId)}`));
  box.appendChild(head);
  if (view.label) box.appendChild(cfgEl('div', 'cfg-detail', cfgText(view.label)));
  // 🔴 **무엇이** 큐에 들어갔는지 — 서버가 되돌려준 echo다. 이것이 없으면 이 상자는 「실행됐다」만
  // 말하고 「무엇이」를 말하지 않는다. 파라미터가 어긋난 채 확정된 실행을 사후에 알아볼 수 있는
  // 유일한 자리이기도 하다.
  if (view.params.length) {
    const line = cfgEl('div', 'retro-extras');
    line.appendChild(cfgEl('span', 'cfg-group-label', cfgText(view.paramsLabel)));
    view.params.forEach((param) => {
      const pairEl = cfgEl('span', 'retro-extra');
      pairEl.appendChild(cfgEl('span', 'cfg-subject', cfgText(param.name)));
      pairEl.appendChild(cfgEl('span', 'cfg-jsonval',
        param.values.map(cfgText).join(', ')));
      line.appendChild(pairEl);
    });
    box.appendChild(line);
  }
  return box;
}

/** 실패 응답의 문장은 **서버 것을 먼저 쓴다.**
 *
 * 400 거절(알 수 없는 연산·파라미터 누락·보호된 소스 회수 시도·계산 불가)에는 서버가 이유를
 * 문장으로 담아 보낸다. 그것을 버리고 「조회 실패」로 뭉개면 운영자를 로그로 돌려보내는 것이다.
 * 반대로 404·401/403·무응답은 서버가 자기에 대해 말할 수 없는 상태라 클라의 다섯 상수가 답이다
 * — 그 가름은 `fetchFailureText`가 이미 소유하고 있으므로, 서버 문장을 **fallback으로 넘기는
 * 것만으로** 두 규칙이 하나의 분류기 안에서 만난다. 새 분기를 만들지 않는다.
 */
async function retroFailureLine(res, failure, fallback) {
  let detail = '';
  try {
    const body = await res.json();
    if (body && typeof body.detail === 'string') detail = body.detail;
  } catch (e) { /* 본문 없는 실패 응답 — 클라 상수로 답한다 */ }
  return fetchFailureLine(failure, detail || fallback);
}

// 읽기 전용 계기다 — `apply`류 파라미터는 이 라우트에 존재하지 않고 서버가 구조적으로
// rollback한다. 그래서 확인 없이 클릭 한 번(「읽기 무마찰」). 다만 다섯 중 셋은 이 수를 얻는
// 것이 곧 표본 드라이런이라 자동으로는 절대 돌리지 않는다: 운영자가 물어볼 때만 센다.
async function runRetroactiveCount(op) {
  const state = retroState(op.op);
  if (state.busy) return;
  const entries = retroParamEntries(op.op, op);
  // 🔴 이 측정이 **어느 파라미터의 것인지**를 결과와 함께 적어 둔다. 이것이 없으면 측정은
  // 연산에 대한 사실인 척하고, `_count_chain_replay`의 `detail`은 규칙 이름을 말하지 않으므로
  // 어긋난 채로 확인 대화상자까지 따라가도 화면 어디에도 표가 나지 않는다.
  const measuredKey = paramsKey(entries);
  state.busy = 'count';
  renderRetroOperation(op.op);
  let failure = null;
  try {
    const query = entries
      .map((e) => `${encodeURIComponent(e.key)}=${encodeURIComponent(e.value)}`).join('&');
    const res = await adminFetch(
      `${API_BASE}/admin/retroactive/${encodeURIComponent(op.op)}/count${query ? `?${query}` : ''}`);
    failure = failureFactOf(res);
    if (!res.ok) {
      state.count = {
        ok: false, view: null, paramsKey: measuredKey,
        failure: await retroFailureLine(res, failure, RETRO_CHROME.COUNT_FAILED),
      };
    } else {
      state.count = { ok: true, view: buildCountView(await res.json()), paramsKey: measuredKey };
    }
  } catch (e) {
    console.error('[Retroactive] count failed', op.op, failure, e);
    state.count = {
      ok: false, view: null, paramsKey: measuredKey,
      failure: fetchFailureLine(failure, RETRO_CHROME.COUNT_FAILED),
    };
  } finally {
    state.busy = null;
    // 화면은 레코드에서 다시 유도된다. 여기서 DOM을 손으로 깁지 않으므로, 이 경로가 실행 버튼의
    // 진행 중 상태를 되살릴 방법이 없다 — 그것이 두 번째 아웃박스 행을 만들던 자리였다.
    renderRetroOperation(op.op);
  }
}

// 🔴 쓰기 촉발이다. 확인은 **정확히 한 번**이고 마법사는 없다.
// 대화상자에 들어가는 사실은 전부 서버 문자열(라벨 · 무엇을 지우는가 · 커밋 단위 · 방금 센
// 문장)이고, 운영자가 타이핑한 파라미터가 그대로 되읽힌다. 클라가 짓는 문장은 마지막 질문
// 한 줄뿐이다 — 위험을 클라가 요약하기 시작하면 다섯 중 넷과 다른 하나를 같은 말로 덮게 된다.
async function runRetroactiveRun(op) {
  const state = retroState(op.op);
  // 🔴 확인창을 **열기 전에** 막는다. 더블클릭이나 Enter 키 반복이 대화상자를 닫자마자 두 번째
  // 클릭을 흘려보내는 경로가 여기 하나뿐이고, 브라우저의 모달 동작에 기대는 것은 계약이 아니다.
  if (state.busy) return;
  const params = retroParamEntries(op.op, op);
  // 레코드를 통째로 넘긴다. 뷰 모델이 「이 측정이 이 파라미터의 것인가」를 스스로 판정하므로,
  // 어긋난 측정을 실어 보낼 수 있는 인자 모양 자체가 존재하지 않는다.
  const lines = buildConfirmLines(op, state, params);
  // 🔴 플래그를 **확인창을 열기 전에** 세운다. 「confirm()이 탭 모달이라 두 번째 클릭은 페이지에
  // 닿지 않는다」는 참이지만 그건 **브라우저 동작**이지 이 코드가 보장하는 성질이 아니다(키 반복이
  // 대화상자를 닫으면서 클릭을 흘리는 경로가 실제로 있다). 여기서 세우면 모달 의미론에 기대지
  // 않고도 두 번째 진입이 위 `if (state.busy) return;`에 걸린다. 취소하면 되돌린다.
  state.busy = 'run';
  if (!confirm(lines.map((node) => node.text).join('\n'))) {
    state.busy = null;
    return;
  }
  renderRetroOperation(op.op);
  let failure = null;
  let failureText = null;
  try {
    const body = {};
    params.forEach((entry) => { body[entry.key] = entry.value; });
    const res = await adminFetch(`${API_BASE}/admin/retroactive/${encodeURIComponent(op.op)}/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ params: body }),
    });
    failure = failureFactOf(res);
    if (!res.ok) {
      failureText = await retroFailureLine(res, failure, RETRO_CHROME.RUN_FAILED);
      // 503(토큰 미설정으로 이 라우트가 닫혀 있음)은 `adminFetch`가 **이미** 서버 본문을
      // 토스트로 띄운다. 여기서 또 띄우면 같은 문장이 두 번 뜬다(실측 확인). 두 번째 분류기를
      // 만들지 않고 그 하나에 양보한다 — 줄은 남긴다, 토스트는 사라지고 줄은 남으니까.
      if (res.status !== 503) showToast(failureText, 'error', { ttl: 12000 });
    } else {
      // 큐 응답은 **레코드에 남는다.** 앞선 판본은 이것만 DOM에 직접 붙여서, 다음 재렌더가
      // run_id를 영구히 지웠다 — 토스트는 이미 사라진 뒤였고, 무언가 실행됐다는 증거가 화면에서
      // 완전히 없어졌다. 카운트와 파라미터는 살아남는데 그것만 못 살아남을 이유가 없다.
      state.run = buildRunView(await res.json());
      // 방금 큐에 들어간 것을 «지금» 보여 줍니다 -- 다음 박자를 기다리면 그 사이에
      // 운영자는 안 걸린 줄 알고 한 번 더 누릅니다.
      refreshRunning().then(scheduleRunsPoll, scheduleRunsPoll);
      showToast(`${cfgText(state.run.queuedLabel)} — `
        + `${cfgText(state.run.runIdLabel)} ${cfgText(state.run.runId)}`, 'success');
    }
  } catch (e) {
    console.error('[Retroactive] run request failed', op.op, failure, e);
    failureText = fetchFailureLine(failure, RETRO_CHROME.RUN_FAILED);
    showToast(failureText, 'error', { ttl: 12000 });
  } finally {
    state.busy = null;
    // 실패 문장도 레코드에 있다 — 토스트는 사라지고 줄은 남아야 하며, 남는 것은 재렌더를
    // 견뎌야 한다. 성공하면 지운다: 지난 실패가 이번 큐 응답 옆에 남아 있으면 안 된다.
    state.runFailure = failureText;
    renderRetroOperation(op.op);
  }
}

// ── Overview 탭 (헬스 스트립 확장판 — 첫 화면) ─────────────

async function fetchOverview(isStale) {
  // 의도적으로 await 하지 않는다(위 주석 참조): 본문 카드가 이 요청을 기다리지 않는다.
  refreshCoreValueLines();
  // 같은 이유로 await 하지 않는다. 이쪽은 DB를 건드리지 않아 값싸지만, 본문 렌더가
  // 설정 파일 읽기를 기다릴 이유도 없다.
  refreshConfigResolve();
  // 같은 이유로 await 하지 않는다. 목록은 설정만 읽고(DB 질의 0건) 페이지당 한 번만
  // 읽히므로 30초 폴링에 아무 비용도 더하지 않는다 — 카운트는 여기서 돌지 않는다.
  refreshRetroactiveOperations();

  const [failedRes, wsRes, outboxRes, rulesRes, mappersRes, autoRes, activeRes] = await Promise.all([
    adminFetch(`${API_BASE}/admin/file-ingestion/failed?page=1&limit=100`),
    adminFetch(`${API_BASE}/admin/file-ingestion/workspaces`),
    adminFetch(`${API_BASE}/admin/outbox/failed?page=1&limit=3`),
    adminFetch(`${API_BASE}/admin/chain/rules`),
    adminFetch(`${API_BASE}/admin/mappers/list`),
    adminFetch(`${API_BASE}/admin/auto-update/status`),
    adminFetch(`${API_BASE}/admin/file-ingestion/active`) // [Heavy Lane P1] 진행 중 인제션
  ].map(p => p.catch(() => null)));

  const jsonOf = async (r) => (r && r.ok) ? r.json().catch(() => null) : null;
  const [failed, ws, outbox, rules, mappers, auto, active] = await Promise.all(
    [failedRes, wsRes, outboxRes, rulesRes, mappersRes, autoRes, activeRes].map(jsonOf)
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

  renderOverview({ failed, ws, outbox, rules, mappers, auto, enrich, active });
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

function renderOverview({ failed, ws, outbox, rules, mappers, auto, enrich, active }) {
  overviewGrid.innerHTML = '';

  // ① File Ingestion 카드 (+ [Heavy Lane P1] 진행 중 인제션 = 재기동 경고)
  {
    const total = failed ? (failed.total || 0) : null;
    const wsCount = ws ? (ws.data || []).length : null;
    const activeItems = active ? (active.data || []) : [];
    let status = total == null ? 'loading' : (total > 0 ? 'danger' : 'ok');
    if (status === 'ok' && activeItems.length > 0) status = 'warn';
    // 진행 중 항목을 이벤트 라인 상단에 노출 (실패 라인보다 앞) — 재기동 전 확인 유도
    const activeEvents = activeItems.slice(0, 2).map(i => ({
      time: null,
      text: `${i.filename} → ${i.table_name} (${i.progress || 0}%${i.lane === 'heavy' ? ' · heavy' : ''}) — 재기동 시 처음부터 재처리`,
      badge: i.status === 'QUEUED' ? '대기' : '진행 중',
      badgeTone: 'warn'
    }));
    const events = activeEvents.concat(
      (failed ? (failed.data || []).slice(0, 3 - activeEvents.length) : []).map(l => ({
        time: formatTimestamp(l.created_at),
        text: `${l.filename} → ${l.table_name}`,
        badge: 'FAIL',
        badgeTone: 'danger'
      }))
    );
    overviewGrid.appendChild(ovCard({
      status,
      title: 'File Ingestion',
      metrics: [
        { value: total == null ? '—' : total, label: '인제션 실패', tone: total > 0 ? 'danger' : (total === 0 ? 'ok' : null) },
        { value: activeItems.length, label: '진행 중', tone: activeItems.length > 0 ? 'warn' : null },
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
    const activeCount = collectors ? collectors.filter(c => c.active !== false).length : null;
    let linked = null;
    if (collectors && failed) {
      const autoTables = new Set(collectors.map(c => c.table_name));
      linked = (failed.data || []).filter(l => autoTables.has(l.table_name)).length;
    }
    let status = 'loading';
    if (collectors) {
      if (failCount > 0) status = 'danger';
      else if (linked > 0) status = 'warn';
      else if (collectors.length > 0 && activeCount === 0) status = 'warn'; // 전부 비활성 = 수집 전면 중단
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
        {
          value: collectors == null ? '—' : `${activeCount}/${collectors.length}`,
          label: '활성 수집기',
          tone: collectors && collectors.length > 0 && activeCount === 0 ? 'warn'
            : (collectors && activeCount < collectors.length ? null
              : (collectors ? 'ok' : null))
        },
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
      onOpen: () => switchTab('enrichment')
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
    const res = await adminFetch(`${API_BASE}/admin/auto-update/run-now`, {
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

// API Call: 수집기 스케줄 활성/비활성 토글
// 계약: POST /admin/auto-update/toggle {script: "<workspace>/<script.py>", active: bool}
//       → {status: "success", script, active} · 404(미존재)/400(형식 오류)
async function toggleCollectorActive(col, inputEl) {
  const nextActive = inputEl.checked;
  inputEl.disabled = true; // 응답 전 연타 방지 (성공 시 재렌더로 새 토글로 교체됨)
  try {
    const res = await adminFetch(`${API_BASE}/admin/auto-update/toggle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        script: `${col.table_name}/${col.script_name}`,
        active: nextActive
      })
    });
    if (!res.ok) {
      let msg = res.status === 404 ? '해당 수집기를 찾을 수 없습니다' : `요청 거부 (HTTP ${res.status})`;
      try {
        const err = await res.json();
        if (err && err.detail) msg = typeof err.detail === 'string' ? err.detail : msg;
      } catch (e) { /* 본문 없는 에러 응답은 기본 메시지 유지 */ }
      throw new Error(msg);
    }
    const r = await res.json();
    const applied = (r && r.active !== undefined) ? !!r.active : nextActive;

    // fetchSeq 가드 준수: 보관해 둔 옛 배열/행을 되살리지 않고, "현재" autoUpdateData에서
    // 키로 다시 찾아 갱신한다 (토글 요청 중 fetchData가 배열을 교체했어도 안전).
    const target = autoUpdateData.find(c =>
      c.script_name === col.script_name && c.table_name === col.table_name);
    if (target) target.active = applied;
    col.active = applied;
    if (currentTab === 'autoupdate') renderAutoUpdateTable();

    showToast(applied
      ? `▶️ [${col.script_name}] 수집기 스케줄이 활성화되었습니다.`
      : `⏸️ [${col.script_name}] 수집기 스케줄이 비활성화되었습니다. (Run Now 수동 실행은 계속 가능)`,
      'success');
  } catch (err) {
    console.error('Failed to toggle collector active', col.table_name, col.script_name, err);
    // 실패 시 원복: 스위치를 이전 상태로 되돌리고 다시 조작 가능하게
    inputEl.checked = !nextActive;
    inputEl.disabled = false;
    showToast(`❌ 수집기 활성 상태 변경 실패 — ${err.message || '네트워크 오류'}`, 'error');
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
  tracebackSeverity.textContent = chainRuleIsActive(rule) ? 'ACTIVE' : 'DISABLED';
  tracebackSeverity.className = chainRuleIsActive(rule) ? 'badge badge-success' : 'badge badge-danger';
  tracebackSeverity.style.display = 'inline';
  payloadTitle.innerHTML = `Raw Chain Ingestion Rule Configuration
    <button id="inline-edit-mapper-btn" class="glass-btn btn-primary" style="padding: 2px 8px; font-size: 0.75rem; margin-left: 10px;">🛠️ Edit Mapper Code</button>`;

  tracebackViewer.textContent = chainRuleNarrative(rule) +
    (rule.description ? `\n\n${rule.description}` : '');
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
        ? `대상 필드가 비어 있는 행이 ${missing}건 있습니다 — 메인 그리드에서 직접 입력.`
        : '대상 필드가 모두 채워져 있습니다.'
  ];
  tracebackViewer.innerHTML = `<div style="color: var(--text-muted); line-height: 1.7; white-space: pre;">${lines.join('\n')}</div>` +
    `<div style="margin-top: 12px; color: var(--text-dim); line-height: 1.6;">✏️ 규칙 편집(read-only): 서버 <span style="font-family: var(--font-mono); color: var(--text);">server/config/enrichment_rules.json</span> 수기 편집 후 Reload Configs &amp; Code로 반영.<br>규칙 CRUD UI는 온보딩 위저드(대안 단계)로 이관.</div>`;

  payloadTitle.textContent = 'Rule Configuration (read-only)';
  payloadViewer.textContent = JSON.stringify(rule, null, 2);
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
    const res = await adminFetch(`${API_BASE}/admin/outbox/retry-failed?transaction_id=${txId}`, {
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
    const res = await adminFetch(`${API_BASE}/admin/file-ingestion/retry-failed?log_id=${logId}`, {
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
      const res = await adminFetch(`${API_BASE}/admin/outbox/retry-failed`, {
        method: 'POST'
      });
      if (!res.ok) throw new Error('Retry-all API returned error status');
      const result = await res.json();

      showToast(`🔄 ${result.message || '모든 실패 체인 트랜잭션이 초기화되었습니다.'}`, 'success');
      outboxPage = 1;
    } else {
      const res = await adminFetch(`${API_BASE}/admin/file-ingestion/retry-failed`, {
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

// API Call: Reload system configurations and python modules cache
async function reloadSystemConfigs() {
  try {
    const res = await adminFetch(`${API_BASE}/admin/reload-configs`, {
      method: 'POST'
    });
    if (!res.ok) throw new Error('Reload configs API returned error status');
    showToast('🚀 시스템 설정 및 파이썬 코드가 성공적으로 핫-리로드되었습니다.', 'success');
    enrichmentStatusCache = null; // 규칙이 바뀌었을 수 있음
    scriptsListCache = null;      // 스크립트 목록도 최신화
    // [F9] 이 버튼이 **처음으로 무언가를 돌려주는** 자리. 리로드는 선언의 효과가 바뀌는
    // 유일한 계기이므로 스로틀을 무시하고 다시 읽는다. 자동 펼침 1회 권한도 되살린다 —
    // 방금 누른 리로드의 결과가 접혀 있으면 의미가 없다. (보고서가 실제로 달라졌을 때만
    // 다시 그려지고, 그때 낡은 드라이런 측정값도 함께 버려진다.)
    configResolveAutoOpened = false;
    refreshConfigResolve(true);
    // 소급 적용 목록도 규칙 이름(체인·Enrichment)에서 나오므로 리로드가 그 유일한 변경
    // 계기다. force로 스로틀을 건너뛰되, **버리는 판정은 내용 비교가 한다** — 목록이 실제로
    // 달라졌을 때만 측정을 버리고 다시 그린다. 눌렀는데 아무것도 안 바뀌었으면 화면도 그대로다.
    refreshRetroactiveOperations(true);
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
      const res = await adminFetch(`${API_BASE}/admin/scripts/list`);
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

    const res = await adminFetch(`${API_BASE}/admin/scripts/code?path=${encodeURIComponent(path)}`);
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
    const res = await adminFetch(`${API_BASE}/admin/scripts/code`, {
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
  // Missing count: composed by `queueQuery` (enrichment_queue.js), the SAME named server
  // queue predicate the worklist itself is fetched with, re-asked per rule with limit=1 so
  // only `total` is read. The shared predicate is what makes this number and the worklist's
  // count the same population; a filter dict spelled here instead would be AND-ed by the
  // consumer into "every target blank" and undercount any rule with two targets.
  const perRule = [];
  let totalMissing = 0;
  for (const rule of rules) {
    // 큐 조건을 만들 수 없으면 missing = null(조회 실패 표기). 조건을 떼고 물으면
    // 파생 테이블 전체 행 수가 「결손」이라는 이름으로 카드에 실린다.
    const queue = queueQuery(rule);
    let missing = null;
    if (queue) {
      try {
        const url = `${API_BASE}/tables/${encodeURIComponent(rule.derived_table)}/data` +
          `?skip=0&limit=1&${queue}`;
        const cres = await fetch(url);
        if (cres.ok) {
          const cr = await cres.json();
          missing = cr.total || 0;
          totalMissing += missing;
        }
      } catch (e) { /* missing = null → 카드/배지에서 조회 실패 표기 */ }
    }
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
    const res = await adminFetch(`${API_BASE}/admin/file-ingestion/failed?page=1&limit=100`);
    if (res.ok) {
      const r = await res.json();
      failedTotal = r.total || 0;
      failedLogs = r.data || [];
    }
  } catch (e) { /* 아래에서 조회 실패 카드 처리 */ }

  // [Heavy Lane P1] 진행 중 인제션 — 재기동 경고 (조회 실패는 무음, 카운트 0 취급)
  let activeCount = 0;
  let activeHeavy = 0;
  try {
    const res = await adminFetch(`${API_BASE}/admin/file-ingestion/active`);
    if (res.ok) {
      const r = await res.json();
      activeCount = r.total || 0;
      activeHeavy = (r.data || []).filter(i => i.lane === 'heavy').length;
    }
  } catch (e) { /* 보조 정보 — 무음 */ }
  const activeSub = activeCount > 0
    ? `⚠️ 인제션 진행 중 ${activeCount}건${activeHeavy ? ` (heavy ${activeHeavy})` : ''} — 재기동 시 처음부터 재처리`
    : null;

  if (failedTotal === null) {
    setHealthCard('file', 'loading', '—', activeSub || '상태 조회 실패');
  } else if (failedTotal > 0) {
    setHealthCard('file', 'danger', `실패 ${failedTotal}건`,
      activeSub || '클릭 → File 탭 실패 필터로 이동');
  } else if (activeCount > 0) {
    setHealthCard('file', 'warn', `인제션 진행 중 ${activeCount}건`, activeSub);
  } else {
    setHealthCard('file', 'ok', '실패 0건', '파일 인제션 정상');
  }

  try {
    const res = await adminFetch(`${API_BASE}/admin/auto-update/status`);
    if (!res.ok) throw new Error('auto-update status fetch failed');
    const r = await res.json();
    const collectors = r.data || [];
    if (collectors.length === 0) {
      setHealthCard('auto', 'loading', '수집기 없음', '등록된 auto-update 설정 없음');
      return;
    }

    const failCount = collectors.filter(c => c.last_status === 'FAIL').length;
    const activeCount = collectors.filter(c => c.active !== false).length;
    // 감사 §1.2 실증 시나리오 연계: 수집기는 SUCCESS인데 산출물 파일 인제션이
    // 실패 중인 경우를 카드에서 즉시 노출 (auto-update 대상 테이블 ∩ 최근 실패 로그)
    const autoTables = new Set(collectors.map(c => c.table_name));
    const linkedFails = failedLogs.filter(l => autoTables.has(l.table_name)).length;
    const linkedSuffix = (failedTotal !== null && failedTotal > failedLogs.length) ? '+' : '';

    let status = 'ok';
    if (failCount > 0) status = 'danger';
    else if (linkedFails > 0) status = 'warn';
    else if (activeCount === 0) status = 'warn'; // 전 수집기 비활성 = 자동 수집 전면 중단

    const main = failCount > 0
      ? `수집기 실패 ${failCount}/${collectors.length}`
      : `수집기 ${collectors.length}개 중 ${activeCount} 활성`;
    const sub = linkedFails > 0
      ? `산출물 인제션 실패 ${linkedFails}${linkedSuffix}건`
      : (activeCount === 0
        ? '모든 수집기가 비활성 상태입니다'
        : `최근 실행 ${formatTimestamp(latestLastRun(collectors))}`);
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
    const res = await adminFetch(`${API_BASE}/admin/outbox/failed?page=1&limit=1`);
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
