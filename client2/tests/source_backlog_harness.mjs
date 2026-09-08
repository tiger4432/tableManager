/**
 * 🏷️ C-42 — 「이 소스, 돌 게 있나」. 대상을 IMPORT 해서 잽니다.
 *
 * 🔴 THE THREE STATES ARE THE WHOLE ROUND. A count that is ABSENT and a count that is `0` are
 *    opposite instructions — 「아직 아무도 안 셌다」 versus 「세 봤고 돌 게 없다」 — and the
 *    cheap version of this feature draws both as 0. That reads as 「비었다」 to an operator
 *    who is asking whether anything is waiting, which is the exact question this line answers.
 *
 * 🔴 AND ONE MORE, ADDED WITH THE NEW NAMES (2026-09-09): `rows_remaining` is READ, never
 *    computed. It equals N − M today, which is why a client would be tempted, and the day the
 *    server's definition stops being plain subtraction the arithmetic goes on producing a
 *    confident wrong number with nothing to raise.
 *
 * ⚠️ 서버는 이 셋을 «아직 안 보냅니다». 그래서 이 파일의 픽스처가 계약의 «유일한 재료»이고,
 *    실배선은 서버가 실은 뒤입니다 — 그렇게 지시받았고 그렇게 적습니다.
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
// the three the server will add. Written together because that is how the screen meets them.
const COUNTED = { target_key: 'source_plan|s', status: 'verified', stale: false,
  rows_total: 4200, rows_indexed: 4080, rows_remaining: 120 };
const DONE = { ...COUNTED, rows_indexed: 4200, rows_remaining: 0 };
// A server that does not carry the three at all — today's, and every older one.
const UNCOUNTED = { target_key: 'source_plan|s', status: 'verified', stale: false };

async function score(mutate) {
  pass = 0; failures.length = 0;
  const { probe } = await loadWithProbe(SRC, {
    expose: ['backlogCells', 'hasBacklog', 'BACKLOG_FIELDS'], mutate, tag: 'backlog',
  });
  const cells = probe.backlogCells;
  const has = probe.hasBacklog;
  const textOf = (status, name) => (cells(status).find((c) => c.name === name) || {}).text;

  // ══ ① 계약의 세 이름, 그 순서 ═══════════════════════════════════════════════════════
  eq('A1 the three names are the contract, in order',
    'rows_total,rows_indexed,rows_remaining', probe.BACKLOG_FIELDS.join(','));
  eq('A2 every field gets a cell, counted or not', 3, cells(UNCOUNTED).length);
  // 🔴 THE LABEL IS THE SERVER'S KEY, NOT A TRANSLATION. A translated label goes on looking
  //    right on the day the server renames the field, with the number under the old name.
  ok('A3 the cell carries the name it was sent',
    cells(COUNTED).every((c) => probe.BACKLOG_FIELDS.includes(c.name)));
  // ⚠️ THE CURSOR'S WORDS ARE GONE, NOT RENAMED. `rows_past_cursor`, `rows_before_cursor` and
  //    `caught_up` belonged to a world S-76 retired; keeping one under a new spelling would
  //    keep asking a question nobody answers any more.
  ok('A4 no cursor-world name survives',
    !probe.BACKLOG_FIELDS.some((n) => /cursor|caught/.test(n)), probe.BACKLOG_FIELDS.join(','));

  // ══ ② 안 셈 / 셌는데 0 / 셌고 N — «다른 픽셀» ═══════════════════════════════════════
  eq('B1 a counted number is drawn', '4200', textOf(COUNTED, 'rows_total'));
  eq('B2 a measured ZERO is drawn as zero — somebody counted', '0',
    textOf(DONE, 'rows_remaining'));
  // 🔴 THE ONE THAT MATTERS. Absent is not zero: nobody has looked, and telling an operator
  //    who is asking 「돌 게 있나」 that the answer is 0 is telling them the queue is empty.
  eq('B3 an ABSENT count is a blank, never a zero', '', textOf(UNCOUNTED, 'rows_total'));
  ok('B4 ...and the two are different pixels',
    textOf(DONE, 'rows_remaining') !== textOf(UNCOUNTED, 'rows_remaining'));
  eq('B5 an explicit null is also 「안 셈」', '',
    textOf({ ...COUNTED, rows_total: null }, 'rows_total'));
  eq('B6 a value that is not a number is 「안 셈」, not a drawn string', '',
    textOf({ ...COUNTED, rows_indexed: 'many' }, 'rows_indexed'));

  // ══ ③ 「남은 수」는 «읽습니다» — 안 셈합니다 ═════════════════════════════════════════
  // 🔴 N − M IS RIGHT TODAY, WHICH IS THE WHOLE DANGER. A client that computed it would agree
  //    with the server until the day the definition stops being subtraction, and then disagree
  //    silently and confidently. So a record carrying the two but not the third leaves the
  //    third BLANK.
  eq('C1 with no remaining sent, the cell is blank rather than N − M', '',
    textOf({ rows_total: 4200, rows_indexed: 4080 }, 'rows_remaining'));
  // ⚠️ CONTROL for C1: it must not be blank because the whole row is blank — the other two
  //    are drawn from the same record.
  eq('C2 CONTROL: ...while the two that WERE sent are drawn', '4200',
    textOf({ rows_total: 4200, rows_indexed: 4080 }, 'rows_total'));
  // 🔴 AND THE SERVER'S NUMBER WINS EVEN WHEN IT DISAGREES WITH THE SUBTRACTION. This is the
  //    discriminating case: a client doing arithmetic would draw 120 here, and the ledger said 7.
  eq('C3 a remaining that contradicts N − M is drawn AS SENT', '7',
    textOf({ rows_total: 4200, rows_indexed: 4080, rows_remaining: 7 }, 'rows_remaining'));

  // ══ ④ 안 세었으면 «줄 자체가 없습니다» — 오늘 화면 바이트 동일 ═══════════════════════
  ok('D1 nothing counted, nothing drawn', has(UNCOUNTED) === false);
  ok('D2 one counted field is enough to draw the line',
    has({ ...UNCOUNTED, rows_total: 0 }) === true);
  ok('D3 no record at all draws nothing', has(null) === false && has(undefined) === false);
  ok('D4 CONTROL: a fully counted record does draw', has(COUNTED) === true);

  return { pass, failures: failures.slice() };
}

const base = await score(undefined);
console.log(`\n${base.failures.length === 0 ? '✓' : '✗'} baseline: ${base.pass} passed, `
  + `${base.failures.length} failed`);
console.log(`ASSERTIONS ${base.pass + base.failures.length} ${base.failures.length}`);

const MUTATIONS = [
  // 🔴 THE ONE THE ORDER NAMES: absent drawn as zero.
  ['M1 an uncounted field is drawn as 0, so 「아직 모름」 reads as 「돌 게 없다」',
   s => s.replace("    if (raw === undefined || raw === null) return { name, text: '' };",
                  "    if (raw === undefined || raw === null) return { name, text: '0' };")],
  ['M2 a measured zero stops being drawn, so counted-and-empty looks uncounted',
   s => s.replace('    return { name, text: String(count) };',
                  "    return { name, text: count === 0 ? '' : String(count) };")],
  // 🔴 THE NEW ONE: the client starts doing the ledger's arithmetic.
  ['M3 the client computes the remainder, becoming a second author for it',
   s => s.replace('    const raw = Object.prototype.hasOwnProperty.call(src, name) ? src[name] : undefined;',
                  "    const raw = name === 'rows_remaining' && src.rows_remaining === undefined\n"
                  + "      ? Number(src.rows_total) - Number(src.rows_indexed)\n"
                  + '      : (Object.prototype.hasOwnProperty.call(src, name) ? src[name] : undefined);')],
  ['M4 the presence check becomes a truthiness check, so every zero vanishes',
   s => s.replace('    const raw = Object.prototype.hasOwnProperty.call(src, name) ? src[name] : undefined;',
                  '    const raw = src[name] || undefined;')],
  ['M5 the line is drawn even when nothing was counted',
   s => s.replace("  return backlogCells(status).some((cell) => cell.text !== '');",
                  '  return true;')],
  ['M6 the labels are translated, so a renamed field keeps the old name',
   s => s.replace("export const BACKLOG_FIELDS = Object.freeze(['rows_total', 'rows_indexed', 'rows_remaining']);",
                  "export const BACKLOG_FIELDS = Object.freeze(['전체', '색인', '남음']);")],
  ['M7 a cursor-world name comes back',
   s => s.replace("'rows_remaining']);", "'rows_remaining', 'rows_past_cursor']);")],
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
