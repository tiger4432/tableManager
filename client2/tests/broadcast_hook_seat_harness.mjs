// 브로드캐스트 훅의 «자리» — 판정 2026-09-22 (소유자 신고: 「대기열 떴는데 안 사라짐」).
//
// 🔴 훅은 «관찰»이다. 관찰이 «남의 조기 반환» 뒤에 앉으면, 그 가드가 막는 모든 것이
//    관찰에서도 사라진다. 계측 상설의 판별식: 「이 줄이 안 돌면 무엇이 «안» 되나」 —
//    답이 「관찰 말고 다른 것」이면 자리가 틀렸다. 그래서 자리는 «맨 처음»이다.
// ⚠️ 이 하니스가 재는 것은 «자리»다. 대기열이 실제로 다시 읽는지는 main.js 의 소비자가
//    하는 일이고, 그 조건은 «한 자리»에 있다 (센 명령은 보고서에).
import { makeDoc } from './lib/board_dom.mjs';
import { handleWebSocketMessage, onBroadcast } from '../src/websocket.js';

let pass = 0; const failures = [];
const eq = (what, got, want) => {
  if (String(got) === String(want)) { pass += 1; console.log(`  PASS ${what}`); }
  else { failures.push(what); console.log(`  FAIL ${what} -- got ${got}, want ${want}`); }
};
const ok = (what, cond, shown) => eq(what, cond ? 'true' : `false (${shown})`, 'true');

// 박스에 DOM 이 없으면 핸들러의 «뒷부분»이 터진다. 그건 이 하니스가 재는 것이 아니라서
// 감싸고, 대신 「터져도 훅은 이미 불렸나」를 단언한다 — 그게 이 자리의 성질이다.
globalThis.document = globalThis.document || makeDoc('light');
const send = (msg) => { try { handleWebSocketMessage(msg); } catch (e) { return String(e && e.message); } return ''; };

const seen = [];
const off = onBroadcast((m) => seen.push(m));

console.log('\n[게이트 ①] 지금 «안 보는 표»의 변경도 관찰에 닿는다');
{
  // state.currentTable 은 이 박스에서 비어 있다 -> 그리드 가드가 «먼저» 걸리는 바로 그 경우다.
  seen.length = 0;
  send({ event: 'row_update', table_name: 'some_other_table', row_id: 1 });
  eq('B1 a message for a table nobody is looking at still reaches the hook', seen.length, 1);
  ok('B1b ...and it is the same message, not a copy of some other one',
    seen[0] && seen[0].table_name === 'some_other_table', JSON.stringify(seen[0]));
}

console.log('\n[게이트 ①b] 그리드가 «아직 없을 때»도 닿는다');
{
  seen.length = 0;
  send({ event: 'row_update', table_name: null, row_id: 2 });
  eq('B2 no grid, no current table -- the hook still fires', seen.length, 1);
}

console.log('\n[모든 메시지] 갈래로 «일찍 끝나는» 것들도 관찰된다');
{
  // 🔴 이 셋은 각자 자기 갈래에서 return 한다. 훅이 아래에 있었을 때 «전부» 사라졌다.
  seen.length = 0;
  send({ event: 'file_ingestion_progress', table_name: 't', filename: 'f', progress: 10 });
  send({ event: 'file_ingestion_progress', run_id: 'r1', op: 'x', progress: 50 });
  send({ event: 'unknown_event_name_nobody_handles', table_name: 't' });
  eq('B3 every early-returning branch is still observed', seen.length, 3);
  // ⚠️ 그래서 인제션 «진행 틱»마다 훅이 불린다. 거르는 것은 소비자의 일이다 (보고서).
}

console.log('\n[관찰은 자기만 조용하다] 터진 훅이 다음 훅을 안 죽인다');
{
  const after = [];
  const offBad = onBroadcast(() => { throw new Error('훅이 터졌다'); });
  const offGood = onBroadcast((m) => after.push(m));
  seen.length = 0;
  const err = send({ event: 'row_update', table_name: 'x' });
  eq('B4 a throwing hook does not take the others with it', after.length, 1);
  ok('B4b ...and it does not escape into the handler', err === '' || !err.includes('훅이 터졌다'), err);
  offBad(); offGood();
}

console.log('\n[대조군] 끊으면 «안» 온다 — 계기가 아무거나 세고 있지 않다');
{
  seen.length = 0;
  off();
  send({ event: 'row_update', table_name: 'y' });
  eq('B5 CONTROL: after unsubscribing the hook is silent', seen.length, 0);
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
