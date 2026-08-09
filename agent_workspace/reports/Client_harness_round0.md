# Client report -- map_editor.js refactoring Round 0: harness prerequisites

- **Agent**: client-pm
- **Date**: 2026-08-04
- **Commit**: `b322267` `test(harness): the oracle gets eyes before the refactor moves anything` (branch `main`, NOT pushed)
- **Scope kept**: no file under `client2/src/` touched, no build run, `dist/` untouched, `git add` by explicit path only. Files: `client2/scripts/check_harnesses.mjs`, all 20 existing `client2/tests/*.mjs`, 2 new test files, `docs/architecture/frontend.md` (one bullet).

## H1 -- ASSERTIONS protocol

### Exact format

Each harness prints, at its own summary point, exactly one line to stdout:

```
ASSERTIONS <ran> <failed>
```

- `<ran>` = assertions actually executed (the harness's OWN counter -- where a harness already had a countable summary, e.g. `baseline: 46 assertions`, that same variable feeds the line; the runner never counts markers or re-scores prose, per the board warning about the 42-vs-41 miscount).
- `<failed>` = failing assertions among them.
- Runner parse: `/^ASSERTIONS (\d+) (\d+)\s*$/gm` over stdout, last occurrence wins.
- All new output is cp949-safe ASCII.

### Runner rules (client2/scripts/check_harnesses.mjs)

`KNOWN_RED` entries changed shape from `name -> prose` to `name -> { ran, failed, why }`: `ran` is a floor, `failed` a ceiling. BLOCKING regardless of debt status when:

| # | condition | verdict |
|---|-----------|---------|
| 1 | exit 0 + no ASSERTIONS line | BLOCKING (green that measured nothing) |
| 2 | exit 0 + `ran = 0` | BLOCKING (same; this is what will catch `reposition_regime_probe` if its crash is ever "fixed" without giving it assertions) |
| 3 | exit 0 + `failed > 0` | BLOCKING (verdict contradicts its own count) |
| 4 | known-red, `ran < recorded ran` | BLOCKING ("it stopped asserting, which is death, not debt") -- applies on the green path too (going green by deleting assertions blocks) |
| 5 | known-red, `failed > recorded failed` | BLOCKING (debt grew) |
| 6 | known-red with `recorded ran > 0`, line missing | BLOCKING (used to assert, now crashes before measuring) |
| 7 | known-red with `recorded ran = 0`, line missing | tolerated still-red (the entry already confesses the harness is dead) |

All rules were scored empirically in a sandboxed copy of the runner with 10 synthetic harnesses (one per rule, plus green/recovered/as-recorded controls); every intended BLOCKING fired and every intended pass passed. Evidence: scratchpad `runner_sbx/`.

### Per-harness ASSERTIONS counts (before = what the old exit-code-only runner knew, after = the measured line)

| harness | before (exit only) | after `ASSERTIONS ran failed` | note |
|---|---|---|---|
| company_roundtrip_harness.mjs | exit 2 | (line at final summary; not reached today) | pre-existing anchor drift, see "found dead" |
| copy_header_count_harness.mjs | exit 0 | 151 0 | |
| effort_instrument_harness.mjs | exit 1 | none -> recorded (0,0) | dead: sandbox crash before assertion 1 |
| effort_meter_harness.mjs | exit 0 | 131 0 | |
| geometry_origin_reseat_harness.mjs | exit 2 | 46 0 (baseline; dies later at mutation step) | pre-existing anchor drift |
| m4_symbol_extractability_probe.mjs | exit 0 | 15 0 | |
| map_key_canonical_harness.mjs | exit 0 | 116 0 | |
| map_key_datalist_harness.mjs | exit 0 | 53 0 | |
| overlay_wafer_mm_harness.mjs | exit 0 | 69 0 | only harness that had NO ran-counter; added one inside its `ok()` (3-line change) |
| push_gate_harness.mjs | exit 0 | 15 0 | |
| reposition_regime_probe.mjs | exit 1 | `ASSERTIONS 0 0` at file end -> recorded (0,0) | measurement probe, asserts nothing by design; see below |
| retroactive_view_harness.mjs | exit 0 | 263 0 | |
| split_registry_harness.mjs | exit 1 | none -> recorded (0,0) | dead: extraction throw |
| standard_frame_origin_harness.mjs | exit 0 | 19 0 | |
| **startxy_probe.mjs (NEW, M1)** | -- | 29 0 | |
| **undeclared_identifier_harness.mjs (NEW, H2)** | -- | 6 0 | |
| valid_die_authoring_harness.mjs | exit 1 | 99 1 -> recorded (99,1) | |
| valid_die_frame_adoption_harness.mjs | exit 1 | 228 42 -> recorded (228,42) | debt prose said "28 of 228"; live measure is 42 (board once said 41). Recorded the measured number with a note in the entry |
| valid_die_head_parity_oracle.mjs | exit 0 | 17498 0 | per-cell parity comparisons + 2 self-vacuity controls |
| valid_die_origin_alignment_harness.mjs | exit 0 | 153 0 | |
| value_suggest_keys_harness.mjs | exit 0 | 94 0 | |
| virtual_column_render_harness.mjs | exit 0 | 59 0 | |

Design note: for mutation-scoring harnesses the line reports the ASSERTION totals; mutation escapes still fail via exit code (a non-known-red exit 1 blocks regardless of the line), so no information is lost and the line stays a single honest number.

## H2 -- undeclared-identifier smoke check

- **File**: `client2/tests/undeclared_identifier_harness.mjs` (matches the `tests/*.mjs` discovery glob; verified discovered -- runner now reports 22 harnesses, was 20).
- **Zero new dependencies**: parses with `rolldown/parseAst` (the oxc parser vite 8 already ships in `client2/node_modules`; no eslint/acorn exist there and none were added).
- **Method**: one parse, two walks. (1) every name declared anywhere in the file (var/let/const incl. destructuring, function/class decls+expressions, params, catch params, imports); (2) every identifier referenced in value position (member property names, object keys, method keys, labels, import/export aliases, new.target/import.meta excluded). Undeclared = referenced - declared - platform-global allowlist. Deliberately file-level (not scope-aware): under-approximates so false positives are zero, which is what lets it BLOCK. Does not execute any product code.
- **Live population at HEAD**: 1148 declared, 1182 referenced, 0 undeclared -- with floors (>= 500 each) asserted so a broken walker cannot report a green nothing, plus a built-in mutant (injected stale ref must be flagged) and negative control (declared local must not be) scored on every run. 6 assertions total.
- **Mutation pair (required evidence)**: scratch copy of `client2/src/map_editor.js`, inserted after the `function pushBlockingCount(u) {` line: `const staleProbe = validDieListCache.has('x');` -> RED, exit 1, output names it exactly: `validDieListCache (first ref at line 3226)`. Restored the copy -> GREEN, exit 0. (Also re-ran the harness itself against both -- `ASSERTIONS 6 1` vs `ASSERTIONS 6 0`.)
- Takes an optional `argv[2]` source path (defaults to the live src), which is what made the scratch-copy proof runnable without touching src.

## M1 -- startxy_probe.mjs landed

- **File**: `client2/tests/startxy_probe.mjs` (probe naming convention, discovered by the runner).
- **Default argument**: `process.argv[2] || <repo>/client2/src/map_editor.js` resolved from the probe's own location. Why meaningful: in-repo its job is guarding the LIVE source on every build; bare `node` under the discovery runner must therefore score exactly the file the bundle is built from. The argument stays so it can still probe other commits (its original differential use).
- **Scored**: the scratchpad version was the read-only diagnostic (0 assertions, exit 0 always -- landing it as-is would have been a harness that can never go red, the exact H1 disease). I converted its six cases into **29 assertions** pinning measured HEAD behavior. The brief said 28; the scored variant with that count was not in the scratchpad, so I re-derived from the live differential -- 29 is the honest count of what I pinned.
- **Differential verification** (required): bare run on live src -> `PASS, ASSERTIONS 29 0`, exit 0. Against `git show aee05b1^:client2/src/map_editor.js` in a scratch copy (never git) -> RED, `ASSERTIONS 29 18` initially, `29 8` after type normalization, failing on exactly the fixed axes:
  - E (spec read HTTP 500): pre-fix degraded to the painted bbox -- start (1,-6)->(5,-1), grid 21x21->8x7, loaded 46 cells, zero toasts; HEAD keeps the declaration, refuses the load (0 cells), toasts once.
  - F (metadata row without start fields): pre-fix left the inputs as the string `undefined`; HEAD preserves the panel (7,7).
  - Case D (counterfactual) proves the axis is live on both versions: forcing start to the bbox moves 41 of 46 cells to a different physical die and would persist a different grid_start.
- One fix during landing: the mock inputs do not coerce assignments to string like real DOM inputs, so value assertions compare `String(el.*.value)` (first bare run showed `"1"` vs `1` false-reds; the pre-fix run stayed red for the real reasons after the fix).

## Verification (whole suite)

`node client2/scripts/check_harnesses.mjs`: 22 harnesses, 17 gated, 5 known-red exactly as recorded (0 recovered), both new harnesses green with counts. Blocking set UNCHANGED from the pre-round baseline I measured first: `company_roundtrip_harness.mjs` and `geometry_origin_reseat_harness.mjs` -- see next section; they were exit-2 before I changed anything.

## Found already dead / pre-existing (not fixed here -- not mine to fix)

1. **Working-tree anchor drift (BLOCKING today, green at HEAD)**: the uncommitted edit to `client2/src/map_editor.js` (in flight, lead PM's `M` in git status) reformatted two spots that mutation anchors match verbatim:
   - `geometry_origin_reseat_harness.mjs` anchor `... || was.invertY !== now.invertY\n      || was.startX ...` -- continuation indent changed 6 -> 4 spaces at src line ~2273.
   - `company_roundtrip_harness.mjs` anchor `return { ok: false, notchVerified: false,` (one line) -- src now wraps it as `return {\n      ok: false, ...` at src line ~7090.
   Both harnesses run their full baselines green (46/0 and all-ok) then exit 2 at the mutation step. I verified both anchors match at HEAD (`git show HEAD:...`). Whoever lands the map_editor.js edit must update these two anchor strings in the same commit, or the build gate stays red. I did NOT add them to KNOWN_RED -- that would be the exact disguise this round exists to remove.
2. **Debt-list numbers were stale**: `valid_die_frame_adoption` entry said "28 of 228 fail"; live measure is 42 (board previously quoted 41). The recorded pair is now the measured (228, 42) with the discrepancy noted in the entry. When the in-flight src edit lands, re-measure; if it returns to 41, the runner notes it (failed below ceiling is not blocking).
3. **The three dead harnesses are now machine-visible as dead**: `effort_instrument` (ReferenceError: `pushBlockingCount` is not defined **in the harness's vm sandbox** -- the symbol exists in src at line 3225; the harness's slicer just does not lift it. NOT an H2 finding), `split_registry` (extraction throw), `reposition_regime_probe` (fs arg TypeError). Recorded as `ran: 0` confessions.
4. **reposition_regime_probe asserts nothing by design** (pure measurement). It now prints `ASSERTIONS 0 0`, so if its crash is ever fixed the runner will refuse the green until it gains real assertions -- intended forcing function, documented in the file.

## Living docs

- `docs/architecture/frontend.md` §2 `check:harnesses` bullet: added the ASSERTIONS-protocol sentence (that bullet is the gate's doc home; its own text forbids re-quoting counts, so I added the rule, not numbers).
- NOT touched (lead-PM-owned or other agents in flight): `PROJECT_STATUS.md`, `docs/history/*` + index, `CODE_MAP.md`, `MAP_EDITOR_SPEC.md`. History draft below.
- Post-commit hook fired a doc-keeper trigger (23 commits accrued, `.claude/doc_sync_pending`); that cycle and the board are yours to schedule.

### History entry draft (for doc-historian at integration)

> **2026-08-04 `b322267` -- the oracle gets eyes before the refactor moves anything.** Round 0 of the map_editor.js refactor ships three harness prerequisites and zero src changes. (H1) Every harness now prints `ASSERTIONS <ran> <failed>` from its own counters and the runner reads it: green-with-nothing-measured blocks, and KNOWN_RED entries carry recorded (ran, failed) pairs so a debt harness that stops asserting blocks instead of hiding -- the exit-code-only runner had let 3 dead harnesses disguise as known debt. (H2) `undeclared_identifier_harness.mjs` parses map_editor.js with the bundler's own parser (rolldown/parseAst, zero new deps) and blocks on any identifier referenced but declared nowhere -- the validDieListCache class that text-slicing harnesses structurally cannot see; mutation-proven red/green. (M1) `startxy_probe.mjs` lands as a 29-assertion scored harness with a bare-run default, guarding aee05b1: declared grid_start wins over the painted bbox, a failed spec read refuses instead of degrading, and it goes red against the pre-fix source on exactly those axes.

## Lessons proposed (for client-pm memory, per protocol)

1. **A harness's exit code is a verdict without evidence** -- before trusting any red or green, read (or add) the harness's own count line; three "known debt" entries here were crashes that had run zero assertions for weeks, and the debt prose (28) disagreed with the live count (42) until measured.
2. **When landing a diagnostic probe as a gate, count its assertions first** -- a probe that prints observations and exits 0 can never go red; landing it unconverted creates a permanent green that measures nothing (startxy was exactly this until scored).
3. **Mock DOM inputs do not stringify like real ones** -- `el.value = 5` stays a number in a test sandbox; assert on `String(value)` or the harness fails green code (10 false-reds on the first bare run here).

## Handoff

- Review + push is yours. `npm run build` not run (dist untouched by instruction).
- When the in-flight map_editor.js edit lands: fix the two mutation anchors (exact strings above), re-run the runner, and re-check the (228, 42) expectation.
- Suggested next rounds (not started): give `reposition_regime_probe`/`split_registry`/`effort_instrument` real repairs or retire them; consider a recorded-floor ledger for GREEN harnesses too (today only KNOWN_RED entries have floors, so a green harness that quietly loses assertions while staying green is still invisible).

---

# Round 0 follow-up -- mutation anchor repair (post-reflow)

- **Commit**: `2664004` `test(harness): repair two mutation anchors the reflow moved, in a form it cannot move again` (branch `main`, NOT pushed)
- **Context**: finding ① confirmed at HEAD. `c0a3715` (formatter reflow) is now permanently in the tree, so both anchor drifts became real reds.
- **Scope**: two harness files only. No `client2/src/` change, no relaxed check, neither harness added to KNOWN_RED, no build, explicit-path `git add`.

## What was stale, and the repair

| harness / mutant | what the reflow did | old anchor | new anchor | reflow-proof? |
|---|---|---|---|---|
| `geometry_origin_reseat` / `orientation-guard-removed` | re-indented one continuation line 6 -> 4 spaces | exact 2-line literal of the whole guard | regex `/if \(was\.rotation[\s\S]*?return null;/` via new `onceRe` | **yes** -- whitespace/line breaks inside the guard no longer matter |
| `company_roundtrip` / `P0-2: an absent notch fingerprint warns instead of refusing` | split the refusal object literal across more lines | `'  if (!notchOnGrid) {\n    return { ok: false, notchVerified: false,'` | `'if (!notchOnGrid) {'` | **yes** -- single line, immune to how the object below wraps, and needs no CRLF handling |

Both repairs are reflow-proof without weakening the mutation, so the "keep it exact and say so" escape hatch was not needed.

- **geometry**: added `onceRe(src, re, repl)` next to `once`. It keeps the same discipline deliberately -- it **dies loudly if the pattern matches zero times OR more than once**. That non-uniqueness check is the point: a pattern anchor that quietly matches a second site would be exactly the silent disarmament this file guards against. Anchoring on the guard's *shape* is not weaker than its exact text, because the replacement still deletes the whole guard, which is all this mutant ever did.
- **company**: the dropped tail was pure disambiguation. `if (!notchOnGrid) {` occurs exactly once in `map_editor.js` (verified: `grep -c` = 1; `notchOnGrid` appears 3 times total), so nothing is lost.

## Red/green proof per repaired mutation

Each harness's own sweep is the apply/restore cycle; "RED" below means the mutant produced *new* failures relative to a green baseline, and the plain run is the restore.

| mutant | applied -> RED, caught by | restored -> GREEN |
|---|---|---|
| `orientation-guard-removed` | 1 new failure: `fixture/5-rotation-really-renumbers: expected true, got false` | `baseline: 46 assertions, 0 failure(s)`, `ASSERTIONS 46 0`, `mutation check: 8/8`, exit 0 |
| `P0-2: an absent notch fingerprint...` | 2 named detections: `default: a missing notch fingerprint no longer refuses`, `no-materials: a missing notch fingerprint no longer refuses` | `84 passed, 0 failed`, `ASSERTIONS 84 0`, `mutation check: 18/18`, exit 0 |

**Bite preserved, not merely present.** The orientation mutant is caught by a fixture-vacuity assertion rather than an obviously rule-4 one, which could have meant my repair changed what it scores. It did not: I reconstructed the pre-reflow world in a scratch tree (`git archive b322267 client2/src` + the **pre-repair** harnesses from `b322267`) and ran it. The pre-reflow pair produces the identical result -- same single detection, same name, same 8/8; and identically for P0-2 (same two names, same 84 assertions, same 18/18). So the repair reproduces the original bite exactly rather than substituting a different one.

**Reflow-independence demonstrated on three formattings.** The repaired harnesses were run against (a) the pre-reflow source, (b) post-reflow HEAD, (c) an invented third re-wrap (guard collapsed to one line; notch refusal object put back on one line) in a scratch copy. All three: baseline green and full mutation scores (8/8, 18/18). Scratch copies only -- the source was never modified and git was never used to revert anything.

## Full runner after the repair

```
22 harnesses -- 17 gated, 5 on the known-red debt list (5 still red, 0 recovered).
every gated harness is green.                                    (exit 0)
```

**Blocking set: empty.** Gate/debt split identical to round 0 (22 / 17 / 5), same five debt entries, and every gated harness reports the same ASSERTIONS counts as round 0 -- plus the two repaired harnesses now contributing real numbers where round 0 could only record a crash:

| harness | round 0 | now |
|---|---|---|
| company_roundtrip_harness.mjs | exit 2, no line | `ran 84, failed 0` |
| geometry_origin_reseat_harness.mjs | exit 2, baseline-only 46/0 then died | `ran 46, failed 0`, 8/8 mutants |

The reflow did not move the debt numbers either: `valid_die_frame_adoption` still reports `228 42`, so the recorded expectation needs no re-triage.

## Answer: can the prose figure be deleted rather than corrected?

**Yes for the prose figure -- and it should be. No for the structured field, which is load-bearing.** The two are different things and my round 0 entry conflated them:

```js
['valid_die_frame_adoption_harness.mjs', { ran: 228, failed: 42,
  why: '...under triage (measured 42 failing on the 2026-08-04 working tree;
        the debt-list prose used to say 28 ...)' }],
```

- `ran`/`failed` are **not prose and cannot be deleted**: they are the enforcement floor and ceiling. Delete them and rules 4-6 lose their comparand, which is the whole H1 mechanism. They can drift *downward* harmlessly by design (below ceiling never blocks) and drift *upward* only by blocking, which is the intended alarm.
- The figure inside `why` **is** reachable from the machine line and is therefore pure duplication. The runner already prints the live measurement immediately next to the prose on every run: `✗ valid_die_frame_adoption_harness.mjs [known red] (ran 228, failed 42) <why>`. A reader never needs the count restated in the sentence, and that restatement is precisely the kind of number that goes stale silently -- it is how "28" survived long enough for the board to also print 41.

Proposed rule, and I would apply it to all five entries on your word (not done in `2664004`, since it changes what a debt entry claims rather than repairing an anchor): **`why` carries only what the machine cannot know -- the reason and the triage state -- never a count.** For this entry:

```js
['valid_die_frame_adoption_harness.mjs', { ran: 228, failed: 42,
  why: 'fixtures holding the pre-da8f390 contract; under triage' }],
```

The same edit removes "98 passed / 1 failed" from the `valid_die_authoring` entry (identical duplication). The three `ran: 0` entries need no change -- their prose describes a crash cause, which is genuinely unmachinable.

One caveat worth your judgment: this makes the *history* of a debt figure unrecoverable from the file (the "prose said 28, live said 42" discrepancy would live only in git and in this report). I think that is correct -- the debt list should state today's contract, not carry its own changelog -- but it is a deliberate loss, not an oversight.

---

# Round 0 follow-up 2 -- debt-list prose trimmed to the unmachinable

- **Commit**: `db46525` `docs(harness): the debt list states today's contract, not its own changelog` (branch `main`, NOT pushed)
- **Scope honored**: `client2/scripts/check_harnesses.mjs` only -- one file, prose only. No runner logic, no harness file, nothing under `client2/src/`. Explicit-path `git add`, no build, not pushed.
- **Concurrency**: checked `git status` on `client2/src` and `client2/tests` immediately before running the suite -- map-pm's R1 seam extraction had not landed anything in the working tree at that moment, so the runner result below is uncontaminated by in-flight work. I touched neither `map_editor.js` nor `map_key_*`.

## The edit

| entry | before (`why`) | after (`why`) |
|---|---|---|
| `valid_die_authoring_harness.mjs` | `98 passed / 1 failed ― one assertion, not a crash` | `cause not yet triaged ― the failing assertion has never been attributed` |
| `valid_die_frame_adoption_harness.mjs` | `fixtures holding the pre-da8f390 contract; under triage (measured 42 failing on the 2026-08-04 working tree; the debt-list prose used to say 28 ― the count line does not lie)` | `fixtures holding the pre-da8f390 contract; under triage` |
| the three `ran: 0` entries | unchanged | unchanged -- a crash cause is genuinely unmachinable |

Two judgment calls inside the approved rule, both flagged rather than assumed:

1. **"one assertion, not a crash" went too.** Crash-vs-assertion is machine-visible (`ran > 0` means it reached its assertions), so that phrase is the same duplication in words instead of digits. What survives is the only genuinely unmachinable fact about that entry: nobody has attributed the failure yet. I did not invent a cause I do not know.
2. **`ran`/`failed` untouched**, as instructed -- they are the enforcement floor/ceiling, not prose.

I also added a rule to the comment block directly above `KNOWN_RED`, stating the invariant and why (with the 28/42/41 incident as the reason), so the next person adding an entry does not put a count back. That is debt-list prose about the debt list, and it is the only thing standing between this rule and its own slow erosion.

## Verification

```
22 harnesses -- 17 gated, 5 on the known-red debt list (5 still red, 0 recovered).
every gated harness is green.                                    (exit 0)
```

Identical gate/debt split to the previous two rounds; every gated harness reports the same ASSERTIONS counts. **The justification holds on screen** -- both trimmed entries print their live measurement exactly where the prose stopped saying it:

```
x valid_die_authoring_harness.mjs       [known red] (ran 99, failed 1) cause not yet triaged - the failing assertion has never been attributed
x valid_die_frame_adoption_harness.mjs  [known red] (ran 228, failed 42) fixtures holding the pre-da8f390 contract; under triage
```

Swept the file for any surviving count-shaped prose: the only digits left in a `why` are a date (`2026-07-30`), a commit hash (`da8f390`), a symbol name (`pushBlockingCount`), and `ASSERTIONS 0 0` on the reposition entry -- that last one is a pointer to the protocol describing a structural fact (it asserts nothing by design), not a measured figure that can drift.

## Standing state after three rounds

- Commits, none pushed: `b322267` (H1/H2/M1) -> `2664004` (anchor repair) -> `db46525` (debt-list prose).
- Runner: 22 discovered / 17 gated green / 5 known-red, exit 0.
- Open items I am **not** acting on: the three dead harnesses (`effort_instrument`, `split_registry`, `reposition_regime_probe`) still need repair-or-retire decisions, and green harnesses still have no recorded assertion floor -- a green harness that quietly sheds assertions while staying green remains invisible to the gate. Both are yours to schedule.

---

# Round 0 follow-up 3 -- assertion floors for every harness

- **Commit**: `efc4514` `test(harness): floors for every harness, not just the red ones` (branch `main`, NOT pushed)
- **Scope honored**: `client2/scripts/check_harnesses.mjs` only. No harness file needed a protocol line -- all 17 green harnesses already emit `ASSERTIONS` from round 0. Nothing under `client2/src/`, nothing in `client2/tests/map_key_*`, no board edit. Explicit-path `git add` (verified with `git diff --cached --name-only` before committing, because R1's files were dirty in the same tree).

## Where the floors came from

**`db46525` (HEAD)**, materialized with `git archive HEAD | tar -x` into a scratch tree and measured there. This mattered: when I re-checked `git status` mid-task, R1 had landed in the working tree (`client2/src/map_editor.js` and `client2/tests/map_key_canonical_harness.mjs` modified, new `client2/src/map_key.js`). Had I baselined from the working tree, post-move counts would have been recorded as the historical floor -- the gate would have been calibrated to the very reduction it exists to catch.

Three harnesses cannot run in a bare archive; I gave them their environment rather than substituting live-tree numbers:

| harness | missing | how HEAD was still measured |
|---|---|---|
| `copy_header_count` | `.git` | ran with `GIT_DIR` pointed at the real repo -- it reads `HEAD:`, which is the commit being baselined |
| `valid_die_head_parity_oracle` | `.git` | same |
| `undeclared_identifier` | `node_modules` (rolldown) | ran the HEAD harness file against the **scratch HEAD source path** via its `argv[2]` (confirmed the live harness file is byte-identical to HEAD: `git diff --stat HEAD` empty) |

All three agreed with the live-tree numbers, which is expected -- those three do not touch the files R1 is moving.

## Mechanism

`FLOORS`: `harness -> minimum ran`, one entry per currently-green harness (17). A drop is **BLOCKING**, phrased so the honest path is obvious ("if a re-pointed harness now covers less, say so and lower the floor on purpose"). Design decisions worth your review:

- **Floors, not exact matches.** A rise must never require an edit to pass. A gate that fails you for *adding* assertions teaches people to stop adding them, which would cost more than the drift it prevents.
- **Rises are reported, not enforced**: inline `floor 15, +2` on the harness's line, plus a closing note listing them. That is the "visible enough that someone eventually re-baselines" you asked for, and it puts no number into prose -- the floors are structured data, consistent with the rule `db46525` just established.
- **KNOWN_RED keeps its own `ran` floor and is absent from FLOORS** -- one harness, one place its floor lives. The runner **refuses to start** if a name appears in both, so the two mechanisms cannot drift into disagreement and silently let the looser one win.
- **A harness with no floor is a note, not a failure.** It cannot have regressed -- there is nothing to compare. Making it blocking would mean adding a harness breaks the build, which is how people learn not to add harnesses. It is loud so it gets baselined.

## Proof

Scratch tree (HEAD + the new runner), never the live harnesses, never `map_key_*`:

| path | action | result |
|---|---|---|
| **drop (the one that matters)** | deleted 4 of `push_gate_harness.mjs`'s 15 assertions | harness itself **exits 0**, `11 passed, 0 failed`, `ASSERTIONS 11 0` -- a clean green. Runner: `BLOCKING ... ran 11 ... floor is ran >= 15`, exit 1 |
| restore | copied the pristine file back | `✓ push_gate_harness.mjs (ran 15, failed 0)`, `every gated harness is green`, exit 0 |
| rise | added 2 assertions | `✓ (ran 17, failed 0; floor 15, +2)` + re-baseline note, **exit 0** -- no edit required |
| unbaselined | dropped in a new harness | passes with the "no recorded floor" note, exit 0 |
| double-booked | added a KNOWN_RED name to FLOORS | runner refuses to start, exit 1 |

The first row is the whole point: **that harness passed on its own.** Before this commit the runner would have printed "every gated harness is green" over a 27% coverage loss.

## Live runner after the change

```
22 harnesses -- 17 gated, 5 on the known-red debt list (5 still red, 0 recovered).
every gated harness is green.                                    (exit 0)
```

Split unchanged. Note for you: `map_key_canonical_harness.mjs` still reports **116** with R1 partially landed, so the extraction has not shed coverage so far -- the net is live and not firing spuriously. If it drops when R1 completes, that is the net working, not a bug in it, and the fix is map-pm re-pointing the harness (or a deliberate, stated floor change) -- not a floor edit to get green.

## Answer: what actually killed each `ran: 0` harness

| harness | cause | verdict input |
|---|---|---|
| `effort_instrument_harness.mjs` | **Incomplete lift list, not a missing symbol.** It builds its vm sandbox from an explicit list of `extractFunction(src, '<name>')` calls. It lifts `pushMapData`, which calls `pushBlockingCount` -- and `pushBlockingCount` is *not* in the list, so the sandbox throws `ReferenceError: pushBlockingCount is not defined` on first use. The function is alive and well in src (declared line 3225). | **Cheap repair** -- one line added to the lift list. Nothing about the product changed; the harness just never followed a call it depends on. |
| `split_registry_harness.mjs` | **A deleted concept, not a stale name.** It calls `extractConst('DEFAULT_LEGEND')`; `DEFAULT_LEGEND` has **zero occurrences anywhere in `client2/src`**. `95bf072` (U6, config-over-hardcode, 2026-07-28) moved the hardcoded default legend to a *server declaration* (`map_overlay_config.default_legend`, served via `GET /api/maps/paint-rules`). | **Judgment call.** Repair means rewriting the harness against the config-fetch path, not renaming a symbol. Worth asking whether what it scored still needs scoring client-side at all. |
| `reposition_regime_probe.mjs` | **Needs two fixture arguments that do not exist in the repo.** Lines 94-95 are `JSON.parse(readFileSync(process.argv[2]))` and `argv[3]` -- captured cells and frames. Bare `node` passes neither, so `readFileSync(undefined)` throws `ERR_INVALID_ARG_TYPE`. It also asserts nothing by design (pure measurement). | **Retire or relocate.** Same class as `startxy_probe` before M1, but unlike that one it cannot be given a meaningful default -- it needs *live-captured* data. Either land fixtures with it, or move it out of the auto-discovered `client2/tests/` into a probes location so it stops being counted as a gate. |

None of these three is a `map_editor.js` defect; all three are harness-side.

## Standing state

- Commits, none pushed: `b322267` -> `2664004` -> `db46525` -> `efc4514`.
- Runner: 22 discovered / 17 gated green / 5 known-red, exit 0.
- The doc-keeper hook has now fired at 26 commits accrued (`.claude/doc_sync_pending`). Still yours to schedule; I have not run a cycle or touched the board.
