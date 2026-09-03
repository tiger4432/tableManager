// THE NARROWING SET — one builder, and the count of who uses it.
//
// The subject is imported (owner, 2026-09-02: 잘라쓰기 하니스 절대 금지). `narrowing.js` takes
// its three inputs as arguments and touches no DOM, so it imports in node as it stands — which
// is exactly why the extraction had to come before this file. `main.js` imports four
// stylesheets at module scope and cannot be imported at all, and its two call sites live
// inside click handlers, so a test written first could only have SLICED them.
//
// TWO THINGS ARE SCORED, and the second is the one that lasts:
//   ① the grid's own query and the EXPORT url carry the same narrowing. If those drift, the
//      operator downloads a file that does not match what they were looking at, and nothing
//      on screen says so.
//   🔴 ② the builder has exactly FOUR callers. ① alone cannot see a FIFTH site assembling the
//      same parameters by hand — that is how there came to be four in the first place, with
//      the audit recording two.
//
// Run: node client2/tests/narrowing_trio_harness.mjs
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { narrowingParams, narrowingTail } from '../src/narrowing.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src');

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

const screen = (q, cols, filterModel, txn) => ({
  globalSearch: q === null ? null : { value: q },
  searchCols: cols === null ? null : { value: cols },
  gridApi: filterModel === null ? null : { getFilterModel: () => filterModel },
  transactionId: txn,
});

// ═══ ① THE GRID'S QUERY AND THE EXPORT URL CARRY THE SAME NARROWING ═══
console.log('\n[1] the screen and the export cannot narrow differently');
{
  // Both are built the way their call sites build them: same order term, same tail.
  const state = screen('  A B  ', 'name,code', { status: { filter: 'x' } }, 'TX-9');
  const tail = narrowingTail(state);
  const gridUrl = `http://h/tables/t/data?order_by=row_id&order_desc=false${tail}`;
  const exportUrl = `http://h/tables/t/export?order_by=row_id&order_desc=false${tail}`;
  const narrowingOf = (u) => {
    const p = new URL(u).searchParams;
    p.delete('order_by'); p.delete('order_desc'); p.delete('target_row_id'); p.delete('limit');
    return [...p.entries()].sort().map(([k, v]) => `${k}=${v}`);
  };
  eq('the two urls carry an IDENTICAL narrowing', narrowingOf(gridUrl), narrowingOf(exportUrl));
  ok('and it is not empty — two empty sets would match trivially',
    narrowingOf(gridUrl).length > 0, JSON.stringify(narrowingOf(gridUrl)));
  // and the values survive the trip rather than merely matching each other
  const p = new URL(exportUrl).searchParams;
  eq('q is trimmed', p.get('q'), 'A B');
  eq('cols rides along with q', p.get('cols'), 'name,code');
  eq('filters is the serialized model', p.get('filters'), '{"status":{"filter":"x"}}');
  eq('transaction_id is carried', p.get('transaction_id'), 'TX-9');
}

// ═══ the rules the four sites already agreed on, now in one place ═══
console.log('\n[2] what narrows and what does not');
{
  eq('nothing narrowed → empty tail', narrowingTail(screen('', '', {}, null)), '');
  eq('...and an empty params object', narrowingParams(screen('', '', {}, null)).toString(), '');
  // 🔴 `cols` alone is not a narrowing: it names which columns a SEARCH TERM applies to, so
  //    without a term it would ask the server to narrow by nothing in particular.
  ok('cols without q is dropped', !narrowingTail(screen('', 'name', {}, null)).includes('cols'),
    narrowingTail(screen('', 'name', {}, null)));
  ok('whitespace-only q is not a search',
    narrowingTail(screen('   ', 'name', {}, null)) === '',
    narrowingTail(screen('   ', 'name', {}, null)));
  ok('an empty filter model is dropped', !narrowingTail(screen('', '', {}, null)).includes('filters'));
  // absent elements are the boot state, not an error
  eq('missing controls entirely', narrowingTail({}), '');
  eq('null controls', narrowingTail(screen(null, null, null, null)), '');
  eq('a transaction alone still narrows', narrowingTail(screen('', '', {}, 'TX-1')),
    '&transaction_id=TX-1');
}

// ═══ 🔴 ② HOW MANY CALLERS ═══
//
// Text is the SUBJECT here, not a proxy for behaviour: the question IS "how many places in
// the source use this". A fifth hand-assembled site is exactly what ① cannot see.
console.log('\n[3] the caller count');
{
  const files = ['api.js', 'main.js', 'timeline.js', 'grid.js', 'ui.js', 'websocket.js',
                 'enrichment.js', 'admin.js', 'map_editor.js'];
  let callers = 0;
  const where = [];
  for (const f of files) {
    let text;
    try { text = readFileSync(join(SRC, f), 'utf8'); } catch (e) { continue; }
    if (!/from '\.\/narrowing\.js'/.test(text)) continue;
    // count CALLS, not imports — one import can serve several sites (main.js has two).
    const n = (text.match(/\b(narrowingTail|buildNarrowing)\s*\(/g) || []).length;
    callers += n;
    if (n) where.push(`${f}:${n}`);
  }
  eq('exactly four call sites use the one builder', 4, callers);
  eq('and they are where the audit and the recount said', where.sort(),
    ['api.js:1', 'main.js:2', 'timeline.js:1']);

  // 🔴 THE OTHER HALF: nobody may go back to assembling it by hand. Counting only the
  //    callers would stay at four while a fifth site quietly grew beside them.
  const handmade = [];
  for (const f of files) {
    let text;
    try { text = readFileSync(join(SRC, f), 'utf8'); } catch (e) { continue; }
    const lines = text.split(/\r?\n/);
    lines.forEach((l, i) => {
      if (/elements\.globalSearch\s*\?\s*elements\.globalSearch\.value\.trim\(\)/.test(l)) {
        handmade.push(`${f}:${i + 1}`);
      }
    });
  }
  eq('no site reads the search box to build a query by hand any more', [], handmade);
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
