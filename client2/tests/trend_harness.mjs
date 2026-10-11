// The trend (walk/trend.js, walk/trend_view.js, lead f984ab01d, a2eb4a516): a point a read of the table's cell, at its
// end's time (an edge's, a node attribute's own record - lead 10-11 E2c, both schemes on 18766), coloured by its group; numbers on a value axis, words in lanes (the most frequent first,
// the rest «others»); the server's time page (the implementer's contract, faked here) adds the row's other edges, colour
// by where their far end was reached; Load earlier / later widen it. Module, part and page; two parts on one screen.
// The axis (lead 10-10, on the box): the pages' windows and the pressed side's walked points - another side's walked
// point two days off stands at the edge, the window's points keep the width.
//
// CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { readFileSync } from 'node:fs';
import { makeDoc, flush, walk as walkAll } from './lib/board_dom.mjs';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';
import { indexGraph, groupsOf, groupKey } from '../src/walk/reach_table.js';
import { entitySeedId } from '../src/rnd_board/api.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src');
const settle = async () => { for (let i = 0; i < 20; i += 1) await flush(); };
const ascii = (t) => String(t).replace(/[^\x00-\x7f]/g, (c) => `\\u${c.charCodeAt(0).toString(16).padStart(4, '0')}`);
const has = (n, cls) => String((n.attrs && n.attrs.class) || n.className || '').split(/\s+/).includes(cls);
/** A section's name, in its toolbar (lead 10-11 W). */
const secHead = (sec) => (walkAll(sec).find((n) => has(n, 'wk-sechead')) || {})._text || '';

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
// Two wafers measuring two quantities: a wafer section's reads end at two nodes (lead 10-10 E2).
const WALK_TWO = { generated_at: T(12), nodes: [node('wp', 'wafer'), node('wn', 'wafer'), node('q1', 'quantity'), node('q2', 'quantity')],
  edges: [edge('wp', 'measures', 'q1', 30.5, 3, 'c1'), edge('wn', 'measures', 'q2', 11, 5, 'c2')],
  propagation: { ranked: [{ id: 'q1', reach: [1, 0] }, { id: 'q2', reach: [0, 1] }] } };
const TIME = /\d\d-\d\d \d\d:\d\d/;
// The same step walked again from another row (lead 10-11, 18766): other wafers measuring another quantity, and that
// quantity's own time page - a wafer of the walk and one it never reached.
const WALK_RE = { generated_at: T(12), nodes: [node('wa', 'wafer'), node('wb', 'wafer'), node('q2', 'quantity')],
  edges: [edge('wa', 'measures', 'q2', 41, 4, 'r1'), edge('wb', 'measures', 'q2', 43, 6, 'r2')],
  propagation: { ranked: [{ id: 'q2', reach: [1, 1] }] } };
const WY = entitySeedId('wafer', { wafer: 'WY-8' });
const PAGE_Q2 = { ...PAGE, seed: node('q2', 'quantity'),
  nodes: [node('q2', 'quantity'), node('wa', 'wafer'), { id: WY, type: 'wafer', label: 'WY-8', keys: { wafer: 'WY-8' } }],
  edges: [edge('wa', 'measures', 'q2', 42, 2, 'd1'), edge(WY, 'measures', 'q2', 47, 7, 'd2')] };

// bond_temp one step both ways on 18766 (lead 10-11 E2c): the edge scheme, its value on the measures edge; the event scheme,
// its value the measurement node's own.
const fixture = (name) => JSON.parse(readFileSync(join(HERE, 'fixtures', name), 'utf8'));
const ED = fixture('walk_scheme_ed_18766.json');
const EV = fixture('walk_scheme_ev_18766.json');
// The application lane's repros on 18766 as its walk answered them (lead 10-11 G-2): mev_num (value a number, param
// text), mev_txt (a numeral in text), mev_noat (records with no time), mev_key (its key only); mev_num again with its
// value in text beside its param; the wafer given a key at its step's end by + Column - the edge says a time for that key.
const MEV = fixture('walk_mev_18766.json');
const textValue = (s) => ({ ...s, value: String(s.value) });
const MEV_NUM_TEXT = { ...MEV, nodes: MEV.nodes.map((n) => (n.type !== 'mev_num' ? n : { ...n, attributes: textValue(n.attributes),
  attributes_by_world: { ...n.attributes_by_world, value: n.attributes_by_world.value.map(textValue) } })) };
const KEY_AT_STEP = new Map([['wafer', [{ steps: [{ predicate: 'has_mev', direction: 'outgoing' }], value: { on: 'key', name: 'measurement_event' },
  words: ['has_mev', 'measurement_event'] }]]]);
// P2-many (lead 10-11 W 13): pev_many's point and value each a list.
const PEV_MANY = fixture('walk_pev_many_18766.json');

/** The walk page with `answer` walked, a section's Trend pressed (lead 10-10 E2): its dots, their titles, its page's ask. */
async function sectionRun(M, answer, type, decl = null, starts = { positive: ['wp'], negative: ['wn'] }, added = new Map(), prep = null) {
  const urls = [];
  const DECL = decl || { entities: [{ type: 'wafer', keys: ['wafer'] }, { type: 'quantity', keys: ['quantity'] }], predicates: [], worlds: [], operating: null };
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
  handle.state.asked = { type: 'wafer', keys: {}, ...starts };
  handle.state.run = 'done';
  handle.state.result = answer;
  handle.state.added = added;
  if (prep) prep(handle.state);
  handle.render();
  const secOf = () => walkAll(host).filter((n) => n.className === 'wk-sec').find((x) => new RegExp(`^${type}`).test(secHead(x)));
  const sec = secOf();
  const toggle = sec && walkAll(sec).find((n) => n.attrs && n.attrs['data-section-view'] === 'trend');
  if (toggle) toggle.dispatch('click', {});
  await settle();
  // The section after the press: its trend drawn, and Columns - «+ Column» at its foot - still there (lead 10-11 G-2, W).
  const now = secOf();
  const shown = now ? [walkAll(now).some((n) => has(n, 'wk-trend')), walkAll(now).some((n) => n.attrs && n.attrs['data-columns'] !== undefined)] : null;
  const q = (u) => Object.fromEntries(new URLSearchParams(String(u || '').split('?')[1] || ''));
  const asks = urls.filter((u) => u.includes('around=') || u.includes('later=') || u.includes('earlier='));
  const sources = walkAll(host).filter((n) => n.tagName === 'CIRCLE' && n.attrs && n.attrs['data-key'])
    .map((n) => [n.attrs['data-key'], ((n.children || []).find((k) => k.tagName === 'TITLE') || {})._text || '']).sort();
  const note = walkAll(host).filter((n) => n.className === 'wk-note').map((n) => n._text || '').find((x) => TIME.test(x)) || '';
  const title = (walkAll(host).find((n) => n.className === 'wk-trend-title') || {})._text;
  return { toggled: Boolean(toggle), ask: asks.length ? q(asks[0]) : null, sources, walkOnly: note.includes('Walk only · no time page'), title,
    off: toggle ? [Boolean(toggle.disabled), (toggle.attrs || {}).title || ''] : null, shown };
}

/** A section's Trend open on WALK, then the step walked again (WALK_RE): its dots and the pages it asked, by node. */
async function rewalkRun(M) {
  const urls = [];
  const DECL = { entities: [{ type: 'wafer', keys: ['wafer'] }, { type: 'quantity', keys: ['quantity'] }], predicates: [], worlds: [], operating: null };
  const paged = (u) => u.includes('around=') || u.includes('later=') || u.includes('earlier=');
  const q = (u) => Object.fromEntries(new URLSearchParams(String(u || '').split('?')[1] || ''));
  const doc = makeDoc('light');
  doc.head = doc.createElement('head');
  const host = doc.createElement('div');
  const handle = M.page.boot(doc, host, { apiBase: '', fetchImpl: async (url) => {
    const u = String(url);
    urls.push(u);
    const body = paged(u) ? (q(u).id === 'q2' ? PAGE_Q2 : PAGE) : DECL;
    return { ok: true, status: 200, json: async () => body };
  } });
  await settle();
  handle.state.type = 'wafer';
  handle.state.asked = { type: 'wafer', keys: {}, positive: ['wp'], negative: ['wn'] };
  handle.state.run = 'done';
  handle.state.result = WALK;
  handle.render();
  const sec = walkAll(host).filter((n) => n.className === 'wk-sec').find((x) => /^wafer/.test(secHead(x)));
  const toggle = sec && walkAll(sec).find((n) => n.attrs && n.attrs['data-section-view'] === 'trend');
  if (toggle) toggle.dispatch('click', {});
  await settle();
  handle.state.asked = { type: 'wafer', keys: {}, positive: ['wa'], negative: ['wb'] };
  handle.state.result = WALK_RE;
  handle.render();
  await settle();
  const dots = walkAll(host).filter((n) => n.tagName === 'CIRCLE' && n.attrs && n.attrs['data-key']).map((n) => n.attrs['data-key']).sort();
  return { toggled: Boolean(toggle), dots, pages: urls.filter(paged).map((u) => q(u).id) };
}

/** Step 2 on (WALK_RE from q1's row), its wafer section's Trend; Step 1 again, then Step 2 again (lead 10-11). */
async function stepViewsRun(M) {
  const DECL = { entities: [{ type: 'wafer', keys: ['wafer'] }, { type: 'quantity', keys: ['quantity'] }], predicates: [], worlds: [], operating: null };
  const paged = (u) => u.includes('around=') || u.includes('later=') || u.includes('earlier=');
  const doc = makeDoc('light');
  doc.head = doc.createElement('head');
  const host = doc.createElement('div');
  const handle = M.page.boot(doc, host, { apiBase: '', fetchImpl: async (url) => {
    const body = paged(String(url)) ? PAGE_Q2 : DECL;
    return { ok: true, status: 200, json: async () => body };
  } });
  await settle();
  handle.state.type = 'wafer';
  handle.state.asked = { type: 'wafer', keys: {}, positive: ['wp'], negative: ['wn'] };
  handle.state.run = 'done';
  handle.state.result = WALK;
  // A step walked on from q1, as a Next lands it.
  handle.state.steps = [{ id: 1, parent: 0, title: 'measures → wafer', run: 'done', result: WALK_RE, reason: '', marks: 'walk-x',
    asked: { positive: ['wa'], negative: ['wb'], follow: ['measures'], collect: ['wafer'], direction: 'both', hops: 1 } }];
  handle.state.at = 1;
  handle.state.leaf = 1;
  handle.render();
  const wafer = () => walkAll(host).filter((n) => n.className === 'wk-sec').find((x) => /^wafer/.test(secHead(x)));
  const trended = () => Boolean(wafer() && walkAll(wafer()).some((n) => n.className === 'wk-trend' || (n.tagName === 'svg' && walkAll(n).some((c) => c.tagName === 'CIRCLE'))));
  const tab = (id) => walkAll(host).find((n) => n.attrs && n.attrs['data-step'] === String(id));
  const toggle = wafer() && walkAll(wafer()).find((n) => n.attrs && n.attrs['data-section-view'] === 'trend');
  if (toggle) toggle.dispatch('click', {});
  await settle();
  const onTwo = trended();
  if (tab(0)) tab(0).dispatch('click', {});
  await settle();
  const onOne = trended();
  if (tab(1)) tab(1).dispatch('click', {});
  await settle();
  return [Boolean(toggle), onTwo, onOne, trended()];
}

/** A lump of the graph opened as a step of the page (lead 10-11 E2b): Step 2 walked on, then the lump q1 · measures ·
 *  its wafers handed in - its tab, its table, its section's Trend, what was asked. */
async function lumpStepRun(M) {
  const urls = [];
  const DECL = { entities: [{ type: 'wafer', keys: ['wafer'] }, { type: 'quantity', keys: ['quantity'] }], predicates: [], worlds: [], operating: null };
  const paged = (u) => u.includes('around=') || u.includes('later=') || u.includes('earlier=');
  const doc = makeDoc('light');
  doc.head = doc.createElement('head');
  const host = doc.createElement('div');
  const handle = M.page.boot(doc, host, { apiBase: '', fetchImpl: async (url) => {
    const u = String(url);
    urls.push(u);
    return { ok: true, status: 200, json: async () => (paged(u) ? PAGE : DECL) };
  } });
  await settle();
  handle.state.type = 'wafer';
  handle.state.asked = { type: 'wafer', keys: {}, positive: ['wp'], negative: ['wn'] };
  handle.state.run = 'done';
  handle.state.result = WALK;
  // A step walked on, by an id the page's own counter does not give.
  handle.state.steps = [{ id: 99, parent: 0, title: 'measures → wafer', run: 'done', result: WALK_RE, reason: '', marks: 'walk-x',
    asked: { positive: ['wa'], negative: ['wb'], follow: ['measures'], collect: ['wafer'], direction: 'both', hops: 1 } }];
  handle.state.at = 99;
  handle.state.leaf = 99;
  handle.render();
  urls.length = 0;
  const lump = { owner: 'q1', ownerLabel: 'Q1', predicate: 'measures', farType: 'wafer', words: '← measures wafer' };
  // Its edges the form walk's answer - the picture's first step (lead 10-11): its step Step 1's child, not Step 2's.
  handle.graph.openTable(M.fold.lumpAnswer([WALK], { ...lump, members: ['wp', 'wn'] }), { ...lump, step: 0 });
  await settle();
  const step = handle.state.steps.find((x) => x.title === 'From Q1 · ← measures wafer') || {};
  const wafer = () => walkAll(host).filter((n) => n.className === 'wk-sec').find((x) => /^wafer/.test(secHead(x)));
  const rows = (walkAll(wafer() || { children: [] }).filter((n) => n.attrs && n.attrs['data-row-id']).map((n) => n.attrs['data-row-id'])).sort();
  const toggle = wafer() && walkAll(wafer()).find((n) => n.attrs && n.attrs['data-section-view'] === 'trend');
  if (toggle) toggle.dispatch('click', {});
  await settle();
  const dots = walkAll(host).filter((n) => n.tagName === 'CIRCLE' && n.attrs && n.attrs['data-key']).map((n) => n.attrs['data-key']).sort();
  // The page's own read of the whole walk, the same rows and the same column (the wafers' measures value toward q1).
  const full = M.table.walkTableView(WALK, DECL.entities, [], undefined, { positive: ['q1'], negative: [] });
  const sec = full.sections.find((x) => x.type === 'wafer');
  const walked = M.trend.rowsPoints(full, ['wn', 'wp'], sec.columns[0]).map((x) => x.key).sort();
  return { parent: step.parent, shown: handle.state.at === step.id && handle.state.view === 'table', rows, walked,
    dotsWalked: dots.filter((k) => walked.includes(k)), walks: urls.filter((u) => u.includes('/subgraph') && !paged(u)).length,
    page: urls.filter(paged).map((u) => new URLSearchParams(u.split('?')[1]).get('id')) };
}

/** The walk page with `answer` walked: a press on the quantity's + cell - its WP column's (lead 10-11 W: a column a far
 *  node), or the last column's (`last`: a + Column added) - or on the wafer section's Trend, then Load earlier. */
async function pageRun(M, answer, press = 'cell', added = new Map()) {
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
  handle.state.added = added;
  handle.render();
  // The quantity section's + cell (the wafer section holds 30.5 too, read the other way).
  // A value cell's value is its value line (C draws its source under it).
  const valueOf = (n) => walkAll(n).filter((k) => k.className === 'wk-val').map((k) => k._text).join(' ');
  const secs = walkAll(host).filter((n) => n.className === 'wk-sec');
  const quantity = secs.find((x) => /^quantity/.test(secHead(x)));
  const wafer = secs.find((x) => /^wafer/.test(secHead(x)));
  const tds = quantity ? walkAll(quantity).filter((n) => n.tagName === 'TD' && n.attrs && n.attrs['data-col'] !== undefined && /30\.5/.test(valueOf(n))) : [];
  const cell = press === 'section' ? wafer && walkAll(wafer).find((n) => n.attrs && n.attrs['data-section-view'] === 'trend')
    : press === 'last' ? tds[tds.length - 1] : tds[0];
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
  // Who gave a point (lead 10-11 W 11): a walked one its read's giver - an edge's subject, wp read from wp toward q1 -, a
  // paged one its edge's subject.
  const fromWp = { steps: [{ predicate: 'measures', direction: 'outgoing' }], value: { on: 'edge', name: 'value' }, words: ['measures →', 'value'] };
  out.givers = [M.trend.walkPoints(index, groups, 'wp', fromWp).map((p) => p.giver), page.map((p) => p.giver)];
  // A page of wp's edges to q1 and to q2, read for a column that ends at q1.
  const PAGE2 = { edges: [edge('wp', 'measures', 'q1', 30.5, 3, 'c1'), edge('wp', 'measures', 'q2', 4, 4, 'c5')] };
  const toQ1 = { ...fromWp, end: 'q1' };
  out.ended = [M.trend.pagePoints(PAGE2, groups, 'wp', toQ1).map((p) => p.key), M.trend.pagePoints(PAGE2, groups, 'q1', toQ1).map((p) => p.key)];
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
  // Who gave the points: the wafer section's Trend - every wafer's read of q1, q1's page (another wafer's too).
  const bySection = await pageRun(M, WALK, 'section');
  out.pointSources = bySection.sources;
  // The part alone: a point that carries its source says it on its dot.
  const said = part();
  said.view.show({ title: 'S', model: M.trend.trendModel([{ t: Date.parse(T(3)), value: 1, group: 0, walked: true, key: 's1', source: 'WP · start' }]),
    groups: ['Positive'], t0: null });
  out.dotSource = walkAll(said.mount).filter((n) => n.tagName === 'CIRCLE' && n.attrs && n.attrs['data-key'])
    .map((n) => ((n.children || []).find((k) => k.tagName === 'TITLE') || {})._text || '');
  // A section's Trend: the wafers' reads of measures (out) end at q1 - its page read from q1, the cell's same points.
  const sectionTrend = await sectionRun(M, WALK, 'wafer');
  out.sectionTrend = [sectionTrend.toggled, sectionTrend.title, sectionTrend.ask && [sectionTrend.ask.id, sectionTrend.ask.follow,
    sectionTrend.ask.direction], sectionTrend.sources, sectionTrend.walkOnly];
  const OUT = { steps: [{ predicate: 'measures', direction: 'outgoing' }], value: { on: 'edge', name: 'value' }, words: ['measures', 'value'] };
  out.anchors = [M.trend.pageAnchor(['q1'], [], COLUMN), M.trend.pageAnchor(['wp', 'wn'], [{ node: 'q1' }, { node: 'q1' }], OUT),
    M.trend.pageAnchor(['wp', 'wn'], [{ node: 'q1' }, { node: 'q2' }], OUT),
    M.trend.pageAnchor(['wp'], [], { ...OUT, value: { on: 'node', name: 'value' } })];
  const heads = [true, false].map((walkOnly) => {
    const p = part();
    p.view.show({ title: 'W', model: M.trend.trendModel(walk), groups: ['Positive', 'Negative'], t0: null, walkOnly });
    return walkAll(p.mount).some((n) => n.className === 'wk-note' && (n._text || '').includes('Walk only · no time page'));
  });
  out.walkOnlyHead = heads;
  // Reads that end at two nodes: a + Column route (no far node of its own), the step's own groups turned off in Columns.
  const NO_END = { steps: [{ predicate: 'measures', direction: 'outgoing' }], value: { on: 'edge', name: 'value' }, words: ['measures →', 'value'] };
  const two = await sectionRun(M, WALK_TWO, 'wafer', null, undefined, new Map([['wafer', [NO_END]]]),
    (st) => st.off.set('wafer', new Set(['q1', 'q2'].map((end) => groupKey({ ...NO_END, end })))));
  out.sectionTwo = [two.toggled, two.ask, two.sources.map(([k]) => k), two.walkOnly];
  const re = await rewalkRun(M);
  out.rewalk = [re.toggled, re.dots, re.pages];
  out.stepViews = await stepViewsRun(M);
  const ls = await lumpStepRun(M);
  out.lumpStep = [ls.parent, ls.shown, ls.rows, ls.walked, ls.dotsWalked, ls.walks, ls.page];
  // Copy points (lead a27dfbb0f): the sheet - time in this screen's, the value as it is, its side, who gave it, its claim.
  const cp = M.trend.pointsSheet([{ t: Date.parse(T(3)), value: 30.5, group: 0, key: 'c1', node: 'wp', claim: 'c1' },
    { t: null, value: 'A', group: null, key: 'c9', node: 'wz', claim: 'c9' }], ['Positive', 'Negative'], (p) => p.node.toUpperCase());
  out.copySheet = [cp.head, cp.rows.map((r) => [TIME.test(r[0]) || r[0] === '', ...r.slice(1)])];
  const cpPart = part();
  let copied = 0;
  cpPart.view.show({ title: 'C', model: M.trend.trendModel(walk), groups: ['Positive'], t0: null, onCopy: () => { copied += 1; return 'Copied 2 points'; } });
  const cpButton = walkAll(cpPart.mount).find((n) => n.tagName === 'BUTTON' && n._text === 'Copy points');
  if (cpButton) cpButton.dispatch('click', {});
  out.copyPart = [Boolean(cpButton), copied, (walkAll(cpPart.mount).find((n) => has(n, 'wk-copied')) || {})._text || ''];
  const farRun = await pageRun(M, WALK_FAR, 'section');
  // A + Column route reading q1's measures from both wafers: its + cell asks around the + side's walked time (T(3)), not
  // the − side's later one (T(5)).
  const route = { steps: [{ predicate: 'measures', direction: 'incoming' }], value: { on: 'edge', name: 'value' }, words: ['measures ←', 'value'] };
  const bothRun = await pageRun(M, WALK, 'last', new Map([['quantity', [route]]]));
  out.pressedSide = [bothRun.title, bothRun.ask && bothRun.ask.around];
  out.farPage = [farRun.ask && farRun.ask.around, farRun.dots, farRun.edges, farRun.local];
  // E2c: each scheme's value column as a trend reads it - its head, how many points have a time, the points (value, time).
  const scheme = (F, type) => {
    const view = M.table.walkTableView(F, F._decl.entities, F._decl.predicates, undefined, { positive: [F._seed], negative: [] });
    const sec = view.sections.find((x) => x.type === type);
    const at = sec && sec.trendable[0];
    // Every «value» column the section's trend reads - the edge scheme's a wafer each (lead 10-11 W: a column a far node).
    const pts = sec ? sec.trendable.filter((x) => x.column.value.name === 'value')
      .flatMap((x) => M.trend.rowsPoints(view, sec.rows.map((r) => r.id), x.column)) : [];
    return { head: at ? at.head : null, timed: pts.filter((p) => Number.isFinite(p.t)).length,
      points: pts.map((p) => JSON.stringify([p.t, p.value])).sort(),
      claims: M.trend.pointsSheet(pts, ['Positive'], (p) => p.node).rows.map((row) => row[4]).sort() };
  };
  const ed = scheme(ED, 'quantity');
  const ev = scheme(EV, 'measurement');
  out.schemes = [ed.head, ev.head, ed.timed, ev.timed, ed.points.join() === ev.points.join()];
  out.claims = [ev.claims, ed.claims.join() === ED.edges.map((e) => e.claim_id).sort().join() && ed.claims.every(Boolean)];
  const evPage = await sectionRun(M, EV, 'measurement', { ...EV._decl, worlds: [], operating: null }, { positive: [EV._seed], negative: [] });
  out.schemePage = [evPage.toggled, evPage.title, evPage.ask, evPage.sources.length, evPage.walkOnly];
  const evQuantity = await sectionRun(M, EV, 'quantity', { ...EV._decl, worlds: [], operating: null }, { positive: [EV._seed], negative: [] });
  const evView = M.table.walkTableView(EV, EV._decl.entities, EV._decl.predicates, undefined, { positive: [EV._seed], negative: [] });
  out.schemeOff = [evQuantity.off, evQuantity.sources.length, evPage.off,
    evView.sections.map((sec) => [sec.type, sec.trendable.map((x) => x.head).join()])];
  // G-2 (lead 10-11): each repro's columns a trend reads, the one it opens on drawn (a value as a number: reach_table R24).
  const mevOf = (F, type, added = new Map()) => {
    const view = M.table.walkTableView(F, F._decl.entities, F._decl.predicates, undefined, { positive: [F._seed], negative: [] }, added);
    const sec = view.sections.find((x) => x.type === type);
    const at = sec.trendable[0];
    const model = at ? M.trend.trendModel(M.trend.rowsPoints(view, sec.rows.map((r) => r.id), at.column)) : null;
    return [sec.trendable.map((x) => x.head).join(), model && model.numbers.map((p) => p.value).sort((a, b) => a - b), model && model.lanes];
  };
  out.mev = [...['mev_num', 'mev_txt', 'mev_noat', 'mev_key'].map((type) => mevOf(MEV, type)), mevOf(MEV_NUM_TEXT, 'mev_num'),
    mevOf(MEV, 'wafer', KEY_AT_STEP)];
  const mevPage = async (F, type, added) => {
    const p = await sectionRun(M, F, type, { ...F._decl, worlds: [], operating: null }, { positive: [F._seed], negative: [] }, added);
    return [p.off, p.title || null, p.shown];
  };
  out.mevPage = [await mevPage(MEV, 'mev_txt'), await mevPage(MEV, 'mev_noat'), await mevPage(MEV, 'mev_key'), await mevPage(MEV, 'wafer', KEY_AT_STEP)];
  // P2-many: its section's columns a trend reads and the points with a time.
  const many = M.table.walkTableView(PEV_MANY, PEV_MANY._decl.entities, PEV_MANY._decl.predicates, undefined, { positive: [PEV_MANY._seed], negative: [] });
  const manySec = many.sections.find((x) => x.type === 'pev_many');
  out.many = manySec.trendable.map((x) => [x.head, M.trend.rowsPoints(many, manySec.rows.map((r) => r.id), x.column).filter((p) => p.t !== null).length]);
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
    out.pageRun, [true, 'Q1 · measures ← wafer · value', { id: 'q1', follow: 'measures', direction: 'incoming', hops: '1',
      around: new Date(Date.parse(T(3))).toISOString(), page: '1000' }, ['c1', 'c2', 'c3', 'c4'], 'E1']);
  eq('T18 a column ending at one node (a static far type, lead 10-11 W addendum 8 (다)): a page read from its row keeps that node\'s edges only; read from that node, every one',
    out.ended, [['c1'], ['c1', 'c5']]);
  eq('T13 another side\'s walked point two days off the window: the axis is the window and the pressed side\'s walked points, the window\'s points take most of its width, the far one says itself at the edge - the part, then the page (local time said)',
    [out.far, out.farPage], [[[new Date(Date.parse(T(1))).toISOString(), new Date(Date.parse(T(7))).toISOString()], [[1, true, 1]], 3, true,
      ['\u25c0 Negative walked TIME']],
    [new Date(Date.parse(T(3))).toISOString(), ['c1', 'c3', 'c4'], ['\u25c0 Negative walked TIME'], true]]);
  eq('T14 a point says who gave it, as its cell does: the wafer and its side\'s route; a wafer neither side reached, its keys and «not in this walk» - the wafer section\'s Trend (leads 99ed68cb7 C, 10-11)',
    out.pointSources, [['c1', 'WP · start'], ['c2', 'WN · start'], ['c3', 'WP · start'], ['c4', 'WZ-9 · not in this walk']]);
  eq('T15 the part: a point that carries who gave it says it on its dot', out.dotSource, ['WP · start']);
  eq('T17 who gave a point: a walked one its read' + "'" + 's giver - the edge' + "'" + 's subject, not its far end -, a paged one its edge' + "'" + 's subject, not the node the page was read from',
    out.givers, [['wp'], ['wp', 'wp', WZ]]);
  eq('T16 a + Column route over both sides: its + cell' + "'" + 's page asked around the + side' + "'" + 's walked time, not the other side' + "'" + 's later one',
    out.pressedSide, ['Q1 · measures ← · value', new Date(Date.parse(T(3))).toISOString()]);
  eq('TS1 a section' + "'" + 's Trend: every row' + "'" + 's reads, its time page read from the one node they reach - the edge taken the other way - every wafer' + "'" + 's point and who gave it (lead 10-10 E2)',
    out.sectionTrend, [true, 'wafer · 2 · measures → quantity · value', ['q1', 'measures', 'incoming'],
      [['c1', 'WP · start'], ['c2', 'WN · start'], ['c3', 'WP · start'], ['c4', 'WZ-9 · not in this walk']], false]);
  eq('TS3 the page' + "'" + 's anchor: one row its own; rows reaching one end that end, the step the other way; two ends, or a node' + "'" + 's value, none',
    out.anchors, [{ id: 'q1', predicate: 'measures', direction: 'incoming' }, { id: 'q1', predicate: 'measures', direction: 'incoming' }, null, null]);
  eq('TS4 the part: a trend no time page can widen says walk only on its head', out.walkOnlyHead, [true, false]);
  eq('TS2 a section whose reads end at two nodes - a + Column route, the step\'s own groups off: no time page asked, the head says walk only', out.sectionTwo,
    [true, null, ['c1', 'c2'], true]);
  eq('TS5 a section' + "'" + 's Trend open, the step walked again from another row: its points only the new rows' + "'" + ' and the new anchor' + "'" + 's own page, none from the old (lead 10-11)',
    out.rewalk, [true, ['d1', 'd2', 'r1', 'r2'], ['q1', 'q2']]);
  eq('TC1 Copy points: time · value · side · node · claim_id - its time in this screen' + "'" + 's, none none, its value as it is, its side or none, who gave it, its claim',
    out.copySheet, [['time', 'value', 'side', 'node', 'claim_id'], [[true, '30.5', 'Positive', 'WP', 'c1'], [true, 'A', '', 'WZ', 'c9']]]);
  eq('TC2 the part' + "'" + 's «Copy points»: the page copies, the part says what happened beside it', out.copyPart, [true, 1, 'Copied 2 points']);
  eq('OT3 a lump opened as a step: the child of the step whose answer brought its edges (lead 10-11), shown; its rows the members, its section' + "'" + 's Trend the points the page reads for the same rows and column, its page from the owner; nothing walked (lead 10-11 E2b)',
    out.lumpStep, [0, true, ['wn', 'wp'], ['c1', 'c2'], ['c1', 'c2'], 0, ['q1']]);
  eq('SC1 bond_temp on 18766, two schemes: the edge scheme' + "'" + 's measures value and the event scheme' + "'" + 's measurement value - the first column a trend reads, every point timed, the same values and times (lead 10-11 E2c)',
    out.schemes, ['measures ← wafer · value', 'value', 4, 4, true]);
  eq('SC4 a section none of whose reads has a time - the event scheme' + "'" + 's quantity, its key only: its Trend off, said; the measurements' + "'" + ' on (lead 10-11)',
    out.schemeOff, [[true, 'No value with a time'], 0, [false, ''], [['quantity', ''], ['measurement', 'value,eqp_id,role,step,unit']]]);
  eq('SC3 Copy points' + "'" + ' claim_id: a node' + "'" + 's own value has none - an empty cell, not the key a point is told apart by; an edge' + "'" + 's value its claim (lead 10-11)',
    out.claims, [['', '', '', ''], true]);
  eq('SC2 the page, the event scheme: the measurement section' + "'" + 's Trend on its own value - a dot each, walk only, no page asked (lead 10-11 E2c)',
    out.schemePage, [true, 'measurement · 4 · value', null, 4, true]);
  eq('TV1 the Table/Trend choice is its step' + "'" + 's: Step 2' + "'" + 's section in Trend, Step 1 gone back to stays Table, Step 2 again its Trend (lead 10-11)',
    out.stepViews, [true, true, false, true]);
  eq('SC5 the repros on 18766 (lead 10-11 G-2): a number value first and opened on, before a text; a numeral in text a number too, on the value axis, and first; records with no time, a key only, a key at a step' + "'" + 's end - nothing a trend reads',
    out.mev, [['value,param', [1.5, 2.5, 3.5, 4.5], []], ['value', [1.5, 2.5, 3.5, 4.5], []], ['', null, null], ['', null, null],
      ['value,param', [1.5, 2.5, 3.5, 4.5], []], ['measures → TRD-P · value', [4.5], []]]);
  eq('SC6 the page: the numeral-in-text section' + "'" + 's Trend on its value, «+ Column» still there; no time, the key only - Trend off, said; a key at a step' + "'" + 's end not what a Trend opens on',
    out.mevPage, [[[false, ''], 'mev_txt · 4 · value', [true, true]], [[true, 'No value with a time'], null, [false, true]],
      [[true, 'No value with a time'], null, [false, true]], [[false, ''], 'TRD-W-001 · measures → TRD-P · value', [true, true]]]);
  eq('SC7 P2-many (lead 10-11 W 13): a list' + "'" + 's own record found - each column a trend reads has a point with a time an event (E1, E2)',
    out.many, [['point', 2], ['value', 2]]);
  return { ran: names.length, names, failures };
}

const REAL = {
  trend: await import('../src/walk/trend.js'),
  view: await import('../src/walk/trend_view.js'),
  page: await import('../src/walk/main.js'),
  fold: await import('../src/walk/fold_views.js'),
  table: await import('../src/walk/table_view.js'),
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
const TABLE = { file: 'walk/table_view.js', key: 'table' };
const VIEW = { file: 'walk/trend_view.js', key: 'view' };
const PAGE_ = { file: 'walk/main.js', key: 'page' };
const MUTANTS = [
  { id: 'TSm1', what: 'a section' + "'" + 's reads sharing their end: no page', catches: 'TS3', ...TREND,
    mutate: (t) => swap(t, '  return ends.length === 1' + String.fromCharCode(10) + '    ? { id: ends[0],', '  return false' + String.fromCharCode(10) + '    ? { id: ends[0],') },
  { id: 'TSm2', what: 'reads ending at two nodes paged from the first', catches: 'TS3', ...TREND,
    mutate: (t) => swap(t, '  return ends.length === 1' + String.fromCharCode(10), '  return ends.length >= 1' + String.fromCharCode(10)) },
  { id: 'TSm3', what: 'a section' + "'" + 's trend its first row alone', catches: 'TS1', ...PAGE_,
    mutate: (t) => swap(t, 'const own = rowsPoints(view, rows, at.column);', 'const own = rowsPoints(view, rows.slice(0, 1), at.column);') },
  { id: 'OTm3', what: 'the lump' + "'" + 's step walks the server', catches: 'OT3', ...PAGE_,
    mutate: (t) => swap(t, "    step.run = 'done';\n    step.result = answer;\n", "    void walk(asked).then((res) => { step.run = 'done'; step.result = res; render(); });\n") },
  { id: 'OTm4', what: 'the lump' + "'" + 's step the branch' + "'" + 's end' + "'" + 's child, not the step that brought its edges', catches: 'OT3', ...PAGE_,
    mutate: (t) => swap(t, '    const parent = lump.step === 0 ? 0 : (pathTo(state.leaf)[lump.step - 1] || { id: state.leaf }).id;', '    const parent = state.leaf;') },
  { id: 'TSm4', what: 'a walk-only trend not said', catches: 'TS4', ...VIEW,
    mutate: (t) => swap(t, "spec.walkOnly ? TREND_WORDS.noPage : ''", "''") },
  { id: 'TSm5', what: 'a walked point given by its far end', catches: 'T17', ...TREND,
    mutate: (t) => swap(t, '      giver: r.giver,', '      giver: r.node,') },
  { id: 'TSm6', what: 'the page' + "'" + 's anchor ignored: a section paged from nowhere', catches: 'TS1', ...PAGE_,
    mutate: (t) => swap(t, '    t.anchor = pageAnchor(rows, own, at.column);', '    t.anchor = null;') },
  { id: 'TVm1', what: 'one trend slot for every step', catches: 'TV1', ...PAGE_,
    mutate: (t) => swap(t, '  const trendNow = () => trends.get(state.at) || null;', '  const trendNow = () => [...trends.values()].pop() || null;') },
  { id: 'TSm7', what: 'the old anchor' + "'" + 's page kept when the step is walked again', catches: 'TS5', ...PAGE_,
    mutate: (t) => swap(t, '    if (fresh) Object.assign(t, { pageKey, t0: null, pages: [], earlier: null, later: null, hasEarlier: null, hasLater: null });',
      '    if (fresh) t.pageKey = pageKey;') },
  { id: 'TSm8', what: 'a section' + "'" + 's trend reads the rows it was opened on', catches: 'TS5', ...PAGE_,
    mutate: (t) => swap(t, "    const rows = t.at === 'section' ? at.section.rows.map((x) => x.id) : t.rows;", '    const rows = t.rows;') },
  { id: 'TM1', what: 'a point with no time', catches: 'T1', ...TREND,
    mutate: (t) => swap(t, '.map((r) => ({ t: timeOf(r.when),', '.map((r) => ({ t: null,') },
  { id: 'SCm1', what: 'a point at its way' + "'" + 's last edge' + "'" + 's time, a node' + "'" + 's own value at none', catches: 'SC1', ...TREND,
    mutate: (t) => swap(t, '.map((r) => ({ t: timeOf(r.when),', '.map((r) => ({ t: timeOf(r.edge),') },
  { id: 'SCm5', what: 'a column with no read that has a time offered to the trend', catches: 'SC5', ...TABLE,
    mutate: (t) => swap(t, '      }).filter((x) => x.timed);', '      });') },
  { id: 'SCm2', what: 'a trend reads the steps' + "'" + ' columns only', catches: 'SC1', ...TABLE,
    mutate: (t) => swap(t, '      ...centre.map((column) => ({ column, head: column.words.join(', '      ...[].map((column) => ({ column, head: column.words.join(') },
  { id: 'SCm6', what: 'a key at a step' + "'" + 's end offered to the trend', catches: 'SC5', ...TABLE,
    mutate: (t) => swap(t, '.filter(({ column }) => saysValue(column))', '.filter(Boolean)') },
  { id: 'SCm7', what: 'the columns in their order, numbers not first', catches: 'SC5', ...TABLE,
    mutate: (t) => swap(t, 'const trendable = [...valued.filter((x) => x.number), ...valued.filter((x) => !x.number)]', 'const trendable = [...valued]') },
  { id: 'SCm8', what: 'a numeral in text not a number when the columns are ordered', catches: 'SC5', ...TABLE,
    mutate: (t) => swap(t, 'timed.every((p) => numberOf(p.value) !== null)', "timed.every((p) => typeof p.value === 'number')") },
  { id: 'SCm9', what: 'Columns - «+ Column» at its foot - hidden while the section shows its Trend', catches: 'SC6', ...PAGE_,
    mutate: (t) => swap(t, 'bar.append(sectionViews(section, trended), columnsMenu(section), ', 'bar.append(sectionViews(section, trended), ...(trended ? [] : [columnsMenu(section)]), ') },
  { id: 'SCm3', what: 'the section' + "'" + 's Trend opens on a step' + "'" + 's column only', catches: 'SC2', ...PAGE_,
    mutate: (t) => swap(t, '    const first = section.trendable.find((x) => columnKey(x.column) === long) || section.trendable[0];',
      '    const first = section.columns.length ? { column: section.columns[0] } : null;') },
  { id: 'TM2', what: 'a page point with no group', catches: 'T2', ...TREND,
    mutate: (t) => swap(t, 'group: group >= 0 ? group : null,', 'group: null,') },
  { id: 'TM3', what: 'a point twice', catches: 'T3', ...TREND, mutate: (t) => swap(t, '!seen.has(p.key)', 'true') },
  { id: 'TM4', what: 'numbers put in lanes', catches: 'T4', ...TREND,
    mutate: (t) => swap(t, 'const isNumber = (v) => numberOf(v) !== null;', 'const isNumber = () => false;') },
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
    mutate: (t) => swap(t, 'source: view.sources.source(p.group === null || p.group === undefined ? null : view.groups[p.group],',
      "source: p.group === null || p.group === undefined ? '' : view.sources.source(view.groups[p.group],") },
  { id: 'TM15', what: 'a page point given by the node its page was read from', catches: 'T17', ...TREND,
    mutate: (t) => swap(t, '      node: far, giver: e.source,', '      node: far, giver: x,') },
  { id: 'TCm1', what: 'a copied point without its claim', catches: 'TC1', ...TREND, mutate: (t) => swap(t, "keysOf(p), p.claim || '']", "keysOf(p), '']") },
  { id: 'SCm4', what: 'a copied point' + "'" + 's claim the key it is told apart by', catches: 'SC3', ...TREND,
    mutate: (t) => swap(t, "keysOf(p), p.claim || '']", "keysOf(p), p.key || '']") },
  { id: 'TCm2', what: 'Copy points says nothing', catches: 'TC2', ...VIEW,
    mutate: (t) => swap(t, '() => { said.textContent = spec.onCopy(); }', '() => { spec.onCopy(); }') },
  { id: 'TM16', what: 'a page read from the row keeps every far node' + "'" + 's edges', catches: 'T18', ...TREND,
    mutate: (t) => swap(t, ' && (!column.end || x === column.end || p.node === column.end)', '') },
  { id: 'TM13', what: 'the page asks around any side\'s latest walked point', catches: 'T16', ...PAGE_,
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
