# Server — Align consolidation: `wafer_map_metadata` as the single source of alignment

**Date:** 2026-07-27 · **Agent:** Server PM · **Board:** #20 (and the old A2) · **Branch:** `main` (not committed)
**History:** [`docs/history/20260727_004500_align_consolidation_meta_single_source.md`](../../docs/history/20260727_004500_align_consolidation_meta_single_source.md)

---

## Headline

Three coordinate-transform implementations are now **two**: `client2/src/map_editor.js` (rendering)
and `server/map_overlay.py` (everything server-side). `bonding_plan`'s copy is deleted, and the
surviving server implementation now has real production consumers instead of only its own tests.

Two is the floor, and I am not claiming otherwise. Availability is computed server-side
(`/api/bonding-plan/core-summary`, `/api/transfer-plan/source-summary`), so the server needs a
transform; the canvas renders in the browser, so the client needs one. Collapsing to one would
mean either shipping cell coordinates to the browser for every availability query, or rendering
server-side. Neither is on the table. **The remaining duplication is between a Python transform
and a JavaScript transform of the same algorithm — that is a real risk** (they have drifted
twice: QA B1 and A1), and it is now guarded by `test_map_overlay.py`'s independent oracle, which
transcribes the *client's* storage convention and shares no layer with the Python code.

---

## The premise in the task was wrong, and it mattered

> "Dormant only because no `align` is declared live."

**Two live `align` declarations exist**, both on `eds_fail_map`:

| file (gitignored user asset) | path | value |
|---|---|---|
| `server/config/bonding_plan_config.json` | `sources.eds_fail.align` | `{default: {rotation: 180, flip: none, offset: {0,0}}, by_eqp: {}}` |
| `server/config/transfer_plan_config.json` | `stages.bonding.source.fail_sources.eds_fail.align` | same |

Only `map_overlay_config.json`'s `align_overrides` was genuinely dormant — its single key is
`__example_eds_fail_map`, which matches no table.

So the unfixed copy was **running in production**, on the exact path the user relies on:
`/api/transfer-plan/source-summary` (called by `client2/src/transfer_plan.js:321`) →
`transfer_plan._canonical_fail_set` → `bonding_plan.make_align_transform`.

**And the declaration was redundant with the metadata.** A read-only query against the live
PostgreSQL shows:

```
core_defect_map / LOT-*  : 40x40, start(1,1), rotation 0,   side front, chip 7x7, dia 300, margin 3
eds_fail_map    / LOT-*  : 40x40, start(1,1), rotation 180, side front, chip 7x7, dia 300, margin 3
```

The metadata delta is exactly 180 — the number the config declared by hand. That is the user's
domain rule demonstrating itself: the declaration layer was a hand-maintained copy of a fact the
metadata already carried.

---

## The disagreement finding (the two implementations do NOT agree in general)

I compared them cell-by-cell before switching.

| spec | wafer bbox `(minC,maxC,minR,maxR)` | old copy vs `map_overlay` |
|---|---|---|
| **live** 40×40, chip 7×7, dia 300, margin 3 | `(0, 39, 0, 39)` | **1288 / 1288 agree** |
| 29×25, chip 11×13, dia 300, margin 3, rot 180 | `(2, 26, 2, 22)` | **425 / 425 disagree**, uniform `(4, 4)` |
| same spec, rot 90 | `(2, 22, 2, 26)` | 425 / 425 disagree, uniform `(0, 4)` |
| same spec, back only (rot 0) | `(2, 26, 2, 22)` | 425 / 425 disagree, uniform `(4, 0)` |
| same spec, rot 270 + back | `(2, 22, 2, 26)` | **agree** — terms cancel |

### Which is right, and why (physical-coordinate reasoning)

A stored cell coordinate is **not** `cell index + start`. The client writes
`xv = c - box.minC + start_x`, where `box` is the bounding box of the cells whose full die
footprint lies inside the wafer circle (`WaferMapCoordinateTransformer.cell_to_visual`). In
physical terms: `x` counts columns **from the first column that contains any in-wafer die**, not
from the grid's left edge. The wafer is round; the grid is rectangular; the corners are empty.

`map_overlay.make_frame_transform` goes `visual → physical → visual` through that same layer, so
the `minC` term is applied on the way in and removed on the way out.
`bonding_plan.make_align_transform` inverted with `c = x - start_x`, dropping the term entirely.

Write the composite as `xv_dst = L·xv_src + K`. The two omitted terms are `+minC_src` (entering)
and `-minC_dst` (leaving). When `L = +1` they cancel; when a mirror makes `L = -1` they add, and
with `minC_src = minC_dst = m` the error is exactly `2m`. That is why rot 270 + back agrees
(its composite linear part is `+1` on both axes) while rot 180, rot 90, and a bare side flip do
not. **`map_overlay` is right; the deleted copy was wrong** — and it was wrong by a uniform
offset, the one error class that single-implementation round-trip tests cannot see.

The live 40×40 spec has `minC = minR = 0` (grid extent 280 mm inside a 294 mm usable circle, so
column 0 still holds in-wafer dies), which is why the live numbers were correct despite the bug.
The bug was not dormant; it was **masked by the live wafer geometry**.

---

## Before/after availability

Isolated in-memory sqlite, seeded to mirror the live specs read off production metadata. Same
seed data both runs (asserted identical); only the code and the config shape differ.

| query | before | after |
|---|---|---|
| `core-summary` LIVE | `total 1288, defect 4, eds_fail 7, used 2, remaining 1275` | **identical** |
| `core-summary` region=full LIVE | `1288 / 4 / 7 / 2 / 1275` | **identical** |
| `core-summary` region=half-plane LIVE | `328 / 0 / 4 / 0 / 324` | **identical** |
| `source-summary` bonding LIVE | `total 1288, defect 4, eds_fail 7, remaining 1277` | **identical** |
| `core-summary` CROP | `425 / 4 / 7 / 2 / 412` | **identical** |
| `core-summary` region=full CROP | `425 / 4 / 7 / 2 / 412` | **identical** |
| **`core-summary` region=half-plane CROP** | `total 250, defect 4, **eds_fail 6**, remaining 240` | `total 250, defect 4, **eds_fail 7**, remaining 239` |
| `source-summary` bonding CROP | `total 425, defect 4, eds_fail 7, remaining 414` | **identical** |

**Every live-spec number is unchanged.** 7 of 8 queries identical; the one change is on the
cropped/anisotropic spec, which does not exist in the live registrations today.

### Why `7` is the right value

Verified against the independent oracle, not against either implementation:

```
seeded EDS fail dies, canonical coords: [(8,3) (8,4) (8,5) (8,6) (8,7) (8,8) (8,9)]
stored in the EDS frame (rot 180):      [(18,13) … (18,19)]
recovered by the surviving transform:   [(8,3) … (8,9)]        <- exact
recovered by the deleted copy:          [(12,7) … (12,13)]     <- all 7 on different dies
per-die delta (old - correct): (4, 4)   == 2*minC, 2*minR
half-plane y <= 12:  correct -> 7    old copy -> 6
```

All seven fail dies really are at `y ≤ 12`; the old copy pushed one to `y = 13` and lost it.

### The part worth staring at

`source-summary bonding CROP` reads **`eds_fail: 7` both before and after** — yet before, every
one of those seven dies was misidentified. The uniform shift moved all seven onto *other valid
dies*, so the count survived intact. A count-only comparison would have reported "no change" and
been useless. This is why the before/after table above includes boundary-sensitive half-plane
probes, and why the new tests assert **die identity** (1×1 rects on each fail die plus a
non-fail control) rather than totals.

---

## What was removed

**`server/bonding_plan.py`** — deleted: `normalize_align`, `make_align_transform`,
`VALID_ROTATIONS`, `VALID_FLIPS`. Moved (not deleted): `align_status_label` → `map_overlay`,
so the module that owns the transform owns its display marker. Added `load_map_meta` (full meta
dict via the config-bound table, request-scoped cache) with `load_grid_meta` kept as a thin
grid-only shim for region clamping. Added `CANONICAL_FRAME_ROLES`.

**`server/map_overlay.py`** — deleted: `align_overrides` resolution, the `by_eqp` branch,
`ALIGN_ORIGIN_DECLARED`, `ALIGN_ORIGIN_DEFAULT`, `_frame_grid_of` (existed only for the declared
path), and the `eqp` argument to `get_overlay`/`resolve_align`. Added `resolve_map_transform` —
one entry point shared by the overlay endpoint and both availability paths.

**`server/transfer_plan.py`** (not in the stated scope — see below) — `_canonical_origin_grid` →
`_canonical_origin_meta`; `_canonical_fail_set` routed through `resolve_map_transform`.

**`client2/src/map_editor.js`** — deleted `probeAlignDeclaration` and the
`align_override_declared` / `align_unconfirmed` refusal paths. Review finding **B3 is closed by
deletion**. Side effect: adding an overlay now costs one fewer REST round trip.

**`.sample` configs** — `align_overrides` (map_overlay), `sources[].align` (bonding_plan),
`fail_sources[].align` (transfer_plan) removed, each with a `__comment` / `__doc__` explaining
why and telling the reader to register the map's metadata instead.

### Scope expansion I had to make — `transfer_plan.py`

The task scoped the server work to `bonding_plan.py` + `map_overlay.py`. `transfer_plan.py` is a
third consumer of the functions being deleted, and it is the one that actually runs live. Leaving
it would have meant *moving* the un-fixed copy rather than deleting it, so I migrated it. Flagging
it explicitly because it was not in the brief.

---

## Verification

### Injected defects — required, and the first attempt failed the requirement

Four defect variants injected into the real sources (byte-exact backup/restore verified by
sha256; `git checkout --` was unusable because other agents have uncommitted work in the same
files):

| injection | what it simulates | tests that failed |
|---|---|---|
| `bbox_less` | drop the bbox term = the deleted copy's arithmetic | **13** (bonding_plan 3, map_overlay 10) |
| `wrong_bbox_source` | use the target's bbox on both sides | **39** |
| `canonical_lost` | `CANONICAL_FRAME_ROLES = ()` | **12** (incl. 3 in transfer_plan) |
| `tp_canonical_lost` | `dst_meta = None` in transfer_plan | **18** |

**My first version of the bonding_plan fixture was worthless and I only found out by injecting.**
It built the seeded EDS coordinates with `map_overlay.make_frame_transform` — the function under
test. Under `bbox_less`, seed and recovery cancelled and **all 20 tests passed**. The fixture now
builds coordinates from `test_map_overlay`'s independent oracle (the client storage convention
transcribed arithmetically, sharing no layer with the implementation), after which 3 of the 4
axis combinations fail as they should.

The fourth (`rot 270 + back`) does not fail, and that is correct, not a gap: its composite linear
part is `+1` on both axes, so the bbox terms genuinely cancel. **A fixture set consisting only of
rot 270 + back would prove nothing** — which is exactly the failure mode the memory file warns
about, arriving from a new direction.

### Fixture defect axes

`test_bonding_plan.CROP_GRID` = 11×9 grid, chip 11×13, dia 100, margin 3, offset (4, 2).
The test asserts its own axes are live, so a future edit that flattens the fixture fails loudly:

- `bbox != 0` — rot 0/front is `(1, 8, 2, 7)`
- `minC != minR` (1 vs 2) — equal values would let an x/y axis confusion pass
- `chip_x != chip_y` — anisotropic, so the rot 90/270 pitch swap is live
- `oracle_bbox(back) != oracle_bbox(front)` — the `phys_offset_x` sign-flip term actually moves
  the bbox (with a smaller offset it does not, and that term dies silently)
- parametrized over rot 0/back, 90/front, 180/front, 270/back

### Removed-symbol grep

`git grep` over `server/` + `client2/src/` + `docs/architecture/` + `docs/spec/` for
`normalize_align`, `make_align_transform`, `align_overrides`, `probeAlignDeclaration`,
`align_override_declared`, `align_unconfirmed`, `_frame_grid_of`, `ALIGN_ORIGIN_DECLARED`,
`ALIGN_ORIGIN_DEFAULT`, `_canonical_origin_grid`: **zero live references**. Remaining hits are
(a) tests that assert the symbols are gone (`test_deleted_transform_copy_is_gone`,
`test_declared_align_origins_are_gone_from_the_module`), (b) a test that feeds a stale
`align_overrides` block and asserts it is ignored, and (c) comments explaining the removal.

### The surviving transform is exercised by `bonding_plan`'s own tests

`server/tests/test_bonding_plan.py` drives it through `/api/bonding-plan/core-summary` — not via
`map_overlay`'s tests. Confirmed by injection: `bbox_less` and `canonical_lost` both fail tests
*in that file*.

### Suite

`457 passed / 0 failed` on the final run. The stated baseline was 414; I added 13 tests, and the
rest of the growth came from the concurrent agents working in this tree. The three modules I own
total 127 tests, all passing.

---

## Behaviour changes (beyond the one numeric change above)

**1. New refusal: asymmetric metadata.** If a source map has registered metadata but the
canonical (core) frame does not, availability now returns `connected(align_unavailable)` instead
of assuming identity. Rationale: knowing a map is rot 180 *absolutely* tells you nothing about
its rotation *relative* to an unknown reference. Assuming identity there silently undercounts
fails and overstates remaining. When **neither** side is registered, identity still applies —
that is the documented registration-gap fallback, unchanged.

**2. Canonical-frame selection no longer falls through.** The canonical frame is defined by the
first coordinate-binding role (`total_chips → defect → eds_fail`; for transfer_plan, declaration
order among `frame: "origin"` fail sources). If *that* role has no metadata, canonical is `None`
— we do not search later roles. Falling through would let a rotated measurement map crown itself
as the reference, making the transform identity while the status still read `connected`.

**3. One existing test's expectation changed: `test_degraded_fail_source_broken_is_surfaced`,
`remaining_upper_bound` 3 → 5.** That test breaks the `defect` role, which is the role that
defines the canonical frame. Previously the config's `align: 180` carried the relative rotation
independently, so the EDS projection kept working. Now there is no independent carrier, so EDS
also degrades to `align_unavailable`. 5 is still a true upper bound (the real answer is 2), the
bound is merely looser — and **one more degraded role is now surfaced** where EDS previously
looked healthy. Less precision, more honesty; I kept the "is a true upper bound" invariant as an
explicit assertion so the intent survives.

---

## What the user must change in their live config

Nothing is required — the server ignores the stale keys, and `test_stale_align_overrides_in_config_are_ignored`
pins that. But three files carry dead keys that will mislead the next reader:

| file | key to delete |
|---|---|
| `server/config/bonding_plan_config.json` | `sources.eds_fail.align` |
| `server/config/transfer_plan_config.json` | `stages.bonding.source.fail_sources.eds_fail.align` |
| `server/config/map_overlay_config.json` | `align_overrides` (whole block — only `__example_*` inside) |

Deleting them changes no behaviour: `eds_fail_map`'s metadata already declares `rotation: 180`,
which is what the removed declarations said. **I did not touch these files** (gitignored user
assets); sha256 unchanged, verified.

---

## Files changed

| path | what |
|---|---|
| `C:\Users\kk980\Developments\assyManager\server\map_overlay.py` | override layer removed; `resolve_map_transform` single entry point; `align_status_label` moved in |
| `C:\Users\kk980\Developments\assyManager\server\bonding_plan.py` | transform copy deleted; metadata-derived alignment; `load_map_meta` + request-scoped cache |
| `C:\Users\kk980\Developments\assyManager\server\transfer_plan.py` | canonical meta instead of canonical grid; routed through `resolve_map_transform` |
| `C:\Users\kk980\Developments\assyManager\server\main.py` | overlay endpoint no longer threads `eqp`; docstring |
| `C:\Users\kk980\Developments\assyManager\client2\src\map_editor.js` | probe + gate removed (61 added / 90 removed, confined to those two blocks) |
| `C:\Users\kk980\Developments\assyManager\server\config\map_overlay_config.json.sample` | `align_overrides` removed + `__comment` |
| `C:\Users\kk980\Developments\assyManager\server\config\bonding_plan_config.json.sample` | `sources[].align` removed + `__doc__` |
| `C:\Users\kk980\Developments\assyManager\server\config\transfer_plan_config.json.sample` | `fail_sources[].align` removed + `__comment` |
| `C:\Users\kk980\Developments\assyManager\server\tests\test_bonding_plan.py` | crop/anisotropic/back/rot fixtures via independent oracle; deleted-symbol guard |
| `C:\Users\kk980\Developments\assyManager\server\tests\test_map_overlay.py` | override tests → "stale keys are ignored"; `oracle_stored_cells` / `oracle_bbox` exported |
| `C:\Users\kk980\Developments\assyManager\server\tests\test_transfer_plan.py` | align declarations removed; negative controls now flip metadata |
| `C:\Users\kk980\Developments\assyManager\docs\spec\MAP_EDITOR_SPEC.md` | §5.0 / §5.1 / §5.2 / §5.3 — A2 closed, status list 6 → 4 |
| `C:\Users\kk980\Developments\assyManager\docs\architecture\CODE_MAP.md` | bonding_plan / map_overlay / transfer_plan / client sections |
| `C:\Users\kk980\Developments\assyManager\docs\architecture\backend.md` | overlay endpoint align rule |
| `C:\Users\kk980\Developments\assyManager\docs\history\20260727_004500_align_consolidation_meta_single_source.md` | new; index regenerated |

`docs/process/PROJECT_STATUS.md` deliberately untouched (lead-owned). Proposed board edit:
**#20 → resolved**, with the correction that the copy was live rather than dormant, and the note
that server-side implementations are now 1 (2 counting the client renderer).

---

## Open items / needs a decision

1. **`GET /api/maps/overlay?eqp=` is now a no-op.** It existed solely for `by_eqp`. I left the
   parameter on the endpoint because removing it is a REST-signature change (boundary contract,
   lead approval). No caller passes it, and FastAPI ignores unknown query params, so removal
   would be wire-compatible whenever you want it gone.
2. **Python/JS transform drift** is the remaining duplication. Guarded by the oracle today; a
   stronger guard would be a shared golden-vector fixture consumed by both suites.
3. **Registration gap** (spec §5.0): `bonding_map` has ~390k distinct map keys and 9 metadata
   rows. Under the new rule, unregistered maps fall back to identity in the overlay and — where
   the counterpart *is* registered — to `align_unavailable` in availability. Tracked as M3.

---

## Proposed lessons (for `agent_workspace/memory/server-pm.md` — lead to approve)

- **Trap:** building a fixture with the function under test. Seeding coordinates with
  `make_frame_transform` and then recovering them with `make_frame_transform` cancels any
  bijective defect — a bbox-less injection left all 20 tests green. Same family as the
  "single-implementation round trip" lesson, but it bites through the *fixture* rather than the
  assertion, so it survives even when the assertion looks independent.
  **Right way:** build fixtures from an independent oracle (or hand-written golden vectors), and
  prove it by injecting the defect. If injection does not turn the test red, the test is not a test.
- **Trap:** "dormant, so it is safe." The dormancy claim came from reading one config
  (`map_overlay_config.json`, where the key was `__example_`-prefixed) and generalising. Two other
  gitignored configs declared it live, on the exact path that produces user-facing numbers.
  **Right way:** dormancy is a property of *all* config files plus every caller; enumerate the
  gitignored user assets (`server/config/*.json`) explicitly before asserting a path is unused.
- **Trap:** verifying a coordinate change with counts. A uniform offset relocates every die onto a
  different die, and totals over a full region are preserved exactly — the CROP availability count
  read 7 before and after while all 7 dies were wrong.
  **Right way:** assert **identity** (per-die 1×1 probes, or a boundary-crossing half-plane), never
  just cardinality, when validating a transform.
- **Trap:** a fixture with `minC == minR` cannot catch an x/y axis confusion, exactly as
  `chip_x == chip_y` cannot catch a pitch swap. My first crop spec had `bbox = (1,8,1,7)`.
  **Right way:** when choosing a geometry fixture, make every pair of analogous parameters differ,
  and have the test assert that (`assert minC != minR`) so a later "simplification" fails loudly.
