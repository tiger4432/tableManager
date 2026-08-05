// [1d] COORDINATE-TABLE PASTE — an Excel 2D block whose header row is X and whose first
// column is Y, read as DATABASE COORDINATES.
// Run: node client2/tests/coord_table_paste_harness.mjs [--json]
//
// SAME TECHNIQUE as company_roundtrip_harness.mjs: map_editor.js imports ./config.js which
// touches `window` at module scope, so it cannot be imported in node. The functions under
// test stay module-private; their declarations are sliced out of the SOURCE TEXT and
// evaluated in a vm sandbox with stubs for module state.
//
// 🔴 WHY A CELL COUNT PROVES NOTHING HERE. A paste that reads the headers as SCREEN
//    POSITIONS instead of DB COORDINATES writes exactly as many cells as a correct one. The
//    grid looks perfectly aligned and every value is on the wrong die. So every assertion in
//    this file is KEY -> VALUE, and the headline evidence is a DIFFERENTIAL: the same table,
//    read under three misread frames, each producing the SAME cell count and a different die
//    set. If that differential were 0 the fixture would prove nothing.
//
// 🔴 THE ORACLE IS NOT `getCanvasCellFromDb` RUN BACKWARDS. Comparing a function with its own
//    inverse is a self-comparison: a uniform error in the origin box moves both sides and
//    stays green (map-pm lesson, 2026-07-30). Instead the expected canvas cell is computed
//    here from the SPEC formula (MAP_EDITOR_SPEC, origin box) written out independently,
//    against a box whose four numbers are PINNED AS LITERALS below. A dropped `box.minC`, a
//    `minR` where `maxR` belongs, or a lost `startX` all move the literals and go red.
//
// FAILS LOUDLY (exit 2) when a function cannot be extracted or a mutation anchor is not
// unique. A harness that goes green because it stopped finding the code is worse than none.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..', '..');
const JSON_OUT = process.argv.includes('--json');

function die(msg) {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  process.exit(2);
}

// Line endings normalised: the repo stores these files with CRLF and every mutation anchor
// below is written with `\n`. Without this the anchors miss and the run dies at exit 2.
const readSrc = (...p) => readFileSync(join(...p), 'utf8').replace(/\r\n/g, '\n');
const WORK_MAP = readSrc(ROOT, 'client2', 'src', 'map_editor.js');
const WORK_DOE = readSrc(ROOT, 'client2', 'src', 'doe_bands.js');
const WORK_TSV = readSrc(ROOT, 'client2', 'src', 'tsv.js');

function sliceBalanced(src, startIdx, open, close) {
  let i = src.indexOf(open, startIdx);
  if (i < 0) return null;
  let depth = 0;
  for (let j = i; j < src.length; j++) {
    const ch = src[j];
    if (ch === open) depth++;
    else if (ch === close) { depth--; if (depth === 0) return src.slice(startIdx, j + 1); }
  }
  return null;
}
// 🔴 THE FIRST-MATCH TRAP, CLOSED. `valid_die_authoring_harness` scored a COMMENT because its
//    slicer took the first textual occurrence of a name. Here the declaration regex is
//    anchored at a line start (`^`, multiline), which no comment line satisfies, and the
//    match count is asserted to be exactly 1.
function fnFrom(src, label, name) {
  const re = new RegExp(`^(?:async\\s+)?function\\s+${name}\\s*\\(`, 'gm');
  const hits = [...src.matchAll(re)];
  if (hits.length === 0) die(`function ${name} not found at top level in ${label}`);
  if (hits.length > 1) die(`function ${name} declared ${hits.length} times in ${label} — ambiguous slice`);
  const out = sliceBalanced(src, hits[0].index, '{', '}');
  if (!out) die(`unbalanced braces for ${name} in ${label}`);
  return out;
}
function constFrom(src, label, name) {
  const re = new RegExp(`^const\\s+${name}\\s*=`, 'gm');
  const hits = [...src.matchAll(re)];
  if (hits.length === 0) die(`const ${name} not found at top level in ${label}`);
  if (hits.length > 1) die(`const ${name} declared ${hits.length} times in ${label} — ambiguous slice`);
  let depth = 0;
  for (let j = hits[0].index; j < src.length; j++) {
    const ch = src[j];
    if (ch === '[' || ch === '{' || ch === '(') depth++;
    else if (ch === ']' || ch === '}' || ch === ')') depth--;
    else if (ch === ';' && depth === 0) return src.slice(hits[0].index, j + 1);
  }
  die(`no terminator for const ${name} in ${label}`);
}

// ── THE FIXTURE: every defect axis ACTIVE ───────────────────────────────────────
// The brief's requirement, restated as fixture constraints. Each line is here because
// without it a whole class of defect is INVISIBLE, not because it is realistic:
//   startX 3 / startY 2   — a lost START term shifts every die. With 0 it cannot.
//   invertY true          — the `box.maxR - (y - startY)` branch is the one under test.
//                           With false, a maxR/minR confusion is unobservable.
//   rot 90 + back         — rotation and mirror both engaged.
//   chipX 2 != chipY 3    — a pitch swap under rot 90/270 shows up.
//   COLS 11 != ROWS 9     — a transposed read cannot pass a dimension check by accident.
//   edgeMargin 1, NOT 0   — `physNum`'s `|| dflt` turns a declared 0 into 3.0.
//   box.minC != 0         — ASSERTED below, so a dropped bbox term cannot hide.
const DIA = 20, EM = 1, CHIP_X = 2, CHIP_Y = 3;
const COLS = 11, ROWS = 9;
const ROT = 90, SIDE = 'back';
const START_X = 3, START_Y = 2, INVERT_Y = true;
const VC = (ROT === 90 || ROT === 270) ? ROWS : COLS;   // visual columns = 9
const VR = (ROT === 90 || ROT === 270) ? COLS : ROWS;   // visual rows    = 11

function inputStub(v) { return { value: String(v) }; }
function makeEl(over) {
  return Object.assign({
    physWaferDia: inputStub(DIA), physEdgeMargin: inputStub(EM),
    physChipX: inputStub(CHIP_X), physChipY: inputStub(CHIP_Y),
    physOffsetX: inputStub(0), physOffsetY: inputStub(0),
    gridCols: inputStub(COLS), gridRows: inputStub(ROWS),
    gridStartX: inputStub(START_X), gridStartY: inputStub(START_Y),
    gridYInvert: { checked: INVERT_Y },
    showAnnotations: { checked: true },
    gridCanvas: null, btnCopyExcel: null,
    copyHeaderToggle: { checked: false },
  }, over || {});
}

const THEME = {
  outBg: '#e2e6ec', line: '#d1d5db', lineStrong: '#b9c0cb', insideEmpty: '#eef6f1',
  textEmpty: '#47536b', textOut: '#5b6779', waferEdge: '#1f2733',
  wmFront: '#eef4fd', wmBack: '#fdf6e8', accent: '#1a66d0', success: '#177245',
  warning: '#8a5a00', danger: '#c22f2f', dangerWeak: '#f6dede', rangeFill: '#e3ecfa',
  surface: '#ffffff',
};

const MAP_FNS = [
  'physNum', 'gridDimNum', 'validDieBasis', 'isValidDieAt',
  'getTransformedPhysicalConfig', 'isCellInsideWaferFast', 'getScreenShift',
  'getDieIndex', 'getWaferBoundingBox', 'getDbCoords', 'getCanvasCellFromDb',
  'isCellInsideWafer', 'parseCssColor', 'toExcelHex', 'cellFillColor',
  'getGridCellObject', 'getVisualGridDimensions', 'escapeHtmlAttr',
  'isProtectedFCell', 'eachSavableCell', 'classifyUnsavableCells', 'serverCellKeySet',
  'computeLegendCounts',
  'headerSpanFor', 'distributeSpans', 'auxColumnSpans',
  'copyHeaderEnabled', 'mapKeyGroupLabel', 'copyHeaderGroups', 'copyHeaderAuxRows',
  'colHeaderWord', 'copyTitleText', 'computeNotchCell', 'notchMarkCell', 'auxHeadWords',
  'copyGridToExcel',
  // the positional paste path — this harness's NEGATIVE case runs it end to end
  'auxHeaderInLine', 'readCompanyMapBlock', 'checkPasteAgainstFrame',
  'applyPastedGridRows', 'pastedCellCount',
  // [1d] the coordinate path
  'coordRulerTicks', 'readCoordTableBlock', 'planCoordPaste',
];
const MAP_CONSTS = ['UNLISTED_VALUE_FILL', 'HDR_COL_PX', 'HDR_PAD_PX', 'HDR_CHAR_PX',
  'HDR_MIN_SPAN', 'HDR_MAX_SPAN', 'HDR_GAP_COLS', 'pasteBlank', 'pasteAt',
  'COORD_MIN_TICKS', 'coordInt', 'coordMonotonic'];

function buildSandbox(src, label, elOver) {
  const parts = [];
  MAP_FNS.forEach(n => parts.push(fnFrom(src, label, n)));
  MAP_CONSTS.forEach(n => parts.push(constFrom(src, label, n)));
  ['QUOTE', 'TAB'].forEach(n => parts.push(constFrom(WORK_TSV, 'tsv.js', n)));
  ['normalizeNewlines', 'parseTsv', 'needsQuote', 'quoteField', 'serializeTsv']
    .forEach(n => parts.push(fnFrom(WORK_TSV, 'tsv.js', n)));
  ['ZONES', 'ZONE_LABEL', 'DOE_COLUMNS', 'IGNORED_HEADERS'].forEach(n => parts.push(constFrom(WORK_DOE, 'doe_bands.js', n)));
  ['parseMaterialList', 'columnIdByHeader', 'looksLikeHeader'].forEach(n => parts.push(fnFrom(WORK_DOE, 'doe_bands.js', n)));

  const captured = { html: null, text: null, toasts: [], confirms: [], fetches: [] };
  const ctx = {
    console: Object.assign(Object.create(console), { debug: () => {} }),
    physFrameOverride: null,
    currentRotation: ROT, currentSide: SIDE,
    validDie: null, boundingBoxCache: {}, el: makeEl(elOver),
    gridData: {}, gridCells2D: {}, legend: [],
    loadedFCells: new Set(),
    selectedTable: 'bonding_map',
    tableSchema: { map_key_columns: ['base'] },
    loadedIdentity: { table: 'bonding_map', mapKey: '4B12' },
    serverCellKeys: { table: 'bonding_map', mapKey: '4B12', keys: new Set() },
    activeBrush: '',
    isOverlayLocked: () => false,
    getThemeColors: () => THEME,
    getCurrentMapKey: () => '4B12',
    __captured: captured,
  };
  ctx.fetch = (...a) => { captured.fetches.push(String(a[0])); return Promise.reject(new Error('no network')); };
  ctx.confirm = (m) => { captured.confirms.push(m); return true; };
  ctx.showToast = (msg, kind) => { captured.toasts.push({ msg, kind }); };
  ctx.writeClipboardRich = (html, text) => { captured.html = html; captured.text = text; return true; };
  vm.createContext(ctx);
  try {
    vm.runInContext(parts.join('\n\n')
      + '\nglobalThis.__h = { getGridCellObject, getTransformedPhysicalConfig, getWaferBoundingBox,'
      + ' getVisualGridDimensions, getDbCoords, getCanvasCellFromDb, getDieIndex,'
      + ' copyGridToExcel, notchMarkCell, copyTitleText, classifyUnsavableCells,'
      + ' readCompanyMapBlock, checkPasteAgainstFrame, applyPastedGridRows, pastedCellCount,'
      + ' coordRulerTicks, readCoordTableBlock, planCoordPaste, serializeTsv, parseTsv };', ctx);
  } catch (e) {
    die(`sandbox evaluation failed for ${label} — ${e && e.message ? e.message : e}`);
  }
  return { ctx, H: ctx.__h, captured };
}

// the app's own cell factory builds gridCells2D — the harness never hand-rolls a cell
function buildCells(sb) {
  const { ctx, H } = sb;
  const pc = H.getTransformedPhysicalConfig(null, ROT, SIDE);
  ctx.gridCells2D = {};
  for (let r = 0; r < VR; r++) {
    ctx.gridCells2D[r] = {};
    for (let c = 0; c < VC; c++) ctx.gridCells2D[r][c] = H.getGridCellObject(c, r, VC, VR, pc, 700, 700);
  }
}

// A varied starting grid, so "outside the table's rectangle is untouched" is observable.
function paintFixture(sb) {
  const { ctx } = sb;
  ctx.gridData = {};
  let i = 0;
  for (let r = 0; r < VR; r++) {
    for (let c = 0; c < VC; c++) {
      const cell = ctx.gridCells2D[r][c];
      if (!cell || !cell.inside) continue;
      i++;
      if (i % 7 === 0) continue;
      ctx.gridData[cell.key] = (i % 5 === 0) ? 'F' : ((i % 11 === 0) ? 'E1' : '1');
    }
  }
}

function frameOf(sb) {
  const { visualCols, visualRows } = sb.H.getVisualGridDimensions();
  return {
    visualCols, visualRows,
    title: sb.H.copyTitleText(),
    notch: sb.H.notchMarkCell(ROT, SIDE),
  };
}

function coordFrameOf() {
  return {
    cols: COLS, rows: ROWS, rotation: ROT, side: SIDE,
    invertY: INVERT_Y, startX: START_X, startY: START_Y,
    visualCols: VC, visualRows: VR,
  };
}

function gridSnapshot(sb) {
  const out = {};
  for (let r = 0; r < VR; r++) {
    for (let c = 0; c < VC; c++) {
      const co = sb.ctx.gridCells2D[r][c];
      if (co) out[co.key] = sb.ctx.gridData[co.key] || '';
    }
  }
  return out;
}

// ── assertions ──────────────────────────────────────────────────────────────────
let pass = 0;
const fails = [];
const J = (v) => JSON.stringify(v);
function chk(group, what, got, want) {
  if (J(got) === J(want)) { pass++; return true; }
  fails.push({ group, what, got, want });
  return false;
}
function chkTrue(group, what, cond, detail) {
  if (cond) { pass++; return true; }
  fails.push({ group, what, got: detail === undefined ? false : detail, want: true });
  return false;
}

const evidence = {};

// ════════════════════════════════════════════════════════════════════════════════
// 0 — THE FIXTURE IS ADVERSARIAL. Assert the axes are live before scoring anything.
// ════════════════════════════════════════════════════════════════════════════════
const base = buildSandbox(WORK_MAP, 'working tree');
buildCells(base);
paintFixture(base);
const BOX = base.H.getWaferBoundingBox(null, ROT, SIDE);

{
  chkTrue('fixture', 'box.minC != 0 (a dropped bbox term cannot hide)', BOX.minC !== 0, BOX);
  chkTrue('fixture', 'box.minR != 0', BOX.minR !== 0, BOX);
  chkTrue('fixture', 'START X/Y are non-zero (a dropped START term cannot hide)',
    START_X !== 0 && START_Y !== 0, { START_X, START_Y });
  chkTrue('fixture', 'invertY is ON (the maxR branch is the one under test)', INVERT_Y === true);
  chkTrue('fixture', 'chipX != chipY and COLS != ROWS', CHIP_X !== CHIP_Y && COLS !== ROWS);
  chkTrue('fixture', 'the frame is NOT the identity', ROT !== 0 || SIDE !== 'front');
  evidence.fixture = { box: BOX, COLS, ROWS, VC, VR, ROT, SIDE, START_X, START_Y, INVERT_Y };
}

// 🔴 THE BOX IS PINNED AS A LITERAL. The oracle below multiplies these four numbers into
//    every expected cell. Pinning them means a change in wafer geometry that silently moves
//    the coordinate system fails HERE, with a name, instead of quietly re-baselining the
//    whole oracle. If this line goes red the fixture changed — re-derive, do not edit blind.
const BOX_PINNED = { minC: 2, maxC: 6, minR: 2, maxR: 8 };
{
  chk('fixture', 'origin box is the pinned literal', BOX, BOX_PINNED);
}

// ── THE INDEPENDENT ORACLE ──────────────────────────────────────────────────────
// The spec formula, written out here and NOT by calling the code under test:
//     c = x - startX + box.minC
//     r = invertY ? box.maxR - (y - startY) : (y - startY) + box.minR
// This is the ONLY place in this file that decides where a DB coordinate belongs.
function oracleCell(x, y) {
  const c = x - START_X + BOX.minC;
  const r = INVERT_Y ? (BOX.maxR - (y - START_Y)) : ((y - START_Y) + BOX.minR);
  return { c, r };
}

// ════════════════════════════════════════════════════════════════════════════════
// 1 — THE ORACLE AGREES WITH WHAT PUSH SERIALISES
//     Every rendered cell states a DB coordinate (`cellObj.x/y`, produced by `getDbCoords`,
//     which is exactly what ⚡ Push writes). Running the oracle on that coordinate must land
//     back on the same canvas square, for EVERY cell — not a sample.
// ════════════════════════════════════════════════════════════════════════════════
{
  const wrong = [];
  for (let r = 0; r < VR; r++) {
    for (let c = 0; c < VC; c++) {
      const co = base.ctx.gridCells2D[r][c];
      const at = oracleCell(co.x, co.y);
      if (at.c !== c || at.r !== r) wrong.push({ c, r, x: co.x, y: co.y, oracle: at });
    }
  }
  chk('oracle', 'the spec formula reproduces every rendered cell from its serialised x/y',
    wrong, []);
  evidence.oracleDomain = { cells: VC * VR, mismatches: wrong.length };
}

// ── THE COORDINATE TABLE ────────────────────────────────────────────────────────
// A sub-rectangle of the grid, NOT the whole thing, so "outside the table is untouched" is
// observable. The X axis starts away from the grid's first column and the Y axis is listed
// in NATURAL EXCEL ORDER (increasing downward) — which under invertY=true means the table's
// TOP row lands on the screen's BOTTOM. That inversion is the whole point of the round.
const TBL_X = [5, 6, 7, 8];                    // DB x
const TBL_Y = [3, 4, 5, 6, 7];                 // DB y, increasing down the pasted block
// Values encode their own intended coordinate so the evidence is readable and so a
// transposition or an offset cannot coincidentally match. Two deliberate BLANKS: inside the
// table's rectangle a blank means "clear this die", which is a write, not a skip.
const BLANKS = new Set(['6:5', '8:3']);
function tblValue(x, y) { return BLANKS.has(`${x}:${y}`) ? '' : `v${x}_${y}`; }

function buildTableText(sb) {
  const rows = [['', ...TBL_X.map(String)]];
  TBL_Y.forEach(y => rows.push([String(y), ...TBL_X.map(x => tblValue(x, y))]));
  return sb.H.serializeTsv(rows);
}
const TABLE_TEXT = buildTableText(base);

// ════════════════════════════════════════════════════════════════════════════════
// 2 — DETECTION. The predicate is structural and it says so about the real artifact.
// ════════════════════════════════════════════════════════════════════════════════
let coord;
{
  coord = base.H.readCoordTableBlock(TABLE_TEXT);
  chk('detect', 'the block is recognised', coord.kind, 'ok');
  chk('detect', 'the axes are read as DB coordinates, verbatim',
    { minX: coord.minX, maxX: coord.maxX, minY: coord.minY, maxY: coord.maxY, nx: coord.nx, ny: coord.ny },
    { minX: 5, maxX: 8, minY: 3, maxY: 7, nx: 4, ny: 5 });
  chk('detect', 'every table cell is emitted (blanks included)', coord.cells.length, TBL_X.length * TBL_Y.length);
  chk('detect', 'the distinct non-blank values are collected for the legend gateway',
    coord.values.length, TBL_X.length * TBL_Y.length - BLANKS.size);
  evidence.detect = { kind: coord.kind, x: [coord.minX, coord.maxX], y: [coord.minY, coord.maxY] };
}

// ════════════════════════════════════════════════════════════════════════════════
// 3 — PER-CELL PLACEMENT under the NON-IDENTITY frame. key -> value, every cell.
// ════════════════════════════════════════════════════════════════════════════════
// A protected cell INSIDE the table's rectangle, so the confirm's number and the number
// that actually lands are scored against each other with a real gap between them.
const PROT = oracleCell(7, 4);
let placedRun;
{
  const sb = buildSandbox(WORK_MAP, 'placement');
  buildCells(sb);
  paintFixture(sb);
  const protKey = sb.ctx.gridCells2D[PROT.r][PROT.c].key;
  sb.ctx.loadedFCells = new Set([protKey]);
  sb.ctx.gridData[protKey] = 'F';

  const before = gridSnapshot(sb);
  const cf = coordFrameOf();
  const plan = sb.H.planCoordPaste(coord, cf);
  chk('place', 'nothing falls off the grid', plan.offGrid, []);
  const stats = sb.H.applyPastedGridRows({ rows: plan.rows }, Object.assign({}, frameOf(sb), { notch: null }));
  const after = gridSnapshot(sb);

  // ── the key->value assertion, built ONLY from the oracle ──────────────────────
  const expected = {};       // key -> value, for the table's own rectangle
  const landed = {};
  const offOracle = [];
  TBL_Y.forEach(y => TBL_X.forEach(x => {
    const at = oracleCell(x, y);
    if (at.c < 0 || at.c >= VC || at.r < 0 || at.r >= VR) { offOracle.push({ x, y, at }); return; }
    const key = sb.ctx.gridCells2D[at.r][at.c].key;
    // the protected die is the one cell the paste must NOT move
    expected[key] = (key === protKey) ? 'F' : tblValue(x, y);
    landed[key] = after[key];
  }));
  chk('place', 'the oracle itself puts every table cell on the grid', offOracle, []);
  chk('place', 'every table cell landed on the die its DB coordinate names (key -> value)',
    landed, expected);

  // and the dies OUTSIDE the table's rectangle are byte-identical
  const rectKeys = new Set(Object.keys(expected));
  const outsideChanged = Object.keys(before)
    .filter(k => !rectKeys.has(k) && before[k] !== after[k])
    .map(k => ({ key: k, before: before[k], after: after[k] }));
  chk('place', 'dies outside the table rectangle are untouched', outsideChanged, []);

  // INV ⑥ — the confirm's number and the number that lands are ONE quantity
  chk('place', "the confirm's count equals what actually landed",
    { placed: plan.placed, cleared: plan.cleared },
    { placed: stats.set, cleared: stats.cleared });
  chk('place', 'the protected die was blocked, not overwritten', stats.blocked, 1);
  chk('place', 'the protected die still holds its own value', after[protKey], 'F');

  placedRun = { sb, plan, stats, after, expected, protKey };
  evidence.placement = {
    box: BOX,
    perCell: TBL_Y.map(y => TBL_X.map(x => {
      const at = oracleCell(x, y);
      const co = sb.ctx.gridCells2D[at.r][at.c];
      return { x, y, canvas: [at.c, at.r], key: co.key, value: after[co.key] };
    })).flat(),
    stats, confirmCount: { placed: plan.placed, cleared: plan.cleared },
  };
}

// ════════════════════════════════════════════════════════════════════════════════
// 4 — THE DIFFERENTIAL. Three misreadings, each placing the SAME number of cells on a
//     DIFFERENT set of dies. This is the whole reason a count-based check is worthless.
// ════════════════════════════════════════════════════════════════════════════════
// 🔴 THE METRIC IS KEY -> VALUE, NOT A DIE SET. Measured while writing this file: the
//    "y-invert ignored" misreading writes onto the SAME 18 dies as a correct read — the
//    rectangle is its own mirror image — and only the VALUES move. A set-difference metric
//    scored that misreading as 1 wrong and would have called it nearly correct. It is 15
//    dies wrong. A comparison that is not per-cell measures the wrong thing.
{
  const cellsOnGrid = (m) => Object.values(m).filter(v => v !== '').length;
  const diffMap = (a, b) => {
    const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
    return [...keys].filter(k => (a[k] || '') !== (b[k] || ''));
  };

  // the correct placement, straight from the oracle
  const rightMap = {};
  TBL_Y.forEach(y => TBL_X.forEach(x => {
    const at = oracleCell(x, y);
    rightMap[placedRun.sb.ctx.gridCells2D[at.r][at.c].key] = tblValue(x, y);
  }));

  const cases = [];

  // ⓐ read the headers as SCREEN POSITIONS (the positional path's addressing) — the exact
  //    mistake the round is about. Table row i, column j -> visual (r=i, c=j).
  {
    const m = {};
    TBL_Y.forEach((y, i) => TBL_X.forEach((x, j) => {
      const co = base.ctx.gridCells2D[i] ? base.ctx.gridCells2D[i][j] : null;
      if (co) m[co.key] = tblValue(x, y);
    }));
    cases.push(['headers read as screen positions', m]);
  }
  // ⓑ/ⓒ the frame itself misread — same addressing, wrong origin / wrong y direction
  const pick = (o, k, d) => (o[k] !== undefined ? o[k] : d);
  [['START X/Y ignored (origin 0)', { startX: 0, startY: 0 }],
   ['y-invert ignored', { invertY: false }]].forEach(([name, over]) => {
    const m = {};
    coord.cells.forEach(t => {
      const at = base.H.getCanvasCellFromDb(t.x, t.y, COLS, ROWS, ROT, SIDE,
        pick(over, 'invertY', INVERT_Y), pick(over, 'startX', START_X), pick(over, 'startY', START_Y));
      const co = (base.ctx.gridCells2D[at.r] || {})[at.c];
      if (co) m[co.key] = t.value;
    });
    cases.push([name, m]);
  });

  const rightN = cellsOnGrid(rightMap);
  const diffs = cases.map(([name, m]) => {
    const d = diffMap(rightMap, m);
    return {
      misread: name,
      cellsPlaced: cellsOnGrid(m),
      sameCount: cellsOnGrid(m) === rightN,
      diesWrong: d.length,
      sample: d.slice(0, 4).map(k => ({ die: k, correct: rightMap[k] || '(empty)', misread: m[k] || '(absent)' })),
    };
  });

  // the headline: the positional misreading writes the SAME NUMBER of cells and gets every
  // one of them onto the wrong die. That is M4 stated as a measurement.
  const positional = diffs[0];
  chk('differential', 'the positional misreading places the SAME number of cells',
    positional.sameCount, true);
  chk('differential', 'and every one of them is on the wrong die',
    positional.diesWrong >= rightN, true);
  chk('differential', 'every misreading differs from the correct placement per-cell',
    diffs.filter(d => d.diesWrong === 0).map(d => d.misread), []);
  evidence.differential = { correctCells: rightN, cases: diffs };
}

// ════════════════════════════════════════════════════════════════════════════════
// 5 — THE NEGATIVE CASE. A plain block still pastes exactly the way it does today.
//     The input is the ARTIFACT `copyGridToExcel` produced in this same sandbox, not a
//     re-typed layout — a re-typed fixture scores the layout the harness already believes.
// ════════════════════════════════════════════════════════════════════════════════
{
  const results = {};
  [false, true].forEach(headerOn => {
    const sb = buildSandbox(WORK_MAP, `plain:${headerOn}`, { copyHeaderToggle: { checked: headerOn } });
    buildCells(sb);
    paintFixture(sb);
    const before = gridSnapshot(sb);
    sb.H.copyGridToExcel();
    const art = sb.captured.text;

    // ① the new detector YIELDS — it must not even look at a company copy
    const k = sb.H.readCoordTableBlock(art).kind;
    chk('negative', `a copy (header=${headerOn}) is NOT taken for a coordinate table`, k, 'none');

    // ② and the positional path still round-trips it cell for cell
    sb.ctx.gridData = {};
    const parsed = sb.H.readCompanyMapBlock(art);
    const frame = frameOf(sb);
    const verdict = sb.H.checkPasteAgainstFrame(parsed, frame);
    chk('negative', `the positional paste still accepts it (header=${headerOn})`, verdict.ok, true);
    if (verdict.ok) sb.H.applyPastedGridRows(parsed, frame);
    const after = gridSnapshot(sb);
    const differ = Object.keys(before).filter(kk => before[kk] !== after[kk]);
    chk('negative', `the positional round trip is cell-for-cell identical (header=${headerOn})`, differ, []);
    results[`header=${headerOn}`] = { detector: k, verdict: verdict.ok, cellsDiffering: differ.length };
  });

  // ③ adversarial plain blocks that must NOT be taken for a coordinate table
  const H = base.H;
  const notCoord = [
    ['a grid whose values are all integers', [['1', '2', '3'], ['4', '5', '6'], ['7', '8', '9']]],
    ['a grid with a blank corner but repeated values', [['', '1', '1', '1'], ['1', '1', '1', '1']]],
    ['a two-column paste', [['A', 'B'], ['C', 'D']]],
    ['a DOE-style header block', [['VALUE', 'COUNT', 'STACK'], ['F', '12', 'MID']]],
    // 🔴 THE REGRESSION THIS CLAUSE EXISTS FOR. A bare map grid: row 0 starts outside the
    //    wafer so its first cell is blank, and the left column below it is full of `1`s.
    //    Derivation ⓑ fires (integer labels in column 0 from row 1) while ⓐ does not (row 0
    //    has interior blanks). Refusing here would block a paste that works today.
    ['a bare map grid with an integer left column',
      [['', '', '1', '1', ''], ['1', '1', '1', '1', '1'], ['2', '1', 'F', '1', '1'], ['3', '1', '1', '1', '']]],
    ['an ordinary spreadsheet with a numeric id column',
      [['id', 'name', 'qty'], ['1', 'a', '5'], ['2', 'b', '6']]],
  ];
  notCoord.forEach(([name, rows]) => {
    chk('negative', `not a coordinate table: ${name}`, H.readCoordTableBlock(H.serializeTsv(rows)).kind, 'none');
  });
  evidence.negative = { roundTrips: results };
}

// ════════════════════════════════════════════════════════════════════════════════
// 6 — REFUSALS. Named, readable, and never a best-effort placement.
// ════════════════════════════════════════════════════════════════════════════════
{
  const H = base.H;
  const T = (rows) => H.readCoordTableBlock(H.serializeTsv(rows));
  const refusals = [];
  const expectRefuse = (name, rows) => {
    const r = T(rows);
    chk('refuse', name, r.kind, 'refuse');
    refusals.push({ case: name, kind: r.kind, reason: r.reason || '' });
    return r;
  };

  // the two derivations disagree — a ruler-shaped junk row above the real ruler
  expectRefuse('junk ruler row above the real one', [
    ['SLOT', '2', '3', '6'],
    ['', '5', '6', '7'],
    ['3', 'a', 'b', 'c'],
    ['4', 'd', 'e', 'f'],
  ]);
  // X ruler present, no Y labels
  expectRefuse('no Y labels under the ruler', [
    ['', '5', '6', '7'],
    ['A', 'a', 'b', 'c'],
    ['B', 'd', 'e', 'f'],
  ]);
  // content above the table
  expectRefuse('content above the coordinate table', [
    ['note', '', '', ''],
    ['', '5', '6', '7'],
    ['3', 'a', 'b', 'c'],
    ['4', 'd', 'e', 'f'],
  ]);
  // a data row whose first cell is not a coordinate
  expectRefuse('a data row with no Y coordinate', [
    ['', '5', '6', '7'],
    ['3', 'a', 'b', 'c'],
    ['total', 'd', 'e', 'f'],
    ['4', 'g', 'h', 'i'],
  ]);
  // repeated Y coordinate
  expectRefuse('a repeated Y coordinate', [
    ['', '5', '6', '7'],
    ['3', 'a', 'b', 'c'],
    ['3', 'd', 'e', 'f'],
    ['4', 'g', 'h', 'i'],
  ]);
  // a value in a column the ruler never named
  expectRefuse('a value in a column with no X coordinate', [
    ['', '5', '6', ''],
    ['3', 'a', 'b', 'c'],
    ['4', 'd', 'e', ''],
  ]);
  // 🔴 `4A` IS NOT A COORDINATE. A loose `parseInt('4A')` returns 4 and this block sails
  //    through as a well-formed table whose middle row is filed under y=4 — a silently wrong
  //    coordinate, which is the exact class this whole file exists to catch.
  expectRefuse('a Y label that only starts with digits (4A)', [
    ['', '5', '6', '7'],
    ['3', 'a', 'b', 'c'],
    ['4A', 'd', 'e', 'f'],
    ['5', 'g', 'h', 'i'],
  ]);

  chk('refuse', 'every refusal carries a reason a user can read',
    refusals.filter(r => r.kind === 'refuse' && r.reason.length < 10).map(r => r.case), []);

  // and a table whose coordinates do not fit the current grid is refused by the PLANNER
  const far = H.readCoordTableBlock(H.serializeTsv([
    ['', '900', '901'],
    ['900', 'a', 'b'],
    ['901', 'c', 'd'],
  ]));
  chk('refuse', 'an out-of-range table parses', far.kind, 'ok');
  const farPlan = base.H.planCoordPaste(far, coordFrameOf());
  chkTrue('refuse', 'and its cells are reported as off-grid rather than dropped',
    farPlan.offGrid.length === 4, farPlan.offGrid.length);
  evidence.refusals = refusals;
  evidence.offGrid = farPlan.offGrid;
}

// ════════════════════════════════════════════════════════════════════════════════
// 7 — THE HANDLER. One paste, one confirm, no server call.
// ════════════════════════════════════════════════════════════════════════════════
{
  const h = fnFrom(WORK_MAP, 'working tree', 'onMapGridPaste');
  chk('handler', 'the paste handler calls no fetch/push/save',
    /\bfetch\s*\(|pushMapData|saveLegendToServer|replace_map/.test(h), false);
  chk('handler', 'exactly one confirm across BOTH paste paths',
    (h.match(/\bconfirm\s*\(/g) || []).length, 1);
  chk('handler', 'the coordinate path is wired through the shared reader/planner/writer',
    ['readCoordTableBlock(', 'planCoordPaste(', 'applyPastedGridRows(',
      'currentCoordFrame(', 'ensureLegendValues('].filter(s => h.indexOf(s) < 0), []);
  chk('handler', 'the positional path is still wired exactly as before',
    ['readCompanyMapBlock(', 'checkPasteAgainstFrame(', 'applyPastedAuxRows(',
      'classifyUnsavableCells('].filter(s => h.indexOf(s) < 0), []);
  // INV ①: there is no second coordinate transform. The planner must call the ONE inverse.
  const p = fnFrom(WORK_MAP, 'working tree', 'planCoordPaste');
  chk('handler', 'planCoordPaste uses getCanvasCellFromDb and nothing else to place a cell',
    p.indexOf('getCanvasCellFromDb(') >= 0, true);
  chk('handler', 'planCoordPaste contains no hand-rolled box arithmetic',
    /box\.(minC|maxR|minR|maxC)/.test(p), false);
}

// ════════════════════════════════════════════════════════════════════════════════
// MUTATIONS — prove the check can go red, and CONFIRM EACH MUTATION APPLIED
// ════════════════════════════════════════════════════════════════════════════════
// 🔴 `once` DIES when the anchor is missing OR appears more than once. Both traps named in
//    the brief (a non-unique string landing on a comment; a mutation that never applied and
//    scored the pristine file) are structurally impossible here.
const once = (find, repl) => (src, name) => {
  let i = src.indexOf(find);
  if (i < 0) die(`mutation "${name}": anchor not found — the code moved, the harness did not`);
  if (src.indexOf(find, i + 1) >= 0) die(`mutation "${name}": anchor is NOT unique — it would land on the first match`);
  const out = src.slice(0, i) + repl + src.slice(i + find.length);
  if (out === src) die(`mutation "${name}": replacement is identical to the anchor`);
  return out;
};

const MUTATIONS = [
  // ── the transform itself ──────────────────────────────────────────────────────
  ['the START X term is dropped from the inverse',
    once('  const c = dbX - startX + box.minC;', '  const c = dbX + box.minC;')],
  ['the bbox term is dropped from the inverse',
    once('  const c = dbX - startX + box.minC;', '  const c = dbX - startX;')],
  ['y-invert uses minR where maxR belongs',
    once('    r = box.maxR - (dbY - startY);', '    r = dbY - startY + box.minR;')],
  // ── the coordinate addressing ────────────────────────────────────────────────
  ['x and y are swapped on the way in',
    once('    const at = getCanvasCellFromDb(t.x, t.y, cf.cols, cf.rows, cf.rotation, cf.side,',
      '    const at = getCanvasCellFromDb(t.y, t.x, cf.cols, cf.rows, cf.rotation, cf.side,')],
  ['the value is written to the transposed square',
    once('    rows[at.r][at.c] = t.value;', '    rows[at.c] = rows[at.c] || []; rows[at.c][at.r] = t.value;')],
  ['headers are read as screen positions (the round\'s whole point, undone)',
    once('      cells.push({ x: t.v, y: yVals[i], value });',
      '      cells.push({ x: t.c - 1, y: i, value });')],
  // ── the prefill (outside the table must be UNTOUCHED) ────────────────────────
  ['the grid outside the table is wiped instead of preserved',
    once("      line.push(cell ? (gridData[cell.key] || '') : '');", "      line.push('');")],
  // ── the confirm's number vs what lands (INV ⑥) ───────────────────────────────
  ['the confirm counts protected dies it will not write',
    once('    if (isProtectedFCell(cell.key)) return;              // 잠금 — 되쓰기도 막는다',
      '    // mutated: protection ignored in the count')],
  // ── the off-grid report ──────────────────────────────────────────────────────
  ['cells with no square on this grid are dropped silently',
    once("      if (t.value !== '') offGrid.push({ x: t.x, y: t.y, c: at.c, r: at.r });",
      '      // mutated: off-grid cells dropped')],
  // ── the detector ─────────────────────────────────────────────────────────────
  ['a block with no ruler row is refused instead of yielded to the positional path',
    once("  if (topAnchor === null) return { kind: 'none' };", '  if (false) return { kind: \'none\' };')],
  ['the two derivations no longer have to agree',
    once('  if (topAnchor !== bottomAnchor) {', '  if (false) {')],
  ['the X axis no longer has to be strictly monotonic',
    once('  if (!coordMonotonic(ticks.map(t => t.v))) return null;', '  // mutated: monotonic dropped')],
  ['the Y axis no longer has to be strictly monotonic',
    once('  if (!coordMonotonic(yVals)) {', '  if (false) {')],
  ['the corner cell may be a coordinate (a data row becomes a ruler)',
    once('  if (coordInt(pasteAt(line, 0)) !== null) return null;', '  // mutated: corner guard dropped')],
  ['coordInt accepts a loose parseInt (3A becomes 3)',
    once("  return /^[+-]?\\d+$/.test(t) ? parseInt(t, 10) : null;",
      '  const n = parseInt(t, 10); return isNaN(n) ? null : n;')],
  ['content above the table is tolerated',
    once('  for (let r = 0; r < topAnchor; r++) {', '  for (let r = 0; r < 0; r++) {')],
  ['a value in a column with no X coordinate is dropped silently',
    once('      if (!tickCols.has(c) && !pasteBlank(pasteAt(line, c))) {', '      if (false) {')],
  ['the Y labels no longer have to be contiguous',
    once('    if (yRows[i] !== yRows[i - 1] + 1) {', '    if (false) {')],
];

// ONE scorer, applied to the working tree and to every mutant. Returns the list of reasons
// this build is wrong — empty means "indistinguishable from correct".
function score(src, label) {
  const why = [];
  let sb;
  try {
    sb = buildSandbox(src, label);
    buildCells(sb);
    paintFixture(sb);
  } catch (e) { return [`sandbox: ${e && e.message}`]; }

  const box = sb.H.getWaferBoundingBox(null, ROT, SIDE);
  if (JSON.stringify(box) !== JSON.stringify(BOX)) why.push(`box moved to ${JSON.stringify(box)}`);

  // ① the block is still recognised, with the same axes
  let cd;
  try { cd = sb.H.readCoordTableBlock(TABLE_TEXT); } catch (e) { return [`reader threw: ${e && e.message}`]; }
  if (cd.kind !== 'ok') { why.push(`detector said ${cd.kind}`); return why; }
  if (cd.minX !== 5 || cd.maxX !== 8 || cd.minY !== 3 || cd.maxY !== 7) {
    why.push(`axes read as x ${cd.minX}..${cd.maxX} y ${cd.minY}..${cd.maxY}`);
  }

  // ② per-cell placement against the ORACLE (which never changes — it lives here)
  const protKey = sb.ctx.gridCells2D[PROT.r][PROT.c].key;
  sb.ctx.loadedFCells = new Set([protKey]);
  sb.ctx.gridData[protKey] = 'F';
  const before = gridSnapshot(sb);
  let plan, stats;
  try {
    plan = sb.H.planCoordPaste(cd, coordFrameOf());
    stats = sb.H.applyPastedGridRows({ rows: plan.rows }, Object.assign({}, frameOf(sb), { notch: null }));
  } catch (e) { why.push(`plan/apply threw: ${e && e.message}`); return why; }
  if (plan.offGrid.length !== 0) why.push(`${plan.offGrid.length} cells off grid`);
  const after = gridSnapshot(sb);

  let wrong = 0;
  const rect = new Set();
  TBL_Y.forEach(y => TBL_X.forEach(x => {
    const at = oracleCell(x, y);
    if (at.c < 0 || at.c >= VC || at.r < 0 || at.r >= VR) { wrong++; return; }
    const key = sb.ctx.gridCells2D[at.r][at.c].key;
    rect.add(key);
    const want = (key === protKey) ? 'F' : tblValue(x, y);
    if ((after[key] || '') !== want) wrong++;
  }));
  if (wrong > 0) why.push(`${wrong} dies hold the wrong value`);

  const outside = Object.keys(before).filter(k => !rect.has(k) && before[k] !== after[k]).length;
  if (outside > 0) why.push(`${outside} dies outside the table changed`);

  if (plan.placed !== stats.set || plan.cleared !== stats.cleared) {
    why.push(`confirm says ${plan.placed}/${plan.cleared}, ${stats.set}/${stats.cleared} landed`);
  }
  if (stats.blocked !== 1) why.push(`protected die not blocked (blocked=${stats.blocked})`);

  // ③ the off-grid report still fires
  try {
    const far = sb.H.readCoordTableBlock(sb.H.serializeTsv([['', '900', '901'], ['900', 'a', 'b'], ['901', 'c', 'd']]));
    const fp = far.kind === 'ok' ? sb.H.planCoordPaste(far, coordFrameOf()) : { offGrid: [] };
    if (fp.offGrid.length !== 4) why.push(`off-grid report gave ${fp.offGrid.length} instead of 4`);
  } catch (e) { why.push(`off-grid probe threw: ${e && e.message}`); }

  // ④ the NEGATIVE case: a real copy artifact is still not a coordinate table, and the
  //    positional path still round-trips it cell for cell
  try {
    [false, true].forEach(headerOn => {
      const s2 = buildSandbox(src, `${label}:plain`, { copyHeaderToggle: { checked: headerOn } });
      buildCells(s2);
      paintFixture(s2);
      const b2 = gridSnapshot(s2);
      s2.H.copyGridToExcel();
      const art = s2.captured.text;
      const k = s2.H.readCoordTableBlock(art).kind;
      if (k !== 'none') why.push(`a copy (header=${headerOn}) was taken for a coordinate table (${k})`);
      s2.ctx.gridData = {};
      const parsed = s2.H.readCompanyMapBlock(art);
      const fr = frameOf(s2);
      const v = s2.H.checkPasteAgainstFrame(parsed, fr);
      if (!v.ok) { why.push(`positional paste refused its own artifact (header=${headerOn}): ${v.reason}`); return; }
      s2.H.applyPastedGridRows(parsed, fr);
      const a2 = gridSnapshot(s2);
      const d = Object.keys(b2).filter(kk => b2[kk] !== a2[kk]).length;
      if (d > 0) why.push(`positional round trip broke on ${d} cells (header=${headerOn})`);
    });
  } catch (e) { why.push(`negative case threw: ${e && e.message}`); }

  // ⑤ the refusals still refuse
  const mustRefuse = [
    ['junk ruler above', [['SLOT', '2', '3', '6'], ['', '5', '6', '7'], ['3', 'a', 'b', 'c'], ['4', 'd', 'e', 'f']]],
    ['no Y labels', [['', '5', '6', '7'], ['A', 'a', 'b', 'c'], ['B', 'd', 'e', 'f']]],
    ['content above', [['note', '', '', ''], ['', '5', '6', '7'], ['3', 'a', 'b', 'c'], ['4', 'd', 'e', 'f']]],
    ['broken Y run', [['', '5', '6', '7'], ['3', 'a', 'b', 'c'], ['total', 'd', 'e', 'f'], ['4', 'g', 'h', 'i']]],
    ['repeated Y', [['', '5', '6', '7'], ['3', 'a', 'b', 'c'], ['3', 'd', 'e', 'f'], ['4', 'g', 'h', 'i']]],
    ['orphan column', [['', '5', '6', ''], ['3', 'a', 'b', 'c'], ['4', 'd', 'e', '']]],
    ['4A is not a coordinate', [['', '5', '6', '7'], ['3', 'a', 'b', 'c'], ['4A', 'd', 'e', 'f'], ['5', 'g', 'h', 'i']]],
  ];
  mustRefuse.forEach(([name, rows]) => {
    try {
      const k = sb.H.readCoordTableBlock(sb.H.serializeTsv(rows)).kind;
      if (k !== 'refuse') why.push(`"${name}" no longer refuses (${k})`);
    } catch (e) { why.push(`refusal probe "${name}" threw`); }
  });
  const mustYield = [
    ['all-integer grid', [['1', '2', '3'], ['4', '5', '6'], ['7', '8', '9']]],
    ['repeated values', [['', '1', '1', '1'], ['1', '1', '1', '1']]],
    ['bare map grid, integer left column',
      [['', '', '1', '1', ''], ['1', '1', '1', '1', '1'], ['2', '1', 'F', '1', '1'], ['3', '1', '1', '1', '']]],
    ['spreadsheet with a numeric id column', [['id', 'name', 'qty'], ['1', 'a', '5'], ['2', 'b', '6']]],
  ];
  mustYield.forEach(([name, rows]) => {
    try {
      const k = sb.H.readCoordTableBlock(sb.H.serializeTsv(rows)).kind;
      if (k !== 'none') why.push(`"${name}" is no longer yielded to the positional path (${k})`);
    } catch (e) { why.push(`yield probe "${name}" threw`); }
  });

  return why;
}

const baseWhy = score(WORK_MAP, 'working tree');
if (baseWhy.length > 0) {
  baseWhy.forEach(w => fails.push({ group: 'scorer', what: 'the working tree fails its own scorer', got: w, want: '(nothing)' }));
} else {
  pass++;
}

const mutationResults = [];
MUTATIONS.forEach(([name, apply]) => {
  const mutated = apply(WORK_MAP, name);
  // 🔴 CONFIRM THE MUTATED STATE, not just the outcome. `once` already dies on a missing or
  //    non-unique anchor; this is the third guard — the source really is different.
  if (mutated === WORK_MAP) die(`mutation "${name}" did not change the source`);
  const why = score(mutated, `mutant:${name}`);
  mutationResults.push({ name, caught: why.length > 0, why: why.slice(0, 3) });
});
const missed = mutationResults.filter(m => !m.caught);
chk('mutations', 'every injected defect is caught', missed.map(m => m.name), []);
evidence.mutations = mutationResults;

// ── report ──────────────────────────────────────────────────────────────────────
if (JSON_OUT) {
  console.log(JSON.stringify({ pass, fails, evidence }, null, 2));
} else {
  console.log('── [1d] coordinate-table paste ──');
  console.log(`fixture: ${COLS}x${ROWS} rot ${ROT} ${SIDE}, START (${START_X},${START_Y}), `
    + `invertY ${INVERT_Y}, box ${JSON.stringify(BOX)}`);
  console.log('\n--- placement (DB x,y -> canvas c,r -> die key -> value) ---');
  (evidence.placement ? evidence.placement.perCell : []).forEach(p => {
    console.log(`  x=${String(p.x).padStart(3)} y=${String(p.y).padStart(3)}  ->  `
      + `c=${String(p.canvas[0]).padStart(2)} r=${String(p.canvas[1]).padStart(2)}  ->  `
      + `${p.key.padEnd(8)} = ${p.value === '' ? '(empty)' : p.value}`);
  });
  console.log('\n--- differential: same count, different dies (key -> value) ---');
  (evidence.differential ? evidence.differential.cases : []).forEach(d => {
    console.log(`  ${d.misread}: placed ${d.cellsPlaced} (correct places ${evidence.differential.correctCells})`
      + `${d.sameCount ? ' [SAME COUNT]' : ''} -> ${d.diesWrong} dies hold a different value`);
    d.sample.forEach(s => console.log(`        die ${s.die.padEnd(8)} correct=${s.correct.padEnd(8)} misread=${s.misread}`));
  });
  console.log('\n--- refusals ---');
  (evidence.refusals || []).forEach(r => console.log(`  ${r.kind.toUpperCase()}  ${r.case}\n         ${r.reason.slice(0, 110)}`));
  console.log('\n--- negative case (existing paste path) ---');
  Object.entries(evidence.negative ? evidence.negative.roundTrips : {}).forEach(([k, v]) => {
    console.log(`  ${k}: detector=${v.detector}, positional verdict=${v.verdict}, cells differing=${v.cellsDiffering}`);
  });
  console.log('\n--- mutations ---');
  mutationResults.forEach(m => console.log(`  ${m.caught ? 'RED  ' : 'MISS '} ${m.name}${m.caught ? `  <- ${m.why.join(' | ')}` : ''}`));
  if (fails.length > 0) {
    console.log('\n--- FAILURES ---');
    fails.forEach(f => console.log(`  [${f.group}] ${f.what}\n      got  ${J(f.got)}\n      want ${J(f.want)}`));
  }
  console.log(`\n--- ${pass} passed, ${fails.length} failed ---`);
  console.log(`--- mutation check: ${mutationResults.length - missed.length}/${mutationResults.length} defects caught ---`);
}
console.log(`ASSERTIONS ${pass} ${fails.length}`);
process.exit(fails.length > 0 ? 1 : 0);
