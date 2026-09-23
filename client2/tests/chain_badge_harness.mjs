// chain_badge — 메인 그리드의 「체인이 살아 있나」 뱃지. (지시 2df0a7e26)
// Run: node client2/tests/chain_badge_harness.mjs
//
// 🔴 이 라운드가 왜 있나. 오늘 아침 체인 워커가 멈췄고, 소유자는 그것을 「대기열이 안 빠진다」로
//    «간접적으로» 발견하셨다. 신호가 보시는 자리에 없었다.
//
// 🔴 그리고 이 파일이 «무엇을» 재나 — 「화면이 서버의 판정을 그대로 그리는가」다.
//    서버가 낱말을 이미 짓는다(`server/runtime/health.py`): down · unknown · starting ·
//    foreign_beat · missing · wedged · stale · stalled · ok · off_roster.
//    ⚠️ 그래서 지시의 변이(「age_seconds 를 크게 만들면 빨개진다」)는 «이 설계에서 안 난다» —
//       나이로 판정하는 것은 서버이고, 화면이 다시 재면 임계값이 두 벌이 된다.
//       여기서는 그 자리를 «뒤집어» 잰다: status 를 바꾸면 따라 바뀌고(M1), age 만 바꾸면
//       «안 바뀐다»(M2). 둘째가 이 설계의 «성질»이다.
import { chainBadge } from '../src/api.js';

let pass = 0; const failures = [];
const eq = (what, got, want) => {
  if (String(got) === String(want)) { pass += 1; console.log(`  PASS ${what}`); }
  else { failures.push(what); console.log(`  FAIL ${what} -- got ${got}, want ${want}`); }
};
const ok = (what, cond, shown) => eq(what, cond ? 'true' : `false (${shown})`, 'true');

/** 총괄이 실제로 불러 받은 모양 그대로 (지시 2df0a7e26 에 실린 응답). */
const HEALTH = (chain) => ({
  status: chain.status === 'ok' ? 'ok' : 'unhealthy',
  checked_at: '2026-09-23T01:00:00+00:00',
  problems: [],
  checks: { workers: { chain } },
});
const RUNNING = { supervisor_state: 'running', status: 'ok', age_seconds: 0.37,
                  stale_after_seconds: 60.0, pid: 46360, restarts: 0 };

console.log('\n[살아 있을 때]');
{
  const v = chainBadge(HEALTH(RUNNING));
  eq('H1 a healthy worker reads as ok', v.text, 'CHAIN: OK');
  eq('H1b ...and wears the same online class the API·WS badges use', v.cls, 'status-badge online');
  eq('H1c ...and says nothing more — there is no reason to give', v.title, '');
}

console.log('\n[멈췄을 때 — 두 실패는 «다른 말»이다 (게이트 ㉢)]');
{
  // 프로세스는 살아 있는데 고리가 멈춘 것. 오늘 아침이 이 모양이었다.
  const wedged = chainBadge(HEALTH({ ...RUNNING, status: 'wedged', age_seconds: 214.0,
                                     detail: '' }));
  // 감독자가 프로세스가 없다고 말하는 것.
  const down = chainBadge(HEALTH({ ...RUNNING, supervisor_state: 'stopped', status: 'down',
                                   detail: "supervisor reports state 'stopped'" }));
  eq('D1 a wedged loop says WEDGED', wedged.text, 'CHAIN: WEDGED');
  eq('D2 a missing process says DOWN', down.text, 'CHAIN: DOWN');
  ok('D3 the two never read alike — the repairs are different',
    wedged.text !== down.text, `${wedged.text} / ${down.text}`);
  eq('D4 both go offline', `${wedged.cls}|${down.cls}`, 'status-badge offline|status-badge offline');
  eq('D5 the server\'s sentence rides along, verbatim', down.title,
    "supervisor reports state 'stopped'");
  // 🔴 M1 — 판정을 바꾸면 화면이 «따라» 바뀐다
  eq('M1 MUTATION: change the server\'s verdict and the badge follows',
    chainBadge(HEALTH({ ...RUNNING, status: 'missing' })).text, 'CHAIN: MISSING');
  // 🔴 M2 — 나이만 바꾸면 «안» 바뀐다. 나이로 재는 것은 서버의 일이다
  eq('M2 CONTROL: age alone does not move the badge — that judgment is the server\'s',
    chainBadge(HEALTH({ ...RUNNING, age_seconds: 99999 })).text, 'CHAIN: OK');
}

console.log('\n[못 읽었을 때 — 「모름」을 「이상 없다」로 그리지 않는다 (게이트 ㉣)]');
{
  const none = chainBadge(null);
  eq('U1 no payload reads as unknown, not ok', none.text, 'CHAIN: ?');
  eq('U1b ...and is neither green nor red', none.cls, 'status-badge');
  // 503 은 «본문이 있는» 실패다. 본문을 읽으므로 뱃지는 그때도 말한다.
  const unhealthy = chainBadge({ status: 'unhealthy', checks: { workers: { chain:
    { ...RUNNING, status: 'wedged' } } } });
  eq('U2 a 503 body still speaks', unhealthy.text, 'CHAIN: WEDGED');
  eq('U3 a payload without the chain row is unknown, not ok',
    chainBadge({ status: 'ok', checks: { workers: {} } }).text, 'CHAIN: ?');
  eq('U4 a worker row with no status word is unknown too',
    chainBadge(HEALTH({ supervisor_state: 'running' })).text, 'CHAIN: ?');
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
