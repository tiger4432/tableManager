// truncation_carriers_harness — THE FIELDS THAT SAY "THIS LIST IS A SAMPLE" NOW HAVE A READER,
// AND THE READER THEY LEANED ON IS NO LONGER DEAD.
//
// The server caps `created_logs` at 500 and sends the pre-truncation total as `total_log_count`.
// Measured 2026-09-07: four senders put it on the wire and the client read it ZERO times, so a
// change of 65,000 rows appended 500 lines of history and the timeline showed them as 「what
// changed」 — a sample wearing the population's clothes.
//
// 🔴 AND THE COMPENSATION WAS DEAD. Where the server caps a list it sends `batch_refresh_required`
// so the client reloads instead. That branch called `window.triggerHistoryReloadDebounced`, which
// is assigned NOWHERE in this client — the guard was always false and the reload never ran, while
// the same file imports the real function and calls it correctly 148 lines earlier. One capability,
// two spellings, and the dead one was load-bearing.
//
// ⚠️ WHY THE PREDICATE IS NOT IN `truncation.js`. That module answers the same question from
// `(rows, cap)` and its header REFUSES to take a `total` — taking one would force a full count,
// which is the cost it exists to avoid — and its harness pins that with an assertion that the word
// `total` does not appear in the file. Putting this there would have reddened a rule that is right.
// So the comparison lives where the wire lands, and this file scores it there.
//
// ⚠️ AND WHAT THAT COSTS. `websocket.js` cannot be imported in node (it pulls the grid and the DOM
// at module scope), so section A scores its SOURCE — text as the subject, 「does this site ask」,
// not a proxy for behaviour. Section B is the stronger half: it reads the BUNDLE, where the
// bundler is the oracle for whether a line is reachable at all.
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

let passed = 0;
let failed = 0;

function ok(name, cond, saw) {
  if (cond) { passed++; console.log(`  ok   ${name}`); }
  else { failed++; console.log(`  FAIL ${name}${saw === undefined ? '' : `  saw: ${JSON.stringify(saw)}`}`); }
}

const raw = readFileSync(new URL('../src/websocket.js', import.meta.url), 'utf8');
// \u{1f534} COMMENTS ARE NOT CODE, AND THIS FILE LEARNED THAT THE HARD WAY. The repair's own
//    comment CITES the dead spelling it removed ("it went through `window.…`") and names
//    `deleted_row_ids` while explaining why that one needs nothing — so scoring the raw source
//    found both and reported the defect as still present. A citation is not a call. Same shape as
//    the C-33 counter, which counted four retired bodies quoted in the new module's docstring.
const src = raw.split('\n')
  .filter((l) => !l.trim().startsWith('//') && !l.trim().startsWith('*')
    && !l.trim().startsWith('/*'))
  .join('\n');

console.log('\n── A. THE CARRIER IS READ WHERE THE LIST LANDS ─────────────────────');
{
  ok('A1 the pre-truncation total is read', src.includes('msg.total_log_count'));
  // 🔴 THE COMPARISON, NOT THE PRESENCE. A field that is read and then not compared to the list
  //    it qualifies is the same silence with an extra variable in it.
  ok('A2 it is compared against what actually arrived',
    /createdLogs\.length\s*<\s*totalLogs/.test(src), 'nothing compares the two');
  // ⚠️ ABSENT IS NOT COMPLETE. An older server sends no total; `|| 0` would have turned 「말 안
  //    함」 into 「안 잘렸음」 and this whole round back into silence.
  ok('A3 an absent total is not read as "not truncated"',
    /totalLogs\s*!=\s*null/.test(src), 'the absent case is folded into false');
  // 🔴 AND THE VALUE IS TAKEN AS IT ARRIVED. A3 alone pins a SPELLING, and a mutant that
  //    kept that spelling while defaulting the value (`msg.total_log_count || 0`) walked straight
  //    through it: `0 != null` is true and `length < 0` is false, so an absent total read as
  //    「안 잘렸음」 again with the guard still visibly in place. The property is that nothing
  //    stands between the field and the comparison.
  ok('A3b the total is read with no falsy default',
    /const totalLogs = msg\.total_log_count;/.test(src)
    && !/total_log_count\s*(\|\||\?\?)/.test(src),
    'something defaults the total before it is compared');
  ok('A4 and being short triggers the reload the server expects',
    /if \(logsTruncated\) triggerHistoryReloadDebounced\(\)/.test(src));
}

console.log('\n── B. THE DEAD SPELLING IS GONE ────────────────────────────────────');
{
  ok('B1 the never-assigned window spelling is no longer called',
    !src.includes('window.triggerHistoryReloadDebounced'),
    'the dead spelling is still there');
  ok('B2 and nothing assigns it, which is why it was dead',
    !/window\.triggerHistoryReloadDebounced\s*=/.test(src));
  ok('B3 the live import is what gets called',
    /^import \{[^}]*triggerHistoryReloadDebounced/m.test(src)
    && (src.split('triggerHistoryReloadDebounced();').length - 1) >= 2);
}

console.log('\n── B-bis. WHAT THE SHIPPED BUNDLE SAYS (EVIDENCE, NOT A VERDICT) ───');
{
  // 🔴 THE BUNDLER IS THE ORACLE FOR REACHABILITY - source grep only sees the chain I thought
  //    of. Property names survive minification and identifiers do not, so these are the
  //    spellings worth measuring.
  // ⚠️ BUT THIS IS NOT SCORED. `client2/dist` is built by ONE lane and this round is forbidden
  //    to build it, so the shipped bundle necessarily predates this repair. Asserting on it
  //    would make this harness red for a build that has not happened yet - a red that is not
  //    about the code. The numbers are printed so the next reader can check them AFTER the
  //    build, and the expected transition is stated here:
  //        total_log_count                       0 -> at least 1
  //        window.triggerHistoryReloadDebounced  2 -> 0
  const distDir = fileURLToPath(new URL('../dist/assets', import.meta.url));
  const bundles = existsSync(distDir)
    ? readdirSync(distDir).filter(f => f.endsWith('.js'))
      .map(f => readFileSync(path.join(distDir, f), 'utf8')) : [];
  const count = (needle) => bundles.reduce(
    (n, b) => n + b.split(needle).length - 1, 0);
  for (const needle of ['total_log_count', 'window.triggerHistoryReloadDebounced',
    'created_logs', 'batch_refresh_required']) {
    console.log(`  ..   shipped bundle: ${needle} = ${count(needle)}`);
  }
  ok('B4 there is a shipped bundle to look at', bundles.length > 0, bundles.length);
}

console.log('\n── C. THE SIBLING CARRIERS ARE ALREADY COMPENSATED ─────────────────');
{
  // 🔵 MEASURED BEFORE BUILDING ANYTHING FOR THEM. `deleted_row_ids_omitted` and
  //    `scope.delete_ids_omitted` count ids the delete broadcast withheld — and where the server
  //    withholds them it sends `batch_refresh_required` INSTEAD of the capped list. The client
  //    never reads `deleted_row_ids` at all, so there is nothing there to correct; what had to
  //    work was the refresh branch, and that is what B1/B2 above are about.
  ok('C1 the refresh event is still handled', src.includes("event === 'batch_refresh_required'"));
  ok('C2 the deleted-id list has no reader to mislead', !src.includes('deleted_row_ids'));
}

console.log(`\n${passed} passed, ${failed} failed.`);
console.log(`ASSERTIONS ${passed} ${failed}`);
if (failed) process.exit(1);
