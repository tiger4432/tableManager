// The ledger test run's atom table (owner 10-07 「테스트런에서 생성 원자 자세히 볼 수 없니」, lead 026ced7f1).
// The server carries `atoms_sample` (the implementer's spelling, 10-07); the screen tables it under the sentence list
// with the read-rows table's part, a sentence line narrows it to that sentence, and a picked atom marks its source
// rows in the read-rows table by row_id. A server that sends no sample leaves today's screen as it was.
// Each layer is measured where it lives - the function, the store, the part, the drawn screen, the clicks - and each
// has a defect that must go red at its named line.
import { register } from 'node:module';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
register(pathToFileURL(path.join(HERE, 'lib', 'css_loader.mjs')).href);
const SRC = path.join(HERE, '..', 'src');
const CELL = path.join(SRC, 'refusal_cell.js');
const STORE = path.join(SRC, 'ontology_explorer_store.js');
const PART = path.join(SRC, 'rnd_board', 'table_part.js');
const VIEW = path.join(SRC, 'ontology_explorer_view.js');
const SCREEN = path.join(SRC, 'ontology_explorer.js');

function element(tag) {
  const node = {
    tagName: String(tag).toUpperCase(), children: [], attrs: Object.create(null), _classes: [], dataset: Object.create(null),
    _on: Object.create(null), style: { setProperty() {} }, _text: '',
    get className() { return this._classes.join(' '); }, set className(v) { this._classes = String(v).split(/\s+/).filter(Boolean); },
    classList: { add(...n) { for (const x of n) if (!node._classes.includes(x)) node._classes.push(x); },
      remove(...n) { node._classes = node._classes.filter((c) => !n.includes(c)); }, contains(n) { return node._classes.includes(n); },
      toggle(n, on) { if (on) node.classList.add(n); else node.classList.remove(n); } },
    get childElementCount() { return this.children.length; },
    append(...items) { for (const i of items) if (i) this.children.push(i); }, appendChild(c) { this.children.push(c); return c; },
    replaceChildren(...items) { this.children = items.filter(Boolean); }, removeChild(c) { this.children = this.children.filter((x) => x !== c); return c; },
    setAttribute(k, v) { this.attrs[k] = String(v); }, removeAttribute(k) { delete this.attrs[k]; },
    getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }, querySelector() { return null; }, querySelectorAll() { return []; },
    addEventListener(type, fn) { (this._on[type] ||= []).push(fn); }, removeEventListener() {}, focus() {}, scrollIntoView() {},
    closest() { return null; }, contains() { return false; },
    set textContent(v) { this._text = String(v); this.children = []; },
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); },
  };
  return node;
}
globalThis.document = { createElement: element, createDocumentFragment: () => element('#fragment'),
  createTextNode: (t) => { const n = element('#text'); n.textContent = t; return n; },
  addEventListener() {}, removeEventListener() {}, querySelector() { return null; }, querySelectorAll() { return []; } };
globalThis.requestAnimationFrame = (fn) => fn();
globalThis.window = { addEventListener() {}, removeEventListener() {}, location: { hash: '' } };

const walk = (n, out = []) => { out.push(n); for (const c of n.children || []) walk(c, out); return out; };
const byClass = (root, name) => walk(root).filter((n) => n._classes?.includes(name));
const rowsOf = (root, host) => (byClass(root, host)[0] ? byClass(byClass(root, host)[0], 'rb-table-row') : []);

// The implementer's spelling (10-07): four read rows with row_id; seven atoms from two sentences (a third says
// nothing), one the run would not write, one built from two rows (a group_by molecule), one with qualifiers only.
const atom = (sentence, rowIds, keys, over = {}) => ({ sentence, row_ids: rowIds, subject_type: 'job', subject_keys: keys,
  predicate: sentence === 'job_ran' ? 'ran_on' : 'registered', object_kind: null, object_payload: null,
  occurred_at: '2026-10-07T09:00:00+09:00', occurred_at_basis: null, source_raw_ref: null, source_event_id: null,
  source_event_state: null, source_who: 'test', source_translator_ver: 'v2', supersedes: null, writes: true, drop_reason: null, ...over });
const RUN = {
  source_id: 'dt_job', status: 'passed', relation: 'dt_job', rows_read: 12, pages: 2, molecules: 4, incomplete: 0, atoms: 7,
  sentences: [{ sentence: 'job_ran', predicate: 'ran_on', atoms: 4 }, { sentence: 'job_registered', predicate: 'registered', atoms: 3 },
    { sentence: 'job_silent', predicate: 'held_by', atoms: 0 }],
  refused: { count: 0, reasons: {}, samples: [] },
  rows_sample: ['r1', 'r2', 'r3', 'r4'].map((id, i) => ({ dt_job: `J-10${i + 1}`, eqp: 'EQ-7', row_id: id })),
  atoms_sample: [
    atom('job_registered', ['r1'], { dt_job: 'J-101' }, { writes: false, drop_reason: 'already_registered' }),
    atom('job_ran', ['r1'], { dt_job: 'J-101' }, { object_kind: 'entity_ref',
      object_payload: { type: 'eqp', keys: { eqp: 'EQ-7' }, qualifiers: { role: 'main' } }, occurred_at_basis: 'created_at' }),
    atom('job_registered', ['r2'], { dt_job: 'J-102' }, { object_payload: { qualifiers: { lot: 'L-1' } } }),
    atom('job_ran', ['r2'], { dt_job: 'J-102' }, { object_kind: 'value', object_payload: { value: '42' } }),
    atom('job_ran', ['r3', 'r4'], { dt_job: 'J-103' }, { object_kind: 'value', object_payload: { value: 42 } }),
    atom('job_registered', ['r3'], { dt_job: 'J-103' }),
    atom('job_ran', ['r4'], { dt_job: 'J-104' }, { object_kind: 'event_ref', object_payload: { event: 'ev-9' } }),
  ],
  truncated: { atoms_sample: { cut: false, omitted: 0, reason: null } },
};
const { atoms_sample: _a, truncated: _t, ...OLD } = RUN;
OLD.rows_sample = RUN.rows_sample.map(({ row_id: _r, ...rest }) => rest);

let ran = 0;
let failed = [];
const NAMES = [];
const ok = (name, cond, detail) => {
  ran += 1; NAMES.push(name);
  if (cond) { console.log(`  ok   ${name}`); return; }
  failed.push(name);
  console.log(`  FAIL ${name}${detail ? ' -- ' + detail : ''}`);
};
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

async function suite({ cell, store, Part, view, makeController }) {
  const { testRunAtoms, ATOM_KEY } = cell;
  console.log('\n── A. the sample as a table: values in the stored spelling, in the run\'s order ──');
  ok('A1 an older server (no sample): no table', testRunAtoms(OLD, {}) === null);
  const all = testRunAtoms(RUN, {});
  ok('A2 every atom, in the sample\'s order, keyed by its place', same(all.rows.map((r) => r[ATOM_KEY]), ['1', '2', '3', '4', '5', '6', '7'])
    && same(all.columns.map((c) => c.label), ['#', 'Sentence', 'Subject', 'Predicate', 'Object', 'Qualifiers', 'Occurred at', 'Rows', 'Writes']),
  JSON.stringify(all.columns.map((c) => c.label)));
  const [first, second, third, fourth, fifth] = all.rows;
  ok('A3 keys, object and qualifiers in the ledger\'s JSON, the qualifiers out of the object',
    second.subject_keys === '{"dt_job":"J-101"}' && second.object === '{"type":"eqp","keys":{"eqp":"EQ-7"}}'
    && second.qualifiers === '{"role":"main"}' && third.object === '' && third.qualifiers === '{"lot":"L-1"}'
    && fourth.object === '{"value":"42"}' && fifth.object === '{"value":42}', JSON.stringify([second, third.object, fourth.object]));
  ok('A4 an atom the run would not write says so, with its reason', first.writes === 'no' && first.drop_reason === 'already_registered'
    && second.writes === 'yes', JSON.stringify([first.writes, first.drop_reason, second.writes]));
  ok('A5 the rows an atom came from', fifth.row_ids === 'r3, r4' && first.row_ids === 'r1', fifth.row_ids);
  const ranOnly = testRunAtoms(RUN, { sentence: 'job_ran' });
  ok('A6 a picked sentence: its atoms only, keeping their place', same(ranOnly.rows.map((r) => r[ATOM_KEY]), ['2', '4', '5', '7']),
    JSON.stringify(ranOnly.rows.map((r) => r[ATOM_KEY])));
  const silent = testRunAtoms(RUN, { sentence: 'job_silent' });
  ok('A7 a sentence that built nothing: a table with no rows, not no table', silent !== null && silent.rows.length === 0);
  ok('A8 a picked atom: its rows are the linked ones; none picked, none linked',
    same(testRunAtoms(RUN, { atom: '5' }).linked, ['r3', 'r4']) && same(all.linked, []));
  const cut = testRunAtoms({ ...RUN, truncated: { atoms_sample: { cut: true, omitted: 9, reason: 'limit' } } }, {});
  ok('A9 a cut sample says so; a whole one says nothing', same(cut.notes, ['first 7']) && same(all.notes, []),
    JSON.stringify([cut.notes, all.notes]));

  console.log('\n── B. the pick belongs to one run ──');
  const { reduceExplorerState: reduce, initialExplorerState: init } = store;
  const s1 = reduce({ ...init, testRun: RUN }, { type: 'TEST_RUN_SENTENCE_PICKED', sentence: 'job_ran' });
  const s2 = reduce(s1, { type: 'TEST_RUN_ATOM_PICKED', atom: '5' });
  const s3 = reduce(s2, { type: 'TEST_RUN_SENTENCE_PICKED', sentence: 'job_ran' });
  ok('B1 a sentence picks; the same again lets go and lets go of the atom',
    same(s1.testRunPick, { sentence: 'job_ran', atom: null }) && same(s3.testRunPick, { sentence: null, atom: null }),
    JSON.stringify([s1.testRunPick, s3.testRunPick]));
  ok('B2 an atom picks; the same again lets go', same(s2.testRunPick, { sentence: 'job_ran', atom: '5' })
    && same(reduce(s2, { type: 'TEST_RUN_ATOM_PICKED', atom: '5' }).testRunPick, { sentence: 'job_ran', atom: null }),
  JSON.stringify(s2.testRunPick));
  ok('B3 a new run starts with nothing picked', same(reduce(s2, { type: 'TEST_RUN_STARTED' }).testRunPick, { sentence: null, atom: null }));

  console.log('\n── C. the part hands a row\'s click to its page when the page names the action ──');
  const host = element('div');
  new Part(host, { doc: document, columns: [{ key: 'k', label: 'K' }], rows: [{ k: 'a' }], rowKey: 'k', rowAction: 'pick' }).render();
  const plain = element('div');
  new Part(plain, { doc: document, columns: [{ key: 'k', label: 'K' }], rows: [{ k: 'a' }], rowKey: 'k' }).render();
  const [named] = byClass(host, 'rb-table-row');
  const [marking] = byClass(plain, 'rb-table-row');
  ok('C1 a named action: the row carries it and its key, and no marking click of its own',
    named?.dataset.action === 'pick' && named?.dataset.value === 'a' && !(named?._on.click || []).length,
    JSON.stringify([named?.dataset, (named?._on.click || []).length]));
  ok('C2 no action named: the row marks as before', marking?.dataset.action === undefined && (marking?._on.click || []).length === 1);

  console.log('\n── D. the drawn screen ──');
  const state = (run, pick) => ({ ...init, selection: { key: 'source_plan|dt_job', canonical_id: 'dt_job', kind: 'source_plan',
    config_path: 'bundle.sources.dt_job', compile_status: 'valid', config_file: 'ledger_config.json', raw: {} },
  activeSnapshot: { snapshot_hash: 'abc', valid: true }, viewContext: { mode: 'active', context_token: 'active:abc' },
  navigation: { back: [], forward: [] }, testRun: run, ...(pick ? { testRunPick: pick } : {}) });
  const draw = (run, pick) => { const root = element('div'); view.renderOntologyExplorer(root, state(run, pick)); return root; };
  const old = draw(OLD);
  ok('D1 an older server: sentence lines are not buttons, no atom table, read rows carry no row id',
    byClass(old, 'oe-testrun-sentence').length === 3 && byClass(old, 'oe-testrun-sentence').every((l) => l.tagName === 'DIV' && !l.dataset.action)
    && byClass(old, 'oe-testrun-atomtable').length === 0 && rowsOf(old, 'oe-testrun-rows').length === 4
    && rowsOf(old, 'oe-testrun-rows').every((r) => r.attrs['data-row-id'] === undefined),
  JSON.stringify(byClass(old, 'oe-testrun-sentence').map((l) => l.tagName)));
  const fresh = draw(RUN);
  const lines = byClass(fresh, 'oe-testrun-sentence');
  ok('D2 sentence lines are buttons naming their sentence; the atom table holds every atom, each row a pick',
    lines.length === 3 && lines.every((l) => l.tagName === 'BUTTON' && l.dataset.action === 'test-run-sentence')
    && same(lines.map((l) => l.dataset.value), ['job_ran', 'job_registered', 'job_silent'])
    && rowsOf(fresh, 'oe-testrun-atomtable').length === 7
    && rowsOf(fresh, 'oe-testrun-atomtable').every((r) => r.dataset.action === 'test-run-atom'),
  JSON.stringify([lines.map((l) => [l.tagName, l.dataset.action]), rowsOf(fresh, 'oe-testrun-atomtable').length]));
  const narrowed = draw(RUN, { sentence: 'job_ran', atom: null });
  ok('D3 a picked sentence: pressed, and the table holds its atoms only',
    same(byClass(narrowed, 'oe-testrun-sentence').map((l) => l.getAttribute('aria-pressed')), ['true', 'false', 'false'])
    && same(rowsOf(narrowed, 'oe-testrun-atomtable').map((r) => r.dataset.value), ['2', '4', '5', '7']),
  JSON.stringify(rowsOf(narrowed, 'oe-testrun-atomtable').map((r) => r.dataset.value)));
  const linked = draw(RUN, { sentence: null, atom: '5' });
  const markedRead = rowsOf(linked, 'oe-testrun-rows').filter((r) => r._classes.includes('is-marked-case')).map((r) => r.attrs['data-row-id']);
  const markedAtom = rowsOf(linked, 'oe-testrun-atomtable').filter((r) => r._classes.includes('is-marked-case')).map((r) => r.dataset.value);
  ok('D4 a picked atom: its rows marked in the read-rows table by row_id, and itself marked', same(markedRead, ['r3', 'r4'])
    && same(markedAtom, ['5']), JSON.stringify([markedRead, markedAtom]));
  const noted = draw({ ...RUN, truncated: { atoms_sample: { cut: true, omitted: 9, reason: 'limit' } } });
  ok('D5 a cut sample says so on the screen', byClass(noted, 'oe-testrun-note').some((n) => n.textContent === 'first 7'));

  console.log('\n── E. the clicks reach the store ──');
  const root = element('div');
  const screen = makeController({ root, apiBase: '', adminFetch: async () => ({ ok: true, status: 200, json: async () => ({}) }),
    showToast: () => {} });
  const click = async (action, value) => { for (const fn of root._on.click || []) await fn({ target: { closest: () => ({ dataset: { action, value } }) } }); };
  await click('test-run-sentence', 'job_ran');
  const afterSentence = screen.getState().testRunPick;
  await click('test-run-atom', '5');
  const afterAtom = screen.getState().testRunPick;
  ok('E1 a sentence line\'s click picks the sentence', same(afterSentence, { sentence: 'job_ran', atom: null }), JSON.stringify(afterSentence));
  ok('E2 an atom row\'s click picks the atom', same(afterAtom, { sentence: 'job_ran', atom: '5' }), JSON.stringify(afterAtom));
  return { ran, failed: failed.slice() };
}

const swap = (from, to) => (t) => { if (!t.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`); return t.split(from).join(to); };
const load = async (file, mutate) => (await loadWithProbe(file, mutate ? { mutate } : {})).module;
const deps = async (m = {}) => ({
  cell: await load(CELL, m.file === 'cell' && m.mutate), store: await load(STORE, m.file === 'store' && m.mutate),
  Part: (await load(PART, m.file === 'part' && m.mutate)).TablePart, view: await load(VIEW, m.file === 'view' && m.mutate),
  makeController: (await load(SCREEN, m.file === 'screen' && m.mutate)).createOntologyExplorerController,
});

const MUTANTS = [
  { name: 'an older server gets an empty table', catches: ['A1'], file: 'cell',
    mutate: swap('  if (!Array.isArray(src.atoms_sample)) return null;\n', '  if (!Array.isArray(src.atoms_sample)) src.atoms_sample = [];\n') },
  { name: 'the qualifiers stay inside the object', catches: ['A3'], file: 'cell',
    mutate: swap('    const { qualifiers, ...object } = payload;\n', '    const { qualifiers } = payload; const object = payload;\n') },
  { name: 'the reason an atom is not written is dropped', catches: ['A4'], file: 'cell', mutate: swap('      drop_reason: a.drop_reason,\n', '') },
  { name: 'the sentence is not filtered', catches: ['A6', 'A7'], file: 'cell',
    mutate: swap('    if (sentence !== null && String(a.sentence) !== sentence) return;\n', '') },
  { name: 'a picked atom links nothing', catches: ['A8'], file: 'cell', mutate: swap('    if (key === atom) linked = rowIds;\n', '') },
  { name: 'a cut sample is drawn as whole', catches: ['A9'], file: 'cell', mutate: swap('  if (cut) notes.push(', '  if (false) notes.push(') },
  { name: 'a new sentence keeps the old atom', catches: ['B1'], file: 'store',
    mutate: swap('sentence: state.testRunPick?.sentence === action.sentence ? null : action.sentence, atom: null } };',
      'sentence: state.testRunPick?.sentence === action.sentence ? null : action.sentence, atom: state.testRunPick?.atom } };') },
  { name: 'a new run keeps the last pick', catches: ['B3'], file: 'store',
    mutate: swap(', testRunPick: initialExplorerState.testRunPick };', ' };') },
  { name: 'the part marks instead of handing the click on', catches: ['C1'], file: 'part', mutate: swap('    if (id && this.rowAction) {\n', '    if (false) {\n') },
  { name: 'sentence lines are buttons even for an older server', catches: ['D1'], file: 'view',
    mutate: swap("      const line = atoms ? button('', 'test-run-sentence', row.sentence, 'oe-testrun-sentence')",
      "      const line = true ? button('', 'test-run-sentence', row.sentence, 'oe-testrun-sentence')") },
  { name: 'the read-rows table is not keyed by row_id', catches: ['D4'], file: 'view',
    mutate: swap("      rowKey: atoms ? 'row_id' : null,\n", '      rowKey: null,\n') },
  { name: 'the atom table hands its clicks to no one', catches: ['D2'], file: 'view', mutate: swap("      rowAction: 'test-run-atom',\n", '') },
  { name: 'the picked sentence is not pressed', catches: ['D3'], file: 'view',
    mutate: swap("        line.setAttribute('aria-pressed', String(picked));\n", '') },
  { name: 'a cut sample\'s note is not drawn', catches: ['D5'], file: 'view',
    mutate: swap("    for (const note of atoms.notes) box.append(h('span', 'oe-testrun-note', note));\n", '') },
  { name: 'a sentence click is not heard', catches: ['E1', 'E2'], file: 'screen',
    mutate: swap("      dispatch({ type: 'TEST_RUN_SENTENCE_PICKED', sentence: target.dataset.value });\n", '') },
  { name: 'an atom click is not heard', catches: ['E2'], file: 'screen',
    mutate: swap("      dispatch({ type: 'TEST_RUN_ATOM_PICKED', atom: target.dataset.value });\n", '') },
];

console.log('== baseline ==');
const base = await suite(await deps());
const BASE_NAMES = NAMES.slice();
if (base.failed.length) { console.log(`ASSERTIONS ${base.ran} ${base.failed.length}`); process.exit(1); }
const { wrong } = await scoreMutants(MUTANTS, async (m) => {
  const d = await deps(m);
  const real = console.log;
  console.log = () => {};
  ran = 0; failed = [];
  try { await suite(d); } finally { console.log = real; }
  return { failures: failed, ran };
}, { baselineRan: base.ran, baselineNames: BASE_NAMES, title: '\n== defect mutants (each must be CAUGHT by its named line) ==' });
console.log(`\nASSERTIONS ${base.ran} ${base.failed.length}`);
process.exit(wrong ? 1 : 0);
