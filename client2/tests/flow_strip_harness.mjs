// flow_strip - the Flow strip draws one walk of the system world, and the header's chain mark reads the same answer
// (owner 11-06, lead 11-08). The subject is imported whole; a mutant is the same file with one change.
//   F1 comes from: a rule that writes the table, with the tables it reads and the columns it joins on
//   F2 feeds: a rule that reads the table and what it writes - one that also writes the table stays under «comes from»
//   F3 an ingestion that fills it; the ledger sources are the source label's answer for this table, in its words
//      (lead 11-08 ㄴ): a box per source line, another world's named; no line yet - the label's word; not one - nothing
//   F4 columns: a rule's writes_column on this table's column; another table's column is not this table's
//   F5 the table's own: key_columns; an attribute the walk did not carry is null, not ''
//   F6 a table the answer holds no node for: null
//   F7 closed: nothing drawn and nothing walked; opened: walked and drawn; refused: the server's sentence as said
//   F8 a walk answered after the table changed is dropped
//   F9 two strips on one page, two tables: neither draws the other's
//   F10 the header's tip lines name each rule, its tables, its joins and when
//   F11 «Edit» and a table name hand their table to the page
//   F12 a table no rule touches (dt_map): its file under «Comes from», no rule box, «Nothing reads it»
//   F13 a rule that reads the open table itself (dt_inventory's decide rule): that table drawn as words, not a link,
//       another table as a link (owner 11-09 ㄱ - 12e693602 left it out and the box read as having no source)
//   F14 a rule box names the first two columns it writes and «+N»; its tip says when and every column (owner 11-09)
//   F15 a file box says the ingestion's name; the whole folder is its tip, not its words (owner 11-09 ㄴ)
// Run: node client2/tests/flow_strip_harness.mjs
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { gunzipSync } from 'node:zlib';
import { makeDoc, flush, walk } from './lib/board_dom.mjs';
import { readSourceText } from './lib/probe.mjs';
import { fetchSubgraph, entitySeedId } from '../src/rnd_board/api.js';
import { withWorld } from '../src/world.js';
import { FLOW_FOLLOW, FLOW_HOPS } from '../src/flow_strip.js';
import { sourceStateWord } from '../src/grid_source_label.js';

const FILE = fileURLToPath(new URL('../src/flow_strip.js', import.meta.url));
const SOURCE = readSourceText(FILE).text;
const load = (text) => import(`data:text/javascript;base64,${Buffer.from(text, 'utf8').toString('base64')}`);

// The system world's walk as the box answered it (capture_screens.py, lead 11-08: dt_log 34 nodes, 57 edges; dt_map its
// columns and its ingestion, no rule) - the answers the screen checker serves, at the address the page asks.
const FIXTURE = gunzipSync(readFileSync(fileURLToPath(new URL('./fixtures/screens_answers.json.gz', import.meta.url))));
const RECORDED = JSON.parse(FIXTURE.toString('utf8')).answers;
async function recorded(table) {
  let asked = null;
  const stub = (url) => { asked = String(url); return Promise.resolve({ ok: true, status: 200, json: async () => ({}) }); };
  await fetchSubgraph({ apiBase: '', nodeId: entitySeedId('table', { table }), hops: FLOW_HOPS, follow: FLOW_FOLLOW,
    fetchImpl: withWorld(stub, () => 'system') });
  const a = RECORDED[asked];
  const got = a && a.same_as ? RECORDED[a.same_as] : a;
  if (!got || got.status !== 200) { console.log(`HARNESS FAILURE: no recorded answer for ${asked}`); console.log('ASSERTIONS 0 1'); process.exit(1); }
  return got.body;
}
const ANSWER = await recorded('dt_log');
const NO_RULE = await recorded('dt_map');
const SELF_READ = await recorded('dt_inventory');
const T = (table) => ({ id: `table:${table}`, type: 'table', keys: { table } });
// The source label's answer (GridSourceLabel.answer) for dt_log over the same box: the declaration's dt_job reads it.
const LABEL = { relation: 'dt_log', state: 'source', operating: 'default', rows: [{ source: 'dt_job', relation: 'dt_log', world: 'default' }] };

async function answers(M) {
  const out = {};
  const m = M.flowOf(ANSWER, 'dt_log');
  out.F1 = m && m.comesFrom.map((r) => [r.name, r.kind, r.when, r.from, r.on, r.writes]);
  out.F2 = m && m.feeds.map((r) => [r.name, r.to]);
  out.F3 = { fills: m && m.fills.map((f) => [f.name, Boolean(f.folder)]) };
  out.F4 = m && Object.fromEntries(Object.entries(m.columns).map(([column, rules]) => [column, rules.map((r) => r.name)]));
  out.F5 = m && m.table;
  out.F6 = M.flowOf(ANSWER, 'no_such_table');
  const bare = M.flowOf(NO_RULE, 'dt_map');
  out.F12 = bare && { comesFrom: bare.comesFrom.length, feeds: bare.feeds.length, fills: bare.fills.map((f) => f.name),
    columns: Object.keys(bare.columns).length };
  // F7 · F8 · F9 · F11: the part on a stub page
  const doc = makeDoc();
  const hostA = doc.createElement('div');
  const hostB = doc.createElement('div');
  doc.body.appendChild(hostA);
  doc.body.appendChild(hostB);
  const walked = [];
  let hold = null;
  const said = { answers: [], picked: [], edited: [] };
  const walkOf = (table) => {
    walked.push(table);
    if (table === 'slow') return new Promise((resolve) => { hold = resolve; });
    if (table === 'dt_map') return Promise.resolve({ ok: true, body: NO_RULE });
    if (table === 'dt_inventory') return Promise.resolve({ ok: true, body: SELF_READ });
    if (table === 'refused') return Promise.resolve({ ok: false, message: 'no relation w_system.ledger_events' });
    return Promise.resolve({ ok: true, body: ANSWER });
  };
  const a = new M.FlowStrip(hostA, { doc, walk: walkOf, onAnswer: (model) => said.answers.push(model && model.table.name),
    onPickTable: (t) => said.picked.push(t), onEdit: (t) => said.edited.push(t), sourceWord: sourceStateWord });
  const b = new M.FlowStrip(hostB, { doc, walk: walkOf, sourceWord: sourceStateWord });
  a.setSources(LABEL);
  await a.setTable('dt_log');
  const closed = { walked: walked.length, hidden: hostA.hidden, text: hostA.textContent };
  await a.setOpen(true);
  await flush();
  const opened = { walked: [...walked], text: hostA.textContent, answers: [...said.answers] };
  await b.setOpen(true);
  await b.setTable('refused');
  const refused = hostB.textContent;
  out.F7 = { closed, opened: { walked: opened.walked, has: ['inventory_confirmed:target', 'dt_inventory',
    'enrichment_dedup:enrich_in_chain_probe', 'File', 'Ledger', 'key dt_job, b_wx, b_wy', 'No description']
    .filter((w) => !opened.text.includes(w)),
    answers: opened.answers }, refused };
  // F8: the table changes while a walk is out; the late answer is not drawn
  const slow = a.setTable('slow');
  const after = a.setTable('dt_log');
  hold({ ok: true, body: { nodes: [T('slow')], edges: [] } });
  await slow;
  await after;
  await flush();
  out.F8 = { state: a.state, table: a.model && a.model.table.name };
  // F9: b still says its refusal, a its table
  out.F9 = { a: hostA.textContent.includes('inventory_confirmed'), b: hostB.textContent.includes('inventory_confirmed'),
    bSays: hostB.textContent.includes('no relation w_system.ledger_events') };
  // F11
  const button = (host, text) => walk(host).find((n) => n.tagName === 'BUTTON' && n.textContent === text);
  const edit = button(hostA, 'Edit');
  if (edit) edit.dispatch('click');
  const link = button(hostA, 'dt_inventory');
  if (link) link.dispatch('click');
  out.F11 = { edited: said.edited, picked: said.picked };
  // F15 drawn on dt_log's strip: the file box's words and tip
  const boxes = (kind) => walk(hostA).filter((n) => new RegExp(`flow-strip__item--${kind}\\b`).test(n.className || ''));
  const ruleName = (box) => walk(box).find((n) => /flow-strip__rule/.test(n.className || '')).textContent;
  const writesOf = (box) => (walk(box).find((n) => /flow-strip__writes/.test(n.className || '')) || { textContent: null }).textContent;
  out.F15 = boxes('file').map((box) => [box.textContent, box.title]);
  // F3 drawn: the label's answers, one after another, on dt_log's strip
  const ledgerSide = () => ({ boxes: walk(hostA).filter((n) => /flow-strip__item--ledger/.test(n.className || '')).map((n) => n.textContent),
    pending: hostA.textContent.includes('…'), unknown: hostA.textContent.includes('declaration unreadable — no route'),
    notSource: hostA.textContent.includes('not a ledger source') });
  out.F3.source = ledgerSide();
  a.setSources({ ...LABEL, rows: [...LABEL.rows, { source: 'dt_audit', relation: 'dt_log', world: 'audit' }] });
  out.F3.twoWorlds = ledgerSide().boxes;
  a.setSources({ relation: 'dt_log', state: 'pending', rows: [] });
  out.F3.pending = ledgerSide();
  a.setSources({ ...LABEL, relation: 'dt_map' });
  out.F3.otherTable = ledgerSide();
  a.setSources({ relation: 'dt_log', state: 'unknown', rows: [], message: 'no route' });
  out.F3.unknown = ledgerSide();
  a.setSources({ relation: 'dt_log', state: 'not_source', rows: [] });
  out.F3.notSource = ledgerSide();
  a.setSources(LABEL);
  // F12 drawn: dt_map's file under «Comes from», no rule box, «Nothing reads it»
  // the page's order: the label answers the new table, then the strip is told it
  a.setSources({ relation: 'dt_map', state: 'not_source', rows: [] });
  await a.setTable('dt_map');
  await flush();
  out.F12.drawn = { rules: walk(hostA).filter((n) => /flow-strip__item--rule/.test(n.className || '')).length,
    files: walk(hostA).filter((n) => /flow-strip__item--file/.test(n.className || '')).length,
    none: hostA.textContent.includes('Nothing reads it') };
  // F13 · F14: dt_inventory - its decide rule reads and writes dt_inventory, the dedup rule reads dt_log; the join
  // rules that read it write six and five of dt_log's columns
  await a.setTable('dt_inventory');
  await flush();
  out.F13 = boxes('rule').filter((box) => /^enrichment_/.test(ruleName(box))).map((box) => [ruleName(box),
    walk(box).filter((n) => n.tagName === 'BUTTON').map((n) => n.textContent),
    walk(box).filter((n) => /flow-strip__self/.test(n.className || '')).map((n) => n.textContent)]);
  out.F14 = boxes('rule').map((box) => [ruleName(box), writesOf(box), box.title]);
  await a.setOpen(false);
  out.F7.closedAgain = { hidden: hostA.hidden, text: hostA.textContent, last: said.answers[said.answers.length - 1] };
  out.F10 = M.chainTipLines(m && m.columns.dt_slot);
  return out;
}

const expect = {
  F1: (v) => JSON.stringify(v) === JSON.stringify([
    ['inventory_confirmed', 'join', 'on change of dt_job, dt_lot, dt_slot', ['dt_inventory'], ['dt_job'], ['dt_lot', 'dt_slot']],
    ['inventory_confirmed:target', 'join', 'on change of dt_job', ['dt_log'], ['dt_job'], ['dt_lot', 'dt_slot']],
    ['test', 'join', 'on change of dt_job, dt_lot', ['dt_inventory'], ['dt_job'], ['dt_lot']],
    ['test:target', 'join', 'on change of dt_job', ['dt_log'], ['dt_job'], ['dt_lot']]]),
  F2: (v) => JSON.stringify(v) === JSON.stringify([['enrichment_dedup:enrich_in_chain_probe', ['dt_inventory']]]),
  F3: (v) => {
    const none = { boxes: [], pending: false, unknown: false, notSource: false };
    return JSON.stringify(v) === JSON.stringify({ fills: [['dt_log', true]],
      source: { ...none, boxes: ['Ledgerdt_job'] }, twoWorlds: ['Ledgerdt_job', 'Ledgerdt_auditaudit'],
      pending: { ...none, pending: true }, otherTable: { ...none, pending: true }, unknown: { ...none, unknown: true },
      notSource: none });
  },
  F4: (v) => JSON.stringify(v) === JSON.stringify({ dt_lot: ['inventory_confirmed', 'inventory_confirmed:target', 'test', 'test:target'],
    dt_slot: ['inventory_confirmed', 'inventory_confirmed:target'] }),
  F5: (v) => JSON.stringify(v) === JSON.stringify({ name: 'dt_log', keys: 'dt_job, b_wx, b_wy', description: null }),
  F6: (v) => v === null,
  F7: (v) => v.closed.walked === 0 && v.closed.hidden === true && v.closed.text === ''
    && JSON.stringify(v.opened.walked) === '["dt_log"]' && !v.opened.has.length
    && JSON.stringify(v.opened.answers) === '["dt_log"]' && v.refused.includes('no relation w_system.ledger_events')
    && v.closedAgain.hidden === true && v.closedAgain.text === '' && v.closedAgain.last === null,
  F8: (v) => v.state === 'ready' && v.table === 'dt_log',
  F9: (v) => v.a === true && v.b === false && v.bSays === true,
  F10: (v) => JSON.stringify(v) === JSON.stringify(['written by the chain',
    'inventory_confirmed (join) · from dt_inventory · joined on dt_job · on change of dt_job, dt_lot, dt_slot',
    'inventory_confirmed:target (join) · from dt_log · joined on dt_job · on change of dt_job']),
  F11: (v) => JSON.stringify(v) === JSON.stringify({ edited: ['dt_log'], picked: ['dt_inventory'] }),
  F12: (v) => JSON.stringify(v) === JSON.stringify({ comesFrom: 0, feeds: 0, fills: ['dt_map'], columns: 0,
    drawn: { rules: 0, files: 1, none: true } }),
  F13: (v) => JSON.stringify(v) === JSON.stringify([['enrichment_auto_confirm:enrich_in_chain_probe', [], ['dt_inventory']],
    ['enrichment_dedup:enrich_in_chain_probe', ['dt_log'], []]]),
  F14: (v) => JSON.stringify(v) === JSON.stringify([
    ['enrichment_auto_confirm:enrich_in_chain_probe', null, null],
    ['enrichment_dedup:enrich_in_chain_probe', '→ dt_job', 'writes dt_job'],
    ['inventory_confirmed', '→ b_wx, b_wy +4', 'on change of dt_job, dt_lot, dt_slot\nwrites b_wx, b_wy, dt_cell_key, dt_job, dt_lot, dt_slot'],
    ['test', '→ b_wx, b_wy +3', 'on change of dt_job, dt_lot\nwrites b_wx, b_wy, dt_cell_key, dt_job, dt_lot']]),
  F15: (v) => JSON.stringify(v) === JSON.stringify([['Filedt_log',
    'C:\\Users\\kk980\\Developments\\assyManager\\server\\ingestion_workspace\\dt_log']]),
};

let passed = 0;
let failed = 0;
const real = await answers(await load(SOURCE));
for (const [line, ok] of Object.entries(expect)) {
  if (ok(real[line])) { passed += 1; console.log(`  ok   ${line}`); } else { failed += 1; console.log(`  FAIL ${line}  saw: ${JSON.stringify(real[line])}`); }
}

const MUTANTS = [
  ['F1', 'reads_from read backwards', "from: sorted(ends(node.id, 'reads_from')", "from: sorted(into('reads_from')"],
  ['F2', 'a rule that writes the table also feeds', '.filter((node) => !written.has(node.keys.rule))', ''],
  ['F3', "another table's label answer drawn", 'this.sources && this.sources.relation === this.table ? this.sources : null', 'this.sources'],
  ['F3', "the strip's own word for an answer not given yet", 'const word = this.sourceWord(answer);', "const word = 'Reading';"],
  ['F3', '«not a ledger source» said beside «Nothing reads it»', "answer && answer.state === 'not_source' ? null : word", 'word'],
  ['F3', "the operating world's line named with its world", 'row.world && row.world !== answer.operating ?', 'row.world ?'],
  ['F4', "another table's column counted", '      if (column.keys.table !== table) continue;\n', ''],
  ['F5', "a missing attribute read as ''", "return value === undefined || value === null || value === '' ? null : value;",
    "return value === undefined || value === null ? '' : value;"],
  ['F7', 'walks while closed', '    if (!this.open || !this.table) {', '    if (!this.table) {'],
  ['F7', "the server's refusal replaced", "this.message = (got && got.message) || 'walk refused';", "this.message = 'walk refused';"],
  ['F7', 'a closed strip tells the page on every switch', '    if (model === this.told) return;\n', ''],
  ['F8', 'a late answer drawn', '    if (mine !== this.asked) return;\n', ''],
  ['F10', 'the joins left out of the tip', "each.on.length ? `joined on ${each.on.join(', ')}` : '',", "'',"],
  ['F4', "a column's rules in the server's edge order", '  for (const list of Object.values(columns)) list.sort((a, b) => a.name.localeCompare(b.name));\n', ''],
  ['F12', 'an ingestion drawn as a rule', "this._box('file', 'File',", "this._box('rule', 'File',"],
  ['F13', 'the open table left out of its own rule box again', 'this._rule(each, each.from)),',
    'this._rule(each, each.from.filter((name) => name !== this.table))),'],
  ['F13', 'the open table drawn as a link to itself', "name === this.table ? this._el('span', 'flow-strip__self', name)",
    "false ? this._el('span', 'flow-strip__self', name)"],
  ['F14', 'every written column on the box', 'each.writes.slice(0, SHOWN_COLUMNS)', 'each.writes'],
  ['F14', 'the columns past two not counted', "${more > 0 ? ` +${more}` : ''}", ''],
  ['F14', "the tip without the columns", "each.writes.length ? `writes ${each.writes.join(', ')}` : ''", "''"],
  ['F14', 'a joined column read as written', "const columnsOf = (node) => ends(node.id, 'writes_column');", "const columnsOf = (node) => ends(node.id, 'joins_on');"],
  ['F15', 'the whole folder back on the file box', "[this._id('flow-strip__rule', each.name)], each.folder || '')",
    "[this._id('flow-strip__rule', each.name), this._el('span', '', each.folder)], each.folder || '')"],
  ['F15', 'the folder not in the tip', "[this._id('flow-strip__rule', each.name)], each.folder || '')",
    "[this._id('flow-strip__rule', each.name)], '')"],
  ['F11', 'Edit hands nothing', 'edit.addEventListener(\'click\', () => this.onEdit(m.table.name));', ''],
];
let caught = 0;
console.log('\n-- defect mutants (each caught by its line) --');
for (const [line, what, from, to] of MUTANTS) {
  if (!SOURCE.includes(from)) { console.log(`HARNESS FAILURE: mutant anchor gone - ${what}`); console.log(`ASSERTIONS ${passed} ${failed + 1}`); process.exit(1); }
  let saw;
  try { saw = await answers(await load(SOURCE.replace(from, to))); } catch (err) { saw = null; }
  const hit = saw === null || !expect[line](saw[line]);
  if (hit) caught += 1;
  console.log(`  ${hit ? 'caught ' : 'ESCAPED'} ${line} ${what}`);
}
const allCaught = caught === MUTANTS.length;
if (allCaught) passed += 1; else failed += 1;
console.log(`\n${passed} passed, ${failed} failed; ${caught}/${MUTANTS.length} defects caught.`);
console.log(`ASSERTIONS ${passed} ${failed}`);
process.exit(failed ? 1 : 0);
