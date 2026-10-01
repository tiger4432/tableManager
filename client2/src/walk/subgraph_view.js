// Subgraph viewer — a start, the whole walk from it, as a picture (lead c9bf53033; owner 10-01:
// 「걷기 ui 랑 동일한데 start 만 있고 start 에서 걸어 닿는 모든 서브그래프 가져와서 시각적으로」), continued by
// marking (lead f6fc6ba66; owner 「묶은거 펼치고 거기서 특정 점 마킹해서 그 부분에서 다시 서브 그래프 잇고」):
//
//   marking 0 --walk--> subgraph --press--> marking 1 --Continue--> subgraph --press--> marking 2 ...
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
import { SIGN } from '../rnd_board/marking_store.js';
import { setDisabledReason } from '../disabled_reason.js';
// The look travels with the part (the walk page's rule): one stamp, one sheet per document.
import { ensureWalkStyles } from './styles.js';

const SVG_NS = 'http://www.w3.org/2000/svg';
// Geometry on the 3.4 grid (ui-design-system §3).
const MARGIN = 20.4;
const LAYER_GAP_X = 238;
const NODE_GAP_Y = 27.2;
const NODE_R = 6.8;
const LABEL_DX = 10.2;
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
          x: MARGIN + layer * LAYER_GAP_X,
          y: MARGIN + row * NODE_GAP_Y,
          static: statics.has(type),
          colour: colourOf.get(type) % TYPE_COLOURS,
          keys: node.keys || {},
          attributes: node.attributes || {},
        };
        at.set(node.id, one);
        placed.push(one);
        row += 1;
        for (const b of bundlesOf.get(node.id) || []) {
          chips.push({
            step: b.step, node: b.node, predicate: b.predicate, direction: b.direction,
            farType: bareName(b.far_type), count: b.count,
            key: `${b.node}|${b.predicate}|${b.direction}`,
            x: one.x + LABEL_DX, y: MARGIN + row * NODE_GAP_Y,
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
    }));
  return { node, edges };
}

export class SubgraphView {
  /**
   * @param {HTMLElement} mount
   * @param {{doc?: Document, walk: Function, entities?: () => object[],
   *          markings: import('../rnd_board/marking_store.js').MarkingStore, chain: string[],
   *          fanoutLimit?: number}} deps
   *   `walk` is the page's `createWalkBoxWalk` function; `entities` reads the declaration the page holds;
   *   `chain` names the markings: the first is the start, each next one takes the presses of a step.
   *   `fanoutLimit` (declaration, default DEFAULT_FANOUT_LIMIT): a fan-out over it comes back as a bundle chip.
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
    // Another part writing the same name is seen here: same name, same marking.
    for (const name of this.chain) this.markings.subscribe(name, () => this._restyle());
  }

  /** The name the next press writes, or '' once the chain is used up. */
  writes() { return this.chain[this.steps.length] || ''; }

  /** Walk from the chain's first marking and draw it. `reuse`: the same marking already drawn is not asked again. */
  async show(opts = {}) {
    const key = JSON.stringify(this.markings.entries(this.chain[0]));
    if (opts.reuse && key === this.asked && this.state === 'done') return;
    this.asked = key;
    this.steps = [];
    this.layout = null;
    this.selected = null;
    await this._step(this.chain[0]);
  }

  /** Walk from the marking the last step's presses wrote, and draw it on the same picture. */
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

  _svg(tag, attrs) {
    const node = this.doc.createElementNS(SVG_NS, tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value !== undefined && value !== null) node.setAttribute(key, String(value));
    }
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

    const svg = this._svg('svg', {
      class: 'sg-graph', viewBox: `0 0 ${view.width} ${view.height}`,
      width: view.width, height: view.height, preserveAspectRatio: 'xMinYMin meet',
    });
    // Lines first, so the shapes sit on top of them.
    for (const edge of view.edges) {
      svg.appendChild(this._svg('line', {
        class: 'sg-edge', x1: edge.x1, y1: edge.y1, x2: edge.x2, y2: edge.y2, 'data-predicate': edge.predicate,
      }));
    }
    for (const node of view.nodes) {
      const group = this._svg('g', {
        class: this._classOf(node), 'data-node': node.id, 'data-depth': node.depth, 'data-step': node.step,
      });
      this._groups.set(node.id, { group, node });
      group.appendChild(node.static
        ? this._svg('rect', { x: node.x - NODE_R, y: node.y - NODE_R, width: NODE_R * 2, height: NODE_R * 2 })
        : this._svg('circle', { cx: node.x, cy: node.y, r: NODE_R }));
      const label = this._svg('text', { x: node.x + LABEL_DX, y: node.y + 4 });
      label.textContent = node.label;
      group.appendChild(label);
      if (group.addEventListener) group.addEventListener('click', () => this.press(node.id));
      svg.appendChild(group);
    }
    // A fan-out the walk did not draw, under its node: press it and that bundle is drawn.
    for (const chip of view.chips) {
      const group = this._svg('g', { class: 'sg-bundle', 'data-bundle': chip.key, 'data-step': chip.step + 1 });
      const text = this._svg('text', { x: chip.x, y: chip.y + 4 });
      text.textContent = `+${chip.count} ${chip.farType}`;
      group.appendChild(text);
      if (group.addEventListener) group.addEventListener('click', () => { this.expandBundle(chip.step, chip.key); });
      svg.appendChild(group);
    }
    const box = this._el('div', 'sg-box');
    box.appendChild(svg);
    this.root.appendChild(box);
    this.factsBox = this._facts();
    this.root.appendChild(this.factsBox);
    this._restyle();
  }

  _facts() {
    const box = this._el('div', 'sg-facts');
    const facts = this.layout && this.selected ? nodeFacts(this.layout, this.selected) : null;
    if (!facts) return box;
    box.appendChild(this._el('div', 'sg-facts-head', `${facts.node.label} · ${facts.node.type}`));
    for (const [name, value] of [...Object.entries(facts.node.keys), ...Object.entries(facts.node.attributes)]) {
      box.appendChild(this._el('div', 'sg-fact', `${name} ${value}`));
    }
    for (const edge of facts.edges) {
      box.appendChild(this._el('div', 'sg-fact',
        `${edge.out ? '→' : '←'} ${edge.predicate} · ${edge.other}${edge.occurredAt ? ` · ${edge.occurredAt}` : ''}`));
    }
    return box;
  }

  /** The marks, the pick and Continue follow the store without redrawing the picture (the box keeps its scroll). */
  _restyle() {
    for (const { group, node } of (this._groups || new Map()).values()) group.setAttribute('class', this._classOf(node));
    if (!this.continueButton) return;
    const name = this.writes();
    setDisabledReason(this.continueButton, !name ? 'End of chain' : (this.markings.count(name) ? '' : 'Mark a node'));
  }

  /** A press: the node's facts under the picture, and a mark in the marking this step writes. */
  press(id) {
    this.select(id);
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
