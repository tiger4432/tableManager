# Design note: the `/schema` `join_resolved_columns` contract

**Status: NOT LANDED.** Written, run, fault-injected, then removed on the Lead PM's ruling of
2026-07-31 (the `/schema` round is deferred to next week and this week closes clean).

**Why it was removed rather than left red:** `client2/scripts/check_contracts.mjs` *discovers*
contracts by scanning `contracts/*/client_harness.mjs` rather than reading a list. An untracked
directory in the working tree is still found and still run, so a deliberately-red contract with
no implementation behind it would have blocked `npm run build`. That discovery behaviour is a
feature (it is what stops contract #5 landing dead), and it is exactly why a contract-first
vector cannot be parked on disk.

This note exists so next week does not re-derive the design. Everything below was **built and
measured**, not sketched.

---

## 1. What the round is for

`/schema` gains one additive key naming the columns whose value the server resolves through a
join:

```json
"join_resolved_columns": [
  {
    "name": "wafer_id",
    "kind": "collide",                 // "collide" | "virtual_only"
    "rule": "bonding_log_wafer_id",
    "right_table": "core_wafer_map",
    "unresolved_label": "미상"
  }
]
```

The defect it closes: `virtual_join_executor.announced_columns` answers the narrower question
"what does `/schema` have to **add**", so it omits **collide** columns. Its sibling
`exposed_columns` already computes the wider set and already says so in its own docstring.

Live consequence (Lead PM's measurement, 2026-07-31): `bonding_log.WAFER_ID` is a collide
column, is in `columns`, is absent from `virtual_columns`, and therefore looks like an ordinary
stored column to the grid. Its AG-Grid **Blank** filter matches 0 rows, **Not blank** matches
all 15,489, and `equals 미상` returns 4,052 -- because the resolved value COALESCEs to a
non-empty label.

---

## 2. The corpus (fixture)

Five tables, prefixed `jrc_test_` so they cannot collide with the user's gitignored
`table_config` (the `bonding_log` trap: a name collision lets import-time init pin a real
schema, and the contract is then scored against production's column set).

| table | columns | role |
|---|---|---|
| `jrc_test_log` | `log_id`, `jk`, `wafer_id` | the left table, carries both kinds |
| `jrc_test_wafer` | `wafer_key`, `jk`, `wafer_id`, `fab_site` | right table #1 |
| `jrc_test_site` | `site_key`, `jk`, `line_code` | right table #2 |
| `jrc_test_collide_only` | `co_id`, `jk`, `wafer_id` | **isolates the round's defect** |
| `jrc_test_plain` | `p_id`, `note` | control: no declaration |

Three declarations:

| rule | left | right | expose | `unresolved_label` |
|---|---|---|---|---|
| `jrc_rule_wafer` | `jrc_test_log` | `jrc_test_wafer` | `wafer_id`, `fab_site` | `NO-WAFER` |
| `jrc_rule_line` | `jrc_test_log` | `jrc_test_site` | `line_code` | `라인미지정` |
| `jrc_rule_collide_only` | `jrc_test_collide_only` | `jrc_test_wafer` | `wafer_id` | `NO-WAFER` |

Expected announcement for `jrc_test_log`:

```
wafer_id   kind=collide       rule=jrc_rule_wafer  right=jrc_test_wafer  label=NO-WAFER
fab_site   kind=virtual_only  rule=jrc_rule_wafer  right=jrc_test_wafer  label=NO-WAFER
line_code  kind=virtual_only  rule=jrc_rule_line   right=jrc_test_site   label=라인미지정
```

`jrc_test_collide_only` -> one `collide` entry. `jrc_test_plain`, `jrc_test_wafer`,
`jrc_test_site` -> `[]`.

**Three fixture decisions that carry weight, and must be kept:**

1. **`wafer_id` is deliberately both stored and exposed.** That is the whole defect in
   miniature. A fixture where every exposed column is `virtual_only` would pass against an
   implementation wired to `announced_columns` -- i.e. against the bug.
2. **Two declarations on one table, with two different labels, and NEITHER is
   `virtual_join_config.DEFAULT_UNRESOLVED_LABEL`.** A fixture using the default would pass
   against a server emitting the constant *and* against a client hardcoding it -- both sides
   sharing one wrong assumption, which is a vector worth zero. The scorer additionally asserts
   the fixture labels differ from the module default, so the axis cannot silently decay.
3. **`jrc_test_collide_only` exists separately** because it is the only case that proves the
   two keys answer different questions: `virtual_columns` must stay `[]` while
   `join_resolved_columns` has one entry.

Order is **not** asserted. Entries are compared as a set keyed by `name`; declaration order is
the route's business and pinning it would make an unrelated reordering a contract break.

---

## 3. The ten obligations

Six of the Lead PM's, plus four that fell out of building it. `status` is what decides whether
an axis fails hard or is quiet.

| id | status | obligation | waits on |
|---|---|---|---|
| **S1** | live | adding the key changes nothing else -- `columns` and `virtual_columns` byte-stable against a recorded baseline | -- |
| **S2** | contract-first | the key is present on **every** table, `[]` where there is no join | server-pm |
| **S3** | contract-first | the set equals `exposed_columns()`, scored **both** directions | server-pm |
| **S4** | contract-first | `kind` is stated per entry, both values occur, no set arithmetic needed | server-pm |
| **S5** | contract-first | `unresolved_label` rides per entry and follows the declaration | server-pm |
| **S6** | contract-first | every entry names its `rule` and `right_table` | server-pm |
| **S7** | live | a collide-only declaration still leaves `virtual_columns` empty | -- |
| **S8** | live | 🔴 **the marker is not the write guard** | -- |
| **S9** | live | a **collide** column stays writable | -- |
| **S10** | live | no name appears in both `columns` and `virtual_columns` | -- |
| **C1** | live | the client does not derive join-resolvedness by set arithmetic | -- |
| **C2** | contract-first | the client consumes the key, taking `kind`/label from the entry | client-pm |

### What each axis kills

- **S1** -- an implementation that "helpfully" appends collide columns to `columns`, or
  announces them a second time in `virtual_columns`. Either gives two answers to "is this
  column stored?". Same discipline `9200f20` used when it put virtual columns in a new key.
- **S2** -- omitting the key when the list would be empty. An absent key forces the client to
  tell "no joins here" apart from "this server predates the key": a version check wearing a
  data field, and the seed of a fallback that outlives the server it was written for.
- **S3** -- wiring the key to `announced_columns` (misses every collide -- the bug, reproduced
  in a new key), and wiring it to `load_virtual_join_rules` instead of `rules_for` (announces
  *unverified* declarations).
- **S4** -- emitting only `virtual_only` entries so `kind` is a constant; or omitting `kind`
  and expecting the client to difference the arrays.
- **S5** -- a constant, a module-level default, and a client-side literal, in one assertion.
- **S6** -- an entry reduced to `{name, kind}`: enough to grey a cell, not enough to act on it.
  "Where do I go to fix this value" currently has no answer on screen; the write refusal says
  "fix it in the join source" without naming the table.
- **S7** -- the lazy fix: pointing `virtual_columns` at `exposed_columns` and calling it done.
- **S9** -- a guard that refuses everything in the new key instead of everything in
  `virtual_only_columns`. Writing the left column is the **only** way to override a joined
  value (the absent-only rule's "left has a value" arm); "it is announced now, so grey it out"
  would delete that path and would look like tidiness.
- **C1** -- `columns.filter(c => !virtualColumns.includes(c))`-shaped reasoning. It is wrong
  for the collide case *by construction* and wrong silently.

---

## 4. S8 -- the NO-GO detector, in full

This is the one worth regenerating exactly.

> **Removing the announcement must not make a write succeed.**

The refusal belongs to `crud.refuse_virtual_join_columns`, which sits on the funnel every write
path converges on. The announcement only stops the UI *proposing* an impossible edit. If a
write ever succeeds because the announcement was absent, the key has become the defence -- and
a defence that lives in a **read** response is no defence at all: any client that never calls
`/schema` writes freely. That is a NO-GO on the design, not a bug to fix later.

It was implemented in **two halves, and both are needed**:

**Behavioural.** Suppress every nameable producer of the announcement (today
`virtual_join_executor.announced_columns`; after the round, the new symbol too -- looked up by
name from the vectors, and skipped with a reason if absent), then attempt a write to a
`virtual_only` column. It must still be refused. `virtual_only_columns` -- the guard's *real*
input -- is deliberately left alone.

**Structural.** AST-walk `crud.refuse_virtual_join_columns` and assert:

- it does **not** call `announced_columns`, the new announcement symbol, or `get_table_schema`;
- it **does** still call `virtual_join_executor.virtual_only_columns`.

The structural half is not redundant. Behaviour can be right by accident -- a call graph
cannot, and the failure this guards against is a refactor that rewires the input while the
tests still pass because the two sets happen to coincide on the fixture.

The failure message was written to stop the round, not to file a bug:

```
🔴 NO-GO CONDITION MET.
  A write to the virtual_only column 'line_code' SUCCEEDED while the announcement was suppressed.
  The marker has become the write guard. A defence that lives in a read response is no defence --
  any client that never calls /schema can write anything.
  Take this to the Lead PM before anything else in this round proceeds.
```

**S8 and S9 are green today and are scoreable without the implementation.** They are the part
of this contract that could have landed this week on its own, if the red had not come with it.

---

## 5. Measurements taken before removal

Everything here was run, not predicted.

| run | result |
|---|---|
| `pytest contracts/join_resolved_columns/ -q` (verdict `red`) | **6 failed, 8 passed** -- S2, S3, S4, S5, S6 and the coverage check, all banner-attributed |
| same, verdict flipped to `pending` | **8 passed, 6 skipped, 0 failed** -- clean switch, one line in vectors.json |
| `node .../client_harness.mjs` | **2/2 assertions, exit 0** (C2 printed by name as quiet contract-first) |
| `node client2/scripts/check_contracts.mjs` | 7 contracts, no divergence (the harness exits 0 on purpose) |
| `pytest server/tests/ -q` with the shim | **7 failed, 1810 passed, 1 skipped** -- 6 mine, plus one noted in §7 |

**Fault injection (nothing under `server/` was edited -- runtime patches via a scratch plugin):**

| fault | caught by |
|---|---|
| write guard rewired to the announcement | **S8 red** |
| write guard refuses collide columns too | **S9 red** |
| `announced_columns` widened to include collide | **S7 stayed green** -- see §6 |

---

## 6. The axis I could not falsify, and why

**S7's behavioural half is not falsifiable by runtime injection.** Widening
`announced_columns` does not break it, because the `/schema` route's own de-duplication
(`known = set(columns)`) drops the name again. The behaviour is enforced by that filter, not by
the executor.

So a structural half was added: AST-assert the route still filters the announced list against
the names already in `columns`. Deleting that filter is what would make S7 real, and that is
what goes red.

**I did not independently falsify the structural half** -- doing so needs a doctored copy of
`main.py`, which this round was not permitted to touch. Next week: prove it against a temp-tree
copy, the same way the client harness was proved (a copied `grid.js` with `filter: false`
flipped, which produced exit 1 with the file:line).

---

## 7. One measurement to re-check next week

The full-suite run with the shim reported **7 failures: my 6, plus**

```
server/tests/test_config_reload_integrity.py::test_inv_9_1_atomic_save_event_applies_physical_alter
```

That file already bit this session once. The `blank_predicate` fixture left scratch tables in
the process-wide `models.DYNAMIC_TABLES` / `Base.metadata`, and a *different* test in the same
file failed **in full-suite order only** while both files passed alone. It was fixed with an
`_unregister()` teardown, and the suite went to `1801 passed, 0 failed`.

The `join_resolved_columns` fixture carried the same `_unregister()` teardown, so this is
either a second leak with a different shape or an unrelated flake. **It is unverified.** With
the round removed, re-run `pytest server/tests/test_config_reload_integrity.py` and the full
suite to see whether it is gone; if it is not, it is not this round's and it is worth its own
look -- that file's tests drive a real watchdog and a physical ALTER, which is exactly the
shape that goes order-dependent.

---

## 8. Notes for whoever regenerates this

- **Fixture mechanics that work.** `virtual_join_config.unique_index_covering` answers through
  `pg_index` and returns `None` on any non-Postgres dialect. Since "unknown means refuse", the
  suite's SQLite leaves **zero verified rules** and every assertion passes vacuously. Stand it
  in (`lambda db, table, cols: "uq_stub" if table in right_tables else None`) and put a
  **vacuity guard** at the top of the fixture that asserts `rules_for(...)` is non-empty. Same
  stand-in, same reason, as `server/tests/test_virtual_column_search.py`.
- **Teardown must unregister.** Restoring `crud.TABLE_CONFIG` is not enough;
  `init_dynamic_models` also writes `models.DYNAMIC_TABLES` and `Base.metadata`.
- **Filter `$`-prefixed keys once, at load.** `expected` and `additivity_baseline` carry
  `$comment` prose; a missed `startswith("$")` raised a `TypeError` inside a *failure* path,
  i.e. exactly where nobody is looking. Found on the first run.
- **Do not put line numbers in `$why`.** `crud.py` moved ~+58 lines and `main.py` ~+23 while
  this session was running. Point at function names; let the scorer print line numbers it
  measured.
- **The verdict switch is worth keeping.** `"contract_first_verdict": "red" | "pending"` in
  vectors.json, read in one helper, deciding hard-fail vs named skip. It is the Lead PM's dial
  and it needs no code change. The cost of a shared red is on record: 2026-07-29, a
  contract-first axis rendered as hard failures cost a reviewer of an *unrelated* round time
  working out the red was not theirs (`contracts/map_seam/vectors.json`, `$was_pending`).
- **The client harness should exit 0 while its axis is contract-first.** A client cannot
  consume a key the server does not send; a red there is red at the wrong door and stops every
  other lane's build. It should still *print* the axis by name with its owner and what blocks
  it, and it should go **red in the other direction** the moment the client references the key
  while the axis is still marked contract-first -- otherwise the axis silently stops asserting.
- **And the discovery lesson from this stand-down:** a contract-first vector cannot be parked
  on disk. `check_contracts.mjs` finds directories, not list entries. Land it in the same pass
  that lands the implementation, or land only the axes that are green today (here: S1, S7, S8,
  S9, S10, C1 -- which is most of the value) and add the contract-first ones when server-pm
  starts.
