// THE ROUTES - the root part's rows (base set 2; owner 10-14 «마킹 걷기»): a part walks from its start's spread layer
// along every route from the start's types to its row type - the walk page's route list (walk/derive.js walkableRoutes:
// the declaration's paths the walk takes) - their predicates together, and its rows are every node of the row type the
// walk reached. A start of the row type itself is its own row (the seed route, no step). No route is chosen any more: a
// saved `route` is read and not walked.

import { walkableRoutes } from '../walk/derive.js';
import { entityOfId } from '../rnd_board/api.js';
import { hubOf } from './hubs.js';

/** The route of a start of the row type itself: no step, the start its own row. */
export const seedRoute = (type) => ({ hops: 0, follow: [], chain: [type] });

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
