// 「0 인데 일감이 있다」를 «한 곳»에서 그리는지, 그리고 그 0 이 «무엇의 0 인지».
//
// The subject is imported (owner, 2026-09-02: 잘라쓰기 하니스 절대 금지).
//
// 🔴 THE THREE THIS FILE EXISTS FOR:
//   ① A ZERO AND AN UNREAD NUMBER ARE NOT THE SAME PIXEL. One was counted; the other was
//      never seen. Four tabs grew their own sentence for this before a part existed.
//   ② THE WORD BELONGS TO ZERO. Hung beside a non-zero count it contradicts the number.
//   ③ AN UNKNOWN TOKEN SURVIVES. Folding it into the six known ones loses the new word
//      silently, which is the failure this repository keeps closing.
//
// Run: node client2/tests/count_with_absence_harness.mjs
import { countWithAbsence, ABSENCE_WORDS } from '../src/count_with_absence.js';
import { ABSENT } from '../src/absent.js';

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

console.log('\n[1] a zero says what kind of zero it is');
{
  eq('a plain zero is a zero', countWithAbsence({ value: 0 }).text, '0');
  eq('a zero with a reason carries it',
    countWithAbsence({ value: 0, absence: 'truly_none' }).text, '0 · 정말 없음');
  eq('...and the word is the operator\'s, from the closed list',
    countWithAbsence({ value: 0, absence: 'not_yet' }).word, '아직');
  // ⚠️ all six, so a token added to the map is not silently half-wired
  eq('the closed list is six', Object.keys(ABSENCE_WORDS).length, 6);
  for (const token of Object.keys(ABSENCE_WORDS)) {
    ok(`${token} has a word`, countWithAbsence({ value: 0, absence: token }).word === ABSENCE_WORDS[token]);
  }
}

console.log('\n[2] the word belongs to zero, and to nothing else');
{
  eq('a real count is left alone',
    countWithAbsence({ value: 7, absence: 'truly_none' }).text, '7');
  eq('...and carries no word', countWithAbsence({ value: 7, absence: 'not_yet' }).word, '');
}

console.log('\n[3] unread is not zero');
{
  const dead = countWithAbsence({ unread: '이 프로세스에 루프 없음' });
  eq('an unread number is a dash', dead.text, ABSENT);
  eq('...and says why in its own word', dead.word, '이 프로세스에 루프 없음');
  eq('...and is not a read count', dead.read, false);
  // 🔴 unread WINS over a value: a stale number beside "could not read" is worse than a dash
  eq('unread beats a value that came with it',
    countWithAbsence({ value: 0, absence: 'truly_none', unread: '못 봄' }).text, ABSENT);
  // and a missing value is a dash too, without inventing a reason
  eq('no value at all is a dash', countWithAbsence({}).text, ABSENT);
  eq('...with no word attached', countWithAbsence({}).word, '');
  eq('null is not zero', countWithAbsence({ value: null }).text, ABSENT);
  eq('an empty string is not zero', countWithAbsence({ value: '' }).text, ABSENT);
  eq('and neither is whitespace', countWithAbsence({ value: '   ' }).text, ABSENT);
}

console.log('\n[4] a word this build has never seen survives');
{
  // ⛔ folding it into the known six would lose it without an error
  eq('an unknown token is passed through verbatim',
    countWithAbsence({ value: 0, absence: 'some_new_word' }).text, '0 · some_new_word');
  eq('an empty absence adds nothing', countWithAbsence({ value: 0, absence: '' }).text, '0');
  eq('...and neither does null', countWithAbsence({ value: 0, absence: null }).text, '0');
}

console.log('\n[5] two callers, two declarations, one part');
{
  // 🔴 this is the definition of 「부품이다」: the same function, different declarations,
  //    and neither can see the other's words.
  const loop = countWithAbsence({ value: 0, unread: '이 프로세스에 루프 없음' });
  const failed = countWithAbsence({ value: 3 });
  ok('the first says its own thing', loop.text === ABSENT && loop.word === '이 프로세스에 루프 없음');
  ok('the second is untouched by it', failed.text === '3' && failed.word === '');
  const queueRunning = countWithAbsence({ value: 0, absence: 'truly_none' });
  ok('and a third declaration reads the server\'s word', queueRunning.text === '0 · 정말 없음');
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
