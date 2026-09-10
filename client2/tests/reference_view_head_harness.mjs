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
    addEventListener() {}, closest() { return null; },
    set textContent(v) { this._text = String(v); this.children = []; },
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); },
  };
  return node;
}
const host = element('div');
globalThis.document = { createElement: element, createDocumentFragment: () => element('#f'),
  // 🔴 `elements.referenceViewContent` is a GETTER over `getElementById`, so the host is
  //    handed over the way the browser hands it over. Nothing in the subject is patched.
  getElementById: (id) => (id === 'reference-view-content' ? host : null),
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

console.log('\n[2] primary + evidence — two bands, still one panel');
{
  renderReferenceResults([primary('후보', 2), evidence('근거', 5)]);
  eq('each table has its own band', 2, bands().length);
  ok('the first is the primary label', bandText(0).includes('후보'), bandText(0));
  ok('the second is the evidence label', bandText(1).includes('근거'), bandText(1));
  eq('...and the strip is still hidden — evidence is not a tab', 'none', tabsRow().style.display);
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

console.log(`\n════ RESULT: ${ran - failed} passed, ${failed} failed ════`);
console.log(`ASSERTIONS ${ran} ${failed}`);
process.exit(failed === 0 ? 0 : 1);
