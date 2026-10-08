// INDEX TABLE — the declared indexes beside the database (lead d71f931c7), read off GET /admin/indexes.
//
//   I1 one row per declared index of the real answer, in its order, the cells the view says
//   I2 the state is the server's token on a tag; present · building · missing · invalid wear the base layer's tones
//   I3 a building index says the server's sentence under its tag, whole; the others say none
//   I4 a count of no scans is drawn dim, any other count plain
//   I5 the indexes nothing declares stand below, under «Not declared»; none is said
//   I6 an answer that did not come is the refusal's line, not an empty table
//
// The answer is the server's own (fixtures/admin_indexes.json, capture_admin_indexes.py - models.index_states on
// the box PostgreSQL). The box holds no invalid and no building index, so those two rows are hand rows: a captured
// row with its state and, for building, a sentence in the server's shape (models._building). Every defect below
// must be caught by the line it names.
//
// Run: node client2/tests/index_table_panel_harness.mjs
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';
import { makeDoc, byClass } from './lib/board_dom.mjs';
import { ABSENT } from '../src/absent.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SUBJECT = path.join(HERE, '..', 'src', 'index_table_panel.js');
const REAL = JSON.parse(readFileSync(path.join(HERE, 'fixtures', 'admin_indexes.json'), 'utf8'));
const WAITS = 'building - waiting for transactions older than it: pid 4242 (chain)';
const present = REAL.declared.filter((r) => r.state === 'present');
const BODY = { declared: [...REAL.declared,
  { ...present[0], name: `${present[0].name}_hand_invalid`, state: 'invalid' },
  { ...present[1], name: `${present[1].name}_hand_building`, state: 'building', building: WAITS, size_bytes: null, scans: null }],
outside: REAL.outside };

const walk = (n) => [n, ...(n.children || []).flatMap(walk)];
const byTag = (n, tag) => walk(n).filter((c) => c.tagName === tag);
const textOf = (n) => (n.children && n.children.length ? n.children.map(textOf).join('') : n.textContent || '');

async function suite(m) {
  const ran = [];
  const failures = [];
  const eq = (name, got, want) => {
    ran.push(name);
    const g = JSON.stringify(got); const w = JSON.stringify(want);
    if (g !== w) failures.push(`${name}: got ${g}, want ${w}`);
  };
  const doc = makeDoc('light');
  const host = doc.createElement('div');
  const panel = new m.IndexTablePanel(host, { doc });
  panel.render(BODY);
  const [declared, outside] = byTag(host, 'TABLE');
  const rowsOf = (table) => (table ? byTag(table, 'TR').filter((tr) => tr.getAttribute('data-index') !== null) : []);
  const cell = (tr, col) => tr.children.find((td) => td.getAttribute('data-col') === col);
  const rows = rowsOf(declared);

  eq('I1 one row per declared index, in the answer\'s order, its name, table, columns, purpose, serves, size and scans',
    [rows.length > 0, rows.map((tr) => tr.getAttribute('data-index')),
      rows.slice(0, 3).map((tr) => ['name', 'table', 'columns', 'purpose', 'serves', 'size', 'scans'].map((c) => textOf(cell(tr, c))))],
    [true, BODY.declared.map((r) => r.name), BODY.declared.slice(0, 3).map((r) => [r.name, r.table, r.columns.join(', '),
      r.purpose || ABSENT, r.serves || ABSENT, m.sizeText(r.size_bytes), r.scans === null ? ABSENT : String(r.scans)])]);
  eq('I1b sizes read in the unit they reach, a size not sent is a dash',
    [m.sizeText(0), m.sizeText(8192), m.sizeText(106496), m.sizeText(5 * 1024 * 1024 + 1), m.sizeText(null)],
    ['0 B', '8.0 KB', '104 KB', '5.0 MB', ABSENT]);
  const tags = (state) => rows.filter((tr) => byClass(cell(tr, 'state'), 'tag')[0].textContent === state)
    .map((tr) => byClass(cell(tr, 'state'), 'tag')[0].getAttribute('data-tone'));
  eq('I2 the state is the server\'s token on a tag; present ok, building warn, missing and invalid danger',
    [['present', 'building', 'missing', 'invalid'].map((s) => [...new Set(tags(s))]),
      rows.length === BODY.declared.length && rows.every((tr, i) => byClass(cell(tr, 'state'), 'tag')[0].textContent === BODY.declared[i].state)],
    [[['ok'], ['warn'], ['danger'], ['danger']], true]);
  const said = rows.map((tr) => byClass(cell(tr, 'state'), 'index-building').map((n) => n.textContent));
  eq('I3 a building index says the server\'s sentence whole under its tag; no other says one',
    [said.filter((s) => s.length).length, said[rows.findIndex((tr) => tr.getAttribute('data-index').endsWith('_hand_building'))]],
    [1, [WAITS]]);
  const scanCells = rows.map((tr) => cell(tr, 'scans'));
  const zero = BODY.declared.map((r, i) => [r.scans, byClass(scanCells[i], 'meta').length]);
  eq('I4 no scans is drawn dim, a count above it plain',
    [zero.some(([s]) => s === 0), zero.every(([s, dim]) => (s === 0 ? dim === 1 : dim === 0))], [true, true]);
  const title = byClass(host, 'index-outside-title')[0];
  eq('I5 the indexes nothing declares stand below under «Not declared», one row each; with none, None is said',
    [Boolean(title) && title.textContent, rowsOf(outside).map((tr) => [tr.getAttribute('data-index'), textOf(cell(tr, 'valid'))]),
      (() => { const h = doc.createElement('div'); new m.IndexTablePanel(h, { doc }).render({ declared: [], outside: [] });
        return [byTag(h, 'TABLE').length, byClass(h, 'meta').map((n) => n.textContent)]; })()],
    ['Not declared', REAL.outside.map((r) => [r.name, r.valid === true ? 'yes' : r.valid === false ? 'no' : ABSENT]),
      [1, ['None']]]);
  const refusedHost = doc.createElement('div');
  new m.IndexTablePanel(refusedHost, { doc }).render(null, 'Token declined (HTTP 401)');
  eq('I6 an answer that did not come is its refusal line and no table',
    [byTag(refusedHost, 'TABLE').length, byClass(refusedHost, 'refusal').map((n) => n.textContent)],
    [0, ['Token declined (HTTP 401)']]);
  return { ran: ran.length, names: ran, failures };
}

const real = await import('../src/index_table_panel.js');
const base = await suite(real);
console.log('-- index table ------------------------------------------------------');
for (const name of base.names) console.log(`  ${base.failures.some((f) => f.startsWith(name + ':')) ? 'FAIL' : 'PASS'} ${name}`);
base.failures.forEach((f) => console.log(`  FAIL  ${f}`));

const swap = (from, to) => (t) => { if (!t.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`); return t.split(from).join(to); };
const MUTANTS = [
  { id: 'XI1', what: 'the size is the raw byte count', catches: ['I1b'],
    mutate: swap('  return `${unit && value < 10 ? value.toFixed(1) : Math.round(value)} ${units[unit]}`;', '  return String(bytes);') },
  { id: 'XI2', what: 'a building index wears no tone', catches: ['I2'], mutate: swap(" building: 'warn',", '') },
  { id: 'XI3', what: 'an invalid index reads as present', catches: ['I2'], mutate: swap(" invalid: 'danger' });", " invalid: 'ok' });") },
  { id: 'XI4', what: 'the state is the screen\'s word, not the server\'s token', catches: ['I2'],
    mutate: swap('token: text(r.state),', "token: r.state === 'present' ? 'OK' : text(r.state),") },
  { id: 'XI5', what: 'a build\'s sentence is not said', catches: ['I3'],
    mutate: swap("        if (key === said && row.building) td.appendChild(this._el('div', 'meta index-building', row.building));\n", '') },
  { id: 'XI6', what: 'no scans is drawn like any count', catches: ['I4'], mutate: swap("} else if (key === 'scans' && row.unused) {", '} else if (false) {') },
  { id: 'XI7', what: 'the indexes nothing declares are not drawn', catches: ['I5'],
    mutate: swap("    if (view.outside.length) this.root.appendChild(this._table(OUTSIDE_COLUMNS, view.outside, 'valid'));", '    if (false) {}') },
  { id: 'XI8', what: 'an answer that did not come draws an empty table', catches: ['I6'],
    mutate: swap("  if (!declared) return { state: 'unread', declared: [], outside: [] };", "  if (!declared) return { state: 'ready', declared: [], outside: [] };") },
];
console.log('');
const { wrong } = await scoreMutants(MUTANTS, async (mu) => suite((await loadWithProbe(SUBJECT, { mutate: mu.mutate })).module),
  { baselineRan: base.ran, baselineNames: base.names, title: '-- defect mutants (each must be CAUGHT by its named line) -----------' });
const failed = base.failures.length + wrong;
console.log(`\n${base.ran - base.failures.length} passed, ${base.failures.length} failed; ${MUTANTS.length - wrong}/${MUTANTS.length} defects caught, ${wrong} escaped.`);
console.log(`ASSERTIONS ${base.ran + MUTANTS.length} ${failed}`);
process.exit(failed ? 1 : 0);
