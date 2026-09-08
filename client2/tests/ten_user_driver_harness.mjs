/**
 * C-41 — the ten-user driver's decisions, scored WITHOUT a server. Subject is IMPORTED.
 *
 * 🔴 WHY A HARNESS FOR A MEASURING TOOL. A load driver's failures all look like good news: a
 *    lane that reuses another's table is fast because a cache answered, ten lanes that ran one
 *    after another are fast because nothing contended, and a route that 500s is fast because
 *    it did no work. Every one of those makes the table LOOK better, so none of them is
 *    something a reader would question. They have to be values something else scores.
 *
 * Run:  node client2/tests/ten_user_driver_harness.mjs [--mutate]
 */
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { loadWithProbe, readSourceText } from './lib/probe.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'scripts', 'load_driver', 'plan.mjs');

let pass = 0, quiet = false;
const failures = [];
const ok = (cond, name, detail = '') => {
  if (cond) { pass += 1; if (!quiet) console.log(`  OK   ${name}`); }
  else { failures.push(name); if (!quiet) console.log(`  BAD  ${name}${detail ? ' — ' + detail : ''}`); }
};

// Two lanes on their OWN material, and a third that collides with the first on every axis.
const LANE_A = { id: 'a',
  grid: { table: 't_one', limit: 100, order_by: 'row_id', order_desc: false },
  map: { table: 'm_one', map_id: 'K1', metadata_table: 'meta' },
  walk: { type: 'wafer@1', keys: { wafer: 'W1' }, follow: ['inspected', 'observed'], hops: 2 } };
const LANE_B = { id: 'b',
  grid: { table: 't_two', limit: 100, order_by: 'row_id', order_desc: false },
  map: { table: 'm_two', map_id: 'K2', metadata_table: 'meta' },
  walk: { type: 'wafer@1', keys: { wafer: 'W2' }, follow: ['inspected'], hops: 1 } };
const LANE_CLONE = { ...LANE_A, id: 'c' };

function suite(M) {
  const before = failures.length;

  // ══ ① 열마다 «다른» 재료 — 아니면 캐시가 답합니다 ════════════════════════════════════
  ok(M.cacheWarnings([LANE_A, LANE_B]).length === 0,
    'C1 two lanes on their own table, map and seed raise nothing');
  const shared = M.cacheWarnings([LANE_A, LANE_B, LANE_CLONE]);
  ok(shared.length === 3, 'C2 a lane that clones another is called out on ALL THREE axes',
    JSON.stringify(shared));
  ok(shared.every((line) => line.includes('a') && line.includes('c')),
    'C3 ...and the warning names WHICH two, because ten lanes make one line useless');
  // 🔴 THE DISCRIMINATOR. A lane colliding on ONE axis must still be caught: the table is the
  //    axis a driver is most likely to reuse by accident, and a check that only fired on a
  //    full clone would sleep through exactly that.
  ok(M.cacheWarnings([LANE_A, { ...LANE_B, grid: { ...LANE_A.grid } }]).length === 1,
    'C4 a collision on ONE axis is a collision');

  // ══ ② 요청 모양이 «화면의 것»입니다 ═════════════════════════════════════════════════
  const reqs = M.laneRequests(LANE_A);
  const byRoute = Object.fromEntries(reqs.map((r) => [r.route, r.path]));
  ok(reqs.length === 5, 'Q1 five requests: grid data + count, map meta + overlay, walk',
    JSON.stringify(reqs.map((r) => r.route)));
  // 🔴 `defer_total` IS THE SCREEN'S OWN. Without it the grid route counts as well as reads,
  //    and the driver would be timing a request the screen never sends.
  ok(byRoute['grid.data'].includes('defer_total=true')
    && byRoute['grid.data'].includes('order_by=row_id')
    && byRoute['grid.data'].includes('order_desc=false'),
  'Q2 the grid request carries the deferred total and the sort tail', byRoute['grid.data']);
  ok(byRoute['grid.count'].endsWith('/data/count'),
    'Q3 the count is its own call, as the screen makes it', byRoute['grid.count']);
  // 🔴 BOTH KEY COLUMNS. One map_id can live in two tables, and filtering on the id alone
  //    reads a different map's spec — a defect this repo has already had once.
  ok(byRoute['map.meta'].includes('target_table') && byRoute['map.meta'].includes('map_id')
    && byRoute['map.meta'].includes('limit=2'),
  'Q4 the map meta is filtered on the PAIR, and asks for two rows', byRoute['map.meta']);
  ok(byRoute['walk.subgraph'].startsWith('/api/ledger/subgraph?id=ledger-entity%3Av1%3A')
    && (byRoute['walk.subgraph'].match(/follow=/g) || []).length === 2,
  'Q5 the walk carries an encoded seed and one follow per predicate', byRoute['walk.subgraph']);
  // ⚠️ The seed spelling is base64URL, and today's keys do not contain a `+` — so a mutant
  //    swapping it back to standard base64 would pass on this box and 422 on the first key
  //    that does. Scored on a key that HAS one.
  ok(!/[+/]/.test(M.seedId('wafer@1', { wafer: 'SYN-BW-101-16>' }).split(':').pop()),
    'Q6 a seed whose base64 would carry + or / is still URL-safe');
  // 🔴 UNGIVEN IS UNSENT. `hops: 0` and an empty follow are answers, not defaults, and the
  //    screen's rule is that what the caller did not choose does not go on the wire.
  ok(!M.laneRequests({ id: 'x', walk: { type: 'wafer@1', keys: {} } })[0].path.includes('hops'),
    'Q7 a lane that named no hops sends none');

  // ══ ③ 답 안 한 호출은 «표에 남습니다» ═══════════════════════════════════════════════
  // 🔴 SILENCE IS THE FAILURE MODE. Dropping the calls that did not answer makes a run of
  //    five hundred timeouts look like a fast run of nothing, and the p50 of the survivors
  //    is the number a reader would quote.
  const mixed = M.resultRow('a', 'grid.data', [
    { status: 200, ms: 10, truncated: null }, { status: 500, ms: 3, truncated: null },
    { status: 0, ms: 30000, truncated: null },
  ]);
  ok(mixed.n === 3 && mixed.ok === 1, 'F1 every call is counted, answered or not',
    JSON.stringify(mixed));
  ok(mixed.status === '0/200/500', 'F2 the statuses are printed as they came', mixed.status);
  // 🔴 AND THE PERCENTILE IS OF THE ONES THAT ANSWERED. A 500 that returned in 3 ms is not a
  //    fast read, and letting it into the p50 makes a broken route look like the quickest one.
  ok(mixed.p50 === 10 && mixed.p95 === 10,
    'F3 the percentiles are of the 2xx calls only', `${mixed.p50}/${mixed.p95}`);
  const dead = M.resultRow('a', 'walk.subgraph', [{ status: 0, ms: 5, truncated: null }]);
  ok(dead.n === 1 && dead.ok === 0 && dead.p50 === null,
    'F4 a route that never answered has NO number rather than a zero', JSON.stringify(dead));
  ok(M.percentile([], 50) === null && M.percentile([7], 95) === 7,
    'F5 no samples is null, one sample is itself');
  ok(M.percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 95) === 10
    && M.percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 50) === 5,
  'F6 nearest-rank, so p95 of ten samples is the tenth');
  // 절단: 말 안 한 것과 «안 잘렸다»가 다릅니다.
  ok(M.resultRow('a', 'r', [{ status: 200, ms: 1, truncated: null }]).truncated === null
    && M.resultRow('a', 'r', [{ status: 200, ms: 1, truncated: false }]).truncated === false
    && M.resultRow('a', 'r', [{ status: 200, ms: 1, truncated: false },
      { status: 200, ms: 1, truncated: true }]).truncated === true,
  'F7 a route that never mentions truncation is null, not false');

  // ══ ④ 열 «열»이 «동시에» ═══════════════════════════════════════════════════════════
  // 🔴 THE ACCIDENT THIS CATCHES IS ONE MISPLACED `await`. Ten lanes awaited one at a time
  //    are ten users on paper and one user in fact, every number improves, and the code still
  //    reads like a concurrent driver. So the overlap comes from the timestamps.
  const serial = Array.from({ length: 10 }, (_, i) => ({ start: i * 10, end: i * 10 + 9 }));
  const together = Array.from({ length: 10 }, (_, i) => ({ start: i, end: 100 + i }));
  ok(M.maxOverlap(serial) === 1, 'O1 ten calls back to back are ONE at a time',
    String(M.maxOverlap(serial)));
  ok(M.maxOverlap(together) === 10, 'O2 ten calls that overlap are ten',
    String(M.maxOverlap(together)));
  // ⚠️ Touching intervals are not overlapping ones — otherwise a perfectly serial run reads
  //    as two at once and the assertion above stops being able to fail.
  ok(M.maxOverlap([{ start: 0, end: 5 }, { start: 5, end: 9 }]) === 1,
    'O3 a call that starts exactly when another ends is not concurrent');
  ok(M.maxOverlap([]) === 0 && M.maxOverlap([{ start: NaN, end: 1 }]) === 0,
    'O4 CONTROL: nothing measured is zero, not one');

  // ══ ⑤ 표 머리 — 「이 박스가 규격을 어디까지 갖췄나」 ═══════════════════════════════════
  // 🔴 THREE STATES, AND THE THIRD IS THE ONE THAT MATTERS. An axis nobody could measure is
  //    not a met axis and is not a zero: printing 0 atoms would say this box is empty, and
  //    printing nothing would let the run be quoted as if it were production-shaped.
  const spec = { chain_rows_per_transaction: 1000, map_grid: '20x20', users: 10, atoms: 1e7 };
  const header = M.specHeader(spec, { users: 10, map_grid: '27x21', atoms: null });
  const verdictOf = (axis) => header.find((r) => r.axis === axis).verdict;
  ok(header.length === 4, 'H1 every declared axis gets a line');
  ok(verdictOf('users') === '갖춤', 'H2 an axis that was met says so');
  ok(verdictOf('map_grid') === '미달', 'H3 an axis that was measured and missed says MISSED');
  ok(verdictOf('atoms') === '못 셈' && verdictOf('chain_rows_per_transaction') === '못 셈',
    'H4 an axis nobody could measure says 못 셈 — not 0, and not 미달');
  ok(M.meetsSpec(header) === false, 'H5 a box with an unmeasured axis is NOT production-shaped');
  ok(M.meetsSpec(M.specHeader(spec, { chain_rows_per_transaction: 1000, map_grid: '20x20', users: 10, atoms: 2e7 })),
    'H6 CONTROL: a box that meets every axis is, so H5 is not vacuous');
  // 🔴 MORE IS ENOUGH FOR A NUMBER, EXACT IS REQUIRED FOR A SHAPE. 12 users covers a spec of
  //    10; a 40x40 map does not cover a 20x20 one, it is a different question.
  ok(M.specHeader(spec, { users: 12 }).find((r) => r.axis === 'users').verdict === '갖춤'
    && M.specHeader(spec, { map_grid: '40x40' }).find((r) => r.axis === 'map_grid').verdict === '미달',
  'H7 a numeric axis is met by more, a shape axis only by the shape');

  // ══ ⑥ 맵 격자는 «응답에서» 읽습니다 ═════════════════════════════════════════════════
  const metaBody = { data: [{ data: { grid_metadata: { value: '{"grid_cols":20,"grid_rows":20}' } } }] };
  ok(M.gridOf(metaBody) === '20x20', 'G1 the grid is read off the metadata row',
    String(M.gridOf(metaBody)));
  ok(M.gridOf({ data: [] }) === null && M.gridOf(null) === null,
    'G2 no row is null — 「말 안 함」, not 0x0');
  ok(M.gridOf({ data: [{ data: { grid_metadata: { value: 'not json' } } }] }) === null,
    'G3 an unparseable spec is null rather than a guessed grid');
  // 🔴 A SPEC THAT PARSES AND SAYS NOTHING USEFUL IS A DIFFERENT BRANCH, and the sweep found
  //    it uncovered: G3 returns at the JSON.parse catch and never reaches the guard below it,
  //    so a mutant filling that guard with a plausible-looking 「20x20」 walked straight past.
  ok(M.gridOf({ data: [{ data: { grid_metadata: { value: '{"grid_cols":"wide","grid_rows":20}' } } }] }) === null,
    'G4 a spec whose numbers are not numbers is null, not a grid this file invented');

  return { fail: failures.length - before };
}

console.log('-- the ten-user driver\'s decisions ----------------------------------');
suite(await import('../scripts/load_driver/plan.mjs'));
const base = { pass, fail: failures.length };
console.log(`\n${base.fail === 0 ? '✓' : '✗'} baseline: ${base.pass} passed, ${base.fail} failed`);
if (base.fail) console.error(`failed:\n  ${failures.join('\n  ')}`);
console.log(`ASSERTIONS ${base.pass + base.fail} ${base.fail}`);

const DEFECTS = [
  ['the cache warning is removed, so lanes may quietly share material',
    (s) => s.replace('      if (before) out.push(', '      if (false) out.push(')],
  ['only the grid axis is checked, so two lanes may share a map or a seed',
    (s) => s.replace('  for (const [axis, of] of axes) {',
      '  for (const [axis, of] of axes.slice(0, 1)) {')],
  ['calls that did not answer 2xx are dropped from the table',
    (s) => s.replace('  const statuses = [...new Set(calls.map((c) => c.status))].sort((a, b) => a - b);',
      '  calls = calls.filter((c) => c.status >= 200 && c.status < 300);\n'
      + '  const statuses = [...new Set(calls.map((c) => c.status))].sort((a, b) => a - b);')],
  ['a route that never answered is reported as 0 ms rather than as nothing',
    (s) => s.replace('  if (!sorted.length) return null;', '  if (!sorted.length) return 0;')],
  ['every call feeds the percentile, so a fast 500 becomes the median',
    (s) => s.replace('  const okMs = calls.filter((c) => c.status >= 200 && c.status < 300).map((c) => c.ms);',
      '  const okMs = calls.map((c) => c.ms);')],
  ['the overlap is claimed rather than measured, so a serial run reads as ten users',
    (s) => s.replace('  let now = 0, peak = 0;\n  for (const [, delta] of edges) { now += delta; if (now > peak) peak = now; }\n  return peak;',
      '  return (intervals || []).length;')],
  ['a call that starts as another ends counts as concurrent',
    (s) => s.replace('  edges.sort((a, b) => a[0] - b[0] || a[1] - b[1]);',
      '  edges.sort((a, b) => a[0] - b[0] || b[1] - a[1]);')],
  ['an axis nobody could measure is reported as met',
    (s) => s.replace("    if (got === undefined || got === null) return { axis, want, got: null, verdict: '못 셈' };",
      "    if (got === undefined || got === null) return { axis, want, got: null, verdict: '갖춤' };")],
  ['a shape axis is met by anything that was measured',
    (s) => s.replace('    const met = typeof want === \'number\' && typeof got === \'number\' ? got >= want : got === want;',
      '    const met = true;')],
  ['the seed goes out as standard base64, which 422s on keys containing +',
    (s) => s.replace("  return 'ledger-entity:v1:' + b64.replace(/\\+/g, '-').replace(/\\//g, '_').replace(/=+$/, '');",
      "  return 'ledger-entity:v1:' + b64;")],
  ['the grid metadata is guessed rather than read',
    (s) => s.replace('  if (!Number.isFinite(cols) || !Number.isFinite(rowsN)) return null;',
      '  if (!Number.isFinite(cols) || !Number.isFinite(rowsN)) return \'20x20\';')],
  ['the grid request stops filtering on the table, so one map_id reads another map',
    (s) => s.replace('      target_table: { filterType: \'text\', type: \'equals\', filter: String(map.table) },', '')],
];
const CONTROLS = [
  ['comments stripped', (s) => s.split('\n').filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l)).join('\n')],
];

if (process.argv.includes('--mutate')) {
  quiet = true;
  let caught = 0; const wrong = [];
  console.log('\n-- defect mutants (each must be CAUGHT) ------------------------------');
  // 🔴 THE ANCHOR IS CHECKED BY NAME FIRST. The probe refuses a mutant that changed nothing —
  //    correctly — but it refuses ANONYMOUSLY, and with twelve mutants that is a hunt. Naming
  //    the one whose anchor moved is the difference between a minute and twenty.
  const SOURCE = readSourceText(SRC).text;
  for (const [name, mutate] of DEFECTS) {
    if (mutate(SOURCE) === SOURCE) {
      quiet = false;
      console.error(`  anchor GONE: ${name} — its target text is no longer in plan.mjs`);
      process.exit(2);
    }
    let r;
    try { r = suite((await loadWithProbe(SRC, { mutate, tag: 'tenuser' })).module); }
    catch (e) {
      if (/did not mutate|unchanged/.test(String(e && e.message))) {
        quiet = false; console.error(`  anchor GONE: ${name} — ${e.message}`); process.exit(2);
      }
      r = { fail: 1 };
    }
    if (r.fail > 0) { caught += 1; console.log(`  caught  ${name}`); }
    else { wrong.push(name); console.log(`  ESCAPED ${name}`); }
  }
  console.log('\n-- control mutants (each must ESCAPE) --------------------------------');
  for (const [name, mutate] of CONTROLS) {
    let r;
    try { r = suite((await loadWithProbe(SRC, { mutate, tag: 'tenuserc' })).module); }
    catch { r = { fail: 1 }; }
    if (r.fail === 0) console.log(`  escaped ${name}`);
    else { wrong.push(`control caught: ${name}`); console.log(`  CAUGHT  ${name} <- control caught`); }
  }
  quiet = false;
  console.log(`\nmutations: ${caught}/${DEFECTS.length} caught`);
  if (wrong.length) { console.error(`wrong verdicts:\n  ${wrong.join('\n  ')}`); process.exit(1); }
}

process.exit(base.fail === 0 ? 0 : 1);
