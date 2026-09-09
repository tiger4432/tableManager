/**
 * 🏷️ C-48 — 「이 푸시가 몇 행을 바꿨나」. 대상을 IMPORT 해서 잽니다.
 *
 * 🔴 THE DEFECT THIS EXISTS FOR IS A FALSY ZERO. Ruling 192 made the server's
 *    `updated_count` mean 「rows this request changed or created」, so a fully unchanged
 *    re-push now correctly answers 0 — and `a || b || c` throws that answer away, because
 *    0 is falsy in JavaScript. The toast then reported the PAYLOAD SIZE: an unchanged push
 *    of 200 cells said 「적재 완료 — 200건」. That is not a blank where a number should be;
 *    it is an INVENTED number where the true one was 0.
 *
 * 🔴 THE DISCRIMINATING FIXTURE IS `{updated_count: 0, count: 9}`. Every other fixture is
 *    answered the same way by the old chain and the new rule, so only this one — where the
 *    correct answer is falsy AND a later link is truthy — tells them apart.
 *
 * 🔴 AND THE TWO CALL SITES MUST NOT SPLIT. The success toast and the 「규격 저장 실패」
 *    toast both name this number; criterion ④ is not 「둘이 있나」 but 「둘이 갈라질 수 있나」.
 *    They share this function, so a fix cannot land on one of them.
 *
 * Run:  node client2/tests/changed_rows_harness.mjs [--mutate]
 */
import { loadWithProbe } from './lib/probe.mjs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src', 'changed_rows.js');

let pass = 0;
const failures = [];
const ok = (name, cond, detail = '') => {
  if (cond) { pass += 1; console.log(`  PASS ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name}${detail ? ' — ' + detail : ''}`); }
};
const eq = (name, expected, actual) => ok(name, actual === expected,
  `expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);

async function score(mutate) {
  pass = 0; failures.length = 0;
  const { probe } = await loadWithProbe(SRC, {
    expose: ['changedRowsText', 'NOTHING_CHANGED'], mutate, tag: 'changed',
  });
  const text = probe.changedRowsText;
  const NONE = probe.NOTHING_CHANGED;

  // ══ ① 0 은 «답»입니다 — 그리고 그것이 이 파일의 전부입니다 ═══════════════════════════
  eq('A1 an unchanged push says so, instead of reporting what was SENT', NONE, text({ updated_count: 0 }, 200));
  eq('A2 a real count is drawn', '235건', text({ updated_count: 235 }, 200));
  // 🔴 THE DISCRIMINANT: the old `||` chain and the new rule agree on every fixture EXCEPT
  //    one where the right answer is falsy and a later link is truthy.
  eq('A3 zero beats a truthy later link — the one fixture the old chain got wrong',
    NONE, text({ updated_count: 0, count: 9 }, 200));
  eq('A4 ...while a non-zero first link still wins', '3건', text({ updated_count: 3, count: 9 }, 200));

  // ══ ② 폴백은 «없을 때만» ═══════════════════════════════════════════════════════════
  eq('B1 an absent count falls back to what was sent', '200건', text({}, 200));
  eq('B2 a null count is absent, not zero', '4건', text({ updated_count: null, count: 4 }, 200));
  eq('B3 the second link obeys the same rule', NONE, text({ count: 0 }, 200));
  eq('B4 ...and draws its number when it has one', '7건', text({ count: 7 }, 200));
  eq('B5 a sent count of zero is still zero, not a dash', NONE, text({}, 0));

  // ══ ③ 0 은 «낱말»이지 「0건」이 아닙니다 ═══════════════════════════════════════════
  // ⛔ 문장이 아니라 낱말입니다 (소유자 상설: 「ui에 설명 문구 주저리주저리 금지」).
  eq('C1 the zero word is the fact, not a unit', '바뀐 것 없음', NONE);
  ok('C2 ...and it is not 「0건」', text({ updated_count: 0 }, 5) !== '0건',
    text({ updated_count: 0 }, 5));

  // ══ ④ 못 얻은 수는 «0 이 아닙니다» ════════════════════════════════════════════════
  // 🔴 UNREACHABLE FROM TODAY'S CALL SITE — it passes an array length, which is always a
  //    number. Scored anyway, and said plainly: this shape is the guard's own, not the
  //    wire's. A blank that silently became 「바뀐 것 없음」 would claim a measurement
  //    nobody took, which is the same collapse this file exists to prevent.
  eq('D1 no number anywhere is a dash, never a zero', '—', text(null, null));
  eq('D2 ...and a non-numeric fallback does not become one', '—', text({}, 'abc'));
  ok('D3 CONTROL: the dash and the zero word are different pixels',
    text(null, null) !== text({ updated_count: 0 }, 1));

  // ══ ⑤ 0 이 아닌 수의 픽셀은 이 수리 «전후로 같습니다» ══════════════════════════════
  // ⚠️ 천단위 구분을 넣으면 변경 범위가 「0 인 경우」를 넘어섭니다. 이 단언이 그 경계입니다.
  eq('E1 a four-digit count carries no separator, exactly as before', '1205건',
    text({ updated_count: 1205 }, 0));

  return { pass, failures: failures.slice() };
}

const base = await score(undefined);
console.log(`\n${base.failures.length === 0 ? '✓' : '✗'} baseline: ${base.pass} passed, `
  + `${base.failures.length} failed`);
console.log(`ASSERTIONS ${base.pass + base.failures.length} ${base.failures.length}`);

const MUTATIONS = [
  ['M1 the `||` chain comes back, so an unchanged push reports the payload size',
   s => s.replace(/const count = isCount[\s\S]*?: null;/,
                  'const count = r.updated_count || r.count || sentCount;')],
  ['M2 zero is drawn as a count, so 「아무것도 안 바뀜」 reads as a load of nothing',
   s => s.replace("return count === 0 ? NOTHING_CHANGED : `${count}건`;",
                  'return `${count}건`;')],
  ['M3 the fallback wins over the answer, so `count` overrides `updated_count`',
   s => s.replace('const count = isCount(r.updated_count) ? Number(r.updated_count)\n    : isCount(r.count) ? Number(r.count)',
                  'const count = isCount(r.count) ? Number(r.count)\n    : isCount(r.updated_count) ? Number(r.updated_count)')],
  ['M4 an unobtainable number becomes 0, claiming a measurement nobody took',
   s => s.replace('  if (count === null) return ABSENT;', '  if (count === null) return NOTHING_CHANGED;')],
  ['M5 the first link is read for truthiness again — the exact defect, one link in',
   s => s.replace('isCount(r.updated_count) ? Number(r.updated_count)',
                  'r.updated_count ? Number(r.updated_count)')],
  ['M6 the zero word is replaced by a unit, losing what the 0 means',
   s => s.replace("export const NOTHING_CHANGED = '바뀐 것 없음';",
                  "export const NOTHING_CHANGED = '0건';")],
  ['M7 the number is separated by thousands, which widens this fix past the zero case',
   s => s.replace('return count === 0 ? NOTHING_CHANGED : `${count}건`;',
                  'return count === 0 ? NOTHING_CHANGED : `${count.toLocaleString()}건`;')],
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
