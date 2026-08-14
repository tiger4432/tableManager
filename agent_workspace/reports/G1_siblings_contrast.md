# G1 — `GET /api/ledger/siblings`, intersection + contrast

> **Status: LANDED AND WIRED.** Route registered (`server/main.py:172-173`), 14 tests
> green against real PostgreSQL, 6 injected defects each proven RED, verified live
> against `assy_manager`. Read-only throughout: no migration, no index, no write.
>
> ⚠️ **Every number below is measured on a 100% synthetic fixture.** `void_obs`,
> `inspection_run` and `delam_obs` are entirely synthetic; `bonding_log` is 98.5%
> synthetic. Nothing here is a statement about production.

---

## 1. THE CONTRACT — build against this

### 1.1 Route

```
GET /api/ledger/siblings
```

**One endpoint, two framings.** `mode` changes *ranking and filtering only*; the row
shape is identical in both. That is load-bearing, not a convenience: a decoy factor is
`share = 1.0` in the found set (top of `intersection`) and flat in `contrast`. If the two
modes returned different shapes the console could not put them side by side and the
difference — the thing contrast exists to show — would be invisible.

### 1.2 Query parameters

| name | type | default | meaning |
|---|---|---|---|
| `finding` | str | `void` | The finding kind. **A parameter from the first line.** `void` is `finding_kinds.DEFAULT_KIND`, not a branch. |
| `mode` | `intersection` \| `contrast` | `intersection` | Framing. |
| `window` | str | *(none)* | `7d` / `30d`, or `YYYY-MM-DD..YYYY-MM-DD`. Absent = all time. |
| `limit` | int | `20` | Max factor rows (1..200). |
| `min_support` | int | `2` | Minimum found-count for a row to be returned. |
| `axes` | csv | *(all)* | e.g. `bond_eqp,bond_lot`. |

Unknown `finding` → **422**, structured. Malformed `window` → **422**, structured.

### 1.3 Response envelope

```jsonc
{
  "generated_at": "2026-08-14T05:31:22+00:00",
  "state": "ready",                    // ready | absent | empty
  "mode": "contrast",

  "finding": {
    "kind": "void", "label": "보이드", "declared": true,
    "observed_by": ["sat"],            // METHODS whose runs define the denominator
    "population_unit": "package",
    "population_unit_label": "패키지 (base 위치)",
    "unit_columns": ["base_wafer_id", "base_x", "base_y"],
    "source": { "relation": "void_obs" }
  },

  "window": { "declared": true, "spec": "7d",
              "from": "2026-08-07T…", "to": "2026-08-14T…" },

  // 🔴 THREE-WAY SPLIT, ALWAYS. never_scanned is its own count and never joins clean.
  "populations": {
    "found":         { "count": 46899,  "unit": "package" },
    "clean_scanned": { "count": 28101,  "unit": "package" },  // scanned ∧ zero findings
    "never_scanned": { "count": 280000, "unit": "package" },  // no run at all
    "scanned":       { "count": 75000,  "unit": "package" },  // the real denominator
    "universe":      { "count": 352500, "unit": "package" },
    "scanned_outside_universe": { "count": 2500, "message": "…" }
  },

  "denominator": {
    "state": "ready",                  // ready | absent
    "basis": "inspection_run",
    "methods": ["sat"],
    "reason": null,                    // structured token when absent
    "message": null                    // Korean prose, operator's eyes only
  },

  "axes": [ { "name": "bond_eqp", "label": "본딩 장비", "about": "process",
              "source": "bonding_log.bond_eqp",
              "covered": { "found": 44399, "clean_scanned": 28101 } } ],

  "factors": [ /* FactorRow */ ],
  "factors_truncated": true,
  "factors_considered": 219,
  "notes": []                          // structured tokens, never prose to parse
}
```

### 1.4 `FactorRow` — identical in both modes

```jsonc
{
  "axis": "bond_eqp", "value": "BAD-1", "label": "본딩 장비 = BAD-1",
  "about": "process",                  // process | inspection  — a BADGE, see §1.8

  "found":         { "n": 80, "of": 90,  "rate": 0.8889 },
  "clean_scanned": { "n": 20, "of": 110, "rate": 0.1818 },   // null when no denominator

  "enrichment":       4.8889,          // rate_found / rate_clean.  null when undefined
  "enrichment_ci":    [3.19, 7.49],    // 95% interval — WHAT CONTRAST RANKS ON, §1.5
  "rate_delta":       0.7071,
  "enrichment_state": "enriched",      // enriched | flat | depleted | undeterminable
  "reason":           null,            // token when enrichment could not be computed

  "evidence_refs":      [ { "relation": "bonding_log", "key_column": "bond_cell_key",
                            "key": "PKG-000", "column": "bond_eqp",
                            "population": "found" } ],
  "evidence_ref_count": 80             // total; `evidence_refs` is a capped sample
}
```

**Both denominators are on the row.** `found.of` and `clean_scanned.of` sit beside the
rates, so nothing on the screen is a bare ratio.

### 1.5 Ranking — and the one change from the first published draft

`intersection` → sort by `found.rate` desc, then `found.n` desc. Nothing dropped.
`contrast` → sort by **`enrichment_ci[0]`** desc, and **drop `flat` rows**.

🔴 **Ranking moved from the point estimate to the interval's lower bound after a
measurement.** With the bare ratio, `finding=delam` on the live fixture returned a hundred
per-lot rows at 1.7–1.9x, every one carried by ~108 packages, and they buried everything
else. Their lower bounds fall under 1.5 and they correctly become `flat`. A ratio without
its sample size is as unreadable as a rate without its denominator — this is the second
half of 「기저율 대비 놀라움」. Method: Katz log interval, Haldane-corrected, z = 1.96.
Thresholds are declared (`contrast.enriched_at` / `depleted_at`), not literals.

`undeterminable` is **not** `flat` and is never dropped: one is a missing judgement, the
other is a judgement of "no difference".

### 1.6 The nothings, kept apart

| situation | HTTP | `state` |
|---|---|---|
| observation relation not deployed | 200 | `absent` (populations all `null`) |
| deployed, zero findings in window | 200 | `empty` |
| findings exist | 200 | `ready` |
| kind not declared / bad window | **422** | structured `detail` |

**Degrading honestly with no denominator** (`observed_by: []`, or the run relation absent,
or zero runs for the declared methods — three reasons, named apart because the operator's
fix differs):

* `intersection` **works fully**.
* `denominator.state = "absent"`, `reason` ∈ `no_observed_by_declared` |
  `no_runs_for_methods` | `run_relation_absent`, `message` = 「분모 없음 — 대조 불가 …」.
* `clean_scanned` / `never_scanned` / `scanned` are **`null`, not `0`**. A zero there is
  the claim "nothing was clean"; `null` is the absence of a claim.
* Rows keep `found`; `clean_scanned: null`, `enrichment: null`,
  `enrichment_state: "undeterminable"`, `reason` = the same token.
* `mode=contrast` is **200**, plus `notes: [{note: "contrast_unavailable", …}]`. The
  console renders 「분모 없음 — 대조 불가」 *as the panel's content*. A clean population is
  never fabricated.

### 1.7 Refusal bodies

```jsonc
{ "detail": { "reason": "unknown_finding_kind", "kind": "scratchy",
              "declared_kinds": ["delam","void"],
              "message": "선언되지 않은 관측 종류: scratchy" } }
{ "detail": { "reason": "bad_window", "spec": "7 days",
              "message": "window 형식: 7d 또는 YYYY-MM-DD..YYYY-MM-DD" } }
```

### 1.8 `about` — a badge, never a filter

`process` = the axis describes what made the part. `inspection` = it describes the scan
that looked at it. An enrichment on an `inspection` axis is a real finding — the inspector
is biased — but a *different* one. A console that cannot tell them apart will report a
scanner artefact as a process cause, so the badge must reach the screen.

---

## 2. Files

| path | what |
|---|---|
| `C:\Users\kk980\Developments\assyManager\server\ledger_siblings.py` | the engine (new) |
| `C:\Users\kk980\Developments\assyManager\server\config\siblings_axes.json.sample` | factor geometry: joins, axes, universe (new) |
| `C:\Users\kk980\Developments\assyManager\server\ledger_trace_router.py` | `GET /api/ledger/siblings` added |
| `C:\Users\kk980\Developments\assyManager\server\tests\test_ledger_siblings_pg.py` | 14 tests, answer key both directions (new) |

Not touched: `client2/**`, `server/map_alignment.py`, `server/migrations/**`,
`server/config/map_overlay_config.json*`, `server/scripts/**`. Nothing committed or staged.

### 🚧 Lane collision, resolved without clobbering — needs your ruling

I wrote a kind registry at `server/finding_kinds.py` at 09:28; **another lane wrote a
different one at the same path at 09:30.** I did not overwrite it. Theirs is now the SSOT
and my engine **consumes** it (`DEFAULT_KIND`, `kinds()`, `spec()`, `methods()`,
`observation_table()`, `RUN_TABLE`, `PACKAGE_TABLE`), and I deleted my colliding
`server/config/finding_kinds.json.sample`. My own config declares only the factor
geometry, which their registry does not model.

**One duplication remains and I could not resolve it alone:** their
`finding_kinds.population_ctes()` spells the three-way split as SQL text using
SQLAlchemy `:name` binds; my engine needs psycopg2 `%(name)s`, a time window, and a
`unit_id`, so it builds its own. Two spellings of a rule whose own docstring says it must
have one. Proposal: keep mine (it is windowed and parameterised) and have their console
call `siblings()` for population counts, or move `population_ctes` to `%(name)s`. **Your
call.** Also worth adding to their `DEFAULT_FINDING_KINDS`: a kind with
`observed_by: []`, so honest degradation is exercised by a declared kind and not only by
a test injecting one.

---

## 3. Validation

### 3.1 Answer key, both directions — 14 tests, real PostgreSQL, scratch schema dropped

The live fixture is **useless as a positive control**: as of this morning its factors are
unbiased by construction (`bond_eqp` is `1 + lot % 4`, never used to bias a void), and I
measured every `bond_eqp` enrichment at 0.99–1.02. So it is an excellent *decoy* corpus
and the planted factor is planted in the test's own scratch schema, where its true value
is known:

```
bond_eqp = BAD-1   80% of its packages void   ← void's planted factor
bond_eqp = GOOD-1  10%
b_bn     = DEL-1   80% of its packages delam  ← delam's planted factor (a DIFFERENT axis)
bond_lot = LOT-A   every scanned package      ← DECOY
bond_lot = LOT-GHOST  only the 100 never-scanned packages
```

The two kinds' factors sit on **independent axes** (`i%2` vs `i%3`) — if they shared one,
"delam's answer does not contain void's factor" would be true by construction rather than
because the query is right.

* `test_contrast_finds_the_planted_factor` — BAD-1, enrichment > 1.5, `ci[0] > 1.5`.
* `test_contrast_drops_the_decoy_that_intersection_tops` — **the assertion that
  distinguishes a working contrast from a broken one.** LOT-A is asserted to be the FIRST
  row of intersection (rate 1.0) and ABSENT from contrast. A contrast that simply returned
  everything passes the previous test and fails this one.
* `test_switching_the_kind_switches_the_answer_and_not_only_the_heading` — each kind finds
  its own factor and **not** the other's; denominators swing `sat` → `scat`.
* `test_never_scanned_is_its_own_count_and_never_joins_the_clean_side` — the leak is made
  *observable*, not merely counted: LOT-GHOST is carried only by never-scanned packages, so
  if one reached the clean side it would surface as "an unusually clean lot". Asserted
  absent in both modes.
* `test_a_kind_with_no_denominator_degrades_instead_of_inventing_one` — intersection still
  answers; clean buckets `null` not `0`; reason token; `undeterminable` ≠ `flat`.
* plus rescan/fan-out, cross-kind leak, absent relation, unknown kind, 4 bad windows.

```
14 passed  (ASSY_PG_TEST_DATABASE_URL=…/assy_qa, scratch schema, catalogue-verified drop)
```

### 3.2 Six defects injected — every alarm proven to ring

A guard I have never made fire is not a guard. Each was injected into the live source,
run, and the source restored **byte-identically** (binary read/write — this project has
been bitten by a harness silently rewriting to CRLF).

| injected defect | result |
|---|---|
| contrast keeps `flat` rows (returns everything) | **RED** |
| clean = universe − found (the never-scanned leak) | **RED** |
| kind stops being a parameter (methods hardcoded) | **RED** |
| no-denominator reported as `0` instead of `null` | **RED** |
| counts attribution rows instead of units | **RED** |
| attribution not narrowed to the kind's methods | **RED** |

🔴 **Defect 5 was GREEN on the first attempt, and the test was not at fault — my fixture
was.** It had exactly one run per package, so the fan-out axis was never active and
`count(*)` and `count(DISTINCT unit)` agreed. Insufficient mutation and a robust test look
identical from outside. I added a re-scan (every 5th package scanned twice by the same
recipe) and it went red.

### 3.3 Two real defects the live data found, that the unit tests would not have

1. **Cross-kind attribution leak.** `inspection_run` holds every method's runs, so
   attributing voids through it without narrowing pulled `SYN_DELAM_R1` — the
   *delamination* scanner's recipe — onto a `finding=void` answer, purely because the same
   packages had also been scanned for delam. Fixed by a declared
   `filter: {column: "method", values_from: "observed_by"}`; the narrowing follows the kind.
2. **Run fan-out double counting.** A package scanned N times produced N attribution rows.
   `count(*)` would report a numerator larger than its own denominator, on the one screen
   whose rule is that every rate carries one. Fixed with `count(DISTINCT unit_id)`.

---

## 4. Measured behaviour on `assy_manager` (100% synthetic — see banner)

```
found 46,899 | clean_scanned 28,101 | never_scanned 280,000 | scanned 75,000
universe 352,500 | scanned_outside_universe 2,500
```

* **`never_scanned` is 10× `clean_scanned`.** Had those 280,000 packages been folded in,
  every enrichment would be dragged toward 1 and every real factor would vanish. This is
  the whole reason the third bucket exists, and on this fixture it is the difference
  between an analysis and a blank screen.
* **`scanned_outside_universe: 2,500`** — runs against positions with no die
  (the fixture's own negative controls). Reported rather than absorbed: without it,
  `universe − scanned` under-reports `never_scanned` by exactly that many.
* **Decoy filter, live:** intersection returns 200 factor rows; contrast keeps **2** and
  drops **198**. Every dropped row is `flat` at 0.93–1.02, which is what an unbiased
  fixture should produce. The 2 survivors are the negative-control scan values
  (`SYN_VOID_NEG` / `SYN-SAT-NEG`): genuinely 100% found / 0 clean, correctly
  `absent_from_clean_population` with a finite `ci` lower bound of 375.
* **Kind switch works on live data.** `delam_obs` (9,000 rows) and 30,000 `scat` runs
  landed while I was building; `finding=delam` swings the denominator to `scat` and
  returns found 6,989 / clean 23,011 / never 322,500. Its contrast is empty — correct,
  because no factor is planted there yet.

**Latency** (this box, warm): void intersection 3.8 s, void contrast 3.8 s, 7-day window
2.4 s, delam 2.1 s. The `count(DISTINCT (a,b,c))` row-constructor form took **37 s** for
delam; replacing it with a dense `unit_id` integer brought it to 2.1 s. `GROUPING SETS`
means five axes cost one scan, not five.

**Not yet paid for at 10M rows:** `evidence_refs` uses `array_agg(...)[1:n]`, which is
O(population) in memory — the only such construct here. The O(1) fallback is `min`/`max`
of the ref column (two refs instead of five). Flagged, not fixed; no index work was in
scope.

---

## 5. Open / needs your ruling

1. **The duplicate three-way-split spelling** (§2) — mine vs `population_ctes()`.
2. **`observed` is still not in the ledger vocabulary.** This endpoint reads the
   relational tables; `PREDICATES` remains the frozen seven and I did not touch it —
   adding `observed` is a vocabulary ruling. The kind registry is where its `finding_kind`
   qualifier will be checked when it lands; nothing has to move then.
3. **No planted causal factor exists in `assy_manager` yet.** The generator plants none
   (equipment/recipe are deterministic functions of lot and slot). Until the answer-key
   lane plants one, the *live* screen will show an empty contrast for `void` — which is
   the honest answer, but the owner should be told it means "nothing is enriched", not
   "the feature is broken".
4. **Proposed lesson for `agent_workspace/memory/server-pm.md`:** *「비율의 순위는 표본
   크기를 태워야 한다」* — ranking by a bare ratio puts the noisiest rows on top, which is
   the opposite of what a surprise ranking is for. 100 per-lot rows at 1.8x, each carried
   by ~108 units, buried every real factor until ranking moved to the interval's lower
   bound. A ratio without its sample size is as unreadable as a rate without its
   denominator.
