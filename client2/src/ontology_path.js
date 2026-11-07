// Bundle paths, mirrored from the server so both sides decompose them the same way.
//
// 🔴 THIS IS A MIRROR, NOT A DESIGN. The rule lives in `server/ledger/config_authoring.py`
// (`_PATH_STEP` / `_split_path`) and the write it feeds lives in `config_drafts.py`
// (`_set_path`). Inventing a second rule here would let the screen and the file disagree
// about which leaf a field names -- and 69 of the 123 authoring fields on the live config
// sit behind bracket notation, so a naive dot-split would have been silently wrong on more
// than half of them. Keep this file matching its source; the seam is checked by feeding the
// live config's real paths to both and comparing -- 164 paths, 89 of them bracketed,
// 0 mismatches on 2026-08-19. That was a one-off check, not a standing harness.
//
// 🔴 AND IT INHERITS THE SOURCE'S ONE LIMITATION, deliberately. Splitting on `.` assumes no
// declaration or claim id contains a dot. That holds on the live config today -- measured,
// zero dotted ids -- and it is NOT a guarantee: the day someone names a declaration
// `v1.2@1`, this and the server both mis-split it, in the same way. Same answer on both
// sides is the property being kept here; being right about dotted ids is a separate fix and
// belongs in the server first.

import { asList, emptyOf, valueFits, shapeAt } from './ontology_skeleton.js';

const PATH_STEP = /([^.[\]]+)|\[(\d+)\]/g;

/** `bundle.a.b[0].c` -> `['a', 'b', 0, 'c']` (the leading `bundle.` is dropped). */
export function splitBundlePath(path) {
  const steps = [];
  const rest = String(path == null ? '' : path).replace(/^bundle\./, '');
  for (const match of rest.matchAll(PATH_STEP)) {
    steps.push(match[1] === undefined ? Number(match[2]) : match[1]);
  }
  return steps;
}

/** Set the leaf at `steps` inside a parsed draft, returning a NEW document.
 *
 *  Returns `null` when the path does not resolve, rather than building the missing
 *  branch: an authoring field names a leaf the declaration already has a place for, so a
 *  path that does not resolve means this field belongs to something else -- and inventing
 *  the branch would write a shape the validator never asked for.
 */
export function setAtPath(document, steps, value) {
  if (!steps.length) return null;
  const next = JSON.parse(JSON.stringify(document));
  let cursor = next;
  for (const step of steps.slice(0, -1)) {
    if (cursor === null || typeof cursor !== 'object') return null;
    if (typeof step === 'number' ? !Array.isArray(cursor) : Array.isArray(cursor)) return null;
    if (!(step in cursor)) return null;
    cursor = cursor[step];
  }
  const leaf = steps[steps.length - 1];
  if (cursor === null || typeof cursor !== 'object') return null;
  if (typeof leaf === 'number' ? !Array.isArray(cursor) : Array.isArray(cursor)) return null;
  cursor[leaf] = value;
  return next;
}

/**
 * Form D (lead f3639d4a2): a leaf that gates its siblings (`when: {field, is}`) was written - `before` -> `after`. The
 * fields its new value shuts leave the record into `stash`, under the branch they belong to; the fields it opens come
 * back from it. The document holds only the branch picked; the stash is the screen's, so going back restores what was
 * typed there. Nothing else moves: a leaf no field is gated on returns `after` and `stash` as they are.
 * @returns {{document: object, stash: object}}
 */
export function switchGated(before, after, relative, root, defs, stash = {}) {
  const steps = splitBundlePath(relative);
  const key = steps[steps.length - 1];
  const parent = shapeAt(root, steps.slice(0, -1), defs);
  const gated = parent && parent.kind === 'record'
    ? (parent.fields || []).filter((field) => field.when && field.when.field === key) : [];
  const now = getAtPath(after, steps);
  if (!gated.length || getAtPath(before, steps) === now) return { document: after, stash };
  const document = JSON.parse(JSON.stringify(after));
  const record = getAtPath(document, steps.slice(0, -1));
  if (!record || typeof record !== 'object' || Array.isArray(record)) return { document: after, stash };
  const kept = { ...stash };
  for (const field of gated) {
    const at = `${relative}=${JSON.stringify(field.when.is)}:${field.key}`;
    if (field.when.is === now) {
      if (record[field.key] === undefined && kept[at] !== undefined) record[field.key] = kept[at];
      delete kept[at];
    } else if (record[field.key] !== undefined) {
      kept[at] = record[field.key];
      delete record[field.key];
    }
  }
  return { document, stash: kept };
}

/**
 * 폼 컨트롤 하나가 «리프 하나»를 쓴 결과의 새 문서. 못 쓰면 `null`.
 *
 * 🔴 ONE WRITER, BECAUSE THE RULES ARE NOT OBVIOUS AND THERE ARE NOW TWO FORMS (C-86). The
 * explorer's declaration form and the chain rule form both draw from a skeleton, and both
 * have to answer the same three questions the same way. A second copy of these rules would
 * not throw -- it would quietly write a different document.
 *
 * 🔴 THE FORM'S OWN BRANCHES ARE BUILT, because the form is what promised them. `setAtPath`
 * refuses a missing parent on purpose -- an authoring-plan row names a leaf the declaration
 * already has a place for. But a form offers `emit.object.kind` on a claim whose `emit` does
 * not exist yet, and a field that silently does nothing is a refusing control.
 *
 * 🔴 A LIST SLOT IS NEVER INVENTED, but what lives inside one still gets built: a missing
 * INDEX is a member nobody added, and inventing it would put an empty slot in somebody's list.
 *
 * 🔴 THE UI NEVER ASSERTS A TYPE. Whatever type is already at that leaf is preserved, and a
 * value typed into an empty leaf goes in as typed. If that is wrong the validator says so on
 * the screen, and showing beats blocking.
 */
export function writeShapeAtPath(document, relative, value) {
  const steps = splitBundlePath(relative);
  if (!steps.length) return null;
  let raw = liftLoneValues(document, steps);
  for (let depth = 1; depth < steps.length; depth += 1) {
    const branch = steps.slice(0, depth);
    if (getAtPath(raw, branch) !== undefined) continue;
    if (typeof branch[branch.length - 1] === 'number') break;
    const built = setAtPath(raw, branch, {});
    if (built === null) break;
    raw = built;
  }
  const current = getAtPath(raw, steps);
  let written = value;
  if (typeof current === 'number' && typeof value === 'string') {
    const asNumber = Number(value.trim());
    if (value.trim() !== '' && Number.isFinite(asNumber)) written = asNumber;
  }
  return setAtPath(raw, steps, written);
}

// `class[0]` on a file holding `"class": "Lot"`: the form drew that word as a one-item list
// (`asList`), so an index step landing on a single value lifts it into its list first. The
// file keeps the word until somebody edits the list; from then on it holds the list.
function liftLoneValues(document, steps) {
  let next = document;
  for (let depth = 1; depth < steps.length; depth += 1) {
    if (typeof steps[depth] !== 'number') continue;
    const held = getAtPath(next, steps.slice(0, depth));
    if (held === undefined || held === null || held === '' || typeof held === 'object') continue;
    next = setAtPath(next, steps.slice(0, depth), [held]) || next;
  }
  return next;
}

/** Read the leaf at `steps`, or `undefined` when the path does not resolve. */
export function getAtPath(document, steps) {
  let cursor = document;
  for (const step of steps) {
    if (cursor === null || typeof cursor !== 'object') return undefined;
    if (typeof step === 'number' ? !Array.isArray(cursor) : Array.isArray(cursor)) return undefined;
    if (!(step in cursor)) return undefined;
    cursor = cursor[step];
  }
  return cursor;
}

/** Remove the leaf at `steps`, returning a NEW document (or `null` if it is not there).
 *
 *  A member of a list is spliced out rather than left as a hole: `mappings[1]` gone means
 *  the list is one shorter, not that it holds an `undefined` the validator would read as
 *  a mapping with no fields.
 */
export function deleteAtPath(document, steps) {
  if (!steps.length) return null;
  const next = JSON.parse(JSON.stringify(liftLoneValues(document, steps)));
  let cursor = next;
  for (const step of steps.slice(0, -1)) {
    if (cursor === null || typeof cursor !== 'object') return null;
    if (!(step in cursor)) return null;
    cursor = cursor[step];
  }
  const leaf = steps[steps.length - 1];
  if (cursor === null || typeof cursor !== 'object') return null;
  if (Array.isArray(cursor)) {
    if (typeof leaf !== 'number' || leaf < 0 || leaf >= cursor.length) return null;
    cursor.splice(leaf, 1);
    return next;
  }
  if (!(leaf in cursor)) return null;
  delete cursor[leaf];
  return next;
}

/** One new member of the map at `relative` -- the document back with it, plus where it was born.
 *
 *  🔴 ONE AUTHOR FOR BOTH SCREENS. The ledger explorer and the chain panel draw the same `+`
 *  from the same renderer, and only the explorer had anything behind it: on the chain panel the
 *  button did nothing at all (09-24, found before the list skeleton landed). Both now call this.
 *  Removing a member is `deleteAtPath` -- it already splices -- so there is nothing to share there.
 *
 *  🔴 IT REFUSES TO WRITE OVER A VALUE THAT IS NOT THE MAP'S SHAPE. The explorer's `+` used to
 *  replace a string held at a list (`"on": "lot_event"`) with `[<empty member>]`, deleting what
 *  the file said without showing it. The rule is the renderer's own (`valueFits`), so the screen
 *  and the writer cannot disagree about which value is in the way.
 *
 *  Index map: appended, born at `path[n]`. Name map: `name` is required; born at `path.name`.
 *  Returns null when nothing may be written, the same as the other writers here.
 */
export function addMember(document, relative, node, defs, name = '', lists = null) {
  if (!node || node.kind !== 'map') return null;
  const held = asList(node, getAtPath(document, splitBundlePath(relative)));
  if (!valueFits(node, held)) return null;
  const seed = emptyOf(node.of, defs, 0, lists);
  if (node.keyed_by === 'index') {
    const list = Array.isArray(held) ? held : [];
    // Form D: a list of words takes what was typed at its adder - split on commas, line breaks and tabs (a paste of a
    // column of names) - each a member; nothing typed appends one empty member, as before.
    const item = shapeAt(node, ['0'], defs);
    const words = item && item.kind === 'leaf' ? String(name || '').split(/[,\n\t]/).map((w) => w.trim()).filter(Boolean) : [];
    const added = words.length
      ? words.map((w) => (item.hint === 'number' && Number.isFinite(Number(w)) ? Number(w) : w)) : [seed];
    const written = writeShapeAtPath(document, relative, [...list, ...added]);
    return written === null ? null
      : { document: written, born: `${relative}[${list.length + added.length - 1}]`, seed: added[added.length - 1] };
  }
  const key = String(name || '').trim();
  if (!key) return null;
  const born = `${relative}.${key}`;
  const written = writeShapeAtPath(document, born, seed);
  return written === null ? null : { document: written, born, seed };
}
