# Candidate space: rotation4 × start-corner2 — measurement and staged plan

READ-ONLY round. No source, test, or config file was written. Scope per the lead PM's
correction: **`side` is untouched everywhere** — the stored column, `confirmed_meta_for`'s
assignment, and every physical-side reader stay exactly as they are. Item 3 of the original
brief (side readers / map-editor back side) is dropped and was not investigated.

`server/map_alignment.py` and `server/tests/test_map_alignment.py` are dirty in the working
tree (another lane, +261/-7). Every line number below sits **below** that lane's first hunk
(`@@ -1878,0 +1879,64 @@`) except where noted, so it matches HEAD as well as the working tree.

---

## 0. THE BRIEF IS WRONG ON ONE LOAD-BEARING CLAIM — read this first

The brief states, as measured fact:

> On the index axis, `rotθ_back` walked left-to-right is the **same ranking** as `rotθ_front`
> walked right-to-left, **with no rotation shift** (measured).

**That is true on the half-turns and false on the quarter-turns.** Measured today against the
live `map_alignment.serpentine_rank` + `map_overlay.make_frame_transform`, on three grid
shapes (11×9 / 93 dies, 12×8 / 90 dies, 9×14 / 120 dies), identical result on all three:

| today's candidate | equals, on the ordinal-per-die signature | rotation shift? |
|---|---|---|
| `rot0_front`   | `rot0` @ 좌상단 (TL)   | — |
| `rot90_front`  | `rot90` @ TL           | — |
| `rot180_front` | `rot180` @ TL          | — |
| `rot270_front` | `rot270` @ TL          | — |
| `rot0_back`    | `rot0` @ 우상단 (TR)   | none |
| `rot180_back`  | `rot180` @ TR          | none |
| **`rot90_back`**  | **`rot270` @ TR**   | **90 → 270** |
| **`rot270_back`** | **`rot90` @ TR**    | **270 → 90** |

Agreement is exact — 93/93, 90/90, 120/120 dies — for the matching row, and near-zero for
every other corner (e.g. `rot90_back` vs `rot90`@TL: 0/93; vs `rot90`@TR: 1/93).

The reason is visible in the mirror's own definition: on the quarter turns the reflection flips
the **row** axis, not the column axis. `client2/src/map2/seating.js:36-40` states it plainly —
`if (quarter) rm = (visualRows - 1) - r; else cm = (visualCols - 1) - c;`. A row-axis flip is a
top/bottom change of start corner, and it only reads as a left/right change after the quarter
rotation has swapped the axes — which is exactly the 90↔270 shift in the table.

If someone hand-derives the rename table as "`_back` → 우상단, same rotation", it is correct on
`rot0` and `rot180` and **silently wrong on `rot90` and `rot270`**. This is the
`a-hand-check-lands-on-the-degenerate-case` failure mode, and the brief already contains it.

### The decision itself survives the correction

Good news, and it is the reason this does not need re-deciding: **4 rotations × {TL, TR} is
still a bijection onto today's 8**, on the ordinal axis. Measured:

```
today's 8 candidates, distinct ordinal-signatures: 8
front x 4 rot x 4 corners, distinct: 8 of 16      (BL/BR are aliases of TR/TL under a 180 shift)
front x 4 rot x {TL,TR} (the board's 8), distinct: 8
```

So the 8-candidate target is right, the tie problem is real (16 would be 8 duplicate pairs —
`front x 4 rot x 4 corners` collapses to 8 distinct, which is precisely why wiring both axes
made every candidate tie with its twin and 10 tests correctly went red), and no stage should
ever produce 16. **Only the rename table needs correcting**, not the plan.

## 0b. The second thing the plan must not assume: "only names move" is false for occupancy

The lead PM's note says the user-visible behaviour is identical before and after. On the
**index axis** that is true. On the **occupancy and value axes** it is not, and the difference
is measurable:

```
distinct PLACEMENTS (where cells actually land) per space:
  today  (4 rot x 2 side)        : 8 distinct placements
  board's (4 rot front, 2 walks) : 4 distinct placements   <- the walk moves no cell
placements lost: rot0_back, rot90_back, rot180_back, rot270_back  (all det = -1, reflections)
```

Scoring a genuinely mirrored source (`map_alignment.score_candidates`, thresholds 1/1/1):

```
planted=rot0_back   space=both        winner=rot0_back    best agreement = 93/93
planted=rot0_back   space=front-only  winner=None         best agreement = 87/93 on rot0_front
planted=rot90_back  space=both        winner=rot90_back   best agreement = 93/93
planted=rot90_back  space=front-only  winner=None         best agreement = 87/93 on rot90_front
```

The start corner is a **scoring-input axis** (how dt index numbers are walked). `side` is a
**frame axis** (where cells are seated). Collapsing one onto the other keeps the index metric
intact and drops the reflection from occupancy/value. That is the same fact `51e4068` measured
from the other direction (114 of 120 cells on a different die).

This is not an argument to re-open the decision — it is the reason **stage 4 below must not
rewrite stored `_back` values into start-corner tokens**, and the reason the two
`front`-narrowing tests must stay red-or-rewritten rather than be quietly deleted. Flagging it
per the instruction to flag anything that changes what an operator sees.

---

## 1. The frame vocabulary — every producer and consumer, counted

### 1a. Minters (4) — code that constructs a frame string

| # | Site | Note |
|---|---|---|
| 1 | `server/map_alignment.py:56` `frame_text(rotation, side)` | `"rot%d_%s"`; the documented inverse of `parse_frame` |
| 2 | `server/map_alignment.py:61` `candidate_frames()` | loops `FRAME_ROTATIONS × FRAME_SIDES` (`:52`,`:53`), validates each through `parse_frame`, → `CANDIDATE_FRAMES` (`:74`) |
| 3 | `client2/src/map2/candidates.js:24` `candidateId(rotation, side)` | `` `rot${rotation}_${side}` `` — the client's own minter |
| 4 | `server/scripts/seed_dt_index_walk.py` | literal `dt_frame`/`core_frame` in the `JOBS` table (27 literal occurrences) |

### 1b. Acceptors (2) — code that parses a frame string

| # | Site | Note |
|---|---|---|
| 1 | `server/dt_map_derivation.py:313` `parse_frame` | **the SSOT acceptor.** Strict: `rot` prefix, rotation ∈ {0,90,180,270}, side ∈ {front,back} (`:332`,`:334`). Everything else in the server is validated through it |
| 2 | `client2/src/map2/candidates.js:29` `parseCandidateId` | regex twin, client side |

### 1c. Server production code — files carrying frame text

| File | literal `rot*_front|back` | vocabulary lines (frame_text / CANDIDATE_FRAMES / parse_frame / *_frame cols) |
|---|---|---|
| `server/map_alignment.py` | 32 | 50 |
| `server/scripts/seed_dt_index_walk.py` | 27 | 26 |
| `server/map_overlay.py` | 5 | 6 |
| `server/frame_confirmation.py` | 4 | 19 |
| `server/dt_map_derivation.py` | 1 | 21 |
| `server/database/models.py` | 2 | 7 |
| `server/migrations/add_frame_confirmation.py` | 0 | 6 |
| `server/main.py` | 1 | 2 |
| `server/trace_fixture/frames.py` | 2 | — |
| `server/trace_fixture/world.py` | 1 | — |

Consumers worth naming individually, because they are the ones a rename breaks silently:
- `server/dt_map_derivation.py:339` `source_meta_for_frame(target_meta, frame_text)` → `:349-352`
  writes `meta["side"] = side`. **Every candidate placement goes through here.**
- `server/dt_map_derivation.py:616-646` `resolve_frame` → `source_meta_for_frame`, keyed
  `tf_key = (map_id, frame_text)` at `:638`.
- `server/frame_confirmation.py:363` `applied = c.get("applied_frame") or frame`; `:372`
  `map_alignment.confirmed_meta_for(...)`; `:599` writes `confirmed_frame`; `:610` writes
  `winner_frame`; `:650` writes `applied_frame`; `:720`,`:726`,`:741` read them back for `/view`.
- `server/map_alignment.py:547` `confirmed_meta_for` (definition line confirmed), `:676`
  `base["rotation"], base["side"] = rot, side`, with `start_for_placement` at `:748` and
  `start_from_placement` at `:808` reading `base` below it. **Unchanged this round** — `side`
  keeps being written exactly as today.
- `server/map_alignment.py:991` `frame = frame_text(rot["value"], side["value"])` — the
  declared-frame reader; `:2959` `for frame in CANDIDATE_FRAMES` — the scoring loop; `:2941`
  and `:3629`,`:3630` — `sides_considered` / `sides_narrowed` reporting.

### 1d. Storage — 11 columns across 4 tables (verified against the live schema)

| Table | Columns holding frame text |
|---|---|
| `frame_confirmation` | `confirmed_frame`, `winner_frame`, `core_frame`, `dt_frame`, `frames` (JSON) |
| `frame_confirmation_source` | `applied_frame` |
| `eqp_frame_attribution` | `dt_frame`, `core_frame`, `frame_key` |
| `dt_inventory` | `dt_frame`, `core_frame` |

Declared at `server/database/models.py:451` (`confirmed_frame`), `:519` (`winner_frame`),
`:598` (`applied_frame`); DDL at `server/migrations/add_frame_confirmation.py:39`, `:66`,
`:104`, `:175`.

### 1e. Config — 1 file, and `alignment.sides` is declared nowhere

- `server/config/map_overlay_config.json:84-93` holds the `alignment` block. It contains
  `min_margin_dies`, `min_discriminating_dies`, and the `index` sub-block — **no `sides` key**.
- `SIDES_KEY = "sides"` (`server/map_alignment.py:80-81`) and `load_alignment_sides` (`:83`)
  are live code, but **grep finds no `"sides"` declaration in `server/config/`, `config/`, or
  the gitignored user areas.** Per the docstring at `:85-93`, undeclared means *both*, so the
  production search today is always the full 8.
- 3 literal `rot*_front` occurrences in that file, all inside the `__derivation` comment at
  `:89` (the threshold provenance narrative), not machine-read.

### 1f. Client — 8 files in the aligner domain

| File | Role |
|---|---|
| `client2/src/map2/candidates.js:22,24,29,38,41,61` | `SIDES`, `candidateId`, `parseCandidateId`, `candidateList` — the client's vocabulary module |
| `client2/src/map2/main.js:2391-2394` | `spellFrame` → `` `${rotation}° · ${side === 'back' ? '우상단 시작' : '좌상단 시작'}` ``; exported at `:2453`; used at `:700-701`. **Already speaks the start-corner language over a `_back` token.** |
| `client2/src/map2/main.js:2249,2252,2254` | `framesFor` defaults an unparsable id to `{rotation:0, side:'front'}` |
| `client2/src/map2/seating.js:36-40,116` | applies the mirror on `side === 'back'` — **this is where the vocabulary change has geometric teeth** |
| `client2/src/map2/view_model.js:373-376` | `startLabel: side === 'back' ? '우상단 시작' : '좌상단 시작'`; the comment at `:373` claiming confirmation writes `side:"front"` is **stale** (reverted at `51e4068`) |
| `client2/src/map2/declaration.js:223,230,342,354,365,521,528` | `VALUE_CAN_INDICATE_PROVENANCE`, `SIDES`, defaults |
| `client2/src/map2/decode.js:360` | mirror-set commentary |
| `client2/src/map2/api.js:36,239,351` | payload shape docs |
| `client2/src/map_editor2.css:1315` | a comment quoting `rot0_back / 미채점 - 면 선언 제외` |

`client2/src/map_editor.js` also matches on `'back'` (9 sites) but is the **map editor's
physical wafer side** — out of scope this round and not to be touched.

### 1g. Tests — 155 test functions, 12 files

Machine-counted over `server/tests/test_*.py`, per function:

| Category | Count |
|---|---|
| Test functions touching the candidate vocabulary at all | **155** |
| …carrying a literal `rot*_back` | **33** |
| …parameterized over `CANDIDATE_FRAMES` / `candidate_frames()` | **18** |
| …asserting the **count** 8 | **2** |
| …touching `serpentine_index` / `serpentine_rank` / `left_to_right` | **12** |

By file: `test_map_alignment.py` 70, `test_frame_confirmation.py` 22,
`test_frame_confirmation_meta.py` 22, `test_map_alignment_assumption.py` 14,
`test_dt_map_derivation.py` 9, `test_map_alignment_single_key.py` 6,
`test_map_alignment_unregistered.py` 6, `test_map_alignment_worklist.py` 3,
`test_dt_index_walk_core_axis.py` 1, `test_map_overlay.py` 1, `test_trace_fixture.py` 1.

### 1h. Docs — 6 living documents + 15 append-only history files

Living (must be updated): `docs/spec/MAP_ALIGNMENT_SPEC.md` (17 literals),
`docs/process/PROJECT_STATUS.md` (8, **lead-PM owned — do not edit**),
`docs/architecture/data_model.md` (3), `docs/architecture/CODE_MAP.md` (3),
`docs/architecture/frontend.md` (1), `docs/proposal/DT_TRANSFORMATION_CHAIN_PROPOSAL.md` (1).

Append-only (**do not rewrite**): 15 files under `docs/history/`, incl.
`20260807_120619_the_mirror_half_is_the_top_right_half_and_the_walk_axis_replaces_it.md` —
whose title states the claim corrected in §0. A new history entry should carry the correction;
the existing one stays as written.

### 1i. What replaces `rot270_back` as a stored token — recommendation

Two shapes are possible and they are not equivalent for the migration:

- **(A) Keep the `rotθ_<word>` shape, swap the second word**, e.g. `rot270_tl` / `rot270_tr`
  (or `_lt` / `_rt`). `parse_frame` grows the two new words and **keeps accepting `front`/`back`**
  as legacy. Minimal diff, `frame_text`/`candidateId` unchanged in shape, and — critically —
  stored `_back` rows keep parsing and keep meaning what they meant.
- **(B) Two fields on the wire** (`rotation` + `start_corner`) with the id as a display join.
  Cleaner, but it changes the WS/REST payload shape and the `candidate_id` string that
  `client2/src/map2/main.js:2365` matches on — that is a **boundary contract change requiring
  the lead PM's approval**, and it makes the 3 stored rows unreadable without a migration.

**Recommend (A).** It is the only option that satisfies "only names move" for storage, and the
`side` field itself is untouched under it — the candidate token stops *being* a side token, and
the stored `side` on the metadata row goes on meaning the physical side.

⚠️ Under (A) the second word is **not** derivable from `side` by string substitution. The
rename table is the one in §0, including the 90↔270 swap.

---

## 2. Rows already stored under the old vocabulary — this box's numbers

⚠️ **This box is not production.** All figures below are this development box's, taken
read-only (`SET SESSION default_transaction_read_only = on`, the
`server/scripts/check_missing_business_key.py` pattern). Nothing was dropped or altered.

### 2a. `wafer_map_metadata` — 696 rows; `side` is inside `grid_metadata` JSON, not a column

There is **no `side` column** on `wafer_map_metadata` (columns: `row_id`, `business_key_val`,
`created_at`, `updated_at`, `is_graph_synced`, `needs_graph_rollback`, `graph_synced_at`,
`map_pk`, `target_table`, `map_id`, `grid_metadata`). Any migration written against a `side`
column would fail at parse time — worth knowing before someone drafts one.

| `grid_metadata.side` | rows |
|---|---|
| `front` | 629 |
| `back` | **56** |
| absent | 11 |

`side = back`, by table: `dt_map` 42, `bonding_map` 11, `dt_log` 1, `sample_map` 1, `test` 1.

**These 56 rows are untouched this round** — `side` does not change, and these are declarations
about maps, not candidate tokens.

### 2b. `frame_confirmation` — 27 rows, **3** carry a `*_back` frame

| `confirmed_frame` | rows | | `winner_frame` | rows |
|---|---|---|---|---|
| `rot90_front` | 8 | | `rot90_front` | 8 |
| `<NULL>` | 8 | | `rot0_front` | 7 |
| `rot0_front` | 6 | | `<NULL>` | 6 |
| **`rot0_back`** | **3** | | **`rot0_back`** | **3** |
| `rot270_front` | 1 | | `rot180_front` | 2 |
| `rot180_front` | 1 | | `rot270_front` | 1 |

`core_frame`: 23 NULL, 4 `rot0_front` — **zero** `_back`.

All 3 `_back` rows are **one supersession chain** (v1 → v2 → v3, uids
`fc_811fb7c0…` → `fc_9b04afdb…` → `fc_1cf205c7…`, only v3 live), all
`ruling_state = scored`, all against `reference_table = valid_die_ref`,
`map_table = dt_log`, all confirmed 2026-08-08.

### 2c. `frame_confirmation_source` — 77 rows, **3** carry a `*_back` applied_frame

`rot0_front` 34, `rot90_front` 33, NULL 4, **`rot0_back` 3**, `rot180_front` 2, `rot270_front` 1.

All 3 are the same source across the same chain: `source_table = dt_log`,
`map_id = SYN-IDX-MIRROR-R0`, `applied_frame = rot0_back`, `shift_dx = -2`, `shift_dy = 0`.

That map_id is the synthetic mirror job seeded by `server/scripts/seed_dt_index_walk.py:261`
("before this axis existed such a tool was seeded as a MIRROR frame (`dt_frame: rot0_back`)").
So on this box **every `_back` confirmation is synthetic seed data, and all of it is `rot0_back`
— the one rotation where the rename carries no 90↔270 shift.** Production is very unlikely to
be so convenient; the migration must implement the full table.

### 2d. `eqp_frame_attribution` (5 rows) and `dt_inventory` (127 rows)

`eqp_frame_attribution`: `dt_frame` = 4 NULL + 1 `rot90_front`; `core_frame` = 4 NULL + 1
`rot0_front`. **Zero `_back`.** `dt_inventory.dt_frame`/`core_frame`: zero rows match `%back%`
(the per-value breakdown errored on a numeric cast in an unrelated column and is not needed —
the `ILIKE '%back%'` count over both columns returned 0 of 127).

### 2e. What happens to each

| Rows | Under recommendation (A) | Action needed |
|---|---|---|
| 56 `wafer_map_metadata` `side=back` | nothing; `side` is not a candidate token | **none** |
| 3 `frame_confirmation` `rot0_back` (2 superseded) | `parse_frame` keeps accepting the legacy word; `/view` renders via `spellFrame`, which already says 우상단 시작 | **none required**; optional cosmetic rewrite of the 1 live row to `rot0_tr` |
| 3 `frame_confirmation_source` `rot0_back`, `shift_dx=-2` | **do not rewrite.** The shift was solved against a *mirrored* placement (§0b). Rewriting the token to a start-corner token would re-describe a reflection as a rotation and move the redraw | **leave; supersede with a fresh confirmation if the row matters** |
| `eqp_frame_attribution`, `dt_inventory` | no `_back` values exist | **none** |

**The migration is therefore additive-only: teach `parse_frame` the new words, do not rewrite
history.** That also honours the append-only discipline this repo already applies to
supersession chains.

---

## 3. *(dropped by the lead PM — `side` is untouched this round)*

---

## 4. Which tests pin the old space, and which flip vs. which must stay red

### 4a. Correct-and-will-flip — assert the *count* or the *shape*, survive a rename (2)

| Test | File:line | Why it flips cleanly |
|---|---|---|
| `test_the_eight_candidates_are_exactly_what_the_existing_acceptor_accepts` | `test_map_alignment.py:52-57` | asserts `len(CANDIDATE_FRAMES) == 8`, uniqueness, and `{parse_frame(f)}` equals the rotation×side product. **The count 8 survives; the last assertion is the one line that must be rewritten to the new axis product.** |
| `test_grid_y_invert_is_not_a_candidate_axis` | `test_map_alignment.py:70-71` | `len == 8` and `not any("inv" in f)` — both survive verbatim. |

`test_frame_text_is_the_inverse_of_parse_frame` (`:60-63`) also survives verbatim under
recommendation (A) as long as `frame_text` and `parse_frame` stay mutual inverses over the new
vocabulary.

### 4b. Correct-and-will-flip — parameterized over `CANDIDATE_FRAMES`, name-agnostic (18)

These take whatever `CANDIDATE_FRAMES` holds and assert a property of every member. They
**cannot break on a rename** and are the safety net for the whole round. Named ones:
`test_all_eight_are_scored_in_one_call`, `test_scoring_does_not_invent_a_bounding_box_basis`,
`test_values_are_truncated_with_their_cells_not_separately`,
`test_the_floors_own_frame_does_not_displace_the_placement`,
`test_a_confirmed_origin_survives_the_next_read`, `test_the_mask_box_defect_is_reachable`,
`test_the_stored_start_is_not_on_the_wire`, `test_an_empty_row_does_not_flip_the_direction`,
`test_the_gate_reads_the_candidate_vocabulary_rather_than_a_copy_of_it`
(`test_frame_confirmation_meta.py:607-608` — asserts against `candidate_frames()` *itself*,
explicitly built to survive this change), `test_y_invert_is_not_written_and_reads_as_nobody_claimed_it`,
plus 8 more in `test_map_alignment.py` / `test_map_alignment_assumption.py`.

⚠️ Two of them assert **geometric** properties that the front-only space changes:
- `test_y_invert_inverts_which_frames_are_mirrors` (`test_map_alignment.py:2678-2698`) — asserts
  the mirror set is non-empty under both y-invert settings and that `"rot0_back" in a`. With no
  reflection left in `CANDIDATE_FRAMES`, `mirrors(False)` becomes **empty** and the assertion
  `assert a and b` fails. **This one is correct-and-must-stay-red until rewritten** to source
  its mirror set from something other than the candidate list.
- `test_the_linear_part_matches_the_transform` (`test_map_alignment.py:2647-2676`) — loops
  `CANDIDATE_FRAMES` through `frame_linear_part` vs `make_frame_transform`. It still passes, but
  it silently stops covering reflections, which its own docstring calls the case that matters.
  **Flag: coverage loss, not a failure.**

### 4c. Correct-and-must-stay-red / must-be-rewritten — literal `rot*_back` (33)

These plant, expect, or narrow to a specific `_back` frame. A rename alone does not fix them;
each needs a decision. The ones where the *behaviour* changes, not just the name:

| Test | File:line | Why |
|---|---|---|
| `test_an_unconsidered_candidate_cannot_win` | `test_map_alignment.py:3076-3080` | plants `rot0_back`, narrows sides to `["front"]`, asserts the true frame cannot win. With no `back` in the space, the premise is gone. |
| `test_undeclared_sides_score_both`, `test_a_narrowed_side_is_reported_as_unconsidered_not_as_a_loser`, `test_undeclared_sides_leave_the_candidate_list_exactly_as_it_was` | `test_map_alignment.py` (the `load_alignment_sides` block) | the whole `sides` narrowing feature. Its subject disappears if `FRAME_SIDES` stops being the candidate axis. **Needs a product decision: retire `alignment.sides` or repoint it at the start corner.** |
| `test_values_settle_what_occupancy_cannot_see` | `:669-671` | parameterized on `rot0_back` as a planted truth |
| `test_direction_narrows_a_tie_that_order_alone_cannot` | `:2402-2406` | 10 `(frame, invert)` pairs incl. 4 `_back` |
| `test_the_written_start_is_where_the_editor_redraws_it` | `:1932`, `:1599` | plants `rot270_back` / `rot0_back` and checks the editor's redraw — **this is the 51e4068 oracle**; it is the test that must stay honest about the reflection |
| `test_borrowing_the_orientation_axes_would_move_every_cell` | `test_map_alignment_assumption.py:248-278` | asserts `sorted(unaffected) == ["rot0_front", "rot270_back"]` — a **membership** assertion, the `pin-the-members-not-the-count` shape |
| `test_a_planted_frame_is_recovered_under_the_assumption` and 12 more in `test_map_alignment_assumption.py` | `_seed(..., planted="rot90_back")` at `:500`, `_planted_cells` at `:741` | the file's default fixture frame is `rot90_back` — **one fixture default drives 13 tests** |
| `test_frame_parsing_refuses_everything_it_does_not_recognise` | `test_dt_map_derivation.py:876-878` | `parse_frame("rot90_back") == (90,"back")` — **must keep passing** under recommendation (A); would go red under (B) |
| `test_the_core_truths_cover_every_front_rotation` | `test_dt_index_walk_core_axis.py:77,145-153` | `.replace("_back","_front")` and a `FRONT_FRAMES + _back` space — encodes the mirror/front relation directly |
| `test_frame_compose_golden_rot90_back_target` | `test_map_overlay.py` | golden vector on the reflection composition — **map_overlay, not the aligner; must stay green untouched** |

On the earlier attempt's 10 reds: I do not have that run's failure list. From the structure, the
10 are the tie-sensitive ones — any test asserting a unique `winner` while both axes were live
(`test_a_planted_frame_is_recovered_*`, `test_values_settle_*`, `test_direction_narrows_a_tie_*`,
the `_assumption.py` fixture family). Those were **correct-and-will-flip** once the mirror half
is *removed* rather than joined. The ones above marked must-stay-red are a different set: they
fail because their subject genuinely disappears, and deleting them would be hiding the §0b loss.

---

## 5. The staged plan

Assumes recommendation (A) and `side` untouched. Every stage ends green except where flagged.

### Stage 0 — land the correction, before any code (no code change)
Correct the rename table in `docs/spec/MAP_ALIGNMENT_SPEC.md` and add a history entry carrying
the §0 finding. **Reason it is first:** the wrong table (`_back` → 우상단, same rotation) is
currently written into the board, the spec, and a history title. Any implementer who starts from
those three sources ships the 90↔270 bug. Do not rewrite the existing history file.

### Stage 1 — grow the acceptor, keep the space at 8 `front|back` (green, no behaviour change)
`server/dt_map_derivation.py:332-335`: `parse_frame` accepts `tl`/`tr` **in addition to**
`front`/`back`. `server/map_alignment.py:56` `frame_text` unchanged.
**Leaves green:** everything, including all 33 literal-`_back` tests. Nothing produces the new
words yet. Add positive tests for the two new words next to
`test_frame_parsing_refuses_everything_it_does_not_recognise`.

### Stage 2 — wire `left_to_right` into the scorer, still under the `front|back` names (green)
The axis today has **zero consumers**: `score_candidates` calls `serpentine_index` with
`top_is_min_y=True` only, at `server/map_alignment.py:2918` and `:3785` (and `:1486` inside
`serpentine_rank`); the only caller passing `left_to_right` is
`server/scripts/seed_dt_index_walk.py:264-269`. Make the index metric read the candidate's start
corner, derived from the *current* frame via the §0 table (`_back` → TR, with the 90↔270 swap
folded into the derivation, not into the frame). **Still 8 candidates. Never 16.**
**Leaves green:** all of §4a/§4b; the index-axis tests should be *strengthened* here, because
this is the stage where the walk stops being a constant.
**Flag:** this is the only stage that can change a ruling. Verify against the `SYN-IDX-*` seed
units before and after.

### Stage 3 — swap the vocabulary (the rename)
`FRAME_SIDES = ("front","back")` → a start-corner tuple; `frame_text`'s second component becomes
the corner; `CANDIDATE_FRAMES` becomes 4 rotations × 2 corners, **still 8**. `confirmed_meta_for`
at `:547`/`:676` keeps writing `side` exactly as today — it now derives `side` from the
rotation-and-corner pair per the §0 table rather than reading it off the token.
Then, in the same commit, because a partial rename is a broken contract:
- `client2/src/map2/candidates.js:22,24,29` — `SIDES` → corners, `candidateId`, `parseCandidateId`
- `client2/src/map2/main.js:2391-2394` `spellFrame` — already says 좌상단/우상단; repoint at the
  new token and delete the `side === 'back'` test
- `client2/src/map2/view_model.js:373-376` — same, and **delete the stale comment at `:373`**
  claiming confirmation writes `side:"front"` (reverted at `51e4068`)
- `client2/src/map2/seating.js:36-40,116` — ⚠️ **the mirror application.** Under the new space
  there is no reflection candidate, so this branch stops firing for aligner frames. Do not
  delete it: it still serves stored legacy `_back` tokens.
- `client2/src/map_editor2.css:1315` — comment only
- rebuild `client2` (`vite`) — a client change is not done until `dist` carries it
**Leaves red, deliberately:** the §4c set. Fix them in this commit.
**Boundary contract check:** the `candidate_id` string on the wire changes value but not shape
or key name. Confirm with the lead PM that this counts as within `frame id 어휘`.

### Stage 4 — storage (no data migration)
Nothing is rewritten. `parse_frame` keeps accepting `front`/`back` (Stage 1), so the 3
`frame_confirmation` and 3 `frame_confirmation_source` `rot0_back` rows on this box keep parsing
and keep rendering. **Rationale in §2e and §0b:** the stored `shift_dx = -2` was solved against a
mirrored placement, so rewriting the token would re-describe a reflection as a rotation.
If production carries `rot90_back` / `rot270_back` rows, they must **not** be rewritten by
string substitution — that is where the 90↔270 shift bites. Recommend a read-only census script
in the shape of `server/scripts/check_missing_business_key.py` before anyone proposes a rewrite.

### Stage 5 — the `alignment.sides` decision (needs the product owner)
`SIDES_KEY`/`load_alignment_sides` (`server/map_alignment.py:80-105`) and the
`STATE_NOT_CONSIDERED` / `TEXT_SIDE_NOT_CONSIDERED` reporting (`:2941`, `:3629-3630`, and
`client2/src/map_editor2.css:1315`) narrow the search by *side*. Since **no config declares
`sides` anywhere** (§1e), nothing in production depends on it today. Either retire it or repoint
it at the start corner. Retiring is 4 tests (§4c row 2) plus the `not_considered` state; that
state's docstring at `:2933-2940` is a strong argument in this repo and should not be discarded
casually. **Escalate rather than decide.**

### Stage 6 — docs
`MAP_ALIGNMENT_SPEC.md`, `data_model.md`, `CODE_MAP.md`, `frontend.md`,
`DT_TRANSFORMATION_CHAIN_PROPOSAL.md`; history entry + `conda run -n assy_manager python
docs/history/gen_index.py`. `PROJECT_STATUS.md` is lead-PM owned — supply the draft, do not edit.

### Full-suite gate
`conda run -n assy_manager python -m pytest server/tests/ -q` after stages 2, 3, and 6. Never two
pytest processes at once. Note the `test_map_alignment.py` working tree is dirty from another
lane — rebase before measuring, and treat a single red in a shared tree as a hypothesis.

---

## Verification performed

- All line numbers in the brief re-grepped: `candidate_frames` `:61` ✅, `load_alignment_sides`
  `:80` ✅, `confirmed_meta_for` `:547` ✅, `start_for_placement` `:748` ✅,
  `start_from_placement` `:808` ✅, `base["rotation"], base["side"] = rot, side` `:676` ✅.
  **The brief's line numbers are all correct this time.**
- `left_to_right` has zero production consumers ✅ (only `seed_dt_index_walk.py` and tests).
- Ordinal-equivalence measured on 3 grid shapes via the live `serpentine_rank` +
  `make_frame_transform`; the 90↔270 shift reproduces identically on all three.
- Placement-loss measured via `map_alignment.score_candidates` with real thresholds.
- All DB figures read-only under `default_transaction_read_only = on`. No table was dropped or
  altered. **These are this box's numbers, not production's.**
- No source, test, or config file written. Nothing committed or staged.
