// ingestion_done_stats_harness — 「검증 완료」 IS ONLY TRUE WHEN NOTHING WAS SAID.
//
// A load can SUCCEED and still drop rows. The ingester counts them and composes a sentence for it
// (`_compose_detail`: 「키 결측으로 N행 스킵」, 「파싱 결과 0행 ― 저장된 셀 없음」), and that
// sentence rides the success notification's reason slot all the way to the browser. The card read
// only `status === 'SUCCESS'` and said 「적재 성공 및 정합성 검증 완료」 unconditionally — so a load
// with discarded rows looked complete, and the next stage took it as complete. That is the most
// expensive shape in this queue: it is not silence, it is the opposite claim.
//
// ⛔ AND A SUBTITLE IS NOT A REPAIR. 「검증 완료 (일부 행 제외됨)」 leaves the first clause FALSE.
// When the server has something to say, that IS the answer; the default sentence is for when it
// said nothing.
//
// ═══ THIS FILE IMPORTS ITS SUBJECT ═══
// `utils.js` is importable in node — the `typeof window` guard exists for exactly that reason —
// so nothing here is sliced. Mutants go through `loadWithProbe`, which appends to the original
// bytes rather than cutting them out.
import { loadWithProbe } from './lib/probe.mjs';
import * as BASELINE from '../src/utils.js';
import { fileURLToPath } from 'node:url';

const SRC_PATH = fileURLToPath(new URL('../src/utils.js', import.meta.url));

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
if (!X || !X.ingestionDoneStats || !X.INGESTION_DONE_STATS) {
  die('utils.js did not import — `ingestionDoneStats` moved or renamed.');
}

// The two sentences the composer actually produces, and the join it actually uses.
const ZERO_ROWS = '파싱 결과 0행 ― 저장된 셀 없음(파서가 형식을 거부했을 수 있음, 워처 로그 확인)';
const SKIPPED = '키 결측으로 3행 스킵';
const BOTH = `${ZERO_ROWS} / ${SKIPPED}`;

console.log('\n── A. WHAT THE SERVER SAID IS THE ANSWER ───────────────────────────');
{
  ok('A1 nothing said -> the default sentence',
    X.ingestionDoneStats(null) === X.INGESTION_DONE_STATS);
  ok('A2 an empty string is nothing said too',
    X.ingestionDoneStats('') === X.INGESTION_DONE_STATS
    && X.ingestionDoneStats('   ') === X.INGESTION_DONE_STATS);
  // 🔴 THE ROUND. The count reached the browser and the card talked over it.
  ok('A3 a dropped-row count REPLACES the claim', X.ingestionDoneStats(SKIPPED) === SKIPPED,
    X.ingestionDoneStats(SKIPPED));
  ok('A4 ... and the claim is not left standing beside it',
    !X.ingestionDoneStats(SKIPPED).includes('검증 완료'), X.ingestionDoneStats(SKIPPED));
  ok('A5 a zero-row load does not read as a verified one',
    X.ingestionDoneStats(ZERO_ROWS) !== X.INGESTION_DONE_STATS);
}

console.log('\n── B. THE NUMBER IS AT THE TAIL, SO THE CAP MUST CLEAR IT ──────────');
{
  // ⚠️ THE CAP IS SIZED TO TODAY'S COMPOSER, AND THIS IS THE ASSERTION THAT SAYS SO. The
  //    composer joins its parts with ' / ' and the COUNT comes last, so a cap chosen by feel
  //    would cut off exactly the fact this round exists to carry.
  ok('B1 both parts survive together', X.ingestionDoneStats(BOTH) === BOTH, X.ingestionDoneStats(BOTH));
  ok('B2 the count is still there at the end',
    X.ingestionDoneStats(BOTH).endsWith(SKIPPED));
  ok('B3 an unbounded string is still bounded',
    X.ingestionDoneStats('x'.repeat(900)).length === X.MAX_INGESTION_DONE_STATS);
  ok('B4 the cap is wider than the composer needs, not narrower',
    X.MAX_INGESTION_DONE_STATS > BOTH.length, { cap: X.MAX_INGESTION_DONE_STATS, need: BOTH.length });
}

console.log('\n── C. ONE SENTENCE, ONE HOME ───────────────────────────────────────');
{
  // It was written out twice — the in-progress card's done line and the finish line. Two copies
  // of one sentence drift, and this one is a CLAIM about the data, not decoration.
  ok('C1 the sentence is exported, not spelled twice',
    typeof X.INGESTION_DONE_STATS === 'string' && X.INGESTION_DONE_STATS.length > 0);
  ok('C2 the finish path goes through the function',
    typeof X.ingestionDoneStats === 'function');
}

// ── mutants ─────────────────────────────────────────────────────────────────────────
const swap = (from, to) => (src) => {
  if (!src.includes(from)) die(`mutation anchor stopped matching: ${JSON.stringify(from)}. `
    + 'A harness that goes quiet because it lost the code is worse than no harness.');
  return src.replace(from, to);
};

// 🔴 ONE MUTANT PER PROPERTY. The claim-replacement and the cap-width are different facts and a
//    single mutation cannot redden both.
const DEFECTS = [
  ['M1 the detail is ignored and the claim is made anyway (the original defect)',
    swap('  if (!said) return INGESTION_DONE_STATS;', '  return INGESTION_DONE_STATS;')],
  ['M2 the detail is appended instead of replacing (a subtitle)',
    swap('  if (!said) return INGESTION_DONE_STATS;\n',
      '  if (!said) return INGESTION_DONE_STATS;\n'
      + '  return `${INGESTION_DONE_STATS} (${said})`;\n')],
  ['M3 the cap is narrowed to where it cuts the count off',
    swap('export const MAX_INGESTION_DONE_STATS = 120;',
      'export const MAX_INGESTION_DONE_STATS = 50;')],
  ['M4 the cap is removed, so one long note can run off the card',
    swap('  return said.length > MAX_INGESTION_DONE_STATS\n'
      + '    ? said.slice(0, MAX_INGESTION_DONE_STATS) : said;', '  return said;')],
  ['M5 whitespace-only counts as something said',
    swap('const said = detail == null ? \'\' : String(detail).trim();',
      'const said = detail == null ? \'\' : String(detail);')],
];

const CONTROLS = [
  ['a local rename', (src) => src.replace(/\bsaid\b/g, 'spoken')],
  ['comments stripped', (src) => src.split('\n')
    .filter((l) => !l.trim().startsWith('//') && !l.trim().startsWith('*')
      && !l.trim().startsWith('/*'))
    .join('\n')],
];

function verdict(M) {
  return M.ingestionDoneStats(null) !== M.INGESTION_DONE_STATS
    || M.ingestionDoneStats('   ') !== M.INGESTION_DONE_STATS
    || M.ingestionDoneStats(SKIPPED) !== SKIPPED
    || M.ingestionDoneStats(BOTH) !== BOTH
    || M.ingestionDoneStats('x'.repeat(900)).length !== M.MAX_INGESTION_DONE_STATS;
}

if (verdict(BASELINE)) die('the scorer already fails on the UNMUTATED module — '
  + 'every "caught" below would be scoring the scorer, not the mutant.');

async function score(list, mustCatch, heading) {
  console.log(`\n── ${heading} ─────────────────────────────`);
  let hit = 0;
  for (const [name, mutate] of list) {
    let bad = false;
    try {
      bad = verdict((await loadWithProbe(SRC_PATH, { mutate, tag: 'donestats' })).module);
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
