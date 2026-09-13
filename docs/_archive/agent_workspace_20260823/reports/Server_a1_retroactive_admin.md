# Server A1 — retroactive ADMIN AUTO CONFIRM fails with AttributeError

**Verdict on the lead PM's diagnosis: REFUTED.** It is not a circular import, and `main` is
not partially initialised in any process. The mechanism is **name shadowing**: in the worker
processes `main` is not a stable module name, because those processes put user-owned
directories at `sys.path[0]`. The fix is still the one the lead proposed (move the helper out
of the FastAPI entry point), but for a different reason, and the reason changes what else is
exposed.

---

## 1. Reproduction

### 1.1 What the circular-import hypothesis predicted, and what actually happens

Measured, not read:

* `server/main.py` has **no** module-level import of `enrichment_analysis`, `retroactive`,
  `graph_stale_edges` or anything else that reaches back into `main`. There is no cycle to
  find. (`grep -n "^import \|^from " server/main.py` + the same for `retroactive.py`,
  `run_auto_update.py`, `enrichment_candidates.py`, `enrichment_config.py`.)
* A fresh `import main` in a non-uvicorn process **succeeds and exposes the symbol**:

  ```
  step 0: 'main' in sys.modules? False
  step 3: import main   -> ok, file = ...\server\main.py
  step 4: getattr get_column_filter_condition -> <function get_column_filter_condition at 0x...>
  ```

* The full sweep runs clean in **both** process shapes against the live database, read-only
  (`apply=False`, plus `db.rollback()`):

  ```
  [scheduler] 'main' preloaded? False
  --- A: enrichment_analysis.run_auto_confirm_sweep(apply=False)
      OK: {'queue_size': 20, 'confirmed': 40, 'written_cells': 40}
  --- B: retroactive.count('enrichment_confirm')   [the admin COUNT route body]
      OK: affected= 40 scanned= 20
  ```

* `get_column_filter_condition` has been present in **every** version of `main.py` for the
  last 40 commits touching that file (checked with `git show <sha>:server/main.py | grep -c`),
  so no stale-process story explains a missing attribute either.

So the defect does not live in the code as such. It lives in the process.

### 1.2 The actual mechanism

`enrichment_analysis.py:72` did an unqualified `import main`. `main` is the most common
module name in Python, and three of the five processes put **user-owned directories first on
`sys.path` and never remove them**:

| process | inserts at `sys.path[0]` | code |
|---|---|---|
| Auto Update Scheduler (`run_auto_update.py`) | each collector's `ingestion_workspace/<t>/auto_update/` | lines 217-218 (every script run) and 487-488 (reflection loader) |
| File Ingestion Watcher / Chained Ingestion Worker (`parsers/directory_watcher.py`) | each table's `ingestion_workspace/<t>/scripts/` | `_install_legacy_import_shim`, ~line 514 |

After the first collector has run, `import main` in that process binds **whatever `main.py`
sits earliest on `sys.path`** — a user file. Reproduced verbatim, in the scheduler shape,
against the live database:

```
sys.path[0] = ...\scratchpad\fake_collector_dir
'main' preloaded? False
  File "...\server\enrichment_analysis.py", line 85, in _queue_condition
    cond = main.get_column_filter_condition(table_model, col, spec)
AttributeError: module 'main' has no attribute 'get_column_filter_condition'
main resolved to: ...\scratchpad\fake_collector_dir\main.py
```

That is the reported message, verbatim, and it explains **both halves of the report**:

* **the CLI works** — `server/scripts/enrichment_insights.py` inserts only `server/` on
  `sys.path` and never inserts a workspace directory, so `main` resolves correctly there;
* **the web process would also work** — `uvicorn main:app` puts the real module in
  `sys.modules['main']` before any request, and `sys.modules` wins over `sys.path`. The web
  process is immune **by accident**, not by design. `GET /admin/retroactive/enrichment_confirm/count`
  (web) and `POST /admin/retroactive/enrichment_confirm/run` (scheduler) therefore behave
  differently on the same rule, which is the worst possible shape for an operator: the count
  succeeds, the button that follows it fails.

The decoy file used for the reproduction is benign (`def fetch(): return []`) and lives in the
scratchpad — deliberately, because the point is that a perfectly valid user module silently
answers to the name.

### 1.3 What I could NOT confirm

I did **not** find a `main.py` in the live workspace today
(`find . -name "main.py*"` returns only `server/main.py` and the agent worktree copy), and no
log carries the AttributeError (`grep "has no attribute"` over `server/*.log` — only unrelated
`_FakeDB` and pandas `Series` hits). So the *trigger file* is unproven: the user may have
removed or renamed it, or production carries a workspace this checkout does not. **The
mechanism is proven; the specific file that triggered it is not.** If the lead wants that
closed, the one question for the user is: *did you have a `main.py` (or a directory named
`main`) anywhere under an `ingestion_workspace/<table>/auto_update/` or `.../scripts/` folder?*

One incidental finding while reading the logs, unrelated but worth boarding:
`server/auto_update.log:137586` shows `[Retroactive] run_id=43da4ed7c4a5 op=enrichment_confirm
... START` on 2026-07-31 23:21:47 with **no DONE and no FAILED**, and the scheduler emits no
further line of any kind (its per-minute collectors stop too) until the process restarts the
next day. `retroactive.execute` never raises, so a missing terminal line means the process was
stopped mid-run, not that the run failed silently — but a retroactive run that leaves no
terminal record is worth one line of scrutiny.

---

## 2. Radius

**Deferred `import main` / `from main import` inside a function body, whole repo, including
the gitignored user areas (`server/config`, `server/ingestion_workspace`, `server/mappers`):**

| site | status |
|---|---|
| `server/enrichment_analysis.py:72` | **the reported defect.** Fixed. |
| `server/scripts/archive/profile_fetch.py:127` and `:246` — `from main import to_local_str` | Archived profiling script. **Same symbol as the H4 incident** (`to_local_str` moved to `utils/time_format.py` precisely because a worker reached it through `main`), i.e. the H4 fix left a copy behind. Repointed to `utils.time_format`. |
| `contracts/blank_predicate/test_predicate_contract.py:249`, `contracts/config_resolve_report/test_report_contract.py:165,468` | Contract harnesses. They run under pytest, where `conftest.py` has already put the real module in `sys.modules`, so they are not a runtime hazard — and `blank_predicate` reaches `main.get_column_filter_condition` **on purpose**, to score the production builder rather than a copy. Left alone; the re-export keeps them scoring the real object (proven in §3.2). |
| `server/tests/**` (≈45 sites) | Same: `main` is preloaded by `conftest.py` before any test body runs. |

**Module-level `from main import app`:** `server/tests/conftest.py:41`, `test_admin_auth.py:27`.
Correct — the suite is testing the app.

So the runtime radius is exactly **one** production call site, plus one archived script. The
worrying part is not the count; it is that the one site was the only thing standing between a
user's file-naming choice and a dead admin button, and nothing in the suite could see it.

---

## 3. The fix

### 3.1 What changed

**New: `server/column_filter.py`** — the AG-Grid filter DSL to SQLAlchemy translator,
`get_column_filter_condition(table_model, col_name, f_info, col_expr_override=None)`, moved
verbatim out of `main.py` (148 lines, byte-identical body; only the `crud` import moved to
module scope). It depends on SQLAlchemy and `database.crud` and nothing else — no FastAPI, no
app state, no request context. It answers the lead's second question directly: it never needed
to live in a FastAPI entry point, it lived there because `/tables/{t}/data` was its first
caller.

This follows the precedent the repo already set for exactly this class of defect: H4
(`chain_ingestion_worker` doing `from main import to_local_str`) was fixed by creating
`server/utils/time_format.py`. Same shape, same remedy, and the new module's docstring says so
rather than re-deriving it.

**Hunks touched, exactly:**

| file | hunk |
|---|---|
| `server/main.py` | **one** hunk: old lines 1175-1322 (the whole `def`) replaced by a 4-line comment plus `from column_filter import get_column_filter_condition`. 5623 -> 5480 lines. Nothing else in the file is touched; the internal caller at new line 1258 (`apply_column_filters`) is unchanged and still calls the bare name. |
| `server/enrichment_analysis.py` | `import main` -> `import column_filter` (line 72), the call site (line 85 -> 101), and two docstring paragraphs (see below). |
| `server/scripts/archive/profile_fetch.py` | 2 sites, `from main import to_local_str` -> `from utils.time_format import to_local_str`. |
| `server/tests/test_entrypoint_import_isolation.py` | new. |

**Docstring corrections in `enrichment_analysis.py`, which are part of the fix, not decoration.**
The module said *"Everything here is driven from a CLI ... never from the web process"* and the
lazy import was annotated *"lazy: CLI-side only"*. Both were **false since 2026-07-31**: the
retroactive admin surface calls this module from the web process AND from the scheduler. That
false belief is what made an unqualified `import main` look safe. The docstring now names all
three processes and records why the lazy import was not a safety property — it made `main`
*late*, not *safe*.

### 3.2 Re-export proof

`main.py` keeps the name, and it is the **same object**, so nothing that spells it
`main.get_column_filter_condition` breaks:

```
main.get_column_filter_condition -> <function get_column_filter_condition at 0x...>
is the same object as column_filter's: True
defined in: column_filter
notBlank  -> True     # delegates to crud.not_blank_sql_condition
contains  -> True
compound  -> True     # the recursive AND/OR branch
```

External callers verified: `contracts/` **107 passed, 2 skipped** — including
`test_predicate_contract`, which exists specifically to score `main.get_column_filter_condition`
and would have gone green against a stub. It is scoring the moved function.

### 3.3 Reproduction re-run after the fix

The same scheduler-shaped process with the same decoy on `sys.path[0]`:

```
sys.path[0] = ...\fake_collector_dir
'main' preloaded? False
NO FAILURE
KeyError: 'main'          <- the probe's final line, printing sys.modules['main']
```

The `KeyError` is the result, not a problem: after the fix the sweep completes in a process
where **`main` is never imported at all**.

### 3.4 Suite

`conda run -n assy_manager python -m pytest server/tests/ -q` from the repo root:
**2007 passed, 2 skipped** (baseline 2005 + the 2 new tests). No regressions.

---

## 4. The finding that outranks the fix

> This feature was closed on 2026-08-01 as "user verified working". It worked in simulation and
> failed in production.

**Name the hole precisely: the suite has exactly one way of putting `main` into a process, and
it is not the way any worker does it.**

`server/tests/conftest.py:41` does `from main import app` **at module scope, before any test
runs**. From that moment `sys.modules['main']` is the real application module in the pytest
process, and it stays there for all 2000+ tests. Every lazy `import main` in every module under
test is therefore answered out of `sys.modules` and **never touches `sys.path` at all**. The
suite cannot distinguish "this module resolves `main` correctly" from "somebody already
imported `main` for it".

The running system has three different answers to the same question:

| process | how `main` resolves | `sys.path[0]` |
|---|---|---|
| `uvicorn main:app` (web) | preloaded in `sys.modules` | repo-controlled |
| `enrichment_insights.py` (CLI) | fresh import off `sys.path` | `server/`, inserted by the script |
| `run_auto_update.py` / `run_watcher.py` / `run_chain_worker.py` | fresh import off `sys.path` | **a user-owned workspace directory** |
| pytest | preloaded by `conftest`, permanently | repo-controlled |

pytest reproduces the web process's resolution rule and nothing else. Both surfaces that failed
live in the third row.

### What test shape would have caught it — and is now in the tree

`server/tests/test_entrypoint_import_isolation.py`, two tests of two deliberately different
kinds:

1. **A source rule** — `test_no_server_module_imports_the_web_entrypoint`. No module under
   `server/` (except `main.py` and the suite) may say `import main` / `from main import`. This
   is the **general form** of the existing
   `test_config_reload_integrity.test_h4_chain_worker_never_imports_main`, which wrote the same
   rule down for **one worker file** after the same class of defect and therefore could not see
   the second occurrence. Defect axis verified: run against `HEAD` (pre-fix) the predicate flags
   `enrichment_analysis.py:72` and `profile_fetch.py:127,246` and nothing else.

2. **A process test** — `test_the_queue_predicate_translates_with_a_decoy_main_on_the_path`.
   Spawns a subprocess with a benign user `main.py` first on `sys.path`, exactly as the
   scheduler leaves it, and requires `enrichment_analysis._queue_condition` to translate the
   queue predicate anyway. It asserts three things, the third of which is the one that stops it
   from being theatre: `CONDITION True` (it translated), `MAIN_IN_MODULES False` (the entry
   point was never dragged in), and `DECOY_WINS True` (the decoy really did shadow `main`, so
   the defect axis was active — without this the test would pass on a machine where it shadowed
   nothing and would prove nothing). Pre-fix this test raises the reported AttributeError; I
   verified that shape directly with the standalone reproduction in §1.2 rather than by
   temporarily corrupting the source.

**The generalisable lesson, for whoever writes the next verification:** a test that imports the
application module at collection time can never verify anything about how a worker process
resolves names. If a change affects a code path that runs in more than one of the five
processes, the verification has to spawn the process shape, not just call the function. There
is prior art for this in the tree (`test_config_reload_integrity`'s subprocess probes,
`test_ddl_never_reaches_production`) — it just was not reached for here.

---

## 5. Not done / for the lead

**No boundary contract was touched.** No REST signature, path, WS event, cell shape or schema
contract changed. `main.get_column_filter_condition` still resolves (§3.2), so no external
caller is affected.

**Doc impacts (I did not touch `docs/`, as instructed):**

* `docs/architecture/CODE_MAP.md` — several anchors now move. Concretely:
  * §1 line 304 anchor list: `get_column_filter_condition **1175**` -> the function is no longer
    in `main.py` at all; `main.py` is now 5480 lines (was 5623), so every anchor **after old
    line 1322 shifts by -143**.
  * line 290 and line 326 (the `get_column_filter_condition` row, "~1175 / ~1158") -> new home
    `server/column_filter.py:34`.
  * line 977 (`to_public_rule`) and line 1219 (`enrichment_analysis` entry) both say the queue
    predicate is translated by **`main.get_column_filter_condition`**, and line 1219 additionally
    states *"`main` import being a lazy in-function import is INTENTIONAL (so a worker does not
    drag the web app in) — moving it to module scope breaks that property."* **That sentence is
    now the opposite of the rule** and is exactly the belief that shipped the defect; it should
    be replaced, not merely re-anchored.
  * line 1340 (`virtual_join_executor`) and line 1907 (the read flow) reference
    `main.get_column_filter_condition` as a cross-reference.
  * §5-A needs a new module row for `server/column_filter.py` (172 lines).
* `docs/architecture/PRIMITIVES.md` — the filter DSL translator now has a named home worth
  cataloguing (the "one translator, four consumers" claim is unchanged, only relocated).
* `docs/architecture/backend.md` — module inventory gains `server/column_filter.py`.
* `docs/qa/FEATURE_CHECKLIST.md` — the retroactive auto-confirm entry was closed as
  user-verified on 2026-08-01; §4 is the reason that closure was not safe.
* **Deliberately left alone:** `server/database/crud.py` has four comment references to
  `main.get_column_filter_condition` (lines 731, 736, 763, 1028). They remain *true* via the
  re-export, and `crud.py` is boundary-heavy, so I did not touch it in a lane that had already
  seen a collision in `main.py` today. Worth repointing at `column_filter` in a doc pass.
* `docs/guide/CONFIG_GUIDE.md` / `DEPLOY_SETUP.md` / `process/PRODUCTION_READINESS.md`: **no
  change needed** — no config key, reload path, environment variable or deployment unit moved.

**Proposed lesson for `agent_workspace/memory/server-pm.md`** (not added directly, per the
operating rule):

> * **Trap**: an unqualified top-level `import X` inside a worker code path is not a stable
>   binding. `run_auto_update.py` and `parsers/directory_watcher.py` insert user-owned
>   workspace directories at `sys.path[0]` and never remove them, so in the scheduler / watcher
>   / chain-worker processes any common module name (`main` above all) can be answered by a
>   user's file. Making the import *lazy* makes it *late*, not *safe*.
>   **Right way**: shared helpers live in a module that is not a process entry point and does
>   not carry a name a user would pick (`utils/time_format.py`, `column_filter.py`); the entry
>   point re-exports the name so existing callers keep working. Enforced by
>   `server/tests/test_entrypoint_import_isolation.py`.
> * **Trap**: `conftest.py` imports the app at collection time, so the whole suite resolves
>   `main` out of `sys.modules` and can never see how a worker process resolves it. A green
>   suite is not evidence about the other four processes.
>   **Right way**: when a change touches a path that runs in more than one of the five
>   processes, verify by spawning the process shape (subprocess probe with the real
>   `sys.path`), the way `test_config_reload_integrity` already does.
