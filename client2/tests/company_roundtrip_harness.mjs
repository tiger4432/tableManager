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

// 🔴 LINE ENDINGS ARE NORMALISED, AND THAT IS NOT COSMETIC. `once(find, repl)` locates each
//    mutation by an exact multi-line substring written with `\n`. The repo stores these files
//    with CRLF and `core.autocrlf=true`, so on a plain checkout the match MISSES and
//    `die('mutation did not apply')` kills the run with exit 2 — measured 2026-07-30, right
//    after a `git checkout` of these files. A harness that stops finding the code is worse
//    than no harness (this file's own header says so), so the read is made ending-agnostic.
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
// `over` lets one case swap the physical spec — used by the NO-MASK case below, which is
// the frame `loadExistingMap`'s 📐 표준 default applies to every metadata-less map.
function makeEl(headerOn, over) {
  return Object.assign({
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
  }, over || {});
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
  'getDieIndex', 'getDbCoords',
  'isCellInsideWaferFast', 'isCellInsideWafer', 'getWaferBoundingBox',
  'validDieBasis', 'isValidDieAt', 'getGridCellObject',
  'parseCssColor', 'toExcelHex', 'cellFillColor',
  'getVisualGridDimensions', 'escapeHtmlAttr',
  'isProtectedFCell', 'eachSavableCell', 'classifyUnsavableCells', 'serverCellKeySet',
  'computeLegendCounts',
  'headerSpanFor', 'distributeSpans', 'auxColumnSpans',
  'copyHeaderEnabled', 'mapKeyGroupLabel', 'copyHeaderGroups', 'copyHeaderAuxRows',
  'colHeaderWord', 'copyTitleText', 'computeNotchCell', 'copyGridToExcel',
  // [1d] the aux-header word set shared by writer and reader (MEDIUM-4), and the ONE
  // notch predicate both sides use (MEDIUM-3 / P0-2).
  'auxHeadWords', 'notchMarkCell',
  // [F1ⓑ] the paste side
  'auxHeaderInLine', 'readCompanyMapBlock', 'checkPasteAgainstFrame',
  'applyPastedGridRows', 'applyPastedAuxRows', 'pastedCellCount',
];
const MAP_CONSTS = ['UNLISTED_VALUE_FILL', 'HDR_COL_PX', 'HDR_PAD_PX', 'HDR_CHAR_PX',
  'HDR_MIN_SPAN', 'HDR_MAX_SPAN', 'HDR_GAP_COLS', 'pasteBlank', 'pasteAt'];

function buildSandbox(src, label, headerOn, elOver, ctxOver) {
  const parts = [];
  MAP_FNS.forEach(n => parts.push(fnFrom(src, label, n)));
  MAP_CONSTS.forEach(n => parts.push(constFrom(src, label, n)));
  // The real TSV reader and the real DOE column roster — no second parser, no second roster.
  ['QUOTE', 'TAB'].forEach(n => parts.push(constFrom(WORK_TSV, 'tsv.js', n)));
  // [MEDIUM-2] `serializeTsv`/`quoteField` come from tsv.js too — the copy path now WRITES
  // with the same module the paste path READS with, so `parseTsv(serializeTsv(g)) === g` is
  // the property under test rather than an assumption.
  ['normalizeNewlines', 'parseTsv', 'needsQuote', 'quoteField', 'serializeTsv']
    .forEach(n => parts.push(fnFrom(WORK_TSV, 'tsv.js', n)));
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
    validDie: null, boundingBoxCache: {}, el: makeEl(headerOn, elOver),
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
  Object.assign(ctx, ctxOver || {});
  vm.createContext(ctx);
  try {
    vm.runInContext(parts.join('\n\n')
      + '\nglobalThis.__h = { getGridCellObject, getTransformedPhysicalConfig, getWaferBoundingBox,'
      + ' getVisualGridDimensions, copyGridToExcel, copyHeaderAuxRows, computeLegendCounts,'
      + ' computeNotchCell, notchMarkCell, auxHeadWords, auxHeaderInLine,'
      + ' copyTitleText, classifyUnsavableCells, eachSavableCell,'
      + ' readCompanyMapBlock, checkPasteAgainstFrame, applyPastedGridRows, applyPastedAuxRows,'
      + ' pastedCellCount, serializeTsv, parseTsv };', ctx);
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

// The frame the paste is checked against — assembled exactly as `onMapGridPaste` does.
// 🔴 `notchMarkCell`, not `computeNotchCell`: the fingerprint is "where the copy actually
//    drew the mark", which is on-grid AND empty. Using the raw coordinate here would let the
//    harness score a fingerprint the artifact does not contain (MEDIUM-3).
function frameOf(sb) {
  const { visualCols, visualRows } = sb.H.getVisualGridDimensions();
  return {
    visualCols, visualRows,
    title: sb.H.copyTitleText(),
    notch: sb.H.notchMarkCell(sb.ctx.currentRotation, sb.ctx.currentSide),
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
      // `style` distinguishes a merged HEADER cell from the filler that pads the header rows
      // out to the table width. Only the filler carries the gap style verbatim.
      const sty = /style="([^"]*)"/.exec(t[1]);
      cells.push({ span: cs ? parseInt(cs[1], 10) : 1, text: t[2], style: sty ? sty[1] : '' });
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

// ════════════════════════════════════════════════════════════════════════════════
// A PRODUCTION-WIDTH FRAME, because the default fixture cannot see the top merge.
//
// 🔴 THE DEFAULT FIXTURE IS 11x9 AT ROT 90, i.e. 9 grid columns — NARROWER than the group
//    band's minimum legible width (17 columns for this legend). In that regime the band is
//    held at its floor and scoping it to the map area changes almost nothing, so a
//    round-trip scored only there says nothing about the change that shipped. Every
//    production row in `wafer_map_metadata` is 23..51 columns wide.
//
// WHAT THIS SCORES: with the top merge now ending at the map grid (29 columns) while the
// table is still 38 wide, the reader must STILL recover 29 — the aux table's `VALUE` column
// did not move, and the two header lines above it are still exactly two lines.
// ════════════════════════════════════════════════════════════════════════════════
{
  const WIDE = { gridCols: inputStub(29), gridRows: inputStub(25) };
  const sb = buildSandbox(WORK_MAP, 'prod-width', true, WIDE);
  sb.ctx.legend = JSON.parse(JSON.stringify(LEGEND));
  // 🔴 The dimensions come from the APP, not from the two numbers typed above. This harness
  //    runs at rot 90, which swaps them — an earlier draft hardcoded 29x25 and built the cell
  //    grid transposed against the one `copyGridToExcel` walks.
  const { visualCols: vc, visualRows: vr } = sb.H.getVisualGridDimensions();
  const pc = sb.H.getTransformedPhysicalConfig(ROT, SIDE);
  sb.ctx.gridCells2D = {};
  sb.ctx.gridData = {};
  let i = 0;
  for (let r = 0; r < vr; r++) {
    sb.ctx.gridCells2D[r] = {};
    for (let c = 0; c < vc; c++) {
      const co = sb.H.getGridCellObject(c, r, vc, vr, pc, 700, 700);
      sb.ctx.gridCells2D[r][c] = co;
      if (!co.inside) continue;
      i++;
      if (i % 7 === 0) continue;                          // holes inside the wafer
      sb.ctx.gridData[co.key] = (i % 5 === 0) ? 'F' : ((i % 11 === 0) ? 'E1' : '1');
    }
  }
  const before = gridSnapshot(sb);
  sb.H.copyGridToExcel();
  const tsv = sb.captured.text;
  const rows = parseHtmlTable(sb.captured.html);
  // The merged band, read out of the artifact. Filler cells carry the gap style verbatim.
  const band = (cells) => (cells || []).filter(c => !/^border:\s*none;$/.test(c.style || ''))
    .reduce((n, c) => n + c.span, 0);
  const tableCols = (rows[2] || []).reduce((n, c) => n + c.span, 0);

  Object.keys(sb.ctx.gridData).forEach(k => { sb.ctx.gridData[k] = 'F'; });
  const parsed = sb.H.readCompanyMapBlock(tsv);
  const frame = frameOf(sb);
  const verdict = sb.H.checkPasteAgainstFrame(parsed, frame);
  if (verdict.ok) sb.H.applyPastedGridRows(parsed, frame);

  chk('fixture', 'prod-width: the table is wider than the map (there IS an aux table to '
    + 'stop short of, else the scope assertion below is vacuous)', tableCols > vc, true);
  chk('INV-ⓐ-6', 'prod-width: the merge is strictly narrower than the table',
    band(rows[0]) < tableCols, true);
  chk('INV-ⓐ-6', 'prod-width: the top merge stops at the map grid',
    [band(rows[0]), band(rows[1])], [vc, vc]);
  chk('INV-F1ⓑ-1', 'prod-width: the reader still recovers the map width',
    parsed.gridWidth, frame.visualCols);
  chk('INV-F1ⓑ-1', 'prod-width: the frame check accepted it', verdict.ok, true);
  chk('INV-F1ⓑ-1', 'prod-width: the fingerprint was verified', verdict.notchVerified, true);
  chk('INV-F1ⓑ-1', 'prod-width: the grid round-trips cell for cell',
    diffKeys(before, gridSnapshot(sb)).slice(0, 8), []);
  evidence.prodWidth = { mapCols: vc, tableCols, titleMerge: band(rows[0]),
    groupBand: band(rows[1]), recoveredWidth: parsed.gridWidth, painted: Object.keys(before).length };
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
// [P0-2] THE FINGERPRINT IS STRUCTURALLY ABSENT ON EVERY NO-MASK MAP — AND ITS
//        ABSENCE MUST REFUSE, NOT WARN.
//
// `loadExistingMap`'s 📐 표준 branch (the highlighted default for a metadata-less map)
// applies chip 1x1 / offset 0 / margin 3 / a diameter that circumscribes the grid, i.e.
// NO circle mask. The bbox then spans the whole grid, so rot 0's notch (`box.maxR + 1`)
// is exactly `visualRows` — off grid. Same for the other three rotations (-1 / -1 / cols).
// Rotation and side PRESERVE the dimensions, so no other guard fires: copy at 0°, click
// 180°, Ctrl+V used to be accepted with one warning line among five.
// ════════════════════════════════════════════════════════════════════════════════
{
  const NO_MASK = {
    physWaferDia: inputStub(300), physChipX: inputStub(1), physChipY: inputStub(1),
    physOffsetX: inputStub(0), physOffsetY: inputStub(0), physEdgeMargin: inputStub(3),
  };
  const mk = (rot) => {
    const sb = buildSandbox(WORK_MAP, `no-mask rot${rot}`, true, NO_MASK,
      { currentRotation: rot, currentSide: 'front' });
    sb.ctx.legend = JSON.parse(JSON.stringify(LEGEND));
    const vc = (rot === 90 || rot === 270) ? ROWS : COLS;
    const vr = (rot === 90 || rot === 270) ? COLS : ROWS;
    const pc = sb.H.getTransformedPhysicalConfig(rot, 'front');
    sb.ctx.gridCells2D = {};
    for (let r = 0; r < vr; r++) {
      for (let c = 0; c < vc; c++) {
        if (!sb.ctx.gridCells2D[r]) sb.ctx.gridCells2D[r] = {};
        sb.ctx.gridCells2D[r][c] = sb.H.getGridCellObject(c, r, vc, vr, pc, 700, 700);
      }
    }
    return { sb, vc, vr };
  };

  // ① the fixture really is a no-mask frame: EVERY cell is inside, so the bbox fills the grid
  const zero = mk(0);
  const allInside = Object.keys(zero.sb.ctx.gridCells2D)
    .every(r => Object.keys(zero.sb.ctx.gridCells2D[r]).every(c => zero.sb.ctx.gridCells2D[r][c].inside));
  chk('P0-2', 'no-mask fixture: every cell is inside (bbox fills the grid)', allInside, true);
  const box = zero.sb.H.getWaferBoundingBox(0, 'front');
  chk('P0-2', 'no-mask fixture: bbox spans the whole grid', [box.minR, box.maxR], [0, zero.vr - 1]);

  // ② the notch is off grid for ALL FOUR rotations -> computeNotchCell must say null
  const perRot = {};
  [0, 90, 180, 270].forEach(rot => {
    const { sb } = mk(rot);
    perRot[rot] = sb.H.computeNotchCell(rot, 'front');
  });
  chk('P0-2', 'no-mask: computeNotchCell is null for every rotation (미상 != 0)',
    perRot, { 0: null, 90: null, 180: null, 270: null });

  // ③ paint + copy at rot 0, then flip the screen to 180 and offer the artifact back.
  const src0 = mk(0);
  let i = 0;
  Object.keys(src0.sb.ctx.gridCells2D).forEach(r => Object.keys(src0.sb.ctx.gridCells2D[r]).forEach(c => {
    i++;
    src0.sb.ctx.gridData[src0.sb.ctx.gridCells2D[r][c].key] = (i % 3 === 0) ? 'F' : '1';
  }));
  src0.sb.H.copyGridToExcel();
  const artifact = src0.sb.captured.text;
  chk('P0-2', 'the rot-0 copy produced an artifact', typeof artifact === 'string' && artifact.length > 0, true);

  const flipped = mk(180);
  // the same painted map, on a 180° screen (same dimensions — that is the whole hazard)
  Object.keys(src0.sb.ctx.gridData).forEach(k => { flipped.sb.ctx.gridData[k] = src0.sb.ctx.gridData[k]; });
  const parsedFlip = flipped.sb.H.readCompanyMapBlock(artifact);
  const frameFlip = frameOf(flipped.sb);
  chk('P0-2', 'the 180° screen has no fingerprint to compare with', frameFlip.notch, null);
  const vFlip = flipped.sb.H.checkPasteAgainstFrame(parsedFlip, frameFlip);
  chk('P0-2', 'the block itself is readable (so the refusal is about the fingerprint)', parsedFlip.ok, true);
  chk('P0-2', 'width/height agree — no other guard would have fired',
    [parsedFlip.gridWidth, parsedFlip.rows.length >= frameFlip.visualRows],
    [frameFlip.visualCols, true]);
  chk('P0-2', 'REFUSED (was: accepted with notchVerified false)', vFlip.ok, false);
  chk('P0-2', 'the refusal says the rotation/side could not be compared',
    /회전·면을 대조할 수/.test(vFlip.reason || ''), true);

  // ④ NEGATIVE CONTROL — what the refusal prevents, measured on the shipped applier.
  //    Bypass the check and apply the rot-0 artifact onto the 180° screen; count the
  //    physical keys whose value changes. This number is the damage, not a proxy for it.
  const damageBefore = { ...flipped.sb.ctx.gridData };
  flipped.sb.H.applyPastedGridRows(parsedFlip, frameFlip);
  const changed = Object.keys(damageBefore)
    .filter(k => (damageBefore[k] || '') !== (flipped.sb.ctx.gridData[k] || '')).length;
  chk('P0-2', 'the prevented damage is non-zero (the axis is live)', changed > 0, true);
  evidence.p0_2 = {
    noMaskNotchByRotation: perRot,
    refused: vFlip.ok === false,
    reason: (vFlip.reason || '').slice(0, 80),
    physicalKeysThatWouldChange: changed,
    ofTotalCells: Object.keys(damageBefore).length,
  };
}

// ════════════════════════════════════════════════════════════════════════════════
// [MEDIUM-3] ONE notch predicate. A PAINTED notch cell carries no fingerprint — the copy
// (correctly) does not overwrite a value with the mark, so the paste must not demand it.
// Before: copy omitted the D, paste required it -> a rect valid-die template could be
// copied and NEVER pasted back, refused with "회전·면이 다릅니다" (the wrong cause).
// Converse: a cell whose real value IS 'D' was silently cleared, one cell per round trip.
// ════════════════════════════════════════════════════════════════════════════════
{
  const sb = buildSandbox(WORK_MAP, 'painted-notch', true);
  sb.ctx.legend = JSON.parse(JSON.stringify(LEGEND));
  buildCells(sb);
  paintFixture(sb);
  const raw = sb.H.computeNotchCell(ROT, SIDE);
  chk('MEDIUM-3', 'the fixture notch is on grid to begin with', raw !== null, true);
  chk('MEDIUM-3', 'and it carries a fingerprint while empty', sb.H.notchMarkCell(ROT, SIDE), raw);

  // paint it — exactly what M4's rect valid-die authoring path produces
  const cell = sb.ctx.gridCells2D[raw.r] ? sb.ctx.gridCells2D[raw.r][raw.c] : null;
  chk('MEDIUM-3', 'the notch position is a real rendered cell', cell !== null, true);
  sb.ctx.gridData[cell.key] = 'D';
  chk('MEDIUM-3', 'a painted notch cell has NO fingerprint', sb.H.notchMarkCell(ROT, SIDE), null);

  // the round trip on such a map: the value 'D' must SURVIVE, and the refusal (if any) must
  // not blame rotation. With no fingerprint the paste refuses on P0-2 grounds instead.
  const before = gridSnapshot(sb);
  sb.H.copyGridToExcel();
  const parsed = sb.H.readCompanyMapBlock(sb.captured.text);
  const frame = frameOf(sb);
  const v = sb.H.checkPasteAgainstFrame(parsed, frame);
  chk('MEDIUM-3', 'refusal does NOT blame rotation/side', /회전·면이 지금과 다릅니다/.test(v.reason || ''), false);
  // and if it is applied anyway (fingerprint absent -> n is null), the real 'D' is kept
  sb.H.applyPastedGridRows(parsed, frame);
  chk('MEDIUM-3', "a cell whose real value is 'D' survives the paste", gridSnapshot(sb)[cell.key], 'D');
  chk('MEDIUM-3', 'no other cell was disturbed', diffKeys(before, gridSnapshot(sb)), []);
  evidence.medium3 = { notchAt: raw, fingerprintWhenPainted: sb.H.notchMarkCell(ROT, SIDE) };
}

// ════════════════════════════════════════════════════════════════════════════════
// [MEDIUM-2] the copy WRITES with the same quoting the paste READS with.
// ════════════════════════════════════════════════════════════════════════════════
{
  const HOSTILE = [
    { value: 'Q', desc: '"고온" 조건', stack: 3 },
    { value: 'T', desc: '1H\t비교', stack: 2 },
    { value: 'N', desc: '두 줄\n설명', stack: 5 },
  ];
  const sb = buildSandbox(WORK_MAP, 'hostile-desc', true);
  sb.ctx.legend = HOSTILE.map(h => ({ ...h, color: '#888', mat_1h: [], mat_mid: [], mat_top: [] }));
  buildCells(sb);
  paintFixture(sb);
  const before = gridSnapshot(sb);
  const legendBefore = JSON.parse(JSON.stringify(sb.ctx.legend));
  sb.H.copyGridToExcel();
  const parsed = sb.H.readCompanyMapBlock(sb.captured.text);
  const frame = frameOf(sb);
  const v = sb.H.checkPasteAgainstFrame(parsed, frame);
  chk('MEDIUM-2', 'a DESC with quote/tab/newline does not break the frame check', v.ok, true);
  chk('MEDIUM-2', 'grid width still recovered', parsed.gridWidth, frame.visualCols);
  sb.ctx.legend.forEach(l => { l.desc = ''; l.stack = ''; });
  if (v.ok) { sb.H.applyPastedGridRows(parsed, frame); sb.H.applyPastedAuxRows(parsed); }
  const byName = {};
  sb.recorded.updates.forEach(u => { byName[u.name] = u.patch; });
  // Only the three hostile rows are asserted: `paintFixture` paints values ('1','F','E1')
  // that this legend does not declare, and `copyHeaderAuxRows` correctly emits those as
  // extra rows with empty stack/desc. Asserting the whole map would be asserting that
  // behaviour, not the quoting.
  const expect = {};
  legendBefore.forEach(l => { expect[String(l.value)] = { desc: String(l.desc), stack: String(l.stack) }; });
  const got = {};
  Object.keys(expect).forEach(k => { got[k] = byName[k]; });
  chk('MEDIUM-2', 'every hostile DESC round-trips VERBATIM (key->value)', got, expect);
  chk('MEDIUM-2', 'and the grid still round-trips', diffKeys(before, gridSnapshot(sb)), []);
  // the property itself, stated on the artifact
  chk('MEDIUM-2', 'parseTsv(serializeTsv(g)) === g holds for the emitted artifact',
    sb.H.serializeTsv(sb.H.parseTsv(sb.captured.text)), sb.captured.text);
  evidence.medium2 = { hostileDescs: HOSTILE.map(h => h.desc), recovered: byName };
}

// ════════════════════════════════════════════════════════════════════════════════
// [MEDIUM-4] the aux-header scan stops on a GRID CELL, even when that cell's value happens
// to be a roster word the DOE panel's ②→① paste taught the roster (MAT/BIN/MAP/가용/...).
// ════════════════════════════════════════════════════════════════════════════════
{
  const sb = buildSandbox(WORK_MAP, 'roster-collision', true);
  sb.ctx.legend = JSON.parse(JSON.stringify(LEGEND));
  buildCells(sb);
  paintFixture(sb);
  const frame = frameOf(sb);
  // paint the LAST grid column of the aux-header row with each roster word in turn, copy,
  // and require the recovered width to stay correct.
  const widths = {};
  ['1', 'BIN', 'MAT', 'MAP', 'COUNT', 'COLOR', '칠함', '가용', '사용', '잔여'].forEach(word => {
    const s2 = buildSandbox(WORK_MAP, `roster:${word}`, true);
    s2.ctx.legend = JSON.parse(JSON.stringify(LEGEND));
    buildCells(s2);
    paintFixture(s2);
    // row 0 is where the aux header rides; the last grid column is the one adjacent to the gap
    const cell = s2.ctx.gridCells2D[0] ? s2.ctx.gridCells2D[0][frame.visualCols - 1] : null;
    if (cell) s2.ctx.gridData[cell.key] = word;
    s2.H.copyGridToExcel();
    widths[word] = s2.H.readCompanyMapBlock(s2.captured.text).gridWidth;
  });
  const wrong = Object.entries(widths).filter(([, w]) => w !== frame.visualCols);
  chk('MEDIUM-4', 'grid width is recovered correctly whatever the edge cell says', wrong, []);
  // the `value` requirement is still load-bearing on its own
  chk('MEDIUM-4', 'a tail of two OTHER aux words is not read as the aux header',
    sb.H.auxHeaderInLine(['1', 'F', 'STACK', 'DESC']), null);
  chk('MEDIUM-4', 'VALUE is the aux header FIRST word (the stop condition premise)',
    sb.H.auxHeadWords()[0], 'VALUE');
  evidence.medium4 = { recoveredWidths: widths, expected: frame.visualCols };
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
  // ── [1d] the four fixes of this round, each put back defective ─────────────────
  ['P0-2: an absent notch fingerprint warns instead of refusing',
    once('  if (!notchOnGrid) {\n    return { ok: false, notchVerified: false,', '  if (false) {\n    return { ok: false, notchVerified: false,')],
  ['P0-2: computeNotchCell hands back an off-grid coordinate instead of null',
    once('  if (cell.r < 0 || cell.r >= visualRows || cell.c < 0 || cell.c >= visualCols) return null;',
      '  // mutated: off-grid coordinates returned as if they were a fingerprint')],
  ['MEDIUM-3: the paste demands D at the notch even when that cell is painted',
    once("  if (cell && (gridData[cell.key] || '') !== '') return null;",
      '  // mutated: a painted notch cell still claims a fingerprint')],
  ['MEDIUM-2: the plain-text side goes back to a raw join (no Excel quoting)',
    once('  const tsv = serializeTsv(matrix);',
      "  const tsv = matrix.map(r => r.join('\\t')).join('\\n');")],
  ['MEDIUM-4: the scan no longer stops at VALUE (a roster word in the grid steals the width)',
    once("    if (columnIdByHeader(f) === 'value') break;     // VALUE = 보조표의 첫 칸. 왼쪽은 격자다.",
      '    // mutated: no VALUE stop')],
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
    m.sb.H.checkPasteAgainstFrame(m.parsed, Object.assign({}, f, { notch: m.sb.H.notchMarkCell(ROT, 'front') })),
    // 🔴 ONE row shorter, not three. At `visualRows: 3` the notch (row 4) falls off the
    //    frame, so the P0-2 refusal fires and MASKS the height check — the "height check
    //    removed" mutation then stayed green. One row shorter keeps the fingerprint on grid,
    //    so the taller-copy check is the only thing that can refuse.
    m.sb.H.checkPasteAgainstFrame(m.parsed, Object.assign({}, f, { visualRows: f.visualRows - 1 })),
  ];
  if (guards.some(g => g.ok)) why.push('a frame guard stopped refusing');

  // ── [1d] the new guards, scored on every mutant too ────────────────────────────
  // P0-2: an absent fingerprint must REFUSE. This is the cheapest possible probe of it.
  if (m.sb.H.checkPasteAgainstFrame(m.parsed, Object.assign({}, f, { notch: null })).ok) {
    why.push('a missing notch fingerprint no longer refuses');
  }
  // The aux header must begin at VALUE — a tail of two OTHER aux words is grid, not a header.
  if (m.sb.H.auxHeaderInLine(['1', 'F', 'STACK', 'DESC']) !== null) {
    why.push('aux header accepted without VALUE');
  }
  // MEDIUM-3: a PAINTED notch cell carries no fingerprint (the copy cannot draw the mark there).
  {
    const raw = m.sb.H.computeNotchCell(ROT, SIDE);
    const c2 = (raw && m.sb.ctx.gridCells2D[raw.r]) ? m.sb.ctx.gridCells2D[raw.r][raw.c] : null;
    if (c2) {
      const save = m.sb.ctx.gridData[c2.key];
      m.sb.ctx.gridData[c2.key] = 'D';
      if (m.sb.H.notchMarkCell(ROT, SIDE) !== null) why.push('a painted notch cell still claims a fingerprint');
      m.sb.ctx.gridData[c2.key] = save;
    }
  }
  if (variant !== 'default') return why;      // the sandbox-building probes run once, not twice

  // P0-2: in a NO-MASK frame (loadExistingMap's 📐 표준 default) the notch is off grid for
  // every rotation, and `computeNotchCell` must say `null` rather than hand back a coordinate
  // that reads as a fingerprint. Needs its own sandbox — the round-trip fixture is masked.
  {
    const s4 = buildSandbox(src, 'probe:no-mask', true, {
      physWaferDia: inputStub(300), physChipX: inputStub(1), physChipY: inputStub(1),
      physOffsetX: inputStub(0), physOffsetY: inputStub(0), physEdgeMargin: inputStub(3),
    }, { currentRotation: 0, currentSide: 'front' });
    const offGrid = [0, 90, 180, 270].filter(rot => s4.H.computeNotchCell(rot, 'front') !== null);
    if (offGrid.length > 0) why.push(`no-mask notch not null at rotation(s) ${offGrid.join(',')}`);
  }

  // MEDIUM-4: a grid cell whose TEXT is a roster/aux word must not steal the recovered width.
  ['BIN', 'COUNT'].forEach(word => {
    const s2 = buildSandbox(src, `probe:${word}`, true);
    s2.ctx.legend = JSON.parse(JSON.stringify(LEGEND));
    buildCells(s2); paintFixture(s2);
    const cell = s2.ctx.gridCells2D[0] ? s2.ctx.gridCells2D[0][f.visualCols - 1] : null;
    if (cell) s2.ctx.gridData[cell.key] = word;
    s2.H.copyGridToExcel();
    const w = s2.H.readCompanyMapBlock(s2.captured.text).gridWidth;
    if (w !== f.visualCols) why.push(`edge cell '${word}' shifts the recovered width (${w} != ${f.visualCols})`);
  });
  // MEDIUM-2: a DESC carrying a quote and a tab must survive the artifact verbatim.
  {
    const s3 = buildSandbox(src, 'probe:hostile', true);
    s3.ctx.legend = [{ value: '1', color: '#888', desc: '"고온"\t조건', stack: 3, mat_1h: [], mat_mid: [], mat_top: [] }];
    buildCells(s3); paintFixture(s3);
    s3.H.copyGridToExcel();
    const p3 = s3.H.readCompanyMapBlock(s3.captured.text);
    const f3 = frameOf(s3);
    const v3 = s3.H.checkPasteAgainstFrame(p3, f3);
    if (!v3.ok) why.push(`hostile DESC broke the frame check: ${(v3.reason || '').slice(0, 34)}`);
    else {
      s3.H.applyPastedAuxRows(p3);
      const hit = s3.recorded.updates.find(u => u.name === '1');
      if (!hit || hit.patch.desc !== '"고온"\t조건') {
        why.push(`hostile DESC came back as ${JSON.stringify(hit && hit.patch.desc)}`);
      }
    }
  }
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
  // H1 protocol: the runner reads this line to tell "red with N assertions" from a crash.
  console.log(`ASSERTIONS ${st.pass + st.failures.length} ${st.failures.length}`);
}
process.exit((st.failures.length === 0 && mutMissed.length === 0) ? 0 : 1);
