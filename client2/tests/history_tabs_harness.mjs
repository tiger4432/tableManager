// 탭 «한 좌석» — 판정 2026-09-22, 넓힘 10-21 (총괄, 소유자 「탭은 글로벌인데 가끔 대기열 따로 있네」).
// 게이트는 «수»가 아니라 «성질»을 잡는다.
//
// 🔴 이 좌석이 왜 있나: 갈아타기마다 형제를 «손으로» 나열하던 자리가 다섯이었고, 넷째 탭이
//    줄에는 들어갔는데 그 목록들에 안 들어가 탭 «둘»이 동시에 켜졌다 (main.js 의 옛 주석).
//    10-21: 탭 표시 · 창 보이기 · state.activeHistoryTab 이 셋으로 따로 불려서 표 바꾸기가 탭만 Global 로
//    켜고 대기열 창을 남겼다. 그래서 셋은 pickHistoryTab 하나로만 바뀌고, [3] 이 좌석 밖을 센다.
import { readFileSync, readdirSync } from 'node:fs';
import { makeDoc } from './lib/board_dom.mjs';
import { pickHistoryTab } from '../src/history_tabs.js';
import { state } from '../src/state.js';

let pass = 0; const failures = [];
const eq = (what, got, want) => {
  if (String(got) === String(want)) { pass += 1; console.log(`  PASS ${what}`); }
  else { failures.push(what); console.log(`  FAIL ${what} -- got ${got}, want ${want}`); }
};

// The sidebar as index.html has it: the four tabs on the row (Cell is off it), the three panes.
const doc = makeDoc('light');
globalThis.document = doc;
const node = (tag, id, parent) => { const n = doc.createElement(tag); n.setAttribute('id', id); parent.appendChild(n); return n; };
const bar = doc.createElement('div');
doc.body.appendChild(bar);
const BUTTONS = { reference: node('button', 'tab-reference', bar), global: node('button', 'tab-global', bar),
  row: node('button', 'tab-row', bar), queue: node('button', 'tab-queue', bar) };
const PANES = { timeline: node('div', 'timeline-container', doc.body), reference: node('div', 'reference-view', doc.body),
  queue: node('div', 'queue-view', doc.body) };
const PANE_OF = { global: 'timeline', cell: 'timeline', row: 'timeline', reference: 'reference', queue: 'queue' };
const lit = () => bar.children.filter((c) => c.classList.contains('active')).map((c) => c.getAttribute('id') || '?').join(' ');
const shown = () => Object.entries(PANES).filter(([, p]) => p.style.display !== 'none').map(([k]) => k).join(' ');

console.log('\n[1] a pick lights its tab, shows its pane and is the state - from every tab to every tab');
for (const from of Object.keys(BUTTONS)) {
  for (const to of Object.keys(BUTTONS)) {
    pickHistoryTab(from);
    pickHistoryTab(to);
    eq(`T1 ${from} -> ${to}: lit · shown · state`, `${lit()} · ${shown()} · ${state.activeHistoryTab}`,
      `tab-${to} · ${PANE_OF[to]} · ${to}`);
  }
}
pickHistoryTab('queue');
pickHistoryTab('cell');   // its button is off the row: no crash, its pane and its state
eq('T1b the off-row Cell tab shows the timeline and is the state', `${shown()} · ${state.activeHistoryTab}`, 'timeline · cell');

console.log('\n[2] a tab added to the ROW is covered without touching the seat');
{
  const fifth = doc.createElement('button');
  bar.appendChild(fifth);
  fifth.classList.add('active');           // the seat was not told about it
  pickHistoryTab('row');
  eq('T2 a pick turns the row\'s other tabs off', lit(), 'tab-row');
  fifth.remove();
}

console.log('\n[3] PROPERTY: nothing outside this seat lights a tab, shows a pane or sets the tab state');
{
  const dir = new URL('../src/', import.meta.url);
  // [what, a line outside the seat that does it, the seat's own line - the canary]
  const RULES = [
    ['a tab button\'s mark', /tab(Global|Cell|Row|Reference|Queue)Btn[^;]*classList/, /classList\.toggle\('active'/],
    ['the tab state', /activeHistoryTab\s*=(?!=)/, /activeHistoryTab\s*=(?!=)/],
    ['a pane\'s display', /(timelineContainer|referenceView|queueView)[^;]*\.style\.display\s*=(?!=)/, /\.style\.display\s*=(?!=)/],
  ];
  const seat = readFileSync(new URL('history_tabs.js', dir), 'utf8').split('\n');
  for (const [what, re, canary] of RULES) {
    const hits = [];
    for (const name of readdirSync(dir)) {
      if (!name.endsWith('.js') || name === 'history_tabs.js') continue;
      for (const line of readFileSync(new URL(name, dir), 'utf8').split('\n')) if (re.test(line)) hits.push(`${name}: ${line.trim()}`);
    }
    eq(`T3 ${what} is set nowhere else`, hits.length, 0);
    if (hits.length) hits.slice(0, 5).forEach((h) => console.log(`       ${h}`));
    // 카나리아: 이 훑기가 «아무것도 못 짚는» 상태면 위 0 은 뜻이 없다 — 좌석 자신의 줄은 짚혀야 한다
    eq(`T3b CANARY: the scan for ${what} sees the seat's own line`, seat.some((line) => canary.test(line)), 'true');
  }
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
