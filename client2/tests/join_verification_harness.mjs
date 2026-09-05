// JOIN VERIFICATION — 한 낱말 옆에 «진단»이 붙는지, 그리고 넷이 넷인지.
//
// The subject is imported (owner, 2026-09-02: 잘라쓰기 하니스 절대 금지). Pure module.
//
// 🔴 THE THREE THIS FILE EXISTS FOR:
//   ① 「거절」과 「진단 못 냄」은 다르다. 앞은 DDL 한 줄이 답이고 뒤는 답이 «아직 없다»는
//      뜻이다. 합치면 운영자가 고칠 자리를 잃는다.
//   ② 문장은 서버의 것이다. 여기서 지으면 같은 거부가 두 화면에서 다른 문장으로 나오고,
//      「서버가 문장의 정본」이라는 계약이 그 순간 깨진다 -- 서버 소스가 그렇게 적는다.
//   ③ 모양에서 떨어진 선언(`invalid`)은 거절의 다른 «인구»이지 다른 «상태»가 아니다.
//      세는 곳에서 빠지면 「거절 0」이 되고, 그건 참이 아니다.
//
// Run: node client2/tests/join_verification_harness.mjs
import { joinVerificationView, JOIN_UNREAD } from '../src/join_verification.js';

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

// Shapes copied from `virtual_join_config.verification_report`'s own return statement.
const OK_ROW = { name: 'lot_to_wafer', left_table: 'l', right_table: 'w',
                 join_key: ['lot_id = lot_id'], folded_join_key: [], expose: ['x'],
                 accepted: true, unique_index: 'uq_w_lot', required_index: 'uq_w_lot',
                 required_index_ddl: null, detail: null };
const BAD_ROW = { name: 'wafer_to_die', left_table: 'w', right_table: 'd',
                  join_key: ['wafer_id = wafer_id'],
                  folded_join_key: [{ left: 'wafer_id', right: 'wafer_id',
                                      rules: ['case', 'space'] }],
                  expose: [], accepted: false, unique_index: null,
                  required_index: 'uq_d_wafer',
                  required_index_ddl: 'CREATE UNIQUE INDEX uq_d_wafer ON d (wafer_id)',
                  detail: 'd 의 조인 키를 덮는 UNIQUE 인덱스가 없습니다' };
const REPORT = { declarations: [OK_ROW, BAD_ROW], accepted: 1, refused: 1,
                 invalid: [{ subject: 'broken_rule', detail: '오른쪽 표가 선언에 없습니다' }] };

// ═══ ① 네 상태 ═════════════════════════════════════════════════════════════════════
console.log('\n[1] four states, and the last two are not one');
{
  const v = joinVerificationView(REPORT);
  eq('an approved declaration says so', v.rows[0].state, 'accepted');
  eq('a refused one says so', v.rows[1].state, 'refused');
  eq('nothing fetched yet is neither', joinVerificationView(null).read, false);
  eq('...and says the word for 「모름」', joinVerificationView(null).text, JOIN_UNREAD);
  eq('a failed fetch is also 「모름」, not 「거절」',
    joinVerificationView(REPORT, { failed: 'HTTP 401' }).read, false);
  ok('...and keeps the reason, so the operator knows what to fix',
    joinVerificationView(REPORT, { failed: 'HTTP 401' }).reason === 'HTTP 401');

  // 🔴 ① REFUSED WITHOUT A DIAGNOSIS IS ITS OWN STATE. Drawing it as 「거절」 would promise
  //    a fix that is not on the row; drawing it as 「통과」 would be a lie.
  const bare = joinVerificationView(
    { declarations: [{ ...BAD_ROW, required_index_ddl: null, detail: null }] });
  eq('refused with nothing to act on is undiagnosed', bare.rows[0].state, 'undiagnosed');
  const noFlag = joinVerificationView({ declarations: [{ name: 'x' }] });
  eq('a row with no verdict at all is not read as refused', noFlag.rows[0].state, 'undiagnosed');
  ok('the two refusal shapes are not the same state',
    joinVerificationView(REPORT).rows[1].state !== bare.rows[0].state);
}

// ═══ ② 「무엇을 바꾸나」가 실제로 실린다 ═══════════════════════════════════════════════
console.log('\n[2] the fix travels, in the server\'s words');
{
  const v = joinVerificationView(REPORT);
  eq('the DDL to create is carried verbatim', v.rows[1].ddl, BAD_ROW.required_index_ddl);
  eq('...and the server\'s sentence too', v.rows[1].detail, BAD_ROW.detail);
  ok('an approved row carries neither -- there is nothing to do',
    v.rows[0].ddl === '' && v.rows[0].detail === '');

  // 🔴 The fold is why THIS join wants a different index than its neighbours. Without it
  //    the operator cannot tell why the DDL looks unfamiliar.
  ok('folding is said out loud', v.rows[1].folded.length === 1
    && v.rows[1].folded[0].includes('wafer_id') && v.rows[1].folded[0].includes('case'));
  eq('a join with no folding says nothing about folding', v.rows[0].folded, []);

  // The key is already assembled server-side as `left = right`; re-assembling it here
  // would be a second spelling of one fact.
  eq('the join key is carried, not rebuilt', v.rows[1].joinKey, ['wafer_id = wafer_id']);
}

// ═══ ③ 세는 것은 «둘 다» 센다 ═══════════════════════════════════════════════════════
console.log('\n[3] the counts include the declarations that never became rules');
{
  const v = joinVerificationView(REPORT);
  eq('shape-level rejections are carried', v.invalid.length, 1);
  eq('...with their own sentence', v.invalid[0].detail, '오른쪽 표가 선언에 없습니다');
  ok('...and named, so it can be found in the file',
    v.invalid[0].subject === 'broken_rule');
  // 🔴 ③ If `invalid` is left out of the count the line reads 「거절 1」 while two things
  //    are broken.
  eq('the refused count includes them', v.text, '승인 1 · 거절 2');
  eq('a clean report says so', joinVerificationView(
    { declarations: [OK_ROW], accepted: 1, refused: 0, invalid: [] }).text, '승인 1 · 거절 0');

  // A subject the server did not name is still drawn -- silently dropping it would make
  // a broken declaration invisible.
  const unnamed = joinVerificationView(
    { declarations: [], accepted: 0, refused: 0, invalid: [{ detail: 'x' }] });
  eq('an unnamed rejection is not dropped', unnamed.invalid.length, 1);
  ok('...and says that it has no name', unnamed.invalid[0].subject === '이름 없음');

  // Counts the server did not send are not invented.
  const noCounts = joinVerificationView({ declarations: [OK_ROW, BAD_ROW] });
  eq('absent totals fall back to what can be counted', noCounts.text, '선언 2');
  eq('...and are not filled with zero', noCounts.accepted, null);
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
