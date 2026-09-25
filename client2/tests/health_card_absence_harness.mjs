// health_card_absence — AN UNREAD VALUE IS NOT A ZERO, ON THE OVERVIEW TOO.
//
// The Auto Update TAB was taught to tell 「못 읽었다」 from 「없다」: it runs `errorText()` on the
// status body, `absentPath()` on it, and refuses to draw the linked-failure table when either
// input is missing. The health CARD recomputed both of those numbers from the same two sources
// and asked none of those questions — so a repair that landed in one site did not land in the
// other.
//
// ═══ 2026-09-25 (시안 A · 총괄 5d157581e). 카드가 사라지고 «줄»이 됐습니다 ═══════════════
// 🔴 카드 넷(숨은 띠)과 Overview 카드 넷이 같은 응답을 «두 번» 판정하던 것을 줄마다 순수 함수
//    «하나»로 접었습니다(`overview_status.js`). 이 하니스는 지워지지 않고 «그 함수로» 옮겨 왔습니다 —
//    묻는 것은 그대로입니다: 오류 봉투 · 부재 · 진짜 0 이 «서로 다른 줄»인가, 실패 목록을 못 읽으면
//    파일 줄이 「모름」이고 수집기 줄이 초록을 주장하지 «않는가».
// 🔴 주어는 «그 함수 자체»입니다 — import 해서 서버 답을 먹이고 줄이 «무엇이라 적는지»를 읽습니다.
//    변이는 모듈 «전문»에 가하고 import 합니다(잘라쓰기 0).
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FILE = path.join(HERE, '..', 'src', 'overview_status.js');

let passed = 0, failed = 0, quiet = false;
const failedNames = [];
function ok(name, cond, saw) {
  if (cond) { passed++; if (!quiet) console.log(`  ok   ${name}`); }
  else {
    failed++; failedNames.push(name);
    if (!quiet) console.log(`  FAIL ${name}${saw === undefined ? '' : `  saw: ${JSON.stringify(saw)}`}`);
  }
}

// 서버 답 — HTTP 가 실패하면 페이지는 null 을 넘깁니다 (admin.js fetchOverview 의 jsonOf).
const OK_FAILED = { total: 0, data: [] };
const REFUSED = null;
const NO_ACTIVE = { total: 0, data: [] };
const COLLECTORS = { data: [{ table_name: 'dt_log', last_status: 'SUCCESS', active: true }] };
const AUTO_ERROR = { status: 'error', message: '상태 파일을 읽지 못했습니다' };
const AUTO_ABSENT = { state: 'absent', absent_path: '/box/auto_update.json' };
const AUTO_EMPTY = { data: [] };

const facts = (row) => row.facts.join(' · ');

async function suite(mod) {
  const before = { passed, failed };
  ok('A0 overview_status 가 import 되고 두 줄의 함수에 닿는다',
     typeof mod.fileRow === 'function' && typeof mod.autoRow === 'function');
  if (typeof mod.fileRow !== 'function' || typeof mod.autoRow !== 'function') {
    return { passed: passed - before.passed, failed: failed - before.failed };
  }
  const draw = (answers) => ({
    file: mod.fileRow({ failed: answers.failed, active: answers.active }),
    auto: mod.autoRow({ auto: answers.auto, failed: answers.failed }),
  });

  // ── A. 봉투가 «오류»를 나르면, 그것은 「없음」이 아니다 ────────────────────────────
  const errored = draw({ failed: OK_FAILED, active: NO_ACTIVE, auto: AUTO_ERROR });
  ok('A1 200 + 오류 봉투면 줄이 「모름」이다', errored.auto.tone === 'unknown', errored.auto);
  ok('A2 ...그리고 수를 «안 적는다»', !/\d/.test(facts(errored.auto)), facts(errored.auto));
  ok('A3 ...그리고 «서버 문장»을 그대로 세운다',
     facts(errored.auto).includes('상태 파일을 읽지 못했습니다'), facts(errored.auto));

  // ── B. 「원천 경로가 없다」는 또 «다른» 사실이다 ──────────────────────────────────
  const absent = draw({ failed: OK_FAILED, active: NO_ACTIVE, auto: AUTO_ABSENT });
  ok('B1 부재면 「상태 파일 없음」이다', facts(absent.auto).includes('No status file'), absent.auto);
  ok('B2 ...그리고 «고칠 자리»(경로)를 같이 적는다',
     facts(absent.auto).includes('/box/auto_update.json'), facts(absent.auto));

  // ── C. 진짜 0 — 「선언된 것이 없다」. 위 둘과 «같은 줄이면 안 된다» ──────────────────
  const empty = draw({ failed: OK_FAILED, active: NO_ACTIVE, auto: AUTO_EMPTY });
  ok('C1 진짜 0 이면 「수집기 없음」이다', facts(empty.auto) === 'No collectors', empty.auto);
  const three = [errored.auto, absent.auto, empty.auto].map((r) => `${r.tone}|${facts(r)}`);
  ok('C2 「못 읽음」·「파일 없음」·「진짜 0」이 «서로 다른 줄»이다', new Set(three).size === 3, three);

  // ── D. 실패 목록을 못 읽었다 ────────────────────────────────────────────────────
  const unread = draw({ failed: REFUSED, active: NO_ACTIVE, auto: COLLECTORS });
  ok('D1 실패 로그를 못 읽으면 파일 줄이 「모름」이다', unread.file.tone === 'unknown', unread.file);
  ok('D2 ...그리고 수 대신 「—」', facts(unread.file).includes('failed —'), facts(unread.file));
  ok('D3 연계를 «미확인»이라 말한다 — 「연계 실패 없음」이 아니다',
     facts(unread.auto).includes('unchecked'), facts(unread.auto));
  ok('D4 ...그리고 줄이 초록을 «주장하지 않는다»', unread.auto.tone === 'warn', unread.auto.tone);

  // ── E. 전부 읽혔고 실패가 없다 — 음성 대조 ──────────────────────────────────────
  const good = draw({ failed: OK_FAILED, active: NO_ACTIVE, auto: COLLECTORS });
  ok('E1 전부 읽혔고 실패가 없으면 파일 줄이 초록이다',
     good.file.tone === 'ok' && facts(good.file).includes('failed 0'), good.file);
  ok('E2 ...그리고 수집기 줄도 초록이다', good.auto.tone === 'ok', good.auto);
  ok('E3 ...그리고 「미확인」을 말하지 «않는다» — 안 그러면 전부 경고인 화면이 만점을 받는다',
     !facts(good.auto).includes('unchecked'), facts(good.auto));

  return { passed: passed - before.passed, failed: failed - before.failed };
}

const load = (mutate) => loadWithProbe(FILE, { mutate });

const DEFECTS = [
  ['M1 오류 봉투를 안 읽는다 -> A1/A3/C2',
   (s) => s.replace('  const failure = errorText(auto);', '  const failure = null;')],
  ['M2 errorText 를 «부르지만» 그 답으로 아무것도 안 한다 -> A1',
   (s) => s.replace("  if (failure) return row('auto'", "  if (failure && false) return row('auto'")],
  ['M3 부재를 안 읽는다 -> B1/C2',
   (s) => s.replace('  const absent = absentPath(auto);', '  const absent = null;')],
  ['M4 안 물어본 교집합을 0 으로 센다 -> D3/D4',
   (s) => s.replace('  const linked = logs ? logs.filter((l) => tables.has(l.table_name)).length : null;',
                    '  const linked = logs ? logs.filter((l) => tables.has(l.table_name)).length : 0;')],
  ['M5 못 읽어도 줄이 초록을 유지한다 -> D4',
   (s) => s.replace('(linked === null || linked > 0 || activeCount === 0)', '(linked > 0 || activeCount === 0)')],
  ['M6 파일 줄이 못 읽은 것을 0 으로 적는다 -> D1/D2',
   (s) => s.replace('  const total = failed ? count(failed.total) : null;', '  const total = failed ? count(failed.total) : 0;')],
];
const CONTROLS = [
  ['주석 한 낱말', (s) => s.replace('neither is 「no', 'neither one is 「no')],
  ['낱말 표의 대문자', (s) => s.replace("unknown: 'Unknown'", "unknown: 'UNKNOWN'")],
];

console.log('-- health_card_absence (시안 A: the cards became rows) ---------------');
const base = await suite((await load()).module);

const caught = [], escaped = [];
let controlsCaught = 0;
console.log('');
console.log('-- defect mutants (each must be caught by the check it names) ------');
for (const [name, mutate] of DEFECTS) {
  quiet = true;
  const delta = await suite((await load(mutate)).module);
  quiet = process.argv[2] === '--quiet';
  (delta.failed > 0 ? caught : escaped).push(name);
  console.log(`  ${delta.failed > 0 ? 'caught ' : 'ESCAPED'} ${name}`);
}
console.log('');
console.log('-- control mutants (each must ESCAPE) ------------------------------');
for (const [name, mutate] of CONTROLS) {
  quiet = true;
  const delta = await suite((await load(mutate)).module);
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
