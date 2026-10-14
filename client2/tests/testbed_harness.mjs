// The visual testbed (lead aca803a7a, d1b3c1b7f, 5835e6714): the root visual part and its kinds, the one filter, the hubs,
// the reduces against the server's walk fold (contracts/walk_aggregate), the page's save and reopen. Every subject is
// IMPORTED; the page around it is the board's document stub (tests/lib/board_dom.mjs) and a recording chart.
//
// CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
import { readFileSync, existsSync, readdirSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { loadWithProbe, readSourceText } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';
import { makeDoc, walk } from './lib/board_dom.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src');
const TB = join(SRC, 'testbed');
const ROOT = join(HERE, '..', '..');

const REAL = {
  aggregate: await import('../src/testbed/aggregate.js'),
  slot: await import('../src/testbed/slot.js'),
  units: await import('../src/testbed/units.js'),
  filter: await import('../src/testbed/filter.js'),
  hubs: await import('../src/testbed/hubs.js'),
  scatter: await import('../src/testbed/kinds/scatter.js'),
  color: await import('../src/testbed/color_by.js'),
  cross: await import('../src/testbed/kinds/cross_table.js'),
  table: await import('../src/testbed/kinds/table.js'),
  map: await import('../src/testbed/kinds/map.js'),
  visual: await import('../src/testbed/visual_part.js'),
  status: await import('../src/testbed/status_part.js'),
  picker: await import('../src/testbed/picker.js'),
  main: await import('../src/testbed/main.js'),
  palette: await import('../src/testbed/palette.js'),
};
REAL.store = await import('../src/rnd_board/marking_store.js');
REAL.cond = await import('../src/testbed/condition_editor.js');
const { MarkingStore, SIGN } = REAL.store;
const { parseAst } = await import('rolldown/parseAst');
const { indexGraph, routesFrom } = await import('../src/walk/reach_table.js');
const { KeyedStore } = await import('../src/testbed/keyed_store.js');
const { localStamp } = await import('../src/server_time.js');
const EXPR = await import('../src/expression.js');

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
// The measured Spotfire colours (task/SPOTFIRE_SCATTER_REFERENCE.md §11), as this harness writes them: the palette a
// part is handed (a canvas reads the page's tokens; T25 holds tokens.css to these).
const CAT = [['#6489FA', '#4B67BC'], ['#FA7864', '#BC5A4B'], ['#FFDE5C', '#BFA645'], ['#72ECA6', '#56B17C'], ['#ED72DD', '#B256A6'],
  ['#72BEED', '#568EB2'], ['#FAA264', '#BC7A4B']];
const MEASURED = {
  dark: { '--sf-bg': '#2A2A2A', '--sf-page': '#232323', '--sf-text': '#FFFFFF', '--sf-text-2': '#C8C8C8', '--sf-title': '#FFFFFF', '--sf-axis': '#666666',
    '--sf-line': '#404040', '--sf-stripe': '#404040', '--sf-status': '#61646B' },
  light: { '--sf-bg': '#FFFFFF', '--sf-page': '#F7F9FF', '--sf-text': '#61646B', '--sf-title': '#313336', '--sf-axis': '#D1D4DE', '--sf-line': '#F0F1F2',
    '--sf-stripe': '#F7F9FF', '--sf-status': '#EDF0F7' },
  both: { '--sf-cell-h': '18px', '--sf-cell-pad': '2px 8px 1px 6px', '--sf-title-inset': '8px', '--sf-active': '#7188F8', '--sf-marked': '#00A650', '--sf-panel-head': '#F2F5FC', '--sf-panel-accent': '#3050EF', '--sf-one': '#A0A0A0',
    ...Object.fromEntries(CAT.flatMap(([fill, line], k) => [[`--sf-cat-${k + 1}`, fill], [`--sf-cat-${k + 1}-line`, line]])) },
};
const DARK = { bg: '#2A2A2A', text: '#FFFFFF', axis: '#666666', active: '#7188F8', brush: 'rgba(113, 136, 248, 0.15)', one: ['#A0A0A0', '#787878'], cat: CAT };

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
    kinds: { scatter: M.scatter.kind, crossTable: M.cross.kind, ...kinds }, fetchWalk, filters, stats, active: new KeyedStore(), hubs, names: new Map(), charts, palette: () => DARK });
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
  // the root's colours and paint (color_by.js), the kind's model on them
  const t5rows = rowsOf(WAFERS, { x: temp, y: press, color: product });
  const t5paint = M.color.paintRows(t5rows, { marked: (id) => marked.has(id), palette: DARK, declaration: { encode: { color: product } } });
  const model = M.scatter.scatterModel(t5rows, { ...t5paint, palette: DARK });
  const p1 = model.points.find((p) => p.id === 'W1');
  const p4 = model.points.find((p) => p.id === 'W4');
  // T40: the marks (lead-board-13 ②) - several spread a mark each; two several slots from the same records paired, from
  // different records the row dropped with why; one value the same on every mark; a mark is its row's
  const mk = (id, reads) => ({ id, label: id, reads, raw: {} });
  const sev = (values) => ({ state: 'several', values, n: values.length });
  const recordsOf = (id, key) => ({ R1: { x: [{ value: '1', record: 'e1' }, { value: '2', record: 'e2' }], y: [{ value: 'a', record: 'e1' }, { value: 'b', record: 'e2' }] },
    R2: { x: [{ value: '1', record: 'e1' }, { value: '2', record: 'e2' }], y: [{ value: 'a', record: 'e3' }, { value: 'b', record: 'e4' }] } }[id] || {})[key] || null;
  const got = M.units.marksOf([mk('R0', { x: { state: 'one', value: '5' }, y: sev(['p', 'q']) }), mk('R1', { x: sev(['1', '2']), y: sev(['a', 'b']) }),
    mk('R2', { x: sev(['1', '2']), y: sev(['a', 'b']) })], ['x', 'y'], recordsOf, (k) => k.toUpperCase());
  out.marks = [got.marks.map((m) => [m.id, m.row, m.ids.join(), m.reads.x.value, m.reads.y.value]), got.dropped.map((d) => [d.id, d.why])];
  // T36: a slot's scale - the one seat (lead-board-13 ①, owner 10-14 ㄱ)
  const one = (value, declared) => ({ state: 'one', value, ...(declared ? { declared } : {}) });
  const sc = (reads, chosen) => { const s = M.slot.scaleOf(reads, chosen); return `${s.scale}${s.time ? '+time' : ''}`; };
  out.scales = [sc([one('S1', 'number')]), sc([one('2026-10-01', 'datetime')]), sc([one('10', 'string'), one('20', 'string')]),
    sc([one('A', 'string')]), sc([one('10'), one('x')]), sc([one('2026-10-01T00:00:00+09:00'), one('2026-10-02T00:00:00Z')]),
    sc([one('2026-10-01', 'datetime')], 'categorical'), sc([one('A')], 'continuous'), sc([])];
  out.timeOrder = M.slot.categoryOrder(['2026-10-01T20:00:00Z', '2026-10-02T01:00:00+09:00'], true);
  // T38: a continuous Color by - a ramp from the first category colour, the least and the most its ends; no categories
  const pal = { bg: '#ffffff', one: ['#888888', '#666666'], cat: [['#1060c0', '#0a4a90']] };
  const rampRows = [['W1', '10'], ['W2', '20'], ['W3', '30'], ['W4', null]].map(([id, v]) => ({ id, reads: { color: v === null ? { state: 'empty' } : { state: 'one', value: v } } }));
  const ramp = M.color.colorsOf(rampRows, { palette: pal, declaration: { encode: { color: temp } }, scale: { scale: 'continuous', time: false } });
  out.ramp = [ramp.categories.length, ramp.ramp && ramp.ramp.min, ramp.ramp && ramp.ramp.max, ramp.ramp && ramp.ramp.high, ramp.of.get('W3').fill, ramp.of.get('W1').fill,
    ramp.of.get('W1').fill !== ramp.of.get('W2').fill, ramp.of.get('W4').fill];
  out.scatter = { drawn: model.points.map((p) => p.id), notDrawn: model.notDrawn, kinds: [model.xKind, model.yKind],
    marked: p1.fill, dimmed: p4.fill, legend: t5paint.colors.categories.map((l) => [l.name, l.dim, l.ids]) };
  const option = M.scatter.scatterOption(model, DARK);
  out.drag = [M.scatter.idsInRange(model, option, [[15, 45], [1.5, 4.5]]), M.scatter.idsInRange(model, option, [[15, 45], [3.5, 4.5]]),
    M.scatter.idsInRange(model, option, [[0, 5], [0, 1]])];
  // T7: the cross table
  const crossRows = WAFERS.map((id) => ({ id, reads: { rows: readSlot(index, inside, id, lot), columns: readSlot(index, inside, id, product) },
    raw: { cells: index.out.get(id) ? index.out.get(id).filter((e) => e.target === 'QP').map((e) => ({ value: e.qualifiers.value, t: null })) : [] } }));
  const ct = M.cross.crossModel(crossRows, { ...M.color.paintRows(crossRows, { marked: (id) => id === 'W1', palette: DARK, declaration: crossDecl() }), declaration: crossDecl() });
  out.cross = { rows: ct.rowKeys, cols: ct.colKeys, grid: ct.grid.map((line) => line.map((c) => [c.value, c.ids, c.marked])), rowTotals: ct.rowTotals, colTotals: ct.colTotals, total: ct.total };
  // T27: an expression slot - the calculator over the row's own values (src/expression.js)
  const exprSlot = (expr) => ({ expr, words: [expr] });
  const isA = exprSlot('If([product] = "A", 1, 0)');
  out.exprReads = ['W1', 'W2', 'W3', 'W6', 'NOPE'].map((id) => { const r = readSlot(index, inside, id, isA); return [r.state, r.value === undefined ? null : r.value]; });
  out.exprFolds = ['W1', 'W3', 'W6'].map((id) => readSlot(index, inside, id, exprSlot('Count([product])')).value);
  // ... a cross table cell: Count() as the table with no cell slot, Count([product]) as the product slot counted
  const exprCross = (cells) => {
    const decl = crossDecl({ encode: { rows: lot, columns: product, ...(cells ? { cells } : {}) } });
    const xs = WAFERS.map((id) => ({ id, reads: { rows: readSlot(index, inside, id, lot), columns: readSlot(index, inside, id, product) },
      raw: cells ? { cells: M.slot.rawOf(index, inside, id, cells) } : {} }));
    const m = M.cross.crossModel(xs, { ...M.color.paintRows(xs, { palette: DARK, declaration: decl }), declaration: decl });
    return JSON.stringify([m.grid.map((line) => line.map((c) => c.value)), m.rowTotals, m.colTotals, m.total]);
  };
  out.exprCross = [exprCross(exprSlot('Count()')) === exprCross(null), exprCross(exprSlot('Count([product])')) === exprCross({ ...product, reduce: 'Count' }),
    M.cross.title({ rows: lot, columns: product, cells: exprSlot('Avg([wafer])') })];
  // T31: a way in the brackets - its end node's own value, a fold over its ends; a row the way does not reach empty
  out.ways = [['W1', '[in_lot.name]'], ['W6', '[in_lot.name]'], ['W1', 'Avg([measures.value])'], ['W1', '[measures.value]']]
    .map(([id, expr]) => { const r = readSlot(index, inside, id, exprSlot(expr)); return [r.state, r.value === undefined ? null : r.value]; });
  // T32: Marked() reads the page's marking answer the slot is handed - true, false, unknown (empty)
  const pageMarks = (name, id) => (name !== 'pick' ? false : id === 'W1' ? true : id === 'W2' ? false : null);
  out.marked = ['W1', 'W2', 'W3'].map((id) => { const r = readSlot(index, inside, id, exprSlot('Marked("pick")'), false, pageMarks); return [r.state, r.value === undefined ? null : r.value]; });
  // T33: a column the walk declares datetime (A d1f1c3e4b) - Max over it the latest instant; undeclared, a number fold of
  // texts that are not numbers - nothing
  {
    const at = (v, typed) => ({ source: 'TW', target: 'TQ', predicate: 'measures', qualifiers: { at: v }, ...(typed ? { column_types: { at: 'datetime' } } : {}) });
    const g = (typed) => indexGraph({ nodes: [{ id: 'TW', type: 'wafer', label: 'TW', keys: {}, attributes: {} }, { id: 'TQ', type: 'quantity', label: 'TQ', keys: {}, attributes: {} }],
      edges: ['2026-10-01T00:00:00Z', '2026-10-03T00:00:00Z', '2026-10-02T00:00:00Z'].map((v) => at(v, typed)) });
    const inside = new Set(['TW', 'TQ']);
    out.typed = [true, false].map((typed) => { const r = readSlot(g(typed), inside, 'TW', exprSlot('Max([measures.at])')); return [r.state, r.value === undefined ? null : r.value, r.types || null]; });
  }
  // T30: an operator over a text that is not a number - the row empty and said so; a list is several, an empty value empty
  out.notNumber = ['W1', 'W3', 'W6'].map((id) => { const r = readSlot(index, inside, id, exprSlot('[product] * 2')); return [r.state, Boolean(r.notNumber)]; });
  // T29: a filter condition on an expression slot carries the expression and is judged by it; two expression
  //      conditions on one row type stay two
  const cA = M.cond.conditionFor({ row: 'wafer', slot: isA, words: isA.expr, values: [[1, 2], [0, 2]], empty: 1 });
  // a condition that lost its expression reads a slot with no value - the filter throws (the defect M43 makes)
  const passing = () => { try { return keepNodes(index, inside, WAFERS, [{ ...cA, range: { min: 1, max: 1 }, empty: false }]).kept; } catch (e) { return 'threw'; } };
  out.exprCondition = [cA.expr, passing(),
    M.cond.conditionKey(cA) !== M.cond.conditionKey({ row: 'wafer', ...exprSlot('Count([product])') })];
  // T23: each kind words its own title
  out.titles = [M.scatter.title(scatterDecl().encode), M.cross.title(crossDecl().encode), M.cross.title({ rows: lot, columns: product })];
  // T8: hubs
  const book = new M.hubs.HubBook();
  const h = book.put(M.hubs.hubId('wafer', [['lot', 'L1']]), ['W1', 'W2', 'W3']);
  out.hubs = [M.store.seedsOf([[h, SIGN.CASE], ['W2', SIGN.CONTROL], ['W9', SIGN.CONTROL]], (id) => book.open(id)), M.hubs.holds([[h, SIGN.CASE]], book, 'W3'),
    M.hubs.holdsOf ? 1 : 0, M.hubs.hubWords(h)];
  // T20: the walk page's reading - no opener, each entry itself, in the marking's order
  out.walkSeeds = M.store.seedsOf([['A', SIGN.CASE], ['B', SIGN.CONTROL], ['C', SIGN.CASE], ['D', SIGN.ABSENT]]);
  // T16: the picker's routes are the walk table's
  out.routes = JSON.stringify(M.picker.routeChoices(index, WAFERS).slice(1)) === JSON.stringify(routesFrom(index, WAFERS));
  // T26: the palette a canvas draws with is what the document's root computes - each token by its name, trimmed
  const said = { '--sf-bg': '#111111', '--sf-text': '#222222', '--sf-axis': '#333333', '--sf-active': '#444444', '--sf-brush': 'rgba(1, 2, 3, 0.5)',
    '--sf-one': '#555555', '--sf-one-line': '#666666', ...Object.fromEntries([1, 2, 3, 4, 5, 6, 7].flatMap((k) => [[`--sf-cat-${k}`, `#00000${k}`], [`--sf-cat-${k}-line`, `#11111${k}`]])) };
  const docOf = { documentElement: {}, defaultView: { getComputedStyle: () => ({ getPropertyValue: (name) => ` ${said[name] || ''}` }) } };
  const read = M.palette.paletteOf(docOf);
  out.palette = [read.bg, read.text, read.axis, read.active, read.brush, read.one, read.cat[0], read.cat[6], read.cat.length, M.palette.categoryColor(read, 8),
    // the build writes #FFFFFF as #fff and the page computes that: a dimmed point the same either way
    M.palette.mix('#6489FA', '#fff'), M.palette.mix('#6489fa', '#FFFFFF')];
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
  const again = a.charts.made[a.charts.made.length - 1].option.series[0].data.filter((d) => a.part.colors.categories.some((c) => c.fill === d.itemStyle.color)).map((d) => d.id).sort();
  out.hubShown = again;
  // T9c': the status bar's «K marked rows» counts the part's rows the marking holds - a hub of two is two, not one entry
  out.hubCounted = [held.length, a.stats.get('S1').marked];
  // T9d: the system filter's start side - a dropped start node, the walk taken again from the kept ones
  const markings = new MarkingStore();
  markings.set('marking:start', 'W1', SIGN.CASE);
  markings.set('marking:start', 'W4', SIGN.CASE);
  const filters = new KeyedStore({ 'filter:1': [{ row: 'wafer', ...press, range: { min: 3 }, empty: false }] });
  const d = seat(M, scatterDecl({ start: { marking: 'marking:start' } }), { markings, filters });
  await settle();
  out.startSide = { asked: d.asked.map((p) => p.positive), startDropped: d.stats.get('S1').startDropped, system: d.stats.get('S1').system };
  // T9f: the system filter changed - its start side judged again: widened, the start node it let go comes back; narrowed
  // past every start, none walked. The walk from every seed is the one in hand (no walk asked again for it). A
  // declaration that names another system filter walks again from its start side as well.
  const reach = (params) => {
    const seeds = new Set(params.positive || []);
    const nodes = ANSWER.nodes.filter((n) => n.type !== 'wafer' || seeds.has(n.id));
    const ids = new Set(nodes.map((n) => n.id));
    return { ...ANSWER, nodes, edges: ANSWER.edges.filter((e) => ids.has(e.source) && ids.has(e.target)) };
  };
  const m3 = new MarkingStore();
  m3.set('marking:start', 'W1', SIGN.CASE);
  m3.set('marking:start', 'W4', SIGN.CASE);
  const f3 = new KeyedStore({ 'filter:1': [{ row: 'wafer', ...press, range: { min: 3 }, empty: false }], 'filter:2': [] });
  const w = seat(M, scatterDecl({ start: { marking: 'marking:start' } }), { markings: m3, filters: f3, answer: reach });
  await settle();
  const now = () => ({ rows: w.stats.get('S1').rows, startDropped: w.stats.get('S1').startDropped, asked: w.asked.length });
  const filterSteps = [now()];
  f3.set('filter:1', []);
  await settle();
  filterSteps.push(now());
  f3.set('filter:1', [{ row: 'wafer', ...press, range: { min: 5 }, empty: false }]);
  await settle();
  filterSteps.push(now());
  w.part.setDeclaration({ ...w.part.declaration(), system: 'filter:2' });
  await settle();
  filterSteps.push(now());
  out.filterChanged = filterSteps;
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
  // T11: a third kind - the root draws it with no change of its own: the kind's title, the field it reads off its own
  // declaration, its own slot's reduce; the template's pills - its slot on the tray it names, Color by in the legend
  const stub = { name: 'list', label: 'List', slots: [{ key: 'v', label: 'Value', tray: 'bottom' }],
    title: (encode) => `List of ${M.slot.slotWords(encode.v)}`,
    model: (rows, ctx) => { const d = ctx.declaration || {}; return { n: rows.length, every: d.every, reduce: d.encode && d.encode.v && d.encode.v.reduce }; },
    render: (area, model, ctx) => {
      const p = ctx.doc.createElement('p');
      p.textContent = `rows ${model.n} · every ${model.every} · ${model.reduce}`;
      area.append(p);
      return { resize() {}, dispose() {} };
    } };
  const k = seat(M, { ...scatterDecl({ id: 'K1', kind: 'list', every: 3 }), encode: { v: { ...temp, reduce: 'Max' } } }, { kinds: { list: stub } });
  await settle();
  const pills = walk(k.host).filter((n) => n.className && String(n.className).startsWith('sf-pill') && n.tagName === 'BUTTON');
  out.kindAdd = { drawn: walk(k.host).filter((n) => n.tagName === 'P').map((n) => n.textContent),
    title: walk(k.host).filter((n) => n.className === 'sf-part__t').map((n) => n.textContent), statTitle: k.stats.get('K1').title,
    pills: pills.map((n) => [n.textContent.replace('▾', ''), Boolean(n.listeners && n.listeners.click)]) };
  // T28: Custom expression in the picker - a refusal says why and leaves the slot; a valid one sets it and is drawn
  const xp = seat(M, scatterDecl({ id: 'X1' }));
  await settle();
  const pickHost = xp.doc.createElement('div');
  new M.picker.SlotPicker(pickHost, { doc: xp.doc }).open({ part: xp.part, key: 'color', anchor: null });
  walk(pickHost).find((n) => n.tagName === 'BUTTON' && n.textContent === 'Custom expression…').listeners.click[0]({});
  const exprInput = () => walk(pickHost).find((n) => n.className === 'sf-pop__expr');
  const exprWhy = () => (walk(pickHost).find((n) => n.className === 'sf-pop__why' && n.parentNode && n.parentNode.className === 'sf-pop__edit') || {}).textContent;
  const enter = (text) => { exprInput().value = text; exprInput().listeners.keydown[0]({ key: 'Enter' }); };
  enter('Avg(');
  const custom = [exprWhy(), JSON.stringify(xp.part.declaration().encode.color) === JSON.stringify(product)];
  enter('If([nope] = 1, 1, 0)');
  custom.push(exprWhy());
  enter('If([product] = "A", "is A", "not A")');
  await settle();
  custom.push(xp.part.declaration().encode.color, (xp.part.colors ? xp.part.colors.categories : []).map((l) => l.name).filter((n) => n === 'is A' || n === 'not A').sort());
  out.custom = custom;
  // T31: Custom expression starts from the route chosen; the check reads a way's names the way the row does
  const wp = seat(M, scatterDecl({ id: 'X2', encode: { x: temp, y: { ...press, reduce: 'Avg' }, color: lot } }));
  await settle();
  const startOf = (key) => {
    const host = wp.doc.createElement('div');
    new M.picker.SlotPicker(host, { doc: wp.doc }).open({ part: wp.part, key, anchor: null });
    const custom = walk(host).find((n) => n.tagName === 'BUTTON' && n.textContent === 'Custom expression…');
    for (const fn of (custom || { listeners: {} }).listeners.click || []) fn({});
    const input = walk(host).find((n) => n.className === 'sf-pop__expr');
    return input ? input.value : null;
  };
  out.wayStart = [startOf('x'), startOf('y'), startOf('color'), M.picker.expressionRefusal(wp.part, '[in_lot.name]'),
    M.picker.expressionRefusal(wp.part, '[in_lot.nope]'), M.picker.expressionRefusal(wp.part, '[measures.value]')];
  // T37: the root's scale on a part - a pick in the declaration draws x as categories; the picker's Scale chips on X · Y ·
  // Color whatever the type (owner 10-14), and none on a slot the kind draws one way only
  const picked = seat(M, scatterDecl({ id: 'X4', scale: { x: 'categorical' } }));
  await settle();
  const chipsOf = (p, key) => { const host = wp.doc.createElement('div'); new M.picker.SlotPicker(host, { doc: wp.doc }).open({ part: p.part, key, anchor: null });
    return walk(host).filter((n) => n.tagName === 'BUTTON' && n.getAttribute && n.getAttribute('data-scale')).map((n) => `${n.getAttribute('data-scale')}${String(n.className).includes('is-on') ? '*' : ''}`); };
  const cross = seat(M, crossDecl({ id: 'C7' }));
  await settle();
  out.partScale = [picked.part.model.xKind, picked.part.model.yKind, chipsOf(picked, 'x'), chipsOf(picked, 'y'), chipsOf(picked, 'color'), chipsOf(cross, 'rows')];
  // T35: a cross table with no cell slot - its Cell values pill says what the cells hold (owner 10-14 «행수»: UniqueCount(rows));
  // one declared - its own words
  const pillOf = (p) => { const n = walk(p.host).find((x) => x.tagName === 'BUTTON' && x.getAttribute && x.getAttribute('data-slot') === 'cells');
    return n ? String(n.textContent).replace('▾', '') : null; };
  const noCells = seat(M, crossDecl({ id: 'C9', encode: { rows: lot, columns: product } }));
  const withCells = seat(M, crossDecl({ id: 'C8' }));
  await settle();
  out.cellsPill = [pillOf(noCells), pillOf(withCells)];
  // T42: one walk, four kinds on the same two slots (lead-board-13 ② gate): the root makes the same marks for each - W3's
  // two temps two marks, W6 with none one; the table a line a mark, W3's second line W3's
  const k4 = [seat(M, scatterDecl({ id: 'K4', encode: { x: temp, y: press } })), seat(M, scatterDecl({ id: 'K5', kind: 'table', encode: { col1: temp, col2: press } }), { kinds: { table: M.table.kind } }),
    seat(M, crossDecl({ id: 'K6', encode: { rows: temp, columns: press } })), seat(M, scatterDecl({ id: 'K7', kind: 'map', encode: { x: temp, y: press } }), { kinds: { map: M.map.kind } })];
  await settle();
  const second = (k4[1].part.model.lines || []).find((l) => l.id === 'W3#1');
  out.sameMarks = [...k4.map((k) => (k.part.unitsById ? k.part.unitsById.size : null)), (k4[1].part.model.lines || []).length, second ? second.ids : null];
  // T44: several on a slot of the root's (lead 10-15) - a paint slot (Color by, Shape by) one «(Multiple)» category, last,
  // its own look, a press on it marking its rows; a placing slot (Panel by, Marker by) the row in each of its values
  const mc = seat(M, scatterDecl({ id: 'MC' }));
  const ms = seat(M, scatterDecl({ id: 'MS', encode: { x: temp, y: press, shape: product } }));
  const mp = seat(M, scatterDecl({ id: 'MP', encode: { x: temp, y: press, panel: product } }));
  const mm = seat(M, scatterDecl({ id: 'MM', encode: { x: { ...temp, reduce: 'Avg' }, y: { ...press, reduce: 'Avg' }, marker1: product } }));
  await settle();
  const w3 = mc.part.model.points.filter((p) => p.ids.includes('W3'));
  const many = mc.part.colors.categories.find((c) => c.name === '(Multiple)') || {};
  const manyPress = walk(mc.host).find((n) => n.tagName === 'BUTTON' && String(n.className) === 'sf-legend__name' && n.textContent === '(Multiple)');
  for (const fn of (manyPress || { listeners: {} }).listeners.click || []) fn({});
  await settle();
  const pressed = mc.markings.entries('marking:pick').flatMap(([id]) => mc.hubs.open(id)).sort();
  out.multiple = [mc.part.colors.categories.map((c) => c.name), w3.length, [...new Set(w3.map((p) => p.fill))].length === 1 && w3[0].fill === many.fill,
    mc.part.colors.categories.filter((c) => c.fill === many.fill).length, many.ids || null, pressed,
    ms.part.shapes.categories.map((c) => c.name),
    (mp.part.panels || []).map((p) => [p.name, p.model.points.some((q) => q.ids.includes('W3'))]),
    mm.part.model.points.filter((q) => q.ids.includes('W3')).map((q) => q.label).sort(),
    M.color.paintCategoryOf({ state: 'several', values: ['A', 'B'] }), M.slot.categoryOrder(['B', '(Multiple)', 'A'])];
  // T45: one order of categories (lead 10-15) - numbers by their value before text, (Empty) and (Multiple) last; the cross
  // table's row heads, a category axis, the legend and the panels all in it
  const numAnswer = { nodes: ['1', '2', '10', '11'].map((v) => wafer(`N${v}`, { n: v, product: 'A' })), edges: [], truncated: ANSWER.truncated };
  const nAttr = { steps: [], value: { on: 'node', name: 'n' }, words: ['n'] };
  const nc = seat(M, crossDecl({ id: 'NC', encode: { rows: nAttr, columns: product } }), { answer: numAnswer });
  const ns = seat(M, scatterDecl({ id: 'NS', encode: { x: nAttr, y: product, color: nAttr, panel: nAttr }, scale: { x: 'categorical', color: 'categorical' } }), { answer: numAnswer });
  const nx = seat(M, scatterDecl({ id: 'NX', encode: { x: nAttr, y: product }, scale: { x: 'categorical' } }), { answer: numAnswer });
  await settle();
  const nChart = nx.charts.made[nx.charts.made.length - 1];
  out.order = [M.slot.categoryOrder(['10', 'B', '2', '(Empty)', '1', '(Multiple)', 'A', '11']),
    walk(nc.host).filter((n) => n.tagName === 'TH' && String(n.className) === 'sf-table__row').map((n) => n.textContent).filter((w) => w !== 'Total'),
    nChart ? nChart.option.xAxis.data : null, ns.part.colors.categories.map((c) => c.name), (ns.part.panels || []).map((q) => q.name)];
  // T43: a slot of days says its days (lead 10-15): every time of it the page zone's (Asia/Seoul) midnight - «YYYY-MM-DD»
  // on the cross table's row heads, the scatter's category ticks, the legend's names and the tooltip, the hub's value the
  // time itself; one 09:00 there (00:00Z) - every time as the grid says it (localStamp)
  const [D1, D2, DZ] = ['2026-11-24T00:00:00+09:00', '2026-11-25T00:00:00+09:00', '2026-11-24T00:00:00Z'];
  const made = { steps: [], value: { on: 'node', name: 'made' }, words: ['made'] };
  const dayAnswer = (times) => ({ nodes: times.map((v, i) => wafer(`D${i + 1}`, { made: v, product: 'A' })), edges: [], truncated: ANSWER.truncated });
  const daysOf = async (times) => {
    const answer = dayAnswer(times);
    const cross = seat(M, crossDecl({ id: `DC${times.length}`, encode: { rows: made, columns: product } }), { answer });
    const sc = seat(M, scatterDecl({ id: `DS${times.length}`, encode: { x: made, y: product, color: made }, scale: { x: 'categorical', color: 'categorical' } }), { answer });
    await settle();
    const heads = walk(cross.host).filter((n) => n.tagName === 'TH' && String(n.className) === 'sf-table__row').map((n) => n.textContent).filter((w) => w !== 'Total');
    const chart = sc.charts.made[sc.charts.made.length - 1];
    const fmt = chart.option.xAxis.axisLabel.formatter;
    const ticks = (chart.option.xAxis.data || []).map((v) => (fmt ? fmt(v) : v));
    const names = walk(sc.host).filter((n) => n.tagName === 'BUTTON' && String(n.className) === 'sf-legend__name');
    sc.part.showTip({ id: 'D1' }, { clientX: 0, clientY: 0 });
    const tip = sc.part.tip ? (sc.part.tip.children || []).map((n) => n.textContent) : [];
    return [heads, ticks, names.map((n) => n.textContent), names.map((n) => n.getAttribute('data-category') || (n.parentNode && n.parentNode.getAttribute && n.parentNode.getAttribute('data-category'))), tip.find((l) => l.startsWith('made')) || null];
  };
  out.days = [await daysOf([D1, D2]), await daysOf([D1, D2, DZ])];
  // ...and the one place itself: the slot's scale says day, valueText says a day of it
  out.dayText = [M.slot.scaleOf([{ state: 'one', value: D1 }, { state: 'one', value: D2 }]).day, M.slot.scaleOf([{ state: 'one', value: D1 }, { state: 'one', value: DZ }]).day,
    M.slot.valueText(D1, true, true), M.slot.valueText(DZ, true, true), M.slot.valueText(D1, true, false)];
  // T41: a kind that draws one value a place - the root's refusal (#MANY and why); a cross cell holds a row's two marks once
  const refused = M.units.refuseMany([{ id: 'W9', label: 'W9', reads: { a: { state: 'several', values: ['1', '2'], n: 2 } }, raw: {} }])[0].reads.a;
  const cells = M.slot.combosOf([{ id: 'W9#0', ids: ['W9'], reads: { r: { state: 'one', value: 'L' } } }, { id: 'W9#1', ids: ['W9'], reads: { r: { state: 'one', value: 'L' } } }], ['r']);
  out.rootRefusal = [refused.state, refused.error, refused.why, cells.map((c) => c.ids)];
  // T34: «time» in the picker's Value list (lead 10-14 ③ ㄱ): on a route, the slot reads the time of what it reads (its last
  // edge's) - of 'time', the same value; on «(row)» it is off with its reason
  const timeOf = (part, key) => {
    const host = part.doc ? part.doc.createElement('div') : wp.doc.createElement('div');
    new M.picker.SlotPicker(host, { doc: wp.doc }).open({ part, key, anchor: null });
    return walk(host).find((n) => n.tagName === 'BUTTON' && String(n.textContent).startsWith('time'));
  };
  const onRoute = timeOf(wp.part, 'x');
  for (const fn of (onRoute || { listeners: {} }).listeners.click || []) fn({});
  await settle();
  const timed = wp.part.declaration().encode.x || {};
  const read = M.slot.readSlot(wp.part.index, wp.part.inside, 'W1', timed);
  const rowPart = seat(M, scatterDecl({ id: 'X3', encode: { x: temp, y: press, color: product } }));
  await settle();
  const onRow = timeOf(rowPart.part, 'color');
  out.timePick = [timed.of, JSON.stringify(timed.value), JSON.stringify(timed.steps), read.state, read.value, Boolean(read.time),
    Boolean(onRow && onRow.disabled), (onRow && (onRow.title || onRow.getAttribute && onRow.getAttribute('title'))) || ''];
  // T13 / T17: the status words, a cut walk only when an axis says so
  out.status = [M.status.statusWords({ rows: 4, of: 6, system: 1, part: 1, marked: 2, hidden: 1, columns: 3, source: 'wafer', cut: false }),
    M.status.statusWords({ rows: 1, of: 1, system: 0, part: 0, marked: 0, columns: 0, source: 'wafer', cut: true }),
    M.status.statusWords({ rows: 1, of: 1, system: 0, part: 0, startDropped: 2, marked: 1, columns: 1, source: 'wafer', cut: false })];
  // T39: the rows a date function met a text that is not a time on - said where «not a number» is said; a calculator that
  // counts none (no such key) says nothing
  const said = (s) => M.status.statusWords({ rows: 3, of: 3, system: 0, part: 0, marked: 0, columns: 1, source: 'wafer', cut: false, ...s }).filter((w) => /not a (number|time)/.test(w));
  out.notTimeWords = [said({ notNumber: 2, notTime: 1 }), said({ notNumber: 2 })];
  // T30: the bottom line counts the drawn rows an expression left empty on a text (W1 W2 W4 W5 - W3 several, W6 empty)
  const nn = seat(M, scatterDecl({ id: 'S9', encode: { x: { expr: '[product] * 2', words: ['[product] * 2'] }, y: press } }));
  await settle();
  out.notNumberBar = [nn.stats.get('S9').notNumber, M.status.statusWords(nn.stats.get('S9')).filter((w) => w.includes('not a number')),
    M.status.statusWords({ rows: 1, of: 1, notNumber: 1, marked: 0, columns: 1 }).filter((w) => w.includes('not a number'))];
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
  // T34 (lead fe2ba4b1f ①): the page's start gives the declaration's zone to the calculator - a zone not Seoul's.
  const zoned = async () => {
    const elsewhere = { ...declaration, expression_time_zone: 'America/New_York' };
    const zoneFetch = async (url) => {
      const u = String(url);
      const body = u.includes('/api/ledger/declaration') ? elsewhere : u.includes('/api/ledger/subgraph') ? ANSWER : { nodes: [] };
      return { ok: true, status: 200, json: async () => JSON.parse(JSON.stringify(body)) };
    };
    const doc = makeDoc('dark');
    await M.main.boot({ doc, host: doc.createElement('div'), apiBase: '', fetchImpl: zoneFetch, charts: chartsRecorder(), storage: null, theme: 'dark' });
    await settle();
    const day = EXPR.run(EXPR.compile('Date("2026-10-14T02:00:00Z")'), []).value;
    EXPR.useZone(null);
    return day;
  };
  return { same: picture(s) === picture(t), points: t.model ? t.model.points.length : -1,
    siteTheme: [await themed('light', 'dark'), await themed('dark', 'light')], zoned: await zoned() };
}

/** What the root names of the kinds it is handed: a kind's name or a slot key as a string, a `.kind` compared, a slot
 *  read off the encode by name (`encode.cells`) - each where it stands. */
function kindAsks(text) {
  // A kind's slots - a list, or (the table) what it makes of an encode: two columns as a declaration names them.
  const slotsOf = (k) => (typeof k.slots === 'function' ? k.slots({ col1: {}, col2: {} }) : k.slots);
  const names = new Set([...Object.keys(REAL.main.KINDS), ...Object.values(REAL.main.KINDS).flatMap((k) => slotsOf(k).map((s) => s.key))]);
  const found = [];
  const isKind = (n) => n && n.type === 'MemberExpression' && !n.computed && n.property.name === 'kind';
  const isEncode = (n) => n && ((n.type === 'Identifier' && n.name === 'encode') || (n.type === 'MemberExpression' && !n.computed && n.property.name === 'encode'));
  const visit = (n) => {
    if (!n || typeof n.type !== 'string') return;
    if (n.type === 'Literal' && typeof n.value === 'string' && names.has(n.value)) found.push(`'${n.value}'`);
    if (n.type === 'BinaryExpression' && /^[!=]==?$/.test(n.operator) && (isKind(n.left) || isKind(n.right))) found.push('.kind compared');
    if (n.type === 'MemberExpression' && !n.computed && isEncode(n.object) && names.has(n.property.name)) found.push(`encode.${n.property.name}`);
    for (const v of Object.values(n)) {
      if (Array.isArray(v)) v.forEach(visit);
      else if (v && typeof v === 'object' && typeof v.type === 'string') visit(v);
    }
  };
  visit(parseAst(text, { lang: 'js' }));
  return found;
}

/** Every `seedsOf` the client defines - a function or a const of that name, file by file. */
function seedsOfSeats() {
  const out = [];
  const each = (dir) => {
    for (const f of readdirSync(dir)) {
      const p = join(dir, f);
      if (statSync(p).isDirectory()) each(p);
      else if (f.endsWith('.js') && /(?:function|const|let)\s+seedsOf\b/.test(readFileSync(p, 'utf8'))) out.push(p.slice(SRC.length + 1).split('\\').join('/'));
    }
  };
  each(SRC);
  return out;
}

/** T14 / T15 / T19 / T21 / T22: the census and the bundle. `texts` - a file's text as a mutant has it, by its src path. */
function census(texts = {}) {
  const read = (rel) => (texts[`testbed/${rel}`] !== undefined ? texts[`testbed/${rel}`] : readFileSync(join(TB, rel), 'utf8'));
  const files = readdirSync(TB).filter((f) => f.endsWith('.js')).map((f) => [f, read(f)])
    .concat(readdirSync(join(TB, 'kinds')).map((f) => [`kinds/${f}`, read(`kinds/${f}`)]));
  const rootAsks = kindAsks(read('visual_part.js'));
  const css = read('testbed.css');
  const base = texts['spotfire.css'] !== undefined ? texts['spotfire.css'] : readFileSync(join(SRC, 'spotfire.css'), 'utf8');
  const colours = (text) => [...text.replace(/\/\*[\s\S]*?\*\//g, '').matchAll(/#[0-9A-Fa-f]{3,8}\b|rgba?\([^)]*\)/g)].map((m) => m[0]);
  const cssColours = { testbed: colours(css), base: colours(base) };
  // T25: tokens.css holds the measured values - each theme's block and the shared one
  const tokens = texts['tokens.css'] !== undefined ? texts['tokens.css'] : readFileSync(join(SRC, 'tokens.css'), 'utf8');
  const blockOf = (head) => { const at = tokens.indexOf(head); return at < 0 ? '' : tokens.slice(at, tokens.indexOf('\n}', at)); };
  const valueIn = (block, name) => { const m = new RegExp(`${name}:\\s*([^;]+);`).exec(block); return m ? m[1].trim() : null; };
  const blocks = { light: blockOf(':root[data-theme="light"] {'), dark: blockOf(':root[data-theme="dark"] {'), both: blockOf('/* ── Spotfire standard — what both themes share') };
  const measured = Object.entries(MEASURED).flatMap(([side, want]) => Object.entries(want).filter(([name, v]) => valueIn(blocks[side], name) !== v)
    .map(([name, v]) => `${side} ${name} ${valueIn(blocks[side], name)} not ${v}`));
  // ...and every token the canvas reads is defined there
  const palNames = [REAL.palette.TOKENS.bg, REAL.palette.TOKENS.text, REAL.palette.TOKENS.axis, REAL.palette.TOKENS.active, REAL.palette.TOKENS.brush,
    ...REAL.palette.TOKENS.one, ...REAL.palette.TOKENS.cat.flat()];
  const undefinedNames = palNames.filter((name) => !new RegExp(`${name}:`).test(tokens));
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
  return { callers, kindsFilter, bundle, rootAsks, seeds: seedsOfSeats(), cssColours, measured, undefinedNames,
    // the canaries: the walk reads real text - the scatter kind names its own slots; the css has its colours by var();
    // the token blocks were found
    canary: [kindAsks(read('kinds/scatter.js')).length > 0, (base.match(/var\(--sf-/g) || []).length > 0, Object.values(blocks).every((b) => b.length > 100)] };
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
  eq('T40 the marks: several a mark each, the one value the same on all; two several from the same records paired; from different records the row not drawn and why; a mark its row\'s',
    out.marks, [[['R0#0', 'R0', 'R0', '5', 'p'], ['R0#1', 'R0', 'R0', '5', 'q'], ['R1#0', 'R1', 'R1', '1', 'a'], ['R1#1', 'R1', 'R1', '2', 'b']],
      [['R2', 'X and Y come from different records — pick a reduce']]]);
  eq('T36 a slot\'s scale: declared number / datetime continuous; a string or no type by its values (all numbers, all times continuous); the pick wins - a datetime categorical in time order; nothing categorical',
    [out.scales, out.timeOrder], [['continuous', 'continuous+time', 'continuous', 'categorical', 'categorical', 'continuous+time', 'categorical+time', 'continuous', 'categorical'],
      ['2026-10-02T01:00:00+09:00', '2026-10-01T20:00:00Z']]);
  eq('T38 a continuous Color by: a ramp of the first category colour - the most itself, the least toward the background, no categories; no value the one colour',
    out.ramp, [0, '10', '30', '#1060C0', '#1060C0', '#CFDFF2', true, '#888888']);
  eq('T5 the scatter model: two values each drawn, a mark of none or not one value not drawn (the root spreads several - T40); a marked point its colour, the rest mixed 20 % toward the background; legend dim where nothing marked',
    out.scatter, { drawn: ['W1', 'W2', 'W4', 'W5'], notDrawn: 2, kinds: ['value', 'value'], marked: '#6489FA', dimmed: '#363D54',
      legend: [['A', false, ['W1', 'W4']], ['B', false, ['W2', 'W5']], ['(Multiple)', true, ['W3']]] });
  eq('T6 a drag marks the points its rectangle holds - x and y both inside', out.drag, [['W2', 'W4'], ['W4'], []]);
  eq('T7 the cross table: a row with two values stands in both; a cell folds its rows\' values (Avg over the union, not of averages); totals; a cell with a marked row marked',
    out.cross, { rows: ['L1', 'L2', '(Empty)'], cols: ['A', 'B', '(Empty)'],
      grid: [[[2, ['W1', 'W3'], true], [2.5, ['W2', 'W3'], false], [null, [], false]], [[4, ['W4'], false], [5, ['W5'], false], [null, [], false]],
        [[null, [], false], [null, [], false], [null, ['W6'], false]]],
      rowTotals: [2, 4.5, null], colTotals: [2.6666666666666665, 3.3333333333333335, null], total: 3 });
  eq('T27 an expression slot reads through the calculator: a row\'s own value row by row (a list several, none empty, not walked missing); folded (a list its items); a cross cell as the table with no cell slot and as the slot counted; the title its text',
    [out.exprReads, out.exprFolds, out.exprCross],
    [[['one', 1], ['one', 0], ['several', null], ['empty', null], ['missing', null]], [1, 2, 0], [true, true, 'Avg([wafer]) per lot and product']]);
  eq('T30 an operator over a text that is not a number: the row empty and marked; a list several; an empty value empty, not marked; the bottom line counts the drawn rows so marked',
    [out.notNumber, page.notNumberBar], [[['empty', true], ['several', false], ['empty', false]], [4, ['4 rows not a number'], ['1 row not a number']]]);
  eq('T37 a pick in the declaration draws its axis so; the Scale chips on X · Y · Color whatever the type (the lit one the scale drawn), none on a role-fixed slot',
    page.partScale, ['category', 'value', ['categorical*', 'continuous'], ['categorical', 'continuous*'], ['categorical*', 'continuous'], []]);
  eq('T39 the rows not a time said where «not a number» is said; none counted, nothing said', page.notTimeWords, [['2 rows not a number', '1 row not a time'], ['2 rows not a number']]);
  eq('T35 a cross table with no cell slot: its Cell values pill says UniqueCount(rows); one declared, its own words', page.cellsPill, ['UniqueCount(rows)', 'Avg(press · value)']);
  eq('T44 several on a paint slot (Color by, Shape by) one «(Multiple)» category, last, its own colour, a press marking its rows; on a placing slot (Panel by, Marker by) the row in each value',
    page.multiple, [['A', 'B', '(Multiple)'], 2, true, 1, ['W3'], ['W3'], ['A', 'B', '(Multiple)'], [['A', true], ['B', true], ['(Empty)', false]], ['A', 'B'], '(Multiple)', ['A', 'B', '(Multiple)']]);
  eq('T45 one order of categories - numbers by their value before text, (Empty) and (Multiple) last; the cross table\'s row heads, a category axis, the legend and the panels in it',
    page.order, [['1', '2', '10', '11', 'A', 'B', '(Empty)', '(Multiple)'], ['1', '2', '10', '11'], ['1', '2', '10', '11'], ['1', '2', '10', '11'], ['1', '2', '10', '11']]);
  eq('T43 a slot of days says its days - every time the page zone\'s midnight: «YYYY-MM-DD» on the cross row heads, the category ticks, the legend, the tooltip, the hub\'s value the time itself; one not midnight - every time as the grid says it',
    [page.days, page.dayText],
    [[[['2026-11-24', '2026-11-25'], ['2026-11-24', '2026-11-25'], ['2026-11-24', '2026-11-25'], ['2026-11-24T00:00:00+09:00', '2026-11-25T00:00:00+09:00'], 'made: 2026-11-24'],
      [['2026-11-24T00:00:00+09:00', '2026-11-24T00:00:00Z', '2026-11-25T00:00:00+09:00'].map(localStamp), ['2026-11-24T00:00:00+09:00', '2026-11-24T00:00:00Z', '2026-11-25T00:00:00+09:00'].map(localStamp),
        ['2026-11-24T00:00:00+09:00', '2026-11-24T00:00:00Z', '2026-11-25T00:00:00+09:00'].map(localStamp),
        ['2026-11-24T00:00:00+09:00', '2026-11-24T00:00:00Z', '2026-11-25T00:00:00+09:00'], `made: ${localStamp('2026-11-24T00:00:00+09:00')}`]],
      [true, false, '2026-11-24', localStamp('2026-11-24T00:00:00Z'), localStamp('2026-11-24T00:00:00+09:00')]]);
  eq('T42 the same walk on four kinds (scatter, table, cross table, map) on the same slots: the root\'s marks the same; the table a line a mark, a line its row\'s',
    page.sameMarks, [7, 7, 7, 7, 7, ['W3']]);
  eq('T41 the sheet draws the root\'s refusal (#MANY and why); a cell holds a row\'s two marks once (its count the rows)',
    page.rootRefusal, ['empty', '#MANY', '2 values — wrap in an aggregate', [['W9']]]);
  eq('T34 «time» in the picker: on a route the slot reads its last edge\'s time (of time, the value kept); on «(row)» off with its reason',
    page.timePick, ['time', JSON.stringify(temp.value), JSON.stringify(temp.steps), 'one', new Date(T0).toISOString(), true, true, 'No time on this route']);
  eq('T31 a way in the brackets: its end node\'s name; a row it does not reach empty; folded over its ends; two ends several - and Custom expression starts from the route chosen (its reduce around it), the check reading a way as the row does',
    [out.ways, page.wayStart], [[['one', 'L1'], ['empty', null], ['one', 5.5], ['several', null]],
      ['[measures.value]', 'Avg([measures.value])', '[in_lot.name]', '', 'No value named in_lot.nope on wafer', '']]);
  eq('T32 Marked() in a slot: the page answer for the row - true, false, unknown empty', out.marked, [['one', true], ['one', false], ['empty', null]]);
  eq('T33 a column the walk declares datetime: Max the latest instant, as written; undeclared - a number fold, nothing', out.typed,
    [['one', '2026-10-03T00:00:00Z', { 'measures.at': 'datetime' }], ['empty', null, null]]);
  eq('T29 a condition on an expression slot carries the expression and is judged by it; two on one row type stay two',
    out.exprCondition, ['If([product] = "A", 1, 0)', ['W1', 'W4'], true]);
  eq('T23 each kind words its own title: the scatter «y vs. x»; the cross table its cells per rows and columns, no cell slot Count',
    out.titles, ['press · value vs. temp · value', 'Avg(press · value) per lot and product', 'UniqueCount(rows) per lot and product']);
  eq('T8 hubs: members take the hub\'s sign, a + wins over a -, a node stands as itself; a hub holds its members; said in words',
    out.hubs, [{ positive: ['W1', 'W2', 'W3'], negative: ['W9'] }, true, 0, 'wafer · lot = L1']);
  eq('T20 the walk page\'s reading of a marking is the same function - no opener: each entry itself, the marking\'s order, an absent sign no seed',
    out.walkSeeds, { positive: ['A', 'C'], negative: ['B'] });
  eq('T26 the palette a canvas draws with is the document root\'s tokens - each by its name, trimmed; the categories repeat past the seventh; a short hex mixed as its long one',
    out.palette, ['#111111', '#222222', '#333333', '#444444', 'rgba(1, 2, 3, 0.5)', ['#555555', '#666666'], ['#000001', '#111111'], ['#000007', '#111117'], 7, ['#000002', '#111112'], '#E0E7FE', '#E0E7FE']);
  eq('T28 Custom expression: a text that does not read says why and the slot stays; a name the rows do not have says so; a valid one is the slot (Color by: its list of columns, one) and its values drawn',
    page.custom, ['The expression ends too soon', true, 'No value named nope on wafer',
      [{ expr: 'If([product] = "A", "is A", "not A")', words: ['If([product] = "A", "is A", "not A")'] }], ['is A', 'not A']]);
  eq('T16 the picker\'s routes are the walk table\'s «+ Column» routes (reach_table routesFrom) - no second list', out.routes, true);
  // the row walk, then one value walk for x and y together (both measures, one step - the second waits for the first);
  // W3's two temps two points (x and y the scatter's own slots; its two products the one look of Color by) - W6 none
  eq('T9a All walks the row type described; the rows and counts; every drawable point drawn - a several x a point each',
    [page.allAsked, page.allStats, page.drawnPoints], [[['wafer', null], [null, 'W1']], { rows: 6, of: 6, system: 0, part: 0, marked: 0, columns: 3, source: 'wafer', cut: false }, 6]);
  eq('T9b a drag marks what the rectangle holds, replacing; the status bar counts it (W3 a row)', [page.dragMarked, page.dragStats], [['W2', 'W3', 'W4'], 3]);
  eq('T9c a cross table cell marks its hub whole; the scatter draws its members marked', [page.hubMark, page.hubShown],
    [[1, true, ['W1', 'W3']], ['W1', 'W3#0', 'W3#1']]);
  eq('T9c\' «K marked rows» counts the part\'s rows the marking holds - one hub entry of two members is 2', page.hubCounted, [1, 2]);
  eq('T9d the system filter\'s start side keeps the start nodes first and walks again from the kept ones', page.startSide,
    { asked: [['W1', 'W4'], ['W4'], WAFERS], startDropped: 1, system: 3 });
  eq('T9f the system filter changed: its start side judged again - widened, the dropped start comes back; narrowed past all, none; no new walk for the seeds; another system filter named walks again',
    // asked: the row walks two, then a value walk a set of rows - the rows of the widened filter once (the last step
    // has the same rows: the value walk in hand)
    page.filterChanged, [{ rows: 1, startDropped: 1, asked: 3 }, { rows: 2, startDropped: 0, asked: 4 }, { rows: 0, startDropped: 2, asked: 4 },
      { rows: 2, startDropped: 0, asked: 4 }]);
  eq('T9e the received side (system) and the part\'s own filter count apart; a marked node they hide is said', page.twoLayers,
    { rows: 3, of: 6, system: 2, part: 1, hidden: 1 });
  eq('T10 two scatters on one page: a slot changed in one stays there - it alone draws again and lets its old chart go; the other one stands',
    page.twoParts, [['x', 'y'], ['x', 'y'], 1, true, false, true]);
  eq('T11 a third kind draws through the same root: its title, its own declaration\'s field and slot reduce; the template\'s pills - its slot on its tray; no legend with nothing in it (no Marker by, Color by or Shape by - lead 10-14)',
    page.kindAdd, { drawn: ['rows 6 · every 3 · Max'], title: ['List of Max(temp · value)'], statTitle: 'List of Max(temp · value)',
      pills: [['Max(temp · value)', true]] });
  eq('T19 census: the root names no kind - no kind name or slot key as a string, no .kind compared, no slot read off encode by name',
    [counted.rootAsks, counted.canary], [[], [true, true, true]]);
  eq('T21 census: one seedsOf in the client - the marking store\'s', counted.seeds, ['rnd_board/marking_store.js']);
  eq('T22 census: the Spotfire base layer and testbed.css write no colour - every one a --sf-* token', counted.cssColours, { testbed: [], base: [] });
  eq('T25 the Spotfire tokens hold the measured values (§11) in each theme\'s block and the shared one, and every token the canvas reads is defined',
    [counted.measured, counted.undefinedNames], [[], []]);
  eq('T13 the status words: N of M, the drops (the start side\'s when not 0), marked rows and hidden, columns, the row type; a cut walk said',
    page.status, [['4 of 6 rows', 'system −1 · part −1', '2 marked rows · hidden 1', '3 columns', 'wafer'],
      ['1 of 1 rows', 'filter over a cut walk', '0 marked rows', '0 columns', 'wafer'],
      ['1 of 1 rows', 'start −2 · system −0 · part −0', '1 marked row', '1 columns', 'wafer']]);
  eq('T17 a cut walk is the board\'s reading of truncated (an axis true), not «truncated is there»', page.cut, [false, true]);
  eq('T12 Save, then a new page from it: the same declaration, the same points', { same: saved.same, points: saved.points }, { same: true, points: 6 });
  eq('T18 the site\'s theme is the page\'s - the walk page\'s parts on it (the start picker) wear the same tokens', saved.siteTheme, ['dark', 'light']);
  eq('T34 the page\'s start gives the declaration\'s zone to the calculator - a day cut in New York, not Seoul', saved.zoned, '2026-10-13T00:00:00-04:00');
  eq('T14 census: the visual part is the one caller of the filter; no kind imports it', [counted.callers, counted.kindsFilter], [['visual_part.js'], []]);
  if (counted.bundle) eq('T15 the bundle: the testbed chunk under 700 kB, ECharts in no other page\'s chunk', counted.bundle, { testbedUnder700k: true, chartsElsewhere: 0 });
  return { ran: names.length, names, failures };
}

console.log('\n[1] the visual testbed');
const run = async (M, texts) => suite(await measure(M), await parts(M), await reopen(M), census(texts));
const base = await run(REAL);
let ran = base.ran;
let failed = base.failures.length;

const swap = (text, from, to) => {
  if (!text.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`);
  return text.split(from).join(to);
};
const MUTANTS = [
  // ⚠️ M1-M3 (an even median the lower middle · a fold of nothing 0 · Latest picks one at the newest time) moved with
  //    the fold to src/expression.js - expression_vectors_harness X20 · X21 · X17. What stays here is the bridge.
  { id: 'M1', what: 'the test bed fold folds by another name than its reduce', catches: 'T1 the reduces', file: 'testbed/aggregate.js',
    mutate: (t) => swap(t, '  const { value, n, ...rest } = foldItems(reduce, reads || []);', "  const { value, n, ...rest } = foldItems('Count', reads || []);") },
  { id: 'M4', what: 'several values drawn as the first', catches: 'T3', file: 'testbed/slot.js',
    mutate: (t) => swap(t, "  return values.length === 1 ? { state: 'one', value: values[0], n: reads.length, ...time } : { state: 'several', values, n: reads.length, ...time };",
      "  return { state: 'one', value: values[0], n: reads.length, ...time };") },
  { id: 'M5', what: 'a one-valued slot not taken as Latest', catches: 'T3', file: 'testbed/slot.js',
    mutate: (t) => swap(t, "const reduce = slot.reduce || (oneValued ? 'Latest' : null);", 'const reduce = slot.reduce || null;') },
  { id: 'M6', what: 'a condition holds for every type', catches: 'T4', file: 'testbed/filter.js',
    mutate: (t) => swap(t, '  if (!node || node.type !== condition.row) return true;', '  if (!node) return true;') },
  { id: 'M7', what: 'conditions OR, not AND', catches: 'T4', file: 'testbed/filter.js',
    mutate: (t) => swap(t, 'list.every((c) => nodePasses(', 'list.some((c) => nodePasses(') },
  { id: 'M50', what: 'the page\'s start does not give the declaration\'s zone to the calculator', catches: 'T34', file: 'testbed/main.js',
    mutate: (t) => swap(t, '  useZone(declaration.ok ? declaration.zone : null);', '  void 0;') },
  { id: 'M8', what: 'a period closed at its end', catches: 'T4', file: 'testbed/filter.js',
    mutate: (t) => swap(t, '!(Number.isFinite(to) && t >= to)', '!(Number.isFinite(to) && t > to)') },
  { id: 'M9', what: 'a dimmed mark keeps its colour (no mix)', catches: 'T5', file: 'testbed/color_by.js',
    mutate: (t) => swap(t, 'return { fill: mix(c.fill, palette.bg), line: mix(c.line, palette.bg),', 'return { fill: c.fill, line: c.line,') },
  // M10 (a several drawn by the scatter) retired 10-14: the root spreads several into marks (units.js marksOf) - T40's mutants
  { id: 'M60', what: 'a several read not spread - the row drawn as one', catches: 'T40', file: 'testbed/units.js',
    mutate: (t) => swap(t, "    if (!many.length) { marks.push({ ...row, ids: [row.id], row: row.id }); continue; }", "    if (true) { marks.push({ ...row, ids: [row.id], row: row.id }); continue; }") },
  { id: 'M61', what: 'two several slots paired by order, not by record', catches: 'T40', file: 'testbed/units.js',
    mutate: (t) => swap(swap(t, '      if (!same) { dropped.push({ id: row.id, why: PAIR_WORDS(words(many[0]), words(many[1])) }); continue; }', '      if (false) { continue; }'), '      picks = recs[0].map((rec) => lists.map((l) => l.find((r) => r.record === rec).value));', '      picks = lists[0].map((_, i) => lists.map((l) => l[i].value));') },
  { id: 'M62', what: 'a mark forgets its row - a press marks nothing', catches: 'T40', file: 'testbed/units.js',
    mutate: (t) => swap(t, '      marks.push({ ...row, id: `${row.id}#${k}`, ids: [row.id], row: row.id, reads });', '      marks.push({ ...row, id: `${row.id}#${k}`, ids: [`${row.id}#${k}`], row: row.id, reads });') },
  { id: 'M72', what: 'several on a paint slot the one look, no category', catches: 'T44', file: 'testbed/color_by.js',
    mutate: (t) => swap(t, "read.state === 'several' ? MULTIPLE : null);", 'null);') },
  { id: 'M73', what: '«(Multiple)» sorted as text - first', catches: 'T44', file: 'testbed/slot.js',
    mutate: (t) => swap(t, '    if (tail(a) || tail(b)) return tail(a) - tail(b);\n', '') },
  { id: 'M74', what: 'numbers sorted as text', catches: 'T45', file: 'testbed/slot.js',
    mutate: (t) => swap(t, '    if (x !== null && y !== null && x !== y) return x - y;\n', '') },
  { id: 'M75', what: 'the cross table sorts its heads its own way - as text', catches: 'T45', file: 'testbed/kinds/cross_table.js',
    mutate: (t) => swap(t, '    const level = categoryCompare(Boolean(ctx.scale && ctx.scale(key).time));', '    const level = (a, b) => (a < b ? -1 : a > b ? 1 : 0);') },
  { id: 'M67', what: 'a slot of days never said - the scale has no day', catches: 'T43', file: 'testbed/slot.js',
    mutate: (t) => swap(t, '  const day = time && values.length > 0 && values.every((v) => dayText(v) !== null);', '  const day = time && values.length > 0;') },
  { id: 'M68', what: 'the one place says a time of a slot of days as any time', catches: 'T43', file: 'testbed/slot.js',
    mutate: (t) => swap(t, '  return (day && dayText(value)) || (time && timeText(value)) || valueWords(value);', '  return (time && timeText(value)) || valueWords(value);') },
  { id: 'M69', what: 'the root hands the kinds no day', catches: 'T43', file: 'testbed/visual_part.js',
    mutate: (t) => swap(t, '    return valueText(value, Boolean(time || s.time), Boolean(s.day));', '    return valueText(value, Boolean(time || s.time), false);') },
  { id: 'M70', what: 'the cross table draws a row head as it came', catches: 'T43', file: 'testbed/kinds/cross_table.js',
    mutate: (t) => swap(t, "sf-table__row sf-table__row--in', said('rows', run.word));", "sf-table__row sf-table__row--in', run.word);") },
  { id: 'M71', what: 'a category tick as it came', catches: 'T43', file: 'testbed/kinds/scatter.js',
    mutate: (t) => swap(t, "formatter: kind === 'value' ? tickWords : kind === 'category' && text ? text : undefined },", "formatter: kind === 'value' ? tickWords : undefined },") },
  { id: 'M66', what: 'the root\'s own slots (Color by) split a row too - W3 left out for its two products', catches: 'T9a', file: 'testbed/visual_part.js',
    mutate: (t) => swap(t, '    const drawn = own.map((s) => s.key).filter((k) => keysRead.includes(k));', '    const drawn = keysRead;') },
  // in the root's call: a units.js copy reaches M.units only - the root imports the original
  { id: 'M65', what: 'the root spreads a points kind only - a table, a cross table, a map draw rows', catches: 'T42', file: 'testbed/visual_part.js',
    mutate: (t) => swap(t, '    const spread = (some) => spreadUnits(', '    const spread = (some) => (!this.kind.units && !this.kind.cells) ? { units: some.map((r) => ({ ...r, ids: [r.id], row: r.id })), dropped: [] } : spreadUnits(') },
  { id: 'M63', what: 'the sheet keeps its own «several» - no root refusal', catches: 'T41', file: 'testbed/units.js',
    mutate: (t) => swap(t, "  for (const [k, r] of many) reads[k] = { state: 'empty', n: 0, error: '#MANY', why: MANY_WORDS(r.n || (r.values || []).length) };", '') },
  { id: 'M64', what: 'a cell counts a row\'s two marks twice', catches: 'T41', file: 'testbed/slot.js',
    mutate: (t) => swap(t, '      for (const id of row.ids || [row.id]) if (!cell.seen.has(id)) { cell.seen.add(id); cell.ids.push(id); }', '      for (const id of row.ids || [row.id]) cell.ids.push(id);') },
  { id: 'M11', what: 'a drag tests only x', catches: 'T6', file: 'testbed/kinds/scatter.js',
    mutate: (t) => swap(t, ' && inside(coordRange[1], at(model.yKind, option.yAxis, p.y)))', ')') },
  { id: 'M12', what: 'a row with two values counted in its first only', catches: 'T3', file: 'testbed/slot.js',
    mutate: (t) => swap(t, "  if (read.state === 'several') return read.values;", "  if (read.state === 'several') return read.values.slice(0, 1);") },
  { id: 'M13', what: 'a total folded over its cells\' rows twice (a row in two cells)', catches: 'T7', file: 'testbed/kinds/cross_table.js',
    mutate: (t) => swap(t, '    const once = [...new Set(ids)];', '    const once = [...ids];') },
  { id: 'M14', what: 'a - beats a + for a node in two hubs', catches: 'T8', file: 'rnd_board/marking_store.js',
    mutate: (t) => swap(t, '    for (const node of open(id)) if (sign.get(node) !== SIGN.CASE) sign.set(node, s);', '    for (const node of open(id)) sign.set(node, s);') },
  { id: 'M14b', what: 'the walk page\'s reading keeps an absent sign as a control (the - list every not-+)', catches: 'T20', file: 'rnd_board/marking_store.js',
    mutate: (t) => swap(t, '  return { positive: of(SIGN.CASE), negative: of(SIGN.CONTROL) };', '  return { positive: of(SIGN.CASE), negative: [...sign].filter(([, s]) => s !== SIGN.CASE).map(([id]) => id) };') },
  { id: 'M15', what: 'All walks with no seed', catches: 'T9a', file: 'testbed/visual_part.js',
    mutate: (t) => swap(t, 'const params = seeds.all ? { ...this.budget(), seed_type: rows, collect: ask.collect }', 'const params = seeds.all ? { ...this.budget(), collect: ask.collect }') },
  { id: 'M16', what: 'a drag adds instead of replacing', catches: 'T9b', file: 'testbed/visual_part.js',
    mutate: (t) => swap(t, "    if (mode === 'add') { for (const id of ids) this.markings.set(this.writes, id, sign); return; }", '    { for (const id of ids) this.markings.set(this.writes, id, sign); return; }') },
  { id: 'M17', what: 'a hub not opened into its members when the marking is shown', catches: 'T8', file: 'testbed/hubs.js',
    mutate: (t) => swap(t, '  return (entries || []).some(([id]) => book.open(id).includes(nodeId));', '  return (entries || []).some(([id]) => id === nodeId);') },
  { id: 'M17b', what: 'the book opens a hub as itself - its members never seeds', catches: 'T8', file: 'testbed/hubs.js',
    mutate: (t) => swap(t, '  open(id) { return isHubId(id) ? this.membersOf(id) : [id]; }', '  open(id) { return [id]; }') },
  { id: 'M18', what: 'the start side not walked again', catches: 'T9d', file: 'testbed/visual_part.js',
    mutate: (t) => swap(t, '      if (dropped) {', '      if (false) {') },
  { id: 'M19', what: 'the part\'s own filter not applied', catches: 'T9e', file: 'testbed/visual_part.js',
    mutate: (t) => swap(t, 'afterSystem.kept, this.decl.filter || [], this.oneValued', 'afterSystem.kept, [], this.oneValued') },
  { id: 'M20', what: 'a redraw keeps its old chart (two charts on one box)', catches: 'T10', file: 'testbed/visual_part.js',
    mutate: (t) => swap(t, '    if (this.drawn) { this.drawn.dispose(); this.drawn = null; }\n', '') },
  { id: 'M21', what: 'a cut walk read as «truncated is there»', catches: 'T17', file: 'testbed/visual_part.js',
    mutate: (t) => swap(t, 'cut: [this.rowWalk, ...this.values.values()].some((w) => w && !w.complete && !w.receiving),', 'cut: Boolean(this.answer.truncated),') },
  { id: 'M22', what: 'the status bar leaves out the drops', catches: 'T13', file: 'testbed/status_part.js',
    mutate: (t) => swap(t, '  if (s.startDropped || s.system || s.part || s.limit) {', '  if (false) {') },
  { id: 'M22b', what: 'the status bar leaves out the start side\'s drop (the code before)', catches: 'T13', file: 'testbed/status_part.js',
    mutate: (t) => swap(t, "s.startDropped ? `start −${n(s.startDropped)}` : null, ", '') },
  { id: 'M25', what: 'a system filter change folds again only - the start side not judged again (the code before)', catches: 'T9f', file: 'testbed/visual_part.js',
    mutate: (t) => swap(t, "(name) => { if (name === this.decl.system) this.load(); }", "(name) => { if (name === this.decl.system) this.refold(); }") },
  { id: 'M26', what: 'another system filter named folds again only - the comment\'s «system filter walks again» untrue (the code before)', catches: 'T9f', file: 'testbed/visual_part.js',
    mutate: (t) => swap(t, 'JSON.stringify([next.start, next.row, next.system, next.route || null]) !== JSON.stringify([this.decl.start, this.decl.row, this.decl.system, this.decl.route || null])',
      'JSON.stringify([next.start, next.row, next.route || null]) !== JSON.stringify([this.decl.start, this.decl.row, this.decl.route || null])') },
  { id: 'M27', what: 'a filter change walks from every seed again (the walk in hand not taken)', catches: 'T9f', file: 'testbed/visual_part.js',
    mutate: (t) => swap(t, 'const held = walks.find(', 'const held = false && walks.find(') },
  { id: 'M28', what: '«marked» counts the marking\'s entries - a hub one (the code before)', catches: "T9c'", file: 'testbed/visual_part.js',
    mutate: (t) => swap(t, 'marked: received.filter(marked).length,', 'marked: this.markings.entries(this.reads).length,') },
  { id: 'M29', what: 'the root words the title by asking the kind (the code before)', catches: 'T19', file: 'testbed/visual_part.js',
    mutate: (t) => swap(t, "    return this.kind ? this.kind.title(this.decl.encode || {}, this.decl) : '';",
      "    const e = this.decl.encode || {};\n    if (this.decl.kind === 'scatter') return `${slotWords(e.y)} vs. ${slotWords(e.x)}`;\n    return `${slotWords(e.cells) === '(None)' ? 'Count' : slotWords(e.cells)} per ${slotWords(e.rows)} and ${slotWords(e.columns)}`;") },
  { id: 'M30', what: 'the root hands every kind the cell slot\'s reduce and the marker size, not the declaration (the code before)', catches: 'T11', file: 'testbed/visual_part.js',
    mutate: (t) => swap(t, '{ paint, colored, askMarked, label, shape, palette: this.palette(), declaration: this.decl, start,', '{ paint, colored, askMarked, label, shape, palette: this.palette(), reduce: encode.cells && encode.cells.reduce, markerPct: this.decl.markerPct, start,') },
  // M31 (a words-only pill opens the picker) retired 10-14: the template draws a pill only for a slot it holds.
  { id: 'M32', what: 'the cross table folds a cell without its slot\'s reduce - every cell Count', catches: 'T7', file: 'testbed/kinds/cross_table.js',
    mutate: (t) => swap(t, '    return foldRows(cellSlot, once.map((id) => byId.get(id).raw.cells), ctx.askMarked);', '    return foldRows(cellSlot && { ...cellSlot, reduce: undefined }, once.map((id) => byId.get(id).raw.cells), ctx.askMarked);') },

  { id: 'M33', what: 'the scatter\'s title y and x swapped', catches: 'T23', file: 'testbed/kinds/scatter.js',
    mutate: (t) => swap(t, '`${slotWords(encode.y)} vs. ${slotWords(encode.x)}`', '`${slotWords(encode.x)} vs. ${slotWords(encode.y)}`') },
  { id: 'M34', what: 'the cross table\'s title without a cell slot says (None), not UniqueCount(rows)', catches: 'T23', file: 'testbed/kinds/cross_table.js',
    mutate: (t) => swap(t, "${encode.cells ? slotWords(encode.cells) : ROWS_COUNT}", '${slotWords(encode.cells)}') },
  { id: 'M52', what: 'an empty Cell values pill says (None) though the cells count their rows', catches: 'T35', file: 'testbed/visual_part.js',
    mutate: (t) => swap(t, '    p.textContent = opts.words || empty || slotWords(slot);', '    p.textContent = opts.words || slotWords(slot);') },
  { id: 'M23', what: 'a saved page reopens on the layout, not on what was saved', catches: 'T12', file: 'testbed/main.js',
    mutate: (t) => swap(t, '  const layout = laidOut(LAYOUT, saved, entities());', '  const layout = laidOut(LAYOUT, null, entities());') },
  { id: 'M24', what: 'the site\'s theme left as it came (the code before: a white picker on the dark page)', catches: 'T18', file: 'testbed/main.js',
    mutate: (t) => swap(t, "  root.setAttribute('data-theme', theme);\n", '') },
];
MUTANTS.push(
  { id: 'M35', what: 'a measured colour moved in the move to tokens (the dark part\'s ground)', catches: 'T25', file: 'tokens.css',
    mutate: (t) => swap(t, '  --sf-bg: #2A2A2A;', '  --sf-bg: #2B2B2B;') },
  { id: 'M36', what: 'a colour written in the base layer, not a token', catches: 'T22', file: 'spotfire.css',
    mutate: (t) => swap(t, '.sf-table td.is-marked { background: var(--sf-marked);', '.sf-table td.is-marked { background: #00A650;') },
  { id: 'M37', what: 'a token the canvas reads defined nowhere', catches: 'T25', file: 'tokens.css',
    mutate: (t) => swap(t, '--sf-cat-7-line: #BC7A4B;', '--sf-cat-7-edge: #BC7A4B;') },
  { id: 'M38', what: 'the palette reads a category\'s line as its fill', catches: 'T26', file: 'testbed/palette.js',
    mutate: (t) => swap(t, '  const pair = ([fill, line]) => [read(fill), read(line)];', '  const pair = ([fill, line]) => [read(line), read(fill)];') },
  { id: 'M40', what: 'the mix reads only the long hex - in the built page #fff mixed to a grey (the code before)', catches: 'T26', file: 'testbed/palette.js',
    mutate: (t) => swap(t, "  const full = s.length === 3 ? [...s].map((c) => c + c).join('') : s;", '  const full = s;') },
  { id: 'M41', what: 'an expression reads a row\'s own value as its label', catches: 'T27', file: 'testbed/slot.js',
    mutate: (t) => swap(t, "  if (has(node.attributes)) return { on: 'node', name };", "  if (has(node.attributes)) return { on: 'label', name: 'name' };") },
  { id: 'M42', what: 'the picker sets an expression it refused', catches: 'T28', file: 'testbed/picker.js',
    mutate: (t) => swap(t, '        if (said) { why.textContent = said; return; }', '        if (said) { why.textContent = said; }') },
  { id: 'M44', what: 'the part counts no row an expression could not take as a number', catches: 'T30', file: 'testbed/visual_part.js',
    mutate: (t) => swap(t, '      notNumber: rows.filter((r) => Object.values(r.reads).some((read) => read.notNumber)).length,', '      notNumber: 0,') },
  { id: 'M45', what: 'the bottom line does not say the rows that are not a number', catches: 'T30', file: 'testbed/status_part.js',
    mutate: (t) => swap(t, "  if (s.notNumber) words.push(`${unitText(n(s.notNumber), 'row')} not a number`);\n", '') },
  { id: 'M48', what: 'the walk\'s column types not handed to the calculator', catches: 'T33', file: 'testbed/slot.js',
    mutate: (t) => swap(t, 'run(c, [calcRow(index, inside, x)], { marked, cell, types })', 'run(c, [calcRow(index, inside, x)], { marked, cell })') },
  { id: 'M46', what: 'Custom expression starts empty with a route chosen (the code before)', catches: 'T31', file: 'testbed/picker.js',
    mutate: (t) => swap(t, 'isExpression(current) ? current.expr : startingExpression(chosen)', "isExpression(current) ? current.expr : ''") },
  { id: 'M47', what: 'the check reads a way as the row\'s own name, so a way the row reads is refused', catches: 'T31', file: 'testbed/picker.js',
    mutate: (t) => swap(t, '      if (!rows.some((id) => nameValue(part.index, part.inside, id, name).value))', '      if (!rows.some((id) => nameValue(part.index, part.inside, id, name.split(\'.\').pop()).value))') },
  { id: 'M50', what: 'the time pick reads the value, not its time', catches: 'T34', file: 'testbed/picker.js',
    mutate: (t) => swap(t, "const next = { steps: chosen.steps || [], end: chosen.end, value, of: 'time',", 'const next = { steps: chosen.steps || [], end: chosen.end, value,') },
  { id: 'M51', what: 'the time pick is on for «(row)»', catches: 'T34', file: 'testbed/picker.js',
    mutate: (t) => swap(t, '        setDisabledReason(it, (chosen.steps || []).length ? null : NO_TIME_HERE);\n', '') },
  { id: 'M53', what: 'the declaration\'s pick is not read', catches: 'T36', file: 'testbed/slot.js',
    mutate: (t) => swap(t, '  if (SCALES.includes(chosen)) return { scale: chosen, time, day };\n', '') },
  { id: 'M54', what: 'a declared number is read by its values', catches: 'T36', file: 'testbed/slot.js',
    mutate: (t) => swap(t, "  if (one && CONTINUOUS_DECLARED.has(one)) return { scale: 'continuous', time, day };\n", '') },
  { id: 'M55', what: 'categories of times sorted as text', catches: 'T36', file: 'testbed/slot.js',
    mutate: (t) => swap(t, '    if (time && isTimeText(a) && isTimeText(b) && Date.parse(a) !== Date.parse(b)) return Date.parse(a) - Date.parse(b);\n', '') },
  { id: 'M56', what: 'the scatter ignores the root\'s scale', catches: 'T37', file: 'testbed/kinds/scatter.js',
    mutate: (t) => swap(t, '  const s = ctx.scale ? ctx.scale(key) : scaleOf(', '  const s = false ? ctx.scale(key) : scaleOf(') },
  { id: 'M57', what: 'the Scale chips shown on every slot', catches: 'T37', file: 'testbed/picker.js',
    mutate: (t) => swap(t, '      if (desc.scalable) {', '      if (true) {') },
  { id: 'M58', what: 'a continuous Color by still paints categories', catches: 'T38', file: 'testbed/color_by.js',
    mutate: (t) => swap(t, "  if (ctx.scale && ctx.scale.scale === 'continuous' && decl.encode && decl.encode.color) return rampOf(rows, palette, ctx.scale.time);\n", '') },
  { id: 'M59', what: 'the rows not a time are not said', catches: 'T39', file: 'testbed/status_part.js',
    mutate: (t) => swap(t, "  if (s.notTime) words.push(`${unitText(n(s.notTime), 'row')} not a time`);\n", '') },
  { id: 'M43', what: 'a condition on an expression slot drops the expression', catches: 'T29', file: 'testbed/condition_editor.js',
    mutate: (t) => swap(t, '    reduce: summary.slot.reduce, expr: summary.slot.expr, words: summary.words, empty: true };', '    reduce: summary.slot.reduce, words: summary.words, empty: true };') },
  { id: 'M39', what: 'the colours handed no palette - the page\'s tokens never reach the canvas', catches: 'T5', file: 'testbed/color_by.js',
    mutate: (t) => swap(t, '  const palette = ctx.palette;\n', "  const palette = { bg: '#000000', one: ['#000000', '#000000'], cat: [['#000000', '#000000']] };\n") },
);
const KEY = { 'testbed/aggregate.js': 'aggregate', 'testbed/slot.js': 'slot', 'testbed/filter.js': 'filter', 'testbed/hubs.js': 'hubs',
  'testbed/kinds/scatter.js': 'scatter', 'testbed/kinds/cross_table.js': 'cross', 'testbed/visual_part.js': 'visual', 'testbed/status_part.js': 'status',
  'testbed/main.js': 'main', 'rnd_board/marking_store.js': 'store', 'testbed/palette.js': 'palette', 'testbed/picker.js': 'picker', 'testbed/condition_editor.js': 'cond',
  'testbed/color_by.js': 'color', 'testbed/units.js': 'units' };
const scored = await scoreMutants(MUTANTS, async (m) => {
  // A stylesheet is no module: its mutant is the census's text alone.
  if (m.file.endsWith('.css')) return run(REAL, { [m.file]: m.mutate(readFileSync(join(SRC, m.file), 'utf8')) });
  const copy = (await loadWithProbe(join(SRC, m.file), { mutate: m.mutate })).module;
  // The census reads the mutant's text too: a mutant that asks the kind again is counted where it asks.
  return run({ ...REAL, [KEY[m.file]]: copy }, { [m.file]: m.mutate(readSourceText(join(SRC, m.file)).text) });
}, { baselineRan: base.ran, baselineNames: base.names, title: '\n  [1] mutants - each must be caught by the check it names.' });
ran += MUTANTS.length;
failed += scored.wrong;

console.log(`\n${ran - failed} passed, ${failed} failed`);
console.log(`ASSERTIONS ${ran} ${failed}`);
if (failed) process.exit(1);
