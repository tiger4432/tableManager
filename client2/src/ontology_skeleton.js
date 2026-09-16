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
// Four node kinds and no fifth:
//   record  fixed field names        { fields: [ { key, required, when?, node } ] }
//   map     members named elsewhere  { keyed_by: 'name' | 'index', member, of }
//   oneOf   one shape out of several { hint: 'choice', branches: { <value>: node } }
//   leaf    a value                  { hint: free | ref | role | choice | flag }
// plus `{ use: '<name>' }`, which is not a fifth kind but a name for one of the four --
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

/** The node one step under `node` -- by field key, by member, or by branch key. Null under a
 *  leaf, and null for a key the node does not hold.
 *
 *  🔴 DESCENT HAS ONE AUTHOR (C-115). `shapeAt` walks steps and `emptyOf` seeds children, and
 *  each used to spell record-and-map descent for itself -- so when `oneOf` joined the
 *  vocabulary, a oneOf nested under a oneOf was invisible to both while every caller happened
 *  to hand them a node already picked. Spelled here once, the next node kind is one branch in
 *  one place, not one per reader.
 *
 *  A oneOf is descended BY BRANCH KEY, because that is where the branch node lives (ruling
 *  411: for a oneOf at P, the picked value V's node is the shape at P.V -- `derive.join` is a
 *  record and `into.table` is a leaf, and the key is already the cell).
 */
function childOf(node, step, defs) {
  if (!node) return null;
  if (node.kind === 'record') {
    const field = (node.fields || []).find((item) => item.key === String(step));
    return field ? deref(field.node, defs) : null;
  }
  // Every member of a map has the same shape; which one this is does not matter.
  if (node.kind === 'map') return deref(node.of, defs);
  if (node.kind === 'oneOf') {
    const branches = node.branches && typeof node.branches === 'object' ? node.branches : {};
    const branch = branches[String(step)];
    return branch ? deref(branch, defs) : null;
  }
  return null;                                   // a leaf has nothing under it
}

/** The node describing the value at `steps`, walking from `node`. */
export function shapeAt(node, steps, defs) {
  let cursor = deref(node, defs);
  for (const step of steps) {
    if (!cursor) return null;
    cursor = childOf(cursor, step, defs);
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
  // 🔴 ONE LEGAL VALUE IS NOT A DECISION — IT IS A SEED. `const` says the grammar admits exactly
  // one value here, so a newly named member is BORN with it. Before this the client fell through
  // to the tail below, and for a `const: true` flag that meant seeding `false` — the one value
  // the bundle validator refuses. The form produced a member that could not be saved, and the
  // operator had to find the box and tick it. 「가드는 도달 가능해지는 날 틀린다」 in its seeding
  // form: `hint: flag` was read correctly and the answer was still wrong.
  //
  // ⛔ NO DOMAIN WORD HERE. The server's twin reads the same key rather than naming the field
  // (`config_authoring.empty_value`: 「THE SEED IS NOT HARDCODED … The SKELETON says what the one
  // legal value is」), so the next `const` leaf costs zero edits instead of one on each side.
  // This is the CLIENT half: the form builds a new member without a server round trip, so the
  // server fix alone left the screen producing the refused value.
  //
  // ⚠️ IT STAMPS A DEFAULT, NOT A LOCK. Somebody who clears it deliberately still meets the
  // validator by name, with its repairs — an informed refusal of a deliberate act, not a trap
  // sprung on a default. Drawing a `const` leaf as SETTLED rather than as a live checkbox is the
  // other half of that and is a separate round.
  if (Object.prototype.hasOwnProperty.call(shape, 'const')) return shape.const;
  if (shape.kind === 'map') return shape.keyed_by === 'index' ? [] : {};
  // 🔴 A oneOf STARTS AS 「NOTHING PICKED」, AND THAT IS AN OBJECT HOLDING NO BRANCH KEY. The
  // renderer draws the picker blank and no branch for any value that names none (it
  // normalises a non-object to `{}`, then reads `kind`, then a held branch key -- the
  // loader's order), and the loader folds `''` and `{}` alike into kind "unknown". Of the
  // two, `{}` is the one the grammar spells: a oneOf's value is a mapping with the branch
  // under its key, so an unpicked one is that mapping with no key yet. Before this, a
  // required oneOf fell through to the leaf tail below and was seeded `''` -- a string where
  // a mapping belongs, drawn the same and loaded the same only while both sides stay lenient.
  if (shape.kind === 'oneOf') return {};
  if (shape.kind === 'record') {
    // 🔴 A REQUIRED CONTAINER IS THERE FROM THE START, NOT WHEN SOMEBODY FILLS IT. Same
    // rule the server seeds a new declaration with (`empty_declaration`), applied to a
    // member added later: a claim added to a pack needs its own required containers, or the
    // person who wants none of something has no way to say so.
    //
    // Containers, and the one leaf whose control cannot DRAW its own absence. A required
    // text or choice leaf stays absent on purpose -- absent reads as `missing_field`, which
    // asks the operator to fill it, while a seeded `''` would look like a value they chose,
    // and the screen can show that difference: an empty box and a blank select both look
    // unanswered.
    //
    // 🔴 A CHECKBOX HAS NO BLANK. `hint: flag` is drawn `checked = value === true`, so
    // `undefined` and `false` are PIXEL-IDENTICAL -- the operator reads "answered, false",
    // saves, and gets `invalid_type` + `missing_field` on a field the screen showed as
    // settled. The seeded `false` is not a guess about what they meant; it is the value the
    // screen was ALREADY showing them, so the file stops disagreeing with the pixels.
    //
    // The class, not the case: three fields of the skeleton are required flags today, and
    // the HINT is read, so a fourth is covered the day it is declared. `allow_null` is
    // `required: false` and stays absent -- seeding what is not required is the complaint
    // below, coming straight back.
    //
    // 🔴 REQUIRED IS NOT UNCONDITIONAL: `when` SAYS WHO IT IS REQUIRED OF. Four fields of
    // `defs.binding` are `required: true` behind a gate on `kind` -- and a brand-new binding
    // has no `kind` yet, so none of them is required OF IT. Seeding the one that happens to
    // be a container gave every new binding a `keys: {}` its own kind forbids, which the
    // form cannot take out again because the control that removes a field is the one drawn
    // for `required: false`.
    //
    // The gate is ASKED through `fieldApplies` -- the same predicate the renderer decides
    // with, so what a new member holds and what it shows can no longer disagree -- and never
    // by a list of kinds here, which would be a second author for the skeleton and would go
    // stale in silence. An UNGATED required container still lands exactly as before, which
    // is the complaint this seeding exists for.
    if (depth > 6) return {};                     // a def that holds its own kind, bounded
    const seeded = {};
    for (const field of shape.fields || []) {
      if (field.required !== true) continue;
      if (!fieldApplies(field, seeded)) continue;
      const child = childOf(shape, field.key, defs);
      if (!child) continue;
      if (child.kind === 'leaf' && child.hint !== 'flag') continue;
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
