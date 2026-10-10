// ═══════════════════════════════════════════════════════════════════════════════
// REACH TABLE — the side by side table as a formula, the same on any scheme (owner 10-10 «추상화해서 만들어 어떤
// 스킴에서도 작동하게», lead 5cf5c3401). No predicate or type word here: rows, groups and columns come in, the rest is
// the walk's own graph.
//   groups  S1..Sk - each its starts and Ri, the nodes it reached; Gi = the edges with both ends in Ri
//   rows    X - a set of node ids (a type's nodes, or a marking); a row is keyed by its node id
//   column  c = (P, a) - P the (predicate, direction) steps, a an attribute of P's last edge, a key or an attribute of
//           its end node, or the end node's name
//   cell    cell(x, i, c) = { a(end) | the ways from x along P inside Gi } - x not in Ri: missing; no value: empty
// ═══════════════════════════════════════════════════════════════════════════════

import { isBlank } from '../absent.js';

/** The ways one cell follows at most; past them the cell says it has more. */
export const WAYS_A_CELL = 50;

/** The walk's graph, indexed once: nodes by id, each node's edges out and in. */
export function indexGraph(result) {
  const nodes = new Map(((result && result.nodes) || []).map((n) => [n.id, n]));
  const out = new Map();
  const into = new Map();
  for (const e of (result && result.edges) || []) {
    if (!out.has(e.source)) out.set(e.source, []);
    out.get(e.source).push(e);
    if (!into.has(e.target)) into.set(e.target, []);
    into.get(e.target).push(e);
  }
  return { nodes, out, into };
}

/**
 * The groups from the answer's reach (propagation.ranked[].reach, one count per group in `starts`' order): each its
 * starts and Ri - its starts and every node it reached. Null when the answer ranks nothing.
 * @param {Array<{name: string, starts: string[]}>} starts
 */
export function groupsOf(result, starts) {
  const ranked = result && result.propagation && result.propagation.ranked;
  if (!Array.isArray(ranked)) return null;
  return starts.map((group, i) => ({
    name: group.name,
    starts: [...group.starts],
    inside: new Set([...group.starts, ...ranked.filter((row) => Number((row.reach || [])[i]) > 0).map((row) => row.id)]),
  }));
}

/** The far end of an edge taken in `direction` from where it stands. */
const farOf = (e, direction) => (direction === 'incoming' ? e.source : e.target);

/** What a column reads at one end of a way: its last edge's attribute, its end node's attribute, or its end's name. */
function valueAt(index, end, value) {
  const node = index.nodes.get(end.node) || {};
  if (value.on === 'label') return node.label || end.node;
  if (value.on === 'key') return (node.keys || {})[value.name];
  if (value.on === 'edge') return end.edge ? ((end.edge.qualifiers || {})[value.name]) : undefined;
  return (node.attributes || {})[value.name];
}

/**
 * One cell: what column `column` reads from row `x` inside group `inside` (Ri) - every way from x along the column's
 * steps over edges with both ends inside. Not inside: missing. A value is kept per way (none overwrites another).
 * @returns {{missing: boolean, values: Array, nodes: string[], more: boolean}} - `nodes[k]` gave `values[k]`
 */
export function cellOf(index, inside, x, column, cap = WAYS_A_CELL) {
  const got = readsOf(index, inside, x, column, cap);
  return { missing: got.missing, values: got.reads.map((r) => r.value), nodes: got.reads.map((r) => r.node), more: got.more };
}

/** What a cell reads, way by way - its value, its last edge, its end node; the trend's points are these (lead f984ab01d). */
export function readsOf(index, inside, x, column, cap = WAYS_A_CELL) {
  if (!inside.has(x)) return { missing: true, reads: [], more: false };
  const { ends, more } = waysOf(index, inside, [x], column.steps, cap);
  const reads = ends.map((end) => ({ value: valueAt(index, end, column.value), edge: end.edge, node: end.node }))
    .filter((r) => !isBlank(r.value));
  return { missing: false, reads, more };
}

/** A value in words: a boolean ✓ ✗, a list joined, the rest as it came. */
export const valueWords = (v) => (typeof v === 'boolean' ? (v ? '✓' : '✗') : Array.isArray(v) ? v.join(' · ') : String(v));

/** Every way from `starts` along `steps` - inside `inside` when given - its end node and last edge; past `cap`, `more`. */
function waysOf(index, inside, starts, steps, cap) {
  let ends = starts.map((node) => ({ node, edge: null }));
  let more = false;
  for (const step of steps) {
    const next = [];
    for (const end of ends) {
      const edges = (step.direction === 'incoming' ? index.into : index.out).get(end.node) || [];
      for (const e of edges) {
        if (e.predicate !== step.predicate || (inside && !inside.has(farOf(e, step.direction)))) continue;
        if (next.length >= cap) { more = true; break; }
        next.push({ node: farOf(e, step.direction), edge: e });
      }
    }
    ends = next;
  }
  return { ends, more };
}

/** The routes the rows take in this walk, up to `limit` steps, each its steps and the words that say them. */
export function routesFrom(index, rows, limit = 3, most = 60) {
  const out = [];
  let level = [{ steps: [], ends: new Set(rows) }];
  for (let depth = 0; depth < limit && out.length < most; depth += 1) {
    const next = [];
    for (const route of level) {
      const by = new Map();
      for (const at of route.ends) {
        for (const [direction, edges] of [['outgoing', index.out.get(at)], ['incoming', index.into.get(at)]]) {
          for (const e of edges || []) {
            const key = `${e.predicate}\u0000${direction}`;
            if (!by.has(key)) by.set(key, { step: { predicate: e.predicate, direction }, ends: new Set() });
            by.get(key).ends.add(farOf(e, direction));
          }
        }
      }
      for (const { step, ends } of [...by.values()].sort((a, b) => (a.step.predicate < b.step.predicate ? -1 : 1))) {
        if (out.length >= most) break;
        const steps = [...route.steps, step];
        const r = { steps, ends, words: steps.map(stepWords) };
        out.push(r);
        next.push(r);
      }
    }
    level = next;
  }
  return out.map(({ steps, words, ends }) => ({ steps, words,
    to: [...new Set([...ends].map((id) => (index.nodes.get(id) || {}).type).filter(Boolean))].sort() }));
}

/** What a route's end holds in this walk: its last edges' attributes, its end nodes' keys and attributes, their name. */
export function valuesAt(index, rows, steps) {
  const { ends } = waysOf(index, null, rows, steps, WAYS_A_CELL * 20);
  const names = { edge: new Set(), key: new Set(), node: new Set() };
  for (const end of ends) {
    for (const name of Object.keys((end.edge && end.edge.qualifiers) || {})) names.edge.add(name);
    const node = index.nodes.get(end.node) || {};
    for (const name of Object.keys(node.keys || {})) names.key.add(name);
    for (const name of Object.keys(node.attributes || {})) names.node.add(name);
  }
  return [...[...names.edge].sort().map((name) => ({ on: 'edge', name })),
    ...[...names.key].sort().map((name) => ({ on: 'key', name })),
    ...[...names.node].sort().map((name) => ({ on: 'node', name })),
    ...(ends.length ? [{ on: 'label', name: 'name' }] : [])];
}

/** A cell's one number - a JSON number, not a numeral in a string - or null. */
const numberOf = (cell) => (cell && !cell.missing && cell.values.length === 1 && typeof cell.values[0] === 'number'
  && Number.isFinite(cell.values[0]) ? cell.values[0] : null);

/**
 * What a column's values are, judged once by their JSON type (lead a2eb4a516): 'number', 'string', 'boolean', 'mixed'
 * when more than one, 'empty' when none. A list is a string; a time-like string is a string.
 */
export function valueKind(values) {
  const kinds = new Set(values.filter((v) => !isBlank(v))
    .map((v) => (typeof v === 'number' ? 'number' : typeof v === 'boolean' ? 'boolean' : 'string')));
  if (!kinds.size) return 'empty';
  return kinds.size === 1 ? [...kinds][0] : 'mixed';
}

/** Δ: two groups, each cell one number - the first less the second; otherwise null. */
export function deltaOf(cells) {
  if (cells.length !== 2) return null;
  const [a, b] = cells.map(numberOf);
  return a === null || b === null ? null : a - b;
}

/** A step's words: its predicate, «(in)» when it is taken in (the mockup v2). */
export const stepWords = (step) => (step.direction === 'incoming' ? `${step.predicate} (in)` : step.predicate);

/**
 * The columns a set of rows gets by itself (lead a2eb4a516, after 25ac10ad8): the rows' keys and every attribute they
 * carry (no step - the node's own), then for each (predicate, direction) step the rows take in this walk, every attribute
 * its edges carry - what the answer carries, nothing declared in between. The far node: «+ Column».
 * @param {string[]} keyOrder  the declaration's key order, for the keys it names
 */
export function defaultColumns(index, rows, keyOrder = []) {
  const carried = (field) => [...new Set(rows.flatMap((x) => Object.keys((index.nodes.get(x) || {})[field] || {})))];
  const keys = carried('keys');
  const columns = [...[...keyOrder.filter((k) => keys.includes(k)), ...keys.filter((k) => !keyOrder.includes(k)).sort()]
    .map((name) => ({ steps: [], value: { on: 'key', name }, words: [name] })),
  ...carried('attributes').sort().map((name) => ({ steps: [], value: { on: 'node', name }, words: [name] }))];
  const seen = new Map();
  for (const x of rows) {
    for (const [direction, edges] of [['outgoing', index.out.get(x)], ['incoming', index.into.get(x)]]) {
      for (const e of edges || []) {
        const key = `${e.predicate}\u0000${direction}`;
        if (!seen.has(key)) seen.set(key, { predicate: e.predicate, direction, names: new Set() });
        for (const name of Object.keys(e.qualifiers || {})) seen.get(key).names.add(name);
      }
    }
  }
  const steps = [...seen.values()].sort((a, b) => (a.predicate < b.predicate ? -1 : a.predicate > b.predicate ? 1
    : (a.direction < b.direction ? 1 : -1)));
  for (const s of steps) {
    const way = [{ predicate: s.predicate, direction: s.direction }];
    for (const name of [...s.names].sort()) columns.push({ steps: way, value: { on: 'edge', name }, words: [stepWords(s), name] });
  }
  return columns;
}

// ⚰️ viaDepth retired 10-10 (lead df11f9e81): widened into walk/paths.js shortestRoutes - every shortest route, not the
// last predicate - which the table's Route column reads.

/**
 * The table: each row, each column's cell in each group, the column's Δ, and whether the groups differ or one missed.
 * @returns {Array<{id: string, cells: Array<Array<object>>, deltas: Array<number|null>, differs: boolean, missing: boolean}>}
 */
export function tableOf(index, groups, rows, columns, cap = WAYS_A_CELL) {
  return rows.map((id) => {
    const cells = columns.map((column) => groups.map((g) => cellOf(index, g.inside, id, column, cap)));
    const said = (cell) => (cell.missing ? '\u0000missing' : JSON.stringify(cell.values));
    const reached = groups.map((g) => g.inside.has(id));
    return {
      id,
      cells,
      deltas: cells.map(deltaOf),
      missing: reached.some((r) => !r),
      differs: reached.some((r) => r !== reached[0]) || cells.some((byGroup) => byGroup.some((c) => said(c) !== said(byGroup[0]))),
    };
  });
}
