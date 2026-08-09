# QA-1 — adversarial review: `index_group_count` / `bin_fingerprint_shift`

**Scope:** the staged, uncommitted addition to `server/map_alignment.py` (+187 / −0, no
callers) and the claims made for it in
`agent_workspace/reports/Server_dt_to_core_transform.md`.
**Lens:** correctness of the two functions and of the measurements offered for them.
**Not in scope:** the adjudication itself (sibling lane).

---

## 1. Verdict

**GO-WITH-FIXES.**

Nothing is wired, so nothing can break today — that part of the lane's claim holds under
grep and under the suite. The two functions do what they say on the fixture, and the
central premise (group boundaries separate the true core frame) reproduced exactly, on
the real QA_MAP die set, from the live DB, under my own probes.

But two paths in `bin_fingerprint_shift` return a **confident, wrong translation** rather
than refusing (F1, F2), and both are reachable with realistic inputs. And the headline
`128/128` does not pin what it appears to pin: two mutations of `index_group_count`
survive it, and the truth set covers only 4 of the 8 candidate frames. F1 and F2 must
close before anything calls the fingerprint; F4/F6 must close before `128/128` is quoted
as a regression net.

---

## 2. Confirmed defects

### 🔴 [HIGH] F1 — `reason=None` ("determined") on a single-die match

`server/map_alignment.py:1709-1718` · docstring contract at `:1663-1665`

There is no minimum-support floor. `top` is the best hit count; the only rejections are
`top <= 0` (unreachable, see F8) and a non-unique maximum. A translation supported by
**one** die out of hundreds is returned with `reason is None`, which the docstring
defines as *"the translation was determined"*.

Measured (`…/scratchpad/QA1_attack.py`, H1): a 40-die source whose labels cannot match
the reference anywhere except a single rare-label die returns

```
(9, 9, 1, 1, None)          # dx=9 dy=9, matched=1 of 40, reason=None
```

**Failure scenario.** The reference core bin map resolves to the wrong wafer revision, or
to the right map under an unconfirmed frame — the lane's own §4 flags this prerequisite.
Exactly one die coincides by chance. The fingerprint reports a translation of `(9, 9)`
with `reason is None`; a caller written to the docstring accepts it and the whole map
lands a wafer-radius off, with no signal anywhere. This is the "빠르지만 가끔 조용히 안
맞음" case that core value #3 ranks below being slow.

**Recommend:** a `BINFP_LOW_SUPPORT` reason with a declared floor — absolute
(`matched >= N`) or proportional (`matched / len(labelled)`), config-driven per
`config-over-hardcode`. `matched` is already returned, so the fix is a threshold, not a
new measurement.

### 🔴 [HIGH] F2 — `BINFP_SEAT_CAP` returns a non-zero, wrong `(dx, dy)`, breaking its own contract

`server/map_alignment.py:1692` (`seats = sorted(seats)[:seat_cap]`) and `:1718`
(`return dx, dy, top, len(seats), (BINFP_SEAT_CAP if capped else None)`)

The docstring at `:1664` states: *"on any refusal `(dx, dy)` is `(0, 0)` and **that zero
is not a measurement** — read the reason, never the pair."* `BINFP_SEAT_CAP` is the one
reason that violates this. The seat list is truncated by `sorted()[:cap]` — i.e. by
ascending `(x, y)`, an arbitrary geometric corner — and the best of the *survivors* is
returned as a normal-looking pair.

Measured (`…/scratchpad/QA1_seatcap.py`), same input, cap varied:

```
uncapped   : (22, 22, 3, 4, None)                       <- the truth
seat_cap=3 : (-3, -3, 2, 3, 'seat_cap_reached')         <- wrong, non-zero, and plausible
```

**Failure scenario.** A bin map with few distinct labels over many dies pushes the rarest
label past 4096 seats (`_RESIDUAL_SEAT_CAP`, `:1028`). The true seat sits at high `(x, y)`
and is truncated away. A caller that treats `SEAT_CAP` as a *warning* (which is what the
name and the docstring's "stop after this many seats and SAY SO" both suggest) shifts the
map by whatever the truncated remainder liked best.

**Recommend:** on cap, refuse with `(0, 0)` like every other reason — the docstring's
contract is the right one and the code should meet it. If a capped answer must be usable,
it needs its own name and an explicit statement that the pair is provisional.

### [MEDIUM] F3 — duplicate `dt_index` makes the score depend on DB row order

`server/map_alignment.py:1606` — `lst.sort()` over tuples `(int(idx_k[i]), i)`

Ties on the index break on the **array position**. Measured (H4): the same map, the same
indices, rows presented in two orders → `groups = 2` vs `groups = 1`.

This is precisely the property the same commit declares unacceptable 46 lines later, for
the fingerprint anchor (`:1649`): *"array order is not a property of the map, so anchoring
on it would make the same input answer differently when the query returns rows in another
order."* The rule is stated for one function and violated by the other.

`direction_violations:1515` shares the pattern, so the convention is inherited — but the
exposure moved: group count is now the **primary** discriminator and violations only
break the mirror tie, so an order-dependent group count can change the *minimum set*, not
just a tie-break.

**Failure scenario.** A re-probe or a merge lands two cells on the same `dt_index`. Two
runs of the same alignment, with a query that has no `ORDER BY`, name two different core
frames.

**Recommend:** either refuse on duplicate indices, or make the tiebreak positional in
map space — `(int(idx_k[i]), int(phys[i][1]), int(phys[i][0]))`.

### [MEDIUM] F4 — no committed tests; two mutations survive every measurement in the report

`git diff --cached --name-only` = the report + `server/map_alignment.py`. **No
`server/tests/*`.** All six probes live under the session scratchpad and disappear with
the session.

That is a process point; the measured consequence is the finding. I re-ran the QA_MAP
32×4 sweep with four mutants substituted for `index_group_count`
(`…/scratchpad/QA1_sweep_audit.py`):

| mutation | sweep result | |
| --- | --- | --- |
| M1 drop `groups = boundaries + 1` | A=128/128 B=128/128 | **SURVIVES** |
| M2 count equal-`y` as a boundary | A=0/128 B=0/128 | killed |
| M3 read `x` instead of `y` | A=0/128 B=0/128 | killed |
| M4 remove the sort by index | A=128/128 B=128/128 | **SURVIVES** |

The core predicate *is* pinned — M2 and M3 die instantly. The two survivors are the
problem:

- **M4 survives because the sort is never exercised.** `seed.plan_job` returns rows
  already in `dt_index` order in all four jobs (verified: `pre-sorted by dt_index: True`,
  duplicate indices `0`). The function's headline robustness feature — do not trust row
  order, sort by the index — is measured by nothing. A production query without
  `ORDER BY` is the exact input it exists for, and F3 is what happens there.
- **M1 survives because `owner` is `[0]*n` everywhere**, so there is exactly one map and
  `+1` is a constant offset across all eight candidates. The report's most quotable line,
  *"`groups(truth)` lands exactly on the bin count every time"*, is therefore
  unfalsifiable by anything that ships — and the product owner explicitly refused the
  `groups == distinct c_bn` predicate, so no future check will pin it either.

**Recommend:** a committed `server/tests/test_index_group_count.py` covering, at minimum:
scrambled row order, duplicate indices, `cell_owner` with more than one map, and a partial
`idx_has`. Otherwise the anchor for all of this is a scratchpad directory.

### [MEDIUM] F5 — the rarest-label anchor rule is unexercised

`server/map_alignment.py:1682-1687` (`_seat_cost` / `min(labelled, key=_seat_cost)`)

Claim 5's first half — "anchors on the RAREST label rather than array order" — is true of
the code and demonstrated by no measurement. Measured (`…/scratchpad/QA1_fp_mutate.py`):

```
QA_MAP reference seat counts: B1=431  B2=426  B3=424      <- near-uniform
shipped (rarest anchor)  : 4/4 planted shifts, 850/850, seats=424
MF1 (first-in-array)     : 4/4 planted shifts, 850/850, seats=426
```

Deleting the entire rule changes nothing. The cost argument — *"the rarest label yields
the fewest seats (this is the whole cost of the function)"* — buys 424 seats instead of
426 here, 0.5 %. Both stated justifications are sound in principle; neither is defended by
a check. Nothing is wrong today; the risk is that a later edit removes the rule and every
green stays green.

### [MEDIUM] F6 — `128/128` is a count over 4 of the 8 frames

`…/scratchpad/QA1_sweep_audit.py`, Q1:

```
CANDIDATE_FRAMES        : rot0_front rot0_back rot90_front rot90_back
                          rot180_front rot180_back rot270_front rot270_back
truth frames in the sweep: rot0_back rot0_front rot180_back rot90_front
never exercised as truth : rot180_front rot270_back rot270_front rot90_back
```

Half the frame space is never the answer in any of the 128 runs, and two of the four
truths are `rot0_*`. A systematic bias against the 270° pair — or against `rot90_back` —
would leave `128/128` completely intact. This is the counts-vs-members gap: the number
pins a count, and its member set is half the space.

**Recommend:** add fixture jobs whose true core frame is `rot270_front`, `rot270_back`,
`rot90_back` and `rot180_front` before `128/128` is cited as coverage.

### [MEDIUM] F7 — the new `bin_labels` parameter raises on array input

`server/map_alignment.py:1667` — `range(min(len(phys), len(bin_labels or ())))`

`bin_labels or ()` evaluates the truth value of the container. Measured (H3):

```
bin_labels as np.array -> ValueError: The truth value of an array with more than
                          one element is ambiguous.
```

`cell_owner` (`:1602`) and `idx_has.size` (`:1604`) have the same constraint, but those
are copied verbatim from `direction_violations` and are an established convention (list +
numpy bool array). **`bin_labels` is new and has no precedent** — and `c_bn` is a DB
column the scorer will plausibly carry as an ndarray or a Series alongside `idx_k`, which
already *is* one.

**Recommend:** `if bin_labels is None: return …` and index directly; never rely on
container truthiness for a parameter whose real type is undecided.

### [LOW] F8 — unreachable guard

`server/map_alignment.py:1709` — `if top <= 0: return 0, 0, 0, len(seats), BINFP_NO_SEAT`

Each seat is drawn from `ref_by_label[anchor_lab]`, so `dx, dy` always maps the anchor
onto a die carrying the anchor's own label: `hit >= 1` for every seat. With `seats`
non-empty, `top >= 1` always. Dead, but it reads as the low-support guard the function
actually lacks (F1), which makes the absence harder to notice.

### [LOW] F9 — two of the lane's own assertions are impotent

Both in throwaway probes, so the only cost is that the report's `FAILED: none` claims more
than it tested.

- `…/scratchpad/DT_qamap_adjudicate.py:74` —
  `check(tuple(mask_box) != tuple(circle_box) or True, …)`. The `or True` makes the
  mask/circle discrimination check pass unconditionally. The boxes *do* differ (I verified
  it independently), but that is luck, not a verified precondition — and this is the exact
  check the standing QA_MAP warning asks for.
- `…/scratchpad/DT_verify.py:156` — `check(d[4] in (ma.BINFP_SEAT_CAP, None), …)`. Passes
  whether or not the cap fires. It happens to yield `seat_cap_reached`; the assertion did
  not establish that.

### [LOW] F10 — cost is bounded per seat, not per call

`bin_fingerprint_shift` is `O(seats × labelled)` pure Python; `_RESIDUAL_SEAT_CAP = 4096`
(`:1028`) caps the first factor only. QA_MAP: 424 × 850 ≈ 360 k dict lookups, ~0.15 s per
call. At the cap on a 50 k-die map: 4096 × 50 000 = 200 M lookups — minutes, per map per
alignment. Note the degenerate direction: **fewer distinct bins means more seats**, so the
worst case is exactly the low-information input that will end in `NOT_UNIQUE` anyway.
Worth a second bound (e.g. cap `seats × labelled`) before this is wired to anything that
runs per ingestion.

### [MEDIUM] F12 — the handoff's follow-up anchors are pre-insertion line numbers, and the list is incomplete

`agent_workspace/reports/Server_dt_to_core_transform.md` §5, correction 1, names four
comment blocks that carry the disputed `4/88` claim: `:1256`, `:3535`, `:3623`, `:4204`.
**Three of the four point at unrelated code in the tree the lane is handing over.** The
lane recorded the line numbers as they were *before* its own +187-line insertion at
`:1531`:

```
report :3535  ->  actual :3722   (3535 + 187)
report :3623  ->  actual :3810   (3623 + 187)
report :4204  ->  actual :4391   (4204 + 187)
report :1256  ->  actual :1256   (above the insertion point, correct)
```

Verified against `git show HEAD:server/map_alignment.py` — each stale anchor lands on the
`4/88` line in the *pre-change* file and on unrelated code in the current one
(`:3535` → a residual-seat log string, `:3623` → a value-axis format block, `:4204` → a
Korean assumption message).

The list is also **incomplete**: a fifth site, `server/scripts/seed_dt_index_walk.py:41`,
repeats the same claim ("*the same column scores the true frame 88/88 on the DT walk and
4/88 on the …*") and is not named. And `docs/process/PROJECT_STATUS.md:197` cites
`map_alignment.py:4203`, now equally stale.

**Failure scenario.** Queue item 5 («거짓 불변식 정정») is routed from this list. The
implementer opens `:3535`, finds a log-formatting line, and either edits the wrong thing
or concludes the report is wrong and drops the item. Two of the five real sites survive
untouched.

**Recommend:** re-anchor the list by grep, not by line number —
`grep -n "4/88" server/ docs/` returns all five sites plus the new block at `:1546`.
Note the new block itself cites `4/88` at `:1546` as something "the file already records";
that is accurate as a description of the file, but it means the disputed number is now
written in six places rather than five.

### [LOW] F11 — `groups` is dominated by map count, not walk quality

`server/map_alignment.py:1607` — `groups += 1` fires per map before any step is measured.
Measured (H5): 20 single-cell maps → `groups=20, steps=0`. Constant across candidate
frames, so it never flips a ruling. But the docstring's warning ("do not feed this into
the agreement thresholds") understates it: even a *relative* threshold is meaningless
without normalising by map count or by `steps`, and both are already returned.

---

## 3. Attacked and found safe

| hypothesis | result |
| --- | --- |
| **Claim 2 is fixture luck, not structural** — front/back does not really leave `y` alone under `grid_y_invert` / anisotropic chip / non-zero origin | **Safe.** H6: `y` identical for front vs back at all four rotations, under both the shipped meta and a meta with `y_invert=True`, chip 5×11, offset (3.5, −2.5), start (3, −4). 8/8. The 2-way mirror tie is structural. |
| **The `128/128` owes something to an undeclared third tiebreak** — `sorted(sc)[0]` falls through to the frame *name* alphabetically on a full `(groups, violations)` tie | **Safe, and worth recording.** The fallthrough exists, but I measured top-pair strictness across all 128 runs: **0/128 tie**. Nothing is alphabetical luck. |
| **Claim 3 is overstated** (violations alone loses on PART-R270) | **Safe — reproduced exactly.** truth `rot90_front` = 22, `rot270_back` = 20. Full vector measured; `rot270_back` is genuinely the minimum. |
| **Claim 4 is a vacuous assertion** (`assert x == 0` style) | **Safe.** `(None, 0)` verified for `idx_has=None` and for an all-`False` `idx_has`. A bare `0` would fail both checks — the assertion has teeth. |
| **Claim 6 does not reproduce** | **Safe.** 850/850 on all four planted translations, 424 seats, reproduced from a clean run. |
| **The sweep's local `groups_of` measures something different from the shipped function** (float compare vs `int()` cast, no sort, no per-map) — the synthetic `128/128` in report §1 was measured on the reimplementation, not the primitive | **Safe on this fixture.** I compared both over 8 frames × 4 jobs at the shipped meta: **identical on every cell**, and both reproduce the comment block's numbers exactly (1/11,40,44 · 3/31,43,46 · 4/16,19,22 · 2/21,41,45). The QA_MAP `128/128` used the shipped function directly. Downgraded to a note. |
| **Something is wired after all** | **Safe.** `grep` for `index_group_count`, `bin_fingerprint_shift`, `BINFP_` across `*.py`, `*.js`, `*.md` returns hits only inside `map_alignment.py` and the lane's own report. Diff is +187 / −0. `ast.parse` clean. |

---

## 4. QA_MAP numbers — independently verified

Read straight from the live DB, `SELECT` only (`…/scratchpad/QA1_dbfacts.py`):

```
valid_die_ref QA/MAP rows        : 1281   distinct cells: 1281
bbox x[-20..20] y[-21..20] = 41x42 = 1722 slots
FILL                             : 1281/1722 = 74.4%
rows with INTERIOR HOLES         : 7   (y = 14,15,16,17,18,19,20)
EMPTY INTERIOR rows              : 0
row widths min/max               : 2 / 41
map_split_registry map_key='QA_MAP' : 1 row
cached DT_qamap.json == live DB  : True
mask box (2,42,1,42)  vs  circle box (2,42,2,42)     [reproduced]
```

Every number the lane reported checks out, including that its cached fixture is the live
die set and not a stale copy. Note `valid_die_ref` has no `is_active` column — "1,281
active cells" is simply all rows for `product='QA' AND type='MAP'`.

### What the 0 empty-interior-rows actually leaves untested

`direction_violations` rule ② requires a row-change step to land on the **next floor
row** (`next_row`). With **no empty interior rows**, `next_row[y]` is always the
geometrically adjacent row, so "landed on the next *floor* row" and "landed on the
adjacent row" are the same predicate on QA_MAP. The whole point of computing `next_row`
from the floor rather than from `y ± 1` — a serpentine that must skip a fully empty band —
is never exercised. Every wrap judgment in all 128 runs is the easy case. That is not
QA_MAP's fault; it means a floor with a genuine empty band is still required, and no map
in the shipped set has one.

Two further caveats I would add to the lane's own honest list:

- The 7 hole rows are `y = 14..20` — a **single contiguous band at one extreme** of
  `y[-21..20]`, not scattered. Rule ③ is live, but in one locality and one sign of `y`.
- The mask/circle boxes differ **only in `y`-min, by one row**. A mix-up smaller than one
  row is invisible; a mix-up in `x` is invisible entirely.
- `seed._bin_of` is a *position-derived* label, so the reference bin map is spatially
  smooth — the friendliest possible input to a fingerprint. A real `c_bn` field that is
  spatially clustered (all of `B1` on one half of the wafer) yields far fewer
  distinguishing seats, and that is exactly where F1's low-support case and `NOT_UNIQUE`
  live. The lane says the labels are synthetic; this is the specific consequence.
- `idx_has` is `np.ones(n, bool)` in every sweep run and `cell_owner` is `[0]*n`
  everywhere: the partial-index path and multi-map summation are exercised only by the
  two-line R2 refusal check.

---

## 5. Suite — runtime verification NOT complete

**Reported as "not confirmed", not as "no problem".**

`PYTHONIOENCODING=utf-8 conda run -n assy_manager python -m pytest server/tests/ -q` was
started at 23:03 and was **still running at the end of this review** (~55 min, PID
confirmed alive and consuming CPU). Exactly one pytest was run; no second one was started.
The full pass/fail line is not mine to report and the lead PM should collect it before
merging.

What I *did* establish about the blast radius:

```
pytest server/tests/ -q --collect-only   ->  3064 tests collected in 4.05s, no errors
ast.parse(server/map_alignment.py)       ->  clean
grep for the two new symbols outside the file -> 0 hits
git diff --cached --stat                 ->  +187 / -0
```

Collection exercises import of every test module, so an import-time break in
`map_alignment.py` would already have surfaced there and did not. With zero callers, the
only mechanism by which this diff could turn a test red is import-time, which is now
excluded. The residual risk is a shared-tree interaction with the concurrently active
ingestion lane, not this change.

No client changes, so no `node --check`.

For reference, the last recorded baseline in `agent_workspace/reports/` is
**1958 passed, 2 skipped** (2026-08-04); the suite has since grown to 3064 collected, so
that number is not a usable comparison.

---

## 6. Documentation

No living document is stale **yet**, and that is a real finding rather than an omission:
nothing is wired, no REST/WS/cell-shape/`/schema` contract moves, and I confirmed
independently that `direction_violations`, `serpentine_index` and the whole
alignment-scoring family appear **nowhere** in `docs/process/DOC_OWNERSHIP.md`,
`docs/spec/MAP_ALIGNMENT_SPEC.md`, or `docs/architecture/PRIMITIVES.md`. The lane's
handoff item 3 is accurate — the catalogue that the "check before you build" rule points
at does not contain the family this belongs to, so there is no row to update and no row to
have missed.

Consequence for the wiring round: when these are wired, `DOC_OWNERSHIP.md` will need a row
for the scoring axes *created*, not amended. That is the doc work, and it is larger than
the two functions.

No overstatement found in the report's prose against its own measurements — the lane
reported numbers *worse* than the note it was adjudicating (1/88, 1/34, 0/85 vs the
recorded 4/88) rather than repeating an unreproducible one, and flagged its own harness
bug. The one place the prose runs ahead of the evidence is *"`groups(truth)` lands exactly
on the bin count every time"* (F4/M1: nothing checks it) and *"the anchor die is the one
whose label is RAREST"* (F5: nothing measures it).

---

## 7. Proposed lessons (for the lead PM to place, not added directly)

For `agent_workspace/memory/qa-reviewer.md`:

> - **함정**: 「128/128」 같은 전수 통과 수치를 **커버리지**로 읽는다. 실제로는 **정답 집합이
>   후보 공간의 절반**이었다 — 8개 프레임 중 4개는 어떤 런에서도 정답이 아니었고, 편향이 있어도
>   숫자는 그대로 초록이다.
>   **올바른 방법**: 통과 수를 보기 전에 **정답의 구성원 집합**을 먼저 뽑아 후보 공간과 차집합을
>   낸다. 그리고 **변이를 심어 그 수치가 실제로 무엇을 고정하는지** 잰다 — 이번엔 4개 변이 중
>   2개가 128/128을 그대로 통과했고, 통과한 둘이 그 함수의 간판 기능(인덱스 정렬·그룹 +1)이었다.

> - **함정**: 검증 산출물이 세션 스크래치패드에만 있으면 「측정했다」는 다음 라운드에 **재현
>   불가능한 주장**이 된다. 커밋된 테스트가 0건인데 보고서만 초록이었다.
>   **올바른 방법**: 커밋되는 회귀 그물이 없으면 그 측정은 **판정 근거로는 유효하지만 넷으로는
>   무효**라고 보고서에 명시하고, 배선 전 필수 조건으로 올린다.

---

*Probes: `…/scratchpad/QA1_attack.py`, `QA1_sweep_audit.py`, `QA1_fp_mutate.py`,
`QA1_seatcap.py`, `QA1_dbfacts.py`, `QA1_comment_numbers.py`, `QA1_viol.py`.
No code was modified. DB access was `SELECT` only.*
