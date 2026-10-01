// SUBGRAPH VIEW — a start's whole walk as a picture (lead c9bf53033), continued by marking (lead f6fc6ba66).
//
// The subject is imported (no slicing). Both sides of the counts gate come off the REAL wire:
// `createWalkBoxWalk` fed the server's own bodies (fixtures captured by capture_walk_start.mjs), then
// the table's `walkTableView` and this part's layout read the same answer. The markings live in the
// board's MarkingStore, outside the part, as the page holds them.
//
// Run: node client2/tests/subgraph_view_harness.mjs
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { makeDoc, byClass } from './lib/board_dom.mjs';
import { createWalkBoxWalk, entitySeedId } from '../src/rnd_board/api.js';
import { MarkingStore, SIGN } from '../src/rnd_board/marking_store.js';
import { walkTableView } from '../src/walk/table_view.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SUBJECT = path.join(HERE, '..', 'src', 'walk', 'subgraph_view.js');
const WIRE = path.join(HERE, '..', 'src', 'rnd_board', 'api.js');
const fx = (name) => JSON.parse(readFileSync(path.join(HERE, 'fixtures', name), 'utf8'));
const DECL = fx('walk_start_declaration.json');
const WAFER = fx('walk_start_wafer.json');
const DIE = fx('walk_start_die.json');
const STEP2 = fx('walk_start_die_step2.json');
const ENTITIES = DECL.entities;
// The oracle reads the declaration itself: the types whose classes hold 'static'.
const STATIC = new Set(ENTITIES.filter((e) => Array.isArray(e.class) && e.class.includes('static'))
  .map((e) => String(e.type).split('@')[0]));
const TYPE_BY_ID = new Map([...WAFER.nodes, ...DIE.nodes, ...STEP2.nodes].map((n) => [n.id, String(n.type).split('@')[0]]));
const typeOf = (group) => TYPE_BY_ID.get(group.attrs['data-node']) || '';
const startId = (body) => entitySeedId(body._start.type, body._start.keys);

/** The page's wire, answering each call with the next body in turn (the last one repeats).
 *  `makeWalk` is the wire's own factory - a mutant of api.js swaps it. */
const wireWith = (makeWalk) => (bodies, urls) => {
  let i = 0;
  return makeWalk({
    apiBase: '',
    fetchImpl: async (u) => {
      urls.push(String(u));
      const body = bodies[Math.min(i, bodies.length - 1)];
      i += 1;
      return { ok: true, status: 200, json: async () => body };
    },
  });
};
const has = (n, cls) => String(n.className || '').split(/\s+/).includes(cls);
const textOf = (host, cls) => byClass(host, cls).map((n) => n.textContent);
const paramsOf = (u) => new URLSearchParams(String(u).split('?')[1] || '');

async function suite(m, makeWalk = createWalkBoxWalk) {
  const wire = wireWith(makeWalk);
  const names = [];
  const fails = [];
  const say = (name, cond, detail) => {
    names.push(name);
    if (cond) { console.log(`  PASS ${name}`); return; }
    fails.push(name);
    console.log(`  FAIL ${name}${detail ? ' -- ' + detail : ''}`);
  };
  /** One part on its own page; its first marking holds the body's start, as the page writes it. */
  const seat = async (bodies, opts = {}) => {
    const doc = opts.doc || makeDoc('light');
    const host = doc.createElement('div');
    doc.body.appendChild(host);
    const urls = [];
    const markings = opts.markings || new MarkingStore();
    const chain = opts.chain || ['s0', 's1', 's2'];
    if (!opts.keepStart) markings.replace(chain[0], [[startId(bodies[0]), SIGN.CASE]]);
    const view = new m.SubgraphView(host, { doc, walk: wire(bodies, urls), entities: () => ENTITIES, markings, chain });
    await view.show();
    return { doc, host, view, urls, markings, chain };
  };
  const press = (host, id) => {
    const group = byClass(host, 'sg-node').find((g) => g.attrs['data-node'] === id);
    if (group) group.dispatch('click', {});
    return Boolean(group);
  };

  console.log('\n[1] what is drawn is what the walk answered - the same count the table shows');
  for (const [tag, body] of [['A1', WAFER], ['A3', DIE]]) {
    const r = await wire([body], [])(body._start);
    const table = walkTableView(r, ENTITIES, DECL.predicates || []);
    const rows = table.sections.reduce((n, s) => n + s.rows.length, 0) + (table.hidden || 0);
    const { host } = await seat([body]);
    const drawnNodes = byClass(host, 'sg-node').length;
    const drawnEdges = byClass(host, 'sg-edge').length;
    say(`${tag} ${body._start.type}: nodes drawn = the response = the table's rows`,
      drawnNodes > 0 && drawnNodes === r.nodes.length && rows === r.nodes.length,
      JSON.stringify({ drawnNodes, response: r.nodes.length, rows }));
    const edgeTag = tag === 'A1' ? 'A2' : 'A4';
    say(`${edgeTag} ${body._start.type}: edges drawn = the response, none with an end not drawn`,
      drawnEdges > 0 && drawnEdges === r.edges.length && byClass(host, 'sg-note').length === 0,
      JSON.stringify({ drawnEdges, response: r.edges.length, notes: textOf(host, 'sg-note') }));
  }

  console.log('\n[2] the layer is the step count from the start, the same picture for the same answer');
  {
    const r = await wire([DIE], [])(DIE._start);
    const layout = m.subgraphLayout([{ result: r }], ENTITIES);
    const xOf = new Map();
    let sameX = true;
    for (const n of layout.nodes) {
      if (xOf.has(n.depth) && xOf.get(n.depth) !== n.x) sameX = false;
      xOf.set(n.depth, n.x);
    }
    const depths = [...xOf.keys()].sort((a, b) => a - b);
    const rising = depths.every((d, i) => i === 0 || xOf.get(d) > xOf.get(depths[i - 1]));
    let inOrder = true;
    const lastY = new Map();
    for (const n of layout.nodes) {
      if (lastY.has(n.depth) && !(n.y > lastY.get(n.depth))) inOrder = false;
      lastY.set(n.depth, n.y);
    }
    say('B1 one column per depth, columns in step order, the server\'s order down each',
      depths.length > 2 && sameX && rising && inOrder, JSON.stringify({ depths, sameX, rising, inOrder }));
    const again = m.subgraphLayout([{ result: await wire([JSON.parse(JSON.stringify(DIE))], [])(DIE._start) }], ENTITIES);
    say('B2 the same answer lays out the same, twice', JSON.stringify(layout) === JSON.stringify(again));
    const w = await wire([WAFER], [])(WAFER._start);
    const lost = { ...w, nodes: w.nodes.map((n, i) => (i === 1 ? { ...n, depth: undefined } : n)) };
    const partial = m.subgraphLayout([{ result: lost }], ENTITIES);
    say('B3 a node without a depth is counted, not placed', partial.unplaced === 1
      && partial.nodes.length === w.nodes.length - 1, JSON.stringify({ unplaced: partial.unplaced, placed: partial.nodes.length }));
  }

  console.log('\n[3] a static type is another shape, by the declaration\'s list');
  {
    const { host } = await seat([DIE]);
    const groups = byClass(host, 'sg-node');
    const shape = (g) => (g.children.some((c) => c.tagName === 'RECT') ? 'rect'
      : (g.children.some((c) => c.tagName === 'CIRCLE') ? 'circle' : 'none'));
    const wrong = groups.filter((g) => (STATIC.has(typeOf(g)) ? 'rect' : 'circle') !== shape(g));
    const statics = groups.filter((g) => STATIC.has(typeOf(g))).length;
    say('C1 static nodes are squares, the rest circles', statics > 0 && wrong.length === 0,
      JSON.stringify({ statics, wrong: wrong.length }));
  }

  console.log('\n[4] the part asks its marking and nothing else');
  {
    const { urls } = await seat([DIE]);
    const params = paramsOf(urls[0] || '');
    const extra = [...params.keys()].filter((k) => k !== 'id' && k !== 'positive');
    say('D1 one request: the start marking (id and positive, its one node), no follow, collect or budget',
      urls.length === 1 && params.get('id') === startId(DIE)
        && JSON.stringify(params.getAll('positive')) === JSON.stringify([startId(DIE)]) && extra.length === 0,
      JSON.stringify({ urls: urls.length, extra }));
  }

  console.log('\n[5] a node pressed shows its facts');
  {
    const { host } = await seat([DIE]);
    const r = await wire([DIE], [])(DIE._start);
    // A node with edges: the start die itself carries none in this capture.
    const touchingOf = (id) => r.edges.filter((e) => e.source === id || e.target === id).length;
    const target = r.nodes.find((n) => touchingOf(n.id) > 1) || r.nodes[0];
    const pressed = press(host, target.id);
    const lines = textOf(host, 'sg-fact');
    const touching = touchingOf(target.id);
    const keyLines = Object.keys(target.keys || {}).length;
    say('E1 its keys and every edge touching it', pressed && touching > 1 && lines.length === keyLines + touching
      && textOf(host, 'sg-facts-head')[0] === `${target.label} · ${target.type}`,
      JSON.stringify({ lines: lines.length, keyLines, touching }));
    const picked = byClass(host, 'sg-node').filter((g) => has(g, 'is-selected')).map((g) => g.attrs['data-node']);
    say('E2 the pick is on that node alone', picked.length === 1 && picked[0] === target.id, JSON.stringify(picked));
  }

  console.log('\n[6] a cut walk says so, in one line');
  {
    const die = await seat([DIE]);
    const wafer = await seat([WAFER]);
    say('F1 the die walk: Truncated with its budget; the wafer walk: no line',
      JSON.stringify(textOf(die.host, 'sg-trunc')) === '["Truncated · nodes 400"]'
        && textOf(wafer.host, 'sg-trunc').length === 0,
      JSON.stringify([textOf(die.host, 'sg-trunc'), textOf(wafer.host, 'sg-trunc')]));
  }

  console.log('\n[7] two on one page with their own markings do not touch each other');
  {
    const doc = makeDoc('light');
    const markings = new MarkingStore();
    const a = await seat([WAFER], { doc, markings, chain: ['a0', 'a1'] });
    const b = await seat([DIE], { doc, markings, chain: ['b0', 'b1'] });
    const first = byClass(a.host, 'sg-node')[1];
    if (first) first.dispatch('click', {});
    say('G1 each draws its own walk, and a press in one leaves the other unpicked and unmarked',
      JSON.stringify(textOf(a.host, 'sg-counts')) === `["Nodes ${WAFER.nodes.length} · Edges ${WAFER.edges.length}"]`
        && JSON.stringify(textOf(b.host, 'sg-counts')) === `["Nodes ${DIE.nodes.length} · Edges ${DIE.edges.length}"]`
        && byClass(a.host, 'sg-fact').length > 0 && byClass(b.host, 'sg-fact').length === 0
        && markings.count('a1') === 1 && markings.count('b1') === 0
        && byClass(b.host, 'sg-node').every((g) => !has(g, 'is-selected') && !has(g, 'is-marked')),
      JSON.stringify([textOf(a.host, 'sg-counts'), textOf(b.host, 'sg-counts'), markings.count('a1'), markings.count('b1')]));
  }

  console.log('\n[8] the legend: one chip per type drawn, its count, static marked');
  {
    const { host } = await seat([DIE]);
    const chips = byClass(host, 'sg-chip');
    const counted = chips.reduce((n, c) => n + Number(String(c.textContent).split(' ').pop()), 0);
    const types = new Set(DIE.nodes.map((n) => String(n.type).split('@')[0]));
    const staticChips = chips.filter((c) => byClass(c, 'sg-swatch').some((s) => has(s, 'is-static')))
      .map((c) => c.attrs['data-type']);
    say('H1 chips = the types drawn, counts add up, static swatches on the static types',
      chips.length === types.size && counted === DIE.nodes.length
        && staticChips.length > 0 && staticChips.every((t) => STATIC.has(t)),
      JSON.stringify({ chips: chips.length, types: types.size, counted, staticChips }));
  }

  console.log('\n[9] continued by marking: a press marks, Continue walks the marking, one picture');
  {
    const s = await seat([DIE, STEP2]);
    const marked = STEP2._marked;
    const offBefore = s.view.continueButton && s.view.continueButton.disabled === true
      && s.view.continueButton.getAttribute('title') === 'Mark a node';
    press(s.host, marked);
    say('K1 a press writes that node, +, into the marking this step writes',
      JSON.stringify(s.markings.entries('s1')) === JSON.stringify([[marked, SIGN.CASE]]) && s.markings.count('s0') === 1,
      JSON.stringify(s.markings.entries('s1')));
    const onAfter = s.view.continueButton && s.view.continueButton.disabled === false;
    s.urls.length = 0;
    if (s.view.continueButton) s.view.continueButton.dispatch('click', {});
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
    const params = paramsOf(s.urls[0] || '');
    const extra = [...params.keys()].filter((k) => k !== 'id' && k !== 'positive');
    say('K2 Continue is off until something is marked, then asks that marking and nothing else',
      offBefore && onAfter && s.urls.length === 1 && params.get('id') === marked
        && JSON.stringify(params.getAll('positive')) === JSON.stringify([marked]) && extra.length === 0,
      JSON.stringify({ offBefore, onAfter, urls: s.urls.length, id: params.get('id') === marked, extra }));
    const one = new Set(DIE.nodes.map((n) => n.id));
    const union = new Set([...one, ...STEP2.nodes.map((n) => n.id)]);
    const edgeUnion = new Set([...DIE.edges.map((e) => e.id), ...STEP2.edges.map((e) => e.id)]);
    const groups = byClass(s.host, 'sg-node');
    const drawnIds = groups.map((g) => g.attrs['data-node']);
    say('K3 both steps on one picture: a node reached twice is drawn once, every edge once',
      union.size > one.size && groups.length === union.size && new Set(drawnIds).size === drawnIds.length
        && byClass(s.host, 'sg-edge').length === edgeUnion.size,
      JSON.stringify({ drawn: groups.length, union: union.size, edges: byClass(s.host, 'sg-edge').length, edgeUnion: edgeUnion.size }));
    // A shape's centre: a circle's cx, or a square's x plus half its side.
    const xOf = (g) => {
      if (!g) return NaN;   // a mutant may draw nothing here: the check fails, it does not throw
      const s = g.children[0];
      return s.attrs.cx !== undefined ? Number(s.attrs.cx) : Number(s.attrs.x) + Number(s.attrs.width) / 2;
    };
    const seed = groups.find((g) => g.attrs['data-node'] === marked);
    const stepOne = groups.filter((g) => one.has(g.attrs['data-node']));
    const colX = (depth) => xOf(stepOne.find((g) => g.attrs['data-depth'] === String(depth)));
    const gap = colX(1) - colX(0);
    const fresh = groups.filter((g) => !one.has(g.attrs['data-node']));
    // A fresh node's data-depth is its depth in the second walk, counted from the marked point.
    const off = fresh.filter((g) => Math.abs(xOf(g) - (xOf(seed) + Number(g.attrs['data-depth']) * gap)) > 0.01);
    say('K4 the second step carries on from the marked point, and its nodes say which step they came from',
      Boolean(seed) && Number(seed.attrs['data-depth']) >= 2 && fresh.length > 0 && gap > 0 && off.length === 0
        && fresh.every((g) => has(g, 'sg-step-2')) && stepOne.every((g) => has(g, 'sg-step-1')) && has(seed, 'is-seed'),
      JSON.stringify({ fresh: fresh.length, gap, off: off.length, seedDepth: seed && seed.attrs['data-depth'] }));
    say('K5 each cut step says so with its step',
      JSON.stringify(textOf(s.host, 'sg-trunc')) === '["Truncated · step 1 · nodes 400","Truncated · step 2 · nodes 30"]',
      JSON.stringify(textOf(s.host, 'sg-trunc')));
  }

  console.log('\n[10] the same names are the same marking; the chain\'s end is declared');
  {
    const doc = makeDoc('light');
    const markings = new MarkingStore();
    const a = await seat([WAFER], { doc, markings, chain: ['a0', 'a1'] });
    const c = await seat([WAFER], { doc, markings, chain: ['a0', 'a1'], keepStart: true });
    const target = byClass(a.host, 'sg-node')[1];
    const id = target ? target.attrs['data-node'] : '';
    if (target) target.dispatch('click', {});
    const seen = byClass(c.host, 'sg-node').find((g) => g.attrs['data-node'] === id);
    say('L1 a part reading the same names sees the other\'s mark', Boolean(seen) && has(seen, 'is-marked'),
      JSON.stringify({ id: Boolean(id), marked: seen ? has(seen, 'is-marked') : null }));
    const end = await seat([WAFER], { chain: ['only'] });
    const node = byClass(end.host, 'sg-node')[1];
    if (node) node.dispatch('click', {});
    say('L2 a chain of one name: a press marks nothing, Continue is off with End of chain',
      end.markings.names().join() === 'only' && end.view.continueButton.disabled === true
        && end.view.continueButton.getAttribute('title') === 'End of chain',
      JSON.stringify({ names: end.markings.names(), title: end.view.continueButton.getAttribute('title') }));
  }
  return { ran: names.length, names, failures: fails };
}

let pass = 0;
const failures = [];
{
  const real = await import('../src/walk/subgraph_view.js');
  const base = await suite(real);
  pass += base.ran - base.failures.length;
  failures.push(...base.failures);

  const { loadWithProbe } = await import('./lib/probe.mjs');
  const { scoreMutants } = await import('./lib/mutation_scorer.mjs');
  const swap = (text, from, to) => {
    if (!text.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`);
    return text.split(from).join(to);
  };
  const M = (id, what, catches, from, to) => ({ id, what, catches, from, to });
  const MUTANTS = [
    M('M1', 'the layer is the node\'s place in the list, not its depth', 'B1',
      '      const layer = base + node.depth;\n', '      const layer = base + placed.length;\n'),
    M('M2', 'a static node is drawn as a circle', 'C1',
      '      group.appendChild(node.static\n', '      group.appendChild(false\n'),
    M('M3', 'the part asks with a follow of its own', 'D1',
      '    const res = await this.walk({ positive: seeds.positive, negative: seeds.negative });\n',
      "    const res = await this.walk({ positive: seeds.positive, negative: seeds.negative, follow: ['inspected'] });\n"),
    M('M4', 'the edges are not drawn', 'A2',
      '    for (const edge of view.edges) {\n      svg.appendChild(', '    for (const edge of []) {\n      svg.appendChild('),
    M('M5', 'a press does not change the facts', 'E1',
      '    this.selected = id;\n    const next', '    const next'),
    M('M6', 'a cut walk says nothing', 'F1',
      '    if (result.cut) cut.push(', '    if (false) cut.push('),
    M('M7', 'the part draws into the page, not its own mount', 'G1',
      '    this.mount.appendChild(this.root);\n', '    this.doc.body.appendChild(this.root);\n'),
    M('M8', 'a node without a depth is placed anyway', 'B3',
      '      if (!Number.isFinite(node.depth)) { unplaced += 1; continue; }\n', ''),
    M('M9', 'static chips lose their mark', 'H1',
      "      chip.appendChild(this._el('span', `sg-swatch${item.static ? ' is-static' : ''}`));\n",
      "      chip.appendChild(this._el('span', 'sg-swatch'));\n"),
    M('M10', 'a press marks nothing', 'K1',
      '    if (name) this.markings.toggle(name, id, SIGN.CASE);\n', ''),
    M('M11', 'Continue walks the start again, not the marking', 'K2',
      '    if (!name || this.state !== \'done\') return;\n    await this._step(name);\n',
      '    if (!name || this.state !== \'done\') return;\n    await this._step(this.chain[0]);\n'),
    M('M12', 'a node reached twice is drawn twice', 'K3',
      '      if (at.has(node.id)) continue;\n', ''),
    M('M13', 'a later step starts at the first column', 'K4',
      '    const base = index === 0 || !seedLayers.length ? 0 : Math.max(...seedLayers);\n', '    const base = 0;\n'),
    M('M14', 'a node does not carry its step', 'K4',
      'sg-node sg-type-${node.colour} sg-step-${node.step}', 'sg-node sg-type-${node.colour}'),
    M('M15', 'Continue is live with nothing marked', 'K2',
      "    setDisabledReason(this.continueButton, !name ? 'End of chain' : (this.markings.count(name) ? '' : 'Mark a node'));\n",
      "    setDisabledReason(this.continueButton, '');\n"),
    M('M16', 'another part writing the same name is not seen', 'L1',
      '    for (const name of this.chain) this.markings.subscribe(name, () => this._restyle());\n', ''),
    M('M17', 'the chain\'s end is not kept: a press past it writes a name of its own', 'L2',
      "  writes() { return this.chain[this.steps.length] || ''; }\n",
      "  writes() { return this.chain[this.steps.length] || 'extra'; }\n"),
    // The wire, widened for this order: a marking start rides as the board's walk sends it.
    { ...M('W1', 'the wire drops a marking start and asks by type and keys', 'D1',
      '        ...(marked ? { nodeId: positive[0], positive, negative }\n',
      '        ...(false ? { nodeId: positive[0], positive, negative }\n'), file: WIRE },
  ];
  const scored = await scoreMutants(MUTANTS, async (mu) => {
    const loaded = (await loadWithProbe(mu.file || SUBJECT, { mutate: (t) => swap(t, mu.from, mu.to) })).module;
    const quiet = console.log;
    console.log = () => {};
    try {
      return mu.file ? await suite(real, loaded.createWalkBoxWalk) : await suite(loaded);
    } finally { console.log = quiet; }
  }, { baselineRan: base.ran, baselineNames: base.names,
       title: '\n  [mutants] - each must be caught by the check it names.' });
  pass += MUTANTS.length - scored.wrong;
  for (let i = 0; i < scored.wrong; i += 1) failures.push(`mutant verdict ${i + 1}`);
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
