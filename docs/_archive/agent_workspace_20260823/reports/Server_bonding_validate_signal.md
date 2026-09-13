# Server — QA B1 fix: the validate verdict names what it did not subtract

Round: HIGH finding from `agent_workspace/reports/QA_server_n7_bonding_review.md` §2 B1.
Commit: `101311f` (on `main`, **not pushed**). Held commit `2c2a777` is unblocked by this.
Agent: server-pm · 2026-08-04

---

## 1. What changed

`server/transfer_plan.py` — `validate_plan` only. Three edits, all additive:

| Where | Change |
|---|---|
| `:3186` (next to `truncations = []`) | `inactive_subtractions = []` accumulator |
| `:3326` (immediately after `available = int(...)`) | union-append of `summary.get("inactive_subtractions")`, dedup, first-seen order |
| `:3433` (return) | `return {...}` → `out = {...}` + `if inactive_subtractions: out["inactive_subtractions"] = ...` |

Plus the module docstring (`:86-89`) and the `validate_plan` docstring, which now state that the
field rides on **every** response that serves an availability number — slot summary, `scope=lot`
summary, M1 `core-summary`, and `validate`.

**Collection point is deliberate.** The union is taken *after* the `remaining_reliable` gate, not
inside `_get_summary`. A source skipped as 판정 불가 contributed no number to any verdict, so its
inactive kinds are not claimed as the basis of one. The list describes exactly "the numbers this
verdict rests on".

**Not done, per the ruling:** no new warning type (a warning would flip `status` from `ok` to
`warnings`), no change to `remaining_reliable`, no second reliability axis, no rename of any
shipped status. Verdict string stays `ok`.

---

## 2. Before / after payload (measured, not asserted)

Both dumped from the live route through the FastAPI test client, same plan on both sides:
one DOE `A`, `stack=1`, material `TAPE-X_01`, 5 cells painted → required 5.
Fixture availability: gross **8**, fully-subtracted net **2**.

"Before" was produced by disabling the emission line (`if False and inactive_subtractions:`) and
re-running the identical dump; "after" with it restored. Keys sorted for comparability.

### Relaxed config (`transfer_log` / `origin_log` / `fail_sources` / `process_history` keys deleted)

BEFORE
```json
{"availability_checked": true, "doe_count": 1, "map_key": "BASE-RELAXED",
 "map_status": "connected", "painted_values": {"A": 5},
 "ref_table": "tp_test_bonding_map", "stage": "bonding", "status": "ok", "warnings": []}
```

AFTER
```json
{"availability_checked": true, "doe_count": 1,
 "inactive_subtractions": ["transfer_log", "origin_log", "fail_sources"],
 "map_key": "BASE-RELAXED", "map_status": "connected", "painted_values": {"A": 5},
 "ref_table": "tp_test_bonding_map", "stage": "bonding", "status": "ok", "warnings": []}
```

This is B1's exact scenario: `5 <= 8` on a number with **zero** subtractions applied, `status: "ok"`,
zero warnings. The verdict is unchanged by design; what changed is that the response now says the
`ok` was computed without those three terms.

### Fully declared config (same plan, same seed)

BEFORE and AFTER are the same bytes:
```json
{"availability_checked": true, "doe_count": 1, "map_key": "BASE-DECLARED",
 "map_status": "connected", "painted_values": {"A": 5},
 "ref_table": "tp_test_bonding_map", "stage": "bonding", "status": "warnings",
 "warnings": [{"available": 2, "demand": "A[MID]@TAPE-X_01",
               "detail": "DOE 'A[MID]@TAPE-X_01' 수량 부족: 필요 5 > 소스(TAPE-X,01) 가용 2",
               "required": 5, "type": "qty_shortage", "value": "A"},
              {"...": "source_fail_chips"}, {"...": "source_history_fail"}]}
```

**Byte-identity evidence.** `diff` over the two dump lines reports exactly one differing line
(the relaxed one). The declared line hashes identically across before/after:

```
diff before.txt after.txt   → 1c1  (only the RELAXED line)
md5 of DECLARED line before → 70bec1b8cc0886f6dafe0d13254e33e9
md5 of DECLARED line after  → 70bec1b8cc0886f6dafe0d13254e33e9
```

Note the contrast the two payloads make: the identical plan is `qty_shortage 5 > 2` on the declared
config and a bare `ok` on the relaxed one. That is the relaxation working as the user asked, and it
is why the marker had to exist.

---

## 3. New tests — `server/tests/test_availability_relaxation.py`

The gap QA named was that **no test touched `validate` on a relaxed config at all**. Three added:

1. `test_validate_names_the_inactive_subtractions_behind_its_verdict` — relaxed path: asserts
   `status == "ok"`, `warnings == []`, and `inactive_subtractions == ["transfer_log", "origin_log",
   "fail_sources"]`. This is the marker's **presence** assertion.
2. `test_validate_verdict_on_a_declared_config_is_byte_identical` — declared path: asserts
   `"inactive_subtractions" not in body` **and** `set(body) == VALIDATE_DECLARED_KEYS` (the frozen
   9-key shape), so a new field can never appear on the declared path unnoticed. Also re-pins the
   pre-existing judgement (`required 5`, `available 2`, `status: "warnings"`).
3. `test_validate_omits_the_marker_when_the_gross_number_never_judged` — mixed config (two log roles
   absent, `fail_sources.defect` declared-but-broken): the source is unjudgeable, so
   `availability_unreliable` fires and the field is absent even though the underlying summary
   carries inactive kinds. Pins the collection point.

**Defect injection (per the standing rule that a test must be shown to execute the new line).**
With the emission disabled, `pytest -k validate` → `1 failed, 2 passed`; the failure is test #1.
Restored → all pass. The axis is live, not decorative.

---

## 4. Suite

```
cd server && conda run -n assy_manager python -m pytest tests/ -q
1862 passed, 2 skipped, 92 warnings in 335.40s (0:05:35)
```
Exit 0. `grep -cE "^(FAILED|ERROR)"` over full captured stdout → **0**.
Baseline was `1859 passed, 2 skipped`; delta is exactly the 3 new tests. No live pytest at start
(checked `Win32_Process`); the 5-process decoupled server was up, which is normal.

⚠️ Environment note for the next lane: a *failing* pytest under `conda run` crashes conda itself with
`UnicodeEncodeError: 'cp949'` while printing Korean assertion text, and the real result is lost.
Prefix `PYTHONIOENCODING=utf-8` or you will misread a red suite as a broken toolchain.

---

## 5. Doc edits

Owned pair per `docs/process/DOC_OWNERSHIP.md:77` (note: QA cited `docs/architecture/DOC_OWNERSHIP.md`,
which does not exist — the file is under `docs/process/`):

- **`docs/spec/MAP_EDITOR_SPEC.md` §6.2-ter (new)** — the three-state table (`not_declared` /
  `missing` / `untracked`), the `total_chips` exemption, why `transferred` is null while `remaining`
  is a number, `inactive_subtractions` on all four surfaces including `validate`, and the explicit
  statement that `status` and `remaining_reliable` are unchanged.
- **`docs/guide/CONFIG_GUIDE.md` §3-S6 (`:246`)** — the status dictionary. `not_declared` added ahead
  of `missing`, and `missing` re-worded to "**선언은 있는데** 바인딩이 깨짐". This was the sentence
  QA flagged as false.

Stale statements the relaxation falsified, found by predicate rather than by list:

- **`CONFIG_GUIDE` §5.8 (~`:493`)** — new relaxation block: three-state table, the
  `inactive_subtractions` contract, the "`validate` keeps `ok`" rule, and the collision note.
- **`CONFIG_GUIDE` §5.8-ter (`:524`→`:538`)** — "미선언 테이블을 가리키는 바인딩" now scoped to a
  *present* binding, with an explicit warning that an absent key is a different state.
- **`CONFIG_GUIDE` §6 trap I (`:635`→`:649`)** — "role이 빠지거나 테이블이 없으면 `missing`" split:
  a broken table/column is `missing`; an absent auxiliary role is `not_declared` and serves a number.
- **`MAP_EDITOR_SPEC` §6.2-bis (`:1014`)** — 🔴 **this one was not on anyone's list.** It said JSON
  `null` · **키 삭제** · `"None"` are "전부 종전 그대로 `missing`". Key deletion is exactly what the
  relaxation changed, so the 7c contract's own bullet had become false. Corrected in place with a
  pointer to §6.2-ter and a one-line statement of how the two declarations differ (`"none"` = "we
  don't track it → upper bound only"; key absent = "no such table → count without that term").

History: `docs/history/20260804_071048_absence_is_a_declaration_and_the_verdict_must_say_what_it_did_not_subtract.md`
covers **both** `2c2a777` and this follow-up (the relaxation had no entry at all), index regenerated
(`301 entries`). `docs/process/PROJECT_STATUS.md` untouched.

---

## 6. Ruling on the `not_declared` name collision

`CONFIG_GUIDE.md:338` (now `:355`) already carries `not_declared` as a `config_resolve_report`
**reason**: 「효과에 필요한 선언이 없다」.

**Ruling: they mean the same thing, and I did not rename either.** The predicate is identical —
*the declaration required for this effect is absent, so the effect is inactive*. What differs is the
**axis**, not the meaning:

| | §4.2-bis | §5.8 / §6.2-ter |
|---|---|---|
| Kind | a *reason* under the `ineffective` population | a *role status* |
| Payload slot | `domains[].ineffective[].reason` | `sources.<role>` |
| Consequence | that declaration's effect is off | that subtraction term is off |

Renaming a shipped status to dodge a collision that isn't semantic would cost every consumer a
migration for no gain, and the two tokens can never appear in the same payload position. The hazard
QA named is real but is a *reader* hazard, so I fixed it as one: both sections now carry an explicit
cross-reference saying the two are the same predicate on different axes and **cannot substitute for
each other** — don't look up a §5.8 status in the §4.2-bis table.

**For the Lead PM:** flagging rather than deciding unilaterally, as instructed. If you want them
disambiguated by name instead, the cheaper side to rename is the `config_resolve_report` reason (one
domain registered, `enrichment`, and the field is a diagnostic string) — but I recommend against it.

---

## 7. Out of scope, untouched (board items)

Both belong to `5be96f5` (N7), not to this round, and were left alone as instructed:
- N1 — payload/SQL spelling divergence for |v| < 1e-4 (`5.5e-5` → SQL `'5.5e-05'`, grid `0.000055`).
- N2 — the same crash class still live for a `datetime` expose column (`_text_part`,
  `virtual_join_executor.py:351`).

Also unresolved and **not** mine to close: QA B2 — `inactive_subtractions` still has no reader in
`client2/`. A client lane appears to be live on it (`agent_workspace/reports/Client_availability_marker.md`
and `client2/tests/availability_gross_marker_harness.mjs` appeared in the working tree during this
round). The server half is now complete on every surface; whether the operator *sees* the qualifier
is that lane's call. Suggest a contract vector so the two halves are scored against one expectation
rather than against each other's prose.

QA B3 (a present-but-garbage `fail_sources` reported as "not declared", `transfer_plan.py:1444` —
the only site using truthiness-and-shape instead of `role_is_declared`) was LOW and out of this
round's scope. It is a one-line fix and I did not take it without a ruling; worth a board line.

---

## 8. Proposed memory entry (for Lead PM review — not self-added)

- **함정**: 새 신뢰도 필드를 「요약 응답」에만 달면, 그 수치로 **판정을 내리는 라우트**는 그 필드를
  모른 채 숫자만 읽는다 — 그리고 판정 라우트가 정확히 사고가 나는 자리다.
  **올바른 방법**: 신뢰도 축(또는 그 마커)을 하나 늘렸으면 **그 값을 소비해 판정을 내는 모든 라우트를
  열거**해 각각에서 채점한다. 열거의 기준은 "그 필드를 읽는 곳"이 아니라 **"그 숫자를 읽는 곳"**이다.

---

## Handoff

- **Changed**: `server/transfer_plan.py` (validate marker), `server/tests/test_availability_relaxation.py`
  (+3 tests), `docs/spec/MAP_EDITOR_SPEC.md` (§6.2-ter new, §6.2-bis corrected),
  `docs/guide/CONFIG_GUIDE.md` (4 spots), 1 history entry + index. Commit `101311f`, **not pushed**.
- **Verified**: full suite `1862 passed, 2 skipped`, 0 failed; defect injection proves the new test
  executes the new line; byte-identity of the declared payload proven by md5, not by argument.
- **Unresolved**: B2 (client reader), B3 (LOW, `fail_sources` shape predicate), the `not_declared`
  collision ruling awaits your acknowledgement, N1/N2 board items.
- **Next**: push gate is yours. A doc-keeper cycle is also pending (27 commits since last sweep —
  hook notice fired during this round; `.claude/doc_sync_pending` still present).
