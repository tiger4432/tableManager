/**
 * LEDGER COLUMN — the grid's per-row 「did the ledger take it, and which source」 (lead f3bc02f6e ·
 * 533a386c6 · fb4dda078, owner 「at the end」 cdf11b222).
 *
 * The answer to 「is this table a ledger source」 has ONE seat, `GridSourceLabel.answer()`; the column
 * receives it. So every block here drives the REAL label with a served declaration, takes the answer
 * it hands out, and builds the column from it — the column never guesses from the cell.
 *
 *   A  column there or not × the label's answer (and an answer about ANOTHER table)
 *   B  the label says each source's own state; `refused` only when every source reading it is refused
 *   C  the cell × `ledger_sources` × the table's answer — every cell of that table is asserted
 *   G  the real `buildColumnDefs` puts it last, after updated_at
 *   W  the write funnels skip it (the one 「may I write this grid column」 seat)
 *
 * Every assertion is woken by a mutant below.
 */
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { makeDoc, makeNode, walk } from './lib/board_dom.mjs';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FILE = (name) => path.join(HERE, '..', 'src', name);

// grid.js reaches `window` and `document` through its imports; enough of each to load it.
const fake = (id) => ({
  id, innerHTML: '', textContent: '', value: '', checked: false, style: {}, dataset: {},
  classList: { add() {}, remove() {}, contains: () => false, toggle: () => false },
  children: [], appendChild(c) { return c; }, addEventListener() {}, removeEventListener() {},
  querySelector: () => null, querySelectorAll: () => [], setAttribute() {}, getAttribute: () => null,
  removeAttribute() {}, hasAttribute: () => false, focus() {}, blur() {}, remove() {},
});
const byId = new Map();
globalThis.window = {
  location: { port: '', origin: 'http://box', href: 'http://box/', hash: '', search: '' },
  addEventListener() {}, removeEventListener() {},
  matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
};
globalThis.document = {
  hidden: false, activeElement: null, body: fake('body'),
  getElementById: (id) => { if (!byId.has(id)) byId.set(id, fake(id)); return byId.get(id); },
  createElement: () => fake('created'), querySelector: () => null, querySelectorAll: () => [],
  addEventListener() {}, removeEventListener() {},
};

const REAL = {
  label: await import('../src/grid_source_label.js'),
  column: await import('../src/grid_ledger_column.js'),
  state: await import('../src/state.js'),
  grid: await import('../src/grid.js'),
};

/** `/api/ledger/declaration` in the shape c193986a8 serves: a refused source rides with `planned: false`. */
const REFUSAL = { code: 'source_refused', path: 'bundle.sources.bonded_from.relation',
  message: "source 'bonded_from' reads 'bonding_die_from_core', which is not a table that has row_id (view); "
    + 'a ledger source must read a table that has row_id' };
const DECLARATION = { ok: true, sources: [
  { source: 'die_inspection', relation: 'inspection_run', emits: ['inspected@1'] },
  { source: 'bonded_from', relation: 'bonding_die_from_core', emits: ['bonded_from@1'],
    planned: false, refusal: REFUSAL },
  // one table, two sources, one of them refused
  { source: 'lot_moved', relation: 'lot_event', emits: ['moved@1'] },
  { source: 'lot_held', relation: 'lot_event', emits: ['held@1'], planned: false,
    refusal: { ...REFUSAL, message: "source 'lot_held' binds a column the table does not have" } },
] };

/** The real label, served `declaration` (or a refusal), set to `relation`. Returns what it drew and told. */
async function labelled(mods, relation, declaration = DECLARATION) {
  const doc = makeDoc('light');
  const host = makeNode(doc, 'div');
  const told = [];
  const part = new mods.label.GridSourceLabel(host, {
    doc, onAnswer: (a) => told.push(a),
    loadDeclaration: declaration === 'pending' ? () => new Promise(() => {})
      : async () => declaration,
  });
  part.mount();
  await new Promise((r) => setTimeout(r, 0));
  part.setRelation(relation);
  part.render();                                   // a re-render with the same answer tells nothing new
  return { host, told, answer: told[told.length - 1] };
}

async function suite(mods) {
  const ran = [];
  const failures = [];
  const eq = (name, got, want) => {
    ran.push(name);
    const g = JSON.stringify(got); const w = JSON.stringify(want);
    if (g !== w) failures.push(`${name}: got ${g}, want ${w}`);
  };
  const { ledgerColumnDef, LEDGER_COL_ID } = mods.column;
  const shown = (answer, table) => ledgerColumnDef(answer, table) !== null;

  // ── A. the column is there exactly when the label's answer for THIS table says so ──
  const source = await labelled(mods, 'inspection_run');
  const notSource = await labelled(mods, 'dt_map');
  const unknown = await labelled(mods, 'inspection_run', { ok: false, message: 'declaration 503' });
  const pending = await labelled(mods, 'inspection_run', 'pending');
  const refused = await labelled(mods, 'bonding_die_from_core');
  const mixed = await labelled(mods, 'lot_event');
  eq('A1 a ledger source table has the column', shown(source.answer, 'inspection_run'), true);
  eq('A2 a table that is not a source has none', shown(notSource.answer, 'dt_map'), false);
  eq('A3 an unreadable declaration still stands the column (to say Unknown)',
    shown(unknown.answer, 'inspection_run'), true);
  eq('A4 while the declaration is on its way there is no column', shown(pending.answer, 'inspection_run'), false);
  eq('A5 no table chosen, no column', shown({ relation: null, state: 'idle', rows: [] }, ''), false);
  // the grid is drawn for the new table before the label hears of it
  eq('A6 an answer about another table does not stand a column here', shown(source.answer, 'dt_map'), false);
  eq('A7 a table whose only source the loader refused has the column', shown(refused.answer, 'bonding_die_from_core'), true);
  const def = ledgerColumnDef(source.answer, 'inspection_run') || {};
  eq('A8 it is called Ledger and it cannot be edited, sorted or filtered',
    [def.headerName, def.colId, def.editable, def.sortable, def.filter], ['Ledger', LEDGER_COL_ID, false, false, false]);

  // ── B. the label: one answer, each source its own line ───────────────────────────
  eq('B1 one refused source out of two leaves the table a source',
    [mixed.answer.state, walk(mixed.host).filter((n) => /grid-source-label__row/.test(n.className || '')).length],
    ['source', 2]);
  eq('B2 every source refused makes the table refused, with the loader\'s sentence',
    [refused.answer.state, refused.host.textContent.includes(`refused: ${REFUSAL.message}`)], ['refused', true]);
  eq('B3 the standing source still says what it emits',
    [mixed.host.textContent.includes('ledger source — lot_moved · emits moved@1'),
      mixed.host.textContent.includes("ledger source — lot_held · refused: source 'lot_held'")], [true, true]);
  eq('B4 the answer is told once per change, not once per render',
    source.told.map((a) => a.state), ['idle', 'source']);

  // ── C. the cell ─────────────────────────────────────────────────────────────────
  const cell = (answer, table, row) => (ledgerColumnDef(answer, table) || { valueGetter: () => '(no column)' })
    .valueGetter({ data: row });
  const TWO = { row_id: '1', ledger_sources: ['die_inspection', 'lot_moved'] };
  const NONE = { row_id: '2', ledger_sources: [] };
  const OFF = { row_id: '3' };                     // the server could not read the row index
  eq('C1 source table · names', cell(source.answer, 'inspection_run', TWO), 'die_inspection · lot_moved');
  eq('C2 source table · [] is Not yet', cell(source.answer, 'inspection_run', NONE), 'Not yet');
  eq('C3 source table · no key is Unknown, not Not yet', cell(source.answer, 'inspection_run', OFF), 'Unknown');
  eq('C4 refused table · names are still the index\'s fact', cell(refused.answer, 'bonding_die_from_core', TWO),
    'die_inspection · lot_moved');
  eq('C5 refused table · [] is Refused', cell(refused.answer, 'bonding_die_from_core', NONE), 'Refused');
  eq('C6 refused table · no key is Unknown', cell(refused.answer, 'bonding_die_from_core', OFF), 'Unknown');
  eq('C7 unreadable declaration · names', cell(unknown.answer, 'inspection_run', TWO), 'die_inspection · lot_moved');
  eq('C8 unreadable declaration · [] is Unknown, not Not yet', cell(unknown.answer, 'inspection_run', NONE), 'Unknown');
  eq('C9 unreadable declaration · no key is Unknown', cell(unknown.answer, 'inspection_run', OFF), 'Unknown');
  eq('C10 a table with a standing source and a refused one · [] is Not yet', cell(mixed.answer, 'lot_event', NONE),
    'Not yet');

  // ── G. the real grid puts it at the end ─────────────────────────────────────────
  // the grid (real or a mutated copy) imports the real state.js, so this is the object it reads
  const st = REAL.state.state;
  st.currentTable = 'inspection_run';
  st.currentColumns = ['run_uid', 'observed_at', 'created_at', 'updated_at'];
  st.currentColumnTypes = { run_uid: 'string', observed_at: 'datetime' };
  st.currentVirtualColumns = [];
  st.currentJoinResolvedColumns = [];
  st.ledgerAnswer = source.answer;
  const ids = mods.grid.buildColumnDefs().map((d) => d.colId || d.field || d.headerName);
  eq('G1 the Ledger column is the last one, right after updated_at', ids.slice(-2), ['updated_at', LEDGER_COL_ID]);
  st.ledgerAnswer = notSource.answer;
  st.currentTable = 'dt_map';
  eq('G2 and on a table that is not a source the grid has no such column',
    mods.grid.buildColumnDefs().some((d) => d.colId === LEDGER_COL_ID), false);

  // ── W. the write funnels skip it ────────────────────────────────────────────────
  eq('W1 paste, clear and bulk fill are told it is not a stored column',
    [mods.state.isVirtualColumn(LEDGER_COL_ID), mods.state.isVirtualColumn('run_uid')], [true, false]);

  return { ran, failures };
}

const result = await suite(REAL);
console.log('-- grid ledger column ----------------------------------------------');
console.log(`  ${result.ran.length - result.failures.length} passed, ${result.failures.length} failed`);
result.failures.forEach((f) => console.log(`  FAIL  ${f}`));

const probed = async (file, mutate) => (await loadWithProbe(FILE(file), { mutate })).module;
const MUTANTS = [
  { id: 'X1', what: 'a row the server could not read is drawn as Not yet', catches: 'C3',
    mutate: { column: (s) => s.replace('  if (!Array.isArray(names)) return UNKNOWN;',
      '  if (!Array.isArray(names)) return EMPTY_TEXT[state] || UNKNOWN;') } },
  { id: 'X2', what: '[] is drawn as a list of names (an empty one)', catches: 'C2',
    mutate: { column: (s) => s.replace('  if (names.length) return names.join', '  if (true) return names.join') } },
  { id: 'X3', what: 'an answer about another table stands the column', catches: 'A6',
    mutate: { column: (s) => s.replace('answer.relation === table && ', '') } },
  { id: 'X4', what: 'one refused source makes the whole table refused', catches: 'B1',
    mutate: { label: (s) => s.replace('rows.every(refusedByLoader)', 'rows.some(refusedByLoader)') } },
  { id: 'X5', what: 'the label does not read planned, so a refused source says it emits', catches: ['B2', 'B3'],
    mutate: { label: (s) => s.replace('const refusedByLoader = (row) => row.planned === false;',
      'const refusedByLoader = (row) => false;') } },
  { id: 'X6', what: 'the label tells the grid on every render', catches: 'B4',
    mutate: { label: (s) => s.replace('if (this.onAnswer && told !== this.told) {', 'if (this.onAnswer) {') } },
  { id: 'X7', what: 'the unreadable declaration answers [] as Not yet', catches: 'C8',
    mutate: { column: (s) => s.replace('unknown: UNKNOWN };', 'unknown: NOT_YET };') } },
  { id: 'X8', what: 'the grid seats the column first instead of last', catches: 'G1',
    mutate: { grid: (s) => s.replace('  if (ledger) columnDefs.push(ledger);', '  if (ledger) columnDefs.splice(0, 0, ledger);') } },
  { id: 'X9', what: 'the write funnels are not told, so a wide paste sends the column', catches: 'W1',
    mutate: { state: (s) => s.replace('  if (colId === LEDGER_COL_ID) return true;\n', '') } },
];
const FILES = { column: 'grid_ledger_column.js', label: 'grid_source_label.js', grid: 'grid.js', state: 'state.js' };

console.log('');
console.log('-- defect mutants (each must be CAUGHT by its named line) -----------');
const { wrong } = await scoreMutants(MUTANTS, async (m) => {
  const mods = { ...REAL };
  for (const [key, fn] of Object.entries(m.mutate)) mods[key] = await probed(FILES[key], fn);
  return suite(mods);
});

const failed = result.failures.length + wrong;
console.log('');
console.log(`${result.ran.length - result.failures.length} passed, ${result.failures.length} failed; `
  + `${MUTANTS.length - wrong}/${MUTANTS.length} defects caught, ${wrong} escaped.`);
console.log(`ASSERTIONS ${result.ran.length + MUTANTS.length} ${failed}`);
process.exit(failed ? 1 : 0);
