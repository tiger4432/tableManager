import { API_BASE, CURRENT_USER, pageLimit } from './config.js';
import { state } from './state.js';
import { elements } from './dom.js';
import { ensureCellObject, updateGridSortState } from './grid.js';
import { updateTxModeUI, updateSelectedCellUI, setupBeforeUnloadWarning } from './ui.js';
import { getLocalTimeString } from './utils.js';
// The ONE TSV reader/writer. Lifted out of this file (it used to be four lines inline in
// the paste handler) so the DOE panel can run the same code instead of growing a second
// one. A second clipboard implementation is how this project got a Ctrl+C that did nothing
// on the intranet, and it cost a day to find.
import { parseTsv, serializeTsv } from './tsv.js';
import { snapshot, commitIfRecorded } from './effort_meter.js';

export function isCellInRange(rowIndex, colId) {
  const key = `${rowIndex}_${colId}`;
  if (state.selectedCellsMap[key]) return true;

  if (!state.dragStartCell || !state.dragEndCell) return false;
  if (!state.gridApi) return false;

  const startColIdx = state.visibleColIndexMap[state.dragStartCell.colId];
  const endColIdx = state.visibleColIndexMap[state.dragEndCell.colId];
  const colIdx = state.visibleColIndexMap[colId];

  if (startColIdx === undefined || endColIdx === undefined || colIdx === undefined) return false;

  const minColIdx = Math.min(startColIdx, endColIdx);
  const maxColIdx = Math.max(startColIdx, endColIdx);
  const minRowIdx = Math.min(state.dragStartCell.rowIndex, state.dragEndCell.rowIndex);
  const maxRowIdx = Math.max(state.dragStartCell.rowIndex, state.dragEndCell.rowIndex);

  return rowIndex >= minRowIdx && rowIndex <= maxRowIdx && colIdx >= minColIdx && colIdx <= maxColIdx;
}

export function refreshRange(api, startCell, endCell) {
  if (!startCell || !endCell || !api) return;
  const startRow = startCell.rowIndex;
  const endRow = endCell.rowIndex;
  const minRow = Math.min(startRow, endRow);
  const maxRow = Math.max(startRow, endRow);

  const rowNodes = [];
  for (let r = minRow; r <= maxRow; r++) {
    const node = api.getDisplayedRowAtIndex(r);
    if (node) rowNodes.push(node);
  }

  const startColIdx = state.visibleColIndexMap[startCell.colId];
  const endColIdx = state.visibleColIndexMap[endCell.colId];
  if (startColIdx === undefined || endColIdx === undefined) return;

  const minColIdx = Math.min(startColIdx, endColIdx);
  const maxColIdx = Math.max(startColIdx, endColIdx);
  
  const visibleColIds = Object.keys(state.visibleColIndexMap);
  const columns = visibleColIds.slice(minColIdx, maxColIdx + 1)
    .map(colId => api.getColumn(colId))
    .filter(c => c !== null && c !== undefined);

  api.refreshCells({ rowNodes, columns, force: true });
}

export function refreshSelectedRangeDiff(api, startCell, prevEndCell, newEndCell) {
  if (!startCell || !newEndCell || !api) return;

  const startRow = startCell.rowIndex;
  const newEndRow = newEndCell.rowIndex;
  const prevEndRow = prevEndCell ? prevEndCell.rowIndex : newEndRow;

  const minRow = Math.min(startRow, prevEndRow, newEndRow);
  const maxRow = Math.max(startRow, prevEndRow, newEndRow);

  const rowNodes = [];
  for (let r = minRow; r <= maxRow; r++) {
    const node = api.getDisplayedRowAtIndex(r);
    if (node) rowNodes.push(node);
  }

  const startColIdx = state.visibleColIndexMap[startCell.colId];
  const newEndColIdx = state.visibleColIndexMap[newEndCell.colId];
  const prevEndColIdx = prevEndCell ? state.visibleColIndexMap[prevEndCell.colId] : newEndColIdx;

  if (startColIdx === undefined || newEndColIdx === undefined || prevEndColIdx === undefined) {
    return;
  }

  const minColIdx = Math.min(startColIdx, prevEndColIdx, newEndColIdx);
  const maxColIdx = Math.max(startColIdx, prevEndColIdx, newEndColIdx);

  const visibleColIds = Object.keys(state.visibleColIndexMap);
  const columns = visibleColIds.slice(minColIdx, maxColIdx + 1)
    .map(colId => api.getColumn(colId))
    .filter(c => c !== null && c !== undefined);

  api.refreshCells({ rowNodes, columns, force: true });
}

export function clearRangeSelection() {
  if (!state.gridApi) return;

  const rowIndexes = new Set();
  const colIds = new Set();

  if (state.dragStartCell && state.dragEndCell) {
    const minRow = Math.min(state.dragStartCell.rowIndex, state.dragEndCell.rowIndex);
    const maxRow = Math.max(state.dragStartCell.rowIndex, state.dragEndCell.rowIndex);
    for (let r = minRow; r <= maxRow; r++) rowIndexes.add(r);

    const visibleColIds = Object.keys(state.visibleColIndexMap).length > 0
      ? Object.keys(state.visibleColIndexMap)
      : (state.gridApi.getColumnState() || []).filter(c => !c.hide).map(c => c.colId);

    const startColIdx = state.visibleColIndexMap[state.dragStartCell.colId] !== undefined
      ? state.visibleColIndexMap[state.dragStartCell.colId]
      : visibleColIds.indexOf(state.dragStartCell.colId);

    const endColIdx = state.visibleColIndexMap[state.dragEndCell.colId] !== undefined
      ? state.visibleColIndexMap[state.dragEndCell.colId]
      : visibleColIds.indexOf(state.dragEndCell.colId);

    if (startColIdx !== -1 && startColIdx !== undefined && endColIdx !== -1 && endColIdx !== undefined) {
      const minCol = Math.min(startColIdx, endColIdx);
      const maxCol = Math.max(startColIdx, endColIdx);
      for (let c = minCol; c <= maxCol; c++) colIds.add(visibleColIds[c]);
    }
  }

  Object.values(state.selectedCellsMap).forEach(cell => {
    rowIndexes.add(cell.rowIndex);
    colIds.add(cell.colId);
  });

  state.dragStartCell = null;
  state.dragEndCell = null;
  state.isDraggingRange = false;
  state.selectedCellsMap = {};

  if (rowIndexes.size > 0 && colIds.size > 0) {
    const rowNodes = Array.from(rowIndexes)
      .map(r => state.gridApi.getDisplayedRowAtIndex(r))
      .filter(n => n !== null && n !== undefined);
    const columns = Array.from(colIds)
      .map(colId => state.gridApi.getColumn(colId))
      .filter(c => c !== null && c !== undefined);

    state.gridApi.refreshCells({ rowNodes, columns, force: true });
  }
}

export function commitDragSelection(api) {
  if (!state.dragStartCell || !state.dragEndCell || !api) return;

  const startColIdx = state.visibleColIndexMap[state.dragStartCell.colId];
  const endColIdx = state.visibleColIndexMap[state.dragEndCell.colId];

  if (startColIdx !== undefined && endColIdx !== undefined) {
    const minCol = Math.min(startColIdx, endColIdx);
    const maxCol = Math.max(startColIdx, endColIdx);
    const minRow = Math.min(state.dragStartCell.rowIndex, state.dragEndCell.rowIndex);
    const maxRow = Math.max(state.dragStartCell.rowIndex, state.dragEndCell.rowIndex);

    const visibleColIds = Object.keys(state.visibleColIndexMap);
    const targetCols = visibleColIds.filter((_, idx) => idx >= minCol && idx <= maxCol && _ !== '#');

    for (let r = minRow; r <= maxRow; r++) {
      const node = api.getDisplayedRowAtIndex(r);
      if (!node || !node.data) continue;
      const rowId = node.data.row_id;

      targetCols.forEach(colId => {
        const key = `${r}_${colId}`;
        state.selectedCellsMap[key] = { rowIndex: r, colId, rowId };
      });
    }
  }
}

export function getRangeSelectedTSV() {
  if (!state.gridApi) return '';

  let selectedCells = Object.values(state.selectedCellsMap);
  
  if (selectedCells.length === 0) {
    if (!state.dragStartCell || !state.dragEndCell) {
      // Fallback: If no custom selection map, get current focused cell
      const focusedCell = state.gridApi.getFocusedCell();
      if (focusedCell) {
        selectedCells.push({ rowIndex: focusedCell.rowIndex, colId: focusedCell.column.getId() });
      } else {
        return '';
      }
    } else if (selectedCells.length === 0) {
      if (state.dragStartCell && state.dragEndCell) {
        const visibleCols = (state.gridApi.getColumnState() || [])
          .filter(c => !c.hide)
          .map(c => c.colId);
        const startColIdx = visibleCols.indexOf(state.dragStartCell.colId);
        const endColIdx = visibleCols.indexOf(state.dragEndCell.colId);
        if (startColIdx !== -1 && endColIdx !== -1) {
          const minCol = Math.min(startColIdx, endColIdx);
          const maxCol = Math.max(startColIdx, endColIdx);
          const minRow = Math.min(state.dragStartCell.rowIndex, state.dragEndCell.rowIndex);
          const maxRow = Math.max(state.dragStartCell.rowIndex, state.dragEndCell.rowIndex);
          for (let r = minRow; r <= maxRow; r++) {
            for (let c = minCol; c <= maxCol; c++) {
              selectedCells.push({ rowIndex: r, colId: visibleCols[c] });
            }
          }
        } else {
          selectedCells.push({ rowIndex: state.dragStartCell.rowIndex, colId: state.dragStartCell.colId });
        }
      }
    }
  }

  const visibleCols = (state.gridApi.getColumnState() || [])
    .filter(c => !c.hide)
    .map(c => c.colId);
  
  let minRow = Infinity;
  let maxRow = -Infinity;
  let minColIdx = Infinity;
  let maxColIdx = -Infinity;

  selectedCells.forEach(cell => {
    const cIdx = visibleCols.indexOf(cell.colId);
    if (cIdx !== -1) {
      if (cell.rowIndex < minRow) minRow = cell.rowIndex;
      if (cell.rowIndex > maxRow) maxRow = cell.rowIndex;
      if (cIdx < minColIdx) minColIdx = cIdx;
      if (cIdx > maxColIdx) maxColIdx = cIdx;
    }
  });

  if (minRow === Infinity || minColIdx === Infinity) return '';

  const colsToCopy = visibleCols.filter((colId, idx) => {
    if (idx < minColIdx || idx > maxColIdx) return false;
    if (colId === '#' || /^\d+$/.test(colId)) return false;
    return state.currentColumns.includes(colId) || ['row_id', 'created_at', 'updated_at'].includes(colId);
  });
  if (colsToCopy.length === 0) return '';

  // A grid of raw strings; `serializeTsv` does the quoting at the end. Previously each
  // value had its tabs and newlines REPLACED with spaces here - silent data loss on copy,
  // and the reason a copied cell could never be pasted back to produce the same cell.
  const tsvMatrix = [];

  const includeHeaders = elements.copyHeaderToggle && elements.copyHeaderToggle.checked;
  if (includeHeaders) {
    tsvMatrix.push(colsToCopy.map(c => c.toUpperCase()));
  }

  for (let r = minRow; r <= maxRow; r++) {
    const rowNode = state.gridApi.getDisplayedRowAtIndex(r);
    if (!rowNode || !rowNode.data) continue;

    let rowVals = [];
    colsToCopy.forEach(col => {
      const key = `${r}_${col}`;
      if (!state.selectedCellsMap[key] && (!state.dragStartCell || !state.dragEndCell || !isCellInRange(r, col))) {
        rowVals.push('');
        return;
      }

      let val = '';
      if (col === 'row_id') val = rowNode.data.row_id;
      else if (col === 'created_at') val = rowNode.data.created_at;
      else if (col === 'updated_at') val = rowNode.data.updated_at;
      else {
        const cell = rowNode.data.data?.[col];
        if (cell && typeof cell === 'object') {
          val = cell.value !== undefined ? cell.value : '';
        } else {
          val = cell !== undefined ? cell : '';
        }
      }

      if (val === null || val === undefined) {
        val = '';
      }
      rowVals.push(String(val));
    });
    tsvMatrix.push(rowVals);
  }

  return serializeTsv(tsvMatrix);
}

// Smart paste (upload the clipboard to the parser) lives in main.js, but the only place the
// clipboard can actually be READ is the native `paste` event handled here. Rather than have
// clipboard.js import main.js - a cycle - main.js registers its handler through this hook.
let smartPasteHandler = null;

export function registerSmartPasteHandler(fn) {
  smartPasteHandler = fn;
}

export function setupClipboardHandlers() {
  // 1. Paste handler
  document.addEventListener('paste', async (e) => {
    const activeEl = document.activeElement;
    if (activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA' || activeEl.hasAttribute('contenteditable') || activeEl.classList.contains('ag-input-field-input'))) {
      return;
    }

    // Smart paste gets first refusal, BEFORE the gridApi guard: it uploads to the parser and
    // needs no target cells, so the normal range-paste preconditions do not apply to it.
    // The latch is consumed here whether or not the upload succeeds - one arming, one paste.
    if (smartPasteHandler && state.smartPasteArmedUntil > Date.now()) {
      state.smartPasteArmedUntil = 0;
      e.preventDefault();
      smartPasteHandler(e);
      return;
    }

    if (!state.gridApi) return;

    // Determine target cells from selection map or drag bounds
    let targetCells = Object.values(state.selectedCellsMap);
    const focusedCell = state.gridApi.getFocusedCell();

    if (targetCells.length === 0) {
      if (state.dragStartCell && state.dragEndCell) {
        // Fallback to drag bounds
        const visibleCols = (state.gridApi.getColumnState() || [])
          .filter(c => !c.hide)
          .map(c => c.colId);
        const startColIdx = visibleCols.indexOf(state.dragStartCell.colId);
        const endColIdx = visibleCols.indexOf(state.dragEndCell.colId);
        if (startColIdx !== -1 && endColIdx !== -1) {
          const minCol = Math.min(startColIdx, endColIdx);
          const maxCol = Math.max(startColIdx, endColIdx);
          const minRow = Math.min(state.dragStartCell.rowIndex, state.dragEndCell.rowIndex);
          const maxRow = Math.max(state.dragStartCell.rowIndex, state.dragEndCell.rowIndex);
          
          const targetCols = visibleCols.filter((_, idx) => idx >= minCol && idx <= maxCol && _ !== '#');
          for (let r = minRow; r <= maxRow; r++) {
            targetCols.forEach(colId => {
              targetCells.push({ rowIndex: r, colId });
            });
          }
        }
      } else if (focusedCell) {
        targetCells.push({ rowIndex: focusedCell.rowIndex, colId: focusedCell.column.getId() });
      }
    }

    if (targetCells.length === 0) return;

    e.preventDefault();
    const clipboardText = e.clipboardData.getData('text/plain');
    if (!clipboardText) return;

    // Parse TSV clipboard through the shared reader. `trimCells`/`dropBlankLines` keep this
    // handler's long-standing whitespace and blank-line treatment byte for byte; what
    // CHANGES is that a cell Excel quoted because it contains a newline is now one cell.
    // It used to become two grid rows, the second of them garbage ending in a stray quote.
    const parsedMatrix = parseTsv(clipboardText, { trimCells: true, dropBlankLines: true });
    if (parsedMatrix.length === 0) return;

    elements.performanceLog.textContent = 'Processing paste updates...';

    const batchUpdates = [];
    const updateMapByRow = {};
    const allCols = state.gridApi.getColumns().map(c => c.getColId());

    try {
      const isSingleVal = (parsedMatrix.length === 1 && parsedMatrix[0].length === 1);

      if (isSingleVal) {
        // 1x1 Single value clipboard ➡️ Fill all target cells
        const val = parsedMatrix[0][0];

        targetCells.forEach(cell => {
          const { rowIndex, colId } = cell;
          const isSystem = ['created_at', 'updated_at', 'row_id', 'id', 'updated_by', '#', 'is_graph_synced', 'needs_graph_rollback', 'graph_synced_at'].includes(colId);
          if (isSystem) return;

          const rowNode = state.gridApi.getDisplayedRowAtIndex(rowIndex);
          if (!rowNode || !rowNode.data) return;
          const rowId = rowNode.data.row_id;
          if (!rowId) return;

          if (!updateMapByRow[rowId]) {
            updateMapByRow[rowId] = { rowNode, updates: {} };
          }

          const colTypes = state.currentColumnTypes || {};
          const colType = colTypes[colId] || 'string';
          let castedVal = val;
          if (colType === 'number') {
            if (val === '' || val === null || val === undefined) {
              castedVal = null;
            } else {
              const parsedVal = Number(val);
              if (isNaN(parsedVal)) {
                alert(`컬럼 '${colId}'의 값 '${val}'은(는) 올바른 숫자 형식이 아닙니다.`);
                throw new Error(`Invalid number format`);
              }
              castedVal = parsedVal;
            }
          }
          updateMapByRow[rowId].updates[colId] = castedVal;
        });
      } else {
        // MxN Matrix clipboard ➡️ Standard offset paste starting from top-left anchor cell
        // Find visible columns in grid
        const visibleCols = (state.gridApi.getColumnState() || [])
          .filter(c => !c.hide)
          .map(c => c.colId);

        // Find anchor (top-left) cell
        let anchorRow = Infinity;
        let anchorColVisibleIdx = -1;
        let anchorColId = '';

        if (focusedCell) {
          anchorRow = focusedCell.rowIndex;
          anchorColId = focusedCell.column.getColId();
          anchorColVisibleIdx = visibleCols.indexOf(anchorColId);
        } else {
          targetCells.forEach(cell => {
            const idx = visibleCols.indexOf(cell.colId);
            if (cell.rowIndex < anchorRow) {
              anchorRow = cell.rowIndex;
            }
            if (idx !== -1 && (anchorColVisibleIdx === -1 || idx < anchorColVisibleIdx)) {
              anchorColVisibleIdx = idx;
              anchorColId = cell.colId;
            }
          });
        }

        // If anchor col not in visible list, fallback to first visible column (excluding index column '#')
        if (anchorColVisibleIdx === -1 && visibleCols.length > 0) {
          const firstNonHash = visibleCols.find(c => c !== '#');
          if (firstNonHash) {
            anchorColId = firstNonHash;
            anchorColVisibleIdx = visibleCols.indexOf(firstNonHash);
          }
        }

        if (anchorRow === Infinity || anchorColVisibleIdx === -1) return;

        parsedMatrix.forEach((rowValues, rOffset) => {
          const targetRowIndex = anchorRow + rOffset;
          const rowNode = state.gridApi.getDisplayedRowAtIndex(targetRowIndex);
          if (!rowNode || !rowNode.data) return;
          const rowId = rowNode.data.row_id;

          rowValues.forEach((val, cOffset) => {
            const targetColIndex = anchorColVisibleIdx + cOffset;
            if (targetColIndex >= visibleCols.length) return;

            const colId = visibleCols[targetColIndex];
            const isSystem = ['created_at', 'updated_at', 'row_id', 'id', 'updated_by', '#', 'is_graph_synced', 'needs_graph_rollback', 'graph_synced_at'].includes(colId);
            if (isSystem) return;

            if (!updateMapByRow[rowId]) {
              updateMapByRow[rowId] = { rowNode, updates: {} };
            }

            const colTypes = state.currentColumnTypes || {};
            const colType = colTypes[colId] || 'string';
            let castedVal = val;
            if (colType === 'number') {
              if (val === '' || val === null || val === undefined) {
                castedVal = null;
              } else {
                const parsedVal = Number(val);
                if (isNaN(parsedVal)) {
                  alert(`컬럼 '${colId}'의 값 '${val}'은(는) 올바른 숫자 형식이 아닙니다.`);
                  throw new Error(`Invalid number format`);
                }
                castedVal = parsedVal;
              }
            }
            updateMapByRow[rowId].updates[colId] = castedVal;
          });
        });
      }

      // Populate batchUpdates array
      Object.keys(updateMapByRow).forEach(rowId => {
        const item = updateMapByRow[rowId];
        if (Object.keys(item.updates).length > 0) {
          batchUpdates.push({
            row_id: rowId,
            updates: item.updates,
            source_name: 'user',
            updated_by: CURRENT_USER
          });

          // Stage edits in pendingTxEdits if Tx Mode is active, and update local grid row node data in-place
          const oldRowData = item.rowNode.data;
          if (state.txModeActive) {
            Object.keys(item.updates).forEach(col => {
              const key = `${rowId}_${col}`;
              if (!state.pendingTxEdits[key]) {
                const oldValue = oldRowData.data?.[col]?.value !== undefined ? oldRowData.data[col].value : '';
                const oldIsOverwrite = oldRowData.data?.[col]?.is_overwrite === true;
                state.pendingTxEdits[key] = {
                  rowId,
                  colId: col,
                  newValue: item.updates[col],
                  oldValue: oldValue,
                  oldIsOverwrite: oldIsOverwrite,
                  data: oldRowData
                };
              } else {
                state.pendingTxEdits[key].newValue = item.updates[col];
              }

              // Update in-place on latest row data
              const latestNode = state.gridApi.getRowNode(rowId);
              const latestData = latestNode ? latestNode.data : oldRowData;
              if (latestData) {
                ensureCellObject(latestData, col);
                latestData.data[col].value = item.updates[col];
              }
            });
          }
        }
      });

      if (state.txModeActive) {
        if (batchUpdates.length > 0) {
          updateTxModeUI();
          state.gridApi.refreshCells({ force: true });
          elements.performanceLog.textContent = `Staged clipboard paste: ${Object.keys(state.pendingTxEdits).length} total pending edits`;
        }
        return;
      }

      if (batchUpdates.length > 0) {
        const res = await fetch(`${API_BASE}/tables/${state.currentTable}/data/updates`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          // V1 instrument: `effort` is an optional field. Raw counts only.
          body: JSON.stringify({ updates: batchUpdates, effort: snapshot() })
        });

        if (res.ok) {
          state.pageCache.clear();
          const result = await res.json();
          // V1 instrument: reset ONLY when the server confirms it recorded the effort — a
          // paste whose values already match storage returns 200 and records nothing.
          commitIfRecorded(result);
          elements.performanceLog.textContent = `Pasted successfully: ${batchUpdates.length} rows updated`;

          // Fast-apply local data values by updating latest node data in-place
          batchUpdates.forEach(update => {
            const rowNode = state.gridApi.getRowNode(update.row_id);
            if (rowNode) {
              const latestData = rowNode.data;
              if (latestData) {
                Object.keys(update.updates).forEach(col => {
                  ensureCellObject(latestData, col);
                  latestData.data[col].value = update.updates[col];
                  latestData.data[col].is_overwrite = true;
                });
                latestData.updated_at = getLocalTimeString();
              }
            }
          });

          // Force sort update to push modified rows to the top
          updateGridSortState();
          state.gridApi.refreshCells({ force: true });

          // Sync selected cell UI if inside pasted range
          if (state.selectedCell) {
            const matchedUpdate = batchUpdates.find(u => u.row_id === state.selectedCell.rowId);
            if (matchedUpdate && matchedUpdate.updates[state.selectedCell.colId] !== undefined) {
              state.selectedCell.value = matchedUpdate.updates[state.selectedCell.colId];
              updateSelectedCellUI();
            }
          }
        } else {
          const errData = await res.json().catch(() => ({}));
          const errMsg = errData.detail || 'Paste batch update failed';
          throw new Error(errMsg);
        }
      }
    } catch (err) {
      console.error('Failed to paste updates', err);
      alert(`붙여넣기 저장 실패: ${err.message}`);
      elements.performanceLog.textContent = '❌ Smart paste failed to save';
    }
  });

  // 2. Copy handler
  document.addEventListener('copy', (e) => {
    if (!state.gridApi) return;

    const activeEl = document.activeElement;
    if (activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA' || activeEl.hasAttribute('contenteditable') || activeEl.classList.contains('ag-input-field-input'))) {
      return;
    }

    // 1순위: 커스텀 드래그 선택 범위가 존재할 경우 범위 복사 실행
    const rangeTsv = getRangeSelectedTSV();
    if (rangeTsv) {
      e.preventDefault();
      e.clipboardData.setData('text/plain', rangeTsv);
      elements.performanceLog.textContent = '📋 Range copied to clipboard';
      return;
    }

    // 2순위 (Fallback): 선택된 행 단위 복사 실행
    const selectedNodes = state.gridApi.getSelectedNodes();
    if (selectedNodes.length === 0) return;

    e.preventDefault();
    const columns = state.gridApi.getColumns().filter(c => c.isVisible()).map(c => c.getColId()).filter(c => {
      if (c === '#' || /^\d+$/.test(c)) return false;
      return state.currentColumns.includes(c) || ['row_id', 'created_at', 'updated_at'].includes(c);
    });

    // Headers copy setting check
    const includeHeaders = elements.copyHeaderToggle.checked;
    const lines = [];

    if (includeHeaders) {
      lines.push(columns.map(c => c.toUpperCase()));
    }

    selectedNodes.forEach(node => {
      if (!node.data) return;
      const rowCells = columns.map(col => {
        if (col === 'row_id') return node.data.row_id;
        if (col === 'created_at') return node.data.created_at;
        if (col === 'updated_at') return node.data.updated_at;

        const cell = node.data.data?.[col];
        if (cell && typeof cell === 'object') {
          return cell.value !== undefined ? cell.value : '';
        }
        return cell !== undefined ? cell : '';
      });
      lines.push(rowCells);
    });

    // `e.clipboardData`, never `navigator.clipboard`: production is plain-HTTP LAN, a
    // non-secure context, where the async Clipboard API is undefined.
    e.clipboardData.setData('text/plain', serializeTsv(lines));
    elements.performanceLog.textContent = `📋 Copied ${selectedNodes.length} rows to clipboard`;
  });
}

// Feature: Clear selected cells in range or single focused cell
export async function clearSelectedCells() {
  if (!state.gridApi || !state.currentTable) return;

  let cellsToClear = []; // Array of { rowIndex, colId }
  const selectedCells = Object.values(state.selectedCellsMap);

  if (selectedCells.length > 0) {
    cellsToClear = selectedCells;
  } else if (state.dragStartCell && state.dragEndCell) {
    const allCols = state.gridApi.getColumns().map(c => c.getColId());
    const startColIdx = allCols.indexOf(state.dragStartCell.colId);
    const endColIdx = allCols.indexOf(state.dragEndCell.colId);
    if (startColIdx !== -1 && endColIdx !== -1) {
      const minColIdx = Math.min(startColIdx, endColIdx);
      const maxColIdx = Math.max(startColIdx, endColIdx);
      const minRowIdx = Math.min(state.dragStartCell.rowIndex, state.dragEndCell.rowIndex);
      const maxRowIdx = Math.max(state.dragStartCell.rowIndex, state.dragEndCell.rowIndex);

      for (let r = minRowIdx; r <= maxRowIdx; r++) {
        for (let cIdx = minColIdx; cIdx <= maxColIdx; cIdx++) {
          cellsToClear.push({ rowIndex: r, colId: allCols[cIdx] });
        }
      }
    }
  } else {
    // Single focused cell
    const focusedCell = state.gridApi.getFocusedCell();
    if (focusedCell) {
      cellsToClear.push({ rowIndex: focusedCell.rowIndex, colId: focusedCell.column.getId() });
    }
  }

  if (cellsToClear.length === 0) return;

  const systemCols = ['created_at', 'updated_at', 'row_id', 'id', 'updated_by', '#', 'is_graph_synced', 'needs_graph_rollback', 'graph_synced_at'];
  const updateMapByRow = {};

  cellsToClear.forEach(cell => {
    // Skip system columns
    if (systemCols.includes(cell.colId) || /^\d+$/.test(cell.colId)) return;

    const rowNode = state.gridApi.getDisplayedRowAtIndex(cell.rowIndex);
    if (!rowNode || !rowNode.data) return;
    const rowId = rowNode.data.row_id;
    if (!rowId) return;

    if (!updateMapByRow[rowId]) {
      updateMapByRow[rowId] = {
        row_id: rowId,
        updates: {},
        rowNode: rowNode
      };
    }

    const colType = (state.currentColumnTypes || {})[cell.colId] || 'string';
    const clearValue = colType === 'number' ? null : '';
    updateMapByRow[rowId].updates[cell.colId] = clearValue;
  });

  const updatesArray = [];

  Object.keys(updateMapByRow).forEach(rowId => {
    const item = updateMapByRow[rowId];
    if (Object.keys(item.updates).length > 0) {
      if (state.txModeActive) {
        // Stage edits in pendingTxEdits
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

          // Update in-place on latest row data
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
      elements.performanceLog.textContent = `Staged cell clear: ${Object.keys(state.pendingTxEdits).length} total pending edits`;
    }
    return;
  }

  if (updatesArray.length === 0) return;

  elements.performanceLog.textContent = `Clearing ${updatesArray.reduce((acc, cur) => acc + Object.keys(cur.updates).length, 0)} cells...`;
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
      // V1 instrument: reset ONLY when the server confirms it recorded the effort — clearing
      // cells that are already empty returns 200 and records nothing.
      commitIfRecorded(result);
      const saveTime = (performance.now() - startTime).toFixed(1);
      elements.performanceLog.textContent = `Cleared cells in ${saveTime}ms (${result.change_count} cells updated)`;

      // Apply grid local updates on the latest nodes directly
      updatesArray.forEach(item => {
        const rowNode = state.gridApi.getRowNode(item.row_id);
        if (rowNode) {
          const latestData = rowNode.data;
          if (latestData) {
            if (!latestData.data) latestData.data = {};
            Object.keys(item.updates).forEach(colId => {
              if (!latestData.data[colId]) latestData.data[colId] = {};
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
    } else {
      const errData = await res.json().catch(() => ({}));
      const errMsg = errData.detail || 'Cell clearing failed';
      throw new Error(errMsg);
    }
  } catch (err) {
    console.error('Failed to clear cells', err);
    alert(`셀 내용 비우기 실패: ${err.message}`);
    elements.performanceLog.textContent = '❌ Cell clearing failed';
  }
}
