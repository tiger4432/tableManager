// 탭 활성 표시 «한 좌석» — 판정 2026-09-22. 게이트는 «수»가 아니라 «성질»을 잡는다.
//
// 🔴 이 좌석이 왜 있나: 갈아타기마다 형제를 «손으로» 나열하던 자리가 다섯이었고, 넷째 탭이
//    줄에는 들어갔는데 그 목록들에 안 들어가 탭 «둘»이 동시에 켜졌다 (main.js 의 옛 주석).
//    그래서 이 파일의 핵심 단언은 T2 다 — «목록을 안 고치고» 탭을 하나 더 넣어도 덮이는가.
import { readFileSync, readdirSync } from 'node:fs';
import { makeDoc } from './lib/board_dom.mjs';
import { activateHistoryTab } from '../src/history_tabs.js';

let pass = 0; const failures = [];
const eq = (what, got, want) => {
  if (String(got) === String(want)) { pass += 1; console.log(`  PASS ${what}`); }
  else { failures.push(what); console.log(`  FAIL ${what} -- got ${got}, want ${want}`); }
};

const doc = makeDoc('light');
const barOf = (n) => {
  const bar = doc.createElement('div');
  bar.className = 'history-tabs';
  const buttons = [];
  for (let i = 0; i < n; i += 1) {
    const b = doc.createElement('button');
    b.className = 'tab-btn';
    bar.appendChild(b); buttons.push(b);
  }
  return { bar, buttons };
};
const activeCount = (bar) => bar.children.filter((c) => c.classList.contains('active')).length;

console.log('\n[1] one active, and only one');
{
  const { bar, buttons } = barOf(3);
  activateHistoryTab(buttons[0]);
  eq('T1 activating one leaves exactly one active', activeCount(bar), 1);
  activateHistoryTab(buttons[2]);
  eq('T1b ...and switching moves it rather than stacking', activeCount(bar), 1);
  eq('T1c ...onto the button that was asked for',
    buttons[2].classList.contains('active'), 'true');
}

console.log('\n[2] a tab added to the ROW is covered without touching the seat');
{
  // 🔴 이것이 그 사고다. 옛 코드는 목록을 «손으로» 들고 있어서, 줄에만 넣은 탭이
  //    남의 활성을 못 껐다 — 그리고 그 탭이 숨겨져 있는 동안은 아무 증상이 없었다.
  const { bar, buttons } = barOf(3);
  const fifth = doc.createElement('button');
  fifth.className = 'tab-btn';
  bar.appendChild(fifth);              // 좌석은 한 글자도 안 고쳤다
  activateHistoryTab(buttons[1]);
  activateHistoryTab(fifth);
  eq('T2 the new tab turns the others off', activeCount(bar), 1);
  eq('T2b ...and it is the new one that is on', fifth.classList.contains('active'), 'true');
}

console.log('\n[3] it does not throw on the shapes the page actually passes');
{
  activateHistoryTab(null);
  activateHistoryTab(undefined);
  pass += 1; console.log('  PASS T3 a missing button is a no-op, not a crash');
  const loose = doc.createElement('button');
  activateHistoryTab(loose);
  eq('T3b a button with no row still turns on', loose.classList.contains('active'), 'true');
}

console.log('\n[4] PROPERTY: nothing outside this seat touches tab activation');
{
  // 🔵 총괄 지시(20:15): 「그 수를 게이트에 쓰지 말고 «성질»로 잡으십시오」.
  //    그래서 16 이라는 수가 아니라 «좌석 밖이 0 인가»를 단언한다 — 탭이 늘어도 안 낡는다.
  const dir = new URL('../src/', import.meta.url);
  const hits = [];
  for (const name of readdirSync(dir)) {
    if (!name.endsWith('.js') || name === 'history_tabs.js') continue;
    const text = readFileSync(new URL(name, dir), 'utf8');
    for (const line of text.split('\n')) {
      if (/tab(Global|Cell|Row|Reference)Btn[^;]*classList/.test(line)) hits.push(`${name}: ${line.trim()}`);
    }
  }
  eq('T4 tab-button classList is touched nowhere else', hits.length, 0);
  if (hits.length) hits.slice(0, 5).forEach((h) => console.log(`       ${h}`));
  // 카나리아: 이 훑기가 «아무것도 못 짚는» 상태면 위 0 은 뜻이 없다
  const seat = readFileSync(new URL('history_tabs.js', dir), 'utf8');
  eq('T4b CANARY: the scan can see the seat itself', /classList/.test(seat), 'true');
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
