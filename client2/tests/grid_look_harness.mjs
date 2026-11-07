// A cell's look (owner 11-06 mockup v3, lead L2): src/grid_look.js lookOf - the one seat that says a cell's role - and
// the rows the Colours tab writes. Every subject is IMPORTED.
//
//   P  a paint over every rule; a later rule over an earlier one (lead 11-07 ㄱ); no look -> null; looks not said -> null
//   S  a rule on its columns only (none = every column); a writer rule on that writer's cells - absent writer: no match
//   C  the condition is the calculator's: «0.52» > 0.5 holds, «hold» and blank do not; a refused condition is refused
//   L  a broadcast's rule and paint rows taken in, a wiped role gone, rules in their order; another table's left alone
//   W  the writes - a rule's cells, a paint's key «<row>/<column>», a wipe; a place still a place (grid_order)
//   O  a rule dragged: its place between its new neighbours' (grid_order.dropPlace), only its position written
//   M  mutants - a copy of the whole grid_look.js (its imports pointed at the real modules), one change, P and S again
//
// Run: node client2/tests/grid_look_harness.mjs
import { lookOf, ruleRefusal, ruleText, ruleUpdate, ruleMove, ruleOff, paintUpdate, paintKey, looksOn, pageLooks, RULE_EMPTY_NOTE } from '../src/grid_look.js';
import { placeUpdate, placesOn, dropPlace } from '../src/grid_order.js';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { readSourceText } from './lib/probe.mjs';

let pass = 0;
const failures = [];
function eq(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { pass++; console.log(`  PASS ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name}\n        got  ${g}\n        want ${w}`); }
}

const rule = (id, position, role, more = {}) => ({ id, position, role, when: null, columns: null, written_by: null, ...more });
const LOOKS = {
  rules: [rule('r1', '08', 'warn', { when: '[value] > 0.3' }), rule('r2', '8', 'danger', { when: '[value] > 0.5' }),
    rule('r3', '9', 'accent', { written_by: 'ai', columns: ['cmp'] })],
  paints: { [paintKey('row-2', 'cmp')]: { role: 'ok', row_id: 'p1' } },
};
const at = (rowId, column, value, writtenBy) => lookOf(LOOKS, rowId, column, { value, ...(writtenBy ? { written_by: writtenBy } : {}) });

eq('P1 the later rule wins - 0.52 is Danger, 0.34 is Warn (the mockup)', [at('row-1', 'etch', '0.52'), at('row-1', 'etch', '0.34')],
  [{ role: 'danger', hand: false }, { role: 'warn', hand: false }]);
eq('P2 a paint over every rule - even one that holds', at('row-2', 'cmp', '0.52', 'ai'), { role: 'ok', hand: true });
eq('P3 no rule holds: no look', at('row-1', 'etch', '0.12'), null);
eq('P4 the looks not said (absent from the read): nothing drawn', lookOf(null, 'row-1', 'etch', { value: '0.9' }), null);
eq('S1 a writer rule on its column, that writer: Accent (the last rule); elsewhere not',
  [at('row-1', 'cmp', '0.12', 'ai'), at('row-1', 'etch', '0.12', 'ai'), at('row-1', 'cmp', '0.12', 'chain')],
  [{ role: 'accent', hand: false }, null, null]);
eq('S2 a cell whose writer was not read (no written_by): a writer rule does not hold', at('row-1', 'cmp', '0.12'), null);
eq('S3 a wiped role is no rule and no paint', lookOf({ rules: [rule('r', '8', '', { when: '[value] > 0' })],
  paints: { [paintKey('row-1', 'etch')]: { role: '' } } }, 'row-1', 'etch', { value: '1' }), null);
eq('C1 text that is no number holds nothing; a blank neither', [at('row-1', 'etch', 'hold'), at('row-1', 'etch', '')], [null, null]);
eq('C2 the refusals - an empty rule, a condition the calculator cannot read; a good one and a writer alone pass',
  [ruleRefusal({}), typeof ruleRefusal({ when: '[value] >' }), ruleRefusal({ when: '[value] > 0.3' }), ruleRefusal({ written_by: 'ai' })],
  [RULE_EMPTY_NOTE, 'string', null, null]);
eq('C3 a rule as its list says it', [ruleText(LOOKS.rules[0]), ruleText(LOOKS.rules[2]), ruleText(rule('r', '8', 'ok', { when: '[value] > 1', written_by: 'file' }))],
  ['[value] > 0.3', 'Written by: AI', '[value] > 1 · Written by: File']);

const item = (row_id, cells) => ({ row_id, data: Object.fromEntries(Object.entries(cells).map(([k, v]) => [k, { value: v }])) });
const msg = { items: [
  item('s1', { look_table: 'T', look_axis: 'rule', look_key: 'r4', position: '07', role: 'ok', rule_when: '[value] < 0', rule_columns: '["etch"]', written_by: '' }),
  item('s2', { look_table: 'T', look_axis: 'rule', look_key: 'r2', role: '' }),
  item('s3', { look_table: 'T', look_axis: 'paint', look_key: paintKey('row-2', 'cmp'), role: '' }),
  item('s4', { look_table: 'T', look_axis: 'paint', look_key: paintKey('row-3', 'etch'), role: 'danger' }),
  item('s5', { look_table: 'U', look_axis: 'paint', look_key: paintKey('row-9', 'etch'), role: 'warn' }),
] };
const after = looksOn(msg, 'T', LOOKS);
eq('L1 rules taken in and in order, a wiped one gone; paints taken in, a wiped one gone; another table\'s not',
  [after.rules.map((r) => [r.id, r.role, r.columns]), after.paints],
  [[['r4', 'ok', ['etch']], ['r1', 'warn', null], ['r3', 'accent', ['cmp']]], { [paintKey('row-3', 'etch')]: { role: 'danger', row_id: 's4' } }]);
eq('L2 a broadcast with no look of this table: null (nothing to draw again); a place is not a look',
  [looksOn({ items: [msg.items[4]] }, 'T', LOOKS), looksOn({ items: [item('x', { look_table: 'T', look_axis: 'row', look_key: 'a', position: '8' })] }, 'T', LOOKS)],
  [null, null]);
eq('L3 a place broadcast moves rows; a look broadcast on the same table does not (it is no place)',
  [placesOn({ items: [item('x', { look_table: 'T', look_axis: 'row', look_key: 'a', position: '8' })] }, 'T'),
    placesOn({ items: [msg.items[3]] }, 'T')], [true, false]);
eq('L4 a page\'s looks: a first page replaces, a later page of the scroll keeps the paints shown; a page saying none clears',
  [pageLooks(LOOKS, { rules: [], paints: { k: { role: 'ok' } } }), pageLooks(LOOKS, { rules: [], paints: { k: { role: 'ok' } } }, true).paints,
    pageLooks(LOOKS, undefined)],
  [{ rules: [], paints: { k: { role: 'ok' } } }, { ...LOOKS.paints, k: { role: 'ok' } }, null]);

eq('W1 a rule\'s write - its role, condition, writer, columns as JSON, place',
  ruleUpdate('T', 'r5', { role: 'warn', when: '[value] > 1', written_by: 'ai', columns: ['a', 'b'], position: '88' }, 'kim'),
  { updates: { look_table: 'T', look_axis: 'rule', look_key: 'r5', role: 'warn', rule_when: '[value] > 1', written_by: 'ai',
    rule_columns: '["a","b"]', position: '88' }, source_name: 'user', updated_by: 'kim' });
eq('W2 a rule taken off - its role wiped, its condition, writer and columns not touched', ruleOff('T', 'r5', 'kim').updates,
  { look_table: 'T', look_axis: 'rule', look_key: 'r5', role: '' });
eq('W3 a paint\'s write - one cell, its role; a wipe its role blank', [paintUpdate('T', 'row-1', 'etch', 'danger', 'kim').updates,
  paintUpdate('T', 'row-1', 'etch', '', 'kim').updates.role],
  [{ look_table: 'T', look_axis: 'paint', look_key: 'row-1/etch', role: 'danger' }, '']);
eq('O1 Danger dragged above Warn - its place sorts first, so 0.52 is Warn (the later rule)', (() => {
  const place = dropPlace(LOOKS.rules.map((r) => r.position), 1, 0).place;
  const rules = LOOKS.rules.map((r) => (r.id === 'r2' ? { ...r, position: place } : r))
    .sort((x, y) => (x.position < y.position ? -1 : x.position > y.position ? 1 : 0));
  return [place < LOOKS.rules[0].position, lookOf({ ...LOOKS, rules }, 'row-1', 'etch', { value: '0.52' })];
})(), [true, { role: 'warn', hand: false }]);
eq('O2 a move writes its position only - its role, condition, writer and columns not touched', ruleMove('T', 'r2', '04', 'kim').updates,
  { look_table: 'T', look_axis: 'rule', look_key: 'r2', position: '04' });
eq('W4 a place is still a place', placeUpdate('T', 'row', 'f1', '08', 'kim'),
  { updates: { look_table: 'T', look_axis: 'row', look_key: 'f1', position: '08' }, source_name: 'user', updated_by: 'kim' });

// ── mutants: the whole grid_look.js copied, its two imports pointed at the real modules, one change ──
const SRC = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'src');
const decide = (m) => {
  const on = (rowId, column, value, writtenBy) => m.lookOf(LOOKS, rowId, column, { value, ...(writtenBy ? { written_by: writtenBy } : {}) });
  return [on('row-1', 'etch', '0.52'), on('row-2', 'cmp', '0.52', 'ai'), on('row-1', 'cmp', '0.12', 'ai'), on('row-1', 'etch', '0.12', 'ai'),
    on('row-1', 'cmp', '0.12', 'chain'), on('row-1', 'cmp', '0.12')];
};
const real = JSON.stringify(decide({ lookOf }));
const MUTANTS = [
  ['M1 a paint not over the rules', 'if (paint && paint.role) return { role: paint.role, hand: true };', ''],
  ['M2 the first rule wins, not the later', '    role = rule.role;', '    role = role || rule.role;'],
  ['M3 a rule on every column, its columns ignored', '(rule.columns && !rule.columns.includes(column))', 'false'],
  ['M4 a writer rule on any writer', '    if (rule.written_by && !(cell && cell.written_by === rule.written_by)) continue;\n', ''],
];
for (const [name, from, to] of MUTANTS) {
  const dir = mkdtempSync(path.join(tmpdir(), 'look-mutant-'));
  try {
    let { text } = readSourceText(path.join(SRC, 'grid_look.js'));     // LF whatever the checkout did
    if (!text.includes(from)) { eq(`${name}: its anchor is in grid_look.js`, false, true); continue; }
    for (const dep of ['expression.js', 'grid_order.js']) text = text.replace(`'./${dep}'`, `'${pathToFileURL(path.join(SRC, dep)).href}'`);
    const file = path.join(dir, 'grid_look.js');
    writeFileSync(file, text.replace(from, to));
    let caught;
    try { caught = JSON.stringify(decide(await import(pathToFileURL(file).href))) !== real; } catch (e) { caught = `threw ${e.message}`; }
    eq(`${name}: caught`, caught, true);
  } finally { rmSync(dir, { recursive: true, force: true }); }
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
