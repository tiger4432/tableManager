// APPENDED MODULE — 잘라쓰기를 대신할 «다리»가 실제로 다리인지.
//
// 🔴 이 하니스가 재는 것은 «부품 하나»가 아니라 이 저장소의 «규율»입니다:
//    대상 모듈을 잘라내지 «않고» 그 내부를 잴 수 있는가. 지금 하니스 여럿이 대상 파일을
//    텍스트로 읽어 함수를 잘라내고 vm 에 넣는데, 그건 동작이 아니라 «글자 모양»을 잽니다.
//
// 🔴 그리고 여기서 제일 중요한 단언은 「닿는다」가 아니라 «퇴화하지 않는다»입니다 —
//    사본이 원본 바이트로 «시작»하지 않으면 던져야 합니다. 그 단언이 없으면 덧붙이기는
//    조용히 잘라쓰기로 돌아가고, 그때는 아무도 모릅니다.
//
// Run: node client2/tests/appended_module_harness.mjs
import { importWithAccessors, startsWithOriginal } from './lib/appended_module.mjs';
import { readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname } from 'node:path';

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

const SRC = new URL('../src/map_editor.js', import.meta.url);
const SRC_DIR = dirname(fileURLToPath(SRC));

// ═══ ① 잘라내지 «않고» 내부에 닿는다 ═══════════════════════════════════════════════════
//
// 🔴 이 파일이 고르는 대상이 우연이 아닙니다: `map_editor.js` 는 이 저장소에서 가장 많이
//    «잘려» 온 파일이고, 잘린 이유로 기록된 것(`import './tokens.css'`)은 2026-09-05 실측
//    기준 «이미 사라졌습니다». 남은 이유는 하나뿐입니다 — 이 모듈은 아무것도 export 하지
//    않아서 밖에서 «잡을 이름»이 없습니다. 그것이 덧붙이기가 필요한 진짜 사유입니다.
console.log('\n[1] the module is reached without cutting it');
{
  const ns = await importWithAccessors(SRC,
    'export const __probe = {'
    + ' table: typeof VALID_DIE_TABLE !== "undefined" ? VALID_DIE_TABLE : null,'
    + ' hasGeometry: typeof applyPhysicalGeometry === "function",'
    + ' };');
  ok('the appended copy imports at all', !!ns);
  // 🔴 값을 «다시 적지» 않습니다 — 여기에 'valid_die_ref' 를 손으로 쓰면 그 순간 두 번째
  //    저자가 생기고, 선언이 바뀌는 날 이 하니스가 «옛 값»을 초록으로 지킵니다.
  ok('a module-level const is readable', typeof ns.__probe.table === 'string'
    && ns.__probe.table.length > 0, `saw ${JSON.stringify(ns.__probe.table)}`);
  ok('...and a module-level function too', ns.__probe.hasGeometry === true);
}

// ═══ ② 🔴 퇴화 방지 — 사본이 원본으로 «시작»하지 않으면 던진다 ═══════════════════════════
//
// 이 단언이 이 파일의 «존재 이유»입니다. 「그 import 하나만 빼면 되잖아」가 덧붙이기를
// 잘라쓰기로 되돌리는 방법이고, 그 되돌림은 조용합니다.
console.log('\n[2] it refuses to become slicing again');
{
  eq('appending keeps the prefix', startsWithOriginal('abc', 'abc\nexport const x = 1;'), true);
  eq('removing anything breaks it', startsWithOriginal('abc', 'bc\nexport const x = 1;'), false);
  eq('a middle edit breaks it too', startsWithOriginal('abc', 'axc\nexport const x = 1;'), false);
  eq('an empty copy is not a prefix of a real original', startsWithOriginal('abc', ''), false);
  // The helper must not accept a non-string and call it a match.
  eq('a missing copy is not a match', startsWithOriginal('abc', null), false);
}

// ═══ ③ 흔적을 남기지 않는다 ═══════════════════════════════════════════════════════════
//
// ⚠️ 사본은 상대 import 가 풀려야 해서 «원본 옆»에 놓입니다. 그래서 지우는 것이 규율입니다 —
//    남으면 추적 안 되는 파일이 `src/` 에 서고, 다음 사람의 git status 에 «남의 것»처럼 보입니다.
console.log('\n[3] it leaves nothing behind');
{
  const strays = readdirSync(SRC_DIR).filter((f) => f.startsWith('.appended-'));
  eq('no appended copy survives the import', strays, []);
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
