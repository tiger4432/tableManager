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
// 🔴 It judges nothing the server or the declaration already said: the column is the node's `depth`,
//    static is `staticTypes(declaration)`, truncation is `cutBudgets`, the name is the response's `label`.
// 🔴 Drawn by Cytoscape.js with a dagre layout, left to right (owner 10-06, lead 5e1d9e372). The columns are
//    held to the depth; dagre only orders inside them. Everything is laid out once — the first draw and Reset;
//    after that nothing already drawn moves and the view (zoom · pan) is never moved for you (lead 03bc94b6b).
// 🔴 ONE LUMP (lead e523cfe91): a folded branch, the keys split out of it, and a fan-out the server did not send
//    (`bundles`) are one node shape keyed like the server's bundle, `node|predicate|direction`. Pressing one
//    lists what is inside; only what is ticked opens. A lump the server has not sent is walked first: one step
//    from its node (`stepAlong`, lead 11e5ea207).

import cytoscape from 'cytoscape';
import dagre from 'cytoscape-dagre';
import { staticTypes, cutBudgets, walkableRoutes, edgeQualifiers, qualifierWords, stepAlong } from './derive.js';
import { SIGN } from '../rnd_board/marking_store.js';
import { markingIntent } from '../rnd_board/panel.js';
import { setDisabledReason } from '../disabled_reason.js';
import { FAILED, LOADING, unitText } from '../ui_words.js';
import { localMinute } from '../server_time.js';
import { TablePart } from '../rnd_board/table_part.js';
// A folded lump seen as a table or as points, its start branch lit (leads 793017c62 · edcc0568c · 5ef260acf · 10-08).
import { FOLD_VIEWS, STEP_NODE_LIMIT, openLumpSeen, pointsOf, pointsSvg, rememberPick, rememberedPick, saidAt,
  startBranch, svgAddress, valueAttributes, windowAround } from './fold_views.js';
// The look travels with the part (the walk page's rule): one stamp, one sheet per document.
import { ensureWalkStyles } from './styles.js';
// The paths between two marked nodes (lead 55f854fc5): the one simple-path search, called from here.
import { pathKinds, edgeCounts, PATH_STEPS, PATHS_A_KIND, PATHS_AT_MOST } from './paths.js';

// The layout is registered with the library once per load - the library's registry, not this part's state.
if (!cytoscape('layout', 'dagre')) cytoscape.use(dagre);

/** The picture's geometry on the 3.4 grid (ui-design-system §3): a node, the gap dagre keeps between columns,
 *  a stacked row, and the room kept around the picture when it is fitted. */
const GEOMETRY = Object.freeze({ node: 13.6, rankSep: 224.4, nodeSep: 13.6, row: 27.2, fitPad: 27.2 });
/** How many type colours there are; a type's colour is its declaration index modulo this. */
export const TYPE_COLOURS = 9;
/** The fan-out cap the part walks with unless its declaration says another (lead c9bf53033 · 1d07f1dae). */
export const DEFAULT_FANOUT_LIMIT = 20;
/** A list longer than this gets a filter field in the picker (lead 03bc94b6b). */
const PICK_FILTER_AT = 8;
/** A branch's node in the window's values: its branch's key, then the node. */
const PICK_SEP = '\u0000';
/** A big lump's branch seen on its own (its row's Trend) - not a lump in the picture. */
const GROUP_LUMP = 'branch:';
/** The first fit never zooms out past this: a 15px name stays at the 12px meta size (「작은 글씨는 없느니만 못하다」). */
const READABLE_ZOOM = 0.8;
/** How far (px) a press may wander and still be a press, not a node drag (owner 10-07 「노드 클릭이 불안정」, lead
 *  5f1eb137e: on the built page a press that moved a few px past the library's 4 dragged the node and picked nothing). */
export const TAP_SLOP = 10;

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
 * What the walks answered, decided from the answers and the declaration only.
 *
 * One step is one marking walked; a step may hold more than one answer — each lump opened is one step from its
 * node, tagged `opened` with its key, and stands from that node's layer. Step 1's layer is the node's `depth`; a
 * later step's layers carry on from the marked points: `depth + the furthest layer its seeds already stand in`. A
 * node stands once, where it was first reached, and remembers that step. A node without a depth is counted, not
 * placed — its distance is not this screen's guess. The bundles still standing are the step's walk's, less those
 * opened.
 *
 * @param {Array<{results: object[], seeds?: string[]}>} steps
 * @param {object[]} entities  the declaration's entities
 */
export function subgraphLayout(steps, entities) {
  const statics = staticTypes(entities);
  // Colour follows the declaration's order, so a type keeps its colour from walk to walk; a type the
  // declaration does not name takes the next index in the order it first appears.
  const order = (entities || []).map((e) => String((e && e.type) || ''));
  const colourOf = new Map(order.map((type, i) => [type, i]));
  const walked = (step) => ((step && step.results) || []).find((r) => !r.opened) || {};
  const at = new Map();
  const placed = [];
  let unplaced = 0;
  (steps || []).forEach((step, index) => {
    const seedLayers = (step.seeds || []).map((id) => at.get(id)).filter(Boolean).map((n) => n.layer);
    const stepBase = index === 0 || !seedLayers.length ? 0 : Math.max(...seedLayers);
    for (const result of step.results || []) {
      const owner = result.opened && at.get(keyParts(result.opened).node);
      const base = owner ? owner.layer : stepBase;
      for (const node of (Array.isArray(result.nodes) ? result.nodes : [])) {
        const type = String(node.type || '');
        if (!colourOf.has(type)) colourOf.set(type, colourOf.size);
        if (at.has(node.id)) continue;
        if (!Number.isFinite(node.depth)) { unplaced += 1; continue; }
        const one = {
          id: node.id,
          type,
          label: node.label || node.id,
          depth: node.depth,
          layer: base + node.depth,
          step: index + 1,
          static: statics.has(type),
          colour: colourOf.get(type) % TYPE_COLOURS,
          keys: node.keys || {},
          attributes: node.attributes || {},
          // Each world's value of each attribute (server 351b23ef8), drawn like an edge's worlds.
          attributesByWorld: node.attributes_by_world || {},
          // An opening's answer walked to it, not from it (lead f6e8ef44b): what is behind it is not known.
          unwalked: Boolean(result.opened) && node.id !== keyParts(result.opened).node,
        };
        at.set(node.id, one);
        placed.push(one);
      }
    }
  });
  // A node walked from since - its own opening, every predicate one step (`<node>||both`) - is known behind.
  for (const step of steps || []) {
    for (const r of step.results || []) if (r.opened && at.has(keyParts(r.opened).node) && !keyParts(r.opened).predicate) at.get(keyParts(r.opened).node).unwalked = false;
  }
  // The fan-outs a step's walk did not send in full and no opening has walked, under the node they leave; `drawn` is
  // how many of `count` the walk did send (server 11e5ea207).
  const chips = [];
  (steps || []).forEach((step, index) => {
    const opened = new Set((step.results || []).map((r) => r.opened).filter(Boolean));
    for (const b of walked(step).bundles || []) {
      const key = `${b.node}|${b.predicate}|${b.direction}`;
      if (!at.has(b.node) || opened.has(key)) continue;
      chips.push({ step: index, node: b.node, predicate: b.predicate, direction: b.direction,
        farType: b.far_type, count: b.count, drawn: Number.isFinite(b.drawn) ? b.drawn : 0, key });
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
        if (!at.has(edge.source) || !at.has(edge.target)) { missing.add(edge.id); continue; }
        edgeSeen.add(edge.id);
        missing.delete(edge.id);
        drawn.push({
          id: edge.id, source: edge.source, target: edge.target,
          predicate: edge.predicate_label || edge.predicate || '',
          // The name a bundle's key spells, so a branch folded here and a fan-out the server held are one key.
          predicateName: edge.predicate || '',
          occurredAt: edge.occurred_at || '',
          // Each world that says it, with its evidence (lead ee0f66e7b): one line in the picture, one row each here.
          byWorld: Array.isArray(edge.by_world) ? edge.by_world : [],
          qualifiers: edgeQualifiers(edge) || {},
        });
      }
      if (result.cut) cut.push({ step: index + 1, budgets: cutBudgets(result.truncatedAxes, result.limits) });
    }
  });
  const counts = new Map();
  for (const node of placed) counts.set(node.type, (counts.get(node.type) || 0) + 1);
  const legend = [...counts.entries()]
    .sort((a, b) => colourOf.get(a[0]) - colourOf.get(b[0]))
    .map(([type, count]) => ({ type, count, colour: colourOf.get(type) % TYPE_COLOURS, static: statics.has(type) }));
  return { nodes: placed, edges: drawn, chips, legend, unplaced, loose: missing.size, cut };
}

/** An edge's predicate as the walk names it (the picture labels it with `predicate`). */
const predicateOf = (e) => (e.predicateName !== undefined ? e.predicateName : e.predicate);

/** What the Paths box says (lead 55f854fc5). */
const PATH_WORDS = Object.freeze({
  none: 'No path over the ticked edges in this walk · tick more edges, or walk further',
  limits: `Up to ${PATH_STEPS} steps · only through what this walk brought`,
  cut: `Not all · the first ${PATHS_AT_MOST} paths`,
});

/** The key a lump and a bundle share, taken apart (a node id holds no `|`). */
const keyParts = (key) => {
  const [node, predicate, direction] = String(key).split('|');
  return { node, predicate, direction };
};

/**
 * Every step the picture walks: from a node, along one edge, to a node in its layer or a later one (a walk's
 * depth can stay put along an edge), with the bundle key that step belongs to.
 */
function stepsOf(layout) {
  const layerOf = new Map(layout.nodes.map((n) => [n.id, n.layer]));
  const steps = new Map();
  for (const e of layout.edges) {
    const name = predicateOf(e);
    for (const [a, b, direction] of [[e.source, e.target, 'outgoing'], [e.target, e.source, 'incoming']]) {
      if (!(layerOf.get(b) >= layerOf.get(a))) continue;
      if (!steps.has(a)) steps.set(a, []);
      steps.get(a).push({ to: b, key: `${a}|${name}|${direction}` });
    }
  }
  return steps;
}

/** The keys a node's branches leave by: its steps' and its unsent bundles'. Folding it puts all of them in one lump. */
export function branchKeys(layout, id) {
  const keys = new Set((stepsOf(layout).get(id) || []).map((s) => s.key));
  for (const chip of layout.chips || []) if (chip.node === id) keys.add(chip.key);
  return keys;
}

/** Where a step's walk stood: its marked points and every node its walk put at depth 0 (a seed's twins) - not an
 *  opened lump's node, where only that one step stood. */
export function startsOf(step) {
  const twins = ((step && step.results) || []).filter((r) => !r.opened).flatMap((r) => (Array.isArray(r.nodes) ? r.nodes : [])
    .filter((n) => n.depth === 0).map((n) => n.id));
  return [...new Set([...((step && step.seeds) || []), ...twins])];
}

/** A fold that holds nothing: every branch open, no lump but the server's. */
export function openFold() {
  return { big: new Map(), lumped: new Map() };
}

/**
 * The first picture's rule (owner 10-06, lead): from these points every node one step on is drawn and the points'
 * own branches open. Whatever else the answer brings is held: behind a node new to the picture as its one big lump,
 * behind a node already in sight as a small lump that keeps what that node already showed (nothing drawn leaves).
 * A fan-out the server did not send stays its own dashed lump, as it is today. `fold` is added to and returned.
 */
export function foldBeyond(layout, fold, points, shownBefore) {
  const steps = stepsOf(layout);
  const from = new Set(points);
  const before = shownBefore || new Set();
  const near = new Set();
  for (const s of from) {
    fold.big.delete(s);
    for (const step of steps.get(s) || []) {
      fold.lumped.delete(step.key);
      if (!from.has(step.to)) near.add(step.to);
    }
  }
  const drawn = new Set([...before, ...from, ...near]);
  for (const [id, out] of steps) {
    if (from.has(id)) continue;
    if (near.has(id) && !before.has(id)) {
      fold.big.set(id, new Set(out.map((x) => x.key)));
    } else if (before.has(id)) {
      for (const step of out) {
        if (drawn.has(step.to) || fold.lumped.has(step.key)) continue;
        fold.lumped.set(step.key, new Set(out.filter((x) => x.key === step.key && before.has(x.to)).map((x) => x.to)));
      }
    }
  }
  return fold;
}

/**
 * What the picture shows with this fold (lead e523cfe91 · 03bc94b6b, view only — nothing is walked).
 *
 * `fold.big`: node -> the keys still inside its one big lump. `fold.lumped`: key -> the ids opened out of that
 * small lump; the rest of its members stay inside. Walking from where the walks stood (the seeds and every node
 * the server put at depth 0) over the steps, a step is not taken when its key is in its node's big lump, or when
 * its key is a small lump that has not opened its far end. A node no start reaches is left as it is; a node
 * reached another way stays. Each node still in sight then shows its big lump (the keys left in it, what they
 * hold), one small lump per key with members still inside, and one per bundle the server has not sent.
 */
export function lumpView(layout, fold, seeds) {
  const big = (fold && fold.big) || new Map();
  const lumped = (fold && fold.lumped) || new Map();
  const steps = stepsOf(layout);
  const ids = new Set(layout.nodes.map((n) => n.id));
  const starts = [...(seeds || []), ...layout.nodes.filter((n) => n.depth === 0).map((n) => n.id)]
    .filter((id) => ids.has(id));
  const closed = (from, s) => ((big.get(from) || new Set()).has(s.key)
    || (lumped.has(s.key) && !lumped.get(s.key).has(s.to)));
  const reach = (stop) => {
    const seen = new Set(starts);
    const queue = [...seen];
    while (queue.length) {
      const id = queue.shift();
      for (const s of steps.get(id) || []) {
        if (seen.has(s.to) || stop(id, s)) continue;
        seen.add(s.to);
        queue.push(s.to);
      }
    }
    return seen;
  };
  const kept = reach(closed);
  const hidden = new Set([...reach(() => false)].filter((id) => !kept.has(id)));
  const shown = (id) => ids.has(id) && !hidden.has(id);
  const typeOf = new Map(layout.nodes.map((n) => [n.id, n.type]));
  /** Everything hidden that these members lead to, the members included. */
  const inside = (members) => {
    const seen = new Set(members);
    const queue = [...members];
    while (queue.length) {
      const id = queue.shift();
      for (const s of steps.get(id) || []) {
        if (hidden.has(s.to) && !seen.has(s.to)) { seen.add(s.to); queue.push(s.to); }
      }
    }
    return seen;
  };
  const membersOf = (owner, key) => [...new Set((steps.get(owner) || [])
    .filter((s) => s.key === key && hidden.has(s.to)).map((s) => s.to))];
  const unsent = new Map((layout.chips || []).map((c) => [c.key, c]));
  // What a fan-out holds that the server did not send: its count less what it drew.
  const restOf = (key) => (unsent.has(key) ? unsent.get(key).count - unsent.get(key).drawn : 0);
  const typesOf = (members) => [...new Set(members.map((m) => typeOf.get(m)))].join(' · ');
  const lumps = [];
  for (const node of layout.nodes) {
    if (!shown(node.id)) continue;
    const inBig = big.get(node.id) || new Set();
    const groups = [...inBig].map((key) => {
      const chip = unsent.get(key);
      const members = membersOf(node.id, key);
      const rest = restOf(key);
      return { key, ...keyParts(key), members, rest, farType: chip ? chip.farType : typesOf(members),
        count: members.length + rest, unsent: rest > 0 };
    }).filter((g) => g.count > 0);
    if (groups.length) {
      // «N next · M behind» (leads df11f9e81, 2f25c883a): next - the distinct nodes All -> Open draws; behind - what
      // stays folded then, once. A bundle not yet walked may share nodes with another branch: next is then a bound.
      const firsts = new Set(groups.flatMap((g) => g.members));
      const held = inside([...firsts]);
      const rest = groups.reduce((n, g) => n + g.rest, 0);
      const mix = new Map();
      for (const id of firsts) mix.set(typeOf.get(id), (mix.get(typeOf.get(id)) || 0) + 1);
      for (const g of groups) if (g.rest) mix.set(g.farType, (mix.get(g.farType) || 0) + g.rest);
      lumps.push({ id: `big:${node.id}`, level: 'big', owner: node.id, groups,
        count: held.size + rest, next: firsts.size + rest, behind: held.size - firsts.size, bound: rest > 0,
        mix: [...mix.entries()].sort((a, b) => b[1] - a[1]).map(([type, count]) => ({ type, count })) });
    } else if (node.unwalked) {
      lumps.push({ id: `big:${node.id}`, level: 'big', owner: node.id, key: `${node.id}||both`, groups: [], unsent: true,
        unwalked: true, count: 0, next: 0, behind: 0, mix: [] });
    }
    const keys = new Set([...(steps.get(node.id) || []).map((s) => s.key),
      ...(layout.chips || []).filter((c) => c.node === node.id).map((c) => c.key)]);
    for (const key of keys) {
      if (inBig.has(key)) continue;
      const members = lumped.has(key) ? membersOf(node.id, key) : [];
      const chip = unsent.get(key);
      const rest = restOf(key);
      if (!members.length && !rest) continue;
      // `more`: some of this fan-out is in sight - opened out of the lump, or, not lumped, what the walk drew.
      lumps.push({ id: `lump:${key}`, level: 'small', owner: node.id, key, ...keyParts(key), members,
        farType: members.length ? typesOf(members) : chip.farType, count: members.length + rest,
        more: lumped.has(key) ? lumped.get(key).size > 0 : Boolean(chip && chip.drawn), unsent: rest > 0,
        ...(chip ? { step: chip.step } : {}) });
    }
  }
  return {
    nodes: layout.nodes.filter((n) => shown(n.id)),
    edges: layout.edges.filter((e) => shown(e.source) && shown(e.target)),
    lumps,
    hidden: hidden.size,
    // What a member leaves behind it: everything hidden it leads to, itself not counted.
    behind: (id) => inside([id]).size - 1,
  };
}

/**
 * What folding hides (lead 43a738d58 ③): the nodes no longer reached once every branch of the folded nodes is
 * one big lump. The same walk the lumps take (`lumpView`), so a fold and a lump cannot disagree.
 */
export function foldedAway(layout, folded, seeds) {
  const big = new Map([...folded].map((id) => [id, branchKeys(layout, id)]));
  const shown = new Set(lumpView(layout, { big, lumped: new Map() }, seeds).nodes.map((n) => n.id));
  return new Set(layout.nodes.map((n) => n.id).filter((id) => !shown.has(id)));
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
      qualifiers: e.qualifiers,
    }));
  return { node, edges };
}

/** How many qualifiers a chosen node's edge label says before the rest is one `+N` (lead 3181313b5). */
const LABEL_QUALIFIERS = 2;
/** A chosen node's edge label: its predicate, then its first qualifiers. */
const edgeTag = (e) => [e.predicate, ...qualifierWords(e.qualifiers, LABEL_QUALIFIERS)].join(' · ');

/** A cut walk's words, the picture's status line and a lump's head alike (lead 161757c35): every axis cut, with its
 *  budget where the answer says it (`cutBudgets`). */
const truncatedWords = (budgets, where = '') => `Truncated · ${where}${budgets.join(' · ')}`;

/** The words «Points from» says before anything is picked (lead 10-08). */
const PICK_TYPE = 'Pick a type';

/** This window's localStorage, or none where reading it throws (a private window, a blocked site). */
function windowStorage(doc) {
  try {
    return (doc && doc.defaultView && doc.defaultView.localStorage) || null;
  } catch (e) {
    return null;
  }
}

/** A big lump's count words, on the lump and atop its window: «≤» while a bundle is not walked (lead 2f25c883a);
 *  a node the server never walked from, «?» (lead f6e8ef44b). */
const NOT_WALKED = 'not walked';
const nextWords = (lump) => (lump.unwalked ? `? next · ${NOT_WALKED}` : `${lump.bound ? '≤ ' : ''}${lump.next} next · ${lump.behind} behind`);

/** A lump's words: the predicate with its arrow, then what it holds. */
function lumpLabel(lump) {
  if (lump.level === 'big') {
    const mix = lump.mix.slice(0, 3).map((m) => `${m.count} ${m.type}`).join(' · ');
    return `${nextWords(lump)}${mix ? `\n${mix}` : ''}`;
  }
  return `${arrowed(lump)}\n${lump.unsent && lump.more ? '+' : ''}${lump.count}${lump.more ? ' more' : ''} ${lump.farType}`;
}
const arrowed = (g) => (g.direction === 'incoming' ? `← ${g.predicate}` : `${g.predicate} →`);

export class SubgraphView {
  /**
   * @param {HTMLElement} mount
   * @param {{doc?: Document, walk: Function, entities?: () => object[],
   *          markings: import('../rnd_board/marking_store.js').MarkingStore, chain: string[],
   *          fanoutLimit?: number, worldChips?: boolean}} deps
   *   `walk` is the page's `createWalkBoxWalk` function; `entities` reads the declaration the page holds;
   *   `chain` names the markings: the first is the start, each next one takes the marks of a step.
   *   `fanoutLimit` (declaration, default DEFAULT_FANOUT_LIMIT): a fan-out over it comes back with its first drawn
   *   and the rest an unsent lump.
   *   `worldChips`: the page reads several worlds, so each fact says which (lead 99032248f).
   *   `declaration()`: the declaration whose routes a folded lump walks to its values (lead 10-08).
   *   `storage`: where a lump's «Points from» pick is remembered (default this window's localStorage; none: not kept).
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
    this.declaration = deps.declaration || (() => null);
    this.storage = deps.storage !== undefined ? deps.storage : windowStorage(this.doc);
    this.markings = deps.markings;
    this.chain = deps.chain.slice();
    this.fanoutLimit = Number.isFinite(deps.fanoutLimit) ? deps.fanoutLimit : DEFAULT_FANOUT_LIMIT;
    this.worldChips = Boolean(deps.worldChips);
    ensureWalkStyles(this.doc);
    this.root = this._el('div', 'sg-view');
    this.mount.appendChild(this.root);
    // Made once: above the picture (owner 10-07, lead d78bf28bd) a cell that always holds the picked node's facts
    // (swapped) beside the lines with the tools (redrawn); then the picture (kept - Cytoscape lives in it).
    this.top = this._el('div', 'sg-top');
    this.factSlot = this._el('div', 'sg-factslot');
    this.factsBox = this._el('div', 'sg-facts');
    this.factSlot.appendChild(this.factsBox);
    this.head = this._el('div', 'sg-head');
    this.top.appendChild(this.factSlot);
    this.top.appendChild(this.head);
    this.wrap = this._el('div', 'sg-canvas-wrap is-empty');
    this.canvas = this._el('div', 'sg-canvas');
    this.wrap.appendChild(this.canvas);
    this.root.appendChild(this.top);
    this.root.appendChild(this.wrap);
    this.state = 'idle';
    this.reason = '';
    // A sentence about the last opening that brought nothing (lead 11e5ea207); the next walk clears it.
    this.note = '';
    this.steps = [];
    this.layout = null;
    this.selected = null;
    this.asked = '';
    // This instance's, never a module's, never a marking: what is folded, and where each node stood.
    this.fold = openFold();
    this.pos = new Map();
    this.cy = null;
    this.grid = null;
    this.picker = null;
    this._from = null;
    this._relayout = true;
    this.expanding = [];
    // How each lump is seen and the lump the info box holds - this instance's, a new start's to clear.
    this.lumpSeen = openLumpSeen();
    this.pickedLump = null;
    // The paths between two marked nodes: this instance's edges unticked and the kind pressed (lead 55f854fc5).
    this.pathsBox = this._el('div', 'sg-paths');
    this.pathsBox.hidden = true;
    this.wrap.appendChild(this.pathsBox);
    this.pathOff = new Set();
    this.pathKind = null;
    this.pathsFound = null;
    // Another part writing the same name is seen here: same name, same marking.
    for (const name of this.chain) this.markings.subscribe(name, () => { this._paths(); this._restyle(); });
  }

  /** The name the next Mark writes, or '' once the chain is used up. */
  writes() { return this.chain[this.steps.length] || ''; }

  /** Walk from the chain's first marking and draw it. `reuse`: the same marking already drawn is not asked again. */
  async show(opts = {}) {
    const key = JSON.stringify(this.markings.entries(this.chain[0]));
    if (opts.reuse && key === this.asked && this.state === 'done') return;
    this.asked = key;
    // A new start: what the last picture's Mark wrote is that picture's, not this one's (lead 10-07).
    for (const name of this.chain.slice(1)) this.markings.clear(name);
    this.steps = [];
    this.layout = null;
    this.selected = null;
    this.fold = openFold();
    this.lumpSeen = openLumpSeen();
    this.pickedLump = null;
    this.pathOff = new Set();
    this.pathKind = null;
    this.pos = new Map();
    this._relayout = true;
    this._closePicker();
    await this._step(this.chain[0]);
  }

  /** Every seed the steps walked from - where the fold's walk starts. */
  _seeds() { return this.steps.flatMap((s) => s.seeds); }

  /** The view as drawn now. */
  _view() { return lumpView(this.layout, this.fold, this._seeds()); }

  /** The fold state a node's own presses touch: its big lump and its keys' small lumps. */
  _isFolded(id) {
    return this.fold.big.has(id) || [...this.fold.lumped.keys()].some((k) => keyParts(k).node === id);
  }

  /**
   * Fold every branch beyond one node into one big lump, or open it all again: that node and everything behind
   * it in the walk lose their folds, and each node comes back where it stood. Nothing is walked again.
   */
  toggleFold(id) {
    if (this._isFolded(id)) this._unfold(id);
    else this.fold.big.set(id, branchKeys(this.layout, id));
    this._closePicker();
    this.render();
  }

  /** A node and everything behind it in the walk. */
  _behind(id) {
    const behind = new Set([id]);
    const steps = stepsOf(this.layout);
    const queue = [id];
    while (queue.length) {
      for (const s of steps.get(queue.shift()) || []) if (!behind.has(s.to)) { behind.add(s.to); queue.push(s.to); }
    }
    return behind;
  }

  /** Unfold's half: the node and everything behind it lose their folds. */
  _unfold(id) {
    const behind = this._behind(id);
    for (const n of behind) this.fold.big.delete(n);
    for (const k of [...this.fold.lumped.keys()]) if (behind.has(keyParts(k).node)) this.fold.lumped.delete(k);
  }

  /** Unfold, as the Unfold press does, each folded node in sight that hides one of `ids`, until none is hidden. */
  _unfoldFor(ids) {
    for (let guard = 0; guard <= this.layout.nodes.length; guard += 1) {
      const shown = new Set(this._view().nodes.map((n) => n.id));
      const hidden = [...ids].filter((id) => !shown.has(id));
      if (!hidden.length) return;
      const owner = [...shown].find((id) => this._isFolded(id) && hidden.some((h) => this._behind(id).has(h)));
      if (!owner) return;
      this._unfold(owner);
    }
  }

  /** The first picture's fold, step by step: each step's points with their one step, the rest folded. */
  _firstFold() {
    const fold = openFold();
    let shown = new Set();
    for (const step of this.steps) {
      foldBeyond(this.layout, fold, startsOf(step), shown);
      shown = new Set(lumpView(this.layout, fold, this._seeds()).nodes.map((n) => n.id));
    }
    return fold;
  }

  /** Back to the first draw: the first picture's fold, everything laid out again and fitted. */
  reset() {
    this.fold = this._firstFold();
    this.pos = new Map();
    this._relayout = true;
    this._closePicker();
    this.render();
  }

  /** Fit the picture into the box - the one press that moves the view. */
  fit() {
    if (this.cy) this.cy.fit(undefined, GEOMETRY.fitPad);
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
    await this._ask({ positive: step.positive, negative: step.negative, fanout_limit: this.fanoutLimit }, [],
      (res) => [...this.steps, { ...step, results: [res] }], true);
  }

  /** Open one bundle a step left unsent: one step from its node along its predicate, the way it leaves, to its far
   *  type (lead 11e5ea207 · c06b45ea5) - not the step walked again, so how deep the bundle stands does not matter. */
  async expandBundle(index, key) {
    const step = this.steps[index];
    if (!step || this.state !== 'done' || step.expand.includes(key)) return;
    const { node, predicate, direction } = keyParts(key);
    const chip = this.layout.chips.find((c) => c.key === key);
    const expand = [...step.expand, key];
    await this._ask(stepAlong({ positive: [node], predicate, farType: chip && chip.farType, direction }), [key],
      (res) => this.steps.map((s, i) => (i === index ? { ...s, expand, results: [...s.results, { ...res, opened: key }] } : s)));
  }

  /** One walk - a step's marking with the cap this part declares, or one bundle's step; `next` builds the steps from
   *  the answer. A new step (`fresh`) draws its points' one step and folds the rest; an opening changes no fold. */
  async _ask(asked, expanding, next, fresh) {
    const steps = this.steps;
    const before = fresh && this.layout ? new Set(this._view().nodes.map((n) => n.id)) : new Set();
    this.state = 'running';
    this.note = '';
    // What this ask walks, so the lump pressed reads as on its way (lead 10-07); a newer ask owns it after.
    this.expanding = expanding;
    this.render();
    const res = await this.walk(asked);
    if (this.steps !== steps) return;   // a new start was asked meanwhile
    this.expanding = [];
    if (res && res.ok) {
      this.steps = next(res);
      this.layout = subgraphLayout(this.steps, this.entities());
      if (fresh) foldBeyond(this.layout, this.fold, startsOf(this.steps[this.steps.length - 1]), before);
      this.state = 'done';
    } else {
      this.state = 'failed';
      this.reason = (res && res.message) || '';
    }
    this.render();
  }

  /**
   * A lump pressed: the picker lists what it holds and only what is ticked opens (lead 03bc94b6b). A big lump
   * lists its keys - those ticked become small lumps; a small lump lists its members - those ticked become nodes,
   * each folded if it leads anywhere; a lump the server has not sent is walked first, then listed the same way.
   */
  async openLump(id, keep) {
    const lump = this._view().lumps.find((l) => l.id === id);
    if (!lump || this.state !== 'done') return;
    // Not walked from (lead f6e8ef44b): one step from it by a bundle's own door, then its branches folded, its window.
    if (lump.unwalked) {
      const at = this.layout.nodes.find((n) => n.id === lump.owner);
      await this.expandBundle(at ? at.step - 1 : 0, lump.key);
      if (this.state !== 'done') return;
      this.fold.big.set(lump.owner, branchKeys(this.layout, lump.owner));
      this.render();
      await this.openLump(id, keep);
      return;
    }
    if (lump.level === 'big') {
      // One window, one layer (lead df11f9e81): a row a branch, its ▸ its nodes; what is ticked opens as nodes at
      // once - each folded if it leads anywhere - and what is left of a branch stays its «n more». A branch the
      // server did not send is walked first, unfolded or ticked, and the window comes back with it.
      const view = this._view();
      const lit = startBranch(this.steps);
      const items = lump.groups.map((g) => ({ value: g.key, text: `${arrowed(g)} ${g.farType}`, count: g.count,
        ...(g.unsent ? { load: () => this._loadBranch(id, g.key) }
          : { members: g.members.map((m) => ({ value: m, text: this._labelOf(m), count: view.behind(m) || undefined, lit: lit.has(m) })) }) }));
      const open = (picked) => {
        const inBig = this.fold.big.get(lump.owner);
        const out = [];
        const keys = new Set();
        for (const value of picked) {
          const [key, member] = value.split(PICK_SEP);
          inBig.delete(key);
          keys.add(key);
          if (!this.fold.lumped.has(key)) this.fold.lumped.set(key, new Set());
          this.fold.lumped.get(key).add(member);
          this.fold.big.set(member, branchKeys(this.layout, member));
          if (!out.includes(member)) out.push(member);
        }
        if (!inBig.size) this.fold.big.delete(lump.owner);
        // What came out stands where the lump stood; what is left of a branch goes under it.
        this._openedFrom(id, [...out, ...[...keys].map((key) => `lump:${key}`)]);
      };
      // A row's own Trend (owner 10-08): that branch's points at once, the branch left as it was.
      const asPoints = async (key) => {
        if (lump.groups.some((g) => g.key === key && g.unsent)) await this._expandKey(key);
        this.lumpSeen.kind.set(`${GROUP_LUMP}${key}`, FOLD_VIEWS[2]);
        this.pickedLump = `${GROUP_LUMP}${key}`;
        this.selected = null;
        this._closePicker();
        const branch = this._branchLump(key);
        if (branch) await this._seeLump(branch);
      };
      this._openPicker(id, items, `Behind ${this._labelOf(lump.owner)}`, nextWords(lump), open,
        { word: FOLD_VIEWS[2], run: asPoints }, keep);
      return;
    }
    if (lump.unsent) {
      // Held as a lump before the answer comes, so what it brings stays inside until it is ticked; what the walk
      // already drew of it stays drawn.
      if (!this.fold.lumped.has(lump.key)) {
        const shown = new Set(this._view().nodes.map((n) => n.id));
        this.fold.lumped.set(lump.key, new Set((stepsOf(this.layout).get(lump.owner) || [])
          .filter((s) => s.key === lump.key && shown.has(s.to)).map((s) => s.to)));
      }
      const had = this.layout.nodes.length + this.layout.edges.length;
      await this.expandBundle(lump.step, lump.key);
      if (this._view().lumps.some((l) => l.id === id && !l.unsent)) await this.openLump(id);
      else if (this.state === 'done' && this.layout.nodes.length + this.layout.edges.length === had) {
        this.note = `No more ${lump.farType} · ${arrowed(lump)}`;
        this.render();
      }
      return;
    }
    // The info box holds the lump now (lead 10-08): its switch, and - seen as a table or points - those instead of the list.
    this.pickedLump = id;
    this.selected = null;
    if (this._kindOf(id) !== FOLD_VIEWS[0]) {
      this._closePicker();
      await this._seeLump(lump);
      return;
    }
    const view = this._view();
    const lit = startBranch(this.steps);
    const items = lump.members.map((m) => ({ value: m, text: this._labelOf(m), count: view.behind(m) || undefined,
      lit: lit.has(m) }));
    this._openPicker(id, items, `${lump.predicate} · ${lump.farType}`,
      `${lump.count} not drawn · from ${this._labelOf(lump.owner)}`, (members) => {
        const opened = this.fold.lumped.get(lump.key);
        for (const m of members) {
          opened.add(m);
          // What it leads to comes out folded, so an opening does not open more (lead 03bc94b6b).
          this.fold.big.set(m, branchKeys(this.layout, m));
        }
        this._openedFrom(id, members);
      });
    this._swapFacts();
    this._restyle();
  }

  /** See a lump another way (lead 10-08): its list (today's), its nodes as a table, or their points. The view stays put.
   *  A big lump's branch seen so (its row's Trend) lists in its owner's window, the branch unfolded. */
  setLumpView(id, kind) {
    this.lumpSeen.kind.set(id, kind);
    if (!id.startsWith(GROUP_LUMP)) return this.openLump(id);
    const key = id.slice(GROUP_LUMP.length);
    const branch = this._branchLump(key);
    if (!branch) return undefined;
    if (kind !== FOLD_VIEWS[0]) return this._seeLump(branch);
    this.pickedLump = null;
    return this.openLump(`big:${branch.owner}`, { unfolded: new Set([key]) });
  }

  /** A big lump's branch as a lump of its own, for its points or its table - not a lump in the picture. */
  _branchLump(key) {
    for (const big of this._view().lumps.filter((l) => l.level === 'big')) {
      const g = big.groups.find((x) => x.key === key);
      if (g) return { ...g, id: `${GROUP_LUMP}${key}`, level: 'small', owner: big.owner };
    }
    return null;
  }

  /** Walk a branch the server did not send - its bundle's own step, one fan-out (lead 11e5ea207). */
  async _expandKey(key) {
    const chip = this.layout && this.layout.chips.find((c) => c.key === key);
    if (chip) await this.expandBundle(chip.step, key);
  }

  /** A branch the server did not send, unfolded or ticked in the window: walked, then the window again, that branch open
   *  - ticked, all it brought ticked - and what was ticked before still ticked. */
  async _loadBranch(lumpId, key) {
    const was = this.picker ? this._pickerState() : { unfolded: new Set(), values: new Set(), whole: new Set() };
    if (this.picker) this.picker.loading(key);
    await this._expandKey(key);
    if (this.state !== 'done') return;
    was.unfolded.add(key);
    await this.openLump(lumpId, was);
  }

  _kindOf(id) { return this.lumpSeen.kind.get(id) || FOLD_VIEWS[0]; }

  /** The types «Points from» offers: every declared type the route list reaches from the members' types but theirs. */
  _pickChoices(from) {
    const key = from.join(' · ');
    if (!this.lumpSeen.choices.has(key)) {
      const declaration = this.declaration();
      this.lumpSeen.choices.set(key, ((declaration && declaration.entities) || []).map((e) => e.type)
        // The members' own type is not offered (lead 10-08); a route can come back to it (lead 10-09).
        .filter((type) => !from.includes(type))
        .filter((type) => from.some((a) => walkableRoutes(declaration, a, type).length)));
    }
    return this.lumpSeen.choices.get(key);
  }

  /** The type a lump's points come from: picked here, else what this browser remembers for its members' type. */
  _pickedFrom(id, from) {
    const remembered = rememberedPick(this.storage, from.join(' · '));
    const picked = this.lumpSeen.from.get(id) || (remembered && remembered.from) || '';
    return this._pickChoices(from).includes(picked) ? picked : '';
  }

  /** «Points from» changed: that lump is walked again to the type picked, and the pick is kept. */
  setLumpFrom(lump, key, type) {
    this.lumpSeen.from.set(lump.id, type);
    this.lumpSeen.data.delete(lump.id);
    rememberPick(this.storage, key, { from: type });
    return this._seeLump(lump);
  }

  /** A lump seen as a table or points: what it needs is walked once, by its own answer, and drawn when it comes. */
  async _seeLump(lump) {
    const seen = this.lumpSeen;
    if (!seen.data.has(lump.id)) {
      const source = this._lumpSource(lump);
      if (source.pick && !source.ask) seen.data.set(lump.id, { state: 'done', nodes: [], pick: source.pick });
      else if (!source.ask) seen.data.set(lump.id, { state: 'done', nodes: source.nodes });
      else {
        seen.data.set(lump.id, { state: 'loading' });
        this.render();
        const res = await this.walk(source.ask);
        // A new start meanwhile made its own `lumpSeen`: this answer lands in the old one, which nothing reads.
        seen.data.set(lump.id, res && res.ok
          ? { state: 'done', nodes: subgraphLayout([{ results: [res] }], this.entities()).nodes, pick: source.pick,
            window: source.window, windowed: source.windowed, cut: cutBudgets(res.truncatedAxes, res.limits) }
          : { state: 'failed', reason: (res && res.message) || '' });
      }
    }
    this.render();
  }

  /**
   * THE ONE SEAT that says where a lump's points come from (lead 10-08). Members that hold numbers are the points;
   * nothing is asked. Members that are definition nodes (static) take one more step back along the lump's predicate -
   * to whatever does with them what the lump's owner does (collect: the owner's type) - within the start branch's
   * times, AROUND_DAYS each side (none known: no window), capped at STEP_NODE_LIMIT. Any other members are walked from
   * along the declaration's routes (`walkableRoutes`, the walk page's own list) to the type the operator picks in
   * «Points from» (collect: that type) - nothing is asked before a pick (lead 10-08: the code does not guess which
   * type holds the values). The walk does the choosing; the views draw what it brought.
   */
  _lumpSource(lump) {
    const byId = new Map(this.layout.nodes.map((n) => [n.id, n]));
    const members = lump.members.map((m) => byId.get(m)).filter(Boolean);
    if (!members.length || valueAttributes(members).length) return { nodes: members };
    if (!members.every((n) => n.static)) {
      const from = [...new Set(members.map((n) => n.type))].sort();
      const pick = { key: from.join(' · '), choices: this._pickChoices(from), picked: this._pickedFrom(lump.id, from) };
      const routes = pick.picked ? from.flatMap((a) => walkableRoutes(this.declaration(), a, pick.picked)) : [];
      return { pick, ask: routes.length ? { positive: lump.members, direction: 'both',
        hops: Math.max(...routes.map((r) => r.hops)), follow: [...new Set(routes.flatMap((r) => r.follow))],
        collect: [pick.picked] } : null };
    }
    const owner = byId.get(lump.owner);
    const lit = startBranch(this.steps);
    const window = windowAround(this.layout.nodes.filter((n) => lit.has(n.id) && owner && n.type === owner.type)
      .flatMap((n) => Object.keys(n.attributes).map((name) => saidAt(n, name))));
    return { window, windowed: true, ask: { ...stepAlong({ positive: lump.members, predicate: lump.predicate,
      farType: owner && owner.type, direction: lump.direction === 'incoming' ? 'outgoing' : 'incoming' }),
      node_limit: STEP_NODE_LIMIT,
      ...(window ? { since: new Date(window.since).toISOString(), until: new Date(window.until).toISOString() } : {}) } };
  }

  /** Draw what a lump let out, stacked where the lump stood; the lump, if anything is left in it, goes under. */
  _openedFrom(lumpId, out) {
    const at = this.pos.get(lumpId);
    this._from = at ? { lumpId, x: at.x, y: at.y, out: new Set(out) } : null;
    this._closePicker();
    this.render();
  }

  _labelOf(id) {
    const node = this.layout && this.layout.nodes.find((n) => n.id === id);
    return node ? node.label : id;
  }

  _el(tag, cls, text) {
    const node = this.doc.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = String(text);
    return node;
  }

  render() {
    this.head.textContent = '';
    this.continueButton = null;
    const drawn = Boolean(this.layout) && this.state !== 'empty';
    this.wrap.className = `sg-canvas-wrap${drawn ? '' : ' is-empty'}`;
    // The counts and notes are one line that wraps: a note coming or going does not stack a line of its own.
    const status = this._el('div', 'sg-status');
    this.head.appendChild(status);
    if (this.state === 'empty') status.appendChild(this._el('div', 'sg-note', 'Nothing marked'));
    if (this.state === 'failed') status.appendChild(this._el('div', 'sg-fail', `Failed · ${this.reason}`));
    if (this.state === 'running') status.appendChild(this._el('div', 'sg-note', 'Walking'));
    if (this.note) status.appendChild(this._el('div', 'sg-note', this.note));
    if (!drawn) { this._swapFacts(); return; }
    const layout = this.layout;
    status.appendChild(this._el('div', 'sg-counts', `Nodes ${layout.nodes.length} · Edges ${layout.edges.length}`));
    for (const one of layout.cut) {
      const where = this.steps.length > 1 ? `step ${one.step} · ` : '';
      status.appendChild(this._el('div', 'sg-trunc', truncatedWords(one.budgets, where)));
    }
    if (layout.unplaced) status.appendChild(this._el('div', 'sg-note', `No depth · ${layout.unplaced} nodes`));
    if (layout.loose) status.appendChild(this._el('div', 'sg-note', `Not drawn · ${layout.loose} edges`));
    const view = this._view();
    if (view.hidden) status.appendChild(this._el('div', 'sg-note', `Folded · ${unitText(view.hidden, 'node')}`));

    const legend = this._el('div', 'sg-legend');
    for (const item of layout.legend) {
      const chip = this._el('span', `sg-chip sg-type-${item.colour}`);
      chip.setAttribute('data-type', item.type);
      chip.appendChild(this._el('span', `sg-swatch${item.static ? ' is-static' : ''}`));
      chip.appendChild(this._el('span', '', `${item.type} ${item.count}`));
      legend.appendChild(chip);
    }
    const acts = this._el('div', 'sg-acts');
    for (const [cls, word, act] of [['sg-fit', 'Fit', () => this.fit()], ['sg-reset', 'Reset', () => this.reset()]]) {
      const button = this._el('button', `sg-tool ${cls}`, word);
      button.setAttribute('type', 'button');
      if (button.addEventListener) button.addEventListener('click', act);
      acts.appendChild(button);
    }
    const go = this._el('button', 'sg-continue', 'Continue');
    go.setAttribute('type', 'button');
    if (go.addEventListener) go.addEventListener('click', () => { this.continueWalk(); });
    this.continueButton = go;
    acts.appendChild(go);
    // The tools first, so a long legend or many notes scroll inside the cell and never take them out of sight.
    this.head.insertBefore(acts, status);
    this.head.appendChild(legend);
    this._draw(view);
    this._swapFacts();
    this._paths();
    this._restyle();
  }

  /**
   * Two nodes in the marking Mark writes (owner 10-10 «마킹 두 노드 ... 두 노드를 잇는 path 뜨게», lead 55f854fc5): the
   * paths between them over the ticked edges of this walk, by kind - nothing asked of the server. Any other count: no box.
   */
  _paths() {
    const box = this.pathsBox;
    box.textContent = '';
    const name = this.writes();
    const marked = name && this.layout ? this.markings.entries(name).map(([id]) => id) : [];
    if (marked.length !== 2) {
      box.hidden = true;
      this.pathKind = null;
      this.pathsFound = null;
      return;
    }
    box.hidden = false;
    const walk = { nodes: this.layout.nodes,
      edges: this.layout.edges.map((e) => ({ id: e.id, source: e.source, target: e.target, predicate: predicateOf(e) })) };
    const counts = edgeCounts(walk.edges);
    const found = pathKinds(walk, marked[0], marked[1], new Set(counts.map((c) => c.predicate).filter((p) => !this.pathOff.has(p))));
    this.pathsFound = found;
    if (!found.kinds.some((k) => k.key === this.pathKind)) this.pathKind = null;
    box.appendChild(this._el('div', 'sg-paths-head', `Paths · ${this._labelOf(marked[0])} — ${this._labelOf(marked[1])}`));
    const edges = this._el('div', 'sg-paths-edges');
    for (const { predicate, count } of counts) {
      const row = this._el('label', 'sg-paths-edge');
      const tick = this._el('input');
      tick.type = 'checkbox';
      tick.checked = !this.pathOff.has(predicate);
      tick.setAttribute('data-path-edge', predicate);
      if (tick.addEventListener) {
        tick.addEventListener('change', () => {
          if (tick.checked) this.pathOff.delete(predicate);
          else this.pathOff.add(predicate);
          this._paths();
          this._restyle();
        });
      }
      row.appendChild(tick);
      row.appendChild(this._el('span', '', `${predicate} ${count}`));
      edges.appendChild(row);
    }
    box.appendChild(edges);
    if (!found.kinds.length) {
      box.appendChild(this._el('div', 'sg-fail', PATH_WORDS.none));
      box.appendChild(this._el('div', 'sg-note', PATH_WORDS.limits));
      return;
    }
    const kinds = this._el('div', 'sg-paths-kinds');
    for (const kind of found.kinds) {
      const on = kind.key === this.pathKind;
      const press = this._el('button', `sg-paths-kind${on ? ' is-on' : ''}`);
      press.setAttribute('type', 'button');
      press.setAttribute('aria-pressed', String(on));
      press.appendChild(this._el('span', 'sg-paths-words', kind.words.join(' — ')));
      press.appendChild(this._el('span', 'sg-paths-count', kind.more ? `${PATHS_A_KIND}+` : String(kind.count)));
      if (press.addEventListener) press.addEventListener('click', () => this.showPathKind(on ? null : kind.key));
      kinds.appendChild(press);
    }
    box.appendChild(kinds);
    if (found.cut) box.appendChild(this._el('div', 'sg-note', PATH_WORDS.cut));
  }

  /** A kind pressed (or none): its paths lit, the rest faded; a path node in a folded lump is unfolded first. */
  showPathKind(key) {
    this.pathKind = key;
    const kind = key && this.pathsFound && this.pathsFound.kinds.find((k) => k.key === key);
    if (kind) this._unfoldFor(new Set(kind.paths.flatMap((p) => p.nodes)));
    this.render();
  }

  /** The nodes and edges of the pressed kind's paths, or null. */
  _litPaths() {
    const kind = this.pathKind && this.pathsFound && this.pathsFound.kinds.find((k) => k.key === this.pathKind);
    if (!kind) return null;
    return { nodes: new Set(kind.paths.flatMap((p) => p.nodes)), edges: new Set(kind.paths.flatMap((p) => p.edges.map((e) => e.id))) };
  }

  // ── the picture ─────────────────────────────────────────────────────────────────────────────────────────────

  /** A colour role from tokens.css as the document holds it now, or '' where none is readable. */
  _token(name) {
    const view = this.doc.defaultView;
    if (!view || typeof view.getComputedStyle !== 'function') return '';
    return String(view.getComputedStyle(this.doc.documentElement).getPropertyValue(name) || '').trim();
  }

  /** The picture's look, from the tokens (both themes); a role not readable is left to the library's default. */
  _style() {
    const t = (name) => this._token(name);
    const px = (name, fallback) => parseFloat(t(name)) || fallback;
    const set = (style) => Object.fromEntries(Object.entries(style).filter(([, v]) => v !== ''));
    const sheet = [
      { selector: 'node', style: set({ 'font-family': t('--font-sans'), color: t('--text'), 'min-zoomed-font-size': 6 }) },
      { selector: 'node[kind = "node"]', style: set({
        width: GEOMETRY.node, height: GEOMETRY.node, shape: 'ellipse', label: 'data(label)',
        'font-size': px('--fs-body', 15), 'text-valign': 'center', 'text-halign': 'right', 'text-margin-x': 6.8,
        // The name is what a person aims at; the dot alone is a GEOMETRY.node target (lead 5f1eb137e).
        'text-events': 'yes', 'border-width': 1.5, 'border-color': t('--bg-surface') }) },
      { selector: 'node[kind = "node"][?static]', style: { shape: 'rectangle' } },
      { selector: 'node[kind = "node"][step > 1]', style: set({ 'border-style': 'dashed', 'border-color': t('--text') }) },
      { selector: 'node.is-seed', style: set({ 'border-width': 2, 'border-style': 'solid', 'border-color': t('--accent') }) },
      { selector: 'node.is-marked', style: set({ 'border-width': 3.4, 'border-style': 'solid', 'border-color': t('--accent') }) },
      // A control: the board's control colour, dashed so it reads without colour too.
      { selector: 'node.is-control', style: set({ 'border-style': 'dashed', 'border-color': t('--text-muted') }) },
      { selector: 'node.is-selected', style: set({ 'overlay-color': t('--accent'), 'overlay-opacity': 0.16,
        'overlay-padding': 6.8, 'font-weight': 600 }) },
      { selector: 'node[kind = "lump"]', style: set({
        shape: 'rectangle', label: 'data(label)', 'text-wrap': 'wrap', 'text-valign': 'center', 'text-halign': 'center',
        'font-size': px('--fs-body', 15), 'line-height': 1.3, 'background-color': t('--bg-inset'),
        'border-width': 1.5, 'border-color': t('--border-strong'),
        // Its size follows what it holds, so a big one reads as big (lead e523cfe91).
        width: (n) => 136 + Math.min(68, Math.sqrt(n.data('count')) * 13.6),
        height: (n) => 54.4 + Math.min(23.8, Math.sqrt(n.data('count')) * 3.4),
        'text-max-width': (n) => 122.4 + Math.min(68, Math.sqrt(n.data('count')) * 13.6) }) },
      { selector: 'node[kind = "lump"][level = "big"]', style: set({ 'font-weight': 600, 'border-width': 2.5,
        'border-color': t('--text') }) },
      { selector: 'node[kind = "lump"][?unsent]', style: { 'border-style': 'dashed' } },
      { selector: 'node[kind = "lump"][?loading]', style: { label: LOADING } },
      { selector: 'node[kind = "lump"][?spark]', style: { 'background-image': 'data(spark)', 'background-fit': 'contain' } },
      { selector: 'node.is-lit', style: set({ 'overlay-color': t('--accent'), 'overlay-opacity': 0.1, 'overlay-padding': 6.8 }) },
      { selector: 'edge', style: set({
        width: 1.4, 'line-color': t('--border-strong'), 'target-arrow-color': t('--border-strong'),
        'target-arrow-shape': 'triangle', 'arrow-scale': 0.7, 'curve-style': 'unbundled-bezier',
        'control-point-distances': [-13.6, 13.6], 'control-point-weights': [0.25, 0.75],
        'font-size': px('--fs-label', 12), color: t('--text-dim'), 'text-background-color': t('--bg-surface'),
        'text-background-opacity': 1, 'text-background-padding': 2 }) },
      // The lines that cross the picture sideways or back are the tangle; they stand back until picked (lead 5e1d9e372).
      { selector: 'edge.is-far', style: set({ 'line-color': t('--border'), 'target-arrow-color': t('--border'),
        'line-style': 'dashed', width: 1 }) },
      { selector: 'edge[kind = "lump"]', style: set({ 'line-color': t('--border'), 'target-arrow-shape': 'none',
        'curve-style': 'straight' }) },
      { selector: 'edge.is-hot', style: set({ label: 'data(tag)', width: 2.4, 'line-style': 'solid',
        'line-color': t('--accent'), 'target-arrow-color': t('--accent') }) },
      { selector: '.is-faded', style: { opacity: 0.18 } },
      // A pressed kind of the Paths box: its paths lit, the rest faded (lead 55f854fc5).
      { selector: 'node.is-path', style: set({ 'overlay-color': t('--accent'), 'overlay-opacity': 0.16, 'overlay-padding': 6.8 }) },
      { selector: 'edge.is-path', style: set({ label: 'data(tag)', width: 2.4, 'line-style': 'solid',
        'line-color': t('--accent'), 'target-arrow-color': t('--accent') }) },
      { selector: '.is-dim', style: { opacity: 0.18 } },
    ];
    for (let k = 0; k < TYPE_COLOURS; k += 1) {
      const c = t(`--cat-${k + 1}`);
      if (c) sheet.splice(2, 0, { selector: `node[kind = "node"][colour = ${k}]`, style: { 'background-color': c } });
    }
    return sheet;
  }

  /** The one Cytoscape instance of this part, made the first time there is something to draw. */
  _ensureCy() {
    if (this.cy) return this.cy;
    // A real element is drawn into; the stub document of the harnesses has none, so the same part runs headless.
    const canRender = typeof this.canvas.getBoundingClientRect === 'function';
    const cy = cytoscape({ container: canRender ? this.canvas : undefined, headless: !canRender, styleEnabled: true,
      style: this._style(), elements: [], minZoom: 0.1, maxZoom: 3,
      boxSelectionEnabled: false, desktopTapThreshold: TAP_SLOP });
    // Headless there is no frame to draw; the library's frame loop would only keep a node process from ending.
    if (!canRender) cy.stopAnimationLoop();
    cy.on('tap', 'node', (ev) => {
      const n = ev.target;
      if (n.data('kind') === 'lump') this.openLump(n.id());
      else { this._closePicker(); this.press(n.id()); }
    });
    cy.on('tap', (ev) => { if (ev.target === cy) this._closePicker(); });
    cy.on('mouseover', 'node[kind = "node"]', (ev) => {
      if (this.picker) return;
      const near = ev.target.closedNeighborhood();
      cy.elements().not(near).addClass('is-faded');
    });
    cy.on('mouseout', 'node', () => { cy.elements().removeClass('is-faded'); });
    cy.on('dragfree', 'node', (ev) => { this.pos.set(ev.target.id(), { ...ev.target.position() }); });
    cy.on('viewport', () => { if (this.picker) this._closePicker(); });
    // The box takes the height the window leaves (owner 10-07), so its size changes under the picture.
    const Sizer = this.doc.defaultView && this.doc.defaultView.ResizeObserver;
    if (Sizer && canRender) {
      this._sizeWatch = new Sizer(() => this._resized());
      this._sizeWatch.observe(this.canvas);
    }
    // The site's theme toggle (data-theme on the root) restyles the picture; the instance owns its observer.
    const Observer = this.doc.defaultView && this.doc.defaultView.MutationObserver;
    if (Observer) {
      // The dots are drawn with the tokens' values, so they are drawn again too.
      this._themeWatch = new Observer(() => { if (this.cy) { this.cy.style(this._style()); this.render(); } });
      this._themeWatch.observe(this.doc.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    }
    this.cy = cy;
    return cy;
  }

  /** The elements a view draws: its nodes, its edges, its lumps and the line from each lump to its node. */
  _elements(view) {
    const layerOf = new Map(view.nodes.map((n) => [n.id, n.layer]));
    const lit = startBranch(this.steps);
    const out = [];
    for (const n of view.nodes) {
      out.push({ group: 'nodes', data: { id: n.id, kind: 'node', label: n.label, type: n.type, layer: n.layer,
        depth: n.depth, step: n.step, colour: n.colour, static: n.static } });
    }
    for (const l of view.lumps) {
      out.push({ group: 'nodes', data: { id: l.id, kind: 'lump', level: l.level, owner: l.owner, key: l.key || '',
        count: l.count, unsent: Boolean(l.unsent), loading: Boolean(l.unsent) && this.expanding.includes(l.key),
        spark: this._spark(l, lit), label: lumpLabel(l), layer: (layerOf.get(l.owner) || 0) + 1 } });
    }
    for (const e of view.edges) {
      // A line one column forward is the walk's own step; any other runs sideways or back and stands back.
      const forward = layerOf.get(e.target) - layerOf.get(e.source) === 1
        || layerOf.get(e.source) - layerOf.get(e.target) === 1;
      out.push({ group: 'edges', data: { id: e.id, source: e.source, target: e.target, kind: 'edge',
        predicate: e.predicate, tag: edgeTag(e) }, classes: forward ? '' : 'is-far' });
    }
    for (const l of view.lumps) {
      const back = l.direction === 'incoming';
      out.push({ group: 'edges', data: { id: `to:${l.id}`, source: back ? l.id : l.owner, target: back ? l.owner : l.id,
        kind: 'lump' } });
    }
    return out;
  }

  /**
   * Bring the picture to this view. What is already drawn stays where it stands; what leaves is taken off; what
   * comes is placed by `_place`. The first draw and Reset lay the whole walk out and fit it - nothing else does.
   */
  _draw(view) {
    const cy = this._ensureCy();
    const want = this._elements(view);
    const wanted = new Set(want.map((e) => e.data.id));
    const full = this._relayout;
    this._relayout = false;
    const added = [];
    cy.batch(() => {
      cy.elements().filter((e) => !wanted.has(e.id())).remove();
      for (const e of want) {
        const have = cy.getElementById(e.data.id);
        if (have.nonempty()) { have.data(e.data); have.classes(e.classes || ''); continue; }
        cy.add({ group: e.group, data: e.data, classes: e.classes || '',
          position: e.group === 'nodes' ? { x: 0, y: 0 } : undefined });
        if (e.group === 'nodes') added.push(e.data.id);
      }
    });
    if (full) this._layoutAll(view);
    else this._place(view, added);
    cy.nodes().forEach((n) => { this.pos.set(n.id(), { ...n.position() }); });
    // The view moves on the first draw and Reset only (lead 03bc94b6b). A box not yet on the page has no size to
    // fit into; the fit then waits for the first draw that has one.
    if (full) this._fitPending = true;
    if (this._fitPending && this.canvas.clientWidth) this._firstFit();
  }

  /**
   * The box changed size. A box that only now has one (the page put the picture in after the walk answered) gets
   * the first fit; otherwise the picture follows the box and the view stays where it is (lead 03bc94b6b, d78bf28bd).
   */
  _resized() {
    if (!this.cy || !this.canvas.clientWidth) return;
    if (this._fitPending) this._firstFit();
    else this.cy.resize();
  }

  /** The whole walk in the box; if that needs names too small to read, the start at the left, readable instead. */
  _firstFit() {
    const cy = this.cy;
    this._fitPending = false;
    cy.resize();
    cy.fit(undefined, GEOMETRY.fitPad);
    // A first picture of a few nodes is not blown up past its own size.
    if (cy.zoom() > 1) { cy.zoom(1); cy.center(); }
    if (cy.zoom() >= READABLE_ZOOM) return;
    const start = this._seeds().map((id) => cy.getElementById(id)).find((n) => n.nonempty());
    if (!start) return;
    // The start at the left; the picture's middle at the middle, so what is around the start's branches shows.
    const box = cy.elements().boundingBox();
    cy.zoom(READABLE_ZOOM);
    cy.pan({ x: GEOMETRY.fitPad * 2 - start.position('x') * READABLE_ZOOM,
      y: cy.height() / 2 - ((box.y1 + box.y2) / 2) * READABLE_ZOOM });
  }

  /** The whole walk laid out by dagre, its columns held to the depth; the lumps then stand beside their nodes. */
  _layoutAll(view) {
    const cy = this.cy;
    const layerOf = new Map(view.nodes.map((n) => [n.id, n.layer]));
    // Layout-only edges, low column to high, as long as the columns between them: dagre may not move a column.
    const guides = [];
    const fed = new Set();
    for (const e of view.edges) {
      const [a, b] = layerOf.get(e.source) <= layerOf.get(e.target) ? [e.source, e.target] : [e.target, e.source];
      const span = layerOf.get(b) - layerOf.get(a);
      if (span < 1) continue;
      fed.add(b);
      guides.push({ group: 'edges', data: { id: `guide:${e.id}`, source: a, target: b, span } });
    }
    // A node reached only sideways would fall to the first column; a guide from a start holds it in its own.
    const first = view.nodes.find((n) => n.layer === 0);
    for (const n of view.nodes) {
      if (first && n.layer > 0 && !fed.has(n.id)) {
        guides.push({ group: 'edges', data: { id: `guide:anchor:${n.id}`, source: first.id, target: n.id, span: n.layer } });
      }
    }
    const added = cy.add(guides);
    added.style('display', 'none');
    cy.nodes('[kind = "node"]').union(added).layout({ name: 'dagre', rankDir: 'LR', fit: false, animate: false,
      nodeSep: GEOMETRY.nodeSep, rankSep: GEOMETRY.rankSep, minLen: (edge) => edge.data('span') || 1 }).run();
    cy.remove(added);
    // The columns as dagre stood them (a node's border counts in its width), so a later node joins its column.
    const cols = new Map();
    cy.nodes('[kind = "node"]').forEach((n) => { if (!cols.has(n.data('layer'))) cols.set(n.data('layer'), n.position('x')); });
    const layers = [...cols.keys()].sort((p, q) => p - q);
    const lo = layers[0];
    const hi = layers[layers.length - 1];
    const gap = hi > lo ? (cols.get(hi) - cols.get(lo)) / (hi - lo) : GEOMETRY.node + GEOMETRY.rankSep;
    this.grid = { cols, gap };
    this._place(view, cy.nodes('[kind = "lump"]').map((n) => n.id()));
  }

  /** The x of a column, from the first layout's grid. */
  _colX(layer) {
    const grid = this.grid || { cols: new Map(), gap: GEOMETRY.node + GEOMETRY.rankSep };
    if (grid.cols.has(layer)) return grid.cols.get(layer);
    const known = [...grid.cols.keys()];
    if (!known.length) return layer * grid.gap;
    const near = known.reduce((p, q) => (Math.abs(q - layer) < Math.abs(p - layer) ? q : p));
    return grid.cols.get(near) + (layer - near) * grid.gap;
  }

  /**
   * Place what was just added, nothing else (lead 03bc94b6b). What a lump let out comes out where the lump stood,
   * one row each, and the lump, if anything is left in it, goes under them; a node folded and opened again comes
   * back where it stood; a node a Continue reached stands in its column at the row of the node it came from, or the
   * nearest free row to it; a lump stands one column right of its node, at its row or the nearest free one.
   */
  _place(view, added) {
    const cy = this.cy;
    const gap = (this.grid || { gap: GEOMETRY.node + GEOMETRY.rankSep }).gap;
    const pending = new Set(added);
    // What stands, per column, as plain numbers - made the first time a free row is asked for, kept as things land.
    let columns = null;
    const columnOf = (x) => Math.round(x / gap);
    const stand = (x, y, height) => {
      const c = columnOf(x);
      if (!columns.has(c)) columns.set(c, []);
      columns.get(c).push({ x, y, half: height / 2 });
    };
    const put = (id, p) => {
      const el = cy.getElementById(id);
      el.position(p);
      pending.delete(id);
      if (columns) stand(p.x, p.y, el.height());
    };
    // The nearest free row to `y` in that column, one row down, one up, two down, ...
    const clear = (x, y, height) => {
      if (!columns) {
        columns = new Map();
        cy.nodes().forEach((n) => { if (!pending.has(n.id())) stand(n.position('x'), n.position('y'), n.height()); });
      }
      const c = columnOf(x);
      const near = [c - 1, c, c + 1].flatMap((k) => columns.get(k) || []).filter((o) => Math.abs(o.x - x) < gap / 2);
      const pad = height / 2 + GEOMETRY.row / 4;
      for (let k = 0; k < 800; k += 1) {
        const at = y + (k % 2 ? 1 : -1) * Math.ceil(k / 2) * GEOMETRY.row;
        if (!near.some((o) => Math.abs(o.y - at) < o.half + pad)) return at;
      }
      return y;
    };
    const layerOf = new Map(view.nodes.map((n) => [n.id, n.layer]));
    const from = this._from;
    this._from = null;
    // 1. what a lump let out, stacked where it stood
    if (from) {
      // One under the other by its own height - a row for a node, more for a lump, which is taller than a row
      // (owner 10-08: a small lump let out overlapped the big one left) - the first where the lump stood.
      const stepOf = (id) => Math.max(GEOMETRY.row, cy.getElementById(id).height() + GEOMETRY.row / 4);
      const first = [...from.out].find((id) => pending.has(id));
      let top = first ? from.y - stepOf(first) / 2 : from.y;
      // In the picker's order, the order the person read them in.
      for (const id of from.out) {
        if (!pending.has(id)) continue;
        const step = stepOf(id);
        put(id, { x: layerOf.has(id) ? this._colX(layerOf.get(id)) : from.x, y: top + step / 2 });
        top += step;
      }
      const left = cy.getElementById(from.lumpId);
      if (left.nonempty() && first) left.position({ x: from.x, y: top + GEOMETRY.row / 2 + left.height() / 2 });
    }
    // 2. back where they stood
    for (const id of added) if (pending.has(id) && this.pos.has(id)) put(id, this.pos.get(id));
    // 3. nodes new to the picture: their column, the row of the node they came from
    const around = new Map();
    for (const e of view.edges) {
      for (const [a, b] of [[e.source, e.target], [e.target, e.source]]) {
        if (!around.has(a)) around.set(a, []);
        around.get(a).push(b);
      }
    }
    for (const n of view.nodes) {
      if (!pending.has(n.id)) continue;
      const from1 = (around.get(n.id) || []).find((p) => !pending.has(p) && layerOf.get(p) < n.layer);
      const x = this._colX(n.layer);
      put(n.id, { x, y: clear(x, from1 ? cy.getElementById(from1).position('y') : 0, GEOMETRY.node) });
    }
    // 4. lumps: one column right of their node
    for (const l of view.lumps) {
      if (!pending.has(l.id)) continue;
      const owner = cy.getElementById(l.owner);
      const lump = cy.getElementById(l.id);
      // Its left edge where the next column's nodes stand, so it never covers its own node's name.
      const x = owner.position('x') + gap + lump.width() / 2 - GEOMETRY.node;
      put(l.id, { x, y: clear(x, owner.position('y'), lump.height()) });
    }
  }

  /** Swap the facts box for the picked node's. */
  _swapFacts() {
    const next = this._facts();
    this.factSlot.insertBefore(next, this.factsBox);
    this.factSlot.removeChild(this.factsBox);
    this.factsBox = next;
  }

  _facts() {
    const lump = this.pickedLump && this.layout
      && (this._view().lumps.find((l) => l.id === this.pickedLump && l.level === 'small')
        || (this.pickedLump.startsWith(GROUP_LUMP) ? this._branchLump(this.pickedLump.slice(GROUP_LUMP.length)) : null));
    if (lump) return this._lumpFacts(lump);
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
    if (mark.addEventListener) mark.addEventListener('click', (event) => { this.toggleMark(id, event); });
    this.markButton = mark;
    acts.appendChild(mark);
    const folded = this._isFolded(id);
    if (folded || foldedAway(this.layout, new Set([id]), this._seeds()).size
        || this.layout.chips.some((c) => c.node === id)) {
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
      box.appendChild(this._el('div', 'sg-fact', [`${edge.out ? '→' : '←'} ${edge.predicate}`, edge.other,
        ...(edge.occurredAt ? [edge.occurredAt] : []), ...qualifierWords(edge.qualifiers)].join(' · ')));
      this._worldRows(box, edge.byWorld, (said) => [said.source_who, said.occurred_at]);
    }
    return box;
  }

  /**
   * The info box holding a lump (lead 10-08): what it is and its switch, then - seen as a table or points - its counts
   * as values and the table or the points, the start branch lit in both (the one `startBranch`).
   */
  _lumpFacts(lump) {
    const box = this._el('div', 'sg-facts sg-lumpview');
    this.markButton = null;
    const kind = this._kindOf(lump.id);
    const head = this._el('div', 'sg-facts-acts');
    head.appendChild(this._el('span', 'sg-facts-head', `${arrowed(lump)} ${lump.farType}`));
    for (const one of FOLD_VIEWS) {
      const button = this._el('button', 'sg-tool sg-lv-kind', one);
      button.setAttribute('type', 'button');
      button.setAttribute('data-lump-view', one);
      button.setAttribute('aria-pressed', String(one === kind));
      if (button.addEventListener) button.addEventListener('click', () => { this.setLumpView(lump.id, one); });
      head.appendChild(button);
    }
    box.appendChild(head);
    const data = this.lumpSeen.data.get(lump.id);
    if (kind === FOLD_VIEWS[0] || !data) return box;
    if (data.state === 'loading') { box.appendChild(this._el('div', 'sg-note', LOADING)); return box; }
    if (data.state === 'failed') { box.appendChild(this._el('div', 'sg-fail', `${FAILED} · ${data.reason}`)); return box; }
    if (data.pick) {
      head.appendChild(this._choice('Points from', data.pick.choices, data.pick.picked, PICK_TYPE,
        (type) => { this.setLumpFrom(lump, data.pick.key, type); }));
      if (!data.pick.picked) { box.appendChild(this._el('div', 'sg-note', PICK_TYPE)); return box; }
    }
    const ys = valueAttributes(data.nodes);
    const y = this._yOf(lump.id, ys, data.pick);
    const lit = startBranch(this.steps);
    const got = pointsOf(data.nodes, y, lit);
    if (ys.length) {
      head.appendChild(this._choice('Value', ys, y, '', (name) => {
        this.lumpSeen.y.set(lump.id, name);
        if (data.pick) rememberPick(this.storage, data.pick.key, { y: name });
        this.render();
      }));
    }
    const said = [`Points ${got.points.length}`];
    if (data.window) said.push(`Window ${localMinute(new Date(data.window.since))} – ${localMinute(new Date(data.window.until))}`);
    else if (data.windowed) said.push('Window all time');
    if (data.cut && data.cut.length) said.push(truncatedWords(data.cut));
    if (got.notNumber) said.push(`${got.notNumber} not numbers`);
    if (got.noTime) said.push(`${got.noTime} no time`);
    if (got.noValue) said.push(`${got.noValue} without ${y || 'values'}`);
    box.appendChild(this._el('div', 'sg-lv-meta', said.join(' · ')));
    if (kind === FOLD_VIEWS[2]) {
      const plot = this._el('img', 'sg-lv-plot');
      plot.setAttribute('alt', '');
      plot.setAttribute('src', svgAddress(pointsSvg(got.points,
        { width: 480, height: 80, pad: 6.8, r: 3.4, colours: this._dotColours(), axes: true })));
      box.appendChild(plot);
      return box;
    }
    const names = [...new Set(data.nodes.flatMap((n) => Object.keys(n.attributes)))];
    const timeOf = (n) => saidAt(n, y);
    const rows = data.nodes.slice().sort((a, b) => (timeOf(a) ?? Infinity) - (timeOf(b) ?? Infinity)).map((n) => ({
      id: n.id, name: n.label, time: timeOf(n) === null ? null : localMinute(new Date(timeOf(n))),
      ...Object.fromEntries(names.map((name) => [`a:${name}`, n.attributes[name]])) }));
    const host = this._el('div', 'sg-lv-table');
    new TablePart(host, { doc: this.doc, rows, rowLit: (row) => lit.has(row.id), emptyText: 'No nodes',
      columns: [{ key: 'name', label: 'Name' },
        ...names.map((name) => ({ key: `a:${name}`, label: name, kind: ys.includes(name) ? 'number' : 'text' })),
        { key: 'time', label: 'Time' }] }).render();
    box.appendChild(host);
    return box;
  }

  /** The attribute a lump's points stand on: the one picked if it is still there - here, else the one this browser
   *  remembers for its members' type - else the first that holds a number. */
  _yOf(id, ys, pick) {
    const remembered = pick ? rememberedPick(this.storage, pick.key) : null;
    const picked = this.lumpSeen.y.get(id) || (remembered && remembered.y);
    return ys.includes(picked) ? picked : ys[0];
  }

  /** A labelled choice in the info box's head; `empty` (if any) is the option that stands for no choice yet. */
  _choice(word, values, value, empty, onPick) {
    const label = this._el('label', 'sg-lv-choice');
    label.appendChild(this._el('span', 'sg-lv-word', word));
    const pick = this._el('select', 'sg-lv-y');
    for (const name of [...(empty ? [''] : []), ...values]) {
      const option = this._el('option', '', name || empty);
      option.setAttribute('value', name);
      pick.appendChild(option);
    }
    pick.value = value || '';
    if (pick.addEventListener) pick.addEventListener('change', () => { if (pick.value) onPick(pick.value); });
    label.appendChild(pick);
    return label;
  }

  /** The dots' colours, as the tokens are now - an image reads no page variable. */
  _dotColours() {
    const t = (name) => this._token(name);
    return { lit: t('--accent'), ring: t('--text'), rest: t('--text-dim'), text: t('--text-dim'), font: t('--font-sans') };
  }

  /** A lump seen as points carries them as its own picture (lead 10-08), drawn by the same one drawing, smaller. */
  _spark(lump, lit) {
    const data = this.lumpSeen.data.get(lump.id);
    if (this._kindOf(lump.id) !== FOLD_VIEWS[2] || !data || data.state !== 'done') return '';
    const got = pointsOf(data.nodes, this._yOf(lump.id, valueAttributes(data.nodes), data.pick), lit);
    return got.points.length ? svgAddress(pointsSvg(got.points,
      { width: 136, height: 54.4, pad: 6.8, r: 2.4, colours: this._dotColours(), axes: false })) : '';
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

  // ── the picker: what to open out of a lump (lead 03bc94b6b) ─────────────────────────────────────────────────

  /** `rowView` (if any): a press of its own on each row, `{word, run(value)}` - a big lump's rows' Trend. */
  /**
   * The picker: a row an item, ticked to open. An item with `members` is a branch - its ▸ lists them, each ticked on its
   * own, the branch's box ticks them all; one with `load` lists nothing until it is walked (its ▸ or its box walks it).
   * `keep` reopens it as it was: the branches unfolded, the values ticked, the branches ticked whole.
   */
  _openPicker(lumpId, items, title, sub, onOpen, rowView, keep = {}) {
    this._closePicker();
    const unfolded = keep.unfolded || new Set();
    const keptValues = keep.values || new Set();
    const keptWhole = keep.whole || new Set();
    const box = this._el('div', 'sg-pick');
    box.setAttribute('role', 'dialog');
    box.setAttribute('data-lump', lumpId);
    const head = this._el('div', 'sg-pick-head', title);
    head.appendChild(this._el('div', 'sg-pick-sub', sub));
    box.appendChild(head);
    let filter = null;
    if (items.length > PICK_FILTER_AT) {
      filter = this._el('input', 'sg-pick-filter');
      filter.setAttribute('type', 'search');
      filter.setAttribute('placeholder', 'Filter');
      box.appendChild(filter);
    }
    const list = this._el('div', 'sg-pick-list');
    const box_ = () => {
      const cb = this._el('input');
      cb.setAttribute('type', 'checkbox');
      cb.type = 'checkbox';
      cb.checked = false;
      return cb;
    };
    const rows = items.map((item) => {
      const row = this._el('label', `sg-pick-row${item.lit ? ' is-lit' : ''}`);
      row.setAttribute('data-value', item.value);
      const cb = box_();
      cb.checked = keptWhole.has(item.value);
      row.appendChild(cb);
      row.appendChild(this._el('span', 'sg-pick-text', item.text));
      if (item.count !== undefined) row.appendChild(this._el('span', 'sg-pick-n', String(item.count)));
      const branch = Boolean(item.members || item.load);
      let unfold = null;
      if (branch) {
        unfold = this._el('button', 'sg-tool sg-pick-unfold', '▸');
        unfold.setAttribute('type', 'button');
        unfold.setAttribute('data-value', item.value);
        unfold.setAttribute('aria-expanded', String(unfolded.has(item.value) && Boolean(item.members)));
        row.appendChild(unfold);
      }
      if (rowView) {
        const view = this._el('button', 'sg-tool sg-pick-view', rowView.word);
        view.setAttribute('type', 'button');
        view.setAttribute('data-value', item.value);
        if (view.addEventListener) {
          view.addEventListener('click', (ev) => {
            // The row is a label: the press must not tick its box as well.
            if (ev && ev.preventDefault) ev.preventDefault();
            rowView.run(item.value);
          });
        }
        row.appendChild(view);
      }
      list.appendChild(row);
      const entry = { row, cb, value: item.value, text: String(item.text).toLowerCase(), item, unfold, kids: [], sub: null };
      if (item.members) {
        const subList = this._el('div', 'sg-pick-members');
        subList.hidden = !unfolded.has(item.value);
        for (const m of item.members) {
          const r = this._el('label', `sg-pick-row is-member${m.lit ? ' is-lit' : ''}`);
          const value = `${item.value}${PICK_SEP}${m.value}`;
          r.setAttribute('data-value', value);
          const c = box_();
          c.checked = keptWhole.has(item.value) || keptValues.has(value);
          r.appendChild(c);
          r.appendChild(this._el('span', 'sg-pick-text', m.text));
          if (m.count !== undefined) r.appendChild(this._el('span', 'sg-pick-behind', `+${m.count} behind`));
          subList.appendChild(r);
          entry.kids.push({ row: r, cb: c, value, text: String(m.text).toLowerCase() });
        }
        list.appendChild(subList);
        entry.sub = subList;
        cb.checked = entry.kids.length > 0 && entry.kids.every((k) => k.cb.checked);
      }
      return entry;
    });
    box.appendChild(list);
    const foot = this._el('div', 'sg-pick-foot');
    const allRow = this._el('label', 'sg-pick-all');
    const all = this._el('input');
    all.setAttribute('type', 'checkbox');
    all.type = 'checkbox';
    allRow.appendChild(all);
    allRow.appendChild(this._el('span', '', 'All'));
    const cancel = this._el('button', 'sg-tool sg-pick-cancel', 'Cancel');
    cancel.setAttribute('type', 'button');
    const go = this._el('button', 'sg-continue sg-pick-open', 'Open');
    go.setAttribute('type', 'button');
    // What Open opens: a branch's ticked nodes, or a plain row's value.
    const chosenOf = () => rows.flatMap((r) => (r.item.members ? r.kids.filter((k) => k.cb.checked).map((k) => k.value)
      : (r.item.load ? [] : (r.cb.checked ? [r.value] : []))));
    const sync = () => {
      // Distinct nodes: one ticked under two branches that share it opens once.
      const n = new Set(chosenOf().map((value) => value.split(PICK_SEP).pop())).size;
      go.textContent = n ? `Open ${n}` : 'Open';
      setDisabledReason(go, n ? '' : 'Tick one');
    };
    const visible = (r) => !r.row.hidden;
    if (all.addEventListener) {
      all.addEventListener('change', () => {
        const unsent = rows.filter((r) => visible(r) && r.item.load);
        for (const r of rows) {
          if (!visible(r)) continue;
          r.cb.checked = all.checked;
          for (const k of r.kids) k.cb.checked = all.checked;
        }
        sync();
        // All of a window with unsent branches walks them, then comes back with everything ticked.
        if (all.checked && unsent.length) void this._loadAll(lumpId, unsent.map((r) => r.item));
      });
      for (const r of rows) {
        r.cb.addEventListener('change', () => {
          for (const k of r.kids) k.cb.checked = r.cb.checked;
          if (r.cb.checked && r.item.load) void r.item.load();
          sync();
        });
        for (const k of r.kids) {
          k.cb.addEventListener('change', () => { r.cb.checked = r.kids.every((x) => x.cb.checked); sync(); });
        }
        if (r.unfold) {
          r.unfold.addEventListener('click', (ev) => {
            // The row is a label: the press must not tick its box as well.
            if (ev && ev.preventDefault) ev.preventDefault();
            if (r.item.load) { void r.item.load(); return; }
            r.sub.hidden = !r.sub.hidden;
            r.unfold.setAttribute('aria-expanded', String(!r.sub.hidden));
          });
        }
      }
      if (filter) {
        filter.addEventListener('input', () => {
          const q = String(filter.value || '').trim().toLowerCase();
          for (const r of rows) {
            for (const k of r.kids) k.row.hidden = Boolean(q) && !k.text.includes(q);
            r.row.hidden = Boolean(q) && !r.text.includes(q) && !r.kids.some((k) => k.text.includes(q));
          }
        });
      }
      cancel.addEventListener('click', () => this._closePicker());
      go.addEventListener('click', () => {
        const chosen = chosenOf();
        if (!chosen.length) return;
        this._closePicker();
        onOpen(chosen);
      });
    }
    foot.appendChild(allRow);
    foot.appendChild(cancel);
    foot.appendChild(go);
    box.appendChild(foot);
    sync();
    this.wrap.appendChild(box);
    // Beside the lump, inside the picture's box.
    const lump = this.cy && this.cy.getElementById(lumpId);
    if (lump && lump.nonempty()) {
      const p = lump.renderedPosition();
      const w = this.wrap.clientWidth || 0;
      const h = this.wrap.clientHeight || 0;
      const width = box.offsetWidth || 0;
      const height = box.offsetHeight || 0;
      const left = Math.max(6.8, Math.min(p.x + lump.renderedWidth() / 2 + 13.6, w - width - 6.8));
      const top = Math.max(6.8, Math.min(p.y - 40.8, h - height - 6.8));
      box.style.left = `${Math.round(left)}px`;
      box.style.top = `${Math.round(top)}px`;
      lump.addClass('is-lit');
    }
    this._onKey = (ev) => { if (ev && ev.key === 'Escape') this._closePicker(); };
    if (this.doc.addEventListener) this.doc.addEventListener('keydown', this._onKey);
    this.picker = { box, lumpId, rows, all, filter, go, cancel,
      // A branch being walked says so in its row until the window comes back.
      loading: (value) => {
        const r = rows.find((x) => x.value === value);
        if (r) { r.row.className += ' is-loading'; if (r.unfold) { r.unfold.textContent = LOADING; setDisabledReason(r.unfold, LOADING); } }
      } };
    if (filter && filter.focus) filter.focus(); else if (rows[0] && rows[0].cb.focus) rows[0].cb.focus();
  }

  /** What the open window holds: the branches unfolded, the nodes ticked, the branches ticked whole. */
  _pickerState() {
    const rows = (this.picker && this.picker.rows) || [];
    return { unfolded: new Set(rows.filter((r) => r.sub && !r.sub.hidden).map((r) => r.value)),
      values: new Set(rows.flatMap((r) => r.kids.filter((k) => k.cb.checked).map((k) => k.value))),
      whole: new Set(rows.filter((r) => r.cb.checked).map((r) => r.value)) };
  }

  /** All ticked in a window with unsent branches: each walked, then the window again with everything ticked. */
  async _loadAll(lumpId, items) {
    const was = this._pickerState();
    for (const item of items) if (this.picker) this.picker.loading(item.value);
    for (const item of items) {
      await this._expandKey(item.value);
      if (this.state !== 'done') return;
    }
    const lump = this._view().lumps.find((l) => l.id === lumpId);
    if (lump) for (const g of lump.groups || []) was.whole.add(g.key);
    await this.openLump(lumpId, was);
  }

  _closePicker() {
    if (!this.picker) return;
    const { box, lumpId } = this.picker;
    this.picker = null;
    if (box.parentNode) box.parentNode.removeChild(box);
    if (this.doc.removeEventListener && this._onKey) this.doc.removeEventListener('keydown', this._onKey);
    this._onKey = null;
    const lump = this.cy && this.cy.getElementById(lumpId);
    if (lump && lump.nonempty()) lump.removeClass('is-lit');
  }

  // ── marks, the pick and Continue follow the store; the picture is not laid out again ─────────────────────

  _restyle() {
    const name = this.writes();
    if (this.cy) {
      const seeds = new Set(this._seeds());
      const lit = this._litPaths();
      this.cy.batch(() => {
        this.cy.nodes('[kind = "lump"]').toggleClass('is-dim', Boolean(lit));
        this.cy.edges('[kind = "lump"]').toggleClass('is-dim', Boolean(lit));
        this.cy.nodes('[kind = "node"]').forEach((n) => {
          const id = n.id();
          n.toggleClass('is-path', Boolean(lit) && lit.nodes.has(id));
          n.toggleClass('is-dim', Boolean(lit) && !lit.nodes.has(id));
          n.toggleClass('is-seed', seeds.has(id));
          n.toggleClass('is-marked', Boolean(name) && this.markings.signOf(name, id) !== SIGN.ABSENT);
          n.toggleClass('is-control', Boolean(name) && this.markings.signOf(name, id) === SIGN.CONTROL);
          n.toggleClass('is-selected', id === this.selected);
        });
        this.cy.edges('[kind = "edge"]').forEach((e) => {
          e.toggleClass('is-path', Boolean(lit) && lit.edges.has(e.id()));
          e.toggleClass('is-dim', Boolean(lit) && !lit.edges.has(e.id()));
          e.toggleClass('is-hot', Boolean(this.selected) && (e.data('source') === this.selected || e.data('target') === this.selected));
        });
      });
    }
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

  /** Mark or unmark one node in the marking this step writes; the store tells every part that reads it. Shift makes it
   *  a control - the board's markingIntent, one rule for the two screens (lead 10-09). */
  toggleMark(id, event) {
    const name = this.writes();
    if (name) this.markings.toggle(name, id, markingIntent(event).sign);
  }

  /** Pick a node: the facts box is swapped; the picture is not laid out again. */
  select(id) {
    this.pickedLump = null;
    this.selected = id;
    this._swapFacts();
    this._restyle();
  }
}
