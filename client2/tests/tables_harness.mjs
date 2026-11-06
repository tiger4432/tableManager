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
//         the count says all; scrolled near the end it reads the next; a head pressed orders by the server; a chip's
//         remove reads again without it; a refusal is the server's sentence; two boxes on one page do not meet
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
const SUBJECT = path.join(HERE, '..', 'src', 'tables', 'table_box.js');
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

const NARROW = `filters=${encodeURIComponent(JSON.stringify({ dt_lot: { filterType: 'text', type: 'contains', filter: 'LOT-10' } }))}`;

async function suite(m) {
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
  eq('B4 near the end the next page is read, below the first', [b.srv.pages().length, new URLSearchParams((b.srv.pages()[1] || '?').split('?')[1]).get('skip'), b.foot()],
    [2, '500', 'rows 1–1,000 of 1,284 · next page on scroll']);
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
  return { ran: ran.length, names: ran, failures };
}

const real = await import('../src/tables/table_box.js');
const base = await suite(real);
for (const name of base.names) console.log(`  ${base.failures.some((f) => f.startsWith(name + ':')) ? 'FAIL' : 'PASS'} ${name}`);
base.failures.forEach((f) => console.log(`  FAIL  ${f}`));

const swap = (from, to) => (t) => { if (!t.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`); return t.split(from).join(to); };
const MUTANTS = [
  { id: 'XT1', what: 'the first table opens whole', catches: ['N1', 'B1'], mutate: swap('return Boolean(n.q || n.tx || Object.keys(n.filters).length);', 'return true;') },
  { id: 'XT2', what: 'a page asks without the narrowing', catches: ['N5', 'B2'], mutate: swap("  const p = new URLSearchParams(text || '');\n  p.set('skip'", "  const p = new URLSearchParams('');\n  p.set('skip'") },
  { id: 'XT3', what: 'no order means latest first, not entered order', catches: ['N5'], mutate: swap("order ? order.column : 'row_id'", "order ? order.column : 'updated_at'") },
  { id: 'XT4', what: 'a full page always says more, past an exact count', catches: ['P1', 'B3'],
    mutate: swap('return lastPage === PAGE_ROWS && !(c.total !== null && !c.capped && read >= c.total);', 'return lastPage === PAGE_ROWS;') },
  { id: 'XT5', what: 'a chip\'s remove keeps its filter', catches: ['N3', 'B6'], mutate: swap('  delete n.filters[column];\n', '') },
  { id: 'XT6', what: 'a column the row carries itself reads blank', catches: ['L1'], mutate: swap(': (row[column] ?? null);', ': null;') },
  { id: 'XT7', what: 'a refusal is the screen\'s words', catches: ['B7'], mutate: swap("this.say(await refusalText(res, 'Rows read failed'));", "this.say('Rows read failed');") },
  { id: 'XT8', what: 'a scroll near the end reads nothing', catches: ['B4'], mutate: swap('if (left < MORE_WITHIN_LINES) this.page();', 'if (false) this.page();') },
  { id: 'XT9', what: 'a head pressed sorts the page in the browser', catches: ['B5'],
    mutate: swap('declare: ({ sort }) => this.orderBy(this.columns[Number(sort.key.slice(3)) - 1], sort.desc),', 'declare: () => {},') },
];
console.log('');
const { wrong } = await scoreMutants(MUTANTS, async (mu) => suite((await loadWithProbe(SUBJECT, { mutate: mu.mutate })).module),
  { baselineRan: base.ran, baselineNames: base.names, title: '-- defect mutants (each must be CAUGHT by its named line) -----------' });
const failed = base.failures.length + wrong;
console.log(`\n${base.ran - base.failures.length} passed, ${base.failures.length} failed; ${MUTANTS.length - wrong}/${MUTANTS.length} defects caught, ${wrong} escaped.`);
console.log(`ASSERTIONS ${base.ran + MUTANTS.length} ${failed}`);
process.exit(failed ? 1 : 0);
