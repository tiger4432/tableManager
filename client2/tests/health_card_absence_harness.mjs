// health_card_absence — AN UNREAD VALUE IS NOT A ZERO, ON THE CARD TOO.
//
// The Auto Update TAB was taught to tell 「못 읽었다」 from 「없다」: it runs `errorText()` on the
// status body, `absentPath()` on it, and refuses to draw the linked-failure table when either
// input is missing. The health CARD recomputed both of those numbers from the same two sources
// and asked none of those questions — so a repair that landed in one site did not land in the
// other, and the card kept saying 「수집기 없음」 for a status file that had vanished and
// 「최근 실행 …」 for a linkage it had never checked.
//
// ═══ 2026-09-17 (C-117 ㉱). 이 파일은 «잘라쓰기»였습니다. 이제 아닙니다 ═══════════════
//
// 🔴 전 판은 `admin.js` 를 텍스트로 읽어 `indexOf` 로 `refreshFileAndAutoHealth` 의 «본문을
//    잘라» 내고, 그 조각에 정규식을 먹였습니다(`/errorText\(/` 가 있나). CLAUDE.md 가 절대
//    금지로 박아 둔 그 모양입니다 — 재는 것이 «동작»이 아니라 «글자 모양»이라, 같은 판단을
//    다른 낱말로 적으면 옳은 코드가 빨개지고, 낱말만 남기고 판단을 지우면 «틀린 코드가
//    초록»입니다. 후자가 이 파일의 실제 위험이었습니다: `errorText(` 를 부르기만 하고
//    그 답으로 «아무것도 안 해도» 전 판의 A1 은 통과합니다.
//
// 🔴 그리고 그 판의 머리글은 「`admin.js` 는 import 할 수 없다 — CSS 를 끌고 모듈 최상단에서
//    document 를 만진다」로 그 선택을 정당화했는데, **그 문장은 오늘 거짓입니다.**
//    `probe_hooks.mjs` 가 `.css` 를 빈 모듈로 풀어 준 뒤(C-95) `chain_rule_user_path_harness`
//    가 이 파일을 «통째로» import 하고 있었고, 저는 C-121 에서 또 한 번 그렇게 했습니다.
//    낡은 문장이 금지를 «정당화»하고 있었습니다.
//
// 🔴 그래서 이제 주어는 «그 함수 자체»입니다. 서버 답을 먹이고, 카드가 «무엇이라 적는지»를
//    읽습니다. 잘라낸 양은 «0» 이고, 재는 것은 글자가 아니라 화면입니다.
// ⚠️ 판별식이 바뀐 만큼 «못 잡던 것을 잡습니다»: 아래 M2 는 `errorText` 를 «부르면서»
//    그 답을 버리는 변이입니다. 전 판은 그것을 초록으로 통과시켰습니다.

import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { makeDoc } from './lib/board_dom.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ADMIN = path.join(HERE, '..', 'src', 'admin.js');

let passed = 0, failed = 0, quiet = false;
const failedNames = [];
function ok(name, cond, saw) {
  if (cond) { passed++; if (!quiet) console.log(`  ok   ${name}`); }
  else {
    failed++; failedNames.push(name);
    if (!quiet) console.log(`  FAIL ${name}${saw === undefined ? '' : `  saw: ${JSON.stringify(saw)}`}`);
  }
}

// ── the world `admin.js` wakes up in ──────────────────────────────────────────────────
const doc = makeDoc('light');
globalThis.document = doc;
globalThis.window = {
  location: { port: '', origin: 'http://box', href: 'http://box/admin.html', hash: '', search: '' },
  addEventListener() {}, removeEventListener() {},
  localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
  setTimeout, clearTimeout, setInterval: () => 0, clearInterval() {},
};
globalThis.localStorage = globalThis.window.localStorage;
if (!globalThis.navigator.clipboard) {
  Object.defineProperty(globalThis.navigator, 'clipboard',
                        { value: { writeText: async () => {} }, configurable: true });
}

/** 세 라우트에 대한 답. 「이 화면이 무엇을 보나」는 여기서만 정해집니다. */
let plan = {};
globalThis.fetch = async (url) => {
  const u = String(url);
  const key = u.includes('/file-ingestion/failed') ? 'failed'
    : u.includes('/file-ingestion/active') ? 'active'
      : u.includes('/auto-update/status') ? 'auto' : 'other';
  const a = plan[key] || { status: 200, body: {} };
  return {
    ok: a.status >= 200 && a.status < 300,
    status: a.status,
    headers: { get: () => '' },
    json: async () => a.body,
    clone() { return this; },
  };
};

/** 카드 여섯 칸을 새로 앉히고, 함수를 돌리고, «화면이 적은 것»을 읽습니다. */
async function draw(refreshFileAndAutoHealth, answers) {
  plan = answers;
  doc.body.children.length = 0;
  const seats = {};
  for (const key of ['file', 'auto']) {
    for (const [id, tag] of [[`health-card-${key}`, 'div'], [`health-${key}-main`, 'span'],
                             [`health-${key}-sub`, 'span']]) {
      const el = doc.createElement(tag);
      el.setAttribute('id', id);
      doc.body.appendChild(el);
      seats[id] = el;
    }
  }
  await refreshFileAndAutoHealth();
  const read = (key) => ({
    status: seats[`health-card-${key}`].dataset.status || '',
    main: seats[`health-${key}-main`].textContent || '',
    sub: seats[`health-${key}-sub`].textContent || '',
  });
  return { file: read('file'), auto: read('auto') };
}

// ── 서버가 실제로 내는 봉투들 ─────────────────────────────────────────────────────────
const OK_FAILED = { status: 200, body: { total: 0, data: [] } };
const REFUSED = { status: 401, body: null };
const NO_ACTIVE = { status: 200, body: { total: 0, data: [] } };
const COLLECTORS = {
  status: 200,
  body: { data: [{ table_name: 'dt_log', last_status: 'SUCCESS', active: true }] },
};
// 봉투 A: 200 인데 «오류를 나릅니다». `data` 는 아예 없습니다.
const AUTO_ERROR = { status: 200, body: { status: 'error', message: '상태 파일을 읽지 못했습니다' } };
// 부재: 「원천 경로가 없다」. 「한 번도 안 돌았다」와 «다른 사실»입니다.
const AUTO_ABSENT = { status: 200, body: { state: 'absent', absent_path: '/box/auto_update.json' } };
// 진짜 0: 선언된 수집기가 «없습니다».
const AUTO_EMPTY = { status: 200, body: { data: [] } };

async function suite(probe) {
  const before = { passed, failed };
  const run = probe.refreshFileAndAutoHealth;
  ok('A0 admin.js 가 import 되고 그 카드의 함수에 닿는다', typeof run === 'function');
  if (typeof run !== 'function') return { passed: passed - before.passed, failed: failed - before.failed };

  // ── A. 봉투가 «오류»를 나르면, 그것은 「없음」이 아니다 ────────────────────────────
  const errored = await draw(run, { failed: OK_FAILED, active: NO_ACTIVE, auto: AUTO_ERROR });
  ok('A1 200 + 오류 봉투면 카드가 「못 읽음」이다', errored.auto.status === 'unread', errored.auto);
  ok('A2 ...그리고 수를 «안 그린다»', errored.auto.main === '—', errored.auto.main);
  ok('A3 ...그리고 «서버 문장»을 그대로 세운다',
     errored.auto.sub.includes('상태 파일을 읽지 못했습니다'), errored.auto.sub);

  // ── B. 「원천 경로가 없다」는 또 «다른» 사실이다 ──────────────────────────────────
  const absent = await draw(run, { failed: OK_FAILED, active: NO_ACTIVE, auto: AUTO_ABSENT });
  ok('B1 부재면 「상태 파일 없음」이다', absent.auto.main === '상태 파일 없음', absent.auto);
  ok('B2 ...그리고 «고칠 자리»(경로)를 같이 적는다',
     absent.auto.sub.includes('/box/auto_update.json'), absent.auto.sub);

  // ── C. 진짜 0 — 「선언된 것이 없다」. 위 둘과 «같은 픽셀이면 안 된다» ──────────────
  const empty = await draw(run, { failed: OK_FAILED, active: NO_ACTIVE, auto: AUTO_EMPTY });
  ok('C1 진짜 0 이면 「수집기 없음」이다', empty.auto.main === '수집기 없음', empty.auto);
  // 🔴 판별식. 셋이 한 그림이면 운영자는 «고칠 자리»를 못 찾습니다.
  const three = [errored.auto.main, absent.auto.main, empty.auto.main];
  ok('C2 「못 읽음」·「파일 없음」·「진짜 0」이 «서로 다른 그림»이다',
     new Set(three).size === 3, three);

  // ── D. 안 물어본 질의는 0 이 아니다 (연계) ────────────────────────────────────────
  const unread = await draw(run, { failed: REFUSED, active: NO_ACTIVE, auto: COLLECTORS });
  ok('D1 실패 로그를 못 읽으면 파일 카드가 「못 읽음」이다', unread.file.status === 'unread',
     unread.file);
  ok('D2 ...그리고 수 대신 「—」', unread.file.main === '—', unread.file.main);
  // 🔴 이것이 이 파일의 이름이 된 결함입니다. 교집합의 «한쪽»이 안 왔는데 0 으로 셌습니다.
  ok('D3 연계를 «미확인»이라 말한다 — 「연계 실패 없음」이 아니다',
     unread.auto.sub.includes('미확인'), unread.auto.sub);
  ok('D4 ...그리고 카드가 초록을 «주장하지 않는다»', unread.auto.status === 'warn',
     unread.auto.status);

  // ── E. 대조군 — 둘 다 읽혔고 아무 문제가 없으면 «초록이어야» 한다 ────────────────
  const good = await draw(run, { failed: OK_FAILED, active: NO_ACTIVE, auto: COLLECTORS });
  ok('E1 전부 읽혔고 실패가 없으면 파일 카드가 초록이다',
     good.file.status === 'ok' && good.file.main === '실패 0건', good.file);
  ok('E2 ...그리고 수집기 카드도 초록이다', good.auto.status === 'ok', good.auto);
  ok('E3 ...그리고 「미확인」을 말하지 «않는다» — 안 그러면 전부 경고인 화면이 만점을 받는다',
     !good.auto.sub.includes('미확인'), good.auto.sub);

  return { passed: passed - before.passed, failed: failed - before.failed };
}

// ── 채점 ──────────────────────────────────────────────────────────────────────────────
const load = (tag, mutate) => loadWithProbe(ADMIN, {
  tag, mutate, expose: ['refreshFileAndAutoHealth'],
});

const DEFECTS = [
  ['M1 오류 봉투를 안 읽는다 -> A1/A2/C2',
   (s) => s.replace('    const autoFailure = errorText(r);', '    const autoFailure = null;')],
  // 🔴 전 판(잘라쓰기)이 «초록으로» 통과시키던 변이입니다: 부르기는 부르고 답을 버립니다.
  ['M2 errorText 를 «부르지만» 그 답으로 아무것도 안 한다 -> A1 (전 판은 못 잡았다)',
   (s) => s.replace('    const autoFailure = errorText(r);\n    if (autoFailure) {',
                    '    const autoFailure = errorText(r);\n    if (autoFailure && false) {')],
  ['M3 부재를 안 읽는다 -> B1/C2',
   (s) => s.replace('    const autoAbsent = absentPath(r);', '    const autoAbsent = null;')],
  ['M4 안 물어본 교집합을 0 으로 센다 -> D3/D4',
   (s) => s.replace('    const linkedRead = failedTotal !== null;',
                    '    const linkedRead = true;')],
  ['M5 못 읽어도 카드가 초록을 유지한다 -> D4',
   (s) => s.replace("    else if (!linkedRead) status = 'warn';",
                    '    else if (!linkedRead) status = status;')],
  ['M6 파일 카드가 못 읽은 것을 0 으로 그린다 -> D1/D2',
   (s) => s.replace('  if (failedTotal === null) {', '  if (false) {')],
];
const CONTROLS = [
  ['주석 한 낱말', (s) => s.replace('못 물어봤다', '안 물어봤다')],
  ['진행 중 건수의 부수 문구', (s) => s.replace('재기동 시 처음부터 재처리', '재기동 시 처음부터 다시')],
];

console.log('-- health_card_absence (C-117 ㉱: sliced -> imported) --------------');
let tag = 0;
const base = await suite((await load(`h${tag += 1}`)).probe);

const caught = [], escaped = [];
let controlsCaught = 0;
console.log('');
console.log('-- defect mutants (each must be caught by the check it names) ------');
for (const [name, mutate] of DEFECTS) {
  quiet = true;
  const delta = await suite((await load(`h${tag += 1}`, mutate)).probe);
  quiet = process.argv[2] === '--quiet';
  (delta.failed > 0 ? caught : escaped).push(name);
  console.log(`  ${delta.failed > 0 ? 'caught ' : 'ESCAPED'} ${name}`);
}
console.log('');
console.log('-- control mutants (each must ESCAPE) ------------------------------');
for (const [name, mutate] of CONTROLS) {
  quiet = true;
  const delta = await suite((await load(`h${tag += 1}`, mutate)).probe);
  quiet = process.argv[2] === '--quiet';
  if (delta.failed > 0) controlsCaught += 1;
  console.log(`  ${delta.failed > 0 ? 'CAUGHT ' : 'escaped'} ${name}`);
}

const badScore = escaped.length > 0 || controlsCaught > 0;
console.log('');
console.log(`${base.passed} passed, ${base.failed} failed; ${caught.length}/${DEFECTS.length} `
  + `defects caught, ${escaped.length} escaped; ${CONTROLS.length - controlsCaught}/`
  + `${CONTROLS.length} controls escaped.`);
console.log(`ASSERTIONS ${base.passed + base.failed} ${base.failed}`);
if (base.failed) console.log('FAILED: ' + failedNames.slice(0, base.failed).join(' | '));
if (base.failed || badScore) process.exitCode = 1;
