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
  ['reposition_regime_probe.mjs', { ran: 0, failed: 0,
    why: 'throws with ERR_INVALID_ARG_TYPE ― DEAD: a path/arg it reads has moved (and it asserts nothing by design; see its ASSERTIONS 0 0)' }],
  ['split_registry_harness.mjs', { ran: 0, failed: 0,
    why: 'throws at its extraction step ― DEAD: symbols it slices were renamed (known since 2026-07-30)' }],
  ['valid_die_authoring_harness.mjs', { ran: 100, failed: 1,
    why: 'ATTRIBUTED 2026-08-04 ― this is a HARNESS defect, not a code defect. The slicer '
       + 'matches `projectCellsToPhys` where it first appears in the file, which is inside a '
       + 'COMMENT at offset 8297, ahead of the chain guard\'s real call at 9564. The code '
       + 'order is correct. Same first-match trap the overlay round hit from the other side '
       + '(a mutation string that is not unique lands on the wrong function). Fix belongs '
       + 'with the slicer, not with map_editor.js' }],
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
  ['coord_table_paste_harness.mjs', 52],
  ['copy_header_count_harness.mjs', 151],
  // Off the debt list 2026-08-04. It had been DEAD for one missing name in its slice list
  // (`pushBlockingCount`), and it is the ONLY harness that runs `pushMapData` end to end --
  // so for as long as that name was missing, the client's single write path had no
  // executable scorer at all. It gets a floor like any other green harness precisely
  // because of how it died: silently, while the debt list recorded it as merely red.
  ['effort_instrument_harness.mjs', 71],
  ['effort_meter_harness.mjs', 131],
  ['geometry_origin_reseat_harness.mjs', 46],
  // New 2026-08-04 with the isotropic-cell round (equal mm-per-pixel on both canvas axes, so
  // the wafer outline is a circle by construction). Same rule as the entries above: the floor
  // is the count it reports on the commit that introduces it — there is no earlier tree to
  // measure it against. 5 of its assertions are the mutation floor itself.
  ['isotropic_cell_harness.mjs', 120],
  ['m4_symbol_extractability_probe.mjs', 15],
  ['map_key_canonical_harness.mjs', 116],
  // 54, not the 53 the overlay branch carried: that branch forked before the datalist
  // harness gained its assertion, and a floor is a minimum — merging the lower number
  // would have quietly un-scored the newer one.
  // 54 -> 83 (2026-08-04). Two lanes raised this floor independently and the merge carries
  // BOTH sets of assertions, so neither branch's number is the floor here: 1-a added 16 (the
  // key control's SHAPE ― <select> only when the list is provably the whole population, text
  // input otherwise ― plus the empty-but-successful wording), and the discovery round added
  // 13 (the candidate list is ordered, and each candidate carries its registered spec as an
  // option label). Taking either branch's figure would have quietly un-scored the other's.
  ['map_key_datalist_harness.mjs', 83],
  // New 2026-08-04 with the offset/origin fix, so its floor is the count it reports on the
  // commit that introduces it — there is no earlier tree to measure it against.
  ['offset_pitch_guard_harness.mjs', 94],
  // New with the N2 round (overlay markers coloured by the overlay cell's own value). Same
  // rule: floor is the count it reports on the commit that introduces it.
  // 70 as of 2026-08-04: A12 (loading an overlay REGISTERS its values, so the colouring this
  // harness already scored stops being inert) added 16.
  ['overlay_value_colour_harness.mjs', 82],
  // New 2026-08-04 with the overlay-provenance round. Floor is the count it reports on the
  // commit that introduces it — there is no earlier tree to measure it against.
  ['overlay_provenance_harness.mjs', 21],
  ['overlay_wafer_mm_harness.mjs', 69],
  ['push_gate_harness.mjs', 15],
  ['retroactive_view_harness.mjs', 263],
  ['standard_frame_origin_harness.mjs', 19],
  ['startxy_probe.mjs', 29],
  ['undeclared_identifier_harness.mjs', 10],
  ['valid_die_head_parity_oracle.mjs', 17498],
  ['valid_die_origin_alignment_harness.mjs', 153],
  ['value_suggest_keys_harness.mjs', 94],
  ['virtual_column_render_harness.mjs', 65],
]);

// ── the ceilings ────────────────────────────────────────────────────────────────
// A FLOOR says "do not measure less than you used to". A CEILING says the mirror thing about
// a quantity we want to shrink: "do not accumulate more than you have". Same protocol, same
// file, opposite direction -- so a baseline is edited in exactly one place either way.
//
// WHAT IS CEILINGED, AND WHY IT IS NOT A CLEANUP PROJECT. R3 through R6 each stopped at
// module-level mutable state in `map_editor.js`, never at file length: `paintLockConfig` had
// 7 reads and 2 writes all inside one cluster and STILL could not be extracted, because its
// second writer was entangled with three other bindings. Cleaning that up is a behaviour
// change that blocks no feature, so it is deliberately NOT scheduled. What is cheap and
// preventive is the half that was missing: the number must not go UP. Three new bindings in a
// quiet week would have been invisible. Shrinking is opportunistic -- a feature round that
// already has a cluster open takes it.
//
// EXCEEDING IS BLOCKING. Coming in UNDER is not a failure and never will be: it is reported
// the way a rising assertion count is, so somebody eventually re-baselines it on purpose.
// Raising a ceiling to make a build pass is the same lie as lowering a floor.
//
// The counting rule lives with the counter (`undeclared_identifier_harness.mjs`, which emits
// `MODULE_STATE <n>`); it is top-level `let`/`var` declarators, per bound name.
//
// ⚠️ 48 INCLUDES TWO BINDINGS ALREADY KNOWN TO BE DEAD -- `tables` and `isMouseDown`. They are
//    boarded, not deleted here, and the round that finally touches their neighbourhood takes
//    them. So the FIRST re-baseline of this number is expected, not a surprise.
// Scope: `map_editor.js` only for now. Whether the other client modules deserve the same
// ceiling is a separate question and should be answered by measuring them, not by assuming.
const CEILINGS = new Map([
  ['undeclared_identifier_harness.mjs', { key: 'MODULE_STATE', max: 48,
    what: 'module-level mutable bindings in client2/src/map_editor.js' }],
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

// ── THE THIRD STATE: "cannot be measured in THIS tree" ────────────────────────
// A harness that needs an installed package (today only the undeclared-identifier check,
// via `rolldown/parseAst`) cannot run in a git worktree, because worktrees get no
// `node_modules`. Reporting that as BLOCKING is not strict, it is BLIND: every worktree
// lane then starts red before touching anything, so the gate number cannot move no matter
// what that lane breaks, and a real regression hides behind the pre-existing red.
//
// So it gets its own verdict -- not green, not red. UNAVAILABLE is claimable ONLY when the
// dependency store is demonstrably absent AND the failure is specifically module
// resolution. If `node_modules` exists and a harness still cannot resolve an import, that
// is a real breakage and stays BLOCKING: this escape hatch must never widen into one a
// broken harness can climb through.
const HAS_NODE_MODULES = existsSync(path.join(REPO_ROOT, 'client2', 'node_modules'));
const UNRESOLVED_IMPORT_RE = /ERR_MODULE_NOT_FOUND|Cannot find package|Cannot find module/;

const blocking = [];
const unavailable = [];
const stillRed = [];
const recovered = [];
const rose = [];        // ran above its recorded floor ― re-baseline when convenient
const unfloored = [];   // discovered but never baselined ― cannot have regressed yet
const shrank = [];      // came in UNDER its ceiling ― good; re-baseline when convenient

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

  // Floor bookkeeping runs BEFORE the ceiling verdict below, which can `continue`. A harness
  // that breached its ceiling is still a harness whose coverage we want recorded.
  if (floor === undefined && !known) unfloored.push(name);
  if (floor !== undefined && counts && counts.ran > floor) rose.push({ name, was: floor, now: counts.ran });

  // Checked before the ceiling: a harness that could not load did not report a ceiling
  // either, and blaming it for the missing number would be the same blindness twice.
  if (!ok && !counts && !HAS_NODE_MODULES && UNRESOLVED_IMPORT_RE.test(run.stderr || '')) {
    unavailable.push(name);
    // Naming the ceiling is not decoration. The ceiling rides on THIS harness's output, so
    // an unavailable harness is also an unenforced ceiling ― and a ceiling that quietly
    // stops enforcing is how a lane adds module state, sees green, and hits a wall at merge.
    // "Unmeasured" has to say WHAT went unmeasured.
    const lostCeil = CEILINGS.get(name);
    console.log(`? ${name}  [UNAVAILABLE in this tree] needs an installed package and `
      + `client2/node_modules is absent (worktrees do not get one). NOT counted as passing `
      + `― whatever it scores is simply unmeasured here. Re-run it in the main checkout `
      + `before merging this branch.`
      + (lostCeil ? `\n    ⚠ AND THE CEILING RODE ON IT: \`${lostCeil.key} <= ${lostCeil.max}\` `
          + `(${lostCeil.what}) is NOT enforced in this tree. You can add ${lostCeil.what} here `
          + `and still see a green gate; the main checkout will refuse it.` : ''));
    continue;
  }

  // ── the ceiling, if this harness carries one ──────────────────────────────────
  // Read exactly like the ASSERTIONS line: the harness counts, the runner only compares.
  const ceil = CEILINGS.get(name);
  let ceilBreach = null;
  if (ceil) {
    let measured = null;
    for (const m of (run.stdout || '').matchAll(new RegExp(`^${ceil.key} (\\d+)\\s*$`, 'gm')))
      measured = +m[1];
    if (measured === null) {
      // A ceiling whose number stopped arriving is not a pass. It is a gate that went quiet,
      // which is exactly how this directory once went 14/15 unrun.
      ceilBreach = `[BLOCKING] no \`${ceil.key} <n>\` line ― it is ceilinged at <= ${ceil.max} `
        + `(${ceil.what}) and stopped reporting. A silent ceiling is not a ceiling.`;
    } else if (measured > ceil.max) {
      ceilBreach = `[BLOCKING] ${ceil.key} ${measured}, but the ceiling is <= ${ceil.max} `
        + `(${ceil.what}). This number is meant to fall, never rise. Take the new state out, `
        + `or pass it as an argument instead of declaring it at module scope. Raising the `
        + `ceiling to go green is the same lie as lowering a floor.`;
    } else if (measured < ceil.max) {
      shrank.push({ name, was: ceil.max, now: measured, what: ceil.what });
    }
  }
  if (ceilBreach) {
    blocking.push({ name, run });
    console.log(`✗ ${name}  ${ceilBreach}`);
    continue;
  }

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
  + `debt list (${stillRed.length} still red, ${recovered.length} recovered)`
  + (unavailable.length > 0 ? `, ${unavailable.length} UNMEASURED in this tree` : '') + `.`);

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

// The ceiling's mirror of the block above, and it must stay a note for the same reason: this
// number is meant to fall, so falling can never be a failure. It is reported because an
// un-refreshed ceiling still catches a doubling but stops catching the re-accumulation of
// everything that was cleared since it was recorded.
if (shrank.length > 0) {
  console.log(`\n! ${shrank.length} harness(es) came in UNDER their ceiling ― that is the `
    + `direction this number is supposed to move. Not a failure. Lower the ceiling in `
    + `CEILINGS when convenient so the ground gained is also held:\n  `
    + shrank.map(s => `${s.name}: ceiling ${s.was} -> ${s.now} (${s.what})`).join('\n  ') + '\n');
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

// The unavailable set is stated HERE rather than only next to each harness, because this
// last line is the one people quote. "Every gated harness is green" would be a false
// summary of a run where something was never measured at all.
if (unavailable.length > 0) {
  console.log(`✓ every gated harness that COULD run in this tree is green ― but `
    + `${unavailable.length} was not measured here (${unavailable.join(', ')}). This is not a `
    + `green build for those; run the gate in the main checkout before merging.\n`);
} else {
  console.log(`✓ every gated harness is green.\n`);
}
