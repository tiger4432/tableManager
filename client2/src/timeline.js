import { API_BASE, pageLimit } from './config.js';
import { state } from './state.js';
import { elements } from './dom.js';
import { switchTable, fetchData } from './api.js';
import { setTransactionFilter, updateSelectedCellUI } from './ui.js';
import { updateGridSortState, updateLoadedCount, updatePaginationUI } from './grid.js';
import { countNav, ROUTES } from './effort_meter.js';

// Feature 3: Load audit log history from API
export async function loadHistory() {
  if (state.activeHistoryTab === 'global') {
    elements.timeline.innerHTML = '<li class="timeline-empty">Loading global history...</li>';
    try {
      const res = await fetch(`${API_BASE}/audit_logs/recent?limit_groups=100`);
      const logs = await res.json();
      state.globalHistoryData = logs;
      renderGlobalTimeline();
    } catch (err) {
      console.error('Failed to load global history', err);
      elements.timeline.innerHTML = '<li class="timeline-empty" style="color:var(--color-danger)">Failed to load global history log</li>';
    }
    return;
  }

  if (!state.selectedCell) {
    elements.timeline.innerHTML = '<li class="timeline-empty">Select a cell to view history</li>';
    return;
  }

  elements.timeline.innerHTML = '<li class="timeline-empty">Loading history...</li>';

  const { rowId, colId } = state.selectedCell;
  let url = `${API_BASE}/tables/${state.currentTable}/rows/${rowId}/history`;

  if (state.activeHistoryTab === 'cell') {
    url = `${API_BASE}/tables/${state.currentTable}/rows/${rowId}/cells/${colId}/history`;
  }

  try {
    const res = await fetch(url);
    const logs = await res.json();
    state.cellRowHistoryData = logs || [];
    renderTimeline(state.cellRowHistoryData);
  } catch (err) {
    console.error('Failed to load history', err);
    elements.timeline.innerHTML = '<li class="timeline-empty" style="color:var(--color-danger)">Failed to load history log</li>';
  }
}

// Create single timeline list item DOM element
export function createTimelineItemDom(log) {
  const li = document.createElement('li');
  li.className = 'timeline-item';
  li.style.cursor = 'pointer';

  const isUser = log.updated_by !== 'system';
  li.classList.add(isUser ? 'user-change' : 'system-change');
  if (log.is_row_deleted) {
    li.classList.add('deleted-row-log');
  }

  const isCurrentTx = log.transaction_id && log.transaction_id === state.currentTransactionId;
  if (isCurrentTx) {
    li.classList.add('active-tx-log');
  }

  const dateStr = new Date(log.timestamp).toLocaleString();

  li.innerHTML = `
    <div class="timeline-time">${dateStr}</div>
    <div class="timeline-card">
      <div class="timeline-user">
        <span class="user-tag">${log.updated_by}</span>
        <span class="source-tag">${log.source_name}</span>
      </div>
      <div class="timeline-changes">
        <div class="change-detail">
          <span class="change-field">${log.column_name}</span>
          <div class="change-values">
            <span class="val-old">${formatVal(log.old_value, true)}</span>
            <span class="val-arrow">→</span>
            <span class="val-new">${formatVal(log.new_value, false)}</span>
          </div>
        </div>
      </div>
      ${log.transaction_id ? `<div class="tx-tag" data-tx-id="${log.transaction_id}">Tx: ${log.transaction_id.slice(0, 8)}... <span class="filter-tx-btn" data-tx-id="${log.transaction_id}" title="Filter table by this transaction">🔍</span></div>` : ''}
    </div>
  `;

  li.addEventListener('click', (e) => {
    if (e.target.closest('.filter-tx-btn')) {
      e.stopPropagation();
      const txId = e.target.closest('.filter-tx-btn').dataset.txId;
      setTransactionFilter(txId);
    } else {
      navigateToLog(log);
    }
  });

  return li;
}

// Create global timeline group list item DOM element
export function createGlobalTimelineItemDom(group) {
  const txId = group.transaction_id;
  const isSummary = group.total_count > 1;
  const baseLog = group.logs[0];
  if (!baseLog) return null;

  const li = document.createElement('li');
  li.className = 'timeline-item';
  if (txId) {
    li.dataset.txId = txId;
  }

  const isCurrentTx = txId && txId === state.currentTransactionId;
  if (isCurrentTx) {
    li.classList.add('active-tx-log');
  }

  const user = baseLog.updated_by || 'system';
  const isUser = user !== 'system';
  li.classList.add(isUser ? 'user-change' : 'system-change');

  const dateStr = new Date(baseLog.timestamp).toLocaleString();

  let displayTitle = '';
  let colorClass = '';

  if (isSummary) {
    const allDeletes = group.logs.every(log => log.column_name === 'DELETE');
    const allCreates = group.logs.every(log => log.column_name === 'CREATE');

    if (allDeletes) {
      displayTitle = `🗑️ [${user}] 님 | ${baseLog.table_name} | ${group.total_count}행 삭제`;
      colorClass = 'color-delete';
    } else if (allCreates) {
      displayTitle = `🆕 [${user}] 님 | ${baseLog.table_name} | ${group.total_count}행 생성`;
      colorClass = 'color-create';
    } else {
      displayTitle = `📦 [${user}] 님 | ${baseLog.table_name} | ${group.total_count}건 변경`;
      colorClass = baseLog.is_row_deleted ? 'color-deleted-row' : 'color-summary';
    }
  } else {
    const targetId = baseLog.business_key ? (baseLog.business_key.length > 10 ? baseLog.business_key.slice(0, 10) + '...' : baseLog.business_key) : baseLog.row_id.slice(0, 8);
    const col = baseLog.column_name;
    if (col === 'CREATE') {
      displayTitle = `🆕 [${user}] 님이 ${baseLog.table_name} (${targetId}) 생성`;
      colorClass = 'color-create';
    } else if (col === 'DELETE') {
      displayTitle = `🗑️ [${user}] 님이 ${baseLog.table_name} (${targetId}) 삭제`;
      colorClass = 'color-delete';
    } else if (col === 'ROW_UPDATE') {
      displayTitle = `🤖 [${user}] 님이 ${baseLog.table_name} (${targetId}) 자동 업데이트`;
      colorClass = baseLog.is_row_deleted ? 'color-deleted-row' : 'color-auto';
    } else {
      displayTitle = `🔄 [${user}] 님이 ${baseLog.table_name} (${targetId}) 의 ${col} 수정`;
      colorClass = baseLog.is_row_deleted ? 'color-deleted-row' : (baseLog.source_name === 'user' ? 'color-user-edit' : 'color-parser-edit');
    }
  }

  if (baseLog.is_row_deleted) {
    displayTitle = `❌ [삭제됨] ` + displayTitle;
  }

  const summaryColsText = group.summary_columns && group.summary_columns.length > 0
    ? (group.summary_columns.length > 5 ? group.summary_columns.slice(0, 5).join(', ') + ` 외 ${group.summary_columns.length - 5}건` : group.summary_columns.join(', '))
    : '';

  li.innerHTML = `
    <div class="timeline-time">${dateStr}</div>
    <div class="timeline-card ${colorClass} ${isSummary ? 'summary-card' : ''}">
      <div class="timeline-user">
        <span class="user-tag">${user}</span>
        <span class="source-tag">${baseLog.source_name || 'system'}</span>
      </div>
      <div class="timeline-changes">
        <div class="change-detail">
          <span class="change-title-text">${displayTitle}</span>
          ${summaryColsText ? `<div class="summary-columns-list">${summaryColsText}</div>` : ''}
          ${!isSummary ? `
          <div class="change-values">
            <span class="val-old">${formatVal(baseLog.old_value, true)}</span>
            <span class="val-arrow">→</span>
            <span class="val-new">${formatVal(baseLog.new_value, false)}</span>
          </div>` : ''}
        </div>
      </div>
      ${txId ? `<div class="tx-tag" data-tx-id="${txId}">Tx: ${txId.slice(0, 8)}... <span class="filter-tx-btn" data-tx-id="${txId}" title="Filter table by this transaction">🔍</span> ${isSummary ? '<span class="expand-indicator">▶</span>' : ''}</div>` : ''}
    </div>
    ${isSummary ? `<div class="tx-details-container" style="display: none;"></div>` : ''}
  `;

  if (isSummary) {
    const card = li.querySelector('.timeline-card');
    const detailsContainer = li.querySelector('.tx-details-container');
    const indicator = li.querySelector('.expand-indicator');

    const toggleExpand = async () => {
      const isExpanded = state.expandedTransactions.has(txId);
      if (isExpanded) {
        state.expandedTransactions.delete(txId);
        detailsContainer.style.display = 'none';
        indicator.style.transform = 'rotate(0deg)';
        indicator.textContent = '▶';
      } else {
        state.expandedTransactions.add(txId);
        detailsContainer.style.display = 'block';
        indicator.style.transform = 'rotate(90deg)';
        indicator.textContent = '▼';

        if (group.logs.length <= 1 && group.total_count > 1) {
          if (state.fetchingTransactions.has(txId)) return;
          state.fetchingTransactions.add(txId);
          detailsContainer.innerHTML = '<div class="loading-subdetails">Loading details...</div>';

          try {
            const res = await fetch(`${API_BASE}/audit_logs/transaction/${txId}`);
            const txDetail = await res.json();
            group.logs = txDetail.logs;
            state.fetchingTransactions.delete(txId);
            renderSubDetails(detailsContainer, group.logs);
          } catch (err) {
            console.error('Failed to load transaction details', err);
            detailsContainer.innerHTML = '<div class="error-subdetails">Failed to load details.</div>';
            state.fetchingTransactions.delete(txId);
          }
        } else {
          renderSubDetails(detailsContainer, group.logs);
        }
      }
    };

    card.addEventListener('click', (e) => {
      if (e.target.closest('.filter-tx-btn')) {
        e.stopPropagation();
        const targetTxId = e.target.closest('.filter-tx-btn').dataset.txId;
        setTransactionFilter(targetTxId);
      } else if (e.target.closest('.tx-tag') || e.target.closest('.expand-indicator')) {
        toggleExpand();
      } else {
        if (group.logs && group.logs.length > 0 && group.logs[0].row_id !== '_BATCH_') {
          navigateToLog(group.logs[0]);
        }
      }
    });

    card.addEventListener('dblclick', () => {
      toggleExpand();
    });
  } else {
    const card = li.querySelector('.timeline-card');
    card.addEventListener('click', (e) => {
      if (e.target.closest('.filter-tx-btn')) {
        e.stopPropagation();
        const targetTxId = e.target.closest('.filter-tx-btn').dataset.txId;
        setTransactionFilter(targetTxId);
      } else {
        if (baseLog.row_id !== '_BATCH_') {
          navigateToLog(baseLog);
        } else {
          elements.performanceLog.textContent = '⚠️ Batch operations do not support cell positioning';
        }
      }
    });
  }

  return li;
}

// Prepend single item incrementally to cell/row history tab
export function renderTimelineIncremental(log) {
  if (state.activeHistoryTab === 'cell') {
    if (!state.selectedCell || state.selectedCell.rowId !== log.row_id || state.selectedCell.colId !== log.column_name) return;
  } else if (state.activeHistoryTab === 'row') {
    if (!state.selectedCell || state.selectedCell.rowId !== log.row_id) return;
  } else {
    return;
  }

  const emptyLi = elements.timeline.querySelector('.timeline-empty');
  if (emptyLi) {
    emptyLi.remove();
  }

  const li = createTimelineItemDom(log);
  elements.timeline.insertBefore(li, elements.timeline.firstChild);
}

// Prepend or update item incrementally to global history tab
export function renderGlobalTimelineIncremental(log) {
  if (state.activeHistoryTab !== 'global') return;

  const emptyLi = elements.timeline.querySelector('.timeline-empty');
  if (emptyLi) {
    emptyLi.remove();
  }

  const group = state.globalHistoryData.find(g => g.transaction_id === log.transaction_id);
  if (!group) return;

  let oldLi = null;
  if (log.transaction_id) {
    oldLi = elements.timeline.querySelector(`li[data-tx-id="${log.transaction_id}"]`);
  }

  const newLi = createGlobalTimelineItemDom(group);
  if (!newLi) return;

  if (oldLi) {
    const isExpanded = state.expandedTransactions.has(log.transaction_id);
    if (isExpanded) {
      const detailsContainer = newLi.querySelector('.tx-details-container');
      const indicator = newLi.querySelector('.expand-indicator');
      if (detailsContainer) {
        detailsContainer.style.display = 'block';
        renderSubDetails(detailsContainer, group.logs);
      }
      if (indicator) {
        indicator.style.transform = 'rotate(90deg)';
        indicator.textContent = '▼';
      }
    }

    elements.timeline.replaceChild(newLi, oldLi);
  } else {
    elements.timeline.insertBefore(newLi, elements.timeline.firstChild);
  }
}

// Render history logs in a vertical timeline UI card structure
export function renderTimeline(logs) {
  elements.timeline.innerHTML = '';

  if (!logs || logs.length === 0) {
    elements.timeline.innerHTML = '<li class="timeline-empty">No change history recorded.</li>';
    return;
  }

  logs.forEach(log => {
    const li = createTimelineItemDom(log);
    elements.timeline.appendChild(li);
  });
}

// Render overall table audit history logs (recent transactions)
export function renderGlobalTimeline() {
  elements.timeline.innerHTML = '';

  if (!state.globalHistoryData || state.globalHistoryData.length === 0) {
    elements.timeline.innerHTML = '<li class="timeline-empty">No database history recorded.</li>';
    return;
  }

  state.globalHistoryData.forEach((group) => {
    const li = createGlobalTimelineItemDom(group);
    if (li) {
      elements.timeline.appendChild(li);
    }
  });
}

export function renderSubDetails(container, logs) {
  container.innerHTML = '';
  const ul = document.createElement('ul');
  ul.className = 'sub-timeline-list';

  const renderLimit = 500;
  const initialLogs = logs.slice(0, renderLimit);
  const remainingLogs = logs.slice(renderLimit);

  function appendLogItem(log) {
    const li = document.createElement('li');
    li.className = 'sub-timeline-item';

    const col = log.column_name;
    const val = formatVal(log.new_value);
    const bk = log.business_key;
    const targetId = bk ? (bk.length > 10 ? bk.slice(0, 10) + '...' : bk) : (log.row_id ? log.row_id.slice(0, 8) : '');

    let labelText = '';
    if (col === 'ROW_UPDATE') {
      labelText = `ROW_UPDATE: ${val} (ID: ${targetId})`;
    } else {
      labelText = `[${col}] ${val} (ID: ${targetId})`;
    }

    li.innerHTML = `
      <span class="sub-bullet">└</span>
      <span class="sub-log-text">${labelText}</span>
    `;

    li.addEventListener('click', (e) => {
      e.stopPropagation();
      if (log.row_id !== '_BATCH_') {
        navigateToLog(log);
      }
    });

    ul.appendChild(li);
  }

  initialLogs.forEach(appendLogItem);
  container.appendChild(ul);

  if (remainingLogs.length > 0) {
    const moreBtn = document.createElement('button');
    moreBtn.className = 'glass-btn';
    moreBtn.style.margin = '10px 0 10px 24px';
    moreBtn.style.padding = '6px 16px';
    moreBtn.style.fontSize = '0.8rem';
    moreBtn.style.color = 'var(--accent)';
    moreBtn.style.borderColor = 'var(--border-strong)';
    moreBtn.style.background = 'var(--accent-weak)';
    moreBtn.textContent = `➕ Show remaining ${remainingLogs.length} logs`;
    
    moreBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      remainingLogs.forEach(appendLogItem);
      moreBtn.remove();
    });
    
    container.appendChild(moreBtn);
  }
}

// Helper to format values
export function formatVal(v, isOld = false) {
  if (v === null || v === undefined || v === '') {
    return isOld ? '비어있음' : '삭제됨';
  }
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

// Debounced History Loader
let historyDebounceTimeout = null;
export function triggerHistoryReloadDebounced() {
  clearTimeout(historyDebounceTimeout);
  historyDebounceTimeout = setTimeout(() => {
    loadHistory();
  }, 300);
}

// Feature 3: Append single history log locally to prevent full API refresh on cell change
export function appendHistoryLocally(log, skipRender = false) {
  if (!log) return;

  if (state.activeHistoryTab === 'global') {
    const existingGroup = state.globalHistoryData.find(g => g.transaction_id === log.transaction_id);
    if (existingGroup) {
      const isDuplicate = existingGroup.logs.some(l => {
        if (log.id && l.id && log.id === l.id) return true;
        const lTime = l.timestamp ? new Date(l.timestamp).getTime() : 0;
        const logTime = log.timestamp ? new Date(log.timestamp).getTime() : 0;
        return lTime === logTime && l.column_name === log.column_name && l.row_id === log.row_id;
      });
      if (!isDuplicate) {
        existingGroup.logs.unshift(log);
        existingGroup.total_count += 1;
        if (!existingGroup.summary_columns) {
          existingGroup.summary_columns = [];
        }
        if (log.column_name && !existingGroup.summary_columns.includes(log.column_name)) {
          existingGroup.summary_columns.push(log.column_name);
        }
      }
    } else {
      state.globalHistoryData.unshift({
        transaction_id: log.transaction_id,
        total_count: 1,
        summary_columns: log.column_name ? [log.column_name] : [],
        logs: [log]
      });
    }
    if (!skipRender) {
      renderGlobalTimelineIncremental(log);
    }
    return;
  }

  // Non-global tabs ('cell' or 'row')
  if (!state.selectedCell) return;

  if (state.activeHistoryTab === 'cell') {
    if (state.selectedCell.rowId !== log.row_id || state.selectedCell.colId !== log.column_name) return;
  } else if (state.activeHistoryTab === 'row') {
    if (state.selectedCell.rowId !== log.row_id) return;
  }

  // Store in cache if not duplicate
  const isDuplicate = state.cellRowHistoryData.some(l => {
    if (log.id && l.id && log.id === l.id) return true;
    const lTime = l.timestamp ? new Date(l.timestamp).getTime() : 0;
    const logTime = log.timestamp ? new Date(log.timestamp).getTime() : 0;
    return lTime === logTime && l.column_name === log.column_name && l.row_id === log.row_id;
  });
  if (!isDuplicate) {
    state.cellRowHistoryData.unshift(log);
  }

  if (!skipRender) {
    renderTimelineIncremental(log);
  }
}

// HistoryNavigator (4-Step Jump Sequence)
export async function navigateToLog(log) {
  if (state.isNavigating) {
    elements.performanceLog.textContent = '⚠️ Already navigating, please wait...';
    return;
  }

  state.isNavigating = true;
  // V1 instrument: the deepest in-page jump on the grid page — it can change table, set a
  // transaction filter and scroll to another row, so the prior working context is gone.
  countNav(ROUTES.GRID, 'grid:log_jump');
  elements.performanceLog.textContent = `🔍 Navigating to ${log.table_name}:${log.row_id} in Transaction ${log.transaction_id}...`;

  // Set 5s watchdog safety net (mimics PyQt 10s guard timer)
  if (state.navigationWatchdog) clearTimeout(state.navigationWatchdog);
  state.navigationWatchdog = setTimeout(() => {
    releaseNavigationGuard('❌ Navigation Timeout');
  }, 5000);

  const targetTable = log.table_name;
  const targetTx = log.transaction_id;

  // Step 1: Switch table/tab if different
  if (state.currentTable !== targetTable) {
    elements.tableSelect.value = targetTable;
    await switchTable(targetTable);
  }

  // Set the transaction filter context automatically
  if (targetTx) {
    state.currentTransactionId = targetTx;
    if (elements.bannerTxId) elements.bannerTxId.textContent = targetTx;
    if (elements.txFilterBanner) elements.txFilterBanner.style.display = 'flex';

    // Highlight timeline items
    const timelineItems = elements.timeline.querySelectorAll('.timeline-item');
    timelineItems.forEach(li => {
      const itemTxId = li.dataset.txId || (li.querySelector('.filter-tx-btn')?.dataset.txId);
      if (itemTxId && itemTxId === state.currentTransactionId) {
        li.classList.add('active-tx-log');
      } else {
        li.classList.remove('active-tx-log');
      }
    });
  } else {
    state.currentTransactionId = null;
    if (elements.bannerTxId) elements.bannerTxId.textContent = '';
    if (elements.txFilterBanner) elements.txFilterBanner.style.display = 'none';

    // Clear highlights
    const timelineItems = elements.timeline.querySelectorAll('.timeline-item');
    timelineItems.forEach(li => {
      li.classList.remove('active-tx-log');
    });
  }

  // Give browser event loop 50ms to stabilize layout
  setTimeout(() => {
    navigatorStep3(log);
  }, 50);
}

// Step 2: Check local caching or decide server target jump
export function navigatorStep2(log) {
  if (!state.gridApi) {
    releaseNavigationGuard('❌ Grid not initialized');
    return;
  }

  const rowNode = state.gridApi.getRowNode(log.row_id);
  if (rowNode) {
    // Cache Hit -> directly scroll (Step 4)
    navigatorFinalScroll(rowNode, log.column_name);
  } else {
    // Check if row exists in any of the cached pages
    for (const [skip, cached] of state.pageCache.entries()) {
      const found = cached.data.some(r => (r.row_id || r.id) === log.row_id);
      if (found) {
        state.currentSkip = skip;
        state.gridApi.setGridOption('rowData', cached.data);
        updateGridSortState();
        updateLoadedCount(cached.data.length);
        elements.totalRowsCount.textContent = `Matches: ${cached.total}`;
        updatePaginationUI(cached.total);

        setTimeout(() => {
          const node = state.gridApi.getRowNode(log.row_id);
          if (node) {
            navigatorFinalScroll(node, log.column_name);
          } else {
            releaseNavigationGuard('❌ Failed to locate row in cached page');
          }
        }, 50);
        return;
      }
    }

    // Cache Miss -> request server target jump (Step 3)
    navigatorStep3(log);
  }
}

// Step 3: Fetch target row via API parameter
export async function navigatorStep3(log) {
  elements.performanceLog.textContent = '🌐 Requesting target position from server...';

  const q = elements.globalSearch ? elements.globalSearch.value.trim() : '';
  const cols = elements.searchCols ? elements.searchCols.value : '';
  const sortLatest = elements.sortLatestToggle.checked;
  const filterModel = state.gridApi ? state.gridApi.getFilterModel() : {};
  const filterStr = Object.keys(filterModel).length > 0 ? JSON.stringify(filterModel) : '';

  let url = `${API_BASE}/tables/${state.currentTable}/data?target_row_id=${log.row_id}&limit=${pageLimit}`;
  url += `&order_by=${sortLatest ? 'updated_at' : 'row_id'}&order_desc=${sortLatest}`;
  if (state.currentTransactionId) {
    url += `&transaction_id=${state.currentTransactionId}`;
  }
  if (q) {
    url += `&q=${encodeURIComponent(q)}`;
    if (cols) url += `&cols=${encodeURIComponent(cols)}`;
  }
  if (filterStr) {
    url += `&filters=${encodeURIComponent(filterStr)}`;
  }

  try {
    const res = await fetch(url);
    const result = await res.json();

    if (result.target_offset === -1 || result.data.length === 0) {
      releaseNavigationGuard('❌ Target row does not match active search/transaction filters');
      return;
    }

    // Load returned chunk page to local grid
    state.gridApi.setGridOption('rowData', result.data);
    updateGridSortState();

    // Update skip counter
    state.currentSkip = result.calculated_skip !== null ? result.calculated_skip : 0;

    // Update Counts (Zero-lag counter concept)
    updateLoadedCount(result.data.length);
    elements.totalRowsCount.textContent = `Matches: ${result.total}`;

    // Update Pagination UI
    updatePaginationUI(result.total);

    // Save to Cache
    state.pageCache.set(state.currentSkip, { data: result.data, total: result.total });

    // Check if target node loaded successfully
    setTimeout(() => {
      const rowNode = state.gridApi.getRowNode(log.row_id);
      if (rowNode) {
        navigatorFinalScroll(rowNode, log.column_name);
      } else {
        releaseNavigationGuard('❌ Failed to locate row after server fetch');
      }
    }, 20); // 20ms layout sync delay

  } catch (err) {
    console.error('Jump fetch error', err);
    releaseNavigationGuard('❌ Server fetch error');
  }
}

// Step 4: Scroll and Focus Column Cell
export function navigatorFinalScroll(rowNode, columnName) {
  try {
    // 1. Ensure visible
    state.gridApi.ensureNodeVisible(rowNode, 'middle');

    // 2. Select row
    rowNode.setSelected(true, true);

    // 3. Focus Cell
    state.gridApi.setFocusedCell(rowNode.rowIndex, columnName);

    // 4. Trigger flash micro-animation
    state.gridApi.flashCells({
      rowNodes: [rowNode],
      columns: [columnName],
      flashDelay: 1000
    });

    // 5. Sync details panel manually
    state.selectedCell = {
      rowId: rowNode.data.row_id,
      colId: columnName,
      value: rowNode.data.data?.[columnName]?.value ?? '',
      rowIndex: rowNode.rowIndex
    };
    updateSelectedCellUI();

    elements.performanceLog.textContent = `🎯 Jumped to ${columnName} at Row ${rowNode.data.row_id}`;

    // Finalize
    releaseNavigationGuard();
  } catch (err) {
    console.error('Final scroll error', err);
    releaseNavigationGuard('❌ Scroller positioning error');
  }
}

// Helper: Navigation Locker Release
export function releaseNavigationGuard(errorMessage = '') {
  state.isNavigating = false;
  if (state.navigationWatchdog) {
    clearTimeout(state.navigationWatchdog);
    state.navigationWatchdog = null;
  }
  if (errorMessage) {
    elements.performanceLog.textContent = errorMessage;
  }
}
