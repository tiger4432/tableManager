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
  part(L).mark([lines[0].id], {});
  await settle();
  say(`Dela causes holds ${page.markings.entries(causes).map(([id]) => (page.layers.graph.nodes.get(id) || {}).label || id).join(', ')}`);
}
process.exit(0);
