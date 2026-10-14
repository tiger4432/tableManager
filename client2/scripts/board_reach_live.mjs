// Reach on a live box (lead-board-12, lead 10-12 «Reach(노드) = 걷기의 aux 판정»): a Table of one wafer's dies with a
// column Reach(defect_kind("dela")) - the row walk carries that node (aux) and each die reads the server's judgment:
// found ✓ · none ✗ · unknown empty (counted on the status line). Prints the requests, the answers' counts, the ms.
// Box numbers - not a pass/fail gate.
//
//   node client2/scripts/board_reach_live.mjs [--api http://127.0.0.1:18769] [--wafer W01] [--to 'defect_kind("dela")']
// CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
import { makeDoc } from '../tests/lib/board_dom.mjs';

const argOf = (k, d) => (process.argv.includes(k) ? process.argv[process.argv.indexOf(k) + 1] : d);
const API = argOf('--api', 'http://127.0.0.1:18769');
const WAFER = argOf('--wafer', 'W01');
const TO = argOf('--to', 'defect_kind("dela")');
const main = await import('../src/testbed/main.js');
const { entitySeedId } = await import('../src/rnd_board/api.js');
const { SIGN } = await import('../src/rnd_board/marking_store.js');

const settle = async () => { for (let i = 0; i < 40; i += 1) await new Promise((r) => setTimeout(r, 5)); };
const until = async (test, ms = 120000) => { const t0 = Date.now(); while (!test()) { if (Date.now() - t0 > ms) throw new Error('timed out'); await new Promise((r) => setTimeout(r, 20)); } await settle(); };
const charts = { init: () => ({ setOption() {}, dispatchAction() {}, on() {}, getZr() { return { on() {} }; }, resize() {}, dispose() {} }) };
const asked = [];
const fetchImpl = async (url, init) => { const u = String(url); if (u.includes('/api/ledger/subgraph')) asked.push(u); return fetch(u, init); };
const doc = makeDoc('dark');
const host = doc.createElement('div');
doc.body.appendChild(host);
const page = await main.boot({ doc, host, apiBase: API, fetchImpl, charts, storage: null, theme: 'dark' });
const part = (id) => page.shell.partOf(id);
const say = (...x) => console.log(...x);
for (const id of ['scatter-1', 'cross-1', 'marked']) page.shell.remove(id);
const T = page.add('table');
const col = (text) => ({ expr: text, words: [text] });
part(T).setDeclaration({ ...part(T).declaration(), system: null, filter: [], walk: { node_limit: 1000 }, row: 'die', start: { marking: 'marking:start' }, writes: null,
  encode: { col1: { steps: [], value: { on: 'label', name: 'name' }, words: ['name'] }, col2: col(`Reach(${TO})`) } });
const n0 = asked.length;
const t0 = performance.now();
page.markings.replace('marking:start', [[entitySeedId('wafer', { wafer: WAFER }), SIGN.CASE]]);
await until(() => part(T).state !== 'walking' && !(part(T).aborts && part(T).aborts.size) && part(T).model);
const ms = Math.round(performance.now() - t0);
for (const u of asked.slice(n0)) { const q = new URL(u).searchParams; say(`asked follow ${q.getAll('follow').join('+') || '(all)'} hops ${q.get('hops')} aux ${q.getAll('aux').length}`); }
const said = {};
for (const l of part(T).model.lines) said[l.cells[1].text || '(unknown)'] = (said[l.cells[1].text || '(unknown)'] || 0) + 1;
say(`T ${part(T).state} ${part(T).refusal || ''} in ${ms} ms: ${part(T).model.lines.length} dies, Reach ${JSON.stringify(said)}`);
say(`status: ${JSON.stringify((page.stats.get(T) || {}).unknown)} unknown`);
process.exit(0);
