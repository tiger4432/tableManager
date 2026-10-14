// The Board's clock on an operating-shape box (lead 10-14 «누름 → 연쇄 마지막 부품 그림 끝 ≤ 1 s»): ten wafers marked
// as the start; A a map of their dies (x, y), T a table of the dies with their warpage (a value walk from every die);
// a coordinate pressed in A marks its dies - B a scatter of those dies' void_area against warpage, C a cross table of
// them by the core wafer they were bonded from. Each step's clock per part: asked · first answer · all in · drawn, the
// requests (and how many at once), fetch · fold · draw ms. The draw is the stub document's, not a browser's paint.
// Box numbers - not a pass/fail gate.
//
//   node client2/scripts/board_opshape_clock.mjs [--api http://127.0.0.1:18769] [--wafers W01,W02,...]
// CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
import { makeDoc } from '../tests/lib/board_dom.mjs';

const argOf = (k, d) => (process.argv.includes(k) ? process.argv[process.argv.indexOf(k) + 1] : d);
const API = argOf('--api', 'http://127.0.0.1:18769');
const WAFERS = argOf('--wafers', 'W01,W02,W03,W04,W05,W06,W07,W08,W09,W10').split(',');
const main = await import('../src/testbed/main.js');
const { entitySeedId } = await import('../src/rnd_board/api.js');
const { SIGN } = await import('../src/rnd_board/marking_store.js');

const settle = async () => { for (let i = 0; i < 40; i += 1) await new Promise((r) => setTimeout(r, 5)); };
const until = async (test, ms = 120000) => { const t0 = Date.now(); while (!test()) { if (Date.now() - t0 > ms) throw new Error('timed out'); await new Promise((r) => setTimeout(r, 20)); } await settle(); };
const charts = { init: () => ({ setOption() {}, dispatchAction() {}, on() {}, getZr() { return { on() {} }; }, resize() {}, dispose() {} }) };
const doc = makeDoc('dark');
const host = doc.createElement('div');
doc.body.appendChild(host);
const page = await main.boot({ doc, host, apiBase: API, charts, storage: null, theme: 'dark' });
const part = (id) => page.shell.partOf(id);
const say = (...x) => console.log(...x);

const book = page.markingBook;
const dies = book.add();
book.edit(dies, { label: 'Dies' });
const key = (name) => ({ steps: [], value: { on: 'key', name }, words: [name] });
const measured = (q) => ({ steps: [{ predicate: 'measures', direction: 'outgoing' }], end: entitySeedId('quantity', { quantity: q }), value: { on: 'edge', name: 'value' }, words: [q] });
const CORE = { steps: [{ predicate: 'bonded_from', direction: 'outgoing' }, { predicate: 'in_container', direction: 'outgoing' }], value: { on: 'label', name: 'name' }, words: ['core wafer'] };
const declare = (id, patch) => part(id).setDeclaration({ ...part(id).declaration(), system: null, filter: [], ...patch });
for (const id of ['scatter-1', 'cross-1', 'marked']) page.shell.remove(id);
const A = page.add('map');
const T = page.add('table');
const B = page.add('scatter');
const C = page.add('crossTable');
const WIDE = { node_limit: 1000 };
declare(A, { walk: WIDE, row: 'die', start: { marking: 'marking:start' }, writes: dies, encode: { x: key('x'), y: key('y') } });
declare(T, { walk: WIDE, row: 'die', start: { marking: 'marking:start' }, writes: null, encode: { col1: key('x'), col2: key('y'), col3: measured('warpage') } });
declare(B, { walk: WIDE, row: 'die', start: { marking: dies }, writes: null, encode: { x: measured('void_area'), y: measured('warpage') } });
declare(C, { walk: WIDE, row: 'die', start: { marking: dies }, writes: null, encode: { rows: CORE } });
// A and T take the route wafer -> die along inspected (this box's wafers name their dies so)
for (const id of [A, T]) declare(id, { route: { hops: 1, follow: ['inspected'], chain: ['wafer', 'die'], loops: [] } });

const clocks = new Map();
const watch = (id) => {
  const p = part(id);
  const c = { requests: 0, inFlight: 0, together: 0, fetchMs: 0, foldMs: 0, drawMs: 0 };
  clocks.set(id, c);
  if (!p.__clocked) {
    p.__clocked = true;
    const f = p.fetchWalk;
    p.fetchWalk = async (params) => {
      const k = clocks.get(id);
      const t = performance.now();
      k.requests += 1; k.inFlight += 1; k.together = Math.max(k.together, k.inFlight);
      if (k.asked == null) k.asked = t;
      try { return await f(params); } finally { const e = performance.now(); k.inFlight -= 1; k.fetchMs += e - t; if (k.first == null) k.first = e; k.received = e; }
    };
    const fold = p.refold.bind(p);
    const draw = p.render.bind(p);
    p.render = (...a) => { const k = clocks.get(id); const t = performance.now(); const r = draw(...a); const e = performance.now(); k.drawMs += e - t; k.drawn = e; return r; };
    p.refold = (...a) => { const k = clocks.get(id); const t = performance.now(); const d0 = k.drawMs; const r = fold(...a); k.foldMs += performance.now() - t - (k.drawMs - d0); return r; };
  }
};
const timed = async (name, press, ids) => {
  for (const id of ids) watch(id);
  const t0 = performance.now();
  await press();
  for (const id of ids) await until(() => clocks.get(id).drawn != null && part(id).state !== 'walking' && !(part(id).aborts && part(id).aborts.size));
  const ms = (x) => (x == null ? '-' : String(Math.round(x - t0)));
  say(`CLOCK ${name} (ms from the press): part | rows | asked | first answer | all in | drawn | requests (at once) | fetch | fold | draw`);
  for (const id of ids) {
    const c = clocks.get(id);
    say(`CLOCK   ${id} | ${(page.stats.get(id) || {}).of || 0} | ${ms(c.asked)} | ${ms(c.first)} | ${ms(c.received)} | ${ms(c.drawn)} | ${c.requests} (${c.together}) | ${Math.round(c.fetchMs)} | ${Math.round(c.foldMs)} | ${Math.round(c.drawMs)}`);
  }
  say(`CLOCK ${name}: the last part drawn at ${Math.round(Math.max(...ids.map((id) => clocks.get(id).drawn)) - t0)} ms`);
};

await timed('ten wafers marked -> A, T', () => page.markings.replace('marking:start', WAFERS.map((w) => [entitySeedId('wafer', { wafer: w }), SIGN.CASE])), [A, T]);
say('A', part(A).state, part(A).refusal || '', JSON.stringify(part(A).walkedRoute), JSON.stringify(part(A).rowWalk && part(A).rowWalk.ask)); const cells = part(A).model.cells;
say(`A map: ${cells.length} cells, T rows ${(page.stats.get(T) || {}).of}, walks so far`);
for (const cell of [cells[Math.floor(cells.length / 2)], cells[1]]) {
  await timed(`A pressed (${cell.where}, ${cell.ids.length} dies) -> B, C`, () => part(A).markHub([['x', cell.where[0]], ['y', cell.where[1]]], cell.ids, {}), [B, C]);
}
say(`B points ${part(B).model.points.length}, C rows ${part(C).model.rowKeys.length}`);
process.exit(0);
