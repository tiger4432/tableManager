/**
 * TWO-REVISION SIGNATURE DRIFT — the shared adapter for probes that compare a pinned baseline
 * blob against the working tree.
 *
 * WHY THIS EXISTS. `valid_die_head_parity_oracle.mjs` and `copy_header_count_harness.mjs` each
 * slice TWO revisions of `client2/src/map_editor.js` — a baseline pinned by SHA, plus the
 * working tree — and run both through ONE shared probe. Both already absorb a RENAME: each
 * carries a list of accepted spellings, takes whichever one the revision actually has, and
 * binds an alias so the probe names the function one way.
 *
 * A SIGNATURE change is the same class of event and those spelling lists cannot express it.
 * The frame-as-argument refactor gives one function after another a new leading `frame`
 * parameter, so the baseline takes `(…)` and the working tree takes `(frame, …)`. Neither
 * revision is wrong; they spell the call differently. That is resolved here, at the slicing
 * boundary — never by advancing a pinned baseline, which would make the oracle compare the new
 * code against itself and report green having compared nothing.
 *
 * 🔴 WHY `null` AND NOT AN OMITTED ARGUMENT. Under the refactor's contract `null` means "no
 *    frame — read the screen controls", and `undefined` means "the caller forgot" and throws.
 *    Reading the screen unconditionally is exactly and only what the baseline revision did.
 *    So passing `null` is what asks the OLD signature and the NEW signature the SAME question,
 *    and a two-revision comparison is meaningful only while both sides face the same question.
 *    Do not "simplify" this to dropping the argument: the new signature would then throw, and
 *    do not pass a real frame: the two revisions would be answering different questions and
 *    the parity result would mean nothing at all.
 *
 * 🔴 WHY `>=` AND NOT `===`. A later stage of this refactor may add a further argument. With
 *    `===` the working tree would silently fall back to the legacy branch and be called with
 *    the wrong shape — the failure would look like a code defect rather than an adapter that
 *    stopped applying. `>=` fails loudly instead of drifting quietly.
 *
 * 🔴 ARITY IS READ OFF THE FUNCTION, never inferred from which revision we believe we hold.
 *    The entire value of these probes is that they do not get to assume what the two sides
 *    contain, and an adapter that assumed would give that away.
 *
 * NOT A HARNESS. This file lives under `client2/tests/oracle/` because `check_harnesses.mjs`
 * scans `client2/tests/` for FILES only and does not recurse, so modules here are imported
 * rather than executed as harnesses. Do not put a harness in this directory — it would be
 * silently undiscovered, which is the failure mode that runner exists to prevent.
 */

/** The single decision both shapes below are built on. */
export function takesFrameFirst(fn, legacyArity) {
  if (typeof fn !== 'function') {
    throw new Error(`revision_signature_drift: expected a function, got ${typeof fn}. `
      + 'The probe sliced something that is not callable — that is a slicing failure, '
      + 'not a signature question, and must not be adapted away.');
  }
  if (!Number.isInteger(legacyArity) || legacyArity < 0) {
    throw new Error(`revision_signature_drift: legacyArity must be a non-negative integer, `
      + `got ${legacyArity}.`);
  }
  return fn.length >= legacyArity + 1;
}

/**
 * Host-side shape: wrap a function object so the probe can call it with the LEGACY argument
 * list regardless of which revision produced it.
 *   `const pc = frameAdapted(H.getTransformedPhysicalConfig, 2)(rot, side);`
 */
export function frameAdapted(fn, legacyArity) {
  return takesFrameFirst(fn, legacyArity)
    ? (...rest) => fn(null, ...rest)
    : (...rest) => fn(...rest);
}

/**
 * In-sandbox shape: source text that binds a stable alias INSIDE a `vm` context, for probes
 * whose hot loop runs in the sandbox and must not cross the host boundary per cell.
 * `fnExpr` is the name the revision actually shipped (post rename-resolution).
 */
export function frameAdaptedSource(alias, fnExpr, legacyArity) {
  if (!Number.isInteger(legacyArity) || legacyArity < 0) {
    throw new Error(`revision_signature_drift: legacyArity must be a non-negative integer, `
      + `got ${legacyArity}.`);
  }
  return `globalThis.${alias} = (${fnExpr}.length >= ${legacyArity + 1})\n`
    + `  ? ((...rest) => ${fnExpr}(null, ...rest))\n`
    + `  : ((...rest) => ${fnExpr}(...rest));`;
}
