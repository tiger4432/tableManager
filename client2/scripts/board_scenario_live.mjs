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
// ready: walked, and no walk of its in flight (a value walk comes after the rows - lead-board-10)
const ready = (id) => () => (part(id).state === 'ready' || part(id).state === 'refused') && !(part(id).aborts && part(id).aborts.size);

// The markings and the relations - the declarations the scenario names.
const book = page.markingBook;
const [die, core, step] = [book.add(), book.add(), book.add()];
book.edit(die, { label: 'Die' });
book.edit(core, { label: 'Core wafer' });
book.edit(step, { label: 'Step' });
page.relations.set('list', [{ from: 'die', predicate: 'bonded_from', to: 'die', both: false }, { from: 'die', predicate: 'in_container', to: 'wafer', both: false },
  { from: 'wafer', predicate: 'has_measurement', to: 'measurement', both: false }]);
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
// C: the measurements of the core wafer pressed in B - a B cell stands for the core wafer node (hubs.js nodesOfPress), the
// route the shortest wafer -has_measurement-> measurement, no route named; its rows by their step.
const attr = (name) => ({ steps: [], value: { on: 'node', name }, words: [name] });
declare(C, { walk: WIDE, row: 'measurement',
  start: { marking: core }, writes: step, encode: { rows: attr('step') } });
// D: those measurements of the step pressed in C - a point a measurement, X its eventtime, Y its value, red where the
// Core wafer marking reaches it along the relations, grey elsewhere (the declaration's colours).
declare(D, { walk: WIDE, row: 'measurement', start: { marking: step }, writes: 'marking:pick', colors: { B: '#E8423F', other: '#8C8C8C' },
  encode: { x: attr('eventtime'), y: attr('value'), color: { expr: 'If(Marked("Core wafer"), "B", "other")' } } });

const say = (...x) => console.log(...x);
const report = [];
// THE CLOCK (lead 10-14 «누름 → 연쇄 마지막 부품 그림 끝 ≤ 1 s»): each part's requests (asked · first answer · every
// answer in), its fold and its draw, from a press. The draw is the stub document's - not a browser's paint.
const clocks = new Map();
const watch = (id) => {
  const p = part(id);
  const c = { requests: 0, inFlight: 0, together: 0, fetchMs: 0, foldMs: 0, drawMs: 0 };
  clocks.set(id, c);
  const f = p.fetchWalk;
  p.fetchWalk = async (params) => {
    const t = performance.now();
    c.requests += 1; c.inFlight += 1; c.together = Math.max(c.together, c.inFlight);
    if (c.asked == null) c.asked = t;
    try { return await f(params); } finally { const e = performance.now(); c.inFlight -= 1; c.fetchMs += e - t; if (c.first == null) c.first = e; c.received = e; }
  };
  const fold = p.refold.bind(p);
  const draw = p.render.bind(p);
  p.render = (...a) => { const t = performance.now(); const r = draw(...a); const e = performance.now(); c.drawMs += e - t; c.drawn = e; return r; };
  p.refold = (...a) => { const t = performance.now(); const d0 = c.drawMs; const r = fold(...a); c.foldMs += performance.now() - t - (c.drawMs - d0); return r; };
};
const timed = async (name, press, ids) => {
  for (const id of ids) watch(id);
  const t0 = performance.now();
  await press();
  // each in turn: drawn since the press and nothing of its in flight (a walk in hand asks nothing; a start pruned empty draws none)
  for (const id of ids) await until(() => clocks.get(id).drawn != null && part(id).state !== 'walking' && !(part(id).aborts && part(id).aborts.size));
  const ms = (x) => (x == null ? '-' : String(Math.round(x - t0)));
  say(`CLOCK ${name} (ms from the press): part | asked | first answer | all in | drawn | requests (at once) | fetch | fold | draw`);
  for (const id of ids) {
    const c = clocks.get(id);
    say(`CLOCK   ${id} | ${ms(c.asked)} | ${ms(c.first)} | ${ms(c.received)} | ${ms(c.drawn)} | ${c.requests} (${c.together}) | ${Math.round(c.fetchMs)} | ${Math.round(c.foldMs)} | ${Math.round(c.drawMs)}`);
  }
  report.push({ step: name, ms: Math.round(clocks.get(ids[ids.length - 1]).drawn - t0) });
};
// C's route: from the bonding dies through their bonded_from to the core dies' wafers (die -> die -> wafer).
const takeRoute = (id, chain) => { const r = part(id).routes().find((x) => x.chain.join('>') === chain); if (r) declare(id, { ...part(id).declaration(), route: r }); return Boolean(r); };
const walks = () => asked.length;
const stat = (id) => page.stats.get(id) || {};
const step0 = walks();
// A: the bonding wafer the start - the map walks from it
await timed('start marked -> A', () => page.markings.set('marking:start', entitySeedId('wafer', { wafer: WAFER }), SIGN.CASE), [A]);
const cells = part(A).model.cells;
say(`A map: ${cells.length} cells drawn, ${part(A).model.notDrawn} not drawn, walks ${walks() - step0}`);
// A coordinate pressed - B walks from its die along B's route (die to die: the die itself) and counts its core wafer.
const press = async (cell) => {
  const ticket = part(B).walking;
  part(A).markHub([['x', cell.where[0]], ['y', cell.where[1]]], cell.ids, {});
  await until(() => part(B).walking > ticket && ready(B)());
  return part(B).model;
};
const s1 = walks();
const t1 = Date.now();
const coresOf = (m) => m.rowKeys.filter((k) => k !== '(Empty)');
let b = null;
let first = null;
const seen = [];
for (const cell of cells) {
  b = await press(cell);
  if (coresOf(b).length) {
    if (!first) first = { cell, cores: coresOf(b) };
    else if (coresOf(b).join() !== first.cores.join()) { seen.push({ cell, cores: coresOf(b) }); break; }
  }
}
say(`B route ${JSON.stringify(part(B).walkedRoute)} asked follow/hops ${(() => { const q = new URL(asked[asked.length - 1]).searchParams; return JSON.stringify([q.getAll('follow'), q.get('hops')]); })()}`);
say(`B die ${first.cell.where} -> core wafers ${first.cores.join(', ')}; die ${seen[0] ? seen[0].cell.where : '-'} -> ${seen[0] ? seen[0].cores.join(', ') : '-'}`);
// a die not pressed yet - no walk of B's in hand for it; then the first die again - B's walk in hand
const fresh = cells[cells.length - 1];
await timed('A pressed (a new die) -> B', () => part(A).markHub([['x', fresh.where[0]], ['y', fresh.where[1]]], fresh.ids, {}), [B]);
await timed('A pressed (a die pressed before) -> B', () => part(A).markHub([['x', first.cell.where[0]], ['y', first.cell.where[1]]], first.cell.ids, {}), [B]);
b = part(B).model;
say(`B cross: rows ${b.rowKeys.length} (${b.rowKeys.slice(0, 4).join(', ')}...), total ${b.total}, walks ${walks() - s1}, ${Date.now() - t1} ms, layer ${JSON.stringify(page.layers.last)}`);
report.push({ step: 'A->B', walks: walks() - s1 });
// B: a core wafer's cell pressed - it stands for the core wafer node, not a hub of B's dies
const coreRow = b.rowKeys.findIndex((k) => k !== '(Empty)');
const s2 = walks();
say(`C routes before B is pressed: ${part(C).routes().length}`);
part(B).markHub([['core wafer', b.rowKeys[coreRow]], ['(None)', '']], b.grid[coreRow][0].ids, {});
await until(ready(C));
say(`B marking: ${JSON.stringify(page.markings.entries(core).map(([id]) => [id, (page.layers.graph.nodes.get(id) || {}).type || 'hub']))}; B cell marked ${part(B).model.grid[coreRow][0].marked}`);
say(`C routes: ${part(C).routes().map((r) => r.chain.join('>') + ' ' + r.follow.join('+')).join(' | ')}; taken ${JSON.stringify(part(C).walkedRoute)}`);
const c = part(C).model;
say(`C cross: steps ${c.rowKeys.length} (${c.rowKeys.join(', ')}), total ${c.total}, walks ${walks() - s2}, layer ${JSON.stringify(page.layers.last)}`);
// C: a step pressed
const stepRow = c.rowKeys.findIndex((k) => k !== '(Empty)');
const s3 = walks();
await timed('C pressed -> D', () => part(C).markHub([['step', c.rowKeys[stepRow]]], c.rowIds[stepRow], {}), [D]);
const d = part(D).model;
const byCat = {};
const catOf = (pt) => part(D).colors.of.get(pt.ids[0]).category;
for (const pt of d.points) byCat[catOf(pt)] = (byCat[catOf(pt)] || 0) + 1;
say(`D scatter: ${d.points.length} points (${JSON.stringify(byCat)}), x ${d.xKind}, ${d.notDrawn} not drawn, ${d.several} several, unknown ${stat(D).unknown || 0}, walks ${walks() - s3}`);
const bWafers = () => [...new Set(part(D).model.points.filter((pt) => catOf(pt) === 'B').map((pt) => pt.label))];
say(`D B wafers: ${bWafers().join(', ')} (B pressed: ${b.rowKeys[coreRow]})`);
const fills = () => JSON.stringify(Object.entries(part(D).model.points.reduce((acc, pt) => { acc[pt.fill] = (acc[pt.fill] || 0) + 1; return acc; }, {})));
say(`D fills ${fills()} (declared B #E8423F, other #8C8C8C)`);
// No relation: the Core wafer marking is its dies only - no measurement is in it, every point other
const keptRelations = page.relations.get('list');
page.relations.set('list', []);
await settle();
say(`no relations: D fills ${fills()}`);
page.relations.set('list', keptRelations);
await settle();
say(`relations back: D fills ${fills()}`);
// The numbers: the layer on a marking change (the other die's core wafer pressed in B), the graph
const b2 = seen[0] ? await press(seen[0].cell) : b;
const otherRow = b2.rowKeys.findIndex((k) => k !== '(Empty)');
const computed0 = page.layers.computed;
const s5 = walks();
await timed('B pressed -> C -> D', () => part(B).markHub([['core wafer', b2.rowKeys[otherRow]]], b2.rowIds[otherRow], {}), [C, D]);
say(`B pressed ${b2.rowKeys[otherRow]}: layers computed ${page.layers.computed - computed0}, last ${JSON.stringify(page.layers.last)}, walks ${walks() - s5}`);
say(`D after: ${part(D).state} (the Step marking pruned: ${page.markings.entries(step).length} entries); unknown ${stat(D).unknown || 0}`);
const kept = page.save();
say(`CLOCK report ${JSON.stringify(report)}`);
say(`graph: ${page.layers.graph.nodes.size} nodes, ${page.layers.graph.edges.size} edges; walks in all ${walks() - step0}`);
const save = argOf('--save', null);
// Saved on a two-by-two layout - A B over C D - so the shots show the four alike.
const leaf = (pid) => ({ id: pid, size: 1 });
const grid = { split: 'column', children: [{ split: 'row', size: 1, children: [leaf(A), leaf(B)] }, { split: 'row', size: 1, children: [leaf(C), leaf(D)] }] };
if (save) { writeFileSync(save, JSON.stringify({ kept: { ...kept, root: grid }, wafer: WAFER, ids: { A, B, C, D } }, null, 1)); say(`saved ${save}`); }
process.exit(0);
