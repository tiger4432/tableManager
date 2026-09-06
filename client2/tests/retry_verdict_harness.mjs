// retry_verdict_harness — THREE STATES, AND THE THIRD ONE IS NOT "NOT FAILED".
//
// The screen decided a retry had succeeded by asking whether the row was still FAILED. In
// decoupled mode the route does not retry anything: it marks rows `PENDING_RETRY` and a separate
// watcher process picks them up later. A third state satisfies "not FAILED", so 「✅ 재시도 완료」
// appeared for work that had not started, and nothing threw.
//
// 🔴 THE DEFECT IS MODE-DEPENDENT, WHICH IS WHY IT LIVED SO LONG. With the decoupled branch off,
// the route retries synchronously and 「완료」 is TRUE. A harness that only checked the happy path
// would have agreed with the old code forever.
//
// ═══ THIS FILE IMPORTS ITS SUBJECT ═══
// `retry_verdict.js` was extracted precisely so this could be an import rather than a slice.
// Three harnesses died tonight because their subjects are cut out of source and run in a vm, and
// one added import put a name out of reach — CLAUDE.md's standing ban describes exactly that, and
// naming a module that can be imported is the destination it points at.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import * as BASELINE from '../src/retry_verdict.js';

const SRC_PATH = fileURLToPath(new URL('../src/retry_verdict.js', import.meta.url));

let passed = 0;
let failed = 0;

function die(msg) {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  console.log('ASSERTIONS 0 1');
  process.exit(2);
}

function ok(name, cond, saw) {
  if (cond) { passed++; console.log(`  ok   ${name}`); }
  else { failed++; console.log(`  FAIL ${name}${saw === undefined ? '' : `  saw: ${JSON.stringify(saw)}`}`); }
}

const X = BASELINE;
if (!X || !X.retryVerdict || !X.retryMessage) {
  die('retry_verdict.js did not import — its exports moved or renamed.');
}

console.log('\n── A. THE THIRD STATE IS ITS OWN ANSWER ────────────────────────────');
{
  ok('A1 SUCCESS is done', X.retryVerdict('SUCCESS').state === 'done');
  ok('A2 FAILED is failed', X.retryVerdict('FAILED').state === 'failed');
  // 🔴 THE WHOLE ROUND. Under the old predicate this row read as a success.
  ok('A3 PENDING_RETRY is neither', X.retryVerdict('PENDING_RETRY').state === 'queued',
    X.retryVerdict('PENDING_RETRY'));
  ok('A4 and it is NOT settled', X.retryVerdict('PENDING_RETRY').settled === false);
  ok('A5 the two that ARE settled say so',
    X.retryVerdict('SUCCESS').settled === true && X.retryVerdict('FAILED').settled === true);
  // ⚠️ THE PAIR THAT MAKES A3 NON-VACUOUS. "queued" would also be produced by a function that
  //    answers "queued" for everything; these three say the answers are three.
  ok('A6 the three states give three answers',
    new Set(['SUCCESS', 'FAILED', 'PENDING_RETRY'].map(v => X.retryVerdict(v).state)).size === 3);
}

console.log('\n── B. AN UNKNOWN SPELLING IS NOT A SUCCESS ─────────────────────────');
{
  // The old code's shape: anything that is not FAILED passes as done. A state the server adds
  // tomorrow must not inherit that.
  ok('B1 an unknown status is unknown', X.retryVerdict('QUARANTINED').state === 'unknown');
  ok('B2 ... and not settled', X.retryVerdict('QUARANTINED').settled === false);
  ok('B3 an absent status is unknown too, not done',
    X.retryVerdict(undefined).state === 'unknown' && X.retryVerdict(null).state === 'unknown');
  ok('B4 an empty string is unknown, not done', X.retryVerdict('').state === 'unknown');
  // Spelling robustness: the server writes upper case, but a screen that lower-cases on the way
  // in must not silently fall to "unknown" and then to a wrong sentence.
  ok('B5 case and padding do not change the answer',
    X.retryVerdict(' pending_retry ').state === 'queued');
}

console.log('\n── C. THE SENTENCE MATCHES THE VERDICT ─────────────────────────────');
{
  ok('C1 done reads as success', X.retryMessage('SUCCESS').tone === 'success');
  ok('C2 queued does NOT read as success', X.retryMessage('PENDING_RETRY').tone !== 'success',
    X.retryMessage('PENDING_RETRY'));
  ok('C3 queued names who has to act',
    /워처/.test(X.retryMessage('PENDING_RETRY').text), X.retryMessage('PENDING_RETRY').text);
  ok('C4 failed does not read as success', X.retryMessage('FAILED').tone !== 'success');
  ok('C5 unknown does not read as success', X.retryMessage('WHAT').tone !== 'success');
  // ⚠️ ABSENT FROM THE PAGE IS NOT A BROKEN STATE. With the FAILED filter on, a row
  //    that SUCCEEDED leaves the list - that is the normal case, and reporting it in the
  //    same words as 'the server invented a state' would make routine success read as a
  //    fault. Both stay non-success; they do not share a sentence.
  ok('C8 an absent row is not worded as an unknown state',
    !/알 수 없는 상태/.test(X.retryMessage(null).text),
    X.retryMessage(null).text);
  ok('C8b and the unknown spelling still is',
    /알 수 없는 상태/.test(X.retryMessage('WHAT').text));
  ok('C9 and neither claims success',
    X.retryMessage(null).tone !== 'success' && X.retryMessage('WHAT').tone !== 'success');
  // 🔴 THE SERVER'S OWN SENTENCE IS CARRIED, NOT OVERWRITTEN. The route already says 「Marked N
  //    logs as PENDING_RETRY. Standalone watcher will process them」 and the old toast appended
  //    it AFTER a tick, which is how a true sentence read as a false one.
  ok('C6 the server message is carried through',
    X.retryMessage('PENDING_RETRY', 'Marked 3 logs').text.includes('Marked 3 logs'));
  ok('C7 and its absence is not a blank tail',
    !X.retryMessage('PENDING_RETRY').text.includes('—')
    || X.retryMessage('PENDING_RETRY').text.trim().length > 6);
}

console.log('\n── D. THE SCREEN GOES THROUGH THIS PLACE, AND OWNS NO LIST ─────────');
{
  // 🔴 TEXT IS THE SUBJECT HERE, NOT A PROXY (CLAUDE.md 2026-09-03, per assertion). 「does this
  //    site call the one place」 is invisible in output — a site that does not just keeps
  //    answering correctly until a state it never heard of arrives.
  const js = readFileSync(new URL('../src/admin.js', import.meta.url), 'utf8');
  ok('D1 the retry outcome goes through the verdict', js.includes('retryMessage('));
  ok('D2 the severity badge goes through it too', js.includes('retryVerdict('));
  // 🔴 THE OLD PREDICATE IS GONE. This is the actual defect: 「still FAILED?」 read as
  //    「did it succeed?」. Leaving it anywhere in this file would leave the bug reachable.
  ok('D3 no site decides the outcome by one state\'s absence',
    !/status === 'FAILED'\s*\)\s*\|\|/.test(js)
    && !js.includes('const stillFailed ='), 'the FAILED-absence predicate is still there');
  // ⛔ AND THIS MODULE MUST NOT GROW A CATALOGUE. The server owns the state list
  //    (`file_ingestion_status.FILE_INGESTION_STATUS_VOCABULARY`, five members); a list here
  //    would be a second one and, as first drafted, a wrong one.
  ok('D4 this module exports no state list',
    X.INGESTION_STATUSES === undefined && X.STATUS_LABEL === undefined,
    Object.keys(X));
}

// ── mutants ─────────────────────────────────────────────────────────────────────────
const swap = (from, to) => (src) => {
  if (!src.includes(from)) die(`mutation anchor stopped matching: ${JSON.stringify(from)}. `
    + 'A harness that goes quiet because it lost the code is worse than no harness.');
  return src.replace(from, to);
};

// 🔴 ONE MUTANT PER PROPERTY, NOT ONE MUTANT FOR ALL OF THEM. The three states rest on three
//    different lines and a single mutation cannot redden them together — asking it to would
//    reject a correct design (lead's correction, 2026-09-07).
const DEFECTS = [
  ['M1 the third state collapses back into "done" (the original defect)',
    swap("  if (spelled === 'PENDING_RETRY') return { state: 'queued', tone: 'warn', "
      + 'settled: false };', '')],
  ['M2 waiting counts as settled',
    swap("return { state: 'queued', tone: 'warn', settled: false };",
      "return { state: 'queued', tone: 'warn', settled: true };")],
  ['M3 an unknown spelling is treated as a success',
    swap("  return { state: 'unknown', tone: 'warn', settled: false };",
      "  return { state: 'done', tone: 'ok', settled: true };")],
  ['M4 the queued sentence reads as a success',
    swap("return { tone: 'warning', text: `⏳ 재시도 대기 — 워처가 집어 가야 처리됩니다${tail}` };",
      "return { tone: 'success', text: `✅ 재시도 완료${tail}` };")],
  ['M5 the server sentence is dropped',
    swap('const tail = serverMessage ? ` — ${serverMessage}` : \'\';', "const tail = '';")],
  ['M6 an absent row is reported as a broken state',
    swap("      return { tone: 'warning', text: status == null", "      return { tone: 'warning', text: false")],
  ['M7 spelling normalisation is dropped, so a lower-case status becomes unknown',
    swap(".trim().toUpperCase();", ";")],
];

const CONTROLS = [
  ['a local rename', (src) => src.replace(/\bspelled\b/g, 'word')],
  ['comments stripped', (src) => src.split('\n')
    .filter((l) => !l.trim().startsWith('//') && !l.trim().startsWith('*')
      && !l.trim().startsWith('/*'))
    .join('\n')],
];

/** 채점기 — 기준선과 변이가 «같은 질문»에 답해야 비교가 뜻을 가집니다. */
function verdict(M) {
  return M.retryVerdict('SUCCESS').state !== 'done'
    || M.retryVerdict('FAILED').state !== 'failed'
    || M.retryVerdict('PENDING_RETRY').state !== 'queued'
    || M.retryVerdict('PENDING_RETRY').settled !== false
    || M.retryVerdict('QUARANTINED').state !== 'unknown'
    || M.retryVerdict(' pending_retry ').state !== 'queued'
    || M.retryMessage('PENDING_RETRY').tone === 'success'
    || !M.retryMessage('PENDING_RETRY', 'Marked 3 logs').text.includes('Marked 3 logs')
    || /알 수 없는 상태/.test(M.retryMessage(null).text);
}

if (verdict(BASELINE)) die('the scorer already fails on the UNMUTATED module — '
  + 'every "caught" below would be scoring the scorer, not the mutant.');

async function score(list, mustCatch, heading) {
  console.log(`\n── ${heading} ─────────────────────────────`);
  let hit = 0;
  for (const [name, mutate] of list) {
    let bad = false;
    try {
      bad = verdict((await loadWithProbe(SRC_PATH, { mutate, tag: 'retryverdict' })).module);
    } catch (e) {
      if (/did not mutate|unchanged/.test(String(e && e.message))) die(`${name}: ${e.message}`);
      bad = true;
    }
    if (bad === mustCatch) { hit++; console.log(`  ${mustCatch ? 'caught ' : 'escaped'} ${name}`); }
    else { failed++; console.log(`  ${mustCatch ? 'ESCAPED' : 'CAUGHT '} ${name}  <- wrong`); }
  }
  return hit;
}

const caught = await score(DEFECTS, true, 'defect mutants (each must be CAUGHT)');
const escaped = await score(CONTROLS, false, 'control mutants (each must ESCAPE)');

console.log(`\n${passed} passed, ${failed} failed; ${caught}/${DEFECTS.length} defects caught; `
  + `${escaped}/${CONTROLS.length} controls escaped.`);
console.log(`ASSERTIONS ${passed} ${failed}`);
if (failed) process.exit(1);
