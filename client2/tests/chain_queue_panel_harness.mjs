// CHAIN QUEUE INSTRUMENT — the four rules the panel exists to keep, scored.
//
// The subject is imported (owner, 2026-09-02: 잘라쓰기 하니스 절대 금지). `chain_queue_panel.js`
// touches no DOM and no CSS at module scope, so it imports in node as it stands.
//
// What is scored is the DISCRIMINATION, not the wording:
//   ① `null` and `0` must not render the same. Every assertion here compares the two states
//      against each other rather than against a fixed string, so a copy edit cannot redden it
//      and a copy edit cannot silently collapse them either.
//   ② a number the route refused to compute is drawn WITH ITS REASON, because an absent
//      number reads as zero.
//   ③ the panel invents no threshold — no sample of a single reading is coloured as late.
//   ④ a list the route CUT says it was cut, because a silently truncated list reads as the
//      whole queue.
//
// 🔴 2026-09-04, the card strip became a table (owner: 「그냥 대기중인 트랜잭션 리스트로
//    보여줘 kpi 카드 형태 말고」). The two numbers the strip carried — depth and retries —
//    did NOT leave with it; they are asserted below on the headline line, because a measured
//    number that stops being drawn is rule ② with the sign flipped.
//
// Run: node client2/tests/chain_queue_panel_harness.mjs
import { queueView, formatAge, STATUS, ChainQueuePanel } from '../src/chain_queue_panel.js';

let pass = 0;
const failures = [];
function eq(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { pass++; console.log(`  PASS ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name}\n        got  ${g}\n        want ${w}`); }
}
function ok(name, cond, detail = '') {
  if (cond) { pass++; console.log(`  PASS ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name} ${detail}`); }
}

// ── the DOM stub (same shape `grid_source_label_harness.mjs` drives; consolidating the four
//    copies in `tests/` is its own round, and it is not this one) ──────────────────────────
function makeNode(doc, tag) {
  const node = {
    tagName: String(tag).toUpperCase(),
    className: '', style: {}, children: [], attrs: Object.create(null), _text: '', title: '',
    appendChild(c) { this.children.push(c); return c; },
    setAttribute(k, v) { this.attrs[String(k)] = String(v); },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, String(k)) ? this.attrs[String(k)] : null; },
    set textContent(v) { this._text = String(v); this.children.length = 0; },
    get textContent() { return this._text + this.children.map(c => c.textContent).join(''); },
  };
  return node;
}
const makeDoc = () => { const doc = { createElement: t => makeNode(doc, t) }; return doc; };
const walk = (n, out = []) => { out.push(n); for (const c of n.children || []) walk(c, out); return out; };
const byClass = (host, cls) => walk(host)
  .filter(n => String(n.className || '').split(/\s+/).includes(cls));
const byTag = (host, tag) => walk(host).filter(n => n.tagName === tag);

const NOT_MEASURED = {
  retried_total: 'retry_count 에 인덱스가 없어 표 전체를 훑는다 (EXPLAIN 비용 272,812)',
  processed_recently: 'processed_at 에 인덱스가 없어 표 전체를 훑는다 (EXPLAIN 비용 272,817)',
};
const EMPTY = { waiting: 0, oldest_waiting_seconds: null, oldest_waiting_at: null,
                retried_among_waiting: 0, waiting_transactions: [],
                listed: { rows_scanned: 0, cap: 200, capped: false },
                not_measured: NOT_MEASURED };
const JUST_ARRIVED = { waiting: 1, oldest_waiting_seconds: 0,
                       oldest_waiting_at: '2026-09-03 11:40:00', retried_among_waiting: 0,
                       waiting_transactions: [
                         { transaction_id: 'aaaaaaaa-1111-2222-3333-444444444444', rows: 1,
                           tables: ['wafer_process'], event_types: ['CREATE'], max_retry: 0,
                           waiting_seconds: 0, waiting_at: '2026-09-03 11:40:00' },
                       ],
                       listed: { rows_scanned: 1, cap: 200, capped: false },
                       not_measured: NOT_MEASURED };
// 812 waiting, but the route only ever reads `cap` rows -> the list is CUT. See rule ④.
const BACKED_UP = { waiting: 812, oldest_waiting_seconds: 3725.4,
                    oldest_waiting_at: '2026-09-03 10:38:14', retried_among_waiting: 17,
                    waiting_transactions: [
                      { transaction_id: 'bbbbbbbb-1111-2222-3333-444444444444', rows: 40,
                        tables: ['wafer_process', 'lot_master'], event_types: ['CREATE', 'UPDATE'],
                        max_retry: 3, waiting_seconds: 3725.4, waiting_at: '2026-09-03 10:38:14' },
                      { transaction_id: 'cccccccc-1111-2222-3333-444444444444', rows: 160,
                        tables: ['mi_gauge'], event_types: ['UPDATE'], max_retry: 0,
                        waiting_seconds: 90, waiting_at: '2026-09-03 11:38:14' },
                    ],
                    listed: { rows_scanned: 200, cap: 200, capped: true },
                    not_measured: NOT_MEASURED };

const rowsOf = (host) => byClass(host, 'table-row');
// Re-read one blocked field through the real view, so the assertion exercises `blockedView`
// rather than a copy of it.
const blockedOf = (v, over) => queueView({
  waiting_by_owner: [{ owner: 'scheduler', waiting: 1, oldest_waiting_seconds: 1,
    event_types: [], blocked_by: { run_id: 'r', op: 'o', state: 'running', moving: 'unreported',
      stall_after_seconds: 300, processed_rows: 0, total_rows: 0, cancel_reaches: 'unknown',
      ...over } }],
}).byOwner[0].blocked.noProgress;
const cellsOf = (row) => row.children;

// ═══ ① null IS NOT 0 ═══════════════════════════════════════════════════════════════
console.log('\n[1] an empty queue and a queue that just received something are DIFFERENT');
{
  const a = queueView(EMPTY).headline;
  const b = queueView(JUST_ARRIVED).headline;

  // 🔴 THE DISCRIMINANT. Compared against each other, not against fixed strings: this is the
  //    one property that cannot be allowed to drift, and pinning wording instead would make a
  //    copy edit look like a defect while a real collapse looked like a rename.
  ok('the two states do not share a headline', a.main !== b.main, `${a.main} / ${b.main}`);
  ok('nor an explanation', a.sub !== b.sub);
  ok('nor a status token', a.status !== b.status, `${a.status} / ${b.status}`);

  // and each says the right thing, so "different" cannot be satisfied by two wrong answers
  ok('empty says nothing is waiting', /대기 없음/.test(a.main), a.main);
  eq('empty is the only OK state on this line', a.status, STATUS.OK);
  ok('just-arrived shows a real zero, not an absence', /0/.test(b.main) && !/없/.test(b.main), b.main);
  ok('and its explanation carries the timestamp it has been waiting since',
    b.sub.includes('2026-09-03 11:40:00'), b.sub);

  // the same discrimination, drawn
  const doc = makeDoc();
  const h1 = doc.createElement('div'), h2 = doc.createElement('div');
  new ChainQueuePanel(h1, { doc }).render(EMPTY);
  new ChainQueuePanel(h2, { doc }).render(JUST_ARRIVED);
  const mainOf = (h) => byClass(h, 'chain-queue-headline-main')[0].textContent;
  ok('and the two render to different pixels', mainOf(h1) !== mainOf(h2),
    `${mainOf(h1)} / ${mainOf(h2)}`);

  // 🔴 the same rule, one layer in: a ROW whose age cannot be read is a dash, never 「0초」.
  const unreadable = queueView({ ...JUST_ARRIVED, waiting_transactions: [
    { ...JUST_ARRIVED.waiting_transactions[0], waiting_seconds: null }] });
  eq('a row with no readable age is a dash', unreadable.rows[0].age, '—');
  eq('and a row that really waited 0 says 0초', queueView(JUST_ARRIVED).rows[0].age, '0초');
}

// ═══ ② a number that was NOT measured is named, with its reason ═══════════════════
console.log('\n[2] the two the route refuses to compute are named, not omitted');
{
  const v = queueView(BACKED_UP);
  eq('both are carried', v.notMeasured.map(x => x.name), ['retried_total', 'processed_recently']);
  ok('each carries the route\'s own reason, not a shrug',
    v.notMeasured.every(x => x.why.length > 20 && /인덱스/.test(x.why)),
    JSON.stringify(v.notMeasured));

  const doc = makeDoc();
  const host = doc.createElement('div');
  new ChainQueuePanel(host, { doc }).render(BACKED_UP);
  const named = walk(host).filter(n => n.getAttribute && n.getAttribute('data-name'));
  eq('and both reach the screen', named.map(n => n.getAttribute('data-name')),
    ['retried_total', 'processed_recently']);
  ok('with the reason beside the name', named.every(n => /인덱스/.test(n.textContent)));

  // 🔴 NEGATIVE CONTROL. A response that names nothing must draw nothing here -- otherwise
  //    "both reach the screen" would pass on a panel that printed a hardcoded pair.
  const bare = { ...BACKED_UP };
  delete bare.not_measured;
  const doc2 = makeDoc();
  const host2 = doc2.createElement('div');
  new ChainQueuePanel(host2, { doc: doc2 }).render(bare);
  eq('a response that names none draws none',
    walk(host2).filter(n => n.getAttribute && n.getAttribute('data-name')).length, 0);

  // 🔴 THE SIGN-FLIPPED CASE, added when the card strip was replaced by the table. The strip
  //    carried depth and retries; if losing the strip lost the numbers, this reddens.
  ok('the depth the strip carried is still drawn', /812/.test(v.headline.aggregate), v.headline.aggregate);
  ok('and so is the retry count', /17/.test(v.headline.aggregate), v.headline.aggregate);
  ok('and both reach the screen', /812/.test(host.textContent) && /17/.test(host.textContent));
}

// ═══ ③ no invented threshold, and no invented number ═══════════════════════════════
console.log('\n[3] the panel judges nothing it was not told, and prints no number it was not given');
{
  // An hour of backlog is still not coloured as a fault: one sample cannot tell "growing"
  // from "busy", and the route's own docstring says so. If a threshold is ever wanted it is a
  // declaration, not a constant hidden in a view.
  const v = queueView(BACKED_UP);
  eq('a large age is NOT coloured as danger', v.headline.status, STATUS.NEUTRAL);
  ok('and the line says how to read it instead', /자라는지/.test(v.headline.sub));
  // the same restraint per row: 3 retries is stated, not judged
  eq('a row with retries states the count', v.rows[0].maxRetry, '3');
  eq('and a row with none leaves the cell empty, not 0', v.rows[1].maxRetry, '');

  // A missing count is a dash. `0` would be a claim.
  const partial = queueView({ oldest_waiting_seconds: null, not_measured: NOT_MEASURED });
  ok('an absent depth is a dash, not 0', /대기 —개/.test(partial.headline.aggregate),
    partial.headline.aggregate);
  ok('an absent retry count is a dash, not 0', /재시도 —개/.test(partial.headline.aggregate),
    partial.headline.aggregate);
  ok('a present zero IS a zero', /대기 0개/.test(queueView(EMPTY).headline.aggregate),
    queueView(EMPTY).headline.aggregate);
  eq('and a response with no list at all draws no rows, rather than throwing',
    partial.rows.length, 0);

  // Unavailable: nothing at all. A stale or invented figure is worse than an empty panel.
  const gone = queueView(null, { unavailable: '이 서버 프로세스에 /admin/chain/queue 가 없습니다 (404).' });
  eq('unavailable draws no rows', gone.rows.length, 0);
  eq('and no headline to hang a number on', gone.headline, null);
  ok('and says why by name', /404/.test(gone.reason), gone.reason);
  const doc = makeDoc();
  const host = doc.createElement('div');
  new ChainQueuePanel(host, { doc }).render(null, { unavailable: 'HTTP 500' });
  eq('and nothing numeric reaches the screen', byClass(host, 'chain-queue-headline-main').length, 0);
  eq('nor any row', rowsOf(host).length, 0);
  ok('but the reason does', /HTTP 500/.test(host.textContent), host.textContent);
}

// ═══ ④ a list that was CUT says it was cut ═════════════════════════════════════════
console.log('\n[4] truncation is stated, and only when it happened');
{
  const cut = queueView(BACKED_UP);
  ok('a capped read says so', cut.truncated.length > 0, cut.truncated);
  ok('and names both the rows read and the cap', /200/.test(cut.truncated), cut.truncated);
  ok('and says the list is not the whole queue', /전부가 아닙니다/.test(cut.truncated), cut.truncated);

  // 🔴 NEGATIVE CONTROL. An uncut list must say NOTHING -- a permanent warning is the same
  //    as no warning, because the reader stops seeing it.
  eq('an uncut read says nothing', queueView(JUST_ARRIVED).truncated, '');
  eq('and neither does an empty one', queueView(EMPTY).truncated, '');
  // a response from a server that predates `listed` must not claim truncation either
  const noListed = { ...BACKED_UP };
  delete noListed.listed;
  eq('nor a response that carries no `listed` at all', queueView(noListed).truncated, '');

  const doc = makeDoc();
  const host = doc.createElement('div');
  new ChainQueuePanel(host, { doc }).render(BACKED_UP);
  eq('and the notice reaches the screen exactly once',
    byClass(host, 'chain-queue-truncated').length, 1);
}

// ═══ ⑤ the list itself — order, contents, and the empty case ══════════════════════
console.log('\n[5] the list is drawn in the order it arrived, oldest first');
{
  const v = queueView(BACKED_UP);
  eq('one row per transaction', v.rows.length, 2);
  // 🔴 the server orders by `id` ascending = longest waiting first. That ORDER IS THE ANSWER
  //    to 「누가 밀려 있나」, so the view must not re-sort it.
  eq('server order is preserved', v.rows.map(r => r.txId.slice(0, 8)), ['bbbbbbbb', 'cccccccc']);
  eq('the id is abbreviated head8', v.rows[0].txShort, 'bbbbbbbb…');
  eq('several tables join into one cell', v.rows[0].tables, 'wafer_process, lot_master');
  eq('a transaction with no table named draws a dash, not blank',
    queueView({ ...BACKED_UP, waiting_transactions: [
      { transaction_id: 'x', rows: 1, tables: [], event_types: [], max_retry: 0,
        waiting_seconds: 5 }] }).rows[0].tables, '—');
  eq('the row count is carried', v.rows[0].rows, '40');
  eq('the age is formatted, not raw seconds', v.rows[0].age, '1시간 2분');

  const doc = makeDoc();
  const host = doc.createElement('div');
  new ChainQueuePanel(host, { doc }).render(BACKED_UP);
  eq('two rows are drawn', rowsOf(host).length, 2);
  eq('each row has the six columns the header declares', cellsOf(rowsOf(host)[0]).length, 6);
  eq('the header declares six', byTag(host, 'TH').length, 6);
  ok('the full id is on the chip for copying, not only the abbreviation',
    walk(host).some(n => n.title === 'bbbbbbbb-1111-2222-3333-444444444444'));
  ok('and the row carries it as data for anything that wants to select on it',
    rowsOf(host)[0].getAttribute('data-txid') === 'bbbbbbbb-1111-2222-3333-444444444444');

  // an empty queue draws NO table -- an empty table with a header reads as "loading"
  const doc2 = makeDoc();
  const host2 = doc2.createElement('div');
  new ChainQueuePanel(host2, { doc: doc2 }).render(EMPTY);
  eq('an empty queue draws no table at all', byTag(host2, 'TABLE').length, 0);
  ok('and says so in words', /대기 중인 트랜잭션이 없습니다/.test(host2.textContent));
  // ...but the headline is still there, because 「대기 없음」 is itself the answer (rule ①)
  eq('while the headline stays', byClass(host2, 'chain-queue-headline-main').length, 1);
}

// ═══ ⑥ formatAge — total, and the boundaries ═══════════════════════════════════════
console.log('\n[6] formatAge');
{
  eq('0', formatAge(0), '0초');
  eq('59', formatAge(59), '59초');
  eq('60', formatAge(60), '1분');
  eq('90', formatAge(90), '1분 30초');
  eq('3600', formatAge(3600), '1시간');
  eq('3725.4 truncates, never rounds up past the real wait', formatAge(3725.4), '1시간 2분');
  eq('86400', formatAge(86400), '1일');
  eq('90000', formatAge(90000), '1일 1시간');
  // total: garbage in is null, not `NaN초`
  eq('null', formatAge(null), null);
  eq('undefined', formatAge(undefined), null);
  eq('a string', formatAge('soon'), null);
  eq('negative', formatAge(-5), null);
}

// ═══ ⑦ 조립식 — two instances on one page do not touch each other ═══════════════════
console.log('\n[7] two panels on one page');
{
  const doc = makeDoc();
  const h1 = doc.createElement('div'), h2 = doc.createElement('div');
  const p1 = new ChainQueuePanel(h1, { doc });
  const p2 = new ChainQueuePanel(h2, { doc });
  p1.render(EMPTY);
  p2.render(BACKED_UP);
  const headOf = (h) => byClass(h, 'chain-queue-headline-main')[0].textContent;
  ok('the second does not overwrite the first', headOf(h1) !== headOf(h2),
    `${headOf(h1)} / ${headOf(h2)}`);
  eq('the first still reads its own payload', rowsOf(h1).length, 0);
  eq('the second still reads its own', rowsOf(h2).length, 2);
  // re-rendering replaces rather than appends -- a panel that appended would show every
  // refresh ever made, stacked, and the newest would be at the bottom.
  p1.render(BACKED_UP);
  eq('a re-render replaces, it does not append', rowsOf(h1).length, 2);
  eq('and leaves exactly one headline', byClass(h1, 'chain-queue-headline').length, 1);
}

// ═══ ⑧ WHO EMPTIES THE ROW — and the fold that must not happen ══════════════════
//
// 🔴 THE ONE THIS SECTION EXISTS FOR: `unknown` must not be counted as `chain`. The route
//    was read as one undifferentiated queue called the chain's, and on 2026-09-04 that sent
//    someone to inspect a worker that was healthy while a scheduler run sat still. The server
//    now keeps the buckets apart; the screen folding them would rebuild the misreading one
//    layer out, and no existing assertion would notice.
console.log('\n[8] the owner split, and unknown is not chain');
{
  const OWNED = {
    ...BACKED_UP,
    waiting: 8,
    waiting_by_owner: [
      { owner: 'chain', waiting: 5, oldest_waiting_seconds: 90, event_types: ['CREATE'] },
      { owner: 'scheduler', waiting: 2, oldest_waiting_seconds: 3725.4,
        event_types: ['RETRO'],
        blocked_by: {
          run_id: 'run-77', op: 'ledger_rescope', state: 'running', moving: 'stalled',
          no_progress_seconds: 900, stall_after_seconds: 300,
          processed_rows: 12, total_rows: 400, cancel_reaches: 'never',
          recovery: '이 실행은 취소로 멈출 수 없습니다.',
        } },
      { owner: 'unknown', waiting: 1, oldest_waiting_seconds: 5, event_types: ['WAT'] },
    ],
    waiting_transactions: [
      { ...BACKED_UP.waiting_transactions[0], owners: ['chain'] },
      { ...BACKED_UP.waiting_transactions[1], owners: ['scheduler', 'unknown'] },
    ],
  };
  const v = queueView(OWNED);

  // 🔴 THE DISCRIMINANT. Compared against the server's own numbers, not a fixed string.
  eq('three buckets stay three', v.byOwner.map(b => b.owner), ['chain', 'scheduler', 'unknown']);
  eq('chain carries ONLY chain\'s rows', v.byOwner[0].waiting, '5');
  ok('and not the sum of chain + unknown', v.byOwner[0].waiting !== '6', v.byOwner[0].waiting);
  ok('nor the whole queue', v.byOwner[0].waiting !== '8', v.byOwner[0].waiting);
  eq('unknown is its own bucket with its own number', v.byOwner[2].waiting, '1');
  eq('each bucket keeps its own age', v.byOwner[1].age, '1시간 2분');

  // one owner is not a split
  const ONE = { ...OWNED, waiting_by_owner: [OWNED.waiting_by_owner[0]] };
  eq('two or more owners split', v.splitByOwner, true);
  eq('one owner does NOT split', queueView(ONE).splitByOwner, false);
  eq('and a server that sends no buckets at all splits nothing',
    queueView(BACKED_UP).splitByOwner, false);
  eq('...and draws no bucket', queueView(BACKED_UP).byOwner.length, 0);

  // per row
  eq('a row shows who empties it', v.rows[0].owners, 'chain');
  eq('a row with two owners shows both', v.rows[1].owners, 'scheduler, unknown');
  eq('a row the server did not name draws a dash, not chain',
    queueView({ ...OWNED, waiting_transactions: [
      { ...BACKED_UP.waiting_transactions[0] }] }).rows[0].owners, '—');

  // ── blocked_by: the server's words, moved not translated ──
  const bl = v.byOwner[1].blocked;
  ok('the scheduler bucket carries its blocker', !!bl, JSON.stringify(v.byOwner[1]));
  eq('moving is the server\'s token', bl.moving, 'stalled');
  eq('cancel_reaches is the server\'s token', bl.cancelReaches, 'never');
  eq('the run is named', bl.runId, 'run-77');
  eq('progress is carried', `${bl.processed} / ${bl.total}`, '12 / 400');
  eq('the recovery sentence is the server\'s, verbatim', bl.recovery,
    '이 실행은 취소로 멈출 수 없습니다.');
  // rule ① one layer down: a run that never reported is not a run at 0 seconds
  eq('an unreported run\'s no-progress is a dash', blockedOf(v, { no_progress_seconds: null }), '—');
  eq('...and a real zero is a zero', blockedOf(v, { no_progress_seconds: 0 }), '0초');

  // 🔴 NEGATIVE CONTROL. A bucket with no blocker draws NOTHING — an 「없음」 here is the
  //    same invented zero the whole file exists to prevent, and the server says so itself.
  eq('a bucket with blocked_by null carries no blocker', v.byOwner[0].blocked, null);
  eq('and a bucket that never had the field carries none either', v.byOwner[2].blocked, null);

  // ── and all of it reaches the screen ──
  const doc = makeDoc();
  const host = doc.createElement('div');
  new ChainQueuePanel(host, { doc }).render(OWNED);
  const owners = walk(host).filter(n => n.getAttribute && n.getAttribute('data-owner'));
  eq('three owner elements are drawn as three', new Set(owners.map(n => n.getAttribute('data-owner'))).size, 3);
  ok('chain\'s line says 5, not 8', /chain · 대기 5개/.test(host.textContent), host.textContent.slice(0, 120));
  ok('unknown appears on screen under its own name', /unknown · 대기 1개/.test(host.textContent));
  eq('exactly one blocked box is drawn', byClass(host, 'chain-queue-blocked').length, 1);
  ok('and it prints the tokens rather than a translation',
    /stalled/.test(host.textContent) && /never/.test(host.textContent));
  ok('the row owners reach the screen',
    walk(host).some(n => n.getAttribute && n.getAttribute('data-owners') === 'scheduler, unknown'));
  // the table did not grow a column — the overflow round measured that cost
  eq('the header still declares six', byTag(host, 'TH').length, 6);
  eq('and each row still has six cells', cellsOf(rowsOf(host)[0]).length, 6);

  const doc2 = makeDoc();
  const host2 = doc2.createElement('div');
  new ChainQueuePanel(host2, { doc: doc2 }).render(BACKED_UP);
  eq('a bucket-less response draws no owner strip', byClass(host2, 'chain-queue-owner-strip').length, 0);
  eq('and no blocked box', byClass(host2, 'chain-queue-blocked').length, 0);
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
