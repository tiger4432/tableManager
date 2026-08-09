# QA2 — adversarial review, lens 2 (consumers, contracts, documentation)

Target: `1ebcc88 feat(align): the value axis scored a map it gave the screen no way to draw`
(`server/map_alignment.py` +128/−7, `server/tests/test_map_alignment.py` +140,
`docs/spec/MAP_ALIGNMENT_SPEC.md` +39). Baseline `34d2518`.

⚠️ **The change was committed to `main` while this review was running.** The brief named it as
uncommitted working tree; by the time I re-ran `git diff` the tree was clean and the content had
landed as `1ebcc88`. I verified `1ebcc88`'s three-file stat matches the diff I read, so the
findings below apply to what is now on `main`, not to a pending patch.

🔴 No pytest was run (lane rule). Every claim below is source reading, grep, or static reasoning.
Where only a run can settle something I name the test.

---

## 1. Verdict

**GO-WITH-FIXES.**

The mechanism is sound and the index path is genuinely untouched — I could not construct an input
where an indexed unit's `placement` changes, and the `ruling["anchor"]` gate is a provable no-op on
that path. But the change removes a guard that was accidentally load-bearing: it makes anchor-less
units *drawable*, and a drawable candidate on a screen whose confirm button was opened on 2026-08-07
is a **confirmable** candidate. The confirmation that an operator can now take on such a unit runs
through the one derivation branch this spec already records as unable to carry the origin-box
correction (`MAP_ALIGNMENT_SPEC.md:887` ⏳ item ①) — and the same commit's own §9.9 does not mention
that pending item, let alone resolve it. That is finding H1 and it is the reason this is not a GO.

---

## 2. Confirmed defects

### [HIGH] H1 — the change makes a known-unfixed confirmation defect reachable, and §9.9 does not say so

`docs/spec/MAP_ALIGNMENT_SPEC.md:887` already carries this, written 2026-08-06 and still open:

> ⏳ **남은 것 둘(총괄 판정 대기)**: ① **`elif shift` 갈래**(`start_for_placement`)는 유도가
> **선형부만** 읽어 상자가 원리적으로 상쇄되므로 이 보정을 실을 자리가 없다 — **앵커 없는 확정이
> `valid_die_ref`를 함께 적는 경로가 실재하는지부터 판정이 필요하다.**

That question — "does an anchor-less confirmation that also writes `valid_die_ref` actually exist?"
— is answered **yes** by this commit, and answered silently.

Mechanism, in code:

- `server/map_alignment.py:702-716`. `src_box` (the mask origin box) is computed at `:702-706`
  from `basis_cells`, then passed **only** into the anchor branch at `:710`. The `elif shift`
  branch at `:713-716` calls `start_for_placement(base, basis_meta, shift)` with no box argument
  at all — `start_for_placement` (`:748-806`) calls `make_frame_transform(framed_meta, target_meta)`
  with no `source_box`/`target_box`, so it derives the origin in **original-box** space.
- `server/map_alignment.py:743-749` (`_ref_id` / `apply_valid_die_ref`) runs **after** the if/elif
  and is gated only on `basis.map_id`. It is not branch-aware. So the same write that stored an
  original-box origin also stamps `valid_die_ref`, which is exactly the declaration that flips the
  editor to the **mask** box (`MAP_EDITOR_SPEC §5.7`, mirrored server-side by
  `resolve_valid_die_basis(...) == SOURCE_REF`).
- `server/frame_confirmation.py:769-803` (`_placement_of`) lifts the anchor pair from
  `ruling["anchor"]`; on the search path that key is null by the new gate, so `_p` is
  `{"dx","dy"}` only and `confirmed_meta_for` necessarily takes the `elif shift` branch.

Failure scenario (the live unit named in §9.9 is exactly this shape):
`dt_frame_confrimation` / `DT-EQP-02_20260512T0000_T09` scored against `valid_die_ref/QA_MAP2`,
`index_axis: absent`. Before this commit the screen drew nothing, so an operator had no picture to
confirm. After it, eight thumbnails render, the operator presses 확정, and
`confirmed_meta_for` writes `grid_start_x/y` computed in original-box space **and**
`valid_die_ref: QA_MAP2` into the same `grid_metadata`. The editor then reopens that map, resolves
the ref, switches to the mask box, and reads the stored origin against a different box.
`MAP_ALIGNMENT_SPEC.md:880` gives this box's measured cost on the anchor path:
**2,880 of 3,840 cells landed on a different die, in 12 of 16 frame combinations.** The shift branch
has no place to put the correction, so on a floor whose mask is inside its circle the confirmation
stores an origin that is wrong in the same 12 combinations — and nothing tells the operator.

⚠️ Note this is not a defect the commit *introduced*: `start_for_placement`'s blindness to the box
predates it, and the confirm button was opened in `21209d7`. What the commit does is remove the
last thing that kept the combination out of an operator's hands. This project has a history entry
titled for precisely this pattern (`docs/history/…the_last_accidental_guard_and_the_race_it_hid.md`).

Recommended action (pick one, do not ship silently):
(a) resolve §9.7-ter ⏳① before this reaches operators — either teach the shift branch a box
    correction or refuse `valid_die_ref` stamping on that branch; or
(b) if (a) is a separate round, make the confirm path *say* it: surface at confirm time that this
    unit's translation came from a saturated search and its origin derivation cannot carry the mask
    box, and record the fact (see H2). The screen already has the vocabulary slot for
    "you are answering on a guess" — `21209d7` kept `restsOnGuess` in the note for this reason.
(c) at minimum, §9.9 must reference §9.7-ter ⏳① and state that this commit activates it.

### [HIGH] H2 — the wire and the stored record cannot distinguish "placed from an index anchor" from "placed from a searched pivot"

The payload keys are `linear` / `anchor_src` / `anchor_ref` on **both** paths
(`server/map_alignment.py:1927-1940`, `_placement_payload`). On the search path `anchor_src` is not
an anchor — it is `search_pivot_of`'s minimum-`(y,x)` cell, which the function's own docstring says
"carries NO claim". Two responses that are byte-identical in `per_candidate[].placement` can rest on
completely different evidence.

What a reader *could* use instead, and why each is insufficient:

- `ruling["placement"]` (`:3596`) is the word `anchor`/`shift_search` — but it is gated on
  **`anchor_dxy`**, while the new placement branch is gated on **`anchor_cell`**. They are not the
  same predicate. `ANCHOR_PLACEMENT_ENABLED = False` (`:1427`, `:1972`) makes `anchor_dxy` None
  while `anchor_cell` stands, so the word says `shift_search` while the placement (and, per the new
  code at `:3627`, `ruling["anchor"]` too) is anchor-pivoted. Pre-existing, but it means the
  vocabulary a consumer would reach for is not a reliable discriminator for the field this commit
  changed.
- `ruling["anchor"]` is null on the search path, so *a server-side reader* can infer it. But no
  client code reads that key: grep over `client2/src/**` finds `anchor_reason`, `shift_search`,
  and `placementWord` at **0 hits**. Only `index_axis` is decoded (`decode.js:778-779`), and only
  into the index-walk legend.
- The confirmation record does not store it. `server/database/models.py:420-575` persists
  `ruling_state`, `ruling_reason`, `winner_frame`, `margin`, `discriminating`,
  `thresholds_defaulted`, `reference_cell_count`, `geometry_assumed`; `FrameConfirmationSource`
  (`:577-616`) persists `applied_frame`, `shift_dx/dy`, `agreement`, `discriminating`,
  `geometry_basis`. **Neither table has a column for `ruling.placement` or `anchor_reason`.**

Failure scenario: a no-index unit's search saturates (the commit's own test comment at
`test_map_alignment.py:2523-2530` measures exactly this — at offset (0,0) all eight candidates settle
on `(0,0)` by tie-break) and `PLACEMENT_SEARCH`'s definition at `:1421` says so outright:
「겹침 최대화 탐색. 포화하면 **동점 규칙이 정한다**」. The operator sees a confident eight-panel
picture, confirms, and six months later someone asks "which decisions rested on a tie-broken
placement rather than on read data?" — the question `geometry_assumed` was added to the header to
make answerable for the *assumption* axis has no answer for the *placement* axis. The precedent
argument is written into the model itself (`models.py:534-541`: 「나중에 그 가정이 거짓으로 밝혀지면
어느 결정이 그 위에 서 있었나」).

Recommended action: persist `ruling["placement"]` (and `anchor_reason`) on `FrameConfirmation`,
same class of field as `geometry_assumed`/`thresholds_defaulted`; and surface the word on the
alignment screen beside the picture. Renaming the wire keys is *not* recommended — that breaks the
decoder, both harnesses and the built bundle for no gain; the discriminator belongs in the ruling
and the record, where the project already puts this kind of fact.

### [MEDIUM] M1 — the change's extension is larger than §9.9 and the tests state

§9.9 and all three new tests describe the affected population as "순번이 하나도 없는 단위" / "no die
carries an index". The actual gate is `anchor_cell is None` (`:3495-3501`), and `anchor_cell_of`
(`:1855-1875`) returns None in **three** distinct situations, not one:

1. no index values anywhere (`ANCHOR_NO_INDEX`) — the documented case;
2. **the minimum index is not unique** (`:1872` `best = (kv, None, None, None)`, surfaced as
   `ANCHOR_MIN_NOT_UNIQUE`) — an indexed unit with a duplicate minimum;
3. **more than one map carries indices** (`:1873` `len(maps_seen) > 1`, `ANCHOR_MULTI_MAP`) — here
   `search_pivot_of` also refuses (it requires exactly one contributing map), so only if the second
   map contributes no usable cells does this reach the new path;
   plus `reference_top_left is None` (`:2949`), which short-circuits `anchor_cell` entirely.

Cases 2 and 4 now ship a non-null placement where they shipped null before, and neither is covered:
`test_an_unusable_anchor_falls_back_and_names_which[MIN_NOT_UNIQUE]`
(`test_map_alignment.py:2968-2986`) exercises case 2 but asserts only `ruling["placement"]` and
`anchor_reason` — it would go green whether the candidates carry a placement or not.

Failure scenario: a unit whose equipment restarted numbering mid-job has two dies numbered 1.
`ruling.index_axis` is `ranking`, the operator sees a full index legend *and* now a drawn source
map, and nothing on the screen says the translation came from the ±3 search rather than from the
duplicated anchor. Before this commit the blank stage was the signal.

Recommended action: state the real predicate in §9.9 ("`anchor_cell` did not stand", with its three
reasons), and add one case to `test_the_screen_can_draw_when_no_die_carries_an_index` — or a
sibling — for `ANCHOR_MIN_NOT_UNIQUE`, so the newly-drawable population is pinned by membership
rather than by the one reason that was reported.

### [MEDIUM] M2 — four client comments now state a mechanism that no longer exists

The project treats a comment describing a changed mechanism as a real defect. §9.9's ⚠️ bullet names
**one** stale site (`main.js:2357`). I found **four**, and one of them is not stale-in-wording but
false-in-substance:

| file:line | text | why it is now false |
|---|---|---|
| `client2/src/map2/decode.js:669-671` | "`null` means this server did not place this candidate — **the anchor declined**, or this producer predates the field." | "the anchor declined" is no longer sufficient for null. Null now means the anchor declined **and** the search pivot also refused (≠1 contributing map). A reader debugging a null placement is sent to the wrong half of the server. |
| `client2/src/map2/decode.js:310-313` | "the server places **every row whose anchor stood** regardless of whether it could rank it" | The server now also places every row whose *search pivot* stood. |
| `client2/src/map2/decode.js:661` | "`anchor_ref = reference_top_left + (dx, dy)` adds `(dx, dy)` to `reference_top_left`" | Same retired formula §9.9 flags at `main.js:2357`. **This is the second copy and §9.9 does not name it.** (Behaviour is still right — both sentences conclude "do not add the shift again".) |
| `client2/src/map2/main.js:2357-2359` | same formula | named by §9.9; still unfixed in the tree. |

Also inside the changed file: `server/map_alignment.py:3475-3477`'s "앵커 쌍 옆에 파생값을…" now
describes a pair that on one of the two paths is not an anchor pair.

Failure scenario: this is the "stale copy surfaced all at once" pattern the codebase already paid
for — `main.js:1711-1714` documents it in the past tense. The next person reading `decode.js:669`
to explain a blank stage on a two-map unit will look for a declined anchor and find one, and stop.

### [LOW] L1 — `CODE_MAP.md` was not re-anchored for the two new symbols

`docs/architecture/CODE_MAP.md:1928` enumerates the placement family:
`anchor_cell_of(usable)` · `_anchor_shift(...)` · `_residual_shift(...)` · `_CANONICAL_AXES`.
`search_pivot_of` and `_placement_payload` are absent — grep across `CODE_MAP.md` and
`PRIMITIVES.md` returns 0 hits for both. `search_pivot_of` is by its own docstring a *sibling rule*
to `anchor_cell_of` ("both answer 'which source cell is the pivot', and they are the ONLY two places
that answer it"), so a catalogue that lists one and not the other is exactly the shape that makes
someone write a third. Note `8d89b98` re-anchored this file the same day; this line was missed
because the commit under review landed after it.

---

## 3. Hypotheses I tried to break and could not

1. **"The `ruling["anchor"]` gate is not actually a no-op on the index path."** Refuted. Old code
   was `ruling["anchor"] = (_win_row or {}).get("placement")`; on the search path `_win_row`'s
   `placement` was already `None` (the old ternary was gated on `anchor_cell`), so the new
   `if anchor_cell is not None else None` returns the identical value in every reachable state.
   `_win_row` (`:3610`) is a row of the same `out` list, so there is no second producer.
2. **"The search branch can shadow the anchor branch."** Refuted. `_pivot` is computed only when
   `anchor_cell is None` (`:2955`), `pivot_map_index` stays `None` on the index path, and `mi` is
   always an int so `mi == None` is False — neither `search_linear` (`:3047-3049`) nor
   `search_placed` (`:3076-3081`) can be captured while an anchor stands.
3. **"The pivot index can drift between `search_pivot_of` and the capture."** Refuted.
   `sm["_use"]` is built once at `:2857-2863`, before the frame loop, and the scoring loop iterates
   `for mi, sm in enumerate(usable)` (`:2987`) over the same list with the same indices. The
   capture matches on `i == pivot_i` (index, not coordinate), so a duplicated coordinate cannot
   make it ambiguous.
4. **"`placementFor` reads the raw snake_case dict and `placeCells` expects camelCase, so the new
   non-null placement will throw."** Refuted. `main.js:2105` sets `per_candidate: decoded.scorings`,
   and both decode sites (`decode.js:317` for unmeasured states, `:365` for measured) run
   `decodePlacement`, which emits `{linear, anchorSrc, anchorRef, det}`. `placementFor` therefore
   reads decoded rows. The determinant refusal at `decode.js:688-691` also still applies to the new
   payload — `search_linear` comes from `frame_linear_part`, a signed permutation matrix, so it
   passes.
5. **"The built bundle is stale and would ignore or mishandle the new field."** Refuted for this
   field. `client2/dist/` is **tracked** (`git check-ignore` returns nothing), and
   `client2/dist/assets/map_editor2-BtVYbYe9.js` contains `placement` ×11, `anchor_ref` ×2,
   `anchor_src` ×2 and exactly one `배치 없음` — the same shape as `src`. It also contains
   `우상단 시작` (added 2026-08-07 in `c959368`), so it postdates the last client change to this
   path. No client rebuild is required by this commit.
6. **"A gitignored user-area config carries a placement consumer."** Refuted.
   `grep -rn "placement" server/config server/mappers server/ingestion_workspace` → 0 hits.
7. **"A contract vector pins `placement: null` on a no-index unit."** Refuted.
   `contracts/map2_seam/vectors.json` has one `placement` hit and it is the word "misplacement" in
   a `$kills` note about rotation parsing. No seam vector covers this field.

---

## 4. Consumer census — counted, not estimated

Every reader of `per_candidate[].placement` in executable code. **9 sites in 5 files, plus one
built copy.** None of them assumes an index anchor existed; the assumption lives only in the
comments (M2) and in the absent vocabulary (H2).

| # | site | what it does | affected? |
|---|---|---|---|
| 1 | `server/map_alignment.py:3497` | producer (`_candidate_rows`) | changed |
| 2 | `server/map_alignment.py:3627` | `ruling["anchor"]` ← winner row's placement | gated, value unchanged |
| 3 | `client2/src/map2/decode.js:317` | decodes it for `not_considered`/unmeasured rows | now sees non-null on search path |
| 4 | `client2/src/map2/decode.js:365` | decodes it for scored rows | same |
| 5 | `client2/src/map2/decode.js:672-699` | `decodePlacement` — shape + determinant validation | passes the new payload |
| 6 | `client2/src/map2/main.js:2363-2366` | `placementFor` — field access on decoded row | now returns an object |
| 7 | `client2/src/map2/main.js:2296-2298` | `seatingFor` — the one seat producer; `null` → `배치 없음` | this is the behaviour change the operator sees |
| 8 | `client2/src/map2/main.js:2334` | `paintCandidateThumbs` → `seatingFor` per thumbnail | eight pictures instead of none |
| 9 | `client2/src/map2/seating.js:338-380` | `placeCells` — applies `anchorRef + L·(cell − anchorSrc)` | unchanged arithmetic |
| — | `client2/dist/assets/map_editor2-BtVYbYe9.js` | built copy of 3–9 | current, no rebuild needed |

Not consumers, checked and cleared: `view_model.js:251-252` iterates `per_candidate` but reads
`shift`/`agree`/`state`, never `placement` (`:391`); `verdict_placeholder.js`, `excel_io.js`,
`websocket.js`, `value_suggest.js`, `map_editor.js`, `map_editor2.css` match only on the substrings
"replacement"/"misplacement" or in prose; `server/main.py`, `health.py`, `keyset_scan.py`,
`enrichment_backfill.py`, `map_overlay.py` have no `per_candidate` reader
(`grep -rn "per_candidate" server/` outside tests is confined to `map_alignment.py`).

Tests and harnesses reading the field (not consumers in production, but they pin the contract):
`server/tests/test_map_alignment.py` (`:2044`, `:2317`, `:2493`, `:2916-2928`, and the new block
`:2513-2650`), `client2/tests/map2_placement_seat_harness.mjs`,
`client2/tests/map_editor2_shell_harness.mjs`. `valid_die_dirty_guard_harness.mjs`,
`overlay_provenance_harness.mjs` and `coord_table_paste_harness.mjs` match only on
"replacement"/generic "placement loop" prose and do not read the wire field.

**One test needs a run to settle** (I could not execute it this lane):
`server/tests/test_map_alignment.py:2317` asserts `ruling.get("anchor") == win["placement"]`
**unconditionally**. Its fixture (`:2309-2312`) passes `indices=ks` so it should stay on the anchor
path and the assertion should hold as an identity. If any parametrisation of
`test_the_handoff_puts_the_source_where_the_scorer_did` ever lands on a fixture where the anchor
declines, that assertion now compares `None` against a dict and fails. Naming it as the one place
the new gate is directly observable by an existing test.

---

## 5. Runtime verification still required

1. **The confirm round-trip on a no-index unit** (H1). Only a run can show what
   `wafer_map_metadata.grid_metadata` holds after confirming
   `DT-EQP-02_20260512T0000_T09` against `valid_die_ref/QA_MAP2`, and whether reopening that map in
   the editor seats the dies where the alignment screen drew them. The oracle already exists:
   `server/tests/oracle/editor_origin_box_oracle.mjs`. There is no test for the `elif shift` branch
   with a `valid_die_ref` basis — `test_the_written_start_is_where_the_editor_redraws_it` covers the
   anchor branch (32 combinations) only.
2. **`test_map_alignment.py:2317`** as described above.
3. **Whether the search saturates on the reported live unit.** §9.9 reports 72 cells and
   `value_agreement` 51–72 but does not report whether the eight shifts were distinct. If they
   saturate, the drawn picture is a tie-break and H2 is not a hypothetical.
4. **Client harnesses**: `map2_placement_seat_harness.mjs` and `map_editor2_shell_harness.mjs` use
   synthetic placements and should be unaffected, but I did not run `node --check` or the harnesses
   this lane.

---

## 6. Documentation integrity

- ❌ **§9.9 does not reference §9.7-ter ⏳①** (`MAP_ALIGNMENT_SPEC.md:887`), the open item it
  activates. See H1. This is the single most important documentation fix in this review.
- ❌ **§9.9 understates the affected population** — "순번이 하나도 없는 단위" is one of three
  reasons `anchor_cell` fails to stand. See M1.
- ❌ **§9.9's ⚠️ "클라 변경 없음" bullet names one stale comment site; there are four.** See M2.
  The project's own lesson (`brief-the-claim-not-the-sites`) is that copies of a wrong sentence
  outnumber the ones you know about.
- ⚠️ **§9.9 is honest where it matters most**, and this deserves recording: the parenthetical about
  offset `(0,0)` saturating and therefore certifying a shift-dropping implementation is exactly the
  kind of self-incriminating note that makes a regression net trustworthy. Same for the note that
  `rot0_front` is *absent* from `test_the_index_path_still_pivots_on_the_minimum_index_die`'s
  parametrisation because the two pivot rules coincide there.
- ❌ **`CODE_MAP.md:1928` was not updated** for `search_pivot_of` / `_placement_payload`. See L1.
- ✅ **No contradiction found with the rest of `MAP_ALIGNMENT_SPEC.md`**, which three lanes edited in
  the last day. §9.7-ter's line 873 ("탐색 배치에서는 `shift`가 평행이동 **전부**이므로
  `start_for_placement`가 옳고") and §9.9's `ruling["anchor"]` bullet agree; line 875's
  "앵커 쌍이 확정 경로에 도달하는 길" is still accurate because the gate preserves it; line 867's
  table entry for `start_for_placement` ("⚠️ 탐색 배치에서는 옳다") is consistent. The §"`no_winner`의
  문장" section at `:498-503` (「`ruling.index_axis == absent`와 `anchor_reason == no_index_values`가
  함께 나오면 …」) also survives — the change does not touch either token.
- ✅ `docs/process/DOC_OWNERSHIP.md:93` routes `map_alignment.py`'s confirmation surface to
  `architecture/data_model.md §4-bis` and `spec/MAP_ALIGNMENT_SPEC.md`. Nothing in this commit
  changes the stored shape, so `data_model.md` needs no edit **unless** H2's recommendation
  (persisting `ruling.placement`) is adopted — in which case it does.

---

## 7. Proposed lessons for `agent_workspace/memory/qa-reviewer.md`

(Proposal only, per the operating rule — not added.)

- **함정**: 검수 중에 대상이 커밋되면 `git diff`가 비어 「변경 없음」으로 읽힌다.
  **올바른 방법**: 착수 시 baseline SHA와 대상 파일 목록을 고정하고, diff가 비면 `git log`로
  **누가 언제 커밋했는지**부터 확인한다. 공유 트리에서는 대상이 움직인다.
- **함정**: 「무엇이 새로 가능해졌나」만 보고 「무엇이 더 이상 막혀 있지 않나」를 안 본다.
  **올바른 방법**: 화면에 안 그려지던 것이 그려지면, 그 화면의 **쓰기 버튼**이 무엇을 새로
  도달 가능하게 하는지를 별도 가설로 세운다. 스펙의 ⏳/미해결 항목을 grep해 **이번 변경이 그중
  하나를 활성화하는지** 확인한다.
