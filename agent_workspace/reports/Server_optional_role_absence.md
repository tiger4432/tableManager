# Server — board N14: a deleted optional `val` must not turn every row into FAIL

**Date:** 2026-08-04 · **Agent:** server-pm · **Board item:** N14 (push blocker)
**Source finding:** `agent_workspace/reports/QA_batch_gate_2026-08-04.md` §3 F5
**Files touched:** `server/transfer_plan.py`, `server/bonding_plan.py`,
`server/tests/test_optional_role_absence.py` (new),
`server/tests/test_transfer_plan_derivation.py`,
`server/config/transfer_plan_config.json.sample`,
`server/config/bonding_plan_config.json.sample`

---

## 1. Which of the two sides was the defect, and why

**The JUDGEMENT was the defect. The reliability flag was downstream of it and is
not touched directly.**

`fail_values` declares WHICH values mean fail. `val` declares WHERE to read that
value. With no `val` the predicate "is this row a fail" is **unanswerable** — and
unanswerable is not YES. Counting the pool with the predicate dropped does not
report "we could not tell"; it reports "all of them", which is a specific,
false, and maximally damaging answer.

Three reasons this side is the defect and not the flag:

1. **The system had already ruled on the identical arithmetic.** The
   declared-but-unresolvable spelling (`val: "typo"`) has been refused since
   2026-07-28 with the comment "counting without the fail filter would count
   EVERY row as fail — overstating the subtraction (breaks the upper-bound
   invariant)". Deleting the line produces byte-for-byte the same SQL as the
   typo produces. Two inputs, one arithmetic, one ruling. The deletion simply
   walked around a decision that had already been made.
2. **Fixing the flag would keep serving the wrong number.** `fail_breakdown.eds`
   would still read 144 on a pool where zero rows are fail. A wrong number with
   an honest caveat attached is the failure mode this batch spent its effort
   removing everywhere else — the response would say "144 chips failed, but do
   not trust the remaining", and 144 is not a measurement of anything.
3. **The upper-bound invariant only survives on this side.** Dropping a
   subtraction term can only RAISE the computed remaining, so `total − 0` is a
   genuine upper bound and is served as `remaining_upper_bound`. Keeping the 144
   subtraction breaks the bound downward — the served value would be *below* the
   truth, and the whole availability contract rests on the other direction.

Once the judgement refuses, the flag follows on its own with no separate change:
the refusal composes a status marker, `_status_is_degraded` recognises it,
`assess_degradation` classifies the role as `remaining_overstated`, and
`build_chips_block` nulls `remaining` and serves the bound. That chain already
existed — it was never reached because nothing demoted.

### The shape of the fix

One predicate, `bonding_plan.fail_filter_status(src_cfg, cols, status)`, owns the
ruling next to the resolver. It returns `(refused, status)` and distinguishes the
two shapes so the operator is told what to DO, not just that something is wrong:

| shape | marker | repair |
|---|---|---|
| `val` declared, column not on the table | `column_unresolved:val` (unchanged) | fix or delete the name |
| `val` not declared at all | `fail_value_column_absent` (new) | declare one |
| no `fail_values` at all | none — untouched | nothing; the table IS the fail list |

**Three readers call it**, which is the point of extracting it — a fix applied to
only the measured branch is how this class returns:

- `server/transfer_plan.py` self-frame `fail_sources` (the branch QA measured)
- `server/transfer_plan.py` `frame: "origin"` projection (a SET, so an absent
  predicate paints the *whole tape*, not just a count)
- `server/bonding_plan.py` `get_core_summary`'s `defect` / `eds_fail` /
  `total_chips` map roles (reached by every `source_config_ref: "bonding_plan"`
  stage, i.e. `dt`)

`compose_status_marker` was extracted from `_demote_for_unresolved` so the new
cause could not grow a second copy of the same `connected(...)` string surgery.

---

## 2. The 0 -> 144 red/green pair

### RED — measured against the pre-fix tree, before any edit

`server/tests/test_optional_role_absence.py::test_deleting_the_optional_val_does_not_fail_every_row`
(8-row scaled twin of the live 144):

```
AssertionError: a fail predicate with no column to read counted every row as FAIL:
{"total": 8, "fail_breakdown": {"eds": 8}, "transferred": null,
 "remaining": 0, "remaining_reliable": true}
assert 8 == 0
```

`remaining_reliable: true` is visible in the before, exactly as QA reported.

### RED at live scale — the real `dt_log`, read-only

The live config declares no `fail_sources`, so the two SQL statements the two
code paths issue were run directly against production (`SELECT count(*)`, no
writes, no DDL), lot `DT-2601-001` slot `22`:

```
   144  pool (the pre-fix fail count: no predicate)
     0  with the declared predicate c_bn IN ('F')
```

That is QA's 0 -> 144, reproduced on the real pool.

### GREEN — the same live pool through the fixed engine

Synthesised the `fail_sources.eds` declaration QA described (self frame,
`fail_values: ["F"]`) against live `dt_log`, read-only, both forms:

```
--- val DECLARED
  chips  : {"total":144,"fail_breakdown":{"eds":0},"transferred":null,
            "remaining":144,"remaining_reliable":true}
  sources: {"total_chips":"connected", "eds":"connected", ...}
  warnings: []

--- val DELETED
  chips  : {"total":144,"fail_breakdown":{"eds":0},"transferred":null,
            "remaining":null,"remaining_reliable":false,
            "remaining_upper_bound":144}
  sources: {"total_chips":"connected",
            "eds":"connected(fail_value_column_absent)", ...}
  warnings: [{"type":"source_degraded","role":"eds",
              "effect":"remaining_overstated"}]
```

### What an operator now sees

- **The number:** `fail_breakdown.eds` is `0`, not 144. `remaining` is `null`
  (never a fabricated 0), and the honest upper bound `144` is served under its
  own name, `remaining_upper_bound` — the client renders "<= 144", not a
  confident figure.
- **The flag:** `remaining_reliable: false`, plus a `source_degraded` warning
  naming role `eds`, status `connected(fail_value_column_absent)`, and effect
  `remaining_overstated`.
- **The dry-run row** (`GET /admin/transfer-plan/dry-run`, role
  `fail_sources.eds`):

```json
"val": {"column": null, "origin": "absent", "required": false,
        "derivable": false, "derived_from": null, "derived_role": null,
        "exists_on_table": null,
        "effect": "fail 값 필터(`fail_values`) ― 없으면 fail 판정을 내릴 수 없으므로
                   이 감산은 0으로 거절되고 소스가 강등됩니다
                   (fail_value_column_absent). `fail_values`를 선언했다면 이
                   역할은 사실상 필수입니다."}
```

Before this round that key did not exist in the report at all: the pre-deletion
report showed 5 columns, the post-deletion report showed 4, and no field said
which one had left. `counts.absent_optional_columns` gives the same fact as a
single number.

---

## 3. Byte-identity proof for a fully-declared config

`test_fully_declared_summary_is_byte_identical_to_the_prefix_behaviour` — the
same pattern `8817dde` used. The whole stage summary runs twice over identical
seeded data, once live and once with `bonding_plan.fail_filter_status` repointed
at the pre-fix rule (refuse only the declared-but-unresolvable spelling). Both
sides are md5'd over a sorted JSON dump:

```python
assert _md5(live) == _md5(without)
assert live["chips"]["total"] == ROWS      # not vacuous
```

**Mutation, executed.** Made the predicate over-broad by disabling its
"`val` is usable, nothing changes" early return — i.e. a fix that also refuses a
config which DOES declare a working `val`:

```
FAILED test_fully_declared_summary_is_byte_identical_to_the_prefix_behaviour
FAILED test_declared_val_counts_only_the_failing_rows
FAILED test_origin_frame_projection_refuses_the_same_deletion
FAILED test_m1_core_summary_refuses_the_same_deletion
4 failed, 9 passed
```

The byte-identity test goes red, as required. Mutation reverted; suite green
again (`13 passed`).

Additional evidence that nothing on the declared path moved: on the **live**
config as it exists on disk today, `dry_run` reports
`absent_optional_columns: 0` — no new rows appear, because every optional role
the live file uses is declared.

---

## 4. Sibling sweep

| optional role | absence today | verdict |
|---|---|---|
| `fail_sources.*` `val` (self frame) | counted the whole pool as fail, `reliable: true` | **DEFECT — fixed** |
| `fail_sources.*` `val` (frame `"origin"`) | projected the whole core onto the tape as fail | **DEFECT — fixed** (same predicate; a self-frame-only fix would have left it) |
| `bonding_plan` `defect`/`eds_fail`/`total_chips` `val` | counted the whole core as defect; reaches every `source_config_ref: "bonding_plan"` stage | **DEFECT — fixed** |
| `total_chips` `x`/`y` | `total_pts` stays `None`; `_region_block` serves `total: null` / `remaining: null`, `_bins_block` serves `status: unknown`, `reliable: false` and a reason sentence naming the missing coordinates | **NOT the same defect** — nothing claims a number it does not have. Behaviour unchanged; the absence is now named in the dry-run. Pinned by `test_absent_total_chips_coordinates_null_the_number_instead_of_moving_it` |
| `transfer_log` `x`/`y` | lands on `connected(count_only)`, which the degradation engine already reads -> `remaining_reliable: false` | **NOT the same defect.** Behaviour unchanged; named in the dry-run. Pinned by `test_absent_transfer_log_coordinates_already_demote` |
| `fail_sources.*` `x`/`y` | origin frame: `missing` + 0; self frame with `origin_log`: `connected(count_only)` | already honest; named in the dry-run |
| `process_history` `time` | no `ORDER BY` -> an arbitrary 50 rows instead of the most recent 50, and nothing says so | **weaker sibling, NOT fixed** (see §6). Semantics deliberately unchanged; now named in the dry-run |
| `process_history` `result` | `result_fail` warnings never fire | same class as `time`; named in the dry-run, semantics unchanged |
| `plan_store.registry` `bands` | legacy band blobs unreadable; already an intentional optional | named in the dry-run |

The catalogue is deliberately not a schema dump: only roles whose **absence
changes a computed number or a warning** are listed. Pure display fields
(`step`/`eqp`/`recipe`/`knobs`) are excluded, because listing everything would
bury the three lines that matter.

One noise defect found and fixed while building the catalogue: counting
`origin == "absent"` alone swept in **undeclared required roles** — 30 rows on
the live config against the 0 that are actually optional. The count predicate is
`origin == "absent" and required is False`. Absent-optional rows are also only
emitted for roles that HAVE a declaration, since "the operator deleted a line" is
only a meaningful question when there is a `columns` block to have deleted it
from.

---

## 5. Tests

New: `server/tests/test_optional_role_absence.py` — 13 tests
(prefix `optabs_test_`, cannot collide with a user's live config).

Changed: `server/tests/test_transfer_plan_derivation.py` — the exact-shape pin on
a dry-run column entry now includes `"effect": None`. Deliberately kept as an
exact-equality assertion so a future key addition has to be written down.

Suite: see §7.

---

## 6. Open / not done

1. **`process_history` `time` and `result`.** Their absence changes which rows
   and which warnings the operator sees, and nothing said so. The dry-run now
   names both. I did **not** change the semantics: `time` absence is a sampling
   defect, not a verdict inversion, and the honest repair (refuse, or degrade
   `process_history` to `history_incomplete` when unordered) is a behaviour
   change on a role classified `EFFECT_HISTORY_INCOMPLETE`. Boarding it rather
   than folding it into a push-blocker fix.
2. **`server/main.py`** (off-limits this round): the
   `GET /admin/transfer-plan/dry-run` route docstring enumerates what the report
   carries and does not yet mention the absent-optional rows or
   `counts.absent_optional_columns`. One paragraph, next time that file is open.
3. **Living docs** (off-limits this round). Per `DOC_OWNERSHIP.md` the rows for
   `server/transfer_plan.py` / `server/bonding_plan.py` should pick up: the new
   `connected(fail_value_column_absent)` status marker in the degradation
   vocabulary, and the dry-run's `columns[].effect` / `origin: "absent"` rows +
   `counts.absent_optional_columns`. `guide/CONFIG_GUIDE.md` and the repair guide
   rewritten by `ba65c59` should carry the one sentence now in both
   `.json.sample` `__comment`s: *deleting a declaration is the repair for a
   REQUIRED role only; an optional role is never derived back.*
4. **QA F8 still stands.** The named refusal reaches the operator only through
   the admin dry-run route, which no client fetches. The new absent rows inherit
   that limitation. The availability payload does carry the demotion (status +
   warning), so the number itself is safe today.
5. **Client status vocabulary.** `client2/src/transfer_plan.js`'s
   `__held_classifySourceStatus` folds any unrecognised `connected(...)` into
   `severity: ok` with no note — so `fail_value_column_absent` would render as
   fine there, exactly as `count_only` and `column_unresolved` already do. Those
   functions are `__held_` (dead, eslint-disabled) and the live path reads
   `remaining_reliable` and `remaining === null`, both of which this fix sets, so
   there is no client breakage. Pre-existing gap, not introduced here; boarding
   it for the Client PM rather than touching `client2/` this round.

---

## 7. Verification

- `conda run -n assy_manager python -m pytest tests/ -q` from `server/`, with
  `PYTHONIOENCODING=utf-8`. No pytest lane was live at start (checked
  `Get-CimInstance Win32_Process`; only the 5-process decoupled server).
  **Result: `2005 passed, 2 skipped` in 347.62s — baseline 1992 + the 13 new
  tests, zero failures.**
  *Note for the next runner:* `conda run` buffers the entire stream and writes it
  only on exit, so a redirected output file stays 0 bytes for the whole run.
  That is not a hang — poll the pytest PID, not the file.
- Scoped runs during development: `test_optional_role_absence.py` (13),
  `test_transfer_plan_derivation.py`, `test_transfer_plan.py`,
  `test_bonding_plan.py`, `test_availability_relaxation.py`,
  `test_transfer_untracked.py`, `test_binding_refusal.py`,
  `test_map_seam_contract.py` — 270 passed together.
- **Do NOT run `pytest` from `server/` without `tests/`**: it collects
  `scripts/archive/test_cte_search.py` and `test_work_mem.py`, which are
  DB-connecting scratch scripts and error out. Pre-existing, unrelated to this
  round.
- Live DB touched read-only only (`SELECT count(*)` and the availability engine's
  own SELECTs). No DDL, no writes, `server/config/*.json` untouched (only the
  two `.sample` files).

---

## 8. Proposed lesson for `agent_workspace/memory/server-pm.md`

*(proposal only — not added directly, per the operating rule)*

- **함정**: 「선언이 깨졌다」만 거절하고 「선언이 **없다**」는 안 거절한다. 둘은 같은
  산술을 만든다 — 오타 `val`과 지워진 `val`이 내는 SQL은 동일한데, 2026-07-28 픽스는
  `"val" in _unresolved_of(cols)`(= **선언됐는데** 미해석)만 봤다. 그래서 유도 라운드가
  「지우는 것이 수리다」를 가르치자 그 조언이 곧바로 결함 경로가 됐다.
  **올바른 방법**: 술어를 **쓸 수 있는가**로 쓰라(`"val" not in cols`), **어떻게 없는가**로
  쓰지 말라. 없는 방식(오타/삭제)은 *사유 이름*에서 구분하고, *판정*은 하나로 합친다.
- **함정**: 필수 역할의 수리법(지우기)을 선택 역할에 그대로 적용한다. 필수는 유도가
  메우고 선택은 **절대 메우지 않는다** — 한 줄 아래에서 조언이 파괴적으로 바뀐다.
  **올바른 방법**: 선택 역할의 **부재를 산출물에 행으로** 낸다. 빠진 줄은 보고서에서
  사라지므로, 없는 것을 세려면 없는 것에 이름을 먼저 줘야 한다.
- **함정**: `origin == "absent"`처럼 이미 쓰이던 값으로 새 카운트를 만든다. 라이브에서
  30 대 0이었다(미선언 **필수** 역할이 전부 딸려 왔다).
  **올바른 방법**: 새 카운트를 만들면 **라이브 config에 먹여 외연을 세어 본다** — 계급
  이름이 아니라 술어의 외연이 맞아야 한다.
