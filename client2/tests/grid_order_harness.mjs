// A table read in its entered order, and the place a drag writes (owner 11-06). The subject is imported (grid_order.js).
//
//   between  a place stands strictly between its neighbours, as the server's ORDER BY compares text - under uuid7 row
//            ids, under places made before it, at the start and at the end; a thousand drags into one gap stay in order
//   drop     a drop's neighbours are the rows it lands between; at an edge whose other side is another page it is
//            refused; the same place is no move
//   write    one sys_looks update - the table, the axis, the first row_id, the place
//   live     a sys_looks broadcast is this table's when an item says so, or says no items - not a place this screen wrote
//
// Run: node client2/tests/grid_order_harness.mjs
import { placeBetween, dropPlace, placeUpdate, placesOn, placeWord, PLACE_OFF_PAGE_NOTE, PLACE_STALE_NOTE, ENTERED, LOOK_TABLE }
  from '../src/grid_order.js';

let pass = 0;
const failures = [];
function eq(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { pass++; console.log(`  PASS ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name}\n        got  ${g}\n        want ${w}`); }
}

// uuid7 text as the engine mints it - time-ordered, lowercase hex and «-»
const IDS = ['019a5f2e-1c00-7000-8000-000000000001', '019a5f2e-1c00-7000-8000-000000000002',
  '019a5f2e-1c01-7abc-9def-0123456789ab', '019a5f2f-0000-7fff-bfff-ffffffffffff'];
const inOrder = (keys) => keys.every((k, i) => i === 0 || keys[i - 1] < k);
const sortsAsBytes = (keys) => JSON.stringify([...keys].sort()) === JSON.stringify(keys);

eq('E0 the sort name and the table are the server\'s', [ENTERED, LOOK_TABLE], ['entered', 'sys_looks']);

const mid = placeBetween(IDS[0], IDS[1]);
eq('B1 between two row ids: strictly between', [IDS[0] < mid, mid < IDS[1]], [true, true]);
const first = placeBetween(null, IDS[0]);
const last = placeBetween(IDS[3], null);
eq('B2 the start and the end', [first < IDS[0], IDS[3] < last, /[^0-9a-f-]/.test(first + last)], [true, true, false]);
eq('B3 neighbours out of order: no place', [placeBetween(IDS[1], IDS[0]), placeBetween(IDS[0], IDS[0])], [null, null]);

// a thousand drags, each into a gap a random pair of neighbours leaves - the list stays in order, as bytes sort it
let keys = [...IDS];
let seed = 7;
const rnd = (n) => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed % n; };
let none = 0;
for (let i = 0; i < 1000; i += 1) {
  const at = rnd(keys.length + 1);
  const place = placeBetween(at > 0 ? keys[at - 1] : null, at < keys.length ? keys[at] : null);
  if (place === null) { none += 1; continue; }
  keys = [...keys.slice(0, at), place, ...keys.slice(at)];
}
eq('B4 1,000 drags into random gaps: every place made, in order, as bytes sort them',
  [none, keys.length, inOrder(keys), sortsAsBytes(keys)], [0, 1004, true, true]);
// a thousand into the same gap - the deepest case, every place under the last one made
let low = IDS[0];
const high = IDS[1];
const deep = [];
for (let i = 0; i < 1000; i += 1) { const p = placeBetween(low, high); deep.push(p); low = p; }
eq('B5 1,000 drags into one gap: each between the last and the next', [deep.every((p) => p !== null), inOrder([IDS[0], ...deep, high]),
  deep[999].length < 1100], [true, true, true]);
let top = IDS[0];
const tops = [];
for (let i = 0; i < 200; i += 1) { const p = placeBetween(null, top); tops.push(p); top = p; }
eq('B6 200 drags to the very top: each under the one before', [tops.every((p) => p !== null), inOrder([...tops].reverse())], [true, true]);

const page = [IDS[0], IDS[1], IDS[2], IDS[3]];
const down = dropPlace(page, 0, 2);
eq('D1 down: lands after the row it is dropped on', [IDS[2] < down.place, down.place < IDS[3]], [true, true]);
const up = dropPlace(page, 3, 1);
eq('D2 up: lands before the row it is dropped on', [IDS[0] < up.place, up.place < IDS[1]], [true, true]);
eq('D3 the same place: no move; off the list: no move', [dropPlace(page, 2, 2), dropPlace(page, 2, 9)], [null, null]);
eq('D4 the top of a page with one before it, the bottom of one with one after: refused',
  [dropPlace(page, 2, 0, { openStart: true }), dropPlace(page, 1, 3, { openEnd: true })],
  [{ refused: PLACE_OFF_PAGE_NOTE }, { refused: PLACE_OFF_PAGE_NOTE }]);
eq('D5 the top of the first page, the bottom of the last: a place', [Boolean(dropPlace(page, 2, 0).place), Boolean(dropPlace(page, 1, 3).place)],
  [true, true]);
eq('D6 neighbours out of order (a stale read): refused', dropPlace([IDS[1], IDS[0], IDS[2]], 2, 1), { refused: PLACE_STALE_NOTE });

eq('W1 one sys_looks update', placeUpdate('plan', 'group', IDS[0], '08', 'kim'),
  { updates: { look_table: 'plan', look_axis: 'group', look_key: IDS[0], position: '08' }, source_name: 'user', updated_by: 'kim' });

eq('L1 a broadcast of this table\'s place, another\'s, one without items',
  [placesOn({ items: [{ data: { look_table: { value: 'plan' }, look_axis: { value: 'row' } } }] }, 'plan'),
    placesOn({ items: [{ data: { look_table: { value: 'other' }, look_axis: { value: 'row' } } }] }, 'plan'), placesOn({ count: 300 }, 'plan')], [true, false, true]);

const told = { items: [{ data: { look_table: { value: 'plan' }, look_axis: { value: 'group' }, look_key: { value: IDS[0] }, position: { value: '08' } } }] };
eq('L2 the place this screen wrote itself: not read again; another place: read', [placesOn(told, 'plan', new Set([placeWord(IDS[0], '08')])),
  placesOn(told, 'plan', new Set([placeWord(IDS[0], '09')]))], [false, true]);

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
