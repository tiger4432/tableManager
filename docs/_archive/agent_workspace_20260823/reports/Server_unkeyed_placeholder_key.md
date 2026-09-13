# LANE UNKEYED (narrowed) — a blank business key column never stores `''`

**Domain:** Server · **Tier:** T2 · **Date:** 2026-08-07 · **Status:** implemented, NOT committed
**All numbers below are from this workstation against a local PostgreSQL — a simulation, not production.**

---

## 0. What the narrowing changed

The product owner ruled the placeholder out: keyless rows arise only from manual grid
work, never from ingestion, so making a row recognisable to a *later ingestion* is value
nobody collects. **`UNKEYED_KEY_PREFIX`, `mint_unkeyed_business_key`,
`is_unkeyed_business_key`, `_ensure_row_business_key` and all three mint call sites are
removed.** No second mechanism replaced them. A keyless row keeps NULL, which is what it
already got and what the grid already handles by `row_id`.

What survives is one branch in `_update_row_business_key` and the reason it exists.

🔴 **The narrowing surfaced a defect in my own first draft, and it was worse than the bug
it replaced.** Details in §3 — it is the most important thing in this report.

---

## 1. The `''` path reproduces, asserted first

Probe against a real PostgreSQL database (`assy_unk_6f856759`, created and dropped by the
probe — never the dev DB), with `uq_bk_<table>` installed on both scratch tables, which is
the shape production will have after the migration. Old `''` behaviour injected back into
`crud.py` byte-for-byte.

**A. Five rows whose key column arrives blank, pushed 3×:**

```
push 1 REFUSED: IntegrityError   after push 1: {'total': 0, 'nulls': 0}
push 2 REFUSED: IntegrityError   after push 2: {'total': 0, 'nulls': 0}
push 3 REFUSED: IntegrityError   after push 3: {'total': 0, 'nulls': 0}
batches refused: 3/3
```

with `🔴 [BK Conflict Unresolved] ... attempts: 3` on each. **0 rows written, three pushes
running.** This is not a duplicate-row problem — it is a collision problem. The five `''`
rows collide **with each other inside one transaction**, and the `IntegrityError` recovery
cannot resolve it: its recovery is "roll back, re-read in a new snapshot, resolve onto the
row the winner committed", and none of the colliding rows was ever committed, so the replay
reproduces the identical collision.

**C. And it is not only keyless rows — a MAP RE-PUSH is refused too.** This is new since my
first report and it widens the case for the guard:

```
after push 1: {'total': 4, 'distinct_keys': 4}     # keys M3_0..M3_3, fine
push 2 REFUSED: IntegrityError                     # DETAIL: (business_key_val)=() already exists
push 3 REFUSED: IntegrityError
```

A map CSV carries its key column **present and blank** (`test_set_based_write_path._item`).
On re-push the rows resolve by their assembled key, `_update_row_business_key` then wrote
`''` over the live key of *every* row, and two of them collided. So under the old code plus
the index, **the second push of any unchanged map is refused**. "Ingestion does not produce
keyless rows" is true and still leaves this standing.

---

## 2. The change

One branch, `server/database/crud.py:1745-1810` (`_update_row_business_key`):

```python
str_val = str(raw).strip()
if str_val == "":
    # Blank -> write nothing. Never `''` (a shared identity that collides), and
    # never a clear (it destroys a map row's key on re-push). See the docstring.
    return
```

**A blank value writes nothing at all.** A new row keeps the NULL it was created with; a
row that already has a key keeps that key.

**Why NULL is the right resting state** (and why I did not need to pick anything else):
PostgreSQL treats NULLs as distinct under a plain UNIQUE index — which is exactly why the
migration does **not** use `NULLS NOT DISTINCT` — so any number of keyless rows coexist. It
is also the shape a keyless row already has everywhere else: `create_empty_rows_batch`
writes it, the grid addresses such rows by `row_id`, and the live database holds them today.

---

## 3. 🔴 My first draft was `blank → set NULL`, and it was wrong

I wrote the obvious fix — clear the field to NULL — and the PostgreSQL probe caught it.
Measured with that draft in place:

```
=== C. map payload (key column present and blank) ===
after push 1: {'total': 4, 'nulls': 0, 'distinct_keys': 4}
after push 2: {'total': 4, 'nulls': 4, 'distinct_keys': 0}    # every key destroyed
after push 3: {'total': 8, 'nulls': 4, 'distinct_keys': 4}    # 4 MORE rows
```

The key column of a map table is **derived** (`map_pk` from `map_id`+`die_no`). Blank there
means "the file did not supply it", not "this row has no key". On a re-push of an unchanged
map the composite recomputation is **skipped** (`is_src_changed` is False, the row is not
new), so nothing puts the key back.

**The old `''` code did the identical destruction** — and got away with it only because
`''` collided on the way out, so the batch was refused and the damage never committed. A
bug masking a bug. My draft removed the collision and left the destruction, converting a
loud refusal into **silent key loss followed by duplication**. That is strictly worse than
what I set out to fix, and it would have shipped had I not run the map case three times.

The lesson is in §7. `test_a_map_payload_survives_an_unchanged_re_push` pins it, and its
docstring records that **a single-push version of that test passes against the bug** —
push 1 assembles the key after the blank is processed, so only the loop catches it.

**Consequence, stated rather than buried:** blanking a displayed key cell now leaves
`business_key_val` stale instead of destroying it. That is the deliberate trade — a
stale-but-unique handle is recoverable by typing a new key, whereas dropping the identity
of a live row orphans everything keyed to it (`FrameConfirmation.unit_key`,
`GraphNode.identity_key`) and `''` additionally collides.

---

## 4. Verification, post-change

Same probe, same isolated database, UNIQUE index live:

| | result |
|---|---|
| A. 5 blank-key rows × 3 pushes | 5 → 10 → 15 rows, **0 empty strings, 15 NULLs, 0 batches refused** |
| B. 3 pre-existing NULL-keyed rows + an unrelated write | all 3 present, all still NULL |
| C. unchanged 4-row map × 3 pushes | **4 → 4 → 4**, keys `M3_0..M3_3` intact, no duplication |
| D. final census | 0 empty strings, 0 duplicate non-null keys, both tables |

**On the 11 existing NULL rows.** I did not touch the dev DB. I ran a **read-only** census
against the isolated `assy_qa` snapshot (37 tables carrying the column, 52,770 rows):
**0 empty strings, 0 NULLs**, and `wafer_map_metadata` holds **677 rows** — which is exactly
your *before* number. So the snapshot predates the manual merges you measured; it
corroborates your baseline rather than contradicting your 677→684 / 0→11. Two independent
confirmations that those rows are safe: the change contains **no statement that writes on a
blank key value** (the branch returns), and probe section B demonstrates NULL-keyed rows
surviving an unrelated write in the same table.

### Tests — written, pytest NOT run

`server/tests/test_blank_business_key_is_null.py`, **10 tests** (renamed from the
placeholder module, which is deleted). Table prefix `blankkey_test_*` so it cannot collide
with the user's gitignored `table_config.json`.

I verified the alarms ring against **two** mutations, both injected as bytes so CRLF is
preserved and the restore is sha256-verified:

| | current | old `''` injected | my clear-to-NULL draft injected |
|---|---|---|---|
| | **10 pass, 0 fail** | **4 pass, 6 fail** | **8 pass, 2 fail** |

The 4 that pass against the old code say so in their own docstrings and are not offered as
evidence: two controls (a complete composite key is unaffected; `create_empty_rows_batch`
still writes NULL), one noting the composite path already wrote NULL, and one standing
guard that the withdrawn placeholder stays withdrawn. The two that fire against the draft
are the two that matter — no key destruction, and the map re-push.

### Coupled edits, all four you listed

1. **Tests.** The 14 placeholder tests are **deleted**, not adapted. Nothing survives that
   passes for a reason it no longer states. The two consequential edits to
   `test_composite_business_key.py` and `test_composite_key_prefetch_budget.py` are
   **reverted to `is None`** (correct again), with a comment on each saying why `None` and
   not `''` is load-bearing. Both modules re-run: **12 passed, 2 failed, 1 skipped** — the
   same two as before the narrowing (see §5).
2. **Migration comment block** rewritten. The `UNKEYED::<row_id>` sentence is gone; the
   0-rows-written measurement, the reason the recovery cannot help, and the "one file stops
   that table's ingestion" consequence are all kept, plus your 11/10 NULL figures and the
   ruling that produced the narrowing.
3. **`data_model.md §3.1-bis`** rewritten and retitled — «빈 문자열이 아니라 **NULL**을
   받는다». It now records the ruling and carries a 🔴 line telling a future reader that if
   they want a synthetic identity here, the first question is who reads it.
4. **`test_set_based_write_path.py` docstring** re-checked and still true — it says the row
   is created with no `business_key_val` at all, which is exactly what "write nothing"
   produces. The stale `_ensure_row_business_key` reference is replaced with
   `_update_row_business_key`.

---

## 5. Open items

1. **⚠️ `test_composite_key_prefetch_budget::test_inserting_new_rows_still_probes_once_per_row`
   fails in my harness and is NOT mine.** Expects 201 selects; my harness measures 1. I
   measured it **with the old behaviour injected and got the same 1**, so neither the
   original lane nor the narrowing moved it. My harness is not pytest and does not get
   conftest's fixtures — per the lesson about instruments, this is a measurement problem
   until proven otherwise. Your serialized run is the authority; flagging only so it is not
   attributed here. (`test_composite_business_key_ingestion` is a pure harness artifact —
   my runner supplies no `monkeypatch`.)

2. **Pre-existing, newly visible, and worth its own lane:** a re-pushed map now blanks the
   derived key **column** (`map_pk` reads NULL after push 2) while `business_key_val` stays
   correct. That is the ordinary cell loop writing the payload's blank cell — independent
   of this branch, and invisible before only because the old code refused the batch first.
   My test asserts `business_key_val` and explicitly does **not** pin `map_pk`, with the
   reason in its docstring.

3. **Still recommended before the index ships** (unchanged from the first report):
   `crud.py:~2960` documents that a non-composite table whose key arrives as a plain
   payload value with no `business_key_val` on the item is never matched — every push
   creates a fresh row. Reproduced: 20 → 25 → 30 across three pushes of 5 real distinct
   keys. With the index that becomes the same unresolvable refusal as §1.

4. The `test_set_based_write_path.py` docstring edit is in another lane's untracked file —
   you approved it; re-checked and correct after the narrowing.

---

## 6. Files changed

| File | Change |
|---|---|
| `server/database/crud.py` | **+62/−16.** One branch in `_update_row_business_key`. No new public symbols. |
| `server/tests/test_blank_business_key_is_null.py` | **new**, 10 tests |
| `server/tests/test_unkeyed_placeholder_key.py` | **deleted** (never committed) |
| `server/tests/test_composite_business_key.py` | reverted to `is None` + why-comment |
| `server/tests/test_composite_key_prefetch_budget.py` | reverted to `is None` + why-comment |
| `server/tests/test_set_based_write_path.py` | docstring only — another lane's untracked file |
| `server/migrations/add_business_key_unique_index.py` | comment block rewritten |
| `docs/architecture/data_model.md` | §3.1-bis rewritten |

Nothing committed, nothing staged, no `git add -a`/`-A`. Probe database dropped; remaining
`assy%` databases are `assy_manager` (14 GB) and `assy_qa` (642 MB), both pre-existing.

---

## 7. Proposed lessons for `agent_workspace/memory/server-pm.md` (do not add directly)

> **함정**: **버그가 버그를 가리고 있는데 앞의 버그만 고친다.** `''` 쓰기는 맵 재푸시 때
> 살아 있는 키를 **파괴**하고 있었는데, 파괴 직후 `''`끼리 충돌해 배치가 거절되는 바람에
> 손상이 커밋된 적이 없었다. 내 1차 수정(`공백 → NULL로 클리어`)은 **충돌만 없애고 파괴는
> 남겨서**, 시끄러운 거절을 **조용한 키 소실 + 중복 생성**으로 바꿨다(실측: 무변경 맵
> 2회차 push에서 4행 전부 키 NULL, 3회차에 4행 추가 생성). 고치기 전보다 나빴다.
> **올바른 방법**: 실패를 없애는 수정을 할 때는 **그 실패가 무엇을 막고 있었는지 먼저
> 물어라.** 거절·예외·롤백은 손상의 원인이 아니라 **손상의 브레이크**일 수 있다. 그리고
> 파생 컬럼이 「비어서 왔다」는 것은 「값이 없다」가 아니라 **「파일이 안 실어 왔다」**다.

> **함정**: **1회 실행으로는 안 잡히는 결함에 1회짜리 픽스처를 쓴다.** 위 파괴는 push 1에서
> 안 보인다 — 공백 처리 **뒤에** 복합 키가 조립되기 때문이다. 2회차부터 조립이 스킵되면서
> 드러난다.
> **올바른 방법**: **멱등성·재적재 경로는 최소 3회 반복해서 재고, 매 회차마다 단언한다.**
> 「1회 push 후 상태가 맞다」는 업서트 경로에서 아무것도 증명하지 않는다.
