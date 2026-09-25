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
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import * as BASELINE from '../src/retry_verdict.js';
import { autoUpdateRowHtml } from '../src/admin_rows.js';
import { autoRow } from '../src/overview_status.js';

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
    /watcher/.test(X.retryMessage('PENDING_RETRY').text), X.retryMessage('PENDING_RETRY').text);
  ok('C4 failed does not read as success', X.retryMessage('FAILED').tone !== 'success');
  ok('C5 unknown does not read as success', X.retryMessage('WHAT').tone !== 'success');
  // ⚠️ ABSENT FROM THE PAGE IS NOT A BROKEN STATE. With the FAILED filter on, a row
  //    that SUCCEEDED leaves the list - that is the normal case, and reporting it in the
  //    same words as 'the server invented a state' would make routine success read as a
  //    fault. Both stay non-success; they do not share a sentence.
  ok('C8 an absent row is not worded as an unknown state',
    !/Unknown state/.test(X.retryMessage(null).text),
    X.retryMessage(null).text);
  ok('C8b and the unknown spelling still is',
    /Unknown state/.test(X.retryMessage('WHAT').text));
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
  // The badge's class is the drawer's, whose tone is `retryVerdict`'s (F6 · G2 score that) — in
  // BOTH drawers, and no drawer keeps a status ternary of its own (lead e1af65168: one mapping).
  const collectorDrawer = (js.split(/\n(?=(?:async )?function )/).find((fn) => fn.startsWith('function selectAutoUpdateRow')) || '');
  ok('D2 the severity badge goes through it too — in both drawers, with no ternary of its own',
    (js.match(/tracebackSeverity\.className = drawer\.badgeClass;/g) || []).length === 2
    && collectorDrawer.length > 0 && !/last_status ===/.test(collectorDrawer),
    { badgeReads: (js.match(/tracebackSeverity\.className = drawer\.badgeClass;/g) || []).length, drawerFound: collectorDrawer.length > 0 });
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
  // 🔴 AND NEITHER DOES THE SCREEN. The filter draws its options from the vocabulary the
  //    server publishes. Before this round the markup spelled two of five by hand, so the one
  //    state an operator needed to look for (`PENDING_RETRY`) was the one they could not
  //    filter to — the half of F-2 that was true.
  const html = readFileSync(new URL('../admin.html', import.meta.url), 'utf8');
  ok('D5 the filter reads the published vocabulary',
    js.includes('status_vocabulary') && js.includes('applyStatusVocabulary'),
    'admin.js does not read the vocabulary');
  ok('D6 the markup spells no statuses',
    !/<option value="(FAILED|SUCCESS|PENDING_RETRY|PENDING|SKIPPED)"/.test(html),
    'admin.html still spells a status by hand');
  // ⚠️ ALL IS NOT A STATE. It stays in the markup on purpose: it means 「거르지
  //    않음」, and putting it in the vocabulary would make the state count and the option
  //    count disagree by one forever.
  ok('D7 ALL survives as the no-filter option', /<option value="ALL"/.test(html));
  // 🔴 A SELECT REFUSES A MISSING VALUE WITHOUT ERROR. The deep link from the health card
  //    assigns `FAILED` to it; if the options had not arrived the assignment leaves `ALL` and
  //    the operator gets the whole list where they asked for one state.
  ok('D8 a filter preset that does not take is not silent',
    /statusFilterSelect\.value !== opts\.statusFilter/.test(js),
    'the deep-link assignment can still fail silently');
  // 🔴 총괄 f063c948e — two sites call the outbox retry route; both read its reply.
  ok('D9 both outbox retry sites read the reply through the judge',
    (js.match(/outboxRetryMessage\(/g) || []).length === 2, (js.match(/outboxRetryMessage\(/g) || []).length);
  // 🔴 총괄 59fa66aaf — the file drawer's title and body come from the one judge, not a fixed «Error».
  ok('D10 the file drawer reads its title and body through the judge',
    /ingestionMessageView\(log\.status, log\.error_message\)/.test(js) && !js.includes('Ingestion Error Message'),
    'the drawer still writes its own title');
  ok('D10b the collector drawer reads its title and body through the judge',
    /collectorMessageView\(col\.last_status, col\.last_error\)/.test(js)
    && !js.includes('Last Collector Execution Error') && !js.includes('Last execution was successful'),
    'the collector drawer still writes its own title or success sentence');
  // 🔴 1f87a0baf — the body is ONE <pre> every drawer writes. A drawer that writes it without setting
  //    its class inherits the neutral colour a success file left, so an error is drawn un-red.
  //    Text is the subject: each top-level function that writes the body also sets its class.
  const writers = js.split(/\n(?=(?:async )?function )/)
    .filter((fn) => /tracebackViewer\.(textContent|innerHTML|appendChild)/.test(fn));
  const unset = writers.filter((fn) => !/tracebackViewer\.className = /.test(fn))
    .map((fn) => fn.slice(0, 60).split('\n')[0]);
  ok('D11 every drawer that writes the body sets its class (writers counted from the file)',
    writers.length > 0 && unset.length === 0, { writers: writers.length, unset });
}

console.log('\n── F. THE FILE DRAWER — its title and body follow the badge\'s tone ───────');
{
  const failed = X.ingestionMessageView('FAILED', 'Parser raised KeyError: lot_id');
  const kept = X.ingestionMessageView('SUCCESS', 'Dropped 3 rows without a key.');
  const clean = X.ingestionMessageView('SUCCESS', '');
  ok('F1 a failure is titled as an error, with its reason',
    failed.title === 'Ingestion error' && failed.body === 'Parser raised KeyError: lot_id', failed);
  ok('F2 a success that carries a sentence is not titled as an error — and shows the sentence',
    kept.title !== failed.title && kept.body === 'Dropped 3 rows without a key.', kept);
  ok('F3 a success with no sentence says it succeeded, under the same title',
    clean.body === 'No message — ingested successfully.' && clean.title === kept.title, clean);
  const blankFailure = X.ingestionMessageView('FAILED', '   ');
  ok('F4 a failure with a blank sentence does not claim it succeeded', !/success/i.test(blankFailure.body), blankFailure);
  const waiting = X.ingestionMessageView('PENDING_RETRY', null);
  ok('F5 a waiting file with no sentence claims neither success nor error',
    !/success/i.test(waiting.body) && waiting.title !== failed.title, waiting);
  ok('F6 the drawer\'s tone is the badge\'s tone for every status',
    ['SUCCESS', 'FAILED', 'PENDING_RETRY', 'QUARANTINED'].every((s) => X.ingestionMessageView(s, 'm').tone === X.retryVerdict(s).tone));
  // 1f87a0baf — only a failure is drawn red; the success and waiting bodies are not.
  ok('F7 the body is red for a failure only',
    JSON.stringify(['FAILED', 'SUCCESS', 'PENDING_RETRY'].map((s) => X.ingestionMessageView(s, 'm').bodyClass))
    === JSON.stringify([X.DRAWER_BODY_CLASS, `${X.DRAWER_BODY_CLASS} is-neutral`, `${X.DRAWER_BODY_CLASS} is-neutral`]),
    ['FAILED', 'SUCCESS', 'PENDING_RETRY'].map((s) => X.ingestionMessageView(s, 'm').bodyClass));
}

console.log('\n── G. THE COLLECTOR DRAWER — the same seat, its own words (lead e1af65168) ──');
{
  // The collector's seven words as the server writes them — FAIL, not the file's FAILED.
  const TABLE = [
    ['PENDING', 'warn'], ['RUNNING', 'warn'], ['SUCCESS', 'ok'], ['FAIL', 'danger'],
    ['SKIPPED', 'warn'], ['orphaned', 'warn'], ['unknown', 'warn'],
  ];
  const views = TABLE.map(([s]) => X.collectorMessageView(s, ''));
  ok('G1 each word reads the tone the table gives — FAIL is a failure',
    JSON.stringify(views.map((v) => v.tone)) === JSON.stringify(TABLE.map(([, t]) => t)), views.map((v) => v.tone));
  ok('G2 ...and that tone is the badge seat\'s own (one mapping)',
    TABLE.every(([s]) => X.collectorMessageView(s, 'm').tone === X.retryVerdict(s).tone));
  ok('G3 only FAIL is titled as an error',
    views.map((v) => v.title).filter((t) => t === 'Last run error').length === 1 && views[3].title === 'Last run error',
    views.map((v) => v.title));
  ok('G4 only SUCCESS says the last run succeeded — not one that never ran, is off or lost its owner',
    views.filter((v) => /succeed/i.test(v.body)).length === 1 && /succeed/i.test(views[2].body), views.map((v) => v.body));
  ok('G5 only FAIL is drawn red, and only FAIL has the red badge',
    views.filter((v) => v.bodyClass === X.DRAWER_BODY_CLASS).length === 1 && views[3].badgeClass === 'badge badge-danger'
    && views[2].badgeClass === 'badge badge-success', views.map((v) => [v.badgeClass, v.bodyClass]));
  ok('G6 a sentence the server wrote is shown as it is',
    X.collectorMessageView('FAIL', ' Cut off by a restart. ').body === 'Cut off by a restart.');
}

console.log('\n── H. EVERY SEAT THAT READS A COLLECTOR STATUS GIVES THE DRAWER\'S ANSWER (lead 457b34131) ──');
{
  const WORDS = ['PENDING', 'RUNNING', 'SUCCESS', 'FAIL', 'SKIPPED', 'orphaned', 'unknown'];
  const drawerFailed = WORDS.filter((s) => X.collectorMessageView(s, '').tone === 'danger').length;
  // the list badge, drawn by the real row renderer
  const listBadge = (s) => (autoUpdateRowHtml({ table_name: 't', script_name: 'x', cron_expression: '*', last_status: s },
    { isActive: true, nextRunText: '', lastRunText: '' }).match(/<span class="(badge [^"]+)">/) || [])[1];
  ok('H1 the collector list badge is the drawer\'s badge for all seven words',
    WORDS.every((s) => listBadge(s) === X.collectorMessageView(s, '').badgeClass), WORDS.map((s) => [s, listBadge(s)]));
  // the Overview line, counted by the real row builder
  const line = autoRow({ auto: { data: WORDS.map((s, i) => ({ table_name: `t${i}`, script_name: 'x', last_status: s })) },
    failed: { data: [] } });
  ok('H2 the Overview line counts the failures the drawer calls failures',
    drawerFailed === 1 && line.facts.includes(`failures ${drawerFailed}`), { drawerFailed, facts: line.facts });
  ok('H3 the section count\'s judge agrees with the drawer',
    WORDS.filter((s) => X.isFailedStatus(s)).length === drawerFailed);
  const js = readFileSync(new URL('../src/admin.js', import.meta.url), 'utf8');
  ok('H4 the Auto Update section count goes through that judge',
    /autoUpdateData\.filter\(c => isFailedStatus\(c\.last_status\)\)/.test(js), 'the section count spells a status itself');
  // 🔴 the order's gate: no seat compares the spelling but this module. Text is the subject.
  const dir = new URL('../src/', import.meta.url);
  const files = readdirSync(dir, { recursive: true }).map(String).filter((f) => f.endsWith('.js'));
  const spelling = files.filter((f) => !f.endsWith('retry_verdict.js')
    && /last_status ===/.test(readFileSync(new URL(f.replace(/\\/g, '/'), dir), 'utf8')));
  ok('H5 no file in client2/src but retry_verdict compares last_status by spelling (files read from the folder)',
    files.length > 20 && spelling.length === 0, { files: files.length, spelling });
}

console.log('\n── E. THE OUTBOX RETRY REPLY — the server\'s status is the verdict ───────');
{
  // The reply as `retry_failed_outbox_events` answers today (8dfd50ab): reset · ended_missing_row · skipped_reexpanded.
  const refused = X.outboxRetryMessage({ status: 'refused', message: 'No matching failed outbox events found.',
    reset: 0, ended_missing_row: 0, skipped_reexpanded: 0 });
  ok('E1 a refused retry is a refusal, never a success', refused.tone === 'error' && refused.refused === true, refused);
  ok('E2 ...and says the server\'s own sentence', refused.text.includes('No matching failed outbox events found.'), refused.text);
  const mixed = X.outboxRetryMessage({ status: 'success', message: 'Reset 1 failed event(s) to PENDING. Skipped 2 collapsed chunk(s).',
    reset: 1, ended_missing_row: 0, skipped_reexpanded: 2 });
  ok('E3 a reset with skips is not a plain success — both halves', mixed.tone === 'warning' && mixed.text.includes('Skipped 2'), mixed);
  const clean = X.outboxRetryMessage({ status: 'success', message: 'Reset 3 failed event(s) to PENDING. Ended 1 row event(s).',
    reset: 3, ended_missing_row: 1, skipped_reexpanded: 0 });
  ok('E4 a reset that also ended a row is a success with the sentence', clean.tone === 'success' && clean.text.includes('Ended 1'), clean);
  ok('E5 an unreadable reply is not a success', X.outboxRetryMessage(null).tone !== 'success', X.outboxRetryMessage(null));
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
    swap("return { tone: 'warning', text: `⏳ Retry waiting — runs when the watcher picks it up${tail}` };",
      "return { tone: 'success', text: `✅ Retry done${tail}` };")],
  ['M5 the server sentence is dropped',
    swap('const tail = serverMessage ? ` — ${serverMessage}` : \'\';', "const tail = '';")],
  ['M6 an absent row is reported as a broken state',
    swap("      return { tone: 'warning', text: status == null", "      return { tone: 'warning', text: false")],
  ['M7 spelling normalisation is dropped, so a lower-case status becomes unknown',
    swap(".trim().toUpperCase();", ";")],
  ['M8 a refused retry reads as a success (the defect f063c948e names)',
    swap("if (reply.status === 'refused') return { tone: 'error', refused: true,",
      "if (reply.status === 'refused') return { tone: 'success', refused: false,")],
  ['M9 the skips are ignored, so a partial reset reads as clean',
    swap('    return skipped > 0', '    return false')],
  ['M10 the drawer title is «error» whatever the status (the defect 59fa66aaf names)',
    swap("title: `${words.subject} ${tone === 'danger' ? 'error' : 'message'}`", 'title: `${words.subject} error`')],
  ['M11 an empty message always claims the file succeeded',
    swap("const empty = tone === 'ok' ?", 'const empty = true ?')],
  ['M12 the server\'s sentence is dropped from the drawer',
    swap('body: said || empty', 'body: empty')],
  ['M13 the collector\'s FAIL is not read as a failure (the spelling e1af65168 names)',
    swap("if (spelled === 'FAILED' || spelled === 'FAIL')", "if (spelled === 'FAILED')")],
  ['M14 every drawer body is drawn red (the colour 1f87a0baf names)',
    swap("bodyClass: tone === 'danger' ? DRAWER_BODY_CLASS :", 'bodyClass: true ? DRAWER_BODY_CLASS :')],
  ['M15 the badge class stops following the tone',
    swap("return `badge badge-${tone === 'ok' ? 'success'", "return `badge badge-${true ? 'success'")],
  ['M16 nothing is counted as a failure (the count 457b34131 moves here)',
    swap("export const isFailedStatus = (status) => retryVerdict(status).tone === 'danger';",
      'export const isFailedStatus = (status) => false;')],
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
    || /Unknown state/.test(M.retryMessage(null).text)
    || M.outboxRetryMessage({ status: 'refused', message: 'm' }).tone !== 'error'
    || M.outboxRetryMessage({ status: 'success', message: 'm', reset: 1, skipped_reexpanded: 1 }).tone !== 'warning'
    || M.ingestionMessageView('SUCCESS', 'm').title === M.ingestionMessageView('FAILED', 'm').title
    || /success/i.test(M.ingestionMessageView('FAILED', '').body)
    || M.ingestionMessageView('SUCCESS', ' m ').body !== 'm'
    || M.collectorMessageView('FAIL', '').tone !== 'danger'
    || M.ingestionMessageView('SUCCESS', 'm').bodyClass === M.ingestionMessageView('FAILED', 'm').bodyClass
    || M.collectorMessageView('FAIL', 'm').badgeClass === M.collectorMessageView('SUCCESS', 'm').badgeClass
    || M.isFailedStatus('FAIL') !== true || M.isFailedStatus('SKIPPED') !== false
    || M.statusBadgeClass('FAIL') === M.statusBadgeClass('SUCCESS');
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
