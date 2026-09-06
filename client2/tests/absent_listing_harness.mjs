// ABSENT LISTING — 「없음」과 「빔」이 «다른 답»으로 나오는가.
//
// The subject is imported (owner, 2026-09-02: 잘라쓰기 하니스 절대 금지).
//
// 🔴 이 파일이 재는 «둘»은 총괄 게이트 그대로이고, «각각» 단언합니다:
//   ① 원천 경로가 «없을 때»  -> 화면이 「0개」가 아니라 「없음 + 그 경로」를 말한다
//   ② 있는데 «빈» 경우       -> «오늘과 동일». 「0개」가 «맞는» 답이다
//   두 상태가 서버에서 «같은 `data: []`» 로 오기 때문에, ②를 같이 안 재면 ①의 수리가
//   「빈 목록 전부를 없음이라 부르는」 새 거짓이 될 수 있습니다.
//
// ⛔ `body_error.errorText` 와 «합치지 않았습니다» — 부재는 `status: "success"` 이고
//    오류가 아닙니다. 그 둘을 한 함수로 접으면 「고장」과 「덜 설치됨」이 다시 같아집니다.
//
// Run: node client2/tests/absent_listing_harness.mjs
import { absentPath, LISTING_ABSENT } from '../src/absent_listing.js';
import { errorText } from '../src/body_error.js';

let pass = 0;
const failures = [];
function check(name, got, want) {
  if (got === want) { pass++; console.log(`  PASS ${name}`); }
  else {
    failures.push(name);
    console.log(`  FAIL ${name}\n        got  ${JSON.stringify(got)}\n        want ${JSON.stringify(want)}`);
  }
}

// server/listing_absence.py 가 내는 «그 모양».
const ABSENT_BODY = {
  status: 'success', data: [], state: LISTING_ABSENT,
  absent_path: 'C:/…/server/config/chain_rules.json',
};

console.log('gate 1 — an absent source names itself');
check('the path comes back so the operator knows where to look',
  absentPath(ABSENT_BODY), 'C:/…/server/config/chain_rules.json');
check('the fourth route carries its own field and is still absent',
  absentPath({ ...ABSENT_BODY, last_updated: null }), ABSENT_BODY.absent_path);
check('absence without a path is still absence, not a healthy empty list',
  absentPath({ status: 'success', data: [], state: LISTING_ABSENT }), LISTING_ABSENT);

console.log('gate 2 — an empty-but-present source is UNCHANGED');
check('a present source with no rows is not absent — 「0개」 is the right answer',
  absentPath({ status: 'success', data: [] }), null);
check('… and having rows is obviously not absent',
  absentPath({ status: 'success', data: [1, 2] }), null);
check('a body that never parsed says nothing about absence',
  absentPath(null), null);
check('… nor does a non-object', absentPath('nope'), null);

console.log('the three states stay three');
// 🔴 두 함수가 «서로의 답을 안 먹습니다». 하나로 접었으면 이 넷 중 둘이 깨집니다.
check('an ERROR body is not read as absent', absentPath(
  { status: 'error', message: 'PermissionError', data: [] }), null);
check('an ABSENT body is not read as an error', errorText(ABSENT_BODY), null);
check('an EMPTY body is neither', absentPath({ status: 'success', data: [] }), null);
check('… and errorText agrees about the empty one',
  errorText({ status: 'success', data: [] }), null);

console.log(`\n${failures.length ? 'FAIL' : 'PASS'}  ${pass} passed, ${failures.length} failed`);
// 🔴 The runner's evidence line. Exit code alone cannot tell 「red」 from 「never asserted」.
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
if (failures.length) { console.log(failures.map(f => `  - ${f}`).join('\n')); process.exit(1); }
