// Reading the skeleton — the document that says what a ledger config is made of.
//
// 🔴 THIS FILE KNOWS NO SECTION NAMES. Not `packs`, not `claims`, not `emit`. The owner's
// rule for the whole round is 「폼은 스켈레톤에서 목적 객체 형태 받아」 and his standing
// definition of done for it is 「다른 스키마 운영 환경에서 코드 0줄, 선언 교체만으로 발화」 --
// so the moment anything here asks WHICH declaration it is looking at, the next schema needs
// code again and the document has become a config-shaped hardcode. Add a field to the
// skeleton and the form offers it; remove it and the form stops. That is the whole contract.
//
// The document is served on `/authoring/schema` beside the closed lists, and the server
// checks it against the validator's own field tuples in both directions -- see
// `server/tests/test_ledger_skeleton.py`, which prints both counts and requires 0.
//
// Three node kinds and no fourth:
//   record  fixed field names        { fields: [ { key, required, when?, node } ] }
//   map     members named elsewhere  { keyed_by: 'name' | 'index', member, of }
//   leaf    a value                  { hint: free | ref | role | choice | flag }
// plus `{ use: '<name>' }`, which is not a fourth kind but a name for one of the three --
// a binding holds bindings under its identity keys, and a document that cannot say so
// would have to stop one level in and call that the grammar.

/** Follow `{use}` until a real node. */
function deref(node, defs) {
  let cursor = node;
  const seen = new Set();
  while (cursor && typeof cursor === 'object' && typeof cursor.use === 'string') {
    if (seen.has(cursor.use)) return null;      // a def that names itself, not a shape
    seen.add(cursor.use);
    cursor = (defs || {})[cursor.use];
  }
  return cursor || null;
}

/** The node describing the value at `steps`, walking from `node`. */
export function shapeAt(node, steps, defs) {
  let cursor = deref(node, defs);
  for (const step of steps) {
    if (!cursor) return null;
    if (cursor.kind === 'record') {
      const field = (cursor.fields || []).find((item) => item.key === String(step));
      cursor = field ? deref(field.node, defs) : null;
      continue;
    }
    if (cursor.kind === 'map') {
      // Every member of a map has the same shape; which one this is does not matter.
      cursor = deref(cursor.of, defs);
      continue;
    }
    return null;                                 // a leaf has nothing under it
  }
  return cursor;
}

/** The node for one declaration of `section`, i.e. what a member of that section is. */
export function declarationShape(skeleton, section) {
  if (!skeleton || !skeleton.root) return null;
  return shapeAt(skeleton.root, [section, '*'], skeleton.defs);
}

/** The field record for `key` inside a record node, or null. */
export function fieldOf(node, key) {
  if (!node || node.kind !== 'record') return null;
  return (node.fields || []).find((item) => item.key === String(key)) || null;
}

/** Is this field shown right now? `when` gates a field on a sibling's value.
 *
 *  🔴 A GATED FIELD IS STILL SHOWN WHEN THE DOCUMENT HOLDS ONE. Hiding a control takes
 *  somebody's data off the screen while leaving it in the file, which is the failure this
 *  screen keeps removing -- an absence that is really a value nobody can see.
 */
export function fieldApplies(field, siblings, held) {
  if (!field || !field.when) return true;
  if (held !== undefined) return true;
  const actual = siblings && typeof siblings === 'object'
    ? siblings[field.when.field] : undefined;
  return actual === field.when.is;
}

/** The emptiest value of this node's kind -- what a newly named member starts as. */
export function emptyOf(node, defs, depth = 0) {
  const shape = deref(node, defs);
  if (!shape) return '';
  if (shape.kind === 'map') return shape.keyed_by === 'index' ? [] : {};
  if (shape.kind === 'record') {
    // 🔴 A REQUIRED CONTAINER IS THERE FROM THE START, NOT WHEN SOMEBODY FILLS IT. Same
    // rule the server seeds a new declaration with (`empty_declaration`), applied to a
    // member added later: a claim added to a pack needs its own required containers, or the
    // person who wants none of something has no way to say so.
    //
    // Containers only. A required LEAF stays absent on purpose -- absent reads as
    // `missing_field`, which asks the operator to fill it, while a seeded `''` would look
    // like a value they chose. And no field is known by name: the skeleton is asked whether
    // it is required and whether it is a container.
    if (depth > 6) return {};                     // a def that holds its own kind, bounded
    const seeded = {};
    for (const field of shape.fields || []) {
      if (field.required !== true) continue;
      const child = deref(field.node, defs);
      if (!child || child.kind === 'leaf') continue;
      seeded[field.key] = emptyOf(field.node, defs, depth + 1);
    }
    return seeded;
  }
  return shape.hint === 'flag' ? false : '';
}

/** `a.b` + a member -> the path the server would spell, brackets and all.
 *
 *  Index-keyed members are `mappings[0]`, not `mappings.0`: that is how the authoring plan
 *  spells them (measured -- 69 of 123 live authoring paths are bracketed), and a form that
 *  spelled them the other way would look up every one of those rows and find nothing.
 */
export function memberPath(path, key, keyedBy) {
  return keyedBy === 'index' ? `${path}[${key}]` : `${path}.${key}`;
}

/** The members a map currently holds, in the order they should be drawn. */
export function membersOf(node, value) {
  if (!node || node.kind !== 'map') return [];
  if (node.keyed_by === 'index') {
    return Array.isArray(value) ? value.map((_, index) => index) : [];
  }
  return value && typeof value === 'object' && !Array.isArray(value)
    ? Object.keys(value) : [];
}
