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
const RV = join(HERE, '..', 'src', 'retroactive_view.js');
const RL = join(HERE, '..', 'src', 'run_lines.js');
const PC = join(HERE, '..', 'src', 'progress_card.js');

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

async function score(mutate, target = 'ws') {
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
    ...(mutate && target === 'ws' ? { mutate } : {}),
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
     ['R1', 'enrichment_confirm', 25, 5, 20, null], run[0].args);
  // implementer A 10-14: the beat before the pages carries the step and its seconds
  const beat = send({ event: 'file_ingestion_progress', run_id: 'R4', op: 'ledger_rescope', progress: null,
                      processed_rows: null, total_rows: null, status: 'PROCESSING', phase: 'Starting 4 slices', phase_seconds: 12 });
  eq('A12 a beat before the pages hands its step, seconds, rate and time left on',
     ['R4', 'ledger_rescope', null, null, null, { phase: 'Starting 4 slices', phase_seconds: 12, rows_per_second: null, seconds_left: null }], beat[0].args);

  // 🔴 총계를 «모르는» 것은 0 이 아닙니다 — 그대로 넘어가야 카드가 「0 중 5」를 안 말합니다.
  const unknown = send({ event: 'file_ingestion_progress', run_id: 'R2', op: 'backfill',
                         progress: null, processed_rows: 5, total_rows: null, status: 'PROCESSING' });
  eq('A5 모르는 총계는 null 그대로, 0 으로 접히지 않는다',
     ['R2', 'backfill', null, 5, null, null], unknown[0].args);

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

  // ══ the step before the pages - one seat for the card and the queue line ═════════════
  const { module: rv } = await loadWithProbe(RV, { stubs: {}, tag: 'retrophase', ...(mutate && target === 'rv' ? { mutate } : {}) });
  eq('A13 before the pages: the step and its seconds', 'Starting 4 slices · 12 s', rv.runProgressWords({ phase: 'Starting 4 slices', phaseSeconds: 12, processed: null }));
  eq('A14 ...the step alone when the server sends no seconds', 'Counting rows', rv.runProgressWords({ phase: 'Counting rows', phaseSeconds: null, processed: 0 }));
  eq('A15 once rows are processed the counts say it', '', rv.runProgressWords({ phase: 'Writing', phaseSeconds: 3, processed: 1000 }));
  const line = rv.buildRunsView({ runs: [{ run_id: 'R4', op: 'ledger_rescope', state: 'running', processed_rows: null, total_rows: null,
    phase: 'Starting 4 slices', phase_seconds: 12, queued_at: '2026-10-14T01:00:00Z', started_at: '2026-10-14T01:00:00Z' }], state_names: {} },
    Date.parse('2026-10-14T01:00:30Z'), {}, {}).runs[0];
  eq('A16 the queue line draws the same words', 'Starting 4 slices · 12 s', line && line.progress && line.progress.text);
  const paged = rv.buildRunsView({ runs: [{ run_id: 'R5', op: 'ledger_rescope', state: 'running', processed_rows: 500, total_rows: 2000,
    phase: 'Writing', phase_seconds: 40, queued_at: '2026-10-14T01:00:00Z', started_at: '2026-10-14T01:00:00Z' }], state_names: {} },
    Date.parse('2026-10-14T01:01:00Z'), {}, {}).runs[0];
  eq('A17 ...and the counts once pages come, as today', '500 / 2,000', paged && paged.progress && paged.progress.text);

  // ══ the server's rate and time left once pages come (implementer A 10-14) ═══════════
  eq('A18 pages with the server\'s rate and time left', '500 / 2,000 · 12.5 rows/s · 2 min left',
     rv.runProgressWords({ processed: 500, total: 2000, rowsPerSecond: 12.5, secondsLeft: 120 }));
  eq('A19 ...a total not known: no time left, the counts with a dash', '500 / — · 12.5 rows/s',
     rv.runProgressWords({ processed: 500, total: null, rowsPerSecond: 12.5, secondsLeft: null }));
  eq('A20 ...and neither sent: nothing of its own, the seats say their counts', '', rv.runProgressWords({ processed: 500, total: 2000, rowsPerSecond: null, secondsLeft: null }));
  const rated = rv.buildRunsView({ runs: [{ run_id: 'R6', op: 'ledger_rescope', state: 'running', processed_rows: 500, total_rows: 2000,
    phase: 'Page 3: insert atoms', phase_seconds: 4, rows_per_second: 12.5, seconds_left: 7300, queued_at: '2026-10-14T01:00:00Z', started_at: '2026-10-14T01:00:00Z' }],
    state_names: {} }, Date.parse('2026-10-14T01:01:00Z'), {}, {}).runs[0];
  const { module: rl } = await loadWithProbe(RL, { stubs: {}, tag: 'retrorl', ...(mutate && target === 'rl' ? { mutate } : {}) });
  const lineView = rl.runLineView(rated);
  eq('A21 the queue line says the words and keeps its bar', ['500 / 2,000 · 12.5 rows/s · 2.0 h left', 'known', 25],
     [lineView.number, lineView.bar, lineView.percent]);

  // ══ the card keeps the beat's line through a page's event (it carries no beat) ══════
  const cards = Object.create(null);
  const cardEl = () => { const el = { style: {}, dataset: {}, children: [], classList: { _s: new Set(), add(c) { this._s.add(c); }, contains(c) { return this._s.has(c); } },
    _stats: { textContent: '' }, appendChild(c) { this.children.push(c); return c; }, remove() {},
    set id(v) { this._id = v; cards[v] = this; }, get id() { return this._id; },
    set innerHTML(v) { this._html = v; this._stats = { textContent: '' }; }, get innerHTML() { return this._html; },
    querySelector(sel) { return sel === '.progress-stats' ? this._stats : null; } }; return el; };
  const saved = globalThis.document;
  globalThis.document = { getElementById: (id) => cards[id] || null, createElement: cardEl, body: { appendChild() {} } };
  try {
    const { module: pc } = await loadWithProbe(PC, { stubs: {}, tag: 'retropc', ...(mutate && target === 'pc' ? { mutate } : {}) });
    pc.showProgressCard({ key: 'k1', title: 'T', processed: 500, total: 2000, stats: '500 / 2,000 · 12.5 rows/s · 2 min left' });
    pc.showProgressCard({ key: 'k1', title: 'T', processed: 600, total: 2000, keepStats: true });
    eq('A22 a page\'s event keeps the beat\'s line until the next beat', '500 / 2,000 · 12.5 rows/s · 2 min left', cards['progress-k1']._stats.textContent);
    pc.showProgressCard({ key: 'k2', title: 'T', processed: 600, total: 2000 });
    eq('A23 ...and a card never given a line draws its counts (no line of its own)', '', cards['progress-k2']._stats.textContent);
  } finally { globalThis.document = saved; }

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
   s => s.replace('          msg.processed_rows, msg.total_rows, beatOf(msg));',
                  '          msg.processed_rows, msg.total_rows || 0, beatOf(msg));')],
  ['M6 the beat\'s step is not handed on',
   s => s.replace('          msg.processed_rows, msg.total_rows, beatOf(msg));',
                  '          msg.processed_rows, msg.total_rows);')],
  ['M10 the rate dropped',
   s => s.replace("`${r.rowsPerSecond.toLocaleString()} rows/s` : ''", "'' : ''"), 'rv'],
  ['M11 the time left dropped',
   s => s.replace("`${leftClock(r.secondsLeft)} left` : ''", "'' : ''"), 'rv'],
  ['M12 the hours said as minutes',
   s => s.replace("`${(s / 3600).toFixed(1)} h`", "`${Math.round(s / 60)} min`"), 'rv'],
  ['M13 the queue line says its percent over the words',
   s => s.replace('    number: bar && !progress.words ?', '    number: bar ?'), 'rl'],
  ['M14 a page\'s event wipes the beat\'s line',
   s => s.replace(": decl.keepStats ? card.dataset.stats || '' : '';", ": '';"), 'pc'],
  ['M7 the step drawn over the counts',
   s => s.replace('  if (Number.isFinite(r.processed) && r.processed > 0) {', '  if (false) {'), 'rv'],
  ['M8 the seconds dropped',
   s => s.replace('`${phase} · ${Math.round(r.phaseSeconds)} s`', 'phase'), 'rv'],
  ['M9 the queue line asks nothing of the step',
   s => s.replace("  if (words) {", "  if (false) {"), 'rv'],
  ['M5 the ingestion branch starts taking the retroactive subject',
   s => s.replace('      msg.table_name,\n      msg.filename,', '      msg.run_id,\n      msg.op,')],
];

if (process.argv.includes('--mutate')) {
  console.log('\n── MUTATIONS (each must turn the harness RED) ──');
  let caught = 0; const green = [];
  for (const [name, apply, target] of MUTATIONS) {
    let r;
    try { r = await score(apply, target || 'ws'); }
    catch (e) { console.log(`  ~ ${name} -> harness THREW (${e && e.message})`); caught++; continue; }
    if (r.failures.length === 0) { console.log(`  ✗ ${name} -> STILL GREEN`); green.push(name); continue; }
    caught++;
    console.log(`  ✓ ${name} -> ${r.failures.length} failure(s): ${r.failures.sort().join(' ')}`);
  }
  console.log(`\nmutations: ${caught}/${MUTATIONS.length} caught (${MUTATIONS.length} declared)`);
  if (green.length) { console.log(`  ✗ undetected: ${green.join(' | ')}`); process.exit(1); }
}

process.exit(base.failures.length === 0 ? 0 : 1);
