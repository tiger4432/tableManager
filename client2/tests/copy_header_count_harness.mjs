// F1ⓐ COPY HEADER MODE + F2 count/save agreement.
// Run: node client2/tests/copy_header_count_harness.mjs [--json]
//
// Same technique as valid_die_authoring_harness.mjs / push_gate_harness.mjs: map_editor.js
// imports ./config.js which touches `window` at module scope, so it cannot be imported in
// node. The functions under test stay module-private; their declarations are sliced out of
// the SOURCE TEXT and evaluated in a vm sandbox with stubs for the module state they read.
//
// TWO SOURCES ARE LOADED. The suite scores the WORKING TREE against `git show HEAD:` for the
// additivity invariant (INV-ⓐ-1) and against HEAD's defective counters for F2. A suite that
// only compares the new code with itself proves the new code is self-consistent, which is
// exactly what the defect already was.
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

const WORK_MAP = readFileSync(join(ROOT, 'client2', 'src', 'map_editor.js'), 'utf8');
const WORK_DOE = readFileSync(join(ROOT, 'client2', 'src', 'doe_bands.js'), 'utf8');
let HEAD_MAP;
try {
  HEAD_MAP = execFileSync('git', ['show', 'HEAD:client2/src/map_editor.js'],
    { cwd: ROOT, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
} catch (e) {
  die(`cannot read HEAD:client2/src/map_editor.js - ${e && e.message}`);
}

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

const SHARED_FNS = [
  'physNum', 'gridDimNum',
  'getScreenShift', 'getTransformedPhysicalConfig',
  'getPhysicalCoords', 'getVisualCoords',
  'isCellInsideWaferFast', 'isCellInsideWafer', 'getWaferBoundingBox',
  'validDieBasis', 'isValidDieAt', 'getGridCellObject',
  'parseCssColor', 'toExcelHex', 'cellFillColor',
  'getVisualGridDimensions', 'escapeHtmlAttr',
  'isProtectedFCell', 'computeLegendCounts', 'fillGrid', 'copyGridToExcel',
];

function buildSandbox(src, label, extraFns = [], extraCode = '') {
  const parts = [];
  SHARED_FNS.concat(extraFns).forEach(n => parts.push(fnFrom(src, label, n)));
  parts.push(constFrom(src, label, 'UNLISTED_VALUE_FILL'));
  // doe_bands pieces the working tree's copy path imports. HEAD's copy path does not use
  // them, but defining them is harmless and keeps ONE sandbox builder.
  parts.push(constFrom(WORK_DOE, 'doe_bands.js', 'ZONES'));
  parts.push(constFrom(WORK_DOE, 'doe_bands.js', 'ZONE_LABEL'));
  parts.push(constFrom(WORK_DOE, 'doe_bands.js', 'DOE_COLUMNS'));
  parts.push(fnFrom(WORK_DOE, 'doe_bands.js', 'parseMaterialList'));

  const captured = { html: null, text: null, toasts: [] };
  const ctx = {
    console: Object.assign(Object.create(console), { debug: () => {} }),
    physFrameOverride: null,
    currentRotation: ROT, currentSide: SIDE,
    validDie: null, boundingBoxCache: {}, el: makeEl(),
    gridData: {}, gridCells2D: {}, legend: [],
    loadedFCells: new Set(),
    selectedTable: 'bonding_map',
    activeBrush: '',
    // stubs for everything outside the two invariants under test
    isOverlayLocked: () => false,
    getThemeColors: () => THEME,
    getCurrentMapKey: () => '4B12',       // 7b canonical is scored by map_key_canonical_harness
    renderGridCanvas: () => {},
    scheduleCellDraft: () => {},
    confirm: () => true,
    alert: () => {},
    showToast: (msg, kind) => { captured.toasts.push({ msg, kind }); },
    writeClipboardRich: (html, text) => { captured.html = html; captured.text = text; return true; },
    __captured: captured,
  };
  vm.createContext(ctx);
  try {
    vm.runInContext(parts.join('\n\n') + '\n' + extraCode
      + `\nglobalThis.__h = { getPhysicalCoords, getVisualCoords, getWaferBoundingBox,`
      + ` getTransformedPhysicalConfig, isCellInsideWaferFast, getGridCellObject,`
      + ` computeLegendCounts, fillGrid, copyGridToExcel,`
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
  ['eachSavableCell', 'copyHeaderEnabled', 'copyHeaderGroups', 'copyHeaderAuxRows',
   'colHeaderWord', 'collectPlanCells']);
const head = buildSandbox(HEAD_MAP, 'HEAD');

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
function savableSet(sb) {
  // Push가 직렬화하는 그 집합. HEAD에는 `eachSavableCell`이 없으므로 여기서는 두 소스에
  // 공통인 **셀 객체의 `inside`와 값**으로 만든다 — 이것이 pushMapData 루프의 술어다.
  const { ctx } = sb;
  const keys = [];
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
function visualRowsOf(sb) {
  return sb.H.getVisualGridDimensions
    ? sb.H.getVisualGridDimensions().visualRows
    : ((sb.ctx.currentRotation === 90 || sb.ctx.currentRotation === 270) ? COLS : ROWS);
}
function nonEmptyOnGrid(sb) {
  return Object.keys(sb.ctx.gridData).filter(k => (sb.ctx.gridData[k] || '') !== '').length;
}

[work, head].forEach(sb => {
  sb.ctx.legend = JSON.parse(JSON.stringify(LEGEND));
  buildCells(sb);
  sb.ctx.activeBrush = '1';
  sb.ctx.gridData = {};
  sb.H.fillGrid();                     // ← 사용자 동작. 상태를 직접 세팅하지 않는다.
});

{
  const wCounts = work.H.computeLegendCounts();
  const hCounts = head.H.computeLegendCounts();
  const wSave = savableSet(work).length;
  const hSave = savableSet(head).length;

  evidence.fillAll = {
    HEAD: { screenCount: hCounts['1'], savableCount: hSave, nonEmptyOnGrid: nonEmptyOnGrid(head),
      droppedByContrastGate: nonEmptyOnGrid(head) - hSave },
    working: { screenCount: wCounts['1'], savableCount: wSave, nonEmptyOnGrid: nonEmptyOnGrid(work),
      droppedByContrastGate: nonEmptyOnGrid(work) - wSave },
  };

  chk('INV-F2-1', 'working tree: screen count == savable count', wCounts['1'], wSave);
  // 역주입: HEAD가 실제로 어긋난다는 것을 보인다. 이 차이가 0이면 위 단언은 아무것도
  // 증명하지 못한 것이다(픽스처가 축을 활성화하지 못했다는 뜻).
  chk('INV-F2-1', 'HEAD (defect version) diverges: screen count > savable count',
    hCounts['1'] > hSave, true);
  // 그리고 HEAD에서는 대비 관문이 발화한다 = Fill All 한 번이 그 맵의 Push를 막는다.
  chk('INV-F2-1', 'HEAD: the contrast gate would REFUSE the push (dropped > 0)',
    nonEmptyOnGrid(head) - hSave > 0, true);
  chk('INV-F2-1', 'working tree: the contrast gate is silent (dropped == 0)',
    nonEmptyOnGrid(work) - wSave, 0);
  chk('INV-F2-1', 'Fill All told the user what it skipped',
    work.captured.toasts.some(t => /유효 다이 밖/.test(t.msg)), true);
}

// ── F2 수량 변화 실측: 같은 격자에서 화면 수량이 얼마나 내려가는가 ────────────────
{
  const before = head.H.computeLegendCounts();
  const after = work.H.computeLegendCounts();
  evidence.countDrop = {
    value: '1', head: before['1'], working: after['1'],
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
    ['eachSavableCell', 'copyHeaderEnabled', 'copyHeaderGroups', 'copyHeaderAuxRows',
     'colHeaderWord', 'collectPlanCells']);
  const loadedHead = buildSandbox(HEAD_MAP, 'loaded-map@HEAD');
  [loaded, loadedHead].forEach(sb => {
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
  const a = loadedHead.H.computeLegendCounts()['1'];
  const b = loaded.H.computeLegendCounts()['1'];
  chk('INV-F2-1', 'a server-loaded map shows the SAME number as before (no user-visible drop)', b, a);
  evidence.loadedMapUnchanged = { head: a, working: b };
}

// ── 좌표 단위 대조: 사라진 셀은 정확히 "원 밖" 집합인가 (키→값) ─────────────────
{
  const wKeys = new Set(savableSet(work));
  const hPainted = new Set(Object.keys(head.ctx.gridData).filter(k => head.ctx.gridData[k] !== ''));
  const removed = [...hPainted].filter(k => !wKeys.has(k));
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
  const sharedData = { ...head.ctx.gridData };
  // 'F'도 섞되 **원 안쪽 셀**에 넣는다. 원 밖에만 넣으면 F의 COUNT가 0이 되어 두 번째 값의
  // 계수 경로가 죽고, 그 축이 죽은 픽스처는 그 축에 대해 아무것도 검증하지 못한다.
  const insideKeys = savableSet(work);
  insideKeys.slice(0, 7).forEach(k => { sharedData[k] = 'F'; });
  work.ctx.gridData = { ...sharedData };
  head.ctx.gridData = { ...sharedData };

  const wOff = runCopy(work, false);
  const hOff = runCopy(head, false);
  chk('INV-ⓐ-1', 'checkbox OFF: html is byte-identical to HEAD', wOff.html === hOff.html, true);
  chk('INV-ⓐ-1', 'checkbox OFF: tsv is byte-identical to HEAD', wOff.text === hOff.text, true);
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

  // ── INV-ⓐ-2 · ⓐ-4 · 보조표 내용 ────────────────────────────────────────────
  const lines = wOn.text.split('\n');
  evidence.headerLines = lines.slice(0, 2 + Math.min(4, lines.length));
  const cellsOf = (i) => (lines[i] || '').split('\t');
  chk('INV-ⓐ-4', 'group row labels come from the DOE declaration',
    cellsOf(1).filter((_, i) => i % 2 === 0).slice(0, 4), ['Base', '1H', 'MID', 'TOP']);
  chk('INV-ⓐ-4', 'group row values are the declared materials',
    cellsOf(1).filter((_, i) => i % 2 === 1).slice(0, 4), ['4B12', 'AF_03', 'MIDLOT_01', 'TOP_01']);
  chk('INV-ⓐ-4', 'aux header words come from DOE_COLUMNS (+COUNT)',
    cellsOf(2).slice(-4), ['VALUE', 'COUNT', 'STACK', 'DESC']);

  // COUNT == 화면 수량 == 저장될 수량, 값별로.
  // 줄 배치: 0 TITLE · 1 그룹 · 2 격자0줄(=보조표 머리줄) · 3.. 격자1줄부터(=보조표 데이터).
  // 보조표가 없는 격자 줄까지 slice(-4)로 긁으면 격자 값이 보조표 행으로 둔갑한다.
  const counts = work.H.computeLegendCounts();
  const nAux = work.H.copyHeaderAuxRows(counts).length;
  const auxByValue = {};
  for (let i = 3; i < 3 + nAux; i++) {
    const f = cellsOf(i).slice(-4);
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
  chk('INV-ⓐ-2', 'COUNT counts INSIDE only (HEAD would have counted more)',
    auxByValue['1'].count < head.H.computeLegendCounts()['1'], true);
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
      ['eachSavableCell', 'copyHeaderEnabled', 'copyHeaderGroups', 'copyHeaderAuxRows',
       'colHeaderWord', 'collectPlanCells']);
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
];

let mutCaught = 0;
const mutMissed = [];
MUTATIONS.forEach(([name, mut]) => {
  const mutated = mut(WORK_MAP);
  if (mutated === WORK_MAP) die(`mutation did not apply: ${name}`);
  let red = false;
  try {
    const sb = buildSandbox(mutated, `mutant(${name})`,
      ['eachSavableCell', 'copyHeaderEnabled', 'copyHeaderGroups', 'copyHeaderAuxRows',
       'colHeaderWord', 'collectPlanCells']);
    sb.ctx.legend = JSON.parse(JSON.stringify(LEGEND));
    buildCells(sb);
    sb.ctx.activeBrush = '1';
    sb.ctx.gridData = {};
    sb.H.fillGrid();
    const counts = sb.H.computeLegendCounts();
    const save = savableSet(sb).length;
    if (counts['1'] !== save) red = true;
    // 두 번째 축: Fill All이 저장 불가 셀을 만들면 대비 관문이 그 맵의 Push를 영구 거절한다.
    // 수량 일치만 보면 이 결함(M2)이 통과한다 — ⓐ와 ⓑ가 서로 다른 증상을 고친다는 증거다.
    if (nonEmptyOnGrid(sb) - save > 0) red = true;

    // OFF byte identity against HEAD, with HEAD's gridData on both sides
    const shared = { ...head.ctx.gridData };
    sb.ctx.gridData = { ...shared };
    head.ctx.gridData = { ...shared };
    const off = runCopy(sb, false);
    const hOff = runCopy(head, false);
    if (off.html !== hOff.html || off.text !== hOff.text) red = true;

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
