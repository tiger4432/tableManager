// PICKUP STATE — 「집는 이가 살아 있나」가 첫 줄인지, 그리고 수를 «누가» 셌는지.
//
// The subject is imported (owner, 2026-09-02: 잘라쓰기 하니스 절대 금지). Pure module.
//
// 🔴 THE FOUR THIS FILE EXISTS FOR:
//   ① 「집은 적 없음」 is not 「0초 전」. Drawing a queue nothing has ever picked up as a
//      fresh pickup is the exact inversion of the fact the operator needs.
//   ② 🔴 THE COUNT IS THE SERVER'S. The list is newest-first and can be truncated, so a
//      screen that measures `waiting.length` reports FEWER than are waiting - and the
//      truncation is invisible, which is what makes the wrong number believable.
//   ③ 🔴 NO INVENTED THRESHOLD. This file must not decide 「늦음」; it carries the age and
//      the interval, both with units. A verdict here would be a rule nobody declared.
//   ④ `unknown` IS NOT `orphaned`. The server says a run on an unreachable process is
//      undecidable; calling it orphaned is how "never finishes" becomes "two at once".
//
// Run: node client2/tests/pickup_state_harness.mjs
import { pickupState, ageText, PICKUP_UNREAD } from '../src/pickup_state.js';

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

// Keys copied from `retroactive.queue_view`'s own return statement.
const LIVE = {
  last_pickup_at: '2026-09-05T14:00:00+00:00', last_pickup_age_seconds: 3.0,
  picker_interval_seconds: 5.0, waiting_count: 2,
  waiting: [{ run_id: 'r1', op: 'replay', requested_by: 'kim',
              queued_at: '2026-09-05T13:59:57+00:00', waiting_seconds: 3.0 },
            { run_id: 'r2', op: 'resolve', requested_by: 'kim',
              queued_at: '2026-09-05T13:59:58+00:00', waiting_seconds: 2.0 }],
  orphaned: [],
};
const STALLED = { ...LIVE, last_pickup_age_seconds: 320.5, waiting_count: 1,
                  waiting: [LIVE.waiting[0]] };

// ═══ ① 집기의 세 상태 ═══════════════════════════════════════════════════════════════
console.log('\n[1] never picked up is not just-picked-up');
{
  eq('a recent pickup says how long ago', pickupState(LIVE).pickup, '마지막 집기 · 3초 전');
  eq('an old one says the same way, in its own unit',
    pickupState(STALLED).pickup, '마지막 집기 · 5분 전');
  // 🔴 ① The inversion this guards.
  eq('a queue nothing ever picked up says THAT',
    pickupState({ ...LIVE, last_pickup_at: null, last_pickup_age_seconds: null }).pickup,
    '집은 적 없음');
  ok('...and does not read as a fresh pickup',
    !pickupState({ ...LIVE, last_pickup_at: null }).pickup.includes('0초'));
  eq('a stamp with no age is 「모름」, not zero',
    pickupState({ ...LIVE, last_pickup_age_seconds: null }).pickup, PICKUP_UNREAD);
  eq('nothing fetched at all is 「모름」 too, and says it is unread',
    pickupState(null).read, false);
}

// ═══ ② 임의 임계 없음 — 기준을 «같이» 낸다 ══════════════════════════════════════════
console.log('\n[2] no invented verdict, and the basis travels with the number');
{
  // 🔴 ③ Neither a live nor a stalled queue gets a word this file made up.
  for (const [label, q] of [['live', LIVE], ['stalled', STALLED]]) {
    const v = pickupState(q);
    ok(`${label}: no verdict word is invented`,
      !/멈춤|늦음|정상|죽음/.test(v.pickup + v.basis));
  }
  eq('the declared interval is carried, with its unit', pickupState(LIVE).basis, '주기 5초');
  ok('...so the age has something to be read against',
    pickupState(STALLED).basis === '주기 5초');
  eq('an absent interval draws no basis rather than a made-up one',
    pickupState({ ...LIVE, picker_interval_seconds: null }).basis, '');
  // The unit switches so the number stays readable; the fact does not change.
  eq('seconds stay seconds', ageText(45), '45초');
  eq('minutes become minutes', ageText(320.5), '5분');
  eq('hours become hours', ageText(7200), '2시간');
  eq('an absent duration draws nothing', ageText(null), '');
}

// ═══ ③ 수는 서버가 센다 ════════════════════════════════════════════════════════════
console.log('\n[3] the count is the server\'s, and truncation is said out loud');
{
  eq('the waiting count comes from the server', pickupState(LIVE).waiting, 2);
  eq('...and reads as one number when the list is whole',
    pickupState(LIVE).waitingText, '대기 2');
  // 🔴 ② The list is newest-first and capped. Measuring it would under-report.
  const capped = { ...LIVE, waiting_count: 40 };
  eq('a truncated list does not become the count', pickupState(capped).waiting, 40);
  eq('...and the screen says both numbers', pickupState(capped).waitingText,
    '대기 40 · 목록 2');
  eq('...and marks itself truncated', pickupState(capped).truncated, true);
  eq('a whole list is not marked truncated', pickupState(LIVE).truncated, false);
  eq('a missing count is 「모름」, not 0',
    pickupState({ ...LIVE, waiting_count: null }).waitingText, PICKUP_UNREAD);
  eq('...and stays null rather than becoming a number',
    pickupState({ ...LIVE, waiting_count: null }).waiting, null);
}

// ═══ ④ 어긋난 행 — 판정은 서버의 것 ═══════════════════════════════════════════════════
console.log('\n[4] running with no owner, decided by the heartbeat and not here');
{
  const withOrphan = { ...LIVE, orphaned: [
    { run_id: 'r9', op: 'replay', runner: 'sched/h/17', owner: 'orphaned',
      started_seconds: 900 },
    // 🔴 ④ `unknown` is undecidable, not dead. It must not appear.
    { run_id: 'r8', op: 'resolve', runner: '?/?/?', owner: 'unknown',
      started_seconds: 20 },
    { run_id: 'r7', op: 'replay', runner: 'sched/h/18', owner: 'owned',
      started_seconds: 5 },
  ] };
  const v = pickupState(withOrphan);
  eq('only the orphaned one is drawn', v.orphaned.map((o) => o.runId), ['r9']);
  eq('...with how long it has been running', v.orphaned[0].age, '15분');
  eq('...and what it is', v.orphaned[0].op, 'replay');
  eq('no orphans, no rows', pickupState(LIVE).orphaned, []);
  eq('an absent orphan list is not a crash',
    pickupState({ ...LIVE, orphaned: undefined }).orphaned, []);
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
