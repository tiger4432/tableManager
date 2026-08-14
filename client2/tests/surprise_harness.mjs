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
  row_axis: { name: 'bond_lot', label: '본딩 랏', about: 'process',
              relation: 'bonding_log', column: 'bond_lot',
              source: 'bonding_log.bond_lot' },
  axes_available: [{ name: 'bond_lot', label: '본딩 랏', about: 'process' }],
  aggregates_available: [
    { aggregate: 'found_rate', label: '발생 칩비', value_kind: 'ratio', needs_denominator: true },
    { aggregate: 'extent_mean', label: '평균 크기', value_kind: 'mean', needs_denominator: true },
    { aggregate: 'event_count', label: '관측 건수', value_kind: 'count', needs_denominator: false },
  ],
  columns: [
    {
      id: 'zzq:found_rate', kind: 'zzq', kind_label: '지큐',
      aggregate: 'found_rate', aggregate_label: '발생 칩비',
      value_kind: 'ratio', doc: '발견 칩 / 검사 칩', has_denominator: true,
      denominator: { population: 'scanned_chips', label: '검사 칩', methods: ['AOI'] },
      baseline: { value: 0.065, basis: 'median_of_rows', n_rows: 4,
                  excluded_rows: 0, excluded_reason: null },
      thresholds: [{ level: 1, at: 2.0, label: '주의' }, { level: 2, at: 3.0, label: '높음' },
                   { level: 3, at: 4.5, label: '심각' }, { level: 4, at: 6.0, label: '극단' }],
      state: 'ready', reason: null,
    },
    {
      id: 'zzq:extent_mean', kind: 'zzq', kind_label: '지큐',
      aggregate: 'extent_mean', aggregate_label: '평균 크기',
      value_kind: 'mean', doc: '', has_denominator: true,
      denominator: { population: 'found_chips', label: '발견 칩', methods: ['AOI'] },
      baseline: { value: 1500, basis: 'median_of_rows', n_rows: 3,
                  excluded_rows: 0, excluded_reason: null },
      thresholds: [{ level: 1, at: 2.0, label: '주의' }, { level: 2, at: 3.0, label: '높음' },
                   { level: 3, at: 4.5, label: '심각' }, { level: 4, at: 6.0, label: '극단' }],
      state: 'ready', reason: null,
    },
    {
      // 🔴 THE COLUMN THAT IS NEVER PAINTED — R-2026-08-14-G. Every cell is
      // measured and none reaches the first step, which is exactly the shape that
      // reads as 「정상」 if the screen stays silent.
      id: 'wob:found_rate', kind: 'wob', kind_label: '워브',
      aggregate: 'found_rate', aggregate_label: '발생 칩비',
      value_kind: 'ratio', doc: '', has_denominator: true,
      denominator: { population: 'scanned_chips', label: '검사 칩', methods: ['AOI'] },
      baseline: { value: 0.6124, basis: 'median_of_rows', n_rows: 4,
                  excluded_rows: 0, excluded_reason: null },
      thresholds: [{ level: 1, at: 2.0, label: '주의' }, { level: 2, at: 3.0, label: '높음' },
                   { level: 3, at: 4.5, label: '심각' }, { level: 4, at: 6.0, label: '극단' }],
      state: 'ready', reason: null,
    },
  ],
  rows: [
    {
      row: 'R-1', label: 'CL-2601-002', order_index: 2,
      occurred_at: { first: '2026-05-03T02:17:00+09:00', last: '2026-05-03T09:00:00+09:00' },
      bucket: { id: 'unknown', label: '미상', counts_toward_baseline: true },
      universe: 3525,
      cells: [
        // 🔴 A MEASURED ZERO. 725 chips inspected, none had the finding.
        { column: 'zzq:found_rate', state: 'measured', value: 0, n: 0, of: 725,
          ratio_to_baseline: 0, level: 0 },
        { column: 'zzq:extent_mean', state: 'unscanned', value: null, n: null, of: 0 },
        { column: 'wob:found_rate', state: 'measured', value: 0.61, n: 442, of: 725,
          ratio_to_baseline: 0.996, level: 0 },
      ],
    },
    {
      row: 'R-2', label: 'CL-2601-006', order_index: 6,
      occurred_at: { first: '2026-05-06T02:00:00+09:00', last: '2026-05-06T11:00:00+09:00' },
      bucket: { id: 'unknown', label: '미상', counts_toward_baseline: true },
      universe: 3525,
      cells: [
        { column: 'zzq:found_rate', state: 'measured', value: 0.416, n: 302, of: 725,
          ratio_to_baseline: 6.4, level: 4 },
        { column: 'zzq:extent_mean', state: 'measured', value: 5210, n: 302, of: 302,
          ratio_to_baseline: 3.47, level: 2 },
        { column: 'wob:found_rate', state: 'measured', value: 0.648, n: 470, of: 725,
          ratio_to_baseline: 1.059, level: 0 },
      ],
    },
    {
      // 🔴 OUT OF THE BASELINE BY THE SERVER'S OWN DECLARATION — shown, badged,
      // and NOT painted even though it carries a level.
      row: 'R-3', label: 'CL-2601-QE2', order_index: 7,
      occurred_at: { first: '2026-05-07T02:00:00+09:00', last: null },
      bucket: { id: 'special_eval', label: '특수평가', counts_toward_baseline: false },
      universe: 1200,
      cells: [
        { column: 'zzq:found_rate', state: 'measured', value: 0.34, n: 82, of: 240,
          ratio_to_baseline: 5.2, level: 3 },
        { column: 'zzq:extent_mean', state: 'measured', value: 4880, n: 82, of: 82,
          ratio_to_baseline: 3.25, level: 2 },
        { column: 'wob:found_rate', state: 'measured', value: 0.59, n: 141, of: 240,
          ratio_to_baseline: 0.963, level: 0 },
      ],
    },
    {
      // 🔴 THE ROW THAT DISCRIMINATES TWO MORE DEFECTS: an ABSENT cell, and a
      // measured rate whose denominator never arrived.
      row: 'R-4', label: 'CL-2601-021', order_index: 9,
      occurred_at: { first: null, last: null },
      bucket: { id: 'unknown', label: '미상', counts_toward_baseline: true },
      universe: null,
      cells: [
        { column: 'zzq:found_rate', state: 'measured', value: 0.08, n: 12, of: null,
          ratio_to_baseline: 1.2, level: 0 },
        // 'zzq:extent_mean' is ABSENT — 답의 구멍, 미검사가 아니다.
        { column: 'wob:found_rate', state: 'unmeasurable', value: null, n: null, of: null },
      ],
    },
  ],
  populations: { rows_total: 12, rows_returned: 4, rows_truncated: true },
  window: { requested: '전 기간', applied: '30d', forced: true,
            forced_reason: 'grid_too_large' },
  notes: [{ code: 'relation_absent', message: 'delam_obs 미배포' }],
  provenance: { source: 'source_tables', ledger_backed: false,
                relations: ['void_obs', 'bonding_log'], absent_relations: ['delam_obs'],
                note: '이 경로가 아직 원장을 읽지 않는다.' },
};

const KINDS = { state: 'ready', kinds: [{ kind: 'zzq', label: '지큐', atoms: 900 }, { kind: 'vrn', label: '브른', atoms: 11 }] };

// 🔴 FIXTURE-SHAPE GUARDS. A fixture that stopped discriminating would make this
// whole file pass vacuously, so the properties the assertions depend on are
// checked before anything is compared.
{
  const cell = (r, c) => FIX.rows[r].cells.find((x) => x.column === c);
  if (cell(0, 'zzq:found_rate').value !== 0) die('fixture lost its MEASURED ZERO — S1 cannot be scored');
  if (cell(0, 'zzq:extent_mean').state !== 'unscanned') die('fixture lost its UNSCANNED cell — S1 cannot be scored');
  if (FIX.rows[2].bucket.counts_toward_baseline !== false) die('fixture lost its off-baseline row');
  if (!(cell(2, 'zzq:found_rate').level > 0)) die('off-baseline row carries no level — suppression is untestable');
  if (cell(1, 'zzq:found_rate').of === FIX.rows[1].universe) die('fixture denominator collapsed into the row universe');
  if (cell(3, 'zzq:extent_mean')) die('fixture lost its ABSENT cell — 미보고 vs 미검사 is untestable');
  if (cell(3, 'zzq:found_rate').of !== null) die('fixture lost its denominator-less rate — S2 is untestable');
  // R-2026-08-14-G: the column every cell of which is measured and none painted.
  const wob = FIX.rows.map((r) => r.cells.find((x) => x.column === 'wob:found_rate'));
  if (!wob.slice(0, 3).every((c) => c.state === 'measured' && c.level === 0)) {
    die('fixture lost its NEVER-PAINTED column — fake attenuation is untestable');
  }
  if (/zzq|wob/.test(CORE_SRC) || /zzq|wob/.test(VIEW_SRC)) die('the fixture metric names appear in the source — S4 is vacuous');
  if (/1\.554/.test(CORE_SRC + VIEW_SRC + PAGE_SRC)) die('the retracted 1.554 figure is in the shipped source');
}

const AXIS_FIX = {
  row: 'R-2', slot: '3', kind: 'zzq',
  row_axis: { name: 'bond_lot', label: '본딩 랏', source: 'bonding_log.bond_lot' },
  projections: [
    {
      axis: 'bond', label: '본딩축', sublabel: '스테이지 좌표',
      state: 'ready', reason: null, message: null,
      coordinate_unit: 'cells_from_origin',
      frame: {
        state: 'ready', table: 'bonding_log', map_id: 'CL-2601-006_3',
        grid: { grid_cols: 5, grid_rows: 5, grid_start_x: 1, grid_start_y: 1,
                rotation: 0, side: 'front' },
        valid_die_ref: { relation: 'valid_die_ref', present: true },
      },
      cells: [{ x: 2, y: 2, n: 3 }, { x: 3, y: 2, n: 1 }],
      found: 4, scanned: 25,
    },
    {
      // 🔴 THE ROW SPANS SEVERAL FRAMES — and the SLOT LIST is the server's answer.
      axis: 'dt', label: 'DT축', sublabel: '테이프 좌표',
      state: 'no_frame', reason: 'frame_ambiguous_across_slots',
      message: '이 행이 프레임 여러 개에 걸쳐 있다 — 슬롯마다 격자 치수가 다르다.',
      coordinate_unit: 'cells_from_origin',
      frame: { state: 'no_frame', reason: 'frame_ambiguous_across_slots',
               available_slots: ['1', '3', '7'], available_lots: ['CL-2601-006'] },
      cells: [{ x: 1, y: 4, n: 2 }], found: 2, scanned: 25,
    },
    // 🔴 MEASURED UNREACHABLE — 357,796 rows of NULL bridge columns.
    {
      axis: 'core', label: '코어축', sublabel: '웨이퍼 좌표',
      state: 'unreachable', reason: 'no_live_bridge',
      message: 'bonding_log.cx가 이 행에서 전부 NULL — 좌표가 기록되지 않았다.',
      frame: null, cells: [], found: 0, scanned: 0,
    },
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
    'view=surprise&columns=zzq:found_rate,zzq:extent_mean,wob:found_rate&mark=R-2'));
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
    const zero = first(byAttr(r0, 'data-col', 'zzq:found_rate'));
    const unscanned = first(byAttr(r0, 'data-col', 'zzq:extent_mean'));

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
    const absent = first(byAttr(r3, 'data-col', 'zzq:extent_mean'));
    eq('A11 a cell the response omitted reads as 미보고', absent.getAttribute('data-cell-state'), 'unreported');
    ok('A12 and NOT as 미검사', absent.getAttribute('data-cell-state')
      !== first(byAttr(r0, 'data-col', 'zzq:extent_mean')).getAttribute('data-cell-state'));
    ok('A13 the two nothings read differently on screen',
      absent.textContent.includes('미보고') && !absent.textContent.includes('미검사'), absent.textContent);

    const unmeasurable = first(byAttr(r3, 'data-col', 'wob:found_rate'));
    eq('A9 unmeasurable is its own state', unmeasurable.getAttribute('data-cell-state'), 'unmeasurable');
    ok('A10 and it reads as neither zero nor 미검사',
      unmeasurable.textContent.includes('측정 불가') && !unmeasurable.textContent.includes('미검사'),
      unmeasurable.textContent);
  }

  // ── B. 분모 ──────────────────────────────────────────────────────────────────
  console.log('\n── B. 분모 없는 숫자 출고 금지 ────────────────────────────');
  {
    const r1 = first(byAttr(tbody, 'data-lot', 'CL-2601-006'));
    const rate = first(byAttr(r1, 'data-col', 'zzq:found_rate'));
    const frac = first(byClass(rate, 'sx-cell__f'));
    // 🔴 725, NOT 3525. The denominator is the INSPECTED chip count; a client that
    // took the row's universe would be wrong by ~5×.
    eq('B1 the denominator is the inspected chip count, off the wire',
      frac.getAttribute('data-denominator'), '725');
    eq('B2 and it is NOT the row universe', frac.getAttribute('data-denominator') === '3525', false);
    ok('B3 the fraction is on screen beside the percentage',
      rate.textContent.includes('302/725'), rate.textContent);
    const chips = first(byClass(r1, 'sx-row__chips'));
    ok('B4 the row universe is labelled as its own thing, not as the denominator',
      chips.textContent.includes('3,525'), chips.textContent);

    const nod = first(byAttr(tbody, 'data-lot', 'CL-2601-021'));
    const bare = first(byAttr(nod, 'data-col', 'zzq:found_rate'));
    eq('B5 a measured rate with no denominator refuses', bare.getAttribute('data-cell-state'), 'no_denominator');
    ok('B6 and the count still shows, because the count is real',
      bare.textContent.includes('12건'), bare.textContent);
    ok('B7 naming which denominator is missing',
      bare.textContent.includes('검사 칩'), bare.textContent);
    ok('B8 no percentage is printed without a denominator', !bare.textContent.includes('%'), bare.textContent);

    eq('B9 an unreported row universe is not 0',
      first(byClass(nod, 'sx-row__chips--none')).getAttribute('data-chips'), 'none');
  }

  // ── C. level은 서버가 낸다 ────────────────────────────────────────────────────
  console.log('\n── C. 조건부서식 단계는 서버의 것 ─────────────────────────');
  {
    const r1 = first(byAttr(tbody, 'data-lot', 'CL-2601-006'));
    eq('C1 the served level reaches the cell verbatim',
      first(byAttr(r1, 'data-col', 'zzq:found_rate')).getAttribute('data-heat'), '4');
    eq('C2 and a different column keeps ITS level',
      first(byAttr(r1, 'data-col', 'zzq:extent_mean')).getAttribute('data-heat'), '2');
    // 🔴 NO THRESHOLD FUNCTION EXISTS IN THE SOURCE. S3, scored as text because
    // the defect is a second implementation existing at all.
    const bare = stripComments(coreSrc);
    ok('C3 the core carries no client-side threshold ladder',
      !/l\s*>=\s*bands\[/.test(bare) && !/function heatLevel/.test(bare), 'a level ladder is back in the core');
    ok('C4 the legend says who assigned the step',
      legend.textContent.includes('단계 판정'), legend.textContent.slice(0, 200));
    ok('C5 the legend ladder is the wire\'s, labels included',
      legend.textContent.includes('주의') && legend.textContent.includes('2배 이상'));
  }

  // ── D. 특수평가: 뱃지만, 칠하지 않고, 숨기지 않고 ─────────────────────────────
  console.log('\n── D. 특수평가 행 ────────────────────────────────────────');
  {
    const rows = byClass(tbody, 'sx-row');
    eq('D1 every row is in the table, off-baseline included', rows.length, 4);
    const qe = first(byAttr(tbody, 'data-lot', 'CL-2601-QE2'));
    ok('D2 it is not hidden', qe !== NOTHING);
    eq('D3 it is badged', first(byClass(qe, 'sx-bucket')).getAttribute('data-bucket-badge'), 'special_eval');
    ok('D4 the badge says so in words', qe.textContent.includes('특수평가'), qe.textContent.slice(0, 120));
    // 🔴 THE SUPPRESSION RULE IS THE SERVER'S DECLARATION, not a bucket-name match.
    eq('D3b the row carries the server\'s baseline membership',
      qe.getAttribute('data-counts-baseline'), '0');
    const cell = first(byAttr(qe, 'data-col', 'zzq:found_rate'));
    eq('D5 and its cell is NOT painted despite a served level', cell.getAttribute('data-heat'), null);
    eq('D6 the suppression is stated, not silent', cell.getAttribute('data-heat-suppressed'), 'special_eval');
    ok('D7 the value is still printed', cell.textContent.includes('34.0%'), cell.textContent);
    ok('D8 the legend explains the rule', legend.textContent.includes('칠하지 않습니다'), '');
    ok('D9 and names the declared discriminator rather than a guessed one',
      legend.textContent.includes('counts_toward_baseline'), '');
  }

  // ── E. 지표 목록은 선언에서 나온다 ────────────────────────────────────────────
  console.log('\n── E. 하드코딩된 지표 목록 없음 ───────────────────────────');
  {
    const cols = first(byClass(mount, 'sx-cols'));
    ok('E1 the declared metric reaches the column bar',
      byAttr(cols, 'data-col', 'zzq:found_rate').length > 0);
    ok('E2 a SECOND declared metric does too',
      byAttr(cols, 'data-col', 'wob:found_rate').length > 0);
    // The 「열 추가」 menu is the cross product of registered kinds with declared
    // aggregates — both off the wire, neither listed in the source.
    ok('E3 a declared aggregate that is not up is offered for adding',
      byAttr(cols, 'data-col-add', 'wob:event_count').length > 0);
    // 🔴 THE REAL TEST OF S4: a metric name invented HERE, right now, reaches the
    // screen without a line changing in the source.
    const invented = core.surpriseModel({
      body: {
        ...FIX,
        columns: FIX.columns.concat([{
          id: 'qqx:zz', kind: 'qqx', kind_label: '큐엑스',
          aggregate: 'zz', aggregate_label: '집계', value_kind: 'count',
          has_denominator: false, baseline: { value: null }, thresholds: [], state: 'ready',
        }]),
      },
      kinds: KINDS,
      question: core.parseSurpriseQuery(new URLSearchParams('view=surprise')),
    });
    const d2 = makeDoc('light');
    const m2 = d2.createElement('div');
    view.renderSurprise(d2, m2, invented, null, null);
    ok('E4 a metric declared one second ago is a column',
      byAttr(first(byClass(m2, 'sx-table')), 'data-col', 'qqx:zz').length > 0);
    ok('E5 and its label came from the declaration',
      first(byClass(m2, 'sx-table')).textContent.includes('큐엑스'));
    // An item the kind catalog knows and the metric declaration does not.
    ok('E6 a declared-but-unaggregated item is shown, not dropped',
      byAttr(cols, 'data-item', 'vrn').length > 0);
    // 🔴 THE ROW AXIS NAMES ITSELF TOO — it is switchable (`by=`), so a hardcoded
    // 「랏」 would mislabel the column the moment somebody asks a different axis.
    ok('E7 the row axis label comes off the wire',
      first(byClass(mount, 'sx-table')).textContent.includes('본딩 랏'));
    ok('E8 and the header stat uses it as well',
      first(byAttr(mount, 'data-stat', 'rows')).textContent.includes('본딩 랏'));
  }

  // ── F. URL은 질문이다 ────────────────────────────────────────────────────────
  console.log('\n── F. 열 구성 · 마킹 · 슬롯이 URL에 실린다 ─────────────────');
  {
    const q = core.parseSurpriseQuery(new URLSearchParams(
      'view=surprise&columns=zzq:found_rate,wob:found_rate&mark=A,B&slot=3&by=bond_lot&window=7d'));
    eq('F1 columns parse out of the URL', q.cols.length, 2);
    eq('F2 marks parse out of the URL', q.marked.join('|'), 'A|B');
    eq('F3 the slot parses out of the URL', q.slot, '3');
    const back = core.surpriseQuery(q);
    ok('F4 and the question round-trips', back.includes('columns=') && back.includes('mark=') && back.includes('slot=3'), back);
    // 🔴 THE REQUEST IS NOT THE ADDRESS BAR. `mark` and `slot` are the client's own.
    const req = core.lotsQuery(q);
    ok('F4b the request carries the server\'s parameters only',
      req.includes('columns=') && req.includes('by=bond_lot') && req.includes('window=7d')
      && !req.includes('mark=') && !req.includes('slot='), req);
    const dropped = core.surpriseQuery(core.withoutColumn(q, { kind: 'zzq', aggregate: 'found_rate' }));
    ok('F5 dropping a column is a URL, not a mode', dropped.includes('wob%3Afound_rate') && !dropped.includes('zzq%3Afound_rate'), dropped);
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
    eq('H4 on the REGISTERED frame', bond.getAttribute('data-axis-code'), 'mask_absent');
    eq('H5 with its defect chips seated', first(byTag(bond, 'CANVAS')).getAttribute('data-mark-cells'), '2');
    ok('H6 and it names the registered frame it drew on',
      bond.textContent.includes('CL-2601-006_3'), bond.textContent);
    ok('H7 and states the coordinate unit', bond.textContent.includes('오리진 기준 칸수'), bond.textContent);
    // 🔴 THE MASK IS ANNOUNCED-ONLY ON THE WIRE, SO ITS ABSENCE IS STATED.
    ok('H7b the missing valid-die mask is named, not implied',
      bond.textContent.includes('유효 다이 마스크 미적용'), bond.textContent);
    ok('H7c and the panel does not claim 0 good dies',
      !bond.textContent.includes('유효 다이 0'), bond.textContent);
    ok('H7d the projection\'s own denominator is on screen',
      first(byAttr(bond, 'data-map-stat', 'scanned')).textContent.includes('25'));

    // 🔴 S7 — the core axis is UNREACHABLE and it says so IN ITS OWN PLACE.
    const coreAxis = first(byAttr(row, 'data-axis', 'core'));
    ok('H8 the core axis is present, not hidden', coreAxis !== NOTHING);
    eq('H9 it is flagged unreachable, distinctly from a failure', coreAxis.getAttribute('data-unreachable'), '1');
    ok('H10 and says 연결 없음 in words', coreAxis.textContent.includes('연결 없음'), coreAxis.textContent);
    ok('H11 naming absence rather than zero', coreAxis.textContent.includes('0이 아니라 부재'), coreAxis.textContent);
    // 🔴 S6 — NOTHING IS DRAWN THAT WAS NOT SOURCED.
    eq('H12 a refused axis has NO canvas at all', byTag(coreAxis, 'CANVAS').length, 0);
    const dt = first(byAttr(row, 'data-axis', 'dt'));
    eq('H13 an axis with an ambiguous frame draws nothing', byTag(dt, 'CANVAS').length, 0);
    ok('H14 and says which leg was missing',
      dt.textContent.includes('프레임 여러 개'), dt.textContent);
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
    // 🔴 READ, NOT ASSEMBLED. The list is the server's answer to
    // `frame_ambiguous_across_slots`, so the client does not build it twice.
    eq('I2 listing the slots the SERVER says exist', strip.getAttribute('data-slot-count'), '3');
    eq('I3 the served slot is marked current', first(byAttr(strip, 'aria-current', 'true')).getAttribute('data-slot'), '3');
    ok('I4 each slot is an anchor carrying the whole question',
      first(byAttr(strip, 'data-slot', '7')).getAttribute('href').includes('slot=7'));
    eq('I5 the note is attributed to the refusal it came from',
      first(byClass(strip, 'sx-slots__note')).getAttribute('data-slot-note'),
      'frame_ambiguous_across_slots');
    ok('I6 and it is the server\'s sentence, not a paraphrase',
      strip.textContent.includes('격자 치수가 다르다'), strip.textContent);
    const cached = mapCore.mapSection(model, { 'R-2|': AXIS_FIX }, {});
    eq('I7 the map is keyed on the row id the route takes', cached.lots[0].row, 'R-2');
  }

  // ── J. 차트 ──────────────────────────────────────────────────────────────────
  console.log('\n── J. 소형 다중 차트 ─────────────────────────────────────');
  {
    const charts = first(byClass(mount, 'sx-charts'));
    eq('J1 one chart per column', byClass(charts, 'sx-chart').length, model.columns.length);
    const c0 = first(byAttr(charts, 'data-chart', 'zzq:found_rate'));
    ok('J2 the chart states its own denominator', c0.textContent.includes('/4 랏 표시'), c0.textContent);
    // Special-eval lots are not in the line but are on the axis.
    ok('J3 the special lot is marked apart from the line',
      byAttr(c0, 'data-special-lot', 'CL-2601-QE2').length === 1);
    ok('J4 the marked lot has an emphasised dot',
      first(byAttr(c0, 'data-dot-lot', 'CL-2601-006')).getAttribute('data-dot-marked') === '1');
    const c1 = first(byAttr(charts, 'data-chart', 'zzq:extent_mean'));
    ok('J5 unscanned rows are counted as gaps, not plotted as zero',
      c1.getAttribute('data-chart-gaps') !== null || c1.textContent.includes('미측정'), c1.textContent);
    // 🔴 THE WIRE CARRIES NO LEDGER EVENTS TODAY, so no marker is drawn and none
    // is claimed. A chart that invented a marker would be the whole defect.
    eq('J6 no event marker is drawn when none was served', hasAttr(charts, 'data-event').length, 0);
  }

  // ── N. 채점 불가가 화면에 보인다 (R-2026-08-14-G) ────────────────────────────
  console.log('\n── N. 가짜 감쇄 방지 ─────────────────────────────────────');
  {
    // 🔴 A COLUMN THAT IS NEVER PAINTED READS AS 「정상」. The fixture's third
    // column is measured in every row and painted in none — exactly the shape the
    // ruling names, and exactly what `found_rate` does on the live box (saturates
    // at 1.0, baseline 0.6124, so the ceiling is 1.633 and the first step is 2.0).
    const head = first(byAttr(first(byClass(mount, 'sx-table')), 'data-col', 'wob:found_rate'));
    const flag = first(byClass(head, 'sx-th__flag'));
    ok('N1 an entirely unpainted column says so in its header', flag !== NOTHING);
    eq('N2 naming how many cells were measured', flag.getAttribute('data-col-unpainted'), '3');
    ok('N3 with the largest multiple and the first threshold, so silence is legible',
      flag.textContent.includes('첫 문턱 2배') && flag.textContent.includes('최대'), flag.textContent);
    // 🔴 IT MUST NOT CLAIM THE METRIC CANNOT BE GRADED. That is the SERVER'S
    // declaration about the metric's mathematics; this is a fact about this answer.
    ok('N4 and it does NOT claim 채점 불가 — that is the server\'s to declare',
      !flag.textContent.includes('채점 불가'), flag.textContent);
    // A painted column carries no such flag — otherwise the marker is noise.
    const painted = first(byAttr(first(byClass(mount, 'sx-table')), 'data-col', 'zzq:found_rate'));
    eq('N5 a column that did paint carries no flag', byClass(painted, 'sx-th__flag').length, 0);
    // 🔴 THE SERVER'S DECLARATION, WHEN IT SHIPS, RENDERS AHEAD OF THE OBSERVATION.
    const declaredModel = core.surpriseModel({
      body: {
        ...FIX,
        columns: FIX.columns.map((c) => (c.id === 'wob:found_rate'
          ? { ...c, state: 'ungradable', reason: '천장 1.633 < 첫 문턱 2.0' } : c)),
      },
      kinds: KINDS, question: model.question,
    });
    const d3 = makeDoc('light');
    const m3 = d3.createElement('div');
    view.renderSurprise(d3, m3, declaredModel, null, null);
    const declaredHead = first(byAttr(first(byClass(m3, 'sx-table')), 'data-col', 'wob:found_rate'));
    eq('N6 a column state the client has never heard of still renders',
      first(byClass(declaredHead, 'sx-th__flag')).getAttribute('data-col-state'), 'ungradable');
    ok('N7 as 채점 불가, with the server\'s reason verbatim',
      declaredHead.textContent.includes('채점 불가')
      && declaredHead.textContent.includes('천장 1.633'), declaredHead.textContent);
    ok('N8 and it replaces the observation rather than doubling it',
      byClass(declaredHead, 'sx-th__flag').length === 1);
  }

  // ── O. 응답의 성질을 숨기지 않는다 ───────────────────────────────────────────
  console.log('\n── O. 강제 구간 · 잘린 행 · 출처 ─────────────────────────');
  {
    const facts = first(byAttr(mount, 'data-panel', 'facts'));
    ok('O1 a forced window is stated', byAttr(facts, 'data-fact', 'window_forced').length === 1);
    ok('O2 a truncated row set is stated', byAttr(facts, 'data-fact', 'truncated').length === 1);
    ok('O3 with both sides of the fraction',
      first(byAttr(facts, 'data-fact', 'truncated')).textContent.includes('4/12'),
      first(byAttr(facts, 'data-fact', 'truncated')).textContent);
    ok('O4 provenance says these numbers are not ledger-backed',
      first(byAttr(facts, 'data-fact', 'provenance')).textContent.includes('원장 미기반'));
    ok('O5 a server note reaches the screen',
      byAttr(facts, 'data-fact', 'relation_absent').length === 1);
  }

  // ── K. 배선 ──────────────────────────────────────────────────────────────────
  console.log('\n── K. 배선 ──────────────────────────────────────────────');
  {
    ok('K1 the page carries the mount', /id="lt-surprise"/.test(PAGE_SRC));
    ok('K2 the view is a URL, not a mode', /view=surprise/.test(PAGE_SRC));
    ok('K3 the entry imports the renderer', /renderSurprise/.test(ENTRY_SRC));
    ok('K4 and asks the confirmed aggregate route', /api\/ledger\/lots/.test(ENTRY_SRC));
    ok('K4b sending the server\'s parameters, not the address bar',
      /lotsQuery\(question\)/.test(ENTRY_SRC));
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
    (s) => s.replace("state: 'unreported', value: null, n: null, of: null,", "state: 'unscanned', value: null, n: null, of: null,")],
  ['core', 'S3 the level is derived from the ratio instead of served',
    (s) => s.replace('const served = numOrNull(raw.level);', 'const served = numOrNull(raw.ratio_to_baseline);')],
  ['core', 'S2 a rate prints without its denominator',
    (s) => s.replace('if (col.hasDenominator && of === null) {', 'if (false) {')],
  ['core', 'D5 the off-baseline row gets painted',
    (s) => s.replace('const suppressed = counts === false;', 'const suppressed = false;')],
  ['core', 'E7 the row axis label is dropped',
    (s) => s.replace('label: strOrEmpty(body && body.row_axis && body.row_axis.label),', "label: '',")],
  ['core', 'N1 the unpainted-column fact is never computed',
    (s) => s.replace('neverPainted: measured > 0 && painted === 0,', 'neverPainted: false,')],
  ['core', 'O1 a forced window stops being reported',
    (s) => s.replace('forced: win.forced === true,', 'forced: false,')],
  ['view', 'A2 the cell state stops reaching the DOM',
    (s) => s.replace("attrs(td, { 'data-col': column.key, 'data-cell-state': reading.state });", "attrs(td, { 'data-col': column.key, 'data-cell-state': 'measured' });")],
  ['view', 'G4 painted cells stop being painted',
    (s) => s.replace("if (reading.level !== null) td.setAttribute('data-heat', String(reading.level));", 'if (false) td.setAttribute("data-heat", "0");')],
  ['view', 'B2 the fraction loses its denominator attribute',
    (s) => s.replace("'data-denominator': reading.of === null ? null : String(reading.of),", "'data-denominator': null,")],
  ['view', 'N1 the unpainted-column header flag disappears',
    (s) => s.replace('} else if (col.observed && col.observed.neverPainted) {', '} else if (false) {')],
  ['view', 'D1 the off-baseline row is filtered out of the table',
    (s) => s.replace('for (const row of model.rows) body.appendChild(renderRow(doc, row, model));', 'for (const row of model.rows) { if (row.special) continue; body.appendChild(renderRow(doc, row, model)); }')],
  ['mapcore', 'S7 the unreachable axis stops being flagged',
    (s) => s.replace("panel.unreachable = state === 'unreachable';", 'panel.unreachable = false;')],
  ['mapcore', 'H7b the absent valid-die mask stops being named',
    (s) => s.replace("code: floorSeating ? (cellSet.cells.length ? null : 'no_cells') : 'mask_absent',", 'code: null,')],
  ['mapview', 'S6 a refused axis gets a canvas anyway',
    (s) => s.replace('if (!panel.ok) {', 'if (false) {')],
  ['mapview', 'S8 the slot strip disappears',
    (s) => s.replace('if (lot.slots && lot.slots.length) {', 'if (false) {')],
  ['view', 'O2 truncation stops being reported',
    (s) => s.replace('if (model.truncated) {', 'if (false) {')],
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
    (s) => s.replace("item.setAttribute('data-heat-key', String(step.level));", "item.setAttribute('data-heat', String(step.level)); item.setAttribute('data-heat-key', String(step.level));"),
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
