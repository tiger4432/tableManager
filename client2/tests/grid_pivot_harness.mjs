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
import { pivotRows, pivotColumns, pivotUpdate, itemColId, itemOf, rememberedPivot, rememberPivot } from '../src/grid_pivot.js';
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
