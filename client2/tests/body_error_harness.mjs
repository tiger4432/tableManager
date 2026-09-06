// BODY ERROR — 「이 본문이 오류를 나르나」가 «봉투 둘 다»에서 참인가.
//
// The subject is imported (owner, 2026-09-02: 잘라쓰기 하니스 절대 금지). `body_error.js`
// touches no DOM and no CSS at module scope, so it imports in node as it stands.
//
// 🔴 THIS FILE EXISTS FOR ONE THING — 변이 «둘», 봉투마다 하나 (총괄 판정 22).
//    한 번만 걸면 「이름이 같으니 같은 함수」를 또 믿는 것이다. 그래서 각 표본에 «어느
//    갈래가 답해야 하는지»를 적고, 그 표본은 «그 갈래로만» 잡히게 만든다:
//      봉투 A 표본 -> `error` 키가 «아예 없다». 갈래 A 를 지우면 null 이 되어 빨개진다
//      봉투 B 표본 -> `status` 키가 «아예 없다». 갈래 B 를 지우면 null 이 되어 빨개진다
//    두 규칙이 «같은 답을 내는» 표본은 판별식이 아니므로 하나도 쓰지 않았다.
//
// 🔴 그리고 이 파일이 «오늘 잡은» 것: 봉투 B 는 성한 응답에도 `error` 키가 «있다»(값 null).
//    그래서 F-10 의 검사를 「`error` 라는 칸이 있나」로 복사했으면 «성한 응답 전부»가
//    오류가 됐다. 성질로 물으면 그 사고가 안 난다 — 아래 healthy-B 표본이 그 자리다.
//
// ⛔ 여기 본문은 «모양»이다. 이 상자의 행이 아니고, 운영 값도 아니다.
//
// Run: node client2/tests/body_error_harness.mjs
import { errorText, UNSAID } from '../src/body_error.js';

let pass = 0;
const failures = [];
const answeredBy = { A: 0, B: 0 };

function check(name, branch, body, want) {
  const got = errorText(body);
  if (got === want) {
    pass++;
    if (branch) answeredBy[branch]++;
    console.log(`  PASS ${name}`);
  } else {
    failures.push(name);
    console.log(`  FAIL ${name}\n        got  ${JSON.stringify(got)}\n        want ${JSON.stringify(want)}`);
  }
}

// ── 봉투 A — main.py admin 계열. 판별자는 `status` 의 «값»이다 ──────────────
// 셋 다 `error` 키가 «없다»: 갈래 A 가 지워지면 셋이 «같이» 빨개진다.

console.log('envelope A — status carries the verdict');
check('chain rules: a broken declaration is an error, not an empty list', 'A',
  { status: 'error', message: "JSONDecodeError: Expecting ',' delimiter: line 12", data: [] },
  "JSONDecodeError: Expecting ',' delimiter: line 12");

check('auto-update status: same envelope, same illness', 'A',
  { status: 'error', message: 'PermissionError: scheduler_status.json', data: [] },
  'PermissionError: scheduler_status.json');

// 🔴 등급 1. 이 자리는 「없다」가 아니라 「됐다」를 그렸다 — 서버는 롤백하고 200 을 낸다.
check('run-now: a rolled-back trigger is not a published one', 'A',
  { status: 'error', message: 'OperationalError: server closed the connection' },
  'OperationalError: server closed the connection');

check('a success body is not an error', null,
  { status: 'success', data: [1, 2, 3] }, null);

check('run-now success carries a message too — a message is not a failure', null,
  { status: 'success', message: 'Successfully published trigger to run ...' }, null);

// 실패했다고 «말은 했는데» 사유가 없는 경우. null 을 돌려주면 「오류 없음」을 «단언»하게 된다.
check('an error with nothing said is still an error', 'A',
  { status: 'error', message: '', data: [] }, UNSAID);
check('… and a missing message field does not become the string "null"', 'A',
  { status: 'error', data: [] }, UNSAID);

// ── 봉투 B — ledger_admin 계열. 판별자는 `error` 가 «참인가»다 ─────────────
// `status` 키가 «없다»: 갈래 B 가 지워지면 이 자리가 빨개진다.

console.log('envelope B — the error key carries the verdict, by truth not by presence');
check('ledger sources: the declaration will not parse (F-10 stays closed)', 'B',
  { kinds: [], sources: {}, config_path: '/…/ledger_config.json',
    error: 'JSONDecodeError: Expecting value: line 3' },
  'JSONDecodeError: Expecting value: line 3');

// 🔴 이 표본이 「기제로 묻기」가 죽는 자리다: `'error' in body` 는 여기서 «참»이다.
check('a healthy ledger body carries error: null — and is NOT an error', null,
  { kinds: [], sources: { lot: {} }, config_path: '/…/ledger_config.json', error: null },
  null);

// ── 이웃한 사실들이 오류로 «오인»되지 않는다 ────────────────────────────────

console.log('neighbours that must not be read as failures');
// server/listing_absence.py — 「원천이 없다」는 «사실»이지 실패가 아니다.
check('an absent listing is a fact, not a failure', null,
  { status: 'success', data: [], state: 'absent', absent_path: '/…/chain_rules.json' }, null);
check('an empty list is not a failure', null, { status: 'success', data: [] }, null);
check('a body that never parsed is not a claim either', null, null, null);
check('… nor is a non-object', null, 'not json', null);
check('… nor is undefined', null, undefined, null);

// ── 🔴 변이 «둘»의 계산서 ────────────────────────────────────────────────────
// 갈래 하나를 지웠을 때 «몇 자리»가 빨개지는지를 여기서 «센다». 0 이나 1 이면 그 갈래는
// 이 하니스가 지키고 있지 않다는 뜻이고, 그때 사본이 조용히 갈라진다.
console.log('mutation ledger');
function counted(name, branch, atLeast) {
  if (answeredBy[branch] >= atLeast) { pass++; console.log(`  PASS ${name} (${answeredBy[branch]})`); }
  else {
    failures.push(name);
    console.log(`  FAIL ${name} — ${answeredBy[branch]} site(s) depend on branch ${branch}, wanted ${atLeast}`);
  }
}
counted('removing the envelope-A branch reddens the three admin routes', 'A', 3);
counted('removing the envelope-B branch reddens the ledger route', 'B', 1);

console.log(`\n${failures.length ? 'FAIL' : 'PASS'}  ${pass} passed, ${failures.length} failed`);
// 🔴 The runner's evidence line. Exit code alone cannot tell 「red」 from 「never asserted」.
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
if (failures.length) { console.log(failures.map(f => `  - ${f}`).join('\n')); process.exit(1); }
