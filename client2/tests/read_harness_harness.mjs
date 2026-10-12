#!/usr/bin/env node
// check_harnesses reads every harness through scripts/read_harness.mjs (lead 10-13): an output inside its buffer is
// read whole, one past it is no verdict (null) - not a red one. The fixture says 1.2 MB, past spawnSync's 1 MiB default.
//   node client2/tests/read_harness_harness.mjs
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const READER = path.join(HERE, '..', 'scripts', 'read_harness.mjs');
const LOUD = path.join(HERE, 'fixtures', 'loud_harness.mjs');

async function measure(mutate) {
  const { module: m } = await loadWithProbe(READER, { expose: ['readHarness'], mutate });
  const big = m.readHarness(LOUD, [], HERE);
  const small = m.readHarness(LOUD, [], HERE, 16384);
  return {
    read: Boolean(big) && big.status === 0 && /^ASSERTIONS 1 0$/m.test(big.stdout),
    none: small === null,
  };
}
const cells = (r) => [
  ['R1 an output inside the gate\'s buffer is read whole - its ASSERTIONS line is there (1.2 MB, past the 1 MiB default)', r.read],
  ['R2 an output past the buffer is no verdict: null, not a run with no ASSERTIONS line', r.none],
];
const DEFECTS = [
  ['D1 the gate reads with spawnSync\'s default buffer (the code before) -> R1', 'R1',
    (t) => t.replace('maxBuffer = RUN_BUFFER', 'maxBuffer = undefined').replace("{ cwd, encoding: 'utf8', maxBuffer }", "{ cwd, encoding: 'utf8', ...(maxBuffer ? { maxBuffer } : {}) }")],
  ['D2 an output past the buffer comes back as a run -> R2', 'R2',
    (t) => t.replace("  if (run.error && run.error.code === 'ENOBUFS') return null;\n", '')],
];

let pass = 0;
let fail = 0;
const failed = [];
console.log('-- read_harness (lead 10-13) ---------------------------------------');
for (const [name, ok] of cells(await measure())) {
  console.log(`  ${ok ? 'OK ' : 'BAD'}  ${name}`);
  if (ok) pass += 1; else { fail += 1; failed.push(name); }
}
console.log('');
console.log('-- defect mutants (each must be caught by the check it names) ------');
let escaped = 0;
for (const [name, names, mutate] of DEFECTS) {
  // The text comes through the probe's one reader (LF), so the anchors are written with \n.
  const caught = cells(await measure((t) => {
    const out = mutate(t);
    if (out === t) throw new Error(`mutant «${name}» changed nothing - its anchor is gone`);
    return out;
  })).some(([n, ok]) => n.startsWith(names) && !ok);
  if (!caught) escaped += 1;
  console.log(`  ${caught ? 'caught ' : 'ESCAPED'} ${name}`);
}
console.log('');
console.log(`${pass} passed, ${fail} failed; ${DEFECTS.length - escaped}/${DEFECTS.length} defects caught.`);
console.log(`ASSERTIONS ${pass + fail} ${fail}`);
if (fail) console.log(`FAILED: ${failed.join(' | ')}`);
if (fail || escaped) process.exitCode = 1;
