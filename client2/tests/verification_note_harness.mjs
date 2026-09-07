/**
 * 🏷️ S-46 — 「미검증」이 «왜» 미검증인가. 대상을 IMPORT 해서 잽니다.
 *
 * 🔴 세 상태가 «값으로» 갈려야 합니다. 「한 번도 안 돌았다」와 「돌았는데 선언이 바뀌었다」는
 *    조작자에게 «정반대의 다음 행동»이고, 한 낱말로 덮으면 그 차이가 화면에서 사라집니다.
 *
 * Run:  node client2/tests/verification_note_harness.mjs [--mutate]
 */
import { loadWithProbe } from './lib/probe.mjs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src', 'verification_note.js');

let pass = 0;
const failures = [];
const ok = (name, cond, detail = '') => {
  if (cond) { pass += 1; console.log(`  PASS ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name}${detail ? ' — ' + detail : ''}`); }
};
const eq = (name, expected, actual) => ok(name, actual === expected,
  `expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);

// The server's own shapes, from `config_explorer_service` — record absent / hash differs /
// hash matches. Written as the route writes them so a change there reddens this.
const NEVER = { target_key: 'source_plan|s', status: 'unverified', ran_at: null,
                rows_read: null, molecules: null, atoms: null, stale: false };
const CHANGED = { target_key: 'source_plan|s', status: 'unverified',
                  ran_at: '2026-09-07T10:00:00+00:00', rows_read: null, molecules: null,
                  atoms: null, stale: true };
const VERIFIED = { target_key: 'source_plan|s', status: 'verified',
                   ran_at: '2026-09-07T10:00:00+00:00', rows_read: 12, molecules: 3,
                   atoms: 9, stale: false };

async function score(mutate) {
  pass = 0; failures.length = 0;
  const { probe } = await loadWithProbe(SRC, {
    expose: ['verificationNote'], mutate, tag: 'verifnote',
  });
  const N = probe.verificationNote;

  // ══ 세 상태가 «값으로» 갈린다 ═══════════════════════════════════════════════════════
  eq('A1 검증된 소스는 배지가 없다', '', N(VERIFIED));
  eq('A2 한 번도 안 돌았으면 그렇게 말한다',
     '● 미검증 · 이 소스로 아직 실행 안 됨', N(NEVER));
  eq('A3 돌았는데 선언이 바뀌었으면 «다른 낱말»', '● 미검증 · 선언 변경됨', N(CHANGED));
  ok('A4 그 둘이 «갈린다» — 같은 낱말이면 다음 행동이 사라진다', N(NEVER) !== N(CHANGED));

  // 🔴 순서가 이 판정의 전부입니다. `stale` 인 레코드도 `ran_at` 을 «들고» 있으므로,
  //    「ran_at 없음」을 먼저 보면 안 걸리고, 「stale」을 나중에 보면 먹힙니다.
  eq('A5 stale 이 ran_at 보다 «먼저» 읽힌다',
     '● 미검증 · 선언 변경됨', N({ ...CHANGED, ran_at: null }));

  // ══ 모르는 모양은 «오늘 그리던 것»을 그대로 ═══════════════════════════════════════
  // ⚠️ 옛 서버는 이 키들을 «안 보낼» 수 있습니다. 그때 「아직 실행 안 됨」을 그리면
  //    «안 물어본 것»을 «답»으로 만듭니다.
  eq('A6 키가 없는 옛 응답은 종전 낱말 그대로', '● 미검증',
     N({ target_key: 'source_plan|s', status: 'unverified' }));
  eq('A7 레코드가 없으면 아무것도 안 그린다', '', N(null));
  eq('A8 레코드가 아니어도 같다', '', N('unverified'));

  return { pass, failures: failures.slice() };
}

const base = await score(undefined);
console.log(`\n${base.failures.length === 0 ? '✓' : '✗'} baseline: ${base.pass} passed, `
  + `${base.failures.length} failed`);
console.log(`ASSERTIONS ${base.pass + base.failures.length} ${base.failures.length}`);

const MUTATIONS = [
  ['M1 the two unverified states collapse into one word',
   s => s.replace("  if (verified.ran_at == null && verified.stale === false) return NEVER_RAN;", '')],
  ['M2 the order flips, so a changed declaration reads as never run',
   s => s.replace("  if (verified.stale === true) return CHANGED;\n", '')],
  ['M3 an old response with no keys is told it never ran',
   s => s.replace('verified.ran_at == null && verified.stale === false',
                  'verified.ran_at == null')],
  ['M4 a verified source grows a badge',
   s => s.replace("  if (verified.status === 'verified') return '';", '')],
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
