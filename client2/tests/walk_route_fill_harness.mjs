// 「경로를 누르면 follow 가 채워진다」 — and the two ways it silently did not.
//
// WHY THIS EXISTS. Measured live 2026-09-06: clicking a derived route filled `hops` and ticked
// NOTHING. Two independent causes, and neither was visible to any check that existed:
//   ① the derivation speaks bare names (`observed`) and the checkboxes carry the declared
//      spelling (`observed@1`), so no name matched;
//   ② the second-hop predicate had no checkbox at all, because the list only offers predicates
//      whose subject is the START type — `observed` belongs to `die`.
// The import test and the request test were both GREEN through all of it: the wire was correct
// and only the screen was wrong. So this scores the screen's own decisions.
//
// IT IMPORTS ITS SUBJECT. Those decisions were closures inside `boot()`, reachable only by
// standing up a DOM; they now live in `src/walk/derive.js` and this file imports the same two
// functions the screen calls. Mutants are whole modules from `lib/probe.mjs`.
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(HERE, '..', 'src', 'walk', 'derive.js');

let pass = 0, fail = 0, quiet = false;
const failedNames = [];
function ok(cond, name) {
  if (cond) { pass++; if (!quiet) console.log(`  OK   ${name}`); }
  else { fail++; failedNames.push(name); if (!quiet) console.log(`  BAD  ${name}`); }
}

// The declaration's own spelling, and a route as `pathsBetween` actually returns it.
// 🔴 These are the LIVE shapes, not invented ones: the walk screen's follow boxes read
//    `inspected@1 · measures@1 · processed_with@1 · register@1` for a `wafer@1` seed, and the
//    two-hop route to `defect` is `[inspected, observed]`.
const DECLARED = ['inspected@1', 'measures@1', 'processed_with@1', 'register@1', 'observed@1',
  'of_kind@1', 'bonded_from@1'];
const FROM_WAFER = ['inspected@1', 'measures@1', 'processed_with@1', 'register@1'];
const ROUTE_2HOP = ['inspected', 'observed'];
const ROUTE_3HOP = ['measures', 'leads_to', 'of_kind'];

function suite(M) {
  const before = { pass, fail };

  const filled = M.followFromRoute(DECLARED, ROUTE_2HOP);
  ok(filled.length === 2, 'F1 a two-hop route fills TWO predicates, not zero');
  ok(filled.includes('inspected@1') && filled.includes('observed@1'),
    'F2 ... and they are the DECLARED spellings, matched on the bare name');

  // 🔴 The control for F1/F2: a route naming something the declaration does not have must fill
  //    nothing. Without it, a function that returned every declared name would pass both above.
  ok(M.followFromRoute(DECLARED, ['not_a_predicate']).length === 0,
    'F3 a predicate the declaration does not carry fills nothing');
  ok(M.followFromRoute(DECLARED, []).length === 0, 'F4 an empty route fills nothing');

  // A three-hop route whose middle predicate is undeclared here: the two that exist still land.
  ok(M.followFromRoute(DECLARED, ROUTE_3HOP).join() === 'measures@1,of_kind@1',
    'F5 a longer route fills every hop the declaration knows');

  const shown = M.followChoices(FROM_WAFER, DECLARED, new Set(filled));
  ok(shown.includes('observed@1'),
    'C1 a later-hop predicate that is SELECTED becomes visible, though it does not start here');
  ok(FROM_WAFER.every((n) => shown.includes(n)),
    'C2 ... and the start-type options all stay — the filter is widened, not replaced');
  ok(new Set(shown).size === shown.length, 'C3 ... with no duplicate row for the overlap');

  // 🔴 The control for C1: nothing selected must not widen the list. Otherwise "show the
  //    selected too" and "show everything" are the same function and C1 proves nothing.
  ok(M.followChoices(FROM_WAFER, DECLARED, new Set()).join() === FROM_WAFER.join(),
    'C4 with nothing selected the list is exactly the start-type set');

  ok(M.bareName('observed@1') === 'observed' && M.bareName('observed') === 'observed',
    'B1 the version suffix is dropped, and a bare name survives unchanged');

  return { fail: fail - before.fail };
}

console.log('-- the screen\'s two decisions ---------------------------------------');
suite(await import('../src/walk/derive.js'));

const base = { pass, fail };
failedNames.length = 0;

// -- mutants -----------------------------------------------------------------------------
// ③ of the Lead's gate: deleting the filling line must turn ① red.
const DEFECTS = [
  ['the spellings are compared directly again, so nothing is ticked',
    (s) => s.replace('  const wanted = new Set((routeFollow || []).map(bareName));\n'
      + '  return (declaredNames || []).filter((name) => wanted.has(bareName(name)));',
    '  const wanted = new Set(routeFollow || []);\n'
      + '  return (declaredNames || []).filter((name) => wanted.has(name));')],
  ['the fill returns nothing at all',
    (s) => s.replace('  return (declaredNames || []).filter((name) => wanted.has(bareName(name)));',
      '  return [];')],
  ['the later-hop predicate stops being shown',
    (s) => s.replace('  return [...new Set([...(fromStartType || []), ...extra])];',
      '  return [...(fromStartType || [])];')],
  ['the list widens to everything instead of to what is selected',
    (s) => s.replace('  const extra = (declaredNames || []).filter((name) => picked.has(name));',
      '  const extra = (declaredNames || []);')],
];
const CONTROLS = [
  ['a local rename', (s) => s.replace('  const wanted = new Set((routeFollow || []).map(bareName));',
    '  const want = new Set((routeFollow || []).map(bareName));')
    .replace('  return (declaredNames || []).filter((name) => wanted.has(bareName(name)));',
      '  return (declaredNames || []).filter((name) => want.has(bareName(name)));')],
  ['comments stripped', (s) => s.split('\n').filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l)).join('\n')],
];

quiet = true;
let caught = 0; const escaped = [];
async function score(name, mutate, tag) {
  try { return suite((await loadWithProbe(SRC, { mutate, tag })).module); }
  catch (e) {
    if (/did not mutate|unchanged/.test(String(e && e.message))) {
      quiet = false; console.error(`  anchor GONE: ${name} — ${e.message}`); process.exit(2);
    }
    return { fail: 1 };
  }
}
console.log('\n-- defect mutants (each must be CAUGHT) ------------------------------');
for (const [name, mutate] of DEFECTS) {
  const r = await score(name, mutate, 'wkfill');
  if (r.fail > 0) { caught++; console.log(`  caught  ${name}`); }
  else { escaped.push(name); console.log(`  ESCAPED ${name}`); }
}
console.log('\n-- control mutants (each must ESCAPE) --------------------------------');
for (const [name, mutate] of CONTROLS) {
  const r = await score(name, mutate, 'wkfillc');
  if (r.fail === 0) console.log(`  escaped ${name}`);
  else { escaped.push(`control caught: ${name}`); console.log(`  CAUGHT  ${name} <- control caught`); }
}
quiet = false;

if (base.fail) console.error(`\nfailed:\n  ${failedNames.join('\n  ')}`);
if (escaped.length) console.error(`\nwrong verdicts:\n  ${escaped.join('\n  ')}`);

console.log(`\n${base.pass} passed, ${base.fail} failed; ${caught}/${DEFECTS.length} defects `
  + `caught; ${CONTROLS.length - escaped.filter((e) => e.startsWith('control')).length}/`
  + `${CONTROLS.length} controls escaped.`);
console.log(`ASSERTIONS ${base.pass + base.fail} ${base.fail}`);
process.exit(base.fail === 0 && escaped.length === 0 ? 0 : 1);
