// C-9 — 「체인이 «몇 행» 냈나」가 화면에 닿나.
//
// 🔴 대상을 «import 합니다». 판정이 `websocket.js` 의 분기 안에 있으면 재려고 그리드와 DOM 을
//    통째로 세워야 합니다 — 표준 규율대로 판정만 모듈로 뺐습니다.
// 🔴 재는 것은 «가름»입니다: 「0행」(값)과 「이 서버는 그 말을 안 한다」(옛 서버)가 «같은 글자»면
//    안 됩니다. 서버가 자기 상수 옆에 「0 도 항상 실린다」고 적어 둔 이유가 그것입니다.
//
// Run: node client2/tests/chain_refresh_note_harness.mjs
import { chainRefreshNote } from '../src/chain_refresh_note.js';

let pass = 0, fail = 0;
const failed = [];
function ok(cond, name) {
  if (cond) { pass++; console.log(`  OK   ${name}`); }
  else { fail++; failed.push(name); console.log(`  BAD  ${name}`); }
}
// 던짐을 «값»으로 — 던지면 뒤 단언이 한 번도 안 돌고, 그러면 다른 결함이 같은 답으로 보입니다.
function note(msg) {
  try { return chainRefreshNote(msg); }
  catch (e) { return `<<threw: ${e && e.message}>>`; }
}
const ev = (extra) => note({ event: 'batch_refresh_required', table_name: 't', ...extra });

console.log('-- the round\'s sentence ----------------------------------------------');
ok(ev({ change_count: 12 }) !== '', 'A1 a refresh that carries a row count SAYS the count');
ok(ev({ change_count: 12 }).includes('12'), 'A2 ...and it is the server\'s number');
// 🔴 0 IS A VALUE. The sweep recovery arrives with 0, and the server says so beside its own
//    constant. Silence must mean exactly one thing, and it is not this.
ok(ev({ change_count: 0 }) !== '', 'A3 zero is a VALUE and is said');
ok(ev({ change_count: 0 }).includes('0'), 'A4 ...as the number 0, not as a word for nothing');
ok(ev({}) === '', 'A5 a message WITHOUT the key says nothing (older server)');
ok(ev({ change_count: 0 }) !== ev({}),
  'A6 so 「0 rows」 and 「this server does not say」 are not the same pixels — the whole gate');

console.log('\n-- the word is a COUNT, not a claim about change ----------------------');
// ⛔ C-9 의 사실은 「쓴 행 수」입니다. 「바꿈」은 서버가 모르는 것입니다 (C-1 의 ran:changed 와 같은 이유).
ok(!ev({ change_count: 3 }).includes('바꿈') && !ev({ change_count: 3 }).includes('변경'),
  'B1 the line does not claim anything CHANGED — the server only knows rows were written');
ok(ev({ change_count: 3 }).includes('행'),
  'B2 ...it says rows, which is the fact the server actually has');
ok(ev({ change_count: 3 }).includes('체인'),
  'B3 and it names the actor, so the operator knows which writer this number is about');

console.log('\n-- silence: what must draw nothing ------------------------------------');
ok(note(null) === '' && note(undefined) === '', 'C1 no message — nothing, and no throw');
ok(note('batch_refresh_required') === '', 'C2 a non-object message — nothing');
ok(ev({ change_count: null }) === '', 'C3 an explicit null is not a count');
ok(ev({ change_count: '3' }) === '',
  'C4 the STRING "3" is not coerced — coercing quietly widens the contract');
ok(ev({ change_count: NaN }) === '' && ev({ change_count: Infinity }) === '',
  'C5 NaN and Infinity are not counts');
ok(ev({ change_count: true }) === '', 'C6 a boolean is not a count');

console.log('\n-- the count is carried, not recomputed -------------------------------');
// 🔴 화면이 «세지» 않습니다. 이 메시지에는 행 목록이 없고(그것이 이 이벤트의 정의입니다),
//    세려 들면 없는 목록의 길이를 0 으로 읽게 됩니다.
ok(ev({ change_count: 7, rows: [] }).includes('7'),
  'D1 the server\'s number wins over anything the message might look countable by');
ok(ev({ change_count: 1 }).includes('1') && ev({ change_count: 1000 }).includes('1000'),
  'D2 the number is passed through rather than bucketed or capped');

console.log(`\n${pass} passed, ${fail} failed.`);
if (fail) console.error(`failed:\n  ${failed.join('\n  ')}`);
console.log(`ASSERTIONS ${pass + fail} ${fail}`);
process.exit(fail ? 1 : 0);
