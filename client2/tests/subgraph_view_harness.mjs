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
// Run: node client2/tests/subgraph_view_harness.mjs [--control]
// A mutant runs only the blocks holding the check it names (lead 10-09). --control runs each mutant's blocks on the
// unmutated part as well, and every one must be green: a block that leans on one skipped would otherwise redden a
// named check with no mutant. The narrow gate of a commit that edits this file passes it, and the runner does.
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { makeDoc, byClass, flush } from './lib/board_dom.mjs';
import { createWalkBoxWalk, entitySeedId } from '../src/rnd_board/api.js';
import { MarkingStore, SIGN } from '../src/rnd_board/marking_store.js';
import { walkTableView } from '../src/walk/table_view.js';
import { LOADING } from '../src/ui_words.js';
import { STEP_NODE_LIMIT } from '../src/walk/fold_views.js';
import { walkableRoutes } from '../src/walk/derive.js';
import { pathKinds } from '../src/walk/paths.js';

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
// A die walk whose wafer, one step out, holds two fan-outs over the cap (first 20 drawn), and the first opened: one
// step from the wafer (capture_walk_bundles.py, real server, lead 11e5ea207).
const BUNDLES = fx('walk_bundles_die.json');
const OPENED = fx('walk_bundles_die_opened.json');
const OPEN_KEY = `${OPENED._opened.node}|${OPENED._opened.predicate}|${OPENED._opened.direction}`;
// The wafer's other bundle (inspected, out) holds the same 40 dies (lead 2f25c883a: branches overlap): one answer with
// both bundles' edges, so whichever is walked first, each is answered.
const OPENED_BOTH = { ...OPENED, edges: [...OPENED.edges, ...OPENED.edges.map((e) => ({ ...e, id: `${e.id}~inspected`,
  source: e.target, target: e.source, predicate: 'inspected', predicate_label: 'inspected', original_predicate: 'inspected' }))] };
// The implementer's captures of the folded lumps' walks (real server, PostgreSQL): the start wafer, the recipe's one
// more step (lead 793017c62 · edcc0568c).
const FOLD_WAFER = fx('walk_fold_wafer.json');
const FOLD_STEP = fx('walk_fold_recipe_step.json');
const FOLD_PROCESS = fx('walk_fold_process_lump.json');
// The declaration those captures were walked under, captured in the same run (implementer 5201b22c5). A hand-built
// one drifts from the server's in silence (lead).
const FOLD_DECL = fx('walk_fold_declaration.json');
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

async function suite(m, makeWalk = createWalkBoxWalk, css = REAL_CSS, foldDecl = FOLD_DECL, only = null) {
  // A mutant names the check it must break; only the blocks holding that check run for it (lead 10-09).
  const asked = only == null ? null : [].concat(only).map(String);
  const want = (ids) => !asked || ids.some((id) => asked.some((c) => id.startsWith(c)));
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
      worldChips: opts.worldChips, declaration: () => opts.declaration || null, storage: opts.storage });
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
  // A big lump's window (lead df11f9e81): a row a branch; its ▸ lists the branch's nodes, each a row of its own.
  const branchRows = (s) => rowsOf(s).filter((r) => !r.className.includes('is-member'));
  const nodeRows = (s, key) => rowsOf(s).filter((r) => r.className.includes('is-member') && String(r.attrs['data-value']).startsWith(`${key}\u0000`));
  const unfoldRow = (s, key) => {
    const b = byClass(pickerOf(s) || { children: [] }, 'sg-pick-unfold').find((x) => x.attrs['data-value'] === key);
    if (b) b.dispatch('click', {});
    return Boolean(b);
  };
  /** A big lump's branch seen from its row's Trend: no small lump between (lead df11f9e81). `before` runs first. */
  const branchTrend = async (s, bigId, part, before) => {
    press(s, bigId);
    if (before) before(s);
    const b = byClass(pickerOf(s) || { children: [] }, 'sg-pick-view')
      .find((x) => x.textContent === 'Trend' && String(x.attrs['data-value']).includes(part));
    if (b) b.dispatch('click', {});
    await settle();
    return b ? `branch:${b.attrs['data-value']}` : '';
  };
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
  if (want(["A5"])) {
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
  if (want(["B1", "B2", "B3"])) {
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
  if (want(["C1"])) {
    const s = die;
    const typeOf = (n) => String(n.data('type')).split('@')[0];
    const wrong = nodesOf(s).filter((n) => (STATIC.has(typeOf(n)) ? 'rectangle' : 'ellipse') !== n.style('shape'));
    const statics = nodesOf(s).filter((n) => STATIC.has(typeOf(n))).length;
    say('C1 static nodes are squares, the rest circles', statics > 0 && wrong.length === 0,
      JSON.stringify({ statics, wrong: wrong.length }));
  }

  console.log('\n[4] the part asks its marking and nothing else');
  if (want(["D1"])) {
    const { urls } = die;
    const params = paramsOf(urls[0] || '');
    const extra = [...params.keys()].filter((k) => k !== 'id' && k !== 'positive' && k !== 'fanout_limit');
    say('D1 one request: the start marking (id and positive, its one node) and the declared fan-out cap, nothing else',
      urls.length === 1 && params.get('id') === startId(DIE) && params.get('fanout_limit') === '20'
        && JSON.stringify(params.getAll('positive')) === JSON.stringify([startId(DIE)]) && extra.length === 0,
      JSON.stringify({ urls: urls.length, extra }));
  }

  console.log('\n[5] a node pressed shows its facts');
  if (want(["E1", "E2"])) {
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

  console.log('\n[EQ] a picked node\'s lines say their qualifiers - on the label and in the info box (lead 3181313b5)');
  if (want(["EQ1", "EQ2", "EQ3"])) {
    // The captured bundle walk, every fold opened so the lines are drawn: a node that touches lines with qualifiers and without.
    const s = await seat([BUNDLES]);
    openAll(s);
    const has = (e) => Boolean(e.qualifiers) && Object.keys(e.qualifiers).length > 0;
    const touching = (id) => BUNDLES.edges.filter((e) => e.source === id || e.target === id);
    const target = BUNDLES.nodes.find((n) => touching(n.id).some(has) && touching(n.id).some((e) => !has(e)));
    if (target) press(s, target.id);
    const raw = new Map(BUNDLES.edges.map((e) => [e.id, e]));
    const name = (e) => e.predicate_label || e.predicate;
    const words = (q) => Object.entries(q || {}).map(([k, v]) => `${k} ${v}`);
    const want = (e) => {
      const w = words(e.qualifiers);
      return [name(e), ...(w.length > 2 ? [...w.slice(0, 2), `+${w.length - 2}`] : w)].join(' · ');
    };
    const hot = edgesOf(s).filter((e) => e.hasClass('is-hot'));
    const qual = hot.filter((h) => has(raw.get(h.id())));
    const bare = hot.filter((h) => !has(raw.get(h.id())));
    say('EQ1 a line with qualifiers is labelled its predicate, its first two and +N, and the label is drawn',
      Boolean(target) && qual.length > 0 && qual.some((h) => /\+\d+$/.test(h.data('tag')))
        && qual.every((h) => h.data('tag') === want(raw.get(h.id())) && h.style('label') === h.data('tag')),
      JSON.stringify(qual.map((h) => [h.data('tag'), h.style('label')]).slice(0, 2)));
    say('EQ2 a line with none is labelled its predicate alone',
      bare.length > 0 && bare.every((h) => h.data('tag') === name(raw.get(h.id())) && h.style('label') === h.data('tag')),
      JSON.stringify(bare.map((h) => h.data('tag'))));
    const labelOf = new Map(BUNDLES.nodes.map((n) => [n.id, n.label || n.id]));
    const lineOf = (e) => [`${e.source === target.id ? '→' : '←'} ${name(e)}`,
      labelOf.get(e.source === target.id ? e.target : e.source), ...(e.occurred_at ? [e.occurred_at] : []),
      ...words(e.qualifiers)].join(' · ');
    const lines = textOf(s.host, 'sg-fact');
    say('EQ3 the info box gives every qualifier of every line, as sent; a line with none, none',
      Boolean(target) && touching(target.id).every((e) => lines.includes(lineOf(e))),
      JSON.stringify(touching(target ? target.id : '').map(lineOf).filter((l) => !lines.includes(l)).slice(0, 2)));
  }

  console.log('\n[6] a cut walk says so, in one line');
  if (want(["F1"])) {
    const wafer = await seat([WAFER]);
    say('F1 the die walk: Truncated with its budget; the wafer walk: no line',
      JSON.stringify(textOf(die.host, 'sg-trunc')) === '["Truncated · nodes 400"]'
        && textOf(wafer.host, 'sg-trunc').length === 0,
      JSON.stringify([textOf(die.host, 'sg-trunc'), textOf(wafer.host, 'sg-trunc')]));
  }

  console.log('\n[7] two on one page with their own markings do not touch each other');
  if (want(["G1"])) {
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
  if (want(["H1"])) {
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
  if (want(["K1", "K2", "K3", "K4", "K5", "K6", "K7", "K8"])) {
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
  if (want(["L1", "L2"])) {
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

  console.log('\n[11] bundles: a fan-out over the cap draws its first, the rest is an unsent lump; pressed, it is one step from its node, then listed');
  if (want(["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9", "PB", "PC", "PD", "PL", "PN"])) {
    const doc = stubDoc();
    const markings = new MarkingStore();
    const a = await seat([BUNDLES, OPENED], { doc, markings, chain: ['a0', 'a1'] });
    const b = await seat([BUNDLES], { doc, markings, chain: ['b0', 'b1'] });
    // Every fold opened, so each bundle's lump stands on its own beside what the walk drew of it.
    openAll(a);
    const unsent = (s) => lumpsOf(s).filter((n) => n.data('unsent'));
    const keyOf = (x) => `${x.node}|${x.predicate}|${x.direction}`;
    const rest = (x) => x.count - x.drawn;
    const words = (x) => `${x.direction === 'incoming' ? `← ${x.predicate}` : `${x.predicate} →`}\n+${rest(x)} more ${x.far_type}`;
    const want = BUNDLES.bundles.map(words).sort();
    const got = unsent(a).map((n) => n.data('label')).sort();
    say('P1 one unsent lump per bundle: its predicate, +what the walk did not draw more, its far type; it counts that rest, dashed',
      want.length > 1 && BUNDLES.bundles.every((x) => x.drawn > 0 && x.drawn < x.count)
        && JSON.stringify(got) === JSON.stringify(want) && unsent(a).every((n) => n.style('border-style') === 'dashed')
        && BUNDLES.bundles.every((x) => a.view.cy.getElementById(`lump:${keyOf(x)}`).data('count') === rest(x)),
      JSON.stringify({ got, want }));
    const first = OPENED._opened;
    const key = OPEN_KEY;
    a.urls.length = 0;
    const bBefore = b.urls.length;
    const shownBefore = new Set(nodesOf(a).map((n) => n.id()));
    const pressed = press(a, `lump:${key}`);
    await settle();
    const params = paramsOf(a.urls[0] || '');
    say('P2 pressed, it asks one step from the bundle\'s node along its predicate, its direction, to its far type - no cap, no expand; the other part asks nothing',
      pressed && a.urls.length === 1 && params.get('id') === first.node
        && JSON.stringify(params.getAll('positive')) === JSON.stringify([first.node])
        && JSON.stringify(params.getAll('follow')) === JSON.stringify([first.predicate])
        && JSON.stringify(params.getAll('collect')) === JSON.stringify([first.far_type])
        && params.get('direction') === first.direction && params.get('hops') === '1'
        && !params.has('fanout_limit') && params.getAll('expand').length === 0 && b.urls.length === bBefore,
      JSON.stringify({ pressed, urls: a.urls.length, asked: [...params.entries()], b: b.urls.length - bBefore }));
    const fanEnds = new Set(OPENED.nodes.map((n) => n.id).filter((id) => id !== first.node));
    const listed = rowsOf(a).map((r) => r.attrs['data-value']);
    const lump = a.view.cy.getElementById(`lump:${key}`);
    say('P3 then lists what the step brought that is not in sight - the bundle\'s rest; what the walk drew of it stays drawn',
      listed.length === rest(first) && listed.length === [...fanEnds].filter((id) => !shownBefore.has(id)).length
        && lump.nonempty() && lump.data('count') === listed.length && !lump.data('unsent')
        && listed.every((id) => !shownBefore.has(id)) && [...shownBefore].every((id) => a.view.cy.getElementById(id).nonempty()),
      JSON.stringify({ listed: listed.length, rest: rest(first), fan: fanEnds.size, count: lump.nonempty() && lump.data('count') }));
    tickAll(a);
    openTicked(a);
    const drawnIds = nodesOf(a).map((n) => n.id());
    const drawnEdges = new Set(edgesOf(a).map((e) => e.id()));
    say('P4 All, opened: the bundle\'s whole count drawn once, every line of the step drawn; its lump is gone and no unsent lump keeps its key',
      new Set(drawnIds).size === drawnIds.length && fanEnds.size === first.count && [...fanEnds].every((id) => drawnIds.includes(id))
        && OPENED.edges.length > 0 && OPENED.edges.every((e) => drawnEdges.has(e.id))
        && a.view.cy.getElementById(`lump:${key}`).empty() && !unsent(a).some((n) => n.data('key') === key),
      JSON.stringify({ drawn: drawnIds.length, fan: fanEnds.size, count: first.count,
        left: a.view.cy.getElementById(`lump:${key}`).length }));
    const others = BUNDLES.bundles.filter((x) => keyOf(x) !== key);
    const bundleLumps = unsent(a).filter((n) => n.data('level') !== 'big');
    say('P7 the node\'s other bundle stays as it was: its lump, +its rest more',
      others.length > 0 && JSON.stringify(bundleLumps.map((n) => n.data('label')).sort()) === JSON.stringify(others.map(words).sort()),
      JSON.stringify(bundleLumps.map((n) => n.data('label'))));
    const layerOf = new Map(a.view.layout.nodes.map((n) => [n.id, n.layer]));
    const firstIds = new Set(BUNDLES.nodes.map((n) => n.id));
    const brought = [...fanEnds].filter((id) => !firstIds.has(id));
    say('P8 what the step brought stands one column on from the bundle\'s node, beside what the walk drew of it; its lines run one column',
      brought.length === rest(first) && brought.every((id) => layerOf.get(id) === layerOf.get(first.node) + 1)
        && [...fanEnds].filter((id) => firstIds.has(id) && id !== startId(BUNDLES)).every((id) => layerOf.get(id) === layerOf.get(first.node) + 1)
        && edgesOf(a).filter((e) => brought.includes(e.data('source')) || brought.includes(e.data('target'))).every((e) => !e.hasClass('is-far')),
      JSON.stringify({ brought: brought.length, layers: [...new Set(brought.map((id) => layerOf.get(id)))], node: layerOf.get(first.node) }));
    const inside = nodesOf(a).find((n) => !firstIds.has(n.id()));
    if (inside) press(a, inside.id());
    mark(a.host);
    say('P5 a point inside the opened bundle can be marked for Continue',
      Boolean(inside) && JSON.stringify(markings.entries('a1')) === JSON.stringify([[inside.id(), SIGN.CASE]]),
      JSON.stringify(markings.entries('a1')));
    // A lump already opened: one ticked out of it, then pressed again.
    const c = await seat([BUNDLES, OPENED]);
    openAll(c);
    press(c, `lump:${key}`);
    await settle();
    const total = rowsOf(c).length;
    if (rowsOf(c)[0]) tickRow(rowsOf(c)[0]);
    openTicked(c);
    const asked = c.urls.length;
    press(c, `lump:${key}`);
    await settle();
    const again = c.view.cy.getElementById(`lump:${key}`);
    say('P6 a lump already opened keeps the rest - n more - and, pressed again, lists them and asks nothing',
      total > 1 && c.urls.length === asked && rowsOf(c).length === total - 1 && again.nonempty()
        && again.data('label').includes(`${total - 1} more`),
      JSON.stringify({ total, rows: rowsOf(c).length, asked: c.urls.length - asked, label: again.nonempty() && again.data('label') }));
    // The first picture: the bundle's node is one step out, so its branches - the bundles with what they drew - are
    // its one big lump. A bundle ticked out of it holds what the walk drew and the rest; nothing comes into sight.
    const d = await seat([BUNDLES, OPENED]);
    const bigLump = d.view.cy.getElementById(`big:${first.node}`);
    if (bigLump.nonempty()) press(d, bigLump.id());
    const row = rowsOf(d).find((r) => r.attrs['data-value'] === key);
    const sightBefore = new Set(nodesOf(d).map((n) => n.id()));
    const drewOf = BUNDLES.edges.filter((e) => e.predicate === first.predicate
      && (first.direction === 'outgoing' ? e.source === first.node : e.target === first.node))
      .map((e) => (first.direction === 'outgoing' ? e.target : e.source));
    const hiddenDrew = [...new Set(drewOf)].filter((id) => !sightBefore.has(id)).length;
    const rowCount = row ? Number(textOf(row, 'sg-pick-n').join()) : NaN;
    d.urls.length = 0;
    unfoldRow(d, key);
    await settle();
    const underIt = nodeRows(d, key);
    say('PB in a big lump a bundle\'s row counts what the walk drew and its rest; its ▸ walks it, nothing comes into sight, and the window lists them under it (lead df11f9e81)',
      Boolean(row) && hiddenDrew > 0 && rowCount === hiddenDrew + rest(first)
        && JSON.stringify([...sightBefore].sort()) === JSON.stringify(nodesOf(d).map((n) => n.id()).filter((id) => sightBefore.has(id)).sort())
        && d.urls.length === 1 && paramsOf(d.urls[0]).get('direction') === first.direction
        && underIt.length === [...fanEnds].filter((id) => !sightBefore.has(id)).length && underIt.every((r) => !r.hidden),
      JSON.stringify({ row: Boolean(row), hiddenDrew, rowCount, rest: rest(first), urls: d.urls.length, listed: underIt.length }));
    // The same branch ticked, not unfolded: walked, its row loading meanwhile, then back with all it brought ticked.
    const t = await seat([BUNDLES, OPENED]);
    const bigT = t.view.cy.getElementById(`big:${first.node}`);
    if (bigT.nonempty()) press(t, bigT.id());
    const rowT = rowsOf(t).find((r) => r.attrs['data-value'] === key);
    t.urls.length = 0;
    if (rowT) tickRow(rowT);
    const unfoldT = rowT && rowT.children.find((c) => String(c.className).includes('sg-pick-unfold'));
    const whileT = { row: Boolean(rowT) && rowT.className.includes('is-loading'), word: unfoldT && unfoldT.textContent };
    await settle();
    const kidsT = nodeRows(t, key);
    const goT = (byClass(pickerOf(t) || { children: [] }, 'sg-pick-open')[0] || {}).textContent;
    say('PL a branch not sent, ticked in the window: walked once, its row says Loading till the window is back, then its nodes come ticked (lead df11f9e81)',
      whileT.row && whileT.word === LOADING && t.urls.length === 1 && kidsT.length > 0
        && kidsT.every((r) => r.children[0].checked && !r.hidden) && goT === `Open ${kidsT.length}`,
      JSON.stringify({ whileT, urls: t.urls.length, kids: kidsT.length, goT }));
    // An opening that brings nothing new: said in a sentence, nothing listed.
    const e = await seat([BUNDLES, { ...OPENED, nodes: [], edges: [] }]);
    openAll(e);
    press(e, `lump:${key}`);
    await settle();
    say('PN an opening that brings nothing new says so, and lists nothing',
      textOf(e.host, 'sg-note').includes(`No more ${first.far_type} · ${first.direction === 'incoming' ? `← ${first.predicate}` : `${first.predicate} →`}`)
        && !pickerOf(e) && e.view.cy.getElementById(`lump:${key}`).empty(),
      JSON.stringify({ notes: textOf(e.host, 'sg-note'), picker: Boolean(pickerOf(e)) }));
    // A hand walk whose bundle's drawn ones are reached through that bundle alone - the wafer's are also reached by
    // its other bundle, so the real walk cannot tell whether an opening keeps them drawn.
    const hn = (id, depth) => ({ id, type: 'die', label: id, depth, keys: {} });
    const he = (source, target) => ({ id: `${source}>${target}`, source, target, predicate: 'p' });
    const only = (nodes, edges, more = {}) => ({ state: 'ready', seed: { id: 'h:s' }, nodes, edges, truncated: { reason: null }, ...more });
    const h = await seat([
      only([hn('h:s', 0), hn('h:w', 1), hn('h:a', 2), hn('h:b', 2)], [he('h:s', 'h:w'), he('h:w', 'h:a'), he('h:w', 'h:b')],
        { bundles: [{ node: 'h:w', predicate: 'p', direction: 'outgoing', far_type: 'die', count: 4, drawn: 2 }] }),
      only(['h:a', 'h:b', 'h:c', 'h:d'].map((id) => hn(id, 1)), ['h:a', 'h:b', 'h:c', 'h:d'].map((id) => he('h:w', id)))]);
    openAll(h);
    const hLabel = (h.view.cy.getElementById('lump:h:w|p|outgoing').nonempty() && h.view.cy.getElementById('lump:h:w|p|outgoing').data('label'));
    press(h, 'lump:h:w|p|outgoing');
    await settle();
    say('PD opened, what the walk drew of a bundle stays drawn and only the rest is listed',
      hLabel === 'p →\n+2 more die' && JSON.stringify(rowsOf(h).map((r) => r.attrs['data-value']).sort()) === '["h:c","h:d"]'
        && ['h:a', 'h:b'].every((id) => h.view.cy.getElementById(id).nonempty()),
      JSON.stringify({ hLabel, rows: rowsOf(h).map((r) => r.attrs['data-value']) }));
    // Hand steps: an opened answer's node at depth 0 is not where the step stood, and its cut is said.
    const hand = { seeds: ['s'], results: [
      { nodes: [{ id: 's', type: 't', depth: 0 }, { id: 'w', type: 't', depth: 1 }], edges: [{ id: 'sw', source: 's', target: 'w', predicate: 'p' }],
        bundles: [{ node: 'w', predicate: 'p', direction: 'outgoing', far_type: 't', count: 30, drawn: 20 },
          { node: 'w', predicate: 'q', direction: 'outgoing', far_type: 't', count: 30, drawn: 20 }] },
      { opened: 'w|p|outgoing', nodes: [{ id: 'w', type: 't', depth: 0 }, { id: 'x', type: 't', depth: 1 }],
        edges: [{ id: 'wx', source: 'w', target: 'x', predicate: 'p' }], cut: true, truncatedAxes: ['nodes'], limits: { nodes: 400 } }] };
    const handLayout = m.subgraphLayout([hand], ENTITIES);
    say('P9 where a step stood is its marking and its walk\'s depth 0, not an opened bundle\'s node',
      JSON.stringify(m.startsOf(hand)) === JSON.stringify(['s']), JSON.stringify(m.startsOf(hand)));
    say('PC an opened bundle\'s chip is gone, the other stays; a cut opening is said like a cut walk',
      JSON.stringify(handLayout.chips.map((c2) => c2.key)) === JSON.stringify(['w|q|outgoing'])
        && JSON.stringify(handLayout.cut) === JSON.stringify([{ step: 1, budgets: ['nodes 400'] }]),
      JSON.stringify({ chips: handLayout.chips.map((c2) => c2.key), cut: handLayout.cut }));
  }

  console.log('\n[N] a node folds its branches into one lump, on the picture only (lead 43a738d58 ③ · e523cfe91)');
  if (want(["N1", "N2", "N3", "N4", "N5", "N6", "N7", "N8", "N9", "NF"])) {
    // A hand graph: s -> a -> b -> c and s -> d -> c. Folding a hides b; c is reached through d.
    // And s -> e at the same depth (a real walk's depth stays put along some edges), f -> e one deeper.
    // No depth: the fold walks from the seed alone here, so a same-depth edge is the only way to e.
    const node = (id, layer) => ({ id, layer, type: 't' });
    const edge = (source, target) => ({ id: `${source}${target}`, source, target, predicate: 'p', predicateName: 'p' });
    const chip = (n) => ({ node: n, predicate: 'q', direction: 'outgoing', farType: 'x', count: 2, drawn: 0, step: 0, key: `${n}|q|outgoing` });
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
    const firstFold = m.foldBeyond(hand, m.openFold(), ['s'], new Set());
    const fv0 = m.lumpView(hand, firstFold, ['s']);
    say('NF the first picture folds what lies behind a node one step out, but a fan-out the walk drew none of stays its own lump',
      firstFold.big.has('a') && !firstFold.big.get('a').has('a|q|outgoing')
        && fv0.lumps.some((l) => l.unsent && l.owner === 'a' && l.key === 'a|q|outgoing'),
      JSON.stringify(fv0.lumps.map((l) => [l.id, l.count])));

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
    const said = m.lumpView(a.view.layout, a.view.fold, seeds).lumps.find((l) => l.level === 'big' && l.owner === target.id) || {};
    say('N3 Fold branches hides exactly what the fold reaches, and one big lump says N next · M behind where the branches were, the two its whole',
      target.hides > 0 && Boolean(fold) && nodesOf(a).length === a.view.layout.nodes.length - target.hides
        && big.length === 1 && big[0].data('owner') === target.id && said.next + said.behind === target.hides
        && big[0].data('label').startsWith(`${said.next} next · ${said.behind} behind`),
      JSON.stringify({ hides: target.hides, drawn: nodesOf(a).length, all: a.view.layout.nodes.length, lump: big.length && big[0].data('label') }));
    say('N4 the counts above stay the walk\'s; the folded count is its own line',
      counts() === countsBefore && textOf(a.host, 'sg-note').includes(`Folded · ${target.hides} node${target.hides === 1 ? '' : 's'}`),
      JSON.stringify({ before: countsBefore, after: counts(), notes: textOf(a.host, 'sg-note') }));
    b.view.render();
    say('N5 the other part on the page, the same walk, folds nothing: drawn again, its picture is what it was',
      nodesOf(b).length > 0 && JSON.stringify([nodesOf(b).map((n) => n.id()).sort(), lumpsOf(b).map((n) => n.id()).sort()]) === bWas,
      String(nodesOf(b).length));
    const sent = await seat([BUNDLES]);
    openAll(sent);
    const unsentLump = lumpsOf(sent).filter((n) => n.data('unsent'))[0];
    say('N6 both lumps are one lump: the fold\'s and the unsent fan-out\'s share the kind and the shape, each saying its count',
      Boolean(unsentLump) && big.length === 1 && unsentLump.data('kind') === big[0].data('kind')
        && unsentLump.style('shape') === big[0].style('shape')
        && /^\d+ next · \d+ behind/.test(big[0].data('label')) && /\n\+\d+ more \S+$/.test(unsentLump.data('label')),
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
  if (want(["LM1", "LM2", "LM3", "LM4", "LM5", "LM6", "LM7", "LM8", "LM9", "LM10", "LM11", "LM12", "LM13", "LM14"])) {
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
    const lumpAt = bigs[0] ? { ...bigs[0].position() } : { x: NaN, y: NaN };
    if (bigs[0]) press(s, bigs[0].id());
    const keyRows = branchRows(s);
    const said = (r) => [textOf(r, 'sg-pick-n').join(), textOf(r, 'sg-pick-behind').join()];
    const keyRow = keyRows.find((r) => keyed && r.attrs['data-value'] === keyed.key);
    // The branch's ▸: its nodes, two of them ticked.
    unfoldRow(s, keyed ? keyed.key : '');
    const memberRows = nodeRows(s, keyed ? keyed.key : '');
    const chosen = memberRows.slice(0, 2).map((r) => String(r.attrs['data-value']).split('\u0000')[1]);
    for (const r of memberRows.slice(0, 2)) tickRow(r);
    const goWord = (byClass(pickerOf(s) || { children: [] }, 'sg-pick-open')[0] || {}).textContent;
    const at2 = positions(s);
    openTicked(s);
    const drawn = new Set(nodesOf(s).map((n) => n.id()));
    const left = lumpsOf(s, 'small').filter((n) => n.data('key') === (keyed && keyed.key));
    const stillBig = lumpsOf(s, 'big').filter((n) => n.data('owner') === (pick && pick.id));
    const stood = { left: left.length ? left[0].position('y') : NaN, big: stillBig.length ? stillBig[0].position('y') : NaN };
    const v0 = m.lumpView(s.view.layout, s.view.fold, seeds);
    say('LM2 the big lump lists one row per branch, its one-step count only (34b4cebd0: no «+N behind», branches overlap behind); a branch\'s ▸ lists its nodes (lead df11f9e81)',
      Boolean(keyed) && keyRows.length === pick.groups.length && Boolean(keyRow)
        && JSON.stringify(said(keyRow)) === JSON.stringify([String(keyed.count), ''])
        && memberRows.length === keyed.members.length && memberRows.every((r) => !r.hidden),
      JSON.stringify({ rows: keyRows.length, keys: pick && pick.groups.length, said: keyRow && said(keyRow), members: memberRows.length }));
    say('LM3 only the two nodes ticked come out, with one Open; the branch keeps the rest and says n more; the other branches stay in the big one',
      Boolean(keyed) && goWord === 'Open 2' && chosen.every((id) => drawn.has(id))
        && keyed.members.filter((id) => !chosen.includes(id)).every((id) => !drawn.has(id))
        && left.length === 1 && left[0].data('count') === keyed.members.length - 2
        && left[0].data('label').includes(`${keyed.members.length - 2} more`) && stillBig.length === 1,
      JSON.stringify({ goWord, left: left.length && left[0].data('label'), big: stillBig.length }));
    const [fuller, lighter] = stillBig.length && left.length && stillBig[0].data('count') > left[0].data('count')
      ? [stillBig[0], left[0]] : [left[0], stillBig[0]];
    const smalls = left;
    say('LM9 a lump that holds more is bigger: of the big one and the small one it let out, the fuller is the wider',
      smalls.length === 1 && stillBig.length === 1 && fuller.data('count') > lighter.data('count')
        && fuller.width() > lighter.width(),
      JSON.stringify({ big: stillBig.length && [stillBig[0].data('count'), stillBig[0].width()],
        small: smalls.length && [smalls[0].data('count'), smalls[0].width()] }));
    // Another branch ticked whole: its nodes come out with one Open - no small lump of it between.
    const other = pick ? pick.groups.find((g) => g !== keyed && g.members.length && !g.unsent) : null;
    if (stillBig[0]) press(s, stillBig[0].id());
    const otherRow = branchRows(s).find((r) => other && r.attrs['data-value'] === other.key);
    if (otherRow) tickRow(otherRow);
    const wholeWord = (byClass(pickerOf(s) || { children: [] }, 'sg-pick-open')[0] || {}).textContent;
    openTicked(s);
    const drawnNow = new Set(nodesOf(s).map((n) => n.id()));
    say('LM10 a branch ticked whole opens as nodes with one Open, no small lump of it (lead df11f9e81)',
      Boolean(other) && wholeWord === `Open ${other.members.length}` && other.members.every((id) => drawnNow.has(id))
        && lumpsOf(s, 'small').every((n) => n.data('key') !== other.key),
      JSON.stringify({ other: Boolean(other), wholeWord, smallOfIt: lumpsOf(s, 'small').filter((n) => other && n.data('key') === other.key).length }));
    const v = m.lumpView(s.view.layout, s.view.fold, seeds);
    const leading = chosen.filter((id) => v.behind(id) > 0);
    say('LM4 a node let out that leads further comes out folded: its own big lump, nothing behind it drawn',
      leading.length > 0 && leading.every((id) => lumpsOf(s, 'big').some((n) => n.data('owner') === id)),
      JSON.stringify({ leading: leading.length }));
    say('LM5 fold and two openings move neither the view nor any node already drawn',
      viewport(s) === view0 && stayed(new Map([...at0].filter(([id]) => at1.has(id))), s) && stayed(at1, s) && stayed(at2, s),
      JSON.stringify({ view: viewport(s) === view0 }));
    const ys = chosen.map((id) => s.view.cy.getElementById(id).position('y'));
    const leftNow = lumpsOf(s, 'small').filter((n) => n.data('key') === (keyed && keyed.key));
    say('LM6 what came out stands where the lump stood, a row each; what is left of the branch goes under them, the big lump under that',
      ys.length === 2 && ys[0] === lumpAt.y && ys[1] > ys[0] && leftNow.length === 1 && leftNow[0].position('y') > ys[1]
        && stood.big > stood.left,
      JSON.stringify({ lumpAt, ys, left: leftNow.length && leftNow[0].position('y'), stood }));
    // «N next · M behind» (lead df11f9e81): N is what All -> Open draws, M what stays folded after it - done, not read.
    const w = await seat([DIE]);
    openAll(w);
    press(w, pick ? pick.id : '');
    const foldW = byClass(w.host, 'sg-fold')[0];
    if (foldW) foldW.dispatch('click', {});
    const seedsW = w.view.steps.flatMap((x) => x.seeds);
    const wordsW = (m.lumpView(w.view.layout, w.view.fold, seedsW).lumps.find((l) => l.level === 'big' && l.owner === (pick && pick.id)) || {});
    const before = new Set(nodesOf(w).map((n) => n.id()));
    const wordsSaid = (lumpsOf(w, 'big').find((n) => n.data('owner') === (pick && pick.id)) || { data: () => '' }).data('label');
    press(w, `big:${pick ? pick.id : ''}`);
    tickAll(w);
    await settle();
    if (pickerOf(w)) openTicked(w);
    await settle();
    const came = nodesOf(w).filter((n) => !before.has(n.id())).length;
    const after = m.lumpView(w.view.layout, w.view.fold, seedsW).hidden;
    say('LM11 a big lump says N next · M behind: All -> Open draws N new nodes and leaves M folded',
      Boolean(pick) && wordsW.next > 0 && came === wordsW.next && after === wordsW.behind
        && String(wordsSaid).startsWith(`${wordsW.next} next · ${wordsW.behind} behind`),
      JSON.stringify({ said: wordsSaid, next: wordsW.next, behind: wordsW.behind, came, after }));
    // Overlapping branches (lead 2f25c883a): w by p to x1 and x2, by q to x2 and x3 - rows 2 and 2, three distinct.
    const on = (id, depth) => ({ id, type: 'die', label: id, depth, keys: {} });
    const oe = (source, predicate, target) => ({ id: `${source}>${predicate}>${target}`, source, target, predicate });
    const OVER = { state: 'ready', seed: { id: 'o:s' }, truncated: { reason: null },
      nodes: [on('o:s', 0), on('o:w', 1), on('o:x1', 2), on('o:x2', 2), on('o:x3', 2)],
      edges: [oe('o:s', 'r', 'o:w'), oe('o:w', 'p', 'o:x1'), oe('o:w', 'p', 'o:x2'), oe('o:w', 'q', 'o:x2'), oe('o:w', 'q', 'o:x3')] };
    const ov = await seat([OVER]);
    const ovLump = ov.view.cy.getElementById('big:o:w');
    const ovWords = ovLump.nonempty() ? ovLump.data('label') : '';
    const ovBefore = new Set(nodesOf(ov).map((n) => n.id()));
    press(ov, 'big:o:w');
    const ovRows = branchRows(ov).map((r) => textOf(r, 'sg-pick-n').join());
    const ovSub = textOf(pickerOf(ov) || { children: [] }, 'sg-pick-sub').join();
    tickAll(ov);
    const ovGo = (byClass(pickerOf(ov) || { children: [] }, 'sg-pick-open')[0] || {}).textContent;
    openTicked(ov);
    const ovCame = nodesOf(ov).map((n) => n.id()).filter((id) => !ovBefore.has(id)).sort();
    say('LM13 branches sharing nodes: each row its own one-step count, the lump and its window say the distinct next, Open counts and draws those (lead 2f25c883a)',
      String(ovWords).startsWith('3 next · 0 behind') && ovSub === '3 next · 0 behind' && JSON.stringify(ovRows) === JSON.stringify(['2', '2'])
        && ovGo === 'Open 3' && JSON.stringify(ovCame) === JSON.stringify(['o:x1', 'o:x2', 'o:x3']),
      JSON.stringify({ ovWords, ovSub, ovRows, ovGo, ovCame }));
    // The real two bundles (40 dies each, the same 20 drawn): a bound until walked, then the exact count All -> Open draws.
    const bb = await seat([BUNDLES, OPENED_BOTH]);
    const bbId = `big:${BUNDLES.bundles[0].node}`;
    const bbWords = () => (bb.view.cy.getElementById(bbId).nonempty() ? String(bb.view.cy.getElementById(bbId).data('label')) : '');
    const bound = bbWords();
    press(bb, bbId);
    tickAll(bb);
    await settle();
    const exact = bbWords();
    const exactN = Number((exact.match(/^(\d+) next/) || [])[1]);
    const bbBefore = new Set(nodesOf(bb).map((n) => n.id()));
    const bbGo = (byClass(pickerOf(bb) || { children: [] }, 'sg-pick-open')[0] || {}).textContent;
    openTicked(bb);
    const bbCame = nodesOf(bb).map((n) => n.id()).filter((id) => !bbBefore.has(id)).length;
    say('LM14 a bundle not walked: «≤ N next»; walked (All), the exact count, which Open draws (lead 2f25c883a)',
      /^≤ \d+ next · \d+ behind/.test(bound) && /^\d+ next · \d+ behind/.test(exact) && exactN > 0
        && Number(bound.match(/^≤ (\d+)/)[1]) > exactN && bbGo === `Open ${exactN}` && bbCame === exactN && bb.urls.length === 3,
      JSON.stringify({ bound: bound.split('\n')[0], exact: exact.split('\n')[0], bbGo, bbCame, urls: bb.urls.length }));
    // One node under a branch's ▸, one Open: it alone comes out; the branch's rest stays its «n more».
    const one = await seat([DIE]);
    openAll(one);
    press(one, pick ? pick.id : '');
    const foldOne = byClass(one.host, 'sg-fold')[0];
    if (foldOne) foldOne.dispatch('click', {});
    const drawnOne = new Set(nodesOf(one).map((n) => n.id()));
    press(one, `big:${pick ? pick.id : ''}`);
    unfoldRow(one, keyed ? keyed.key : '');
    const oneRow = nodeRows(one, keyed ? keyed.key : '')[0];
    const oneId = oneRow ? String(oneRow.attrs['data-value']).split('\u0000')[1] : null;
    if (oneRow) tickRow(oneRow);
    const oneWord = (byClass(pickerOf(one) || { children: [] }, 'sg-pick-open')[0] || {}).textContent;
    openTicked(one);
    const cameOne = nodesOf(one).map((n) => n.id()).filter((id) => !drawnOne.has(id));
    const restOne = lumpsOf(one, 'small').filter((n) => n.data('key') === (keyed && keyed.key));
    say('LM12 one node ticked under a branch\'s ▸, one Open: that node alone comes out, the branch\'s rest its n more (lead df11f9e81)',
      Boolean(keyed) && Boolean(oneId) && oneWord === 'Open 1' && JSON.stringify(cameOne) === JSON.stringify([oneId])
        && restOne.length === 1 && restOne[0].data('count') === keyed.members.length - 1
        && restOne[0].data('label').includes(`${keyed.members.length - 1} more`),
      JSON.stringify({ oneWord, came: cameOne.length, rest: restOne.length && restOne[0].data('label') }));
    // A lump of more than eight: a filter field; Cancel and Esc close without opening anything.
    const many = await seat([BUNDLES, OPENED]);
    const key = OPEN_KEY;
    openAll(many);
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
  if (want(["Q5", "TK1", "TK2"])) {
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
  if (want(["R1", "V1", "V2", "V3", "V4"])) {
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
  if (want(["Z1", "Z2", "Z3", "Z4"])) {
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
    // The box takes the height the window leaves (owner 10-07), so it changes size under a picture already fitted.
    let resized = 0;
    if (s.view.cy) { s.view.cy.on('resize', () => { resized += 1; }); s.view.cy.zoom(1.3); s.view.cy.pan({ x: 17, y: -29 }); }
    const was = s.view.cy ? JSON.stringify([s.view.cy.zoom(), s.view.cy.pan()]) : '';
    s.view._resized();
    const now = s.view.cy ? JSON.stringify([s.view.cy.zoom(), s.view.cy.pan()]) : '';
    say('Z4 the box changes size: the picture follows it, the view stays (zoom and pan)', resized === 1 && now === was,
      JSON.stringify({ resized, was, now }));
  }

  console.log('\n[X] a press lands: the name is part of the node, a hand that wanders a little still presses (lead 5f1eb137e)');
  if (want(["X1", "X2"])) {
    const s = await seat([DIE]);
    const node = nodesOf(s)[0];
    const textEvents = node ? node.pstyle('text-events').strValue : null;
    say('X1 a node\'s name takes the press as its dot does', textEvents === 'yes', String(textEvents));
    const slop = s.view.cy ? s.view.cy._private.options.desktopTapThreshold : null;
    say('X2 a press may wander TAP_SLOP px before it drags, more than the library\'s 4', slop === m.TAP_SLOP && m.TAP_SLOP > 4,
      JSON.stringify({ slop, TAP_SLOP: m.TAP_SLOP }));
  }

  console.log('\n[Y] a new start keeps nothing of the last picture: no mark, no fold, no opened lump (lead 10-07)');
  if (want(["Y1", "Y2", "Y3", "Y4", "Y5", "Y6"])) {
    const markings = new MarkingStore();
    const s = await seat([BUNDLES, OPENED, WAFER], { markings, chain: ['y0', 'y1', 'y2'] });
    // The last picture: an unsent lump walked and opened, then a node marked that the next start does not reach.
    openAll(s);
    press(s, `lump:${OPEN_KEY}`);
    await settle();
    tickAll(s);
    openTicked(s);
    const inWafer = new Set(WAFER.nodes.map((n) => n.id));
    const x = nodesOf(s).filter((n) => !inWafer.has(n.id()) && n.id() !== startId(BUNDLES))[0];
    if (x) press(s, x.id());
    mark(s.host);
    // A name of the page's own, outside the chain, holding the same node.
    markings.replace('named', x ? [[x.id(), SIGN.CASE]] : []);
    const markedA = markings.count('y1');
    const named = JSON.stringify(markings.entries('named'));
    markings.replace('y0', [[startId(WAFER), SIGN.CASE]]);
    s.urls.length = 0;
    await s.view.show();
    await settle();
    const fresh = await seat([WAFER]);
    const ids = (t) => JSON.stringify([...nodesOf(t).map((n) => n.id()), ...lumpsOf(t).map((n) => n.id())].sort());
    const go = s.view.continueButton;
    say('Y1 the last picture\'s marks are gone: none in the marking Continue walks, none drawn, Continue off',
      Boolean(x) && markedA === 1 && markings.count('y1') === 0 && !nodesOf(s).some((n) => n.hasClass('is-marked'))
        && Boolean(go) && go.disabled === true && go.getAttribute('title') === 'Mark a node',
      JSON.stringify({ x: Boolean(x), markedA, y1: markings.count('y1'), title: go && go.getAttribute('title') }));
    const params = paramsOf(s.urls[0] || '');
    say('Y2 the new start is walked once, asking it alone; what comes is the first picture of that start, no list open',
      s.urls.length === 1 && params.get('id') === startId(WAFER) && params.getAll('expand').length === 0
        && ids(s) === ids(fresh) && !pickerOf(s),
      JSON.stringify({ urls: s.urls.length, id: params.get('id') === startId(WAFER), expand: params.getAll('expand'),
        same: ids(s) === ids(fresh), picker: Boolean(pickerOf(s)) }));
    s.urls.length = 0;
    if (go) go.dispatch('click', {});
    await settle();
    say('Y3 Continue then asks nothing', s.urls.length === 0, String(s.urls.length));
    say('Y4 a marking the page names itself keeps what it held, a node not in this picture too',
      Boolean(x) && named.includes(x.id()) && JSON.stringify(markings.entries('named')) === named
        && s.view.cy.getElementById(x.id()).empty(), JSON.stringify(markings.entries('named')));
    // The same start shown again (the page's view switch) is the same picture: its marks stay, nothing is asked.
    const r = await seat([WAFER], { chain: ['r0', 'r1'] });
    const node = nodesOf(r).filter((n) => n.id() !== startId(WAFER))[0];
    if (node) press(r, node.id());
    mark(r.host);
    const before = r.markings.count('r1');
    r.urls.length = 0;
    await r.view.show({ reuse: true });
    say('Y5 the same start shown again keeps its marks and asks nothing',
      before === 1 && r.markings.count('r1') === 1 && r.urls.length === 0 && node.hasClass('is-marked'),
      JSON.stringify({ before, after: r.markings.count('r1'), urls: r.urls.length }));
    await r.view.show();
    await settle();
    const again = node && r.view.cy.getElementById(node.id());
    say('Y6 the same start walked anew is a new picture: its marks go, on the node drawn again too',
      r.urls.length === 1 && r.markings.count('r1') === 0 && Boolean(again) && again.nonempty() && !again.hasClass('is-marked'),
      JSON.stringify({ urls: r.urls.length, r1: r.markings.count('r1'), marked: again && again.nonempty() && again.hasClass('is-marked') }));
  }

  console.log('\n[U] a lump on its way says so; pressed again meanwhile it asks nothing more (lead 10-07)');
  if (want(["U1", "U2", "U3"])) {
    const id = `lump:${OPEN_KEY}`;
    const labelOf = (t) => { const n = t.view.cy && t.view.cy.getElementById(id); return n && n.nonempty() ? n.pstyle('label').strValue : null; };
    const s = await seat([BUNDLES, OPENED]);
    openAll(s);
    const words = labelOf(s);
    s.urls.length = 0;
    press(s, id);
    const during = labelOf(s);
    press(s, id);
    press(s, id);
    await settle();
    say('U1 pressed, the lump reads Loading until its list comes; pressed again meanwhile, nothing more is asked',
      Boolean(words) && words !== LOADING && during === LOADING && s.urls.length === 1,
      JSON.stringify({ words, during, urls: s.urls.length }));
    const lump = s.view.cy.getElementById(id);
    say('U2 the list come, the lump reads its own words again and the list is open',
      labelOf(s) !== LOADING && lump.nonempty() && labelOf(s) === lump.data('label') && Boolean(pickerOf(s)),
      JSON.stringify({ label: labelOf(s), picker: Boolean(pickerOf(s)) }));
    // A walk that is refused: the lump does not read Loading for ever.
    const f = await seat([BUNDLES]);
    openAll(f);
    f.view.walk = async () => ({ ok: false, message: 'Refused' });
    press(f, id);
    await settle();
    say('U3 refused, the lump reads its own words again and the refusal is said',
      labelOf(f) !== null && labelOf(f) !== LOADING && textOf(f.host, 'sg-fail').join() === 'Failed · Refused',
      JSON.stringify({ label: labelOf(f), fail: textOf(f.host, 'sg-fail') }));
  }

  console.log('\n[J] a folded lump seen as its list, a table or points; the start branch lit in all (lead 10-08)');
  if (want(["J1", "J2", "J3", "J4", "J5", "J6", "J7", "J8", "J9"])) {
    const s = await seat([FOLD_WAFER, FOLD_STEP]);
    const startIds = new Set(FOLD_WAFER.nodes.map((n) => n.id));
    // M1's branches are one big lump; its `used` branch holds the recipe, seen from its row (no small lump between).
    const owner = FOLD_WAFER.nodes.find((n) => FOLD_WAFER.edges.some((e) => e.source === n.id && e.predicate === 'used'));
    const box = () => s.view.factsBox;
    const kinds = () => byClass(box(), 'sg-lv-kind');
    const switchTo = (word) => { const b = kinds().find((k) => k.textContent === word); if (b) b.dispatch('click', {}); return Boolean(b); };
    const was = positions(s);
    const viewWas = viewport(s);
    const lumpsWas = lumpsOf(s).map((n) => [n.id(), n.data('label')]);
    press(s, `big:${owner.id}`);
    const usedKey = (branchRows(s).find((r) => r.attrs['data-value'].includes('|used|')) || { attrs: {} }).attrs['data-value'];
    unfoldRow(s, usedKey);
    const pickerRows = nodeRows(s, usedKey);
    s.urls.length = 0;
    let during = '';
    const id = await branchTrend(s, `big:${owner.id}`, '|used|', () => {});
    during = s.view.lumpSeen.data.get(id) ? 'asked' : '';
    say('J1 a branch\'s row: its ▸ lists its nodes, the start branch lit; its Trend puts the branch in the info box - its words and Nodes · Table · Trend, Trend on - and the picture keeps its lumps (lead df11f9e81)',
      Boolean(usedKey) && JSON.stringify(kinds().map((k) => [k.textContent, k.getAttribute('aria-pressed')]))
        === '[["Nodes","false"],["Table","false"],["Trend","true"]]'
        && pickerRows.length > 0 && pickerRows.every((r) => r.className.includes('is-lit') === startIds.has(String(r.attrs['data-value']).split('\u0000')[1]))
        && pickerRows.some((r) => r.className.includes('is-lit')) && s.view.pickedLump === id
        && JSON.stringify(lumpsOf(s).map((n) => [n.id(), n.data('label')])) === JSON.stringify(lumpsWas),
      JSON.stringify({ key: Boolean(usedKey), kinds: kinds().map((k) => k.textContent), rows: pickerRows.length, picked: s.view.pickedLump }));
    const params = paramsOf(s.urls[0] || '');
    const recipe = FOLD_WAFER.edges.find((e) => e.source === owner.id && e.predicate === 'used').target;
    const times = FOLD_WAFER.nodes.filter((n) => n.type === owner.type)
      .flatMap((n) => Object.values(n.attributes_by_world || {}).flat().map((w) => Date.parse(w.occurred_at)));
    const DAY = 24 * 60 * 60 * 1000;
    const since = new Date(Math.min(...times) - 7 * DAY).toISOString();
    const until = new Date(Math.max(...times) + 7 * DAY).toISOString();
    say('J2 a lump of definition nodes walks one step back along its predicate, the start branch\'s times a week each side, capped; once',
      during === 'asked' && s.urls.length === 1 && JSON.stringify(params.getAll('positive')) === JSON.stringify([recipe])
        && params.get('hops') === '1' && JSON.stringify(params.getAll('follow')) === '["used"]'
        && JSON.stringify(params.getAll('collect')) === JSON.stringify([owner.type])
        && params.get('direction') === 'incoming' && params.get('node_limit') === String(STEP_NODE_LIMIT)
        && params.get('since') === since && params.get('until') === until && !pickerOf(s),
      JSON.stringify({ during, urls: s.urls.length, q: [...params.entries()].filter(([k]) => k !== 'id' && k !== 'positive'), since, until }));
    const circles = (src) => [...decodeURIComponent(String(src || '').split(',').slice(1).join(',')).matchAll(/<circle [^>]*>/g)].map((c) => c[0]);
    const plot = byClass(box(), 'sg-lv-plot')[0];
    const dots = circles(plot && plot.getAttribute('src'));
    const valued = FOLD_STEP.nodes.filter((n) => n.attributes && 'value' in n.attributes);
    const litCount = valued.filter((n) => startIds.has(n.id)).length;
    const meta = textOf(box(), 'sg-lv-meta').join();
    say('J3 its points: one per node that holds a number, the start branch\'s drawn over the rest; the count and the window said as values',
      dots.length === valued.length && litCount > 0 && litCount < valued.length
        && dots.slice(-litCount).every((c) => !c.includes('opacity')) && dots.slice(0, -litCount).every((c) => c.includes('opacity'))
        && meta.startsWith(`Points ${valued.length} · Window `) && !meta.includes('Capped'),
      JSON.stringify({ dots: dots.length, valued: valued.length, litCount, meta }));
    // A lump in the picture carries its points: the measurements' branch with one node opened, the rest a small lump.
    const vl = await seat([FOLD_WAFER], { declaration: foldDecl });
    const waferId = startId(FOLD_WAFER);
    press(vl, waferId);
    const foldIt = byClass(vl.host, 'sg-fold')[0];
    if (foldIt) foldIt.dispatch('click', {});
    press(vl, `big:${waferId}`);
    const measuredKey = (branchRows(vl).find((r) => r.attrs['data-value'].includes('|measured|')) || { attrs: {} }).attrs['data-value'];
    unfoldRow(vl, measuredKey);
    const firstNode = nodeRows(vl, measuredKey)[0];
    if (firstNode) tickRow(firstNode);
    openTicked(vl);
    const rest = lumpsOf(vl, 'small').filter((n) => n.data('key') === measuredKey)[0];
    if (rest) press(vl, rest.id());
    const toTrend = byClass(vl.view.factsBox, 'sg-lv-kind').find((k) => k.textContent === 'Trend');
    if (toTrend) toTrend.dispatch('click', {});
    await settle();
    const picture = rest ? vl.view.cy.getElementById(rest.id()) : null;
    say('J4 the lump carries the same points as its own picture',
      Boolean(picture) && picture.nonempty() && rest.data('count') > 0 && circles(picture.data('spark')).length === rest.data('count'),
      String(picture && picture.nonempty() && picture.data('spark')).slice(0, 40));
    s.urls.length = 0;
    switchTo('Table');
    await settle();
    const tableRows = byClass(box(), 'rb-table-row');
    const head = byClass(box(), 'rb-table-head')[0];
    say('J5 as a table: a row per node it walked, the start branch\'s lit, nothing asked again; and its picture goes',
      s.urls.length === 0 && tableRows.length === FOLD_STEP.nodes.length
        && tableRows.filter((r) => r.className.includes('is-lit')).length === FOLD_STEP.nodes.filter((n) => startIds.has(n.id)).length
        && head && [...head.children].map((c) => c.textContent).join() === 'Name,value,Time',
      JSON.stringify({ urls: s.urls.length, rows: tableRows.length, head: head && [...head.children].map((c) => c.textContent) }));
    say('J6 seeing a lump another way moves nothing: the nodes stand, the view stays',
      was.size > 0 && stayed(was, s) && viewport(s) === viewWas, JSON.stringify({ view: viewport(s) === viewWas }));
    switchTo('Nodes');
    say('J7 back to Nodes, its owner\'s window opens with the branch unfolded and nothing is asked',
      Boolean(pickerOf(s)) && s.urls.length === 0 && nodeRows(s, usedKey).length > 0 && nodeRows(s, usedKey).every((r) => !r.hidden),
      JSON.stringify({ picker: Boolean(pickerOf(s)), urls: s.urls.length }));
    press(s, owner.id);
    say('J8 a node pressed, the info box holds that node again', byClass(box(), 'sg-lv-kind').length === 0
      && textOf(box(), 'sg-facts-head').join().includes(owner.type), textOf(box(), 'sg-facts-head').join());
    // A new start while a lump's walk is on its way: the answer lands nowhere, and nothing of the lumps stays.
    s.view.lumpSeen.data.delete(id);
    const pending = branchTrend(s, `big:${owner.id}`, '|used|');
    await s.view.show();
    await pending;
    await settle();
    say('J9 a new start keeps no lump\'s view, choice or walk - an answer that comes after lands nowhere',
      s.view.lumpSeen.kind.size === 0 && s.view.lumpSeen.data.size === 0 && s.view.pickedLump === null
        && byClass(box(), 'sg-lv-kind').length === 0,
      JSON.stringify({ kind: s.view.lumpSeen.kind.size, data: s.view.lumpSeen.data.size, picked: s.view.pickedLump }));
  }

  console.log('\n[S] a key let out of a big lump stands clear of it; a big lump\'s row goes to points in one press; a lump of values asks nothing (owner 10-08)');
  if (want(["S1", "S2", "S3"])) {
    const owner = FOLD_WAFER.nodes.find((n) => FOLD_WAFER.edges.some((e) => e.source === n.id && e.predicate === 'used'));
    const boxOf = (n) => n.boundingBox({ includeLabels: false });
    const apart = (a, b) => a.x2 <= b.x1 || b.x2 <= a.x1 || a.y2 <= b.y1 || b.y2 <= a.y1;
    // A branch's nodes, one opened: what is left of it a small lump beside the big one.
    const s = await seat([FOLD_WAFER], { declaration: foldDecl });
    const wafer0 = startId(FOLD_WAFER);
    press(s, wafer0);
    const fold0 = byClass(s.host, 'sg-fold')[0];
    if (fold0) fold0.dispatch('click', {});
    press(s, `big:${wafer0}`);
    const measured = (branchRows(s).find((r) => r.attrs['data-value'].includes('|measured|')) || { attrs: {} }).attrs['data-value'];
    unfoldRow(s, measured);
    const one = nodeRows(s, measured)[0];
    if (one) tickRow(one);
    openTicked(s);
    const small = lumpsOf(s, 'small').filter((n) => n.data('key') === measured)[0];
    const big = lumpsOf(s, 'big').filter((n) => n.data('owner') === wafer0)[0];
    say('S1 the small lump a big one let out and the big one left do not overlap, by their boxes',
      Boolean(small) && Boolean(big) && apart(boxOf(small), boxOf(big)),
      JSON.stringify({ small: small && boxOf(small), big: big && boxOf(big) }));
    // The long way took one walk for the recipe's points (J2); the row's own Trend takes the same.
    const t = await seat([FOLD_WAFER, FOLD_STEP]);
    press(t, `big:${owner.id}`);
    t.urls.length = 0;
    const trendOf = (key) => byClass(pickerOf(t) || { children: [] }, 'sg-pick-view')
      .find((b) => String(b.attrs['data-value']).includes(key));
    const rowTrend = trendOf('|used|');
    if (rowTrend) rowTrend.dispatch('click', {});
    await settle();
    const opened = lumpsOf(t, 'small').filter((n) => n.data('owner') === owner.id)[0];
    const kinds = byClass(t.view.factsBox, 'sg-lv-kind').map((k) => [k.textContent, k.getAttribute('aria-pressed')]);
    say('S2 a big lump\'s row has its own Trend: one press shows that branch\'s points, no small lump of it between, asking what the long way asks',
      Boolean(rowTrend) && rowTrend.textContent === 'Trend' && !opened && t.view.pickedLump === `branch:${rowTrend.attrs['data-value']}`
        && JSON.stringify(kinds) === '[["Nodes","false"],["Table","false"],["Trend","true"]]'
        && byClass(t.view.factsBox, 'sg-lv-plot').length === 1 && t.urls.length === 1 && !pickerOf(t),
      JSON.stringify({ button: Boolean(rowTrend), opened: Boolean(opened), kinds, urls: t.urls.length }));
    // The start wafer's own measurements folded and opened: members that hold the values themselves.
    const v = await seat([FOLD_WAFER], { declaration: foldDecl });
    const wafer = startId(FOLD_WAFER);
    press(v, wafer);
    const fold = byClass(v.host, 'sg-fold')[0];
    if (fold) fold.dispatch('click', {});
    v.urls.length = 0;
    const values = await branchTrend(v, `big:${wafer}`, '|measured|');
    const branch = v.view._branchLump(values.slice('branch:'.length));
    const members = branch ? branch.members.length : 0;
    const dots = (() => { const p = byClass(v.view.factsBox, 'sg-lv-plot')[0];
      return p ? (decodeURIComponent(String(p.getAttribute('src')).split(',').slice(1).join(',')).match(/<circle /g) || []).length : -1; })();
    say('S3 a lump whose members hold the values: Trend asks nothing, a point per member, no Points from',
      Boolean(values) && members > 0 && v.urls.length === 0 && dots === members
        && textOf(v.view.factsBox, 'sg-lv-meta').join() === `Points ${members}`
        && !byClass(v.view.factsBox, 'sg-lv-word').some((w) => w.textContent === 'Points from'),
      JSON.stringify({ values: Boolean(values), members, urls: v.urls.length, dots, meta: textOf(v.view.factsBox, 'sg-lv-meta') }));
  }

  console.log('\n[O] what the info box says of a lump\'s walk: capped, refused, values that are not numbers (lead 10-08)');
  if (want(["O1", "O2", "O3", "O5"])) {
    // The recipe lump behind the start wafer's first measurement, seen as points; `second` is its walk's answer.
    const seeRecipe = async (second, beforeTrend) => {
      const s = await seat([FOLD_WAFER, second]);
      const owner = FOLD_WAFER.nodes.find((n) => FOLD_WAFER.edges.some((e) => e.source === n.id && e.predicate === 'used'));
      const lumps = lumpsOf(s).map((n) => [n.id(), n.data('label')]);
      await branchTrend(s, `big:${owner.id}`, '|used|', beforeTrend);
      // A branch seen so changes no lump in the picture (lead df11f9e81): nothing carries what its walk brought.
      return { s, meta: textOf(s.view.factsBox, 'sg-lv-meta').join(),
        spark: JSON.stringify(lumpsOf(s).map((n) => [n.id(), n.data('label')])) !== JSON.stringify(lumps) || lumpsOf(s).some((n) => n.data('spark')) };
    };
    const capped = await seeRecipe({ ...FOLD_STEP, truncated: { ...FOLD_STEP.truncated, nodes: true, reason: 'nodes' } });
    say('O1 a walk the node cap cut says so in the picture\'s own words, with the cap the answer names',
      capped.meta.endsWith(` · Truncated · nodes ${FOLD_STEP.limits.nodes}`), capped.meta);
    // A claims cut (lead 161757c35): the answer carries nodes whose attributes did not arrive.
    const bare = JSON.parse(JSON.stringify(FOLD_STEP));
    const stripped = bare.nodes.filter((n) => n.attributes && 'value' in n.attributes).slice(0, 2);
    for (const n of stripped) { n.attributes = {}; n.attributes_by_world = {}; }
    bare.truncated = { ...bare.truncated, claims: true, reason: 'claims' };
    const claims = await seeRecipe(bare);
    const held = FOLD_STEP.nodes.filter((n) => n.attributes && 'value' in n.attributes).length - stripped.length;
    say('O5 a claims cut is said with the node cut\'s words, and the nodes it left bare are counted beside the rest',
      stripped.length === 2 && claims.meta.startsWith(`Points ${held} · Window `)
        && claims.meta.endsWith(` · Truncated · claims ${FOLD_STEP.limits.claims} · 2 without value`),
      claims.meta);
    const refused = await seeRecipe(FOLD_STEP, (s) => { s.view.walk = async () => ({ ok: false, message: 'Refused' }); });
    say('O2 a walk refused says so in the info box, and the lump carries no picture',
      textOf(refused.s.view.factsBox, 'sg-fail').join() === 'Failed · Refused' && !refused.spark,
      JSON.stringify({ fail: textOf(refused.s.view.factsBox, 'sg-fail'), spark: Boolean(refused.spark) }));
    const odd = JSON.parse(JSON.stringify(FOLD_STEP));
    const [a, b] = odd.nodes.filter((n) => n.attributes && 'value' in n.attributes);
    a.attributes.value = 'n/a';
    a.attributes_by_world.value = a.attributes_by_world.value.map((w) => ({ ...w, value: 'n/a' }));
    b.attributes_by_world.value = b.attributes_by_world.value.map(({ occurred_at: _, ...w }) => w);
    const left = FOLD_STEP.nodes.filter((n) => n.attributes && 'value' in n.attributes).length - 2;
    const counted = await seeRecipe(odd);
    say('O3 a value that is not a number and one said at no time are left out, each counted as a value',
      counted.meta.startsWith(`Points ${left} · `) && counted.meta.endsWith(' · 1 not numbers · 1 no time'), counted.meta);
  }

  console.log('\n[I] a lump of events that hold no number: its points come from the type the operator picks (lead 10-08)');
  if (want(["I1", "I2", "I3", "I4", "I5"])) {
    // A browser's storage, as far as the part touches it.
    const memory = () => { const kept = new Map(); return { getItem: (k) => (kept.has(k) ? kept.get(k) : null),
      setItem: (k, v) => { kept.set(k, String(v)); } }; };
    // The start wafer's branches folded, its `underwent` key opened: a small lump holding the process events.
    const seatProcess = async (declaration, storage) => {
      const s = await seat([FOLD_WAFER, FOLD_PROCESS], { declaration, storage });
      const wafer = startId(FOLD_WAFER);
      press(s, wafer);
      const fold = byClass(s.host, 'sg-fold')[0];
      if (fold) fold.dispatch('click', {});
      s.urls.length = 0;
      const lump = await branchTrend(s, `big:${wafer}`, '|underwent|');
      return { s, lump };
    };
    const choiceOf = (s, word) => {
      const label = byClass(s.view.factsBox, 'sg-lv-choice').find((l) => textOf(l, 'sg-lv-word').join() === word);
      return label ? byClass(label, 'sg-lv-y')[0] || label.children[1] : null;
    };
    const optionsOf = (select) => (select ? [...select.children].map((o) => o.attrs.value) : null);
    const storage = memory();
    const { s, lump } = await seatProcess(foldDecl, storage);
    const from = choiceOf(s, 'Points from');
    const reachable = foldDecl.entities.map((e) => e.type)
      .filter((t) => t !== 'process_event' && walkableRoutes(foldDecl, 'process_event', t).length);
    say('I1 before a pick, Points from lists the types the route list reaches from the members\' type but theirs; nothing is asked',
      Boolean(lump) && JSON.stringify(optionsOf(from)) === JSON.stringify(['', ...reachable])
        && reachable.includes('measurement_event') && !reachable.includes('process_event')
        && s.urls.length === 0 && textOf(s.view.factsBox, 'sg-note').join() === 'Pick a type' && !byClass(s.view.factsBox, 'sg-lv-plot').length,
      JSON.stringify({ lump: Boolean(lump), options: optionsOf(from), urls: s.urls.length }));
    if (from) { from.value = 'measurement_event'; from.dispatch('change', {}); }
    await settle();
    const params = paramsOf(s.urls[0] || '');
    const asked = new URLSearchParams(FOLD_PROCESS._asked.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join('&'));
    const valued = FOLD_PROCESS.nodes.filter((n) => n.attributes && 'value' in n.attributes);
    const meta = textOf(s.view.factsBox, 'sg-lv-meta').join();
    say('I2 picked, walked once along every route to that type and collecting it - as the implementer asked it; its values are the points',
      s.urls.length === 1
        && JSON.stringify(params.getAll('positive').sort()) === JSON.stringify(asked.getAll('positive').sort())
        && JSON.stringify(params.getAll('follow').sort()) === JSON.stringify(asked.getAll('follow').sort())
        && JSON.stringify(params.getAll('collect')) === JSON.stringify(asked.getAll('collect'))
        && params.get('hops') === asked.get('hops') && params.get('direction') === asked.get('direction')
        && !params.get('since') && valued.length > 0 && meta === `Points ${valued.length}`
        && choiceOf(s, 'Points from').value === 'measurement_event' && Boolean(choiceOf(s, 'Value')),
      JSON.stringify({ urls: s.urls.length, q: [...params.entries()].filter(([k]) => k !== 'id'), meta }));
    const again = await seatProcess(foldDecl, storage);
    say('I3 this browser remembers the pick for the members\' type: the next time it is walked at once, nothing to pick',
      again.s.urls.length === 1 && paramsOf(again.s.urls[0] || '').getAll('collect').join() === 'measurement_event'
        && textOf(again.s.view.factsBox, 'sg-lv-meta').join() === `Points ${valued.length}`,
      JSON.stringify({ urls: again.s.urls.length, meta: textOf(again.s.view.factsBox, 'sg-lv-meta') }));
    // A picture with no measurement in it: the list is the declaration's, whatever the picture holds (lead 10-08 gate).
    const bare = (body) => {
      const gone = new Set(body.nodes.filter((n) => n.type === 'measurement_event').map((n) => n.id));
      return { ...body, nodes: body.nodes.filter((n) => !gone.has(n.id)),
        edges: body.edges.filter((e) => !gone.has(e.source) && !gone.has(e.target)) };
    };
    const lean = await (async () => {
      const t = await seat([bare(FOLD_WAFER), FOLD_PROCESS], { declaration: foldDecl, storage: memory() });
      const wafer = startId(FOLD_WAFER);
      press(t, wafer);
      const fold = byClass(t.host, 'sg-fold')[0];
      if (fold) fold.dispatch('click', {});
      t.urls.length = 0;
      const small = await branchTrend(t, `big:${wafer}`, '|underwent|');
      return { t, small };
    })();
    say('I5 no measurement in the picture: Points from still lists the declaration\'s types, measurement_event among them; nothing asked',
      Boolean(lean.small) && !nodesOf(lean.t).some((n) => n.data('type') === 'measurement_event')
        && JSON.stringify(optionsOf(choiceOf(lean.t, 'Points from'))) === JSON.stringify(['', ...reachable])
        && lean.t.urls.length === 0,
      JSON.stringify({ small: Boolean(lean.small), options: optionsOf(choiceOf(lean.t, 'Points from')), urls: lean.t.urls.length }));
    const none = await seatProcess(null, null);
    say('I4 no declaration to route by and no storage: nothing to pick from, nothing asked',
      Boolean(none.lump) && none.s.urls.length === 0 && JSON.stringify(optionsOf(choiceOf(none.s, 'Points from'))) === '[""]'
        && textOf(none.s.view.factsBox, 'sg-note').join() === 'Pick a type',
      JSON.stringify({ urls: none.s.urls.length, options: optionsOf(choiceOf(none.s, 'Points from')) }));
  }

  console.log('\n[QS] Shift on Mark marks a control - the board\'s markingIntent (lead 10-09)');
  if (want(["QS1"])) {
    const s = await seat([DIE, STEP2]);
    openAll(s);
    const id = STEP2._marked;
    press(s, id);
    const button = byClass(s.host, 'sg-mark')[0];
    if (button) button.dispatch('click', { shiftKey: true });
    const n = s.view.cy && s.view.cy.getElementById(id);
    say('QS1 a Shift press on Mark marks the node a control, and the picture draws it as one',
      s.markings.signOf('s1', id) === SIGN.CONTROL && Boolean(n && n.nonempty() && n.hasClass('is-control')),
      JSON.stringify(s.markings.entries('s1')));
  }

  console.log('\n[Q] Mark is the one press that marks; the facts stay in sight (lead 9dc2a5695 ① ②)');
  if (want(["Q1", "Q12", "Q2", "Q3", "Q4", "Q6"])) {
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
    // Owner 10-07 (lead d78bf28bd): above the picture, in a cell the row holds at one height - so a pick moves nothing.
    const rootKids = (byClass(s.host, 'sg-view')[0] || { children: [] }).children;
    const holds = (k) => byClass(k, 'sg-facts').length > 0;
    const above = rootKids.findIndex(holds) >= 0 && rootKids.findIndex(holds) < rootKids.findIndex((k) => has(k, 'sg-canvas-wrap'));
    const rowFixed = rules.some(([sels, body]) => sels.includes('.sg-top') && /grid-template-rows:\s*[\d.]+px;/.test(body));
    say('Q3 the facts box is above the picture, held in a cell of a fixed height, with its own scroll',
      above && rowFixed && ruled('.sg-factslot > .sg-facts', 'position: absolute') && ruled('.sg-factslot > .sg-facts', 'inset: 0')
        && ruled('.sg-facts', 'overflow: auto'), JSON.stringify({ above, rowFixed, kids: rootKids.map((k) => k.className) }));
    const headBox = byClass(s.host, 'sg-head')[0] || { children: [] };
    const toolsAt = rootKids.findIndex((k) => byClass(k, 'sg-continue').length > 0);
    say('Q12 the tools (Fit, Reset, Continue) are above the picture, first in their cell',
      toolsAt >= 0 && toolsAt < rootKids.findIndex((k) => has(k, 'sg-canvas-wrap'))
        && has(headBox.children[0] || {}, 'sg-acts') && byClass(headBox.children[0], 'sg-continue').length === 1,
      JSON.stringify(headBox.children.map((k) => k.className)));
    say('Q4 nothing picked draws no box', ruled('.sg-facts:empty', 'display: none')
      && byClass((await seat([WAFER])).host, 'sg-facts').every((b) => b.children.length === 0));
    // A height of its own would cut the picture to it; `min-height` is the floor, not a height.
    const fixedHeight = rules.some(([sels, body]) => sels.includes('.sg-canvas-wrap') && /(^|[;{\s])height\s*:/.test(body));
    say('Q6 the picture takes the height left (owner 10-07), panning inside itself',
      ruled('.sg-canvas-wrap', 'flex: 1 1 auto') && !fixedHeight && ruled('.sg-canvas-wrap', 'overflow: hidden')
        && ruled('.wk-graph', 'flex: 1 1 auto') && ruled('.wk-graph', 'min-height: 0')
        && ruled('.wk-graph > .sg-view', 'flex: 1 1 auto'), JSON.stringify({ fixedHeight }));
  }

  console.log('\n[W] several worlds read: under each attribute and each edge, a row per world that says it (leads ee0f66e7b, 4e1e49fe9)');
  if (want(["W5", "W6", "W7"])) {
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

  if (want(['AW1', 'AW2'])) {
    // A die out of the wafer's unsent bundle (lead f6e8ef44b): drawn, its back not walked by the server.
    const die = OPENED.nodes.find((n) => !BUNDLES.nodes.some((b) => b.id === n.id));
    const dn = (id, type) => ({ id, type, label: id, depth: 1, keys: {} });
    const STEP = { state: 'ready', seed: { id: die.id }, truncated: { reason: null },
      nodes: [{ ...die, depth: 0 }, dn('aw:x', 'die'), dn('aw:y', 'container'), ...[1, 2, 3, 4, 5, 6].map((k) => dn(`aw:o${k}`, 'defect'))],
      edges: [{ id: 'aw:e1', source: die.id, target: 'aw:x', predicate: 'bonded_from' }, { id: 'aw:e2', source: die.id, target: 'aw:y', predicate: 'transfer' },
        ...[1, 2, 3, 4, 5, 6].map((k) => ({ id: `aw:e${k + 2}`, source: die.id, target: `aw:o${k}`, predicate: 'observed' }))] };
    const w = await seat([BUNDLES, OPENED, STEP]);
    const wafer = `big:${BUNDLES.bundles[0].node}`;
    press(w, wafer);
    unfoldRow(w, OPEN_KEY);
    await settle();
    const dieRow = nodeRows(w, OPEN_KEY).find((r) => String(r.attrs['data-value']).endsWith(`\u0000${die.id}`));
    if (dieRow) tickRow(dieRow);
    openTicked(w);
    await settle();
    const dashed = w.view.cy.getElementById(`big:${die.id}`);
    const walkedBefore = nodesOf(w).filter((n) => BUNDLES.nodes.some((b) => b.id === n.id())).map((n) => n.id());
    const widenedDashed = walkedBefore.filter((id) => w.view.cy.getElementById(`big:${id}`).nonempty() && w.view.cy.getElementById(`big:${id}`).data('unsent'));
    say('AW1 a node a bundle\'s opening brought: a dashed «? next · not walked» lump behind it; a node the walk widened, none (lead f6e8ef44b)',
      Boolean(dieRow) && dashed.nonempty() && Boolean(dashed.data('unsent')) && String(dashed.data('label')).startsWith('? next · not walked')
        && walkedBefore.length > 0 && widenedDashed.length === 0,
      JSON.stringify({ row: Boolean(dieRow), dashed: dashed.nonempty() && dashed.data('label'), widenedDashed }));
    const asked = w.urls.length;
    const before = new Set(nodesOf(w).map((n) => n.id()));
    press(w, `big:${die.id}`);
    await settle();
    const ask = w.urls.slice(asked);
    const params = ask.length ? paramsOf(ask[0]) : new URLSearchParams();
    const words = (w.view.cy.getElementById(`big:${die.id}`).nonempty() ? String(w.view.cy.getElementById(`big:${die.id}`).data('label')) : '').split('\n')[0];
    const sub = textOf(pickerOf(w) || { children: [] }, 'sg-pick-sub').join();
    tickAll(w);
    openTicked(w);
    const came = nodesOf(w).map((n) => n.id()).filter((id) => !before.has(id)).length;
    const after = w.view.cy.getElementById(`big:${die.id}`).nonempty();
    say('AW2 pressed: one walk from that node, every predicate one step; then its big lump\'s window, its words what Open draws; all open, no lump again (lead f6e8ef44b)',
      ask.length === 1 && params.getAll('positive').length === 1 && !params.has('follow') && params.get('hops') === '1'
        && words === '8 next · 0 behind' && sub === words && came === 8 && !after,
      JSON.stringify({ asks: ask.length, follow: params.getAll('follow'), hops: params.get('hops'), words, sub, came, after }));
  }

  if (want(['PA1', 'PA2', 'PA3', 'PA4'])) {
    // A hand walk: s by p to w and by r to c; w by q to a and by p to b; c by q to a. Two kinds of path s - a.
    const pn = (id, depth) => ({ id, type: 'die', label: id, depth, keys: {} });
    const pe = (source, predicate, target) => ({ id: `${source}>${predicate}>${target}`, source, target, predicate });
    const HAND = { state: 'ready', seed: { id: 'h:s' }, truncated: { reason: null },
      nodes: [pn('h:s', 0), pn('h:w', 1), pn('h:c', 1), pn('h:a', 2), pn('h:b', 2)],
      edges: [pe('h:s', 'p', 'h:w'), pe('h:s', 'r', 'h:c'), pe('h:w', 'q', 'h:a'), pe('h:w', 'p', 'h:b'), pe('h:c', 'q', 'h:a')] };
    const boxOf = (x) => byClass(x.host, 'sg-paths')[0];
    const kindWords = (x) => (boxOf(x) ? byClass(boxOf(x), 'sg-paths-words').map((n) => n.textContent) : []);
    const s = await seat([HAND]);
    openAll(s);
    const asked = s.urls.length;
    s.markings.replace(s.chain[1], [['h:s', SIGN.CASE], ['h:a', SIGN.CASE]]);
    const box = boxOf(s);
    const want0 = pathKinds(HAND, 'h:s', 'h:a', new Set(['p', 'q', 'r'])).kinds.map((k) => k.words.join(' — '));
    say('PA1 two nodes in the marking Mark writes: the Paths box names them, the walk\'s edges with their counts, the kinds - pathKinds\' own - nothing asked',
      Boolean(box) && !box.hidden && textOf(box, 'sg-paths-head').join() === 'Paths · h:s — h:a'
        && JSON.stringify(byClass(box, 'sg-paths-edge').map((n) => n.textContent)) === JSON.stringify(['p 2', 'q 2', 'r 1'])
        && want0.length === 2 && JSON.stringify(kindWords(s)) === JSON.stringify(want0) && s.urls.length === asked,
      JSON.stringify({ hidden: box && box.hidden, edges: box && byClass(box, 'sg-paths-edge').map((n) => n.textContent), kinds: kindWords(s), want0 }));
    const r = box && byClass(box, 'sg-paths-edge').map((n) => n.children[0]).find((t) => t.attrs['data-path-edge'] === 'r');
    if (r) { r.checked = false; r.dispatch('change', {}); }
    say('PA2 an edge unticked: the kinds through it are gone, the others stay',
      JSON.stringify(kindWords(s)) === JSON.stringify([want0.find((w) => !w.includes(' r '))]), JSON.stringify(kindWords(s)));
    s.markings.replace(s.chain[1], [['h:s', SIGN.CASE]]);
    const one = Boolean(boxOf(s)) && boxOf(s).hidden;
    s.markings.replace(s.chain[1], [['h:s', SIGN.CASE], ['h:a', SIGN.CASE], ['h:b', SIGN.CASE]]);
    say('PA3 one node marked, or three: no Paths box', one && boxOf(s).hidden, JSON.stringify({ one, three: boxOf(s) && boxOf(s).hidden }));
    // s - w - b: b behind w alone; w folded, b out of sight; the kind pressed brings it back and lights the path.
    const f = await seat([HAND]);
    openAll(f);
    f.markings.replace(f.chain[1], [['h:s', SIGN.CASE], ['h:b', SIGN.CASE]]);
    press(f, 'h:w');
    const foldW = byClass(f.host, 'sg-fold')[0];
    if (foldW && foldW.textContent !== 'Unfold') foldW.dispatch('click', {});
    const hidden = f.view.cy.getElementById('h:b').empty();
    const kind = boxOf(f) && byClass(boxOf(f), 'sg-paths-kind')[0];
    if (kind) kind.dispatch('click', {});
    const cls = (id, c) => f.view.cy.getElementById(id).nonempty() && f.view.cy.getElementById(id).hasClass(c);
    const litEdges = f.view.cy.edges('[kind = "edge"]').filter((e) => e.hasClass('is-path')).map((e) => e.id()).sort();
    say('PA4 a kind pressed: its nodes and edges lit, the rest dimmed - and a node of it folded out of sight comes back first',
      hidden && ['h:s', 'h:w', 'h:b'].every((id) => cls(id, 'is-path')) && ['h:c', 'h:a'].every((id) => cls(id, 'is-dim'))
        && JSON.stringify(litEdges) === JSON.stringify(['h:s>p>h:w', 'h:w>p>h:b']),
      JSON.stringify({ hidden, kind: Boolean(kind), lit: ['h:s', 'h:w', 'h:b'].map((id) => cls(id, 'is-path')), litEdges }));
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
      ' negative: step.negative, fanout_limit: this.fanoutLimit }, [],',
      " negative: step.negative, fanout_limit: this.fanoutLimit, follow: ['inspected'] }, [],"),
    M('M4', 'the edges are not drawn', 'A2',
      '    for (const e of view.edges) {\n      // A line one column forward', '    for (const e of []) {\n      // A line one column forward'),
    M('M5', 'a press does not change the facts', 'E1',
      '    this.selected = id;\n    this._swapFacts();', '    this._swapFacts();'),
    M('M6', 'a cut walk says nothing', 'F1',
      '      if (result.cut) cut.push(', '      if (false) cut.push('),
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
      '    if (name) this.markings.toggle(name, id, markingIntent(event).sign);\n', ''),
    M('QS1m', 'Mark takes no sign from Shift (lead 10-09)', 'QS1',
      'this.markings.toggle(name, id, markingIntent(event).sign);', 'this.markings.toggle(name, id, SIGN.CASE);'),
    M('Q2m', 'Mark does not show its state', 'Q1',
      "      this.markButton.setAttribute('aria-pressed', String(on));\n", ''),
    M('Q3m', 'Mark is live past the chain\'s end', 'L2',
      "      setDisabledReason(this.markButton, name ? '' : 'End of chain');\n", ''),
    M('Q4m', 'Mark stands after the facts', 'Q2',
      '    box.appendChild(acts);\n    for (const [name, value]', '    for (const [name, value]'),
    { ...M('Q5m', 'the facts box is not held in its cell', 'Q3',
      '.sg-factslot > .sg-facts { position: absolute; inset: 0; }\n', ''), file: STYLES },
    M('Q10m', 'the facts are below the picture again', 'Q3',
      '    this.root.appendChild(this.top);\n    this.root.appendChild(this.wrap);\n',
      '    this.root.appendChild(this.wrap);\n    this.root.appendChild(this.top);\n'),
    M('Q12m', 'the tools stand last in their cell', 'Q12',
      '    this.head.insertBefore(acts, status);\n', '    this.head.appendChild(acts);\n'),
    { ...M('Q11m', 'the row above the picture grows with what it holds', 'Q3',
      '  grid-template-rows: 163.2px; gap:', '  gap:'), file: STYLES },
    M('Q7m', 'node names back at the tag size', 'Q5',
      "'font-size': px('--fs-body', 15),", "'font-size': px('--fs-tag', 15),"),
    { ...M('Q6m', 'an empty facts box is drawn as a bar', 'Q4',
      '.sg-facts:empty { display: none; }\n', ''), file: STYLES },
    { ...M('Q8m', 'the picture box is cut to the graph height token again', 'Q6',
      '.sg-canvas-wrap { position: relative; flex: 1 1 auto;', '.sg-canvas-wrap { position: relative; height: var(--graph-max-height);'),
      file: STYLES },
    { ...M('Q9m', 'the part does not grow into the result column', 'Q6',
      '.wk-graph > .sg-view { flex: 1 1 auto; min-height: 0; }\n', ''), file: STYLES },
    M('M11', 'Continue walks the start again, not the marking', 'K2',
      '    if (!name || this.state !== \'done\') return;\n    await this._step(name);\n',
      '    if (!name || this.state !== \'done\') return;\n    await this._step(this.chain[0]);\n'),
    M('M12', 'a node reached again is moved to the later step', 'K4',
      '        if (at.has(node.id)) continue;\n',
      '        if (at.has(node.id)) placed.splice(placed.indexOf(at.get(node.id)), 1);\n'),
    M('M13', 'a later step starts at the first column', 'K4',
      '    const stepBase = index === 0 || !seedLayers.length ? 0 : Math.max(...seedLayers);\n', '    const stepBase = 0;\n'),
    M('M14', 'a node does not carry its step', 'K4', '          step: index + 1,\n', '          step: 1,\n'),
    M('M15', 'Continue is live with nothing marked', 'K2',
      "    setDisabledReason(this.continueButton, !name ? 'End of chain' : (this.markings.count(name) ? '' : 'Mark a node'));\n",
      "    setDisabledReason(this.continueButton, '');\n"),
    M('M16', 'another part writing the same name is not seen', 'L1',
      '    for (const name of this.chain) this.markings.subscribe(name, () => { this._paths(); this._restyle(); });\n', ''),
    M('M17', 'the chain\'s end is not kept: a press past it writes a name of its own', 'L2',
      "  writes() { return this.chain[this.steps.length] || ''; }\n",
      "  writes() { return this.chain[this.steps.length] || 'extra'; }\n"),
    M('M18', 'every draw lays the whole picture out again', 'LM5',
      '    const full = this._relayout;\n', '    const full = true;\n'),
    M('B1', 'the part walks without its fan-out cap', 'D1',
      ' negative: step.negative, fanout_limit: this.fanoutLimit }, [],', ' negative: step.negative }, [],'),
    M('B2', 'the unsent lumps are not drawn', 'P1',
      '      if (!members.length && !rest) continue;\n', '      if (!members.length) continue;\n'),
    // Lead 11e5ea207: a bundle opens as one step from its node, the way it leaves.
    M('B3', 'a lump opens from the marking, not from its node', 'P2',
      'stepAlong({ positive: [node], predicate,', 'stepAlong({ positive: this.steps[index].positive, predicate,'),
    M('B3b', 'a lump opens both ways', 'P2',
      'farType: chip && chip.farType, direction }),', 'farType: chip && chip.farType }),'),
    M('B4', 'a lump says its far type but not its count', 'P1',
      "  return `${arrowed(lump)}\\n${lump.unsent && lump.more ? '+' : ''}${lump.count}${lump.more ? ' more' : ''} ${lump.farType}`;",
      '  return `${arrowed(lump)}\\n${lump.farType}`;'),
    M('B4b', 'a lump of a bundle the walk drew part of counts the whole bundle', 'P1',
      '(unsent.has(key) ? unsent.get(key).count - unsent.get(key).drawn : 0)', '(unsent.has(key) ? unsent.get(key).count : 0)'),
    M('B4c', 'a lump does not say the walk drew part of its bundle', 'P1', "${lump.unsent && lump.more ? '+' : ''}", ''),
    M('B5', 'the chips are read from a step\'s latest answer, an opening\'s too', 'P7',
      '  const walked = (step) => ((step && step.results) || []).find((r) => !r.opened) || {};\n',
      '  const walked = (step) => ((step && step.results) || []).slice(-1)[0] || {};\n'),
    M('B5b', 'an opened bundle still stands as a chip', 'P4',
      '      if (!at.has(b.node) || opened.has(key)) continue;\n', '      if (!at.has(b.node)) continue;\n'),
    M('B6', 'what an opened lump brings is drawn at once, not listed', 'P3',
      '      if (!this.fold.lumped.has(lump.key)) {\n', '      if (false) {\n'),
    M('B6b', 'opening a lump hides what the walk drew of it', 'PD',
      '          .filter((s) => s.key === lump.key && shown.has(s.to)).map((s) => s.to)));', '          .filter(() => false)));'),
    { ...M('B7', 'an opened lump still reads as unsent, and the walk does not guard what it opened', 'P6'),
      mutate: (t) => swap(swap(t, ' : Boolean(chip && chip.drawn), unsent: rest > 0,',
        ' : Boolean(chip && chip.drawn), unsent: true, step: 0,'),
        '    if (!step || this.state !== \'done\' || step.expand.includes(key)) return;\n',
        '    if (!step || this.state !== \'done\') return;\n') },
    M('B8', 'what an opening brings stands from the step\'s start, not one column on from its node', 'P8',
      '      const base = owner ? owner.layer : stepBase;\n', '      const base = stepBase;\n'),
    M('B9', 'an opened bundle\'s node counts as where the step stood', 'P9',
      '((step && step.results) || []).filter((r) => !r.opened).flatMap(', '((step && step.results) || []).flatMap('),
    M('B10', 'a cut opening is not said', 'PC', '      if (result.cut) cut.push(', '      if (result.cut && !result.opened) cut.push('),
    M('B11', 'an opening that brings nothing says nothing', 'PN',
      '        this.note = `No more ${lump.farType} · ${arrowed(lump)}`;\n', ''),
    M('B12', 'a bundle walked from a big lump\'s window lets what it brought into sight', 'PB',
      '    await this._expandKey(key);\n    if (this.state !== \'done\') return;\n    was.unfolded.add(key);',
      '    const owner = (this._view().lumps.find((l) => l.id === lumpId) || {}).owner;\n    if (owner && this.fold.big.get(owner)) this.fold.big.get(owner).delete(key);\n    await this._expandKey(key);\n    if (this.state !== \'done\') return;\n    was.unfolded.add(key);'),
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
    M('F5', 'Unfold never opens', 'N7', '    if (this._isFolded(id)) this._unfold(id);\n', '    if (false) this._unfold(id);\n'),
    M('F6', 'the fold is shared by every part on the page', 'N5',
      '  return { big: new Map(), lumped: new Map() };\n',
      '  return (globalThis.__sgFold ||= { big: new Map(), lumped: new Map() });\n'),
    M('F7', 'the fold\'s lump is a shape of its own', 'N6',
      "      { selector: 'node[kind = \"lump\"][level = \"big\"]', style: set({ 'font-weight': 600, 'border-width': 2.5,",
      "      { selector: 'node[kind = \"lump\"][level = \"big\"]', style: set({ shape: 'ellipse', 'font-weight': 600, 'border-width': 2.5,"),
    M('F8', 'the folded count is not said', 'N4',
      "    if (view.hidden) status.appendChild(this._el('div', 'sg-note', `Folded · ${unitText(view.hidden, 'node')}`));\n", ''),
    M('F9', 'the picture draws the folded nodes anyway', 'N3',
      '    nodes: layout.nodes.filter((n) => shown(n.id)),\n', '    nodes: layout.nodes,\n'),
    M('L1m', 'opening a big lump opens every branch\'s nodes, not the ticked', 'LM3',
      '        for (const value of picked) {', '        for (const value of lump.groups.flatMap((g) => g.members.map((x) => `${g.key}${PICK_SEP}${x}`))) {'),
    M('L2m', 'opening a small lump draws every member, not the ticked', 'P6',
      '        for (const m of members) {\n          opened.add(m);', '        for (const m of lump.members) {\n          opened.add(m);'),
    M('L3m', 'a node let out comes out open', 'LM4',
      '          this.fold.big.set(member, branchKeys(this.layout, member));\n', ''),
    M('L4m', 'an opening fits the view', 'LM5',
      '    else this._place(view, added);\n', '    else { this._place(view, added); cy.zoom(cy.zoom() * 1.1); }\n'),
    M('L5m', 'the lump left is not moved under what came out', 'LM6',
      '      if (left.nonempty() && first) left.position(', '      if (false) left.position('),
    M('L6m', 'a long list has no filter field', 'LM7', '    if (items.length > PICK_FILTER_AT) {\n', '    if (false) {\n'),
    M('L7m', 'Esc does not close the picker', 'LM7',
      "    this._onKey = (ev) => { if (ev && ev.key === 'Escape') this._closePicker(); };\n", '    this._onKey = () => {};\n'),
    M('L8m', 'All ticks nothing', 'LM8',
      '          r.cb.checked = all.checked;\n          for (const k of r.kids) k.cb.checked = all.checked;\n', ''),
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
    M('S5m', 'the first picture folds the unsent fan-outs too', 'NF',
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
    M('X1m', 'a node\'s name is not part of it again (lead 5f1eb137e)', 'X1',
      "        'text-events': 'yes', 'border-width': 1.5,", "        'border-width': 1.5,"),
    M('X2m', 'a press that wanders past the library\'s 4 px drags again (lead 5f1eb137e)', 'X2',
      '      boxSelectionEnabled: false, desktopTapThreshold: TAP_SLOP });', '      boxSelectionEnabled: false });'),
    M('Y1m', 'a new start keeps the last picture\'s marks (lead 10-07)', 'Y1',
      '    for (const name of this.chain.slice(1)) this.markings.clear(name);\n', ''),
    { ...M('Y2m', 'the same start shown again loses its marks', 'Y5'),
      mutate: (t) => swap(swap(t, '    for (const name of this.chain.slice(1)) this.markings.clear(name);\n', ''),
        '    if (opts.reuse && key === this.asked',
        '    for (const name of this.chain.slice(1)) this.markings.clear(name);\n    if (opts.reuse && key === this.asked') },
    M('Y3m', 'a new start clears every name on the page, not only its chain', 'Y4',
      'for (const name of this.chain.slice(1)) this.markings.clear(name);',
      'for (const name of this.markings.names().filter((n) => n !== this.chain[0])) this.markings.clear(name);'),
    M('U1m', 'a lump on its way reads as before (lead 10-07)', 'U1',
      'loading: Boolean(l.unsent) && this.expanding.includes(l.key),', 'loading: false,'),
    M('U2m', 'a lump reads Loading after its walk is answered', 'U3',
      '    if (this.steps !== steps) return;   // a new start was asked meanwhile\n    this.expanding = [];\n',
      '    if (this.steps !== steps) return;   // a new start was asked meanwhile\n'),
    { ...M('U3m', 'a lump pressed again on its way is asked again', 'U1'),
      mutate: (t) => swap(swap(t, "    if (!lump || this.state !== 'done') return;\n    // Not walked from",
        "    if (!lump) return;\n    // Not walked from"),
        "    if (!step || this.state !== 'done' || step.expand.includes(key)) return;\n",
        '    if (!step || step.expand.includes(key)) return;\n') },
    M('J0m', 'every view reads an empty start branch - the one question answered nowhere (lead 10-08)', 'J3',
      'startBranch(this.steps)', 'new Set()'),
    M('J1m', 'a lump\'s chosen view is not kept', 'J5', '    this.lumpSeen.kind.set(id, kind);\n', ''),
    M('J2m', 'a definition lump walks forward, not back along its predicate', 'J2',
      "direction: lump.direction === 'incoming' ? 'outgoing' : 'incoming' }),", 'direction: lump.direction }),'),
    M('J3m', 'the window is not sent', 'J2', '      ...(window ? { since:', '      ...(false ? { since:'),
    M('J4m', 'the lump does not carry its points', 'J4', '        spark: this._spark(l, lit), label:', "        spark: '', label:"),
    M('J5m', 'the table does not light the start branch', 'J5', 'rowLit: (row) => lit.has(row.id),', 'rowLit: null,'),
    M('J6m', 'a lump\'s walk is asked again at every switch', 'J5', '    if (!seen.data.has(lump.id)) {\n', '    if (true) {\n'),
    M('J7m', 'a new start keeps the lumps\' views', 'J9',
      '    this.lumpSeen = openLumpSeen();\n    this.pickedLump = null;\n    this.pathOff = new Set();\n', '    this.pathOff = new Set();\n'),
    M('J8m', 'the lump\'s list does not light the start branch', 'J1',
      'count: view.behind(m) || undefined, lit: lit.has(m) })) }) }));', 'count: view.behind(m) || undefined, lit: false })) }) }));'),
    M('LA1m', 'a big lump\'s words count all it hides again, not what one Open draws', 'LM11',
      'next: firsts.size + rest, behind: held.size - firsts.size,', 'next: held.size + rest, behind: 0,'),
    M('LA3m', 'a branch not sent, ticked, is not walked', 'PL',
      '          if (r.cb.checked && r.item.load) void r.item.load();\n', ''),
    M('LA4m', 'a branch being walked does not say so in its row', 'PL',
      "        if (r) { r.row.className += ' is-loading'; if (r.unfold) { r.unfold.textContent = LOADING; setDisabledReason(r.unfold, LOADING); } }\n", ''),
    M('PAm1', 'three marked open the Paths box too', 'PA3', '    if (marked.length !== 2) {\n', '    if (marked.length < 2) {\n'),
    M('PAm2', 'an unticked edge still walked', 'PA2', '.filter((p) => !this.pathOff.has(p))', ''),
    M('PAm3', 'a kind pressed unfolds nothing', 'PA4',
      '    if (kind) this._unfoldFor(new Set(kind.paths.flatMap((p) => p.nodes)));\n', ''),
    M('PAm4', 'a pressed kind\'s nodes not lit', 'PA4', "          n.toggleClass('is-path', Boolean(lit) && lit.nodes.has(id));\n", ''),
    M('PAm5', 'a marking written from outside does not open the box', 'PA1',
      '    for (const name of this.chain) this.markings.subscribe(name, () => { this._paths(); this._restyle(); });\n',
      '    for (const name of this.chain) this.markings.subscribe(name, () => this._restyle());\n'),
    M('PAm6', 'the edge list without its counts', 'PA1', "this._el('span', '', `${predicate} ${count}`)", "this._el('span', '', predicate)"),
    M('LA6m', 'next summed over the branches, shared nodes twice', 'LM13',
      'next: firsts.size + rest, behind: held.size - firsts.size, bound: rest > 0,',
      'next: groups.reduce((n, g) => n + g.members.length, 0) + rest, behind: held.size - firsts.size, bound: rest > 0,'),
    M('LA7m', 'Open counts the ticks, a shared node twice', 'LM13',
      '      const n = new Set(chosenOf().map((value) => value.split(PICK_SEP).pop())).size;', '      const n = chosenOf().length;'),
    M('LA8m', 'a bundle not walked: next said as exact', 'LM14', 'bound: rest > 0,', 'bound: false,'),
    M('LA9m', 'the window\'s sub line not the lump\'s words', 'LM13',
      '`Behind ${this._labelOf(lump.owner)}`, nextWords(lump), open,', '`Behind ${this._labelOf(lump.owner)}`, `${lump.count} folded`, open,'),
    M('AWm1', 'a node an opening brought said walked', 'AW1',
      '          unwalked: Boolean(result.opened) && node.id !== keyParts(result.opened).node,', '          unwalked: false,'),
    M('AWm2', 'every node said not walked', 'AW1',
      '          unwalked: Boolean(result.opened) && node.id !== keyParts(result.opened).node,', '          unwalked: true,'),
    M('AWm3', 'a node walked from still said not walked: dashed again once its branches are all open', 'AW2',
      "  for (const step of steps || []) {\n    for (const r of step.results || []) if (r.opened && at.has(keyParts(r.opened).node) && !keyParts(r.opened).predicate) at.get(keyParts(r.opened).node).unwalked = false;\n  }\n", ''),
    M('AWm4', 'walked, its branches not folded into its big lump', 'AW2',
      '      this.fold.big.set(lump.owner, branchKeys(this.layout, lump.owner));\n      this.render();\n', '      this.render();\n'),
    M('LA5m', 'one node ticked lets its whole branch out', 'LM12',
      '          this.fold.lumped.get(key).add(member);\n',
      '          for (const x of lump.groups.find((g) => g.key === key).members) this.fold.lumped.get(key).add(x);\n'),
    M('LA2m', 'a branch ticked in the window comes out a small lump again, not its nodes', 'LM10',
      '          this.fold.lumped.get(key).add(member);\n', ''),
    M('OV1m', 'what a lump lets out is stacked a row apart whatever its height (owner 10-08)', 'S1',
      '      const stepOf = (id) => Math.max(GEOMETRY.row, cy.getElementById(id).height() + GEOMETRY.row / 4);',
      '      const stepOf = () => GEOMETRY.row;'),
    M('RT1m', 'a big lump\'s row Trend opens the key but shows its list', 'S2',
      '        this.lumpSeen.kind.set(`${GROUP_LUMP}${key}`, FOLD_VIEWS[2]);\n', ''),
    M('VL1m', 'a lump of values is treated as one to pick a type for (lead mutant 8504654f0)', 'S3',
      '    if (!members.length || valueAttributes(members).length) return { nodes: members };',
      '    if (!members.length) return { nodes: members };'),
    M('O1m', 'a cut walk says nothing of the cut', 'O1', '    if (data.cut && data.cut.length) said.push(truncatedWords(data.cut));\n', ''),
    M('O5m', 'a lump\'s walk says only the node cut, as before (lead 161757c35)', 'O5',
      'cut: cutBudgets(res.truncatedAxes, res.limits) }', "cut: cutBudgets((res.truncatedAxes || []).filter((a) => a === 'nodes'), res.limits) }"),
    M('O6m', 'the nodes left bare are not said', 'O5', "    if (got.noValue) said.push(`${got.noValue} without ${y || 'values'}`);\n", ''),
    M('O2m', 'a refused walk reads as no points', 'O2',
      "    if (data.state === 'failed') { box.appendChild(this._el('div', 'sg-fail', `${FAILED} · ${data.reason}`)); return box; }\n", ''),
    M('J9m', 'a definition lump\'s walk collects everything, not the owner\'s type', 'J2',
      '      farType: owner && owner.type, direction:', '      direction:'),
    M('O3m', 'the values left out are not counted', 'O3', '    if (got.notNumber) said.push(`${got.notNumber} not numbers`);\n', ''),
    M('I1m', 'the part picks the type for the operator', 'I1',
      'picked: this._pickedFrom(lump.id, from) };', 'picked: this._pickedFrom(lump.id, from) || this._pickChoices(from)[0] };'),
    M('I2m', 'a picked lump\'s walk collects everything on the way, not the type picked', 'I2',
      '        collect: [pick.picked] } : null };', '        } : null };'),
    M('I3m', 'the pick is not kept', 'I3', '    rememberPick(this.storage, key, { from: type });\n', ''),
    M('I1n', 'Points from offers the members\' own type now that a route can come back to it', 'I1',
      '        .filter((type) => !from.includes(type))\n', ''),
    M('I5m', 'Points from offers only the types the picture already shows', 'I5',
      '        .filter((type) => from.some(',
      '        .filter((type) => this.layout.nodes.some((n) => n.type === type) && from.some('),
    // The captured declaration less one predicate; the part is not touched (lead).
    { id: 'ID1m', what: 'the declaration loses measured: Points from no longer reaches measurement_event', catches: 'I1',
      declaration: { ...FOLD_DECL, predicates: FOLD_DECL.predicates.filter((p) => p.name !== 'measured') } },
    M('Z2m', 'Fit keeps the floor', 'Z2', 'if (this.cy) this.cy.fit(undefined, GEOMETRY.fitPad);', 'if (this.cy) this._firstFit();'),
    M('Z3m', 'the first draw is not fitted', 'Z1', '    if (full) this._fitPending = true;\n', ''),
    M('Z4m', 'a change of size fits the picture again', 'Z4', '    else this.cy.resize();\n', '    else this._firstFit();\n'),
    M('Z5m', 'a change of size leaves the picture at its old size', 'Z4', '    else this.cy.resize();\n', ''),
    M('EQ1m', 'the label stays the predicate alone', 'EQ1', "label: 'data(tag)'", "label: 'data(predicate)'"),
    M('EQ2m', 'the label says every qualifier', 'EQ1', 'qualifierWords(e.qualifiers, LABEL_QUALIFIERS)', 'qualifierWords(e.qualifiers)'),
    M('EQ3m', 'the info box drops the qualifiers', 'EQ3', ', ...qualifierWords(edge.qualifiers)].join', '].join'),
    M('EQ4m', 'the picture keeps no qualifiers', 'EQ1', '          qualifiers: edgeQualifiers(edge) || {},\n', '          qualifiers: {},\n'),
  ];
  const scored = await scoreMutants(MUTANTS, async (mu) => {
    const mutate = mu.mutate || ((t) => swap(t, mu.from, mu.to));
    const loaded = mu.declaration ? real : (await loadWithProbe(mu.file || SUBJECT, { mutate })).module;
    const quiet = console.log;
    console.log = () => {};
    try {
      if (mu.file === STYLES) return await suite(real, createWalkBoxWalk, loaded.WALK_CSS, FOLD_DECL, mu.catches);
      return mu.file ? await suite(real, loaded.createWalkBoxWalk, REAL_CSS, FOLD_DECL, mu.catches)
        : await suite(loaded, undefined, undefined, mu.declaration, mu.catches);
    } finally { console.log = quiet; }
  }, { baselineNames: base.names,
       title: '\n  [mutants] - each must be caught by the check it names.' });
  pass += MUTANTS.length - scored.wrong;
  for (let i = 0; i < scored.wrong; i += 1) failures.push(`mutant verdict ${i + 1}`);

  if (process.argv.includes('--control')) {
    const asks = [...new Map(MUTANTS.map((mu) => [JSON.stringify([].concat(mu.catches)), mu.catches])).values()];
    const t0 = Date.now();
    let red = 0;
    for (const only of asks) {
      const quiet = console.log;
      console.log = () => {};
      let got;
      try { got = await suite(real, createWalkBoxWalk, REAL_CSS, FOLD_DECL, only); } finally { console.log = quiet; }
      if (got.failures.length) {
        red += 1;
        failures.push(`control ${[].concat(only).join('/')}`);
        console.log(`  CONTROL ${[].concat(only).join('/')} red on unmutated code: ${got.failures.slice(0, 2).join(' | ')}`);
      } else pass += 1;
    }
    console.log(`\n  [control] ${asks.length} mutant subsets on unmutated code, ${red} red, ${Math.round((Date.now() - t0) / 1000)} s`);
  }
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
