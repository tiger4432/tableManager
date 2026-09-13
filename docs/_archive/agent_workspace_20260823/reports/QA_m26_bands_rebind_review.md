# QA — M2.6 bands rebind (`0f8d35f`), two parallel adversarial reviews

**Date:** 2026-07-27 · **Recorded by:** lead-pm · **Reviews:** qa-reviewer ×2, dispatched concurrently with different lenses

The reviewers' operating policy forbids them writing report files, so their findings existed
only in the dispatching session. The confirmed defects are already captured in tests and in
`0f8d35f`'s commit message. **This file exists for the part that is nowhere else: what was
attacked and held.** A future reviewer of this module should start after this list, not before it.

---

## 1. Method — and why the split mattered

| | Lens | Verdict |
|---|---|---|
| **A** | Derivation fidelity vs the client; boundary contract | GO-WITH-FIXES |
| **B** | Silent-pass hazards; data integrity; caps | **NO-GO** |

Each found a HIGH the other missed. A single reviewer would very likely have shipped one of them.

**Both blocking findings were found by executing the code against constructed inputs, not by
reading it.** `float(raw)` beside `Number(b.to)` looks equivalent on the page. Review A built a
shared case file and ran both implementations against it; that is what surfaced the divergence.

---

## 2. Confirmed defects → disposition

All fixed in `0f8d35f`. Kept here in one line each so the negative results below have context.

| ID | Defect | Fix |
|---|---|---|
| B-H1 | Duplicate band `seq` disabled the F4 over-allocation guard — `label` gated the aggregate check while `required` had already summed both demands. 100 needed vs 60 available returned `ok`, zero warnings | Gate counts **demands**, not labels; `seq` made unique on parse |
| B-H2 | Incomplete `painted` read zeroed every quantity. Deriving made a previously inert read load-bearing without a gate | `painted_reliable` gates the derivation; the two painting-assertive warnings are suppressed when counts are unknown |
| A-H1 | `_band_to` diverged from client `bandTo` on 5 input classes; `prevTo` propagated it to a **neighbouring** band | `to` narrowed to `blank \| valid \| invalid` on both sides; blank and invalid skipped identically |
| A-H2 | One non-object array element voided the whole value server-side; unreadable values also emitted a false "no DOE definition" | Element dropped; unreadable subtracted from the difference |
| A-M1 | Material split disagreed on every malformed ID; a shipped test asserted the divergence under a comment claiming equivalence | Both sides refuse and trim; decision registered in `PRIMITIVES.md` |
| B-M1 | `OverflowError` uncaught → one poisoned band 500'd the entire plan | Integer-magnitude check before `float()` |
| B-M2 | `MAX_PLAN_VALUES` was the one cap still truncating silently — and it now drives quantities | Surfaces `result_truncated`, forces `unverified` |
| B-M3/M4 | Fan-out ceiling grew 4× (128,000 source summaries measured from one 1.53 MB row); blob fully parsed before any cap | Global demand/source caps; pre-parse byte bound; failing summaries cached |
| A-M2 | `MAX_SOURCES_PER_DOE` truncation reported the wrong role and cap | Per-role truncation list |

**Two tests were cited as evidence while being unable to fail.** `test_band_arithmetic_mirrors_the_client`
hardcoded seven inputs on which the two sides happened to agree; `test_layer_coverage_gap_warning_is_gone`
asserted a Python attribute name. Both replaced with behavioural versions. The implementer
independently reported writing `assert ... or True` into a first draft and removing it — the
pattern is evidently easy to produce under time pressure.

---

## 3. Attacked and held — **do not re-derive these**

Each was driven through the real `validate_plan` body, not reasoned about.

**`availability_checked` cannot report a clean pass on an unchecked plan.** Every enumerated
path yields `unverified`: empty registry · `bands` NULL · `"[]"` · unknown stage · unresolvable
materials · missing `material_identity` · all-blank `to` · all-degraded sources · summary raising
for every source · row truncation · band truncation. Only the healthy baseline reached `ok`.

**JSON parsing of `bands` degrades, never crashes or passes.** Malformed JSON, a JSON object
instead of an array, double-encoded strings, `"null"`, arrays of non-objects, 300-deep nesting,
bytes — all reach `unreadable` + `unverified`. `RecursionError` is caught. `materials` as a string,
or containing objects/nulls/numbers, reaches `source_unresolved`; nothing is silently skipped.

**`bands IS NULL` reads as "no DOE yet", not as a defect and not as a pass.** All 102 live rows
across 25 plans were in this state at review time.

**Ordering is safe.** Nothing sorts; `_prev_to` and the demand loop walk `enumerate(bands)`.
Descending `seq` (legal, and the canonical example) derives identically on both sides.

**Response contract is intact.** Measured key set exactly `ref_table, map_key, stage, map_status,
doe_count, painted_values, status, availability_checked, warnings`, types unchanged. New `reason` /
`band` / `to` / `prev_to` keys live inside warning objects, which were already free-form.

**Retired tables are genuinely unreachable.** Code-only grep across `server/`, `client2/src/`,
`dev_env/` for `map_doe`, `band_seq`, `stack_band`, `qty_total` found no reads. Remaining hits are
the deliberate deprecated declarations, retained index entries, tests, and prose.

**The new index matches the predicate** — `idx_map_split_registry_ref_map` on plain columns, no
cast, against bare column equality. (This was checked because a prior cycle shipped an
expression-cast mismatch.)

**No test writes into the live tree.** `git status` unchanged after a full run; the only live-tree
mtime change was `scheduler_status.json`, written by the running auto-update process.

**`replace_map` does not expose a torn state to a concurrent `validate`** — delete and rewrite
share one transaction, so READ COMMITTED never sees the gap. What *is* new: bands and colours now
share a row, so a legend-only save and a DOE save collide on the same scope where they previously
hit different tables.

**`layer_coverage_gap` had no live consumer.** Verified independently by both reviewers: absent
from every built bundle; the sole source reference is a held constant behind `eslint-disable`.

**Math idioms agree.** `Math.trunc` vs `int()` on negatives, `Math.ceil` vs `-(-a//b)` — checked
across a range of pairs, identical. Duplicate/blank materials do not change `share`, because
`normalizeBands` dedups on read before `bandShare` ever sees the array.

---

## 4. Still open

1. **`seq` type axis is unpinned and already diverging** — `{"seq": 2.0}` yields 2 on the client
   (JSON.parse collapses it) and positional fallback on the server (`isinstance(raw, int)` is False).
   Found by doc-historian after the merge, not by either review. Follow-up dispatched.
   **The general lesson: the contract file protects exactly the axes it enumerates.**
2. **The client hard-codes the two-field material split** that the server derives from
   `plan_store.material_identity`. Same family as the divergence just fixed; next one to surface.
3. **`_prev_to` walks back to a band's `to` without checking that band was valid**, so
   `[10, 5, 20]` derives 25 layers of demand for a 20-layer stack. **Both sides agree**, so it is
   not a mirror defect — but `not_increasing`'s wording describes the wrong victim.
4. **Runtime, post-restart**: no production row has yet exercised the parse path; no live client
   consumes `validate`; the config-before-code ordering is a rollback hazard (see
   `PROJECT_STATUS.md` queue item 3).

---

## 5. Lessons offered for `agent_workspace/memory/qa-reviewer.md`

Recorded here rather than folded in silently; the lead PM folds memory.

- When a report claims one implementation "mirrors" another, **execute both against a shared
  input vector**. Reading them side by side is what let this divergence ship in the first place.
- In a **"stored → derived"** refactor, treat *the derivation's input read failing or truncating*
  as a first-class hypothesis. A read that was inert when the value came from storage becomes
  load-bearing the moment it becomes a multiplier.
- When a human-readable label list doubles as the **counter gating a check**, a label collision
  silently disables the safety net. Always ask what `len(...)` is actually counting.
- Enumerate `MAX_*` constants exhaustively and tabulate surfacing per cap. Counting only the caps
  that *do* surface hides the one that does not.
- Before ranking a malformed-input divergence unreachable, check whether the column is in
  `display_columns` — a declared dynamic table means the generic grid can paste arbitrary strings
  into it, so "only the editor writes this" is usually false.
