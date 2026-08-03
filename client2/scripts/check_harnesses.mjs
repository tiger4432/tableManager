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
// EXIT CODE IS THE VERDICT; `ASSERTIONS <ran> <failed>` IS THE EVIDENCE. Exit code alone
// cannot tell "red with N assertions" from "red with 0 assertions": a harness that crashes
// before asserting anything looks exactly like one that ran and failed, and this week that
// disguise hid 3 dead harnesses as known debt. So every harness prints one machine line,
// `ASSERTIONS <ran> <failed>`, sourced from ITS OWN counters (this runner never counts
// check marks or re-scores prose -- the harness's summary is the only scorer). The runner
// reads that line and blocks when:
//   - a harness exits 0 without the line, or with ran=0, or with failed>0 (a green verdict
//     that measured nothing, or that contradicts its own count, proves nothing);
//   - a KNOWN_RED harness runs fewer assertions than its recorded expectation (it stopped
//     asserting -- that is death, not debt), or fails more than recorded (the debt grew).
// A missing line on a KNOWN_RED entry recorded as ran: 0 is tolerated: that entry already
// says out loud that the harness dies before measuring anything.

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
// Each entry records the ASSERTIONS expectation as last measured: `ran` is the floor the
// harness must never sink under, `failed` the ceiling it must never exceed. `ran: 0` is an
// honest confession that the harness dies before measuring anything -- three of these were
// exactly the dead-harness class H1 exists to expose.
//
// `why` CARRIES ONLY WHAT THE MACHINE CANNOT KNOW -- the reason and the triage state, never
// a count. The runner prints the live measurement immediately before it on every run
// (`[known red] (ran N, failed M) <why>`), so a count restated here is duplication of a
// number that is already on screen, and duplication is how it goes stale unnoticed: this
// list said "28 of 228" while the harness had been reporting 42, and the board separately
// printed 41. Whether a harness crashed or merely failed is machine-visible too (`ran > 0`),
// so it does not belong here either. If you want to record how a figure moved, that is what
// git and the round's report are for.
const KNOWN_RED = new Map([
  ['effort_instrument_harness.mjs', { ran: 0, failed: 0,
    why: 'sandbox build crashes (pushBlockingCount is not sliced into the vm context) ― DEAD: never reaches its assertions' }],
  ['reposition_regime_probe.mjs', { ran: 0, failed: 0,
    why: 'throws with ERR_INVALID_ARG_TYPE ― DEAD: a path/arg it reads has moved (and it asserts nothing by design; see its ASSERTIONS 0 0)' }],
  ['split_registry_harness.mjs', { ran: 0, failed: 0,
    why: 'throws at its extraction step ― DEAD: symbols it slices were renamed (known since 2026-07-30)' }],
  ['valid_die_authoring_harness.mjs', { ran: 99, failed: 1,
    why: 'cause not yet triaged ― the failing assertion has never been attributed' }],
  ['valid_die_frame_adoption_harness.mjs', { ran: 228, failed: 42,
    why: 'fixtures holding the pre-da8f390 contract; under triage' }],
]);

// ── the floors ──────────────────────────────────────────────────────────────────
// EVERY harness has a floor, not just the red ones. A GREEN harness that quietly runs
// fewer assertions than it used to is invisible to exit codes AND to the debt list -- it
// passes, so nothing complains, and the coverage it silently stopped scoring is exactly
// what a refactor is most likely to take. That is not hypothetical: the R1 seam extraction
// re-points three harnesses at moved code, `map_key_canonical_harness.mjs` is one of them,
// and it is green. Without this map it could land scoring half of what it scores today and
// the build would say "every gated harness is green".
//
// FLOORS, NOT EXACT MATCHES. A rising count must never require an edit to pass -- adding
// assertions is the thing we want people to do, and a gate that punishes it teaches them to
// stop. Rises are reported (see the re-baseline note at the end of the run) so the numbers
// here get refreshed eventually, but they never block.
//
// KNOWN_RED entries carry their OWN `ran` floor and are deliberately absent here: one
// harness, one place its floor lives. The runner refuses to start if a name appears in both.
//
// Measured on db46525 (HEAD), in a tree materialized with `git archive` -- NOT the working
// tree, which held an in-flight seam extraction whose post-move counts would have been
// baselined as if they were the historical floor.
// `availability_gross_marker_harness.mjs` is new here, so its floor is the count it reports
// on the commit that introduces it -- there is no earlier tree to measure it against.
const FLOORS = new Map([
  ['availability_gross_marker_harness.mjs', 48],
  ['company_roundtrip_harness.mjs', 84],
  ['copy_header_count_harness.mjs', 151],
  ['effort_meter_harness.mjs', 131],
  ['geometry_origin_reseat_harness.mjs', 46],
  ['m4_symbol_extractability_probe.mjs', 15],
  ['map_key_canonical_harness.mjs', 116],
  ['map_key_datalist_harness.mjs', 53],
  ['overlay_wafer_mm_harness.mjs', 69],
  ['push_gate_harness.mjs', 15],
  ['retroactive_view_harness.mjs', 263],
  ['standard_frame_origin_harness.mjs', 19],
  ['startxy_probe.mjs', 29],
  ['undeclared_identifier_harness.mjs', 6],
  ['valid_die_head_parity_oracle.mjs', 17498],
  ['valid_die_origin_alignment_harness.mjs', 153],
  ['value_suggest_keys_harness.mjs', 94],
  ['virtual_column_render_harness.mjs', 59],
]);

const doubleBooked = [...FLOORS.keys()].filter(n => KNOWN_RED.has(n));
if (doubleBooked.length > 0) {
  fail(`${doubleBooked.join(', ')} appear(s) in BOTH \`FLOORS\` and \`KNOWN_RED\`. A harness's `
     + `floor must live in exactly one place ― two copies drift, and the looser one wins by `
     + `accident. Keep the floor on the KNOWN_RED entry while it is debt; move it to FLOORS `
     + `when it goes green.`);
}

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
const rose = [];        // ran above its recorded floor ― re-baseline when convenient
const unfloored = [];   // discovered but never baselined ― cannot have regressed yet

for (const name of harnesses) {
  const run = spawnSync(process.execPath, [path.join(TESTS_DIR, name)],
    { cwd: REPO_ROOT, encoding: 'utf8' });
  const ok = run.status === 0;
  const known = KNOWN_RED.get(name);

  // The harness's own count line; last occurrence wins. Never counted here, only read.
  let counts = null;
  for (const m of (run.stdout || '').matchAll(/^ASSERTIONS (\d+) (\d+)\s*$/gm))
    counts = { ran: +m[1], failed: +m[2] };
  const said = counts ? `ran ${counts.ran}, failed ${counts.failed}` : 'no ASSERTIONS line';
  const floor = FLOORS.get(name);

  if (floor === undefined && !known) unfloored.push(name);
  if (floor !== undefined && counts && counts.ran > floor) rose.push({ name, was: floor, now: counts.ran });

  if (ok && (!counts || counts.ran === 0 || counts.failed > 0)) {
    blocking.push({ name, run });
    console.log(`✗ ${name}  [BLOCKING] exit 0 but ${said} ― a green verdict that measured `
      + `nothing (or contradicts its own count) proves nothing`);
  } else if (floor !== undefined && counts && counts.ran < floor) {
    blocking.push({ name, run });
    console.log(`✗ ${name}  [BLOCKING] ${said}, but the recorded floor is ran >= ${floor} ― it `
      + `is scoring less than it used to. If assertions were deliberately removed or a `
      + `re-pointed harness now covers less, say so and lower the floor on purpose; passing `
      + `while quietly scoring less is the failure this floor exists to make visible`);
  } else if (floor !== undefined && !counts) {
    blocking.push({ name, run });
    console.log(`✗ ${name}  [BLOCKING] ${said}, but it is baselined at ran >= ${floor} ― it `
      + `used to assert and now measures nothing`);
  } else if (known && counts && counts.ran < known.ran) {
    blocking.push({ name, run });
    console.log(`✗ ${name}  [BLOCKING] ${said}, but the recorded expectation is ran >= `
      + `${known.ran} ― it stopped asserting, which is death, not debt`);
  } else if (!ok && known && counts && counts.failed > known.failed) {
    blocking.push({ name, run });
    console.log(`✗ ${name}  [BLOCKING] ${said}, but the recorded debt is failed <= `
      + `${known.failed} ― the debt grew; fix the regression or re-triage the entry`);
  } else if (!ok && known && !counts && known.ran > 0) {
    blocking.push({ name, run });
    console.log(`✗ ${name}  [BLOCKING] ${said}, but the recorded expectation is ran >= `
      + `${known.ran} ― it used to assert and now crashes before measuring anything`);
  } else if (ok && known) {
    recovered.push(name);
    console.log(`✓ ${name}  (${said}; was on the known-red list ― remove it)`);
  } else if (ok) {
    const up = (floor !== undefined && counts && counts.ran > floor) ? `; floor ${floor}, +${counts.ran - floor}` : '';
    console.log(`✓ ${name}  (${said}${up})`);
  } else if (known) {
    stillRed.push(name);
    console.log(`✗ ${name}  [known red] (${said}) ${known.why}`);
  } else {
    blocking.push({ name, run });
    console.log(`✗ ${name}  [BLOCKING] (${said})`);
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

// Rises never block ― see the FLOORS note. They are reported so the floors get refreshed
// eventually: an un-refreshed floor still catches a total collapse, but it stops catching
// the loss of everything added since it was recorded.
if (rose.length > 0) {
  console.log(`\n! ${rose.length} harness(es) now run MORE assertions than their recorded floor. `
    + `Not a failure ― raise the floors in FLOORS when convenient so the new coverage is also `
    + `protected:\n  `
    + rose.map(r => `${r.name}: floor ${r.was} -> ran ${r.now}`).join('\n  ') + '\n');
}

// A harness with no floor cannot have regressed (there is nothing to compare), so this is a
// note, not a failure ― making it blocking would mean adding a harness breaks the build,
// which is how people learn not to add harnesses.
if (unfloored.length > 0) {
  console.log(`\n! ${unfloored.length} harness(es) have no recorded floor and are NOT protected `
    + `against silently scoring less. Add them to FLOORS with the count they report today:\n  `
    + unfloored.join('\n  ') + '\n');
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
