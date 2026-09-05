// PLAN DRY RUN — 「왜 거절됐나」와 「무엇을 바꾸나」가 실제로 실리는지.
//
// The subject is imported (owner, 2026-09-02: 잘라쓰기 하니스 절대 금지). Pure module.
//
// 🔴 THE FOUR THIS FILE EXISTS FOR:
//   ① 「거절」·「미선언」·「앞이 막힘」은 서버가 «따로» 세는 세 버킷이고 운영자가 하는 일이
//      각각 다르다 -- 고치기 / 적기 / 앞을 먼저 풀기. 접으면 그 셋이 한 낱말로 돌아간다,
//      즉 이 항목이 없애려던 바로 그 상태로.
//   ② 컬럼은 이름만이 아니라 «어디서 왔나»다. 선언된 이름과 유도된 이름이 같아 보이면
//      지워도 되는 것과 지우면 안 되는 것이 구별되지 않는다.
//   ③ 🔴 「지우면 무엇이 유도되는지」가 이 항목의 값이다. 한 낱말이 못 하던 일.
//   ④ 「못 물어봄」은 「없음」이 아니다 -- 모델이 없어 확인 못 한 컬럼을 「없음」으로
//      그리면 멀쩡한 컬럼이 결함으로 보인다.
//
// Run: node client2/tests/plan_dry_run_harness.mjs
import { planDryRunView, DRY_RUN_UNREAD } from '../src/plan_dry_run.js';

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

const NOT_REACHED = 'binding_not_reached';
// Keys copied from `transfer_plan._role_dry_run` / `dry_run` return statements.
const OK_ROLE = {
  role: 'transfer_log', where: 'stages.bond.source.transfer_log', declared: true,
  table: 'bond_log', accepted: true, reason: null, detail: null, required: ['lot'],
  columns: { lot: { column: 'lot_id', origin: 'declared', required: true,
                    derivable: false, derived_from: null, derived_role: null,
                    exists_on_table: true, effect: null } },
  removable_declarations: [],
};
const BAD_ROLE = {
  role: 'registry', where: 'plan_store.registry', declared: true, table: 'plan_registry',
  accepted: false, reason: 'column_missing_on_table',
  detail: '선언된 `wafer_no` 가 `plan_registry` 에 없습니다', required: ['wafer'],
  columns: { wafer: { column: 'wafer_no', origin: 'declared', required: true,
                      derivable: true, derived_from: null, derived_role: null,
                      exists_on_table: false, effect: null } },
  removable_declarations: [{ role: 'wafer', would_derive: 'wafer_id' }],
};
const UNDECLARED = { role: 'source_region', where: 'plan_store.source_region',
                     declared: false, table: null, accepted: false,
                     reason: 'not_declared', detail: '선언이 없습니다', required: [],
                     columns: {}, removable_declarations: [] };
const BLOCKED = { role: 'bin_map', where: 'stages.bond.bin_map', declared: true,
                  table: null, accepted: false, reason: NOT_REACHED,
                  detail: '앞 단계가 막혀 이 바인딩에 닿지 못했습니다', required: [],
                  columns: {}, removable_declarations: [] };
const PAYLOAD = {
  config_path: '/data/config/transfer_plan_config.json',
  stages: [{ name: 'bond', target_map: {}, roles: [OK_ROLE, BAD_ROLE, BLOCKED] }],
  plan_store: [UNDECLARED],
  counts: { total: 4, accepted: 1, rejected: 1, not_declared: 1, not_reached: 1 },
  not_reached_reason: NOT_REACHED,
};

// ═══ ① 서버의 버킷 셋을 접지 않는다 ═════════════════════════════════════════════════
console.log('\n[1] refused, undeclared and blocked are three different jobs');
{
  const v = planDryRunView(PAYLOAD);
  eq('every role is carried, stages and store alike', v.roles.length, 4);
  // 🔴 STATE COMES FROM THE BOOLEANS, NEVER FROM THE REASON WORD. A blocked role and
  //    a plainly refused one are both accepted:false / declared:true, so they share a
  //    state here and are told apart by the server's own reason, which is rendered.
  //    The first version classified by reason word and the seam contract (INV-F9-7)
  //    refused it -- a client holding that list goes quiet when the server adds to it.
  eq('state is structural', v.roles.map((r) => r.state),
    ['accepted', 'refused', 'refused', 'undeclared']);
  eq('...and the server word is carried rather than classified on',
    v.roles.map((r) => r.reason),
    ['', 'column_missing_on_table', NOT_REACHED, 'not_declared']);
  eq('the counts line iterates the buckets, naming none of them here', v.text,
    'accepted 1 · rejected 1 · not_declared 1 · not_reached 1');
  // A bucket the server counted zero for does not print a zero nobody asked about.
  eq('a clean config says only what it has', planDryRunView({
    stages: [{ name: 'b', roles: [OK_ROLE] }], plan_store: [],
    counts: { total: 1, accepted: 1, rejected: 0, not_declared: 0, not_reached: 0 },
  }).text, 'accepted 1');
  // 🔴 A BUCKET THIS FILE HAS NEVER HEARD OF STILL APPEARS -- the whole point of
  //    iterating rather than mapping: the day the server adds one, the screen gains it.
  ok('an unfamiliar bucket is carried too', planDryRunView({
    stages: [], plan_store: [],
    counts: { total: 2, accepted: 1, some_future_bucket: 1 },
  }).text.includes('some_future_bucket 1'));
  eq('a role with no verdict at all is not read as refused',
    planDryRunView({ stages: [{ roles: [{ role: 'x', declared: true }] }] })
      .roles[0].state, 'unknown');
}

// ═══ ② 사유와 문장은 서버의 것 ═══════════════════════════════════════════════════════
console.log('\n[2] the named reason and the sentence, both the server\'s');
{
  const bad = planDryRunView(PAYLOAD).roles.find((r) => r.role === 'registry');
  eq('the reason keeps its code name', bad.reason, 'column_missing_on_table');
  eq('...and the sentence is verbatim', bad.detail, BAD_ROLE.detail);
  eq('...beside the address in the file', bad.where, 'plan_store.registry');
  eq('an accepted role carries no reason', planDryRunView(PAYLOAD).roles[0].reason, '');
}

// ═══ ③ 「무엇을 바꾸나」 ══════════════════════════════════════════════════════════════
console.log('\n[3] what to change - the thing one word could never say');
{
  const bad = planDryRunView(PAYLOAD).roles.find((r) => r.role === 'registry');
  eq('deleting the wrong declaration would derive this instead',
    bad.removable, [{ role: 'wafer', wouldDerive: 'wafer_id' }]);
  eq('a role with nothing to remove says nothing',
    planDryRunView(PAYLOAD).roles[0].removable, []);
  // 🔴 ② The column's ORIGIN travels with its name.
  eq('the resolved column comes with where it came from',
    bad.columns, [{ role: 'wafer', column: 'wafer_no', origin: 'declared',
                    exists: false, derivedFrom: '' }]);
  const derived = planDryRunView({ stages: [{ roles: [{ ...OK_ROLE, columns: {
    lot: { column: 'lot_id', origin: 'derived', derived_from: 'stages.bond.source.mes',
           exists_on_table: true } } }] }] }).roles[0].columns[0];
  eq('a derived column says it is derived', derived.origin, 'derived');
  ok('...and names what it came from', derived.derivedFrom === 'stages.bond.source.mes');
  // 🔴 ④ Three states, not two.
  eq('a column nothing could be asked about is neither present nor absent',
    planDryRunView({ stages: [{ roles: [{ ...OK_ROLE, columns: {
      lot: { column: 'lot_id', origin: 'declared', exists_on_table: null } } }] }] })
      .roles[0].columns[0].exists, null);
}

// ═══ ④ 못 물어봤음 ≠ 거절 ═══════════════════════════════════════════════════════════
console.log('\n[4] not asked is not refused');
{
  eq('nothing fetched says so', planDryRunView(null).read, false);
  eq('...in the word for 「모름」', planDryRunView(null).text, DRY_RUN_UNREAD);
  eq('...and draws no roles', planDryRunView(null).roles, []);
  const failed = planDryRunView(PAYLOAD, { failed: 'HTTP 401' });
  eq('a failed fetch is unread, not a verdict', failed.read, false);
  eq('...and keeps its reason', failed.reason, 'HTTP 401');
  ok('...and does not report the payload it was handed', failed.roles.length === 0);
  eq('counts are not invented when the server sent none',
    planDryRunView({ stages: [{ roles: [OK_ROLE] }] }).counts, []);
  // 🔴 AND IT FALLS BACK TO WHAT IT CAN SEE, NOT TO A ZERO. With no `counts` the server
  //    has said nothing about how many passed, and printing 「통과 0」 would be this file
  //    answering a question nobody asked it -- the same invention the counts guard above
  //    exists to stop. (This assertion was written the wrong way round first; the code
  //    was right and the expectation was the invented one.)
  eq('...and the line counts roles rather than inventing a verdict tally',
    planDryRunView({ stages: [{ roles: [OK_ROLE] }] }).text, '역할 1');
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
