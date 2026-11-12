// TABLES - the walk from one table's rows to another's (owner 11-11 «표 걷기», lead): the paths between two tables read
// off the declaration, and one hop - a row set kept as a server marking, reached along a path to the next table's rows,
// kept again. No DOM; the page and its boxes call these.
import { pathsBetween } from '../rnd_board/api.js';

/** A row's node id - the server's spelling («relation:row id», ledger_subgraph's virtual atoms, walk_shadow). */
export const rowNodeId = (table, rowId) => `${table}:${rowId}`;

/** rowNodeId's pair: {table, rowId} - a row id of digits as the number the table holds; not a row's id: null. */
export function rowOfNodeId(id) {
  const s = String(id ?? '');
  const at = s.indexOf(':');
  if (at <= 0) return null;
  const rowId = s.slice(at + 1);
  return { table: s.slice(0, at), rowId: /^-?\d+$/.test(rowId) ? Number(rowId) : rowId };
}

/** The node types a table's rows name: the entities its sources' columns key (the declaration's sources[].columns). */
export function typesOfTable(declaration, table) {
  const sources = ((declaration && declaration.sources) || []).filter((s) => s.relation === table);
  return [...new Set(sources.flatMap((s) => (s.columns || []).filter((c) => c.role === 'key' && c.entity).map((c) => c.entity)))];
}

/**
 * The ways from `from`'s rows to `to`'s: a type `from` names, then a path of the type graph (pathsBetween) to a type `to`
 * names, through a predicate `to` emits - else no atom read is one of `to`'s rows. One a type and its follow, the
 * shortest first; {type, follow, chain, hops}.
 */
export function routesBetween(declaration, from, to) {
  const emitted = new Set(((declaration && declaration.sources) || []).filter((s) => s.relation === to).flatMap((s) => s.emits || []));
  const ends = typesOfTable(declaration, to);
  const out = new Map();
  for (const type of typesOfTable(declaration, from)) {
    for (const end of ends) {
      for (const route of pathsBetween(declaration, type, end)) {
        if (!route.follow.some((p) => emitted.has(p))) continue;
        const key = `${type}|${route.follow.join('|')}`;
        if (!out.has(key) || route.hops < out.get(key).hops) out.set(key, { type, follow: route.follow, chain: route.chain, hops: route.hops });
      }
    }
  }
  return [...out.values()].sort((a, b) => a.hops - b.hops || a.follow.length - b.follow.length);
}

/** A path's words: its type and predicates. */
export const routeWords = (route) => [route.type, ...route.follow].join(' · ');

async function post(deps, path, body) {
  const world = deps.world ? `?world=${encodeURIComponent(deps.world)}` : '';
  const res = await deps.fetch(`${deps.apiBase}${path}${world}`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
  const said = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = said && said.detail;
    throw new Error((detail && (detail.message || detail.reason)) || (typeof detail === 'string' ? detail : `${path} failed (${res.status})`));
  }
  return said;
}

/** Keep a table's rows on the server (POST /markings, the rows by row_id): {id, rev}. The rows ride the body, never a URL. */
export const keepRows = (deps, table, rowIds) => post({ ...deps, world: null }, '/markings', { table, column: 'row_id', values: rowIds });

/** One hop: the rows of `to` a kept marking reaches along `route` (trace_router.reach) - {rows, count, seeds, left_out}. */
export const reachRows = (deps, marking, route, to) => post(deps, '/api/ledger/subgraph',
  { reach: { marking, type: route.type, follow: route.follow, to } });
