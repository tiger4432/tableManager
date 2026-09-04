// ABSENT — 「안 왔다」와 「0이다」가 같은 픽셀이 되지 않는다.
//
// The subject is imported (owner, 2026-09-02: 잘라쓰기 하니스 절대 금지). `absent.js` touches
// no DOM and no CSS, so it imports in node as it stands.
//
// 🔴 EVERY ASSERTION HERE IS SCORED IN PAIRS, and that is the whole design. An assertion that
//    only feeds a missing value would pass against a function that returns `—` for EVERYTHING,
//    including a real zero — which is the opposite failure and just as wrong. So each missing
//    case is stated beside the genuine `0` it must not become.
//
// Run: node client2/tests/absent_harness.mjs
import { ABSENT, isCount, countText, localeCountText } from '../src/absent.js';

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

// ═══ ① THE DISCRIMINANT — missing and zero, side by side ═══════════════════════════
console.log('\n[1] a missing count is not a zero, and a zero is not a dash');
{
  // 🔴 THE FOUR VALUES `Number()` LIES ABOUT. Three of them become 0 and one becomes NaN,
  //    and every one of them means 「the field did not arrive」.
  for (const [label, v] of [['null', null], ['undefined', undefined], ['empty string', ''],
                            ['NaN', NaN], ['a word', 'abc'], ['Infinity', Infinity]]) {
    eq(`${label} is not a count`, isCount(v), false);
    eq(`...so it renders as the dash (countText)`, countText(v), ABSENT);
    eq(`...and as the dash with separators too`, localeCountText(v), ABSENT);
  }

  // ...and the other half, which is what stops the function from just always dashing
  eq('a real zero IS a count', isCount(0), true);
  eq('and it renders as 0, not as a dash', countText(0), '0');
  eq('with separators too', localeCountText(0), '0');
  ok('the two are DIFFERENT pixels', countText(0) !== countText(null),
    `${countText(0)} / ${countText(null)}`);

  // the string '0' arrives from datasets and query strings and IS a count
  eq(`the string '0' is a count`, isCount('0'), true);
  eq(`...and renders as 0`, countText('0'), '0');
  // but a string of spaces is not a number, whatever Number() says about it
  eq('whitespace is not a count', isCount('   '), false);
}

// ═══ ② the separator, and that it is the only difference between the two ═══════════
console.log('\n[2] the two spellings differ only in separators');
{
  eq('countText leaves the digits alone', countText(1234567), '1234567');
  eq('localeCountText groups them', localeCountText(1234567), (1234567).toLocaleString());
  eq('negative is still a count', countText(-3), '-3');
  eq('a float is not rounded away', countText(1.5), '1.5');
  eq('a numeric string is normalised', countText('007'), '7');
}

// ═══ ③ the mark itself ═════════════════════════════════════════════════════════════
console.log('\n[3] one spelling, and it is an em dash');
{
  eq('the mark is U+2014', ABSENT.codePointAt(0), 0x2014);
  eq('and it is one character', ABSENT.length, 1);
  // 🔴 NOT A HYPHEN. `-` is what the retroactive table used for its own absence and the two
  //    must not be confused by anyone reading the screen or grepping the source.
  ok('not an ascii hyphen', ABSENT !== '-');
}

// ═══ ④ 🔴 ONE SPELLING — chain_queue_panel must be using THIS, not a copy ═══════════
//
// The panel carried a private `countOf` with a hole in it: `Number('') === 0` and `''` is
// neither null nor undefined, so an empty string rendered as 「0」. Importing the shared one
// closed that. If someone re-privatises it, this reddens.
console.log('\n[4] the panel uses this spelling and not its own');
{
  const mod = await import('../src/chain_queue_panel.js');
  const v = mod.queueView({ waiting: '', oldest_waiting_seconds: null, not_measured: {} });
  eq('an empty-string count reaches the screen as a dash, not 0', v.depth, ABSENT);
  const z = mod.queueView({ waiting: 0, oldest_waiting_seconds: null, not_measured: {} });
  eq('...and a real zero still reaches it as 0', z.depth, '0');
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
