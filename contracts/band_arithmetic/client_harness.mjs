/**
 * Runs the CLIENT's band arithmetic against contracts/band_arithmetic/vectors.json.
 *
 * Read-only: it never writes to client2/. The band functions in
 * client2/src/transfer_plan.js are module-private (not exported), and this harness must
 * not change that, so it slices the named function declarations out of the source text
 * and evaluates them in a vm sandbox with a stub for the module state they touch.
 *
 * The harness FAILS LOUDLY on extraction problems. A harness that silently passes when
 * it can no longer find the functions is worse than no harness, because its green result
 * gets cited as evidence that the two sides agree. If the client refactors these
 * functions, this exits non-zero with "could not extract" rather than reporting success.
 *
 * Exit codes: 0 = client matches the contract | 1 = divergence(s) | 2 = harness failure.
 *
 *   node contracts/band_arithmetic/client_harness.mjs
 *   node contracts/band_arithmetic/client_harness.mjs --json
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..', '..');
const VECTORS = join(HERE, 'vectors.json');
const SRC_PLAN = join(ROOT, 'client2', 'src', 'transfer_plan.js');
const SRC_EDITOR = join(ROOT, 'client2', 'src', 'map_editor.js');

function die(msg) {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  process.exit(2);
}

/** Slice `function NAME(...) { ... }` out of source by brace matching. */
function extractFunction(source, name, file) {
  const decl = new RegExp(`(^|\\n)\\s*function\\s+${name}\\s*\\(`);
  const m = decl.exec(source);
  if (!m) die(`could not extract function '${name}' from ${file} — it was renamed, removed, or reshaped. Update this harness deliberately; do not delete the check.`);
  const start = m.index + (m[1] ? m[1].length : 0);
  let i = source.indexOf('{', m.index + m[0].length - 1);
  if (i < 0) die(`found '${name}' in ${file} but no body`);
  let depth = 0;
  for (; i < source.length; i++) {
    const c = source[i];
    if (c === '{') depth++;
    else if (c === '}') { depth--; if (depth === 0) return source.slice(start, i + 1); }
  }
  die(`unbalanced braces while extracting '${name}' from ${file}`);
}

const planSrc = readFileSync(SRC_PLAN, 'utf8');
const editorSrc = readFileSync(SRC_EDITOR, 'utf8');

// ── THE CLIENT RETIRED THE BAND EDITOR (2026-07-28). This file did not become wrong. ──
//
// The panel now edits ZONES (STACK + 1H/MID/TOP), which have no walk at all - a zone's
// layers come from STACK and the presence of its neighbours, not from its position in an
// array. What did NOT change is that `map_split_registry.bands` still holds real plans and
// the SERVER still reads them exactly this way. So `sequence_cases` are not stale: they
// describe a path that still runs on both sides, and pytest
// (`test_band_sequence_arithmetic_matches_the_shared_contract`) still scores all four
// columns against `server/transfer_plan.py`.
//
// On the CLIENT the surviving reader is `bandsToZones`, which walks with `prevTo` to
// migrate a stored band plan into zones. So `prevTo` and `bandToState` stay pinned here.
//
// RETIRED, and asserted GONE below rather than merely unreferenced:
//   `bandTo` · `bandLayers` · `bandTotal` · `bandShare`
// Their layers/total/share coverage did not disappear - it moved to `zoneDemand` in
// contracts/doe_band_rules (`demand_cases`), including a case that pins ceil against both
// round and floor. Asserting their ABSENCE is the point: if one came back it would be a
// second implementation of an arithmetic this project has already seen diverge (saving
// used ceil, display used round, the DB held 34 and the screen said 33).
const RETIRED_CLIENT_FNS = ['bandTo', 'bandLayers', 'bandTotal', 'bandShare'];
for (const name of RETIRED_CLIENT_FNS) {
  if (new RegExp(`(^|\\n)\\s*function\\s+${name}\\s*\\(`).test(planSrc)) {
    die(`'${name}' is back in transfer_plan.js. The band editor was retired on 2026-07-28 and its arithmetic lives in doe_bands.js \`zoneDemand\` now; two implementations of the same layer arithmetic is the divergence this contract exists to prevent. If it is genuinely needed again, wire it here deliberately.`);
  }
}

const pieces = [
  // `bandToState` is the single `to` classifier (blank | ok | invalid); `normalizeBands`
  // calls it across the module boundary and `bandsToZones` reads stored plans through it.
  extractFunction(planSrc, 'bandToState', 'transfer_plan.js'),
  extractFunction(planSrc, 'prevTo', 'transfer_plan.js'),
  extractFunction(planSrc, 'splitMaterialId', 'transfer_plan.js'),
  extractFunction(editorSrc, 'normalizeBands', 'map_editor.js'),
];

// `paintedOf` reads module state (S.counts); stub it so the arithmetic is testable in
// isolation. Everything else above is pure.
const sandbox = { S: { counts: {} }, console };
vm.createContext(sandbox);
try {
  vm.runInContext(`function paintedOf(v){ return Number(S.counts[v] || 0); }\n${pieces.join('\n')}`, sandbox);
} catch (e) {
  die(`extracted sources did not evaluate: ${e && e.message}`);
}
for (const fn of ['bandToState', 'prevTo', 'splitMaterialId', 'normalizeBands']) {
  if (typeof sandbox[fn] !== 'function') die(`'${fn}' did not evaluate to a function`);
}

const spec = JSON.parse(readFileSync(VECTORS, 'utf8'));
const failures = [];
let compared = 0;
const scored = new Set();          // which groups actually contributed assertions
const rec = (group, name, field, expected, actual) => {
  compared++;
  scored.add(group);
  const same = JSON.stringify(expected) === JSON.stringify(actual);
  if (!same) failures.push({ group, name, field, expected, actual });
};

// --- to_cases: the client has no tri-state, so map its null to blank-or-invalid ------
// A single null cannot distinguish blank from invalid. The contract requires only that
// both be SKIPPED by the walk, so for this group we compare the client's value against
// the contract's, treating blank and invalid alike (null). Sequence cases below are what
// actually pin the walk behaviour, and they are where the divergence shows.
//
// AMBIGUOUS INPUTS. Two vectors can carry different JSON numbers that collapse to the same
// JS double (anything past 2^53 — JSON.parse('9007199254740993') === 9007199254740992).
// The client receives `bands` as JSON text and parses it the same way, so it physically
// cannot tell such vectors apart: no function returns two answers for one argument. That is
// a transport limit, not a client defect, and it is not fixable on this side. Such groups
// are listed instead of scored — and the detection is DERIVED (same parsed input, differing
// expectations), never a name-based exemption, so a vector that becomes representable
// (e.g. restated as a decimal string, which IS exact here) is scored again automatically.
const unrepresentable = [];
const ambiguous = new Set();
{
  const byInput = new Map();
  for (const c of spec.to_cases) {
    if (!('band' in c)) continue;                        // $comment entry
    const k = JSON.stringify(c.band);
    if (!byInput.has(k)) byInput.set(k, []);
    byInput.get(k).push(c);
  }
  for (const [input, group] of byInput) {
    if (group.length < 2) continue;
    const answers = new Set(group.map(c => JSON.stringify(c.state === 'ok' ? c.value : null)));
    if (answers.size < 2) continue;                      // agreeing duplicates are harmless
    group.forEach(c => ambiguous.add(c.name));
    unrepresentable.push({
      input,
      cases: group.map(c => c.name),
      expected: group.map(c => (c.state === 'ok' ? c.value : null)),
    });
  }
}

for (const c of spec.to_cases) {
  if (!('band' in c) || ambiguous.has(c.name)) continue;
  const expected = c.state === 'ok' ? c.value : null;
  // `bandTo` was the thin wrapper; with it retired the value comes from the classifier
  // itself, which is what the wrapper always returned. Same assertion, one hop shorter.
  let actual;
  try { actual = sandbox.bandToState(c.band).value; } catch (e) { actual = `THREW ${e.message}`; }
  rec('to_cases', c.name, 'to', expected, actual === undefined ? null : actual);
}

// --- sequence_cases: prev_to (+ the state that decides whether the walk stops) --------
//
// `layers` / `total` / `share` are NOT scored here any more, and that is a deliberate
// narrowing rather than a gap: the client no longer computes them from bands at all. The
// server still does, and pytest still scores all four columns of every one of these
// vectors against `server/transfer_plan.py`. On this side the surviving question is the
// one `bandsToZones` depends on - where does band `i` START - and the walk that answers it.
//
// ⚠️ The two sides now consume DIFFERENT SUBSETS of the same vectors. That is the honest
//    state of affairs (one side retired an editor, the other still reads the column) and
//    it is written down here so a later reader does not mistake the narrower client scoring
//    for a contract that quietly lost an axis.
for (const c of spec.sequence_cases) {
  for (let i = 0; i < c.expect.length; i++) {
    const e = c.expect[i];
    rec('sequence', c.name, `[${i}].prev_to`, e.prev_to, sandbox.prevTo(c.bands, i));
    rec('sequence', c.name, `[${i}].state`, e.state, sandbox.bandToState(c.bands[i]).state);
  }
}

// --- normalization_cases: seq identity ----------------------------------------------
for (const c of spec.normalization_cases) {
  const out = sandbox.normalizeBands(c.bands);
  rec('normalization', c.name, 'count', c.expect_count, out.length);
  rec('normalization', c.name, 'seqs', c.expect_seqs, out.map(b => b.seq));
}

// --- normalize round-trip: normalizeBands must not silently rewrite `to` --------------
// DERIVED from to_cases — no new vectors, and it stays honest if to_cases changes.
//
// `normalizeBands` is the client's read/modify/write normaliser: everything loaded from the
// column goes through it and everything saved is re-serialised from its output. The server
// has no equivalent step — it leaves `to` alone and classifies on read — so if the client
// interprets `to` with a SECOND rule here, a value the contract calls invalid gets rewritten
// into a real layer count and saved back. The screen then shows no mistake, because the
// mistake became the data ('0x10' was being stored as 16 this way, before bandTo ever saw
// it; '  ' became 0). The normalization_cases group cannot see this: it only inspects seq
// and count. The invariant: a band's classification must survive normalizeBands unchanged.
for (const c of spec.to_cases) {
  if (!('band' in c) || ambiguous.has(c.name)) continue;
  const before = sandbox.bandToState(c.band);
  const out = sandbox.normalizeBands([c.band]);
  const after = (out.length === 1)
    ? sandbox.bandToState(out[0])
    : { value: null, state: `DROPPED (normalizeBands returned ${out.length} bands)` };
  rec('normalize_roundtrip', c.name, 'state', before.state, after.state);
  rec('normalize_roundtrip', c.name, 'value', before.value, after.value);
}

// --- material_split_cases ------------------------------------------------------------
for (const c of spec.material_split_cases) {
  if (!c.id && c.id !== '') continue;              // skip the $comment entry
  const got = sandbox.splitMaterialId(c.id);
  rec('material_split', c.name, 'lot', c.lot, got.lot === '' ? null : got.lot);
  rec('material_split', c.name, 'slot', c.slot, got.slot === '' ? null : got.slot);
}

// --- materials_cases: element types of bands[].materials ------------------------------
// The raw string IS the material's identity, so a difference here changes WHICH wafer's
// availability is queried. Read through normalizeBands, which is the client's only path
// from stored JSON to the strings the panel uses.
for (const c of spec.materials_cases) {
  if (!c.name) continue;                           // skip the $comment entry
  const band = { seq: 1, to: 1 };
  if ('materials' in c) band.materials = c.materials;
  const out = sandbox.normalizeBands([band]);
  rec('materials', c.name, 'materials', c.expect, out.length === 1 ? out[0].materials : null);
}

// --- every vector group must actually be scored --------------------------------------
// The ambiguity check above catches an individual vector going unscored. It cannot catch a
// whole GROUP being added to the file and never wired in here — which would be silent, and
// silence is the failure this harness exists to prevent. Any top-level `*_cases` key must
// have contributed assertions, so adding a group without wiring it fails the run.
const scoredGroups = new Set(scored);
const GROUP_TO_LABEL = {
  to_cases: 'to_cases',
  sequence_cases: 'sequence',
  normalization_cases: 'normalization',
  material_split_cases: 'material_split',
  materials_cases: 'materials',
};
const unwired = Object.keys(spec)
  .filter(k => k.endsWith('_cases'))
  .filter(k => !GROUP_TO_LABEL[k] || !scoredGroups.has(GROUP_TO_LABEL[k]));
if (unwired.length) {
  console.error(`HARNESS FAILURE: vector group(s) present but never scored: ${unwired.join(', ')}`);
  console.error('Wire them into this harness, or the contract silently stops covering them.');
  process.exit(2);
}

if (process.argv.includes('--json')) {
  console.log(JSON.stringify({ compared, failed: failures.length, failures, unrepresentable }, null, 2));
} else {
  console.log(`band arithmetic contract — client side`);
  console.log(`  vectors : ${VECTORS}`);
  console.log(`  compared: ${compared} assertions`);
  if (unrepresentable.length > 0) {
    // Printed BEFORE the verdict on purpose: a green result that quietly skipped vectors is
    // the failure mode this whole harness exists to prevent.
    console.log(`\n  NOT COMPARED — ${unrepresentable.length} ambiguous input(s). Distinct JSON numbers that`);
    console.log(`  collapse to one JS double past 2^53. The client cannot distinguish them; the`);
    console.log(`  server (arbitrary-precision int) can and is still pinned by pytest.`);
    for (const u of unrepresentable) {
      console.log(`    to_cases ${u.cases.join(' / ')} — both arrive as ${u.input}`);
      console.log(`        contract expects: ${JSON.stringify(u.expected)}  (one input, two answers)`);
    }
    console.log(`  Restating one as a decimal STRING is exact on both sides and testable here.\n`);
  }
  if (failures.length === 0) {
    console.log(`  result  : MATCHES the contract`);
  } else {
    console.log(`  result  : ${failures.length} DIVERGENCE(S) — the client does not yet meet the contract\n`);
    for (const f of failures) {
      console.log(`    [${f.group}] ${f.name} ${f.field}`);
      console.log(`        contract: ${JSON.stringify(f.expected)}`);
      console.log(`        client  : ${JSON.stringify(f.actual)}`);
    }
    console.log(`\n  These are for map-pm. The server side is pinned to the same file by pytest.`);
  }
}
// An unscored vector FAILS the run. The comment above says a green result that quietly
// skipped vectors is the failure mode this harness exists to prevent — so it must not be
// green. Ambiguity is a defect in the vector file (restate the input so both sides parse it
// exactly), not a licence to drop the assertion.
process.exit(failures.length || unrepresentable.length ? 1 : 0);
