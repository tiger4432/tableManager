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

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = join(HERE, '..', '..');
const SRC_PATH = join(HERE, '..', 'src', 'map_editor.js');
const baseIdx = process.argv.indexOf('--base');
const BASE = baseIdx > 0 ? process.argv[baseIdx + 1] : 'HEAD';

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
//   isValidDieAt(phys.x, phys.y, isCellInsideWaferFast(...))
const NEEDED = ['physNum', 'gridDimNum', 'withPhysFrame', 'getScreenShift',
  'getTransformedPhysicalConfig', 'getPhysicalCoords', 'isCellInsideWaferFast',
  'getWaferBoundingBox', 'validDieBasis', 'isValidDieAt'];

function buildVerdictFn(src, label) {
  const parts = NEEDED.map(name => {
    const m = new RegExp(`(?:async\\s+)?function\\s+${name}\\s*\\(`).exec(src);
    if (!m) die(`function ${name} not found in ${label}`);
    const out = sliceBalanced(src, m.index);
    if (!out) die(`unbalanced braces for ${name} in ${label}`);
    return out;
  });
  const ctx = {
    console, physFrameOverride: null, currentRotation: 0, currentSide: 'front',
    validDie: null, boundingBoxCache: {}, el: {},
  };
  vm.createContext(ctx);
  try { vm.runInContext(parts.join('\n\n'), ctx); } catch (e) {
    die(`sandbox evaluation failed for ${label} - ${e && e.message ? e.message : e}`);
  }
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
  ctx.physFrameOverride = null;
}

// One frame -> the verdict for every cell of the visual rect, as a flat string.
function verdicts(ctx, f, validDieState) {
  setFrame(ctx, f);
  ctx.validDie = validDieState;
  const run = vm.runInContext(`(function (cols, rows, rot, side) {
    const isRot = (rot === 90 || rot === 270);
    const vc = isRot ? rows : cols, vr = isRot ? cols : rows;
    const pc = getTransformedPhysicalConfig(rot, side);
    const out = [];
    for (let r = 0; r < vr; r++) for (let c = 0; c < vc; c++) {
      const p = getPhysicalCoords(c, r, cols, rows, rot, side);
      const circle = isCellInsideWaferFast(c, r, vc, vr, pc, 700, 700);
      out.push(isValidDieAt(p.x, p.y, circle) ? 1 : 0);
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
if (baseSrc === workSrc) die('baseline and working copy are identical - nothing to compare');

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

const ok = diffs === 0 && controlDiff > 0 && redProof > 0;
console.log(ok
  ? `\nPASS - with no declaration the working copy reproduces ${BASE} cell for cell, `
    + `and the comparator is demonstrably able to see a difference (state AND source).`
  : `\nFAIL`);
process.exit(ok ? 0 : 1);
