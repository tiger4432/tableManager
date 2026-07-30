// F1ⓐ COPY HEADER MODE + F2 count/save agreement.
// Run: node client2/tests/copy_header_count_harness.mjs [--json]
//
// Same technique as valid_die_authoring_harness.mjs / push_gate_harness.mjs: map_editor.js
// imports ./config.js which touches `window` at module scope, so it cannot be imported in
// node. The functions under test stay module-private; their declarations are sliced out of
// the SOURCE TEXT and evaluated in a vm sandbox with stubs for the module state they read.
//
// TWO SOURCES ARE LOADED. The suite scores the WORKING TREE against a PINNED PRE-FIX
// BASELINE for the additivity invariant (INV-ⓐ-1) and against that baseline's defective
// counters for F2. A suite that only compares the new code with itself proves the new code
// is self-consistent, which is exactly what the defect already was.
//
// 🔴 THE BASELINE IS PINNED, NOT `HEAD`. It was `HEAD`, and that was correct only while the
//    F1ⓐ+F2 change was uncommitted. The moment it landed (064550f), `HEAD` BECAME the fixed
//    source: every "the defect version diverges" assertion turned into a self-comparison
//    that can only pass, and the byte-identity check compared a file with itself. Same
//    failure class the suite exists to catch, so the ref is a constant with a name.
//
// FAILS LOUDLY (exit 2) when a function cannot be extracted. A harness that goes green
// because it stopped finding the code is worse than no harness - its green gets cited.
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { tmpdir } from 'node:os';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..', '..');
const JSON_OUT = process.argv.includes('--json');

function die(msg) {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  process.exit(2);
}

// 7524d00 = 064550f^ = the last commit before COPY HEADER MODE + the F2 count convergence.
// Override only to re-baseline deliberately.
const BASE_REF = process.env.MAP_HARNESS_BASE_REF || '7524d00d43fab05f3221c228fc63d163755c91b5';

const WORK_MAP = readFileSync(join(ROOT, 'client2', 'src', 'map_editor.js'), 'utf8');
const WORK_DOE = readFileSync(join(ROOT, 'client2', 'src', 'doe_bands.js'), 'utf8');
// [MEDIUM-2] the copy path now WRITES plain text with tsv.js, the same module the paste path
// READS with, so those symbols are module IMPORTS rather than map_editor locals. Loaded the
// same way company_roundtrip_harness.mjs loads them.
const WORK_TSV = readFileSync(join(ROOT, 'client2', 'src', 'tsv.js'), 'utf8');
let BASE_MAP;
try {
  BASE_MAP = execFileSync('git', ['show', `${BASE_REF}:client2/src/map_editor.js`],
    { cwd: ROOT, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
} catch (e) {
  die(`cannot read ${BASE_REF}:client2/src/map_editor.js - ${e && e.message}`);
}
if (BASE_MAP === WORK_MAP) die('baseline is byte-identical to the working tree - nothing is being compared');

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
// 🔴 THIS HARNESS SLICES TWO REVISIONS (working tree vs a pinned baseline blob), so one
//    spelling cannot address both across a rename: the baseline keeps the old name forever.
//    `name` may therefore be a LIST OF ACCEPTED SPELLINGS, newest first. The first spelling
//    the revision actually has is sliced, and when that is not the canonical (first) one an
//    alias is appended so every consumer below — including `globalThis.__h` — keeps naming
//    the function one way.
// ⚠️ Do not collapse the lists once the baseline moves. They are what keeps this comparison
//    alive across the NEXT rename, instead of the harness dying and being waived.
function fnFrom(src, label, name) {
  const aliases = Array.isArray(name) ? name : [name];
  for (const n of aliases) {
    const m = new RegExp(`(?:async\\s+)?function\\s+${n}\\s*\\(`).exec(src);
    if (!m) continue;
    const out = sliceBalanced(src, m.index, '{', '}');
    if (!out) die(`unbalanced braces for ${n} in ${label}`);
    return (n === aliases[0]) ? out : `${out}\nconst ${aliases[0]} = ${n};`;
  }
  die(`none of [${aliases.join(', ')}] found in ${label}`);
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
// chipX != chipY  (a pitch swap under rot 90/270 shows up)
// rot 90 + back   (rotation and mirror both engaged)
// edgeMargin 1    (NOT 0 - `physNum`'s `|| dflt` turns a declared 0 into 3.0)
// bbox minC != 0  (asserted below, so a dropped bbox term cannot hide)
// startX/startY 1 (visual coords are not the raw c/r)
const DIA = 20, EM = 1, CHIP_X = 2, CHIP_Y = 3;
const COLS = 11, ROWS = 9;
const ROT = 90, SIDE = 'back';

function inputStub(v) { return { value: String(v) }; }
function makeEl() {
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
    copyHeaderToggle: { checked: false },
  };
}

// A fixed palette. `getThemeColors` reads getComputedStyle, which node has not got; both the
// WORKING TREE and HEAD sandboxes get the SAME stub, so the byte comparison below is fair
// and any difference it reports is a difference in THIS round's code.
const THEME = {
  outBg: '#e2e6ec', line: '#d1d5db', lineStrong: '#b9c0cb', insideEmpty: '#eef6f1',
  textEmpty: '#47536b', textOut: '#5b6779', waferEdge: '#1f2733',
  wmFront: '#eef4fd', wmBack: '#fdf6e8', accent: '#1a66d0', success: '#177245',
  warning: '#8a5a00', danger: '#c22f2f', dangerWeak: '#f6dede', rangeFill: '#e3ecfa',
  surface: '#ffffff',
};

// functions that exist only in the working tree (the pre-fix baseline has none of them)
// [F1ⓑ 2026-07-30] `copyTitleText`/`computeNotchCell` were lifted OUT of `copyGridToExcel`
// so the paste path could run the same two computations instead of writing a second copy of
// them. They are working-tree-only (the pinned baseline has neither), which is why they
// belong here rather than in SHARED_FNS.
const WORK_FNS = ['eachSavableCell', 'classifyUnsavableCells', 'serverCellKeySet',
  'headerSpanFor', 'distributeSpans', 'auxColumnSpans',
  'copyHeaderEnabled', 'mapKeyGroupLabel', 'copyHeaderGroups', 'copyHeaderAuxRows',
  'colHeaderWord', 'auxHeadWords', 'collectPlanCells', 'copyTitleText',
  'computeNotchCell', 'notchMarkCell', 'pushBlockingCount'];

const SHARED_FNS = [
  'physNum', 'gridDimNum',
  'getScreenShift', 'getTransformedPhysicalConfig',
  ['getDieIndex', 'getPhysicalCoords'], ['getDbCoords', 'getVisualCoords'],   // renamed 2026-07-31
  'isCellInsideWaferFast', 'isCellInsideWafer', 'getWaferBoundingBox',
  'validDieBasis', 'isValidDieAt', 'getGridCellObject',
  'parseCssColor', 'toExcelHex', 'cellFillColor',
  'getVisualGridDimensions', 'escapeHtmlAttr',
  'isProtectedFCell', 'computeLegendCounts', 'fillGrid', 'copyGridToExcel',
];

// ── the REAL push gate, not a re-typed one ──────────────────────────────────────
// QA 2026-07-29: a harness that re-types the predicate under test scores itself. The gate
// is a straight-line block inside `pushMapData` (a large async function full of fetches),
// so instead of imitating it the block is SLICED OUT BETWEEN TWO CODE ANCHORS and wrapped
// in a function - `return;` inside the slice then means "refused", exactly as it does in
// the app. The alert/confirm TEXT is therefore scored byte for byte, and so is the
// cleanup. Both anchors exist in the pre-fix baseline too, so both sources run the same
// extraction.
const GATE_START = 'const nonEmptyOnGrid = Object.keys(gridData)';
const GATE_END = 'if (updates.length === 0) {';
function gateSlice(src, label) {
  const a = src.indexOf(GATE_START);
  if (a < 0) die(`push-gate start anchor not found in ${label} (${GATE_START})`);
  const b = src.indexOf(GATE_END, a);
  if (b < 0) die(`push-gate end anchor not found in ${label} (${GATE_END})`);
  return src.slice(a, b);
}

function buildSandbox(src, label, extraFns = [], extraCode = '') {
  const parts = [];
  SHARED_FNS.concat(extraFns).forEach(n => parts.push(fnFrom(src, label, n)));
  parts.push(constFrom(src, label, 'UNLISTED_VALUE_FILL'));
  // 폭 정책 상수는 이번 라운드에 생겼다 — 베이스라인에는 없으므로 있을 때만 싣는다.
  // 없는데 필요하면 copyGridToExcel이 ReferenceError로 죽고 die()가 그것을 잡는다.
  ['HDR_COL_PX', 'HDR_PAD_PX', 'HDR_CHAR_PX', 'HDR_MIN_SPAN', 'HDR_MAX_SPAN', 'HDR_GAP_COLS'].forEach(n => {
    if (new RegExp('const\\s+' + n + '\\s*=').test(src)) parts.push(constFrom(src, label, n));
  });
  // doe_bands pieces the working tree's copy path imports. HEAD's copy path does not use
  // them, but defining them is harmless and keeps ONE sandbox builder.
  ['QUOTE', 'TAB'].forEach(n => parts.push(constFrom(WORK_TSV, 'tsv.js', n)));
  ['normalizeNewlines', 'parseTsv', 'needsQuote', 'quoteField', 'serializeTsv']
    .forEach(n => parts.push(fnFrom(WORK_TSV, 'tsv.js', n)));
  parts.push(constFrom(WORK_DOE, 'doe_bands.js', 'ZONES'));
  parts.push(constFrom(WORK_DOE, 'doe_bands.js', 'ZONE_LABEL'));
  parts.push(constFrom(WORK_DOE, 'doe_bands.js', 'DOE_COLUMNS'));
  parts.push(fnFrom(WORK_DOE, 'doe_bands.js', 'parseMaterialList'));

  const captured = { html: null, text: null, toasts: [], alerts: [], confirms: [] };
  const ctx = {
    console: Object.assign(Object.create(console), { debug: () => {} }),
    physFrameOverride: null,
    currentRotation: ROT, currentSide: SIDE,
    validDie: null, boundingBoxCache: {}, el: makeEl(),
    gridData: {}, gridCells2D: {}, legend: [],
    loadedFCells: new Set(),
    selectedTable: 'bonding_map',
    // the served shape for bonding_map (see push_gate_harness fixtures) — `mapKeyGroupLabel`
    // reads this, and a per-table case is asserted separately below.
    tableSchema: { map_key_columns: ['base'] },
    // [F2b] provenance state. Default = "the server sent nothing", which is what a
    // never-loaded map looks like; individual cases set it explicitly.
    loadedIdentity: { table: 'bonding_map', mapKey: '4B12' },
    serverCellKeys: { table: 'bonding_map', mapKey: '4B12', keys: new Set() },
    activeBrush: '',
    // stubs for everything outside the two invariants under test
    isOverlayLocked: () => false,
    getThemeColors: () => THEME,
    getCurrentMapKey: () => '4B12',       // 7b canonical is scored by map_key_canonical_harness
    renderGridCanvas: () => {},
    scheduleCellDraft: () => {},
    // confirm() is answered by the case, so a gate that asks and a gate that does not are
    // distinguishable. Default yes = the user pressing [확인].
    confirmAnswer: true,
    __captured: captured,
  };
  ctx.confirm = (msg) => { captured.confirms.push(msg); return ctx.confirmAnswer; };
  ctx.alert = (msg) => { captured.alerts.push(msg); };
  ctx.showToast = (msg, kind) => { captured.toasts.push({ msg, kind }); };
  ctx.writeClipboardRich = (html, text) => { captured.html = html; captured.text = text; return true; };
  vm.createContext(ctx);
  try {
    vm.runInContext(parts.join('\n\n') + '\n' + extraCode
      // The gate, verbatim. `updates` is the caller's; everything else is module state.
      + `\nfunction runPushGate(updates) {\n${gateSlice(src, label)}\n  return 'PROCEED';\n}`
      + `\nglobalThis.__h = { getDieIndex, getDbCoords, getWaferBoundingBox,`
      + ` getTransformedPhysicalConfig, isCellInsideWaferFast, getGridCellObject,`
      + ` computeLegendCounts, fillGrid, copyGridToExcel, runPushGate, getVisualGridDimensions,`
      + ` eachSavableCell: (typeof eachSavableCell === 'function') ? eachSavableCell : null,`
      + ` classifyUnsavableCells: (typeof classifyUnsavableCells === 'function') ? classifyUnsavableCells : null,`
      + ` copyHeaderGroups: (typeof copyHeaderGroups === 'function') ? copyHeaderGroups : null,`
      + ` copyHeaderAuxRows: (typeof copyHeaderAuxRows === 'function') ? copyHeaderAuxRows : null };`, ctx);
  } catch (e) {
    die(`sandbox evaluation failed for ${label} - ${e && e.message ? e.message : e}`);
  }
  return { ctx, H: ctx.__h, captured };
}

// ── the app's own cell factory builds gridCells2D ────────────────────────────────
// 하네스 규율: 컨트롤 상태를 직접 세팅하지 않는다. `getGridCellObject`는 렌더 루프와
// `getGridCellFromMouseEvent`가 쓰는 그 팩토리이고, 여기서도 그것만 부른다.
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

const LEGEND = [
  { value: '1', color: '#facc15', desc: 'POR', stack: 16, mat_1h: 'AF_03', mat_mid: 'MIDLOT_01', mat_top: 'TOP_01' },
  { value: 'F', color: '#ef4444', desc: 'FAIL', stack: 1, mat_1h: '', mat_mid: '', mat_top: '' },
];

// ── 산출물 파서 (독립 오라클) ────────────────────────────────────────────────────
// 엑셀이 실제로 읽는 것은 HTML이다. 폭·병합·정합은 **그 문자열에서** 읽어야 하고,
// 계산식을 다시 타이핑하면 하네스가 또 자기 자신을 채점한다.
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
const rowWidth = (cells) => cells.reduce((n, c) => n + c.span, 0);

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
// fixture self-check — the defect axes really are live
// ════════════════════════════════════════════════════════════════════════════════
const work = buildSandbox(WORK_MAP, 'working tree',
  WORK_FNS);
const base = buildSandbox(BASE_MAP, 'pre-fix baseline');

{
  const box = work.H.getWaferBoundingBox(ROT, SIDE);
  chk('fixture', 'bbox minC != 0 (a dropped bbox term cannot hide)', box.minC > 0, true);
  chk('fixture', 'chipX != chipY (a pitch swap under rot90 cannot hide)', CHIP_X !== CHIP_Y, true);
  const { vc, vr } = buildCells(work);
  let inside = 0, outside = 0;
  for (let r = 0; r < vr; r++) for (let c = 0; c < vc; c++) (work.ctx.gridCells2D[r][c].inside ? inside++ : outside++);
  // 원 밖 셀이 0이면 이 픽스처는 F2를 원리적으로 재현할 수 없다.
  chk('fixture', 'the circle actually excludes cells (outside > 0)', outside > 0, true);
  evidence.grid = { visualCols: vc, visualRows: vr, cells: vc * vr, inside, outside,
    outsidePct: +(100 * outside / (vc * vr)).toFixed(1) };
}

// ════════════════════════════════════════════════════════════════════════════════
// INV-F2-1  화면에 보이는 수량 == 실제 저장될 수량
//   HEAD와 working tree에 **같은 사용자 동작**(Fill All)을 시키고, 각자의
//   `computeLegendCounts`와 각자의 저장 대상 집합을 비교한다.
// ════════════════════════════════════════════════════════════════════════════════
// Push가 직렬화하는 그 집합. **술어를 다시 타이핑하지 않는다** (QA 2026-07-29): 소스가
// `eachSavableCell`을 갖고 있으면 그 함수를 그대로 돌린다. 갖고 있지 않은 것은 pre-fix
// 베이스라인뿐이고(그 커밋에는 그 함수가 아예 없다), 그때만 두 소스 공통의 셀 객체
// 술어로 되돌아간다 — 베이스라인은 "결함이 있었다"를 보이는 용도이지 채점 대상이 아니다.
function savableSet(sb) {
  const { ctx, H } = sb;
  const keys = [];
  if (H.eachSavableCell) {
    H.eachSavableCell((cellObj) => { keys.push(cellObj.key); });
    return keys;
  }
  Object.keys(ctx.gridCells2D).forEach(rStr => {
    Object.keys(ctx.gridCells2D[rStr] || {}).forEach(cStr => {
      const co = ctx.gridCells2D[rStr][cStr];
      if (!co || !co.inside) return;
      if ((ctx.gridData[co.key] || '') === '') return;
      keys.push(co.key);
    });
  });
  return keys;
}
// pushMapData의 직렬화 루프가 **정말로** 그 함수를 쓰는지는 소스로 확인한다 — 위의
// `eachSavableCell` 호출은 함수를 채점할 뿐, 그 함수가 Push 경로에 꽂혀 있는지는 말하지 않는다.
function pushLoopUsesSharedPredicate(src) {
  const i = src.indexOf('const updates = [];');
  const j = src.indexOf(GATE_START, i);
  if (i < 0 || j < 0) return null;
  const body = src.slice(i, j);
  return {
    callsShared: /eachSavableCell\(/.test(body),
    // a second `inside` predicate typed into the push loop is the exact F2 regression
    retypesInside: /\.inside\b/.test(body),
  };
}
function visualRowsOf(sb) {
  return sb.H.getVisualGridDimensions
    ? sb.H.getVisualGridDimensions().visualRows
    : ((sb.ctx.currentRotation === 90 || sb.ctx.currentRotation === 270) ? COLS : ROWS);
}
function nonEmptyOnGrid(sb) {
  return Object.keys(sb.ctx.gridData).filter(k => (sb.ctx.gridData[k] || '') !== '').length;
}

[work, base].forEach(sb => {
  sb.ctx.legend = JSON.parse(JSON.stringify(LEGEND));
  buildCells(sb);
  sb.ctx.activeBrush = '1';
  sb.ctx.gridData = {};
  sb.H.fillGrid();                     // ← 사용자 동작. 상태를 직접 세팅하지 않는다.
});

{
  const wCounts = work.H.computeLegendCounts();
  const bCounts = base.H.computeLegendCounts();
  const wSave = savableSet(work).length;
  const bSave = savableSet(base).length;

  evidence.fillAll = {
    baseline: { screenCount: bCounts['1'], savableCount: bSave, nonEmptyOnGrid: nonEmptyOnGrid(base),
      droppedByContrastGate: nonEmptyOnGrid(base) - bSave },
    working: { screenCount: wCounts['1'], savableCount: wSave, nonEmptyOnGrid: nonEmptyOnGrid(work),
      droppedByContrastGate: nonEmptyOnGrid(work) - wSave },
  };

  chk('INV-F2-1', 'working tree: screen count == savable count', wCounts['1'], wSave);
  // 역주입: HEAD가 실제로 어긋난다는 것을 보인다. 이 차이가 0이면 위 단언은 아무것도
  // 증명하지 못한 것이다(픽스처가 축을 활성화하지 못했다는 뜻).
  chk('INV-F2-1', 'pre-fix baseline diverges: screen count > savable count',
    bCounts['1'] > bSave, true);
  // 그리고 HEAD에서는 대비 관문이 발화한다 = Fill All 한 번이 그 맵의 Push를 막는다.
  chk('INV-F2-1', 'pre-fix baseline: the contrast gate would REFUSE the push (dropped > 0)',
    nonEmptyOnGrid(base) - bSave > 0, true);
  chk('INV-F2-1', 'working tree: the contrast gate is silent (dropped == 0)',
    nonEmptyOnGrid(work) - wSave, 0);
  chk('INV-F2-1', 'Fill All told the user what it skipped',
    work.captured.toasts.some(t => /유효 다이 밖/.test(t.msg)), true);
}

// ── F2 수량 변화 실측: 같은 격자에서 화면 수량이 얼마나 내려가는가 ────────────────
{
  const before = base.H.computeLegendCounts();
  const after = work.H.computeLegendCounts();
  evidence.countDrop = {
    value: '1', baseline: before['1'], working: after['1'],
    delta: after['1'] - before['1'],
    pct: +(100 * (before['1'] - after['1']) / before['1']).toFixed(1),
  };
  chk('INV-F2-1', 'the drop is real and measurable (not 0)', after['1'] < before['1'], true);
}

// ── 평범한 맵(서버에서 로드된 맵)에서는 수량이 **내려가지 않는다** ────────────────
// Push가 원 밖 셀을 저장한 적이 없으므로, 서버본으로 채워진 격자는 전부 inside다.
// 이 확인이 없으면 "얼마나 줄어드는가"의 답이 "전부 줄어든다"로 오해된다.
{
  const loaded = buildSandbox(WORK_MAP, 'loaded-map',
    WORK_FNS);
  const loadedBase = buildSandbox(BASE_MAP, 'loaded-map@base');
  [loaded, loadedBase].forEach(sb => {
    sb.ctx.legend = JSON.parse(JSON.stringify(LEGEND));
    buildCells(sb);
    const data = {};
    Object.keys(sb.ctx.gridCells2D).forEach(rStr => {
      Object.keys(sb.ctx.gridCells2D[rStr]).forEach(cStr => {
        const co = sb.ctx.gridCells2D[rStr][cStr];
        if (co.inside) data[co.key] = '1';       // 서버가 돌려주는 것과 같은 모양
      });
    });
    sb.ctx.gridData = data;
  });
  const a = loadedBase.H.computeLegendCounts()['1'];
  const b = loaded.H.computeLegendCounts()['1'];
  chk('INV-F2-1', 'a server-loaded map shows the SAME number as before (no user-visible drop)', b, a);
  evidence.loadedMapUnchanged = { baseline: a, working: b };
}

// ── 좌표 단위 대조: 사라진 셀은 정확히 "원 밖" 집합인가 (키→값) ─────────────────
{
  const wKeys = new Set(savableSet(work));
  const bPainted = new Set(Object.keys(base.ctx.gridData).filter(k => base.ctx.gridData[k] !== ''));
  const removed = [...bPainted].filter(k => !wKeys.has(k));
  // 제거된 키가 하나도 inside가 아니어야 한다.
  const insideByKey = new Map();
  Object.keys(work.ctx.gridCells2D).forEach(rStr => {
    Object.keys(work.ctx.gridCells2D[rStr]).forEach(cStr => {
      const co = work.ctx.gridCells2D[rStr][cStr];
      insideByKey.set(co.key, co.inside);
    });
  });
  const wronglyRemoved = removed.filter(k => insideByKey.get(k) === true);
  chk('INV-F2-1', 'every dropped key is OUTSIDE the valid-die set (key->value, not a count)',
    wronglyRemoved, []);
  const keptOutside = [...wKeys].filter(k => insideByKey.get(k) !== true);
  chk('INV-F2-1', 'no outside key survived into the savable set', keptOutside, []);
  evidence.droppedKeys = { total: removed.length, sample: removed.slice(0, 12).sort() };
}

// ════════════════════════════════════════════════════════════════════════════════
// INV-ⓐ-1  체크박스를 끄면 출력이 HEAD와 **바이트로** 같다 (가산적)
// ════════════════════════════════════════════════════════════════════════════════
function runCopy(sb, on) {
  sb.ctx.el.copyHeaderToggle = { checked: on };
  sb.captured.html = null; sb.captured.text = null;
  sb.H.copyGridToExcel();
  return { html: sb.captured.html, text: sb.captured.text };
}

// 같은 격자·같은 gridData를 두 소스에 준다. HEAD의 fillGrid가 더 많이 칠했으므로,
// 비교는 **HEAD가 만든 gridData**를 양쪽에 넣고 한다 — 그래야 차이가 있다면 그 차이는
// 오직 COPY HEADER MODE 코드에서 온 것이다.
{
  const sharedData = { ...base.ctx.gridData };
  // 'F'도 섞되 **원 안쪽 셀**에 넣는다. 원 밖에만 넣으면 F의 COUNT가 0이 되어 두 번째 값의
  // 계수 경로가 죽고, 그 축이 죽은 픽스처는 그 축에 대해 아무것도 검증하지 못한다.
  const insideKeys = savableSet(work);
  insideKeys.slice(0, 7).forEach(k => { sharedData[k] = 'F'; });
  work.ctx.gridData = { ...sharedData };
  base.ctx.gridData = { ...sharedData };

  const wOff = runCopy(work, false);
  const bOff = runCopy(base, false);
  chk('INV-ⓐ-1', 'checkbox OFF: html is byte-identical to the pre-fix baseline', wOff.html === bOff.html, true);
  chk('INV-ⓐ-1', 'checkbox OFF: tsv is byte-identical to the pre-fix baseline', wOff.text === bOff.text, true);
  evidence.offBytes = { html: wOff.html.length, tsv: wOff.text.length };

  const wOn = runCopy(work, true);
  chk('INV-ⓐ-1', 'checkbox ON actually changes the output (else nothing was tested)',
    wOn.html !== wOff.html && wOn.text !== wOff.text, true);
  // 가산성: 켠 출력이 끈 출력의 격자 부분을 **그대로** 포함한다.
  const gridRowsOff = wOff.text.split('\n');
  const gridRowsOn = wOn.text.split('\n').slice(2);          // TITLE·그룹 두 줄을 걷어낸다
  const onGridPart = gridRowsOn.slice(0, gridRowsOff.length)
    .map(line => line.split('\t').slice(0, gridRowsOff[0].split('\t').length).join('\t'));
  chk('INV-ⓐ-1', 'ON output CONTAINS the OFF grid unchanged (additive, not rebuilt)',
    onGridPart.join('\n'), gridRowsOff.join('\n'));

  // ── INV-ⓐ-2 · ⓐ-4 · ⓐ-5 · 보조표 내용 ─────────────────────────────────────
  // 🔴 판독은 **HTML에서** 한다. 헤더 칸이 `colspan`으로 병합된 뒤로 TSV의 i%2·slice(-4)는
  //    거짓말을 한다(병합된 칸 뒤에 빈 열이 따라온다). 그리고 엑셀이 실제로 읽는 것도
  //    HTML이다 — 산출물을 파싱하는 것은 코드를 흉내내는 것이 아니라 독립 오라클이다.
  const lines = wOn.text.split('\n');
  evidence.headerLines = lines.slice(0, 2 + Math.min(4, lines.length));
  const rowsOn = parseHtmlTable(wOn.html);
  const VC = work.H.getVisualGridDimensions().visualCols;
  const groupCells = rowsOn[1] || [];
  const auxAt = (i) => (rowsOn[2 + i] || []).slice(VC + 1, VC + 5).map(c => c.text);

  chk('INV-ⓐ-4', 'group row labels come from the DOE declaration',
    groupCells.filter((_, i) => i % 2 === 0).map(c => c.text), ['Base', '1H', 'MID', 'TOP']);
  chk('INV-ⓐ-4', 'group row values are the declared materials',
    groupCells.filter((_, i) => i % 2 === 1).map(c => c.text), ['4B12', 'AF_03', 'MIDLOT_01', 'TOP_01']);
  chk('INV-ⓐ-4', 'aux header words come from DOE_COLUMNS (+COUNT)',
    auxAt(0), ['VALUE', 'COUNT', 'STACK', 'DESC']);

  // ── INV-ⓐ-5  헤더 칸은 더 이상 맵 셀 한 칸이 아니다 ──────────────────────────
  // 사용자 보고 2026-07-29: "상단 헤더 칸들 적절히 분배하여 병합해서 너무 좁지 않게.
  // 지금은 MAP CELL과 셀 크기 동일." 32px 정사각에 `MIDLOT_01`은 들어가지 않는다.
  const widths = rowsOn.map(rowWidth);
  evidence.headerLayout = {
    totalCols: widths[0], rows: widths.length, distinctRowWidths: [...new Set(widths)],
    groupSpans: groupCells.map(c => ({ text: c.text, span: c.span })),
    auxSpans: (rowsOn[2] || []).slice(VC + 1, VC + 5).map(c => ({ text: c.text, span: c.span })),
  };
  chk('INV-ⓐ-5', 'EVERY html row spans the same number of columns (ragged = Excel shifts the table)',
    [...new Set(widths)].length, 1);
  chk('INV-ⓐ-5', 'no header cell is one map cell wide any more (the reported defect)',
    groupCells.filter(c => c.span < 2).map(c => c.text), []);
  // 균등 분배 금지: 긴 라벨이 짧은 라벨보다 **넓어야** 한다. 같으면 MIDLOT_01이 또 잘린다.
  chk('INV-ⓐ-5', 'the long value gets MORE columns than the short one (not an even split)',
    groupCells[5].span > groupCells[4].span, true);
  chk('INV-ⓐ-5', 'the aux table columns are widened too (DESC was 32px as well)',
    (rowsOn[2] || []).slice(VC + 1, VC + 5).filter(c => c.span < 2), []);
  // TSV와 HTML이 같은 표를 말해야 한다 — 평문에는 병합이 없으므로 빈 열로 자리를 지킨다.
  chk('INV-ⓐ-5', 'the tsv has exactly as many fields per line as the html has columns',
    [...new Set(lines.map(l => l.split('\t').length))], [widths[0]]);

  // COUNT == 화면 수량 == 저장될 수량, 값별로.
  // 줄 배치: 0 TITLE · 1 그룹 · 2 격자0줄(=보조표 머리줄) · 3.. 격자1줄부터(=보조표 데이터).
  const counts = work.H.computeLegendCounts();
  const nAux = work.H.copyHeaderAuxRows(counts).length;
  const auxByValue = {};
  for (let i = 1; i <= nAux; i++) {
    const f = auxAt(i);
    if (f[0]) auxByValue[f[0]] = { count: Number(f[1]), stack: f[2], desc: f[3] };
  }
  evidence.auxTable = auxByValue;
  chk('INV-ⓐ-2', 'COUNT(1) == computeLegendCounts(1)', auxByValue['1'].count, counts['1']);
  chk('INV-ⓐ-2', 'COUNT(F) == computeLegendCounts(F)', auxByValue['F'].count, counts['F']);
  const savableByValue = {};
  savableSet(work).forEach(k => {
    const v = work.ctx.gridData[k];
    savableByValue[v] = (savableByValue[v] || 0) + 1;
  });
  chk('INV-ⓐ-2', 'COUNT == the set ⚡ Push would serialize (per value)',
    { '1': auxByValue['1'].count, F: auxByValue['F'].count },
    { '1': savableByValue['1'] || 0, F: savableByValue['F'] || 0 });
  chk('INV-ⓐ-2', 'COUNT counts INSIDE only (the baseline would have counted more)',
    auxByValue['1'].count < base.H.computeLegendCounts()['1'], true);
  chk('INV-ⓐ-3', 'STACK / DESC come from the DOE declaration, not the grid',
    [auxByValue['1'].stack, auxByValue['1'].desc, auxByValue['F'].stack, auxByValue['F'].desc],
    ['16', 'POR', '1', 'FAIL']);
  chk('INV-ⓐ-3', 'ON mode keeps the legend fill colour in the grid',
    /#facc15/i.test(wOn.html), true);
  // 서식 보존의 강한 형태: 끈 출력의 **모든 격자 행**이, 셀 하나까지, 켠 출력 안에
  // 글자 그대로 들어 있다. 보조표는 그 뒤에 붙기만 하므로 `</tr>` 앞까지를 비교한다.
  // 이게 INV-ⓐ-3의 실질이다 — 범례색·테두리·노치 D·유효/무효 구분이 전부 이 문자열 안에 있다.
  const offRows = wOff.html.split('<tr>').slice(1).map(chunk => '<tr>' + chunk.slice(0, chunk.indexOf('</tr>')));
  const missingRows = offRows.filter(row => !wOn.html.includes(row));
  chk('INV-ⓐ-3', 'every grid row of the OFF output appears verbatim in the ON output',
    missingRows.length, 0);
  chk('INV-ⓐ-3', 'that check compared something (row count > 0)', offRows.length, visualRowsOf(work));

  // 저장용: 사람이 눈으로 확인할 수 있게 실제 산출물을 떨군다.
  const outDir = join(tmpdir(), 'copy_header_harness');
  try {
    mkdirSync(outDir, { recursive: true });
    writeFileSync(join(outDir, 'copy_on.html'), wOn.html, 'utf8');
    writeFileSync(join(outDir, 'copy_on.tsv'), wOn.text, 'utf8');
    evidence.artifacts = outDir;
  } catch (e) { /* 산출물 저장 실패는 판정과 무관 */ }
}

// ════════════════════════════════════════════════════════════════════════════════
// INV-ⓐ-5  좁은 격자 · 넓은 격자 · 빈 라벨 · 아주 긴 라벨
//
// 하나라도 행 폭이 어긋나면 엑셀이 표 전체를 민다. 특히 **좁은 격자**에서 헤더가 격자보다
// 넓어지는 경우(QA가 지적한 상황)는 제목 행이 데이터 행보다 길어지는 모양으로 나타난다 —
// 해법은 헤더를 줄이는 게 아니라 **모든 행을 함께 넓히는 것**이고, 이 블록이 그것을 잰다.
// ════════════════════════════════════════════════════════════════════════════════
function layoutProbe(name, { cols, rows, rot = 0, side = 'front', legendRows = LEGEND, schema }) {
  const sb = buildSandbox(WORK_MAP, `layout/${name}`, WORK_FNS);
  sb.ctx.legend = JSON.parse(JSON.stringify(legendRows));
  if (schema !== undefined) sb.ctx.tableSchema = schema;
  sb.ctx.el.gridCols = inputStub(cols);
  sb.ctx.el.gridRows = inputStub(rows);
  sb.ctx.currentRotation = rot;
  sb.ctx.currentSide = side;
  sb.ctx.boundingBoxCache = {};
  const isRot = (rot === 90 || rot === 270);
  const vc = isRot ? rows : cols, vr = isRot ? cols : rows;
  const pc = sb.H.getTransformedPhysicalConfig(rot, side);
  sb.ctx.gridCells2D = {};
  const data = {};
  for (let r = 0; r < vr; r++) {
    sb.ctx.gridCells2D[r] = {};
    for (let c = 0; c < vc; c++) {
      const co = sb.H.getGridCellObject(c, r, vc, vr, pc, 700, 700);
      sb.ctx.gridCells2D[r][c] = co;
      if (co.inside) data[co.key] = '1';
    }
  }
  sb.ctx.gridData = data;
  const out = runCopy(sb, true);
  const parsed = parseHtmlTable(out.html);
  const widths = parsed.map(rowWidth);
  const tsvWidths = out.text.split('\n').map(l => l.split('\t').length);
  return { sb, html: out.html, tsv: out.text, parsed, widths, tsvWidths,
    visualCols: vc, groupCells: parsed[1] || [] };
}

{
  const LONG = [
    { value: '1', color: '#facc15', desc: 'the very long description a process engineer actually types',
      stack: 16, mat_1h: 'AF_03', mat_mid: 'MIDLOT_01_VERY_LONG_TOKEN_0001, MIDLOT_02', mat_top: 'TOP_01' },
    { value: 'F', color: '#ef4444', desc: '', stack: '', mat_1h: '', mat_mid: '', mat_top: '' },
  ];
  const probes = {
    narrow3: layoutProbe('narrow3', { cols: 3, rows: 3 }),
    narrow5: layoutProbe('narrow5', { cols: 5, rows: 5 }),
    wide51: layoutProbe('wide51', { cols: 51, rows: 51 }),
    rot90: layoutProbe('rot90', { cols: 39, rows: 51, rot: 90, side: 'back' }),
    longLabels: layoutProbe('longLabels', { cols: 9, rows: 9, legendRows: LONG }),
    emptyLabels: layoutProbe('emptyLabels', { cols: 9, rows: 9,
      legendRows: [{ value: '1', color: '#facc15', desc: '', stack: '', mat_1h: '', mat_mid: '', mat_top: '' }],
      schema: {} }),
  };
  evidence.layoutProbes = {};
  Object.entries(probes).forEach(([name, p]) => {
    evidence.layoutProbes[name] = {
      visualCols: p.visualCols, totalCols: p.widths[0], htmlRows: p.widths.length,
      distinctHtmlWidths: [...new Set(p.widths)], distinctTsvWidths: [...new Set(p.tsvWidths)],
      groupSpans: p.groupCells.map(c => `${c.text || '(empty)'}:${c.span}`).join(' '),
    };
    chk('INV-ⓐ-5', `${name}: every html row spans the same column count`,
      [...new Set(p.widths)].length, 1);
    chk('INV-ⓐ-5', `${name}: tsv field count matches the html column count on every line`,
      [...new Set(p.tsvWidths)], [p.widths[0]]);
    chk('INV-ⓐ-5', `${name}: the title row does not overflow the data rows`,
      p.widths[0] >= p.visualCols, true);
    chk('INV-ⓐ-5', `${name}: no header cell is a bare map cell`,
      p.groupCells.filter(c => c.span < 2).map(c => c.text || '(empty)'), []);
  });
  // 좁은 격자에서는 표 전체가 헤더 폭까지 넓어져야 한다 (헤더를 깎으면 다시 잘린다).
  chk('INV-ⓐ-5', 'a 3-column grid widens the WHOLE table instead of crushing the header',
    probes.narrow3.widths[0] > probes.narrow3.visualCols + 1 + 4, true);
  // 넓은 격자에서는 남는 폭이 헤더로 흘러야 한다 (51열인데 헤더가 최소폭이면 낭비).
  chk('INV-ⓐ-5', 'a 51-column grid spends its surplus width on the header',
    rowWidth(probes.wide51.groupCells) > 17, true);
  // 아주 긴 자재 토큰은 상한(HDR_MAX_SPAN)에 걸리되 이웃보다 넓다.
  const lg = probes.longLabels.groupCells;
  chk('INV-ⓐ-5', 'a very long material token is wider than its short neighbours, and capped',
    [lg[5].span > lg[3].span, lg[5].span <= 8 * 4], [true, true]);

  // 사람이 실제로 붙여 보는 산출물. 단언은 "colspan 숫자가 맞다"까지밖에 못 간다.
  const outDir = join(tmpdir(), 'copy_header_harness');
  try {
    mkdirSync(outDir, { recursive: true });
    Object.entries(probes).forEach(([name, p]) => {
      writeFileSync(join(outDir, `layout_${name}.html`), p.html, 'utf8');
      writeFileSync(join(outDir, `layout_${name}.tsv`), p.tsv, 'utf8');
    });
    evidence.layoutArtifacts = outDir;
  } catch (e) { /* 산출물 저장 실패는 판정과 무관 */ }
}

// ════════════════════════════════════════════════════════════════════════════════
// INV-F2b  이미 오염된 초안 — 두 모집단이 갈리고, 두 번째는 한 번 눌러 정리된다
//
// 시나리오: 어제 (수정 전) `Fill All`을 눌러 원 밖 셀이 초안에 들어갔고, 오늘 그 초안이
// 화면에 복원된 상태로 ⚡ Push를 누른다. 종전에는 "격자 크기·시작 좌표·회전·물리 규격을
// 맞추라"는 **작동할 수 없는** 안내를 받았다(그 셀들은 격자 밖이 아니라 원 밖이다).
//
// 채점 대상은 `pushMapData`의 **실제 게이트 블록**이다(코드 앵커로 잘라 그대로 실행).
// 문구를 여기 다시 쓰지 않는다 — 다시 쓰면 이 하네스가 자기 자신을 채점한다.
// ════════════════════════════════════════════════════════════════════════════════
function contaminatedDraftSandbox(src, label, extra = WORK_FNS) {
  const sb = buildSandbox(src, label, extra);
  sb.ctx.legend = JSON.parse(JSON.stringify(LEGEND));
  buildCells(sb);
  // ① 서버가 돌려준 맵: 유효 다이 안쪽만. (Push가 원 밖을 저장한 적이 없다.)
  const serverKeys = [];
  Object.keys(sb.ctx.gridCells2D).forEach(rStr => {
    Object.keys(sb.ctx.gridCells2D[rStr]).forEach(cStr => {
      const co = sb.ctx.gridCells2D[rStr][cStr];
      if (co.inside) serverKeys.push(co.key);
    });
  });
  const data = {};
  serverKeys.forEach(k => { data[k] = '1'; });
  // ② 어제의 오염 초안이 얹은 원 밖 셀 (수정 전 `Fill All`이 만든 그 집합)
  const strayKeys = [];
  Object.keys(sb.ctx.gridCells2D).forEach(rStr => {
    Object.keys(sb.ctx.gridCells2D[rStr]).forEach(cStr => {
      const co = sb.ctx.gridCells2D[rStr][cStr];
      if (!co.inside) { data[co.key] = '1'; strayKeys.push(co.key); }
    });
  });
  sb.ctx.gridData = data;
  sb.ctx.loadedIdentity = { table: 'bonding_map', mapKey: '4B12' };
  sb.ctx.serverCellKeys = { table: 'bonding_map', mapKey: '4B12', keys: new Set(serverKeys) };
  return { sb, serverKeys, strayKeys };
}
// 게이트를 그 상태 그대로 한 번 돌린다. `updates`는 실제 직렬화 집합이다.
function runGate(sb) {
  sb.captured.alerts.length = 0;
  sb.captured.confirms.length = 0;
  sb.captured.toasts.length = 0;
  const keys = savableSet(sb);
  const r = sb.H.runPushGate(keys.map(() => ({})));
  return { outcome: r === 'PROCEED' ? 'PROCEED' : 'REFUSED', keys };
}

{
  const { sb: work2, serverKeys, strayKeys } = contaminatedDraftSandbox(WORK_MAP, 'contaminated/working');
  const { sb: base2 } = contaminatedDraftSandbox(BASE_MAP, 'contaminated/baseline', []);

  chk('fixture', 'the contaminated draft actually carries outside-wafer cells', strayKeys.length > 0, true);

  // ── 분류: 개수가 아니라 **키 집합**으로 대조한다 ──────────────────────────────
  const cls = work2.H.classifyUnsavableCells();
  chk('INV-F2b', 'the stray population is EXACTLY the outside-wafer keys (key set, not a count)',
    cls.outsideStray.slice().sort(), strayKeys.slice().sort());
  chk('INV-F2b', 'nothing is misfiled as off-grid (that population is the truncation guard)',
    cls.offGrid, []);
  chk('INV-F2b', 'nothing is retained when the server set proves the origin', cls.outsideRetained, []);
  // 항등: 세 모집단 + 저장 대상 == 값 있는 셀 전체. 하나라도 새면 안내가 거짓말을 한다.
  const nonEmpty = Object.keys(work2.ctx.gridData).filter(k => (work2.ctx.gridData[k] || '') !== '').length;
  chk('INV-F2b', 'populations partition the non-empty cells (no cell counted twice or lost)',
    cls.offGrid.length + cls.outsideRetained.length + cls.outsideStray.length + savableSet(work2).length,
    nonEmpty);

  // ── 게이트를 실제로 돌린다: 거부 → 문구 → 한 번 눌러 정리 → 재시도 성공 ───────
  const g1 = runGate(work2);
  chk('INV-F2b', 'push is still REFUSED on the contaminated draft', g1.outcome, 'REFUSED');
  chk('INV-F2b', 'the refusal is a WRITE confirm (one press), not a dead-end alert',
    [work2.captured.confirms.length, work2.captured.alerts.length], [1, 0]);
  const msg = work2.captured.confirms[0] || '';
  chk('INV-F2b', 'the message names the real cause (valid-die/outside-wafer), with the count',
    /유효 다이 밖/.test(msg) && msg.includes(String(strayKeys.length)), true);
  chk('INV-F2b', 'the message says adjusting the FRAME cannot fix it (they are not off-grid)',
    /격자 크기·시작 좌표·회전을 맞추는 것으로는 사라지지 않습니다/.test(msg), true);
  chk('INV-F2b', 'the message offers the non-destructive exit too (widen the spec)',
    /물리 규격.*넓혀 다시 시도/.test(msg), true);
  chk('INV-F2b', 'the message states these were never saved on the server',
    /저장된 적도 없습니다/.test(msg), true);
  // 한 번 눌렀다 = confirm 이 true 였다 → 정리가 실제로 일어났는가
  chk('INV-F2b', 'one press removed EXACTLY the stray keys from gridData',
    strayKeys.filter(k => k in work2.ctx.gridData), []);
  chk('INV-F2b', 'the cleanup touched nothing the server sent',
    serverKeys.filter(k => work2.ctx.gridData[k] !== '1'), []);
  chk('INV-F2b', 'the cleanup told the user it happened', work2.captured.toasts.length, 1);
  // 그리고 다시 누르면 통과한다.
  const g2 = runGate(work2);
  chk('INV-F2b', 'the retry PROCEEDS (the cleanup is a real way out)', g2.outcome, 'PROCEED');
  chk('INV-F2b', 'the retry asks nothing (read/retry stays frictionless)',
    [work2.captured.confirms.length, work2.captured.alerts.length], [0, 0]);

  // ── 역주입 ①: 쪼개기 이전의 게이트는 옛 문구를 낸다 ─────────────────────────
  const gb = runGate(base2);
  const bMsg = base2.captured.alerts[0] || '';
  chk('INV-F2b', 'pre-split baseline: same state, but a dead-end alert (no way out)',
    [gb.outcome, base2.captured.alerts.length, base2.captured.confirms.length], ['REFUSED', 1, 0]);
  chk('INV-F2b', 'pre-split baseline: the old text tells the user to fix the FRAME',
    /격자 크기·시작 좌표·회전·물리 규격을 맵 전체가 보이도록 맞춘 뒤/.test(bMsg), true);
  chk('INV-F2b', 'the two texts really differ (a 0-byte difference proves nothing)',
    bMsg !== msg && bMsg.length > 0 && msg.length > 0, true);
  evidence.f2b = {
    serverCells: serverKeys.length, strayCells: strayKeys.length,
    straySample: strayKeys.slice(0, 10).sort(),
    baselineMessage: bMsg.split('\n')[0],
    workingMessage: msg.split('\n')[0],
    retryOutcome: g2.outcome,
  };
}

// ── 출처를 모르면 아무것도 지우지 않는다 (불변식 ③·④) ──────────────────────────
// 조회 실패·절단·다른 맵의 기록이면 `serverCellKeySet()`이 null이고, 그때 원 밖 셀은
// 전부 `outsideRetained`로 남아 **종전과 같은 거부**를 받는다. 정리를 제안하면, 파서가
// 인제션한 맵(마스크 밖에 실재 행이 있는 경우)에서 그 행들이 다음 Push에 삭제된다.
{
  const cases = [
    ['server state unknown (registry/cell read failed)', sb => { sb.ctx.serverCellKeys = null; }],
    ['a DIFFERENT map\'s record (frame switch)', sb => { sb.ctx.serverCellKeys.mapKey = 'OTHER'; }],
    ['a DIFFERENT table\'s record', sb => { sb.ctx.serverCellKeys.table = 'dt_map'; }],
    ['identity not pinned (never loaded)', sb => { sb.ctx.loadedIdentity = null; }],
    ['the server DID send those coordinates (ingested map outside the mask)',
      sb => { Object.keys(sb.ctx.gridData).forEach(k => sb.ctx.serverCellKeys.keys.add(k)); }],
  ];
  cases.forEach(([name, mutate]) => {
    const { sb, strayKeys } = contaminatedDraftSandbox(WORK_MAP, `provenance/${name}`);
    mutate(sb);
    const cls = sb.H.classifyUnsavableCells();
    chk('INV-F2b-③', `no cleanup offered when: ${name}`, cls.outsideStray, []);
    chk('INV-F2b-③', `...and the cells are RETAINED, not lost: ${name}`,
      cls.outsideRetained.length, strayKeys.length);
    const g = runGate(sb);
    chk('INV-F2b-③', `...and the push is refused with the frame alert: ${name}`,
      [g.outcome, sb.captured.alerts.length, sb.captured.confirms.length], ['REFUSED', 1, 0]);
  });
}

// ── 격자 밖 모집단(H2)의 거부는 **약해지지 않았다** ────────────────────────────
// 쪼개는 것이지 무르게 하는 게 아니다. 프레임이 덮지 못하는 좌표는 정리 대상이 아니고,
// 확인 한 번으로 통과할 수도 없다.
{
  const { sb, strayKeys } = contaminatedDraftSandbox(WORK_MAP, 'h2/off-grid');
  // 서버가 준 좌표 중 현재 격자에 아예 없는 것 — H2가 정확히 이 모양이었다(1293 -> 379).
  const offKeys = ['9999_9999', '-9999_-9999', '9999_-9999'];
  offKeys.forEach(k => { sb.ctx.gridData[k] = '1'; sb.ctx.serverCellKeys.keys.add(k); });
  const cls = sb.H.classifyUnsavableCells();
  chk('INV-F2b-H2', 'off-grid keys land in the off-grid population, exactly',
    cls.offGrid.slice().sort(), offKeys.slice().sort());
  chk('INV-F2b-H2', 'off-grid keys are NEVER offered for cleanup',
    cls.outsideStray.filter(k => offKeys.includes(k)), []);
  const g = runGate(sb);
  chk('INV-F2b-H2', 'the off-grid population still gets the hard refusal (alert, no confirm)',
    [g.outcome, sb.captured.alerts.length, sb.captured.confirms.length], ['REFUSED', 1, 0]);
  chk('INV-F2b-H2', 'and it still names replace_map deletion',
    /서버에서 삭제됩니다/.test(sb.captured.alerts[0] || ''), true);
  // 원 밖 셀이 함께 있어도 그 사실을 숨기지 않는다 (화면에 원인의 흔적이 남아야 한다)
  chk('INV-F2b-H2', 'the stray cells are still mentioned so their trace is not lost',
    (sb.captured.alerts[0] || '').includes(String(strayKeys.length)), true);
}

// ── INV-ⓐ-4 확장: 첫 열 그룹 이름이 맵 키 선언에서 나온다 ─────────────────────
// `'Base'`는 `bonding_map`의 컬럼명이었고 📋 Copy to Excel은 모든 맵 테이블에 있다.
{
  const sb = buildSandbox(WORK_MAP, 'group-label', WORK_FNS);
  sb.ctx.legend = JSON.parse(JSON.stringify(LEGEND));
  const labelFor = (schema) => { sb.ctx.tableSchema = schema; return sb.H.copyHeaderGroups()[0].label; };
  const seen = {
    bonding_map: labelFor({ map_key_columns: ['base'] }),
    dt_map: labelFor({ map_key_columns: ['lot', 'slot'] }),
    undeclared: labelFor({}),
    noSchema: labelFor(null),
  };
  evidence.groupLabels = seen;
  chk('INV-ⓐ-4', 'bonding_map keeps the exact word the company form uses', seen.bonding_map, 'Base');
  chk('INV-ⓐ-4', 'dt_map names its OWN key columns (was the hardcoded "Base")', seen.dt_map, 'Lot_Slot');
  chk('INV-ⓐ-4', 'no declaration -> a role name, not a borrowed column name',
    [seen.undeclared, seen.noSchema], ['MAP KEY', 'MAP KEY']);
  chk('INV-ⓐ-4', 'the label is not the literal "Base" for every table (the defect itself)',
    seen.dt_map !== 'Base', true);
}

// ── 직렬화 루프가 정말로 공유 술어를 쓰는가 (소스 수준) ────────────────────────
// 위 검사들은 `eachSavableCell`을 **함수로** 채점한다. 그 함수가 Push 경로에 꽂혀 있다는
// 것은 별개의 사실이고, 소스로만 확인할 수 있다 — 하네스가 루프를 흉내내면 그 순간
// "저장이 ceil, 표시가 round" 계급이 다시 열린다.
{
  const w = pushLoopUsesSharedPredicate(WORK_MAP);
  if (!w) die('could not locate the pushMapData serialization loop in the working tree');
  chk('INV-F2', 'pushMapData builds `updates` through eachSavableCell', w.callsShared, true);
  chk('INV-F2', 'pushMapData does not re-type an `inside` predicate of its own', w.retypesInside, false);
}

// ════════════════════════════════════════════════════════════════════════════════
// F2 수량 변화 **실측** — 사용자가 "숫자가 줄었다"고 느낄 폭이 얼마인가.
// 위 픽스처는 결함 검출용(이방성 칩 · rot90 · back)이라 원 밖 비율이 극단적이다.
// 여기서는 앱의 프리셋 경로(`applyPhysicalGeometry`와 같은 식)로 나오는 **생산 규격**에서
// 잰다. 격자 크기는 방향·물리 규격에서 파생되고, 데이터 범위에서 역산하지 않는다.
// ════════════════════════════════════════════════════════════════════════════════
{
  const gridFor = (dia, em, cx, cy) => {
    const R = Math.max(0, dia / 2 - em);
    let cols = Math.ceil((2 * R) / cx) + 2; if (cols % 2 === 0) cols += 1;
    let rows = Math.ceil((2 * R) / cy) + 2; if (rows % 2 === 0) rows += 1;
    return { cols: Math.max(5, Math.min(100, cols)), rows: Math.max(5, Math.min(100, rows)) };
  };
  const measure = (dia, em, cx, cy, rot, side) => {
    const sb = buildSandbox(WORK_MAP, 'measure',
      WORK_FNS);
    const { cols, rows } = gridFor(dia, em, cx, cy);
    sb.ctx.el.physWaferDia = inputStub(dia); sb.ctx.el.physEdgeMargin = inputStub(em);
    sb.ctx.el.physChipX = inputStub(cx); sb.ctx.el.physChipY = inputStub(cy);
    sb.ctx.el.gridCols = inputStub(cols); sb.ctx.el.gridRows = inputStub(rows);
    sb.ctx.currentRotation = rot; sb.ctx.currentSide = side;
    sb.ctx.boundingBoxCache = {};
    const isRot = (rot === 90 || rot === 270);
    const vc = isRot ? rows : cols, vr = isRot ? cols : rows;
    const pc = sb.H.getTransformedPhysicalConfig(rot, side);
    sb.ctx.gridCells2D = {};
    let inside = 0;
    for (let r = 0; r < vr; r++) {
      sb.ctx.gridCells2D[r] = {};
      for (let c = 0; c < vc; c++) {
        const co = sb.H.getGridCellObject(c, r, vc, vr, pc, 700, 700);
        sb.ctx.gridCells2D[r][c] = co;
        if (co.inside) inside++;
      }
    }
    const total = vc * vr;
    return { spec: `${dia}mm · edge ${em} · chip ${cx}x${cy} · rot${rot} ${side}`,
      grid: `${vc}x${vr}`, cellsBefore: total, cellsAfter: inside,
      dropPct: +(100 * (total - inside) / total).toFixed(1) };
  };
  evidence.fillAllCountDrop = [
    measure(300, 3, 2.5, 2.5, 0, 'front'),
    measure(300, 3, 6, 6, 0, 'front'),
    measure(300, 3, 10, 10, 0, 'front'),
    measure(300, 3, 6, 8, 90, 'front'),
    measure(200, 3, 5, 5, 0, 'front'),
  ];
}

// ════════════════════════════════════════════════════════════════════════════════
// 역주입(mutation) — 결함 버전을 되돌려 넣어 이 suite가 실제로 빨개지는지 본다.
// 적용되지 않은 변이는 "잡았다"도 "놓쳤다"도 아무것도 아니므로 치명적으로 다룬다.
// ════════════════════════════════════════════════════════════════════════════════
const MUTATIONS = [
  ['M1 counts walk gridData again (the F2 defect itself)',
    s => s.replace(/eachSavableCell\(\(cellObj, val\) => \{ counts\[val\] = \(counts\[val\] \|\| 0\) \+ 1; \}\);/,
      "Object.values(gridData).forEach(v => { if (v !== undefined && v !== '') counts[v] = (counts[v] || 0) + 1; });")],
  ['M2 Fill All paints the whole rectangle again',
    s => s.replace('if (!inside) { skippedOutside++; continue; }', '')],
  ['M3 the savable predicate forgets `inside`',
    s => s.replace('if (!cellObj || !cellObj.inside) return;   // Skip blocked outside-wafer cells',
      'if (!cellObj) return;')],
  ['M4 COPY HEADER emits its own COUNT instead of the shared function',
    s => s.replace('copyHeaderAuxRows(computeLegendCounts())',
      "copyHeaderAuxRows((() => { const q = {}; Object.values(gridData).forEach(v => { if (v) q[v] = (q[v]||0)+1; }); return q; })())")],
  ['M5 zone group names are hardcoded instead of read from the DOE declaration',
    s => s.replace('groups.push({ label: ZONE_LABEL[z], value: seen.join(\', \') });',
      "groups.push({ label: z.toUpperCase(), value: seen.join(', ') });")],
  ['M6 the header block is emitted even when the checkbox is OFF (additivity broken)',
    s => s.replace('const headerOn = copyHeaderEnabled();', 'const headerOn = true;')],
  // ── F2b 축 ──────────────────────────────────────────────────────────────────
  ['M7 the gate is NOT split again (one population, the unactionable frame message)',
    s => s.replace(/const strayKeys = unsavable\.outsideStray;/,
      'const strayKeys = []; unsavable.outsideRetained = unsavable.outsideRetained.concat(unsavable.outsideStray);')],
  // 🔴 이 변이만 두 줄에 걸친다. 리터럴 `\n`으로 적으면 **찾지 못한다** — 이 저장소의
  //    map_editor.js는 blob 자체가 CRLF이고, 그때 `die("mutation did not apply")`가 난다.
  //    줄바꿈은 `\r?\n`으로만 적는다.
  ['M8 cleanup ignores provenance (would delete ingested rows outside the mask)',
    s => s.replace(/ {4}if \(known && !known\.has\(k\)\) outsideStray\.push\(k\);\r?\n {4}else outsideRetained\.push\(k\);/,
      '    outsideStray.push(k);')],
  ['M9 a truncated cell load is trusted as a complete server set',
    s => s.replace('const cellsTruncated = !!(result && typeof result.total === \'number\'',
      'const cellsTruncated = false && !!(result && typeof result.total === \'number\'')],
  ['M10 off-grid keys are swept into the cleanable population (H2 guard weakened)',
    s => s.replace('if (inside === undefined) { offGrid.push(k); return; }',
      'if (inside === undefined) { outsideStray.push(k); return; }')],
  ['M11 the first copy-header group label is hardcoded to Base again',
    s => s.replace('const groups = [{ label: mapKeyGroupLabel(), value: getCurrentMapKey() || \'\' }];',
      "const groups = [{ label: 'Base', value: getCurrentMapKey() || '' }];")],
  // M8과 같은 이유로 정규식이다 (소스가 CRLF).
  ['M12 clearGrid stops writing the draft again',
    s => s.replace(/ {2}updateLegendCounts\(\);\r?\n {2}renderGridCanvas\(\);\r?\n {2}scheduleCellDraft\(\);\r?\n\}\r?\n\r?\nfunction fillGrid\(\)/,
      '  renderGridCanvas();\n}\n\nfunction fillGrid()')],
];

// F2b·라벨·clearGrid 변이는 Fill All/COPY 경로가 아니라 **게이트와 소스**에서 빨개진다.
// 그 판정을 여기 한 곳에 모아 두면, 위 루프가 잡지 못하는 변이가 조용히 통과하지 않는다.
function f2bMutantIsRed(mutated) {
  try {
    // ① 라벨: dt_map에서 첫 그룹 이름이 맵 키 선언을 따라가는가
    const lb = buildSandbox(mutated, 'mutant/label', WORK_FNS);
    lb.ctx.legend = JSON.parse(JSON.stringify(LEGEND));
    lb.ctx.tableSchema = { map_key_columns: ['lot', 'slot'] };
    if (lb.H.copyHeaderGroups()[0].label !== 'Lot_Slot') return true;

    // ② 오염 초안: 정리가 정확히 stray 만 지우고, 재시도가 통과하는가
    const { sb, serverKeys, strayKeys } = contaminatedDraftSandbox(mutated, 'mutant/f2b');
    const cls = sb.H.classifyUnsavableCells();
    if (JSON.stringify(cls.outsideStray.slice().sort()) !== JSON.stringify(strayKeys.slice().sort())) return true;
    // 🔴 분할 항등 — 술어(`eachSavableCell`)와 분류(`classifyUnsavableCells`)가 서로의
    //    오라클이다. 술어가 `inside`를 잊으면(M3) 여기서 합이 넘친다. 이 픽스처는 원 밖
    //    셀에 **값이 있어서** 그 축이 살아 있다 (Fill All 픽스처에서는 원 밖이 전부 빈
    //    값이라 M3가 원리적으로 나타나지 않는다).
    const nonEmpty0 = Object.keys(sb.ctx.gridData).filter(k => (sb.ctx.gridData[k] || '') !== '').length;
    if (cls.offGrid.length + cls.outsideRetained.length + cls.outsideStray.length
        + savableSet(sb).length !== nonEmpty0) return true;
    const g1 = runGate(sb);
    if (g1.outcome !== 'REFUSED' || sb.captured.confirms.length !== 1) return true;
    if (serverKeys.some(k => sb.ctx.gridData[k] !== '1')) return true;
    if (runGate(sb).outcome !== 'PROCEED') return true;

    // ③ 출처 미상이면 정리 금지 (불변식 ③)
    const { sb: unk, strayKeys: unkStray } = contaminatedDraftSandbox(mutated, 'mutant/unknown');
    unk.ctx.serverCellKeys = null;
    const cu = unk.H.classifyUnsavableCells();
    if (cu.outsideStray.length !== 0 || cu.outsideRetained.length !== unkStray.length) return true;

    // ④ 절단 응답은 서버 집합으로 승격되지 않는다 (소스 수준 — 로드 경로는 fetch를 탄다)
    if (!/const cellsTruncated = !!\(result && typeof result\.total === 'number'/.test(mutated)) return true;

    // ⑤ 격자 밖은 정리 대상이 아니다 (H2)
    const { sb: h2 } = contaminatedDraftSandbox(mutated, 'mutant/h2');
    const offK = '9999_9999';
    h2.ctx.gridData[offK] = '1'; h2.ctx.serverCellKeys.keys.add(offK);
    if (h2.H.classifyUnsavableCells().outsideStray.includes(offK)) return true;

    // ⑥ 모든 편집 경로가 초안 writer를 부른다 (PRIMITIVES §1)
    const clear = fnFrom(mutated, 'mutant', 'clearGrid');
    if (!/scheduleCellDraft\(\)/.test(clear)) return true;
  } catch (e) {
    return true;   // 돌지도 않는 변이는 잡힌 것이다
  }
  return false;
}

let mutCaught = 0;
const mutMissed = [];
MUTATIONS.forEach(([name, mut]) => {
  const mutated = mut(WORK_MAP);
  if (mutated === WORK_MAP) die(`mutation did not apply: ${name}`);
  let red = false;
  try {
    const sb = buildSandbox(mutated, `mutant(${name})`,
      WORK_FNS);
    sb.ctx.legend = JSON.parse(JSON.stringify(LEGEND));
    buildCells(sb);
    sb.ctx.activeBrush = '1';
    sb.ctx.gridData = {};
    sb.H.fillGrid();
    const counts = sb.H.computeLegendCounts();
    const savedKeys = savableSet(sb);
    const save = savedKeys.length;
    if (counts['1'] !== save) red = true;
    // 🔴 INDEPENDENT ORACLE. `savableSet`이 이제 `eachSavableCell` **그 함수**를 돌리므로
    //    (QA 2026-07-29의 지적대로 술어를 재타이핑하지 않는다), 그 술어 자체를 무너뜨리는
    //    변이(M3)는 화면 수량과 저장 수량을 **함께** 틀리게 만들어 위 대조를 통과한다.
    //    그래서 술어가 아니라 **셀 팩토리의 `inside`**(getGridCellObject의 출력)와 댄다 —
    //    같은 함수의 자기 대조가 아니라 독립 오라클이다.
    const insideByKey = new Map();
    Object.keys(sb.ctx.gridCells2D).forEach(rStr => {
      Object.keys(sb.ctx.gridCells2D[rStr] || {}).forEach(cStr => {
        const co = sb.ctx.gridCells2D[rStr][cStr];
        if (co) insideByKey.set(co.key, co.inside === true);
      });
    });
    if (savedKeys.some(k => insideByKey.get(k) !== true)) red = true;
    // 두 번째 축: Fill All이 저장 불가 셀을 만들면 대비 관문이 그 맵의 Push를 영구 거절한다.
    // 수량 일치만 보면 이 결함(M2)이 통과한다 — ⓐ와 ⓑ가 서로 다른 증상을 고친다는 증거다.
    if (nonEmptyOnGrid(sb) - save > 0) red = true;

    // OFF byte identity against HEAD, with HEAD's gridData on both sides
    const shared = { ...base.ctx.gridData };
    sb.ctx.gridData = { ...shared };
    base.ctx.gridData = { ...shared };
    const off = runCopy(sb, false);
    const bOff = runCopy(base, false);
    if (off.html !== bOff.html || off.text !== bOff.text) red = true;

    const on = runCopy(sb, true);
    const l = on.text.split('\n');
    const labels = (l[1] || '').split('\t').filter((_, i) => i % 2 === 0).slice(0, 4);
    if (JSON.stringify(labels) !== JSON.stringify(['Base', '1H', 'MID', 'TOP'])) red = true;
    const aux = {};
    const nA = sb.H.copyHeaderAuxRows ? sb.H.copyHeaderAuxRows(sb.H.computeLegendCounts()).length : 0;
    for (let i = 3; i < 3 + nA; i++) {
      const f = (l[i] || '').split('\t').slice(-4);
      if (f[0]) aux[f[0]] = Number(f[1]);
    }
    const byValue = {};
    savableSet(sb).forEach(k => { const v = sb.ctx.gridData[k]; byValue[v] = (byValue[v] || 0) + 1; });
    if (aux['1'] !== (byValue['1'] || 0)) red = true;
  } catch (e) {
    red = true;   // a mutant that cannot even run is caught
  }
  if (!red && f2bMutantIsRed(mutated)) red = true;
  if (red) mutCaught++; else mutMissed.push(name);
});

const result = {
  passed: st.pass, failed: st.failures.length, failures: st.failures,
  mutations: { total: MUTATIONS.length, caught: mutCaught, missed: mutMissed },
  evidence,
};
if (JSON_OUT) console.log(JSON.stringify(result, null, 2));
else {
  console.log('\n--- evidence ---');
  console.log(JSON.stringify(evidence, null, 2));
  console.log(`\n--- ${st.pass} passed, ${st.failures.length} failed ---`);
  console.log(`--- mutation check: ${mutCaught}/${MUTATIONS.length} defects caught ---`);
  mutMissed.forEach(m => console.log(`    MISSED: ${m}`));
}
process.exit((st.failures.length === 0 && mutMissed.length === 0) ? 0 : 1);
