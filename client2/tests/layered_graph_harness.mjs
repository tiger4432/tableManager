// LAYERED GRAPH — one SVG drawer the chain graph and the subgraph viewer both declare into (lead 65754c39a).
//
// Four questions, in the order's words:
//   S  「두 화면의 오늘 그림은 그대로」 - both screens, seated as graph_seats seats them, draw the trees pinned by
//      capture_graph_snapshots.mjs before the template existed, byte for byte.
//   I  「같은 화면에 두 선언 — 간섭 0」 - the chain and the viewer on one document; a press in one changes
//      nothing in the other.
//   U  the template itself: a declaration in, the tree it promises out (shapes, marks, texts, slots, presses).
//      Its mutants are scored here - the viewer imports it from a parent folder, which the probe cannot
//      redirect, so a template mutant reaches the screens only through this.
//   P  「팔레트 토큰 하나」 - nine category tokens in tokens.css, and the viewer's type colours read them.
// The template file is also read as TEXT for one claim whose subject is its text: no domain word, no import.
//
// Run: node client2/tests/layered_graph_harness.mjs
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { makeDoc, byClass, walk as all, flush } from './lib/board_dom.mjs';
import { snapshot, seatChain, seatSubgraph, CHAIN_PAYLOAD } from './lib/graph_seats.mjs';
import { ChainGraphPanel } from '../src/chain_graph.js';
import { SubgraphView } from '../src/walk/subgraph_view.js';
import { WALK_CSS } from '../src/walk/styles.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const TEMPLATE = path.join(HERE, '..', 'src', 'layered_graph.js');
const PINNED = JSON.parse(readFileSync(path.join(HERE, 'fixtures', 'graph_snapshots.json'), 'utf8'));
const TOKENS = readFileSync(path.join(HERE, '..', 'src', 'tokens.css'), 'utf8');
const TEMPLATE_TEXT = readFileSync(TEMPLATE, 'utf8');

const has = (n, cls) => String(n.className || '').split(/\s+/).includes(cls);

/** A declaration that uses every slot the template offers: two shapes, a mark, a text, a missing nothing. */
const DECL = (presses) => ({
  geometry: { margin: 10, gapX: 100, gapY: 20, r: 5, labelDx: 8 },
  boxClass: 'box-x', svgClass: 'svg-x', width: 300, height: 90,
  edges: [{ x1: 10, y1: 10, x2: 110, y2: 30, attrs: { class: 'e-x', 'data-k': 'k1' } }],
  nodes: [
    { id: 'a', x: 10, y: 10, label: 'A', attrs: { class: 'n-x', 'data-node': 'a' },
      marks: [{ dx: -4, dy: -9, text: 'm', attrs: { class: 'mk-x' } }], onPress: () => presses.push('a') },
    { id: 'b', x: 110, y: 30, label: 'B', shape: 'rect', attrs: { class: 'n-x', 'data-node': 'b' } },
  ],
  texts: [{ x: 118, y: 50, text: '+3 t', attrs: { class: 't-x', 'data-t': 't1' }, onPress: () => presses.push('t') }],
});

async function suite(m) {
  const names = [];
  const fails = [];
  const say = (name, cond, detail) => {
    names.push(name);
    if (cond) { console.log(`  PASS ${name}`); return; }
    fails.push(name);
    console.log(`  FAIL ${name}${detail ? ' -- ' + detail : ''}`);
  };

  console.log('\n[U] a declaration in, the tree it promises out');
  {
    const doc = makeDoc('light');
    const presses = [];
    const drawn = m.drawLayeredGraph(doc, DECL(presses));
    const svg = drawn.svg;
    say('U1 the box carries the declared class and holds the svg, which declares its own size',
      drawn.box.className === 'box-x' && drawn.box.children[0] === svg
        && svg.attrs.class === 'svg-x' && svg.attrs.width === '300' && svg.attrs.height === '90'
        && svg.attrs.viewBox === '0 0 300 90' && svg.attrs.preserveAspectRatio === 'xMinYMin meet',
      JSON.stringify(svg.attrs));
    const kinds = svg.children.map((c) => c.tagName);
    say('U2 lines first, then the nodes, then the texts', JSON.stringify(kinds) === '["LINE","G","G","G"]'
      && svg.children[0]?.attrs['data-k'] === 'k1' && svg.children[0]?.attrs.x2 === '110', JSON.stringify(kinds));
    // A mutant may leave a slot empty: then the check fails, it does not throw.
    const [ga, gb] = [svg.children[1] || { children: [], attrs: {} }, svg.children[2] || { children: [], attrs: {} }];
    const circle = ga.children[0] || { attrs: {} };
    const rect = gb.children[0] || { attrs: {} };
    say('U3 a node is its shape at its slot, its label beside it, its marks where declared',
      circle.tagName === 'CIRCLE' && circle.attrs.cx === '10' && circle.attrs.r === '5'
        && rect.tagName === 'RECT' && rect.attrs.x === '105' && rect.attrs.width === '10'
        && ga.children[1]?.textContent === 'A' && ga.children[1]?.attrs.x === '18' && ga.children[1]?.attrs.y === '14'
        && ga.children[2]?.textContent === 'm' && ga.children[2]?.attrs.class === 'mk-x' && ga.children[2]?.attrs.x === '6',
      JSON.stringify([circle.attrs, rect.attrs, ga.children.map((c) => c.attrs)]));
    const t = svg.children[3] || { children: [], attrs: {} };
    say('U4 a text is a group with its words just under its slot', t.attrs.class === 't-x' && t.attrs['data-t'] === 't1'
      && t.children[0]?.textContent === '+3 t' && t.children[0]?.attrs.y === '54', JSON.stringify(t.attrs));
    for (const g of [ga, t, gb]) if (g.dispatch) g.dispatch('click', {});
    say('U5 a press reaches what the node or text declared, and only those', JSON.stringify(presses) === '["a","t"]'
      && drawn.groups.get('a') === ga && drawn.groups.get('b') === gb, JSON.stringify(presses));
    const slot = m.slotXY({ margin: 10, gapX: 100, gapY: 20 }, 2, 3);
    say('U6 a slot: the layer is the column, the row is the row', slot.x === 210 && slot.y === 70, JSON.stringify(slot));
  }
  return { ran: names.length, names, failures: fails };
}

async function screens() {
  const names = [];
  const fails = [];
  const say = (name, cond, detail) => {
    names.push(name);
    if (cond) { console.log(`  PASS ${name}`); return; }
    fails.push(name);
    console.log(`  FAIL ${name}${detail ? ' -- ' + detail : ''}`);
  };
  console.log('\n[S] both screens draw today what they drew before the template');
  say('S1 the chain graph', JSON.stringify(snapshot(seatChain(ChainGraphPanel))) === JSON.stringify(PINNED.chain));
  for (const [tag, which] of [['S2', 'die'], ['S3', 'continue'], ['S4', 'bundles']]) {
    say(`${tag} the subgraph viewer, ${which}`,
      JSON.stringify(snapshot(await seatSubgraph(SubgraphView, which))) === JSON.stringify(PINNED[`subgraph_${which}`]));
  }

  console.log('\n[I] two declarations on one page');
  {
    const doc = makeDoc('light');
    const chainHost = doc.createElement('div');
    const viewHost = doc.createElement('div');
    doc.body.appendChild(chainHost);
    doc.body.appendChild(viewHost);
    const chain = new ChainGraphPanel(chainHost, { doc });
    chain.render(CHAIN_PAYLOAD);
    const seated = await seatSubgraph(SubgraphView, 'die');
    // The viewer's own seat builds its own doc; move its host here, as a page would place a part.
    doc.body.appendChild(seated);
    const before = JSON.stringify(snapshot(seated));
    const node = byClass(chainHost, 'cg-node').find((g) => g.attrs['data-node'] === 'dt_log');
    if (node) node.dispatch('click', {});
    const after = JSON.stringify(snapshot(seated));
    const viewNode = byClass(seated, 'sg-node')[1];
    if (viewNode) viewNode.dispatch('click', {});
    await flush();
    const wakes = byClass(chainHost, 'chain-graph-wake').length;
    say('I1 a press in the chain picks its table and leaves the viewer as it was; a press in the viewer leaves the chain\'s list',
      Boolean(node && viewNode) && before === after && wakes === 2 && byClass(seated, 'sg-fact').length > 0
        && all(chainHost).every((n) => !has(n, 'sg-fact')),
      JSON.stringify({ same: before === after, wakes }));
  }

  console.log('\n[T] the template is the shape, not a screen');
  {
    const words = ['chain', 'wake', 'mapper', 'ledger', 'walk', 'marking', 'bundle', 'wafer', 'die', 'cg-', 'sg-'];
    const code = TEMPLATE_TEXT.split('\n').filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l)).join('\n');
    const found = words.filter((w) => new RegExp(`\\b${w}`, 'i').test(code));
    const imports = (TEMPLATE_TEXT.match(/^import /gm) || []).length;
    const lets = (code.match(/^(let|var) /gm) || []).length;
    say('T1 its code names no screen, imports nothing and keeps no module state',
      found.length === 0 && imports === 0 && lets === 0 && /export function drawLayeredGraph/.test(code),
      JSON.stringify({ found, imports, lets }));
  }

  console.log('\n[P] one category palette');
  {
    const tokens = [1, 2, 3, 4, 5, 6, 7, 8, 9].map((k) => (TOKENS.match(new RegExp(`--cat-${k}:`, 'g')) || []).length);
    const canary = (TOKENS.match(/--accent:/g) || []).length;
    const reads = [0, 1, 2, 3, 4, 5, 6, 7, 8].every((k) => WALK_CSS.includes(`.sg-type-${k} { --sg-c: var(--cat-${k + 1}); }`));
    say('P1 nine category tokens, each once, and the viewer\'s nine type colours read them in order',
      canary > 0 && tokens.every((n) => n === 1) && reads, JSON.stringify({ tokens, canary, reads }));
  }
  return { ran: names.length, names, failures: fails };
}

let pass = 0;
const failures = [];
{
  const real = await import('../src/layered_graph.js');
  const base = await suite(real);
  const scr = await screens();
  pass += base.ran - base.failures.length + scr.ran - scr.failures.length;
  failures.push(...base.failures, ...scr.failures);

  const { loadWithProbe } = await import('./lib/probe.mjs');
  const { scoreMutants } = await import('./lib/mutation_scorer.mjs');
  const swap = (text, from, to) => {
    if (!text.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`);
    return text.split(from).join(to);
  };
  const M = (id, what, catches, from, to) => ({ id, what, catches, from, to });
  const MUTANTS = [
    M('L1', 'every node is drawn as a circle', 'U3',
      "    group.appendChild(node.shape === 'rect'\n", '    group.appendChild(false\n'),
    M('L2', 'the svg loses its own size', 'U1',
      '    width: decl.width, height: decl.height, preserveAspectRatio', '    preserveAspectRatio'),
    M('L3', 'a node\'s marks are dropped', 'U3',
      '    for (const mark of node.marks || []) {\n', '    for (const mark of []) {\n'),
    M('L4', 'the texts are dropped', 'U2',
      '  for (const item of decl.texts || []) {\n', '  for (const item of []) {\n'),
    M('L5', 'a slot\'s row is spaced by the column gap', 'U6',
      'y: geometry.margin + row * geometry.gapY', 'y: geometry.margin + row * geometry.gapX'),
    M('L6', 'the box is not given its class', 'U1',
      '  box.className = decl.boxClass;\n', ''),
    M('L7', 'a node\'s press is not wired', 'U5',
      "    if (node.onPress && group.addEventListener) group.addEventListener('click', node.onPress);\n", ''),
    M('L8', 'the lines are not drawn', 'U2',
      '  // Lines first, so the shapes sit on top of them.\n  for (const edge of decl.edges || []) {',
      '  for (const edge of []) {'),
  ];
  const scored = await scoreMutants(MUTANTS, async (mu) => {
    const loaded = (await loadWithProbe(TEMPLATE, { mutate: (t) => swap(t, mu.from, mu.to) })).module;
    const quiet = console.log;
    console.log = () => {};
    try { return await suite(loaded); } finally { console.log = quiet; }
  }, { baselineRan: base.ran, baselineNames: base.names,
       title: '\n  [mutants] - each must be caught by the check it names.' });
  pass += MUTANTS.length - scored.wrong;
  for (let i = 0; i < scored.wrong; i += 1) failures.push(`mutant verdict ${i + 1}`);
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
