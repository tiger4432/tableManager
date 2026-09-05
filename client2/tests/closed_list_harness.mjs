// CLOSED LIST — 「고를 게 없는 고르개」와 「고장난 고르개」가 화면에서 달라지는지.
//
// The subject is imported (owner, 2026-09-02: 잘라쓰기 하니스 절대 금지). `closed_list.js`
// takes its element factory as an argument, so it holds no DOM at module scope and imports
// in node as it stands.
//
// 🔴 THE THREE THIS FILE EXISTS FOR:
//   ① A DROPDOWN WITH ONE ENTRY LOOKS BROKEN. `occurred_at_basis` ships with exactly one
//      member and its picker could never do anything; on screen it was indistinguishable
//      from the two pickers that were genuinely broken, and those want opposite fixes.
//   ② FOUR STATES, NOT TWO. list-not-arrived · zero members · the value · the picker.
//      Reading 「아직 안 옴」 as 「멤버 0」 draws EVERY list as empty while the fetch is in
//      flight, which is this repository's oldest closed class in a new place.
//   ③ 🔴 AND THE WRITE PATH MUST SURVIVE THE RULE. One member with an EMPTY document is the
//      one case where the picker is the only way the value can ever be written -- turning
//      that into a value would make the field unfillable, which is 「도출로 바꾸면 먹이던
//      축이 죽는다」 with the axis being the operator's own typing.
//
// Run: node client2/tests/closed_list_harness.mjs
import { closedListChoice, renderClosedList, LIST_UNREAD, NO_CHOICE } from '../src/closed_list.js';

let pass = 0;
const failures = [];
function eq(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { pass++; console.log(`  PASS ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name}\n        got  ${g}\n        want ${w}`); }
}
function ok(name, cond, detail = '') {
  if (cond) { pass++; console.log(`  PASS ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name} ${detail}`); }
}

// The real `h` is `document.createElement` plus a class and a text; this is that contract
// and nothing more, so anything the part needs beyond it fails here rather than in a browser.
function h(tag, cls, text) {
  const el = {
    tagName: String(tag).toUpperCase(),
    className: cls || '', children: [], attrs: Object.create(null),
    dataset: Object.create(null), _text: '', value: '', selected: false,
    append(...cs) { this.children.push(...cs); },
    setAttribute(k, v) { this.attrs[String(k)] = String(v); },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, String(k))
      ? this.attrs[String(k)] : null; },
    get textContent() { return this._text + this.children.map(c => c.textContent).join(''); },
  };
  if (text !== undefined) el._text = String(text);
  return el;
}
const draw = (options, current, opts, spec = {}) => renderClosedList(
  closedListChoice(options, current, opts), h,
  { action: 'edit-shape', path: 'bundle.sources.s.read.occurred_at_basis', ...spec });
const opts = (el) => el.children.filter(c => c.tagName === 'OPTION').map(c => c.value);

// ═══ ① 멤버 수가 컨트롤을 정한다 ═══════════════════════════════════════════════════
console.log('\n[1] the member count decides the control');
{
  // 🔴 THE SHIPPED CASE. One member, and the document holds it -- there is nothing this
  //    control could select that is not already there.
  eq('one member, already declared, is a VALUE',
    closedListChoice(['ingested'], 'ingested').control, 'value');
  eq('two members is a picker', closedListChoice(['row', 'group'], 'row').control, 'picker');
  eq('three likewise', closedListChoice(['event', 'row', 'group_by'], 'row').control, 'picker');

  // 🔴 ③ — the one case the rule must NOT swallow.
  eq('one member with an EMPTY document stays a picker, or it can never be filled',
    closedListChoice(['ingested'], '').control, 'picker');
  eq('...and the blank is offered beside it, so the box does not read as already-answered',
    closedListChoice(['ingested'], '').options, ['', 'ingested']);

  // A value the list does not know is a second thing to choose between: the stray and the
  // member. Drawing that as a value would leave the operator no way to correct it.
  eq('one member and a stray value is a picker',
    closedListChoice(['ingested'], 'bogus').control, 'picker');
  eq('...offering both, the stray first', closedListChoice(['ingested'], 'bogus').options,
    ['bogus', 'ingested']);
}

// ═══ ② 네 상태 — 「모름」과 「없음」은 같은 픽셀이 아니다 ══════════════════════════════
console.log('\n[2] four states, and two of them are not the same empty');
{
  const unread = closedListChoice(['ingested'], 'ingested', { loaded: false });
  eq('a list that has not arrived says so', unread.control, 'unread');
  eq('...in the word for 「모름」', unread.reason, LIST_UNREAD);

  const none = closedListChoice([], '', { name: 'occurred_at_basis' });
  eq('a list that arrived empty says something else', none.control, 'none');
  ok('...naming WHICH list, so the operator has somewhere to go',
    none.reason.startsWith(NO_CHOICE) && none.reason.includes('occurred_at_basis'));
  ok('the two are not the same pixel', unread.reason !== none.reason);
  ok('...nor the same class',
    draw(['a'], 'a', { loaded: false }).className !== draw([], '', {}).className);

  // 🔴 THE FETCH-IN-FLIGHT CASE, WHICH IS THE WHOLE REASON `loaded` EXISTS. The schema is
  //    `{}` until it lands; a list read out of it is `undefined`, not `[]`.
  eq('an absent list under a loaded schema is 「없음」',
    closedListChoice(undefined, '', { name: 'x' }).control, 'none');
  eq('...but the same absence before the schema lands is 「모름」',
    closedListChoice(undefined, '', { loaded: false, name: 'x' }).control, 'unread');
  eq('a non-list is not read as a member', closedListChoice('ingested', '').control, 'none');
  eq('non-strings in the list are not offered',
    closedListChoice(['a', 7, null, 'b'], 'a').options, ['a', 'b']);
}

// ═══ ③ 그리는 것만으로 남의 파일을 고치지 않는다 ═══════════════════════════════════════
console.log('\n[3] rendering never rewrites the file');
{
  const stray = draw(['row', 'group'], 'bogus');
  eq('a stray value is still an option', opts(stray), ['bogus', 'row', 'group']);
  eq('...and it is the selected one, not the first member',
    stray.children.filter(c => c.selected).map(c => c.value), ['bogus']);
  const blank = draw(['row', 'group'], '');
  eq('an absent value shows blank rather than the first choice',
    blank.children.filter(c => c.selected).map(c => c.value), ['']);

  // 🔴 THE VALUE SURVIVES EVERY STATE. If the list is unreadable and the screen drops what
  //    the document holds, the screen reads as having deleted it -- and it deleted nothing.
  ok('an unread list still shows the declared value',
    draw(['ingested'], 'ingested', { loaded: false }).textContent.includes('ingested'));
  ok('...and still says why there is no control',
    draw(['ingested'], 'ingested', { loaded: false }).textContent.includes(LIST_UNREAD));
  ok('an empty list still shows the declared value',
    draw([], 'bogus', { name: 'occurred_at_basis' }).textContent.includes('bogus'));
  ok('...and names the list it found no members in',
    draw([], 'bogus', { name: 'occurred_at_basis' }).textContent.includes('occurred_at_basis'));
  eq('an empty list with an empty document draws no value at all',
    draw([], '', { name: 'x' }).children.filter(c => c.className === 'oe-value').length, 0);
}

// ═══ ④ 쓰기 주소는 부르는 쪽의 것 ═══════════════════════════════════════════════════
//
// 🔴 두 자리가 «같은 부품»을 쓰되 쓰기 주소는 각자의 것이다. 여기서 한쪽 주소가 다른 쪽에
//    새면 고르개는 멀쩡히 그려지면서 «남의 칸»에 쓴다 — 오류 없이.
console.log('\n[4] one part, two write addresses');
{
  const skeleton = draw(['row', 'group'], 'row', {},
    { action: 'edit-shape', path: 'bundle.sources.s.read.unit' });
  eq('the skeleton leaf writes through its own action', skeleton.dataset.action, 'edit-shape');
  eq('...at its own path', skeleton.dataset.value, 'bundle.sources.s.read.unit');
  const planRow = draw(['row', 'group'], 'row', {},
    { action: 'edit-field', path: 'bundle.sources.s.read.unit', label: '읽기 단위' });
  eq('the plan row writes through the other one', planRow.dataset.action, 'edit-field');
  eq('...and a row that has a label uses it, not the path',
    planRow.getAttribute('aria-label'), '읽기 단위');
  eq('a leaf with no label falls back to the path',
    skeleton.getAttribute('aria-label'), 'bundle.sources.s.read.unit');
  // A value is still addressable: a screen reader must reach it the same way.
  ok('the value form carries the same label',
    draw(['ingested'], 'ingested', {}, { label: '발생 시각 기준' })
      .getAttribute('aria-label') === '발생 시각 기준');
}

// ═══ ⑤ 규칙이 «한 곳»에 있나 — 드리프트 오라클 ═════════════════════════════════════════
//
// ⚠️ 여기서 «주어»는 텍스트다 (총괄 판정 2026-09-03의 예외 그대로). 재는 것은 동작이 아니라
//    「이 규칙의 사본이 다시 생겼나」이고, 모양이 바뀌면 빨개지는 것이 여기서는 기능이다.
console.log('\n[5] the rule has one home');
{
  const { readFileSync } = await import('node:fs');
  const view = readFileSync(new URL('../src/ontology_explorer_view.js', import.meta.url), 'utf8');
  ok('the view builds no closed-list dropdown of its own', !view.includes("oe-field-select"));
  ok('...it asks the part instead', view.includes('renderClosedList')
    && view.includes('closedListChoice'));
  eq('and it asks from BOTH sites, not one',
    (view.match(/renderClosedList\(/g) || []).length, 2);
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
