// The main grid's pivot (owner 10-22, lead ㄱ ①) - what the grid makes of the server's pivot answer and what one cell's
// write sends. The subject is imported (grid_pivot.js, narrowing.js, match_count.js - no DOM).
//
//   rows     a key group is one grid row: its keys, its cells as «item:<value>» each with the long row it is
//   columns  the keys, then the items; before the first answer the declaration's keys
//   write    a cell with a row writes that row's value; a blank cell its keys, its item and the value - the row made
//   narrow   pivot=true rides the one narrowing (data and count alike); the footer says groups when told so
//   memory   per table, and a storage that throws keeps nothing and breaks nothing
//
// Run: node client2/tests/grid_pivot_harness.mjs
import { pivotRows, pivotColumns, pivotUpdate, pivotWire, keyColumnsIn, itemColId, itemOf, rememberedPivot, rememberPivot,
  newPivotRows, isNewPivotRow, pivotWriteRefusal, holdNewRowKeys, groupFilters, strayLongRow, PIVOT_KEY_NOTE, PIVOT_NEW_KEYS_NOTE } from '../src/grid_pivot.js';
import { narrowingParams } from '../src/narrowing.js';
import { matchCountText } from '../src/match_count.js';

let pass = 0;
const failures = [];
function eq(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { pass++; console.log(`  PASS ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name}\n        got  ${g}\n        want ${w}`); }
}

// the server's answer (server/tests/test_the_grid_pivots_a_long_table_by_its_item_key.py's table): W2 has no «b»
const VIEW = { column: 'itemid', value: 'value', keys: ['lot', 'wafer'], items: ['a', 'b', 'c'], items_more: 2 };
const ANSWER = { pivot: VIEW, data: [
  { lot: 'L1', wafer: 'W1', cells: { a: { value: 1, row_id: 'r1' }, b: { value: 5, row_id: 'r2' }, c: { value: 9, row_id: 'r3' } } },
  { lot: 'L1', wafer: 'W2', cells: { a: { value: 2, row_id: 'r4' }, c: { value: 7, row_id: 'r5' } } },
] };

console.log('-- rows --');
const rows = pivotRows(ANSWER);
eq('R1 one grid row per key group', rows.length, 2);
eq('R2 a group keeps its keys as cells', [rows[0].data.lot.value, rows[0].data.wafer.value], ['L1', 'W1']);
eq('R3 an item cell is «item:<value>» with its value and the long row it is', rows[0].data['item:b'], { value: 5, row_id: 'r2' });
eq('R4 an item the group lacks is no cell (blank)', rows[1].data['item:b'], undefined);
eq('R5 groups have distinct row ids', rows[0].row_id !== rows[1].row_id, true);
eq('R6 no group row id is a long row\'s', rows.some((r) => ['r1', 'r2', 'r3', 'r4', 'r5'].includes(r.row_id)), false);

console.log('-- columns --');
eq('C1 the keys, then the items as «item:<value>»', pivotColumns(VIEW, { column: 'itemid', value: 'value' }, []),
  ['lot', 'wafer', 'item:a', 'item:b', 'item:c']);
eq('C2 before the first answer: the declaration\'s keys less the item column',
  pivotColumns(null, { column: 'itemid', value: 'value' }, ['lot', 'wafer', 'itemid']), ['lot', 'wafer']);
eq('C3 itemOf names an item column\'s item and nothing else', [itemOf(itemColId('x y')), itemOf('lot'), itemOf(undefined)], ['x y', null, null]);

console.log('-- write --');
eq('W1 a cell with a row writes that row\'s value column', pivotUpdate(VIEW, rows[0], 'item:b', 6), { row_id: 'r2', updates: { value: 6 } });
eq('W2 a blank cell writes its keys, its item and the value - no row_id', pivotUpdate(VIEW, rows[1], 'item:b', 3),
  { updates: { lot: 'L1', wafer: 'W2', itemid: 'b', value: 3 } });

console.log('-- many cells (part ②) --');
// a 3x3 paste over three groups and items a, b, c; W2 has no «b» - eight cells with a row, one blank
const ANSWER3 = { pivot: VIEW, data: [...ANSWER.data,
  { lot: 'L2', wafer: 'W1', cells: { a: { value: 3, row_id: 'r6' }, b: { value: 4, row_id: 'r7' }, c: { value: 8, row_id: 'r8' } } }] };
const rows3 = pivotRows(ANSWER3);
const rowOf = (id) => rows3.find((r) => r.row_id === id);
const paste = rows3.map((r, i) => ({ row_id: r.row_id, updates: { 'item:a': 10 + i, 'item:b': 20 + i, 'item:c': 30 + i },
  source_name: 'user', updated_by: 'u' }));
const wire = pivotWire(VIEW, paste, rowOf);
eq('P1 a 3x3 paste is nine updates: eight with their long row, one with its keys and item', [wire.length,
  wire.filter((u) => u.row_id).map((u) => u.row_id), wire.filter((u) => !u.row_id).map((u) => u.updates)],
  [9, ['r1', 'r2', 'r3', 'r4', 'r5', 'r6', 'r7', 'r8'], [{ lot: 'L1', wafer: 'W2', itemid: 'b', value: 21 }]]);
eq('P2 each carries its cell\'s value under the value column, and the batch\'s own fields',
  [wire[0].updates, wire.every((u) => u.source_name === 'user' && u.updated_by === 'u')], [{ value: 10 }, true]);
eq('P3 no pivot view: the updates as they are', pivotWire(null, paste, rowOf) === paste, true);
eq('K1 a write reaching a key column names it; items alone name none',
  [keyColumnsIn([{ updates: { 'item:a': 1, lot: 'x' } }, { updates: { lot: 'y', wafer: 'z' } }]), keyColumnsIn(paste)],
  [['lot', 'wafer'], []]);

console.log('-- new rows and deleted groups (owner 10-23) --');
const [fresh] = newPivotRows(1, 5);
const item = (row, updates) => ({ rowNode: { data: row }, updates });
eq('R1 a new row is the screen\'s: its own id, nothing in it, no group\'s id', [isNewPivotRow(fresh.row_id), fresh.data,
  isNewPivotRow(rows3[0].row_id)], [true, {}, false]);
const keysOnly = item(fresh, { lot: 'L9', wafer: 'W9' });
eq('R2 its keys go, and are held on it - not written', [pivotWriteRefusal(VIEW, [keysOnly]), holdNewRowKeys(VIEW, [keysOnly]),
  keysOnly.updates, fresh.data], ['', true, {}, { lot: { value: 'L9' }, wafer: { value: 'W9' } }]);
const [halfKeyed] = newPivotRows(1, 6);
eq('R3 a value on a new row with a key blank is refused - the keys this write brings counted',
  [pivotWriteRefusal(VIEW, [item(halfKeyed, { lot: 'L9', 'item:a': 1 })]),
    pivotWriteRefusal(VIEW, [item(halfKeyed, { lot: 'L9', wafer: ' ', 'item:a': 1 })]),
    pivotWriteRefusal(VIEW, [item(halfKeyed, { lot: 'L9', wafer: 'W9', 'item:a': 1 })])],
  [PIVOT_NEW_KEYS_NOTE, PIVOT_NEW_KEYS_NOTE, '']);
eq('R4 a saved group\'s key cell refuses the whole write, a new row\'s beside it too',
  pivotWriteRefusal(VIEW, [item(rows3[0], { lot: 'X' }), item(fresh, { lot: 'L8' })]), PIVOT_KEY_NOTE);
const heldWire = pivotWire(VIEW, [{ row_id: fresh.row_id, updates: { 'item:b': 3 } }], () => fresh);
eq('R5 its value goes as a blank cell\'s: its held keys, its item, the value', heldWire.map((u) => u.updates),
  [{ lot: 'L9', wafer: 'W9', itemid: 'b', value: 3 }]);
eq('D1 a group\'s long rows are read by its keys - a blank key by blank', [groupFilters(VIEW, rows3[0]),
  groupFilters(VIEW, { data: { lot: { value: 'L1' }, wafer: { value: '' } } })],
  [{ lot: { type: 'equals', filter: 'L1' }, wafer: { type: 'equals', filter: 'W1' } }, { lot: { type: 'equals', filter: 'L1' }, wafer: { type: 'blank' } }]);
const longRow = (lot, wafer) => ({ row_id: `${lot}${wafer}`, data: { lot: { value: lot }, wafer: { value: wafer }, itemid: { value: 'z' } } });
eq('D2 a read that brings another group\'s row is caught, naming the key, what was asked and what came',
  [strayLongRow(VIEW, rows3[0], [longRow('L1', 'W1'), longRow('L1', 'W1')]), strayLongRow(VIEW, rows3[0], [longRow('L1', 'W1'), longRow('L1', 'W2')])],
  [null, { key: 'wafer', want: 'W1', got: 'W2' }]);

console.log('-- narrowing and the footer --');
eq('N1 pivot=true rides the one narrowing', narrowingParams({ pivot: true }).get('pivot'), 'true');
eq('N2 not asked, not sent', narrowingParams({ pivot: false }).has('pivot'), false);
eq('N3 the footer counts groups when told so', matchCountText({ total: 412, count: { total: 412 } }, 0, 'group').startsWith('412 groups'), true);
eq('N4 rows by default', matchCountText({ total: 412, count: { total: 412 } }, 0).startsWith('412 rows'), true);

console.log('-- memory --');
const store = new Map();
const storage = { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, v), removeItem: (k) => store.delete(k) };
rememberPivot(storage, 'long_t', true);
eq('M1 kept per table', [rememberedPivot(storage, 'long_t'), rememberedPivot(storage, 'other_t')], [true, false]);
rememberPivot(storage, 'long_t', false);
eq('M2 switched off, forgotten', rememberedPivot(storage, 'long_t'), false);
const throwing = { getItem: () => { throw new Error('blocked'); }, setItem: () => { throw new Error('blocked'); }, removeItem: () => { throw new Error('blocked'); } };
let threw = false;
try { rememberPivot(throwing, 't', true); } catch (e) { threw = true; }
eq('M3 a storage that throws: not kept, not thrown', [threw, rememberedPivot(throwing, 't'), rememberedPivot(null, 't')], [false, false, false]);

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
