// truncation_harness — EXACTLY THE CAP IS NOT TRUNCATED.
//
// The map editor asked "was this cut short?" in three spellings, two of them by comparing the
// server's `total` against the rows it returned. That answer costs a full count, and the count
// is most of a first paint. The other two ask for cap+1 rows and look at how many came back,
// which is the same answer without the count. This file is that question, once.
//
// 🔴 THE DISCRIMINATING CASE IS A FULL PAGE. Ask for `cap` and test `length >= cap` and a map
// with exactly cap cells reads as truncated — the editor then demotes a complete set to
// "unknown", stops offering cleanup, and the screen says it does not know something it does.
// Asking for cap+1 and testing `>` is what separates "full" from "there is more".
//
// Every check is paired with a mutant; two controls must escape.
//
// ═══ 🔴 이 파일은 «잘라쓰기»였습니다 (2026-09-06 전환) ═══
// 종전: 소스를 텍스트로 읽어 `export` 를 지우고 vm 컨텍스트에서 돌렸습니다. 그러면 재는 것이
// «동작»이 아니라 «글자 모양»이 됩니다 — 이 모듈이 헬퍼를 하나 import 하게 되는 날
// 「코드가 맞는데」 빨개지고, 반대로 틀렸는데 초록일 수도 있습니다 (소유자 상설 2026-09-02).
//
// 지금:
//   기준선  «그냥 import» 합니다. `truncation.js` 는 export 를 가진 평범한 모듈이라
//           다리조차 필요 없습니다 — 이 모듈이 «import 되라고» 뽑힌 파일이기 때문입니다
//   변이    `importMutated` 가 원본 «전문»에 한 자리만 바꾼 사본을 만들어 import 합니다.
//           잘라내는 양은 «0» 이고, 「변이가 안 먹으면 던진다」가 그 헬퍼 안에 있습니다
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';//
// 🔴 정정 (2026-09-06 오후): 이 파일은 «제가 오늘 만든» 다리를 쓰고 있었습니다. 그런데 그
//    기제는 «이미 있었습니다» — `tests/lib/probe.mjs` (251줄 · 소비자 21). 덧붙이기도,
//    바이트 접두 단언도, 「변이가 안 먹으면 죽는다」도, 의존 모듈 갈아끼우기도 «전부» 거기
//    있습니다. 제가 그것을 안 찾고 두 번째 경로를 지었고, 그게 기준 ④ 위반입니다.
//    -> 정본 하나로 모읍니다. 제 헬퍼는 삭제했습니다.
import * as BASELINE from '../src/truncation.js';

const SRC_PATH = fileURLToPath(new URL('../src/truncation.js', import.meta.url));

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

const rows = (n) => Array.from({ length: n }, (_, i) => ({ i }));
const X = BASELINE;
if (!X || !X.isTruncated) die('truncation.js did not import — its exports moved or renamed.');

const CAP = 2000;

console.log('\n── A. THE QUESTION IT ASKS ─────────────────────────────────────────');
{
  ok('A1 one more than the cap is asked for', X.fetchLimitFor(CAP) === CAP + 1, X.fetchLimitFor(CAP));
  // 🔴 THE PAIR. Either alone passes with `>=` in place; together they do not.
  ok('A2 exactly the cap is NOT truncated', X.isTruncated(rows(CAP), CAP) === false);
  ok('A3 one past the cap IS truncated', X.isTruncated(rows(CAP + 1), CAP) === true);
  ok('A4 fewer than the cap is not truncated', X.isTruncated(rows(3), CAP) === false);
  ok('A5 nothing at all is not truncated', X.isTruncated([], CAP) === false);
  // The rows can be missing entirely when a response has no `data` — that is not "cut short".
  ok('A6 a missing array is not truncated', X.isTruncated(undefined, CAP) === false
    && X.isTruncated(null, CAP) === false);
  ok('A7 an unusable cap answers no rather than throwing',
    X.isTruncated(rows(9), undefined) === false && X.isTruncated(rows(9), -1) === false);
  // 🔴 이 «하나»는 텍스트가 «주어»입니다 (CLAUDE.md 2026-09-03 예외, 단언 단위).
  //    묻는 것이 「무엇을 돌려주나」가 아니라 「이 모듈이 `total` 을 «받지 않나»」이고, 그건
  //    출력으로 관측할 수 없습니다 — 안 쓰는 것은 «안 보이기» 때문입니다. 대리가 아니라 주어입니다.
  const SOURCE_TEXT = readFileSync(new URL('../src/truncation.js', import.meta.url), 'utf8');
  ok('A8 the total is not part of the question',
    !/\btotal\b/.test(SOURCE_TEXT.replace(/^\s*(\/\/|\*|\/\*).*$/gm, '')), 'source mentions total');
}

console.log('\n── B. THE EXTRA ROW IS A SIGNAL, NOT A CELL ────────────────────────');
{
  // Asked for cap+1, so a truncated answer carries one row that must not be drawn.
  ok('B1 a truncated answer is cut back to the cap', X.withinCap(rows(CAP + 1), CAP).length === CAP);
  ok('B2 a full answer is left alone', X.withinCap(rows(CAP), CAP).length === CAP);
  ok('B3 a short answer is left alone', X.withinCap(rows(7), CAP).length === 7);
  ok('B4 a missing array becomes an empty one, not an error', (() => {
    try { return X.withinCap(null, CAP).length === 0; } catch (e) { return false; }
  })());
}

// ── mutants ─────────────────────────────────────────────────────────────────────────
//
// ⚠️ `swap` 은 앵커가 안 맞으면 «죽습니다». 그리고 `importMutated` 가 「사본이 원본과 다른가」를
//    한 번 더 잽니다 — 두 그물이 같은 구멍을 봅니다: «변이가 안 먹었는데 초록».
const swap = (from, to) => (src) => {
  if (!src.includes(from)) die(`mutation anchor stopped matching: ${JSON.stringify(from)}. `
    + 'A harness that goes quiet because it lost the code is worse than no harness.');
  return src.replace(from, to);
};

const DEFECTS = [
  ['M1 a full page reads as truncated (the >= spelling this round removes)',
    swap('return (Array.isArray(rows) ? rows.length : 0) > cap;',
      'return (Array.isArray(rows) ? rows.length : 0) >= cap;')],
  ['M2 the request asks for the cap, so a full page cannot be told from a cut one',
    swap('return cap + 1;', 'return cap;')],
  ['M3 nothing is ever truncated',
    swap('return (Array.isArray(rows) ? rows.length : 0) > cap;', 'return false;')],
  ['M4 the extra row is kept and drawn',
    swap('return rows.length > cap ? rows.slice(0, cap) : rows;', 'return rows;')],
  ['M5 a missing array is treated as a cut-short read',
    swap('return (Array.isArray(rows) ? rows.length : 0) > cap;',
      'return !Array.isArray(rows) || rows.length > cap;')],
  // 🔴 이 변이의 «이름»이 처음엔 틀렸습니다: 가드를 지워도 던지지 않습니다 --
  //    `9 > undefined` 는 그냥 false 입니다. 답이 «갈리는» 곳은 음수 상한이고,
  //    그 입력을 채점기에 안 넣었을 때 이 변이는 그냥 빠져나갔습니다.
  ['M6 a negative cap turns every read into a truncated one',
    swap('if (!Number.isFinite(cap) || cap < 0) return false;', '')],
];

const CONTROLS = [
  ['a local rename', (src) => src.replace(/\bcap\b/g, 'ceiling')],
  ['comments stripped', (src) => src.split('\n')
    .filter((l) => !l.trim().startsWith('//') && !l.trim().startsWith('*')
      && !l.trim().startsWith('/*'))
    .join('\n')],
];

/** 채점기. 기준선과 변이가 «같은 질문»에 답해야 비교가 뜻을 가집니다. */
function verdict(M) {
  return M.fetchLimitFor(CAP) !== CAP + 1
    || M.isTruncated(rows(CAP), CAP) !== false
    || M.isTruncated(rows(CAP + 1), CAP) !== true
    || M.isTruncated([], CAP) !== false
    || M.isTruncated(undefined, CAP) !== false
    || M.isTruncated(rows(9), undefined) !== false
    || M.isTruncated(rows(9), -1) !== false
    || M.withinCap(rows(CAP + 1), CAP).length !== CAP
    || M.withinCap(rows(7), CAP).length !== 7
    || M.withinCap(null, CAP).length !== 0;
}

// 🔴 채점기가 «기준선»에서 조용한지 먼저 봅니다. 여기서 시끄러우면 아래 「잡았다」는 전부
//    변이가 아니라 채점기를 잰 것입니다.
if (verdict(BASELINE)) die('the scorer already fails on the UNMUTATED module — '
  + 'every "caught" below would be scoring the scorer, not the mutant.');

async function score(list, mustCatch, heading) {
  console.log(`\n── ${heading} ─────────────────────────────`);
  let hit = 0;
  for (const [name, mutate] of list) {
    let bad = false;
    try {
      bad = verdict((await loadWithProbe(SRC_PATH, { mutate, tag: 'trunc' })).module);
    } catch (e) {
      // 🔴 「던졌다」와 「틀린 답을 냈다」는 둘 다 «잡힘»이지만, 사본이 아예 «안 만들어진»
      //    것(변이가 안 먹음)은 잡힘이 아닙니다 — 그건 계기 고장이라 죽어야 합니다.
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
