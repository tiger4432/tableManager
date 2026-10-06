// run_lines_harness — one run is one line of FIVE cells, and what it did sits UNDER it (lead a274c90f0).
//
//   A  five cells, always — the defect was a 3-column grid with 4 children on a finished row
//   B  the result and the failure reason are their own full-width line, never a cell
//   C  a finished run says so in the server's word, with no fade
//   D  × only where a cancel reaches, and never on a run already stopping
//   E  the title carries the form's params only (buildRunsView) — no path, no bare numbers
//   F  two instances on one page do not touch each other (조립식)
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';
import { makeDoc, byClass } from './lib/board_dom.mjs';
import { buildRunsView } from '../src/retroactive_view.js';
import { failureRecordCells } from '../src/failure_summary.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FILE = path.join(HERE, '..', 'src', 'run_lines.js');
const REAL = await import('../src/run_lines.js');

const NOW = Date.parse('2026-09-25T10:30:00+00:00');
const RUNS = {
  state_names: { running: 'Running', done: 'Done', failed: 'Failed', cancel_requested: 'Stopping' },
  runs: [
    { run_id: 'r1', op: 'resolve', label: 'Recompute shown values (R3)', state: 'running',
      params: { table: 'void_obs', pace: 'slow', world: 'exp', chunk_size: 100 },
      processed_rows: 50, total_rows: 100, started_at: '2026-09-25T10:20:00+00:00' },
    { run_id: 'r2', op: 'resolve', label: 'Recompute shown values (R3)', state: 'done',
      params: { table: 'void_obs' }, processed_rows: 103858, total_rows: null,
      started_at: '2026-09-25T10:00:00+00:00', finished_at: '2026-09-25T10:05:00+00:00',
      result_sentence: 'cells changed 0 · cells examined 1 · rows scanned 103858' },
    { run_id: 'r3', op: 'resolve', label: 'Recompute shown values (R3)', state: 'failed',
      params: { table: 'x' }, started_at: '2026-09-25T09:00:00+00:00',
      finished_at: '2026-09-25T09:01:00+00:00', error: 'relation x does not exist' },
    { run_id: 'r4', op: 'resolve', label: 'Recompute shown values (R3)', state: 'cancel_requested',
      params: { table: 'void_obs' }, processed_rows: 5, started_at: '2026-09-25T10:25:00+00:00' },
  ],
};
const VIEW = buildRunsView(RUNS, NOW, { resolve: true }, { resolve: ['table', 'pace'] });

async function suite(mod) {
  const ran = [];
  const failures = [];
  const eq = (name, got, want) => {
    ran.push(name);
    const g = JSON.stringify(got); const w = JSON.stringify(want);
    if (g !== w) failures.push(`${name}: got ${g}, want ${w}`);
  };
  const doc = makeDoc();
  const mount = doc.createElement('div');
  const cancelled = [];
  const part = new mod.RunLines(mount, { doc, onCancel: (id) => cancelled.push(id),
    resultBoxes: (extras) => extras.map(() => doc.createElement('div')) });
  part.render(VIEW.rows);
  const lines = byClass(mount, 'run-line');
  const byId = (id) => lines.find((l) => l.getAttribute('data-run-id') === id) || { children: [], className: '' };
  const cells = (line) => line.children.filter((c) => c.className !== 'run-line__result');

  eq('A1 every line has exactly five cells', lines.map((l) => cells(l).length), lines.map(() => 5));
  eq('A2 in the declared order', cells(byId('r1')).map((c) => c.className),
    ['run-line__what', 'run-line__progress', 'run-line__elapsed', 'run-line__state', 'run-line__act']);

  const resultOf = (id) => byId(id).children.find((c) => c.className === 'run-line__result');
  eq('B1 a finished run\'s result is its own line under the cells',
    resultOf('r2') ? resultOf('r2').textContent : null, 'cells changed 0 · cells examined 1 · rows scanned 103858');
  eq('B2 ...and the elapsed cell holds only the elapsed time',
    (cells(byId('r2'))[2] || {}).textContent, '5m');
  eq('B3 a failure reason sits on the same full-width line',
    resultOf('r3') ? resultOf('r3').textContent : null, 'relation x does not exist');
  eq('B4 a run that said nothing has no result line', resultOf('r1') === undefined, true);

  eq('C1 the state cell is the server\'s word', lines.map((l) => (cells(l)[3] || {}).textContent),
    ['Running', 'Stopping', 'Done', 'Failed']);
  eq('C2 a finished run is marked by class, never by an inline fade',
    [/is-finished/.test(byId('r2').className), byId('r2').style ? (byId('r2').style.opacity || '') : ''], [true, '']);

  const xOf = (id) => byClass(byId(id), 'running-x');
  eq('D1 a running, cancellable run has one ×', xOf('r1').length, 1);
  eq('D2 a finished run has none', xOf('r2').length, 0);
  eq('D3 a run already stopping has none', xOf('r4').length, 0);
  (xOf('r1')[0] && xOf('r1')[0].listeners.click || []).forEach((fn) => fn());
  eq('D4 pressing × asks by the run id', cancelled, ['r1']);

  eq('E1 the title carries the form\'s params and not the rest',
    (cells(byId('r1'))[0] || {}).textContent, 'Recompute shown values (R3) · void_obs · slow');

  // A `rule_rows` run's error is the chain's failure record (server 67b2e423b): drawn as the Chain
  // tab's five cells, label then value, and never as its JSON. A record cut short stays text.
  const record = { failed_at: '2026-10-06T10:00:00', reason: 'boom', rules: ['r_llm'], tables: ['notes'], rows: 6, row: null };
  const cut = JSON.stringify(record).slice(0, 40);
  const failedRun = (id, error) => ({ run_id: id, op: 'rule_rows', label: "Run a rule's queued rows",
    state: 'failed', params: {}, finished_at: '2026-09-25T09:01:00+00:00', error });
  const mount3 = doc.createElement('div');
  new mod.RunLines(mount3, { doc }).render(buildRunsView({ state_names: RUNS.state_names,
    runs: [failedRun('q1', JSON.stringify(record)), failedRun('q2', cut)] }, NOW, {}, {}).rows);
  const resultIn = (id) => (byClass(mount3, 'run-line').find((l) => l.getAttribute('data-run-id') === id) || { children: [] })
    .children.find((c) => c.className === 'run-line__result') || { children: [], textContent: null };
  eq('B5 a failure record is the Chain tab\'s five cells, label then value',
    resultIn('q1').children.map((c) => c.children.map((x) => x.textContent)),
    failureRecordCells(record));
  eq('B6 ...and its JSON is not drawn', /[{}]/.test(resultIn('q1').textContent || ''), false);
  eq('B7 a record cut short stays the text it was', resultIn('q2').textContent, cut);

  const mount2 = doc.createElement('div');
  const other = new mod.RunLines(mount2, { doc });
  other.render([VIEW.rows[0]]);
  eq('F1 a second instance draws only its own rows, and the first keeps its own',
    [byClass(mount2, 'run-line').length, byClass(mount, 'run-line').length], [1, 4]);
  return { ran, failures };
}

const result = await suite(REAL);
console.log('-- run lines -------------------------------------------------------');
console.log(`  ${result.ran.length - result.failures.length} passed, ${result.failures.length} failed`);
result.failures.forEach((f) => console.log(`  FAIL  ${f}`));

const MUTANTS = [
  { id: 'R1', what: 'the empty × cell is not drawn, so a finished line has four cells', catches: ['A1'],
    mutate: (s) => s.replace("    line.appendChild(act);\n", "    if (v.cancel) line.appendChild(act);\n") },
  { id: 'R2', what: 'the result goes into the elapsed cell — the 32px defect back', catches: ['B1', 'B2'],
    mutate: (s) => s.replace("line.appendChild(this._el('span', 'run-line__elapsed', v.elapsed));",
      "line.appendChild(this._el('span', 'run-line__elapsed', v.elapsed + v.summary));") },
  { id: 'R3', what: 'the state cell draws the token, not the server\'s word', catches: ['C1'],
    mutate: (s) => s.replace('    state: textOf(r.stateName),', '    state: String(r.state || \'\'),') },
  { id: 'R4', what: 'a stopping run keeps its ×', catches: ['D3'],
    mutate: (s) => s.replace('    cancel: Boolean(r.cancel) && !r.stopping,', '    cancel: Boolean(r.cancel),') },
  { id: 'R5', what: 'the failure reason is dropped', catches: ['B3'],
    mutate: (s) => s.replace("      if (v.reason) result.appendChild(this._el('span', 'run-line__reason', v.reason));\n", '') },
  { id: 'R6', what: 'a failure record\'s cells are not drawn', catches: ['B5'],
    mutate: (s) => s.replace('    if (boxes.length || v.summary || v.reason || v.failure.length) {',
      '    if (boxes.length || v.summary || v.reason) {') },
  { id: 'R7', what: 'a cell loses its label', catches: ['B5'],
    mutate: (s) => s.replace("        pair.appendChild(this._el('span', 'run-line__label', cell.label));\n", '') },
];
console.log('');
console.log('-- defect mutants (each must be CAUGHT by its named line) -----------');
const { wrong } = await scoreMutants(MUTANTS, async (m) => suite((await loadWithProbe(FILE, { mutate: m.mutate })).module));
const failed = result.failures.length + wrong;
console.log(`\n${result.ran.length - result.failures.length} passed, ${result.failures.length} failed; `
  + `${MUTANTS.length - wrong}/${MUTANTS.length} defects caught, ${wrong} escaped.`);
console.log(`ASSERTIONS ${result.ran.length + MUTANTS.length} ${failed}`);
process.exit(failed ? 1 : 0);
