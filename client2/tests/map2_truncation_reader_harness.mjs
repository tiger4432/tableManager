// S-5 (클라 절) — map2 의 두 전선 독자가 「잘렸나」를 «정본 하나»에게 묻나.
//
// 🔴 닫는 문장: `truncated === true` 는 «불리언 모양»만 읽습니다. 전선의 그 칸은 실측 «다섯 모양»
//    이고, 그중 객체 `{reason}` 은 `=== true` 에서 «false» 로 떨어집니다 — 서버가 「잘랐다」고
//    말한 목록이 «온전한 것»으로 그려집니다. 오류는 «안 납니다».
// ⛔ 새 독자를 만들지 않았습니다. `truncation.js` 의 `saysTruncated` 는 이미 바깥 화면 «셋»이
//    부르는 그 자리이고, map2 만 자기 판정을 들고 있었습니다.
//
// ⚠️ `map2/authoring.js` 의 `input.truncated` 는 «안 건드렸습니다** — 그 값은 전선이 아니라
//    이미 정규화된 내부 불리언입니다(그 파일의 @param 이 `{boolean}` 이라 적습니다). 전선이
//    아닌 자리에 전선 독자를 붙이면 그것이 «세 번째 저자»입니다.
//
// Run: node client2/tests/map2_truncation_reader_harness.mjs
import { normaliseReferenceCatalog } from '../src/map2/api.js';
import { decodeIndexWalk } from '../src/map2/decode.js';
import { saysTruncated } from '../src/truncation.js';

let pass = 0, fail = 0;
const failed = [];
function ok(cond, name) {
  if (cond) { pass++; console.log(`  OK   ${name}`); }
  else { fail++; failed.push(name); console.log(`  BAD  ${name}`); }
}

// 전선의 다섯 모양 중 이 라운드가 가르는 둘 + 침묵 셋.
const SHAPES = [
  ['boolean true', true, true],
  ['object with a reason', { reason: 'node_limit' }, true],
  ['boolean false', false, false],
  ['object with NO reason', { reason: '' }, false],
  ['missing', undefined, false],
];

console.log('-- decode: the source list that says it was cut ----------------------');
const decodeSaysCut = (truncated) => {
  const sources = { cells: [], indices: [] };
  if (truncated !== undefined) sources.truncated = truncated;
  try { return decodeIndexWalk({ sources }, []).truncated === true; }
  catch (e) { return `<<threw: ${e && e.message}>>`; }
};
for (const [label, wire, want] of SHAPES) {
  ok(decodeSaysCut(wire) === want, `A ${label} -> ${want ? 'cut' : 'not cut'} (decode)`);
}
// 🔴 이 줄이 이 라운드입니다: 오늘 이전에는 이것이 «false» 였습니다.
ok(decodeSaysCut({ reason: 'node_limit' }) === true,
  'A6 THE ROUND: an object-shaped truncation is no longer read as 「not cut」');

console.log('\n-- api: the reference catalog record ---------------------------------');
// 🔴 이 라우트의 `truncated` 는 «봉투 최상단»입니다 — 항목마다가 아니라 «목록 전체»가 잘린
//    것이라서입니다. 픽스처를 항목에 달면 «아무것도 안 재고» 초록이 됩니다.
const apiSaysCut = (truncated) => {
  const body = { items: [{ table: 't', map_id: 'm' }] };
  if (truncated !== undefined) body.truncated = truncated;
  try { return normaliseReferenceCatalog(body).truncated === true; }
  catch (e) { return `<<threw: ${e && e.message}>>`; }
};
for (const [label, wire, want] of SHAPES) {
  ok(apiSaysCut(wire) === want, `B ${label} -> ${want ? 'cut' : 'not cut'} (api)`);
}

console.log('\n-- the two cannot drift, because they ask the same reader -------------');
// 🔴 «행동»으로 잽니다 — 「같은 함수를 부른다」가 아니라 「같은 입력에 같은 답을 낸다」입니다.
//    이름을 재면 사본을 만들어도 초록이고, 사본이 갈라지는 것이 이 라운드가 막는 것입니다.
for (const [label, wire] of SHAPES) {
  ok(decodeSaysCut(wire) === apiSaysCut(wire),
    `C the two carriers agree on ${label}`);
}
// 그리고 둘 다 «정본»과 같은 답이어야 합니다.
for (const [label, wire] of SHAPES) {
  ok(decodeSaysCut(wire) === (saysTruncated(wire) === true),
    `D decode matches the canonical reader on ${label}`);
}

console.log(`\n${pass} passed, ${fail} failed.`);
if (fail) console.error(`failed:\n  ${failed.join('\n  ')}`);
console.log(`ASSERTIONS ${pass + fail} ${fail}`);
process.exit(fail ? 1 : 0);
