import { createGrid, ModuleRegistry, AllCommunityModule } from 'ag-grid-community';
import 'ag-grid-community/styles/ag-grid.css';
import 'ag-grid-community/styles/ag-theme-quartz.css';
import './tokens.css';
import './style.css';
import { initTheme } from './theme.js';
import { API_BASE, CURRENT_USER, pageLimit } from './config.js';
import { state } from './state.js';
import { elements } from './dom.js';
import {
  checkServerHealth,
  loadTables,
  switchTable,
  fetchData,
  addRows,
  deleteSelectedRows
} from './api.js';
import { initWebSocket } from './websocket.js';
import { GridSourceLabel } from './grid_source_label.js';
import {
  loadHistory,
  triggerHistoryReloadDebounced,
  navigateToLog,
  installAuditFilters
} from './timeline.js';
import {
  isCellInRange,
  refreshRange,
  refreshSelectedRangeDiff,
  clearRangeSelection,
  commitDragSelection,
  setupClipboardHandlers,
  registerSmartPasteHandler,
  clearSelectedCells
} from './clipboard.js';
import {
  updateGridSortState,
  updateLoadedCount,
  updateViewModeUI,
  updatePaginationUI,
  ensureCellObject,
  renderGrid
} from './grid.js';
import {
  showToast,
  dismissToasts,
  showIngestionProgress,
  finishIngestionProgress,
  getLocalTimeString
} from './utils.js';
import {
  updateSelectedCellUI,
  updateTxModeUI,
  setTransactionFilter,
  applyValueToSelectedRange,
  setupBeforeUnloadWarning,
  updatePageCacheOnUpsert,
  updatePageCacheOnDelete
} from './ui.js';
import { initTraceEntry } from './trace_launch.js';

// Every control that shows `localStorage['copyHeader']`. Read through `elements`' lazy
// getters, the convention the whole module already uses, and `filter(Boolean)` so a missing
// one is skipped instead of throwing -- this runs inside `init()`, where a throw takes the
// WebSocket down with it.
const copyHeaderToggles = () =>
  [elements.copyHeaderToggle, elements.copyHeaderMenuToggle].filter(Boolean);
import { hideReferenceView, installReferenceKeyboardIsolation, showReferenceView } from './enrichment_reference_view.js';
import {
  startSession,
  installGlobalListeners,
  installNavLinkCounting,
  countNav,
  snapshot,
  commitIfRecorded,
  ROUTES
} from './effort_meter.js';

// Register AG-Grid Community Modules
ModuleRegistry.registerModules([AllCommunityModule]);

// View Mode State
let viewMode = 'pagination'; // 'pagination' | 'infinite'
let allDataLoaded = false;

// Initialize Application
async function init() {
  // 웹 브라우저에서 접근 시, 백그라운드에서 로컬 데스크톱 앱 자동 실행을 시도하던 로직을 사용자 요청에 따라 주석 처리합니다.
  /*
  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.get('client') !== 'desktop') {
    console.log('[Launcher] Triggering local desktop client launch via URI scheme...');
    const iframe = document.createElement('iframe');
    iframe.style.display = 'none';
    iframe.src = 'assymanager://open';
    document.body.appendChild(iframe);
    setTimeout(() => iframe.remove(), 1000);
  }
  */

  // THE LIVE CHANNEL IS NOT GATED ON ANYTHING ELSE. This used to be the LAST statement of
  // `init()`, after `await checkServerHealth()` and `await loadTables()`. Since the whole
  // reconnect ladder lives inside `initWebSocket`, anything that stopped `init()` short of this
  // line left the page with no socket AND no retry, for the rest of the session — reproduced
  // three ways (see startup_socket_gate_harness.mjs): a `catch` block that itself throws on a
  // null DOM handle, and a `fetch` that never settles (a hung backend or proxy), which does not
  // even reject and so logs nothing at all.
  //
  // FIRST, not merely "earlier". Every setup call below can throw too — `elements.sortLatestToggle
  // .checked` on the next lines is an unguarded handle — so the socket goes ahead of ALL of it.
  // (It used to name `copyHeaderToggle`; that one is now read through a `filter(Boolean)` list,
  // which is why the example moved rather than the rule.)
  // Opening it has no dependency on health status or the table list: `initWebSocket` reads only
  // WS_URL, `state`, and the wake signals, and its `onopen` re-derives what it needs
  // (`checkServerHealth`, then `loadTables` only if the picker is still empty). The overlap that
  // creates with `loadTables()` below is de-duplicated by an in-flight latch in api.js.
  initWebSocket();

  // Load cached settings from localStorage
  const cachedCopyHeader = localStorage.getItem('copyHeader');
  if (cachedCopyHeader !== null) {
    copyHeaderToggles().forEach(toggle => { toggle.checked = cachedCopyHeader === 'true'; });
  }
  const cachedSortLatest = localStorage.getItem('sortLatest');
  if (cachedSortLatest !== null) {
    elements.sortLatestToggle.checked = cachedSortLatest === 'true';
  }

  initTheme();
  // V1 instrument: start counting human effort before any listener can fire.
  // Invisible by design — no UI, no badge. See effort_meter.js.
  startSession();
  installGlobalListeners();
  installNavLinkCounting(ROUTES.GRID); // covers the nav dropdown anchors in index.html
  setupEventListeners();
  // 라벨은 표보다 «먼저» 섭니다 -- 선언 읽기가 표 로드와 나란히 가고, 표가 정해지면
  // `setRelation` 한 번으로 문장이 확정됩니다.
  sourceLabel = initGridSourceLabel();
  installReferenceKeyboardIsolation();
  installAuditFilters();
  initTraceEntry(); // G2 추적 진입점 (mapping-summary 기반 표시 — fire-and-forget)
  setupClipboardHandlers();
  // The `paste` listener in clipboard.js owns the only readable clipboard on plain HTTP;
  // this hands it the smart-paste reader without clipboard.js having to import main.js.
  registerSmartPasteHandler(smartPasteFromPasteEvent);
  setupDragAndDrop();
  // 소켓은 이 함수 **첫 줄**에서 이미 열렸다(위 참조). 이 둘은 이제 소켓을 막을 수 없다.
  // 📌 남은 결: `checkServerHealth`가 reject하면 `loadTables`가 건너뛰어져 테이블 목록이
  //    비어 있게 된다. 각각 감싸면 막히지만, 그러면 하네스의 M1/M9 앵커(원래 사고를
  //    재조립하는 변이)가 안 맞아 **적용조차 안 된다** ― 앵커를 같이 옮기는 일이라
  //    운영 사고 수리에 얹지 않는다. 별건으로 남긴다.
  await checkServerHealth();
  await loadTables();
  // 🔴 부팅 자동 선택도 «표를 고른 것»입니다. 여기서 안 알려 주면 첫 화면의 라벨만
  //    조용히 비고, 사용자가 표를 «한 번 바꿔야» 나타납니다 (그 침묵이 「아님」처럼 보입니다).
  if (sourceLabel) sourceLabel.setRelation(state.currentTable);
}

// 🔴 주소는 «합성 루트»가 압니다 (조립식 상설). 부품은 라우트도 apiBase 도 모르고
//    이 함수 하나를 받습니다. 성공도 실패도 «같은 모양»(`{ok}`)으로 답해서, 읽는 쪽이
//    「못 읽음」과 「소스가 아님」을 구별할 수 있게 합니다.
async function loadLedgerDeclaration() {
  try {
    const res = await fetch(`${API_BASE}/api/ledger/declaration`);
    const body = await res.json().catch(() => null);
    if (!res.ok || !body) {
      // 🔴 «사유»만 돌려줍니다. 부품이 「선언을 못 읽었습니다」를 이미 말하므로, 여기서 같은
      //    문장을 또 쓰면 화면에 두 번 나옵니다 (실측 2026-08-31에 실제로 그렇게 나왔습니다).
      return { ok: false, message: `서버가 ${res.status} 로 거절했습니다` };
    }
    return { ok: true, sources: Array.isArray(body.sources) ? body.sources : null };
  } catch (err) {
    return { ok: false, message: `라우트에 닿지 못했습니다 — ${err && err.message}` };
  }
}

// 그리드 머리의 원장 소스 라벨. 자기 div 하나를 받고, 표 이름은 «화면이» 알려 줍니다.
let sourceLabel = null;
function initGridSourceLabel() {
  const host = document.getElementById('grid-source-label-host');
  if (!host) return null;
  const part = new GridSourceLabel(host, {
    doc: document,
    loadDeclaration: loadLedgerDeclaration,
  });
  part.mount();
  return part;
}

// Event Listeners Setup
function setupEventListeners() {
  // admin 계정 접속 시 그래프 동기화 버튼 활성화 및 클릭 연동
  const urlParams = new URLSearchParams(window.location.search);
  const isAdmin = CURRENT_USER.toLowerCase() === 'admin' || 
                  window.location.pathname.includes('admin') || 
                  urlParams.get('user') === 'admin' ||
                  localStorage.getItem('isAdmin') === 'true';
  // ⚰️ [판정 R-2026-08-14-H] 구 그래프 갈래 은퇴 — 이 버튼은 더 이상 노출하지 않는다.
  // 이건 «조회»가 아니라 사본을 만드는 파이프라인으로 들어가는 «쓰기» 진입점이었다
  // (선택 행 → POST /api/graph/sync → 머티리얼라이즈). 서버가 그 라우트를 410으로
  // 거절하므로 버튼을 두면 누를 때마다 실패 토스트만 뜬다 — 눌러도 되는 것처럼
  // 보이는 죽은 버튼은 화면이 사용자에게 하는 거짓말이다.
  // 마크업(index.html)의 기본값이 이미 `display: none`이라, 「보이게 만들지 않는 것」
  // 만으로 진입이 닫힌다. 버튼 마크업과 이 핸들러 몸통은 판정 ④의 코드 제거 라운드 몫.
  const GRAPH_SYNC_RETIRED = true;   // R-2026-08-14-H
  if (!GRAPH_SYNC_RETIRED && isAdmin && elements.graphSyncBtn) {
    elements.graphSyncBtn.style.display = 'inline-block';
    elements.graphSyncBtn.addEventListener('click', async () => {
      if (!state.gridApi) return;
      const selectedRows = state.gridApi.getSelectedRows();
      if (selectedRows.length === 0) {
        showToast("동기화할 행을 선택해주세요.", 'warning');
        return;
      }
      
      const rowIds = selectedRows.map(r => r.row_id);
      const confirmSync = confirm(`선택한 ${rowIds.length}개 행을 그래프 DB와 동기화하시겠습니까?`);
      if (!confirmSync) return;
      
      showToast("그래프 DB 동기화 요청 중...", 'info');
      try {
        const res = await fetch(`${API_BASE}/api/graph/sync`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            table_name: state.currentTable,
            row_ids: rowIds
          })
        });
        const data = await res.json();
        if (res.ok && data.status === 'success') {
          showToast(`동기화 완료! (모드: ${data.mode}, 성공: ${data.synced_count}건, 삭제: ${data.deleted_count || 0}건)`, 'success');
          await fetchData(false);
        } else {
          showToast(`동기화 실패: ${data.detail || '알 수 없는 오류'}`, 'error');
        }
      } catch (err) {
        console.error(err);
        showToast("네트워크 오류로 그래프 동기화에 실패했습니다.", 'error');
      }
    });
  }

  // Desktop -- 서버에 «구워져 있는» zip 을 그대로 내려받는다. 라우트는 구현자 몫이고
  // (`GET /api/desktop/download`), 그것이 서기 전까지 이 버튼은 404 를 받는다.
  //
  // 🔴 그래서 «먼저 물어보고» 이동한다. 바로 이동시키면 404 일 때 브라우저가 JSON 을
  //    띄우거나 아무 일도 안 일어난 것처럼 보인다 -- 이 프로젝트가 「없는 것을 조용히」로
  //    여러 번 헤맨 그 자리다.
  //
  // 🔴 묻는 방법은 HEAD 가 «아니다». 이 서버는 «있는» 라우트에도 HEAD 에 405 를 준다
  //    (실측 2026-08-25: `HEAD /tables` -> 405). HEAD 로 재면 405 도 404 도 똑같이
  //    `!ok` 라, 빌드가 «서는 날» 이 버튼이 「없습니다」라고 말하게 된다 -- 오늘은 맞고
  //    도달 가능해지는 날 틀리는 가드다. GET 으로 묻고 헤더가 오는 즉시 끊는다:
  //    fetch 는 헤더에서 resolve 하므로 236 MB 가 «흐르지 않는다».
  //
  // 🔴 크기를 «문구에 박지 않는다» (총괄 2026-08-25). 245 라 적어 두었더니 패키징이
  //    onefile exe -> zip 으로 바뀌면서 «세 가지가 동시에» 틀렸다 -- 확장자 · 크기 ·
  //    그리고 «쓰는 법»(받아서 바로 실행 -> 풀고 안의 실행 파일). 숫자는 서버의
  //    Content-Length 가 정본이므로 화면은 안 적는다.
  const desktopDownloadBtn = document.getElementById('desktop-download-btn');
  if (desktopDownloadBtn) {
    desktopDownloadBtn.addEventListener('click', async () => {
      const url = `${API_BASE}/api/desktop/download`;
      const probe = new AbortController();
      try {
        const res = await fetch(url, { signal: probe.signal });
        probe.abort();
        if (!res.ok) {
          showToast('데스크톱 빌드가 없습니다 — 서버에 zip 이 아직 없습니다.', 'error');
          return;
        }
      } catch (err) {
        console.error(err);
        showToast('데스크톱 빌드를 확인하지 못했습니다 — 서버에 닿지 않습니다.', 'error');
        return;
      }
      window.location.href = url;
    });
  }

  // Global mouseup guard to release range drag selection state securely
  document.addEventListener('mouseup', () => {
    if (state.isDraggingRange) {
      state.isDraggingRange = false;
      if (state.gridApi) {
        commitDragSelection(state.gridApi);
        state.gridApi.refreshCells({ force: true });
      }
      state.dragStartCell = null;
      state.dragEndCell = null;
    }
  });

  if (elements.refreshHistoryBtn) {
    elements.refreshHistoryBtn.addEventListener('click', () => {
      loadHistory();
    });
  }

  if (elements.clearTxFilterBtn) {
    elements.clearTxFilterBtn.addEventListener('click', () => {
      setTransactionFilter(null);
    });
  }

  if (elements.prevPageBtn) {
    elements.prevPageBtn.addEventListener('click', () => {
      if (state.currentSkip >= pageLimit) {
        state.currentSkip -= pageLimit;
        state.allDataLoaded = false;
        fetchData(false);
      }
    });
  }
  if (elements.nextPageBtn) {
    elements.nextPageBtn.addEventListener('click', () => {
      state.currentSkip += pageLimit;
      state.allDataLoaded = false;
      fetchData(false);
    });
  }

  if (elements.pageInput) {
    const handlePageJump = () => {
      let targetPage = parseInt(elements.pageInput.value, 10);
      const totalPages = parseInt(elements.totalPagesSpan?.textContent || '1', 10);

      if (isNaN(targetPage) || targetPage < 1) {
        elements.pageInput.value = Math.floor(state.currentSkip / pageLimit) + 1;
        return;
      }

      if (targetPage > totalPages) {
        targetPage = totalPages;
      }

      const newSkip = (targetPage - 1) * pageLimit;
      if (newSkip !== state.currentSkip || state.allDataLoaded) {
        state.currentSkip = newSkip;
        state.allDataLoaded = false;
        fetchData(false);
      } else {
        elements.pageInput.value = targetPage;
      }
    };

    elements.pageInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        handlePageJump();
        elements.pageInput.blur();
      }
    });

    elements.pageInput.addEventListener('blur', () => {
      handlePageJump();
    });
  }

  elements.tableSelect.addEventListener('change', async (e) => {
    const table = e.target.value;
    if (table) {
      // V1 instrument: counted here, not inside switchTable(), because switchTable is
      // also called on boot auto-select and by navigateToLog — neither is a user move.
      countNav(ROUTES.GRID, 'grid:table');
      await switchTable(table);
      if (sourceLabel) sourceLabel.setRelation(table);
    }
  });

  // Debounced search
  let searchTimeout;
  if (elements.globalSearch) {
    elements.globalSearch.addEventListener('input', () => {
      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(() => {
        fetchData(true);
      }, 300);
    });
  }

  if (elements.searchCols) {
    elements.searchCols.addEventListener('change', () => {
      fetchData(true);
    });
  }

  // Dropdown Menus toggling logic (UI/UX Consolidation)
  if (elements.settingsMenuBtn && elements.settingsDropdown) {
    elements.settingsMenuBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      const isVisible = elements.settingsDropdown.style.display === 'flex';
      elements.settingsDropdown.style.display = isVisible ? 'none' : 'flex';
      // Close other dropdowns
      if (elements.navDropdown) elements.navDropdown.style.display = 'none';
      if (elements.columnSelectorDropdown) elements.columnSelectorDropdown.style.display = 'none';
    });
  }

  if (elements.navMenuBtn && elements.navDropdown) {
    elements.navMenuBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      const isVisible = elements.navDropdown.style.display === 'flex';
      elements.navDropdown.style.display = isVisible ? 'none' : 'flex';
      // Close other dropdowns
      if (elements.settingsDropdown) elements.settingsDropdown.style.display = 'none';
      if (elements.columnSelectorDropdown) elements.columnSelectorDropdown.style.display = 'none';
    });
  }

  // Click outside to close dropdowns
  document.addEventListener('click', () => {
    if (elements.settingsDropdown) elements.settingsDropdown.style.display = 'none';
    if (elements.navDropdown) elements.navDropdown.style.display = 'none';
  });

  // Stop propagation inside dropdown panels so clicking inputs doesn't close them
  if (elements.settingsDropdown) {
    elements.settingsDropdown.addEventListener('click', (e) => {
      e.stopPropagation();
    });
  }
  if (elements.navDropdown) {
    elements.navDropdown.addEventListener('click', (e) => {
      e.stopPropagation();
    });
  }

  // History Tabs
  elements.tabGlobalBtn.addEventListener('click', () => {
    hideReferenceView();
    // The reference tab is in this set too. Every switch here names its siblings one
    // by one, and the fourth tab was added to the row without being added to the
    // lists — harmless while it was hidden by default, two highlighted tabs now that
    // a rule-bearing table selects it.
    elements.tabGlobalBtn.classList.add('active');
    elements.tabCellBtn?.classList.remove('active');
    elements.tabRowBtn.classList.remove('active');
    elements.tabReferenceBtn?.classList.remove('active');
    state.activeHistoryTab = 'global';
    loadHistory();
  });

  // The Cell History tab is off the row (owner, 2026-08-21: it has no function). The
  // listener is GUARDED rather than deleted: `activeHistoryTab === 'cell'` is still read in
  // five places in timeline.js, so removing the branch is a different change from taking the
  // tab off the screen, and doing both at once would make the second one hard to undo.
  elements.tabCellBtn?.addEventListener('click', () => {
    hideReferenceView();
    elements.tabCellBtn.classList.add('active');
    elements.tabGlobalBtn.classList.remove('active');
    elements.tabRowBtn.classList.remove('active');
    elements.tabReferenceBtn?.classList.remove('active');
    state.activeHistoryTab = 'cell';
    loadHistory();
  });

  elements.tabRowBtn.addEventListener('click', () => {
    hideReferenceView();
    elements.tabRowBtn.classList.add('active');
    elements.tabGlobalBtn.classList.remove('active');
    elements.tabCellBtn?.classList.remove('active');
    elements.tabReferenceBtn?.classList.remove('active');
    state.activeHistoryTab = 'row';
    loadHistory();
  });

  if (elements.tabReferenceBtn) {
    elements.tabReferenceBtn.addEventListener('click', () => showReferenceView());
  }

  // Transaction Mode listeners
  if (elements.txModeToggle) {
    elements.txModeToggle.addEventListener('change', () => {
      state.txModeActive = elements.txModeToggle.checked;
      if (!state.txModeActive) {
        const pendingCount = Object.keys(state.pendingTxEdits).length;
        if (pendingCount > 0) {
          const confirmApply = confirm(`대기 중인 수정사항이 ${pendingCount}건 있습니다. 적용하시겠습니까?\n\n'확인'을 누르면 수정 사항을 일괄 적용하고,\n'취소'를 누르면 수정 사항을 모두 취소(Discard)합니다.`);
          if (confirmApply) {
            applyPendingTxEdits();
          } else {
            discardPendingTxEdits();
          }
        } else {
          updateTxModeUI();
          state.gridApi.refreshCells({ force: true });
        }
      } else {
        updateTxModeUI();
        state.gridApi.refreshCells({ force: true });
      }
    });
  }

  if (elements.txApplyBtn) {
    elements.txApplyBtn.addEventListener('click', () => {
      applyPendingTxEdits();
    });
  }

  if (elements.txDiscardBtn) {
    elements.txDiscardBtn.addEventListener('click', () => {
      discardPendingTxEdits();
    });
  }

  // Prevent accidental page leave with unsaved edits
  window.addEventListener('beforeunload', (e) => {
    if (Object.keys(state.pendingTxEdits).length > 0) {
      e.preventDefault();
      e.returnValue = '저장되지 않은 수정사항이 있습니다. 페이지를 벗어나시겠습니까?';
      return e.returnValue;
    }
  });

  // Refresh Grid
  if (elements.refreshGridBtn) {
    elements.refreshGridBtn.addEventListener('click', () => {
      if (!state.currentTable) return;
      elements.performanceLog.textContent = 'Refreshing current page...';
      state.pageCache.clear();
      if (state.viewMode === 'infinite' || state.allDataLoaded) {
        state.allDataLoaded = false;
        state.hasMoreData = true;
        fetchData(true);
      } else {
        fetchData(false);
      }
      showToast('🔄 화면이 최신 데이터로 새로고침되었습니다.', 'success');
    });
  }

  // Add Empty Row
  elements.addRowBtn.addEventListener('click', async () => {
    if (!state.currentTable) return;

    const countStr = prompt('Enter the number of empty rows to add:', '1');
    if (countStr === null) return; // Cancelled

    const count = parseInt(countStr.trim(), 10);
    if (isNaN(count) || count < 1) {
      alert('Please enter a valid number greater than or equal to 1.');
      return;
    }

    await addRows(count);
  });

  // Delete Selected Rows Button
  elements.deleteRowBtn.addEventListener('click', () => {
    deleteSelectedRows();
  });


  // Keyboard shortcuts inside the grid
  document.addEventListener('keydown', (e) => {
    const activeEl = document.activeElement;
    const isTextField = !!activeEl && (
      activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA' ||
      activeEl.hasAttribute('contenteditable') || activeEl.classList.contains('ag-input-field-input')
    );

    // Smart paste: Ctrl+Shift+V.
    //   * Ctrl+V is already the grid's cell-range paste (clipboard.js), so smart paste needs
    //     its own modifier; Ctrl+Shift+V is "paste special" in every spreadsheet an operator
    //     here has used, and nothing in this client binds it.
    //   * It is deliberately NOT scoped to #myGrid the way Delete/Ctrl+A are. After closing
    //     the context menu focus sits on <body>, and a shortcut that quietly does nothing
    //     there would reproduce the very complaint this fixes.
    //   * NOTHING is preventDefault()ed. The browser's own paste command is what produces the
    //     `paste` event carrying `e.clipboardData` - the only readable clipboard on plain
    //     HTTP. Swallowing the keydown would swallow the read.
    if (!isTextField && e.shiftKey && (e.ctrlKey || e.metaKey) && (e.key === 'v' || e.key === 'V')) {
      armSmartPaste(SMART_PASTE_KEY_TTL_MS);
      elements.performanceLog.textContent = `📋 Smart paste (${SMART_PASTE_KEY_LABEL}): waiting for the paste event`;
      // Whether a browser turns Ctrl+Shift+V into a paste command is the browser's business,
      // not ours, and it differs between Chrome, Edge and Firefox. So do not BET on it: if no
      // paste event lands, hold the latch open and name the chord that is guaranteed to
      // produce one. One keystroke when the shortcut works, two when it does not, and never
      // the silent nothing that sent this bug to support in the first place.
      clearTimeout(smartPasteEscalationTimer);
      smartPasteEscalationTimer = setTimeout(() => {
        if (state.smartPasteArmedUntil === 0) return; // already consumed - the chord worked
        armSmartPaste(SMART_PASTE_ARM_TTL_MS);
        showToast(
          `스마트 붙여넣기 대기 중 — 이어서 ${SMART_PASTE_FALLBACK_KEY_LABEL} 를 눌러 주세요. (취소: Esc)`,
          'info',
          { ttl: SMART_PASTE_ARM_TTL_MS, dedupeKey: SMART_PASTE_ARM_TOAST_KEY }
        );
      }, SMART_PASTE_ESCALATE_MS);
      return;
    }

    // Escape retracts an armed paste, so the promise made by the toast stays true.
    if (e.key === 'Escape' && state.smartPasteArmedUntil > Date.now()) {
      cancelSmartPasteArm('Smart paste cancelled');
    }

    if (activeEl && activeEl.closest('#myGrid')) {
      const isEditing = activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA' || activeEl.hasAttribute('contenteditable') || activeEl.classList.contains('ag-input-field-input');

      if (!isEditing) {
        // Delete key inside the grid to clear selected cells
        if (e.key === 'Delete') {
          e.preventDefault();
          clearSelectedCells();
        }
        // NOTE: Ctrl+C is intentionally NOT intercepted here. The native copy
        // event is handled by the `copy` listener in clipboard.js, which uses
        // e.clipboardData and therefore works in non-secure (plain HTTP)
        // contexts where navigator.clipboard is undefined.
        // Ctrl+A / Cmd+A inside the grid to select all cells
        else if ((e.ctrlKey || e.metaKey) && (e.key === 'a' || e.key === 'A')) {
          e.preventDefault();
          if (state.gridApi) {
            const allCols = state.gridApi.getColumns().map(c => c.getColId()).filter(c => c !== '#');
            const totalRows = state.gridApi.getDisplayedRowCount();
            if (allCols.length > 0 && totalRows > 0) {
              state.dragStartCell = { rowIndex: 0, colId: allCols[0] };
              state.dragEndCell = { rowIndex: totalRows - 1, colId: allCols[allCols.length - 1] };

              state.gridApi.refreshCells({ force: true });
              elements.performanceLog.textContent = '📋 All cells selected';
            }
          }
        }
      }
    }
  });

  // Ingest File Button (Trigger file selector)
  if (elements.ingestFileBtn) {
    elements.ingestFileBtn.addEventListener('click', () => {
      elements.toolbarFileInput.click();
    });
  }

  // 🔴 하나의 처리기를 «두 입력»이 나눠 씁니다. 폴더 업로드는 파이프라인이 아니라 입력이
  //    하나 는 것이라, 이 루프를 두 번째로 그리면 그날부터 둘이 갈라집니다 (소유자 상설:
  //    「근원 템플릿 요소 개발 후 데이터 갈아끼우기」). 폴더 input 은 `webkitdirectory` 때문에
  //    «하위 폴더까지» 훑어 `files` 에 담아 주므로, 이 루프가 보는 것은 여전히 파일 목록입니다.
  const ingestSelectedFiles = async (e) => {
    if (!state.currentTable) return;
    const files = e.target.files;
    if (files.length === 0) return;

    elements.performanceLog.textContent = `Uploading ${files.length} log file(s)...`;

    // 🔴 토스트는 루프 «밖»에서 «한 번». 파일마다 띄우면 폴더 하나에 100개가 뜹니다 --
    //    파일 몇 개를 고르던 시절엔 견딜 만했고, 「폴더」라는 입력이 생긴 순간 넘었습니다.
    //    진행 표시는 아래 `performanceLog` 가 «덮어쓰며» 이미 하고 있습니다 (새 UI 없음).
    let done = 0;
    let failed = 0;

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      elements.performanceLog.textContent = `Uploading file [${file.name}] (${(file.size / 1024).toFixed(1)} KB)...`;

      const formData = new FormData();
      formData.append('file', file);

      // 🔴 폴더 이름을 «같이» 보냅니다. `webkitdirectory` 가 이미 채워 주는 값이고
      //    (「WF-001/WORK_20260817_031405/voids.json」), 파일 하나를 고른 경우엔 «빈 문자열»이라
      //    요청이 예전과 «바이트 동일»합니다.
      //    이게 없으면 서버가 성분을 접어 leaf 만 남기고, `voids_json` 처럼 웨이퍼 식별자를
      //    «폴더 이름»에서 읽는 파서는 그 파일을 «거절»합니다 -- 같은 트리인데 문에 따라 답이
      //    달랐던 자리입니다 (실측 2026-08-27).
      const relativePath = file.webkitRelativePath || '';

      try {
        const res = await fetch(`${API_BASE}/tables/${state.currentTable}/upload`
          + `?user=${encodeURIComponent(CURRENT_USER)}`
          + `&relative_path=${encodeURIComponent(relativePath)}`, {
          method: 'POST',
          body: formData
        });

        if (res.ok) {
          const resData = await res.json();
          const savedPath = resData.path || '';
          const savedFilename = savedPath.split(/[/\\]/).pop() || file.name;
          elements.performanceLog.textContent = `✅ Successfully ingested [${file.name}] (RAW: ${savedFilename}). Sync will refresh table shortly.`;
          done += 1;
        } else {
          throw new Error('Upload failed');
        }
      } catch (err) {
        console.error('File ingestion failed', err);
        elements.performanceLog.textContent = `❌ Ingestion failed for [${file.name}]`;
        failed += 1;
      }
    }

    // 🔴 성공은 «한 번», 실패는 «묶어서 한 번». 전부 실패하면 「0개 완료」를 안 띄웁니다 --
    //    0 을 성공으로 그리는 것이 이 화면이 없애려는 오독입니다.
    if (done) showToast(`📤 ${done}개 업로드 완료`, 'success');
    if (failed) showToast(`❌ ${files.length}개 중 ${failed}개 실패`, 'error');
    // 🔴 «불을 지른 input» 을 비웁니다. `toolbarFileInput` 을 고정으로 비우면 폴더 쪽은
    //    값이 남아 «같은 폴더를 두 번» 고를 때 change 가 안 옵니다.
    e.target.value = '';
  };
  elements.toolbarFileInput.addEventListener('change', ingestSelectedFiles);
  if (elements.toolbarFolderInput) {
    elements.toolbarFolderInput.addEventListener('change', ingestSelectedFiles);
  }
  if (elements.folderUploadBtn) {
    elements.folderUploadBtn.addEventListener('click', () => elements.toolbarFolderInput.click());
  }

  // Smart Paste Button
  if (elements.smartPasteBtn) {
    elements.smartPasteBtn.addEventListener('click', () => {
      smartPasteViaIngestion();
    });
  }

  // Sort Toggle
  elements.sortLatestToggle.addEventListener('change', () => {
    localStorage.setItem('sortLatest', elements.sortLatestToggle.checked);
    fetchData(true);
  });

  // Copy Header Toggle. TWO controls, ONE stored value: the mockup puts it at the foot of the
  // reference panel, and that panel is `display:none` on every table with no reference rule --
  // measured on `lot_event`: tab hidden, panel hidden, rect 0x0. The toggle decides the MAIN
  // grid's copy (`clipboard.js:256`, `:655`), so leaving only that copy would put a live
  // setting out of reach on most tables.
  //
  // No new storage key and no event bridge -- the mirror is the assignment below, because
  // both boxes are on THIS page and a stale checkbox is a second vocabulary for one value.
  copyHeaderToggles().forEach(toggle => {
    toggle.addEventListener('change', () => {
      localStorage.setItem('copyHeader', toggle.checked);
      copyHeaderToggles().forEach(other => { other.checked = toggle.checked; });
    });
  });

  // Context Menu Item: Sources Management
  document.getElementById('menu-sources').addEventListener('click', () => {
    elements.contextMenu.style.display = 'none';
    openSourcesModal();
  });

  // Context Menu Item: Delete selected rows
  document.getElementById('menu-delete').addEventListener('click', () => {
    elements.contextMenu.style.display = 'none';
    deleteSelectedRows();
  });

  // Context Menu Item: Smart paste via parser
  document.getElementById('menu-smart-paste').addEventListener('click', () => {
    elements.contextMenu.style.display = 'none';
    smartPasteViaIngestion();
  });

  // Close context menu on outside click
  document.addEventListener('click', (e) => {
    if (!e.target.closest('#custom-context-menu')) {
      elements.contextMenu.style.display = 'none';
    }
  });

  // Block browser default context menu on AG-Grid container to prevent overlap
  const gridContainer = document.getElementById('myGrid');
  if (gridContainer) {
    gridContainer.addEventListener('contextmenu', (e) => {
      e.preventDefault();
    });
    gridContainer.addEventListener('mouseleave', () => {
      if (state.isDraggingRange) {
        state.isDraggingRange = false;
        commitDragSelection(state.gridApi);
        if (state.gridApi) {
          state.gridApi.refreshCells({ force: true });
        }
      }
    });
  }

  // Sources Modal Close Button
  elements.modalCloseBtn.addEventListener('click', () => {
    elements.sourcesModal.style.display = 'none';
  });

  // Close modal on background click
  elements.sourcesModal.addEventListener('click', (e) => {
    if (e.target === elements.sourcesModal) {
      elements.sourcesModal.style.display = 'none';
    }
  });

  // ── 컬럼 토글 드롭다운 구현 ──
  if (elements.columnSelectorBtn) {
    elements.columnSelectorBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      // Hide settings dropdown when launching column selector dropdown
      if (elements.settingsDropdown) elements.settingsDropdown.style.display = 'none';

      const isVisible = elements.columnSelectorDropdown.style.display === 'block';
      if (isVisible) {
        elements.columnSelectorDropdown.style.display = 'none';
      } else {
        // 드롭다운 위치 조정 (Options 버튼 하단에 배치)
        const targetBtn = elements.settingsMenuBtn || elements.columnSelectorBtn;
        const rect = targetBtn.getBoundingClientRect();
        elements.columnSelectorDropdown.style.top = `${rect.bottom + window.scrollY + 6}px`;
        elements.columnSelectorDropdown.style.left = `${rect.left + window.scrollX}px`;
        elements.columnSelectorDropdown.style.display = 'block';

        // 현재 컬럼 가시성 상태에 맞춰 리스트 렌더링
        renderColumnSelectorList();
      }
    });
  }

  // 드롭다운 및 버튼 영역 외부 클릭 시 드롭다운 닫기
  document.addEventListener('click', (e) => {
    if (elements.columnSelectorDropdown && elements.columnSelectorDropdown.style.display === 'block') {
      if (!e.target.closest('#column-selector-dropdown') && !e.target.closest('#column-selector-btn')) {
        elements.columnSelectorDropdown.style.display = 'none';
      }
    }
  });

  // 컬럼 선택 드롭다운 내 체크박스 리스트 동적 렌더링 함수
  function renderColumnSelectorList() {
    if (!state.gridApi || !elements.columnListContainer) return;
    elements.columnListContainer.innerHTML = '';

    // AG-Grid의 모든 컬럼을 조회
    const columns = state.gridApi.getColumns() || [];
    
    columns.forEach(col => {
      const colId = col.getColId();
      // 번호 열('#')은 가시성 토글에서 제외
      if (colId === '#') return;

      const isVisible = col.isVisible();
      const headerName = col.getColDef().headerName || colId;

      const li = document.createElement('li');
      li.className = 'col-selector-item';

      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.className = 'col-selector-checkbox';
      checkbox.checked = isVisible;
      checkbox.id = `col-toggle-${colId}`;

      const label = document.createElement('label');
      label.className = 'col-selector-label';
      label.htmlFor = `col-toggle-${colId}`;
      label.textContent = headerName;

      // 항목 클릭 시 체크박스 토글 연동
      li.addEventListener('click', (evt) => {
        if (evt.target !== checkbox && evt.target !== label) {
          evt.stopPropagation();
          checkbox.checked = !checkbox.checked;
          state.gridApi.setColumnsVisible([colId], checkbox.checked);
        }
      });

      checkbox.addEventListener('change', () => {
        state.gridApi.setColumnsVisible([colId], checkbox.checked);
      });

      li.appendChild(checkbox);
      li.appendChild(label);
      elements.columnListContainer.appendChild(li);
    });
  }

  // 전체 선택 버튼
  if (elements.colSelectAllBtn) {
    elements.colSelectAllBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (!state.gridApi) return;
      const columns = state.gridApi.getColumns() || [];
      const colIds = columns.map(c => c.getColId()).filter(id => id !== '#');
      state.gridApi.setColumnsVisible(colIds, true);
      renderColumnSelectorList();
    });
  }

  // 전체 해제 버튼
  if (elements.colSelectNoneBtn) {
    elements.colSelectNoneBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (!state.gridApi) return;
      const columns = state.gridApi.getColumns() || [];
      const colIds = columns.map(c => c.getColId()).filter(id => id !== '#');
      state.gridApi.setColumnsVisible(colIds, false);
      renderColumnSelectorList();
    });
  }

  // View Mode Change Handler
  if (elements.viewModeSelect) {
    elements.viewModeSelect.addEventListener('change', (e) => {
      // V1 instrument: the working surface is rebuilt from skip 0 under a new paging model.
      countNav(ROUTES.GRID, 'grid:viewmode');
      state.viewMode = e.target.value;
      state.allDataLoaded = false;
      state.hasMoreData = true;
      updateViewModeUI();
      state.pageCache.clear();
      fetchData(true);
    });
  }

  // Load All Button Handler
  if (elements.loadAllBtn) {
    elements.loadAllBtn.addEventListener('click', async () => {
      if (!state.currentTable || state.isLoadingMore) return;

      state.isLoadingMore = true;
      elements.performanceLog.textContent = '⚡ 1/3. Initializing bulk request...';
      const startTime = performance.now();

      const q = elements.globalSearch ? elements.globalSearch.value.trim() : '';
      const cols = elements.searchCols ? elements.searchCols.value : '';
      const sortLatest = elements.sortLatestToggle.checked;
      const filterModel = state.gridApi ? state.gridApi.getFilterModel() : {};
      const filterStr = Object.keys(filterModel).length > 0 ? JSON.stringify(filterModel) : '';

      const baseApiUrl = `${API_BASE}/tables/${state.currentTable}/data`;
      let queryParams = `order_by=${sortLatest ? 'updated_at' : 'row_id'}&order_desc=${sortLatest}`;
      if (state.currentTransactionId) {
        queryParams += `&transaction_id=${state.currentTransactionId}`;
      }
      if (q) {
        queryParams += `&q=${encodeURIComponent(q)}`;
        if (cols) {
          queryParams += `&cols=${encodeURIComponent(cols)}`;
        }
      }
      if (filterStr) {
        queryParams += `&filters=${encodeURIComponent(filterStr)}`;
      }

      try {
        const chunkLimit = 3000; // 청크 단위로 분할 로드
        let accumulatedData = [];
        let totalRows = 0;
        let currentSkipOffset = 0;

        elements.performanceLog.textContent = '⚡ 1/3. Fetching initial row chunk...';

        // 1. 첫 번째 청크 요청하여 전체 개수(total)와 첫 데이터를 받아옴
        const firstUrl = `${baseApiUrl}?skip=${currentSkipOffset}&limit=${chunkLimit}&${queryParams}`;
        const firstRes = await fetch(firstUrl);
        if (!firstRes.ok) throw new Error(`HTTP error! status: ${firstRes.status}`);
        const firstResult = await firstRes.json();

        accumulatedData = firstResult.data || [];
        totalRows = firstResult.total || 0;
        currentSkipOffset += accumulatedData.length;

        // 실시간 진행률 업데이트
        if (totalRows > 0) {
          const percent = Math.min(100, Math.floor((accumulatedData.length / totalRows) * 100));
          elements.performanceLog.textContent = `⏳ 2/3. Fetching rows: ${percent}% (${accumulatedData.length} / ${totalRows})`;
        } else {
          elements.performanceLog.textContent = `⏳ 2/3. Fetching rows: 100% (0 / 0)`;
        }

        // 2. 전체 데이터 개수가 첫 번째 수집량보다 많다면 루프를 돌며 추가 청크 수집
        while (accumulatedData.length < totalRows && currentSkipOffset < totalRows) {
          // 브라우저 렌더링 프레임 양보하여 UI 갱신 보장
          await new Promise(resolve => setTimeout(resolve, 5));

          const nextUrl = `${baseApiUrl}?skip=${currentSkipOffset}&limit=${chunkLimit}&${queryParams}`;
          const nextRes = await fetch(nextUrl);
          if (!nextRes.ok) throw new Error(`HTTP error! status: ${nextRes.status}`);
          const nextResult = await nextRes.json();

          const nextChunk = nextResult.data || [];
          if (nextChunk.length === 0) {
            // 더 이상 가져올 데이터가 없음 (서버 데이터 변동 가능성 대비 탈출)
            break;
          }

          accumulatedData = accumulatedData.concat(nextChunk);
          currentSkipOffset += nextChunk.length;

          const percent = Math.min(100, Math.floor((accumulatedData.length / totalRows) * 100));
          elements.performanceLog.textContent = `⏳ 2/3. Fetching rows: ${percent}% (${accumulatedData.length} / ${totalRows})`;
        }

        const fetchEndTime = performance.now();
        const totalFetchTime = (fetchEndTime - startTime).toFixed(0);

        elements.performanceLog.textContent = '🎨 3/3. Initializing cells & drawing grid...';
        await new Promise(resolve => setTimeout(resolve, 20)); // UI 반영을 위해 양보

        const renderStartTime = performance.now();

        state.allDataLoaded = true;
        state.hasMoreData = false;

        // 그리드 데이터 로드
        state.gridApi.setGridOption('rowData', accumulatedData);
        updateGridSortState();

        updateLoadedCount(accumulatedData.length);
        elements.totalRowsCount.textContent = `Matches: ${totalRows}`;
        updateViewModeUI();

        const renderEndTime = performance.now();
        const renderTime = (renderEndTime - renderStartTime).toFixed(0);
        const totalTime = (renderEndTime - startTime).toFixed(0);

        elements.performanceLog.textContent = `✅ Loaded ${accumulatedData.length} rows (Fetch Chunks: ${totalFetchTime}ms, Render: ${renderTime}ms | Total: ${totalTime}ms)`;
        showToast(`📥 전체 ${accumulatedData.length}개 행 로드 완료!`, 'success');
        state.isLoadingMore = false;
      } catch (err) {
        console.error('Failed to load all rows sequentially', err);
        elements.performanceLog.textContent = '❌ Failed to load all rows';
        showToast('❌ 전체 데이터 로드 중 오류 발생', 'error');
        state.isLoadingMore = false;
      }
    });
  }


  // Load CSV Button Handler (Direct Download with Progress & Custom Filename / Native FileDialog)
  if (elements.loadCsvBtn) {
    elements.loadCsvBtn.addEventListener('click', async () => {
      if (!state.currentTable) return;

      // Determine default filename
      const now = new Date();
      const timestamp = now.getFullYear() +
        String(now.getMonth() + 1).padStart(2, '0') +
        String(now.getDate()).padStart(2, '0') + '_' +
        String(now.getHours()).padStart(2, '0') +
        String(now.getMinutes()).padStart(2, '0') +
        String(now.getSeconds()).padStart(2, '0');
      const defaultFilename = `${state.currentTable}_extract_${timestamp}.csv`;

      let fileHandle = null;
      let writableStream = null;
      let useFileSystemAccess = !state.isDesktop && (typeof window.showSaveFilePicker === 'function');

      if (useFileSystemAccess) {
        try {
          fileHandle = await window.showSaveFilePicker({
            suggestedName: defaultFilename,
            types: [{
              description: 'CSV Files (*.csv)',
              accept: {
                'text/csv': ['.csv']
              }
            }]
          });
        } catch (err) {
          // If user cancels the picker, abort the download completely
          if (err.name === 'AbortError') {
            console.log('[CSV Export] User cancelled file dialog picker.');
            return;
          }
          // For security or other errors in wrapping environment, fallback to standard prompt
          console.warn('[CSV Export] File System Access API failed, falling back to prompt:', err);
          useFileSystemAccess = false;
        }
      }

      let finalFilename = defaultFilename;
      if (!state.isDesktop && !useFileSystemAccess) {
        const filenameInput = prompt('저장할 CSV 파일명을 입력해주세요:', defaultFilename);
        if (filenameInput === null) return; // Cancelled by user

        finalFilename = filenameInput.trim();
        if (!finalFilename) {
          finalFilename = defaultFilename;
        }
        if (!finalFilename.toLowerCase().endsWith('.csv')) {
          finalFilename += '.csv';
        }
      }

      const q = elements.globalSearch ? elements.globalSearch.value.trim() : '';
      const cols = elements.searchCols ? elements.searchCols.value : '';
      const sortLatest = elements.sortLatestToggle.checked;
      const filterModel = state.gridApi ? state.gridApi.getFilterModel() : {};
      const filterStr = Object.keys(filterModel).length > 0 ? JSON.stringify(filterModel) : '';

      let url = `${API_BASE}/tables/${state.currentTable}/export?`;
      url += `order_by=${sortLatest ? 'updated_at' : 'row_id'}&order_desc=${sortLatest}`;
      if (state.currentTransactionId) {
        url += `&transaction_id=${state.currentTransactionId}`;
      }
      if (q) {
        url += `&q=${encodeURIComponent(q)}`;
        if (cols) {
          url += `&cols=${encodeURIComponent(cols)}`;
        }
      }
      if (filterStr) {
        url += `&filters=${encodeURIComponent(filterStr)}`;
      }

      elements.performanceLog.textContent = 'Connecting...';
      showToast('📄 CSV 다운로드를 시작합니다.', 'success');

      try {
        const response = await fetch(url);
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        const totalBytesHeader = response.headers.get('X-Estimated-Content-Length') || response.headers.get('Content-Length');
        const totalBytes = totalBytesHeader ? parseInt(totalBytesHeader, 10) : 0;

        const reader = response.body.getReader();
        let receivedBytes = 0;

        if (useFileSystemAccess && fileHandle) {
          writableStream = await fileHandle.createWritable();
        }

        const chunks = [];

        while (true) {
          const { done, value } = await reader.read();
          if (done) {
            break;
          }

          if (useFileSystemAccess && writableStream) {
            await writableStream.write(value);
          } else {
            chunks.push(value);
          }
          receivedBytes += value.length;

          if (totalBytes > 0) {
            let percent = Math.floor((receivedBytes / totalBytes) * 100);
            if (percent > 99) percent = 99;
            if (percent < 0) percent = 0;
            const kbReceived = (receivedBytes / 1024).toFixed(0);
            const kbTotal = (totalBytes / 1024).toFixed(0);
            elements.performanceLog.textContent = `Downloading: ${percent}% (${kbReceived}K / ${kbTotal}K)`;
          } else {
            const kbReceived = (receivedBytes / 1024).toFixed(0);
            elements.performanceLog.textContent = `Downloading: ${kbReceived}KB`;
          }
        }

        elements.performanceLog.textContent = 'Processing...';

        if (useFileSystemAccess && writableStream) {
          await writableStream.close();
          const savedName = fileHandle.name;
          elements.performanceLog.textContent = `CSV Saved: ${savedName}`;
          showToast(`📄 CSV 파일 저장 완료! (${savedName})`, 'success');
        } else {
          // Assemble chunks into a Blob
          const blob = new Blob(chunks, { type: 'text/csv;charset=utf-8;' });
          const blobUrl = URL.createObjectURL(blob);

          const link = document.createElement('a');
          link.href = blobUrl;
          link.download = finalFilename;
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
          URL.revokeObjectURL(blobUrl);

          elements.performanceLog.textContent = `CSV Downloaded: ${finalFilename}`;
          showToast(`📄 CSV 파일 다운로드 완료! (${finalFilename})`, 'success');
        }
      } catch (err) {
        console.error('Failed to download CSV', err);
        if (writableStream) {
          try { await writableStream.abort(); } catch (e) { }
        }
        elements.performanceLog.textContent = '❌ CSV Download Failed';
        showToast('❌ CSV 다운로드 중 오류 발생', 'error');
      }
    });
  }

  // Initialize Main Layout Split Panel Resizer Drag Logic
  const mainResizer = document.getElementById('main-split-resizer');
  const gridSection = document.querySelector('.grid-section');
  const historySidebar = document.querySelector('.history-sidebar');

  if (mainResizer && gridSection && historySidebar) {
    let isDragging = false;

    // The width the operator dragged to, restored on load.
    //
    // Without this the sidebar snaps back to its CSS width on every F5, so widening it to
    // read a reference grid is work that has to be redone each visit — and a control whose
    // result does not survive a refresh reads as a control that did not take.
    //
    // Clamped on the way back in, not just on the way out: the stored number was legal
    // against YESTERDAY's window, and a 900px sidebar restored into a 1000px window would
    // leave no grid. A missing or unparseable entry simply leaves the CSS width alone.
    const SIDEBAR_WIDTH_KEY = 'assy.sidebarWidth';
    const clampSidebarWidth = (width, containerWidth) =>
      Math.min(Math.max(width, 300), Math.max(300, containerWidth - 350));

    try {
      const stored = Number(localStorage.getItem(SIDEBAR_WIDTH_KEY));
      const mainLayout = document.querySelector('.main-layout');
      if (Number.isFinite(stored) && stored > 0 && mainLayout) {
        const width = clampSidebarWidth(stored, mainLayout.getBoundingClientRect().width);
        historySidebar.style.width = `${width}px`;
        historySidebar.style.flex = 'none';
      }
    } catch { /* storage disabled or full: the CSS width is a correct fallback */ }

    mainResizer.addEventListener('mousedown', (e) => {
      isDragging = true;
      document.body.classList.add('resizing-active');
      mainResizer.classList.add('dragging');
      e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
      if (!isDragging) return;

      const mainLayout = document.querySelector('.main-layout');
      if (mainLayout) {
        const containerRect = mainLayout.getBoundingClientRect();
        
        // 오른쪽 패널 너비 = 컨테이너 우측 X 좌표 - 마우스 X 좌표
        let sidebarWidth = containerRect.right - e.clientX;

        // 최소 300px, 최대 컨테이너 전체너비 - 350px 범위 제한
        const minWidth = 300;
        const maxWidth = containerRect.width - 350;

        if (sidebarWidth < minWidth) sidebarWidth = minWidth;
        if (sidebarWidth > maxWidth) sidebarWidth = maxWidth;

        historySidebar.style.width = `${sidebarWidth}px`;
        historySidebar.style.flex = 'none'; // flex-grow 간섭 방지

        // AG-Grid 컬럼 가로 크기 반응형 자동 피팅
        if (state.gridApi) {
          state.gridApi.sizeColumnsToFit();
        }
      }
    });

    document.addEventListener('mouseup', () => {
      if (isDragging) {
        isDragging = false;
        document.body.classList.remove('resizing-active');
        mainResizer.classList.remove('dragging');

        // Written on mouseup, not on every mousemove: a drag raises hundreds of moves and
        // only the resting place is a decision.
        try {
          const width = parseFloat(historySidebar.style.width);
          if (Number.isFinite(width) && width > 0) {
            localStorage.setItem(SIDEBAR_WIDTH_KEY, String(Math.round(width)));
          }
        } catch { /* storage refused the write; the drag itself still stands */ }

        if (state.gridApi) {
          state.gridApi.sizeColumnsToFit();
        }
      }
    });
  }
}



// Drag and Drop Log Ingestion
function setupDragAndDrop() {
  const dropOverlay = document.getElementById('drop-overlay');
  const dropTableName = document.getElementById('drop-table-name');

  if (!dropOverlay) return;

  let dragCounter = 0;

  window.addEventListener('dragenter', (e) => {
    e.preventDefault();
    if (!currentTable) return;

    // Only trigger for files
    if (e.dataTransfer.types.includes('Files')) {
      dragCounter++;
      dropTableName.textContent = currentTable;
      dropOverlay.style.display = 'flex';
      // Force layout calculation
      dropOverlay.offsetHeight;
      dropOverlay.classList.add('active');
    }
  });

  window.addEventListener('dragover', (e) => {
    e.preventDefault();
  });

  window.addEventListener('dragleave', (e) => {
    e.preventDefault();
    if (!currentTable) return;

    if (e.dataTransfer.types.includes('Files')) {
      dragCounter--;
      if (dragCounter === 0) {
        dropOverlay.classList.remove('active');
        setTimeout(() => {
          if (!dropOverlay.classList.contains('active')) {
            dropOverlay.style.display = 'none';
          }
        }, 300);
      }
    }
  });

  window.addEventListener('drop', async (e) => {
    e.preventDefault();
    dragCounter = 0;
    dropOverlay.classList.remove('active');
    dropOverlay.style.display = 'none';

    if (!currentTable) return;

    const files = e.dataTransfer.files;
    if (files.length === 0) return;

    elements.performanceLog.textContent = `Uploading ${files.length} log file(s)...`;

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      elements.performanceLog.textContent = `Uploading file [${file.name}] (${(file.size / 1024).toFixed(1)} KB)...`;

      const formData = new FormData();
      formData.append('file', file);

      try {
        const res = await fetch(`${API_BASE}/tables/${state.currentTable}/upload?user=${encodeURIComponent(CURRENT_USER)}`, {
          method: 'POST',
          body: formData
        });

        if (res.ok) {
          elements.performanceLog.textContent = `✅ Successfully ingested [${file.name}]. Sync will refresh table shortly.`;
        } else {
          throw new Error('Upload failed');
        }
      } catch (err) {
        console.error('File ingestion failed', err);
        elements.performanceLog.textContent = `❌ Ingestion failed for [${file.name}]`;
      }
    }
  });
}

// Feature 2: Open Cell Sources Dialog Modal
// Helper: get selected cells range or single focused cell
function getSelectedCells() {
  if (!state.gridApi) return [];
  const cells = [];
  const systemCols = ['created_at', 'updated_at', 'row_id', 'id', 'updated_by', '#', 'is_graph_synced', 'needs_graph_rollback', 'graph_synced_at'];

  if (state.dragStartCell && state.dragEndCell) {
    const startColIdx = state.visibleColIndexMap[state.dragStartCell.colId];
    const endColIdx = state.visibleColIndexMap[state.dragEndCell.colId];
    if (startColIdx !== undefined && endColIdx !== undefined) {
      const minColIdx = Math.min(startColIdx, endColIdx);
      const maxColIdx = Math.max(startColIdx, endColIdx);
      const minRowIdx = Math.min(state.dragStartCell.rowIndex, state.dragEndCell.rowIndex);
      const maxRowIdx = Math.max(state.dragStartCell.rowIndex, state.dragEndCell.rowIndex);

      const visibleColIds = Object.keys(state.visibleColIndexMap);
      for (let r = minRowIdx; r <= maxRowIdx; r++) {
        for (let cIdx = minColIdx; cIdx <= maxColIdx; cIdx++) {
          const colId = visibleColIds[cIdx];
          if (systemCols.includes(colId) || /^\d+$/.test(colId)) continue;

          const rowNode = state.gridApi.getDisplayedRowAtIndex(r);
          if (rowNode && rowNode.data) {
            const rowId = rowNode.data.row_id;
            cells.push({ rowId, colId, rowIndex: r });
          }
        }
      }
    }
  } else {
    // Focused cell fallback
    const focusedCell = state.gridApi.getFocusedCell();
    if (focusedCell) {
      const colId = focusedCell.column.getId();
      if (!systemCols.includes(colId) && !/^\d+$/.test(colId)) {
        const rowNode = state.gridApi.getDisplayedRowAtIndex(focusedCell.rowIndex);
        if (rowNode && rowNode.data) {
          cells.push({ rowId: rowNode.data.row_id, colId, rowIndex: focusedCell.rowIndex });
        }
      }
    } else if (state.selectedCell) {
      cells.push({ rowId: state.selectedCell.rowId, colId: state.selectedCell.colId, rowIndex: state.selectedCell.rowIndex });
    }
  }
  return cells;
}

// Feature 2: Open Cell Sources Dialog Modal
async function openSourcesModal() {
  const cells = getSelectedCells();
  if (cells.length === 0) return;

  if (cells.length > 1) {
    const cols = Array.from(new Set(cells.map(c => c.colId)));
    const rows = Array.from(new Set(cells.map(c => c.rowIndex)));
    elements.modalMetaInfo.innerHTML = `
      <div><strong>Selected Range:</strong> <span style="color:var(--color-secondary)">${cells.length} cells (${rows.length} rows × ${cols.length} cols)</span></div>
      <div><strong>Columns:</strong> <span style="color:var(--color-primary)">${cols.map(c => c.toUpperCase()).join(', ')}</span></div>
    `;
  } else {
    const { rowId, colId } = cells[0];
    elements.modalMetaInfo.innerHTML = `
      <div><strong>Row ID:</strong> <span style="color:var(--color-secondary)">${rowId}</span></div>
      <div><strong>Column:</strong> <span style="color:var(--color-primary)">${colId.toUpperCase()}</span></div>
    `;
  }
  elements.sourcesList.innerHTML = '<tr><td colspan="3" style="text-align:center">Loading sources...</td></tr>';
  elements.sourcesModal.style.display = 'flex';

  await refreshSourcesList();
}

// Fetch and render source details inside table
async function refreshSourcesList() {
  const cells = getSelectedCells();
  if (cells.length === 0) return;

  if (cells.length === 1) {
    const { rowId, colId } = cells[0];
    try {
      const res = await fetch(`${API_BASE}/tables/${state.currentTable}/${rowId}/${colId}/sources`);
      if (!res.ok) throw new Error('Failed to fetch sources');

      const data = await res.json();
      const sources = data.sources || {};
      const manualPriority = data.manual_priority_source;

      elements.sourcesList.innerHTML = '';
      const sourceNames = Object.keys(sources);

      if (sourceNames.length === 0) {
        elements.sourcesList.innerHTML = '<tr><td colspan="3" style="text-align:center;color:var(--text-dim)">No source data available.</td></tr>';
        return;
      }

      sourceNames.forEach(sourceName => {
        const sourceVal = sources[sourceName];
        const isPinned = manualPriority === sourceName;

        let displayVal = sourceVal;
        let titleAttr = '';
        if (sourceVal && typeof sourceVal === 'object') {
          displayVal = sourceVal.value !== undefined ? sourceVal.value : '';
          if (sourceVal.timestamp || sourceVal.updated_by) {
            const timeStr = sourceVal.timestamp ? new Date(sourceVal.timestamp).toLocaleString() : 'N/A';
            const userStr = sourceVal.updated_by || 'system';
            titleAttr = `title="Updated by ${userStr} at ${timeStr}"`;
          }
        }

        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${sourceName}</td>
          <td><code ${titleAttr}>${displayVal !== null ? displayVal : 'NULL'}</code></td>
          <td>
            <button class="action-btn pin-btn ${isPinned ? 'active' : ''}" title="Pin this value">${isPinned ? '📌 Pinned' : '📍 Pin'}</button>
            <button class="action-btn del-btn" title="Delete this source">🗑️ Delete</button>
          </td>
        `;

        // Bind Pin Action
        tr.querySelector('.pin-btn').addEventListener('click', async () => {
          const nextPriority = isPinned ? null : sourceName; // Toggle pin
          elements.performanceLog.textContent = 'Updating cell priority...';
          try {
            const pinRes = await fetch(`${API_BASE}/tables/${state.currentTable}/${rowId}/${colId}/priority`, {
              method: 'PUT',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                source_name: nextPriority,
                updated_by: CURRENT_USER
              })
            });

            if (pinRes.ok) {
              elements.performanceLog.textContent = 'Cell priority updated successfully';
              state.pageCache.clear();
              await fetchData(false);
              await refreshSourcesList();
            } else {
              throw new Error('Priority update failed');
            }
          } catch (err) {
            console.error(err);
            elements.performanceLog.textContent = '❌ Failed to pin source';
          }
        });

        // Bind Delete Action
        tr.querySelector('.del-btn').addEventListener('click', async () => {
          if (!confirm(`Are you sure you want to delete source [${sourceName}] data for this cell?`)) return;

          elements.performanceLog.textContent = 'Deleting cell source...';
          try {
            const delRes = await fetch(`${API_BASE}/tables/${state.currentTable}/${rowId}/${colId}/sources/${sourceName}`, {
              method: 'DELETE'
            });

            if (delRes.ok) {
              elements.performanceLog.textContent = 'Cell source deleted successfully';
              state.pageCache.clear();
              await fetchData(false);
              await refreshSourcesList();
            } else {
              throw new Error('Source deletion failed');
            }
          } catch (err) {
            console.error(err);
            elements.performanceLog.textContent = '❌ Failed to delete cell source';
          }
        });

        elements.sourcesList.appendChild(tr);
      });
    } catch (err) {
      console.error(err);
      elements.sourcesList.innerHTML = '<tr><td colspan="3" style="text-align:center;color:var(--color-danger)">Failed to load sources.</td></tr>';
    }
  } else {
    // Batch Mode
    try {
      const res = await fetch(`${API_BASE}/tables/${state.currentTable}/cells/sources/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          updates: cells.map(c => ({ row_id: c.rowId, column_name: c.colId }))
        })
      });
      if (!res.ok) throw new Error('Failed to query batch sources');

      const cellSourcesList = await res.json();

      const uniqueSources = new Set();
      const sourceValuesMap = {};
      const sourcePinnedCount = {};

      cellSourcesList.forEach(cellData => {
        const sources = cellData.sources || {};
        const manualPriority = cellData.manual_priority_source;

        Object.keys(sources).forEach(srcName => {
          uniqueSources.add(srcName);
          if (!sourceValuesMap[srcName]) {
            sourceValuesMap[srcName] = [];
          }
          let srcVal = sources[srcName];
          let valStr = srcVal;
          if (srcVal && typeof srcVal === 'object') {
            valStr = srcVal.value !== undefined ? srcVal.value : '';
          }
          sourceValuesMap[srcName].push(valStr);

          if (manualPriority === srcName) {
            sourcePinnedCount[srcName] = (sourcePinnedCount[srcName] || 0) + 1;
          }
        });
      });

      elements.sourcesList.innerHTML = '';
      const sourceNames = Array.from(uniqueSources);

      if (sourceNames.length === 0) {
        elements.sourcesList.innerHTML = '<tr><td colspan="3" style="text-align:center;color:var(--text-dim)">No source data available in selected cells.</td></tr>';
        return;
      }

      sourceNames.forEach(sourceName => {
        const values = sourceValuesMap[sourceName] || [];
        const pinnedCount = sourcePinnedCount[sourceName] || 0;
        const isPinnedAll = pinnedCount === cells.length;

        const uniqueVals = Array.from(new Set(values));
        let valText = '';
        if (uniqueVals.length === 0) {
          valText = 'N/A';
        } else if (uniqueVals.length === 1) {
          valText = String(uniqueVals[0]);
        } else {
          valText = `Multiple Values (${uniqueVals.length} types)`;
        }

        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${sourceName}</td>
          <td><code>${valText}</code></td>
          <td>
            <button class="action-btn pin-btn ${isPinnedAll ? 'active' : ''}" title="Pin this source for all selected cells">${isPinnedAll ? '📌 Pinned' : '📍 Pin'}</button>
            <button class="action-btn del-btn" title="Delete this source from all selected cells">🗑️ Delete</button>
          </td>
        `;

        // Bind batch Pin Action
        tr.querySelector('.pin-btn').addEventListener('click', async () => {
          const nextPriority = isPinnedAll ? null : sourceName;
          elements.performanceLog.textContent = `Batch updating cell priority to [${sourceName}]...`;
          try {
            const pinRes = await fetch(`${API_BASE}/tables/${state.currentTable}/cells/priority/batch`, {
              method: 'PUT',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                updates: cells.map(c => ({ row_id: c.rowId, column_name: c.colId })),
                source_name: nextPriority,
                updated_by: CURRENT_USER
              })
            });

            if (pinRes.ok) {
              elements.performanceLog.textContent = 'Batch cell priority updated successfully';
              state.pageCache.clear();
              await fetchData(false);
              await refreshSourcesList();
            } else {
              throw new Error('Batch priority update failed');
            }
          } catch (err) {
            console.error(err);
            elements.performanceLog.textContent = '❌ Failed to batch pin source';
          }
        });

        // Bind batch Delete Action
        tr.querySelector('.del-btn').addEventListener('click', async () => {
          if (!confirm(`Are you sure you want to delete source [${sourceName}] from all ${cells.length} selected cells?`)) return;

          elements.performanceLog.textContent = `Batch deleting source [${sourceName}]...`;
          try {
            const delRes = await fetch(`${API_BASE}/tables/${state.currentTable}/cells/sources/delete/batch`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                cells: cells.map(c => ({ row_id: c.rowId, column_name: c.colId })),
                source_name: sourceName
              })
            });

            if (delRes.ok) {
              elements.performanceLog.textContent = 'Batch cell sources deleted successfully';
              state.pageCache.clear();
              await fetchData(false);
              await refreshSourcesList();
            } else {
              throw new Error('Batch source deletion failed');
            }
          } catch (err) {
            console.error(err);
            elements.performanceLog.textContent = '❌ Failed to batch delete source';
          }
        });

        elements.sourcesList.appendChild(tr);
      });
    } catch (err) {
      console.error(err);
      elements.sourcesList.innerHTML = '<tr><td colspan="3" style="text-align:center;color:var(--color-danger)">Failed to query sources for selected cells.</td></tr>';
    }
  }
}



// ── Feature 2: Smart Paste (clipboard ➡️ ingestion parser) ─────────────────────────────
//
// `navigator.clipboard` is UNDEFINED in production. The intranet is plain HTTP, a NON-SECURE
// context, so the whole object is missing - not merely permission-gated. Reading the
// clipboard therefore has exactly ONE door: `e.clipboardData` on a native `paste` event. A
// button cannot open that door, because `document.execCommand('paste')` is blocked in web
// content. This is a browser constraint, not a design choice, and the flow below accepts it:
//
//   * Ctrl+Shift+V              - the direct route: it arms and the browser's own paste
//                                 command lands in the same breath, so it is one keystroke
//                                 WHEN the browser honours the chord. When it does not, the
//                                 arming holds and the user is told to press Ctrl+V.
//   * Button / context menu     - cannot read at all; they ARM the next paste and name the key.
//   * navigator.clipboard.read  - still PREFERRED where it genuinely exists (localhost dev is
//                                 a secure context) because a click can drive it.
//
// What is deliberately absent is the shape that caused the defect: a fallback for
// `navigator.clipboard` being absent that then calls `navigator.clipboard`. Every branch below
// is guarded on the exact method it is about to call.

const SMART_PASTE_KEY_LABEL = 'Ctrl+Shift+V';
const SMART_PASTE_FALLBACK_KEY_LABEL = 'Ctrl+V';
// The keystroke and the paste event it triggers are one user action; the latch only has to
// survive the browser's command dispatch.
const SMART_PASTE_KEY_TTL_MS = 1500;
// A click has to wait for the operator to read the toast and reach for the keyboard.
const SMART_PASTE_ARM_TTL_MS = 15000;
// Real paste-event latency after a keydown is single-digit milliseconds. If nothing has
// arrived by here, this browser did not translate the chord into a paste command at all.
const SMART_PASTE_ESCALATE_MS = 600;

let smartPasteEscalationTimer = null;

function armSmartPaste(ttlMs) {
  state.smartPasteArmedUntil = Date.now() + ttlMs;
  // Remember WHICH table was armed. The arming window is long enough for an operator to
  // change tables in between, and this path ingests a file - landing it in a table the user
  // was no longer looking at is a data error, not a UI annoyance.
  state.smartPasteArmedTable = state.currentTable;
}

// Every arming toast carries this key so it can be retracted the instant the arming ends.
const SMART_PASTE_ARM_TOAST_KEY = 'smart-paste-arm';

function cancelSmartPasteArm(logText) {
  state.smartPasteArmedUntil = 0;
  clearTimeout(smartPasteEscalationTimer);
  smartPasteEscalationTimer = null;
  dismissToasts(SMART_PASTE_ARM_TOAST_KEY);
  if (logText) elements.performanceLog.textContent = logText;
}

// Text-bearing formats only. An image or a file list has nothing for the parser to read, and
// naming WHICH formats were present is the difference between a user who can fix it himself
// and a support question.
function pickTextTypes(types) {
  return Array.from(types || []).filter(
    t => t.startsWith('text/') || t.includes('json') || t.includes('csv')
  );
}

function extForMime(mime) {
  if (mime === 'text/html') return 'html';
  if (mime === 'text/rtf') return 'rtf';
  if (mime === 'application/json' || mime === 'text/json') return 'json';
  if (mime === 'text/csv') return 'csv';
  return 'txt';
}

// The half that is identical for every reader: wrap the text as a file and hand it to the
// ingestion endpoint.
async function uploadSmartPastePayload(selectedText, selectedType) {
  if (!state.currentTable) {
    showToast('테이블이 선택되지 않아 스마트 붙여넣기를 보낼 수 없습니다.', 'error');
    return;
  }
  if (!selectedText || !selectedText.trim()) {
    elements.performanceLog.textContent = '📋 Smart paste: clipboard held no text';
    showToast('클립보드가 비어 있습니다. 복사한 뒤 다시 시도해 주세요.', 'error');
    return;
  }

  const fileExt = extForMime(selectedType);
  elements.performanceLog.textContent = `Uploading ${selectedType} clipboard data for parsing...`;

  const blob = new Blob([selectedText], { type: selectedType });
  const file = new File([blob], `web_smart_paste_${Date.now()}.${fileExt}`, { type: selectedType });

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch(`${API_BASE}/tables/${state.currentTable}/upload?user=${encodeURIComponent(CURRENT_USER)}`, {
      method: 'POST',
      body: formData
    });

    if (res.ok) {
      const resData = await res.json();
      const savedPath = resData.path || '';
      const savedFilename = savedPath.split(/[/\\]/).pop() || file.name;
      elements.performanceLog.textContent = '📋 Clipboard uploaded to parser. Automatic reload will trigger soon.';
      showToast(`스마트 붙여넣기 완료! (포맷: ${selectedType.split('/')[1].toUpperCase()}, 파일: ${savedFilename})`, 'success');
    } else {
      const detail = await res.text().catch(() => '');
      console.error('Smart paste upload rejected', res.status, detail);
      elements.performanceLog.textContent = `❌ Smart paste upload rejected (HTTP ${res.status})`;
      showToast(`서버가 스마트 붙여넣기를 거부했습니다 (HTTP ${res.status}).`, 'error');
    }
  } catch (err) {
    // A transport failure, not a clipboard failure - say so, or the user reads it as the
    // clipboard bug again.
    console.error('Smart paste upload failed', err);
    elements.performanceLog.textContent = '❌ Smart paste upload failed to reach the server';
    showToast('서버에 전송하지 못했습니다. 네트워크를 확인해 주세요.', 'error');
  }
}

// THE production reader. Runs inside the `paste` event dispatch, where `e.clipboardData` is
// the only clipboard that exists on plain HTTP.
async function smartPasteFromPasteEvent(e) {
  // The latch has just been spent, so retire the "press Ctrl+V" instruction and the pending
  // escalation with it. A prompt that outlives what it asked for reads as "it did nothing".
  clearTimeout(smartPasteEscalationTimer);
  smartPasteEscalationTimer = null;
  dismissToasts(SMART_PASTE_ARM_TOAST_KEY);

  if (state.smartPasteArmedTable !== state.currentTable) {
    elements.performanceLog.textContent = '❌ Smart paste: table changed after arming';
    showToast(
      `테이블이 [${state.smartPasteArmedTable}] → [${state.currentTable}] 로 바뀌어 취소했습니다. 다시 실행해 주세요.`,
      'error'
    );
    return;
  }

  const dt = e.clipboardData;
  if (!dt) {
    elements.performanceLog.textContent = '❌ Smart paste: paste event carried no clipboardData';
    showToast('붙여넣기 이벤트에 클립보드 데이터가 없습니다. 다시 시도해 주세요.', 'error');
    return;
  }

  const allTypes = Array.from(dt.types || []);
  const textTypes = pickTextTypes(allTypes);
  if (textTypes.length === 0) {
    elements.performanceLog.textContent = '❌ Smart paste: no text-bearing format on the clipboard';
    showToast(
      `클립보드에 텍스트 형식이 없습니다. (감지된 형식: ${allTypes.length ? allTypes.join(', ') : '없음'})`,
      'error'
    );
    return;
  }

  // ⚠️ Read EVERY candidate synchronously, before the first await. A paste event's
  // DataTransfer is only readable during dispatch; `getData()` after the handler yields
  // returns an empty string, which would silently turn the format modal into a data-loss bug.
  const byType = {};
  textTypes.forEach(t => { byType[t] = dt.getData(t); });

  let selectedType = textTypes[0];
  if (textTypes.length > 1) {
    const chosen = await showClipboardTypeModal(textTypes);
    if (!chosen) {
      elements.performanceLog.textContent = 'Smart paste cancelled';
      return;
    }
    selectedType = chosen;
  }

  await uploadSmartPastePayload(byType[selectedType], selectedType);
}

// Click entry point (toolbar button / context-menu item). Prefers the async Clipboard API
// where it is really there; otherwise it cannot read at all, and says so while arming the key.
async function smartPasteViaIngestion() {
  if (navigator.clipboard && typeof navigator.clipboard.read === 'function') {
    let items = null;
    try {
      items = await navigator.clipboard.read();
    } catch (err) {
      // Denied permission, unfocused document, or an empty clipboard. Do NOT retry through
      // `readText()` on this same object - it is the same permission and the same gate.
      console.warn('navigator.clipboard.read() refused', err);
      items = null;
    }

    const item = items && items.length > 0 ? items[0] : null;
    if (item) {
      const allTypes = Array.from(item.types || []);
      const textTypes = pickTextTypes(allTypes);
      if (textTypes.length === 0) {
        showToast(
          `클립보드에 텍스트 형식이 없습니다. (감지된 형식: ${allTypes.length ? allTypes.join(', ') : '없음'})`,
          'error'
        );
        return;
      }

      let selectedType = textTypes[0];
      if (textTypes.length > 1) {
        const chosen = await showClipboardTypeModal(textTypes);
        if (!chosen) {
          elements.performanceLog.textContent = 'Smart paste cancelled';
          return;
        }
        selectedType = chosen;
      }

      try {
        const blob = await item.getType(selectedType);
        await uploadSmartPastePayload(await blob.text(), selectedType);
      } catch (err) {
        console.error('Clipboard blob read failed', err);
        showToast(`클립보드의 ${selectedType} 형식을 읽지 못했습니다.`, 'error');
      }
      return;
    }

    // The API exists but would not give us anything. Fall through to the key route rather
    // than dialling the same object again.
    armSmartPaste(SMART_PASTE_ARM_TTL_MS);
    showToast(`브라우저가 클립보드 읽기를 거부했습니다. 이어서 ${SMART_PASTE_FALLBACK_KEY_LABEL} 를 눌러 주세요. (취소: Esc)`, 'info', { ttl: SMART_PASTE_ARM_TTL_MS, dedupeKey: SMART_PASTE_ARM_TOAST_KEY });
    elements.performanceLog.textContent = `📋 Smart paste armed - press ${SMART_PASTE_FALLBACK_KEY_LABEL}`;
    return;
  }

  if (navigator.clipboard && typeof navigator.clipboard.readText === 'function') {
    // A genuinely different capability (older browsers ship readText without read), guarded
    // on the exact method being called. Plain text only - that is all this API offers here.
    try {
      const text = await navigator.clipboard.readText();
      await uploadSmartPastePayload(text, 'text/plain');
    } catch (err) {
      console.warn('navigator.clipboard.readText() refused', err);
      armSmartPaste(SMART_PASTE_ARM_TTL_MS);
      showToast(`브라우저가 클립보드 읽기를 거부했습니다. 이어서 ${SMART_PASTE_FALLBACK_KEY_LABEL} 를 눌러 주세요. (취소: Esc)`, 'info', { ttl: SMART_PASTE_ARM_TTL_MS, dedupeKey: SMART_PASTE_ARM_TOAST_KEY });
    }
    return;
  }

  // Production lands here: plain HTTP = non-secure context = no `navigator.clipboard` at all.
  // Naming the cause and the key is the whole point - the user's bug report was
  // "무슨 read 막혔다고 작동안하네", which is as far as the old generic toast let them get.
  armSmartPaste(SMART_PASTE_ARM_TTL_MS);
  elements.performanceLog.textContent = `📋 Smart paste armed - press ${SMART_PASTE_FALLBACK_KEY_LABEL} (clipboard API unavailable on plain HTTP)`;
  showToast(
    `이 환경(평문 HTTP)에서는 버튼이 클립보드를 읽을 수 없습니다. 지금 ${SMART_PASTE_FALLBACK_KEY_LABEL} 를 눌러 주세요. (취소: Esc)`,
    'info',
    // The toast lives exactly as long as the latch: when the instruction disappears, the
    // arming really is gone. A prompt that outlives what it promises is its own defect.
    { ttl: SMART_PASTE_ARM_TTL_MS, dedupeKey: SMART_PASTE_ARM_TOAST_KEY }
  );
}

// Glassmorphism selection modal for clipboard data types
function showClipboardTypeModal(types) {
  return new Promise((resolve) => {
    // 1. Create overlay container
    const overlay = document.createElement('div');
    overlay.id = 'clipboard-type-modal-overlay';
    Object.assign(overlay.style, {
      position: 'fixed',
      top: '0',
      left: '0',
      width: '100vw',
      height: '100vh',
      backgroundColor: 'var(--scrim)',
      zIndex: '9999',
      display: 'flex',
      justifyContent: 'center',
      alignItems: 'center',
      opacity: '0',
      transition: 'opacity 0.2s cubic-bezier(0.4, 0, 0.2, 1)'
    });

    // 2. Map mime-types to user friendly labels & icons
    const typeConfigs = {
      'text/plain': { label: 'Plain Text (일반 텍스트)', icon: '📋', color: 'var(--accent)' },
      'text/html': { label: 'HTML Table (엑셀 표 서식 포함)', icon: '🌐', color: 'var(--success)' },
      'text/rtf': { label: 'Rich Text Format (RTF 서식)', icon: '📝', color: 'var(--warning)' },
      'text/csv': { label: 'Comma Separated (CSV)', icon: '📊', color: 'var(--info)' },
      'application/json': { label: 'JSON Data Object', icon: '⚙️', color: 'var(--accent-2)' }
    };

    // 3. Create modal container card
    const card = document.createElement('div');
    Object.assign(card.style, {
      background: 'var(--bg-surface)',
      border: '1px solid var(--border-strong)',
      borderRadius: '16px',
      padding: '28px',
      width: '420px',
      boxShadow: 'var(--shadow-pop)',
      display: 'flex',
      flexDirection: 'column',
      gap: '20px',
      transform: 'scale(0.92)',
      transition: 'transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1)'
    });

    // 4. Modal Header
    const header = document.createElement('div');
    header.innerHTML = `
      <h3 style="font-family: var(--font-sans); font-size: 1.35rem; font-weight: 600; color: var(--text); margin-bottom: 6px;">📋 Paste Clipboard Type</h3>
      <p style="font-family: var(--font-sans); font-size: 0.85rem; color: var(--text-muted); line-height: 1.45;">클립보드에 여러 포맷의 데이터가 감지되었습니다.<br>파싱을 위해 전송할 데이터 타입을 선택하세요.</p>
    `;
    card.appendChild(header);

    // 5. Buttons Container
    const btnContainer = document.createElement('div');
    Object.assign(btnContainer.style, {
      display: 'flex',
      flexDirection: 'column',
      gap: '10px'
    });

    types.forEach(type => {
      const cfg = typeConfigs[type] || { label: type, icon: '📄', color: 'var(--text)' };
      const btn = document.createElement('button');

      Object.assign(btn.style, {
        background: 'var(--bg-inset)',
        border: '1px solid var(--border)',
        borderRadius: '10px',
        padding: '12px 16px',
        color: 'var(--text)',
        fontFamily: 'var(--font-sans)',
        fontSize: '0.92rem',
        fontWeight: '500',
        textAlign: 'left',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        gap: '12px',
        transition: 'all 0.15s ease',
        outline: 'none'
      });

      btn.innerHTML = `
        <span style="font-size: 1.25rem; background: var(--bg-surface); padding: 4px; border-radius: 6px; display: flex; align-items: center; justify-content: center;">${cfg.icon}</span>
        <div style="display: flex; flex-direction: column;">
          <span style="color: ${cfg.color}; font-weight: 600;">${cfg.label.split(' (')[0]}</span>
          <span style="font-size: 0.72rem; color: var(--text-muted); margin-top: 1px;">${type}</span>
        </div>
      `;

      btn.addEventListener('mouseenter', () => {
        btn.style.background = 'var(--surface-hover)';
        btn.style.borderColor = cfg.color;
        btn.style.transform = 'translateX(4px)';
        btn.style.boxShadow = 'var(--shadow-card)';
      });
      btn.addEventListener('mouseleave', () => {
        btn.style.background = 'var(--bg-inset)';
        btn.style.borderColor = 'var(--border)';
        btn.style.transform = 'none';
        btn.style.boxShadow = 'none';
      });

      btn.addEventListener('click', () => {
        closeModal(type);
      });

      btnContainer.appendChild(btn);
    });

    card.appendChild(btnContainer);

    // 6. Cancel Button
    const cancelBtn = document.createElement('button');
    Object.assign(cancelBtn.style, {
      background: 'transparent',
      border: '1px solid var(--border)',
      borderRadius: '10px',
      padding: '10px',
      color: 'var(--text-muted)',
      fontFamily: 'var(--font-sans)',
      fontSize: '0.88rem',
      fontWeight: '500',
      cursor: 'pointer',
      transition: 'all 0.15s ease',
      outline: 'none'
    });
    cancelBtn.textContent = 'Cancel (취소)';
    cancelBtn.addEventListener('mouseenter', () => {
      cancelBtn.style.background = 'var(--danger-weak)';
      cancelBtn.style.color = 'var(--danger)';
      cancelBtn.style.borderColor = 'var(--danger)';
    });
    cancelBtn.addEventListener('mouseleave', () => {
      cancelBtn.style.background = 'transparent';
      cancelBtn.style.color = 'var(--text-muted)';
      cancelBtn.style.borderColor = 'var(--border)';
    });
    cancelBtn.addEventListener('click', () => {
      closeModal(null);
    });
    card.appendChild(cancelBtn);

    overlay.appendChild(card);
    document.body.appendChild(overlay);

    requestAnimationFrame(() => {
      overlay.style.opacity = '1';
      card.style.transform = 'scale(1)';
    });

    function closeModal(val) {
      overlay.style.opacity = '0';
      card.style.transform = 'scale(0.92)';
      setTimeout(() => {
        overlay.remove();
        resolve(val);
      }, 200);
    }
  });
}

// Global mouseup handling for drag range selection completion
document.addEventListener('mouseup', () => {
  if (state.isDraggingRange) {
    state.isDraggingRange = false;
    if (state.gridApi && state.dragStartCell && state.dragEndCell) {
      refreshRange(state.gridApi, state.dragStartCell, state.dragEndCell);
    }
  }
});

// Transaction Mode Helpers
async function applyPendingTxEdits() {
  const pendingCount = Object.keys(state.pendingTxEdits).length;
  if (pendingCount === 0) return;

  elements.performanceLog.textContent = 'Applying batch transaction updates...';
  const applyStartTime = performance.now();

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
      const saveTime = (performance.now() - applyStartTime).toFixed(1);

      // Update cell is_overwrite status locally on the latest nodes directly
      Object.values(state.pendingTxEdits).forEach(edit => {
        const { rowId, colId, newValue, data } = edit;
        const latestNode = state.gridApi.getRowNode(rowId);
        const latestData = latestNode ? latestNode.data : data;
        if (latestData) {
          ensureCellObject(latestData, colId);
          latestData.data[colId].value = newValue;
          latestData.data[colId].is_overwrite = true;
          latestData.updated_at = getLocalTimeString();
        }
      });

      state.pendingTxEdits = {};
      // V1 instrument: reset ONLY when the server confirms it recorded the effort. Two
      // gates, not one: a failed save keeps accumulating because retry effort is real human
      // effort, and a 200 that changed nothing (every staged edit already matched storage)
      // records no effort row — resetting there would delete the effort it cost.
      commitIfRecorded(result);
      state.txModeActive = elements.txModeToggle.checked;
      updateTxModeUI();
      updateGridSortState();
      state.gridApi.refreshCells({ force: true });

      elements.performanceLog.textContent = `Applied batch updates in ${saveTime}ms (${result.change_count} cells updated)`;
    } else {
      const errData = await res.json().catch(() => ({}));
      const errMsg = errData.detail || 'Save failed';
      throw new Error(errMsg);
    }
  } catch (err) {
    console.error('Batch apply failed', err);
    alert(`일괄 적용 실패: ${err.message}`);
    elements.performanceLog.textContent = '❌ Batch apply failed';
  }
}

function discardPendingTxEdits() {
  const pendingCount = Object.keys(state.pendingTxEdits).length;
  if (pendingCount === 0) return;

  Object.values(state.pendingTxEdits).forEach(edit => {
    const { rowId, colId, oldValue, oldIsOverwrite, data } = edit;
    const latestNode = state.gridApi.getRowNode(rowId);
    const latestData = latestNode ? latestNode.data : data;
    if (latestData) {
      ensureCellObject(latestData, colId);
      latestData.data[colId].value = oldValue;
      latestData.data[colId].is_overwrite = oldIsOverwrite;
    }
  });

  state.pendingTxEdits = {};
  state.txModeActive = elements.txModeToggle.checked;
  updateTxModeUI();
  updateGridSortState();
  state.gridApi.refreshCells({ force: true });
  elements.performanceLog.textContent = 'Pending updates discarded';
}

// Start Application.
// The `catch` NAMES the failure instead of leaving it as a bare unhandled rejection — it does
// not swallow it. Startup dying silently is how the missing WebSocket stayed invisible; the
// socket itself is now opened on the first line of `init()`, so reaching here still means the
// live channel is up.
init().catch(err => console.error('[init] startup aborted before completing', err));
console.log('AssyManager Client Bundle Loaded. Version Hash Buster: 019ee29f-b2fb-727e');

