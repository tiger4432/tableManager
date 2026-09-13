/**
 * clipboard_type_modal -- 조립식의 «정의»를 이 부품에 대고 잽니다 (C-100).
 *
 * WHY THIS EXISTS. 이 모달은 `main.js` 안의 함수였고 겉모양을 «전부» JS 에서 지었습니다 --
 * `Object.assign(el.style, {…})` 다섯 블록과 innerHTML 의 `style="…"` 넷, 클래스는 «0». 그러면
 * 시트가 이 화면에 대해 아무 말도 못 하고(스킬 「인라인이 스타일시트를 이긴다」), hover 가
 * `mouseenter`/`mouseleave` 두 리스너라 «키보드로는 닿지도 않습니다».
 * 그리고 겉 상자가 «고정 id» 를 달고 있었습니다 -- 같은 화면에 둘이 뜨면 둘째가 첫째의
 * 셀렉터를 훔치고, 오류는 «안 납니다».
 *
 * 🔴 그래서 재는 것은 「예쁜가」가 아니라 소유자 상설의 «시험» 그 문장입니다:
 *      「같은 화면에 두 인스턴스를 놓고 간섭이 없어야 한다 -- 이게 «끼워넣을 수 있다»의 정의」
 *
 * WHAT IT SCORES:
 *   A  자기 div 하나를 mount 아래 만든다. 고정 id 는 «없다»
 *   B  서버가 아니라 «브라우저»가 준 MIME 마다 줄 하나. 모르는 MIME 도 «고를 수 있다»
 *   C  고른 것이 resolve 된다 · 취소는 `null` -- 둘은 다른 답이다
 *   D  같은 화면에 «둘», 간섭 «0»: 하나를 닫아도 다른 하나가 서 있고 자기 답만 받는다
 *   E  겉모양은 클래스로 말한다 -- 「열림」도, 줄의 강조색도(사용자 지정 속성)
 *
 * CONSOLE OUTPUT IS ASCII-SAFE WHERE IT MATTERS (cp949).
 */
import { makeDoc, walk, byClass, flush } from './lib/board_dom.mjs';
import { ClipboardTypeModal, CLIPBOARD_TYPE_LABELS } from '../src/clipboard_type_modal.js';

let pass = 0, fail = 0;
const failed = [];
const ok = (name, cond, note) => {
  if (cond) { pass++; console.log(`  ok   ${name}`); }
  else { fail++; failed.push(name); console.log(`  BAD  ${name}${note === undefined ? '' : ' -- ' + note}`); }
};
const eq = (name, got, want) => ok(name, got === want, `got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`);

const doc = makeDoc('light');
// 🔴 시간은 «주입»합니다. 기다림은 이 부품의 성질이 아니라 그 자리의 성질이고, 하니스가
//    진짜로 200ms 를 기다리면 그 기다림은 «단언»이 아니라 비용입니다.
// ⚠️ 프레임은 주입할 것이 «없습니다» — 부품이 프레임에 안 기댑니다. 기대던 판은 숨겨진 탭에서
//    영영 안 열렸습니다(실측 2026-09-13), 그래서 그 손잡이 자체가 사라졌습니다.
const nowDeps = { doc, timer: (fn) => fn(), closeMs: 0 };
const mountIn = () => {
  const host = doc.createElement('div');
  doc.body.appendChild(host);
  return host;
};
const TYPES = ['text/plain', 'text/html', 'application/x-invented-here'];
const rowsIn = (host) => byClass(host, 'ctm-row');

console.log('-- A. 자기 div 하나, 고정 id 없음 --');
{
  const host = mountIn();
  const modal = new ClipboardTypeModal(host, nowDeps);
  const answer = modal.open(TYPES);
  eq('A1 mount 아래에 자기 상자 하나', host.children.length, 1);
  eq('A2 그 상자가 부품의 것', host.children[0].className, 'ctm-overlay is-open');
  // 🔴 고정 id 가 «없습니다». 이것이 D 절이 성립하는 이유이고, 종전 결함 그 자체입니다.
  ok('A3 고정 id 를 안 단다 -- 둘째 인스턴스가 훔칠 셀렉터가 없다',
    walk(host).every((el) => !(el.attrs && el.attrs.id)),
    JSON.stringify(walk(host).map((el) => el.attrs && el.attrs.id).filter(Boolean)));
  ok('A4 dialog 라고 «말한다»', host.children[0].getAttribute('role') === 'dialog');
  byClass(host, 'ctm-cancel')[0].dispatch('click', {});
  await answer;
}

console.log('\n-- B. 브라우저가 준 것마다 한 줄, 모르는 것도 --');
{
  const host = mountIn();
  const answer = new ClipboardTypeModal(host, nowDeps).open(TYPES);
  const rows = rowsIn(host);
  eq('B1 줄 수는 받은 MIME 수', rows.length, TYPES.length);
  eq('B2 줄마다 자기 MIME 을 든다',
    rows.map((r) => r.attrs['data-type']).join('|'), TYPES.join('|'));
  // 🔴 모르는 MIME 을 «빼면» 붙일 수 있는 것을 못 고르게 됩니다. 이름표만 없는 것이지
  //    못 붙이는 것이 아닙니다.
  eq('B3 이름표 없는 MIME 도 «그 이름»으로 서 있다',
    byClass(rows[2], 'ctm-label')[0].textContent, 'application/x-invented-here');
  eq('B4 아는 MIME 은 괄호 앞까지만 이름으로',
    byClass(rows[0], 'ctm-label')[0].textContent,
    CLIPBOARD_TYPE_LABELS['text/plain'].label.split(' (')[0]);
  byClass(host, 'ctm-cancel')[0].dispatch('click', {});
  await answer;
}

console.log('\n-- C. 고른 것과 취소는 «다른 답» --');
{
  const host = mountIn();
  const answer = new ClipboardTypeModal(host, nowDeps).open(TYPES);
  rowsIn(host)[1].dispatch('click', {});
  eq('C1 고른 MIME 이 그대로 나온다', await answer, 'text/html');
  eq('C2 ...그리고 자기 상자를 치운다', host.children.length, 0);

  const host2 = mountIn();
  const answer2 = new ClipboardTypeModal(host2, nowDeps).open(TYPES);
  byClass(host2, 'ctm-cancel')[0].dispatch('click', {});
  // 🔴 `null` 은 「아무것도 안 골랐다」이고, 「고르다 실패했다」가 아닙니다. 부른 쪽이 그 둘을
  //    가릅니다 -- 취소를 빈 문자열로 내면 그 구별이 사라집니다.
  eq('C3 취소는 null 이다 -- 「안 골랐다」', await answer2, null);
}

console.log('\n-- D. 같은 화면에 «둘», 간섭 0 (조립식의 정의) --');
{
  const one = mountIn();
  const two = mountIn();
  const a = new ClipboardTypeModal(one, nowDeps).open(['text/plain', 'text/csv']);
  const b = new ClipboardTypeModal(two, nowDeps).open(['text/html']);
  eq('D1 각자 자기 mount 안에만 그린다', `${one.children.length}/${two.children.length}`, '1/1');
  eq('D2 각자 자기 목록을 든다', `${rowsIn(one).length}/${rowsIn(two).length}`, '2/1');

  rowsIn(two)[0].dispatch('click', {});
  eq('D3 둘째를 닫아도 «첫째»는 서 있다', one.children.length, 1);
  eq('D4 ...그리고 둘째의 답은 둘째의 것', await b, 'text/html');

  rowsIn(one)[1].dispatch('click', {});
  eq('D5 첫째의 답은 첫째의 것 -- 둘이 섞이지 않는다', await a, 'text/csv');
  eq('D6 그리고 둘 다 자기 상자를 치웠다', `${one.children.length}/${two.children.length}`, '0/0');
}

console.log('\n-- E. 겉모양은 «클래스»가 말한다 --');
{
  const host = mountIn();
  const answer = new ClipboardTypeModal(host, nowDeps).open(TYPES);
  const overlay = host.children[0];
  // 🔴 「열림」이 클래스입니다. 인라인 opacity 로 말하면 시트가 그 상태에 대해 아무 말도 못 하고,
  //    그것이 이 부품이 통째로 앓던 병입니다.
  ok('E1 열림은 클래스로 말한다', overlay.classList.contains('is-open'), overlay.className);
  // 🔴 줄의 강조색은 «데이터»(어느 MIME 인가)라 사용자 지정 속성으로 내려갑니다 -- 규칙은
  //    시트에 하나, 값만 부품이 실어 줍니다. 인라인 `color` 로 적으면 규칙이 둘이 됩니다.
  eq('E2 강조색은 값으로 내려가고 규칙은 시트에 남는다',
    rowsIn(host)[0].style.getPropertyValue('--ctm-accent'),
    CLIPBOARD_TYPE_LABELS['text/plain'].accent);
  // 🔴 E3 은 「부품이 «보통» 스타일 속성을 쓰지 않는다」입니다 — 사용자 지정 속성(`--…`)은
  //    값이라 셈에서 빠집니다. 첫 판은 「style 속성이 없다」였는데 그건 아무것도 안 재는
  //    단언이었습니다: 이 스텁에서 `setProperty` 는 속성을 «안 쓰고»(그래서 언제나 참),
  //    진짜 DOM 에서는 사용자 지정 속성 때문에 «언제나» 거짓입니다.
  const ordinary = walk(host).flatMap((el) => Object.keys(
    (el.style && el.style._props) || {}).filter((k) => !k.startsWith('--')));
  ok('E3 CONTROL: 부품이 «보통» 스타일 속성을 하나도 안 쓴다 -- 겉모양은 전부 시트의 것',
    ordinary.length === 0, JSON.stringify(ordinary));
  byClass(host, 'ctm-cancel')[0].dispatch('click', {});
  await answer;
  eq('E4 닫히면 body 에 남는 것이 없다', doc.body.children.filter((h) => h.children.length).length, 0);
}

await flush();
console.log(`\n${pass} passed, ${fail} failed.`);
console.log(`ASSERTIONS ${pass + fail} ${fail}`);
if (fail) {
  console.log('FAILED: ' + failed.join(' | '));
  process.exitCode = 1;
}
