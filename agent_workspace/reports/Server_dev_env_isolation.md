# Server — Isolated Development Environment

> Domain: Server (backend) · 2026-07-26 · branch `main`, **not committed**
> Deliverable for: "agents must stop verifying against the user's live production environment"

---

## 1. What an agent runs

```bash
# once (or whenever the snapshot should be refreshed)
conda run -n assy_manager python server/scripts/dev_env/devenv.py snapshot

# start / stop
conda run -n assy_manager python server/scripts/dev_env/devenv.py up
conda run -n assy_manager python server/scripts/dev_env/devenv.py down

# where am I pointing?
conda run -n assy_manager python server/scripts/dev_env/devenv.py status
```

`up` bootstraps the data tree on first run, so a cold start is literally
`snapshot` then `up`. The isolated API is on **`http://127.0.0.1:8081`**.

For a one-off script that must also stay off production:

```bash
conda run -n assy_manager python server/scripts/dev_env/devenv.py env   # prints the overrides
```

| | production | isolated |
|---|---|---|
| database | `assy_manager` | `assy_qa` (`DATABASE_URL`) |
| config | `server/config/**` | `dev_env/config/**` (`ASSY_DATA_ROOT`) |
| workspace | `server/ingestion_workspace/**` | `dev_env/ingestion_workspace/**` |
| API + WS | `127.0.0.1:8080` | `127.0.0.1:8081` |
| graph worker | `127.0.0.1:8090` | `127.0.0.1:8091` (`GRAPH_SYNC_PORT`) |
| watcher | running | **not started** |
| auto-update scheduler | running (`*/2` cron) | **not started** |

`devenv.py` has no flag that starts the watcher or the scheduler. Their churn is
the entire problem, so the guarantee is structural rather than a default.

---

## 2. What was built

### 2.1 `server/paths.py` — one override point for the data root

`DATABASE_URL` already made the database swappable; nothing made the on-disk data
swappable. ~17 modules each rebuilt `config/` and `ingestion_workspace/` paths
from their own `os.path.dirname(__file__)`. They now all read from one module:

```python
DATA_ROOT     = os.path.abspath(os.environ.get("ASSY_DATA_ROOT") or SERVER_DIR)
CONFIG_DIR    = os.path.join(DATA_ROOT, "config")
WORKSPACE_DIR = os.path.join(DATA_ROOT, "ingestion_workspace")
```

Unset → resolves to `server/`, so production behaviour is unchanged. The import
convention copies the existing `event_constants.py` pattern (`server/` is on
`sys.path` in every entry point; the two modules that can be imported without it
use the same try/except fallback `crud.py` already uses).

Consumers updated: `main.py` (9 sites incl. the admin script editor),
`database/crud.py`, `parsers/directory_watcher.py`, `run_watcher.py`,
`run_auto_update.py`, `run_chain_worker.py`, `run_graph_sync.py`,
`chain_ingestion_worker.py`, `graph_sync_worker.py`, `bonding_plan.py`,
`transfer_plan.py`, `map_overlay.py`, `enrichment_config.py`,
`ontology_config.py`, `utils/auto_update_control.py`, `setup/{init_db,reset_db,seed_data,setup_workspace}.py`.

Two judgement calls worth flagging:

- **`utils/auto_update_control.SERVER_DIR` kept its name.** It was always "the
  base for config/ and ingestion_workspace/", i.e. the data root, and it is the
  symbol five tests monkeypatch. Repointing its *value* at `paths.DATA_ROOT`
  relocates both trees without touching the test seam. I initially also changed
  `main.py`'s status endpoint to bypass it and that broke
  `test_status_annotates_active` — the endpoint now resolves through
  `auc.SERVER_DIR` again, deliberately.
- **`main.py` admin script editor** now routes the `ingestion_workspace/` prefix
  through `WORKSPACE_DIR` while `mappers/` stays under `server/`. The extracted
  helper `_resolve_admin_script_path` also tightened the containment check from
  `full_path.startswith(base)` to a separator-aware comparison; that was the line
  being rewritten anyway.

### 2.2 `server/scripts/dev_env/snapshot_db.py` — the snapshot

Not a clone. Production is **13 GB**; the snapshot is **422 MB / 704,647 rows**,
built in **~3.5 minutes**. Composition:

| kept | how |
|---|---|
| `wafer_map_metadata` | in full (171 maps) |
| map data tables | only rows belonging to a registered map — `bonding_map` 1,190 of 1,756,739; `core_defect_map` and `eds_fail_map` 95,312 each (all 74 registered maps) |
| plan tables | `map_doe`, `map_doe_source`, `map_split_registry`, `transfer_plan*` in full |
| every table ≤ 20,000 rows | in full (`bonding_log`, `dt_log`, `dt_map`, `sample_map`, `wafer_process`, graph store, ingestion logs/checkpoints…) |
| large tables with no map key | newest 5,000 (`inventory_master`) |
| `cell_sources` / `cell_overwrites` / `audit_logs` | scoped to the rows actually copied, under a global budget |
| `database_outbox` | **empty by design** — 2.9M consumed events; a fresh env must not replay production history on first worker start. `graph_sync_state` is reset to 0 to match. |

**The source connection is opened READ ONLY and that guard is self-tested on
every run.** Before a single row is read the script attempts a write and
requires it to fail with SQLSTATE `25006`; anything else aborts. A bug in this
script cannot write to production, it can only crash. (The guard earned its keep
immediately — see §5.)

Idempotent: target tables are truncated and refilled, so `snapshot` is also
"refresh".

### 2.3 `server/scripts/dev_env/devenv.py` — the entry point

`bootstrap` / `snapshot` / `up` / `down` / `status` / `env`. Bootstrap copies
`server/config` and `server/ingestion_workspace` into `dev_env/`, leaving
`raws/ archives/ err/` as empty shells (those hold 9,400+ live pipeline files) and
resetting `scheduler_status.json` so no cron state is inherited.

The **auto-update collector scripts themselves are copied in**, on purpose: it
makes "the scheduler is off" a fact about the running processes rather than an
artefact of a missing file, which is what makes the §3.3 measurement meaningful.

`isolated_env()` also sets `ASSY_API_BASE`. That matters: the collector scripts
default to `http://localhost:8080`, i.e. **production**, so anything run without
this override would have posted into the live server.

### 2.4 `server/scripts/dev_env/manifest.py` — the instrument

`capture` / `diff` for production integrity: per-table row count + `max(updated_at)`
+ `max(created_at)`, and sha256 + mtime + size for every file under
`server/config/**`, `server/ingestion_workspace/**` and `server/mappers/**`
(9,400+ files). `diff` separates *stable* files from `raws/archives/err`, whose
churn is the live pipeline's, not an agent's.

### 2.5 Board issue #16ⓐ — pytest no longer reaches production

`server/tests/conftest.py` now pins `DATABASE_URL` **before** `from main import app`:

```python
os.environ["DATABASE_URL"] = os.environ.get("ASSY_TEST_DATABASE_URL", "sqlite:///:memory:")
```

Hard assignment, not `setdefault` — an ambient `DATABASE_URL` in the shell must
not be able to leak in. `ASSY_TEST_DATABASE_URL` is the escape hatch for running
the suite against a different isolated database.

### 2.6 The `mappers/` gap is closed (round 2)

`_resolve_admin_script_path` gained `for_write`. Writes to any **non-relocated**
prefix are refused with **403** while `paths.IS_ISOLATED`; `POST /admin/scripts/code`
is the only caller that passes `for_write=True`. Reads stay allowed — reading a
mapper to understand it is harmless, overwriting it is the incident. The flag is
read at call time, not captured at import, so it reflects the process's real data
root and stays patchable.

### 2.7 `server/tests/test_dev_env_isolation.py` (new, round 2)

**10 tests**, each written so that deleting what it guards turns it red:

| class | guards |
|---|---|
| `TestSuiteNeverTouchesProduction` (3) | the conftest pin. Asserts the engine URL equals the pin's *expression* (`ASSY_TEST_DATABASE_URL` or in-memory sqlite) — that is what catches a `setdefault` downgrade, since setdefault would let an ambient value win. A separate test asserts "never `assy_manager`" regardless, in case someone points `ASSY_TEST_DATABASE_URL` at production. |
| `TestDataRootOverride` (2) | `paths.py` staying the single override point. Runs a **subprocess** with `ASSY_DATA_ROOT` set (the value is read at import; reloading in-process would leave already-imported consumers holding stale constants — `main.py` reads `paths.WORKSPACE_DIR` at request time) and asserts all 10 probed module constants land under the overridden root. Any module that re-hardcodes its own path shows up as a straggler. Second test asserts unset is a no-op. |
| `TestIsolatedServerCannotWriteLiveMappers` (5) | the 403. Primary check is at the **resolver**, with no filesystem access at all; three more go over real HTTP guarded by a self-repairing fixture (§6). |

---

## 3. Isolation proof

Every claim below is a measurement taken this session, not a design argument.

### 3.1 The isolated server serves from the snapshot

Same endpoint, two servers, observed through their own APIs:

```
GET /tables/inventory_master/data   :8080 (production) -> total 320,238
GET /tables/inventory_master/data   :8081 (isolated)   -> total   5,000
```

`dev_env/logs/api.log` line 1:
`[paths] data_root=…\dev_env isolated=True db=postgresql://…/assy_qa`

### 3.2 A run that deliberately writes leaves production byte-identical

Three write paths were exercised against `:8081`, each carrying the sentinel
`DEVENV_ISO_PROBE_7f3c1a9e` — including **the two exact paths that overwrote user
assets today**:

1. `PUT /tables/inventory_master/data/updates` → dynamic table + `cell_sources` + `audit_logs` + outbox
2. `POST /map-presets` → writes `config/maps.json`
3. `POST /admin/scripts/code` → writes `ingestion_workspace/**/*.py`

All returned 200. Then:

| | `assy_qa` (isolated) | `assy_manager` (**production**) |
|---|---|---|
| `inventory_master.part_no` | 1 | **0** |
| `cell_sources.updated_by` | 3 | **0** |
| `audit_logs.transaction_id`/`updated_by` | 3 | **0** |
| `database_outbox.payload` | 2 | **0** |

A sentinel is used rather than row counts because **production row counts are
useless as evidence** — over one 3-minute window they moved
`inventory_master 320,235 → 320,247`, `bonding_log +8`, `graph_edges +24`, and
`bonding_map` and `database_outbox` actually went *down*. That is the live system,
and it is precisely why reviewers were chasing phantoms.

**Files (sha256 + mtime).** Six captures spanning 23:40 → 00:15, bracketing the
deliberate write (~23:42):

```
config/maps.json                                sha=5fcc8c8af266  mtime=2026-07-26T10:34:54   6/6 identical
workspace/inventory_master/config/config.json   sha=a4fbcee26199  mtime=2026-07-26T21:35:42   6/6 identical
config/table_config.json                        sha=226d7956824b  mtime=2026-07-26T18:31:00   6/6 identical
config/scheduler_status.json                    6 DIFFERENT sha   mtime 23:40:00 → 23:44:03 → 23:46:05
                                                                        → 23:48:00 → 23:59:04 → 00:15:01
```

Both files that were clobbered today are unchanged in content **and** in mtime —
their mtimes pre-date this session by hours. `scheduler_status.json` is the
control: **six distinct states**, moving on the live scheduler's own ~2-minute
cadence, which proves the instrument is sensitive and a flat reading means "never
opened", not "instrument asleep".

> **Correction on the evidence chain.** My original 23:11 baseline capture
> (`prod_before.json`) was **overwritten at 00:13 by a concurrent process sharing
> this session's scratchpad** — its `captured_at` now reads 00:13:48. I caught it
> because the file claimed to contain 23:58 mtimes, which a 23:11 capture cannot.
> Everything above has therefore been **re-derived from the five captures that
> survive**, each of whose `captured_at` proves it predates the event it is used
> to judge. The conclusions are unchanged; the earliest surviving bracket is
> 23:40 rather than 23:11. Lesson filed in §7 — baseline manifests need unique,
> unguessable filenames when the scratchpad is shared.

Across all 9,400+ files under `config/`, `ingestion_workspace/` and `mappers/`,
the **only** stable file that changed during the write exercise was
`scheduler_status.json`. The isolated writes landed in `dev_env/config/maps.json`
and `dev_env/ingestion_workspace/inventory_master/scripts/_devenv_probe.py`.

A final capture at the end of the session shows three more stable files changed —
`config/{bonding_plan,map_overlay,transfer_plan}_config.json.sample` at
23:58:42–23:59:09. Those are **not mine**: they are the `.sample` counterparts of
the three modules the concurrent editor rewrote (§6), timestamped 40 minutes
after my last server edit. My tooling never writes to `server/config/` —
`bootstrap` only reads it (`shutil.copy2` source side).

### 3.3 The watcher and scheduler are genuinely off

Not "configured off" — observed off. A **420-second** window (production
collectors run `*/2` and `*/3`; the watcher re-sweeps `raws/` every 300 s, so the
window covers 3+ collector cycles and a full sweep interval), tracking all 33
tables of `assy_qa` (row count + `max(updated_at)`) plus the file count under
`dev_env/ingestion_workspace/`:

```
[idle] window start 2026-07-26T23:44:09  (420s)
[idle] window end   2026-07-26T23:51:11
[idle] tracked keys: 34
[idle] RESULT: ZERO CHANGE - no row appeared, no file appeared,
       no updated_at moved, over the whole window.
```

For contrast, production over an overlapping 3.5-minute window gained rows in 12
tables. The isolated env was *not* idle by accident: the chain worker and the
graph sync worker were both running throughout — they are reactive outbox
consumers, so they cost nothing when nobody writes.

This measurement is only meaningful because bootstrap **does** copy the collector
scripts (all 9 of them are present under `dev_env/ingestion_workspace/*/auto_update/`).
Nothing ran them because no scheduler process exists.

### 3.4 pytest no longer reaches production — with defect injection

A proof that never executes the new line proves nothing, so the pin was removed
and restored byte-for-byte (autocrlf rewrites are a known trap; the marker is a
single line for that reason):

| run | `DATABASE_URL` in the environment | result |
|---|---|---|
| pin **removed** | `postgresql://…/assy_devenv_does_not_exist` | **exit 4** — reached `psycopg2.connect` during import, i.e. import-time `create_all` really does follow `DATABASE_URL` |
| pin **active** | same poisoned value | **exit 0**, 14 passed — the ambient value is ignored |

Since `database.py:10` is the only place that selects the database, and the pin
is assigned before `main` is imported, the suite can no longer reach the live DB.

Additionally measured: a **full suite run writes nothing to the live config
tree**. Manifest captured immediately before and after `pytest server/tests/ -q`
— only `scheduler_status.json` (the live scheduler) differed.

### 3.4b Each new guard proven by removing it

Same discipline as the pin: markers are single-line so CRLF cannot break the byte
match, and every file is restored byte-for-byte and verified.

| guard removed | test | result |
|---|---|---|
| `conftest.py` DATABASE_URL pin | `TestSuiteNeverTouchesProduction` | 3 failed → restored → 3 passed |
| `ontology_config` routed via `paths.py` (re-hardcoded to `dirname(__file__)/config`) | `TestDataRootOverride` | 1 failed → restored → 2 passed |
| `if for_write and paths.IS_ISOLATED` in `main.py` | `TestIsolatedServerCannotWriteLiveMappers` | 3 failed + 2 fixture errors → restored → 5 passed |

`OVERALL: every guard is exercised`. And on the second run the injection left
`server/mappers/` byte- **and** mtime-identical — see §6.

### 3.5 Suite — 414/0 for my change, then a concurrent rewrite went red

`414 passed, 0 failed` was verified **twice** with the complete change set in
place: once right after the path refactor + conftest pin, and again at 23:48:00
as part of the "does pytest write to the live config tree" measurement.

At 23:52 and 23:55 a **concurrent editor rewrote `server/map_overlay.py`,
`server/bonding_plan.py` and `server/transfer_plan.py`** (removing the
`align_overrides` declaration layer — see §6). The suite then went to
33–42 failures, all inside `test_map_overlay.py`, `test_bonding_plan.py` and
`test_transfer_plan.py`, whose own mtimes are 08:52 / 20:14 / 18:24, i.e. they
still assert the contract that rewrite deleted.

Attribution is not a guess — two independent proofs:

**a. The refactor is a provable no-op with `ASSY_DATA_ROOT` unset.** Every
touched constant compared against the exact expression it replaced:

```
[OK] paths.DATA_ROOT / CONFIG_DIR / WORKSPACE_DIR / IS_ISOLATED(False)
[OK] map_overlay.CONFIG_PATH      [OK] bonding_plan.CONFIG_PATH
[OK] transfer_plan.CONFIG_PATH    [OK] enrichment_config.CONFIG_DIR
[OK] ontology_config.CONFIG_DIR   [OK] chain_worker.RULES_PATH
[OK] crud.CONFIG_PATH             [OK] auto_update_control.SERVER_DIR
[OK] auc.get_control_path()       [OK] auc.resolve_script_file()
RESULT: identical to pre-refactor paths
```

**b. The suite is green everywhere the concurrent rewrite did not reach:**

```
pytest server/tests/ --ignore=test_map_overlay --ignore=test_bonding_plan --ignore=test_transfer_plan
-> 300 passed, 0 failed      (290 before the 10 new tests)
```

**I did not touch those three files beyond the 2-line `paths` import each**, and
I have left the concurrent work alone. Re-run the full suite once it settles.

**Final count.** You asked for 416; the guards needed 10 tests, not 2, so my
contribution is **414 → 424**. The full run currently reports 426 total
(419 passed / 7 failed) — the extra 2 and all remaining failures are the
concurrent agent's, now confined to `test_bonding_plan.py` and
`test_transfer_plan.py` (`test_map_overlay.py` went green while I worked). Their
numbers move between runs because they are still editing.

---

## 4. What is deliberately NOT isolated, and why

| not isolated | why | residual risk |
|---|---|---|
| **`server/mappers/**` — relocation** | Loaded as the `mappers` Python *package* via `sys.path`, not by path construction. Relocating it means `sys.path` surgery across 5 processes — a much larger blast radius than the problem. | **Writes are now refused (403) when isolated** (§2.6), so the tree is unreachable rather than merely unlikely to be hit. Reads still resolve to the live files — deliberate, and harmless. |
| **pytest's config *reads*** | The suite still reads the live `table_config.json` at import. Writing was the incident; reading is not. Pointing `ASSY_DATA_ROOT` at a fixture tree would change which tables exist during collection and risks the exact `bonding_log`-style collisions already recorded in the lessons file. Measured (§3.4): the suite writes nothing there. | A user config change can still perturb the suite — an existing, documented coupling, unchanged by this work. |
| **`raws/` and `archives/` contents** | 9,400+ live pipeline files. Copying them would make bootstrap slow and the snapshot enormous, and the isolated watcher is not running to consume them anyway. | An ingestion test in the isolated env starts from an empty `raws/`. Drop a file in by hand. |
| **The production server** | Not restarted, not reconfigured. It is live and in use. | Production still churns. That is the environment, not a defect — the point is that agents no longer *measure* it. |
| **`database_outbox` history** | Snapshot starts empty. | Tests that need to observe outbox replay must generate their own events. |

---

## 5. Cost of refreshing the snapshot

| | |
|---|---|
| wall clock | **~3.5 min** (199 s and 219 s on two runs) |
| rows copied | 704,647 |
| snapshot DB size | **422 MB** (production: 13 GB) |
| `dev_env/` on disk | **346 KB** |
| load on production | read-only, one connection, `application_name=assy_devenv_snapshot_readonly`, streamed in 1,000-row chunks |

Refresh with `devenv.py snapshot`. Bootstrap the data tree again (after the user
changes their config) with `devenv.py bootstrap --force`.

Three bugs the verification caught that a "looks right" review would not have:

1. The read-only self-test failed on its own error handling: the guard matched
   the message string `"read-only"`, but PostgreSQL emits it in the OS locale
   (Korean here) so the check never matched. Now matched on SQLSTATE `25006`.
2. The side-table budget was spent first-come, so `core_defect_map` took 351k of
   the 400k `cell_sources` budget and every alphabetically later table —
   `eds_fail_map`, `dt_map`, `sample_map`, `wafer_map_metadata` — got **zero**
   layering rows. Replaced with max-min fair allocation across owner tables; all
   22 tables now have coverage.
3. My own `.gitignore` rule `dev_env/` was unanchored and therefore also ignored
   `server/scripts/dev_env/` — the tooling itself would have been silently
   untracked. Anchored to `/dev_env/`.

---

## 6. Not mine — flagging for the lead

**Someone else is editing the same working tree, live, including my domain.**

| files | mtime | mine? |
|---|---|---|
| `client2/{map_editor.html, src/map_editor.js, src/tokens.css, src/transfer_plan.css, src/transfer_plan.js}` | 23:45–23:48 | no — Client domain |
| `server/{map_overlay.py, bonding_plan.py, transfer_plan.py}` | 23:52–23:55 | **no** — beyond my 2-line `paths` import in each |
| `server/config/{bonding_plan,map_overlay,transfer_plan}_config.json.sample` | 23:58–23:59 | **no** — same rewrite's `.sample` counterparts |

The `server/` three are an in-flight rewrite removing the `align_overrides`
declaration layer ("정렬의 유일한 근거는 `wafer_map_metadata`"), and it is what
turned the suite red (§3.5). My last edit to any server file was 23:19:54; the
suite was green at 23:48:00.

**This matters for merging:** my diff and theirs are interleaved in the same
files. `git diff server/map_overlay.py` shows both changes at once. Please
separate them before committing, and re-run the full suite after that rewrite
lands. I deliberately did not touch or revert any of it.

`dev_env/ingestion_workspace/inventory_master/scripts/_devenv_probe.py` and the
`DEVENV_ISO_PROBE_*` rows in `assy_qa` are verification residue inside the
isolated environment; they vanish on the next `snapshot` / `bootstrap --force`.

### 6.1 I damaged a user file, and recovered it — full disclosure

Proving the `mappers/` guard required removing it and showing the test went red.
**That injected run did exactly what the guard exists to prevent**: with the
guard gone, the end-to-end test's `POST /admin/scripts/code` overwrote
`server/mappers/__init__.py` with `# CLOBBERED` (33 bytes → 12) and created a
probe file. `server/mappers/**` is gitignored user code.

Recovered, and verified rather than assumed:

- The `.pyc` in `__pycache__` proved the module body was empty
  (`co_consts=(None,)`, `co_names=()`) and recorded the original source size (33)
  and mtime.
- Five **pre-clobber manifest captures** all held the same fingerprint:
  `sha256=ff5ab66a…cad4, size=33, mtime=1780839067.4746883`.
- Commit `e03515f` (before the gitignore rule was added) still had the blob:
  `# Mappers package initialization\n` — sha256 **matches the manifest exactly**.
- Restored byte-identical, then `os.utime`'d back to the original mtime.

  First restore used the `.pyc` header's mtime, which stores **whole seconds
  only** — it landed on `1780839067.0`, off by 0.47 s. The manifest's float
  caught it (`2 DISTINCT states` on an otherwise identical file) and it was
  corrected to `1780839067.4746883`, now an exact match. Worth noting because
  the sloppy version would have passed a second-precision check.
- The probe file was removed only after asserting its content was mine.

`server/mappers/` is now byte- and mtime-identical to its pre-session state.
The manifest tool I built to prove I hadn't damaged anything is what let me
prove I had, and then repair it exactly — that is the argument for capturing a
fingerprint *before* starting, not after something looks wrong.

**The fix is in the test, not just the apology.** The mappers tests now run under
a `live_mappers_must_be_untouched` fixture that snapshots `server/mappers/**`,
repairs anything that changed (content, mtime, created, deleted) and *then*
asserts nothing changed. The primary guard was also moved down to the resolver,
where it needs no filesystem access at all. Re-running the same injection now
leaves the tree pristine while still reporting loudly (3 failures + 2 fixture
errors). Verified.

---

## 7. Proposed standing rule (do not apply — for review)

For the **shared section** of `agent_workspace/memory/*.md`:

> - **함정**: 사용자의 **운영 환경(라이브 DB·`server/config/**`·`server/ingestion_workspace/**`)에서 검증**한다. 수집기가 2분 크론으로 계속 쓰기 때문에 측정이 재현되지 않아, 에이전트가 자기 변경과 스케줄러의 변경을 구분하려고 유령을 쫓는다(2026-07-26: `created_at == updated_at`·6분 주기 분석 전량 폐기). 더 나쁜 것은 사고다 — 같은 날 `maps.json`과 워크스페이스 `config.json`이 테스트에 덮어써졌다.
>   **올바른 방법**: 검증은 **항상 격리 환경**에서 한다 — `python server/scripts/dev_env/devenv.py up` (API `:8081`, DB `assy_qa`, 데이터 루트 `dev_env/`, 워처·스케줄러 미기동). 운영 DB/설정에 대고 재는 순간 그 측정은 무효다. 격리 환경에는 **마음껏 써도 된다** — fetch shim·전후 해시·"나는 안 썼다" 증명 의식은 전부 불필요하다. 일회성 스크립트는 `devenv.py env`의 환경변수를 얹어 실행한다.
>   운영을 **읽어야만** 하는 경우(스냅샷 등)는 세션을 `SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY`로 열고 **쓰기가 SQLSTATE 25006으로 실패하는지 자기검증**한 뒤 진행한다.

One more for the **shared** section — earned the hard way in §6.1:

> - **함정**: **회귀 테스트가 자기가 지키는 대상을 파괴**한다. 가드를 제거해 테스트가 붉어지는지 확인하는 결함 주입은 옳지만, 그 주입 실행에서 테스트가 **라이브 사용자 파일에 실제로 쓴다**면 증명하는 순간 사고가 난다(2026-07-26: mappers 가드 주입 실행이 gitignored `server/mappers/__init__.py`를 덮어씀).
>   **올바른 방법**: ⓐ 1차 가드는 **파일시스템에 닿지 않는 지점**(리졸버·순수 함수)에서 검증하고, ⓑ 실제 쓰기를 태우는 E2E는 대상 트리를 스냅샷 → **복구 후 무변경 단언**하는 픽스처 아래에서만 돌린다. 가드가 깨져도 트리는 온전하고 신호는 남는다. 그리고 **작업 착수 전에 지문(sha256+mtime)을 떠 두라** — 사고가 났을 때 정확한 복구의 유일한 근거다.

Three smaller lessons proposed for the **server-pm** section:

> - **함정**: 무결성 증명의 **기준선(baseline) 파일을 공용 스크래치패드에 흔한 이름으로** 두면 병렬 에이전트가 같은 이름으로 덮어써, 증명의 근거가 조용히 사라진다(2026-07-26: `prod_before.json`이 00:13에 덮어써짐 — 23:11 캡처가 23:58 mtime을 담고 있어 발각).
>   **올바른 방법**: 기준선 파일명에 타임스탬프·태스크 식별자를 넣고, 인용 전에 **`captured_at`이 판정 대상 사건보다 앞서는지 확인**한다. 캡처는 한 번이 아니라 구간마다 남겨 하나가 소실돼도 브래킷이 유지되게 한다.

> - **함정**: PostgreSQL 오류를 **메시지 문자열로 판별**하면 서버 로케일(여기선 한국어)에서 조용히 빗나간다 — 읽기전용 가드 자기검증이 실제로는 아무것도 검증하지 못했다.
>   **올바른 방법**: `e.orig.pgcode`(SQLSTATE)로 판별한다. 읽기전용은 `25006`.
> - **함정**: `.gitignore`에 앵커 없는 디렉터리 규칙(`dev_env/`)을 쓰면 **같은 이름의 하위 디렉터리까지 전부** 무시된다 — 생성물을 무시하려다 도구 소스(`server/scripts/dev_env/`)가 통째로 추적에서 빠졌다.
>   **올바른 방법**: 루트 산출물은 `/dev_env/`로 앵커. 규칙 추가 후 `git status -uall`로 의도한 파일이 보이는지 확인.

---

## 8. Handover

**Changed** — `server/paths.py` (new); path override wired into 20 modules;
`server/tests/conftest.py` (DB pin); `server/main.py` `_resolve_admin_script_path`
(`for_write` + 403 when isolated); `server/tests/test_dev_env_isolation.py` (new,
10 tests); `.gitignore` (`/dev_env/`);
`server/scripts/dev_env/{devenv,snapshot_db,manifest}.py` (new).

**Verified** — isolated API serves the snapshot; a deliberate write leaves
production byte- and mtime-identical; 420 s idle window with zero movement; the
conftest pin, the `paths.py` wiring and the `mappers/` 403 each proven by
removing them and watching the tests go red; suite 300/300 outside the
concurrently-rewritten modules (414 → 424 from my side).

**Open / next**

1. Merge — my diff is interleaved with a concurrent agent's in
   `map_overlay.py`, `bonding_plan.py`, `transfer_plan.py` and three
   `.sample` files (§6). Remaining suite failures are all theirs.
2. §7 memory rules await your review; three proposed, one of them earned by the
   §6.1 incident.
3. Nothing committed, per instruction.
