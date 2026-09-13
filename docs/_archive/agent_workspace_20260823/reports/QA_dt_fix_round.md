# QA-DT — adversarial review of the DT/CORE alignment-scorer fix round (T1)

**Scope reviewed:** the staged tree only —
`server/map_alignment.py` (+291), `server/scripts/seed_dt_index_walk.py` (+29),
`server/tests/test_index_group_count.py`, `server/tests/test_bin_fingerprint_shift.py`,
`server/tests/test_dt_index_walk_core_axis.py` (all new).
Lane report: `agent_workspace/reports/Server_dt_fix_round.md`.

**No pytest was started** (a sibling lane owns the suite). All test/mutation numbers below
come from a pytest-free runner I wrote
(`…/scratchpad/QADT_runner.py`) that imports the three files, expands the
`parametrize` marks and the one module-scoped `bench` fixture by hand, and mutates
`server/map_alignment.py` in binary with CRLF-normalised anchors. **The file was restored
byte-identically and `git diff` on all five staged paths is empty after the run.**

⚠️ **This box is a simulation.** Every number below is a measurement of
`localhost:5432/assy_manager` and of synthetic fixtures. None of it is a claim about
production.

---

## 1. Verdict

## **GO-WITH-FIXES**

The one wired change (`direction_violations` moving onto `_walk_by_index`) is **correct and
an improvement**: I reproduced the old nondeterminism, confirmed the new order is genuinely
a property of the map, and found no input where the two orderings differ while indices are
unique. The mutation table reproduces **exactly**, digit for digit.

The fixes are to the *justifications*, not to the wired code:
- **F1's support floor is inert against the failure it is named for** at any realistic map
  size — measured on this box's own core bin map (finding D1). This must be settled
  **before** the wiring round, not after.
- The lane's blast-radius argument rests on "`dt_index` verified unique in the DB", and
  raw uniqueness is **not** the predicate that matters — `int()` truncation of a
  `double precision` column can manufacture duplicates (D2). The fix is unaffected; the
  argument was thinner than stated.
- The `_residual_shift` defect the lane surfaced **reproduces exactly as described** (D3),
  and is unreachable on this box but reachable at production wafer sizes.

---

## 2. The wired call site — attacked, and it holds

### 2.1 The anchor in the brief is off by 88 lines

`direction_violations` is **not** called at `server/map_alignment.py:3079` (that line is
prose inside the `_residual` REVERTED comment block). The live call is:

```
server/map_alignment.py:3167-3168
        c["index_violations"], c["index_steps"] = direction_violations(
            c["_phys"], cell_owner, idx_k, idx_has, _judge)
```

It is the **only** wired caller (`grep` over the repo including the gitignored operator
areas `server/config/*.json`, `server/mappers/`, `server/ingestion_workspace/`).

### 2.2 "`(k,y,x,i)` and `(k,i)` sort identically when `k` separates every pair" — TRUE

Not merely true for these fixtures. Lexicographic tuple comparison decides at position 0
whenever position 0 differs, so the claim is a property of the comparison, not of the value
ranges. Confirmed empirically anyway — **4,000 randomised trials**, 1–12 cells, 1–3 maps,
`dt_index` drawn from −50..50 including zero and negatives, mixed `idx_has`, random
coordinates including negatives: **0 divergences** between the pre-fix and post-fix
orderings (`…/scratchpad/QADT_order.py`, section A).

### 2.3 The OLD behaviour really was nondeterministic — this is not one answer swapped for another

The source rows are read with **no `ORDER BY`**:

```
server/map_alignment.py:4999
        rows = db.query(*q_cols).filter(*mfilters).limit(cell_cap + 1).all()
```

so array position is PostgreSQL's choice (heap order, and it moves after UPDATE/VACUUM).
Exhaustively permuting a 4-cell map that carries one duplicate index
(`…/scratchpad/QADT_order2.py`):

| fixture | OLD `direction_violations` over all 24 row orders | NEW |
| --- | --- | --- |
| duplicate index on two different rows | **`{(1,3), (3,3)}` — two answers** | `{(3,3)}` |
| duplicate index on the same row, different x | **`{(1,3), (2,3)}` — two answers** | `{(1,3)}` |

The new order is genuinely a property of the map: cells that tie on `(k, y, x)` are
*coordinate-identical*, so the loop reads the same `phys[ia]` either way and the residual
`i` tiebreak cannot change any output. Verified (`QADT_order.py`, section D).

### 2.4 Where the lane's argument is thin — see D2

---

## 3. Mutation table — re-run, and it reproduces exactly

Baseline and all seven of the lane's mutants land on the **same numbers the lane reported**:

```
                                                        MINE          LANE REPORTED
BASELINE (unmutated)                              39 passed,  0     39 passed
M1 drop the per-map `groups += 1`                 29 passed, 10     10 failed, 29 passed
M2 count equal y as a boundary                    25 passed, 14     14 failed, 25 passed
M3 read x instead of y                            28 passed, 11     11 failed, 28 passed
M4 remove the sort by index                       35 passed,  4      4 failed, 35 passed
M5 seat cap truncates instead of refusing         38 passed,  1      1 failed, 38 passed
M6 drop the minimum-support floor                 37 passed,  2      2 failed, 37 passed
M7 drop the positional tiebreak                   36 passed,  3      3 failed, 36 passed
```

**No anchor rot**: every mutation text matched exactly once in the current file (I grep the
mutation TEXT, not the call shape; the three that initially reported 0 occurrences were my
own CRLF bug, corrected).

I added five mutants of my own, targeting the specific claims this round makes. **All five
die**, which answers item 4 of the brief directly:

```
M8  [QA] BINFP_SEAT_CAP re-merged: = RESIDUAL_SEAT_CAP        37 passed,  2 failed   KILLED
M9  [QA] the support floor moved AFTER the uniqueness check    37 passed,  2 failed   KILLED
M10 [QA] seat-cap refusal reports `seat_cap`, not `len(seats)` 38 passed,  1 failed   KILLED
M11 [QA] BINFP_NO_SEAT de-aliased (the one that must STAY)     37 passed,  2 failed   KILLED
M12 [QA] _walk_by_index sorts (k,x,y) instead of (k,y,x)       38 passed,  1 failed   KILLED
```

M8 is the re-merge the brief asked about: `test_the_seat_cap_reason_is_not_the_residual_search_s_spelling`
**and** `test_every_refusal_carries_a_zero_pair` both go red. The pin is real, and the
alias-direction is pinned too (M11) — someone "cleaning up" the remaining aliases also goes
red.

---

## 4. Confirmed defects

### D1 · [심각도 **높음** — 배선 전 판정 필요] The minimum-support floor of 3 does not defend against the failure it names

`server/map_alignment.py:1671-1678` (`_BINFP_MIN_SUPPORT = 3`) and `:1793-1798`.

The constant's own comment names the failure it exists for: *"기준 맵이 엉뚱한 리비전으로
풀렸을 때 실제로 도달하는 자리"* — the reference resolving to the wrong wafer revision.
Measured against this box's **actual** core bin map, that defence does not exist:

```
core_wafer_map: 24,200 rows, distinct c_bn = 2      ('1' x 22,234 ; '0' x 1,966)
one wafer (CL-2601-008 / slot 21): 121 dies, histogram [('1',109), ('0',12)]

source scored against a WRONG-REVISION reference (labels reshuffled, same geometry):
   n=34   ->  (dx,dy)=(5,2)  matched=28   seats=12   reason=None
   n=121  ->  (dx,dy)=(1,3)  matched=70   seats=12   reason=None
```

**Failure scenario.** The reference resolves to the wrong wafer revision. With two bin
labels the coincidental match rate is ~58%, so the winning translation is held up by
**70 of 121 dies** — 23x the floor. `reason is None`, which the docstring defines as
*"the translation was determined"*, and the map lands wherever the noise peaked.
On `QA_MAP` (1,281 cells) the same arithmetic gives ~750 coincidental matches.

The floor of 3 fires only on sources so small that the top match count is 1 or 2 — i.e.
exactly and only on QA-1's 40-die toy fixture. **The lane's stated reason for choosing an
absolute floor over a proportional one ("a ratio floor refuses first on the partial maps
this function exists for") is correct about ratio floors and does not rescue the absolute
one: an absolute floor of 3 also protects only tiny maps, and it protects them by refusing,
which is the same objection.** On `PART-R270` (34 dies) 3/34 ≈ 9%; on `QA_MAP` 3/1281 ≈
0.23%. The floor's strength varies by a factor of 38 across the fixtures in this tree, in
the direction that makes it weakest where the source is largest.

**Recommendation (not applied — review only).** Do not settle this as "absolute vs ratio".
The measurement says the discriminator is not support at all but **margin**: the gap between
the best seat and the runner-up. With 2 labels there is no such gap. Options for the lead
PM, in the order I'd rank them:
1. Make the wiring round carry `matched` and `seats_considered` to the operator screen and
   gate on the **margin** (top − second) rather than on `top`, or
2. Refuse when the reference's label cardinality is too low to be a fingerprint at all
   (2 labels is a pass/fail map, not a fingerprint — the docstring's premise
   *"`c_bn` values vary die to die across the wafer"* is **false on this box's data**), or
3. Keep the floor as a floor, but state in the comment that it defends only against
   degenerate-size sources, so the wiring round does not read it as revision protection.

⚠️ **This cannot break anything running.** `bin_fingerprint_shift` has zero callers
(re-verified by grep, including the gitignored operator areas). It is a **blocker for the
wiring round**, not for this commit.

### D2 · [심각도 중] "verified unique in the DB" is not the predicate the blast-radius argument needs

`server/map_alignment.py:1410-1415` (`_normalised_indices`), `:1507` (`_walk_by_index`).

`dt_index` is `double precision` in **both** `dt_log` and `dt_map` (measured from
`information_schema`). `_normalised_indices` does `int(k)` — a **truncation** — before
anything sees the value. So two *distinct* `dt_index` values can arrive at the walk as the
*same* `k`:

```
raw dt_index [1.0, 2.0, 2.5, 3.0]  ->  idx_k [1, 2, 2, 3]      (2.0 and 2.5 collapse)
OLD violations across the 24 row orders: {(1,3), (3,3)}   <- nondeterministic
NEW violations across the 24 row orders: {(3,3)}
```

The lane's claim — *"maps that carry duplicate `dt_index` values within a single map …
Verified unique across all six seeded jobs in the live DB"* — checks **raw** uniqueness.
The predicate that decides whether the two orderings diverge is uniqueness **after
truncation**, which is strictly weaker. I re-ran both:

```
duplicate raw dt_index within a job, all 126 jobs   : 0
duplicate trunc(dt_index) within a job, all 126 jobs: 0
non-integer dt_index rows in dt_log                 : 0
```

so the conclusion happens to hold on this box — but it holds for a reason the lane did not
check, and the column type permits the counterexample at any time.

**Also worth the lead PM's attention:** of the **126** `dt_job` values in `dt_log`, **120
carry `dt_index` NULL on every row**. Only the six `SYN-IDX-*` synthetic jobs carry indices
at all. So "verified across all six seeded jobs" is verified across 100% of the jobs that
exercise this axis on this box, and 0% of the DT-EQP data that looks like production.
The index axis is dormant outside the fixtures here.

**Recommendation:** none for this diff — the fix makes the divergence unreachable either
way. State the predicate correctly in the report/history (uniqueness *after* `int()`), and
if `dt_index` is ever meant to be integral, that belongs as a declaration, not an
assumption.

### D3 · [심각도 중 — 확인만, 수리하지 않음] `_residual_shift` loses the "I did not see them all" fact — CONFIRMED, exactly as the lane described

Comment: `server/map_alignment.py:1024-1028` — *"넘치면 그때까지 최선을 쓰되 **사유를
이름으로 낸다**… 조용히 포기하면 「앵커가 옳았다」와 「다 못 봤다」가 화면에서 같아진다."*
Code: `capped` is set at `:1137` and read **only** inside `if best is None:` at `:1165-1166`.
When the cap is hit *after* a qualifying seat was found, control falls through to `:1171`.

Reproduced (`…/scratchpad/QADT_resid2.py`; `_RESIDUAL_SEAT_CAP` overridden **in memory
only**, the file was not touched):

```
cap=1000  -> (0,0) hit=3  state=anchor_seat_held  scanned=61 of 62 candidate seats
cap=5     -> (0,0) hit=3  state=anchor_seat_held  scanned= 6 of 62 candidate seats
```

**Failure scenario.** A partial DT map whose anchor claim is true. The residual search finds
its one qualifying seat immediately, then hits the cap 4,090 seats later. The operator sees
`anchor_seat_held` — *"the anchor was right"* — with no way to know that 99% of the seats
were never scanned and one of them may also have qualified (which would have produced
`RESIDUAL_NOT_UNIQUE`, a refusal). The capped run and the honest run are byte-identical on
screen; `seats_scanned` does not separate them, because it is also small on an honest early
exit.

**Reachability, measured.** `seats` is the reference cell list, so
`tried <= len(reference cells) + 1`. The largest reference floor on this box:

```
('QA','MAP') 1281 | ('CORE','YINV') 927 | ('CORE','1X') 854 | ('5N','BASE') 425
('TEST','TEST') 425 | ('QA','MAP2') 337 | ('PRD-A','DT13') 88
largest = 1281  ->  max seats scanned 1282  ->  cap 4096 reachable? NO
```

**So on this box it is unreachable and purely theoretical.** In production it is not
exotic: a 300 mm wafer floor with more than 4,095 valid dies is ordinary, and the cap was
presumably chosen with such a floor in mind.

**Priority, my recommendation: LOW-MEDIUM, and it is a diagnostics defect, not a placement
defect.** `_residual_shift`'s answer is currently **not applied** —
`server/map_alignment.py:3081-3084` sets `_residual["applied"] = False` and uses the
anchor's seat. So the lost fact corrupts only what the operator reads, which is exactly the
harm the comment at `:1024-1028` describes, and nothing else. The one-line shape of the fix
is visible (carry `capped` into the `:1171` branch, or add a `capped` boolean to `obs`), but
**I did not apply it, per the brief.**

### D4 · [심각도 낮] The new order is a property of the map only while the map is not truncated

`server/map_alignment.py:4999` applies `.limit(cell_cap + 1)` with **no `ORDER BY`**. For a
map above `cell_cap`, PostgreSQL is free to return a *different subset* on two runs, not
just a different order. `_walk_by_index` makes the walk deterministic given the cells; it
cannot make the cells deterministic. The docstring's *"the same map answers the same way
when the query returns its rows in another order"* is therefore true up to `cell_cap` and
false above it. Pre-existing, out of scope, worth a line in the docstring or a board item.

### D5 · [심각도 낮] `bin_fingerprint_shift`'s seat cap still *defaults* to the residual constant

`server/map_alignment.py:1682` — `seat_cap: int = _RESIDUAL_SEAT_CAP`. The round split the
two *names* on the argument that the two caps are different events with different contracts;
the default **value** is still borrowed from the other event's tuning. On this box the
borrowed 4096 is far above any reachable seat count (the rarest label on a real wafer has
**12** seats), so the cap never fires in practice and its refusal path is exercised only by
the test's explicit `seat_cap=` argument. Cosmetic today; name it `_BINFP_SEAT_CAP` when the
wiring round sources it from config, or the split is half-done.

---

## 5. Hypotheses I tried to break and could not

| hypothesis | why it is safe (1 line) |
| --- | --- |
| Duplicate `k` **across different maps** diverges | `_walk_by_index` groups by `cell_owner` first (`:1506`); cross-map duplicates never share a list. Fuzzed with 1–3 owners, 0 divergences. |
| Equal `k` **and** equal `(y,x)` leaves array-order dependence | Those cells are coordinate-identical, so `phys[ia]` is the same object-value either way; both outputs identical (`QADT_order.py` D). |
| Negative / zero / large `dt_index` breaks the equivalence | Tuple comparison is lexicographic regardless of sign or magnitude; 4,000 trials over −50..50, 0 divergences. |
| NULL `dt_index` reaches `int(idx_k[i])` | `_normalised_indices:1411-1415` maps `None`/`TypeError`/`ValueError` to `raw=None` and `flags=False`; `_walk_by_index:1505` reads only `idx_has[i]` cells. |
| F2's `(0,0)`-on-refusal contract is broken on some path | All six refusal returns verified by reading every `return` in the function — `:1736 :1745 :1747 :1765 :1771 :1798 :1804` — every one is `0, 0, …`. M10 shows the seat-count reporting is pinned too. |
| The reason-name split has a live consumer branching on the old shared string | Repo-wide grep for `seat_cap_reached` / `RESIDUAL_SEAT_CAP` / `BINFP_`, including `client2/`, `server/config/*.json`, `server/mappers/`, `server/ingestion_workspace/`: **zero** consumers outside `server/map_alignment.py` and `server/tests/`. Nothing branches on it yet. |
| A single re-binned die kills the anchor and hides the truth | It does not: a label absent from the reference gets `1 << 30` in `_seat_cost:1755-1758` and sorts **last**, so the next-rarest die becomes the anchor and the translation still resolves — measured `(2,1,36,28,None)` clean vs `(2,1,35,28,None)` re-binned. The anchor rule is more robust than I expected. |
| The seed jobs were not actually applied / are not idempotent | Live DB confirms the six jobs, `SYN-IDX` rows total **432** = 88+88+34+85+88+49 exactly as reported; `dt_index` is `1..n` and `count(dt_index) == count(distinct dt_index)` on **all six**; the two new jobs are 88+49 = **137 new rows**, and 137 x 16 = **2192**, matching the reported changed-cell count arithmetic exactly. |

---

## 6. Runtime verification still needed

1. **The full suite has never run against the current tree.** The lane's run was 38 tests;
   the tree has 39 (the seat-cap split test), and `server/database/crud.py` was being
   rewritten by another lane *during* that run. My 39-test result is from my own runner, not
   pytest — it does not exercise conftest, fixtures scoping, or collection. **The serialized
   clean run is still owed.**
2. **The three reported failures** (`test_composite_key_prefetch_budget`,
   `test_join_resolved_columns::test_S8b…`, `test_launcher_arguments`) — I could not
   re-measure them without pytest. The lane's attribution to the `crud.py` lane is
   plausible from the assertion text but is **not cleared by me**.
3. **D1 at production label cardinality.** My measurement says 2 labels on this box's
   `core_wafer_map`. If production `c_bn` has 8–16 bins the arithmetic changes and the
   fingerprint premise may hold. **That number has to come from production before the
   wiring round picks a threshold.** Do not carry my `2` forward.
4. **D3's reachability in production** — whether any real `valid_die_ref` floor exceeds
   4,095 dies. On this box the answer is no (max 1,281).

---

## 7. Documentation

**The lane's §8 claim checks out, and I re-derived it independently rather than trusting the
follow-ups list.** Searching `docs/process/DOC_OWNERSHIP.md` by changed code path:
`server/map_alignment.py` appears only in the **좌표계 확정 기록** row (line 93) as a
pointer (*"채점·판정(층 ⑤⑥⑦)은 `server/map_alignment.py`"*), and that row's living
documents are `architecture/data_model §4-bis` and `spec/MAP_ALIGNMENT_SPEC §9.7` — the
symbols it names (`confirmed_meta_for`, `parse_frame`) are untouched by this diff.

I also went one step further than the lane and grepped the living documents for the axis
itself:

```
grep "direction_violations|index_group_count|순번|walk order|dt_index"
     docs/spec/MAP_ALIGNMENT_SPEC.md docs/architecture/data_model.md docs/architecture/backend.md
  -> zero hits
```

So: **nothing is stale, and that is because a wired scoring axis (`direction_violations`,
live at `:3167`) is documented nowhere at all.** That is a pre-existing gap, not this
round's, and it is the row the wiring round must create. Recording it here so it is not
rediscovered.

**One correction to the lane's own prose, for the historian:** the draft history entry says
*"38 committed tests where there were none"*. The tree carries **39**. Same class of error
as the suite-count footnote the lane already flagged — worth fixing before it is committed,
since the count is the second copy of the list.

---

## 8. Proposed lessons (for the lead PM to place, not added by me)

For `agent_workspace/memory/qa-reviewer.md`:

> - **함정**: **「DB에서 유일함을 확인했다」를 그대로 안전 근거로 받는다.** 코드가 보는 값은
>   DB의 값이 아니라 **정규화를 한 번 통과한 값**이다 — `dt_index`는 `double precision`이고
>   `_normalised_indices`가 `int()`로 자르므로, 원본이 유일해도 잘린 뒤에는 중복이 될 수
>   있다. 이번엔 결론이 우연히 맞았다.
>   **올바른 방법**: 유일성·범위·부호 같은 술어는 **그 술어를 실제로 읽는 코드 지점의 값**에
>   먹여서 재검증한다. 컬럼 타입을 먼저 본다.
>
> - **함정**: **바닥(threshold)이 「있다」를 「지킨다」로 읽는다.** 절대 바닥 3은 QA-1의
>   40다이 픽스처만 막고, 그 바닥이 이름으로 내건 실패(기준 리비전 오류)는 **실제 데이터
>   규모에서 23배 여유로 통과한다**.
>   **올바른 방법**: 문턱을 검수할 때는 **그 문턱이 막겠다고 선언한 실패를 실제 데이터
>   분포로 재현해 통과하는지** 잰다. 라벨 카디널리티처럼 문턱의 유효성을 결정하는 분포는
>   실측해서 보고서에 적는다.

---

*Probes (all under the session scratchpad, prefix `QADT_`): `QADT_db_probe.py`,
`QADT_order.py`, `QADT_order2.py`, `QADT_runner.py` (mutation sweep), `QADT_resid_seed.py`,
`QADT_resid2.py`, `QADT_final.py`. DB access was `SELECT` only — no writes, no DDL, no
reseed. `server/map_alignment.py` was mutated in place for the sweep and restored
byte-identically; `git diff` on all five staged paths is empty.*
