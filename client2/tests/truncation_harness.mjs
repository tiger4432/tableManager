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
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
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
if (!X || !X.isTruncated || !X.saysTruncated) die('truncation.js did not import — its exports moved or renamed.');

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

console.log('\n── C. WHAT THE WIRE SAYS ABOUT ITSELF ───────────────────');
{
  // The bool shape: four live readers see this today, and it is the ONLY reason `!!` was right.
  ok('C1 a bool true is truncated', X.saysTruncated(true) === true);
  ok('C2 a bool false is not', X.saysTruncated(false) === false);

  // The axis-object shape (`GET /api/ledger/subgraph`). It arrives on EVERY response.
  const cut = { depth: false, nodes: true, edges: false, claims: false, actions: false,
    reason: 'nodes' };
  const whole = { depth: false, nodes: false, edges: false, claims: false, actions: false,
    reason: null };
  ok('C3 an object that names a reason is truncated', X.saysTruncated(cut) === true);
  // \u{1f534} THE TRAP, AND THE POINT OF THIS ROUND. The object is present, so anything that
  //    reads its PRESENCE or its truthiness answers "cut" on a complete walk. Every screen
  //    would say 「절단됨」 forever, and nothing would throw.
  ok('C4 an object with nothing cut is NOT truncated', X.saysTruncated(whole) === false,
    X.saysTruncated(whole));
  ok('C5 the two objects are told apart', X.saysTruncated(cut) !== X.saysTruncated(whole));

  // \u26a0\ufe0f ABSENT IS NOT FALSE. A server that never had the field has not said "complete".
  ok('C6 a missing field is unknown, not false', X.saysTruncated(undefined) === null
    && X.saysTruncated(null) === null);
  // The record-ARRAY shape is out of scope this round (no live reader, senders uncounted).
  // It must not be guessed at: an unknown shape answers unknown rather than "complete".
  ok('C7 a shape it does not know answers unknown', X.saysTruncated([{ role: 'x', cap: 1 }]) === null);
  ok('C8 a string is unknown too, not truthy', X.saysTruncated('true') === null);

  // 🔴 THE SIXTH SHAPE — the canonical axis map (`event_constants.truncated_note`), which this
  //    reader answered WRONG rather than "unknown": it has no top-level `reason`, so reading
  //    that field called a truncated response complete. Measured 2026-09-07 (ruling 99).
  const note = (cut, reason = null) => ({ cut, omitted: null, reason: cut ? reason : null });
  const axisCut = { rows: note(true, 'cap'), columns: note(false) };
  const axisWhole = { rows: note(false), columns: note(false) };
  ok('C9 an axis map with one axis cut is truncated', X.saysTruncated(axisCut) === true,
    X.saysTruncated(axisCut));
  ok('C10 an axis map with nothing cut is NOT truncated', X.saysTruncated(axisWhole) === false,
    X.saysTruncated(axisWhole));
  ok('C11 the two axis maps are told apart', X.saysTruncated(axisCut) !== X.saysTruncated(axisWhole));
  // 🔴 `cut` IS THE JUDGEMENT, NOT `reason`. The server only carries a reason when there is one
  //    (`reason if (reason and cut) else None`), and a cut with no reason is a real shape --
  //    a caller that knows only the budget bit. Reading `reason` would call that complete.
  ok('C12 a cut with no reason is still cut', X.saysTruncated({ rows: note(true) }) === true);
  // ⚠️ THE FIVE OLDER SHAPES MUST NOT MOVE. The old subgraph map's axes are BOOLEANS beside a
  //    top-level reason; the new one's are OBJECTS. That is what tells them apart, and this
  //    line fails if the axis branch starts swallowing the older map.
  ok('C13 the older boolean-axis map still answers from its top-level reason',
    X.saysTruncated({ depth: true, nodes: false, reason: 'depth' }) === true
    && X.saysTruncated({ depth: false, nodes: false, reason: null }) === false);
}

console.log('\n── D. THE TWO READERS OF ONE ROUTE GET ONE VERDICT ───────────');
{
  // \u{1f534} TEXT IS THE SUBJECT HERE, NOT A PROXY (CLAUDE.md 2026-09-03, per ASSERTION).
  //    The question is 「does this site go through the one place」, and a site that does NOT
  //    is invisible in output — it just keeps answering correctly until the shape changes.
  //    The same exception the `total` check above already stands on.
  const read = (rel) => readFileSync(new URL(rel, import.meta.url), 'utf8');
  const CALL = 'saysTruncated(body && body.truncated)';
  const suggest = read('../src/value_suggest.js');
  const editor = read('../src/map_editor.js');
  const timeline = read('../src/timeline.js');
  ok('D1 the value-suggest reader goes through it', suggest.includes(CALL));
  ok('D2 the map-editor reader of THE SAME ROUTE goes through it', editor.includes(CALL));
  ok('D3 both history readers go through it',
    (timeline.split(CALL).length - 1) === 2, timeline.split(CALL).length - 1);
  // \u{1f534} AND NOBODY BYPASSES IT. Importing without calling is the shape the order named:
  //    a one place that some sites do not reach is a comment, not a contract.
  const BYPASS = /(?:!!\s*\()?\s*body\s*&&\s*body\.truncated\s*\)?(?!\s*\))/;
  for (const [name, src] of [['value_suggest', suggest], ['map_editor', editor],
    ['timeline', timeline]]) {
    const stray = src.split('\n').filter((l) => /body\.truncated/.test(l)
      && !l.includes('saysTruncated') && !l.trim().startsWith('//') && !l.trim().startsWith('*'));
    ok(`D4 ${name} has no site that reads the field directly`, stray.length === 0, stray);
  }
  void BYPASS;
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
  // \u{1f534} TWO ARMS, ON PURPOSE. One mutant cannot show that the two branches answer two
  //    different questions \u2014 deleting either one has to redden a DIFFERENT assertion, or
  //    "one place knows every shape" is a claim the harness never measured.
  // 🔴 THE ANCHOR MOVED WHEN THE SIXTH SHAPE LANDED, and it is kept SINGLE-LINE for the reason
  //    M10 records below. Disabling the branch head kills both object shapes at once, which is
  //    what "the object shape is not understood" means.
  ['M7 the object shape is not understood (the walk goes quiet)',
    swap("  if (said && typeof said === 'object' && !Array.isArray(said)) {", '  if (false) {')],
  ['M8 the bool shape is not understood (every other route goes quiet)',
    swap("  if (typeof said === 'boolean') return said;", '')],
  // The trap this round exists to close: presence read as truth.
  ['M9 an object that arrived is read as an object that says yes',
    swap('return Boolean(said.reason);', 'return true;')],
  ['M10 an unknown shape is folded into "complete"',
    // 🔴 A SINGLE-LINE ANCHOR ON PURPOSE. The first spelling of this mutant
    //    carried a newline and died on this CRLF checkout - the harness went quiet
    //    for a reason that had nothing to do with the code (C-32, five harnesses today).
    swap('  return null;', '  return false;')],
  // ── the sixth shape's own arms (ruling 99) ───────────────────────────────────────────
  // 🔴 M11 IS THE DEFECT ITSELF, restored: without the axis branch the map falls through to
  //    the top-level `reason`, which the canonical shape does not have, and a CUT response
  //    comes back `false`. Not "unknown" — WRONG, and silently.
  ['M11 the axis map is not understood, so a cut list reads as complete',
    swap('    if (axes.length) return axes.some(a => a.cut === true);', '')],
  // M12 keeps the branch but stops reading the judgement, so "cut" and "not cut" stop being
  //     told apart. One mutant cannot show that; this is why the scorer holds BOTH axis lines.
  ['M12 every axis map answers the same, cut or not',
    swap('return axes.some(a => a.cut === true);', 'return false;')],
  // M13: reading `reason` instead of `cut` is the plausible near-miss — the server only carries
  //      a reason when it has one, so a budget-bit caller's cut would read as complete.
  ['M13 the axis judgement is taken from `reason` instead of `cut`',
    swap('return axes.some(a => a.cut === true);', 'return axes.some(a => Boolean(a.reason));')],
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
    || M.withinCap(null, CAP).length !== 0
    // the wire shapes \u2014 each line is the only one some mutant above moves
    || M.saysTruncated(true) !== true
    || M.saysTruncated(false) !== false
    || M.saysTruncated({ nodes: true, reason: 'nodes' }) !== true
    || M.saysTruncated({ nodes: false, reason: null }) !== false
    || M.saysTruncated(undefined) !== null
    || M.saysTruncated([{ role: 'x' }]) !== null
    // the sixth shape — the canonical axis map. Two lines, because "cut" and "not cut" must
    // stay TOLD APART: a mutant that answers one constant passes either line alone.
    || M.saysTruncated({ rows: { cut: true, omitted: null, reason: 'cap' } }) !== true
    || M.saysTruncated({ rows: { cut: false, omitted: null, reason: null } }) !== false
    // 🔴 THE DISCRIMINATING INPUT, and the scorer did not have it at first: on a cut that
    //    carries a reason, `cut` and `reason` AGREE, so a mutant that reads the wrong one
    //    walked straight through (M13 escaped until this line existed). A cut with no reason
    //    is a real shape — the server writes `reason if (reason and cut) else None` — and it
    //    is the only input on which the two spellings part.
    || M.saysTruncated({ rows: { cut: true, omitted: null, reason: null } }) !== true;
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

// ═══ 클라 7 ㈩ — 값 제안이 잘렸다는 문장이 «하나»인가 ═════════════
//
// 🔴 이 파일의 머리말이 이름 댈 잔여입니다 — «같은 라우트»의 같은 칸을 두 화면이 각자
//    읽고 «다른 두 문장»을 만들었습니다. 갈라져도 «오류가 안 납니다».
// ⚠️ 아래 둘은 «텍스트가 주어»인 단언입니다(드리프트 오라클) — 사본이 «다시 태어나는» 것은
//    어느 행동 검사로도 안 보입니다. 그래서 모집단을 «소스에» 묻고, 그렇게 적습니다.
{
  const note = BASELINE.suggestTruncatedNote;
  ok('K1 the note names the count it is about', String(note(7)).includes('7'));
  // ⛔ 다음 행동을 떼면 「자막 단 실패」가 됩니다 — 이 줄이 그것을 막습니다.
  ok('K2 ...and keeps the NEXT ACTION, which is what makes it more than a label',
    String(note(7)).includes('입력'));
  ok('K3 a different count gives a different sentence, so the number is not decorative',
    note(7) !== note(8));

  const SRC = fileURLToPath(new URL('../src/', import.meta.url));
  const LINE_COMMENT = new RegExp('(^|[^:])//[^' + String.fromCharCode(10) + ']*', 'g');
  const strip = (t) => t.replace(/\/\*[\s\S]*?\*\//g, '').replace(LINE_COMMENT, '$1');
  const files = [];
  const walk = (d) => {
    for (const e of readdirSync(d, { withFileTypes: true })) {
      if (e.isDirectory()) walk(join(d, e.name));
      else if (e.name.endsWith('.js')) files.push(join(d, e.name));
    }
  };
  walk(SRC);
  ok(`K4 CONTROL: the sweep saw the source tree (${files.length} files)`, files.length > 50);
  const writers = files.filter((f) => {
    const t = strip(readFileSync(f, 'utf8'));
    return t.includes('더 입력하면');
  }).map((f) => f.replace(SRC, ''));
  // 오직 이 모듈만이 그 문장을 씁니다.
  ok(`K5 exactly one file writes that sentence (${writers.join(', ')})`,
    writers.length === 1 && writers[0].includes('truncation.js'));
  // 🔴 그리고 예전의 둘째 문장은 «어느 파일에도» 없습니다.
  const oldSecond = files.filter((f) => strip(readFileSync(f, 'utf8')).includes('내려왔습니다'));
  ok('K6 the second sentence is gone from the source entirely', oldSecond.length === 0);
}

const caught = await score(DEFECTS, true, 'defect mutants (each must be CAUGHT)');
const escaped = await score(CONTROLS, false, 'control mutants (each must ESCAPE)');

console.log(`\n${passed} passed, ${failed} failed; ${caught}/${DEFECTS.length} defects caught; `
  + `${escaped}/${CONTROLS.length} controls escaped.`);
console.log(`ASSERTIONS ${passed} ${failed}`);
if (failed) process.exit(1);
