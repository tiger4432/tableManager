// Score the ONE place that says "a person overwrote this cell".
//
// WHY THIS EXISTS. The grid paints a pin from `priority_source` / `manual_priority_source` and
// never from `is_overwrite`. Measured 2026-09-06: six sites marked a cell as user-overwritten
// and four of them set only `is_overwrite`, so a cell's FIRST overwrite through paste, clear,
// range-write or a transaction commit was drawn as an untouched cell. The split hid on a cell
// that already carried a pin, because those patches merge. The repair routes all six through
// `markCellOverwritten`, and this harness exists so that removing the half they used to omit
// turns something red instead of turning the pin off again.
//
// IT IMPORTS ITS SUBJECT. `grid.js` loads under node, so the mutants are whole modules built by
// `lib/probe.mjs` (byte-identical copy + append). Nothing here slices a function body out of a
// file, and a mutant that fails to parse fails loudly rather than scoring as caught.
import { readFileSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC_DIR = path.join(HERE, '..', 'src');
const SRC_PATH = path.join(SRC_DIR, 'grid.js');

let pass = 0, fail = 0, quiet = false;
const failedNames = [];
function ok(cond, name) {
  if (cond) { pass++; if (!quiet) console.log(`  OK   ${name}`); }
  else { fail++; failedNames.push(name); if (!quiet) console.log(`  BAD  ${name}`); }
  return !!cond;
}

// The whole suite, run against ONE module object so a mutant is scored with the same checks.
function suite(M) {
  const before = { pass, fail };
  const mk = () => ({ row_id: 'r1', data: {} });

  const a = mk();
  M.ensureCellObject(a, 'c1');
  ok('priority_source' in a.data.c1,
    'A1 the constructor creates `priority_source` -- the field the paint rule reads');

  const b = mk();
  M.markCellOverwritten(b, 'c1', 'v');
  ok(b.data.c1.is_overwrite === true, 'A2 marking sets `is_overwrite`');
  ok(b.data.c1.priority_source === 'user',
    'A3 marking ALSO sets `priority_source` -- the half four sites used to omit');
  ok(b.data.c1.value === 'v', 'A4 the supplied value is written');

  ok(M.PRIORITY_SOURCE_USER === 'user',
    'A5 the writer and the paint rule share one spelling of the pin value');

  const c = mk();
  c.data.c1 = { value: 'keep', is_overwrite: false, priority_source: null };
  M.markCellOverwritten(c, 'c1');
  ok(c.data.c1.value === 'keep', 'A6 omitting the value leaves the stored one alone');
  ok(c.data.c1.priority_source === 'user', 'A7 ... and still marks the pin');

  const d = mk();
  d.data.c1 = { value: 'x', is_overwrite: true, priority_source: 'collision_merge' };
  M.markCellOverwritten(d, 'c1', 'y');
  ok(d.data.c1.priority_source === 'user',
    'A8 a later user overwrite wins over an earlier merge mark');

  let threw = false;
  try { M.markCellOverwritten(null, 'c1'); } catch (e) { threw = true; }
  ok(!threw, 'A9 marking a missing row is a no-op, not a throw');

  return { pass: pass - before.pass, fail: fail - before.fail };
}

console.log('-- the canonical writer --------------------------------------------');
const REAL = await import('../src/grid.js');
suite(REAL);

// A10: THE POPULATION. Text IS the subject here, not a stand-in for behaviour.
// The defect this closes is not "one function is wrong", it is "the fact had six authors". No
// behavioural check can see a SEVENTH author appearing in another file, because that author's
// code is on no path this harness calls. So the question asked here is literally a question
// about the source: how many files assign this field. It fails the day someone writes the pair
// by hand again.
console.log('\n-- the population --------------------------------------------------');
function jsFiles(dir) {
  const out = [];
  for (const e of readdirSync(dir)) {
    const p = path.join(dir, e);
    if (statSync(p).isDirectory()) out.push(...jsFiles(p));
    else if (e.endsWith('.js') && !e.includes('.probe-copy.')) out.push(p);
  }
  return out;
}
const writers = jsFiles(SRC_DIR)
  .filter(p => /\bis_overwrite\s*=\s*true/.test(readFileSync(p, 'utf8')))
  .map(p => path.relative(SRC_DIR, p).replace(/\\/g, '/'));
ok(writers.length === 1 && writers[0] === 'grid.js',
  `A10 exactly one file marks a cell overwritten -- found [${writers.join(', ')}]`);

// A11: the UNDO direction, same drift oracle and the same reason. C-22, measured 2026-09-06:
// three sites restore a saved `is_overwrite` and only two restored the other half, so
// discarding a staged edit left the cell drawn as a pin it no longer had. Counting rather than
// window-matching on purpose -- a window is what hid the sixth marking site this morning.
// 🔵 The pair is what is asserted, not a number: if a fourth restore site lands, both counts
//    move together or this goes red.
const bodies = jsFiles(SRC_DIR).map((p) => readFileSync(p, 'utf8')).join('\n');
const restoresFlag = (bodies.match(/\.is_overwrite\s*=\s*old[A-Za-z]*/g) || []).length;
const restoresPin = (bodies.match(/\.priority_source\s*=\s*old[A-Za-z]*/g) || []).length;
ok(restoresFlag > 0 && restoresFlag === restoresPin,
  `A11 every site that restores the flag restores the pin too -- flag ${restoresFlag}, pin ${restoresPin}`);

// -- mutants ---------------------------------------------------------------------------
const DEFECTS = [
  ['the pin half is dropped again',
    s => s.replace('  cell.priority_source = PRIORITY_SOURCE_USER;\n', '')],
  ['the writer spells the pin value differently from the rule',
    s => s.replace("export const PRIORITY_SOURCE_USER = 'user';",
                   "export const PRIORITY_SOURCE_USER = 'User';")],
  ['the constructor stops creating the field the rule reads',
    s => s.replace('      priority_source: null\n', '')],
  ['marking overwrites the stored value when none was supplied',
    s => s.replace('  if (value !== undefined) cell.value = value;', '  cell.value = value;')],
];
const CONTROLS = [
  ['a local rename', s => s
    .replace('  const cell = dataObj && dataObj.data ? dataObj.data[colId] : null;\n  if (!cell) return;',
             '  const target = dataObj && dataObj.data ? dataObj.data[colId] : null;\n  if (!target) return;')
    .replace('  if (value !== undefined) cell.value = value;\n  cell.is_overwrite = true;\n  cell.priority_source = PRIORITY_SOURCE_USER;',
             '  if (value !== undefined) target.value = value;\n  target.is_overwrite = true;\n  target.priority_source = PRIORITY_SOURCE_USER;')],
  ['comments stripped', s => s.split('\n').filter(l => !/^\s*\/\//.test(l)).join('\n')],
];

async function scoreMutant(mutate, tag) {
  try {
    return suite((await loadWithProbe(SRC_PATH, { mutate, tag })).module);
  } catch (e) {
    const m = String(e && e.message);
    if (/did not mutate|unchanged/.test(m)) {
      quiet = false;
      console.error(`\nan anchor no longer matches: ${m}`);
      process.exit(2);
    }
    return { pass: 0, fail: 1 };
  }
}

// The reported count is the REAL run's, snapshotted here. Mutant runs deliberately fail, and
// folding their failures into `failed` would make a working gate report nine failures -- the
// runner reads that line as evidence, so it has to describe the subject, not the corpus.
const base = { pass, fail };
failedNames.length = 0;

quiet = true;
let caught = 0; const escapedNames = [];
console.log('\n-- defect mutants (each must be CAUGHT) ----------------------------');
for (const [name, mutate] of DEFECTS) {
  const r = await scoreMutant(mutate, 'cellmark');
  if (r.fail > 0) { caught++; console.log(`  caught  ${name}`); }
  else { escapedNames.push(name); console.log(`  ESCAPED ${name}`); }
}

let controlsCaught = 0;
console.log('\n-- control mutants (each must ESCAPE) ------------------------------');
for (const [name, mutate] of CONTROLS) {
  const r = await scoreMutant(mutate, 'cellmarkc');
  if (r.fail === 0) console.log(`  escaped ${name}`);
  else { controlsCaught++; console.log(`  CAUGHT  ${name}  <- a check is reading source text`); }
}
quiet = false;

if (base.fail) console.error(`\nfailed:\n  ${failedNames.join('\n  ')}`);
if (escapedNames.length) console.error(`\ndefects that escaped:\n  ${escapedNames.join('\n  ')}`);

const bad = base.fail + escapedNames.length + controlsCaught;
console.log(`\n${base.pass} passed, ${base.fail} failed; ${caught}/${DEFECTS.length} defects `
  + `caught, ${escapedNames.length} escaped; ${CONTROLS.length - controlsCaught}/`
  + `${CONTROLS.length} controls escaped.`);
console.log(`ASSERTIONS ${base.pass + base.fail} ${base.fail}`);
process.exit(bad ? 1 : 0);
