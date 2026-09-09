/**
 * 🏷️ C-42 — 「이 소스, 돌 게 있나」. 대상을 IMPORT 해서 잽니다.
 *
 * 🔴 THE FIXTURES ARE THE ROUTE'S OWN SHAPE, copied off `GET /api/ledger/declaration` on
 *    2026-09-09 rather than off the sentence describing it. That mattered twice already: the
 *    counts are not numbers but `{estimate, exact, method, measured_at}` envelopes, and a
 *    THIRD of this box's sources answer with a REFUSAL and no counts at all — 15 sources, 11
 *    counted, 4 refused. A harness built from the description would have scored four blanks
 *    and called that correct.
 *
 * 🔴 FOUR STATES, AND THREE OF THEM COLLAPSE IF NOBODY IS WATCHING:
 *      키 없음 / refused / 0 / N. 「못 센다」와 「안 셌다」를 같은 빈 칸으로 그리면
 *      고칠 수 있는 것을 기다리게 만듭니다 — 서버가 고칠 자리까지 문장으로 줬는데도.
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

const AT = '2026-09-09T01:30:31.658998+00:00';
const box = (estimate, method, exact = true) => ({ estimate, exact, method, measured_at: AT });
// `die_inspection`, verbatim in shape — a source that is fully translated.
const COUNTED = { source: 'die_inspection', relation: 'inspection_run', measured_at: AT,
  relation_rows: box(117742, 'count(*)'),
  indexed_rows: box(117742, 'count(distinct row_id)'),
  not_yet: box(0, 'relation_rows - indexed_rows') };
const BEHIND = { ...COUNTED, indexed_rows: box(117000, 'count(distinct row_id)'),
  not_yet: box(742, 'relation_rows - indexed_rows') };
// `bonded_from`, verbatim in shape — the census could not be taken at all.
const REFUSED = { source: 'bonded_from', relation: 'bonding_die_from_core', measured_at: AT,
  refused: 'no_row_id',
  remedy: "expose the base table's row_id column on 'bonding_die_from_core': declare it in "
    + 'table_config as a view column of type string, and this count can then say which rows '
    + 'are already translated.' };

async function score(mutate) {
  pass = 0; failures.length = 0;
  const { probe } = await loadWithProbe(SRC, {
    expose: ['backlogCells', 'hasBacklog', 'censusRefusal', 'BACKLOG_FIELDS', 'MEASURED_AT'],
    mutate, tag: 'backlog',
  });
  const cells = probe.backlogCells;
  const has = probe.hasBacklog;
  const refusalOf = probe.censusRefusal;
  const textOf = (census, name) => (cells(census).find((c) => c.name === name) || {}).text;

  // ══ ① 계약의 이름과 그 순서 ═════════════════════════════════════════════════════════
  eq('A1 the three counts are the contract, in order',
    'relation_rows,indexed_rows,not_yet', probe.BACKLOG_FIELDS.join(','));
  eq('A2 four cells: the three counts and WHEN they were taken', 4, cells(COUNTED).length);
  eq('A3 the fourth is the stamp', probe.MEASURED_AT, cells(COUNTED)[3].name);
  ok('A4 no cursor-world name survives',
    !probe.BACKLOG_FIELDS.some((n) => /cursor|caught/.test(n)), probe.BACKLOG_FIELDS.join(','));

  // ══ ② 봉투를 «연다» — 수는 `estimate` 안에 있습니다 ═════════════════════════════════
  // 🔴 THE COUNTS ARE NOT NUMBERS ON THE WIRE. Reading the envelope as a number yields NaN,
  //    which this file renders as a blank — safe, and permanently empty. That is what the
  //    first wiring did, and only reading the real response caught it.
  eq('B1 the count comes out of the envelope', '117742', textOf(COUNTED, 'relation_rows'));
  eq('B2 a measured ZERO is drawn as zero — somebody counted', '0', textOf(COUNTED, 'not_yet'));
  eq('B3 ...and a real remainder is drawn', '742', textOf(BEHIND, 'not_yet'));
  eq('B4 the stamp is carried as sent, never reworded', AT, textOf(COUNTED, 'measured_at'));

  // ══ ③ 「추정」과 「정확」이 «같은 픽셀이 아니다» ══════════════════════════════════════
  // 🔴 `measured()` EXISTS FOR THIS: 「약 1,300만」 becoming 「1,300만」. One symbol, not a
  //    sentence, and only when `exact` is EXPLICITLY false — an absent `exact` said nothing.
  eq('C1 an estimate is marked', '≈900',
    textOf({ ...COUNTED, relation_rows: box(900, 'pg_class.reltuples', false) }, 'relation_rows'));
  eq('C2 an exact count carries no mark', '117742', textOf(COUNTED, 'relation_rows'));
  eq('C3 an unstated `exact` is not read as an estimate', '900',
    textOf({ ...COUNTED, relation_rows: { estimate: 900, method: 'x' } }, 'relation_rows'));

  // ══ ④ 「셀 수 없다」는 «빈 칸이 아니다» ═════════════════════════════════════════════
  // 🔴 THE STATE THE DESCRIPTION DID NOT HAVE, and a third of this box's sources are in it.
  //    Drawn as a blank it reads as 「아직 안 셌다」 and nobody fixes the thing the server
  //    already told them how to fix.
  ok('D1 a refused census is named', refusalOf(REFUSED) !== null);
  eq('D2 ...by the server\'s own reason word', 'no_row_id', refusalOf(REFUSED).reason);
  ok('D3 ...and carries the gate\'s sentence verbatim',
    refusalOf(REFUSED).remedy === REFUSED.remedy, refusalOf(REFUSED).remedy.slice(0, 40));
  ok('D4 a counted census is not a refusal', refusalOf(COUNTED) === null);
  ok('D5 ...nor is an absent one', refusalOf(undefined) === null && refusalOf(null) === null);
  // ⚠️ 거절이어도 «시각»은 남습니다 — 「언제 못 셌는지」도 사실입니다.
  eq('D6 a refused census still says when it tried', AT, textOf(REFUSED, 'measured_at'));
  eq('D7 ...and its counts are blank rather than zero', '', textOf(REFUSED, 'relation_rows'));

  // ══ ⑤ 줄을 «그릴까» ═══════════════════════════════════════════════════════════════
  ok('E1 no census at all draws nothing', has(undefined) === false && has(null) === false);
  ok('E2 a counted census draws', has(COUNTED) === true);
  // 🔴 A REFUSAL DRAWS. It has no counts, so a cell-only test would hide it — and the whole
  //    point is that this state is actionable.
  ok('E3 a REFUSED census draws, though it has no counts', has(REFUSED) === true);
  ok('E4 CONTROL: a census with a stamp and nothing else still draws',
    has({ measured_at: AT }) === true);
  // 🔴 E3 IS SATISFIED BY THE STAMP TODAY, WHICH MAKES IT A WEAK TEST OF THE REFUSAL GUARD —
  //    the sweep proved it: removing that guard left E3 green. The guard is not redundant, it
  //    is UNREACHABLE while every census carries `measured_at`, and its job is to keep the
  //    refusal's REASON renderable when the stamp is not there. Scored on that case, and said
  //    plainly: today's server always stamps, so this shape is the guard's own, not the wire's.
  ok('E5 a refusal with no stamp still draws, because its reason is the thing to show',
    has({ source: 's', refused: 'no_row_id', remedy: 'declare it' }) === true);

  return { pass, failures: failures.slice() };
}

const base = await score(undefined);
console.log(`\n${base.failures.length === 0 ? '✓' : '✗'} baseline: ${base.pass} passed, `
  + `${base.failures.length} failed`);
console.log(`ASSERTIONS ${base.pass + base.failures.length} ${base.failures.length}`);

const MUTATIONS = [
  ['M1 the envelope is read as a number, so every count goes blank',
   s => s.replace('    const count = Number(box.estimate);', '    const count = Number(box);')],
  ['M2 an uncounted field is drawn as 0, so 「아직 모름」 reads as 「돌 게 없다」',
   s => s.replace("    if (!box || typeof box !== 'object') return { name, text: '' };",
                  "    if (!box || typeof box !== 'object') return { name, text: '0' };")],
  ['M3 a measured zero stops being drawn, so counted-and-empty looks uncounted',
   s => s.replace('    return { name, text: `${mark}${count}` };',
                  "    return { name, text: count === 0 ? '' : `${mark}${count}` };")],
  ['M4 an estimate is drawn like an exact count — the thing `measured()` exists to stop',
   s => s.replace("    const mark = box.exact === false ? ESTIMATE_MARK : '';",
                  "    const mark = '';")],
  ['M5 anything not exactly true is marked, so a silent `exact` becomes an estimate',
   s => s.replace('box.exact === false', 'box.exact !== true')],
  ['M6 the refusal stops being named, so 「못 센다」 becomes 「안 셌다」',
   s => s.replace('  if (!src || !src.refused) return null;', '  return null;')],
  ['M7 a refused source stops drawing its line at all',
   s => s.replace('  if (censusRefusal(census)) return true;', '')],
  ['M8 the remedy is dropped, leaving a reason nobody can act on',
   s => s.replace("remedy: src.remedy ? String(src.remedy) : ''", "remedy: ''")],
  ['M9 the stamp is reworded instead of carried',
   s => s.replace("text: at == null ? '' : String(at)",
                  "text: at == null ? '' : String(at).slice(0, 10)")],
  ['M10 the labels are translated, so a renamed field keeps the old name',
   s => s.replace("Object.freeze(['relation_rows', 'indexed_rows', 'not_yet'])",
                  "Object.freeze(['전체', '색인', '남음'])")],
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
