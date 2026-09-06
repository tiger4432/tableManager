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
