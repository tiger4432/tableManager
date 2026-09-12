#!/usr/bin/env node
//
// WALK AGGREGATE -- the CLIENT half, scored against contracts/walk_aggregate/vectors.json.
//
//     node contracts/walk_aggregate/client_harness.mjs [--json]
//
// Discovered and run by `client2/scripts/check_contracts.mjs`, which scans
// `contracts/*/client_harness.mjs`. A non-zero exit is the only verdict that runner reads.
//
// ⛔ THIS HARNESS IMPORTS. It does not read `api.js` as text and it does not re-type the
// seven folds. 「잘라쓰기 하니스 절대 금지」 -- a harness that cut the table out would be
// measuring the SHAPE OF THE SOURCE, and it would go green on a file that no longer runs.
//
// EXIT CODES ARE THREE, NOT TWO
//   0  scored, no divergence      1  scored, DIVERGED      2  COULD NOT SCORE
//
// 🔴 TODAY THIS EXITS 2, AND THAT IS THE FINDING RATHER THAN A GAP IN THE HARNESS.
// `AGGREGATE` in `client2/src/rnd_board/api.js` is a module-private `const`: the server
// half of this seam landed with S-146 and the client half is C-90, which is where the table
// becomes reachable (either exported, or replaced by a read of the server's `groups`). Until
// then the honest verdict is 「could not score」 -- NOT a silent pass, which is what a harness
// that quietly folded the vectors with its own arithmetic would produce, and not a red,
// because nothing has diverged yet.
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const vectors = JSON.parse(readFileSync(resolve(here, 'vectors.json'), 'utf8'));
const asJson = process.argv.includes('--json');

const report = (code, verdict, detail) => {
  if (asJson) {
    process.stdout.write(`${JSON.stringify({ seam: 'walk_aggregate', verdict, detail })}\n`);
  } else {
    process.stdout.write(`walk_aggregate: ${verdict} -- ${detail}\n`);
  }
  process.exit(code);
};

let AGGREGATE = null;
try {
  // ⚠️ A FILE URL, NOT A PATH. On Windows `import('C:\…')` throws 「protocol 'c:'」,
  // and this harness would then report 「could not score」 for a reason that has nothing
  // to do with the seam - a false diagnosis that would survive C-90 landing.
  const api = await import(
    pathToFileURL(resolve(here, '../../client2/src/rnd_board/api.js')).href);
  AGGREGATE = api.AGGREGATE || null;
} catch (error) {
  report(2, 'COULD NOT SCORE',
    `client2/src/rnd_board/api.js did not import: ${error && error.message}`);
}

if (!AGGREGATE) {
  report(2, 'COULD NOT SCORE',
    'AGGREGATE is not exported from client2/src/rnd_board/api.js -- the client half of this '
    + 'seam is C-90. The server half is scored by server/tests/test_walk_aggregate_contract.py, '
    + 'and this side stays unscored rather than folding the vectors with arithmetic of its own.');
}

// ---------------------------------------------------------------------------
// Reached once C-90 exports the table: the SAME vectors, folded by the client.
// ---------------------------------------------------------------------------
// 🔴 THE SAME THREE SOURCES, IN THE SAME ORDER, as `VALUE_SOURCES` on the server — and the
// response carries that order in `value_sources` so this is a mirror rather than a guess.
const valuesOf = (node, name) => {
  for (const source of ['attributes', 'qualifiers']) {
    const carried = (node[source] || {});
    if (name in carried) {
      const value = carried[name];
      return Array.isArray(value) ? value : [value];
    }
  }
  return (node.predicates || [])
    .filter((entry) => entry.predicate === name && entry.count != null)
    .map((entry) => entry.count);
};

const diverged = [];
for (const vector of vectors.vectors) {
  // 🔴 `measure` MAY BE A LIST, and `value` is ALWAYS a map keyed by the measure string
  // (S-146-c). One measure does not collapse to a bare number: a cell with two shapes is
  // one the reader has to type-check before using.
  const asked = Array.isArray(vector.measure) ? vector.measure : [vector.measure];

  const groups = new Map();
  for (const node of vector.nodes) {
    const keys = vector.group_by === 'type' ? [node.type] : valuesOf(node, vector.group_by);
    for (const key of keys) {
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(node);
    }
  }
  for (const expected of vector.groups) {
    const members = groups.get(expected.key) || [];
    if (members.length !== expected.n) {
      diverged.push(`${vector.name}/${expected.key}: n ${members.length} != ${expected.n}`);
    }
    const value = {};
    for (const spelled of asked) {
      const [measure, qualifier] = String(spelled).split(':');
      const fold = AGGREGATE[measure];
      if (!fold) { diverged.push(`${vector.name}: client has no measure '${measure}'`); continue; }
      const stream = qualifier
        ? members.flatMap((node) => valuesOf(node, qualifier))
        : members.map((node) => node.id);
      value[String(spelled)] = stream.length || !qualifier ? fold(stream) : null;
    }
    if (JSON.stringify(value) !== JSON.stringify(expected.value)) {
      diverged.push(
        `${vector.name}/${expected.key}: value ${JSON.stringify(value)} != ${JSON.stringify(expected.value)}`);
    }
  }
}

if (diverged.length) report(1, 'DIVERGED', diverged.join(' | '));
report(0, 'agreed', `${vectors.vectors.length} vectors folded identically`);
