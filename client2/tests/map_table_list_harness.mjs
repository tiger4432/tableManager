/**
 * 🏷️ C-44 ② — 맵 표 목록이 «한 응답»에서 나오는가. 대상을 IMPORT 합니다.
 *
 * 🔴 THE OLD SHAPE COST ONE REQUEST PER TABLE and was invisible: every call succeeded, nothing
 *    logged, and the only symptom was the first screen being slow in a deployment with many
 *    tables. Measured on this box before the change: 45 requests for a list of ten, 34 answers
 *    discarded. The property that matters is that requests EQUALED tables.
 *
 * Run:  node client2/tests/map_table_list_harness.mjs [--mutate]
 */
import { loadWithProbe } from './lib/probe.mjs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src', 'map_table_list.js');

let pass = 0;
const failures = [];
const ok = (name, cond, detail = '') => {
  if (cond) { pass += 1; console.log(`  PASS ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name}${detail ? ' — ' + detail : ''}`); }
};
const eq = (name, expected, actual) => ok(name, actual === expected,
  `expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);

// 🔴 THE ORDERS DISAGREE ON PURPOSE. On this box `tables` and `map_key_columns` happen to be
//    in the same order, so the live response CANNOT tell 「walk the table list」 from 「walk the
//    map's keys」 — a fixture both rules answer the same way decides nothing. Here the map's
//    keys are reversed, and only one of the two rules gives the order the operator has been
//    reading since before this change.
const BODY = {
  tables: ['lot_event', 'dt_log', 'process_event', 'dt_map', 'bonding_map'],
  map_key_columns: {
    bonding_map: ['base_wafer_id'],
    dt_map: ['dt_lot', 'dt_slot'],
    dt_log: ['dt_job_id'],
  },
};
const OLD_SERVER = { tables: ['lot_event', 'dt_log', 'dt_map'] };

async function score(mutate) {
  pass = 0; failures.length = 0;
  const { probe } = await loadWithProbe(SRC, {
    expose: ['mapTablesFrom', 'NOT_SERVED'], mutate, tag: 'maptables',
  });
  const { mapTablesFrom, NOT_SERVED } = probe;

  // ══ ① 목록과 «그 순서» ═════════════════════════════════════════════════════════════
  const got = mapTablesFrom(BODY);
  eq('A1 only the tables that declare a map key are offered', 'dt_log,dt_map,bonding_map',
    got.tables.join(','));
  // 🔴 THE DISCRIMINATOR. Walking `map_key_columns` would answer
  //    「bonding_map,dt_map,dt_log」 — the same three, in an order the operator has never seen.
  ok('A2 ...in the ORDER `tables` gave them, not the order the keys happen to be in',
    got.tables.join(',') !== Object.keys(BODY.map_key_columns).join(','), got.tables.join(','));
  eq('A3 and nothing is owed when the server answered', '', got.reason);
  // ⚠️ A declared-but-EMPTY column list is not a map table: the picker would offer a table
  //    whose map key nobody can build.
  eq('A4 an empty column list does not qualify', 'dt_log',
    mapTablesFrom({ tables: ['dt_log', 'dt_map'],
      map_key_columns: { dt_log: ['a'], dt_map: [] } }).tables.join(','));
  eq('A5 ...and neither does a non-list', 'dt_log',
    mapTablesFrom({ tables: ['dt_log', 'dt_map'],
      map_key_columns: { dt_log: ['a'], dt_map: 'dt_lot' } }).tables.join(','));
  // 🔴 A TABLE THE MAP NAMES BUT `tables` DOES NOT is not offered — the picker may only offer
  //    what the server says exists, or the operator picks a table that is not there.
  eq('A6 a key for a table that is not listed is ignored', 'dt_log',
    mapTablesFrom({ tables: ['dt_log'],
      map_key_columns: { dt_log: ['a'], gone_away: ['b'] } }).tables.join(','));

  // ══ ② 「키 없음」은 «그 자체로 답»입니다 ════════════════════════════════════════════
  // 🔴 THE ONE THE RULING NAMES. An older server sends no `map_key_columns` at all, and that is
  //    「서버가 말 안 함」 — telling an operator 「맵 표 없음」 instead says their tables are
  //    unusable, which is a different and false thing.
  const old = mapTablesFrom(OLD_SERVER);
  eq('B1 an older server yields an EMPTY list', 0, old.tables.length);
  eq('B2 ...with the reason, in one word', NOT_SERVED, old.reason);
  ok('B3 ...and the reason is a word, not a sentence',
    NOT_SERVED.length <= 6 && !/[.!?]/.test(NOT_SERVED), NOT_SERVED);
  // ⚠️ THE DISCRIMINATOR FOR B1/B2. A server that DID answer and found none is a different
  //    state: empty list, and NOTHING owed. Folding the two would put a reason on a true answer.
  const none = mapTablesFrom({ tables: ['lot_event'], map_key_columns: {} });
  eq('B4 a server that answered and found none says nothing', '', none.reason);
  eq('B5 ...and its list is empty too, so only the reason tells them apart', 0, none.tables.length);
  ok('B6 the two empties are different answers', none.reason !== old.reason);
  // 옛 서버가 «그 칸을 다른 모양»으로 보내는 경우도 「말 안 함」입니다 — 배열이나 문자열은 이 답이 아닙니다.
  eq('B7 a wrong-shaped key is not read as an answer', NOT_SERVED,
    mapTablesFrom({ tables: ['a'], map_key_columns: ['a'] }).reason);

  // ══ ③ 아무것도 없을 때 ═════════════════════════════════════════════════════════════
  eq('C1 no body at all is 「말 안 함」', NOT_SERVED, mapTablesFrom(null).reason);
  eq('C2 ...with an empty list rather than a throw', 0, mapTablesFrom(undefined).tables.length);
  eq('C3 a body with no tables offers none', 0,
    mapTablesFrom({ map_key_columns: { a: ['x'] } }).tables.length);

  return { pass, failures: failures.slice() };
}

const base = await score(undefined);
console.log(`\n${base.failures.length === 0 ? '✓' : '✗'} baseline: ${base.pass} passed, `
  + `${base.failures.length} failed`);
console.log(`ASSERTIONS ${base.pass + base.failures.length} ${base.failures.length}`);

const MUTATIONS = [
  // 🔴 THE RULING'S OWN MUTANT, EXPRESSED AS WHAT THE LOOP DID: read the map's keys instead of
  //    the table list. Same members, different order — and this box could not have caught it.
  ['M1 the order comes from the map\'s keys, so the picker reshuffles',
   s => s.replace('  return { tables: all.filter(keyed), reason: \'\' };',
                  "  return { tables: Object.keys(declared).filter((n) => all.includes(n) && keyed(n)), reason: '' };")],
  ['M2 a server that never answered is reported as having no map tables',
   s => s.replace('    return { tables: [], reason: NOT_SERVED };', '    return { tables: [], reason: \'\' };')],
  ['M3 an empty answer grows a reason, so a true answer looks like a failure',
   s => s.replace("  return { tables: all.filter(keyed), reason: '' };",
                  '  return { tables: all.filter(keyed), reason: NOT_SERVED };')],
  ['M4 a declared-but-empty column list qualifies, offering a table with no key',
   s => s.replace('    return Array.isArray(cols) && cols.length > 0;', '    return cols !== undefined;')],
  ['M5 a key for a table the server does not list is offered anyway',
   s => s.replace('  return { tables: all.filter(keyed), reason: \'\' };',
                  "  return { tables: Object.keys(declared).filter(keyed), reason: '' };")],
  ['M6 the reason becomes a sentence',
   s => s.replace("export const NOT_SERVED = '미제공';",
                  "export const NOT_SERVED = '이 서버는 맵 키 컬럼을 알려주지 않습니다.';")],
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
