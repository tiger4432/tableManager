import { API_BASE, pageLimit } from './config.js';
import { state } from './state.js';
import { elements } from './dom.js';
import { switchTable, fetchData } from './api.js';
import { setTransactionFilter, updateSelectedCellUI } from './ui.js';
import { updateGridSortState, updateLoadedCount, updatePaginationUI } from './grid.js';
import { setMatchCount } from './match_count.js';
import { countNav, ROUTES } from './effort_meter.js';

// Feature 3: Load audit log history from API
export async function loadHistory() {
  // [2c] The audit table's header and legend are siblings of the `<ul>`, so `innerHTML = ''`
  // on the list leaves them alone. ONE place decides whether they show, here rather than in
  // each of the four tab handlers -- every switch calls this.
  elements.timelineContainer?.classList.toggle('audit-table', state.activeHistoryTab === 'global');
  if (state.activeHistoryTab === 'global') {
    elements.timeline.innerHTML = '<li class="timeline-empty">Loading global history...</li>';
    try {
      const res = await fetch(`${API_BASE}/audit_logs/recent?limit_groups=100`);
      // THE SAME ENVELOPE, OPENED BY THE SAME READER. This route answered with a bare array
      // until 2026-08-11 and now answers `{groups, truncated, next_cursor, ...}` — the shape the
      // row/cell history routes already used. `state.globalHistoryData = await res.json()` would
      // put that OBJECT where `renderGlobalTimeline` calls `.forEach` and `appendHistoryLocally`
      // calls `.find`, so the panel dies on load and every live WebSocket update after it.
      // The list key is `groups`, not `logs`, because that is what this route returns — each
      // group carries a `logs` of its own. A bare array is still read as a complete list.
      const { logs: groups } = readHistoryPage(await res.json(), 'groups');
      state.globalHistoryData = groups;
      renderGlobalTimeline();
    } catch (err) {
      console.error('Failed to load global history', err);
      elements.timeline.innerHTML = '<li class="timeline-empty" style="color:var(--color-danger)">Failed to load global history log</li>';
    }
    return;
  }

  if (!state.selectedCell) {
    // No target, so no position to page from. Retiring the session here too keeps a cursor from
    // outliving the list it names.
    beginHistorySession();
    elements.timeline.innerHTML = '<li class="timeline-empty">Select a cell to view history</li>';
    return;
  }

  elements.timeline.innerHTML = '<li class="timeline-empty">Loading history...</li>';

  // A FRESH LOAD OPENS A NEW PAGING SESSION. Everything below is reset BEFORE the request goes
  // out, not after it lands: between the two, a 더 보기 from the previous cell can still be in
  // flight, and the stale cursor it would append against belongs to another row's history.
  const session = beginHistorySession();

  const { rowId, colId } = state.selectedCell;
  const url = historyUrl(rowId, colId);

  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const page = readHistoryPage(await res.json());
    // Superseded while in flight — the operator is looking at a different list now.
    if (session !== state.cellRowHistorySession) return;
    state.cellRowHistoryData = page.logs;
    state.cellRowHistoryCursor = page.nextCursor;
    state.cellRowHistoryTruncated = page.truncated;
    state.cellRowHistoryLoaded = page.logs.length;
    // Cell route only; `null` on the row route. Assigned BEFORE the render because the empty
    // state reads it — it is the difference between "이 행엔 이력이 없다" and "기록은 있는데
    // 이 화면이 못 보여준다".
    state.cellRowHistoryRowTotal = page.rowHistoryTotal;
    state.cellRowHistoryRowTotalIsFloor = page.rowHistoryTotalIsFloor;
    renderTimeline(state.cellRowHistoryData);
  } catch (err) {
    if (session !== state.cellRowHistorySession) return;
    console.error('Failed to load history', err);
    elements.timeline.innerHTML = '<li class="timeline-empty" style="color:var(--color-danger)">Failed to load history log</li>';
  }
}

// The row-history or cell-history endpoint for the active tab. One spelling, because the pager
// has to rebuild the SAME url `loadHistory` used — a second copy that drifts would page the row
// endpoint while the sidebar shows the cell tab, and every appended row would look plausible.
function historyUrl(rowId, colId, cursor = null) {
  let url = state.activeHistoryTab === 'cell'
    ? `${API_BASE}/tables/${state.currentTable}/rows/${rowId}/cells/${colId}/history`
    : `${API_BASE}/tables/${state.currentTable}/rows/${rowId}/history`;
  if (cursor) url += `?cursor=${encodeURIComponent(cursor)}`;
  return url;
}

// Open a new paging session and return its token. Callers compare the token back after every
// await; anything that does not match belongs to a list that has been replaced.
function beginHistorySession() {
  state.cellRowHistoryCursor = null;
  state.cellRowHistoryTruncated = false;
  state.cellRowHistoryLoaded = 0;
  // Cleared here with the rest of the envelope, not just overwritten on arrival: a count that
  // outlived the cell it described would put "행 이력 12건" under a different row's empty tab —
  // a disclosure that is confidently wrong is worse than the one that was missing.
  state.cellRowHistoryRowTotal = null;
  state.cellRowHistoryRowTotalIsFloor = false;
  state.cellRowHistorySession += 1;
  return state.cellRowHistorySession;
}

// [History paging] Read one history response into the three things the timeline needs.
//
// 🔴 THE RESPONSE IS AN ENVELOPE, NOT THE LIST. All three history routes used to answer with a
//    bare array — for `/history` that was every audit row the target had ever accumulated,
//    measured at 300,019 rows / 119 MB / 18.9 s on a deep fixture, on every single click. They
//    now answer `{<list>, truncated, next_cursor, ...}`. Assigning that object where an array
//    used to go is what breaks the sidebar outright, so this is the ONE place that opens it.
//
// ONE READER, TWO LIST NAMES. `/history` calls its list `logs` because it returns audit rows;
// `/audit_logs/recent` calls its list `groups` because it returns transaction groups, each with
// a `logs` of its own. `listKey` is which of the two to open — NOT a second reader, because a
// parallel copy is how the two shapes start drifting apart. The RESULT field stays `logs` in
// both cases: it is "this page's list", and the caller names it (`const { logs: groups } = …`).
//
// A BARE ARRAY IS STILL READ, AND READ AS A COMPLETE LIST — which is exactly what it is. An
// unpaged server returns everything, so "not truncated, no cursor" is the true description of
// its answer, not a fallback that hides a cap.
//
// `truncated` REQUIRES THE CURSOR. On `/history` the server's contract is that `next_cursor` is
// non-null exactly when `truncated` is true; requiring both here means a `truncated: true` that
// arrives without a usable position can never paint a control that has nowhere to go. That state
// is the "looks clickable, does nothing" failure, and it is cheaper to make it unrepresentable.
// ⚠️ `/audit_logs/recent` CAN legitimately send `truncated` with a null cursor (a live merge that
// trims the projection loses its resume position), and the sidebar reads that as "not truncated"
// — correct today only because the global tab paints no pager at all. Anything that gives it one
// must read that third state from the body, not from this collapse.
// 🔴 UNKNOWN KEYS USED TO BE DROPPED HERE, AND THAT IS WHY NOTHING BROKE AND NOTHING SHOWED.
//    `row_history_total`/`row_history_truncated` have been on the wire since `721b175`; this
//    reader threw them away, so the cell tab kept drawing one "no history" for two different
//    facts. They are carried through as `rowHistoryTotal`/`rowHistoryTotalIsFloor`.
//    `row_history_truncated` is renamed on the way in ON PURPOSE: in this module `truncated`
//    means "the LIST is capped, page for more" and drives the 더 보기 control, while this one
//    means "the COUNT is a lower bound". One word for two facts is how a pager ends up hanging
//    off a number. `rowHistoryTotal` is `null` on the ROW route BY CONTRACT (not a missing
//    field) — there `returned`/`truncated` already describe that same population.
export function readHistoryPage(body, listKey = 'logs') {
  if (Array.isArray(body)) {
    return { logs: body, truncated: false, nextCursor: null, rowHistoryTotal: null, rowHistoryTotalIsFloor: false };
  }
  const list = body ? body[listKey] : null;
  const logs = Array.isArray(list) ? list : [];
  const raw = body ? body.next_cursor : null;
  const nextCursor = (typeof raw === 'string' && raw) ? raw : null;
  const rowTotal = body ? body.row_history_total : null;
  return {
    logs,
    truncated: !!(body && body.truncated) && !!nextCursor,
    nextCursor,
    rowHistoryTotal: typeof rowTotal === 'number' ? rowTotal : null,
    rowHistoryTotalIsFloor: !!(body && body.row_history_truncated),
  };
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
/**
 * The row's kind, as a pill.
 *
 * 🔴 DERIVED FROM THE BRANCH THAT ALREADY PICKS THE COLOUR, not from a new taxonomy. Mockup 2c
 * names seven kinds (MANUAL/PASTE/INGEST/OVERWRITE/BATCH/DELETE/SYNC); the audit rows do not
 * carry that distinction -- they carry `column_name`, `source_name` and `total_count`, which is
 * the six-way split this file has always drawn in colour. Inventing the other seven would put a
 * classification on screen that nothing computes.
 */
/**
 * An absent value, in one glyph.
 *
 * `formatVal` writes 「비어있음」 / 「삭제됨」, which is right in the card timeline where there is
 * room for a sentence. In a 150px cell those words crowd out the value that is actually there,
 * and the mockup writes `—` for the same state. `formatVal` is UNCHANGED -- the Row tab and the
 * transaction sub-list still read it -- because this is one surface's rendering, not a new rule
 * about what absence means.
 */
function auditVal(value, isOld) {
  if (value === null || value === undefined || value === '') return '—';
  return formatVal(value, isOld);
}

function auditKind(group, baseLog, isSummary) {
  if (isSummary) {
    if (group.logs.every(log => log.column_name === 'DELETE')) return { label: 'DELETE', cls: 'kind-delete' };
    if (group.logs.every(log => log.column_name === 'CREATE')) return { label: 'CREATE', cls: 'kind-create' };
    return { label: 'BATCH', cls: 'kind-batch' };
  }
  const col = baseLog.column_name;
  if (col === 'CREATE') return { label: 'CREATE', cls: 'kind-create' };
  if (col === 'DELETE') return { label: 'DELETE', cls: 'kind-delete' };

  const source = baseLog.source_name || '';
  const byHand = source === 'user';
  const byPaste = /paste/i.test(source);
  // OVERWRITE beats MANUAL and PASTE, and only for a HUMAN source: replacing a value someone
  // already had is a different act from filling a blank, and it is the one worth spotting in a
  // scan. A cell whose previous value was absent stays MANUAL/PASTE -- which is why the rows
  // the grid paints as 「미상」 do not turn into overwrites: absent reaches here as null.
  if ((byHand || byPaste) && baseLog.old_value !== null && baseLog.old_value !== undefined && baseLog.old_value !== '') {
    return { label: 'OVERWRITE', cls: 'kind-overwrite' };
  }
  if (byPaste) return { label: 'PASTE', cls: 'kind-paste' };
  if (byHand) return { label: 'MANUAL', cls: 'kind-manual' };
  // A file name is an ingest -- that is what the parser writes into `source_name`.
  if (/\.[a-z0-9]{2,4}$/i.test(source)) return { label: 'INGEST', cls: 'kind-ingest' };
  if (source === 'custom_script') return { label: 'SCRIPT', cls: 'kind-script' };
  if (col === 'ROW_UPDATE') return { label: 'AUTO', cls: 'kind-auto' };
  return { label: 'SYSTEM', cls: 'kind-auto' };
}

/**
 * 그룹이 건드린 «대상 표». 그룹은 트랜잭션이고, 한 트랜잭션은 표를 «여럿» 건드릴 수 있습니다.
 *
 * 🔴 그래서 첫 로그의 `table_name` 을 «대표»로 쓰지 않습니다 -- 순서 없는 집합에서
 *    대표를 고르는 것이고, 둘째 표가 끼는 날 조용히 틀립니다.
 *
 * 🔴 그리고 «들고 있는 로그가 전부가 아닐 수 있습니다». `/audit_logs/recent` 는 그룹마다
 *    로그를 «표본»으로 줍니다 (실측 2026-08-31: 100 그룹 중 98 이 logs 1 개 · total_count 는
 *    128~1000). 그런 그룹에서 「표는 하나」라고 말하면 표본 하나를 집합이라 부르는 것입니다.
 *    그래서 표본이 일부일 때는 … 를 붙여 «더 있을 수 있다»를 말합니다.
 *    펼치면 서버가 나머지를 가져오고, 그때는 이 함수가 정확해집니다.
 */
export function auditTargetTable(group) {
  const logs = (group && Array.isArray(group.logs)) ? group.logs : [];
  const names = [...new Set(logs.map((log) => log && log.table_name).filter(Boolean))];
  if (!names.length) return '';
  // total_count 가 없으면 NaN 이고, NaN 은 어떤 `<` 비교도 false 로 만듭니다
  // -- 즉 «완전함»으로 읽힙니다. 그것이 맞는 동작이라 대체값을 안 둡니다
  // (넣어 봤는데 «어떤 입력에서도» 답이 같아서 죽은 줄이었고, 변이가 그걸 잡았습니다).
  const total = Number(group && group.total_count);
  const sampled = logs.length < total;
  // 여럿임이 «표본으로 이미 증명된» 때만 수를 붙입니다 (하한입니다).
  const more = names.length > 1 ? ` +${names.length - 1}` : '';
  return `${names[0]}${more}${sampled ? ' …' : ''}`;
}

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

  // [2c] A ROW, not a card. The class names and the nesting roles are unchanged -- the click,
  // expand and Tx-filter handlers below query `.timeline-card`, `.tx-tag`, `.filter-tx-btn` and
  // `.expand-indicator`, and all four are still here. Only the layout changed.
  li.classList.add('audit-row');
  const kind = auditKind(group, baseLog, isSummary);
  // △소유자: 「변경이력 문구에서 맨앞에 ., -, -> 빼줘」. A row that CREATED a value has no
  // 「from」, so a dash and an arrow in front of it are punctuation standing in for nothing.
  const hadOldValue = baseLog.old_value !== null && baseLog.old_value !== undefined && baseLog.old_value !== '';
  // `toLocaleTimeString()` writes 「오후 11:31:31」 in this locale, which does not fit 58px and
  // wrapped the cell to two lines. The mockup's `09:31:12` is what a scan needs: fixed width,
  // no marker to read past. Built from the parts rather than a locale option so the width is
  // the same on every machine.
  const stamp = new Date(baseLog.timestamp);
  const timeStr = [stamp.getHours(), stamp.getMinutes(), stamp.getSeconds()]
    .map(part => String(part).padStart(2, '0')).join(':');
  // 대상 표는 «줄을 늘리지 않고» 이 칸 안에 들어갑니다. 묶음 줄은 원래 여기에 표 이름을
  // 그렸고(다만 첫 로그에서 가져왔고), 낱개 줄은 표를 «아예 안 보여 줬습니다» --
  // 소유자가 본 것이 그쪽입니다.
  const targetTable = auditTargetTable(group);
  const rowKey = baseLog.business_key || baseLog.row_id.slice(0, 8);
  const targetKey = isSummary
    ? (targetTable || baseLog.table_name)
    : (targetTable ? `${targetTable} · ${rowKey}` : rowKey);
  const targetCol = isSummary
    ? `${group.total_count} ROWS`
    : baseLog.column_name;

  li.innerHTML = `
    <div class="timeline-card ${colorClass} ${isSummary ? 'summary-card' : ''}" title="${displayTitle}">
      <div class="audit-cell audit-time">${timeStr}</div>
      <div class="audit-cell audit-user">${user}</div>
      <div class="audit-cell audit-kind"><span class="audit-pill ${kind.cls}">${kind.label}</span></div>
      <div class="audit-cell audit-target">
        <span class="audit-target-key">${targetKey}</span>
        <span class="audit-target-col">${targetCol}</span>
      </div>
      <div class="audit-cell audit-change">
        ${hadOldValue ? `<span class="val-old">${auditVal(baseLog.old_value, true)}</span><span class="val-arrow">→</span>` : ''}
        <span class="val-new">${auditVal(baseLog.new_value, false)}</span>
      </div>
      ${txId ? `<div class="audit-cell audit-tx tx-tag" data-tx-id="${txId}"><span class="filter-tx-btn" data-tx-id="${txId}" title="이 트랜잭션만 보기">…${txId.slice(-8)}</span>${isSummary ? '<span class="expand-indicator">▶</span>' : ''}</div>` : '<div class="audit-cell audit-tx"></div>'}
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
            // 이제 그룹의 로그를 «전부» 들고 있습니다. 그러면 접힌 줄의 … 가 거짓말이 됩니다 --
            // «더 있을 수 있다»는 표시인데 이제 없다는 것을 압니다. 그 칸만 고칩니다:
            // 줄을 통째로 다시 그리면 방금 펌친 것이 접힙니다.
            const keyEl = li.querySelector('.audit-target-key');
            if (keyEl) keyEl.textContent = auditTargetTable(group) || keyEl.textContent;
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
    elements.timeline.appendChild(createHistoryEmptyDom());
    return;
  }

  logs.forEach(log => {
    const li = createTimelineItemDom(log);
    elements.timeline.appendChild(li);
  });

  renderHistoryMore();
}

// [Cell history] THE EMPTY SLOT IS TWO STATES, AND IT USED TO BE ONE SENTENCE.
//
// 🔴 An empty cell tab is NOT "no history". Machine writes — parsers, chains, scripts — record
//    ONE audit row per ROW with the literal `ROW_UPDATE` in the column-name slot, so the cell
//    route's `column_name == col` filter can never match them. Isolated `assy_qa` measurement
//    2026-08-11 (this workstation, NOT a production figure): 225,586 of 239,786 audit rows
//    (94.08%) are `ROW_UPDATE`, and 225,101 rows carry machine history and not one per-column
//    entry — on every one of those, every cell tab is empty while the row tab is full. Drawing
//    both cases as `No change history recorded.` told the operator the records did not exist.
//    They existed; they were absent FROM ONE SCREEN, which is why nobody ever reported it.
//
// THE FIX IS A DISCLOSURE, NOT A RECONSTRUCTION. The count comes from the envelope the server
// already sends. It is NEVER derived by parsing the machine summary string: that value is a
// RENDERED SENTENCE (`f"{col}: {val}"` joined on ", ", NULL written as the Korean word 비어있음
// so integer 0 and string "0" are indistinguishable) and a live `wafer_map_metadata` record
// reads `grid_metadata: {"grid_cols": 2, "grid_rows": 2, ...}` — splitting that on ", " invents
// a column named `"grid_rows"` that does not exist. Presentation turned back into data does not
// produce the missing history, it produces confidently wrong history.
//
// THE COUNT ALONE WOULD BE A DEAD END, so the fact carries the way out of it: the row tab is one
// click away, on the existing tab button rather than a second copy of its wiring.
function createHistoryEmptyDom() {
  const li = document.createElement('li');
  // Keeps the `.timeline-empty` class in BOTH states: `renderTimelineIncremental` finds and
  // removes the empty slot by that selector when a live WebSocket log arrives.
  li.className = 'timeline-empty';

  const total = state.cellRowHistoryRowTotal;
  // `null` on the row tab (contract) and `0` when the row really has nothing — same answer.
  if (state.activeHistoryTab !== 'cell' || !total || total <= 0) {
    li.textContent = '기록 없음';
    return li;
  }

  li.classList.add('has-row-history');

  const note = document.createElement('div');
  note.className = 'timeline-empty-note';
  note.textContent = '이 셀 기록 없음';
  li.appendChild(note);

  const btn = document.createElement('button');
  btn.type = 'button';
  // Same control the truncated-list pager uses, deliberately: this row is the same kind of thing
  // — "there is more, and here is where it is" — and a second visual vocabulary for it would
  // only make the panel harder to read.
  btn.className = 'timeline-more-btn';
  // 🔴 `이상` IS NOT DECORATION. The server probes this count with a cap, so a capped answer is a
  //    FLOOR. Printing it bare would state an exact number the server never claimed.
  btn.textContent = state.cellRowHistoryRowTotalIsFloor
    ? `행 이력 ${total.toLocaleString()}건 이상 보기`
    : `행 이력 ${total.toLocaleString()}건 보기`;
  btn.addEventListener('click', () => {
    // The row tab's own button, not a reimplementation of it. Switching tabs here directly would
    // mean a second copy of the active-class bookkeeping, the reference-view teardown and the
    // reload — and the copy is what drifts.
    elements.tabRowBtn?.click();
  });
  li.appendChild(btn);

  return li;
}

// [History paging] The one control at the end of a capped list, and the only thing on this
// screen that says the list IS capped. Appended last, so `renderTimelineIncremental` — which
// prepends live logs at `firstChild` — keeps it at the bottom without knowing it exists.
//
// A COMPLETE LIST CARRIES NO CONTROL. That is the whole affordance: its presence is the fact.
function renderHistoryMore() {
  if (!state.cellRowHistoryTruncated || !state.cellRowHistoryCursor) return;
  elements.timeline.appendChild(createHistoryMoreDom());
}

// The label the operator reads. `일부만` is this client's existing word for a server-truncated
// list (map_editor.js puts it on a truncated overlay) and `더 보기` its existing pager — one
// spelling each, not a third invented here.
//
// 🔴 THE FACT LEADS, THE ACTION FOLLOWS. `더 보기` on its own reads as "there is more if you
//    feel like it"; the question an operator actually has in front of a history list is "is
//    this the whole thing?". A trailing row that only offers to fetch answers that question by
//    implication, and by implication is how a capped list passes for a complete one.
function historyMoreLabel() {
  return `일부만 (${state.cellRowHistoryLoaded}건) · 더 보기`;
}

export function createHistoryMoreDom() {
  const li = document.createElement('li');
  li.className = 'timeline-more';

  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'timeline-more-btn';
  btn.textContent = historyMoreLabel();

  btn.addEventListener('click', () => {
    // After a 400 the cursor names a position the server cannot decode, so the same token can
    // only fail again. The control stops being a pager and becomes the one move that recovers.
    if (btn.dataset.mode === 'reload') {
      loadHistory();
      return;
    }
    loadMoreHistory(btn);
  });

  li.appendChild(btn);
  return li;
}

// A page that did not arrive. The rows already on screen are untouched — losing them would cost
// the operator more than the page they asked for — and the control stays live, because the
// cursor is still good: a transport failure says nothing about the position.
function markMoreFailed(btn) {
  delete btn.dataset.mode;
  btn.classList.add('is-error');
  btn.disabled = false;
  btn.textContent = '조회 실패 · 재시도';
}

// The position itself is unusable (400). Retrying it forever is the trap; a reload from the top
// is the only thing that can produce a valid cursor again.
function markMoreLost(btn) {
  btn.dataset.mode = 'reload';
  btn.classList.add('is-error');
  btn.disabled = false;
  btn.textContent = '위치 만료 · 새로고침';
}

// [History paging] Fetch the next page and APPEND it. Never replaces what is on screen.
export async function loadMoreHistory(btn) {
  if (!btn || btn.disabled) return;
  const cursor = state.cellRowHistoryCursor;
  if (!cursor || !state.selectedCell) return;

  const session = state.cellRowHistorySession;
  const { rowId, colId } = state.selectedCell;
  const url = historyUrl(rowId, colId, cursor);

  btn.disabled = true;
  btn.classList.remove('is-error');
  delete btn.dataset.mode;
  btn.textContent = '조회 중…';

  let page;
  try {
    const res = await fetch(url);
    if (session !== state.cellRowHistorySession) return;
    if (res.status === 400) {
      markMoreLost(btn);
      return;
    }
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    page = readHistoryPage(await res.json());
  } catch (err) {
    if (session !== state.cellRowHistorySession) return;
    console.error('Failed to load more history', err);
    markMoreFailed(btn);
    return;
  }

  // The session moved on while this was in flight (another cell, another tab, a refresh). These
  // rows are real and they belong to a list that is no longer on screen.
  if (session !== state.cellRowHistorySession) return;

  page.logs.forEach(log => {
    state.cellRowHistoryData.push(log);
    elements.timeline.insertBefore(createTimelineItemDom(log), btn.parentElement);
  });
  state.cellRowHistoryLoaded += page.logs.length;
  state.cellRowHistoryCursor = page.nextCursor;
  state.cellRowHistoryTruncated = page.truncated;

  if (!page.truncated) {
    // Nothing further to page toward: the list is complete now, and a complete list says so by
    // carrying no control at all.
    btn.parentElement.remove();
    return;
  }

  btn.disabled = false;
  btn.textContent = historyMoreLabel();
}

// Render overall table audit history logs (recent transactions)
/**
 * The audit filter strip, mockup 2c.
 *
 * 🔴 CLIENT-SIDE OVER WHAT IS ALREADY LOADED, and the count says so: 「N건 중 M」 counts the
 * groups in hand, not the table. `/audit_logs/recent` EMITS `next_cursor` but its signature
 * does not ACCEPT one, so there is no honest way to claim these filters searched all history.
 *
 * Options come from the loaded groups rather than a fixed list, so a source this screen has
 * never seen still gets an entry the day it first appears.
 */
function auditFilterState() {
  return {
    user: document.getElementById('audit-filter-user')?.value || '',
    kind: document.getElementById('audit-filter-kind')?.value || '',
    when: document.getElementById('audit-filter-when')?.value || ''
  };
}

function groupKindLabel(group) {
  const baseLog = group.logs?.[0];
  if (!baseLog) return '';
  return auditKind(group, baseLog, group.total_count > 1).label;
}

function fillAuditFilterOptions(groups) {
  const fill = (id, values) => {
    const select = document.getElementById(id);
    if (!select) return;
    const chosen = select.value;
    // Option 0 is the "all" row and lives in the markup, so it is kept and the rest rebuilt --
    // clearing everything would drop the label the mockup names.
    while (select.options.length > 1) select.remove(1);
    values.forEach(value => {
      const option = document.createElement('option');
      option.value = value; option.textContent = value;
      select.appendChild(option);
    });
    // A choice that no longer exists in the data must not go on filtering invisibly.
    select.value = values.includes(chosen) ? chosen : '';
  };
  fill('audit-filter-user', [...new Set(groups.map(g => g.logs?.[0]?.updated_by || 'system'))].sort());
  fill('audit-filter-kind', [...new Set(groups.map(groupKindLabel).filter(Boolean))].sort());
}

function auditFilterPasses(group, filters) {
  const baseLog = group.logs?.[0];
  if (!baseLog) return false;
  if (filters.user && (baseLog.updated_by || 'system') !== filters.user) return false;
  if (filters.kind && groupKindLabel(group) !== filters.kind) return false;
  if (filters.when) {
    const stamp = new Date(baseLog.timestamp);
    const now = new Date();
    if (filters.when === 'today' && stamp.toDateString() !== now.toDateString()) return false;
    if (filters.when === '7d' && now - stamp > 7 * 24 * 60 * 60 * 1000) return false;
  }
  return true;
}

export function renderGlobalTimeline() {
  elements.timeline.innerHTML = '';
  const count = document.getElementById('audit-filter-count');

  if (!state.globalHistoryData || state.globalHistoryData.length === 0) {
    elements.timeline.innerHTML = '<li class="timeline-empty">No database history recorded.</li>';
    if (count) count.textContent = '';
    return;
  }

  fillAuditFilterOptions(state.globalHistoryData);
  const filters = auditFilterState();
  const shown = state.globalHistoryData.filter(group => auditFilterPasses(group, filters));

  shown.forEach((group) => {
    const li = createGlobalTimelineItemDom(group);
    if (li) elements.timeline.appendChild(li);
  });

  if (!shown.length) {
    elements.timeline.innerHTML = '<li class="timeline-empty">조건에 맞는 기록이 없습니다.</li>';
  }
  if (count) count.textContent = `${state.globalHistoryData.length}건 중 ${shown.length}`;
}

/** Re-render on a filter change. The selects are static markup, so this installs once. */
export function installAuditFilters() {
  ['audit-filter-user', 'audit-filter-kind', 'audit-filter-when'].forEach(id => {
    document.getElementById(id)?.addEventListener('change', () => renderGlobalTimeline());
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
        setMatchCount(elements.totalRowsCount, cached.total);
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
    setMatchCount(elements.totalRowsCount, result.total);

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
