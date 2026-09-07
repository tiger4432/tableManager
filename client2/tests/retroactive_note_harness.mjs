/**
 * 🔁 S-36 — 대기열의 소급 행이 «자기가 무엇인지» 말하나. 대상을 IMPORT 해서 잽니다.
 *
 * 🔴 이 하니스가 지키는 것은 «두 갈래»입니다:
 *      ① 소급 행: 서버가 실어 온 낱말이 «그대로» 한 줄이 된다
 *      ② 소급이 아닌 행: 어제와 «한 글자도» 다르지 않다
 *    ②가 없으면 「새 줄을 더했다」와 「멀쩡하던 칸을 덮었다」가 같은 초록이 됩니다.
 *
 * Run:  node client2/tests/retroactive_note_harness.mjs [--mutate]
 */
import { loadWithProbe } from './lib/probe.mjs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src', 'retroactive_note.js');

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
    expose: ['retroactiveNote', 'paramsSummary'],
    mutate,
    tag: 'retronote',
  });
  const N = probe.retroactiveNote;

  // ══ ② 소급이 아닌 행 — 아무것도 그리지 않는다 ════════════════════════════════════
  // 🔴 키가 «없다»는 것은 「이 묶음에 소급이 없다」입니다. 빈 문자열이라야 부르는 쪽의
  //    `||` 가 어제 그리던 것으로 떨어집니다 — 여기서 무엇이든 내놓으면 멀쩡한 표 이름을 덮습니다.
  eq('A1 키가 없으면 아무 말도 안 한다', '', N(undefined));
  eq('A2 null 도 같다', '', N(null));
  eq('A3 빈 배열도 같다 — 「섞인 게 없다」와 같은 사실', '', N([]));
  eq('A4 배열이 아닌 것을 받아도 조용하다', '', N({ op: 'x' }));

  // ══ ① 소급 행 — 서버의 낱말 그대로 ══════════════════════════════════════════════
  const one = [{ run_id: 'r1', op: 'enrichment_confirm', requested_by: 'kk980',
                 params: { rule: 'dt_frame' }, outbox_id: 12 }];
  eq('A5 op·요청자·인자가 한 줄에, 서버 값 그대로',
     '소급 · enrichment_confirm · kk980 · {"rule":"dt_frame"}', N(one));

  // 🔴 「물었는데 아무도 안 적었다」와 「해당 없음」은 다른 사실입니다. 앞은 «없음»을 그립니다.
  eq('A6 요청자가 null 이면 「없음」 — 빈칸이 아니다',
     '소급 · enrichment_confirm · 없음 · {"rule":"dt_frame"}',
     N([{ ...one[0], requested_by: null }]));
  eq('A7 op 이 null 이어도 자리는 남는다 (그 행이 소급이라는 사실은 남는다)',
     '소급 · 없음 · kk980 · {"rule":"dt_frame"}', N([{ ...one[0], op: null }]));

  // 인자가 «없는» 것과 «빈» 것은 그릴 것이 없다는 점에서 같습니다 — 자리만 사라집니다.
  eq('A8 인자가 없으면 그 마디만 빠진다',
     '소급 · enrichment_confirm · kk980', N([{ ...one[0], params: null }]));
  eq('A9 빈 인자도 마디를 만들지 않는다',
     '소급 · enrichment_confirm · kk980', N([{ ...one[0], params: {} }]));

  // ══ 🔴 배열이다 — 지시서는 객체 하나라고 했고, 서버는 append 한다 ═══════════════
  const two = [one[0], { run_id: 'r2', op: 'backfill', requested_by: 'ops', params: null }];
  ok('A10 둘째 소급 행이 «사라지지 않는다»',
     N(two).includes('backfill') && N(two).includes('enrichment_confirm'), N(two));
  ok('A11 ...그리고 둘이 «갈라져» 보인다', N(two).split(' | ').length === 2, N(two));

  // ══ 자르는 것은 «길이»이지 뜻이 아니다 ═══════════════════════════════════════════
  const long = { ...one[0], params: { note: 'x'.repeat(200) } };
  const text = N([long]);
  ok('A12 긴 인자는 잘리고, 잘렸다고 말한다', text.endsWith('…'), text.slice(-20));
  ok('A13 ...그리고 앞의 낱말들은 살아 있다',
     text.startsWith('소급 · enrichment_confirm · kk980 · '), text.slice(0, 40));
  // 🔴 자르기가 «뜻을 짓지» 않는지: 서버 문자열의 앞부분이 그대로 남아야 합니다.
  ok('A14 잘린 것은 서버 값의 «앞부분» 그대로', text.includes('{"note":"xxxx'), text.slice(0, 80));

  // 문자열 인자(서버가 그렇게 보내는 자리)도 그대로 지나갑니다.
  eq('A15 문자열 인자는 JSON 으로 감싸지 않는다',
     '소급 · backfill · ops · rule=dt_frame',
     N([{ op: 'backfill', requested_by: 'ops', params: 'rule=dt_frame' }]));

  return { pass, failures: failures.slice() };
}

const base = await score(undefined);
console.log(`\n${base.failures.length === 0 ? '✓' : '✗'} baseline: ${base.pass} passed, `
  + `${base.failures.length} failed`);
console.log(`ASSERTIONS ${base.pass + base.failures.length} ${base.failures.length}`);

const MUTATIONS = [
  ['M1 a non-retroactive row starts drawing something (the table name gets covered)',
   s => s.replace("  if (!Array.isArray(list) || list.length === 0) return '';",
                  "  if (!Array.isArray(list)) return '';")],
  ['M2 「없음」 collapses into a blank, so "nobody said" reads as "not applicable"',
   s => s.replace("      ? String(r.requested_by) : UNSAID;", "      ? String(r.requested_by) : '';")],
  ['M3 only the first retroactive row survives',
   s => s.replace('list.map(one).join(\' | \')', 'one(list[0])')],
  ['M4 the params are dropped instead of trimmed',
   s => s.replace('  return text.length > PARAMS_CAP ? `${text.slice(0, PARAMS_CAP)}…` : text;',
                  '  return text.length > PARAMS_CAP ? \'\' : text;')],
  ['M5 the trim stops saying it trimmed',
   s => s.replace('`${text.slice(0, PARAMS_CAP)}…`', 'text.slice(0, PARAMS_CAP)')],
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
