# Server — QA B3 fix: declaredness goes through the one predicate

Round: B3 ruling from Lead PM (2026-08-04), raised at the end of `101311f`.
Agent: server-pm · Commit: see §5 (on `main`, **not pushed**)

---

## 1. The defect

`server/transfer_plan.py:1447` (pre-fix) decided whether the site declared `fail_sources`
with a hand-rolled truthiness-and-shape test:

```python
fail_sources = source_cfg.get("fail_sources") or {}
if not (isinstance(fail_sources, dict) and fail_sources):
    inactive_subtractions.append("fail_sources")
```

`or {}` erases the difference between an absent key and a present `null`, and the
`isinstance`/truthy pair then rejects every other malformed shape as well. Result: state 2
(present-but-broken) collapsed into state 1 (absent) — a misconfigured site got the relaxed
treatment, and `inactive_subtractions` named a role the operator **had** declared.

Fixed by calling the shared predicate that already answers exactly this question:

```python
if not role_is_declared(source_cfg, "fail_sources"):
```

`role_is_declared` is `server/bonding_plan.py:94` — `isinstance(block, dict) and key in block`.

---

## 2. Call-site sweep — **1 hand-rolled site found, 1 fixed**

Swept every place in `server/` (excluding tests) that decides declaredness or emits
`STATUS_NOT_DECLARED` / `inactive_subtractions`:

| Site | Verdict |
|---|---|
| `transfer_plan.py:1447` `fail_sources` | 🔴 **hand-rolled — fixed this commit** |
| `transfer_plan.py:380` `_aux_role_status` | ✅ predicate |
| `transfer_plan.py:1351` `transfer_log` | ✅ predicate |
| `transfer_plan.py:1404` `origin_log` | ✅ predicate |
| `transfer_plan.py:1701` `process_history` | ✅ predicate |
| `bonding_plan.py:360` `defect`/`eds_fail`/`total_chips` | ✅ predicate |
| `bonding_plan.py:453` `used_chips` | ✅ predicate |
| `bonding_plan.py:486` `process_history` | ✅ predicate |
| `bonding_plan.py:552` M1 `inactive_subtractions` derivation | ✅ derived from statuses, which come from the predicate |

Non-sites checked and cleared (they iterate or resolve bindings, they do not classify
declaredness): `transfer_plan.py:414` (`_stage_role_statuses` fail loop), `:1186`
(`_canonical_origin_meta`), `:688` (M1 region adapter), `:1467` (the fail-source loop itself).

So the sweep count is **one**. Every sibling was already on the predicate; the defect was a
single second spelling, which is exactly the failure mode the one-predicate rule exists to
prevent.

---

## 3. 🔴 Red first — per malformed shape

New tests in `server/tests/test_availability_relaxation.py`:

* `test_malformed_fail_sources_is_declared_not_absent[...]` — parametrized over four
  PRESENT-but-malformed shapes, with **every other role left declared and working** so the
  container is the only variable.
* `test_validate_never_names_a_declared_role_as_inactive` — same defect carried to the verdict
  surface.

### Before the fix (RED) — all four shapes, all on the first assertion

```
FAILED ...::test_malformed_fail_sources_is_declared_not_absent[json_null]
FAILED ...::test_malformed_fail_sources_is_declared_not_absent[string_none]
FAILED ...::test_malformed_fail_sources_is_declared_not_absent[wrong_type_int]
FAILED ...::test_malformed_fail_sources_is_declared_not_absent[wrong_type_list]
FAILED ...::test_validate_never_names_a_declared_role_as_inactive
5 failed, 13 deselected
```

Each failure line (`--tb=line`):

```
assert 'fail_sources' not in ((['fail_sources']))
```

| Shape | config value | Pre-fix classification | Already correct? |
|---|---|---|---|
| `json_null` | `"fail_sources": null` | absent (wrong) | **no — was broken** |
| `string_none` | `"fail_sources": "None"` | absent (wrong) | **no — was broken** |
| `wrong_type_list` | `"fail_sources": ["defect"]` | absent (wrong) | **no — was broken** |
| `wrong_type_int` | `"fail_sources": 7` | absent (wrong) | **no — was broken** |

**No shape was already handled correctly.** All four reached the *first* assertion and failed
there, i.e. the red is on the marker itself and not on a downstream number.

### After the fix (GREEN)

```
tests/test_availability_relaxation.py  18 passed in 2.57s
```

The shapes now assert the full state-2 payload, which is the pre-relaxation one: no
`inactive_subtractions` field at all, `total 8`, `fail_breakdown {}`, `remaining 5`
(= 8 − used 3, the fail term simply never enters the arithmetic because no source resolves),
`remaining_reliable true`, `transferred 3`, and `transfer_log`/`origin_log` still `connected`.

### `inactive_subtractions` no longer lists a declared-but-broken role

`test_validate_never_names_a_declared_role_as_inactive` pins the verdict surface directly:
with `"fail_sources": null` and a plan requiring 5 against an available 5, `validate` returns
`availability_checked: true` and **no** `inactive_subtractions` key, and its key set is exactly
the frozen `VALIDATE_DECLARED_KEYS`. Pre-fix it returned `inactive_subtractions:
["fail_sources"]` — the list naming a source the operator declared, which is the lie the
ruling ordered removed.

The relaxed path is unaffected: `test_absent_declarations_serve_availability` and
`test_validate_names_the_inactive_subtractions_behind_its_verdict` still assert
`["transfer_log", "origin_log", "fail_sources"]` when the keys are genuinely deleted.

---

## 4. Two things the Lead PM should know (not fixed — no ruling)

1. **State 2 for `fail_sources` is silent, and always was.** For `transfer_log` / `origin_log`
   a broken declaration demotes to `missing` → `source_degraded` warning → `remaining` nulled.
   For a malformed `fail_sources` **container** there is no such demotion and never was: no
   source name exists to hang a status on, so pre-relaxation the engine just skipped it with
   no warning. "Demote exactly as before the relaxation" therefore resolves to *no demotion*,
   which is what this commit restores. The residual is that a site with `"fail_sources": null`
   now gets a gross-ish number with neither a marker nor a warning. Fixing that means adding a
   new demotion (`statuses["fail_sources"] = "missing"` → `EFFECT_REMAINING_OVERSTATED` →
   `remaining` nulled), which changes response payloads and is a second, unruled change. Raising
   it, not doing it.
2. **`"fail_sources": {}` (empty object) is now "declared".** The predicate is `key in block`,
   so an explicitly-empty container is a declaration of zero sources and gets no marker. This
   follows the one-predicate rule strictly and matches how `transfer_log: {}` would behave, but
   it is a shape an operator might reasonably write meaning "none" — same residual as (1).

---

## 5. Suite and scope

```
cd server && PYTHONIOENCODING=utf-8 conda run -n assy_manager python -m pytest tests/ -q -p no:warnings
1867 passed, 2 skipped in 315.08s (0:05:15)
```

Baseline was `1862 passed, 2 skipped`; +5 is exactly the new tests. Zero failures, zero errors.
Checked for a live pytest before running — only the 5-process decoupled server was up
(`run_decoupled_app.py`, uvicorn :8080, watcher, graph_sync, chain_worker, auto_update).

Files staged (explicit paths only, no `-a`/`-A`):

* `server/transfer_plan.py`
* `server/tests/test_availability_relaxation.py`

`docs/` untouched — the doc lanes are running concurrently. **No doc statement is falsified by
this fix**: `CONFIG_GUIDE.md:497/541` and `MAP_EDITOR_SPEC.md:1052` already describe the
boundary as **키 부재** (key absence) vs 깨진 선언, which is precisely what the code now
implements. The fix moved the code toward the docs, not away.

`client2/` untouched, no build run, nothing pushed.

---

## 6. Proposed lesson (server-pm memory — for Lead PM review)

> **함정**: 공용 술어가 있는데도 호출부에서 같은 판정을 **손으로 다시 쓴다**
> (`role_is_declared` 대신 `isinstance(x, dict) and x`). `or {}` 한 조각이 「키 부재」와
> 「present + null」을 같은 값으로 접어, 세 상태 설계가 두 상태로 무너진다 —
> 잘못 설정된 사이트가 완화(relaxed) 대우를 받고, 그 사실을 알리는 필드가 **선언된 역할을
> 미선언이라고 지목**한다.
> **올바른 방법**: 새 상태 술어를 도입할 때 그 술어의 **모든 호출부를 grep으로 세고**
> 두 번째 철자가 남지 않았는지 확인한다. 특히 `X = cfg.get(k) or {}` 뒤에 오는 판정은
> 이미 부재/널 구분을 잃은 뒤다.
