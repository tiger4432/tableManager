// THE ROUTE - the root part's rows (base set 2, lead 10-14 after the owner «안 되겠구나 · 다른 다이라»): a part walks
// from its start only along a route, from the start's type to its row type - the walk page's route list (walk/derive.js
// walkableRoutes: the declaration's paths the walk takes) - and its rows are that route's ends, not every node of the row
// type the walk reached (a bonding die's siblings came in through their wafer and brought every core wafer). A start of
// the row type itself is its own row (the seed route, no step). The walk asks the route's predicates and steps and the
// slots' own on top, so the slots can be read from the rows.

import { walkableRoutes } from '../walk/derive.js';
import { entityOfId } from '../rnd_board/api.js';
import { hubOf } from './hubs.js';
import { isExpression, wayOf, columnsOf } from './slot.js';
import { compile } from '../expression.js';

/** The route of a start of the row type itself: no step, the start its own row. */
export const seedRoute = (type) => ({ hops: 0, follow: [], chain: [type] });
/** A route's identity - its steps, its predicates, its types. */
export const routeKey = (r) => (r ? `${r.hops}|${[...(r.follow || [])].sort().join(',')}|${(r.chain || []).join('>')}` : '');
/** A route in words - «die · bonded_from → die · in_container → wafer»; the seed route «(start)». */
export const routeWords = (r) => (r && r.hops ? `${r.chain.join(' → ')} · ${r.follow.join(' · ')}` : '(start)');

/** A start entry's node type: a hub its row type, a node its id's (the server's entity id) - known before any walk. */
export function typeOfStart(id) {
  const hub = hubOf(id);
  return hub ? hub.row : (entityOfId(id) || {}).type || null;
}

/** The routes from a start type to a row type, the shortest first; the seed route first when they are one type. A route
 *  with a loop on a type it stands on (die -bonded_from-> die) is offered with that loop taken too - one step more, the
 *  type twice on its chain (the walk page's loop chips, rnd_board/api.js routeWith). */
export function routesFor(vocabulary, from, to) {
  if (!from || !to) return [];
  const walked = walkableRoutes(vocabulary, from, to).flatMap((r) => [r, ...(r.loops || []).map((loop) => {
    const at = r.chain.indexOf(loop.at);
    return { hops: r.hops + 1, follow: [...r.follow, loop.predicate], chain: [...r.chain.slice(0, at + 1), loop.at, ...r.chain.slice(at + 1)] };
  })]);
  return from === to ? [seedRoute(to), ...walked] : walked;
}

/** The route a declaration takes: the one it names when it is still a route, else the shortest. */
export function routeOf(decl, routes) {
  // a route it names that is not a route from its start is no route - never the shortest instead (the 18766 run: a
  // wafer route named, the start dies - it walked the dies' own wafer and drew its measurements as the core's)
  if (decl && decl.route) return routes.find((r) => routeKey(r) === routeKey(decl.route)) || null;
  return routes[0] || null;
}

/** What a walk along a route asks: its predicates and the slots' (`follow`), its steps and the longest slot's (`hops`). */
export function walkOfRoute(route, encode) {
  // An expression's ways ([measures.value] · [in_container~.x]) are its steps (slot.js wayOf), as a value slot's are.
  const ways = (s) => { const c = compile(s.expr); return c.ok ? c.names.map(wayOf).filter(Boolean).map((w) => ({ steps: w.steps })) : []; };
  // every column of every slot - a slot of several columns walks each column's steps (lead 10-14: a pill of two lost its
  // steps and its inner column read (Empty))
  const slots = Object.values(encode || {}).flatMap(columnsOf).flatMap((s) => (isExpression(s) ? ways(s) : [s]))
    .filter((s) => s && Array.isArray(s.steps));
  const follow = [...new Set([...route.follow, ...slots.flatMap((s) => s.steps.map((st) => st.predicate))])];
  const hops = route.hops + Math.max(0, ...slots.map((s) => s.steps.length));
  return { follow, hops: Math.max(1, hops) };
}

/** The route's ends in a walk's answer: from the seeds, step by step, the nodes an edge of the route's predicates
 *  (either way) reaches that are of the next type on the route's chain. */
export function routeEnds(answer, seeds, route) {
  const typeOf = new Map(((answer && answer.nodes) || []).map((n) => [n.id, n.type]));
  const follow = new Set(route.follow);
  let at = new Set(seeds);
  for (let k = 1; k < route.chain.length; k += 1) {
    const next = new Set();
    for (const e of (answer && answer.edges) || []) {
      if (!follow.has(e.predicate)) continue;
      if (at.has(e.source) && typeOf.get(e.target) === route.chain[k]) next.add(e.target);
      if (at.has(e.target) && typeOf.get(e.source) === route.chain[k]) next.add(e.source);
    }
    at = next;
  }
  return [...at].filter((id) => typeOf.get(id) === route.chain[route.chain.length - 1]);
}
