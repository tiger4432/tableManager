# Server — Isolated dev environment: closing F1 and F2

> Domain: Server (backend) · 2026-07-27 · branch `main`, **not committed**
> Fixes the two gaps `QA_p2_drills_isolated.md` found the first time anyone actually
> used the environment built in `Server_dev_env_isolation.md`.

| | |
|---|---|
| suite | **498 passed / 0 failed** (measured 3×) |
| my contribution | **exactly +28** — A/B on the current tree: 470 without my six files, 498 with |
| guards proven by removal | **7 / 7** turned red, all restored byte-identical |
| production written to | none. Same 6 pids at start and end; live logs carry zero lines of mine |

---

## 1. What changed

| file | change |
|---|---|
| `server/paths.py` | new `log_path(filename)` — process logs resolve inside `DATA_ROOT` |
| `server/utils/logger.py` | file handler routed through `paths.log_path()` instead of its own `__file__`; `import paths` with the `crud.py` try/except fallback |
| `server/graph_sync_worker.py` | **`VIRTUAL_GRAPH_PATH`** routed through `paths.DATA_ROOT` (F1's sibling — §4) |
| `server/parsers/directory_watcher.py` | removed a dead `log_path = join(server_dir, "watcher.log")` — unused since the unified logger, and a trap of exactly the shape F1 was |
| `server/scripts/dev_env/iso_watcher.py` | **new** — the gated watcher entry point |
| `server/scripts/dev_env/devenv.py` | new `watcher-up` / `watcher-down`; `down` and `status` now cover the watcher |
| `server/tests/test_dev_env_isolation.py` | 10 → 38 tests |

No second mechanism was introduced. `ASSY_DATA_ROOT` remains the only override, and
`paths.py` remains the only place that reads it.

### 1.1 F1 — logs follow the data root

```python
# server/paths.py
def log_path(filename):
    return os.path.join(DATA_ROOT, filename)

# server/utils/logger.py  (was: dirname(dirname(abspath(__file__))))
log_path = paths.log_path(log_filename)
os.makedirs(os.path.dirname(log_path), exist_ok=True)
```

Unset `ASSY_DATA_ROOT` → `DATA_ROOT == SERVER_DIR` → `server/server.log`, i.e.
production's layout is unchanged, asserted by
`test_unset_data_root_keeps_the_production_log_location`.

One import-order detail worth recording: `main.py` imports `utils.logger` at line 19
but `paths` at line 34, so `logger.py` cannot assume `server/` is already on
`sys.path`. It uses the same try/except fallback `database/crud.py` uses rather than
silently reverting to a `__file__`-relative directory — a fallback that quietly
returned the live tree would reintroduce the bug in exactly the case that matters.

### 1.2 F2 — a watcher that cannot be pointed at production

`devenv.py watcher-up` / `watcher-down`. `up` still starts no watcher and no
scheduler — that is asserted by a test now, so the churn-free guarantee cannot
erode by accident.

The rail is in `server/scripts/dev_env/iso_watcher.py`, and four properties make it
structural rather than advisory:

1. **The gate is a pure function.** `check_static_isolation` / `check_live_isolation`
   take resolved facts and return a list of violations. A test can hand it
   production-shaped facts and assert the refusal with no process, no connection and
   no filesystem anywhere near the decision.
2. **It runs before anything that touches disk.** `import run_watcher` alone opens a
   log file, issues DDL and resolves the workspace it will watch, so that import
   lives inside `_start_watcher()` and nowhere else. An AST test enforces it.
3. **The live check asks an opened session**, per the P2 team's design:
   `SELECT current_database()` from a real `SessionLocal()`, not a string parsed out
   of the environment variable this process just read. A URL that says `assy_qa` but
   resolves elsewhere is caught, and `str(engine.url)` is read from the engine the
   watcher's own pool will use rather than from `os.environ`.
4. **The failure mode is "does not start."** Every refusal returns exit 9 before a
   watchdog handler exists. *Being unable to prove* isolation — unreachable database,
   unparseable URL, missing workspace — is itself a refusal, never a warning.

Ordering matters and is deliberate: the static gate rejects a production-named
database *before* any connection is opened, so a production-pointed launcher never
even contacts production. The live probe is the second rail, not the first.

`devenv.py watcher-up` additionally runs the gate once in `--check-only` mode so a
refusal lands in the operator's terminal instead of a log file. That pre-flight is a
convenience; the load-bearing gate is the one the real process runs on itself, and
the two are visibly different processes (§3.2: `backend_pid=35464` vs `8996`).

---

## 2. F1 proof

The production stack was **running throughout** (6 pids, appending to `server/*.log`
every few seconds), so the measurement is content attribution, not just flatness:
every byte a live log gained during the window was extracted and read.

### 2.1 Window 1 — 05:20:12 → 05:20:27, `devenv up` + traffic on :8081

```
                        BEFORE                              AFTER
server/auto_update.log  6,296,270  f90eb1a59597   BYTE + MTIME IDENTICAL
server/chain_worker.log 3,207,938  ff39882dfafd   BYTE + MTIME IDENTICAL
server/graph_sync.log   1,578,980  54d56ebb1696   BYTE + MTIME IDENTICAL
server/server.log      11,891,566  c45ee0fb9a81   BYTE + MTIME IDENTICAL
server/watcher.log     18,504,508  b7cbd0331f6d   BYTE + MTIME IDENTICAL

dev_env/server.log        NEW  +405 B   markers {dev_env: 1, assy_qa: 1, isolated=True: 1}
dev_env/chain_worker.log  NEW  +1,267 B
dev_env/graph_sync.log    NEW  +793 B   markers {8091: 1}
```

`dev_env/server.log` line 1 is
`[paths] data_root=…\dev_env isolated=True db=postgresql://…/assy_qa` — the exact
line that used to land in the user's `server/server.log`.

### 2.2 Window 2 — the sensitivity control

Window 1's flat reading is only worth something if the instrument can register
movement on **those same files**. Window 2 (≈4.5 min, spanning the live collectors'
2–3 min cron) supplies it:

```
server/auto_update.log   +5,244 B    isolated markers appended: NONE   whole-file delta: zero
server/chain_worker.log  +4,588 B    isolated markers appended: NONE   whole-file delta: zero
server/graph_sync.log    +1,723 B    isolated markers appended: NONE   whole-file delta: zero
server/server.log      +223,581 B    isolated markers appended: NONE   whole-file delta: zero
server/watcher.log      +14,003 B    isolated markers appended: NONE   whole-file delta: zero

live logs that moved: 5/5     live logs with zero isolated content: 5/5
```

All five moved — the fingerprint is provably awake on exactly the files that read
"identical" in window 1 — and the 249 KB they gained contains **zero** occurrences of
`dev_env`, `assy_qa`, `isolated=True`, `8081` or `8091`, while the isolated stack ran
throughout. Both halves of the claim are measured on the same instrument.

(Window 1's usual control, `config/scheduler_status.json`, did not move in those
15 seconds; window 2 supersedes it with a stronger one on the files under test.)

### 2.3 The live logs still carry the *previous* session's lines — left alone

Not cleaned, per instruction. The numbers, so the decision can be made on evidence:

| file | residual occurrences |
|---|---|
| `server/server.log` | **219** — `p2drill` ×207, `dev_env` ×4, `assy_qa` ×4, `isolated=True` ×4 |
| `server/chain_worker.log` | **12** — `p2d3-` ×10, `DEVENV_ISO_PROBE` ×2 |
| `graph_sync.log`, `watcher.log`, `auto_update.log` | 0 |

**My recommendation: leave them.** They are append-only, they are dated, and a log
whose history has been edited is worth less than one with a known contaminated
window — a reviewer who knows "2026-07-26 23:00 → 2026-07-27 01:30 contains isolated
lines" can read around it, whereas a rewritten file cannot be trusted anywhere. If
you disagree, the discriminators above are exact and a filtered copy is trivial; but
the live server holds these files open, so any edit needs the stack down.

---

## 3. F2 proof

### 3.1 Three negatives — each isolates one production vector, none can reach production

| | configuration | result |
|---|---|---|
| **N1** | live data root + a database named `assy_manager` **on 127.0.0.1:1** | exit **9**, 6 violations |
| **N2** | live data root only — database is the *isolated* `assy_qa` | exit **9**, 4 violations |
| **N3** | fully isolated except `API_BASE_URL` on production port 8080 | exit **9**, 2 violations |

N1's port is 1 because a negative test must not be able to cause the incident it
describes: nothing listens there, so even a gate that let this through could not
reach the production database. N2 and N3 involve no production endpoint at all —
N2 proves the *workspace* alone is disqualifying, N3 proves the *event sink* is too.

```
--- N1
[iso-watcher] paths.IS_ISOLATED    = False
[iso-watcher] engine.url           = postgresql://postgres:***@127.0.0.1:1/assy_manager
[iso-watcher] REFUSED TO START - 6 isolation assertion(s) failed:
  1. ASSY_DATA_ROOT does not relocate the data root: paths.IS_ISOLATED is False, so
     config/ and ingestion_workspace/ resolve to the LIVE tree (…\server). The
     watcher would ingest into the user's real workspace.
  2. data root resolves inside the live server tree: …\server
  3. config dir resolves inside the live server tree: …\server\config
  4. ingestion workspace resolves inside the live server tree: …\server\ingestion_workspace
[iso-watcher] No watchdog handler was registered and no ingestion code was imported.
              Nothing was started.
```

### 3.2 The positive — the same binary, pointed at the isolated environment

```
[devenv] running the isolation gate...
[iso-watcher] LIVE CONNECTION -> current_database='assy_qa' user='postgres' port=5432 backend_pid=35464
[iso-watcher] ALL TARGET ASSERTIONS PASSED - starting watcher
[devenv] started watcher pid=37696

   the REAL process's own gate output (dev_env/logs/watcher_stdout.log):
[iso-watcher] LIVE CONNECTION -> current_database='assy_qa' user='postgres' port=5432 backend_pid=8996
[iso-watcher] ALL TARGET ASSERTIONS PASSED - starting watcher

   watches registered by the running watcher: 25
       …\dev_env\ingestion_workspace\bonding_log\raws
       …\dev_env\ingestion_workspace\bonding_map\raws
       …\dev_env\ingestion_workspace\core_defect_map\raws
   watches pointing INTO the live server tree: 0
   dev_env/watcher.log grew: 13,579 bytes
```

Two backend pids, **35464** and **8996**, are the load-bearing detail: the pre-flight
and the process that actually watches are different processes, and the one holding
the watchdog handlers proved its own database from its own connection pool.
25 watches registered, **0** of them inside the live tree.

`devenv down` then stopped the watcher along with api/chain/graph, and the six
production pids observed at session start (33192, 24480, 32352, 45956, 30300, 47380)
were verified still running immediately afterwards.

**The production stack was later restarted — not by me.** At 05:32:41 all six pids
were replaced (1840, 43636, 50156, 46588, 47780, 42036). The evidence that it is the
concurrent agent's restart, not mine:

- the only kill I issued all session was `devenv down`, whose own output names the
  four pids it stopped (37696, 36964, 27872, 38184) — every one of them spawned by my
  `devenv up` minutes earlier;
- I verified the original six alive **after** that `devenv down`;
- uvicorn runs without `--reload`, so nothing I edited could restart it;
- the restart timestamp coincides with commit `08d2b12`
  *"feat(crud): warn once when an update drops an undeclared column"*, which changes
  `server/database/crud.py` — a module every server process loads at import, i.e. a
  change that requires a restart to take effect;
- and the live `server/server.log` at 05:34:52 shows **that commit's brand-new
  feature firing**, with its author's probe column names:
  `[Schema] Column 'ghost_b' is not declared in column_types … was DROPPED`,
  `Reached 3 distinct undeclared columns for table 'inventory_master'`.

Production is healthy (`GET :8080/tables` → 200).

### 3.3 Every guard proven by removing it

Injections are on **pure functions and source-level structure only**. None starts a
process or issues a write, so — unlike the incident in the last session's §6.1 — a
broken guard here cannot cause the damage it exists to prevent.

| guard removed | test | injected | restored |
|---|---|---|---|
| logger routed through `paths.log_path` | `TestProcessLogsFollowTheDataRoot` | **RED** (1 failed + 1 fixture error) | 2 passed |
| `VIRTUAL_GRAPH_PATH` via `paths.DATA_ROOT` | `TestVirtualGraphFollowsTheDataRoot` | **RED** | 1 passed |
| gate rule: production database name | `…GateIsAPureDecision` | **RED** 2 failed | 18 passed |
| gate rule: `ASSY_DATA_ROOT` not isolated | `…GateIsAPureDecision` | **RED** 2 failed | 18 passed |
| gate rule: production API port | `…GateIsAPureDecision` | **RED** 3 failed | 18 passed |
| live check: connection on production | `…GateIsAPureDecision` | **RED** 1 failed | 18 passed |
| `run_watcher` imported only after the gate | `…RefusalIsStructural` | **RED** 2 failed | 4 passed |

`OVERALL: every guard is exercised.` All seven restored with **identical sha256**
(the harness reads and writes binary and matches the file's own line-ending flavour —
a text-mode rewrite would leave `git diff` clean while the bytes differ).

The logger injection is the interesting one: with the guard gone the probe wrote
`server/_devenv_logprobe_<uuid>.log` into the live tree, the fixture removed it and
failed loudly, and **zero** probe files remain. The fixture deliberately does *not*
snapshot-and-restore pre-existing `server/*.log` the way the mappers fixture does —
the live server is appending to those right now, and "restoring" one would destroy
lines the live server had just written. It only ever touches a uuid-named file that
cannot exist unless this test created it.

The eleven-way parametrized `test_each_rule_refuses_on_its_own` exists so a *single*
deleted rule shows up. An all-or-nothing production case stays red with ten rules
left and proves nothing about the eleventh.

---

## 4. Sweep: other modules that escape `paths.py`

Assumed there were siblings, and there was one of the same severity class.

### 4.1 Fixed — a long-running process that **writes**

`server/graph_sync_worker.py:277`

```python
VIRTUAL_GRAPH_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "database", "virtual_graph.json"))
```

Worse than the log bug: `save_virtual_graph()` **overwrites** it (not append), and
`run_graph_sync.py` is one of the three processes `devenv up` starts. The module
already imports `paths` — `ONTOLOGY_PATH` two lines above it uses `paths.config_path`
— so this one constant was simply missed. Now `paths.DATA_ROOT/database/virtual_graph.json`,
which is byte-identical to the old value when `ASSY_DATA_ROOT` is unset.

### 4.2 Fixed — dead, but a trap

`server/parsers/directory_watcher.py:25` held an unused
`log_path = os.path.join(server_dir, "watcher.log")`. Nothing imports it. Removed
rather than left for the next person to pick up.

### 4.3 Not fixed — manual scripts, reported for a decision

None of these run in a process; they escape only when a human runs them. The first
is the one I would act on:

| file:line | what it does |
|---|---|
| `server/scratch/generate_large_table.py:10,39-80` | **writes** the live `config/table_config.json`, `os.makedirs` a live workspace, and drops a generated CSV into the **live watcher's `raws/`** — running this against an isolated env still feeds production. The most dangerous script in the tree. |
| `server/scripts/migrate_assets.py:67,88-95` | `shutil.copytree` into `server/config` + `server/ingestion_workspace` wholesale |
| `server/scripts/reapply_chain.py:8`, `scripts/migrate_jsonb_to_rdb.py:7`, `scripts/archive/profile_fetch.py:49` | read the live `table_config.json` |
| `server/migrations/migrate_jsonb_numeric.py:6` | reads `server/migrations/server/config/…` — escapes *and* is simply wrong; the path never exists, so the script is dead on arrival |
| `server/scripts/migrate_to_postgres.py:12` | reads `server_root/assy_manager.db` |
| `server/tests/verify_advanced_ingestion.py:10` | hardcoded **relative** `server/ingestion_workspace/inventory_master` — the only literal of its kind. Not collected by pytest (`verify_*`, not `test_*`). |
| `server/scratch/generate_random_rows.py:24` | `to_csv('inventory_master.csv')`, cwd-relative |
| `server/scripts/install_product_tables.py:55,505` | `--sample` mode writes `server/config/table_config.json.sample` + a `.bak` sibling into the real config dir even under `ASSY_DATA_ROOT`. Defensible (the `.sample` is git-tracked, i.e. code) but worth a deliberate call. **Not touched — another agent owns this file.** |

Deliberately correct and left alone: `main.py`'s `client2/dist`, `mappers/` and
`admin.html` resolution (code and static assets, not data — and `mappers/` writes are
already refused while isolated), plus `devenv/manifest/snapshot_db` referencing the
live `SERVER_DIR` on purpose, since that is the tooling that *creates* the copy.
70 `sys.path` manipulations across 57 files are code location, not data location.

Verified clean, i.e. every data path already through `paths`: `run_auto_update.py`,
`database/crud.py`, `chain_ingestion_worker.py`, `enrichment_config.py`,
`ontology_config.py`, `bonding_plan.py`, `map_overlay.py`, `transfer_plan.py`,
`utils/auto_update_control.py`, all of `setup/`, and every `main.py`
config/workspace endpoint.

---

## 5. Observation: the suite writes one line into the live `server/server.log`

Measured, not inferred:

```
[paths] data_root lines in LIVE server/server.log: before=186 after=187 delta=1
[Server] [2026-07-27 05:35:21,663] INFO - [paths] data_root=…\server isolated=False db=sqlite:///:memory:
```

`conftest.py` pins `DATABASE_URL` but not `ASSY_DATA_ROOT`, so `from main import app`
logs its startup banner into the user's live log — **186 such lines have already
accumulated**. Pre-existing (`main.py:37`, commit `4ba13ae`), append-only, unchanged
by this work, and I did **not** fix it because every available fix is worse than the
problem:

- pinning `ASSY_DATA_ROOT` in `conftest.py` relocates config *reads* too, which
  changes which tables exist at collection time — the `bonding_log`-style collision
  already in the lessons file, and a decision the previous agent took deliberately;
- a log-only override would be the second mechanism this task rules out.

Wants a deliberate decision, like F1 did. Flagging, not deciding.

---

## 6. Suite

| measurement | number |
|---|---|
| session-start baseline (05:12, my two edits stashed) | **461 passed / 0 failed** |
| tree as it is now, my six files stashed | **470 passed / 0 failed** |
| tree as it is now, my changes in | **498 passed / 0 failed** |
| **my contribution** | **+28**, exactly the 28 tests I added (`test_dev_env_isolation.py` 10 → 38) |

The task quoted 457 on `4ba13ae`; this tree has moved since. **Two** concurrent
commits landed mid-session — `8e80fcc` (product-owned table declarations) and
`08d2b12` (undeclared-column warning in `crud.py`, +4 tests) — which accounts for
461 → 470, so the session-start baseline is no longer a valid comparator. Hence the
A/B on the tree as it stands, which is the only honest attribution. Their files were
never touched; the stash was scoped to my six paths and `git diff --stat` was
identical before and after (599 insertions / 45 deletions). The working tree now
holds **only** my files — both concurrent changes are committed, so this diff is
clean to review, unlike the interleaved one the last session had to hand over.

One artefact: the stash round-trip normalised `devenv.py`, `test_dev_env_isolation.py`
and `paths.py` from LF to CRLF (autocrlf). Content is identical — verified by
`git diff --stat` — and CRLF matches the rest of the repo. `iso_watcher.py` is
untracked and remains LF; git will normalise it on commit.

---

## 7. Proposed lessons (not applied — for review)

**Shared section:**

> - **함정**: 격리는 "데이터 트리"만 옮기면 끝난 것처럼 보이지만, **프로세스가 디스크에 쓰는 것은 config/workspace만이 아니다**. 로그 파일(`utils/logger`)과 그래프 저장소(`graph_sync_worker.VIRTUAL_GRAPH_PATH`)가 각각 자기 `__file__`로 경로를 만들어 `ASSY_DATA_ROOT`를 우회했고, 후자는 append가 아니라 **덮어쓰기**였다(2026-07-27 실측: 운영 `server/server.log`에 격리 세션 흔적 219건).
>   **올바른 방법**: 새 경로 상수를 만들 때 판단 기준은 "config인가"가 아니라 **"이 프로세스가 이 경로에 쓰는가"**다. 쓰면 `paths.py`를 통과시킨다. 그리고 격리 작업을 마칠 때 `__file__` 기반 경로를 **전수 스윕**해 (A) sys.path 조작 (B) 코드·정적자산 위치 (C) 데이터 읽기/쓰기 로 분류하라 — (C)만이 결함이고, 한 건이 발견되면 형제가 있다고 가정할 것.

> - **함정**: 회귀 테스트의 결함 주입이 **지키는 대상을 실제로 파괴**한다(2026-07-26 mappers 사고). 그러나 스냅샷-복구 픽스처도 만능이 아니다 — **운영 프로세스가 지금도 append 중인 파일**(`server/*.log`)을 "복구"하면 운영이 방금 쓴 줄이 사라진다.
>   **올바른 방법**: 결함 주입은 **순수 함수와 소스 구조(AST)** 에 한정하라 — 프로세스를 띄우지 않으므로 사고가 원천 봉쇄된다. 파일시스템을 태워야 한다면 픽스처가 손대는 대상을 **테스트가 직접 만든 uuid 이름 파일로 한정**하고, 기존 사용자 파일은 **보고만 하고 복구하지 마라**.

**server-pm section:**

> - **함정**: 운영 스택이 돌고 있는 동안 `server/*.log`에 "byte-identical"을 주장하면 창(window)에 따라 참이 되기도 거짓이 되기도 한다 — 라이브 프로세스가 몇 초마다 append하기 때문이다.
>   **올바른 방법**: 크기 기록 후 **증가분 바이트 구간만 잘라내 내용으로 귀속**하라(`f.seek(before_size)`). 그리고 창을 **라이브 크론 주기보다 길게** 한 번 더 잡아 "그 파일들이 실제로 움직인다"를 보이면, 짧은 창의 flat 판독이 비로소 의미를 갖는다. 통제군은 별개 파일이 아니라 **같은 파일의 다른 창**이 가장 강하다.
> - **함정**: 안전 가드를 프로세스 **바깥**(런처 부모)에서 검사하면 정작 위험한 일을 하는 자식 프로세스에 대해 아무것도 증명하지 못한다. 환경변수를 방금 설정했다는 사실도 증거가 아니다.
>   **올바른 방법**: 가드는 **자식 프로세스 안에서, 실제로 연 세션에 `SELECT current_database()`를 물어** 판정한다. 그리고 위험한 모듈의 import 자체가 부작용(로그 파일 생성·DDL·핸들러 등록)이므로 **import를 가드 통과 이후로 미루고, 그 순서를 AST 테스트로 고정**하라 — "가드가 있다"와 "가드를 우회할 수 없다"는 다른 명제다.
> - **함정**: 동시 작업 중인 트리에서 세션 시작 시점 스위트 수치를 기준선으로 쓰면 내 기여도를 틀리게 보고한다(본 세션: 기준선 461 → 타 에이전트 커밋·신규 테스트로 470).
>   **올바른 방법**: **지금 이 트리에서 내 파일만 stash한 A/B**로 측정한다. stash 범위를 내 경로로 한정하고, 복원 후 `git diff --stat` 동일성을 확인한다(autocrlf가 바이트를 바꾸므로 sha 비교만으로는 오탐이 난다).

---

## 8. Handover

**Changed** — `server/paths.py` (+`log_path`), `server/utils/logger.py`,
`server/graph_sync_worker.py`, `server/parsers/directory_watcher.py`,
`server/scripts/dev_env/devenv.py`, `server/tests/test_dev_env_isolation.py` (10→38);
new `server/scripts/dev_env/iso_watcher.py`.

**Verified** — isolated stack leaves all five live logs byte- and mtime-identical
while the relocated ones are created and grow, with a same-file sensitivity control
over a longer window; the watcher gate refuses three distinct production
configurations (exit 9) and runs against the isolated one with 25 watches and none in
the live tree; 7/7 guards red on removal and restored byte-identical; suite 498/0
with my contribution isolated at +28.

**Open / next**

1. **Not committed**, per instruction. My diff is disjoint from the concurrent
   agent's (`crud.py`, `test_undeclared_column_warning.py`) — no interleaving this
   time, unlike the last session.
2. Docs not updated (history entry, `gen_index.py`, `architecture/backend.md`) — the
   task scoped the deliverable to this report and the tree has an active concurrent
   editor. `devenv watcher-up/-down` and `paths.log_path` want a line in the dev-env
   docs when this merges.
3. §5 — the suite's one line per run into the live `server/server.log` needs a
   decision; every fix I can see is worse than the symptom.
4. §2.3 — the previous session's 231 residual lines in `server/server.log` and
   `server/chain_worker.log` are untouched. My recommendation is to leave them.
5. §4.3 — `server/scratch/generate_large_table.py` writes into the live watcher's
   `raws/`. Worth a board entry: it is a loaded gun for the next agent who wants a
   large test table.
6. QA's F3 (`resume_from_checkpoint` disables resuming, not checkpointing) and F4
   (a table removed from config is resurrected as an empty physical table) are
   untouched by this work and still open.
