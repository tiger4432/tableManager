/**
 * rnd_board — 「닿는 곳」 scoring
 *
 * WHAT THIS SCORES:
 *   A  the model groups a REAL one-hop answer by predicate, with the target kinds
 *   B  the count is REACHED NODES, not edges -- two edges to one node is one place
 *   C  clicking a row expands: that predicate's node SET lands in the write marking
 *   D  two instances on one screen do not interfere -- the definition of 조립식
 *   E  the absences are DIFFERENT SENTENCES, never one empty box
 *   F  `truncated.depth` is the QUESTION, not a loss -- hops=1 always cuts depth
 *
 * 🔴 THE FIXTURE IS REAL SERVER OUTPUT (`fixtures/rnd_board_reach.json`), captured off the
 *    live ledger. The four numbers it pins are the Lead PM's own measurement, reproduced
 *    independently before this file was written -- so green here means the screen agrees
 *    with the ledger, not with me.
 *
 * 🔴 EVERY ASSERTION IS WOKEN BY A MUTANT, and a mutation whose anchor has rotted STOPS the
 *    run instead of reading as a pass.
 *
 * CONSOLE OUTPUT IS ASCII ONLY (cp949-safe) except for the sentences it quotes.
 */

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const BOARD_DIR = path.join(HERE, '..', 'src', 'rnd_board');
const LF = String.fromCharCode(10);
const CRLF = String.fromCharCode(13, 10);
const dataUrl = (src) => `data:text/javascript;base64,${Buffer.from(src, 'utf8').toString('base64')}`;

const BODY = JSON.parse(readFileSync(path.join(HERE, 'fixtures', 'rnd_board_reach.json'), 'utf8'));

let ran = 0;
let failedList = [];
const ok = (name, cond, detail) => {
  ran += 1;
  if (cond) { console.log(`  ok   ${name}`); return; }
  failedList.push(detail ? `${name} -- ${detail}` : name);
  console.log(`  FAIL ${name}${detail ? ' -- ' + detail : ''}`);
};
const eq = (name, got, want) => ok(name, String(got) === String(want), `got ${got}, want ${want}`);

async function loadModules(mutate = {}) {
  const read = (file) => {
    const text = readFileSync(path.join(BOARD_DIR, file), 'utf8').split(CRLF).join(LF);
    const fn = mutate[file];
    const out = fn ? fn(text) : text;
    if (fn && out === text) throw new Error(`mutation anchor is GONE: ${file}`);
    return out;
  };
  const storeUrl = dataUrl(read('marking_store.js'));
  const panelUrl = dataUrl(read('panel.js').split("'./marking_store.js'").join(`'${storeUrl}'`));
  const tableUrl = dataUrl(read('table_part.js')
    .split("'./panel.js'").join(`'${panelUrl}'`)
    .split("'./marking_store.js'").join(`'${storeUrl}'`));
  const reachUrl = dataUrl(read('reach_panel.js')
    .split("'./panel.js'").join(`'${panelUrl}'`)
    .split("'./marking_store.js'").join(`'${storeUrl}'`)
    .split("'./table_part.js'").join(`'${tableUrl}'`));
  const apiUrl = dataUrl(read('api.js'));
  return {
    store: await import(storeUrl),
    reach: await import(reachUrl),
    api: await import(apiUrl),
  };
}

/** The smallest document a part can be scored under. No jsdom, no globals. */
function makeDoc() {
  const make = (tag) => ({
    tagName: tag, children: [], style: {}, attrs: {}, _text: '', className: '', listeners: {},
    appendChild(c) { this.children.push(c); return c; },
    append(...cs) { cs.forEach((c) => this.appendChild(c)); },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return this.attrs[k] === undefined ? null : this.attrs[k]; },
    addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); },
    click(event) { (this.listeners.click || []).forEach((fn) => fn(event || {})); },
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); },
    set textContent(v) { this._text = String(v); this.children = []; },
  });
  return { createElement: make };
}

const walkAll = (el, out = []) => { out.push(el); el.children.forEach((c) => walkAll(c, out)); return out; };
const rowsOf = (host) => walkAll(host).filter((e) => (e.className || '').includes('rb-table-row'));
const textOf = (host) => walkAll(host).map((e) => e._text).join(' ');
const settle = async () => { for (let i = 0; i < 6; i += 1) await Promise.resolve(); };

async function suite(mods) {
  const { store: S, reach: R, api: A } = mods;
  const { MarkingStore, SIGN } = S;
  const { ReachPanel } = R;
  const { reachModel } = A;

  const SEED = BODY.seed.id;
  const model = reachModel({ ok: true, status: 200, body: BODY });

  console.log(`${LF}-- A. the model reads a real one-hop answer --`);
  ok('A1 the answer is not a refusal', model.ok === true, JSON.stringify(model.message));
  eq('A2 it kept every node', model.nodes, 82);
  eq('A3 it kept every edge', model.edges, 87);
  eq('A4 four predicates came back', model.rows.length, 4);
  const by = Object.fromEntries(model.rows.map((r) => [r.predicate, r]));
  eq('A5 inspected reaches 39', by.inspected && by.inspected.count, 39);
  eq('A6 bonded_from reaches 29', by.bonded_from && by.bonded_from.count, 29);
  // 🔴 THE DISCRIMINATING ROW. The Lead PM's four numbers (39/29/10/9) are EDGE counts;
  //    `binding` is the only one where edges and places disagree, so it is the only row
  //    that can tell the two rules apart. A screen that shows 10 and marks 4 has lied,
  //    and the other three rows would never have caught it.
  eq('A7 binding reaches 4 places', by.binding && by.binding.count, 4);
  eq('A7b on 10 edges', by.binding && by.binding.edges, 10);
  ok('A7c the other three agree, which is why they decide nothing',
    ['inspected', 'bonded_from', 'processed_with'].every((p) => by[p].count === by[p].edges));
  eq('A7d and the kind count follows the places, not the edges',
    by.binding.kinds.map((k) => `${k.type} ${k.count}`).join(','), 'Value 4');
  eq('A8 processed_with reaches 9', by.processed_with && by.processed_with.count, 9);
  eq('A9 inspected goes to die', by.inspected.kinds.map((k) => k.type).join(','), 'die');
  eq('A10 bonded_from goes to wafer', by.bonded_from.kinds.map((k) => k.type).join(','), 'wafer');
  eq('A11 the biggest predicate is first', model.rows[0].predicate, 'inspected');

  console.log(`${LF}-- B. the count is PLACES, not edges --`);
  const totalReached = model.rows.reduce((n, r) => n + r.nodeIds.length, 0);
  ok('B1 every row counts its own node set', model.rows.every((r) => r.count === r.nodeIds.length));
  ok('B2 no row repeats a node', model.rows.every((r) => new Set(r.nodeIds).size === r.nodeIds.length));
  // 🔴 B3 NEEDS AN INPUT THAT CAN TELL THE RULE APART. The real answer has no self-loop,
  //    so on it the guard is unreachable and removing the guard changes nothing -- the
  //    assertion would have been decoration on green. This feeds one: an edge whose two
  //    ends are both the seed. 「이 노드에서 이 노드로」 is not a place you can go.
  ok('B3 the real answer has none to hide behind',
    model.rows.every((r) => !r.nodeIds.includes(SEED)));
  const selfLoop = reachModel({ ok: true, status: 200, body: { ...BODY,
    edges: [...BODY.edges, { predicate: 'binding', source: SEED, target: SEED }] } });
  const selfRow = selfLoop.rows.find((r) => r.predicate === 'binding');
  ok('B3b a self-loop is not a destination', !selfRow.nodeIds.includes(SEED),
    JSON.stringify(selfRow.nodeIds.length));
  eq('B3c and it did not inflate the count', selfRow.count, 4);
  ok('B4 places never exceed edges', totalReached <= model.edges, `${totalReached} vs ${model.edges}`);

  console.log(`${LF}-- F. depth is the question, not a loss --`);
  ok('F1 the fixture really did cut depth', BODY.truncated.depth === true);
  eq('F2 and the model does not call that a cut', JSON.stringify(model.cut), '[]');

  console.log(`${LF}-- C. clicking a row expands into the write marking --`);
  const markings = new MarkingStore();
  markings.set('marking:1', SEED, SIGN.CASE);
  const doc = makeDoc();
  const host = doc.createElement('div');
  const asked = [];
  const panel = new ReachPanel(host, {
    doc,
    markings,
    reads: 'marking:1',
    writes: 'marking:2',
    start: { marking: 'marking:1', groupby: 'wafer' },
    collect: 'reach',
    walk: (spec) => { asked.push(spec); return Promise.resolve(model); },
  });
  panel.mount();
  await settle();

  eq('C1 it asked exactly once', asked.length, 1);
  eq('C2 it asked the reach collect', asked[0].collect, 'reach');
  ok('C3 the marking was the subject', asked[0].start && asked[0].start.value === SEED,
    JSON.stringify(asked[0].start && asked[0].start.value));
  ok('C4 the part does not carry hops', asked[0].hops === undefined, String(asked[0].hops));
  eq('C5 four rows are drawn', rowsOf(host).length, 4);

  const rowNamed = (h, name) => rowsOf(h).find((r) => r.getAttribute('data-row-id') === name);
  const inspectedRow = rowNamed(host, 'inspected');
  ok('C6 a row carries its predicate as its key', Boolean(inspectedRow));
  inspectedRow.click({});
  eq('C7 clicking put the whole set in the write marking', markings.count('marking:2'), 39);
  ok('C8 every marked node is one the predicate reaches',
    markings.entries('marking:2').every((e) => by.inspected.nodeIds.includes(e[0])));
  ok('C9 they are marked as cases, not controls',
    markings.entries('marking:2').every((e) => e[1] === SIGN.CASE));
  rowNamed(host, 'bonded_from').click({});
  eq('C10 a second row replaces the first', markings.count('marking:2'), 29);
  eq('C11 the read marking was not written', markings.count('marking:1'), 1);

  console.log(`${LF}-- D. two on one screen, no interference --`);
  const hostA = doc.createElement('div');
  const hostB = doc.createElement('div');
  markings.clear('marking:2');
  markings.set('marking:2', SEED, SIGN.CASE);
  const a = new ReachPanel(hostA, {
    doc, markings, reads: 'marking:1', writes: 'marking:3',
    start: { marking: 'marking:1', groupby: 'wafer' }, collect: 'reach',
    walk: () => Promise.resolve(model),
  });
  // 🔴 EACH GETS ITS OWN ANSWER OBJECT. Two panels asking the SAME question share one
  //    in-flight promise by design, so object identity would prove nothing about
  //    module-level state. Handing them different answers makes D1 mean 「each instance
  //    stored the one IT received」 -- which is exactly what a module-level field breaks.
  const modelB = reachModel({ ok: true, status: 200, body: BODY });
  const b = new ReachPanel(hostB, {
    doc, markings, reads: 'marking:2', writes: 'marking:4',
    start: { marking: 'marking:2', groupby: 'wafer' }, collect: 'reach',
    walk: () => Promise.resolve(modelB),
  });
  a.mount(); b.mount();
  await settle();
  ok('D1 each instance stored the answer IT received',
    a.model === model && b.model === modelB && a.model !== b.model);
  ok('D2 each drew into its own host', rowsOf(hostA).length === 4 && rowsOf(hostB).length === 4);
  rowNamed(hostA, 'inspected').click({});
  eq('D3 A wrote its own name', markings.count('marking:3'), 39);
  eq('D4 and B name stayed empty', markings.count('marking:4'), 0);
  eq('D5 A opened a row', a.opened, 'inspected');
  ok('D6 B did not open anything', b.opened === null, String(b.opened));
  rowNamed(hostB, 'binding').click({});
  eq('D7 B wrote its own name', markings.count('marking:4'), 4);
  eq('D8 and A keeps what it wrote', markings.count('marking:3'), 39);
  ok('D9 the two opened different rows', a.opened === 'inspected' && b.opened === 'binding');

  console.log(`${LF}-- E. the absences are different sentences --`);
  const empty = new MarkingStore();
  const hostE = doc.createElement('div');
  const pe = new ReachPanel(hostE, {
    doc, markings: empty, reads: 'marking:1', writes: 'marking:2',
    start: { marking: 'marking:1', groupby: 'wafer' }, collect: 'reach',
    walk: () => Promise.resolve(model),
  });
  pe.mount();
  await settle();
  const notChosen = textOf(hostE);
  ok('E1 an empty marking says 「not chosen yet」', notChosen.includes('아직 안 골랐습니다'), notChosen.slice(0, 60));
  ok('E2 and it did not ask a question with no subject', pe.model === null);

  const hostR = doc.createElement('div');
  const refused = reachModel({ ok: false, status: 503, body: null });
  const pr = new ReachPanel(hostR, {
    doc, markings, reads: 'marking:1', writes: 'marking:2',
    start: { marking: 'marking:1', groupby: 'wafer' }, collect: 'reach',
    walk: () => Promise.resolve(refused),
  });
  pr.mount();
  await settle();
  const refusedText = textOf(hostR);
  ok('E3 a refusal says the server refused', refusedText.includes('거절'), refusedText.slice(0, 60));
  ok('E4 a refusal is not the not-chosen sentence', !refusedText.includes('아직 안 골랐습니다'));

  const hostN = doc.createElement('div');
  const noEdges = reachModel({ ok: true, status: 200, body: { ...BODY, edges: [] } });
  const pn = new ReachPanel(hostN, {
    doc, markings, reads: 'marking:1', writes: 'marking:2',
    start: { marking: 'marking:1', groupby: 'wafer' }, collect: 'reach',
    walk: () => Promise.resolve(noEdges),
  });
  pn.mount();
  await settle();
  const noneText = textOf(hostN);
  ok('E5 no outgoing edges is its own sentence', noneText.includes('나가는 엣지가 없습니다'), noneText.slice(0, 60));
  ok('E6 and that is not the not-chosen sentence', !noneText.includes('아직 안 골랐습니다'));

  return { ran, failed: failedList.slice() };
}

const MUTANTS = [
  { name: 'count-edges-instead-of-places', target: 'api.js', wakes: 'B1',
    from: '    count: g.ids.size,',
    to: '    count: g.kinds.size,' },
  { name: 'the-seed-counts-as-its-own-destination', target: 'api.js', wakes: 'B3',
    from: '    if (!otherId || otherId === seedId) continue;',
    to: '    if (!otherId) continue;' },
  { name: 'depth-is-reported-as-a-cut', target: 'api.js', wakes: 'F2',
    from: "    cut: [t.nodes ? 'nodes' : null, t.edges ? 'edges' : null, t.claims ? 'claims' : null].filter(Boolean),",
    to: "    cut: [t.depth ? 'depth' : null].filter(Boolean)," },
  { name: 'rows-arrive-in-response-order', target: 'api.js', wakes: 'A11',
    from: '  rows.sort((a, b) => b.count - a.count || String(a.predicate).localeCompare(String(b.predicate)));',
    to: '  rows.sort((a, b) => a.count - b.count);' },
  { name: 'clicking-accumulates-instead-of-replacing', target: 'reach_panel.js', wakes: 'C10',
    from: "    row.nodeIds.forEach((id, i) => this.mark(id, SIGN.CASE, i === 0 ? 'replace' : 'add'));",
    to: "    row.nodeIds.forEach((id) => this.mark(id, SIGN.CASE, 'add'));" },
  { name: 'the-part-carries-its-own-hops', target: 'reach_panel.js', wakes: 'C4',
    from: '    const model = await this.walkFn({ start, collect: this.collect });',
    to: '    const model = await this.walkFn({ start, collect: this.collect, hops: 1 });' },
  { name: 'an-empty-marking-asks-anyway', target: 'reach_panel.js', wakes: 'E1/E2',
    from: '    if (!this.walkFn || !start) {',
    to: '    if (!this.walkFn) {' },
  { name: 'every-absence-shares-one-sentence', target: 'reach_panel.js', wakes: 'E3',
    from: "    if (this.loadState === 'refused') return (this.model && this.model.message) || '걸어 보지 못했습니다';",
    to: "    if (this.loadState === 'refused') return '아직 안 골랐습니다';" },
  // 🔴 `writes: null` ON THE TABLE IS NOT SCORED, AND THAT IS SAID OUT LOUD RATHER THAN
  //    FAKED. A mutant that hands the table this part's write name ESCAPES: the table would
  //    mark the predicate STRING, and then `_expand` immediately marks the first real node
  //    with `replace`, which clears it. So the wrong write is unobservable through this
  //    part's own behaviour. The line stays because it states the truth -- a table of
  //    predicates writes no nodes -- but a mutant that never wakes an assertion is
  //    decoration, and this file does not carry decoration.
];

const main = async () => {
  console.log('== baseline ==');
  const base = await suite(await loadModules());
  console.log(`${LF}${base.ran - base.failed.length} passed, ${base.failed.length} failed.`);
  if (base.failed.length) {
    console.log(`ASSERTIONS ${base.ran} ${base.failed.length}`);
    process.exit(1);
  }

  console.log(`${LF}== defect mutants (each must be CAUGHT) ==`);
  let escaped = 0;
  for (const m of MUTANTS) {
    let mods;
    try {
      mods = await loadModules({
        [m.target]: (src) => (src.includes(m.from) ? src.split(m.from).join(m.to) : src),
      });
    } catch (err) {
      console.error(`HARNESS FAILURE: ${err.message} (${m.name})`);
      console.error('(This is not a passing result. Nothing was compared.)');
      process.exit(2);
    }
    const real = console.log;
    console.log = () => {};
    ran = 0; failedList = [];
    let result;
    try { result = await suite(mods); } catch (err) { result = { failed: ['threw: ' + err.message] }; }
    console.log = real;
    const caught = result.failed.length > 0;
    if (caught) real(`  caught  ${m.name}  (${m.wakes}) -- ${String(result.failed[0]).slice(0, 66)}`);
    else { real(`  ESCAPED ${m.name}  (${m.wakes})`); escaped += 1; }
  }

  console.log(`${LF}ASSERTIONS ${base.ran} ${base.failed.length}`);
  process.exit(escaped ? 1 : 0);
};

main();
