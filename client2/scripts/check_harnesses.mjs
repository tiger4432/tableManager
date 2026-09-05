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

// 🔴 THE EXIT CODE IS THE GATE, AND REMOVING IT IS NOT THE SAME AS MARKING SOMETHING RED.
//    On 2026-08-09 this line lost its `process.exit(1)` so the candidate-axis migration could
//    land, and the cost was measured over the following week: a clean exit proved nothing, so
//    every lane had to hand the Lead PM `✓`/`✗` lines by hand, and 794 assertions that had
//    stopped executing were carried as debt rather than noticed as death. A disabled gate leaves
//    NOTHING TO GREP FOR and reads, from the outside, exactly like a gate that runs.
//
//    `KNOWN_RED` is the marker that exists for this. An entry there is still RUN and still
//    REPORTED and still does not block -- that is the whole design (see the debt-list note
//    below) -- so a migration in flight has a way to say so out loud, in one place, per harness,
//    with a reason attached. Reaching for the exit code instead trades a per-harness statement
//    for a silence covering all of them.
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
// ── NOT HARNESSES ─────────────────────────────────────────────────────────────
// Files under `tests/` that are DIAGNOSTIC TOOLS, not gated checks. They are skipped, and
// the reason is written here rather than left as a permanent red.
//
// 🔴 WHY NOT `KNOWN_RED`. An entry there means "red today, green one day" — it is a DEBT,
//    and something on it is expected to be repaid. A tool that reads `process.argv` and is
//    run by a person will never go green under a runner that passes no arguments, so
//    parking it in the debt list makes the debt list a lie: the count says five are owed
//    when one of them can never be paid.
//
// Measured 2026-09-03: `reposition_regime_probe.mjs:94-95` reads `process.argv[2]` and
// `[3]` as JSON file paths. The runner spawns with no arguments, so it dies in
// `readFileSync(undefined)` before reaching anything. Its own KNOWN_RED note already said
// "asserts nothing by design; see its ASSERTIONS 0 0" — the note described a tool while
// the list it sat in described a test.
const NOT_A_HARNESS = new Map([
  ['reposition_regime_probe.mjs',
    'a manual diagnostic: it takes two JSON file paths on argv (cells, frames) and PRINTS '
    + 'the regime table. It asserts nothing, so there is no verdict for a runner to collect. '
    + 'Run it by hand: node client2/tests/reposition_regime_probe.mjs <cells.json> <frames.json>'],
]);

const KNOWN_RED = new Map([
  ['alignment_verdict_harness.mjs', { ran: 164, failed: 7,
    // These assertions share three scope prefixes (A/C/D0), so the runner's deliberately
    // de-duplicated failure-name parser cannot member-pin them one by one.
    namesUnavailable: 'the failures collapse to three scope labels (A/C/D0)',
    why: 'MEASURED 2026-09-03, and the 2026-08-09 prescription ("rewrite the oracle/fixtures") '
       + 'is backwards: the fixtures are CURRENT and the oracle is one repair behind. Two facts. '
       + '(1) `candidateFrames` copies only rotation and side into the frame and `flatFrame` '
       + 'keeps seven axes without `start`, so the walk start corner that replaced the mirror on '
       + '2026-08-08 never reaches the seater -- 8 candidate ids produce 4 distinct seatings, '
       + 'every candidate ties its twin, and the margin is 0 dies by construction. The server hit '
       + 'this and repaired it (`map_alignment.py` `first_die_of`). (2) 5 of the 7 are ONE '
       + 'fixture, `core_defect_map LOT-A/05`, whose targetMetaTruth is rotation 270 / side back '
       + '/ invert false -- which the harness\'s own alias16 measurement lists among the 8 '
       + 'tuples NO candidate covers. Its recorded truth `rot90_tr` therefore names a candidate '
       + 'that cannot reproduce it, and repairing (1) does NOT turn those 5 green: a start corner '
       + 'moves an anchor (and on the server only in index mode), it is not a mirror. Open ruling '
       + 'with the Lead: either the candidate space regains a way to express a mirrored frame, or '
       + 'that fixture states an unreachable truth and its assertions retire.' }],
  // 163/6 -> 164/7 (2026-09-03). The added assertion is the one that names cause (1) out loud:
  // `A: the oracle emits exactly 8 candidates` counts NAMES (a Map keyed by candidate id, so its
  // size is 8 whatever the frames do) and could never fail. The new one counts distinct SEATINGS
  // and reports 4. It is red on purpose -- it states a defect rather than hiding one.
  // `map_editor2_shell_harness.mjs`, `map_editor2_question_harness.mjs` and
  // `map2_placement_seat_harness.mjs` were here with `ran: 0` from 2026-08-09 to 2026-08-11.
  // Their fixtures were rewritten for the walk-start candidate space and they are back on the
  // gate with floors of their own -- see FLOORS below, which carries what moved and why.
  // `split_registry_harness.mjs` was here from 2026-07-30 to 2026-09-03 with `ran: 0`, and the
  // recorded reason -- "symbols it slices were renamed" -- was only half of it. It sliced
  // FOURTEEN names out of map_editor.js as text. Nine moved or stayed; FIVE were DELETED FROM
  // THE PRODUCT (DEFAULT_LEGEND, loadLegendFromStorage, fetchLegendFromServer, loadLegend,
  // maybeOfferLegendMigration), so no re-pointing could have revived those assertions. Retired
  // with an ABSENCE CHECK in their place, re-aimed on the nine that live, and converted to
  // import. 0 -> 34/0; see FLOORS below.
  // `valid_die_authoring_harness.mjs` was here from 2026-08-04 to 2026-09-03 at 100/1. The
  // attribution was right (a harness defect, not a code defect) and the prescription was not:
  // it read "fix belongs with the slicer". Re-pointing the anchor would have put the red out
  // and left the disease in -- `projectCellsToPhys` appears SEVEN times inside the
  // `resolveValidDie` slice and SIX of them are comments, so any first/last-match anchor is one
  // comment away from being wrong again. The assertion was scoring a RUN order through a TEXT
  // proxy. It now runs the function (probe, [INV-6 §reach]) and the harness is green at
  // 103/0 with its 19 mutants still caught -- see FLOORS below.
  ['valid_die_frame_adoption_harness.mjs', { ran: 241, failed: 13,
    failures: [
      "F6/A(stored==derived)/F8/domain-is-not-empty",
      "F6/A(stored==derived)/F8/stored-coordinates-preserved-total",
      "F6/B(stored!=derived)/F8/domain-is-not-empty",
      "F6/B(stored!=derived)/F8/stored-coordinates-preserved-total",
      "F6/C/F8/nothing-became-unaddressable",
      "F6/C/F8/stored-coordinates-preserved",
      "F6/C/coord/screen-position-unmoved",
      "F6/E/F8/no-coordinate-changed",
      "F6/E/F8/stored-coordinates-preserved-total",
      "F6/empty-A/F8/target-index-space-unmoved",
      "F6/empty-B/F8/target-index-space-unmoved",
      "MEDIUM-1/coord/classification-survives-a-designation",
      "O/aligned/alarm-tracks-the-actual-misalignment",
    ],
    why: 'OWNER RULING 2026-09-03 (ⓐ): a designation adopts the reference PHYSICAL spec and re-derives the grid from it. 228/41 -> 241/13, and every remaining failure is ONE question. Twelve assertions said nothing is adopted: eleven were REPLACED by their inverse (retiring them alone would have left the adoption unscored) and the twelfth was MOVED, because what it scored was whether the CELLS moved. Sixteen scored the wording of a notice that said nothing changed; the notice now names both grids and which one is in use, and the harness selects it by its dedupe key instead of by grepping its text -- pinning wording is what reddened sixteen assertions on a copy edit, none of which was about the sentence. WHAT IS LEFT, AND WHY IT STAYS RED: the ruling settled where the grid comes from, NOT whether a stored coordinate may be re-based when it moves. Measured on fixture A: of 290 painted cells, 224 land where the new frame issues no address and all 66 that remain are the earlier coordinate translated by exactly (0,+8). These are NOT re-aimed to whatever the code produces today -- that would decide the question by writing down the answer -- and their numbers are to be re-measured through an IMPORTED harness before any of it is promoted to a defect, because this file still slices its subject and slicing is wrong in both directions.' }],
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
  // NEW 2026-09-03 with the chain-queue instrument. The count is the one it reports on the
  // commit that introduces it -- there is no earlier tree to measure it against.
  // Most of it is one property: an EMPTY queue (`oldest_waiting_seconds: null`) and a queue
  // that just received something (`0`) must not render the same. The assertions compare the
  // two states AGAINST EACH OTHER rather than against fixed strings, so a copy edit cannot
  // redden them and cannot silently collapse them either. A drop here means the instrument
  // regained the ambiguity it was built to remove.
  // 2026-09-04, 38 -> 71: the card strip became a TABLE (owner: 「kpi 카드 형태 말고」) and
  // rule ④ arrived with it -- a list the route CUT has to say it was cut, because a silently
  // truncated list reads as the whole queue. The two numbers the strip carried (depth, retries)
  // are asserted on the headline, so losing the strip cannot quietly lose them.
  // 2026-09-04, 71 -> 104: the route now names WHO empties each waiting row, and the
  // load-bearing one is that `unknown` must not be counted as `chain`. Reading the queue as
  // one undifferentiated number sent someone to inspect a healthy worker while a scheduler
  // run sat still; the server keeps the buckets apart and a screen that folded them would
  // rebuild that misreading one layer out, with no existing assertion noticing. The
  // `blocked_by` assertions score that the server's own tokens are MOVED, not translated.
  // The NaN/absence class, slice 1 (2026-09-04). Every assertion is scored IN PAIRS -- a
  // missing value beside the genuine 0 it must not become -- because a one-sided test would
  // pass against a function that dashes EVERYTHING, which is the opposite failure. It also
  // pins that chain_queue_panel uses this spelling rather than a private copy: the copy it
  // used to carry rendered an empty string as 0.
  // Phase step (5), 2026-09-04. Two things it exists for, and neither is visible to any
  // other harness: an unreadable translator cursor must NOT render as a list of never_ran
  // -- the server keeps 'could not read' and 'nothing ran' apart on purpose -- and the four
  // states stay four rather than folding into normal/warning/error, because the server never
  // said which of them is bad and a screen deciding that would be inventing a judgement.
  ['ledger_sources_panel_harness.mjs', 62],
  // TABLE CONFIG. The two it exists for: the `base` fingerprint survives the round trip
  // (drop it and two operators editing one file erase each other silently, which is the
  // guard the server made part of the ruling), and a refusal keeps the server's own code,
  // path and sentence rather than a second refusal vocabulary written here.
  ['table_config_panel_harness.mjs', 35],
  // CHAIN RULE. The one this exists for beyond the table's two: a saved rule may not be
  // a RUNNING rule. The server writes a new rule with `enabled: false` because the loader
  // re-reads on reload, so saving would otherwise arm and fire at once - and if the screen
  // does not show that value the operator reads "saved" as "running". Three states, because
  // the list response carries no `enabled` at all and drawing that as `false` would answer
  // a question nobody asked.
  ['chain_rule_panel_harness.mjs', 38],
  ['absent_harness.mjs', 35],
  // THE ZERO THAT LIES. Four tabs each grew their own sentence for "0 but there is work",
  // while the server has shipped a closed list of six absence words that nothing read.
  // This scores the part that draws them: a zero and an unread number are different
  // pixels, the word belongs to zero and not to any other count, and a token this build
  // has never seen survives instead of folding into the six.
  ['count_with_absence_harness.mjs', 27],
  // PROGRESS CARD. An unknown percentage is not zero: a replay can run with no total at
  // all, and a 0% bar claims nothing has happened about something that may be nearly
  // done. The bar is a LENGTH, so with no number it is not drawn and the percent reads
  // as a dash. Also scores that a finished card does not reopen when a late message
  // arrives, and counts the one remaining domain word - the overflow summary - so that
  // a second one turns this red.
  ['progress_card_harness.mjs', 19],
  ['chain_queue_panel_harness.mjs', 104],
  ['company_roundtrip_harness.mjs', 84],
  ['coord_table_paste_harness.mjs', 52],
  ['copy_header_count_harness.mjs', 151],
  // Off the debt list 2026-08-04. It had been DEAD for one missing name in its slice list
  // (`pushBlockingCount`), and it is the ONLY harness that runs `pushMapData` end to end --
  // so for as long as that name was missing, the client's single write path had no
  // executable scorer at all. It gets a floor like any other green harness precisely
  // because of how it died: silently, while the debt list recorded it as merely red.
  ['effort_instrument_harness.mjs', 78],
  // 2026-09-04, 131 -> 133: `graph_viewer.js` and `trace.js` were retired outright, so the
  // two mutants that scored them moved to `admin.js` -- the surviving member of the same
  // class -- and the two route-resolution assertions that named /trace.html now name
  // /admin.html, with two more added so the REMOVAL itself has a scorer: a retired screen
  // must resolve to null rather than to a route id nothing can navigate to.
  ['effort_meter_harness.mjs', 133],
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
  // New 2026-08-11 with the paged `/history` envelope. Same rule as the other new entries: the
  // floor is the count it reports on the commit that introduces it -- there is no earlier tree
  // to measure it against. 12 of its 98 are the mutation corpus itself (10 defects + 2 controls),
  // scored as assertions rather than printed as prose so a corpus that stops being applied sinks
  // `ran` and BLOCKS.
  //
  // 🔴 IT IS THE FIRST EXECUTABLE SCORER `timeline.js` HAS EVER HAD, and the two things it
  //    protects are both invisible to an exit code and to the screen:
  //
  //    · `state.cellRowHistoryData` MUST STAY A PLAIN ARRAY. The endpoint stopped answering with
  //      a bare list, so `state.cellRowHistoryData = await res.json()` now assigns an OBJECT
  //      where `renderTimelineIncremental` and `appendHistoryLocally` call `.unshift()`/`.some()`.
  //      The page renders fine and then every live WebSocket update on the sidebar throws.
  //      Section F pins it by RUNNING those two against the state a real load leaves behind.
  //
  //    · A CAPPED LIST MUST NOT PASS FOR A COMPLETE ONE. `truncated` reaching the screen is the
  //      difference between a slow answer and a wrong one, and `truncated: true` arriving with no
  //      cursor must not paint a control with nowhere to go (A4 makes that state unrepresentable).
  //
  //    Section D drives the paging-reset defect directly -- a 더 보기 issued on row A and resolved
  //    after the operator clicked row B -- across BOTH awaits. D6 exists because deleting the
  //    second session check (after `res.json()`) passes every other case in the file: the status
  //    line has already arrived by then, so the first check cannot see it.
  //
  //    A drop here most likely means one of those stopped being scored, and none of the three
  //    failures is visible from a green build.
  // 98 -> 117 on 2026-08-11 when `/audit_logs/recent` moved from headers to a body envelope.
  // The +19 is section H: the real renderer driven against the envelope, plus the two mutation
  // verdicts. Raised HERE rather than in the lane that earned it, because a floor left at 98
  // leaves the new assertions unprotected — the gate would stay green through their removal.
  // 117 -> 138 on 2026-08-12 when the empty cell tab split into its two real states. The +21 is
  // section I (the row genuinely has no history vs. the records exist and this view cannot show
  // them, the count, the floor wording, and the one-click way to the row tab) plus its four
  // mutation verdicts. Raised in the same lane that earned it: a floor left at 117 would let the
  // gate stay green while the disclosure is deleted and 225,101 rows go back to being told their
  // history does not exist.
  ['history_paging_harness.mjs', 138],
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
  // New 2026-08-13 with the ledger lineage screen (slice 1, layer 3). Floor is the count it
  // reports on the commit that introduces it -- there is no earlier tree to measure it against.
  // 23 of its 171 are the mutation corpus itself (21 defects + 2 controls), scored as assertions
  // rather than printed as prose so a corpus that stops being applied sinks `ran` and BLOCKS.
  //
  // 🔴 ITS LOAD-BEARING HALF IS ONE DISTINCTION: a hop resting on a DECLARED CONVENTION must not
  //    render like one resting on a measurement. The server writes it as `· convention:<name>`
  //    versus `· basis=<name>`, and the ontology owner ruled (2026-08-13) that convention-backed
  //    atoms resolve at class 3 exactly so an operator can see the difference. The naive reading
  //    -- `reason.includes('convention:')` -- is not merely weaker, it INVERTS the answer: a
  //    `candidate` reason names the LOSERS' bases inline, so both contested hops in the probe
  //    fixture contain that substring while the winner of each is a measurement. C4/C5/F9/G12
  //    pin it, and the fixtures are REAL server output (a throwaway `ledger_probe` schema built
  //    from the 878-atom `assy_qa` ledger), not a guess at the reason grammar.
  //
  // 🔴 THE SECOND HALF IS THAT `unresolvable` IS CONTENT. `[no_claim]` and `[root]` are the
  //    product telling the truth about what nobody recorded, so G4/G13 pin that a gap row is
  //    never toned as an error, is never filtered out of the chain, and that an answer made
  //    ENTIRELY of gaps still renders as an answer. Two of the defect mutants (`gap-rows-hidden`,
  //    `gap-rows-toned-as-errors`) are the shapes that would look like a tidy screen.
  //
  // H13/H14 are the COMPLEXITY BUDGET as an assertion: exactly one form control on the page and
  // no buttons. A later round that grows a filter bar goes red here and has to argue for it.
  //
  // 171 -> 276 (2026-08-13, P4 「어떤걸 찾을수 있고 없는지 막연하다」). The product owner ran the
  // shipped screen against a database with no `ledger_events` and got a blank; FOUR unrelated
  // situations painted that same blank (table never migrated / backfill never run / unknown lot
  // / registered lot nobody claimed a parent for). 17 more mutants come with it, and two of them
  // are the load-bearing pair:
  //
  // 🔴 `nothing-ignores-the-ledger-state` IS THE SHIPPED DEFECT. With zero atoms the walk takes
  //    `cur_lot not in lots_with_atoms` for EVERY lot, so an empty ledger answers
  //    `[unknown_subject] … 원장에 원자 0` — byte-identical to a genuinely unknown lot on a full
  //    one. K5/M3 feed the SAME captured trace object two ledger states and demand two different
  //    screens; nothing inside the trace can tell them apart, which is why the answer comes from
  //    `GET /api/ledger/coverage`'s `state` and never from an inference.
  //
  // 🔴 `no-lineage-claimed-on-a-real-root` IS THE INVERSION ON THAT AXIS, the same shape as the
  //    convention/measurement one above: a chain that really walked three generations ALSO
  //    terminates `[root]`, so a rule keyed on the terminal tag alone announces a working answer
  //    as having no lineage. K6/M5 pin it against a real 8-hop capture.
  //
  // K7/K7b are why none of this is read out of prose: same tag + different sentence must give
  // the same verdict, and a `[root]` sentence that reads like an `[unknown_subject]` one must
  // not win. Two mutants (`nothing-ignores-the-ledger-state`, `lineage-step-counts-any-hop`)
  // were caught by a THROW on their first run and were re-armed with tolerant accessors, so
  // each is now caught by the assertion that names it rather than by an exception that aborts
  // the file.
  //
  // 276 -> 291 mid-round, when the server lane's `/trace` refusal turned STRUCTURED
  // (`detail: {reason, state, relation, message}`, ruling R-2026-08-13-C) while this one was in
  // flight. J23-J28 score that reading against the REAL captured 503 body, and J24 is the
  // prohibition itself: `refusalReading({state:'ready', message:'…없음'})` must answer "ready".
  // Mutant `refusal-state-read-from-the-sentence` passes the real capture — whose sentence does
  // contain 없음 — and lies about every other one, which is why the assertion is written from
  // the direction that catches it.
  //
  // 291 -> 319 (2026-08-13, row 3's dead end). The four-nothings round got the SENTENCE right
  // and left one of the four a dead end: an operator who mistypes a lot reads a correct
  // "원장에 없음" and has nowhere to go. K3b's ruling stands — no second sentence about a fact
  // the hops already state — so the way out is the sample list the empty state already offers,
  // read off the coverage body the page already fetched. 3 more mutants, and the interesting
  // half of this entry is what the first run of those mutants measured:
  //
  // 🔴 THE THROW TRAP, RE-ARMED AND RE-CAUGHT. K11-K14 were first written as `nv(...).samples`.
  //    Two mutants (`nothing-ignores-the-ledger-state`, `lineage-step-counts-any-hop`) make
  //    `nothingVerdict` return NULL, so they were reported "caught (threw: Cannot read
  //    properties of null)" — an exception that aborts the file before the assertions meant to
  //    name them ever run. That is the SAME defect this entry already records being fixed once
  //    with `first`/`at`/`kindOf`; `samplesOf` is the third tolerant reader for the same reason.
  //
  // 🔴 AN AMBIGUOUS MUTANT ANCHOR TESTS A DIFFERENT FUNCTION. `way-forward-offered-on-every-
  //    nothing` first anchored on `title: '원장이 비어 있습니다 — 백필 미실행',`, which the core
  //    spells TWICE (`coverageVerdict` and `nothingVerdict`). `String.replace` takes the first,
  //    so the mutation landed where nothing reads a `samples` key and ESCAPED — while the
  //    did-it-apply guard passed, because the source genuinely changed. It is now anchored on
  //    the `detail` line, which is unique to the verdict under test.
  //
  // 🔴 AND ONE NEW ASSERTION CAUGHT ITSELF. M8h was written as `byTag(...,'LI').length === 1`
  //    and read 4 — the sample links are list items too. Both CONTROL mutants were "caught" by
  //    it, which is this file's own signal that a check is broken rather than that a defect was
  //    found. It counts `lt-hop` now.
  //
  // M8g (the way forward renders AFTER the terminal block, because above the chain is where a
  // line reframes the answer) has no mutant in the corpus — one would have to anchor on a
  // comment. It was mutation-tested BY HAND instead: reordering the two appends in
  // `ledger_trace_view.js` turns it red and prints the order it found.
  //
  // 319 -> 380 (2026-08-14, E1 — the client wired to server 5bacdfc). Two contract changes in
  // one: per-hop `basis: {kind, name}`, and `contested` split out of `candidate`.
  //
  // 🔴 THE FIELD IS NOT A CONVENIENCE, IT CLOSES AN INVERSION AND AN IMPOSSIBILITY. The screen
  //    used to read the winner's basis off the reason sentence — which also names the LOSERS'
  //    bases, so both disputed hops in the probe fixture read "assumption" while the winner of
  //    each is a measurement. And no reading of `state` could have replaced it: an undisputed
  //    convention-backed hop is `resolved`, the SAME word a fully measured one gets. C3c/C3d
  //    and N4 score that exact pair; C5c/C5d feed a hop whose sentence and field DISAGREE,
  //    because on real output they never do and no capture can force the choice.
  //
  // 🔴 `contested` REACHED PAST ITS LABEL. `trace()` follows `res.answer`, so a contested
  //    `derived_from` hop MOVED the walk — but `hasLineageStep` was keyed on
  //    `state === 'resolved'` and announced such a chain as having no parentage. It was already
  //    wrong for `candidate`. N7/N8 pin the repair; `lineage-step-keyed-on-the-state-word` is
  //    the mutant.
  //
  // 11 more mutants (44 -> 55). The new fixture, `ledger_trace_contested.json`, is REAL
  // resolver output with NO DATABASE behind it: `contested` needs a cross-class disagreement
  // and the natural ledger has ZERO in 278 hops, so `fixtures/gen_ledger_trace_contested.py`
  // declares the atoms and runs the shipped `trace()` over `InMemoryClaimLookup`.
  // New 2026-08-15 with the independent ledger lineage viewer. Protects response
  // parsing, deterministic radial layout, type/predicate filtering and the page seams.
  // `ledger_graph_harness.mjs` had a floor of 42 here until 2026-08-25. The harness is
  // DELETED, with the screen it measured (`ledger-graph.html`, owner ruling 「ㅇㅇ 버려」).
  // It read `src/ledger_graph/**` and nothing else, so every one of its 42 assertions lost
  // its subject at once -- a floor left behind would be a floor over nothing.
  // `ledger_trace_harness.mjs` had a floor here -- 380, lowered to 360 on purpose the same
  // morning it was deleted. The harness is gone with `ledger_trace_core/view.js`, and those
  // went with admin's 원장 선언 tab (owner: 「안 쓰니까」). A floor outlives its harness by
  // exactly as long as nobody looks, so it leaves in the same commit.
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
  // 🔴 OFF THE GATE 2026-08-09, BACK ON IT 2026-08-11 AT 577. It was moved to KNOWN_RED with
  // `ran: 0` because it died at an ESM import of the retired `SIDE_HEADERS`, and this floor was
  // deleted with it -- so for two days the largest client harness in the tree was scoring nothing
  // and the build said so nowhere. THE CODE WAS NEVER THE DEFECT: `db1ee42` replaced the mirror
  // half of the candidate space with the walk start corner, and the fixtures still spoke
  // `rot*_front/back`. What was repaired, in the harness only:
  //   · the import and section A now read `START_HEADERS` and the `start` axis, and A11b-A11d
  //     pin that the LEGACY `_front`/`_back` spellings still parse and still mean what they meant
  //     (stored confirmations hold them; a screen that stopped reading them shows 선언 없음).
  //   · the document stub authored its eight controls as `front`/`back`, so every
  //     `data-frame-code` lookup missed and a click threw. It authors `tl`/`tr` now, exactly as
  //     `map_editor2.html` does.
  //   · 🔴 SECTION L'S ORACLE MOVED, AND THAT IS THE LOAD-BEARING PART OF THIS REPAIR. It seated
  //     cells through `framesFor`, which reads ROTATION AND SIDE ONLY -- so with every candidate
  //     now `front` it could never tell more than four of the eight apart, and it was scoring a
  //     function that is no longer the drawing path anyway. The oracle now reads the wire's own
  //     `placement`, and L7b/L7c pin WHERE the walk axis lives: the turn in the matrix, the start
  //     corner in `anchor_ref`. If a later round puts the corner back into the linear part, that
  //     is the mirror returning under a new name and those two go red.
  // 560 -> 577 is +17 from those pins (A6b, A11b-A11d, L7b/L7c x4, L14b, L14c); no assertion was
  // deleted, and L14 was re-pointed rather than dropped -- the eight thumbnails no longer share
  // one bounding box, because the normalisation that made them share one also cancelled the
  // start-corner term, so the floor is scored on the floor POPULATION instead of on its pixels.
  // 577 -> 594 (2026-08-11). THE CONFIRM SENTENCE AT ANY ARITY. `3d43a6c` opened arities 1 and 3
  // on the decision key and left the one full sentence on this screen assuming exactly two
  // values; F8b/F8c had PINNED that two-value shape as a contract, so the pin itself was wrong.
  //   F8b-F8l  the unit is a LIST whose length is the rule's, scored at arity 1 / 2 / 3 off a
  //            served `__key`. F8h is the negative control -- three arities must render three
  //            different strings, or the block is scoring one state three times.
  //   S1-S8    the SENTENCE, read off the DOM the shell wrote, plus a hook census on
  //            `map_editor2.html` itself. Both halves are needed: `unitLabel` being right while
  //            the sentence is wrong is a renamed hook, and a stub authoring hooks the page does
  //            not is the third-census trap this tree has paid for twice.
  // 🔴 THE ARITY-2 ASSERTIONS CANNOT DEFEND THIS FLOOR ON THEIR OWN, and that is measured, not
  //    argued: a mutant truncating the unit to two values leaves F8b/F8c/S5 GREEN and is caught
  //    only by the arity-3 and negative-control lines. Same shape as `3d43a6c`'s J41. Seven
  //    defect mutants were applied to the real source (truncate-to-two, ignore the served dict,
  //    prefix the column names, a second separator, a blank rendered as an empty slot, the
  //    markup regrowing an axis hook, the shell not writing the slot) and all seven died with
  //    their ASSERTIONS line printed; a comment-only control stayed green.
  ['map_editor2_shell_harness.mjs', 594],
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
  // 🔴 OFF THE GATE 2026-08-09, BACK ON IT 2026-08-11 AT 60. It died parsing `rot*_front/back`
  // out of `candidateList()`, and its floor was deleted with it. THE SPLIT IT SCORES SURVIVED THE
  // AXIS CHANGE, re-pointed rather than deleted: the operator reported it as front-versus-back,
  // and what it actually is -- the old rule reproducing the shipped seat on EXACTLY ONE candidate
  // and being displaced on the other seven -- is now scored at ONE ROTATION (`rot0_tl` still,
  // `rot0_tr` moves), so the difference cannot be attributed to the turn. B1/B2/B3 kept their
  // numbers and their meaning.
  // 🔴 B3b IS NEW AND IT IS THE STRONGER HALF: the pre-placement rule read rotation and side, so
  // it returns byte-identical seats for BOTH columns of a turn -- it was structurally incapable
  // of expressing the axis, not merely wrong about it. That is `db1ee42`'s server-side defect
  // (all eight shifts measured at `(-13,-11)`) arriving here as its mirror image, and it is
  // asserted as an IDENTITY on the legacy function rather than as an error count, because a
  // count also passes on a version that is wrong in two different ways.
  // ⚠️ THE FIXTURE'S TRUTH MOVED FROM `rot90_back` TO `rot90_tl` and the reference gained a
  // top-RIGHT corner, because the right column anchors there (`map_alignment.py:2113`). A7/A7b/A7c
  // are the guard on that: two columns sharing one `anchor_ref` is exactly the state in which the
  // walk axis does nothing, and A8 requires the eight to seat the map in eight different places.
  // 42 -> 60 is +18 and every one of them is new coverage, not a re-count: A6 (1), A7/A7b/A7c on
  // each of the four turns (12), A8 (1), and B3b on each turn (4). Nothing was removed.
  ['map2_placement_seat_harness.mjs', 60],
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
  // 🔴 OFF THE GATE 2026-08-09, BACK ON IT 2026-08-11 AT 193. It died selecting the retired
  // `rot180_back` out of the candidate control, and its floor was deleted with it. THE REPAIR IS
  // ONE RESPELLING AND NOTHING ELSE -- this harness's stub publishes an EMPTY per-pair grid and
  // lets the shell fill it from `candidateList()`, so the eight controls followed the axis change
  // on their own and only the ids the fixture reaches for had to move. 192 -> 193 is that one
  // assertion which had been added after the floor was last recorded, not new work.
  //
  // ⚠️ ITS `H4` NO LONGER PINS THE DECISION UNIT. `api.js` retargeted `loadReferenceView` to a
  //    rule/map_table key, so the assertion that the reference view is keyed by (eqp, product)
  //    was replaced with the weaker "exactly one request" claim, which is what the 30-second
  //    switchover bar actually rests on. That is a deliberate, reported downgrade awaiting a
  //    seam judgement -- not a coverage loss to be baselined away. If the unit is restored,
  //    restore the stronger assertion and raise this floor.
  //
  // 193 -> 256 (2026-08-11). THE DECISION KEY FOLLOWS THE DECLARATION, AT EVERY ARITY. Sections
  // J/K/L/M, and the defect they close had never worked for anybody: `map_editor2.js` honoured
  // `decision_key` at arity 2 and emitted a hardcoded two-column pair at every other arity, so a
  // deployment whose rule declares ONE column could not confirm a frame at any point in that
  // feature's life. The server's answer to it -- 「빠진 결정키: …」 -- is a true statement about
  // the payload and a misleading one about the cause, which is what made it expensive to find.
  //   J  the composer, at arities 1 / 2 / 3, plus refusal-instead-of-blank and the served dict
  //      read column by column. `J40` is the WORTHLESSNESS CHECK: the defective spelling must
  //      disagree with the repair on every probe here, and `J41` records WHY arity 2 alone could
  //      never have caught this -- the two versions AGREE there. A fixture spelled
  //      `[dt_eqp, product]` scores both versions green.
  //   K  a refusal that declines in SILENCE is indistinguishable from loading. Zero or two
  //      capable rules issue no worklist request at all, and the operator has been reading that
  //      as a broken load; the line now carries how many declared `alignment` and that one is
  //      required.
  //   L  the WIRING census. `map_editor2.js` is a page entry that cannot be imported under bare
  //      node, so it is read as text and asked whether it imports the composer, calls it at both
  //      seams, and names no decision-key column in code OR in prose. Without it the composer
  //      could be perfect and unused.
  //   M  end to end through `bootstrap`: the arity-1 key on the request AND in the write record,
  //      and a key short of a declared column refusing in the confirm slot instead of posting a
  //      blank. `M2b`/`M8` are the non-vacuity guards -- a refusal measured against a dead
  //      button is a green proxy.
  // 🔴 EVERY READ IN M GOES THROUGH A TOLERANT ACCESSOR ON PURPOSE. The defect stops the request
  //    and the write from happening, so `fetches[0]` and `api.lastRecord` are absent on exactly
  //    the runs that must be scored -- and a throw before the ASSERTIONS line reports to this
  //    runner as DEAD, not red. Measured: two of the five mutants did exactly that before the
  //    accessors existed. All five now report `ASSERTIONS 256 <n>` with n > 0.
  // 256 -> 305: sections N..N4 -- the rule chooses the map table (`selection.map_tables`), a
  // refused table carries the server's reason, `derived` stops being folded into
  // `fallback_guess`, an override is visible as one, and a rule pick empties the worklist.
  ['map_editor2_question_harness.mjs', 305],
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
  // Ontology Config Explorer: one-context response, stale-response rejection,
  // navigation restoration and dirty-draft movement decision.
  // 35 -> 43 (2026-08-19). Section E: naming a declaration that does not exist yet. The
  // screen could edit and could not create, so a new source had to be typed into the
  // config by hand. E6-E8 are the counter-tests -- without them a reducer that returns
  // `state` unchanged would satisfy everything else.
  // 43 -> 50 (2026-08-19). Section F: the mirror. F2 is the one that matters -- a picker
  // fed from the paged, search-filtered tree would pass every test where nothing was
  // filtered and go silently short the moment somebody typed.
  // 50 -> 56 (2026-08-19). Section G: an empty config through the whole client path.
  // Four separate places read "there is no selection" as "the selection is wrong" or
  // dereferenced it anyway; every one was found by the owner, not by a test.
  ['ontology_explorer_harness.mjs', 56],
  // New 2026-08-19. The explorer panel committed every state change with
  // `replaceChildren`, which is correct output that destroys the operator's scroll,
  // focus, expand state and half-typed text -- the owner reported it as "refreshed to
  // see the list update and got thrown back to the top". The floor is the count on the
  // commit that introduces it.
  //
  // 🔴 A DROP HERE IS ALMOST CERTAINLY THE COUNTER-TESTS DYING, NOT THE FEATURE. Section F
  // re-runs the OLD `replaceChildren` commit against the same cases and REQUIRES it to
  // fail them. Without F, every survival assertion in A-E is satisfied by a reconciler
  // that does nothing at all, and this harness would have stayed green throughout the
  // defect it exists to prevent.
  // 20 -> 27 the same day: section G. The browser walk found a defect this harness had
  // stayed green through -- an error banner inserted ahead of `.oe-main` renumbered it
  // under absolute-index keying and the tree was rebuilt. Sections A-F all rendered the
  // SAME SHAPE twice, so none of them could shift a sibling.
  ['dom_patch_harness.mjs', 27],
  // New 2026-08-19 with the authoring panels (what one declaration forces, and its
  // ground). Counts are taken INSIDE each bucket element, never off the page, so a
  // legend using the same words cannot satisfy them.
  // 36 -> 41 (2026-08-19). Section F: the fold. B and E now open the row by hand first --
  // they always described the OPENED row, which the screen no longer shows by default.
  // 41 -> 44 on 2026-08-21. The `packs` round rewrote C1-C3 and C8 onto the surfaces that
  // replaced the two `oe-bucket--missing` blocks (the tree row and the map's `is-left`),
  // and added a G block for the binding template the same round introduced. Same four
  // questions, three more answers.
  // NEW 2026-09-03 with the C3 extraction. Two halves, and the second is the durable one:
  // the grid's own query and the EXPORT url must carry an identical narrowing (a drift there
  // hands the operator a file that does not match the screen, silently), and the builder must
  // have exactly FOUR callers with nobody assembling the set by hand. The audit recorded two
  // sites and there were four; the count assertion is what stops a fifth appearing quietly.
  ['narrowing_trio_harness.mjs', 17],
  // 2026-09-04, 44 -> 68: block G scores the two values R1 landed on the server with no
  // reader. Each is checked in THREE states, not two -- true, false, and 'the server did
  // not say' -- because an older build sends neither key and a two-state test passes
  // against a view that reads absent as false. G4 keeps the red result on screen: this
  // round removes the misreading, not the information.
  // 68 -> 79 the same evening: blocks H and I score what R2 landed with no reader.
  // H4 is the load-bearing one -- without the partial_apply line the operator reads
  // 「나머지는 들어가겠지」, which is the promise the server was forbidden to make, so a
  // screen that omits it makes that promise on the server's behalf. H5/H6 hold the two
  // silent states, and I3 holds that a code-less issue draws no code rather than a blank.
  ['ontology_authoring_panel_harness.mjs', 79],
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
  // NEW 2026-09-03 at the count it reports on the commit that revives it -- there is no
  // earlier tree to measure it against, because it scored nothing from 2026-07-30 to here.
  // 6 of the 34 are the absence check standing in for the five deleted subjects, and one of
  // those six is its own control: a name that DOES live must be found by the same scan, or a
  // stripper that emptied every file would make the other five pass silently.
  ['split_registry_harness.mjs', 34],
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
  // 100 -> 103 (2026-09-03) and OFF the debt list. The one text-order assertion became four
  // that RUN `resolveValidDie` through the probe: a chained reference is refused and the cells
  // are never projected, plus the negative control -- with the chain removed the reference is
  // accepted and the projection DOES run, so the zero is a refusal rather than a path nobody
  // walks. Those four are scored once, outside the mutant loop: the mutants edit a slice and
  // the probe imports the real file, so counting them there would score "caught" for a reason
  // unrelated to the defect.
  ['valid_die_authoring_harness.mjs', 103],
  ['valid_die_dirty_guard_harness.mjs', 95],
  ['valid_die_head_parity_oracle.mjs', 17498],
  ['valid_die_origin_alignment_harness.mjs', 153],
  ['value_suggest_keys_harness.mjs', 94],
  ['virtual_column_render_harness.mjs', 66],
  // New 2026-08-21 with the 2b reference-grid paste round. Floor is the count it reports on
  // the commit that introduces it — there is no earlier tree to measure it against.
  //
  // 🔴 THE COUNT INCLUDES ITS OWN MUTANTS AND CONTROLS, and that is the load-bearing part.
  //    Four defects must be CAUGHT (declared column order reversed, the clipboard guard
  //    removed, the alignment comparison reduced to a column COUNT, and the virtual-column
  //    predicate pinned false) and two controls must ESCAPE. A drop here means one of those
  //    stopped being provable — most likely because a source anchor moved, which is exactly
  //    how a mutant goes quietly inert rather than red.
  //
  //    FLOORS, not KNOWN_RED: it lands green. A name in both lists refuses to start.
  ['reference_grid_paste_harness.mjs', 13],
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
  .filter(n => !NOT_A_HARNESS.has(n))
  .sort((a, b) => a.localeCompare(b));

// Named out loud on every run. A file that is skipped silently is a file nobody remembers
// exists, and the next person to read `tests/` cannot tell "deliberately not gated" from
// "forgotten".
for (const [name, why] of NOT_A_HARNESS) {
  if (!existsSync(path.join(TESTS_DIR, name))) {
    fail(`\`NOT_A_HARNESS\` names \`${name}\`, which is not in \`client2/tests/\`. `
      + 'Either it was deleted and this entry should go with it, or it was renamed and the '
      + 'entry now skips nothing.');
  }
  console.log(`  · skipped (not a harness) ${name} — ${why}`);
}

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
