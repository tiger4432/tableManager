/**
 * ⚖️ S-35 — 확정 «응답»의 판정이 읽히나. 대상을 IMPORT 해서 잽니다.
 *
 * 이 하니스가 지키는 것은 «둘»입니다:
 *   ① 독자 — 세 경우(받았다 · 뒤집었다 · 고를 후보 없음)가 «값으로» 갈린다
 *   ② 세션 — 그 판정이 «그 단위의 그 행위»와 함께 죽는다. 다음 단위로 따라가면 화면이
 *            «보지도 않은 단위»에 대해 답합니다
 *
 * Run:  node client2/tests/confirm_ruling_harness.mjs [--mutate]
 */
import { loadWithProbe } from './lib/probe.mjs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { createMapSession, withConfirmed, withSelectedCandidate, withDecision, withConfirmFailed }
  from '../src/map2/session.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src', 'map2', 'confirm_ruling.js');

let pass = 0;
const failures = [];
const ok = (name, cond, detail = '') => {
  if (cond) { pass += 1; console.log(`  PASS ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name}${detail ? ' — ' + detail : ''}`); }
};
const eq = (name, expected, actual) => ok(name, JSON.stringify(actual) === JSON.stringify(expected),
  `expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);

const record = (winner, confirmed, state = 'scored') => ({
  confirmation_uid: 'u1', version: 1,
  confirmed: { frame: confirmed, map_table: 'dt_log', columns: {} },
  ruling: { state, reason_code: null, winner, margin: 3, discriminating: 12 },
});

async function score(mutate) {
  pass = 0; failures.length = 0;
  const { probe } = await loadWithProbe(SRC, {
    expose: ['confirmRulingNote', 'RULING_ACCEPTED', 'RULING_OVERRIDDEN',
             'RULING_NO_CANDIDATE', 'RULING_UNRECORDED'],
    mutate,
    tag: 'confirmruling',
  });
  const N = probe.confirmRulingNote;

  // ══ ① 세 경우가 «값으로» 갈린다 ═════════════════════════════════════════════════
  eq('A1 후보를 그대로 받았다',
     { state: probe.RULING_ACCEPTED, text: '채점기 후보 그대로' },
     N(record('rot90_front', 'rot90_front')));
  eq('A2 뒤집었다 — 이름 «둘»을, 일이 일어난 순서로',
     { state: probe.RULING_OVERRIDDEN, text: '채점기 rot90_front → 확정 rot270_back' },
     N(record('rot90_front', 'rot270_back')));
  eq('A3 고를 후보가 없었다',
     { state: probe.RULING_NO_CANDIDATE, text: '이긴 후보 없음' },
     N(record(null, 'rot90_front', 'no_winner')));
  // 🔴 「채점했는데 이긴 후보가 없다」와 「채점이 성립조차 안 했다」는 조작자에게 다른 상황입니다.
  eq('A4 채점 자체가 성립 안 한 것은 «다른 낱말»',
     { state: probe.RULING_NO_CANDIDATE, text: '채점 불가' },
     N(record(null, 'rot90_front', 'not_scorable')));
  ok('A5 그 둘이 «갈린다»',
     N(record(null, 'x', 'no_winner')).text !== N(record(null, 'x', 'not_scorable')).text);
  // 🔴 기본 문장은 `winner` 하나가 받칩니다 — 처음 보는 상태 낱말에도 참으로 남아야 합니다.
  eq('A6 모르는 상태 낱말이어도 「이긴 후보 없음」은 참이다',
     '이긴 후보 없음', N(record(null, 'x', 'something_new')).text);

  // ══ 세 상태: 「말 안 함」을 「없음」으로 접지 않는다 ═══════════════════════════════
  eq('A7 `ruling` 키가 «없으면» 아무것도 안 그린다',
     { state: probe.RULING_UNRECORDED, text: '' },
     N({ confirmed: { frame: 'rot90_front' } }));
  eq('A8 `ruling: null` 도 같다 — 다만 이건 «이 서버»가 말하는 것이다',
     { state: probe.RULING_UNRECORDED, text: '' },
     N({ ruling: null, confirmed: { frame: 'rot90_front' } }));
  eq('A9 응답이 아니면 아무것도 안 그린다',
     { state: probe.RULING_UNRECORDED, text: '' }, N(null));
  // 견줄 것이 없는 승자는 비교가 아닙니다.
  eq('A10 확정 프레임이 없는 응답은 «비교하지 않는다»',
     { state: probe.RULING_UNRECORDED, text: '' },
     N({ ruling: { winner: 'rot90_front' } }));

  // 🔴 SWAP-PROOF: 두 이름이 «자리»를 지키는지. 「둘 다 나온다」는 뒤바뀜을 통과합니다.
  const flipped = N(record('A', 'B')).text;
  ok('A11 채점기 이름이 «앞», 확정 이름이 «뒤»',
     flipped.indexOf('A') < flipped.indexOf('B'), flipped);

  // ══ ② 세션 — 판정은 «그 단위의 그 행위»와 함께 죽는다 ═══════════════════════════
  const note = { state: 'accepted', text: '채점기 후보 그대로' };
  const landed = withConfirmed(createMapSession({}), note);
  eq('B1 확정과 함께 실린다', note, landed.confirmRuling);
  eq('B2 다른 후보를 고르면 죽는다', null, withSelectedCandidate(landed, 'other').confirmRuling);
  eq('B3 다른 단위로 가면 죽는다',
     null, withDecision(landed, { eqp: 'E2' }).confirmRuling);
  // 🔴 거절과 판정은 «같은 행위에 대한 배타적인 두 주장»입니다. 둘이 같이 서면 화면이
  //    자기 모순을 말합니다 — 그래서 거절이 판정을 «지웁니다».
  eq('B4 거절이 오면 앞선 판정은 죽는다',
     null, withConfirmFailed(landed, '거절 사유').confirmRuling);
  eq('B5 판정이 없는 확정은 null 이지, 지어낸 값이 아니다',
     null, withConfirmed(createMapSession({})).confirmRuling);

  return { pass, failures: failures.slice() };
}

const base = await score(undefined);
console.log(`\n${base.failures.length === 0 ? '✓' : '✗'} baseline: ${base.pass} passed, `
  + `${base.failures.length} failed`);
console.log(`ASSERTIONS ${base.pass + base.failures.length} ${base.failures.length}`);

const MUTATIONS = [
  ['M1 an overruled ruling is reported as an accepted one',
   s => s.replace('  if (confirmed === winner) {', '  if (true) {')],
  ['M2 the two names swap places',
   s => s.replace('text: `채점기 ${winner} → 확정 ${confirmed}`,',
                  'text: `채점기 ${confirmed} → 확정 ${winner}`,')],
  ['M3 「not scorable」 is folded into 「no winner」',
   s => s.replace('ruling.state === STATE_NOT_SCORABLE ? MARK_UNSCORABLE : MARK_NONE',
                  'MARK_NONE')],
  // 🔴 M4 WAS AN EQUIVALENT MUTANT AND THE SOURCE CHANGED INSTEAD. It removed a
  //    `hasOwnProperty` guard that claimed to tell an absent `ruling` from a null one — and
  //    both fell through to the same answer, so deleting it changed nothing. The guard is gone
  //    from the subject; a branch that asserts a distinction its answers do not make is a false
  //    claim in code, and chasing it with an assertion would have made the harness lie too.
  ['M4 an unreadable ruling block is drawn as 「no winner」 instead of nothing',
   s => s.replace("  if (!ruling || typeof ruling !== 'object') return NOTHING;", '')],
  ['M5 a blank winner is treated as a name, so the comparison runs on ""',
   s => s.replace("  const winner = ruling.winner != null && String(ruling.winner) !== ''",
                  '  const winner = ruling.winner !== undefined')],
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
