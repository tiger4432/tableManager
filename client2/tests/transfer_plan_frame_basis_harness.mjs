// S-9b — 「이 계획이 «왜 이 프레임인가»」가 화면에 닿나.
//
// 🔴 대상을 «import 합니다». `transfer_plan.js` 는 모듈 최상단에서 DOM 도 CSS 도 안 건드려
//    node 가 그대로 읽습니다 — 그래서 새 모듈을 만들지 않고 판정 함수 «하나»를 export 했습니다.
// 🔴 재는 것은 «문구»가 아니라 «가름»입니다: 확정으로 고른 코어와 역할 순서로 «물러난» 코어가
//    같은 픽셀이면 안 되고, 「모른다」가 「확정이다」로 읽혀서도 안 됩니다.
// ⚠️ 서버 절반(`server/transfer_plan.py` 의 `by_core[].frame_basis`)은 여기서 «못 잽니다» —
//    DB 가 필요합니다. 이 하니스가 재는 것은 「그 칸이 오면 화면이 무엇을 말하나」이고,
//    그 칸이 «실제로 오나»는 보고에 «따로» 적습니다.
//
// Run: node client2/tests/transfer_plan_frame_basis_harness.mjs
import { frameBasisNote } from '../src/transfer_plan.js';

let pass = 0, fail = 0;
const failed = [];
function ok(cond, name) {
  if (cond) { pass++; console.log(`  OK   ${name}`); }
  else { fail++; failed.push(name); console.log(`  BAD  ${name}`); }
}

// 🔴 TOTAL BY CONSTRUCTION, AND THAT IS THE POINT OF THE WRAPPER. A subject that THROWS
//    kills the run at the first call and every assertion after it silently never executes —
//    which is how two different mutants came back as the same finding twice today. A throw
//    is recorded as a value that no assertion accepts, so the run keeps scoring.
function fbn(summaries) {
  try { return frameBasisNote(summaries); }
  catch (e) { return `<<threw: ${e && e.message}>>`; }
}

const ROLES = ['core_defect_map', 'core_area_map'];
const fellCore = (id, reason = 'not_declared') => ({
  core_id: id, frame_basis: { kind: 'role_order', reason, roles: ROLES },
});
const firmCore = (id) => ({
  core_id: id, frame_basis: { kind: 'confirmation', confirmation_uid: 'u1', version: 3 },
});
const note = (...cores) => fbn([{ by_core: cores }]);

console.log('-- the round\'s sentence ----------------------------------------------');
// 🔴 ㉠ The two rows differ in the ONE field. If the judgement read anything else they would
//    come out the same -- which is the defect this round closes.
ok(note(fellCore('L1|1')) !== '', 'A1 a core that fell back to role order SAYS so');
ok(note(firmCore('L1|1')) === '', 'A2 ...and a core the confirmation picked is silent');
ok(note(fellCore('L1|1')) !== note(firmCore('L1|1')),
  'A3 the two are drawn DIFFERENTLY, which is the whole round');
// 🔴 A REAL CONTROL, NOT A TAUTOLOGY. A2 must be silence BY DECISION, not because the
//    fixture was unreadable. Same object, `kind` flipped and nothing else: it speaks.
const firmFlipped = firmCore('L1|1');
firmFlipped.frame_basis = { ...firmFlipped.frame_basis, kind: 'role_order' };
ok(note(firmFlipped) !== '',
  'A4 CONTROL: the confirmed fixture IS read — flipping only its `kind` makes it speak');

console.log('\n-- the server\'s words, printed rather than translated ----------------');
// ⛔ The file's own rule (`inactiveSubtractionsOf`): do not translate a token the operator
//    has to find in config, or the screen's spelling and the config's spelling diverge.
ok(note(fellCore('L1|1')).includes('not_declared'),
  'B1 the server\'s `reason` is printed verbatim');
ok(note(fellCore('L1|1', 'mapping_unavailable')).includes('mapping_unavailable'),
  'B2 ...whatever the reason is — the screen does not choose it');
ok(ROLES.every(r => note(fellCore('L1|1')).includes(r)),
  'B3 the server\'s `roles` are printed verbatim, in the server\'s order');
ok(note(fellCore('L1|1')).includes('role_order'),
  'B4 and the kind keeps the server\'s spelling, so there is no second word for it');

console.log('\n-- 「전부」 must not overclaim -----------------------------------------');
ok(note(fellCore('L1|1'), fellCore('L1|2')).includes('전부'),
  'C1 every core on one reason reads 「전부」 rather than a list');
ok(!note(fellCore('L1|1'), fellCore('L1|2')).includes('L1|1'),
  'C2 ...and then the ids are NOT listed (a footnote that lists is the 주저리주저리)');
const mixed = note(fellCore('L1|1'), firmCore('L1|2'));
ok(!mixed.includes('전부') && mixed.includes('L1|1'),
  'C3 a mixed response names the fallen core instead of claiming 전부');
ok(!mixed.includes('L1|2'), 'C4 ...and does not name the core that was confirmed');
// 🔴 THE ONE THAT COST A REVISION. A core that did not ANSWER is not a core that was
//    confirmed. Counting only answering cores made 「전부」 true of a set the operator reads
//    as every core.
const withUnknown = note(fellCore('L1|1'), fellCore('L1|2'),
                         { core_id: 'AREA-7', core_lot: null, core_slot: null, frame_basis: null });
ok(!withUnknown.includes('전부'),
  'C5 an unanswered core stops 「전부」 — it is unknown, not confirmed');
ok(withUnknown.includes('L1|1') && withUnknown.includes('L1|2'),
  'C6 ...and the fallen cores are named instead');
ok(!withUnknown.includes('AREA-7'),
  'C7 ...while the unanswered core is not named as fallen, which would be inventing a fact');
// Two reasons is not one sentence either.
const twoWhy = note(fellCore('L1|1'), fellCore('L1|2', 'mapping_unavailable'));
ok(!twoWhy.includes('전부') && twoWhy.includes('not_declared')
   && twoWhy.includes('mapping_unavailable'),
  'C8 two different reasons are kept apart rather than folded into one word');

console.log('\n-- silence: the states that must draw nothing -------------------------');
ok(fbn([{ by_core: [] }]) === '', 'D1 no cores — nothing');
ok(fbn([{}]) === '', 'D2 an older server that sends no by_core — nothing');
ok(fbn([null]) === '', 'D3 a summary that failed — nothing');
ok(fbn([]) === '' && fbn(null) === '',
  'D4 no summaries at all — nothing, and no throw');
ok(note({ core_id: 'AREA-7', frame_basis: null }) === '',
  'D5 the area-map path (opaque core, no lot/slot) draws nothing — null is 「모른다」');
ok(note({ core_id: 'L1|1' }) === '',
  'D6 an older server that sends by_core WITHOUT the key draws nothing');
ok(note({ core_id: 'L1|1', frame_basis: { kind: null } }) === '',
  'D7 an unreadable kind draws nothing rather than guessing which side it was on');

console.log('\n-- more than one pool: the note is one, gathered in one place ---------');
const twoPools = fbn([{ by_core: [fellCore('L1|1')] }, { by_core: [firmCore('L2|1')] }]);
ok(twoPools.includes('L1|1') && !twoPools.includes('L2|1'),
  'E1 pools are unioned, and only the fallen cores are named');
ok(!twoPools.includes('전부'),
  'E2 ...and a confirmed core in ANOTHER pool still stops 「전부」');

console.log(`\n${pass} passed, ${fail} failed.`);
if (fail) console.error(`failed:\n  ${failed.join('\n  ')}`);
console.log(`ASSERTIONS ${pass + fail} ${fail}`);
process.exit(fail ? 1 : 0);
