import { API_BASE, WS_URL, CURRENT_USER, pageLimit } from './config.js';
import { narrowingParams as buildNarrowing } from './narrowing.js';
import { state, gridFetch, tableIsPerWorld } from './state.js';
import { notANumber, unitText } from './ui_words.js';
import { isBlank } from './absent.js';
import { refuseWrite, applyWriteGuards, writeRefusal } from './write_guard.js';
import { setDisabledReason } from './disabled_reason.js';
import { elements } from './dom.js';
import { activateHistoryTab } from './history_tabs.js';
import { clearRangeSelection } from './clipboard.js';
import { updateSelectedCellUI, updateTxModeUI } from './ui.js';
import { renderGrid, dropGridFilters, updateGridSortState, updateLoadedCount, updatePaginationUI, ensureCellObject, markCellOverwritten, syncReferenceRule, sortQueryTail } from './grid.js';
// 「Matches:」를 쓰는 자리는 다섯입니다. 철자와 «세는 중» 판정은 한 곳에 삽니다.
import { countOf, setMatchCount } from './match_count.js';
import { loadHistory } from './timeline.js';
import { getLocalTimeString, showToast } from './utils.js';
// 거절·무응답의 문장은 그 좌석이 짓는다. 뜻을 두 번 짓지 않는다.
import { failureFactOf, fetchFailureLine } from './config_resolve_view.js';
import { resetSuggestLearning } from './value_suggest.js';
import { snapshot, commitIfRecorded } from './effort_meter.js';
import { tableMenu, fillTableSelect } from './table_menu.js';
import { timedRead, QueueReadTimeout, QUEUE_READ_TIMEOUT_MS } from './queue_poll.js';

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

/**
 * 거절의 «사유» — 서버가 문장을 보냈으면 그것이고, 아니면 상태를 이름 댑니다.
 *
 * 🔴 자리가 «하나»입니다: 쓰기(`addRows`)와 읽기(`fetchData` · 행 이동 `navigatorStep3`)가 같은 답을 내야 하고, 각자
 *    적으면 한쪽이 조용히 달라집니다. 그리고 이 함수는 «던지지 않습니다» — 거절은 예외가
 *    아니라 «답»이고, 던지면 그 문장이 콘솔로만 갑니다.
 * ⚠️ 답은 «문장»일 때만입니다 — `detail` 이 문자열이거나, 멈춘 읽기(503 grid_read_stopped, adae5832a)처럼
 *    `detail.message` 가 문자열일 때. FastAPI 의 기본 422 는 `detail` 이 목록이라, 그대로 그리면
 *    화면이 「[object Object]」를 말합니다.
 *
 * @param {Response} res 거절한 응답
 * @param {string} whenSilent 서버가 문장을 «안 보냈을» 때 화면이 댈 이름
 */
export async function refusalText(res, whenSilent) {
  const said = await refusalSaid(res);
  return said || `${whenSilent} (HTTP ${res.status})`;
}

/** 거절에 서버가 실은 문장 — 없으면 ''. 미룬 수의 실패(fillMatchCount)도 이것을 읽습니다. */
async function refusalSaid(res) {
  const body = await res.json().catch(() => null);
  const detail = body ? body.detail : null;
  const said = typeof detail === 'string' ? detail
    : (detail && typeof detail.message === 'string' ? detail.message : '');
  return said;
}

/**
 * 거절된 «읽기»를 그립니다. 🔴 이 함수는 던지지 않습니다.
 *
 * ⚠️ 사유를 «맨 먼저» 답니다 — 뒤의 한 줄이 실패해도 문장은 화면에 서 있어야 합니다. 그리는
 *    도중의 실패가 사유를 지우면 운영자는 다시 「Data fetch failed」만 보게 되고, 그것이 이
 *    라운드의 출발점입니다(실측: 하니스의 문서 스텁에서 토스트가 던지자 바깥 `catch` 가
 *    사유를 덮었습니다).
 * ⚠️ 개수는 «0 이 아니라 모름»입니다. 세러 간 적이 없습니다 — 0 은 「없다」는 측정입니다.
 */
function showReadRefusal(why) {
  setBadge(elements.performanceLog, why);
  // 격자를 «비웁니다» — 앞 표의 행이 남아 있으면 그것을 «이 표의 데이터»로 읽습니다.
  if (state.gridApi) state.gridApi.setGridOption('rowData', []);
  updateLoadedCount(0);
  setMatchCount(elements.totalRowsCount, null);
  updatePaginationUI(null);
  try { showToast(why, 'error'); } catch (err) { console.error('[toast] refusal', err); }
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

/** 체인 워커가 살아 있나 — «판정은 `/health` 가 내린다».
 *
 * 🔴 여기서 다시 유도하지 않는다. 서버가 낱말을 «이미» 짓는다(`runtime/health.py`):
 *    down · unknown · starting · foreign_beat · missing · wedged · stale · stalled · ok · off_roster.
 *    그 가름의 근거는 두 주인에게 나뉘어 있다(`utils/heartbeat.py`) — 감독자는 «프로세스가 있나»,
 *    심박은 «고리가 도나». 화면이 나이로 다시 재면 임계값이 두 벌이 되고, 오늘 아침처럼
 *    「프로세스는 살아 있는데 고리가 멈춘」 경우에 둘이 다른 말을 한다.
 * ⛔ 그래서 이 함수는 색만 고른다: «ok 면 online, 나머지는 offline». 못 읽었으면 «중립»이다 —
 *    「못 봤다」를 「이상 없다」로 그리지 않는다(그 계약은 서버 쪽 주석에도 같은 말로 있다).
 *
 * @param {object|null} payload `/health` 의 본문 (503 이어도 본문은 온다)
 * @returns {{text: string, cls: string, title: string}}
 */
export function chainBadge(payload) {
  const chain = ((payload || {}).checks || {}).workers;
  const row = (chain || {}).chain;
  if (!row || !row.status) {
    return { text: 'CHAIN: ?', cls: 'status-badge', title: '' };
  }
  const token = String(row.status);
  return {
    text: `CHAIN: ${token.toUpperCase()}`,
    cls: token === 'ok' ? 'status-badge online' : 'status-badge offline',
    // 문장은 서버 것이다. 없으면 «아무 말도 안 한다» — 사유를 지어내지 않는다.
    title: typeof row.detail === 'string' ? row.detail : '',
  };
}

/** 그 뱃지를 한 번 그린다. 503 이어도 «본문»을 읽는다 — 정작 알려야 할 순간이 그때다. */
export async function checkChainHealth() {
  let failure = null;
  let body = null;
  try {
    const res = await fetch(`${API_BASE}/health`);
    failure = failureFactOf(res);
    body = await res.json().catch(() => null);
  } catch (err) {
    console.error('[health] chain badge could not read /health', err);
  }
  // 🔴 그리는 쪽도 «던질 수 있다» — 이 파일 위쪽 `setBadge` 주석이 그 사고를 적어 두었고,
  //    이 함수는 `await` 없이 불리므로(주기) 여기서 던지면 «미처리 거부»가 된다. 뱃지 하나를
  //    못 그린 것이 페이지를 내리는 이유가 될 수 없다.
  try {
    const view = chainBadge(body);
    if (setBadge(elements.chainStatus, view.text, view.cls)) {
      elements.chainStatus.setAttribute('title',
        view.title || (body ? '' : fetchFailureLine(failure)));
    }
  } catch (err) {
    console.error('[health] chain badge could not be drawn', err);
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
    // 🔴 Unchecked, a failure body has no `tables` key, the dropdown is built empty, and
    //    the screen says 「this server has no tables」 -- an answer, where the truth was
    //    「could not ask」. Same class as F-11; the catch below already says it properly.
    const res = await fetch(`${API_BASE}/tables`);
    if (!res.ok) throw new Error(`tables ${res.status}`);
    const data = await res.json();
    if (!elements.tableSelect) throw new Error('#table-select is not present on this page');
    elements.tableSelect.innerHTML = '';

    if (data.tables && data.tables.length > 0) {
      // `groups` rides the list (lead 685f236d7): {table: group}, an ungrouped table absent.
      state.tableList = { tables: data.tables, groups: data.groups, perWorld: data.per_world,
        worlds: data.worlds, operating: data.operating };
      // Auto select first table (switchTable draws the dropdown)
      const firstTable = data.tables[0];
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

/** The table dropdown, grouped and narrowed by the search box. The open table is always in it. */
export function drawTableMenu(selected = state.currentTable) {
  if (!state.tableList || !elements.tableSelect) return;
  const query = elements.tableSearch ? elements.tableSearch.value : '';
  fillTableSelect(elements.tableSelect,
    tableMenu(state.tableList.tables, state.tableList.groups, query, selected), selected);
}

// The world tab row over the grid (lead 120450931 ②). The page seats the part; every table switch redraws it,
// because every way to a table - the dropdown, boot, a history jump - goes through `switchTable`.
let worldTabs = null;
export function seatWorldTabs(part) {
  worldTabs = part;
  drawWorldTabs();
}
function drawWorldTabs() {
  if (!worldTabs) return;
  const list = state.tableList || {};
  worldTabs.show(tableIsPerWorld()
    ? { worlds: list.worlds, operating: list.operating, current: state.gridWorld } : null);
}
/** A world tab picked: the open table is read again in it, from its first page. */
export async function pickGridWorld(world) {
  state.gridWorld = world || null;
  drawWorldTabs();
  await fetchData(true);
}

// The parts that follow the open table - the source label, the Re-translate banner (lead 10-12: a history jump left the
// last table's lists). The page seats them once; every way to a table goes through switchTable, boot's included.
let tableFollower = null;
export function seatTableFollower(follow) {
  tableFollower = follow;
}

// Switch current working table
export async function switchTable(tableName) {
  // Every way in (the dropdown, a history jump) leaves the opened table in the list, search or not.
  drawTableMenu(tableName);
  const leaving = state.currentTable;
  state.currentTable = tableName;
  window.currentTable = tableName; // Expose globally for Desktop Wrapper
  elements.performanceLog.textContent = `Switching to ${tableName}...`;

  // Clean selected cell info
  state.selectedCell = null;
  clearRangeSelection();
  updateSelectedCellUI();

  // Discard pending edits on table switch
  state.pendingTxEdits = {};
  closeQuestion();
  keepTxOn();

  // 🔴 A-6. THE SORT COLUMN BELONGS TO THE TABLE IT WAS PICKED ON. Carrying `dt_lot` into a
  //    table that does not declare it is the one way this screen could put an unknown name on
  //    the wire, and the server answers that with a 422 — a refusal the operator did nothing
  //    to earn. It dies with the table, like the transaction filter above it.
  state.serverSort = null;
  // The grid's filters die with the table too (lead 10-12); the same table drawn again keeps them.
  if (leaving !== tableName) await dropGridFilters();
  // The world tab dies with the table too (lead 120450931 ②); the row is drawn for the table now open.
  state.gridWorld = null;
  drawWorldTabs();

  // Reset transaction filter
  state.currentTransactionId = null;
  if (elements.txFilterBanner) elements.txFilterBanner.style.display = 'none';
  if (elements.bannerTxId) elements.bannerTxId.textContent = '';

  // Load Schema
  await loadSchema(tableName);
  // 🔴 C-102 ①. 자리가 여기인 이유: 표의 «종류»를 `loadSchema` 가 읽고, 그다음 줄이 그것을
  //    아는 «첫» 자리입니다. 컨트롤이 각자 물으면 새 컨트롤마다 한 번씩 빠집니다.
  //    C-107: 이제 «쓰는 컨트롤 전부»와 머리의 배지가 같은 줄에서 맞춰집니다.
  applyWriteGuards();
  // The label and the banner know the table once its columns are read - the label's answer redraws them.
  if (tableFollower) tableFollower(tableName);
  // Re-create empty grid to bind new columns
  renderGrid([]);
  // Fetch initial chunk of data (reset skip to 0)
  await fetchData(true);

  // Reset active history tab to global when switching tables to avoid empty screen
  state.activeHistoryTab = 'global';
  // 🔵 참조 탭의 강조도 여기서 같이 꺼집니다 — 규칙 «없는» 표가 앞 표의 강조를 물려받으면
  //    안 되고, 규칙 있는 표는 `syncReferenceViewRule` 이 잠시 뒤 다시 켭니다.
  //    좌석이 «줄 전체»를 끄므로 형제를 여기서 나열하지 않습니다 (2026-09-22).
  activateHistoryTab(elements.tabGlobalBtn);
  await loadHistory();

  // Enrichment 결손 배지: fire-and-forget (테이블 전환을 블로킹하지 않음, 실패 무음)
  // The headers get their ①② here, not in `renderGrid` above: the rule is still in flight
  // at that point. The pairing and its `.catch` live in `syncReferenceRule`.
  syncReferenceRule();

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
    // 🔴 Unchecked, a failure body became `columns: []` and the grid believed the table
    //    had no columns -- which is the state writes start from. Same class as F-11.
    const res = await gridFetch(`${API_BASE}/tables/${tableName}/schema`);
    if (!res.ok) throw new Error(`schema ${res.status}`);
    const data = await res.json();
    state.currentColumns = data.columns || [];
    state.currentColumnTypes = data.column_types || {};
    // C-84. 표인가 뷰인가. S-187 이 `/schema` 에 실었고, `/tables` 의 `kinds` 와 «같은 서버
    // 함수»라 둘 다 읽을 이유가 없다 — 두 경로면 갈라질 수 있다(criterion ④).
    // 🔴 문자열이 «아니면» 빈 값이다: 옛 서버는 이 키를 안 보내고, 그 «모름»을 뷰로 읽으면
    //    멀쩡한 표의 편집이 사라진다.
    state.currentTableKind = typeof data.kind === 'string' ? data.kind : '';
    // The table's smart paste order (lead 8771e43ac 1): `null` when it declares none.
    state.currentSmartPaste = Array.isArray(data.smart_paste) ? data.smart_paste : null;
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
// Reads the screen and hands it to the one builder. The BUILDING lives in `narrowing.js`
// so a harness can score it -- this wrapper is the part that cannot be imported, because it
// reaches for `elements` and `state`.
function narrowingParams() {
  return buildNarrowing({
    globalSearch: elements.globalSearch, searchCols: elements.searchCols,
    gridApi: state.gridApi, transactionId: state.currentTransactionId,
  });
}

/** 미룬 개수를 가져와 채웁니다. 행은 «이미» 그려져 있습니다.
 *
 * 🔴 못 세었으면(서버의 `failed` · 거절된 답) «Count failed (<사유>)» 입니다 — 0 은 「일치 없음」이라는 거짓이고,
 *    «Counting rows…» 에 머물면 끝나지 않는 세기로 읽힙니다(총괄 0fd18ae19 6). 닿지 못한 요청은 «세는 중» 그대로.
 */
/** 서버가 «아직 안 셌다»(counting)고 하면 다시 묻는 간격과 상한 (총괄 10-13 ②): 같은 질문(표 · 좁힘 · 세상)일 때만,
 *  바뀌면 멈춤, 상한을 넘으면 «Counting rows…» 그대로 두고 더 안 묻습니다. */
export const RECOUNT_ASK_MS = 3000;
export const RECOUNT_ASK_FOR_MS = 120000;

async function fillMatchCount(params, table, since = Date.now()) {
  const mine = ++countGeneration;
  const world = state.gridWorld;
  const tail = params.toString();
  try {
    const res = await gridFetch(`${API_BASE}/tables/${table}/data/count${tail ? `?${tail}` : ''}`);
    const body = res.ok ? await res.json() : { failed: { reason: (await refusalSaid(res)) || `HTTP ${res.status}` } };
    // 늦게 온 답은 버립니다 -- 그 사이에 표나 필터가 바뀌었으면 이건 «다른 질문»의 답입니다.
    if (mine !== countGeneration || table !== state.currentTable) return;
    const count = countOf(body);
    if (count.failed) {
      setMatchCount(elements.totalRowsCount, count);
      return;
    }
    if (count.total === null) {
      if (body.counting === true && Date.now() - since < RECOUNT_ASK_FOR_MS) {
        setTimeout(() => {
          if (mine === countGeneration && table === state.currentTable && world === state.gridWorld) fillMatchCount(params, table, since);
        }, RECOUNT_ASK_MS);
      }
      return;
    }
    setMatchCount(elements.totalRowsCount, count);
    const page = state.pageCache.get(state.currentSkip);
    updatePaginationUI(count, page ? page.data.length : undefined);
    // 캐시된 쪽들은 «같은 좁힘»의 것들입니다 (필터가 바뀌면 캐시가 비워집니다).
    // 안 채우면 캐시 적중이 「세는 중」으로 되돌아갑니다.
    state.pageCache.forEach((entry) => { entry.count = count; });
  } catch (e) {
    console.error('Failed to fetch match count', e);
  }
}

/** 지금 그리드의 질문으로 미룬 수를 묻습니다 — 행 점프(timeline.js)처럼 수 없이 쪽을 그린 자리가 부릅니다. */
export function askMatchCount() {
  return fillMatchCount(narrowingParams(), state.currentTable);
}

/** Load All (main.js): every row of the grid's question, chunk by chunk. The end is a chunk shorter than `chunkLimit` -
 *  a count is «as of» a time, 10,000+ past the cap or still counting (구현자 A 67e5e9ccd ㄱ-1), so it is not the end.
 *  Only the first chunk is counted; the rest ask none (`defer_total`). `onProgress(rows so far, the exact count or
 *  null)`. -> { rows, count } */
export async function fetchAllRows(baseUrl, queryParams, chunkLimit, onProgress) {
  const read = async (skip, deferTotal) => {
    const res = await gridFetch(`${baseUrl}?skip=${skip}&limit=${chunkLimit}&${queryParams}${deferTotal ? '&defer_total=true' : ''}`);
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return res.json();
  };
  const first = await read(0, false);
  const count = countOf(first);
  const exact = count.total !== null && !count.capped ? count.total : null;
  let rows = first.data || [];
  let last = rows.length;
  onProgress(rows.length, exact);
  while (last === chunkLimit) {
    // 브라우저 렌더링 프레임 양보하여 UI 갱신 보장
    await new Promise((resolve) => setTimeout(resolve, 5));
    const chunk = (await read(rows.length, true)).data || [];
    if (!chunk.length) break;
    rows = rows.concat(chunk);
    last = chunk.length;
    onProgress(rows.length, exact);
  }
  return { rows, count };
}

export const EXPORT_FAILED = '❌ CSV download failed';

/** The CSV export's read: the response to stream, or the server's refusal sentence through the one refusal seat (413
 *  past the export cap, 구현자 A 67e5e9ccd ㄱ-1). -> { res } | { refused } */
export async function openExport(url) {
  const res = await gridFetch(url);
  return res.ok ? { res } : { refused: await refusalText(res, EXPORT_FAILED) };
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
      state.gridApi.setGridOption('rowData', overlayStagedEdits(copyRows(cached.data)));
      updateGridSortState();
      updateLoadedCount(cached.data.length);
      setMatchCount(elements.totalRowsCount, cached.count);
      updatePaginationUI(cached.count, cached.data.length);
      // 아직 안 센 쪽이 캐시에 있으면 «다시 묻습니다». 안 그러면 「세는 중」이 영영 남습니다.
      if (cached.count.total === null) fillMatchCount(narrowingParams(), state.currentTable);
      elements.performanceLog.textContent = `Loaded ${unitText(cached.data.length, 'row')} from client cache`;
      return;
    }
  }

  state.isLoadingMore = true;
  elements.performanceLog.textContent = 'Fetching data...';

  const startTime = performance.now();

  const narrowing = narrowingParams();
  const table = state.currentTable;

  // 🔴 `defer_total=true` -> 응답의 `total` 이 «null» 입니다. 행이 먼저 나오고 개수는
  //    두 번째 요청이 채웁니다. 세는 데 걸리는 시간이 첫 화면에서 빠집니다.
  let url = `${API_BASE}/tables/${table}/data?skip=${state.currentSkip}&limit=${pageLimit}`;
  // A-6. One spelling of the sort, shared with the row jump — see `grid.sortParams`.
  url += sortQueryTail();
  url += '&defer_total=true';
  const tail = narrowing.toString();
  if (tail) url += `&${tail}`;

  try {
    const res = await gridFetch(url);
    // 🔴 C-105. 거절은 «읽기»에도 옵니다 — 그리고 그 답에는 행이 «없습니다». 종전에는 `res.ok`
    //    를 안 보고 `result.data.length` 를 읽어 «던졌고», 서버가 이름을 대고 거절한 사유가
    //    (실경로: 「전순서가 없어 페이지를 읽을 수 없다 — business_key 를 선언하라」) 화면
    //    어디에도 안 섰습니다. 운영자가 본 것은 「Data fetch failed」 한 줄입니다.
    if (!res.ok) {
      showReadRefusal(await refusalText(res, 'Data fetch failed'));
      state.isLoadingMore = false;
      return;
    }
    const result = await res.json();

    const fetchTime = (performance.now() - startTime).toFixed(1);

    if (result.data.length < pageLimit) {
      state.hasMoreData = false;
    }

    // Render rowData depending on View Mode
    if (state.viewMode === 'infinite') {
      if (resetSkip || state.currentSkip === 0) {
        state.gridApi.setGridOption('rowData', overlayStagedEdits(result.data));
      } else {
        state.gridApi.applyTransaction({ add: overlayStagedEdits(result.data) });
      }
    } else {
      state.gridApi.setGridOption('rowData', overlayStagedEdits(result.data));
    }
    updateGridSortState();

    // Update Counts (Zero-lag counter concept)
    updateLoadedCount();
    const count = countOf(result);
    setMatchCount(elements.totalRowsCount, count);

    // Update Pagination UI
    updatePaginationUI(count, result.data.length);

    elements.performanceLog.textContent = `Loaded ${unitText(result.data.length, 'row')} in ${fetchTime}ms`;

    // 행은 그려졌습니다. 이제 개수를 가지러 갑니다 -- «기다리지 않고» 돌려줍니다.
    if (count.total === null) fillMatchCount(narrowing, table);

    // Save to Cache
    if (state.viewMode !== 'infinite') {
      state.pageCache.set(state.currentSkip, { data: copyRows(result.data), count });
    }

    state.isLoadingMore = false;
    // The rows are on screen. A caller that must say WHAT it showed asks this; the others ignore it.
    return true;
  } catch (err) {
    console.error('Failed to fetch data', err);
    elements.performanceLog.textContent = 'Data fetch failed';
    state.isLoadingMore = false;
  }
}

/** A cell value as a number when it is one or is spelled as one ("29.50"), else NaN. */
const asNumber = (v) => (typeof v === 'number' ? v : typeof v === 'string' && v.trim() !== '' ? Number(v) : NaN);

/** The same value on both sides - blank alike (absent.js isBlank); in a number column the same number however spelled
 *  (29.5, "29.50" - an edit keeps a number cell's old value as a number, a paste or a fill as the stored text; lead QA
 *  10-12); else the same text - a text column's "1.10" and "1.1" are two values (lead re-QA F2). */
function sameCellValue(a, b, colId) {
  if (isBlank(a) || isBlank(b)) return isBlank(a) && isBlank(b);
  if ((state.currentColumnTypes || {})[colId] === 'number') {
    const x = asNumber(a), y = asNumber(b);
    if (Number.isFinite(x) && Number.isFinite(y)) return x === y;
  }
  return String(a) === String(b);
}

/** A row with its own cell objects. The page cache keeps the server's rows and the grid edits its own in place, so
 *  the two never share one (lead QA 10-12: an edit written into the cached row came back as a conflict with itself). */
export const copyRow = (row) => (row && row.data ? { ...row, data: Object.fromEntries(Object.entries(row.data)
  .map(([col, cell]) => [col, cell && typeof cell === 'object' ? { ...cell } : cell])) } : row);
export const copyRows = (rows) => rows.map(copyRow);

/** Rows from the server as the grid draws them while edits are staged on them (lead 10-12): a staged cell shows its
 *  staged value, and an edit whose cell the server no longer holds at the value it was made over says so -
 *  `conflict: { server, at }`. Every place server rows reach the grid passes them here - a read, a cached page, a
 *  broadcast, a row jump - so a staged edit is never hidden under the server's value and sent over it unseen.
 *  Rows with nothing staged come back as they were; the others are copies (the page cache keeps the server's). */
export function overlayStagedEdits(rows) {
  const staged = Object.values(state.pendingTxEdits);
  if (!staged.length || !Array.isArray(rows)) return rows;
  const byRow = new Map();
  for (const edit of staged) byRow.set(edit.rowId, [...(byRow.get(edit.rowId) || []), edit]);
  const out = rows.map((row) => {
    const edits = row && byRow.get(row.row_id);
    if (!edits) return row;
    const data = { ...row.data };
    for (const edit of edits) {
      const cell = data[edit.colId];
      // A row without this column (a broadcast item may carry fewer) says nothing about this edit.
      if (!cell) continue;
      edit.conflict = sameCellValue(cell.value, edit.oldValue, edit.colId) ? null : { server: cell.value, at: row.updated_at || null };
      data[edit.colId] = { ...cell, value: edit.newValue };
    }
    return { ...row, data };
  });
  if (askingConflicts) sayConflicts(conflictedEdits().length);
  return out;
}

/** The staged edits of rows that are gone (deleted here, by a broadcast, or missing from Apply's read) are dropped -
 *  Apply would send them to no row (lead QA 10-12). Returns how many; `droppedText` is the bottom line's words. */
export function dropStagedEditsOf(rowIds) {
  const gone = new Set(rowIds);
  const keys = Object.keys(state.pendingTxEdits).filter((key) => gone.has(state.pendingTxEdits[key].rowId));
  for (const key of keys) delete state.pendingTxEdits[key];
  if (keys.length) {
    updateTxModeUI();
    if (askingConflicts) sayConflicts(conflictedEdits().length);
  }
  return keys.length;
}
export const droppedText = (count) => (count ? ` · ${unitText(count, 'staged edit')} dropped (row deleted)` : '');

/** Staged edits whose cell changed on the server since they were made. */
export const conflictedEdits = () => Object.values(state.pendingTxEdits).filter((edit) => edit.conflict);

/** The in-screen question Apply asks before sending a conflicted cell (lead 10-12 - not a confirm()). While it is up
 *  its count follows the conflicts, and it goes when they do (lead QA 10-12). */
let askingConflicts = false;
/** What the question asked about: each conflicted cell's key and the server value it named. An answer holds for these
 *  only (lead re-QA F1) - a conflict outside them, or one whose server value moved since, is asked again. */
let asked = null;
/** The question is over - answered, nothing left to apply, discarded, another table. Its line going because its
 *  conflicts went (the overlay, a dropped row) does not end it: an answer pressed as Apply's own read finds a cell back at
 *  the value it was edited over still holds for that cell (lead 10-13 1). */
function closeQuestion() {
  asked = null;
  sayConflicts(0);
}
function sayConflicts(count) {
  askingConflicts = count > 0;
  const line = elements.txConflictLine;
  if (!line) return;
  line.style.display = count > 0 ? '' : 'none';
  if (elements.txConflictText) {
    elements.txConflictText.textContent = count > 0 ? `${unitText(count, 'cell')} changed on the server since you edited` : '';
  }
}

/** Tx on - while edits are still staged (an Apply that asks, or one that could not read or save), and on a new table. */
function keepTxOn() {
  if (elements.txModeToggle) elements.txModeToggle.checked = true;
  state.txModeActive = true;
  updateTxModeUI();
}

/** Tx when an Apply or a Discard is done: on while edits are still staged, else what its toggle says - turned off to
 *  apply them, it goes off only now (lead 10-13 2). */
function settleTx() {
  if (Object.keys(state.pendingTxEdits).length) { keepTxOn(); return; }
  if (elements.txModeToggle) state.txModeActive = elements.txModeToggle.checked;
  updateTxModeUI();
}

/** The Tx toggle (main.js). Turned off with edits staged, it asks: apply them all or discard them all - and Tx stays on
 *  until that is done (settleTx), so an edit made while Apply's PUT is out is staged, not sent straight and then painted
 *  over by the batch's answer (lead 10-13 2; 18766: PUT [28.9] then [29.1], the cell 29.1 and at the end 28.9). */
export function txToggled() {
  const pendingCount = Object.keys(state.pendingTxEdits).length;
  if (elements.txModeToggle && !elements.txModeToggle.checked && pendingCount > 0) {
    if (confirm(`${pendingCount} pending edits. Apply them?\n\nOK applies them all.\nCancel discards them all.`)) applyPendingEdits();
    else discardPendingEdits();
    return;
  }
  settleTx();
  state.gridApi.refreshCells({ force: true });
}

/** The staged rows read again from the server, through the overlay, so a change no redraw brought (a refresh notice,
 *  an ingest's end, a dropped socket) is caught before Apply sends (lead QA 10-12). Rows the read no longer finds lose
 *  their edits. One read per REREAD_CHUNK rows - the ids ride in the url. Returns how many edits were dropped. */
const REREAD_CHUNK = 50;
async function rereadStagedRows() {
  const ids = [...new Set(Object.values(state.pendingTxEdits).map((edit) => edit.rowId))];
  // One deadline for the whole read, its bodies too - the one time cap a read that holds a screen gets (queue_poll.js
  // timedRead, the Queue tab's): past it Apply stops (lead 10-13 4, 6).
  const rows = await timedRead(async (signal) => {
    const read = [];
    for (let i = 0; i < ids.length; i += REREAD_CHUNK) {
      const part = ids.slice(i, i + REREAD_CHUNK);
      const filters = JSON.stringify({ row_id: { operator: 'OR', conditions: part.map((id) => ({ type: 'equals', filter: id })) } });
      const res = await gridFetch(`${API_BASE}/tables/${state.currentTable}/data?skip=0&limit=${part.length}`
        + `&defer_total=true&filters=${encodeURIComponent(filters)}`, { signal });
      if (!res.ok) throw new Error(await refusalText(res, 'The staged rows could not be read again'));
      read.push(...(await res.json()).data);
    }
    return read;
  });
  const onGrid = overlayStagedEdits(rows).filter((row) => state.gridApi.getRowNode(row.row_id));
  if (onGrid.length) state.gridApi.applyTransaction({ update: onGrid });
  // The cached pages take the server's rows too - a page drawn from a stale cache would claim a conflict with a value
  // already gone (18766: a silent write, Take server, another page and back -> «conflict» with the old value).
  const fresh = new Map(rows.map((row) => [row.row_id, row]));
  for (const cached of state.pageCache.values()) {
    cached.data = cached.data.map((row) => (fresh.has(row.row_id) ? copyRow(fresh.get(row.row_id)) : row));
  }
  const found = new Set(fresh.keys());
  return dropStagedEditsOf(ids.filter((id) => !found.has(id)));
}

/** Apply the staged edits. Conflicted cells are not sent unasked: without `choice` Apply stops and asks; 'mine' sends
 *  them, 'server' drops them and draws the server's value - the cells without a conflict go as they always did. */
let applying = false;
export async function applyPendingEdits(choice = null) {
  // A second click while the first Apply is on the wire would send the same edits twice (lead QA 10-12) - and it says so.
  if (applying) { elements.performanceLog.textContent = 'Already applying'; return; }
  applying = true;
  try {
    const handingOver = closeOpenEditor();
    if (handingOver) await handingOver;
    await applyStaged(choice);
  } finally {
    applying = false;
  }
}

/** An editor still open when Apply is pressed: its value goes with this Apply (lead 10-13). The grid hands a changed
 *  value to handleCellEdit only after a timeout (AG Grid fires its public events async), so Apply closes the editor and
 *  waits for that hand-over - an event, not a pause: the promise of it, or null when there is nothing to wait for (no
 *  editor, or a value that did not change and so hands nothing over). */
function closeOpenEditor() {
  const api = state.gridApi;
  const [open] = (api && api.getEditingCells && api.getEditingCells()) || [];
  if (!open) return null;
  const node = api.getDisplayedRowAtIndex(open.rowIndex);
  const colId = open.column.getColId();
  const read = () => api.getCellValue({ rowNode: node, colKey: colId });
  const key = node && node.data ? `${node.data.row_id}_${colId}` : null;
  const before = key ? read() : undefined;
  const handedOver = key ? new Promise((resolve) => cellHandedOver.set(key, resolve)) : null;
  api.stopEditing();
  if (!key) return null;
  if (Object.is(read(), before)) { cellHandedOver.delete(key); return null; }
  return handedOver;
}

async function applyStaged(choice) {
  if (Object.keys(state.pendingTxEdits).length === 0) { closeQuestion(); return; }
  let dropped = 0;
  const rowsStaged = new Set(Object.values(state.pendingTxEdits).map((edit) => edit.rowId)).size;
  elements.performanceLog.textContent = `Checking ${unitText(rowsStaged, 'row')} on the server…`;
  try {
    dropped = await rereadStagedRows();
  } catch (err) {
    // The edits are still staged: Tx comes back on if it was turned off to apply them (lead re-QA F4).
    keepTxOn();
    elements.performanceLog.textContent = `Apply stopped: ${err instanceof QueueReadTimeout
      ? `the staged rows did not answer in ${QUEUE_READ_TIMEOUT_MS / 1000} s` : err.message}`;
    return;
  }
  if (Object.keys(state.pendingTxEdits).length === 0) {
    closeQuestion();
    settleTx();
    elements.performanceLog.textContent = `Nothing applied${droppedText(dropped)}`;
    return;
  }
  const conflicted = conflictedEdits();
  const keyOf = (edit) => `${edit.rowId}_${edit.colId}`;
  // An answer holds for what was asked: every conflict now among those, at the server value it named (lead re-QA F1).
  // Keep mine wants the same set both ways, or no conflict left; Take server takes a smaller set too - it drops every
  // cell it was asked about below (lead 10-13 1).
  const within = Boolean(choice && asked) && conflicted.every((edit) => asked.has(keyOf(edit))
    && sameCellValue(asked.get(keyOf(edit)), edit.conflict.server, edit.colId));
  const answered = within && (choice === 'server' || conflicted.length === 0 || conflicted.length === asked.size);
  if (conflicted.length && !answered) {
    // Tx off with a conflict asks too - Tx comes back on, since the edits are still staged (lead QA 10-12).
    keepTxOn();
    sayConflicts(conflicted.length);
    asked = new Map(conflicted.map((edit) => [keyOf(edit), edit.conflict.server]));
    return;
  }
  const askedKeys = asked ? [...asked.keys()] : [];
  closeQuestion();
  if (choice === 'server') {
    // Every cell asked about goes, at the server's value - one whose server value went back to the value it was edited
    // over too: it conflicts no more, and would otherwise go as mine (lead 10-13 1).
    for (const key of askedKeys) {
      const edit = state.pendingTxEdits[key];
      if (!edit) continue;
      const node = state.gridApi.getRowNode(edit.rowId);
      if (node && node.data) {
        ensureCellObject(node.data, edit.colId);
        node.data.data[edit.colId].value = edit.conflict ? edit.conflict.server : edit.oldValue;
      }
      delete state.pendingTxEdits[key];
    }
    state.gridApi.refreshCells({ force: true });
    if (Object.keys(state.pendingTxEdits).length === 0) { settleTx(); return; }
    updateTxModeUI();
  }

  elements.performanceLog.textContent = 'Applying batch transaction updates...';
  const applyStartTime = performance.now();

  // What goes out, by key and value: an edit made while the PUT is out is not among it and stays staged (lead re-QA F3).
  const sent = new Map(Object.entries(state.pendingTxEdits).map(([key, edit]) => [key, edit.newValue]));
  const grouped = {};
  Object.values(state.pendingTxEdits).forEach(edit => {
    if (!grouped[edit.rowId]) {
      grouped[edit.rowId] = {};
    }
    grouped[edit.rowId][edit.colId] = edit.newValue;
  });

  const updates = Object.keys(grouped).map(rowId => ({
    row_id: rowId,
    updates: grouped[rowId],
    source_name: 'user',
    updated_by: CURRENT_USER
  }));

  const payload = {
    updates: updates,
    silent: false,
    // V1 instrument: optional field. Raw counts only — the server weights at query time.
    effort: snapshot()
  };

  try {
    // The save under the same cap as the read: a PUT that never answers would hold Apply shut (lead 10-13 5).
    const result = await timedRead(async (signal) => {
      const res = await fetch(`${API_BASE}/tables/${state.currentTable}/data/updates`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload),
        signal
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Save failed');
      }
      return res.json();
    });
    state.pageCache.clear();
    const saveTime = (performance.now() - applyStartTime).toFixed(1);

    // The cells it sent are saved: drawn so, and their edits go. One edited again while it was out stays staged, now
    // made over the value just saved; one made while it was out was never sent and stays as it is.
    for (const [key, value] of sent) {
      const edit = state.pendingTxEdits[key];
      if (!edit) continue;
      if (edit.newValue !== value) {
        edit.oldValue = value;
        edit.conflict = null;
        continue;
      }
      const latestNode = state.gridApi.getRowNode(edit.rowId);
      const latestData = latestNode ? latestNode.data : edit.data;
      if (latestData) {
        markCellOverwritten(latestData, edit.colId, edit.newValue);
        latestData.updated_at = getLocalTimeString();
      }
      delete state.pendingTxEdits[key];
    }
    // V1 instrument: reset ONLY when the server confirms it recorded the effort. Two
    // gates, not one: a failed save keeps accumulating because retry effort is real human
    // effort, and a 200 that changed nothing (every staged edit already matched storage)
    // records no effort row — resetting there would delete the effort it cost.
    commitIfRecorded(result);
    settleTx();
    updateGridSortState();
    state.gridApi.refreshCells({ force: true });

    elements.performanceLog.textContent = `Applied batch updates in ${saveTime}ms (${result.change_count} cells updated)${droppedText(dropped)}`;
  } catch (err) {
    // Not saved: the edits are still staged, so Tx comes back on (lead 10-13 3 - the read's F4, for the save).
    keepTxOn();
    console.error('Batch apply failed', err);
    alert(`Apply failed: ${err instanceof QueueReadTimeout
      ? `the save did not answer in ${QUEUE_READ_TIMEOUT_MS / 1000} s - Apply again reads the rows first` : err.message}`);
    elements.performanceLog.textContent = '❌ Batch apply failed';
  }
}

/** The rows on screen read again from the server - the Refresh button's read, and Discard's (lead 10-12). */
export function rereadGrid() {
  state.pageCache.clear();
  if (state.viewMode === 'infinite' || state.allDataLoaded) {
    state.allDataLoaded = false;
    state.hasMoreData = true;
    return fetchData(true);
  }
  return fetchData(false);
}

/** Discard the staged edits: each cell back at once to the value it had when edited, then the rows read again from the
 *  server - a write or a Refresh since makes that value stale, and the read corrects it (lead 10-12; 18766: a stored
 *  28.5 drawn as the 28 from before the edit until Refresh). */
export function discardPendingEdits() {
  const staged = Object.values(state.pendingTxEdits);
  if (staged.length === 0) return Promise.resolve();
  for (const { rowId, colId, oldValue, oldIsOverwrite, oldPrioritySource, data } of staged) {
    const node = state.gridApi.getRowNode(rowId);
    const row = node ? node.data : data;
    if (!row) continue;
    ensureCellObject(row, colId);
    row.data[colId].value = oldValue;
    // 🔴 C-22. Both halves: the paint rule reads `priority_source`, never `is_overwrite`.
    row.data[colId].is_overwrite = oldIsOverwrite;
    row.data[colId].priority_source = oldPrioritySource ?? null;
  }
  state.pendingTxEdits = {};
  closeQuestion();
  settleTx();
  state.gridApi.refreshCells({ force: true });
  elements.performanceLog.textContent = 'Pending updates discarded';
  return rereadGrid();
}

/** An Apply waiting for a cell's edit to be handed over, by cell key (closeOpenEditor). */
const cellHandedOver = new Map();

// Handle inline editing updates to DB
export async function handleCellEdit(event) {
  try {
    await editCell(event);
  } finally {
    // Every way out of it - staged, sent, refused, unchanged - lets an Apply waiting on this cell go on.
    const key = `${event.data && event.data.row_id}_${event.colDef && event.colDef.field}`;
    const handedOver = cellHandedOver.get(key);
    cellHandedOver.delete(key);
    if (handedOver) handedOver();
  }
}

async function editCell(event) {
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
        alert(notANumber(colId, newValue));
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
        // 🔴 C-22. The undo restores what this record holds, and it held only HALF the pair:
        //    `is_overwrite` came back and `priority_source` did not, so discarding a staged edit
        //    left the cell claiming a pin it no longer had. Both non-tx paths in this same
        //    function already capture and restore both (the refusal path just above), so the
        //    transaction path was the one place not doing what its neighbours do.
        //    The value is already computed at the top of this function; the record simply
        //    dropped it.
        oldPrioritySource: oldPrioritySource,
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

      markCellOverwritten(latestData, colId, finalValue);

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
    alert(`Save failed: ${err.message}`);
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
  // 🔴 C-102 ①. 네 번째 깔때기. 붙여넣기·지우기·일괄채우기가 이미 이 모양이고, 이것만
  //    빠져 있어서 뷰에서 «서버까지» 갔습니다. 거절이 깔때기에 있어야 버튼이 아닌 다른
  //    경로로 불려도 같은 답이 납니다 (criterion ④).
  if (refuseWrite()) return;
  setBadge(elements.performanceLog, `Creating ${count} empty row(s)...`);
  // 🔴 C-102 ②. 거절의 «사유»는 서버의 것입니다 — 이 파일이 이미 그렇게 하는 자리가 있고
  //    (:528 `errData.detail`), 이 한 자리만 `Error('Create failed')` 로 접고 있었습니다.
  //    접으면 운영자는 「무엇이 · 왜」를 콘솔에서도 못 봅니다.
  // ⚠️ 화면 쓰기가 `catch` «밖»입니다 — 이 파일의 머리글이 말하는 그대로입니다:
  //    catch 안에서 DOM 을 쓰면 «처리된» 장애가 처리되지 않은 거절이 됩니다.
  let refused = '';
  try {
    const res = await fetch(`${API_BASE}/tables/${state.currentTable}/rows?count=${count}&user_name=${encodeURIComponent(CURRENT_USER)}`, {
      method: 'POST'
    });
    if (res.ok) {
      setBadge(elements.performanceLog, `${count} empty row(s) created successfully`);
      return;
    }
    // 🔴 C-105. 읽기와 «같은 함수»를 지납니다 — 사유를 만드는 자리가 둘이면 갈라집니다.
    refused = await refusalText(res, 'Create failed');
  } catch (err) {
    console.error('Failed to create row(s)', err);
    // 서버에 «닿지 못한» 것은 서버가 낸 사유가 없는 자리라 이 문장이 화면의 것입니다.
    refused = 'Add-row request did not reach the server (network)';
  }
  setBadge(elements.performanceLog, refused);
  showToast(refused, 'error');
}

// Delete selected rows batch
//
// 🔴 a0ae05b60 (소유자 「ㄱ, 한 1만행」). 기다림이 «보입니다» — 지우기 버튼은 사유와 함께 꺼지고
//    상태줄이 초를 셉니다. 끝나면 그 행들을 «여기서» 뺍니다. 거절은 서버의 문장 그대로에 다음
//    행동 하나를 붙입니다 — 커밋 뒤 방송에서 실패할 수도 있어 「안 지워졌다」고는 말하지 않습니다.
export async function deleteSelectedRows() {
  if (!state.gridApi || state.isDeletingRows) return;
  const selectedNodes = state.gridApi.getSelectedNodes();
  if (selectedNodes.length === 0) {
    alert('No rows selected for deletion');
    return;
  }

  const rowIds = selectedNodes.map(node => node.data.row_id).filter(Boolean);
  if (rowIds.length === 0) return;

  if (!confirm(`Are you sure you want to permanently delete the selected ${unitText(rowIds.length, 'row')}?`)) return;

  state.isDeletingRows = true;
  const startedAt = Date.now();
  const seconds = () => Math.floor((Date.now() - startedAt) / 1000);
  const tick = () => {
    elements.performanceLog.textContent = `Deleting ${unitText(rowIds.length, 'row')} · ${seconds()} s`;
  };
  setDisabledReason(elements.deleteRowBtn, 'Deleting…');
  tick();
  const timer = setInterval(tick, 1000);
  let refused = '';
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
      // ⚠️ Only the rows still in the grid: the broadcast may have taken them first, and AG-Grid
      //    warns once per id it cannot find.
      const left = rowIds.filter((rowId) => state.gridApi.getRowNode(rowId));
      if (left.length) state.gridApi.applyTransaction({ remove: left.map((rowId) => ({ row_id: rowId })) });
      updateLoadedCount();
      elements.performanceLog.textContent = `Deleted ${unitText(result.deleted_count, 'row')} · ${seconds()} s${droppedText(dropStagedEditsOf(rowIds))}`;
    } else {
      refused = await refusalText(res, 'Delete failed');
    }
  } catch (err) {
    console.error('Failed to delete rows', err);
    refused = 'Delete request did not reach the server (network)';
  } finally {
    clearInterval(timer);
    state.isDeletingRows = false;
    setDisabledReason(elements.deleteRowBtn, writeRefusal());
  }
  if (!refused) return;
  const line = `${refused} — reload the table to see which rows remain`;
  setBadge(elements.performanceLog, line);
  showToast(line, 'error');
}
