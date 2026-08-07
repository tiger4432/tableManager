// ============================================================
// Enrichment Queue Page Orchestrator (Phase 1 conveyor + Phase 2 reference views)
// - admin.js / map_editor.js 선례: 자체 모듈 지역 상태 (state.js/dom.js/api.js 미임포트)
// - 재사용: config.js / utils.js / AG-Grid Community
// - 계약(확정): GET /enrichment/rules
//   { "rules": [ { name, source_table, derived_table, decision_key[],
//                  target_fields[], list_columns[], reference_views:[{label}] } ] }
// - 워크리스트: GET /tables/{derived}/data + blank 필터 청크 페칭 (전량 로드 금지)
//   → 정렬·필터는 **브라우저에서** 한다(2026-08-05 제품소유자 재정). 그래서 화면은 자기가
//     보고 있는 것이 부분집합인지 말해야 한다 — `worklistCountText` 참조.
// - 저장: PUT /tables/{derived}/data/updates (source_name='user' → priority 0)
// - 참조뷰(계약 확정): GET /enrichment/rules/{rule}/references/{i}?params=<JSON {decision_key: value}>
//   → {label, columns[], rows[[]]} (서버 LIMIT 강제 · 404: 규칙/인덱스 미존재)
//   → 400: 비허용 키, 또는 **이 뷰가 묶는 판단키가 비어 물을 수 없음**. 어느 뷰가 답할 수
//     있는지는 서버가 판정하고 사유 문장도 서버가 만든다. 클라는 묻고, 온 것을 렌더한다.
// ============================================================
import { createGrid, ModuleRegistry, AllCommunityModule } from 'ag-grid-community';
import 'ag-grid-community/styles/ag-grid.css';
import 'ag-grid-community/styles/ag-theme-quartz.css';
import './tokens.css';
import { API_BASE, CURRENT_USER, pageLimit } from './config.js';
import { showToast } from './utils.js';
import { initTheme } from './theme.js';
// The queue is asked for BY NAME, and this module is the only place that spells
// the request. See its header for why the filter-dict spelling had to go.
import { queueQuery, QUEUE_SCOPE_BLANK_KEY } from './enrichment_queue.js';
// [V1 effort instrument] The ONE collector (effort_meter.js). This file keeps no counters
// of its own. The conveyor is a correction write path, so it must be measured — it is
// plausibly the LOWEST-effort correction surface in the product, and unmeasured we cannot
// support that claim with anything.
import {
  ROUTES, startSession, installGlobalListeners, installNavLinkCounting, countNav,
  snapshot as effortSnapshot, commitIfRecorded as effortCommitIfRecorded
} from './effort_meter.js';

ModuleRegistry.registerModules([AllCommunityModule]);

// 컨베이어 버퍼 보충 임계치: 남은 행이 이보다 적으면 skip=0 재페치
const REFILL_THRESHOLD = 50;

// 참조뷰 로드 debounce(ms): 빠른 ↑/↓ 이동·연속 Enter 시 요청 폭주 방지
const REF_DEBOUNCE_MS = 250;

// ── 지역 상태 (싱글턴) ─────────────────────────────────────
const S = {
  rules: [],
  rule: null,
  sessionToken: null,   // 규칙 전환/새로고침마다 재발급되는 세션 가드 UUID
  gridApi: null,
  totalBlank: 0,        // 서버 기준 잔여 결손 행 수 (저장 시 로컬 감산)
  // 진행률 분모 = 파생 테이블 전체 **행** 수. 「키 수」가 아니다: 값은 무필터
  // `result.total`(행 카운트)이고, 잔여도 이제 같은 테이블의 행 카운트라 둘이 같은
  // 모집단이다. 종전 라벨('유니크 키 수' · `N / M keys`)은 `composite_key_source ==
  // decision_key`인 현재 두 규칙에서만 우연히 참이었고 로더는 진부분집합도 허용한다
  // (그 경우 판단키 2개가 1행으로 접힌다) — 코드가 뒷받침하지 못하는 주장이었다.
  totalAll: null,
  // 「판단키 없음 N건」 = 서버 scope `blank_key`의 total 그대로. null은 「모른다」다
  // (구버전 서버는 이 술어를 만들 수 없다) — 0과 구별해서 보관한다.
  blankKeyCount: null,
  doneCount: 0,         // 이번 세션에서 채운 건수
  isFetching: false,
  exhausted: false,     // 서버에 버퍼 밖 잔여분이 없음
  saving: false,
  selectedRowId: null,

  // ── [C] 참조뷰 상태 ──
  refViews: [],         // 현재 규칙의 reference_views 메타 [{label}]
  refActiveIdx: 0,      // 활성 탭 인덱스
  refSeq: 0,            // 요청 시퀀스 가드: 최신 요청의 응답만 렌더 (stale 폐기)
  refTimer: null,       // debounce 타이머 핸들
  refCache: new Map(),  // 현재 선택 행 한정 탭 캐시: viewIdx → {columns, rows, ms}
  refCacheRowId: null,  // refCache가 유효한 row_id (행 변경 시 클리어)
  refGridApi: null,     // 참조뷰 AG-Grid (컬럼은 응답이 정하므로 뷰마다 갈아 끼운다)
  refColSignature: null,// 마지막으로 그린 컬럼 구성 — 바뀌면 정렬·필터를 버린다
  refRowCount: 0,       // 서버가 보낸 행 수 (필터 전) — 메타의 분모
  refMs: '0',           // 마지막 조회 소요 ms (필터 변경 시 재계산하지 않는다)
};

const el = (id) => document.getElementById(id);

// ── ONE grid spelling, used by BOTH panels ──────────────────────────────────────
// 워크리스트와 참조뷰는 한 화면의 두 표다. 규율이 서로 다르면 조작자가 어느 쪽에서 무엇을
// 기대할지 매번 다시 배워야 하므로, 정렬·필터 규율은 이 객체 한 곳에만 쓴다.
//
// WHY NOT IMPORT `grid.js`. That module owns the MAIN grid and imports `state.js`, `dom.js`,
// `api.js`, `timeline.js`, `clipboard.js`, `ui.js` and `value_suggest.js` — importing it here
// would drag the entire main-app module graph into this page's bundle to obtain a
// `defaultColDef`. So its CONVENTIONS are reused verbatim (`theme: 'legacy'`, floating
// filters, resizable columns, `agTextColumnFilter`) and the object is written once here
// instead of twice.
//
// TEXT FILTER ON EVERY COLUMN, DELIBERATELY. `grid.js` chooses `agNumberColumnFilter` from
// `/schema` column types. Neither panel on this page has a type source: the worklist's
// columns come from rule metadata, and the reference view's SQL is written by the operator.
// Guessing a type per panel from whichever rows happened to arrive would make the two panels
// treat the same value differently — the two-grids-behaving-differently trap this screen must
// not set. What numbers actually need is the ORDER, and `compareCells` gives them that on
// both panels.
const GRID_SORT_FILTER_DEFAULTS = {
  sortable: true,
  filter: 'agTextColumnFilter',
  floatingFilter: true,
  resizable: true,
  comparator: compareCells,
};

// 그리드 **수준** 공통 옵션 (위는 컬럼 수준). 같은 이유로 한 곳에만 쓴다.
//
// 「행 없음」과 「일치 행 없음」은 AG-Grid에서 **다른 오버레이**다. 전자는
// `suppressNoRowsOverlay`로 끌 수 있지만 후자(`NoMatchingRowsOverlayDef`)에는 억제 옵션이
// 아예 없다 — 그래서 끄는 대신 **문구를 바꾼다.** 두 표 모두 여기 한 문장을 쓰므로, 필터가
// 전부 가린 상태를 한 화면에서 두 가지 말로 알리는 일이 없다.
// 셀 복사 (2026-08-07). 조작자가 값 하나를 집어 다른 화면에 옮기는 일이 이 페이지의 상시
// 동작인데, AG-Grid는 기본적으로 셀 텍스트 선택을 막아 드래그 자체가 안 됐다.
//
// 🔴 `clipboard.js`를 쓰지 않는 이유는 위 `grid.js` 블록과 **같다, 그리고 한 겹 더 나쁘다**:
//    그 모듈은 `grid.js`·`state.js`·`dom.js`·`ui.js`를 직접 import하므로, 여기서 부르면
//    이 파일이 피하려고 통째로 다시 쓴 그 모듈 그래프가 그대로 딸려 온다. 엑셀형 **범위**
//    복사가 필요해지면 그때 그 모듈에서 순수 부분을 떼어내는 것이 순서이고, 한 셀 복사를
//    위해 그 값을 치를 이유는 없다.
// ⚠️ 그래서 이것은 브라우저 기본 복사다 — 범위 선택 복사가 아니다. AG-Grid의 범위 복사는
//    Enterprise 기능이고 이 페이지는 Community로 돈다.
const GRID_SHARED_OPTIONS = {
  theme: 'legacy',
  localeText: { noMatchingRows: '필터 결과 없음' },
  enableCellTextSelection: true,
  // 여러 셀에 걸쳐 드래그했을 때 복사 순서가 화면 순서와 같도록. 한 셀에는 무관하지만
  // 없으면 가상 스크롤이 DOM을 재배치한 순서로 붙어 나간다.
  ensureDomOrder: true,
};

// 숫자로 읽히면 숫자로, 아니면 문자열로. 빈 값은 오름차순에서 항상 뒤.
// `'10' < '9'` is the defect this exists for: both panels carry columns whose values are
// numbers stored as text (there is no `/schema` here to say otherwise), and AG-Grid's default
// comparator would order them lexically — the operator asks for the largest and gets the one
// starting with 9. Blanks sort LAST ascending because a blank is the absence of a value, not
// the smallest one; the worklist's key-less rows are exactly that case, and scattering them
// through the order is what `partitionQueueRows` exists to prevent. (AG-Grid inverts the
// result for descending, so blanks lead there — the same shape `grid.js` documents for its
// unresolved-label comparator.)
function compareCells(a, b) {
  const aBlank = a === null || a === undefined || String(a).trim() === '';
  const bBlank = b === null || b === undefined || String(b).trim() === '';
  if (aBlank || bBlank) return (aBlank && bBlank) ? 0 : (aBlank ? 1 : -1);
  const an = Number(a), bn = Number(b);
  if (!Number.isNaN(an) && !Number.isNaN(bn)) return an < bn ? -1 : (an > bn ? 1 : 0);
  const as = String(a), bs = String(b);
  return as < bs ? -1 : (as > bs ? 1 : 0);
}

// 서버 셀 계약 {value, is_overwrite, priority_source} → 표시값 (형태는 절대 변조하지 않음)
function cellVal(row, col) {
  const c = row && row.data ? row.data[col] : undefined;
  if (c && typeof c === 'object') {
    return c.value === null || c.value === undefined ? '' : c.value;
  }
  return c === null || c === undefined ? '' : c;
}

// The cell contract's `priority_source`: WHO decided this value. It is the fact the screen
// owes an operator before they overwrite anything -- "deciding again" is only a decision if
// you can see whose decision you are replacing. A cell that arrived as a bare scalar carries
// no provenance, and then this says nothing rather than inventing a writer.
function cellSource(row, col) {
  const c = row && row.data ? row.data[col] : undefined;
  if (c && typeof c === 'object' && c.priority_source) return String(c.priority_source);
  return '';
}

function newSessionToken() {
  S.sessionToken = (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}_${Math.random()}`);
  return S.sessionToken;
}

// ── 규칙 메타 로드 (미배포/규칙 없음 → 우아한 안내, 콘솔 스팸 금지) ──
async function loadRules() {
  try {
    const res = await fetch(`${API_BASE}/enrichment/rules`);
    if (!res.ok) {
      showSetupState('🚧', 'Enrichment 규칙 API가 아직 준비되지 않았습니다',
        `서버가 GET /enrichment/rules (HTTP ${res.status})를 제공하면 이 화면이 자동으로 활성화됩니다.`);
      return false;
    }
    const data = await res.json();
    S.rules = Array.isArray(data.rules) ? data.rules.filter(r => r && r.derived_table) : [];
    if (S.rules.length === 0) {
      showSetupState('🗒️', '등록된 Enrichment 규칙이 없습니다',
        '서버 enrichment_rules.json에 규칙을 등록하면 워크리스트가 표시됩니다.');
      return false;
    }
    hideSetupState();
    return true;
  } catch (e) {
    showSetupState('📡', '서버에 연결할 수 없습니다',
      'API 서버 상태를 확인한 뒤 다시 시도해 주세요.');
    return false;
  }
}

function showSetupState(icon, title, desc) {
  el('setup-icon').textContent = icon;
  el('setup-title').textContent = title;
  el('setup-desc').textContent = desc;
  el('setup-overlay').style.display = 'flex';
}

function hideSetupState() {
  el('setup-overlay').style.display = 'none';
}

function populateRuleSelect() {
  const sel = el('rule-select');
  sel.innerHTML = '';
  S.rules.forEach(rule => {
    const opt = document.createElement('option');
    opt.value = rule.name;
    opt.textContent = rule.name;
    sel.appendChild(opt);
  });
}

// ── 규칙 선택 → 그리드 재구성 + 초기 청크 로드 ─────────────
function selectRule(rule) {
  S.rule = rule;
  newSessionToken();
  S.totalBlank = 0;
  S.totalAll = null;
  S.blankKeyCount = null;
  S.isFetching = false;
  S.exhausted = false;
  S.selectedRowId = null;

  el('rule-select').value = rule.name;
  el('conveyor-meta').textContent = `${rule.derived_table}`;
  initReferencePanel(rule);
  showConveyorEmpty();
  rebuildGrid(rule);
  updateHeaderStats();

  fetchWorklist(true);
  fetchTotalAll();
  fetchBlankKeyTotal();
}

function buildColumnDefs(rule) {
  const decisionCols = (rule.decision_key || []).map(col => ({
    field: col,
    headerName: `🔑 ${col.toUpperCase()}`,
    valueGetter: (p) => cellVal(p.data, col),
    cellStyle: { color: 'var(--color-primary)', fontFamily: 'var(--font-mono)' },
  }));
  const listCols = (rule.list_columns || []).map(col => ({
    field: col,
    headerName: col.toUpperCase(),
    valueGetter: (p) => cellVal(p.data, col),
  }));
  return [...decisionCols, ...listCols];
}

function rebuildGrid(rule) {
  if (S.gridApi) {
    S.gridApi.destroy();
    S.gridApi = null;
  }
  const gridOptions = {
    ...GRID_SHARED_OPTIONS,
    columnDefs: buildColumnDefs(rule),
    rowData: [],
    getRowId: (params) => String(params.data.row_id),
    rowSelection: 'single',
    suppressCellFocus: true,
    animateRows: true,
    // 「행 없음」은 이 패널의 오버레이가 말한다 (`updateWorklistOverlay`) — 필터가 가린
    // 것인지 큐가 빈 것인지를 구별해서. AG-Grid 기본 오버레이를 켜 두면 그 위에 영어
    // 'No Matching Rows'가 겹쳐 두 문장이 같은 자리에서 다른 말을 한다.
    suppressNoRowsOverlay: true,
    defaultColDef: {
      flex: 1,
      minWidth: 110,
      editable: false,       // 입력은 [B] 컨베이어에서만 (인라인 편집과 흐름 충돌 방지)
      // 정렬·필터는 참조뷰와 **같은 규율**을 쓴다 (한 화면, 한 철자).
      ...GRID_SORT_FILTER_DEFAULTS,
    },
    onSelectionChanged: () => {
      if (!S.gridApi) return;
      const selected = S.gridApi.getSelectedNodes();
      if (selected.length > 0) renderDetail(selected[0].data);
    },
    // 정렬·필터가 바뀌면 화면이 몇 건을 보이고 있는지도 바뀐다. 세는 곳이 한 곳이므로
    // 두 사건 모두 같은 갱신기를 부른다 — 필터가 전부 가린 상태를 「큐가 비었다」로
    // 읽지 않게 하는 것이 `updateWorklistOverlay`의 일이다.
    onFilterChanged: () => { refreshWorklistCounts(); },
    onSortChanged: () => { refreshWorklistCounts(); },
  };
  S.gridApi = createGrid(el('worklist-grid'), gridOptions);
}

// 이 행이 판단키를 전부 갖췄는가 = 사람이 근거를 조회할 수 있는가.
// 참조뷰는 판단키 **값으로** 조회되므로 빈 값은 근거를 찾지 못한다.
function hasDecisionKeys(row, rule) {
  return (rule.decision_key || []).every(col => String(cellVal(row, col)).trim() !== '');
}

// 컨베이어 **기본** 순서: 처리 가능한 행 먼저, 판단 불가(판단키 없음) 행은 뒤로.
// 서버는 row_id asc로 주고 그 순서는 **각 구획 안에서 그대로 보존**된다 — 컨베이어의
// "앞에서 소비한다"는 불변식은 유지되고, 앞을 막는 것만 내려간다.
//
// 2026-08-05부터 조작자가 컬럼 정렬을 걸 수 있다. 그때는 이 구획이 아니라 조작자가 고른
// 순서가 표시 순서다 — 이 함수가 정하는 것은 **행 데이터 순서**이고, 정렬을 풀면 그대로
// 돌아온다. 그래서 이 구획은 여전히 유효하지만 **정렬 없는 상태의 규칙**이라는 점이
// 달라졌다. (`blankKeyBoundaryIndex`가 표시 순서가 아니라 행 데이터 순서를 세는 이유.)
function partitionQueueRows(rows, rule) {
  const keyed = [], keyless = [];
  rows.forEach(r => (hasDecisionKeys(r, rule) ? keyed : keyless).push(r));
  return keyed.concat(keyless);
}

// 판단키 없는 행이 시작되는 **행 데이터** 인덱스 (없으면 버퍼 끝).
// 보충(refill)으로 들어온 신규 행을 이 위치에 끼워 넣어 구획을 유지한다.
//
// 🔴 표시 순서가 아니라 행 데이터 순서다. `applyTransaction`의 `addIndex`는 행 데이터에
// 대한 좌표인데, 조작자가 정렬이나 필터를 걸면 표시 순서와 행 데이터 순서가 갈라진다 —
// `getDisplayedRowAtIndex`로 센 인덱스를 넘기면 신규 행이 엉뚱한 자리에 꽂히고, 필터가
// 걸린 상태에서는 가려진 행이 아예 세어지지 않아 구획이 무너진다. `forEachNode`는 정렬·
// 필터 이전 순서로 돈다. (정렬·필터가 없던 시절에는 두 순서가 같아서 티가 나지 않았다.)
function blankKeyBoundaryIndex() {
  if (!S.gridApi || !S.rule) return 0;
  let idx = 0, boundary = -1;
  S.gridApi.forEachNode((node) => {
    if (boundary < 0 && node && node.data && !hasDecisionKeys(node.data, S.rule)) boundary = idx;
    idx++;
  });
  return boundary < 0 ? idx : boundary;
}

// 버퍼에 실제로 들어 있는 행 수 — **필터와 무관하다.**
// `getDisplayedRowCount()`는 필터가 걸리면 줄어든다. 그 수를 버퍼 크기로 읽으면 「필터가
// 가린 것」이 「없는 것」이 되고, 진행률·잔여·오버레이가 전부 같은 거짓말을 하게 된다.
function bufferRowCount() {
  if (!S.gridApi) return 0;
  let n = 0;
  S.gridApi.forEachNode(() => { n++; });
  return n;
}

// 화면이 부분집합을 보이고 있으면 화면이 그렇게 **말한다.**
// 「1,000건」과 「12,431건 중 1,000건」은 다른 문장이고, 조작자가 정렬·필터를 걸 수 있게 된
// 지금 그 차이가 답을 바꾼다: 정렬은 도착한 것만 정렬하기 때문이다. 두 조각 모두 **해당
// 사실이 참일 때만** 붙는다 — 필터가 없으면 필터 머리말이 없고, 서버 전체가 버퍼와 같으면
// 「/ 전체」가 없다. 늘 붙어 있는 꼬리표는 아무도 읽지 않는다.
function worklistCountText() {
  const buffered = bufferRowCount();
  const shown = S.gridApi ? S.gridApi.getDisplayedRowCount() : buffered;
  // 서버가 센 큐 전체(`S.totalBlank`). 버퍼보다 작게 보고되면(낙관적 감산 직후 등) 버퍼를
  // 쓴다 — 「전체보다 많이 들고 있다」는 문장은 어느 쪽으로도 참일 수 없다.
  const total = Math.max(S.totalBlank, buffered);
  const head = shown !== buffered ? `필터 ${shown.toLocaleString()} · ` : '';
  const body = buffered < total
    ? `버퍼 ${buffered.toLocaleString()} / 전체 ${total.toLocaleString()}건`
    : `버퍼 ${buffered.toLocaleString()}건`;
  return `${head}${body}`;
}

// 정렬·필터·저장 뒤에 화면의 수와 오버레이를 같은 사실로 맞춘다 (세는 곳은 한 곳).
function refreshWorklistCounts() {
  el('worklist-meta').textContent = worklistCountText();
  updateWorklistOverlay();
}

// ── 워크리스트 청크 페칭 (항상 skip=0: 완료 행은 큐 술어에서 자동 이탈) ──
// 큐 진입 조건은 이름으로 요청한다: `?enrichment_queue=<규칙명>`. 서버가 규칙의
// target_fields로 **OR-of-blank**를 조성하므로 target이 하나라도 비면 남는다.
// 종전에는 필터 dict(queue_filters)를 실어 보냈고 소비자가 그것을 논리곱해서
// 「전부 blank」가 됐다 — target이 둘인 규칙에서 한 칸만 채워도 행이 목록을 떠났다.
// 판단키 notBlank는 2026-08-04 사용자 재정으로 여기서 빠졌다 — 진행률 분모는 무필터
// 전체 행이라, 잔여가 판단키까지 요구하면 두 수가 다른 모집단을 세어 판단키 빈 행이
// 「답한 것」으로 계산됐다(N36: 데이터 변경 0, 설정 한 줄로 33% → 100%).
// 그 행들은 이제 워크리스트에 **뜬다**(숨기면 인제션 결함이 영영 안 고쳐진다).
async function fetchWorklist(reset) {
  if (!S.rule || S.isFetching) return;

  // 큐 조건을 만들 수 없으면 **묻지 않는다.** 조건을 떼고 물으면 전체 테이블이 큐라는
  // 이름으로 돌아온다 — 서버가 `?cols=`에서 거절하는 바로 그 형태다.
  const queue = queueQuery(S.rule);
  if (!queue) {
    el('worklist-meta').textContent = '큐 조건 없음';
    console.log('[enrichment] queue predicate unavailable', {
      rule: S.rule.name, derived_table: S.rule.derived_table,
      queue_predicate: S.rule.queue_predicate || null,
      queue_filters: S.rule.queue_filters || null,
      target_fields: S.rule.target_fields || [],
    });
    showToast('이 서버에서 큐 조건을 만들 수 없습니다. 규칙 설정을 확인해 주세요.', 'error');
    return;
  }

  const token = S.sessionToken;
  S.isFetching = true;
  el('worklist-meta').textContent = '로딩 중...';

  const url = `${API_BASE}/tables/${encodeURIComponent(S.rule.derived_table)}/data` +
    `?skip=0&limit=${pageLimit}&order_by=row_id&order_desc=false&${queue}`;

  const startTime = performance.now();
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const result = await res.json();
    if (token !== S.sessionToken) return; // 세션 가드: stale 응답 폐기

    S.totalBlank = result.total;
    S.exhausted = result.data.length < pageLimit;

    if (reset) {
      S.gridApi.setGridOption('rowData', partitionQueueRows(result.data, S.rule));
    } else {
      // skip=0 재페치는 버퍼 잔존분과 겹침 → row_id로 dedupe 후 신규만 추가.
      // addIndex로 판단키 없는 꼬리 **앞**에 끼워 넣는다 — 그냥 append하면 처리 가능한
      // 신규 행이 판단 불가 행 뒤로 밀려 컨베이어 앞이 다시 막힌다.
      const known = new Set();
      S.gridApi.forEachNode(n => known.add(String(n.data.row_id)));
      const fresh = result.data.filter(r => !known.has(String(r.row_id)));
      if (fresh.length > 0) {
        S.gridApi.applyTransaction({
          add: partitionQueueRows(fresh, S.rule),
          addIndex: blankKeyBoundaryIndex(),
        });
      }
    }

    const ms = (performance.now() - startTime).toFixed(0);
    updateHeaderStats();
    refreshWorklistCounts();
    el('worklist-meta').textContent = `${worklistCountText()} · ${ms}ms`;

    // 초기 로드 시 첫 항목 자동 선택 (컨베이어 시동)
    if (reset && S.gridApi.getDisplayedRowCount() > 0) {
      selectDisplayedIndex(0);
    }
  } catch (e) {
    if (token !== S.sessionToken) return;
    el('worklist-meta').textContent = '로드 실패';
    showToast(`워크리스트 로드 실패: ${e.message}`, 'error');
  } finally {
    if (token === S.sessionToken) S.isFetching = false;
  }
}

// 진행률 분모: 파생 테이블 전체 **행** 수 (limit=1, total만 사용 — 서버 5초 캐시).
// **무필터가 설계다.** 잔여(큐 술어 = target 중 하나라도 blank)는 이 모집단의 부분집합이고,
// 그 정합이 N36의 수리 그 자체다. 여기에 큐 조건을 붙이면 100% 결함이 되돌아온다.
async function fetchTotalAll() {
  if (!S.rule) return;
  const token = S.sessionToken;
  try {
    const res = await fetch(
      `${API_BASE}/tables/${encodeURIComponent(S.rule.derived_table)}/data?skip=0&limit=1`);
    if (!res.ok) return;
    const result = await res.json();
    if (token !== S.sessionToken) return;
    S.totalAll = result.total;
    updateHeaderStats();
  } catch (e) {
    // 진행률 분모는 부가 정보 — 실패 시 무음 (잔여 카운트로 동작 지속)
  }
}

// 「판단키 없음 N건」 = scope `blank_key`의 total. **서버가 센 수를 그대로 읽는다.**
// 종전에는 잔여 - 판단키 보유 잔여(두 번의 total)를 뺐다. 그 차분은 판단키 컬럼 간 OR을
// 필터 DSL이 표현하지 못해서 존재했을 뿐이고, 술어에 이름이 붙은 지금은 같은 수의 두 번째
// 계산 경로다 — 수가 틀릴 수 있는 자리가 하나 더 있다는 뜻이다. 게다가 워크리스트가
// ANY-blank로 바뀐 뒤의 차분은 **모집단이 다른 두 수의 뺄셈**이 되어 배지가 워크리스트와
// 어긋난다(N36과 같은 형태). 서버는 keyed + blank_key로 큐를 정확히 분할하므로 직접 묻는다.
async function fetchBlankKeyTotal() {
  if (!S.rule) return;
  const queue = queueQuery(S.rule, QUEUE_SCOPE_BLANK_KEY);
  if (!queue) {
    // 구버전 서버: 이 술어를 만들 수 없다 = 「모른다」. 0으로 지어내지도, 뺄셈으로
    // 근사하지도 않는다. 화면에는 아무 말도 하지 않는 쪽이 정직하다.
    S.blankKeyCount = null;
    console.log('[enrichment] blank-key total unavailable on this server', {
      rule: S.rule.name, derived_table: S.rule.derived_table,
      scope: QUEUE_SCOPE_BLANK_KEY, queue_predicate: S.rule.queue_predicate || null,
    });
    updateHeaderStats();
    return;
  }
  const token = S.sessionToken;
  try {
    const res = await fetch(`${API_BASE}/tables/${encodeURIComponent(S.rule.derived_table)}` +
      `/data?skip=0&limit=1&${queue}`);
    if (!res.ok) return;
    const result = await res.json();
    if (token !== S.sessionToken) return;
    S.blankKeyCount = result.total;
    updateHeaderStats();
  } catch (e) {
    // 실패 시 마지막으로 아는 값 유지 — 「없다」와 「확인 못 했다」를 섞지 않는다
  }
}

function refillIfNeeded() {
  if (!S.gridApi || S.exhausted || S.isFetching) return;
  if (S.gridApi.getDisplayedRowCount() < REFILL_THRESHOLD) {
    fetchWorklist(false);
  }
}

// ── 헤더 통계 (진행률 / 잔여 / 세션) ───────────────────────
function updateHeaderStats() {
  const remaining = Math.max(0, S.totalBlank);
  const badge = el('remaining-badge');
  badge.textContent = remaining === 0 ? '✅ 결손 없음' : `잔여 ${remaining.toLocaleString()}건`;
  badge.classList.toggle('all-done', remaining === 0);
  el('session-badge').textContent = `이번 세션 ${S.doneCount.toLocaleString()}건`;

  // 「판단키 없음 N건」 — 서버가 센 수를 그대로 싣는다. 여기서 계산하지 않는다.
  // null = 「확인 못 했다」(구버전 서버), 0 = 「없다」. 둘 다 배지를 숨기지만 상태로는
  // 구별해 둔다: 「0건」이라고 말하는 것과 아무 말도 하지 않는 것은 다른 사실이다.
  const known = typeof S.blankKeyCount === 'number';
  const bkBadge = el('blankkey-badge');
  if (bkBadge) {
    bkBadge.style.display = (known && S.blankKeyCount > 0) ? 'inline-block' : 'none';
    if (known) bkBadge.textContent = `⚠️ 판단키 없음 ${S.blankKeyCount.toLocaleString()}건`;
    // 이 수는 「판단키가 온전하지 않은 행 수」다. 종전 설명은 여기에 「여기서는 해소할 수
    // 없다」를 덧붙였는데, 남은 키로 답하는 참조뷰가 생긴 지금 그건 틀린 주장이다.
    bkBadge.title = '판단키가 온전하지 않은 행 수 (워크리스트 맨 뒤).';
  }

  if (S.totalAll !== null && S.totalAll > 0) {
    const filled = Math.max(0, S.totalAll - remaining);
    const pct = Math.round((filled / S.totalAll) * 100);
    // 단위는 「행」이다 — 분모도 분자도 파생 테이블의 행 카운트다. 종전 'keys'는
    // composite_key_source == decision_key인 현재 규칙에서만 우연히 참인 주장이었다.
    el('progress-text').textContent =
      `${filled.toLocaleString()} / ${S.totalAll.toLocaleString()} 행`;
    el('progress-percent').textContent = `${pct}%`;
    el('progress-fill').style.width = `${pct}%`;
  } else {
    el('progress-text').textContent = '- / -';
    el('progress-percent').textContent = '-%';
    el('progress-fill').style.width = '0%';
  }
}

function updateWorklistOverlay() {
  const overlay = el('worklist-overlay');
  const count = bufferRowCount();
  const shown = S.gridApi ? S.gridApi.getDisplayedRowCount() : 0;

  // 필터가 전부 가린 것과 큐가 빈 것은 **다른 사실**이다. 여기서 「모든 결손이 처리되었
  // 습니다」를 말하면 화면이 자기가 숨긴 것을 없다고 주장한다 — 결과를 숨기는 설계.
  //
  // 이 경우 이 오버레이는 **비켜선다.** 그리드 자신의 「필터 결과 없음」(양쪽 표가 공유하는
  // 한 문장, `GRID_SHARED_OPTIONS`)이 이미 그 자리에 있고, 몇 건을 들고 있는지는 패널 머리의
  // 수(`worklistCountText` → `필터 0 · 버퍼 115건`)가 말한다. 같은 사실을 두 번 쓰지 않는다.
  if (count > 0 && shown === 0) {
    overlay.style.display = 'none';
    return;
  }

  if (count === 0) {
    if (S.totalBlank === 0) {
      el('worklist-overlay-icon').textContent = '🎉';
      el('worklist-overlay-text').textContent = '모든 결손이 처리되었습니다!';
    } else {
      el('worklist-overlay-icon').textContent = '📭';
      el('worklist-overlay-text').textContent = '표시할 항목이 없습니다. 새로고침 해 주세요.';
    }
    overlay.style.display = 'flex';
  } else {
    overlay.style.display = 'none';
  }
}

// ── [B] 판단 · 입력 컨베이어 ───────────────────────────────
function showConveyorEmpty() {
  el('conveyor-empty').style.display = 'flex';
  el('conveyor-detail').style.display = 'none';
  S.selectedRowId = null;
  clearReferencePanel();
}

// IS WHAT SITS IN THIS BOX STILL THE STORED VALUE, UNTOUCHED? One spelling, because the
// screen's mark and `saveCurrent`'s write set must be the SAME sentence. If they drift, the
// form says "기존값" while the save records a human declaration -- which is the whole defect.
// Blankness folds the way the queue folds it (trim), so a stored value of whitespace is no
// value at all and typing over it is a real edit.
function isTargetUntouched(input) {
  const baseline = input.dataset.baseline || '';
  return baseline !== '' && input.value.trim() === baseline;
}

// The `proposed` shape from the map screen, for the same reason it exists there: what is in
// this control was not put there by you. Dropped the instant the text differs, restored if the
// operator types the stored string back -- retyping a machine value character for character is
// not a decision, and nothing gets written for it either.
function markTargetInput(input) {
  const untouched = isTargetUntouched(input);
  input.dataset.existing = untouched ? 'true' : 'false';
  const mark = el(input.dataset.markId);
  if (!mark) return;
  const src = input.dataset.source || '';
  mark.textContent = untouched ? (src ? `기존값 · ${src}` : '기존값') : '';
  mark.style.display = untouched ? 'inline-flex' : 'none';
}

function renderDetail(row) {
  if (!row || !S.rule) return;
  S.selectedRowId = row.row_id;
  el('conveyor-empty').style.display = 'none';
  el('conveyor-detail').style.display = 'flex';

  // 판단키 (XSS 안전: textContent만 사용)
  const keyBody = el('decision-key-body');
  keyBody.innerHTML = '';
  // 여기서 말하는 것은 **이 행의 사실**뿐이다: 어느 판단키가 비었는가. 종전에는 "여기서는
  // 판단할 수 없습니다"라고 단언했는데, 2026-08-05 사용자 재정("일부가 비면 남은 것으로
  // 한다") 이후 그것은 틀린 문장이다. 남은 키만 묶는 참조뷰는 답하고, 스윕도 남은 키로
  // 해석한다. 무엇을 물을 수 있고 무엇을 물을 수 없는지의 판정과 그 문장은 서버 것이고,
  // 참조뷰 패널이 뷰마다 그대로 싣는다. 여기서 그걸 다시 지으면 철자가 둘이 된다.
  const blankKeys = (S.rule.decision_key || [])
    .filter(col => String(cellVal(row, col)).trim() === '');
  if (blankKeys.length > 0) {
    const warn = document.createElement('div');
    warn.className = 'blankkey-notice';
    warn.textContent = `판단키 공백: ${blankKeys.join(', ')}`;
    keyBody.appendChild(warn);
  }
  (S.rule.decision_key || []).forEach(col => {
    const rowEl = document.createElement('div');
    rowEl.className = 'kv-row';
    const k = document.createElement('span');
    k.className = 'kv-key';
    k.textContent = col;
    const v = document.createElement('span');
    v.className = 'kv-val';
    const val = cellVal(row, col);
    v.textContent = val === '' ? '(empty)' : String(val);
    rowEl.appendChild(k);
    rowEl.appendChild(v);
    keyBody.appendChild(rowEl);
  });

  // 단서 칩
  const chips = el('clue-chips');
  chips.innerHTML = '';
  const listCols = S.rule.list_columns || [];
  el('clue-block').style.display = listCols.length > 0 ? 'block' : 'none';
  listCols.forEach(col => {
    const chip = document.createElement('span');
    chip.className = 'clue-chip';
    const k = document.createElement('span');
    k.className = 'chip-key';
    k.textContent = col;
    const v = document.createElement('span');
    v.className = 'chip-val';
    const val = cellVal(row, col);
    v.textContent = val === '' ? '-' : String(val);
    chip.appendChild(k);
    chip.appendChild(v);
    chips.appendChild(chip);
  });

  // target 입력 필드 (규칙 메타 기반 동적 생성)
  //
  // A COLUMN THAT ALREADY HOLDS A VALUE RENDERS WITH IT. Handing over an empty box for a
  // column that is already decided made the operator retype what was already there, and the
  // retyped copy landed as `user` (priority 0) -- a machine decision turned into a human one
  // because the form did not show what it already knew. The value is loaded, marked as
  // existing, and `saveCurrent` writes only what actually changed.
  const inputsBody = el('target-inputs');
  inputsBody.innerHTML = '';
  (S.rule.target_fields || []).forEach((field, idx) => {
    const wrap = document.createElement('div');
    wrap.className = 'target-field-row';
    const head = document.createElement('div');
    head.className = 'target-field-head';
    const label = document.createElement('label');
    label.className = 'target-field-label';
    label.textContent = field;
    label.htmlFor = `target-input-${idx}`;
    const mark = document.createElement('span');
    mark.className = 'target-existing-mark';
    mark.id = `target-existing-${idx}`;
    head.appendChild(label);
    head.appendChild(mark);

    const input = document.createElement('input');
    input.type = 'text';
    input.id = `target-input-${idx}`;
    input.className = 'glass-input target-input';
    input.dataset.field = field;
    input.dataset.markId = mark.id;
    // The baseline is the comparison the write set is decided against, so it is stored
    // TRIMMED and the box is loaded with the same string -- otherwise stray whitespace in
    // storage reads as an edit on every render and rewrites provenance by itself.
    const stored = String(cellVal(row, field)).trim();
    input.dataset.baseline = stored;
    input.dataset.source = cellSource(row, field);
    input.value = stored;
    input.placeholder = stored === '' ? `${field} 입력 후 Enter` : '';
    input.autocomplete = 'off';
    input.addEventListener('keydown', onInputKeydown);
    input.addEventListener('input', () => markTargetInput(input));
    wrap.appendChild(head);
    wrap.appendChild(input);
    inputsBody.appendChild(wrap);
    markTargetInput(input);
  });

  // Focus lands on the first EMPTY box. Parking the cursor in a filled one would make
  // overwriting a stored decision the default gesture; the queue's business is the blanks.
  const inputs = Array.from(inputsBody.querySelectorAll('input'));
  const first = inputs.find(i => i.value.trim() === '') || inputs[0];
  if (first) first.focus();

  // [C] 참조뷰: 선택 행 기준 비동기 로드 예약 (debounce — 입력·이동을 절대 막지 않음)
  scheduleReferenceLoad();
}

function onInputKeydown(e) {
  if (e.key === 'Enter') {
    e.preventDefault();
    saveCurrent();
  } else if (e.key === 'Escape') {
    e.preventDefault();
    // Back to what is stored, not to blank. Emptying a box that holds an existing value would
    // stage an erasure the operator never asked for, and the next save would have to refuse it.
    const inputs = Array.from(el('target-inputs').querySelectorAll('input'));
    inputs.forEach(i => { i.value = i.dataset.baseline || ''; markTargetInput(i); });
    const first = inputs.find(i => i.value.trim() === '') || inputs[0];
    if (first) first.focus();
  } else if (e.key === 'ArrowDown') {
    e.preventDefault();
    moveSelection(1);
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    moveSelection(-1);
  }
}

function moveSelection(delta) {
  if (!S.gridApi || S.selectedRowId === null) return;
  const node = S.gridApi.getRowNode(String(S.selectedRowId));
  const count = S.gridApi.getDisplayedRowCount();
  if (!node || count === 0) return;
  const next = Math.min(Math.max(node.rowIndex + delta, 0), count - 1);
  if (next !== node.rowIndex) selectDisplayedIndex(next);
}

function selectDisplayedIndex(idx) {
  if (!S.gridApi) return;
  const count = S.gridApi.getDisplayedRowCount();
  if (count === 0) {
    showConveyorEmpty();
    updateWorklistOverlay();
    return;
  }
  const clamped = Math.min(Math.max(idx, 0), count - 1);
  const node = S.gridApi.getDisplayedRowAtIndex(clamped);
  if (!node) return;
  node.setSelected(true, true); // clearSelection=true → single 유지, onSelectionChanged가 renderDetail 호출
  S.gridApi.ensureIndexVisible(clamped, 'middle');
}

// 방금 쓴 값만 이 행의 셀에 반영한다. **출처는 지어내지 않는다.**
// The PUT does not return the stored row, so what finally won the priority contest is not
// known here. The shape of the cell contract is kept and `priority_source` goes to null,
// which is "unread", not "nobody" -- carrying the OLD source forward would attribute this
// value to a writer that did not write it, the same impersonation this round is closing.
function applyWrittenValues(rowData, written) {
  if (!rowData) return;
  if (!rowData.data) rowData.data = {};
  Object.keys(written).forEach(col => {
    const cell = rowData.data[col];
    rowData.data[col] = (cell && typeof cell === 'object')
      ? { ...cell, value: written[col], priority_source: null }
      : { value: written[col], is_overwrite: false, priority_source: null };
  });
}

// ── 저장 → 낙관적 제거 → 다음 항목 (컨베이어 핵심 루프) ────
//
// THE WRITE SET IS WHAT THE OPERATOR EDITED, AND NOTHING ELSE. An untouched column keeps its
// existing value AND its existing provenance (`enrichment_auto_confirm`, or whatever wrote
// it); only a genuinely edited one becomes `user`. Sending every box -- which is what the
// all-fields-required guard forced once partly-filled rows started staying in the queue --
// rewrote machine decisions as human ones with a hand-typed duplicate of themselves.
//
// Overwriting a stored machine value on purpose stays possible and needs no control: EDITING
// THE FIELD IS THE ACT. What it must not be is an accident, and it no longer can be, because
// leaving the box alone now writes nothing.
async function saveCurrent() {
  if (S.saving || !S.rule || S.selectedRowId === null || !S.gridApi) return;

  const inputs = Array.from(el('target-inputs').querySelectorAll('input'));
  if (inputs.length === 0) return;

  const updates = {};
  // The whole record goes to the console: which columns were written, which were held back
  // and under whose provenance. One line reaches the screen; the audit belongs here.
  const record = { rule: S.rule.name, row_id: S.selectedRowId, written: {}, withheld: {} };
  const after = {};   // target state AFTER this save -- decides whether the row leaves the queue
  for (const input of inputs) {
    const field = input.dataset.field;
    const baseline = input.dataset.baseline || '';
    const val = input.value.trim();
    after[field] = val;
    if (val === baseline) {
      record.withheld[field] = { value: baseline, priority_source: input.dataset.source || null };
      continue;
    }
    if (val === '') {
      // Clearing is not confirming. Writing '' as `user` would erase a machine decision by
      // hand and sign the empty space with a person's name, so it is refused rather than sent.
      showToast(`'${field}' 칸이 비었습니다. 값을 되돌리거나 새 값을 입력해 주세요.`, 'warning');
      console.log('[enrichment] save refused: a target was emptied', { ...record, field, baseline });
      input.focus();
      return;
    }
    updates[field] = val;
    record.written[field] = { from: baseline || null, to: val,
                              was: input.dataset.source || null, becomes: 'user' };
  }

  if (Object.keys(updates).length === 0) {
    // A REFUSAL, NOT A SILENT NO-OP. A save that writes nothing and reports success teaches
    // the operator that the button lies, and the next real failure gets read as the same lie.
    showToast('바뀐 값이 없습니다. 고칠 칸을 수정한 뒤 저장해 주세요.', 'warning');
    console.log('[enrichment] save refused: nothing edited', record);
    const first = inputs.find(i => i.value.trim() === '') || inputs[0];
    if (first) first.focus();
    return;
  }

  const rowId = S.selectedRowId;
  const node = S.gridApi.getRowNode(String(rowId));
  const removedIndex = node && node.rowIndex !== null ? node.rowIndex : 0;
  const token = S.sessionToken;

  S.saving = true;
  const saveBtn = el('save-btn');
  saveBtn.disabled = true;

  // 기존 handleCellEdit 계약 그대로 (GeneralUpdateBatch) — 셀 계약 불변
  const payload = {
    updates: [{
      row_id: rowId,
      updates: updates,
      source_name: 'user',
      updated_by: CURRENT_USER,
    }],
    silent: false,
    // [V1 effort instrument] Optional field. Raw counts only — weighted at query time.
    effort: effortSnapshot(),
  };

  try {
    const res = await fetch(
      `${API_BASE}/tables/${encodeURIComponent(S.rule.derived_table)}/data/updates`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || `HTTP ${res.status}`);
    }

    // [V1 effort instrument] Reset ONLY when the server confirms it recorded the effort.
    // `res.ok` alone is not enough: a value that already matches storage returns 200 and
    // writes no effort row, and committing there erases the effort that attempt cost.
    // Still placed BEFORE the stale guard below: the server committed either way, so the
    // effort was genuinely spent and has already been reported.
    const result = await res.json().catch(() => null);
    effortCommitIfRecorded(result);

    console.log('[enrichment] saved', record);

    if (token !== S.sessionToken) return; // 저장 중 규칙 전환 → UI 반영 생략

    // 큐 이탈 판정은 「이 저장 뒤에도 target이 비어 있는가」다. The queue predicate is
    // OR-of-blank, so a row with one target still empty STAYS in it. A save that fills one of
    // two is now reachable (it was not while every box was mandatory), and removing the row
    // for it would drop it off the screen while it is still in the queue and drift the
    // remainder by one per save -- a count claiming progress that did not happen.
    const stillBlank = (S.rule.target_fields || []).some(f => (after[f] || '') === '');

    const liveNode = S.gridApi.getRowNode(String(rowId));
    // 판단키 보유 여부는 **제거 전에** 읽는다. 판단키가 빈 행을 채웠다면 그 행은
    // blank_key 집계에서도 함께 빠진다 — 잔여만 줄이면 배지가 저장 한 번마다 1씩 부푼다.
    const wasKeyed = liveNode && liveNode.data ? hasDecisionKeys(liveNode.data, S.rule) : true;

    if (stillBlank) {
      // The row stays. Only the written columns move, and the form redraws so what was just
      // stored reads as an existing value and the cursor lands on the box still empty.
      if (liveNode && liveNode.data) {
        applyWrittenValues(liveNode.data, updates);
        S.gridApi.applyTransaction({ update: [liveNode.data] });
        renderDetail(liveNode.data);
      }
    } else {
      // 낙관적 반영: target이 전부 찼으므로 큐(ANY-blank)에서 이탈 → 버퍼에서 제거
      if (liveNode) S.gridApi.applyTransaction({ remove: [liveNode.data] });
      S.totalBlank = Math.max(0, S.totalBlank - 1);
      if (!wasKeyed && typeof S.blankKeyCount === 'number') {
        S.blankKeyCount = Math.max(0, S.blankKeyCount - 1);
      }
      S.doneCount += 1;
    }

    flashSaved();
    updateHeaderStats();
    refreshWorklistCounts();

    // 다음 항목 자동 선택 (제거된 자리 승계) + 버퍼 보충
    if (!stillBlank) {
      selectDisplayedIndex(removedIndex);
      refillIfNeeded();
    }
  } catch (e) {
    // 실패: 입력 유지 + 행 잔존
    showToast(`저장 실패: ${e.message}`, 'error');
  } finally {
    S.saving = false;
    saveBtn.disabled = false;
  }
}

function flashSaved() {
  const block = el('target-input-block');
  block.classList.remove('saved-flash');
  void block.offsetWidth; // reflow로 애니메이션 재시동
  block.classList.add('saved-flash');
  setTimeout(() => block.classList.remove('saved-flash'), 600);
}

// ── [C] 참조뷰 (실데이터) ──────────────────────────────────
// 계약: GET /enrichment/rules/{rule}/references/{i}?params=<urlencoded JSON {decision_key col: value}>
//   → 200 {"label", "columns": [str], "rows": [[...]]} (서버 LIMIT 강제, 기본 200)
//   → 400 params에 decision_key 외 키 / 404 규칙·인덱스 미존재
// 원칙: 활성 탭만 조회(선택 이동당 1요청), debounce + 시퀀스/세션 이중 가드,
//       로딩이 컨베이어 입력·포커스를 절대 막지 않음(순수 비동기, 포커스 무접촉).

function initReferencePanel(rule) {
  S.refViews = Array.isArray(rule.reference_views) ? rule.reference_views : [];
  S.refActiveIdx = 0;
  S.refSeq += 1; // 규칙 전환: 진행 중 응답 전부 무효화
  if (S.refTimer) { clearTimeout(S.refTimer); S.refTimer = null; }
  S.refCache.clear();
  S.refCacheRowId = null;
  // 규칙이 바뀌면 컬럼 구성도 통째로 바뀐다 — 다음 렌더가 정렬·필터를 버리도록 표시한다.
  S.refColSignature = null;
  el('reference-meta').textContent = '';

  const tabs = el('reference-tabs');
  tabs.innerHTML = '';

  if (S.refViews.length === 0) {
    tabs.style.display = 'none';
    showRefStatus('🗒️', '참조뷰 미설정',
      '이 규칙에는 참조뷰가 정의되어 있지 않습니다.\nenrichment_rules.json의 reference_views에 등록하면 표시됩니다.');
    return;
  }

  tabs.style.display = 'flex';
  S.refViews.forEach((view, idx) => {
    const tab = document.createElement('button');
    tab.type = 'button';
    tab.className = 'reference-tab' + (idx === S.refActiveIdx ? ' active' : '');
    tab.textContent = view.label || `참조뷰 ${idx + 1}`;
    // mousedown 기본동작 차단 → 탭 클릭이 [B] 입력 포커스를 빼앗지 않음 (컨베이어 무간섭)
    tab.addEventListener('mousedown', (e) => e.preventDefault());
    tab.addEventListener('click', () => activateRefTab(idx));
    tabs.appendChild(tab);
  });
  showRefIdle();
}

function activateRefTab(idx) {
  if (idx === S.refActiveIdx) return;
  S.refActiveIdx = idx;
  el('reference-tabs').querySelectorAll('.reference-tab').forEach((t, i) => {
    t.classList.toggle('active', i === idx);
  });
  // 탭 전환은 의도적 단일 행동 — debounce 없이 즉시 로드 (같은 행이면 캐시 히트)
  if (S.refTimer) { clearTimeout(S.refTimer); S.refTimer = null; }
  loadActiveReference();
}

// 선택 변경 시 호출: debounce로 고속 ↑/↓ 이동·연속 Enter의 요청 폭주 방지
function scheduleReferenceLoad() {
  if (S.refViews.length === 0) return;
  S.refSeq += 1; // 이전 in-flight 응답 즉시 무효화 (이전 행의 데이터가 새 행에 표시되는 것 방지)
  if (S.refTimer) clearTimeout(S.refTimer);
  S.refTimer = setTimeout(() => {
    S.refTimer = null;
    loadActiveReference();
  }, REF_DEBOUNCE_MS);
}

// 컨베이어가 비었을 때: 대기 로드 취소 + 패널을 유휴 상태로
function clearReferencePanel() {
  S.refSeq += 1;
  if (S.refTimer) { clearTimeout(S.refTimer); S.refTimer = null; }
  el('reference-meta').textContent = '';
  if (S.refViews.length > 0) showRefIdle();
}

async function loadActiveReference() {
  if (!S.rule || S.refViews.length === 0 || !S.gridApi) return;
  if (S.selectedRowId === null) { showRefIdle(); return; }
  const node = S.gridApi.getRowNode(String(S.selectedRowId));
  if (!node || !node.data) { showRefIdle(); return; }

  const rowId = S.selectedRowId;
  const idx = S.refActiveIdx;
  const view = S.refViews[idx];

  // 판단키가 일부(또는 전부) 비어 있어도 **묻는다.** 어느 뷰가 답할 수 있는지는 서버가
  // 안다. 남은 키만 묶는 뷰는 답하고, 빈 컬럼을 묶는 뷰는 이름 붙은 거절로 400을 낸다.
  // 여기서 미리 거르면 서버가 이미 적용하는 규칙의 **두 번째 구현**이 되고 둘은 언젠가
  // 갈라진다(이번 라운드가 내내 닫아 온 결함 계급). 그래서 사전 게이트가 없다.
  // 종전 게이트는 뷰 하나가 아니라 **행 전체**를 「조회 불가」로 접었다: 스윕은 같은 행을
  // 남은 키로 해석하는데 사람은 근거를 볼 수 없다는 뜻이었고, 그 절반이 이 수리다.

  // 행 단위 캐시: 같은 행에서 탭을 오가면 재요청하지 않음 (행이 바뀌면 무효)
  if (S.refCacheRowId !== rowId) {
    S.refCache.clear();
    S.refCacheRowId = rowId;
  }
  const cached = S.refCache.get(idx);
  if (cached) { renderRefOutcome(cached); return; }

  const seq = ++S.refSeq;
  const token = S.sessionToken;
  showRefLoading(view.label || `참조뷰 ${idx + 1}`);

  // params = 선택 행의 decision_key 전체 값 (계약: decision_key 외 키 금지 → 400).
  // 빈 값도 **거르지 않고 그대로** 보낸다: 빈 값을 「없는 값」으로 접을지는 서버의 규칙이고
  // (`missing_binds`), 여기서 미리 빼면 그 규칙의 사본이 하나 더 생긴다.
  const paramsObj = {};
  (S.rule.decision_key || []).forEach(col => {
    paramsObj[col] = cellVal(node.data, col);
  });
  const url = `${API_BASE}/enrichment/rules/${encodeURIComponent(S.rule.name)}` +
    `/references/${idx}?params=${encodeURIComponent(JSON.stringify(paramsObj))}`;

  const t0 = performance.now();
  try {
    const res = await fetch(url);
    if (seq !== S.refSeq || token !== S.sessionToken) return; // stale 폐기
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      if (seq !== S.refSeq || token !== S.sessionToken) return;
      const refusal = {
        refused: true,
        status: res.status,
        detail: typeof err.detail === 'string' ? err.detail : null,
      };
      // 전문은 콘솔로, 화면은 한 줄. 400은 이 (행, 뷰) 조합에 대해 **결정적**이라 캐시한다.
      // 탭을 오갈 때마다 같은 거절을 다시 묻지 않는다. 404·네트워크 오류는 캐시하지
      // 않는다: 「지금 못 물었다」와 「이 키로는 물을 수 없는 뷰다」는 다른 사실이다.
      console.log('[enrichment] reference view refused', {
        rule: S.rule.name, index: idx, label: view.label,
        params: paramsObj, status: res.status, detail: refusal.detail,
      });
      if (res.status === 400) S.refCache.set(idx, refusal);
      renderRefOutcome(refusal);
      return;
    }
    const data = await res.json();
    if (seq !== S.refSeq || token !== S.sessionToken) return;
    const payload = {
      columns: Array.isArray(data.columns) ? data.columns : [],
      rows: Array.isArray(data.rows) ? data.rows : [],
      ms: (performance.now() - t0).toFixed(0),
    };
    S.refCache.set(idx, payload);
    renderRefOutcome(payload);
  } catch (e) {
    if (seq !== S.refSeq || token !== S.sessionToken) return;
    console.log('[enrichment] reference view request failed', {
      rule: S.rule.name, index: idx, label: view.label, error: e && e.message,
    });
    renderRefOutcome({ refused: true, status: 0, detail: null }); // 네트워크 오류
  }
}

// 응답 1건을 그린다. 표이거나, 서버가 이름 붙인 거절이거나. 한 행에서 어떤 뷰는 답하고
// 어떤 뷰는 거절하는 것이 **이제 정상 상태**다: 행을 하나의 판정으로 접지 않는다.
function renderRefOutcome(outcome) {
  if (outcome && outcome.refused) {
    showRefError(outcome.status, outcome.detail);
    return;
  }
  renderRefTable(outcome);
}

// 컬럼은 **응답이 말한다.** 조작자가 SQL을 쓰므로 뷰마다 컬럼 집합이 다르고, 여기서
// 선언하는 순간 그 선언과 실제 결과가 갈라진다.
//
// `field` IS THE POSITION, NEVER THE NAME. Operator SQL can return two columns with the same
// label, and AG-Grid reads a dotted field as a property path — either would silently drop a
// column. The name is used for the header only, so `SELECT a.x, b.x` and `SELECT 1 AS "a.b"`
// both render whole. Rows arrive as arrays, so the value is read by index.
function refColumnDefs(columns) {
  return columns.map((name, i) => ({
    field: `c${i}`,
    headerName: String(name),
    headerTooltip: String(name),
    valueGetter: (p) => (p.data ? p.data[i] : undefined),
    // NULL은 '-'로 **보이기만** 한다. 필터·정렬은 원래 값(null)을 보므로 빈 값은
    // `compareCells` 규칙대로 뒤로 간다 — 표시용 문자열로 걸러지지 않는다.
    valueFormatter: (p) => (p.value === null || p.value === undefined ? '-' : String(p.value)),
    cellClassRules: { 'ref-null': (p) => p.value === null || p.value === undefined },
    minWidth: 110,
  }));
}

// 서버 LIMIT(기본 200, 최대 1000) 이하 행만 오므로 클라가 전량을 들고 있고, 정렬·필터도
// 전량에 대해 답한다 (2026-08-05 제품소유자 재정: 왕복 없이 브라우저에서).
//
// ⚠️ 이 응답에는 절단 플래그가 없다 — `{label, columns, rows}`가 전부이고 뷰별 limit은
// 서버가 클라에 노출하지 않는다(`GET /enrichment/rules` 주석). 그래서 「잘렸다」를 여기서
// 말하지 않는다. 모르는 사실을 짐작해서 쓰는 배지는 없는 것만 못하다.
function renderRefTable(payload) {
  const wrap = el('reference-table-wrap');
  S.refRowCount = payload.rows.length;
  S.refMs = payload.ms;
  updateRefMeta();

  if (payload.rows.length === 0) {
    wrap.style.display = 'none';
    showRefStatus('🫙', '근거 데이터 없음', '이 판단키에 해당하는 참조 데이터가 없습니다.');
    return;
  }

  hideRefStatus();
  wrap.style.display = 'block'; // AG-Grid가 크기를 재기 전에 보이는 상태여야 한다

  const defs = refColumnDefs(payload.columns);
  const signature = payload.columns.map(String).join(' ');

  if (!S.refGridApi) {
    S.refGridApi = createGrid(wrap, {
      ...GRID_SHARED_OPTIONS,
      columnDefs: defs,
      rowData: payload.rows,
      suppressCellFocus: true,
      // 워크리스트와 **같은** 규율. 두 표가 한 화면에서 다르게 굴면 그 자체가 함정이다.
      defaultColDef: { ...GRID_SORT_FILTER_DEFAULTS },
      onFilterChanged: () => updateRefMeta(),
    });
  } else {
    if (signature !== S.refColSignature) {
      // 컬럼이 바뀌었다 = 다른 질문이다. 이전 뷰의 정렬·필터를 남기면 새 결과가 이유 없이
      // 걸러진 채로 나타난다 — 조작자에게는 「데이터가 없다」로 보이는 바로 그 상태.
      S.refGridApi.setFilterModel(null);
      S.refGridApi.applyColumnState({ defaultState: { sort: null } });
      S.refGridApi.setGridOption('columnDefs', defs);
    }
    // 같은 뷰에서 행만 바뀌면 정렬·필터는 **유지한다**: 조작자가 한 번 정해 둔 보기 방식을
    // 항목을 옮길 때마다 되돌리면 컨베이어에서 그 기능이 쓸모없어진다.
    S.refGridApi.setGridOption('rowData', payload.rows);
  }
  S.refColSignature = signature;
  updateRefMeta();
}

// 참조뷰 메타 한 줄. 필터가 걸렸을 때만 앞머리가 붙는다 — 「200건」과 「200건 중 12건을
// 보는 중」은 다른 문장이고, 그 차이가 실재할 때만 화면에 나타난다.
function updateRefMeta() {
  const total = S.refRowCount;
  const shown = S.refGridApi ? S.refGridApi.getDisplayedRowCount() : total;
  const head = shown !== total ? `필터 ${shown.toLocaleString()} · ` : '';
  el('reference-meta').textContent = `${head}${total.toLocaleString()}건 · ${S.refMs}ms`;
}

// ── 참조뷰 상태 표시 헬퍼 (loading / idle / empty / error) ──
function showRefStatus(icon, text, sub, spinning) {
  el('reference-table-wrap').style.display = 'none';
  el('reference-status').style.display = 'flex';
  el('reference-spinner').style.display = spinning ? 'block' : 'none';
  el('reference-status-icon').style.display = spinning ? 'none' : 'block';
  el('reference-status-icon').textContent = icon;
  el('reference-status-text').textContent = text;
  el('reference-status-sub').textContent = sub || '';
}

function hideRefStatus() {
  el('reference-status').style.display = 'none';
}

function showRefIdle() {
  el('reference-meta').textContent = '';
  showRefStatus('🛰️', '항목을 선택하면 근거 데이터가 표시됩니다.', '');
}

function showRefLoading(label) {
  showRefStatus('', `'${label}' 조회 중...`, '', true);
}

// 오류는 토스트가 아닌 패널 내 표시 — 고속 이동 중 토스트 스팸으로 컨베이어를 방해하지 않음
function showRefError(status, detail) {
  el('reference-meta').textContent = '';
  if (status === 404) {
    showRefStatus('🧭', '참조뷰를 찾을 수 없습니다',
      '규칙 설정이 변경되었을 수 있습니다. 새로고침(🔄) 해 주세요.');
  } else if (status === 400) {
    // 거절이지 고장이 아니다. 판단키가 일부만 남은 행에서 이건 정상 상태이므로 오류로
    // 읽히는 문구를 쓰지 않는다. 머리말은 클라의 분류 라벨이고, **사유 문장은 서버 것을
    // 그대로** 싣는다(2026-08-05 사용자 재정: 어휘는 공유, 문장은 서버의 것). 서버가
    // 아무 말도 안 했으면 비운다. 침묵은 정직하고, 지어낸 문장은 그렇지 않다.
    showRefStatus('🚧', '조회 불가 참조뷰', detail || '');
  } else if (status === 0) {
    showRefStatus('📡', '서버에 연결할 수 없습니다', '네트워크 상태 확인 후 다시 시도해 주세요.');
  } else {
    showRefStatus('⚠️', `참조뷰 조회 실패 (HTTP ${status})`, detail || '');
  }
}

// ── 초기화 ─────────────────────────────────────────────────
async function init() {
  initTheme();
  // [V1 effort instrument] Start counting before any listener can fire. Invisible: no UI.
  // installNavLinkCounting covers the two "메인으로" anchors -> `enrichment > grid`.
  startSession();
  installGlobalListeners();
  installNavLinkCounting(ROUTES.ENRICHMENT);
  el('rule-select').addEventListener('change', (e) => {
    const rule = S.rules.find(r => r.name === e.target.value);
    // [V1 effort instrument] Counted on the USER's handler, not inside selectRule():
    // start() calls it on boot with the ?rule= deep link, which is not a move the user made.
    // The refresh button also calls it, but re-selecting the SAME rule is a refetch of the
    // same work stream, not a screen move — deliberately not counted.
    if (rule) {
      countNav(ROUTES.ENRICHMENT, ROUTES.ENRICHMENT);
      selectRule(rule);
    }
  });
  el('refresh-btn').addEventListener('click', () => {
    if (S.rule) selectRule(S.rule);
  });
  el('save-btn').addEventListener('click', saveCurrent);
  el('setup-retry-btn').addEventListener('click', () => start());

  await start();
}

async function start() {
  showSetupState('🧩', 'Enrichment 규칙을 불러오는 중...', '');
  const ok = await loadRules();
  if (!ok) return;

  populateRuleSelect();

  // ?rule={name} 진입 파라미터 (main.js URLSearchParams 선례)
  const params = new URLSearchParams(window.location.search);
  const wanted = params.get('rule');
  const rule = S.rules.find(r => r.name === wanted) || S.rules[0];
  selectRule(rule);
}

init();
