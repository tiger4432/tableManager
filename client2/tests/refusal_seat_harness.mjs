// refusal_seat — `/admin/**` 로 가는 «전송 하나»와 그 거절을 «읽는 자리 하나». (C-122)
// Run: node client2/tests/refusal_seat_harness.mjs
//
// 🔴 이 라운드가 왜 있나. 같은 물음(「무엇이 잘못됐나」)에 철자가 «둘»이었습니다:
//
//    admin.js   adminFetch 로 «보내고» failureFactOf -> retroFailureLine 으로 «읽습니다»
//    main.js    맨 fetch 로 «보내고»  `why = ${res.status}` 에 detail 을 붙여 «지었습니다»
//
//    오늘 같은 답을 내더라도 «갈라질 수 있습니다» — 판별식 ④ 그대로이고, 갈라진 것은
//    오류를 내지 않습니다. 실제로 이미 갈라져 있었습니다: 맨 fetch 쪽은 토큰 부착 · 503 본문 ·
//    날아가는 중 토큰 교체 · 게이트 재질문을 «전부» 못 받았습니다.
//
// 🔴 전수(제가 셌습니다, 2026-09-16): `/admin/**` 을 «맨 fetch» 로 부르는 자리 «1»
//    (main.js 의 소급 실행). 총괄이 전에 인용한 「55 대 4」는 «잰 수가 아니었습니다» —
//    다시 셌고, 이 파일의 S1 이 그 「1 -> 0」을 «성질»로 못 박습니다.
// ⚠️ `adminFetch` 호출 수는 여기 «적지 않습니다». 아래 S2 가 그때그때 재서 보고합니다 —
//    머리글에 박아 두면 다음 라운드에 제 문장이 «제 전제»를 거짓으로 만듭니다.
//
// 🔴 이 파일의 절반은 «이음매»이고 절반은 «동작»입니다:
//      전송  `admin_token.adminFetch`      — 네 가지 일을 «실제로» 하는지
//      읽기  `config_resolve_view` 의 둘   — 서버 문장을 먼저 쓰고, 못 말하는 상태면 상수로
//      이음매 `/admin/` URL 이 «전부» 그 전송을 지나는지 (텍스트가 주어인 단언)
//
// ⚠️ `main.js` 는 import 하지 않습니다 — 모듈 최상단에서 `init()` 을 부르고 ag-grid 의 CSS 를
//    끌어옵니다. 그래서 그쪽 절반은 «이음매»로 잽니다: 그 페이지가 전송을 «지나간다»는 것을
//    호출로 확인하고, 문장 자체는 그 전송·분류기의 동작으로 확인합니다.

import path from 'node:path';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(HERE, '..', 'src');
const TOKEN = path.join(SRC, 'admin_token.js');
const VIEW = path.join(SRC, 'config_resolve_view.js');

let pass = 0, fail = 0, quiet = false;
const failedNames = [];
function ok(cond, name, saw) {
  if (cond) { pass++; if (!quiet) console.log(`  OK   ${name}`); }
  else {
    fail++; failedNames.push(name);
    if (!quiet) console.log(`  BAD  ${name}${saw === undefined ? '' : `  -- ${JSON.stringify(saw)}`}`);
  }
  return !!cond;
}

// ── 세상 ──────────────────────────────────────────────────────────────────────────────
let stored = '';
globalThis.localStorage = {
  getItem: () => stored,
  setItem(_k, v) { stored = String(v); },
  removeItem() { stored = ''; },
};

/** 서버 «하나»의 답. 헤더는 진짜 `Headers` 처럼 대소문자를 안 가립니다. */
const answer = ({ status = 200, body = null, challenge = false, server = '' } = {}) => ({
  status,
  ok: status >= 200 && status < 300,
  headers: {
    get(name) {
      const k = String(name).toLowerCase();
      if (k === 'www-authenticate') return challenge ? 'X-Admin-Token realm="admin"' : '';
      if (k === 'server') return server;
      return '';
    },
  },
  json: async () => body,
  clone() { return this; },
});

/** 요청을 기록하는 fetch. `plan` 이 호출 순서대로 답을 냅니다. */
function wiretap(plan) {
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init: init || {} });
    const next = plan[Math.min(calls.length - 1, plan.length - 1)];
    return typeof next === 'function' ? next(calls.length) : next;
  };
  return calls;
}
const headerOf = (call) => (call && call.init && call.init.headers
  && call.init.headers['X-Admin-Token']) || '';

// ── ① 전송 ────────────────────────────────────────────────────────────────────────────
async function transportSuite(mod) {
  const { adminFetch, bumpTokenGeneration } = mod;

  stored = 'T0K3N';
  let calls = wiretap([answer({ status: 200 })]);
  await adminFetch('/admin/x');
  ok(headerOf(calls[0]) === 'T0K3N', 'T1 토큰을 «헤더로» 붙인다', headerOf(calls[0]));

  stored = '';
  calls = wiretap([answer({ status: 200 })]);
  await adminFetch('/admin/x');
  ok(!headerOf(calls[0]), 'T2 토큰이 없으면 «지어내지» 않는다', headerOf(calls[0]));

  // 503 = 서버에 토큰이 «설정되지 않아» 이 라우트가 닫혀 있음. 본문이 변수 이름을 말합니다.
  stored = 'T0K3N';
  calls = wiretap([answer({ status: 503, body: { detail: 'ASSY_ADMIN_TOKEN 미설정' } })]);
  const said = [];
  let asked = 0;
  await adminFetch('/admin/x', null,
                   { onServiceUnavailable: (d) => said.push(d), askForToken: () => { asked += 1; return ''; } });
  ok(said.length === 1 && said[0] === 'ASSY_ADMIN_TOKEN 미설정',
     'T3 503 이면 «서버 본문»을 한 번 세운다', said);
  ok(asked === 0, 'T4 503 에는 토큰을 «묻지 않는다» — 토큰 문제가 아니다', asked);
  ok(calls.length === 1, 'T5 503 에는 재시도하지 않는다', calls.length);

  // 🔴 그리드 페이지의 모양: 세울 자리를 «안 넘깁니다». 그때 같은 문장이 두 번 뜨지 않습니다.
  calls = wiretap([answer({ status: 503, body: { detail: '같은 문장' } })]);
  let threw = false;
  try { await adminFetch('/admin/x'); } catch (e) { threw = true; }
  ok(!threw, 'T6 세울 자리를 «안 넘겨도» 던지지 않는다 — 그 줄이 문장을 들고 있다');

  // 게이트 거절 = 401/403 «그리고» 서버가 자기 것이라 표시한 것.
  calls = wiretap([answer({ status: 401, challenge: true }), answer({ status: 200 })]);
  asked = 0;
  await adminFetch('/admin/x', null, { askForToken: () => { asked += 1; return 'NEW'; } });
  ok(asked === 1 && calls.length === 2, 'T7 게이트가 거절하면 «한 번» 묻고 «한 번» 다시 보낸다',
     [asked, calls.length]);
  ok(headerOf(calls[1]) === 'T0K3N' || headerOf(calls[1]) === 'NEW',
     'T8 재시도는 «저장된» 토큰으로 간다', headerOf(calls[1]));

  // ⚠️ 프록시가 자기 `Basic realm=...` 으로 401 을 내는 경우. 그건 우리 토큰 얘기가 아닙니다.
  calls = wiretap([answer({ status: 401, challenge: false })]);
  asked = 0;
  await adminFetch('/admin/x', null, { askForToken: () => { asked += 1; return 'NEW'; } });
  ok(asked === 0 && calls.length === 1,
     'T9 게이트가 «표시하지 않은» 401 에는 묻지 않는다 — 멀쩡한 토큰을 덮어쓰지 않는다',
     [asked, calls.length]);

  // 날아가는 중에 누가 토큰을 바꿨으면, 그 응답은 «낡은 증거»입니다.
  calls = wiretap([(n) => { if (n === 1) bumpTokenGeneration(); return answer({ status: 401, challenge: true }); },
                   answer({ status: 200 })]);
  asked = 0;
  await adminFetch('/admin/x', null, { askForToken: () => { asked += 1; return 'NEW'; } });
  ok(asked === 0 && calls.length === 2,
     'T10 날아가는 중 토큰이 바뀌었으면 «조용히» 다시 보낸다 — 멀쩡한 토큰을 탓하지 않는다',
     [asked, calls.length]);

  // 묻는 방법을 «안 넘기면» 묻지 않습니다 — 그리드 페이지에는 모달이 없습니다.
  calls = wiretap([answer({ status: 401, challenge: true })]);
  const res = await adminFetch('/admin/x');
  ok(calls.length === 1 && res.status === 401,
     'T11 묻는 방법이 없으면 «응답 그대로» 돌려준다', [calls.length, res.status]);

  // 🔴 그리고 «두 번째 거절»은 부르는 쪽으로 돌아갑니다 — 운영자를 모달에 가두지 않습니다.
  //    이 자리가 없으면 「한 번만 묻는다」가 «아무 변이도 이름 대지 않는» 단언이 됩니다
  //    (첫 판에 그랬고, M5 가 빠져나가서 잡았습니다: 재시도가 200 인 픽스처로는 못 잽니다).
  calls = wiretap([answer({ status: 401, challenge: true })]);
  asked = 0;
  const twice = await adminFetch('/admin/x', null,
                                 { askForToken: () => { asked += 1; return 'NEW'; } });
  ok(asked === 1 && calls.length === 2 && twice.status === 401,
     'T12 다시 보내도 거절이면 «한 번 더 묻지 않고» 부르는 쪽으로 돌아간다',
     [asked, calls.length, twice.status]);
}

// ── ② 읽기 ────────────────────────────────────────────────────────────────────────────
function readerSuite(mod) {
  const { failureFactOf, retroFailureLine, fetchFailureText, fetchFailureLine, CHROME } = mod;
  const line = (a, fallback) => retroFailureLine(a, failureFactOf(a), fallback);

  const gate = failureFactOf(answer({ status: 401, challenge: true }));
  ok(gate.gate === true, 'R1 게이트가 표시한 401 은 «게이트»다', gate);
  const proxy = failureFactOf(answer({ status: 401, challenge: false }));
  ok(proxy.gate === false,
     'R2 프록시의 401 은 게이트가 «아니다» — 규칙을 다시 유도하지 않고 토큰 파일 것을 부른다', proxy);
  ok(failureFactOf(answer({ status: 500, server: 'squid/5.7' })).server === 'squid/5.7',
     'R3 누가 답했는지가 «증거»로 실린다');
  return Promise.all([
    line(answer({ status: 400, body: { detail: '규칙 이름이 없습니다' } }), 'FALLBACK')
      .then((t) => ok(t.includes('규칙 이름이 없습니다'),
                      'R4 400 이면 «서버 문장»이 먼저다 — 뭉개면 운영자를 로그로 보낸다', t)),
    // 🔴 R5 는 「줄에 404 가 없다」를 쟀다. 그것은 «대리»였고, 지키던 «성질»은 「문장을 숫자로
    //    짓지 않는다」다. 지시 `6b2531fc8` 이 「코드는 남기되 그것만 두지 마십시오」라 했으므로
    //    성질로 다시 겨눈다 — 문장은 상수 «그대로»이고, 코드는 그 «옆»(R5b)에 선다.
    Promise.resolve(fetchFailureText(failureFactOf(answer({ status: 404 })), 'FALLBACK'))
      .then((t) => ok(t === CHROME.FETCH_OLD_SERVER,
                      'R5 서버가 자기에 대해 못 말하는 상태면 문장이 «클라 상수 그대로»다', t)),
    line(answer({ status: 404 }), 'FALLBACK')
      .then((t) => ok(t.startsWith(CHROME.FETCH_OLD_SERVER) && t.includes('HTTP 404'),
                      'R5b 코드는 문장 «옆»에 남는다 — 코드만도 아니고 코드 없이도 아니다', t)),
    line(answer({ status: 500, server: 'squid/5.7' }), CHROME.FETCH_FAILED)
      .then((t) => ok(t.includes('squid/5.7'), 'R6 증거가 그 줄에 같이 선다', t)),
    // ㉠ 사유 + 다음 행동 + 코드. ㉢ 401 이 아닌 실패는 «다른 문장»이다.
    line(answer({ status: 401, challenge: true }), 'FALLBACK')
      .then((t) => ok(t.startsWith(CHROME.FETCH_UNAUTHORIZED) && t.includes('HTTP 401')
                      && CHROME.FETCH_UNAUTHORIZED.includes('·'),
                      'R7 게이트의 401 은 «사유»와 «다음 행동»과 코드를 한 줄에 낸다', t)),
    // 응답이 «아예 없는» 갈래는 부르는 쪽이 `fetchFailureLine(null, …)` 로 든다 — 읽을 본문이
    // 없으므로 `retroFailureLine` 의 길이 아니다 (admin.js 의 catch 가 그 모양이다).
    Promise.all([line(answer({ status: 401, challenge: true }), 'FALLBACK'),
                 line(answer({ status: 500 }), 'FALLBACK'),
                 Promise.resolve(fetchFailureLine(null, 'FALLBACK'))])
      .then(([gateLine, brokeLine, goneLine]) => {
        ok(gateLine !== brokeLine && brokeLine !== goneLine && gateLine !== goneLine,
           'R8 401 · 500 · 무응답이 «서로 다른» 문장이다 — 하나로 뭉치지 않는다',
           [gateLine, brokeLine, goneLine]);
        ok(!goneLine.includes('HTTP'),
           'R9 답한 것이 «없으면» 코드도 없다 — 없는 값을 지어내지 않는다', goneLine);
      }),
  ]);
}

// ── ③ 이음매 — 「/admin 은 «전부» 그 전송을 지난다」 ───────────────────────────────────
// 🔴 이 단언의 주어는 «텍스트»입니다. `admin.js:91` 이 이 규칙을 이미 «산문»으로 적어
//    두었습니다 — 「grep 이 아무것도 안 돌려줘야 한다, 아니면 그 자리는 인증 없이 나간다」.
//    산문은 아무것도 막지 않습니다. 같은 문장을 «게이트»로 올립니다.
const files = [];
const collect = (dir) => {
  for (const name of readdirSync(dir)) {
    const p = path.join(dir, name);
    if (statSync(p).isDirectory()) collect(p);
    else if (name.endsWith('.js')) files.push(p);
  }
};
collect(SRC);
// 🔴 주석은 «줄 단위»로 버린다. 종전에는 `/* … */` 를 통째로 지웠고, 문자열 안의 `/*` 하나가
//    «다음 `*/` 까지»를 먹었다 — S5 를 달자마자 그것이 잡혔다: 변이가 심은 줄이 실재하는데
//    계기가 0 을 냈다. 실측: 이 필터로 바꾸니 `adminFetch(` 호출이 58 -> 61 로 늘었다(셋이
//    안 보이고 있었다). 줄 사이에 상태를 안 들고 가면 그 구멍이 «없다».
const live = (text) => text.split('\n')
  .filter((l) => { const t = l.trim(); return !(t.startsWith('//') || t.startsWith('*') || t.startsWith('/*')); })
  .join('\n');

function seamSuite(overrides = {}) {
  let adminFetchCalls = 0;
  const bare = [];
  for (const file of files) {
    const rel = path.relative(SRC, file).split(path.sep).join('/');
    const raw = Object.prototype.hasOwnProperty.call(overrides, rel)
      ? overrides[rel] : readFileSync(file, 'utf8');
    const text = live(raw);
    adminFetchCalls += (text.match(/\badminFetch\(/g) || []).length;
    // 전송 «자신»은 맨 fetch 를 씁니다 — 그게 그 파일의 일입니다.
    if (rel === 'admin_token.js') continue;
    for (const line of text.split('\n')) {
      if (!line.includes('/admin/')) continue;
      if (/[^A-Za-z0-9_.]fetch\s*\(/.test(line)) bare.push(`${rel}: ${line.trim().slice(0, 70)}`);
    }
  }
  ok(bare.length === 0,
     `S1 «맨 fetch» 로 /admin/ 을 부르는 자리가 하나도 없다 (본 수 ${bare.length})`, bare);
  ok(adminFetchCalls >= 30,
     `S2 그 성질의 모집단이 실재한다 — adminFetch 호출 ${adminFetchCalls}`, adminFetchCalls);

  // 🔴 그리고 «읽는 쪽»도 하나. 이름이 두 파일에서 «정의»되면 그게 둘째 철자입니다.
  const defs = { failureFactOf: [], retroFailureLine: [] };
  for (const file of files) {
    const rel = path.relative(SRC, file).split(path.sep).join('/');
    const raw = Object.prototype.hasOwnProperty.call(overrides, rel)
      ? overrides[rel] : readFileSync(file, 'utf8');
    const text = live(raw);
    for (const name of Object.keys(defs)) {
      if (new RegExp(`function\\s+${name}\\s*\\(`).test(text)) defs[name].push(rel);
    }
  }
  ok(defs.failureFactOf.length === 1, `S3 \`failureFactOf\` 의 정의가 «하나»다`, defs.failureFactOf);
  ok(defs.retroFailureLine.length === 1, `S4 \`retroFailureLine\` 의 정의가 «하나»다`,
     defs.retroFailureLine);

  // 🔴 ㉡ 「같은 상황에 화면들이 «같은 문장»을 낸다」. 정의가 하나여도 «부르지 않으면» 갈라진다 —
  //    어드민 화면은 자리 넷에서 404·!ok·네트워크를 «손으로» 적고 있었고, 운영자가 실제로 누르는
  //    동기화 토스트는 응답을 던져 버려서 아무것도 못 말했다.
  //    ⚠️ 이 단언의 주어는 «텍스트»이고 범위는 «어드민 화면 한 파일»이다. 세 화면을 «띄워서»
  //       잰 것이 아니다 — `admin.js` 는 node 가 import 할 수 없다(부팅이 DOM 을 든다).
  const spoken = [];
  let seatCalls = 0;
  let reasonLines = 0;
  const seat = /\b(fetchFailureLine|retroFailureLine)\(/;
  for (const file of files) {
    const rel = path.relative(SRC, file).split(path.sep).join('/');
    const raw = Object.prototype.hasOwnProperty.call(overrides, rel)
      ? overrides[rel] : readFileSync(file, 'utf8');
    const text = live(raw);
    // 🔴 세는 범위는 S5 가 «보는 범위»와 같아야 한다. 전체 파일에서 세면 main.js 의 호출이
    //    어드민 화면의 호출을 «대신» 서 준다 — 어드민이 좌석을 다 버려도 이 칸이 안 운다.
    if (rel !== 'admin.js') continue;
    seatCalls += (text.match(new RegExp(seat.source, 'g')) || []).length;
    for (const one of text.split('\n')) {
      // ㉠ 못 읽은 «이유»를 나르는 칸. 물음은 「이 문장의 «저자»가 누구인가」다 —
      //    좌석이거나(응답이 못 왔다) 서버이거나(200 본문이 error 를 말했다). 둘 다 아니면
      //    화면이 자기 문장을 지은 것이고, 그 자리가 둘째 철자다.
      //    ⚠️ 「서버가 지었다」는 «대리»로 잰다: 상태 코드가 «아닌» 값을 그 줄에 싣고 있나.
      if (/\bunavailable\s*[:=]/.test(one)) {
        reasonLines += 1;
        const byServer = /\$\{(?!res\.status)[A-Za-z_]/.test(one);
        if (!seat.test(one) && !byServer) spoken.push(one.trim().slice(0, 74));
        continue;
      }
      // ㉡ 토스트·실패 칸이 «상태 코드로» 문장을 짓는 자리.
      if (!/showToast|failed:/.test(one)) continue;
      reasonLines += 1;
      if (/HTTP \$\{|\$\{res\.status\}/.test(one)) spoken.push(one.trim().slice(0, 74));
    }
  }
  ok(spoken.length === 0,
     `S5 어드민 화면이 못 읽은 이유를 «자기 문장»으로 짓는 자리가 없다 (본 수 ${spoken.length})`,
     spoken);
  ok(reasonLines > 0 && seatCalls >= 6,
     `S6 그 성질의 모집단이 실재한다 — 어드민의 이유 줄 ${reasonLines} · 어드민의 좌석 호출 ${seatCalls}`,
     [reasonLines, seatCalls]);
}

// ── 채점 ──────────────────────────────────────────────────────────────────────────────
const load = (file, tag, mutate) => loadWithProbe(file, { tag, mutate });

async function suite(token, view, seamOverrides) {
  const before = { pass, fail };
  await transportSuite(token.module);
  await readerSuite(view.module);
  seamSuite(seamOverrides || {});
  return { pass: pass - before.pass, fail: fail - before.fail };
}

const TOKEN_DEFECTS = [
  ['M1 전송이 토큰을 «안 붙인다» -> T1',
   (s) => s.replace('  if (!token) return init;', '  return init;')],
  ['M2 503 에도 토큰을 «묻는다» -> T4/T5',
   (s) => s.replace('    return res;\n  }\n\n  if (!isGateRejection(res)) return res;',
                    '  }\n\n  if (!isGateRejection(res) && res.status !== 503) return res;')],
  ['M3 프록시의 401 도 게이트로 읽는다 -> T9',
   (s) => s.replace('  if (res.status !== 401 && res.status !== 403) return false;\n'
                    + '  const challenge = res.headers && res.headers.get\n'
                    + "    ? (res.headers.get('WWW-Authenticate') || '') : '';\n"
                    + '  return challenge.toLowerCase().includes(ADMIN_TOKEN_HEADER.toLowerCase());',
                    '  return res.status === 401 || res.status === 403;')],
  ['M4 날아가는 중 토큰 교체를 «안 본다» -> T10',
   (s) => s.replace('  if (generation !== generationAtSend) {', '  if (false) {')],
  ['M5 게이트 거절에 «두 번» 묻는다 -> T12',
   (s) => s.replace('  if (token) res = await fetch(url, withAdminToken(init));\n  return res;',
                    '  if (token) res = await fetch(url, withAdminToken(init));\n'
                    + '  if (isGateRejection(res) && deps.askForToken) await deps.askForToken(message);\n'
                    + '  return res;')],
];
const VIEW_DEFECTS = [
  ['M6 읽는 쪽이 «서버 문장»을 버린다 -> R4',
   (s) => s.replace("    if (body && typeof body.detail === 'string') detail = body.detail;", '')],
  ['M7 읽는 쪽이 게이트 규칙을 «다시 유도»한다 -> R2',
   (s) => s.replace('    gate: isGateRejection(res),',
                    '    gate: res.status === 401 || res.status === 403,')],
  ['M8 증거를 안 싣는다 -> R3/R6',
   (s) => s.replace("    server: (res.headers && res.headers.get ? res.headers.get('Server') : '') || '',",
                    "    server: '',")],
  ['M11 문장을 «상태 코드로» 짓는다 -> R5',
   (s) => s.replace('  const text = fetchFailureText(failure, fallback);',
                    '  const text = failure && failure.status\n'
                    + "    ? 'HTTP ' + failure.status : fetchFailureText(failure, fallback);")],
  ['M12 코드를 «안» 싣는다 -> R5b/R7',
   (s) => s.replace('  if (failure && failure.status) facts.push(`HTTP ${failure.status}`);', '')],
];
const SEAM_DEFECTS = [
  ['M9 그리드 페이지가 다시 «맨 fetch» 로 간다 -> S1',
   () => ({ 'main.js': readFileSync(path.join(SRC, 'main.js'), 'utf8')
     .replace('const res = await adminFetch(',
              'const res = await fetch(`${API_BASE}/admin/retroactive/run`); await 0 || await adminFetch(') })],
  ['M10 읽는 쪽이 «둘째 파일»에 다시 정의된다 -> S3',
   () => ({ 'main.js': `function failureFactOf(res) { return res; }\n`
     + readFileSync(path.join(SRC, 'main.js'), 'utf8') })],
  ['M13 어드민 화면이 «자기 문장»을 다시 짓는다 -> S5',
   () => ({ 'admin.js': readFileSync(path.join(SRC, 'admin.js'), 'utf8')
     .replace("opts.unavailable = fetchFailureLine(failureFactOf(res), 'Rule registry read failed');",
              'opts.unavailable = `Rule registry read failed (HTTP ${res.status}).`;') })],
  // 🔴 S6 가 «카나리아인지»를 잰다. 좌석을 버리되 «서버가 준 값»을 싣는 모양으로 바꾸면
  //    S5 는 할 말이 없다 — 그때 우는 자리가 S6 여야 한다. 실측: 이 변이에서 S5 0 · S6 0 호출.
  //    (이 하니스는 admin.js 를 «텍스트로»만 본다. 그래서 이 변이가 문법을 깨도 상관없다.)
  ['M14 어드민 화면이 좌석을 «아예 안 부른다» -> S6',
   () => ({ 'admin.js': readFileSync(path.join(SRC, 'admin.js'), 'utf8')
     .replace(/\b(fetchFailureLine|retroFailureLine)\([^)]*\)/g, '`${API_BASE}`') })],
];
const CONTROLS = [
  ['전송의 주석 한 낱말', TOKEN, (s) => s.replace('두 번째 전송', '세 번째 전송')],
  ['읽는 쪽의 주석 한 낱말', VIEW, (s) => s.replace('같은 판단에 철자가 둘이면', '한 판단에 철자가 둘이면')],
];

console.log('-- refusal_seat (C-122) -------------------------------------------');
let tag = 0;
const nx = () => `r${tag += 1}`;
const tokenBase = await load(TOKEN, nx());
const viewBase = await load(VIEW, nx());
const base = await suite(tokenBase, viewBase);

const caught = [], escaped = [];
let controlsCaught = 0;
console.log('');
console.log('-- defect mutants (each must be caught by the check it names) ------');
for (const [name, mutate] of TOKEN_DEFECTS) {
  quiet = true;
  const delta = await suite(await load(TOKEN, nx(), mutate), viewBase);
  quiet = process.argv[2] === '--quiet';
  (delta.fail > 0 ? caught : escaped).push(name);
  console.log(`  ${delta.fail > 0 ? 'caught ' : 'ESCAPED'} ${name}`);
}
for (const [name, mutate] of VIEW_DEFECTS) {
  quiet = true;
  const delta = await suite(tokenBase, await load(VIEW, nx(), mutate));
  quiet = process.argv[2] === '--quiet';
  (delta.fail > 0 ? caught : escaped).push(name);
  console.log(`  ${delta.fail > 0 ? 'caught ' : 'ESCAPED'} ${name}`);
}
for (const [name, make] of SEAM_DEFECTS) {
  quiet = true;
  const delta = await suite(tokenBase, viewBase, make());
  quiet = process.argv[2] === '--quiet';
  (delta.fail > 0 ? caught : escaped).push(name);
  console.log(`  ${delta.fail > 0 ? 'caught ' : 'ESCAPED'} ${name}`);
}
console.log('');
console.log('-- control mutants (each must ESCAPE) ------------------------------');
for (const [name, file, mutate] of CONTROLS) {
  quiet = true;
  const hit = await load(file, nx(), mutate);
  const delta = await suite(file === TOKEN ? hit : tokenBase, file === VIEW ? hit : viewBase);
  quiet = process.argv[2] === '--quiet';
  if (delta.fail > 0) controlsCaught += 1;
  console.log(`  ${delta.fail > 0 ? 'CAUGHT ' : 'escaped'} ${name}`);
}

const DEFECTS = TOKEN_DEFECTS.length + VIEW_DEFECTS.length + SEAM_DEFECTS.length;
const badScore = escaped.length > 0 || controlsCaught > 0;
console.log('');
console.log(`${base.pass} passed, ${base.fail} failed; ${caught.length}/${DEFECTS} defects caught, `
  + `${escaped.length} escaped; ${CONTROLS.length - controlsCaught}/${CONTROLS.length} controls escaped.`);
console.log(`ASSERTIONS ${base.pass + base.fail} ${base.fail}`);
if (base.fail) console.log('FAILED: ' + failedNames.slice(0, base.fail).join(' | '));
if (base.fail || badScore) process.exitCode = 1;
