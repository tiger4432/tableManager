// A cell's look (owner 11-06 mockup v3, lead L2): src/grid_look.js lookOf - the one seat that says a cell's role - and
// the rows the Colours tab writes. Every subject is IMPORTED.
//
//   P  a paint over every rule; a later rule over an earlier one (lead 11-07 ㄱ); no look -> null; looks not said -> null
//   S  a rule on its columns only (none = every column); a writer rule on that writer's cells - absent writer: no match
//   C  the condition is the calculator's: «0.52» > 0.5 holds, «hold» and blank do not; a refused condition is refused
//   L  a broadcast's rule and paint rows taken in, a wiped role gone, rules in their order; another table's left alone
//   W  the writes - a rule's cells, a paint's key «<row>/<column>», a wipe; a place still a place (grid_order)
//   O  a rule dragged: its place between its new neighbours' (grid_order.dropPlace), only its position written
//   R  the grid's selection (state.selectedCells, the one count bulk fill, copy, a drag's commit and paint ask): the
//      ctrl-clicked cells first, else the rectangle in column order; data columns unless said; the rectangle alone
//   T  what a selection paints: each stored cell once, a pivot's key or carried cell skipped and counted
//   B  what a sys_looks broadcast does: a paint drawn from the message; a rule, a place moved, or a count-only message
//      (past the server's BROADCAST_ITEM_LIMIT) reads the page again unless its edits_of leaves the table out;
//      another table's nothing
//   M  mutants - a copy of the whole module (its imports pointed at the real ones), one change, its cases again
//
// Run: node client2/tests/grid_look_harness.mjs
import { lookOf, ruleRefusal, ruleText, ruleUpdate, ruleMove, ruleOff, paintUpdate, paintKey, paintTargets, lookBroadcast, looksOn, pageLooks, RULE_EMPTY_NOTE } from '../src/grid_look.js';
import * as stateModule from '../src/state.js';
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

// ── R: the selection, T: what it paints ──
const selecting = (m, { clicked = {}, from = null, to = null } = {}) => {
  Object.assign(m.state, { visibleColIndexMap: { '#': 0, lot: 1, owner: 2, value: 3 }, selectedCellsMap: clicked, dragStartCell: from, dragEndCell: to });
};
const choose = (m) => {
  const said = [];
  selecting(m, { from: { rowIndex: 2, colId: 'value' }, to: { rowIndex: 1, colId: '#' } });
  said.push(m.selectedCells().map((c) => `${c.rowIndex}${c.colId}`));
  said.push(m.selectedCells({ keep: () => true }).length);
  selecting(m, { clicked: { '5_lot': { rowIndex: 5, colId: 'lot', rowId: 'x' }, '5_#': { rowIndex: 5, colId: '#' } },
    from: { rowIndex: 0, colId: 'lot' }, to: { rowIndex: 0, colId: 'owner' } });
  said.push(m.selectedCells().map((c) => `${c.rowIndex}${c.colId}`), m.selectedCells({ rectangle: true }).map((c) => `${c.rowIndex}${c.colId}`));
  selecting(m);
  said.push(m.selectedCells().length);
  // the cells a command acts on: the selection, else the focused cell when its column counts
  const focusing = (colId) => { m.state.gridApi = { getFocusedCell: () => (colId ? { rowIndex: 7, column: { getId: () => colId } } : null) }; };
  const acts = (opts) => m.cellsToActOn(opts).map((c) => `${c.rowIndex}${c.colId}`);
  focusing('owner');
  selecting(m, { from: { rowIndex: 0, colId: 'lot' }, to: { rowIndex: 0, colId: 'owner' } });
  const withRange = acts();
  selecting(m);
  const focusedData = acts();
  focusing('#');
  const focusedGutter = [acts(), acts({ keep: () => true })];
  focusing(null);
  const none = acts();
  m.state.gridApi = null;
  said.push([withRange, focusedData, focusedGutter, none]);
  // the highlight: the cells isSelected says yes to, over a 4 x 4 grid, against the cells selectedCells lists
  const lit = () => { const on = []; for (let r = 0; r < 4; r++) for (const c of ['#', 'lot', 'owner', 'value']) if (m.isSelected(r, c)) on.push(`${r}${c}`); return on; };
  const listed = () => m.selectedCells().map((c) => `${c.rowIndex}${c.colId}`).sort();
  const both = { '1_lot': { rowIndex: 1, colId: 'lot' } };
  selecting(m, { clicked: both, from: { rowIndex: 2, colId: 'owner' }, to: { rowIndex: 3, colId: 'value' } });
  const clickedAndRect = [lit(), listed()];
  m.state.isDraggingRange = true;
  const ctrlDragging = lit();
  m.state.isDraggingRange = false;
  selecting(m, { from: { rowIndex: 0, colId: '#' }, to: { rowIndex: 1, colId: 'owner' } });
  const rect = [lit(), listed()];
  selecting(m);
  said.push([clickedAndRect, ctrlDragging, rect, lit()]);
  return said;
};
const chosen = choose(stateModule);
eq('R1 the rectangle, rows then columns in column order, data columns only - the gutter «#» not counted',
  chosen[0], ['1lot', '1owner', '1value', '2lot', '2owner', '2value']);
eq('R2 every column when asked (copy): 2 rows x 4', chosen[1], 8);
eq('R3 ctrl-clicked cells first (the rectangle not added), data ones; the rectangle alone when asked (a drag\'s commit)',
  [chosen[2], chosen[3]], [['5lot'], ['0lot', '0owner']]);
eq('R4 no selection: none', chosen[4], 0);
eq('R6 the highlight is the listed selection: ctrl-clicked cells over a rectangle - only they lit, as listed; a ctrl drag'
  + ' being made lights its rectangle too; a rectangle lit as listed, the gutter not; none none', chosen[6],
  [[['1lot'], ['1lot']], ['1lot', '2owner', '2value', '3owner', '3value'], [['0lot', '0owner', '1lot', '1owner'], ['0lot', '0owner', '1lot', '1owner']], []]);
eq('R5 the cells a command acts on: the selection over the focused cell; no selection - the focused cell when its column'
  + ' counts (the gutter not, unless every column is asked); no focus - none', chosen[5],
  [['0lot', '0owner'], ['7owner'], [[], ['7#']], []]);
// a pivot page: «K» its key column, «I:a» an item whose cells are long rows' value cells - two grid cells, one stored cell
const LONG = { 'g1|I:a': 'r1', 'g1|I:b': 'r2', 'g2|I:a': 'r1' };
const targetOf = ({ rowIndex, colId }) => (colId === 'K' ? null : { rowId: LONG[`g${rowIndex}|${colId}`], column: 'value' });
const paintsOf = (m) => m.paintTargets([{ rowIndex: 1, colId: 'K' }, { rowIndex: 1, colId: 'I:a' }, { rowIndex: 1, colId: 'I:b' },
  { rowIndex: 2, colId: 'I:a' }], targetOf);
eq('T1 a selection\'s paints - each stored cell once, the key cell skipped and counted', paintsOf({ paintTargets }),
  { targets: [{ rowId: 'r1', column: 'value' }, { rowId: 'r2', column: 'value' }], skipped: 1 });
eq('T2 a range painted is one write of its paints', [paintsOf({ paintTargets }).targets.map((t) => paintUpdate('T', t.rowId, t.column, 'warn', 'kim').updates.look_key)],
  [['r1/value', 'r2/value']]);

const told = (m) => {
  const item = (table, axis, key, more = {}) => ({ row_id: `id-${key}`, data: { look_table: { value: table }, look_axis: { value: axis },
    look_key: { value: key }, ...Object.fromEntries(Object.entries(more).map(([k, v]) => [k, { value: v }])) } });
  const said = (msg, entered = false) => {
    const out = m.lookBroadcast(msg, 'T', { rules: [], paints: {} }, { entered });
    return out.reread ? 'reread' : out.looks ? `draw ${Object.keys(out.looks.paints).join(',')}` : 'nothing';
  };
  return [said({ items: [item('T', 'paint', 'r1/a', { role: 'warn' })] }), said({ count: 300 }), said({ items: [] }),
    said({ items: [item('T', 'rule', 'q1', { role: 'warn', rule_when: '[value] > 1' })] }),
    said({ items: [item('U', 'paint', 'r1/a', { role: 'warn' })] }),
    said({ items: [item('T', 'row', 'r9', { position: '8' })] }, true), said({ items: [item('T', 'row', 'r9', { position: '8' })] }, false),
    said({ count: 300, edits_of: ['S', 'T'] }), said({ count: 300, edits_of: ['U'] }), said({ count: 300, edits_of: [] }),
    said({ count: 300, truncated: { edits_of: { cut: true, omitted: 120 } } }),
    said({ event: 'batch_row_delete', row_ids: ['id-1'], edits_of: ['T'] }), said({ event: 'batch_row_delete', row_ids: ['id-1'], edits_of: ['U'] })];
};
eq('B1 a paint drawn from the message; a count-only message read again (two shapes); a rule read again; another table\'s nothing;'
  + ' a place on a table read in entered order read again, not on another; a count-only message naming this table in edits_of'
  + ' read again, naming others or none nothing, its edits_of cut read again; a delete the same (D 538297673)', told({ lookBroadcast }),
  ['draw r1/a', 'reread', 'reread', 'reread', 'nothing', 'reread', 'nothing', 'reread', 'nothing', 'nothing', 'reread', 'reread', 'nothing']);

// ── mutants: the whole module copied, its imports pointed at the real modules, one change ──
const SRC = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'src');
const decide = (m) => {
  const on = (rowId, column, value, writtenBy) => m.lookOf(LOOKS, rowId, column, { value, ...(writtenBy ? { written_by: writtenBy } : {}) });
  return [on('row-1', 'etch', '0.52'), on('row-2', 'cmp', '0.52', 'ai'), on('row-1', 'cmp', '0.12', 'ai'), on('row-1', 'etch', '0.12', 'ai'),
    on('row-1', 'cmp', '0.12', 'chain'), on('row-1', 'cmp', '0.12')];
};
const LOOK = ['grid_look.js', ['expression.js', 'grid_order.js'], (m) => [decide(m), paintsOf(m), told(m)]];
const STATE = ['state.js', ['grid_ledger_column.js', 'world.js', 'latest_read.js'], choose];
const MUTANTS = [
  ['M1 a paint not over the rules', LOOK, 'if (paint && paint.role) return { role: paint.role, hand: true };', ''],
  ['M2 the first rule wins, not the later', LOOK, '    role = rule.role;', '    role = role || rule.role;'],
  ['M3 a rule on every column, its columns ignored', LOOK, '(rule.columns && !rule.columns.includes(column))', 'false'],
  ['M4 a writer rule on any writer', LOOK, '    if (rule.written_by && !(cell && cell.written_by === rule.written_by)) continue;\n', ''],
  ['M5 a key cell skipped without being counted', LOOK, 'if (!at || !at.rowId) { skipped += 1; continue; }', 'if (!at || !at.rowId) continue;'],
  ['M8 a count-only broadcast not read again (a big paint never reaches another screen)', LOOK, '  if (!items.length) return Array.isArray(msg && msg.edits_of) && !msg.edits_of.includes(table) ? {} : { reread: true };\n', ''],
  ['M9 edits_of ignored (every screen reads again on any big paint)', LOOK, 'Array.isArray(msg && msg.edits_of) && !msg.edits_of.includes(table)', 'false'],
  ['M10 a count-only message without edits_of not read again', LOOK, 'Array.isArray(msg && msg.edits_of) && !msg.edits_of.includes(table)', '!(msg.edits_of || []).includes(table)'],
  ['M6 the ctrl-clicked cells not first', STATE, 'if (!rectangle && anyKey(clicked)) return', 'if (false) return'],
  ['M7 the gutter and every column counted', STATE, 'within(shape.cols, map[id]) && keep(id))', 'within(shape.cols, map[id]))'],
  ['M11 no focused cell when nothing is selected', STATE, 'return colId && keep(colId) ? [{ rowIndex: focused.rowIndex, colId }] : [];', 'return [];'],
  ['M13 the highlight lights the rectangle beside the ctrl-clicked cells (what is seen is not what is touched)', STATE,
    'const drawn = state.isDraggingRange ? selection(true) : null;', 'const drawn = selection(true);'],
  ['M14 the highlight lights the gutter', STATE, 'if (!shape || !keep(colId)) return false;', 'if (!shape) return false;'],
  ['M12 the focused cell whatever its column', STATE, 'return colId && keep(colId) ?', 'return colId ?'],
];
for (const [name, [module, deps, cases], from, to] of MUTANTS) {
  const dir = mkdtempSync(path.join(tmpdir(), 'look-mutant-'));
  try {
    let { text } = readSourceText(path.join(SRC, module));     // LF whatever the checkout did
    if (!text.includes(from)) { eq(`${name}: its anchor is in ${module}`, false, true); continue; }
    for (const dep of deps) text = text.replace(`'./${dep}'`, `'${pathToFileURL(path.join(SRC, dep)).href}'`);
    const file = path.join(dir, module);
    writeFileSync(file, text.replace(from, to));
    const real = JSON.stringify(cases(module === 'state.js' ? stateModule : { lookOf, paintTargets, lookBroadcast }));
    let caught;
    try { caught = JSON.stringify(cases(await import(pathToFileURL(file).href))) !== real; } catch (e) { caught = `threw ${e.message}`; }
    eq(`${name}: caught`, caught, true);
  } finally { rmSync(dir, { recursive: true, force: true }); }
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
