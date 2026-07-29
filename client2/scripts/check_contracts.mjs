#!/usr/bin/env node
//
// Run every seam contract's client harness, and fail the build if any of them diverges.
//
// WHY THIS EXISTS. `contracts/<name>/client_harness.mjs` scores the client half of a seam
// against `vectors.json`. Until 2026-07-30 nothing executed any of them: `pytest server/tests/`
// scores only the server half, and `client2/package.json` had no script for them. A contract
// that nobody runs is a comment. This is not hypothetical — `split_registry_harness.mjs` threw
// at its extraction step for weeks after five symbols were renamed, and the failure was
// invisible because no gate called it. contract-keeper reported the same condition for all four
// contracts on 2026-07-30.
//
// DISCOVERY, NOT A LIST. Harnesses are found by scanning `contracts/*/client_harness.mjs`.
// A hardcoded list would recreate the exact bug this closes: contract #5 lands, nobody adds it
// here, and it is dead on arrival while the build stays green.
//
// A harness signals divergence with a NON-ZERO EXIT. `map_seam` prints "DECLARED DIVERGENCES"
// and still exits 0 — those are named, expected divergences pinned by its vectors, which is the
// contract-keeper charter's rule 5 (no anonymous permanent red). Exit code is the only verdict
// this runner reads; interpreting harness prose here would put a second scorer in the pipeline.

import { spawnSync } from 'node:child_process';
import { readdirSync, existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, '..', '..');
const CONTRACTS_DIR = path.join(REPO_ROOT, 'contracts');
const HARNESS_NAME = 'client_harness.mjs';

const fail = msg => { console.error(`\n✗ ${msg}\n`); process.exit(1); };

// An empty scan must be LOUD. If `contracts/` is moved or renamed, a silent "0 harnesses, all
// green" is worse than the unwired state it replaced: it reports coverage that does not exist.
if (!existsSync(CONTRACTS_DIR)) {
  fail(`no \`contracts/\` directory at ${CONTRACTS_DIR}. If contracts moved, update this runner — `
     + `an empty scan must never pass as "all contracts green".`);
}

const harnesses = readdirSync(CONTRACTS_DIR, { withFileTypes: true })
  .filter(d => d.isDirectory())
  .map(d => ({ name: d.name, file: path.join(CONTRACTS_DIR, d.name, HARNESS_NAME) }))
  .filter(h => existsSync(h.file))
  .sort((a, b) => a.name.localeCompare(b.name));

if (harnesses.length === 0) {
  fail(`\`contracts/\` holds no \`${HARNESS_NAME}\`. Either every contract lost its client half, `
     + `or the layout changed — both need a human, neither is a passing build.`);
}

let diverged = 0;
for (const h of harnesses) {
  const run = spawnSync(process.execPath, [h.file], { cwd: REPO_ROOT, encoding: 'utf8' });
  const ok = run.status === 0;
  console.log(`${ok ? '✓' : '✗'} contract ${h.name}`);
  if (!ok) {
    diverged++;
    // Print the harness's own output only on failure. Its job is to say WHICH assertion
    // diverged and with what values; re-summarising it here would lose exactly that.
    process.stdout.write(run.stdout || '');
    process.stderr.write(run.stderr || '');
    if (run.error) console.error(String(run.error));
  }
}

if (diverged > 0) {
  fail(`${diverged} of ${harnesses.length} contract(s) diverged. The client and server halves of `
     + `a seam no longer give the same answer — fix the implementation or, if the contract is `
     + `what changed, take it to the Lead PM. Do not edit vectors to make this pass.`);
}

console.log(`\n✓ ${harnesses.length} contracts, no divergence.\n`);
