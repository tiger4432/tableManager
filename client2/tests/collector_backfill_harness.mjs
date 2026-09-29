// COLLECTOR BACKFILL — the Auto Update row's Backfill cell (lead 09f0be40f), scored.
//
// The subject is imported (owner 2026-09-02: 잘라쓰기 하니스 절대 금지). What is scored:
//   ① the window's three states: declared -> on · null -> off with the reason · no key -> no button
//   ② this row's line is THIS collector's latest run, and its words come from buildRunsView
//   ③ the cell draws what the page keeps (open · typed · busy · refused) and escapes it
// Run: node client2/tests/collector_backfill_harness.mjs
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import * as BASELINE from '../src/collector_backfill.js';
import { backfillCellHtml, backfillLineClass } from '../src/admin_rows.js';

const SRC_PATH = fileURLToPath(new URL('../src/collector_backfill.js', import.meta.url));
let passed = 0;
let failed = 0;
function ok(name, cond, saw) {
  if (cond) { passed++; console.log(`  ok   ${name}`); }
  else { failed++; console.log(`  FAIL ${name}${saw === undefined ? '' : `  saw: ${JSON.stringify(saw)}`}`); }
}
function die(msg) { console.log(`HARNESS FAILURE: ${msg}`); console.log(`ASSERTIONS ${passed} ${failed + 1}`); process.exit(1); }

const X = BASELINE;
const COL = { table_name: 'lot_master', script_name: 'daily.py', window: '1d' };
const NAMES = { running: 'Running', done: 'Done', failed: 'Failed' };
const RUNS = { state_names: NAMES, runs: [
  { op: 'collector_backfill', params: { collector: 'other_table/daily.py' }, state: 'running', processed_rows: 8, total_rows: 9 },
  { op: 'ledger_backfill', params: { collector: 'lot_master/daily.py' }, state: 'running', processed_rows: 1, total_rows: 2 },
  { op: 'collector_backfill', params: { collector: 'lot_master/daily.py' }, state: 'running', processed_rows: 3, total_rows: 7 },
  { op: 'collector_backfill', params: { collector: 'lot_master/daily.py' }, state: 'failed', processed_rows: 1, total_rows: 7,
    error: 'the file collected for 2026-09-20 00:00 (KST) failed to ingest (x.csv) - fix it, then start again from 2026-09-20 00:00' },
] };
const only = (run) => ({ state_names: NAMES, runs: [run] });
const PICKUP = { op: 'collector_backfill', params: { collector: 'lot_master/daily.py', start: '2026-09-01' },
  state: 'failed', processed_rows: 3, total_rows: 7, next_start: '2026-09-21 06:00:00' };

console.log('\n── A. THE WINDOW\'S THREE STATES ─────────────────────────────');
{
  const on = X.collectorBackfillView(COL, null);
  ok('A1 a declared window turns the button on, titled with that window',
    on.show && on.offReason === '' && on.title.includes('1d'), on);
  const off = X.collectorBackfillView({ ...COL, window: null }, null);
  ok('A2 no declared window turns it off with the reason the lead wrote',
    off.show && off.offReason === 'Declare # window: to backfill', off);
  const blank = X.collectorBackfillView({ ...COL, window: '   ' }, null);
  ok('A3 a blank declaration is no declaration', blank.offReason === X.BACKFILL_WORDS.offTitle, blank);
  const old = X.collectorBackfillView({ table_name: 't', script_name: 'd.py' }, null);
  ok('A4 an older record without the key draws no button - a declared collector is never told to declare',
    old.show === false && backfillCellHtml({ view: old }) === '', old);
  ok('A5 the key is the operation\'s own param shape <table>/<script.py>', on.key === 'lot_master/daily.py', on.key);
}

console.log('\n── B. THIS ROW\'S LINE IS THIS COLLECTOR\'S LATEST RUN ───────────');
{
  const v = X.collectorBackfillView(COL, RUNS);
  ok('B1 another collector\'s run and another operation\'s run are not this row\'s', v.line && !v.line.text.includes('8/9')
    && !v.line.text.includes('1/2'), v.line);
  ok('B2 the latest of this collector\'s runs (the list is newest first) - in flight, with N/M days',
    v.line && v.line.text === 'Running · 3/7 days' && v.line.tone === 'live', v.line);
  const failedV = X.collectorBackfillView(COL, only(RUNS.runs[3]));
  ok('B3 a failed run is red and says the server\'s sentence naming the day, as it came',
    failedV.line.tone === 'danger' && failedV.line.text.includes(RUNS.runs[3].error) && failedV.line.text.startsWith('Failed'),
    failedV.line);
  const doneV = X.collectorBackfillView(COL, only({ op: 'collector_backfill', params: { collector: 'lot_master/daily.py' },
    state: 'done', processed_rows: 7, total_rows: 7, result_sentence: 'days 7 · days collected 7' }));
  ok('B4 a finished run says done with its result sentence', doneV.line.tone === 'done'
    && doneV.line.text === 'Done · 7/7 days · days 7 · days collected 7', doneV.line);
  ok('B5 no runs read yet is no line (not an empty run)', X.collectorBackfillView(COL, null).line === null);
  const noTotal = X.collectorBackfillView(COL, only({ op: 'collector_backfill', params: { collector: 'lot_master/daily.py' },
    state: 'running', processed_rows: null, total_rows: null }));
  ok('B6 a run with no total yet draws no day count - never 0/0', noTotal.line.text === 'Running', noTotal.line);
  ok('B7 the line\'s class is one spelling for the cell and the poll', backfillLineClass({ tone: 'danger' }) === 'au-backfill-line is-danger'
    && backfillLineClass(null) === 'au-backfill-line');
  // 🔴 TEXT IS THE SUBJECT: no run state is compared here — buildRunsView is the one seat.
  const src = readFileSync(SRC_PATH, 'utf8');
  ok('B8 this file compares no run state word', !/[!=]==\s*'(running|done|failed|queued|cancelled|cancelling|cancel_requested)'/.test(src)
    && src.includes('buildRunsView('));
}

console.log('\n── C. THE CELL DRAWS WHAT THE PAGE KEEPS ─────────────────────');
{
  const view = X.collectorBackfillView(COL, RUNS);
  const closed = backfillCellHtml({ view });
  ok('C1 closed: the button with its own title, no date entry', closed.includes('btn-backfill"')
    && closed.includes('title="Backfill day by day (# window: 1d)"') && !closed.includes('au-backfill-start'), closed);
  const open = backfillCellHtml({ view, open: true, value: '2026-09-20' });
  ok('C2 open: the date entry keeps what was typed, with Start and Cancel', open.includes('value="2026-09-20"')
    && open.includes('placeholder="YYYY-MM-DD"') && open.includes('btn-backfill-start') && open.includes('btn-backfill-cancel'), open);
  ok('C3 busy: Start is off while the request is out', /btn-backfill-start"\s*disabled/.test(backfillCellHtml({ view, open: true, busy: true })));
  const refused = backfillCellHtml({ view, open: true, failure: "start '2099-01-01' is not in the past (KST)" });
  ok('C4 a refusal stays on the row as the server said it', refused.includes('au-backfill-refusal')
    && (refused.includes('start &#39;2099-01-01&#39; is not in the past (KST)')
      || refused.includes("start '2099-01-01' is not in the past (KST)")), refused);
  const hostile = backfillCellHtml({ view, open: true, value: '"><img src=x onerror=alert(1)>', failure: '<b>x</b>' });
  ok('C5 typed text and the server sentence are escaped', !hostile.includes('<img') && !hostile.includes('<b>x</b>'), hostile);
  ok('C6 the run line carries its collector key for the poll', closed.includes('data-backfill-key="lot_master/daily.py"'));
}

console.log('\n── D. START IS WHERE THE LAST RUN STOPPED (lead 75bac3964) ───────');
{
  // next_start is NOT params.start + processed days here, on purpose: a screen that counted days
  // itself would land on 2026-09-04, and the server said 2026-09-21 06:00:00.
  const picked = X.collectorBackfillView(COL, only(PICKUP));
  ok('D1 the field is the latest run\'s next_start as the server wrote it',
    picked.nextStart === PICKUP.next_start
    && backfillCellHtml({ view: picked, open: true }).includes(`value="${PICKUP.next_start}"`), picked.nextStart);
  const oldDone = X.collectorBackfillView(COL, only({ ...PICKUP, next_start: null }));
  ok('D2 null is an empty field', oldDone.nextStart === ''
    && backfillCellHtml({ view: oldDone, open: true }).includes('value=""'), oldDone.nextStart);
  ok('D3 a run still going (the server says null, or nothing) is an empty field',
    X.collectorBackfillView(COL, RUNS).nextStart === ''
    && X.collectorBackfillView(COL, only({ ...RUNS.runs[2], next_start: null })).nextStart === '');
  ok('D4 no run of this collector in the list is an empty field',
    X.collectorBackfillView(COL, only(RUNS.runs[0])).nextStart === '' && X.collectorBackfillView(COL, null).nextStart === '');
  const typed = backfillCellHtml({ view: picked, open: true, value: '2026-09-10' });
  const emptied = backfillCellHtml({ view: picked, open: true, value: '' });
  ok('D5 what the operator typed - even emptied - stays when the list comes again',
    typed.includes('value="2026-09-10"') && emptied.includes('value=""') && !emptied.includes(PICKUP.next_start), [typed, emptied]);
}

// ── mutants ───────────────────────────────────────────────────────────────────────
const swap = (from, to) => (src) => {
  if (!src.includes(from)) die(`mutation anchor stopped matching: ${JSON.stringify(from)}`);
  return src.replace(from, to);
};
const DEFECTS = [
  ['M1 an older record without the key is drawn as «not declared»',
    swap("if (!('window' in c)) return", "if (false) return")],
  ['M2 the row takes any backfill run, not its own collector\'s',
    swap('r.op === BACKFILL_OP && r.params && r.params.collector === key', 'r.op === BACKFILL_OP')],
  ['M3 a failed run is not drawn red', swap("tone: reason ? 'danger' :", "tone: false ? 'danger' :")],
  ['M4 the day count drops the total', swap('`${Number.isFinite(done) ? done : 0}/${total} days`', '`${done} days`')],
  ['M5 a null window is read as declared', swap("const declared = typeof c.window === 'string' ? c.window.trim() : '';",
    "const declared = String(c.window);")],
  ['M6 the screen counts the next start itself (start + finished days)',
    swap("const nextStart = typeof latest.next_start === 'string' ? latest.next_start : '';",
      'const nextStart = latest.params && latest.params.start ? new Date(Date.parse(latest.params.start)'
      + ' + 86400000 * Number(latest.processed_rows || 0)).toISOString().slice(0, 10) : \'\';')],
];
// The cell is its own module; its one defect is scored against it.
const ROWS_PATH = fileURLToPath(new URL('../src/admin_rows.js', import.meta.url));
const ROW_DEFECTS = [
  ['R1 a re-read list writes the next start over what the operator typed',
    swap("b.value !== undefined ? b.value : (v.nextStart || '')", "v.nextStart || b.value || ''")],
];
function rowsVerdict(R) {
  const v = { show: true, key: 'k', nextStart: 'N' };
  return !R.backfillCellHtml({ view: v, open: true, value: 'T' }).includes('value="T"')
    || !R.backfillCellHtml({ view: v, open: true, value: '' }).includes('value=""')
    || !R.backfillCellHtml({ view: v, open: true }).includes('value="N"');
}
const CONTROLS = [
  ['a comment removed', (src) => src.replace('// The list is newest first', '// ')],
];
function verdict(M) {
  const v = M.collectorBackfillView(COL, RUNS);
  const f = M.collectorBackfillView(COL, only(RUNS.runs[3]));
  return M.collectorBackfillView({ table_name: 't', script_name: 'd.py' }, null).show !== false
    || !v.line || v.line.text !== 'Running · 3/7 days'
    || f.line.tone !== 'danger'
    || M.collectorBackfillView({ ...COL, window: null }, null).offReason !== 'Declare # window: to backfill'
    || M.collectorBackfillView(COL, only(PICKUP)).nextStart !== PICKUP.next_start;
}
if (verdict(BASELINE)) die('the scorer already fails on the UNMUTATED module');
if (rowsVerdict(await import('../src/admin_rows.js'))) die('the cell scorer already fails on the UNMUTATED module');
async function score(list, mustCatch, heading, target = SRC_PATH, judge = verdict) {
  console.log(`\n── ${heading} ─────────────────────────────`);
  let hit = 0;
  for (const [name, mutate] of list) {
    let bad = false;
    try { bad = judge((await loadWithProbe(target, { mutate, tag: 'backfill' })).module); }
    catch (e) {
      if (/did not mutate|unchanged/.test(String(e && e.message))) die(`${name}: ${e.message}`);
      bad = true;
    }
    if (bad === mustCatch) { hit++; console.log(`  ${mustCatch ? 'caught ' : 'escaped'} ${name}`); }
    else { failed++; console.log(`  ${mustCatch ? 'ESCAPED' : 'CAUGHT '} ${name}  <- wrong`); }
  }
  return hit;
}
const caught = await score(DEFECTS, true, 'defect mutants (each must be CAUGHT)')
  + await score(ROW_DEFECTS, true, 'cell defect mutants (each must be CAUGHT)', ROWS_PATH, rowsVerdict);
const escaped = await score(CONTROLS, false, 'control mutants (each must ESCAPE)');
console.log(`\n${passed} passed, ${failed} failed; ${caught}/${DEFECTS.length + ROW_DEFECTS.length} defects caught; `
  + `${escaped}/${CONTROLS.length} controls escaped.`);
console.log(`ASSERTIONS ${passed} ${failed}`);
if (failed) process.exit(1);
