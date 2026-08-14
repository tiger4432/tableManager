// ============================================================
// surprise_harness.mjs — 놀라움 장치(화면 ①)를 채점한다.
// Run: node client2/tests/surprise_harness.mjs
//
// The defects this file exists to defend, each one a thing that has already been
// paid for once in this project:
//
//  S1  `Number(null) === 0` — 미검사가 「측정된 0」이 되는 자리. 이 화면에서
//      미검사와 0은 다른 state, 다른 글자, 다른 data-*여야 한다. 픽스처는 둘 다
//      싣고, 둘이 같아지는 변이는 반드시 빨개져야 한다.
//  S2  분모를 랏 크기로 잡는 것. 실측: 랏당 3,525칩 중 725칩만 검사된다 —
//      분모를 틀리면 5배 틀린다. 분모는 서버가 준 `d`뿐이고 없으면 숫자를
//      출고하지 않는다.
//  S3  `level`을 클라가 다시 계산하는 것. 두 구현이 한 척도를 나누면 색과 숫자가
//      갈라진다. 소스에 임계값 함수가 «없어야» 한다.
//  S4  지표 목록 하드코딩. 처음 보는 지표 이름을 선언에 넣으면 그것이 화면에
//      도달해야 한다 — 소스 텍스트가 아니라 «동작»으로 채점한다.
//  S5  범례가 행과 같은 낱말·같은 data-*를 쓰면 트리 전체 훑기는 공허하다.
//      🔴 이건 걱정이 아니라 «측정»이다: 행을 지우는 변이는 CAUGHT여야 하고,
//      범례를 행의 언어로 바꾸는 변이는 ESCAPE여야 한다. 둘이 같이 성립할 때만
//      단언이 «행»을 재고 있다는 뜻이다.
//  S6  없는 웨이퍼를 그리는 것. 거절된 축에는 캔버스가 «아예 없어야» 한다.
//  S7  코어축을 숨기는 것. 오늘 브릿지가 없어 연결 0인데, 자리를 비우면 읽는
//      사람은 축이 둘뿐이었다고 읽는다. 자리와 이유가 남아야 한다.
//  S8  랏 하나를 프레임 하나에 그리는 것. 맵 키가 (bond_lot, bond_slot)이고
//      슬롯마다 격자가 다르다 — 슬롯은 질문의 일부다.
// ============================================================

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src');
const CORE_PATH = join(SRC, 'surprise_core.js');
const VIEW_PATH = join(SRC, 'surprise_view.js');
const MAPCORE_PATH = join(SRC, 'surprise_map_core.js');
const MAPVIEW_PATH = join(SRC, 'surprise_map_view.js');
const ENTRY_PATH = join(SRC, 'ledger_trace.js');
const PAGE_PATH = join(HERE, '..', 'ledger.html');

const die = (msg) => {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  process.exit(2);
};

let CORE_SRC; let VIEW_SRC; let MAPCORE_SRC; let MAPVIEW_SRC; let ENTRY_SRC; let PAGE_SRC;
try {
  CORE_SRC = readFileSync(CORE_PATH, 'utf8');
  VIEW_SRC = readFileSync(VIEW_PATH, 'utf8');
  MAPCORE_SRC = readFileSync(MAPCORE_PATH, 'utf8');
  MAPVIEW_SRC = readFileSync(MAPVIEW_PATH, 'utf8');
  ENTRY_SRC = readFileSync(ENTRY_PATH, 'utf8');
  PAGE_SRC = readFileSync(PAGE_PATH, 'utf8');
} catch (err) {
  die(`could not read a source file: ${err.message}`);
}

// ── the fixture ────────────────────────────────────────────────────────────────────
//
// 🔴 THE METRIC NAMES ARE DELIBERATELY NONSENSE. `zzq` and `wob` are not words
// this codebase has ever seen, so a column of theirs reaching the screen can only
// have come from the DECLARATION — that is S4 scored as behaviour rather than as
// a grep over source text.
const FIX = {
  state: 'ready',
  generated_at: '2026-08-14T18:00:00+09:00',
  scale: [2, 3, 4.5, 6],
  metrics: [
    {
      metric: 'zzq',
      label: '지큐',
      basis: 'inspection_run',
      observed_by: ['AOI'],
      aggregates: [
        { agg: 'chip_rate', label: '발생칩비', unit: 'ratio', denominator: '검사 칩', baseline: 0.065 },
        { agg: 'mean_area', label: '평균면적', unit: 'um2', baseline: 1500 },
      ],
    },
    {
      metric: 'wob',
      label: '워브',
      basis: 'inspection_run',
      aggregates: [
        { agg: 'chip_rate', label: '발생칩비', unit: 'ratio', denominator: '검사 칩', baseline: 0.01 },
        // Declared and NOT in the URL — the 「열 추가」 side of the declaration.
        { agg: 'per_chip', label: '칩당수', unit: '', baseline: 0.02 }],
    },
  ],
  default_columns: [{ metric: 'zzq', agg: 'chip_rate' }, { metric: 'wob', agg: 'chip_rate' }],
  lots: [
    {
      row: 'R-1', lot: 'CL-2601-002', seq: 2, bucket: 'production', bucket_label: '양산',
      inspected: { chips: 725 },
      cells: {
        // 🔴 A MEASURED ZERO. 725 chips were inspected and none had the finding.
        'zzq|chip_rate': { state: 'measured', value: 0, n: 0, d: 725, baseline: 0.065, lift: 0, level: 0 },
        'zzq|mean_area': { state: 'unmeasurable', reason: '결함 0 — 면적 정의 안 됨' },
        // 🔴 AND AN UNSCANNED CELL, IN THE SAME ROW. Not 0. Not clean. Unknown.
        'wob|chip_rate': { state: 'unscanned' },
      },
    },
    {
      row: 'R-2', lot: 'CL-2601-006', seq: 6, bucket: 'production', bucket_label: '양산',
      inspected: { chips: 725 },
      cells: {
        'zzq|chip_rate': { state: 'measured', value: 0.416, n: 302, d: 725, baseline: 0.065, lift: 6.4, level: 4 },
        'zzq|mean_area': { state: 'measured', value: 5210, baseline: 1500, lift: 3.47, level: 2 },
        'wob|chip_rate': { state: 'no_denominator', n: 4, reason: '검사 런 없음' },
      },
    },
    {
      // 🔴 SPECIAL EVALUATION, WITH A LEVEL THE SERVER ASSIGNED. It must be SHOWN,
      // BADGED, and NOT PAINTED — and above all not filtered away.
      row: 'R-3', lot: 'CL-2601-QE2', seq: 7, bucket: 'special_eval', bucket_label: '특수평가',
      inspected: { chips: 240 },
      cells: {
        'zzq|chip_rate': { state: 'measured', value: 0.34, n: 82, d: 240, baseline: 0.065, lift: 5.2, level: 3 },
        'zzq|mean_area': { state: 'measured', value: 4880, baseline: 1500, lift: 3.25, level: 2 },
        'wob|chip_rate': { state: 'measured', value: 0.021, n: 5, d: 240, baseline: 0.01, lift: 2.1, level: 1 },
      },
    },
    {
      // 🔴 THE ROW THAT DISCRIMINATES TWO MORE DEFECTS.
      row: 'R-4', lot: 'CL-2601-021', seq: 9, bucket: 'unknown', bucket_label: '미상',
      inspected: { chips: null },
      cells: {
        // 값은 있는데 분모가 없다 — 「분모 없는 숫자 출고 금지」의 시험대.
        'zzq|chip_rate': { state: 'measured', value: 0.08, n: 12, baseline: 0.065, lift: 1.2, level: 0 },
        // 그리고 'zzq|mean_area' 는 «아예 없다» — 미검사가 아니라 답의 구멍.
        'wob|chip_rate': { state: 'unscanned' },
      },
    },
  ],
  events: [{ seq: 6, label: 'EQP-07 투입', kind: 'equipment' }],
};

const KINDS = { state: 'ready', kinds: [{ kind: 'zzq', label: '지큐', atoms: 900 }, { kind: 'vrn', label: '브른', atoms: 11 }] };

// 🔴 FIXTURE-SHAPE GUARDS. A fixture that stopped discriminating would make this
// whole file pass vacuously, so the properties the assertions depend on are
// checked before anything is compared.
{
  const r0 = FIX.lots[0].cells;
  if (r0['zzq|chip_rate'].value !== 0) die('fixture lost its MEASURED ZERO — S1 cannot be scored');
  if (r0['wob|chip_rate'].state !== 'unscanned') die('fixture lost its UNSCANNED cell — S1 cannot be scored');
  if (FIX.lots[2].bucket !== 'special_eval') die('fixture lost its special-eval row');
  if (!(FIX.lots[2].cells['zzq|chip_rate'].level > 0)) die('special-eval row carries no level — suppression is untestable');
  if (FIX.lots[1].cells['zzq|chip_rate'].d === FIX.lots[1].inspected.chips * 5) die('fixture denominator degenerated');
  if ('zzq|mean_area' in FIX.lots[3].cells) die('fixture lost its ABSENT cell — 미보고 vs 미검사 is untestable');
  if (FIX.lots[3].cells['zzq|chip_rate'].d !== undefined) die('fixture lost its denominator-less rate — S2 is untestable');
  if (/zzq|wob/.test(CORE_SRC) || /zzq|wob/.test(VIEW_SRC)) die('the fixture metric names appear in the source — S4 is vacuous');
}

const AXIS_FIX = {
  row: 'R-2', lot: 'CL-2601-006', slot: '3',
  slots: [{ slot: '1', cols: 11, rows: 11 }, { slot: '3', cols: 12, rows: 13 }, { slot: '7', cols: 13, rows: 13 }],
  axes: [
    {
      axis: 'bond', table: 'bonding_log', basis: 'transferred',
      reference: { table: 'valid_die_ref', map_id: 'PRD-A_BASE' },
      frame: { grid_cols: 5, grid_rows: 5, grid_start_x: 1, grid_start_y: 1, rotation: 0, side: 'front', phys_wafer_dia: 300, phys_chip_x: 40, phys_chip_y: 40, phys_offset_x: 0, phys_offset_y: 0, phys_edge_margin: 3 },
      floor: [{ x: 1, y: 1 }, { x: 2, y: 1 }, { x: 3, y: 1 }, { x: 1, y: 2 }, { x: 2, y: 2 }, { x: 3, y: 2 }],
      cells: [{ x: 2, y: 2 }],
      state: 'ready',
    },
    {
      axis: 'dt', table: 'bonding_log', basis: 'transferred',
      reference: { table: 'valid_die_ref', map_id: 'PRD-A_TAPE' },
      frame: null, floor: null, cells: null, state: 'absent',
    },
    // 🔴 MEASURED UNREACHABLE — 357,796 rows of NULL bridge columns.
    { axis: 'core', state: 'unreachable', reason: 'no_live_bridge' },
  ],
};

// ── module loading, with mutation ──────────────────────────────────────────────────
const b64 = (s) => Buffer.from(s, 'utf8').toString('base64');
const dataUrl = (s) => `data:text/javascript;base64,${b64(s)}`;
const SRC_URL = (name) => new URL(`../src/${name}`, import.meta.url).href;

async function load(coreSrc, viewSrc, mapCoreSrc, mapViewSrc) {
  const coreUrl = dataUrl(coreSrc);
  const mapCoreUrl = dataUrl(
    mapCoreSrc
      .replaceAll("'./map2/declaration.js'", `'${SRC_URL('map2/declaration.js')}'`)
      .replaceAll("'./map2/seating.js'", `'${SRC_URL('map2/seating.js')}'`),
  );
  const mapViewUrl = dataUrl(
    mapViewSrc
      .replaceAll("'./map2/painter.js'", `'${SRC_URL('map2/painter.js')}'`)
      .replaceAll("'./surprise_map_core.js'", `'${mapCoreUrl}'`)
      .replaceAll("'./surprise_core.js'", `'${coreUrl}'`),
  );
  const viewUrl = dataUrl(
    viewSrc
      .replaceAll("'./surprise_core.js'", `'${coreUrl}'`)
      .replaceAll("'./surprise_map_view.js'", `'${mapViewUrl}'`)
      .replaceAll("'./case_control_view.js'", `'${SRC_URL('case_control_view.js')}'`),
  );
  const [core, view, mapCore] = await Promise.all([
    import(coreUrl), import(viewUrl), import(mapCoreUrl),
  ]);
  return { core, view, mapCore };
}

// ── the document stub ──────────────────────────────────────────────────────────────
//
// 🔴 A STUB THAT CANNOT SEE THE DEFECT IS THE DEFECT. That is not a worry here, it
// is measured: the mutant corpus below is applied to the real modules and driven
// through this stub, and every one of them must be CAUGHT.
//
// It deliberately has NO `getContext`, which is what lets the map view be scored
// under bare node: the structure, the counts and the refusal sentences are what
// this screen is judged on, and `painter.js`/`seating.js` carry their own harnesses.
function makeNode(doc, tag, ns) {
  return {
    tagName: String(tag).toUpperCase(),
    namespaceURI: ns || null,
    className: '',
    style: {},
    checked: false,
    children: [],
    attrs: Object.create(null),
    _text: '',
    parentNode: null,
    appendChild(c) { this.children.push(c); c.parentNode = this; return c; },
    removeChild(c) {
      const i = this.children.indexOf(c);
      if (i >= 0) this.children.splice(i, 1);
      c.parentNode = null;
      return c;
    },
    setAttribute(k, v) {
      this.attrs[String(k)] = String(v);
      if (String(k) === 'class') this.className = String(v);
    },
    getAttribute(k) {
      return Object.prototype.hasOwnProperty.call(this.attrs, String(k))
        ? this.attrs[String(k)] : null;
    },
    get firstChild() { return this.children.length ? this.children[0] : null; },
    set textContent(v) { this._text = String(v); this.children.length = 0; },
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); },
  };
}

function makeDoc(theme) {
  const doc = {
    createElement(tag) { return makeNode(doc, tag, null); },
    createElementNS(ns, tag) { return makeNode(doc, tag, ns); },
  };
  doc.documentElement = makeNode(doc, 'html', null);
  doc.documentElement.setAttribute('data-theme', theme || 'light');
  return doc;
}

// ── tolerant tree accessors, scoped by construction ────────────────────────────────
//
// Every helper takes an explicit ROOT. Narrowing an assertion is passing a
// sub-node instead of the mount — see S5.
const walk = (node, out = []) => {
  out.push(node);
  for (const c of node.children) walk(c, out);
  return out;
};
const NOTHING = { tagName: '', className: '', children: [], textContent: '', attrs: {}, getAttribute: () => null };
const first = (list) => (list && list.length ? list[0] : NOTHING);
const classesOf = (n) => String(n.className || '').split(/\s+/).filter(Boolean);
const byClass = (root, cls) => walk(root).filter((n) => classesOf(n).includes(cls));
const byTag = (root, tag) => walk(root).filter((n) => n.tagName === String(tag).toUpperCase());
const byAttr = (root, k, v) => walk(root).filter((n) => n.getAttribute(k) === v);
const hasAttr = (root, k) => walk(root).filter((n) => n.getAttribute(k) !== null);
const stripComments = (s) => s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');

// ── the suite ──────────────────────────────────────────────────────────────────────

async function suite(coreSrc, viewSrc, mapCoreSrc, mapViewSrc) {
  let pass = 0;
  const failed = [];
  const ok = (name, cond, detail) => {
    if (cond) { pass += 1; return; }
    failed.push(detail ? `${name} — ${detail}` : name);
  };
  const eq = (name, got, want) => ok(name, got === want, `got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`);

  const { core, view, mapCore } = await load(coreSrc, viewSrc, mapCoreSrc, mapViewSrc);

  const question = core.parseSurpriseQuery(new URLSearchParams(
    'view=surprise&cols=zzq:chip_rate,zzq:mean_area,wob:chip_rate&mark=CL-2601-006'));
  const model = core.surpriseModel({ body: FIX, kinds: KINDS, question });

  const doc = makeDoc('light');
  const mount = doc.createElement('div');
  view.renderSurprise(doc, mount, model, null,
    { maps: { 'R-2|': AXIS_FIX }, floors: {} });

  // 🔴 EVERY ROW ASSERTION IS SCOPED TO THE TABLE BODY. The legend prints the same
  // words ('미검사', '측정된 0') and a tree-wide check would stay green with every
  // row deleted. See S5, and the mutant pair that measures it.
  const tbody = first(byClass(mount, 'sx-tbody'));
  const legend = first(byClass(mount, 'sx-legend'));

  // ── A. 미검사 ≠ 0 ────────────────────────────────────────────────────────────
  console.log('\n── A. 미검사와 0은 다른 칸 ───────────────────────────────');
  {
    const r0 = first(byAttr(tbody, 'data-lot', 'CL-2601-002'));
    const zero = first(byAttr(r0, 'data-col', 'zzq|chip_rate'));
    const unscanned = first(byAttr(r0, 'data-col', 'wob|chip_rate'));

    eq('A1 the measured zero says it was measured', zero.getAttribute('data-cell-state'), 'measured');
    eq('A2 the unscanned cell says it was not', unscanned.getAttribute('data-cell-state'), 'unscanned');
    ok('A3 and the two are NOT the same state',
      zero.getAttribute('data-cell-state') !== unscanned.getAttribute('data-cell-state'));
    ok('A4 the zero prints a zero', zero.textContent.includes('0%'), zero.textContent);
    eq('A5 the unscanned VALUE is a dash, not a number',
      first(byClass(unscanned, 'sx-cell__v')).textContent, '—');
    ok('A6 and it says out loud that it is not zero',
      unscanned.textContent.includes('0 아님'), unscanned.textContent);
    // 🔴 THE PAINT. A zero is a result and carries a level; an unscanned cell has
    // no level at all, so it can never be painted at the baseline step and read as
    // "normal".
    eq('A7 the measured zero carries the served level', zero.getAttribute('data-heat'), '0');
    eq('A8 the unscanned cell carries NO heat', unscanned.getAttribute('data-heat'), null);

    // 🔴 AN ABSENT CELL IS NOT AN UNSCANNED CELL. 미검사 is a measurement the server
    // made; a cell the response never carried is a hole in the ANSWER.
    const r3 = first(byAttr(tbody, 'data-lot', 'CL-2601-021'));
    const absent = first(byAttr(r3, 'data-col', 'zzq|mean_area'));
    eq('A11 a cell the response omitted reads as 미보고', absent.getAttribute('data-cell-state'), 'unreported');
    ok('A12 and NOT as 미검사', absent.getAttribute('data-cell-state')
      !== first(byAttr(r3, 'data-col', 'wob|chip_rate')).getAttribute('data-cell-state'));
    ok('A13 the two nothings read differently on screen',
      absent.textContent.includes('미보고') && !absent.textContent.includes('미검사'), absent.textContent);

    const unmeasurable = first(byAttr(r0, 'data-col', 'zzq|mean_area'));
    eq('A9 unmeasurable is its own state', unmeasurable.getAttribute('data-cell-state'), 'unmeasurable');
    ok('A10 and it carries the server reason', unmeasurable.textContent.includes('면적 정의 안 됨'), unmeasurable.textContent);
  }

  // ── B. 분모 ──────────────────────────────────────────────────────────────────
  console.log('\n── B. 분모 없는 숫자 출고 금지 ────────────────────────────');
  {
    const r1 = first(byAttr(tbody, 'data-lot', 'CL-2601-006'));
    const rate = first(byAttr(r1, 'data-col', 'zzq|chip_rate'));
    eq('B1 the denominator is the INSPECTED chip count', rate.getAttribute('data-denominator'), null);
    const frac = first(byClass(rate, 'sx-cell__f'));
    eq('B2 and it reaches the DOM as the fraction', frac.getAttribute('data-denominator'), '725');
    ok('B3 the fraction is on screen beside the percentage',
      rate.textContent.includes('302/725'), rate.textContent);
    // 🔴 725, NOT 3525. A client that took the lot size would be wrong by 5×.
    const chips = first(byClass(r1, 'sx-row__chips'));
    ok('B4 the inspected count is stated per row', chips.textContent.includes('725'), chips.textContent);

    const nod = first(byAttr(r1, 'data-col', 'wob|chip_rate'));
    eq('B5 a rate with no denominator refuses', nod.getAttribute('data-cell-state'), 'no_denominator');
    ok('B6 and the count still shows, because the count is real',
      nod.textContent.includes('4건'), nod.textContent);
    ok('B7 with the server reason for why there is no rate',
      nod.textContent.includes('검사 런 없음'), nod.textContent);
    ok('B8 no percentage is printed without a denominator', !nod.textContent.includes('%'), nod.textContent);

    // 🔴 AND A *MEASURED* RATE WITH NO DENOMINATOR IS REFUSED TOO. This is the
    // one that would be wrong by 5× if the client guessed the lot size.
    const bare = first(byAttr(first(byAttr(tbody, 'data-lot', 'CL-2601-021')), 'data-col', 'zzq|chip_rate'));
    eq('B9 a measured rate with no denominator refuses', bare.getAttribute('data-cell-state'), 'no_denominator');
    ok('B10 and prints no percentage', !bare.textContent.includes('%'), bare.textContent);
    ok('B11 the count survives, because the count is real', bare.textContent.includes('12건'), bare.textContent);
    eq('B12 an unreported chip count is not 0', first(byClass(first(byAttr(tbody, 'data-lot', 'CL-2601-021')), 'sx-row__chips--none')).getAttribute('data-chips'), 'none');
  }

  // ── C. level은 서버가 낸다 ────────────────────────────────────────────────────
  console.log('\n── C. 조건부서식 단계는 서버의 것 ─────────────────────────');
  {
    const r1 = first(byAttr(tbody, 'data-lot', 'CL-2601-006'));
    eq('C1 the served level reaches the cell verbatim',
      first(byAttr(r1, 'data-col', 'zzq|chip_rate')).getAttribute('data-heat'), '4');
    eq('C2 and a different column keeps ITS level',
      first(byAttr(r1, 'data-col', 'zzq|mean_area')).getAttribute('data-heat'), '2');
    // 🔴 NO THRESHOLD FUNCTION EXISTS IN THE SOURCE. S3, scored as text because
    // the defect is a second implementation existing at all.
    const bare = stripComments(coreSrc);
    ok('C3 the core carries no client-side threshold ladder',
      !/l\s*>=\s*bands\[/.test(bare) && !/function heatLevel/.test(bare), 'a level ladder is back in the core');
    ok('C4 the legend says who assigned the step',
      legend.textContent.includes('단계 판정: 서버'), legend.textContent.slice(0, 200));
  }

  // ── D. 특수평가: 뱃지만, 칠하지 않고, 숨기지 않고 ─────────────────────────────
  console.log('\n── D. 특수평가 행 ────────────────────────────────────────');
  {
    const rows = byClass(tbody, 'sx-row');
    eq('D1 every lot is in the table, special included', rows.length, 4);
    const qe = first(byAttr(tbody, 'data-lot', 'CL-2601-QE2'));
    ok('D2 it is not hidden', qe !== NOTHING);
    eq('D3 it is badged', first(byClass(qe, 'sx-bucket')).getAttribute('data-bucket-badge'), 'special_eval');
    ok('D4 the badge says so in words', qe.textContent.includes('특수평가'), qe.textContent.slice(0, 120));
    const cell = first(byAttr(qe, 'data-col', 'zzq|chip_rate'));
    eq('D5 and its cell is NOT painted despite a served level', cell.getAttribute('data-heat'), null);
    eq('D6 the suppression is stated, not silent', cell.getAttribute('data-heat-suppressed'), 'special_eval');
    ok('D7 the value is still printed', cell.textContent.includes('34.0%'), cell.textContent);
    ok('D8 the legend explains the rule', legend.textContent.includes('칠하지 않습니다'), '');
  }

  // ── E. 지표 목록은 선언에서 나온다 ────────────────────────────────────────────
  console.log('\n── E. 하드코딩된 지표 목록 없음 ───────────────────────────');
  {
    const cols = first(byClass(mount, 'sx-cols'));
    ok('E1 the declared metric reaches the column bar',
      byAttr(cols, 'data-col', 'zzq|chip_rate').length > 0);
    ok('E2 a SECOND declared metric does too',
      byAttr(cols, 'data-col', 'wob|chip_rate').length > 0);
    ok('E3 a declared aggregate that is not up is offered for adding',
      byAttr(cols, 'data-col-add', 'wob|per_chip').length > 0);
    // 🔴 THE REAL TEST OF S4: a metric name invented HERE, right now, reaches the
    // screen without a line changing in the source.
    const invented = core.surpriseModel({
      body: { ...FIX, metrics: FIX.metrics.concat([{ metric: 'qqx', label: '큐엑스', aggregates: [{ agg: 'zz', label: '집계', unit: '' }] }]) },
      kinds: KINDS,
      question: core.parseSurpriseQuery(new URLSearchParams('view=surprise&cols=qqx:zz')),
    });
    const d2 = makeDoc('light');
    const m2 = d2.createElement('div');
    view.renderSurprise(d2, m2, invented, null, null);
    ok('E4 a metric declared one second ago is a column',
      byAttr(first(byClass(m2, 'sx-table')), 'data-col', 'qqx|zz').length > 0);
    ok('E5 and its label came from the declaration',
      first(byClass(m2, 'sx-table')).textContent.includes('큐엑스'));
    // An item the kind catalog knows and the metric declaration does not.
    ok('E6 a declared-but-unaggregated item is shown, not dropped',
      byAttr(cols, 'data-item', 'vrn').length > 0);
    // A column the URL asks for that nothing declares.
    const strayModel = core.surpriseModel({
      body: FIX, kinds: KINDS,
      question: core.parseSurpriseQuery(new URLSearchParams('view=surprise&cols=nope:none')),
    });
    eq('E7 an undeclared column is flagged rather than silently dropped',
      strayModel.columns.length, 1);
    eq('E8 and it knows it is undeclared', strayModel.columns[0].declared, false);
  }

  // ── F. URL은 질문이다 ────────────────────────────────────────────────────────
  console.log('\n── F. 열 구성 · 마킹 · 슬롯이 URL에 실린다 ─────────────────');
  {
    const q = core.parseSurpriseQuery(new URLSearchParams('view=surprise&cols=zzq:chip_rate,wob:chip_rate&mark=A,B&slot=3'));
    eq('F1 columns parse out of the URL', q.cols.length, 2);
    eq('F2 marks parse out of the URL', q.marked.join('|'), 'A|B');
    eq('F3 the slot parses out of the URL', q.slot, '3');
    const back = core.surpriseQuery(q);
    ok('F4 and the question round-trips', back.includes('cols=') && back.includes('mark=') && back.includes('slot=3'), back);
    const dropped = core.surpriseQuery(core.withoutColumn(q, { metric: 'zzq', agg: 'chip_rate' }));
    ok('F5 dropping a column is a URL, not a mode', dropped.includes('wob%3Achip_rate') && !dropped.includes('zzq%3Achip_rate'), dropped);
    const toggled = core.toggleMark(q, 'A');
    eq('F6 unmarking removes exactly one lot', toggled.marked.join('|'), 'B');
    // Every column control is an anchor.
    const chips = byClass(first(byClass(mount, 'sx-cols')), 'sx-colchip__drop');
    ok('F7 column removal is an anchor with an href', chips.length > 0 && first(chips).getAttribute('href').startsWith('?view=surprise'));
  }

  // ── G. 범례는 행의 언어를 쓰지 않는다 ─────────────────────────────────────────
  console.log('\n── G. 범례 vs 행 ────────────────────────────────────────');
  {
    // 🔴 STRUCTURAL, NOT JUST SCOPED. The legend carries `data-heat-key`; only rows
    // carry `data-heat`. So even a careless tree-wide sweep cannot be satisfied by
    // the legend — and the mutant pair below measures that this actually holds.
    eq('G1 the legend uses no row attribute', hasAttr(legend, 'data-heat').length, 0);
    ok('G2 it uses its own instead', hasAttr(legend, 'data-heat-key').length >= 4);
    eq('G3 the legend has no table rows in it', byClass(legend, 'sx-row').length, 0);
    ok('G4 painted cells exist only in the table body',
      hasAttr(tbody, 'data-heat').length > 0);
  }

  // ── H. 3축 맵: 실물 위에, 없는 것은 그리지 않고 ──────────────────────────────
  console.log('\n── H. 3축 맵 ────────────────────────────────────────────');
  {
    const maps = first(byClass(mount, 'sx-maps'));
    eq('H1 the marked lot has a map row', byAttr(maps, 'data-map-lot', 'CL-2601-006').length, 1);
    const row = first(byAttr(maps, 'data-map-lot', 'CL-2601-006'));
    const panels = byClass(row, 'sx-map');
    eq('H2 all three axes keep their places', panels.length, 3);

    const bond = first(byAttr(row, 'data-axis', 'bond'));
    eq('H3 the bonding axis rendered', bond.getAttribute('data-axis-ok'), '1');
    eq('H4 on the real valid-die floor', first(byTag(bond, 'CANVAS')).getAttribute('data-floor-cells'), '6');
    eq('H5 with the defect chip on it', first(byTag(bond, 'CANVAS')).getAttribute('data-mark-cells'), '1');
    ok('H6 and it names its provenance', bond.textContent.includes('valid_die_ref|PRD-A_BASE'), bond.textContent);
    ok('H7 and states the coordinate unit', bond.textContent.includes('오리진 기준 칸수'), bond.textContent);

    // 🔴 S7 — the core axis is UNREACHABLE and it says so IN ITS OWN PLACE.
    const coreAxis = first(byAttr(row, 'data-axis', 'core'));
    ok('H8 the core axis is present, not hidden', coreAxis !== NOTHING);
    eq('H9 it is flagged unreachable, distinctly from a failure', coreAxis.getAttribute('data-unreachable'), '1');
    ok('H10 and says 연결 없음 in words', coreAxis.textContent.includes('연결 없음'), coreAxis.textContent);
    ok('H11 naming absence rather than zero', coreAxis.textContent.includes('0이 아니라 부재'), coreAxis.textContent);
    // 🔴 S6 — NOTHING IS DRAWN THAT WAS NOT SOURCED.
    eq('H12 a refused axis has NO canvas at all', byTag(coreAxis, 'CANVAS').length, 0);
    const dt = first(byAttr(row, 'data-axis', 'dt'));
    eq('H13 an axis with no frame also draws nothing', byTag(dt, 'CANVAS').length, 0);
    ok('H14 and says which leg was missing', dt.textContent.includes('프레임 미등록'), dt.textContent);
    // No invented wafer anywhere in the source.
    ok('H15 the map view contains no circle-drawing path',
      !/Math\.sqrt|<circle|arc\(/.test(stripComments(mapViewSrc)), 'a circular grid crept back in');
  }

  // ── I. 슬롯은 질문의 일부 ────────────────────────────────────────────────────
  console.log('\n── I. 랏 하나 ≠ 프레임 하나 ──────────────────────────────');
  {
    const row = first(byAttr(first(byClass(mount, 'sx-maps')), 'data-map-lot', 'CL-2601-006'));
    const strip = first(byClass(row, 'sx-slots'));
    ok('I1 the slot strip exists', strip !== NOTHING);
    eq('I2 listing the slots the lot ACTUALLY has', strip.getAttribute('data-slot-count'), '3');
    eq('I3 the served slot is marked current', first(byAttr(strip, 'aria-current', 'true')).getAttribute('data-slot'), '3');
    ok('I4 each slot is an anchor carrying the whole question',
      first(byAttr(strip, 'data-slot', '7')).getAttribute('href').includes('slot=7'));
    // 🔴 THE GRIDS DIFFER PER SLOT, AND THE SCREEN SAYS SO.
    eq('I5 differing grids are announced',
      first(byClass(strip, 'sx-slots__note')).getAttribute('data-slot-dims'), '3');
    ok('I6 in words', strip.textContent.includes('슬롯마다 격자가 다릅니다'), strip.textContent);
    const cached = mapCore.mapSection(model, { 'R-2|': AXIS_FIX }, {});
    eq('I7 the map is keyed on the bonding row id, not the lot name', cached.lots[0].row, 'R-2');
  }

  // ── J. 차트 ──────────────────────────────────────────────────────────────────
  console.log('\n── J. 소형 다중 차트 ─────────────────────────────────────');
  {
    const charts = first(byClass(mount, 'sx-charts'));
    eq('J1 one chart per column', byClass(charts, 'sx-chart').length, model.columns.length);
    const c0 = first(byAttr(charts, 'data-chart', 'zzq|chip_rate'));
    ok('J2 the chart states its own denominator', c0.textContent.includes('/4 랏 표시'), c0.textContent);
    // Special-eval lots are not in the line but are on the axis.
    ok('J3 the special lot is marked apart from the line',
      byAttr(c0, 'data-special-lot', 'CL-2601-QE2').length === 1);
    ok('J4 the marked lot has an emphasised dot',
      first(byAttr(c0, 'data-dot-lot', 'CL-2601-006')).getAttribute('data-dot-marked') === '1');
    const c1 = first(byAttr(charts, 'data-chart', 'wob|chip_rate'));
    ok('J5 unscanned lots are counted as gaps, not plotted as zero',
      c1.getAttribute('data-chart-gaps') !== null || c1.textContent.includes('미측정'), c1.textContent);
    ok('J6 the ledger event is on the axis', byAttr(c0, 'data-event', 'EQP-07 투입').length > 0);
  }

  // ── K. 배선 ──────────────────────────────────────────────────────────────────
  console.log('\n── K. 배선 ──────────────────────────────────────────────');
  {
    ok('K1 the page carries the mount', /id="lt-surprise"/.test(PAGE_SRC));
    ok('K2 the view is a URL, not a mode', /view=surprise/.test(PAGE_SRC));
    ok('K3 the entry imports the renderer', /renderSurprise/.test(ENTRY_SRC));
    ok('K4 and asks the confirmed aggregate route', /api\/ledger\/lots/.test(ENTRY_SRC));
    ok('K5 and the confirmed map route', /api\/ledger\/lot_map/.test(ENTRY_SRC));
    ok('K6 it has its own session guard', /surpriseSession/.test(ENTRY_SRC));
    ok('K7 the surprise view does not also run the console',
      /if \(view === SURPRISE_VIEW\)[\s\S]{0,1400}?return;/.test(ENTRY_SRC));
    ok('K8 marking is delegated once on the mount, not bound per row',
      /mount\.addEventListener\('change'/.test(ENTRY_SRC) && !/addEventListener/.test(stripComments(viewSrc)));
    ok('K9 no new dependency was added',
      !/from '(?!\.\/|\.\.\/)/.test(stripComments(viewSrc) + stripComments(coreSrc) + stripComments(mapViewSrc)));
    ok('K10 the renderer is reused, not rewritten',
      /from '\.\/map2\/painter\.js'/.test(mapViewSrc) && /from '\.\/map2\/seating\.js'/.test(mapCoreSrc));
    ok('K11 no innerHTML anywhere in the views',
      !/innerHTML|outerHTML|insertAdjacentHTML/.test(stripComments(viewSrc) + stripComments(mapViewSrc)));
  }

  // ── L. 가독성 = 기능 ─────────────────────────────────────────────────────────
  console.log('\n── L. 가독성 ────────────────────────────────────────────');
  {
    const block = PAGE_SRC.slice(PAGE_SRC.indexOf('놀라움 장치 (?view=surprise)'));
    const cssEnd = block.indexOf('</style>');
    const css = cssEnd > 0 ? block.slice(0, cssEnd) : block;
    const sizes = [...css.matchAll(/font-size:\s*([\d.]+)px/g)].map((m) => Number(m[1]));
    ok('L1 the surprise CSS declares font sizes at all', sizes.length > 15, `${sizes.length}`);
    const small = sizes.filter((s) => s < 13);
    ok('L2 nothing is below 13px', small.length === 0, `found ${JSON.stringify(small)}`);
    ok('L3 the wide table scrolls rather than shrinking the type',
      /\.sx-tablewrap\s*\{[^}]*overflow-x:\s*auto/.test(css));
    ok('L4 cell values are 15px', /\.sx-cell__v\s*\{[^}]*font-size:\s*15px/.test(css));
    ok('L5 the unmarked rows are not hidden or faded (스팟파이어식)',
      !/\.sx-row:not\(\.sx-row--marked\)[^{]*\{[^}]*(display:\s*none|opacity:\s*0\.[0-5])/.test(css));
    ok('L6 the refused axis is dashed, not dimmed',
      /\.sx-map--refused\s*\{[^}]*border-style:\s*dashed/.test(css)
      && !/\.sx-map--refused[^{]*\{[^}]*opacity:\s*0\.[0-5]/.test(css));
  }

  return { pass, fail: failed.length, failed };
}

// ── the mutant corpus ──────────────────────────────────────────────────────────────
//
// Every DEFECT must be CAUGHT. Every CONTROL must ESCAPE. A mutation that did not
// change the source is a `die()` — an anchor that moved silently retires the entry
// and the corpus stops measuring anything.
const DEFECTS = [
  ['core', 'S1 unscanned collapses into the measured path',
    (s) => s.replace("if (wire === 'unscanned') {", "if (false && wire === 'unscanned') {")],
  ['core', 'S1 an absent cell is called 미검사 instead of 미보고',
    (s) => s.replace("state: 'unreported', value: null, n: null, d: null,", "state: 'unscanned', value: null, n: null, d: null,")],
  ['core', 'S3 the level is derived from the lift instead of served',
    (s) => s.replace('const served = numOrNull(raw.level);', 'const served = numOrNull(raw.lift);')],
  ['core', 'S2 a rate prints without its denominator',
    (s) => s.replace("if (col.unit === UNIT_RATIO && d === null) {", "if (false) {")],
  ['core', 'D5 the special-eval row gets painted',
    (s) => s.replace("const suppressed = strOrEmpty(bucket) === 'special_eval';", 'const suppressed = false;')],
  ['core', 'E7 an undeclared column is dropped instead of flagged',
    (s) => s.replace('      const hit = declared.get(key);\n      if (hit) return { ...hit, declared: true };', '      const hit = declared.get(key);\n      return { ...(hit || {}), declared: true };')],
  ['view', 'A2 the cell state stops reaching the DOM',
    (s) => s.replace("attrs(td, { 'data-col': column.key, 'data-cell-state': reading.state });", "attrs(td, { 'data-col': column.key, 'data-cell-state': 'measured' });")],
  ['view', 'G4 painted cells stop being painted',
    (s) => s.replace("if (reading.level !== null) td.setAttribute('data-heat', String(reading.level));", 'if (false) td.setAttribute("data-heat", "0");')],
  ['view', 'B2 the fraction loses its denominator attribute',
    (s) => s.replace("'data-denominator': reading.d === null ? null : String(reading.d),", "'data-denominator': null,")],
  ['view', 'D1 the special-eval row is filtered out of the table',
    (s) => s.replace('for (const row of model.rows) body.appendChild(renderRow(doc, row, model));', 'for (const row of model.rows) { if (row.special) continue; body.appendChild(renderRow(doc, row, model)); }')],
  ['mapcore', 'S7 the unreachable axis stops being flagged',
    (s) => s.replace("if (state === 'unreachable') {", 'if (false) {')],
  ['mapview', 'S6 a refused axis gets a canvas anyway',
    (s) => s.replace('    if (panel.detail) box.appendChild(el(doc, \'p\', \'sx-map__detail\', panel.detail));\n    // 🔴 AND NOTHING IS DRAWN. No canvas, no placeholder grid, no circle.\n    return box;', "    if (panel.detail) box.appendChild(el(doc, 'p', 'sx-map__detail', panel.detail));")],
  ['mapview', 'S8 the slot strip disappears',
    (s) => s.replace('if (lot.slots && lot.slots.length) {', 'if (false) {')],
];

// 🔴 THE CONTROLS ARE THE OTHER HALF OF S5. The first one gives the LEGEND the
// rows' own attribute. If any row assertion were reading the tree instead of the
// table body, this would change an outcome — it must ESCAPE for the scoping to
// mean anything.
const CONTROLS = [
  // 🔴 THE ONE THAT MATTERS. G1 is an assertion ABOUT the legend and is expected
  // to move; every ROW assertion (A*, B*, C1-C2, D*, G4) must NOT — that, and
  // only that, is what proves the row assertions are measuring rows.
  ['view', "the legend speaks the rows' attribute (must not move any ROW assertion)",
    (s) => s.replace("item.setAttribute('data-heat-key', String(i));", "item.setAttribute('data-heat', String(i));\n    item.setAttribute('data-heat-key', String(i));"),
    ['G1']],
  ['core', 'a private helper is renamed', (s) => s.replace(/\bstrOrEmpty\b/g, 'asText'), []],
];


function mutate(target, fn, sources) {
  const key = { core: 0, view: 1, mapcore: 2, mapview: 3 }[target];
  const out = sources.slice();
  const before = out[key];
  out[key] = fn(before);
  if (out[key] === before) return null;
  return out;
}

const PRISTINE = [CORE_SRC, VIEW_SRC, MAPCORE_SRC, MAPVIEW_SRC];

const base = await suite(...PRISTINE);

let caught = 0;
const escaped = [];
for (const [target, name, fn] of DEFECTS) {
  const mutated = mutate(target, fn, PRISTINE);
  if (!mutated) die(`mutant anchor no longer matches: ${name}`);
  let red = false;
  try {
    const r = await suite(...mutated);
    red = r.fail > 0;
  } catch (err) {
    red = true;
  }
  if (red) caught += 1; else escaped.push(name);
}

// 🔴 A CONTROL IS SCORED AS A DELTA, NOT AS AN ABSOLUTE. Judging it by
// `fail > 0` would make every control red the moment the base suite has one
// failure, which reports the base's own bug as an escape and teaches nothing.
// What a control asserts is that the mutation moved NOTHING it was not allowed
// to move.
const baseFailed = new Set(base.failed);
let controlsCaught = 0;
for (const [target, name, fn, allowed] of CONTROLS) {
  const mutated = mutate(target, fn, PRISTINE);
  if (!mutated) die(`control anchor no longer matches: ${name}`);
  try {
    const r = await suite(...mutated);
    const moved = r.failed.filter((f) => !baseFailed.has(f)
      && !(allowed || []).some((a) => f.startsWith(a)));
    if (moved.length) {
      controlsCaught += 1;
      console.error(`  ! control moved a row assertion: ${name} — ${moved.join('; ')}`);
    }
  } catch (err) {
    controlsCaught += 1;
    console.error(`  ! control threw: ${name} — ${err.message}`);
  }
}

console.log('\n── verdict ──────────────────────────────────────────────');
for (const f of base.failed) console.log(`  ✗ ${f}`);
for (const e of escaped) console.log(`  ✗ ESCAPED: ${e}`);
console.log(`\n${base.pass} passed, ${base.fail} failed; `
  + `${caught}/${DEFECTS.length} defects caught, ${escaped.length} escaped; `
  + `${CONTROLS.length - controlsCaught}/${CONTROLS.length} controls escaped.`);
const ran = base.pass + base.fail + DEFECTS.length + CONTROLS.length;
const failedTotal = base.fail + escaped.length + controlsCaught;
console.log(`ASSERTIONS ${ran} ${failedTotal}`);
process.exit(failedTotal ? 1 : 0);
