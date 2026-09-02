import { API_BASE, WS_URL, CURRENT_USER, pageLimit } from './config.js';
import { state } from './state.js';
import { elements } from './dom.js';
import { clearRangeSelection } from './clipboard.js';
import { updateSelectedCellUI, updateTxModeUI } from './ui.js';
import { renderGrid, updateGridSortState, updateLoadedCount, updatePaginationUI, ensureCellObject, applyFillTargetHeaders } from './grid.js';
// 「Matches:」를 쓰는 자리는 다섯입니다. 철자와 «세는 중» 판정은 한 곳에 삽니다.
import { setMatchCount } from './match_count.js';
import { loadHistory } from './timeline.js';
import { getLocalTimeString } from './utils.js';
import { refreshTraceEntry } from './trace_launch.js';
import { resetSuggestLearning } from './value_suggest.js';
import { snapshot, commitIfRecorded } from './effort_meter.js';
import { syncReferenceViewRule } from './enrichment_reference_view.js';

/**
 * Write a status badge WITHOUT trusting the handle to exist.
 *
 * A CATCH BLOCK MUST NOT BE ABLE TO THROW. Both functions below used to write DOM handles
 * unguarded from inside their `catch`, which turns a HANDLED outage into an UNHANDLED
 * rejection at the exact instant the code was trying to be careful — and that rejection
 * escaped far enough to take the WebSocket down with it (see the comment on `init()` in
 * main.js). This repo has a measured precedent for `elements` getters resolving to null:
 * two of them named ids that had never existed in index.html at any point in git history.
 *
 * This does NOT silence anything. The originating error is logged by the caller before any
 * badge is touched; only the cosmetic write is made optional, because a missing badge is not
 * a reason to abandon the rest of startup.
 */
function setBadge(el, text, className) {
  if (!el) return false;
  el.textContent = text;
  if (className !== undefined) el.className = className;
  return true;
}

// Check backend server status
export async function checkServerHealth() {
  try {
    const res = await fetch(`${API_BASE}/tables`);
    if (!res.ok) throw new Error(`/tables responded ${res.status}`);
    setBadge(elements.serverStatus, 'API: ONLINE', 'status-badge online');
  } catch (err) {
    // Loud first, cosmetic second. The old catch swallowed `err` entirely, so an outage and a
    // programming error inside this function were indistinguishable in the console.
    console.error('[health] server health check failed', err);
    setBadge(elements.serverStatus, 'API: OFFLINE', 'status-badge offline');
    setBadge(elements.performanceLog, 'Error connecting to database server');
  }
}

/**
 * In-flight de-duplication for `loadTables`.
 *
 * WHY IT EXISTS. `loadTables` now has two callers that can overlap: `init()` and the socket's
 * `onopen`, which bootstraps the table list when it finds the picker empty. Since the socket is
 * started FIRST (so no failure in REST startup can leave the page without a live channel), a
 * localhost handshake — measured median 2.54ms — reliably lands while `init()`'s own
 * `loadTables()` is still mid-flight, and `elements.tableSelect.value` is still ''. Without this
 * latch that produced two concurrent `switchTable()` runs: two `loadSchema`, two `renderGrid`
 * tearing down and rebuilding the grid, and two racing `fetchData(true)`.
 *
 * Sharing the promise rather than dropping the second call is what makes it safe for `onopen`,
 * which AWAITS the result and must not proceed as if the list were loaded when it is not.
 */
let tablesLoadInFlight = null;

// Load available tables
export async function loadTables() {
  if (tablesLoadInFlight) return tablesLoadInFlight;
  tablesLoadInFlight = loadTablesOnce();
  try {
    return await tablesLoadInFlight;
  } finally {
    tablesLoadInFlight = null;
  }
}

async function loadTablesOnce() {
  try {
    const res = await fetch(`${API_BASE}/tables`);
    const data = await res.json();
    if (!elements.tableSelect) throw new Error('#table-select is not present on this page');
    elements.tableSelect.innerHTML = '';

    if (data.tables && data.tables.length > 0) {
      data.tables.forEach(table => {
        const option = document.createElement('option');
        option.value = table;
        option.textContent = table;
        elements.tableSelect.appendChild(option);
      });

      // Auto select first table
      const firstTable = data.tables[0];
      elements.tableSelect.value = firstTable;
      await switchTable(firstTable);
    } else {
      elements.tableSelect.innerHTML = '<option value="">No tables found</option>';
    }
  } catch (err) {
    console.error('Failed to load tables', err);
    // Guarded for the same reason as `setBadge` above: the handle this catch wants to write is
    // exactly the handle whose absence is one of the ways we get here.
    if (elements.tableSelect) elements.tableSelect.innerHTML = '<option value="">Failed to load</option>';
  }
}

// Switch current working table
export async function switchTable(tableName) {
  state.currentTable = tableName;
  window.currentTable = tableName; // Expose globally for Desktop Wrapper
  elements.performanceLog.textContent = `Switching to ${tableName}...`;

  // Clean selected cell info
  state.selectedCell = null;
  clearRangeSelection();
  updateSelectedCellUI();

  // Discard pending edits on table switch
  state.pendingTxEdits = {};
  state.txModeActive = true;
  if (elements.txModeToggle) elements.txModeToggle.checked = true;
  updateTxModeUI();

  // Reset transaction filter
  state.currentTransactionId = null;
  if (elements.txFilterBanner) elements.txFilterBanner.style.display = 'none';
  if (elements.bannerTxId) elements.bannerTxId.textContent = '';

  // Load Schema
  await loadSchema(tableName);
  // Re-create empty grid to bind new columns
  renderGrid([]);
  // Fetch initial chunk of data (reset skip to 0)
  await fetchData(true);

  // Reset active history tab to global when switching tables to avoid empty screen
  state.activeHistoryTab = 'global';
  elements.tabGlobalBtn.classList.add('active');
  elements.tabCellBtn?.classList.remove('active');
  elements.tabRowBtn.classList.remove('active');
  // Cleared here too: a table WITHOUT a rule must not inherit the previous table's
  // reference highlight, and `syncReferenceViewRule` re-selects it a moment later on
  // the tables that do have one.
  elements.tabReferenceBtn?.classList.remove('active');
  await loadHistory();

  // Enrichment 결손 배지: fire-and-forget (테이블 전환을 블로킹하지 않음, 실패 무음)
  // The headers get their ①② here, not in `renderGrid` above: the rule is still in flight
  // at that point. `.catch` keeps the stated fire-and-forget contract -- adding a `.then`
  // to a bare call would otherwise turn a silent failure into an unhandled rejection.
  syncReferenceViewRule().then(applyFillTargetHeaders).catch(() => {});

  // G2 추적 진입점: 현재 테이블의 그래프 매핑 여부 재판정 (fire-and-forget, 실패 무음)
  refreshTraceEntry();
}

// Load table column schema
export async function loadSchema(tableName) {
  // [F3] Drop the value-suggestion module's learned negative facts (disabled columns, prefix
  // floors, unavailable cooldowns). They are learned from the server's own refusals, which are
  // derived from `table_config` — the same declaration this /schema read is about to refresh.
  // `table_config` is HOT-RELOADED and the server honours a change from the next request, so
  // without this a column newly declared suggestible stays dead in an already-open tab. Those
  // latches also expire on their own (LEARNED_TTL_MS); this is what makes the change land at
  // once on the one path that has a signal.
  resetSuggestLearning();
  try {
    const res = await fetch(`${API_BASE}/tables/${tableName}/schema`);
    const data = await res.json();
    state.currentColumns = data.columns || [];
    state.currentColumnTypes = data.column_types || {};
    state.currentBusinessKey = data.business_key || '';
    state.currentCompositeKeySources = data.composite_key_source || [];
    // [Virtual join] The route always sends this key (`[]` when no verified join touches the
    // table), so a missing key means an OLD SERVER — fall back to empty, never to undefined,
    // because every consumer below treats "no virtual columns" as the normal case.
    // `Array.isArray` rather than `|| []`: `|| []` still lets a non-array truthy value
    // through, and `state.currentVirtualColumns.some(...)` on an object would throw inside
    // the write guards, i.e. exactly where a failure must not happen.
    state.currentVirtualColumns = Array.isArray(data.virtual_columns) ? data.virtual_columns : [];
    // [Virtual join] Which columns the SERVER resolves through a join (collide AND
    // virtual_only) — a WIDER set than `virtual_columns`, which announces only the ones the
    // grid must add. Same `Array.isArray` discipline and the same reason: a missing key
    // means an OLD SERVER, and `[]` is the correct reading of "this server resolves nothing
    // through a join", which is exactly how every pre-change server behaved.
    state.currentJoinResolvedColumns = Array.isArray(data.join_resolved_columns)
      ? data.join_resolved_columns : [];

    // Fill search columns dropdown: stored columns first, then the join-resolved names.
    //
    // 🔴 THE LIST IS READ OFF THE ANNOUNCEMENT, NEVER ASSEMBLED HERE. `?cols=` is scoped by
    // the server's `apply_search_filter`, whose virtual vocabulary is the binder's
    // `virtual_join_executor.exposed_columns` — the exact set `/schema` publishes as
    // `join_resolved_columns`. A name this client invented would be one the server has no
    // expression for, and the server REFUSES such a scope with 400 rather than answering
    // with the whole table. So an absent or empty announcement offers stored columns only,
    // which is exactly how every pre-change server behaved.
    //
    // 🔴 KEYED OFF `join_resolved_columns`, NOT `virtual_columns` — the same choice
    // `grid.js` makes for the column filter, and for the same reason. This asks "can the
    // SERVER search this name", and only the wider announcement answers it; `virtual_columns`
    // says merely "add this column" and is silent about every `collide` name.
    //
    // 🔴 SEARCH ONLY — this element is not a write path. It is read by exactly four sites
    // (`fetchData` here, the export in `main.js` x2, `timeline.js`), all of which put the
    // value into `?cols=` of a READ. Editability is decided by `isVirtualColumn` inside the
    // write funnels, which never look at this select, so widening it cannot make a
    // read-only column look editable anywhere.
    if (elements.searchCols) {
      elements.searchCols.innerHTML = '<option value="">All Columns</option>';
      const appendOption = (col, joined) => {
        const option = document.createElement('option');
        option.value = col;
        // 🔗 is the header vocabulary `grid.js` already uses for a join-resolved column,
        // reused rather than inventing a second way to say the same thing. Only the
        // LABEL carries it — `option.value` stays the bare name the server is sent.
        option.textContent = joined ? `${col} 🔗` : col;
        elements.searchCols.appendChild(option);
      };
      state.currentColumns.forEach(col => {
        if (col !== 'created_at' && col !== 'updated_at') appendOption(col, false);
      });
      state.currentJoinResolvedColumns.forEach(entry => {
        // Malformed entry: skip it rather than offering an option whose value is `undefined`.
        if (!entry || typeof entry.name !== 'string' || entry.name === '') return;
        // A `collide` name is a STORED column and the loop above already offered it. Emitting
        // it twice would put two identical options in the select that build the identical
        // query — the announcement is wider than what is missing here, so it must be
        // differenced against what was already offered rather than appended wholesale.
        if (state.currentColumns.includes(entry.name)) return;
        appendOption(entry.name, true);
      });
    }
  } catch (err) {
    console.error('Failed to load schema', err);
    elements.performanceLog.textContent = 'Schema load error';
  }
}

// 늦게 오는 개수의 «세대». 표를 바꾸거나 필터를 고치면 앞선 요청의 답은 «다른 질문»의
// 답이 됩니다 -- 그게 도착해서 화면을 덮으면 화면과 바닥글이 서로 다른 것을 말합니다.
let countGeneration = 0;

/** 「몇 건인가」를 «바꾸는» 인자만. `skip`·`limit`·`order_by` 는 어느 행을 보여줄지를 정할 뿐
 *  개수를 바꾸지 않으므로 여기 없습니다 (서버의 `/data/count` 도 같은 이유로 안 받습니다).
 *
 * 🔴 이 한 곳에서 만들어 data 와 count 가 «같은 것»을 싣습니다. 두 벌로 조립하면 두 수가
 *    갈리고, 그건 오류를 내지 않습니다 -- 화면은 없는 행을 그리고 바닥글은 없다고 말합니다.
 */
function narrowingParams() {
  const params = new URLSearchParams();
  const q = elements.globalSearch ? elements.globalSearch.value.trim() : '';
  const cols = elements.searchCols ? elements.searchCols.value : '';
  const filterModel = state.gridApi ? state.gridApi.getFilterModel() : {};
  if (state.currentTransactionId) params.set('transaction_id', state.currentTransactionId);
  if (q) {
    params.set('q', q);
    if (cols) params.set('cols', cols);
  }
  if (Object.keys(filterModel).length > 0) params.set('filters', JSON.stringify(filterModel));
  return params;
}

/** 미룬 개수를 가져와 채웁니다. 행은 «이미» 그려져 있습니다.
 *
 * 🔴 못 가져오면 «세는 중»인 채로 둡니다. 0 으로 떨어뜨리면 「일치 없음」이라는 거짓이고,
 *    「모른다」는 못 세었을 때도 참입니다.
 */
async function fillMatchCount(params, table) {
  const mine = ++countGeneration;
  const tail = params.toString();
  try {
    const res = await fetch(`${API_BASE}/tables/${table}/data/count${tail ? `?${tail}` : ''}`);
    const body = await res.json();
    // 늦게 온 답은 버립니다 -- 그 사이에 표나 필터가 바뀌었으면 이건 «다른 질문»의 답입니다.
    if (mine !== countGeneration || table !== state.currentTable) return;
    if (!res.ok || !Number.isFinite(body.total)) return;
    setMatchCount(elements.totalRowsCount, body.total);
    updatePaginationUI(body.total);
    // 캐시된 쪽들은 «같은 좁힘»의 것들입니다 (필터가 바뀌면 캐시가 비워집니다).
    // 안 채우면 캐시 적중이 「세는 중」으로 되돌아갑니다.
    state.pageCache.forEach((entry) => { entry.total = body.total; });
  } catch (e) {
    console.error('Failed to fetch match count', e);
  }
}

// Fetch row data and render inside AG-Grid (Handles Pagination)
export async function fetchData(resetSkip = true) {
  if (!state.currentTable || state.isLoadingMore) return;

  if (resetSkip) {
    state.pageCache.clear();
    clearRangeSelection();
    state.currentSkip = 0;
    state.hasMoreData = true;
    state.allDataLoaded = false;
  } else {
    if (state.viewMode !== 'infinite' && state.pageCache.has(state.currentSkip)) {
      const cached = state.pageCache.get(state.currentSkip);
      state.gridApi.setGridOption('rowData', cached.data);
      updateGridSortState();
      updateLoadedCount(cached.data.length);
      setMatchCount(elements.totalRowsCount, cached.total);
      updatePaginationUI(cached.total);
      // 아직 안 센 쪽이 캐시에 있으면 «다시 묻습니다». 안 그러면 「세는 중」이 영영 남습니다.
      if (!Number.isFinite(cached.total)) fillMatchCount(narrowingParams(), state.currentTable);
      elements.performanceLog.textContent = `Loaded ${cached.data.length} rows from client cache`;
      return;
    }
  }

  state.isLoadingMore = true;
  elements.performanceLog.textContent = 'Fetching data...';

  const startTime = performance.now();

  const sortLatest = elements.sortLatestToggle.checked;
  const narrowing = narrowingParams();
  const table = state.currentTable;

  // 🔴 `defer_total=true` -> 응답의 `total` 이 «null» 입니다. 행이 먼저 나오고 개수는
  //    두 번째 요청이 채웁니다. 세는 데 걸리는 시간이 첫 화면에서 빠집니다.
  let url = `${API_BASE}/tables/${table}/data?skip=${state.currentSkip}&limit=${pageLimit}`;
  url += `&order_by=${sortLatest ? 'updated_at' : 'row_id'}&order_desc=${sortLatest}`;
  url += '&defer_total=true';
  const tail = narrowing.toString();
  if (tail) url += `&${tail}`;

  try {
    const res = await fetch(url);
    const result = await res.json();

    const fetchTime = (performance.now() - startTime).toFixed(1);

    if (result.data.length < pageLimit) {
      state.hasMoreData = false;
    }

    // Render rowData depending on View Mode
    if (state.viewMode === 'infinite') {
      if (resetSkip || state.currentSkip === 0) {
        state.gridApi.setGridOption('rowData', result.data);
      } else {
        state.gridApi.applyTransaction({ add: result.data });
      }
    } else {
      state.gridApi.setGridOption('rowData', result.data);
    }
    updateGridSortState();

    // Update Counts (Zero-lag counter concept)
    updateLoadedCount();
    setMatchCount(elements.totalRowsCount, result.total);

    // Update Pagination UI
    updatePaginationUI(result.total);

    elements.performanceLog.textContent = `Loaded ${result.data.length} rows in ${fetchTime}ms`;

    // 행은 그려졌습니다. 이제 개수를 가지러 갑니다 -- «기다리지 않고» 돌려줍니다.
    if (!Number.isFinite(result.total)) fillMatchCount(narrowing, table);

    // Save to Cache
    if (state.viewMode !== 'infinite') {
      state.pageCache.set(state.currentSkip, { data: result.data, total: result.total });
    }

    state.isLoadingMore = false;
  } catch (err) {
    console.error('Failed to fetch data', err);
    elements.performanceLog.textContent = 'Data fetch failed';
    state.isLoadingMore = false;
  }
}

// Handle inline editing updates to DB
export async function handleCellEdit(event) {
  const { data, colDef, newValue, oldValue } = event;
  const colId = colDef.field;
  const rowId = data.row_id;

  if (newValue === oldValue) return;

  // 이전 상태 복구를 위해 저장
  const oldCell = data.data?.[colId];
  const oldIsOverwrite = oldCell ? oldCell.is_overwrite : false;
  const oldPrioritySource = oldCell ? oldCell.priority_source : null;

  // --- 타입 검사 및 변환 추가 ---
  let finalValue = newValue;
  const colTypes = state.currentColumnTypes || {};
  const colType = colTypes[colId] || 'string';
  if (colType === 'number') {
    if (newValue === '' || newValue === null || newValue === undefined) {
      finalValue = null;
    } else {
      const parsedVal = Number(newValue);
      if (isNaN(parsedVal)) {
        alert(`컬럼 '${colId}'의 값 '${newValue}'은(는) 올바른 숫자 형식이 아닙니다.`);
        // Rollback grid value & overwrite status
        const latestNode = state.gridApi.getRowNode(rowId);
        const latestData = latestNode ? latestNode.data : data;
        if (latestData) {
          ensureCellObject(latestData, colId);
          latestData.data[colId].value = oldValue;
          latestData.data[colId].is_overwrite = oldIsOverwrite;
          latestData.data[colId].priority_source = oldPrioritySource;
        }
        state.gridApi.refreshCells({ rowNodes: [latestNode].filter(Boolean), columns: [colId], force: true });
        elements.performanceLog.textContent = '❌ Invalid number format';
        return;
      }
      finalValue = parsedVal;
    }
  }

  // Intercept and stage if Tx Mode is active
  if (state.txModeActive) {
    const key = `${rowId}_${colId}`;
    if (!state.pendingTxEdits[key]) {
      state.pendingTxEdits[key] = {
        rowId,
        colId,
        newValue: finalValue,
        oldValue: oldValue,
        oldIsOverwrite: oldIsOverwrite,
        data: data
      };
    } else {
      state.pendingTxEdits[key].newValue = finalValue;
    }

    const latestNode = state.gridApi.getRowNode(rowId);
    const latestData = latestNode ? latestNode.data : data;
    if (latestData) {
      ensureCellObject(latestData, colId);
      latestData.data[colId].value = finalValue;
    }

    updateTxModeUI();
    state.gridApi.refreshCells({ rowNodes: [latestNode].filter(Boolean), columns: [colId], force: true });
    return;
  }

  elements.performanceLog.textContent = 'Saving edit...';
  const editStartTime = performance.now();

  // API body payload mapping to GeneralUpdateBatch
  const payload = {
    updates: [
      {
        row_id: rowId,
        updates: {
          [colId]: finalValue
        },
        source_name: 'user',
        updated_by: CURRENT_USER
      }
    ],
    silent: false,
    // V1 instrument: optional field. Raw counts only — the server weights at query time.
    effort: snapshot()
  };

  try {
    const res = await fetch(`${API_BASE}/tables/${state.currentTable}/data/updates`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      state.pageCache.clear();
      const result = await res.json();
      // V1 instrument: reset ONLY when the server confirms it recorded the effort. A 200 is
      // not proof of a correction — a no-op save writes nothing, and resetting there would
      // erase the effort the attempt cost. Read AFTER res.json() for that reason.
      commitIfRecorded(result);
      const saveTime = (performance.now() - editStartTime).toFixed(1);
      elements.performanceLog.textContent = `Saved in ${saveTime}ms (${result.change_count} cell updated)`;

      const latestNode = state.gridApi.getRowNode(rowId);
      const latestData = latestNode ? latestNode.data : data;

      ensureCellObject(latestData, colId);
      latestData.data[colId].value = finalValue;
      latestData.data[colId].is_overwrite = true;
      latestData.data[colId].priority_source = 'user';

      // Update updated_at timestamp locally to trigger sort update
      latestData.updated_at = getLocalTimeString();

      state.gridApi.refreshCells({
        rowNodes: [latestNode].filter(Boolean),
        columns: [colId, 'updated_at'],
        force: true
      });

      // Refresh current focused cell UI if active
      if (state.selectedCell && state.selectedCell.rowId === rowId && state.selectedCell.colId === colId) {
        state.selectedCell.value = finalValue;
        updateSelectedCellUI();
      }
    } else {
      const errData = await res.json().catch(() => ({}));
      const errMsg = errData.detail || 'Save failed';
      throw new Error(errMsg);
    }
  } catch (err) {
    console.error('Cell update failed', err);
    alert(`수정 사항 저장 실패: ${err.message}`);
    elements.performanceLog.textContent = '❌ Edit failed to save';

    // Rollback grid value & overwrite status
    const latestNode = state.gridApi.getRowNode(rowId);
    const latestData = latestNode ? latestNode.data : data;
    if (latestData) {
      ensureCellObject(latestData, colId);
      latestData.data[colId].value = oldValue;
      latestData.data[colId].is_overwrite = oldIsOverwrite;
      latestData.data[colId].priority_source = oldPrioritySource;
    }
    state.gridApi.refreshCells({ rowNodes: [latestNode].filter(Boolean), columns: [colId], force: true });
  }
}

// Add Empty Rows
export async function addRows(count) {
  if (!state.currentTable) return;
  elements.performanceLog.textContent = `Creating ${count} empty row(s)...`;
  try {
    const res = await fetch(`${API_BASE}/tables/${state.currentTable}/rows?count=${count}&user_name=${encodeURIComponent(CURRENT_USER)}`, {
      method: 'POST'
    });
    if (res.ok) {
      elements.performanceLog.textContent = `${count} empty row(s) created successfully`;
    } else {
      throw new Error('Create failed');
    }
  } catch (err) {
    console.error('Failed to create row(s)', err);
    elements.performanceLog.textContent = '❌ Failed to create row(s)';
  }
}

// Delete selected rows batch
export async function deleteSelectedRows() {
  if (!state.gridApi) return;
  const selectedNodes = state.gridApi.getSelectedNodes();
  if (selectedNodes.length === 0) {
    alert('No rows selected for deletion');
    return;
  }

  const rowIds = selectedNodes.map(node => node.data.row_id).filter(Boolean);
  if (rowIds.length === 0) return;

  if (!confirm(`Are you sure you want to permanently delete the selected ${rowIds.length} rows?`)) return;

  elements.performanceLog.textContent = 'Deleting selected rows...';
  try {
    const res = await fetch(`${API_BASE}/tables/${state.currentTable}/rows/batch_delete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        row_ids: rowIds,
        user_name: CURRENT_USER
      })
    });

    if (res.ok) {
      state.pageCache.clear();
      const result = await res.json();
      elements.performanceLog.textContent = `Deleted ${result.deleted_count} rows successfully`;
    } else {
      throw new Error('Batch delete request failed');
    }
  } catch (err) {
    console.error(err);
    elements.performanceLog.textContent = '❌ Failed to delete selected rows';
  }
}
