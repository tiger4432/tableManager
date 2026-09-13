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
  addEventListener() {}, querySelector: () => null };


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
  const tabLabels = byClass(host, 'reference-view-tab').map((b) => b.textContent);
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
  // ⚠️ 「행 0」 is a measurement; a blank is 「셀 것이 안 왔다」. They are not the same claim.
  renderReferenceResults([primary('빈', 0)]);
  ok('no rows means no count, not a zero', !bandText(0).includes('0행'),
    bandText(0));
  ok('...but the name is still there', bandText(0).includes('빈'),
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

console.log(`\n════ RESULT: ${ran - failed} passed, ${failed} failed ════`);
console.log(`ASSERTIONS ${ran} ${failed}`);
process.exit(failed === 0 ? 0 : 1);
