// The screen checker's --mutant (lead 11-07): a named mutant runs and the others do not. The subject is imported
// (lib/mutant_pick.mjs - the checker builds the `run` it answers).
//
//   named    --mutant <name>, repeatable: those, in the list's order; none named: every mutant
//   narrow   --only and --touched narrow by page on top of the names
//   unknown  a name no mutant has is said - a typo is not a silent «nothing ran»
//
// Run: node client2/tests/mutant_pick_harness.mjs
import { namedMutants, pickMutants } from './lib/mutant_pick.mjs';

let pass = 0;
const failures = [];
function eq(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { pass++; console.log(`  PASS ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name}\n        got  ${g}\n        want ${w}`); }
}

const MUTANTS = [{ name: 'Pivot drawn on every table', entry: 'index.html' }, { name: 'a click no longer selects its row', entry: 'index.html' },
  { name: 'the footer counts rows in pivot view', entry: 'index.html' }, { name: 'a walk drawn twice', entry: 'walk.html' }];
const names = (picked) => picked.run.map((m) => m.name);

eq('A1 --mutant read in order, repeatable; a trailing flag without a name is no name',
  namedMutants(['node', 'h.mjs', '--mutant', 'b', '--touched', '--mutant', 'a', '--mutant']), ['b', 'a']);
eq('A2 no --mutant: none named', namedMutants(['node', 'h.mjs', '--mutate', '--touched']), []);

eq('N1 one named: it runs, the others do not', names(pickMutants(MUTANTS, { named: ['a click no longer selects its row'] })),
  ['a click no longer selects its row']);
eq('N2 two named: both, in the list\'s order', names(pickMutants(MUTANTS, { named: ['the footer counts rows in pivot view', 'Pivot drawn on every table'] })),
  ['Pivot drawn on every table', 'the footer counts rows in pivot view']);
eq('N3 none named: every mutant', names(pickMutants(MUTANTS)).length, 4);
eq('O1 --only and --touched narrow by page on top of the names',
  [names(pickMutants(MUTANTS, { named: ['a walk drawn twice', 'Pivot drawn on every table'], only: 'walk.html' })),
    names(pickMutants(MUTANTS, { picked: ['walk.html'] }))], [['a walk drawn twice'], ['a walk drawn twice']]);
eq('U1 a name no mutant has: said, and nothing else built for it',
  pickMutants(MUTANTS, { named: ['Pivot drawn on every tabel'] }), { run: [], unknown: ['Pivot drawn on every tabel'] });

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
