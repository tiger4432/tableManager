// ============================================================
// trace_launch.js — index 그리드 → G2 추적 리포트(trace.html) 진입점
// - GET /graph/mapping-summary 로 현재 테이블의 그래프 매핑 여부 판정
//   (매핑 없으면 진입 UI 숨김 — 지시서 계약: {tables:[{table,node_label,identity_columns}]})
// - 선택 행들의 identity_columns 값(셀 계약 {value,...} — ensureCellObject 경유)을
//   composeIdentity로 조립해 시드 목록 생성 → trace.html?seeds=<urlencoded JSON> 새 탭
// - 시드 상한 SEED_CAP(20) — 초과 시 토스트 안내 후 앞 20개만
// ============================================================
import { API_BASE } from './config.js';
import { state } from './state.js';
import { elements } from './dom.js';
import { showToast } from './utils.js';
import { ensureCellObject } from './grid.js';
import { composeIdentity, capSeeds, SEED_CAP } from './trace_core.js';

// table → {table, node_label, identity_columns} (fetch 실패 시 null = 전부 숨김)
let mappingByTable = null;

function currentMapping() {
  if (!mappingByTable || !state.currentTable) return null;
  return mappingByTable.get(state.currentTable) || null;
}

/** 진입 UI(툴바 버튼 + 컨텍스트 메뉴 항목) 표시/숨김 갱신 */
export function updateTraceEntryVisibility() {
  const show = !!currentMapping();
  if (elements.traceBtn) elements.traceBtn.style.display = show ? 'inline-block' : 'none';
  if (elements.menuTrace) elements.menuTrace.style.display = show ? '' : 'none';
}

/**
 * mapping-summary 재조회 + 진입 UI 갱신.
 * fire-and-forget 용도(테이블 전환을 블로킹하지 않음, 실패 무음 → 숨김).
 */
export async function refreshTraceEntry() {
  try {
    const res = await fetch(`${API_BASE}/graph/mapping-summary`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const tables = Array.isArray(data.tables) ? data.tables : [];
    mappingByTable = new Map(
      tables
        .filter((t) => t && t.table && t.node_label
          && Array.isArray(t.identity_columns) && t.identity_columns.length > 0)
        .map((t) => [t.table, t]),
    );
  } catch (err) {
    mappingByTable = null; // 그래프 미가동/미배포 환경 — 진입점 자체를 숨긴다
  }
  updateTraceEntryVisibility();
}

/** 선택 행 → 시드 변환 → trace.html 새 탭 (진입 본체) */
export function openTraceForSelection() {
  const mapping = currentMapping();
  if (!mapping) {
    showToast('현재 테이블은 그래프 매핑이 없어 추적할 수 없습니다.', 'warning');
    return;
  }
  if (!state.gridApi) return;
  const rows = state.gridApi.getSelectedRows();
  if (!rows.length) {
    showToast('추적할 행을 먼저 선택하세요.', 'warning');
    return;
  }

  const rawSeeds = [];
  let skipped = 0;
  for (const row of rows) {
    // 셀 계약: data[col] = {value, is_overwrite, priority_source} — ensureCellObject 정규화 경유
    const values = mapping.identity_columns.map((col) => {
      ensureCellObject(row, col);
      return row.data[col].value;
    });
    const identity = composeIdentity(values);
    if (identity === null) { skipped++; continue; }
    rawSeeds.push({ label: mapping.node_label, identity });
  }

  if (!rawSeeds.length) {
    showToast(`선택 행에서 유효한 식별자를 만들 수 없습니다 (${skipped}행 결손)`, 'warning');
    return;
  }
  const { seeds, dropped } = capSeeds(rawSeeds, SEED_CAP);
  if (dropped > 0) {
    showToast(`시드 상한 ${SEED_CAP}개 — 앞 ${SEED_CAP}개만 추적합니다 (${dropped}개 제외)`, 'warning');
  }
  if (skipped > 0) {
    showToast(`식별자 결손으로 ${skipped}개 행이 제외되었습니다`, 'info');
  }

  window.open(`trace.html?seeds=${encodeURIComponent(JSON.stringify(seeds))}`, '_blank');
}

/** 진입점 초기화 — main.js init()에서 1회 호출 */
export function initTraceEntry() {
  if (elements.traceBtn) {
    elements.traceBtn.addEventListener('click', openTraceForSelection);
  }
  if (elements.menuTrace) {
    elements.menuTrace.addEventListener('click', () => {
      if (elements.contextMenu) elements.contextMenu.style.display = 'none';
      openTraceForSelection();
    });
  }
  refreshTraceEntry(); // fire-and-forget
}
