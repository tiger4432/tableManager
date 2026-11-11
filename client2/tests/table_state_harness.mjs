// table_state.js - the open tables and what each was left as (owner 11-05 ㄱ, mockup v3): settings in the browser,
// rows in memory for the last five; two stores on one page do not meet; a browser that refuses storage still works.
import { TableStateStore, splitSnapshot } from '../src/table_state.js';

let pass = 0;
const failures = [];
const eq = (name, got, want) => {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { pass += 1; console.log(`  PASS ${name}`); } else { failures.push(name); console.log(`  FAIL ${name} - expected ${w}, got ${g}`); }
};
const memoryStorage = () => {
  const m = new Map();
  return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: (k) => m.delete(k), m };
};
const snap = (table, extra = {}) => ({ filterModel: { lot: { values: [table] } }, serverSort: { col: 'a', dir: 'asc' },
  columnState: [{ colId: 'a', hide: false, width: 120 }], scrollTop: 40, selectedRowId: 'r1', pivot: null,
  pages: [[100, { data: [{ row_id: `${table}-1` }], count: { total: 1 } }]], currentSkip: 100, hasMoreData: true, allDataLoaded: false, ...extra });

console.log('[S] the store');
{
  const storage = memoryStorage();
  const store = new TableStateStore({ storage });
  store.opened('a'); store.opened('b'); store.opened('a');
  eq('S1 tables opened once each, in the order opened', store.tables(), ['a', 'b']);
  store.park('a', snap('a'));
  const back = store.take('a');
  eq('S2 a table left comes back as it was left - settings and rows',
    [back.settings.filterModel, back.settings.scrollTop, back.data.pages[0][1].data, back.data.currentSkip],
    [{ lot: { values: ['a'] } }, 40, [{ row_id: 'a-1' }], 100]);
  eq('S3 settings are in the browser, rows are not', Object.keys(JSON.parse(storage.m.get('grid-table:a'))).includes('pages'), false);
  eq('S4 a table never seen: no settings, no rows', store.take('zz'), { settings: null, data: null });

  for (const t of ['t1', 't2', 't3', 't4', 't5', 't6']) store.park(t, snap(t));
  eq('S5 rows for the last five tables only - the oldest let go, its settings kept',
    [store.take('a').data, store.take('a').settings !== null, store.take('t6').data !== null], [null, true, true]);

  const reload = new TableStateStore({ storage });
  eq('S6 after a reload: the tabs and settings come back, the rows do not', [reload.tables(), reload.take('t6').data, reload.take('t6').settings.scrollTop],
    [['a', 'b'], null, 40]);

  store.close('a');
  eq('S7 a tab closed: off the row, its rows and settings forgotten - here and in the browser (owner 11-11 × = forget)',
    [store.tables(), store.take('a'), storage.m.has('grid-table:a'), new TableStateStore({ storage }).take('a')],
    [['b'], { settings: null, data: null }, false, { settings: null, data: null }]);
}

console.log('[I] two stores on one page');
{
  const one = new TableStateStore({ storage: memoryStorage() });
  const two = new TableStateStore({ storage: memoryStorage() });
  one.opened('x'); one.park('x', snap('x'));
  eq('I1 the other store has nothing of it', [two.tables(), two.take('x')], [[], { settings: null, data: null }]);
}

console.log('[N] a browser that refuses storage');
{
  const refusing = { getItem: () => { throw new Error('blocked'); }, setItem: () => { throw new Error('blocked'); }, removeItem() {} };
  const store = new TableStateStore({ storage: refusing });
  store.opened('a'); store.park('a', snap('a'));
  eq('N1 nothing thrown - the tabs, settings and pages held for this page', [store.tables(), store.take('a').data.pages.length, store.take('a').settings.scrollTop],
    [['a'], 1, 40]);
  eq('N2 no storage at all works the same', new TableStateStore().take('a'), { settings: null, data: null });
}

console.log('[P] splitSnapshot');
eq('P1 no pages read: data is null, not an empty page', [splitSnapshot({ scrollTop: 1 }).data, splitSnapshot({ pages: [] }).data], [null, null]);

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length ? 1 : 0);
