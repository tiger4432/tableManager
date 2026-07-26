import './tokens.css';
import './style.css';
import { API_BASE, CURRENT_USER } from './config.js';
import { initTheme } from './theme.js';
import { getLocalTimeString, showToast } from './utils.js';
import { initBondingPlan } from './bonding_plan.js';

let tables = [];
let selectedTable = '';
let tableSchema = null;
let gridData = {}; // key: "x_y" -> value (physical coordinates)
let legend = [];
let activeBrush = '';
let isMouseDown = false;
let isRightDrag = false;

// Rotation & Side Mirroring States
let currentRotation = 0; // 0, 90, 180, 270
let currentSide = 'front'; // 'front', 'back'
let isOriginMode = false; // Origin designation mode state
let isBoxDragging = false; // Bounding box drag selection state
let boxStartCell = null; // Start cell reference for bounding box
let lastSelectionBox = null; // Track coordinates of current selection bounding box
let gridCells2D = []; // 2D reference array of cell metadata objects [row][col]
let dragType = null; // 'paint' | 'erase'
let selectedEdgeTargetMap = null; // Track active E1/E2 edge selection map
let loadedFCells = new Set(); // Track physical keys of cells loaded with value 'F'

function isProtectedFCell(key) {
  return loadedFCells.has(key);
}

// Default Legend
const DEFAULT_LEGEND = [
  { value: '1', desc: 'GOOD', color: '#10b981' },
  { value: '0', desc: 'FAIL', color: '#ef4444' },
  { value: '2', desc: 'EMPTY', color: '#4b5563' },
  { value: '3', desc: 'REWORK', color: '#f59e0b' }
];

// ----------------------------------------------------
// Split Registry (map_split_registry) — legend의 서버 영속화
// value description = 실험 split 조건의 자연어 기록.
// 서버(제네릭 테이블 API)가 SSOT, localStorage는 오프라인 캐시로 강등.
// ----------------------------------------------------
const SPLIT_REGISTRY_TABLE = 'map_split_registry';
// map_key 자체가 '_' 조인 문자열이고 테이블명에도 '_'가 흔하므로 bk 분리자는 '|' 사용
// (server/config/table_config.json의 composite_key_separator와 반드시 일치해야 함)
const SPLIT_KEY_SEP = '|';

let legendMeta = {}; // legend value -> { updated_by, updated_at } (registry 조회/저장 메타)
let legendServerSaveTimer = null;

function buildSplitKey(refTable, mapKey, value) {
  return [refTable, mapKey, value].join(SPLIT_KEY_SEP);
}

// PUT /tables/map_split_registry/data/updates 페이로드 빌더 (순수 함수 — 하니스 검증 대상)
function buildLegendRegistryUpdates(refTable, mapKey, legendArr, user, nowStr) {
  if (!refTable || !mapKey || !Array.isArray(legendArr)) return [];
  return legendArr
    .filter(item => item && item.value !== undefined && item.value !== null && String(item.value).trim() !== '')
    .map(item => {
      const value = String(item.value).trim();
      const bk = buildSplitKey(refTable, mapKey, value);
      return {
        business_key_val: bk,
        updates: {
          split_key: bk,
          ref_table: refTable,
          map_key: mapKey,
          value: value,
          split_desc: (item.desc || '').trim(),
          color: item.color || '',
          eventtime: nowStr
        },
        source_name: 'user',
        updated_by: user
      };
    });
}

// GET /tables/map_split_registry/data 응답 → legend 행 배열 (순수 함수 — 하니스 검증 대상)
// 셀 계약 준수: 각 컬럼은 {value, is_overwrite, priority_source, updated_by, ...} 객체로 읽는다.
// dedupeByValue=true(테이블 단위 조회)면 value 중복 시 updated_at 최신 행이 이긴다.
function parseLegendRegistryRows(result, dedupeByValue) {
  const rows = [];
  if (result && Array.isArray(result.data)) {
    result.data.forEach(row => {
      const d = row.data || {};
      const value = d.value?.value;
      if (value === undefined || value === null || String(value).trim() === '') return;
      rows.push({
        value: String(value).trim(),
        desc: d.split_desc?.value != null ? String(d.split_desc.value) : '',
        color: d.color?.value != null && String(d.color.value) !== '' ? String(d.color.value) : '#6b7280',
        map_key: d.map_key?.value != null ? String(d.map_key.value) : '',
        updated_by: d.split_desc?.updated_by || d.value?.updated_by || 'system',
        updated_at: d.updated_at?.value || ''
      });
    });
  }
  if (!dedupeByValue) return rows;
  const byValue = new Map();
  rows.forEach(r => {
    const prev = byValue.get(r.value);
    if (!prev || String(r.updated_at) > String(prev.updated_at)) byValue.set(r.value, r);
  });
  return Array.from(byValue.values());
}

// push 대상 값 중 split 서술이 비어있는 값 추출 (순수 함수 — 하니스 검증 대상)
function getMissingDescValues(pushedValues, legendArr) {
  return (pushedValues || []).filter(v => {
    const item = (legendArr || []).find(l => String(l.value) === String(v));
    return !item || !(item.desc || '').trim();
  });
}

function formatLegendMetaText(meta) {
  if (!meta || (!meta.updated_by && !meta.updated_at)) return '서버 미저장';
  return `${meta.updated_by || 'system'} · ${meta.updated_at || ''}`;
}

function getMapIdFromMeta(metaDict) {
  if (!metaDict) return 'default_map';

  let mapKeyCols = tableSchema.map_key_columns;
  if (!mapKeyCols || !Array.isArray(mapKeyCols) || mapKeyCols.length === 0) {
    if (tableSchema.composite_key_source && Array.isArray(tableSchema.composite_key_source)) {
      mapKeyCols = tableSchema.composite_key_source.filter(col => !['x', 'y', 'val', 'die_id', 'code', 'grid_metadata'].includes(col.toLowerCase()));
    }
  }

  if (mapKeyCols && mapKeyCols.length > 0) {
    const vals = mapKeyCols.map(col => metaDict[col]).filter(v => v !== undefined && v !== null && String(v).trim() !== '');
    if (vals.length > 0) return vals.join('_');
  }

  const allVals = Object.values(metaDict).filter(v => v !== undefined && v !== null && String(v).trim() !== '');
  return allVals.length > 0 ? allVals.join('_') : 'default_map';
}

function debounce(func, wait = 200) {
  let timeout;
  return function(...args) {
    clearTimeout(timeout);
    timeout = setTimeout(() => func.apply(this, args), wait);
  };
}

// Initialize DOM elements when loaded
document.addEventListener('DOMContentLoaded', async () => {
  initTheme();
  initDOMElements();
  initMouseDragEvents();
  initBondingPlan();
  await loadTablesList();
});

// Cache DOM Elements
const el = {};
function initDOMElements() {
  el.tableSelect = document.getElementById('map-table-select');
  el.metadataContainer = document.getElementById('metadata-fields-container');
  el.gridCols = document.getElementById('grid-cols');
  el.gridRows = document.getElementById('grid-rows');
  el.gridStartX = document.getElementById('grid-start-x');
  el.gridStartY = document.getElementById('grid-start-y');
  el.gridYInvert = document.getElementById('grid-y-invert');
  el.showAnnotations = document.getElementById('show-annotations');
  
  el.physWaferDia = document.getElementById('phys-wafer-dia');
  el.physChipX = document.getElementById('phys-chip-x');
  el.physChipY = document.getElementById('phys-chip-y');
  el.physOffsetX = document.getElementById('phys-offset-x');
  el.physOffsetY = document.getElementById('phys-offset-y');
  el.physEdgeMargin = document.getElementById('phys-edge-margin');
  el.btnApplyPhysGeom = document.getElementById('btn-apply-phys-geom');
  
  el.colMapX = document.getElementById('col-map-x');
  el.colMapY = document.getElementById('col-map-y');
  el.colMapVal = document.getElementById('col-map-val');
  
  el.btnLoadMap = document.getElementById('btn-load-map');
  el.btnAddLegend = document.getElementById('btn-add-legend');
  el.legendList = document.getElementById('legend-list');
  
  el.activeBrushVal = document.getElementById('active-brush-val');
  el.gridStatusCoords = document.getElementById('grid-status-coords');
  el.btnSetOrigin = document.getElementById('btn-set-origin');
  el.btnSelectE1 = document.getElementById('btn-select-e1');
  el.btnSelectE2 = document.getElementById('btn-select-e2');
  el.btnAutoPaintE1E2 = document.getElementById('btn-autopaint-e1e2');
  el.btnFillSelected = document.getElementById('btn-fill-selected');
  el.btnClearSelected = document.getElementById('btn-clear-selected');
  el.btnClearGrid = document.getElementById('btn-clear-grid');
  el.btnFillGrid = document.getElementById('btn-fill-grid');
  el.btnPushMap = document.getElementById('btn-push-map');
  
  el.presetSelect = document.getElementById('preset-select');
  el.btnSavePreset = document.getElementById('btn-save-preset');
  el.btnDeletePreset = document.getElementById('btn-delete-preset');
  
  el.btnSelectMenu = document.getElementById('btn-select-menu');
  el.selectMenuDropdown = document.getElementById('select-menu-dropdown');
  el.btnOpsMenu = document.getElementById('btn-ops-menu');
  el.opsMenuDropdown = document.getElementById('ops-menu-dropdown');
  el.selectionActionsContainer = document.getElementById('selection-actions-container');
  el.btnCopyExcel = document.getElementById('btn-copy-excel');

  el.choiceModal = document.getElementById('choice-modal');
  el.btnChoiceStandard = document.getElementById('btn-choice-standard');
  el.btnChoiceCurrent = document.getElementById('btn-choice-current');
  el.btnChoiceCancel = document.getElementById('btn-choice-cancel');

  el.gridCanvas = document.getElementById('grid-canvas');
  el.waferCanvas = document.getElementById('wafer-grid-canvas');
  el.gridWrapper = document.getElementById('grid-wrapper');
  el.gridNotch = document.getElementById('grid-notch');
  el.mapWorkspace = document.getElementById('map-workspace');
  el.sideIndicator = document.getElementById('side-indicator');

  // Fit the (square) grid to the available workspace on any size change.
  // ResizeObserver also covers container-only resizes (split panels) that window 'resize' misses.
  window.addEventListener('resize', fitGridToWorkspace);
  if (window.ResizeObserver && el.mapWorkspace) {
    new ResizeObserver(() => fitGridToWorkspace()).observe(el.mapWorkspace);
  }
  updateSideIndicator();

  // Bind Events
  el.tableSelect.addEventListener('change', (e) => switchTable(e.target.value));

  if (el.btnSelectMenu && el.selectMenuDropdown) {
    el.btnSelectMenu.addEventListener('click', (e) => {
      e.stopPropagation();
      const isVisible = el.selectMenuDropdown.style.display === 'flex';
      el.selectMenuDropdown.style.display = isVisible ? 'none' : 'flex';
      if (el.opsMenuDropdown) el.opsMenuDropdown.style.display = 'none';
    });
  }

  if (el.btnOpsMenu && el.opsMenuDropdown) {
    el.btnOpsMenu.addEventListener('click', (e) => {
      e.stopPropagation();
      const isVisible = el.opsMenuDropdown.style.display === 'flex';
      el.opsMenuDropdown.style.display = isVisible ? 'none' : 'flex';
      if (el.selectMenuDropdown) el.selectMenuDropdown.style.display = 'none';
    });
  }

  document.addEventListener('click', () => {
    if (el.selectMenuDropdown) el.selectMenuDropdown.style.display = 'none';
    if (el.opsMenuDropdown) el.opsMenuDropdown.style.display = 'none';
  });

  if (el.selectMenuDropdown) {
    el.selectMenuDropdown.addEventListener('click', (e) => {
      e.stopPropagation();
    });
  }
  if (el.opsMenuDropdown) {
    el.opsMenuDropdown.addEventListener('click', (e) => {
      e.stopPropagation();
    });
  }
  
  if (el.presetSelect) {
    el.presetSelect.addEventListener('change', loadSelectedPreset);
  }
  if (el.btnSavePreset) {
    el.btnSavePreset.addEventListener('click', saveCustomPreset);
  }
  if (el.btnDeletePreset) {
    el.btnDeletePreset.addEventListener('click', deleteCustomPreset);
  }
  fetchAndRenderPresets();
  
  const inputsToRedraw = [el.gridCols, el.gridRows, el.gridStartX, el.gridStartY, el.gridYInvert, el.showAnnotations];
  inputsToRedraw.forEach(input => {
    input.addEventListener('change', () => {
      // Validate bounds
      if (input === el.gridCols || input === el.gridRows) {
        let v = parseInt(input.value, 10);
        if (isNaN(v) || v < 1) input.value = 1;
        if (v > 100) input.value = 100;
        
        // Auto-disable annotation display on large grids (>400 cells) to prevent rendering bottleneck
        const currentCols = parseInt(el.gridCols.value, 10) || 10;
        const currentRows = parseInt(el.gridRows.value, 10) || 10;
        if (currentCols * currentRows > 400 && el.showAnnotations) {
          el.showAnnotations.checked = false;
        }
      } else if (input === el.gridStartX || input === el.gridStartY) {
        let v = parseInt(input.value, 10);
        if (isNaN(v)) input.value = 0;
      }
      scheduleRenderGridCanvas();
    });
  });

  el.btnLoadMap.addEventListener('click', loadExistingMap);
  el.btnAddLegend.addEventListener('click', addNewLegendRow);
  el.btnSetOrigin.addEventListener('click', () => {
    isOriginMode = !isOriginMode;
    if (isOriginMode) {
      el.btnSetOrigin.classList.add('active');
      el.btnSetOrigin.style.borderColor = 'var(--color-secondary)';
      el.btnSetOrigin.style.color = 'var(--color-secondary)';
      el.gridCanvas.classList.add('origin-mode-active');
    } else {
      el.btnSetOrigin.classList.remove('active');
      el.btnSetOrigin.style.borderColor = '';
      el.btnSetOrigin.style.color = '';
      el.gridCanvas.classList.remove('origin-mode-active');
    }
  });
  el.btnClearGrid.addEventListener('click', clearGrid);
  el.btnFillGrid.addEventListener('click', fillGrid);
  el.btnPushMap.addEventListener('click', pushMapData);
  if (el.btnCopyExcel) el.btnCopyExcel.addEventListener('click', copyGridToExcel);
  if (el.btnApplyPhysGeom) el.btnApplyPhysGeom.addEventListener('click', applyPhysicalGeometry);
  
  // Physical input triggers: use change event for typing completion and scheduleRenderGridCanvas for rAF throttling
  [el.physWaferDia, el.physChipX, el.physChipY, el.physOffsetX, el.physOffsetY, el.physEdgeMargin].forEach(input => {
    if (input) {
      input.addEventListener('change', () => scheduleRenderGridCanvas());
      input.addEventListener('input', () => scheduleRenderGridCanvas());
    }
  });
  
  if (el.btnSelectE1) el.btnSelectE1.addEventListener('click', () => selectEdgeCells(1));
  if (el.btnSelectE2) el.btnSelectE2.addEventListener('click', () => selectEdgeCells(2));
  if (el.btnAutoPaintE1E2) el.btnAutoPaintE1E2.addEventListener('click', autoPaintE1E2);
  if (el.btnFillSelected) el.btnFillSelected.addEventListener('click', fillSelectedCells);
  if (el.btnClearSelected) el.btnClearSelected.addEventListener('click', clearSelectedCells);

  // Dynamic Metadata Inputs change triggers
  el.colMapX.addEventListener('change', () => {
    renderMetadataInputs();
    scheduleRenderGridCanvas();
  });
  el.colMapY.addEventListener('change', () => {
    renderMetadataInputs();
    scheduleRenderGridCanvas();
  });
  el.colMapVal.addEventListener('change', () => {
    renderMetadataInputs();
    scheduleRenderGridCanvas();
  });

  // Rotation Buttons
  document.querySelectorAll('.btn-rot').forEach(btn => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('.btn-rot').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentRotation = parseInt(btn.dataset.rot, 10);
      scheduleRenderGridCanvas();
    });
  });

  // Wafer Side Radios
  document.querySelectorAll('input[name="wafer-side"]').forEach(radio => {
    radio.addEventListener('change', (e) => {
      currentSide = e.target.value;
      updateSideIndicator();
      scheduleRenderGridCanvas();
    });
  });

  // Prevent right-click context menu on canvas
  el.gridCanvas.addEventListener('contextmenu', (e) => e.preventDefault());
}

function getGridCellObject(c, r, visualCols, visualRows, physConfig, width, height) {
  const cols = parseInt(el.gridCols.value, 10) || 10;
  const rows = parseInt(el.gridRows.value, 10) || 10;
  const startX = parseInt(el.gridStartX.value, 10) || 0;
  const startY = parseInt(el.gridStartY.value, 10) || 0;
  const invertY = el.gridYInvert ? el.gridYInvert.checked : false;

  const box = getWaferBoundingBox(currentRotation, currentSide);
  const c_zero = box.minC - startX;
  const r_zero = !invertY ? (box.minR - startY) : (box.maxR + startY);
  const hasZeroZero = (c_zero >= 0 && c_zero < visualCols) && (r_zero >= 0 && r_zero < visualRows);

  const physical = getPhysicalCoords(c, r, cols, rows, currentRotation, currentSide);
  const visual = getVisualCoords(c, r, cols, rows, currentRotation, currentSide, invertY, startX, startY);
  const coordKey = `${physical.x}_${physical.y}`;

  const isOriginCell = hasZeroZero 
    ? (visual.x === 0 && visual.y === 0) 
    : (visual.x === startX && visual.y === startY);

  const completelyInside = isCellInsideWaferFast(c, r, visualCols, visualRows, physConfig, width, height);

  return {
    c, r, x: visual.x, y: visual.y, px: physical.x, py: physical.y,
    key: coordKey, inside: completelyInside, isOrigin: isOriginCell
  };
}

function getGridCellFromMouseEvent(e) {
  const canvasTarget = el.waferCanvas || el.gridCanvas;
  if (!canvasTarget) return null;
  const rect = canvasTarget.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) return null;

  const cols = parseInt(el.gridCols.value, 10) || 10;
  const rows = parseInt(el.gridRows.value, 10) || 10;
  const isRotated90or270 = (currentRotation === 90 || currentRotation === 270);
  const visualCols = isRotated90or270 ? rows : cols;
  const visualRows = isRotated90or270 ? cols : rows;

  const xRel = e.clientX - rect.left;
  const yRel = e.clientY - rect.top;

  if (xRel < 0 || xRel > rect.width || yRel < 0 || yRel > rect.height) return null;

  const physConfig = getTransformedPhysicalConfig(currentRotation, currentSide);
  const cellW = rect.width / visualCols;
  const cellH = rect.height / visualRows;
  const { shiftX, shiftY } = getScreenShift(physConfig, cellW, cellH);

  const c = Math.floor((xRel - shiftX) / cellW);
  const r = Math.floor((yRel - shiftY) / cellH);

  if (c >= 0 && c < visualCols && r >= 0 && r < visualRows && gridCells2D[r]?.[c]) {
    return gridCells2D[r][c];
  }

  return getGridCellObject(c, r, visualCols, visualRows, physConfig, rect.width, rect.height);
}

let currentHoverCell = null;

function initMouseDragEvents() {
  window.addEventListener('mousedown', (e) => {
    isMouseDown = true;
    isRightDrag = (e.button === 2);
  });

  const canvasTarget = el.waferCanvas || el.gridCanvas;
  if (canvasTarget) {
    canvasTarget.addEventListener('mousedown', (e) => {
      e.preventDefault();
      const cell = getGridCellFromMouseEvent(e);
      if (!cell) return;

      if (el.selectionActionsContainer) el.selectionActionsContainer.style.display = 'none';

      if (isOriginMode) {
        handleCellClick(cell, e);
        return;
      }

      const isRight = (e.button === 2 || e.buttons === 2);
      isBoxDragging = true;
      boxStartCell = cell;
      dragType = isRight ? 'erase' : 'paint';
      lastSelectionBox = { minC: cell.c, maxC: cell.c, minR: cell.r, maxR: cell.r };

      scheduleRenderGridCanvas();
    });

    canvasTarget.addEventListener('mouseleave', () => {
      if (currentHoverCell !== null) {
        currentHoverCell = null;
        scheduleRenderGridCanvas();
      }
    });

    canvasTarget.addEventListener('mousemove', (e) => {
      const cell = getGridCellFromMouseEvent(e);
      if (cell === currentHoverCell && !isBoxDragging) return;
      currentHoverCell = cell;

      if (cell) {
        const val = gridData[cell.key] || '';
        el.gridStatusCoords.textContent = `Cursor: (${cell.x}, ${cell.y}) = ${val !== '' ? val : 'Empty'}`;
      }

      if (isBoxDragging && boxStartCell && cell) {
        const c1 = boxStartCell.c;
        const r1 = boxStartCell.r;
        const c2 = cell.c;
        const r2 = cell.r;

        const minC = Math.min(c1, c2);
        const maxC = Math.max(c1, c2);
        const minR = Math.min(r1, r2);
        const maxR = Math.max(r1, r2);

        if (lastSelectionBox && 
            lastSelectionBox.minC === minC && lastSelectionBox.maxC === maxC &&
            lastSelectionBox.minR === minR && lastSelectionBox.maxR === maxR) {
          return;
        }

        lastSelectionBox = { minC, maxC, minR, maxR };
        scheduleRenderGridCanvas();
      } else if (!isBoxDragging) {
        scheduleRenderGridCanvas();
      }
    });
  }

  window.addEventListener('mouseup', () => {
    isMouseDown = false;
    isRightDrag = false;

    if (isBoxDragging) {
      if (boxStartCell && lastSelectionBox) {
        const { minC, maxC, minR, maxR } = lastSelectionBox;

        for (let r = minR; r <= maxR; r++) {
          for (let c = minC; c <= maxC; c++) {
            const cell = gridCells2D[r]?.[c];
            if (!cell) continue;

            const key = cell.key;
            if (isProtectedFCell(key)) continue;

            if (dragType === 'erase') {
              gridData[key] = '';
            } else if (dragType === 'paint') {
              if (!cell.inside) continue;

              const existingVal = gridData[key] || '';
              const isSingleClick = (minC === maxC && minR === maxR);
              if (!isSingleClick && existingVal !== '') {
                continue;
              }

              if (activeBrush !== undefined && activeBrush !== null) {
                gridData[key] = activeBrush;
              }
            }
          }
        }
      }

      if (el.selectionActionsContainer) el.selectionActionsContainer.style.display = 'none';

      isBoxDragging = false;
      boxStartCell = null;
      lastSelectionBox = null;
      dragType = null;
      
      updateLegendCounts();
      scheduleRenderGridCanvas();
    }
  });
}

// Fetch tables list
async function loadTablesList() {
  try {
    const res = await fetch(`${API_BASE}/tables`);
    const data = await res.json();
    el.tableSelect.innerHTML = '';
    
    if (data.tables && data.tables.length > 0) {
      // Fetch schema for all tables and filter ONLY map tables that have map_key_columns configured
      const mapTables = [];
      for (const tableName of data.tables) {
        try {
          const sRes = await fetch(`${API_BASE}/tables/${tableName}/schema`);
          if (sRes.ok) {
            const schema = await sRes.json();
            const keys = schema.map_key_columns || [];
            if (Array.isArray(keys) && keys.length > 0) {
              mapTables.push(tableName);
            }
          }
        } catch (e) {
          console.warn(`Failed to fetch schema for ${tableName}:`, e);
        }
      }

      if (mapTables.length > 0) {
        mapTables.forEach(table => {
          const option = document.createElement('option');
          option.value = table;
          option.textContent = table;
          el.tableSelect.appendChild(option);
        });
        // Auto select bonding_map if available, otherwise first map table
        const hasBondingMap = mapTables.includes('bonding_map');
        const startTable = hasBondingMap ? 'bonding_map' : mapTables[0];
        el.tableSelect.value = startTable;
        await switchTable(startTable);
      } else {
        el.tableSelect.innerHTML = '<option value="">No map tables available (map_key_columns missing)</option>';
      }
    } else {
      el.tableSelect.innerHTML = '<option value="">No tables available</option>';
    }
  } catch (err) {
    console.error('Failed to load tables', err);
    el.tableSelect.innerHTML = '<option value="">Connection Error</option>';
  }
}

// Switch current working table & load schema
async function switchTable(tableName) {
  selectedTable = tableName;
  try {
    const res = await fetch(`${API_BASE}/tables/${tableName}/schema`);
    tableSchema = await res.json();
    
    // Fill advanced column selectors
    fillColumnDropdowns();

    // Render Dynamic Metadata Inputs
    renderMetadataInputs();

    // If a map is currently in progress, offer to carry it over to the newly
    // selected table so it can be edited-then-saved there directly, instead of
    // always resetting. pushMapData() targets selectedTable, so the kept map is
    // pushed to the new table once its metadata (map identity) is entered.
    const hasWorkingMap = gridData && Object.keys(gridData).length > 0;
    const keepMap = hasWorkingMap && confirm(
      `현재 편집 중인 맵을 유지한 채 '${tableName}' 테이블로 전환하시겠습니까?\n\n` +
      `[확인] 맵 유지 — 저장 시 '${tableName}'에 적재됩니다. (대상 테이블의 메타데이터를 새로 입력하세요)\n` +
      `[취소] 맵 초기화`
    );

    if (keepMap) {
      // Preserve current grid + legend/colors; only the target metadata is re-entered.
      renderLegendTable();
    } else {
      // Load target table's legend, then reset the grid (original behavior).
      // 서버 split registry(테이블 단위, value별 최신) 우선 → localStorage 캐시 → DEFAULT.
      // 메타 미입력 시점이라 map_key는 없음 — 정확한 맵 단위 legend는 Load Existing Map에서 재적용.
      await loadLegend(tableName, null);
      renderLegendTable();
      gridData = {};
    }
    renderGridCanvas();
  } catch (err) {
    console.error('Schema fetch failed', err);
  }
}

function renderMetadataInputs() {
  const container = el.metadataContainer;
  if (!container || !tableSchema) return;
  container.innerHTML = '';

  const cols = tableSchema.columns || [];
  const xCol = el.colMapX ? el.colMapX.value : 'x';
  const yCol = el.colMapY ? el.colMapY.value : 'y';
  const valCol = el.colMapVal ? el.colMapVal.value : 'val';

  // Determine map_id search columns
  let searchCols = tableSchema.map_key_columns;
  if (!searchCols || !Array.isArray(searchCols) || searchCols.length === 0) {
    if (tableSchema.composite_key_source && Array.isArray(tableSchema.composite_key_source)) {
      searchCols = tableSchema.composite_key_source.filter(col => 
        !['x', 'y', 'val', 'die_id', 'code', 'grid_metadata'].includes(col.toLowerCase()) &&
        col !== xCol && col !== yCol && col !== valCol
      );
    }
  }
  if (!searchCols || searchCols.length === 0) {
    if (tableSchema.business_key && !['x', 'y', 'val', 'die_id', 'code'].includes(tableSchema.business_key.toLowerCase())) {
      searchCols = [tableSchema.business_key];
    }
  }

  // Fallback: system cols filter
  if (!searchCols || searchCols.length === 0) {
    const systemCols = [
      'created_at', 'updated_at', 'row_id', 'business_key_val',
      'is_graph_synced', 'needs_graph_rollback', 'graph_synced_at',
      'grid_metadata'
    ];
    searchCols = cols.filter(col => !systemCols.includes(col) && col !== xCol && col !== yCol && col !== valCol);
  }

  searchCols.forEach(col => {
    if (!cols.includes(col)) return;
    const colType = tableSchema.column_types[col] || 'string';
    const formGroup = document.createElement('div');
    formGroup.className = 'control-group-vertical';

    const label = document.createElement('label');
    label.htmlFor = `meta-input-${col}`;
    label.textContent = `${col} (${colType})`;

    const input = document.createElement('input');
    input.type = 'text';
    input.id = `meta-input-${col}`;
    input.className = 'glass-input w-full';
    input.placeholder = `${col} 검색어 입력`;
    
    formGroup.appendChild(label);
    formGroup.appendChild(input);
    container.appendChild(formGroup);
  });
}

function getBaseColumnName() {
  if (!tableSchema) return 'base';
  const compositeSources = tableSchema.composite_key_source || [];
  // Base is usually the first non-coordinate key source
  const baseCol = compositeSources.find(c => c !== 'x' && c !== 'y');
  return baseCol || 'base';
}

function fillColumnDropdowns() {
  if (!tableSchema) return;
  const cols = tableSchema.columns || [];
  
  const populate = (dropdown, defaultPattern) => {
    dropdown.innerHTML = '';
    cols.forEach(col => {
      if (col === 'created_at' || col === 'updated_at') return;
      const option = document.createElement('option');
      option.value = col;
      option.textContent = col;
      dropdown.appendChild(option);
    });
    // Auto select based on name matching
    const matched = cols.find(c => c.toLowerCase() === defaultPattern.toLowerCase());
    if (matched) dropdown.value = matched;
  };

  populate(el.colMapX, 'x');
  populate(el.colMapY, 'y');
  // bonding_map has 'leg' as value column. Fallback to common value column names
  const valMatches = ['leg', 'status', 'value', 'val', 'bin'];
  const matchedVal = cols.find(c => valMatches.includes(c.toLowerCase()));
  populate(el.colMapVal, matchedVal || cols[0]);
}

// ----------------------------------------------------
// Coordinates Mapping Calculation
// ----------------------------------------------------
function getPhysicalCoords(colVisual, rowVisual, cols, rows, rotation, side) {
  const isRotated90or270 = (rotation === 90 || rotation === 270);
  const visualCols = isRotated90or270 ? rows : cols;
  const visualRows = isRotated90or270 ? cols : rows;

  const origChipX = el.physChipX ? (parseFloat(el.physChipX.value) || 2.5) : 2.5;
  const origChipY = el.physChipY ? (parseFloat(el.physChipY.value) || 2.5) : 2.5;
  let origOffsetX = el.physOffsetX ? (parseFloat(el.physOffsetX.value) || 0.0) : 0.0;
  let origOffsetY = el.physOffsetY ? (parseFloat(el.physOffsetY.value) || 0.0) : 0.0;

  if (side === 'back') {
    origOffsetX = -origOffsetX;
  }

  // Get screen-space shift for the current rotation in cell units
  const physConfig = getTransformedPhysicalConfig(rotation, side);
  const { shiftX, shiftY } = getScreenShift(physConfig, 1.0, 1.0);

  // Screen cell position relative to wafer center
  const xScreenWafer = colVisual - (visualCols - 1) / 2.0 + shiftX;
  const yScreenWafer = rowVisual - (visualRows - 1) / 2.0 + shiftY;

  // Rotate screen cell relative to wafer center by -rotation (to map screen coordinates to physical coordinates)
  let xRot = xScreenWafer;
  let yRot = yScreenWafer;

  if (rotation === 0) {
    xRot = xScreenWafer;
    yRot = yScreenWafer;
  } else if (rotation === 90) {
    // -90 deg CCW = 90 deg CW: X' = Y, Y' = -X
    xRot = yScreenWafer;
    yRot = -xScreenWafer;
  } else if (rotation === 180) {
    xRot = -xScreenWafer;
    yRot = -yScreenWafer;
  } else if (rotation === 270) {
    // -270 deg CCW = 90 deg CCW: X' = -Y, Y' = X
    xRot = -yScreenWafer;
    yRot = xScreenWafer;
  }

  if (side === 'back') {
    xRot = -xRot;
  }

  // Convert back to physical grid coordinate (xp, yp)
  const xp = Math.round(xRot + (cols - 1) / 2.0);
  const yp = Math.round(yRot + (rows - 1) / 2.0);

  return { x: xp, y: yp };
}

function getCellFromPhysicalCoords(xp, yp, cols, rows, rotation, side) {
  const isRotated90or270 = (rotation === 90 || rotation === 270);
  const visualCols = isRotated90or270 ? rows : cols;
  const visualRows = isRotated90or270 ? cols : rows;

  let xRot = xp - (cols - 1) / 2.0;
  let yRot = yp - (rows - 1) / 2.0;

  if (side === 'back') {
    xRot = -xRot;
  }

  // Rotate back to screen coordinates
  let xScreenWafer = xRot;
  let yScreenWafer = yRot;

  if (rotation === 0) {
    xScreenWafer = xRot;
    yScreenWafer = yRot;
  } else if (rotation === 90) {
    xScreenWafer = -yRot;
    yScreenWafer = xRot;
  } else if (rotation === 180) {
    xScreenWafer = -xRot;
    yScreenWafer = -yRot;
  } else if (rotation === 270) {
    xScreenWafer = yRot;
    yScreenWafer = -xRot;
  }

  // Get screen-space shift for the current rotation in cell units
  const physConfig = getTransformedPhysicalConfig(rotation, side);
  const { shiftX, shiftY } = getScreenShift(physConfig, 1.0, 1.0);

  const colVisual = xScreenWafer + (visualCols - 1) / 2.0 - shiftX;
  const rowVisual = yScreenWafer + (visualRows - 1) / 2.0 - shiftY;

  return { c: Math.round(colVisual), r: Math.round(rowVisual) };
}

function getCellFromVisualCoords(xv, yv, cols, rows, rotation, side, invertY, startX, startY) {
  const box = getWaferBoundingBox(rotation, side);
  
  const c = xv - startX + box.minC;

  let r = 0;
  if (!invertY) {
    r = yv - startY + box.minR;
  } else {
    r = box.maxR - (yv - startY);
  }

  return { c, r };
}

let boundingBoxCache = {};

function getWaferBoundingBox(rotation, side) {
  const dia = el.physWaferDia ? el.physWaferDia.value : '300';
  const cx = el.physChipX ? el.physChipX.value : '2.5';
  const cy = el.physChipY ? el.physChipY.value : '2.5';
  const ox = el.physOffsetX ? el.physOffsetX.value : '0';
  const oy = el.physOffsetY ? el.physOffsetY.value : '0';
  const em = el.physEdgeMargin ? el.physEdgeMargin.value : '3';

  const cols = parseInt(el.gridCols ? el.gridCols.value : '10', 10) || 10;
  const rows = parseInt(el.gridRows ? el.gridRows.value : '10', 10) || 10;
  const isRotated90or270 = (rotation === 90 || rotation === 270);
  const visualCols = isRotated90or270 ? rows : cols;
  const visualRows = isRotated90or270 ? cols : rows;

  const key = `${rotation}_${side}_${visualCols}_${visualRows}_${dia}_${cx}_${cy}_${ox}_${oy}_${em}`;
  if (boundingBoxCache[key]) {
    return boundingBoxCache[key];
  }

  const physConfig = getTransformedPhysicalConfig(rotation, side);
  const width = 700;
  const height = 700;

  let minC = 9999, maxC = -9999;
  let minR = 9999, maxR = -9999;
  let insideCount = 0;

  for (let r = 0; r < visualRows; r++) {
    for (let c = 0; c < visualCols; c++) {
      if (isCellInsideWaferFast(c, r, visualCols, visualRows, physConfig, width, height)) {
        insideCount++;
        if (c < minC) minC = c;
        if (c > maxC) maxC = c;
        if (r < minR) minR = r;
        if (r > maxR) maxR = r;
      }
    }
  }

  const box = {
    minC: minC === 9999 ? 0 : minC,
    maxC: maxC === -9999 ? 0 : maxC,
    minR: minR === 9999 ? 0 : minR,
    maxR: maxR === -9999 ? 0 : maxR
  };

  boundingBoxCache[key] = box;
  return box;
}

function getVisualCoords(colVisual, rowVisual, cols, rows, rotation, side, invertY, startX, startY) {
  const box = getWaferBoundingBox(rotation, side);

  const xv = colVisual - box.minC + startX;

  let yv = 0;
  if (!invertY) {
    yv = rowVisual - box.minR + startY;
  } else {
    yv = box.maxR - rowVisual + startY;
  }

  return { x: xv, y: yv };
}

function getTransformedPhysicalConfig(currentRotation, currentSide) {
  const waferDia = el.physWaferDia ? (parseFloat(el.physWaferDia.value) || 300) : 300;
  const edgeMargin = el.physEdgeMargin ? (parseFloat(el.physEdgeMargin.value) || 3.0) : 3.0;
  const effectiveRadius = Math.max(0, (waferDia / 2.0) - edgeMargin);
  const origChipX = el.physChipX ? (parseFloat(el.physChipX.value) || 2.5) : 2.5;
  const origChipY = el.physChipY ? (parseFloat(el.physChipY.value) || 2.5) : 2.5;
  let origOffsetX = el.physOffsetX ? (parseFloat(el.physOffsetX.value) || 0.0) : 0.0;
  let origOffsetY = el.physOffsetY ? (parseFloat(el.physOffsetY.value) || 0.0) : 0.0;

  if (currentSide === 'back') {
    origOffsetX = -origOffsetX;
  }

  let chipX = origChipX;
  let chipY = origChipY;
  if (currentRotation === 90 || currentRotation === 270) {
    chipX = origChipY;
    chipY = origChipX;
  }

  return {
    waferDia,
    effectiveRadius,
    radiusSq: effectiveRadius * effectiveRadius,
    chipX,
    chipY,
    origChipX,
    origChipY,
    origOffsetX,
    origOffsetY,
    rotation: currentRotation,
    side: currentSide
  };
}

function getScreenShift(physConfig, cellW, cellH) {
  if (!physConfig) return { shiftX: 0, shiftY: 0 };
  const { origOffsetX, origOffsetY, origChipX, origChipY, rotation } = physConfig;
  const chipX = origChipX || 2.5;
  const chipY = origChipY || 2.5;

  let shiftX = 0;
  let shiftY = 0;

  if (rotation === 0) {
    shiftX = (origOffsetX / chipX) * cellW;
    shiftY = -(origOffsetY / chipY) * cellH;
  } else if (rotation === 90) {
    shiftX = (origOffsetY / chipY) * cellW;
    shiftY = (origOffsetX / chipX) * cellH;
  } else if (rotation === 180) {
    shiftX = -(origOffsetX / chipX) * cellW;
    shiftY = (origOffsetY / chipY) * cellH;
  } else if (rotation === 270) {
    shiftX = -(origOffsetY / chipY) * cellW;
    shiftY = -(origOffsetX / chipX) * cellH;
  }

  return { shiftX, shiftY };
}

function isCellInsideWaferFast(c, r, visualCols, visualRows, physConfig, width = 700, height = 700) {
  if (physConfig && physConfig.chipX > 0 && physConfig.chipY > 0 && physConfig.effectiveRadius > 0 && width > 0 && height > 0) {
    const cellW = width / visualCols;
    const cellH = height / visualRows;

    const { shiftX, shiftY } = getScreenShift(physConfig, cellW, cellH);

    const x0 = c * cellW + shiftX;
    const y0 = r * cellH + shiftY;

    const centerX = width / 2.0;
    const centerY = height / 2.0;

    const effRadX = (physConfig.effectiveRadius / physConfig.chipX) * cellW;
    const effRadY = (physConfig.effectiveRadius / physConfig.chipY) * cellH;

    const corners = [
      { x: x0, y: y0 },
      { x: x0 + cellW, y: y0 },
      { x: x0, y: y0 + cellH },
      { x: x0 + cellW, y: y0 + cellH }
    ];

    for (const corner of corners) {
      const dx = corner.x - centerX;
      const dy = corner.y - centerY;
      const normDistSq = (dx * dx) / (effRadX * effRadX) + (dy * dy) / (effRadY * effRadY);
      if (normDistSq > 1.0) {
        return false;
      }
    }

    return true;
  }

  return false;
}

function isCellInsideWafer(c, r, visualCols, visualRows) {
  const physConfig = getTransformedPhysicalConfig(currentRotation, currentSide);
  const width = el.gridCanvas ? Math.floor(el.gridCanvas.getBoundingClientRect().width || 700) : 700;
  const height = el.gridCanvas ? Math.floor(el.gridCanvas.getBoundingClientRect().height || 700) : 700;
  return isCellInsideWaferFast(c, r, visualCols, visualRows, physConfig, width, height);
}

function applyPhysicalGeometry() {
  const waferDia = el.physWaferDia ? parseFloat(el.physWaferDia.value) : 300;
  const edgeMargin = el.physEdgeMargin ? parseFloat(el.physEdgeMargin.value) : 3.0;
  const effectiveRadius = Math.max(0, (waferDia / 2.0) - edgeMargin);

  const chipX = el.physChipX ? parseFloat(el.physChipX.value) : 2.5;
  const chipY = el.physChipY ? parseFloat(el.physChipY.value) : 2.5;

  if (chipX <= 0 || chipY <= 0 || effectiveRadius <= 0) return;

  let cols = Math.ceil((2.0 * effectiveRadius) / chipX) + 2;
  let rows = Math.ceil((2.0 * effectiveRadius) / chipY) + 2;

  if (cols % 2 === 0) cols += 1;
  if (rows % 2 === 0) rows += 1;

  cols = Math.max(5, Math.min(100, cols));
  rows = Math.max(5, Math.min(100, rows));

  if (el.gridCols) el.gridCols.value = cols;
  if (el.gridRows) el.gridRows.value = rows;

  renderGridCanvas();
}

// ----------------------------------------------------
// Value Counts & Preset Functions
// ----------------------------------------------------
let serverPresets = {};

function updateOrientationUI() {
  document.querySelectorAll('.btn-rot').forEach(btn => {
    const rotVal = parseInt(btn.dataset.rot, 10);
    if (rotVal === currentRotation) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });

  document.querySelectorAll('input[name="wafer-side"]').forEach(radio => {
    if (radio.value === currentSide) {
      radio.checked = true;
    } else {
      radio.checked = false;
    }
  });
  updateSideIndicator();
}

async function fetchAndRenderPresets() {
  if (!el.presetSelect) return;
  try {
    const res = await fetch(`${API_BASE}/api/map-presets`);
    if (res.ok) {
      const data = await res.json();
      serverPresets = data.presets || {};
      renderPresetDropdown();
    }
  } catch (err) {
    console.error('[Map Presets] Failed to fetch map presets:', err);
  }
}

function renderPresetDropdown() {
  if (!el.presetSelect) return;
  el.presetSelect.innerHTML = '<option value="">-- Select Geometry Preset --</option>';

  const builtins = [];
  const customs = [];

  Object.entries(serverPresets).forEach(([key, p]) => {
    if (p.is_custom) {
      customs.push({ key, ...p });
    } else {
      builtins.push({ key, ...p });
    }
  });

  if (builtins.length > 0) {
    const optGroupBuiltin = document.createElement('optgroup');
    optGroupBuiltin.label = 'Built-in Geometry Presets';
    builtins.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.key;
      opt.textContent = p.name;
      optGroupBuiltin.appendChild(opt);
    });
    el.presetSelect.appendChild(optGroupBuiltin);
  }

  if (customs.length > 0) {
    const optGroupCustom = document.createElement('optgroup');
    optGroupCustom.label = 'Custom Geometry Presets';
    customs.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.key;
      opt.textContent = `⭐ ${p.name}`;
      optGroupCustom.appendChild(opt);
    });
    el.presetSelect.appendChild(optGroupCustom);
  }
}

// 프리셋 객체를 물리 규격/방향 UI에 적용 (프리셋 셀렉트와 무관하게 재사용 —
// 영역 선택 모드가 CORE/BASE 프리셋 규격 강제 시에도 동일 경로를 탄다)
function applyPresetObject(preset) {
  if (!preset) return;
  if (preset.phys_wafer_dia !== undefined && el.physWaferDia) {
    const diaStr = String(preset.phys_wafer_dia);
    if (['300', '200', '150'].includes(diaStr)) {
      el.physWaferDia.value = diaStr;
    } else {
      let opt = el.physWaferDia.querySelector(`option[value="${diaStr}"]`);
      if (!opt) {
        opt = document.createElement('option');
        opt.value = diaStr;
        opt.textContent = `${diaStr} mm (Custom)`;
        el.physWaferDia.appendChild(opt);
      }
      el.physWaferDia.value = diaStr;
    }
  }
  if (preset.phys_chip_x !== undefined && el.physChipX) el.physChipX.value = preset.phys_chip_x;
  if (preset.phys_chip_y !== undefined && el.physChipY) el.physChipY.value = preset.phys_chip_y;
  if (preset.phys_offset_x !== undefined && el.physOffsetX) el.physOffsetX.value = preset.phys_offset_x;
  if (preset.phys_offset_y !== undefined && el.physOffsetY) el.physOffsetY.value = preset.phys_offset_y;
  if (preset.phys_edge_margin !== undefined && el.physEdgeMargin) el.physEdgeMargin.value = preset.phys_edge_margin;

  if (preset.rotation !== undefined) currentRotation = preset.rotation;
  if (preset.side !== undefined) currentSide = preset.side;

  boundingBoxCache = {};
  updateOrientationUI();
  applyPhysicalGeometry();
  scheduleRenderGridCanvas();
  updateLegendCounts();
}

function loadSelectedPreset() {
  if (!el.presetSelect) return;
  const val = el.presetSelect.value;
  if (!val) {
    if (el.btnDeletePreset) el.btnDeletePreset.style.display = 'none';
    return;
  }

  const preset = serverPresets[val];
  if (preset) {
    applyPresetObject(preset);
    if (el.btnDeletePreset) {
      el.btnDeletePreset.style.display = preset.is_custom ? 'inline-block' : 'none';
    }
  }
}

async function saveCustomPreset() {
  const presetName = prompt('Enter custom geometry preset name:', `Geometry Preset ${new Date().toLocaleDateString()}`);
  if (!presetName) return;

  let diaVal = 300;
  if (el.physWaferDia) {
    if (el.physWaferDia.value === 'custom') {
      diaVal = parseFloat(prompt('Enter custom wafer diameter (mm):', '300')) || 300;
    } else {
      diaVal = parseFloat(el.physWaferDia.value) || 300;
    }
  }

  const payload = {
    name: presetName,
    phys_wafer_dia: diaVal,
    phys_chip_x: el.physChipX ? (parseFloat(el.physChipX.value) || 2.5) : 2.5,
    phys_chip_y: el.physChipY ? (parseFloat(el.physChipY.value) || 2.5) : 2.5,
    phys_offset_x: el.physOffsetX ? (parseFloat(el.physOffsetX.value) || 0.0) : 0.0,
    phys_offset_y: el.physOffsetY ? (parseFloat(el.physOffsetY.value) || 0.0) : 0.0,
    phys_edge_margin: el.physEdgeMargin ? (parseFloat(el.physEdgeMargin.value) || 3.0) : 3.0,
    rotation: currentRotation,
    side: currentSide
  };

  try {
    const res = await fetch(`${API_BASE}/api/map-presets`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      const data = await res.json();
      await fetchAndRenderPresets();
      if (el.presetSelect && data.preset_key) {
        el.presetSelect.value = data.preset_key;
        loadSelectedPreset();
      }
      alert(`Custom geometry preset '${presetName}' saved to server!`);
    } else {
      const errorData = await res.json().catch(() => ({ detail: res.statusText }));
      alert(`Failed to save custom geometry preset: ${errorData.detail || res.statusText}`);
    }
  } catch (err) {
    console.error('[Map Presets] Error saving preset:', err);
    alert(`Error saving custom preset to server: ${err.message}`);
  }
}

async function deleteCustomPreset() {
  if (!el.presetSelect) return;
  const val = el.presetSelect.value;
  if (!val) return;

  const preset = serverPresets[val];
  if (!preset || !preset.is_custom) return;

  if (!confirm(`Are you sure you want to delete custom preset '${preset.name}' from server?`)) return;

  try {
    const res = await fetch(`${API_BASE}/api/map-presets/${val}`, {
      method: 'DELETE'
    });

    if (res.ok) {
      await fetchAndRenderPresets();
      el.presetSelect.value = '';
      if (el.btnDeletePreset) el.btnDeletePreset.style.display = 'none';
      alert(`Preset '${preset.name}' deleted successfully.`);
    } else {
      const errorData = await res.json().catch(() => ({ detail: res.statusText }));
      alert(`Failed to delete preset from server: ${errorData.detail || res.statusText}`);
    }
  } catch (err) {
    console.error('[Map Presets] Error deleting preset:', err);
    alert(`Error deleting preset from server: ${err.message}`);
  }
}

function updateLegendCounts() {
  const counts = {};
  legend.forEach(item => {
    counts[item.value] = 0;
  });

  Object.values(gridData).forEach(val => {
    if (val !== undefined && val !== '') {
      counts[val] = (counts[val] || 0) + 1;
    }
  });

  legend.forEach(item => {
    const badge = document.getElementById(`legend-count-${item.value}`);
    if (badge) {
      const qty = counts[item.value] || 0;
      badge.textContent = qty;
      badge.style.color = qty > 0 ? 'var(--color-primary)' : 'var(--text-dim)';
    }
  });
}

// ----------------------------------------------------
// Rendering Functions
// ----------------------------------------------------

// ── 캔버스 테마 색 캐시 ─────────────────────────────────────
// 성능 규율: 렌더 루프(수만 셀)에서 getComputedStyle 호출 금지.
// 최초 1회 캐싱 후, 테마 전환(themechange) 시에만 재캐싱한다 (tokens.css --canvas-* 토큰).
let themeColors = null;

function rebuildThemeColorCache() {
  const cs = getComputedStyle(document.documentElement);
  const v = (name, fallback) => (cs.getPropertyValue(name) || '').trim() || fallback;
  themeColors = {
    outBg: v('--canvas-out-bg', '#e2e6ec'),               // 매트릭스/웨이퍼 밖 셀 배경
    line: v('--canvas-line', 'rgba(31, 39, 51, 0.10)'),   // 기본 격자선
    lineStrong: v('--canvas-line-strong', 'rgba(31, 39, 51, 0.16)'), // 원 내부 격자선
    insideEmpty: v('--canvas-inside-empty', 'rgba(23, 114, 69, 0.06)'), // 원 내부 빈 셀 채움
    textEmpty: v('--canvas-text-empty', 'rgba(71, 83, 107, 0.8)'),   // 좌표 표기(원 내부)
    textOut: v('--canvas-text-out', 'rgba(91, 103, 121, 0.45)'),     // 좌표 표기(원 외부)
    waferEdge: v('--canvas-wafer-edge', 'rgba(31, 39, 51, 0.7)'),    // 웨이퍼 외곽 원
    wmFront: v('--canvas-wm-front', 'rgba(26, 102, 208, 0.09)'),     // FRONT 워터마크
    wmBack: v('--canvas-wm-back', 'rgba(138, 90, 0, 0.09)'),         // BACK 워터마크
    accent: v('--accent', '#1a66d0'),
    success: v('--success', '#177245'),
    warning: v('--warning', '#8a5a00'),
    danger: v('--danger', '#c22f2f'),
    dangerWeak: v('--danger-weak', 'rgba(194, 47, 47, 0.15)'),
    rangeFill: v('--range-fill', 'rgba(26, 102, 208, 0.14)'),
    surface: v('--bg-surface', '#ffffff'),
  };
}

function getThemeColors() {
  if (!themeColors) rebuildThemeColorCache();
  return themeColors;
}

// 테마 전환 시: 색 캐시 재빌드 + 캔버스 1회 재렌더 (theme.js 'themechange' 구독)
document.addEventListener('themechange', () => {
  rebuildThemeColorCache();
  scheduleRenderGridCanvas();
});

let isRenderScheduled = false;

function scheduleRenderGridCanvas() {
  if (isRenderScheduled) return;
  isRenderScheduled = true;
  requestAnimationFrame(() => {
    isRenderScheduled = false;
    renderGridCanvas();
  });
}

// Update the FRONT/BACK indicator chip (DOM, outside the grid). Cheap; call directly
// on every side change so the label is instant even if the canvas re-render is throttled.
function updateSideIndicator() {
  if (!el.sideIndicator) return;
  const isBack = (currentSide === 'back');
  el.sideIndicator.textContent = isBack ? 'BACK · 뒷면' : 'FRONT · 앞면';
  el.sideIndicator.classList.toggle('side-back', isBack);
  el.sideIndicator.classList.toggle('side-front', !isBack);
}

// Size the (square) grid wrapper to fill the available workspace, then re-render.
// Square-fit avoids distorting the circular wafer; min(availW,availH) never overflows,
// so it won't fight the workspace scrollbars (no ResizeObserver feedback loop).
function fitGridToWorkspace() {
  const ws = el.mapWorkspace;
  const wrapper = el.gridWrapper;
  if (!ws || !wrapper) { scheduleRenderGridCanvas(); return; }
  const cs = getComputedStyle(ws);
  const padX = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight);
  const padY = parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom);
  const availW = ws.clientWidth - padX;
  const availH = ws.clientHeight - padY;
  const side = Math.max(200, Math.floor(Math.min(availW, availH)));
  wrapper.style.width = `${side}px`;
  wrapper.style.height = `${side}px`;
  scheduleRenderGridCanvas();
}

function renderGridCanvas() {
  if (!el.waferCanvas || !el.gridCanvas) return;

  const cols = parseInt(el.gridCols.value, 10) || 10;
  const rows = parseInt(el.gridRows.value, 10) || 10;
  const startX = parseInt(el.gridStartX.value, 10) || 0;
  const startY = parseInt(el.gridStartY.value, 10) || 0;
  const invertY = el.gridYInvert.checked;

  const isRotated90or270 = (currentRotation === 90 || currentRotation === 270);
  const visualCols = isRotated90or270 ? rows : cols;
  const visualRows = isRotated90or270 ? cols : rows;

  const box = getWaferBoundingBox(currentRotation, currentSide);
  const isXMirrored = (currentSide === 'back' && !isRotated90or270);
  const isYMirrored = (currentSide === 'back' && isRotated90or270);

  const c_zero = isXMirrored ? (box.maxC + startX) : (box.minC - startX);
  let r_zero = 0;
  if (!invertY) {
    r_zero = !isYMirrored ? (box.minR - startY) : (box.maxR + startY);
  } else {
    r_zero = !isYMirrored ? (box.maxR + startY) : (box.minR - startY);
  }
  const hasZeroZero = (c_zero >= 0 && c_zero < visualCols) && (r_zero >= 0 && r_zero < visualRows);

  gridCells2D = {};

  const rect = el.gridCanvas.getBoundingClientRect();
  const width = Math.floor(rect.width || 700);
  const height = Math.floor(rect.height || 700);

  if (width <= 0 || height <= 0) return;

  const dpr = window.devicePixelRatio || 1;
  el.waferCanvas.width = width * dpr;
  el.waferCanvas.height = height * dpr;

  const ctx = el.waferCanvas.getContext('2d');
  ctx.save();
  ctx.scale(dpr, dpr);

  ctx.clearRect(0, 0, width, height);

  // 테마 색 캐시 (렌더 루프 내 getComputedStyle 금지 — 캐시만 참조)
  const C = getThemeColors();

  const cellW = width / visualCols;
  const cellH = height / visualRows;

  const tStart = performance.now();

  const physConfig = getTransformedPhysicalConfig(currentRotation, currentSide);
  const showAnno = el.showAnnotations ? el.showAnnotations.checked : true;

  const colorMap = {};
  legend.forEach(item => {
    colorMap[item.value] = item.color;
  });

  const fontPx = Math.max(8, Math.min(13, Math.floor(cellH * 0.45)));
  ctx.font = `bold ${fontPx}px "JetBrains Mono", monospace`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';

  const { shiftX, shiftY } = getScreenShift(physConfig, cellW, cellH);

  const startC = Math.min(-visualCols, Math.floor(-shiftX / cellW) - 2);
  const endC = Math.max(2 * visualCols, Math.ceil((width - shiftX) / cellW) + 2);
  const startR = Math.min(-visualRows, Math.floor(-shiftY / cellH) - 2);
  const endR = Math.max(2 * visualRows, Math.ceil((height - shiftY) / cellH) + 2);

  for (let r = startR; r <= endR; r++) {
    for (let c = startC; c <= endC; c++) {
      const x0 = c * cellW + shiftX;
      const y0 = r * cellH + shiftY;

      if (x0 + cellW < 0 || x0 > width || y0 + cellH < 0 || y0 > height) continue;

      const completelyInside = isCellInsideWaferFast(c, r, visualCols, visualRows, physConfig, width, height);
      const isMatrixCell = completelyInside || (c >= -visualCols && c < 2 * visualCols && r >= -visualRows && r < 2 * visualRows);

      if (!isMatrixCell) {
        ctx.fillStyle = C.outBg;
        ctx.fillRect(x0, y0, cellW, cellH);
        ctx.strokeStyle = C.line;
        ctx.lineWidth = 0.5;
        ctx.strokeRect(x0, y0, cellW, cellH);
        continue;
      }

      const physical = getPhysicalCoords(c, r, cols, rows, currentRotation, currentSide);
      const visual = getVisualCoords(c, r, cols, rows, currentRotation, currentSide, invertY, startX, startY);
      const coordKey = `${physical.x}_${physical.y}`;
      const val = gridData[coordKey] || '';

      const isOriginCell = hasZeroZero 
        ? (visual.x === 0 && visual.y === 0) 
        : (visual.x === startX && visual.y === startY);

      const cellObj = {
        c, r, x: visual.x, y: visual.y, px: physical.x, py: physical.y,
        key: coordKey, inside: completelyInside, isOrigin: isOriginCell
      };
      if (!gridCells2D[r]) gridCells2D[r] = {};
      gridCells2D[r][c] = cellObj;

      // 1. Fill cell background
      if (!completelyInside) {
        ctx.fillStyle = C.outBg;
      } else if (val !== '') {
        // 범례 색은 사용자 데이터(테마 불변) — 미등록 값만 기본 범례색 폴백
        ctx.fillStyle = colorMap[val] || '#10b981';
      } else {
        ctx.fillStyle = C.insideEmpty;
      }
      ctx.fillRect(x0, y0, cellW, cellH);

      // 2. Stroke grid border across ALL cells (inside and outside wafer)
      ctx.strokeStyle = completelyInside ? C.lineStrong : C.line;
      ctx.lineWidth = 0.5;
      ctx.strokeRect(x0, y0, cellW, cellH);

      // 3. Wafer inside boundary cell outline
      if (completelyInside) {
        ctx.strokeStyle = C.success;
        ctx.lineWidth = 1.2;
        ctx.strokeRect(x0 + 0.5, y0 + 0.5, cellW - 1, cellH - 1);
      }

      // 4. Origin cell highlight
      if (isOriginCell) {
        ctx.fillStyle = C.dangerWeak;
        ctx.fillRect(x0, y0, cellW, cellH);
        ctx.strokeStyle = C.danger;
        ctx.lineWidth = 2.0;
        ctx.strokeRect(x0 + 1, y0 + 1, cellW - 2, cellH - 2);
      }

      // 5. Annotations text (Dynamic font size fitting)
      const textToDraw = val !== '' ? String(val) : (showAnno ? `${visual.x},${visual.y}` : '');
      if (textToDraw) {
        const len = textToDraw.length;
        const maxFontW = (cellW * 0.85) / Math.max(1, len * 0.58);
        const maxFontH = cellH * 0.35;
        const fontPx = Math.max(5, Math.min(12, Math.floor(Math.min(maxFontW, maxFontH))));

        ctx.font = `bold ${fontPx}px "JetBrains Mono", monospace`;
        // 값 셀 텍스트: 채도 높은 범례색 위 흰색 고정(테마 불변), 좌표 표기: 테마 토큰
        ctx.fillStyle = val !== '' ? '#ffffff' : (completelyInside ? C.textEmpty : C.textOut);
        ctx.fillText(textToDraw, x0 + cellW / 2, y0 + cellH / 2);
      }
    }
  }

  // 6. Physical Wafer Circles (FIXED at Wafer Center 0,0 at Canvas Center)
  const waferCenterX = width / 2.0;
  const waferCenterY = height / 2.0;

  // A. White Outer Silicon Wafer Edge Circle (Full Diameter, e.g. 300mm)
  const outerRadX = ((physConfig.waferDia / 2.0) / physConfig.chipX) * cellW;
  const outerRadY = ((physConfig.waferDia / 2.0) / physConfig.chipY) * cellH;

  ctx.beginPath();
  if (typeof ctx.ellipse === 'function') {
    ctx.ellipse(waferCenterX, waferCenterY, outerRadX, outerRadY, 0, 0, 2 * Math.PI);
  } else {
    ctx.arc(waferCenterX, waferCenterY, outerRadX, 0, 2 * Math.PI);
  }
  ctx.strokeStyle = C.waferEdge;
  ctx.lineWidth = 2.0;
  ctx.stroke();

  // B. Green Edge Exclusion Boundary Circle (Effective Radius, e.g. 147mm = 150mm - Edge Exclusion)
  const effRadX = (physConfig.effectiveRadius / physConfig.chipX) * cellW;
  const effRadY = (physConfig.effectiveRadius / physConfig.chipY) * cellH;

  ctx.beginPath();
  if (typeof ctx.ellipse === 'function') {
    ctx.ellipse(waferCenterX, waferCenterY, effRadX, effRadY, 0, 0, 2 * Math.PI);
  } else {
    ctx.arc(waferCenterX, waferCenterY, effRadX, 0, 2 * Math.PI);
  }
  ctx.strokeStyle = C.success;
  ctx.lineWidth = 2.0;
  ctx.setLineDash([6, 4]);
  ctx.stroke();
  ctx.setLineDash([]);

  // C. Centering Offset Marker Point (Drawn at center of shifted chip grid array)
  const gridCenterX = waferCenterX + shiftX;
  const gridCenterY = waferCenterY + shiftY;
  if (physConfig.offsetX !== 0 || physConfig.offsetY !== 0) {
    ctx.beginPath();
    ctx.arc(gridCenterX, gridCenterY, 4, 0, 2 * Math.PI);
    ctx.fillStyle = C.warning;
    ctx.fill();
    ctx.strokeStyle = C.surface;
    ctx.lineWidth = 1.0;
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(gridCenterX - 8, gridCenterY);
    ctx.lineTo(gridCenterX + 8, gridCenterY);
    ctx.moveTo(gridCenterX, gridCenterY - 8);
    ctx.lineTo(gridCenterX, gridCenterY + 8);
    ctx.strokeStyle = C.warning;
    ctx.lineWidth = 1.2;
    ctx.stroke();
  }

  // 7. Selection Box overlay
  if (isBoxDragging && lastSelectionBox) {
    const { minC, maxC, minR, maxR } = lastSelectionBox;
    const boxX = minC * cellW + shiftX;
    const boxY = minR * cellH + shiftY;
    const boxW = (maxC - minC + 1) * cellW;
    const boxH = (maxR - minR + 1) * cellH;

    const isErase = (dragType === 'erase');
    ctx.fillStyle = isErase ? C.dangerWeak : C.rangeFill;
    ctx.fillRect(boxX, boxY, boxW, boxH);

    ctx.strokeStyle = isErase ? C.danger : C.accent;
    ctx.lineWidth = 2.0;
    ctx.strokeRect(boxX + 1, boxY + 1, boxW - 2, boxH - 2);
  }

  // 8. Hover Cell highlight
  if (currentHoverCell && !isBoxDragging) {
    const hX = currentHoverCell.c * cellW + shiftX;
    const hY = currentHoverCell.r * cellH + shiftY;
    ctx.strokeStyle = C.accent;
    ctx.lineWidth = 2.0;
    ctx.strokeRect(hX + 1, hY + 1, cellW - 2, cellH - 2);
  }

  // 9. FRONT / BACK translucent watermark (display-only overlay, centered)
  //    Faint large label showing the current observation side. Purely visual:
  //    it draws centered text only and touches NO cell data / gridCells2D / hit-test,
  //    so it never affects mouse->cell mapping. Font/alignment state is isolated
  //    via save/restore so it doesn't leak into the next render pass.
  //    FRONT = sky blue, BACK = amber (matches the DOM #side-indicator chip).
  {
    const isBack = (currentSide === 'back');
    const sideWord = isBack ? 'BACK' : 'FRONT';
    const wmColor = isBack ? C.wmBack : C.wmFront;
    const wmFont = Math.max(40, Math.floor(width * 0.16));

    ctx.save();
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.font = `900 ${wmFont}px "JetBrains Mono", monospace`;
    ctx.fillStyle = wmColor;
    ctx.fillText(sideWord, width / 2, height / 2);
    ctx.restore();
  }

  ctx.restore();

  updateNotchPosition();
  updateLegendCounts();
}

function handleCellClick(cell, event) {
  if (!cell) return;
  const c = cell.c !== undefined ? cell.c : 0;
  const r = cell.r !== undefined ? cell.r : 0;
  const key = cell.key;

  if (isProtectedFCell(key)) {
    return;
  }

  if (isOriginMode) {
    const box = getWaferBoundingBox(currentRotation, currentSide);
    const invertY = el.gridYInvert ? el.gridYInvert.checked : false;

    const newStartX = box.minC - c;
    const newStartY = !invertY ? (box.minR - r) : (r - box.maxR);

    el.gridStartX.value = newStartX;
    el.gridStartY.value = newStartY;

    isOriginMode = false;
    el.btnSetOrigin.classList.remove('active');
    el.btnSetOrigin.style.borderColor = '';
    el.btnSetOrigin.style.color = '';
    el.gridCanvas.classList.remove('origin-mode-active');

    scheduleRenderGridCanvas();
    return;
  }

  let isRight = isRightDrag;
  if (event) {
    isRight = (event.button === 2 || event.buttons === 2);
  }

  if (isRight) {
    gridData[key] = '';
  } else {
    if (activeBrush !== undefined && activeBrush !== null) {
      const existingVal = gridData[key] || '';
      if (!event && existingVal !== '') {
        return;
      }
      gridData[key] = activeBrush;
    }
  }

  updateLegendCounts();
  scheduleRenderGridCanvas();
}

function updateCellStyles(cell, val) {
  const match = legend.find(item => item.value === val);
  if (match && val !== '') {
    cell.style.backgroundColor = match.color;
    cell.style.borderColor = 'var(--border-strong)';
  } else {
    cell.style.backgroundColor = 'var(--bg-inset)';
    cell.style.borderColor = 'var(--border)';
  }
}

// ----------------------------------------------------
// V-Notch Orientation & Offsets
// ----------------------------------------------------
function updateNotchPosition() {
  if (!el.gridNotch) return;

  el.gridNotch.className = 'wafer-notch';
  el.gridNotch.textContent = 'D';

  let positionClass = '';
  if (currentRotation === 0) positionClass = 'notch-bottom';
  else if (currentRotation === 90) positionClass = 'notch-left';
  else if (currentRotation === 180) positionClass = 'notch-top';
  else if (currentRotation === 270) positionClass = 'notch-right';
  el.gridNotch.classList.add(positionClass);

  const offset = 24; // px shift
  el.gridNotch.style.left = '';
  el.gridNotch.style.right = '';
  el.gridNotch.style.top = '';
  el.gridNotch.style.bottom = '';
  el.gridNotch.style.transform = '';

  const dx = (currentSide === 'front') ? 1 : -1;
  let screenDx = 0;
  let screenDy = 0;

  if (currentRotation === 0) { screenDx = dx; screenDy = 0; }
  else if (currentRotation === 90) { screenDx = 0; screenDy = dx; }
  else if (currentRotation === 180) { screenDx = -dx; screenDy = 0; }
  else if (currentRotation === 270) { screenDx = 0; screenDy = -dx; }

  if (currentRotation === 0) { // Bottom
    el.gridNotch.style.bottom = '2px';
    const shift = screenDx * offset;
    el.gridNotch.style.left = `calc(50% + ${shift}px)`;
    el.gridNotch.style.transform = 'translateX(-50%)';
  } else if (currentRotation === 180) { // Top
    el.gridNotch.style.top = '2px';
    const shift = screenDx * offset;
    el.gridNotch.style.left = `calc(50% + ${shift}px)`;
    el.gridNotch.style.transform = 'translateX(-50%)';
  } else if (currentRotation === 90) { // Left
    el.gridNotch.style.left = '2px';
    const shift = screenDy * offset;
    el.gridNotch.style.top = `calc(50% + ${shift}px)`;
    el.gridNotch.style.transform = 'translateY(-50%)';
  } else if (currentRotation === 270) { // Right
    el.gridNotch.style.right = '2px';
    const shift = screenDy * offset;
    el.gridNotch.style.top = `calc(50% + ${shift}px)`;
    el.gridNotch.style.transform = 'translateY(-50%)';
  }
}

// ----------------------------------------------------
// Legend / Palette Management
// ----------------------------------------------------
function loadLegendFromStorage() {
  const stored = localStorage.getItem(`map_legend_${selectedTable}`);
  if (stored) {
    try {
      legend = JSON.parse(stored);
    } catch (e) {
      legend = [...DEFAULT_LEGEND];
    }
  } else {
    legend = [...DEFAULT_LEGEND];
  }
  if (legend.length > 0) {
    activeBrush = legend[0].value;
  } else {
    activeBrush = '';
  }
}

function saveLegendToStorage() {
  localStorage.setItem(`map_legend_${selectedTable}`, JSON.stringify(legend));
}

// ── Split Registry 서버 IO ──────────────────────────

// 현재 메타 입력값들로 맵 식별자(map_key) 해석 — 미입력이면 null (push 시 일괄 저장으로 미룸)
function getCurrentMapKey() {
  const dict = {};
  document.querySelectorAll('[id^="meta-input-"]').forEach(input => {
    const col = input.id.replace('meta-input-', '');
    const val = input.value.trim();
    if (val !== '') dict[col] = val;
  });
  if (Object.keys(dict).length === 0) return null;
  const mapKey = getMapIdFromMeta(dict);
  return (mapKey && mapKey !== 'default_map') ? mapKey : null;
}

async function fetchLegendFromServer(refTable, mapKey) {
  const filters = { ref_table: { filterType: 'text', type: 'equals', filter: refTable } };
  if (mapKey) filters.map_key = { filterType: 'text', type: 'equals', filter: mapKey };
  const url = `${API_BASE}/tables/${SPLIT_REGISTRY_TABLE}/data?limit=500&filters=${encodeURIComponent(JSON.stringify(filters))}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`split registry fetch failed (HTTP ${res.status})`);
  const result = await res.json();
  return parseLegendRegistryRows(result, !mapKey);
}

// legend 로드 오케스트레이터: 서버 registry 우선 → localStorage 캐시 폴백 → DEFAULT
async function loadLegend(refTable, mapKey) {
  legendMeta = {};
  try {
    const rows = await fetchLegendFromServer(refTable, mapKey);
    if (rows.length > 0) {
      legend = rows.map(r => ({ value: r.value, desc: r.desc, color: r.color }));
      rows.forEach(r => { legendMeta[r.value] = { updated_by: r.updated_by, updated_at: r.updated_at }; });
      activeBrush = legend[0].value;
      saveLegendToStorage(); // 서버 로드 성공 시 오프라인 캐시 동기화
      return 'server';
    }
    loadLegendFromStorage(); // 서버 접근 성공, 등록 행 없음 → 캐시 폴백
    return 'local';
  } catch (e) {
    console.warn('[Map Editor] split registry load failed — localStorage fallback:', e);
    loadLegendFromStorage();
    return 'offline';
  }
}

// legend 전체를 registry에 업서트. map_key 미확정이면 조용히 스킵(false).
async function saveLegendToServer(mapKeyOverride) {
  const mapKey = mapKeyOverride || getCurrentMapKey();
  if (!selectedTable || !mapKey) return false;
  const updates = buildLegendRegistryUpdates(selectedTable, mapKey, legend, CURRENT_USER, getLocalTimeString());
  if (updates.length === 0) return false;
  try {
    const res = await fetch(`${API_BASE}/tables/${SPLIT_REGISTRY_TABLE}/data/updates`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ updates })
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const nowStr = getLocalTimeString();
    legend.forEach(item => {
      legendMeta[item.value] = { updated_by: CURRENT_USER, updated_at: nowStr };
    });
    renderLegendMetaOnly();
    return true;
  } catch (e) {
    console.warn('[Map Editor] split registry save skipped (offline?):', e);
    return false;
  }
}

// 입력 도중 포커스를 깨지 않도록 디바운스 서버 저장
function scheduleLegendServerSave() {
  clearTimeout(legendServerSaveTimer);
  legendServerSaveTimer = setTimeout(() => { saveLegendToServer(); }, 800);
}

// legend 변조의 단일 영속화 관문: 캐시 즉시 + 서버 디바운스
function persistLegend() {
  saveLegendToStorage();
  scheduleLegendServerSave();
}

// 행 DOM을 유지한 채 수정자·시각 라인만 갱신 (textarea 포커스 보존)
function renderLegendMetaOnly() {
  if (!el.legendList) return;
  el.legendList.querySelectorAll('.legend-row').forEach(row => {
    const line = row.querySelector('.legend-meta-line');
    if (line) line.textContent = formatLegendMetaText(legendMeta[row.dataset.value]);
  });
}

// 1회 마이그레이션: 서버 registry가 비어 있고 localStorage legend가 있으면 업로드 제안
async function maybeOfferLegendMigration(refTable, mapKey) {
  if (!refTable || !mapKey) return;
  const migFlag = `map_split_migrated_${refTable}${SPLIT_KEY_SEP}${mapKey}`;
  if (localStorage.getItem(migFlag)) return;
  const stored = localStorage.getItem(`map_legend_${refTable}`);
  if (!stored) return;
  let localLegend = [];
  try { localLegend = JSON.parse(stored); } catch (e) { return; }
  if (!Array.isArray(localLegend) || localLegend.length === 0) return;
  localStorage.setItem(migFlag, '1'); // 수락 여부와 무관하게 1회만 제안
  const ok = confirm(
    `이 맵(${mapKey})의 legend ${localLegend.length}건이 브라우저(localStorage)에만 저장되어 있습니다.\n` +
    `서버 split registry로 업로드하여 팀과 공유하시겠습니까?`
  );
  if (!ok) return;
  const saved = await saveLegendToServer(mapKey);
  if (saved) showToast('로컬 legend를 서버 split registry로 마이그레이션했습니다.', 'success');
  else showToast('legend 마이그레이션 실패 — 서버 연결을 확인하십시오.', 'error');
}

function renderLegendTable() {
  el.legendList.innerHTML = '';
  legend.forEach((item, index) => {
    const row = document.createElement('tr');
    row.className = 'legend-row';
    row.dataset.value = item.value;
    if (activeBrush === item.value) {
      row.classList.add('legend-row-active');
      el.activeBrushVal.textContent = `${item.value} (${item.desc})`;
      el.activeBrushVal.style.color = item.color;
    }

    row.addEventListener('click', (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.classList.contains('btn-delete')) return;
      selectBrush(item.value);
    });

    // Value column
    const tdVal = document.createElement('td');
    const inputVal = document.createElement('input');
    inputVal.type = 'text';
    inputVal.className = 'glass-input';
    inputVal.style.padding = '6px 10px';
    inputVal.style.fontSize = '0.9rem';
    inputVal.style.width = '100%';
    inputVal.value = item.value;
    inputVal.addEventListener('change', (e) => {
      const oldVal = item.value;
      const newVal = e.target.value.trim();
      if (!newVal) {
        inputVal.value = oldVal;
        return;
      }
      // Check duplicate values
      const exists = legend.some((l, idx) => idx !== index && l.value === newVal);
      if (exists) {
        alert('중복된 범례 값이 존재합니다.');
        inputVal.value = oldVal;
        return;
      }
      item.value = newVal;
      // Remap grid values from oldVal to newVal
      remapGridValues(oldVal, newVal);
      if (activeBrush === oldVal) {
        activeBrush = newVal;
        row.dataset.value = newVal;
        el.activeBrushVal.textContent = `${newVal} (${item.desc})`;
      } else {
        row.dataset.value = newVal;
      }
      // 값 rename = registry에는 신규 bk 행 생성 (구 값 행은 서버에 이력으로 잔존)
      delete legendMeta[oldVal];
      persistLegend();
      renderGridCanvas();
    });
    tdVal.appendChild(inputVal);

    // Description column — 자연어 split 조건 서술 (여러 줄 textarea, 자동 확장)
    const tdDesc = document.createElement('td');
    const inputDesc = document.createElement('textarea');
    inputDesc.className = 'glass-input legend-desc-input';
    inputDesc.rows = 1;
    inputDesc.placeholder = '실험 split 조건 서술…';
    inputDesc.style.padding = '6px 10px';
    inputDesc.style.fontSize = '0.9rem';
    inputDesc.style.width = '100%';
    inputDesc.style.resize = 'none';
    inputDesc.style.overflow = 'hidden';
    inputDesc.style.lineHeight = '1.4';
    inputDesc.style.fontFamily = 'inherit';
    inputDesc.style.display = 'block';
    inputDesc.value = item.desc;
    const autoGrowDesc = () => {
      inputDesc.style.height = 'auto';
      inputDesc.style.height = `${Math.min(Math.max(inputDesc.scrollHeight, 32), 120)}px`;
    };
    inputDesc.addEventListener('input', autoGrowDesc);
    inputDesc.addEventListener('focus', autoGrowDesc);
    requestAnimationFrame(autoGrowDesc);
    inputDesc.addEventListener('change', (e) => {
      item.desc = e.target.value.trim();
      persistLegend();
      if (activeBrush === item.value) {
        el.activeBrushVal.textContent = `${item.value} (${item.desc})`;
      }
    });
    tdDesc.appendChild(inputDesc);

    // 마지막 수정자·시각 (서버 registry 메타 — 미저장 시 '서버 미저장')
    const metaLine = document.createElement('div');
    metaLine.className = 'legend-meta-line';
    metaLine.style.fontSize = '0.7rem';
    metaLine.style.color = 'var(--text-muted)';
    metaLine.style.marginTop = '3px';
    metaLine.style.whiteSpace = 'nowrap';
    metaLine.style.overflow = 'hidden';
    metaLine.style.textOverflow = 'ellipsis';
    metaLine.textContent = formatLegendMetaText(legendMeta[item.value]);
    tdDesc.appendChild(metaLine);

    // Color indicator and Picker column
    const tdColor = document.createElement('td');
    tdColor.style.textAlign = 'center';
    
    const colorIndicator = document.createElement('span');
    colorIndicator.className = 'legend-color-indicator';
    colorIndicator.style.backgroundColor = item.color;
    
    // Hidden color picker
    const colorInput = document.createElement('input');
    colorInput.type = 'color';
    colorInput.className = 'legend-color-input';
    colorInput.style.display = 'none';
    colorInput.value = item.color;
    
    colorIndicator.addEventListener('click', () => colorInput.click());
    colorInput.addEventListener('input', (e) => {
      const col = e.target.value;
      item.color = col;
      colorIndicator.style.backgroundColor = col;
      if (activeBrush === item.value) {
        el.activeBrushVal.style.color = col;
      }
      persistLegend();
      renderGridCanvas();
    });

    tdColor.appendChild(colorIndicator);
    tdColor.appendChild(colorInput);

    // Delete column
    const tdDel = document.createElement('td');
    const btnDel = document.createElement('button');
    btnDel.className = 'glass-page-btn btn-delete hover-danger';
    btnDel.style.padding = '2px 6px';
    btnDel.innerHTML = '&times;';
    btnDel.addEventListener('click', () => {
      if (legend.length <= 1) {
        alert('최소 하나의 범례 정의가 필요합니다.');
        return;
      }
      const deletedVal = item.value;
      legend.splice(index, 1);
      delete legendMeta[deletedVal]; // 서버 registry 행은 이력으로 잔존 (삭제 API 미사용)
      persistLegend();
      // Remove all elements in gridData matching deleted value
      Object.keys(gridData).forEach(k => {
        if (gridData[k] === deletedVal) gridData[k] = '';
      });
      if (activeBrush === deletedVal) {
        activeBrush = legend[0].value;
      }
      renderLegendTable();
      renderGridCanvas();
    });
    tdDel.appendChild(btnDel);

    // Count column
    const tdCount = document.createElement('td');
    tdCount.style.textAlign = 'center';
    tdCount.style.fontWeight = 'bold';
    tdCount.id = `legend-count-${item.value}`;
    tdCount.textContent = '0';
    tdCount.style.color = 'var(--text-muted)';

    row.appendChild(tdVal);
    row.appendChild(tdDesc);
    row.appendChild(tdCount);
    row.appendChild(tdColor);
    row.appendChild(tdDel);

    el.legendList.appendChild(row);
  });
  updateLegendCounts();
}

function selectBrush(val) {
  activeBrush = val;
  
  // Find matching legend item
  const item = legend.find(l => l.value === val);
  if (item) {
    el.activeBrushVal.textContent = `${item.value} (${item.desc})`;
    el.activeBrushVal.style.color = item.color;
  } else {
    el.activeBrushVal.textContent = 'None';
    el.activeBrushVal.style.color = 'var(--text-dim)';
  }

  // Toggle active styling on existing row elements without tearing down DOM
  const rows = el.legendList.querySelectorAll('.legend-row');
  rows.forEach(row => {
    if (row.dataset.value === val) {
      row.classList.add('legend-row-active');
    } else {
      row.classList.remove('legend-row-active');
    }
  });
}

function addNewLegendRow() {
  // Find a unique value name
  let nextVal = 1;
  while (legend.some(item => item.value === String(nextVal))) {
    nextVal++;
  }
  
  const colors = ['#3b82f6', '#ec4899', '#14b8a6', '#f43f5e', '#8b5cf6', '#06b6d4'];
  const nextColor = colors[legend.length % colors.length];

  legend.push({
    value: String(nextVal),
    desc: '',
    color: nextColor
  });

  persistLegend();
  renderLegendTable();
}

function remapGridValues(oldVal, newVal) {
  Object.keys(gridData).forEach(k => {
    if (isProtectedFCell(k)) return;
    if (gridData[k] === oldVal) {
      gridData[k] = newVal;
    }
  });
}

// ----------------------------------------------------
// Load Map & Grid Actions
// ----------------------------------------------------
async function loadExistingMap() {
  const filterModel = {};
  const metaInputs = document.querySelectorAll('[id^="meta-input-"]');
  let hasFilter = false;

  metaInputs.forEach(input => {
    const col = input.id.replace('meta-input-', '');
    const val = input.value.trim();
    if (val) {
      hasFilter = true;
      filterModel[col] = {
        filterType: 'text',
        type: 'equals',
        filter: val
      };
    }
  });

  if (!hasFilter) {
    alert('기존 맵 데이터를 로드하기 위해 하나 이상의 메타데이터 필드 값을 입력하십시오.');
    return;
  }

  const xCol = el.colMapX.value;
  const yCol = el.colMapY.value;
  const valCol = el.colMapVal.value;

  el.btnLoadMap.textContent = '📂 Loading...';
  el.btnLoadMap.disabled = true;

  const url = `${API_BASE}/tables/${selectedTable}/data?limit=2000&filters=${encodeURIComponent(JSON.stringify(filterModel))}`;

  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error('API fetch failed');
    const result = await res.json();

    // Reset local cache & loaded F cells protection set
    gridData = {};
    loadedFCells.clear();
    let count = 0;
    
    // Pre-calculate coordinate bounds first
    let maxX = -9999;
    let maxY = -9999;
    let minX = 9999;
    let minY = 9999;

    if (result && result.data) {
      result.data.forEach(row => {
        const rowData = row.data || {};
        const xVal = rowData[xCol]?.value;
        const yVal = rowData[yCol]?.value;
        if (xVal !== undefined && yVal !== undefined) {
          const xNum = parseInt(xVal, 10);
          const yNum = parseInt(yVal, 10);
          if (!isNaN(xNum) && !isNaN(yNum)) {
            if (xNum > maxX) maxX = xNum;
            if (yNum > maxY) maxY = yNum;
            if (xNum < minX) minX = xNum;
            if (yNum < minY) minY = yNum;
          }
        }
      });
    }

    let loadedGridMeta = null;
    let loadedMapKey = null; // split registry 적용을 위해 맵 식별자를 함수 스코프로 유지

    // 1. Try fetching from dedicated wafer_map_metadata table
    try {
      const filterMetaDict = {};
      Object.keys(filterModel).forEach(col => {
        if (filterModel[col] && filterModel[col].filter) {
          filterMetaDict[col] = filterModel[col].filter;
        }
      });
      const mapIdStr = getMapIdFromMeta(filterMetaDict);
      if (mapIdStr && mapIdStr !== 'default_map') {
        loadedMapKey = mapIdStr;
        const metaFilter = {
          map_id: { filterType: 'text', type: 'equals', filter: mapIdStr }
        };
        const metaRes = await fetch(`${API_BASE}/tables/wafer_map_metadata/data?limit=1&filters=${encodeURIComponent(JSON.stringify(metaFilter))}`);
        if (metaRes.ok) {
          const metaResult = await metaRes.json();
          if (metaResult && metaResult.data && metaResult.data.length > 0) {
            const metaRow = metaResult.data[0].data || {};
            const metaStr = metaRow['grid_metadata']?.value;
            if (metaStr) {
              loadedGridMeta = JSON.parse(metaStr);
            }
          }
        }
      }
    } catch (e) {
      console.warn('[Map Editor] Dedicated wafer_map_metadata table fetch skipped:', e);
    }

    // 2. Fallback to cell-level grid_metadata
    if (!loadedGridMeta && result && result.data) {
      const firstWithMeta = result.data.find(row => row.data && row.data['grid_metadata'] && row.data['grid_metadata'].value);
      if (firstWithMeta) {
        try {
          loadedGridMeta = JSON.parse(firstWithMeta.data['grid_metadata'].value);
        } catch (e) {
          console.error('Failed to parse fallback grid_metadata:', e);
        }
      }
    }

    let userChoice = null; // 'standard' | 'current' | 'meta'

    if (!loadedGridMeta && minX !== 9999) {
      // Choice modal triggers for maps with no grid metadata records
      userChoice = await new Promise((resolve) => {
        el.choiceModal.style.display = 'flex';
        
        const onStandard = () => {
          cleanup();
          resolve('standard');
        };
        const onCurrent = () => {
          cleanup();
          resolve('current');
        };
        const onCancel = () => {
          cleanup();
          resolve('cancel');
        };

        const cleanup = () => {
          el.choiceModal.style.display = 'none';
          el.btnChoiceStandard.removeEventListener('click', onStandard);
          el.btnChoiceCurrent.removeEventListener('click', onCurrent);
          el.btnChoiceCancel.removeEventListener('click', onCancel);
        };

        el.btnChoiceStandard.addEventListener('click', onStandard);
        el.btnChoiceCurrent.addEventListener('click', onCurrent);
        el.btnChoiceCancel.addEventListener('click', onCancel);
      });

      if (userChoice === 'cancel') {
        el.btnLoadMap.textContent = '📂 Load Existing Map';
        el.btnLoadMap.disabled = false;
        return;
      }
    } else if (loadedGridMeta) {
      userChoice = 'meta';
    } else {
      userChoice = 'current';
    }

    // Determine grid properties based on choice
    let cols, rows, startX, startY, invertY, rotation, side;

    if (userChoice === 'standard') {
      cols = (maxX >= minX) ? (maxX - minX + 1) : 10;
      rows = (maxY >= minY) ? (maxY - minY + 1) : 10;
      startX = 0;
      startY = 0;
      invertY = false;
      rotation = 0;
      side = 'front';
    } else if (userChoice === 'meta') {
      cols = loadedGridMeta.grid_cols;
      rows = loadedGridMeta.grid_rows;
      startX = loadedGridMeta.grid_start_x;
      startY = loadedGridMeta.grid_start_y;
      invertY = loadedGridMeta.grid_y_invert;
      rotation = loadedGridMeta.rotation || 0;
      side = loadedGridMeta.side || 'front';

      if (loadedGridMeta.phys_wafer_dia !== undefined && el.physWaferDia) el.physWaferDia.value = loadedGridMeta.phys_wafer_dia;
      if (loadedGridMeta.phys_chip_x !== undefined && el.physChipX) el.physChipX.value = loadedGridMeta.phys_chip_x;
      if (loadedGridMeta.phys_chip_y !== undefined && el.physChipY) el.physChipY.value = loadedGridMeta.phys_chip_y;
      if (loadedGridMeta.phys_offset_x !== undefined && el.physOffsetX) el.physOffsetX.value = loadedGridMeta.phys_offset_x;
      if (loadedGridMeta.phys_offset_y !== undefined && el.physOffsetY) el.physOffsetY.value = loadedGridMeta.phys_offset_y;
      if (loadedGridMeta.phys_edge_margin !== undefined && el.physEdgeMargin) el.physEdgeMargin.value = loadedGridMeta.phys_edge_margin;

      boundingBoxCache = {};
    } else {
      // Use current UI settings
      cols = parseInt(el.gridCols.value, 10) || 10;
      rows = parseInt(el.gridRows.value, 10) || 10;
      startX = parseInt(el.gridStartX.value, 10) || 0;
      startY = parseInt(el.gridStartY.value, 10) || 0;
      invertY = el.gridYInvert.checked;
      rotation = currentRotation;
      side = currentSide;
    }

    // Sync state variables and input values back to UI panel BEFORE mapping cell coordinates
    el.gridCols.value = cols;
    el.gridRows.value = rows;
    el.gridStartX.value = startX;
    el.gridStartY.value = startY;
    el.gridYInvert.checked = invertY;
    currentRotation = rotation;
    currentSide = side;
    boundingBoxCache = {}; // Invalidate bounding box cache so getWaferBoundingBox calculates with new dimensions

    // Update Side Radio UI
    document.querySelectorAll('input[name="wafer-side"]').forEach(radio => {
      if (radio.value === currentSide) {
        radio.checked = true;
      }
    });

    // Update Rotation Buttons UI
    document.querySelectorAll('.btn-rot').forEach(btn => {
      const rotVal = parseInt(btn.dataset.rot, 10);
      if (rotVal === currentRotation) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });

    const uniqueVals = new Set();

    if (result && result.data) {
      result.data.forEach(row => {
        const rowData = row.data || {};
        const xVal = rowData[xCol]?.value;
        const yVal = rowData[yCol]?.value;
        const val = rowData[valCol]?.value;

        if (xVal !== undefined && yVal !== undefined) {
          let xNum = parseInt(xVal, 10);
          let yNum = parseInt(yVal, 10);
          if (!isNaN(xNum) && !isNaN(yNum)) {
            const strVal = val !== null ? String(val).trim() : '';
            count++;

            if (strVal !== '') {
              uniqueVals.add(strVal);
            }

            // If standard system was selected, shift coordinates so minX, minY maps to 0,0
            if (userChoice === 'standard') {
              xNum = xNum - minX;
              yNum = yNum - minY;
            }

            const cell = getCellFromVisualCoords(xNum, yNum, cols, rows, rotation, side, invertY, startX, startY);
            const c = cell.c;
            const r = cell.r;

            const physical = getPhysicalCoords(c, r, cols, rows, rotation, side);
            const gridKey = `${physical.x}_${physical.y}`;
            gridData[gridKey] = strVal;

            if (strVal === 'F') {
              loadedFCells.add(gridKey);
            }
          }
        }
      });
    }

    // Auto detect legend from unique values
    if (uniqueVals.size > 0) {
      const predefinedColors = ['#10b981', '#ef4444', '#3b82f6', '#ec4899', '#f59e0b', '#8b5cf6', '#14b8a6', '#f43f5e', '#06b6d4', '#84cc16', '#a855f7', '#6b7280'];
      const newLegend = [];
      const usedColors = new Set();

      // First, try to match and preserve existing legend items
      uniqueVals.forEach(v => {
        const existingItem = legend.find(item => item.value === v);
        if (existingItem) {
          newLegend.push(existingItem);
          usedColors.add(existingItem.color);
        }
      });

      // For new unique values, assign description and unique color
      let colorIdx = 0;
      uniqueVals.forEach(v => {
        const exists = newLegend.some(item => item.value === v);
        if (!exists) {
          // Find next unused color from predefined colors list
          let chosenColor = '';
          while (colorIdx < predefinedColors.length) {
            const candidate = predefinedColors[colorIdx++];
            if (!usedColors.has(candidate)) {
              chosenColor = candidate;
              break;
            }
          }
          if (!chosenColor) {
            // Fallback to random color if all predefined are used
            chosenColor = '#' + Math.floor(Math.random()*16777215).toString(16).padStart(6, '0');
          }
          
          usedColors.add(chosenColor);
          newLegend.push({
            value: v,
            desc: v === '1' ? 'GOOD' : (v === '0' ? 'FAIL' : `BIN ${v}`),
            color: chosenColor
          });
        }
      });

      // Update legend array, save to localStorage and rebuild legend table
      legend = newLegend;
      saveLegendToStorage();
      
      // Auto select the first legend item as the active brush
      if (legend.length > 0) {
        activeBrush = legend[0].value;
      } else {
        activeBrush = '';
      }
      renderLegendTable();
    }

    // [Split Registry] 서버에 기록된 이 맵의 split 서술·색을 최우선 적용.
    // 값 일치 항목은 override, 그리드에 없지만 registry에 정의된 값은 브러시로 추가 노출.
    if (loadedMapKey) {
      try {
        const regRows = await fetchLegendFromServer(selectedTable, loadedMapKey);
        if (regRows.length > 0) {
          const byValue = new Map(regRows.map(r => [r.value, r]));
          legendMeta = {};
          legend.forEach(item => {
            const r = byValue.get(String(item.value));
            if (r) {
              if (r.desc) item.desc = r.desc;
              if (r.color) item.color = r.color;
              legendMeta[item.value] = { updated_by: r.updated_by, updated_at: r.updated_at };
              byValue.delete(String(item.value));
            }
          });
          byValue.forEach(r => {
            legend.push({ value: r.value, desc: r.desc, color: r.color });
            legendMeta[r.value] = { updated_by: r.updated_by, updated_at: r.updated_at };
          });
          if (legend.length > 0 && !legend.some(l => l.value === activeBrush)) {
            activeBrush = legend[0].value;
          }
          saveLegendToStorage();
          renderLegendTable();
        } else {
          // 서버 접근은 됐지만 이 맵의 registry가 빈 경우 — 로컬 legend 1회 마이그레이션 제안
          await maybeOfferLegendMigration(selectedTable, loadedMapKey);
        }
      } catch (e) {
        console.warn('[Map Editor] split registry apply skipped:', e);
      }
    }

    renderGridCanvas();
    alert(`기존 데이터 로드 완료: ${count}개 좌표 데이터 매핑.`);
  } catch (err) {
    console.error(err);
    alert('맵 로드 실패: 해당 테이블 또는 메타데이터 값을 다시 확인하십시오.');
  } finally {
    el.btnLoadMap.textContent = '📂 Load Existing Map';
    el.btnLoadMap.disabled = false;
  }
}

function clearGrid() {
  if (!confirm('격자 내의 모든 입력 값을 삭제하시겠습니까?')) return;
  gridData = {};
  loadedFCells.clear();
  renderGridCanvas();
}

function fillGrid() {
  if (!activeBrush) {
    alert('페인팅 브러쉬를 먼저 선택하십시오.');
    return;
  }
  if (!confirm(`격자 전체를 현재 선택한 값 '${activeBrush}'(으)로 채우시겠습니까?`)) return;

  const cols = parseInt(el.gridCols.value, 10) || 10;
  const rows = parseInt(el.gridRows.value, 10) || 10;

  const isRotated90or270 = (currentRotation === 90 || currentRotation === 270);
  const visualCols = isRotated90or270 ? rows : cols;
  const visualRows = isRotated90or270 ? cols : rows;

  for (let r = 0; r < visualRows; r++) {
    for (let c = 0; c < visualCols; c++) {
      const physical = getPhysicalCoords(c, r, cols, rows, currentRotation, currentSide);
      const key = `${physical.x}_${physical.y}`;
      if (isProtectedFCell(key)) continue;
      gridData[key] = activeBrush;
    }
  }

  renderGridCanvas();
}

// ----------------------------------------------------
// PUSH Map Data to Backend
// ----------------------------------------------------
async function pushMapData() {
  const metaInputs = document.querySelectorAll('[id^="meta-input-"]');
  const metaValues = {};
  let hasMeta = false;

  metaInputs.forEach(input => {
    const col = input.id.replace('meta-input-', '');
    const val = input.value.trim();
    if (val !== '') {
      hasMeta = true;
      const colType = tableSchema.column_types[col] || 'string';
      metaValues[col] = colType === 'number' ? Number(val) : val;
    }
  });

  if (!hasMeta && metaInputs.length > 0) {
    alert('데이터 적재를 위해 하나 이상의 메타데이터 필드 값을 입력하십시오.');
    return;
  }

  const xCol = el.colMapX.value;
  const yCol = el.colMapY.value;
  const valCol = el.colMapVal.value;

  const xType = tableSchema.column_types[xCol] || 'number';
  const yType = tableSchema.column_types[yCol] || 'number';
  const valType = tableSchema.column_types[valCol] || 'string';

  const cols = parseInt(el.gridCols.value, 10) || 10;
  const rows = parseInt(el.gridRows.value, 10) || 10;
  const startX = parseInt(el.gridStartX.value, 10) || 0;
  const startY = parseInt(el.gridStartY.value, 10) || 0;
  const invertY = el.gridYInvert.checked;

  // Always construct grid metadata object & JSON string for dedicated wafer_map_metadata table
  const gridMeta = {
    grid_cols: cols,
    grid_rows: rows,
    grid_start_x: startX,
    grid_start_y: startY,
    grid_y_invert: invertY,
    rotation: currentRotation,
    side: currentSide,
    phys_wafer_dia: el.physWaferDia ? (parseFloat(el.physWaferDia.value) || 300) : 300,
    phys_chip_x: el.physChipX ? (parseFloat(el.physChipX.value) || 2.5) : 2.5,
    phys_chip_y: el.physChipY ? (parseFloat(el.physChipY.value) || 2.5) : 2.5,
    phys_offset_x: el.physOffsetX ? (parseFloat(el.physOffsetX.value) || 0.0) : 0.0,
    phys_offset_y: el.physOffsetY ? (parseFloat(el.physOffsetY.value) || 0.0) : 0.0,
    phys_edge_margin: el.physEdgeMargin ? (parseFloat(el.physEdgeMargin.value) || 3.0) : 3.0
  };
  const gridMetaStr = JSON.stringify(gridMeta);

  const updates = [];

  if (gridCells2D) {
    Object.keys(gridCells2D).forEach(rStr => {
      const r = parseInt(rStr, 10);
      if (!gridCells2D[r]) return;
      Object.keys(gridCells2D[r]).forEach(cStr => {
        const c = parseInt(cStr, 10);
        const cellObj = gridCells2D[r][c];
        if (!cellObj || !cellObj.inside) return; // Skip blocked outside-wafer cells

        const val = gridData[cellObj.key] || '';
        if (val === '' || val === null || val === undefined) return; // Skip empty/NULL cells since replace_map=true cleans existing map

        let valParsed = valType === 'number' ? Number(val) : val;

        let xParsed = xType === 'number' ? parseInt(cellObj.x, 10) : String(cellObj.x);
        let yParsed = yType === 'number' ? parseInt(cellObj.y, 10) : String(cellObj.y);

        const rowUpdates = {
          [xCol]: xParsed,
          [yCol]: yParsed,
          [valCol]: valParsed,
          ...metaValues
        };

        if (tableSchema.column_types && tableSchema.column_types['grid_metadata']) {
          rowUpdates['grid_metadata'] = gridMetaStr;
        }

        const updateItem = {
          updates: rowUpdates,
          source_name: 'user',
          updated_by: CURRENT_USER
        };
        updates.push(updateItem);
      });
    });
  }

  if (updates.length === 0) {
    alert('적재할 데이터가 격자에 존재하지 않습니다. 먼저 셀들을 칠해 주십시오.');
    return;
  }

  // [Split Registry] push 대상 값 중 split 서술이 비어있는 값 경고 (자연어 기록 누락 방지 관문)
  const pushedValues = Array.from(new Set(updates.map(u => String(u.updates[valCol]))));
  const missingDescVals = getMissingDescValues(pushedValues, legend);
  if (missingDescVals.length > 0) {
    const preview = missingDescVals.slice(0, 10).join(', ') + (missingDescVals.length > 10 ? ' …' : '');
    const okMissing = confirm(
      `split 서술(Description)이 없는 값 ${missingDescVals.length}개 — 그래도 저장하시겠습니까?\n` +
      `대상 값: [${preview}]\n\n` +
      `서술은 실험 split 조건의 자연어 기록으로, 팀 공유·검색·온톨로지 승격에 사용됩니다.`
    );
    if (!okMissing) return;
  }

  if (!confirm(`총 ${updates.length}건의 활성 맵 데이터를 '${selectedTable}' 테이블에 덮어쓰기 적재(Clean Replace)하시겠습니까?`)) {
    return;
  }

  el.btnPushMap.textContent = '⚡ Pushing...';
  el.btnPushMap.disabled = true;

  const mapIdStr = getMapIdFromMeta(metaValues) || 'default_map';

  console.group('%c🚀 [Map Editor API] PUSH MAP DATA EXECUTED', 'color: #3b82f6; font-weight: bold; font-size: 13px;');
  console.log('📌 Target Table:', selectedTable);
  console.log('📌 Map ID:', mapIdStr);
  console.log('📌 Cell Update Count:', updates.length);
  console.log('📌 Grid Metadata Payload:', gridMeta);

  // Always push dedicated wafer_map_metadata record
  try {
    const metaPayload = {
      updates: [{
        business_key_val: `${selectedTable}_${mapIdStr}`,
        updates: {
          map_pk: `${selectedTable}_${mapIdStr}`,
          target_table: selectedTable,
          map_id: mapIdStr,
          grid_metadata: gridMetaStr
        },
        source_name: 'user',
        updated_by: CURRENT_USER
      }]
    };
    console.log('📤 [API Request 1/2] Header Metadata:', `${API_BASE}/tables/wafer_map_metadata/data/updates`, metaPayload);
    const metaRes = await fetch(`${API_BASE}/tables/wafer_map_metadata/data/updates`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(metaPayload)
    });
    console.log('📥 [API Response 1/2] Status:', metaRes.status);
  } catch (e) {
    console.warn('[Map Editor] Dedicated wafer_map_metadata push skipped/warn:', e);
  }

  const payload = {
    updates: updates,
    silent: false,
    replace_map: true
  };

  try {
    console.log(`📤 [API Request 2/2] Cell Data (${updates.length} rows):`, `${API_BASE}/tables/${selectedTable}/data/updates`, payload);
    const res = await fetch(`${API_BASE}/tables/${selectedTable}/data/updates`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      const result = await res.json();
      console.log('📥 [API Response 2/2] Success Result:', result);
      console.groupEnd();

      // [Split Registry] 맵과 서술의 원자적 동행 — push 성공 시 legend 일괄 서버 저장
      saveLegendToStorage();
      const legendSaved = await saveLegendToServer(mapIdStr);
      if (legendSaved) {
        showToast(`Split 서술 registry 저장 완료 (${legend.length}건)`, 'success');
      } else {
        showToast('Split 서술 registry 저장 실패 — 오프라인 캐시에만 보관됨', 'warning');
      }

      alert(`성공적으로 적재 완료!\n- 적재 처리 건수: ${result.updated_count || result.count || updates.length}개\n- 비즈니스 키 중복 발생 시 자동 병합(Silent Merge) 처리가 완결되었습니다.`);
    } else {
      const errData = await res.json().catch(() => ({}));
      console.error('❌ [API Response 2/2] Error Payload:', errData);
      console.groupEnd();
      throw new Error(errData.detail || 'Push failed');
    }
  } catch (err) {
    console.error('❌ [API Error]', err);
    console.groupEnd();
    alert(`데이터 적재 실패: ${err.message}`);
  } finally {
    el.btnPushMap.textContent = '⚡ Push Map Data';
    el.btnPushMap.disabled = false;
  }
}

// ----------------------------------------------------
// E1/E2 Batch Actions
// ----------------------------------------------------
function getEdgeClassification() {
  const cols = parseInt(el.gridCols.value, 10) || 10;
  const rows = parseInt(el.gridRows.value, 10) || 10;
  const isRotated90or270 = (currentRotation === 90 || currentRotation === 270);
  const visualCols = isRotated90or270 ? rows : cols;
  const visualRows = isRotated90or270 ? cols : rows;

  // 1. Build inside wafer map
  const isInside = Array.from({ length: visualRows }, () => Array(visualCols).fill(false));
  for (let r = 0; r < visualRows; r++) {
    for (let c = 0; c < visualCols; c++) {
      if (isCellInsideWafer(c, r, visualCols, visualRows)) {
        isInside[r][c] = true;
      }
    }
  }

  // 2. BFS Distance Transform from outside cells to compute exact layer depth
  const dist = Array.from({ length: visualRows }, () => Array(visualCols).fill(Infinity));
  const queue = [];

  for (let r = 0; r < visualRows; r++) {
    for (let c = 0; c < visualCols; c++) {
      if (!isInside[r][c]) {
        dist[r][c] = 0;
        queue.push({ r, c });
      }
    }
  }

  const dRow = [-1, 1, 0, 0];
  const dCol = [0, 0, -1, 1];

  let head = 0;
  while (head < queue.length) {
    const { r, c } = queue[head++];
    const currentDist = dist[r][c];

    for (let i = 0; i < 4; i++) {
      const nr = r + dRow[i];
      const nc = c + dCol[i];

      if (nr >= 0 && nr < visualRows && nc >= 0 && nc < visualCols) {
        if (dist[nr][nc] === Infinity) {
          dist[nr][nc] = currentDist + 1;
          queue.push({ r: nr, c: nc });
        }
      }
    }
  }

  // 3. Classify E1 (Distance == 1) and E2 (Distance == 2)
  const isE1 = Array.from({ length: visualRows }, () => Array(visualCols).fill(false));
  const isE2 = Array.from({ length: visualRows }, () => Array(visualCols).fill(false));

  for (let r = 0; r < visualRows; r++) {
    for (let c = 0; c < visualCols; c++) {
      if (isInside[r][c]) {
        if (dist[r][c] === 1) {
          isE1[r][c] = true;
        } else if (dist[r][c] === 2) {
          isE2[r][c] = true;
        }
      }
    }
  }

  return { isE1, isE2 };
}

function getVisualGridDimensions() {
  const cols = parseInt(el.gridCols.value, 10) || 10;
  const rows = parseInt(el.gridRows.value, 10) || 10;
  const isRotated90or270 = (currentRotation === 90 || currentRotation === 270);
  return {
    visualCols: isRotated90or270 ? rows : cols,
    visualRows: isRotated90or270 ? cols : rows
  };
}

function selectEdgeCells(target) {
  const { isE1, isE2 } = getEdgeClassification();
  const targetMap = target === 1 ? isE1 : isE2;
  const { visualCols, visualRows } = getVisualGridDimensions();

  let count = 0;

  for (let r = 0; r < visualRows; r++) {
    for (let c = 0; c < visualCols; c++) {
      if (targetMap[r] && targetMap[r][c]) {
        count++;
      }
    }
  }

  if (count > 0) {
    selectedEdgeTargetMap = targetMap;
    if (el.selectionActionsContainer) el.selectionActionsContainer.style.display = 'flex';
    el.gridStatusCoords.textContent = `Selected ${count} E${target} cells`;
  } else {
    selectedEdgeTargetMap = null;
    if (el.selectionActionsContainer) el.selectionActionsContainer.style.display = 'none';
    alert(`격자 상에 E${target} 조건에 부합하는 셀이 존재하지 않습니다.`);
  }
  scheduleRenderGridCanvas();
}

function autoPaintE1E2() {
  let legendUpdated = false;
  if (!legend.some(item => item.value === 'E1')) {
    legend.push({ value: 'E1', desc: 'Edge 1 (Outermost)', color: '#8b5cf6' });
    legendUpdated = true;
  }
  if (!legend.some(item => item.value === 'E2')) {
    legend.push({ value: 'E2', desc: 'Edge 2 (Inner Outer)', color: '#ec4899' });
    legendUpdated = true;
  }
  if (legendUpdated) {
    persistLegend();
    renderLegendTable();
  }

  const { isE1, isE2 } = getEdgeClassification();
  const { visualCols, visualRows } = getVisualGridDimensions();
  
  let e1Count = 0;
  let e2Count = 0;

  for (let r = 0; r < visualRows; r++) {
    for (let c = 0; c < visualCols; c++) {
      const cell = gridCells2D[r]?.[c];
      if (!cell) continue;
      const key = cell.key;
      if (isProtectedFCell(key)) continue;

      if (isE1[r] && isE1[r][c]) {
        gridData[key] = 'E1';
        e1Count++;
      } else if (isE2[r] && isE2[r][c]) {
        gridData[key] = 'E2';
        e2Count++;
      }
    }
  }

  scheduleRenderGridCanvas();
  alert(`E1/E2 자동 페인팅 완료!\n- E1 (가장 외곽 1칸): ${e1Count}개 셀\n- E2 (외곽에서 2칸): ${e2Count}개 셀`);
}

function fillSelectedCells() {
  if (!activeBrush) {
    alert('페인팅 브러쉬를 먼저 선택하십시오.');
    return;
  }
  if (!selectedEdgeTargetMap) return;

  const { visualCols, visualRows } = getVisualGridDimensions();

  for (let r = 0; r < visualRows; r++) {
    for (let c = 0; c < visualCols; c++) {
      if (selectedEdgeTargetMap[r] && selectedEdgeTargetMap[r][c]) {
        const cell = gridCells2D[r]?.[c];
        if (cell && !isProtectedFCell(cell.key)) {
          gridData[cell.key] = activeBrush;
        }
      }
    }
  }

  selectedEdgeTargetMap = null;
  if (el.selectionActionsContainer) el.selectionActionsContainer.style.display = 'none';
  scheduleRenderGridCanvas();
}

function clearSelectedCells() {
  if (!selectedEdgeTargetMap) return;

  const { visualCols, visualRows } = getVisualGridDimensions();

  for (let r = 0; r < visualRows; r++) {
    for (let c = 0; c < visualCols; c++) {
      if (selectedEdgeTargetMap[r] && selectedEdgeTargetMap[r][c]) {
        const cell = gridCells2D[r]?.[c];
        if (cell && !isProtectedFCell(cell.key)) {
          gridData[cell.key] = '';
        }
      }
    }
  }

  selectedEdgeTargetMap = null;
  if (el.selectionActionsContainer) el.selectionActionsContainer.style.display = 'none';
  scheduleRenderGridCanvas();
}

async function copyGridToExcel() {
  if (!gridCells2D) {
    alert('격자가 생성되어 있지 않습니다.');
    return;
  }

  const { visualCols, visualRows } = getVisualGridDimensions();
  const matrix = [];
  
  // HTML table for rich formatting in Excel (Border + Fill Colors)
  let html = '<table style="border-collapse: collapse; text-align: center; font-family: Arial, sans-serif;">';

  // Helper to find background color from legend
  const getColorForValue = (v) => {
    if (!v) return null;
    const item = legend.find(l => l.value === String(v));
    return item ? item.color : null;
  };

  // Helper for text color contrast
  const getContrastColor = (hexcolor) => {
    if (!hexcolor || hexcolor.charAt(0) !== '#') return '#000000';
    const r = parseInt(hexcolor.substr(1,2),16);
    const g = parseInt(hexcolor.substr(3,2),16);
    const b = parseInt(hexcolor.substr(5,2),16);
    const yiq = ((r*299)+(g*587)+(b*114))/1000;
    return (yiq >= 128) ? '#000000' : '#ffffff';
  };

  const box = getWaferBoundingBox(currentRotation, currentSide);
  const centerC = Math.floor((box.minC + box.maxC) / 2);
  const centerR = Math.floor((box.minR + box.maxR) / 2);

  const dx = (currentSide === 'front') ? 1 : -1;
  let screenDx = 0;
  let screenDy = 0;

  if (currentRotation === 0) { screenDx = dx; screenDy = 0; }
  else if (currentRotation === 90) { screenDx = 0; screenDy = dx; }
  else if (currentRotation === 180) { screenDx = -dx; screenDy = 0; }
  else if (currentRotation === 270) { screenDx = 0; screenDy = -dx; }

  let notchR = -1;
  let notchC = -1;

  if (currentRotation === 0) {
    // Bottom Notch: 1 row below box.maxR
    notchR = box.maxR + 1;
    notchC = centerC + screenDx;
  } else if (currentRotation === 180) {
    // Top Notch: 1 row above box.minR
    notchR = box.minR - 1;
    notchC = centerC + screenDx;
  } else if (currentRotation === 90) {
    // Left Notch: 1 col left of box.minC
    notchC = box.minC - 1;
    notchR = centerR + screenDy;
  } else if (currentRotation === 270) {
    // Right Notch: 1 col right of box.maxC
    notchC = box.maxC + 1;
    notchR = centerR + screenDy;
  }

  for (let r = 0; r < visualRows; r++) {
    const rowCells = [];
    html += '<tr>';
    for (let c = 0; c < visualCols; c++) {
      const cell = gridCells2D[r]?.[c];
      const isNotchCell = (r === notchR && c === notchC);

      if (cell) {
        const key = cell.key;
        let val = gridData[key] || '';
        const isInside = cell.inside;

        if (isNotchCell && val === '') {
          val = 'D';
        }
        rowCells.push(val);

        const bgColor = getColorForValue(val);

        let style = 'width: 32px; height: 32px; font-size: 10pt; font-weight: bold; text-align: center; vertical-align: middle;';
        
        if (isNotchCell && val === 'D') {
          // Notch D indicator cell 1 row below valid wafer area
          style += ' border: 2px solid #222222; background-color: #a855f7; color: #ffffff; font-size: 11pt;';
        } else if (isInside) {
          // 1. Thick border & background color formatting for valid wafer cells
          style += ' border: 2px solid #222222;';
          if (bgColor && val !== '') {
            const textColor = getContrastColor(bgColor);
            style += ` background-color: ${bgColor}; color: ${textColor};`;
          } else {
            // NULL / Empty area inside valid wafer filled with #DAF2D0
            style += ' background-color: #DAF2D0; color: #2e7d32;';
          }
        } else {
          style += ' border: 1px dashed #d1d5db; background-color: #f8fafc; color: #cbd5e1;';
        }

        html += `<td style="${style}">${val}</td>`;
      } else {
        const val = isNotchCell ? 'D' : '';
        rowCells.push(val);
        const style = isNotchCell
          ? 'border: 2px solid #222222; background-color: #a855f7; color: #ffffff; font-weight: bold; text-align: center; vertical-align: middle;'
          : 'border: 1px dashed #d1d5db; background-color: #f8fafc;';
        html += `<td style="${style}">${val}</td>`;
      }
    }
    html += '</tr>';
    matrix.push(rowCells.join('\t'));
  }

  html += '</table>';
  const tsv = matrix.join('\n');

  try {
    if (navigator.clipboard && window.ClipboardItem) {
      const blobText = new Blob([tsv], { type: 'text/plain' });
      const blobHtml = new Blob([html], { type: 'text/html' });
      await navigator.clipboard.write([
        new ClipboardItem({
          'text/plain': blobText,
          'text/html': blobHtml
        })
      ]);
    } else {
      await navigator.clipboard.writeText(tsv);
    }

    if (el.btnCopyExcel) {
      const originalText = el.btnCopyExcel.textContent;
      el.btnCopyExcel.textContent = '✅ Copied to Excel!';
      setTimeout(() => {
        el.btnCopyExcel.textContent = originalText;
      }, 1500);
    }
  } catch (err) {
    console.warn('Rich clipboard write failed, falling back to plain text:', err);
    try {
      await navigator.clipboard.writeText(tsv);
      if (el.btnCopyExcel) {
        const originalText = el.btnCopyExcel.textContent;
        el.btnCopyExcel.textContent = '✅ Copied!';
        setTimeout(() => {
          el.btnCopyExcel.textContent = originalText;
        }, 1500);
      }
    } catch (e) {
      console.error('Failed to copy to clipboard', e);
      alert('클립보드 복사에 실패했습니다.');
    }
  }
}
