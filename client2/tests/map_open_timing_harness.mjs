/**
 * 🏷️ C-43 ① ③ — 맵 열기의 계측. 대상을 IMPORT 합니다.
 *
 * 🔴 THIS IS AN INSTRUMENT, AND AN INSTRUMENT'S FAILURES READ AS GOOD NEWS. A call it missed
 *    is a smaller number; a duplicate it folded away is a tidier one; a draw time it filled in
 *    as 0 is an instant screen. Every one of those makes the map look faster than it is, which
 *    is the direction nobody double-checks — so they are values something else scores.
 *
 * Run:  node client2/tests/map_open_timing_harness.mjs [--mutate]
 */
import { loadWithProbe } from './lib/probe.mjs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src', 'map_open_timing.js');

let pass = 0;
const failures = [];
const ok = (name, cond, detail = '') => {
  if (cond) { pass += 1; console.log(`  PASS ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name}${detail ? ' — ' + detail : ''}`); }
};
const eq = (name, expected, actual) => ok(name, actual === expected,
  `expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);

// One open, as the screen actually makes it: a preset, the paint rules, a metadata probe, the
// cells, and an overlay — with the paint rules asked for TWICE, which is the finding this
// instrument exists to surface.
const CALLS = [
  { url: '/api/maps/preset-routing', ms: 31 },
  { url: '/api/maps/paint-rules?table=dt_map', ms: 44 },
  { url: '/tables/wafer_map_metadata/data?limit=2', ms: 57 },
  { url: '/tables/dt_map/data?limit=2001&defer_total=true', ms: 812 },
  { url: '/api/maps/paint-rules?table=dt_map', ms: 12 },
];

async function score(mutate) {
  pass = 0; failures.length = 0;
  const { probe } = await loadWithProbe(SRC, {
    expose: ['createOpenTimer', 'summarise', 'timingText', 'duplicateTitle'], mutate, tag: 'opentime',
  });
  const { createOpenTimer, summarise, timingText, duplicateTitle } = probe;
  const s = summarise(CALLS, 143);

  // ══ ① 센 것이 «전부» 세어졌나 ═══════════════════════════════════════════════════════
  eq('A1 every call is counted, including the repeated one', 5, s.requests);
  eq('A2 the total is the sum of what went out', 31 + 44 + 57 + 812 + 12, s.totalMs);
  // 🔴 THE SLOWEST IS NAMED. 「어느 것이 느린가」 is the whole reason to count: a total alone
  //    sends somebody optimising the four calls that were never the problem.
  eq('A3 the slowest call is the cell load', '/tables/dt_map/data?limit=2001&defer_total=true',
    s.slowest.url);
  eq('A4 ...with its own time', 812, s.slowest.ms);

  // ══ ② 같은 것을 두 번 부른 것은 «발견»입니다 ════════════════════════════════════════
  eq('B1 the repeated URL is found', 1, s.duplicates.length);
  // ⚠️ Read through a guard: when B1 fails these must FAIL rather than throw, or the mutant
  //    that empties the list scores as 「caught by exception」 and says nothing about which
  //    assertion noticed.
  const firstDupe = s.duplicates[0] || {};
  eq('B2 ...and it is NAMED', '/api/maps/paint-rules?table=dt_map', firstDupe.url);
  eq('B3 ...with how many times', 2, firstDupe.times);
  // ⚠️ THE URL IS NOT TIDIED. Stripping a query string would fold two DIFFERENT questions into
  //    one and report a duplicate that is not there — and would hide a real one the other way.
  ok('B4 two different tables are not a duplicate', summarise([
    { url: '/api/maps/paint-rules?table=a', ms: 1 },
    { url: '/api/maps/paint-rules?table=b', ms: 1 },
  ], 1).duplicates.length === 0);
  eq('B5 CONTROL: an open with nothing repeated finds none', 0,
    summarise(CALLS.slice(0, 4), 10).duplicates.length);

  // ══ ③ 안 잰 것은 «안 씁니다» ═══════════════════════════════════════════════════════
  // 🔴 A DRAW TIME OF 0 WOULD READ AS 「즉시 그려졌다」, which is the one thing this instrument
  //    must never say on its own. Not-yet-drawn is null and prints nothing.
  eq('C1 before the draw, the time is null rather than zero', null, summarise(CALLS).drawnMs);
  ok('C2 ...and the line does not mention drawing at all',
    !timingText(summarise(CALLS)).includes('그리기'), timingText(summarise(CALLS)));
  ok('C3 once drawn, it is on the line', timingText(s).includes('그리기 143 ms'), timingText(s));
  eq('C4 an open with no calls at all is zero requests, not a crash', 0,
    summarise([], null).requests);
  eq('C5 ...and its slowest is nothing rather than a made-up call', null,
    summarise([], null).slowest);

  // ══ ④ 줄은 «값»입니다 ═════════════════════════════════════════════════════════════
  const line = timingText(s);
  eq('D1 the line is counts and times, in order', '요청 5 · 최장 812 ms · 그리기 143 ms · 중복 1', line);
  // ⛔ 문장 금지. A line that explains itself is the thing this screen keeps removing.
  ok('D2 nothing on it is a sentence', line.length <= 60 && !/[.!?]/.test(line), line);
  ok('D3 no record, no line', timingText(null) === '' && timingText(undefined) === '');
  // 🔴 THE NAMES GO IN THE TOOLTIP, because the line must stay one line — but they must go
  //    SOMEWHERE, or 「중복 1」 is a number nobody can act on.
  ok('D4 the duplicated URL is reachable by name',
    duplicateTitle(s).includes('2×') && duplicateTitle(s).includes('paint-rules?table=dt_map'),
    duplicateTitle(s));
  eq('D5 nothing duplicated, nothing to name', '', duplicateTitle(summarise(CALLS.slice(0, 4), 1)));

  // ══ ⑤ 시계는 «주입»입니다 — 하니스가 시간을 쥡니다 ═══════════════════════════════════
  {
    let t = 1000;
    const timer = createOpenTimer(() => t);
    timer.note('/a', 5);
    timer.note('/b', 7);
    t = 1250;
    timer.drawn();
    const out = timer.summary();
    eq('E1 the timer counts what it was handed', 2, out.requests);
    eq('E2 ...and the draw is measured from the open, not from the last response', 250, out.drawnMs);
    eq('E3 CONTROL: a timer nobody drew on reports null', null,
      createOpenTimer(() => t).summary().drawnMs);
  }

  return { pass, failures: failures.slice() };
}

const base = await score(undefined);
console.log(`\n${base.failures.length === 0 ? '✓' : '✗'} baseline: ${base.pass} passed, `
  + `${base.failures.length} failed`);
console.log(`ASSERTIONS ${base.pass + base.failures.length} ${base.failures.length}`);

const MUTATIONS = [
  ['M1 a repeated call is folded away, so the screen stops finding the second ask',
   s => s.replace('    .filter(([, times]) => times > 1)', '    .filter(() => false)')],
  ['M2 the URL is tidied to its path, so two different questions look like one',
   s => s.replace("seen.set(call.url,", "seen.set(String(call.url).split('?')[0],")],
  ['M3 an undrawn open reports 0 ms, which reads as 「즉시 그려졌다」',
   s => s.replace("    drawnMs: typeof drawnMs === 'number' ? drawnMs : null,",
                  '    drawnMs: Number(drawnMs) || 0,')],
  ['M4 the slowest call is the FIRST rather than the slowest',
   s => s.replace('if (!slowest || call.ms > slowest.ms) slowest = call;',
                  'if (!slowest) slowest = call;')],
  ['M5 the line grows a sentence',
   s => s.replace("  return parts.join(' · ');",
                  "  return parts.join(' · ') + ' 입니다. 느리면 다시 여십시오.';")],
  ['M6 the duplicate names stop being reachable',
   s => s.replace('  return dupes.map((d) => `${d.times}× ${d.url}`).join(\'\\n\');',
                  "  return '';")],
  ['M7 the draw is timed from the last response instead of from the open',
   s => s.replace('    drawn() { drawnAt = clock() - started; },',
                  '    drawn() { drawnAt = 0; },')],
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
