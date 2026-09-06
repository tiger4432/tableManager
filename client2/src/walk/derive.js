// The two pure decisions behind 「경로를 누르면 follow 가 채워진다」.
//
// WHY THIS IS ITS OWN MODULE. Both lived as closures inside `boot()`, which means the only way
// to score them was to stand up a DOM. The standing rule for that is to move the logic being
// measured into a module the harness can `import` rather than to reach into the file — so they
// live here, `main.js` calls them, and `walk_route_fill_harness.mjs` imports the same two
// functions the screen runs.
//
// 🔴 BOTH EXIST BECAUSE OF A MEASURED DEFECT, not for symmetry. Clicking a route filled `hops`
//    and ticked nothing: the derivation speaks bare names (`observed`) and the checkboxes carry
//    the declared spelling (`observed@1`), and the second-hop predicate had no checkbox at all
//    because the list only offered predicates whose subject is the START type.

/** `wafer@1` -> `wafer`. The declaration versions its names; the type graph and the wire do not. */
export function bareName(value) {
  return String(value || '').split('@')[0];
}

/**
 * The declared spellings for a route's predicates.
 *
 * 🔴 Matching is on the BARE name in both directions. Comparing the two spellings directly is
 *    the defect this closes, and it fails silently: no name matches, so nothing is ticked and
 *    the screen looks like it simply ignored the click.
 */
export function followFromRoute(declaredNames, routeFollow) {
  const wanted = new Set((routeFollow || []).map(bareName));
  return (declaredNames || []).filter((name) => wanted.has(bareName(name)));
}

/**
 * Which follow checkboxes to draw.
 *
 * 🔴 THE START-TYPE FILTER STAYS. Its reason holds: someone choosing a seed should see the
 *    predicates that leave it, not the whole vocabulary. What it cannot do alone is show a
 *    LATER hop — `wafer -inspected-> die -observed-> defect` needs `observed`, whose subject is
 *    `die` — so a selected predicate is added back. A box that is ticked but not drawn is the
 *    screen hiding what it is about to send, which is worse than showing one extra row.
 */
export function followChoices(fromStartType, declaredNames, selected) {
  const picked = selected instanceof Set ? selected : new Set(selected || []);
  const extra = (declaredNames || []).filter((name) => picked.has(name));
  return [...new Set([...(fromStartType || []), ...extra])];
}

/**
 * The types the walk treats as static, read off the declaration rather than decided here.
 *
 * 🔴 THE PREDICATE IS `class === 'static'` AND NOTHING ELSE, because that is the server's:
 *    `_static_types()` collects exactly that, so a type with NO class is dynamic to the walk.
 *    Measured 2026-09-06 on the served declaration: three carry it (defect_kind, quantity,
 *    recipe) and six carry nothing at all - and treating those six as "unknown, so leave them
 *    alone" is what leaves refused routes on the screen.
 * ⚠️ No list of type names lives in this client. Asking the declaration means the screen follows
 *    it the day it changes; writing the names here would make this the second author of a fact.
 */
export function staticTypes(entities) {
  return new Set((entities || [])
    .filter((e) => e && e.class === 'static')
    .map((e) => bareName(e.type)));
}

/**
 * Drop the routes the walk will refuse.
 *
 * 🔴 THE STEP THAT IS REFUSED IS `static -> not static`, NOT "the path touches a static type".
 *    static -> static is a mechanism chain and the walk allows it, so filtering on "passes
 *    through a static type" would delete the answers `defect_kind` exists to give.
 *    Measured live before this existed: `wafer -> quantity -> defect_kind -> defect` was offered
 *    and returned the seed alone - one node, or zero with a collect - while the route the screen
 *    should have led with returned 121.
 */
export function keepWalkableRoutes(entities, routes) {
  const statics = staticTypes(entities);
  return (routes || []).filter((route) => {
    const chain = (route && route.chain) || [];
    for (let i = 0; i + 1 < chain.length; i += 1) {
      const here = bareName(chain[i]);
      const next = bareName(chain[i + 1]);
      if (statics.has(here) && !statics.has(next)) return false;
    }
    return true;
  });
}
