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
import { IMAGE_TYPE } from '../grid_image_column.js';

/** The ways one cell draws at most; past them the cell says «read of total» and the walk screen offers Show all. */
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

/** What a column reads at one end of a way, and what says when - the end's time (owner 10-10 e54560dc2): its last edge's
 *  attribute, that edge; its end node's attribute, the node's own record of that value (attributes_by_world, lead 10-11
 *  E2c); its end's name or a key, the way's last edge (a node says no time for those). */
function valueAt(index, end, value) {
  const node = index.nodes.get(end.node) || {};
  if (value.on === 'label') return { value: node.label || end.node, when: end.edge };
  if (value.on === 'key') return { value: (node.keys || {})[value.name], when: end.edge };
  // An image reference is what the answer says it is (server c5463a475: the column's declared type), never the value's
  // shape - an edge's `column_types` by qualifier, a node's own record's `column_type`.
  if (value.on === 'edge') return { value: end.edge ? ((end.edge.qualifiers || {})[value.name]) : undefined, when: end.edge,
    image: Boolean(end.edge) && (end.edge.column_types || {})[value.name] === IMAGE_TYPE };
  const said = (node.attributes || {})[value.name];
  const when = ((node.attributes_by_world || {})[value.name] || []).find((s) => s && sameValue(s.value, said)) || null;
  return { value: said, when, image: Boolean(when) && when.column_type === IMAGE_TYPE };
}

/** Two values the same as said - a list (a many attribute) by its items, not by being one object (lead 10-11 W ⑬). */
export const sameValue = (a, b) => JSON.stringify(a) === JSON.stringify(b);

/** A column whose value something says - an edge's attribute or a node's - not who a node is, its key or its name
 *  (lead 10-11: identity is never a trend's). */
export const saysValue = (column) => column.value.on === 'edge' || column.value.on === 'node';

/**
 * One cell: what column `column` reads from row `x` inside group `inside` (Ri) - every way from x along the column's
 * steps over edges with both ends inside. Not inside: missing. A value is kept per way (none overwrites another).
 * @returns {{missing: boolean, values: Array, nodes: string[], more: boolean, images: boolean[]}} - `nodes[k]` gave
 *   `values[k]`, an image reference when `images[k]`
 */
export function cellOf(index, inside, x, column, cap = WAYS_A_CELL) {
  const got = readsOf(index, inside, x, column, cap);
  return { missing: got.missing, values: got.reads.map((r) => r.value), nodes: got.reads.map((r) => r.giver), more: got.more,
    read: got.read, total: got.total, images: got.reads.map((r) => Boolean(r.image)) };
}

/** What a cell reads, way by way - its value, what says when, its last edge, its end node, and who gave it: an edge's value
 *  its subject's (the atom's), a node's its own (lead 10-11 W 11: a source line one meaning); the trend's points are these
 *  (lead f984ab01d). */
export function readsOf(index, inside, x, column, cap = WAYS_A_CELL) {
  if (!inside.has(x)) return { missing: true, reads: [], more: false, read: 0, total: 0 };
  const { ends, more, total } = waysOf(index, inside, [x], column.steps, cap, column);
  const reads = ends.map((end) => ({ ...valueAt(index, end, column.value), edge: end.edge, node: end.node,
    giver: column.value.on === 'edge' && end.edge ? end.edge.source : end.node }))
    .filter((r) => !isBlank(r.value));
  return { missing: false, reads, more, read: ends.length, total };
}

/** A read's records (lead 10-12 C3: Long a line a record) - its edge's every atom (`records`, server e5e0a87e2), its end
 *  node's every registration of the name; each its value, when, point and `record` - its claim id, the one identity two
 *  ways to the same record share. A read the answer lists no records for is its one record. */
export function recordsOf(index, column, r) {
  const { on, name } = column.value;
  const listed = on === 'edge' ? r.edge && r.edge.records : on === 'node' ? ((index.nodes.get(r.node) || {}).records || {})[name] : null;
  if (!Array.isArray(listed) || !listed.length) return [{ ...r, point: pointOf(column, r.edge), record: r.edge || r.node }];
  return listed.map((rec) => ({ ...r, when: rec, record: rec.claim_id ?? rec, point: pointOf(column, rec),
    ...(on === 'edge' ? { value: (rec.qualifiers || {})[name], image: (rec.column_types || {})[name] === IMAGE_TYPE }
      : { value: rec.value, image: rec.column_type === IMAGE_TYPE }) }))
    .filter((x) => !isBlank(x.value));
}

/** A column by what it reads - its steps, the node it ends at when it names one, its value - not its place. */
export const columnKey = (column) => JSON.stringify([column.steps, column.end || null, column.endTypes || null, column.value]);
/** The group a column stands in - its steps and the node it ends at (lead 10-11 W addendum 8). */
export const groupKey = (column) => JSON.stringify([column.steps, column.end || null, column.endTypes || null]);

/** A value in words: a boolean ✓ ✗, a list joined, the rest as it came. */
export const valueWords = (v) => (typeof v === 'boolean' ? (v ? '✓' : '✗') : Array.isArray(v) ? v.join(' · ') : String(v));

/** A read's point (lead 10-11 W, addendum 2 ⑭): its edge's other attributes beside the column's value, blanks out, as
 *  [name, value] - Long's «point», the trend's Split by and a dot's title read this one. A node's own value has none. */
export const pointOf = (column, edge) => (column.value.on === 'edge' && edge
  ? Object.entries(edge.qualifiers || {}).filter(([name, v]) => name !== column.value.name && !isBlank(v)) : []);
export const pointWords = (point) => point.map(([name, v]) => `${name} ${valueWords(v)}`).join(' · ');

/** Every way from `starts` along `steps` - inside `inside` when given; a column's (`last`) ending at its node or at its far
 *  types when it names them - its end node and last edge; past `cap`, `more`. */
export function waysOf(index, inside, starts, steps, cap, last = null) {
  const lastId = last && last.end;
  const lastTypes = last && last.endTypes;
  /** The edges `step` takes from `node`: its predicate and direction, the far end inside, the last step's at the column's end. */
  const taken = (node, step, isLast) => ((step.direction === 'incoming' ? index.into : index.out).get(node) || []).filter((e) => {
    const far = farOf(e, step.direction);
    if (e.predicate !== step.predicate || (inside && !inside.has(far))) return false;
    return !(isLast && ((lastId && far !== lastId) || (lastTypes && !lastTypes.includes((index.nodes.get(far) || {}).type || ''))));
  });
  let ends = starts.map((node) => ({ node, edge: null }));
  // Every way counted - by node, so a wide frontier costs its nodes, not its ways - the first `cap` kept (lead 10-13:
  // a cut cell says «50 of 2,199»).
  let counts = new Map();
  for (const node of starts) counts.set(node, (counts.get(node) || 0) + 1);
  for (const [k, step] of steps.entries()) {
    const isLast = k === steps.length - 1;
    const tally = new Map();
    for (const [node, n] of counts) {
      for (const e of taken(node, step, isLast)) { const far = farOf(e, step.direction); tally.set(far, (tally.get(far) || 0) + n); }
    }
    const next = [];
    for (const end of ends) {
      for (const e of taken(end.node, step, isLast)) {
        if (next.length >= cap) break;
        next.push({ node: farOf(e, step.direction), edge: e });
      }
      if (next.length >= cap) break;
    }
    ends = next;
    counts = tally;
  }
  const total = [...counts.values()].reduce((a, b) => a + b, 0);
  return { ends, more: total > ends.length, total };
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
        const r = { steps, ends, words: [...(route.words || []), stepWords(step, typesAt(index, ends).join(' / '))] };
        out.push(r);
        next.push(r);
      }
    }
    level = next;
  }
  return out.map(({ steps, words, ends }) => ({ steps, words, to: typesAt(index, ends) }));
}

/** The types of some nodes of the walk, sorted, each once. */
const typesAt = (index, ids) => [...new Set([...ids].map((id) => (index.nodes.get(id) || {}).type).filter(Boolean))].sort();

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

/** A value as a number, or null: the server sends text, so '10.1' reads as 10.1 and 'S1' or '' as nothing - the one
 *  answer to «is this a number» (lead 10-11: a numeral in text is a number - the trend's axis, a column's kind, Δ; the
 *  expression calculator's folds). A numeral is, trimmed, only sign · digits · point · exponent (lead 10-13): '29,50',
 *  '29 mm' and '0x10' are text. */
const NUMERAL = /^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/;
export function numberOf(value) {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value !== 'string' || !NUMERAL.test(value.trim())) return null;
  const n = Number(value.trim());
  return Number.isFinite(n) ? n : null;
}

/** A cell's one number, or null. */
const cellNumber = (cell) => (cell && !cell.missing && cell.values.length === 1 ? numberOf(cell.values[0]) : null);

/**
 * What a column's values are, judged once (lead a2eb4a516, 10-11): 'number' - a numeral in text one -, 'string',
 * 'boolean', 'mixed' when more than one, 'empty' when none. A list is a string; a time-like string is a string.
 */
export function valueKind(values) {
  const kinds = new Set(values.filter((v) => !isBlank(v))
    .map((v) => (numberOf(v) !== null ? 'number' : typeof v === 'boolean' ? 'boolean' : 'string')));
  if (!kinds.size) return 'empty';
  return kinds.size === 1 ? [...kinds][0] : 'mixed';
}

/** Δ: two groups, each cell one number - the first less the second; otherwise null. */
export function deltaOf(cells) {
  if (cells.length !== 2) return null;
  const [a, b] = cells.map(cellNumber);
  return a === null || b === null ? null : a - b;
}

/** A step's words: its predicate, an arrow the way it is taken - out «→», in «←» - and what stands at its far end (lead
 *  10-11 W: «(in)» retired). */
export const stepWords = (step, far = '') => `${step.predicate} ${step.direction === 'incoming' ? '←' : '→'}${far ? ` ${far}` : ''}`;

/**
 * The columns a set of rows gets by itself (lead a2eb4a516, after 25ac10ad8): the rows' keys and every attribute they
 * carry (no step - the node's own), then for each (predicate, direction) step the rows take in this walk, every attribute
 * its edges carry - what the answer carries, nothing declared in between. The far node: «+ Column».
 * @param {string[]} keyOrder  the declaration's key order, for the keys it names
 * @param {(type: string) => boolean} [perNode]  a far type whose nodes each stand a group of their own - the declared
 *        static ones, names (lead 10-11 W addendum 8, (다)); any other far type one group, each side its own values
 */
export function defaultColumns(index, rows, keyOrder = [], perNode = () => false) {
  const carried = (field) => [...new Set(rows.flatMap((x) => Object.keys((index.nodes.get(x) || {})[field] || {})))];
  const keys = carried('keys');
  const columns = [...[...keyOrder.filter((k) => keys.includes(k)), ...keys.filter((k) => !keyOrder.includes(k)).sort()]
    .map((name) => ({ steps: [], value: { on: 'key', name }, words: [name] })),
  ...carried('attributes').sort().map((name) => ({ steps: [], value: { on: 'node', name }, words: [name] }))];
  // A step's edges that carry values, a group of columns per far end (lead 10-11 W 10, addendum 8 (다)): a node of a type
  // that names - measures → bond_temp · value, its name in the column's -, else the far type - measures ← wafer · value,
  // each side its own values, Δ between.
  const seen = new Map();
  for (const x of rows) {
    for (const [direction, edges] of [['outgoing', index.out.get(x)], ['incoming', index.into.get(x)]]) {
      for (const e of edges || []) {
        const names = Object.keys(e.qualifiers || {}).filter((name) => !isBlank(e.qualifiers[name]));
        if (!names.length) continue;
        const id = farOf(e, direction);
        const type = (index.nodes.get(id) || {}).type || '';
        const end = perNode(type) ? id : null;
        const key = `${e.predicate}\u0000${direction}\u0000${end === null ? `type\u0000${type}` : end}`;
        if (!seen.has(key)) {
          seen.set(key, { predicate: e.predicate, direction, end, type, far: end === null ? type : (index.nodes.get(id) || {}).label || id, names: new Set() });
        }
        for (const name of names) seen.get(key).names.add(name);
      }
    }
  }
  const order = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
  const steps = [...seen.values()].sort((a, b) => order(a.predicate, b.predicate) || order(b.direction, a.direction) || order(a.far, b.far));
  for (const s of steps) {
    const way = [{ predicate: s.predicate, direction: s.direction }];
    const at = s.end === null ? { endTypes: [s.type] } : { end: s.end };
    for (const name of [...s.names].sort()) columns.push({ steps: way, ...at, value: { on: 'edge', name }, words: [stepWords(s, s.far), name] });
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
    const same = (a, b) => a.missing === b.missing && (a.missing || sameValue(a.values, b.values));
    const reached = groups.map((g) => g.inside.has(id));
    return {
      id,
      cells,
      deltas: cells.map(deltaOf),
      missing: reached.some((r) => !r),
      differs: reached.some((r) => r !== reached[0]) || cells.some((byGroup) => byGroup.some((c) => !same(c, byGroup[0]))),
    };
  });
}
