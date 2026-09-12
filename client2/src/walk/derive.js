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
 * WHICH TABLE IS ASKING — and it is a WIDTH, not a second author.
 *
 * 🔴 `FOR_PICKING` carries its own reason in its name: that list is PICKED FROM, not read. The
 *    walk box runs a walk and you click a row to mark it; depth, qualifiers, attributes and the
 *    long id are for the page you read, and putting them in a picking list buys nothing.
 * 🔴 What it must NOT do is decide the columns itself. It named `label · type · id` in its own
 *    source until 2026-09-10, and the two walk tables were then free to drift apart with no
 *    error to say so — a declared key reached one screen and not the other (기준 ④).
 */
export const COLUMNS = Object.freeze({ FULL: 'full', FOR_PICKING: 'for_picking' });

/**
 * 타입별 구획 — 「처음 나온 순서」로. 서버가 실어 온 순서가 답의 일부이므로 정렬하지 않는다.
 *
 * 🔴 두 걷기 표가 «이 함수 하나»를 부른다. 걷기 결과는 «한 타입이 아니고»(collect 를 안 실으면
 *    서버 기본값이 「닿은 것 전부」다) 타입마다 선언된 키가 다르므로, 구획이 없으면 컬럼을
 *    선언에서 가져올 자리 자체가 없다. 그래서 이것과 `tableColumns` 는 «한 짝»이다.
 */
export function sectionsByType(nodes) {
  const sections = new Map();
  for (const node of nodes || []) {
    const type = (node && node.type) || '';
    if (!sections.has(type)) sections.set(type, []);
    sections.get(type).push(node);
  }
  return sections;
}

/** 구획 머리 «한 줄» — 타입과 수. 문장이 아니다(설명 문구 금지 상설). */
export function sectionHeading(type, count) {
  return `${type || '타입 없음'} · ${count}`;
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
/**
 * 선언이 말하는 그 타입의 «식별 키», 선언된 순서 그대로. 없으면 빈 목록.
 *
 * 🔴 C-92. 이 물음의 독자를 «하나»로 둡니다. 보드의 구성 모델이 다이의 id 를 지을 때 같은 답이
 *    필요한데, 거기서 키 이름을 «적으면»(`keys.mat_id`) 선언이 바뀌어도 그 화면만 안 따라옵니다.
 */
export function declaredKeys(entities, type) {
  const bare = bareName(type);
  const found = (entities || []).find((e) => e && bareName(e.type) === bare);
  return (found && found.keys) || [];
}

export function tableColumns(entities, type, qualifierNames, preset = COLUMNS.FULL) {
  const bare = bareName(type);
  const found = (entities || []).find((e) => e && bareName(e.type) === bare);
  const declared = declaredKeys(entities, type);
  const attributes = (found && found.attributes) || [];
  const identity = declared.map((key) => ({ name: key, kind: 'key', key }));
  // 🔴 THE PRESET CHOOSES THE WIDTH. IT NEVER CHOOSES THE AUTHOR. Both presets read the same
  //    declaration for the same type, so a key added to the declaration reaches BOTH screens
  //    with no edit — which is the whole reason the narrow list stopped naming its own three.
  if (preset === COLUMNS.FOR_PICKING) return [...identity, { name: '라벨', kind: 'label' }];
  return [
    { name: '깊이', kind: 'depth' },
    ...identity,
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
/**
 * 봉투가 「이 타입의 이 이름은 «여럿»」이라고 «말한» 것 -> `Map<타입, Set<이름>>`.
 *
 * 🔴 선언이 답합니다, 값의 «모양»이 아니라 (S-144, 판정 327). 서버는 `many` 이름을 «언제나»
 *    리스트로 내지만 — 값이 하나여도 — `one` 이름의 값이 «우연히» 배열일 수도 있습니다(원장에
 *    JSON 목록이 들어 있는 칸). 모양으로 고르면 그 칸을 「등록이 여럿」으로 그리게 되고, 그건
 *    아무도 안 한 주장입니다. 「대리를 성질로 읽지 않는다」.
 * ⚠️ 칸이 «없는» 봉투(옛 서버, 또는 many 이름이 하나도 없는 걷기)는 빈 Map 입니다 — 「없다」와
 *    「안 물었다」가 그리기에서는 같은 답이라 여기서 갈라 두지 않습니다. 그 구별이 필요해지는
 *    자리가 생기면 그때 봉투의 키 유무로 갈립니다.
 */
export function pluralAttributes(answer) {
  const out = new Map();
  const declared = answer && answer.attribute_cardinality;
  if (!declared || typeof declared !== 'object') return out;
  for (const type of Object.keys(declared)) {
    const names = declared[type];
    if (!names || typeof names !== 'object') continue;
    const many = new Set(Object.keys(names).filter((name) => names[name] === ATTRIBUTE_MANY));
    if (many.size) out.set(String(type), many);
  }
  return out;
}

/** 서버의 낱말. 화면이 다시 적지 않습니다. */
export const ATTRIBUTE_MANY = 'many';

export function cellSource(column, node, qualifiers, plural) {
  const n = node || {};
  switch (column && column.kind) {
    case 'depth': return n.depth;
    case 'key': return (n.keys || {})[column.key];
    case 'qualifier': return (qualifiers || {})[column.key];
    // 🔴 C-89. 선언이 «여럿»이라 부른 이름은 «목록»입니다 — 값이 하나여도 리스트로 옵니다
    //    (서버가 이름당 모양을 «고정»합니다: 「둘일 때만 리스트」면 한 칸에 두 모양이 됩니다).
    //    그리는 쪽이 `String(['a','b'])` 로 이어 붙이면 `a,b` 가 되는데, 이 제품에서 목록의
    //    철자는 「·」입니다. 그 판단이 여기 «한 자리»에 있는 이유는 표가 «둘»이기 때문입니다.
    // ⚠️ 선언이 말한 이름이 아니면 손대지 않습니다. 그리고 리스트가 «아닌» 값이 오면 그대로
    //    둡니다 — 옛 서버가 스칼라를 낼 수 있고, 그때 이어 붙일 것이 없습니다.
    case 'attribute': {
      const held = (n.attributes || {})[column.key];
      return (plural && plural.has(column.key) && Array.isArray(held))
        ? held.join(' · ') : held;
    }
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
