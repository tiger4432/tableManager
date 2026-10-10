// ═══════════════════════════════════════════════════════════════════════════════
// PATHS — every simple path between two vertices over a list of edges, either way along an edge (owner 10-10 «마킹 두
// 노드 이어서 하면 두 노드를 잇는 path 뜨게», lead 55f854fc5). The declaration's type routes (api.js pathsBetween) and
// the paths between two marked nodes of a walk are the same search; both call `simplePaths`.
// ═══════════════════════════════════════════════════════════════════════════════

/** A path's steps at most, the paths a kind keeps at most, and the paths one search finds at most. */
export const PATH_STEPS = 8;
export const PATHS_A_KIND = 20;
export const PATHS_AT_MOST = 2000;

/**
 * Every simple path from `from` to `to` over `edges` (`{from, to, predicate}`), either way along an edge, at most
 * `limit` steps. A self-loop is not a step. `to` may be `from` - a route back: the destination is the one vertex a path
 * may reach twice, on arriving. The edges' order is the paths' order. Stops once `most` are found: `cut`.
 * @returns {{paths: Array<Array<{predicate: string, next: string, edge: object}>>, cut: boolean}}
 */
export function simplePaths(edges, from, to, limit, most = Infinity) {
  const around = new Map();
  for (const edge of edges) {
    if (edge.from === edge.to) continue;
    for (const [at, next] of [[edge.from, edge.to], [edge.to, edge.from]]) {
      if (!around.has(at)) around.set(at, []);
      around.get(at).push({ edge, next });
    }
  }
  const paths = [];
  let cut = false;
  const walkOn = (at, seen, chain) => {
    if (chain.length && at === to) {
      if (paths.length >= most) cut = true;
      else paths.push(chain.slice());
      return;
    }
    if (chain.length >= limit) return;
    for (const { edge, next } of around.get(at) || []) {
      if (cut) return;
      if (seen.has(next) && next !== to) continue;
      seen.add(next);
      chain.push({ predicate: edge.predicate, next, edge });
      walkOn(next, seen, chain);
      chain.pop();
      seen.delete(next);
    }
  };
  walkOn(from, new Set([from]), []);
  return { paths, cut };
}

/** The predicates a walk's edges carry, each with its count, by name - the paths' edge list. */
export function edgeCounts(edges) {
  const counts = new Map();
  for (const e of edges || []) counts.set(e.predicate, (counts.get(e.predicate) || 0) + 1);
  return [...counts].map(([predicate, count]) => ({ predicate, count })).sort((x, y) => (x.predicate < y.predicate ? -1 : 1));
}

/**
 * The paths between nodes `a` and `b` of one walk (`nodes` `{id, type}`, `edges` `{id, source, target, predicate}`) over
 * the edges whose predicate is in `checked`, by kind: the node types and predicates passed, from `a` to `b`. A kind keeps
 * its first `PATHS_A_KIND` paths (`more` past them); the shortest kinds first, then the most paths.
 * @returns {{kinds: Array<{key: string, words: string[], steps: number, count: number, more: boolean,
 *   paths: Array<{nodes: string[], edges: object[]}>}>, found: number, cut: boolean}}
 */
export function pathKinds(walk, a, b, checked, caps = {}) {
  const typeOf = new Map(((walk && walk.nodes) || []).map((n) => [n.id, n.type]));
  const usable = ((walk && walk.edges) || [])
    .filter((e) => checked.has(e.predicate) && typeOf.has(e.source) && typeOf.has(e.target))
    .map((e) => ({ from: e.source, to: e.target, predicate: e.predicate, of: e }));
  const perKind = caps.perKind || PATHS_A_KIND;
  const { paths, cut } = typeOf.has(a) && typeOf.has(b) && a !== b
    ? simplePaths(usable, a, b, caps.steps || PATH_STEPS, caps.most || PATHS_AT_MOST) : { paths: [], cut: false };
  const kinds = new Map();
  for (const steps of paths) {
    const nodes = [a, ...steps.map((s) => s.next)];
    const words = [typeOf.get(a), ...steps.flatMap((s) => [s.predicate, typeOf.get(s.next)])];
    const key = words.join('\u0000');
    if (!kinds.has(key)) kinds.set(key, { key, words, steps: steps.length, count: 0, more: false, paths: [] });
    const kind = kinds.get(key);
    kind.count += 1;
    if (kind.paths.length < perKind) kind.paths.push({ nodes, edges: steps.map((s) => s.edge.of) });
    else kind.more = true;
  }
  return {
    kinds: [...kinds.values()].sort((x, y) => x.steps - y.steps || y.count - x.count),
    found: paths.length,
    cut,
  };
}
