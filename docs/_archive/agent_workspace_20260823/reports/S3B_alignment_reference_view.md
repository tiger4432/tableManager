# S3B - Alignment reference-view payload (`GET /api/maps/alignment/view`)

Read-only. Nothing staged, nothing committed, no process started or stopped.
Measured 2026-08-05 against production `assy_manager`, every connection `SET TRANSACTION READ ONLY`.

Files: `server/map_alignment.py` (new, 615 lines), `server/main.py:4159` (new route, +1 import at
`:4118`), `server/tests/test_map_alignment.py` (new, 23 tests).

---

## 1. Endpoint

```
GET /api/maps/alignment/view
      ?rule=<enrichment rule name>          # decision unit declaration; decision_key IS the unit
      &map_table=<table>                    # its map_key_columns define the map unit
      &params=<urlenc JSON {key: value}>    # decision_key columns ONLY (else 400)
      &reference=<table>:<map_id>           # optional; omitted -> the maps' valid_die_ref; else absent
      &include_cells=<bool>                 # false -> counts and scorings only
```

`params` validation is byte-for-byte the rule the existing `/enrichment/rules/{r}/references/{i}`
uses (`main.py:4547-4553`), so there is one spelling of "which keys may a caller bind".
Nothing about the unit is hardcoded: `decision_key` comes from `enrichment_rules.json`, the map
unit from the map table's own `map_key_columns`.

## 2. Payload schema

```
unit       {rule, decision_key{}, source_table, map_table, map_key_columns[]}
state      "scored" | "no_winner" | "not_scorable"      ("computing" declared, never emitted -
                                                          the route is synchronous; see cuts)
refusal    Korean sentence composed BY THE SERVER, or null when there is an answer
reference  {state: "resolved"|"absent"|"refused", source, table, map_id, count, reason,
            truncated, cells[[x,y]]}
sources    {map_count, usable_map_count, cell_count, truncated, cell_cap,
            cells[[x,y]], maps[{map_id, cell_count, declared_frame}]}
candidates [ 8 x {frame, rotation, side, state, shift{dx,dy}, agreement, discriminating,
                  placed, margin, reason} ]
ruling     {winner, margin, reason_code, tied[]?}
excluded   [{reason_code, reason, count, example_map_id, example_detail}]  + excluded_total
stats      {scored_cells, truncated, cell_cap, shift_window, reference_cells,
            source_maps_usable, elapsed_ms, build_ms}
```

All eight scorings ship in one response, so candidate switching is a repaint.
**No metric is a ratio** - `agreement`, `discriminating`, `placed`, `margin` are ints; a test
asserts no float and no `pct`/`percent`/`ratio` key can appear on a candidate.

`margin` is agreement minus the best of the other seven, in cells. `discriminating` is the count
of that candidate's agreeing cells whose in-reference answer is **not** the same across all eight
candidates - the direct implementation of spec section 1 (the circle is invariant under all eight
frames, so only the occupied subset can break a tie). A candidate with high agreement and zero
discrimination cannot win; that is asserted.

## 3. Real responses (route exercised in-process via the ASGI app against production)

I did not restart or bind anything - requests go through the real route, real serialization, real
database, in the same process. Byte sizes are the actual response bodies.

| case | unit | reference | HTTP | bytes | state |
|---|---|---|---|---|---|
| 1 | DT-EQP-01/PRD-A | `dt_map:a_01` (resolved, 81 cells) | 200 | **25,334** | `not_scorable` |
| 1b | same, `include_cells=false` | same | 200 | **6,499** | `not_scorable` |
| 2 | DT-EQP-01/PRD-A | none -> **absent** | 200 | **22,632** | `not_scorable` |
| 3 | DT-EQP-02/PRD-B | none -> **absent** | 200 | **11,926** | `not_scorable` |
| 4 | DT-EQP-01/PRD-A | `valid_die_ref:NOPE` -> **refused** | 200 | 22,611 | `not_scorable` |
| 5 | DT-EQP-01/PRD-A | `valid_die_ref:CORE_YINV` (resolved, 927) | 200 | 31,921 | `not_scorable` |
| guard | non-decision-key param | - | **400** | 79 | - |
| guard | unknown rule | - | **404** | 53 | - |

**Size verdict: the design holds.** The largest full payload is 31.9 KB carrying 2,889 source
cells + 927 reference cells + all 8 scorings; the list-view form is **6.5 KB**. For scale, the
8 scorings themselves are ~1.5 KB of that - the cells dominate, and `include_cells=false` is the
lever. This is not a second `dt_log_frame_attribution` (81 KB per page of nothing): 6.5 KB buys
the entire decision, and 25-32 KB buys it with both cell layers for painting.

Build time 78-719 ms per unit (40 maps, 2,889 cells, 8 candidates x 49 shifts).

**The refusal, exactly as it appears on the wire (case 2, `"refusal"` field):**

```
이 단위에 정렬 기준(공통 바닥)이 선언되지 않았습니다 ― 유효 다이 맵을 지정하거나 비교할
다른 맵을 골라 주십시오. 기준이 없으면 후보를 채점할 대상이 없어 여덟 프레임 중 무엇도
배제되지 않습니다.
```

`reference.state` is `"absent"` with `reason: null` and `count: 0`, and **`candidates` is an
empty list** - there is no row of zeros for a client to render as "scored nothing". That was the
explicit requirement and it is what ships.

Case 5's sentence names the actual cause instead of blaming the data:

```
여덟 후보 전부가 기준 맵으로 변환되지 않았습니다 ― physical grid dims differ:
source 13x13 vs target 45x39 ...
```

That sentence exists because exercising the endpoint found the defect: with a reference resolved
and sources present, all 8 candidates were refused by `make_frame_transform` on grid dims, and the
first version answered "there are no coordinates to score" - which sends the operator to inspect
data that is fine. Fixed at `map_alignment.compose_refusal`, and pinned by
`test_a_transform_that_refuses_every_candidate_says_so_rather_than_blaming_the_data`.

## 4. What I proved

- **The planted frame is recovered.** `test_the_planted_frame_wins` re-expresses a reference in a
  known frame and requires the scorer to name it back, for `rot90_front`, `rot180_front`,
  `rot270_front`, `rot0_back`. It runs through the real `make_frame_transform` /
  `_frame_phys_params` stack.
- **The full-meta premise is honoured.** A spy asserts all 8 rotation/side pairs reach the
  transform builder separately. Mutation B (one transform reused for all candidates) turns all
  four planted-winner cases red.
- **Ties are not broken.** A symmetric occupied set yields `winner: null`, `reason_code` `tie` or
  `no_discrimination`, with agreement still high - the point being that a high score is not a win.
- **The bbox basis is never varied.** A test asserts `_FRAME_TF_CACHE` only ever contains keys
  that are `frame_axes` of metas actually passed in, so this module cannot hand the next caller
  someone else's box through the basis-free cache key.
- **The vocabulary has one spelling.** The 8 candidates are composed from axes and validated
  through the existing `dt_map_derivation.parse_frame`; a frame that acceptor rejects cannot
  become a candidate.

**A fixture bug I caught by scoring the fixture, worth recording.** My first reference set clipped
`{(3,3), (3,4), (4,3)}` - symmetric under transpose, and transpose is one of the eight frames. The
scorer correctly reported a two-way tie on every planted frame and it read as a scorer bug. I then
measured the composed mappings over the full grid: **8 distinct of 8** on the production dt_map
spec (13x13, chip 7x7, offset 0) and on four other specs including the decentred section-2 fixture
- so the transforms were never aliased, the fixture was. `test_the_fixture_has_no_symmetry` now
scores the fixture under the dihedral group so this cannot recur silently.

**Mutations** (monkeypatch plugin, `pytest_sessionfinish` re-probes after the last test):

| | mutation | result | still mutated at finish |
|---|---|---|---|
| baseline | none | 23 passed | False |
| A | drop the discrimination requirement from the ruling | **3 failed** | True |
| B | one transform for all 8 candidates | **4 failed** | True |
| C | add a coverage percentage to each candidate | **1 failed** | True |

Note B did *not* kill the spy test (the spy patches the same symbol the mutation does); the
planted-winner tests are what catch it. A guard that can be neutralised by the thing it guards is
worth knowing about.

## 5. Production facts this surfaced

- The 4 live units are `(DT-EQP-01|02) x (PRD-A|B)` with 40/20/40/20 jobs and 2,889/1,446/2,892/
  1,473 `dt_log` rows. All 120 `dt_job` values resolve to a registered `dt_map` meta.
- **No unit has a resolvable reference.** `valid_die_ref` holds products `TEST/CORE/5N`, while
  `dt_log` carries `PRD-A/PRD-B`. Combined with the 8 declarations that resolve to zero and the
  320 auto-registered maps already refused, `reference.state = "absent"` is the normal state.
- **No dimensionally compatible reference exists in production at all.** The units' source maps
  are 13x13 (352 of 668 metas are 13x13); the only `dt_map` map carrying cells is `a_01` at 23x23,
  and `valid_die_ref:CORE_YINV` is 45x39. So every scorable path in production currently ends in a
  named refusal - which is precisely the gap this screen exists to close.

## 6. What I cut for time, and what I did not run

1. **No production response in the `scored` state** - not a shortcut, an absence: no registered map
   with cells shares the units' 13x13 spec (section 5). The scored path is proven by
   `test_the_planted_frame_wins` through the real transform stack instead. Cases 1/4/5 exercise
   the three distinct `not_scorable` causes for real.
2. **`computing` is declared but never emitted.** The route is synchronous. I left the token in the
   closed vocabulary rather than pretend the state exists; if the client wants progressive
   rendering, that is a second round.
3. **Shift search is a bounded window (`SHIFT_WINDOW = 3`, 49 offsets/candidate)**, not a global
   argmax over the difference histogram. Declared in `stats.shift_window` on every response. A
   true misalignment beyond 3 cells would be scored as a miss rather than found.
4. **Not exercised over a real socket** - requests go through the ASGI app in-process. The route,
   validation, serialization and DB are real; only the TCP hop is not. I did not bind a port
   because the instruction not to disturb running processes outranked the nicety.
5. **Full suite still running** at the time of writing; the alignment and orientation modules pass
   (23 + 52). Result to follow.
6. `map_overlay.make_frame_transform`'s existing refusal text contains an em-dash (U+2014) and my
   composed sentence embeds it verbatim rather than editing a message I do not own. My own
   sentences use U+2015. Worth a separate one-line fix.

---

## 7. Client `ROUTES` divergence - NOT silently conformed (needs your ruling)

`client2/src/map2/api.js:38-45` expects `/map/align/{reference,worklist,config,confirm}`.
I did not implement them tonight, because conforming would bake in four decisions I should not
make alone:

| # | conflict | why it is not a rename |
|---|---|---|
| 1 | **Path** `/map/align/*` vs every other map route at `/api/maps/*` | cosmetic, but picking silently creates two conventions. Your call; I will follow either. |
| 2 | **`?eqp=&product=`** vs my `?rule=&params={...}` | the rule declares `decision_key = ["dt_eqp","product"]`. `eqp` is **not** a column. Accepting it hardcodes the decision key into the server and undoes the reason the declaration exists. |
| 3 | **No `map_table` / `reference` params** on the client | the server would have to invent both. Defaulting `map_table` is a hardcode; defaulting the reference is worse - it is the pluggable floor. |
| 4 | **`stored_candidate_id`** on the unit and each source | that is layer 8 (the only writing layer). My payload is read-only by contract; `confirm` is the write route and it is not mine tonight. |

Field-name deltas, all mechanical once 1-4 are settled: `floor_cells`/`reference.cells`,
`per_candidate`/`candidates`, `occupancy_winner_id`/`ruling.winner`, `refusal_detail`/`refusal`,
and per-source cell lists vs my pooled `sources.cells` + `sources.maps`.

**One delta I recommend keeping mine:** cells as `[x, y]` pairs, not `{x, y}` objects. At 2,889
source cells that is roughly 40% of the cell payload. It is the difference between a 25 KB and a
~35 KB response, and cells dominate the budget.

## 8. Byte sizes after `reference_kind` (for the 13 ms paint budget)

| response | bytes |
|---|---|
| unit + resolved reference + both cell layers + 8 scorings | **25,307** |
| same, `include_cells=false` | **6,473** |
| unit, reference absent, source cells | 22,415 |
| smaller unit (20 maps), reference absent | 11,708 |

The 8 scorings are ~1.5 KB of that. Real scorings will not move these numbers - cells do.

## 9. `reference_kind` and the register fix (both landed)

`reference.kind` is now sent explicitly: `none` | `occupancy` | `values`, decided from whether the
resolved binding actually has a value column. Verified on the wire: case 2 `none`, case 5
`values`. The client should delete its inference.

Refusal strings converted to nominal register, facts kept:

```
기준 없음 - 유효 다이 맵 미지정
칩 규격 미선언 - 좌표 변환 불가
8후보 전부 변환 거절 - physical grid dims differ: source 13x13 vs target 45x39 ...
동점 - 판별 불가
기준 발자국이 대칭 - 8프레임 구별 불가
```

No thresholds are emitted anywhere in this payload, so the `Number(null) === 0` hazard has no
surface here. When `/map/align/config` is built it must omit absent thresholds, not zero them.

Full suite after all of this: **2,293 passed, 1 failed, 6 skipped** (417s). The one failure is the
pre-existing unrelated `test_dual_stack_bind.py::test_the_launcher_default_is_the_dual_stack_host`
(`ModuleNotFoundError: run_decoupled_app`).

---

## 10. The stored declaration (your point 3) - added, and it found something

`declaration` is now a top-level block, plus `declared_by_maps` (a count) on each candidate.
Named to keep your distinction structural: **declaration = what someone wrote down**, confirmation
= what someone decided. No confirmation field exists in this read-only payload.

```
declaration: {frames: {<frame>: <map count>}, unanimous, frame, attested_maps,
              unattested_maps, axis_sources: {rotation: {...}, side: {...}}}
candidates[].declared_by_maps: <count of the unit's maps whose meta declares this frame>
sources.maps[].declared_frame / .declared_frame_source
```

**It is a count per frame, not one badge**, because the unit's maps can disagree - that
disagreement is the reason this screen works at unit granularity at all. One badge would have to
pick a winner among declarations, which is a judgement the client must not make.

**And it must not be driven by the raw value.** `rotation:0, side:"front"` is what the registrar
and the ingestion scripts write with nobody looking, so a badge on the raw string would put
`현재` on maps that were never measured - I4 exactly. So the block is gated on the D2 provenance
token, and only `declared` maps are tallied.

**What that produced on the only live unit (DT-EQP-01/PRD-A, 40 maps), measured on the wire:**

```
"declaration": {"frames": {}, "attested_maps": 0, "unattested_maps": 40,
                "axis_sources": {"rotation": {"declared": 40},
                                 "side": {"indeterminate": 40}}}
```

All 40 maps write `rot90_front`. **Rotation 90 is a real declaration** - no default path emits it.
**`side: "front"` is not** - it is the reader's absent-default. So the pair is honestly unattested
and no `현재` badge is earned, and that would have been the whole answer if I had shipped only the
combined token. That would have thrown away a rotation declaration which on its own **narrows 8
candidates to 2**. Hence `axis_sources`: the verdict uses the combined token, the screen gets the
axes. The screen can say "회전만 선언됨" instead of showing nothing.

Per-map axis dicts were built and then removed: they cost **6,473 -> 11,171 bytes** (+72%) on the
no-cells payload for 40 repetitions of the same two words. The unit-level tally carries the
distribution and `maps[].declared_frame_source` still says which individual maps are unattested.

Final sizes: **27,244** bytes with both cell layers, **8,411** without (the +1.9 KB over the
earlier 6,473 is the declaration block plus one provenance string per map). Tests: 27 in
`test_map_alignment.py`, 52 in `test_orientation_declaration.py`, all passing.
