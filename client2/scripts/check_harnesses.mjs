#!/usr/bin/env node
//
// Run every harness under `client2/tests/`, and fail the build on the ones that are supposed
// to be green.
//
// WHY THIS EXISTS. `client2/tests/` held 15 harnesses and nothing ran 14 of them: only
// `value_suggest_keys_harness.mjs` had a package.json script. The sibling gate
// (`check_contracts.mjs`) covers `contracts/*/client_harness.mjs` and stops at that directory.
// The cost of the gap is measured, not hypothetical: `da8f390` added one module global to
// `getGridCellObject` and killed `company_roundtrip_harness.mjs` and
// `copy_header_count_harness.mjs` outright ― the build stayed green for a full round, and by
// the time anyone looked, `copy_header_count_harness.mjs` had accumulated three more
// independent breakages (`ae2811c`'s `notchMarkCell`, the tsv.js import move, and two
// mutation anchors that stopped matching). A harness nobody runs is a comment.
//
// DISCOVERY, NOT A LIST. Harnesses are found by scanning `client2/tests/*.mjs`, the same way
// `check_contracts.mjs` scans `contracts/`. A hardcoded roster would recreate the exact defect
// this closes: harness #16 lands, nobody adds it here, and it is dead on arrival.
//
// KNOWN_RED IS A DEBT LIST, NOT A SKIP LIST. Harnesses that are red TODAY are still executed
// and still reported as failing ― they just do not fail the build, because wedging the build
// on pre-existing red is not a gate, it is an outage. Every entry carries a reason and must be
// removed the moment it goes green (the runner says so out loud when that happens). A silent
// skip would be the same defect as no gate at all.
//
// EXIT CODE IS THE ONLY VERDICT this runner reads. A harness that prints prose and exits 0 has
// said it is green; interpreting its prose here would put a second scorer in the pipeline.

import { spawnSync } from 'node:child_process';
import { readdirSync, existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, '..', '..');
const TESTS_DIR = path.join(REPO_ROOT, 'client2', 'tests');

const fail = msg => { console.error(`\n✗ ${msg}\n`); process.exit(1); };

// ── the debt list ───────────────────────────────────────────────────────────────
// Red as of 2026-07-30. Each is RUN and REPORTED; none of them blocks the build yet.
// Delete an entry the moment its harness goes green ― the runner tells you when.
const KNOWN_RED = new Map([
  ['effort_instrument_harness.mjs',
    'throws during setup (sandbox build) ― never reached its assertions'],
  ['reposition_regime_probe.mjs',
    'throws with ERR_INVALID_ARG_TYPE ― a path/arg it reads has moved'],
  ['split_registry_harness.mjs',
    'throws at its extraction step ― symbols it slices were renamed (known since 2026-07-30)'],
  ['valid_die_authoring_harness.mjs',
    '98 passed / 1 failed ― one assertion, not a crash'],
  ['valid_die_frame_adoption_harness.mjs',
    '28 of 228 assertions fail ― most are fixtures holding the pre-da8f390 contract; under triage'],
]);

if (!existsSync(TESTS_DIR)) {
  fail(`no \`client2/tests/\` directory at ${TESTS_DIR}. If the harnesses moved, update this `
     + `runner ― an empty scan must never pass as "all harnesses green".`);
}

const harnesses = readdirSync(TESTS_DIR, { withFileTypes: true })
  .filter(d => d.isFile() && d.name.endsWith('.mjs'))
  .map(d => d.name)
  .sort((a, b) => a.localeCompare(b));

if (harnesses.length === 0) {
  fail(`\`client2/tests/\` holds no \`*.mjs\`. Either every harness was deleted or the layout `
     + `changed ― both need a human, neither is a passing build.`);
}

const blocking = [];
const stillRed = [];
const recovered = [];

for (const name of harnesses) {
  const run = spawnSync(process.execPath, [path.join(TESTS_DIR, name)],
    { cwd: REPO_ROOT, encoding: 'utf8' });
  const ok = run.status === 0;
  const known = KNOWN_RED.has(name);

  if (ok && known) {
    recovered.push(name);
    console.log(`✓ ${name}  (was on the known-red list ― remove it)`);
  } else if (ok) {
    console.log(`✓ ${name}`);
  } else if (known) {
    stillRed.push(name);
    console.log(`✗ ${name}  [known red] ${KNOWN_RED.get(name)}`);
  } else {
    blocking.push({ name, run });
    console.log(`✗ ${name}  [BLOCKING]`);
  }
}

const gated = harnesses.length - KNOWN_RED.size;
console.log(`\n${harnesses.length} harnesses ― ${gated} gated, ${KNOWN_RED.size} on the known-red `
  + `debt list (${stillRed.length} still red, ${recovered.length} recovered).`);

if (recovered.length > 0) {
  console.log(`\n! ${recovered.length} harness(es) on the known-red list now PASS. Take them off `
    + `the list in client2/scripts/check_harnesses.mjs so they start gating:\n  `
    + recovered.join('\n  ') + '\n');
}

if (blocking.length > 0) {
  // Print each failing harness's own output. Its job is to say WHICH assertion failed and with
  // what values; re-summarising it here would lose exactly that.
  for (const b of blocking) {
    console.error(`\n──────── ${b.name} ────────`);
    process.stdout.write(b.run.stdout || '');
    process.stderr.write(b.run.stderr || '');
    if (b.run.error) console.error(String(b.run.error));
  }
  fail(`${blocking.length} harness(es) that were green went red: `
     + `${blocking.map(b => b.name).join(', ')}. Fix the code, or ― if the contract is what `
     + `changed ― take it to the Lead PM. Adding it to KNOWN_RED to get a green build is how `
     + `this directory went 14/15 unrun in the first place.`);
}

console.log(`✓ every gated harness is green.\n`);
