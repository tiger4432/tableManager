// The lens scene on a live box (owner 10-14 «행 = 웨이퍼 아이디 · 열 = dela 와 닿는 퀀티티 이름 · 값 = 미디언», lead-board-11):
// a Table L starting from the written node defect_kind("dela"), its rows the quantities - walked along every route's
// predicates from defect_kind to quantity (no static-only rule yet: the owner is asked) - and a row pressed marks
// «Dela causes». Prints the routes, the walk asked, the rows and the marking. Box numbers - not a pass/fail gate.
//
//   node client2/scripts/board_lens_live.mjs [--api http://127.0.0.1:18769] [--kind dela]
// CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
import { makeDoc } from '../tests/lib/board_dom.mjs';

const argOf = (k, d) => (process.argv.includes(k) ? process.argv[process.argv.indexOf(k) + 1] : d);
const API = argOf('--api', 'http://127.0.0.1:18769');
const KIND = argOf('--kind', 'dela');
const main = await import('../src/testbed/main.js');

const settle = async () => { for (let i = 0; i < 40; i += 1) await new Promise((r) => setTimeout(r, 5)); };
const until = async (test, ms = 60000) => { const t0 = Date.now(); while (!test()) { if (Date.now() - t0 > ms) throw new Error('timed out'); await new Promise((r) => setTimeout(r, 20)); } await settle(); };
const charts = { init: () => ({ setOption() {}, dispatchAction() {}, on() {}, getZr() { return { on() {} }; }, resize() {}, dispose() {} }) };
const asked = [];
const fetchImpl = async (url, init) => { const u = String(url); if (u.includes('/api/ledger/subgraph')) asked.push(u); return fetch(u, init); };
const doc = makeDoc('dark');
const host = doc.createElement('div');
doc.body.appendChild(host);
const page = await main.boot({ doc, host, apiBase: API, fetchImpl, charts, storage: null, theme: 'dark' });
const part = (id) => page.shell.partOf(id);
const say = (...x) => console.log(...x);

const causes = page.markingBook.add();
page.markingBook.edit(causes, { label: 'Dela causes' });
for (const id of ['scatter-1', 'cross-1', 'marked']) page.shell.remove(id);
const L = page.add('table');
const name = { steps: [], value: { on: 'label', name: 'name' }, words: ['name'] };
const t0 = performance.now();
part(L).setDeclaration({ ...part(L).declaration(), system: null, filter: [], walk: { node_limit: 1000 }, row: 'quantity',
  start: { node: `defect_kind("${KIND}")` }, writes: causes, encode: { col1: name } });
await until(() => part(L).state !== 'walking' && !(part(L).aborts && part(L).aborts.size));
const ms = Math.round(performance.now() - t0);
say(`L ${part(L).state} ${part(L).refusal || ''}`);
say(`L start types ${JSON.stringify(part(L).startTypes())}; routes ${part(L).routes().map((r) => r.chain.join('>') + '[' + r.follow.join('+') + ']').join(' | ')}`);
for (const u of asked) { const q = new URL(u).searchParams; say(`L asked follow ${q.getAll('follow').join('+') || '(all)'} hops ${q.get('hops')} collect ${q.getAll('collect').join('+')}`); }
const lines = part(L).model ? part(L).model.lines : [];
say(`L rows ${lines.length} (${lines.map((l) => l.cells[0].text).join(', ')}) in ${ms} ms`);
if (lines.length) {
  // every quantity L reached - «Dela causes» as a whole (Ctrl presses each row)
  part(L).mark(lines.map((l) => l.id), {});
  await settle();
  say(`Dela causes holds ${page.markings.entries(causes).map(([id]) => (page.layers.graph.nodes.get(id) || {}).label || id).join(', ')}`);
}
// THE CROSS TABLE (lead-board-11 ②): rows the dies of the wafers marked as the start, the row axis the wafer, the column
// axis the quantity name, the cell Median of the measured value - a die's measures edges each a mark (units.js marksOf,
// lead-board-13: the column and the cell read off the same edge); Limit by «Dela causes» along the relation die
// -measures- quantity.
const WAFERS = argOf('--wafers', 'W01,W02,W03,W04,W05,W06,W07,W08,W09,W10').split(',');
const { entitySeedId } = await import('../src/rnd_board/api.js');
const { SIGN } = await import('../src/rnd_board/marking_store.js');
page.relations.set('list', [{ from: 'die', predicate: 'measures', to: 'quantity', both: true }]);
const X = page.add('crossTable');
const way = (predicate, direction, value, words) => ({ steps: [{ predicate, direction }], value, words: [words] });
const t1 = performance.now();
part(X).setDeclaration({ ...part(X).declaration(), system: null, filter: [], walk: { node_limit: 1000 }, row: 'die', start: { marking: 'marking:start' }, writes: null,
  limit: { markings: [causes], must: 'all', none: 'all' },
  encode: { rows: way('inspected', 'incoming', { on: 'label', name: 'name' }, 'wafer'), columns: way('measures', 'outgoing', { on: 'label', name: 'name' }, 'quantity'),
    cells: { ...way('measures', 'outgoing', { on: 'edge', name: 'value' }, 'value'), reduce: 'Median' } } });
page.markings.replace('marking:start', WAFERS.map((w) => [entitySeedId('wafer', { wafer: w }), SIGN.CASE]));
await until(() => part(X).state !== 'walking' && !(part(X).aborts && part(X).aborts.size) && part(X).model, 120000);
const xm = part(X).model;
const st = page.stats.get(X) || {};
say(`X ${part(X).state} in ${Math.round(performance.now() - t1)} ms: rows ${xm.rowKeys.length} (${xm.rowKeys.slice(0, 3).join(', ')}...), columns ${xm.colKeys.join(', ')}; status ${JSON.stringify(st.rows)} of ${JSON.stringify(st.of)} rows, limit ${st.limit}`);
for (let r = 0; r < Math.min(2, xm.rowKeys.length); r += 1) say(`X ${xm.rowKeys[r]}: ${xm.colKeys.map((c, k) => `${c}=${xm.grid[r][k].value === null ? '-' : Number(xm.grid[r][k].value).toFixed(4)} (${xm.grid[r][k].ids.length})`).join(' ')}`);
// the pairing checked against the box: the median of each quantity's measures values over the first wafer's dies
const first = xm.rowKeys[0];
if (!first) process.exit(0);
const wid = entitySeedId('wafer', { wafer: first });
const dies = await (await fetch(`${API}/api/ledger/subgraph?id=${encodeURIComponent(wid)}&hops=1&follow=inspected&collect=die&node_limit=1000&propagation=false`)).json();
const ids = dies.nodes.filter((n) => n.type === 'die').map((n) => n.id);
const byQ = {};
for (let i = 0; i < ids.length; i += 300) {
  const q = new URLSearchParams({ id: ids[i], hops: '1', node_limit: '1000', propagation: 'false' });
  for (const s of ids.slice(i, i + 300)) q.append('positive', s);
  q.append('follow', 'measures'); q.append('collect', 'quantity');
  const b = await (await fetch(`${API}/api/ledger/subgraph?${q}`)).json();
  const name = new Map(b.nodes.map((n) => [n.id, n.label]));
  for (const e of b.edges) if (e.predicate === 'measures' && name.has(e.target)) (byQ[name.get(e.target)] = byQ[name.get(e.target)] || []).push(Number(e.qualifiers.value));
}
const median = (v) => { const s = [...v].sort((a, b) => a - b); const m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
say(`box ${first}: ${Object.entries(byQ).map(([q, v]) => `${q}=${median(v).toFixed(4)} (${v.length})`).join(' ')}`);
process.exit(0);
