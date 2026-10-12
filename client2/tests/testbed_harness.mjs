// The visual testbed (lead aca803a7a, d1b3c1b7f, 5835e6714): the root visual part and its kinds, the one filter, the hubs,
// the reduces against the server's walk fold (contracts/walk_aggregate), the page's save and reopen. Every subject is
// IMPORTED; the page around it is the board's document stub (tests/lib/board_dom.mjs) and a recording chart.
//
// CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
import { readFileSync, existsSync, readdirSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';
import { makeDoc, walk } from './lib/board_dom.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src');
const TB = join(SRC, 'testbed');
const ROOT = join(HERE, '..', '..');

const REAL = {
  aggregate: await import('../src/testbed/aggregate.js'),
  slot: await import('../src/testbed/slot.js'),
  filter: await import('../src/testbed/filter.js'),
  hubs: await import('../src/testbed/hubs.js'),
  scatter: await import('../src/testbed/kinds/scatter.js'),
  cross: await import('../src/testbed/kinds/cross_table.js'),
  visual: await import('../src/testbed/visual_part.js'),
  status: await import('../src/testbed/status_part.js'),
  picker: await import('../src/testbed/picker.js'),
  main: await import('../src/testbed/main.js'),
  palette: await import('../src/testbed/palette.js'),
};
const { MarkingStore, SIGN } = await import('../src/rnd_board/marking_store.js');
const { indexGraph, routesFrom } = await import('../src/walk/reach_table.js');
const { KeyedStore } = await import('../src/testbed/keyed_store.js');

// ── the walk: six wafers, two lots, two measured quantities ──
const T0 = '2026-10-01T00:00:00Z';
const T1 = '2026-10-02T00:00:00Z';
const wafer = (id, attrs = {}) => ({ id, type: 'wafer', label: id, keys: { wafer: id }, attributes: attrs });
const ANSWER = {
  nodes: [wafer('W1', { product: 'A' }), wafer('W2', { product: 'B' }), wafer('W3', { product: ['A', 'B'] }), wafer('W4', { product: 'A' }),
    wafer('W5', { product: 'B' }), wafer('W6', {}),
    { id: 'L1', type: 'lot', label: 'L1', keys: { lot: 'L1' }, attributes: {} }, { id: 'L2', type: 'lot', label: 'L2', keys: { lot: 'L2' }, attributes: {} },
    { id: 'QT', type: 'quantity', label: 'temp', keys: { quantity: 'temp' }, attributes: {} },
    { id: 'QP', type: 'quantity', label: 'press', keys: { quantity: 'press' }, attributes: {} }],
  edges: [
    ...['W1', 'W2', 'W3'].map((w) => ({ source: w, target: 'L1', predicate: 'in_lot', qualifiers: {} })),
    ...['W4', 'W5'].map((w) => ({ source: w, target: 'L2', predicate: 'in_lot', qualifiers: {} })),
    { source: 'W1', target: 'QT', predicate: 'measures', qualifiers: { value: '10' }, occurred_at: T0 },
    { source: 'W2', target: 'QT', predicate: 'measures', qualifiers: { value: '20' }, occurred_at: T0 },
    { source: 'W3', target: 'QT', predicate: 'measures', qualifiers: { value: '30' }, occurred_at: T0 },
    { source: 'W3', target: 'QT', predicate: 'measures', qualifiers: { value: '34' }, occurred_at: T1 },
    { source: 'W4', target: 'QT', predicate: 'measures', qualifiers: { value: '40' }, occurred_at: T0 },
    { source: 'W5', target: 'QT', predicate: 'measures', qualifiers: { value: '50' }, occurred_at: T0 },
    ...[['W1', '1'], ['W2', '2'], ['W3', '3'], ['W4', '4'], ['W5', '5']].map(([w, v]) => ({ source: w, target: 'QP', predicate: 'measures', qualifiers: { value: v }, occurred_at: T0 })),
  ],
  truncated: { nodes: false, edges: false, depth: false, claims: false, actions: false, reason: null },
};
const temp = { steps: [{ predicate: 'measures', direction: 'outgoing' }], end: 'QT', value: { on: 'edge', name: 'value' }, words: ['temp · value'] };
const press = { steps: [{ predicate: 'measures', direction: 'outgoing' }], end: 'QP', value: { on: 'edge', name: 'value' }, words: ['press · value'] };
const lot = { steps: [{ predicate: 'in_lot', direction: 'outgoing' }], value: { on: 'label', name: 'name' }, words: ['lot'] };
const product = { steps: [], value: { on: 'node', name: 'product' }, words: ['product'] };
const WAFERS = ['W1', 'W2', 'W3', 'W4', 'W5', 'W6'];

// ── a recording chart and a page ──
function chartsRecorder() {
  const made = [];
  return { made, init: (el) => { const c = { el, option: null, handlers: {}, actions: [], setOption(o) { this.option = o; }, dispatchAction(a) { this.actions.push(a); },
    on(name, fn) { this.handlers[name] = fn; }, getZr() { return { on() {} }; }, resize() {}, dispose() { this.disposed = true; } }; made.push(c); return c; } };
}
const settle = async () => { for (let i = 0; i < 10; i += 1) await new Promise((r) => setTimeout(r, 0)); };

/** A visual seated on a stub document, its walk answered by `answer` (a function of the params, or one answer). */
function seat(M, decl, { answer = ANSWER, markings = new MarkingStore(), filters = new KeyedStore({ 'filter:1': [] }), charts = chartsRecorder(),
  stats = new KeyedStore(), hubs = new M.hubs.HubBook(), asked = [], kinds = {} } = {}) {
  const doc = makeDoc('dark');
  const host = doc.createElement('div');
  const fetchWalk = async (params) => { asked.push(params); return { ok: true, body: typeof answer === 'function' ? answer(params) : JSON.parse(JSON.stringify(answer)) }; };
  const part = new M.visual.VisualPart(host, { doc, markings, reads: decl.reads, writes: decl.writes, start: decl.start, declaration: decl,
    kinds: { scatter: M.scatter.kind, crossTable: M.cross.kind, ...kinds }, fetchWalk, filters, stats, active: new KeyedStore(), hubs, names: new Map(), charts, theme: 'dark' });
  part.mount();
  return { part, host, doc, markings, filters, charts, stats, hubs, asked };
}
const scatterDecl = (extra = {}) => ({ id: 'S1', part: 'visual', kind: 'scatter', row: 'wafer', start: { marking: null }, system: 'filter:1', filter: [],
  encode: { x: temp, y: press, color: product }, reads: 'marking:pick', writes: 'marking:pick', ...extra });
const crossDecl = (extra = {}) => ({ id: 'C1', part: 'visual', kind: 'crossTable', row: 'wafer', start: { marking: null }, system: 'filter:1', filter: [],
  encode: { rows: lot, columns: product, cells: { ...press, reduce: 'Avg' } }, reads: 'marking:pick', writes: 'marking:pick', ...extra });

// ── the measurements ──
async function measure(M) {
  const out = {};
  const { fold } = M.aggregate;
  // T1: the server's walk fold, vector by vector - each group's values (plural flattened) folded here
  const vectors = JSON.parse(readFileSync(join(ROOT, 'contracts', 'walk_aggregate', 'vectors.json'), 'utf8')).vectors;
  out.contract = vectors.map((v) => {
    const groups = new Map();
    for (const n of v.nodes) {
      const key = v.group_by === 'type' ? [n.type] : [].concat((n.attributes || {})[v.group_by]);
      for (const k of key) { if (!groups.has(k)) groups.set(k, []); groups.get(k).push(n); }
    }
    const measures = [].concat(v.measure);
    const got = [...groups.keys()].sort().map((k) => {
      const nodes = groups.get(k);
      const value = Object.fromEntries(measures.map((m) => {
        const [name, of] = m.split(':');
        if (!of) return [m, nodes.length];
        const reads = nodes.flatMap((n) => {
          const said = (n.attributes || {})[of];
          const pred = (n.predicates || []).find((p) => p.predicate === of);
          return said !== undefined ? [{ value: said }] : pred ? [{ value: pred.count }] : [];
        });
        return [m, fold(name, reads).value];
      }));
      return { key: k, n: nodes.length, value };
    });
    return [v.name, JSON.stringify(got) === JSON.stringify(v.groups.map(({ key, n, value }) => ({ key, n, value })))];
  }).filter(([, ok]) => !ok).map(([name]) => name);
  // T2: Latest
  const t = (iso) => Date.parse(iso);
  out.latest = [fold('Latest', [{ value: 1, t: t(T0) }, { value: 2, t: t(T1) }]).value, fold('Latest', [{ value: 1, t: t(T1) }, { value: 2, t: t(T1) }]),
    fold('Latest', [{ value: 7, t: null }]).value, fold('Latest', [{ value: 1, t: null }, { value: 2, t: null }]).value, fold('Avg', []).value, fold('Median', [{ value: '1' }, { value: 'x' }])];
  // T3: a slot read
  const index = indexGraph(ANSWER);
  const inside = M.visual.insideOf(ANSWER);
  const { readSlot } = M.slot;
  out.reads = [readSlot(index, inside, 'W1', temp).state, readSlot(index, inside, 'W3', temp).state, readSlot(index, inside, 'W3', temp, true).value,
    readSlot(index, inside, 'W3', { ...temp, reduce: 'Max' }).value, readSlot(index, inside, 'W6', temp).state, readSlot(index, inside, 'NOPE', temp).state,
    readSlot(index, inside, 'W3', product).state, M.slot.categoriesOf(readSlot(index, inside, 'W3', product))];
  // T4: the filter
  const { keepNodes, valuePasses } = M.filter;
  const range = { row: 'wafer', ...press, range: { min: 2, max: 4 }, empty: false };
  const values = { row: 'wafer', ...product, values: ['A'], empty: true };
  out.filter = [keepNodes(index, inside, WAFERS, [range]).kept, keepNodes(index, inside, WAFERS, [range, values]).kept,
    keepNodes(index, inside, WAFERS, [values]).kept, keepNodes(index, inside, ['L1', 'W1'], [{ ...range, range: { min: 99 } }]).kept,
    valuePasses({ period: { from: '2026-10-01', to: '2026-10-02' } }, '2026-10-01T12:00:00Z'), valuePasses({ period: { from: '2026-10-01', to: '2026-10-02' } }, '2026-10-02T00:00:00Z')];
  // T5 / T6: the scatter model, its option, a drag
  const rowsOf = (ids, slots) => ids.map((id) => ({ id, label: id, reads: Object.fromEntries(Object.entries(slots).map(([k, s]) => [k, readSlot(index, inside, id, s)])) }));
  const marked = new Set(['W1', 'W2']);
  const model = M.scatter.scatterModel(rowsOf(WAFERS, { x: temp, y: press, color: product }), { marked: (id) => marked.has(id), theme: 'dark' });
  const p1 = model.points.find((p) => p.id === 'W1');
  const p4 = model.points.find((p) => p.id === 'W4');
  out.scatter = { drawn: model.points.map((p) => p.id), notDrawn: model.notDrawn, several: model.several, kinds: [model.xKind, model.yKind],
    marked: p1.fill, dimmed: p4.fill, legend: model.legend.map((l) => [l.name, l.dim, l.ids]) };
  const option = M.scatter.scatterOption(model, 'dark');
  out.drag = [M.scatter.idsInRange(model, option, [[15, 45], [1.5, 4.5]]), M.scatter.idsInRange(model, option, [[15, 45], [3.5, 4.5]]),
    M.scatter.idsInRange(model, option, [[0, 5], [0, 1]])];
  // T7: the cross table
  const crossRows = WAFERS.map((id) => ({ id, reads: { rows: readSlot(index, inside, id, lot), columns: readSlot(index, inside, id, product) },
    raw: { cells: index.out.get(id) ? index.out.get(id).filter((e) => e.target === 'QP').map((e) => ({ value: e.qualifiers.value, t: null })) : [] } }));
  const ct = M.cross.crossModel(crossRows, { marked: (id) => id === 'W1', reduce: 'Avg' });
  out.cross = { rows: ct.rowKeys, cols: ct.colKeys, grid: ct.grid.map((line) => line.map((c) => [c.value, c.ids, c.marked])), rowTotals: ct.rowTotals, colTotals: ct.colTotals, total: ct.total };
  // T8: hubs
  const book = new M.hubs.HubBook();
  const h = book.put(M.hubs.hubId('wafer', [['lot', 'L1']]), ['W1', 'W2', 'W3']);
  out.hubs = [M.hubs.seedsOf([[h, SIGN.CASE], ['W2', SIGN.CONTROL], ['W9', SIGN.CONTROL]], book), M.hubs.holds([[h, SIGN.CASE]], book, 'W3'), M.hubs.holdsOf ? 1 : 0, M.hubs.hubWords(h)];
  // T16: the picker's routes are the walk table's
  out.routes = JSON.stringify(M.picker.routeChoices(index, WAFERS).slice(1)) === JSON.stringify(routesFrom(index, WAFERS));
  return out;
}

async function parts(M) {
  const out = {};
  // T9a: All walks the row type described; the rows, the counts, the chart drawn
  const a = seat(M, scatterDecl());
  await settle();
  out.allAsked = a.asked.map((p) => [p.seed_type || null, p.nodeId || null]);
  out.allStats = (({ rows, of, system, part, marked, columns, source, cut }) => ({ rows, of, system, part, marked, columns, source, cut }))(a.stats.get('S1'));
  const chart = a.charts.made[a.charts.made.length - 1];
  out.drawnPoints = chart.option.series[0].data.length;
  // T9b: a drag marks what the rectangle holds, replacing what was marked; the chart redraws with the marked bright
  a.markings.set('marking:pick', 'W5', SIGN.CASE);
  await settle();
  a.charts.made[a.charts.made.length - 1].handlers.brushEnd({ areas: [{ coordRange: [[15, 45], [1.5, 4.5]] }] });
  await settle();
  out.dragMarked = a.markings.entries('marking:pick').map(([id]) => id).sort();
  out.dragStats = a.stats.get('S1').marked;
  // T9c: a cross cell marks its hub; the scatter shows its members marked
  const c = seat(M, crossDecl(), { markings: a.markings, hubs: a.hubs, stats: a.stats, filters: a.filters });
  await settle();
  const cell = walk(c.host).filter((n) => n.tagName === 'TD' && n.listeners && n.listeners.click)[0];
  cell.listeners.click[0]({});
  await settle();
  const held = a.markings.entries('marking:pick');
  out.hubMark = [held.length, M.hubs.isHubId(held[0][0]), a.hubs.membersOf(held[0][0]).sort()];
  const again = a.charts.made[a.charts.made.length - 1].option.series[0].data.filter((d) => d.itemStyle.color === M.palette.categoryColor(0)[0] || d.itemStyle.color === M.palette.categoryColor(1)[0]).map((d) => d.id).sort();
  out.hubShown = again;
  // T9d: the system filter's start side - a dropped start node, the walk taken again from the kept ones
  const markings = new MarkingStore();
  markings.set('marking:start', 'W1', SIGN.CASE);
  markings.set('marking:start', 'W4', SIGN.CASE);
  const filters = new KeyedStore({ 'filter:1': [{ row: 'wafer', ...press, range: { min: 3 }, empty: false }] });
  const d = seat(M, scatterDecl({ start: { marking: 'marking:start' } }), { markings, filters });
  await settle();
  out.startSide = { asked: d.asked.map((p) => p.positive), startDropped: d.stats.get('S1').startDropped, system: d.stats.get('S1').system };
  // T9e: received side and the part's own filter count apart; a marked node they hide is said
  const m2 = new MarkingStore();
  m2.set('marking:pick', 'W4', SIGN.CASE);
  const f2 = new KeyedStore({ 'filter:1': [{ row: 'wafer', ...press, range: { min: 2 }, empty: false }] });
  const e = seat(M, scatterDecl({ filter: [{ row: 'wafer', ...product, values: ['B'], empty: false }] }), { markings: m2, filters: f2 });
  await settle();
  out.twoLayers = (({ rows, of, system, part, hidden }) => ({ rows, of, system, part, hidden }))(e.stats.get('S1'));
  // T10: two scatters on one page share the marking and nothing else
  const shared = new MarkingStore();
  const oneCharts = chartsRecorder();
  const s1 = seat(M, scatterDecl({ id: 'S1' }), { markings: shared, charts: oneCharts });
  await settle();
  const s1Chart = oneCharts.made[oneCharts.made.length - 1];
  const s2 = seat(M, scatterDecl({ id: 'S2', encode: { x: press, y: temp } }), { markings: shared, charts: oneCharts });
  await settle();
  const s2Chart = oneCharts.made[oneCharts.made.length - 1];
  const before = oneCharts.made.length;
  s1.part.setSlot('color', null);
  await settle();
  out.twoParts = [Object.keys(s1.part.declaration().encode).sort(), Object.keys(s2.part.declaration().encode).sort(),
    oneCharts.made.length - before, Boolean(s1Chart.disposed), Boolean(s2Chart.disposed), s1Chart.el !== s2Chart.el];
  // T11: a kind added - the root draws it with no change of its own
  const stub = { name: 'list', label: 'List', slots: [{ key: 'v', label: 'Value' }], model: (rows) => ({ n: rows.length }),
    render: (body, model, ctx) => { const p = ctx.doc.createElement('p'); p.textContent = `rows ${model.n}`; body.append(p); return { resize() {}, dispose() {} }; } };
  const k = seat(M, { ...scatterDecl({ id: 'K1', kind: 'list' }), encode: { v: temp } }, { kinds: { list: stub } });
  await settle();
  out.kindAdd = walk(k.host).filter((n) => n.tagName === 'P').map((n) => n.textContent);
  // T13 / T17: the status words, a cut walk only when an axis says so
  out.status = [M.status.statusWords({ rows: 4, of: 6, system: 1, part: 1, marked: 2, hidden: 1, columns: 3, source: 'wafer', cut: false }),
    M.status.statusWords({ rows: 1, of: 1, system: 0, part: 0, marked: 0, columns: 0, source: 'wafer', cut: true })];
  const cutAnswer = { ...ANSWER, truncated: { ...ANSWER.truncated, nodes: true } };
  const g = seat(M, scatterDecl(), { answer: cutAnswer });
  await settle();
  out.cut = [a.stats.get('S1').cut, g.stats.get('S1').cut];
  return out;
}

/** T12: Save, then a new page from what was saved - the same picture. */
async function reopen(M) {
  const memory = new Map();
  const storage = { getItem: (k) => (memory.has(k) ? memory.get(k) : null), setItem: (k, v) => memory.set(k, String(v)), removeItem: (k) => memory.delete(k) };
  const declaration = { entities: [{ type: 'wafer' }, { type: 'lot' }], predicates: [] };
  const fetchImpl = async (url) => {
    const u = String(url);
    const body = u.includes('/api/ledger/declaration') ? declaration : u.includes('/api/ledger/subgraph') ? ANSWER : { nodes: [] };
    return { ok: true, status: 200, json: async () => JSON.parse(JSON.stringify(body)) };
  };
  const open = async () => {
    const doc = makeDoc('dark');
    const host = doc.createElement('div');
    const page = await M.main.boot({ doc, host, apiBase: '', fetchImpl, charts: chartsRecorder(), storage, theme: 'dark' });
    await settle();
    return page;
  };
  const first = await open();
  const s = first.shell.partOf('scatter-1');
  s.setDeclaration({ ...s.declaration(), start: { marking: null }, encode: { x: temp, y: press } });
  await settle();
  first.save();
  const second = await open();
  const t = second.shell.partOf('scatter-1');
  const picture = (part) => JSON.stringify([part.declaration(), part.model && part.model.points.map((p) => [p.id, p.x, p.y])]);
  // T18: the site's theme follows the page's, whatever the document came with.
  const themed = async (was, theme) => {
    const doc = makeDoc(was);
    await M.main.boot({ doc, host: doc.createElement('div'), apiBase: '', fetchImpl, charts: chartsRecorder(), storage: null, theme });
    await settle();
    return doc.documentElement.getAttribute('data-theme');
  };
  return { same: picture(s) === picture(t), points: t.model ? t.model.points.length : -1,
    siteTheme: [await themed('light', 'dark'), await themed('dark', 'light')] };
}

/** T14 / T15: the census and the bundle. */
function census() {
  const files = readdirSync(TB).filter((f) => f.endsWith('.js')).map((f) => [f, readFileSync(join(TB, f), 'utf8')])
    .concat(readdirSync(join(TB, 'kinds')).map((f) => [`kinds/${f}`, readFileSync(join(TB, 'kinds', f), 'utf8')]));
  const callers = files.filter(([f, t]) => f !== 'filter.js' && /\bkeepNodes\(/.test(t)).map(([f]) => f);
  const kindsFilter = files.filter(([f, t]) => f.startsWith('kinds/') && /from '\.\.\/filter\.js'/.test(t)).map(([f]) => f);
  const dist = join(HERE, '..', 'dist', 'assets');
  let bundle = null;
  if (existsSync(dist)) {
    const all = readdirSync(dist).filter((f) => f.endsWith('.js'));
    const tb = all.filter((f) => /^testbed-/.test(f)).map((f) => statSync(join(dist, f)).size);
    const others = all.filter((f) => !/^testbed-/.test(f) && /zrender|echarts/.test(readFileSync(join(dist, f), 'utf8'))).length;
    bundle = { testbedUnder700k: tb.length > 0 && Math.max(...tb) < 700 * 1024, chartsElsewhere: others };
  }
  return { callers, kindsFilter, bundle };
}

function suite(out, page, saved, counted) {
  const names = [];
  const failures = [];
  const eq = (name, got, want) => {
    names.push(name);
    const g = JSON.stringify(got), w = JSON.stringify(want);
    if (g === w) { console.log(`  PASS ${name}`); return; }
    failures.push(name);
    console.log(`  FAIL ${name}\n        got  ${g}\n        want ${w}`);
  };
  eq('T1 the reduces fold as the server walk fold does - contracts/walk_aggregate, every vector', out.contract, []);
  eq('T2 Latest: the newest time; two values at it none (tied); one read itself; untimed several none; an empty Avg null; a numeric fold skips what is not a number',
    out.latest, [2, { value: null, n: 2, tied: 2, untimed: 0 }, 7, null, null, { value: 1, n: 2, skipped: 1 }]);
  eq('T3 a slot read: one; several without a reduce; one-valued takes the newest; a reduce folds; nothing said empty; not walked missing; a plural attribute several, each a category',
    out.reads, ['one', 'several', '34', 34, 'empty', 'missing', 'several', ['A', 'B']]);
  eq('T4 the one filter: a range; two conditions AND; checked values with empty kept; another type passes untouched; a period [from, to)',
    out.filter, [['W2', 'W3', 'W4'], ['W3', 'W4'], ['W1', 'W3', 'W4', 'W6'], ['L1'], true, false]);
  eq('T5 the scatter model: two values each drawn, several not drawn, nothing not drawn; a marked point its colour, the rest mixed 20 % toward the background; legend dim where nothing marked',
    out.scatter, { drawn: ['W1', 'W2', 'W4', 'W5'], notDrawn: 1, several: 1, kinds: ['value', 'value'], marked: '#6489FA', dimmed: '#363D54',
      legend: [['A', false, ['W1', 'W4']], ['B', false, ['W2', 'W5']]] });
  eq('T6 a drag marks the points its rectangle holds - x and y both inside', out.drag, [['W2', 'W4'], ['W4'], []]);
  eq('T7 the cross table: a row with two values stands in both; a cell folds its rows\' values (Avg over the union, not of averages); totals; a cell with a marked row marked',
    out.cross, { rows: ['L1', 'L2', '(Empty)'], cols: ['A', 'B', '(Empty)'],
      grid: [[[2, ['W1', 'W3'], true], [2.5, ['W2', 'W3'], false], [null, [], false]], [[4, ['W4'], false], [5, ['W5'], false], [null, [], false]],
        [[null, [], false], [null, [], false], [null, ['W6'], false]]],
      rowTotals: [2, 4.5, null], colTotals: [2.6666666666666665, 3.3333333333333335, null], total: 3 });
  eq('T8 hubs: members take the hub\'s sign, a + wins over a -, a node stands as itself; a hub holds its members; said in words',
    out.hubs, [{ positive: ['W1', 'W2', 'W3'], negative: ['W9'] }, true, 0, 'wafer · lot = L1']);
  eq('T16 the picker\'s routes are the walk table\'s «+ Column» routes (reach_table routesFrom) - no second list', out.routes, true);
  eq('T9a All walks the row type described; the rows and counts; every drawable point drawn',
    [page.allAsked, page.allStats, page.drawnPoints], [[['wafer', null]], { rows: 6, of: 6, system: 0, part: 0, marked: 0, columns: 3, source: 'wafer', cut: false }, 4]);
  eq('T9b a drag marks what the rectangle holds, replacing; the status bar counts it', [page.dragMarked, page.dragStats], [['W2', 'W4'], 2]);
  eq('T9c a cross table cell marks its hub whole; the scatter draws its members marked', [page.hubMark, page.hubShown],
    [[1, true, ['W1', 'W3']], ['W1']]);
  eq('T9d the system filter\'s start side keeps the start nodes first and walks again from the kept ones', page.startSide,
    { asked: [['W1', 'W4'], ['W4']], startDropped: 1, system: 3 });
  eq('T9e the received side (system) and the part\'s own filter count apart; a marked node they hide is said', page.twoLayers,
    { rows: 3, of: 6, system: 2, part: 1, hidden: 1 });
  eq('T10 two scatters on one page: a slot changed in one stays there - it alone draws again and lets its old chart go; the other one stands',
    page.twoParts, [['x', 'y'], ['x', 'y'], 1, true, false, true]);
  eq('T11 a kind added draws through the same root, the root unchanged', page.kindAdd, ['rows 6']);
  eq('T13 the status words: N of M, the two drops, marked and hidden, columns, the row type; a cut walk said',
    page.status, [['4 of 6 rows', 'system −1 · part −1', '2 marked · hidden 1', '3 columns', 'wafer'],
      ['1 of 1 rows', 'filter over a cut walk', '0 marked', '0 columns', 'wafer']]);
  eq('T17 a cut walk is the board\'s reading of truncated (an axis true), not «truncated is there»', page.cut, [false, true]);
  eq('T12 Save, then a new page from it: the same declaration, the same points', { same: saved.same, points: saved.points }, { same: true, points: 4 });
  eq('T18 the site\'s theme is the page\'s - the walk page\'s parts on it (the start picker) wear the same tokens', saved.siteTheme, ['dark', 'light']);
  eq('T14 census: the visual part is the one caller of the filter; no kind imports it', [counted.callers, counted.kindsFilter], [['visual_part.js'], []]);
  if (counted.bundle) eq('T15 the bundle: the testbed chunk under 700 kB, ECharts in no other page\'s chunk', counted.bundle, { testbedUnder700k: true, chartsElsewhere: 0 });
  return { ran: names.length, names, failures };
}

console.log('\n[1] the visual testbed');
const run = async (M) => suite(await measure(M), await parts(M), await reopen(M), census());
const base = await run(REAL);
let ran = base.ran;
let failed = base.failures.length;

const swap = (text, from, to) => {
  if (!text.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`);
  return text.split(from).join(to);
};
const MUTANTS = [
  { id: 'M1', what: 'an even median the lower middle', catches: 'T1', file: 'testbed/aggregate.js',
    mutate: (t) => swap(t, ': (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2;', ': sorted[sorted.length / 2 - 1];') },
  { id: 'M2', what: 'a fold of nothing 0, not null', catches: 'T1', file: 'testbed/aggregate.js',
    mutate: (t) => swap(t, '  if (!nums.length) return { value: null, n, skipped };', '  if (!nums.length) return { value: 0, n, skipped };') },
  { id: 'M3', what: 'Latest picks one of two values at the newest time', catches: 'T2', file: 'testbed/aggregate.js',
    mutate: (t) => swap(t, '  return at.length === 1 ? { value: at[0], n: flat.length, untimed }', '  return at.length >= 1 ? { value: at[0], n: flat.length, untimed }') },
  { id: 'M4', what: 'several values drawn as the first', catches: 'T3', file: 'testbed/slot.js',
    mutate: (t) => swap(t, "  return values.length === 1 ? { state: 'one', value: values[0], n: reads.length } : { state: 'several', values, n: reads.length };",
      "  return { state: 'one', value: values[0], n: reads.length };") },
  { id: 'M5', what: 'a one-valued slot not taken as Latest', catches: 'T3', file: 'testbed/slot.js',
    mutate: (t) => swap(t, "const reduce = slot.reduce || (oneValued ? 'Latest' : null);", 'const reduce = slot.reduce || null;') },
  { id: 'M6', what: 'a condition holds for every type', catches: 'T4', file: 'testbed/filter.js',
    mutate: (t) => swap(t, '  if (!node || node.type !== condition.row) return true;', '  if (!node) return true;') },
  { id: 'M7', what: 'conditions OR, not AND', catches: 'T4', file: 'testbed/filter.js',
    mutate: (t) => swap(t, 'list.every((c) => nodePasses(', 'list.some((c) => nodePasses(') },
  { id: 'M8', what: 'a period closed at its end', catches: 'T4', file: 'testbed/filter.js',
    mutate: (t) => swap(t, '!(Number.isFinite(to) && t >= to)', '!(Number.isFinite(to) && t > to)') },
  { id: 'M9', what: 'a dimmed point keeps its colour (no mix)', catches: 'T5', file: 'testbed/kinds/scatter.js',
    mutate: (t) => swap(t, 'fill: dim ? mix(fill, theme.bg) : fill', 'fill: fill') },
  { id: 'M10', what: 'a several drawn - not counted apart', catches: 'T5', file: 'testbed/kinds/scatter.js',
    mutate: (t) => swap(t, "    if ([x, y, color].some((r) => r && r.state === 'several')) { several += 1; continue; }\n", '') },
  { id: 'M11', what: 'a drag tests only x', catches: 'T6', file: 'testbed/kinds/scatter.js',
    mutate: (t) => swap(t, ' && inside(coordRange[1], at(model.yKind, option.yAxis, p.y)))', ')') },
  { id: 'M12', what: 'a row with two values counted in its first only', catches: 'T3', file: 'testbed/slot.js',
    mutate: (t) => swap(t, "  if (read.state === 'several') return read.values;", "  if (read.state === 'several') return read.values.slice(0, 1);") },
  { id: 'M13', what: 'a total folded over its cells\' rows twice (a row in two cells)', catches: 'T7', file: 'testbed/kinds/cross_table.js',
    mutate: (t) => swap(t, '    const once = [...new Set(ids)];', '    const once = [...ids];') },
  { id: 'M14', what: 'a - beats a + for a node in two hubs', catches: 'T8', file: 'testbed/hubs.js',
    mutate: (t) => swap(t, '      if (sign.get(node) !== SIGN.CASE) sign.set(node, s);', '      sign.set(node, s);') },
  { id: 'M15', what: 'All walks with no seed', catches: 'T9a', file: 'testbed/visual_part.js',
    mutate: (t) => swap(t, "    const params = seeds.all ? { ...base, seed_type: this.decl.row }", '    const params = seeds.all ? { ...base }') },
  { id: 'M16', what: 'a drag adds instead of replacing', catches: 'T9b', file: 'testbed/visual_part.js',
    mutate: (t) => swap(t, "    if (mode === 'add') { for (const id of ids) this.markings.set(this.writes, id, sign); return; }", '    { for (const id of ids) this.markings.set(this.writes, id, sign); return; }') },
  { id: 'M17', what: 'a hub not opened into its members when the marking is shown', catches: 'T8', file: 'testbed/hubs.js',
    mutate: (t) => swap(t, "(isHubId(id) && book.membersOf(id).includes(nodeId))", 'false') },
  { id: 'M18', what: 'the start side not walked again', catches: 'T9d', file: 'testbed/visual_part.js',
    mutate: (t) => swap(t, '      if (dropped) {', '      if (false) {') },
  { id: 'M19', what: 'the part\'s own filter not applied', catches: 'T9e', file: 'testbed/visual_part.js',
    mutate: (t) => swap(t, 'afterSystem.kept, this.decl.filter || [], this.oneValued', 'afterSystem.kept, [], this.oneValued') },
  { id: 'M20', what: 'a redraw keeps its old chart (two charts on one box)', catches: 'T10', file: 'testbed/visual_part.js',
    mutate: (t) => swap(t, '    if (this.drawn) { this.drawn.dispose(); this.drawn = null; }\n', '') },
  { id: 'M21', what: 'a cut walk read as «truncated is there»', catches: 'T17', file: 'testbed/visual_part.js',
    mutate: (t) => swap(t, 'cut: (truncationAxes(this.answer.truncated, { hopsChosen: false }) || []).length > 0 };', 'cut: Boolean(this.answer.truncated) };') },
  { id: 'M22', what: 'the status bar leaves out the drops', catches: 'T13', file: 'testbed/status_part.js',
    mutate: (t) => swap(t, '  if (s.system || s.part) words.push(', '  if (false) words.push(') },
  { id: 'M23', what: 'a saved page reopens on the layout, not on what was saved', catches: 'T12', file: 'testbed/main.js',
    mutate: (t) => swap(t, '  const layout = laidOut(LAYOUT, saved, entities());', '  const layout = laidOut(LAYOUT, null, entities());') },
  { id: 'M24', what: 'the site\'s theme left as it came (the code before: a white picker on the dark page)', catches: 'T18', file: 'testbed/main.js',
    mutate: (t) => swap(t, "  root.setAttribute('data-theme', theme);\n", '') },
];
const KEY = { 'testbed/aggregate.js': 'aggregate', 'testbed/slot.js': 'slot', 'testbed/filter.js': 'filter', 'testbed/hubs.js': 'hubs',
  'testbed/kinds/scatter.js': 'scatter', 'testbed/kinds/cross_table.js': 'cross', 'testbed/visual_part.js': 'visual', 'testbed/status_part.js': 'status',
  'testbed/main.js': 'main' };
const scored = await scoreMutants(MUTANTS, async (m) => {
  const copy = (await loadWithProbe(join(SRC, m.file), { mutate: m.mutate })).module;
  return run({ ...REAL, [KEY[m.file]]: copy });
}, { baselineRan: base.ran, baselineNames: base.names, title: '\n  [1] mutants - each must be caught by the check it names.' });
ran += MUTANTS.length;
failed += scored.wrong;

console.log(`\n${ran - failed} passed, ${failed} failed`);
console.log(`ASSERTIONS ${ran} ${failed}`);
if (failed) process.exit(1);
