# Server_m4p1_valid_die_ref — report

**Baseline:** `2a9f6c4` (suite measured green at 1005 before any edit)
**Scope:** server half of M4 phase 1 (`valid_die_ref`) + the `_get_recorrection_stat` twin fix.

---

## What changed (3 lines)

1. `map_overlay` gained the M4 phase-1 decision point — `parse_valid_die_ref` / `circle_die_mask` /
   **`resolve_valid_die_basis(meta, resolver) -> {basis, source, reason}`** (the contract symbol) —
   plus the DB-backed `resolve_valid_die_set` that turns a declared ref into a cell set with a
   per-work-unit cache and honest refusals.
2. `canonical_map_key` closes the last 7b hole: an *already assembled* map-key string (which is what
   a declaration is) is now canonicalised for the **meta** lookup too, sharing one decomposition rule
   (`map_key_parts`, extracted from `build_key_filters`) instead of a second normalisation.
3. `main._get_recorrection_stat` now names the actual failure cause instead of one canned
   timeout/index string (the A-F6 twin left out of scope this morning).

**No new REST path.** See "Escalated" #1.

---

## StableDevelopmentProtocol §1 side-effect checklist

| Axis | Analysis | Handling |
|---|---|---|
| **Shared signature** | `build_key_filters` internals refactored (decomposition extracted to `map_key_parts`). Signature and behaviour unchanged. Exhaustive grep of callers: `map_overlay.get_overlay`, `transfer_plan.py:2756`, `contracts/map_seam`, 2 test modules, plus the client mirrors (`buildKeyFilters`, `decomposeMapKey`) which are unaffected because the wire behaviour is identical. | Proven by `test_map_overlay` + `test_key_canonicalization` + the seam `decompose_cases` all green. |
| **Boundary contract** | REST signatures, WS event names/payloads, cell shape `{value,is_overwrite,priority_source}`, `table_config.json`→`/schema`: **none touched.** The one boundary item I nearly added (a `/api/maps/valid-dies` endpoint) was built, then removed — see Escalated #1. | Zero boundary change in this diff. |
| **Metadata schema** | `valid_die_ref` is a key inside the `grid_metadata` JSON payload, not a column. No `ALTER TABLE`, no migration ordering dependency (server-pm memory #66: prefer new state that `create_all` handles or that needs no DDL at all). | Additive by construction. |
| **Readers of `grid_metadata`** | `_grid_of` / `_phys_signature` / `frame_axes` / `_rotation_of` / `_side_of` / `_y_invert_of` all read **known keys only**, so a new key cannot perturb alignment. `frame_axes` keys `_FRAME_TF_CACHE`, so a leak there would silently re-frame maps. | Pinned by `test_declaration_does_not_perturb_frame_axes` and `test_declaration_is_inert_on_the_overlay_path` (byte-identical `get_overlay` output with and without the field). |
| **Layering invariant** | Meta rows are written through the normal path; `auto_map_meta` resolves to the lowest priority, so a user edit always wins. `map_meta_registrar` is absent-only — an ingestion batch must never erase a hand-declared ref. | New regression `test_ingestion_auto_registration_never_clobbers_a_declared_ref` (plus the existing `test_existing_meta_is_never_overwritten`). |
| **Shared mutable state** | New module global `_CIRCLE_MASK_CACHE`, keyed by `frame_axes` (which fully determines the mask), bounded at 256 and cleared on overflow — same discipline as `_FRAME_TF_CACHE` / `map_meta_registrar._known_present`. Unlocked, like its precedents: worst case is a redundant recomputation, never a wrong answer. | Bounded + documented. |
| **Timing / re-entrancy** | `resolve_valid_die_set` takes a caller-owned cache dict (request = work unit). No global request state, no async, no background task. | n/a |
| **Write path** | A malformed declaration is reported at **read** time and never rejects the metadata row. This is deliberate: an hour earlier `_validate_effort` rejected a user's correction because the instrument was malformed. Validation must not destroy the user's work. | `test_a_malformed_declaration_never_blocks_the_write_path`. |
| **Scale (10M rows)** | Per declared ref: 1 target-meta read (cached), 1 ref-meta read, 1 cell query with `limit(cap+1)`. Cache key is `(ref_table, ref_map_id, frame_axes(target))`, so N maps sharing one template + frame resolve **once**. No per-cell and no per-request rescan. `circle_die_mask` is O(cols×rows) over a ≤100×100 grid and is cached per frame. | `test_repeated_resolution_within_a_work_unit_costs_one_query` and `test_two_maps_sharing_a_ref_and_frame_resolve_it_once` count real SELECTs via a SQLAlchemy `before_cursor_execute` listener. |
| **Truncation** | Over the cap the resolver **refuses** rather than truncating: a truncated valid-die set is a wrong set that looks right, and the difference never reaches the screen. | `test_reference_over_the_cell_cap_is_refused_not_truncated`. |

---

## Invariants — what was proved and how

Tests were written **before** the implementation: the new file failed 26 of 29 at that point. The 3
that passed were the INV-M4-1 tests, which must be green on both sides of the change — that is what
INV-M4-1 means.

### INV-M4-1 — no ref ⇒ identical to `2a9f6c4`
- `frame_axes` is provably unchanged by the field; `get_overlay` output is byte-identical
  (`json.dumps(..., sort_keys=True)` compare) with and without declarations on both maps.
- `resolve_valid_die_basis` with no declaration returns `source: "circle"` and a mask that matches
  the **measured** `2a9f6c4` baseline in `contracts/map_seam/mask_baseline_cases` — not a restatement
  of it. The seam's `test_circle_die_mask_agrees_with_the_engine_baseline` scores this.
- Full suite: 1005 → 1050, **zero pre-existing tests changed or removed.**

### INV-M4-2 — ref present ⇒ the referenced map is the sole basis
The fixture is built so a circle implementation **cannot** pass. 6×6 grid with 60 mm chips: the circle
admits 12 of 36 cells with `bbox minC/minR = 1` (a real crop — per SPEC §5.3, a 40×40 `minC=0` fixture
cannot express this defect at all). `test_fixture_circle_actually_crops` guards the guard.
- The template **adds** `(0,0)`/`(1,1)` which the circle rejects, and **omits** `(2,2)` which the
  circle accepts; both directions asserted.
- Every assertion on this axis also asserts `resolved != circle_mask` and
  `basis != circle & ref` — the intersection is the tempting bug (it looks conservative while
  silently dropping dies the template declares valid), and it fails here.
- A rectangular tape strip — geometry no circle can express — resolves exactly.
- The ref is read **in the referring map's frame**: a 180-rotated template lands on the transform
  from `map_overlay.make_frame_transform`, and the test asserts the result differs from the stored
  coordinates, so a verbatim copy fails.

### INV-M4-3 — unresolvable ⇒ refuse with a stated reason, never a silent circle
Nine refusal cases, each asserting `status != ok`, a non-empty `detail`, and **the absence of the
`cells` key** — the consumer structurally cannot read a fallback set. Vocabulary reuses the existing
degradation words: `source_missing` (table/binding/key/grammar), `align_unavailable` (ref meta
unregistered, incompatible grid dims), `ref_unavailable` (over the cap), `no_data` (zero rows).
- **Zero rows is a refusal, not "no die is valid."** It almost always means "not loaded yet", and
  answering zero would invalidate the user's whole map.
- **Asymmetric frames refuse.** The declaration lives inside the meta, so the referring frame is
  always known; assuming identity when only the *referenced* frame is unknown would silently accept
  a 180-rotated template. Same reasoning as `bonding_plan`'s canonical-frame rule.
- **Only `null`/absent is "not declared."** An unreadable declaration is a refusal, not a fold back
  to circle — otherwise one typo silently reverts to circle geometry, which is the exact
  indistinguishability this round removes.

### INV-M4-4 — resolution rides the 7b canonicalisation, no second normalisation
The happy path (`LOT_01` resolving against a stored number-declared `1`) is paired with a **mutation
twin** borrowed from `test_key_canonicalization.py`: degrade `map_overlay.canonical_key_value` to raw
`str()` and the same declaration must stop resolving. Without the twin, the happy path would also
pass on an implementation that added its own normalisation.

**This invariant found a real defect in my first implementation.** `build_key_filters` casts cell
filters by declared column type, so `LOT_01` found the *cells* — but `load_map_meta` matches `map_id`
as an exact string, so it missed the *meta* and refused with `align_unavailable`. The fix is
`canonical_map_key`, which is the composition of two existing functions over one shared decomposition
rule, not a third implementation.

---

## Test results (conda env `assy_manager`)

| Run | Result |
|---|---|
| `server/tests/` at `2a9f6c4`, before any edit | **1005 passed** |
| `server/tests/test_valid_die_ref.py` **before** implementation | 26 failed, 3 passed (the 3 are the INV-M4-1 tests) |
| `server/tests/test_valid_die_ref.py` after | **43 passed** |
| `server/tests/` final | **1050 passed** (1005 + 43 M4 + 2 recorrection), 131 s |
| `contracts/map_seam/` M4 subset | **8 passed** — incl. `test_valid_die_basis_matches_the_contract`, `test_valid_die_ref_parse_matches_the_contract`, `test_circle_die_mask_agrees_with_the_engine_baseline`, `test_m4_ref_key_reuses_the_7b_canonicalisation` |
| `contracts/map_seam/` whole file | 30 passed, 1 failed — the single failure is **7c** `transfer_log_is_declared_none`, pre-existing and outside this task |

> Run with `PYTHONIOENCODING=utf-8 PYTHONUTF8=1` — without it `conda run` dies on a cp949
> `UnicodeEncodeError` when any Korean assertion text reaches stdout (memory-file trap, hit again).

---

## Escalated / open

1. **No `/api/maps/valid-dies` endpoint — deliberate, reversible.** I built one, then removed it after
   reading the client half: `resolveValidDie` resolves refs through existing endpoints
   (`/tables/{t}/data` + paint-rules `binding` + `/schema`), so the new path had **zero consumers**,
   and a REST signature is a boundary contract requiring your approval. The server-side resolver
   remains as the module function `resolve_valid_die_set` for phases 2-3. A comment at the former
   site in `main.py` records the decision. **Say the word and it goes back in — it is ~40 lines.**

2. **Recorded seam divergence — `object_no_table_no_home` (Lead PM's call).** For an object-form
   declaration naming no table when the caller also supplied no home table, my server yields a ref
   (`table: None`, and the DB resolver then refuses with a stated cause) while the client errors at
   parse time. The seam agent recorded both answers rather than deciding. My reasoning: table absence
   is not a *grammar* violation, and on the real server path `default_table` is always the target
   table, so the case is **unreachable in production**. Matching the client is one line if you prefer
   strictness — but it would also require updating `valid_die_ref_home_divergence_cases`, which is
   the seam agent's file, so I did not touch either side.

3. **Cell cap is a constant, not config.** `MAX_VALID_DIE_CELLS = 20_000`, matching `MAX_OVERLAY_CELLS`
   (a 300 mm / 2.5 mm wafer is 14,400 cells). A tape map larger than that refuses loudly with the cap
   named. If operations hit it, raising the constant is a one-liner; I did not add a config key because
   the neighbouring payload caps are constants too and adding one would pull in CONFIG_GUIDE +
   `guide/config/` duty for a defensive limit rather than a policy knob.

4. **A coordinates-only template table cannot be referenced.** Resolution goes through
   `resolve_binding`, which requires a value column. That is deliberate (one binding rule, per
   §5.6-bis, which exists precisely because there used to be three derivations), and the documented
   escape hatch is a declared `map_overlay_config.table_bindings` entry. Worth knowing before
   phase 3 migrates the 188 existing metadata rows.

5. **Not in scope, noticed in passing:** `contracts/map_seam` is not part of
   `pytest server/tests/`, so a green default suite does **not** mean the seam contract passes. The
   harness header says wiring it in is your call (add `contracts/` to testpaths, or a 3-line shim).
   The 7c `transfer_log_is_declared_none` extraction is likewise still open and belongs to that track.

---

## Docs updated (per DOC_OWNERSHIP, by changed code path)

| Doc | Change |
|---|---|
| `docs/map_editor/architecture_and_management.md` §2.3 / new §2.3-bis | `valid_die_ref` + `auto_registered` added to the `grid_metadata` field spec; **§2.3-bis is the grammar/refusal SSOT** (grammar table, three `source` values, the five refusal rules, the "bbox is untouched" rule). |
| `docs/spec/MAP_EDITOR_SPEC.md` new §5.7 + badge | The overlay-infrastructure relationship only (no duplication): resolution is structurally the same operation as an overlay, refusal reuses the §5.1/§5.2 vocabulary, bbox is out of scope until phase 3, plus the both-sides implementation table. |
| `docs/architecture/backend.md` | Recorrection `unavailable_reason` contract; the stale note claiming the twin was "still a canned string, out of scope this round" is now marked resolved. |
| `docs/history/20260729_101500_valid_die_ref_server_half.md` + `gen_index.py` | New entry (253 entries indexed). |

**Proposed memory-file additions (for your review — not added directly):**

- *Trap:* canonicalising a map key at **composition** time is not enough. A key that arrives
  already assembled (a declaration, a parsed token, a client string) still misses `load_map_meta`,
  which matches `map_id` as an exact string — cell filters survive because crud casts by declared
  type, so the symptom looks like an *alignment* failure, not a key failure.
  *Right way:* route assembled keys through `map_overlay.canonical_map_key`, and when a decomposition
  rule is needed twice, extract it (`map_key_parts`) instead of writing it twice.
- *Trap:* when another agent owns the seam, the contract vectors can land **after** you start.
  Grepping the repo for your own new symbol names surfaced both the published contract and the
  client's already-chosen grammar, which was different from the one I had designed.
  *Right way:* re-grep for the feature's vocabulary before finalising any cross-side shape, and read
  the other half's committed code rather than assuming the shape.
