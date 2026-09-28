// COLUMN SAVE — the map editor's «save only the chosen column's changed cells» (lead 40bae1219).
// Imports the real module. Gates from the order: one cell of c1 changed -> one write, c1 only;
// untouched cells -> 0 writes; a paint and a clear -> one each; a cell changed elsewhere since the
// load is not overwritten; two rows on one cell refuse by name; and the «send every cell» mutant
// must go red.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import * as LIVE from '../src/column_save.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = readFileSync(join(HERE, '..', 'src', 'column_save.js'), 'utf8');

const row = (id, x, y, c1, c2 = 'keep2', c3 = 'keep3') => ({
  row_id: id, data: { x: { value: x }, y: { value: y }, c1: { value: c1 }, c2: { value: c2 }, c3: { value: c3 } },
});
const base = () => ({
  baseline: new Map([['1|1', 'A'], ['1|2', 'B'], ['2|1', '']]),
  current: new Map([['1|1', 'A'], ['1|2', 'B'], ['2|1', '']]),
  rows: [row('r11', 1, 1, 'A'), row('r12', 1, 2, 'B')],
  xCol: 'x', yCol: 'y', valCol: 'c1', types: { x: 'number', y: 'number', c1: 'string' },
  keyValues: { lot: 'L1' }, author: 'tester',
});

function score(M) {
  const failures = [];
  let compared = 0;
  const ok = (cond, what) => { compared += 1; if (!cond) failures.push(what); };

  let a = base(); let p = M.planColumnSave(a);
  ok(p.updates && p.updates.length === 0, 'nothing changed -> 0 writes');

  a = base(); a.current.set('1|1', 'Z'); p = M.planColumnSave(a);
  ok(p.updates?.length === 1 && p.edited === 1, 'one c1 edit -> one write');
  ok(p.updates?.[0]?.row_id === 'r11', 'the edit names the row it read');
  ok(JSON.stringify(p.updates?.[0]?.updates) === JSON.stringify({ c1: 'Z' }), 'the edit carries c1 only — c2 and c3 untouched');
  ok(JSON.stringify(p.written) === JSON.stringify(['1|1']), 'the written cell is named, to become the new baseline');

  a = base(); a.current.set('1|1', 'Z'); a.rows = [row('r11', '01', ' 1', 'A'), row('r12', 1, 2, 'B')];
  p = M.planColumnSave(a);
  ok(p.updates?.[0]?.row_id === 'r11', 'a stored coordinate is read the way the load reads it (parseInt)');

  a = base(); a.current.set('2|1', 'N'); p = M.planColumnSave(a);
  ok(p.painted === 1 && p.updates?.length === 1 && !p.updates[0].row_id, 'a paint -> one new row');
  ok(JSON.stringify(p.updates?.[0]?.updates) === JSON.stringify({ lot: 'L1', x: 2, y: 1, c1: 'N' }),
    'the new row carries the map key, x, y and c1 only');

  a = base(); a.current.set('1|2', ''); p = M.planColumnSave(a);
  ok(p.cleared === 1 && p.updates?.[0]?.row_id === 'r12', 'a clear keeps the row');
  ok(JSON.stringify(p.updates?.[0]?.updates) === JSON.stringify({ c1: '' }), 'a clear empties c1 only');
  a = base(); a.types.c1 = 'number'; a.baseline.set('1|2', '7'); a.current.set('1|2', '');
  a.rows = [row('r11', 1, 1, 'A'), row('r12', 1, 2, 7)]; p = M.planColumnSave(a);
  ok(p.updates?.[0]?.updates?.c1 === null, 'a cleared number cell goes out as null (the grid spelling)');

  a = base(); a.current.set('1|1', 'Z'); a.rows = [row('r11', 1, 1, 'Q'), row('r12', 1, 2, 'B')];
  p = M.planColumnSave(a);
  ok(p.updates?.length === 0 && p.conflicts?.[0] === '1|1', 'changed elsewhere since the load -> not overwritten, counted');

  a = base(); a.current.set('1|1', 'Z'); a.rows.push(row('r11b', 1, 1, 'A')); p = M.planColumnSave(a);
  ok(p.refusal === 'doubled' && p.cells?.[0] === '1|1', 'two rows on one cell -> refused by name');

  a = base(); a.current.set('2|1', 'N'); a.paintAllowed = false; p = M.planColumnSave(a);
  ok(p.refusal === 'paint' && p.cells?.[0] === '2|1', 'a paint on a table whose key lacks x·y -> refused');
  ok(M.paintIsSafe({}, 'x', 'y') === true, 'no declared key -> painting is safe');
  ok(M.paintIsSafe({ composite_key_source: ['lot', 'x', 'y'] }, 'x', 'y') === true, 'a key with x and y -> safe');
  ok(M.paintIsSafe({ composite_key_source: ['lot'] }, 'x', 'y') === false, 'a key without x·y -> not safe');
  return { compared, failures };
}

const live = score(LIVE);
if (live.compared === 0) { console.error('HARNESS FAILURE: nothing was compared.'); process.exit(2); }

// The order's mutant: «send every cell». It must go red.
const MUTANTS = [['send every cell', 'if (now !== was) changed.push', 'changed.push']];
const sweepFail = [];
for (const [name, from, to] of MUTANTS) {
  if (!SRC.includes(from)) { sweepFail.push(`${name}: its anchor is gone — the mutant never applied`); continue; }
  const url = 'data:text/javascript;base64,' + Buffer.from(SRC.replace(from, to), 'utf8').toString('base64');
  const out = score(await import(url));
  if (out.failures.length === 0) sweepFail.push(`${name}: survived — no assertion reads what it breaks`);
  else console.log(`  mutant «${name}» caught by: ${out.failures[0]}`);
}

const ran = live.compared + MUTANTS.length;
const failed = live.failures.length + sweepFail.length;
console.log(`\n${ran - failed} passed, ${failed} failed  (${live.compared} behaviour + ${MUTANTS.length} mutation verdicts)`);
live.failures.forEach((f) => console.log(`   x ${f}`));
sweepFail.forEach((f) => console.log(`   x mutant ${f}`));
console.log(`ASSERTIONS ${ran} ${failed}`);
process.exit(failed ? 1 : 0);
