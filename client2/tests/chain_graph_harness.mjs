/**
 * 체인 그래프 — 네 선언이 «한 그림»이 되고, 거미줄이 스스로 보인다.
 *
 *   node client2/tests/chain_graph_harness.mjs
 *
 * WHY (C-75, owner 2026-09-11 「chain 이 너무 거미줄 같아」). One flow is written across four
 * declarations, so 「what does this table wake」 needed four files laid on top of each other.
 *
 * ⚠️ THE FIXTURE'S SHAPE COMES FROM THE ORDER, NOT FROM SERVER SOURCE. `/chain/graph` (S-178)
 *    has not landed — measured, not assumed: the only two `chain/graph` strings under
 *    `server/` are prose inside comments. So every key here is one the order names, and when
 *    the route lands this fixture is the first thing to re-measure against it. The panel is
 *    NOT wired into the overview yet for the same reason: a contract adopted before its
 *    material blanks a screen while the harness stays green.
 */
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(HERE, '..', 'src', 'chain_graph.js');
const LF = String.fromCharCode(10);

function makeDoc() {
  const make = (tag) => ({
    tagName: tag, children: [], attrs: {}, listeners: {}, className: '', _text: '',
    parentNode: null,
    appendChild(c) { c.parentNode = this; this.children.push(c); return c; },
    append(...cs) { cs.forEach((c) => this.appendChild(c)); },
    replaceChild(next, old) {
      const at = this.children.indexOf(old);
      if (at >= 0) { next.parentNode = this; this.children[at] = next; }
      return old;
    },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return this.attrs[k] === undefined ? null : this.attrs[k]; },
    addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); },
    fire(t) { (this.listeners[t] || []).forEach((fn) => fn({})); },
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); },
    set textContent(v) { this._text = String(v); this.children = []; },
  });
  // 🔴 SVG IS A DIFFERENT NAMESPACE and the panel uses `createElementNS`. A stub that only
  //    answered `createElement` would make every shape undefined -- and the harness would be
  //    measuring its own stub rather than the panel.
  return { createElement: make, createElementNS: (_ns, tag) => make(tag) };
}
const walkAll = (el, out = []) => { out.push(el); el.children.forEach((c) => walkAll(c, out)); return out; };
const byTag = (root, tag) => walkAll(root).filter((e) => e.tagName === tag);
// 🔴 AN EXACT CLASS TOKEN, and it reads the ATTRIBUTE too. Two traps, both hit on the first
//    run: `includes` made `chain-graph-wakes` match `chain-graph-wakes-head` (one box read as
//    two, two wake rows read as four), and SVG elements carry `class` as an ATTRIBUTE -- a
//    `className` string is an HTML thing -- so the opt-in mark counted zero while it was
//    plainly there. Both failures looked like the subject and were the measuring stick.
const classesOf = (e) => String((e.className || '') + ' '
  + ((e.getAttribute && e.getAttribute('class')) || '')).trim().split(/\s+/);
const byClass = (root, cls) => walkAll(root).filter((e) => classesOf(e).includes(cls));

// The four declarations, one flow: two source tables wake a derived table (mapper), the
// derived one feeds an enrichment and a virtual join, and the ledger reads the result.
const GRAPH = {
  nodes: [
    { id: 'raw_log', label: 'raw_log', wakes: ['dt_log'] },
    { id: 'eqp_log', label: 'eqp_log', wakes: ['dt_log'] },
    { id: 'dt_log', label: 'dt_log', wakes: ['dt_job_attribution', 'dt_inventory'] },
    { id: 'dt_job_attribution', label: 'dt_job_attribution', opt_in: true, wakes: [] },
    { id: 'dt_inventory', label: 'dt_inventory', enabled: false, wakes: [] },
    { id: 'ledger', label: 'ledger', wakes: [] },
  ],
  edges: [
    { from: 'raw_log', to: 'dt_log', kind: 'mapper' },
    { from: 'eqp_log', to: 'dt_log', kind: 'mapper' },
    { from: 'dt_log', to: 'dt_job_attribution', kind: 'enrich' },
    { from: 'dt_log', to: 'dt_inventory', kind: 'vjoin', enabled: false },
    { from: 'dt_job_attribution', to: 'ledger', kind: 'ledger' },
  ],
  cycles: [],
};

let ran = 0;
const NAMES = [];
let failures = [];
const ok = (name, cond, detail) => {
  ran += 1; NAMES.push(name);
  if (cond) { console.log(`  ok   ${name}`); return; }
  failures.push(detail ? `${name} -- ${detail}` : name);
  console.log(`  FAIL ${name}${detail ? ' -- ' + detail : ''}`);
};
const eq = (name, got, want) => ok(name, String(got) === String(want), `got ${got}, want ${want}`);

function suite(mod) {
  const { ChainGraphPanel, chainGraphView, edgeClass, layersOf } = mod;
  const doc = makeDoc();
  const mount = doc.createElement('div');
  const panel = new ChainGraphPanel(mount, { doc });
  panel.render(GRAPH);

  console.log(`${LF}-- the four declarations, drawn once --`);
  eq('G1 one circle per node', byTag(mount, 'circle').length, GRAPH.nodes.length);
  eq('G2 one line per edge', byTag(mount, 'line').length, GRAPH.edges.length);
  eq('G3 each line carries its kind', byTag(mount, 'line')
    .map((l) => l.getAttribute('data-kind')).join(','),
    GRAPH.edges.map((e) => e.kind).join(','));

  console.log(`${LF}-- the kinds are four DIFFERENT classes, and a fifth is drawn too --`);
  eq('K1 mapper', edgeClass('mapper'), 'cg-edge cg-edge--mapper');
  eq('K2 enrich', edgeClass('enrich'), 'cg-edge cg-edge--enrich');
  eq('K3 vjoin', edgeClass('vjoin'), 'cg-edge cg-edge--vjoin');
  eq('K4 ledger', edgeClass('ledger'), 'cg-edge cg-edge--ledger');
  // 🔴 A FIFTH DECLARATION MUST NOT VANISH. Dropping an unknown kind hides the very thing
  //    this picture exists to show, and it does it without an error.
  eq('K5 a kind nobody listed still gets a class', edgeClass('notify'),
    'cg-edge cg-edge--unknown');
  eq('K6 ...and is still drawn', chainGraphView(
    { nodes: [{ id: 'a' }, { id: 'b' }], edges: [{ from: 'a', to: 'b', kind: 'notify' }] })
    .edges.length, 1);

  console.log(`${LF}-- layers run left to right, source to ledger --`);
  const layer = layersOf(GRAPH.nodes, GRAPH.edges);
  eq('L1 a table nothing wakes is the first layer', layer.get('raw_log'), 0);
  eq('L2 the table they wake is the next', layer.get('dt_log'), 1);
  eq('L3 ...and the ledger is last', layer.get('ledger'), 3);
  const view = chainGraphView(GRAPH);
  ok('L4 x grows with the layer',
    view.nodes.find((n) => n.id === 'ledger').x > view.nodes.find((n) => n.id === 'raw_log').x);
  ok('L5 two tables in one layer do not sit on top of each other',
    view.nodes.find((n) => n.id === 'raw_log').y !== view.nodes.find((n) => n.id === 'eqp_log').y);

  console.log(`${LF}-- disabled is dim, opt-in is one mark, and absence is neither --`);
  eq('D1 enabled false is dim', view.nodes.find((n) => n.id === 'dt_inventory').dim, 'true');
  // 「끈 적이 없다」 is not 「꺼져 있다」: a node with no `enabled` key must draw normally.
  eq('D2 a node that never said is NOT dim', view.nodes.find((n) => n.id === 'raw_log').dim,
    'false');
  eq('D3 a disabled edge is dim too',
    view.edges.find((e) => e.to === 'dt_inventory').className.includes('is-dim'), 'true');
  eq('D4 opt-in draws one mark', byClass(mount, 'cg-optin').length, 1);

  console.log(`${LF}-- a cycle is red, and ONLY the tables in it --`);
  {
    const looped = {
      nodes: [{ id: 'a' }, { id: 'b' }, { id: 'c' }],
      edges: [{ from: 'a', to: 'b', kind: 'mapper' }, { from: 'b', to: 'a', kind: 'enrich' },
        { from: 'a', to: 'c', kind: 'ledger' }],
      cycles: [['a', 'b']],
    };
    const cycleView = chainGraphView(looped);
    eq('C1 a table in the cycle is marked',
      cycleView.nodes.find((n) => n.id === 'a').inCycle, 'true');
    // 🔴 NOT EVERYTHING RED. Painting the whole graph on one cycle hides WHICH table is the
    //    problem -- the same silence in a brighter colour.
    eq('C2 a table outside it is not',
      cycleView.nodes.find((n) => n.id === 'c').inCycle, 'false');
    eq('C3 the edge between two cycle members is marked',
      cycleView.edges[0].className.includes('is-cycle'), 'true');
    eq('C4 an edge leaving the cycle is not',
      cycleView.edges[2].className.includes('is-cycle'), 'false');
    // 🔴 AND IT TERMINATES. A cycle must not take the whole picture down -- the installation
    //    with a cobweb is exactly the one that needs to see it.
    eq('C5 a cycle still produces a drawing', cycleView.state, 'ready');
  }

  console.log(`${LF}-- clicking a table says what it wakes --`);
  const group = walkAll(mount).find((e) => e.getAttribute && e.getAttribute('data-node') === 'dt_log');
  group.fire('click');
  const wakeText = byClass(mount, 'chain-graph-wakes')[0].textContent;
  ok('W1 the clicked table names itself', wakeText.includes('dt_log'), wakeText);
  ok('W2 ...and lists what it wakes', wakeText.includes('dt_job_attribution')
    && wakeText.includes('dt_inventory'), wakeText);
  eq('W3 one row per wake', byClass(mount, 'chain-graph-wake').length, 2);
  // 다른 원을 누르면 «갈아 끼웁니다» — 쌓이면 어느 표의 목록인지 못 읽습니다.
  walkAll(mount).find((e) => e.getAttribute && e.getAttribute('data-node') === 'ledger').fire('click');
  eq('W4 clicking another table replaces the list rather than stacking it',
    byClass(mount, 'chain-graph-wakes').length, 1);

  console.log(`${LF}-- the REAL route's shape, measured 2026-09-11 on server/chain_graph.py --`);
  {
    // 🔴 THE ORDER SUMMARISED A SHAPE THE ROUTE DOES NOT SERVE, and two of this panel's
    //    features were silent no-ops against the real one. `cycles` carries the validator's
    //    SENTENCES, not id arrays, and nodes carry `{id, kind, declared, wakes}` -- no
    //    `enabled`, no `opt_in`. Both failures are invisible: nothing throws, nothing turns red.
    const real = {
      generated_at: 1, counts: { edges: 1, nodes: 3 },
      nodes: [
        { id: 'dt_log', kind: 'table', declared: true, wakes: ['dt_inventory'] },
        { id: 'ghost_table', kind: 'table', declared: false, wakes: [] },
        { id: '(ledger)', kind: 'ledger' },
      ],
      edges: [{ kind: 'ledger', from: 'dt_log', to: '(ledger)', enabled: true }],
      cycles: ['chain rule cascade would loop: dt_log -> dt_x -> dt_log'],
    };
    const realView = chainGraphView(real);
    eq('S1 the real answer still draws', realView.state, 'ready');
    // 🔴 A CYCLE MUST STILL BE SAID even when the table cannot be pointed at.
    eq('S2 a cycle SENTENCE is carried through as a value', realView.cycleNotes.length, 1);
    eq('S3 ...and nobody is painted red, because the answer never named a table',
      realView.nodes.filter((n) => n.inCycle).length, 0);
    eq('S4 a table the catalogue does not declare is marked',
      realView.nodes.find((n) => n.id === 'ghost_table').undeclared, 'true');
    eq('S5 ...and a declared one is not',
      realView.nodes.find((n) => n.id === 'dt_log').undeclared, 'false');
    eq('S6 the ledger node keeps its kind', realView.nodes.find((n) => n.id === '(ledger)').kind,
      'ledger');
    const realDoc = makeDoc();
    const realMount = realDoc.createElement('div');
    new ChainGraphPanel(realMount, { doc: realDoc }).render(real);
    eq('S7 the cycle sentence reaches the screen', byClass(realMount, 'chain-graph-cycle').length, 1);
    // A box that is not there must be SCORED, not thrown on: under M7 an index straight into
    // the list kills the run and the remaining assertions go unmeasured (INERT, not caught).
    const cycleText = (byClass(realMount, 'chain-graph-cycle')[0] || {}).textContent || '(none)';
    ok('S8 ...in the server own words', cycleText.includes('would loop'), cycleText);
  }

  console.log(`${LF}-- a read that failed is not an empty graph --`);
  eq('U1 no payload reads as unread', chainGraphView(null).state, 'unread');
  eq('U2 an answer with an empty node list is READY',
    chainGraphView({ nodes: [], edges: [] }).state, 'ready');
}

const first = await loadWithProbe(SRC, {});
suite(first.module);
console.log(`${LF}${failures.length === 0 ? 'PASS' : 'FAIL'} baseline: ${ran} assertions, `
  + `${failures.length} failure(s)`);
failures.forEach((f) => console.log(`   x ${f}`));
const base = { ran, names: NAMES.slice(), failed: failures.length };

const MUTANTS = [
  { id: 'M1', what: 'an unknown edge kind is dropped instead of drawn',
    catches: 'K6 ...and is still drawn',
    from: '    edges: edges.map((edge) => ({',
    to: '    edges: edges.filter((e) => EDGE_KINDS.includes(e.kind)).map((edge) => ({' },
  { id: 'M2', what: 'a node that never said `enabled` is drawn dim',
    catches: 'D2 a node that never said',
    from: '      dim: node.enabled === false,',
    to: '      dim: !node.enabled,' },
  { id: 'M3', what: 'one cycle paints every table red',
    catches: 'C2 a table outside it is not',
    from: '      inCycle: inCycle.has(node.id),',
    to: '      inCycle: inCycle.size > 0,' },
  { id: 'M4', what: 'the layer ignores who wakes whom',
    catches: 'L2 the table they wake is the next',
    from: '    const value = parents.length === 0 ? 0 : Math.max(...parents.map(depth)) + 1;',
    to: '    const value = 0;' },
  { id: 'M5', what: 'a failed read is folded into an empty graph',
    catches: 'U1 no payload reads as unread',
    from: '  if (!nodes) return { state: \'unread\', nodes: [], edges: [], cycles: [] };',
    to: '  if (!nodes) return { state: \'ready\', nodes: [], edges: [], cycles: [] };' },
  { id: 'M6', what: 'the wake list stacks instead of being replaced',
    catches: 'W4 clicking another table replaces',
    from: '      this.root.replaceChild(next, this.wakesBox);',
    to: '      this.root.appendChild(next);' },
  { id: 'M7', what: 'a cycle sentence is dropped because it is not an array',
    catches: 'S2 a cycle SENTENCE is carried through',
    from: '    else if (cycle) cycleNotes.push(String(cycle));',
    to: '    else if (false) cycleNotes.push(String(cycle));' },
  { id: 'M8', what: 'a sentence is read as if it named tables',
    catches: 'S3 ...and nobody is painted red',
    from: '    else if (cycle) cycleNotes.push(String(cycle));',
    to: '    else if (cycle) { cycleNotes.push(String(cycle));'
      + ' for (const id of String(cycle).split(/[^a-z_]+/)) inCycle.add(id); }' },
  { id: 'M9', what: 'an undeclared table looks declared',
    catches: 'S4 a table the catalogue does not declare',
    from: '      undeclared: node.declared === false,',
    to: '      undeclared: false,' },
  { id: 'M7c', what: 'CONTROL: a comment line is removed', control: true,
    from: '/** 선언 넷이 내는 엣지 종류. 순서는 «범례»의 순서이고 판정이 아닙니다. */',
    to: '/** */' },
];

const runMutant = async (m) => {
  ran = 0; NAMES.length = 0; failures = [];
  const loaded = await loadWithProbe(SRC, {
    mutate: (text) => {
      if (!text.includes(m.from)) throw new Error(`mutation anchor is GONE: ${m.id}`);
      return text.split(m.from).join(m.to);
    },
  });
  suite(loaded.module);
  return { ran, names: NAMES.slice(), failures: failures.slice() };
};

const defects = await scoreMutants(MUTANTS.filter((m) => !m.control), runMutant,
  { baselineRan: base.ran, baselineNames: base.names,
    title: `${LF}== defect mutants (each must be CAUGHT by the check it names) ==` });
const controls = await scoreMutants(MUTANTS.filter((m) => m.control), runMutant,
  { mustCatch: false, baselineRan: base.ran, baselineNames: base.names,
    title: `${LF}== controls (each must wake NOTHING) ==` });

const scored = MUTANTS.length - defects.wrong - controls.wrong;
console.log(`${LF}  ${scored}/${MUTANTS.length} scored as intended.`);
const failed = base.failed + (MUTANTS.length - scored);
console.log(`ASSERTIONS ${base.ran + MUTANTS.length} ${failed}`);
process.exit(failed === 0 ? 0 : 1);
