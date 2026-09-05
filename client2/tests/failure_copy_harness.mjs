// FAILURE COPY — 실패했을 때만 보이는 문구의 «모양»을 붙잡습니다.
//
// 🔴 왜 하니스인가: 이 문구들은 «망가진 동안에만» 화면에 나옵니다. 오늘 어드민에서 다섯을
//    잡은 방법(도는 화면 읽기)이 여기서는 «안 통합니다» — 그 상태를 이 상자에서 만들 수
//    없습니다. 계약도 하니스도 이 문자열들을 재지 않았습니다. 그래서 「적용 52건」이
//    검증 없이 착지하고 «조용히 되돌아갈» 수 있는 자리였습니다.
//
// ⚠️ 텍스트가 «대상»인 하니스입니다 (CLAUDE.md 2026-09-03 예외). 동작을 재려고 텍스트를
//    «대리»로 쓰는 것이 아니라, 「문구가 어떤 모양으로 쓰였나」 자체가 주어입니다.
//    그래서 모양이 바뀌면 빨개지는 것이 여기서는 «병이 아니라 기능»입니다.
//
// 🔴 그리고 단언은 «모양 수»만큼입니다. 문자열 55개를 단언하지 않습니다 — 그러면 문구를
//    한 번 다듬을 때마다 55개가 빨개지고, 그건 오늘 이 저장소가 이미 한 번 치른 값입니다.
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

// The three files behind index.html and map_editor.html -- the pages whose failure copy
// has never been through the rule.
const FILES = ['src/main.js', 'src/map_editor.js', 'src/transfer_plan.js'];
const HANGUL = /[가-힣]/;
const SENTENCE = /(습니다|합니다|하십시오|하세요|해주세요|입니다)/;
const FAILURE = /(실패|없음|없습니다|불가|오류|에러|거부|끊|안 |못 |unavailable|failed|error)/;
// 🔴 IMPERATIVE ONLY. An earlier count matched 「확인」/「시도」 anywhere, which also fires
//    inside a REASON ("확인 중"), and over-counted this bucket by two. The verb ending is
//    what makes a clause an instruction.
const IMPERATIVE = /(하십시오|하세요|해 ?주세요)/;

function strings(file) {
  const text = readFileSync(new URL(`../${file}`, import.meta.url), 'utf8');
  const out = [];
  for (const m of text.matchAll(/['"`]([^'"`\n]{6,160})['"`]/g)) out.push(m[1]);
  return out;
}
const all = FILES.flatMap(strings);
const failureCopy = [...new Set(all.filter(
  (s) => HANGUL.test(s) && SENTENCE.test(s) && !s.includes('·') && FAILURE.test(s)))];

// ═══ ① 계기가 «눈이 멀지» 않았는지 ═══════════════════════════════════════════════════
//
// 🔴 THE VACUOUS PASS IS THE REAL RISK HERE. A scanner that finds nothing passes every
//    assertion below it, and a regex broken by a refactor looks exactly like clean copy.
//    So the population is asserted before anything is asserted ABOUT the population.
console.log('\n[1] the instrument can still see');
{
  ok('the three files are read at all', all.length > 200, `saw ${all.length}`);
  ok('and failure copy is found in them', failureCopy.length > 10,
    `saw ${failureCopy.length}`);
  // The classifier itself must fire on a control, or 「0 found」 means nothing.
  ok('the imperative test fires on an instruction',
    IMPERATIVE.test('다시 시도해 주세요'));
  ok('...and does not fire on a bare reason',
    !IMPERATIVE.test('확인 중에 실패했습니다'));
}

// ═══ ② 모양 A+C — 사유 + «행동»이 한 문장으로 붙어 있지 않다 ═══════════════════════════
//
// 전례: 오늘 어드민의 실패 다섯 (975f9024) -> 「토큰 거부 · 새로고침 후 재입력」
// 상태는 «명사», 행동은 «옆에», 가르는 것은 「·」. 행동은 «지우지 않습니다» -- 지우면
// 짧아진 것이 아니라 운영자가 갈 곳을 잃습니다.
console.log('\n[2] shape A+C: a reason and an instruction are not one sentence');
{
  const withAction = failureCopy.filter((s) => IMPERATIVE.test(s));
  eq('no failure line carries an imperative clause in sentence form',
    withAction, []);
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
