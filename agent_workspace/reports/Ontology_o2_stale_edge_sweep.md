# O2 - Stale edge sweep: making re-derivation a correction instead of an accumulation

**Agent:** ontology-pm | **Date:** 2026-08-04 | **Status:** implemented, tested, NOT committed, NOT scheduled

## What shipped

| File | What |
|---|---|
| `C:\Users\kk980\Developments\assyManager\server\graph_stale_edges.py` | new - ownership model, dry-run planner, guarded apply |
| `C:\Users\kk980\Developments\assyManager\server\scripts\graph_stale_edge_sweep.py` | new - operator CLI, dry run by default |
| `C:\Users\kk980\Developments\assyManager\server\tests\test_ontology_stale_edge_sweep.py` | new - 28 tests, red-first + survival + mutation-checked |

Nothing else in the tree was touched. `main.py`, `crud.py`, `transfer_plan.py`, `bonding_plan.py`,
`virtual_join_executor.py`, `server/config/*.json`, `client2/`, `docs/` untouched. No route added.
No commit, no push. No write of any kind reached the live PostgreSQL - every measurement below is
sqlite in an isolated `ASSY_DATA_ROOT`.

---

## 1. RED first - measured, not assumed

Script: `.../scratchpad/red_o2.py`, isolated sqlite, using ONLY code that exists at HEAD.

```
=== derive ===                      {'rows': 2, 'nodes': 4, 'edges': 2, 'chunks': 1}
=== (A) delete row_LOG1, then RE-DERIVE ===
resync -> {'rows': 1, 'nodes': 2, 'edges': 1, 'chunks': 1}
RED (A): 1 edge(s) of the DELETED row survived re-derivation
=== (B) retire the whole table mapping, then RE-DERIVE ===
mapped tables now: []
resync -> {'rows': 0, 'nodes': 0, 'edges': 0, 'chunks': 0}
RED (B): 2 edge(s) of a RETIRED purpose survived
=== what the orphan sweep can do about it ===
orphan nodes found: []
node population   : {'O2Cell': 2, 'O2Core': 2}
```

Three findings in that block:

- **(A)** `materialize_events` counts DELETE into `skipped_deletes` and returns; `resync_table`
  iterates rows that EXIST, so a deleted row's ref is never in a `processed_refs` scope again and
  `_retarget_stale_edges` structurally cannot see it.
- **(B)** `resync_table` returns `{'rows': 0, ...}` for a table the declaration no longer maps.
  Deleting an `exp:` purpose's declaration removes the producer and keeps every edge - **this is why
  `exp:` retirement has no mechanism**, and it is a one-line consequence of an early return.
- **(C, new)** the existing node sweep cannot compensate. It found **0 orphans** while 4 dead nodes
  sat there: the corpse edges hold both endpoints above degree zero. **Edge cleanup is a
  precondition for node cleanup**, not an alternative to it. The CLI says so on exit.

---

## 2. The ownership model

**`graph_edges.source_row_ref` is the graph-side `cell_sources`.** Verified by grep, not assumed:
`graph_materializer.bulk_upsert_edges` is the **only** writer of `graph_edges` in the whole server
(`main.py` reads; nothing else constructs a `GraphEdge`). So that one string - `f"{table}:{row_id}"`
- is the complete record of which derivation minted an edge.

An edge is **derivation-owned** iff that string parses into `(table, row_id)`. Ownership is never
inferred from `type`, from a label, or from an endpoint; a sweep scoped by "everything of type X"
would take another purpose's edges with it.

Four verdicts, one per distinct ref:

| verdict | meaning | swept? |
|---|---|---|
| `live` | a mapped table still holds that row | **no** - `resync_table` is the authority there |
| `row_gone` | mapped table, row absent (population A) | yes, subject to the guards |
| `not_declared` | table registered, declaration no longer maps it (population B) | yes, subject to the guards |
| `not_reached` | ownership could **not** be established | **never** |

`row_gone` is a positive determination (the RDB was asked), not a synonym for an inability word.
The inability words are imported verbatim from `config_resolve_report` - `not_declared`,
`mapping_unavailable`, `not_reached` - and `count_kind` (`exact`/`sample`) from `retroactive`. No
new dialect: a test asserts the constants ARE the canonical ones, so a future respelling breaks.

**Deliberate non-goal.** The sweep does not recompute what a mapping produces. Retire an edge type,
rename a label, correct an identity - `_retarget_stale_edges` already deletes those, because the row
is visited again. Recomputing the produced set here would make this module a second materializer,
which is the failure this repo has paid for twice in coordinate transforms.

---

## 3. What CANNOT be safely swept (the finding you asked for)

Three populations. All reported by name with counts, none deleted:

1. **`source_row_ref` NULL / empty / no `:`** - nothing records who minted it. Could be a
   hand-authored edge, could be a pre-provenance write. *"I do not know who owns this" is not
   "nobody owns it."*
2. **the literal `"<table>:None"`** - `bulk_upsert_edges` formats the ref with an f-string, and
   `materialize_events` sets `"row_id": payload.get("row_id")` with no guard, so a payload without a
   `row_id` produced that exact string. Asking the RDB for a row called `None` returns "absent" and
   the edge would be swept on the strength of a question that was never about it. **`parse_row_ref`
   refuses it explicitly.** (Second-order finding: such an edge is *also* permanently outside
   `_retarget_stale_edges`' scope, since `processed_refs` skips `row_id is None`. It is a corpse
   that nothing can ever clean. Naming it is the honest outcome; guessing is not.)
3. **a table not in `DYNAMIC_TABLES`** - this process cannot query it, and "not registered here" is
   indistinguishable from "retired". Reading the first as the second **is** the
   `mapping_unavailable` -> `not_declared` confusion. Two separate mutations (M2b, M2c) prove the
   tests catch exactly this.

Plus the whole-run refusal: if the declaration did not load cleanly, the sweep **refuses entirely**
(`graph_orphans.declaration_blockers`, reused not reimplemented). A renamed column silently drops a
table's mapping - that is the loader's documented contract - and that table then looks *unmapped*,
which this sweep reads as "delete every edge it produced". The budget guard does not save you: a
type under `min_population` is exempt from it. So the declaration has to be the gate.

And one population deliberately left alone with a note, not silence: **superseded `source_name`
duplicates**. `_retarget_stale_edges` matches on `(from, type, to)` only, so re-ingesting the same
rows from a differently named file mints a second edge and the old one survives with its stale
`event_time` (live: 830 surplus of 15,970 per `graph_orphans.report_duplicate_source_edges`). Their
owning rows are **live**, so this sweep correctly declines - the fix belongs in the materializer's
UPSERT matching key, which is a hot-path change and its own round. See section 7.

---

## 4. How human-confirmed content is protected

**Rule: an edge whose `source_name` is `crud.USER_SOURCE` is removed from the delete set and
reported as protected - even when its owning row is gone, even when its purpose was retired.**

This is not hypothetical content. `ontology_config.synthesize_enrichment_mappings` mints every
`RESOLVED_AS` edge with `source_override: "user"` precisely because it is a person's correction.
Those edges *are* the "one human judgement propagates" value proposition, in the graph.

The asymmetry is deliberate and stated in the module: for a machine-derived edge, "no row produces
this any more" is a complete argument; for a human-confirmed one it is not, because what would be
destroyed is not re-derivable. A stale user edge costs a wrong neighbour in a trace; a swept one
costs a person's time. Same shape as `chain_replay`'s `user_protected_cells` and `retroactive`'s
`pinned`.

Selected **positively** by the constant, never by blacklisting automatic sources - crud's own
documented rule, and there are 10,750 distinct automatic source values on live, so a blacklist can
only ever be incomplete. A test asserts six non-user spellings all return False.

---

## 5. The dry-run shape

Follows `GET /admin/enrichment/auto-confirm/dry-run`: measure, then act.

- `plan_sweep(db, mappings, ...)` **writes nothing**. Returns `population` / `per_type` /
  `sweepable` / `declined` / `protected` / `not_reached` / `delete_ids` / `count_kind` / `scanned` /
  `truncated` / `elapsed_ms`.
- `apply_sweep(db, plan)` deletes **exactly `plan["delete_ids"]`** and re-derives nothing of its
  own. If it recomputed its own scope, the dry run would be a decoration - mutation M5 proves the
  test catches that.
- `run_sweep(...)` defaults to `apply_deletions=False`. This is the **one place this module
  deliberately diverges from `graph_orphans.run_scheduled(apply_deletions=True)`**: deleting a
  degree-zero node changes no answer anyone can traverse; deleting an edge changes what a trace says.
- CLI defaults to dry run; `--apply` against a non-isolated data root refuses without
  `--allow-production` (same gate as the sibling).

**Honest counts.** `count_kind` is `exact` by default. With `--scan-limit` it becomes `sample`, and
a **truncated scan deletes nothing**: each stale edge in a sample is individually certain, but the
budget guard's numerator would come from the sample while its denominator is the whole population,
so the fraction is a *lower bound* and the guard could only ever fail to decline. A guard that
cannot answer must not wave things through. `scan_limit` is a measurement knob, not a batch size,
and every type lands in `declined` with the truncation named.

Real CLI output, isolated fixture (`.../scratchpad/cli_drill.py`), fixture seeded with one edge of
every class:

```
scanned 15 edge(s), count_kind=exact

-- not_reached: 1 edge(s) across 1 ref(s) whose owner could not be established --
     These are NEVER swept. 'I do not know who minted this' is not 'nobody minted this'.
     [     15] CLI_HAND           ref=None

-- PROTECTED: 1 human-confirmed edge(s) (source_name='user') --
     CLI_RESOLVED_AS    1
     A person's judgement is not re-derivable. These stay even though nothing produces them any more.

-- 3 stale edge(s): the owning row is gone, or its table is no longer declared (detection 219 ms) --
   CLI_EXP_LINK (1)
     [     14] not_declared   cli_retired:row_X1
   CLI_FROM_CORE (2)
     [      1] row_gone       cli_bonding:row_B0
     [      2] row_gone       cli_bonding:row_B1

-- budget guard --
     CLI_EXP_LINK       1/1 = 100%  ok (small type, exempt)
     CLI_FROM_CORE      2/12 = 17%  ok

DRY RUN - nothing written. 3 edge(s) would be deleted. Re-run with --apply.
```

After `--apply`: 12 edges left, verified **by identity, not by count** - the 10 live bonding edges,
the human-confirmed one whose row is gone, and the unattributable one.

---

## 6. Mutation evidence

Harness: `.../scratchpad/mutate.py` - injects a defect into `graph_stale_edges.py`, runs the named
tests, always restores the file. Every one must go RED.

| # | Injected defect | Tests | Result |
|---|---|---|---|
| M1 | `is_human_confirmed` -> `False` (no protection) | 2 human-confirmed survival tests | **RED** |
| M2 | `not_reached` added to `SWEEPABLE_VERDICTS` | 2 unattributable survival tests | **RED** |
| M2b | unparseable ref classified `not_declared` | no-owner survival | **RED** |
| M2c | unknown table classified `not_declared` | unknown-table survival | **RED** |
| M3 | `declaration_blockers` gate removed | rejected-mapping refusal | **RED** |
| M4 | row-existence check skipped (table-scoped delete) | live-row + collateral tests | **RED** |
| M5 | `apply_sweep` deletes by `type` instead of by planned ids | apply-exactly + collateral | **RED** |
| M6 | truncated scan allowed to delete | count_kind test | **RED** |

**M2 initially came back GREEN, and that was a real defect in my own design, not a bad mutation.**
`plan_sweep` had an early `continue` in the `not_reached` branch, so `SWEEPABLE_VERDICTS` was
decoration sitting next to a branch that had already returned - the constant advertised itself as
the gate while a different line actually was. Restructured so the membership test is the single
gate and the `not_reached` branch only counts. M2 then went red. This is the exact reason the brief
demands mutation-checking: the test was fine, the *structure* was lying.

---

## 7. Live measurement I did NOT run - handed over as requested

Read-only, but per the brief I am handing the queries over rather than running them. Both are pure
`SELECT` against PostgreSQL.

**(a) How much of `graph_edges` falls into each ownership class:**

```sql
SELECT
  CASE
    WHEN source_row_ref IS NULL OR source_row_ref = ''      THEN 'not_reached:no_ref'
    WHEN position(':' in source_row_ref) = 0                THEN 'not_reached:unparseable'
    WHEN split_part(source_row_ref, ':', 2) IN ('', 'None') THEN 'not_reached:no_row_id'
    ELSE split_part(source_row_ref, ':', 1)
  END AS owner,
  count(*)                                        AS edges,
  count(DISTINCT source_row_ref)                  AS refs,
  count(*) FILTER (WHERE source_name = 'user')    AS human_confirmed
FROM graph_edges
GROUP BY 1 ORDER BY 2 DESC;
```

This answers, in one row each: how big population (B) would be if a table were retired, how many
edges are permanently unattributable, and how much human-confirmed content the protection is
actually holding.

**(b) Population (A) per mapped table** - substitute the table name in both places:

```sql
SELECT count(*) AS row_gone_edges
FROM graph_edges e
WHERE split_part(e.source_row_ref, ':', 1) = '<table>'
  AND split_part(e.source_row_ref, ':', 2) NOT IN ('', 'None')
  AND NOT EXISTS (SELECT 1 FROM <table> t
                  WHERE t.row_id = split_part(e.source_row_ref, ':', 2));
```

The `--scan-limit` path exists so a first live look can be bounded, and it deletes nothing by
construction.

---

## 8. Decisions taken, and what is deliberately NOT done

1. **Existence check, not DELETE-event handling.** The board names "the materializer skips DELETE",
   and the obvious fix is a DELETE branch in `materialize_events`. I did not take it, for three
   reasons: an event branch trusts a payload where the RDB is ground truth; it cannot help the rows
   already deleted (which is the entire accumulated backlog); and it does nothing at all for
   population (B), which produces no event. The sweep subsumes both and is idempotent. **A DELETE
   branch remains worth adding for latency** (the sweep is a run, not a millisecond) - it would be
   strictly additive on top of this. Flagging, not doing: it is a hot-path change.
2. **Not wired to the auto-update scheduler.** `graph_orphans` runs on the tick with
   `apply_deletions=True`. This one does not run unattended at all yet. A destructive graph job
   should be read once by a person in its dry-run form before it deletes on a timer. Recommend
   wiring it after one live dry run, and **before** the orphan sweep in the same tick (edges first -
   see finding (C)).
3. **No route.** A `/graph/stale-edges/dry-run` endpoint is the natural surface and would mirror
   `/admin/enrichment/auto-confirm/dry-run`, but that requires `main.py`, which is another lane's.
   Stopping and reporting per the brief. The planner is already shaped for it (`plan_sweep` returns
   a JSON-serialisable dict except for the tuple entries in `sweepable`).
4. **`server/config/ontology_mapping.json` untouched.** Never read for anything but tests, never
   written.

---

## 9. Test results

- New file: **28 passed** (`server/tests/test_ontology_stale_edge_sweep.py`).
- Ontology neighbours: **84 passed** (`..._stale_edge_sweep` + `..._reload_and_sweep` + `..._g1`).
- Full suite: **1939 passed, 2 skipped** in 383 s. Baseline given was 1879 + 2; the extra 60 are my
  28 plus another lane's `test_virtual_join_types.py` and `contracts/blank_predicate` additions,
  which are in the tree concurrently. **No failures.**
- One pytest at a time was respected: a live suite run was in progress at start and I waited it out
  (~15 min) before running anything.
- All three new files are **cp949-encodable**. U+2014 turned out NOT to be cp949-encodable, and
  `argparse` prints the CLI module docstring as its `description`, so an em dash there would have
  crashed `--help` on a Korean Windows console. Verified `--help` renders.

---

## 10. Proposed lessons (suggestions only - not written to the memory file)

For `agent_workspace/memory/ontology-pm.md`, ontology-pm section:

- **함정**: 상수가 게이트인 척하지만 실제 게이트는 그 위의 `continue`인 경우가 있다.
  `SWEEPABLE_VERDICTS`가 정확히 그 상태였고, **결함 주입이 초록으로 통과해서** 드러났다.
  **올바른 방법**: 판정 상수를 만들었으면 **그 상수의 멤버십 검사 한 줄이 유일한 관문**이 되게
  구조를 잡아라. 조기 `continue`가 앞에 있으면 상수는 장식이고, 그 사실은 결함 주입으로만 보인다.
- **함정**: 그래프에서 엣지를 지우지 않으면 **노드 스윕도 끝나지 않는다** - 시체 엣지가 양 끝
  노드를 degree-zero 밖에 붙들고 있어 `graph_orphans`가 0건을 보고한다(실측: 죽은 노드 4개 앞에서
  orphan 0). **올바른 방법**: 정리는 **엣지 먼저, 노드 나중**. 순서가 계약이다.
- **함정**: `f"{table}:{row_id}"`로 만든 provenance는 `row_id`가 `None`일 때 **문자열 `"None"`**을
  낳는다. 그 ref는 `processed_refs` 스코프에도 영원히 안 들어와 재교정이 닿지 못한다.
  **올바른 방법**: 파싱 실패는 「없다」가 아니라 **`not_reached`(못 물어봤다)**로 이름 붙여 보고하고
  절대 지우지 마라.

For the common section:

- **함정**: `U+2014`(em dash)는 **cp949로 인코딩되지 않는다.** argparse는 모듈 docstring을
  `description`으로 출력하므로, CLI docstring에 em dash가 있으면 한글 콘솔에서 `--help`가 죽는다.
  **올바른 방법**: 콘솔로 나가는 문자열이 든 파일은 `text.encode('cp949')`로 한 번 검증한다.
