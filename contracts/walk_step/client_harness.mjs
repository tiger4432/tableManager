/**
 * WALK STEP — the CLIENT half, scored against `vectors.json`.
 *
 *   node contracts/walk_step/client_harness.mjs
 *
 * Exit codes: 0 = the client takes exactly the steps the contract says
 *             1 = divergence(s)   2 = harness failure
 *
 * Read-only. It imports `client2/src/walk/derive.js` and calls `walkTakesStep` — the seat the
 * follow list (step 0) and the route list (every step) both ask.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const DERIVE = join(HERE, '..', '..', 'client2', 'src', 'walk', 'derive.js');

let vectors;
let derive;
try {
  vectors = JSON.parse(readFileSync(join(HERE, 'vectors.json'), 'utf8'));
  derive = await import(pathToFileURL(DERIVE).href);
} catch (e) {
  console.error(`walk_step: could not load its own subject — ${e && e.message}`);
  process.exit(2);
}

const CASES = vectors.cases || [];
// 🔴 A set with only one answer cannot tell 「the rule」 from 「always yes」 or 「always no」.
if (!CASES.some((c) => c.takes === true) || !CASES.some((c) => c.takes === false)) {
  console.error('walk_step: the vectors need both a taken and a refused step — an empty or one-sided set passes anything.');
  process.exit(2);
}
if (typeof derive.walkTakesStep !== 'function') {
  console.error('walk_step: `walkTakesStep` is gone from client2/src/walk/derive.js. That is the finding.');
  process.exit(1);
}

const failures = [];
console.log(`\n[1] the step rule — ${CASES.length} cases`);
for (const c of CASES) {
  const got = derive.walkTakesStep(new Set(c.static_types), c.from, c.to, c.step);
  if (got === c.takes) console.log(`  PASS ${c.id}`);
  else {
    failures.push(c.id);
    console.log(`  FAIL ${c.id} — ${c.from} -> ${c.to} at step ${c.step}: want ${c.takes}, got ${got}`);
  }
}

console.log(`\n${CASES.length - failures.length} passed, ${failures.length} diverged.`);
process.exit(failures.length ? 1 : 0);
