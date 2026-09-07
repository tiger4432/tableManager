/**
 * 🔁 S-37 — 하나의 이벤트 이름, «두 주어». 갈래가 옳은 독자를 부르나.
 *
 * 🔴 서버는 소급 진행을 인제션과 «같은 이름»으로 보냅니다(`file_ingestion_progress`). 그래서
 *    이 갈래는 «이미» 소급 이벤트를 받고 있었고, 그것을 인제션으로 읽으면 두 가지가 조용히
 *    틀립니다: dedupe 키가 `ingestionKey(undefined, undefined)` 로 «모든 실행에 대해 같아»
 *    카드가 겹치고, 제목이 파일을 말합니다 — 파일이 없는 실행에 대해서.
 *
 * 이 하니스는 대상을 IMPORT 하고, `./utils.js` 를 «형제 스텁»으로 갈아 끼워 어느 독자가
 * 불렸는지를 «기록»합니다. 잘라쓰기 0.
 *
 * Run:  node client2/tests/retroactive_progress_harness.mjs [--mutate]
 */
import { loadWithProbe } from './lib/probe.mjs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const WS = join(HERE, '..', 'src', 'websocket.js');
const UTILS = join(HERE, '..', 'src', 'utils.js');

let pass = 0;
const failures = [];
const ok = (name, cond, detail = '') => {
  if (cond) { pass += 1; console.log(`  PASS ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name}${detail ? ' — ' + detail : ''}`); }
};
const eq = (name, expected, actual) => ok(name, JSON.stringify(actual) === JSON.stringify(expected),
  `expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);

function installDom() {
  globalThis.window = { location: { port: '', origin: '', protocol: 'http:', host: '', search: '' },
    addEventListener() {}, removeEventListener() {}, devicePixelRatio: 1 };
  globalThis.document = { getElementById: () => null, querySelector: () => null,
    querySelectorAll: () => [], addEventListener() {}, removeEventListener() {},
    createElement: () => ({ style: {}, classList: { add() {}, remove() {} },
                            appendChild() {}, setAttribute() {} }) };
  globalThis.performance = { now: () => 0 };
  globalThis.WebSocket = function () {};
}

async function score(mutate) {
  pass = 0; failures.length = 0;
  installDom();
  const calls = [];
  const rec = (name) => (...args) => calls.push({ name, args });

  const { probe } = await loadWithProbe(WS, {
    expose: ['handleWebSocketMessage'],
    stubs: {
      './utils.js': {
        showIngestionProgress: rec('ingestion'),
        finishIngestionProgress: rec('ingestionDone'),
        showRetroactiveProgress: rec('retro'),
        finishRetroactiveProgress: rec('retroDone'),
        showToast: () => {},
        getLocalTimeString: () => '',
      },
    },
    mutate,
    tag: 'retroprog',
  });

  const send = (msg) => { calls.length = 0; probe.handleWebSocketMessage(msg); return calls; };

  // ══ 인제션 — 오늘과 «한 글자도» 다르지 않아야 합니다 ═════════════════════════════
  const ing = send({ event: 'file_ingestion_progress', table_name: 'dt_log',
                     filename: 'a.csv', progress: 40, processed_rows: 4, total_rows: 10 });
  eq('A1 인제션 이벤트는 인제션 독자로', ['ingestion'], ing.map(c => c.name));
  eq('A2 ...그리고 인자 다섯이 그대로', ['dt_log', 'a.csv', 40, 4, 10], ing[0].args);

  // ══ 소급 — «다른 주어», 같은 이름 ═══════════════════════════════════════════════
  const run = send({ event: 'file_ingestion_progress', run_id: 'R1', op: 'enrichment_confirm',
                     progress: 25, processed_rows: 5, total_rows: 20, status: 'PROCESSING' });
  eq('A3 소급 이벤트는 소급 독자로', ['retro'], run.map(c => c.name));
  eq('A4 ...run_id 와 op 를 주어로, 서버 값 그대로',
     ['R1', 'enrichment_confirm', 25, 5, 20], run[0].args);

  // 🔴 총계를 «모르는» 것은 0 이 아닙니다 — 그대로 넘어가야 카드가 「0 중 5」를 안 말합니다.
  const unknown = send({ event: 'file_ingestion_progress', run_id: 'R2', op: 'backfill',
                         progress: null, processed_rows: 5, total_rows: null, status: 'PROCESSING' });
  eq('A5 모르는 총계는 null 그대로, 0 으로 접히지 않는다',
     ['R2', 'backfill', null, 5, null], unknown[0].args);

  // ══ 끝 — 이 이벤트 «하나»로 들어옵니다. 끝난 이유는 status 가 말합니다 ══════════
  const done = send({ event: 'file_ingestion_progress', run_id: 'R1', op: 'x',
                      progress: 100, processed_rows: 20, total_rows: 20, status: 'FINISHED' });
  eq('A6 FINISHED 는 진행이 아니라 «끝»으로', ['retroDone'], done.map(c => c.name));
  eq('A7 ...그리고 서버의 낱말을 그대로 넘긴다', ['R1', 'FINISHED'], done[0].args);
  const cancelled = send({ event: 'file_ingestion_progress', run_id: 'R3', op: 'x',
                           status: 'CANCELLED' });
  eq('A8 취소도 «끝»이고, 완료와 «다른 낱말»로 넘어간다', ['R3', 'CANCELLED'], cancelled[0].args);

  // ⚠️ 갈래가 «run_id 의 있음»으로 갈립니다 — 그 칸이 정확히 한쪽에만 있기 때문입니다.
  const noRun = send({ event: 'file_ingestion_progress', table_name: 't', filename: 'f',
                       status: 'FINISHED' });
  eq('A9 run_id 가 없으면 status 가 무엇이든 인제션 길이다', ['ingestion'], noRun.map(c => c.name));

  // ══ 카드 키 — 실행 하나에 카드 하나 ═════════════════════════════════════════════
  const { probe: u } = await loadWithProbe(UTILS, {
    expose: ['retroactiveKey'], stubs: {}, tag: 'retrokey',
  });
  ok('A10 실행마다 다른 카드', u.retroactiveKey('R1') !== u.retroactiveKey('R2'));
  // 🔴 THE DEFECT THIS FORK EXISTS TO PREVENT: one key for every run.
  ok('A11 ...그리고 run_id 가 키에 «실제로» 들어간다', u.retroactiveKey('R1').includes('R1'),
     u.retroactiveKey('R1'));

  return { pass, failures: failures.slice() };
}

const base = await score(undefined);
console.log(`\n${base.failures.length === 0 ? '✓' : '✗'} baseline: ${base.pass} passed, `
  + `${base.failures.length} failed`);
console.log(`ASSERTIONS ${base.pass + base.failures.length} ${base.failures.length}`);

const MUTATIONS = [
  ['M1 the fork is removed, so a run is read as an ingestion',
   s => s.replace('    if (msg.run_id != null) {', '    if (false) {')],
  ['M2 a finished run keeps drawing progress, so its card never closes',
   s => s.replace("      if (msg.status === 'FINISHED' || msg.status === 'CANCELLED') {",
                  '      if (false) {')],
  ['M3 cancellation is folded into completion',
   s => s.replace("      if (msg.status === 'FINISHED' || msg.status === 'CANCELLED') {\n        finishRetroactiveProgress(msg.run_id, msg.status);",
                  "      if (msg.status === 'FINISHED' || msg.status === 'CANCELLED') {\n        finishRetroactiveProgress(msg.run_id, 'FINISHED');")],
  ['M4 an unknown total is sent as zero',
   s => s.replace('          msg.processed_rows, msg.total_rows);',
                  '          msg.processed_rows, msg.total_rows || 0);')],
  ['M5 the ingestion branch starts taking the retroactive subject',
   s => s.replace('      msg.table_name,\n      msg.filename,', '      msg.run_id,\n      msg.op,')],
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
