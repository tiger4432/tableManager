// S-21 ㉮ — 「고른 칸 «일부»에만 있는 소스」가 「전부에 있는 소스」와 갈리나.
//
// 🔴 대상을 «import 합니다** — `source_rows.js` 는 이미 그렇게 채점되는 모듈입니다.
// 🔴 재는 것은 «가름»입니다. 판정 70 의 ㉰ 절반(단일 셀)은 «설계로 닫혔고**, 여기서 재는 것은
//    ㉮ — 모집단이 «선택 칸 수»인 그 절반입니다.
// ⚠️ 두 수를 헷갈리면 안 됩니다: `values` 는 «칸마다 하나»이고 `uniqueVals` 는 «값의 종류»입니다.
//    같은 값을 든 두 칸은 «두 칸»입니다.
//
// Run: node client2/tests/source_rows_coverage_harness.mjs
import { sourceRowAllHtml, sourceRowHtml } from '../src/source_rows.js';

let pass = 0, fail = 0;
const failed = [];
function ok(cond, name) {
  if (cond) { pass++; console.log(`  OK   ${name}`); }
  else { fail++; failed.push(name); console.log(`  BAD  ${name}`); }
}
function row(values, opts) {
  try { return sourceRowAllHtml('excel', values, opts); }
  catch (e) { return `<<threw: ${e && e.message}>>`; }
}
const RATIO = /칸 중 .*칸/;

console.log('-- the round\'s sentence ----------------------------------------------');
const partial = row(['a', 'b'], { isPinnedAll: false, cellCount: 5 });
const full = row(['a', 'b', 'c', 'd', 'e'], { isPinnedAll: false, cellCount: 5 });
ok(RATIO.test(partial), 'A1 a source present in only SOME of the selection says so');
ok(!RATIO.test(full), 'A2 ...and one present in all of them stays silent (today\'s row)');
ok(partial !== full, 'A3 the two are drawn DIFFERENTLY, which is the whole round');
// 🔴 CONTROL: the SAME values, only the denominator moves. If the note turned on anything
//    else, this pair would not separate.
const sameValuesCovered = row(['a', 'b'], { isPinnedAll: false, cellCount: 2 });
ok(!RATIO.test(sameValuesCovered),
  'A4 CONTROL: identical values covering the whole selection say nothing — only the ratio decides');
// 🔴 A5 AS FIRST WRITTEN WAS BLIND TO A SWAP: 「both numbers appear」 stays true when the two
//    are exchanged, and the swap mutant went green. What matters is the ORDER — the selection
//    is the denominator and must sit before 중, or the row states the opposite of the truth.
ok(/5칸 중 2칸/.test(partial),
  'A5 the SELECTION comes first and the covered count second — a swap reads as its own opposite');

console.log('\n-- cells, not distinct values -----------------------------------------');
// ⚠️ 같은 값을 든 두 칸은 «두 칸»입니다. 여기서 중복을 지우면 «덮고 있는 칸»을 적게 세어
//    멀쩡한 소스를 「빠졌다」고 말합니다.
const dupes = row(['a', 'a', 'a'], { isPinnedAll: false, cellCount: 3 });
ok(!RATIO.test(dupes),
  'B1 three cells holding the SAME value cover three cells — not one');
const dupesPartial = row(['a', 'a'], { isPinnedAll: false, cellCount: 3 });
ok(RATIO.test(dupesPartial) && dupesPartial.includes('2'),
  'B2 ...and two such cells out of three is still 2, not 1');

console.log('\n-- 무회귀: what must render exactly as before --------------------------');
ok(!RATIO.test(row(['a', 'b'], { isPinnedAll: false })),
  'C1 a caller that passes no cellCount renders as it did (nothing added)');
ok(row(['a', 'b'], { isPinnedAll: false }) === row(['a', 'b'], { isPinnedAll: false, cellCount: 2 }),
  'C2 ...and covering the whole selection is byte-identical to that older rendering');
ok(!RATIO.test(row([], { isPinnedAll: false, cellCount: 4 })),
  'C3 a source with no values at all keeps today\'s answer, with no ratio bolted on');
ok(row([], { isPinnedAll: false, cellCount: 4 }).includes('N/A'),
  'C4 ...which is N/A, unchanged');
// 🔴 넘치는 수는 «그리지 않습니다** — 있을 수 없는 비율을 그리면 화면이 자기 모순을 말합니다.
ok(!RATIO.test(row(['a', 'b', 'c'], { isPinnedAll: false, cellCount: 2 })),
  'C5 more covered than selected cannot happen, and is drawn as nothing rather than as nonsense');
ok(!RATIO.test(row(['a'], { isPinnedAll: false, cellCount: '5' })),
  'C6 a non-integer denominator is not coerced into a ratio');

console.log('\n-- the single-cell row is a different question, and is untouched -------');
const single = sourceRowHtml('excel', { value: 42 }, { isPinned: false });
ok(!RATIO.test(single),
  'D1 the per-cell row draws no ratio — ruling 70 closed that half as DESIGN, not as a gap');
ok(single.includes('42'), 'D2 ...and still shows its value');

console.log('\n-- escaping still holds on the path this round touched -----------------');
const nasty = row(['<img src=x onerror=1>'], { isPinnedAll: false, cellCount: 3 });
ok(!nasty.includes('<img'),
  'E1 a hostile value is still escaped once the ratio is appended beside it');
ok(RATIO.test(nasty), 'E2 CONTROL: that row really did take the ratio branch');

console.log(`\n${pass} passed, ${fail} failed.`);
if (fail) console.error(`failed:\n  ${failed.join('\n  ')}`);
console.log(`ASSERTIONS ${pass + fail} ${fail}`);
process.exit(fail ? 1 : 0);
