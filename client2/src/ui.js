import { API_BASE, CURRENT_USER, pageLimit } from './config.js';
import { state, isVirtualColumn } from './state.js';
import { elements } from './dom.js';
import { getLocalTimeString } from './utils.js';
import { updateGridSortState } from './grid.js';
import { ensureCellObject } from './grid.js';
import { snapshot, commitIfRecorded } from './effort_meter.js';

export function setupBeforeUnloadWarning() {
  window.onbeforeunload = (e) => {
    if (state.txModeActive && Object.keys(state.pendingTxEdits).length > 0) {
      e.preventDefault();
      e.returnValue = '저장되지 않은 변경 사항이 있습니다. 정말 페이지를 벗어나시겠습니까?';
      return e.returnValue;
    }
  };
}

export function updateSelectedCellUI() {
  if (!state.selectedCell) {
    elements.selectedCellInfo.innerHTML = 'Select a cell to view history';
    return;
  }

  const isSystem = ['created_at', 'updated_at', 'row_id', 'is_graph_synced', 'needs_graph_rollback', 'graph_synced_at'].includes(state.selectedCell.colId);
  // [Virtual join] The same read-only slot, filled with the one thing the write refusal
  // cannot say: WHICH table to go and fix. No new element — this line already existed for
  // system columns and only ever shows for the one selected cell.
  const virt = (state.currentVirtualColumns || [])
    .find(vc => vc && vc.name === state.selectedCell.colId);
  elements.selectedCellInfo.innerHTML = `
    <div><strong>Row ID:</strong> <span style="color:var(--color-secondary)">${state.selectedCell.rowId}</span></div>
    <div><strong>Column:</strong> <span style="color:var(--color-primary)">${state.selectedCell.colId.toUpperCase()}</span></div>
    <div><strong>Current Value:</strong> <code>${state.selectedCell.value !== null ? state.selectedCell.value : 'NULL'}</code></div>
    ${isSystem ? '<div style="color:var(--text-dim);margin-top:4px;font-style:italic">Read-only System Column</div>' : ''}
    ${virt ? `<div style="color:var(--text-dim);margin-top:4px;font-style:italic">읽기 전용 조인 컬럼 — 원본 '${virt.right_table}'</div>` : ''}
  `;
}

export function updateTxModeUI() {
  const count = Object.keys(state.pendingTxEdits).length;
  if (state.txModeActive) {
    if (elements.txModeToggle) {
      elements.txModeToggle.checked = true;
    }
    if (elements.txApplyBtn) {
      elements.txApplyBtn.style.display = count > 0 ? 'inline-block' : 'none';
      elements.txApplyBtn.textContent = `Apply (${count})`;
    }
    if (elements.txDiscardBtn) {
      elements.txDiscardBtn.style.display = count > 0 ? 'inline-block' : 'none';
    }
    if (elements.txPendingBadge) {
      elements.txPendingBadge.style.display = count > 0 ? 'inline-block' : 'none';
      elements.txPendingBadge.textContent = `⚡ Unsaved: ${count}`;
    }
    if (elements.performanceLog) {
      elements.performanceLog.textContent = count > 0 
        ? `Tx Mode active: ${count} edits pending` 
        : 'Tx Mode active (No pending edits)';
    }
  } else {
    if (elements.txModeToggle) {
      elements.txModeToggle.checked = false;
    }
    if (elements.txApplyBtn) {
      elements.txApplyBtn.style.display = 'none';
    }
    if (elements.txDiscardBtn) {
      elements.txDiscardBtn.style.display = 'none';
    }
    if (elements.txPendingBadge) {
      elements.txPendingBadge.style.display = 'none';
    }
    if (elements.performanceLog) {
      elements.performanceLog.textContent = 'Ready';
    }
  }

  // Toggle ag-grid cell class rules (dirty dashed border)
  if (state.gridApi) {
    state.gridApi.refreshCells({ force: true });
  }
}

export function setTransactionFilter(txId) {
  state.currentTransactionId = txId;
  if (txId) {
    if (elements.bannerTxId) elements.bannerTxId.textContent = txId;
    if (elements.txFilterBanner) elements.txFilterBanner.style.display = 'flex';
  } else {
    if (elements.bannerTxId) elements.bannerTxId.textContent = '';
    if (elements.txFilterBanner) elements.txFilterBanner.style.display = 'none';
  }

  // Refresh history timeline highlights to match the new filter context
  const timelineItems = elements.timeline.querySelectorAll('.timeline-item');
  timelineItems.forEach(li => {
    const itemTxId = li.dataset.txId || (li.querySelector('.filter-tx-btn')?.dataset.txId);
    if (itemTxId && itemTxId === state.currentTransactionId) {
      li.classList.add('active-tx-log');
    } else {
      li.classList.remove('active-tx-log');
    }
  });

  // Reload data from skip = 0
  import('./api.js').then(({ fetchData }) => {
    fetchData(true);
  });
}

export async function applyValueToSelectedRange(newValue) {
  if (!state.gridApi) return;

  let cellsToUpdate = Object.values(state.selectedCellsMap);
  if (cellsToUpdate.length === 0) {
    if (!state.dragStartCell || !state.dragEndCell) return;

    const startIdx = state.visibleColIndexMap[state.dragStartCell.colId];
    const endIdx = state.visibleColIndexMap[state.dragEndCell.colId];
    if (startIdx === undefined || endIdx === undefined) return;

    const minColIdx = Math.min(startIdx, endIdx);
    const maxColIdx = Math.max(startIdx, endIdx);
    const minRow = Math.min(state.dragStartCell.rowIndex, state.dragEndCell.rowIndex);
    const maxRow = Math.max(state.dragStartCell.rowIndex, state.dragEndCell.rowIndex);

    const visibleColIds = Object.keys(state.visibleColIndexMap);
    const targetCols = visibleColIds.filter((_, idx) => idx >= minColIdx && idx <= maxColIdx && _ !== '#');
    for (let rIdx = minRow; rIdx <= maxRow; rIdx++) {
      targetCols.forEach(colId => {
        cellsToUpdate.push({ rowIndex: rIdx, colId });
      });
    }
  }

  if (cellsToUpdate.length === 0) return;

  const updatesArray = [];
  const updateMapByRow = {};

  cellsToUpdate.forEach(cell => {
    const { rowIndex, colId } = cell;
    const isSystem = ['created_at', 'updated_at', 'row_id', 'id', 'updated_by', '#', 'is_graph_synced', 'needs_graph_rollback', 'graph_synced_at'].includes(colId);
    if (isSystem) return;
    // [Virtual join] The third write funnel that builds updates from grid column ids
    // (with the two paste branches and the clear path in clipboard.js). Ctrl+Enter bulk
    // fill spans whatever rectangle is selected, so it reaches an appended virtual column
    // the same way an MxN paste does, and the server's refusal is batch-level.
    if (isVirtualColumn(colId)) return;

    const rowNode = state.gridApi.getDisplayedRowAtIndex(rowIndex);
    if (!rowNode || !rowNode.data) return;
    const rowId = rowNode.data.row_id;

    if (!updateMapByRow[rowId]) {
      updateMapByRow[rowId] = { rowNode, updates: {} };
    }
    updateMapByRow[rowId].updates[colId] = newValue;
  });

  Object.keys(updateMapByRow).forEach(rowId => {
    const item = updateMapByRow[rowId];
    if (state.txModeActive) {
      Object.keys(item.updates).forEach(colId => {
        const key = `${rowId}_${colId}`;
        if (!state.pendingTxEdits[key]) {
          const oldValue = item.rowNode.data.data?.[colId]?.value !== undefined ? item.rowNode.data.data[colId].value : '';
          const oldIsOverwrite = item.rowNode.data.data?.[colId]?.is_overwrite === true;
          state.pendingTxEdits[key] = {
            rowId,
            colId,
            newValue: item.updates[colId],
            oldValue: oldValue,
            oldIsOverwrite: oldIsOverwrite,
            data: item.rowNode.data
          };
        } else {
          state.pendingTxEdits[key].newValue = item.updates[colId];
        }

        const latestNode = state.gridApi.getRowNode(rowId);
        const latestData = latestNode ? latestNode.data : item.rowNode.data;
        if (latestData) {
          ensureCellObject(latestData, colId);
          latestData.data[colId].value = item.updates[colId];
        }
      });
    } else {
      updatesArray.push({
        row_id: rowId,
        updates: item.updates,
        source_name: 'user',
        updated_by: CURRENT_USER
      });
    }
  });

  if (state.txModeActive) {
    if (Object.keys(updateMapByRow).length > 0) {
      if (state.selectedCell && updateMapByRow[state.selectedCell.rowId] && updateMapByRow[state.selectedCell.rowId].updates[state.selectedCell.colId] !== undefined) {
        state.selectedCell.value = updateMapByRow[state.selectedCell.rowId].updates[state.selectedCell.colId];
        updateSelectedCellUI();
      }

      updateTxModeUI();
      state.gridApi.refreshCells({ force: true });
      setupBeforeUnloadWarning();
      elements.performanceLog.textContent = `Staged range value edit: ${Object.keys(state.pendingTxEdits).length} total pending edits`;
    }
    return;
  }

  if (updatesArray.length === 0) return;

  elements.performanceLog.textContent = `Updating ${updatesArray.reduce((acc, cur) => acc + Object.keys(cur.updates).length, 0)} cells...`;
  const startTime = performance.now();

  try {
    const res = await fetch(`${API_BASE}/tables/${state.currentTable}/data/updates`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        updates: updatesArray,
        silent: false,
        // V1 instrument: optional field. Raw counts only — the server weights at query time.
        effort: snapshot()
      })
    });

    if (res.ok) {
      state.pageCache.clear();
      const result = await res.json();
      // V1 instrument: reset ONLY when the server confirms it recorded the effort — a no-op
      // save returns 200 and records nothing, so committing there erases real effort.
      commitIfRecorded(result);
      const saveTime = (performance.now() - startTime).toFixed(1);
      elements.performanceLog.textContent = `Updated range cells in ${saveTime}ms (${result.change_count} cells updated)`;

      updatesArray.forEach(item => {
        const rowNode = state.gridApi.getRowNode(item.row_id);
        if (rowNode) {
          const latestData = rowNode.data;
          if (latestData) {
            Object.keys(item.updates).forEach(colId => {
              ensureCellObject(latestData, colId);
              latestData.data[colId].value = item.updates[colId];
              latestData.data[colId].is_overwrite = true;
            });
            latestData.updated_at = getLocalTimeString();
          }
        }
      });

      if (state.selectedCell && updateMapByRow[state.selectedCell.rowId] && updateMapByRow[state.selectedCell.rowId].updates[state.selectedCell.colId] !== undefined) {
        state.selectedCell.value = updateMapByRow[state.selectedCell.rowId].updates[state.selectedCell.colId];
        updateSelectedCellUI();
      }

      updateGridSortState();
      state.gridApi.refreshCells({ force: true });
    } else {
      const errData = await res.json().catch(() => ({}));
      const errMsg = errData.detail || 'Save failed';
      throw new Error(errMsg);
    }
  } catch (err) {
    console.error('Bulk cell update failed', err);
    alert(`범위 수정 사항 저장 실패: ${err.message}`);
    elements.performanceLog.textContent = '❌ Range edit failed to save';
  }
}

export function updatePageCacheOnUpsert(items) {
  if (!items || items.length === 0) return;
  const isSortLatest = elements.sortLatestToggle && elements.sortLatestToggle.checked;

  items.forEach(item => {
    let foundAnywhere = false;

    for (const [skip, cached] of state.pageCache.entries()) {
      const idx = cached.data.findIndex(r => r.row_id === item.row_id);
      if (idx !== -1) {
        foundAnywhere = true;
        const oldRowData = cached.data[idx];
        cached.data[idx] = {
          ...oldRowData,
          created_at: item.created_at || oldRowData.created_at,
          updated_at: item.updated_at || oldRowData.updated_at,
          data: {
            ...oldRowData.data,
            ...item.data
          }
        };
      }
    }

    if (!foundAnywhere) {
      for (const [skip, cached] of state.pageCache.entries()) {
        cached.total += 1;

        if (skip === 0 && isSortLatest) {
          const nowStr = getLocalTimeString();
          const newItem = {
            ...item,
            created_at: item.created_at || nowStr,
            updated_at: item.updated_at || nowStr
          };

          if (!cached.data.some(r => r.row_id === newItem.row_id)) {
            cached.data.unshift(newItem);
            if (cached.data.length > pageLimit) {
              cached.data.pop();
            }
          }
        }
      }
    }
  });
}

// ── Enrichment Queue "결손 N건" 배지 (phase 3) ─────────────────────────────
// 규칙 목록은 페이지 로드 후 최초 필요 시 1회만 페치·캐시한다.
// 규칙 API 미배포(404 등)·빈 배열·네트워크 오류 → 배지 기능 전체 무음 비활성.
let enrichmentRulesPromise = null;
const enrichmentCountCache = new Map(); // derived_table -> { total, ts }
const ENRICHMENT_COUNT_TTL = 5000; // 서버측 5초 카운트 캐시와 동일 주기

function loadEnrichmentRules() {
  if (!enrichmentRulesPromise) {
    enrichmentRulesPromise = fetch(`${API_BASE}/enrichment/rules`)
      .then(res => (res.ok ? res.json() : { rules: [] }))
      .then(data => (Array.isArray(data.rules) ? data.rules.filter(r => r && r.derived_table) : []))
      .catch(() => []);
  }
  return enrichmentRulesPromise;
}

function findEnrichmentRule(rules, tableName) {
  if (!tableName) return null;
  return rules.find(r => r.source_table === tableName || r.derived_table === tableName) || null;
}

// Fire-and-forget: 호출부는 await 하지 않는다(테이블 전환·WS 흐름 블로킹 금지).
export async function updateEnrichmentBadge(options = {}) {
  try {
    const badge = elements.enrichmentBadge;
    if (!badge) return;

    const table = state.currentTable;
    const rules = await loadEnrichmentRules();
    const rule = findEnrichmentRule(rules, table);
    if (!rule) {
      badge.style.display = 'none';
      return;
    }

    let total;
    const cached = enrichmentCountCache.get(rule.derived_table);
    if (!options.force && cached && (Date.now() - cached.ts) < ENRICHMENT_COUNT_TTL) {
      total = cached.total;
    } else {
      // 큐 진입 조건은 서버 단일 조성(queue_filters) — 워크리스트/어드민 카운트와 동일 수치 보장
      const filters = rule.queue_filters
        || Object.fromEntries((rule.target_fields || []).map(f => [f, { type: 'blank' }]));
      const url = `${API_BASE}/tables/${encodeURIComponent(rule.derived_table)}/data` +
        `?skip=0&limit=1&filters=${encodeURIComponent(JSON.stringify(filters))}`;
      const res = await fetch(url);
      if (!res.ok) { badge.style.display = 'none'; return; }
      const result = await res.json();
      total = result.total || 0;
      enrichmentCountCache.set(rule.derived_table, { total, ts: Date.now() });
    }

    // 응답 대기 중 테이블이 바뀌었으면 stale 결과 폐기 (다음 switchTable 훅이 갱신)
    if (state.currentTable !== table) return;

    if (total > 0) {
      badge.textContent = `🧩 결손 ${total}건`;
      badge.dataset.rule = rule.name || '';
      badge.title = `${rule.derived_table}에 결손 ${total}건 — 클릭하여 Enrichment Queue 열기`;
      badge.style.display = 'inline-block';
    } else {
      badge.style.display = 'none';
    }
  } catch (err) {
    // 무음 실패가 설계 목표: 배지가 메인 그리드 흐름을 방해해선 안 된다
    const badge = elements.enrichmentBadge;
    if (badge) badge.style.display = 'none';
  }
}

// WS 델타 수신 훅: 이벤트 테이블이 현재 뷰 관련 규칙의 derived 테이블일 때만
// 500ms 디바운스로 카운트를 강제 재조회한다. (동기 시그니처 — 호출부 무부담)
let enrichmentWsTimer = null;
export function notifyEnrichmentTableEvent(tableName) {
  if (!tableName || !enrichmentRulesPromise) return; // 규칙 미로드 = 배지 미사용 상태
  enrichmentRulesPromise.then(rules => {
    const active = findEnrichmentRule(rules, state.currentTable);
    if (!active || tableName !== active.derived_table) return;
    clearTimeout(enrichmentWsTimer);
    enrichmentWsTimer = setTimeout(() => updateEnrichmentBadge({ force: true }), 500);
  }).catch(() => { });
}

export function updatePageCacheOnDelete(rowIds) {
  if (!rowIds || rowIds.length === 0) return;

  rowIds.forEach(rowId => {
    for (const [skip, cached] of state.pageCache.entries()) {
      const originalLength = cached.data.length;
      cached.data = cached.data.filter(r => r.row_id !== rowId);

      const removedCount = originalLength - cached.data.length;
      if (removedCount > 0) {
        cached.total -= removedCount;
      } else {
        cached.total -= 1;
      }
      if (cached.total < 0) cached.total = 0;
    }
  });
}
