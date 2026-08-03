# Server report - `bin_map` refused on the live bonding stage (2026-08-04)

Round: diagnose (Part 1) -> name the refusal (Part 2) -> propose (Part 3).
Environment: conda `assy_manager`, live simulation DB, READ-ONLY (SELECT +
`information_schema` only; no DDL, no write to `server/config/*.json`).

---

## Part 1 - DIAGNOSIS

### The single actual cause

**The config is wrong, not the reader.** The declaration is present, well-formed,
points at a declared table, and names every required role - and two of the column
names inside it do not exist on that table.

Live fragment, `C:\Users\kk980\Developments\assyManager\server\config\transfer_plan_config.json`
lines 19-28:

```json
"bin_map": {
  "table": "dt_log",
  "columns": {
    "lot": "dt_lot",
    "slot": "dt_slot",
    "x": "x",          <-- dt_log has no column `x`
    "y": "y",          <-- dt_log has no column `y`
    "bin": "c_bn"
  }
}
```

`dt_log`'s real coordinate columns are **`dt_x` / `dt_y`** (verified two ways:
`table_config.json` `column_types`, and live `information_schema.columns`).

### The predicate that fails, exactly

1. `server/transfer_plan.py:_bin_axis_binding` resolves the declaration with
   `required=("lot", "slot", "x", "y", "bin")`.
2. `server/bonding_plan.py:_resolve_model_columns` walks `columns`; for role `x`
   it does `getattr(model, "x", None)` -> `None`; `x` is in `required`, so it
   returns `(None, None)` at **`server/bonding_plan.py:285`** (pre-change line
   number; the resolver body is unchanged).
3. `_bin_axis_binding` returns `(None, None, None)`.
4. `server/transfer_plan.py:_bins_block` sees `model is None` and emits the
   "not declared" block.

Measured on the live config, before the Part 2 change:

```
_bin_axis_binding -> UNRESOLVED (None, None, None)
_bins_block(bonding, DT-2601-001/22).detail
  = "이 단계에 BIN 축(`bin_map`)이 선언돼 있지 않습니다 - BIN별 가용을 계산할 수 없습니다."
```

The message was **false**: it was declared.

### Every acceptance condition, checked against the live system

| # | Condition | Result |
|---|---|---|
| 1 | declaration present at `stages.bonding.bin_map` or `...source.bin_map` | PASS (stage-level, line 19) |
| 2 | shape `{table: str, columns: dict}` (`_valid_binding`) | PASS |
| 3 | `table` declared in `table_config.json` | PASS - `dt_log` is one of 14 declared tables |
| 4 | all 5 required role keys present in `columns` | PASS - lot, slot, x, y, bin |
| 5 | **each named column exists on the ORM model** | **FAIL - `x`, `y`** |
| 6 | lot/slot roles agree with the table's `map_key_columns` | PASS - `dt_log.map_key_columns = ["dt_lot","dt_slot"]`, and the declaration uses exactly those |
| 7 | reader sees the file on disk (no stale singleton) | PASS - see below |
| 8 | `role_is_declared` presence-vs-truthiness (the `c09bb0e` / `transfer_plan.py:1447` bug shape) | NOT THE CAUSE - `bin_map` never goes through `_aux_role_status`; it is resolved directly |

**Restart is NOT required, in either direction.**
`transfer_plan.load_transfer_plan_config` (`server/transfer_plan.py:265-279`)
opens the file on every call with no cache, so the reader was already seeing the
current file, and a corrected file takes effect on the next request. The one
thing that *does* need care is `table_config.json`, which is loaded into
`models.DYNAMIC_TABLES` at boot - but nothing in that file needs to change here.

Physical evidence rather than a 200 from `/schema`:

```
information_schema.columns WHERE table_name='dt_log'
  ... dt_lot, dt_slot, dt_x, dt_y, core_lot, core_slot, core_x, core_y, c_bn, ...
  (legacy leftovers also present and 100% NULL: tape_lot, tape_slot, tx, ty, cx, cy)
  no column named `x`, no column named `y`
```

Live data confirms the corrected binding will actually answer:
`dt_log` = 8,700 rows; `dt_x`/`dt_y`/`c_bn` 100% populated; `dt_lot`/`dt_slot`
5,651/8,700 (the fixture's stated ~40% absent inference target); `c_bn`
distinct = `'1'` (8,618) and `'0'` (82).

### A SECOND, independent break in the same stage - this is the "remaining does not work" half

`source.total_chips` (lines 41-49) is broken the same way, worse:

```json
"total_chips": {
  "table": "dt_log",
  "columns": { "lot": "lot", "slot": "slot", "x": "x", "y": "y" }
}
```

**All four column names are wrong.** `total_chips` is the required denominator,
so `_binding_status` returns `missing`, which drives `EFFECT_TOTAL_UNKNOWN` and
makes every remaining/available figure for the bonding stage unknowable -
independently of `bin_map`. Measured now:

```
list_stages().roles
  bonding: {"total_chips": "missing", "transfer_log": "not_declared",
            "process_history": "not_declared", "origin_log": "not_declared"}
```

### Root of both: a table swap that left the reference template's generic column names behind

`docs/guide/config_reference/transfer_plan_config.json` declares the bonding
stage against `dt_map` with generic names (`lot`, `slot`, `x`, `y`, `val`). The
live simulation env was reshaped into the DT-inference trace fixture (per the
`dt_log` `__comment`, user 2026-08-01), where every column is prefixed
(`dt_*` / `core_*`). Someone repointed `table` to `dt_log` and updated `lot`/
`slot`/`bin` but left `x`/`y` at the template's spelling; `total_chips` was not
touched at all. Note the reference template itself no longer resolves either -
`dt_map` in this env is `cell_key, dt_job, dt_x, dt_y, c_bn`, keyed by `dt_job`.

### Full binding audit of the live plan configs (read-only)

```
=== transfer_plan_config.json ===
  [COLUMN MISSING] stages.bonding.bin_map            -> dt_log : x='x', y='y'
  [ok]             stages.bonding.source.map_metadata-> wafer_map_metadata
  [COLUMN MISSING] stages.bonding.source.total_chips -> dt_log : lot='lot', slot='slot', x='x', y='y'
  [ok]             plan_store.registry               -> map_split_registry
  ok=2, unresolvable-table=0, missing-column-refs=6

=== bonding_plan_config.json ===   (the `dt` stage delegates here via source_config_ref)
  [ok]                  map_metadata            -> wafer_map_metadata
  [TABLE NOT DECLARED]  sources.process_history -> wafer_process
  [TABLE NOT DECLARED]  sources.defect          -> core_defect_map
  [TABLE NOT DECLARED]  sources.eds_fail        -> eds_fail_map
  [COLUMN MISSING]      sources.used_chips      -> bonding_log : lot='core_lot', slot='core_slot', x='cx', y='cy'
  [TABLE NOT DECLARED]  sources.total_chips     -> core_defect_map
  ok=1, unresolvable-table=4, missing-column-refs=4
```

So the whole `dt` stage is unwired too (4 tables that no longer exist in this
env). The user did not report it, so nothing was changed - flagging it.

### The exact edit for the user to apply (NOT applied by me)

File: `C:\Users\kk980\Developments\assyManager\server\config\transfer_plan_config.json`
No restart needed; takes effect on the next request.

Replace lines 19-28:

```json
      "bin_map": {
        "table": "dt_log",
        "columns": {
          "lot": "dt_lot",
          "slot": "dt_slot",
          "x": "dt_x",
          "y": "dt_y",
          "bin": "c_bn"
        }
      },
```

Replace lines 41-49 (`source.total_chips`):

```json
        "total_chips": {
          "table": "dt_log",
          "columns": {
            "lot": "dt_lot",
            "slot": "dt_slot",
            "x": "dt_x",
            "y": "dt_y"
          }
        },
```

Optional follow-up, user's call - `transfer_log` for the bonding stage is not
declared at all, so consumption is never subtracted and the reading stays
`not_declared` / `inactive_subtractions`. `bonding_log` carries the tape-frame
identity of each bonded die (`dt_lot`, `dt_slot`, `dt_x`, `dt_y`), which is the
natural binding:

```json
        "transfer_log": {
          "table": "bonding_log",
          "columns": {
            "lot": "dt_lot", "slot": "dt_slot", "x": "dt_x", "y": "dt_y"
          }
        },
```

Not prescribed - it changes what `remaining` means, so it should be a decision,
not a patch.

---

## Part 2 - the refusal now names its cause

### What changed

New: `bonding_plan.explain_binding_refusal(src_cfg, required, label, where)`
-> `(reason, Korean sentence)`, `(None, None)` when the binding resolves. It sits
next to `_resolve_model_columns` because that is already the declared home of
shared resolver mechanics (`_demote_for_unresolved` comment).

The accept/reject decision is **not duplicated** - `_resolve_model_columns` still
decides; the new function re-walks the same inputs to describe the FIRST failing
check. `test_diagnostic_agrees_with_the_resolver` scores the two against each
other over 12 declarations so they cannot drift apart silently.

Closed vocabulary, borrowed not invented:

| cause | reason word | borrowed from |
|---|---|---|
| key absent / required role never named | `not_declared` | `config_resolve_report.REASON_NOT_DECLARED` |
| shape unreadable, or table not in `table_config.json` | `mapping_unavailable` | `config_resolve_report.REASON_MAPPING_UNAVAILABLE` |
| role named at a column the table does not have | `candidate_column_missing` | `enrichment_candidates.REASON_CANDIDATE_COLUMN_MISSING` |

`bonding_plan` spells the three literally rather than importing those modules
(it should not depend on the admin-report or enrichment stacks);
`test_vocabulary_matches_its_canonical_definitions` pins each literal equal to
its upstream definition, so a rename cannot leave a second spelling behind.

### Call sites rewired (`server/transfer_plan.py`)

- `_bin_axis_source` / `BIN_AXIS_ROLES` / `BIN_AXIS_WHERE` extracted so the
  judgement and the sentence read the same declaration from the same two places.
- `_bin_axis_refusal(stage_cfg)` and `_lot_membership_refusal(stage_cfg)` -
  both go through the one diagnostic, via `_refusal()` which guarantees a
  non-empty sentence (a raw `(None, None)` interpolated into a message would
  print `None` on screen - the exact opposite of the goal).
- `_bins_block` refusal - was one generic string, now the named cause.
- `get_lot_source_summary` "no `bin_map` and no `lot_membership`" refusal - now
  reports **each source separately** (`(1) ... (2) ...`). The merged sentence used
  to report a site that legitimately does not use a material ledger and a
  `bin_map` column typo with identical wording.
- `_bins_unavailable` gained an optional `reason` field carrying the vocabulary
  word. Query-failure and cap-truncation refusals leave it `None` - no word is
  forced onto a cause outside the closed vocabulary.

### What the live config now says

```
reason : candidate_column_missing
detail : BIN별 가용을 계산할 수 없습니다 ― `bin_map`의 필수 역할이 가리키는 컬럼이
         테이블 `dt_log`에 없습니다 (읽는 자리: stages.<stage>.bin_map 또는
         stages.<stage>.source.bin_map): x → `x`, y → `y`. `dt_log`의 실제 컬럼:
         business_key_val, c_bn, core_lot, core_slot, core_wafer, core_x, core_y,
         created_at, dt_cell_key, dt_eqp, dt_job, dt_lot, dt_slot, dt_x, dt_y,
         event_time, graph_synced_at, is_graph_synced, needs_graph_rollback,
         product, row_id, updated_at.
```

The operator can fix the file from that sentence without opening a debugger.

**No client change needed.** `client2/src/transfer_plan.js:460` already renders
`block.detail` verbatim on the `bins_unavailable` path, so the improved sentence
reaches the screen as-is, and the added `reason` key is ignored by the existing
reader.

### cp949

Every sentence the change can emit was `.encode("cp949")`-tested (a pytest case,
plus a standalone sweep): 0 failures. No emoji, no U+2014. U+2015, U+2192 and
the circled digits used are all in KS X 1001 and were verified encodable.

### Tests

New file: `C:\Users\kk980\Developments\assyManager\server\tests\test_binding_refusal.py`
(12 tests, isolation prefix `binref_test_*` - cannot collide with a user config
table, per the `bonding_log` incident in the memory file).

Pins the message content for **five** distinct causes (the brief asked for two):
declared-but-wrong-column, absent declaration, table not in `table_config.json`,
required role key never named, malformed shape.
`test_every_cause_produces_a_distinct_sentence` pins the reason vector alongside
the sentence set, so a collapse cannot slip through by keeping the strings
incidentally different while re-labelling the cause.

**Defect injection (memory rule: prove the test executes the new line).**
Making the column-missing branch return the generic `not_declared` sentence -
i.e. re-creating exactly the bug being fixed - fails 4 of the 12:
`test_declared_but_column_name_wrong_says_so`,
`test_missing_role_key_is_not_the_same_sentence_as_a_wrong_column`,
`test_bins_block_carries_the_named_cause`,
`test_lot_membership_refusal_uses_the_same_diagnostic`.
The injection was reverted via the Edit tool (no script rewrite, so no CRLF
churn); `git diff` confirms only the intended hunks remain.

Suite: `conda run -n assy_manager python -m pytest server/tests/ -q` ->
**1879 passed, 2 skipped** (baseline 1867 + 2, plus the 12 new). No regressions.
Repo-wide `pytest` cannot be run as one command: `server/scripts/archive/
test_cte_search.py` and `test_work_mem.py` fail at COLLECTION because they open a
live Postgres connection at import - pre-existing, unrelated, untouched.

### Boundary-contract note for the lead PM

`_bins_unavailable` now emits one additional key, `reason`, inside the `bins`
block of the stage-source-summary responses. Additive only; `detail`, `axis`,
`entries`, `scope`, `requested`, `truncated`, `cells_truncated` are unchanged,
and the existing client ignores unknown keys. Flagging it rather than assuming
it: it is a REST response-body addition. Nothing else in the boundary contract
was touched (no REST path/signature change, no WS event, no cell shape, no
`table_config.json` -> `/schema` change).

### Doc impacts (NOT written - doc lanes are live)

- `docs/guide/config/transfer_plan_config.md` - should state that `bin_map`
  column values are **real column names on the bound table**, not role names,
  and that the reference template's generic `x`/`y`/`val` are placeholders. This
  is the misreading that caused the incident.
- `docs/guide/config_reference/README.md` - the three documented silent-failure
  modes now have a fourth sibling worth naming: *declared, well-formed, correct
  table, correct roles, wrong column name*. Also worth recording that this class
  of refusal now answers with a named reason.
- `docs/guide/config_reference/transfer_plan_config.json` - the shipped
  reference does not resolve against the current `table_config.json` in this
  environment (points at `dt_map` with `lot`/`slot`/`x`/`y`/`val`). Either the
  reference or a note beside it should say which schema it assumes.
- `docs/architecture/CODE_MAP.md` - new symbols:
  `bonding_plan.explain_binding_refusal`, `bonding_plan.BINDING_*`,
  `transfer_plan._bin_axis_source` / `_bin_axis_refusal` / `_lot_membership_refusal`
  / `_refusal`, `transfer_plan.BIN_AXIS_ROLES` / `LOT_MEMBERSHIP_ROLES`.

---

## Part 3 - PROPOSAL (not implemented)

### Measured, not guessed

| metric | reference template | live file |
|---|---|---|
| keys (excluding `__comment`) | 107 | 57 |
| `table` references (into `table_config.json`) | 11 | 6 |
| column references (into that table's columns) | 50 | 20 |
| **cross-referential leaves** | **61 of 107 = 57%** | **26 of 57 = 46%** |
| distinct tables named | 9 | 4 |

`transfer_plan.py` has **18** `required=` sites across 8 distinct role tuples
(from `("lot","slot")` up to an 8-role origin tuple), and **40** `.get(...) or {}`
/ `or []` reads - each one a place where absent and null are collapsed before any
check runs.

So: **over half of what an operator types is a name that must match something in
another file, and nothing checks it until a live request happens to touch that
role.** That is the difficulty. It is not the key count.

Ranked recommendations:

**1. A validating dry-run route. Highest value per unit of work.**
`GET /admin/config/transfer-plan/dry-run` returning, for every binding in the
file, the `(reason, detail)` this round already produces - the audit table in
Part 1 is literally its output, and the engine now exists. Answers "would this
declaration be accepted, and if not, why" without touching data, and would have
caught board O4, board O7, and this incident before anyone opened a map.
Precedent: `GET /admin/enrichment/auto-confirm/dry-run`, which measures rules
that are switched OFF via `ignore_knob=True` - the same idea, that a check must
be able to evaluate a declaration that is not currently live. Should also accept
a **candidate body** so an operator can validate an edit before saving it.
Cheap because the predicate is already written and already tested.

**2. Derive the column map when it follows the table's own convention.**
Precedent: `map_overlay_config` declares bindings only where columns depart from
the x/y/val convention and derives the rest from `table_config` - and its own
comment notes that a duplicate declaration hides whether the derivation path
still works. Concretely for transfer_plan:
  - `lot` / `slot` are already declared per table as `map_key_columns`.
    `dt_log.map_key_columns = ["dt_lot","dt_slot"]` is exactly what the correct
    `bin_map` and `total_chips` would have said. **Roughly 8 of the live file's
    20 column references are re-statements of `map_key_columns`.**
  - `x` / `y` could derive from a per-table coordinate convention (a
    `map_xy_columns` in `table_config`, one declaration per table instead of one
    per role per stage).
  - `bin` / `val` should stay explicit: `_bin_axis_binding`'s docstring already
    argues, correctly, that guessing "the map's `val` is the BIN" is wrong at
    this site, and the same `dt_map.val` is a core identifier elsewhere.
  Keep the escape hatch (an explicit declaration always wins), but make the
  common case omissible - and follow `map_overlay_config`'s warning: a
  *redundant* explicit declaration should be reported, because it hides whether
  the derivation still works.

**3. A one-line refusal is not a report - give the dry-run a UI surface.**
Once (1) exists, the admin config panel should show the same three populations
`config_resolve_report` already defines (`effective` / `ineffective` /
`rejected`) for transfer_plan, reusing `build_domain` and registering a resolver
in `_RESOLVERS`. That module's own docstring says enrichment was the first slice
and the second one is what reveals whether the frame generalises. transfer_plan
is a good second slice: it is where the failures actually happen.

**4. Lowest priority - shrink the required-role tuples.**
8 distinct tuples across 18 sites is a lot of vocabulary for an operator to hold.
Naming them (`BIN_AXIS_ROLES` and `LOT_MEMBERSHIP_ROLES` from this round are the
first two) and documenting each as a named role set would make the error messages
and the guide agree. Mechanical, low risk, low payoff on its own - do it after
(1) and (2), or as part of them.

---

## Handover

**Changed**
- `C:\Users\kk980\Developments\assyManager\server\bonding_plan.py` - new
  `explain_binding_refusal`, `BINDING_*` vocabulary, `_model_column_names`.
  `_resolve_model_columns` itself is unchanged.
- `C:\Users\kk980\Developments\assyManager\server\transfer_plan.py` - refusal
  sites now name their cause; `_bin_axis_source`/`_bin_axis_refusal`/
  `_lot_membership_refusal`/`_refusal` added; `_bins_unavailable` gained
  `reason`.
- `C:\Users\kk980\Developments\assyManager\server\tests\test_binding_refusal.py` - new, 12 tests.

**Not changed (deliberately)**
- `server/config/transfer_plan_config.json` - read-only round; the exact edit is
  written out above for the user to apply.
- `docs/**` - doc lanes are live; impacts listed above instead.
- `client2/**` - client lane is live; no client change is needed anyway.
- `bonding_plan_config.json`'s four dead table references - out of scope, flagged.

**Verified**
- Live config + live `information_schema` + live row counts (read-only).
- Reader-level reproduction before and after.
- Defect injection proves the new tests execute the new lines.
- `server/tests/` : 1879 passed, 2 skipped.
- cp949 encodability of every emittable sentence: 0 failures.

**Unresolved / next**
1. The user must apply the config edit (bin_map + total_chips). Nothing else
   unblocks them.
2. The `dt` stage is entirely unwired (`bonding_plan_config.json` points at 4
   tables that do not exist in this env). Separate decision.
3. `transfer_log` for the bonding stage is undeclared - `remaining` will have no
   consumption subtracted even after the fix. Needs a product decision.
4. Part 3 items 1-3 are a separate implementation round.

**Proposed memory entries for `agent_workspace/memory/server-pm.md`** (not added
directly, per the file's own rule):
- 함정: `{table, columns}` 바인딩이 거절되면 "선언돼 있지 않습니다"만 나와서, 선언이
  **있는데** 컬럼명이 틀린 가장 흔한 경우에 그 문장이 거짓이 된다. 2주에 3번 반복
  (보드 O4·O7, 2026-08-04 `bin_map.columns.x`).
  올바른 방법: 라이브 config를 의심할 땐 파일을 눈으로 읽지 말고 `DYNAMIC_TABLES`의
  모델에 `getattr`로 **컬럼 존재를 직접 물어라**. 이제
  `bonding_plan.explain_binding_refusal`이 그 판정을 문장으로 돌려준다.
- 함정: 사용자 config의 테이블을 교체하면서 컬럼명은 레퍼런스 템플릿의 **일반명**
  (`x`/`y`/`val`/`lot`)으로 남겨두면, 형태 검증·필수 역할 검증을 전부 통과하고 조회
  시점에만 조용히 죽는다. `docs/guide/config_reference/*.json`은 특정 스키마를 가정한
  예시이지 이식 가능한 기본값이 아니다.
  올바른 방법: 테이블을 바꾸면 그 테이블의 `map_key_columns`와 `column_types`를 열어
  **모든** 역할의 컬럼명을 다시 쓴다 - 한 블록만 고치면 형제 블록(`total_chips` 등)이
  남는다.
