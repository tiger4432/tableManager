// F1ⓑ — the COPY HEADER MODE round trip: copy a map, paste it back, get the same grid.
// Run: node client2/tests/company_roundtrip_harness.mjs [--json]
//
// SAME TECHNIQUE as copy_header_count_harness.mjs / valid_die_authoring_harness.mjs:
// map_editor.js imports ./config.js which touches `window` at module scope, so it cannot be
// imported in node. The functions under test stay module-private; their declarations are
// sliced out of the SOURCE TEXT and evaluated in a vm sandbox with stubs for module state.
//
// 🔴 THE ROUND TRIP IS SCORED ON THE ARTIFACT, NOT ON A RE-TYPED FIXTURE.
//    The input to every paste assertion below is `captured.text` — the literal string
//    `copyGridToExcel` handed to the clipboard in this same sandbox. A test that re-types
//    the expected layout scores the layout it already believes in; contract-keeper measured
//    that lesson on 2026-07-29 and it is the reason this file never writes a TSV by hand.
//
// 🔴 AND THE CHECK IS PROVEN TO GO RED. Ten source mutations are applied to the working tree
//    and the whole round trip is re-run against each. A mutation that stays green is
//    reported as MISSED and fails the run — an unscored axis is not a passing axis.
//
// FAILS LOUDLY (exit 2) when a function cannot be extracted. A harness that goes green
// because it stopped finding the code is worse than no harness — its green gets cited.
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

const WORK_MAP = readFileSync(join(ROOT, 'client2', 'src', 'map_editor.js'), 'utf8');
const WORK_DOE = readFileSync(join(ROOT, 'client2', 'src', 'doe_bands.js'), 'utf8');
const WORK_TSV = readFileSync(join(ROOT, 'client2', 'src', 'tsv.js'), 'utf8');

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
function fnFrom(src, label, name) {
  const m = new RegExp(`(?:async\\s+)?function\\s+${name}\\s*\\(`).exec(src);
  if (!m) die(`function ${name} not found in ${label}`);
  const out = sliceBalanced(src, m.index, '{', '}');
  if (!out) die(`unbalanced braces for ${name} in ${label}`);
  return out;
}
function constFrom(src, label, name) {
  const m = new RegExp(`const\\s+${name}\\s*=`).exec(src);
  if (!m) die(`const ${name} not found in ${label}`);
  let depth = 0;
  for (let j = m.index; j < src.length; j++) {
    const ch = src[j];
    if (ch === '[' || ch === '{') depth++;
    else if (ch === ']' || ch === '}') depth--;
    else if (ch === ';' && depth === 0) return src.slice(m.index, j + 1);
  }
  die(`no terminator for const ${name} in ${label}`);
}

// ── the fixture: every defect axis ACTIVE ───────────────────────────────────────
// chipX != chipY  — a pitch swap under rot 90/270 shows up
// rot 90 + back   — rotation and mirror both engaged; the notch lands on a LEFT column,
//                   so the frame fingerprint is not the trivial rot-0 bottom row
// edgeMargin 1    — NOT 0 (`physNum`'s `|| dflt` turns a declared 0 into 3.0)
// bbox minC != 0  — asserted below, so a dropped bbox term cannot hide
// COLS != ROWS    — a transposed read cannot pass the width check by accident
const DIA = 20, EM = 1, CHIP_X = 2, CHIP_Y = 3;
const COLS = 11, ROWS = 9;
const ROT = 90, SIDE = 'back';

function inputStub(v) { return { value: String(v) }; }
function makeEl(headerOn) {
  return {
    physWaferDia: inputStub(DIA), physEdgeMargin: inputStub(EM),
    physChipX: inputStub(CHIP_X), physChipY: inputStub(CHIP_Y),
    physOffsetX: inputStub(0), physOffsetY: inputStub(0),
    gridCols: inputStub(COLS), gridRows: inputStub(ROWS),
    gridStartX: inputStub(1), gridStartY: inputStub(1),
    gridYInvert: { checked: false },
    showAnnotations: { checked: true },
    gridCanvas: null,
    btnCopyExcel: null,
    copyHeaderToggle: { checked: !!headerOn },
  };
}

const THEME = {
  outBg: '#e2e6ec', line: '#d1d5db', lineStrong: '#b9c0cb', insideEmpty: '#eef6f1',
  textEmpty: '#47536b', textOut: '#5b6779', waferEdge: '#1f2733',
  wmFront: '#eef4fd', wmBack: '#fdf6e8', accent: '#1a66d0', success: '#177245',
  warning: '#8a5a00', danger: '#c22f2f', dangerWeak: '#f6dede', rangeFill: '#e3ecfa',
  surface: '#ffffff',
};

// ── THE DOE FIXTURE — the swap axis must be LIVE ────────────────────────────────
// 🔴 `E1` has an EMPTY STACK and a NON-EMPTY DESC. Without such a row a reader that
//    compacts the blanks out of an aux record produces the SAME four fields as a reader
//    that honours the merge, and the "swapped COUNT/STACK" mutation below would be green
//    for a reason that has nothing to do with the code being right.
// 🔴 The four DESC strings have very different lengths, so `auxColumnSpans` gives the four
//    aux columns DIFFERENT widths. If every column were one cell wide, "read by learned
//    position" and "read by field index" would coincide and INV-F1ⓑ-3 would be untestable.
const LEGEND = [
  { value: '1', color: '#facc15', desc: 'POR', stack: 16, mat_1h: 'AF_03', mat_mid: 'MIDLOT_01', mat_top: 'TOP_01' },
  { value: 'F', color: '#ef4444', desc: 'FAIL — 압흔 불량으로 폐기', stack: 1, mat_1h: '', mat_mid: '', mat_top: '' },
  { value: 'E1', color: '#3b82f6', desc: 'Edge', stack: '', mat_1h: '', mat_mid: '', mat_top: '' },
  { value: 'XLONG', color: '#8b5cf6', desc: '', stack: 4, mat_1h: '', mat_mid: '', mat_top: '' },
];

const MAP_FNS = [
  // shared geometry / copy path
  'physNum', 'gridDimNum',
  'getScreenShift', 'getTransformedPhysicalConfig',
  'getPhysicalCoords', 'getVisualCoords',
  'isCellInsideWaferFast', 'isCellInsideWafer', 'getWaferBoundingBox',
  'validDieBasis', 'isValidDieAt', 'getGridCellObject',
  'parseCssColor', 'toExcelHex', 'cellFillColor',
  'getVisualGridDimensions', 'escapeHtmlAttr',
  'isProtectedFCell', 'eachSavableCell', 'classifyUnsavableCells', 'serverCellKeySet',
  'computeLegendCounts',
  'headerSpanFor', 'distributeSpans', 'auxColumnSpans',
  'copyHeaderEnabled', 'mapKeyGroupLabel', 'copyHeaderGroups', 'copyHeaderAuxRows',
  'colHeaderWord', 'copyTitleText', 'computeNotchCell', 'copyGridToExcel',
  // [F1ⓑ] the paste side
  'auxHeaderInLine', 'readCompanyMapBlock', 'checkPasteAgainstFrame',
  'applyPastedGridRows', 'applyPastedAuxRows', 'pastedCellCount',
];
const MAP_CONSTS = ['UNLISTED_VALUE_FILL', 'HDR_COL_PX', 'HDR_PAD_PX', 'HDR_CHAR_PX',
  'HDR_MIN_SPAN', 'HDR_MAX_SPAN', 'HDR_GAP_COLS', 'pasteBlank', 'pasteAt'];

function buildSandbox(src, label, headerOn) {
  const parts = [];
  MAP_FNS.forEach(n => parts.push(fnFrom(src, label, n)));
  MAP_CONSTS.forEach(n => parts.push(constFrom(src, label, n)));
  // The real TSV reader and the real DOE column roster — no second parser, no second roster.
  ['QUOTE', 'TAB'].forEach(n => parts.push(constFrom(WORK_TSV, 'tsv.js', n)));
  ['normalizeNewlines', 'parseTsv'].forEach(n => parts.push(fnFrom(WORK_TSV, 'tsv.js', n)));
  ['ZONES', 'ZONE_LABEL', 'DOE_COLUMNS', 'IGNORED_HEADERS'].forEach(n => parts.push(constFrom(WORK_DOE, 'doe_bands.js', n)));
  ['parseMaterialList', 'columnIdByHeader', 'looksLikeHeader', 'leadingBlankColumnDropped', 'mapPastedGrid']
    .forEach(n => parts.push(fnFrom(WORK_DOE, 'doe_bands.js', n)));

  const captured = { html: null, text: null, toasts: [], alerts: [], confirms: [], fetches: [] };
  // The legend-mutation gateways are NOT under test here (they are map_editor's single
  // legend gate and the DOE panel's paste already scores them). They are RECORDERS, so the
  // assertion can be made at the boundary: exactly which patch reaches the gate.
  const recorded = { added: [], updates: [] };
  const ctx = {
    console: Object.assign(Object.create(console), { debug: () => {} }),
    physFrameOverride: null,
    currentRotation: ROT, currentSide: SIDE,
    validDie: null, boundingBoxCache: {}, el: makeEl(headerOn),
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
    renderGridCanvas: () => {},
    renderLegendTable: () => {},
    updateLegendCounts: () => {},
    scheduleCellDraft: () => {},
    persistLegend: () => {},
    __captured: captured,
    __recorded: recorded,
  };
  ctx.autoAddLegendValue = (v, d) => {
    const s = String(v);
    if (ctx.legend.some(l => String(l.value) === s)) return false;
    ctx.legend.push({ value: s, desc: String(d || ''), color: '#6b7280', stack: '', mat_1h: [], mat_mid: [], mat_top: [] });
    recorded.added.push({ value: s, desc: String(d || '') });
    return true;
  };
  ctx.updateLegendRowForPanel = (name, patch) => {
    recorded.updates.push({ name: String(name), patch: { ...patch } });
    const it = ctx.legend.find(l => String(l.value) === String(name));
    if (!it) return { ok: false, error: 'legend 행을 찾을 수 없습니다.' };
    Object.assign(it, patch);
    return { ok: true, value: String(name) };
  };
  // INV-F1ⓑ-4 evidence: any server call at all during a paste is a failure. The shim
  // RECORDS instead of throwing, so the assertion can print the request list.
  ctx.fetch = (...args) => { captured.fetches.push(String(args[0])); return Promise.reject(new Error('no network in harness')); };
  ctx.confirm = (msg) => { captured.confirms.push(msg); return true; };
  ctx.alert = (msg) => { captured.alerts.push(msg); };
  ctx.showToast = (msg, kind) => { captured.toasts.push({ msg, kind }); };
  ctx.writeClipboardRich = (html, text) => { captured.html = html; captured.text = text; return true; };
  vm.createContext(ctx);
  try {
    vm.runInContext(parts.join('\n\n')
      + '\nglobalThis.__h = { getGridCellObject, getTransformedPhysicalConfig, getWaferBoundingBox,'
      + ' getVisualGridDimensions, copyGridToExcel, copyHeaderAuxRows, computeLegendCounts,'
      + ' computeNotchCell, copyTitleText, classifyUnsavableCells, eachSavableCell,'
      + ' readCompanyMapBlock, checkPasteAgainstFrame, applyPastedGridRows, applyPastedAuxRows,'
      + ' pastedCellCount };', ctx);
  } catch (e) {
    die(`sandbox evaluation failed for ${label} — ${e && e.message ? e.message : e}`);
  }
  return { ctx, H: ctx.__h, captured, recorded };
}

// the app's own cell factory builds gridCells2D — the harness never hand-rolls a cell
function buildCells(sb) {
  const { ctx, H } = sb;
  const rot = ctx.currentRotation;
  const vc = (rot === 90 || rot === 270) ? ROWS : COLS;
  const vr = (rot === 90 || rot === 270) ? COLS : ROWS;
  const pc = H.getTransformedPhysicalConfig(rot, ctx.currentSide);
  ctx.gridCells2D = {};
  for (let r = 0; r < vr; r++) {
    for (let c = 0; c < vc; c++) {
      if (!ctx.gridCells2D[r]) ctx.gridCells2D[r] = {};
      ctx.gridCells2D[r][c] = H.getGridCellObject(c, r, vc, vr, pc, 700, 700);
    }
  }
  return { vc, vr };
}

// A varied grid: painted inside cells, DELIBERATE HOLES inside the wafer, and painted cells
// OUTSIDE the valid-die set (the `outsideRetained`/`outsideStray` population that
// INV-F1ⓑ-5 says must be reported rather than silently dropped or silently kept).
//
// 🔴 THE OFF-WAFER CELLS ARE PLACED AT THE EXTREMES ON PURPOSE — the LAST column and the
//    LAST row. Measured 2026-07-30: with them anywhere else, the mutation "grid row read
//    one field short" stayed GREEN, because the only column it truncated was empty in
//    every row. A fixture whose edges are blank cannot score an edge-dropping defect.
function paintFixture(sb) {
  const { ctx } = sb;
  const vc = (ROT === 90 || ROT === 270) ? ROWS : COLS;
  const vr = (ROT === 90 || ROT === 270) ? COLS : ROWS;
  ctx.gridData = {};
  let i = 0;
  const outsideKeys = [];
  for (let r = 0; r < vr; r++) {
    for (let c = 0; c < vc; c++) {
      const cell = ctx.gridCells2D[r][c];
      if (!cell || !cell.inside) continue;
      i++;
      if (i % 7 === 0) continue;                        // a hole INSIDE the wafer
      ctx.gridData[cell.key] = (i % 5 === 0) ? 'F' : ((i % 11 === 0) ? 'E1' : '1');
    }
  }
  // an off-wafer cell that carries a value, as an ingestion-written map really has
  [[0, vc - 1], [vr - 1, 0]].forEach(([r, c]) => {
    const cell = ctx.gridCells2D[r] ? ctx.gridCells2D[r][c] : null;
    if (!cell || cell.inside) return;
    ctx.gridData[cell.key] = 'F';
    outsideKeys.push(cell.key);
  });
  return { outside: outsideKeys.length, outsideKeys };
}

function frameOf(sb) {
  const { visualCols, visualRows } = sb.H.getVisualGridDimensions();
  return {
    visualCols, visualRows,
    title: sb.H.copyTitleText(),
    notch: sb.H.computeNotchCell(sb.ctx.currentRotation, sb.ctx.currentSide),
  };
}

// The domain of the comparison is the RENDERED cell set — exactly `eachSavableCell`'s
// domain minus its non-empty filter. A cell the render never made is a cell push never
// serializes, so it is not part of "the grid".
function gridSnapshot(sb) {
  const out = {};
  Object.keys(sb.ctx.gridCells2D).forEach(rStr => {
    Object.keys(sb.ctx.gridCells2D[rStr] || {}).forEach(cStr => {
      const co = sb.ctx.gridCells2D[rStr][cStr];
      if (co) out[co.key] = sb.ctx.gridData[co.key] || '';
    });
  });
  return out;
}
function diffKeys(a, b) {
  const keys = new Set(Object.keys(a).concat(Object.keys(b)));
  const out = [];
  keys.forEach(k => { if ((a[k] || '') !== (b[k] || '')) out.push({ key: k, before: a[k] || '', after: b[k] || '' }); });
  return out.sort((x, y) => (x.key < y.key ? -1 : 1));
}

function parseHtmlTable(html) {
  const rows = [];
  const trRe = /<tr>([\s\S]*?)<\/tr>/g;
  let m;
  while ((m = trRe.exec(html)) !== null) {
    const cells = [];
    const tdRe = /<td([^>]*)>([\s\S]*?)<\/td>/g;
    let t;
    while ((t = tdRe.exec(m[1])) !== null) {
      const cs = /colspan="(\d+)"/.exec(t[1]);
      cells.push({ span: cs ? parseInt(cs[1], 10) : 1, text: t[2] });
    }
    rows.push(cells);
  }
  return rows;
}

function newRun() {
  const st = { pass: 0, failures: [] };
  st.check = (inv, name, actual, expected) => {
    const a = JSON.stringify(actual), e = JSON.stringify(expected);
    if (a === e) { st.pass++; if (!JSON_OUT) console.log(`  ok   [${inv}] ${name}`); }
    else {
      st.failures.push({ inv, name, actual, expected });
      if (!JSON_OUT) console.log(`  FAIL [${inv}] ${name}\n        actual   ${a}\n        expected ${e}`);
    }
  };
  return st;
}

const st = newRun();
const chk = st.check;
const evidence = {};

// ════════════════════════════════════════════════════════════════════════════════
// THE ROUND TRIP. One sandbox: copy, wipe, paste, compare.
// ════════════════════════════════════════════════════════════════════════════════
// `variant: 'no-materials'` strips every zone from the legend. That is not cosmetic: with
// no materials the top GROUP BAND's trailing cells are the LABELS `1H`/`MID`/`TOP`, and all
// three are `DOE_COLUMNS` header words — so a reader that does not insist on `VALUE` reads
// the group band as the aux header and recovers the grid width from the wrong row.
// Measured 2026-07-30: without this variant that mutation was GREEN.
function runRoundTrip(src, label, variant) {
  const sb = buildSandbox(src, label, true);
  sb.ctx.legend = JSON.parse(JSON.stringify(LEGEND));
  if (variant === 'no-materials') {
    sb.ctx.legend.forEach(l => { l.mat_1h = []; l.mat_mid = []; l.mat_top = []; });
  }
  const dims = buildCells(sb);
  const paint = paintFixture(sb);
  const before = gridSnapshot(sb);
  const legendBefore = JSON.parse(JSON.stringify(sb.ctx.legend));

  // ← THE ARTIFACT. Everything below reads this string; nothing re-types it.
  sb.H.copyGridToExcel();
  const tsv = sb.captured.text;
  const html = sb.captured.html;
  if (!tsv) die(`${label}: the copy path produced no text/plain — nothing to paste back`);

  // The operator's screen is now DIFFERENT: every inside cell holds 'F'. A paste that only
  // WRITES non-empty cells leaves the holes wrong; a paste that writes nothing scores 0.
  Object.keys(sb.ctx.gridCells2D).forEach(rStr => {
    Object.keys(sb.ctx.gridCells2D[rStr]).forEach(cStr => {
      const co = sb.ctx.gridCells2D[rStr][cStr];
      if (co && co.inside) sb.ctx.gridData[co.key] = 'F';
    });
  });
  // ... and the DOE has been degraded, so a paste that applies nothing scores 0 there too.
  sb.ctx.legend.forEach(l => { l.stack = ''; l.desc = ''; });

  const parsed = sb.H.readCompanyMapBlock(tsv);
  const frame = frameOf(sb);
  const verdict = sb.H.checkPasteAgainstFrame(parsed, frame);
  let gridStats = null, auxStats = null;
  if (verdict.ok) {
    gridStats = sb.H.applyPastedGridRows(parsed, frame);
    auxStats = sb.H.applyPastedAuxRows(parsed);
  }
  const after = gridSnapshot(sb);

  // The number the confirm ANNOUNCES must be the number of cells that actually land. Run the
  // paste once more onto an EMPTY grid, where `set` is exactly "how many cells were placed",
  // and compare it to `pastedCellCount` — the function the confirm string calls.
  let cleanSlate = null;
  if (verdict.ok) {
    const announced = sb.H.pastedCellCount(parsed, frame);
    sb.ctx.gridData = {};
    const s2 = sb.H.applyPastedGridRows(parsed, frame);
    cleanSlate = { announced, placed: s2.set };
  }
  return { sb, dims, paint, before, legendBefore, tsv, html, parsed, frame, verdict, gridStats, auxStats, after, cleanSlate };
}

const rt = runRoundTrip(WORK_MAP, 'working tree');

// ── fixture self-check: the defect axes really are live ─────────────────────────
{
  const box = rt.sb.H.getWaferBoundingBox(ROT, SIDE);
  chk('fixture', 'bbox minC != 0 (a dropped bbox term cannot hide)', box.minC > 0, true);
  chk('fixture', 'chipX != chipY (a pitch swap under rot90 cannot hide)', CHIP_X !== CHIP_Y, true);
  chk('fixture', 'visualCols != visualRows (a transposed read cannot pass by accident)',
    rt.frame.visualCols !== rt.frame.visualRows, true);
  const insideEmpty = Object.values(rt.before).filter(v => v === '').length;
  chk('fixture', 'the copied grid has EMPTY cells (so "including empty cells" is testable)',
    insideEmpty > 0, true);
  chk('fixture', 'the copied grid has cells OUTSIDE the valid-die set (INV-F1ⓑ-5 is live)',
    rt.paint.outside > 0, true);
  // the aux fixture's swap axis
  const auxRows = rt.sb.H.copyHeaderAuxRows(rt.sb.H.computeLegendCounts ? {} : {});
  chk('fixture', 'a DOE row has an EMPTY STACK and a NON-EMPTY DESC (the compaction axis)',
    LEGEND.some(l => String(l.stack) === '' && String(l.desc) !== ''), true);
  const spans = new Set((rt.parsed.auxWords || []).map((w, i) => rt.parsed.auxRecords ? i : i));
  evidence.fixture = {
    grid: { visualCols: rt.frame.visualCols, visualRows: rt.frame.visualRows },
    cells: Object.keys(rt.before).length, insideEmpty,
    outsidePainted: rt.paint.outside,
    notch: rt.frame.notch,
    auxRowsEmitted: auxRows.length, spanBuckets: spans.size,
  };
}

// ── the artifact is well formed: TSV field count == HTML colspan sum, per row ────
// This is the PRECONDITION of the whole plain-text read (INV-F1ⓑ-3). If the two ever
// disagree, "blank = merge continuation" stops being a convention and the reader is
// guessing. The two representations are independent oracles for each other.
{
  const htmlRows = parseHtmlTable(rt.html);
  const tsvRows = rt.tsv.split('\n').map(l => l.split('\t'));
  chk('INV-F1ⓑ-3', 'row count: html == tsv', htmlRows.length, tsvRows.length);
  const bad = [];
  for (let i = 0; i < Math.min(htmlRows.length, tsvRows.length); i++) {
    const span = htmlRows[i].reduce((n, c) => n + c.span, 0);
    if (span !== tsvRows[i].length) bad.push({ row: i, colspanSum: span, tsvFields: tsvRows[i].length });
  }
  chk('INV-F1ⓑ-3', 'every row: TSV field count == HTML colspan sum', bad, []);
}

// ════════════════════════════════════════════════════════════════════════════════
// INV-F1ⓑ-1 — copy, paste, and the grid is identical. Cell for cell, empties included.
// ════════════════════════════════════════════════════════════════════════════════
{
  chk('INV-F1ⓑ-1', 'the block was readable', rt.parsed.ok, true);
  chk('INV-F1ⓑ-1', 'the frame check accepted it', rt.verdict.ok, true);
  chk('INV-F1ⓑ-1', 'the frame fingerprint (notch) was actually verified', rt.verdict.notchVerified, true);
  chk('INV-F1ⓑ-1', 'grid width recovered from the artifact == the screen',
    rt.parsed.gridWidth, rt.frame.visualCols);
  // A row shorter than the declared width is malformed WHATEVER the fixture happens to hold
  // there. The cell diff only notices it when that column carries a value.
  chk('INV-F1ⓑ-1', 'every read row is exactly gridWidth wide',
    rt.parsed.rows.filter(r => r.length !== rt.parsed.gridWidth).length, 0);
  const d = diffKeys(rt.before, rt.after);
  // key -> value, not a count. A count comparison passes on a grid where every cell moved.
  chk('INV-F1ⓑ-1', 'every cell round-trips (key->value diff is empty)', d.slice(0, 12), []);
  chk('INV-F1ⓑ-1', 'the paste actually wrote (it did not "pass" by doing nothing)',
    rt.gridStats.set + rt.gridStats.cleared > 0, true);
  evidence.roundTrip = {
    cellsCompared: Object.keys(rt.before).length,
    mismatches: d.length,
    stats: rt.gridStats,
    sampleRestored: Object.keys(rt.before).filter(k => rt.before[k] !== '').slice(0, 6)
      .map(k => ({ key: k, value: rt.after[k] })),
  };
}

// ── the notch 'D' is a DRAWING, not a cell value ────────────────────────────────
{
  const n = rt.frame.notch;
  const cell = rt.sb.ctx.gridCells2D[n.r] ? rt.sb.ctx.gridCells2D[n.r][n.c] : null;
  chk('INV-F1ⓑ-1', 'the notch marker exists in the artifact', rt.parsed.rows[n.r][n.c], 'D');
  chk('INV-F1ⓑ-1', 'the paste DISCARDED it (it is not a cell the map ever had)',
    rt.gridStats.notchDropped > 0, true);
  if (cell) chk('INV-F1ⓑ-1', 'the notch cell is still empty after the paste', rt.after[cell.key], '');
  // 쓰기 1회 확인: the number the confirm announces is the number that lands.
  chk('INV-F1ⓑ-1', 'the confirm announces the number of cells that actually land',
    rt.cleanSlate.announced, rt.cleanSlate.placed);
  evidence.notch = { at: n, dropped: rt.gridStats.notchDropped, confirmSays: rt.cleanSlate.announced };
}

// ── how many cells move if the frame is read WRONG? (fixture liveness) ──────────
// map-pm's own lesson: if the answer is 0, the fixture proved nothing. This reads the SAME
// artifact one column to the right and counts the cells that change.
{
  const sb2 = buildSandbox(WORK_MAP, 'wrong-frame probe', true);
  sb2.ctx.legend = JSON.parse(JSON.stringify(LEGEND));
  buildCells(sb2);
  paintFixture(sb2);
  const parsed2 = sb2.H.readCompanyMapBlock(rt.tsv);
  const shifted = JSON.parse(JSON.stringify(parsed2));
  shifted.rows = shifted.rows.map(r => r.slice(1).concat(['']));    // one column to the right
  const frame2 = frameOf(sb2);
  const baseline = gridSnapshot(sb2);
  sb2.H.applyPastedGridRows(shifted, frame2);
  const moved = diffKeys(baseline, gridSnapshot(sb2)).length;
  chk('fixture', 'reading the artifact one column off changes cells (fixture is not inert)',
    moved > 0, true);
  evidence.wrongFrameDelta = { shiftedByOneColumn: moved,
    outOf: Object.keys(baseline).length };
}

// ════════════════════════════════════════════════════════════════════════════════
// INV-F1ⓑ-2 — the aux table round-trips; COUNT is recognised and DISCARDED
// ════════════════════════════════════════════════════════════════════════════════
{
  const emitted = rt.sb.H.copyHeaderAuxRows(rt.sb.H.computeLegendCounts());
  // what the artifact says, read back
  chk('INV-F1ⓑ-2', 'aux header words recovered', rt.parsed.auxWords, ['VALUE', 'COUNT', 'STACK', 'DESC']);
  chk('INV-F1ⓑ-2', 'aux row count recovered', rt.parsed.auxRecords.length, emitted.length);

  // the patches that reached the legend gate — key->value against the emitted table
  const byName = {};
  rt.sb.recorded.updates.forEach(u => { byName[u.name] = u.patch; });
  const expect = {};
  rt.legendBefore.forEach(l => { expect[String(l.value)] = { desc: String(l.desc || ''), stack: String(l.stack === null || l.stack === undefined ? '' : l.stack) }; });
  chk('INV-F1ⓑ-2', 'every DOE row restored (VALUE -> {stack, desc})', byName, expect);

  // COUNT never reaches the gate, in any shape
  const countKeys = rt.sb.recorded.updates
    .flatMap(u => Object.keys(u.patch))
    .filter(k => !['desc', 'stack'].includes(k));
  chk('INV-F1ⓑ-2', 'no COUNT (or any other key) reached the legend gate', countKeys, []);
  chk('INV-F1ⓑ-2', 'the roster routed COUNT to IGNORE (it was seen, not missed)',
    rt.auxStats.countsIgnored, 1);
  evidence.aux = {
    header: rt.parsed.auxWords,
    emitted: emitted.map(r => [r.value, String(r.count), String(r.stack), r.desc]),
    patches: rt.sb.recorded.updates,
  };
}

// ════════════════════════════════════════════════════════════════════════════════
// INV-F1ⓑ-4 — pasting writes NOTHING to the server
// ════════════════════════════════════════════════════════════════════════════════
{
  chk('INV-F1ⓑ-4', 'request list is empty', rt.sb.captured.fetches, []);
  // and structurally: the handler must not reach for a save
  const h = fnFrom(WORK_MAP, 'working tree', 'onMapGridPaste');
  chk('INV-F1ⓑ-4', 'the paste handler calls no fetch/push/save',
    /\bfetch\s*\(|pushMapData|saveLegendToServer|replace_map/.test(h), false);
  chk('INV-F1ⓑ-4', 'the paste handler asks for confirmation exactly once',
    (h.match(/\bconfirm\s*\(/g) || []).length, 1);
  chk('INV-F1ⓑ-4', 'the handler routes through the shared reader/checker/appliers',
    ['readCompanyMapBlock(', 'checkPasteAgainstFrame(', 'applyPastedGridRows(',
      'applyPastedAuxRows(', 'classifyUnsavableCells('].filter(s => h.indexOf(s) < 0), []);
  evidence.serverWrites = { requests: rt.sb.captured.fetches };
}

// ════════════════════════════════════════════════════════════════════════════════
// INV-F1ⓑ-5 — cells outside the valid-die set are REPORTED (not dropped, not silent)
// ════════════════════════════════════════════════════════════════════════════════
{
  const un = rt.sb.H.classifyUnsavableCells();
  const total = un.offGrid.length + un.outsideRetained.length + un.outsideStray.length;
  chk('INV-F1ⓑ-5', 'the off-wafer painted cells survived the round trip (not dropped)',
    total, rt.paint.outside);
  // provenance: the harness's serverCellKeys is an EMPTY set for this map, so "the server
  // never sent these" is proven and they classify as stray rather than retained.
  chk('INV-F1ⓑ-5', 'they are classified with provenance, not lumped together',
    { stray: un.outsideStray.length, retained: un.outsideRetained.length, offGrid: un.offGrid.length },
    { stray: rt.paint.outside, retained: 0, offGrid: 0 });
  evidence.unsavable = { offGrid: un.offGrid, outsideRetained: un.outsideRetained, outsideStray: un.outsideStray };
}

// ════════════════════════════════════════════════════════════════════════════════
// Frame refusals — a changed frame REFUSES with a reason; it never best-effort places
// ════════════════════════════════════════════════════════════════════════════════
{
  const cases = [];
  const f = rt.frame;
  const mk = (over) => Object.assign({}, f, over);

  const narrower = rt.sb.H.checkPasteAgainstFrame(rt.parsed, mk({ visualCols: f.visualCols - 1 }));
  cases.push(['width changed', narrower]);
  const taller = rt.sb.H.checkPasteAgainstFrame(rt.parsed, mk({ visualRows: f.visualRows + 3 }));
  cases.push(['grid taller than the copy', taller]);
  const shorter = rt.sb.H.checkPasteAgainstFrame(rt.parsed, mk({ visualRows: 3 }));
  cases.push(['grid shorter than the copy', shorter]);
  const otherMap = rt.sb.H.checkPasteAgainstFrame(rt.parsed, mk({ title: 'bonding_map · 9Z99' }));
  cases.push(['a different map', otherMap]);
  // rot 0/180 and front/back keep the dimensions — only the notch tells them apart
  const flipped = rt.sb.H.computeNotchCell(ROT, 'front');
  const otherFrame = rt.sb.H.checkPasteAgainstFrame(rt.parsed, mk({ notch: flipped }));
  cases.push(['same size, different rotation/side', otherFrame]);

  cases.forEach(([name, v]) => {
    chk('INV-F1ⓑ-frame', `refused: ${name}`, v.ok, false);
    chk('INV-F1ⓑ-frame', `refusal names a reason: ${name}`, (v.reason || '').length > 10, true);
  });
  chk('INV-F1ⓑ-frame', 'the notch really moved when the side flipped',
    JSON.stringify(flipped) !== JSON.stringify(f.notch), true);
  evidence.refusals = cases.map(([name, v]) => ({ case: name, ok: v.ok, reason: v.reason }));
}

// ── an unrelated clipboard is not hijacked ──────────────────────────────────────
{
  const junk = rt.sb.H.readCompanyMapBlock('a\tb\tc\n1\t2\t3');
  const v = rt.sb.H.checkPasteAgainstFrame(junk, rt.frame);
  chk('INV-F1ⓑ-frame', 'an unrelated 3x2 block does not land in the grid', v.ok, false);
  chk('INV-F1ⓑ-frame', 'an empty clipboard is refused, not crashed',
    rt.sb.H.readCompanyMapBlock('').ok, false);
}

// ── a map with NO MATERIALS round-trips too (the group band is all labels) ──────
{
  const nm = runRoundTrip(WORK_MAP, 'no-materials', 'no-materials');
  chk('INV-F1ⓑ-3', 'no-materials: the aux header is found on the GRID row, not the group band',
    nm.parsed.gridWidth, nm.frame.visualCols);
  chk('INV-F1ⓑ-3', 'no-materials: grid round-trips', diffKeys(nm.before, nm.after).slice(0, 8), []);
  // and prove the trap is live: the group band really does end in three known header words
  const groupLine = nm.tsv.split('\n')[1].split('\t').filter(x => x !== '');
  chk('INV-F1ⓑ-3', 'no-materials: the group band ends in DOE header words (the trap is live)',
    groupLine.slice(-3), ['1H', 'MID', 'TOP']);
  evidence.noMaterials = { groupBandTail: groupLine.slice(-3), gridWidth: nm.parsed.gridWidth };
}

// ── header-OFF copies round-trip too, and say the identity is unknown ───────────
{
  const off = buildSandbox(WORK_MAP, 'header-off', false);
  off.ctx.legend = JSON.parse(JSON.stringify(LEGEND));
  buildCells(off);
  paintFixture(off);
  const before = gridSnapshot(off);
  off.H.copyGridToExcel();
  const parsed = off.H.readCompanyMapBlock(off.captured.text);
  const frame = frameOf(off);
  const v = off.H.checkPasteAgainstFrame(parsed, frame);
  Object.keys(off.ctx.gridData).forEach(k => { off.ctx.gridData[k] = 'F'; });
  if (v.ok) off.H.applyPastedGridRows(parsed, frame);
  chk('INV-F1ⓑ-1', 'header-off copy: identity is UNKNOWN, not blank', parsed.title, null);
  chk('INV-F1ⓑ-1', 'header-off copy: accepted', v.ok, true);
  chk('INV-F1ⓑ-1', 'header-off copy: grid round-trips', diffKeys(before, gridSnapshot(off)).slice(0, 8), []);
}

// ════════════════════════════════════════════════════════════════════════════════
// MUTATIONS — prove the check can go red
// ════════════════════════════════════════════════════════════════════════════════
const once = (find, repl) => (src) => {
  const i = src.indexOf(find);
  if (i < 0) return src;
  return src.slice(0, i) + repl + src.slice(i + find.length);
};

const MUTATIONS = [
  // ① the named one: a one-off in the merge-continuation reading
  ['merge-continuation: gap column not subtracted',
    once('gridWidth = aux.positions[0] - HDR_GAP_COLS;', 'gridWidth = aux.positions[0];')],
  ['merge-continuation: grid read one column to the right (SILENT shift)',
    once('for (let c = 0; c < gridWidth; c++) out.push(pasteAt(lines[i], c).trim());',
      'for (let c = 0; c < gridWidth; c++) out.push(pasteAt(lines[i], c + 1).trim());')],
  // ② the named one: a dropped trailing empty column
  ['dropped trailing empty column (grid row one short)',
    once('for (let c = 0; c < gridWidth; c++) out.push(pasteAt(lines[i], c).trim());',
      'for (let c = 0; c < gridWidth - 1; c++) out.push(pasteAt(lines[i], c).trim());')],
  ['dropped trailing empty column (aux scan stops at the first pad blank)',
    once('if (pasteBlank(f)) continue;                    // 병합 연장 · 꼬리 채움',
      'if (pasteBlank(f)) break;                          // MUTANT')],
  // ③ the named one: swapped COUNT/STACK — the classic compaction read
  ['swapped COUNT/STACK (aux record compacted instead of read by position)',
    once('const rec = aux.positions.map(p => pasteAt(lines[i], p).trim());',
      'const rec = (() => { const nb = aux.positions.map(p => pasteAt(lines[i], p).trim()).filter(x => x !== \'\'); while (nb.length < aux.positions.length) nb.push(\'\'); return nb; })();')],
  // the notch marker becomes data
  ['notch D written back as a cell value',
    once("if (n && r === n.r && c === n.c && v === 'D') { v = ''; stats.notchDropped++; }",
      "if (false) { v = ''; stats.notchDropped++; }")],
  // empty cells not cleared — "cell for cell, INCLUDING empty cells"
  ['empty cells skipped instead of cleared',
    once('const cur = gridData[cell.key] || \'\';',
      'if (v === \'\') { stats.unchanged++; continue; }\n      const cur = gridData[cell.key] || \'\';')],
  // the gap between grid and aux table drifts on the WRITE side only. The reader recovers
  // the grid width as `VALUE position - HDR_GAP_COLS`, so this is the seam that pins them.
  ['writer emits a wider gap than the reader assumes',
    once("const out = new Array(HDR_GAP_COLS).fill('');", "const out = new Array(2).fill('');")],
  // the confirm's number drifts from what actually lands
  ['confirm counts the notch marker it is about to discard',
    once("&& parsed.rows[n.r][n.c] === 'D') ? 1 : 0;", "&& parsed.rows[n.r][n.c] === 'D') ? 0 : 0;")],
  // the frame guards
  ['identity check removed (a different map would be accepted)',
    once('if (parsed.title !== null && parsed.title !== \'\' && frame.title && parsed.title !== frame.title) {',
      'if (false) {')],
  ['frame fingerprint removed (rot 0 vs 180 would be accepted)',
    once('if (notchOnGrid && parsed.rows[n.r][n.c] !== \'D\') {', 'if (false) {')],
  ['height check removed (a taller copy would be accepted)',
    once('if (parsed.rows[i].some(f => f !== \'\')) {', 'if (false) {')],
  // the aux header guard that keeps the GROUP BAND from being read as the aux head
  ['aux header no longer requires VALUE (the group band can be mistaken for it)',
    once("if (ids.indexOf('value') < 0) return null;", 'if (false) return null;')],
];

// ONE scorer, applied to the working tree and to every mutant. It returns the reasons a
// round trip is wrong; an empty list is "this source behaves like the fixed one".
function redReasons(src, label, variant) {
  const why = [];
  let m;
  try {
    m = runRoundTrip(src, label, variant);
  } catch (e) {
    return [`threw: ${String(e && e.message).slice(0, 60)}`];   // a mutant that cannot run is caught
  }
  if (!m.parsed.ok) return ['block unreadable'];
  if (m.parsed.rows.some(r => r.length !== m.parsed.gridWidth)) why.push('ragged rows');
  if (!m.verdict.ok) return why.concat([`refused: ${m.verdict.reason.slice(0, 44)}`]);
  const d = diffKeys(m.before, m.after);
  if (d.length > 0) why.push(`${d.length} cells differ`);
  if (m.gridStats && m.gridStats.set + m.gridStats.cleared === 0) why.push('nothing written');
  if (m.cleanSlate && m.cleanSlate.announced !== m.cleanSlate.placed) {
    why.push(`confirm says ${m.cleanSlate.announced}, ${m.cleanSlate.placed} land`);
  }
  const byName = {};
  m.sb.recorded.updates.forEach(u => { byName[u.name] = u.patch; });
  const expect = {};
  m.legendBefore.forEach(l => {
    expect[String(l.value)] = { desc: String(l.desc || ''), stack: String(l.stack === null || l.stack === undefined ? '' : l.stack) };
  });
  if (JSON.stringify(byName) !== JSON.stringify(expect)) why.push('DOE patches differ');
  // The frame guards: a mutant that accepts a changed frame is red even when its own round
  // trip is clean — that is precisely the defect those guards exist for.
  const f = m.frame;
  const guards = [
    m.sb.H.checkPasteAgainstFrame(m.parsed, Object.assign({}, f, { title: 'bonding_map · 9Z99' })),
    m.sb.H.checkPasteAgainstFrame(m.parsed, Object.assign({}, f, { notch: m.sb.H.computeNotchCell(ROT, 'front') })),
    m.sb.H.checkPasteAgainstFrame(m.parsed, Object.assign({}, f, { visualRows: 3 })),
  ];
  if (guards.some(g => g.ok)) why.push('a frame guard stopped refusing');
  return why;
}

// The scorer must be SILENT on the real source, or every mutant is "caught" by a defect the
// working tree already has. Both variants.
['default', 'no-materials'].forEach(v => {
  chk('harness', `scorer is silent on the working tree (${v})`, redReasons(WORK_MAP, `self-check:${v}`, v), []);
});

let mutCaught = 0;
const mutMissed = [];
const mutNotes = [];
MUTATIONS.forEach(([name, mut]) => {
  const mutated = mut(WORK_MAP);
  if (mutated === WORK_MAP) die(`mutation did not apply: ${name}`);
  const why = [];
  ['default', 'no-materials'].forEach(v => {
    redReasons(mutated, `mutant(${name}/${v})`, v).forEach(r => why.push(`${v}: ${r}`));
  });
  if (why.length > 0) { mutCaught++; mutNotes.push({ mutation: name, caught: true, by: why }); }
  else { mutMissed.push(name); mutNotes.push({ mutation: name, caught: false, by: [] }); }
});

const result = {
  passed: st.pass, failed: st.failures.length, failures: st.failures,
  mutations: { total: MUTATIONS.length, caught: mutCaught, missed: mutMissed, detail: mutNotes },
  evidence,
};
if (JSON_OUT) console.log(JSON.stringify(result, null, 2));
else {
  console.log('\n--- evidence ---');
  console.log(JSON.stringify(evidence, null, 2));
  console.log('\n--- mutations ---');
  mutNotes.forEach(m => console.log(`  ${m.caught ? 'RED ' : 'MISS'}  ${m.mutation}${m.caught ? `  <- ${m.by.join(', ')}` : ''}`));
  console.log(`\n--- ${st.pass} passed, ${st.failures.length} failed ---`);
  console.log(`--- mutation check: ${mutCaught}/${MUTATIONS.length} defects caught ---`);
}
process.exit((st.failures.length === 0 && mutMissed.length === 0) ? 0 : 1);
