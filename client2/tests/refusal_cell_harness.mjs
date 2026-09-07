/**
 * 🚪 S-39 — 「이 소스의 행이 왜 안 들어갔나」가 그 소스의 행에서 읽히나. 대상을 IMPORT 합니다.
 *
 * 🔴 이 하니스가 지키는 것은 «세 픽셀»입니다: 안 잼 / 쟀는데 0 / 쟀고 N. 가운데를 0 으로
 *    그리면 「없음」과 「안 잼」이 같아지고, 그 둘은 조작자에게 정반대의 지시입니다.
 *
 * Run:  node client2/tests/refusal_cell_harness.mjs [--mutate]
 */
import { loadWithProbe } from './lib/probe.mjs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src', 'refusal_cell.js');

let pass = 0;
const failures = [];
const ok = (name, cond, detail = '') => {
  if (cond) { pass += 1; console.log(`  PASS ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name}${detail ? ' — ' + detail : ''}`); }
};
const eq = (name, expected, actual) => ok(name, actual === expected,
  `expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);

const SINCE = '2026-09-07T19:00:00+00:00';
const report = (sources) => ({
  since: SINCE, sources,
  declared_reasons: ['no_time_column', 'undeclared_event_type', 'subject_unresolvable'],
  samples_cap: 20,
  truncated: { samples: { cut: false, omitted: null, reason: null } },
});
const reason = (count, details = []) => ({
  count, samples: details.map(d => ({ detail: d, atoms: 1, rows: 1, addresses: [] })),
});

async function score(mutate) {
  pass = 0; failures.length = 0;
  const { probe } = await loadWithProbe(SRC, {
    expose: ['refusalCell'], mutate, tag: 'refusalcell',
  });
  const C = probe.refusalCell;

  // ══ 세 픽셀 ═══════════════════════════════════════════════════════════════════════
  const nothing = C(null, 'dt_job');
  eq('A1 응답이 없으면 아무것도 — since 도 없다', '', nothing.text);
  eq('A2 ...그리고 그것이 「안 잼」의 표시다', '', nothing.since);

  const clean = C(report({}), 'dt_job');
  eq('A3 쟀는데 0 이면 「거절」을 안 그린다', '', clean.text);
  ok('A4 ...다만 since 는 남는다 — 그게 「안 잼」과 갈리는 유일한 픽셀이다',
     clean.since.includes(SINCE), clean.since);

  const one = C(report({ dt_job: { rows_refused: 7, atoms_lost: 0, incomplete_molecules: 0,
                                   reasons: { no_time_column: reason(7, ['declare it there and this atom lands']) } } }),
                'dt_job');
  eq('A5 쟀고 N 이면 수와 사유가 한 줄로', '거절 7 · no_time_column 7', one.text);

  // ══ 사유 낱말은 «응답의 키» 그대로 — 사본 0 ══════════════════════════════════════
  const two = C(report({ dt_job: { reasons: {
    no_time_column: reason(2), undeclared_event_type: reason(9) } } }), 'dt_job');
  eq('A6 여러 사유는 «많은 것부터», 낱말은 그대로',
     '거절 11 · undeclared_event_type 9 · no_time_column 2', two.text);
  ok('A7 화면이 사유를 «번역하지 않는다» — 응답에 없는 낱말이 안 나온다',
     !/[가-힣]/.test(two.text.replace('거절', '')), two.text);

  // ⚠️ 0 인 사유는 마디를 만들지 않습니다 — 「이 사유로는 안 걸렸다」는 그릴 것이 아닙니다.
  eq('A8 0 인 사유는 세지도 그리지도 않는다', '거절 3 · undeclared_event_type 3',
     C(report({ s: { reasons: { no_time_column: reason(0), undeclared_event_type: reason(3) } } }), 's').text);

  // ══ 표본 문장은 «그대로» ═════════════════════════════════════════════════════════
  const sampled = C(report({ s: { reasons: {
    no_time_column: reason(1, ['source `s` declares no time column - declare it there and this atom lands']) } } }), 's');
  eq('A9 표본 detail 이 «한 글자도 안 바뀌고» 툴팁으로',
     'source `s` declares no time column - declare it there and this atom lands', sampled.title);
  eq('A10 표본이 없으면 툴팁도 없다 — 빈 문장을 지어내지 않는다', '',
     C(report({ s: { reasons: { no_time_column: reason(4) } } }), 's').title);

  // ══ 다른 소스의 수를 이 행에 그리지 않는다 ═══════════════════════════════════════
  const many = report({ dt_job: { reasons: { no_time_column: reason(5) } },
                        other: { reasons: { undeclared_event_type: reason(99) } } });
  eq('A11 이 행은 «이 소스»의 수만 말한다', '거절 5 · no_time_column 5', C(many, 'dt_job').text);
  eq('A12 목록에 없는 소스는 0 이 아니라 «빈 칸»', '', C(many, 'absent_source').text);
  ok('A13 ...그리고 그 행도 since 는 받는다(쟀다는 사실은 표 전체의 것)',
     C(many, 'absent_source').since.includes(SINCE));

  // 🔴 THE DISCRIMINATING INPUT, AND THE SWEEP FOUND IT MISSING. A3 uses a report with NO
  //    entry for this source, so it returns at the "no entry" guard and never reaches the
  //    zero-total one — a mutant that deleted the second walked straight through. A source
  //    that IS listed and counted zero is a different shape, and it is the one 「거절 0 이면
  //    빈 칸」 is actually about.
  const listedZero = C(report({ s: { rows_refused: 0, atoms_lost: 0, incomplete_molecules: 0,
                                     reasons: { no_time_column: reason(0) } } }), 's');
  eq('A14 «목록에 있고» 0 인 소스도 「거절 0」을 안 그린다', '', listedZero.text);
  ok('A15 ...다만 since 는 남는다 — 쟀다는 사실은 참이다',
     listedZero.since.includes(SINCE), listedZero.since);
  // 그리고 reasons 가 아예 «빈» 것도 같은 사실입니다.
  eq('A16 사유 블록이 비어도 같다', '',
     C(report({ s: { reasons: {} } }), 's').text);

  return { pass, failures: failures.slice() };
}

const base = await score(undefined);
console.log(`\n${base.failures.length === 0 ? '✓' : '✗'} baseline: ${base.pass} passed, `
  + `${base.failures.length} failed`);
console.log(`ASSERTIONS ${base.pass + base.failures.length} ${base.failures.length}`);

const MUTATIONS = [
  ['M1 a measured zero is drawn as 「거절 0」, so 「none」 and 「not measured」 look alike',
   s => s.replace("  if (total === 0) return Object.freeze({ text: '', title: '', since });", '')],
  ['M2 「not measured」 starts carrying a since, so the two collapse the other way',
   s => s.replace("  if (!report || typeof report !== 'object') return Object.freeze({ ...none });",
                  "  if (!report || typeof report !== 'object') return Object.freeze({ text: '', title: '', since: 'x' });")],
  ['M3 the reason words stop being the response keys',
   s => s.replace('.map(r => `${r.reason} ${r.count}`)', '.map(r => `사유 ${r.count}`)')],
  ['M4 the sample sentence is clipped instead of carried',
   s => s.replace('details.push(String(s.detail))', 'details.push(String(s.detail).slice(0, 10))')],
  ['M5 every source shows the whole table, not its own row',
   s => s.replace('const entry = sourceId != null ? sources[String(sourceId)] : null;',
                  'const entry = Object.values(sources)[0] || null;')],
  ['M6 a zero-count reason still takes a segment',
   s => s.replace('    .filter(r => r.count > 0)', '')],
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
