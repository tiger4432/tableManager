// The Board's destination scenario on a live box (owner 10-13, lead): A a map of the bonding wafer's dies -> a die pressed
// marks Die; B a cross table walking from Die - its dies by the core wafer they were bonded from, Count -> a core wafer
// pressed marks Core wafer; C a cross table walking from Core wafer - its wafers by the measure step, Count -> a step
// pressed marks Step; D a scatter walking from Step - a point a value record, X its time, Y its value, coloured by
// If(Marked("Core wafer"), "B", "other") along the page's relations. The test bed page itself (testbed/main.js boot) on
// the box's API, the document a stub. Prints what each part drew and the numbers the lead asked: the walks each part
// asked, the layer's ms on a marking change, the walked graph's nodes. Not a pass/fail gate - the box's data.
//
//   node client2/scripts/board_scenario_live.mjs [--api http://127.0.0.1:18766] [--wafer SYN-BW-103-11] [--save <file>]
// CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
import { writeFileSync } from 'node:fs';
import { makeDoc } from '../tests/lib/board_dom.mjs';

const argOf = (k, d) => (process.argv.includes(k) ? process.argv[process.argv.indexOf(k) + 1] : d);
const API = argOf('--api', 'http://127.0.0.1:18766');
const WAFER = argOf('--wafer', 'SYN-BW-103-11');
const main = await import('../src/testbed/main.js');
const { entitySeedId } = await import('../src/rnd_board/api.js');
const { SIGN } = await import('../src/rnd_board/marking_store.js');

const settle = async () => { for (let i = 0; i < 40; i += 1) await new Promise((r) => setTimeout(r, 5)); };
const until = async (test, ms = 60000) => { const t0 = Date.now(); while (!test()) { if (Date.now() - t0 > ms) throw new Error('timed out'); await new Promise((r) => setTimeout(r, 50)); } await settle(); };
const charts = { init: () => ({ setOption() {}, dispatchAction() {}, on() {}, getZr() { return { on() {} }; }, resize() {}, dispose() {} }) };
const asked = [];
const fetchImpl = async (url, init) => {
  const u = String(url);
  if (u.includes('/api/ledger/subgraph')) asked.push(u);
  return fetch(u, init);
};

const doc = makeDoc('dark');
const host = doc.createElement('div');
doc.body.appendChild(host);
const page = await main.boot({ doc, host, apiBase: API, fetchImpl, charts, storage: null, theme: 'dark' });
const part = (id) => page.shell.partOf(id);
const ready = (id) => () => part(id).state === 'ready' || part(id).state === 'refused';

// The markings and the relations - the declarations the scenario names.
const book = page.markingBook;
const [die, core, step] = [book.add(), book.add(), book.add()];
book.edit(die, { label: 'Die' });
book.edit(core, { label: 'Core wafer' });
book.edit(step, { label: 'Step' });
page.relations.set('list', [{ from: 'die', predicate: 'bonded_from', to: 'die', both: false }, { from: 'die', predicate: 'in_container', to: 'wafer', both: false }]);
const label = { steps: [], value: { on: 'label', name: 'name' }, words: ['name'] };
const key = (name) => ({ steps: [], value: { on: 'key', name }, words: [name] });
const out = (p) => ({ predicate: p, direction: 'outgoing' });
// The server's largest node budget for the parts that walk past the bonding wafer (the default 400 is spent on defects).
const WIDE = { node_limit: 1000 };
const declare = (id, patch) => part(id).setDeclaration({ ...part(id).declaration(), system: null, filter: [], ...patch });
// The default page's visuals go; the four are added through the page's own call.
for (const id of ['scatter-1', 'cross-1', 'marked']) page.shell.remove(id);
const A = page.add('map');
const B = page.add('crossTable');
const C = page.add('crossTable');
const D = page.add('scatter');
declare(A, { row: 'die', start: { marking: 'marking:start' }, writes: die, encode: { x: key('x'), y: key('y') } });
declare(B, { walk: WIDE, row: 'die', start: { marking: die }, writes: core, encode: { rows: { steps: [out('bonded_from'), out('in_container')], value: { on: 'label', name: 'name' }, words: ['core wafer'] } } });
declare(C, { walk: WIDE, row: 'wafer', start: { marking: core }, writes: step, encode: { rows: { steps: [out('measures')], value: { on: 'edge', name: 'step' }, words: ['step'] } } });
declare(D, { walk: WIDE, row: 'wafer', start: { marking: step }, writes: 'marking:pick', markerBy: 'record',
  encode: { x: { steps: [out('measures')], value: { on: 'edge', name: 'value' }, words: ['value'], of: 'time' },
    y: { steps: [out('measures')], value: { on: 'edge', name: 'value' }, words: ['value'] }, color: { expr: 'If(Marked("Core wafer"), "B", "other")' } } });

const say = (...x) => console.log(...x);
const walks = () => asked.length;
const stat = (id) => page.stats.get(id) || {};
const report = [];
const step0 = walks();
// A: the bonding wafer the start - the map walks from it
page.markings.set('marking:start', entitySeedId('wafer', { wafer: WAFER }), SIGN.CASE);
await until(ready(A));
const cells = part(A).model.cells;
say(`A map: ${cells.length} cells drawn, ${part(A).model.notDrawn} not drawn, walks ${walks() - step0}`);
// A die that was bonded: the one whose B shows core wafers - the first drawn
const s1 = walks();
const t1 = Date.now();
part(A).markHub([['x', cells[0].where[0]], ['y', cells[0].where[1]]], cells[0].ids, {});
await until(ready(B));
const b = part(B).model;
say(`B cross: rows ${b.rowKeys.length} (${b.rowKeys.slice(0, 4).join(', ')}...), total ${b.total}, walks ${walks() - s1}, ${Date.now() - t1} ms, layer ${JSON.stringify(page.layers.last)}`);
report.push({ step: 'A->B', walks: walks() - s1 });
// B: a core wafer pressed - its row head's hub
const coreRow = b.rowKeys.findIndex((k) => k !== '(Empty)');
const s2 = walks();
part(B).markHub([['core wafer', b.rowKeys[coreRow]]], b.rowIds[coreRow], {});
await until(ready(C));
const c = part(C).model;
say(`C cross: steps ${c.rowKeys.length} (${c.rowKeys.join(', ')}), total ${c.total}, walks ${walks() - s2}, layer ${JSON.stringify(page.layers.last)}`);
// C: a step pressed
const stepRow = c.rowKeys.findIndex((k) => k !== '(Empty)');
const s3 = walks();
part(C).markHub([['step', c.rowKeys[stepRow]]], c.rowIds[stepRow], {});
await until(ready(D));
const d = part(D).model;
const byCat = {};
for (const p of d.points) byCat[p.category] = (byCat[p.category] || 0) + 1;
say(`D scatter: ${d.points.length} points (${JSON.stringify(byCat)}), x ${d.xKind}, ${d.notDrawn} not drawn, ${d.several} several, unknown ${stat(D).unknown || 0}, walks ${walks() - s3}`);
const bWafers = () => [...new Set(part(D).model.points.filter((p) => p.category === 'B').map((p) => p.label))];
say(`D B wafers: ${bWafers().join(', ')} (B pressed: ${b.rowKeys[coreRow]})`);
// The numbers: the layer on a marking change (another core wafer pressed in B), the graph
const otherRow = b.rowKeys.findIndex((k, i) => i !== coreRow && k !== '(Empty)');
const computed0 = page.layers.computed;
const s5 = walks();
part(B).markHub([['core wafer', b.rowKeys[otherRow]]], b.rowIds[otherRow], {});
await settle();
await until(ready(C));
await until(ready(D));
say(`B pressed ${b.rowKeys[otherRow]}: layers computed ${page.layers.computed - computed0}, last ${JSON.stringify(page.layers.last)}, walks ${walks() - s5}`);
say(`D B wafers now: ${bWafers().join(', ')}; unknown ${stat(D).unknown || 0}`);
const kept = page.save();
// No relation: D's points all other
page.relations.set('list', []);
await settle();
const none = {};
for (const p of part(D).model.points) none[p.category] = (none[p.category] || 0) + 1;
say(`no relations: D ${JSON.stringify(none)}`);
say(`graph: ${page.layers.graph.nodes.size} nodes, ${page.layers.graph.edges.size} edges; walks in all ${walks() - step0}`);
const save = argOf('--save', null);
// Saved on a two-by-two layout - A B over C D - so the shots show the four alike.
const leaf = (pid) => ({ id: pid, size: 1 });
const grid = { split: 'column', children: [{ split: 'row', size: 1, children: [leaf(A), leaf(B)] }, { split: 'row', size: 1, children: [leaf(C), leaf(D)] }] };
if (save) { writeFileSync(save, JSON.stringify({ kept: { ...kept, root: grid }, wafer: WAFER, ids: { A, B, C, D } }, null, 1)); say(`saved ${save}`); }
process.exit(0);
