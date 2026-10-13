// THE MARKING LAYER (owner 10-13 «마킹 전파를 미리 층으로», Spotfire's Relations): what a marking holds, spread ahead of
// time. The page's parts' walks are added to one graph (GraphBook - beside the marking store, no part's); a marking's
// members (a hub its members, hubs.js) spread over that graph along the page's declared relations only - a relation a
// node type, a predicate, a node type, one way or both - into the marking's layer, a node set computed once per change
// of the marking, the graph or the relations. Every place that asks «is this marked» reads it: a part's marked rows, the
// markings' limit, an expression's Marked(). No relation - the layer is the members, as before.

/** The page's walked graph: every part's answer added - its nodes and edges once each. `version` moves when it grows. */
export class GraphBook {
  constructor() {
    this.nodes = new Map();
    this.edges = new Map();
    this.version = 0;
  }

  add(answer) {
    let grew = false;
    for (const n of (answer && answer.nodes) || []) if (!this.nodes.has(n.id)) { this.nodes.set(n.id, n); grew = true; }
    for (const e of (answer && answer.edges) || []) {
      const key = e.id || `${e.source}\u0000${e.predicate}\u0000${e.target}`;
      if (!this.edges.has(key)) { this.edges.set(key, e); grew = true; }
    }
    if (grew) this.version += 1;
  }

  typeOf(id) { return (this.nodes.get(id) || {}).type || null; }
}

/** A relation as the page declares it: { from: node type, predicate, to: node type, both: boolean }. */
const relationKey = (r) => `${r.from}\u0000${r.predicate}\u0000${r.to}`;

export class MarkingLayers {
  /**
   * @param {{markings: import('../rnd_board/marking_store.js').MarkingStore, hubs: import('./hubs.js').HubBook,
   *          graph?: GraphBook, relations?: {get: (name: string) => Array}}} deps  relations - a store whose 'list' is
   *   the page's relations (none - no spreading)
   */
  constructor(deps) {
    this.markings = deps.markings;
    this.hubs = deps.hubs;
    this.graph = deps.graph || new GraphBook();
    this.relations = deps.relations || null;
    this.cache = new Map();
    this.ways = null;
    /** The last layer computed: its marking, its nodes, the ms it took; how many have been computed. */
    this.last = null;
    this.computed = 0;
  }

  relationList() { return (this.relations && this.relations.get('list')) || []; }

  /** The graph's steps along the relations: node -> the nodes a relation takes it to; and the nodes a relation edge
   *  touches. Built once per graph and relations. */
  steps() {
    const key = `${this.graph.version}|${JSON.stringify(this.relationList().map((r) => [relationKey(r), Boolean(r.both)]))}`;
    if (this.ways && this.ways.key === key) return this.ways;
    const rel = new Map(this.relationList().map((r) => [relationKey(r), r]));
    const next = new Map();
    const touched = new Set();
    const link = (a, b) => { if (!next.has(a)) next.set(a, []); next.get(a).push(b); };
    for (const e of this.graph.edges.values()) {
      const r = rel.get(`${this.graph.typeOf(e.source)}\u0000${e.predicate}\u0000${this.graph.typeOf(e.target)}`);
      if (!r) continue;
      touched.add(e.source);
      touched.add(e.target);
      link(e.source, e.target);
      if (r.both) link(e.target, e.source);
    }
    this.ways = { key, next, touched };
    return this.ways;
  }

  /** A marking's layer - its members spread along the relations - and the node types a spread from them can reach. */
  layer(name) {
    const ways = this.steps();
    const key = `${this.markings.version(name)}|${ways.key}`;
    const held = this.cache.get(name);
    if (held && held.key === key) return held;
    const t0 = now();
    const set = new Set(this.markings.entries(name).flatMap(([id]) => this.hubs.open(id)));
    // The members' own types - before the spread: a node of one that is not in is not marked, not «not known».
    const own = new Set([...set].map((id) => this.graph.typeOf(id)).filter(Boolean));
    const queue = [...set];
    while (queue.length) {
      for (const to of ways.next.get(queue.pop()) || []) if (!set.has(to)) { set.add(to); queue.push(to); }
    }
    // The types a spread reaches from the members' types and are not theirs - a node of one that no relation edge touches
    // is not known (its edge not walked yet); a node of the members' own type that is not in is not marked.
    const reach = new Set(own);
    for (let grew = true; grew;) {
      grew = false;
      for (const r of this.relationList()) {
        for (const [a, b] of r.both ? [[r.from, r.to], [r.to, r.from]] : [[r.from, r.to]]) if (reach.has(a) && !reach.has(b)) { reach.add(b); grew = true; }
      }
    }
    const types = new Set([...reach].filter((t) => !own.has(t)));
    const out = { key, set, types, members: this.markings.entries(name).length };
    this.cache.set(name, out);
    this.computed += 1;
    this.last = { name, nodes: set.size, ms: now() - t0 };
    return out;
  }

  /** Whether node `id` is in a marking: true, false - or null, not known: its type is one the relations reach from the
   *  members, but no relation edge of it has been walked yet. */
  marked(name, id) {
    if (!name) return false;
    const got = this.layer(name);
    if (got.set.has(id)) return true;
    const type = this.graph.typeOf(id);
    return type && got.types.has(type) && !this.steps().touched.has(id) ? null : false;
  }
}

const now = () => (typeof performance !== 'undefined' && performance.now ? performance.now() : Date.now());
