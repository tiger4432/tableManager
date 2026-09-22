// 「대기열」 부품 — 판정 2026-09-22. 게이트 ③④ 가 여기 산다.
//   ③ 「기다리는 중」과 「재시도 중」이 화면에서 «갈린다»  (둘 다 chain_state=waiting 이다)
//   ④ DELETE 행이 «빈 칸이 아니라 문장»을 낸다
import { makeDoc, walk } from './lib/board_dom.mjs';
import { outboxQueueView, OutboxQueuePanel } from '../src/outbox_queue_panel.js';
import { formatAge } from '../src/chain_queue_panel.js';

let pass = 0; const failures = [];
const eq = (what, got, want) => {
  if (String(got) === String(want)) { pass += 1; console.log(`  PASS ${what}`); }
  else { failures.push(what); console.log(`  FAIL ${what} -- got ${got}, want ${want}`); }
};
const ok = (what, cond, shown) => eq(what, cond ? 'true' : `false (${shown})`, 'true');

const doc = makeDoc('light');
const byClass = (root, cls) => walk(root).filter(
  (n) => String(n.className || '').split(/\s+/).includes(cls));
const mountPanel = (payload, opts) => {
  const mount = doc.createElement('div');
  new OutboxQueuePanel(mount, { doc }).render(payload, opts);
  return mount;
};

// 서버가 «실제로» 내는 모양 (main.py 의 행 조립을 읽고 적음)
const WAITING = { outbox_id: 11, event_type: 'EDIT', table_name: 'dt_log',
                  created_at: '2026-09-22 20:00:00', waiting_seconds: 90, owner: 'chain',
                  chain_state: 'waiting', state_detail: '', broadcast_state: 'pending',
                  rules: [{ name: 'dt_log_to_dt_map', will_fire: true }], note: '' };
const RETRYING = { ...WAITING, outbox_id: 12, chain_state: 'waiting',
                   state_detail: '2회 실패 후 재시도 대기' };
const DELETED = { outbox_id: 13, event_type: 'DELETE', table_name: 'dt_log',
                  created_at: '2026-09-22 20:01:00', waiting_seconds: 30, owner: 'scheduler',
                  chain_state: 'waiting', state_detail: '', broadcast_state: 'not_applicable',
                  rules: [], note: 'DELETE 는 규칙을 깨우지 않습니다 — 트리거는 CREATE·EDIT 뿐입니다.' };
const REPLY = (rows) => ({ generated_at: '2026-09-22 20:02:00', clock: 'server', rows,
                           rules_known: ['dt_log_to_dt_map'],
                           listed: { cap: 200, capped: false, next_cursor: null },
                           population: 'processed_chain=false ∪ (done & undelivered) ∪ failed' });

console.log('\n[게이트 ③] 기다리는 중 vs 재시도 중 — 둘 다 waiting 이다');
{
  const mount = mountPanel(REPLY([WAITING, RETRYING]));
  const details = byClass(mount, 'queue-state-detail').map((n) => n.textContent);
  eq('G3 the retrying row carries a sentence', details.length, 1);
  ok('G3b ...and it is the server\'s, not ours', details[0].includes('재시도'), details[0]);
  // 🔴 이 둘이 «같은 픽셀»이면 운영자는 멈춘 행을 「아직 안 돌았다」로 읽는다.
  const rows = byClass(mount, 'queue-row').map((n) => walk(n).map((c) => c.textContent).join('|'));
  ok('G3c the two rows do not render identically', rows[0] !== rows[1], rows[0]);
}

console.log('\n[게이트 ④] DELETE 행은 빈 칸이 아니라 문장을 낸다');
{
  const mount = mountPanel(REPLY([DELETED]));
  const notes = byClass(mount, 'queue-note').map((n) => n.textContent);
  eq('G4 a row nothing looked at says so', notes.length, 1);
  ok('G4b ...in the server\'s words', notes[0].includes('트리거는'), notes[0] || '(none)');
  eq('G4c ...and draws no rule line', byClass(mount, 'queue-rule').length, 0);
  // 대조군: 규칙이 «있는» 행은 note 줄을 안 만든다
  eq('G4d CONTROL: a row with rules draws no note',
    byClass(mountPanel(REPLY([WAITING])), 'queue-note').length, 0);
}

console.log('\n[판단은 한 좌석] 나이·주인·표·사유');
{
  const view = outboxQueueView(REPLY([WAITING]));
  eq('S1 age comes from the shared seat', view.rows[0].age, formatAge(90));
  eq('S2 an owner the server did not name is 「—」, never 「chain」',
    outboxQueueView(REPLY([{ ...WAITING, owner: null }])).rows[0].owner, '—');
  eq('S3 a placeholder table (server sends null) draws a dash',
    outboxQueueView(REPLY([{ ...WAITING, table_name: null }])).rows[0].table, '—');
  const off = outboxQueueView(REPLY([{ ...WAITING,
    rules: [{ name: 'r', will_fire: false, why_not: 'declaration is switched off' }] }]));
  ok('S4 a rule that will not fire carries the server\'s reason',
    off.rows[0].rules[0].whyNot.includes('switched off'), off.rows[0].rules[0].whyNot);
}

console.log('\n[화면이 «자기 경계»를 말한다]');
{
  const view = outboxQueueView(REPLY([WAITING]));
  ok('P1 the population sentence is carried verbatim',
    view.population.includes('processed_chain=false'), view.population);
  eq('P2 ...and reaches the screen', byClass(mountPanel(REPLY([WAITING])), 'queue-population').length, 1);
  // capped 는 「서버 상한」이지 「이 쪽이 꽉 찼다」가 아니다 (서버가 20:10 에 고친 뜻).
  eq('P3 a full page alone is not 「잘림」', view.capped, 'false');
  eq('P4 ...and 「더 있다」 is next_cursor, not capped',
    outboxQueueView({ ...REPLY([WAITING]), listed: { capped: false, next_cursor: 11 } }).hasMore, 'true');
}

console.log('\n[못 읽었을 때]');
{
  const v = outboxQueueView(null, { failed: '구버전 서버 · 재시작 필요' });
  eq('U1 no payload reads as unread', v.read, 'false');
  ok('U2 ...with the reason, because a reasonless 「모름」 has nowhere to go',
    v.reason.includes('재시작'), v.reason);
  eq('U3 ...and draws no rows', byClass(mountPanel(null, { failed: 'x' }), 'queue-row').length, 0);
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
