// health_card_absence_harness — AN UNREAD VALUE IS NOT A ZERO, ON THE CARD TOO.
//
// The Auto Update TAB was taught to tell 「못 읽었다」 from 「없다」: it runs `errorText()` on the
// status body, `absentPath()` on it, and refuses to draw the linked-failure table when either
// input is missing. The health CARD recomputes both of those numbers from the same two sources
// and asked none of those questions — so a repair that landed in one site did not land in the
// other, and the card kept saying 「수집기 없음」 for a status file that had vanished and
// 「최근 실행 …」 for a linkage it had never checked.
//
// ⚠️ WHY THIS FILE SCORES TEXT, AND WHAT THAT COSTS.
// The subject is a DOM-and-fetch function inside `admin.js`, which cannot be imported (it pulls
// in CSS and touches `document` at module scope). Slicing it out is banned for good reasons, so
// what is scored here is 「이 자리가 그 질문을 «하나»」 — text as the SUBJECT, not as a proxy for
// behaviour (CLAUDE.md 2026-09-03, per assertion). That is a real property: a site that does not
// ask keeps answering plausibly until the day the value is missing.
// 🔴 IT IS ALSO A WEAKER GATE THAN AN IMPORT WOULD BE, and saying so is the point of this note.
// Making it behavioural means extracting the card's verdict into an importable module, the way
// `retry_verdict.js` was extracted; that is a separate round and is NOT done here.
import { readFileSync } from 'node:fs';

let passed = 0;
let failed = 0;

function ok(name, cond, saw) {
  if (cond) { passed++; console.log(`  ok   ${name}`); }
  else { failed++; console.log(`  FAIL ${name}${saw === undefined ? '' : `  saw: ${JSON.stringify(saw)}`}`); }
}

const src = readFileSync(new URL('../src/admin.js', import.meta.url), 'utf8');

// The card lives in `refreshFileAndAutoHealth`; score THAT function, not the whole file, or the
// tab's guards would satisfy every assertion here and the card could keep having none.
const start = src.indexOf('async function refreshFileAndAutoHealth()');
const end = src.indexOf('\nasync function ', start + 10);
const card = start === -1 ? '' : src.slice(start, end === -1 ? src.length : end);

if (!card) {
  console.error('HARNESS FAILURE: `refreshFileAndAutoHealth` not found — it was renamed or moved.');
  console.error('(This is not a passing result. Nothing was compared.)');
  console.log('ASSERTIONS 0 1');
  process.exit(2);
}

console.log('\n── A. THE CARD ASKS WHAT THE TAB ASKS ──────────────────────────────');
{
  ok('A1 it reads the error envelope', /errorText\(/.test(card), 'no errorText in the card');
  ok('A2 it reads the absence', /absentPath\(/.test(card), 'no absentPath in the card');
  // 🔴 ORDER MATTERS: both readings must happen BEFORE `data` is turned into a count, or the
  //    empty-list branch answers first and the card says 「수집기 없음」 either way.
  const dataAt = card.indexOf('const collectors = r.data');
  ok('A3 both are read before the collectors are counted',
    dataAt > card.indexOf('errorText(') && dataAt > card.indexOf('absentPath('),
    { dataAt, errorAt: card.indexOf('errorText('), absentAt: card.indexOf('absentPath(') });
}

console.log('\n── B. AN UNANSWERED QUERY IS NOT A ZERO ────────────────────────────');
{
  // `failedTotal === null` is this function's own word for 「실패 로그를 못 읽었다」 and the File
  // card three lines above already refuses to draw on it.
  ok('B1 the linkage is only counted when the log query answered',
    /failedTotal !== null/.test(card) && /linkedRead/.test(card),
    'the intersection is still computed unconditionally');
  ok('B2 an unread linkage is not reported as none',
    /!linkedRead/.test(card), 'nothing branches on the unread case');
  // ⚠️ AND IT CHANGES THE COLOUR, NOT ONLY THE WORDS. A sentence that says 「미확인」 under a
  //    green tick is read as green; the card has to stop claiming OK.
  ok('B3 ... and it stops the card claiming OK',
    /else if \(!linkedRead\) status = 'warn'/.test(card),
    'the unread case still leaves the card green');
}

console.log('\n── C. THE FILE CARD KEEPS ITS OWN GUARD ────────────────────────────');
{
  // No-regression: the guard this round copied the SHAPE of must still be there. If it went
  // away, B1 would be asserting a rule the file no longer follows anywhere.
  ok('C1 the file card still refuses to draw an unread total',
    /if \(failedTotal === null\)/.test(card));
}

console.log(`\n${passed} passed, ${failed} failed.`);
console.log(`ASSERTIONS ${passed} ${failed}`);
if (failed) process.exit(1);
