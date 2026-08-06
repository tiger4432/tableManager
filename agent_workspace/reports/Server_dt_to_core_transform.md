# LANE DT — queue item 1: `dt_log` → core map transform

**Adjudication: (a) — NO CONTRADICTION. The dictated design is sound and I implemented it.**

But the reason is not the one option (a) offered, and the difference matters, so it is stated
first.

---

## 1. The adjudication

### What option (a) guessed, and why it is only half right

The brief's option (a) says the 4/88 "was measured under a fixed/assumed core frame", i.e. that
the low number is what a **wrong rotation** looks like. That is not what I measure. The 4/88 was
measured under the **TRUE** core frame, and it is low because the **predicate is the wrong
question**, not because the frame was wrong.

`_index_member` (`server/map_alignment.py:1431`) asks one thing:

> is this cell the k-th cell of a **global serpentine** over this walk?

On the core walk that is false **by construction, under the correct rotation**, because the pick
order is **bin-major**: every bin boundary throws the global rank off by the size of the
preceding bin. The number 4 is not "the size of a wrong anchor" (which is what
`map_alignment.py:1257` asserts) — it is the residue of two orderings that only coincide by
accident.

So the existing note and the dictated design are **not talking about the same measurement**. The
note measures rank-equality; the owner's design measures **monotonicity within a run**. Both can
be true at once, and both are.

### The numbers I measured myself

Fixture: `server/scripts/seed_dt_index_walk.py` (the generator that produced the original note),
driven **in memory, no DB**. Probe:
`…/scratchpad/DT_adjudicate.py`.

**Core walk, SHIPPED predicate (`_index_member`), score of the TRUE core frame:**

| job | dies | bins | true core frame | truth scores | best of 8 scores | winner |
| --- | --- | --- | --- | --- | --- | --- |
| FULL-R0 | 88 | 1 | `rot0_front` | **88/88** | 88 | truth |
| FULL-R90 | 88 | 3 | `rot180_back` | **1/88** | 2 | `rot180_front` ❌ |
| PART-R270 | 34 | 4 | `rot90_front` | **1/34** | 2 | `rot0_back`, `rot90_back` ❌ |
| NEAR-R180 | 85 | 2 | `rot0_back` | **0/85** | 4 | `rot270_back` ❌ |

⚠️ **`FULL-R0` cannot show anything and I exclude it.** With `bins=1` and
`core_frame == dt_frame == rot0_front`, `plan_job` produces `core_x/core_y` **byte-identical to
`dt_x/dt_y`** (asserted in the probe, not assumed). That job is the degenerate case, and it is
the reason the literal number "4/88" is **not reproducible**: no run of this fixture yields 4 on
an 88-die core walk. I report my own numbers (1/88, 1/34, 0/85 — *worse* than 4) rather than
repeat one I could not reproduce. The note's *structure* — "near-zero on the core walk, and a
wrong frame comes first" — reproduces exactly, in **3 of 3 non-degenerate jobs**, which is
stronger than the "2 of 8 combinations" the note claims.

**Core walk, DICTATED predicate (group boundaries: index rises while y falls):**

| job | bins | groups at truth | groups at the 7 others | min held by |
| --- | --- | --- | --- | --- |
| FULL-R0 | 1 | **1** | 11 / 40 / 44 | `rot0_front`, `rot0_back` |
| FULL-R90 | 3 | **3** | 31 / 43 / 46 | `rot180_back`, `rot180_front` |
| PART-R270 | 4 | **4** | 16 / 19 / 22 | `rot90_front`, `rot90_back` |
| NEAR-R180 | 2 | **2** | 21 / 41 / 45 | `rot0_back`, `rot0_front` |

The separation is not marginal — it is an order of magnitude. **The premise holds: `dt_index` IS
an ordering over the core walk, and a wrong rotation does mass-produce group events.** That is
option (a).

### 🔴 The finding that changes how this must be wired

**Group minimisation ALONE can never name a frame. It always ties exactly 2-way**, and the tie is
always the **front/back mirror**. This is structural, not fixture luck: a front↔back flip is
`x → −x` and leaves `y` untouched, so **no y-based count can ever separate that pair.** In 4 of 4
jobs the minimising set was exactly `{truth, its mirror}` — never a unique winner.

`direction_violations` breaks it every time (it reads the x-direction of each step). And the
converse also holds — **violations alone is not enough either**: on `PART-R270` it prefers
`rot270_back` (20 violations) over the truth (22). So the two are structural partners, exactly as
open task **#36** records. The dictated design and #36 are **the same thread**, and #36's
recorded property is the operational form of it.

Joint ordering `(groups, then violations)` named the true core frame in **128 / 128** runs.

### Degeneracy sweep — I turned every axis on

Per the brief, all five degenerate axes toggled (2⁵ = 32 combinations) × 4 jobs. Probe:
`…/scratchpad/DT_degenerate_sweep.py`.

| axis | OFF (shipped fixture) | ON |
| --- | --- | --- |
| chip | 7×7 | **5×11** (`chip_x != chip_y`) |
| start | (0, 0) | **(3, −4)** (non-zero origin) |
| y invert | False | **True** |
| phys offset | (0, 0) | **(3.5, −2.5)** |
| wafer dia | 300 | **200** (a second, different box) |

```
combinations x jobs = 128
A. truth in the group-count MINIMUM set : 128/128
B. joint (groups, violations) names truth: 128/128
no failures.
```

The linear part was **read, not derived** — three points through
`map_overlay.make_physical_transform` for each of the 8 frames
(`o`, `d/dx`, `d/dy` printed in `DT_adjudicate.py`). I also verified the fixture's round trip is
exact rather than assuming it: `physical(express(cell, F)) == physical(cell)` is **88/88 for all
eight frames** (`…/scratchpad/DT_roundtrip.py`) — that check is what caught a bug in my own test
harness (below).

---

## 1-bis. Re-measured on QA_MAP (product owner standing instruction, received mid-round)

Everything above was first measured on the synthetic `PRD-A/DT13` floor (88 dies). The whole
adjudication was then **re-run against the real valid die map, `QA_MAP`**, read straight out of
`valid_die_ref` (`product='QA'`, `type='MAP'`). Probes:
`…/scratchpad/DT_qamap_read.py` (read-only DB) and `…/scratchpad/DT_qamap_adjudicate.py`.

### It is genuinely sparse — measured, not assumed

```
valid_die_ref QA/MAP rows: 1281   distinct cells: 1281      <- matches the 1,281 given
bbox x[-20..20] y[-21..20] = 41x42 = 1722 slots
FILL: 1281/1722 = 74.4%
rows with INTERIOR HOLES : 7        <- serpentine rule 3 is LIVE
EMPTY INTERIOR rows      : 0        <- serpentine rule 2 is NOT exercised
row widths min/max       : 2 / 41
meta: grid 45x45  start (-20,-20)  yinv=False  rot=0/front  chip 7x7  dia 300  margin 3
```

And the check the standing warning actually asks for — **the mask box and the circle box are not
the same box**:

```
mask box (from the 1,281 dies) : (2, 42, 1, 42)
circle box (phys geometry)     : (2, 42, 2, 42)      <- differ in y-min
```

So a fixture built on QA_MAP **can** go red on a mask/circle mix-up. A full disc could not.
⚠️ One honest caveat: the difference is **one row** (`y` 1 vs 2), so it discriminates but not
loudly; a bug smaller than one row is still invisible here. **Empty interior rows are 0**, so
serpentine rule ② remains unexercised by this map — the same blind spot the shipped docstring
already records for the other five floors.

### The defect, on real dies

Shipped `_index_member` on the core walk. Denominators are now real:

| job | dies | bins | truth scores | best of 8 | winner |
| --- | --- | --- | --- | --- | --- |
| FULL-R0 | 1281 | 1 | 1281/1281 | 1281 | truth — **but degenerate**, `core` cols are byte-identical to `dt` cols |
| FULL-R90 | 1281 | 3 | **2/1281** | 2 | ties with `rot0_back` ❌ |
| PART-R270 | 487 | 4 | **2/487** | 2 | ties with `rot90_back` ❌ |
| NEAR-R180 | 1278 | 2 | **0/1278** | 3 | `rot90_front` ❌ outright |

The old predicate is not merely weak on real dies — on 1,278 numbered cells it scores the correct
answer **zero** and hands the win to a wrong frame.

### The repair, on real dies

| job | bins | groups at truth | groups at the 7 others | min set | joint winner |
| --- | --- | --- | --- | --- | --- |
| FULL-R0 | 1 | **1** | 42 / 627 / 638 | mirror pair | ✅ truth |
| FULL-R90 | 3 | **3** | 123 / 625 / 656 | mirror pair | ✅ truth |
| PART-R270 | 4 | **4** | 156 / 228 / 260 | mirror pair | ✅ truth |
| NEAR-R180 | 2 | **2** | 82 / 637 / 642 | mirror pair | ✅ truth |

Separation widened from ~10× on the 88-die floor to **~40–200×** on 1,281 real dies, and
`groups(truth)` lands exactly on the bin count every time. The min set is **again always the
front/back mirror pair** — the structural 2-way tie is confirmed on real data, not a small-fixture
artefact.

**Fingerprint on QA_MAP**, partial-bin job (bin `B1` dropped, 850 of 1,281 cells, 424 seats):
the anchor rule mis-seats it by `(−1, 0)`; the fingerprint recovers all four planted translations
`(0,0) (4,−3) (−7,5) (11,9)` exactly, **850/850 matched** each time.

**Degeneracy sweep on QA_MAP** (chip 5×11 · start shifted from the map's real `(−20,−20)` ·
`grid_y_invert` · phys offset `(3.5,−2.5)` · dia 450), 32 combinations × 4 jobs:

```
A. truth in group-count MINIMUM set : 128/128
B. joint (groups, violations) winner: 128/128
```

### 🔴 What is real here and what is still synthetic

**The valid die basis is real** — 1,281 dies out of `valid_die_ref`, no substitute, no synthetic
floor. **The pick order is still synthetic and has to be**: this box has no production
`dt_index` that was assigned bin-major, because the rule being implemented was dictated for the
first time on 2026-08-06. The bin labels come from `seed._bin_of` (a deterministic
position-derived label), not from a real `c_bn` distribution. So the correct reading of these
numbers is: *given a pick order that obeys the owner's stated rule, on the real die field, the
transform is recoverable.* Whether real `dt_log` obeys that rule is **not** something I can
measure here, and it is the first thing a live drill should check.

---

## 2. What I built

Both live in **`server/map_alignment.py`**, placed immediately after `direction_violations`
because they are read together. **The change is purely additive: +187 lines, zero existing lines
touched.** Nothing is wired into a route, a payload, or the scorer yet — **no boundary contract
moves**, and the pipeline behaves byte-identically until the lead PM authorises wiring.

### `index_group_count(phys, cell_owner, idx_k, idx_has) -> (groups, steps)`

Same four arguments as `direction_violations`, same order, same meaning — they are consumed as a
pair. Per map: sort by index, count strict `y` decreases, `groups = boundaries + 1`, sum over
maps.

- **Smaller is better**, like `direction_violations` and unlike everything else in the file. The
  docstring says so explicitly so it never lands in an agreement threshold.
- Returns **`(None, 0)`** when nothing carries an index. A `0` here would read as "one group",
  i.e. a *perfect* score, for a walk nobody numbered — the `absent-zero-is-not-inert-zero` class.
- Equal `y` is **not** a boundary (inside a serpentine row `y` is constant).
- It returns the **count only**. The exact predicate `groups == distinct c_bn` was refused by the
  product owner; comparing here would smuggle that refused ruling back in.

### `bin_fingerprint_shift(phys, bin_labels, reference_bins, seat_cap) -> (dx, dy, matched, seats, reason)`

Seats, not a window — the same argument `_residual_shift` already makes (the offset can be a
wafer radius; `±w` search is quadratic and misses). A source die can only sit on a reference die
**carrying the same label**, so candidate translations are enumerated from the data, linear in
the reference.

- **The anchor die is the one whose label is RAREST in the reference**, not the first in the
  array. Two reasons, both load-bearing: the rarest label yields the fewest seats (that is the
  entire cost of the function), and **array order is not a property of the map** — anchoring on
  it would make the same input answer differently when the query returns rows in another order.
- **Refuses rather than guesses.** A non-unique maximum returns `qualifying_seat_not_unique` and
  does *not* fall back to the origin-nearest tie-break — that would let the *rule* place the map,
  the exact move `[3-0]` retired the shift search for. On any refusal `(dx, dy)` is `(0, 0)` and
  the docstring states that **the zero is not a measurement**.
- Reason vocabulary **reuses** `RESIDUAL_NO_QUALIFYING_SEAT` / `RESIDUAL_NOT_UNIQUE` /
  `RESIDUAL_SEAT_CAP` (the outcomes are literally the same facts); only two genuinely new names
  are added, `BINFP_NO_SOURCE_BINS` and `BINFP_NO_REFERENCE_BINS`.

### Primitives reused, not re-spelled

| reused | where | for what |
| --- | --- | --- |
| `serpentine_index` / `serpentine_rank` | `:1287` / `:1320` | the fixture's own walk; not re-implemented |
| `direction_violations` | `:1479` | the mirror-breaking partner; argument shape copied verbatim |
| `direction_judge` | `:1456` | the reference-side row rule |
| `_RESIDUAL_SEAT_CAP`, `RESIDUAL_*` reasons | `:1028`, `:1374-1378` | cap + refusal vocabulary |
| `map_overlay.make_physical_transform` | `map_overlay.py:1342` | canonical coords, the same mapping `_index_member` reads |
| `dt_map_derivation.source_meta_for_frame` | `:339` | candidate frame → meta |
| `map_alignment.CANDIDATE_FRAMES` | `:73` | the eight; no literal list |

**Nothing pre-existing does either job.** `grep` for group counting and for bin fingerprinting
across `map_alignment.py`, `map_overlay.py` and `docs/architecture/PRIMITIVES.md` returns
nothing; `PRIMITIVES.md` does not catalogue `serpentine_index`, `direction_violations`,
`_solve_shift` or `_residual_shift` either (see §5).

---

## 3. The fixture reproduces the defect BEFORE the repair was scored

Probe: `…/scratchpad/DT_verify.py`. Part 1 runs and asserts **before** Part 2 exists in the
output.

```
PART 1 - THE FIXTURE REPRODUCES THE DEFECTS (asserted before any repair)

 D1. the SHIPPED index axis (`_index_member`) cannot read the core walk
   OK  FULL-R0 is degenerate (core cols == dt cols), excluded   truth=88/88
   OK  FULL-R90:  truth=1/88  best=2 at ['rot180_front']            <- WRONG frame first
   OK  PART-R270: truth=1/34  best=2 at ['rot0_back','rot90_back']  <- WRONG frames first
   OK  NEAR-R180: truth=0/85  best=4 at ['rot270_back']             <- WRONG frame first

 D2. the ANCHOR rule places a partial-bin job wrong
   OK  lowest-index die is NOT the wafer top-left
       anchor sits at (7,0), wafer top-left is (5,0) -> anchor rule would shift by (-2,0)
   OK  the partial-bin fixture really drops a bin   59/88 cells, bins ['B2','B3']
```

D2 is the defect the fingerprint exists for, and it is a **real** miss, not a hypothetical: with
bin `B1` removed the anchor rule mis-seats the whole map by `(−2, 0)`.

Then the repair:

```
PART 2 - THE REPAIR
 R1  joint winner == truth on all four jobs (min set is always the mirror pair)
 R2  index_group_count returns None, not 0, when nothing carries an index
 R3  planted translations (0,0) (4,-3) (-7,5) (11,9) all recovered exactly,
     matched 59/59 each, 29 seats
 R4  refuses: no_source_bin_values / no_reference_bin_map /
     qualifying_seat_not_unique (single-label map) / seat_cap_reached
PART 3  32-combination degeneracy sweep, planted-shift recovery: 96/96
FAILED: none
```

### 🔴 One measurement disagreed with what I believed, and I chased it instead of shipping it

The first run of R3 reported the correct shift with **`matched=16/59`**. The shift was right, all
four plants recovered, every line was `OK` — and 16 was wrong. I stopped and measured the round
trip directly (`DT_roundtrip.py`), which proved bin agreement at zero shift is **59/59**. The
cause was **in my harness, not the primitive**: a `for job in seed.JOBS` loop in Part 2 rebound
`job`, so R3 built the reference bin map from `NEAR-R180` (2 bins) while the cells came from
`FULL-R90` (3 bins). Fixed; now 59/59.

Worth recording: **the fingerprint still recovered every planted shift against a wrong-arity
reference bin map at 27 % agreement.** That is evidence it is robust, and it is also exactly the
kind of green that hides a broken fixture.

---

## 4. Where this stands, and the wiring hazard

Nothing is wired. When it is:

- **`_same_walk` (`:4106`) must NOT be loosened.** It correctly blocks the *rank-equality*
  predicate from following `dt_index` onto a walk that never claimed it. The new axis is a
  different mechanism that legitimately reads the core walk, so it needs **its own** gate — a
  declaration that says "this table's `index` numbers the core pick order" — not a hole in that
  one.
- **The `c_bn` fingerprint needs an input that does not exist yet in the scorer**: the *original*
  core bin map (`core_wafer_map.c_bn` or equivalent) as `{(x, y): label}` in canonical
  coordinates. That is a new reference resolution, adjacent to `_resolve_reference`, and it is a
  design decision (which table, declared where) rather than an implementation detail. **I did not
  invent it.**
- **Reference-frame prerequisite.** Every number above is measured against a reference bin map
  whose own frame is known. If the original bin map's frame is itself unconfirmed, the
  fingerprint inherits that uncertainty. Flagging, not solving.

---

## 5. Handoff

**Changed:** `server/map_alignment.py` only. +187 lines, additive. Not committed. Not wired. No
REST/WS/cell-shape/schema contract touched.

**Verified:** five standalone probes under the session scratchpad, `conda run -n assy_manager` —
two of them against the real `QA_MAP` die set (one read-only DB read, one pure scoring run).
No writes, no DDL, no probe database created.
**I did not run pytest** (another lane holds it) — QA must. The added functions are not imported
by any existing code path, so the suite's behaviour should be unchanged; that is a prediction, not
a measurement, and it is QA's to confirm.

**Corrections the lead PM should route (I did not make them unilaterally):**

1. 🔴 **Four comment blocks in `map_alignment.py` state a claim I could not reproduce and whose
   stated *cause* is wrong** — `:1256`, `:3535`, `:3623`, `:4204`. They say the core walk scores
   4/88 and that "4는 … **앵커가 틀린 것의 크기**다" (the size of a wrong anchor). My measurement:
   the number is 1/88, 1/34, 0/85 depending on the job (never 4), and the cause is the
   **bin-major pick order vs. global rank**, not the anchor. The *conclusion* those blocks draw
   (the index axis is a DT-walk rule, `_same_walk` must gate it) is **correct and unaffected** —
   only the number and the mechanism are wrong. This belongs with **queue item 5**
   («거짓 불변식 정정»), not to me this round.
2. **Board `#36` and queue item 1 are the same thread**, now with evidence: groups always tie the
   front/back mirror, violations alone loses `PART-R270`. The board's «두 숫자가 각각 거울상 하나씩
   못 본다» is confirmed and now has a named mechanism for the groups half (a front/back flip is
   `x → −x`; no y-based count can see it).
3. **`PRIMITIVES.md` gap** — it catalogues neither `serpentine_index`/`serpentine_rank`, nor
   `direction_violations`, nor `_solve_shift`/`_residual_shift`, nor the two added here. That is
   the whole alignment-scoring family missing from the "check before you build" catalogue.

**History entry draft** (for the lead PM to place; I did not touch `docs/history/` or
`gen_index.py`):

> `20260806_dt_index_orders_the_core_walk_the_old_number_measured_a_different_question.md`
> The 4/88 that looked like a refutation of the owner's dictated design was measuring rank
> equality, not order. Under the true core frame the bin-major pick order cannot equal a global
> serpentine rank — that is the design, not a defect. Measured on the same fixture: group
> boundaries separate the true frame from the wrong ones by an order of magnitude, 128/128 across
> the full degeneracy sweep. And group count alone can never finish the job: a front/back flip
> leaves y untouched, so the minimum is always a two-way mirror tie. That is why #36 says the two
> numbers are partners.

**Proposed lesson for `agent_workspace/memory/server-pm.md`** (not added directly):

> - **함정**: 「같은 컬럼이 저기서 88/88, 여기서 4/88」을 **축이 다르다**로 읽는다. 실제로는
>   **술어가 다른 질문을 하고 있었다** — 순위 일치(`_index_member`)와 구간 내 단조성은 같은
>   번호에 대한 서로 다른 물음이고, 낮은 점수는 좌표가 틀렸다는 뜻이 아니라 **그 질문의 답이
>   아니라는 뜻**이다.
>   **올바른 방법**: 두 수가 모순처럼 보이면 **먼저 두 수가 같은 술어로 잰 것인지 확인**한다.
>   그리고 픽스처의 **퇴화 유닛을 먼저 골라낸다** — 이 라운드의 `FULL-R0`는 core 컬럼과 dt 컬럼이
>   **바이트 동일**이라 어느 쪽 주장도 증명할 수 없었고, 원 실측이 재현되지 않은 이유가 그것이다.
