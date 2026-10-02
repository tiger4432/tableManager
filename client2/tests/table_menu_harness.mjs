// The main grid's table dropdown, grouped by the operator's `group` (lead 685f236d7, owner 10-02).
//
// Scores `table_menu.js` (the sections and their drawing) and the three seats in `api.js` that use
// it: the list load keeps `groups`, the search box narrows, and a table switch keeps the opened
// table in the list whatever the search says. It imports its subjects; the page around them is a
// small fake DOM, enough for `api.js` to import and draw.
//
// CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).

// ── a DOM whose `innerHTML = ''` clears, as the browser's does ─────────────────────────
function fakeNode(tag) {
  const node = {
    tagName: String(tag).toUpperCase(), children: [], label: '', textContent: '', style: {},
    dataset: {}, attrs: {}, _value: '',
    set innerHTML(v) { this.children.length = 0; this._html = String(v); },
    get innerHTML() { return this._html || ''; },
    appendChild(c) { this.children.push(c); return c; },
    setAttribute(k, v) { this.attrs[k] = String(v); }, getAttribute(k) { return this.attrs[k] ?? null; },
    removeAttribute(k) { delete this.attrs[k]; }, hasAttribute(k) { return k in this.attrs; },
    addEventListener() {}, removeEventListener() {}, focus() {}, blur() {}, remove() {},
    querySelector: () => null, querySelectorAll: () => [],
    classList: { add() {}, remove() {}, contains: () => false, toggle: () => false },
    // a <select>'s value is one of its options' or nothing, as in the browser
    set value(v) { this._value = optionsOf(this).some((o) => o.value === v) ? v : (this.tagName === 'SELECT' ? '' : v); },
    get value() { return this._value; },
  };
  return node;
}
const optionsOf = (n) => n.children.flatMap((c) => (c.tagName === 'OPTGROUP' ? c.children : [c]))
  .filter((c) => c.tagName === 'OPTION');
const byId = new Map();
globalThis.window = { currentTable: null, addEventListener() {}, removeEventListener() {},
  location: { port: '', origin: 'http://box', href: 'http://box/', hash: '', search: '' },
  matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }) };
globalThis.document = {
  hidden: false, activeElement: null, body: fakeNode('body'),
  getElementById: (id) => { if (!byId.has(id)) byId.set(id, fakeNode(id === 'table-select' ? 'select' : 'input')); return byId.get(id); },
  createElement: (tag) => fakeNode(tag), querySelector: () => null, querySelectorAll: () => [],
  addEventListener() {}, removeEventListener() {},
};
let answer = null;
globalThis.fetch = async (url) => ({ ok: true, status: 200,
  json: async () => (String(url).endsWith('/tables') ? answer : {}), text: async () => '' });

const { tableMenu, fillTableSelect, OTHER_GROUP } = await import('../src/table_menu.js');
const api = await import('../src/api.js');
const { state } = await import('../src/state.js');

let pass = 0, fail = 0;
const failedNames = [];
const eq = (name, got, want) => {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { pass++; console.log(`  OK   ${name}`); }
  else { fail++; failedNames.push(name); console.log(`  BAD  ${name}\n        got  ${g}\n        want ${w}`); }
};
const drawn = (select) => select.children.map((c) => (c.tagName === 'OPTGROUP'
  ? [c.label, c.children.map((o) => o.value)] : c.value));

const TABLES = ['wafer_process', 'lot_master', 'ledger_atom_rows', 'dt_log', 'mi_gauge', 'dt_job'];
const GROUPS = { wafer_process: 'Process', dt_log: 'Logs', ledger_atom_rows: 'Ledger', dt_job: 'Logs' };

console.log('-- the sections ------------------------------------------------------');
const menu = tableMenu(TABLES, GROUPS);
eq('M1 groups by name, each group\'s tables in the server\'s order, the ungrouped under Other last',
  menu, [{ group: 'Ledger', tables: ['ledger_atom_rows'] }, { group: 'Logs', tables: ['dt_log', 'dt_job'] },
    { group: 'Process', tables: ['wafer_process'] }, { group: OTHER_GROUP, tables: ['lot_master', 'mi_gauge'] }]);
eq('M2 every table once - the same set as the list', menu.flatMap((s) => s.tables).sort(), TABLES.slice().sort());
eq('M3 Other is last even when a group sorts after it', tableMenu(['a', 'b'], { a: 'Zeta' }).map((s) => s.group),
  ['Zeta', OTHER_GROUP]);
eq('M4 an answer without groups is today\'s flat list, in the server\'s order',
  tableMenu(TABLES, undefined), [{ group: null, tables: TABLES }]);
eq('M5 ... and so is one where no table wrote a group (no lone Other head)',
  tableMenu(TABLES, {}), [{ group: null, tables: TABLES }]);
eq('M6 a search keeps the names that contain it, any case, and drops a group left empty',
  tableMenu(TABLES, GROUPS, '  DT_ '), [{ group: 'Logs', tables: ['dt_log', 'dt_job'] }]);
eq('M7 the open table stays under a search that does not match it, in its own group',
  tableMenu(TABLES, GROUPS, 'dt_', 'lot_master'),
  [{ group: 'Logs', tables: ['dt_log', 'dt_job'] }, { group: OTHER_GROUP, tables: ['lot_master'] }]);
eq('M8 a search that matches nothing and no open table is no section', tableMenu(TABLES, GROUPS, 'zzz'), []);

console.log('-- the drawing -------------------------------------------------------');
const sel = fakeNode('select');
fillTableSelect(sel, menu, 'dt_job', document);
eq('D1 an <optgroup> per group, labelled with it, holding its options', drawn(sel),
  [['Ledger', ['ledger_atom_rows']], ['Logs', ['dt_log', 'dt_job']], ['Process', ['wafer_process']],
    [OTHER_GROUP, ['lot_master', 'mi_gauge']]]);
eq('D2 the open table is the selected one, inside its group', sel.value, 'dt_job');
fillTableSelect(sel, tableMenu(TABLES, undefined), 'lot_master', document);
eq('D3 the flat list draws bare options, no group heads, as today', drawn(sel), TABLES);

console.log('-- the page\'s seats (api.js) ----------------------------------------');
const select = document.getElementById('table-select');
const search = document.getElementById('table-search');
answer = { tables: TABLES, groups: GROUPS, kinds: {}, map_key_columns: {} };
try { await api.loadTables(); } catch (e) { /* switchTable walks further than this page goes */ }
eq('P1 the list load keeps the answer\'s groups beside its tables', state.tableList,
  { tables: TABLES, groups: GROUPS });
state.currentTable = 'wafer_process';
search.value = 'log';
api.drawTableMenu();
eq('P2 typing narrows the dropdown, the open table kept in its group', drawn(select),
  [['Logs', ['dt_log']], ['Process', ['wafer_process']]]);
try { await api.switchTable('mi_gauge'); } catch (e) { /* as above */ }
eq('P3 switching to a table the search hides (a history jump) puts it in the list and selects it',
  [drawn(select), select.value], [[['Logs', ['dt_log']], [OTHER_GROUP, ['mi_gauge']]], 'mi_gauge']);
search.value = '';
api.drawTableMenu('mi_gauge');
eq('P4 clearing the search brings every table back', drawn(select).flatMap((s) => s[1]).sort(), TABLES.slice().sort());

console.log(`\n${pass} passed, ${fail} failed`);
if (failedNames.length) console.log(`FAILED: ${failedNames.join(' | ')}`);
console.log(`ASSERTIONS ${pass + fail} ${fail}`);
if (fail) process.exit(1);
