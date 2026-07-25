// ============================================================
// Enrichment Queue Page Orchestrator (Phase 1)
// - admin.js / map_editor.js 선례: 자체 모듈 지역 상태 (state.js/dom.js/api.js 미임포트)
// - 재사용: config.js / utils.js / AG-Grid Community
// - 계약(확정): GET /enrichment/rules
//   { "rules": [ { name, source_table, derived_table, decision_key[],
//                  target_fields[], list_columns[], reference_views:[{label}] } ] }
// - 워크리스트: GET /tables/{derived}/data + blank 필터 청크 페칭 (전량 로드 금지)
// - 저장: PUT /tables/{derived}/data/updates (source_name='user' → priority 0)
// ============================================================
import { createGrid, ModuleRegistry, AllCommunityModule } from 'ag-grid-community';
import 'ag-grid-community/styles/ag-grid.css';
import 'ag-grid-community/styles/ag-theme-quartz.css';
import { API_BASE, CURRENT_USER, pageLimit } from './config.js';
import { showToast } from './utils.js';

ModuleRegistry.registerModules([AllCommunityModule]);

// 컨베이어 버퍼 보충 임계치: 남은 행이 이보다 적으면 skip=0 재페치
const REFILL_THRESHOLD = 50;

// ── 지역 상태 (싱글턴) ─────────────────────────────────────
const S = {
  rules: [],
  rule: null,
  sessionToken: null,   // 규칙 전환/새로고침마다 재발급되는 세션 가드 UUID
  gridApi: null,
  totalBlank: 0,        // 서버 기준 잔여 결손 키 수 (저장 시 로컬 감산)
  totalAll: null,       // 파생 테이블 전체 유니크 키 수 (진행률 분모)
  doneCount: 0,         // 이번 세션에서 채운 건수
  isFetching: false,
  exhausted: false,     // 서버에 버퍼 밖 잔여분이 없음
  saving: false,
  selectedRowId: null,
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
  S.isFetching = false;
  S.exhausted = false;
  S.selectedRowId = null;

  el('rule-select').value = rule.name;
  el('conveyor-meta').textContent = `${rule.derived_table}`;
  renderReferencePlaceholder(rule);
  showConveyorEmpty();
  rebuildGrid(rule);
  updateHeaderStats();

  fetchWorklist(true);
  fetchTotalAll();
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
function buildBlankFilters(rule) {
  const filters = {};
  (rule.target_fields || []).forEach(f => {
    filters[f] = { type: 'blank' };
  });
  return filters;
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
      S.gridApi.setGridOption('rowData', result.data);
    } else {
      // skip=0 재페치는 버퍼 잔존분과 겹침 → row_id로 dedupe 후 신규만 추가
      const known = new Set();
      S.gridApi.forEachNode(n => known.add(String(n.data.row_id)));
      const fresh = result.data.filter(r => !known.has(String(r.row_id)));
      if (fresh.length > 0) S.gridApi.applyTransaction({ add: fresh });
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

// 진행률 분모: 파생 테이블 전체 키 수 (limit=1, total만 사용 — 서버 5초 캐시)
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

  if (S.totalAll !== null && S.totalAll > 0) {
    const filled = Math.max(0, S.totalAll - remaining);
    const pct = Math.round((filled / S.totalAll) * 100);
    el('progress-text').textContent = `${filled.toLocaleString()} / ${S.totalAll.toLocaleString()} keys`;
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
}

function renderDetail(row) {
  if (!row || !S.rule) return;
  S.selectedRowId = row.row_id;
  el('conveyor-empty').style.display = 'none';
  el('conveyor-detail').style.display = 'flex';

  // 판단키 (XSS 안전: textContent만 사용)
  const keyBody = el('decision-key-body');
  keyBody.innerHTML = '';
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

    if (token !== S.sessionToken) return; // 저장 중 규칙 전환 → UI 반영 생략

    // 낙관적 반영: 결손 필터에서 이탈했으므로 버퍼에서 제거
    const liveNode = S.gridApi.getRowNode(String(rowId));
    if (liveNode) S.gridApi.applyTransaction({ remove: [liveNode.data] });
    S.totalBlank = Math.max(0, S.totalBlank - 1);
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

// ── [C] 참조뷰 placeholder (단계②에서 실데이터 연동) ───────
function renderReferencePlaceholder(rule) {
  const tabs = el('reference-tabs');
  tabs.innerHTML = '';
  (rule.reference_views || []).forEach(view => {
    const tab = document.createElement('span');
    tab.className = 'reference-tab';
    tab.textContent = view.label || '(unnamed)';
    tab.title = '단계②에서 활성화됩니다';
    tabs.appendChild(tab);
  });
}

// ── 초기화 ─────────────────────────────────────────────────
async function init() {
  el('rule-select').addEventListener('change', (e) => {
    const rule = S.rules.find(r => r.name === e.target.value);
    if (rule) selectRule(rule);
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
