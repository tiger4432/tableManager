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
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC_PATH = join(HERE, '..', 'src', 'truncation.js');
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
  const sandbox = { Number, Array, Math, Object, Boolean };
  vm.createContext(sandbox);
  vm.runInContext(`${src.replace(/^export /gm, '')};
    __out = { fetchLimitFor, isTruncated, withinCap };`, sandbox);
  return sandbox.__out;
}

const rows = (n) => Array.from({ length: n }, (_, i) => ({ i }));
const X = load(SOURCE);
if (!X || !X.isTruncated) die('truncation.js did not evaluate — its exports moved or renamed.');

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
  ok('A8 the total is not part of the question',
    !/\btotal\b/.test(SOURCE.replace(/^\s*(\/\/|\*|\/\*).*$/gm, '')), 'source mentions total');
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

function score(list, mustCatch, heading) {
  console.log(`\n── ${heading} ─────────────────────────────`);
  let hit = 0;
  for (const [name, mutate] of list) {
    let bad = false;
    try {
      const M = load(mutate(SOURCE));
      bad = M.fetchLimitFor(CAP) !== CAP + 1
        || M.isTruncated(rows(CAP), CAP) !== false
        || M.isTruncated(rows(CAP + 1), CAP) !== true
        || M.isTruncated([], CAP) !== false
        || M.isTruncated(undefined, CAP) !== false
        || M.isTruncated(rows(9), undefined) !== false
        || M.isTruncated(rows(9), -1) !== false
        || M.withinCap(rows(CAP + 1), CAP).length !== CAP
        || M.withinCap(rows(7), CAP).length !== 7
        || M.withinCap(null, CAP).length !== 0;
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
