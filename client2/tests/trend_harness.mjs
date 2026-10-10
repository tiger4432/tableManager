// The trend (walk/trend.js, walk/trend_view.js, lead f984ab01d, a2eb4a516): a point a read of the table's cell, at the
// time of its way's last edge, coloured by its group; numbers on a value axis, words in lanes (the most frequent first,
// the rest «others»); the server's time page (the implementer's contract, faked here) adds the row's other edges, colour
// by where their far end was reached; Load earlier / later widen it. Module, part and page; two parts on one screen.
// The axis (lead 10-10, on the box): the pages' windows and the pressed side's walked points - another side's walked
// point two days off stands at the edge, the window's points keep the width.
//
// CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { makeDoc, flush, walk as walkAll } from './lib/board_dom.mjs';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';
import { indexGraph, groupsOf } from '../src/walk/reach_table.js';
import { entitySeedId } from '../src/rnd_board/api.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src');
const settle = async () => { for (let i = 0; i < 20; i += 1) await flush(); };
const ascii = (t) => String(t).replace(/[^\x00-\x7f]/g, (c) => `\\u${c.charCodeAt(0).toString(16).padStart(4, '0')}`);
const has = (n, cls) => String((n.attrs && n.attrs.class) || n.className || '').split(/\s+/).includes(cls);

const T = (h) => `2026-10-0${h < 10 ? '1' : '2'}T${String(h % 10).padStart(2, '0')}:00:00+00:00`;
const node = (id, type) => ({ id, type, label: id.toUpperCase(), keys: { [type]: id.toUpperCase() } });
const edge = (source, predicate, target, value, h, claim) => ({ id: `${source}>${target}`, source, target, predicate,
  qualifiers: { value }, occurred_at: T(h), claim_id: claim });
// A quantity measured from the + wafer and the − wafer, at hours 3 and 5.
const WALK = {
  generated_at: T(12),
  nodes: [node('wp', 'wafer'), node('wn', 'wafer'), node('q1', 'quantity')],
  edges: [edge('wp', 'measures', 'q1', 30.5, 3, 'c1'), edge('wn', 'measures', 'q1', 11, 5, 'c2')],
  propagation: { ranked: [{ id: 'q1', reach: [1, 1] }] },
};
const STARTS = [{ name: '+', starts: ['wp'] }, { name: '−', starts: ['wn'] }];
const COLUMN = { steps: [{ predicate: 'measures', direction: 'incoming' }], value: { on: 'edge', name: 'value' }, words: ['measures (in)', 'value'] };
// The server's time page: the row's other measures edges - one from the + wafer, one from a wafer neither group reached.
// A wafer the walk never reached, on the time page alone - its id the ledger's, so it can be read (lead 10-11).
const WZ = entitySeedId('wafer', { wafer: 'WZ-9' });
const PAGE = {
  seed: node('q1', 'quantity'),
  nodes: [node('q1', 'quantity'), node('wp', 'wafer'), { id: WZ, type: 'wafer', label: 'WZ-9', keys: { wafer: 'WZ-9' } }],
  edges: [edge('wp', 'measures', 'q1', 30.5, 3, 'c1'), edge('wp', 'measures', 'q1', 29, 1, 'c3'), edge(WZ, 'measures', 'q1', 12, 7, 'c4')],
  page: { mode: 'around', around: T(5), size: 1000, rows: 3, window: { from: T(1), to: T(7) }, earlier: 'E1', has_earlier: true,
    later: 'L1', has_later: false, not_event_time: 0 },
};
// The same walk with the − wafer's edge two days before the page's window.
const WALK_FAR = { ...WALK, edges: [WALK.edges[0], { ...WALK.edges[1], occurred_at: '2026-09-29T05:00:00+00:00' }] };
const TIME = /\d\d-\d\d \d\d:\d\d/;

/** The walk page with `answer` walked: a press on the quantity's + cell, then Load earlier. */
async function pageRun(M, answer) {
  const urls = [];
  const DECL = { entities: [{ type: 'wafer', keys: ['wafer'] }, { type: 'quantity', keys: ['quantity'] }], predicates: [], worlds: [], operating: null };
  const doc = makeDoc('light');
  doc.head = doc.createElement('head');
  const host = doc.createElement('div');
  const handle = M.page.boot(doc, host, { apiBase: '', fetchImpl: async (url) => {
    const u = String(url);
    urls.push(u);
    const body = u.includes('around=') || u.includes('later=') || u.includes('earlier=') ? PAGE : DECL;
    return { ok: true, status: 200, json: async () => body };
  } });
  await settle();
  handle.state.type = 'wafer';
  handle.state.asked = { type: 'wafer', keys: {}, positive: ['wp'], negative: ['wn'] };
  handle.state.run = 'done';
  handle.state.result = answer;
  handle.render();
  // The quantity section's + cell (the wafer section comes first and holds 30.5 too, read the other way).
  // A value cell's value is its value line (C draws its source under it).
  const valueOf = (n) => (n.children || []).filter((k) => k.className === 'wk-val').map((k) => k._text).join(' ');
  const cell = walkAll(host).filter((n) => n.tagName === 'TD' && n.attrs && n.attrs['data-col'] === '0' && /30\.5/.test(valueOf(n))).pop();
  if (cell) cell.dispatch('click', {});
  await settle();
  const q = (u) => Object.fromEntries(new URLSearchParams(String(u || '').split('?')[1] || ''));
  const asks = urls.filter((u) => u.includes('around=') || u.includes('later=') || u.includes('earlier='));
  const title = (walkAll(host).find((n) => n.className === 'wk-trend-title') || {})._text;
  const dots = walkAll(host).filter((n) => n.tagName === 'CIRCLE' && n.attrs && n.attrs['data-key']).map((n) => n.attrs['data-key']).sort();
  const sources = walkAll(host).filter((n) => n.tagName === 'CIRCLE' && n.attrs && n.attrs['data-key'])
    .map((n) => [n.attrs['data-key'], ((n.children || []).find((k) => k.tagName === 'TITLE') || {})._text || '']).sort();
  const edges = walkAll(host).filter((n) => n.tagName === 'TEXT' && has(n, 'wk-trend-edge')).map((n) => n._text.replace(TIME, 'TIME'));
  const note = (walkAll(host).find((n) => n.className === 'wk-note' && TIME.test(n._text || '')) || {})._text || '';
  const earlier = walkAll(host).find((n) => n.tagName === 'BUTTON' && n._text === 'Load earlier');
  if (earlier) earlier.dispatch('click', {});
  await settle();
  const asks2 = urls.filter((u) => u.includes('earlier='));
  return { cell: Boolean(cell), title, ask: asks.length ? q(asks[0]) : null, dots, sources, earlier: asks2.length ? q(asks2[0]).earlier : null,
    edges, local: note.endsWith('local time') };
}

async function seen(M) {
  const out = {};
  const index = indexGraph(WALK);
  const groups = groupsOf(WALK, STARTS);
  // ── the module ──
  const walk = M.trend.walkPoints(index, groups, 'q1', COLUMN);
  out.walk = walk.map((p) => [p.t === Date.parse(T(p.group ? 5 : 3)), p.value, p.group, p.walked, p.key]);
  const page = M.trend.pagePoints(PAGE, groups, 'q1', COLUMN, new Set(walk.map((p) => p.key)));
  out.page = page.map((p) => [p.value, p.group, p.walked, p.key]);
  out.merged = M.trend.mergePoints(walk, page).map((p) => p.key);
  const words = ['A', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J'].map((w, i) => ({ t: i, value: w, group: 0, walked: false, key: `w${i}` }));
  const model = M.trend.trendModel([...walk, ...words, { t: null, value: 1, group: 0, key: 'x' }, { t: 4, value: true, group: 1, key: 'b' }]);
  out.model = [model.numbers.map((p) => p.value), model.lanes, model.words.filter((p) => p.lane === M.trend.OTHERS).map((p) => p.word),
    model.untimed, model.v];
  out.t0 = [M.trend.walkedTime(walk, WALK.generated_at) === Date.parse(T(5)), M.trend.walkedTime([], WALK.generated_at) === Date.parse(T(12)),
    M.trend.walkedTime(walk, WALK.generated_at, 0) === Date.parse(T(3))];
  // ── the part ──
  const part = () => {
    const doc = makeDoc('light');
    const mount = doc.createElement('div');
    doc.body.appendChild(mount);
    return { doc, mount, view: new M.view.TrendView(mount, { doc }) };
  };
  const one = part();
  let asked = [];
  one.view.show({ title: 'Q1 · measures (in) · value', model: M.trend.trendModel(M.trend.mergePoints(walk, page)), groups: ['Positive', 'Negative'],
    t0: Date.parse(T(5)), onEarlier: () => asked.push('earlier'), onLater: () => asked.push('later'), hasEarlier: true, hasLater: false });
  const dots = walkAll(one.mount).filter((n) => n.tagName === 'CIRCLE' && n.attrs['data-key']);
  out.dots = dots.map((d) => [d.attrs['data-key'], ['is-g0', 'is-g1', 'is-other'].find((c) => has(d, c)), has(d, 'is-walked')]).sort();
  out.dashed = walkAll(one.mount).some((n) => n.tagName === 'LINE' && has(n, 'wk-trend-t0'));
  const buttons = walkAll(one.mount).filter((n) => n.tagName === 'BUTTON');
  for (const b of buttons) if (!b.disabled) b.dispatch('click', {});
  out.loads = [buttons.map((b) => [b._text, Boolean(b.disabled), (b.attrs && b.attrs.title) || '']), asked];
  const lanes = part();
  lanes.view.show({ title: 'x', model: M.trend.trendModel(words), groups: ['Positive'], t0: null });
  out.lanes = walkAll(lanes.mount).filter((n) => n.tagName === 'TEXT' && has(n, 'wk-trend-word') && !/^\d\d-/.test(n._text))
    .map((n) => [n._text, has(n, 'is-others')]);
  const none = part();
  none.view.show({ title: 'x', model: M.trend.trendModel([{ t: null, value: 1, group: 0, key: 'n' }]), groups: [], t0: null });
  out.none = walkAll(none.mount).filter((n) => n.className === 'wk-note').map((n) => n._text);
  // Two parts on one screen: each draws its own.
  const doc2 = makeDoc('light');
  const m1 = doc2.createElement('div');
  const m2 = doc2.createElement('div');
  doc2.body.appendChild(m1); doc2.body.appendChild(m2);
  const a = new M.view.TrendView(m1, { doc: doc2 });
  const b = new M.view.TrendView(m2, { doc: doc2 });
  a.show({ title: 'A', model: M.trend.trendModel(walk), groups: ['Positive', 'Negative'], t0: null });
  b.show({ title: 'B', model: M.trend.trendModel(words), groups: ['Positive'], t0: null });
  const circles = (m) => walkAll(m).filter((n) => n.tagName === 'CIRCLE' && n.attrs['data-key']).length;
  out.two = [circles(m1), circles(m2), m1.children[0].children.length, m2.children[0].children.length];
  // ── another side's walked point two days off (lead 10-10) ──
  const farGroups = groupsOf(WALK_FAR, STARTS);
  const farWalk = M.trend.walkPoints(indexGraph(WALK_FAR), farGroups, 'q1', COLUMN);
  const farModel = M.trend.trendModel(M.trend.mergePoints(farWalk, M.trend.pagePoints(PAGE, farGroups, 'q1', COLUMN,
    new Set(farWalk.map((p) => p.key)))), undefined, { windows: [M.trend.windowOf(PAGE)], group: 0 });
  const far = part();
  far.view.show({ title: 'far', model: farModel, groups: ['Positive', 'Negative'], t0: Date.parse(T(3)) });
  const svg = walkAll(far.mount).find((n) => n.tagName === 'SVG' && n.attrs && n.attrs.viewBox);
  const width = svg ? Number(String(svg.attrs.viewBox).split(' ')[2]) : 0;
  const xs = walkAll(far.mount).filter((n) => n.tagName === 'CIRCLE' && n.attrs['data-key']).map((n) => Number(n.attrs.cx));
  out.far = [farModel.t && farModel.t.map((t) => new Date(t).toISOString()), farModel.outside.map((o) => [o.group, o.before, o.n]),
    xs.length, width > 0 && (Math.max(...xs) - Math.min(...xs)) / width >= 0.7,
    walkAll(far.mount).filter((n) => n.tagName === 'TEXT' && has(n, 'wk-trend-edge')).map((n) => n._text.replace(TIME, 'TIME'))];
  // ── the page ──
  const run = await pageRun(M, WALK);
  out.pageRun = [run.cell, run.title, run.ask, run.dots, run.earlier];
  out.pointSources = run.sources;
  // The part alone: a point that carries its source says it on its dot.
  const said = part();
  said.view.show({ title: 'S', model: M.trend.trendModel([{ t: Date.parse(T(3)), value: 1, group: 0, walked: true, key: 's1', source: 'WP · start' }]),
    groups: ['Positive'], t0: null });
  out.dotSource = walkAll(said.mount).filter((n) => n.tagName === 'CIRCLE' && n.attrs && n.attrs['data-key'])
    .map((n) => ((n.children || []).find((k) => k.tagName === 'TITLE') || {})._text || '');
  const farRun = await pageRun(M, WALK_FAR);
  out.farPage = [farRun.ask && farRun.ask.around, farRun.dots, farRun.edges, farRun.local];
  return out;
}

function suite(out) {
  const names = [];
  const failures = [];
  const eq = (name, got, want) => {
    names.push(name);
    const g = ascii(JSON.stringify(got)), w = ascii(JSON.stringify(want));
    if (g === w) { console.log(`  PASS ${name}`); return; }
    failures.push(name);
    console.log(`  FAIL ${name}\n        got  ${g}\n        want ${w}`);
  };
  eq('T1 the walk\'s points: each group\'s reads of the cell, at the time of the way\'s last edge, walked',
    out.walk, [[true, 30.5, 0, true, 'c1'], [true, 11, 1, true, 'c2']]);
  eq('T2 a time page\'s points: an edge each, its group where its far end was reached (none: another row\'s), walked when the walk brought it',
    out.page, [[30.5, 0, true, 'c1'], [29, 0, false, 'c3'], [12, null, false, 'c4']]);
  eq('T3 the walk\'s points with a page\'s: one point a key', out.merged, ['c1', 'c2', 'c3', 'c4']);
  eq('T4 numbers on the value axis; words in lanes - the most frequent first, past eight «others»; a point without a time counted',
    out.model, [[30.5, 11], ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'others'], ['I', 'J', '✓'], 1, [11, 30.5]]);
  eq('T5 the walked time: the pressed side\'s latest walked point\'s (any side\'s when none is named), else the answer\'s', out.t0,
    [true, true, true]);
  eq('T6 a dot a point: its group\'s colour, other rows faint, the walked ringed', out.dots,
    [['c1', 'is-g0', true], ['c2', 'is-g1', true], ['c3', 'is-g0', false], ['c4', 'is-other', false]]);
  eq('T7 the walked time dashed', out.dashed, true);
  eq('T8 Load earlier asks; Load later off with its reason when the page says nothing is later',
    out.loads, [[['Load earlier', false, ''], ['Load later', true, 'Nothing later']], ['earlier']]);
  eq('T9 a lane a word, the rest «others»', out.lanes, [['A', false], ['B', false], ['C', false], ['D', false], ['E', false],
    ['F', false], ['G', false], ['H', false], ['others', true]]);
  eq('T10 no value with a time: said', out.none, ['1 point without a time', 'No value with a time in this column']);
  eq('T11 two parts on one screen: each draws its own', out.two, [2, 11, 3, 3]);
  eq('T12 the page: a press on a value cell opens its trend, asks the server\'s page around the walked time, draws both, and Load earlier asks past the page',
    out.pageRun, [true, 'Q1 · measures (in) · value', { id: 'q1', follow: 'measures', direction: 'incoming', hops: '1',
      around: new Date(Date.parse(T(3))).toISOString(), page: '1000' }, ['c1', 'c2', 'c3', 'c4'], 'E1']);
  eq('T13 another side\'s walked point two days off the window: the axis is the window and the pressed side\'s walked points, the window\'s points take most of its width, the far one says itself at the edge - the part, then the page (local time said)',
    [out.far, out.farPage], [[[new Date(Date.parse(T(1))).toISOString(), new Date(Date.parse(T(7))).toISOString()], [[1, true, 1]], 3, true,
      ['\u25c0 Negative walked TIME']],
    [new Date(Date.parse(T(3))).toISOString(), ['c1', 'c3', 'c4'], ['\u25c0 Negative walked TIME'], true]]);
  eq('T14 a point says who gave it, as its cell does: the wafer and its side\'s route; a wafer neither side reached, its keys and «not in this walk» (leads 99ed68cb7 C, 10-11)',
    out.pointSources, [['c1', 'WP · start'], ['c2', 'WN · start'], ['c3', 'WP · start'], ['c4', 'WZ-9 · not in this walk']]);
  eq('T15 the part: a point that carries who gave it says it on its dot', out.dotSource, ['WP · start']);
  return { ran: names.length, names, failures };
}

const REAL = {
  trend: await import('../src/walk/trend.js'),
  view: await import('../src/walk/trend_view.js'),
  page: await import('../src/walk/main.js'),
};
console.log('\n[1] trend');
const base = suite(await seen(REAL));
let ran = base.ran;
let failed = base.failures.length;
const swap = (text, from, to) => {
  if (!text.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`);
  return text.split(from).join(to);
};
const TREND = { file: 'walk/trend.js', key: 'trend' };
const VIEW = { file: 'walk/trend_view.js', key: 'view' };
const PAGE_ = { file: 'walk/main.js', key: 'page' };
const MUTANTS = [
  { id: 'TM1', what: 'a point with no time', catches: 'T1', ...TREND,
    mutate: (t) => swap(t, '.map((r) => ({ t: timeOf(r.edge),', '.map((r) => ({ t: null,') },
  { id: 'TM2', what: 'a page point with no group', catches: 'T2', ...TREND,
    mutate: (t) => swap(t, 'group: group >= 0 ? group : null,', 'group: null,') },
  { id: 'TM3', what: 'a point twice', catches: 'T3', ...TREND, mutate: (t) => swap(t, '!seen.has(p.key)', 'true') },
  { id: 'TM4', what: 'numbers put in lanes', catches: 'T4', ...TREND,
    mutate: (t) => swap(t, "const isNumber = (v) => typeof v === 'number' && Number.isFinite(v);", 'const isNumber = () => false;') },
  { id: 'TM5', what: 'no «others» lane', catches: 'T4', ...TREND,
    mutate: (t) => swap(t, '...(order.length > lanes ? [OTHERS] : [])', '') },
  { id: 'TM6', what: 'the walked points not ringed', catches: 'T6', ...VIEW, mutate: (t) => swap(t, "${p.walked ? ' is-walked' : ''}", '') },
  { id: 'TM7', what: 'the page asks no time', catches: 'T12', ...PAGE_,
    mutate: (t) => swap(t, "const ask = mode === 'around' ? { around: t.t0 === null ? null : new Date(t.t0).toISOString() }",
      "const ask = mode === 'around' ? { around: null }") },
  { id: 'TM8', what: 'Load later on though nothing is later', catches: 'T8', ...VIEW,
    mutate: (t) => swap(t, "spec.hasLater === false ? TREND_WORDS.noLater : ''", "''") },
  { id: 'TM9', what: 'the walked time not dashed', catches: 'T7', ...VIEW,
    mutate: (t) => swap(t, 'if (spec.t0 !== null && spec.t0 >= t0 && spec.t0 <= t1) {', 'if (false) {') },
  // The axis the lead found on the box (10-10), and what holds it.
  { id: 'TM10', what: 'the axis every timed point again', catches: 'T13', ...TREND,
    mutate: (t) => swap(t, 'const all = ts.length ? ts : timed.map((p) => p.t);', 'const all = timed.map((p) => p.t);') },
  { id: 'TM11', what: 'the page draws without its windows and side', catches: 'T13', ...PAGE_,
    mutate: (t) => swap(t, 'trendModel(points, undefined, { windows: t.pages.map(windowOf).filter(Boolean), group: t.group })', 'trendModel(points)') },
  { id: 'TM12', what: 'no edge marker', catches: 'T13', ...VIEW,
    mutate: (t) => swap(t, 'outside.filter((o) => o.before === before).forEach(', '[].forEach(') },
  { id: 'TM14', what: 'a point does not say who gave it', catches: 'T15', ...VIEW,
    mutate: (t) => swap(t, "    if (p.source) { const said = this._svg('title', {}); said.textContent = p.source; dot.append(said); }\n", '') },
  { id: 'TM16', what: 'a paged point no side reached says nothing', catches: 'T14', ...PAGE_,
    mutate: (t) => swap(t, 'source: view.sources.source(p.group === null || p.group === undefined ? null : view.groups[p.group], p.node)',
      "source: p.group === null || p.group === undefined ? '' : view.sources.source(view.groups[p.group], p.node)") },
  { id: 'TM15', what: 'a point\'s source the row\'s, not its read\'s', catches: 'T14', ...PAGE_,
    mutate: (t) => swap(t, 'view.groups[p.group], p.node) }))', 'view.groups[p.group], t.row) }))') },
  { id: 'TM13', what: 'the page asks around any side\'s latest walked point', catches: 'T12', ...PAGE_,
    mutate: (t) => swap(t, 'walkedTime(own, r.generated_at, t.group)', 'walkedTime(own, r.generated_at)') },
];
const scored = await scoreMutants(MUTANTS, async (m) => {
  const copy = (await loadWithProbe(join(SRC, m.file), { mutate: m.mutate })).module;
  return suite(await seen({ ...REAL, [m.key]: copy }));
}, { baselineRan: base.ran, baselineNames: base.names, title: '\n  [1] mutants - each must be caught by the check it names.' });
ran += MUTANTS.length;
failed += scored.wrong;
console.log(`\n${ran - failed} passed, ${failed} failed`);
console.log(`ASSERTIONS ${ran} ${failed}`);
if (failed) process.exit(1);
