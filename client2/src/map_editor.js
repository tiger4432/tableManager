import './style.css';
import { API_BASE, CURRENT_USER } from './config.js';

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
let physicalOrigin = null; // Coordinates of fixed physical origin chip { x, y }
let isBoxDragging = false; // Bounding box drag selection state
let boxStartCell = null; // Start cell reference for bounding box
let lastSelectionBox = null; // Track coordinates of current selection bounding box
let gridCells2D = []; // 2D reference array of cell metadata objects [row][col]
let dragType = null; // 'paint' | 'erase'
let selectedEdgeTargetMap = null; // Track active E1/E2 edge selection map

// Default Legend
const DEFAULT_LEGEND = [
  { value: '1', desc: 'GOOD', color: '#10b981' },
  { value: '0', desc: 'FAIL', color: '#ef4444' },
  { value: '2', desc: 'EMPTY', color: '#4b5563' },
  { value: '3', desc: 'REWORK', color: '#f59e0b' }
];

function debounce(func, wait = 200) {
  let timeout;
  return function(...args) {
    clearTimeout(timeout);
    timeout = setTimeout(() => func.apply(this, args), wait);
  };
}

// Initialize DOM elements when loaded
document.addEventListener('DOMContentLoaded', async () => {
  initDOMElements();
  initMouseDragEvents();
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

  window.addEventListener('resize', () => scheduleRenderGridCanvas());

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
  renderPresetDropdown();
  
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
      const nextRotation = parseInt(btn.dataset.rot, 10);
      recalculateOriginOffset(nextRotation, currentSide);
      currentRotation = nextRotation;
      scheduleRenderGridCanvas();
    });
  });

  // Wafer Side Radios
  document.querySelectorAll('input[name="wafer-side"]').forEach(radio => {
    radio.addEventListener('change', (e) => {
      const nextSide = e.target.value;
      recalculateOriginOffset(currentRotation, nextSide);
      currentSide = nextSide;
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

  const hasZeroZero = (startX <= 0 && (startX + visualCols - 1) >= 0) && (startY <= 0 && (startY + visualRows - 1) >= 0);

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
      data.tables.forEach(table => {
        const option = document.createElement('option');
        option.value = table;
        option.textContent = table;
        el.tableSelect.appendChild(option);
      });
      // Auto select bonding_map if exists, otherwise first table
      const hasBondingMap = data.tables.includes('bonding_map');
      const startTable = hasBondingMap ? 'bonding_map' : data.tables[0];
      el.tableSelect.value = startTable;
      await switchTable(startTable);
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
    
    // Load Legend from localStorage or defaults
    loadLegendFromStorage();
    renderLegendTable();
    
    // Reset Grid data and Draw
    gridData = {};
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
  const xCol = el.colMapX.value;
  const yCol = el.colMapY.value;
  const valCol = el.colMapVal.value;

  // Filter out system columns and coordinate/value columns
  const systemCols = [
    'created_at', 'updated_at', 'row_id', 'business_key_val',
    'is_graph_synced', 'needs_graph_rollback', 'graph_synced_at',
    'grid_metadata'
  ];

  const metaCols = cols.filter(col => {
    return !systemCols.includes(col) &&
           col !== xCol &&
           col !== yCol &&
           col !== valCol;
  });

  metaCols.forEach(col => {
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
    input.placeholder = `${col} 값 입력`;
    
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
  const isRotated90or270 = (rotation === 90 || rotation === 270);
  const visualCols = isRotated90or270 ? rows : cols;
  const visualRows = isRotated90or270 ? cols : rows;

  let c_screen = xv - startX;
  let r_screen = yv - startY;

  if (invertY) {
    r_screen = (visualRows - 1) - r_screen;
  }

  let c = c_screen;
  let r = r_screen;

  if (side === 'back') {
    if (isRotated90or270) {
      r = (visualRows - 1) - r_screen;
    } else {
      c = (visualCols - 1) - c_screen;
    }
  }

  return { c, r };
}

function recalculateOriginOffset(newRotation, newSide) {
  if (!physicalOrigin) return;

  const cols = parseInt(el.gridCols.value, 10) || 10;
  const rows = parseInt(el.gridRows.value, 10) || 10;
  const invertY = el.gridYInvert.checked;

  // 1. Find the screen cell index of physicalOrigin under the new rotation & side
  const cellOrigin = getCellFromPhysicalCoords(physicalOrigin.x, physicalOrigin.y, cols, rows, newRotation, newSide);

  // 2. Find visual coordinates of this cell under new rotation/side with startX = 0, startY = 0
  const visualCoords = getVisualCoords(cellOrigin.c, cellOrigin.r, cols, rows, newRotation, newSide, invertY, 0, 0);

  // 3. Negate visual coordinates to get the new startX and startY
  const newStartX = -visualCoords.x;
  const newStartY = -visualCoords.y;

  // 4. Update the input values
  el.gridStartX.value = newStartX;
  el.gridStartY.value = newStartY;
}

function getVisualCoords(colVisual, rowVisual, cols, rows, rotation, side, invertY, startX, startY) {
  const isRotated90or270 = (rotation === 90 || rotation === 270);
  const visualCols = isRotated90or270 ? rows : cols;
  const visualRows = isRotated90or270 ? cols : rows;

  let c_screen = colVisual;
  let r_screen = rowVisual;

  const xv = c_screen + startX;
  let yv = r_screen;

  if (invertY) {
    yv = (visualRows - 1) - yv;
  }
  yv = yv + startY;

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
  const waferDia = el.physWaferDia ? parseFloat(el.physWaferDia.value) : 300;
  const edgeMargin = el.physEdgeMargin ? parseFloat(el.physEdgeMargin.value) : 3.0;
  const effectiveRadius = Math.max(0, (waferDia / 2.0) - edgeMargin);

  const chipX = el.physChipX ? parseFloat(el.physChipX.value) : 2.5;
  const chipY = el.physChipY ? parseFloat(el.physChipY.value) : 2.5;
  const offsetX = el.physOffsetX ? parseFloat(el.physOffsetX.value) : 0.0;
  const offsetY = el.physOffsetY ? parseFloat(el.physOffsetY.value) : 0.0;

  return isCellInsideWaferFast(c, r, visualCols, visualRows, {
    chipX, chipY, offsetX, offsetY, effectiveRadius, radiusSq: effectiveRadius * effectiveRadius
  });
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
const BUILTIN_PRESETS = {
  std_10: { name: "Std 10x10 (0°, Front)", cols: 10, rows: 10, startX: 0, startY: 0, rot: 0, side: "front", invertY: false },
  prod_a: { name: "Product A (30x30, 90°, Back)", cols: 30, rows: 30, startX: 0, startY: 0, rot: 90, side: "back", invertY: false },
  prod_b: { name: "Product B (50x50, 180°, Front)", cols: 50, rows: 50, startX: 0, startY: 0, rot: 180, side: "front", invertY: false },
  prod_c: { name: "Product C (60x60, 270°, Back)", cols: 60, rows: 60, startX: 0, startY: 0, rot: 270, side: "back", invertY: false }
};

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
}

function renderPresetDropdown() {
  if (!el.presetSelect) return;
  el.presetSelect.innerHTML = '<option value="">-- Select Preset --</option>';

  const optGroupBuiltin = document.createElement('optgroup');
  optGroupBuiltin.label = 'Built-in Presets';
  Object.entries(BUILTIN_PRESETS).forEach(([k, p]) => {
    const opt = document.createElement('option');
    opt.value = k;
    opt.textContent = p.name;
    optGroupBuiltin.appendChild(opt);
  });
  el.presetSelect.appendChild(optGroupBuiltin);

  const customPresets = JSON.parse(localStorage.getItem('map_editor_custom_presets') || '{}');
  if (Object.keys(customPresets).length > 0) {
    const optGroupCustom = document.createElement('optgroup');
    optGroupCustom.label = 'Custom Presets';
    Object.entries(customPresets).forEach(([k, p]) => {
      const opt = document.createElement('option');
      opt.value = k;
      opt.textContent = p.name;
      optGroupCustom.appendChild(opt);
    });
    el.presetSelect.appendChild(optGroupCustom);
  }
}

function loadSelectedPreset() {
  if (!el.presetSelect) return;
  const val = el.presetSelect.value;
  if (!val) return;

  let preset = BUILTIN_PRESETS[val];
  if (!preset) {
    const customPresets = JSON.parse(localStorage.getItem('map_editor_custom_presets') || '{}');
    preset = customPresets[val];
  }

  if (preset) {
    el.gridCols.value = preset.cols;
    el.gridRows.value = preset.rows;
    el.gridStartX.value = preset.startX;
    el.gridStartY.value = preset.startY;
    el.gridYInvert.checked = preset.invertY;
    currentRotation = preset.rot;
    currentSide = preset.side;

    updateOrientationUI();
    renderGridCanvas();
    updateLegendCounts();
  }
}

function saveCustomPreset() {
  const presetName = prompt('Enter custom preset name:', `Product Preset ${new Date().toLocaleDateString()}`);
  if (!presetName) return;

  const key = `custom_${Date.now()}`;
  const newPreset = {
    name: presetName,
    cols: parseInt(el.gridCols.value, 10) || 10,
    rows: parseInt(el.gridRows.value, 10) || 10,
    startX: parseInt(el.gridStartX.value, 10) || 0,
    startY: parseInt(el.gridStartY.value, 10) || 0,
    rot: currentRotation,
    side: currentSide,
    invertY: el.gridYInvert.checked
  };

  const customPresets = JSON.parse(localStorage.getItem('map_editor_custom_presets') || '{}');
  customPresets[key] = newPreset;
  localStorage.setItem('map_editor_custom_presets', JSON.stringify(customPresets));

  renderPresetDropdown();
  el.presetSelect.value = key;
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
let isRenderScheduled = false;

function scheduleRenderGridCanvas() {
  if (isRenderScheduled) return;
  isRenderScheduled = true;
  requestAnimationFrame(() => {
    isRenderScheduled = false;
    renderGridCanvas();
  });
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

  const hasZeroZero = (startX <= 0 && (startX + visualCols - 1) >= 0) && (startY <= 0 && (startY + visualRows - 1) >= 0);

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
        ctx.fillStyle = 'rgba(15, 23, 42, 0.6)';
        ctx.fillRect(x0, y0, cellW, cellH);
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.04)';
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
        ctx.fillStyle = 'rgba(15, 23, 42, 0.6)';
      } else if (val !== '') {
        ctx.fillStyle = colorMap[val] || '#10b981';
      } else {
        ctx.fillStyle = 'rgba(34, 197, 94, 0.08)';
      }
      ctx.fillRect(x0, y0, cellW, cellH);

      // 2. Stroke grid border across ALL cells (inside and outside wafer)
      ctx.strokeStyle = completelyInside ? 'rgba(255, 255, 255, 0.08)' : 'rgba(255, 255, 255, 0.05)';
      ctx.lineWidth = 0.5;
      ctx.strokeRect(x0, y0, cellW, cellH);

      // 3. Wafer inside boundary cell outline
      if (completelyInside) {
        ctx.strokeStyle = '#22c55e';
        ctx.lineWidth = 1.2;
        ctx.strokeRect(x0 + 0.5, y0 + 0.5, cellW - 1, cellH - 1);
      }

      // 4. Origin cell highlight
      if (isOriginCell) {
        ctx.fillStyle = 'rgba(239, 68, 68, 0.25)';
        ctx.fillRect(x0, y0, cellW, cellH);
        ctx.strokeStyle = '#ef4444';
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
        ctx.fillStyle = val !== '' ? '#ffffff' : (completelyInside ? 'rgba(148, 163, 184, 0.85)' : 'rgba(71, 85, 105, 0.5)');
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
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.85)';
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
  ctx.strokeStyle = '#22c55e';
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
    ctx.fillStyle = '#f59e0b';
    ctx.fill();
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 1.0;
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(gridCenterX - 8, gridCenterY);
    ctx.lineTo(gridCenterX + 8, gridCenterY);
    ctx.moveTo(gridCenterX, gridCenterY - 8);
    ctx.lineTo(gridCenterX, gridCenterY + 8);
    ctx.strokeStyle = 'rgba(245, 158, 11, 0.85)';
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
    ctx.fillStyle = isErase ? 'rgba(239, 68, 68, 0.3)' : 'rgba(59, 130, 246, 0.3)';
    ctx.fillRect(boxX, boxY, boxW, boxH);

    ctx.strokeStyle = isErase ? '#ef4444' : '#3b82f6';
    ctx.lineWidth = 2.0;
    ctx.strokeRect(boxX + 1, boxY + 1, boxW - 2, boxH - 2);
  }

  // 8. Hover Cell highlight
  if (currentHoverCell && !isBoxDragging) {
    const hX = currentHoverCell.c * cellW + shiftX;
    const hY = currentHoverCell.r * cellH + shiftY;
    ctx.strokeStyle = '#00f0ff';
    ctx.lineWidth = 2.0;
    ctx.strokeRect(hX + 1, hY + 1, cellW - 2, cellH - 2);
  }

  ctx.restore();

  updateNotchPosition();
  updateLegendCounts();

  const tEnd = performance.now();
  console.log(`[PERF DEBUG] Canvas renderGridCanvas completed in ${(tEnd - tStart).toFixed(2)} ms (${visualCols}x${visualRows} = ${visualCols * visualRows} cells)`);
}

function handleCellClick(cell, event) {
  if (!cell) return;
  const c = cell.c !== undefined ? cell.c : 0;
  const r = cell.r !== undefined ? cell.r : 0;
  const key = cell.key;

  if (isOriginMode) {
    const cols = parseInt(el.gridCols.value, 10) || 10;
    const rows = parseInt(el.gridRows.value, 10) || 10;
    const invertY = el.gridYInvert.checked;

    // Save physical coordinates of origin
    physicalOrigin = { x: cell.px, y: cell.py };

    const visualCoords = getVisualCoords(c, r, cols, rows, currentRotation, currentSide, invertY, 0, 0);

    const newStartX = -visualCoords.x;
    const newStartY = -visualCoords.y;

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
    cell.style.borderColor = 'rgba(255, 255, 255, 0.2)';
  } else {
    cell.style.backgroundColor = 'rgba(30, 41, 59, 0.8)';
    cell.style.borderColor = 'rgba(255, 255, 255, 0.05)';
  }
}

// ----------------------------------------------------
// V-Notch Orientation & Offsets
// ----------------------------------------------------
function updateNotchPosition() {
  if (!el.gridNotch) return;

  el.gridNotch.className = 'wafer-notch';

  let positionClass = '';
  if (currentRotation === 0) positionClass = 'notch-bottom';
  else if (currentRotation === 90) positionClass = 'notch-left';
  else if (currentRotation === 180) positionClass = 'notch-top';
  else if (currentRotation === 270) positionClass = 'notch-right';
  el.gridNotch.classList.add(positionClass);

  const offset = 20; // px shift
  el.gridNotch.style.left = '';
  el.gridNotch.style.right = '';
  el.gridNotch.style.top = '';
  el.gridNotch.style.bottom = '';
  el.gridNotch.style.transform = '';

  if (currentRotation === 0) { // Bottom
    el.gridNotch.style.bottom = '5px';
    if (currentSide === 'front') {
      el.gridNotch.style.left = `calc(50% + ${offset}px)`;
    } else {
      el.gridNotch.style.left = `calc(50% - ${offset}px)`;
    }
    el.gridNotch.style.transform = 'translateX(-50%)';
  } else if (currentRotation === 180) { // Top
    el.gridNotch.style.top = '5px';
    if (currentSide === 'front') {
      el.gridNotch.style.left = `calc(50% + ${offset}px)`;
    } else {
      el.gridNotch.style.left = `calc(50% - ${offset}px)`;
    }
    el.gridNotch.style.transform = 'translateX(-50%)';
  } else if (currentRotation === 90) { // Left
    el.gridNotch.style.left = '5px';
    if (currentSide === 'front') {
      el.gridNotch.style.top = `calc(50% - ${offset}px)`;
    } else {
      el.gridNotch.style.top = `calc(50% + ${offset}px)`;
    }
    el.gridNotch.style.transform = 'translateY(-50%)';
  } else if (currentRotation === 270) { // Right
    el.gridNotch.style.right = '5px';
    if (currentSide === 'front') {
      el.gridNotch.style.top = `calc(50% + ${offset}px)`;
    } else {
      el.gridNotch.style.top = `calc(50% - ${offset}px)`;
    }
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
      if (e.target.tagName === 'INPUT' || e.target.classList.contains('btn-delete')) return;
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
      saveLegendToStorage();
      renderGridCanvas();
    });
    tdVal.appendChild(inputVal);

    // Description column
    const tdDesc = document.createElement('td');
    const inputDesc = document.createElement('input');
    inputDesc.type = 'text';
    inputDesc.className = 'glass-input';
    inputDesc.style.padding = '6px 10px';
    inputDesc.style.fontSize = '0.9rem';
    inputDesc.style.width = '100%';
    inputDesc.value = item.desc;
    inputDesc.addEventListener('change', (e) => {
      item.desc = e.target.value.trim();
      saveLegendToStorage();
      if (activeBrush === item.value) {
        el.activeBrushVal.textContent = `${item.value} (${item.desc})`;
      }
    });
    tdDesc.appendChild(inputDesc);

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
      saveLegendToStorage();
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
      saveLegendToStorage();
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
    desc: `VALUE ${nextVal}`,
    color: nextColor
  });
  
  saveLegendToStorage();
  renderLegendTable();
}

function remapGridValues(oldVal, newVal) {
  Object.keys(gridData).forEach(k => {
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

    // Reset local cache
    gridData = {};
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
    if (result && result.data) {
      const firstWithMeta = result.data.find(row => row.data && row.data['grid_metadata'] && row.data['grid_metadata'].value);
      if (firstWithMeta) {
        try {
          loadedGridMeta = JSON.parse(firstWithMeta.data['grid_metadata'].value);
        } catch (e) {
          console.error('Failed to parse grid_metadata:', e);
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

            const c_screen = xNum - startX;
            const isRotated90or270 = (rotation === 90 || rotation === 270);
            const visualCols = isRotated90or270 ? rows : cols;
            const visualRows = isRotated90or270 ? cols : rows;

            let r_screen = yNum - startY;
            if (invertY) {
              r_screen = (visualRows - 1) - r_screen;
            }

            let c = c_screen;
            let r = r_screen;
            if (side === 'back') {
              if (rotation === 90 || rotation === 270) {
                r = (visualRows - 1) - r_screen;
              } else {
                c = (visualCols - 1) - c_screen;
              }
            }

            const physical = getPhysicalCoords(c, r, cols, rows, rotation, side);
            gridData[`${physical.x}_${physical.y}`] = strVal;
          }
        }
      });
    }

    // Set the physical origin based on loaded metadata
    const cellOrigin = getCellFromVisualCoords(0, 0, cols, rows, rotation, side, invertY, startX, startY);
    physicalOrigin = getPhysicalCoords(cellOrigin.c, cellOrigin.r, cols, rows, rotation, side);

    // Sync state variables and input values back to left panel
    el.gridCols.value = cols;
    el.gridRows.value = rows;
    el.gridStartX.value = startX;
    el.gridStartY.value = startY;
    el.gridYInvert.checked = invertY;
    currentRotation = rotation;
    currentSide = side;

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
      gridData[`${physical.x}_${physical.y}`] = activeBrush;
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

  // Serialize current grid metadata config if the table supports it
  let gridMetaStr = null;
  if (tableSchema.column_types && tableSchema.column_types['grid_metadata']) {
    const gridMeta = {
      grid_cols: cols,
      grid_rows: rows,
      grid_start_x: startX,
      grid_start_y: startY,
      grid_y_invert: invertY,
      rotation: currentRotation,
      side: currentSide
    };
    gridMetaStr = JSON.stringify(gridMeta);
  }

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

        let valParsed = null;
        if (val !== '') {
          valParsed = valType === 'number' ? Number(val) : val;
        }

        let xParsed = xType === 'number' ? parseInt(cellObj.x, 10) : String(cellObj.x);
        let yParsed = yType === 'number' ? parseInt(cellObj.y, 10) : String(cellObj.y);

        const rowUpdates = {
          [xCol]: xParsed,
          [yCol]: yParsed,
          [valCol]: valParsed,
          ...metaValues
        };

        if (gridMetaStr) {
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

  if (!confirm(`총 ${updates.length}건의 좌표 맵 데이터를 '${selectedTable}' 테이블에 바로 적재(Upsert/Push)하시겠습니까?`)) {
    return;
  }

  el.btnPushMap.textContent = '⚡ Pushing...';
  el.btnPushMap.disabled = true;

  const payload = {
    updates: updates,
    silent: false
  };

  try {
    const res = await fetch(`${API_BASE}/tables/${selectedTable}/data/updates`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      const result = await res.json();
      alert(`성공적으로 적재 완료!\n- 적재 처리 건수: ${result.updated_count || result.count || updates.length}개\n- 비즈니스 키 중복 발생 시 자동 병합(Silent Merge) 처리가 완결되었습니다.`);
    } else {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || 'Push failed');
    }
  } catch (err) {
    console.error(err);
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

  // 2. Classify E1 (Edge 1): Outermost active layer adjacent to outside or grid bounds
  const isE1 = Array.from({ length: visualRows }, () => Array(visualCols).fill(false));
  for (let r = 0; r < visualRows; r++) {
    for (let c = 0; c < visualCols; c++) {
      if (!isInside[r][c]) continue;
      
      // Check 8 neighbors
      let touchesOutside = false;
      for (let dr = -1; dr <= 1; dr++) {
        for (let dc = -1; dc <= 1; dc++) {
          if (dr === 0 && dc === 0) continue;
          const nr = r + dr;
          const nc = c + dc;
          if (nr < 0 || nr >= visualRows || nc < 0 || nc >= visualCols || !isInside[nr][nc]) {
            touchesOutside = true;
            break;
          }
        }
        if (touchesOutside) break;
      }
      if (touchesOutside) {
        isE1[r][c] = true;
      }
    }
  }

  // 3. Classify E2 (Edge 2): Second layer, not E1 but adjacent to E1
  const isE2 = Array.from({ length: visualRows }, () => Array(visualCols).fill(false));
  for (let r = 0; r < visualRows; r++) {
    for (let c = 0; c < visualCols; c++) {
      if (!isInside[r][c] || isE1[r][c]) continue;

      // Check if adjacent to E1
      let touchesE1 = false;
      for (let dr = -1; dr <= 1; dr++) {
        for (let dc = -1; dc <= 1; dc++) {
          if (dr === 0 && dc === 0) continue;
          const nr = r + dr;
          const nc = c + dc;
          if (nr >= 0 && nr < visualRows && nc >= 0 && nc < visualCols && isE1[nr][nc]) {
            touchesE1 = true;
            break;
          }
        }
        if (touchesE1) break;
      }
      if (touchesE1) {
        isE2[r][c] = true;
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
    saveLegendToStorage();
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
        if (cell) {
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
        if (cell) {
          gridData[cell.key] = '';
        }
      }
    }
  }

  selectedEdgeTargetMap = null;
  if (el.selectionActionsContainer) el.selectionActionsContainer.style.display = 'none';
  scheduleRenderGridCanvas();
}

function copyGridToExcel() {
  if (!gridCells2D) {
    alert('격자가 생성되어 있지 않습니다.');
    return;
  }

  const { visualCols, visualRows } = getVisualGridDimensions();
  const matrix = [];

  for (let r = 0; r < visualRows; r++) {
    const rowCells = [];
    for (let c = 0; c < visualCols; c++) {
      const cell = gridCells2D[r]?.[c];
      if (cell) {
        const key = cell.key;
        const val = gridData[key] || '';
        rowCells.push(val);
      } else {
        rowCells.push('');
      }
    }
    matrix.push(rowCells.join('\t'));
  }

  const tsv = matrix.join('\n');

  navigator.clipboard.writeText(tsv).then(() => {
    if (el.btnCopyExcel) {
      const originalText = el.btnCopyExcel.textContent;
      el.btnCopyExcel.textContent = '✅ Copied!';
      setTimeout(() => {
        el.btnCopyExcel.textContent = originalText;
      }, 1500);
    }
  }).catch(err => {
    console.error('Failed to copy to clipboard', err);
    alert('클립보드 복사에 실패했습니다.');
  });
}
