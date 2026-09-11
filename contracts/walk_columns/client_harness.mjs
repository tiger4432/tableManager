/**
 * WALK COLUMNS — the CLIENT half, scored against `vectors.json`.
 *
 *   node contracts/walk_columns/client_harness.mjs
 *
 * Exit codes: 0 = the client orders its declared columns the way the contract says
 *             1 = divergence(s)   2 = harness failure
 *
 * Read-only. It never writes to `client2/`.
 *
 * ── WHAT IS SCORED, AND WHAT IS DELIBERATELY NOT ──────────────────────────────────────────
 * One rule, stated by the vectors: for a single type, the DECLARED column names and their
 * order are 「the declaration's `keys`, then the qualifier names the response actually
 * carried, then the declaration's `attributes`」.
 *
 * 🔴 THE TWO HALVES DRAW DIFFERENT SHAPES AND THAT IS NOT A DIVERGENCE. The client returns one
 *    section per type and decorates it with fixed columns whose names are Korean display text
 *    (깊이 · 충돌 · 라벨 · id); the server's `format=rows` is one TSV whose fixed columns are
 *    machine names. The vectors say so themselves, so this harness reads ONLY the columns whose
 *    `kind` is key/qualifier/attribute and says nothing about the rest. Asserting the full list
 *    would be asserting a shape nobody can satisfy on both sides.
 *
 * 🔴 WHY A DECOY DECLARATION RIDES IN EVERY CASE. The node type is bare (`wafer`) and the
 *    declaration key is versioned (`wafer@1`); the vectors carry that asymmetry on purpose,
 *    because a lookup that matched NOTHING would return the fixed columns only and pass every
 *    case whose expectation is short. With a decoy present, 「matched nothing」 and 「matched the
 *    right one」 stop being the same answer — and 「matched the wrong one」 becomes visible too.
 *
 * ⚠️ OVERLAP WITH `walk_node_shape`, NAMED RATHER THAN AVOIDED. That contract scores that
 *    declared attribute NAMES become columns and that a declaration without attributes leaves
 *    the table byte-identical. It does not score the ORDER of the three groups, nor the
 *    undeclared type. Neither can contradict the other: this file reads a subset of the same
 *    answer and pins a property the other one never states.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..', '..');
const DERIVE = join(ROOT, 'client2', 'src', 'walk', 'derive.js');

let pass = 0;
const failures = [];
const ok = (name, cond, detail = '') => {
  if (cond) { pass += 1; console.log(`  PASS ${name}`); } else {
    failures.push(name);
    console.log(`  FAIL ${name}${detail ? ' — ' + detail : ''}`);
  }
};
const eq = (name, want, got) => ok(name, want === got, `want ${want}, got ${got}`);

// ── the vectors, and the module under test ───────────────────────────────────────────────
let vectors;
let derive;
try {
  vectors = JSON.parse(readFileSync(join(HERE, 'vectors.json'), 'utf8'));
  derive = await import(pathToFileURL(DERIVE).href);
} catch (e) {
  console.error(`walk_columns: could not load its own subject — ${e && e.message}`);
  process.exit(2);
}

const CASES = vectors.per_type_declared_columns || [];
if (!Array.isArray(CASES) || CASES.length === 0) {
  console.error('walk_columns: the vectors carry no cases. An empty scan is not a passing contract.');
  process.exit(2);
}
if (typeof derive.tableColumns !== 'function') {
  console.error('walk_columns: `tableColumns` is gone from client2/src/walk/derive.js. '
    + 'That is the finding, not a harness failure to route around.');
  process.exit(1);
}

// 🔴 THE DECOY. Present in every case, never expected in any answer.
const DECOY = Object.freeze({
  type: 'decoy_type@1', keys: ['decoy_key'], attributes: ['decoy_attribute'], class: null,
});
const DECLARED_KINDS = new Set(['key', 'qualifier', 'attribute']);

console.log(`\n[1] the declared columns, per type — ${CASES.length} cases`);
for (const c of CASES) {
  // The declaration list the client reads is the WHOLE declaration, so the case's own entry
  // (when it has one) sits beside a type it must not confuse itself with.
  const entities = [DECOY];
  if (c.declaration) {
    entities.push({
      type: c.declaration_key,
      keys: c.declaration.keys || [],
      // ⚠️ `attributes` ABSENT and `attributes: []` must render identically, so an empty list
      //    is passed through as an empty list rather than being dropped here — otherwise this
      //    harness would be the thing making the two cases agree.
      ...(c.declaration.attributes === undefined ? {} : { attributes: c.declaration.attributes }),
      class: null,
    });
  }

  const columns = derive.tableColumns(entities, c.type, c.qualifiers_present || []);
  const declared = columns.filter((col) => DECLARED_KINDS.has(col.kind));

  eq(`V «${c.name}» declared columns in contract order`,
    (c.expect || []).join(','), declared.map((col) => col.name).join(','));

  // Same list, read as SOURCES rather than names: a column named `mat_id` that reads from a
  // qualifier would draw the right header over the wrong value, and the header alone cannot
  // tell. The contract's three groups are exactly these three kinds.
  ok(`K «${c.name}» ...each reading from the group it belongs to`,
    declared.every((col) => col.key === col.name),
    declared.map((col) => `${col.name}:${col.kind}<-${col.key}`).join(' '));

  const names = columns.map((col) => col.name);
  ok(`D «${c.name}» the decoy declaration is not read`,
    !names.includes('decoy_key') && !names.includes('decoy_attribute'), names.join(','));
}

// ── the sensitivity control, stated as its own line ──────────────────────────────────────
// 🔴 The vectors name `unknown_type_declares_nothing` as the case that separates 「reads the
//    declaration」 from 「invents columns out of the response」. If that case is ever dropped from
//    the vectors, this contract silently stops being able to tell those apart — so its PRESENCE
//    is asserted, not just its outcome.
console.log('\n[2] the control the vectors name');
ok('C1 an undeclared type is still one of the cases',
  CASES.some((c) => c.declaration === null || c.declaration === undefined),
  CASES.map((c) => c.name).join(','));

console.log(`\n${failures.length === 0 ? 'OK' : 'DIVERGED'}: ${pass} passed, `
  + `${failures.length} diverged`);
failures.forEach((f) => console.log(`   x ${f}`));
process.exit(failures.length === 0 ? 0 : 1);
