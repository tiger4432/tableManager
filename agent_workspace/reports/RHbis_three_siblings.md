# R-H-bis — the three siblings, landed

Scope kept: `server/ledger/**` and `server/tests/test_ledger*` only. Six files changed,
listed at the end. Nothing committed, nothing staged, nothing stashed. No file belonging
to the map-alignment lane or the `client2` lane was opened.

---

## 0. WHERE YOUR THREE-ITEM SUMMARY DISAGREES WITH THE RULING (read first)

**Two corrections and one nuance. Item 2 was exactly right.**

### ⚠️ Correction A — item 3 was not a duplication. There was one call site, in the wrong place.

You wrote: *"Scope-opening is duplicated per call site and must be hoisted into the shared
backfill driver."*

The ruling says something different:

> **스코프 상속의 구조화 — 여는 책임을 공유 드라이버로 올린다.** 두 번째 번역기가 규율을
> «발견해야만» 물려받는 구조는 규율이 아니라 구전이다. 분자를 도는 공유 루프(backfill
> 드라이버)가 `building_molecule`을 열면 번역기는 구조적으로 그 안에서 태어난다.

That is a **relocation of responsibility**, not a de-duplication. Measured, before and
after, over `server/ledger/**`:

| | `with gate.building_molecule(` in production code |
|---|---|
| before (`git show HEAD`) | **1** — `lot_event_translator.py:285`, inside `translate` |
| after (working tree) | **1** — `backfill.py:252`, inside the molecule loop |

The count did not fall. It moved. There never were "old copies left in place" to find,
so the "a hoist that leaves the old copies is not a hoist" test cannot be applied here;
the applicable test is *does the translator still open one*, and the answer is no — proven
by a test that goes red if it does (§3 below).

### ⚠️ Correction B — "how many callers go through the shared driver" is **one**, and the ruling knew that.

You asked me to say so plainly rather than report "landed":

- Translator classes in the ledger package: **1** (`LotEventTranslator`,
  `server/ledger/lot_event_translator.py:188`).
- Callers of `backfill.run`: the CLI `main()` in `backfill.py`, plus 7 call sites in
  `server/tests/test_ledger_l1_pg.py`. **No production daemon calls it yet.**

So the hoist is wired to exactly one translator. **That is the ruling's stated intent, not
a shortfall** — the whole sentence is about the translator that does not exist yet ("두
번째 번역기가... 구조적으로 그 안에서 태어난다"). But it does mean item 3 buys no behaviour
change today; its entire value is the RuntimeError a future second translator's author
will hit instead of silently getting counted-but-not-aborted refusals. I would not call it
"landed" without that sentence attached.

### ◽ Nuance on item 1 — your diagnosis is right, your stated reason is not the ruling's.

You wrote the defect as *"returning an empty list makes a refusal indistinguishable from
'nothing matched'"*. True, and it is why the two had to stop being spelled alike. But the
ruling's stated reason is narrower and sharper:

> 합침이 무시할 수 있는 신호는 방금 사형된 그 모양이고, 신호 문법이 둘이면 미래 호출자가
> 틀린 쪽을 고른다.

i.e. **a signal a merge can ignore** (the shape `f313279` just executed) and **two
signalling grammars in one module**. This matters practically: it means only the *refusal*
return converts to an exception. The **`[]` for "this molecule legitimately had nothing to
say" stays a return** — the gate's own comment says counting it would make the refusal
counter mean two things, and the ruling does not disturb that. A repair that made
`screen_molecule` raise on both would have been over-applying it. I kept the silence path
and pinned it with a test.

### One thing worth knowing that neither of us said

These three are not loose observations — they are enumerated verbatim in the technical
spec as **"⚠️ 의도적으로 남긴 모양 셋"** (`docs/spec/LEDGER_TECHNICAL_SPEC.md`, the block
beginning "⚠️ 의도적으로 남긴 모양 셋"), in your exact order: ① `screen_molecule`'s `[]`
② `write_batch(reasons=None)` ③ the second translator having to open the scope. R-H-bis
retires all three, so that block is now false and must be rewritten. See §5 — I did not
edit it, it is outside my scope.

---

## 1. `screen_molecule` — the refusal leaves as an exception

**What the ruling said:**

> **`screen_molecule`의 `[]` 거절 신호 — 예외 형태로 통일한다.** 합침이 무시할 수 있는
> 신호는 방금 사형된 그 모양이고, 신호 문법이 둘이면 미래 호출자가 틀린 쪽을 고른다.
> 스코프 안 `gate.refuse` 경유로 전환 — 세지 않고 잃는 데이터 손실 경로를 지금 닫는다.

**What I changed** (`server/ledger/gate.py`). The refusal arm went from a direct `_record`
plus `return [], report` to the established `f313279` pattern — out through `refuse`,
which counts first and raises second:

```python
    if report["refused"]:
        refuse(source, report["reason"],
               f"molecule={molecule_ref} :: " + " ; ".join(report["violations"][:3]),
               atoms=len(atoms), rows=source_rows)
        return [], report
```

This is deliberately the same shape `f313279` used and not a second one: `refuse` counts
unconditionally and raises **only when `molecule_is_open()`**, so the `return` below it is
still reached by a caller who never opened a scope. That fall-through is the double net,
not a second contract.

The driver (`backfill.py`) now calls `screen_molecule` **inside** the molecule scope, which
is what makes the raise fire at all, and its `refused = screen_report["refused"]` check is
gone — the exception is the only signal now.

**Evidence, with the anti-patterns addressed:**

- ✅ **Not an injection-harness entry.** You warned that both shared harnesses in
  `test_ledger_l1_unit.py` treat `AssertionError` as success. A guard whose claim is "an
  exception is raised" cannot be stated there, so these are plain tests using
  `pytest.raises(gate.MoleculeRefused)` — which distinguishes the right exception from the
  wrong one. I did **not** add them to `INJECTIONS` / `EXPECTED_INJECTIONS`; I proved
  redness by injection-and-measure instead (below), which is what that list is a proxy for.
- ✅ **No assertion after the raising call.** Every claim about the refusal is made on
  `caught.value` **after** the `with pytest.raises(...)` block. Inside the block there is
  only one statement after the call — `reached_the_line_after_the_call.extend(kept or [])`,
  the swallow itself — and the test asserts (outside) that the list is empty, i.e. that the
  line never ran. That is an observable, not an assertion the harness could eat.
- ✅ **Measured red, unit level.** Reverting only the `refuse(...)` call back to
  `_record(...)`: `1 failed, 98 passed`, failing with
  `Failed: DID NOT RAISE <class 'ledger.gate.MoleculeRefused'>`. No other test moved.
- ✅ **Measured red at the DRIVER, against PostgreSQL.** This is the one that matters,
  because the unit test would pass even if the driver never opened a scope. With the old
  return-form re-injected,
  `test_a_subject_type_the_source_never_declared_is_refused_by_the_REAL_backfill`
  (which drives a **gate-level** refusal through `backfill.run`) fails with:

  ```
  E  AssertionError: both molecules of the fixture mention wafers, so both must be refused whole
  E  assert 0 == 2
  ```

  `refused_molecules == 0` while the gate had counted 2 — the caller loses the molecule
  **without counting it**, which is precisely the path the ruling's last clause names
  ("세지 않고 잃는 데이터 손실 경로") and the direction that drives `refusals_unaccounted`
  negative. Restored: green.

New tests (`server/tests/test_ledger_l1_unit.py`):
`test_a_gate_refusal_inside_a_molecule_scope_UNWINDS_rather_than_returning`,
`test_a_refusal_and_a_silence_are_no_longer_SPELLED_alike` (the other arm — pins that the
"nothing to say" `[]` survives and is still uncounted),
`test_outside_a_molecule_scope_the_gate_still_refuses_by_RETURNING` (the double net).

---

## 2. `write_batch(reasons=None)` — the default is gone

**What the ruling said:**

> **`write_batch(reasons=None)` — 기본값을 없앤다.** 아무 말 안 하면 옛 동작이 유지되는
> 기본값은 R-D가 사형한 미끼 필드의 함수 인자판이다. count가 있는 쓰기는 이름을 가져와야
> 하고, 정당한 빈 내역은 깨끗한 실행의 «명시적» 빈 dict뿐이다. 「이력의 옷을 입은 장부
> 결함」이라는 진단 그대로 — 부호 계약(>0 = 배포 이력)의 신뢰가 여기 걸려 있다.

**What I changed** (`server/ledger/store.py`) — three parts, because removing the default
alone would not have done it:

1. `def write_batch(..., refused=0, incomplete=0, *, reasons)` — **keyword-only**, not
   merely undefaulted. It sits behind two integer parameters that do have defaults, so
   positionally it is one miscount away from being handed `incomplete`.
2. **An explicit `None` is rejected too**, `raise TypeError(_REASONS_REQUIRED)`, before the
   connection is opened. Without this the ruling would have been satisfied on paper and
   defeated by one keystroke: the body read `_json(dict(reasons or {}))`, so
   `reasons=None` would have reinstated the decoy exactly. That line is now
   `_json(dict(reasons))`.
3. The same treatment on `_advance_cursor`, which is the statement that actually writes
   `molecules_refused`. **This is an extension beyond the ruling's literal text** (it names
   `write_batch`) — I judged it in-scope because the ruling's reason is "count가 있는 쓰기는
   이름을 가져와야 한다" and this is that write, and because leaving the private door open
   would let a future caller bypass the public one. Flagging it so you can veto it; it is
   two lines.

**Evidence, with the anti-pattern addressed:**

- ✅ **Proven by calling it WITHOUT `reasons`, not by a green suite.** You were right that
  green proves nothing: grep shows `write_batch` has **exactly one** caller in the whole
  tree (`backfill.py:_flush`) and it already passes `reasons=delta`, plus **zero** test
  callers before today. The default could have come back and nothing would have noticed.
  `test_a_write_that_FORGETS_reasons_fails_loudly_and_writes_nothing` calls it the way a
  caller who forgot would, and separately with an explicit `None`.
- ✅ **Measured red.** Restoring `reasons=None` and deleting the body check:
  `2 failed, 83 passed`. The signature test fails `assert None is <class 'inspect._empty'>`.
  The call test fails with
  `AttributeError: 'NoneType' object has no attribute 'raw_connection'` at
  `server\ledger\store.py:80` — which is the interesting one: it proves that with the
  default back, the forgetful call **proceeds into opening a connection and committing**.
  The test's own docstring predicts that exact failure ("An `AttributeError` here would
  mean the check runs too late"), and `engine=None` is what turns it into evidence that
  nothing is written.
- ✅ Live write path still exercised: 27 PG tests drive `backfill.run` → `_flush` →
  `write_batch(..., reasons=delta)` against `assy_qa`, green.

---

## 3. Scope-opening hoisted to the shared driver

**What the ruling said:**

> **스코프 상속의 구조화 — 여는 책임을 공유 드라이버로 올린다.** [...] 분자를 도는 공유
> 루프(backfill 드라이버)가 `building_molecule`을 열면 번역기는 구조적으로 그 안에서
> 태어난다. `_build`의 스코프 단언은 이중 그물로 유지.

**What I changed:**

- `lot_event_translator.translate` no longer opens the scope. Its `try` / `except
  gate.MoleculeRefused` stays — that is `f313279`'s one-way door and the ruling does not
  touch it.
- `backfill.run`'s molecule loop holds the `with gate.building_molecule(source)`, wrapping
  **both** `translator.translate(...)` and `gate.screen_molecule(...)`, with an
  `except gate.MoleculeRefused` that sets `refused = True` and gives back the molecule's
  register memos.
- `_build`'s `molecule_is_open()` assertion **kept**, per the ruling's last sentence. Its
  message was wrong after the move (it said "Call translate()."), so it now names who opens
  the scope and shows the two-line spelling a hand-driving caller needs.

**Counts, as requested:**

| | production (`server/ledger/**`) | tests (`server/tests/test_ledger*`) |
|---|---|---|
| before | 1 (`lot_event_translator.py`) | 0 |
| after | 1 (`backfill.py`) | 8 |

Test count rose 0 → 8 because the tests are now the drivers: `translate_one` was reshaped
to mirror `backfill.run`'s loop exactly (open scope, translate, screen inside it, catch),
and four other places that drive a translator by hand now open the scope themselves.
Callers actually going through the shared driver: **one** — see Correction B.

**Evidence:**

- ✅ **Measured red.** Restoring `with gate.building_molecule(SOURCE):` inside `translate`:
  `1 failed, 98 passed`, failing `Failed: DID NOT RAISE <class 'RuntimeError'>`.
- ✅ **Both arms in one test.** A guard that only ever refuses is indistinguishable from one
  that refuses everything, so
  `test_a_translator_run_without_the_DRIVERS_scope_refuses_to_run_at_all` runs the *same*
  molecule twice: without a scope it must `RuntimeError`, inside one it must produce atoms.
  The `RuntimeError` assertions are on `str(caught.value)` **after** the `pytest.raises`
  block.
- ✅ The message is asserted to name `backfill.run`, not just to exist — otherwise the next
  author has to go reading to find out who owns the scope.

---

## 4. Test runs

Only the suites that import what I touched. `grep` confirms exactly three test files import
the `ledger` package; `test_ledger_trace*.py` and `test_ingestion_ledger_tier1.py` do not,
and I did not touch `ledger_trace.py`.

```
test_ledger_l1_unit.py + test_ledger_trace_contract.py + test_ledger_l1_pg.py
  -> 126 passed, 6 warnings in 25.24s
```

PG suite ran against **`assy_qa`** via `ASSY_PG_TEST_DATABASE_URL`. Its harness refuses
`assy_manager` by name (`_resolve_url`), re-checks through `db_safety.check_test_database`,
and builds everything — including the `lot_event` source fixture — inside scratch schema
`assy_ledger_l1_pytest`, dropped at teardown, with `public` off the search path. **No write
of any kind reached `assy_manager`; no throwaway database was created, so none was left
behind.** All injections were applied and reverted with the Edit tool (not a rewriting
script), and the final `git diff --stat` shows only the six intended files.

Net new tests: **6**. No new test file.

---

## 5. Handoff — living docs I did NOT touch (outside the stated scope)

Per `docs/process/DOC_OWNERSHIP.md` the ledger row's update trigger ① is "`server/ledger/*`
의 모듈 계약·불변식 변경", which is exactly this round. These are owned by doc-keeper with
Backend review, and `LEDGER_RULINGS.md` is ontology-pm's. Predicates, not line numbers, so
they survive the other lanes' edits:

- **`docs/spec/LEDGER_TECHNICAL_SPEC.md`** — the block "⚠️ **의도적으로 남긴 모양 셋**" is
  now false in all three items and should be replaced by a statement of what R-H-bis did.
  Also the sentence "`screen_molecule`은 거절 시 여전히 `[]`를 돌려준다" and the row
  describing `gate.building_molecule(source)` (which does not yet say the driver opens it).
- **`docs/guide/LEDGER_GUIDE.md`** — the `gate.py` and `lot_event_translator.py` rows in the
  module map. The translator row currently says `_build` runs inside `gate.building_molecule`
  without saying who opens it, and reads as if the translator does.
- **`docs/process/LEDGER_RULINGS.md`** — R-H-bis has no closing mark. Suggested content for
  it is §§1-3 above; I did not write it, since the rulings file is the canonical record and
  ontology-pm's.

## 6. Proposed lesson for `agent_workspace/memory/server-pm.md` (not added — proposal only)

> **함정**: 「예외가 던져진다」는 주장을 주입 하네스 항목으로 낸다. 이 저장소의 공유 하네스
> 둘은 `AssertionError`를 성공으로 읽으므로, **틀린 예외가 던져져도 초록**이다. 그리고
> `pytest.raises` 블록 «안»에서 호출 뒤에 쓴 단언은 한 번도 실행되지 않는다.
> **올바른 방법**: 예외 주장은 `pytest.raises(<정확한 타입>)`으로 쓰고, 예외에 대한 단언은
> 전부 블록 «밖»에서 `caught.value`에 대고 한다. 블록 안에 남기는 것은 하네스가 삼킬 수
> 없는 **관측물**(그 줄이 실행됐는지 알려주는 리스트)뿐이다.

## 7. Files changed

```
server/ledger/backfill.py                  |  46 +++--
server/ledger/gate.py                      |  62 ++++--
server/ledger/lot_event_translator.py      |  26 +++-
server/ledger/store.py                     |  42 ++++-
server/tests/test_ledger_l1_unit.py        | 195 +++++++++++++++++--
server/tests/test_ledger_trace_contract.py |   6 +-
```
