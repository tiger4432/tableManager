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
  ['reposition_regime_probe.mjs', { ran: 0, failed: 0, namesUnavailable: 'dies before asserting; 0 failure lines emitted (measured 2026-08-06)',
    why: 'throws with ERR_INVALID_ARG_TYPE ― DEAD: a path/arg it reads has moved (and it asserts nothing by design; see its ASSERTIONS 0 0)' }],
  ['split_registry_harness.mjs', { ran: 0, failed: 0, namesUnavailable: 'dies at extraction; 0 failure lines emitted (measured 2026-08-06)',
    why: 'throws at its extraction step ― DEAD: symbols it slices were renamed (known since 2026-07-30)' }],
  ['valid_die_authoring_harness.mjs', { ran: 100, failed: 1,
    failures: [
      "[INV-6] resolveValidDie runs the chain check before projecting the cells",
    ],
    why: 'ATTRIBUTED 2026-08-04 ― this is a HARNESS defect, not a code defect. The slicer '
       + 'matches `projectCellsToPhys` where it first appears in the file, which is inside a '
       + 'COMMENT at offset 8297, ahead of the chain guard\'s real call at 9564. The code '
       + 'order is correct. Same first-match trap the overlay round hit from the other side '
       + '(a mutation string that is not unique lands on the wrong function). Fix belongs '
       + 'with the slicer, not with map_editor.js' }],
  ['valid_die_frame_adoption_harness.mjs', { ran: 228, failed: 41,
    failures: [
      "F6/A(stored==derived)/F8/domain-is-not-empty",
      "F6/A(stored==derived)/F8/frame-untouched",
      "F6/A(stored==derived)/F8/notice-is-info-not-error",
      "F6/A(stored==derived)/F8/notice-says-nothing-changed",
      "F6/A(stored==derived)/F8/notice-shown-exactly-once",
      "F6/A(stored==derived)/F8/stored-coordinates-preserved-total",
      "F6/B(stored!=derived)/F8/domain-is-not-empty",
      "F6/B(stored!=derived)/F8/frame-untouched",
      "F6/B(stored!=derived)/F8/notice-is-info-not-error",
      "F6/B(stored!=derived)/F8/notice-says-nothing-changed",
      "F6/B(stored!=derived)/F8/notice-shown-exactly-once",
      "F6/B(stored!=derived)/F8/stored-coordinates-preserved-total",
      "F6/C/F8/grid-NOT-opened-at-reference-size",
      "F6/C/F8/nothing-became-unaddressable",
      "F6/C/F8/notice-names-both-grids",
      "F6/C/F8/notice-says-nothing-changed",
      "F6/C/F8/offset-notice-announced",
      "F6/C/F8/offset-notice-is-info",
      "F6/C/F8/physical-spec-NOT-adopted",
      "F6/C/F8/screen-position-NOT-re-derived",
      "F6/C/F8/stored-coordinates-preserved",
      "F6/E/F8/frame-untouched",
      "F6/E/F8/no-coordinate-changed",
      "F6/E/F8/notice-shown-exactly-once",
      "F6/E/F8/physical-spec-untouched",
      "F6/E/F8/stored-coordinates-preserved-total",
      "F6/empty-A/F8/grid-NOT-opened-at-reference-size",
      "F6/empty-A/F8/phys-NOT-adopted",
      "F6/empty-A/F8/target-index-space-unmoved",
      "F6/empty-B/F8/grid-NOT-opened-at-reference-size",
      "F6/empty-B/F8/phys-NOT-adopted",
      "F6/empty-B/F8/target-index-space-unmoved",
      "MEDIUM-1/classification-survives-a-designation",
      "O/aligned/alarm-tracks-the-actual-misalignment",
      "O/rot-only/alarm-tracks-the-actual-misalignment",
      "O/specimen/alarm-fired-exactly-once",
      "O/specimen/alarm-is-info",
      "O/specimen/alarm-names-both-origins",
      "O/specimen/alarm-names-the-measured-offset",
      "O/specimen/alarm-tracks-the-actual-misalignment",
      "O/specimen/frame-untouched",
    ],
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
  // New 2026-08-05 with MAP_ALIGNMENT_SPEC layer 7 (verdict) and the payload decoder. Same
  // rule as the other new entries: the floor is the count it reports on the commit that
  // introduces it -- there is no earlier tree to measure it against.
  //
  // 🔴 A LARGE PART OF THIS COUNT IS THE "NEVER RANK BELOW THRESHOLD" RULE AND THE TWO
  //    SECTION-4 CAUSES, scored end to end on real cells. It also pins that an ABSENT
  //    threshold refuses to rank: `Number(null) === 0` was measured turning a missing
  //    `min_margin_dies` into a finite zero, i.e. "always rank", so four separate spellings
  //    of absence are asserted rather than one. A drop here means the screen regained the
  //    ability to crown a candidate it cannot actually tell from its mirror.
  //
  //    Its scoring ORACLE is `client2/tests/oracle/alignment_scoring_oracle.mjs`, in a
  //    subdirectory on purpose: this runner discovers every `*.mjs` directly under
  //    `client2/tests/`, and a library has no ASSERTIONS line to report.
  //
  // 91 -> 124 (2026-08-05, same day). `decode.js` was retargeted to the live server payload
  // and the decoder's expectations moved WITH the wire -- not because the code was wrong.
  // The count rose because the replacements are stronger than what they replaced: the
  // reference-kind INFERENCE was deleted (the wire declares `reference.kind` now), so instead
  // of "guess it and mark the guess" the harness pins that the wire value is read straight
  // through, is never promoted by valued-looking cells, is never invented when absent, and
  // that the retired `KIND_INFERRED` token is unreachable from any payload shape.
  //
  // 124 -> 163 (2026-08-06). Section G: the ruling names an AXIS (`ruling.metric`, which gained
  // `index` this week) and the per-candidate numbers must be read from the pair that axis names
  // -- measured on the live wire reading the occupancy column under an index ruling, so the
  // screen's own conclusion disagreed with the server's on the same payload. The rise also pins
  // the three candidate STATES apart: a frame the side declaration excluded is carried with NO
  // counts rather than with the placeholder zeroes the wire ships beside it, which is what
  // stopped `Number(null) === 0` from entering it into the ranking as a scored zero.
  // 🔴 OFF THE BUILD GATE 2026-08-08 (product owner: 「하네스 무시해」). `db1ee42` replaced the
  //    mirror half of the candidate space with the walk axis, so 8 of the 16 production frame
  //    tuples are no longer reachable BY RULING, and this harness reports that honestly: 6 of
  //    its 163 assertions fail, including a recorded unit whose truth was a reflection. Those
  //    failures are TRUE -- the harness is not broken and its vectors were not edited. It is
  //    off the gate so `npm run build` stops needing `npx vite build` to bypass it, not because
  //    the numbers were dismissed. Run it by hand: `node tests/alignment_verdict_harness.mjs`.
  // ['alignment_verdict_harness.mjs', 163],
  ['availability_gross_marker_harness.mjs', 48],
  ['company_roundtrip_harness.mjs', 84],
  ['coord_table_paste_harness.mjs', 52],
  ['copy_header_count_harness.mjs', 151],
  // Off the debt list 2026-08-04. It had been DEAD for one missing name in its slice list
  // (`pushBlockingCount`), and it is the ONLY harness that runs `pushMapData` end to end --
  // so for as long as that name was missing, the client's single write path had no
  // executable scorer at all. It gets a floor like any other green harness precisely
  // because of how it died: silently, while the debt list recorded it as merely red.
  ['effort_instrument_harness.mjs', 78],
  ['effort_meter_harness.mjs', 131],
  // New 2026-08-05 with the partial-decision-key round (the client asked for NO reference
  // view when ANY key column was blank, so the sweep could resolve a row whose evidence a
  // human could not see). Floor is the count it reports on the commit that introduces it --
  // there is no earlier tree to measure it against.
  //
  // 🔴 ITS LOAD-BEARING HALF IS THE PROHIBITION, NOT THE FEATURE: that the client asks
  //    rather than pre-deciding which views are answerable, and that the refusal text on
  //    screen is the server's `detail` verbatim rather than a sentence composed here. Both
  //    are the two-spellings class -- a client copy stays green against every server test
  //    while the two drift. A floor drop here means one of them stopped being scored.
  //
  // 26 -> 28 (2026-08-05, same day). The reference panel became an AG-Grid, so "what reached
  // the screen" moved from scraping the wrap's innerText to reading what the grid was handed.
  // The count rose because the replacement is stronger than what it replaced: one assertion
  // that the served rows arrived became three -- the rows, the HEADERS (derived from the
  // response, never declared, because the operator writes the SQL), and that the grid was
  // built inside the panel it belongs to.
  ['enrichment_partial_key_reference_harness.mjs', 28],
  // New 2026-08-05 with the round that made BOTH enrichment panels AG-Grid, sorting and
  // filtering in the browser. Floor is the count it reports on the commit that introduces
  // it -- there is no earlier tree to measure it against.
  //
  // 🔴 ITS LOAD-BEARING HALF IS THAT NOTHING ON THIS SCREEN SHOWS A SUBSET SILENTLY. The
  //    worklist buffer is capped (`pageLimit`) while the server reports the whole queue in
  //    `total`, and a client-side sort orders only what arrived. So the count carries both
  //    numbers WHEN THEY DIFFER and says nothing extra when they do not (`G7`), the filtered
  //    count appears only while a filter hides rows (`G8`, both panels), and the panel
  //    overlay never calls a filtered-empty view a finished queue (`G9`). A drop in those
  //    means the screen regained the ability to answer "the top ten" with "the top ten of
  //    whatever arrived" and say nothing about it.
  //
  //    The other half is ONE SPELLING FOR TWO GRIDS (`G1`): both panels spread the same
  //    `GRID_SORT_FILTER_DEFAULTS` and the same `GRID_SHARED_OPTIONS`, asserted by identity,
  //    not by resemblance. Two grids on one screen behaving differently is its own trap, and
  //    a second parallel configuration is exactly what this file's culture keeps paying for.
  ['enrichment_grid_sort_filter_harness.mjs', 45],
  // Floored 2026-08-05, when the queue became a NAMED server predicate and this harness
  // gained the request itself as a target. It had been running unfloored since N36, which
  // the runner had been reporting; the count here is what it reports on the commit that
  // adopts the predicate.
  //
  // 🔴 ITS LOAD-BEARING HALF IS THAT A NUMBER IS READ RATHER THAN COMPUTED. "판단키 없음
  //    N건" used to be remainder minus a keyed total -- a difference of two totals that
  //    existed only because the filter DSL could not express a cross-column OR. Under the
  //    ANY-blank queue those two totals count DIFFERENT populations, which is the N36
  //    shape exactly. The assertion that catches its return is `P4 the count is the server
  //    number verbatim`, and it is the reason this floor is worth defending.
  //
  //    It also carries a SECOND mutation target, `client2/src/enrichment_queue.js`, which
  //    it evaluates as text AND imports, refusing to run if the two disagree. Two of the
  //    other three call sites (`ui.js`, `admin.js`) cannot be imported under bare node at
  //    all, so "all three share one composer" is what stands in for scoring them directly.
  //    A drop here means either the shared composer or the read-not-computed count stopped
  //    being scored.
  ['enrichment_queue_partition_harness.mjs', 41],
  // New 2026-08-05 with the round that made the conveyor's form show what it already knew.
  // Floor is the count it reports on the commit that introduces it -- there is no earlier
  // tree to measure it against.
  //
  // 🔴 ITS LOAD-BEARING ASSERTIONS ARE ABOUT WHAT IS *NOT* SENT. Once the queue predicate let
  //    partly-filled rows stay, the form handed over empty boxes and the save demanded all of
  //    them, so the operator retyped a value already there and the duplicate landed as `user`
  //    (priority 0) -- a machine decision reissued as a human declaration. The checks that
  //    catch its return are `P3 the untouched column is absent from the payload` and `P3 a
  //    hand-typed duplicate of a machine value is NOT written`. `P7` guards the mirror image
  //    on the way back: a locally reflected write carries `priority_source: null` (unread)
  //    rather than the previous writer's name. A drop here means one of those stopped being
  //    scored, and neither failure is visible on screen when it happens.
  ['enrichment_provenance_harness.mjs', 59],
  // New 2026-08-05 with the Excel form gateway (`map2/excel_io.js`). Floor is the count it
  // reports on the commit that introduces it -- there is no earlier tree to measure against.
  //
  // 🔴 IT `import`s ITS TARGET, like `frame_declaration_harness.mjs` and unlike everything
  //    older here. That is the property worth defending: the form's reader/writer has no
  //    module state, so a harness never has to slice its text, so the module's structure
  //    never acquires a veto over refactoring it. A floor drop here means the round trip
  //    stopped being scored in one of its two directions, which is invisible to exit codes.
  ['excel_form_roundtrip_harness.mjs', 306],
  // New 2026-08-05 with MAP_ALIGNMENT_SPEC 0.3 step 1 (the frame becomes a value). Same rule
  // as the other new entries: the floor is the count it reports on the commit that introduces
  // it -- there is no earlier tree to measure it against.
  //
  // 🔴 IT IS ALSO THE FIRST CLIENT HARNESS THAT DOES NOT SLICE SOURCE AS TEXT -- it `import`s
  //    `client2/src/map2/declaration.js`. That matters to THIS file specifically, because the
  //    slicing habit is what the `MODULE_STATE` ceiling below is defending against: a new
  //    module global breaks every harness that slices, so the ceiling and this floor are two
  //    halves of one problem. Most of its assertions are production parity against every
  //    distinct `wafer_map_metadata` shape, so a floor drop here means production coverage
  //    was dropped, not that somebody tidied a test.
  ['frame_declaration_harness.mjs', 4079],
  // 46 -> 62 (2026-08-04). The valid-die COMMIT-GESTURE cases: 🎯 APPLY was deleted because the
  // key control became a real <select>, and the 16 new assertions pin WHICH gesture applies in
  // each of the two controls. The fallback text input (truncated / unavailable / unlisted key)
  // is the reason they exist — typing lives there, and `change` on that input also fires on
  // BLUR, so committing there would restore the exact complaint the deletion answered.
  ['geometry_origin_reseat_harness.mjs', 62],
  // New 2026-08-04 with the isotropic-cell round (equal mm-per-pixel on both canvas axes, so
  // the wafer outline is a circle by construction). Same rule as the entries above: the floor
  // is the count it reports on the commit that introduces it — there is no earlier tree to
  // measure it against. 5 of its assertions are the mutation floor itself.
  // 120 -> 124 (2026-08-04, wafer-anchored scale). The count rose without a new assertion
  // being written: the anchor gives the 700x700 fixture a real margin, so 4 more
  // margin-click probes in ④d actually ran. Raising the floor protects that coverage.
  // 124 -> 152 (2026-08-04, D1). "Auto-registered geometry is not a declaration": the flag,
  // never the chip value, decides. The added assertions are mostly ONE discrimination —
  // an UNFLAGGED chip 1x1 must stay a real 1mm declaration — because that is the only thing
  // separating this from a magic-number sentinel, and 1 is a legal pitch.
  ['isotropic_cell_harness.mjs', 152],
  // New 2026-08-06 with `opts.restoreDraft` (e34d57d, 「맵을 로드하면 로드한 맵이 나온다」).
  // Same rule as the other new entries: the floor is the count it reports on the commit that
  // introduces it. 14 of its assertions are the mutation corpus itself (12 defects + 2
  // controls), scored as assertions rather than printed as prose so a corpus that stops being
  // applied sinks `ran` and BLOCKS.
  //
  // 🔴 IT SCORES THE CANVAS, NOT THE FLAG. The change it protects shipped with the gap named
  //    in its own commit message, and the failure mode is an operator's unsaved edits
  //    vanishing — which leaves an identical exit code, an identical DOM and an identical
  //    server row. So `gridData` is compared KEY BY VALUE against a server set and a draft
  //    set built in the harness and asserted DISJOINT first (section P): a version that
  //    passes `restoreDraft` and restores anyway satisfies every flag-shaped assertion and
  //    fails `A1`. Measured against `e34d57d^` the same file reports 11 failures, so it is
  //    known to be capable of failing on the code it was written for.
  //
  // 🔴 ITS HOST WAS CHOSEN BY MEASUREMENT, and that is the property most at risk here. The
  //    obvious candidate (`valid_die_dirty_guard_harness`) reaches `readRegistryScope` 84
  //    times and the draft function 0 times, and every leg of it carrying CELLS dies in the
  //    load's own catch on `LEGEND_PALETTE is not defined`. This harness therefore refuses to
  //    swallow: any unmodelled global routes to that same catch, and `noSwallowed()` turns it
  //    into a HARNESS FAILURE instead of a green run that measured an empty screen. A drop in
  //    this floor most likely means that guard, or the reachability check in section R,
  //    stopped running — i.e. the file went back to being the thing it was written not to be.
  //
  // ⚠️ SECTION D PINNED A DEFECT AND NOW PINS ITS REPAIR. A plain load used to re-persist the
  //    loaded map's OWN draft slot from the server copy (`if (!staleDraftKept)
  //    saveLegendToStorage()` reached with `staleDraftKept` hard-wired false once the restore
  //    was gated), so 편집 → 📂 로드 → 새로고침 recovered nothing. Repaired 2026-08-06; D1-D3
  //    were INVERTED rather than deleted and the defect is now the mutant
  //    `skipped-restore-reports-not-stale`, so the corpus still carries it.
  //
  // 55 -> 57 (2026-08-06, same day). TWO rises and only ONE is a new assertion.
  //   +1  the repair round added the 12th defect mutant (the persist's removal), which had
  //       been sitting in the corpus as the CANDIDATE repair and became a defect the moment
  //       the repair landed. The floor was never raised for it.
  //   +1  `R4b`, and it exists because that mutant SURVIVED. Deleting the persist on EVERY
  //       path passed this file: `S3` only forbids it on a plain load, and a prohibition with
  //       no matching obligation scores "never" exactly like "only where it is wrong". `R4b`
  //       is S3's positive twin — on the boot-restore path `staleDraftKept` is legitimately
  //       false and the persist is CORRECT, because the draft just replayed onto the canvas
  //       must be re-baselined against the fingerprints THIS load established or the next
  //       refresh rejects the operator's own edits as stale.
  //       🔴 IT ASSERTS THE DRAFT KEY, NOT "a write happened". `map_editor_last_open` is not
  //          a draft slot and must still be written on every load — the same distinction S3
  //          was re-derived to make. Measured: a boot restore writes
  //          `map_doe_draft::bonding_map::LOT_A` AND `map_editor_last_open`; a plain load
  //          writes only the latter. A drop below 57 most likely means one side of that pair
  //          stopped being scored, and neither direction is visible from an exit code.
  ['load_shows_loaded_map_harness.mjs', 57],
  ['m4_symbol_extractability_probe.mjs', 15],
  ['map_key_canonical_harness.mjs', 116],
  // New 2026-08-04 with the marker-shape + wafer-anchor round (the overlay marker follows its
  // cell's own proportions instead of the shorter axis; the wafer, not the grid, anchors the
  // canvas scale). Floor is the count it reports on the commit that introduces it -- there is
  // no earlier tree to measure it against. 11 of its assertions are the mutation floor itself.
  ['marker_shape_wafer_anchor_harness.mjs', 114],
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
  // New 2026-08-05 with Map Editor 2 (MAP_ALIGNMENT_SPEC 0.2 layers 4, 7 and 10, plus the
  // composition root). Floor is the count it reports on the commit that introduces it -- there
  // is no earlier tree to measure it against.
  //
  // 🔴 IT IMPORTS EVERY MODULE IT SCORES, INCLUDING THE COMPOSITION ROOT, which it drives
  //    against a minimal document written inside the harness rather than jsdom -- so it adds no
  //    `node_modules` dependency and slices no source. That is possible only because the
  //    modules take arguments and return values; the moment one of them reaches for a module
  //    global, this harness stops being writable and the slicing habit comes back.
  //
  //    Its load-bearing assertions are the ones that would go quiet first under a refactor:
  //    that seating registers a cell placed far outside any viewport (the legacy off-canvas
  //    `continue` that removed declared cells from the save payload AND from the plan's
  //    numbers), that the renderer paints every seat it is handed at every viewport size down
  //    to 1px, that an absent threshold produces NO ranking instead of a zero-margin winner,
  //    and that no percentage and no bare `0` can reach a count column. A floor drop here means
  //    one of those stopped being scored.
  // 276 -> 408 (2026-08-05). Overdue: the floor had not moved since the harness landed while
  // three rounds added to it, so 25 assertions were already running ungated. The rest is this
  // round, and it is three claims that each cost the operator a day:
  //   K  EXPLORING IS NOT RANKING. `inert` was keyed on the same flag as the numerals, so a
  //      refusal to rank arrived on screen as eight DISABLED controls -- a list of frames the
  //      operator could not open, in the one state where looking is the only move left. Both
  //      directions are pinned: a refused run opens the eight, a FAILED one (no payload, nothing
  //      to look through) still closes them.
  //   L  EIGHT PICTURES. The load-bearing assertion is not "eight canvases exist" -- it is that
  //      the count of DISTINCT pictures equals the count of distinct seatings computed
  //      independently through `computeSeating`. Painting one frame eight times passes every
  //      weaker form of this and is exactly the failure that would waste the operator's day.
  //      L21-L25 exist because the first version of L ran only in `no_winner`: gating the
  //      pictures on `numerals` changed nothing there, so the refused state -- the state they
  //      exist for -- was unmeasured.
  //   M  THE SCREEN SAYS WHY. Five refusals are decided AHEAD of the two threshold checks, so
  //      lowering `min_margin_dies` moves none of them; the operator was reading the code out of
  //      the console. The server's sentence is scored BYTE FOR BYTE, and its absence is scored
  //      too, because a label of ours would be indistinguishable from a real answer.
  // A drop here means one of those three regressed, and none of them is visible from an exit
  // code -- all three were green builds with an unusable screen.
  //   P  THE SCREEN CARRIES THE RULING, ON THE RULING'S OWN AXIS. Driven through `bootstrap`
  //      with the payload the live route served for `dt_map` / `SYN-IDX-FULL-R0`: the server
  //      ruled a winner on the `index` axis and the screen said `채점 불가` over the OCCUPANCY
  //      column, while the four frames the side declaration excluded rendered as `0 / 0` marked
  //      scored. `setConfig` is deliberately NOT called in that block, because
  //      `loadAlignConfig` rejects unconditionally on every live run -- a drop here means the
  //      screen went back to reaching its own conclusion about someone else's evidence.
  // 456 -> 463 (2026-08-06, one-action confirm). The arming step was removed by product owner
  // ruling, and the assertions that pinned it were RE-POINTED rather than deleted -- so this
  // is not seven new tests, it is the same seam scored where it now lives, plus the guards the
  // removal made load-bearing.
  //   🔴 THE FOUR THAT MATTER ARE `G26`, `G26b`, `G26c` AND `G27`, AND THEY EXIST BECAUSE A
  //      COUNT COULD NOT SEE THE DEFECT. Enter on a focused <button> also fires a native
  //      `click`, and the shell binds both `click` and a document keydown to `onConfirm`: one
  //      keystroke, two POSTs. One POST and two POSTs leave an identical session, an identical
  //      DOM and an identical server row, so every end-state assertion in the file passes
  //      either way. Worse, MEASURED BY MUTATION: there are THREE overlapping guards
  //      (`preventDefault`, the in-flight flag, the disable-on-repaint) and deleting any ONE
  //      of them still leaves the write count at 1, because the other two swallow the native
  //      click. A single "exactly one write" assertion therefore scores the STACK and would
  //      keep passing while two thirds of it rotted. Each guard now has its own assertion that
  //      dies alone. A drop here means one of the three stopped being scored individually.
  //   `G27` pins `bar.actions === 4` EXACTLY rather than `<= 6`. The bound could not have
  //      noticed the arming being removed (5 -> 4) and could not notice it coming back.
  // 463 -> 476 (2026-08-06). The refused-confirmation path: ten server refusals used to be
  // discarded by the confirm's `.catch`. G29-G35 score that the SERVER'S sentence reaches the
  // screen byte for byte, H9-H10 that the write carries the top-level `state`, H11-H14 that the
  // transport lifts the sentence out of FastAPI's envelope. A drop here means a confirmation
  // can fail silently again, which is the state this round found it in.
  // 476 -> 486 (2026-08-06). The PROVISIONAL RANKING marker. The server now ranks when the
  // thresholds are undeclared instead of refusing, substituting 1/1 and saying so on the ruling.
  // 🔴 THE DANGER IS THAT IT COSTS THE CLIENT NOTHING TO GET WRONG: `ruling.min_*` arrive
  // non-null, so the client's verdict layer reproduces the same winner and draws the same
  // confident badge with no client work at all -- while the field that says the bar was invented
  // sits in a payload nobody forwarded, because `adaptPayload` is a hand-written literal.
  // G36-G45 score the sentence BYTE FOR BYTE (a word of ours would pass a looser check), the
  // caution tone, and the three-state absent/empty/non-empty distinction. A drop here means the
  // screen can claim more authority than the server does.
  // 486 -> 493 (2026-08-06). THE DISCLOSURE AT THE WRITE. G46-G52: the confirm note carries the
  // provisional mark, leading, with the flag beside the word -- and the control stays ENABLED.
  // 🔴 G48 PINS AN ARGUMENT, NOT A BEHAVIOUR, AND THAT IS WHY IT IS HERE. Refusing on the
  // client what the server accepts would be a second scoring implementation wearing the clothes
  // of a safety feature; the default changes WHICH ranking may be claimed, not which candidate
  // wins. A future round that "hardens" this by disabling the button goes red and has to
  // re-argue it. G52 pins the other half: `WORDS.provisionalRanking` is a TRUNCATION of the
  // server's sentence, admissible only while the full sentence is on the same screen.
  // 493 -> 501 (2026-08-06). THE OVERLAY'S PLACEMENT. `decode` did not keep
  // `candidates[].shift`, so the offset never reached `computeSeating` and the picture was
  // drawn at (0,0) whatever the server placed it at -- the counts beside it measured at one
  // position, the picture drawn at another.
  // 🔴 G54/G57 ASSERT THE DRAWING, NOT THE PLUMBING, and that distinction is the reason this
  // entry exists: a test that checks the field arrived passes a version that receives it and
  // paints at zero anyway. The fixture offsets the source cells by exactly the shift, so an
  // applied offset empties the mismatch layers and a dropped one fills them with all four.
  // G58 is the NEGATIVE CONTROL -- without a placement the same four cells miss, so G54 cannot
  // pass on a fixture that happened to overlap. That accident is precisely what hid this bug:
  // the old shift search broke ties toward the origin, returned (0,0) on a saturated map, and
  // agreed with a client that applied nothing.
  // 501 -> 509 (2026-08-06). Section K gained the rank picture on the UNSCORABLE screen -- the
  // one the operator is actually stuck on, and therefore the one the diagnostic exists for. The
  // rise is the assertion that the toggle has a visible consequence there, scored on the FILLS
  // (ranks 1 and 2 must land close, 1 and 40 far apart) rather than on the ranks arriving.
  // 540 -> 544 (2026-08-06). The seat is the server's, not a recomposition. Three fixtures here
  // predated `placement` and modelled a wire that no longer exists; G58 had become a green proxy
  // -- with nothing drawn, "0 misses" passed vacuously -- and now varies the SEAT instead of
  // stripping it.
  // 544 -> 560 (2026-08-07). Section R: THE SET-UP ROW RE-ASKS THE REQUEST IT CHANGES. The 대상
  // 테이블 control changed the column pickers and never re-issued `/worklist`, so the rows and
  // their map counts still belonged to the previous table -- two tables on one screen, with
  // nothing saying which was which. R0 is the worthlessness check (the two fixtures must paint
  // different counts), R2c is the symptom itself (191/1 giving way to 40/6), and R5b scores the
  // supersession as an ABORT rather than as an end state. R3/R3b are the negative controls: the
  // 기준 and column controls must NOT re-ask, which is the route's contract and not symmetry.
  ['map_editor2_shell_harness.mjs', 560],
  //
  // THE SEAT ITSELF. Scores that the screen draws where the server says it seated the map,
  // rather than recomposing `seatOf(frame) + shift` from a frame it built out of absent fields.
  // The old rule displaced 232 of 312 rendered cells: front frames cancelled by accident
  // (`b = (0,0)`, `linear = I`, so the error is `anchor_src - reference_top_left`, zero on a full
  // map) while the mirrors flipped the sign of the anchor term against an unmirrored `b`, and the
  // quarter turns were not translations at all.
  // 🔴 C1 IS THE WORTHLESSNESS CHECK -- it requires the fixture to move a non-zero number of cells
  // between the defective and repaired seats, so a fixture that stops activating the defect goes
  // RED rather than passing vacuously. The condition that makes the FRONT correct
  // (`anchor_src == reference_top_left`) is part of the fixture on purpose: without it every frame
  // is displaced, the front/back split the operator reported vanishes, and the harness measures a
  // different defect than the one that was filed.
  ['map2_placement_seat_harness.mjs', 42],
  //
  // THE SET-UP QUESTION. Scores that the screen's three parameters -- table, coordinate
  // columns, reference floor -- are held as ONE primitive tuple that cannot express an invalid
  // combination; that a `fallback_guess` binding is marked as a guess and refuses to underwrite
  // the single write; that an answer the wire cannot attribute to a column pair is NOT rendered
  // under one; that occupancy-only evidence is named with the word the system already has; and
  // that the worklist's badges report the SERVER'S totals rather than the rows on the page. A
  // floor drop here means one of those stopped being scored.
  // 149 -> 191 (2026-08-05). Not this round's work: the floor simply had not been raised since
  // the harness landed, so 42 assertions added by later rounds were running ungated. Raised to
  // what the tree reports so that coverage is protected too.
  // 191 -> 192 (2026-08-06, one-action confirm). One assertion, and it is a PRECONDITION: the
  // Enter-guard block asserts that a keystroke in a dropdown confirms nothing, and a confirm
  // earlier in the same block had already set the acknowledgement -- so the check was scoring a
  // stale state and would have passed, or failed, for reasons unrelated to the dropdowns. The
  // new line clears it first and says so. A drop here means the guard block went back to
  // asserting something it had not established.
  ['map_editor2_question_harness.mjs', 192],
  //
  // ⚠️ ITS `H4` NO LONGER PINS THE DECISION UNIT. `api.js` retargeted `loadReferenceView` to a
  //    rule/map_table key, so the assertion that the reference view is keyed by (eqp, product)
  //    was replaced with the weaker "exactly one request" claim, which is what the 30-second
  //    switchover bar actually rests on. That is a deliberate, reported downgrade awaiting a
  //    seam judgement -- not a coverage loss to be baselined away. If the unit is restored,
  //    restore the stronger assertion and raise this floor.
  // New 2026-08-04 with 📐 규격만 저장 (`saveMapSpecOnly`), the metadata-only write path, so its
  // floor is the count it reports on the commit that introduces it. It is the only scorer of
  // a write that must touch NO cells: its central assertions name the ENTIRE request list, and
  // the stranded-cell count in the confirm is checked against an independent set-difference
  // oracle rather than against a number the code produced.
  // Raised 36 -> 59 on 2026-08-04 with the response-bound round: the PUT had no timeout, so a
  // hung response stranded the button on "Saving..." forever while the write had already
  // landed, and the catch block told the operator nothing was recorded.
  ['map_spec_only_save_harness.mjs', 72],
  // New 2026-08-05 with the Map Editor 2 authoring modules (`brush.js`, `legend.js`,
  // `authoring.js`), so its floor is the count it reports on the commit that introduces it --
  // there is no earlier tree to measure it against.
  //
  // 🔴 ITS LOAD-BEARING SECTION IS `A`, AND IT SCORES THE FIXTURE RATHER THAN THE CODE. The
  //    frames it uses must be anisotropic, decentred and y-inverted, because an isotropic chip
  //    hides a pitch swap and a `minC == 0` box hides a dropped box term ENTIRELY -- a green
  //    run on such a fixture measures nothing. Section B then compares the brush's enumeration
  //    against `computeSeating` KEY BY VALUE and reports how many seats a deliberately wrong
  //    frame moves; if that number were 0 the agreement would be evidence of nothing.
  //
  //    A floor drop here means one of those stopped being scored, or that the save gate lost a
  //    precondition. The gate's preconditions are not preferences: `replace_map` on a partial
  //    or unknown read deletes what it did not see, and a valid-die map is the floor every
  //    consumer of that reference reads its coordinates against.
  ['map2_authoring_harness.mjs', 140],
  // New 2026-08-05 with the borrowed wafer geometry, so its floor is the count it reports on
  // the commit that introduces it -- there is no earlier tree to measure it against.
  //
  // 🔴 WHAT A DROP HERE WOULD MEAN. The server can score a spec-less source map by borrowing the
  //    reference floor's wafer dimensions, and it defaults that OFF because "these two maps are
  //    the same wafer" is a claim the OPERATOR is entitled to make. Most of this count is that
  //    one sentence, scored from four sides: nothing sends the flag by default (truthy junk does
  //    not unlock it either), accepting is one click and one re-ask, the claim does not latch
  //    across rows or across a change of floor, and a result reached that way is visibly
  //    distinct from one reached on a declaration. A drop means the screen regained the ability
  //    to assume silently -- to show a confirmed alignment whose geometry was borrowed without
  //    saying so, which is a manufactured declaration on the layer the bonding plan rests on.
  // 101 -> 87 (2026-08-06). A FLOOR DROP THAT IS NOT A COVERAGE DROP, and the distinction is
  // the whole reason this line carries prose. The product owner ruled that the borrowed-wafer
  // assumption applies automatically, so the accept control was removed -- and 15 assertions
  // that scored THE ACT have no successor because the act no longer exists. They are named one
  // by one in the harness itself rather than absorbed here:
  //   C1 C2 C3  accepting sets the claim / re-asks / drops the previous answer
  //   D5        a value column does not clear the claim
  //   G4        an offer is not painted as a warning (the `available` state cannot occur)
  //   G5 G6 G9  accepting costs one fetch / the request carries it / the control then hides
  //   H5..H11   the whole "pick the floor, then accept" second motion
  // 4 replaced them (D1a G3b G7b G7c), and two are STRICTER than what they replaced: G7b/G7c
  // pin the server's sentence BYTE FOR BYTE where G2 only checked it contained the floor id.
  //
  // 🔴 WHAT MUST NOT DROP FURTHER IS THE DISCLOSURE HALF. Removing consent did not remove
  // notice: `data-me2-assumed`, the verbatim server sentence, the caution tone and the write's
  // own disclosure are all still scored, and they are now reached WITH NOBODY PRESSING
  // ANYTHING. A drop below this floor most likely means one of those went, which is the change
  // that turns "automatic" into "silent".
  ['map2_geometry_assumption_harness.mjs', 87],
  // New 2026-08-06 with the rank picture (the serpentine index painted as a spectrum). Floor is
  // the count it reports on the commit that introduces it -- there is no earlier tree.
  //
  // 🔴 THE ASSERTION IN HERE THAT MUST NEVER BE DELETED IS THE NEGATIVE CONTROL (`D1`): the
  //    eight candidate frames must produce eight DISTINCT orientation signatures. The first
  //    oracle written for this feature scored one value for all eight and looked green, because
  //    the eight frames are ISOMETRIES of the stored lattice and every adjacency-based statistic
  //    is invariant under them. `D3` pins that blindness deliberately, so a later round cannot
  //    quietly start reading a local colour break as a frame fault -- a break is a statement
  //    about the DATA (a renumbering, a gap, a clipped pool), never about the frame.
  //
  // 🔴 SECTION B RUNS A MONOTONE RAMP AND REQUIRES IT TO FAIL. That is what stops this being
  //    "simplified" back into a gradient: a gradient's local contrast is inversely proportional
  //    to N (measured: turbo's jump-of-ten falls from 20.24 dE00 at N=88 to 1.26 at N=1313) and
  //    most reference floors in this database are far above where it dies. If B ever passes,
  //    the cyclic period has been removed and nothing else on the screen would say so.
  ['map2_index_ramp_harness.mjs', 94],
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
  // 15 -> 34 (2026-08-05, the first import-not-slice conversion). It stopped reading
  // `map_editor.js` as text: Gate 4 moved to `client2/src/push_columns.js` and this harness
  // now `import`s it. Two things happened to the count, and only one of them is new coverage.
  //
  // 🔴 18 OF THE 34 ARE MUTATION VERDICTS, AND THEY ARE COUNTED HERE ON PURPOSE. This harness
  //    had NO mutation corpus at all, so its 15 green assertions had never been shown to be
  //    capable of failing. The 16 defect mutants and 2 controls are now scored as assertions
  //    rather than printed as prose, which puts them under this floor -- a corpus that stops
  //    being applied sinks `ran` and BLOCKS. That is the direct answer to what happened to
  //    `frame_declaration_harness.mjs` the same week: its corpus sat behind `--mutate`, the
  //    gate runs every harness BARE, and a stale anchor left it dead with the build green.
  //    Anything put behind a flag here is a thing this runner does not run.
  //
  //    The 16th behaviour assertion is the roster named MEMBER BY MEMBER. A count would stay
  //    green while a member was swapped, and a member is exactly what protects a column.
  ['push_gate_harness.mjs', 34],
  ['retroactive_view_harness.mjs', 263],
  ['standard_frame_origin_harness.mjs', 19],
  // New 2026-08-04 with the startup-gate round (the page ran a whole session with no WebSocket
  // and no retry, because `initWebSocket()` was the last statement of `init()` behind two
  // awaited REST calls). Same rule as the other new entries: the floor is the count it reports
  // on the commit that introduces it — there is no earlier tree to measure it against.
  ['startup_socket_gate_harness.mjs', 103],
  ['startxy_probe.mjs', 75],
  ['undeclared_identifier_harness.mjs', 10],
  // New 2026-08-04 with the back-guard round. A valid-die selection set `frameTouched`
  // NOWHERE, so applying one left the frame marked clean and the next frame pop discarded it
  // in silence — screen fine, value gone. Floor is the count it reports on the commit that
  // introduces it; there is no earlier tree to measure it against. It executes the real
  // listener bodies (sliced out of `initDOMElements`), because a fixture that called
  // `onValidDieRefChanged()` directly would stay green with the `<select>` wired to nothing.
  // 48 -> 73 (2026-08-04, same day, second door). The back guard did not close the path the
  // user reported: 📂 Load Existing Map discards the declaration in its first three
  // statements and asked nothing. The predicate was spelled twice — once in `popMapFrame`,
  // and by omission not at all in the load — so the added cases score ONE shared predicate
  // (`unsavedWorkNotice`) being honoured at both doors, plus what declining must leave
  // untouched and which callers are legitimately non-interactive.
  // 73 -> 95 (2026-08-04): the K leg. The user ruled that the valid-die designation must not
  // be reset until a map carrying its OWN declaration is loaded, and the clear that survived
  // three repair rounds arrives through `resolveValidDie`, not from `loadExistingMap` — so K
  // runs the REAL resolver and scores all three clear sites, one mutant each.
  ['valid_die_dirty_guard_harness.mjs', 95],
  ['valid_die_head_parity_oracle.mjs', 17498],
  ['valid_die_origin_alignment_harness.mjs', 153],
  ['value_suggest_keys_harness.mjs', 94],
  ['virtual_column_render_harness.mjs', 65],
  // New 2026-08-04 with the reconnect-backoff round (the 30s ceiling that left the page dark
  // after a server restart). Same rule as the other new entries: the floor is the count it
  // reports on the commit that introduces it — there is no earlier tree to measure it against.
  ['ws_reconnect_backoff_harness.mjs', 42],
  // New 2026-08-04 with the connect-watchdog round. The reconnect ladder above it is driven
  // entirely by `onclose`, so a socket that enters CONNECTING and never leaves bypassed all of
  // it — the production hang produced exactly 1 attempt and 0 retries. Same rule as the other
  // new entries: the floor is the count it reports on the commit that introduces it.
  ['ws_connect_watchdog_harness.mjs', 39],
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

// ── known-red MEMBERS, not just the count ───────────────────────────────────────
// WHY THIS EXISTS, MEASURED. `failed <= known.failed` is a count check, and a count is a
// proxy for the claim "no NEW failure appeared". On 2026-08-06 a refactor added one failure
// to `valid_die_frame_adoption_harness` (`F6/C/adoption-would-have-moved-every-coordinate`,
// a negative control that had gone inert) and took the harness 41 -> 42. The recorded debt
// happened to say 42, so the count check passed and the regression shipped. It was found
// days later by hand-diffing failure names.
//
// 🔴 A DEBT LIST MUST NOT BE A PLACE DEFECTS CAN HIDE. Pin the MEMBERS. A name that is not
//    on the list blocks, whatever the total is; a name on the list that has gone is reported
//    so somebody re-baselines. This is the same rule this repository keeps relearning under
//    other names -- pin the members, not the count.
//
// EXTRACTION IS VALIDATED, NOT TRUSTED. The harnesses print failures in two shapes, and this
// runner never re-scores prose (the harness's own `ASSERTIONS` line is the only scorer). So
// the extracted name count is CROSS-CHECKED against the harness's own `failed` number: if
// they disagree, the parse is unreliable and the runner says so and blocks rather than
// pinning a set it cannot read. That refusal is the honest outcome -- a half-parsed set would
// silently stop protecting the entries it could not read.
//
// ⚠️ TWO ENTRIES CANNOT BE NAME-PINNED AND THAT IS RECORDED, NOT WORKED AROUND.
//    `reposition_regime_probe` and `split_registry_harness` throw before asserting: measured
//    2026-08-06, both emit ZERO failure lines. There are no members to pin, `ran: 0` is the
//    whole of what can be checked, and they are marked `namesUnavailable` so the gap is
//    visible in the output instead of looking like a pin that passes.
function failureNamesOf(stdout) {
  const out = [];
  for (const line of (stdout || '').split(/\r?\n/)) {
    let m = /^\s*(?:✗|x)\s+(.+)$/.exec(line);
    if (!m) m = /^\s*FAIL\s+(.+)$/.exec(line);
    if (!m) continue;
    const n = m[1].split(':')[0].trim();
    if (!n || /^baseline$/i.test(n)) continue;       // the harness's own summary line
    out.push(n);
  }
  return [...new Set(out)];
}

function knownRedNameVerdict(name, known, run, counts) {
  if (known.namesUnavailable) return { blocked: false, message: '' };
  if (!Array.isArray(known.failures)) {
    return { blocked: true, message: `This entry has no \`failures\` list, so only its count `
      + `is protected and a swapped failure would pass. Add the member list.` };
  }
  const seen = failureNamesOf(run.stdout);
  if (seen.length !== counts.failed) {
    return { blocked: true, message: `parsed ${seen.length} failure name(s) but the harness `
      + `reports ${counts.failed} ― the extraction is unreliable here, so the member pin is `
      + `NOT protecting this entry. Fix the parse or mark the entry \`namesUnavailable\` with `
      + `a reason; do not leave it looking pinned.` };
  }
  const pinned = new Set(known.failures);
  const added = seen.filter(n => !pinned.has(n));
  if (added.length > 0) {
    return { blocked: true, message: `NEW failure(s) not on the recorded list:\n    ― `
      + added.join('\n    ― ') + `\n    A new failure inside an existing red count is exactly `
      + `what this check exists to catch. Fix it, or re-triage the entry deliberately.` };
  }
  return { blocked: false, message: '', gone: [...pinned].filter(n => !seen.includes(n)) };
}

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
  } else if (!ok && known && counts && knownRedNameVerdict(name, known, run, counts).blocked) {
    const v = knownRedNameVerdict(name, known, run, counts);
    blocking.push({ name, run });
    console.log(`✗ ${name}  [BLOCKING] ${said} ― the COUNT is within its recorded debt but the `
      + `MEMBERS are not. ${v.message}`);
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
