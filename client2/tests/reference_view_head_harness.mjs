/**
 * 🏷️ C-60 — 참조뷰의 «첫째 표에도 제목». 대상을 IMPORT 해서 «렌더»합니다.
 *
 * 🔴 소유자가 본 것: 참조뷰 패널이 하나면 탭 줄이 `display:none` 이라 첫째 표의 이름이
 *    «아무 데도» 없었습니다. 근거(evidence) 표는 처음부터 띠를 갖고 있었고, 첫째만
 *    못 가진 것이었습니다 — 「없는 기능」이 아니라 「한쪽에만 있던 기능」입니다.
 *
 * 🔴 그리고 이 화면의 기존 하니스는 «잘라쓰기»이고 그 사유가 낡았습니다: 「`config.js` 가
 *    모듈 최상단에서 `window` 를 만져 import 가 안 된다」 — 오늘 이 파일은 node 가
 *    «import 합니다»(이 하니스가 그 증거입니다). 그래서 여기서는 자르지 않습니다.
 *
 * 🟦 C-103 이 갈래를 하나로 만들었고(뷰 N → 탭 N), C-108 이 그 탭을 «쓸 수 있게» 합니다 —
 * 탭이 자기 행 수를 달고, 표마다 마지막 탭을 기억하고, ←→ 로 넘어갑니다([6] 절).
 *
 * Run: node client2/tests/reference_view_head_harness.mjs
 */
let ran = 0;
let failed = 0;
const ok = (name, cond, detail = '') => {
  ran += 1;
  if (cond) console.log(`  PASS ${name}`);
  else { failed += 1; console.log(`  FAIL ${name}${detail ? ' — ' + detail : ''}`); }
};
const eq = (name, expected, actual) => ok(name, actual === expected,
  `expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);

function element(tag) {
  const node = {
    tagName: String(tag).toUpperCase(), children: [], attrs: Object.create(null),
    _text: '', _classes: [], dataset: Object.create(null), style: {}, type: '',
    get className() { return this._classes.join(' '); },
    set className(v) { this._classes = String(v).split(/\s+/).filter(Boolean); },
    classList: {
      add(...n) { for (const x of n) if (!node._classes.includes(x)) node._classes.push(x); },
      remove(...n) { node._classes = node._classes.filter((c) => !n.includes(c)); },
      contains(n) { return node._classes.includes(n); },
      toggle(n, on) { if (on) node.classList.add(n); else node.classList.remove(n); },
    },
    append(...i) { for (const x of i) if (x) this.children.push(x); },
    appendChild(c) { this.children.push(c); return c; },
    replaceChildren(...i) { this.children = i.filter(Boolean); },
    insertBefore(node2, ref) {
      const at = ref ? this.children.indexOf(ref) : -1;
      if (at < 0) this.children.push(node2); else this.children.splice(at, 0, node2);
      return node2;
    },
    get firstChild() { return this.children[0] || null; },
    setAttribute(k, v) { this.attrs[String(k)] = String(v); },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, String(k)) ? this.attrs[String(k)] : null; },
    querySelector() { return null; }, querySelectorAll() { return []; },
    // 🔴 C-108. 초점을 «옮깁니다». 스텁에 없는 철자를 대상이 읽으면 그 줄은 조용히 «안
    //    재집니다» — 그리고 ←→ 의 절반이 「다음 화살표가 이어지나」입니다.
    focus() { globalThis.document.activeElement = this; },
    // «띄우기»도 브라우저가 하는 일입니다 — 기록해 두면 「고른 탭이 보이나」를 재지만,
    // 없으면 그 줄이 «던집니다».
    scrollIntoView(opts) { node.scrolledIntoView = (node.scrolledIntoView || 0) + 1; node.scrollOpts = opts; },
    // 🔴 C-103. 듣고, «발화»합니다. 기록만 하고 못 쏘는 스텁은 「무엇이 배선됐나」를 재고,
    //    「탭을 누르면 그 표가 뜬다」는 «무슨 일이 일어나나»입니다 — 다른 물음입니다.
    listeners: Object.create(null),
    addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); },
    dispatch(type, event = {}) {
      for (const fn of this.listeners[String(type)] || []) fn({ type, target: this, ...event });
    },
    closest() { return null; },
    set textContent(v) { this._text = String(v); this.children = []; },
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); },
  };
  return node;
}
const host = element('div');
// 🔴 EVERY id GETS A NODE, and the same node twice. `elements.*` is a GETTER over
//    `getElementById`, so the host is handed over the way the browser hands it over --
//    but `activateReferenceTab` also reaches for the timeline containers and tab buttons,
//    and a `null` there throws BEFORE the request is built (measured: C-73 section died on
//    `elements.timelineContainer.style`). Nothing in the subject is patched.
const byId = new Map([['reference-view-content', host]]);
globalThis.document = { createElement: element, createDocumentFragment: () => element('#f'),
  getElementById: (id) => {
    if (!byId.has(id)) byId.set(id, element('div'));
    return byId.get(id);
  },
  addEventListener() {}, querySelector: () => null, activeElement: null };
// 🔴 C-108 ②. 브라우저의 저장소를 «흉내»가 아니라 «같은 계약»으로 둡니다: 없는 키는 `null`.
//    (`undefined` 로 두면 대상의 `|| ''` 가 두 경우를 같게 만들어 「기억이 없다」를 못 잽니다.)
const memory = new Map();
globalThis.localStorage = {
  getItem: (k) => (memory.has(String(k)) ? memory.get(String(k)) : null),
  setItem: (k, v) => { memory.set(String(k), String(v)); },
  removeItem: (k) => { memory.delete(String(k)); },
};


const { renderReferenceResults } = await import('../src/enrichment_reference_view.js');

const walk = (n, out = []) => { out.push(n); for (const c of n.children || []) walk(c, out); return out; };
const byClass = (root, cls) => walk(root).filter((n) => n._classes?.includes(cls));
const bands = () => byClass(host, 'reference-evidence-head');
const tabsRow = () => byClass(host, 'reference-view-tabs')[0];
// A band that is not there must be SCORED, not thrown on: under the mutant that removes
// the primary band, an index straight into the list kills the run after one failure and
// the remaining assertions go unmeasured -- a mutant that throws is a hole, not a catch.
const bandText = (i) => bands()[i]?.textContent ?? '(no band)';

const rows = (n) => Array.from({ length: n }, (_, i) => ({ a: `a${i}`, b: `b${i}` }));
const payload = (n) => ({ columns: ['a', 'b'], rows: rows(n) });
const primary = (label, n) => ({ view: { label, candidate_for: { dt_lot: 'a' } }, payload: payload(n) });
const evidence = (label, n) => ({ view: { label }, payload: payload(n) });

console.log('\n[1] one view — the table has a title even with no tab strip');
{
  renderReferenceResults([primary('후보', 3)]);
  eq('the first table gets a band', 1, bands().length);
  ok('...carrying the view label verbatim', bandText(0).includes('후보'),
    bandText(0));
  ok('...and the row count beside it', bandText(0).includes('3행'),
    bandText(0));
  // 🔴 THE POINT OF THE ROUND: with one panel the tab strip is hidden, so before this the
  //    name lived nowhere at all.
  eq('the tab strip stays hidden for a single panel', 'none', tabsRow().style.display);
}

// ⚠️ 이 절은 «뒤집혔습니다» (C-103, 소유자 2026-09-13 「참조뷰는 왜 맨상단 두개는 탭이고
//    아래는 그냥 리스트야? 그냥 다 탭으로 해줘」). 종전 단언은 「근거는 탭이 아니다」였고,
//    그것이 목업 2b 의 배치였습니다. 지우지 «않고» 반대로 세웁니다 — 지우면 새 규칙을 재는
//    것이 아무것도 안 남습니다.
console.log('\n[2] a fillable view and an evidence view — BOTH are tabs');
{
  renderReferenceResults([primary('후보', 2), evidence('근거', 5)]);
  eq('each table has its own band', 2, bands().length);
  ok('the first is the primary label', bandText(0).includes('후보'), bandText(0));
  ok('the second is the evidence label', bandText(1).includes('근거'), bandText(1));
  eq('an evidence view gets a tab like any other', 2, byClass(host, 'reference-view-tab').length);
  eq('...so the strip is SHOWN', '', tabsRow().style.display);
  eq('...and there is no stack under the grid any more', 0,
    byClass(host, 'reference-evidence').length);
}

// ═══ C-103 — 갈래가 하나. 뷰 N 이면 탭 N, 순서는 `results` 그대로 ══════════════════════
console.log('\n[2b] five views — five tabs, one branch, and the tab points at its own table');
{
  const five = [primary('채움A', 2), evidence('근거1', 3), primary('채움B', 1),
                evidence('근거2', 4), evidence('근거3', 6)];
  renderReferenceResults(five);
  eq('one tab per view, fillable or not', 5, byClass(host, 'reference-view-tab').length);
  eq('one panel per view', 5, byClass(host, 'reference-view-panels')[0].children.length);
  eq('no evidence stack survives', 0, byClass(host, 'reference-evidence').length);
  // ⚠️ C-108 이후 탭은 «두 칸»(이름 · 행 수)입니다. 이름을 재려면 이름 칸을 읽어야 합니다 —
  //    `textContent` 는 이제 「채움A2행」입니다.
  const tabLabels = byClass(host, 'reference-view-tab')
    .map((b) => byClass(b, 'reference-view-tab-name')[0]?.textContent);
  eq('the tabs stand in the order the response gave them',
    '채움A,근거1,채움B,근거2,근거3', tabLabels.join(','));
  // 🔴 THE INDEX IS WHAT DECIDES WHICH TABLE A SELECTION IS IN (`td.dataset.view`), so a panel
  //    whose table carries another view's number is 「the tab shows one grid and the copy
  //    takes another」 -- which is exactly what two separate counters used to risk.
  const panels = byClass(host, 'reference-view-panels')[0];
  const tableIndex = panels.children.map(
    (p) => byClass(p, 'reference-view-table')[0]?.dataset.view);
  eq('each panel holds ITS OWN table, by number', '0,1,2,3,4', tableIndex.join(','));
  // 🔴 그리고 «눌러» 봅니다. 배선이 아니라 일어나는 일입니다.
  byClass(host, 'reference-view-tab')[3].dispatch('click');
  const shown = panels.children.map((p) => (p.style.display === 'none' ? '.' : 'X')).join('');
  eq('clicking the fourth tab shows the fourth panel and only it', '...X.', shown);
  ok('...and the active mark moved with it',
    byClass(host, 'reference-view-tab')[3].classList.contains('active')
    && !byClass(host, 'reference-view-tab')[0].classList.contains('active'),
    byClass(host, 'reference-view-tab').map((b) => b.className).join('|'));
  ok('...and the table under that tab is the fourth one',
    byClass(panels.children[3], 'reference-view-table')[0]?.dataset.view === '3');
}

console.log('\n[3] two primaries — tabs come back, and both keep their bands');
{
  renderReferenceResults([primary('A', 1), primary('B', 4)]);
  eq('two bands', 2, bands().length);
  eq('...and the tab strip is shown', '', tabsRow().style.display);
  eq('one tab per primary', 2, byClass(host, 'reference-view-tab').length);
  // 🔴 THE BAND LIVES INSIDE ITS PANEL. Appended as a sibling in `panels` it would make
  //    `selectView`'s index two-per-view, and clicking tab B would reveal A's band.
  const panels = byClass(host, 'reference-view-panels')[0];
  eq('panels stay one child per view', 2, panels.children.length);
  ok('...and each panel carries its own band',
    panels.children.every((p) => byClass(p, 'reference-evidence-head').length === 1),
    panels.children.map((p) => byClass(p, 'reference-evidence-head').length).join(','));
}

console.log('\n[4] the words are the response\'s, and a missing count is blank');
{
  renderReferenceResults([{ view: { candidate_for: { dt_lot: 'a' } }, payload: payload(2) }]);
  ok('an unlabelled primary falls back to Reference N',
    bandText(0).includes('Reference 1'), bandText(0));
  // ⚠️ 이 단언은 «뒤집혔습니다» (C-108). 「행 0」은 measurement 이고 빈 칸은 「셀 것이 안
  //    왔다」인데, 종전 코드가 그 둘을 «같이» 비워 두고 바로 위 주석이 구별한다고 적고
  //    있었습니다. 지우지 «않고» 반대로 세웁니다 — 지우면 새 규칙이 안 재집니다.
  renderReferenceResults([primary('빈', 0)]);
  ok('zero rows is a measurement and says so', bandText(0).includes('0행'),
    bandText(0));
  ok('...but the name is still there', bandText(0).includes('빈'),
    bandText(0));
  // 그리고 «안 온 것»은 빈 칸입니다. 거절된 뷰는 셀 것이 없었지 0 을 센 것이 아닙니다.
  renderReferenceResults([{ view: { label: '거절' }, error: '서버 문장' }]);
  ok('a refused view counts nothing, and says nothing', bandText(0) === '거절',
    bandText(0));
}


// ═══════════════════════════════════════════════════════════════════════════════════════════
// [5] C-73 — the request binds every column the derived table DECLARES, not the decision key.
//
// 🔴 THE DEFECT WAS LIVE. S-163 widened the server to accept any declared column and to refuse
//    an unknown key with a 400 that NAMES it; this screen still bound `decision_key` alone, so
//    every view naming another column came back `missing required bind param(s)`.
// 🔴 SCORED ON THE REQUEST, not on the render. The panel drew fine throughout -- what was wrong
//    was the URL, which is why nothing above this line could have caught it.
// ⚠️ The virtual-column case is pinned as a PROPERTY, not as a measurement: whether the server
//    ever puts a join column in `column_types` as well as in `virtual_columns` is a server
//    question this harness did not measure. If it ever does, the bind must still leave it out.
// ═══════════════════════════════════════════════════════════════════════════════════════════
console.log('\n[5] C-73 — the bind is the declared columns, not the decision key');

const path = await import('node:path');
const { fileURLToPath } = await import('node:url');
const { loadWithProbe } = await import('./lib/probe.mjs');
const { scoreMutants } = await import('./lib/mutation_scorer.mjs');
const { state } = await import('../src/state.js');

const SUBJECT = path.join(path.dirname(fileURLToPath(import.meta.url)),
  '..', 'src', 'enrichment_reference_view.js');

const RULE = {
  name: 'r1', derived_table: 'dt_x', decision_key: ['lot', 'slot'],
  reference_views: [{ label: 'v', candidate_for: { dt_lot: 'lot' } }],
};
// `note` is declared and blank -- a column the view asks ABOUT. `joined` is virtual. `stray`
// is on the row but not declared, so the catalogue is what decides, never the response.
const ROW = { id: 'r1', data: {
  lot: { value: 'L-1' }, slot: { value: '07' }, note: { value: '' },
  joined: { value: 'J' }, stray: { value: 'S' } } };

function armState() {
  state.currentTable = 'dt_x';
  state.currentColumnTypes = { lot: 'string', slot: 'string', note: 'string', joined: 'string' };
  state.currentVirtualColumns = [{ name: 'joined' }];
  state.selectedCell = { rowId: 'r1', colId: 'lot' };
  state.gridApi = { getRowNode: (id) => (id === 'r1' ? { data: ROW } : null) };
  state.activeHistoryTab = 'reference';
}

/** Drives the panel and hands back the `params` the request actually carried. */
async function askedParams(mod) {
  armState();
  let asked = null;
  globalThis.fetch = async (url) => {
    const u = String(url);
    if (u.includes('/enrichment/rules?') || u.endsWith('/enrichment/rules')) {
      return { ok: true, json: async () => ({ rules: [RULE] }) };
    }
    asked = new URL(u, 'http://x').searchParams.get('params');
    return { ok: true, json: async () => ({ columns: ['a'], rows: [{ a: 1 }] }) };
  };
  await mod.syncReferenceViewRule();
  await mod.showReferenceView();
  return asked === null ? null : JSON.parse(asked);
}

function paramsSuite(sent) {
  const names = [];
  const failures = [];
  const say = (name, cond, detail) => {
    names.push(name);
    if (cond) { console.log(`  PASS ${name}`); return; }
    failures.push(detail ? `${name} — ${detail}` : name);
    console.log(`  FAIL ${name}${detail ? ' — ' + detail : ''}`);
  };
  const keys = sent ? Object.keys(sent).sort().join(',') : '(no request)';
  say('C73-1 the request is made at all', sent !== null, keys);
  say('C73-2 params are the DECLARED columns present on the row', keys === 'lot,note,slot', keys);
  say('C73-3 ...which is WIDER than the decision key', sent
    && Object.keys(sent).length > RULE.decision_key.length, keys);
  say('C73-4 every decision key is still bound', sent
    && RULE.decision_key.every((k) => k in sent), keys);
  say('C73-5 a declared column that is BLANK is still bound, not dropped',
    sent && sent.note === '', JSON.stringify(sent && sent.note));
  say('C73-6 a virtual join column is left out — the server refuses it',
    sent ? !('joined' in sent) : false, keys);
  say('C73-7 a column the row carries but the catalogue does not declare is left out',
    sent ? !('stray' in sent) : false, keys);
  return { ran: names.length, names, failures };
}

const baseMod = (await loadWithProbe(SUBJECT, {})).module;
const baseSent = await askedParams(baseMod);
const base = paramsSuite(baseSent);
ran += base.ran;
failed += base.failures.length;

const MUTANTS = [
  // 🔴 THE DEFECT ITSELF, put back. The panel still renders and the row count is unchanged;
  //    only the URL is wrong, which is exactly how it reached production.
  { id: 'M1', what: 'the bind narrows back to the decision key',
    catches: 'C73-2 params are the DECLARED columns',
    from: '  const params = Object.fromEntries(declared.map(column => [column, valueOf(row, column)]));',
    to: '  const params = Object.fromEntries((activeRule.decision_key || [])'
      + '.map(column => [column, valueOf(row, column)]));' },
  { id: 'M2', what: 'virtual join columns stop being excluded',
    catches: 'C73-6 a virtual join column is left out',
    from: '    .filter(column => !isVirtualColumn(column) && Object.prototype.hasOwnProperty.call(row.data || {}, column));',
    to: '    .filter(column => Object.prototype.hasOwnProperty.call(row.data || {}, column));' },
  // 🔴 A WIDER EMPTINESS TEST CLOSES THE PANEL FOR THE ROWS IT EXISTS FOR. `note` is declared
  //    and blank on purpose, so this mutant makes the screen refuse instead of asking.
  { id: 'M3', what: 'the emptiness test widens to every bound column',
    catches: 'C73-1 the request is made at all',
    from: "  if ((activeRule.decision_key || []).some(column => String(valueOf(row, column)).trim() === '')) {",
    to: "  if (Object.values(params).some(value => String(value).trim() === '')) {" },
];

/**
 * 한 자리를 바꾸고, 그 자리가 «없으면» 던집니다.
 *
 * 🔴 앵커가 썩은 변이는 「잡혔다」가 아니라 «구멍»입니다 — 채점기가 그것을 INERT 로 부르고
 *    실패로 셉니다. 조용히 원문을 돌려주면 그 변이는 영원히 초록입니다.
 */
function swap(text, from, to) {
  if (!text.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`);
  return text.split(from).join(to);
}

const runMutant = async (m) => {
  const loaded = await loadWithProbe(SUBJECT, {
    mutate: (text) => {
      if (!text.includes(m.from)) throw new Error(`mutation anchor is GONE: ${m.id}`);
      return text.split(m.from).join(m.to);
    },
  });
  return paramsSuite(await askedParams(loaded.module));
};

const scored = await scoreMutants(MUTANTS, runMutant,
  { baselineRan: base.ran, baselineNames: base.names,
    title: '\n  C-73 mutants — each must be caught by the check it names.' });
ran += MUTANTS.length;
failed += scored.wrong;

// ═══════════════════════════════════════════════════════════════════════════════════════════
// [6] C-108 — 탭이 «행 수»를 달고, 표마다 «마지막 탭»을 기억하고, ←→ 로 넘어간다.
//
// 🔴 셋 다 «일어나는 일»로 잽니다: 배지의 «글자», 저장소의 «칸», 그리고 키를 «쏴서» 보는
//    패널. 배선(리스너가 걸렸나)은 이 물음들의 답이 아닙니다.
// ⚠️ 기억은 «이름»으로 합니다 — 번호로 하면 선언이 뷰를 하나 끼워 넣는 날 조용히 다른 표를
//    가리킵니다. 그 차이를 재는 것이 T7(뒤섞어도 같은 표) 입니다.
// ═══════════════════════════════════════════════════════════════════════════════════════════
console.log('\n[6] C-108 — the row-count badge, the remembered tab, and the arrow keys');

const refused = (label) => ({ view: { label }, error: '서버 문장' });
const tabsOf = () => byClass(host, 'reference-view-tab');
const nameOf = (b) => byClass(b, 'reference-view-tab-name')[0]?.textContent ?? '(no name)';
const countOf = (b) => byClass(b, 'reference-view-tab-count')[0]?.textContent ?? '';
const activeAt = () => tabsOf().findIndex((b) => b.classList.contains('active'));
const shownPanels = () => byClass(host, 'reference-view-panels')[0].children
  .map((p) => (p.style.display === 'none' ? '.' : 'X')).join('');
/** 탭 줄에 키를 «쏘고», 그 키가 거기서 끝났는지(`preventDefault`) 돌려줍니다. */
const press = (key, extra = {}) => {
  let ended = false;
  tabsRow().dispatch('keydown', { key, preventDefault: () => { ended = true; }, ...extra });
  return ended;
};
const FOUR = () => [primary('채움A', 2), evidence('근거1', 0), primary('채움B', 3), refused('거절')];

function c108Suite(mod) {
  const names = [];
  const failures = [];
  const say = (name, cond, detail) => {
    names.push(name);
    if (cond) { console.log(`  PASS ${name}`); return; }
    failures.push(detail ? `${name} — ${detail}` : name);
    console.log(`  FAIL ${name}${detail ? ' — ' + detail : ''}`);
  };

  memory.clear();
  state.currentTable = 'dt_x';
  mod.renderReferenceResults(FOUR());

  // ── ① 행 수 배지 ──────────────────────────────────────────────────────────────────
  say('T1 the tab says how many rows its own table has',
    countOf(tabsOf()[0]) === '2행' && countOf(tabsOf()[2]) === '3행',
    tabsOf().map((b) => `${nameOf(b)}=${countOf(b)}`).join('|'));
  say('T2 a measured zero is a number, not a blank', countOf(tabsOf()[1]) === '0행',
    countOf(tabsOf()[1]));
  say('T3 a refused view counted nothing, and its tab says nothing',
    countOf(tabsOf()[3]) === '', countOf(tabsOf()[3]));
  // 🔴 한 수를 두 자리가 적으면 언젠가 갈라집니다. 같은 함수를 지나는 것이 그 답입니다.
  say('T4 the band over the table says the same number as the tab',
    bandText(0).includes('2행') && bandText(1).includes('0행'),
    `${bandText(0)} / ${bandText(1)}`);

  // ── ② 표마다 마지막 탭 ────────────────────────────────────────────────────────────
  say('T5 a plain render remembers NOTHING -- drawing is not choosing', memory.size === 0,
    JSON.stringify([...memory.entries()]));
  tabsOf()[2].dispatch('click');
  const keys = [...memory.keys()];
  say('T6 choosing a tab remembers it, under a key that names the table',
    keys.length === 1 && keys[0].includes('dt_x') && memory.get(keys[0]) === '채움B',
    JSON.stringify([...memory.entries()]));
  mod.renderReferenceResults(FOUR());
  say('T7 ...so the next visit to this table opens on that tab', activeAt() === 2,
    `${activeAt()} / ${shownPanels()}`);
  // 🔴 실제 브라우저에서 잡힌 것(09-13): 탭 줄은 가로로 스크롤되므로 기억한 탭이
  //    «보이는 밖»에 있을 수 있고(offsetLeft 412 · 폭 394 · scrollLeft 0), 그러면 화면은
  //    「첫 탭」을 고른 것처럼 보입니다. 고른 탭은 «보이는» 것까지가 고른 것입니다.
  say('T22 ...and that tab is brought into view, because the strip scrolls',
    tabsOf()[2].scrolledIntoView === 1 && tabsOf()[0].scrolledIntoView === undefined,
    tabsOf().map((b) => b.scrolledIntoView || 0).join('|'));
  // 🔴 THE POINT OF REMEMBERING A NAME. The declaration may gain a view or reorder them; a
  //    remembered POSITION then points at another table and nothing errors.
  mod.renderReferenceResults([evidence('근거1', 0), primary('채움B', 3), primary('채움A', 2)]);
  say('T8 ...even after the views are reordered, because a NAME was remembered',
    activeAt() === 1 && nameOf(tabsOf()[1]) === '채움B',
    `${activeAt()} → ${nameOf(tabsOf()[activeAt()] || {})}`);
  state.currentTable = 'dt_other';
  mod.renderReferenceResults(FOUR());
  say('T9 another table does not inherit it -- the memory is per table', activeAt() === 0,
    `${activeAt()}`);
  state.currentTable = 'dt_x';
  mod.renderReferenceResults(FOUR());
  say('T10 ...and coming back opens on the remembered tab again', activeAt() === 2,
    `${activeAt()}`);
  // 이름이 오늘 목록에 «없으면» 첫 탭입니다. 기억이 화면을 못 정하는 자리입니다.
  mod.renderReferenceResults([primary('채움A', 2), evidence('근거1', 0)]);
  say('T11 a remembered view that is gone today falls back to the first tab',
    activeAt() === 0, `${activeAt()}`);

  // ── ③ ←→ ─────────────────────────────────────────────────────────────────────────
  memory.clear();
  state.currentTable = 'dt_keys';
  mod.renderReferenceResults(FOUR());
  const endedRight = press('ArrowRight');
  say('T12 ArrowRight moves to the next tab, and that panel is the one shown',
    activeAt() === 1 && shownPanels() === '.X..', `${activeAt()} / ${shownPanels()}`);
  say('T13 ...the key ends there, so the strip does not scroll as well', endedRight === true);
  say('T14 ...and the focus follows it, so the next arrow carries on',
    globalThis.document.activeElement === tabsOf()[1],
    nameOf(globalThis.document.activeElement || {}));
  // ⚠️ 키의 «철자»를 벯겨 적지 «않습니다» — 베끼면 이 하니스가 그 문자열의 «둘째 저자»가 되고,
  //    이름만 바꾸는 리팩터링이 «올바른 코드»를 빨갞니다. 재는 것은 «왕복»이고, 표마다라는
  //    성질은 키가 표 이름을 «들고 있나»로 재집니다(T9 가 그 본롯입니다).
  say('T15 ...and an arrow is remembered exactly as a click is',
    memory.size === 1 && [...memory.keys()][0].includes('dt_keys')
      && [...memory.values()][0] === '근거1',
    JSON.stringify([...memory.entries()]));
  press('ArrowLeft');
  say('T16 ArrowLeft goes back', activeAt() === 0, `${activeAt()}`);
  const endedEdge = press('ArrowLeft');
  say('T17 at the first tab it stays -- the strip does not wrap around', activeAt() === 0,
    `${activeAt()}`);
  say('T18 ...and the key still ends there', endedEdge === true);
  press('ArrowRight'); press('ArrowRight'); press('ArrowRight'); press('ArrowRight');
  say('T19 at the last tab it stays too', activeAt() === 3, `${activeAt()}`);
  // Shift+←→ 는 «선택»의 몫입니다(`installSelectionKeys`). 탭이 그것을 먹으면 범위를
  // 넓히려던 손이 표를 바꿉니다.
  const before = activeAt();
  press('ArrowLeft', { shiftKey: true });
  say('T20 Shift+Arrow is the selection\'s, not the tab strip\'s', activeAt() === before,
    `${before} → ${activeAt()}`);
  const endedOther = press('ArrowDown');
  say('T21 another key is not a tab switch, and is not swallowed',
    activeAt() === before && endedOther === false, `${activeAt()} / ${endedOther}`);

  return { ran: names.length, names, failures };
}

const c108Base = c108Suite(baseMod);
ran += c108Base.ran;
failed += c108Base.failures.length;

const C108_MUTANTS = [
  { id: 'M4', what: 'the tab loses its row count',
    catches: 'T1 the tab says how many rows',
    mutate: (text) => swap(text, '    const tabCount = rowCountText(payload?.rows?.length);',
      "    const tabCount = '';") },
  // 🔴 THE OLD BEHAVIOUR, PUT BACK: `0` and 「nothing came」 render identically again.
  { id: 'M5', what: 'a measured zero goes blank again',
    catches: 'T2 a measured zero is a number',
    mutate: (text) => swap(text, '  return isCount(rowCount) ? `${rowCount}행` : \'\';',
      '  return rowCount ? `${rowCount}행` : \'\';') },
  { id: 'M6', what: 'the memory holds a POSITION instead of a name',
    catches: 'T8 ...even after the views are reordered',
    mutate: (text) => swap(
      swap(text, '  const chooseView = (index) => { selectView(index); rememberTabName(names[index]); };',
        '  const chooseView = (index) => { selectView(index); rememberTabName(index); };'),
      '    const remembered = names.indexOf(rememberedTabName());',
      '    const remembered = rememberedTabName() === \'\' ? -1 : Number(rememberedTabName());') },
  { id: 'M7', what: 'every table shares one memory',
    catches: 'T9 another table does not inherit it',
    mutate: (text) => swap(text,
      '  return state.currentTable ? `${TAB_MEMORY_PREFIX}${state.currentTable}` : \'\';',
      '  return TAB_MEMORY_PREFIX;') },
  { id: 'M8', what: 'the arrow switches the tab but nobody remembers it',
    catches: 'T15 ...and an arrow is remembered',
    mutate: (text) => swap(text, '    chooseView(next);', '    selectView(next);') },
  { id: 'M9', what: 'the arrows wrap around at the ends',
    catches: 'T17 at the first tab it stays',
    mutate: (text) => swap(text,
      '    const next = Math.min(Math.max(at + step, 0), tabs.children.length - 1);',
      '    const next = (at + step + tabs.children.length) % tabs.children.length;') },
  { id: 'M11', what: 'the chosen tab is never brought into view',
    catches: 'T22 ...and that tab is brought into view',
    mutate: (text) => swap(text,
      "    tabs.children[index]?.scrollIntoView({ block: 'nearest', inline: 'nearest' });\n", '') },
  { id: 'M10', what: 'the strip keeps the key, so it scrolls while the tab changes',
    catches: 'T13 ...the key ends there',
    mutate: (text) => swap(text, '    event.preventDefault();\n    if (next === at) return;',
      '    if (next === at) return;') },
];

// 🔴 CONTROLS. A change that alters no behaviour must wake NOTHING -- otherwise the suite is
//    scoring the file's shape rather than what the screen does.
const C108_CONTROLS = [
  { id: 'C1', what: 'a local rename inside the tab builder',
    mutate: (text) => swap(text, 'const tabName = document.createElement', 'const nameCell = document.createElement')
      .split('tabName.className').join('nameCell.className')
      .split('tabName.textContent').join('nameCell.textContent')
      .split('tab.appendChild(tabName)').join('tab.appendChild(nameCell)') },
  { id: 'C2', what: 'the storage key is spelled differently',
    mutate: (text) => swap(text, "const TAB_MEMORY_PREFIX = 'assy.refview.tab.';",
      "const TAB_MEMORY_PREFIX = 'assy.reference.lastTab.';") },
];

const runC108 = async (m) =>
  c108Suite((await loadWithProbe(SUBJECT, { mutate: m.mutate })).module);

const scored108 = await scoreMutants(C108_MUTANTS, runC108,
  { baselineRan: c108Base.ran, baselineNames: c108Base.names,
    title: '\n  C-108 mutants — each must be caught by the check it names.' });
ran += C108_MUTANTS.length;
failed += scored108.wrong;

const controls108 = await scoreMutants(C108_CONTROLS, runC108,
  { mustCatch: false, baselineRan: c108Base.ran, baselineNames: c108Base.names,
    title: '\n  C-108 controls — behaviour unchanged, so nothing may wake.' });
ran += C108_CONTROLS.length;
failed += controls108.wrong;

console.log(`\n════ RESULT: ${ran - failed} passed, ${failed} failed ════`);
console.log(`ASSERTIONS ${ran} ${failed}`);
process.exit(failed === 0 ? 0 : 1);
