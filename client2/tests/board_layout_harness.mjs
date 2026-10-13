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
  units: await import('../src/testbed/units.js'),
  color: await import('../src/testbed/color_by.js'),
  layer: await import('../src/testbed/marking_layer.js'),
  map: await import('../src/testbed/kinds/map.js'),
  trend: await import('../src/walk/trend.js'),
  reach: await import('../src/walk/reach_table.js'),
};
const { MarkingStore, SIGN } = await import('../src/rnd_board/marking_store.js');
const { HubBook, hubId, holds } = await import('../src/testbed/hubs.js');
const { KeyedStore } = await import('../src/testbed/keyed_store.js');
const { Panel } = await import('../src/rnd_board/panel.js');

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
  markings.set('marking:lim', 'W4', SIGN.CASE);
  await settle();
  const after = part.model.lines.map((l) => l.id);
  // A line pressed: with Ctrl it joins the pick, without it is the pick.
  const press = (id, ctrlKey) => walk(part.host).filter((n) => n.tagName === 'TR' && n.children.length > 1)
    .find((tr) => tr.children[0]._text === id).dispatch('click', { ctrlKey, stopPropagation() {} });
  const picked = () => markings.entries('marking:pick').map(([id]) => id).sort();
  press('W4', true);
  const added = picked();
  press('W1', false);
  return { before, after, added, replaced: picked() };
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
  out.loop = { refused, kept: JSON.stringify(part(a).declaration()) === aWas, loop: part(a).loop, said,
    self: M.visual.chainLoop([{ id: 'S', start: { marking: m3 }, writes: m3 }]), limitIsNoStep: M.visual.chainLoop([{ id: 'T', start: { marking: 'marking:start' }, limit: { markings: [m3] }, writes: m3 }]) };
  // K5: Save, then a new page from it - the markings and the chain's declarations
  p.save();
  const again = await page(M, storage, chainAnswer);
  const decl = (q, id) => { const s = q.shell.partOf(id); if (!s) return null; const d = s.declaration(); return [d.start && d.start.marking, d.writes]; };
  const before2 = again.asked.length;
  if (again.shell.partOf(a)) again.shell.partOf(a).mark(['W2'], {});
  await settle();
  out.reopen = { labels: again.markingBook.list.get('list').map((m) => m.label), chain: [decl(again, a), decl(again, b), decl(again, c)],
    walks: seedsAsked(again.asked.slice(before2)) };
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
    const m = M.scatter.scatterModel(M.units.unitsOf(own, decl, Object.keys(encode), 'y'), { ...M.color.paintRows(own, { marked, palette: pal, declaration: decl }), palette: pal, declaration: decl });
    return { points: m.points.map((p) => [p.label, Math.round(p.x * 1000) / 1000, p.y, p.ids, p.marked]), several: m.several };
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
 *  table its members. */
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
  return { points, marked: markings.entries('marking:pick').map(([id]) => id), lines: table.model.lines.map((l) => l.id) };
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

/** The route (lead 10-14 «다른 다이라»): a bonding die d1 of BW (its sibling d2), bonded from c1 on CW1 (d2 from c2 on
 *  CW2). A part starting from d1 walks only its route, and its rows are the route's ends. */
async function routed(M) {
  const { entitySeedId } = await import('../src/rnd_board/api.js');
  const id = (type, key) => entitySeedId(type, { [type]: key });
  const [BW, CW1, CW2, d1, d2, c1, c2] = [['wafer', 'BW'], ['wafer', 'CW1'], ['wafer', 'CW2'], ['die', 'd1'], ['die', 'd2'], ['die', 'c1'], ['die', 'c2']].map(([t, k]) => id(t, k));
  const label = new Map([[BW, 'BW'], [CW1, 'CW1'], [CW2, 'CW2'], [d1, 'd1'], [d2, 'd2'], [c1, 'c1'], [c2, 'c2']]);
  const node = (nid) => ({ id: nid, type: nid === BW || nid === CW1 || nid === CW2 ? 'wafer' : 'die', label: label.get(nid), keys: {}, attributes: {} });
  const answer = { nodes: [BW, CW1, CW2, d1, d2, c1, c2].map(node),
    edges: [[d1, 'in_container', BW], [d2, 'in_container', BW], [d1, 'bonded_from', c1], [d2, 'bonded_from', c2], [c1, 'in_container', CW1], [c2, 'in_container', CW2]]
      .map(([source, predicate, target], i) => ({ id: `r${i}`, source, target, predicate, qualifiers: {} })), truncated: ANSWER.truncated };
  const vocabulary = { entities: [{ type: 'die' }, { type: 'wafer' }],
    predicates: [{ name: 'in_container', subjects: ['die'], object: { kind: 'entity_ref', types: ['wafer'] } }, { name: 'bonded_from', subjects: ['die'], object: { kind: 'entity_ref', types: ['die'] } }] };
  const CORE = { steps: [{ predicate: 'bonded_from', direction: 'outgoing' }, { predicate: 'in_container', direction: 'outgoing' }], value: { on: 'label', name: 'name' }, words: ['core wafer'] };
  const seat = async (decl, withVocabulary = true) => {
    const doc = makeDoc('dark');
    const markings = new MarkingStore();
    markings.set('marking:die', d1, SIGN.CASE);
    const asked = [];
    const part = new M.visual.VisualPart(doc.createElement('div'), { doc, markings, writes: null, start: decl.start, declaration: decl, vocabulary: withVocabulary ? () => vocabulary : undefined,
      kinds: { crossTable: (await import('../src/testbed/kinds/cross_table.js')).kind }, filters: new KeyedStore(), stats: new KeyedStore(), active: new KeyedStore(), hubs: new HubBook(), names: new Map(), charts: charts(),
      fetchWalk: async (params) => { asked.push([params.follow || null, params.hops || null]); return { ok: true, body: JSON.parse(JSON.stringify(answer)) }; } });
    part.mount();
    await settle();
    return { rows: part.model.rowKeys, total: part.model.total, asked, routes: part.routes().map((r) => r.chain.join('>')), part, labels: (part.rowIds || []).map((x) => label.get(x)).sort() };
  };
  const base = { id: 'B', part: 'visual', kind: 'crossTable', start: { marking: 'marking:die' }, system: null, filter: [] };
  const dies = await seat({ ...base, row: 'die', encode: { rows: CORE } });
  const all = await seat({ ...base, start: { marking: null }, row: 'die', encode: { rows: CORE } });
  const wafers = await seat({ ...base, row: 'wafer', encode: {} });
  const core = await seat({ ...base, row: 'wafer', encode: {}, route: wafers.part.routes()[1] });
  return { dies: [dies.rows, dies.total, dies.asked, dies.routes], all: [all.rows, all.total], wafers: [wafers.routes, wafers.labels], core: [core.labels, core.asked] };
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
    judge('G2b an older save (visuals by id) opens on the layout\'s tree, its visuals laid over, the chrome docked', p.older, { tree: true, x: true, docks: true }),
    judge('G5 each kind added: its id and kind, the largest split (the scatter, stacked: new on top), the new one active and walked; the add window lists them in order',
      p.add, { ids: ['table-1', 'crossTable-1', 'scatter-2', 'map-1'], kinds: ['table', 'crossTable', 'scatter', 'map'], active: 'map-1', firstPath: '[0,0]',
        scatterPath: '[0,1]', walked: 4, flyout: ['Table', 'Cross table', 'Scatter plot', 'Map'] }),
    judge('L3 the Marked table: empty while nothing is picked; a hub picked - its members; N of M and the limit\'s drop, none hidden; a line pressed re-marks to it; a head sorts; the ground clears',
      p.marked, { emptyFirst: 0, viaHub: ['W1', 'W3'], counts: [2, 4, 2, 0], afterPress: ['W3'], sort: { key: 'col1', desc: false }, cleared: 0, emptyAgain: 0 }),
    judge('L4 a limited part counts the limit\'s drop apart: a marked row it leaves out is not hidden; a limiting marking changed, it folds again',
      { before: one.before, after: one.after }, { before: { rows: 1, of: 4, limit: 3, hidden: 0, marked: 1 }, after: ['W1', 'W4'] }),
    judge('T2 a table line pressed with Ctrl joins the pick; pressed alone it is the pick', [one.added, one.replaced], [['W2', 'W4'], ['W1']]),
    judge('K1 markings added: the next free names, «Marking (n)», each its own colour', k.added,
      { names: ['marking:3', 'marking:4', 'marking:5'], labels: ['Start', 'Pick', 'Marking (3)', 'Marking (4)', 'Marking (5)'], colours: true }),
    judge('K1b a chain declared: B walks from what A marks, C from what B marks', k.built,
      { b: ['W2', 'W3'], c: ['W2', 'W3', 'W4'], held: [['W2'], ['W2', 'W3'], ['W3', 'W4']] }),
    judge('K2 A marks again: B walks once from it, its marking keeps what its new data holds, so C walks once from that - and its marking the same',
      k.chain, { walks: ['W1', 'W2'], b: ['W1', 'W2'], c: ['W2', 'W3'], held: [['W1'], ['W2'], ['W3']] }),
    judge('K2b the same chain seated alone: B and C walk once each, in turn; each marking keeps what its part\'s new data holds',
      sc, { walked: ['B:W1', 'C:W2'], held: [['W1'], ['W2'], ['W3']] }),
    judge('K3 a loop of markings refused and named, the declaration kept; a part walking from what it writes is one; a limit is not a step',
      k.loop, { refused: false, kept: true, loop: ['marking:3', 'table-2', 'marking:4', 'table-3', 'marking:5', 'table-1', 'marking:3'],
        said: ['Refused - a loop: Marking (3) → wafer → Marking (4) → wafer → Marking (5) → wafer → Marking (3)'],
        self: ['marking:3', 'S', 'marking:3'], limitIsNoStep: null }),
    judge('K5 Save keeps the markings and the chain; a new page from it follows the chain; an older save opens on the default markings',
      { ...k.reopen, olderSave: k.olderSave }, { labels: ['Start', 'Pick', 'Marking (3)', 'Marking (4)', 'Marking (5)'],
        chain: [['marking:start', 'marking:3'], ['marking:3', 'marking:4'], ['marking:4', 'marking:5']], walks: ['W2'], olderSave: ['Start', 'Pick'] }),
    judge('K4 a marking deleted: its users named first; the part writing it writes none, the part walking from it walks from All (once), a limit loses it; the start row\'s marking not deleted, named; a new one takes the next free name',
      k.deleted, { shown: ['marking:start', 'marking:pick', 'marking:3', 'marking:4', 'marking:5'], ask: ['Used by Marked, wafer, wafer'],
        after: ['marking:start', 'marking:pick', 'marking:3', 'marking:5', 'marking:6'], b: ['marking:3', null], c: [null, 'marking:5'],
        limit: ['marking:pick'], walks: ['type:wafer'], kept: ['Not deleted - used by start'] }),
    judge('K6 a marking\'s colour is its marked lines\' and points\'', k.colour, { line: '#123456', unmarked: true, marked: '#123456' }),
    judge('P1 Marker by none: a point a node; a node with several x and no reduce not drawn', mk.none,
      { points: [['W1', 30, 5, ['W1'], false], ['W2', 10, 5, ['W2'], false], ['W4', 40, 7, ['W4'], false]], several: 1 }),
    judge('P2 Marker by lot: a point a lot - x the Avg of every value of its rows (not of each row\'s); y without a reduce its one value, several not drawn; marked when a row of it is',
      mk.lot, { points: [['L1', 25.333, 5, ['W1', 'W3'], true]], several: 1 }),
    judge('P3 Marker by lot and product: a point each combination, its words both; x the Count', mk.two,
      { points: [['L1 · A', 1, 5, ['W1'], false], ['L2 · A', 1, 5, ['W2'], false], ['L1 · B', 2, 5, ['W3'], false], ['L2 · B', 1, 7, ['W4'], false]], several: 0 }),
    judge('P4 Latest: the newest value of the marker\'s rows; Avg on y', mk.latest,
      { points: [['L1', 26, 5, ['W1', 'W3'], false], ['L2', 40, 6, ['W2', 'W4'], false]], several: 0 }),
    judge('P5 a marker is the hub the cross table names (hubId of the row type and the values by their words); the slots - Marker by held and the next, the axes folding',
      [mk.hub, mk.slots], [[hubId('wafer', [['lot', 'L1']]), hubId('wafer', [['lot', 'L2']])],
        [['x', 'y', 'marker1', 'color'], ['x*', 'y*', 'marker1', 'marker2', 'color']]]),
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
    judge('W1 a start of the row type is its own row: d1 alone - its one core wafer, the walk asking the slot\'s predicates and steps; the route die to die the seed alone (a simple path stops at two types)',
      rt.dies, [['CW1'], 1, [[['bonded_from', 'in_container'], 2]], ['die']]),
    judge('W2 from All every die of the type (the route only from a start)', rt.all, [['CW1', 'CW2', '(Empty)'], 4]),
    judge('W3 die to wafer: the shortest route its own wafer; the route with the bonded_from loop the core wafer, the walk asking that route',
      [rt.wafers, rt.core], [[['die>wafer', 'die>die>wafer'], ['BW']], [['CW1'], [[['in_container', 'bonded_from'], 2]]]]),
    judge('P6 a marker pressed marks its hub whole - the Marked table its members', mp,
      { points: [['L1', 25, 30], ['L2', 25, 40]], marked: [hubId('wafer', [['lot', 'L1']])], lines: ['W1', 'W3'] }),
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
    mutate: (t) => swap(t, '    this.root = dockLeaf(this.root, id, targetId, edge);\n    this.drawArea();',
      '    this.render({ ...this.layoutNow(), root: dockLeaf(this.root, id, targetId, edge) });') },
  { id: 'M9', what: 'Save writes the visuals only (the code before) - the tree is lost', catches: 'G2 ', file: 'testbed/main.js', key: 'main',
    mutate: (t) => swap(t, "    const kept = { root: shell.layoutNow().root, visuals: declarations(), markings: markingList.get('list'), relations: relations.get('list') };", '    const kept = declarations();') },
  { id: 'M11', what: 'a table line marks without the press\'s keys - Ctrl replaces too', catches: 'T2 ', file: 'testbed/kinds/table.js', key: 'table',
    mutate: (t) => swap(t, "tr.addEventListener('click', (event) => { event.stopPropagation(); ctx.mark([line.id], event); });",
      "tr.addEventListener('click', (event) => { event.stopPropagation(); ctx.mark([line.id], {}); });") },
  { id: 'M12', what: 'a part walked anew leaves its marking alone - the chain does not follow', catches: 'K2b ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, '    if (kept.length !== entries.length) this.markings.replace(this.writes, kept);', '') },
  { id: 'M13', what: 'a limit counted as a step of the chain - the Marked table a loop', catches: 'K3 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, '    if (!next.has(start)) next.set(start, []);',
      '    for (const from of markingsOf(d).limit) { if (!next.has(from)) next.set(from, []); next.get(from).push([d.id, emits]); }\n    if (!next.has(start)) next.set(start, []);') },
  { id: 'M14', what: 'Save leaves the markings out - a reopen has the default two', catches: 'K5 ', file: 'testbed/main.js', key: 'main',
    mutate: (t) => swap(t, ", markings: markingList.get('list'), relations", ', relations') },
  { id: 'M15', what: 'a marking a docked panel writes is deleted too', catches: 'K4 ', file: 'testbed/main.js', key: 'main',
    mutate: (t) => swap(t, '      if (fixed.length) return', '      if (fixed.length && false) return') },
  { id: 'M16', what: 'a marked mark keeps its category colour, not its marking\'s', catches: 'K6 ', file: 'testbed/color_by.js', key: 'color',
    mutate: (t) => swap(t, '{ fill: markColor || c.fill, line: markColor || c.line,', '{ fill: c.fill, line: c.line,') },
  { id: 'M17', what: 'a hub\'s axis reads its rows without the reduce - no fold', catches: ['P2 ', 'P3 ', 'P4 '], file: 'testbed/units.js', key: 'units',
    mutate: (t) => swap(t, '  if (slot.reduce || isExpression(slot)) {', '  if (false) {') },
  { id: 'M18', what: 'a marker pressed marks its id as a node - the hub never put, the Marked table empty', catches: 'P6 ', file: 'testbed/kinds/scatter.js', key: 'scatter',
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
  { id: 'M25', what: 'the rows every node of the row type the walk reached - not the route\'s ends', catches: 'W1 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, '    if (this.walkedRoute && this.walkedSeeds) return routeEnds(', '    if (false) return routeEnds(') },
  { id: 'M26', what: 'the walk asks no route - every predicate, the default steps', catches: ['W1 ', 'W3 '], file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, '{ ...base, ...along, nodeId:', '{ ...base, nodeId:') },
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
