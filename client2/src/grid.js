import { createGrid } from 'ag-grid-community';
import { pageLimit } from './config.js';
import { state, updateVisibleColIndexMap } from './state.js';
import { elements } from './dom.js';
import { handleCellEdit, fetchData } from './api.js';
import { loadHistory } from './timeline.js';
import {
  isCellInRange,
  refreshRange,
  refreshSelectedRangeDiff,
  commitDragSelection,
  clearRangeSelection
} from './clipboard.js';
import { applyValueToSelectedRange, updateSelectedCellUI } from './ui.js';

// Apply AG-Grid client-side sorting configuration based on Sort Latest toggle
export function updateGridSortState() {
  if (!state.gridApi) return;

  // Do not re-sort if Tx Mode is active to prevent staged rows from jumping
  if (state.txModeActive) {
    return;
  }

  // Do not re-sort if user is actively editing a cell to prevent the row from jumping away
  const editingCells = state.gridApi.getEditingCells();
  if (editingCells && editingCells.length > 0) {
    return;
  }

  const sortLatest = elements.sortLatestToggle.checked;
  state.gridApi.applyColumnState({
    state: [
      { colId: 'updated_at', sort: sortLatest ? 'desc' : null },
      { colId: 'row_id', sort: sortLatest ? null : 'asc' }
    ],
    defaultState: { sort: null }
  });
}

// Update Loaded count slice text
export function updateLoadedCount(forcedCount = null) {
  if (!state.gridApi) return;
  const displayedCount = state.gridApi.getDisplayedRowCount();

  if (state.viewMode === 'infinite') {
    elements.exposedRowsCount.textContent = `Loaded: 1 - ${displayedCount}`;
  } else {
    const forced = forcedCount !== null ? forcedCount : displayedCount;
    const startRow = forced === 0 ? 0 : state.currentSkip + 1;
    const endRow = state.currentSkip + forced;

    if (startRow === endRow) {
      if (startRow === 0) {
        elements.exposedRowsCount.textContent = `Loaded: 0`;
      } else {
        elements.exposedRowsCount.textContent = `Loaded: ${startRow}`;
      }
    } else {
      elements.exposedRowsCount.textContent = `Loaded: ${startRow} - ${endRow}`;
    }
  }
}

// Update View Mode UI controls visibility
export function updateViewModeUI() {
  const paginationControls = document.querySelector('.pagination-controls');
  if (paginationControls) {
    paginationControls.style.display = (state.viewMode === 'pagination') ? 'flex' : 'none';
  }
}

// Update Pagination controls state
export function updatePaginationUI(total) {
  const currentPage = Math.floor(state.currentSkip / pageLimit) + 1;
  const totalPages = Math.ceil(total / pageLimit) || 1;

  if (elements.pageInput) {
    elements.pageInput.value = currentPage;
    elements.pageInput.max = totalPages;
  }
  if (elements.totalPagesSpan) {
    elements.totalPagesSpan.textContent = totalPages;
  }
  if (elements.prevPageBtn) {
    elements.prevPageBtn.disabled = (currentPage === 1);
  }
  if (elements.nextPageBtn) {
    elements.nextPageBtn.disabled = (currentPage >= totalPages);
  }
}

// Ensure that the cell data structure exists as an object: { value, is_overwrite, sources, updated_by }
export function ensureCellObject(dataObj, colId) {
  if (!dataObj) return;
  if (!dataObj.data) dataObj.data = {};
  
  const cell = dataObj.data[colId];
  if (typeof cell !== 'object' || cell === null) {
    dataObj.data[colId] = {
      value: cell !== undefined ? cell : '',
      is_overwrite: false,
      is_collision_merge: false,
      sources: {},
      updated_by: 'system',
      priority_source: null
    };
  }
}

// Helper to build column definitions dynamically based on schema
export function buildColumnDefs() {
  const columnDefs = state.currentColumns.map((col, index) => {
    const isSystem = ['created_at', 'updated_at', 'row_id', 'id', 'updated_by'].includes(col);
    const colTypes = state.currentColumnTypes || {};
    const colType = colTypes[col] || 'string';

    // 헤더명에 비즈니스 키 / 조합 소스 컬럼 아이콘 표시
    let headerLabel = col.toUpperCase();
    if (col === state.currentBusinessKey) {
      headerLabel = `${headerLabel}🗝️`;
    } else if (state.currentCompositeKeySources.includes(col)) {
      headerLabel = `${headerLabel}*`;
    }

    const colDef = {
      headerName: headerLabel,
      headerTooltip: headerLabel,
      field: col,
      editable: !isSystem,
      sortable: true,
      filter: colType === 'number' ? 'agNumberColumnFilter' : 'agTextColumnFilter',
      resizable: true,
      checkboxSelection: index === 0,
      headerCheckboxSelection: index === 0,
      valueGetter: (params) => {
        if (col === 'row_id') return params.data.row_id;
        if (col === 'created_at') return params.data.created_at;
        if (col === 'updated_at') return params.data.updated_at;

        const cell = params.data.data?.[col];
        let val = '';
        if (cell && typeof cell === 'object') {
          val = cell.value !== undefined ? cell.value : '';
        } else {
          val = cell !== undefined ? cell : '';
        }

        if (colType === 'number' && val !== '' && val !== null && val !== undefined) {
          const parsed = Number(val);
          if (!isNaN(parsed)) {
            return parsed;
          }
        }
        return val;
      },
      valueSetter: (params) => {
        if (isSystem) return false;
        ensureCellObject(params.data, col);

        let finalVal = params.newValue;
        if (colType === 'number') {
          if (params.newValue === '' || params.newValue === null || params.newValue === undefined) {
            finalVal = null;
          } else {
            const parsed = Number(params.newValue);
            if (isNaN(parsed)) {
              alert(`컬럼 '${col}'의 값 '${params.newValue}'은(는) 올바른 숫자 형식이 아닙니다.`);
              return false;
            }
            finalVal = parsed;
          }
        }

        params.data.data[col].value = finalVal;
        if (!state.txModeActive) {
          params.data.data[col].is_overwrite = true;
          params.data.data[col].priority_source = 'user';
        }
        return true;
      },
      cellClassRules: {
        'cell-system-readonly': () => isSystem,
        'cell-dirty-tx': (params) => {
          if (isSystem) return false;
          if (!params.data) return false;
          const key = `${params.data.row_id}_${col}`;
          return state.pendingTxEdits.hasOwnProperty(key);
        },
        'cell-collision-merge': (params) => {
          if (isSystem) return false;
          if (!params.data) return false;
          const key = `${params.data.row_id}_${col}`;
          if (state.pendingTxEdits.hasOwnProperty(key)) return false;
          const cell = params.data.data?.[col];
          return cell?.priority_source === 'collision_merge';
        },
        'cell-overwrite': (params) => {
          if (isSystem) return false;
          if (!params.data) return false;
          const key = `${params.data.row_id}_${col}`;
          if (state.pendingTxEdits.hasOwnProperty(key)) return false;
          const cell = params.data.data?.[col];
          return cell?.priority_source === 'user';
        },
        'custom-range-selected': (params) => {
          return isCellInRange(params.node.rowIndex, col);
        }
      }
    };

    if (colType === 'number') {
      colDef.cellEditor = 'agNumberCellEditor';
    }

    if (isSystem) {
      colDef.cellClass = 'cell-system-readonly';
    }

    return colDef;
  });

  columnDefs.unshift({
    headerName: '#',
    headerTooltip: 'Row Number',
    valueGetter: (params) => {
      const skip = (state.viewMode === 'pagination' && !state.allDataLoaded) ? state.currentSkip : 0;
      return skip + params.node.rowIndex + 1;
    },
    width: 100,
    minWidth: 90,
    maxWidth: 150,
    pinned: 'left',
    suppressMovable: true,
    sortable: false,
    filter: false,
    resizable: false,
    editable: false,
    cellClass: 'cell-system-readonly'
  });

  return columnDefs;
}

// Render grid layout using AG-Grid Core
export function renderGrid(initialRows) {
  const columnDefs = buildColumnDefs();

  if (state.gridApi) {
    console.log('[Grid] Swapping grid options dynamically (columnDefs & rowData)...');
    state.gridApi.setGridOption('columnDefs', columnDefs);
    state.gridApi.setGridOption('rowData', initialRows);

    state.colIdToIndexMap = {};
    state.gridApi.getColumns().forEach((c, idx) => {
      state.colIdToIndexMap[c.getColId()] = idx;
    });

    updateVisibleColIndexMap();
    updateGridSortState();
    return;
  }

  const gridDiv = document.querySelector('#myGrid');

  const gridOptions = {
    theme: 'legacy',
    columnDefs: columnDefs,
    rowData: initialRows,
    enableBrowserTooltips: false,
    suppressColumnVirtualization: false,
    suppressRowHoverHighlight: true,
    suppressSortOnDataChange: true,
    getRowId: (params) => params.data?.row_id || params.data?.id,
    defaultColDef: {
      width: 150,
      minWidth: 100,
      floatingFilter: true,
      suppressKeyboardEvent: (params) => {
        const event = params.event;
        const key = event.key;

        if (params.editing && event.ctrlKey && key === 'Enter') {
          event.preventDefault();
          const editors = params.api.getCellEditorInstances();
          if (editors && editors.length > 0) {
            const editingValue = editors[0].getValue();
            params.api.stopEditing(true);
            applyValueToSelectedRange(editingValue);
          }
          return true;
        }

        if (!params.editing && (key === 'Delete' || key === 'Backspace')) {
          return true;
        }
        return false;
      }
    },
    rowSelection: 'multiple',
    onGridReady: (event) => {
      state.gridApi = event.api;
      updateVisibleColIndexMap();
    },
    onColumnMoved: () => {
      updateVisibleColIndexMap();
    },
    onColumnVisible: () => {
      updateVisibleColIndexMap();
    },
    onColumnPinned: () => {
      updateVisibleColIndexMap();
    },
    onColumnEverythingChanged: () => {
      updateVisibleColIndexMap();
    },
    onFilterChanged: () => {
      fetchData(true);
    },
    onCellFocused: (event) => {
      if (!event.column || event.rowIndex === null || event.rowIndex === undefined) return;
      const rowNode = event.api.getDisplayedRowAtIndex(event.rowIndex);
      if (!rowNode || !rowNode.data) return;

      const debugColId = event.column.getId();
      const debugRowId = rowNode.data.row_id;
      if (!['row_id', 'created_at', 'updated_at', '#'].includes(debugColId)) {
        const cellObj = rowNode.data.data?.[debugColId];
        console.log(`%c[Grid Debug] Clicked Cell Info`, 'color: #00f0ff; font-weight: bold; font-size: 1.1rem;');
        console.log(`- Row ID: ${debugRowId}`);
        console.log(`- Col ID: ${debugColId}`);
        console.log(`- Priority Source:`, cellObj?.priority_source);
        console.log(`- Is Overwrite:`, cellObj?.is_overwrite);
        console.log(`- Raw Value:`, cellObj?.value);
        console.log(`- Sources:`, cellObj?.sources);
        console.log(`- Full Cell Object:`, cellObj);
      }

      const colId = event.column.getId();
      const rowId = rowNode.data.row_id;

      let val = '';
      if (colId === 'row_id') val = rowNode.data.row_id;
      else if (colId === 'created_at') val = rowNode.data.created_at;
      else if (colId === 'updated_at') val = rowNode.data.updated_at;
      else {
        const cell = rowNode.data.data?.[colId];
        val = cell && typeof cell === 'object' ? (cell.value !== undefined ? cell.value : '') : (cell !== undefined ? cell : '');
      }

      state.selectedCell = { rowId, colId, value: val, rowIndex: event.rowIndex };
      updateSelectedCellUI();
      if (state.activeHistoryTab !== 'global') {
        loadHistory();
      }
    },
    onCellMouseDown: (event) => {
      if (event.event.button !== 0) return;
      if (event.column.getColId() === '#') return;

      const isShift = event.event.shiftKey;
      const isCtrl = event.event.ctrlKey || event.event.metaKey;
      const currRow = event.rowIndex;
      const currCol = event.column.getColId();

      const oldEnd = state.dragEndCell;

      if (isShift) {
        if (state.dragStartCell) {
          state.dragEndCell = { rowIndex: currRow, colId: currCol };
        } else {
          state.dragStartCell = { rowIndex: currRow, colId: currCol };
          state.dragEndCell = { rowIndex: currRow, colId: currCol };
        }
        state.isDraggingRange = false;
        refreshSelectedRangeDiff(event.api, state.dragStartCell, oldEnd, state.dragEndCell);
      } else {
        if (!isCtrl) {
          clearRangeSelection();
        }

        state.isDraggingRange = true;
        state.dragStartCell = { rowIndex: currRow, colId: currCol };
        state.dragEndCell = { rowIndex: currRow, colId: currCol };

        refreshRange(event.api, state.dragStartCell, state.dragEndCell);
      }
    },
    onCellMouseOver: (event) => {
      if (event.event && event.event.buttons !== undefined && event.event.buttons !== 1) {
        if (state.isDraggingRange) {
          state.isDraggingRange = false;
          commitDragSelection(event.api);
          event.api.refreshCells({ force: true });
        }
        return;
      }

      if (!state.isDraggingRange || !state.dragStartCell) return;
      if (event.column.getColId() === '#') return;

      const currRow = event.rowIndex;
      const currCol = event.column.getColId();

      if (state.dragEndCell.rowIndex !== currRow || state.dragEndCell.colId !== currCol) {
        const prevEnd = state.dragEndCell;
        state.dragEndCell = { rowIndex: currRow, colId: currCol };

        if (!state.dragRefreshPending) {
          state.dragRefreshPending = true;
          const api = event.api;
          requestAnimationFrame(() => {
            try {
              refreshSelectedRangeDiff(api, state.dragStartCell, prevEnd, state.dragEndCell);
            } catch (err) {
              api.refreshCells({ force: true });
            } finally {
              state.dragRefreshPending = false;
            }
          });
        }
      }
    },
    onCellMouseUp: (event) => {
      if (state.isDraggingRange) {
        state.isDraggingRange = false;
        
        const isCtrl = event.event.ctrlKey || event.event.metaKey;
        const isSingleClick = (state.dragStartCell.rowIndex === state.dragEndCell.rowIndex && state.dragStartCell.colId === state.dragEndCell.colId);
        
        if (isSingleClick && isCtrl) {
          const key = `${state.dragStartCell.rowIndex}_${state.dragStartCell.colId}`;
          if (state.selectedCellsMap[key]) {
            delete state.selectedCellsMap[key];
          } else {
            const rowNode = event.api.getDisplayedRowAtIndex(state.dragStartCell.rowIndex);
            const rowId = rowNode?.data?.row_id;
            state.selectedCellsMap[key] = { rowIndex: state.dragStartCell.rowIndex, colId: state.dragStartCell.colId, rowId };
          }
          state.dragStartCell = null;
          state.dragEndCell = null;
        } else {
          commitDragSelection(event.api);
        }

        const oldStart = state.dragStartCell;
        const oldEnd = state.dragEndCell;
        state.dragStartCell = null;
        state.dragEndCell = null;
        
        if (oldStart && oldEnd) {
          refreshRange(event.api, oldStart, oldEnd);
        }
        event.api.refreshCells({ force: true });
      }
    },
    onCellValueChanged: async (event) => {
      await handleCellEdit(event);
    },
    onCellContextMenu: (event) => {
      event.event.preventDefault();
      if (!event.node || !event.node.data) return;

      const colId = event.column.getId();
      const rowId = event.node.data.row_id;
      const val = event.value;
      const rowIndex = event.node.rowIndex;

      if (state.dragStartCell && state.dragEndCell && !isCellInRange(rowIndex, colId)) {
        clearRangeSelection();
      }

      state.selectedCell = { rowId, colId, value: val, rowIndex };
      updateSelectedCellUI();

      if (!state.dragStartCell || !state.dragEndCell) {
        event.node.setSelected(true, true);
      }

      const contextMenu = elements.contextMenu;
      if (contextMenu) {
        contextMenu.style.left = `${event.event.clientX}px`;
        contextMenu.style.top = `${event.event.clientY}px`;
        contextMenu.style.display = 'block';
      }
    },
    onBodyScroll: (event) => {
      if (state.viewMode !== 'infinite') return;
      if (state.isLoadingMore || !state.hasMoreData || state.allDataLoaded) return;

      const viewport = document.querySelector('.ag-body-viewport');
      if (viewport) {
        const threshold = 150;
        const nearBottom = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight < threshold;
        if (nearBottom) {
          state.currentSkip += pageLimit;
          fetchData(false);
        }
      }
    }
  };

  state.gridApi = createGrid(gridDiv, gridOptions);

  const originalApplyTx = state.gridApi.applyTransaction.bind(state.gridApi);
  state.gridApi.applyTransaction = (tx) => {
    console.log('[Debug applyTransaction] Called with tx:', tx);
    console.trace('[Debug applyTransaction] Call stack trace:');
    return originalApplyTx(tx);
  };

  state.colIdToIndexMap = {};
  state.gridApi.getColumns().forEach((c, idx) => {
    state.colIdToIndexMap[c.getColId()] = idx;
  });

  updateGridSortState();
}
