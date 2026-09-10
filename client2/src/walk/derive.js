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
 * The result table's columns for one type section — each one saying WHERE its value comes from.
 *
 * 🔴 NO KEY NAME IS WRITTEN HERE OR ANYWHERE IN THIS CLIENT. The identity columns come from the
 *    DECLARATION's `keys` for that type, the attribute columns from its `attributes`, and the
 *    qualifier columns from what the response actually carried. So a name added to the
 *    declaration adds a column with no edit here, which is the whole point: the screen follows
 *    the declaration instead of copying it.
 * 🔴 `depth` first because the first question about a returned node is how far it is from the
 *    seed, and `id` last because it is long and is for picking up, not for reading.
 *
 * 🔴 WHY DESCRIPTORS AND NOT A LIST OF NAMES (ruling 130-C ㉡). This used to return names only,
 *    and the renderer split the identity columns back out of that answer by ARITHMETIC:
 *    `cols.slice(1, cols.length - 2 - qualNames.length)`. Two authors for one layout, and the
 *    day a THIRD group of columns appears the arithmetic mis-splits — attribute values would be
 *    looked up in `keys`, every attribute cell would come back empty, and NO ERROR WOULD BE
 *    RAISED. Worse, an empty cell is the CORRECT rendering for a declared attribute the walk
 *    never reached, so the wrong screen and the right screen are the same pixels. Saying where
 *    each column reads from removes the second author instead of correcting its arithmetic.
 *
 * 🔵 `attributes` IS ON THE WIRE (measured 2026-09-10, C-69). `/declaration` carries it per
 *    entity (`server/ledger_trace_router.py:735`~`:737`), ABSENT rather than empty when a type
 *    declares none — so a type without attributes still draws the table it drew before. This
 *    paragraph said the opposite until today: it was true when written and the server caught up,
 *    which is why the slot was built before anything could fill it.
 */
export function tableColumns(entities, type, qualifierNames) {
  const bare = bareName(type);
  const found = (entities || []).find((e) => e && bareName(e.type) === bare);
  const declared = (found && found.keys) || [];
  const attributes = (found && found.attributes) || [];
  return [
    { name: '깊이', kind: 'depth' },
    ...declared.map((key) => ({ name: key, kind: 'key', key })),
    ...(qualifierNames || []).map((key) => ({ name: key, kind: 'qualifier', key })),
    ...attributes.map((key) => ({ name: key, kind: 'attribute', key })),
    // 🔴 THE DISAGREEMENT COLUMN EXISTS WHEN ATTRIBUTES ARE DECLARED, NOT WHEN ONE IS FOUND.
    //    A header that appears only once some node disagrees would make the table's shape a
    //    function of the answer, so the same walk would draw two different tables; and an
    //    operator who never sees the column cannot learn that the question is being asked.
    //    A type declaring no attributes gets no column at all, which keeps today's table
    //    byte-identical.
    ...(attributes.length ? [{ name: '충돌', kind: 'conflicts' }] : []),
    { name: '라벨', kind: 'label' },
    { name: 'id', kind: 'id' },
  ];
}

/**
 * The raw value one column reads for one node — the other half of the same decision.
 *
 * 🔴 IT LIVES HERE, NOT IN THE RENDERER, because this is the mapping the arithmetic used to get
 *    wrong and a mapping nobody can import is a mapping no mutant can redden. The renderer is
 *    left with one loop over `tableColumns`, used for the header and the cells alike, so the
 *    order is stated exactly once.
 * ⚠️ Raw, not text. Turning `undefined` into 「」 is the caller's job, and doing it here would
 *    hide 「the walk never reached this」 behind a string this function invented.
 */
export function cellSource(column, node, qualifiers) {
  const n = node || {};
  switch (column && column.kind) {
    case 'depth': return n.depth;
    case 'key': return (n.keys || {})[column.key];
    case 'qualifier': return (qualifiers || {})[column.key];
    case 'attribute': return (n.attributes || {})[column.key];
    // 🔴 ONLY A DISAGREEMENT IS AN ANSWER HERE, and that is a reading rule rather than a
    //    display one. The server sends three states — no key (the walk reached no
    //    registration), 0 (it read them and they agree), and N (N names hold differing
    //    values). The first two have nothing to say, and drawing 0 would put a number in
    //    front of an operator that means 「nothing is wrong」, which is the sentence this
    //    column exists to avoid making.
    // ⚠️ The two silent states are still told apart ONE COLUMN TO THE LEFT: a node the walk
    //    reached has its attribute cells filled and a node it did not has them empty. So the
    //    row keeps 「없음」 and 「안 닿음」 apart even though this cell cannot.
    case 'conflicts': {
      const count = Number(n.attribute_conflicts);
      return Number.isFinite(count) && count > 0 ? count : undefined;
    }
    case 'label': return n.label;
    case 'id': return n.id;
    default: return undefined;
  }
}

/**
 * 「잘렸다」 옆에 「«얼마»에서」를 붙인다.
 *
 * 🔴 S-13. 화면은 `truncated` 를 읽어 「절단됨」을 «말할 수» 있었지만 `limits` 를 안 읽어
 *    「무슨 예산에서」를 «못 말했습니다» (실측 2026-09-07: `limits` 독자 소스 0 · 번들 0).
 *    그 둘이 붙어야 운영자가 「더 넓혀 다시 물을지」를 정할 수 있습니다 — 축 이름만으로는
 *    「많아서 잘렸다」와 「상한이 낮아서 잘렸다」가 같아 보입니다.
 * 🔴 `depth` 의 예산은 `max_hops` 입니다 — 이름이 «다릅니다». 그대로 `limits.depth` 를 찾으면
 *    «언제나 없음»이 되고, 그러면 이 줄이 조용히 축 이름만 그리던 때로 돌아갑니다.
 * ⚠️ 상한을 «모르면 축만» 씁니다. 「0」이나 「모름」을 지어내지 않습니다 — 옛 서버는 `limits`
 *    를 안 보낼 수 있고, 없는 예산을 그리면 그것이 «틀린 수»입니다.
 *
 * @param {string[]|null} axes    잘린 축 이름 (`truncationAxes` 의 답)
 * @param {object|null} limits    응답의 `limits`
 * @returns {string[]} 축마다 한 조각 — 「nodes 400」 또는 상한을 모르면 「nodes」
 */
export function cutBudgets(axes, limits) {
  const caps = limits && typeof limits === 'object' ? limits : {};
  return (axes || []).map((axis) => {
    const cap = axis === 'depth' ? caps.max_hops : caps[axis];
    return Number.isFinite(cap) ? `${axis} ${cap}` : String(axis);
  });
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
