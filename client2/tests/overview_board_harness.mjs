/**
 * OVERVIEW BOARD — mockup A's STATUS rows (lead 3c3f2b1f2 · 5d157581e · 575a844f7).
 *
 *   W  the words are a closed four, paired with the dot, and every row carries one of them
 *   P  not arrived is 「Loading…」 and unread is grey — neither is a 0
 *   K H N L D T C E   one judge per row: Workers · Chain · Enrichment · Ledger · Declarations ·
 *      Retroactive · Re-correction · Correction effort (File · Auto Update: health_card_absence)
 *   B  the board part: seats in the mockup's order, one seat per update, a body opens in place,
 *      「Open ›」 goes and does not also open, two boards on a page do not touch
 *
 * Every defect below must be caught by the assertion it names.
 */
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';
import { makeDoc, byClass } from './lib/board_dom.mjs';
import { buildConfigResolveView } from '../src/config_resolve_view.js';
import { localShort } from '../src/server_time.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const STATUS_FILE = path.join(HERE, '..', 'src', 'overview_status.js');
const BOARD_FILE = path.join(HERE, '..', 'src', 'overview_board.js');

const AT = '2026-09-22T15:14:06+00:00';
const RESOLVE = buildConfigResolveView({
  vocabulary: { populations: ['effective', 'ineffective', 'rejected'] },
  domains: [{ domain: 'ledger', title: 'Ledger',
    effective: [{ subject: 'a', reason: 'ok', detail: 'fine', fields: {} }],
    rejected: [{ subject: 'r', reason: 'mapping_unavailable', detail: 'bad', fields: {} }] }],
});
const LEDGER = (refused) => ({ ingestion: {
  states: { ran_and_wrote: 'rows are named', never_ran: 'nothing yet' },
  sources: [{ source: 's1', state: 'ran_and_wrote', declared: true, molecules_refused: refused },
            { source: 's2', state: 'never_ran', declared: true, molecules_refused: null }] } });
const RUNS = (over = {}) => ({ liveCount: 2, empty: false, failedSources: [], rows: [
  { finished: false, progress: { elapsedMinutes: 5 } }, { finished: false, progress: { elapsedMinutes: 21 } },
  { finished: true, progress: { elapsedMinutes: 40 } }], ...over });

async function suite({ status: S, board: B }) {
  const ran = [];
  const failures = [];
  const eq = (name, got, want) => {
    ran.push(name);
    const g = JSON.stringify(got); const w = JSON.stringify(want);
    if (g !== w) failures.push(`${name}: got ${g}, want ${w}`);
  };
  const said = (row) => `${row.tone}|${row.facts.join(' · ')}`;
  const all = [];
  const r = (row) => { all.push(row); return row; };

  // ── W ──
  eq('W1 the words are the closed four, one per dot colour', S.WORDS,
    { ok: 'OK', warn: 'Warning', danger: 'Failing', unknown: 'Unknown' });

  // ── P ──
  const pendings = [S.workersRow(), S.fileRow(), S.chainRow(), S.autoRow(), S.enrichmentRow(), S.ledgerRow(),
    S.declarationsRow(), S.retroactiveRow(), S.recorrectionRow(), S.effortRow()].map(r);
  eq('P1 a row that has not arrived is grey and says Loading…',
    [...new Set(pendings.map(said))], ['unknown|Loading…']);
  const unread = [S.workersRow(null), S.chainRow({ outbox: null }), S.enrichmentRow(null), S.ledgerRow(null),
    S.declarationsRow(null, 'refused'), S.retroactiveRow(null)].map(r);
  eq('P2 an unread answer is grey and claims no number',
    unread.map((x) => [x.tone, /\d/.test(x.facts.join(''))]), unread.map(() => ['unknown', false]));

  // ── K Workers ──
  const loops = (...alive) => ({ loops: alive.map((a, i) => ({ loop: `l${i}`, alive: a })) });
  eq('K1 every loop alive is OK, counted', said(r(S.workersRow(loops(true, true)))), 'ok|2 of 2 alive');
  eq('K2 a dead loop is Failing', r(S.workersRow(loops(true, false))).tone, 'danger');
  eq('K3 a loop of unknown life is Warning, not OK', r(S.workersRow(loops(true, null))).tone, 'warn');

  // ── H Chain ──
  eq('H1 failures carry since when, and fail the row',
    said(r(S.chainRow({ outbox: { total: 81, oldest_failed_at: AT }, rules: { data: [1, 2] }, mappers: { data: [1] } }))),
    `danger|failed 81 since ${localShort(AT)} · rules 2 · mappers 1`);
  eq('H2 NEGATIVE CONTROL: none failed is OK', r(S.chainRow({ outbox: { total: 0 } })).tone, 'ok');
  eq('H3 a body with no total is unread, not 0', r(S.chainRow({ outbox: { data: [] } })).tone, 'unknown');

  // ── N Enrichment ──
  eq('N1 no rules is grey, not OK', said(r(S.enrichmentRow({ rules: [], totalMissing: 0 }))), 'unknown|No rules');
  eq('N2 missing values are Warning', r(S.enrichmentRow({ rules: [{}], totalMissing: 3 })).tone, 'warn');
  eq('N3 NEGATIVE CONTROL: nothing missing is OK', r(S.enrichmentRow({ rules: [{}], totalMissing: 0 })).tone, 'ok');

  // ── L Ledger ──
  eq('L1 sources by the server\'s own state words', said(r(S.ledgerRow(LEDGER(0)))), 'ok|ran_and_wrote 1 · never_ran 1');
  eq('L2 refused molecules are counted and warn', said(r(S.ledgerRow(LEDGER(1234)))),
    'warn|ran_and_wrote 1 · never_ran 1 · refused 1,234');
  // lead 909ea2052 ①: the row says the server's short names once the server sends them.
  const named = LEDGER(0);
  named.ingestion.state_names = { ran_and_wrote: 'Translated', never_ran: 'Not run' };
  eq('L3 the row draws the server\'s state names, not the machine words', said(r(S.ledgerRow(named))),
    'ok|Translated 1 · Not run 1');

  // ── D Declarations ──
  const decl = r(S.declarationsRow(RESOLVE));
  eq('D1 the populations are the facts, and a rejected line fails the row',
    [decl.tone, decl.facts.length], ['danger', 3]);
  eq('D2 an unread report says the refusal', said(r(S.declarationsRow(null, 'HTTP five hundred'))),
    'unknown|HTTP five hundred');

  // ── T Retroactive ──
  eq('T1 N running, and the oldest is the MAX of the unfinished', said(r(S.retroactiveRow(RUNS()))),
    'ok|2 running · oldest 21m');
  // lead 909ea2052 ③: an empty cell read the same as an unread one.
  eq('T2 nothing running says 0 running, not an empty cell', said(r(S.retroactiveRow(RUNS({ liveCount: 0, rows: [] })))),
    'ok|0 running');
  eq('T3 a source that could not be read makes it grey', r(S.retroactiveRow(RUNS({ failedSources: ['run list'] }))).tone,
    'unknown');

  // ── C Re-correction ──
  const rc = (rate, cells) => S.recorrectionRow({ rate_pct: rate, measured_cells: cells, recorrected_cells: 3, window_days: 7 });
  eq('C1 a small sample is grey, not a verdict', [r(rc(12, 50)).tone, rc(12, 50).facts.includes('small sample')],
    ['unknown', true]);
  eq('C2 the rate decides above 100 cells', [r(rc(12, 500)).tone, r(rc(6, 500)).tone, r(rc(2, 500)).tone],
    ['danger', 'warn', 'ok']);

  // ── E Correction effort ──
  const ef = (score, ratio) => S.effortRow({ avg_score: score, measured_ratio: ratio, window_days: 7, tx_count: 4, session_count: 2 });
  eq('E1 0 measured while people corrected is Failing — the instrument died', r(ef(null, 0)).tone, 'danger');
  eq('E2 low coverage warns', r(ef(3.1, 0.3)).tone, 'warn');
  eq('E3 NEGATIVE CONTROL: good coverage is OK', r(ef(3.1, 0.9)).tone, 'ok');

  eq('W2 every row above carries a tone of the four and the word that goes with it',
    all.filter((x) => !(x.tone in S.WORDS) || x.word !== S.WORDS[x.tone]).length, 0);

  // ── B the board part ──
  const doc = makeDoc('light');
  const mountA = doc.createElement('div');
  const mountB = doc.createElement('div');
  const body = doc.createElement('div');
  let opened = 0;
  const a = new B.OverviewBoard(mountA, { doc, bodies: { workers: body },
    open: { chain: () => { opened += 1; }, workers: () => { opened += 10; } } });
  const b = new B.OverviewBoard(mountB, { doc });
  const seats = (m) => byClass(m, 'ov-row');
  const seat = (m, key) => seats(m).find((n) => n.getAttribute('data-key') === key);
  eq('B1 ten seats in the mockup\'s order', seats(mountA).map((n) => n.getAttribute('data-key')), S.ROW_ORDER);
  a.update(S.chainRow({ outbox: { total: 81 } }));
  const cells = (n) => byClass(n, 'ov-row-name').concat(byClass(n, 'ov-row-facts'), byClass(n, 'ov-row-word'))
    .map((c) => c.textContent);
  eq('B2 an update fills its own seat', [seat(mountA, 'chain').getAttribute('data-tone'), ...cells(seat(mountA, 'chain'))],
    ['danger', 'Chain', 'failed 81 · rules — · mappers —', 'Failing']);
  eq('B3 ...and no other seat, on this board or the other',
    [cells(seat(mountA, 'file')).join(''), cells(seat(mountB, 'chain')).join('')], ['', '']);
  const wrap = body.parentNode;
  eq('B4 the page\'s body is moved under its row, closed', [!!wrap && wrap.className, wrap && wrap.hidden], ['ov-row-body', true]);
  seat(mountA, 'workers').dispatch('click');
  eq('B5 clicking the row opens it in place', [wrap.hidden, seat(mountA, 'workers').getAttribute('aria-expanded')], [false, 'true']);
  seat(mountA, 'workers').dispatch('click');
  eq('B6 ...and clicking again closes it', wrap.hidden, true);
  eq('B7 a row with no body is not a button', seat(mountA, 'file').getAttribute('role'), null);
  const open = byClass(seat(mountA, 'chain'), 'ov-row-open').find((n) => n.tagName === 'BUTTON');
  open.dispatch('click');
  eq('B8 「Open ›」 does what the page gave it', opened, 1);
  byClass(seat(mountA, 'workers'), 'ov-row-open').find((n) => n.tagName === 'BUTTON').dispatch('click');
  eq('B10 「Open ›」 on a row with a body goes, and does not also open the body', [opened, wrap.hidden], [11, true]);
  eq('B9 a row the page gave no Open has no button', byClass(seat(mountA, 'file'), 'ov-row-open').map((n) => n.tagName), ['SPAN']);
  return { ran, failures };
}

const status = await import('../src/overview_status.js');
const board = await import('../src/overview_board.js');
const result = await suite({ status, board });
console.log('-- overview board ---------------------------------------------------');
console.log(`  ${result.ran.length - result.failures.length} passed, ${result.failures.length} failed`);
result.failures.forEach((f) => console.log(`  FAIL  ${f}`));

const onStatus = (mutate) => async () => ({ status: (await loadWithProbe(STATUS_FILE, { mutate })).module, board });
const onBoard = (mutate) => async () => ({ status, board: (await loadWithProbe(BOARD_FILE, { mutate })).module });
const MUTANTS = [
  { id: 'S1', what: 'the words drift', catches: ['W1'], load: onStatus((s) => s.replace("warn: 'Warning'", "warn: 'Watch'")) },
  { id: 'S2', what: 'a dead loop only warns', catches: ['K2'],
    load: onStatus((s) => s.replace('TONE.UNKNOWN : dead ? TONE.DANGER', 'TONE.UNKNOWN : dead ? TONE.WARN')) },
  { id: 'S3', what: 'a loop of unknown life counts as alive', catches: ['K3'],
    load: onStatus((s) => s.replace('    : alive < view.rows.length ? TONE.WARN : TONE.OK;', '    : TONE.OK;')) },
  { id: 'S4', what: 'an unread chain total is OK', catches: ['H3'],
    load: onStatus((s) => s.replace('const tone = !failed.read ? TONE.UNKNOWN : failed.total > 0', 'const tone = !failed.read ? TONE.OK : failed.total > 0')) },
  { id: 'S5', what: 'no enrichment rules is OK', catches: ['N1'],
    load: onStatus((s) => s.replace("['No rules'], TONE.UNKNOWN)", "['No rules'], TONE.OK)")) },
  { id: 'S6', what: 'refused molecules are ignored', catches: ['L2'],
    load: onStatus((s) => s.replace('  if (refused) facts.push', '  if (false) facts.push')) },
  { id: 'S7', what: 'the oldest run counts finished ones', catches: ['T1'],
    load: onStatus((s) => s.replace('.filter((r) => r && !r.finished)', '.filter((r) => r)')) },
  { id: 'S8', what: 'a small sample is coloured by its rate', catches: ['C1'],
    load: onStatus((s) => s.replace('const small = cells === null || cells < 100;', 'const small = false;')) },
  { id: 'S9', what: 'an unreachable run source reads idle', catches: ['T3'],
    load: onStatus((s) => s.replace('unreachable.length ? TONE.UNKNOWN : TONE.OK', 'TONE.OK')) },
  { id: 'X1', what: 'the body is not closed at first', catches: ['B4'],
    load: onBoard((s) => s.replace('      wrap.hidden = true;\n', '')) },
  { id: 'X2', what: '「Open ›」 also folds the row open', catches: ['B10'],
    load: onBoard((s) => s.replace("line.addEventListener('click', (e) => { if (!btn || e.target !== btn) toggle(); });", "line.addEventListener('click', () => toggle());")) },
  { id: 'X3', what: 'an update writes the first seat whatever its key', catches: ['B2', 'B3'],
    load: onBoard((s) => s.replace('const seat = row && this.seats.get(row.key);', 'const seat = row && [...this.seats.values()][0];')) },
  { id: 'X4', what: 'every row is a button', catches: ['B7'],
    load: onBoard((s) => s.replace("    line.setAttribute('data-key', key);", "    line.setAttribute('data-key', key); line.setAttribute('role', 'button');")) },
];
console.log('');
console.log('-- defect mutants (each must be CAUGHT by its named line) -----------');
const { wrong } = await scoreMutants(MUTANTS, async (m) => suite(await m.load()));
const failed = result.failures.length + wrong;
console.log(`\n${result.ran.length - result.failures.length} passed, ${result.failures.length} failed; `
  + `${MUTANTS.length - wrong}/${MUTANTS.length} defects caught, ${wrong} escaped.`);
console.log(`ASSERTIONS ${result.ran.length + MUTANTS.length} ${failed}`);
process.exit(failed ? 1 : 0);
