/**
 * 🏷️ C-43 ② — 맵 셀 조회가 «세는 일»을 시키지 않는가. 대상을 IMPORT 합니다.
 *
 * 🔴 THE COST WAS INVISIBLE BY CONSTRUCTION. The main load asked without `defer_total`, so the
 *    server ran a COUNT over the same filter and the same table before answering — a second
 *    full scan that shows up nowhere except in the seconds the operator waits. Nothing was
 *    broken, nothing logged, and the only symptom was 「사람들이 못 쓴다」.
 *
 * Run:  node client2/tests/map_cell_query_harness.mjs [--mutate]
 */
import { loadWithProbe } from './lib/probe.mjs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src', 'map_cell_query.js');

let pass = 0;
const failures = [];
const ok = (name, cond, detail = '') => {
  if (cond) { pass += 1; console.log(`  PASS ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name}${detail ? ' — ' + detail : ''}`); }
};

const FILTERS = { map_id: { filterType: 'text', type: 'equals', filter: 'SYN-MAP20_1' } };
const rows = (n) => Array.from({ length: n }, (_, i) => ({ i }));

async function score(mutate) {
  pass = 0; failures.length = 0;
  const { probe } = await loadWithProbe(SRC, {
    expose: ['CELL_LIMIT', 'cellQuery', 'cellsTruncated', 'cellsToDraw'], mutate, tag: 'cellq',
  });
  const { CELL_LIMIT: CAP, cellQuery, cellsTruncated, cellsToDraw } = probe;
  const q = cellQuery(FILTERS);

  // ══ ① 두 번째 스캔을 «안 시킵니다» ══════════════════════════════════════════════════
  // 🔴 THE ONE THE RULING NAMES. Without this the server counts the same filter over the same
  //    table before it answers, and the person opening the map waits for both.
  ok('A1 the query defers the total, so the load does not also count', q.includes('defer_total=true'), q);
  // 🔴 ONE MORE THAN THE CAP, because that extra row IS the truncation evidence. Asking for
  //    exactly the cap leaves 「정확히 상한」 and 「상한에서 잘림」 indistinguishable without a
  //    total — which is the count this round removed.
  ok(`A2 it asks for one more than the cap (${CAP})`, q.includes(`limit=${CAP + 1}`), q);
  ok('A3 the filter rides encoded, as the server receives it',
    q.includes(`filters=${encodeURIComponent(JSON.stringify(FILTERS))}`), q);
  // ⚠️ CONTROL: the query is a tail, not a whole URL — the caller owns the table name, and a
  //    table spelled here would make this the second author of the route.
  ok('A4 CONTROL: no table and no origin are written here',
    !q.includes('/tables/') && !q.includes('http'), q);

  // ══ ② 절단은 «행 수»로 ═════════════════════════════════════════════════════════════
  ok('B1 one more than the cap is a cut', cellsTruncated(rows(CAP + 1)) === true);
  // 🔴 THE DISCRIMINATOR. Exactly the cap is a WHOLE answer, and reading it as a cut demotes
  //    a perfectly good map to 「모름」 — the same off-by-one that would make every full map
  //    look truncated.
  ok('B2 exactly the cap is NOT a cut', cellsTruncated(rows(CAP)) === false);
  ok('B3 fewer is not a cut', cellsTruncated(rows(3)) === false);
  ok('B4 nothing at all is not a cut', cellsTruncated([]) === false
    && cellsTruncated(null) === false && cellsTruncated(undefined) === false);

  // ══ ③ 그리는 것은 «상한까지» ════════════════════════════════════════════════════════
  // 🔴 The extra row is evidence, not a cell. Drawing it would make a truncated map render
  //    one cell more than it used to, which is the screen changing without anyone saying so.
  ok('C1 a cut answer draws exactly the cap', cellsToDraw(rows(CAP + 1)).length === CAP);
  ok('C2 a whole answer draws all of it', cellsToDraw(rows(CAP)).length === CAP
    && cellsToDraw(rows(7)).length === 7);
  ok('C3 nothing in, nothing out', cellsToDraw(null).length === 0);

  // ══ ④ 상한은 «하나» ═══════════════════════════════════════════════════════════════
  // 🔴 The overlay loader kept its own `2000` with a comment saying 「메인 로드와 같은 상한」.
  //    A comment is not a mechanism; this constant is.
  ok('D1 the cap is a number both loaders can read',
    typeof CAP === 'number' && CAP > 0);
  ok('D2 ...and the query, the cut and the draw all agree with it',
    q.includes(String(CAP + 1)) && cellsTruncated(rows(CAP + 1))
    && cellsToDraw(rows(CAP + 1)).length === CAP);

  return { pass, failures: failures.slice() };
}

const base = await score(undefined);
console.log(`\n${base.failures.length === 0 ? '✓' : '✗'} baseline: ${base.pass} passed, `
  + `${base.failures.length} failed`);
console.log(`ASSERTIONS ${base.pass + base.failures.length} ${base.failures.length}`);

const MUTATIONS = [
  ['M1 the total comes back, so the load pays for a second scan of the same filter',
   s => s.replace("&defer_total=true", "")],
  ['M2 it asks for exactly the cap, so a full map cannot be told from a cut one',
   s => s.replace('limit=${CELL_LIMIT + 1}', 'limit=${CELL_LIMIT}')],
  ['M3 exactly the cap reads as truncated, demoting whole maps to 「모름」',
   s => s.replace('> CELL_LIMIT;', '>= CELL_LIMIT;')],
  ['M4 the evidence row is drawn as a cell',
   s => s.replace('.slice(0, CELL_LIMIT)', '')],
];
// 🔴 A CONTROL, AND IT EARNED THE PROMOTION BY ESCAPING. Moving the cap is a LEGITIMATE edit,
//    and every assertion above is written relative to `CELL_LIMIT` rather than to the number
//    2000 — so if this one reddened, the harness would be pinning the value instead of the
//    rule, and the next person who changes the cap would get a red gate for doing it right.
//    It was declared as a defect first and escaped; that escape is the evidence.
const CONTROLS = [
  ['the cap moves, and the query, the cut and the draw all follow it',
   s => s.replace('export const CELL_LIMIT = 2000;', 'export const CELL_LIMIT = 500;')],
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
  console.log('\n── CONTROLS (each must stay GREEN) ──');
  for (const [name, apply] of CONTROLS) {
    let r;
    try { r = await score(apply); } catch (e) { r = { failures: [`threw: ${e && e.message}`] }; }
    if (r.failures.length === 0) console.log(`  ✓ ${name} -> stayed green`);
    else { console.log(`  ✗ ${name} -> WENT RED`); green.push(`control: ${name}`); }
  }
  if (green.length) { console.log(`  ✗ wrong verdicts: ${green.join(' | ')}`); process.exit(1); }
}

process.exit(base.failures.length === 0 ? 0 : 1);
