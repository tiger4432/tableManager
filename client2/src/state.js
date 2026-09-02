export const state = {
  gridApi: null,
  currentTable: '',
  currentColumns: [],
  currentColumnTypes: {},
  currentBusinessKey: '',          // 비즈니스 키 컬럼명 (예: 'pkg_id')
  currentCompositeKeySources: [],  // 조합 소스 컬럼 목록 (예: ['base', 'x', 'y'])
  // [Virtual join] `/schema`'s `virtual_columns`, verbatim. Entries are
  // `{name, type, editable:false, right_table, rule, unresolved_label}`.
  //
  // 🔴 DELIBERATELY NOT MERGED INTO `currentColumns`. That list means "columns this table
  // STORES", and its consumers read it as exactly that: `clipboard.js`'s copy predicates,
  // `grid.js`'s editability, and — through `/schema.columns` rather than this list —
  // `map_editor.js:getUnprotectedPushColumns`, which counts unprotected data columns a
  // ⚡ Push would destroy. A virtual column cannot be lost by a push because it is not
  // stored, so counting it there would downgrade or block a push for no reason.
  // Keeping the two lists apart is what makes each of those answers stay right.
  //
  // `api.js`'s search dropdown USED to be in that list and no longer is: `?cols=` now
  // reaches join-resolved names, so it unions the WIDER announcement below instead. It is
  // still not merged here — a searchable name is not a stored one.
  currentVirtualColumns: [],
  // [Virtual join] `/schema`'s `join_resolved_columns`, verbatim. Entries are
  // `{name, kind: 'collide'|'virtual_only', rule, right_table, unresolved_label}`.
  //
  // 🔴 A DIFFERENT QUESTION FROM `currentVirtualColumns`, which is why it is a second list
  // and not a flag on the first. `virtual_columns` answers "which columns must the grid
  // ADD"; this answers "which columns does the SERVER resolve through a join, and what
  // does it call the unresolved case". The two sets differ exactly on `kind: 'collide'` —
  // a column that IS stored (so it is in `currentColumns`, editable, writable) and whose
  // filter the server nonetheless evaluates against the joined COALESCE rather than
  // against storage. Reading `virtual_columns` to answer the second question silently
  // misses every collide column.
  //
  // 🔴 NOT A WRITE GUARD. Editability is `currentColumns` vs `currentVirtualColumns`, and
  // the enforcement is `crud.refuse_virtual_join_columns` on the server. This list carries
  // no writability field on purpose: a collide column is join-resolved AND writable.
  currentJoinResolvedColumns: [],
  ws: null,
  wsReconnectDelay: 1000,
  // The single pending reconnect timer, or null. Held so a wake signal can CANCEL the wait
  // instead of racing it — without this handle the only way to reconnect early would be to
  // open a second socket alongside the one the timer is about to open.
  wsRetryTimer: null,
  // When the current socket opened (0 = not open). The flap guard in `websocket.js` reads it
  // to tell a healthy session from a connection that died on arrival.
  wsOpenedAt: 0,
  // The rung the ladder was on when the socket opened, so a flap can resume the climb instead
  // of restarting it at the base delay.
  wsPrevReconnectDelay: 1000,
  // Last time a visibility/online signal forced an immediate retry — the throttle's memory.
  wsLastWakeAt: 0,
  // The connect watchdog's timer handle, or null. A socket stuck in CONNECTING delivers no
  // onopen, no onclose and no onerror, so this timer is the ONLY thing that can fail such an
  // attempt and hand it to the backoff ladder. Cleared on open, on close, and whenever a socket
  // is replaced — a timer that outlives its socket would fire against the NEXT connection.
  wsConnectWatchdog: null,
  // When the socket currently in flight was created. Lets `wakeNow` tell a socket that is
  // negotiating right now from one that has been "negotiating" for seconds, which is a hang
  // wearing the same readyState.
  //
  // 🔴 THE ZERO HERE IS "UNSET", NOT A SENTINEL ANYONE MAY TEST FOR. `Date.now()` can legally
  // BE 0, and reading this field for truthiness rather than reading `state.ws.readyState`
  // silently made a socket created at epoch 0 permanently unwakeable. Ask readyState whether
  // something is in flight; only then is this number meaningful.
  wsConnectingSince: 0,
  // How many attempts the watchdog has torn down. Distinct from the attempt counter on purpose:
  // a server that refuses is not a route that blackholes, and today's incident was prolonged by
  // a badge that could not tell two states apart. This one is on the badge for the same reason.
  wsWatchdogTrips: 0,
  // The wake listeners are attached once for the life of the page, not once per reconnect.
  wsWakeSignalsInstalled: false,
  selectedCell: null, // { rowId, colId, value, rowIndex }
  activeHistoryTab: 'global',
  dragStartCell: null,
  dragEndCell: null,
  selectedCellsMap: {}, // key: "rowIndex_colId"
  isDraggingRange: false,
  globalHistoryData: [],
  cellRowHistoryData: [],
  // [History paging] The `/history` envelope's fields, held BESIDE the list and never on it.
  //
  // 🔴 `cellRowHistoryData` MUST STAY A PLAIN ARRAY. `renderTimelineIncremental` and
  //    `appendHistoryLocally` (timeline.js) `unshift`/`some` straight into it when a WebSocket
  //    log arrives, so the moment it becomes an envelope object every live update on the
  //    sidebar throws. The server answers `{logs, truncated, next_cursor, limit, returned}`;
  //    `logs` is what lands here and the rest lands in the three fields below.
  //
  // The cursor is OPAQUE (base64url of a `(timestamp, id)` keyset position). It is never
  // parsed, never constructed here, and only ever handed back verbatim as `?cursor=`.
  cellRowHistoryCursor: null,
  // True == the server said there is older history past what is on screen. This is the ONLY
  // thing that distinguishes a capped list from a complete one, and the 더 보기 control is how
  // it reaches the operator — a list that just ends where the page ended is a wrong answer,
  // not a slow one.
  cellRowHistoryTruncated: false,
  // Rows PAGED IN from the server, across all pages of the current session. Deliberately not
  // `cellRowHistoryData.length`: that array also collects live WebSocket appends, which are not
  // part of what the pager fetched and would make the control's count drift upward on its own.
  cellRowHistoryLoaded: 0,
  // [Cell history] Audit entries on the ROW the selected cell belongs to — i.e. the population
  // the Row History tab pages through. CELL ROUTE ONLY; `null` on the row tab, where
  // `cellRowHistoryLoaded`/`cellRowHistoryTruncated` already describe the same population.
  //
  // 🔴 THE ONE FACT THAT TELLS THE TWO EMPTY TABS APART. Machine writes (parsers, chains,
  //    scripts) store ONE audit row per ROW under the literal column name `ROW_UPDATE`, so the
  //    cell route's `column_name == col` filter can never match them. An empty cell tab with
  //    `> 0` here means the records EXIST and this view cannot show them — 225,101 rows in the
  //    isolated `assy_qa` copy are in exactly that state. Drawing that the same as "기록 없음"
  //    was the defect; this field is what makes the difference representable on screen.
  cellRowHistoryRowTotal: null,
  // True == the count above is a FLOOR, not exact (the server probes it capped). Named `IsFloor`
  // rather than `Truncated` on purpose: in this module `truncated` already means "the LIST is
  // capped, page for more", and a count that is a lower bound is a different fact. Conflating
  // them would hang the 더 보기 pager off a number.
  cellRowHistoryRowTotalIsFloor: false,
  // The paging session token. Bumped by every fresh `loadHistory()`, so a 더 보기 still in
  // flight when the operator clicks another cell can tell that its page belongs to a list that
  // is no longer on screen — appending the previous row's page 2 onto this row's page 1 is the
  // defect this counter exists to prevent, and those rows would all be real.
  cellRowHistorySession: 0,
  expandedTransactions: new Set(),
  fetchingTransactions: new Set(),
  currentTransactionId: null,
  colIdToIndexMap: {},
  currentSkip: 0,
  isLoadingMore: false,
  hasMoreData: true,
  isNavigating: false,
  navigationWatchdog: null,
  pageCache: new Map(),
  txModeActive: true,
  pendingTxEdits: {}, // key: row_id + "_" + col_name -> { rowId, colId, newValue, oldValue, oldIsOverwrite, data }
  viewMode: 'pagination', // 'pagination' | 'infinite'
  allDataLoaded: false,
  // 🔴 브라우저에서는 전과 «같은 값»입니다 -- window 가 있으면 같은 질의문자열을 읽습니다.
  //    window 가 «없는» 곳(node)에서는 false 이고, 그게 데스크톱이 아닌 것과 같은 답입니다.
  //    이 한 줄이 state.js 를 import 불가로 만들고, state.js 를 import 하는
  //    api.js · grid.js · clipboard.js · timeline.js «넷»을 같이 막고 있었습니다.
  isDesktop: typeof window !== 'undefined' && window.location
    ? new URLSearchParams(window.location.search).get('client') === 'desktop'
    : false,
  dragRefreshPending: false,
  visibleColIndexMap: {}, // key: colId -> visibleIndex
  // Smart paste latch. `navigator.clipboard` is undefined on the plain-HTTP intranet, so the
  // ONLY way to read the clipboard is a native `paste` event - which a button click cannot
  // produce (`document.execCommand('paste')` is blocked in web content). This timestamp is
  // the window during which the next `paste` event is routed to the parser instead of to the
  // normal cell-range paste. 0 = not armed. Consumed on use, expires on its own otherwise.
  smartPasteArmedUntil: 0,
  // The table that was on screen when the latch was armed. If it changed before the paste
  // landed the upload is refused - this path INGESTS, and a file in the wrong table is a
  // data error rather than a cosmetic one.
  smartPasteArmedTable: ''
};

/**
 * [Virtual join] Is this grid column id a join-attached column rather than a stored one?
 *
 * WHY A PREDICATE AND NOT A LIST MEMBERSHIP TEST AT EACH SITE. Every write funnel in this
 * client answers "may I write this grid column?" with its own hardcoded system-name array
 * (`clipboard.js` x3, `ui.js`). Those arrays are name lists and a virtual column's name is
 * site-specific, so it cannot join them. This is the one place that knows the answer.
 *
 * 🔴 THIS IS NOT THE ENFORCEMENT. The server refuses a write to a virtual column in
 * `crud.refuse_virtual_join_columns`, at the single funnel every write path converges on.
 * This predicate only stops the client OFFERING a write that would come back 400 — and the
 * refusal is BATCH-LEVEL, so one pasted block overlapping a virtual column would lose the
 * whole paste, not just the cell it could not have written anyway.
 */
export function isVirtualColumn(colId) {
  const list = state.currentVirtualColumns;
  if (!Array.isArray(list) || list.length === 0) return false;
  return list.some(vc => vc && vc.name === colId);
}

/**
 * [Virtual join] The `join_resolved_columns` entry for this grid column, or `null`.
 *
 * Returns the ENTRY rather than a boolean because every caller needs the payload: the
 * `unresolved_label` is per declaration, so a client that answers "yes/no" here has to go
 * looking for the label a second time — and the site that goes looking is the site that
 * ends up hardcoding '미상'. A configured site that changes the label must see the change.
 *
 * 🔴 SEPARATE FROM `isVirtualColumn`, DELIBERATELY. `isVirtualColumn` asks "did /schema ADD
 * this column" and is the right question for the write funnels (`clipboard.js`, `ui.js`),
 * which must not offer an edit the server will refuse. This asks "does the server resolve
 * this column through a join", which is the right question for FILTERING — and a collide
 * column answers no to the first and yes to the second.
 */
export function joinResolvedColumn(colId) {
  const list = state.currentJoinResolvedColumns;
  if (!Array.isArray(list) || list.length === 0) return null;
  return list.find(e => e && e.name === colId) || null;
}

/**
 * Visible column ids in visible order, '#' (the row-number gutter) excluded.
 * Ordered by the index map's VALUES rather than trusting key insertion order, so it
 * cannot silently disagree with `visibleColIndexMap` after a column move.
 *
 * 🔴 LIVES HERE, NEXT TO THE TWO FIELDS IT READS, and not in `grid.js` where it was
 * written. It answers a question about `state` alone — `visibleColIndexMap` and `gridApi` —
 * so `grid.js` was never more than its first caller. The second caller is the reference
 * panel's alignment band, which must know the paste target's column order, and importing
 * `grid.js` to get it would have formed a CYCLE: `grid.js` already imports
 * `refreshReferenceForSelection` from that module. Copying the four lines instead would
 * have been a second implementation of column order, which is exactly the kind of pair that
 * later disagrees about what '#' means.
 */
export function visibleRangeColIds() {
  const map = state.visibleColIndexMap || {};
  const ids = Object.keys(map).filter(id => id !== '#');
  if (ids.length > 0) return ids.sort((a, b) => map[a] - map[b]);
  if (!state.gridApi) return [];
  return (state.gridApi.getColumnState() || [])
    .filter(c => !c.hide && c.colId !== '#')
    .map(c => c.colId);
}

export function updateVisibleColIndexMap() {
  if (!state.gridApi) return;
  const colState = state.gridApi.getColumnState() || [];
  const indexMap = {};
  let visibleIdx = 0;
  colState.forEach(c => {
    if (!c.hide) {
      indexMap[c.colId] = visibleIdx;
      visibleIdx++;
    }
  });
  state.visibleColIndexMap = indexMap;
}
