import { API_BASE, pageLimit, READ_AGAIN_MS } from './config.js';
import { ABSENT, isCount } from './absent.js';
import { LOADING, UPDATING, unitText } from './ui_words.js';
import { escapeHtml } from './utils.js';
import { localStamp, localClock, NO_TIME } from './server_time.js';
import { widestCell } from './cell_fit.js';
import { markWork } from './ui_stall.js';
import { sayStopped } from './write_guard.js';
import { worldList } from './world.js';
import { narrowingTail } from './narrowing.js';
import { state, gridFetch } from './state.js';
import { elements } from './dom.js';
import { switchTable, fetchData, overlayStagedEdits, copyRows, refusalText, askMatchCount, fillWriters } from './api.js';
import { rowsKey } from './rows_key.js';
import { pageLooks, saidLooksChanged } from './grid_look.js';
import { setTransactionFilter, updateSelectedCellUI } from './ui.js';
import { updateGridSortState, updateLoadedCount, updatePaginationUI, sortQueryTail } from './grid.js';
import { countOf, setMatchCount } from './match_count.js';
import { saysTruncated } from './truncation.js';
import { countNav, ROUTES } from './effort_meter.js';

// Feature 3: Load audit log history from API - on the history board (lead 10-28): another tab or another cell cuts the
// read out; the same question asked while it reads (three socket events, a table switch, a tab click) is read once more
// when it ends.
export function loadHistory() {
  const cell = state.selectedCell;
  const question = state.activeHistoryTab === 'global' ? 'global'
    : `${state.activeHistoryTab}:${state.currentTable}:${cell ? `${cell.rowId}:${cell.colId}` : ''}`;
  return state.historyReads.ask(question, readHistory);
}

let historyRereadTimer = null;

/** The server or the operator says read again: the held Global list is old, and the shown tab is read again. */
export function rereadHistory() {
  state.globalHistoryStale = true;
  return loadHistory();
}

async function readHistory(read) {
  // [2c] The audit table's header and legend are siblings of the `<ul>`, so `innerHTML = ''`
  // on the list leaves them alone. ONE place decides whether they show, here rather than in
  // each of the four tab handlers -- every switch calls this.
  // 🔴 «둘»을 놓는다. `audit-table` 은 겉모양(격자·셀·머리줄·배지)이고 `tab-global` 은
  //    「Global 탭이다」는 신호다. 대기열 표가 같은 모양을 입어야 해서 갈랐다 (2026-09-22).
  //    겉모양만 입은 화면에 Global 전용 동작이 따라가면 안 된다.
  const onGlobal = state.activeHistoryTab === 'global';
  elements.timelineContainer?.classList.toggle('audit-table', onGlobal);
  elements.timelineContainer?.classList.toggle('tab-global', onGlobal);
  if (state.activeHistoryTab === 'global') {
    // The Global list is the whole database's, not the open table's: a held list that missed nothing is drawn again, not
    // read again (A 10-28: the read costs what piled up since the last one - 56 s on a box with 8 million new rows).
    if (!state.globalHistoryStale && state.globalHistoryData.length) {
      renderGlobalTimeline();
      return;
    }
    // A held list stays drawn while the read is out, said «Updating» (owner 11-09 «쓰는 중에도 90 % 가 페치 중이거나 비어
    // 있음»: every capped notification wiped it to Loading). Only an empty panel says Loading.
    if (state.globalHistoryData.length) {
      state.globalHistoryUpdating = true;
      renderGlobalTimeline();
    } else {
      elements.timeline.innerHTML = '<li class="timeline-empty">Loading global history...</li>';
    }
    // Cleared as the read goes out: logs that come while it reads set it again, and the board's repeat reads them.
    state.globalHistoryStale = false;
    let readWhole = false;
    try {
      const res = await fetch(`${API_BASE}/audit_logs/recent?limit_groups=100`, { signal: read.signal });
      if (!read.current()) return;
      // 🔴 F-11. There was no `res.ok` here, and the catch below could not stand in for
      //    one: a 500 answers with a VALID JSON body (`{detail: …}`), so `res.json()`
      //    resolves, `readHistoryPage` looks for `groups`, finds no such key, and returns
      //    `logs: []` (see its `Array.isArray(list) ? list : []`). The panel then drew its
      //    empty state -- 「no records」 for a route that had FAILED. Silence would have
      //    been better; this was an answer, and a wrong one.
      // 🔵 Throwing hands it to the catch that is already here, which paints the red
      //    failure line. 「could not read」 and 「nothing to read」 stop sharing a pixel.
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      // THE SAME ENVELOPE, OPENED BY THE SAME READER. This route answered with a bare array
      // until 2026-08-11 and now answers `{groups, truncated, next_cursor, ...}` — the shape the
      // row/cell history routes already used. `state.globalHistoryData = await res.json()` would
      // put that OBJECT where `renderGlobalTimeline` calls `.forEach` and `appendHistoryLocally`
      // calls `.find`, so the panel dies on load and every live WebSocket update after it.
      // The list key is `groups`, not `logs`, because that is what this route returns — each
      // group carries a `logs` of its own. A bare array is still read as a complete list.
      // 🔴 F-12. The envelope is opened by the shared reader, but TRUNCATION IS READ FROM THE
      //    BODY. `readHistoryPage` collapses `truncated && next_cursor` into one flag, which is
      //    right for `/history` and wrong here -- and reading the body does not depend on
      //    whether the cursorless state is reachable, so a query predicate changing upstream
      //    cannot silently turn this back off.
      const body = await res.json();
      // superseded while the body came - the operator is looking at another list now
      if (!read.current()) return;
      const page = readHistoryPage(body, 'groups');
      state.globalHistoryData = page.logs;
      state.globalHistoryTruncated = saysTruncated(body && body.truncated) === true;
      // The position to resume from, and the count the control reads. `globalHistoryLoaded` is
      // deliberately NOT `globalHistoryData.length`: live WebSocket logs are unshifted into that
      // array, so its length drifts upward on its own — the defect `cellRowHistoryLoaded` exists
      // to prevent, arriving on the other tab.
      state.globalHistoryCursor = page.nextCursor;
      state.globalHistoryLoaded = page.logs.length;
      // the server's walk or merge runs behind this answer: it is drawn, and read again once that has had its time
      state.globalHistoryUpdating = Boolean(body && body.updating === true);
      renderGlobalTimeline();
      if (state.globalHistoryUpdating) {
        clearTimeout(historyRereadTimer);
        historyRereadTimer = setTimeout(() => {
          if (state.activeHistoryTab === 'global') rereadHistory();
        }, READ_AGAIN_MS);
      }
      readWhole = true;
    } catch (err) {
      if (!read.current()) return;
      state.globalHistoryUpdating = false;
      console.error('Failed to load global history', err);
      elements.timeline.innerHTML = '<li class="timeline-empty" style="color:var(--color-danger)">Failed to load global history log</li>';
    } finally {
      // cut, refused or failed: the held list is still the old one
      if (!readWhole) state.globalHistoryStale = true;
    }
    return;
  }

  if (!state.selectedCell) {
    // No target, so no position to page from - the board's new ticket already retired the session; the envelope goes
    // too, so a cursor does not outlive the list it names.
    clearCellRowEnvelope();
    elements.timeline.innerHTML = '<li class="timeline-empty">Select a cell to view history</li>';
    return;
  }

  elements.timeline.innerHTML = '<li class="timeline-empty">Loading history...</li>';

  // A FRESH LOAD OPENS A NEW PAGING SESSION (the board's ticket). The envelope is reset BEFORE the request goes out, not
  // after it lands: between the two, a 더 보기 from the previous cell can still be in flight, and the stale cursor it
  // would append against belongs to another row's history.
  clearCellRowEnvelope();

  const { rowId, colId } = state.selectedCell;
  const url = historyUrl(rowId, colId);

  try {
    const res = await fetch(url, { signal: read.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const page = readHistoryPage(await res.json());
    // Superseded while in flight — the operator is looking at a different list now.
    if (!read.current()) return;
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
    if (!read.current()) return;
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

// The cell/row envelope back to empty, as a fresh list opens. The session token is the history board's ticket.
function clearCellRowEnvelope() {
  state.cellRowHistoryCursor = null;
  state.cellRowHistoryTruncated = false;
  state.cellRowHistoryLoaded = 0;
  // Cleared here with the rest of the envelope, not just overwritten on arrival: a count that
  // outlived the cell it described would put "행 이력 12건" under a different row's empty tab —
  // a disclosure that is confidently wrong is worse than the one that was missing.
  state.cellRowHistoryRowTotal = null;
  state.cellRowHistoryRowTotalIsFloor = false;
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
// ⚠️ `/audit_logs/recent` can carry `truncated` with a null cursor, and this reader folds that
// into "not truncated". THE GLOBAL TAB NO LONGER RELIES ON THAT FOLD -- it reads `truncated`
// from the body (see `loadHistory`), so the fold is confined to the `/history` contract it was
// written for.
// 🔴 THE STATED CAUSE HERE WAS 「a live merge that trims the projection loses its resume
//    position」. THAT PATH IS UNCONFIRMED: searching the server on 2026-09-06 found no such
//    merge. The one route to a null cursor that does exist is `audit_cache.py:316-319`, where a
//    null-stamped edge fails to encode -- and the comment above it calls that branch
//    unreachable. Two files, opposite claims; neither is settled here. Written as unconfirmed
//    rather than as fact, because the previous wording was used as evidence.
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
    truncated: saysTruncated(body && body.truncated) === true && !!nextCursor,
    nextCursor,
    rowHistoryTotal: typeof rowTotal === 'number' ? rowTotal : null,
    rowHistoryTotalIsFloor: !!(body && body.row_history_truncated),
  };
}

/** A person's write, by the server's own word for it (crud.USER_SOURCE) - selected by it, never by who it is not: the
 *  chain's writes are getting their rule's name as updated_by (lead 10-13), and «not system» would paint them a person's. */
const USER_SOURCE = 'user';
const byPerson = (log) => Boolean(log) && log.source_name === USER_SOURCE;

// Create single timeline list item DOM element
export function createTimelineItemDom(log) {
  const li = document.createElement('li');
  li.className = 'timeline-item';
  li.style.cursor = 'pointer';

  const isUser = byPerson(log);
  li.classList.add(isUser ? 'user-change' : 'system-change');
  if (log.is_row_deleted) {
    li.classList.add('deleted-row-log');
  }

  const isCurrentTx = log.transaction_id && log.transaction_id === state.currentTransactionId;
  if (isCurrentTx) {
    li.classList.add('active-tx-log');
  }

  // 🔴 `new Date(undefined)` 는 Invalid Date 이고, 그것을 그리면 화면에
  //    「Invalid Date」라는 «글자»가 나갑니다. 이 부류의 날짜 판입니다.
  const stamped = localStamp(log.timestamp);
  const dateStr = stamped === NO_TIME ? ABSENT : stamped;

  // 🔴 이 줄의 값은 «전부 서버가 실어 준 것»이고, 그중 둘은 «운영자가 친 셀 값»입니다
  //    (`old_value` · `new_value`). 이력은 그것을 «그대로» 되비추는 자리라, 이스케이프가 없으면
  //    표에 넣은 글자가 여기서 마크업이 됩니다. `formatVal` 은 평문만 돌려주므로(:934) 감싸도
  //    잃는 것이 없습니다.
  // ⚠️ 감싸는 것은 «값»뿐입니다. 아래 삼항이 만드는 `<div class="tx-tag">` 는 이 파일이 지은
  //    마크업이라 감싸면 화면에 태그가 «글자»로 찍힙니다 -- 안쪽 값만 감쌉니다.
  const txId = log.transaction_id;
  li.innerHTML = `
    <div class="timeline-time">${escapeHtml(dateStr)}</div>
    <div class="timeline-card">
      <div class="timeline-user">
        <span class="user-tag">${escapeHtml(log.updated_by)}</span>
        <span class="source-tag">${escapeHtml(log.source_name)}</span>
      </div>
      <div class="timeline-changes">
        <div class="change-detail">
          <span class="change-field">${escapeHtml(log.column_name)}</span>
          <div class="change-values">
            <span class="val-new">${escapeHtml(formatVal(log.new_value, false))}</span>
          </div>
        </div>
      </div>
      ${txId ? `<div class="tx-tag" data-tx-id="${escapeHtml(txId)}">Tx: ${escapeHtml(String(txId).slice(0, 8))}... <span class="filter-tx-btn" data-tx-id="${escapeHtml(txId)}" title="Filter table by this transaction">🔍</span></div>` : ''}
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

/** 서버가 원장 배치 영수증을 적는 칸. 이 낱말은 «응답의 키»이고 화면이 짓지 않습니다. */
export const LEDGER_BATCH_COLUMN = 'ledger_batch';
/** 체인 없이 들어온 배치가 모이는 버킷 이름 — 라우트가 내는 값 그대로. */
export const NO_TRANSACTION_BUCKET = 'no_tid';

/**
 * C-55 / S-117 — 원장 배치 영수증 «한 줄». 값들이지 문장이 아닙니다.
 *
 * 🔴 봉투가 «둘»입니다. 실측 픽스처(`contracts/ledger_receipt/vectors.json`, 라이브에서 뜬 것):
 *      ok      {rows, molecules, atoms_written, atoms_deduped, atoms_withdrawn, refused,
 *               reasons, translator_ver, world, status:'ok', error:null}
 *      failed  {source, world, status:'failed', error:'RuntimeError: …'}   ← «수가 하나도 없습니다»
 *    실패 쪽을 수 자리로 그리면 셋이 빈 칸이 되고, 빈 칸은 「안 쟀다」로 읽힙니다 — 그래서
 *    가르는 것은 `status` 이고, 실패는 «상태와 사유»로 그립니다(C-42 의 거절과 같은 부류).
 *
 * ⛔ 낱말은 «응답의 키 그대로»입니다(판정 177). 번역하면 서버가 키를 바꾸는 날 화면이
 *    «옛 이름으로» 옳아 보입니다.
 * ⛔ `error` 는 «이름»만 — 문장 전체를 타임라인 줄에 펴면 그 줄이 설명문이 됩니다
 *    (소유자 상설 2026-09-04). 전문이 필요하면 펼친 자리에 있습니다.
 * `world` 는 세상이 둘 이상일 때만 맨 앞에 — 한 이벤트가 켜진 세상마다 영수증을 남깁니다(서버 6922cd6cb).
 *    `worlds` 는 이 설치의 세상 목록(`/tables`)이고, 하나뿐이면 안 그립니다(총괄).
 */
export function ledgerReceiptLine(newValue, worlds) {
  const v = newValue && typeof newValue === 'object' && !Array.isArray(newValue) ? newValue : null;
  if (!v) return '';
  const world = worldList(worlds).length > 1 ? worldList(v.world)[0] || '' : '';
  const status = v.status == null ? '' : String(v.status);
  if (status && status !== 'ok') {
    // 🔴 「RuntimeError: a translator blew up」 -> 「RuntimeError」. 이름이 조작자가 찾는 것이고,
    //    문장은 이 줄의 자리가 아닙니다.
    const name = v.error == null ? '' : String(v.error).split(':')[0].trim();
    return [world, status, v.source == null ? '' : String(v.source), name].filter(Boolean).join(' · ');
  }
  const parts = world ? [world] : [];
  for (const key of ['atoms_written', 'atoms_deduped', 'refused']) {
    // ⚠️ 「수가 아니면」 그 마디를 «안 만듭니다» — 0 으로 그리면 「세 봤더니 0」이 되고,
    //    이 봉투에서 키가 없는 것은 「안 보냈다」입니다. 철자는 `absent.js` 하나뿐입니다.
    if (isCount(v[key])) parts.push(`${key} ${Number(v[key])}`);
  }
  if (status) parts.push(status);
  return parts.join(' · ');
}

// What a folded line is, said once - the kind pill, the card's title and its Row · column cell read it. 🔴 C-55: the
// ledger first - a failed receipt has two lines and would fold as a table edit. «All» for the same reason as DELETE ·
// CREATE: a mixed transaction is not named after one side.
const FOLDS = {
  ledger: { pill: 'LEDGER', cls: 'kind-ledger' },
  delete: { pill: 'DELETE', cls: 'kind-delete' },
  create: { pill: 'CREATE', cls: 'kind-create' },
  batch: { pill: 'BATCH', cls: 'kind-batch' },
};

/** The rows a transaction changed (owner 11-10: «바뀐 행수»; lead 11-12 ㄷ reverses lead 10-29's «the audit lines»): the
 *  recent list's changed_rows summed over its tables, «+» when one is the floor (the server counts to its cap) - the
 *  route's total_count after unfolding is the same quantity. With no counted table, a group that holds all its logs (one
 *  built from live logs, one read to its end) counts their rows; a sample says it does not know. */
export function changedRowsOf(group) {
  const tables = Array.isArray(group && group.changed) ? group.changed.filter((t) => t && isCount(t.changed_rows)) : [];
  if (tables.length) {
    return rowsText(tables.reduce((sum, t) => sum + Number(t.changed_rows), 0),
      tables.some((t) => t.changed_rows_truncated === true));
  }
  if (!holdsAll(group)) return `${ABSENT} rows`;
  const logs = group && Array.isArray(group.logs) ? group.logs : [];
  const rows = new Set(logs.map((log) => log && log.row_id).filter((id) => id && id !== '_BATCH_'));
  return unitText(rows.size.toLocaleString('en-US'), 'row');
}

/** «N rows», «N+ rows» when `floor` (the server counted to its cap). */
function rowsText(n, floor) {
  return unitText(`${Number(n).toLocaleString('en-US')}${floor ? '+' : ''}`, 'row');
}

function foldOf(group) {
  const kind = allLogsAre(group, LEDGER_BATCH_COLUMN) ? 'ledger'
    : allLogsAre(group, 'DELETE') ? 'delete'
      : allLogsAre(group, 'CREATE') ? 'create' : 'batch';
  return { kind, ...FOLDS[kind], count: changedRowsOf(group) };
}

/** A receipt's own word - the server's `receipt_label` (crud.receipt_log: «Ledger batch», «formula T.c»); a receipt
 *  written before it carried one is a ledger batch's. */
export function receiptLabel(newValue) {
  const label = newValue && typeof newValue === 'object' && typeof newValue.receipt_label === 'string'
    ? newValue.receipt_label.trim() : '';
  return label || 'Ledger batch';
}

/**
 * 이 묶음의 로그가 «전부» 그 칸인가. 목록 라우트는 묶음마다 대표 로그 «1건»만 싣으므로 실린 로그로
 * 세면 섞인 묶음이 한쪽 이름이 됩니다 — 고친 행 + 세상 둘 영수증(로그 셋)이 「LEDGER」로 접혔습니다
 * (구현자 c49217a06). 그래서 묶음의 칸 이름들(`summary_columns`)로 답합니다.
 */
function allLogsAre(group, column) {
  const columns = Array.isArray(group && group.summary_columns) ? group.summary_columns : [];
  return columns.length > 0 && columns.every((name) => name === column);
}

/**
 * 그 트랜잭션의 영수증이 쓰인 세상들 — 서버 `receipt_worlds`(쓰인 순서, c49217a06). 세상이 둘 이상인
 * 설치에서만 그립니다(세상 하나면 표시 없음). 세상 칸 없는 옛 영수증은 `—`.
 */
export function receiptWorldsLine(group, worlds) {
  const rows = Array.isArray(group && group.receipt_worlds) ? group.receipt_worlds : [];
  // The line stands on two or more worlds, or on any failure - a failed world must not read like a written one.
  if (!rows.length || (worldList(worlds).length < 2 && !rows.some((row) => row.failed > 0))) return '';
  return ['Ledger', ...rows.map((row) => `${row.world == null ? ABSENT : row.world}`
    + `${row.receipts > 1 ? ` ×${row.receipts}` : ''}`
    + `${row.failed > 0 ? ` (${row.failed} failed)` : ''}`)].join(' · ');
}

function auditKind(group, baseLog, isSummary) {
  if (isSummary) {
    const fold = foldOf(group);
    return { label: fold.pill, cls: fold.cls };
  }
  const col = baseLog.column_name;
  // 🔴 C-55. 종전엔 여기까지 흘러 «SYSTEM» 이 됐습니다 — 원장 배치가 다른 시스템 행과
  //    «같은 픽셀»이었고, 필터에서 갈라낼 방법이 없었습니다.
  if (col === LEDGER_BATCH_COLUMN) return { label: 'LEDGER', cls: 'kind-ledger' };
  if (col === 'CREATE') return { label: 'CREATE', cls: 'kind-create' };
  if (col === 'DELETE') return { label: 'DELETE', cls: 'kind-delete' };

  const source = baseLog.source_name || '';
  const byHand = byPerson(baseLog);
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
  // 여럿임이 «표본으로 이미 증명된» 때만 수를 붙입니다 (하한입니다).
  const more = names.length > 1 ? ` +${names.length - 1}` : '';
  return `${names[0]}${more}${holdsAll(group) ? '' : ' …'}`;
}

/** Whether a group holds all its logs. Once the transaction route has answered, its cursor says (null: every page read) -
 *  the route gives a row once and the list counts lines, so a count cannot. Before, the count: the list route sends one
 *  representative (A 1e4bbe748); no total_count is NaN, which no `<` holds - complete. */
function holdsAll(group) {
  if (group && 'nextCursor' in group) return !group.nextCursor;
  const logs = group && Array.isArray(group.logs) ? group.logs : [];
  return !(logs.length < Number(group && group.total_count));
}

/** Unfolding a group reads the transaction's first page when it holds a part of its logs and the route has not answered
 *  it yet - unfolded again, it keeps the pages «more» read (lead 11-12). */
export function needsTransactionRead(group) {
  return !(group && 'nextCursor' in group) && !holdsAll(group);
}

/** A group's line facts - THE seat the Global line, its filter and the filter's lists read (lead 11-13). Two shapes reach
 *  the list:
 *    the route     GET /audit_logs/recent (server main.py `_shape_recent_groups`): `logs` [] and `changed`, a table an
 *                  entry, newest first - {table_name, changed_rows, changed_rows_truncated, kinds, written_by, at}
 *    a live write  a broadcast's `created_logs` (server database/crud.py `_said_logs`, sent by main.py
 *                  `apply_batch_updates_endpoint` and the workers' batch_refresh), grouped by `appendHistoryLocally`:
 *                  `logs` [line, ...], no `changed`
 *  The route's facts are its entries' `kinds` and `written_by`: a group whose `changed` carries them is read from it,
 *  a live line joined to it or not; one whose `changed` counts rows only (the release before, a line beside its
 *  counts) is read from its line. -> {at, who [], kinds [{label, cls}], tables [{name, label, rows}], log}: `tables`
 *  newest first, `name` the table a press jumps to, `rows` its count or null; `log` the representative line, null in
 *  the route's shape. null for a group with neither. */
export function groupFacts(group) {
  const log = (group && Array.isArray(group.logs) && group.logs[0]) || null;
  const changed = Array.isArray(group && group.changed) ? group.changed.filter(Boolean) : [];
  if (changed.some((t) => Array.isArray(t.kinds))) {
    const words = (key) => [...new Set(changed.flatMap((t) => (Array.isArray(t[key]) ? t[key] : [])).filter(Boolean))];
    const who = words('written_by');
    return {
      at: changed[0].at || null,
      who: who.length ? who : ['system'],
      kinds: words('kinds').map((label) => ({ label, cls: 'kind-auto' })),
      tables: changed.filter((t) => t.table_name).map((t) => ({ name: t.table_name, label: t.table_name,
        rows: isCount(t.changed_rows) ? rowsText(t.changed_rows, t.changed_rows_truncated === true) : null })),
      log,
    };
  }
  if (!log) return null;
  return { at: log.timestamp, who: [log.updated_by || 'system'], kinds: [auditKind(group, log, group.total_count > 1)],
    tables: [{ name: log.table_name, label: auditTargetTable(group) || log.table_name, rows: null }], log };
}

/** The Table cell: a name a table the line names, each pressed to its first changed row (owner 11-13 «여러 표라며»);
 *  of several, those past the cell's first line fold into «+N» (foldTableNames), which unfolds the transaction. */
function tableNames(tables) {
  const names = tables.map((t) => `<span class="audit-target-table" data-wrap-ok data-table="${escapeHtml(t.name)}"`
    + ` title="${escapeHtml(t.rows ? `${t.label} · ${t.rows}` : t.label)}">${tablePieces(t.label)}</span>`);
  return names.join('') + (names.length > 1 ? `<span class="audit-tbl-more" hidden>+${names.length - 1}</span>` : '');
}

/** A Global line pressed (owner 11-13 «네비게이션»): `named` the table name pressed, else the line's first table. The
 *  line's own row when its line names a row of that table; else the first row the transaction changed there, asked of
 *  the transaction route (`?table=&limit=1`, owner 11-10 «바뀐 행 네비»). An answer with no row is said. */
async function goToLine(group, named) {
  const facts = groupFacts(group);
  const table = named ? named.dataset.table : facts && facts.tables.length ? facts.tables[0].name : null;
  if (!table) return undefined;
  const log = facts.log;
  if (log && log.row_id !== '_BATCH_' && log.table_name === table) return navigateToLog(log);
  const txId = group.transaction_id;
  try {
    const res = await fetch(`${API_BASE}/audit_logs/transaction/${encodeURIComponent(txId)}`
      + `?table=${encodeURIComponent(table)}&limit=1`);
    if (!res.ok) { sayStopped(await refusalText(res, '❌ Changed rows not read')); return undefined; }
    const body = await res.json();
    const row = (Array.isArray(body && body.logs) ? body.logs : []).find((one) => one && one.table_name === table);
    if (!row) { sayStopped(`No changed row of ${table} in this transaction`); return undefined; }
    return navigateToLog({ table_name: table, row_id: row.row_id, column_name: row.column_name, transaction_id: txId });
  } catch (err) {
    console.error('Failed to read the changed rows', err);
    sayStopped('❌ Changed rows not read');
    return undefined;
  }
}

export function createGlobalTimelineItemDom(group) {
  const txId = group.transaction_id;
  const facts = groupFacts(group);
  if (!facts) return null;
  const baseLog = facts.log;
  // the route's shape has no line to draw a cell from: its line is the transaction's, unfolded by the transaction route
  const isSummary = !baseLog || group.total_count > 1;

  const li = document.createElement('li');
  li.className = 'timeline-item';
  if (txId) {
    li.dataset.txId = txId;
  }

  const isCurrentTx = txId && txId === state.currentTransactionId;
  if (isCurrentTx) {
    li.classList.add('active-tx-log');
  }

  const user = facts.who.join(', ');
  const isUser = Boolean(baseLog) && byPerson(baseLog);
  li.classList.add(isUser ? 'user-change' : 'system-change');

  let displayTitle = '';
  let colorClass = '';

  const fold = isSummary ? foldOf(group) : null;
  // the title names the line's table; the route's shape names its tables
  const titleTable = baseLog ? baseLog.table_name : facts.tables.map((t) => t.name).join(', ');
  if (isSummary) {
    if (fold.kind === 'ledger') {
      // ③ 'no_tid' 는 «이름»이지 빈 칸이 아닙니다 — 백필·소급은 체인 트랜잭션이 «없는» 것입니다.
      const chainless = txId === NO_TRANSACTION_BUCKET;
      displayTitle = `📒 ${receiptLabel(baseLog && baseLog.new_value)} · ${fold.count} · ${titleTable}`
        + `${chainless ? ' · batch without a chain' : ''}`;
      colorClass = 'color-ledger';
    } else if (fold.kind === 'delete') {
      displayTitle = `🗑️ [${user}] | ${titleTable} | ${fold.count} deleted`;
      colorClass = 'color-delete';
    } else if (fold.kind === 'create') {
      displayTitle = `🆕 [${user}] | ${titleTable} | ${fold.count} created`;
      colorClass = 'color-create';
    } else {
      displayTitle = `📦 [${user}] | ${titleTable} | ${fold.count}`;
      colorClass = baseLog && baseLog.is_row_deleted ? 'color-deleted-row' : 'color-summary';
    }
  } else {
    const targetId = baseLog.business_key ? (baseLog.business_key.length > 10 ? baseLog.business_key.slice(0, 10) + '...' : baseLog.business_key) : baseLog.row_id.slice(0, 8);
    const col = baseLog.column_name;
    if (col === 'CREATE') {
      displayTitle = `🆕 [${user}] created ${baseLog.table_name} (${targetId})`;
      colorClass = 'color-create';
    } else if (col === 'DELETE') {
      displayTitle = `🗑️ [${user}] deleted ${baseLog.table_name} (${targetId})`;
      colorClass = 'color-delete';
    } else if (col === 'ROW_UPDATE') {
      displayTitle = `🤖 [${user}] auto-updated ${baseLog.table_name} (${targetId})`;
      colorClass = baseLog.is_row_deleted ? 'color-deleted-row' : 'color-auto';
    } else if (col === LEDGER_BATCH_COLUMN) {
      // 🔴 C-55 / S-117. 원장 배치는 «표의 셀 하나»가 바뀐 것이 아니라 배치 하나가 돈 것이라,
      //    「누가 어느 칸을 고쳤다」 문장을 쓰면 그 줄이 거짓이 됩니다.
      // 🔴 ③ 'no_tid' 는 «빈 칸이 아니라 이름»입니다 — 백필·소급은 체인 트랜잭션이 «없는»
      //    것이고, 「자료 없음」과 섞으면 조작자가 없는 트랜잭션을 찾아다닙니다.
      const chainless = txId === NO_TRANSACTION_BUCKET;
      displayTitle = `📒 ${receiptLabel(baseLog.new_value)} · ${baseLog.table_name}${chainless ? ' · batch without a chain' : ''}`;
      colorClass = 'color-ledger';
    } else {
      displayTitle = `🔄 [${user}] edited ${col} of ${baseLog.table_name} (${targetId})`;
      colorClass = baseLog.is_row_deleted ? 'color-deleted-row' : (byPerson(baseLog) ? 'color-user-edit' : 'color-parser-edit');
    }
  }

  if (baseLog && baseLog.is_row_deleted) {
    displayTitle = `❌ [deleted] ` + displayTitle;
  }

  // [2c] A ROW, not a card. The class names and the nesting roles are unchanged -- the click,
  // expand and Tx-filter handlers below query `.timeline-card`, `.tx-tag`, `.filter-tx-btn` and
  // `.expand-indicator`, and all four are still here. Only the layout changed.
  li.classList.add('audit-row');
  // 🔴 C-55 ②. 원장 배치의 영수증만 이 줄을 얻습니다. 다른 종류는 «한 글자도» 안 바뀝니다 —
  //    빈 문자열이면 아래가 종전 값 칸을 그대로 그립니다.
  //    접힌 묶음은 그 트랜잭션의 영수증이 «어느 세상들»에 쓰였는지를 그 자리에 — 대표 영수증 하나의 수는
  //    묶음의 수가 아닙니다(총괄, 서버 c49217a06).
  const installWorlds = state.tableList && state.tableList.worlds;
  const receiptLine = (isSummary ? receiptWorldsLine(group, installWorlds) : '')
    || (baseLog && baseLog.column_name === LEDGER_BATCH_COLUMN ? ledgerReceiptLine(baseLog.new_value, installWorlds) : '');
  // △소유자: 「변경이력 문구에서 맨앞에 ., -, -> 빼줘」. A row that CREATED a value has no
  // 「from」, so a dash and an arrow in front of it are punctuation standing in for nothing.
  // An old value belongs to its own log's new value: where the receipt line stands instead, no arrow
  // (the folded row's log is the person's edit since 67f156c11 - 「RCP-1 → Ledger · …」 was false).
  const hadOldValue = !receiptLine && Boolean(baseLog)
    && baseLog.old_value !== null && baseLog.old_value !== undefined && baseLog.old_value !== '';
  // `toLocaleTimeString()` writes 「오후 11:31:31」 in this locale, which does not fit 58px and
  // wrapped the cell to two lines. The mockup's `09:31:12` is what a scan needs: fixed width,
  // no marker to read past - on the product's zone (owner 11-07), not the machine's.
  const timeStr = localClock(facts.at);
  // The table a column of its own (owner 10-12 「감사로그 대상 테이블 컬럼 따로 빼」), said once: the target cell
  // keeps the row and its column. 묶음 줄은 표본이면 첫 로그의 표라도 말합니다.
  const keyRow = isSummary ? '' : (baseLog.business_key || baseLog.row_id.slice(0, 8));
  const targetCol = isSummary ? fold.count : baseLog.column_name;

  li.innerHTML = `
    <div class="timeline-card ${colorClass} ${isSummary ? 'summary-card' : ''}" title="${escapeHtml(displayTitle)}">
      <div class="audit-cell audit-time">${timeStr}</div>
      <div class="audit-cell audit-user">${escapeHtml(user)}</div>
      <div class="audit-cell audit-kind">${facts.kinds.map((kind) => `<span class="audit-pill ${kind.cls}">${escapeHtml(kind.label)}</span>`).join(' ')}</div>
      <div class="audit-cell audit-tbl${facts.tables.length > 1 ? ' audit-tbl-names' : ''}">${tableNames(facts.tables)}</div>
      <div class="audit-cell audit-target">
        <span class="audit-target-key" title="${escapeHtml(keyRow)}"><span class="audit-target-row">${escapeHtml(keyRow)}</span></span>
        <span class="audit-target-col">${escapeHtml(targetCol)}</span>
      </div>
      <div class="audit-cell audit-change">
        ${hadOldValue ? `<span class="val-old">${escapeHtml(auditVal(baseLog.old_value, true))}</span><span class="val-arrow">→</span>` : ''}
        ${receiptLine
          // 🔴 C-55 ②. 원장 배치는 «값 옆 한 줄»입니다 — 봉투를 JSON 으로 펴면 그 칸이
          //    읽을 수 없고, 그렇다고 「배치」 한 낱말만 두면 조작자가 펼쳐야 수를 봅니다.
          //    수는 여기, 문장(문지기의 error 전문)은 펼친 자리에 그대로 남습니다.
          ? `<span class="val-new val-receipt">${escapeHtml(receiptLine)}</span>`
          : baseLog ? `<span class="val-new">${escapeHtml(auditVal(baseLog.new_value, false))}</span>` : ''}
      </div>
      ${txId ? `<div class="audit-cell audit-tx tx-tag" data-tx-id="${txId}"><span class="filter-tx-btn" data-tx-id="${txId}" title="Only this transaction">…${txId.slice(-8)}</span>${isSummary ? '<span class="expand-indicator">▶</span>' : ''}</div>` : '<div class="audit-cell audit-tx"></div>'}
    </div>
    ${isSummary ? `<div class="tx-details-container" style="display: none;"></div>` : ''}
  `;

  if (isSummary) {
    const card = li.querySelector('.timeline-card');
    const detailsContainer = li.querySelector('.tx-details-container');
    const indicator = li.querySelector('.expand-indicator');

    // Open or shut is state.expandedTransactions alone (lead 11-13): a line drawn again - the list read again, a live log -
    // is drawn as that state says, so the next press does what the screen shows.
    const drawShut = () => {
      detailsContainer.style.display = 'none';
      indicator.style.transform = 'rotate(0deg)';
      indicator.textContent = '▶';
    };
    const drawOpen = async () => {
      detailsContainer.style.display = 'block';
      indicator.style.transform = 'rotate(90deg)';
      indicator.textContent = '▼';
      if (needsTransactionRead(group)) {
        if (state.fetchingTransactions.has(txId)) return;
        state.fetchingTransactions.add(txId);
        detailsContainer.innerHTML = '<div class="loading-subdetails">Loading details...</div>';

        try {
          // 🔴 Unchecked, `txDetail.logs` is undefined on a failure body and the group
          //    renders as though the transaction has no rows. The catch below already
          //    says 「Failed to load details.」 and releases `fetchingTransactions`, so a
          //    throw both tells the truth and leaves the group retryable.
          const res = await fetch(`${API_BASE}/audit_logs/transaction/${txId}`);
          if (!res.ok) throw new Error(`transaction ${res.status}`);
          // a page and its cursor (lead 11-12 ㄴ) - the rest by the «more» at its end
          const page = readHistoryPage(await res.json(), 'logs');
          group.logs = page.logs;
          group.nextCursor = page.truncated ? page.nextCursor : null;
          state.fetchingTransactions.delete(txId);
          // 첫 쪽과 커서를 들었습니다. 접힌 줄의 … 는 이제 커서가 답합니다(남은 쪽이 있으면 그대로). 그 칸만 고칩니다.
          const tblEl = li.querySelector('.audit-tbl');
          if (tblEl) { tblEl.innerHTML = tableNames(groupFacts(group).tables); fitAuditTable(); }
          renderSubDetails(detailsContainer, group.logs, transactionPane(group, txId, detailsContainer));
        } catch (err) {
          console.error('Failed to load transaction details', err);
          detailsContainer.innerHTML = '<div class="error-subdetails">Failed to load details.</div>';
          state.fetchingTransactions.delete(txId);
        }
      } else {
        renderSubDetails(detailsContainer, group.logs, transactionPane(group, txId, detailsContainer));
      }
    };
    const toggleExpand = () => {
      if (state.expandedTransactions.has(txId)) {
        state.expandedTransactions.delete(txId);
        drawShut();
      } else {
        state.expandedTransactions.add(txId);
        drawOpen();
      }
    };
    if (state.expandedTransactions.has(txId)) drawOpen();

    card.addEventListener('click', (e) => {
      if (e.target.closest('.filter-tx-btn')) {
        e.stopPropagation();
        const targetTxId = e.target.closest('.filter-tx-btn').dataset.txId;
        setTransactionFilter(targetTxId);
      } else if (e.target.closest('.tx-tag') || e.target.closest('.expand-indicator') || e.target.closest('.audit-tbl-more')) {
        toggleExpand();
      } else {
        goToLine(group, e.target.closest('.audit-target-table'));
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
        goToLine(group, e.target.closest('.audit-target-table'));
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
/** A table name breaks only after «_» or «.» or at a space, never between two letters (owner 11-05): each unbreakable
 *  piece its own span, which fitAuditTable measures. */
function tablePieces(name) {
  return (String(name ?? '').match(/[^_.\s]*[_.]|[^_.\s]+|\s+/g) || [])
    .map((piece) => (/^\s/.test(piece) ? ' '
      : `<span class="audit-tbl-piece">${escapeHtml(piece)}</span>${/[_.]$/.test(piece) ? '<wbr>' : ''}`)).join('');
}

let auditFitWatch = null;
let auditFitFrame = 0;
let auditFitAll = false;
const auditFitRows = new Set();
/** The audit's Table column as wide as its widest whole name, up to --audit-table-max; a longer name breaks after «_» «.»
 *  and the column is never narrower than its widest piece - the head's word too (owner 11-05, lead 11-06: «dt_log» was
 *  three lines at the widest piece). Every row drawn asks; it is measured once, in the next frame (owner 11-06 «가만히
 *  있어도 굳음»: a live message of 500 logs measured the whole panel 500 times, each read after a write). A `row` drawn
 *  only widens it; a whole draw and a width change measure all. A hidden panel measures nothing and owes all - its
 *  showing is a width change. */
function fitAuditTable(row) {
  const box = elements.timelineContainer;
  if (!box) return;
  if (!auditFitWatch && typeof ResizeObserver === 'function') {
    auditFitWatch = new ResizeObserver(() => fitAuditTable());
    auditFitWatch.observe(box);
  }
  if (row) auditFitRows.add(row);
  else auditFitAll = true;
  if (!auditFitFrame) auditFitFrame = requestAnimationFrame(measureAuditTable);
}

function measureAuditTable() {
  auditFitFrame = 0;
  const box = elements.timelineContainer;
  const rows = [...auditFitRows].filter((row) => row.isConnected);
  markWork('history widths', null, rows.length);
  auditFitRows.clear();
  if (!box || !box.getClientRects().length) { auditFitAll = true; return; }
  const all = auditFitAll;
  auditFitAll = false;
  const roots = all ? [box] : rows;
  if (!roots.length) return;
  const held = parseFloat(box.style.getPropertyValue('--audit-tbl-w')) || 0;
  const widest = (sel) => Math.max(0, ...roots.map((root) => widestCell(root, sel, '.audit-cell')));
  box.classList.add('audit-tbl-whole'); // each name on one line for this reading
  const cap = parseFloat(getComputedStyle(box).getPropertyValue('--audit-table-max')) || Infinity;
  const whole = widest('.audit-target-table');
  box.classList.remove('audit-tbl-whole');
  const need = Math.max(widest('.audit-tbl-piece'), Math.min(cap, whole));
  if (need && (all ? need !== held : need > held)) box.style.setProperty('--audit-tbl-w', `${need}px`);
  foldTableNames(roots);
}

/** A Table cell of several names: those on its first line shown, the rest «+N» (owner 11-13; «+N» unfolds the
 *  transaction, which lists every table's rows). Read after the column's width is set. */
function foldTableNames(roots) {
  roots.flatMap((root) => [...root.querySelectorAll('.audit-tbl-names')]).forEach((cell) => {
    const names = [...cell.querySelectorAll('.audit-target-table')];
    const more = cell.querySelector('.audit-tbl-more');
    if (!more || !names.length) return;
    names.forEach((name) => { name.hidden = false; });
    more.hidden = true;
    const onFirst = (el) => el.offsetTop === names[0].offsetTop;
    if (names.every(onFirst)) return;
    more.hidden = false;
    for (let shown = names.length - 1; shown > 0; shown -= 1) {
      names[shown].hidden = true;
      more.textContent = `+${names.length - shown}`;
      if (names.slice(0, shown).every(onFirst) && onFirst(more)) return;
    }
  });
}

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

  // open or shut as state.expandedTransactions says - createGlobalTimelineItemDom draws it so (lead 11-13)
  if (oldLi) {
    elements.timeline.replaceChild(newLi, oldLi);
  } else {
    elements.timeline.insertBefore(newLi, elements.timeline.firstChild);
  }
  fitAuditTable(newLi);
}

// Render history logs in a vertical timeline UI card structure
export function renderTimeline(logs) {
  markWork('history', state.currentTable, Array.isArray(logs) ? logs.length : null);
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
    li.textContent = 'No history';
    return li;
  }

  li.classList.add('has-row-history');

  const note = document.createElement('div');
  note.className = 'timeline-empty-note';
  note.textContent = 'No history for this cell';
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
    ? `Row history · ${total.toLocaleString()}+`
    : `Row history · ${total.toLocaleString()}`;
  btn.addEventListener('click', () => {
    // The row tab's own button, not a reimplementation of it. Switching tabs here directly would
    // mean a second copy of the active-class bookkeeping, the reference-view teardown and the
    // reload — and the copy is what drifts.
    elements.tabRowBtn?.click();
  });
  li.appendChild(btn);

  return li;
}

// [History paging] THE PANE DECLARATION — one pager, two tabs.
//
// 🔴 WHY A DECLARATION AND NOT A SECOND PAGER. The cell/row tabs and the global tab page the
//    same way: hold a cursor, ask for the next page, append it, stop when the server says there
//    is no more. What differs is DATA — which URL, which list key, where the rows go. A second
//    copy of the pager would be the 「같은 기능에 두 경로」 defect, and the copy is the one that
//    drifts: the three error states below (transport failed / position expired / session moved
//    on) each cost this repository a round to get right, and a second implementation starts by
//    not having them.
//
// ⚠️ THE GLOBAL TAB COULD NOT PAGE AT ALL UNTIL TODAY, and this module said so in two places:
//    「`/audit_logs/recent` EMITS `next_cursor` but its signature does not ACCEPT one」 and 「a
//    pager here would be the 「clickable, goes nowhere」 control this module refuses to build」.
//    Both were TRUE when written and are FALSE now — 판정 473 put `cursor` on the route that
//    publishes it, with the gap/overlap gate on the server side. The sentences are rewritten
//    where they stand rather than deleted, because why a control was refused is the record.
const HISTORY_PANES = {
  // The cell and row tabs share one pane: they page the same population through the same state,
  // and which of the two is active only changes the URL `historyUrl` builds.
  cellRow: {
    label: () => `Partial (${state.cellRowHistoryLoaded}) · more`,
    cursor: () => state.cellRowHistoryCursor,
    session: () => state.historyReads.ticket,
    // A page is only wanted while the list it belongs to is still the list on screen.
    live: () => !!state.selectedCell,
    url: (cursor) => historyUrl(state.selectedCell.rowId, state.selectedCell.colId, cursor),
    listKey: 'logs',
    absorb(page, btn) {
      page.logs.forEach(log => {
        state.cellRowHistoryData.push(log);
        elements.timeline.insertBefore(createTimelineItemDom(log), btn.parentElement);
      });
      state.cellRowHistoryLoaded += page.logs.length;
      state.cellRowHistoryCursor = page.nextCursor;
      state.cellRowHistoryTruncated = page.truncated;
    },
    // Rows were inserted where they belong; the control stays put and relabels itself.
    redraw: null,
  },
  global: {
    label: () => `Partial (${state.globalHistoryLoaded}) · more`,
    cursor: () => state.globalHistoryCursor,
    session: () => state.historyReads.ticket,
    live: () => state.activeHistoryTab === 'global',
    url: (cursor) => `${API_BASE}/audit_logs/recent?limit_groups=100`
      + `&cursor=${encodeURIComponent(cursor)}`,
    // Each entry of this list is a transaction GROUP carrying its own `logs`; the envelope's
    // list is named `groups`, and `readHistoryPage` is told which key to open.
    listKey: 'groups',
    absorb(page) {
      page.logs.forEach(group => state.globalHistoryData.push(group));
      state.globalHistoryLoaded += page.logs.length;
      state.globalHistoryCursor = page.nextCursor;
      state.globalHistoryTruncated = page.truncated;
    },
    // 🔴 THIS LIST IS FILTERED CLIENT-SIDE, so a new page cannot be inserted as DOM: which rows
    //    belong on screen is decided by the filter, not by arrival order, and 「N건 중 M」 is
    //    computed from the whole list. Re-drawing from state is what keeps that count true, and
    //    it rebuilds the control from state as part of the same pass.
    redraw: () => renderGlobalTimeline(),
  },
};

// [History paging] The one control at the end of a capped list, and the only thing on this
// screen that says the list IS capped. Appended last, so `renderTimelineIncremental` — which
// prepends live logs at `firstChild` — keeps it at the bottom without knowing it exists.
//
// A COMPLETE LIST CARRIES NO CONTROL. That is the whole affordance: its presence is the fact.
function renderHistoryMore() {
  if (!state.cellRowHistoryTruncated || !state.cellRowHistoryCursor) return;
  elements.timeline.appendChild(createHistoryMoreDom(HISTORY_PANES.cellRow));
}

// The label the operator reads. `일부만` is this client's existing word for a server-truncated
// list (map_editor.js puts it on a truncated overlay) and `더 보기` its existing pager — one
// spelling each, not a third invented here.
//
// 🔴 THE FACT LEADS, THE ACTION FOLLOWS. `더 보기` on its own reads as "there is more if you
//    feel like it"; the question an operator actually has in front of a history list is "is
//    this the whole thing?". A trailing row that only offers to fetch answers that question by
//    implication, and by implication is how a capped list passes for a complete one.
function historyMoreLabel(pane = HISTORY_PANES.cellRow) {
  return pane.label();
}

export function createHistoryMoreDom(pane = HISTORY_PANES.cellRow) {
  const li = document.createElement('li');
  li.className = 'timeline-more';

  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'timeline-more-btn';
  btn.textContent = historyMoreLabel(pane);

  btn.addEventListener('click', () => {
    // After a 400 the cursor names a position the server cannot decode, so the same token can
    // only fail again. The control stops being a pager and becomes the one move that recovers.
    if (btn.dataset.mode === 'reload') {
      rereadHistory();
      return;
    }
    loadMoreHistory(btn, pane);
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
  btn.textContent = 'Read failed · retry';
}

// The position itself is unusable (400). Retrying it forever is the trap; a reload from the top
// is the only thing that can produce a valid cursor again.
function markMoreLost(btn) {
  btn.dataset.mode = 'reload';
  btn.classList.add('is-error');
  btn.disabled = false;
  btn.textContent = 'Position expired · refresh';
}

// [History paging] Fetch the next page and APPEND it. Never replaces what is on screen.
export async function loadMoreHistory(btn, pane = HISTORY_PANES.cellRow) {
  if (!btn || btn.disabled) return;
  const cursor = pane.cursor();
  if (!cursor || !pane.live()) return;

  const session = pane.session();
  const url = pane.url(cursor);

  btn.disabled = true;
  btn.classList.remove('is-error');
  delete btn.dataset.mode;
  btn.textContent = LOADING;

  let page;
  try {
    const res = await fetch(url);
    if (session !== pane.session()) return;
    if (res.status === 400) {
      markMoreLost(btn);
      return;
    }
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    page = readHistoryPage(await res.json(), pane.listKey);
  } catch (err) {
    if (session !== pane.session()) return;
    console.error('Failed to load more history', err);
    markMoreFailed(btn);
    return;
  }

  // The session moved on while this was in flight (another cell, another tab, a refresh). These
  // rows are real and they belong to a list that is no longer on screen.
  if (session !== pane.session()) return;

  pane.absorb(page, btn);

  if (pane.redraw) {
    // The pane rebuilds itself from state, control included, so nothing below applies.
    pane.redraw();
    return;
  }

  if (!page.truncated) {
    // Nothing further to page toward: the list is complete now, and a complete list says so by
    // carrying no control at all.
    btn.parentElement.remove();
    return;
  }

  btn.disabled = false;
  btn.textContent = historyMoreLabel(pane);
}

// Render overall table audit history logs (recent transactions)
/**
 * The audit filter strip, mockup 2c.
 *
 * 🔴 CLIENT-SIDE OVER WHAT IS ALREADY LOADED, and the count says so: 「N건 중 M」 counts the
 * groups in hand, not the table. That reading is unchanged; its REASON is not. It used to be
 * 「`/audit_logs/recent` EMITS `next_cursor` but its signature does not ACCEPT one, so there is
 * no honest way to claim these filters searched all history」 — 판정 473 put `cursor` on the
 * route that publishes it, so history can be PAGED IN and the filter widens with what arrives.
 * What the filter still cannot do is search what was never fetched, which is exactly why the
 * count names its own denominator instead of the table's.
 *
 * Options come from the loaded groups rather than a fixed list, so a source this screen has
 * never seen still gets an entry the day it first appears — and one that only exists further
 * down the history appears the moment a page brings it in.
 */
function auditFilterState() {
  return {
    user: document.getElementById('audit-filter-user')?.value || '',
    kind: document.getElementById('audit-filter-kind')?.value || '',
    when: document.getElementById('audit-filter-when')?.value || ''
  };
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
  const facts = groups.map(groupFacts).filter(Boolean);
  fill('audit-filter-user', [...new Set(facts.flatMap(f => f.who))].sort());
  fill('audit-filter-kind', [...new Set(facts.flatMap(f => f.kinds.map(k => k.label)))].sort());
}

function auditFilterPasses(group, filters) {
  const facts = groupFacts(group);
  if (!facts) return false;
  if (filters.user && !facts.who.includes(filters.user)) return false;
  if (filters.kind && !facts.kinds.some(k => k.label === filters.kind)) return false;
  if (filters.when) {
    const stamp = new Date(facts.at);
    const now = new Date();
    // today on the product's wall clock (owner 11-07), the day the history column shows
    if (filters.when === 'today' && localStamp(stamp).slice(0, 10) !== localStamp(now).slice(0, 10)) return false;
    if (filters.when === '7d' && now - stamp > 7 * 24 * 60 * 60 * 1000) return false;
  }
  return true;
}

export function renderGlobalTimeline() {
  markWork('history', null, (state.globalHistoryData || []).length);
  elements.timeline.innerHTML = '';
  const count = document.getElementById('audit-filter-count');

  const updating = state.globalHistoryUpdating === true;
  if (!state.globalHistoryData || state.globalHistoryData.length === 0) {
    // the server has not read it yet (its walk runs behind the answer) - not «none»
    elements.timeline.innerHTML = updating ? '<li class="timeline-empty">Reading history…</li>'
      : '<li class="timeline-empty">No database history recorded.</li>';
    if (count) count.textContent = updating ? UPDATING : '';
    return;
  }

  fillAuditFilterOptions(state.globalHistoryData);
  const filters = auditFilterState();
  const shown = state.globalHistoryData.filter(group => auditFilterPasses(group, filters));

  shown.forEach((group) => {
    const li = createGlobalTimelineItemDom(group);
    if (li) elements.timeline.appendChild(li);
  });
  fitAuditTable();

  if (!shown.length) {
    elements.timeline.innerHTML = '<li class="timeline-empty">No history matches</li>';
  } else if (state.globalHistoryTruncated) {
    // 🔴 THE FACT, AND NOW THE CONTROL — BUT ONLY WHEN THERE IS A POSITION TO PAGE FROM.
    //    This read 「FACT ONLY, NO CONTROL … a pager here would be the 「clickable, goes nowhere」
    //    control this module already refuses to build」, and that was TRUE when written: the
    //    route published `next_cursor` and its signature accepted none. 판정 473 put `cursor` on
    //    the route that publishes it, with the no-gap/no-overlap gate on the server side, so the
    //    reason for the refusal is gone and the control is the one this screen already has.
    //
    //    ⚠️ THE REFUSAL ITSELF HAS NOT EXPIRED, IT HAS NARROWED. `truncated` arriving without a
    //    usable cursor is still a fact with nowhere to go, and it still draws as a fact — the
    //    same rule `renderHistoryMore` applies to the other tab, and the same one A4 pins. A
    //    control is offered when it can actually move, and not otherwise.
    if (state.globalHistoryCursor) {
      elements.timeline.appendChild(createHistoryMoreDom(HISTORY_PANES.global));
    } else {
      const li = document.createElement('li');
      li.className = 'timeline-empty';
      // 🔴 THE PAGED COUNT, NOT THE LIST LENGTH. Live WebSocket logs are unshifted into
      //    `globalHistoryData` (a log with no group on screen becomes a group), so its length
      //    drifts upward on its own and would make this number grow while nothing was fetched.
      //    That is the same reason `cellRowHistoryLoaded` is kept beside its array rather than
      //    read off it.
      li.textContent = `Partial (${state.globalHistoryLoaded})`;
      elements.timeline.appendChild(li);
    }
  }
  if (count) count.textContent = `${shown.length} of ${state.globalHistoryData.length}${updating ? ' · Updating' : ''}`;
}

/** Re-render on a filter change. The selects are static markup, so this installs once. */
export function installAuditFilters() {
  ['audit-filter-user', 'audit-filter-kind', 'audit-filter-when'].forEach(id => {
    document.getElementById(id)?.addEventListener('change', () => renderGlobalTimeline());
  });
}

/** The pane of an unfolded transaction's rows (lead 11-12 ㄴ): the route answers a page and its cursor, and the same
 *  «more» the history lists use reads the next one into this group's list - its lined rows, then its receipt-only
 *  rows, into `container`'s list. A group read whole carries no cursor and no control. */
export function transactionPane(group, txId, container) {
  return {
    label: () => `Partial (${group.logs.length}) · more`,
    cursor: () => group.nextCursor || null,
    session: () => state.historyReads.ticket,
    live: () => state.expandedTransactions.has(txId),
    url: (cursor) => `${API_BASE}/audit_logs/transaction/${txId}?cursor=${encodeURIComponent(cursor)}`,
    listKey: 'logs',
    absorb(page) {
      const list = container.querySelector('.sub-timeline-list');
      page.logs.forEach((log) => {
        group.logs.push(log);
        list.appendChild(createSubDetailItemDom(log));
      });
      group.nextCursor = page.truncated ? page.nextCursor : null;
    },
    redraw: null,
  };
}

export function createSubDetailItemDom(log) {
  const li = document.createElement('li');
  li.className = 'sub-timeline-item';

  const col = log.column_name;
  const val = formatVal(log.new_value);
  const bk = log.business_key;
  const targetId = bk ? (bk.length > 10 ? bk.slice(0, 10) + '...' : bk) : (log.row_id ? log.row_id.slice(0, 8) : '');

  let labelText = '';
  if (col === 'ROW_UPDATE') {
    labelText = `ROW_UPDATE: ${val} (ID: ${targetId})`;
  } else if (col == null) {
    // a row the transaction route names (owner 11-10 «바뀐 행 네비»: a row, no column, no value) - its key and who wrote it
    labelText = log.is_row_deleted ? `Deleted (ID: ${targetId})` : `${targetId} · by ${log.updated_by || 'system'}`;
  } else {
    labelText = `[${col}] ${val} (ID: ${targetId})`;
  }

  // 🔴 C-14. `labelText` is assembled from a column name, a business key and the value an
  //    operator last typed — all three arrive from the server and none is authored here.
  //    Escaped at the interpolation, which is where this file already escapes (`:224`), so
  //    `formatVal` stays a formatter and does not become a second escaping author.
  li.innerHTML = `
    <span class="sub-bullet">└</span>
    <span class="sub-log-text">${escapeHtml(labelText)}</span>
  `;

  li.addEventListener('click', (e) => {
    e.stopPropagation();
    if (log.row_id !== '_BATCH_') {
      navigateToLog(log);
    }
  });
  return li;
}

export function renderSubDetails(container, logs, pane = null) {
  container.innerHTML = '';
  const ul = document.createElement('ul');
  ul.className = 'sub-timeline-list';

  // a paged transaction holds only the pages its «more» read - all drawn, so a page read next lands after them (lead 11-12)
  const renderLimit = pane ? Infinity : 500;
  const initialLogs = logs.slice(0, renderLimit);
  const remainingLogs = logs.slice(renderLimit);
  const appendLogItem = (log) => ul.appendChild(createSubDetailItemDom(log));

  initialLogs.forEach(appendLogItem);
  container.appendChild(ul);

  if (remainingLogs.length > 0) {
    const moreBtn = document.createElement('button');
    moreBtn.className = 'glass-btn';
    moreBtn.style.margin = '10px 0 10px 24px';
    moreBtn.style.padding = '6px 16px';
    moreBtn.style.fontSize = 'var(--fs-button)';
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

  if (pane && pane.cursor()) {
    const tail = document.createElement('ul');
    tail.className = 'sub-timeline-more';
    tail.appendChild(createHistoryMoreDom(pane));
    container.appendChild(tail);
  }
}

// Helper to format values
export function formatVal(v, isOld = false) {
  if (v === null || v === undefined || v === '') {
    return isOld ? 'Empty' : 'Deleted';
  }
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

// Debounced History Loader
let historyDebounceTimeout = null;
export function triggerHistoryReloadDebounced() {
  // the server says logs were missed: Global is old now, read when it is shown
  state.globalHistoryStale = true;
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

/**
 * A ledger batch receipt has no row to jump to — its `row_id` is the BATCH, so the row jump below
 * failed on every receipt. It shows the rows of its transaction in that table and stops; a batch
 * with no transaction (backfill, retroactive — `no_tid`) has nothing to show and says so.
 * ⚠️ Rows translated in the same batch that this transaction did not change are not shown (lead 43a738d58).
 */
async function openLedgerReceipt(log) {
  const tx = log.transaction_id;
  if (!tx || tx === NO_TRANSACTION_BUCKET) {
    sayStopped(`Ledger batch · ${log.table_name} · no transaction to show — a backfill or retroactive batch`);
    return;
  }
  if (state.currentTable !== log.table_name) {
    elements.tableSelect.value = log.table_name;
    if (!(await switchTable(log.table_name))) return;
  }
  // Only on screen does the line say what is shown; a refused read keeps the server's sentence.
  // ⚠️ No count: the grid holds one page (pageLimit), so its displayed count lies past that page.
  //    The grid's own total says how many (lead 8bc1bd530).
  if (await setTransactionFilter(tx)) {
    elements.performanceLog.textContent =
      `Ledger batch · ${log.table_name} · transaction ${String(tx).slice(0, 8)}`;
  }
}

// HistoryNavigator (4-Step Jump Sequence)
export async function navigateToLog(log) {
  // Every click path (the row tabs, the global tab's single and grouped lines) reaches here.
  if (log && log.column_name === LEDGER_BATCH_COLUMN) return openLedgerReceipt(log);
  if (state.isNavigating) {
    sayStopped('⚠️ Already navigating, please wait...');
    return;
  }

  state.isNavigating = true;
  const jump = {};
  state.navigationJump = jump;
  // V1 instrument: the deepest in-page jump on the grid page — it can change table, set a
  // transaction filter and scroll to another row, so the prior working context is gone.
  countNav(ROUTES.GRID, 'grid:log_jump');
  elements.performanceLog.textContent = `🔍 Navigating to ${log.table_name}:${log.row_id} in Transaction ${log.transaction_id}...`;

  // Set 5s watchdog safety net (mimics PyQt 10s guard timer)
  if (state.navigationWatchdog) clearTimeout(state.navigationWatchdog);
  state.navigationWatchdog = setTimeout(() => {
    releaseNavigationGuard('❌ Navigation Timeout', jump);
  }, 5000);

  const targetTable = log.table_name;
  const targetTx = log.transaction_id;
  // The rows on screen answer this jump only when they were read for the same table and transaction.
  const sameView = state.currentTable === targetTable && (state.currentTransactionId || null) === (targetTx || null);

  // Step 1: Switch table/tab if different
  if (state.currentTable !== targetTable) {
    elements.tableSelect.value = targetTable;
    // refused (staged edits): the sentence is said, the jump let go without a second one
    if (!(await switchTable(targetTable))) { releaseNavigationGuard('', jump); return; }
  }

  // Set the transaction filter context automatically
  // Another transaction: the cached pages were read under the old one (setTransactionFilter's own read clears them too).
  if (!sameView) state.pageCache.clear();
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
    if (sameView) navigatorStep2(log, jump);
    else navigatorStep3(log, jump);
  }, 50);
}

// Step 2: Check local caching or decide server target jump
export function navigatorStep2(log, jump = null) {
  if (!state.gridApi) {
    releaseNavigationGuard('❌ Grid not initialized', jump);
    return;
  }

  const rowNode = state.gridApi.getRowNode(log.row_id);
  if (rowNode) {
    // Cache Hit -> directly scroll (Step 4)
    navigatorFinalScroll(rowNode, log.column_name, jump, log.business_key);
  } else {
    // Check if row exists in any of the cached pages
    for (const [skip, cached] of state.pageCache.entries()) {
      const found = cached.data.some(r => (r.row_id || r.id) === log.row_id);
      if (found) {
        state.currentSkip = skip;
        state.looks = cached.looks || null;   // the page's looks, as the page read's cache hit (api.js fetchData)
        saidLooksChanged();
        state.gridApi.setGridOption('rowData', overlayStagedEdits(copyRows(cached.data)));
        updateGridSortState();
        updateLoadedCount(cached.data.length);
        setMatchCount(elements.totalRowsCount, cached.count);
        updatePaginationUI(cached.count, cached.data.length);

        setTimeout(() => {
          const node = state.gridApi.getRowNode(log.row_id);
          if (node) {
            navigatorFinalScroll(node, log.column_name, jump, log.business_key);
          } else {
            releaseNavigationGuard('❌ Failed to locate row in cached page', jump);
          }
        }, 50);
        return;
      }
    }

    // Cache Miss -> request server target jump (Step 3)
    navigatorStep3(log, jump);
  }
}

// Step 3: Fetch target row via API parameter
export async function navigatorStep3(log, jump = null) {
  elements.performanceLog.textContent = '🌐 Requesting target position from server...';
  // On the grid's board: a page, a table or another jump asked after this cuts it, and its answer is not drawn. The
  // read it cut held the page latch, which this jump does not hold.
  const read = state.gridReads.begin();
  state.isLoadingMore = false;
  const cut = () => !read.current();

  const narrowing = narrowingTail({
    globalSearch: elements.globalSearch, searchCols: elements.searchCols,
    gridApi: state.gridApi, transactionId: state.currentTransactionId,
  });

  // A-6. The SAME sort the grid is showing — `sortQueryTail` is the one spelling. This used to
  // re-derive it from the toggle here, which was a second copy of one decision and would have
  // computed the jump's offset in a different order from the one on screen.
  // `defer_total=true`, fetchData's: the total is not counted on the way (A 10-28: 3.3 s of a jump's 7.5-13.6 s on the box
  // was that count); `askMatchCount` below fills it the way the grid's own read does.
  const url = `${API_BASE}/tables/${state.currentTable}/data?target_row_id=${log.row_id}`
    + `&limit=${pageLimit}${sortQueryTail()}&defer_total=true${narrowing}`;

  try {
    const res = await gridFetch(url, { signal: read.signal });
    if (cut()) { releaseNavigationGuard('', jump); return; }

    // 🔴 THE REFUSAL IS SHOWN, NOT SWALLOWED (A-6-b). Under a header sort the server refuses
    //    this jump: its offset comparison is written for three names only. Without this branch
    //    `result.data.length` throws on the refusal body and the outer catch reports
    //    「Server fetch error」 — a transport story for a deliberate, explained refusal. The
    //    sentence is the SERVER'S, verbatim, into the status line every other refusal uses; a
    //    Korean equivalent written here would be this side classifying evidence the server
    //    already judged. Worded by the one refusal seat (api.js refusalText) - a stopped read's
    //    `detail.message` too (lead 87dfa71d7).
    if (!res.ok) {
      releaseNavigationGuard(await refusalText(res, '❌ Jump refused'), jump);
      return;
    }
    const result = await res.json();
    if (cut()) { releaseNavigationGuard('', jump); return; }

    if (result.target_offset === -1 || result.data.length === 0) {
      releaseNavigationGuard('❌ Target row does not match active search/transaction filters', jump);
      return;
    }

    // Load returned chunk page to local grid - with its looks, as the page read takes them
    state.looks = pageLooks(state.looks, result.looks);
    saidLooksChanged();
    state.gridApi.setGridOption('rowData', overlayStagedEdits(result.data));
    updateGridSortState();

    // Update skip counter
    state.currentSkip = result.calculated_skip !== null ? result.calculated_skip : 0;
    state.readAfter = rowsKey(result.data, 'after');   // the infinite view scrolls on from the page jumped to

    // Update Counts (Zero-lag counter concept)
    updateLoadedCount(result.data.length);
    const count = countOf(result);
    setMatchCount(elements.totalRowsCount, count);

    // Update Pagination UI
    updatePaginationUI(count, result.data.length);
    // A table the server has not counted yet (ㄱ-1): asked the way the grid's own read asks, again while it counts.
    if (count.total === null) askMatchCount();

    // Save to Cache
    state.pageCache.set(state.currentSkip, { data: copyRows(result.data), count, looks: state.looks });
    // who wrote its cells, when the page came without them (D 11-10)
    if (result.looks && result.looks.updating) fillWriters(url, state.currentSkip, read);

    // Check if target node loaded successfully
    setTimeout(() => {
      if (cut()) { releaseNavigationGuard('', jump); return; }
      const rowNode = state.gridApi.getRowNode(log.row_id);
      if (rowNode) {
        navigatorFinalScroll(rowNode, log.column_name, jump, log.business_key);
      } else {
        releaseNavigationGuard('❌ Failed to locate row after server fetch', jump);
      }
    }, 20); // 20ms layout sync delay

  } catch (err) {
    // cut by a newer read - its end, not a failure
    if (cut()) { releaseNavigationGuard('', jump); return; }
    console.error('Jump fetch error', err);
    releaseNavigationGuard('❌ Server fetch error', jump);
  }
}

// Step 4: Scroll and Focus Column Cell - a jump to a row the history names with no column (the transaction route's,
// owner 11-10 «바뀐 행 네비») selects the row and focuses no cell; `rowKey` is the row's business key, said for it.
export function navigatorFinalScroll(rowNode, columnName, jump = null, rowKey = null) {
  try {
    const column = columnName || null;
    // 1. Ensure visible
    state.gridApi.ensureNodeVisible(rowNode, 'middle');

    // 2. Select row
    rowNode.setSelected(true, true);

    // 3. Focus Cell
    if (column) state.gridApi.setFocusedCell(rowNode.rowIndex, column);

    // 4. Trigger flash micro-animation
    state.gridApi.flashCells({
      rowNodes: [rowNode],
      ...(column ? { columns: [column] } : {}),
      flashDelay: 1000
    });

    // 5. Sync details panel manually
    state.selectedCell = {
      rowId: rowNode.data.row_id,
      colId: column,
      value: column ? rowNode.data.data?.[column]?.value ?? '' : null,
      rowIndex: rowNode.rowIndex,
      rowKey: rowKey || null
    };
    updateSelectedCellUI();

    const row = rowKey || rowNode.data.row_id;
    elements.performanceLog.textContent = column ? `🎯 Jumped to ${column} at Row ${row}` : `🎯 Jumped to Row ${row}`;

    // Finalize
    releaseNavigationGuard('', jump);
  } catch (err) {
    console.error('Final scroll error', err);
    releaseNavigationGuard('❌ Scroller positioning error', jump);
  }
}

// Helper: Navigation Locker Release. A jump ends only its own lock: one that ends after its watchdog let the next jump
// start leaves that jump's lock, and says nothing over it. No `jump` - a caller outside a jump - ends whatever holds it.
export function releaseNavigationGuard(errorMessage = '', jump = null) {
  if (jump && jump !== state.navigationJump) return;
  state.navigationJump = null;
  state.isNavigating = false;
  if (state.navigationWatchdog) {
    clearTimeout(state.navigationWatchdog);
    state.navigationWatchdog = null;
  }
  if (errorMessage) sayStopped(errorMessage);
}
