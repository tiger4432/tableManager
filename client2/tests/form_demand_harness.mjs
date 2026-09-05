// FORM DEMAND — 빈 선언에서 폼이 «무엇을 요구하는지» 말하는가.
//
// The subject is imported (owner, 2026-09-02: 잘라쓰기 하니스 절대 금지). Pure module.
//
// 🔴 THE THREE THIS FILE EXISTS FOR:
//   ① 🔴 THE DOOR. A NEW declaration has no plan rows -- that is what new means -- and
//      every box drew bare, so nobody could start a source from nothing. The skeleton
//      knew `required` all along and was never asked once the plan came up empty.
//   ② 「계획이 아직 안 옴」 is not 「계획이 비었음」. The first has no answer yet; the
//      second is the normal state of every new declaration. Reading one as the other
//      either hides the form or claims a demand nobody stated.
//   ③ 🔴 A SHAPE THIS SCREEN CANNOT READ IS A FAULT, NOT A REASON TO DRAW A TEXT BOX.
//      A box under an unknown shape accepts anything, and used to be indistinguishable
//      from a field that simply does not apply -- which is normal.
//
// Run: node client2/tests/form_demand_harness.mjs
import { demandState, PLAN_UNREAD, SHAPE_MISSING } from '../src/form_demand.js';

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
const shaped = (extra) => demandState({ hasShape: true, planLoaded: true, ...extra });

// ═══ ① 넷이 넷 ═════════════════════════════════════════════════════════════════════
console.log('\n[1] four sources, and none of them is another');
{
  eq('a planned box is spoken for by the plan', shaped({ planned: true }).source, 'plan');
  eq('an unplanned one falls to the skeleton',
    shaped({ planned: false, required: true }).source, 'skeleton');
  eq('a plan that has not arrived is neither',
    demandState({ hasShape: true, planLoaded: false, planned: false }).source, 'unread');
  eq('a shape this screen cannot read is a fault',
    demandState({ hasShape: false, planLoaded: true, planned: false }).source, 'broken');
  ok('the four are four distinct sources', new Set([
    shaped({ planned: true }).source,
    shaped({ planned: false }).source,
    demandState({ hasShape: true, planLoaded: false }).source,
    demandState({ hasShape: false }).source,
  ]).size === 4);
}

// ═══ ② 「안 옴」과 「비었음」 ═══════════════════════════════════════════════════════════
console.log('\n[2] not-yet-arrived is not empty, and empty is normal');
{
  eq('an unarrived plan says 「모름」',
    demandState({ hasShape: true, planLoaded: false }).text, PLAN_UNREAD);
  // 🔴 ② The empty plan is the NEW-declaration case and must not read as an error.
  ok('an empty plan does not say 「모름」',
    shaped({ planned: false, required: true }).text !== PLAN_UNREAD);
  ok('...it states the demand instead', shaped({ planned: false, required: true }).text === '필수');
  eq('an optional field says so', shaped({ planned: false, required: false }).text, '선택');
  // 「required unknown」 is a third thing again: the skeleton did not say.
  eq('a field whose demand the skeleton never stated says THAT',
    shaped({ planned: false }).text, '요구 · 모름');
  ok('...and does not wear the colour of a stated demand',
    shaped({ planned: false }).tone !== shaped({ planned: false, required: true }).tone);
  ok('a planned box adds no chip of its own -- the plan already owns that column',
    shaped({ planned: true }).text === '');
}

// ═══ ③ 고장은 계획 유무로 가려지지 않는다 ═══════════════════════════════════════════════
console.log('\n[3] a broken shape wins over everything else');
{
  eq('...even when the plan speaks for the path',
    demandState({ hasShape: false, planLoaded: true, planned: true }).source, 'broken');
  eq('...even when the plan has not arrived',
    demandState({ hasShape: false, planLoaded: false }).source, 'broken');
  eq('...and it says so in its own words',
    demandState({ hasShape: false }).text, SHAPE_MISSING);
  ok('...in the loudest tone on the row',
    demandState({ hasShape: false }).tone === 'danger');
  // If this ever ranked below the plan check, a broken shape would read as a normal
  // planned box and the fault would be invisible again.
  ok('broken is not the same source as plan',
    demandState({ hasShape: false, planned: true }).source !== 'plan');
}

// ═══ ④ 모르는 것을 「아니오」로 읽지 않는다 ═══════════════════════════════════════════════
console.log('\n[4] unknown is never read as no');
{
  eq('a non-boolean required is not read as optional',
    shaped({ planned: false, required: 'yes' }).text, '요구 · 모름');
  eq('...nor as required', shaped({ planned: false, required: 1 }).text, '요구 · 모름');
  eq('a missing planLoaded defaults to arrived, which is what the caller passes',
    demandState({ hasShape: true, planned: false, required: true }).source, 'skeleton');
  eq('a missing hasShape is not read as broken',
    demandState({ planLoaded: true, planned: true }).source, 'plan');
  eq('no facts at all still answers', demandState().source, 'skeleton');
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
