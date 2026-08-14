# RETIRED — `source_config_ref` (the M1 source-role delegation path)

**Retired 2026-08-14 by the product owner's ruling** that `bonding_plan_config.json` be
taken out of the transfer-plan engine. What is retired here is the **bridge**: the way a
`transfer_plan_config.json` stage could hand its five source roles to
`bonding_plan_config.json`. **`bonding_plan_config.json` itself is NOT retired** — see
"What retiring this does NOT do" below, which names the one consumer that blocks it and
what the owner has to decide.

This marker follows the discipline the `map_doe` retirement set (`c0fb735`) and the
`migrate_map_meta_to_wafer_id.RETIRED.md` marker restated: a retirement leaves a durable,
named artifact next to what it retired, stating the approval, the **measured** reason,
what the retirement cannot undo, and the exact conditions under which the thing comes
back. The thing retired here is a code path plus a config key, so the artifact is prose
and the archive is git. It lives in `server/` rather than `server/config/` because
`server/config/*` is gitignored (`.gitignore:44`, `!*.sample`) and a marker nobody clones
is not durable.

## What it was

`transfer_plan_config.json` allowed a stage to write

```json
"dt": { "source_kind": "core", "source_config_ref": "bonding_plan", ... }
```

instead of an inline `"source": {...}` block. Five sites in `server/transfer_plan.py`
branched on it:

| site | what the branch did |
|---|---|
| `M1_SOURCE_REFS` | the allow-list, one entry: `("bonding_plan",)` |
| `_stage_role_statuses` | read `bonding_plan_config.sources` and renamed `used_chips` → `transfer_log` |
| `dry_run` | emitted `not_reached` for every `source.*` role, plus `source_config_ref` as a stage attribute |
| `get_stage_source_summary` | called `bonding_plan.get_core_summary` and reshaped it (`_reshape_m1_summary`); region scope went through `_core_region_counts`; the BIN axis was refused |
| `validate_plan` | took a `bonding_plan_config.json` snapshot once per plan (`bp_config=` keyword) |

`_reshape_m1_summary` and `_core_region_counts` had no other caller and went with it. The
`bp_config` keyword of `get_stage_source_summary` / `get_lot_bin_summary` went with it.

## Why it is retired — the delegate pointed at things that no longer exist

`dt` was the only stage using it, and **all five of its roles read `missing`** on the
live server. Measured 2026-08-14 on this checkout, `GET /api/transfer-plan/stages`:

```
dt  total_chips:missing  transfer_log:missing  process_history:missing
    defect:missing       eds_fail:missing
```

There were **two** causes, not one:

1. **Four roles — the table is not declared.** `total_chips` and `defect` bound
   `core_defect_map`, `eds_fail` bound `eds_fail_map`, `process_history` bound
   `wafer_process`. None of the three is in `table_config.json`, so
   `models.DYNAMIC_TABLES` has no model and `bonding_plan._resolve_model_columns`
   returns `(None, None)` at its first line. All three are **retired fixture tables**:
   their generators sit in `auto_update_control.json`'s `disabled` list
   (`core_defect_map/generate_core_defect.py`, `eds_fail_map/generate_eds_fail.py`,
   `wafer_process/generate_wafer_process.py`) and they left `table_config.json` between
   the `20260728-005810` and `20260804` backups. They still hold rows (5,152 / 2,576 /
   22), which is why "the columns really exist" was true and irrelevant.

2. **One role — the table is declared, the columns are not.** `used_chips` bound
   `bonding_log.core_lot / core_slot / cx / cy`. `bonding_log` **is** declared, and those
   four columns **do** exist physically — but they are absent from that table's
   `table_config` declaration, so the ORM model has no such attributes and the required
   `lot`/`slot` roles fail to resolve. They are also **NULL on all 357,796 rows**, so
   repairing the declaration would have produced a silent `transferred: 0` rather than an
   error. The DT consumption log is `dt_log` (`core_lot` populated on 12,007 of 13,789
   rows, `core_x`/`core_y` on all 13,789).

The `dt` stage is now declared inline against `core_wafer_map` (total) and `dt_log`
(transfer log). Measured immediately after, same route, no restart — the config is
re-read per request:

```
dt  total_chips:connected  transfer_log:connected
    process_history:not_declared  origin_log:not_declared
```

and `GET /api/transfer-plan/source-summary?stage=dt&lot=CL-2601-001&slot=03` answers
`total 121 / transferred 50 / remaining 71`, which agrees with the independent SQL census
(`core_wafer_map` 121 rows for that wafer; `dt_log` 50 distinct `(core_x, core_y)`).

## What retiring this does NOT do

- **It does not retire `bonding_plan_config.json`, and it cannot yet.** That file still
  has a live consumer: `GET /api/bonding-plan/core-summary` (`server/main.py:4644`),
  which calls `bonding_plan.load_bonding_plan_config()` and
  `bonding_plan.get_core_summary()`. **That route is now serving five `missing` roles**,
  for the causes above — it is broken in exactly the way `dt` was. Retiring the file
  therefore requires retiring or repointing that route, which is a REST path and needs
  the product owner's decision. Consumers counted at retirement (excluding
  `.claude/worktrees/`, `docs/history/`, `agent_workspace/reports/`, `*.bak`):
  `source_config_ref` — **0 in config**, 6 comment mentions in `transfer_plan.py`, 1 test,
  and docs; `load_bonding_plan_config` — **1 live caller** (`main.py:4644`) plus
  `bonding_plan.py` itself and one test; `get_core_summary` — **1 live caller**
  (`main.py:4667`), plus `bonding_plan.py`, `map_overlay.py` (a comment) and three tests.
- **It does not retire `server/bonding_plan.py`.** `DERIVED_ROLE_OF`, the resolver,
  `role_is_declared`, `STATUS_NOT_DECLARED`, `explain_binding_refusal`,
  `canonical_basis`, `fail_filter_status` and the refusal vocabulary all live there and
  `transfer_plan` calls them on every request. This was a config retirement, not a module
  retirement.
- **`BINDING_NOT_REACHED` stays.** It is still in `BINDING_REFUSALS` and `dry_run`'s
  `counts` still buckets on it, so a future delegate reuses the word instead of coining a
  second one.
- **It does not change any data.** Config and Python only; no DDL, no writes.

## What it DID cost — two capabilities, both measured

Report these before reintroducing anything; they are the price of the move, not
side effects that were overlooked.

1. **A core-frame (`frame: "self"`) fail source is no longer aligned.** M1 mapped each
   fail map onto the canonical core frame (`bonding_plan.canonical_basis` +
   `CANONICAL_FRAME_ROLES`) before intersecting. The inline engine calls
   `_canonical_fail_set` only in the `frame == "origin"` branch, which requires an
   `origin_log` — a core-kind stage has none. **Counts are unaffected** (alignment is
   count-invariant), only coordinate intersection is: region and BIN totals. Pinned by
   `server/tests/test_transfer_plan.py::test_core_frame_fail_source_is_not_aligned`,
   which asserts that rotating the map's declared frame changes nothing — flip that
   assertion when the capability returns. **Latent on live**: the `dt` stage declares no
   fail sources at all.
2. **`region_chips.fail_breakdown` lost its per-source keys on the `dt` stage.** The M1
   adapter produced `{"defect": n, "eds_fail": m}`; the inline engine keeps only the
   union and reports `{"all_fail": n}` (the `bonding` stage always behaved this way). No
   consumer: `region_chips` and `fail_breakdown` appear 0 times in `client2/src/`.

Also removed from the `/admin/transfer-plan/dry-run` response: the per-stage
`source_config_ref` field. No client consumer — `client2` fetches only the enrichment
dry-run, never this admin route.

## Revival conditions — in this order

1. **Fix the delegate before restoring the bridge.** Restoring the branch on today's
   configs reproduces five `missing` roles exactly. Both must hold first:
   - `core_defect_map`, `eds_fail_map` and `wafer_process` are declared in
     `table_config.json` **and** their auto-update generators are out of
     `auto_update_control.json`'s `disabled` list — otherwise the tables are registered
     but frozen, and the availability numbers silently age;
   - `bonding_plan_config.json`'s `used_chips` binds a table whose declared columns
     resolve **and are populated**. `bonding_log.core_lot/cx` satisfy neither today.

   Until (1) holds, restoring the branch only restores `missing`.

2. **Then restore the code from git.** The retirement commit removes it in one piece:

   ```
   git log --oneline -S 'M1_SOURCE_REFS' -- server/transfer_plan.py
   git show <sha>^:server/transfer_plan.py > /tmp/before.py     # then diff and port
   ```

   The five branch sites and the two deleted helpers are each marked with a `🗄️` comment
   at the exact place they stood, so the diff is readable in both directions.

3. **Prefer not to.** The reason the bridge existed was backward compatibility with M1's
   config shape, and the inline form is strictly more expressive: it can declare
   `origin_log`, `fail_sources` with per-source frames, a `bin_map` axis, and
   `lot_membership`, none of which the delegation path could reach. If the goal is
   "reuse one declaration in two places", the honest shape is one config with two
   readers, not one reader that reads another config's schema.
