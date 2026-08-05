// ============================================================
// Enrichment Queue Page Orchestrator (Phase 1 conveyor + Phase 2 reference views)
// - admin.js / map_editor.js 선례: 자체 모듈 지역 상태 (state.js/dom.js/api.js 미임포트)
// - 재사용: config.js / utils.js / AG-Grid Community
// - 계약(확정): GET /enrichment/rules
//   { "rules": [ { name, source_table, derived_table, decision_key[],
//                  target_fields[], list_columns[], reference_views:[{label}] } ] }
// - 워크리스트: GET /tables/{derived}/data + blank 필터 청크 페칭 (전량 로드 금지)
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
  totalKeyed: null,     // 판단키를 갖춘 잔여 (= 사람이 실제로 처리 가능한 항목)
  blankKeyCount: 0,     // 잔여 - 판단키 보유 잔여. 「판단키 없음 N건」의 실수
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
};

const el = (id) => document.getElementById(id);

// 서버 셀 계약 {value, is_overwrite, priority_source} → 표시값 (형태는 절대 변조하지 않음)
function cellVal(row, col) {
  const c = row && row.data ? row.data[col] : undefined;
  if (c && typeof c === 'object') {
    return c.value === null || c.value === undefined ? '' : c.value;
  }
  return c === null || c === undefined ? '' : c;
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
  S.totalKeyed = null;
  S.blankKeyCount = 0;
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
  fetchKeyedTotal();
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
    theme: 'legacy',
    columnDefs: buildColumnDefs(rule),
    rowData: [],
    getRowId: (params) => String(params.data.row_id),
    rowSelection: 'single',
    suppressCellFocus: true,
    animateRows: true,
    defaultColDef: {
      flex: 1,
      minWidth: 110,
      sortable: false,       // 서버 정렬(row_id asc) 고정 — 컨베이어는 항상 앞에서 소비
      filter: false,
      editable: false,       // 입력은 [B] 컨베이어에서만 (인라인 편집과 흐름 충돌 방지)
      resizable: true,
    },
    onSelectionChanged: () => {
      if (!S.gridApi) return;
      const selected = S.gridApi.getSelectedNodes();
      if (selected.length > 0) renderDetail(selected[0].data);
    },
  };
  S.gridApi = createGrid(el('worklist-grid'), gridOptions);
}

// ── 워크리스트 청크 페칭 (항상 skip=0: 완료 행은 blank 필터에서 자동 이탈) ──
// 큐 진입 조건은 서버가 단일 조성한다(rule.queue_filters: **target blank뿐**).
// 판단키 notBlank는 2026-08-04 사용자 재정으로 여기서 빠졌다 — 진행률 분모는 무필터
// 전체 행이라, 잔여가 판단키까지 요구하면 두 수가 다른 모집단을 세어 판단키 빈 행이
// 「답한 것」으로 계산됐다(N36: 데이터 변경 0, 설정 한 줄로 33% → 100%).
// 그 행들은 이제 워크리스트에 **뜬다**(숨기면 인제션 결함이 영영 안 고쳐진다).
function buildBlankFilters(rule) {
  if (rule.queue_filters) return rule.queue_filters;
  // fallback (구버전 서버): target blank만 — 지금은 서버 조성과 같은 형태다
  const filters = {};
  (rule.target_fields || []).forEach(f => {
    filters[f] = { type: 'blank' };
  });
  return filters;
}

// 이 행이 판단키를 전부 갖췄는가 = 사람이 근거를 조회할 수 있는가.
// 참조뷰는 판단키 **값으로** 조회되므로 빈 값은 근거를 찾지 못한다.
function hasDecisionKeys(row, rule) {
  return (rule.decision_key || []).every(col => String(cellVal(row, col)).trim() !== '');
}

// 컨베이어 순서: 처리 가능한 행 먼저, 판단 불가(판단키 없음) 행은 뒤로.
// 서버는 row_id asc로 주고 그 순서는 **각 구획 안에서 그대로 보존**된다 — 컨베이어의
// "앞에서 소비한다"는 불변식은 유지되고, 앞을 막는 것만 내려간다. 정렬 컨트롤도
// 모드도 만들지 않는다(순서 규칙 자체가 바뀐 것이지 사용자가 고르는 것이 아니다).
function partitionQueueRows(rows, rule) {
  const keyed = [], keyless = [];
  rows.forEach(r => (hasDecisionKeys(r, rule) ? keyed : keyless).push(r));
  return keyed.concat(keyless);
}

// 판단키 없는 행이 시작되는 버퍼 인덱스 (없으면 버퍼 끝).
// 보충(refill)으로 들어온 신규 행을 이 위치에 끼워 넣어 구획을 유지한다.
function blankKeyBoundaryIndex() {
  if (!S.gridApi || !S.rule) return 0;
  const count = S.gridApi.getDisplayedRowCount();
  for (let i = 0; i < count; i++) {
    const node = S.gridApi.getDisplayedRowAtIndex(i);
    if (node && node.data && !hasDecisionKeys(node.data, S.rule)) return i;
  }
  return count;
}

async function fetchWorklist(reset) {
  if (!S.rule || S.isFetching) return;
  const token = S.sessionToken;
  S.isFetching = true;
  el('worklist-meta').textContent = '로딩 중...';

  const filters = encodeURIComponent(JSON.stringify(buildBlankFilters(S.rule)));
  const url = `${API_BASE}/tables/${encodeURIComponent(S.rule.derived_table)}/data` +
    `?skip=0&limit=${pageLimit}&order_by=row_id&order_desc=false&filters=${filters}`;

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
    el('worklist-meta').textContent =
      `버퍼 ${S.gridApi.getDisplayedRowCount().toLocaleString()}건 · ${ms}ms`;

    updateHeaderStats();
    updateWorklistOverlay();

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
// 무필터이므로 잔여(queue_filters = target blank)와 같은 모집단을 센다 — 이 정합이
// N36의 수리 그 자체다. 여기에 필터를 다시 붙이면 100% 결함이 되돌아온다.
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

// 「판단키 없음 N건」의 분해: 잔여(queue_filters) - 판단키 보유 잔여(keyed_queue_filters).
// 두 술어 모두 서버가 조성한 **논리곱** 필터라 기존 `/tables/{t}/data` DSL이 그대로
// 번역한다 — 신규 엔드포인트 없음. (직접 세려면 판단키 컬럼 간 OR이 필요한데 필터 DSL은
// 한 컬럼 안의 조합만 표현한다. 그래서 차분으로 얻는다.)
async function fetchKeyedTotal() {
  if (!S.rule || !S.rule.keyed_queue_filters) {
    S.totalKeyed = null;      // 구버전 서버: 「모른다」 — 0으로 지어내지 않는다
    S.blankKeyCount = 0;
    return;
  }
  const token = S.sessionToken;
  try {
    const filters = encodeURIComponent(JSON.stringify(S.rule.keyed_queue_filters));
    const res = await fetch(`${API_BASE}/tables/${encodeURIComponent(S.rule.derived_table)}` +
      `/data?skip=0&limit=1&filters=${filters}`);
    if (!res.ok) return;
    const result = await res.json();
    if (token !== S.sessionToken) return;
    S.totalKeyed = result.total;
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

  // 「판단키 없음 N건」 — 이름 붙인 집계. 0이면 숨긴다(없는 문제를 세우지 않는다).
  // 서버가 keyed_queue_filters를 안 주면 S.totalKeyed는 null로 남고 배지도 뜨지 않는다:
  // 「0건」이라고 말하는 것과 「확인 못 했다」는 다른 사실이다.
  S.blankKeyCount = (S.totalKeyed === null) ? 0 : Math.max(0, remaining - S.totalKeyed);
  const bkBadge = el('blankkey-badge');
  if (bkBadge) {
    bkBadge.style.display = S.blankKeyCount > 0 ? 'inline-block' : 'none';
    bkBadge.textContent = `⚠️ 판단키 없음 ${S.blankKeyCount.toLocaleString()}건`;
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
  const count = S.gridApi ? S.gridApi.getDisplayedRowCount() : 0;
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
  const inputsBody = el('target-inputs');
  inputsBody.innerHTML = '';
  (S.rule.target_fields || []).forEach((field, idx) => {
    const wrap = document.createElement('div');
    wrap.className = 'target-field-row';
    const label = document.createElement('label');
    label.className = 'target-field-label';
    label.textContent = field;
    label.htmlFor = `target-input-${idx}`;
    const input = document.createElement('input');
    input.type = 'text';
    input.id = `target-input-${idx}`;
    input.className = 'glass-input target-input';
    input.dataset.field = field;
    input.placeholder = `${field} 입력 후 Enter`;
    input.autocomplete = 'off';
    input.addEventListener('keydown', onInputKeydown);
    wrap.appendChild(label);
    wrap.appendChild(input);
    inputsBody.appendChild(wrap);
  });

  const first = inputsBody.querySelector('input');
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
    el('target-inputs').querySelectorAll('input').forEach(i => { i.value = ''; });
    const first = el('target-inputs').querySelector('input');
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

// ── 저장 → 낙관적 제거 → 다음 항목 (컨베이어 핵심 루프) ────
async function saveCurrent() {
  if (S.saving || !S.rule || S.selectedRowId === null || !S.gridApi) return;

  const inputs = Array.from(el('target-inputs').querySelectorAll('input'));
  if (inputs.length === 0) return;

  const updates = {};
  for (const input of inputs) {
    const val = input.value.trim();
    if (val === '') {
      showToast(`'${input.dataset.field}' 값을 입력해 주세요.`, 'warning');
      input.focus();
      return;
    }
    updates[input.dataset.field] = val;
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

    if (token !== S.sessionToken) return; // 저장 중 규칙 전환 → UI 반영 생략

    // 낙관적 반영: 결손 필터에서 이탈했으므로 버퍼에서 제거
    const liveNode = S.gridApi.getRowNode(String(rowId));
    // 판단키 보유 여부는 **제거 전에** 읽는다 — 두 카운트를 함께 감산해야
    // 「판단키 없음 N건」이 저장 한 번마다 1씩 부풀지 않는다.
    const wasKeyed = liveNode && liveNode.data ? hasDecisionKeys(liveNode.data, S.rule) : true;
    if (liveNode) S.gridApi.applyTransaction({ remove: [liveNode.data] });
    S.totalBlank = Math.max(0, S.totalBlank - 1);
    if (wasKeyed && S.totalKeyed !== null) S.totalKeyed = Math.max(0, S.totalKeyed - 1);
    S.doneCount += 1;

    flashSaved();
    updateHeaderStats();
    updateWorklistOverlay();
    el('worklist-meta').textContent =
      `버퍼 ${S.gridApi.getDisplayedRowCount().toLocaleString()}건`;

    // 다음 항목 자동 선택 (제거된 자리 승계) + 버퍼 보충
    selectDisplayedIndex(removedIndex);
    refillIfNeeded();
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

// 서버 LIMIT(기본 200, 최대 1000) 이하 행만 오므로 경량 HTML 테이블로 충분 (읽기 전용)
function renderRefTable(payload) {
  const wrap = el('reference-table-wrap');
  el('reference-meta').textContent = `${payload.rows.length.toLocaleString()}건 · ${payload.ms}ms`;

  if (payload.rows.length === 0) {
    wrap.style.display = 'none';
    showRefStatus('🫙', '근거 데이터 없음', '이 판단키에 해당하는 참조 데이터가 없습니다.');
    return;
  }

  hideRefStatus();
  wrap.innerHTML = '';
  const table = document.createElement('table');
  table.className = 'reference-table';

  const thead = document.createElement('thead');
  const headRow = document.createElement('tr');
  payload.columns.forEach(colName => {
    const th = document.createElement('th');
    th.textContent = colName; // XSS 안전: textContent만 사용
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement('tbody');
  payload.rows.forEach(r => {
    const tr = document.createElement('tr');
    payload.columns.forEach((_, i) => {
      const td = document.createElement('td');
      const v = r[i];
      if (v === null || v === undefined) {
        td.textContent = '-';
        td.className = 'ref-null';
      } else {
        td.textContent = String(v);
      }
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);

  wrap.appendChild(table);
  wrap.scrollTop = 0;
  wrap.style.display = 'block';
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
