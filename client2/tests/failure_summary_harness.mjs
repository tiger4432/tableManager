// failure_summary_harness — the failure section is one line per (table · kind · day), and an open
// line seats the page's row table under it (lead e573a6edf · 2f2a2f570).
//
//   A  a line says table kind count · span · attempts, from the server's summary as sent
//   B  the section's count is the rows the summary folded
//   C  a day cut in another zone than the one sent says whose day it is
//   D  the open line — and only it — gets the row table; pressing it again folds it
//   E  no summary is unread, not 「no failures」
//   F  two instances on one page do not touch each other
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';
import { makeDoc, byClass } from './lib/board_dom.mjs';
import { localSpan } from '../src/server_time.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FILE = path.join(HERE, '..', 'src', 'failure_summary.js');
const REAL = await import('../src/failure_summary.js');

const FIRST = '2026-09-23T00:14:00+09:00';
const LAST = '2026-09-23T00:39:00+09:00';
const BODY = { day_zone: 'Asia/Seoul', summary: [
  { table_name: 'dt_inventory', event_type: 'EDIT', day: '2026-09-23', count: 33,
    first_at: FIRST, last_at: LAST, retry_max: 1 },
  { table_name: 'wafer', event_type: 'CREATE', day: '2026-09-22', count: 2,
    first_at: FIRST, last_at: FIRST, retry_max: 0 },
] };

async function suite(mod) {
  const ran = [];
  const failures = [];
  const eq = (name, got, want) => {
    ran.push(name);
    const g = JSON.stringify(got); const w = JSON.stringify(want);
    if (g !== w) failures.push(`${name}: got ${g}, want ${w}`);
  };
  const view = mod.failureSummaryView(BODY, 'Asia/Seoul');
  eq('A1 a line is table kind count · span · attempts', view.lines[0].text,
    `dt_inventory EDIT 33 · ${localSpan(FIRST, LAST)} · attempts 1`);
  eq('A2 each line keeps its own numbers', view.lines.map((l) => l.count), [33, 2]);
  eq('A3 a line carries the key the unfold asks by', view.lines[0].filter,
    { table: 'dt_inventory', event_type: 'EDIT', day: '2026-09-23' });
  eq('B1 the section counts the rows the summary folded', view.rows, 35);
  const foreign = mod.failureSummaryView(BODY, 'Europe/Paris');
  eq('C1 a day cut in another zone says whose day', /2026-09-23 \(Asia\/Seoul day\)/.test(foreign.lines[0].text), true);
  eq('C2 ...and the viewer\'s own day does not', /day\)/.test(view.lines[0].text), false);
  eq('E1 no summary is unread, not no failures', [mod.failureSummaryView(null).read, mod.failureSummaryView({}).read], [false, false]);

  const doc = makeDoc();
  const mount = doc.createElement('div');
  const toggled = [];
  const part = new mod.FailureSummary(mount, { doc, onToggle: (line) => toggled.push(line ? line.key : null) });
  const rows = doc.createElement('div');
  rows.className = 'rows-box';
  part.render(view, { openKey: view.lines[1].key, rowsBody: rows });
  const kids = mount.children[0].children;
  eq('D1 the open line, and only it, is followed by the row table',
    kids.map((k) => k.className), ['fail-summary__line', 'fail-summary__line is-open', 'rows-box']);
  const lines = byClass(mount, 'fail-summary__line');
  (lines[0].listeners.click || []).forEach((fn) => fn());
  (lines[1].listeners.click || []).forEach((fn) => fn());
  eq('D2 pressing a folded line opens it; pressing the open one folds it', toggled, [view.lines[0].key, null]);
  part.render(view, { openKey: null, rowsBody: rows });
  eq('D3 with nothing open no line holds the table', byClass(mount, 'rows-box').length, 0);

  const mount2 = doc.createElement('div');
  new mod.FailureSummary(mount2, { doc }).render(mod.failureSummaryView({ summary: [BODY.summary[0]] }, ''));
  eq('F1 a second instance draws only its own lines, the first keeps its own',
    [byClass(mount2, 'fail-summary__line').length, byClass(mount, 'fail-summary__line').length], [1, 2]);
  return { ran, failures };
}

const result = await suite(REAL);
console.log('-- failure summary -------------------------------------------------');
console.log(`  ${result.ran.length - result.failures.length} passed, ${result.failures.length} failed`);
result.failures.forEach((f) => console.log(`  FAIL  ${f}`));

const MUTANTS = [
  { id: 'Y1', what: 'the attempts are read off the wrong field', catches: ['A1'],
    mutate: (s) => s.replace('parts.push(`attempts ${Number(l && l.retry_max) || 0}`);', 'parts.push(`attempts ${Number(l && l.count) || 0}`);') },
  { id: 'Y2', what: 'the section count is the number of lines, not the rows', catches: ['B1'],
    mutate: (s) => s.replace('rows: out.reduce((n, l) => n + l.count, 0) };', 'rows: out.length };') },
  { id: 'Y3', what: 'a foreign day goes unsaid', catches: ['C1'],
    mutate: (s) => s.replace("const foreignDay = Boolean(zone) && zone !== sentZone;", 'const foreignDay = false;') },
  { id: 'Y4', what: 'every line gets the row table', catches: ['D1'],
    mutate: (s) => s.replace('if (open && opts.rowsBody)', 'if (opts.rowsBody)') },
  { id: 'Y5', what: 'pressing the open line opens it again instead of folding it', catches: ['D2'],
    mutate: (s) => s.replace('this.onToggle(open ? null : line)', 'this.onToggle(line)') },
  { id: 'Y6', what: 'no summary reads as an empty one', catches: ['E1'],
    mutate: (s) => s.replace("if (!lines) return { read: false, lines: [], rows: 0 };", "if (!lines) return { read: true, lines: [], rows: 0 };") },
];
console.log('');
console.log('-- defect mutants (each must be CAUGHT by its named line) -----------');
const { wrong } = await scoreMutants(MUTANTS, async (m) => suite((await loadWithProbe(FILE, { mutate: m.mutate })).module));
const failed = result.failures.length + wrong;
console.log(`\n${result.ran.length - result.failures.length} passed, ${result.failures.length} failed; `
  + `${MUTANTS.length - wrong}/${MUTANTS.length} defects caught, ${wrong} escaped.`);
console.log(`ASSERTIONS ${result.ran.length + MUTANTS.length} ${failed}`);
process.exit(failed ? 1 : 0);
