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
  const next = JSON.parse(JSON.stringify(document));
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
