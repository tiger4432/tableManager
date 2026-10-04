// Subgraph viewer — a start, the whole walk from it, as a picture (lead c9bf53033; owner 10-01:
// 「걷기 ui 랑 동일한데 start 만 있고 start 에서 걸어 닿는 모든 서브그래프 가져와서 시각적으로」), continued by
// marking (lead f6fc6ba66; owner 「묶은거 펼치고 거기서 특정 점 마킹해서 그 부분에서 다시 서브 그래프 잇고」):
//
//   marking 0 --walk--> subgraph --Mark--> marking 1 --Continue--> subgraph --Mark--> marking 2 ...
//
// 🔴 The markings live in the store handed in (`deps.markings`), never in this part; the chain of names is
//    the part's declaration (`deps.chain`): the first is read, each next one is written in turn.
// 🔴 It asks the walk the page already asks, through the same wire (`createWalkBoxWalk`, `deps.walk`) — a
//    marking and nothing else: no follow, no collect, no budget of its own.
// 🔴 It judges nothing the server or the declaration already said: the layer is the node's `depth`,
//    static is `staticTypes(declaration)`, truncation is `cutBudgets` — the doors the table walks through.
// 🔴 Bundles (lead 1d07f1dae, server b1245bab9): the walk carries `fanout_limit`; a fan-out over it comes back
//    in `bundles` and stands as a chip under its node; a chip pressed adds `expand` to that step's walk.

import { bareName, staticTypes, cutBudgets } from './derive.js';
import { drawLayeredGraph, slotXY } from '../layered_graph.js';
import { SIGN } from '../rnd_board/marking_store.js';
import { setDisabledReason } from '../disabled_reason.js';
import { unitText } from '../ui_words.js';
// The look travels with the part (the walk page's rule): one stamp, one sheet per document.
import { ensureWalkStyles } from './styles.js';

// Geometry on the 3.4 grid (ui-design-system §3).
/** The viewer's own geometry (lead 65754c39a: each screen declares it; the template places by it). */
const GEOMETRY = Object.freeze({ margin: 20.4, gapX: 238, gapY: 27.2, r: 6.8, labelDx: 10.2 });
const MARGIN = GEOMETRY.margin;
const LAYER_GAP_X = GEOMETRY.gapX;
const LABEL_DX = GEOMETRY.labelDx;
/** How many type colours there are; a type's colour is its declaration index modulo this. */
export const TYPE_COLOURS = 9;
/** The fan-out cap the part walks with unless its declaration says another (lead c9bf53033 · 1d07f1dae). */
export const DEFAULT_FANOUT_LIMIT = 20;

/** The signed ids of a marking, as the walk takes them. */
export function seedsOf(entries) {
  const positive = [];
  const negative = [];
  for (const [id, sign] of entries || []) {
    if (sign === SIGN.CASE) positive.push(id);
    else if (sign === SIGN.CONTROL) negative.push(id);
  }
  return { positive, negative };
}

/**
 * Where everything goes, decided from the walks' answers and the declaration only.
 *
 * One step is one marking walked; a step may hold more than one answer — each bundle expanded is the
 * same walk asked again with that bundle drawn. Step 1's layer is the node's `depth`; a later step's
 * layers carry on from the marked points: `depth + the furthest column its seeds already stand in`. A
 * node is drawn once, where it was first reached, and remembers that step. Inside a column, arrival order
 * (the server's order, answer after answer); a node's bundles (its step's latest answer) take the rows
 * right under it. Same input, same picture. A node without a depth is counted, not placed — its distance
 * is not this screen's guess.
 *
 * @param {Array<{results: object[], seeds?: string[]}>} steps
 * @param {object[]} entities  the declaration's entities
 */
export function subgraphLayout(steps, entities) {
  const statics = staticTypes(entities);
  // Colour follows the declaration's order, so a type keeps its colour from walk to walk; a type the
  // declaration does not name takes the next index in the order it first appears.
  const order = (entities || []).map((e) => bareName(e && e.type));
  const colourOf = new Map(order.map((type, i) => [type, i]));
  const latest = (step) => {
    const all = (step && step.results) || [];
    return all[all.length - 1] || {};
  };
  // The bundles still standing: each step's latest answer says which fan-outs it did not draw.
  const bundlesOf = new Map();
  (steps || []).forEach((step, index) => {
    for (const b of latest(step).bundles || []) {
      if (!bundlesOf.has(b.node)) bundlesOf.set(b.node, []);
      bundlesOf.get(b.node).push({ ...b, step: index });
    }
  });
  const rows = new Map();
  const at = new Map();
  const placed = [];
  const chips = [];
  let unplaced = 0;
  (steps || []).forEach((step, index) => {
    const seedLayers = (step.seeds || []).map((id) => at.get(id)).filter(Boolean).map((n) => n.layer);
    const base = index === 0 || !seedLayers.length ? 0 : Math.max(...seedLayers);
    for (const result of step.results || []) {
      for (const node of (Array.isArray(result.nodes) ? result.nodes : [])) {
        const type = bareName(node.type);
        if (!colourOf.has(type)) colourOf.set(type, colourOf.size);
        if (at.has(node.id)) continue;
        if (!Number.isFinite(node.depth)) { unplaced += 1; continue; }
        const layer = base + node.depth;
        let row = rows.get(layer) || 0;
        const one = {
          id: node.id,
          type,
          label: node.label || node.id,
          depth: node.depth,
          layer,
          step: index + 1,
          ...slotXY(GEOMETRY, layer, row),
          static: statics.has(type),
          colour: colourOf.get(type) % TYPE_COLOURS,
          keys: node.keys || {},
          attributes: node.attributes || {},
          // Each world's value of each attribute (server 351b23ef8), drawn like an edge's worlds.
          attributesByWorld: node.attributes_by_world || {},
        };
        at.set(node.id, one);
        placed.push(one);
        row += 1;
        for (const b of bundlesOf.get(node.id) || []) {
          chips.push({
            step: b.step, node: b.node, predicate: b.predicate, direction: b.direction,
            farType: bareName(b.far_type), count: b.count,
            key: `${b.node}|${b.predicate}|${b.direction}`,
            x: one.x + LABEL_DX, y: slotXY(GEOMETRY, layer, row).y,
          });
          row += 1;
        }
        rows.set(layer, row);
      }
    }
  });
  // Edges once every node of every answer stands, so an edge an expansion completes is drawn, not lost.
  const drawn = [];
  const edgeSeen = new Set();
  const missing = new Set();
  const cut = [];
  (steps || []).forEach((step, index) => {
    for (const result of step.results || []) {
      for (const edge of (Array.isArray(result.edges) ? result.edges : [])) {
        if (edgeSeen.has(edge.id)) continue;
        const from = at.get(edge.source);
        const to = at.get(edge.target);
        if (!from || !to) { missing.add(edge.id); continue; }
        edgeSeen.add(edge.id);
        missing.delete(edge.id);
        drawn.push({
          id: edge.id, source: edge.source, target: edge.target,
          predicate: edge.predicate_label || edge.predicate || '',
          occurredAt: edge.occurred_at || '',
          // Each world that says it, with its evidence (lead ee0f66e7b): one line in the picture, one row each here.
          byWorld: Array.isArray(edge.by_world) ? edge.by_world : [],
          x1: from.x, y1: from.y, x2: to.x, y2: to.y,
        });
      }
    }
    const last = latest(step);
    if (last.cut) cut.push({ step: index + 1, budgets: cutBudgets(last.truncatedAxes, last.limits) });
  });
  const counts = new Map();
  for (const node of placed) counts.set(node.type, (counts.get(node.type) || 0) + 1);
  const legend = [...counts.entries()]
    .sort((a, b) => colourOf.get(a[0]) - colourOf.get(b[0]))
    .map(([type, count]) => ({ type, count, colour: colourOf.get(type) % TYPE_COLOURS, static: statics.has(type) }));
  return {
    nodes: placed,
    edges: drawn,
    chips,
    legend,
    unplaced,
    loose: missing.size,
    cut,
    width: MARGIN * 2 + Math.max(0, ...placed.map((n) => n.x)) + LAYER_GAP_X,
    height: MARGIN * 2 + Math.max(0, ...placed.map((n) => n.y), ...chips.map((c) => c.y)),
  };
}

/**
 * What folding hides (lead 43a738d58 ③, view only): walking from where the walks stood — the seeds and every
 * node the server put at depth 0 (a seed can have no edge of its own while a depth-0 twin carries them all) — in
 * the picture's direction (never to a lower layer; a walk's depth can stay put along an edge) over the drawn
 * edges, the nodes no longer reached once the folded nodes are not walked past.
 * A node reached another way stays; a folded node itself stays; a node no start reaches is untouched.
 */
export function foldedAway(layout, folded, seeds) {
  const layerOf = new Map(layout.nodes.map((n) => [n.id, n.layer]));
  const starts = [...(seeds || []), ...layout.nodes.filter((n) => n.depth === 0).map((n) => n.id)];
  const next = new Map();
  for (const e of layout.edges) {
    for (const [a, b] of [[e.source, e.target], [e.target, e.source]]) {
      if (!(layerOf.get(b) >= layerOf.get(a))) continue;
      if (!next.has(a)) next.set(a, []);
      next.get(a).push(b);
    }
  }
  const reach = (stop) => {
    const seen = new Set(starts.filter((id) => layerOf.has(id)));
    const queue = [...seen];
    while (queue.length) {
      const id = queue.shift();
      if (stop.has(id)) continue;
      for (const to of next.get(id) || []) {
        if (!seen.has(to)) { seen.add(to); queue.push(to); }
      }
    }
    return seen;
  };
  const kept = reach(folded);
  return new Set([...reach(new Set())].filter((id) => !kept.has(id)));
}

/**
 * The «+N» chip on the picture, for both kinds (lead 015ef2aab): a fan-out the walk did not draw (`press`
 * asks the walk again) and a branch this view folded (`press` only opens it). One shape, one look.
 */
export function plusChip({ x, y, count, word, data, press }) {
  return { x, y, text: `+${count} ${word}`, attrs: { class: 'sg-bundle', ...data }, onPress: press };
}

/**
 * The layout as drawn with these nodes folded: the hidden nodes, their edges and their bundles left out, a
 * folded node's own bundles too (they branch from it), and one «+N folded» spot per folded node still in sight
 * — where the first node it hides stood. The counts above the picture stay the walk's.
 */
export function foldView(layout, folded, seeds) {
  const hidden = foldedAway(layout, folded, seeds);
  const gone = (id) => hidden.has(id);
  const folds = [];
  for (const id of folded) {
    if (gone(id)) continue;
    const under = foldedAway(layout, new Set([id]), seeds);
    const first = layout.nodes.filter((n) => under.has(n.id))
      .sort((a, b) => a.layer - b.layer || a.y - b.y)[0];
    if (first) folds.push({ node: id, count: under.size, x: first.x, y: first.y });
  }
  return {
    nodes: layout.nodes.filter((n) => !gone(n.id)),
    edges: layout.edges.filter((e) => !gone(e.source) && !gone(e.target)),
    chips: layout.chips.filter((c) => !gone(c.node) && !folded.has(c.node)),
    folds,
    hidden: hidden.size,
  };
}

/** The facts the walks brought for one node: its keys, its attributes, and every edge touching it. */
export function nodeFacts(layout, id) {
  const node = layout.nodes.find((n) => n.id === id);
  if (!node) return null;
  const labelOf = new Map(layout.nodes.map((n) => [n.id, n.label]));
  const edges = layout.edges
    .filter((e) => e.source === id || e.target === id)
    .map((e) => ({
      out: e.source === id,
      predicate: e.predicate,
      other: labelOf.get(e.source === id ? e.target : e.source),
      occurredAt: e.occurredAt,
      byWorld: e.byWorld,
    }));
  return { node, edges };
}

export class SubgraphView {
  /**
   * @param {HTMLElement} mount
   * @param {{doc?: Document, walk: Function, entities?: () => object[],
   *          markings: import('../rnd_board/marking_store.js').MarkingStore, chain: string[],
   *          fanoutLimit?: number, worldChips?: boolean}} deps
   *   `walk` is the page's `createWalkBoxWalk` function; `entities` reads the declaration the page holds;
   *   `chain` names the markings: the first is the start, each next one takes the marks of a step.
   *   `fanoutLimit` (declaration, default DEFAULT_FANOUT_LIMIT): a fan-out over it comes back as a bundle chip.
   *   `worldChips`: the page reads several worlds, so each fact says which (lead 99032248f).
   */
  constructor(mount, deps = {}) {
    if (!mount) throw new Error('SubgraphView needs a mount element');
    if (!deps.markings || !Array.isArray(deps.chain) || !deps.chain.length) {
      throw new Error('SubgraphView needs a marking store and a chain of marking names');
    }
    this.mount = mount;
    this.doc = deps.doc || mount.ownerDocument;
    this.walk = deps.walk;
    this.entities = deps.entities || (() => []);
    this.markings = deps.markings;
    this.chain = deps.chain.slice();
    this.fanoutLimit = Number.isFinite(deps.fanoutLimit) ? deps.fanoutLimit : DEFAULT_FANOUT_LIMIT;
    this.worldChips = Boolean(deps.worldChips);
    ensureWalkStyles(this.doc);
    this.root = this.doc.createElement('div');
    this.root.className = 'sg-view';
    this.mount.appendChild(this.root);
    this.state = 'idle';
    this.reason = '';
    this.steps = [];
    this.layout = null;
    this.selected = null;
    this.asked = '';
    // The nodes this view folds (lead 43a738d58 ③): this instance's, never a module's, never a marking.
    this.folded = new Set();
    // Another part writing the same name is seen here: same name, same marking.
    for (const name of this.chain) this.markings.subscribe(name, () => this._restyle());
  }

  /** The name the next Mark writes, or '' once the chain is used up. */
  writes() { return this.chain[this.steps.length] || ''; }

  /** Walk from the chain's first marking and draw it. `reuse`: the same marking already drawn is not asked again. */
  async show(opts = {}) {
    const key = JSON.stringify(this.markings.entries(this.chain[0]));
    if (opts.reuse && key === this.asked && this.state === 'done') return;
    this.asked = key;
    this.steps = [];
    this.layout = null;
    this.selected = null;
    this.folded = new Set();
    await this._step(this.chain[0]);
  }

  /** Every seed the steps walked from - where the fold's walk starts. */
  _seeds() { return this.steps.flatMap((s) => s.seeds); }

  /** Fold or open the branches beyond one node. The picture is redrawn; nothing is walked again. */
  toggleFold(id) {
    if (this.folded.has(id)) this.folded.delete(id); else this.folded.add(id);
    this.render();
  }

  /** Walk from the marking the last step's marks wrote, and draw it on the same picture. */
  async continueWalk() {
    const name = this.writes();
    if (!name || this.state !== 'done') return;
    await this._step(name);
  }

  async _step(name) {
    const seeds = seedsOf(this.markings.entries(name));
    if (!seeds.positive.length) {
      if (!this.steps.length) { this.state = 'empty'; this.render(); }
      return;
    }
    const step = { marking: name, seeds: [...seeds.positive, ...seeds.negative],
      positive: seeds.positive, negative: seeds.negative, expand: [], results: [] };
    await this._ask(step, [], (res) => [...this.steps, { ...step, results: [res] }]);
  }

  /** Draw one bundle a step left undrawn: the same walk asked again with it expanded, on the same picture. */
  async expandBundle(index, key) {
    const step = this.steps[index];
    if (!step || this.state !== 'done' || step.expand.includes(key)) return;
    const expand = [...step.expand, key];
    await this._ask(step, expand, (res) => this.steps.map((s, i) => (
      i === index ? { ...s, expand, results: [...s.results, res] } : s)));
  }

  /** One walk of a step's marking, with the cap this part declares; `next` builds the steps from the answer. */
  async _ask(step, expand, next) {
    const steps = this.steps;
    this.state = 'running';
    this.render();
    const res = await this.walk({ positive: step.positive, negative: step.negative,
      fanout_limit: this.fanoutLimit, expand });
    if (this.steps !== steps) return;   // a new start was asked meanwhile
    if (res && res.ok) {
      this.steps = next(res);
      this.layout = subgraphLayout(this.steps, this.entities());
      this.state = 'done';
    } else {
      this.state = 'failed';
      this.reason = (res && res.message) || '';
    }
    this.render();
  }

  _el(tag, cls, text) {
    const node = this.doc.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = String(text);
    return node;
  }

  /** A node's class: type, shape, the step it came from, and whether it is picked, marked or a seed. */
  _classOf(node) {
    const name = this.writes();
    const seeded = this.steps.some((s) => s.seeds.includes(node.id));
    return `sg-node sg-type-${node.colour} sg-step-${node.step}`
      + (node.static ? ' is-static' : '')
      + (seeded ? ' is-seed' : '')
      + (name && this.markings.signOf(name, node.id) !== SIGN.ABSENT ? ' is-marked' : '')
      + (node.id === this.selected ? ' is-selected' : '');
  }

  render() {
    this.root.textContent = '';
    this._groups = new Map();
    this.continueButton = null;
    if (this.state === 'empty') { this.root.appendChild(this._el('div', 'sg-note', 'Nothing marked')); return; }
    if (this.state === 'failed') { this.root.appendChild(this._el('div', 'sg-fail', `Failed · ${this.reason}`)); }
    if (this.state === 'running') this.root.appendChild(this._el('div', 'sg-note', 'Walking'));
    if (!this.layout) return;
    const view = this.layout;
    this.root.appendChild(this._el('div', 'sg-counts', `Nodes ${view.nodes.length} · Edges ${view.edges.length}`));
    for (const one of view.cut) {
      const where = this.steps.length > 1 ? `step ${one.step} · ` : '';
      this.root.appendChild(this._el('div', 'sg-trunc', `Truncated · ${where}${one.budgets.join(' · ')}`));
    }
    if (view.unplaced) this.root.appendChild(this._el('div', 'sg-note', `No depth · ${view.unplaced} nodes`));
    if (view.loose) this.root.appendChild(this._el('div', 'sg-note', `Not drawn · ${view.loose} edges`));
    const shown = foldView(view, this.folded, this._seeds());
    if (shown.hidden) this.root.appendChild(this._el('div', 'sg-note', `Folded · ${unitText(shown.hidden, 'node')}`));

    const bar = this._el('div', 'sg-bar');
    const legend = this._el('div', 'sg-legend');
    for (const item of view.legend) {
      const chip = this._el('span', `sg-chip sg-type-${item.colour}`);
      chip.setAttribute('data-type', item.type);
      chip.appendChild(this._el('span', `sg-swatch${item.static ? ' is-static' : ''}`));
      chip.appendChild(this._el('span', '', `${item.type} ${item.count}`));
      legend.appendChild(chip);
    }
    bar.appendChild(legend);
    const go = this._el('button', 'sg-continue', 'Continue');
    go.setAttribute('type', 'button');
    if (go.addEventListener) go.addEventListener('click', () => { this.continueWalk(); });
    this.continueButton = go;
    bar.appendChild(go);
    this.root.appendChild(bar);

    // Declared into the one layered drawer (lead 65754c39a): the viewer's classes, data, shapes and chips.
    const { box, groups } = drawLayeredGraph(this.doc, {
      geometry: GEOMETRY, boxClass: 'sg-box', svgClass: 'sg-graph', width: view.width, height: view.height,
      edges: shown.edges.map((edge) => ({
        x1: edge.x1, y1: edge.y1, x2: edge.x2, y2: edge.y2,
        attrs: { class: 'sg-edge', 'data-predicate': edge.predicate },
      })),
      nodes: shown.nodes.map((node) => ({
        id: node.id, x: node.x, y: node.y, label: node.label,
        shape: node.static ? 'rect' : 'circle',
        attrs: { class: this._classOf(node), 'data-node': node.id, 'data-depth': node.depth, 'data-step': node.step },
        onPress: () => this.press(node.id),
      })),
      // A fan-out the walk did not draw, under its node: press it and that bundle is drawn. A folded branch,
      // where it stood: press it and it opens. Both are one chip (`plusChip`).
      texts: [
        ...shown.chips.map((chip) => plusChip({ x: chip.x, y: chip.y, count: chip.count, word: chip.farType,
          data: { 'data-bundle': chip.key, 'data-step': chip.step + 1 },
          press: () => { this.expandBundle(chip.step, chip.key); } })),
        ...shown.folds.map((fold) => plusChip({ x: fold.x, y: fold.y, count: fold.count, word: 'folded',
          data: { 'data-fold': fold.node }, press: () => { this.toggleFold(fold.node); } })),
      ],
    });
    for (const node of shown.nodes) this._groups.set(node.id, { group: groups.get(node.id), node });
    this.root.appendChild(box);
    this.factsBox = this._facts();
    this.root.appendChild(this.factsBox);
    this._restyle();
  }

  _facts() {
    const box = this._el('div', 'sg-facts');
    this.markButton = null;
    const facts = this.layout && this.selected ? nodeFacts(this.layout, this.selected) : null;
    if (!facts) return box;
    box.appendChild(this._el('div', 'sg-facts-head', `${facts.node.label} · ${facts.node.type}`));
    // A press on the node only picks it (owner 10-03, lead 9dc2a5695); marking for Continue is this button.
    // Folding is its own press too. Both stand first, so a box capped in height shows them before the facts.
    const id = facts.node.id;
    const acts = this._el('div', 'sg-facts-acts');
    const mark = this._el('button', 'sg-mark', 'Mark');
    mark.setAttribute('type', 'button');
    mark.setAttribute('data-mark-node', id);
    if (mark.addEventListener) mark.addEventListener('click', () => { this.toggleMark(id); });
    this.markButton = mark;
    acts.appendChild(mark);
    const folded = this.folded.has(id);
    if (folded || foldedAway(this.layout, new Set([id]), this._seeds()).size) {
      const fold = this._el('button', 'sg-fold', folded ? 'Unfold' : 'Fold branches');
      fold.setAttribute('type', 'button');
      fold.setAttribute('data-fold-node', id);
      if (fold.addEventListener) fold.addEventListener('click', () => { this.toggleFold(id); });
      acts.appendChild(fold);
    }
    box.appendChild(acts);
    for (const [name, value] of Object.entries(facts.node.keys)) {
      box.appendChild(this._el('div', 'sg-fact', `${name} ${value}`));
    }
    for (const [name, value] of Object.entries(facts.node.attributes)) {
      box.appendChild(this._el('div', 'sg-fact', `${name} ${value}`));
      this._worldRows(box, facts.node.attributesByWorld[name], (said) => [said.value, said.source_who, said.occurred_at]);
    }
    for (const edge of facts.edges) {
      box.appendChild(this._el('div', 'sg-fact',
        `${edge.out ? '→' : '←'} ${edge.predicate} · ${edge.other}${edge.occurredAt ? ` · ${edge.occurredAt}` : ''}`));
      this._worldRows(box, edge.byWorld, (said) => [said.source_who, said.occurred_at]);
    }
    return box;
  }

  /** Under a fact, when the walk reads several worlds, a row per world that says it: its chip, then what it says. */
  _worldRows(box, saids, words) {
    if (!this.worldChips) return;
    for (const said of saids || []) {
      const row = this._el('div', 'sg-fact sg-fact--world');
      row.appendChild(this._el('span', 'sg-world', said.world));
      row.appendChild(this._el('span', '', words(said).filter((word) => word != null && word !== '').join(' · ')));
      box.appendChild(row);
    }
  }

  /** The marks, the pick and Continue follow the store without redrawing the picture (the box keeps its scroll). */
  _restyle() {
    for (const { group, node } of (this._groups || new Map()).values()) group.setAttribute('class', this._classOf(node));
    const name = this.writes();
    if (this.markButton && this.selected) {
      const on = Boolean(name) && this.markings.signOf(name, this.selected) !== SIGN.ABSENT;
      this.markButton.setAttribute('aria-pressed', String(on));
      this.markButton.className = `sg-mark${on ? ' is-on' : ''}`;
      setDisabledReason(this.markButton, name ? '' : 'End of chain');
    }
    if (!this.continueButton) return;
    setDisabledReason(this.continueButton, !name ? 'End of chain' : (this.markings.count(name) ? '' : 'Mark a node'));
  }

  /** A press on a node: its facts, nothing else - marking is the Mark button (owner 10-03). */
  press(id) {
    this.select(id);
  }

  /** Mark or unmark one node in the marking this step writes; the store tells every part that reads it. */
  toggleMark(id) {
    const name = this.writes();
    if (name) this.markings.toggle(name, id, SIGN.CASE);
  }

  /** Pick a node: the list under the picture is swapped; the picture is not redrawn. */
  select(id) {
    this.selected = id;
    const next = this._facts();
    if (this.factsBox && this.factsBox.parentNode === this.root) {
      this.root.insertBefore(next, this.factsBox);
      this.root.removeChild(this.factsBox);
    } else {
      this.root.appendChild(next);
    }
    this.factsBox = next;
    this._restyle();
  }
}
