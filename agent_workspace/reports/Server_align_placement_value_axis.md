# Server — the aligner scored on the value axis but shipped nothing drawable

Base: `34d2518`. Files touched: `server/map_alignment.py`, `server/tests/test_map_alignment.py`,
`docs/spec/MAP_ALIGNMENT_SPEC.md` (new §9.9). Nothing committed, nothing staged.

---

## 1. THE MEASUREMENT (line numbers are HEAD `34d2518`)

The brief asked three questions before any repair. **Two of the three answers contradict the
brief**, and one of them would have made the prescribed repair a no-op.

### Q1. When `anchor_cell is None`, what pivot does the scoring loop use?

**There is no pivot. It takes a different branch entirely.** `:2954-2964` is the `else` of
`if anchor_cell is not None`, and it builds two absolute transforms:

```python
tf  = map_overlay.make_frame_transform(src_meta, reference_meta)
ptf = map_overlay.make_physical_transform(src_meta)
```

Then at `:2966-2972` the placement is `p = tf(x, y)` — an affine map through the whole
phys/box/start stack, not a difference from any reference point. The anchor branch's
difference formula (`:2967-2970`, `anchor_cell + L·(cell − anchor_cell)`) is not reached.

### Q2. What are `c["_linear"]` and `c["_anchor_placed"]` in that branch?

**Both are None**, and this is where the brief is wrong.

- `frame_linear` is initialised `None` at `:2903` and assigned **only** at `:2952-2953`, inside
  `if anchor_cell is not None`. On the search path it is never assigned.
- `anchor_placed` is initialised `None` at `:2905` and assigned **only** at `:2987-2989`, whose
  condition begins `anchor_cell is not None`.

So the brief's line — *"The value/shift path computed both and threw the drawable form away"* —
is false as stated: it computed **neither**. And the prescribed repair, *"move the gate from
`anchor_cell` to `_linear`"*, would have changed nothing at all: all three operands of the
`:3391` expression are None together on this path. It would have shipped as a green no-op.

What is true is the conclusion, by a different route: the search path holds an **affine**
transform, and an affine transform is a linear part plus an offset. The linear part is
recoverable from the same `src_meta`/`reference_meta` the transform was built from, and the
offset is recoverable from any single placed cell. So the drawable form was **derivable**, not
discarded.

### Q3. Where do `dx`/`dy` come from, and are they already folded in?

From `_solve_shift(c["keys"], ref_sorted, shift_window)` at `:3107` — a brute-force sweep over
±`shift_window` maximising overlap, ties broken toward the origin.

**They are NOT folded into what the scorer placed.** `keys = _encode(placed)` (`:3012`) encodes
the pre-shift coordinates, and every consumer applies the shift separately at compare time:
`_membership(c["keys"], ref_sorted, dx, dy)` at `:3112` (which computes
`keys + dx*_KEY_STRIDE + dy`, `:1204`), the value axis at `:3224`, the canonicalisation at
`:3129`. So the seat scoring actually used is exactly

```
seat = tf(cell) + (dx, dy)
```

### What this makes exact — and why no pivot had to be invented

`tf` is affine with linear part `L`, and that identity is not my assumption: the existing oracle
`test_the_linear_part_matches_the_transform` (`server/tests/test_map_alignment.py:2509`) asserts
`tf(cell) == tf(CELLS[0]) + L·(cell − CELLS[0])` across all eight frames and both y-invert flags.
Therefore, **for any pivot `q`**:

```
seat(cell) = tf(cell) + shift = [tf(q) + shift] + L·(cell − q)
           = anchor_ref      + L·(cell − anchor_src)
```

The brief's warning — *"`anchor_ref` must be where scoring actually seated the map, not a fresh
derivation"* — is honoured in the strong sense: `anchor_ref` is captured off the scoring loop's
own `p`, at the line that places the cell. The pivot choice cannot move the map (it cancels
algebraically); the seat is the measured one. On the anchor path the pivot is load-bearing
because it *decides* the translation; here it is only the point the reconstruction hangs off.
That asymmetry is why a second pivot rule is admissible at all, and it is written down at the
rule itself.

---

## 2. A DEFECT THE BRIEF DID NOT ANTICIPATE — `ruling.anchor` is derived from `placement`

`ruling["anchor"] = (_win_row or {}).get("placement")` (HEAD `:3620`). The brief lists
`ruling.anchor` under MUST NOT CHANGE, and the first version of my change silently changed it —
the new test caught it on the first run, with `ruling.anchor` populated on a payload whose
`anchor_reason` was `no_index_values`.

This is not cosmetic. `ruling.anchor` is **not read for drawing** — it is read for
**confirmation**: `frame_confirmation._placement_of` (`server/frame_confirmation.py:798-803`)
lifts `anchor_src`/`anchor_ref` out of it and hands them to `start_from_placement`, whose whole
derivation assumes *the rest of the translation lives inside the anchor pair* (spec §9.7-ter;
the alternative wiring's measured failure was 240 of 240 cells displaced by (4,3)). A
search-path placement has no such pair — there the shift carries the entire translation. So
shipping it under the name `anchor` would have re-bought that exact defect at confirm time.

Fixed by gating that key on `anchor_cell is not None`, which reproduces the old value exactly
(when `anchor_cell` was None the old `placement` was always None, hence the old `ruling.anchor`
was always None).

---

## 3. THE CHANGE

`server/map_alignment.py`:

| line | what |
|---|---|
| `1879` | **`search_pivot_of(usable)`** — new, placed directly beneath `anchor_cell_of` so both pivot rules are read together. Minimum `(y, x)` in stored source coordinates; returns `(map index, cell index, (x, y))`; **None unless exactly one map contributes cells**. Identity travels as the cell index, so a repeated coordinate cannot make the capture ambiguous. |
| `1927` | **`_placement_payload(linear, anchor_src, anchor_placed, dx, dy)`** — the drawable form spelled once. Both paths emit through it, so `anchor_ref = seat + shift` exists in one place. |
| `2955` | `_pivot` computed **only when `anchor_cell is None`**, so the two paths are mutually exclusive by construction rather than by careful ordering. |
| `3050` | `search_linear = frame_linear_part(src_meta, reference_meta)` for the pivot's map, in the `else` branch only. |
| `3081` | `search_placed = p` captured at the placing line, matched by cell index. |
| `3114` | `_search_linear` / `_search_placed` stored under **separate keys** — the index path's `_linear`/`_anchor_placed` are not shared, so "unchanged" is structural and not a claim. |
| `3501` | the emitter: anchor path first, search path in the `else`. |
| `3627` | `ruling["anchor"]` gated on `anchor_cell is not None` (§2 above). |

Nothing reads the two new keys except the payload. Scores, shift, thresholds, ruling, stats,
the candidate list and `ruling.placement`/`ruling.anchor_reason` are untouched — verified by
byte comparison, §4A.

`docs/spec/MAP_ALIGNMENT_SPEC.md`: new **§9.9** records the live payload, the two pivot rules
and why they differ, the `ruling.anchor` restriction, and the fixture trap in §4C.

**No client change.** `client2/src/map2/decode.js:341-360` passes the candidate's `placement`
through untouched and `main.js:2363` `placementFor` reads only that field; its no-fallback rule
is intentional and stays. (One stale sentence noted, not touched: `main.js:2357` still describes
`anchor_ref = reference_top_left + (dx, dy)`, a server formula retired on 2026-08-06. The
behaviour it prescribes — never add `shift` on top of `anchor_ref` — remains correct.)

---

## 4. VERIFICATION

### A. The index path is byte-identical to HEAD

HEAD's `map_alignment.py` was extracted verbatim (`git show HEAD:… > server/_head_probe_ma.py`,
deleted afterwards) and run beside the working tree on the same fixtures — same process, same
`map_overlay`, so any difference is this change. Full payload (`candidates` + `ruling` + `stats`)
compared as sorted JSON:

```
== A. WITH index values - must be byte-identical ==
  rot0_front     identical=True  len(head)=6936 len(now)=6936
  rot0_back      identical=True  len(head)=6945 len(now)=6945
  rot90_front    identical=True  len(head)=6983 len(now)=6983
  rot90_back     identical=True  len(head)=6983 len(now)=6983
  rot180_front   identical=True  len(head)=6976 len(now)=6976
  rot180_back    identical=True  len(head)=6965 len(now)=6965
  rot270_front   identical=True  len(head)=6966 len(now)=6966
  rot270_back    identical=True  len(head)=6964 len(now)=6964
  ALL EIGHT IDENTICAL: True
```

One field is excluded and named: `stats.elapsed_ms`, a wall clock (HEAD 266–781 ms vs NOW
265–953 ms across the same eight runs). It was the **only** difference before exclusion —
`ruling diff: []` and zero candidate-field differences on all eight.

### B. The reported case, before and after

```
== B. NO index values - the reported case ==
  planted rot0_front
    HEAD placements non-null: 0 / 8   ruling.anchor=None
    NOW  placements non-null: 8 / 8   ruling.anchor=None
    ruling keys that moved: NONE
    candidate keys that moved: ['placement']
    stats diff: []
    reconstruction (frame, occ_ok, val_ok, agreement, value_agreement):
      ('rot0_front', True, True, 266, 266)
      ('rot0_back', True, True, 266, 11)
      ('rot90_front', True, True, 266, 0)
      ('rot90_back', True, True, 266, 4)
      ('rot180_front', True, True, 266, 0)
      ('rot180_back', True, True, 266, 0)
      ('rot270_front', True, True, 266, 0)
      ('rot270_back', True, True, 266, 5)
```

(`rot90_front` and `rot270_back` plantings give the same shape, rotated.) `occ_ok`/`val_ok` are
the client's formula fed the server's three numbers, counted against the floor. The value column
is what makes this an assertion rather than a smoke test: it separates 266 from 0/4/5/11, so a
placement that drew the map anywhere else could not reproduce it.

### C. 🔴 The fixture trap, and why the offset case exists

Measured on the 41×41 / 266-cell partial map at offset `(0,0)`: **all eight candidates settle on
`shift {dx: 0, dy: 0}`** — the search saturates (every subset of the valid dies sits on valid
dies under every frame) and the tie-break returns the origin. On that fixture a placement that
**dropped the shift entirely** reproduces every count and the test certifies it green.

So the test carries a second fixture with the source translated by `(5, -4)`, where the search
solves real shifts (`dx, dy ∈ {−3, +3}`, occupancy 196/266), plus an in-test guard asserting the
shifts are not all zero there.

Mutation results — both alarms rung before delivery:

| injected defect | result |
|---|---|
| `anchor_ref` built without the shift (`_placement_payload(…, 0, 0)`) | **8 failed, 8 passed** — every failure is an `offset1` case; every `offset0` case passes. The trap above, demonstrated. |
| pivot identity off by one (`i == pivot_i + 1`) | **14 failed, 2 passed** |
| *(no injection)* | 20 passed |

### D. Test output

```
$ conda run -n assy_manager python -m pytest server/tests/test_map_alignment.py -q \
    -k "draw_when_no_die or minimum_index_die or refuses_two_maps"
20 passed, 237 deselected, 6 warnings in 2.64s

$ conda run -n assy_manager python -m pytest server/tests/test_map_alignment.py -q
254 passed, 3 skipped, 6 warnings in 66.83s (0:01:06)
```

Full suite: see §7.

New tests, all in `server/tests/test_map_alignment.py`:

- `test_the_screen_can_draw_when_no_die_carries_an_index` — 8 frames × 2 offsets. Asserts the
  fixture is genuinely on the search branch (`ruling.anchor is None`,
  `ruling.placement == shift_search`, `index_axis == absent`) before asserting anything else, so
  it cannot pass by taking the anchor path.
- `test_the_index_path_still_pivots_on_the_minimum_index_die` — the anchor path pivots on the
  minimum-index die and not on minimum-`(y, x)`. `rot0_front` is **excluded and the exclusion is
  the point**: there the two rules pick the same cell, and the in-test guard fails rather than
  passing vacuously. The remaining three frames are ones where they disagree.
- `test_the_search_pivot_refuses_two_maps` — the one-map restriction, the empty-map skip, and the
  `(y, x)` ordering.

### E. Standing instruction on `QA_MAP`

Not applicable to these tests and not violated. The suite's `_valid_die_floor` is not a synthetic
stand-in for a valid-die map — it is **the whole wafer's valid dies** derived through
`map_overlay`'s own transformer, which is the shape the standing instruction protects (the
failure it names is a basis off by 3 dies). These tests take no database. The live `QA_MAP`
payload is quoted in §1 as the reported case; I did not re-query it (no live DB reading was
needed to answer the three questions, and this box is not production).

---

## 5. WHERE I WOULD LOOK IF THIS IS WRONG

For the adversarial passes, the three places this could still be wrong:

1. **`frame_linear_part` vs the transform actually run.** I take `L` from declared axes rather
   than probing `tf` at three points. They are identical by oracle across 8 frames × 4 invert
   combinations — but the oracle uses one meta shape. If a source ever reaches the search branch
   with a meta whose axes `frame_linear_part` reads differently from what `_frame_transformer`
   builds, the placement would be wrong while every score stayed right. Probing `tf` directly
   would remove the dependency at the cost of two extra transform calls.
2. **Multi-map units get no placement.** Honest, but it means a two-source unit still draws
   nothing. Whether the screen should draw one map and name the other's absence is a product
   call, not mine.
3. **`stats.elapsed_ms` excluded from the byte comparison.** Named rather than hidden; if a
   reviewer wants it in, the comparison must then be run on a quiesced box.

## 6. PROPOSED MEMORY ENTRY (for lead-PM review, not added by me)

> **함정**: 지시서가 「이 값은 계산돼 있는데 버려진다」고 단정하면 그 문장을 전제로 관문만 옮긴다.
> 2026-08-08: `_linear`은 탐색 갈래에서 **계산되지 않았다**(앵커 갈래에서만 대입된다). 지시받은
> 대로 관문을 `anchor_cell` → `_linear`로 옮겼다면 세 피연산자가 함께 None이라 **아무것도 안
> 바뀌면서 테스트는 초록**이었을 것이다.
> **올바른 방법**: 「이미 있다」는 주장은 **대입문을 찾아** 확인한다 — 읽는 자리가 아니라 쓰는
> 자리다. 그리고 관문을 옮기기 전에 **관문 뒤의 값이 실재하는지**를 먼저 센다.

## 7. FULL SUITE

_(appended below — see the final line of this report)_
