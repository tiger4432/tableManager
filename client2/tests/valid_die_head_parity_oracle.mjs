// INV-1 acceptance test, measured against the BASELINE BLOB rather than restated.
// Run: node client2/tests/valid_die_head_parity_oracle.mjs [--base <git-rev>]
//
// The claim under test: "a map with no valid_die_ref behaves exactly as at <base>".
// Prose cannot carry that claim, and neither can a self-comparison. So this loads the
// baseline `map_editor.js` OUT OF GIT, loads the working copy, and compares the ONE thing
// that decides what the user sees and what Push writes - the per-cell `inside` verdict -
// cell by cell, across every rotation / side / geometry in the matrix.
//
// It also runs a NEGATIVE CONTROL: the same comparator, with a mask declared, MUST report
// a non-zero difference. A comparator that cannot tell two different answers apart proves
// nothing when it reports zero.
import { readFileSync, writeFileSync, mkdtempSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { tmpdir } from 'node:os';
import vm from 'node:vm';
import { frameAdaptedSource } from './oracle/revision_signature_drift.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = join(HERE, '..', '..');
const SRC_PATH = join(HERE, '..', 'src', 'map_editor.js');

// ── THE BASE IS A FIXED ACCEPTANCE ANCHOR, NOT `HEAD` ───────────────────────────
// 🔴 THE DEFAULT USED TO BE `HEAD`, AND THAT IS INVERTED: it made this oracle green only
//    on a DIRTY tree and dead on a clean checkout. Once a change to `map_editor.js` is
//    committed, `HEAD`'s blob IS the working copy, `baseSrc === workSrc` fires, and the run
//    dies having compared nothing. Measured 2026-08-05: commit `74ce8b1` landed an in-flight
//    `map_editor.js` and this oracle went from `ASSERTIONS 17498 0` to a hard die on the very
//    next run, with no line of `map_editor.js` differing from what had just passed.
// 🔴 THAT IS THE `ASSERTIONS 0 0` CLASS, and it is the same trap `map_spec_only_save_harness`
//    carries from the other side: a check that locates its subject by matching text (there, a
//    toast used as a slicer anchor; here, a git rev) stops comparing anything the moment the
//    text moves, and "nothing was compared" reads exactly like "nothing was wrong". The
//    `die()` on identical sources below is the guard against that, and it is CORRECT — the
//    defect was never the guard, it was choosing a base that makes vacuity the normal state.
// 🔴 SO THE BASE IS THE COMMIT WHERE INV-1 WAS ACCEPTED, and it does not move when HEAD does.
//    `4d973d6` (M4 phase 2, 2026-07-29) is the commit that introduced this oracle and the
//    claim it scores, so "unchanged since acceptance" is literally what the run now measures.
//    It is also the OLDEST anchor that still holds: parity was measured against every
//    map_editor.js commit from `4d973d6` forward on 2026-08-05 and every one gave 0 differing
//    cells, so the strongest available claim is the one taken. Anchoring nearer to HEAD would
//    have been weaker for no gain — it would only protect changes made after that point.
// ⚠️ WHEN THIS GOES RED, DO NOT RE-BASE IT TO SILENCE IT. Red means the no-declaration verdict
//    MOVED, which is the one thing INV-1 forbids. Re-base only after the new verdict has been
//    deliberately blessed, and say so in the commit — an anchor advanced to get a green build
//    turns this file back into the thing it was written to replace, a restated claim.
const ACCEPTANCE_BASE = '4d973d6';
const baseIdx = process.argv.indexOf('--base');
const BASE = baseIdx > 0 ? process.argv[baseIdx + 1] : ACCEPTANCE_BASE;

function die(msg) {
  console.error(`ORACLE FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  process.exit(2);
}

function sliceBalanced(src, startIdx) {
  let i = src.indexOf('{', startIdx);
  if (i < 0) return null;
  let depth = 0;
  for (let j = i; j < src.length; j++) {
    if (src[j] === '{') depth++;
    else if (src[j] === '}') { depth--; if (depth === 0) return src.slice(startIdx, j + 1); }
  }
  return null;
}

// The verdict path, exactly as `getGridCellObject` composes it:
//   isValidDieAt(die.x, die.y, isCellInsideWaferFast(...))
//
// 🔴 THIS ORACLE SLICES TWO DIFFERENT REVISIONS, so a single name list cannot address both:
//    the moment a function is renamed, the baseline blob still carries the old name and the
//    working copy carries the new one. That is not a defect in either revision — it is the
//    one place in this directory where a rename is legitimately NOT mechanical, and the fix
//    belongs here, at the slicing boundary, not in a score waiver.
//    An entry is therefore a list of ACCEPTED SPELLINGS, newest first. Each side takes the
//    first spelling it actually has; the probe below then calls a stable alias, so the two
//    sandboxes stay comparable without either revision being restated.
// ⚠️ Do NOT collapse this back to a single name once HEAD carries the new one. The list is
//    what lets this oracle keep working across the NEXT rename too, and an oracle that dies
//    on a rename gets waived rather than fixed.
const NEEDED = [
  ['physNum'], ['gridDimNum'], ['getScreenShift'],
  ['getTransformedPhysicalConfig'],
  ['getDieIndex', 'getPhysicalCoords'],          // renamed 2026-07-31
  ['isCellInsideWaferFast'], ['getWaferBoundingBox'], ['validDieBasis'], ['isValidDieAt'],
];
// The alias the probe calls, and the entry it resolves through.
const DIE_INDEX_ALIAS = '__dieIndexFn';

// [2026-08-05] THE SECOND KIND OF DRIFT THIS ORACLE HAS TO ABSORB, and the name list above
// cannot express it: a SIGNATURE change. One function after another is gaining a leading
// `frame` argument, so the baseline takes `(…)` and the working copy takes `(frame, …)`.
// Same class as the 2026-07-31 rename — neither revision is wrong, they spell the call
// differently — and resolved in the same place, at the slicing boundary.
//
// The rule, and above all WHY THE ADAPTER PASSES `null` RATHER THAN OMITTING THE ARGUMENT,
// live in `oracle/revision_signature_drift.mjs` — shared with `copy_header_count_harness.mjs`,
// which has exactly the same problem. Read it there; do not restate it here. Two copies of a
// rule is how the two sides of a comparison start answering different questions.
const PHYS_CONFIG_ALIAS = '__physConfigFn';
const VALID_DIE_ALIAS = '__validDieAtFn';

function buildVerdictFn(src, label) {
  const parts = [];
  const chosen = {};
  for (const aliases of NEEDED) {
    let hit = null;
    for (const name of aliases) {
      const m = new RegExp(`(?:async\\s+)?function\\s+${name}\\s*\\(`).exec(src);
      if (m) { hit = { name, index: m.index }; break; }
    }
    if (!hit) die(`none of [${aliases.join(', ')}] found in ${label}`);
    const out = sliceBalanced(src, hit.index);
    if (!out) die(`unbalanced braces for ${hit.name} in ${label}`);
    chosen[aliases[0]] = hit.name;
    parts.push(out);
  }
  const ctx = {
    console, currentRotation: 0, currentSide: 'front',
    // KEPT ON PURPOSE. The working copy no longer has this binding, but the PINNED BASELINE
    // still reads it -- that is the whole point of a two-revision oracle. Removing it from
    // the shared sandbox does not clean anything up; it kills the old side with a
    // ReferenceError and takes the comparison with it.
    physFrameOverride: null,
    validDie: null, boundingBoxCache: {}, el: {},
  };
  vm.createContext(ctx);
  try { vm.runInContext(parts.join('\n\n'), ctx); } catch (e) {
    die(`sandbox evaluation failed for ${label} - ${e && e.message ? e.message : e}`);
  }
  // Bind each alias to whichever spelling AND whichever signature this revision shipped.
  // The rename half is resolved by `chosen.*` above; the signature half is
  // `oracle/revision_signature_drift.mjs`, shared with `copy_header_count_harness.mjs` so the
  // rule — and the reason it passes `null` — is written down in exactly one place.
  vm.runInContext(frameAdaptedSource(DIE_INDEX_ALIAS, chosen.getDieIndex, 6), ctx);
  vm.runInContext(
    frameAdaptedSource(PHYS_CONFIG_ALIAS, chosen.getTransformedPhysicalConfig, 2), ctx);
  // legacy arity 4: (physX, physY, circleInside, state) -- `state` is trailing-optional and
  // is NOT the frame; only the leading argument moved.
  vm.runInContext(frameAdaptedSource(VALID_DIE_ALIAS, chosen.isValidDieAt, 4), ctx);
  return ctx;
}

const inputStub = (v) => ({ value: String(v) });
function setFrame(ctx, f) {
  ctx.el = {
    physWaferDia: inputStub(f.dia), physEdgeMargin: inputStub(f.em),
    physChipX: inputStub(f.chipX), physChipY: inputStub(f.chipY),
    physOffsetX: inputStub(f.offX), physOffsetY: inputStub(f.offY),
    gridCols: inputStub(f.cols), gridRows: inputStub(f.rows),
    gridStartX: inputStub(1), gridStartY: inputStub(1),
    gridYInvert: { checked: false },
  };
  ctx.currentRotation = f.rot;
  ctx.currentSide = f.side;
  ctx.boundingBoxCache = {};
}

// One frame -> the verdict for every cell of the visual rect, as a flat string.
function verdicts(ctx, f, validDieState) {
  setFrame(ctx, f);
  ctx.validDie = validDieState;
  const run = vm.runInContext(`(function (cols, rows, rot, side) {
    const isRot = (rot === 90 || rot === 270);
    const vc = isRot ? rows : cols, vr = isRot ? cols : rows;
    const pc = ${PHYS_CONFIG_ALIAS}(rot, side);
    const out = [];
    for (let r = 0; r < vr; r++) for (let c = 0; c < vc; c++) {
      const p = ${DIE_INDEX_ALIAS}(c, r, cols, rows, rot, side);
      const circle = isCellInsideWaferFast(c, r, vc, vr, pc, 700, 700);
      out.push(${VALID_DIE_ALIAS}(p.x, p.y, circle) ? 1 : 0);
    }
    return out;
  })`, ctx);
  return run(f.cols, f.rows, f.rot, f.side);
}

// ── the matrix: every axis that can hide a defect, all active ───────────────────
const GEOMS = [
  // anisotropic chip + a non-zero offset + edge margin != 0 (a declared 0 hits the
  // PRE-EXISTING `|| dflt` defect reported at M4 phase 1 §6-A - not this round's subject)
  { name: 'aniso_20mm', dia: 20, em: 1, chipX: 2, chipY: 3, offX: 0, offY: 0, cols: 11, rows: 9 },
  { name: 'aniso_offset', dia: 20, em: 1, chipX: 2, chipY: 3, offX: 0.5, offY: -0.25, cols: 11, rows: 9 },
  { name: 'prod_300mm', dia: 300, em: 3, chipX: 8, chipY: 6, offX: 0.5, offY: 0.25, cols: 39, rows: 51 },
];
const ROTS = [0, 90, 180, 270];
const SIDES = ['front', 'back'];

const baseSrc = (() => {
  try {
    return execFileSync('git', ['show', `${BASE}:client2/src/map_editor.js`],
      { cwd: REPO, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
  } catch (e) { die(`could not read ${BASE}:client2/src/map_editor.js from git`); }
})();
const workSrc = readFileSync(SRC_PATH, 'utf8');
// Kept, unweakened: comparing a file with itself yields 0 differing cells for the wrong
// reason. With a fixed acceptance base this fires only if the tree really is checked out AT
// that base, and dying is the right answer there. See the base note at the top for why it
// used to fire on every clean tree instead.
if (baseSrc === workSrc) {
  die(`baseline and working copy are identical - nothing to compare `
    + `(base ${BASE}; pass --base <git-rev> to compare against a different revision)`);
}

const baseCtx = buildVerdictFn(baseSrc, `${BASE} blob`);
const workCtx = buildVerdictFn(workSrc, 'working copy');

const NO_DECL = { basis: 'circle', keys: null, reason: '', ref: null, raw: undefined };

let cells = 0, diffs = 0, frames = 0;
const diffFrames = [];
for (const g of GEOMS) {
  for (const rot of ROTS) {
    for (const side of SIDES) {
      const f = { ...g, rot, side };
      const a = verdicts(baseCtx, f, NO_DECL);
      const b = verdicts(workCtx, f, NO_DECL);
      frames++;
      if (a.length !== b.length) die(`cell count differs for ${g.name}/${rot}/${side}`);
      let d = 0;
      for (let i = 0; i < a.length; i++) { cells++; if (a[i] !== b[i]) { diffs++; d++; } }
      if (d > 0) diffFrames.push(`${g.name}/${rot}/${side}: ${d}`);
    }
  }
}

// ── red-proof: put a defect back into the WORKING SOURCE and require this to fail ──
// The negative control below shows the comparator can see a state difference. This shows
// it can see a SOURCE difference on the very path INV-1 protects - the circle verdict of a
// map that declared nothing. Without it, "0 cells differ" could mean "measured nothing".
// (a `>= 1.0` boundary flip was tried first and moved 0 cells - exact boundary hits are
//  measure-zero at these geometries, so it proves nothing. A shrunken radius does bite.)
const MUTATED = workSrc.replace('if (normDistSq > 1.0) {', 'if (normDistSq > 0.9) {');
if (MUTATED === workSrc) die('red-proof mutation did not apply - isCellInsideWaferFast changed shape');
const mutCtx = buildVerdictFn(MUTATED, 'mutated working copy');
let redProof = 0;
for (const g of GEOMS) {
  const f = { ...g, rot: 90, side: 'back' };
  const a = verdicts(baseCtx, f, NO_DECL);
  const b = verdicts(mutCtx, f, NO_DECL);
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) redProof++;
}

// ── negative control ────────────────────────────────────────────────────────────
// The comparator must be able to SEE a difference. Declare a mask on the working copy
// only, and require a non-zero count - otherwise the zero above means "measured nothing".
const f0 = { ...GEOMS[0], rot: 90, side: 'back' };
const baseline = verdicts(baseCtx, f0, NO_DECL);
const masked = verdicts(workCtx, f0,
  { basis: 'ref', keys: new Set(['5_5', '5_4']), reason: '', ref: { table: 't', mapKey: 'k' }, raw: 'k' });
let controlDiff = 0;
for (let i = 0; i < baseline.length; i++) if (baseline[i] !== masked[i]) controlDiff++;

console.log(`\n=== INV-1 parity vs ${BASE} ===`);
console.log(`frames compared : ${frames}   (3 geometries x 4 rotations x 2 sides)`);
console.log(`cells compared  : ${cells}`);
console.log(`cells differing : ${diffs}`);
diffFrames.forEach(l => console.log(`   ${l}`));
console.log(`negative control (a declared mask MUST differ): ${controlDiff} cells`);
console.log(`red-proof (a defect in the circle path MUST differ): ${redProof} cells`);

// H1 protocol: the runner reads this line to tell "red with N assertions" from a crash.
// ran = per-cell parity comparisons + the two self-vacuity controls; failed mirrors `ok`.
console.log(`ASSERTIONS ${cells + 2} ${diffs + (controlDiff > 0 ? 0 : 1) + (redProof > 0 ? 0 : 1)}`);
const ok = diffs === 0 && controlDiff > 0 && redProof > 0;
console.log(ok
  ? `\nPASS - with no declaration the working copy reproduces ${BASE} cell for cell, `
    + `and the comparator is demonstrably able to see a difference (state AND source).`
  : `\nFAIL`);
process.exit(ok ? 0 : 1);
