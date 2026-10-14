// The Board's layout and its Table (lead 10-13, owner «스팟파이어 사용해서 기능 체크 후 똑같이 만들어»): the page's split
// tree (rnd_board/split_tree.js) and the shell that draws it (grid_shell.js) - dock on each edge, a line dragged and
// clamped, the last part closed, a part added where Spotfire adds one, a redraw that never seats again, maximize; the
// test bed page on it (testbed/main.js) - two Boards side by side, Save keeping the tree, an older save still opening,
// each kind added; Spotfire's «Limit data using markings» (testbed/visual_part.js limitRows) and the Table kind
// (testbed/kinds/table.js). Every subject is IMPORTED; the page is the board's document stub.
//
// CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';
import { makeDoc, makeObserver, walk } from './lib/board_dom.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src');
const REAL = {
  tree: await import('../src/rnd_board/split_tree.js'),
  shell: await import('../src/rnd_board/grid_shell.js'),
  main: await import('../src/testbed/main.js'),
  visual: await import('../src/testbed/visual_part.js'),
  table: await import('../src/testbed/kinds/table.js'),
  scatter: await import('../src/testbed/kinds/scatter.js'),
  baskets: await import('../src/walk/start_baskets.js'),
  units: await import('../src/testbed/units.js'),
  color: await import('../src/testbed/color_by.js'),
  layer: await import('../src/testbed/marking_layer.js'),
  map: await import('../src/testbed/kinds/map.js'),
  sheet: await import('../src/testbed/kinds/sheet.js'),
  slot: await import('../src/testbed/slot.js'),
  route: await import('../src/testbed/route.js'),
  walks: await import('../src/testbed/part_walks.js'),
  api: await import('../src/rnd_board/api.js'),
  trend: await import('../src/walk/trend.js'),
  reach: await import('../src/walk/reach_table.js'),
  show: await import('../src/testbed/show_items.js'),
  tooltip: await import('../src/testbed/tooltip.js'),
  cond: await import('../src/testbed/condition_editor.js'),
  trellis: await import('../src/testbed/trellis.js'),
  shape: await import('../src/testbed/shape_by.js'),
  picker: await import('../src/testbed/picker.js'),
  cross: await import('../src/testbed/kinds/cross_table.js'),
  hubs: await import('../src/testbed/hubs.js'),
};
const { localStamp } = await import('../src/server_time.js');
const { MarkingStore, SIGN } = await import('../src/rnd_board/marking_store.js');
const { HubBook, hubId, holds, isHubId, hubOf } = await import('../src/testbed/hubs.js');
const { KeyedStore } = await import('../src/testbed/keyed_store.js');
const { Panel } = await import('../src/rnd_board/panel.js');
const { statusWords } = await import('../src/testbed/status_part.js');

const settle = async () => { for (let i = 0; i < 10; i += 1) await new Promise((r) => setTimeout(r, 0)); };
const json = (x) => JSON.stringify(x);
const leaf = (id, size = 1) => ({ id, size });
const AB = () => ({ split: 'row', children: [leaf('A'), leaf('B')] });

// ── the walk: four wafers, a measured temp ──
const wafer = (id) => ({ id, type: 'wafer', label: id, keys: { wafer: id }, attributes: {} });
const ANSWER = {
  nodes: [wafer('W1'), wafer('W2'), wafer('W3'), wafer('W4'), { id: 'QT', type: 'quantity', label: 'temp', keys: { quantity: 'temp' }, attributes: {} }],
  edges: [['W1', '30'], ['W2', '10'], ['W3', '20']].map(([w, v]) => ({ source: w, target: 'QT', predicate: 'measures', qualifiers: { value: v } })),
  truncated: { nodes: false, edges: false, depth: false, claims: false, actions: false, reason: null },
};
const NAME = { steps: [], value: { on: 'label', name: 'name' }, words: ['name'] };
const TEMP = { steps: [{ predicate: 'measures', direction: 'outgoing' }], value: { on: 'edge', name: 'value' }, words: ['temp'] };

/** A part that counts its mounts - so a redraw that seats again is seen. */
function countingPart(seen) {
  return class extends Panel {
    mount() { seen.mounts += 1; super.mount(); }
    render() { this.host.textContent = this.title; }
  };
}

function charts() { return { init: () => ({ setOption() {}, dispatchAction() {}, on() {}, getZr() { return { on() {} }; }, resize() {}, dispose() {} }) }; }

/** The test bed page booted on a stub, its walks counted; `storage` shared between pages to reopen a save. */
async function page(M, storage = null, answerOf = () => ANSWER) {
  const doc = makeDoc('dark');
  const host = doc.createElement('div');
  doc.body.appendChild(host);
  const asked = [];
  const fetchImpl = async (url) => {
    const u = String(url);
    if (u.includes('/api/ledger/subgraph')) asked.push(u);
    const body = u.includes('/api/ledger/declaration') ? { entities: [{ type: 'wafer' }], predicates: [] }
      : u.includes('/api/ledger/subgraph') ? answerOf(u) : { nodes: [] };
    return { ok: true, status: 200, json: async () => JSON.parse(JSON.stringify(body)) };
  };
  const p = await M.main.boot({ doc, host, apiBase: '', fetchImpl, charts: charts(), storage, theme: 'dark' });
  // A start picked: every visual walks from it.
  p.markings.set('marking:start', 'W1', SIGN.CASE);
  await settle();
  return { ...p, doc, host, asked };
}

function memoryStorage() {
  const memory = new Map();
  return { getItem: (k) => (memory.has(k) ? memory.get(k) : null), setItem: (k, v) => memory.set(k, String(v)), removeItem: (k) => memory.delete(k) };
}

async function measure(M) {
  const out = {};
  const T = M.tree;
  // S1: a part docked on each edge of another
  out.dock = ['left', 'right', 'top', 'bottom'].map((edge) => { const r = T.dockLeaf(AB(), 'B', 'A', edge); return [r.split, T.leafIds(r)]; });
  // S1': on an edge of the page - the whole tree on the other side; onto itself - nothing moves
  const three = { split: 'row', children: [leaf('A'), { split: 'column', size: 1, children: [leaf('B'), leaf('C')] }] };
  const paged = T.dockLeaf(three, 'C', null, 'bottom');
  out.pageEdge = [paged.split, T.leafIds(paged), json(T.dockLeaf(AB(), 'A', 'A', 'left')) === json(AB())];
  // S2: a line dragged - the pair keeps its sum, neither under the floor; a pair already under two floors does not move
  out.resize = [T.resizePair([1, 1, 2], 0, 500, 500, 100, 60), T.resizePair([1, 1], 0, 500, 500, 900, 60), T.resizePair([1, 1], 0, 500, 500, -900, 60),
    T.resizePair([1, 1], 0, 50, 50, 10, 60)];
  // S3: the last part closed - no tree; a part added to none is the tree
  out.last = [T.removeLeaf({ id: 'A' }, 'A'), T.addLeaf(null, 'N', {})];
  // S4: a part closed gives its share back to the ones beside it; a split left with one child is that child, in its share
  out.share = [T.removeLeaf({ split: 'row', children: [leaf('A'), leaf('B'), leaf('C', 2)] }, 'B'),
    T.removeLeaf({ split: 'row', children: [leaf('A', 3), { split: 'column', size: 2, children: [leaf('B'), leaf('C')] }] }, 'C')];
  // S5: an added part splits the largest (by area), side by side when it is wider, stacked otherwise
  out.add = [T.addLeaf(AB(), 'N', { A: { width: 400, height: 300 }, B: { width: 500, height: 500 } }),
    T.addLeaf(AB(), 'N', { A: { width: 800, height: 300 }, B: { width: 500, height: 400 } })].map((r) => json(r));
  // S6: the edge a drop is nearest, by the box's own proportions
  const box = { left: 0, top: 0, width: 1000, height: 100 };
  out.edges = [T.edgeAt(box, 50, 50), T.edgeAt(box, 950, 50), T.edgeAt(box, 500, 10), T.edgeAt(box, 500, 90)];
  // S7: a drop on a part's middle (owner 10-14, Spotfire's): the two swap places - shares and the tree's shape kept;
  // near a side (a quarter of the side across) that edge as before; onto itself or a part not there - nothing moves
  const tree3 = { split: 'row', children: [leaf('A', 2), { split: 'column', size: 1, children: [leaf('B'), leaf('C', 3)] }] };
  out.swap = [json(T.swapLeaves(tree3, 'A', 'C')), json(T.swapLeaves(tree3, 'A', 'A')) === json(tree3), json(T.swapLeaves(tree3, 'A', 'Z')) === json(tree3),
    T.edgeAt(box, 500, 50, T.DROP_EDGE), T.edgeAt(box, 200, 50, T.DROP_EDGE), T.edgeAt(box, 500, 20, T.DROP_EDGE)];
  // L1-L2: the markings' limit
  const book = new HubBook();
  const hub = book.put(hubId('wafer', [['lot', 'L1']]), ['W1', 'W3']);
  const marks = { P: [['W1', SIGN.CASE], ['W2', SIGN.CASE]], Q: [['W2', SIGN.CASE], ['W3', SIGN.CASE]], E: [], H: [[hub, SIGN.CASE]] };
  const ids = ['W1', 'W2', 'W3', 'W4'];
  const store = new MarkingStore();
  for (const [name, entries] of Object.entries(marks)) store.replace(name, entries);
  const layers = new M.layer.MarkingLayers({ markings: store, hubs: book });
  const lim = (markings, must, none) => M.visual.limitRows(ids, { markings, must, none }, layers);
  out.limit = [lim(['P', 'Q'], 'all', 'all'), lim(['P', 'Q'], 'any', 'all'), lim(['E'], 'all', 'all'), lim(['E'], 'all', 'empty'),
    lim(['E', 'Q'], 'all', 'all'), M.visual.limitRows(ids, null, layers)];
  out.hub = [lim(['H'], 'all', 'empty'), lim(['H', 'P'], 'all', 'empty')];
  // T1: the table's model - its columns by the encode, sorted both ways, blanks last, numbers by number
  const read = (v) => (v === null ? { state: 'empty' } : { state: 'one', value: v });
  const rows = [['W1', '30'], ['W2', '10'], ['W3', null], ['W4', '9']].map(([id, t]) => ({ id, label: id, reads: { col1: read(id), col3: read(t) } }));
  const tdecl = (sort) => ({ encode: { col3: TEMP, col1: NAME }, sort });
  const model = (sort) => M.table.tableModel(rows, { ...M.color.paintRows(rows, { palette: { one: ['#111111', '#222222'], bg: '#000000', cat: [] }, declaration: tdecl(sort), marked: (id) => id === 'W2' }), declaration: tdecl(sort) });
  const order = (m) => m.lines.map((l) => l.id);
  out.table = { keys: model().keys, next: model().next, numeric: model().numeric, asc: order(model({ key: 'col3', desc: false })),
    desc: order(model({ key: 'col3', desc: true })), marked: model().lines.filter((l) => l.marked).map((l) => l.id), stale: order(model({ key: 'col9' })) };
  return out;
}

/** A table seated alone from M's visual part - its limit's counts. */
async function seated(M) {
  const doc = makeDoc('dark');
  const markings = new MarkingStore();
  const stats = new KeyedStore();
  markings.set('marking:lim', 'W1', SIGN.CASE);
  markings.set('marking:pick', 'W2', SIGN.CASE);
  const decl = { id: 'T', part: 'visual', kind: 'table', row: 'wafer', start: { marking: null }, system: null, filter: [],
    limit: { markings: ['marking:lim'], must: 'all', none: 'empty' }, encode: { col1: NAME }, reads: 'marking:pick', writes: 'marking:pick' };
  const part = new M.visual.VisualPart(doc.createElement('div'), { doc, markings, reads: decl.reads, writes: decl.writes, start: decl.start,
    declaration: decl, kinds: { table: M.table.kind }, fetchWalk: async () => ({ ok: true, body: JSON.parse(JSON.stringify(ANSWER)) }),
    filters: new KeyedStore(), stats, active: new KeyedStore(), hubs: new HubBook(), names: new Map(), charts: charts() });
  part.mount();
  await settle();
  const before = (({ rows, of, limit, hidden, marked }) => ({ rows, of, limit, hidden, marked }))(stats.get('T'));
  const filterable = stats.get('T').slots.map((s) => [s.key, s.words]);
  markings.set('marking:lim', 'W4', SIGN.CASE);
  await settle();
  const after = part.model.lines.map((l) => l.id);
  // A line pressed: with Ctrl it joins the pick, without it is the pick.
  const press = (id, ctrlKey) => walk(part.host).filter((n) => n.tagName === 'TR' && n.children.length > 0)
    .find((tr) => tr.children[0]._text === id).dispatch('click', { ctrlKey, stopPropagation() {} });
  const picked = () => markings.entries('marking:pick').map(([id]) => id).sort();
  press('W4', true);
  const added = picked();
  press('W1', false);
  return { before, after, added, replaced: picked(), filterable };
}

async function shells(M) {
  const out = {};
  // G3: a redraw moves the panels - dock, resize, maximize, restore seat nothing again
  const doc = makeDoc('dark');
  const host = doc.createElement('div');
  const seen = { mounts: 0 };
  const observe = makeObserver();
  const shell = new M.shell.GridShell(host, { doc, markings: new MarkingStore(), parts: { fake: countingPart(seen) }, observeSize: observe });
  shell.render({ gap: '2px', panels: ['A', 'B', 'C'].map((id) => ({ id, part: 'fake', title: id })).concat([{ id: 'D', part: 'fake', dock: 'right', size: '200px' }]),
    root: { split: 'row', children: [leaf('A'), { split: 'column', size: 1, children: [leaf('B'), leaf('C')] }] } });
  const parts = ['A', 'B', 'C'].map((id) => shell.partOf(id));
  const cells = () => walk(host).filter((n) => n.attrs && n.attrs['data-cell']).map((n) => n.attrs['data-cell']);
  shell.dock('C', 'A', 'left');
  shell.resizeAt([], 0, 400, 400, 100);
  shell.maximize('B');
  const maxed = cells();
  shell.maximize(null);
  out.redraw = { mounts: seen.mounts, same: ['A', 'B', 'C'].every((id, k) => shell.partOf(id) === parts[k]), maxed, cells: cells(),
    root: json(shell.root), docked: walk(host).some((n) => n.attrs && n.attrs['data-dock'] === 'right' && n.children.some((c) => c.attrs['data-panel'] === 'D')) };
  // G3s: a drop on a middle - A and B swap places, nothing seated again
  const order = M.tree.leafIds(shell.root);
  const mountsNow = seen.mounts;
  const [one, , last] = order;
  const shape = (r) => json(r).replace(/"id":"[A-C]"/g, 'id');
  const shapeBefore = shape(shell.root);
  shell.dock(one, last, 'center');
  out.swapShell = [M.tree.leafIds(shell.root).join() + (shape(shell.root) === shapeBefore ? ' same shape' : ' other shape'), [last, order[1], one].join() + ' same shape', seen.mounts === mountsNow, cells().length];
  // G4: the last area part closed - the area says so; one added is the tree; a docked panel is not closed
  for (const id of ['A', 'B', 'C']) shell.remove(id);
  shell.remove('D');
  const empty = walk(host).some((n) => String(n.className).includes('rb-area__empty') && n._text === 'Add a visualization');
  shell.add({ id: 'N', part: 'fake', title: 'N' });
  out.last = { root: json(shell.root), empty, docked: Boolean(shell.partOf('D')), seated: shell.panels.size };
  return out;
}

async function pages(M) {
  const out = {};
  // G1: two Boards side by side - one's layout and marking leave the other alone
  const one = await page(M);
  const two = await page(M);
  const before = json(two.shell.root);
  one.shell.dock('marked', 'scatter-1', 'left');
  one.markings.set('marking:pick', 'W1', SIGN.CASE);
  await settle();
  const linesOf = (p) => (p.shell.partOf('marked').model || { lines: [] }).lines.map((l) => l.id);
  out.two = { otherTree: json(two.shell.root) === before, mine: linesOf(one), other: linesOf(two), trees: json(one.shell.root) !== json(two.shell.root) };
  // G2: Save keeps the tree and the visuals; a reopen draws them; an older save (visuals by id) still opens on the layout's tree
  const storage = memoryStorage();
  const first = await page(M, storage);
  first.shell.dock('cross-1', null, 'top');
  first.shell.resizeAt([], 0, 300, 600, 100);
  const sorted = first.shell.partOf('marked');
  sorted.setDeclaration({ ...sorted.declaration(), sort: { key: 'col1', desc: true } });
  await settle();
  const kept = first.save();
  const second = await page(M, storage);
  const visuals = (p) => json(p.declarations().map((d) => [d.id, d.kind, d.sort || null]).sort());
  out.save = { tree: json(second.shell.root) === json(kept.root), visuals: visuals(second) === visuals(first), sortKept: (second.shell.partOf('marked').decl.sort || {}).desc };
  const old = memoryStorage();
  // G2c: a part dropped on another's middle - the two swap; Save keeps it, a reopen draws it so
  const swapped = await page(M, memoryStorage());
  const was = swapped.shell.root;
  swapped.shell.dock('scatter-1', 'marked', 'center');
  const keptSwap = swapped.save();
  out.swapSaved = [M.tree.leafIds(was).join(), M.tree.leafIds(swapped.shell.root).join(), json(keptSwap.root) === json(swapped.shell.root),
    json(was).replace(/"scatter-1"|"marked"/g, '"_"') === json(swapped.shell.root).replace(/"scatter-1"|"marked"/g, '"_"')];
  old.setItem('testbed:visuals', json([{ ...first.shell.partOf('scatter-1').declaration(), encode: { x: TEMP } }]));
  const third = await page(M, old);
  out.older = { tree: json(third.shell.root) === json(M.main.LAYOUT.root), x: Boolean(third.shell.partOf('scatter-1').decl.encode.x), docks: ['banner', 'start', 'status', 'properties', 'filters'].every((id) => third.shell.partOf(id)) };
  // G5: each kind added through the left bar's call - the largest one split, the new one the active one, walked
  const fourth = await page(M);
  const sizes = { 'scatter-1': [900, 960], 'cross-1': [800, 480], marked: [800, 480] };
  for (const [id, [w, h]] of Object.entries(sizes)) fourth.shell.panels.get(id).box = { width: w, height: h };
  const walked = fourth.asked.length;
  const added = [];
  let firstPath = null;
  let scatterPath = null;
  for (const kind of Object.keys(M.main.KINDS)) {
    added.push(fourth.add(kind));
    if (!firstPath) { firstPath = json(fourth.shell.pathOf(added[0])); scatterPath = json(fourth.shell.pathOf('scatter-1')); }
  }
  await settle();
  out.add = { ids: added, kinds: added.map((id) => fourth.shell.partOf(id).decl.kind), active: fourth.active.get('active'),
    firstPath, scatterPath, walked: fourth.asked.length - walked,
    flyout: (() => { const banner = fourth.shell.partOf('banner'); banner.toggle('types'); const names = walk(banner.host).filter((n) => String(n.className) === 'sf-flyout__it').map((n) => n.textContent); banner.toggle(null); return names; })() };
  // L3 / T2: the Marked table - limited by the pick: empty, then a hub's members, a line pressed re-marks, a head sorts
  const fifth = await page(M);
  const marked = fifth.shell.partOf('marked');
  const emptyFirst = marked.model.lines.length;
  const hub = fifth.hubs.put(hubId('wafer', [['lot', 'L1']]), ['W1', 'W3']);
  fifth.markings.replace('marking:pick', [[hub, SIGN.CASE]]);
  await settle();
  const viaHub = marked.model.lines.map((l) => l.id);
  const stats = fifth.stats.get('marked');
  const tr = walk(marked.host).filter((n) => n.tagName === 'TR' && n.className.includes('is-marked'));
  tr[1].dispatch('click', { ctrlKey: false, stopPropagation() {} });
  await settle();
  const afterPress = marked.model.lines.map((l) => l.id);
  const th = walk(marked.host).find((n) => n.tagName === 'TH' && n._text === 'name');
  th.dispatch('click');
  await settle();
  const wrap = walk(marked.host).find((n) => String(n.className) === 'tb-table__wrap');
  wrap.dispatch('click');
  await settle();
  out.marked = { emptyFirst, viaHub, counts: [stats.rows, stats.of, stats.limit, stats.hidden], afterPress, sort: marked.decl.sort,
    cleared: fifth.markings.entries('marking:pick').length, emptyAgain: marked.model.lines.length };
  return out;
}

// ── the markings as a declaration and the chain (owner 10-13 «마킹 클래스 추가» · «a 부품 마킹 -> b 부품 입력 마킹2 -> c …») ──
// A walk from the positive seeds reaches them and the next wafer: W1 -> W2 -> W3 -> W4 -> W5.
const NEXT = { W1: 'W2', W2: 'W3', W3: 'W4', W4: 'W5' };
function chainAnswer(url) {
  const seeds = new URL(url, 'http://x').searchParams.getAll('positive');
  const ids = [...new Set(seeds.flatMap((s) => [s, NEXT[s]]).filter(Boolean))];
  return { nodes: ids.map(wafer), edges: [], truncated: ANSWER.truncated };
}
const seedsAsked = (urls) => urls.map((u) => { const q = new URL(u, 'http://x').searchParams; return q.get('seed_type') ? `type:${q.get('seed_type')}` : q.getAll('positive').join('+'); });

async function chains(M) {
  const out = {};
  const storage = memoryStorage();
  const p = await page(M, storage, chainAnswer);
  const book = p.markingBook;
  // K1: three markings added - the next free names, the people's words, a colour each not in use
  const [m3, m4, m5] = [book.add(), book.add(), book.add()];
  const list = book.list.get('list');
  out.added = { names: [m3, m4, m5], labels: list.map((m) => m.label), colours: new Set(list.map((m) => m.color)).size === list.length };
  // A emits m3; B receives m3 and emits m4; C receives m4 and emits m5 - each through its declaration
  const [a, b, c] = ['table', 'table', 'table'].map((k) => p.add(k));
  const part = (id) => p.shell.partOf(id);
  const declare = (id, patch) => part(id).setDeclaration({ ...part(id).declaration(), system: null, ...patch });
  declare(a, { writes: m3 });
  declare(b, { start: { marking: m3 }, writes: m4 });
  declare(c, { start: { marking: m4 }, writes: m5 });
  await settle();
  const lines = (id) => (part(id).model ? part(id).model.lines.map((l) => l.id) : []);
  const held = (name) => p.markings.entries(name).map(([id]) => id).sort();
  part(a).mark(['W2'], {});
  await settle();
  part(b).mark(['W2', 'W3'], {});
  await settle();
  part(c).mark(['W3', 'W4'], {});
  await settle();
  out.built = { b: lines(b), c: lines(c), held: [held(m3), held(m4), held(m5)] };
  // K2: A marks again - B walks from it, its marking keeps what its new data holds, so C walks from that: one walk each
  const before = p.asked.length;
  part(a).mark(['W1'], {});
  await settle();
  out.chain = { walks: seedsAsked(p.asked.slice(before)), b: lines(b), c: lines(c), held: [held(m3), held(m4), held(m5)] };
  // K3: a loop refused and named - A walking from m5 (m5 -> A -> m3 -> B -> m4 -> C -> m5); one part from what it writes
  const aWas = JSON.stringify(part(a).declaration());
  const refused = declare(a, { start: { marking: m5 } });
  p.active.set('active', a);
  await settle();
  const said = walk(p.shell.partOf('properties').host).filter((n) => String(n.className).includes('sf-props__refused')).map((n) => n._text);
  // the panel's Data lines: no Route (owner 10-14 - the part walks every route; a saved route is read, not walked)
  out.panel = walk(p.shell.partOf('properties').host).filter((n) => String(n.className) === 'sf-props__lab').map((n) => n._text);
  out.loop = { refused, kept: JSON.stringify(part(a).declaration()) === aWas, loop: part(a).loop, said,
    self: M.visual.chainLoop([{ id: 'S', start: { marking: m3 }, writes: m3 }]), limitIsNoStep: M.visual.chainLoop([{ id: 'T', start: { marking: 'marking:start' }, limit: { markings: [m3] }, writes: m3 }]) };
  // K5: Save, then a new page from it - the markings and the chain's declarations
  p.save();
  const again = await page(M, storage, chainAnswer);
  const marksKept = [m3, m4, m5].map((name) => again.markings.entries(name).map(([id]) => id));
  const decl = (q, id) => { const s = q.shell.partOf(id); if (!s) return null; const d = s.declaration(); return [d.start && d.start.marking, d.writes]; };
  const before2 = again.asked.length;
  if (again.shell.partOf(a)) again.shell.partOf(a).mark(['W2'], {});
  await settle();
  out.reopen = { labels: again.markingBook.list.get('list').map((m) => m.label), chain: [decl(again, a), decl(again, b), decl(again, c)],
    walks: seedsAsked(again.asked.slice(before2)), marksKept };
  const older = memoryStorage();
  older.setItem('testbed:visuals', JSON.stringify({ root: again.shell.layoutNow().root, visuals: again.declarations() }));
  out.olderSave = (await page(M, older, chainAnswer)).markingBook.list.get('list').map((m) => m.label);
  // K4: a marking deleted from the markings window - asked first, its users named; B writes none, C walks from «All», a
  // limit loses it; the start row's marking not deleted, the reply naming it
  part('marked').setDeclaration({ ...part('marked').declaration(), limit: { markings: ['marking:pick', m4], must: 'all', none: 'empty' } });
  await settle();
  const banner = part('banner');
  banner.toggle('markings');
  const rows = () => walk(banner.host).filter((n) => n.attrs && n.attrs['data-marking']).map((n) => n.attrs['data-marking']);
  const shown = rows();
  const x = (name) => walk(banner.host).find((n) => n.attrs && n.attrs['data-marking'] === name).children.find((k) => String(k.className) === 'sf-mark__x');
  const before3 = p.asked.length;
  x(m4).dispatch('click');
  const ask = walk(banner.host).filter((n) => String(n.className) === 'sf-mark__ask').map((n) => n.children[0]._text);
  walk(banner.host).find((n) => n.tagName === 'BUTTON' && n._text === 'Delete').dispatch('click');
  await settle();
  x('marking:start').dispatch('click');
  try { walk(banner.host).find((n) => n.tagName === 'BUTTON' && n._text === 'Delete').dispatch('click'); } catch (e) { /* a throw is a wrong answer below */ }
  const kept = walk(banner.host).filter((n) => String(n.className) === 'sf-mark__ask').map((n) => n.children[0]._text);
  walk(banner.host).find((n) => String(n.className).includes('sf-mark__add')).dispatch('click');
  out.deleted = { shown, ask, after: rows(), b: decl(p, b), c: decl(p, c), limit: part('marked').declaration().limit.markings,
    walks: seedsAsked(p.asked.slice(before3)), kept };
  // K6: a marking's colour is its marked lines' and points'
  book.edit(m3, { color: '#123456' });
  await settle();
  const sec = walk(part(a).host).find((n) => n.tagName === 'SECTION');
  const pal = { bg: '#000000', one: ['#111111', '#222222'], cat: [['#6489FA', '#4B67BC']] };
  const two = [{ id: 'W1', label: 'W1', reads: { x: { state: 'one', value: 1 }, y: { state: 'one', value: 2 } } }, { id: 'W2', label: 'W2', reads: { x: { state: 'one', value: 3 }, y: { state: 'one', value: 4 } } }];
  const pts = M.scatter.scatterModel(two, { ...M.color.paintRows(two, { marked: (id) => id === 'W2', markColor: '#123456', palette: pal }), palette: pal }).points;
  out.colour = { line: sec.style._props['--sf-marked'], unmarked: pts[0].fill !== '#123456', marked: pts[1].fill };
  return out;
}

/** The chain seated alone from M's visual part (three tables on one marking store) - what each walked from, what each
 *  marking keeps. */
async function seatedChain(M) {
  const doc = makeDoc('dark');
  const markings = new MarkingStore();
  const hubs = new HubBook();
  const walked = [];
  const seat = (id, start, writes) => {
    const decl = { id, part: 'visual', kind: 'table', row: 'wafer', start: { marking: start }, system: null, filter: [], encode: { col1: NAME }, writes };
    const part = new M.visual.VisualPart(doc.createElement('div'), { doc, markings, writes, start: decl.start, declaration: decl,
      kinds: { table: M.table.kind }, filters: new KeyedStore(), stats: new KeyedStore(), active: new KeyedStore(), hubs, names: new Map(), charts: charts(),
      fetchWalk: async (params) => { walked.push(`${id}:${(params.positive || []).join('+')}`); return { ok: true, body: chainAnswer(`/?${(params.positive || []).map((s) => `positive=${s}`).join('&')}`) }; } });
    part.mount();
    return part;
  };
  const [a, b, c] = [seat('A', 'm0', 'm1'), seat('B', 'm1', 'm2'), seat('C', 'm2', 'm3')];
  markings.set('m0', 'W1', SIGN.CASE);
  await settle();
  a.mark(['W2'], {});
  await settle();
  b.mark(['W2', 'W3'], {});
  await settle();
  c.mark(['W3', 'W4'], {});
  await settle();
  walked.length = 0;
  a.mark(['W1'], {});
  await settle();
  const held = (name) => markings.entries(name).map(([id]) => id).sort();
  return { walked: [...walked], held: [held('m1'), held('m2'), held('m3')] };
}

// ── the scatter's Marker by (owner 10-13): a marker a combination of the Marker by values - a hub of its rows ──
const LOT = { steps: [{ predicate: 'in_lot', direction: 'outgoing' }], value: { on: 'label', name: 'name' }, words: ['lot'] };
const PRODUCT = { steps: [{ predicate: 'of_product', direction: 'outgoing' }], value: { on: 'label', name: 'name' }, words: ['product'] };

function markerModels(M) {
  const one = (value) => ({ state: 'one', value });
  const pal = { bg: '#000000', one: ['#111111', '#222222'], cat: [['#6489FA', '#4B67BC']] };
  // W3 reads two temps; W4's press differs from W2's
  const DATA = [['W1', 'L1', 'A', [[30, 1]], 5], ['W2', 'L2', 'A', [[10, 1]], 5], ['W3', 'L1', 'B', [[20, 2], [26, 3]], 5], ['W4', 'L2', 'B', [[40, 2]], 7]];
  const rows = DATA.map(([id, lot, product, temps, press]) => ({ id, label: id,
    reads: { x: temps.length === 1 ? one(temps[0][0]) : { state: 'several', values: temps.map(([v]) => v) }, y: one(press), marker1: one(lot), marker2: one(product) },
    raw: { x: temps.map(([value, t]) => ({ value, t })), y: [{ value: press, t: 1 }] } }));
  const model = (encode, marked = () => false) => {
    const own = rows.map((r) => ({ ...r, reads: Object.fromEntries(Object.entries(r.reads).filter(([k]) => encode[k])) }));
    const decl = { row: 'wafer', encode };
    // the root's one spreading (units.js spreadUnits, lead-board-13 ②): a node's several x its marks, a hub of several left out
    const spread = M.units.spreadUnits(own, decl, Object.keys(encode), { record: 'y', drawn: ['x', 'y'] });
    const m = M.scatter.scatterModel(spread.units, { ...M.color.paintRows(own, { marked, palette: pal, declaration: decl }), palette: pal, declaration: decl });
    return { points: m.points.map((p) => [p.label, Math.round(p.x * 1000) / 1000, p.y, p.ids, p.marked]), several: spread.dropped.length };
  };
  const X = (reduce) => ({ ...TEMP, reduce });
  const Y = { steps: [], value: { on: 'attribute', name: 'press' }, words: ['press'] };
  return {
    none: model({ x: X(), y: Y }),
    lot: model({ x: X('Avg'), y: Y, marker1: LOT }, (id) => id === 'W3'),
    two: model({ x: X('Count'), y: Y, marker1: LOT, marker2: PRODUCT }),
    latest: model({ x: X('Latest'), y: { ...Y, reduce: 'Avg' }, marker1: LOT }),
    hub: M.units.unitsOf(rows, { row: 'wafer', encode: { x: X('Avg'), y: { ...Y, reduce: 'Avg' }, marker1: LOT } }, ['x', 'y', 'marker1'], 'y').map((p) => p.id),
    // value records: W9's two edges, three records then one - a unit a record; Latest on Y - a unit an edge
    records: (() => {
      const rec = (value, t, read) => ({ value, t, read });
      const row = { id: 'W9', label: 'W9', reads: { y: { state: 'several', values: ['1', '2', '3', '7'] } },
        raw: { y: [rec('1', 1, 0), rec('2', 2, 0), rec('3', 3, 0), rec('7', 4, 1)], x: [rec('t1', 1, 0), rec('t2', 2, 0), rec('t3', 3, 0), rec('t4', 4, 1)] } };
      const read = (decl) => M.units.unitsOf([row], decl, ['x', 'y'], 'y').map((u) => [u.id, u.reads.x.state === 'one' ? u.reads.x.value : u.reads.x.state, u.reads.y.value]);
      return [read({ markerBy: 'record', encode: { x: TEMP, y: TEMP } }), read({ markerBy: 'record', encode: { x: { ...TEMP, reduce: 'Latest' }, y: { ...TEMP, reduce: 'Latest' } } })];
    })(),
    // the root's slot list for a scatter: its axes, Marker by held and the next, Color by
    slots: [{}, { marker1: LOT }].map((encode) => new M.visual.VisualPart(makeDoc('dark').createElement('div'), { doc: makeDoc('dark'), markings: new MarkingStore(),
      declaration: { id: 'S', kind: 'scatter', row: 'wafer', encode }, kinds: { scatter: M.scatter.kind } }).slotList().map((s) => `${s.key}${s.folds ? '*' : ''}`)),
  };
}

/** A scatter with Marker by lot and the Marked table limited by its pick, seated alone from M: a marker pressed - the
 *  lot node marked. */
async function markerPress(M) {
  const doc = makeDoc('dark');
  const markings = new MarkingStore();
  const hubs = new HubBook();
  const handlers = {};
  const stubCharts = { init: () => ({ setOption() {}, dispatchAction() {}, on(name, fn) { handlers[name] = fn; }, getZr() { return { on() {} }; }, resize() {}, dispose() {} }) };
  const lot = (id) => ({ id, type: 'lot', label: id, keys: { lot: id }, attributes: {} });
  const answer = { nodes: [wafer('W1'), wafer('W2'), wafer('W3'), wafer('W4'), lot('L1'), lot('L2'), ANSWER.nodes[4]],
    edges: [...ANSWER.edges, { source: 'W4', target: 'QT', predicate: 'measures', qualifiers: { value: '40' } },
      ...[['W1', 'L1'], ['W2', 'L2'], ['W3', 'L1'], ['W4', 'L2']].map(([w, l]) => ({ source: w, target: l, predicate: 'in_lot', qualifiers: {} }))],
    truncated: ANSWER.truncated };
  const seat = (decl, kinds) => {
    const part = new M.visual.VisualPart(doc.createElement('div'), { doc, markings, writes: decl.writes, start: decl.start, declaration: decl, kinds,
      filters: new KeyedStore(), stats: new KeyedStore(), active: new KeyedStore(), hubs, names: new Map(), charts: stubCharts,
      fetchWalk: async () => ({ ok: true, body: JSON.parse(JSON.stringify(answer)) }) });
    part.mount();
    return part;
  };
  const base = { part: 'visual', row: 'wafer', start: { marking: null }, system: null, filter: [], writes: 'marking:pick' };
  const scatter = seat({ ...base, id: 'S', kind: 'scatter', encode: { x: { ...TEMP, reduce: 'Avg' }, y: { ...TEMP, reduce: 'Max' }, marker1: LOT } }, { scatter: M.scatter.kind });
  const table = seat({ ...base, id: 'T', kind: 'table', limit: { markings: ['marking:pick'], must: 'all', none: 'empty' }, encode: { col1: NAME } }, { table: M.table.kind });
  await settle();
  const points = scatter.model.points.map((p) => [p.label, p.x, p.y]);
  handlers.click({ data: { id: hubId('wafer', [['lot', 'L1']]) }, event: { event: {} } });
  await settle();
  const said = (statusWords(table.stats.get('T')) || []).find((w) => w.includes('marked row')) || null;
  return { points, marked: markings.entries('marking:pick').map(([id]) => id), lines: table.model.lines.map((l) => l.id), said };
}

// ── the walk screen's trend as one scatter declaration (owner 10-13 «트렌드 부품은 산점도로 대체») ──
/** A trend's points (walk/trend.js rowsPoints) and the scatter's - X the time of Y's reads, a point a value record - on one
 *  answer: [ms, value] each, sorted; and what a record pressed marks. */
async function trendAsScatter(M) {
  const at = (d) => `2026-01-0${d}T00:00:00Z`;
  const reads = [['W1', '30', 1], ['W1', '32', 2], ['W1', '31', 4], ['W2', '10', 3], ['W3', '12', 5]];
  const answer = { nodes: [wafer('W1'), wafer('W2'), wafer('W3'), ANSWER.nodes[4]],
    edges: reads.map(([w, v, d], i) => ({ id: `e${i}`, claim_id: `c${i}`, source: w, target: 'QT', predicate: 'measures', qualifiers: { value: v }, occurred_at: at(d) })),
    truncated: ANSWER.truncated };
  const index = M.reach.indexGraph(answer);
  const trend = M.trend.rowsPoints({ index, groups: [{ inside: M.visual.insideOf(answer) }] }, ['W1', 'W2', 'W3'], TEMP)
    .map((p) => [p.t, p.value]).sort((a, b) => a[0] - b[0]);
  const doc = makeDoc('dark');
  const markings = new MarkingStore();
  const handlers = {};
  const stubCharts = { init: () => ({ setOption() {}, dispatchAction() {}, on(name, fn) { handlers[name] = fn; }, getZr() { return { on() {} }; }, resize() {}, dispose() {} }) };
  const decl = { id: 'S', part: 'visual', kind: 'scatter', row: 'wafer', start: { marking: null }, system: null, filter: [], writes: 'marking:pick',
    markerBy: 'record', encode: { x: { ...TEMP, of: 'time' }, y: TEMP } };
  const part = new M.visual.VisualPart(doc.createElement('div'), { doc, markings, writes: decl.writes, start: decl.start, declaration: decl,
    kinds: { scatter: M.scatter.kind }, filters: new KeyedStore(), stats: new KeyedStore(), active: new KeyedStore(), hubs: new HubBook(), names: new Map(),
    charts: stubCharts, fetchWalk: async () => ({ ok: true, body: JSON.parse(JSON.stringify(answer)) }) });
  part.mount();
  await settle();
  const scatter = part.model.points.map((p) => [Date.parse(p.x), p.y]).sort((a, b) => a[0] - b[0]);
  const pill = walk(part.host).filter((n) => String(n.className).startsWith('sf-pill')).map((n) => n._text).find((w) => w.startsWith('('));
  const second = part.model.points.find((p) => p.y === '32');
  if (second) handlers.click({ data: { id: second.id }, event: { event: {} } });
  return { same: JSON.stringify(trend) === JSON.stringify(scatter), n: [trend.length, scatter.length], times: scatter.map(([t]) => new Date(t).toISOString().slice(0, 10)),
    xKind: part.model.xKind, pill, marked: markings.entries('marking:pick').map(([id]) => id) };
}

// ── the marking layer (owner 10-13 «마킹 전파를 미리 층으로», Spotfire's Relations) ──
// Bonding dies d1 (from c1 on CW1) and d2 (from c2 on CW2) on BW; CW3's die c3 not walked - its wafer has no in_container.
const node = (id, type) => ({ id, type, label: id, keys: {}, attributes: {} });
const LAYER_GRAPH = {
  nodes: [node('BW', 'wafer'), node('CW1', 'wafer'), node('CW2', 'wafer'), node('CW3', 'wafer'), node('d1', 'die'), node('d2', 'die'), node('c1', 'die'), node('c2', 'die'),
    { id: 'Q', type: 'quantity', label: 'temp', keys: {}, attributes: {} }],
  edges: [['d1', 'bonded_from', 'c1'], ['d2', 'bonded_from', 'c2'], ['d1', 'in_container', 'BW'], ['d2', 'in_container', 'BW'], ['c1', 'in_container', 'CW1'], ['c2', 'in_container', 'CW2']]
    .map(([source, predicate, target]) => ({ id: `${source}-${predicate}`, source, target, predicate, qualifiers: {} }))
    .concat(['BW', 'CW1', 'CW2', 'CW3'].map((w, i) => ({ id: `${w}-m`, source: w, target: 'Q', predicate: 'measures', qualifiers: { value: String(10 + i) }, occurred_at: `2026-01-0${i + 1}T00:00:00Z` }))),
  truncated: ANSWER.truncated,
};
const RELATIONS = [{ from: 'die', predicate: 'bonded_from', to: 'die', both: false }, { from: 'die', predicate: 'in_container', to: 'wafer', both: false }];

async function layered(M) {
  const markings = new MarkingStore();
  const hubs = new HubBook();
  const relations = new KeyedStore({ list: [] });
  const layers = new M.layer.MarkingLayers({ markings, hubs, graph: new M.layer.GraphBook(), relations });
  layers.graph.add(LAYER_GRAPH);
  const ids = LAYER_GRAPH.nodes.map((n) => n.id);
  const hub = hubs.put(hubId('die', [['core wafer', 'CW1']]), ['d1']);
  markings.replace('B', [[hub, SIGN.CASE]]);
  const ask = () => ids.map((id) => layers.marked('B', id));
  const none = ask();
  const same = ids.every((id) => (layers.marked('B', id) === true) === holds(markings.entries('B'), hubs, id));
  relations.set('list', RELATIONS);
  const spread = ask();
  // asked again and again, one marking change - one more computation
  const before = layers.computed;
  ask();
  ask();
  const unchanged = layers.computed - before;
  markings.replace('B', [['d2', SIGN.CASE]]);
  ask();
  ask();
  const changed = layers.computed - before;
  const moved = ids.filter((id) => layers.marked('B', id) === true);
  return { none, same, spread, unchanged, changed, moved };
}

/** D in little: a scatter of wafers coloured by If(Marked("Core wafer"), "B", "other") on a page's layers, seated alone. */
async function markedColour(M, withRelations) {
  const doc = makeDoc('dark');
  const markings = new MarkingStore();
  const hubs = new HubBook();
  const relations = new KeyedStore({ list: withRelations ? RELATIONS : [] });
  const layers = new M.layer.MarkingLayers({ markings, hubs, graph: new M.layer.GraphBook(), relations });
  layers.graph.add(LAYER_GRAPH);
  const stats = new KeyedStore();
  const markingList = new KeyedStore({ list: [{ name: 'marking:core', label: 'Core wafer', color: '#00A650' }, { name: 'marking:pick', label: 'Pick', color: '#00A650' }] });
  markings.replace('marking:core', [[hubs.put(hubId('die', [['core wafer', 'CW1']]), ['d1']), SIGN.CASE]]);
  const decl = { id: 'D', part: 'visual', kind: 'scatter', row: 'wafer', start: { marking: null }, system: null, filter: [], writes: 'marking:pick', markerBy: 'record',
    encode: { x: { ...TEMP, of: 'time' }, y: TEMP, color: { expr: 'If(Marked("Core wafer"), "B", "other")' } } };
  const part = new M.visual.VisualPart(doc.createElement('div'), { doc, markings, writes: decl.writes, start: decl.start, declaration: decl, layers, relations, markingList,
    kinds: { scatter: M.scatter.kind }, filters: new KeyedStore(), stats, active: new KeyedStore(), hubs, names: new Map(), charts: charts(),
    fetchWalk: async () => ({ ok: true, body: JSON.parse(JSON.stringify(LAYER_GRAPH)) }) });
  part.mount();
  await settle();
  const colours = () => Object.fromEntries(part.model.points.map((p) => [p.label, part.colors.of.get(p.ids[0]).category]));
  const first = { colours: colours(), unknown: stats.get('D').unknown };
  // the core wafer marking moved to CW2's die: D folds again (it asked that marking) - CW2 now
  markings.replace('marking:core', [['d2', SIGN.CASE]]);
  await settle();
  return { ...first, moved: colours() };
}

/** The map kind seated alone: two wafers' dies at one coordinate - one cell; pressed, both marked. */
async function mapPress(M) {
  const doc = makeDoc('dark');
  const markings = new MarkingStore();
  const die = (id, x, y) => ({ id, type: 'die', label: id, keys: { x: String(x), y: String(y) }, attributes: {} });
  const answer = { nodes: [die('a1', 0, 0), die('b1', 0, 0), die('a2', 1, 0), die('a3', 0, 2)], edges: [], truncated: ANSWER.truncated };
  const decl = { id: 'A', part: 'visual', kind: 'map', row: 'die', start: { marking: null }, system: null, filter: [], writes: 'marking:pick',
    encode: { x: { steps: [], value: { on: 'key', name: 'x' }, words: ['x'] }, y: { steps: [], value: { on: 'key', name: 'y' }, words: ['y'] } } };
  const hubs = new HubBook();
  const part = new M.visual.VisualPart(doc.createElement('div'), { doc, markings, writes: decl.writes, start: decl.start, declaration: decl,
    kinds: { map: M.map.kind }, filters: new KeyedStore(), stats: new KeyedStore(), active: new KeyedStore(), hubs, names: new Map(), charts: charts(),
    fetchWalk: async () => ({ ok: true, body: JSON.parse(JSON.stringify(answer)) }) });
  part.mount();
  await settle();
  const cells = part.model.cells.map((c) => [c.x, c.y, c.ids]);
  walk(part.host).find((n) => n.attrs && n.attrs['data-cell'] === '0,0').dispatch('click', { stopPropagation() {} });
  await settle();
  const marked = markings.entries('marking:pick').flatMap(([id]) => hubs.open(id)).sort();
  return { cells, marked, drawnMarked: part.model.cells.filter((c) => c.marked).map((c) => `${c.x},${c.y}`) };
}

/** A value record a point (owner 10-13 «선 하나에 기록 넷이면 점 넷»): W1's measure edge with three records, W2's with one -
 *  no reduce: a point a record; Latest on X and Y: a point an edge, its newest record. */
async function recordPoints(M) {
  const rec = (value, d) => ({ occurred_at: `2026-02-0${d}T00:00:00Z`, qualifiers: { value } });
  const answer = { nodes: [wafer('W1'), wafer('W2'), ANSWER.nodes[4]],
    edges: [{ id: 'e1', source: 'W1', target: 'QT', predicate: 'measures', qualifiers: { value: '3' }, occurred_at: '2026-02-03T00:00:00Z', records: [rec('3', 3), rec('2', 2), rec('1', 1)] },
      { id: 'e2', source: 'W2', target: 'QT', predicate: 'measures', qualifiers: { value: '9' }, occurred_at: '2026-02-05T00:00:00Z', records: [rec('9', 5)] }],
    truncated: ANSWER.truncated };
  const seatWith = async (encode) => {
    const doc = makeDoc('dark');
    const decl = { id: 'S', part: 'visual', kind: 'scatter', row: 'wafer', start: { marking: null }, system: null, filter: [], writes: 'marking:pick', markerBy: 'record', encode };
    const part = new M.visual.VisualPart(doc.createElement('div'), { doc, markings: new MarkingStore(), writes: decl.writes, start: decl.start, declaration: decl,
      kinds: { scatter: M.scatter.kind }, filters: new KeyedStore(), stats: new KeyedStore(), active: new KeyedStore(), hubs: new HubBook(), names: new Map(), charts: charts(),
      fetchWalk: async () => ({ ok: true, body: JSON.parse(JSON.stringify(answer)) }) });
    part.mount();
    await settle();
    return part.model.points.map((p) => [p.label, String(p.x).slice(0, 10), p.y]).sort();
  };
  return { all: await seatWith({ x: { ...TEMP, of: 'time' }, y: TEMP }),
    latest: await seatWith({ x: { ...TEMP, of: 'time', reduce: 'Latest' }, y: { ...TEMP, reduce: 'Latest' } }) };
}

/** The marking walk (owner 10-14 «마킹 걷기는 아까대로»): a bonding die d1 of BW (its sibling d2), bonded from c1 on CW1
 *  (d2 from c2 on CW2). The stub walks as the server does - from the seeds along `follow` (none - every predicate) both
 *  ways, `hops` steps, carrying the `collect` types, every edge it took. */
async function routed(M) {
  const { entitySeedId } = await import('../src/rnd_board/api.js');
  const id = (type, key) => entitySeedId(type, { [type]: key });
  const [BW, CW1, CW2, d1, d2, c1, c2] = [['wafer', 'BW'], ['wafer', 'CW1'], ['wafer', 'CW2'], ['die', 'd1'], ['die', 'd2'], ['die', 'c1'], ['die', 'c2']].map(([t, k]) => id(t, k));
  const label = new Map([[BW, 'BW'], [CW1, 'CW1'], [CW2, 'CW2'], [d1, 'd1'], [d2, 'd2'], [c1, 'c1'], [c2, 'c2']]);
  const node = (nid) => ({ id: nid, type: M.route.typeOfStart(nid), label: label.get(nid), keys: {}, attributes: {} });
  const EDGES = [[d1, 'in_container', BW], [d2, 'in_container', BW], [d1, 'bonded_from', c1], [d2, 'bonded_from', c2], [c1, 'in_container', CW1], [c2, 'in_container', CW2]]
    .map(([source, predicate, target], i) => ({ id: `r${i}`, source, target, predicate, qualifiers: {} }));
  const JUDGED = { [CW1]: { [d1]: 'found', [d2]: 'none' }, [CW2]: { [d2]: 'found' } };
  const serve = (p) => {
    if (p.seed_type) return { nodes: [...label.keys()].filter((x) => M.route.typeOfStart(x) === p.seed_type).map(node), edges: [], truncated: ANSWER.truncated };
    const follow = p.follow && p.follow.length ? new Set(p.follow) : null;
    let at = new Set(p.positive || []);
    const seen = new Set(at);
    const took = new Set();
    for (let k = 0; k < (p.hops || 1); k += 1) {
      const next = new Set();
      for (const e of EDGES) {
        if (follow && !follow.has(e.predicate)) continue;
        for (const [a, b] of [[e.source, e.target], [e.target, e.source]]) if (at.has(a)) { took.add(e); if (!seen.has(b)) { seen.add(b); next.add(b); } }
      }
      at = next;
    }
    const collect = p.collect && p.collect.length ? new Set(p.collect) : null;
    // aux (Reach): each node judged against the one node asked - the server's found · none · unknown, a table here
    const judge = (n) => (p.aux && p.aux.length ? { ...n, aux: { state: (JUDGED[p.aux[0]] || {})[n.id] || 'unknown' } } : n);
    return { nodes: [...seen].map(node).filter((n) => !collect || collect.has(n.type)).map(judge), edges: [...took], truncated: ANSWER.truncated };
  };
  const vocabulary = { entities: [{ type: 'die', keys: ['die'] }, { type: 'wafer', keys: ['wafer'] }],
    predicates: [{ name: 'in_container', subjects: ['die'], object: { kind: 'entity_ref', types: ['wafer'] } }, { name: 'bonded_from', subjects: ['die'], object: { kind: 'entity_ref', types: ['die'] } }] };
  const CORE = { steps: [{ predicate: 'bonded_from', direction: 'outgoing' }, { predicate: 'in_container', direction: 'outgoing' }], value: { on: 'label', name: 'name' }, words: ['core wafer'] };
  const NAMED = { steps: [], value: { on: 'label', name: 'name' }, words: ['name'] };
  const KINDS = { crossTable: M.cross.kind, table: M.table.kind };
  // a page: its markings, its hubs, its graph and relations (a part seated on it shares them)
  const page = (relations = []) => {
    const markings = new MarkingStore();
    const hubs = new HubBook();
    const rel = new KeyedStore({ list: relations });
    return { markings, hubs, relations: rel, layers: new M.layer.MarkingLayers({ markings, hubs, relations: rel }) };
  };
  const seat = async (decl, on = page(), withVocabulary = true) => {
    const doc = makeDoc('dark');
    const asked = [];
    const part = new M.visual.VisualPart(doc.createElement('div'), { doc, markings: on.markings, hubs: on.hubs, layers: on.layers, relations: on.relations,
      writes: decl.writes || null, start: decl.start, declaration: decl, vocabulary: withVocabulary ? () => vocabulary : undefined,
      kinds: KINDS, filters: new KeyedStore(), stats: new KeyedStore(), active: new KeyedStore(), names: new Map(), charts: charts(),
      fetchWalk: async (params) => { asked.push([params.follow || null, params.hops ?? null, (params.positive || []).map((x) => label.get(x))]); return { ok: true, body: serve(params) }; } });
    part.mount();
    await settle();
    return { state: part.state, refusal: part.refusal || null, rows: part.model ? part.model.rowKeys : null, asked, part,
      labels: () => part.rowsOf().map((x) => label.get(x)).sort() };
  };
  const base = { id: 'B', part: 'visual', kind: 'crossTable', start: { marking: 'marking:die' }, system: null, filter: [] };
  const withD1 = (relations) => { const p = page(relations); p.markings.set('marking:die', d1, SIGN.CASE); return p; };
  // W1 a start of the row type is its own row: d1 alone (its record walked, no row reached through it), its core wafer
  const dies = await seat({ ...base, row: 'die', encode: { rows: CORE } }, withD1());
  // W2 All: every die of the type
  const all = await seat({ ...base, start: { marking: null }, row: 'die', encode: { rows: CORE } }, withD1());
  // W3 die to wafer: every route's predicates together - its own wafer and its core wafer, the longest route's steps
  const wafers = await seat({ ...base, row: 'wafer', encode: {} }, withD1());
  // W4 the start's spread layer, of two types together: d1 marked, the relation die -in_container-> wafer on the page -
  // the start d1 and BW; rows of die: d1 itself and the dies BW holds
  const spreadPage = withD1([{ from: 'die', predicate: 'in_container', to: 'wafer', both: false }]);
  spreadPage.layers.graph.add({ nodes: [node(d1), node(BW)], edges: [EDGES[0]] });
  const spread = await seat({ ...base, row: 'die', encode: {} }, spreadPage);
  // W5 no route from the start's type to the rows: said, nothing walked
  const none = await seat({ ...base, row: 'lot', encode: {} }, withD1());
  // W6 a press (hubs.js nodesOfPress): a cell of one row - that row's node (d1, not the core wafer it reads); a cell of
  // several - the hub of its rows; a row of a part whose rows are wafers - that wafer (narrowing)
  const held = (on) => on.markings.entries('marking:core').map(([x]) => (isHubId(x) ? 'hub' : label.get(x)));
  const onePage = withD1();
  const one = await seat({ ...base, row: 'die', writes: 'marking:core', encode: { rows: CORE } }, onePage);
  one.part.markHub([['core wafer', one.part.model.rowKeys[0]]], one.part.model.rowIds[0], {});
  await settle();
  const press = [held(onePage), one.part.model.grid[0][0].marked];
  const shows = await seat({ ...base, id: 'S', row: 'wafer', writes: 'marking:core', start: { marking: 'marking:die' }, encode: {} }, onePage);
  press.push((statusWords(shows.part.stats.get('S')) || []).find((w) => w.includes('marked row')) || null);
  const manyPage = page();
  manyPage.markings.set('marking:die', BW, SIGN.CASE);
  const many = await seat({ ...base, row: 'die', writes: 'marking:core', encode: {} }, manyPage);
  many.part.markHub([], many.part.model.grid[0][0].ids, {});
  await settle();
  press.push(held(manyPage));
  const narrow = await seat({ ...base, row: 'wafer', writes: 'marking:core', encode: { rows: NAMED } }, withD1());
  const cw1 = narrow.part.model.rowKeys.indexOf('CW1');
  narrow.part.markHub([['name', 'CW1']], narrow.part.model.rowIds[cw1], {});
  await settle();
  press.push(narrow.part.markings.entries('marking:core').map(([x]) => label.get(x) || 'hub'));
  // W9 a part that writes a marking walks the page's relations from its rows - the edges its marking spreads along
  const writerPage = withD1([{ from: 'die', predicate: 'bonded_from', to: 'die', both: false }]);
  const writer = await seat({ ...base, row: 'die', writes: 'marking:core', encode: {} }, writerPage);
  const reader = await seat({ ...base, id: 'R', row: 'die', start: { marking: 'marking:core' }, encode: {} }, writerPage);
  writer.part.markHub([], [d1], {});
  await settle();
  const relationWalk = [writer.asked.slice(1), (statusWords(writer.part.stats.get('B')) || []).filter((w) => w.startsWith('Relations')), reader.labels()];
  // W7 a pill of two columns, its inner one with steps: the walk carries its steps as the one-column pill's does
  const single = await seat({ ...base, row: 'die', encode: { rows: CORE } }, withD1());
  const pair = await seat({ ...base, row: 'die', encode: { rows: [NAMED, CORE] } }, withD1());
  const twoColumns = [pair.asked, single.asked, pair.rows, JSON.stringify(M.walks.valueAsk([NAMED, CORE], 'die', vocabulary)) === JSON.stringify(M.walks.valueAsk(CORE, 'die', vocabulary))];
  // R1 Reach(node) in a column: the row walk asks the server to judge its rows against that node (aux) - found true, none
  // false, unknown empty and counted on the status line; R2 two nodes Reached - a row walk each; R3 a column that
  // Reaches a node added - the rows walked again with it, the same node again none
  const wafersPage = page();
  wafersPage.markings.set('marking:die', BW, SIGN.CASE);
  const reachCol = (text) => ({ expr: text, words: [text] });
  const reachTable = await seat({ ...base, kind: 'table', row: 'die', encode: { col1: NAMED, col2: reachCol('Reach(wafer("CW1"))'), col3: reachCol('Reach(wafer("CW2"))') } }, wafersPage);
  const lines = reachTable.part.model.lines.map((l) => l.cells.map((c) => c.text)).sort();
  const auxSent = reachTable.part.layers.graph.walks.map((w) => (w.ask.aux || []).map((x) => label.get(x)).join()).sort();
  const reach = [lines, (statusWords(reachTable.part.stats.get('B')) || []).filter((w) => w.includes('unknown')), auxSent];
  const twoPage = page();
  twoPage.markings.set('marking:die', BW, SIGN.CASE);
  const two = await seat({ ...base, kind: 'table', row: 'die', encode: { col1: reachCol('Reach(wafer("CW1")) or Reach(wafer("CW2"))') } }, twoPage);
  reach.push(two.part.layers.graph.walks.map((w) => (w.ask.aux || []).map((x) => label.get(x)).join()).sort());
  const addPage = page();
  addPage.markings.set('marking:die', BW, SIGN.CASE);
  const added = await seat({ ...base, kind: 'table', row: 'die', encode: { col1: NAMED } }, addPage);
  const n0 = added.asked.length;
  added.part.setDeclaration({ ...added.part.declaration(), encode: { col1: NAMED, col2: reachCol('Reach(wafer("CW1"))') } });
  await settle();
  const n1 = added.asked.length;
  added.part.setDeclaration({ ...added.part.declaration(), encode: { col1: NAMED, col2: reachCol('Reach(wafer("CW1"))'), col3: NAMED } });
  await settle();
  reach.push([n1 - n0, added.asked.length - n1, added.part.model.lines.map((l) => l.cells[1].text).sort(),
    M.walks.covers({ seeds: ['a'], follow: [], hops: 1, collect: null, complete: true }, { seeds: ['a'], follow: [], hops: 1, collect: ['die'], aux: ['X'] })]);
  return { reach, twoColumns, press, relationWalk, pure: [M.hubs.nodesOfPress(['a']), M.hubs.nodesOfPress(['a', 'b'])],
    dies: [dies.rows, dies.asked, dies.labels()], all: [all.rows, all.labels()], wafers: [wafers.labels(), wafers.asked],
    spread: [spread.part.startTypes(), spread.labels(), spread.asked], none: [none.state, none.refusal, none.asked.length] };
}

/** A part's walks (owner 10-14 «행 걷기 + 값 걷기», part_walks.js): a row walk from the start to its end, a value walk a
 *  slot from the rows; a slot changed walks that slot alone; a walk in hand that covers it not asked again; a walk in
 *  flight dropped by the next of its kind; the rows a value walk starts from by the seed cap; the answer read by its
 *  edges (core dies: a die reads its own core wafer, not one an undirected evidence would give it). */
async function partWalks(M) {
  const { entitySeedId } = await import('../src/rnd_board/api.js');
  const id = (type, key) => entitySeedId(type, { [type]: key });
  const [BW, CW1, CW2, d1, d2, d3, c1, c2, Q, S1, T1, X1] = [['wafer', 'BW'], ['wafer', 'CW1'], ['wafer', 'CW2'], ['die', 'd1'], ['die', 'd2'], ['die', 'd3'],
    ['die', 'c1'], ['die', 'c2'], ['quantity', 'temp'], ['step', 's1'], ['tool', 't1'], ['xray', 'x1']].map(([t, k]) => id(t, k));
  const label = new Map([[BW, 'BW'], [CW1, 'CW1'], [CW2, 'CW2'], [d1, 'd1'], [d2, 'd2'], [d3, 'd3'], [c1, 'c1'], [c2, 'c2'], [Q, 'temp'], [S1, 's1'], [T1, 't1'], [X1, 'x1']]);
  const node = (nid, attributes = {}) => ({ id: nid, type: M.route.typeOfStart(nid), label: label.get(nid), keys: {}, attributes });
  const edge = (source, predicate, target, qualifiers = {}) => ({ id: `${source}|${predicate}|${target}`, source, target, predicate, qualifiers });
  const OK = { nodes: false, edges: false, depth: false, claims: false, actions: false, reason: null };
  const vocabulary = { entities: ['die', 'wafer', 'quantity', 'step', 'tool', 'xray'].map((type) => ({ type })),
    predicates: [['in_container', 'wafer'], ['bonded_from', 'die'], ['measures', 'quantity'], ['at_step', 'step'], ['at_tool', 'tool'], ['xrayed', 'xray']]
      .map(([name, type]) => ({ name, subjects: ['die'], object: { kind: 'entity_ref', types: [type] } })) };
  const way = (predicate, value, words) => ({ steps: [{ predicate, direction: 'outgoing' }], value, words: [words] });
  const TEMP_V = way('measures', { on: 'edge', name: 'value' }, 'temp');
  const TEMP_NAME = way('measures', { on: 'label', name: 'name' }, 'temp name');
  const STEP = way('at_step', { on: 'label', name: 'name' }, 'step');
  const TOOL = way('at_tool', { on: 'label', name: 'name' }, 'tool');
  const XRAY = way('xrayed', { on: 'label', name: 'name' }, 'xray');
  const XRAY_ATTR = way('xrayed', { on: 'node', name: 'grade' }, 'xray grade');
  const CORE = { steps: [{ predicate: 'bonded_from', direction: 'outgoing' }, { predicate: 'in_container', direction: 'outgoing' }], value: { on: 'label', name: 'name' }, words: ['core wafer'] };
  const DIES = [d1, d2, d3];
  // the answers by what is asked: the row walk two pages; a value walk the types it carries and every edge it walked
  const byFollow = {
    in_container: (p) => (p.resume === 'r2' ? { nodes: [node(d3)], edges: [edge(d3, 'in_container', BW)], truncated: OK }
      : { nodes: [node(BW), node(d1), node(d2)], edges: [edge(d1, 'in_container', BW), edge(d2, 'in_container', BW)], truncated: OK, more: { resume: 'r2' } }),
    bonded_from: () => ({ nodes: [node(BW), node(CW1), node(CW2)], truncated: OK,
      edges: [edge(d1, 'bonded_from', c1), edge(d2, 'bonded_from', c2), edge(c1, 'in_container', CW1), edge(c2, 'in_container', CW2), ...DIES.map((d) => edge(d, 'in_container', BW))] }),
    measures: () => ({ nodes: [node(Q)], edges: DIES.map((d, i) => edge(d, 'measures', Q, { value: String(i + 1) })), truncated: OK }),
    at_step: () => ({ nodes: [node(S1)], edges: DIES.map((d) => edge(d, 'at_step', S1)), truncated: OK }),
    at_tool: () => ({ nodes: [node(T1)], edges: DIES.map((d) => edge(d, 'at_tool', T1)), truncated: OK }),
    // cut: an axis true and no next page
    xrayed: () => ({ nodes: [node(X1, { grade: 'A' })], edges: [edge(d1, 'xrayed', X1)], truncated: { ...OK, nodes: true } }),
  };
  const seat = async (decl, { seedChunk, hold, page } = {}) => {
    const doc = makeDoc('dark');
    const markings = page ? page.markings : new MarkingStore();
    markings.set('marking:start', BW, SIGN.CASE);
    const asked = [];
    const part = new M.visual.VisualPart(doc.createElement('div'), { doc, markings, start: decl.start, declaration: decl, vocabulary: () => vocabulary, seedChunk,
      ...(page ? { layers: page.layers } : {}),
      kinds: { table: M.table.kind, scatter: M.scatter.kind, crossTable: M.cross.kind, map: M.map.kind }, filters: new KeyedStore(), stats: new KeyedStore(), active: new KeyedStore(),
      hubs: new HubBook(), names: new Map(), charts: charts(),
      fetchWalk: async (params) => {
        asked.push(params);
        const answer = (byFollow[(params.follow || []).find((f) => byFollow[f])] || (() => ({ nodes: [], edges: [], truncated: OK })))(params);
        if (hold && hold.when(params)) return new Promise((resolve) => hold.release.push(() => resolve({ ok: true, body: { ...answer, nodes: [...answer.nodes, node('LATE')] } })));
        return { ok: true, body: answer };
      } });
    part.mount();
    await settle();
    return { part, asked, words: () => statusWords(part.stats.get('P')) };
  };
  const base = { id: 'P', part: 'visual', kind: 'table', row: 'die', start: { marking: 'marking:start' }, system: null, filter: [] };
  const brief = (p) => [(p.follow || []).join('+'), (p.positive || []).map((x) => label.get(x)), p.resume || null];
  const out = {};

  // PW1 the row walk to its end: two pages, the second asked with the first's resume; its rows every die; then one
  // value walk for the column (one step: measures)
  const one = await seat({ ...base, encode: { col1: TEMP_V } });
  out.resume = [one.asked.map(brief), one.part.rowsOf().map((x) => label.get(x)).sort(),
    one.part.model.lines.map((l) => l.cells[0].text)];
  // the pure loop: a page with a resume asks the next; an expired resume (410) is said with its reason, the walk cut
  const pages = [];
  const two = await M.walks.walkToEnd(async (p) => { pages.push(p.resume || null); return p.resume ? { ok: false, status: 410, detail: { detail: { reason: 'resume expired' } } }
    : { ok: true, body: { nodes: [], edges: [], truncated: OK, more: { resume: 'k1' } } }; }, {}, null);
  out.expired = [pages, two.complete, two.why, two.answers.length];

  // PW2 the one judgment (part_walks.js covers): a column taken off - covered; another attribute of a type walked - the
  // same ask, covered; a new type - not (a new way, or a type the same way did not carry); a cut walk - not; other rows, a predicate more, a step more - not
  const held = { seeds: ['a', 'b'], follow: ['at_step', 'measures'], hops: 1, collect: ['quantity', 'step'], complete: true };
  const ask = (patch) => ({ seeds: ['b', 'a'], follow: ['measures'], hops: 1, collect: ['quantity'], ...patch });
  out.covers = [M.walks.covers(held, ask({})), M.walks.covers(held, ask({ collect: ['quantity'] })), M.walks.covers(held, ask({ collect: ['tool'], follow: ['at_tool'] })), M.walks.covers(held, ask({ collect: ['wafer'] })),
    M.walks.covers({ ...held, complete: false }, ask({})), M.walks.covers(held, ask({ seeds: ['a'] })), M.walks.covers(held, ask({ follow: ['measures', 'xrayed'] })),
    M.walks.covers(held, ask({ hops: 2 })), M.walks.covers({ ...held, collect: null }, ask({ collect: ['tool'] }))];

  // PW3 the cache in a part: a slot of two columns walked; a column taken off - no request, said cached; another
  // attribute of the type walked - none; a new type - one; a cut walk does not cover - its slot asked again
  const cache = await seat({ ...base, encode: { col1: [TEMP_V, STEP] } });
  const n0 = cache.asked.length;
  const set = async (encode) => { const before = cache.asked.length; cache.part.setDeclaration({ ...cache.part.declaration(), encode }); await settle(); return cache.asked.length - before; };
  const said = (w) => cache.words().filter((x) => x.startsWith('Column')).join(' / ');
  const first = said();
  out.cache = [n0, first, cache.words().find((x) => x.startsWith('Rows')) || null,
    await set({ col1: [TEMP_V] }), said(), await set({ col1: [TEMP_NAME] }), await set({ col1: [TOOL] }), said(),
    await set({ col1: [TOOL], col2: XRAY }), said(), await set({ col1: [TOOL], col2: XRAY_ATTR })];

  // PW4 a slot changed walks that slot alone - every slot of every kind (one function): a new way on it, one request,
  // asking that way
  const oneSlot = async (kindName) => {
    const s = await seat({ ...base, kind: kindName, encode: {} });
    const keys = s.part.slotList().map((x) => x.key);
    const got = [];
    for (const key of keys) {
      const before = s.asked.length;
      const pred = `p_${key}`;
      s.part.setDeclaration({ ...s.part.declaration(), encode: { ...s.part.declaration().encode, [key]: way(pred, { on: 'label', name: 'name' }, pred) } });
      await settle();
      got.push([key, s.asked.length - before, s.asked.slice(before).map((p) => (p.follow || []).join('+'))]);
    }
    return { keys: keys.length, wrong: got.filter(([key, n, follows]) => n !== 1 || follows[0] !== `p_${key}`) };
  };
  out.everySlot = await Promise.all(['table', 'scatter', 'crossTable', 'map'].map(async (k) => [k, await oneSlot(k)]));

  // PW5 the rows a value walk starts from by the seed cap: three rows, a cap of two - two requests
  const chunked = await seat({ ...base, encode: { col1: TEMP_V } }, { seedChunk: 2 });
  out.chunks = [chunked.asked.filter((p) => (p.follow || []).includes('measures')).map((p) => (p.positive || []).map((x) => label.get(x))),
    chunked.part.model.lines.map((l) => l.cells[0].text)];

  // PW6 a walk in flight dropped by the next for its slot: its request's signal aborted, its late answer not drawn
  const hold = { when: (p) => (p.follow || []).includes('at_step'), release: [] };
  const held2 = await seat({ ...base, encode: { col1: TEMP_V } }, { hold });
  held2.part.setDeclaration({ ...held2.part.declaration(), encode: { col1: STEP } });
  await settle();
  const inFlight = held2.asked[held2.asked.length - 1];
  held2.part.setDeclaration({ ...held2.part.declaration(), encode: { col1: TOOL } });
  await settle();
  for (const r of hold.release) r();
  await settle();
  out.abort = [Boolean(inFlight.signal && inFlight.signal.aborted), held2.part.answer.nodes.some((n) => n.id === 'LATE'), held2.part.model.lines.map((l) => l.cells[0].text)];

  // PW8 two slots of different ways walk at once - both asked before either is answered
  const both = { when: (p) => ['measures', 'at_step'].some((f) => (p.follow || []).includes(f)), release: [] };
  const pair = await seat({ ...base, encode: { col1: TEMP_V, col2: STEP } }, { hold: both });
  const atOnce = both.release.length;
  for (const r of both.release) r();
  await settle();
  out.together = [atOnce, pair.part.model.lines.map((l) => l.cells.map((c) => c.text))[0]];

  // PW9 a start of the row type whose nodes a walk on the page carried walks no rows - the value walk only; one written
  // by hand (none carried) is walked for its records. Every request asks no ranking (propagation=false)
  const ofDies = await seat({ ...base, start: { marking: 'marking:dies' }, encode: { col1: TEMP_V } });
  ofDies.part.markings.set('marking:dies', d1, SIGN.CASE);
  ofDies.part.markings.set('marking:dies', d2, SIGN.CASE);
  await settle();
  const handWritten = ofDies.asked.length;
  ofDies.part.layers.graph.add({ nodes: [node(d3)], edges: [] });
  ofDies.part.markings.replace('marking:dies', [[d3, SIGN.CASE]]);
  await settle();
  const carried = ofDies.asked.slice(handWritten).map((p) => (p.follow || []).join('+') || '(all)');
  out.startIsRow = [handWritten > 0, carried, ofDies.part.rowsOf().map((x) => label.get(x)), [...new Set([...one.asked, ...ofDies.asked].map((p) => p.propagation))]];

  // PW10 a value walk's runs by the seed cap asked together - both in flight before either is answered
  const runsHeld = { when: (p) => (p.follow || []).includes('measures'), release: [] };
  const runs = await seat({ ...base, encode: { col1: TEMP_V } }, { seedChunk: 2, hold: runsHeld });
  const inFlightRuns = runsHeld.release.length;
  for (const r of runsHeld.release) r();
  await settle();
  out.runsTogether = [inFlightRuns, runs.part.model.lines.map((l) => l.cells[0].text)];

  // PW11 the ranking left out only where asked: a walk that names no propagation (the walk box, rnd_board) sends none;
  // the part's walk sends propagation=false - its resumed page too
  const { fetchSubgraph } = M.api;
  const urls = [];
  const capture = async (url, init) => { urls.push([url, (init && init.method) || 'GET']); return { ok: true, status: 200, json: async () => ({ nodes: [], edges: [] }) }; };
  await fetchSubgraph({ apiBase: '', nodeId: 'n', fetchImpl: capture });
  await fetchSubgraph({ apiBase: '', nodeId: 'n', fetchImpl: capture, propagation: false, resumable: true });
  await fetchSubgraph({ apiBase: '', nodeId: 'n', fetchImpl: capture, propagation: false, resumable: true, resume: 'k' });
  out.ranking = urls.map(([u, m]) => [m, new URL(u, 'http://x').searchParams.get('propagation')]);

  // PW12 a value walk folds once when every run is in - three runs (a cap of one), not a fold a page
  const once = await seat({ ...base, encode: { col1: TEMP_V } }, { seedChunk: 1 });
  let folds = 0;
  const foldOf = once.part.refold.bind(once.part);
  once.part.refold = (...a) => { folds += 1; return foldOf(...a); };
  const asked0 = once.asked.length;
  once.part.setDeclaration({ ...once.part.declaration(), encode: { col1: STEP } });
  await settle();
  out.foldOnce = [once.asked.length - asked0, folds, once.part.model.lines.map((l) => l.cells[0].text)];

  // PW13 one row walk a page (lead-board-10c): two parts opened together asking the same row walk - one request, the
  // second waits for the first in flight; a third opened after takes the page's walk in hand
  const shared = new MarkingStore();
  const page = { markings: shared, layers: new M.layer.MarkingLayers({ markings: shared, hubs: new HubBook() }) };
  const rowWalks = (s) => s.asked.filter((p) => (p.follow || []).includes('in_container')).length;
  const together = await Promise.all([seat({ ...base, id: 'P1', encode: { col1: TEMP_V } }, { page }), seat({ ...base, id: 'P2', kind: 'map', encode: {} }, { page })]);
  const third = await seat({ ...base, id: 'P3', encode: { col1: STEP } }, { page });
  out.onePage = [together.map(rowWalks), rowWalks(third), [...together, third].map((s) => s.part.rowsOf().length)];

  // PW7 core dies (lead 10-14, 18766): the value walk carries wafers only, its edges every way it walked - each die reads
  // its own core wafer through its edges (a die it did not carry stands by its id), never its own wafer BW
  const core = await seat({ ...base, kind: 'crossTable', encode: { rows: CORE } });
  const read = M.walks.readable([byFollow.bonded_from()]);
  out.core = [core.part.model.rowKeys, core.part.model.grid.map((r) => r[0].ids.map((x) => label.get(x)).sort()),
    read.nodes.filter((n) => n.carried === false).map((n) => label.get(n.id)).sort()];
  return out;
}

/** Color by the root's (owner 10-13 «모든 근원부품이 공유»): the same Color by on a scatter, a table, a cross table and a map
 *  - die D1 (p = A) one colour in all four; A's colour declared - all four draw it. */
async function colourEverywhere(M) {
  const die = (id, x, y, p) => ({ id, type: 'die', label: id, keys: { x: String(x), y: String(y), p }, attributes: {} });
  const answer = { nodes: [die('D1', 0, 0, 'A'), die('D2', 1, 0, 'B'), die('D3', 2, 1, 'A')], edges: [], truncated: ANSWER.truncated };
  const key = (name) => ({ steps: [], value: { on: 'key', name }, words: [name] });
  const encodes = { scatter: { x: key('x'), y: key('y') }, table: { col1: NAME }, crossTable: { rows: key('x') }, map: { x: key('x'), y: key('y') }, sheet: {} };
  const kinds = { scatter: M.scatter.kind, table: M.table.kind, crossTable: (await import('../src/testbed/kinds/cross_table.js')).kind, map: M.map.kind, sheet: M.sheet.kind };
  const doc = makeDoc('dark');
  const pal = { bg: '#000000', one: ['#111111', '#222222'], cat: [['#6489FA', '#4B67BC'], ['#FA7864', '#BC5A4B']] };
  const parts = Object.keys(encodes).map((kind) => {
    const decl = { id: kind, part: 'visual', kind, row: 'die', start: { marking: null }, system: null, filter: [], writes: 'marking:pick', encode: { ...encodes[kind], color: key('p') },
      ...(kind === 'sheet' ? { key: 'A1' } : {}) };
    const part = new M.visual.VisualPart(doc.createElement('div'), { doc, markings: new MarkingStore(), writes: decl.writes, start: decl.start, declaration: decl, palette: () => pal,
      kinds, filters: new KeyedStore(), stats: new KeyedStore(), active: new KeyedStore(), hubs: new HubBook(), names: new Map(), charts: charts(),
      fetchWalk: async () => ({ ok: true, body: JSON.parse(JSON.stringify(answer)) }) });
    part.mount();
    return part;
  });
  await settle();
  // D1's colour as each kind drew it
  const drawn = () => parts.map((part) => {
    const k = part.decl.kind;
    if (k === 'scatter') return part.model.points.find((p) => p.id === 'D1').fill;
    if (k === 'table') return walk(part.host).find((n) => n.tagName === 'TR' && n.children.length > 0 && n.children[0]._text === 'D1').attrs['data-color'];
    if (k === 'crossTable') return walk(part.host).find((n) => n.tagName === 'TH' && n._text === '0').parentNode.children[1].style.background;
    // the sheet's key cell, its row D1 (the first the walk brought)
    if (k === 'sheet') return walk(part.host).find((n) => n.tagName === 'TD' && n.attrs && n.attrs['data-at'] === 'A1').attrs['data-color'];
    return walk(part.host).find((n) => n.attrs && n.attrs['data-cell'] === '0,0').attrs.fill;
  });
  const first = drawn();
  for (const part of parts) part.setDeclaration({ ...part.declaration(), colors: { A: '#123456' } });
  await settle();
  return { first: [new Set(first).size, first[0] === M.color.colorsOf([{ id: 'D1', reads: { color: { state: 'one', value: 'A' } } }], { palette: pal, declaration: { encode: { color: key('p') } } }).categories[0].fill], declared: drawn() };
}

/** The sheet on the root (lead 10-14 ㄱ): a start written as one node, its cells the root's slots naming each other. */
async function sheetRoot(M) {
  const { entitySeedId } = await import('../src/rnd_board/api.js');
  const KEY = entitySeedId('lot_slot', { lot: 'L1', slot: '05' });
  const q = (id) => ({ id, type: 'quantity', label: id, keys: { quantity: id }, attributes: {} });
  const answerFor = (id) => ({ nodes: [{ id, type: 'lot_slot', label: id === KEY ? 'L1 · 05' : 'L2 · 06', keys: {}, attributes: {} }, q('q1'), q('q2'), q('q3')],
    edges: [['q1', 1], ['q2', 2], ['q3', 3]].map(([t2, v], i) => ({ id: `m${i}`, source: id, target: t2, predicate: 'measures', qualifiers: { value: v } })), truncated: ANSWER.truncated });
  const vocabulary = { entities: [{ type: 'lot_slot', keys: ['lot', 'slot'] }, { type: 'quantity', keys: ['quantity'] }],
    predicates: [{ name: 'measures', subjects: ['lot_slot'], object: { kind: 'entity_ref', types: ['quantity'] } }] };
  const cells = { B1: { input: '=Avg([measures.value])' }, B2: { input: '=B1*2' }, B3: { input: '=Sum(C1:C2)' }, C1: { input: '4' }, C2: { input: '=B1' },
    D1: { input: '=D2' }, D2: { input: '=D1' }, E1: { input: '=A1' } };
  const seat = async (decl, kind = 'sheet') => {
    const doc = makeDoc('dark');
    const asked = [];
    const part = new M.visual.VisualPart(doc.createElement('div'), { doc, markings: new MarkingStore(), writes: decl.writes, start: decl.start, declaration: decl,
      vocabulary: () => vocabulary, kinds: { sheet: M.sheet.kind, scatter: M.scatter.kind }, filters: new KeyedStore(), stats: new KeyedStore(), active: new KeyedStore(),
      hubs: new HubBook(), names: new Map(), charts: charts(),
      fetchWalk: async (params) => { asked.push([params.follow || null, params.hops ?? null, params.nodeId]); return { ok: true, body: answerFor(params.nodeId) }; } });
    part.mount();
    await settle();
    void kind;
    return { part, asked };
  };
  const textOf = (part, at) => { const c = part.model && part.model.grid.flat().find((x) => x.at === at); return c ? c.text : null; };
  const base = { id: 'S', part: 'visual', kind: 'sheet', row: null, system: null, filter: [], writes: 'marking:pick', encode: {}, key: 'A1', cells };
  const one = await seat({ ...base, start: { node: 'lot_slot("L1", "05")' } });
  // Saved and reopened (the page's laidOut over a save, 18766 10-14): its row type left to its key, the same cells drawn.
  const saved = one.part.declaration();
  const reopened = M.main.laidOut(M.main.LAYOUT, { root: null, visuals: [saved] }, [{ type: 'quantity' }]).panels.find((p) => p.id === 'S');
  const back = await seat(reopened);
  const reopen = { row: reopened.row, cells: ['A1', 'B1', 'B3'].map((at) => textOf(back.part, at)) };
  const walked = { asked: one.asked.slice(), row: one.part.rowType(), cells: Object.fromEntries(['A1', 'B1', 'B2', 'B3', 'C1', 'C2', 'D1', 'E1'].map((at) => [at, textOf(one.part, at)])) };
  const ringCell = one.part.model.grid.flat().find((x) => x.at === 'D1');
  const other = await seat({ id: 'X', part: 'visual', kind: 'scatter', row: 'lot_slot', start: { node: 'lot_slot("L1", "05")' }, system: null, filter: [], writes: null,
    encode: { x: { expr: 'A1 + 1', words: ['A1 + 1'] }, y: { expr: '1', words: ['1'] } } });
  const xRead = (other.part.model && other.part.model.points) ? null : null;
  void xRead;
  const otherWhy = (() => { const r = M.slot.readSlot(other.part.index, other.part.inside, KEY, { expr: 'A1 + 1' }); return r.why || null; })();
  const walks = [one.asked.length];
  one.part.setDeclaration({ ...one.part.declaration(), start: { node: 'lot_slot("L2", "06")' } });
  await settle();
  walks.push(one.asked.length);
  one.part.setDeclaration({ ...one.part.declaration(), start: { node: 'lot_slot("L2", "06")' } });
  await settle();
  walks.push(one.asked.length);
  one.part.setDeclaration({ ...one.part.declaration(), start: { node: 'nope("x")' } });
  await settle();
  walks.push(one.asked.length);
  const keyCell = one.part.model ? one.part.model.grid.flat().find((x) => x.at === 'A1') : {};
  const again = { walks, seeds: one.asked.slice(2).map((a) => a[2]), refused: [keyCell.text, keyCell.why] };
  const none = await seat({ ...base, start: null });
  const empty = { state: none.part.state, walks: none.asked.length, cells: { C1: textOf(none.part, 'C1'), B1: textOf(none.part, 'B1') } };
  return { walked, ring: { why: ringCell.why, other: otherWhy }, again, empty, reopen };
}

/** A start read back from a save (QA 10-14: a reload showed «ledger-entity:v1:Wy…»): the basket names it by its id - its
 *  keys, as the picker named it when it was put in. */
async function keptStart(M) {
  const { entitySeedId } = await import('../src/rnd_board/api.js');
  const doc = makeDoc('dark');
  const markings = new MarkingStore();
  const id = entitySeedId('wafer', { wafer: 'SYN-BW-103-11' });
  markings.set('marking:start', id, SIGN.CASE);
  markings.set('marking:start', 'W1', SIGN.CASE);
  const b = new M.baskets.StartBaskets(doc.createElement('div'), { doc, markings, name: 'marking:start' });
  return walk(b.root).filter((n) => String(n.className) === 'wk-basketlabel').map((n) => n._text);
}

/** Category colours (QA 10-14): seven categories seven colours, in the order the rows show them, kept in the declaration;
 *  walked again with one more category seen first - the seven keep theirs. */
async function categoryColours(M) {
  const pal = { bg: '#000000', one: ['#111111', '#222222'], cat: ['#1', '#2', '#3', '#4', '#5', '#6', '#7'].map((c) => [c, c + 'L']) };
  const node = (id, p) => ({ id, type: 'die', label: id, keys: { x: '0', y: '0', p }, attributes: {} });
  let answer = { nodes: 'ABCDEFG'.split('').map((p, i) => node('D' + i, p)), edges: [], truncated: ANSWER.truncated };
  const doc = makeDoc('dark');
  const decl = { id: 'T', part: 'visual', kind: 'table', row: 'die', start: { marking: null }, system: null, filter: [], writes: 'marking:pick',
    encode: { col1: NAME, color: { steps: [], value: { on: 'key', name: 'p' }, words: ['p'] } } };
  const part = new M.visual.VisualPart(doc.createElement('div'), { doc, markings: new MarkingStore(), writes: decl.writes, start: decl.start, declaration: decl, palette: () => pal,
    kinds: { table: M.table.kind }, filters: new KeyedStore(), stats: new KeyedStore(), active: new KeyedStore(), hubs: new HubBook(), names: new Map(), charts: charts(),
    fetchWalk: async () => ({ ok: true, body: JSON.parse(JSON.stringify(answer)) }) });
  part.mount();
  await settle();
  const first = { ...part.declaration().colors };
  answer = { ...answer, nodes: [node('Z0', 'Z'), ...answer.nodes] };
  part.layers.graph.walks.length = 0;
  part.load();
  await settle();
  const after = part.declaration().colors || {};
  return { seven: new Set(Object.values(first)).size, order: 'ABCDEFG'.split('').map((p) => first[p]).join(''), kept: 'ABCDEFG'.split('').every((p) => after[p] === first[p]), z: Boolean(after.Z) };
}

/** Tooltip, labels, description (base set 10, 9, 1) - the root's: a scatter and a cross table on three dies. */
async function tipsAndLabels(M) {
  const die = (id, x, y, p) => ({ id, type: 'die', label: id, keys: { x: String(x), y: String(y), p }, attributes: {} });
  const answer = { nodes: [die('D1', 1, 2, 'A'), die('D2', 3, 4, 'B'), die('D3', 3, 5, 'A')], edges: [], truncated: ANSWER.truncated };
  const key = (name) => ({ steps: [], value: { on: 'key', name }, words: [name] });
  const doc = makeDoc('dark');
  const handlers = {};
  const stubCharts = { init: () => ({ setOption(o) { handlers.option = o; }, dispatchAction() {}, on(name, fn) { handlers[name] = fn; }, getZr() { return { on() {} }; }, resize() {}, dispose() {} }) };
  const markings = new MarkingStore();
  markings.set('marking:pick', 'D2', SIGN.CASE);
  const crossKind = (await import('../src/testbed/kinds/cross_table.js')).kind;
  const seat = (kind, encode, extra = {}) => {
    const decl = { id: kind, part: 'visual', kind, row: 'die', start: { marking: null }, system: null, filter: [], writes: 'marking:pick', encode, ...extra };
    const part = new M.visual.VisualPart(doc.createElement('div'), { doc, markings, writes: decl.writes, start: decl.start, declaration: decl,
      kinds: { scatter: M.scatter.kind, crossTable: crossKind }, filters: new KeyedStore(), stats: new KeyedStore(), active: new KeyedStore(), hubs: new HubBook(), names: new Map(), charts: stubCharts,
      fetchWalk: async () => ({ ok: true, body: JSON.parse(JSON.stringify(answer)) }) });
    part.mount();
    return part;
  };
  const tipText = (part) => walk(part.root).filter((n) => String(n.className).startsWith('sf-tip')).flatMap((n) => n.children.map((c) => c._text));
  const scatter = seat('scatter', { x: key('x'), y: key('y'), tip1: key('p'), label: key('p') }, { labels: 'marked', description: 'Dies by x and y' });
  await settle();
  handlers.mouseover({ data: { id: 'D1' }, event: { event: { clientX: 5, clientY: 5 } } });
  const pointTip = tipText(scatter);
  handlers.mouseout();
  const gone = tipText(scatter).length;
  const tags = (labels) => { scatter.setDeclaration({ ...scatter.declaration(), labels }); return scatter.model.points.map((p) => [p.id, p.tag]); };
  const marked = scatter.model.points.map((p) => [p.id, p.tag]);
  const all = tags('all');
  const none = tags('none');
  const desc = walk(scatter.host).filter((n) => String(n.className) === 'sf-part__desc').map((n) => n._text);
  const cross = seat('crossTable', { rows: key('x'), tip1: key('p') });
  await settle();
  // the legend column: nothing to draw - none (the frame column 0); a Color by declared - its categories there (lead 10-14)
  const legendOf = (part) => [String(part.root.children[part.root.children.length - 1].className).includes('sf-frame--nolegend'),
    walk(part.root).filter((n) => String(n.className).startsWith('sf-legend__name')).map((n) => n._text)];
  const bare = legendOf(cross);
  const coloured = seat('crossTable', { rows: key('x'), color: key('p') });
  await settle();
  const legends = [bare, legendOf(coloured)];
  walk(cross.host).find((n) => n.tagName === 'TH' && n._text === '3').parentNode.children[1].dispatch('mousemove', { clientX: 5, clientY: 5 });
  const cellTip = tipText(cross);
  return { pointTip, gone, marked, all, none, desc, cellTip, legends };
}

/** Top/Bottom N (base set 11, show_items.js): the rule itself, then seated - a scatter's points, a hub's folded value. */
async function showCases(M) {
  const one = (value) => ({ reads: { show: { state: 'one', value } } });
  const marks = [{ id: 'a', ...one(5) }, { id: 'b', ...one('7') }, { id: 'c', ...one(7) }, { id: 'd', reads: { show: { state: 'several', values: [1, 9] } } }, { id: 'e', ...one('x') }];
  const ids = (rule, n) => M.show.showItems(marks, { encode: { show: {} }, show: { rule, n } }).kept.map((m) => m.id);
  const rule = [ids('top', 2), ids('top', 1), ids('bottom', 1), ids('top', 9), ids('all', 1), M.show.showItems(marks, { show: { rule: 'top', n: 1 } }).kept.length];
  const die = (id, x, y, p) => ({ id, type: 'die', label: id, keys: { x: String(x), y: String(y), p }, attributes: {} });
  const answer = { nodes: [die('D1', 1, 2, 'A'), die('D2', 3, 4, 'B'), die('D3', 3, 5, 'A')], edges: [], truncated: ANSWER.truncated };
  const key = (name) => ({ steps: [], value: { on: 'key', name }, words: [name] });
  const doc = makeDoc('dark');
  const stubCharts = { init: () => ({ setOption() {}, dispatchAction() {}, on() {}, getZr() { return { on() {} }; }, resize() {}, dispose() {} }) };
  const seat = async (encode, show) => {
    const decl = { id: 'S', part: 'visual', kind: 'scatter', row: 'die', start: { marking: null }, system: null, filter: [], encode, show };
    const part = new M.visual.VisualPart(doc.createElement('div'), { doc, markings: new MarkingStore(), start: decl.start, declaration: decl,
      kinds: { scatter: M.scatter.kind }, filters: new KeyedStore(), stats: new KeyedStore(), active: new KeyedStore(), hubs: new HubBook(), names: new Map(), charts: stubCharts,
      fetchWalk: async () => ({ ok: true, body: JSON.parse(JSON.stringify(answer)) }) });
    part.mount();
    await settle();
    return [part.model.points.map((pt) => pt.label), (statusWords(part.stats.get('S')) || []).find((w) => w.includes('not shown')) || null];
  };
  const points = await seat({ x: key('x'), y: key('y'), show: key('x') }, { rule: 'top', n: 1 });
  const hubs = await seat({ x: { ...key('x'), reduce: 'Avg' }, y: { ...key('y'), reduce: 'Avg' }, marker1: key('p'), show: { ...key('x'), reduce: 'Avg' } }, { rule: 'top', n: 1 });
  return { rule, points, hubs };
}

/** The three the app found on 18766 (lead 10-14): a time shown as the grid shows it (tooltip, filter - the one place
 *  slot.valueText), a label on the point's inner side, a filter value one line with its words in its tooltip. */
async function shownWords(M) {
  const ISO = '2026-11-23T18:49:00Z';
  const answer = { nodes: [{ id: 'D1', type: 'die', label: 'D1', keys: {}, attributes: { when: { $datetime: ISO } } }], edges: [], truncated: ANSWER.truncated };
  const index = M.reach.indexGraph(answer);
  const inside = new Set(['D1']);
  const when = { steps: [], value: { on: 'node', name: 'when' }, words: ['when'] };
  const read = M.slot.readSlot(index, inside, 'D1', when);
  const tip = M.tooltip.tipLines({ id: 'D1', ids: ['D1'] }, { rowsById: new Map([['D1', { id: 'D1', label: 'D1', reads: { tip1: read } }]]), slots: [{ key: 'tip1' }], encode: { tip1: when } });
  // a cross table cell of two rows reading the same time
  const cellTip = M.tooltip.tipLines({ ids: ['D1', 'D2'] }, { rowsById: new Map(['D1', 'D2'].map((id) => [id, { id, label: id, reads: { tip1: read } }])), slots: [{ key: 'tip1' }], encode: { tip1: when } });
  const doc = makeDoc('dark');
  const spans = (summary) => walk(M.cond.drawCondition(doc, summary, null, () => {})).filter((n) => String(n.className) === 'sf-filter__t')
    .map((n) => [n._text, n.title, n.getAttribute('data-clip-ok') !== null]);
  const LONG = 'fake-SYN-CW-103-01-core_cmp_nonuniform';
  const filter = [spans({ row: 'die', words: 'when', slot: when, values: [[read.value, 1]], empty: 0, time: read.time }),
    spans({ row: 'die', words: 'meas_id', slot: { ...when, value: { on: 'node', name: 'meas_id' } }, values: [[LONG, 2]], empty: 0 })];
  const pal = { bg: '#000000', text: '#FFFFFF', axis: '#666666', active: '#7188F8', brush: '#000000', one: ['#111111', '#222222'], cat: [] };
  const pt = (id, x) => ({ id, ids: [id], label: id, tag: id, x, y: 1, fill: '#111111', border: '#222222', marked: false });
  const option = M.scatter.scatterOption({ points: [pt('a', 1), pt('b', 2), pt('c', 3)], xKind: 'value', yKind: 'value', size: 6 }, pal);
  const sides = option.series[0].data.map((d) => [d.id, d.label.position]);
  return { read: [read.state, read.time], tip, cellTip, stamp: localStamp(ISO), filter, sides, LONG };
}

/** Trellis (base set 12, trellis.js): the rows split by Panel by, each panel the kind's picture of its rows; one extent
 *  for every panel; a press in a panel marks its rows there, the panel's value among the conditions. */
async function trellisCases(M) {
  const one = (value) => ({ state: 'one', value });
  const rows = [{ id: 'r1', reads: { panel: one('B') } }, { id: 'r2', reads: { panel: { state: 'several', values: ['A', 'B'] } } }, { id: 'r3', reads: {} }];
  const split = M.trellis.panelsOf(rows, { encode: { panel: { steps: [], value: { on: 'key', name: 'p' }, words: ['p'] } } });
  const panel = split[0];
  const hub = M.trellis.inPanel([{ id: 'h', ids: ['r2'], where: [['lot', 'L1']] }], panel, 'die')[0];
  const pure = [split.map((s) => [s.name, s.rows.map((r) => r.id)]), M.trellis.withPanel(M.trellis.withPanel([['lot', 'L1']], panel), panel), [hub.id === hubId('die', [['lot', 'L1'], ['p', 'A']]), hub.where],
    M.trellis.panelsOf(rows, { encode: {} })];
  const die = (id, x, y, p) => ({ id, type: 'die', label: id, keys: { x: String(x), y: String(y), p }, attributes: {} });
  const answer = { nodes: [die('D1', 1, 2, 'A'), die('D2', 3, 9, 'B'), die('D3', 3, 5, 'A')], edges: [], truncated: ANSWER.truncated };
  const key = (name) => ({ steps: [], value: { on: 'key', name }, words: [name] });
  const doc = makeDoc('dark');
  const charts = [];
  const stubCharts = { init: () => { const h = {}; charts.push(h); return { setOption(o) { h.option = o; }, dispatchAction() {}, on(name, fn) { h[name] = fn; }, getZr() { return { on() {} }; }, resize() {}, dispose() {} }; } };
  const markings = new MarkingStore();
  const hubs = new HubBook();
  const crossKind = (await import('../src/testbed/kinds/cross_table.js')).kind;
  const seat = async (kind, encode) => {
    const decl = { id: kind, part: 'visual', kind, row: 'die', start: { marking: null }, system: null, filter: [], writes: 'marking:pick', encode };
    const part = new M.visual.VisualPart(doc.createElement('div'), { doc, markings, writes: decl.writes, start: decl.start, declaration: decl,
      kinds: { scatter: M.scatter.kind, crossTable: crossKind }, filters: new KeyedStore(), stats: new KeyedStore(), active: new KeyedStore(), hubs, names: new Map(), charts: stubCharts,
      fetchWalk: async () => ({ ok: true, body: JSON.parse(JSON.stringify(answer)) }) });
    part.mount();
    await settle();
    return part;
  };
  const sc = await seat('scatter', { x: key('x'), y: key('y'), panel: key('p') });
  const drawnPanels = walk(sc.root).filter((n) => String(n.className) === 'sf-trellis__h').map((n) => n._text);
  const axes = (sc.panels || []).map((pn) => { const o = M.scatter.scatterOption(pn.model, { bg: '#000000', text: '#FFFFFF', axis: '#666666', active: '#7188F8', brush: '#000000', one: ['#111111', '#222222'], cat: [] });
    return [pn.name, pn.model.points.map((pt) => pt.id), o.xAxis.min, o.xAxis.max, o.yAxis.min, o.yAxis.max]; });
  answer.nodes.push(die('D4', 3, 9, 'B'));
  const hubsSeat = await seat('scatter', { x: { ...key('x'), reduce: 'Avg' }, y: { ...key('y'), reduce: 'Avg' }, marker1: key('x'), panel: key('p') });
  const aThree = hubsSeat.panels ? hubsSeat.panels[0].model.points.find((pt) => pt.label === '3') : null;
  const held = () => markings.entries('marking:pick').map(([id]) => [hubOf(id) ? hubOf(id).where : id, hubs.membersOf(id)]);
  if (aThree) hubsSeat.markHubs([[aThree.where, aThree.ids]], {});
  await settle();
  const marker = held();
  const cross = await seat('crossTable', { rows: key('x'), panel: key('p') });
  const cell = walk(cross.root).filter((n) => n.tagName === 'TD' && n.listeners && n.listeners.click);
  cell[cell.length - 1].listeners.click[0]({});
  await settle();
  const cellHeld = held();
  // a marking holding the wafer node (pressed in a part with no panels): a panel's cell of that wafer is its rows there,
  // the panel's value a second condition - not the wafer, so not drawn marked (as a two-axis cell)
  const wafer = (id, label) => ({ id, type: 'wafer', label, keys: {}, attributes: {} });
  answer.nodes.push(wafer('W1', 'W1'));
  answer.edges = ['D1', 'D2', 'D3'].map((d, i) => ({ id: `e${i}`, source: d, target: 'W1', predicate: 'in_container', qualifiers: {} }));
  markings.replace('marking:pick', [['W1', SIGN.CASE]]);
  const byWafer = await seat('crossTable', { rows: { steps: [{ predicate: 'in_container', direction: 'outgoing' }], value: { on: 'label', name: 'name' }, words: ['wafer'] }, panel: key('p') });
  const waferCells = (byWafer.panels || []).map((pn) => [pn.name, pn.model.grid[0][0].marked]);
  // that cell pressed in panel A: a hub of its 2 rows there, and the status says why not the wafer
  const tds = walk(byWafer.root).filter((n) => n.tagName === 'TD' && n.listeners && n.listeners.click);
  if (tds.length) tds[0].listeners.click[0]({});
  await settle();
  const why = (statusWords(byWafer.stats.get('crossTable')) || []).find((w) => w.startsWith('marked a hub')) || null;
  // a sheet takes no Top/Bottom by and no Panel by (its kind's `without`)
  const sheetSlots = new M.visual.VisualPart(doc.createElement('div'), { doc, markings: new MarkingStore(), declaration: { id: 'SH', kind: 'sheet', row: 'die', encode: {} },
    kinds: { sheet: M.sheet.kind } }).slotList().map((s) => s.key).filter((k) => k === 'show' || k === 'panel');
  return { pure, drawnPanels, axes, marker, cell: cellHeld, waferCells, why, sheetSlots };
}

/** Shape by (base set 7-b, shape_by.js): a category's shape - declared, else the next one free (the colours' rule); a points
 *  kind draws it and the legend says the same names; a kind that draws no points holds no Shape by. */
async function shapeCases(M) {
  const one = (value) => ({ state: 'one', value });
  const rows = [{ id: 'r1', reads: { shape: one('A') } }, { id: 'r2', reads: { shape: one('B') } }, { id: 'r3', reads: { shape: one('A') } }, { id: 'r4', reads: {} }];
  const s = M.shape.shapesOf(rows, { encode: { shape: {} }, shapes: { B: 'diamond' } });
  const pure = [s.categories.map((c) => [c.name, c.shape, c.ids]), s.assigned, M.shape.shapeOfIds(s, ['r1', 'r3']), M.shape.shapeOfIds(s, ['r1', 'r2']),
    M.color.assignLooks(['x', 'y', 'z'], { y: 'p1' }, ['p1', 'p2'])];
  const die = (id, x, y, p) => ({ id, type: 'die', label: id, keys: { x: String(x), y: String(y), p }, attributes: {} });
  const answer = { nodes: [die('D1', 1, 2, 'A'), die('D2', 3, 9, 'B'), die('D3', 3, 5, 'A')], edges: [], truncated: ANSWER.truncated };
  const key = (name) => ({ steps: [], value: { on: 'key', name }, words: [name] });
  const doc = makeDoc('dark');
  const stubCharts = { init: () => ({ setOption() {}, dispatchAction() {}, on() {}, getZr() { return { on() {} }; }, resize() {}, dispose() {} }) };
  const markings = new MarkingStore();
  const crossKind = (await import('../src/testbed/kinds/cross_table.js')).kind;
  const seat = async (kind, encode) => {
    const decl = { id: kind, part: 'visual', kind, row: 'die', start: { marking: null }, system: null, filter: [], writes: 'marking:pick', encode };
    const part = new M.visual.VisualPart(doc.createElement('div'), { doc, markings, writes: decl.writes, start: decl.start, declaration: decl,
      kinds: { scatter: M.scatter.kind, crossTable: crossKind }, filters: new KeyedStore(), stats: new KeyedStore(), active: new KeyedStore(), hubs: new HubBook(), names: new Map(), charts: stubCharts,
      fetchWalk: async () => ({ ok: true, body: JSON.parse(JSON.stringify(answer)) }) });
    part.mount();
    await settle();
    return part;
  };
  const sc = await seat('scatter', { x: key('x'), y: key('y'), shape: key('p') });
  const pal = { bg: '#000000', text: '#FFFFFF', axis: '#666666', active: '#7188F8', brush: '#000000', one: ['#111111', '#222222'], cat: [] };
  const drawn = M.scatter.scatterOption(sc.model, pal).series[0].data.map((d) => [d.id, d.symbol || null]);
  const glyphs = walk(sc.root).filter((n) => String(n.className) === 'sf-legend__shape').map((n) => n.getAttribute('data-shape'));
  const name = walk(sc.root).find((n) => String(n.className) === 'sf-legend__name' && n._text === 'B' && n.parentNode.children.some((c) => String(c.className) === 'sf-legend__shape'));
  if (name) name.listeners.click[0]({});
  await settle();
  const pressed = markings.entries('marking:pick').map(([id]) => (hubOf(id) ? hubOf(id).where : id));
  const cross = await seat('crossTable', { rows: key('x') });
  return { pure, drawn, glyphs, kept: sc.declaration().shapes || null, pressed, crossSlots: cross.slotList().some((x) => x.key === 'shape') };
}

/** The fourth 18766 look (lead 10-14): a picture follows its own div's size (a panel's chart resized when its div grows);
 *  a tooltip says a slot's words once; a label no longer than its room, the x ticks as many as the width holds. */
async function fourthLook(M) {
  const watched = [];
  const was = globalThis.ResizeObserver;
  globalThis.ResizeObserver = class { constructor(cb) { this.cb = cb; this.on = true; watched.push(this); } observe() {} disconnect() { this.on = false; } };
  const die = (id, x, y, p) => ({ id, type: 'die', label: id, keys: { x: String(x), y: String(y), p }, attributes: {} });
  const answer = { nodes: [die('D1', 1, 2, 'A'), die('D2', 3, 9, 'B'), die('D3', 3, 5, 'A')], edges: [], truncated: ANSWER.truncated };
  const key = (name) => ({ steps: [], value: { on: 'key', name }, words: [name] });
  const doc = makeDoc('dark');
  let resized = 0;
  const stubCharts = { init: () => ({ setOption() {}, dispatchAction() {}, on() {}, getZr() { return { on() {} }; }, resize() { resized += 1; }, dispose() {} }) };
  const decl = { id: 'S', part: 'visual', kind: 'scatter', row: 'die', start: { marking: null }, system: null, filter: [], encode: { x: key('x'), y: key('y'), panel: key('p') } };
  const part = new M.visual.VisualPart(doc.createElement('div'), { doc, markings: new MarkingStore(), start: decl.start, declaration: decl,
    kinds: { scatter: M.scatter.kind }, filters: new KeyedStore(), stats: new KeyedStore(), active: new KeyedStore(), hubs: new HubBook(), names: new Map(), charts: stubCharts,
    fetchWalk: async () => ({ ok: true, body: JSON.parse(JSON.stringify(answer)) }) });
  part.mount();
  await settle();
  const live = watched.filter((w) => w.on);
  for (const w of live) w.cb([]);
  const resize = [live.length, resized];
  globalThis.ResizeObserver = was;
  const y = key('value');
  const tip = M.tooltip.tipLines({ id: 'M1', ids: ['M1'] }, { rowsById: new Map([['M1', { id: 'M1', label: 'M1', reads: { y: { state: 'one', value: 4 }, show: { state: 'one', value: 4 }, panel: { state: 'one', value: 'S1' } } }]]),
    slots: [{ key: 'y' }, { key: 'show' }, { key: 'panel' }], encode: { y, show: y, panel: key('step') } });
  const pal = { bg: '#000000', text: '#FFFFFF', axis: '#666666', active: '#7188F8', brush: '#000000', one: ['#111111', '#222222'], cat: [] };
  const pt = (id, x) => ({ id, ids: [id], label: id, tag: `fake-SYN-CW-103-01-${id}`, x, y: 1, fill: '#111111', border: '#222222', marked: false });
  const model = { points: [pt('a', 0), pt('b', 10)], xKind: 'value', yKind: 'value', size: 6 };
  const narrow = M.scatter.scatterOption(model, pal, 268);
  const loose = M.scatter.scatterOption(model, pal);
  const label = (o) => o.series[0].data.map((d) => [d.id, d.label.position, d.label.width === undefined ? null : d.label.width, d.label.overflow || null]);
  return { resize, tip, labels: [label(narrow), label(loose)], ticks: [narrow.xAxis.splitNumber, narrow.xAxis.axisLabel.hideOverlap, loose.xAxis.splitNumber === undefined] };
}

/** A pill's picker under its pill (owner 10-14 «알약 선언창 자꾸 화면 좌상단으로 날아가는데»): the pill drawn again
 *  (a pick redraws the part, the properties panel on every pick) - the picker placed under the new pill, never at 0,0. A
 *  stub with a layout: an element in the document a box by when it was made, one drawn away 0,0 (the browser's). */
async function pickerFollows(M) {
  const doc = makeDoc('dark');
  let made = 0;
  const create = doc.createElement.bind(doc);
  const inDoc = (n) => { for (let up = n; up; up = up.parentNode) if (up === doc.documentElement) return true; return false; };
  doc.createElement = (tag) => {
    const n = create(tag);
    const at = (made += 1);
    Object.defineProperty(n, 'isConnected', { get: () => inDoc(n) });
    n.getBoundingClientRect = () => (inDoc(n) ? { left: 100 + (at % 50) * 10, top: 300, right: 160 + (at % 50) * 10, bottom: 321, width: 60, height: 21 }
      : { left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0 });
    n.offsetWidth = 200;
    n.offsetHeight = 100;
    return n;
  };
  doc.documentElement.clientWidth = 1920;
  doc.documentElement.clientHeight = 950;
  const pickerHost = doc.createElement('div');
  doc.body.appendChild(pickerHost);
  const picker = new M.picker.SlotPicker(pickerHost, { doc });
  const key = (name) => ({ steps: [], value: { on: 'key', name }, words: [name] });
  const die = (id, x, y) => ({ id, type: 'die', label: id, keys: { x: String(x), y: String(y) }, attributes: {} });
  const answer = { nodes: [die('D1', 1, 2), die('D2', 3, 4)], edges: [], truncated: ANSWER.truncated };
  const decl = { id: 'S', part: 'visual', kind: 'scatter', row: 'die', start: { marking: null }, system: null, filter: [], encode: { x: key('x'), y: key('y') } };
  const host = doc.createElement('div');
  doc.body.appendChild(host);
  const stubCharts = { init: () => ({ setOption() {}, dispatchAction() {}, on() {}, getZr() { return { on() {} }; }, resize() {}, dispose() {} }) };
  const part = new M.visual.VisualPart(host, { doc, markings: new MarkingStore(), start: decl.start, declaration: decl, kinds: { scatter: M.scatter.kind },
    filters: new KeyedStore(), stats: new KeyedStore(), active: new KeyedStore(), hubs: new HubBook(), names: new Map(), charts: stubCharts,
    openPicker: (at) => picker.open(at), fetchWalk: async () => ({ ok: true, body: JSON.parse(JSON.stringify(answer)) }) });
  part.mount();
  await settle();
  const pillX = () => walk(part.root).find((n) => n.attrs && n.attrs['data-slot'] === 'x');
  const placed = () => [pickerHost.style.left, pickerHost.style.top];
  const under = (pill) => { const r = pill.getBoundingClientRect(); return [`${r.left}px`, `${r.bottom + 4}px`]; };
  const first = pillX();
  first.listeners.click[0]({});
  const opened = [placed(), under(first)];
  // the part drawn again (a walk's answer, a pick before) - its pills are new
  part.render();
  const again = pillX();
  const value = walk(pickerHost).find((n) => n.tagName === 'BUTTON' && String(n.className).startsWith('sf-pop__it') && n._text && n._text.startsWith('y'));
  if (value) value.listeners.click[0]({});
  const picked = [placed(), under(pillX() || again)];
  return { opened, picked, moved: again !== first };
}

/** A pill of several columns (owner 10-14): the slot's value a list of columns, an older one-column slot a list of one
 *  (slot.js columnsOf); a cross table axis a hierarchy (an outer value told once along its run); Color by a combination
 *  one category; the picker's «+ Column» writes the list. */
async function manyColumns(M) {
  const key = (name) => ({ steps: [], value: { on: 'key', name }, words: [name] });
  const die = (id, x, p) => ({ id, type: 'die', label: id, keys: { x: String(x), y: '1', p }, attributes: {} });
  const answer = { nodes: [die('D1', 1, 'A'), die('D2', 3, 'B'), die('D3', 3, 'A')], edges: [], truncated: ANSWER.truncated };
  const index = M.reach.indexGraph(answer);
  const inside = new Set(['D1', 'D2', 'D3']);
  const read = M.slot.readSlot(index, inside, 'D1', [key('p'), key('x')]);
  const pure = [[read.state, read.value, read.parts], M.slot.slotWords([key('p'), key('x')]), M.slot.columnsOf(key('p')).length,
    JSON.stringify(M.slot.readSlot(index, inside, 'D1', [key('p')])) === JSON.stringify(M.slot.readSlot(index, inside, 'D1', key('p')))];
  const doc = makeDoc('dark');
  const pickerHost = doc.createElement('div');
  const picker = new M.picker.SlotPicker(pickerHost, { doc });
  const stubCharts = { init: () => ({ setOption() {}, dispatchAction() {}, on() {}, getZr() { return { on() {} }; }, resize() {}, dispose() {} }) };
  const seat = async (kind, encode) => {
    const decl = { id: kind, part: 'visual', kind, row: 'die', start: { marking: null }, system: null, filter: [], encode };
    const part = new M.visual.VisualPart(doc.createElement('div'), { doc, markings: new MarkingStore(), start: decl.start, declaration: decl,
      kinds: { scatter: M.scatter.kind, crossTable: M.cross.kind }, filters: new KeyedStore(), stats: new KeyedStore(), active: new KeyedStore(), hubs: new HubBook(), names: new Map(), charts: stubCharts,
      openPicker: (at) => picker.open(at), fetchWalk: async () => ({ ok: true, body: JSON.parse(JSON.stringify(answer)) }) });
    part.mount();
    await settle();
    return part;
  };
  const cross = await seat('crossTable', { rows: [key('p'), key('x')] });
  const heads = walk(cross.root).filter((n) => n.tagName === 'TH' && String(n.className).startsWith('sf-table__row') && n._text !== 'Total').map((n) => [n._text, n.rowSpan || 1]);
  const scatter = await seat('scatter', { x: key('x'), y: key('y'), color: [key('p'), key('x')] });
  const colours = scatter.colors.categories.map((c) => c.name);
  // the picker on the row axis: «+ Column», then a value - the slot a list of two
  const one = await seat('crossTable', { rows: key('p') });
  walk(one.root).find((n) => n.attrs && n.attrs['data-slot'] === 'rows').listeners.click[0]({});
  const plus = walk(pickerHost).find((n) => n.tagName === 'BUTTON' && n._text === '+ Column');
  if (plus) plus.listeners.click[0]({});
  const value = walk(pickerHost).find((n) => n.tagName === 'BUTTON' && String(n.className).startsWith('sf-pop__it') && n._text === 'x');
  if (value) value.listeners.click[0]({});
  await settle();
  const written = (one.declaration().encode.rows || []).map ? one.declaration().encode.rows.map((c) => c.value.name) : null;
  // the second column's chip dragged onto the first - the declaration's columns change places, the hierarchy's outer head
  // the other column now
  const chip = (k) => walk(pickerHost).find((n) => n.attrs && n.attrs['data-column'] === String(k));
  const [second, first] = [chip(1), chip(0)];
  if (second && first) { second.listeners.dragstart[0]({}); first.listeners.drop[0]({}); }
  await settle();
  const reordered = M.slot.columnsOf(one.declaration().encode.rows).map((c) => c.value.name);
  const outer = walk(one.root).filter((n) => n.tagName === 'TH' && String(n.className) === 'sf-table__row').map((n) => n._text).filter((w) => w !== 'Total');
  return { pure, heads, rowKeys: cross.model.rowKeys, colours, written, reordered, outer };
}

const names = [];
const failures = [];
function judge(name, got, want) {
  names.push(name);
  const ok = json(got) === json(want);
  if (!ok) failures.push(name);
  return { name, ok, got, want };
}

async function suite(M) {
  names.length = 0;
  failures.length = 0;
  const m = await measure(M);
  const s = await shells(M);
  const p = await pages(M);
  const one = await seated(M);
  const k = await chains(M);
  const sc = await seatedChain(M);
  const mk = markerModels(M);
  const mp = await markerPress(M);
  const ts = await trendAsScatter(M);
  const rt = await routed(M);
  const pw = await partWalks(M);
  const ce = await colourEverywhere(M);
  const sh = await sheetRoot(M);
  const ks = await keptStart(M);
  const tl = await tipsAndLabels(M);
  const si = await showCases(M);
  const sw = await shownWords(M);
  const tr = await trellisCases(M);
  const fl = await fourthLook(M);
  const shp = await shapeCases(M);
  const pf = await pickerFollows(M);
  const mc = await manyColumns(M);
  const cc = await categoryColours(M);
  const rp = await recordPoints(M);
  const ly = await layered(M);
  const cRel = await markedColour(M, true);
  const cNone = await markedColour(M, false);
  const mpp = await mapPress(M);
  const lines = [
    judge('S1 a part docked on each edge of another: side by side or stacked, on that side', m.dock,
      [['row', ['B', 'A']], ['row', ['A', 'B']], ['column', ['B', 'A']], ['column', ['A', 'B']]]),
    judge('S1b on the page\'s edge the whole rest on the other side; onto itself nothing moves', m.pageEdge, ['column', ['A', 'B', 'C'], true]),
    judge('S2 a dragged line: the pair keeps its sum, neither under 60 px; a pair under two floors stays', m.resize,
      [[1.2, 0.8, 2], [1.88, 0.1200000000000001], [0.12, 1.88], [1, 1]]),
    judge('S3 the last part closed: no tree; a part added to none is the tree', m.last, [null, { id: 'N' }]),
    judge('S4 a closed part\'s share goes back to its neighbours; a split of one is that one in its share', m.share,
      [{ split: 'row', children: [leaf('A'), leaf('C', 2)] }, { split: 'row', children: [leaf('A', 3), leaf('B', 2)] }]),
    judge('S5 an added part splits the largest: stacked new-on-top when it is not wider, side by side new-on-the-right when it is', m.add,
      [json({ split: 'row', children: [leaf('A'), { split: 'column', children: [leaf('N'), leaf('B')], size: 1 }] }),
        json({ split: 'row', children: [{ split: 'row', children: [leaf('A'), leaf('N')], size: 1 }, leaf('B')] })]),
    judge('S6 a drop\'s edge is the nearest by the box\'s own proportions', m.edges, ['left', 'right', 'top', 'bottom']),
    judge('S7 a drop on a part\'s middle: the two swap places, shares and shape kept; near a side that edge; onto itself or a part not there nothing moves', m.swap,
      ['{"split":"row","children":[{"id":"C","size":2},{"split":"column","size":1,"children":[{"id":"B","size":1},{"id":"A","size":3}]}]}', true, true, 'center', 'left', 'top']),
    judge('L1 the limit: in all of the markings, in any; all empty - every row or none; one empty of two under all - none (not the empty branch); no limit - every row',
      m.limit, [['W2'], ['W1', 'W2', 'W3'], ['W1', 'W2', 'W3', 'W4'], [], [], ['W1', 'W2', 'W3', 'W4']]),
    judge('L2 a hub in a limiting marking counts as its members', m.hub, [['W1', 'W3'], ['W1']]),
    judge('T1 the table: columns in their order, the next one, a number column; sorted up and down with blanks last, a stale sort none; the shown marking marked',
      m.table, { keys: ['col1', 'col3'], next: 'col4', numeric: [false, true], asc: ['W4', 'W2', 'W1', 'W3'], desc: ['W1', 'W2', 'W4', 'W3'],
        marked: ['W2'], stale: ['W1', 'W2', 'W3', 'W4'] }),
    judge('G3 a redraw moves the panels: dock, resize, maximize and restore seat nothing again; maximized shows one; the docked one stays docked',
      s.redraw, { mounts: 4, same: true, maxed: ['B'], cells: ['C', 'A', 'B'],
        root: json({ split: 'row', children: [{ split: 'row', children: [leaf('C'), leaf('A')], size: 1.25 }, { id: 'B', size: 0.75 }] }), docked: true }),
    judge('G4 every area part closed: the area says «Add a visualization»; one added is the tree; a docked panel is not closed', s.last,
      { root: json({ id: 'N' }), empty: true, docked: true, seated: 2 }),
    judge('G1 two Boards side by side: one\'s dock and pick leave the other\'s tree and table alone', p.two,
      { otherTree: true, mine: ['W1'], other: [], trees: true }),
    judge('G2 Save keeps the tree and each visual (a table\'s sort too); a reopen draws them', p.save, { tree: true, visuals: true, sortKept: true }),
    judge('G3s a drop on a part\'s middle swaps the two in the shell, nothing seated again', [s.swapShell[0], s.swapShell[2], s.swapShell[3]], [s.swapShell[1], true, 3]),
    judge('G2c a part dropped on another\'s middle swaps with it - the tree\'s shape the same, Save keeps it', p.swapSaved,
      ['scatter-1,cross-1,marked', 'marked,cross-1,scatter-1', true, true]),
    judge('G2b an older save (visuals by id) opens on the layout\'s tree, its visuals laid over, the chrome docked', p.older, { tree: true, x: true, docks: true }),
    // walked: 0 - each new part's row walk is the page's in hand (lead-board-10c)
    judge('G5 each kind added: its id and kind, the largest split (the scatter, stacked: new on top), the new one active, its rows the page\'s walk in hand; the add window lists them in order',
      p.add, { ids: ['table-1', 'crossTable-1', 'scatter-2', 'map-1', 'sheet-1'], kinds: ['table', 'crossTable', 'scatter', 'map', 'sheet'], active: 'sheet-1', firstPath: '[0,0]',
        scatterPath: '[0,1]', walked: 0, flyout: ['Table', 'Cross table', 'Scatter plot', 'Map', 'Sheet'] }),
    judge('L3 the Marked table: empty while nothing is picked; a hub picked - its members; N of M and the limit\'s drop, none hidden; a line pressed re-marks to it; a head sorts; the ground clears',
      p.marked, { emptyFirst: 0, viaHub: ['W1', 'W3'], counts: [2, 4, 2, 0], afterPress: ['W3'], sort: { key: 'col1', desc: false }, cleared: 0, emptyAgain: 0 }),
    judge('L4 a limited part counts the limit\'s drop apart: a marked row it leaves out is not hidden; a limiting marking changed, it folds again',
      { before: one.before, after: one.after }, { before: { rows: 1, of: 4, limit: 3, hidden: 0, marked: 1 }, after: ['W1', 'W4'] }),
    judge('T2 a table line pressed with Ctrl joins the pick; pressed alone it is the pick', [one.added, one.replaced], [['W2', 'W4'], ['W1']]),
    judge('F1 a filter can take a slot or a row\'s own value - its keys and attributes, not only the axes', one.filterable, [['col1', 'name'], ['own:key:wafer', 'wafer']]),
    judge('K1 markings added: the next free names, «Marking (n)», each its own colour', k.added,
      { names: ['marking:3', 'marking:4', 'marking:5'], labels: ['Start', 'Pick', 'Marking (3)', 'Marking (4)', 'Marking (5)'], colours: true }),
    judge('K1b a chain declared: B walks from what A marks, C from what B marks', k.built,
      { b: ['W2', 'W3'], c: ['W2', 'W3', 'W4'], held: [['W2'], ['W2', 'W3'], ['W3', 'W4']] }),
    judge('K2 A marks again: B walks once from it, its marking keeps what its new data holds, so C walks once from that - and its marking the same',
      // no request: B's walk from W1 and C's from W2 are the page's in hand (lead-board-10c)
      k.chain, { walks: [], b: ['W1', 'W2'], c: ['W2', 'W3'], held: [['W1'], ['W2'], ['W3']] }),
    judge('K2b the same chain seated alone: B and C walk once each, in turn; each marking keeps what its part\'s new data holds',
      sc, { walked: ['B:W1', 'C:W2'], held: [['W1'], ['W2'], ['W3']] }),
    judge('W10 the panel names no Route - Start from and Rows only', [k.panel.includes('Route'), k.panel.includes('Start from'), k.panel.includes('Rows')], [false, true, true]),
    judge('K3 a loop of markings refused and named, the declaration kept; a part walking from what it writes is one; a limit is not a step',
      k.loop, { refused: false, kept: true, loop: ['marking:3', 'table-2', 'marking:4', 'table-3', 'marking:5', 'table-1', 'marking:3'],
        said: ['Refused - a loop: Marking (3) → wafer → Marking (4) → wafer → Marking (5) → wafer → Marking (3)'],
        self: ['marking:3', 'S', 'marking:3'], limitIsNoStep: null }),
    judge('K5 Save keeps the markings and the chain; a new page from it follows the chain; an older save opens on the default markings',
      { ...k.reopen, olderSave: k.olderSave }, { labels: ['Start', 'Pick', 'Marking (3)', 'Marking (4)', 'Marking (5)'],
        chain: [['marking:start', 'marking:3'], ['marking:3', 'marking:4'], ['marking:4', 'marking:5']], walks: [], marksKept: [['W1'], ['W2'], ['W3']], olderSave: ['Start', 'Pick'] }),
    judge('K4 a marking deleted: its users named first; the part writing it writes none, the part walking from it walks from All (once), a limit loses it; the start row\'s marking not deleted, named; a new one takes the next free name',
      k.deleted, { shown: ['marking:start', 'marking:pick', 'marking:3', 'marking:4', 'marking:5'], ask: ['Used by Marked, wafer, wafer'],
        after: ['marking:start', 'marking:pick', 'marking:3', 'marking:5', 'marking:6'], b: ['marking:3', null], c: [null, 'marking:5'],
        limit: ['marking:pick'], walks: ['type:wafer'], kept: ['Not deleted - used by start'] }),
    judge('K6 a marking\'s colour is its marked lines\' and points\'', k.colour, { line: '#123456', unmarked: true, marked: '#123456' }),
    judge('P1 Marker by none: a point a mark - a node with several x and no reduce a point each (lead-board-13 ②), each its node\'s', mk.none,
      { points: [['W1', 30, 5, ['W1'], false], ['W2', 10, 5, ['W2'], false], ['W3', 20, 5, ['W3'], false], ['W3', 26, 5, ['W3'], false], ['W4', 40, 7, ['W4'], false]], several: 0 }),
    judge('P2 Marker by lot: a point a lot - x the Avg of every value of its rows (not of each row\'s); y without a reduce its one value, several not drawn; marked when a row of it is',
      mk.lot, { points: [['L1', 25.333, 5, ['W1', 'W3'], true]], several: 1 }),
    judge('P3 Marker by lot and product: a point each combination, its words both; x the Count', mk.two,
      { points: [['L1 · A', 1, 5, ['W1'], false], ['L2 · A', 1, 5, ['W2'], false], ['L1 · B', 2, 5, ['W3'], false], ['L2 · B', 1, 7, ['W4'], false]], several: 0 }),
    judge('P4 Latest: the newest value of the marker\'s rows; Avg on y', mk.latest,
      { points: [['L1', 26, 5, ['W1', 'W3'], false], ['L2', 40, 6, ['W2', 'W4'], false]], several: 0 }),
    judge('P5 a marker is the hub the cross table names (hubId of the row type and the values by their words); the slots - Marker by held and the next, the axes folding',
      [mk.hub, mk.slots], [[hubId('wafer', [['lot', 'L1']]), hubId('wafer', [['lot', 'L2']])],
        [['x', 'y', 'marker1', 'color', 'shape', 'label', 'tip1', 'show', 'panel'], ['x*', 'y*', 'marker1', 'marker2', 'color', 'shape', 'label', 'tip1', 'show*', 'panel']]]),
    judge('R1 the trend as one scatter declaration (X the time of Y\'s reads, Marker by a value record): the trend\'s points, their times and values, on a time axis; the pill says the unit; a record pressed marks its node',
      ts, { same: true, n: [5, 5], times: ['2026-01-01', '2026-01-02', '2026-01-03', '2026-01-04', '2026-01-05'], xKind: 'time', pill: '(Value record)', marked: ['W1'] }),
    judge('Y1 no relation: the layer of a marking is its members (a hub its members) - for every node the same as holds()', [ly.none, ly.same],
      [[false, false, false, false, true, false, false, false, false], true]),
    judge('Y2 relations die -bonded_from-> die, die -in_container-> wafer: the layer spreads along them; a wafer no in_container of which was walked is not known; another type not marked',
      ly.spread, [true, true, false, null, true, false, true, false, false]),
    judge('Y3 asked again and again - computed once; the marking changed - once more, the new spread', [ly.unchanged, ly.changed, ly.moved], [0, 1, ['BW', 'CW2', 'd2', 'c2']]),
    judge('Y4 D in little: If(Marked("Core wafer"), "B", "other") - with the relations the points of the core wafer and of the bonding wafer B, one not known counted; the marking moved - folded again',
      cRel, { colours: { BW: 'B', CW1: 'B', CW2: 'other', CW3: null }, unknown: 1, moved: { BW: 'B', CW1: 'other', CW2: 'B', CW3: null } }),
    judge('Y5 no relation: every point other, none unknown', cNone,
      { colours: { BW: 'other', CW1: 'other', CW2: 'other', CW3: 'other' }, unknown: 0, moved: { BW: 'other', CW1: 'other', CW2: 'other', CW3: 'other' } }),
    judge('Y6 the map: a cell a coordinate - two dies at one x, y one cell; pressed, both marked and the cell drawn marked', mpp,
      { cells: [[0, 0, ['a1', 'b1']], [1, 0, ['a2']], [0, 2, ['a3']]], marked: ['a1', 'b1'], drawnMarked: ['0,0'] }),
    judge('R2 a value record a point: an edge of three records three points, of one one; Latest on X and Y - a point an edge, its newest record',
      rp, { all: [['W1', '2026-02-01', '1'], ['W1', '2026-02-02', '2'], ['W1', '2026-02-03', '3'], ['W2', '2026-02-05', '9']],
        latest: [['W1', '2026-02-03', '3'], ['W2', '2026-02-05', '9']] }),
    judge('P7 the units of a value record: a record a unit, X its own record; a reduce - an edge a unit, folded', mk.records,
      [[['W9#0', 't1', '1'], ['W9#1', 't2', '2'], ['W9#2', 't3', '3'], ['W9#3', 't4', '7']], [['W9#0', 't3', '3'], ['W9#1', 't4', '7']]]),
    judge('PW1 the row walk to its end: two pages, the second with the first\'s resume; its rows every die; one value walk for the column; an expired resume said with its reason, the walk cut',
      [pw.resume, pw.expired], [[[['in_container', ['BW'], null], ['in_container', ['BW'], 'r2'], ['measures', ['d1', 'd2', 'd3'], null]], ['d1', 'd2', 'd3'], ['1', '2', '3']],
        [[null, 'k1'], false, 'resume expired', 1]]),
    judge('PW2 covers (the one judgment): a column taken off, another attribute of a type walked - covered; a new type, a cut walk, other rows, a predicate more, a step more - not; a walk that carried every type covers any',
      pw.covers, [true, true, false, false, false, false, false, false, true]),
    judge('PW3 the cache in a part: a column taken off - no request, said cached; another attribute of the type walked - none; a new type - one; a cut walk does not cover its slot',
      pw.cache, [3, 'Column 1 · complete', 'Rows 3 · complete', 0, 'Column 1 · cached', 0, 1, 'Column 1 · complete', 1, 'Column 1 · complete / Column 2 · cut', 1]),
    judge('PW4 a slot changed walks that slot alone - every slot of the table, the scatter, the cross table and the map: one request, asking its way',
      pw.everySlot.map(([k, r]) => [k, r.keys > 1, r.wrong]), [['table', true, []], ['scatter', true, []], ['crossTable', true, []], ['map', true, []]]),
    judge('PW5 a value walk starts from its rows by the seed cap - three rows, a cap of two: two requests, every row read',
      pw.chunks, [[['d1', 'd2'], ['d3']], ['1', '2', '3']]),
    judge('PW6 a walk in flight dropped by the next for its slot - its request aborted, its late answer not drawn, the newest drawn',
      pw.abort, [true, false, ['t1', 't1', 't1']]),
    judge('PW8 two slots of different ways walk at once - both asked before either is answered', pw.together, [2, ['1', 's1']]),
    judge('PW9 a start of the row type a walk on the page carried walks no rows (the value walk only); written by hand, walked for its records; every request asks no ranking',
      pw.startIsRow, [true, ['measures'], ['d3'], [false]]),
    judge('PW10 the runs of a value walk by the seed cap asked together', pw.runsTogether, [2, ['1', '2', '3']]),
    judge('PW11 the ranking left out only where asked: the walk box sends no propagation; the part sends false, its resumed page too', pw.ranking,
      [['GET', null], ['GET', 'false'], ['POST', 'false']]),
    judge('PW12 a value walk folds once when every run is in - three runs asked, two folds (the slot changed, the walk in)', pw.foldOnce,
      [3, 2, ['s1', 's1', 's1']]),
    judge('PW13 one row walk a page: two parts opened together - one request, the second waits for it; a third opened after - none; each its three rows',
      [pw.onePage[0].reduce((a, b) => a + b, 0), pw.onePage[1], pw.onePage[2]], [2, 0, [3, 3, 3]]),
    judge('PW7 core dies (18766): a value walk carrying wafers only read by its edges - each die its own core wafer, the dies it did not carry by their ids',
      pw.core, [['CW1', 'CW2', '(Empty)'], [['d1'], ['d2'], ['d3']], ['c1', 'c2', 'd1', 'd2', 'd3']]),
    judge('W1 a start of the row type is its own row: d1 alone - its own record read (hops 0), no row reached through it; then the slot\'s value walk; its one core wafer',
      rt.dies, [['CW1'], [[[], 0, ['d1']], [['bonded_from', 'in_container'], 2, ['d1']]], ['d1']]),
    judge('W2 from All every die of the type', rt.all, [['CW1', 'CW2', '(Empty)'], ['c1', 'c2', 'd1', 'd2']]),
    judge('W3 die to wafer: every route\'s predicates together, the longest route\'s steps - every wafer the walk reached is a row',
      rt.wafers, [['BW', 'CW1'], [[['bonded_from', 'in_container'], 2, ['d1']]]]),
    judge('W4 the start is the marking\'s spread layer - d1 and the wafer the page\'s relation takes it to, two types together: d1 its own row, the rest walked from BW',
      rt.spread, [['die', 'wafer'], ['d1', 'd2'], [[['in_container'], 1, ['BW']]]]),
    judge('W5 no route from the start\'s type to the rows: said, nothing walked', rt.none, ['refused', 'No route from die to lot', 0]),
    judge('W6 a press: one row - its node (d1, not the core wafer it reads), drawn marked; several rows - their hub; a part whose rows are wafers narrows - the wafer',
      [rt.pure, rt.press], [[['a'], null], [['d1'], true, '0 marked rows - marking holds die; no relation to wafer', ['hub'], ['CW1']]]),
    judge('W9 a part that writes a marking walks the page\'s relations from its rows (said on its walk line); a part starting from that marking starts from its spread layer',
      rt.relationWalk, [[[['bonded_from'], 1, ['d1']]], ['Relations · complete'], ['c1', 'd1']]),
    judge('RC1 Reach(node) in a column: the row walk carries the node (aux) and each row reads its judgment - found true, none false, unknown empty and said',
      rt.reach.slice(0, 3), [[['d1', '✓', ''], ['d2', '✗', '✓']], ['1 row unknown'], ['CW1', 'CW2']]),
    judge('RC2 two nodes Reached in one expression - a row walk each, the same node once', rt.reach[3], ['CW1', 'CW2']),
    judge('RC3 a column that Reaches a node added: the rows walked again judged against it; another column after - no row walk', rt.reach[4],
      [1, 0, ['✓', '✗'], false]),
    judge('W7 a pill of two columns, its inner one with steps: the walk asks its steps as the one-column pill does, and its value is read - not (Empty)',
      [rt.twoColumns[0], rt.twoColumns[2], rt.twoColumns[3]], [rt.twoColumns[1], ['d1, CW1'], true]),
    judge('C1 the same Color by on five kinds: a row one colour in all five (the value gives it); a category colour declared - all five draw it - the sheet\'s key cell too',
      ce, { first: [1, true], declared: ['#123456', '#123456', '#123456', '#123456', '#123456'] }),
    judge('SH1 the sheet\'s written start: walked from that node alone, along the ways its cells name (measures), its row its type; the cells read in the order they name each other',
      sh.walked, { asked: [[[], 0, 'ledger-entity:v1:WyJsb3Rfc2xvdCIseyJsb3QiOiJMMSIsInNsb3QiOiIwNSJ9XQ'], [['measures'], 1, 'ledger-entity:v1:WyJsb3Rfc2xvdCIseyJsb3QiOiJMMSIsInNsb3QiOiIwNSJ9XQ']], row: 'lot_slot',
        cells: { A1: 'L1 · 05', B1: '2', B2: '4', B3: '6', C1: '4', C2: '2', D1: '#CYCLE', E1: 'L1 · 05' } }),
    judge('SH2 a ring of cells: each #CYCLE and the ring; another kind\'s cell reference refused by name', sh.ring,
      { why: 'A cycle: D1 → D2 → D1', other: "Cell references are the sheet's - A1 reads a sheet's cell" }),
    judge('SH3 the key written anew walks once from the new node; written the same, no walk; a type the page has not - #NAME? and its reason, no walk',
      // a walk is two: the row walk and the cells' value walk
      sh.again, { walks: [2, 4, 4, 4], seeds: ['ledger-entity:v1:WyJsb3Rfc2xvdCIseyJsb3QiOiJMMiIsInNsb3QiOiIwNiJ9XQ', 'ledger-entity:v1:WyJsb3Rfc2xvdCIseyJsb3QiOiJMMiIsInNsb3QiOiIwNiJ9XQ'], refused: ['#NAME?', 'No function named nope'] }),
    judge('SH5 a sheet saved and reopened: its row type left to its key (not the first declared type), the same cells drawn', sh.reopen,
      { row: null, cells: ['L1 · 05', '2', '6'] }),
    judge('SH4 a sheet with no key yet draws its grid - its values written, the formulas empty - and walks nothing', sh.empty,
      { state: 'ready', walks: 0, cells: { C1: '4', B1: '' } }),
    judge('K7 a start read back from a save is named by its id - its keys; an id that is not an entity\'s as it is', ks, ['SYN-BW-103-11', 'W1']),
    judge('C2 seven categories seven colours in the order the rows show them, kept in the declaration; one more seen first - the seven keep theirs',
      cc, { seven: 7, order: '#1#2#3#4#5#6#7', kept: true, z: true }),
    judge('TT1 a point under the pointer: the tooltip of the root - its name, the value of each slot, the Tooltip slot; gone when it leaves; a cross table cell - its rows, the value they share, how many they do not',
      [tl.pointTip, tl.gone, tl.cellTip], [['D1', 'x: 1', 'y: 2', 'p: A'], 0, ['3', 'x: 3', 'p: 2 values']]),
    judge('LB1 labels: the Label by value on the marked only, on all, on none', [tl.marked, tl.all, tl.none],
      [[['D1', null], ['D2', 'B'], ['D3', null]], [['D1', 'A'], ['D2', 'B'], ['D3', 'A']], [['D1', null], ['D2', null], ['D3', null]]]),
    judge('DS1 a description under the title', tl.desc, ['Dies by x and y']),
    judge('LG1 the legend column only when the legend has something to draw - a cross table with no Color by none, with one its categories', tl.legends,
      [[true, []], [false, ['A', 'B']]]),
    judge('PK1 a pill\'s picker under its pill - opened, and after the part drew its pills again and a value was picked: under the new pill, not at 0,0',
      [pf.opened[0], pf.picked[0], pf.moved], [pf.opened[1], pf.picked[1], true]),
    judge('MC1 a slot of several columns: its values\' combination one category, column by column; an older one-column slot reads as a list of one', mc.pure,
      [['one', 'A, 1', ['A', '1']], 'p › x', 1, true]),
    judge('MC2 a cross table axis of two columns is a hierarchy: an outer value once along its run (rowspan), the inner each row', [mc.rowKeys, mc.heads],
      [['A, 1', 'A, 3', 'B, 3'], [['A', 2], ['1', 1], ['3', 1], ['B', 1], ['3', 1]]]),
    judge('MC3 Color by of two columns: a category a combination', mc.colours, ['A, 1', 'A, 3', 'B, 3']),
    judge('MC5 a column chip dragged onto another: the declaration\'s columns change places, the hierarchy\'s outer head the other column', [mc.reordered, mc.outer], [['x', 'p'], ['1', '3']]),
    judge('MC4 the picker\'s «+ Column» then a value writes the slot as its list of columns', mc.written, ['p', 'x']),
    judge('SP1 Shape by: a declared shape kept, a category not declared the next shape no category holds (the colours\' one rule), a mark of rows of one category its shape, of two the one shape',
      shp.pure, [[['A', 'circle', ['r1', 'r3']], ['B', 'diamond', ['r2']]], { A: 'circle' }, 'circle', 'circle', { x: 'p2', z: 'p1' }]),
    judge('SP2 a scatter draws each point its category\'s shape, the legend the same names, the shapes kept in the declaration; a legend name pressed marks its rows (one row - its node); a cross table holds no Shape by',
      [shp.drawn, shp.glyphs, shp.kept, shp.pressed, shp.crossSlots], [[['D1', 'circle'], ['D2', 'rect'], ['D3', 'circle']], ['circle', 'rect'], { A: 'circle', B: 'rect' }, ['D2'], false]),
    judge('TR1 Panel by splits the rows - two values in both, none (Empty) last; a hub in a panel carries the panel\'s value once; no slot - no panels',
      tr.pure, [[['A', ['r2']], ['B', ['r1', 'r2']], ['(Empty)', ['r3']]], [['lot', 'L1'], ['p', 'A']], [true, [['lot', 'L1'], ['p', 'A']]], null]),
    judge('TR2 a scatter in panels: a panel a value, its rows\' points, every panel on the same x and y extent', [tr.drawnPanels, tr.axes],
      [['A', 'B'], [['A', ['D1', 'D3'], 1, 3, 2, 9], ['B', ['D2'], 1, 3, 2, 9]]]),
    judge('TR3 a press in a panel marks its rows there - a marker of x 3 in A is D3, not D2; a cross table cell of two rows - their hub, the panel among its conditions (one row - its node)', [tr.marker, tr.cell],
      [[['D3', []]], [[[['x', '3'], ['(None)', ''], ['p', 'B']], ['D2', 'D4']]]]),
    judge('TR4 a panel\'s cell is painted as it is pressed - a marking holding the wafer leaves the wafer\'s cells in panels unmarked (two conditions, the rows)', tr.waferCells, [['A', false], ['B', false]]),
    judge('WO1 a kind says the base set slots it takes not - the sheet holds no Top/Bottom by, no Panel by', tr.sheetSlots, []),
    judge('RS1 a picture follows its own div: each trellis panel watched, its chart resized when its div changes', fl.resize, [2, 2]),
    judge('TT2 a tooltip says a slot\'s words once - the same column on Y and Top/Bottom by one line', fl.tip, ['M1', 'value: 4', 'step: S1']),
    judge('LB3 a label no longer than the room on its side, cut with «…»; unknown width - not cut', fl.labels,
      [[['a', 'right', 194, 'truncate'], ['b', 'left', 194, 'truncate']], [['a', 'right', null, null], ['b', 'left', null, null]]]),
    judge('LB4 the x ticks as many as the width holds, overlapping ones hidden; unknown width - as ECharts picks', fl.ticks, [2, true, true]),
    judge('TM1 a time the server sends is a time read; the tooltip and the filter say it as the grid does (local, no T · Z), a long value one line with its words in its tooltip',
      [sw.read, sw.tip, sw.filter], [['one', true], ['D1', `when: ${sw.stamp}`], [[[sw.stamp, sw.stamp, true]], [[sw.LONG, sw.LONG, true]]]]),
    judge('TM2 a cross table cell\'s rows reading one time - the tooltip says it as the grid does', sw.cellTip, ['2 rows', `when: ${sw.stamp}`]),
    judge('LB2 a label on the point\'s inner side - right in the left half, left in the right half (not under the legend)', sw.sides, [['a', 'right'], ['b', 'right'], ['c', 'left']]),
    judge('SI1 Top/Bottom N: the highest or lowest N by the slot, a number written as text a number, equal values by id, no number not among them; all or no slot - every mark',
      si.rule, [['b', 'c'], ['b'], ['a'], ['a', 'b', 'c'], ['a', 'b', 'c', 'd', 'e'], 5]),
    judge('SI2 a scatter showing the top 1 by x draws that point only and the status says how many are not shown', si.points, [['D2'], 'Top 1 by x · 2 not shown']),
    judge('SI3 a Marker by hub ranked by its rows folded (Avg of x: A 2, B 3)', si.hubs, [['B'], 'Top 1 by Avg(x) · 1 not shown']),
    // owner 10-14 «누르면 그 아래 행이 마킹»: the lot's rows, not the lot node (the 10-14 exception retired)
    judge('P6 a marker by lot pressed marks its rows - the hub of its wafers; the Marked table of wafers holds them', mp,
      { points: [['L1', 25, 30], ['L2', 25, 40]], marked: ['hub:["wafer",[["lot","L1"]]]'], lines: ['W1', 'W3'], said: '2 marked rows' }),
  ];
  return { lines, ran: names.length, names: [...names], failures: [...failures] };
}

console.log('\n[1] the Board layout, the limit and the table');
const base = await suite(REAL);
for (const l of base.lines) {
  console.log(`  ${l.ok ? 'PASS' : 'FAIL'} ${l.name}`);
  if (!l.ok) console.log(`        got  ${json(l.got)}\n        want ${json(l.want)}`);
}
let ran = base.ran;
let failed = base.failures.length;

const swap = (text, from, to) => {
  if (!text.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`);
  return text.split(from).join(to);
};
const MUTANTS = [
  { id: 'SR6', what: 'a reopened visual walked from a written node given the first declared row type (the code before, 18766)', catches: 'SH5 ', file: 'testbed/main.js', key: 'main',
    mutate: (t) => swap(t, "!d.row && !(d.start && d.start.node) ? { ...d, row: first } : d", "!d.row ? { ...d, row: first } : d") },
  { id: 'SR1', what: 'a written start is not walked - the marking only', catches: 'SH1 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, '    if (this.start && this.start.node) { const s = this.startNode(); return s && s.id ? { positive: [s.id] } : null; }\n', '') },
  { id: 'SR2', what: 'a kind of cells read like any other - a cell naming another refused', catches: 'SH1 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, 'this.oneValued, askMarked, Boolean(this.kind.cells), calc);', 'this.oneValued, askMarked, false, calc);') },
  { id: 'SR3', what: 'a sheet with no key yet draws nothing (Mark a start)', catches: 'SH4 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, '    if (!seeds && this.kind && this.kind.cells) {', '    if (false) {') },
  { id: 'SR4', what: 'the value walks read the declaration\'s encode - a sheet\'s cells (the ways they name) not walked', catches: 'SH1 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, 'async walkValues(key, slot = this.slotsHeld()[key]) {', 'async walkValues(key, slot = (this.decl.encode || {})[key]) {') },
  { id: 'SR5', what: 'the kind\'s own slots not read - the declaration\'s encode only', catches: 'SH1 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, '[s.key, s.slot || encode[s.key]]', '[s.key, encode[s.key]]') },
  { id: 'M1', what: 'an added part splits the first one, not the largest', catches: ['S5 ', 'G5 '], file: 'rnd_board/split_tree.js', key: 'tree',
    mutate: (t) => swap(t, 'ids.reduce((best, k) => (area(k) > area(best) ? k : best), ids[0])', 'ids[0]') },
  { id: 'M2', what: 'a dragged line has no floor', catches: 'S2 ', file: 'rnd_board/split_tree.js', key: 'tree',
    mutate: (t) => swap(t, 'const a = Math.min(Math.max(pxA + delta, min), total - min);', 'const a = pxA + delta;') },
  { id: 'M3', what: 'a docked part lands on the other side of the edge', catches: 'S1 ', file: 'rnd_board/split_tree.js', key: 'tree',
    mutate: (t) => swap(t, "const first = edge === 'left' || edge === 'top';", "const first = edge === 'right' || edge === 'bottom';") },
  { id: 'M4', what: 'a closed part\'s neighbour forgets its parent\'s share', catches: 'S4 ', file: 'rnd_board/split_tree.js', key: 'tree',
    mutate: (t) => swap(t, 'if (children.length === 1) return { ...children[0], size: node.size };', 'if (children.length === 1) return children[0];') },
  { id: 'M5', what: 'the limit\'s «none marked» branch taken when any one marking is empty', catches: 'L1 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, 'if (held.every((layer) => !layer.members))', 'if (held.some((layer) => !layer.members))') },
  { id: 'M6', what: 'a layer takes a marking\'s entries as nodes - a hub never its members', catches: 'L2 ', file: 'testbed/marking_layer.js', key: 'layer',
    mutate: (t) => swap(t, 'this.markings.entries(name).flatMap(([id]) => this.hubs.open(id))', 'this.markings.entries(name).map(([id]) => id)') },
  { id: 'M7', what: 'blank cells follow the sort\'s direction (first when descending)', catches: 'T1 ', file: 'testbed/kinds/table.js', key: 'table',
    mutate: (t) => swap(t, '      if (blank) return blank;\n', '') },
  { id: 'M8', what: 'a dock seats every part again (the page drawn anew)', catches: 'G3 ', file: 'rnd_board/grid_shell.js', key: 'shell',
    mutate: (t) => swap(t, '    this.root = edge === \'center\' ? swapLeaves(this.root, id, targetId) : dockLeaf(this.root, id, targetId, edge);\n    this.drawArea();',
      '    this.render({ ...this.layoutNow(), root: dockLeaf(this.root, id, targetId, edge) });') },
  { id: 'M65', what: 'a drop on a middle docks on an edge - no swap', catches: 'G3s ', file: 'rnd_board/grid_shell.js', key: 'shell',
    mutate: (t) => swap(t, "this.root = edge === 'center' ? swapLeaves(this.root, id, targetId) : dockLeaf(this.root, id, targetId, edge);", "this.root = dockLeaf(this.root, id, targetId, edge === 'center' ? 'right' : edge);") },
  { id: 'M66', what: 'a box has no middle - every drop an edge', catches: 'S7 ', file: 'rnd_board/split_tree.js', key: 'tree',
    mutate: (t) => swap(t, "return middle > 0 && best[1] >= middle ? 'center' : best[0];", 'return best[0];') },
  { id: 'M9', what: 'Save writes the visuals only (the code before) - the tree is lost', catches: 'G2 ', file: 'testbed/main.js', key: 'main',
    mutate: (t) => swap(t, "    const kept = { root: shell.layoutNow().root, visuals: declarations(), markings: markingList.get('list'), relations: relations.get('list'), marks, hubs: held };", '    const kept = declarations();') },
  { id: 'M11', what: 'a table line marks without the press\'s keys - Ctrl replaces too', catches: 'T2 ', file: 'testbed/kinds/table.js', key: 'table',
    mutate: (t) => swap(t, "tr.addEventListener('click', (event) => { event.stopPropagation(); ctx.mark(line.ids || [line.id], event); });",
      "tr.addEventListener('click', (event) => { event.stopPropagation(); ctx.mark(line.ids || [line.id], {}); });") },
  { id: 'M12', what: 'a part walked anew leaves its marking alone - the chain does not follow', catches: 'K2b ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, '    if (kept.length !== entries.length) this.markings.replace(this.writes, kept);', '') },
  { id: 'M13', what: 'a limit counted as a step of the chain - the Marked table a loop', catches: 'K3 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, '    if (!next.has(start)) next.set(start, []);',
      '    for (const from of markingsOf(d).limit) { if (!next.has(from)) next.set(from, []); next.get(from).push([d.id, emits]); }\n    if (!next.has(start)) next.set(start, []);') },
  { id: 'M14', what: 'Save leaves the markings out - a reopen has the default two', catches: 'K5 ', file: 'testbed/main.js', key: 'main',
    mutate: (t) => swap(t, ", markings: markingList.get('list'), relations", ', relations') },
  { id: 'M27', what: 'Save keeps no marks - a reopen starts unmarked', catches: 'K5 ', file: 'testbed/main.js', key: 'main',
    mutate: (t) => swap(t, '    for (const [name, entries] of Object.entries(saved.marks || {})) markings.replace(name, entries);', '') },
  { id: 'M15', what: 'a marking a docked panel writes is deleted too', catches: 'K4 ', file: 'testbed/main.js', key: 'main',
    mutate: (t) => swap(t, '      if (fixed.length) return', '      if (fixed.length && false) return') },
  { id: 'M16', what: 'a marked mark keeps its category colour, not its marking\'s', catches: 'K6 ', file: 'testbed/color_by.js', key: 'color',
    mutate: (t) => swap(t, '{ fill: markColor || c.fill, line: markColor || c.line,', '{ fill: c.fill, line: c.line,') },
  { id: 'M17', what: 'a hub\'s axis reads its rows without the reduce - no fold', catches: ['P2 ', 'P3 ', 'P4 '], file: 'testbed/units.js', key: 'units',
    mutate: (t) => swap(t, '  if (slot.reduce || isExpression(slot)) {', '  if (false) {') },
  { id: 'M18', what: 'a marker pressed marks its rows one by one - not what the press stands for', catches: 'P6 ', file: 'testbed/kinds/scatter.js', key: 'scatter',
    mutate: (t) => swap(t, '    if (pts.some((p) => p.where)) ctx.markHubs(', '    if (false) ctx.markHubs(') },
  { id: 'M19', what: 'a value record reads the row\'s first record for every unit - not its own', catches: 'P7 ', file: 'testbed/units.js', key: 'units',
    mutate: (t) => swap(t, 'const items = picks.map((k) => raw[k]);', 'const items = picks.map(() => raw[0]);') },
  { id: 'M24', what: 'a value record with a reduce still a unit a record - not folded by its edge', catches: 'P7 ', file: 'testbed/units.js', key: 'units',
    mutate: (t) => swap(t, '  if (!(recordSlot && recordSlot.reduce)) return ys.map((_, k) => [k]);', '  return ys.map((_, k) => [k]);') },
  { id: 'M20', what: 'a layer that does not spread - the members only', catches: ['Y2 ', 'Y4 '], file: 'testbed/marking_layer.js', key: 'layer',
    mutate: (t) => swap(t, '      for (const to of ways.next.get(queue.pop()) || [])', '      for (const to of (queue.pop(), []))') },
  { id: 'M21', what: 'a layer computed on every ask - no cache', catches: 'Y3 ', file: 'testbed/marking_layer.js', key: 'layer',
    mutate: (t) => swap(t, '    if (held && held.key === key) return held;', '') },
  { id: 'M22', what: 'a node not known said not marked', catches: ['Y2 ', 'Y4 '], file: 'testbed/marking_layer.js', key: 'layer',
    mutate: (t) => swap(t, "!this.steps().touched.has(id) ? null : false;", '!this.steps().touched.has(id) ? false : false;') },
  { id: 'M23', what: 'a map cell a die, not a coordinate - its press marks one', catches: 'Y6 ', file: 'testbed/kinds/map.js', key: 'map',
    mutate: (t) => swap(t, "  for (const { values, ids } of combosOf(rows, ['x', 'y'])) {", "  for (const { values, ids } of rows.flatMap((r) => combosOf([r], ['x', 'y']))) {") },
  { id: 'M25', what: 'the start\'s own walk brings rows through it - its record walk\'s other dies', catches: 'W1 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, 'if (own.length) got[0] = ', 'if (false) got[0] = ') },
  { id: 'M26', what: 'the row walk asks no route - every predicate', catches: 'W3 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, 'follow: [...new Set(routes.flatMap((r) => r.follow))].sort(),', 'follow: [],') },
  { id: 'M28', what: 'the root hands the colours no declared category colour - the palette colour always', catches: 'C1 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, 'paintRows(rows, { palette: this.palette(), declaration: this.decl,', 'paintRows(rows, { palette: this.palette(), declaration: { ...this.decl, colors: {} },') },
  { id: 'M29', what: 'a start no basket was handed is its raw id', catches: 'K7 ', file: 'walk/start_baskets.js', key: 'baskets',
    mutate: (t) => swap(t, '    const said = entityOfId(id);', '    const said = null;') },
  { id: 'M30', what: 'the colours given are not kept in the declaration - more categories deal them again', catches: 'C2 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, '    if (colors.any && Object.keys(colors.assigned).length) this.decl =', '    if (false) this.decl =') },
  { id: 'M31', what: 'the start is the marking\'s members only - its spread layer not taken', catches: 'W4 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, 'const spread = [...this.layers.layer(name).set].filter((id) => !negative.has(id));', 'const spread = [];') },
  { id: 'M32', what: 'no route from the start\'s type walked anyway, not said', catches: 'W5 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, 'if (away.length && !this.routes().length && this.vocabulary()) {', 'if (false) {') },
  { id: 'M33', what: 'the tooltip never put on the part', catches: 'TT1 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, '    if (this.tip.parentNode !== this.root) this.root.appendChild(this.tip);', '') },
  { id: 'M34', what: 'no label handed to the kind', catches: 'LB1 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, '    const label = (mark) => labelOf(mark,', '    const label = () => null; const unused = (mark) => labelOf(mark,') },
  { id: 'M35', what: 'the description not drawn', catches: 'DS1 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, "...(said ? [el('div', 'sf-part__desc', said)] : [])", '...[]') },
  { id: 'M36', what: 'a press always a hub of its rows - one row never its node', catches: 'W6 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, 'const press = ([where, ids]) => nodesOfPress(ids) ||', 'const press = ([where, ids]) => null ||') },
  { id: 'M38', what: 'no reason said when the marking holds another type only and no relation reaches the rows', catches: 'W6 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, 'marked: received.filter(marked).length, hidden, heldOnly,', 'marked: received.filter(marked).length, hidden,') },
  { id: 'M39', what: 'the kind handed every mark - Top/Bottom N not applied', catches: 'SI2 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, 'this.kind.model(showing.kept,', 'this.kind.model(units,') },
  { id: 'M40', what: 'the Top/Bottom by slot not folded for a hub - a hub reads nothing and none is shown', catches: 'SI3 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, '      folded(SHOW_SLOT), PANEL_SLOT]', '      SHOW_SLOT, PANEL_SLOT]') },
  { id: 'M41', what: 'equal values by id backwards', catches: 'SI1 ', file: 'testbed/show_items.js', key: 'show',
    mutate: (t) => swap(t, '(a.id < b.id ? -1 : a.id > b.id ? 1 : 0)', '(a.id < b.id ? 1 : a.id > b.id ? -1 : 0)') },
  { id: 'M42', what: 'a time read not said a time', catches: 'TM1 ', file: 'testbed/slot.js', key: 'slot',
    mutate: (t) => swap(t, "  const time = (r.value && typeof r.value === 'object' && typeof r.value.$datetime === 'string') || declared === 'datetime';", "  const time = false;") },
  { id: 'M43', what: 'the tooltip says a value as it came - the UTC text', catches: 'TM1 ', file: 'testbed/tooltip.js', key: 'tooltip',
    mutate: (t) => swap(t, 'return ctx.text ? ctx.text(key, read.value, isTimeRead(read)) : valueText(read.value, isTimeRead(read));', 'return String(read.value);') },
  { id: 'M44', what: 'a filter value as it came, no tooltip', catches: 'TM1 ', file: 'testbed/condition_editor.js', key: 'cond',
    mutate: (t) => swap(t, '      words.title = said;', '      words.title = \'\';') },
  { id: 'M45', what: 'every label right of its point', catches: 'LB2 ', file: 'testbed/kinds/scatter.js', key: 'scatter',
    mutate: (t) => swap(t, "(along(p.x) > mid ? 'left' : 'right')", "'right'") },
  { id: 'M46', what: 'no panels - Panel by drawn as one picture', catches: 'TR2 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, "const split = takes.has('panel') ? panelsOf(rows, this.decl) : null;", 'const split = null;') },
  { id: 'M47', what: 'a press in a panel marks without the panel - a cross table cell of the same x in another panel the same hub', catches: 'TR3 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, 'markHub: (where, ids, event) => this.markHub(withPanel(where, panel), ids, event),', 'markHub: (where, ids, event) => this.markHub(where, ids, event),') },
  { id: 'M48', what: 'each panel its own extent', catches: 'TR2 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, 'this.kind.model(marks[i], { ...modelCtx, extent })', 'this.kind.model(marks[i], { ...modelCtx })') },
  { id: 'M55', what: 'a kind\'s without not read - the sheet offered Top/Bottom by and Panel by', catches: 'WO1 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, 'PANEL_SLOT].filter((s) => !without.includes(s.key));', 'PANEL_SLOT];') },
  { id: 'M61', what: 'rows grouped in a cell lose their time - the tooltip says the UTC text', catches: 'TM2 ', file: 'testbed/tooltip.js', key: 'tooltip',
    mutate: (t) => swap(t, "const time = rows.some((r) => isTimeRead(r.reads[key])) ? { time: true } : {};", 'const time = {};') },
  { id: 'M62', what: 'the legend column by the kind - a cross table with a Color by draws no categories', catches: 'LG1 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, 'const legendHeld = Boolean(this.kind.units || encodeNow.color || (this.kind.points && encodeNow.shape));', 'const legendHeld = Boolean(this.kind.units);') },
  { id: 'M63', what: 'the legend column always - 160 empty beside a cross table', catches: 'LG1 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, 'const legendHeld = Boolean(this.kind.units || encodeNow.color || (this.kind.points && encodeNow.shape));', 'const legendHeld = true;') },
  { id: 'M64', what: 'the picker placed under the pill it opened from, drawn away or not - 0,0 after the part redraws', catches: 'PK1 ', file: 'testbed/picker.js', key: 'picker',
    mutate: (t) => swap(t, '      if (!at || at.isConnected !== false) return at;', '      return at;') },
  { id: 'M67', what: 'a slot of several columns read as its first only', catches: 'MC1 ', file: 'testbed/slot.js', key: 'slot',
    mutate: (t) => swap(t, '    if (cols.length === 1) return readSlot(index, inside, x, cols[0], oneValued, marked, cell, calc);', '    if (cols.length >= 1) return readSlot(index, inside, x, cols[0], oneValued, marked, cell, calc);') },
  { id: 'M68', what: 'a hierarchy\'s outer value told every row', catches: 'MC2 ', file: 'testbed/kinds/cross_table.js', key: 'cross',
    mutate: (t) => swap(t, '    if (last && last.at === at) last.n += 1; else', '    if (false) last.n += 1; else') },
  { id: 'M69', what: 'the picker writes one column over the slot - «+ Column» adds none', catches: 'MC4 ', file: 'testbed/picker.js', key: 'picker',
    mutate: (t) => swap(t, '      if (!many) { part.setSlot(key, col); return; }', '      { part.setSlot(key, col); return; }') },
  { id: 'M70', what: 'a chip dropped on another moves nothing', catches: 'MC5 ', file: 'testbed/picker.js', key: 'picker',
    mutate: (t) => swap(t, '          moved.splice(k, 0, it);', '          moved.splice(from, 0, it);') },
  { id: 'PWM1', what: 'a walk asks its first page only - the resume not followed', catches: 'PW1 ', file: 'testbed/part_walks.js', key: 'walks',
    mutate: (t) => swap(t, 'resume = res.body && res.body.more && res.body.more.resume;', 'resume = null;') },
  { id: 'PWM2', what: 'a cut walk in hand covers', catches: 'PW2 ', file: 'testbed/part_walks.js', key: 'walks',
    mutate: (t) => swap(t, 'if (!held || !held.complete) return false;', 'if (!held) return false;') },
  { id: 'PWM3', what: 'a walk in hand covers a type it did not carry', catches: 'PW2 ', file: 'testbed/part_walks.js', key: 'walks',
    mutate: (t) => swap(t, 'if (held.collect && (!ask.collect || !ask.collect.every((t) => held.collect.includes(t)))) return false;', '') },
  { id: 'PWM4', what: 'an edge end the answer did not carry left out - the way through it broken', catches: 'PW7 ', file: 'testbed/part_walks.js', key: 'walks',
    mutate: (t) => swap(t, 'if (id && !nodes.has(id)) nodes.set(', 'if (false) nodes.set(') },
  { id: 'PWM5', what: 'a slot of several columns asks one column\'s way', catches: 'W7 ', file: 'testbed/part_walks.js', key: 'walks',
    mutate: (t) => swap(t, 'for (const col of columnsOf(slot)) {', 'for (const col of [slot]) {') },
  { id: 'PWM6', what: 'a slot changed walks nothing - folded again only', catches: 'PW4 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, 'for (const key of changedSlots(slotsBefore, this.slotsHeld())) this.walkValues(key);', '') },
  { id: 'PWM7', what: 'a slot changed walks every slot again', catches: 'PW4 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, 'for (const key of changedSlots(slotsBefore, this.slotsHeld())) this.walkValues(key);', 'this.values = new Map(); this.valueWalks = []; for (const key of Object.keys(this.slotsHeld())) this.walkValues(key);') },
  { id: 'PWM8', what: 'the walks in hand not looked at - every slot change asks', catches: 'PW3 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, '[...this.values.values(), ...this.valueWalks].find((h) => covers(h, ask))', 'null') },
  { id: 'PWM9', what: 'the rows asked in one request past the seed cap', catches: 'PW5 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, 'chunks(ask.seeds, this.seedChunk)', '[ask.seeds]') },
  { id: 'PWM10', what: 'a slot\'s walk in flight not dropped by the next', catches: 'PW6 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, '  async walkValues(key, slot = this.slotsHeld()[key]) {\n    this.abortWalk(key);', '  async walkValues(key, slot = this.slotsHeld()[key]) {') },
  { id: 'PWM12', what: 'the slots of a load walked one after another', catches: 'PW8 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, 'await Promise.all([...Object.keys(this.slotsHeld()).map((key) => this.walkValues(key)), this.walkValues(RELATION_WALK, this.relationSlot())]);', 'for (const key of Object.keys(this.slotsHeld())) await this.walkValues(key);') },
  { id: 'PWM13', what: 'a start of the row type walked though the page holds its nodes', catches: 'PW9 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, 'if (own && !(seeds.aux || []).length && seeds.positive.every((id) => this.layers.graph.nodes.has(id))) {', 'if (false) {') },
  { id: 'PWM14', what: 'the ranking asked on every walk', catches: 'PW9 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, 'return { ...this.walkParams, ...own, propagation: false };', 'return { ...this.walkParams, ...own };') },
  { id: 'PWM15', what: 'the runs of a value walk asked one after another', catches: 'PW10 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, 'chunks(ask.seeds, this.seedChunk).map((some) => walkToEnd(this.fetchWalk,', 'chunks(ask.seeds, this.seedChunk).map((some, k) => walkToEnd(k ? (p) => new Promise((r) => setTimeout(r, 3000)).then(() => this.fetchWalk(p)) : this.fetchWalk,') },
  { id: 'PWM16', what: 'every walk asks no ranking - the walk box loses its ranked list', catches: 'PW11 ', file: 'rnd_board/api.js', key: 'api',
    mutate: (t) => swap(t, "if (propagation === false) query.set('propagation', 'false');", "query.set('propagation', 'false');") },
  { id: 'PWM17', what: 'a value walk folds again on every page', catches: 'PW12 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, 'control.signal, null)));', 'control.signal, () => this.refold())));') },
  { id: 'PWM18', what: 'a row walk in flight on the page not waited for - each part asks its own', catches: 'PW13 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, 'const coming = walks.find(', 'const coming = false && walks.find(') },
  { id: 'PWM19', what: 'the page\'s row walk in hand not taken by another part', catches: 'PW13 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, 'const held = walks.find(', 'const held = false && walks.find(') },
  { id: 'PWM20', what: 'a part that writes a marking walks no relations - the edges its marking spreads along not on the page', catches: 'W9 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, 'return this.writes && columns.length ? columns : null;', 'return null;') },
  { id: 'RM1', what: 'the node a Reach names not sent to the walk - every row unknown', catches: 'RC1 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, 'collect: ask.collect,\n        ...(ask.aux.length ? { aux: ask.aux } : {}) };', 'collect: ask.collect };') },
  { id: 'RM2', what: 'a walk judged against nothing covers a Reach - the judgment never asked', catches: 'RC3 ', file: 'testbed/part_walks.js', key: 'walks',
    mutate: (t) => swap(t, 'if ((ask.aux || []).length && !same(held.aux || [], ask.aux)) return false;', '') },
  { id: 'RM3', what: 'a column that Reaches a node added folds again only - its rows never judged', catches: 'RC3 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, 'if (walkAgain || this.reachTargets().join() !== reachBefore) {', 'if (walkAgain) {') },
  { id: 'RM4', what: 'two nodes Reached in one walk - the nearest answers for both', catches: 'RC2 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, '(targets.length ? targets : [null]).map((to) => ({ side, aux: to ? [to] : [] }))', '[{ side, aux: targets }]') },
  { id: 'HM1', what: 'the start own records walked a step - every predicate, its neighbours carried', catches: 'W1 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, 'hops: seeds.all || own ? 0 : Math.max(', 'hops: seeds.all || own ? 1 : Math.max(') },
  { id: 'PWM11', what: 'the walks not said on the status line', catches: 'PW3 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, 'walks: this.walkWords() };', 'walks: null };') },
  { id: 'M57', what: 'a panel\'s div not watched - its chart keeps the size it was drawn at', catches: 'RS1 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, '      this.watch(at, one);', '') },
  { id: 'M58', what: 'a tooltip line a slot - the same column twice', catches: 'TT2 ', file: 'testbed/tooltip.js', key: 'tooltip',
    mutate: (t) => swap(t, 'if (said !== null && !lines.has(words))', 'if (said !== null)').split('lines.set(words,').join('lines.set(k,') },
  { id: 'M59', what: 'a label as long as its words - cut by the plot\'s edge', catches: 'LB3 ', file: 'testbed/kinds/scatter.js', key: 'scatter',
    mutate: (t) => swap(t, 'position: side(p), ...fit(p),', 'position: side(p),') },
  { id: 'M60', what: 'the x ticks as many in a narrow panel as in a wide one', catches: 'LB4 ', file: 'testbed/kinds/scatter.js', key: 'scatter',
    mutate: (t) => swap(t, 'splitNumber: Math.max(2, Math.floor(plotW / 110))', 'splitNumber: undefined') },
  { id: 'M49', what: 'the panel condition appended again on every pass', catches: 'TR1 ', file: 'testbed/trellis.js', key: 'trellis',
    mutate: (t) => swap(t, 'return where.some(([w]) => w === words) ? where : [...where, ...panel.where];', 'return [...where, ...panel.where];') },
  { id: 'M50', what: 'the kind handed no shape - every point the one shape', catches: 'SP2 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, 'askMarked, label, shape, palette', 'askMarked, label, shape: null, palette') },
  { id: 'M51', what: 'the shapes given not kept - more categories deal them again', catches: 'SP2 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, 'if (shapes && shapes.any && Object.keys(shapes.assigned).length)', 'if (false)') },
  { id: 'M52', what: 'a category not declared given no shape', catches: 'SP1 ', file: 'testbed/shape_by.js', key: 'shape',
    mutate: (t) => swap(t, 'const assigned = assignLooks(seen, own, SHAPES);', 'const assigned = {};') },
  { id: 'M53', what: 'the scatter draws every point a circle', catches: 'SP2 ', file: 'testbed/kinds/scatter.js', key: 'scatter',
    mutate: (t) => swap(t, '...(p.shape ? { symbol: p.shape } : {}),', '') },
  { id: 'M10', what: 'the status counts a limit-dropped row as hidden by the filters', catches: 'L4 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, '    const shown = new Set(afterPart.kept);', '    const shown = new Set(limited);') },
];
const scored = await scoreMutants(MUTANTS, async (m) => {
  const copy = (await loadWithProbe(join(SRC, m.file), { mutate: m.mutate })).module;
  return suite({ ...REAL, [m.key]: copy });
}, { baselineRan: base.ran, baselineNames: base.names, title: '\n  [1] mutants - each must be caught by the check it names.' });
ran += MUTANTS.length;
failed += scored.wrong;

console.log(`\n${ran - failed} passed, ${failed} failed`);
console.log(`ASSERTIONS ${ran} ${failed}`);
if (failed) process.exit(1);
