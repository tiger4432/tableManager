// STAGED SWITCH - staged edits stand: every way to another table is refused while they are there, in the pivot button's
// one sentence, and goes through when there are none (owner 11-05 ㄱ2; the switch dropped them unsaid till 11-09).
// Run: node client2/tests/staged_switch_harness.mjs
//
//   The six ways in (git grep "switchTable(" -- client2/src, map_editor.js's own aside):
//     W1 boot (loadTables, the address's table)      W2 the dropdown (main.js: switchTable(value), nothing after)
//     W3 the Flow strip's «Edit» (editTableDescription)   W4 the Flow strip's table link (main.js: switchTable(name))
//     W5 a ledger receipt's jump (navigateToLog)      W6 a history line's jump (navigateToLog)
//   R<n> staged: the table does not change, the edits stay, the sentence is said, the target is not read; the dropdown is
//        back on the open table; a jump lets go of its guard. G<n> none staged: the table changes to the target.
//   W2 and W4 are main.js handlers, which runs init() on import: they are driven as the call they make.
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { makeDoc } from './lib/board_dom.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = (name) => path.join(HERE, '..', 'src', name);

const doc = makeDoc('light');
doc.addEventListener = () => {};
doc.removeEventListener = () => {};
const rect = () => ({ left: 0, right: 0, top: 0, bottom: 0, width: 0, height: 0 });
const make = doc.createElement.bind(doc);
doc.createElement = (tag) => { const el = make(tag); if (!el.getBoundingClientRect) el.getBoundingClientRect = rect; return el; };
const byId = new Map();
doc.getElementById = (id) => { if (!byId.has(id)) { const el = doc.createElement('div'); el.setAttribute('id', id); byId.set(id, el); } return byId.get(id); };
doc.querySelectorAll = () => [];
globalThis.document = doc;
globalThis.window = {
  location: { port: '', origin: 'http://box', href: 'http://box/?table=b&tx=tx1', hash: '', search: '?table=b&tx=tx1' },
  addEventListener() {}, removeEventListener() {},
  matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
};

const { state } = await import('../src/state.js');
const SENTENCE = 'Apply or discard the staged edits first';
const settle = async () => { for (let i = 0; i < 20; i += 1) await new Promise((r) => setTimeout(r, 0)); };
const quietly = async (fn) => {
  const say = [console.log, console.error, console.warn];
  console.log = () => {}; console.error = () => {}; console.warn = () => {};
  try { return await fn(); } finally { [console.log, console.error, console.warn] = say; }
};

/** Table «a» open, «b» and sys_tables in the list; staged edits or none; every GET and grid filter recorded. What a way does
 *  after its switch is what a refused way must not do: a transaction filter (boot's address, both jumps), a grid filter
 *  (the Flow «Edit»). */
function stage(staged) {
  const urls = [];
  const filtered = [];
  state.tableList = { tables: ['a', 'b', 'sys_tables'], groups: {} };
  state.currentTable = 'a';
  state.currentTransactionId = null;
  state.pendingTxEdits = staged ? { 'r1::lot': { rowId: 'r1', col: 'lot', value: 'L9' } } : {};
  state.isNavigating = false;
  state.navigationJump = null;
  // a grid to filter only where a refusal is scored - the switch itself goes further without one
  state.gridApi = staged ? { getFilterModel: () => ({}), setFilterModel: (m) => filtered.push(m), addEventListener() {}, removeEventListener() {} } : null;
  urls.filtered = filtered;
  document.getElementById('table-select').value = 'a';
  document.getElementById('performance-log').textContent = '';
  globalThis.fetch = async (url) => {
    urls.push(String(url));
    const body = /\/tables$/.test(String(url)) ? { tables: ['a', 'b', 'sys_tables'] } : {};
    return { ok: true, status: 200, json: async () => body, text: async () => JSON.stringify(body) };
  };
  return urls;
}

const WAYS = [
  ['W1', 'boot', 'b', (M) => M.api.loadTables()],
  ['W2', 'dropdown', 'b', (M) => { document.getElementById('table-select').value = 'b'; return M.api.switchTable('b'); }],
  ['W3', 'Flow «Edit»', 'sys_tables', (M) => M.api.editTableDescription('b')],
  ['W4', 'Flow table link', 'b', (M) => M.api.switchTable('b')],
  ['W5', 'ledger receipt jump', 'b', (M) => M.timeline.navigateToLog({ column_name: M.timeline.LEDGER_BATCH_COLUMN, table_name: 'b', transaction_id: 'tx1' })],
  ['W6', 'history jump', 'b', (M) => M.timeline.navigateToLog({ column_name: 'lot', table_name: 'b', row_id: 'r1', transaction_id: 'tx1' })],
];

async function suite(M) {
  const names = [];
  const fails = [];
  const say = (name, cond, detail) => {
    names.push(name);
    if (cond) { console.log(`  PASS ${name}`); return; }
    fails.push(name);
    console.log(`  FAIL ${name}${detail ? ' -- ' + detail : ''}`);
  };
  console.log('\n[R] staged edits: refused');
  for (const [id, way, target, go] of WAYS) {
    const urls = stage(true);
    const edits = state.pendingTxEdits;
    await quietly(async () => { try { await go(M); } catch (e) { /* the stub ends before the grid does */ } await settle(); });
    const seen = { table: state.currentTable, edits: Object.keys(state.pendingTxEdits), same: state.pendingTxEdits === edits,
      said: document.getElementById('performance-log').textContent, select: document.getElementById('table-select').value,
      navigating: state.isNavigating, targetRead: urls.some((u) => u.includes(`/tables/${target}/`)),
      tx: state.currentTransactionId, filtered: urls.filtered.length };
    say(`R${id.slice(1)} ${way}: stays on a, edits kept, «${SENTENCE}», ${target} not read, dropdown on a, no jump held, `
      + 'no transaction or grid filter set', seen.table === 'a' && seen.same && seen.edits.length === 1 && seen.said === SENTENCE
        && !seen.targetRead && seen.select === 'a' && seen.navigating === false && seen.tx === null && seen.filtered === 0,
      JSON.stringify(seen));
  }
  console.log('\n[G] none staged: switched');
  for (const [id, way, target, go] of WAYS) {
    const urls = stage(false);
    await quietly(async () => { try { await go(M); } catch (e) { /* as above */ } await settle(); });
    say(`G${id.slice(1)} ${way}: the table is ${target}, its columns asked`,
      state.currentTable === target && urls.some((u) => u.includes(`/tables/${target}/schema`)),
      JSON.stringify({ table: state.currentTable, urls: urls.slice(0, 4) }));
  }
  if (state.navigationWatchdog) clearTimeout(state.navigationWatchdog);
  return { ran: names.length, names, failures: fails };
}

const M = { api: await import('../src/api.js'), timeline: await import('../src/timeline.js') };
const base = await suite(M);
let pass = base.ran - base.failures.length;
const failures = [...base.failures];

const { loadWithProbe } = await import('./lib/probe.mjs');
const { scoreMutants } = await import('./lib/mutation_scorer.mjs');
const swap = (text, from, to) => {
  if (!text.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`);
  return text.split(from).join(to);
};
const MUTANTS = [
  { id: 'X1', what: 'the switch drops the staged edits unsaid, as before 11-09', catches: 'R2', file: 'api.js',
    from: '  if (refuseOverStaged()) {\n    drawTableMenu(state.currentTable);\n    return false;\n  }\n', to: '  state.pendingTxEdits = {};\n' },
  { id: 'X2', what: 'refused, the dropdown left on the table asked', catches: 'R2', file: 'api.js',
    from: '    drawTableMenu(state.currentTable);\n    return false;', to: '    return false;' },
  { id: 'X3', what: 'the Flow «Edit» filters the open table after a refused switch', catches: 'R3', file: 'api.js',
    from: "  if (!(await switchTable('sys_tables'))) return;", to: "  await switchTable('sys_tables');" },
  { id: 'X4', what: 'a refused history jump holds its guard till the watchdog', catches: 'R6', file: 'timeline.js',
    from: "{ releaseNavigationGuard('', jump); return; }", to: '{ return; }' },
  { id: 'X8', what: 'a refused history jump goes on and filters the open table by its transaction', catches: 'R6', file: 'timeline.js',
    from: "    if (!(await switchTable(targetTable))) { releaseNavigationGuard('', jump); return; }", to: '    await switchTable(targetTable);' },
  { id: 'X5', what: 'a refused ledger receipt jump filters the open table by its transaction', catches: 'R5', file: 'timeline.js',
    from: '    if (!(await switchTable(log.table_name))) return;', to: '    await switchTable(log.table_name);' },
  { id: 'X6', what: 'a refused boot goes on to the address\'s transaction', catches: 'R1', file: 'api.js',
    from: '      if (await switchTable(asked.table || data.tables[0]) && asked.tx) await setTransactionFilter(asked.tx);',
    to: '      await switchTable(asked.table || data.tables[0]);\n      if (asked.tx) await setTransactionFilter(asked.tx);' },
  { id: 'X7', what: 'the refusal\'s words changed', catches: 'R4', file: 'api.js',
    from: "Object.keys(state.pendingTxEdits).length ? 'Apply or discard the staged edits first'", to: "Object.keys(state.pendingTxEdits).length ? 'Apply or discard the staged edits before switching'" },
];
const scored = await scoreMutants(MUTANTS, async (mu) => quietly(async () => {
  const mutate = (t) => swap(t, mu.from, mu.to);
  const loaded = (await loadWithProbe(SRC(mu.file), { mutate, tag: `ssw${mu.id}` })).module;
  const key = { 'api.js': 'api', 'timeline.js': 'timeline' }[mu.file];
  return suite({ ...M, [key]: loaded });
}), { baselineNames: base.names, title: '\n  [mutants] - each must be caught by the check it names.' });
pass += MUTANTS.length - scored.wrong;
for (let i = 0; i < scored.wrong; i += 1) failures.push(`mutant verdict ${i + 1}`);

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
