// CHAIN QUEUE INSTRUMENT — the four rules the panel exists to keep, scored.
//
// The subject is imported (owner, 2026-09-02: 잘라쓰기 하니스 절대 금지). `chain_queue_panel.js`
// touches no DOM and no CSS at module scope, so it imports in node as it stands.
//
// What is scored is the DISCRIMINATION, not the wording:
//   ① `null` and `0` must not render the same. Every assertion here compares the two states
//      against each other rather than against a fixed string, so a copy edit cannot redden it
//      and a copy edit cannot silently collapse them either.
//   ② a number the screen cannot read has NO CELL — dropped, never drawn as 0. Since mockup A
//      `not_measured` is not drawn at all: there is no slot for those numbers to read as zero.
//   ③ the panel invents no threshold — no sample of a single reading is coloured as late.
//   ④ a list the route CUT says it was cut, because a silently truncated list reads as the
//      whole queue.
//
// 🔴 2026-09-25, mockup A (owner 「A 로 해」): four numbers · the list · one meta line. Depth and
//    retries did NOT leave with the old headline — depth is the Waiting number and retries sit
//    in the meta line, because a measured number that stops being drawn is rule ② with the
//    sign flipped.
//
// Run: node client2/tests/chain_queue_panel_harness.mjs
import { readFileSync } from 'node:fs';
import { queueView, formatAge, failedSince, MINUTE_SECONDS, ChainQueuePanel } from '../src/chain_queue_panel.js';
import { ABSENT } from '../src/absent.js';
import { localShort, localStamp } from '../src/server_time.js';

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
    listeners: Object.create(null),
    addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); },
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
                listed: { lines: 0, lines_total: 0, cap: 200, capped: false },
                not_measured: NOT_MEASURED };
const JUST_ARRIVED = { waiting: 1, oldest_waiting_seconds: 0,
                       oldest_waiting_at: '2026-09-03 11:40:00', retried_among_waiting: 0,
                       waiting_transactions: [
                         { run_id: null, op: null,
                           transaction_id: 'aaaaaaaa-1111-2222-3333-444444444444', events: 1, rows: 1,
                           tables: ['wafer_process'], event_types: ['CREATE'], max_retry: 0,
                           waiting_seconds: 0, waiting_at: '2026-09-03 11:40:00' },
                       ],
                       listed: { lines: 1, lines_total: 1, cap: 200, capped: false },
                       not_measured: NOT_MEASURED };
// 812 waiting in 9 lines, but the route lists `cap` lines -> the list is CUT. See rule ④.
const BACKED_UP = { waiting: 812, oldest_waiting_seconds: 3725.4,
                    oldest_waiting_at: '2026-09-03 10:38:14', retried_among_waiting: 17,
                    waiting_transactions: [
                      { transaction_id: 'bbbbbbbb-1111-2222-3333-444444444444', events: 12, rows: 40,
                        tables: ['wafer_process', 'lot_master'], event_types: ['CREATE', 'UPDATE'],
                        max_retry: 3, waiting_seconds: 3725.4, waiting_at: '2026-09-03 10:38:14' },
                      { transaction_id: 'cccccccc-1111-2222-3333-444444444444', events: 160, rows: 160,
                        tables: ['mi_gauge'], event_types: ['UPDATE'], max_retry: 0,
                        waiting_seconds: 90, waiting_at: '2026-09-03 11:38:14' },
                    ],
                    listed: { lines: 2, lines_total: 9, cap: 2, capped: true },
                    not_measured: NOT_MEASURED };

const rowsOf = (host) => byClass(host, 'table-row');
// One number cell by its key, from the view; and the drawn box that carries the same key.
const numberOf = (v, key) => v.numbers.find((n) => n.key === key);
const metaOf = (v, key) => (v.meta.find((m) => m.key === key) || { text: '' }).text;
const boxOf = (host, key) => walk(host).find((n) => n.getAttribute && n.getAttribute('data-key') === key);
const valueOf = (host, key) => {
  const box = boxOf(host, key);
  return box ? byClass(box, 'chain-queue-number-value').map((n) => n.textContent).join('') : null;
};
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
  const a = numberOf(queueView(EMPTY), 'oldest');
  const b = numberOf(queueView(JUST_ARRIVED), 'oldest');

  // 🔴 THE DISCRIMINANT. Compared against each other, not against fixed strings: this is the
  //    one property that cannot be allowed to drift, and pinning wording instead would make a
  //    copy edit look like a defect while a real collapse looked like a rename.
  ok('the two states do not share an Oldest number', a.value !== b.value, `${a.value} / ${b.value}`);
  // and each says the right thing, so "different" cannot be satisfied by two wrong answers
  eq('empty draws the absence mark (lead 6fdd79d4e: 「Oldest —」)', a.value, ABSENT);
  eq('just-arrived shows a real zero, not an absence', b.value, '0s');
  // an age that does not read is a BLIND cell — dropped, not drawn as 0s and not as 「—」
  eq('an unreadable age has no Oldest cell at all',
    numberOf(queueView({ ...JUST_ARRIVED, oldest_waiting_seconds: 'soon' }), 'oldest'), undefined);

  // the same discrimination, drawn
  const doc = makeDoc();
  const h1 = doc.createElement('div'), h2 = doc.createElement('div');
  new ChainQueuePanel(h1, { doc }).render(EMPTY);
  new ChainQueuePanel(h2, { doc }).render(JUST_ARRIVED);
  ok('and the two render to different pixels', valueOf(h1, 'oldest') !== valueOf(h2, 'oldest'),
    `${valueOf(h1, 'oldest')} / ${valueOf(h2, 'oldest')}`);

  // 🔴 the same rule, one layer in: a ROW whose age cannot be read is a dash, never 「0초」.
  const unreadable = queueView({ ...JUST_ARRIVED, waiting_transactions: [
    { ...JUST_ARRIVED.waiting_transactions[0], waiting_seconds: null }] });
  eq('a row with no readable age is a dash', unreadable.rows[0].age, '—');
  eq('and a row that really waited 0 says 0s', queueView(JUST_ARRIVED).rows[0].age, '0s');
}

// ═══ ② a number that was NOT measured is named, with its reason ═══════════════════
console.log('\n[2] a number the screen cannot read has no cell; not_measured is not drawn');
{
  const v = queueView(BACKED_UP);
  // 🔴 A: the screen has no slot for `retried_total` / `processed_recently`, so nothing reads as
  //    their zero — the reason stays in the route's response (lead 6fdd79d4e).
  eq('the view carries no not-measured list', 'notMeasured' in v, false);
  const doc = makeDoc();
  const host = doc.createElement('div');
  new ChainQueuePanel(host, { doc }).render(BACKED_UP);
  eq('and none of it reaches the screen',
    walk(host).filter(n => n.getAttribute && n.getAttribute('data-name')).length, 0);
  ok('nor its reason', !/인덱스/.test(host.textContent));

  // 🔴 THE SIGN-FLIPPED CASE. Depth and retries left the old headline; if they left the screen
  //    with it, these redden.
  eq('the depth is the Waiting number', numberOf(v, 'waiting').value, '812');
  eq('and the retry count is on the meta line', metaOf(v, 'retried'), 'retried 17');
  ok('and both reach the screen', valueOf(host, 'waiting') === '812' && /retried 17/.test(host.textContent));

  // ── Running is `now_running`'s count — one seat, four sources (lead 4994c3afe · 5996d7f54) ──
  const RUN = { waiting: 0, oldest_waiting_seconds: null, loop_seen_via: 'this_process',
    now_running: [{ what: 'r', where: 'chain_worker', pid: 1, elapsed_seconds: 5, progress: null, cancel: null }] };
  eq('an answer without the seat has no Running cell — not 0',
    numberOf(queueView({ waiting: 0, oldest_waiting_seconds: null, loop_seen_via: 'this_process' }), 'running'),
    undefined);
  eq('...and the old chain-only field is no longer read — two fields must not answer one question',
    numberOf(queueView({ waiting: 0, oldest_waiting_seconds: null, loop_seen_via: 'this_process',
      running: [{ rule: 'r', running_seconds: 5 }] }), 'running'), undefined);
  eq('the seat\'s items are counted', numberOf(queueView(RUN), 'running').value, '1');
  eq('and an empty seat is a read 0', numberOf(queueView({ ...RUN, now_running: [] }), 'running').value, '0');
  // ── the count asks `loop_seen_via` ALONE (lead 36dff3b6a) ──
  eq('a loop nobody saw has no Running cell — not 0',
    numberOf(queueView({ ...RUN, loop_seen_via: null }), 'running'), undefined);
  eq('...even when the old field says this process — two fields must not answer one question',
    numberOf(queueView({ ...RUN, loop_seen_via: null, loop_in_this_process: true }), 'running'), undefined);
  eq('a loop seen through the worker\'s heartbeat is counted',
    numberOf(queueView({ ...RUN, loop_seen_via: 'chain_worker_heartbeat' }), 'running').value, '1');
  const blind = makeDoc();
  const blindHost = blind.createElement('div');
  new ChainQueuePanel(blindHost, { doc: blind }).render({ ...RUN, loop_seen_via: null });
  eq('a blind cell is not drawn — the grid stands on the ones that read',
    byClass(blindHost, 'chain-queue-number').map((n) => n.getAttribute('data-key')), ['waiting', 'oldest']);
}

// ═══ Failed since — one function for the queue cell and the Overview card ═══════════
console.log('\n[F] Failed: unread · 0 · N since a time, decided in one place');
{
  const AT = '2026-09-24T04:02:11+00:00';
  eq('F1 no failed body is unread', failedSince(null).read, false);
  eq('F2 a body without a numeric total is unread, not 0', failedSince({ data: [] }).read, false);
  eq('F3 a read 0 is 0', [failedSince({ total: 0 }).read, failedSince({ total: 0 }).total], [true, 0]);
  eq('F4 a 0 has no since, even when a time came', failedSince({ total: 0, oldest_failed_at: AT }).since, '');
  // 총괄 e573a6edf — with a summary the count is the rows it folded, not the transaction groups.
  eq('F4b a summary is counted by its rows', failedSince({ total: 2,
    summary: [{ count: 33 }, { count: 4 }] }).total, 37);
  eq('F5 N failures carry the oldest one, in the viewer\'s zone', failedSince({ total: 81, oldest_failed_at: AT }).since,
    localShort(AT));
  const cellFor = (failed) => numberOf(queueView(JUST_ARRIVED, { failed }), 'failed');
  eq('F6 unread draws no Failed cell', cellFor(null), undefined);
  eq('F7 N failures: the label says since when, and it is the only coloured cell',
    [cellFor({ total: 81, oldest_failed_at: AT }).label, cellFor({ total: 81, oldest_failed_at: AT }).value,
     cellFor({ total: 81, oldest_failed_at: AT }).tone], [`Failed since ${localShort(AT)}`, '81', 'danger']);
  eq('F8 NEGATIVE CONTROL: 0 failures is not coloured and claims no time',
    [cellFor({ total: 0 }).label, cellFor({ total: 0 }).value, cellFor({ total: 0 }).tone], ['Failed', '0', '']);
}

// ═══ ③ no invented threshold, and no invented number ═══════════════════════════════
console.log('\n[3] the panel judges nothing it was not told, and prints no number it was not given');
{
  // An hour of backlog is still not coloured as a fault: one sample cannot tell "growing"
  // from "busy", and the route's own docstring says so. If a threshold is ever wanted it is a
  // declaration, not a constant hidden in a view.
  const v = queueView(BACKED_UP);
  eq('a large age is NOT coloured as danger', numberOf(v, 'oldest').tone, '');
  // the same restraint per row: 3 retries is stated, not judged
  eq('a row with retries states the count', v.rows[0].maxRetry, '3');
  eq('and a row with none leaves the cell empty, not 0', v.rows[1].maxRetry, '');

  // A missing count is no cell, or a dash. `0` would be a claim.
  const partial = queueView({ oldest_waiting_seconds: null, not_measured: NOT_MEASURED });
  eq('an absent depth has no Waiting cell, not 0', numberOf(partial, 'waiting'), undefined);
  eq('an absent retry count is a dash, not 0', metaOf(partial, 'retried'), 'retried —');
  eq('a present zero IS a zero', numberOf(queueView(EMPTY), 'waiting').value, '0');
  eq('and a response with no list at all draws no rows, rather than throwing',
    partial.rows.length, 0);

  // Unavailable: nothing at all. A stale or invented figure is worse than an empty panel.
  const gone = queueView(null, { unavailable: '이 서버 프로세스에 /admin/chain/queue 가 없습니다 (404).' });
  eq('unavailable draws no rows', gone.rows.length, 0);
  eq('and no number to hang a claim on', gone.numbers.length, 0);
  ok('and says why by name', /404/.test(gone.reason), gone.reason);
  const doc = makeDoc();
  const host = doc.createElement('div');
  new ChainQueuePanel(host, { doc }).render(null, { unavailable: 'HTTP 500' });
  eq('and nothing numeric reaches the screen', byClass(host, 'chain-queue-number').length, 0);
  eq('nor any row', rowsOf(host).length, 0);
  ok('but the reason does', /HTTP 500/.test(host.textContent), host.textContent);
}

// ═══ ④ a list that was CUT says it was cut ═════════════════════════════════════════
console.log('\n[4] truncation is stated, and only when it happened');
{
  const cut = queueView(BACKED_UP);
  ok('a capped read says so', cut.truncated.length > 0, cut.truncated);
  // lead b3a4334db: the route cuts LINES and says how many there are (`rows_scanned` is gone).
  eq('and says how many lines of how many, and the cap', cut.truncated, 'Showing 2 of 9 lines (cap 2).');

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
  eq('server order is preserved', v.rows.map(r => r.id.slice(0, 8)), ['bbbbbbbb', 'cccccccc']);
  eq('the id is abbreviated head8', v.rows[0].label, 'bbbbbbbb…');
  eq('several tables join into one cell', v.rows[0].tables, 'wafer_process, lot_master');
  eq('a transaction with no table named draws a dash, not blank',
    queueView({ ...BACKED_UP, waiting_transactions: [
      { transaction_id: 'x', rows: 1, tables: [], event_types: [], max_retry: 0,
        waiting_seconds: 5 }] }).rows[0].tables, '—');
  // 🔴 S-36. A RETROACTIVE ROW SAYS WHAT IT IS, IN THE SLOT THAT SAID 「—」. Its `tables` is
  //    empty by construction, so before this the operator saw a dash on exactly the row they
  //    could not otherwise identify. Scored by VALUE on both sides of the fork.
  eq('a retroactive row names its op, its requester and its params',
    queueView({ ...BACKED_UP, waiting_transactions: [
      { transaction_id: 'x', rows: 1, tables: [], event_types: [], max_retry: 0,
        waiting_seconds: 5,
        retroactive: [{ run_id: 'r1', op: 'enrichment_confirm', requested_by: 'kk980',
                        params: { rule: 'dt_frame' }, outbox_id: 12 }] }] }).rows[0].tables,
    'Retroactive · enrichment_confirm · kk980 · {"rule":"dt_frame"}');
  // ⚠️ AND THE OTHER SIDE OF THE FORK IS THE HALF THAT CAN GO WRONG SILENTLY: a row with no
  //    `retroactive` key must be BYTE-IDENTICAL to yesterday. The dash assertion above already
  //    covers the empty case; this covers a row that DOES name tables.
  eq('a row with no retroactive key still shows its tables, unchanged',
    queueView({ ...BACKED_UP, waiting_transactions: [
      { transaction_id: 'x', rows: 1, tables: ['wafer_process', 'lot_master'],
        event_types: [], max_retry: 0, waiting_seconds: 5 }] }).rows[0].tables,
    'wafer_process, lot_master');
  eq('the row count is carried', v.rows[0].rows, '40');
  eq('and the event count beside it, where it is not the row count', v.rows[0].eventsNote, '12 events');
  eq('NEGATIVE CONTROL: a line whose events are its rows says nothing more', v.rows[1].eventsNote, '');
  eq('the age is formatted, not raw seconds', v.rows[0].age, '1h 2m');

  const doc = makeDoc();
  const host = doc.createElement('div');
  new ChainQueuePanel(host, { doc }).render(BACKED_UP);
  eq('two rows are drawn', rowsOf(host).length, 2);
  eq('each row has the five columns the header declares', cellsOf(rowsOf(host)[0]).length, 5);
  eq('the header declares five (A; a line is a job or a transaction, lead b3a4334db)',
    byTag(host, 'TH').map((th) => th.textContent),
    ['Job / Transaction', 'Waiting', 'Tables', 'Rows', 'Drained by']);
  // A: no px widths, no inline alignment — the stylesheet reads each column by name.
  eq('no cell carries an inline width or alignment',
    walk(host).filter((n) => n.style && (n.style.width || n.style.textAlign)).length, 0);
  eq('every header cell names its column for the stylesheet',
    byTag(host, 'TH').map((th) => th.getAttribute('data-col')), ['tx', 'age', 'tables', 'rows', 'owners']);
  // lead 6fdd79d4e: the Retries column is gone, the count is not — a small badge when not 0.
  const retryOf = (row) => byClass(row, 'chain-queue-retry-badge').map((n) => n.textContent);
  eq('a row with retries carries 「retry N」', retryOf(rowsOf(host)[0]), ['retry 3']);
  eq('NEGATIVE CONTROL: a row with none carries no badge', retryOf(rowsOf(host)[1]), []);
  ok('the full id is on the chip for copying, not only the abbreviation',
    walk(host).some(n => n.title === 'bbbbbbbb-1111-2222-3333-444444444444'));
  ok('and the row carries it as data for anything that wants to select on it',
    rowsOf(host)[0].getAttribute('data-line-id') === 'bbbbbbbb-1111-2222-3333-444444444444');

  // an empty queue draws NO table -- an empty table with a header reads as "loading"
  const doc2 = makeDoc();
  const host2 = doc2.createElement('div');
  new ChainQueuePanel(host2, { doc: doc2 }).render(EMPTY);
  eq('an empty queue draws no table at all', byTag(host2, 'TABLE').length, 0);
  ok('and says so in one line', byClass(host2, 'chain-queue-empty').map((n) => n.textContent).join('') === 'Nothing waiting');
  // ...but the numbers are still there, because 「대기 없음」 is itself the answer (rule ①)
  eq('while the numbers stay', valueOf(host2, 'waiting'), '0');
}

// ═══ ⑤-J one retroactive job is one line (lead b3a4334db, server f843188e5) ══════════════
// The server folds a job's events by its run: the line carries `run_id` and `op`, and its
// `transaction_id` is null. Before this the chip drew that null — an empty identity cell.
console.log('\n[5J] one retroactive job is one line, named by its op and run');
{
  const JOB = { run_id: '9f8e7d6c5b4a39281706', op: 'chain_replay', transaction_id: null,
                events: 37, rows: 18500, tables: ['wafer_process'], event_types: ['UPDATE'],
                owners: ['chain'], max_retry: 0, waiting_seconds: 600, waiting_at: '2026-10-02 17:30:00' };
  const TX = BACKED_UP.waiting_transactions[1];
  const v = queueView({ ...BACKED_UP, waiting_transactions: [JOB, TX] });
  // two lines, op over the run head - nothing only a hover shows (lead 362f1a91d)
  eq('J1 a job line is named by its op over its run', v.rows[0].label, 'chain_replay\n9f8e7d6c…');
  eq('J2 and its id is the run', v.rows[0].id, JOB.run_id);
  eq('J3 its rows and its events are the server\'s, apart', [v.rows[0].rows, v.rows[0].eventsNote],
    ['18500', '37 events']);
  eq('J4 a transaction line beside it is as before', [v.rows[1].label, v.rows[1].id],
    ['cccccccc…', TX.transaction_id]);
  eq('J5 a job whose op the server could not name still shows its run',
    queueView({ ...BACKED_UP, waiting_transactions: [{ ...JOB, op: null }] }).rows[0].label, '9f8e7d6c…');

  const doc = makeDoc();
  const host = doc.createElement('div');
  new ChainQueuePanel(host, { doc }).render({ ...BACKED_UP, waiting_transactions: [JOB, TX] });
  const [jobRow] = rowsOf(host);
  const cellOf = (row, col) => [...cellsOf(row)].find((td) => td.getAttribute('data-col') === col);
  const chip = byClass(jobRow, 'tx-id-chip')[0];
  const rowsCell = cellOf(jobRow, 'rows');
  // the badge comes first so the number stays at the right edge of a right-aligned column
  eq('J6 the drawn job line: its chip, then the Rows cell as badge and number',
    [rowsOf(host).length, chip.textContent, rowsCell.children.map((n) => [n.className, n.textContent])],
    [2, 'chain_replay\n9f8e7d6c…', [['chain-queue-events-badge', '37 events'], ['', '18500']]]);
  eq('J6b NEGATIVE CONTROL: the transaction line beside it has no events badge',
    byClass(cellOf(rowsOf(host)[1], 'rows'), 'chain-queue-events-badge').length, 0);
  eq('J7 the full run id is on the chip and on the line', [chip.title, jobRow.getAttribute('data-line-id')],
    [JOB.run_id, JOB.run_id]);
}

// ═══ ⑥ formatAge — total, and the boundaries ═══════════════════════════════════════
console.log('\n[6] formatAge');
{
  eq('0', formatAge(0), '0s');
  eq('59', formatAge(59), '59s');
  eq('60', formatAge(60), '1m');
  eq('90', formatAge(90), '1m 30s');
  eq('3600', formatAge(3600), '1h');
  eq('3725.4 truncates, never rounds up past the real wait', formatAge(3725.4), '1h 2m');
  eq('86400', formatAge(86400), '1d');
  eq('90000', formatAge(90000), '1d 1h');
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
  const headOf = (h) => valueOf(h, 'waiting');
  ok('the second does not overwrite the first', headOf(h1) !== headOf(h2),
    `${headOf(h1)} / ${headOf(h2)}`);
  eq('the first still reads its own payload', rowsOf(h1).length, 0);
  eq('the second still reads its own', rowsOf(h2).length, 2);
  // re-rendering replaces rather than appends -- a panel that appended would show every
  // refresh ever made, stacked, and the newest would be at the bottom.
  p1.render(BACKED_UP);
  eq('a re-render replaces, it does not append', rowsOf(h1).length, 2);
  eq('and leaves exactly one number grid', byClass(h1, 'chain-queue-numbers').length, 1);
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
  eq('each bucket keeps its own age', v.byOwner[1].age, '1h 2m');

  // one owner is not a split
  const ONE = { ...OWNED, waiting_by_owner: [OWNED.waiting_by_owner[0]] };
  eq('two or more owners split', v.splitByOwner, true);
  eq('one owner does NOT split', queueView(ONE).splitByOwner, false);
  eq('and a server that sends no buckets at all splits nothing',
    queueView(BACKED_UP).splitByOwner, false);
  eq('...and draws no bucket', queueView(BACKED_UP).byOwner.length, 0);

  // per row
  eq('a row shows who empties it', v.rows[0].owners, ['chain']);
  eq('a row with two owners shows both', v.rows[1].owners, ['scheduler', 'unknown']);
  eq('a row the server did not name carries no owner, not chain',
    queueView({ ...OWNED, waiting_transactions: [
      { ...BACKED_UP.waiting_transactions[0] }] }).rows[0].owners, []);

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
  eq('...and a real zero is a zero', blockedOf(v, { no_progress_seconds: 0 }), '0s');

  // 🔴 NEGATIVE CONTROL. A bucket with no blocker draws NOTHING — an 「없음」 here is the
  //    same invented zero the whole file exists to prevent, and the server says so itself.
  eq('a bucket with blocked_by null carries no blocker', v.byOwner[0].blocked, null);
  eq('and a bucket that never had the field carries none either', v.byOwner[2].blocked, null);

  // 🔴 THE THIRD STATE. 「못 읽었다」 arrives as the SAME `blocked_by: null` as 「도는 것이
  //    없다」, because the server's `except` wrote that null too — and the panel's silence on
  //    null, which is right for the first, made the second invisible as well. The server now
  //    says which it is; these two say the panel keeps them apart.
  const stateOf = (over) => queueView({
    waiting_by_owner: [Object.assign({ owner: 'scheduler', waiting: 0,
      oldest_waiting_seconds: null, event_types: [], blocked_by: null }, over)],
  }).byOwner[0];
  eq('an unread retroactive read is carried as unknown',
    stateOf({ blocked_by_state: 'unknown' }).blockedState, 'unknown');
  eq('a read that answered is not unknown',
    stateOf({ blocked_by_state: 'ready' }).blockedState, 'ready');
  // ⚠️ 키가 없는 옛 서버는 «둘 중 어느 쪽도 아닙니다» — 빈 문자열이고, 화면은 아무것도
  //    안 그립니다. 없는 것을 `ready` 로 채우면 「읽었다」를 지어내는 것입니다.
  eq('an old server without the field claims neither', stateOf({}).blockedState, '');

  // ── and all of it reaches the screen ──
  const doc = makeDoc();
  const host = doc.createElement('div');
  new ChainQueuePanel(host, { doc }).render(OWNED);
  const owners = walk(host).filter(n => n.getAttribute && n.getAttribute('data-owner'));
  eq('three owner elements are drawn as three', new Set(owners.map(n => n.getAttribute('data-owner'))).size, 3);
  ok('chain\'s line says 5, not 8', /chain · waiting 5 /.test(host.textContent), host.textContent.slice(0, 120));
  ok('unknown appears on screen under its own name', /unknown · waiting 1 /.test(host.textContent));
  eq('exactly one blocked box is drawn', byClass(host, 'chain-queue-blocked').length, 1);
  ok('and it prints the tokens rather than a translation',
    /stalled/.test(host.textContent) && /never/.test(host.textContent));
  ok('the row owners reach the screen',
    walk(host).some(n => n.getAttribute && n.getAttribute('data-owners') === 'scheduler, unknown'));
  eq('one badge per owner, in the server\'s words',
    byClass(rowsOf(host)[1], 'chain-queue-owner-badge').map((n) => n.textContent), ['scheduler', 'unknown']);
  const unnamed = makeDoc();
  const unnamedHost = unnamed.createElement('div');
  new ChainQueuePanel(unnamedHost, { doc: unnamed }).render({ ...OWNED, waiting_transactions: [
    { ...BACKED_UP.waiting_transactions[1] }] });
  eq('an unnamed row draws a dash in Drained by, and no badge',
    [byClass(unnamedHost, 'chain-queue-owner-badge').length,
     cellsOf(rowsOf(unnamedHost)[0])[4].textContent], [0, ABSENT]);
  // the table did not grow a column — the overflow round measured that cost
  eq('the header still declares five', byTag(host, 'TH').length, 5);
  eq('and each row still has five cells', cellsOf(rowsOf(host)[0]).length, 5);

  const doc2 = makeDoc();
  const host2 = doc2.createElement('div');
  new ChainQueuePanel(host2, { doc: doc2 }).render(BACKED_UP);
  eq('a bucket-less response draws no owner strip', byClass(host2, 'chain-queue-owner-strip').length, 0);
  eq('and no blocked box', byClass(host2, 'chain-queue-blocked').length, 0);

  // 🔴 AND THE UNREAD CASE REACHES THE SCREEN. Drawing nothing was the whole defect:
  //    a failed read looked exactly like a quiet system. One box, one line.
  const UNREAD = { waiting_transactions: [], waiting_by_owner: [{ owner: 'scheduler', waiting: 0,
    oldest_waiting_seconds: null, event_types: [], blocked_by: null,
    blocked_by_state: 'unknown' }] };
  const doc3 = makeDoc();
  const host3 = doc3.createElement('div');
  new ChainQueuePanel(host3, { doc: doc3 }).render(UNREAD);
  eq('an unread blocker draws a box', byClass(host3, 'chain-queue-blocked').length, 1);
  ok('and the box says it is unknown rather than none',
    /Unknown/.test(byClass(host3, 'chain-queue-blocked-head')[0].textContent));

  // 🔴 NEGATIVE CONTROL, AND IT IS THE ONE THAT MATTERS. A quiet system must stay
  //    quiet — if this drew a box too, the new line would be the invented zero's twin.
  const QUIET = { waiting_transactions: [], waiting_by_owner: [{ owner: 'scheduler', waiting: 0,
    oldest_waiting_seconds: null, event_types: [], blocked_by: null,
    blocked_by_state: 'ready' }] };
  const doc4 = makeDoc();
  const host4 = doc4.createElement('div');
  new ChainQueuePanel(host4, { doc: doc4 }).render(QUIET);
  eq('a read that answered draws no box', byClass(host4, 'chain-queue-blocked').length, 0);

  // \u{1f534} S-12: 「이 아래 수가 틀렸을 수 있다」 REACHES THE SCREEN, and it is FIRST.
  //    Placed after the numbers it invalidates, an operator has already believed them.
  const QUEUE = (over) => ({ waiting_transactions: [], waiting_by_owner: [{
    owner: 'scheduler', waiting: 0, oldest_waiting_seconds: null, event_types: [],
    blocked_by: null, queue: Object.assign({ last_pickup_at: 'x',
      last_pickup_age_seconds: 3, picker_interval_seconds: 5,
      waiting_count: 0, waiting: [] }, over) }] });
  const drawn = (over) => {
    const d = makeDoc();
    const host = d.createElement('div');
    new ChainQueuePanel(host, { doc: d }).render(QUEUE(over));
    return host;
  };
  eq('a record failure is said on the screen',
    byClass(drawn({ record_failures: [1, 2] }), 'chain-queue-stale').length, 1);
  ok('and it names how many',
    /2/.test(byClass(drawn({ record_failures: [1, 2] }), 'chain-queue-stale')[0].textContent));
  // \u{1f534} THE NEGATIVE CONTROL IS THE ONE THAT MATTERS - a healthy queue must stay quiet,
  //    or this line is another invented zero wearing a warning's clothes.
  eq('an empty list says nothing',
    byClass(drawn({ record_failures: [] }), 'chain-queue-stale').length, 0);
  eq('and an older server that never sends it says nothing either',
    byClass(drawn({}), 'chain-queue-stale').length, 0);
  // It has to come BEFORE the numbers it invalidates — the four, and the pickup line.
  ok('it is drawn above the numbers it invalidates', (() => {
    const host = drawn({ record_failures: [1] });
    const classes = walk(host).map((n) => n.className || '').filter(Boolean);
    const stale = classes.indexOf('chain-queue-stale');
    return stale > -1 && stale < classes.indexOf('chain-queue-numbers')
      && stale < classes.indexOf('chain-queue-pickup');
  })());
}

// ═══ S-16: 「재시작하면 풀리나」 — 발신은 살아 있었고 «듣는 쪽»이 없었다 ═══════════════
// 🔴 실측: `loop_uptime_seconds` · `mapper_reload_age_seconds` 가 `/admin/chain/queue` 응답에
//    실리는데 읽는 자리가 소스 «0» · 번들 «0». 그 판단 근거는 지금까지 «큐가 1분 이상 막힌 뒤»
//    «로그 문장 속 글자»로만 나갔다 — 이미 멈춘 시스템의 로그를 읽는 사람만 물을 수 있었다.
// 🔴 이 블록이 재는 것은 «문구»가 아니라 «가름»이다. 규칙 ① 과 같은 자리에서:
//    `null`(한 번도 재적재 안 함)과 `0`(방금 함)은 «반대 사실»이고 같은 픽셀이면 안 된다.
{
  const base = {
    waiting: 0, running: [], loop_in_this_process: true,
    oldest_waiting_seconds: null, waiting_by_owner: [], retried_among_waiting: 0,
  };
  const restartOf = (extra) => metaOf(queueView({ ...base, ...extra }), 'restart');

  // 세 상태 — `logName` 과 같은 규율. 키가 «없으면» 안 그린다(옛 서버).
  eq('R1 an older server that sends neither key draws nothing', restartOf({}), '');
  ok('R2 the loop age is named once the keys arrive',
    restartOf({ loop_uptime_seconds: 90, mapper_reload_age_seconds: null }).includes('1m 30s'));

  // 🔴 R3/R4 ARE THE POINT, AND THEY ARE COMPARED TO EACH OTHER, NOT TO A FIXED STRING —
  //    so a copy edit cannot redden them and cannot silently collapse them either.
  const never = restartOf({ loop_uptime_seconds: 90, mapper_reload_age_seconds: null });
  const justNow = restartOf({ loop_uptime_seconds: 90, mapper_reload_age_seconds: 0 });
  ok('R3 「never reloaded」 and 「reloaded just now」 are NOT the same pixels', never !== justNow);
  ok('R4 ...and neither is empty, so they differ by content rather than by absence',
    never.length > 0 && justNow.length > 0);
  // 모름: 값이 못 읽히는 것은 「0」이 아니다.
  ok('R5 an unreadable loop age reads Unknown, never 0s',
    restartOf({ loop_uptime_seconds: 'x', mapper_reload_age_seconds: 0 }).includes('Unknown'));
  ok('R6 CONTROL: a real loop age is NOT Unknown — else R5 passes for the wrong reason',
    !restartOf({ loop_uptime_seconds: 90, mapper_reload_age_seconds: 0 }).includes('Loop Unknown'));

  // 🔴 R7 EXISTS BECAUSE R3 DID NOT DO WHAT IT CLAIMED. Deleting the explicit `null` branch
  //    was run as a mutant and R3 STAYED GREEN: `formatAge(null)` yields 모름, so the two
  //    strings still differed and the discrimination survived by accident rather than by
  //    the guard. But 모름 is the WRONG WORD here — the server's `null` means 「한 번도 재적재
  //    안 함」, which is a fact it KNOWS, not one it failed to read. Conflating a known
  //    absence with an unreadable value is the same collapse rule ① forbids, one word over.
  ok('R7 「never reloaded」 is a KNOWN fact, so it must not read Unknown',
    !restartOf({ loop_uptime_seconds: 90, mapper_reload_age_seconds: null }).includes('reloaded Unknown'));
}

// ═══ S-20: 「이 수들이 «언제» 것인가」 — 발신은 살아 있었고 «듣는 쪽»이 0 이었다 ═══
// 🔴 실측: `/admin/chain/queue` 가 `generated_at` 을 «항상» 싣는데(`server/main.py`, 이 응답의
//    나이·`oldest_waiting_seconds` 와 «같은 순간») 읽는 자리가 소스 «0» 이었다. 새로 고치지 않은
//    화면은 «그때»의 수를 «현재형»으로 말한다.
// 🔴 이 블록이 재는 것은 «문구»가 아니라 «가름»이다 — 옛 서버(키 없음)와 오늘 서버가 같은
//    픽셀이면 안 되고, 못 읽은 값이 «지어낸 시각»이 되어서도 안 된다.
// ⚠️ 라우트가 어드민 토큰 뒤(401)라 브라우저로 못 본다. 그래서 본문은 «픽스쳐»이고, 도달은
//    별도로 «번들 문자열»로 재다 — 그 둘이 이 줄의 증거 전부이고, 보고에 그렇게 적는다.
{
  const BODY = (over = {}) => Object.assign({
    waiting: 3, running: [], loop_in_this_process: true,
    oldest_waiting_seconds: 12, waiting_by_owner: [], retried_among_waiting: 0,
  }, over);
  const AT = '2026-09-07T09:30:00+00:00';
  const genOf = (over) => metaOf(queueView(BODY(over)), 'generated');

  // 세 상태 — `logName`·`restart` 와 «같은 규율».
  eq('G1 an older server that never sends the key draws nothing', genOf({}), '');
  // A: 「사람이 읽는 로컬 시각」 — the SERVER instant, drawn in the viewer's zone (server_time.js).
  ok('G2 the value is drawn once the key arrives: the server instant, in local time',
    genOf({ generated_at: AT }).includes(localStamp(AT)));
  // 🔴 G3 IS THE POINT. A screen that cannot read the stamp must say so; substituting a
  //    client clock here would make every stale panel look freshly measured, which is the
  //    exact failure this row exists to close.
  ok('G3 an unreadable stamp reads Unknown, never an invented time',
    genOf({ generated_at: null }).includes('Unknown'));
  ok('G4 CONTROL: a real stamp is NOT Unknown — else G3 passes for the wrong reason',
    !genOf({ generated_at: AT }).includes('Unknown'));
  ok('G5 an empty string is not a time either (it is neither null nor undefined)',
    genOf({ generated_at: '' }).includes('Unknown'));

  // 🔴 무회귀, AND IT IS THE WHOLE VIEW, NOT A SPOT CHECK. Adding the stamp must not move
  //    one other thing the panel already drew.
  const without = (v) => ({ ...v, meta: v.meta.filter((m) => m.key !== 'generated') });
  const withOut = without(queueView(BODY({})));
  const withIn = without(queueView(BODY({ generated_at: AT })));
  eq('G6 nothing else on the view moves when the stamp arrives',
    JSON.stringify(withOut), JSON.stringify(withIn));

  // 🔴 AND IT REACHES THE SCREEN. A field on the view model that nothing renders is the
  //    same defect one layer in — a sender with no listener.
  const drawnAs = (over) => {
    const d = makeDoc();
    const host = d.createElement('div');
    new ChainQueuePanel(host, { doc: d }).render(BODY(over));
    return host;
  };
  eq('G7 the stamp is on the screen, not only on the view model',
    byClass(drawnAs({ generated_at: AT }), 'chain-queue-meta-generated').length, 1);
  // 🔴 TOTAL ON PURPOSE. Indexing [0] directly THREW when the line was absent, and a
  //    harness that throws stops scoring — G9 and G10 never ran, so two different mutants
  //    (drop the line / collide with the pickup class) looked like the same finding.
  //    A mutant that throws is a hole, not a catch.
  ok('G8 ...carrying the server instant', (() => {
    const hit = byClass(drawnAs({ generated_at: AT }), 'chain-queue-meta-generated')[0];
    return !!hit && hit.textContent.includes(localStamp(AT));
  })());
  eq('G9 NEGATIVE CONTROL: an older server draws no such line at all',
    byClass(drawnAs({}), 'chain-queue-meta-generated').length, 0);
  // ⚠️ 이름 충돌. 집는 이의 「주기」가 `-basis` 를 이미 쓰고 있어, 한 이름이 두 뜻이 되면
  //    스타일이 둘 중 하나를 «조용히» 잘못 그린다.
  eq('G10 it does not land on the pickup line class',
    byClass(drawnAs({ generated_at: AT }), 'chain-queue-basis').length, 0);
}


// ═══ C-61: 「도는 체인 3」 이 「걸린 것 3」 과 «같은 픽셀»이었다 ═══════════════════════════
// 🔴 소유자 09-10: 「가짜 running 3개 남아있음」. 수는 그것을 말할 수 없다 — 가르는 것은 «나이»다.
// 🔴 총괄 4994c3afe · 78ebdcfc0 — the items come from ONE seat (`now_running`: chain rules,
//    retroactive runs, collectors, file ingestion) and each is ONE line of the `RunLines` part:
//    what · where · progress · elapsed · × where a cancel reaches. The count keeps its longest.
// 🔴 픽스처는 «셋이 서로 다른 답을 내야» 한다: 0초 · 12초 · 2,460초(41분), 그리고 × 는 하나만.
{
  const NOW_THREE = [
    { what: 'just_started', where: 'chain_worker', pid: 7, elapsed_seconds: 0,
      progress: { processed: null, total: 1 }, cancel: null },
    { what: 'warming_up', where: 'chain_worker', pid: 7, elapsed_seconds: 12, progress: null, cancel: null },
    { what: 'Recompute shown values (R3)', where: 'own_process', pid: 42, elapsed_seconds: 2460,
      progress: { processed: 50, total: 100 }, cancel: { run_id: 'run-9' } },
  ];
  const BODY = (over) => ({
    waiting: 0, oldest_waiting_seconds: null, waiting_by_owner: [], retried_among_waiting: 0,
    loop_seen_via: 'this_process', now_running: [], ...over,
  });
  const viewOf = (over) => queueView(BODY(over));
  const runOf = (over) => numberOf(viewOf(over), 'running');
  const cancelled = [];
  const drawn = (over) => {
    const d = makeDoc();
    const host = d.createElement('div');
    new ChainQueuePanel(host, { doc: d, onCancel: (c) => cancelled.push(c), confirm: () => true }).render(BODY(over));
    return host;
  };

  // ── the count keeps its meaning, and the longest age rides beside it ──
  const three = viewOf({ now_running: NOW_THREE });
  eq('C1 the count is the seat\'s items', runOf({ now_running: NOW_THREE }).value, '3');
  ok('C2 ...and says how old the oldest is, beside it', runOf({ now_running: NOW_THREE }).sub.includes('41m'),
    runOf({ now_running: NOW_THREE }).sub);
  // 🔴 C3 IS THE DISCRIMINANT: `[0]` and `max` agree on the server's order; reversed, they do not.
  eq('C3 「longest」 is the MAXIMUM, not whichever came first',
    runOf({ now_running: [...NOW_THREE].reverse() }), runOf({ now_running: NOW_THREE }));
  const ageless = runOf({ now_running: [{ what: 'r' }, { what: 'r2' }] });
  ok('C4 an entry with no age adds no 「longest」 at all', !ageless.sub.includes('longest'), ageless.sub);
  eq('C5 ...and the count of them is still drawn', ageless.value, '2');
  eq('C6 seen and nothing running is 0, with nothing under it', [runOf({}).value, runOf({}).sub], ['0', '']);

  // ── one line per item, in the server's order, through the one part ──
  eq('C7 every item has a line', three.runningRows.length, 3);
  eq('C8 ...titled what · where · pid, the server\'s words as they come',
    three.runningRows.map((r) => `${r.what.text} · ${r.detail.text}`),
    ['just_started · chain_worker · pid 7', 'warming_up · chain_worker · pid 7',
     'Recompute shown values (R3) · own_process · pid 42']);
  eq('C9 ...each beside its own elapsed time', three.runningRows.map((r) => r.progress.elapsed), ['0s', '12s', '41m']);
  eq('C10 a known total is a bar, an unknown one is not', three.runningRows.map((r) => r.progress.mode),
    ['text', 'text', 'bar']);
  eq('C11 × only where the seat names a run to cancel', three.runningRows.map((r) => r.cancel), [false, false, true]);
  eq('C12 a what that did not arrive is ABSENT, never the word "undefined"',
    viewOf({ now_running: [{ elapsed_seconds: 900 }] }).runningRows[0].what.text, ABSENT);

  // ── on the screen, not only in the view model ──
  const host = drawn({ now_running: NOW_THREE });
  eq('C13 each item is painted as a run line', byClass(host, 'run-line').length, 3);
  const xs = byClass(host, 'running-x');
  eq('C14 ...with one ×', xs.length, 1);
  (xs[0] && xs[0].listeners && xs[0].listeners.click || []).forEach((fn) => fn());
  eq('C15 pressing it asks the page to cancel that run by id', cancelled, [{ runId: 'run-9' }]);
  eq('C16 NEGATIVE CONTROL: nothing running paints no run line', byClass(drawn({}), 'run-line').length, 0);
  eq('C16a an unseen loop blinds the count, not the lines the seat did read',
    [valueOf(drawn({ now_running: NOW_THREE, loop_seen_via: null }), 'running'),
     byClass(drawn({ now_running: NOW_THREE, loop_seen_via: null }), 'run-line').length], [null, 3]);
  eq('C16b the Running number is its own cell, apart from those lines', '3',
    valueOf(drawn({ now_running: NOW_THREE }), 'running'));

  // 🔴 C17/C18: 「분 단위」 and `formatAge`'s unit switch read ONE constant.
  eq('C17 the constant IS the one formatAge switches on', '1m', formatAge(MINUTE_SECONDS));
  eq('C18 ...and one second under it is still seconds',
    `${MINUTE_SECONDS - 1}s`, formatAge(MINUTE_SECONDS - 1));
}

// ═══ ST: a run whose owner is gone must not draw like a running one (lead 8e331ca17) ═══════
// The fixture carries all three server words, so a count, an age or a motion that ignored
// `state` gives a different answer on EVERY assertion below — the oldest is the orphan.
{
  const MIXED = [
    { what: 'rule_a', where: 'chain_worker', pid: 7, elapsed_seconds: 30, progress: null, cancel: null, state: 'running' },
    { what: 'Recompute shown values (R3)', where: 'own_process', pid: 42, elapsed_seconds: 3000,
      progress: { processed: 10, total: 100 }, cancel: { run_id: 'run-1' }, state: 'orphaned' },
    { what: 'lot_master/collect', where: 'scheduler', pid: 9, elapsed_seconds: 600, progress: null, cancel: null, state: 'unknown' },
  ];
  const BODY = (items) => ({ waiting: 0, oldest_waiting_seconds: null, waiting_by_owner: [],
    retried_among_waiting: 0, loop_seen_via: 'this_process', now_running: items });
  const v = queueView(BODY(MIXED));
  const run = numberOf(v, 'running');
  eq('ST1 only a running item is counted', run.value, '1');
  ok('ST2 ...and only its age is the longest (not the orphan\'s 50m)', run.sub.includes('30s') && !run.sub.includes('50m'), run.sub);
  eq('ST3 every item still has its line', v.runningRows.length, 3);
  eq('ST4 each line carries the server\'s state word as it comes', v.runningRows.map((r) => r.stateName && r.stateName.text),
    ['running', 'orphaned', 'unknown']);
  eq('ST5 only the running line moves', v.runningRows.map((r) => r.moving), [true, false, false]);
  eq('ST6 × is still where the seat names a run, whatever the state', v.runningRows.map((r) => r.cancel), [false, true, false]);
  const d = makeDoc();
  const host = d.createElement('div');
  new ChainQueuePanel(host, { doc: d }).render(BODY(MIXED));
  eq('ST7 drawn: the two that do not run are painted as not moving',
    byClass(host, 'run-line').filter((n) => String(n.className).split(/\s+/).includes('is-waiting')).length, 2);
  ok('ST8 drawn: the words reach the screen', ['running', 'orphaned', 'unknown'].every((w) => host.textContent.includes(w)), host.textContent.slice(0, 200));
  eq('ST9 all three orphaned: no Running is 0, not blind', numberOf(queueView(BODY(MIXED.map((m) => ({ ...m, state: 'orphaned' })))), 'running').value, '0');
  const old = queueView(BODY(MIXED.map(({ state, ...m }) => m)));
  eq('ST10 an older server\'s items (no state key) are all counted, as before', numberOf(old, 'running').value, '3');
  eq('ST11 ...and all move, with no state word invented', [old.runningRows.map((r) => r.moving), old.runningRows.map((r) => r.stateName)],
    [[true, true, true], [null, null, null]]);
}

// ═══ X: a × on every queue line (lead d32261987, owner 10-08) ═══════════════════════════════
// The server adds `cancel: {key}` to each line; a line with a key goes to POST /admin/chain/queue/cancel, a
// line with only `run_id` (a server before the queue's ×) goes the run's own way, a line with neither has no ×.
// The fixture holds all three on both lists, and one line with a key AND a run id - so «key first» is measured.
const SUBJECT = new URL('../src/chain_queue_panel.js', import.meta.url);
const { fetchFailureLine } = await import('../src/config_resolve_view.js');
async function xSuite(m, say) {
  const BODY = {
    waiting: 3, oldest_waiting_seconds: 30, waiting_by_owner: [], retried_among_waiting: 0, loop_seen_via: 'this_process',
    waiting_transactions: [
      { transaction_id: 'aaaaaaaa-1111', events: 12, rows: 40, tables: ['wafer_process'], waiting_seconds: 30,
        cancel: { key: 'tx:aaaaaaaa-1111' } },
      { run_id: 'run-7', op: 'recompute', transaction_id: null, events: 3, rows: 3, tables: [], waiting_seconds: 20,
        cancel: { key: 'run:run-7', run_id: 'run-7' } },
      { transaction_id: 'cccccccc-1111', events: 1, rows: 1, tables: ['lot_master'], waiting_seconds: 10 },
    ],
    now_running: [
      { what: 'rule_a', where: 'chain_worker', pid: 7, elapsed_seconds: 5, progress: null, cancel: { key: 'group:5' } },
      { what: 'Recompute shown values (R3)', where: 'own_process', pid: 42, elapsed_seconds: 60,
        progress: { processed: 1, total: 2 }, cancel: { run_id: 'run-9' } },
      { what: 'lot_master/collect', where: 'scheduler', pid: 9, elapsed_seconds: 9, progress: null, cancel: null },
    ],
  };
  const seat = (body, answer = true) => {
    const d = makeDoc();
    const host = d.createElement('div');
    const asked = [];
    const got = [];
    const copied = [];
    new m.ChainQueuePanel(host, { doc: d, onCancel: (c) => got.push(c), confirm: (t) => { asked.push(t); return answer; },
      copy: (id, label) => copied.push([id, label]), onRefresh: () => refreshed.push(1) }).render(body);
    return { host, asked, got, copied };
  };
  const press = (node) => (node && node.listeners.click || []).forEach((fn) => fn());
  const rowXs = (host) => rowsOf(host).map((tr) => byClass(tr, 'running-x')[0] || null);
  const runXs = (host) => byClass(host, 'run-line').map((l) => byClass(l, 'running-x')[0] || null);
  const s = seat(BODY);
  say('X1 every line the server gave a cancel has a ×, on both lists',
    same(rowXs(s.host).map(Boolean), [true, true, false]) && same(runXs(s.host).map(Boolean), [true, true, false]),
    JSON.stringify([rowXs(s.host).map(Boolean), runXs(s.host).map(Boolean)]));
  press(rowXs(s.host)[0]);
  say('X2 a waiting line\'s ×: asked once with its events, then the page gets that line\'s key',
    same(s.asked, ['Skip 12 events?']) && same(s.got, [{ key: 'tx:aaaaaaaa-1111' }]), JSON.stringify([s.asked, s.got]));
  const no = seat(BODY, false);
  press(rowXs(no.host)[0]);
  say('X3 declined: nothing reaches the page', no.asked.length === 1 && no.got.length === 0, JSON.stringify(no.got));
  const both = seat(BODY);
  press(rowXs(both.host)[1]);
  say('X4 a line that also names a run hands its key, not the run id', same(both.got, [{ key: 'run:run-7' }]),
    JSON.stringify(both.got));
  const run = seat(BODY);
  press(runXs(run.host)[0]);
  say('X5 a running line with a key hands its key, asked without a count',
    same(run.asked, ['Skip this line?']) && same(run.got, [{ key: 'group:5' }]), JSON.stringify([run.asked, run.got]));
  const old = seat(BODY);
  press(runXs(old.host)[1]);
  say('X6 a server before the queue\'s × (run id only): the run\'s id, as before', same(old.got, [{ runId: 'run-9' }]),
    JSON.stringify(old.got));
  const bare = seat({ ...BODY, waiting_transactions: BODY.waiting_transactions.map(({ cancel, ...t }) => t) });
  say('X7 a table with no × on any line keeps its five columns', byTag(bare.host, 'TH').length === 5
    && rowXs(bare.host).every((x) => !x), String(byTag(bare.host, 'TH').length));
  const sent = [];
  const answer = (status, body) => async (url, init) => {
    sent.push({ url, method: init.method, body: init.body });
    return { ok: status < 300, status, headers: { get: () => '' }, json: async () => body };
  };
  // The contract's answers (lead be5457365): 200 {skipped_events}, a key no longer waiting 200 with `already`, a
  // malformed key 422; no 404.
  const done = await m.skipLine('tx:aaaaaaaa-1111', { adminFetch: answer(200, { skipped_events: 12 }), apiBase: 'http://box' });
  const gone = await m.skipLine('tx:old', { adminFetch: answer(200, { skipped_events: 0, already: 'processed' }) });
  say('X8 the key goes as POST /admin/chain/queue/cancel {key}; a 200 is done, a key already gone too',
    done.ok === true && gone.ok === true && same(sent[0], { url: 'http://box/admin/chain/queue/cancel', method: 'POST',
      body: JSON.stringify({ key: 'tx:aaaaaaaa-1111' }) }), JSON.stringify([done, gone, sent[0]]));
  const words = [];
  for (const already of ['processed', 'set_aside', 'gone']) {
    words.push((await m.skipLine('tx:old', { adminFetch: answer(200, { skipped_events: 0, already }) })).already);
  }
  say('XA a line that had already stopped says what became of it in a word; a line that was waiting says none',
    same(words, ['Already ran', 'Already set aside', 'Gone']) && done.already === '', JSON.stringify([words, done.already]));
  const refused = await m.skipLine('k', { adminFetch: answer(422, { detail: 'Not a queue line key' }) });
  const away = await m.skipLine('k', { adminFetch: async () => { throw new Error('offline'); } });
  say('X9 refused: the server\'s sentence, with its status; unreachable: the unreachable line',
    refused.ok === false && refused.line === 'Not a queue line key (HTTP 422)'
      && away.ok === false && away.line === fetchFailureLine(null, 'Cancel refused'), JSON.stringify([refused, away]));
  // A line's id is drawn short and copied in full on a press, through the page's one copy (lead 421191402).
  const chips = (host) => rowsOf(host).map((tr) => byClass(tr, 'tx-id-chip')[0]);
  const c = seat(BODY);
  press(chips(c.host)[0]);
  press(chips(c.host)[1]);
  say('K1 pressing a line\'s id hands the page the full id and its kind',
    same(c.copied, [['aaaaaaaa-1111', 'Transaction ID'], ['run-7', 'Run ID']]), JSON.stringify(c.copied));
  say('K2 the id is still drawn short, with the full id on hover',
    chips(c.host)[0].textContent === 'aaaaaaaa…' && chips(c.host)[0].title === 'aaaaaaaa-1111',
    JSON.stringify([chips(c.host)[0].textContent, chips(c.host)[0].title]));
  // A one-row line: the server words its transaction cell and carries the row as `outbox_id` (lead 6c678dd13).
  const one = seat({ ...BODY, waiting_transactions: [{ transaction_id: '(no tx · outbox#42)', outbox_id: 42, events: 1,
    rows: 1, tables: ['lot_master'], waiting_seconds: 5 }] });
  press(chips(one.host)[0]);
  say('K3 a one-row line copies its outbox id, named so, not its words',
    same(one.copied, [['42', 'Outbox ID']]), JSON.stringify(one.copied));
  // Refresh reads the queue alone again; the page owns the read (lead 0eadab810).
  refreshed.length = 0;
  const r = seat(BODY);
  const down = seat(null);
  press(byClass(r.host, 'chain-queue-refresh')[0]);
  press(byClass(down.host, 'chain-queue-refresh')[0]);
  const d2 = makeDoc();
  const none = d2.createElement('div');
  new m.ChainQueuePanel(none, { doc: d2 }).render(BODY);
  say('Y1 Refresh, read or not, asks the page for the queue once a press; no page read given, no button',
    refreshed.length === 2 && byClass(none, 'chain-queue-refresh').length === 0
      && byClass(byClass(r.host, 'chain-queue-meta')[0] || r.host, 'chain-queue-refresh').length === 1,
    JSON.stringify([refreshed.length, byClass(none, 'chain-queue-refresh').length]));
  // The chain state, one function for both queues (lead 248ae20cd): each token, its one line, its tone.
  const whys = STATES.map((s) => m.chainStateWhy(s.chain_state));
  say('S1 each state says its why in the lead\'s order, and waiting and done say none',
    same(whys, STATES.map((s) => s.why)), JSON.stringify(whys));
  const nulls = [
    m.chainStateWhy({ state: 'stalled', why: { stage: 'a', moved_seconds: 5, elapsed_seconds: 6, stalled_on: null } }),
    m.chainStateWhy({ state: 'retrying', why: { attempt: 1, cap: 3, last_failure: null } }),
    m.chainStateWhy({ state: 'running', why: { stage: 'a', moved_seconds: null, elapsed_seconds: 6 } })];
  say('S2 a field the server leaves null is left out, never drawn as a word', same(nulls, ['a · moved 5s ago · 6s',
    'attempt 1/3', 'a · 6s']), JSON.stringify(nulls));
  const sd = makeDoc();
  const cells = STATES.map((s) => m.chainStateCell(sd, s.chain_state));
  const drawn = cells.map((c) => {
    const tag = byClass(c, 'tag')[0];
    const why = byClass(c, 'queue-line-state-why')[0];
    return [tag && tag.textContent, tag && tag.getAttribute('data-tone'), why ? why.textContent : '', why ? why.getAttribute('title') || '' : ''];
  });
  say('S3 the cell draws the token on a tag with its tone, then its why once, whole in a title',
    same(drawn, STATES.map((s) => [s.chain_state.state, s.tone, s.why, s.why])), JSON.stringify(drawn));
  const blank = m.chainStateCell(sd, null);
  say('S4 no state is a dash, with no line', byClass(blank, 'tag')[0].textContent === ABSENT
    && byClass(blank, 'queue-line-state-why').length === 0, blank.textContent);
  const odd = [m.chainStateWhy({ state: 'waiting', why: { waiting_seconds: 5, unexpected_status: 'SKIPPED' } }),
    m.chainStateWhy({ state: 'done', why: { unexpected_status: 'ERROR' } })];
  say('S5 a waiting or done row in a status the server did not expect says that status', same(odd,
    ['status SKIPPED', 'status ERROR']), JSON.stringify(odd));
  // The admin's lines (lead 10-08 ①): under the Waiting cell's age, what chainStateCell draws; a line without one, none.
  const shape = (n) => walk(n).map((c) => [String(c.className || ''), c.getAttribute('data-tone'), c.getAttribute('title'),
    c.children.length ? '' : c._text].join('/')).join('|');
  const lines = seat({ ...BODY, waiting_transactions: [...STATES.map((st, i) => ({ transaction_id: `tx-${i}`, events: 1,
    rows: 1, tables: ['t'], waiting_seconds: 30, chain_state: st.chain_state })),
  { transaction_id: 'tx-none', events: 1, rows: 1, tables: ['t'], waiting_seconds: 30 }] });
  const ages = rowsOf(lines.host).map((tr) => tr.children.find((td) => td.getAttribute('data-col') === 'age'));
  const inAge = ages.map((td) => (td ? td.children.map(shape).join('+') : 'no age cell'));
  const wantAge = [...STATES.map((st) => shape(m.chainStateCell(makeDoc(), st.chain_state))), ''];
  say('S6 each admin line\'s Waiting cell holds its age, then exactly what chainStateCell draws; no state, no cell',
    same(inAge, wantAge) && ages.every((td) => td && td._text === '30s'), JSON.stringify(inAge));
  // The slot process a line runs in (lead, slot 422d075c7): its pid, the one an operator kills, under the state's why.
  const pidLines = (n) => byClass(n, 'queue-line-slot-pid').map((x) => x.textContent);
  const running = STATES.find((st) => st.chain_state.state === 'running').chain_state;
  const withPid = m.chainStateCell(makeDoc(), running, 4242);
  const slotted = seat({ ...BODY, waiting_transactions: [
    { transaction_id: 'tx-slot', events: 1, rows: 1, tables: ['t'], waiting_seconds: 30, chain_state: running, slot_pid: 4242 },
    { transaction_id: 'tx-free', events: 1, rows: 1, tables: ['t'], waiting_seconds: 30, chain_state: running, slot_pid: null }] });
  const slotOf = (tr) => pidLines(tr.children.find((td) => td.getAttribute('data-col') === 'age'));
  say('S7 a line run in a slot says «slot pid N» last in its state cell, the admin\'s line too; a line without one says nothing',
    same(pidLines(withPid), ['slot pid 4242']) && withPid.children[withPid.children.length - 1].textContent === 'slot pid 4242'
      && pidLines(m.chainStateCell(makeDoc(), running)).length === 0
      && pidLines(m.chainStateCell(makeDoc(), running, null)).length === 0
      && same(rowsOf(slotted.host).map(slotOf), [['slot pid 4242'], []]),
    JSON.stringify([pidLines(withPid), rowsOf(slotted.host).map(slotOf)]));
}
const STATES = JSON.parse(readFileSync(new URL('./fixtures/chain_states.json', import.meta.url), 'utf8')).states;
const refreshed = [];
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const X_NAMES = [];
await xSuite(await import('../src/chain_queue_panel.js'), (name, cond, detail) => { X_NAMES.push(name); ok(name, cond, detail); });
{
  const { loadWithProbe } = await import('./lib/probe.mjs');
  const { scoreMutants } = await import('./lib/mutation_scorer.mjs');
  const swap = (from, to) => (t) => { if (!t.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`); return t.split(from).join(to); };
  const MUTANTS = [
    { id: 'XM1', what: 'a key is not read', catches: 'X1',
      mutate: swap("  if (c.key != null && String(c.key) !== '') return Object.freeze({ key: String(c.key) });\n", '') },
    { id: 'XM2', what: 'a run id wins over the key', catches: 'X4',
      mutate: swap("  if (c.key != null && String(c.key) !== '')", "  if (!c.run_id && c.key != null && String(c.key) !== '')") },
    { id: 'XM3', what: 'no question is asked', catches: 'X3',
      mutate: swap('if (skip && this.confirm(skip.question)) this.onCancel(skip.cancel);', 'if (skip) this.onCancel(skip.cancel);') },
    { id: 'XM4', what: 'the question does not say how many', catches: 'X2',
      mutate: swap("`Skip ${unitText(countText(events), 'event')}?`", "'Skip this line?'") },
    { id: 'XM5', what: 'the × column always stands', catches: 'X7',
      mutate: swap('const act = rows.some((r) => r.skip);', 'const act = true;') },
    { id: 'XM6', what: 'the POST carries no key', catches: 'X8', mutate: swap('body: JSON.stringify({ key })', 'body: JSON.stringify({})') },
    { id: 'XM7', what: 'a refusal says a fixed word, not the server\'s sentence', catches: 'X9',
      mutate: swap('line: await retroFailureLine(res, failureFactOf(res), CANCEL_REFUSED)', 'line: CANCEL_REFUSED') },
    { id: 'XM8', what: 'a running line\'s × goes nowhere', catches: 'X5',
      mutate: swap('onCancel: (id) => this._skip(skips.get(id))', 'onCancel: () => {}') },
    { id: 'XM10', what: 'a line that had already stopped says nothing', catches: 'XA',
      mutate: swap("      return { ok: true, already: already ? ALREADY[already] || String(already) : '' };", "      return { ok: true, already: '' };") },
    { id: 'XM9', what: 'a run id alone is not read', catches: 'X6',
      mutate: swap('  if (c.run_id) return Object.freeze({ runId: String(c.run_id) });\n', '') },
    { id: 'KM1', what: 'a press copies the short label', catches: 'K1', mutate: swap('this.copy(r.id, r.idLabel)', 'this.copy(r.label, r.idLabel)') },
    { id: 'KM2', what: 'a run id is called a transaction id', catches: 'K1', mutate: swap("idLabel: 'Run ID'", "idLabel: 'Transaction ID'") },
    { id: 'KM3', what: 'the chip draws the full id', catches: 'K2', mutate: swap('chip.textContent = r.label;', 'chip.textContent = r.id;') },
    { id: 'KM4', what: 'a one-row line copies its words', catches: 'K3',
      mutate: swap('  if (!run && t.outbox_id != null) {', '  if (false) {') },
    { id: 'YM1', what: 'Refresh asks nothing', catches: 'Y1', mutate: swap("btn.addEventListener('click', () => this.onRefresh());", '') },
    { id: 'YM2', what: 'a queue that could not be read has no Refresh', catches: 'Y1',
      mutate: swap('      const again = this._refresh();\n      if (again) this.root.appendChild(again);\n', '') },
    { id: 'SM1', what: 'running does not say when it last moved', catches: 'S1',
      mutate: swap('    running: [w.stage, moved && `moved ${moved} ago`, formatAge(w.elapsed_seconds)],', '    running: [w.stage, formatAge(w.elapsed_seconds)],') },
    { id: 'SM2', what: 'a null field is drawn', catches: 'S2',
      mutate: swap("parts.filter((p) => p !== null && p !== undefined && p !== '')", "parts.filter((p) => p !== undefined && p !== '')") },
    { id: 'SM3', what: 'stalled loses its tone', catches: 'S3', mutate: swap(" stalled: 'warn',", '') },
    { id: 'SM4', what: 'a cut line keeps no title', catches: 'S3', mutate: swap("    said.setAttribute('title', why);\n", '') },
    { id: 'SM5', what: 'an unexpected status is not said', catches: 'S5',
      mutate: swap("    waiting: [w.unexpected_status && `status ${w.unexpected_status}`],\n", '') },
    { id: 'SM6', what: 'the admin line draws no state', catches: 'S6',
      mutate: swap('      if (r.chainState) tdAge.appendChild(chainStateCell(doc, r.chainState, r.slotPid));\n', '') },
    { id: 'SM7', what: 'waiting for a table says nothing of the table', catches: 'S1',
      mutate: swap('    waiting_for_table: [w.table && `waiting for ${w.table}`],\n', '') },
    { id: 'SM8', what: 'the slot pid is not drawn', catches: 'S7',
      mutate: swap("    cell.appendChild(line(doc, 'meta queue-line-slot-pid', `slot pid ${slotPid}`));\n", '') },
    { id: 'SM9', what: 'the admin line does not hand over its slot pid', catches: 'S7',
      mutate: swap('chainStateCell(doc, r.chainState, r.slotPid)', 'chainStateCell(doc, r.chainState)') },
    { id: 'SM10', what: 'a line without a slot pid says «slot pid null»', catches: 'S7',
      mutate: swap("  if (slotPid !== null && slotPid !== undefined && slotPid !== '') {", '  if (true) {') },
  ];
  const scored = await scoreMutants(MUTANTS, async (mu) => {
    const m = (await loadWithProbe(SUBJECT.pathname.replace(/^\/([A-Za-z]:)/, '$1'), { mutate: mu.mutate })).module;
    const got = [];
    let ran = 0;
    await xSuite(m, (name, cond) => { ran += 1; if (!cond) got.push(name); });
    return { failures: got, ran };
  }, { baselineRan: X_NAMES.length, baselineNames: X_NAMES, title: '\n  [mutants] - each must be caught by the check it names.' });
  pass += MUTANTS.length - scored.wrong;
  for (let i = 0; i < scored.wrong; i += 1) failures.push(`mutant verdict ${i + 1}`);
}

// The panel says how long since its screen last read the queue (owner 10-11 Q): the age handed in, its first line.
{
  const doc = makeDoc();
  const host = doc.createElement('div');
  const panel = new ChainQueuePanel(host, { doc });
  panel.render(EMPTY, { age: 'Read 7 s ago' });
  const first = host.children[0] && host.children[0].children[0];
  const aged = first && String(first.className || '').includes('chain-queue-read-age') ? first.textContent : '';
  panel.render(EMPTY);
  ok('QA2 the age the screen hands it is the panel\'s first line; none handed, none drawn',
    aged === 'Read 7 s ago' && !byClass(host, 'chain-queue-read-age').length, JSON.stringify([aged]));
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
