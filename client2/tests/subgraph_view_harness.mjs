// SUBGRAPH VIEW — a start's whole walk as a picture (lead c9bf53033), continued by marking (lead f6fc6ba66), drawn
// by Cytoscape.js with dagre (lead 5e1d9e372), folded into lumps (lead e523cfe91) that open only what is ticked,
// with the view held still (lead 03bc94b6b).
//
// The subject is imported (no slicing). Both sides of the counts gate come off the REAL wire:
// `createWalkBoxWalk` fed the server's own bodies (fixtures captured by capture_walk_start.mjs), then
// the table's `walkTableView` and this part's layout read the same answer. The markings live in the
// board's MarkingStore, outside the part, as the page holds them. The stub document has no layout engine, so the
// part runs Cytoscape headless; every cell reads the part's own Cytoscape instance and its own DOM.
//
// Run: node client2/tests/subgraph_view_harness.mjs
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { makeDoc, byClass, flush } from './lib/board_dom.mjs';
import { createWalkBoxWalk, entitySeedId } from '../src/rnd_board/api.js';
import { MarkingStore, SIGN } from '../src/rnd_board/marking_store.js';
import { walkTableView } from '../src/walk/table_view.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SUBJECT = path.join(HERE, '..', 'src', 'walk', 'subgraph_view.js');
const WIRE = path.join(HERE, '..', 'src', 'rnd_board', 'api.js');
const STYLES = path.join(HERE, '..', 'src', 'walk', 'styles.js');
const { WALK_CSS: REAL_CSS } = await import('../src/walk/styles.js');
const fx = (name) => JSON.parse(readFileSync(path.join(HERE, 'fixtures', name), 'utf8'));
const DECL = fx('walk_start_declaration.json');
const WAFER = fx('walk_start_wafer.json');
const DIE = fx('walk_start_die.json');
const STEP2 = fx('walk_start_die_step2.json');
const BUNDLES = fx('walk_bundles_die.json');
const EXPANDED = fx('walk_bundles_die_expanded.json');
const ENTITIES = DECL.entities;
// The oracle reads the declaration itself: the types whose classes hold 'static'.
const STATIC = new Set(ENTITIES.filter((e) => Array.isArray(e.class) && e.class.includes('static'))
  .map((e) => String(e.type).split('@')[0]));
const startId = (body) => (body._start ? entitySeedId(body._start.type, body._start.keys) : body.seed.id);
// Two themes of token values the stub document answers with, so a colour drawn can be traced to its token.
const TOKENS = {
  light: { '--fs-body': '15px', '--fs-tag': '11px', '--fs-label': '12px',
    ...Object.fromEntries([...Array(9)].map((_, k) => [`--cat-${k + 1}`, `#10${k}0a0`])) },
  dark: { '--fs-body': '15px', '--fs-tag': '11px', '--fs-label': '12px',
    ...Object.fromEntries([...Array(9)].map((_, k) => [`--cat-${k + 1}`, `#a0${k}010`])) },
};

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
const textOf = (host, cls) => byClass(host, cls).map((n) => n.textContent);
const paramsOf = (u) => new URLSearchParams(String(u).split('?')[1] || '');
const settle = async () => { for (let i = 0; i < 6; i += 1) await flush(); };

/** A stub document that also keeps key listeners, and - when asked - answers tokens and watches its theme. */
function stubDoc(withTokens) {
  const doc = makeDoc('light');
  const keys = new Set();
  doc.addEventListener = (type, fn) => { if (type === 'keydown') keys.add(fn); };
  doc.removeEventListener = (type, fn) => { if (type === 'keydown') keys.delete(fn); };
  doc.key = (key) => { for (const fn of [...keys]) fn({ key }); };
  if (withTokens) {
    const watchers = [];
    doc.defaultView = {
      getComputedStyle: () => ({ getPropertyValue: (name) => TOKENS[doc.documentElement.getAttribute('data-theme')][name] || '' }),
      MutationObserver: class { constructor(cb) { this.cb = cb; } observe() { watchers.push(this.cb); } },
    };
    doc.theme = (name) => { doc.documentElement.setAttribute('data-theme', name); for (const cb of watchers) cb([]); };
  }
  return doc;
}

async function suite(m, makeWalk = createWalkBoxWalk, css = REAL_CSS) {
  const wire = wireWith(makeWalk);
  const names = [];
  const fails = [];
  const say = (name, cond, detail) => {
    names.push(name);
    if (cond) { console.log(`  PASS ${name}`); return; }
    fails.push(name);
    console.log(`  FAIL ${name}${detail ? ' -- ' + detail : ''}`);
  };
  // Every part this run stood up; their pictures are taken down at the end, so a run does not carry the last one's.
  const seated = [];
  /** One part on its own page; its first marking holds the body's start, as the page writes it. */
  const seat = async (bodies, opts = {}) => {
    const doc = opts.doc || stubDoc(opts.tokens);
    const host = doc.createElement('div');
    doc.body.appendChild(host);
    const urls = [];
    const markings = opts.markings || new MarkingStore();
    const chain = opts.chain || ['s0', 's1', 's2'];
    if (!opts.keepStart) markings.replace(chain[0], [[startId(bodies[0]), SIGN.CASE]]);
    const view = new m.SubgraphView(host, { doc, walk: wire(bodies, urls), entities: () => ENTITIES, markings, chain,
      worldChips: opts.worldChips });
    seated.push(view);
    await view.show();
    return { doc, host, view, urls, markings, chain };
  };
  // A mutant may leave no picture: the cells then fail, they do not throw.
  const none = { length: 0, map: () => [], filter: () => [], some: () => false, every: () => true, forEach() {} };
  const nodesOf = (s) => (s.view.cy ? s.view.cy.nodes('[kind = "node"]') : none);
  const edgesOf = (s) => (s.view.cy ? s.view.cy.edges('[kind = "edge"]') : none);
  const lumpsOf = (s, level) => (s.view.cy ? s.view.cy.nodes(`[kind = "lump"]${level ? `[level = "${level}"]` : ''}`) : none);
  const press = (s, id) => {
    const n = s.view.cy && s.view.cy.getElementById(id);
    if (!n || n.empty()) return false;
    n.emit('tap');
    return true;
  };
  // A press only picks (lead 9dc2a5695 ②); the picked node's Mark puts it in the marking this step writes.
  const mark = (host) => {
    const button = byClass(host, 'sg-mark')[0];
    if (button) button.dispatch('click', {});
    return Boolean(button);
  };
  const pickerOf = (s) => byClass(s.host, 'sg-pick')[0] || null;
  const rowsOf = (s) => (pickerOf(s) ? byClass(pickerOf(s), 'sg-pick-row') : []);
  const tickRow = (row) => { const cb = row.children[0]; cb.checked = !cb.checked; cb.dispatch('change', {}); };
  const tickAll = (s) => {
    const all = pickerOf(s) && byClass(pickerOf(s), 'sg-pick-all')[0];
    if (all) { all.children[0].checked = true; all.children[0].dispatch('change', {}); }
  };
  const openTicked = (s) => { const go = pickerOf(s) && byClass(pickerOf(s), 'sg-pick-open')[0]; if (go) go.dispatch('click', {}); };
  const viewport = (s) => (s.view.cy ? JSON.stringify([s.view.cy.zoom(), s.view.cy.pan()]) : 'none');
  const positions = (s) => new Map(nodesOf(s).map((n) => [n.id(), { ...n.position() }]));
  const stayed = (before, s) => [...before].every(([id, p]) => {
    const n = s.view.cy && s.view.cy.getElementById(id);
    return n && n.nonempty() && n.position('x') === p.x && n.position('y') === p.y;
  });

  /** Open everything, as a person does: press a node with a big lump, then its Unfold, until no big lump is left. */
  const openAll = (s) => {
    for (let guard = 0; guard < 200; guard += 1) {
      const big = lumpsOf(s, 'big')[0];
      if (!big) return;
      press(s, big.data('owner'));
      const unfold = byClass(s.host, 'sg-fold')[0];
      if (!unfold || unfold.textContent !== 'Unfold') return;
      unfold.dispatch('click', {});
    }
  };
  /** Open every lump the server sent, as a person does: press it, All, Open - until none is left. */
  const openEvery = (s) => {
    for (let guard = 0; guard < 400; guard += 1) {
      const lump = lumpsOf(s).filter((n) => !n.data('unsent'))[0];
      if (!lump) return;
      press(s, lump.id());
      tickAll(s);
      openTicked(s);
    }
  };
  /** The nodes one step from where a step stood, read off the layout: the oracle the first picture is held to. */
  const oneStep = (layout, from) => {
    const layerOf = new Map(layout.nodes.map((n) => [n.id, n.layer]));
    const out = new Set();
    for (const e of layout.edges) {
      for (const [a, b] of [[e.source, e.target], [e.target, e.source]]) {
        if (from.has(a) && layerOf.get(b) >= layerOf.get(a) && !from.has(b)) out.add(b);
      }
    }
    return out;
  };

  // The die walk, stood up once and read by the sections that only read it (it is the slow one to lay out).
  const die = await seat([DIE]);
  const dieFirst = positions(die);
  const dieFirstLumps = lumpsOf(die).map((n) => n.id()).sort().join(',');
  console.log('\n[0] the first picture: the start and its one step; what lies behind is folded (owner 10-06)');
  {
    const r = await wire([DIE], [])(DIE._start);
    const from = new Set([...die.view.steps[0].seeds, ...r.nodes.filter((n) => n.depth === 0).map((n) => n.id)]);
    const near = oneStep(die.view.layout, from);
    const drawn = new Set(nodesOf(die).map((n) => n.id()));
    const v = m.lumpView(die.view.layout, die.view.fold, die.view.steps.flatMap((x) => x.seeds));
    const leads = [...near].filter((id) => oneStep(die.view.layout, new Set([id])).size > 0);
    say('A5 drawn are the start, its twins and their one step; each of those that leads further has its big lump; the rest is inside',
      near.size > 0 && drawn.size === from.size + near.size && [...from, ...near].every((id) => drawn.has(id))
        && leads.length > 0 && leads.every((id) => lumpsOf(die, 'big').some((n) => n.data('owner') === id))
        && drawn.size + v.hidden === r.nodes.length
        && JSON.stringify(textOf(die.host, 'sg-counts')) === `["Nodes ${r.nodes.length} · Edges ${r.edges.length}"]`,
      JSON.stringify({ drawn: drawn.size, from: from.size, near: near.size, leads: leads.length, hidden: v.hidden }));
  }
  openAll(die);
  console.log('\n[1] all opened, what is drawn is what the walk answered - the same count the table shows');
  for (const [tag, body] of [['A1', WAFER], ['A3', DIE]]) {
    const r = await wire([body], [])(body._start);
    const table = walkTableView(r, ENTITIES, DECL.predicates || []);
    const rows = table.sections.reduce((n, s) => n + s.rows.length, 0) + (table.hidden || 0);
    const s = body === DIE ? die : await seat([body]);
    if (s !== die) openAll(s);
    const drawnNodes = nodesOf(s).length;
    const drawnEdges = edgesOf(s).length;
    say(`${tag} ${body._start.type}: nodes drawn = the response = the table's rows`,
      drawnNodes > 0 && drawnNodes === r.nodes.length && rows === r.nodes.length,
      JSON.stringify({ drawnNodes, response: r.nodes.length, rows }));
    const edgeTag = tag === 'A1' ? 'A2' : 'A4';
    say(`${edgeTag} ${body._start.type}: edges drawn = the response, none with an end not drawn`,
      drawnEdges > 0 && drawnEdges === r.edges.length && byClass(s.host, 'sg-note').length === 0,
      JSON.stringify({ drawnEdges, response: r.edges.length, notes: textOf(s.host, 'sg-note') }));
  }

  console.log('\n[2] the column is the step count from the start, the same picture for the same answer');
  {
    const s = die;
    const xOf = new Map();
    let sameX = true;
    nodesOf(s).forEach((n) => {
      const d = n.data('depth');
      if (xOf.has(d) && xOf.get(d) !== n.position('x')) sameX = false;
      xOf.set(d, n.position('x'));
    });
    const depths = [...xOf.keys()].sort((a, b) => a - b);
    const rising = depths.every((d, i) => i === 0 || xOf.get(d) > xOf.get(depths[i - 1]));
    say('B1 one column per depth, columns in step order (dagre orders inside a column)',
      depths.length > 2 && sameX && rising, JSON.stringify({ depths, sameX, rising }));
    const r = await wire([DIE], [])(DIE._start);
    const layout = m.subgraphLayout([{ results: [r] }], ENTITIES);
    const again = m.subgraphLayout([{ results: [await wire([JSON.parse(JSON.stringify(DIE))], [])(DIE._start)] }], ENTITIES);
    const twice = await seat([DIE]);
    const p1 = JSON.stringify([...dieFirst]);
    say('B2 the same answer lays out the same, twice - the layout and the first picture\'s places',
      JSON.stringify(layout) === JSON.stringify(again) && p1 === JSON.stringify([...positions(twice)]));
    const w = await wire([WAFER], [])(WAFER._start);
    const lost = { ...w, nodes: w.nodes.map((n, i) => (i === 1 ? { ...n, depth: undefined } : n)) };
    const partial = m.subgraphLayout([{ results: [lost] }], ENTITIES);
    say('B3 a node without a depth is counted, not placed', partial.unplaced === 1
      && partial.nodes.length === w.nodes.length - 1, JSON.stringify({ unplaced: partial.unplaced, placed: partial.nodes.length }));
  }

  console.log('\n[3] a static type is another shape, by the declaration\'s list');
  {
    const s = die;
    const typeOf = (n) => String(n.data('type')).split('@')[0];
    const wrong = nodesOf(s).filter((n) => (STATIC.has(typeOf(n)) ? 'rectangle' : 'ellipse') !== n.style('shape'));
    const statics = nodesOf(s).filter((n) => STATIC.has(typeOf(n))).length;
    say('C1 static nodes are squares, the rest circles', statics > 0 && wrong.length === 0,
      JSON.stringify({ statics, wrong: wrong.length }));
  }

  console.log('\n[4] the part asks its marking and nothing else');
  {
    const { urls } = die;
    const params = paramsOf(urls[0] || '');
    const extra = [...params.keys()].filter((k) => k !== 'id' && k !== 'positive' && k !== 'fanout_limit');
    say('D1 one request: the start marking (id and positive, its one node) and the declared fan-out cap, nothing else',
      urls.length === 1 && params.get('id') === startId(DIE) && params.get('fanout_limit') === '20'
        && JSON.stringify(params.getAll('positive')) === JSON.stringify([startId(DIE)]) && extra.length === 0,
      JSON.stringify({ urls: urls.length, extra }));
  }

  console.log('\n[5] a node pressed shows its facts');
  {
    const s = die;
    const r = await wire([DIE], [])(DIE._start);
    const touchingOf = (id) => r.edges.filter((e) => e.source === id || e.target === id).length;
    const target = r.nodes.find((n) => touchingOf(n.id) > 1) || r.nodes[0];
    const pressed = press(s, target.id);
    const lines = textOf(s.host, 'sg-fact');
    const touching = touchingOf(target.id);
    const keyLines = Object.keys(target.keys || {}).length;
    say('E1 its keys and every edge touching it', pressed && touching > 1 && lines.length === keyLines + touching
      && textOf(s.host, 'sg-facts-head')[0] === `${target.label} · ${target.type}`,
      JSON.stringify({ lines: lines.length, keyLines, touching }));
    const picked = nodesOf(s).filter((n) => n.hasClass('is-selected')).map((n) => n.id());
    say('E2 the pick is on that node alone', picked.length === 1 && picked[0] === target.id, JSON.stringify(picked));
  }

  console.log('\n[6] a cut walk says so, in one line');
  {
    const wafer = await seat([WAFER]);
    say('F1 the die walk: Truncated with its budget; the wafer walk: no line',
      JSON.stringify(textOf(die.host, 'sg-trunc')) === '["Truncated · nodes 400"]'
        && textOf(wafer.host, 'sg-trunc').length === 0,
      JSON.stringify([textOf(die.host, 'sg-trunc'), textOf(wafer.host, 'sg-trunc')]));
  }

  console.log('\n[7] two on one page with their own markings do not touch each other');
  {
    const doc = stubDoc();
    const markings = new MarkingStore();
    const a = await seat([WAFER], { doc, markings, chain: ['a0', 'a1'] });
    const b = await seat([BUNDLES], { doc, markings, chain: ['b0', 'b1'] });
    const second = nodesOf(a)[1];
    if (second) press(a, second.id());
    mark(a.host);
    say('G1 each draws its own walk, and a press and Mark in one leave the other unpicked and unmarked',
      JSON.stringify(textOf(a.host, 'sg-counts')) === `["Nodes ${WAFER.nodes.length} · Edges ${WAFER.edges.length}"]`
        && JSON.stringify(textOf(b.host, 'sg-counts')) === `["Nodes ${BUNDLES.nodes.length} · Edges ${BUNDLES.edges.length}"]`
        && byClass(a.host, 'sg-fact').length > 0 && byClass(b.host, 'sg-fact').length === 0
        && markings.count('a1') === 1 && markings.count('b1') === 0 && a.view.cy !== b.view.cy
        && nodesOf(b).every((n) => !n.hasClass('is-selected') && !n.hasClass('is-marked')),
      JSON.stringify([textOf(a.host, 'sg-counts'), textOf(b.host, 'sg-counts'), markings.count('a1'), markings.count('b1')]));
  }

  console.log('\n[8] the legend: one chip per type drawn, its count, static marked');
  {
    const { host } = die;
    const chips = byClass(host, 'sg-chip');
    const counted = chips.reduce((n, c) => n + Number(String(c.textContent).split(' ').pop()), 0);
    const types = new Set(DIE.nodes.map((n) => String(n.type).split('@')[0]));
    const staticChips = chips.filter((c) => byClass(c, 'sg-swatch').some((x) => x.className.split(' ').includes('is-static')))
      .map((c) => c.attrs['data-type']);
    say('H1 chips = the types drawn, counts add up, static swatches on the static types',
      chips.length === types.size && counted === DIE.nodes.length
        && staticChips.length > 0 && staticChips.every((t) => STATIC.has(t)),
      JSON.stringify({ chips: chips.length, types: types.size, counted, staticChips }));
  }

  console.log('\n[9] continued by marking: a press picks, Mark marks, Continue walks the marking, one picture');
  {
    const s = await seat([DIE, STEP2]);
    openAll(s);
    const marked = STEP2._marked;
    const offBefore = s.view.continueButton && s.view.continueButton.disabled === true
      && s.view.continueButton.getAttribute('title') === 'Mark a node';
    press(s, marked);
    const afterPress = JSON.stringify(s.markings.entries('s1'));
    mark(s.host);
    say('K1 a press writes nothing; its Mark writes that node, +, into the marking this step writes',
      afterPress === '[]' && JSON.stringify(s.markings.entries('s1')) === JSON.stringify([[marked, SIGN.CASE]])
        && s.markings.count('s0') === 1,
      `${afterPress} -> ${JSON.stringify(s.markings.entries('s1'))}`);
    const onAfter = s.view.continueButton && s.view.continueButton.disabled === false;
    const before = positions(s);
    const viewBefore = viewport(s);
    s.urls.length = 0;
    if (s.view.continueButton) s.view.continueButton.dispatch('click', {});
    await settle();
    const params = paramsOf(s.urls[0] || '');
    const extra = [...params.keys()].filter((k) => k !== 'id' && k !== 'positive' && k !== 'fanout_limit');
    say('K2 Continue is off until something is marked, then asks that marking and nothing else',
      offBefore && onAfter && s.urls.length === 1 && params.get('id') === marked && params.get('fanout_limit') === '20'
        && JSON.stringify(params.getAll('positive')) === JSON.stringify([marked]) && extra.length === 0,
      JSON.stringify({ offBefore, onAfter, urls: s.urls.length, id: params.get('id') === marked, extra }));
    const one = new Set(DIE.nodes.map((n) => n.id));
    const union = new Set([...one, ...STEP2.nodes.map((n) => n.id)]);
    const edgeUnion = new Set([...DIE.edges.map((e) => e.id), ...STEP2.edges.map((e) => e.id)]);
    const drawnIds = nodesOf(s).map((n) => n.id());
    const both = m.lumpView(s.view.layout, s.view.fold, s.view.steps.flatMap((x) => x.seeds));
    say('K3 both steps on one picture: a node reached twice is drawn once, every edge once; what is not drawn is inside a lump',
      union.size > one.size && new Set(drawnIds).size === drawnIds.length && drawnIds.length + both.hidden === union.size
        && s.view.layout.edges.length === edgeUnion.size && edgesOf(s).length === both.edges.length,
      JSON.stringify({ drawn: drawnIds.length, hidden: both.hidden, union: union.size, edges: edgesOf(s).length, edgeUnion: edgeUnion.size }));
    // 🔴 THE FIRST PICTURE'S RULE, FROM THE MARKED POINT (owner 10-06): its one step drawn, what lies behind held.
    const from2 = new Set([marked, ...STEP2.nodes.filter((n) => n.depth === 0).map((n) => n.id)]);
    const step2 = [...oneStep(s.view.layout, from2)];
    const fresh2 = [...union].filter((id) => !one.has(id));
    const beyond = fresh2.filter((id) => !step2.includes(id));
    say('K7 Continue draws the marked point\'s one step; what the answer brings beyond it is inside a lump',
      step2.length > 0 && step2.every((id) => drawnIds.includes(id))
        && beyond.length > 0 && beyond.every((id) => !drawnIds.includes(id))
        && fresh2.filter((id) => drawnIds.includes(id)).every((id) => step2.includes(id)),
      JSON.stringify({ step2: step2.length, beyond: beyond.length, drawnNew: fresh2.filter((id) => drawnIds.includes(id)).length }));
    say('K6 Continue moves nothing already drawn and leaves the view where it was',
      before.size > 0 && stayed(before, s) && viewport(s) === viewBefore, JSON.stringify({ view: viewport(s) === viewBefore }));
    say('K5 each cut step says so with its step',
      JSON.stringify(textOf(s.host, 'sg-trunc')) === '["Truncated · step 1 · nodes 400","Truncated · step 2 · nodes 30"]',
      JSON.stringify(textOf(s.host, 'sg-trunc')));
    // 🔴 A HAND WALK where it matters: what was in sight past the marked point's step stays; only the new is held.
    {
      const hn = (id, depth) => ({ id, type: 'die', label: id, depth, keys: { k: id } });
      const he = (a2, b2) => ({ id: `${a2}-${b2}`, source: a2, target: b2, predicate: 'p' });
      const H1 = { seed: { id: 's' }, nodes: [hn('s', 0), hn('a', 1), hn('c', 1), hn('b', 2), hn('y', 3)],
        edges: [he('s', 'a'), he('s', 'c'), he('a', 'b'), he('b', 'y')], truncated: null };
      const H2 = { seed: { id: 'a' }, nodes: [hn('a', 0), hn('b', 1), hn('y', 2), hn('x', 2)],
        edges: [he('a', 'b'), he('b', 'y'), he('b', 'x')], truncated: null };
      const h = await seat([H1, H2]);
      openAll(h);
      press(h, 'a');
      mark(h.host);
      const was = positions(h);
      h.view.continueButton.dispatch('click', {});
      await settle();
      const held = lumpsOf(h, 'small').filter((n) => n.data('owner') === 'b');
      say('K8 a Continue keeps what was in sight past the marked point\'s step, and holds only the new beside it',
        was.has('y') && stayed(was, h) && h.view.cy.getElementById('x').empty()
          && held.length === 1 && held[0].data('count') === 1 && held[0].data('label').includes('1 more'),
        JSON.stringify({ y: h.view.cy.getElementById('y').nonempty(), x: h.view.cy.getElementById('x').nonempty(),
          held: held.length && held[0].data('label') }));
    }
    // Every lump opened, as a person does, to read the second step's columns.
    openEvery(s);
    const nodeById = (id) => s.view.cy && s.view.cy.getElementById(id);
    const seed = nodeById(marked);
    const stepOne = nodesOf(s).filter((n) => one.has(n.id()));
    const colX = (depth) => (stepOne.find((n) => n.data('depth') === depth) || { position: () => NaN }).position('x');
    const gap = colX(1) - colX(0);
    const fresh = nodesOf(s).filter((n) => !one.has(n.id()));
    // A fresh node's depth is its depth in the second walk, counted from the marked point.
    const off = fresh.filter((n) => Math.abs(n.position('x') - (seed.position('x') + n.data('depth') * gap)) > 0.5);
    say('K4 the second step carries on from the marked point, and its nodes say which step they came from',
      Boolean(seed) && seed.nonempty() && seed.data('depth') >= 2 && fresh.length === fresh2.length && gap > 0 && off.length === 0
        && fresh.every((n) => n.data('step') === 2) && stepOne.every((n) => n.data('step') === 1) && seed.hasClass('is-seed'),
      JSON.stringify({ fresh: fresh.length, of: fresh2.length, gap, off: off.length, seedDepth: seed && seed.nonempty() && seed.data('depth') }));
  }

  console.log('\n[10] the same names are the same marking; the chain\'s end is declared');
  {
    const doc = stubDoc();
    const markings = new MarkingStore();
    const a = await seat([WAFER], { doc, markings, chain: ['a0', 'a1'] });
    const c = await seat([WAFER], { doc, markings, chain: ['a0', 'a1'], keepStart: true });
    const target = nodesOf(a)[1];
    const id = target ? target.id() : '';
    press(c, id);
    press(a, id);
    mark(a.host);
    const seen = c.view.cy && c.view.cy.getElementById(id);
    const cMark = byClass(c.host, 'sg-mark')[0];
    say('L1 a part reading the same names sees the other\'s mark, on the node and on its own Mark',
      Boolean(seen) && seen.nonempty() && seen.hasClass('is-marked') && Boolean(cMark) && cMark.getAttribute('aria-pressed') === 'true',
      JSON.stringify({ id: Boolean(id), marked: seen && seen.nonempty() ? seen.hasClass('is-marked') : null,
        cMark: cMark && cMark.getAttribute('aria-pressed') }));
    const end = await seat([WAFER], { chain: ['only'] });
    const node = nodesOf(end)[1];
    if (node) press(end, node.id());
    const endMark = byClass(end.host, 'sg-mark')[0];
    mark(end.host);
    say('L2 a chain of one name: Mark and Continue are off with End of chain, and Mark marks nothing',
      end.markings.names().join() === 'only' && end.view.continueButton.disabled === true
        && end.view.continueButton.getAttribute('title') === 'End of chain'
        && Boolean(endMark) && endMark.disabled === true && endMark.getAttribute('title') === 'End of chain',
      JSON.stringify({ names: end.markings.names(), title: end.view.continueButton.getAttribute('title'),
        mark: endMark && [endMark.disabled, endMark.getAttribute('title')] }));
  }

  console.log('\n[11] bundles: a fan-out over the cap is an unsent lump; pressed, it is walked, then listed');
  {
    const doc = stubDoc();
    const markings = new MarkingStore();
    const a = await seat([BUNDLES, EXPANDED], { doc, markings, chain: ['a0', 'a1'] });
    const b = await seat([BUNDLES], { doc, markings, chain: ['b0', 'b1'] });
    const unsent = (s) => lumpsOf(s).filter((n) => n.data('unsent'));
    const words = (x) => `${x.direction === 'incoming' ? `← ${x.predicate}` : `${x.predicate} →`}\n${x.count} ${x.far_type}`;
    const want = BUNDLES.bundles.map(words).sort();
    const got = unsent(a).map((n) => n.data('label')).sort();
    say('P1 one unsent lump per bundle the walk answered, saying its predicate, count and far type, dashed',
      want.length > 0 && JSON.stringify(got) === JSON.stringify(want)
        && unsent(a).every((n) => n.style('border-style') === 'dashed'),
      JSON.stringify({ got, want }));
    const first = EXPANDED._expanded;
    const key = `${first.node}|${first.predicate}|${first.direction}`;
    a.urls.length = 0;
    const bBefore = b.urls.length;
    const pressed = press(a, `lump:${key}`);
    await settle();
    const params = paramsOf(a.urls[0] || '');
    say('P2 pressed, it asks the same marking again with that bundle expanded; the other part asks nothing',
      pressed && a.urls.length === 1 && JSON.stringify(params.getAll('expand')) === JSON.stringify([key])
        && params.get('id') === startId(BUNDLES) && params.get('fanout_limit') === '20' && b.urls.length === bBefore,
      JSON.stringify({ pressed, urls: a.urls.length, expand: params.getAll('expand'), b: b.urls.length - bBefore }));
    const outgoing = first.direction === 'outgoing';
    const fan = EXPANDED.edges.filter((e) => e.predicate === first.predicate
      && (outgoing ? e.source === first.node : e.target === first.node));
    const fanEnds = new Set(fan.map((e) => (outgoing ? e.target : e.source)));
    const shownBefore = new Set(nodesOf(a).map((n) => n.id()));
    const listed = rowsOf(a).map((r) => r.attrs['data-value']);
    const lump = a.view.cy.getElementById(`lump:${key}`);
    say('P3 then lists what the walk brought, nothing drawn yet: the rows are the fan-out not already in sight, and the lump counts them',
      listed.length > 0 && listed.length === [...fanEnds].filter((id) => !shownBefore.has(id)).length
        && lump.nonempty() && lump.data('count') === listed.length && !lump.data('unsent')
        && listed.every((id) => !shownBefore.has(id)),
      JSON.stringify({ listed: listed.length, fan: fanEnds.size, count: lump.nonempty() && lump.data('count') }));
    tickAll(a);
    openTicked(a);
    const drawnIds = nodesOf(a).map((n) => n.id());
    const drawnEdges = new Set(edgesOf(a).map((e) => e.id()));
    say('P4 All, opened: the fan-out drawn once, its count; the walked lump is gone and no unsent lump keeps its key',
      new Set(drawnIds).size === drawnIds.length && [...fanEnds].every((id) => drawnIds.includes(id))
        && fan.length === first.count && fan.every((e) => drawnEdges.has(e.id))
        && a.view.cy.getElementById(`lump:${key}`).empty() && !unsent(a).some((n) => n.data('key') === key),
      JSON.stringify({ drawn: drawnIds.length, fan: fan.length, count: first.count,
        left: a.view.cy.getElementById(`lump:${key}`).length }));
    const firstIds = new Set(BUNDLES.nodes.map((n) => n.id));
    const inside = nodesOf(a).find((n) => !firstIds.has(n.id()));
    if (inside) press(a, inside.id());
    mark(a.host);
    say('P5 a point inside the opened bundle can be marked for Continue',
      Boolean(inside) && JSON.stringify(markings.entries('a1')) === JSON.stringify([[inside.id(), SIGN.CASE]]),
      JSON.stringify(markings.entries('a1')));
    // A lump already walked: one ticked out of it, then pressed again.
    const c = await seat([BUNDLES, EXPANDED]);
    press(c, `lump:${key}`);
    await settle();
    const total = rowsOf(c).length;
    if (rowsOf(c)[0]) tickRow(rowsOf(c)[0]);
    openTicked(c);
    const asked = c.urls.length;
    press(c, `lump:${key}`);
    await settle();
    const again = c.view.cy.getElementById(`lump:${key}`);
    say('P6 a lump already walked keeps the rest - n more - and, pressed again, lists them and asks nothing',
      total > 1 && c.urls.length === asked && rowsOf(c).length === total - 1 && again.nonempty()
        && again.data('label').includes(`${total - 1} more`),
      JSON.stringify({ total, rows: rowsOf(c).length, asked: c.urls.length - asked, label: again.nonempty() && again.data('label') }));
  }

  console.log('\n[N] a node folds its branches into one lump, on the picture only (lead 43a738d58 ③ · e523cfe91)');
  {
    // A hand graph: s -> a -> b -> c and s -> d -> c. Folding a hides b; c is reached through d.
    // And s -> e at the same depth (a real walk's depth stays put along some edges), f -> e one deeper.
    // No depth: the fold walks from the seed alone here, so a same-depth edge is the only way to e.
    const node = (id, layer) => ({ id, layer, type: 't' });
    const edge = (source, target) => ({ id: `${source}${target}`, source, target, predicate: 'p', predicateName: 'p' });
    const chip = (n) => ({ node: n, predicate: 'q', direction: 'outgoing', farType: 'x', count: 2, step: 0, key: `${n}|q|outgoing` });
    const hand = { nodes: [node('s', 0), node('e', 0), node('a', 1), node('d', 1), node('f', 1), node('b', 2), node('c', 3)],
      edges: [edge('s', 'a'), edge('a', 'b'), edge('b', 'c'), edge('s', 'd'), edge('d', 'c'), edge('s', 'e'), edge('f', 'e')],
      chips: [chip('a'), chip('d')] };
    const away = (folded) => [...m.foldedAway(hand, new Set(folded), ['s'])].sort().join(',');
    say('N1 only what is reached through the folded node hides; a node reached another way stays; a same-depth edge is walked',
      away(['a']) === 'b' && away(['d']) === '' && away(['a', 'd']) === 'b,c' && away(['e']) === 'f',
      JSON.stringify({ a: away(['a']), d: away(['d']), both: away(['a', 'd']), e: away(['e']) }));
    const fv = m.lumpView(hand, { big: new Map([['a', m.branchKeys(hand, 'a')]]), lumped: new Map() }, ['s']);
    const bigA = fv.lumps.filter((l) => l.level === 'big' && l.owner === 'a');
    say('N2 a folded node keeps its place; its unsent fan-out goes inside its one big lump, which counts it; d\'s stays its own',
      fv.nodes.some((n) => n.id === 'a') && !fv.nodes.some((n) => n.id === 'b') && bigA.length === 1 && bigA[0].count === 3
        && !fv.lumps.some((l) => l.level === 'small' && l.owner === 'a') && fv.lumps.some((l) => l.unsent && l.owner === 'd'),
      JSON.stringify(fv.lumps.map((l) => [l.id, l.count])));

    // 🔴 THE RULE ON A HAND GRAPH (owner 10-06): s -> p -> q -> r and s -> v -> u, v -> w. p is folded and in sight,
    //    v and u are in sight; the answer is new for q, r and w. From p: its fold opens, q is drawn and folds r;
    //    v keeps u and holds w in a small lump.
    {
      const hn = (id, layer) => ({ id, layer, type: 't' });
      const he = (source, target, name) => ({ id: `${source}${target}`, source, target, predicate: name, predicateName: name });
      const h2 = { nodes: [hn('s', 0), hn('p', 1), hn('v', 1), hn('q', 2), hn('u', 2), hn('w', 2), hn('r', 3)],
        edges: [he('s', 'p', 'a'), he('p', 'q', 'b'), he('q', 'r', 'c'), he('s', 'v', 'a'), he('v', 'u', 'd'), he('v', 'w', 'd')],
        chips: [] };
      const f2 = { big: new Map([['p', new Set(['p|b|outgoing'])]]), lumped: new Map() };
      m.foldBeyond(h2, f2, ['p'], new Set(['s', 'p', 'v', 'u']));
      const v2 = m.lumpView(h2, f2, ['s']);
      say('N9 from a folded point: its fold opens, its one step is drawn and folds what lies behind; a node in sight keeps what it showed and holds the new',
        v2.nodes.map((n) => n.id).sort().join(',') === 'p,q,s,u,v' && v2.lumps.some((l) => l.level === 'big' && l.owner === 'q')
          && v2.lumps.some((l) => l.level === 'small' && l.owner === 'v' && l.count === 1),
        JSON.stringify({ shown: v2.nodes.map((n) => n.id), lumps: v2.lumps.map((l) => [l.id, l.count]) }));
    }
    const a = await seat([DIE]);
    const b = await seat([DIE], { doc: a.doc });
    openAll(a);
    const bWas = JSON.stringify([nodesOf(b).map((n) => n.id()).sort(), lumpsOf(b).map((n) => n.id()).sort()]);
    const seeds = a.view.steps.flatMap((s) => s.seeds);
    const target = a.view.layout.nodes.map((n) => ({ id: n.id, hides: m.foldedAway(a.view.layout, new Set([n.id]), seeds).size }))
      .sort((x, y) => y.hides - x.hides)[0];
    const counts = () => textOf(a.host, 'sg-counts').join('|');
    const countsBefore = counts();
    const before = positions(a);
    press(a, target.id);
    mark(a.host);
    const marksPressed = JSON.stringify(a.markings.entries(a.chain[1]));
    const fold = byClass(a.host, 'sg-fold')[0];
    if (fold) fold.dispatch('click', {});
    const big = lumpsOf(a, 'big');
    say('N3 Fold branches hides exactly what the fold reaches, and one big lump says N folded where the branches were',
      target.hides > 0 && Boolean(fold) && nodesOf(a).length === a.view.layout.nodes.length - target.hides
        && big.length === 1 && big[0].data('owner') === target.id && big[0].data('label').startsWith(`${target.hides} folded`),
      JSON.stringify({ hides: target.hides, drawn: nodesOf(a).length, all: a.view.layout.nodes.length, lump: big.length && big[0].data('label') }));
    say('N4 the counts above stay the walk\'s; the folded count is its own line',
      counts() === countsBefore && textOf(a.host, 'sg-note').includes(`Folded · ${target.hides} node${target.hides === 1 ? '' : 's'}`),
      JSON.stringify({ before: countsBefore, after: counts(), notes: textOf(a.host, 'sg-note') }));
    b.view.render();
    say('N5 the other part on the page, the same walk, folds nothing: drawn again, its picture is what it was',
      nodesOf(b).length > 0 && JSON.stringify([nodesOf(b).map((n) => n.id()).sort(), lumpsOf(b).map((n) => n.id()).sort()]) === bWas,
      String(nodesOf(b).length));
    const sent = await seat([BUNDLES]);
    const unsentLump = lumpsOf(sent).filter((n) => n.data('unsent'))[0];
    say('N6 both lumps are one lump: the fold\'s and the unsent fan-out\'s share the kind and the shape, each saying its count',
      Boolean(unsentLump) && big.length === 1 && unsentLump.data('kind') === big[0].data('kind')
        && unsentLump.style('shape') === big[0].style('shape')
        && /^\d+ folded/.test(big[0].data('label')) && /→\n\d+ \S+$/.test(unsentLump.data('label')),
      JSON.stringify({ shapes: [unsentLump && unsentLump.style('shape'), big.length && big[0].style('shape')] }));
    const unfold = byClass(a.host, 'sg-fold')[0];
    const unfoldWord = unfold && unfold.textContent;
    if (unfold) unfold.dispatch('click', {});
    say('N7 Unfold opens it all: every node back where it stood, no lump left, nothing walked again',
      unfoldWord === 'Unfold' && nodesOf(a).length === a.view.layout.nodes.length && lumpsOf(a).length === 0
        && stayed(before, a) && a.urls.length === 1, JSON.stringify({ unfoldWord, urls: a.urls.length }));
    say('N8 folding and opening mark nothing: the marking is what Mark left',
      marksPressed !== '[]' && JSON.stringify(a.markings.entries(a.chain[1])) === marksPressed,
      `${marksPressed} -> ${JSON.stringify(a.markings.entries(a.chain[1]))}`);
  }

  console.log('\n[LM] a lump opens only what is ticked, out of where it stood; the view does not move (lead 03bc94b6b)');
  {
    const s = await seat([DIE]);
    openAll(s);
    const seeds = s.view.steps.flatMap((x) => x.seeds);
    // The node whose fold leaves the most keys, among those with a key of three or more members.
    const pick = s.view.layout.nodes.map((n) => {
      const v = m.lumpView(s.view.layout, { big: new Map([[n.id, m.branchKeys(s.view.layout, n.id)]]), lumped: new Map() }, seeds);
      const l = v.lumps.find((x) => x.level === 'big' && x.owner === n.id);
      return { id: n.id, groups: l ? l.groups : [] };
    }).filter((c) => c.groups.length > 1 && c.groups.some((g) => g.members.length > 2))
      .sort((p, q) => q.groups.length - p.groups.length)[0];
    const view0 = viewport(s);
    const at0 = positions(s);
    press(s, pick ? pick.id : '');
    const fold = byClass(s.host, 'sg-fold')[0];
    if (fold) fold.dispatch('click', {});
    const bigs = lumpsOf(s, 'big');
    say('LM1 Fold: one big lump on that node and no small lump of it',
      Boolean(pick) && bigs.length === 1 && bigs[0].data('owner') === pick.id
        && lumpsOf(s, 'small').filter((n) => n.data('owner') === pick.id).length === 0,
      JSON.stringify({ pick: Boolean(pick), big: bigs.length }));
    const keyed = pick ? pick.groups.find((g) => g.members.length > 2) : null;
    const at1 = positions(s);
    if (bigs[0]) press(s, bigs[0].id());
    const keyRows = rowsOf(s);
    const keyRow = keyRows.find((r) => keyed && r.attrs['data-value'] === keyed.key);
    if (keyRow) tickRow(keyRow);
    const goWord = (byClass(pickerOf(s) || { children: [] }, 'sg-pick-open')[0] || {}).textContent;
    openTicked(s);
    const smalls = lumpsOf(s, 'small').filter((n) => n.data('owner') === (pick && pick.id));
    const stillBig = lumpsOf(s, 'big').filter((n) => n.data('owner') === (pick && pick.id));
    say('LM2 the big lump lists one row per key with its count; the key ticked becomes its small lump, the rest stay in the big one',
      Boolean(keyed) && keyRows.length === pick.groups.length && goWord === 'Open 1' && smalls.length === 1
        && smalls[0].data('key') === keyed.key && smalls[0].data('count') === keyed.members.length && stillBig.length === 1,
      JSON.stringify({ rows: keyRows.length, keys: pick && pick.groups.length, goWord, smalls: smalls.length, big: stillBig.length }));
    const [fuller, lighter] = stillBig.length && smalls.length && stillBig[0].data('count') > smalls[0].data('count')
      ? [stillBig[0], smalls[0]] : [smalls[0], stillBig[0]];
    say('LM9 a lump that holds more is bigger: of the big one and the small one it let out, the fuller is the wider',
      smalls.length === 1 && stillBig.length === 1 && fuller.data('count') > lighter.data('count')
        && fuller.width() > lighter.width(),
      JSON.stringify({ big: stillBig.length && [stillBig[0].data('count'), stillBig[0].width()],
        small: smalls.length && [smalls[0].data('count'), smalls[0].width()] }));
    const lumpAt = smalls[0] ? { ...smalls[0].position() } : { x: NaN, y: NaN };
    const at2 = positions(s);
    if (smalls[0]) press(s, smalls[0].id());
    const memberRows = rowsOf(s);
    const chosen = memberRows.slice(0, 2).map((r) => r.attrs['data-value']);
    for (const r of memberRows.slice(0, 2)) tickRow(r);
    openTicked(s);
    const drawn = new Set(nodesOf(s).map((n) => n.id()));
    const left = lumpsOf(s, 'small').filter((n) => n.data('key') === (keyed && keyed.key));
    say('LM3 the small lump lists its members; only the two ticked become nodes, the lump keeps the rest and says n more',
      Boolean(keyed) && memberRows.length === keyed.members.length && chosen.every((id) => drawn.has(id))
        && keyed.members.filter((id) => !chosen.includes(id)).every((id) => !drawn.has(id))
        && left.length === 1 && left[0].data('count') === keyed.members.length - 2
        && left[0].data('label').includes(`${keyed.members.length - 2} more`),
      JSON.stringify({ rows: memberRows.length, members: keyed && keyed.members.length, left: left.length && left[0].data('label') }));
    const v = m.lumpView(s.view.layout, s.view.fold, seeds);
    const leading = chosen.filter((id) => v.behind(id) > 0);
    say('LM4 a node let out that leads further comes out folded: its own big lump, nothing behind it drawn',
      leading.length > 0 && leading.every((id) => lumpsOf(s, 'big').some((n) => n.data('owner') === id)),
      JSON.stringify({ leading: leading.length }));
    say('LM5 fold and two openings move neither the view nor any node already drawn',
      viewport(s) === view0 && stayed(new Map([...at0].filter(([id]) => at1.has(id))), s) && stayed(at1, s) && stayed(at2, s),
      JSON.stringify({ view: viewport(s) === view0 }));
    const ys = chosen.map((id) => s.view.cy.getElementById(id).position('y'));
    say('LM6 what came out stands where the lump stood, a row each, and the lump left goes under them',
      ys.length === 2 && ys[0] === lumpAt.y && ys[1] > ys[0] && left.length === 1 && left[0].position('y') > ys[1],
      JSON.stringify({ lumpAt, ys, left: left.length && left[0].position('y') }));
    // A lump of more than eight: a filter field; Cancel and Esc close without opening anything.
    const many = await seat([BUNDLES, EXPANDED]);
    const key = `${EXPANDED._expanded.node}|${EXPANDED._expanded.predicate}|${EXPANDED._expanded.direction}`;
    press(many, `lump:${key}`);
    await settle();
    const filter = pickerOf(many) && byClass(pickerOf(many), 'sg-pick-filter')[0];
    const total = rowsOf(many).length;
    const word = total ? String(rowsOf(many)[0].children[1].textContent) : '';
    if (filter) { filter.value = word; filter.dispatch('input', {}); }
    const shown = rowsOf(many).filter((r) => !r.hidden).length;
    const drawnBefore = nodesOf(many).length;
    const cancel = pickerOf(many) && byClass(pickerOf(many), 'sg-pick-cancel')[0];
    if (cancel) cancel.dispatch('click', {});
    const cancelled = !pickerOf(many) && nodesOf(many).length === drawnBefore;
    press(many, `lump:${key}`);
    await settle();
    const reopened = Boolean(pickerOf(many));
    many.doc.key('Escape');
    say('LM7 more than eight: a filter field that narrows the rows; Cancel and Esc close it with nothing opened',
      total > 8 && Boolean(filter) && shown >= 1 && shown < total && cancelled && reopened && !pickerOf(many)
        && nodesOf(many).length === drawnBefore,
      JSON.stringify({ total, filter: Boolean(filter), shown, cancelled, reopened, open: Boolean(pickerOf(many)) }));
    press(many, `lump:${key}`);
    await settle();
    tickAll(many);
    const ticked = rowsOf(many).filter((r) => r.children[0].checked).length;
    const go = (byClass(pickerOf(many) || { children: [] }, 'sg-pick-open')[0] || {}).textContent;
    say('LM8 All ticks every row, and the button says how many it will open',
      ticked === total && go === `Open ${total}`, JSON.stringify({ ticked, total, go }));
  }

  console.log('\n[TK] colours and sizes are the tokens\', in both themes');
  {
    const s = await seat([WAFER], { tokens: true });
    const wrong = nodesOf(s).filter((n) => n.style('background-color') !== hex(TOKENS.light[`--cat-${n.data('colour') + 1}`]));
    say('TK1 every node is filled with its type\'s palette token', nodesOf(s).length > 0 && wrong.length === 0,
      JSON.stringify({ wrong: wrong.length }));
    say('Q5 node names are drawn at the body size token, not the tag size',
      nodesOf(s).length > 0 && nodesOf(s).every((n) => n.style('font-size') === TOKENS.light['--fs-body']),
      String(nodesOf(s).length && nodesOf(s)[0].style('font-size')));
    s.doc.theme('dark');
    const dark = nodesOf(s).filter((n) => n.style('background-color') !== hex(TOKENS.dark[`--cat-${n.data('colour') + 1}`]));
    say('TK2 the site\'s theme toggle restyles the picture with the other theme\'s tokens', nodesOf(s).length > 0 && dark.length === 0,
      JSON.stringify({ wrong: dark.length }));
  }

  console.log('\n[V] the picture answers the pointer: neighbours lit, the picked node\'s lines bold, the tangle faint');
  {
    const s = die;
    const cy = s.view.cy;
    const target = nodesOf(s).sort((p, q) => q.degree() - p.degree())[0];
    if (target) target.emit('mouseover');
    const near = target ? target.closedNeighborhood() : null;
    const faded = cy ? cy.elements('.is-faded') : none;
    say('V1 a node under the pointer: everything but it and its neighbours fades',
      Boolean(near) && faded.length > 0 && faded.every((e) => !near.contains(e)) && near.every((e) => !e.hasClass('is-faded')),
      JSON.stringify({ faded: faded.length }));
    if (target) target.emit('mouseout');
    if (target) press(s, target.id());
    const hot = edgesOf(s).filter((e) => e.hasClass('is-hot'));
    say('V2 the picked node\'s lines are bold, and only those', Boolean(target) && hot.length === target.connectedEdges('[kind = "edge"]').length
      && hot.every((e) => e.data('source') === target.id() || e.data('target') === target.id()),
      JSON.stringify({ hot: hot.length }));
    const layerOf = new Map(s.view.layout.nodes.map((n) => [n.id, n.layer]));
    const sideways = s.view.layout.edges.filter((e) => Math.abs(layerOf.get(e.target) - layerOf.get(e.source)) !== 1).map((e) => e.id);
    const far = edgesOf(s).filter((e) => e.hasClass('is-far')).map((e) => e.id());
    say('V3 a line that runs sideways or back stands back; a line one column forward does not',
      sideways.length > 0 && JSON.stringify(far.sort()) === JSON.stringify(sideways.sort()),
      JSON.stringify({ sideways: sideways.length, far: far.length }));
    say('V4 the lines are curves', edgesOf(s).length > 0 && edgesOf(s).every((e) => e.style('curve-style') === 'unbundled-bezier'),
      String(edgesOf(s).length && edgesOf(s)[0].style('curve-style')));
    press(s, target ? target.id() : '');
    const fold = byClass(s.host, 'sg-fold')[0];
    if (fold) fold.dispatch('click', {});
    const reset = byClass(s.host, 'sg-reset')[0];
    if (reset) reset.dispatch('click', {});
    say('R1 Reset: back to the first picture - the same nodes and lumps, each where the first draw put it',
      Boolean(reset) && lumpsOf(s).map((n) => n.id()).sort().join(',') === dieFirstLumps
        && nodesOf(s).length === dieFirst.size && stayed(dieFirst, s),
      JSON.stringify({ lumps: lumpsOf(s).length, nodes: nodesOf(s).length, first: dieFirst.size }));
  }

  console.log('\n[Z] the first picture and Reset stop at the readable zoom; Fit goes below it (lead 10-07)');
  {
    // A box with a width is on the page, so the first draw fits. Headless the picture has a 1x1 viewport, so fitting
    // all of it always needs a zoom below the floor - Z2 shows that it did. The floor is the owner's readable size:
    // a 15px name drawn no smaller than 12px.
    const READABLE = 0.8;
    const doc = stubDoc(false);
    const make = doc.createElement.bind(doc);
    doc.createElement = (tag) => Object.assign(make(tag), { clientWidth: 640 });
    const s = await seat([DIE], { doc });
    const zoom = () => (s.view.cy ? s.view.cy.zoom() : NaN);
    const click = (cls) => { const b = byClass(s.host, cls)[0]; if (b) b.dispatch('click', {}); return zoom(); };
    const first = zoom();
    const fitted = click('sg-fit');
    const reset = click('sg-reset');
    say('Z1 the first picture stands at the readable zoom, not at what fitting all of it needs', first === READABLE,
      JSON.stringify({ first, fitted }));
    say('Z2 Fit fits all of it, below the readable zoom', fitted < READABLE, JSON.stringify({ fitted }));
    say('Z3 Reset fits as the first picture does', reset === READABLE, JSON.stringify({ reset }));
  }

  console.log('\n[Q] Mark is the one press that marks; the facts stay in sight (lead 9dc2a5695 ① ②)');
  {
    const s = await seat([DIE, STEP2]);
    openAll(s);
    const id = STEP2._marked;
    press(s, id);
    // A mutant may draw no Mark or no node: the cell then fails, it does not throw.
    const button = () => byClass(s.host, 'sg-mark')[0] || { getAttribute: () => null, className: '' };
    const isMarked = () => { const n = s.view.cy && s.view.cy.getElementById(id); return Boolean(n && n.nonempty() && n.hasClass('is-marked')); };
    const on = (b) => String(b.className).split(' ').includes('is-on');
    const off = button().getAttribute('aria-pressed') === 'false' && !on(button());
    mark(s.host);
    const marked = button().getAttribute('aria-pressed') === 'true' && on(button()) && isMarked();
    mark(s.host);
    const back = JSON.stringify(s.markings.entries('s1')) === '[]' && button().getAttribute('aria-pressed') === 'false' && !isMarked();
    say('Q1 Mark shows whether this node is marked, and pressing it again takes it out',
      Boolean(off) && Boolean(marked) && back, JSON.stringify({ off, marked, back }));
    const kids = (byClass(s.host, 'sg-facts')[0] || { children: [] }).children;
    const has = (n, cls) => String(n.className || '').split(/\s+/).includes(cls);
    say('Q2 Mark stands first, under the head, before any fact line',
      kids.length > 2 && has(kids[1], 'sg-facts-acts') && byClass(kids[1], 'sg-mark').length === 1
        && kids.slice(2).every((k) => has(k, 'sg-fact')),
      JSON.stringify(kids.map((k) => k.className)));
    // The page has no viewport here, so the cell reads the rule the page carries (WALK_CSS, imported).
    const rules = [...css.replace(/\/\*[\s\S]*?\*\//g, ' ').matchAll(/([^{}]+)\{([^}]*)\}/g)]
      .map((m2) => [m2[1].split(',').map((x) => x.trim()), m2[2]]);
    const ruled = (selector, prop) => rules.some(([sels, body]) => sels.includes(selector) && body.includes(prop));
    say('Q3 the facts box is pinned to the bottom of what scrolls the picture, capped, with its own scroll',
      ruled('.sg-facts', 'position: sticky') && ruled('.sg-facts', 'bottom: 0') && ruled('.sg-facts', 'overflow: auto')
        && ruled('.sg-facts', 'max-height'));
    say('Q4 nothing picked draws no box', ruled('.sg-facts:empty', 'display: none')
      && byClass((await seat([WAFER])).host, 'sg-facts').every((b) => b.children.length === 0));
    say('Q6 the picture is a box of the graph height token, panning inside itself',
      ruled('.sg-canvas-wrap', 'height: var(--graph-max-height)') && ruled('.sg-canvas-wrap', 'overflow: hidden'));
  }

  console.log('\n[W] several worlds read: under each attribute and each edge, a row per world that says it (leads ee0f66e7b, 4e1e49fe9)');
  {
    // As the server answers (351b23ef8, ec6874b28): a node's attributes_by_world beside its one value, an edge's by_world.
    const body = JSON.parse(JSON.stringify(WAFER));
    const touching = (id) => body.edges.filter((e) => e.source === id || e.target === id).length;
    // In the first picture: the start or its one step.
    const target = body.nodes.find((n) => n.depth <= 1 && touching(n.id) > 0);
    target.attributes = { grade: 'B' };
    target.attributes_by_world = { grade: [
      { world: 'default', value: 'A', occurred_at: null, source_who: 'src_a' },
      { world: 'w1', value: 'B', occurred_at: '2026-10-01T09:00:00', source_who: 'src_b' }] };
    for (const e of body.edges) e.by_world = [{ world: 'w1', claim_id: `${e.id}:w1`, occurred_at: null, source_who: 'src_e' }];
    const factsOf = async (worldChips) => {
      const s = await seat([body], { worldChips });
      press(s, target.id);
      const kids = (byClass(s.host, 'sg-facts')[0] || { children: [] }).children;
      const at = kids.findIndex((k) => k.className === 'sg-fact' && k.textContent === 'grade B');
      const under = [];
      for (let i = at + 1; at >= 0 && i < kids.length && kids[i].className === 'sg-fact sg-fact--world'; i += 1) {
        under.push(kids[i].children.map((c) => c.textContent));
      }
      const edgeRows = kids.filter((k) => k.className === 'sg-fact sg-fact--world'
        && (k.children[1] || {}).textContent === 'src_e').length;
      return { at, under, edgeRows };
    };
    const many = await factsOf(true);
    const one = await factsOf(false);
    say('W5 the attribute line, then a row per world: its chip, that world\'s own value, who and when',
      many.at >= 0 && JSON.stringify(many.under)
        === JSON.stringify([['default', 'A · src_a'], ['w1', 'B · src_b · 2026-10-01T09:00:00']]), JSON.stringify(many));
    say('W6 ...and each edge still its rows', many.edgeRows === touching(target.id), JSON.stringify(many));
    say('W7 one world read: the attribute line alone, no world rows', one.at >= 0 && one.under.length === 0
      && one.edgeRows === 0, JSON.stringify(one));
  }

  for (const view of seated) if (view.cy) view.cy.destroy();
  return { ran: names.length, names, failures: fails };
}

/** Cytoscape answers a colour as rgb(); the token is hex. */
function hex(value) {
  const h = String(value || '').replace('#', '');
  if (h.length !== 6) return value;
  return `rgb(${parseInt(h.slice(0, 2), 16)},${parseInt(h.slice(2, 4), 16)},${parseInt(h.slice(4, 6), 16)})`;
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
    M('M1', 'the column is not the node\'s depth', 'B1',
      '          layer: base + node.depth,\n', '          layer: base,\n'),
    M('M2', 'a static node is drawn as a circle', 'C1',
      "      { selector: 'node[kind = \"node\"][?static]', style: { shape: 'rectangle' } },\n", ''),
    M('M3', 'the part asks with a follow of its own', 'D1',
      '      fanout_limit: this.fanoutLimit, expand });\n',
      "      fanout_limit: this.fanoutLimit, expand, follow: ['inspected'] });\n"),
    M('M4', 'the edges are not drawn', 'A2',
      '    for (const e of view.edges) {\n      // A line one column forward', '    for (const e of []) {\n      // A line one column forward'),
    M('M5', 'a press does not change the facts', 'E1',
      '    this.selected = id;\n    this._swapFacts();', '    this._swapFacts();'),
    M('M6', 'a cut walk says nothing', 'F1',
      '    if (last.cut) cut.push(', '    if (false) cut.push('),
    M('M7', 'the part draws into the page, not its own mount', 'G1',
      '    this.mount.appendChild(this.root);\n', '    this.doc.body.appendChild(this.root);\n'),
    M('M8', 'a node without a depth is placed anyway', 'B3',
      '        if (!Number.isFinite(node.depth)) { unplaced += 1; continue; }\n', ''),
    M('M9', 'static chips lose their mark', 'H1',
      "      chip.appendChild(this._el('span', `sg-swatch${item.static ? ' is-static' : ''}`));\n",
      "      chip.appendChild(this._el('span', 'sg-swatch'));\n"),
    M('M10', 'a press still marks (owner 10-03: a press only picks)', 'K1',
      '  press(id) {\n    this.select(id);\n', '  press(id) {\n    this.select(id);\n    this.toggleMark(id);\n'),
    M('Q1m', 'Mark marks nothing', 'K1',
      '    if (name) this.markings.toggle(name, id, SIGN.CASE);\n', ''),
    M('Q2m', 'Mark does not show its state', 'Q1',
      "      this.markButton.setAttribute('aria-pressed', String(on));\n", ''),
    M('Q3m', 'Mark is live past the chain\'s end', 'L2',
      "      setDisabledReason(this.markButton, name ? '' : 'End of chain');\n", ''),
    M('Q4m', 'Mark stands after the facts', 'Q2',
      '    box.appendChild(acts);\n    for (const [name, value]', '    for (const [name, value]'),
    { ...M('Q5m', 'the facts box is not pinned', 'Q3',
      'position: sticky; bottom: 0; z-index: 1;', 'z-index: 1;'), file: STYLES },
    M('Q7m', 'node names back at the tag size', 'Q5',
      "'font-size': px('--fs-body', 15),", "'font-size': px('--fs-tag', 15),"),
    { ...M('Q6m', 'an empty facts box is drawn as a bar', 'Q4',
      '.sg-facts:empty { display: none; }\n', ''), file: STYLES },
    { ...M('Q8m', 'the picture box grows with the picture', 'Q6',
      '.sg-canvas-wrap { position: relative; height: var(--graph-max-height);', '.sg-canvas-wrap { position: relative;'), file: STYLES },
    M('M11', 'Continue walks the start again, not the marking', 'K2',
      '    if (!name || this.state !== \'done\') return;\n    await this._step(name);\n',
      '    if (!name || this.state !== \'done\') return;\n    await this._step(this.chain[0]);\n'),
    M('M12', 'a node reached again is moved to the later step', 'K4',
      '        if (at.has(node.id)) continue;\n',
      '        if (at.has(node.id)) placed.splice(placed.indexOf(at.get(node.id)), 1);\n'),
    M('M13', 'a later step starts at the first column', 'K4',
      '    const base = index === 0 || !seedLayers.length ? 0 : Math.max(...seedLayers);\n', '    const base = 0;\n'),
    M('M14', 'a node does not carry its step', 'K4', '          step: index + 1,\n', '          step: 1,\n'),
    M('M15', 'Continue is live with nothing marked', 'K2',
      "    setDisabledReason(this.continueButton, !name ? 'End of chain' : (this.markings.count(name) ? '' : 'Mark a node'));\n",
      "    setDisabledReason(this.continueButton, '');\n"),
    M('M16', 'another part writing the same name is not seen', 'L1',
      '    for (const name of this.chain) this.markings.subscribe(name, () => this._restyle());\n', ''),
    M('M17', 'the chain\'s end is not kept: a press past it writes a name of its own', 'L2',
      "  writes() { return this.chain[this.steps.length] || ''; }\n",
      "  writes() { return this.chain[this.steps.length] || 'extra'; }\n"),
    M('M18', 'every draw lays the whole picture out again', 'LM5',
      '    const full = this._relayout;\n', '    const full = true;\n'),
    M('B1', 'the part walks without its fan-out cap', 'D1',
      '      fanout_limit: this.fanoutLimit, expand });\n', '      expand });\n'),
    M('B2', 'the unsent lumps are not drawn', 'P1', '      } else if (chip) {\n', '      } else if (false) {\n'),
    M('B3', 'a lump pressed asks without its bundle', 'P2',
      '    const expand = [...step.expand, key];\n', '    const expand = [...step.expand];\n'),
    M('B4', 'a lump says its far type but not its count', 'P1',
      "  return `${arrowed(lump)}\\n${lump.count}${lump.more ? ' more' : ''} ${lump.farType}`;",
      '  return `${arrowed(lump)}\\n${lump.farType}`;'),
    M('B5', 'the unsent lumps come from a step\'s first answer, so a walked one stays', 'P4',
      '    return all[all.length - 1] || {};\n', '    return all[0] || {};\n'),
    M('B6', 'what a walked lump brings is drawn at once, not listed', 'P3',
      '      if (!this.fold.lumped.has(lump.key)) this.fold.lumped.set(lump.key, new Set());\n', ''),
    { ...M('B7', 'a walked lump still reads as unsent, and the walk does not guard what it expanded', 'P6'),
      mutate: (t) => swap(swap(t, 'more: lumped.get(key).size > 0, unsent: false });',
        'more: lumped.get(key).size > 0, unsent: true, step: 0 });'),
        '    if (!step || this.state !== \'done\' || step.expand.includes(key)) return;\n',
        '    if (!step || this.state !== \'done\') return;\n') },
    { ...M('W2', 'the wire drops the expand cells', 'P2',
      "  for (const key of expand || []) query.append('expand', String(key));\n", ''), file: WIRE },
    { ...M('W3', 'the wire drops the fan-out cap', 'D1',
      "  if (fanoutLimit !== undefined && fanoutLimit !== null) query.set('fanout_limit', String(fanoutLimit));\n", ''), file: WIRE },
    { ...M('W4', 'the wire does not carry the bundles', 'P1',
      '        bundles: Array.isArray(body.bundles) ? body.bundles : null,\n', '        bundles: null,\n'), file: WIRE },
    // The wire, widened for this order: a marking start rides as the board's walk sends it.
    { ...M('W1', 'the wire drops a marking start and asks by type and keys', 'D1',
      '        ...(marked ? { nodeId: positive[0], positive, negative }\n',
      '        ...(false ? { nodeId: positive[0], positive, negative }\n'), file: WIRE },
    M('F1', 'the fold walks from the seed ids only, not from every depth-0 node', 'N3',
      '  const starts = [...(seeds || []), ...layout.nodes.filter((n) => n.depth === 0).map((n) => n.id)]\n',
      '  const starts = [...(seeds || [])]\n'),
    M('F2', 'a same-depth edge is not walked', 'N1',
      '      if (!(layerOf.get(b) >= layerOf.get(a))) continue;\n', '      if (!(layerOf.get(b) > layerOf.get(a))) continue;\n'),
    M('F3', 'a folded node is walked past', 'N1',
      '(big.get(from) || new Set()).has(s.key)', 'false'),
    M('F4', 'a folded node keeps its own unsent fan-outs', 'N2',
      '  for (const chip of layout.chips || []) if (chip.node === id) keys.add(chip.key);\n', ''),
    M('F5', 'Unfold never opens', 'N7', '    if (this._isFolded(id)) {\n', '    if (false) {\n'),
    M('F6', 'the fold is shared by every part on the page', 'N5',
      '  return { big: new Map(), lumped: new Map() };\n',
      '  return (globalThis.__sgFold ||= { big: new Map(), lumped: new Map() });\n'),
    M('F7', 'the fold\'s lump is a shape of its own', 'N6',
      "      { selector: 'node[kind = \"lump\"][level = \"big\"]', style: set({ 'font-weight': 600, 'border-width': 2.5,",
      "      { selector: 'node[kind = \"lump\"][level = \"big\"]', style: set({ shape: 'ellipse', 'font-weight': 600, 'border-width': 2.5,"),
    M('F8', 'the folded count is not said', 'N4',
      "    if (view.hidden) this.head.appendChild(this._el('div', 'sg-note', `Folded · ${unitText(view.hidden, 'node')}`));\n", ''),
    M('F9', 'the picture draws the folded nodes anyway', 'N3',
      '    nodes: layout.nodes.filter((n) => shown(n.id)),\n', '    nodes: layout.nodes,\n'),
    M('L1m', 'opening a big lump opens every key, not the ticked', 'LM2',
      '        for (const key of keys) {\n          inBig.delete(key);', '        for (const key of lump.groups.map((g) => g.key)) {\n          inBig.delete(key);'),
    M('L2m', 'opening a small lump draws every member, not the ticked', 'LM3',
      '        for (const m of members) {\n          opened.add(m);', '        for (const m of lump.members) {\n          opened.add(m);'),
    M('L3m', 'a node let out comes out open', 'LM4',
      '          this.fold.big.set(m, branchKeys(this.layout, m));\n', ''),
    M('L4m', 'an opening fits the view', 'LM5',
      '    else this._place(view, added);\n', '    else { this._place(view, added); cy.zoom(cy.zoom() * 1.1); }\n'),
    M('L5m', 'the lump left is not moved under what came out', 'LM6',
      '      if (left.nonempty() && row) left.position(', '      if (false) left.position('),
    M('L6m', 'a long list has no filter field', 'LM7', '    if (items.length > PICK_FILTER_AT) {\n', '    if (false) {\n'),
    M('L7m', 'Esc does not close the picker', 'LM7',
      "    this._onKey = (ev) => { if (ev && ev.key === 'Escape') this._closePicker(); };\n", '    this._onKey = () => {};\n'),
    M('L8m', 'All ticks nothing', 'LM8',
      '      all.addEventListener(\'change\', () => { for (const r of rows) if (visible(r)) r.cb.checked = all.checked; sync(); });\n',
      '      all.addEventListener(\'change\', () => { sync(); });\n'),
    M('T1m', 'a type colour written by hand', 'TK1', "      const c = t(`--cat-${k + 1}`);\n", "      const c = '#888888';\n"),
    M('T2m', 'the theme toggle is not followed', 'TK2',
      "      this._themeWatch.observe(this.doc.documentElement, { attributes: true, attributeFilter: ['data-theme'] });\n", ''),
    M('V1m', 'the pointer lights nothing', 'V1', '      cy.elements().not(near).addClass(\'is-faded\');\n', ''),
    M('V2m', 'the picked node\'s lines stay thin', 'V2',
      "          e.toggleClass('is-hot', Boolean(this.selected) && (e.data('source') === this.selected || e.data('target') === this.selected));\n",
      "          e.toggleClass('is-hot', false);\n"),
    M('V3m', 'the tangle is drawn like the walk\'s own steps', 'V3', "classes: forward ? '' : 'is-far' });", "classes: '' });"),
    M('V4m', 'the lines are straight', 'V4', "'target-arrow-shape': 'triangle', 'arrow-scale': 0.7, 'curve-style': 'unbundled-bezier',",
      "'target-arrow-shape': 'triangle', 'arrow-scale': 0.7, 'curve-style': 'straight',"),
    M('L9m', 'every lump is one size whatever it holds', 'LM9',
      "        width: (n) => 136 + Math.min(68, Math.sqrt(n.data('count')) * 13.6),\n", '        width: 136,\n'),
    M('R1m', 'Reset opens everything instead of giving the first picture back', 'R1',
      '    this.fold = this._firstFold();\n', '    this.fold = openFold();\n'),
    M('S1m', 'the first picture draws the whole walk', 'A5',
      '      if (fresh) foldBeyond(this.layout, this.fold, startsOf(this.steps[this.steps.length - 1]), before);\n', ''),
    M('S2m', 'a seed\'s twins are not where the step stood', 'A5',
      '  return [...new Set([...((step && step.seeds) || []), ...twins])];\n', '  return [...((step && step.seeds) || [])];\n'),
    M('F10', 'a folded point stays folded', 'N9', '    fold.big.delete(s);\n', ''),
    M('F11', 'a new node one step on comes out open', 'A5', '      fold.big.set(id, new Set(out.map((x) => x.key)));\n', ''),
    M('S6m', 'what a Continue brings past a node already in sight is drawn at once', 'K7',
      '        fold.lumped.set(step.key, new Set(out.filter((x) => x.key === step.key && before.has(x.to)).map((x) => x.to)));\n', ''),
    M('S4m', 'a Continue takes nothing as already in sight', 'K8',
      '    const before = fresh && this.layout ? new Set(this._view().nodes.map((n) => n.id)) : new Set();\n',
      '    const before = new Set();\n'),
    M('S5m', 'the first picture folds the unsent fan-outs too', 'P1',
      '      fold.big.set(id, new Set(out.map((x) => x.key)));\n',
      '      fold.big.set(id, branchKeys(layout, id));\n'),
    M('A1m', 'an attribute gets no world rows', 'W5',
      '      this._worldRows(box, facts.node.attributesByWorld[name], (said) => [said.value, said.source_who, said.occurred_at]);\n', ''),
    M('A2m', 'each world row repeats the one value', 'W5',
      '(said) => [said.value, said.source_who, said.occurred_at]', '(said) => [value, said.source_who, said.occurred_at]'),
    M('A3m', 'an edge gets no world rows', 'W6',
      '      this._worldRows(box, edge.byWorld, (said) => [said.source_who, said.occurred_at]);\n', ''),
    M('A4m', 'the world rows are drawn whatever the walk reads', 'W7',
      '    if (!this.worldChips) return;\n', ''),
    M('Z1m', 'the first fit has no floor (lead 10-07)', 'Z1', '    if (cy.zoom() >= READABLE_ZOOM) return;\n', '    return;\n'),
    M('Z2m', 'Fit keeps the floor', 'Z2', 'if (this.cy) this.cy.fit(undefined, GEOMETRY.fitPad);', 'if (this.cy) this._firstFit();'),
    M('Z3m', 'the first draw is not fitted', 'Z1', '    if (full) this._fitPending = true;\n', ''),
  ];
  const scored = await scoreMutants(MUTANTS, async (mu) => {
    const mutate = mu.mutate || ((t) => swap(t, mu.from, mu.to));
    const loaded = (await loadWithProbe(mu.file || SUBJECT, { mutate })).module;
    const quiet = console.log;
    console.log = () => {};
    try {
      if (mu.file === STYLES) return await suite(real, createWalkBoxWalk, loaded.WALK_CSS);
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
