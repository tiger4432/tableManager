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
let isBoxDragging = false; // Bounding box drag selection state
let boxStartCell = null; // Start cell reference for bounding box
let lastSelectionBox = null; // Track coordinates of current selection bounding box
let gridCells2D = []; // 2D reference array of cell DOM elements [row][col]
let dragType = null; // 'paint' | 'erase'

// Default Legend
const DEFAULT_LEGEND = [
  { value: '1', desc: 'GOOD', color: '#10b981' },
  { value: '0', desc: 'FAIL', color: '#ef4444' },
  { value: '2', desc: 'EMPTY', color: '#4b5563' },
  { value: '3', desc: 'REWORK', color: '#f59e0b' }
];

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
  el.gridWrapper = document.getElementById('grid-wrapper');
  el.gridNotch = document.getElementById('grid-notch');

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
      renderGridCanvas();
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
  
  if (el.btnSelectE1) el.btnSelectE1.addEventListener('click', () => selectEdgeCells(1));
  if (el.btnSelectE2) el.btnSelectE2.addEventListener('click', () => selectEdgeCells(2));
  if (el.btnAutoPaintE1E2) el.btnAutoPaintE1E2.addEventListener('click', autoPaintE1E2);
  if (el.btnFillSelected) el.btnFillSelected.addEventListener('click', fillSelectedCells);
  if (el.btnClearSelected) el.btnClearSelected.addEventListener('click', clearSelectedCells);

  // Dynamic Metadata Inputs change triggers
  el.colMapX.addEventListener('change', () => {
    renderMetadataInputs();
    renderGridCanvas();
  });
  el.colMapY.addEventListener('change', () => {
    renderMetadataInputs();
    renderGridCanvas();
  });
  el.colMapVal.addEventListener('change', () => {
    renderMetadataInputs();
    renderGridCanvas();
  });

  // Rotation Buttons
  document.querySelectorAll('.btn-rot').forEach(btn => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('.btn-rot').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentRotation = parseInt(btn.dataset.rot, 10);
      renderGridCanvas();
    });
  });

  // Wafer Side Radios
  document.querySelectorAll('input[name="wafer-side"]').forEach(radio => {
    radio.addEventListener('change', (e) => {
      currentSide = e.target.value;
      renderGridCanvas();
    });
  });

  // Prevent right-click context menu on canvas
  el.gridCanvas.addEventListener('contextmenu', (e) => e.preventDefault());
}

function initMouseDragEvents() {
  window.addEventListener('mousedown', (e) => {
    isMouseDown = true;
    isRightDrag = (e.button === 2);
  });

  if (el.gridCanvas) {
    el.gridCanvas.addEventListener('mousedown', (e) => {
      e.preventDefault();
      const cell = e.target.closest('.grid-cell');
      if (!cell) return;

      // Hide batch actions when starting a new interaction
      if (el.selectionActionsContainer) el.selectionActionsContainer.style.display = 'none';

      if (isOriginMode) {
        handleCellClick(cell, e);
        return;
      }

      const isRight = (e.button === 2 || e.buttons === 2);
      isBoxDragging = true;
      boxStartCell = cell;
      dragType = isRight ? 'erase' : 'paint';
      el.gridCanvas.classList.add('drag-active');

      const c = parseInt(cell.dataset.c, 10);
      const r = parseInt(cell.dataset.r, 10);
      lastSelectionBox = { minC: c, maxC: c, minR: r, maxR: r };

      cell.classList.add(isRight ? 'cell-in-selection-erase' : 'cell-in-selection');
    });

    el.gridCanvas.addEventListener('mousemove', (e) => {
      const cell = e.target.closest('.grid-cell');
      if (!cell) return;

      const c = parseInt(cell.dataset.c, 10);
      const r = parseInt(cell.dataset.r, 10);

      if (!isBoxDragging) {
        const val = gridData[cell.dataset.key] || '';
        el.gridStatusCoords.textContent = `Cursor: (${cell.dataset.x}, ${cell.dataset.y}) = ${val !== '' ? val : 'Empty'}`;
        return;
      }

      if (boxStartCell) {
        const c1 = parseInt(boxStartCell.dataset.c, 10);
        const r1 = parseInt(boxStartCell.dataset.r, 10);
        const c2 = c;
        const r2 = r;

        const minC = Math.min(c1, c2);
        const maxC = Math.max(c1, c2);
        const minR = Math.min(r1, r2);
        const maxR = Math.max(r1, r2);

        // If selection box bounds haven't changed, skip DOM writes to prevent lag
        if (lastSelectionBox && 
            lastSelectionBox.minC === minC && lastSelectionBox.maxC === maxC &&
            lastSelectionBox.minR === minR && lastSelectionBox.maxR === maxR) {
          return;
        }

        const activeClass = (dragType === 'erase') ? 'cell-in-selection-erase' : 'cell-in-selection';

        // 1. Remove selection class from old box cells that are no longer inside the new box bounds
        if (lastSelectionBox) {
          for (let row = lastSelectionBox.minR; row <= lastSelectionBox.maxR; row++) {
            for (let col = lastSelectionBox.minC; col <= lastSelectionBox.maxC; col++) {
              const outsideNewBox = (col < minC || col > maxC || row < minR || row > maxR);
              if (outsideNewBox) {
                const oldCell = gridCells2D[row]?.[col];
                if (oldCell) {
                  oldCell.classList.remove('cell-in-selection');
                  oldCell.classList.remove('cell-in-selection-erase');
                }
              }
            }
          }
        }

        // 2. Add selection class to cells in the new box bounds
        for (let row = minR; row <= maxR; row++) {
          for (let col = minC; col <= maxC; col++) {
            const insideOldBox = lastSelectionBox && (col >= lastSelectionBox.minC && col <= lastSelectionBox.maxC && row >= lastSelectionBox.minR && row <= lastSelectionBox.maxR);
            if (!insideOldBox) {
              const newCell = gridCells2D[row]?.[col];
              if (newCell) {
                newCell.classList.add(activeClass);
              }
            }
          }
        }

        // 3. Update cached box bounds
        lastSelectionBox = { minC, maxC, minR, maxR };
      }
    });
  }

  window.addEventListener('mouseup', () => {
    isMouseDown = false;
    isRightDrag = false;

    if (isBoxDragging) {
      if (boxStartCell && lastSelectionBox) {
        const { minC, maxC, minR, maxR } = lastSelectionBox;
        const showAnno = el.showAnnotations ? el.showAnnotations.checked : true;

        // Apply values to final box selection cells in O(Box_Area) instead of O(Grid_Size)
        for (let r = minR; r <= maxR; r++) {
          for (let c = minC; c <= maxC; c++) {
            const cell = gridCells2D[r]?.[c];
            if (!cell) continue;

            const key = cell.dataset.key;
            if (dragType === 'erase') {
              gridData[key] = '';
              cell.textContent = showAnno ? `${cell.dataset.x},${cell.dataset.y}` : '';
              cell.style.fontSize = '0.65rem';
              cell.style.color = 'var(--text-dim)';
              updateCellStyles(cell, '');
              cell.title = `좌표: (${cell.dataset.x}, ${cell.dataset.y})\n값: Empty`;
              cell.classList.remove('has-value');
            } else if (dragType === 'paint') {
              if (cell.classList.contains('cell-outside-wafer')) continue;

              const existingVal = gridData[key] || '';
              const isSingleClick = (minC === maxC && minR === maxR);
              if (!isSingleClick && existingVal !== '') {
                continue;
              }

              if (activeBrush !== undefined && activeBrush !== null) {
                gridData[key] = activeBrush;
                cell.textContent = activeBrush;
                cell.style.fontSize = '0.8rem';
                cell.style.color = '#fff';
                updateCellStyles(cell, activeBrush);
                cell.title = `좌표: (${cell.dataset.x}, ${cell.dataset.y})\n값: ${activeBrush}`;
                cell.classList.add('has-value');
              }
            }
          }
        }
      }

      // Safeguard: Clear any orphaned selection classes across the entire canvas
      if (el.gridCanvas) {
        el.gridCanvas.querySelectorAll('.cell-in-selection, .cell-in-selection-erase').forEach(cell => {
          cell.classList.remove('cell-in-selection');
          cell.classList.remove('cell-in-selection-erase');
        });
        el.gridCanvas.classList.remove('drag-active');
      }

      if (el.selectionActionsContainer) el.selectionActionsContainer.style.display = 'none';

      isBoxDragging = false;
      boxStartCell = null;
      lastSelectionBox = null;
      dragType = null;
      
      updateLegendCounts();
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

  let c_m = colVisual;
  let r_m = rowVisual;

  let xp = c_m;
  let yp = r_m;

  // Apply rotation to map c_m, r_m back to physical coordinate xp, yp
  if (rotation === 0) {
    xp = c_m;
    yp = r_m;
  } else if (rotation === 90) {
    xp = r_m;
    yp = (visualCols - 1) - c_m;
  } else if (rotation === 180) {
    xp = (visualCols - 1) - c_m;
    yp = (visualRows - 1) - r_m;
  } else if (rotation === 270) {
    xp = (visualRows - 1) - r_m;
    yp = c_m;
  }

  return { x: xp, y: yp };
}

function getVisualCoords(colVisual, rowVisual, cols, rows, rotation, side, invertY, startX, startY) {
  const isRotated90or270 = (rotation === 90 || rotation === 270);
  const visualCols = isRotated90or270 ? rows : cols;
  const visualRows = isRotated90or270 ? cols : rows;

  let c_screen = colVisual;
  let r_screen = rowVisual;

  // Compensate for CSS transforms (flipped/flipped-vertical) on BACK side so that visual coordinates don't flip
  if (side === 'back') {
    if (rotation === 90 || rotation === 270) {
      // Flipped vertically by CSS (flipped-vertical), so map DOM row index back to visual screen row
      r_screen = (visualRows - 1) - rowVisual;
    } else {
      // Flipped horizontally by CSS (flipped), so map DOM col index back to visual screen col
      c_screen = (visualCols - 1) - colVisual;
    }
  }

  const xv = c_screen + startX;
  let yv = r_screen;

  if (invertY) {
    yv = (visualRows - 1) - yv;
  }
  yv = yv + startY;

  return { x: xv, y: yv };
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
function renderGridCanvas() {
  if (!el.gridCanvas) return;

  const cols = parseInt(el.gridCols.value, 10) || 10;
  const rows = parseInt(el.gridRows.value, 10) || 10;
  const startX = parseInt(el.gridStartX.value, 10) || 0;
  const startY = parseInt(el.gridStartY.value, 10) || 0;
  const invertY = el.gridYInvert.checked;

  // Check if coordinate grid contains (0,0) based on start coordinates and dimensions
  const hasZeroZero = (startX <= 0 && (startX + cols - 1) >= 0) && (startY <= 0 && (startY + rows - 1) >= 0);

  el.gridCanvas.innerHTML = '';

  const isRotated90or270 = (currentRotation === 90 || currentRotation === 270);
  const visualCols = isRotated90or270 ? rows : cols;
  const visualRows = isRotated90or270 ? cols : rows;

  gridCells2D = Array.from({ length: visualRows }, () => []);

  el.gridCanvas.style.gridTemplateColumns = `repeat(${visualCols}, 1fr)`;
  el.gridCanvas.style.gridTemplateRows = `repeat(${visualRows}, 1fr)`;

  // Mirror effect animation class based on rotation
  if (currentSide === 'back') {
    if (currentRotation === 90 || currentRotation === 270) {
      el.gridCanvas.classList.add('flipped-vertical');
      el.gridCanvas.classList.remove('flipped');
    } else {
      el.gridCanvas.classList.add('flipped');
      el.gridCanvas.classList.remove('flipped-vertical');
    }
  } else {
    el.gridCanvas.classList.remove('flipped');
    el.gridCanvas.classList.remove('flipped-vertical');
  }

  // Render Visual Grid
  for (let r = 0; r < visualRows; r++) {
    for (let c = 0; c < visualCols; c++) {
      const physical = getPhysicalCoords(c, r, cols, rows, currentRotation, currentSide);
      const visual = getVisualCoords(c, r, cols, rows, currentRotation, currentSide, invertY, startX, startY);
      const coordKey = `${physical.x}_${physical.y}`;
      const val = gridData[coordKey] || '';

      const cell = document.createElement('div');
      cell.className = 'grid-cell';
      cell.dataset.x = visual.x;
      cell.dataset.y = visual.y;
      cell.dataset.c = c;
      cell.dataset.r = r;
      cell.dataset.key = coordKey;

      if (val !== '') {
        cell.classList.add('has-value');
      }

      // Check if this cell is the origin point (falls back to start cell if (0,0) is outside the grid bounds)
      const isOriginCell = hasZeroZero 
        ? (visual.x === 0 && visual.y === 0) 
        : (visual.x === startX && visual.y === startY);

      if (isOriginCell) {
        cell.classList.add('cell-is-origin');
      }

      // Check if visual cell (c, r) is completely inside the wafer boundary circle
      const u1 = (2 * c - visualCols) / visualCols;
      const u2 = (2 * (c + 1) - visualCols) / visualCols;
      const v1 = (2 * r - visualRows) / visualRows;
      const v2 = (2 * (r + 1) - visualRows) / visualRows;

      const maxU2 = Math.max(u1 * u1, u2 * u2);
      const maxV2 = Math.max(v1 * v1, v2 * v2);
      const dMax2 = maxU2 + maxV2;

      const completelyInside = (dMax2 <= 1.0);

      if (completelyInside) {
        cell.classList.add('cell-inside-wafer');
      } else {
        cell.classList.add('cell-outside-wafer');
      }

      updateCellStyles(cell, val);

      const showAnno = el.showAnnotations ? el.showAnnotations.checked : true;
      cell.textContent = val !== '' ? val : (showAnno ? `${visual.x},${visual.y}` : '');
      if (val === '') {
        cell.style.fontSize = '0.65rem';
        cell.style.color = 'var(--text-dim)';
      } else {
        cell.style.fontSize = '0.8rem';
        cell.style.color = '#fff';
      }

      cell.title = `좌표: (${visual.x}, ${visual.y})\n값: ${val !== '' ? val : 'Empty'}`;

      gridCells2D[r][c] = cell;
      el.gridCanvas.appendChild(cell);
    }
  }

  updateNotchPosition();
  updateLegendCounts();
}

function handleCellClick(cell, event) {
  if (isOriginMode) {
    const c = parseInt(cell.dataset.c, 10);
    const r = parseInt(cell.dataset.r, 10);
    const cols = parseInt(el.gridCols.value, 10) || 10;
    const rows = parseInt(el.gridRows.value, 10) || 10;
    const invertY = el.gridYInvert.checked;

    // Calculate 0-indexed visual coordinate (with startX=0, startY=0)
    const visualCoords = getVisualCoords(c, r, cols, rows, currentRotation, currentSide, invertY, 0, 0);

    // Adjust start offsets so this cell becomes (0,0) visually
    const newStartX = -visualCoords.x;
    const newStartY = -visualCoords.y;

    el.gridStartX.value = newStartX;
    el.gridStartY.value = newStartY;

    // Turn off origin mode
    isOriginMode = false;
    el.btnSetOrigin.classList.remove('active');
    el.btnSetOrigin.style.borderColor = '';
    el.btnSetOrigin.style.color = '';
    el.gridCanvas.classList.remove('origin-mode-active');

    // Redraw grid
    renderGridCanvas();
    return;
  }

  let isRight = isRightDrag;
  if (event) {
    isRight = (event.button === 2 || event.buttons === 2);
  }

  const key = cell.dataset.key;
  if (isRight) {
    // Clear cell
    gridData[key] = '';
    const showAnno = el.showAnnotations ? el.showAnnotations.checked : true;
    cell.textContent = showAnno ? `${cell.dataset.x},${cell.dataset.y}` : '';
    cell.style.fontSize = '0.65rem';
    cell.style.color = 'var(--text-dim)';
    updateCellStyles(cell, '');
    cell.title = `좌표: (${cell.dataset.x}, ${cell.dataset.y})\n값: Empty`;
    cell.classList.remove('has-value');
  } else {
    // Draw cell
    if (activeBrush !== undefined && activeBrush !== null) {
      // 드래그 드로잉 중(event가 없는 경우)이고 이미 값이 채워져 있다면 기존 값 보존
      const existingVal = gridData[key] || '';
      if (!event && existingVal !== '') {
        return;
      }
      gridData[key] = activeBrush;
      cell.textContent = activeBrush;
      cell.style.fontSize = '0.8rem';
      cell.style.color = '#fff';
      updateCellStyles(cell, activeBrush);
      cell.title = `좌표: (${cell.dataset.x}, ${cell.dataset.y})\n값: ${activeBrush}`;
      cell.classList.add('has-value');
    }
  }
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

  const updates = [];
  
  // Serialize current grid metadata config if the table supports it
  let gridMetaStr = null;
  if (tableSchema.column_types && tableSchema.column_types['grid_metadata']) {
    const gridMeta = {
      grid_cols: parseInt(el.gridCols.value, 10) || 10,
      grid_rows: parseInt(el.gridRows.value, 10) || 10,
      grid_start_x: 0,
      grid_start_y: 0,
      grid_y_invert: false,
      rotation: 0,
      side: 'front'
    };
    gridMetaStr = JSON.stringify(gridMeta);
  }

  const cols = parseInt(el.gridCols.value, 10) || 10;
  const rows = parseInt(el.gridRows.value, 10) || 10;
  const startX = parseInt(el.gridStartX.value, 10) || 0;
  const startY = parseInt(el.gridStartY.value, 10) || 0;
  const invertY = el.gridYInvert.checked;

  const isRotated90or270 = (currentRotation === 90 || currentRotation === 270);
  const visualCols = isRotated90or270 ? rows : cols;
  const visualRows = isRotated90or270 ? cols : rows;

  for (let r = 0; r < visualRows; r++) {
    for (let c = 0; c < visualCols; c++) {
      // Determine if visual cell (c, r) is inside the wafer boundary
      const u1 = (2 * c - visualCols) / visualCols;
      const u2 = (2 * (c + 1) - visualCols) / visualCols;
      const v1 = (2 * r - visualRows) / visualRows;
      const v2 = (2 * (r + 1) - visualRows) / visualRows;

      const maxU2 = Math.max(u1 * u1, u2 * u2);
      const maxV2 = Math.max(v1 * v1, v2 * v2);
      const dMax2 = maxU2 + maxV2;

      const completelyInside = (dMax2 <= 1.0);
      if (!completelyInside) continue; // Skip blocked outside-wafer cells

      const physical = getPhysicalCoords(c, r, cols, rows, currentRotation, currentSide);
      const visual = getVisualCoords(c, r, cols, rows, currentRotation, currentSide, invertY, startX, startY);
      const key = `${physical.x}_${physical.y}`;
      const val = gridData[key] || '';

      let valParsed = null;
      if (val !== '') {
        valParsed = valType === 'number' ? Number(val) : val;
      }

      let xParsed = xType === 'number' ? parseInt(physical.x, 10) : String(physical.x);
      let yParsed = yType === 'number' ? parseInt(physical.y, 10) : String(physical.y);

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
    }
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
      const u1 = (2 * c - visualCols) / visualCols;
      const u2 = (2 * (c + 1) - visualCols) / visualCols;
      const v1 = (2 * r - visualRows) / visualRows;
      const v2 = (2 * (r + 1) - visualRows) / visualRows;
      const maxU2 = Math.max(u1 * u1, u2 * u2);
      const maxV2 = Math.max(v1 * v1, v2 * v2);
      if (maxU2 + maxV2 <= 1.0) {
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

function selectEdgeCells(target) {
  if (!el.gridCanvas) return;
  const cells = el.gridCanvas.querySelectorAll('.grid-cell');
  
  // Clear any existing selection highlight
  cells.forEach(cell => {
    cell.classList.remove('cell-in-selection');
    cell.classList.remove('cell-in-selection-erase');
  });

  const { isE1, isE2 } = getEdgeClassification();
  const targetMap = target === 1 ? isE1 : isE2;

  let count = 0;
  cells.forEach(cell => {
    const c = parseInt(cell.dataset.c, 10);
    const r = parseInt(cell.dataset.r, 10);
    if (targetMap[r] && targetMap[r][c]) {
      cell.classList.add('cell-in-selection');
      count++;
    }
  });

  if (count > 0) {
    if (el.selectionActionsContainer) el.selectionActionsContainer.style.display = 'flex';
    el.gridStatusCoords.textContent = `Selected ${count} E${target} cells`;
  } else {
    if (el.selectionActionsContainer) el.selectionActionsContainer.style.display = 'none';
    alert(`격자 상에 E${target} 조건에 부합하는 셀이 존재하지 않습니다.`);
  }
}

function autoPaintE1E2() {
  if (!el.gridCanvas) return;
  
  // Ensure E1 and E2 exist in legend
  let legendUpdated = false;
  if (!legend.some(item => item.value === 'E1')) {
    legend.push({ value: 'E1', desc: 'Edge 1 (Outermost)', color: '#8b5cf6' }); // Purple
    legendUpdated = true;
  }
  if (!legend.some(item => item.value === 'E2')) {
    legend.push({ value: 'E2', desc: 'Edge 2 (Inner Outer)', color: '#ec4899' }); // Pink
    legendUpdated = true;
  }
  if (legendUpdated) {
    saveLegendToStorage();
    renderLegendTable();
  }

  const { isE1, isE2 } = getEdgeClassification();
  const cells = el.gridCanvas.querySelectorAll('.grid-cell');
  
  let e1Count = 0;
  let e2Count = 0;

  cells.forEach(cell => {
    const c = parseInt(cell.dataset.c, 10);
    const r = parseInt(cell.dataset.r, 10);
    const key = cell.dataset.key;

    if (isE1[r] && isE1[r][c]) {
      gridData[key] = 'E1';
      e1Count++;
    } else if (isE2[r] && isE2[r][c]) {
      gridData[key] = 'E2';
      e2Count++;
    }
  });

  renderGridCanvas();
  alert(`E1/E2 자동 페인팅 완료!\n- E1 (가장 외곽 1칸): ${e1Count}개 셀\n- E2 (외곽에서 2칸): ${e2Count}개 셀`);
}

function fillSelectedCells() {
  if (!activeBrush) {
    alert('페인팅 브러쉬를 먼저 선택하십시오.');
    return;
  }
  if (!el.gridCanvas) return;
  const selectedCells = el.gridCanvas.querySelectorAll('.grid-cell.cell-in-selection');
  if (selectedCells.length === 0) return;

  selectedCells.forEach(cell => {
    const key = cell.dataset.key;
    gridData[key] = activeBrush;
    cell.textContent = activeBrush;
    cell.style.fontSize = '0.8rem';
    cell.style.color = '#fff';
    updateCellStyles(cell, activeBrush);
    cell.title = `좌표: (${cell.dataset.x}, ${cell.dataset.y})\n값: ${activeBrush}`;
    cell.classList.add('has-value');
    cell.classList.remove('cell-in-selection');
  });

  if (el.selectionActionsContainer) el.selectionActionsContainer.style.display = 'none';
}

function clearSelectedCells() {
  if (!el.gridCanvas) return;
  const selectedCells = el.gridCanvas.querySelectorAll('.grid-cell.cell-in-selection');
  if (selectedCells.length === 0) return;

  selectedCells.forEach(cell => {
    const key = cell.dataset.key;
    gridData[key] = '';
    const showAnno = el.showAnnotations ? el.showAnnotations.checked : true;
    cell.textContent = showAnno ? `${cell.dataset.x},${cell.dataset.y}` : '';
    cell.style.fontSize = '0.65rem';
    cell.style.color = 'var(--text-dim)';
    updateCellStyles(cell, '');
    cell.title = `좌표: (${cell.dataset.x}, ${cell.dataset.y})\n값: Empty`;
    cell.classList.remove('has-value');
    cell.classList.remove('cell-in-selection');
  });

  if (el.selectionActionsContainer) el.selectionActionsContainer.style.display = 'none';
}

function copyGridToExcel() {
  if (!gridCells2D || gridCells2D.length === 0) {
    alert('격자가 생성되어 있지 않습니다.');
    return;
  }

  const visualRows = gridCells2D.length;
  const visualCols = gridCells2D[0] ? gridCells2D[0].length : 0;
  
  const isFlippedHoriz = el.gridCanvas ? el.gridCanvas.classList.contains('flipped') : false;
  const isFlippedVert = el.gridCanvas ? el.gridCanvas.classList.contains('flipped-vertical') : false;

  const matrix = [];

  // Determine row processing order based on vertical mirroring (flipped-vertical scaleY(-1))
  const rowStart = isFlippedVert ? visualRows - 1 : 0;
  const rowEnd = isFlippedVert ? -1 : visualRows;
  const rowStep = isFlippedVert ? -1 : 1;

  // Determine col processing order based on horizontal mirroring (flipped scaleX(-1))
  const colStart = isFlippedHoriz ? visualCols - 1 : 0;
  const colEnd = isFlippedHoriz ? -1 : visualCols;
  const colStep = isFlippedHoriz ? -1 : 1;

  for (let r = rowStart; r !== rowEnd; r += rowStep) {
    const rowCells = [];
    for (let c = colStart; c !== colEnd; c += colStep) {
      const cell = gridCells2D[r]?.[c];
      if (cell) {
        const key = cell.dataset.key;
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
