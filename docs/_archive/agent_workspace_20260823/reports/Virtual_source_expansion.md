# Virtual source expansion — `processed_with` v0, `Recipe`, a second finding kind, and the answer key

**Lane:** server-pm · **Date:** 2026-08-14 · **Target:** `assy_manager` (owner's dev box)
**Status:** LANDED and PROVEN. Nothing committed, nothing pushed, `client2/**` untouched,
`:8080`/`:8081` not restarted. Living-doc sync delegated to `doc-keeper` (running).

---

## 1. Verdict first — the answer key passes in both directions, for both kinds

Run: `conda run -n assy_manager python server/scripts/seed_syn_process_ledger.py --prove`

```
=== ANSWER KEY :: finding=void ===
populations: found=46899  clean-scanned=28101  never-scanned=280001
PLANTED  recipe_rev@BONDING=SYN-RCP-BOND@5   cases  5781/46899 (0.123)  controls  1719/28101 (0.061)  ratio 2.015
DECOY    chamber@BONDING=CH-A                cases 32636/46899 (0.696)  controls 19594/28101 (0.697)  ratio 0.998
DECOY    eqp@MOLDING=SYN-MLD-03              cases 12601/46899 (0.269)  controls  7529/28101 (0.268)  ratio 1.003
DECOY    recipe@BONDING=SYN-RCP-BOND         cases 46899/46899 (1.000)  controls 28101/28101 (1.000)  ratio 1.000
DECOY    recipe_rev@MOLDING=SYN-RCP-MOLD@1   cases 46899/46899 (1.000)  controls 28101/28101 (1.000)  ratio 1.000
DECOY    step:BONDING=BONDING                cases 46899/46899 (1.000)  controls 28101/28101 (1.000)  ratio 1.000
VERDICT: PASS

=== ANSWER KEY :: finding=delam ===
populations: found=6989  clean-scanned=23011  never-scanned=322501
PLANTED  eqp@MOLDING=SYN-MLD-03              cases  4389/6989 (0.628)  controls  3663/23011 (0.159)  ratio 3.945
DECOY    chamber@BONDING=CH-A                cases  4849/6989 (0.694)  controls 16043/23011 (0.697)  ratio 0.995
DECOY    recipe_rev@BONDING=SYN-RCP-BOND@5   cases   705/6989 (0.101)  controls  2295/23011 (0.100)  ratio 1.011
DECOY    recipe_rev@MOLDING=SYN-RCP-MOLD@1   cases  6989/6989 (1.000)  controls 23011/23011 (1.000)  ratio 1.000
DECOY    step:MOLDING=MOLDING                cases  6989/6989 (1.000)  controls 23011/23011 (1.000)  ratio 1.000
VERDICT: PASS

=== MEASURED BEATS SETPOINT (class 2 > class 3) ===
wafers carrying both flavours: 149 | measured won: 149 | class-blind mutant disagreed: 149
VERDICT: PASS
```

**The generalization proof is the two cross-kind rows.** Each kind's planted factor appears
in the *other* kind's contrast as a decoy and comes out flat: void's factor scores 1.011 on
`delam`, delam's factor scores 1.003 on `void`. Switching the kind parameter finds each
kind's own factor and not the other's.

**The decoy that matters is `chamber=CH-A`.** 69.6% of the voided packages share it — the
exact shape of "5 of 6 findings share X" that an intersection view reports as a finding.
69.7% of the clean-scanned packages share it too, so the contrast kills it at ratio 0.998.
A contrast view that cannot kill this is not working, and this is the row to score it on.

---

## 2. What was planted, and how

| axis | value | drives | how the association was built |
|---|---|---|---|
| `recipe.rev` on `BONDING` | `SYN-RCP-BOND@5` on 250 of 2,500 wafers | **void** | assigned to the top decile by **already-measured** void incidence |
| `eqp` on `MOLDING` | `SYN-MLD-03` on 671 of 2,500 wafers | **delam** | assigned by a hash **independent** of void rate; findings then **generated** from it (p=0.55 vs 0.12) |
| `chamber` | `CH-A` on ~70%, `CH-B` on ~30% | nothing | hash, independent of both outcomes — **the decoy with teeth** |
| `eqp` on `BONDING` | `SYN-BD-01..04` | nothing | **read out of `bonding_log.bond_eqp`**, never invented |
| `step`, `step_family`, `recipe.id`, `SYN-RCP-MOLD@1`, `SYN-RCP-DIFF@2` | universal | nothing | 100% of both populations — the intersection decoys |

🔴 **Stated plainly, because it is a construction detail a reader could otherwise mistake
for a claim:** the two associations were built by opposite routes. `delam` runs
factor → outcome (findings generated from the moulding equipment). `void` runs
outcome → factor (the recipe revision assigned against void rates that were already on
disk), because the 91,756 existing voids were written by another script and today's brief
is **add-only**. Both associations are *real in the data*, which is all a contrast view can
ever see; scoring the detector against one of each route means neither construction is the
only one it has been tested on.

Rejected alternative, for the record: generating a fresh planted void population would
have had to *out-mass* 91,756 unplanted voids on the same wafers or the signal would have
been diluted to nothing — a much larger write, for a weaker fixture.

### The mechanism graph is honoured, not decorated

`SYN-RCP-BOND` rev4 → rev5 moves exactly two of six parameters: `pressure_MPa` 0.35 → 0.22
and `temp_C` 145 → 150. That is `PHYSICS_ONTOLOGY_SETUP` §4's `압력↓ → BLT↑ → void↑` edge
and §5-S2's "temp +5", so an `S2` diff view has both signal and noise to separate instead
of reporting "everything changed".

---

## 3. «Measured beats setpoint» — the design paying off, with the mutant that proves it

A wafer with an equipment log carries **two** `processed_with` atoms for the same step:

* `params_actual` — what the machine uttered → **class 2** (the default arm of `claim_class`)
* `params_setpoint` + payload flag `"inferred": true` → **class 3**
  (`ledger_trace.DEFAULT_RESOLVER_CONFIG["inference_payload_flag"]`, which already existed)

**Not one line of ranking code was written.** `ledger_trace.py` was not touched at all.

🔴 And the fixture is built so that **only the class can decide**, because a green that any
rule would produce proves nothing:

* the setpoint atom is written **first**, so its uuid7 sorts lower → rank level 3 favours it
* its `occurred_at` is **later** → rank level 2b favours it
* both `source_who` values are unregistered → `get_source_priority` is 99 for both → level 1 ties

`prove_class_decides` therefore runs a **class-blind mutant** (`claim_rank_key(...)[1:]`)
and requires it to *disagree*. Measured: 149 of 149 sampled wafers — measurement won every
time, mutant picked the setpoint every time.

---

## 3-bis. `transferred` v0 — the fourth leg, and the shape that survived three drafts

Added after the answer key landed, on the coordinator's DT instruction. **The instruction
arrived three times in three shapes; only the third was built.** Recording all three
because the first two are traps that read as reasonable:

| draft | shape | why it was wrong |
|---|---|---|
| 1 | `processed_with` with `step: DT`, one per wafer | models DT as a step a wafer **passes through**. It is not — some dies are picked, the rest stay. Would have needed re-uttering. |
| 2 | two claims: load (적재) + consume (소비), `consumed` registered | selection expressed stage-by-stage. Still stage-shaped; `consumed` would have been minted for something a transfer already says. |
| **3 — built** | **`transferred`**, one predicate for every movement (`PHYSICS_ONTOLOGY_SETUP` §2-bis, `4dff09f`) | selection **is** the event's existence; residual is a fold; `consumed` is absorbed and deliberately **not registered**. |

**Nothing from drafts 1–2 was wasted** — the `SYN-RCP-DT` recipe and the DT-conditions
atom survive as `processed_with`, standing **alongside** the movement events, because
conditions and movement are different claims about one run.

```
(Wafer core, transferred, {from:{type,keys,position}, to:{...}, qty, source_population?})
```

Emitted 65,279 movement atoms in three shapes — and the shapes are the proof the walk is
generic:

```
wafer_grid -> dt_slot      2,500    the pick (partial: source_population > qty)
dt_slot    -> dt_slot        279    the SECOND DT hop
dt_slot    -> package_gate 62,500   the bonding consume (qty MEASURED from bonding_log)
```

🔴 **Only the load side is planted; the consume side is counted.** Every die in
`bonding_log` already records which DT lot and slot it came from, so "how many dies went
from slot S into base wafer B" is a count over rows that exist (125–150 per pair,
measured). Nothing on disk says how many were *picked onto* the slot, and that gap is
what the selection model fills.

### The n-hop proof — the acceptance core

```
=== TRANSFER CHAIN :: package -> DT slot(s) -> core wafer ===
packages walked: 400 | reached the core wafer: 400
chains passing TWO dt slots: 125 | one dt slot: 275
a 'DT happens once' join would be WRONG on: 125 of them        VERDICT: PASS
```

The walk joins **event N's `to` to event N+1's `from`** and stops when nothing matches.
There is no hop count anywhere in it — the only integer is a cycle guard at 20. The
mutant is the load-bearing half: a join that took exactly one step back from the package
lands on a `dt_slot` instead of a `wafer_grid` on precisely the 125 three-hop chains. **On
a fixture where DT always happens once, both walks return the same answer and neither is
tested** — which is why `--double-dt-fraction 0` is documented as the setting that
destroys the discrimination.

### Residual as a fold

```
dt slot containers: 2,779 | containers with NEGATIVE residual: 0
  {dt_lot: SYN-DT-085, dt_slot: 16}  loaded=180 shipped=150 residual=30
```

Computed in SQL as inflow − outflow over `transferred` events only. **Never stored** — a
stored residual can disagree with the events it summarises and then nobody can say which
is wrong. 2,779 = 2,500 recorded slots + 279 staging slots. Zero negative, i.e. no
container ever ships more than it held.

### Idempotency, verified rather than assumed

Re-running `--apply` reported **`inserted=70284 deduped=13554`** — exactly the first run's
atom count deduped, nothing duplicated. That is not luck: adding `SYN-RCP-DT` to a
`sorted(RECIPES)` enumeration would have slid `SYN-RCP-MOLD` from index 3 to 4, changing
its `occurred_at`, its `identity()` tuple, and re-inserting every already-written MOLD
atom as a duplicate. `RECIPE_ORDER` is now explicit and **append-only** for that reason —
a sorted-order timestamp is an idempotency bug that only fires the day somebody adds a
member in the middle.

## 3-ter. Lot-level excursions (ruling R-2026-08-14-F) — BUILT, NOT RUN

🔴 **Condition 4 honoured: nothing was written.** `--apply` was fired *without* the flag to
prove the gate bites, and it refused. Verified after: `bonding_log` rows for lots 101–103
= **0**, excursion atoms = **0**, `cell_sources` under the marker = **0**.

### 🔴 A measurement that changes the ask — `found_rate` can never be coloured

Measured over all 100 lots, no window (`ledger_lots`' own metric definitions):

| aggregate | min | **median (baseline)** | max | max/median |
|---|---|---|---|---|
| `found_rate` | 0.5766 | **0.6124** | 0.6483 | **1.059** |
| `per_chip` | 1.1393 | **1.2248** | 1.3255 | 1.082 |
| `extent_mean` | 55.10 | **58.659** | 64.32 | 1.097 |

`found_rate` is `found chips / scanned chips` — **bounded by 1.0**. Against a 0.6124
baseline the largest ratio that column can *ever* show is **1.633**, and the first ladder
step is 2.0. **A lot where every single scanned chip has a void still renders uncoloured.**
That is a property of a saturating ratio judged against a mid-range baseline; no plant
fixes it. So the excursion is planted on the **unbounded** declared aggregates — `per_chip`
and `extent_mean` — and `found_rate` is declared unscorable in code with the arithmetic
pinned by a test that fails the day someone lowers the threshold below the ceiling.

⚠️ **I could not reproduce the brief's "최대 1.554배".** I measure max/median = **1.059**
for `found_rate` with no window. Both numbers are in the report rather than one being
silently adopted — the gap is probably a window or a different column, and it is worth
one minute from whoever produced 1.554 before the grid's baseline is trusted.

### What is planted, and why new lots

Three lots, **late in production order on the axis the grid actually sorts by** —
`ledger_lots._build` takes each row's time from `inspection_run.observed_at` and says in
its own comment that `bonding_log.event_time` is one identical string across all 352,500
synthetic rows and cannot order anything. So these lots are late because their *scans* are
late (day offsets 101–103), not because their names sort last.

| lot | per_chip | ÷ baseline | level | margin to next step |
|---|---|---|---|---|
| `SYN-VOID-101` | 2.818 | **2.30×** | 1 주의 | below 3.0 |
| `SYN-VOID-102` | 4.146 | **3.39×** | 2 높음 | below 4.5 |
| `SYN-VOID-103` | 6.090 | **4.97×** | 3 심각 | below 6.0 |

Graded so the **ladder itself** is exercised, not one step of it. `found_rate` lands at
0.880 / 0.931 / 0.945 — ratios ~1.44–1.54, still uncoloured, which is the saturation
finding demonstrated rather than argued.

🔴 **New lots rather than more voids on lots 098–100, and the reason is a contradiction.**
Every existing wafer already carries a `processed_with` atom naming its bonding revision.
Giving an excursion a *cause* on those wafers would assert a second, different revision for
a run the ledger has already described — append-only keeps both, the later wins by rank,
and that is a **correction**, a completely different claim from "a new revision rolled out
late". New lots have no history to contradict. It also makes condition 2 far stronger: the
100 existing lots are **untouched**, so "unplanted lots do not light up" holds by
construction rather than by re-measuring and hoping.

**The cause connects (condition 1):** every excursion wafer bonds under **`SYN-RCP-BOND` rev 6**
— a value in the *same* factor namespace the case-control contrast already scores
(`recipe_rev@BONDING`). So grid → reference view → contrast is scorable end to end, and
`prove_cause_connects` runs the existing `contrast()` to check it. Projected enrichment
once applied: ~2,050 cases / ~125 controls → **ratio ≈ 9.5**, with the existing rev5 factor
diluting only from 2.02 to ~1.94 (still over its declared 1.5 floor). rev6 also gives S2 a
second real diff: pressure 0.22 → 0.16, time 12 → 9, four parameters unchanged.

### Both directions, and the bug the second one catches

`server/tests/test_lot_excursion.py` (8 passed) replaces `lot_table` with a synthetic
100-lot table, so the ruling is scorable **without** the database:

- planted lots reach their declared levels;
- 🔴 a **rogue normal lot at 2.5×** must be reported — this is the only assertion standing
  between "the grid works" and "the grid colours everything";
- absence is **PENDING, never a vacuous PASS** (which is what `--prove` prints today);
- the trend break must land at the **end** of the series (a planted lot dated early fails);
- `found_rate`'s ceiling is pinned against the live threshold list.

**The self-consistency test found a real bug in my own declaration**: lot 101 declared
level 1 with `expect_min_ratio` 1.8 when the step is 2.0, and lot 103 declared level 3 with
4.2 when the step is 4.5. The answer key would have failed for a reason having nothing to
do with the data. Corrected to 2.0 / 3.0 / 4.5 with ~13% generator margin.

### To run it, once the owner approves

```
conda run -n assy_manager python server/scripts/seed_syn_lot_excursion.py --apply --i-accept-writing-to-owner-database
conda run -n assy_manager python server/scripts/seed_syn_lot_excursion.py --prove
# then, to extend the DT transfer chain onto the new lots (idempotent for everything else):
conda run -n assy_manager python server/scripts/seed_syn_process_ledger.py --apply --i-accept-writing-to-owner-database
```

Would add: 10,575 `bonding_log`, 2,175 `inspection_run`, 9,464 `void_obs`, 75
`wafer_map_metadata`, 232 atoms.

**Rollback:** `updated_by = 'seed_syn_lot_excursion'` (`cell_sources`/`cell_overwrites`);
`ledger_events WHERE source_translator_ver LIKE 'syn_lot_excursion/%'`;
`bond_lot IN ('SYN-VOID-101','SYN-VOID-102','SYN-VOID-103')`;
`base_wafer_id LIKE 'SYN-BW-1__-%'` for runs and voids.

## 4. The three-way split is real, and cannot silently collapse

`server/finding_kinds.population_ctes(kind)` is the **one** spelling of the split:

```
kind_clean AS (SELECT ... FROM kind_scanned EXCEPT SELECT ... FROM kind_found)
```

🔴 `clean` is `scanned MINUS found`, **never** `NOT EXISTS(finding)`. On this box the
difference for `void` is **280,001 packages** — the wrong spelling would report every
never-scanned position as "looked at and fine", making the console's central claim false
for 91% of the rows supporting it with nothing on screen admitting it.
`test_finding_kinds.py::test_clean_is_scanned_minus_found_and_never_absence_of_a_finding`
fails on that mutation.

⚠️ **One measured wrinkle worth knowing:** the never-scanned population is computed over
**all** of `bonding_log`, not just the synthetic fixture, so it includes ~2,501 distinct
positions from the 5,296 real bonding rows (46,899 + 28,101 + 280,001 = 355,001 vs 352,500
synthetic positions). That is correct behaviour — those really are packages nobody scanned
— but a screen that quotes "352,500 packages" will disagree with it by 2,501.

---

## 5. No hardcoded kind — the trap, and where it is held shut

`server/finding_kinds.py` is the registry. `DEFAULT_KIND = "void"` is the **only** place a
kind name appears as a literal in code, and it is a default parameter value.

* `observed_by` **is** the denominator's definition (`inspection_run.method` values).
* An **empty** `observed_by` means "no systematic scan → no denominator"; `has_denominator()`
  is how a caller asks, so the console can render 「분모 없음 — 대조 불가」 as content.
  An **absent** key is a load-time refusal — absent ≠ empty.
* `spec()` **refuses** an undeclared kind rather than defaulting to `void`. A misspelled kind
  in a URL rendering void's numbers under the wrong heading is the one failure a reader
  could never notice.
* `test_switching_kind_actually_switches_the_denominator` pins that no two kinds share a
  method. If both kinds counted against `sat` runs, a hidden `WHERE finding_kind='void'` in
  the *denominator* would pass every test anyone wrote.

**For the G1 lane:** call `finding_kinds.population_ctes(kind)` and bind `:methods` from
`finding_kinds.methods(kind)`. Do not re-spell the split.

---

## 6. Files

| file | change |
|---|---|
| `C:\Users\kk980\Developments\assyManager\server\ledger\vocabulary.py` | **MODIFIED** — `Recipe` entity type (`keys: ["recipe","rev"]`, issued); `processed_with` + `has_param` + **`transferred`** predicates (`since: 2`, seven words → **ten**); `Recipe` added to `register`/`pin`/`same_as` subjects; `check_signature` now enforces `{"kind":"value","required":[...]}` |
| `C:\Users\kk980\Developments\assyManager\server\finding_kinds.py` | **NEW** — the kind registry and the single spelling of the three-way split |
| `C:\Users\kk980\Developments\assyManager\server\scripts\seed_syn_process_ledger.py` | **NEW** — generator + `--prove` answer key |
| `C:\Users\kk980\Developments\assyManager\server\scripts\seed_syn_lot_excursion.py` | **NEW** — lot excursions (R-2026-08-14-F). **Built and dry-run only; not applied.** |
| `C:\Users\kk980\Developments\assyManager\server\tests\test_lot_excursion.py` | **NEW** — 8 tests, both directions, no database needed |
| `C:\Users\kk980\Developments\assyManager\server\tests\test_finding_kinds.py` | **NEW** — 7 tests |
| `C:\Users\kk980\Developments\assyManager\server\tests\test_ledger_l1_unit.py` | **MODIFIED** — the seven-word pin now records the nine-word ruling (name unchanged, deliberately); 2 new tests |
| `C:\Users\kk980\Developments\assyManager\server\config\table_config.json` | **MODIFIED** (gitignored operator config) — `delam_obs` declared |
| `C:\Users\kk980\Developments\assyManager\server\config\table_config.json.sample` | **MODIFIED** — same declaration, surgically inserted (+38 / −0; a full re-dump was reverted because it reformatted 26 unrelated lines) |

Untouched: `server/map_alignment.py`, `server/migrations/**`,
`server/config/map_overlay_config.json*`, `server/ledger_trace.py`, `client2/**`.

### Tests

```
server/tests/test_ledger_l1_unit.py test_ledger_trace.py
  test_ledger_trace_contract.py test_void_base_join_fixture.py   162 passed
server/tests/test_finding_kinds.py                                 7 passed
```

`test_every_declared_derivation_is_explicitly_classified` was checked deliberately: it
enumerates derivations from `ledger_config.json.sample` for source `lot_event` only, so the
generator's four derivations (declared in the script, not in operator config) do not reach
it. This is why the generator declares its own derivations rather than adding a bogus
source to `ledger_config.json` — `ledger_config.validate` requires `columns.lot`/
`event_type`/… which a generator has none of.

---

## 7. Rows added, and the rollback predicate

| target | before | added |
|---|---|---|
| `ledger_events` | 909 | **83,838** (→ 84,747). `transferred` 65,279 · `processed_with` 13,530 · `register` 5,250 · `has_param` 24. New partition `ledger_events_2026_08`. |
| `ledger_translator_cursor` | 1 row | **1 row** (`syn_process_ledger`, 10,004 molecules) |
| `inspection_run` | 77,500 (`sat`) | **30,000** (`scat`) |
| `delam_obs` | table did not exist | **10,421** |
| `cell_sources` | 21,202,816 | **395,052** (`updated_by = 'seed_syn_process_ledger'`) |

Nothing existing was updated, trimmed or vacuumed. Two `--apply` runs: the first wrote
13,554 atoms (0 deduped), the second wrote 70,284 and **deduped exactly the first 13,554**.
`inspection_run` stayed at 30,000 `scat` rows and `delam_obs` at 10,421 across both runs —
no duplication. Write time 87.5 s + 59.8 s.

### 🔴 Rollback predicate

```sql
DELETE FROM ledger_events            WHERE source_translator_ver LIKE 'syn_process_ledger/%';
DELETE FROM ledger_translator_cursor WHERE source = 'syn_process_ledger';
DELETE FROM delam_obs                WHERE run_uid LIKE 'scat|%';   -- i.e. all of it
DELETE FROM inspection_run           WHERE method = 'scat';
DELETE FROM cell_sources             WHERE updated_by = 'seed_syn_process_ledger';
DELETE FROM cell_overwrites          WHERE updated_by = 'seed_syn_process_ledger';
```

`source_translator_ver` is the ledger marker and **not** `source_who`: `source_who`
deliberately varies (`syn_eqp_log` vs `syn_recipe_book` — an equipment log and a recipe
book are different utterers and the fixture needs them to be), so it cannot also be the
fixture's boundary. Reverting the config is `delam_obs` out of `table_config.json` +
`.sample`; the physical table can stay empty or be dropped separately.

---

## 8. Open items for the lead PM

0. 🔴 **`delam_obs` has no `uq_bk_delam_obs` unique index, and I did not create one because
   the brief says "no index work. Not today."** `server/scripts/audit_schema_canon.py` R2
   now reports exactly one violation and it is mine: 19 declared tables have a valid unique
   index on `business_key_val`, `delam_obs` does not. `create_missing_dynamic_tables` builds
   the table but not that index — `void_obs` got its from
   `server/migrations/add_void_schema_indexes.sql`.
   **Not an active defect today** (measured: 10,421 rows, 10,421 distinct
   `business_key_val`, 0 NULL), but it is the *second* net: `apply_batch_updates`'s
   duplicate-recovery guard fires on `IntegrityError`, which cannot happen without the
   index, so a future duplicate would land silently. One statement, and it is your call:
   ```sql
   CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uq_bk_delam_obs
       ON delam_obs (business_key_val);
   ```
   ⚠️ Another lane holds `server/migrations/**`, so the migration file that should carry
   this is not mine to write either.
1. **`database_outbox` holds 574,693 unprocessed rows and nothing is draining it.**
   Attributed by measurement, not by assumption: 524,258 of them are `bonding_log` 352,500
   + `inspection_run` 77,500 + `void_obs` 91,756 + `wafer_map_metadata` 2,502 from the
   **08:00 seeding of the base fixture** (another lane, this morning). My run contributed
   **40,421** (`inspection_run` 30,000 + `delam_obs` 10,421). **Pre-existing condition, not
   created by this lane**, and out of scope today (no DB housekeeping) — but somebody should
   decide before the console goes live, because the same processor feeds the WS broadcast.
2. **The running `:8080` will not serve `delam_obs`** until its config snapshot is reloaded.
   Not restarted, per instruction. `create_missing_dynamic_tables` created the physical
   table; `/admin/reload-configs` is the CREATE-only path if a reload is wanted without a
   restart.
3. **What did NOT ship from `PHYSICS_ONTOLOGY_SETUP`:** `BondLine` (the M1 composed entity)
   and the M2 physical-quantity dictionary. `chamber` shipped as a **payload field**, not as
   a declared entity. MI `measured` facts were not added — the brief's five items did not
   list them and the ordering line did; flagging the ambiguity rather than deciding it.
4. 🔴 **`population_ctes` is NOT the only spelling of the population split, and I said it
   was.** `server/ledger_siblings.py` (tracked, landed, another lane) assembles its own
   `runs`/`scanned`/`found` and mentions `population_ctes` only in prose. It has a real
   reason — the console scopes runs to a time window and must define `found` *through*
   those windowed runs to keep `found ⊆ scanned` — so "merge them" is the wrong
   prescription. The honest statement, now in both docstrings: **two spellings exist, they
   agree today, and nothing detects the day they stop.** Someone has to decide where the
   window belongs. Found by `doc-keeper`, not by me; my original claim was repeated from a
   docstring without grepping for callers.
5. **`step`'s "closed value set" never shipped.** `PHYSICS_ONTOLOGY_SETUP` §2 asserts it
   as designed; `check_signature` only requires `step` to be *present* and accepts any
   string. The enumeration lives solely in `seed_syn_process_ledger.STEPS` and nothing
   enforces it, so a typo'd step is born as a new step, silently. Same class of hole one
   axis over: `transferred`'s `from.type`/`to.type` container kinds are also unenforced
   strings today.
6. **The vocabulary rulings are not in `LEDGER_RULINGS.md`** — that document's own rule is
   that a ruling not recorded there was never made. It is ontology-pm owned, so neither I
   nor doc-keeper edited it. Three rulings landed today (`processed_with`, `has_param`,
   `transferred`) and `SCENARIO_CONSOLE_BRIEF.md` has no ownership row either. Routing call.
7. **`docs/history/` entry not written** and `gen_index.py` not run, because other lanes are
   live and the history index is a shared file. Draft below for the batch.
8. **Time, stated plainly:** the DT leg was quoted at 30 minutes for one `processed_with`
   row. It became three model revisions and a new predicate, and ran well past that. The
   escape hatch was not taken because the second correction changed the reduction
   direction to "fewer events, not a simpler model" — so the model is complete and the
   event count is the aggregate one (`qty` per container move, 65,279 atoms) rather than
   one atom per die (which would have been ~705,000).

### History entry draft

> **A chip's every movement becomes one word, and the fixture is built so a shortcut fails.**
> `transferred` (§2-bis) replaced two earlier drafts of the same fact in one afternoon —
> DT as a step a wafer passes through, then DT as separate load and consume claims. Both
> would have had to be re-uttered, and the vocabulary count is what caught each one: the
> test that pinned seven words failed three times today and now records why there are ten.
> Selection is the event's existence, residual is inflow minus outflow, and the reserved
> `consumed` is absorbed rather than registered. The part that had to be *engineered* is
> the fixture, not the walk: a tenth of the DT slots are reached through a second DT slot,
> because on a fixture where DT happens once a position-continuity walk and a step-name
> walk return the same answer and neither is tested. 125 of 400 walked chains are three
> hops, and the single-hop shortcut is wrong on exactly those 125.
>
> **`processed_with` opens, and the recipe revision becomes a subject rather than a field.**
> The ledger could record that a package had a void and could record nothing about the
> conditions that made it, so every causal question died at the first hop. The reserved
> predicate is opened (seven words to nine — a ruling, written down in the test that
> guarded seven), `Recipe` joins the issued entities with `rev` **in the subject key** so a
> revision is a registration and rev4's evidence survives rev5, and a second finding kind
> arrives so that `finding=<kind>` is a parameter somebody has actually changed. The part
> worth keeping: **«measured beats setpoint» required no new code.** A setpoint-derived
> claim carries the payload flag the resolver already reads and lands at class 3; a machine's
> utterance lands at class 2; `claim_rank_key` seals every tiebreak inside the class. The
> fixture is built so the setpoint wins on *every other level* — newer, lower id, equal
> source rank — and a class-blind mutant resolver picks it on 149 of 149 wafers. The class
> boundary is doing the work, and that is measurable rather than asserted.

### Proposed lesson for `agent_workspace/memory/server-pm.md`

- **함정**: 대조(case-control) 픽스처에서 「난 쪽에 흔한 요인」을 심고 만족한다. 그러면
  **모든 보편 요인이 미끼가 아니라 정답처럼 보인다** — 이 픽스처의 `chamber=CH-A`는 보이드
  패키지의 69.6%가 공유하고, **깨끗한 패키지의 69.7%도 공유한다**. 교집합 뷰는 둘을 구별
  못 한다.
  **올바른 방법**: 미끼는 **양쪽 모집단에 같은 비율로** 심고, 정답지는 **비율(ratio)**로
  단언한다. 그리고 **kind가 둘이면 서로의 정답을 상대의 미끼 목록에 넣어라** — 「전환하면
  각자 것만 나온다」가 그때 비로소 측정된다.
- **함정**: 클래스·우선순위 체계가 「자동으로 이긴다」고 보고하는데, 픽스처의 두 후보가
  **다른 모든 레벨에서도 같은 답**을 낸다. 그러면 초록은 계급이 아니라 동점 규칙이 낸 것이고
  아무것도 증명하지 못한다.
  **올바른 방법**: 지는 쪽이 **하위 레벨 전부에서 유리하도록**(더 최신·더 작은 id·같은 소스
  서열) 픽스처를 짜고, **그 레벨을 제거한 변이 해결기**가 반대 답을 내는 것까지 단언한다.
  (여기서는 149/149 전원 불일치.)
