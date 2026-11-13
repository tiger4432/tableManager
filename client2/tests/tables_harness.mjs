// TABLES L1 — the first table of the Tables page (owner 11-06, lead L1): opened from the grid with its narrowing, read by
// page through the grid's own door, never opened whole.
//
//   H1-H4 the hand-off: the grid's table, narrowing and world kept, read once, only for its table and while fresh, and a
//         storage that refuses is no crash
//   N1-N5 the narrowing: what opens the table, a chip's words and its removal, the search, and the query a page and a
//         count ask - the grid's narrowing (narrowing.js narrowingParams) whole in both (G4: the same narrowing asks
//         the same rows)
//   L1    a line reads a cell's value, a column the row carries itself (row_id …) its own, a blank none
//   P1-P2 paging: a next page only while the last came full and the count says more; the words under the table
//   B1-B7 the box: unnarrowed it reads no row and says so; narrowed it reads the first page and counts; a page of exactly
//         the count says all; scrolled near the end it reads the next (after the last row read, lead 11-13); a head pressed orders by the server; a chip's
//         remove reads again without it; a refusal is the server's sentence; two boxes on one page do not meet
//   K1-K2 a box's rows marked + and − (Shift) under its name, a press again takes one out; a box opened by a server
//         marking reads its rows without a narrowing, the marking in its page and its count
//   R1-R5 the walk between tables (chain.js): a row's node id, the types a table names, the paths through a predicate the
//         next table emits, a hop's two calls, a kept marking's rows page by page after the last row read
//   F1-F2 the compare (axis_compare.js): folded by the axis - text UniqueConcatenate, number Avg - differing lines up, one
//         side's lines «−»; Differs only; the picks told to the page
//   S1    the marking store's names (owner 11-11): nextName holds what it gives, two in one tick differ, a dropped one is
//         given again, its version kept; labelOf «#N»
//
// Run: node client2/tests/tables_harness.mjs
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';
import { makeDoc } from './lib/board_dom.mjs';
import * as handoff from '../src/tables/handoff.js';
import { narrowingParams } from '../src/narrowing.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SUBJECTS = { box: path.join(HERE, '..', 'src', 'tables', 'table_box.js'), chain: path.join(HERE, '..', 'src', 'tables', 'chain.js'),
  compare: path.join(HERE, '..', 'src', 'tables', 'axis_compare.js'), store: path.join(HERE, '..', 'src', 'rnd_board', 'marking_store.js') };
const walk = (n) => [n, ...(n.children || []).flatMap(walk)];
const byClass = (n, cls) => walk(n).filter((c) => String(c.className || '').split(/\s+/).includes(cls));
const textOf = (n) => (n ? n.textContent : '');
const tick = () => new Promise((r) => setTimeout(r, 0));
const settle = async () => { for (let i = 0; i < 8; i += 1) await tick(); };

class Store {
  constructor(fail = false) { this.m = new Map(); this.fail = fail; }
  getItem(k) { if (this.fail) throw new Error('blocked'); return this.m.has(k) ? this.m.get(k) : null; }
  setItem(k, v) { if (this.fail) throw new Error('blocked'); this.m.set(k, String(v)); }
  removeItem(k) { if (this.fail) throw new Error('blocked'); this.m.delete(k); }
}

const COLUMNS = ['dt_lot', 'dt_slot', 'created_at', 'row_id'];
const rowOf = (i) => ({ row_id: `r${String(i).padStart(5, '0')}`, created_at: `2026-11-06T00:00:${String(i % 60).padStart(2, '0')}Z`,
  data: { dt_lot: { value: `LOT-${100 + (i % 7)}` }, dt_slot: { value: i % 25 }, created_at: undefined } });

/** A server: /schema, /data/count (narrowed or whole), /data pages of `rows` - each request kept. */
function server(total, { refuse = null } = {}) {
  const asked = [];
  const json = (body, status = 200) => ({ ok: status < 400, status, json: async () => body });
  const fetch = async (url) => {
    asked.push(url);
    const [route, query] = url.split('?');
    const q = new URLSearchParams(query || '');
    if (route.endsWith('/schema')) return json({ columns: COLUMNS });
    if (route.endsWith('/data/count') && q.get('marking')) return json({ total: 3, capped: false });
    if (route.endsWith('/data') && q.get('marking')) return json({ data: Array.from({ length: 3 }, (_, k) => rowOf(k)), total: null });
    if (route.endsWith('/data/count')) return json({ total: q.toString() ? total : 9999, capped: false });
    if (route.endsWith('/data')) {
      if (refuse) return json({ detail: refuse }, 422);
      const skip = Number(q.get('skip'));
      const n = Math.max(0, Math.min(Number(q.get('limit')), total - skip));
      return json({ data: Array.from({ length: n }, (_, k) => rowOf(skip + k)), total: null });
    }
    return json({ detail: 'no route' }, 404);
  };
  return { fetch, asked, pages: () => asked.filter((u) => u.split('?')[0].endsWith('/data')) };
}

const R3_WANT = ['wafer · processed_with', 'die · inspected · processed_with', 'die · in_container · processed_with'];
const NARROW = `filters=${encodeURIComponent(JSON.stringify({ dt_lot: { filterType: 'text', type: 'contains', filter: 'LOT-10' } }))}`;

async function suite(mods) {
  const m = mods.box;
  const ran = [];
  const failures = [];
  const eq = (name, got, want) => {
    ran.push(name);
    const g = JSON.stringify(got); const w = JSON.stringify(want);
    if (g !== w) failures.push(`${name}: got ${g}, want ${w}`);
  };

  // ── the hand-off ──
  const s = new Store();
  handoff.handoffWrite(s, 'dt_log', NARROW, 'w2', 1000);
  const first = handoff.handoffRead(s, '?table=dt_log', 2000);
  const again = handoff.handoffRead(s, '?table=dt_log', 2001);
  eq('H1 the grid\'s table, narrowing and world arrive, and the hand-off is taken - read once',
    [first, again.handed, again.narrowing], [{ table: 'dt_log', narrowing: NARROW, world: 'w2', handed: true }, false, '']);
  handoff.handoffWrite(s, 'dt_log', NARROW, null, 1000);
  eq('H2 a hand-off for another table is not this page\'s', handoff.handoffRead(s, '?table=lot_event', 1001),
    { table: 'lot_event', narrowing: '', world: null, handed: false });
  handoff.handoffWrite(s, 'dt_log', NARROW, null, 1000);
  eq('H3 a stale hand-off opens the page as its address says', handoff.handoffRead(s, '?table=dt_log', 1000 + handoff.HANDOFF_MS + 1).handed, false);
  const blocked = new Store(true);
  eq('H4 a storage that refuses is no crash - the address\'s table, no narrowing',
    [handoff.handoffWrite(blocked, 'dt_log', NARROW, null), handoff.handoffRead(blocked, '?table=dt_log')],
    [false, { table: 'dt_log', narrowing: '', world: null, handed: false }]);

  // ── the narrowing ──
  eq('N1 only a search, a filter or a transaction opens the first table',
    ['', 'q=LOT', NARROW, 'transaction_id=tx1', 'cols=dt_lot'].map(m.narrows), [false, true, true, true, false]);
  eq('N2 a chip says the column and its filter as the floating cell does; a transaction is its own chip',
    m.chipsOf(`${NARROW}&transaction_id=tx1`), [{ column: 'dt_lot', words: 'dt_lot LOT-10' }, { column: null, words: 'Transaction tx1' }]);
  eq('N3 a chip\'s remove takes that filter off and keeps the rest; the last one takes the parameter',
    [new URLSearchParams(m.withoutFilter(`${NARROW}&q=x`, 'dt_lot')).toString(), m.withoutTransaction('transaction_id=t&q=x')], ['q=x', 'q=x']);
  eq('N4 a search set, and cleared with its columns', [m.withSearch('cols=dt_lot', ' A '), m.withSearch('q=A&cols=dt_lot', '')], ['cols=dt_lot&q=A', '']);
  const grid = narrowingParams({ globalSearch: { value: 'LOT' }, searchCols: { value: 'dt_lot' },
    gridApi: { getFilterModel: () => ({ dt_slot: { filterType: 'number', type: 'equals', filter: 3 } }) }, transactionId: 'tx9' });
  const page = new URLSearchParams(m.pageQuery(grid.toString(), { skip: 500, order: { column: 'dt_slot', desc: true }, world: 'w2' }));
  const count = new URLSearchParams(m.countQuery(grid.toString(), 'w2'));
  eq('N5 G4 a page and a count ask the grid\'s narrowing whole; the page its place, order (none: row_id) and a deferred count',
    [[...grid].every(([k, v]) => page.get(k) === v && count.get(k) === v), page.get('skip'), page.get('limit'), page.get('order_by'),
      page.get('order_desc'), page.get('defer_total'), page.get('world'), count.has('skip') || count.has('order_by'), count.get('world'),
      new URLSearchParams(m.pageQuery('')).get('order_by')],
    [true, '500', String(m.PAGE_ROWS), 'dt_slot', 'true', 'true', 'w2', false, 'w2', 'row_id']);

  // ── a line ──
  const [line] = m.linesOf([{ row_id: 'r1', created_at: 'T', data: { dt_lot: { value: 'L' }, dt_slot: { value: '' } } }], COLUMNS);
  eq('L1 a cell\'s value; a column the row carries itself its own; a blank none',
    [line.id, line.reads.col1, line.reads.col2, line.reads.col3, line.reads.col4],
    ['r1', { state: 'one', value: 'L' }, { state: 'none' }, { state: 'one', value: 'T' }, { state: 'one', value: 'r1' }]);

  // ── paging ──
  const P = m.PAGE_ROWS;
  eq('P1 a next page while the last came full and the count says more; not past an exact count; a capped count does not stop it',
    [m.moreAfter(P, P, { total: 1284 }), m.moreAfter(P, P, { total: P }), m.moreAfter(P - 1, P - 1, null), m.moreAfter(P, P, null),
      m.moreAfter(P, 10000, { total: 10000, capped: true })], [true, false, false, true, true]);
  eq('P2 the words: read of counted and more on scroll, all, none, reading; the header narrowed of whole',
    [m.footWords({ read: 500, more: true, total: { total: 1284 } }), m.footWords({ read: 500, more: false, total: { total: 500 } }),
      m.footWords({ read: 0, more: false }), m.footWords({ read: 0, more: true }), m.countWords({ total: 1284 }, { total: 412930 }, true),
      m.countWords(null, { total: 412930 }, false)],
    ['rows 1–500 of 1,284 · next page on scroll', 'all 500 rows', 'No rows', m.READING_WORDS, '1,284 of 412,930 rows', '412,930 rows']);

  // ── the box ──
  const open = async (total, narrowing, opts) => {
    const doc = makeDoc('light');
    const host = doc.createElement('div');
    const srv = server(total, opts);
    const box = new m.TableBox(host, { doc, fetch: srv.fetch, apiBase: 'http://x', table: 'dt_log', narrowing });
    await box.open();
    await settle();
    return { doc, host, srv, box, foot: () => textOf(byClass(host, 'tables-box__foot')[0]), count: () => textOf(byClass(host, 'tables-box__count')[0]),
      lines: () => walk(host).filter((n) => n.tagName === 'TR' && !String(n.className).includes('tb-table__pad') && n.parentNode && n.parentNode.tagName === 'TBODY') };
  };
  const shut = await open(3000, '');
  eq('B1 unnarrowed: no row is read, the start words stand, the table\'s count is said',
    [shut.srv.pages().length, textOf(byClass(shut.host, 'tables-box__start')[0]), shut.count()], [0, m.START_WORDS, '9,999 rows']);
  const b = await open(1284, NARROW);
  const firstPage = new URLSearchParams(b.srv.pages()[0].split('?')[1]);
  eq('B2 narrowed: the first page with the narrowing, its lines drawn, the counts and what more comes',
    [firstPage.get('filters'), firstPage.get('skip'), b.lines().length > 0, b.count(), b.foot()],
    [new URLSearchParams(NARROW).get('filters'), '0', true, '1,284 of 9,999 rows', 'rows 1–500 of 1,284 · next page on scroll']);
  const exact = await open(m.PAGE_ROWS, NARROW);
  eq('B3 a page of exactly the count says all, and scrolling reads no more', [exact.foot(), exact.box.more], [`all ${m.PAGE_ROWS} rows`, false]);
  const wrap = byClass(b.host, 'tb-table__wrap')[0];
  Object.assign(wrap, { scrollHeight: 14000, clientHeight: 600, scrollTop: 13300 });
  wrap.dispatch('scroll', {});
  await settle();
  const second = new URLSearchParams((b.srv.pages()[1] || '?').split('?')[1]);
  eq('B4 near the end the next page is read, below the first - after the last row read, skip beside', [b.srv.pages().length, second.get('skip'), second.get('after'), b.foot()],
    [2, '500', 'r00499', 'rows 1–1,000 of 1,284 · next page on scroll']);
  const head = walk(b.host).filter((n) => n.tagName === 'TH').find((th) => th.textContent.startsWith('dt_slot'));
  head.dispatch('click', {});
  await settle();
  const sorted = new URLSearchParams(b.srv.pages().at(-1).split('?')[1]);
  eq('B5 a head pressed orders by the server from the first page, and the head says it',
    [sorted.get('order_by'), sorted.get('order_desc'), sorted.get('skip'), walk(b.host).filter((n) => n.tagName === 'TH').find((th) => th.textContent.startsWith('dt_slot')).textContent],
    ['dt_slot', 'false', '0', 'dt_slot▲']);
  byClass(b.host, 'chip-remove')[0].dispatch('click', {});
  await settle();
  eq('B6 a chip\'s remove reads again without it - unnarrowed, no row is read', [byClass(b.host, 'chip').length, textOf(byClass(b.host, 'tables-box__start')[0])], [0, m.START_WORDS]);
  const no = await open(10, NARROW, { refuse: "cannot sort by 'x'" });
  eq('B7 a refused page is the server\'s sentence', no.foot(), "cannot sort by 'x'");
  const doc = makeDoc('light');
  const [h1, h2] = [doc.createElement('div'), doc.createElement('div')];
  const [s1, s2] = [server(700), server(20)];
  await Promise.all([new m.TableBox(h1, { doc, fetch: s1.fetch, apiBase: 'a', table: 't1', narrowing: NARROW }).open(),
    new m.TableBox(h2, { doc, fetch: s2.fetch, apiBase: 'a', table: 't2', narrowing: NARROW }).open()]);
  await settle();
  eq('B8 two boxes on one page: each its table, its rows, its words', [s1.asked.every((u) => u.includes('/tables/t1')), s2.asked.every((u) => u.includes('/tables/t2')),
    textOf(byClass(h1, 'tables-box__foot')[0]), textOf(byClass(h2, 'tables-box__foot')[0])], [true, true, 'rows 1–500 of 700 · next page on scroll', 'all 20 rows']);
  // ── marking rows; a box opened by a server marking ──
  const store = new mods.store.MarkingStore();
  const name = mods.store.nextName(store);
  const md = makeDoc('light');
  const mh = md.createElement('div');
  const ms = server(30);
  const mb = new m.TableBox(mh, { doc: md, fetch: ms.fetch, apiBase: 'a', table: 'dt_log', narrowing: NARROW, markings: store, writes: name });
  await mb.open();
  await settle();
  const press = (k, extra = {}) => {
    const line = walk(mh).filter((n) => n.tagName === 'TR' && !String(n.className).includes('tb-table__pad') && n.parentNode && n.parentNode.tagName === 'TBODY')[k];
    line.dispatch('click', { stopPropagation() {}, ...extra });
  };
  press(0);
  press(1, { shiftKey: true });
  press(2);
  press(2);
  eq('K1 a press marks its row + under the box\'s name, Shift −, a press again takes it out; the head counts them',
    [store.entries(name), textOf(byClass(mh, 'tables-box__marks')[0]), byClass(mh, 'is-marked').length],
    [[['dt_log:r00000', 1], ['dt_log:r00001', -1]], '+ 1 · − 1 marked', 2]);
  const kd = makeDoc('light');
  const kh = kd.createElement('div');
  const ks = server(30);
  await new m.TableBox(kh, { doc: kd, fetch: ks.fetch, apiBase: 'a', table: 'dt_log', marking: 'mk7', title: '#2 + · 1 → 3 rows' }).open();
  await settle();
  const counted = ks.asked.filter((u) => u.includes('/data/count')).map((u) => new URLSearchParams(u.split('?')[1] || '').get('marking'));
  eq('K2 a box opened by a server marking reads its rows unnarrowed - the marking in its page and its count; its title said',
    [new URLSearchParams((ks.pages()[0] || '?').split('?')[1]).get('marking'), counted, textOf(byClass(kh, 'tables-box__foot')[0]), textOf(byClass(kh, 'tables-box__title')[0])],
    ['mk7', ['mk7', null], 'all 3 rows', '#2 + · 1 → 3 rows']);

  // ── the walk between tables ──
  const ch = mods.chain;
  eq('R1 a row\'s node id is the server\'s «relation:row id», and back - a row id of digits its number; no table, none',
    [ch.rowNodeId('lots', 'u-1'), ch.rowOfNodeId('lots:u-1'), ch.rowOfNodeId('lots:12'), ch.rowOfNodeId('nope')],
    ['lots:u-1', { table: 'lots', rowId: 'u-1' }, { table: 'lots', rowId: 12 }, null]);
  const DECL = { predicates: [
    { name: 'processed_with', subjects: ['wafer'], object: { types: ['recipe'] } },
    { name: 'inspected', subjects: ['wafer'], object: { types: ['die'] } },
    { name: 'in_container', subjects: ['die'], object: { types: ['wafer'] } }],
  sources: [
    { relation: 'insp', emits: ['inspected', 'in_container'], columns: [{ role: 'key', entity: 'wafer' }, { role: 'key', entity: 'die' }, { role: 'time', predicate: 'inspected' }] },
    { relation: 'proc', emits: ['processed_with'], columns: [{ role: 'key', entity: 'wafer' }, { role: 'qualifier', predicate: 'processed_with' }, { role: 'key', entity: 'recipe' }] }] };
  eq('R2 the types a table names are its sources\' key columns\' entities', [ch.typesOfTable(DECL, 'insp'), ch.typesOfTable(DECL, 'proc')], [['wafer', 'die'], ['wafer', 'recipe']]);
  eq('R3 the paths to a table go through a predicate it emits, one a type and its follow, the shortest first',
    ch.routesBetween(DECL, 'insp', 'proc').map(ch.routeWords), R3_WANT);
  const calls = [];
  const cfetch = async (url, init) => { calls.push([url, JSON.parse(init.body)]); return { ok: true, status: 200, json: async () => ({ id: 'k1', rev: 1, rows: [5] }) }; };
  await ch.keepRows({ fetch: cfetch, apiBase: 'a', world: 'w2' }, 'insp', ['u-1', 7]);
  await ch.reachRows({ fetch: cfetch, apiBase: 'a', world: 'w2' }, 'k1', { type: 'wafer', follow: ['processed_with'] }, 'proc');
  eq('R4 a hop: the rows kept by row_id in a body (no world - a marking is the reader\'s), then the reach by the marking in the world',
    calls, [['a/markings', { table: 'insp', column: 'row_id', values: ['u-1', 7] }],
      ['a/api/ledger/subgraph?world=w2', { reach: { marking: 'k1', type: 'wafer', follow: ['processed_with'], to: 'proc' } }]]);
  const kept = [];
  const kfetch = async (url) => {
    const q = new URLSearchParams(url.split('?')[1]);
    kept.push([q.get('marking'), q.get('skip'), q.get('after'), q.get('world')]);
    const skip = Number(q.get('skip'));
    return { ok: true, status: 200, json: async () => ({ data: [{ row_id: `m${skip}` }, { row_id: `m${skip + 1}` }].slice(0, skip ? 1 : 2) }) };
  };
  const marked = await ch.rowsOf({ fetch: kfetch, apiBase: 'a', world: 'w2' }, 'insp', 'k1', 2);
  eq('R5 a kept marking\'s rows page by page - the next page after the last row read, skip beside, in the world',
    [kept, marked.map((r) => r.row_id)], [[['k1', '0', null, 'w2'], ['k1', '2', 'm1', 'w2']], ['m0', 'm1', 'm2']]);

  // ── the compare ──
  const cm = mods.compare;
  const SIDES = [
    { sign: 1, rows: [{ step: 'A', r: 'w', n: 1 }, { step: 'B', r: 'y', n: 1 }, { step: 'B', r: 'x', n: 3 }, { step: 'C', r: 'z', n: 2 }] },
    { sign: -1, rows: [{ step: 'A', r: 'w', n: 1 }, { step: 'B', r: 'x', n: 2 }, { step: 'D', r: 'q', n: 5 }] }];
  const folded = cm.foldSides({ sides: SIDES, axes: ['step'], columns: ['r', 'n'], kinds: { n: 'number' } });
  eq('F1 a line an axis value: text UniqueConcatenate, number Avg; differing and one-sided lines first; a side without the value null',
    folded.map((l) => [l.axis, l.cells[1], l.cells[-1], l.differs, l.one]),
    [[['B'], { r: 'x, y', n: 2 }, { r: 'x', n: 2 }, ['r'], false], [['C'], { r: 'z', n: 2 }, null, [], true],
      [['D'], null, { r: 'q', n: 5 }, [], true], [['A'], { r: 'w', n: 1 }, { r: 'w', n: 1 }, [], false]]);
  const cd = makeDoc('light');
  const chost = cd.createElement('div');
  const told = [];
  const part = new cm.AxisCompare(chost, { doc: cd, onPick: (p) => told.push(p) });
  part.show({ title: 'proc', sides: SIDES, columns: ['step', 'r', 'n'], kinds: { n: 'number' }, axes: ['step'], shown: ['r', 'n'] });
  const bodyRows = () => walk(chost).filter((n) => n.tagName === 'TR' && n.parentNode && n.parentNode.tagName === 'TBODY');
  const all = bodyRows().map((tr) => tr.children.map((td) => td.textContent).join('|'));
  const onlyBox = byClass(chost, 'tables-compare__only')[0].children[0];
  onlyBox.checked = true;
  onlyBox.dispatch('change', {});
  const only = bodyRows().length;
  eq('F2 one table «axis | + | −», a missing side «−»; Differs only keeps the differing lines; each pick told to the page',
    [all, textOf(byClass(chost, 'tables-box__count')[0]), only, told.at(-1)],
    [['B|x, y|2|x|2', 'C|z|2|−|−', 'D|−|−|q|5', 'A|w|1|w|1'], '4 rows · 3 differ', 3, { axes: ['step'], columns: ['r', 'n'], only: true }]);

  // ── the store's names ──
  const st = new mods.store.MarkingStore();
  const [n1, n2] = [mods.store.nextName(st), mods.store.nextName(st)];
  st.set(n1, 'a', 1);
  const v = st.version(n1);
  st.clear(n1, { drop: true });
  const reGiven = mods.store.nextName(st);
  eq('S1 nextName holds what it gives - two in one tick differ, though empty; a dropped one is given again, its version kept; labelOf «#N»',
    [n1, n2, st.names(), reGiven, st.version(reGiven) >= v && v > 0, mods.store.labelOf('marking:3'), mods.store.labelOf('walk-reach')],
    ['marking:1', 'marking:2', [], 'marking:1', true, '#3', 'walk-reach']);
  return { ran: ran.length, names: ran, failures };
}

const REAL = { box: await import('../src/tables/table_box.js'), chain: await import('../src/tables/chain.js'),
  compare: await import('../src/tables/axis_compare.js'), store: await import('../src/rnd_board/marking_store.js') };
const base = await suite(REAL);
for (const name of base.names) console.log(`  ${base.failures.some((f) => f.startsWith(name + ':')) ? 'FAIL' : 'PASS'} ${name}`);
base.failures.forEach((f) => console.log(`  FAIL  ${f}`));

const swap = (from, to) => (t) => { if (!t.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`); return t.split(from).join(to); };
const MUTANTS = [
  { id: 'XT1', what: 'the first table opens whole', catches: ['N1', 'B1'], mutate: swap('return Boolean(n.q || n.tx || Object.keys(n.filters).length);', 'return true;') },
  { id: 'XT2', what: 'a page asks without the narrowing', catches: ['N5', 'B2'], mutate: swap("  const p = new URLSearchParams(text || '');\n  if (marking) p.set('marking', marking);\n  p.set('skip'", "  const p = new URLSearchParams('');\n  if (marking) p.set('marking', marking);\n  p.set('skip'") },
  { id: 'XT3', what: 'no order means latest first, not entered order', catches: ['N5'], mutate: swap("order ? order.column : 'row_id'", "order ? order.column : 'updated_at'") },
  { id: 'XT4', what: 'a full page always says more, past an exact count', catches: ['P1', 'B3'],
    mutate: swap('return lastPage === PAGE_ROWS && !(c.total !== null && !c.capped && read >= c.total);', 'return lastPage === PAGE_ROWS;') },
  { id: 'XT5', what: 'a chip\'s remove keeps its filter', catches: ['N3', 'B6'], mutate: swap('  delete n.filters[column];\n', '') },
  { id: 'XT6', what: 'a column the row carries itself reads blank', catches: ['L1'], mutate: swap(': (row[column] ?? null);', ': null;') },
  { id: 'XT7', what: 'a refusal is the screen\'s words', catches: ['B7'], mutate: swap("this.say(await refusalText(res, 'Rows read failed'));", "this.say('Rows read failed');") },
  { id: 'XT8', what: 'a scroll near the end reads nothing', catches: ['B4'], mutate: swap('if (left < MORE_WITHIN_LINES) this.page();', 'if (false) this.page();') },
  { id: 'XT9', what: 'a head pressed sorts the page in the browser', catches: ['B5'],
    mutate: swap('declare: ({ sort }) => this.orderBy(this.columns[Number(sort.key.slice(3)) - 1], sort.desc),', 'declare: () => {},') },
  { id: 'XT10', what: 'Shift marks + too', catches: ['K1'], mutate: swap('const { sign } = markingIntent(event);', 'const sign = SIGN.CASE;') },
  { id: 'XT11', what: 'a box opened by a marking asks without it', catches: ['K2'], mutate: swap("  if (marking) p.set('marking', marking);\n", '') },
  { id: 'XT12', what: 'a box opened by a marking waits for a search', catches: ['K2'], mutate: swap('narrows(this.narrowing) || Boolean(this.marking)', 'narrows(this.narrowing)') },
  { id: 'XC1', what: 'a path through no predicate the next table emits is offered', catches: ['R3'], key: 'chain',
    mutate: swap('if (!route.follow.some((p) => emitted.has(p))) continue;', '') },
  { id: 'XC2', what: 'the rows kept by another column', catches: ['R4'], key: 'chain', mutate: swap("column: 'row_id'", "column: 'id'") },
  { id: 'XF1', what: 'a number column folded as text', catches: ['F1'], key: 'compare', mutate: swap("kinds[column] === 'number' ? FOLD_NUMBER : FOLD_TEXT", 'FOLD_TEXT') },
  { id: 'XF2', what: 'the differing lines not first', catches: ['F1'], key: 'compare', mutate: swap('return lines.sort((a, b) => up(a) - up(b) || order(a, b));', 'return lines.sort((a, b) => order(a, b));') },
  { id: 'XF3', what: 'Differs only keeps every line', catches: ['F2'], key: 'compare', mutate: swap('const kept = this.only ? lines.filter((l) => l.differs.length || l.one) : lines;', 'const kept = lines;') },
  { id: 'XS1', what: 'nextName does not hold what it gives', catches: ['S1'], key: 'store', mutate: swap('  store._marks.set(name, new Map());\n  return name;', '  return name;') },
  { id: 'XS2', what: 'a dropped name stays held', catches: ['S1'], key: 'store', mutate: swap('if (drop) this._marks.delete(name);', '') },
  { id: 'XK1', what: 'a box\'s next page by skip alone', catches: ['B4'], mutate: swap("key: rowsKey(this.rows, 'after'), ", '') },
  { id: 'XK2', what: 'a marking\'s next page by skip alone', catches: ['R5'], key: 'chain',
    mutate: swap("    for (const [side, rowId] of Object.entries(rowsKey(out, 'after') || {})) p.set(side, rowId);\n", '') },
];
console.log('');
const { wrong } = await scoreMutants(MUTANTS, async (mu) => suite({ ...REAL, [mu.key || 'box']: (await loadWithProbe(SUBJECTS[mu.key || 'box'], { mutate: mu.mutate })).module }),
  { baselineRan: base.ran, baselineNames: base.names, title: '-- defect mutants (each must be CAUGHT by its named line) -----------' });
const failed = base.failures.length + wrong;
console.log(`\n${base.ran - base.failures.length} passed, ${base.failures.length} failed; ${MUTANTS.length - wrong}/${MUTANTS.length} defects caught, ${wrong} escaped.`);
console.log(`ASSERTIONS ${base.ran + MUTANTS.length} ${failed}`);
process.exit(failed ? 1 : 0);
