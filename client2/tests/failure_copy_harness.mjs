// FAILURE COPY — 실패했을 때만 보이는 문구의 «모양»을 붙잡습니다.
//
// 🔴 왜 하니스인가: 이 문구들은 «망가진 동안에만» 화면에 나옵니다. 어드민에서 다섯을 잡은
//    방법(도는 화면 읽기)이 여기서는 안 통합니다 — 그 상태를 이 상자에서 만들 수 없고,
//    계약도 다른 하니스도 이 문자열들을 재지 않았습니다.
//
// ⚠️ 텍스트가 «대상»인 하니스입니다 (CLAUDE.md 2026-09-03 예외). 동작을 재려고 텍스트를
//    «대리»로 쓰는 것이 아니라 「문구가 어떤 모양인가」 자체가 주어입니다.
//
// ═══ 🔴 이 파일의 모집단이 «두 번» 틀렸습니다. 둘 다 여기 적어 둡니다 ═══
//
// ① 첫 판: 모집단에 «문장형»이 들어 있었습니다 -> 모양 D 를 고치면 모집단이 «비고»,
//    아래 가드가 실패하며 나머지 단언이 «공허하게 참»이 됩니다. 가드를 그 이유로 넣어 놓고
//    모집단을 정하는 줄에서 같은 실수를 했습니다.
// ② 둘째 판: 「실패스러움」이 「없음」·「안」을 잡았습니다 -> 라벨 · 툴팁 · «성공» 메시지가
//    섞였습니다. 그 58 을 실패 규칙으로 고쳤으면 «맞는 문장을 틀린 규칙으로» 부쉈습니다.
//
// 🔴 그래서 지금 모집단은 «실패에만 나오는 낱말»로 좁혔고, 그 결과는 «전부»가 아니라 «바닥»입니다.
//    아래 NOTE 가 그 대가를 수로 답니다 — 「안 봐서 0」과 「없어서 0」은 다릅니다.
//
// ⏭ 이 축을 «실제로 닫을» 계기는 문자열이 아니라 «호출 자리»입니다 — 그 문자열이
//    `showToast(…, 'error')` 나 거절 경로로 «나가는가». 그것이 있어야 상한이 잡힙니다.
//
// Run: node client2/tests/failure_copy_harness.mjs
import { readFileSync } from 'node:fs';

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

const FILES = ['src/main.js', 'src/map_editor.js', 'src/transfer_plan.js'];
const HANGUL = /[가-힣]/;
// 🔴 실패에만 나오는 낱말. 「없음」·「안」은 «뺐습니다» — 보통 문구가 늘 씁니다.
const FAILURE = /(실패|오류|에러|거부|불가|failed|error|unavailable)/;
// ⚠️ 넓은 그물. 고치는 데 «안 씁니다» — 「안 본 것」의 크기를 재는 데만 씁니다.
const WIDE = /(실패|없음|없습니다|불가|오류|에러|거부|끊|안 |못 |unavailable|failed|error)/;
const IMPERATIVE = /(하십시오|하세요|해 ?주세요)/;
const DASH_JOINT = / [—―] /;

function strings(file) {
  const text = readFileSync(new URL(`../${file}`, import.meta.url), 'utf8');
  return [...text.matchAll(/['"`]([^'"`\n]{6,160})['"`]/g)].map((m) => m[1]);
}
const all = FILES.flatMap(strings);
const korean = [...new Set(all.filter((s) => HANGUL.test(s)))];
const failureCopy = korean.filter((s) => FAILURE.test(s));
const wideNet = korean.filter((s) => WIDE.test(s));

// ═══ ① 계기가 «눈이 멀지» 않았는지 ═══════════════════════════════════════════════════
//
// 🔴 A SCANNER THAT FINDS NOTHING PASSES EVERYTHING BELOW IT. The population is asserted
//    before anything is asserted ABOUT it -- and it is a population the fixes do NOT
//    shrink: 「실패」 stays in the string after its shape is corrected, which is exactly
//    what the first version of this file got wrong.
console.log('\n[1] the instrument can still see');
{
  ok('the three files are read at all', all.length > 200, `saw ${all.length}`);
  ok('failure copy is found, and fixing a shape does not shrink this',
    failureCopy.length > 40, `saw ${failureCopy.length}`);
  ok('the imperative test fires on an instruction', IMPERATIVE.test('다시 시도해 주세요'));
  ok('...and not on a bare reason', !IMPERATIVE.test('확인 중에 실패했습니다'));
}

// ═══ ② 모양 A+C — 사유 + «행동»이 한 문장으로 붙어 있지 않다 ═══════════════════════════
console.log('\n[2] shape A+C: a reason and an instruction are not one sentence');
{
  eq('no failure line carries an imperative clause in sentence form',
    failureCopy.filter((s) => IMPERATIVE.test(s)), []);
}

// ═══ ③ 모양 B — 사유 다음에 그 결과를 다시 말하지 않는다 ═══════════════════════════════
//
// ⚠️ 결과를 «지우는» 것이 아니라 «마디»로 가릅니다 — 「이것이 무엇을 막는가」는 씁니다.
console.log('\n[3] shape B: a reason does not restate its own consequence');
{
  eq('no failure line joins its consequence with a dash',
    failureCopy.filter((s) => DASH_JOINT.test(s)), []);
}

// ⏸ 모양 D 는 «보류»입니다 — 단언을 여기 넣으면 `valid_die_frame_adoption_harness` 와
//    «동시에 초록일 수 없습니다». 그 하니스는 map_editor.js 를 «잘라내어» vm 에서 돌리고,
//    제 문구 수정이 그 잘라내는 자리를 바꿉니다(단일 편집으로는 재현 안 됨 — 집계 텍스트가
//    자릅니다). HEAD 13 · 제 판 14. 총괄 판정 대기.

// ═══ ⑤ 🔴 이 계기가 «안 본» 것의 크기 — 단언이 아니라 «기록»입니다 ═══════════════════
console.log('\n[5] what this instrument does NOT look at');
console.log(`  NOTE wide net ${wideNet.length} · narrowed ${failureCopy.length}`
  + ` · unexamined ${wideNet.length - failureCopy.length}`);
console.log('  NOTE a FLOOR, not a total. The ceiling needs a call-site scan.');

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
