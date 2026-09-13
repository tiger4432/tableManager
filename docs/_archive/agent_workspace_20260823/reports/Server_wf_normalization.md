# Server — WF notation normalization, PHASE 1 (board request 8)

**Status:** implemented, tested, **not committed** (working tree; three other lanes are
live in this tree — lead PM reviews the diff and commits).
**Suite:** `2030 passed, 2 skipped` at the moment my change landed (baseline 2007 + 2;
**+23 net new**, zero regressions). `conda run -n assy_manager python -m pytest
server/tests/ -q`, from repo root, one pytest repo-wide (checked `Win32_Process` first —
only the 5-process decoupled server was running).

⚠️ **A confirmation re-run 6 minutes later reported `2 failed, 2052 passed, 2 skipped`.**
Both failures belong to another lane that is editing the launcher in this shared tree,
and neither touches anything of mine — stated with the evidence rather than as a claim:

- `test_duplicate_launcher.py::test_operator_lines_survive_the_production_console` —
  `server/process_supervisor.py:13` contains an em-dash the cp949 console cannot encode.
- `test_process_supervisor.py::test_launcher_declares_a_heartbeat_for_every_worker` —
  `run_decoupled_app.py` spawns `run_graph_sync.py` with no `heartbeat="graph"`.

Both named files are in the `git status` modified set and are **not** files I touched;
the run also grew by 22 tests between the two runs, which is that lane landing work.
My 23 tests are green in both runs.

---

## 1. The census was not needed — and it is now RUN, and it is CLEAN

The brief said to skip the standalone census because the raw column stays untouched.
That held. But once the fold function existed, running the false-merge check cost one
read-only script, so it was run against the live database rather than left as a promise.

**`dt_log.core_lot` — 30 distinct raw spellings fold to 15 under R1+R2, in 15 groups:**

```
MERGE CL-2601-001            <- CL-2601-001(1137) | CL_2601_001(130)
MERGE CL-2601-002            <- CL-2601-002(409)  | CL_2601_002(43)
MERGE CL-2601-002-A4         <- CL-2601-002-A4(385) | CL_2601_002_A4(46)
MERGE CL-2601-003            <- CL-2601-003(921)  | CL_2601_003(108)
MERGE CL-2601-004            <- CL-2601-004(908)  | CL_2601_004(95)
MERGE CL-2601-005-A5         <- CL-2601-005-A5(778) | CL_2601_005_A5(97)
MERGE CL-2601-006            <- CL-2601-006(657)  | CL_2601_006(70)
MERGE CL-2601-006-A1         <- CL-2601-006-A1(56) | CL_2601_006_A1(4)
MERGE CL-2601-006-A1-A7      <- CL-2601-006-A1-A7(137) | CL_2601_006_A1_A7(19)
MERGE CL-2601-007            <- CL-2601-007(11)   | CL_2601_007(3)
MERGE CL-2601-007-A2         <- CL-2601-007-A2(34) | CL_2601_007_A2(5)
MERGE CL-2601-007-A2-A3      <- CL-2601-007-A2-A3(158) | CL_2601_007_A2_A3(23)
MERGE CL-2601-007-A2-A6      <- CL-2601-007-A2-A6(105) | CL_2601_007_A2_A6(12)
MERGE CL-2601-007-A2-A6-A8   <- CL-2601-007-A2-A6-A8(334) | CL_2601_007_A2_A6_A8(40)
MERGE CL-2601-008            <- CL-2601-008(644)  | CL_2601_008(71)
```

Every group is **the same token sequence spelled two ways**. There is not one
questionable merge. 766 rows carry the `_` form — the number the brief quoted.

**And every other lot/slot column measured has ZERO merge groups:**

| column | rows | distinct raw | distinct after R1+R2 | merge groups |
|---|---|---|---|---|
| `dt_log.core_lot` | 7,440 | 30 | **15** | **15** |
| `dt_log.dt_lot` | 5,651 | 6 | 6 | 0 |
| `dt_log.core_slot` | 7,440 | 34 | 34 | 0 |
| `core_wafer_map.core_lot` | 24,200 | 8 | 8 | 0 |
| `bonding_log.bond_lot` | 5,296 | 5 | 5 | 0 |
| `bonding_log.dt_lot` | 5,296 | 10 | 10 | 0 |
| `lot_event.lot` | 43 | 24 | 24 | 0 |

That is the strongest form the answer could take: R1+R2 is a **no-op everywhere except
the exact column that was reported**, and there it merges exactly the dash/underscore
pairs. Read-only, no DDL, no writes.

### The ready-to-run false-merge query (per the brief)

Once a pair is declared and derived, the check is one query per column — no XMLTABLE,
no `query_to_xml`, nothing that errored in your environment:

```sql
SELECT core_lot_norm,
       count(DISTINCT core_lot)                                    AS n_raw_spellings,
       string_agg(DISTINCT core_lot, ' | ' ORDER BY core_lot)      AS variants,
       count(*)                                                    AS n_rows
FROM   dt_log
WHERE  core_lot_norm IS NOT NULL
GROUP  BY core_lot_norm
HAVING count(DISTINCT core_lot) > 1
ORDER  BY n_raw_spellings DESC, n_rows DESC;
```

Read the `variants` column and ask *"are these the same physical lot?"*. If even one
group says no: edit `config/notation_rules.json` and re-derive. It is also copied into
`notation_rules.json.sample` under `__false_merge_check` so it is findable without this
report.

---

## 2. What `canonical_key_value` (7b) already folded

`server/map_overlay.py:117`. Measured by reading it, not assumed:

| input class | what 7b already does |
|---|---|
| `number`-declared column | integer parse — `'01'`, `' 1 '`, `1.0`, `'1.0'` all → `'1'`; `'7.5'` kept; unreadable value keeps its trimmed original (the lookup misses honestly) |
| `string` / undeclared | **trim only** — padding in a string is data, per spec |
| a float VALUE, any declared type | integral floats lose the `.0` repr artifact |

**It does not fold separators and does not fold case.** So R1/R2 are genuinely new work,
not a re-spelling. The reconciliation is **layering, not replacement**:

```
normalized = fold_notation(canonical_key_value(raw, declared_type), rules)
```

`canonical_key_value` keeps deciding what the value **is** (by its declared type); this
module decides only how its notation is **spelled**. One vocabulary, two layers, and
`canonical_bind_value` is imported at module level in `notation_norm` so there is
provably no second copy.

A consequence worth naming: **7b's integer parse already is zero-pad stripping for
`number` columns**. Combined with your separate ruling that `slot` is always int, the R3
question is retired for slot *by reuse* rather than by a new rule —
`test_a_number_declared_column_is_folded_by_canonical_key_value_alone` pins it.

---

## 3. The rule toggles

| rule | ships | what it does |
|---|---|---|
| `separator` | **true** | runs of `.` `_` `-` whitespace → a single `-` |
| `case` | **true** | upper-case fold |
| `zero_pad` | **false, and refused if set true** | not implemented |

Each is its own independent branch in `fold_notation` — `{}` returns the input
untouched, which is what makes "prove each rule toggles alone" a real test.
`test_separator_rule_alone` / `test_case_rule_alone` / `test_both_rules_and_neither`
score the pure function; `test_a_column_can_override_the_file_level_rules` scores two
columns of **one row** through the real write path with different rule sets, so a bug
that applied one global rule set to everything cannot pass.

Rules can be declared file-wide, per table, or per column (`{"derived": ..., "rules":
{...}}`).

### 🔴 zero_pad is refused BY NAME, not silently ignored

`"zero_pad": true` produces a named rejection (`zero_pad_unimplemented`), forces the
value back to `false`, and surfaces in `GET /admin/config/resolve?domain=notation`.
A knob that reads as ON and does nothing is the exact silence this repo keeps paying
for. `"zero_pad": false` is **not** a rejection — "declared false" is a decision on the
record (the `auto_confirm_declared` distinction).

`test_zero_padding_is_NOT_folded_in_a_string_column` pins the practical meaning:
`WF010` and `WF10` stay two derived values.

### Where the separator target differs from the census SQL

`wf_spelling_census.sql` writes the class as `[._[:space:]]+ -> '-'`. I use
`[._\-\s]+ -> '-'`, i.e. `-` is inside the class. On the reported pair the two are
identical (`WF.01` and `WF-01` both reach `WF-01`); the difference is only that mixed or
repeated runs (`WF--01`, `WF-_01`) also collapse. Strictly more folding, and the live
measurement above was taken with the implemented rule, not the census one.

Two folds I deliberately did **not** add, so they are decisions and not omissions:
edge separators are not stripped (`WF01-` stays distinct from `WF01`), and interior
runs are collapsed but not removed.

---

## 4. Mechanism — and why it is NOT a chain rule

The brief pointed at the `dt_log_to_dt_map` chain-rule precedent. I did not use it, and
the two traps it warned about are the reason:

1. **A chain rule needs a mapper module on disk, and `server/mappers/*.py` is gitignored
   user territory** (board O7: a rule can point at a module that is not there and pass
   every gate). A chain-based derivation would ship as a `.py.sample` and be dead on
   arrival until the operator copied it — a silent no-op by construction.
2. **A chain writes to a `target_table`.** The derived value belongs in the *same row*
   as its raw value, so the rule would need `trigger_table == target_table`. That does
   not infinitely recurse (`process_chain_transaction_group` filters events whose
   `source_name` is `chain_ingestion`, `chain_ingestion_worker.py:380`) — but it would
   **double every write on the hottest table**, replaying 10M rows through the full
   layering machinery to set a projection.

**The purge trap does not apply either way** and neither does it here: the derived
column lives in the row it derives from, so there is no stale row to delete. Nothing in
this design inherits "can upsert but cannot purge".

What I used instead is the *other* precedent in this repo, and the closer one — **the
write boundary** (`crud.normalize_stored_text` / `cast_value_by_type`, whose own
docstring is titled *THE WRITE BOUNDARY*):

- **`server/notation_norm.py`** (new) — the fold, the loader, the derivation hook, and
  the re-derivation. TTL-cached spec (5.0s) with an explicit `reset_cache()`, exactly
  mirroring `virtual_join_executor` — explicit invalidation for the web server, TTL for
  the worker processes that never reach the hook.
- **`crud.apply_row_update_internal`** — after the value loop and after the audit block,
  each declared derived column is recomputed **from the value that WON the priority
  computation**, not from one source's contribution. So the derived column mirrors what
  the row shows. A derivation failure is logged and swallowed: the raw value is the
  record, the projection is repairable.
- **`crud.refuse_notation_derived_columns`** — a write aimed at a derived column is
  refused for every write path, called from `apply_batch_updates` beside
  `refuse_virtual_join_columns` (the one funnel a new call site cannot forget).

### 🔴 The safety property is enforced in three places, not asserted in a comment

1. `_validate_column` refuses `derived == raw` → `would_rewrite_raw`.
2. `_validate_column` refuses a derived column that is the `business_key` or a member of
   `composite_key_source` → `key_column`. A derived value can never move row identity.
   (The **raw** column may be a key member — `core_wafer_map.core_lot` is one.)
3. The write guard above.

Plus: `_validate_column` refuses a derived column that is not declared `"string"` (a
`number` column would refuse `'WF-01'` outright), and refuses undeclared tables/columns.

---

## 5. Re-derivation — the proof

`notation_norm.rederive(db, table, spec, apply=False)` +
`server/scripts/rederive_notation_norm.py` (dry-run by default, `--apply` to write,
`--table` to scope, `--chunk-size`).

`test_rederivation_changes_the_answer_with_no_manual_cleanup` is the whole argument in
one test: write three rows under `separator+case`, flip `case` off, re-derive, and

- the dry run reports `scanned=3 changed=1` and **writes nothing** (asserted);
- `--apply` lands the new answer (`WF-02` → `wf-02`);
- **every raw value is byte-identical afterwards** (asserted);
- running it again reports `changed=0` (idempotent);
- **no manual cleanup at any step.**

`test_rederivation_fills_rows_written_before_the_declaration` covers the other
direction: rows written before a declaration existed are filled by the same command —
that is how an operator switches a column on.

**10M-row discipline:** keyset pagination on `row_id` (the dynamic tables' PK), never
OFFSET; three columns fetched, not the row; writes emitted as `bulk_update_mappings`
carrying only `{row_id, <derived>}` so the UPDATE statement **does not even mention the
raw column**. It deliberately does not route through `apply_batch_updates` — that path
would refuse the write, and layering a pure projection would mint one `CellSource` row
per cell (10M metadata rows for a value with no sources to arbitrate). The script issues
**no DDL** (no `create_all`) — a repair tool must not be able to change the schema it
repairs.

---

## 6. Evidence, item by item

| the brief asked for | where |
|---|---|
| **Red first** — a `_`-bearing value shreds the map key today | `test_a_lot_containing_underscore_shreds_the_map_key_today`: `map_key_parts({"key_columns":["lot","slot"]}, "CL_2601_001_09_5")` returns `{lot: "CL", slot: "2601_001_09_5"}`, asserted as the *current* behaviour so it stays true after this round |
| **After** — the derived value composes correctly | `test_the_derived_value_composes_the_map_key_correctly`: `CL_2601_001_09` → `CL-2601-001-09`, joined with `_5`, parses back as the intended pair |
| **After** — raw byte-identical | `test_the_raw_column_is_byte_identical_after_derivation` (7 mixed spellings through the real write path) |
| **Re-derivation** | §5 above |
| **Each rule toggled independently** | §3 above, pure function *and* write path |

### Defect injection — actually run, not claimed

Per the server-pm lesson (*a test that never executes the new lines certifies nothing*).
Counts below are measured output, and the test module docstring carries them:

- **Injection A** — `fold_notation` returns its input unchanged: **9 RED**.
- **Injection B** — `apply_derivations` returns `[]` without setting anything: **5 RED**
  (the pure-function tests stay green, and so does the `rederive`-direct test — which is
  precisely why both halves are tested separately).
- **Injection C** — `_validate_column` drops the `derived == raw` refusal: **1 RED**, and
  that single assertion is the guard for the entire safety property.

Each injection was reverted by hand (`git checkout --` does not apply — the file is
untracked) and the suite re-run green.

---

## 7. Visibility: "did my config take?"

New domain `notation` in `GET /admin/config/resolve` (`config_resolve_report.py`,
one resolver + one registry line, no DB queries — the domain's contract). It answers two
different questions in the operator's own sentence:

- **effective**: `dt_log.core_lot`'s normalized notation is written to `core_lot_norm`,
  with the rules in effect named, *and* "지금은 이 값을 읽는 코드가 아직 없습니다(1단계)".
- **rejected**: every refusal with a Korean lead sentence saying what to fix.

`test_the_resolve_report_names_the_declaration_and_says_nothing_reads_it` pins both,
including that every operator-facing string is cp949-encodable.

---

## 8. Files

**New**
- `C:\Users\kk980\Developments\assyManager\server\notation_norm.py`
- `C:\Users\kk980\Developments\assyManager\server\config\notation_rules.json.sample`
- `C:\Users\kk980\Developments\assyManager\server\scripts\rederive_notation_norm.py`
- `C:\Users\kk980\Developments\assyManager\server\tests\test_notation_normalization.py`

**Modified** (`git diff --stat` = 184 lines, **insertions only**, so no other lane has
touched these three):
- `C:\Users\kk980\Developments\assyManager\server\database\crud.py` (+63) — the
  derivation hook and the write refusal
- `C:\Users\kk980\Developments\assyManager\server\config_resolve_report.py` (+112) — the
  `notation` domain
- `C:\Users\kk980\Developments\assyManager\server\main.py` (+9) —
  `notation_norm.reset_cache()` on the config-reload hook

**Not touched:** `client2/`, `docs/`, `server/config/*.json` (live user config — only the
`.sample` was written), no DDL, no DROP, nothing pushed.

**Ships inert.** `notation_rules.json.sample` declares `"columns": {}`. Until the
operator (1) adds a `"<col>_norm": "string"` column to `table_config.json` and lets the
ALTER run, and (2) declares the pair, nothing derives and nothing is refused
(`test_nothing_is_derived_when_nothing_is_declared`).

---

## 9. What PHASE 2 must decide

Phase 1 gives you a correct, re-derivable value that **nothing reads**. Phase 2 is not
"turn it on" — it is these five decisions, and each one is a separate round:

1. **The map-key cutover is a data migration, not a config flip.** `wafer_map_metadata`
   rows are registered under the *raw* identity (`compose_map_id` joins raw values with
   `_`). The moment `canonical_map_key` / `build_key_filters` read the normalized value,
   every existing `map_id` string stops matching its meta row and **maps stop
   resolving**. So phase 2 must decide: re-register the meta rows under normalized
   identities (and what happens to the ones nobody re-registers), or keep composing from
   raw and normalize only the *filter* side, which reintroduces the mismatch 7b exists to
   prevent. There is no arm of this that is a one-line switch.
2. **Which side of a join normalizes.** Joining `dt_log.core_lot_norm` to
   `core_wafer_map.core_lot` is a type error waiting to happen; both sides need the
   derived column, which means both tables need the ALTER, the declaration, and a
   backfill *before* any consumer is switched. Note the measurement above:
   `core_wafer_map.core_lot` has **zero** merge groups, so the two sides do not fold
   symmetrically — normalizing only one side would silently drop matches.
3. **Whether `virtual_join_rules` should point at `_norm` columns**, and if so, that the
   UNIQUE index the gate requires must be built **on the derived column** — which means
   the index has to be created after the backfill, not before.
4. **What the grid shows.** A derived column is an ordinary declared column, so today it
   would appear in the AG-Grid column set and in the row payload
   (`main.py` builds `user_cols` from `column_types`). Phase 2 should decide whether
   `_norm` columns are hidden by default; that is a Client PM call, not mine.
5. **Whether `zero_pad` gets implemented at all.** With the census now run and clean for
   R1+R2, the honest answer is that **nobody has yet shown a reason to want R3**. If it
   is ever wanted, the false-merge query in §1 is the gate, and the refusal already names
   itself so nobody can turn it on by accident.

---

## 10. Handover

- **Changed:** a declared `<col>_norm` column is now derived on every write and can be
  re-derived on demand; `zero_pad` is refused by name; `GET /admin/config/resolve` grew a
  `notation` domain. Nothing consumes the derived value.
- **Verified:** 2030 passed / 2 skipped (baseline + 23); three defect injections with
  measured RED counts; live read-only census showing 15 clean merge groups and zero
  merges on every other column; CLI smoke-tested against the live config (exits 2, "no
  declaration", no writes, no DDL).
- **Unresolved:** none blocking. The mid-batch TTL window is a known, deliberate
  trade-off (a spec edited mid-batch can split a batch across two rule sets; re-deriving
  is the repair, and the module says so).
- **Next:** lead PM reviews the diff and commits; the phase-2 decisions in §9 need a
  ruling before any consumer is pointed at `_norm`.

### Doc impacts (docs/ was off-limits this round — for the doc lane)

Rows found by walking `DOC_OWNERSHIP.md` from the code paths I touched:

- **`guide/CONFIG_GUIDE.md` + a new `guide/config/notation_rules.md`** — a new config
  file with a two-step enable order (table_config ALTER first, declaration second).
  DOC_OWNERSHIP requires **both** when a config file is added.
- **`guide/config_reference/`** — this directory holds *copies* of the real configs and
  is explicitly flagged as silently going stale; it needs `notation_rules.json` plus a
  README row.
- **`architecture/backend.md`** (the write boundary grew a derivation step) and
  **`architecture/data_model.md`** (the `<col>_norm` derived-column convention).
- **`architecture/PRIMITIVES.md`** — "notation folding on top of `canonical_key_value`"
  is a new reusable primitive; **`architecture/DUPLICATION_LEDGER.md` D-3 (`_`
  convention)** should record that the convention is now *defended* by keeping `_` out
  of values, rather than by hoping values do not contain it.
- **`architecture/CODE_MAP.md`** — `server/notation_norm.py` is a new module
  (code-mapper's lane).
- **`qa/FEATURE_CHECKLIST.md`** — the operator-visible surface is
  `GET /admin/config/resolve?domain=notation` and the re-derivation script.
- **`docs/history/`** entry + `conda run -n assy_manager python docs/history/gen_index.py`
  after the commit lands.
- `process/PRODUCTION_READINESS.md`: no gate changes — the feature ships inert.

### Proposed lessons (for `agent_workspace/memory/server-pm.md`, not added directly)

- **함정**: 새 모듈을 결함 주입으로 검증할 때 `git checkout -- <file>`로 되돌리려 하면
  실패한다 — **untracked 파일은 git이 모르므로 복원할 원본이 없다.** 조용히 주입된 코드가
  남을 수 있다.
  **올바른 방법**: 신규(untracked) 파일의 주입은 Edit으로 손수 되돌리고, 되돌린 뒤 스위트를
  다시 초록으로 만들어 확인한다. (기존 추적 파일은 종전대로 `git checkout --`.)
- **함정**: "파생 컬럼은 체인 룰로 만든다"는 선례를 그대로 따르면, 매퍼 모듈이 **gitignored
  사용자 영역(`server/mappers/`)**에 놓여 저장소에는 `.sample`만 남고 기능이 도착 즉시
  죽는다(보드 O7과 같은 모양). 트리거=타깃 자기 참조는 무한 루프는 아니지만
  (`source_name == "chain_ingestion"` 필터) **가장 뜨거운 테이블의 쓰기를 두 배로 만든다.**
  **올바른 방법**: 같은 행 안의 파생값은 체인이 아니라 **쓰기 경계**(`cast_value_by_type`
  계열)에서 만든다 — 코드가 저장소에 남고, 추가 쓰기가 0이며, 원자적이다.
