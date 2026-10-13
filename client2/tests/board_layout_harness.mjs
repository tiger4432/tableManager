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
};
const { MarkingStore, SIGN } = await import('../src/rnd_board/marking_store.js');
const { HubBook, hubId } = await import('../src/testbed/hubs.js');
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
async function page(M, storage = null) {
  const doc = makeDoc('dark');
  const host = doc.createElement('div');
  doc.body.appendChild(host);
  const asked = [];
  const fetchImpl = async (url) => {
    const u = String(url);
    if (u.includes('/api/ledger/subgraph')) asked.push(u);
    const body = u.includes('/api/ledger/declaration') ? { entities: [{ type: 'wafer' }], predicates: [] }
      : u.includes('/api/ledger/subgraph') ? ANSWER : { nodes: [] };
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
  const lim = (markings, must, none) => M.visual.limitRows(ids, { markings, must, none }, (n) => marks[n], book);
  out.limit = [lim(['P', 'Q'], 'all', 'all'), lim(['P', 'Q'], 'any', 'all'), lim(['E'], 'all', 'all'), lim(['E'], 'all', 'empty'),
    lim(['E', 'Q'], 'all', 'all'), M.visual.limitRows(ids, null, (n) => marks[n], book)];
  out.hub = [lim(['H'], 'all', 'empty'), lim(['H', 'P'], 'all', 'empty')];
  // T1: the table's model - its columns by the encode, sorted both ways, blanks last, numbers by number
  const read = (v) => (v === null ? { state: 'empty' } : { state: 'one', value: v });
  const rows = [['W1', '30'], ['W2', '10'], ['W3', null], ['W4', '9']].map(([id, t]) => ({ id, label: id, reads: { col1: read(id), col3: read(t) } }));
  const model = (sort) => M.table.tableModel(rows, { marked: (id) => id === 'W2', declaration: { encode: { col3: TEMP, col1: NAME }, sort } });
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
    flyout: (() => { const banner = fourth.shell.partOf('banner'); banner.toggle(true); const names = walk(banner.host).filter((n) => String(n.className) === 'sf-flyout__it').map((n) => n.textContent); banner.toggle(false); return names; })() };
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
      p.add, { ids: ['table-1', 'crossTable-1', 'scatter-2'], kinds: ['table', 'crossTable', 'scatter'], active: 'scatter-2', firstPath: '[0,0]',
        scatterPath: '[0,1]', walked: 3, flyout: ['Table', 'Cross table', 'Scatter plot'] }),
    judge('L3 the Marked table: empty while nothing is picked; a hub picked - its members; N of M and the limit\'s drop, none hidden; a line pressed re-marks to it; a head sorts; the ground clears',
      p.marked, { emptyFirst: 0, viaHub: ['W1', 'W3'], counts: [2, 4, 2, 0], afterPress: ['W3'], sort: { key: 'col1', desc: false }, cleared: 0, emptyAgain: 0 }),
    judge('L4 a limited part counts the limit\'s drop apart: a marked row it leaves out is not hidden; a limiting marking changed, it folds again',
      { before: one.before, after: one.after }, { before: { rows: 1, of: 4, limit: 3, hidden: 0, marked: 1 }, after: ['W1', 'W4'] }),
    judge('T2 a table line pressed with Ctrl joins the pick; pressed alone it is the pick', [one.added, one.replaced], [['W2', 'W4'], ['W1']]),
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
    mutate: (t) => swap(t, 'if (held.every((entries) => !entries.length))', 'if (held.some((entries) => !entries.length))') },
  { id: 'M6', what: 'the limit reads a marking\'s entries as nodes - a hub never its members', catches: 'L2 ', file: 'testbed/visual_part.js', key: 'visual',
    mutate: (t) => swap(t, 'held[test]((entries) => holds(entries, book, id))', 'held[test]((entries) => entries.some(([e]) => e === id))') },
  { id: 'M7', what: 'blank cells follow the sort\'s direction (first when descending)', catches: 'T1 ', file: 'testbed/kinds/table.js', key: 'table',
    mutate: (t) => swap(t, '      if (blank) return blank;\n', '') },
  { id: 'M8', what: 'a dock seats every part again (the page drawn anew)', catches: 'G3 ', file: 'rnd_board/grid_shell.js', key: 'shell',
    mutate: (t) => swap(t, '    this.root = dockLeaf(this.root, id, targetId, edge);\n    this.drawArea();',
      '    this.render({ ...this.layoutNow(), root: dockLeaf(this.root, id, targetId, edge) });') },
  { id: 'M9', what: 'Save writes the visuals only (the code before) - the tree is lost', catches: 'G2 ', file: 'testbed/main.js', key: 'main',
    mutate: (t) => swap(t, '    const kept = { root: shell.layoutNow().root, visuals: declarations() };', '    const kept = declarations();') },
  { id: 'M11', what: 'a table line marks without the press\'s keys - Ctrl replaces too', catches: 'T2 ', file: 'testbed/kinds/table.js', key: 'table',
    mutate: (t) => swap(t, "tr.addEventListener('click', (event) => { event.stopPropagation(); ctx.mark([line.id], event); });",
      "tr.addEventListener('click', (event) => { event.stopPropagation(); ctx.mark([line.id], {}); });") },
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
