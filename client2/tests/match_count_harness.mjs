// match_count_harness — NONE, UNKNOWN AND A NUMBER ARE THREE DIFFERENT ANSWERS.
//
// The match count leaves the first paint: rows are drawn, and `total` arrives from a second
// request afterwards. Until it lands the screen holds a state it never had before — «we do not
// know yet» — and this repo's oldest rule is that an absence and an unknown may not paint the
// same pixel. `0` under «Matches:» says "your filter matched nothing". Painting that while the server is
// still counting is a lie the operator acts on: they widen a filter that was never narrow.
//
// 🔴 THE SECOND HALF IS PAGING, and it fails silently in the other direction. `Math.ceil(null /
// limit) || 1` is 1, so an uncounted table reads as "one page", `currentPage >= totalPages` turns
// true, and NEXT IS DISABLED — the operator cannot leave page one while the count is in flight.
// Nothing throws. The button is simply grey, and grey is what "you are on the last page" looks
// like too.
//
// Every check is paired with a mutant; two controls must escape.
//
// ═══ 🔴 이 파일은 «잘라쓰기»였습니다 (2026-09-06 전환, truncation 과 «같은 틀») ═══
// 기준선  «그냥 import». `match_count.js` 는 export 를 가진 평범한 모듈입니다
// 변이    `importMutated` 가 원본 «전문»에 한 자리만 바꾼 사본을 만들어 import 합니다
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';//
// 🔴 정정 (2026-09-06 오후): 이 파일은 «제가 오늘 만든» 다리를 쓰고 있었습니다. 그런데 그
//    기제는 «이미 있었습니다» — `tests/lib/probe.mjs` (251줄 · 소비자 21). 덧붙이기도,
//    바이트 접두 단언도, 「변이가 안 먹으면 죽는다」도, 의존 모듈 갈아끼우기도 «전부» 거기
//    있습니다. 제가 그것을 안 찾고 두 번째 경로를 지었고, 그게 기준 ④ 위반입니다.
//    -> 정본 하나로 모읍니다. 제 헬퍼는 삭제했습니다.
import * as BASELINE from '../src/match_count.js';
import { localStamp } from '../src/server_time.js';

const SRC_PATH = fileURLToPath(new URL('../src/match_count.js', import.meta.url));

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

/** An element stub with what `setMatchCount` touches beyond textContent - its mark and its hover line. */
const mkEl = () => {
  const flags = new Set();
  const attrs = {};
  return {
    textContent: '', attrs, style: {},
    classList: { toggle(name, on) { if (on) flags.add(name); else flags.delete(name); } },
    setAttribute(k, v) { attrs[k] = String(v); },
    removeAttribute(k) { delete attrs[k]; },
    has: (name) => flags.has(name),
  };
};

const X = BASELINE;
if (!X || !X.matchCountText) die('match_count.js did not import — its exports moved or renamed.');

const LIMIT = 50;

console.log('\n── A. THREE ANSWERS, THREE TEXTS ───────────────────────────────────');
{
  const counted = X.matchCountText(12);
  const none = X.matchCountText(0);
  const unknown = X.matchCountText(null);
  ok('A1 a number is the number of rows', counted === '12 rows', counted);
  ok('A2 zero is zero rows', none === '0 rows', none);
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
    !none.has('is-counting') && none.textContent === '0 rows',
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

// ── D. THE COUNT IS «AS OF» A TIME (ㄱ-1: implementer A 67e5e9ccd, lead 10-13) ─────────────────
const AT = '2026-10-13T07:00:00+00:00';
const NOW = Date.parse(AT) + 10000;
const WHOLE = { total: 4012334, capped: false, counted_at: AT, count_seconds: 1.6, counting: false };
function dChecks(M) {
  const el = mkEl();
  let now = NOW;
  const timers = [];
  const stopped = [];
  const clock = { now: () => now, every: (fn, ms) => { timers.push({ fn, ms }); return timers.length; }, stop: (h) => stopped.push(h) };
  M.setMatchCount(el, WHOLE, clock);
  const first = [el.textContent, el.attrs.title];
  const floorCounted = el.style.minWidth;
  now += 50000;
  for (const tm of timers) tm.fn();
  const ticked = [el.textContent, timers.map((tm) => tm.ms)];
  M.setMatchCount(el, { total: 10000, capped: true }, clock);
  const next = [el.textContent, stopped.slice(), timers.length, el.matchAgeTimer, 'title' in el.attrs];
  const floorCapped = el.style.minWidth;
  M.setMatchCount(el, { total: null, counting: true }, clock);
  const floorCounting = el.style.minWidth;
  M.setMatchCount(el, null, clock);
  const floorUnasked = el.style.minWidth;
  M.setMatchCount(el, { failed: { reason: 'HTTP 503' } }, clock);
  const failedFloor = el.style.minWidth;
  const capFull = M.pagingView({ total: 10000, capped: true }, 0, LIMIT, LIMIT);
  const capShort = M.pagingView({ total: 10000, capped: true }, 250, LIMIT, 20);
  const countingShort = M.pagingView({ total: null, counting: true }, 0, LIMIT, 7);
  const cOf = (x) => M.countOf(x);
  return [
    ['D1 the table whole: its count and how long ago it was counted', M.matchCountText(WHOLE, NOW) === '4,012,334 rows · 10s ago', M.matchCountText(WHOLE, NOW)],
    ['D2 a narrowed read past the cap: 10,000+, no age', M.matchCountText({ count: { total: 10000, capped: true, counted_at: AT } }, NOW) === '10,000+ rows'],
    ['D3 an answer not counted yet says it is counting - the server\'s counting and a deferred page alike; a read never asked stays «…»',
      M.matchCountText({ total: null, counting: true }, NOW) === 'Counting rows…' && M.matchCountText({ data: [], total: null }) === 'Counting rows…'
        && M.matchCountText(null) === M.COUNTING],
    ['D4 one row is a row', M.matchCountText(1) === '1 row'],
    ['D5 the number alone, for a word before it: 10,050+ · 4,012,334', M.countNumberText({ total: 10050, capped: true }) === '10,050+' && M.countNumberText(4012334) === '4,012,334'],
    ['D6 hover: when it was counted (the viewer\'s zone) and the seconds it took', first[1] === `Counted ${localStamp(AT)} · took 1.6 s`, first[1]],
    ['D7 the age is drawn again every 10 s from the same count - nothing asked', first[0] === '4,012,334 rows · 10s ago' && ticked[0] === '4,012,334 rows · 1m ago'
      && JSON.stringify(ticked[1]) === '[10000]', ticked],
    ['D8 the next count stops the old timer; a count with no age starts none and has no hover line',
      next[0] === '10,000+ rows' && JSON.stringify(next[1]) === '[1]' && next[2] === 1 && next[3] === null && next[4] === false, next],
    ['D9 10,000+: 200+ pages, next stays on a full page and goes off on a short one', capFull.totalPagesText === '200+' && capFull.totalPages === null
      && capFull.nextDisabled === false && capShort.nextDisabled === true, [capFull, capShort]],
    ['D10 still counting: a short page is the end too', countingShort.nextDisabled === true && countingShort.totalPagesText === M.COUNTING, countingShort],
    // A kept count can be old (lead 0fd18ae19 5): its last page that came back full is not the end.
    ['D11 an exact count ends by its own pages and a short page - a full last page keeps next on',
      M.pagingView({ total: 100, capped: false }, 50, LIMIT, 50).nextDisabled === false
      && M.pagingView({ total: 100, capped: false }, 50, LIMIT, 30).nextDisabled === true
      && M.pagingView({ total: 100, capped: false }, 50, LIMIT).nextDisabled === true
      && M.pagingView(120, 50, LIMIT, 50).nextDisabled === false],
    // A count the server could not make says so (lead 0fd18ae19 6) - neither «Counting rows…» nor a number.
    ['D15 a failed count: «Count failed (<reason>)», not counting; a held count with a failed recount stays its number',
      M.matchCountText({ table_name: 't', total: null, capped: false, counted_at: null, count_seconds: null, counting: false,
        failed: { reason: 'count stopped after 10 s', at: AT } }) === 'Count failed (count stopped after 10 s)'
      && M.countOf({ total: null, failed: { reason: 'x' } }).counting === false
      && M.matchCountText({ total: 7, failed: { reason: 'x', at: AT } }) === '7 rows'],
    ['D16 ... and its floor is the words, so a narrow bar never cuts it to a lone «…»', failedFloor === '13ch', failedFloor],
    ['D17 ... and its hover is the whole line and when, as a narrow bar cuts the reason',
      M.matchCountTitle({ total: null, failed: { reason: 'count stopped after 10 s', at: AT } }) === `Count failed (count stopped after 10 s) · ${localStamp(AT)}`
      && M.matchCountTitle({ total: null, failed: { reason: 'HTTP 503' } }) === 'Count failed (HTTP 503)'],
    ['D12 a live row moves an exact count, not a 10,000+ one nor an unknown one', M.shiftCount(WHOLE, 1).total === 4012335
      && M.shiftCount({ total: 10000, capped: true }, -1).total === 10000 && M.shiftCount(null, 1).total === null && M.shiftCount({ total: 0 }, -1).total === 0],
    ['D14 a narrow bar cuts the tail, never the number: the floor is the number and its «…» - 4,012,334 · 10,000+ · Counting · a lone «…»',
      JSON.stringify([floorCounted, floorCapped, floorCounting, floorUnasked]) === JSON.stringify(['10ch', '8ch', '9ch', '1ch']),
      [floorCounted, floorCapped, floorCounting, floorUnasked]],
    ['D13 the shapes the server sends read alike - /data\'s count, /data/count\'s answer, a plain number',
      cOf({ data: [], total: 7, count: { total: 7, capped: false, counted_at: AT } }).countedAt === AT
        && cOf({ table_name: 't', total: 7, counted_at: AT, counting: false }).countedAt === AT && cOf(7).total === 7 && cOf(7).countedAt === null],
  ];
}
console.log('\n── D. THE COUNT IS «AS OF» A TIME ─────────────────────────────────');
for (const [name, cond, saw] of dChecks(X)) ok(name, cond, saw);

// ── mutants ─────────────────────────────────────────────────────────────────────────
const swap = (from, to) => (src) => {
  if (!src.includes(from)) die(`mutation anchor stopped matching: ${JSON.stringify(from)}. `
    + 'A harness that goes quiet because it lost the code is worse than no harness.');
  return src.replace(from, to);
};

const DEFECTS = [
  ['M1 an unknown count falls back to zero',
    swap('const total = isCounted(c.total) ? c.total : null;', 'const total = isCounted(c.total) ? c.total : 0;')],
  ['M2 the counting mark is blank, so unknown reads as an empty field',
    swap("export const COUNTING = '…';", "export const COUNTING = '';")],
  ['M3 anything non-null counts, so `null` prints itself',
    swap('return typeof total === \'number\' && Number.isFinite(total);',
      'return total !== null;')],
  ['M4 paging works out the page count the old way, so unknown becomes one page',
    swap('const totalPages = counted ? (Math.ceil(total / pageLimit) || 1) : null;',
      'const totalPages = Math.ceil(total / pageLimit) || 1;')],
  ['M5 next is switched off while the count is unknown',
    swap('nextDisabled: counted ? currentPage >= totalPages && !(isCounted(shown) && shown >= pageLimit) : isCounted(shown) && shown < pageLimit,',
      'nextDisabled: currentPage >= totalPages,')],
  ['M6 the element mark is set by truthiness, so a real zero reads as still counting',
    swap("if (el.classList) el.classList.toggle('is-counting', c.total === null);",
      "if (el.classList) el.classList.toggle('is-counting', !c.total);")],
  // ── ㄱ-1 (lead 10-13) ──
  ['N1 10,000+ loses its +', swap("${c.capped ? '+' : ''}", '')],
  ['N2 the age is not said', swap('return at ? `${rows} · ${ageText(Math.max(0, (now - at.getTime()) / 1000))} ago` : rows;', 'return rows;')],
  ['N3 a capped count says an age', swap('const at = c.capped ? null : parseServerInstant(c.countedAt);', 'const at = parseServerInstant(c.countedAt);')],
  ['N4 a read never asked says it is counting', swap('return c.counting ? countingText(unit) : COUNTING;', 'return countingText(unit);')],
  ['N5 the age is never drawn again', swap('el.matchAgeTimer = c.countedAt && !c.capped ? clock.every(draw, AGE_EVERY_MS) : null;', 'el.matchAgeTimer = null;')],
  ['N6 the old timer runs on beside the new count', swap('  if (el.matchAgeTimer) clock.stop(el.matchAgeTimer);\n', '')],
  ['N7 the timer draws the age it had', swap("const draw = () => { el.textContent = matchCountText(c, clock.now(), (el.dataset && el.dataset.unit) || 'row'); };",
    "const drawn = matchCountText(c, clock.now(), (el.dataset && el.dataset.unit) || 'row'); const draw = () => { el.textContent = drawn; };")],
  ['N8 10,000+ is taken for an exact count, so paging ends at its 200 pages', swap('const counted = total !== null && !capped;', 'const counted = total !== null;')],
  ['N9 a 10,000+ page that came back short still offers next', swap('isCounted(shown) && shown < pageLimit,', 'false,')],
  ['N10 a live row moves a 10,000+ count', swap('return c.total === null || c.capped ? c :', 'return c.total === null ? c :')],
  ['N11 /data\'s count is not read', swap("(x.count !== null && typeof x.count === 'object' ? x.count : x)", 'x')],
  ['N13 the bar has no floor, so a narrow one cuts the number', swap("  if (el.style) el.style.minWidth = `${floor.length + (floor === el.textContent ? 0 : 1)}ch`;\n", '')],
  ['N14 the floor leaves no room for the «…», so the ellipsis eats the last digit', swap('(floor === el.textContent ? 0 : 1)', '0')],
  ['N12 the hover line drops the seconds it took', swap("${c.seconds === null ? '' : ` · took ${c.seconds} s`}", '')],
  ['N15 an exact count\'s last page that came back full offers no next', swap('currentPage >= totalPages && !(isCounted(shown) && shown >= pageLimit)', 'currentPage >= totalPages')],
  ['N16 a failed count reads as still counting', swap('  if (c.failed) return c.failed.reason ? `${COUNT_FAILED} (${c.failed.reason})` : COUNT_FAILED;\n', '')],
  ['N17 a failed count\'s floor is a lone «…»', swap(': c.failed ? COUNT_FAILED : c.counting', ': c.counting')],
  ['N18 a failed count has no hover, so a cut reason is lost', swap('  if (c.failed) return c.failed.at ? `${matchCountText(c)} · ${localStamp(c.failed.at)}` : matchCountText(c);\n', '')],
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

/** 채점기. 기준선과 변이가 «같은 질문»에 답해야 비교가 뜻을 가집니다. */
function verdict(M) {
  const el0 = mkEl(); M.setMatchCount(el0, 0);
  const elNull = mkEl(); M.setMatchCount(elNull, null);
  const unknown = M.pagingView(null, 0, LIMIT);
  const none = M.pagingView(0, 0, LIMIT);
  const counted = M.pagingView(120, 0, LIMIT);
  return M.matchCountText(12) !== '12 rows'
    || M.matchCountText(0) !== '0 rows'
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
    || counted.nextDisabled !== false
    || dChecks(M).some(([, cond]) => !cond);
}

// 🔴 채점기가 «기준선»에서 조용한지 먼저 봅니다. 여기서 시끄러우면 아래 「잡았다」는 전부
//    변이가 아니라 채점기를 잰 것입니다.
if (verdict(BASELINE)) die('the scorer already fails on the UNMUTATED module — '
  + 'every "caught" below would be scoring the scorer, not the mutant.');

async function score(list, mustCatch, heading) {
  console.log(`
── ${heading} ─────────────────────────────`);
  let hit = 0;
  for (const [name, mutate] of list) {
    let bad = false;
    try {
      bad = verdict((await loadWithProbe(SRC_PATH, { mutate, tag: 'matchcount' })).module);
    } catch (e) {
      // 🔴 「던졌다」와 「틀린 답을 냈다」는 둘 다 «잡힘»이지만, 변이가 «안 먹은» 것은
      //    잡힘이 아닙니다 — 그건 계기 고장이라 죽어야 합니다.
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
