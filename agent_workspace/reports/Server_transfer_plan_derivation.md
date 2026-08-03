# Server report - derive the coordinate columns, and give the operator a place to ask what won

Round: derivation + validating dry-run, built together per the user ruling.
Environment: conda `assy_manager`. Live DB READ-ONLY. `server/config/*.json` not written.

Follows `Server_bin_map_diagnosis.md` / commit `12c1d2e`.

---

## 1. What was actually wrong with the config format

The coordinate binding for `dt_log` already existed in this repo, in
`server/config/map_overlay_config.json`:

```json
"dt_log": { "columns": { "x": "dt_x", "y": "dt_y", "val": "c_bn",
                         "key_columns": ["dt_job"] } }
```

`transfer_plan_config` asked the operator to retype that answer, role by role,
and the 2026-08-04 typo landed exactly in the retyping. That file's own
`__derived_note` already states the rule this round implements:

> declare a binding ONLY where the coordinate columns depart from the x/y/val
> convention ... a duplicate declaration only hides whether the derivation path
> still works.

So this was a third spelling of one fact, not a missing feature.

## 2. Derivation

### No new mechanism

`map_overlay.resolve_binding_info(cfg, table)` already answers "what are this
table's coordinate and value columns", already prefers a declaration over
`table_config` derivation, and already labels which one won
(`declared` / `derived` / `fallback_guess`). It fits, so it is what gets called.
Nothing about map_overlay was changed.

New in `server/bonding_plan.py`:

- `resolve_effective_columns(source_cfg, required) -> (columns, derivation)`
- `deletion_hints(src_cfg, roles, model) -> [(role, would_derive)]`
- `DERIVED_ROLE_OF = {"x": "x", "y": "y", "val": "val", "bin": "val"}`
- `DERIVATION_DECLARED / DERIVATION_DERIVED / DERIVATION_UNAVAILABLE`
- `_overlay_config_snapshot()` - memoized on the overlay file's `(mtime_ns, size)`.
  A resolver runs several times per request; re-reading per role would put a disk
  hit exactly in the configs that adopt the shorter form. Hot-reload survives
  (a saved edit changes mtime).

`_resolve_model_columns` now walks the *effective* columns. It is still the one
predicate; derivation happens inside it, so every reader gets it at once and no
call site needed a flag.

### Explicit always wins - absent-only fill

`resolve_effective_columns` returns **the caller's own `columns` object**, by
identity, when no required derivable role is missing. Not a copy - identity, so
iteration order (which `_resolve_model_columns` walks to build `unresolved`) is
provably untouched.

**Byte-identity evidence** (`test_fully_declared_response_is_byte_identical_with_and_without_derivation`):
the full `get_stage_source_summary` response is computed twice over identical
seeded data - once normally, once with `resolve_effective_columns` replaced by a
pass-through that cannot fill anything - and the md5 of the sorted-key JSON is
compared.

```
MD5 with derivation active : 67818d723c86d37af4b0988237006862
MD5 with derivation removed: 67818d723c86d37af4b0988237006862
```

The fixture is not vacuous: the same test asserts `chips.total > 0` and
`bins.axis == "connected"`, so the hash covers a response that actually carries
numbers. Operators change nothing.

### What is NOT derived, and why

| not derived | reason |
|---|---|
| `lot` / `slot` and every key role | Overlay keys `dt_log` by `dt_job`; the plan keys it by `dt_lot`/`dt_slot`. That difference is real information about purpose. |
| `origin_x` / `origin_y` | A second coordinate pair on the same table. The map binding describes one pair and cannot say which. |
| **any role the caller did not mark `required`** | The load-bearing one - see below. |
| a `fallback_guess` value column | map_overlay keeps that guess out of its own data path; an availability count is not where it should leak back in. Coordinates of a guessed binding are still literal/declared, so those stay usable. |

**The optional-role restriction is the safety property of this change.**
`transfer_plan._summarize_inline` reads a `transfer_log` that declares no x/y as
`connected(count_only)` and subtracts a count instead of a coordinate set;
`bonding_plan`'s canonical-frame pick skips a role that declares no coordinates.
Absence there is already information every reader acts on. Filling it would
silently convert a count-only site into set subtraction and change numbers
nobody asked to change. So absence is only ever filled where absence would
otherwise have been a refusal.

### Derivation that fails, fails by name

Never silent. A required derivable role that is omitted and cannot be derived
returns `mapping_unavailable` with a sentence naming the role, the table, the
map-binding roles it looked for, and both places it looked
(`map_overlay_config.json` `table_bindings`, then `table_config.json`'s x/y
convention). An omitted *key* role still returns `not_declared`, because keys are
never derived - two different words for two different fixes, pinned by
`test_every_cause_produces_a_distinct_sentence`.

`not_reached` (`config_resolve_report.REASON_NOT_REACHED`) joined the vocabulary
as `bonding_plan.BINDING_NOT_REACHED`, for a stage that delegates its source
roles via `source_config_ref`: that stage never reads its own `source.*` block,
so calling those "not declared" would invite an operator to fill in a block
nothing consults.

### Derivation source, per role (live measurement)

`map_overlay_config.json` declares bindings for `core_wafer_map`, `dt_map`,
`dt_log`, `bonding_log`; `bonding_map` and friends derive from `table_config`'s
literal x/y. For the live bonding stage:

| role | source | resolved |
|---|---|---|
| `bin_map.x` | `map_overlay_declared` (`dt_log.x`) | `dt_x` |
| `bin_map.y` | `map_overlay_declared` (`dt_log.y`) | `dt_y` |
| `bin_map.bin` | `map_overlay_declared` (`dt_log.val`) | `c_bn` |

---

## 3. The validating dry-run route

`GET /admin/transfer-plan/dry-run` - `server/main.py`, engine in
`transfer_plan.dry_run(cfg)`.

Auth: `Depends(require_admin_token)`, matching
`GET /admin/enrichment/auto-confirm/dry-run`. Not strict, because it is purely
read-only: no parameters at all, no row queries, model/column resolution only
(`test_dry_run_touches_no_data` fails the run if any role reaches the database).
The precedent measures rules that are switched OFF via `ignore_knob=True`; this
measures declarations that are not currently exercised - the same shape of
question, "answer before you turn it on".

It reuses `explain_binding_refusal`. There is no second explainer.

### Response shape

```jsonc
{
  "config_path": "...",
  "stages": [{
    "name": "bonding",
    "source_config_ref": null,
    "target_map": {...},
    "roles": [{
      "role": "bin_map",
      "where": "stages.bonding.bin_map",
      "declared": true,
      "table": "dt_log",
      "accepted": false,
      "reason": "candidate_column_missing",      // closed vocabulary
      "detail": "...",                            // Korean, rendered verbatim
      "required": ["lot","slot","x","y","bin"],
      "columns": {
        "lot": {"column":"dt_lot","origin":"declared","required":true,
                "derivable":false,"derived_from":null,"derived_role":null,
                "exists_on_table":true},
        "x":   {"column":"x","origin":"declared","required":true,
                "derivable":true,"derived_from":null,"derived_role":null,
                "exists_on_table":false}
      },
      "removable_declarations": [{"role":"x","would_derive":"dt_x"},
                                 {"role":"y","would_derive":"dt_y"}]
    }]
  }],
  "plan_store": [ ...same role shape... ],
  "counts": {"total":18,"accepted":2,"rejected":2,"not_declared":7,
             "not_reached":7,"derived_columns":0,"removable_declarations":2}
}
```

`columns` covers **required roles plus every declared role**, so an operator sees
every line they wrote. `required` and `derivable` are what separate "you can
delete this, it will be derived" from "delete this and a capability disappears" -
see §5, which is the trap the shorter form would otherwise create.

### Live output (read-only, current file)

```
counts: {"total":18,"accepted":2,"rejected":2,"not_declared":7,"not_reached":7,
         "derived_columns":0,"removable_declarations":2}

stage dt        bin_map          not_declared
                (7 source roles) not_reached   -> delegated to bonding_plan config
stage bonding   bin_map          candidate_column_missing
                                 removable: x->dt_x, y->dt_y
                map_metadata     ACCEPTED
                total_chips      candidate_column_missing
                (5 others)       not_declared
plan_store      registry         ACCEPTED
                source_region    not_declared
```

---

## 4. The thing the user hits immediately

Their `bin_map` declares `"x": "x"` explicitly and wrongly. **Explicit wins, so
derivation does not rescue it** - the wrong spelling keeps winning. The clean
repair is therefore *deleting* those entries, not correcting them.

Both surfaces now say that. The refusal sentence ends with:

```
... 이 역할들은 선언을 **지우면** 유도로 해결됩니다: x → `dt_x`, y → `dt_y`
(`dt_log`의 맵 바인딩에서 유도).
```

and the dry-run carries the same fact as structured data in
`removable_declarations`. A dead end became an instruction.

### The edit for the user to apply (still NOT applied by me)

`C:\Users\kk980\Developments\assyManager\server\config\transfer_plan_config.json`.
No restart; the config is read per request.

**`stages.bonding.bin_map` - short form, replaces lines 19-28:**

```json
      "bin_map": {
        "table": "dt_log",
        "columns": {
          "lot": "dt_lot",
          "slot": "dt_slot"
        }
      },
```

`x`, `y`, `bin` are derived as `dt_x`, `dt_y`, `c_bn` from `dt_log`'s binding in
`map_overlay_config.json`. Verified accepted by the dry-run.

**`stages.bonding.source.total_chips` - x/y must be CORRECTED, not deleted:**

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

`total_chips` requires only `lot`/`slot`; its `x`/`y` are **optional**, and
optional roles are never derived. Deleting them here would not be filled in - it
would silently drop region-scoped counting. The dry-run marks these
`"required": false, "derivable": false` precisely so this is visible before it
bites.

---

## 5. How many declaration leaves this removes

Measured against the live file, counting a leaf as omissible only when its role
is **required** for that binding's reader (optional coordinate refs are excluded,
because omitting them is not equivalent):

| | before | after adopting the short form |
|---|---|---|
| keys (excl. `__comment`) | 57 | 54 |
| table references | 4 | 4 |
| column references | 20 | 17 |
| **cross-referential leaves** | **24 of 57 = 42%** | **21 of 54 = 39%** |
| omissible column refs | - | **3 (15% of column refs)** |
| coordinate refs that are optional and therefore never derived | 2 | 2 |

3 of 20 is a modest headline, and it is the honest one. The number that matters
is *which* three: `bin_map`'s `x`, `y`, `bin` - the exact leaves the incident
landed in, and the only leaves in this file where a coordinate has to be
restated. On the shipped reference template the mechanism measures 0 here,
because that file points at `dt_map` with generic names plus three tables that do
not exist in this environment (see §7).

The bigger effect is not the count. It is that a new writer never has to know
`dt_log`'s column prefixes at all: the short form is `{table, lot, slot}`.

---

## 6. Tests

New: `C:\Users\kk980\Developments\assyManager\server\tests\test_transfer_plan_derivation.py` (16).
Updated: `C:\Users\kk980\Developments\assyManager\server\tests\test_binding_refusal.py` (13, was 12).

Pinned:
- fully-declared columns returned **by identity**, derivation empty;
- **md5 byte-identity** of a real response with and without derivation;
- a wrong explicit declaration still loses, and the message says "지우면";
- omitted roles derive from a declared map binding (source labelled);
- a conventional table derives with **no** overlay declaration (different source,
  same path);
- keys are never derived;
- optional roles are never filled (`transfer_log` count-only preserved);
- derivation failure is named `mapping_unavailable`, never silent;
- a `fallback_guess` value column is refused for the value role while its
  coordinates stay usable;
- dry-run shows which spelling won, per role;
- dry-run distinguishes a deletable column from a load-bearing one;
- dry-run marks a delegating stage `not_reached`;
- dry-run touches no data;
- the route is admin-gated (200 unset, 401 with a token configured);
- cp949-encodability of every emittable sentence.

**Defect injection.** Changing `resolve_effective_columns` to fill every
derivable role (derivation overriding explicit declarations, the exact rule
violation the ruling forbids) fails 9 tests across both files, including the
byte-identity proof and the optional-role restriction. Reverted via the Edit
tool; `git diff` confirms only intended hunks.

Two test-isolation fixes were needed and made: `refusal_env` now points
`map_overlay.CONFIG_PATH` at a nonexistent file and resets the overlay memo, so
those cases test the resolver rather than the user's live overlay declarations.

Suite: `conda run -n assy_manager python -m pytest server/tests/ -q` ->
**1896 passed, 2 skipped** (baseline 1879 + 2, plus 17 net new). No regressions.
Repo-wide `pytest` still cannot run as one command: `server/scripts/archive/
test_cte_search.py` and `test_work_mem.py` fail at COLLECTION on a live Postgres
connection at import - pre-existing, unrelated, untouched.

cp949: the only U+2014 on any added line is inside the two assertions
`assert "—" not in detail`, which are the guards themselves. No emoji added.

---

## 7. Out of scope this round - report only, as instructed

- `server/config/bonding_plan_config.json` points at three tables that do not
  exist in this environment (`wafer_process`, `core_defect_map`, `eds_fail_map`)
  plus four wrong column names on `bonding_log` (`core_lot`/`core_slot`/`cx`/`cy`
  against a table whose columns are `bond_*`/`dt_*`). The whole `dt` stage is
  unwired. Note that `map_overlay_config` DOES declare `bonding_log` as
  `bond_x`/`bond_y`/`b_bn`, so several of those leaves would be derivable if
  someone repairs the keys.
- `docs/guide/config_reference/transfer_plan_config.json` does not resolve here
  either (points at `dt_map` with generic `lot`/`slot`/`x`/`y`/`val`).

---

## Handover

**Changed**
- `C:\Users\kk980\Developments\assyManager\server\bonding_plan.py` - derivation
  core, `deletion_hints`, `BINDING_NOT_REACHED`; `_resolve_model_columns` walks
  effective columns; `explain_binding_refusal` reports derivation failure and the
  deletion hint.
- `C:\Users\kk980\Developments\assyManager\server\transfer_plan.py` - named role
  tuples (`IDENTITY_ROLES`, `ORIGIN_LOG_ROLES`, `ORIGIN_AREA_MAP_ROLES`,
  `SOURCE_REGION_ROLES`, `MAP_METADATA_ROLES`, `BIN_AXIS_ROLES`,
  `LOT_MEMBERSHIP_ROLES`) replacing inline copies at 4 call sites; `dry_run()`
  and `_role_dry_run()`.
- `C:\Users\kk980\Developments\assyManager\server\main.py` -
  `GET /admin/transfer-plan/dry-run`.
- `C:\Users\kk980\Developments\assyManager\server\tests\test_transfer_plan_derivation.py` (new)
- `C:\Users\kk980\Developments\assyManager\server\tests\test_binding_refusal.py` (updated)

**Not changed**
- `server/config/*.json`, `docs/**`, `client2/**`.

**Boundary-contract notes for the lead PM**
1. New route `GET /admin/transfer-plan/dry-run` (admin-gated, read-only, no
   parameters). Additive.
2. `_bins_unavailable`'s additive `reason` key from the previous commit is
   unchanged.
3. No change to `/api/transfer-plan/stages`, `/source-summary`, `/validate`
   response shapes; no WS event, no cell shape, no schema contract.

**Doc impacts (NOT written - report only)**
- `docs/guide/config/transfer_plan_config.md` - the short form is now the
  recommended way to write a coordinate binding; document which roles derive
  (`x`, `y`, `val`/`bin`), which never do (keys, `origin_*`), and the
  required-vs-optional asymmetry from §4 that makes `total_chips.x` a correct-me
  and `bin_map.x` a delete-me.
- `docs/guide/config_reference/README.md` - the dry-run route is now the answer
  to "did my config take"; the three documented silent-failure modes gain a
  fourth (declared, well-formed, right table, right roles, wrong column name).
- `docs/guide/CONFIG_GUIDE.md` - `transfer_plan_config.json` now reads
  `map_overlay_config.json`. That cross-file dependency did not exist before and
  is not obvious from either file.
- `docs/architecture/CODE_MAP.md` - **its `transfer_plan.py` anchors were
  re-measured against `ed9cfdb` and this commit shifts them.** New symbols:
  `bonding_plan.resolve_effective_columns` / `deletion_hints` /
  `DERIVED_ROLE_OF` / `DERIVATION_*` / `BINDING_NOT_REACHED` /
  `_overlay_config_snapshot` / `_map_binding_for`; `transfer_plan.dry_run` /
  `_role_dry_run` / `_STAGE_SOURCE_ROLES` and the seven role tuples;
  `main.get_transfer_plan_dry_run`.

**Unresolved / next**
1. The user still has to apply the config edit in §4. Nothing else unblocks them.
2. `bonding_plan_config.json` (§7) - separate decision.
3. `transfer_log` for the bonding stage remains undeclared; `remaining` will have
   no consumption subtracted even after the fix. Product decision.
4. A UI surface for the dry-run (the `config_resolve_report` three-population
   frame, registering transfer_plan as its second `_RESOLVERS` slice) was ranked
   #3 in the previous report and is still unbuilt.

**Proposed memory entries for `agent_workspace/memory/server-pm.md`**
- 함정: 같은 사실(테이블의 좌표·값 컬럼)이 config 파일 셋에 따로 적혀 있으면, 한 곳을
  고쳐도 나머지가 남고 오타는 반드시 **가장 늦게 읽히는 사본**에 남는다.
  올바른 방법: 새 config에 좌표/값 컬럼을 요구하기 전에
  `map_overlay.resolve_binding_info`가 이미 그 답을 갖고 있는지 본다. 선언은 관례를
  벗어난 곳에만 두고 나머지는 유도한다(중복 선언은 유도 경로가 아직 사는지를 가린다 -
  `map_overlay_config.__derived_note`의 규칙).
- 함정: 「빠진 값을 채워주는」 유도를 **선택 역할까지** 확장하면 부재가 정보인 자리
  (`transfer_log`의 x/y 부재 = count_only, canonical frame 후보 제외)를 조용히 뒤집어
  숫자를 바꾼다.
  올바른 방법: 유도는 **required 역할의 부재만** 메운다. 부재가 거절이 되는 자리에서만
  채우고, 부재가 상태인 자리는 건드리지 않는다.
- 함정: 「명시 선언이 유도를 이긴다」를 넣으면, 철자가 틀린 선언은 유도가 있어도 계속
  이겨서 수리 방법이 *고치기*가 아니라 *지우기*가 된다. 그 말을 안 하면 운영자는
  「유도가 있다는데 왜 안 되나」에서 멈춘다.
  올바른 방법: 거절 문장과 dry-run 양쪽이 "이 선언을 지우면 무엇이 유도되는지"를 함께
  말하게 한다(`deletion_hints`).
