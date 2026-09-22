// 「대기열」 부품 — 판정 2026-09-22. 이 라운드의 게이트가 여기 산다.
//   ① 빈 상태가 «왜»인지 말한다 (「안 읽혔다」와 다른 픽셀)
//   ③ 한 행이 «한 줄» — 칸 여섯, 가로지르는 노드 0
//   ⑤ 감사 탭은 그대로 (CSS `:has()` 라 여기선 못 잰다 — 화면을 열어서 잰다)
// ⚠️ 접기 단언은 이 커밋에서 죽는다. 규칙이 «칸»이 돼서 접을 것이 없다 (소유자: 「컬럼 추가」).
import { makeDoc, walk } from './lib/board_dom.mjs';
import { outboxQueueView, OutboxQueuePanel, summaryText } from '../src/outbox_queue_panel.js';
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
const textOf = (mount) => walk(mount).map((n) => n.textContent || '').join(' ');

// 서버가 «실제로» 내는 모양 (main.py 의 행 조립을 읽고 적음)
const WAITING = { outbox_id: 11, event_type: 'EDIT', table_name: 'dt_log',
                  created_at: '2026-09-22 20:00:00', waiting_seconds: 90, owner: 'chain',
                  chain_state: 'waiting', state_detail: '', broadcast_state: 'pending',
                  rules: [{ name: 'dt_log_to_dt_map', will_fire: true }], note: '' };
const RETRYING = { ...WAITING, outbox_id: 12, chain_state: 'waiting',
                   state_detail: 'retrying' };
const DELETED = { outbox_id: 13, event_type: 'DELETE', table_name: 'dt_log',
                  created_at: '2026-09-22 20:01:00', waiting_seconds: 30, owner: 'scheduler',
                  chain_state: 'waiting', state_detail: '', broadcast_state: 'not_applicable',
                  rules: [], note: 'DELETE does not wake any rule; only CREATE and EDIT are triggers' };
// 🔴 실패가 빠진 «오늘의» 모집단 문장 (서버 2eb1d38d).
const POP = 'processed_chain=false ∪ (done & undelivered)';
const REPLY = (rows) => ({ generated_at: '2026-09-22 20:02:00', clock: 'server', rows,
                           rules_known: ['dt_log_to_dt_map'],
                           listed: { cap: 200, next_cursor: null }, population: POP });

console.log('\n[게이트 ③] 기다리는 중 vs 재시도 중 — 둘 다 waiting 이다');
{
  const mount = mountPanel(REPLY([WAITING, RETRYING]));
  const details = byClass(mount, 'queue-state-detail').map((n) => n.textContent);
  eq('G3 the retrying row carries the server\'s detail', details.length, 1);
  ok('G3b ...and it is the server\'s token, not ours', details[0].includes('retrying'), details[0]);
  // 🔴 잘리는 칸은 이 화면에서 «한 가지 답»만 쓴다 — title. 하나만 빠지면 그게 갈라짐이다.
  eq('G3d ...and the clipped cell carries it in title, like every other clipped cell',
    byClass(mount, 'queue-state-detail')[0].getAttribute('title'), 'retrying');
  // 🔴 이 둘이 «같은 픽셀»이면 운영자는 멈춘 행을 「아직 안 돌았다」로 읽는다.
  const rows = byClass(mount, 'queue-row').map((n) => walk(n).map((c) => c.textContent).join('|'));
  ok('G3c the two rows do not render identically', rows[0] !== rows[1], rows[0]);
}

console.log('\n[게이트 ④] DELETE 행은 빈 칸이 아니라 문장을 낸다');
{
  const mount = mountPanel(REPLY([DELETED]));
  const notes = byClass(mount, 'queue-note').map((n) => n.textContent);
  eq('G4 a row nothing looked at says so', notes.length, 1);
  ok('G4b ...in the server\'s words', notes[0].includes('CREATE and EDIT'), notes[0] || '(none)');
  // 대조군: 규칙이 «있는» 행은 note 칸을 안 만든다
  eq('G4c CONTROL: a row with rules draws no note',
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
  // 🔴 「더 있다」의 «유일한» 저자는 next_cursor 다. `capped` 는 서버가 뺐다 (2201da21).
  eq('P3 「더 있다」 is next_cursor and nothing else',
    outboxQueueView({ ...REPLY([WAITING]), listed: { next_cursor: 11 } }).hasMore, 'true');
  eq('P3b ...and a full page alone does not claim it',
    outboxQueueView(REPLY([WAITING])).hasMore, 'false');
}

console.log('\n[못 읽었을 때]');
{
  const v = outboxQueueView(null, { failed: '구버전 서버 · 재시작 필요' });
  eq('U1 no payload reads as unread', v.read, 'false');
  ok('U2 ...with the reason, because a reasonless 「모름」 has nowhere to go',
    v.reason.includes('재시작'), v.reason);
  eq('U3 ...and draws no rows', byClass(mountPanel(null, { failed: 'x' }), 'queue-row').length, 0);
}

// ── 🔴 게이트 ① 이번 라운드의 게이트 — 빈 상태가 «기본»이다 ─────────────────────────
console.log('\n[게이트 ① 빈 것은 «왜» 비었는지 말한다]');
{
  const mount = mountPanel(REPLY([]));
  const empty = byClass(mount, 'queue-empty');
  eq('E1 an empty read says so in a sentence', empty.length, 1);
  ok('E1b ...that names what is not there', empty[0].textContent.includes('Nothing to run right now'),
    empty[0].textContent);
  // 🔴 「비었다」만으로는 «무엇이» 비었는지 모른다. 모집단과 기준 시각이 같은 화면에 있어야 한다.
  const shown = textOf(mount);
  ok('E2 ...beside the population it is empty OF', shown.includes(POP), shown);
  ok('E2b ...and the reference time', shown.includes('2026-09-22 20:02:00'), shown);
  // 🔴 «빈 표»를 그리면 그건 「안 읽혔다」와 같은 픽셀이다.
  eq('E3 an empty read draws no table head', byClass(mount, 'queue-head').length, 0);
  eq('E3b ...and no rows', byClass(mount, 'queue-row').length, 0);
  // 🔴 「이 쪽 0 행」은 «수를 세어 보여 준» 것처럼 읽힌다. 빈 것은 문장이 말한다.
  eq('E3c ...and does not count to zero', byClass(mount, 'queue-page').length, 0);
  // 대조군 — «못 읽은» 화면은 이것과 «다른» 픽셀이어야 한다
  const unread = mountPanel(null, { failed: '서버가 답을 안 했습니다' });
  eq('E4 CONTROL: an unread screen draws no empty sentence',
    byClass(unread, 'queue-empty').length, 0);
  ok('E4b ...and says its own reason instead',
    textOf(unread).includes('서버가 답을 안 했습니다'), textOf(unread));
  ok('E4c ...so the two screens do not render alike', textOf(mount) !== textOf(unread), '(same)');
}

// ── 🔴 게이트 ③ 한 행이 «한 줄» — 감사 표와 같은 모양 ──────────────────────────────
const OFF = 'declaration is switched off (`enabled: false`)';
const CHAIN_ONLY = 'chain-produced event; this rule does not declare `allow_chain_trigger`';
const MANY = { ...WAITING, outbox_id: 21, rules: [
  { name: 'a', will_fire: true }, { name: 'b', will_fire: true },
  { name: 'c', will_fire: false, why_not: OFF },
  { name: 'd', will_fire: false, why_not: OFF },
  { name: 'e', will_fire: false, why_not: OFF }] };
const TWO_REASONS = { ...WAITING, outbox_id: 22, rules: [
  { name: 'c', will_fire: false, why_not: OFF },
  { name: 'f', will_fire: false, why_not: CHAIN_ONLY }] };

console.log('\n[게이트 ③ 한 행 = 한 줄. 칸 여섯, 가로지르는 노드 0]');
{
  const mount = mountPanel(REPLY([MANY, RETRYING, DELETED]));
  const rows = byClass(mount, 'queue-row');
  eq('C1 every payload row is one row node', rows.length, 3);
  // 🔴 «규칙 수가 행 높이를 바꾸면» 한 줄이 아니다. 칸 수가 행마다 같아야 한다.
  const counts = rows.map((r) => r.children.length);
  ok('C1b every row has the same six cells, whatever it carries',
    counts.every((n) => n === 6), counts.join(','));
  // 🔴 이전 설계는 규칙·사유·note 를 «행을 가로지르는» 줄로 그렸다. 그 자리가 두 줄의 원인이다.
  const spanning = walk(mount).filter((n) => ['queue-rule', 'queue-rules-toggle', 'queue-state-detail']
    .some((c) => String(n.className || '').split(/\s+/).includes(c) && n.parentNode
      && String(n.parentNode.className || '').split(/\s+/).includes('queue-row')));
  eq('C2 no node hangs off the row itself any more', spanning.length, 0);
  eq('C2b ...and the fold button is gone', byClass(mount, 'queue-rules-toggle').length, 0);
  // 감사 표의 «모양»을 입는다 — 셀·머리줄·배지가 같은 이름이다
  ok('C3 every cell wears the audit cell class',
    rows.every((r) => r.children.every((c) => String(c.className).includes('audit-cell'))),
    rows[0].children.map((c) => c.className).join(' | '));
  eq('C4 there is a header row', byClass(mount, 'audit-head').length, 1);
  eq('C4b ...with one label per column', byClass(mount, 'audit-head')[0].children.length, 6);
  ok('C4c ...and Owner is the first of them',
    byClass(mount, 'audit-head')[0].children[0].textContent === 'Owner',
    byClass(mount, 'audit-head')[0].children.map((c) => c.textContent).join(','));
  eq('C5 the state cell wears the audit pill', byClass(mount, 'audit-pill').length, 3);
  // 🔴 표가 «자기 상자 안»에서 구른다 — 안 그러면 행 수가 판의 높이가 된다
  eq('C6 rows live in their own scroll box', byClass(mount, 'queue-rows').length, 1);
}

console.log('\n[㉯ 규칙은 «칸»이 됐다 — 사유별 수를 «잃지 않고»]');
{
  const mount = mountPanel(REPLY([MANY]));
  const cell = byClass(mount, 'queue-rules')[0];
  // 🔴 「규칙 5」였으면 이 화면의 존재 이유인 「왜 안 도나」가 사라진다.
  ok('R1 the rules cell counts what runs', cell.textContent.includes('2 firing'), cell.textContent);
  ok('R1b ...and what does not, BY REASON, in the server\'s words',
    cell.textContent.includes(`3 ${OFF}`), cell.textContent);
  const two = byClass(mountPanel(REPLY([TWO_REASONS])), 'queue-rules')[0].textContent;
  ok('R2 two reasons stay two — no word folds them together',
    two.includes(`1 ${OFF}`) && two.includes(`1 ${CHAIN_ONLY}`), two);
  // 🔴 칸이 좁아 «잘린다»(실측 124px vs 302px). 온 문장은 title 이 들어야 잃지 않는다.
  eq('R3 the full sentence rides in title, because the cell truncates it',
    cell.getAttribute('title'), cell.textContent);
  ok('R3b ...and that title is the whole reason, not a prefix',
    cell.getAttribute('title').includes(OFF), cell.getAttribute('title'));
  // 사유 없는 거절은 사유를 «지어내지» 않는다
  const bare = byClass(mountPanel(REPLY([{ ...WAITING, outbox_id: 23,
    rules: [{ name: 'g', will_fire: false }] }])), 'queue-rules')[0].textContent;
  ok('R4 a refusal with no reason says the count and invents nothing',
    bare.includes('1 not firing') && !bare.includes('switched off'), bare);
  // 조립식의 정의: 같은 화면에 둘을 앉혀도 서로를 안 건드린다
  const a = mountPanel(REPLY([MANY]));
  const b = mountPanel(REPLY([TWO_REASONS]));
  ok('R5 two panels on one page draw their own payloads',
    byClass(a, 'queue-rules')[0].textContent !== byClass(b, 'queue-rules')[0].textContent,
    byClass(a, 'queue-rules')[0].textContent);
  // 좌석 하나 — 화면이 부르는 그 함수가 수를 짓는다
  eq('R6 the cell text is the shared seat\'s, not a second author',
    cell.textContent, summaryText(outboxQueueView(REPLY([MANY])).rows[0].ruleSummary));
}

console.log('\n[㉰ 머리글이 «이 쪽»을 말한다 — 수는 이 쪽의 수다]');
{
  const mount = mountPanel({ ...REPLY([WAITING, { ...WAITING, outbox_id: 99 }]),
    listed: { cap: 200, next_cursor: 11 } });
  const text = (byClass(mount, 'queue-page')[0] || {}).textContent || '';
  ok('F1 the page says its own count', text.includes('2 on this page'), text);
  ok('F1b ...and the values every row on it shares', text.includes('dt_log') && text.includes('EDIT'), text);
  // 🔴 수와 「다음 쪽」이 떼어지면 「2」가 «전부»로 읽힌다. 한 «마디»여야 한다.
  ok('F2 ...in the SAME node as 「more pages」', text.includes('more pages'), text);
  eq('F2b ...and there is only one such node', byClass(mount, 'queue-page').length, 1);
  // 🔴 대조군 — 섞인 쪽에서는 그 칸에 대해 «아무 말도 안 한다» (절대어 상설).
  const mixed = (byClass(mountPanel(REPLY([WAITING,
    { ...WAITING, outbox_id: 98, table_name: 'dt_map' }])), 'queue-page')[0] || {}).textContent || '';
  ok('F3 CONTROL: a mixed column is not named at all',
    !mixed.includes('dt_log') && !mixed.includes('dt_map'), mixed);
  ok('F3b ...while the column that IS shared still is', mixed.includes('EDIT'), mixed);
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
