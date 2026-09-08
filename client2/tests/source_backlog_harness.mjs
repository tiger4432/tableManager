/**
 * 🏷️ C-42 — 「이 소스, 돌 게 있나」. 대상을 IMPORT 해서 잽니다.
 *
 * 🔴 THE THREE STATES ARE THE WHOLE ROUND. A count that is ABSENT and a count that is `0` are
 *    opposite instructions — 「아직 아무도 안 셌다」 versus 「세 봤고 돌 게 없다」 — and the
 *    cheap version of this feature draws both as 0. That reads as 「비었다」 to an operator
 *    who is asking whether anything is waiting, which is the exact question this line exists
 *    to answer.
 *
 * Run:  node client2/tests/source_backlog_harness.mjs [--mutate]
 */
import { loadWithProbe } from './lib/probe.mjs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src', 'source_backlog.js');

let pass = 0;
const failures = [];
const ok = (name, cond, detail = '') => {
  if (cond) { pass += 1; console.log(`  PASS ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name}${detail ? ' — ' + detail : ''}`); }
};
const eq = (name, expected, actual) => ok(name, actual === expected,
  `expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);

// The record as `verificationOf` hands it over — the S-46 fields the row already reads, plus
// the four S-69 will add. Written together because that is how the screen meets them.
const COUNTED = { target_key: 'source_plan|s', status: 'verified', stale: false,
  rows_total: 4200, rows_past_cursor: 120, rows_before_cursor: 7, caught_up: false };
const CAUGHT = { ...COUNTED, rows_past_cursor: 0, rows_before_cursor: 0, caught_up: true };
// An older server, before S-69: the four keys are simply not there.
const UNCOUNTED = { target_key: 'source_plan|s', status: 'verified', stale: false };

async function score(mutate) {
  pass = 0; failures.length = 0;
  const { probe } = await loadWithProbe(SRC, {
    expose: ['backlogCells', 'hasBacklog', 'BACKLOG_FIELDS'], mutate, tag: 'backlog',
  });
  const cells = probe.backlogCells;
  const has = probe.hasBacklog;
  const textOf = (status, name) => (cells(status).find((c) => c.name === name) || {}).text;
  const noteOf = (status, name) => (cells(status).find((c) => c.name === name) || {}).note;

  // ══ ① 계약의 네 이름, 그 순서 ═══════════════════════════════════════════════════════
  eq('A1 the four names are the contract, in order',
    'rows_total,rows_past_cursor,rows_before_cursor,caught_up',
    probe.BACKLOG_FIELDS.join(','));
  eq('A2 every field gets a cell, counted or not', 4, cells(UNCOUNTED).length);
  // 🔴 THE LABEL IS THE SERVER'S KEY, NOT A TRANSLATION. A translated label goes on looking
  //    right on the day the server renames the field, with the number under the old name.
  ok('A3 the cell carries the name it was sent',
    cells(COUNTED).every((c) => probe.BACKLOG_FIELDS.includes(c.name)));

  // ══ ② 안 셈 / 셌는데 0 / 셌고 N — «다른 픽셀» ═══════════════════════════════════════
  eq('B1 a counted number is drawn', '4200', textOf(COUNTED, 'rows_total'));
  eq('B2 a measured ZERO is drawn as zero — somebody counted', '0',
    textOf(CAUGHT, 'rows_past_cursor'));
  // 🔴 THE ONE THAT MATTERS. Absent is not zero: nobody has looked, and telling an operator
  //    who is asking 「돌 게 있나」 that the answer is 0 is telling them the queue is empty.
  eq('B3 an ABSENT count is a blank, never a zero', '', textOf(UNCOUNTED, 'rows_total'));
  ok('B4 ...and the two are different pixels',
    textOf(CAUGHT, 'rows_past_cursor') !== textOf(UNCOUNTED, 'rows_past_cursor'));
  eq('B5 an explicit null is also 「안 셈」', '',
    textOf({ ...COUNTED, rows_total: null }, 'rows_total'));

  // ══ ③ 「커서 앞」— 낱말 하나, 값 «옆»에, 0 보다 클 때만 ══════════════════════════════
  eq('C1 rows the cursor already passed carry the reason word', '커서 앞',
    noteOf(COUNTED, 'rows_before_cursor'));
  // ⚠️ 0 에 붙이면 그 낱말이 «칸의 제목»이 되고, 제목은 이미 이름이 하고 있습니다.
  eq('C2 ...and zero of them carries none', '', noteOf(CAUGHT, 'rows_before_cursor'));
  eq('C3 an absent one carries none either', '', noteOf(UNCOUNTED, 'rows_before_cursor'));
  ok('C4 no other cell grows a word', cells(COUNTED)
    .filter((c) => c.name !== 'rows_before_cursor').every((c) => c.note === ''));
  // 🔴 문장 ⛔. The whole line is names, numbers and one word; anything longer means the
  //    screen went back to explaining instead of showing.
  // ⚠️ MEASURED BY LENGTH, NOT BY WHITESPACE. The first version of this line forbade a space
  //    and reddened on 「커서 앞」 — the very word the ruling names. A label may be two
  //    syllables with a space in it; what it may not be is a sentence.
  ok('C5 nothing drawn is a sentence',
    cells(COUNTED).every((c) => c.note.length <= 6 && c.text.length <= 8
      && !/[.·:]/.test(c.note)));

  // ══ ④ caught_up 은 «참/거짓만» 답합니다 ═════════════════════════════════════════════
  eq('D1 caught up says so in one word', '따라잡음', textOf(CAUGHT, 'caught_up'));
  eq('D2 ...and not caught up says the thing the operator asked about', '남음',
    textOf(COUNTED, 'caught_up'));
  ok('D3 the two are different words', textOf(CAUGHT, 'caught_up') !== textOf(COUNTED, 'caught_up'));
  // ⚠️ A truthy value that is not `true` is NOT 「따라잡음」 — folding it in would put a word
  //    in the server's mouth. Absent, a string, a number: all 「안 셈」.
  eq('D4 anything that is not a boolean is 「안 셈」', '',
    textOf({ ...COUNTED, caught_up: 'yes' }, 'caught_up'));
  eq('D5 CONTROL: and false is not swallowed with it', '남음',
    textOf({ ...COUNTED, caught_up: false }, 'caught_up'));

  // ══ ⑤ 안 세었으면 «줄 자체가 없습니다» — 오늘 화면 바이트 동일 ═══════════════════════
  ok('E1 nothing counted, nothing drawn', has(UNCOUNTED) === false);
  ok('E2 one counted field is enough to draw the line', has(UNCOUNTED) === false
    && has({ ...UNCOUNTED, rows_total: 0 }) === true);
  ok('E3 no record at all draws nothing', has(null) === false && has(undefined) === false);
  ok('E4 CONTROL: a fully counted record does draw', has(COUNTED) === true);

  return { pass, failures: failures.slice() };
}

const base = await score(undefined);
console.log(`\n${base.failures.length === 0 ? '✓' : '✗'} baseline: ${base.pass} passed, `
  + `${base.failures.length} failed`);
console.log(`ASSERTIONS ${base.pass + base.failures.length} ${base.failures.length}`);

const MUTATIONS = [
  // 🔴 THE ONE THE ORDER NAMES: absent drawn as zero.
  ['M1 an uncounted field is drawn as 0, so 「아직 모름」 reads as 「돌 게 없다」',
   s => s.replace("    if (raw === undefined || raw === null) return { name, text: '', note: '' };",
                  "    if (raw === undefined || raw === null) return { name, text: '0', note: '' };")],
  ['M2 a measured zero stops being drawn, so counted-and-empty looks uncounted',
   s => s.replace('    const note = ', '    if (count === 0) return { name, text: \'\', note: \'\' };\n    const note = ')],
  ['M3 the reason word rides on every count, so it becomes a column title',
   s => s.replace("count > 0 ? BEHIND_MARK : ''", "BEHIND_MARK")],
  ['M4 the reason word attaches to the wrong count',
   s => s.replace("name === 'rows_before_cursor' && count > 0", "name === 'rows_past_cursor' && count > 0")],
  ['M5 any truthy value becomes 「따라잡음」, which the server never said',
   s => s.replace('      if (raw === true) return { name, text: CAUGHT_UP, note: \'\' };',
                  '      if (raw) return { name, text: CAUGHT_UP, note: \'\' };')],
  ['M6 the line is drawn even when nothing was counted',
   s => s.replace("  return backlogCells(status).some((cell) => cell.text !== '');",
                  '  return true;')],
  ['M7 the labels are translated, so a renamed field keeps the old name',
   s => s.replace("  'rows_total', 'rows_past_cursor', 'rows_before_cursor', 'caught_up',",
                  "  '전체', '커서 뒤', '커서 앞', '상태',")],
];

if (process.argv.includes('--mutate')) {
  console.log('\n── MUTATIONS (each must turn the harness RED) ──');
  let caught = 0; const green = [];
  for (const [name, apply] of MUTATIONS) {
    let r;
    try { r = await score(apply); }
    catch (e) { console.log(`  ~ ${name} -> harness THREW (${e && e.message})`); caught++; continue; }
    if (r.failures.length === 0) { console.log(`  ✗ ${name} -> STILL GREEN`); green.push(name); continue; }
    caught++;
    console.log(`  ✓ ${name} -> ${r.failures.length} failure(s): ${r.failures.sort().join(' ')}`);
  }
  console.log(`\nmutations: ${caught}/${MUTATIONS.length} caught (${MUTATIONS.length} declared)`);
  if (green.length) { console.log(`  ✗ undetected: ${green.join(' | ')}`); process.exit(1); }
}

process.exit(base.failures.length === 0 ? 0 : 1);
