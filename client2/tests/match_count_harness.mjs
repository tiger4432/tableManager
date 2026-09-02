// match_count_harness — NONE, UNKNOWN AND A NUMBER ARE THREE DIFFERENT ANSWERS.
//
// The match count leaves the first paint: rows are drawn, and `total` arrives from a second
// request afterwards. Until it lands the screen holds a state it never had before — «we do not
// know yet» — and this repo's oldest rule is that an absence and an unknown may not paint the
// same pixel. `Matches: 0` says "your filter matched nothing". Painting that while the server is
// still counting is a lie the operator acts on: they widen a filter that was never narrow.
//
// 🔴 THE SECOND HALF IS PAGING, and it fails silently in the other direction. `Math.ceil(null /
// limit) || 1` is 1, so an uncounted table reads as "one page", `currentPage >= totalPages` turns
// true, and NEXT IS DISABLED — the operator cannot leave page one while the count is in flight.
// Nothing throws. The button is simply grey, and grey is what "you are on the last page" looks
// like too.
//
// Every check is paired with a mutant; two controls must escape.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC_PATH = join(HERE, '..', 'src', 'match_count.js');
const SOURCE = readFileSync(SRC_PATH, 'utf8').replace(/\r\n/g, '\n');

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

function load(src) {
  const sandbox = { Number, String, Math, Object, Boolean, JSON };
  vm.createContext(sandbox);
  const body = src.replace(/^export /gm, '');
  vm.runInContext(`${body};
    __out = { COUNTING, isCounted, matchCountText, setMatchCount, pagingView };`, sandbox);
  return sandbox.__out;
}

/** An element stub with the one thing `setMatchCount` touches beyond textContent. */
const mkEl = () => {
  const flags = new Set();
  return {
    textContent: '',
    classList: { toggle(name, on) { if (on) flags.add(name); else flags.delete(name); } },
    has: (name) => flags.has(name),
  };
};

const X = load(SOURCE);
if (!X || !X.matchCountText) die('match_count.js did not evaluate — its exports moved or renamed.');

const LIMIT = 50;

console.log('\n── A. THREE ANSWERS, THREE TEXTS ───────────────────────────────────');
{
  const counted = X.matchCountText(12);
  const none = X.matchCountText(0);
  const unknown = X.matchCountText(null);
  ok('A1 a number is the number', counted === 'Matches: 12', counted);
  ok('A2 zero is zero', none === 'Matches: 0', none);
  // 🔴 THE PAIR THIS FILE EXISTS FOR. Either of these alone passes with the defect in place.
  ok('A3 an unknown count is neither of those', unknown !== none && unknown !== counted, unknown);
  ok('A4 ... and it says it is still counting', unknown.includes(X.COUNTING), unknown);
  // `undefined` is what a missing field actually arrives as, and NaN is what parsing it wrong
  // produces. Both are "we do not know", and both used to print themselves into the sentence.
  ok('A5 undefined reads as unknown too', X.matchCountText(undefined) === unknown, X.matchCountText(undefined));
  ok('A6 ... and so does NaN', X.matchCountText(Number.NaN) === unknown, X.matchCountText(Number.NaN));
  ok('A7 the mark is not the empty string, which would read as a blank',
    typeof X.COUNTING === 'string' && X.COUNTING.length > 0, X.COUNTING);
}

console.log('\n── B. THE ELEMENT IS MARKED, AND ZERO IS NOT UNKNOWN ───────────────');
{
  const unknown = mkEl();
  X.setMatchCount(unknown, null);
  ok('B1 an unknown count marks the element', unknown.has('is-counting'), unknown.textContent);
  const counted = mkEl();
  X.setMatchCount(counted, 7);
  ok('B2 a number clears the mark', !counted.has('is-counting'), counted.textContent);
  // 🔴 THE FALSY TRAP: `!total` is true for 0, so a truthiness test marks a real, complete,
  //    empty result as "still counting" — and the operator waits for a number that never comes.
  const none = mkEl();
  X.setMatchCount(none, 0);
  ok('B3 zero is a COUNTED answer and carries no mark',
    !none.has('is-counting') && none.textContent === 'Matches: 0',
    { mark: none.has('is-counting'), text: none.textContent });
  ok('B4 a missing element is not an error', (() => {
    try { X.setMatchCount(null, 3); return true; } catch (e) { return false; }
  })());
}

console.log('\n── C. PAGING: UNKNOWN IS NOT ONE PAGE ──────────────────────────────');
{
  const counted = X.pagingView(120, 0, LIMIT);
  ok('C1 a counted total gives its own page count', counted.totalPages === 3, counted);
  ok('C2 ... and next is alive before the last page', counted.nextDisabled === false, counted);
  const lastPage = X.pagingView(120, 100, LIMIT);
  ok('C3 ... and dead on it', lastPage.nextDisabled === true && lastPage.currentPage === 3, lastPage);

  // 🔴 THE DEFECT. `Math.ceil(null / 50) || 1` is 1, so this used to say "one page" and switch
  //    NEXT OFF while the count was still in flight.
  const unknown = X.pagingView(null, 0, LIMIT);
  ok('C4 an uncounted total is not a page count', unknown.totalPages === null, unknown);
  ok('C5 ... and next stays alive, because we do not know that this is the last page',
    unknown.nextDisabled === false, unknown);
  ok('C6 ... and the page total says it is counting, not "1"',
    unknown.totalPagesText === X.COUNTING, unknown.totalPagesText);
  ok('C7 prev still obeys the page while unknown',
    unknown.prevDisabled === true && X.pagingView(null, 50, LIMIT).prevDisabled === false, unknown);

  // The other side of the same pair: a real zero IS one page, and next IS dead.
  const none = X.pagingView(0, 0, LIMIT);
  ok('C8 a counted zero is one page and next is dead',
    none.totalPages === 1 && none.nextDisabled === true && none.totalPagesText === '1', none);
  ok('C9 ... so zero and unknown do not paint the same paging',
    none.totalPagesText !== unknown.totalPagesText
    && none.nextDisabled !== unknown.nextDisabled, [none, unknown]);
}

// ── mutants ─────────────────────────────────────────────────────────────────────────
const swap = (from, to) => (src) => {
  if (!src.includes(from)) die(`mutation anchor stopped matching: ${JSON.stringify(from)}. `
    + 'A harness that goes quiet because it lost the code is worse than no harness.');
  return src.replace(from, to);
};

const DEFECTS = [
  ['M1 an unknown count falls back to zero',
    swap('return `Matches: ${isCounted(total) ? total : COUNTING}`;',
      'return `Matches: ${isCounted(total) ? total : 0}`;')],
  ['M2 the counting mark is blank, so unknown reads as an empty field',
    swap("export const COUNTING = '…';", "export const COUNTING = '';")],
  ['M3 anything non-null counts, so `null` prints itself',
    swap('return typeof total === \'number\' && Number.isFinite(total);',
      'return total !== null;')],
  ['M4 paging works out the page count the old way, so unknown becomes one page',
    swap('const totalPages = counted ? (Math.ceil(total / pageLimit) || 1) : null;',
      'const totalPages = Math.ceil(total / pageLimit) || 1;')],
  ['M5 next is switched off while the count is unknown',
    swap('nextDisabled: counted ? currentPage >= totalPages : false,',
      'nextDisabled: currentPage >= totalPages,')],
  ['M6 the element mark is set by truthiness, so a real zero reads as still counting',
    swap("if (el.classList) el.classList.toggle('is-counting', !isCounted(total));",
      "if (el.classList) el.classList.toggle('is-counting', !total);")],
  ['M7 NaN is treated as a counted number',
    swap('typeof total === \'number\' && Number.isFinite(total)',
      "typeof total === 'number'")],
];

const CONTROLS = [
  ['a local rename', (src) => src.replace(/\bcounted\b/g, 'known')],
  ['comments stripped', (src) => src.split('\n')
    .filter((l) => !l.trim().startsWith('//') && !l.trim().startsWith('*')
      && !l.trim().startsWith('/*'))
    .join('\n')],
];

function score(list, mustCatch, heading) {
  console.log(`\n── ${heading} ─────────────────────────────`);
  let hit = 0;
  for (const [name, mutate] of list) {
    let bad = false;
    try {
      const M = load(mutate(SOURCE));
      const el0 = mkEl(); M.setMatchCount(el0, 0);
      const elNull = mkEl(); M.setMatchCount(elNull, null);
      const unknown = M.pagingView(null, 0, LIMIT);
      const none = M.pagingView(0, 0, LIMIT);
      const counted = M.pagingView(120, 0, LIMIT);
      bad = M.matchCountText(12) !== 'Matches: 12'
        || M.matchCountText(0) !== 'Matches: 0'
        || M.matchCountText(null) === M.matchCountText(0)
        || !M.matchCountText(null).includes(M.COUNTING)
        || String(M.COUNTING).length === 0
        || M.matchCountText(Number.NaN) !== M.matchCountText(null)
        || elNull.has('is-counting') !== true
        || el0.has('is-counting') !== false
        || unknown.totalPages !== null
        || unknown.nextDisabled !== false
        || unknown.totalPagesText !== M.COUNTING
        || none.totalPages !== 1
        || none.nextDisabled !== true
        || counted.totalPages !== 3
        || counted.nextDisabled !== false;
    } catch (e) {
      bad = true;
    }
    if (bad === mustCatch) { hit++; console.log(`  ${mustCatch ? 'caught ' : 'escaped'} ${name}`); }
    else { failed++; console.log(`  ${mustCatch ? 'ESCAPED' : 'CAUGHT '} ${name}  <- wrong`); }
  }
  return hit;
}

const caught = score(DEFECTS, true, 'defect mutants (each must be CAUGHT)');
const escaped = score(CONTROLS, false, 'control mutants (each must ESCAPE)');

console.log(`\n${passed} passed, ${failed} failed; ${caught}/${DEFECTS.length} defects caught; `
  + `${escaped}/${CONTROLS.length} controls escaped.`);
console.log(`ASSERTIONS ${passed} ${failed}`);
if (failed) process.exit(1);
