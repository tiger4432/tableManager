// UNIQUENESS — 서버가 «이미» 낸 판정을 화면이 몇 갈래로 읽는지.
//
// The subject is imported (owner, 2026-09-02: 잘라쓰기 하니스 절대 금지). Pure module, no DOM.
//
// 🔴 THE THREE THIS FILE EXISTS FOR:
//   ① 「아직 안 물음」과 「유니크 아님」은 같은 픽셀이 아니다. 하나는 질문이 살아 있고 하나는
//      답이다. 답으로 그리면 운영자가 «고칠 것 없는 자리»를 고치러 간다.
//   ② 🔴 서버의 `unique` 불리언이 «두 가지»를 접는다: `rows == combinations and rows > 0`
//      이므로 «빈 표»가 `unique: false` 로 나온다. 겹친 행이 0인데 「유니크 아님」이라고
//      말하는 칸이 되고, 그 둘은 고치는 방법이 정반대다 — 컬럼을 바꾸는 일 vs 적재하는 일.
//   ③ 추천을 화면이 «다시 고르지» 않는다. 서버가 고른 것을 나르기만 한다. 같은 규칙의
//      두 번째 구현은 그 둘이 갈리는 날까지 조용하다.
//
// Run: node client2/tests/uniqueness_harness.mjs
import { uniquenessVerdict, orderingVerdicts, UNIQUENESS_UNREAD } from '../src/uniqueness.js';

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

// The server's own shapes, copied from `column_stats.combination_uniqueness` /
// `ordering_candidates` return statements -- not invented here.
const UNIQUE = { relation: 'r', columns: ['a', 'b'], total_rows: 34939,
                 distinct_combinations: 34939, duplicate_rows: 0,
                 rows_in_duplicated_groups: 0, largest_group: 1,
                 null_bearing_rows: 0, unique: true };
const DUPED = { relation: 'r', columns: ['a'], total_rows: 34939,
                distinct_combinations: 30000, duplicate_rows: 4939,
                rows_in_duplicated_groups: 9878, largest_group: 3,
                null_bearing_rows: 12, unique: false };
const EMPTY = { relation: 'r', columns: ['a'], total_rows: 0, distinct_combinations: 0,
                duplicate_rows: 0, rows_in_duplicated_groups: 0, largest_group: 0,
                null_bearing_rows: 0, unique: false };
const UNMEASURABLE = { columns: ['x', 'y', 'z'], declared: true, measurable: false,
                       reason: "declared key names column(s) ['z'] that the relation does not have" };

// ═══ ① 다섯 갈래 ═══════════════════════════════════════════════════════════════════
console.log('\n[1] five states, and the server\'s boolean only knows three');
{
  eq('a measured unique key says so', uniquenessVerdict(UNIQUE).state, 'unique');
  eq('a collision says so', uniquenessVerdict(DUPED).state, 'duplicated');
  eq('a key naming a column the table lacks is not judged',
    uniquenessVerdict(UNMEASURABLE).state, 'unmeasurable');
  eq('nothing asked yet is not a verdict',
    uniquenessVerdict(UNIQUE, { read: false }).state, 'unread');
  eq('...and neither is an absent answer', uniquenessVerdict(null).state, 'unread');

  // 🔴 ② THE SPLIT THE SERVER'S BOOLEAN CANNOT MAKE.
  eq('an EMPTY table is not 「유니크 아님」', uniquenessVerdict(EMPTY).state, 'empty');
  ok('...even though the server sent unique:false for it', EMPTY.unique === false);
  ok('...and its wording does not accuse the columns',
    !uniquenessVerdict(EMPTY).text.includes('유니크 아님'));
  ok('the two are not the same pixel',
    uniquenessVerdict(EMPTY).state !== uniquenessVerdict(DUPED).state);
}

// ═══ ② 수는 서버의 것이고, 셋은 서로 다른 질문이다 ═══════════════════════════════════
console.log('\n[2] the numbers travel, and they are not one number');
{
  const v = uniquenessVerdict(DUPED);
  ok('how many rows the contract refuses on', v.detail.includes('4,939'));
  ok('...and how much data is actually involved, which is the larger one',
    v.detail.includes('9,878'));
  ok('NULLs are their own count, because they are a different defect',
    v.detail.includes('12'));
  eq('a clean key carries its row count, not a bare word',
    uniquenessVerdict(UNIQUE).detail, '행 34,939');
  eq('a key with no NULLs does not mention NULLs',
    /NULL/.test(uniquenessVerdict({ ...DUPED, null_bearing_rows: 0 }).detail), false);

  // The verdict says WHAT it is about, so it can never be read as being about another
  // combination -- the columns are part of the answer, not context the caller remembers.
  eq('the verdict carries the columns it judged', uniquenessVerdict(DUPED).columns, ['a']);
  eq('...and so does an unmeasurable one',
    uniquenessVerdict(UNMEASURABLE).columns, ['x', 'y', 'z']);
  ok('an unmeasurable one keeps the server\'s sentence verbatim',
    uniquenessVerdict(UNMEASURABLE).detail === UNMEASURABLE.reason);
}

// ═══ ③ 서버가 «안 실은» 칸을 「아니다」로 읽지 않는다 ═══════════════════════════════════
console.log('\n[3] a key the server did not send is not a "no"');
{
  const { unique, ...noVerdict } = DUPED;
  eq('no `unique` key at all reads as unasked', uniquenessVerdict(noVerdict).state, 'unread');
  eq('a non-boolean is not coerced',
    uniquenessVerdict({ ...DUPED, unique: 'false' }).state, 'unread');
  eq('...nor is a missing row count read as zero rows',
    uniquenessVerdict({ columns: ['a'], measurable: true, unique: true }).detail, '');
  eq('an unread verdict says the word for 「모름」',
    uniquenessVerdict(null).text, UNIQUENESS_UNREAD);
}

// ═══ ④ 추천은 서버가 고른다 ════════════════════════════════════════════════════════
console.log('\n[4] the recommendation is carried, never recomputed');
{
  const ordering = { relation: 'r', declared_keys: [UNMEASURABLE, DUPED, UNIQUE],
                     recommended: ['a', 'b'] };
  const v = orderingVerdicts(ordering);
  eq('every declared key is judged, including the ones that failed',
    v.keys.map((k) => k.state), ['unmeasurable', 'duplicated', 'unique']);
  eq('the server\'s pick is carried through', v.recommended, ['a', 'b']);

  // 🔴 THE PICK IS NOT RE-DERIVED. Handing it a `recommended` that is NOT the shortest
  //    passing key must still come back verbatim -- if this file re-ran the rule, this
  //    assertion is what would catch it.
  const odd = orderingVerdicts({ declared_keys: [UNIQUE, DUPED], recommended: ['z'] });
  eq('a recommendation this file would not have chosen is still the answer',
    odd.recommended, ['z']);

  // `recommended: null` IS an answer: the declaration alone cannot order this relation.
  const none = orderingVerdicts({ declared_keys: [DUPED], recommended: null });
  eq('no surviving key leaves no recommendation', none.recommended, null);
  ok('...and says so rather than drawing blank', none.text === '선언만으로는 못 정함');
  const bare = orderingVerdicts({ declared_keys: [], recommended: null });
  ok('a relation with no declared key says THAT instead',
    bare.text === '선언된 유니크 키 없음');
  ok('the two absences are not the same sentence', none.text !== bare.text);

  eq('nothing fetched yet is not "no keys"', orderingVerdicts(null).read, false);
  eq('...and it says 「모름」', orderingVerdicts(null).text, UNIQUENESS_UNREAD);
  eq('...and offers no keys to draw', orderingVerdicts(undefined).keys, []);
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
