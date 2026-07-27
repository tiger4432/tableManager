# DocAudit — cycle 5 (first run of the split documentation structure)

**Auditor:** doc-auditor · **Date:** 2026-07-27 · **Baseline:** HEAD `d56e7e2`
**Scope:** `d411386` (doc-keeper) · `87cbf35` (code-mapper) · `docs/history/20260727_*` (doc-historian) · post-doc drift from `cdcddee` + `d56e7e2` · grading pass over 49 living documents.
**I modified nothing.** No doc, no code, no config. Archival below is a recommendation only.

---

## Verdict

### 조건부 (Conditional)

**Basis:** the three agents' own work is sound where it was measured — every symbol reference in `PRIMITIVES.md` resolves, every server-side anchor in `CODE_MAP.md` lands within ±1 line, and all three counting corrections (`WARN_*`=14, `EFFECT_*`=5, overlay-clear=2) verify by full grep. What fails is everything the two post-doc commits touched: **a resolved blocker is still published as blocking in three documents, the supervisor's give-up rule is stated unconditionally in three documents when it is now conditional, and the DOE storage map describes a retired two-table model in the present tense while being a pre-flight document for the agent that owns DOE.**

Nothing found is a fabrication. Every defect is drift with a known cause and a known fix.

---

## Findings

Ordered by blast radius. `doc:line` then code evidence then how it is wrong.

---

### F1 — B3 is resolved in code; three living documents still publish it as blocking. **[HIGH]**

| Document | Line | Text |
|---|---|---|
| `docs/process/PRODUCTION_READINESS.md` | 11 | "남은 차단은 **B3 로그 배선**과 **B4 롤백 절차**다" |
| `docs/process/PRODUCTION_READINESS.md` | 19 | `\| 진단 로그 배선 \| 🔴 **차단** (B3) \|` |
| `docs/process/PRODUCTION_READINESS.md` | 51–54 | full B3 section, incl. "현재 다른 작업이 같은 파일에 있어 대기 중" |
| `docs/process/PRODUCTION_READINESS.md` | 107 | "⚠️ 단 B3 미해결로 워처에서는 안 보임" |
| `docs/process/PRODUCTION_READINESS.md` | 153 | "3. **B3** — 로그 배선." (still in the recommended work order) |
| `docs/guide/CONFIG_GUIDE.md` | 628 | "이 경고가 **워처 프로세스의 로그 파일에는 아직 안 남습니다** — PRODUCTION_READINESS B3" |
| `docs/guide/DEPLOY_SETUP.md` | 195 | "⚠️ 워처 프로세스 로그 배선은 PRODUCTION_READINESS B3로 미해결" |

**Code evidence — `server/utils/logger.py:82-101` (docstring of `get_process_logger`), resolved in `d56e7e2`:**

> `[B3] The handlers are attached to the ROOT logger, not to the named process logger, and this is the whole point of the function.` … `Blocker B3.`

`logger.py:107-130` moves both handlers onto the root logger; `server/tests/test_process_logging.py` (207 lines, new in `d56e7e2`) pins it.

**How it is wrong:** `PRODUCTION_READINESS` is the document whose single job is answering "what still blocks deployment." It over-reports the blocker count by one and puts a completed item at position 3 of a 6-item work order. `CONFIG_GUIDE` and `DEPLOY_SETUP` inherited the claim by cross-reference, so the false statement is in three files.

**SSOT conflict:** the committed board already has this right — `docs/process/PROJECT_STATUS.md:53` reads "**해소**: B1 · B2(`8117456`) · **B3 워커 로그 배선**(`d56e7e2`)" and `:54` "**남은 차단**: **B4**". Two living documents state opposite facts about the same gate. Per `docs/README.md` the board is the status SSOT, so `PRODUCTION_READINESS` is the wrong one.

---

### F2 — "6th consecutive failure → permanent FAILED" is now conditional. Three documents state it unconditionally. **[HIGH]**

| Document | Line | Text |
|---|---|---|
| `docs/architecture/PRIMITIVES.md` | 147 | "정해진 횟수를 넘기면 **영구 `FAILED`**로 확정하고 … **다시는 살리지 않는다**" |
| `docs/architecture/backend.md` | ~43 (§1.3) | "**6번째 연속 실패에서 `FAILED` 확정, 이후 재기동 없음**" |
| `docs/process/PRODUCTION_READINESS.md` | 31 | "**6번째 연속 실패에서 `FAILED`로 확정**하고 다시는 살리지 않는다" |
| `docs/qa/FEATURE_CHECKLIST.md` | 143 | "**6번째 연속 실패에서 영구 `FAILED`**(배너 로그 + `/health` 503)" |

**Code evidence — `server/process_supervisor.py:446-462`:**

```python
if child.consecutive_failures > self.max_consecutive_failures:
    peers = self._peers_failed_recently(child, now)
    env_down, env_detail = False, None
    if len(peers) + 1 < self.correlated_min_children:
        try:
            env_down, env_detail = self.environment_probe()
        ...
    if len(peers) + 1 >= self.correlated_min_children or env_down:
        self._enter_correlated(child, now, peers, exit_code, env_detail)
    else:
        self._fail_permanently(child, exit_code, reason)
```

Permanent failure now requires the child to fail **alone**. Otherwise it enters `STATE_RETRYING_CORRELATED` (`:133`) — "retried **indefinitely**, never permanently failed" (`:54`), fixed 60 s backoff (`CORRELATED_BACKOFF_SEC`, `:126`).

**How it is wrong:** this is not a detail — it inverts the property the documents are selling. `PRIMITIVES.md:147` heads its entry "**유한** 재시작 예산" and its first trap reads "무한 재시작은 최악이다"; the code now performs unbounded retry deliberately, for a reason the entry never states. An agent reading `PRIMITIVES` before building a retry loop gets the pre-`d56e7e2` design and, following the catalog's own rule ("같은 이름·같은 형태로 만든다"), would copy a shape the system has since rejected.

**Also missing from all four:** the new supervisor state (`retrying_correlated`), the `shared_dependency_down()` port probe (`process_supervisor.py:163`) and its measured justification (cold start with PostgreSQL down kills exactly one child — the web server, because `main.py` runs `create_all` at import — so a peer-only rule would have permanently failed it at t+94 s), and `/health`'s new `supervisor.status = "correlated_failure"` branch (`server/health.py:139-147`).

---

### F3 — `DOE_STORAGE_MAP.md` describes a retired model in the present tense, and it is a pre-flight document for `map-pm`. **[HIGH]**

`cdcddee` (08:00:28) collapsed three tables into one. `map_doe` and `map_doe_source` are retired.

**Code evidence:**
- `server/product_tables.py:97` — `"[DEPRECATED 2026-07-27 — M2.6] Nothing writes this table any more"` (`map_doe`); `:138` same for `map_doe_source`.
- `client2/src/map_editor.js:163` — `// [M2.6] 하나의 값 = 하나의 행 = 하나의 DOE. map_doe / map_doe_source는 폐기됐고`
- `client2/src/transfer_plan.js:14` — same statement.

**Document claims now false:**

| Line | Claim | Reality |
|---|---|---|
| 8 | "아래 서술은 **현재 커밋된 동작**이며 **지금 화면에서 실제로 일어나는 일**입니다" | The committed client no longer does it. Per the board (`PROJECT_STATUS` §현재 초점 2) the screen does not work at all yet — `bands` has no physical column. |
| 9 | "**착지 전이므로**…" | It landed 8 hours before this audit. |
| 16, 19–25 | "DOE 패널 하나를 편집하면 **세 곳**에 나뉘어 저장된다" + the 3-branch diagram | Two: `map_split_registry` (value row incl. `bands` JSON) + the map table itself. |
| 47–67 | `## 2. map_doe` — full column table, present tense | Table is DEPRECATED, nothing writes it. |
| 71–91 | `## 3. map_doe_source` — full column table, present tense | Same. |
| 106 | "헤더에 `서버 <시각>`으로 뜨는 값은 **`map_doe`에서 읽어온** `eventtime`" | `map_doe` is not read. |
| 113 | "범위는 **세 테이블 모두** `map_key_columns = (ref_table, map_key)`로 잡힌다" | Only one is a live write scope. |
| 124 | "**형제 안전성이 사라졌다** … 동시 편집은 PRODUCTION_READINESS C2" | `cdcddee` added a re-read + fingerprint refusal on this exact path (`map_editor.js:2322-2357`, user-visible string `:2395`). The doc records the hole and not the fix. |
| **134** | "`map_doe`가 테이블 드롭다운에 없다 = 안 쓰는 건가? → **쓴다.**" | **Directly contradicted by `product_tables.py:97`.** This is the single most quotable false sentence in the living set: it is in a FAQ, it is bolded, and it answers a question the reader asked *because they already suspected the truth*. |
| 137 | "현재는 구간 수량을 자재 수로 **올림 배분**한다(`bandShare`)" | `bandShare` survives (`transfer_plan.js:201`) but M2.6's contract is "NOTHING derived is stored" — quantity and share are computed, never persisted (`product_tables.py:61`). |

**Why the banner shape is wrong (answering the brief's question directly):** the banner at lines 7–10 says *"changing — this is the committed state — the board is authoritative until it lands."* That was correct when written and is now the opposite of the situation. The change **landed**; the body is the **superseded** model, not the committed one. A reader who trusts the banner concludes the body is safe to build on today. It is not.

**Why this outranks a normal stale doc:** `.claude/agents/map-pm.md` names `docs/spec/DOE_STORAGE_MAP.md` in its charter — it is loaded on every map/DOE dispatch. Queue item 1 is "서버 `transfer_plan.py`를 M2.6 `bands` JSON 계약에 맞춤." The next agent to touch DOE loads this document first.

**F3b — the same retirement leaks into `PRIMITIVES.md`, where the example carries the whole entry:**

- `PRIMITIVES.md:41` — the primitive **"정체는 안정된 것에, 라벨은 자유롭게"** cites exactly one location: `map_doe.band_seq`(키) vs `stack_band`(자유 텍스트 라벨). Both the table and the column are retired — `cdcddee` replaced the free-text band with two integers precisely because the label could not be parsed. The *principle* survives M2.6 (`seq` is still identity — `product_tables.py:61`: "`seq` is the band's IDENTITY … never renumber on reorder or delete"), so the entry needs a new **어디**, not deletion. As written, an agent that follows PRIMITIVES' own rule ("유사한 것이 있으면 같은 이름·같은 형태로 만든다") is sent to read a dead table for the pattern.
- `PRIMITIVES.md:55` — lists `map_doe` first among product-owned tables. Still declared, so DEPRECATED rather than absent; weaker, but it is the lead example.
- `PRIMITIVES.md:28` — "`map_doe`가 이 경로로 `eventtime`을 잃고 있었다" is a past-tense incident citation and remains **correct**; do not touch it.
- `PRIMITIVES.md:14` — "소비: 맵 Push · **DOE 저장 · legend 저장**(2026-07-27 편입)". After M2.6 these are one write, not two.

---

### F4 — `CODE_MAP.md`'s client anchors were already stale at the moment they were committed. **[MEDIUM-HIGH]**

`CODE_MAP.md:8` sets the contract: *"라인 앵커는 HEAD `be58210` 기준 **±20줄 오차 허용**."* `cdcddee` landed at **08:00:28**; `87cbf35` committed the map at **08:07:49** measured against `be58210`. `client2/src/map_editor.js` went 4,563 → 4,866 lines (+303) and `client2/src/transfer_plan.js` 1,425 → 1,113 (−312) in between.

Measured drift at HEAD (`grep` of each symbol's definition line):

| Symbol | CODE_MAP | HEAD | Drift |
|---|---|---|---|
| `withPhysFrame` (:595) | ~972 | 1117 | **+145** |
| `renderGridCanvas` (:596) | ~1603 | 1748 | **+145** |
| `switchTable` clear call (:615) | ~819 | 964 | **+145** |
| `loadExistingMap` clear call (:615) | ~2563 | 2871 | **+308** |
| `openMapFrame` (:601) | ~3804 | 4105 | **+301** |
| `projectCellsToPhys` (:606) | ~4001 | 4304 | **+303** |
| `OVERLAY_CELL_LIMIT` (:608) | ~4041 | 4344 | **+303** |
| `addOverlayLayer` (:609) | ~4096 | 4399 | **+303** |
| `clearOverlayLayers` (:610) | ~4306 | 4609 | **+303** |
| `importOverlayToGrid` (:613) | ~4392 | 4695 | **+303** |
| `renderOverlayList` (:614) | ~4463 | 4766 | **+303** |
| `getSourceSummary` (:634) | ~327 | 284 | **−43** |
| `availabilityOf` (:634) | ~364 | 318 | **−46** |
| `availableOf` (:634) | ~391 | 345 | **−46** |
| `probeMaterialMap` (:634) | ~413 | 369 | **−44** |

Also `:593` "`map_editor.js` (~4,563줄)" → 4,866; `:618` "`transfer_plan.js` (~1,425줄)" → 1,113.

**How it is wrong:** 7–15× the document's own declared tolerance. `CODE_MAP.md:7` instructs readers to `Read(offset, limit)` the section the map points at instead of the file — a reader who obeys reads 300 lines of the wrong function. The `be58210` label in the header is honest but does not repair the instruction, because the instruction is what the reader acts on.

**Note on the trade-off:** code-mapper measured against a commit rather than a working tree that two other agents were editing. That was the right call for correctness of what it measured. The cost was that the map shipped stale, and only the commit message records it.

---

### F5 — The five §5 ops modules carry a "needs a re-pass" caveat that exists only in the commit message. **[MEDIUM]**

`87cbf35`'s message: *"Those five ops modules have edits in flight, so they need a re-pass once that batch lands."* That warning is **not in the document**. Only `product_tables.py` carries an in-document M2.6 banner (`CODE_MAP.md:343`).

Measured staleness at HEAD:

| CODE_MAP | Claim | HEAD |
|---|---|---|
| `:286` | `process_supervisor.py` (**431줄**) | **709** |
| `:307` | `health.py` (**280줄**) | **323** |
| `:318` | `utils/heartbeat.py` (**174줄**) | **303** |
| `:22` | `directory_watcher.py` ~1,714 | **1,764** |

Specific claims now incomplete or wrong:

- `:290` `STATE_RUNNING|BACKOFF|FAILED|STOPPED` — a 5th state exists, `STATE_RETRYING_CORRELATED` (`process_supervisor.py:133`). Absent: `shared_dependency_down()` (`:163`), `psutil_status()` (`:195`), `CORRELATION_WINDOW_SEC`/`CORRELATED_MIN_CHILDREN`/`CORRELATED_BACKOFF_SEC` (`:119-126`).
- `:322` `read_all(stale_after, now=None)` — actual signature is `read_all(stale_after=DEFAULT_STALE_AFTER_SEC, now=None, stall_after=DEFAULT_STALL_AFTER_SEC)` (`heartbeat.py:248`). The entire work-claim API is undocumented: `work_claim(name, what)` (`:217`), `open_claims()` (`:242`), `_work_snapshot_locked` (`:198`).
- `:328` "비트 이름 4종: `watcher`(`run_watcher.poll_pending_retries` ~154)". The anchor still resolves (`beat("watcher")` at `run_watcher.py:161`, enclosing function `poll_pending_retries` at `:145` — I resolved the enclosing function, not the line). But `d56e7e2` moved the watcher's real signal into the ingestion path: `HEARTBEAT_NAME = "watcher"` (`directory_watcher.py:37`) with beats at `:777`, `:789`, `:1444`. `run_watcher.py:155-160` now says so in a comment: *"This beat used to be the ONLY watcher signal, which left a hole … The poller is now the reporter."* **`CODE_MAP` §3 (directory_watcher, lines 185–243) contains zero mention of heartbeats.**
- `:307` `health.py` worker verdicts — see F6.

---

### F6 — The `/health` worker-status vocabulary is enumerated as 4 values. There are 8. **[MEDIUM]**

| Document | Line | Enumeration |
|---|---|---|
| `docs/process/PRODUCTION_READINESS.md` | 40 | "`down` / `wedged` / `starting` / `ok`" |
| `docs/architecture/backend.md` | §1.3 판정 조인 table | 4 rows: down / wedged / starting / ok (`foreign_beat` in prose below) |
| `docs/architecture/CODE_MAP.md` | 315 | "`not running→down` · `비트 낡음→wedged` · `비트 없음 + 어림→starting` · `비트 신선→ok`" |

**Full grep of `entry["status"] = ` in `server/health.py`:** `down` (:203) · `starting` (:211) · `foreign_beat` **or** `missing` (:214) · `wedged` **or** `stale` (:221) · `ok` (:232) · `stalled` (:248). **Eight.**

`stalled` is new in `d56e7e2` and is the entire point of that batch — the drill that motivated it produced *"312 seconds of 200/ok while the work claim went stale, with the beat itself fresh at one second old."* The document set names every verdict except the one that catches the failure the beat cannot see.

This is my own recorded trap (a "N종" count copied instead of grepped) recurring at the same spot. **It is also where the lesson visibly took:** `FEATURE_CHECKLIST.md:100` now writes the overlay statuses as "명명된 실패 status **4종**(…) **+ IO 실패는 일반 `error`**" — the residual case is named. The health vocabulary did not get the same treatment.

---

### F7 — `PRODUCTION_READINESS` C2 (concurrent editing) predates the guard that changes its grade. **[MEDIUM]**

`docs/process/PRODUCTION_READINESS.md:82`:

> **없는 것**: 마지막 저장이 이김. … DOE 자동 저장은 디바운스라 **두 사람이 같은 값을 편집하면 늦게 끝난 쪽이 이긴다.**

**Code evidence:** `cdcddee` added a re-read-and-refuse guard on that exact save. `client2/src/map_editor.js:2322-2331` re-reads and compares against the loaded fingerprint; `:2355-2357` returns `{ ok: false, reason: 'conflict' }`; user-visible refusal at `:2395` and `transfer_plan.js:395-396` ("⚠ 다른 사람이 변경함 · 다시 불러오기"). `cdcddee`'s message records the negative control: sending the guard's payload by hand destroyed the other session's value, so the refusal is load-bearing.

The board already knows: `PROJECT_STATUS` §현재 초점 3 — "C2 동시 편집은 M2.6의 재읽기·거부로 **완화됨**(재등급 필요)." Same SSOT conflict shape as F1.

---

### F8 — Two of the day's three most consequential commits have no history entry. **[MEDIUM]**

`docs/history/` holds 9 entries dated `20260727_*`, all written by `d411386`. **Neither `cdcddee` (M2.6 — two tables retired, the DOE model rewritten) nor `d56e7e2` (correlated-failure retry, work claims, B3 resolved) has one.** `rg -l "cdcddee|d56e7e2"` over `docs/history/` returns two files, both of which mention M2.6 only as *upcoming*.

The index itself is clean (see "attacked and held"). This is a coverage gap, not an index defect — the historian ran before those commits existed. It matters now because the board says *"여기서 끊고 컴팩트"*: after compaction the permanent record of the day is missing its two largest changes, and `git log` is the only remaining source.

> **Scope note.** F8 is established by my own measurement (`ls docs/history/20260727_*.md` → 9 files; `rg -l "cdcddee|d56e7e2" docs/history/` → 2 files, both referring to M2.6 as upcoming). A deeper per-entry verification of the 9 entries — every cited commit hash resolving, every named source path existing, every claimed symbol present — was dispatched in parallel and had not returned when this report was written. It can only **add** findings inside those 9 files; it cannot change F8 or any finding above, all of which I measured directly.

---

### F9 — `docs/spec/DATA_SYNC_SPEC.md` (indexed) documents a class deleted with the PySide6 client. **[MEDIUM]**

`docs/spec/DATA_SYNC_SPEC.md:25`:

> **`ApiLazyTableModel`**: 초기화 시 데이터를 모두 불러오지 않고, 스크롤이 하단에 도달할 때 `canFetchMore`가 호출됩니다.

`rg "ApiLazyTableModel"` across `server/` and `client2/` returns **zero hits**. Live hits exist only in `agent_workspace/archive/` and `docs/_archive/` (correctly archived) and `docs/history/` (correctly historical). The two living documents that still assert it are `DATA_SYNC_SPEC.md` — **indexed at `docs/README.md:43` as 실시간 동기화 (🟠)** — and `docs/spec/TABLE_ENGINE_SPEC.md` (unindexed, see grading).

This is the exact `client2/src/bonding_plan.js` failure from the lessons file: a deleted symbol kept alive in an indexed document. `docs/_archive/` exists precisely for this class of file and already holds its siblings (`CLIENT_FEATURE_CHECKLIST`, `TECHNICAL_GUIDE`).

---

### F10 — Lower-severity, listed for completeness

| # | Location | Finding |
|---|---|---|
| a | `docs/architecture/backend.md:71` | "`main.py`, **~3,934줄**" — actual 4,045, and it was 4,045 at `be58210` too, so the figure is wrong at backend.md's own declared verification point. `CODE_MAP.md:20` says ~4,045. **Two living documents disagree about one file.** |
| b | `docs/process/PRODUCTION_READINESS.md:45, 133` | "스위트 **540 passed** / 0 failed" — measured at `8117456`. `server/tests/**` grew from 494 to 532 test functions since `be58210` (`d56e7e2` added `test_process_supervisor.py` +364, `test_ingestion_heartbeat.py` +278 new, `test_process_logging.py` +207 new, `test_health_endpoint.py` +214). The figure is presented as current gate evidence with no re-measurement. |
| c | `docs/process/PRODUCTION_READINESS.md:41` | 60 s staleness threshold still justified by the **idle** measurement (worst gap 10.26 s). `d56e7e2` replaced it with a load measurement — 7.01 s worst gap under a live 100k-row heavy-lane ingestion, 8.6× headroom, now pinned by a test. Not false; the doc simply carries the weaker of two available proofs. |
| d | `environment.yml:18`, `pyproject.toml:17` | `psutil` is now a declared dependency (`d56e7e2`). **No living document mentions it.** `rg "psutil" docs --glob '!history/*'` returns exactly one hit — `PRODUCTION_READINESS.md:45`, where it names a drill tool, not a dependency. `process_supervisor.py:206-209` degrades grandchild cleanup silently-but-announced without it, so it belongs in `CONDA_SETUP_GUIDE` / `DEPLOY_SETUP`. |
| e | `docs/DOC_AUDIT.md:173` | Only broken relative link in the entire non-history doc set (335 links resolved). `../overview/SYSTEM_OVERVIEW.md` from `docs/` resolves outside the repo. It sits inside a quoted example of the archive-banner convention, so the path is correct *for the file the example depicts* — cosmetic, but it is a dead link in a linter's eyes. |
| f | `docs/` (10 living files) | 35 `file:///c:/Users/kk980/...` absolute links. They encode one machine's home directory; `docs/map_editor/README.md` reaches its three sibling documents **only** through these. Not wrong today, unusable on any other checkout. |
| g | — | The brief stated "211 history entries." Actual is **217** (`ls docs/history/*.md` minus README). Flagged per my standing rule that instruction claims are inputs, not evidence — this one is harmless, but it is the third instruction-borne numeric error this cycle. |

---

## What I attacked and why it held

A verdict without this list is not usable. Each row is something I expected to break.

| # | Attack | Result |
|---|---|---|
| 1 | **`CODE_MAP`'s `WARN_*` = 14.** Suspected a re-sample, not a count. Full grep: `rg "^WARN_[A-Z0-9_]+\s*="` on `server/transfer_plan.py` → exactly **14** at lines 92–109. The 15th token a naive `rg -o "WARN_[A-Z0-9_]+"` returns is a substring of the private `_WARN_SEVERITY` table, correctly excluded. CODE_MAP's cited range "~92–109" is exact. **Held — the lesson took.** |
| 2 | **`EFFECT_*` = 5.** `rg -o "EFFECT_[A-Z0-9_]+" \| sort -u` → 5 tokens, all defined at `transfer_plan.py:110-116`. CODE_MAP's per-constant line numbers (110/113/114/115/116) are each exact. **Held.** |
| 3 | **Overlay clear = 2, not 3.** The lessons file says resolve to the *enclosing function*, so I did not accept the call lines. `clearOverlayLayers()` fires at `map_editor.js:964` and `:2871`. `964` sits inside `switchTable` (`:932`, next function `:980`); `2871` inside `loadExistingMap` (`:2827`). `openMapFrame` (`:4105`) does not call it, and the comment at `:3827` records why. Button wiring at `:614` and the exported handle at `:452` are not clear points. **Held — 2 is correct and both anchors resolve to the right functions.** |
| 4 | **`summaryStatusOf` removal.** `rg "summaryStatusOf"` across `client2/src` → zero. `availabilityOf` exists at `transfer_plan.js:318`. **Held.** |
| 5 | **`replace_map`'s "no sibling safety" — the brief asked whether M2.6's concurrency refusal falsifies it.** It does not. I read the implementation: `crud.py:1049-1080` scopes from `updates[0]` via `map_key_columns` and deletes the whole scope with no version, fingerprint, or generation check. The guard `cdcddee` added lives at the **caller** (`map_editor.js:2322-2357`), not in the primitive. `PRIMITIVES.md:17` ② is **accurate as written**. *Caveat, not a defect:* the entry does not record that the guard is now mandatory for any new consumer, which is the thing a reader of a "read before you build" catalog most needs. Recommend a sentence, not a correction. |
| 6 | **`replace_map`'s "cannot express the empty set."** `crud.py:1049` — `if batch.replace_map and batch.updates:`. Empty `updates` skips the block entirely. **Held.** |
| 7 | **Every server-side anchor in `CODE_MAP`.** Suspected uniform drift after finding the client drift. `main.py` health block claimed ~88–176 → block comment opens at 88, `async def health_check()` at 133. `/api/maps/overlay` claimed ~3067 → decorator at 3067. `crud._warn_audit_truncation_once` ~43 → 43. `_warn_undeclared_column_once` ~76 → 76. `apply_batch_updates` ~1034 → 1034. `batch.replace_map` ~1050 → 1050. `devenv.py` "372줄" → 372. **All exact. The drift is confined to the five files changed after `be58210` — it is not a systemic measurement failure.** |
| 8 | **Every symbol `PRIMITIVES.md` names.** `HeavyIngestionLane` (`directory_watcher.py:238`) · `_snapshot_table_context` (`:522`) · `compute_file_signature` (`ingestion_checkpoint.py:61`) · `chain_rules.json` (exists) · `build_key_filters` (`map_overlay.py:534`) · `derive_table_binding` (`:484`) · `make_frame_transform` (`:271`) · `resolve_align` (`:354`) · `buildKeyFilters` (`map_editor.js:4379`) · `deriveMapBinding` (`:4362`) · `fetchPaintRules` (`:92`) · `ensureCellObject` (`grid.js:94`) · `physFrameOverride`/`withPhysFrame` (`:1096`/`:1117`) · `maps.json` + `GET /api/map-presets` (`main.py:2967`) · `install_product_tables.py` · `iso_watcher.check_static_isolation`/`check_live_isolation`. **Every one resolves. Zero phantom references.** |
| 9 | **`PRIMITIVES.md:110`'s 8 `devenv.py` verbs.** Suspected an over-list, because `FEATURE_CHECKLIST:147` gives 7 (no `bootstrap`) and history `20260727_000000:44` gives 6. All 8 exist: `add_parser` calls at `devenv.py:348, 351, 354, 357, 358, 360, 362, 364`. **PRIMITIVES held; the other two are subsets, not contradictions.** |
| 10 | **`align_overrides` purge.** `CONFIG_GUIDE` claims removal from five places. `rg "align_overrides"` over `server/` + `client2/` returns only *removal notices* — `main.py:3080,3083`, `map_overlay.py:26`, `map_editor.js:4198`, the `.sample` comment, and `test_map_overlay.py:238` which asserts a stale declaration is **ignored**. No live consumer. Consistent across `SYSTEM_OVERVIEW:137`, `CONFIG_GUIDE:34,491`, `CODE_MAP:462`, `MAP_EDITOR_SPEC:301`, `backend.md:120`. **Held, and consistent across six documents — the cleanest thing in this cycle.** |
| 11 | **Overlay cell cap: `FEATURE_CHECKLIST:100` says 2,000, `map_overlay.py:70` says `MAX_OVERLAY_CELLS = 20_000`.** Looked like a 10× error. It is not: the client path caps at `OVERLAY_CELL_LIMIT = 2000` (`map_editor.js:4344`), the server endpoint at 20,000, and the same checklist row states the map editor does not call the server endpoint. `CODE_MAP` documents both separately (`:466` server, `:608` client). **Held — two caps, correctly distinguished.** |
| 12 | **History index integrity.** 217 `.md` files, 217 links in `docs/history/README.md`, header says 217, all 9 `20260727_*` entries listed, no listed-but-missing files. Generated by `gen_index.py` as the doc claims. **Held.** |
| 13 | **Whole-corpus link resolution.** 335 relative links across all 49 living + 13 archived documents resolved against disk. **One** failure (F10e, cosmetic). **Effectively held.** |
| 14 | **`SYSTEM_OVERVIEW` still listing `align_overrides` as a live key.** `d411386`'s message claims this correction. `SYSTEM_OVERVIEW.md:137` now reads "**`align_overrides`는 2026-07-27 폐지**". **Correction verified as landed.** |
| 15 | **`DOC_OWNERSHIP` reassignment after the agent split.** `:11` PRIMITIVES → doc-keeper; `:17` CODE_MAP → code-mapper with 정합 감사 → doc-auditor; `:40` FEATURE_CHECKLIST → doc-keeper, audit → doc-auditor. Matches `.claude/agents/*.md`. **Held.** |
| 16 | **`ChildSpec` count — docs say "자식 5~6개".** `run_decoupled_app.py:56-71`: 5 fixed specs plus a conditional desktop-client spec. **Held.** |
| 17 | **Heartbeat names "4종".** `rg "heartbeat\.beat\("` over `server/` (excluding tests) → `chain`, `graph`, `scheduler`, and `HEARTBEAT_NAME="watcher"`. Still exactly 4 names. **Held** (the *source* of the watcher beat moved — F5 — but the count did not). |
| 18 | **`DEPLOY_SETUP §5`, rewritten this cycle around "the four axes that actually differ."** Attacked every axis and every named symbol. DB `assy_manager`/`assy_qa` → `devenv.py:59`. Disk via `ASSY_DATA_ROOT` → `paths.py`. API 8080/8081 → `devenv.py:56` (`ASSY_DEV_API_PORT` default 8081). Graph 8090/8091 → `:57`. Gate functions `check_static_isolation`/`check_live_isolation` → `iso_watcher.py:94`/`:146`, both module-level pure functions as claimed. The live-check claim "실제로 열린 세션에 `SELECT current_database()`를 묻는다" → `iso_watcher.py:205`, and the mismatch message at `:161` quotes `current_database()` back. Refusal is `sys.exit` (`:308`), not a warning. **Every claim held.** |
| 19 | **`DEPLOY_SETUP §5`'s log-leak fix claim.** "이전에는 `utils/logger.py`가 자기 `__file__`에서 경로를 만들어 격리 프로세스가 운영 로그 파일에 덧썼다" → `logger.py:5-13` now imports `paths` with an explicit comment on the fallback, and `:125` builds the handler path from `paths.log_path(log_filename)`. **Held.** |
| 20 | **`MAP_EDITOR_SPEC §5`'s "실패 상태 4종" — the exact phrasing my lessons file flags.** It does not stop at 4: `:335` adds "이 4종 외에 **일반 `error`**가 있습니다" and explains the split (the named 4 are all outcomes of "no basis → do not draw"; `error` is plain IO failure). The removed pair `align_unconfirmed`/`align_override_declared` is documented with its cause. Server side agrees — `map_overlay.py:74,76` define `STATUS_ALIGN_UNAVAILABLE`/`STATUS_NO_DATA`. **Held, and this is the counting lesson landing correctly in two documents (here and `FEATURE_CHECKLIST:100`) — which is exactly what makes its absence from the health vocabulary (F6) a regression rather than an oversight.** |

---

## Grading — read trigger, A / B / C

Grade is assigned by **measured read trigger**, not by importance or freshness. The empirical basis for A is `rg -o "docs/[A-Za-z0-9_/]+\.md" .claude/agents/*.md` — a document named in an agent charter is loaded on dispatch. Everything else is judged by whether a real event sends someone to it.

**18 of 49 living documents have a charter-level read trigger. 31 do not.**

### A — loaded on dispatch (charter-referenced). Accuracy is the top priority.

| Document | Charters | Audit state |
|---|---|---|
| `architecture/CODE_MAP.md` | **12** | ⚠️ F4, F5, F6 — server side exact, client + ops sections stale |
| `process/PROJECT_STATUS.md` | 7 | ✅ correct on B3 and C2 where two other docs are not |
| `overview/SYSTEM_OVERVIEW.md` | 7 | ✅ `align_overrides` correction verified |
| `architecture/PRIMITIVES.md` | 4 | ⚠️ F2 (restart budget), F3-adjacent (`:41` `map_doe.band_seq`, `:55` `map_doe` as a live product table) |
| `prompts/client_pm.md` | 3 | — |
| `README.md` (index) | 3 | ⚠️ `:40` still frames DOE_STORAGE_MAP as "M2.6 진행 중" |
| `spec/MAP_EDITOR_SPEC.md` | 2 | ✅ spot checks held |
| `prompts/starting_prompt.md` | 2 | — |
| `prompts/server_pm.md` | 2 | — |
| `process/DOC_OWNERSHIP.md` | 2 | ✅ split correctly recorded |
| `architecture/frontend.md` | 2 | — |
| `spec/DOE_STORAGE_MAP.md` | 1 (`map-pm`) | 🔴 **F3 — worst document in the set** |
| `process/CONTRIBUTING.md` | 1 | — |
| `map_editor/README.md` | 1 | ⚠️ index-only; reaches its 3 children solely via `file:///` links (F10f) |
| `history/README.md` | 1 | ✅ generated, 217/217 |
| `architecture/event_driven_backend.md` | 1 | — |
| `architecture/data_model.md` | 1 | — |
| `architecture/backend.md` | 1 | ⚠️ F2, F6, F10a |

### B — event-triggered. Keep.

| Document | Trigger |
|---|---|
| `process/PRODUCTION_READINESS.md` | deployment decision — 🔴 **F1, F2, F6, F7, F10b/c** |
| `guide/DEPLOY_SETUP.md` | new environment — ⚠️ F1, F10d |
| `guide/CONFIG_GUIDE.md` | new table/map/collector/graph onboarding — ⚠️ F1 |
| `guide/CONDA_SETUP_GUIDE.md` | environment build — ⚠️ F10d (`psutil` undeclared) |
| `guide/NATIVE_POSTGRES_SETUP_GUIDE.md` · `guide/POSTGRES_OPERATIONS_GUIDE.md` | DB install / operations |
| `guide/INGESTION_GUIDE.md` · `guide/chain_ingestion_guide.md` · `guide/AUTO_UPDATE_GUIDE.md` · `guide/HTML_TOPOLOGY_PARSER_GUIDE.md` | subsystem work |
| `guide/data_preservation_and_signature_change.md` | signature change SOP — mandatory-read on that event |
| `qa/FEATURE_CHECKLIST.md` | pre-release regression — ⚠️ F2, and ✅ the "4종 + error" fix landed here |
| `spec/ONTOLOGY_GRAPH_SPEC.md` · `spec/ENRICHMENT_QUEUE_SPEC.md` · `spec/FAILURE_MANAGEMENT_SPEC.md` · `spec/BUSINESS_LOGIC_SPEC.md` | domain work on those subsystems |
| `spec/api_documentation.md` · `spec/DEBUGGING_GUIDE.md` · `guide/SERVER_STARTUP_GUIDE.md` | consulted on demand (all 🟠 — accept as reference-grade, do not maintain to Living) |
| `process/RELEASE_LOG.md` · `process/agentic_environment.md` | release / org change |
| `spec/batch_update_technical_specification.md` | batch upsert work — 🟠, indexed |
| `map_editor/architecture_and_management.md` · `map_editor/philosophy.md` | reachable from an A-grade index; philosophy.md is durable design rationale, not mechanism |

### C — no trigger. **Archive recommended.**

| Document | Why C | Evidence |
|---|---|---|
| `spec/TABLE_ENGINE_SPEC.md` | No index entry, no charter, nothing links to it, **and it is actively false** — 134 lines specifying `ApiLazyTableModel` + Qt background workers, deleted with the PySide6 client | `rg "ApiLazyTableModel"` over `server/`+`client2/` → 0 hits; last touched 2026-04-25 |
| `spec/BATCH_INGESTION_SPEC.md` | No index entry, nothing links to it, zero outgoing links; superseded by `INGESTION_GUIDE` + `backend.md §3`; names PySide6-era components | last touched 2026-04-20 |
| `spec/BATCH_PROCESSING_SPEC.md` | No index entry; only inbound link is from `docs/_archive/TECHNICAL_GUIDE.md` — **an already-archived document.** Overlaps `BATCH_INGESTION_SPEC` and `batch_update_technical_specification` | last touched 2026-06-09 |
| `prompts/starting_prompts.md` | **Duplicate.** `starting_prompt.md` (singular, 121 lines) is indexed and is the live charter; this plural 68-line file is an older multi-agent prompt set, unindexed, unlinked, and describes an org structure the agent split replaced | last touched 2026-07-24 |
| `prompts/CLAUDE.md` | Generic LLM coding guidance, no project content, no index entry, nothing links to it. Superseded in function by `.claude/agents/*.md` + `agent_workspace/memory/*.md`, which *are* loaded | last touched 2026-07-24 |
| `map_editor/specification.md` | Claims to be a complete function reference for `map_editor.js` — 64 lines for a 4,866-line file, last touched 2026-07-24, reachable only via a `file:///` absolute link. `CODE_MAP §7` is the maintained version of exactly this | duplicate-by-construction |
| `DOC_AUDIT.md` | Marked "✅ Executed (2026-07-24 — P1~P5 반영 완료)". It is a completed remediation plan, indexed under "먼저 읽을 것" as though it were current guidance | its own status line |

**Reduction: 49 → 42 living documents (−14%).** Six of the seven have not been touched in ≥3 days by a project that ships several times a day; three assert deleted code. Retiring them removes the only two remaining living-document references to `ApiLazyTableModel` (F9 leaves `DATA_SYNC_SPEC` — see below).

### Grading decisions I want on the record

- **`spec/DATA_SYNC_SPEC.md` — I did not grade it C, though F9 tempts.** It is indexed (`README.md:43`), it covers a live subsystem (WebSocket delta sync), and only one paragraph is dead. Recommend: **B, with `:25` corrected or cut.** Archiving it would take a live subsystem's only spec with it.
- **`map_editor/` (4 files)** — `README.md` is A (charter-referenced) but is a pure index; its 3 children are reachable only through machine-local `file:///` links. Recommend either fixing those to relative links (making the subtree genuinely B) or folding the durable content into `MAP_EDITOR_SPEC` and archiving the subtree. I graded `specification.md` C because it duplicates `CODE_MAP §7`; the other two carry rationale that is not written down elsewhere.
- **I did not grade the 217 history entries.** They are append-only immutable records with a generated index — the A/B/C read-trigger frame does not apply, and archiving them would destroy the record the compaction is meant to preserve. The history *gap* (F8) is the actionable item, not the volume.

---

## Recommended order (advisory — dispatch is yours)

1. **F1** — B3. Five lines in `PRODUCTION_READINESS`, one in `CONFIG_GUIDE`, one in `DEPLOY_SETUP`. Purely mechanical; the board already holds the correct text.
2. **F3** — `DOE_STORAGE_MAP`. Highest risk of the set: an A-grade pre-flight document for the agent that owns the next queue item. If a rewrite is too large before compaction, **replace the banner** so it says *superseded*, not *in flight*, and strike `:134`.
3. **F2 + F6** — supervisor give-up rule and health vocabulary. One `PRIMITIVES` entry, one `backend.md §1.3`, two `PRODUCTION_READINESS` lines, one `FEATURE_CHECKLIST` row, one `CODE_MAP` row.
4. **F8** — two history entries, before compaction. This is the only item that becomes *unrecoverable* rather than merely stale.
5. **F4 + F5** — code-mapper re-pass over `map_editor.js`, `transfer_plan.js`, and the five ops modules at HEAD `d56e7e2`.
6. **F7, F9, F10** — grade C2, fix `DATA_SYNC_SPEC:25`, reconcile the `main.py` line count, declare `psutil`.
7. **Archival** — the 7 C-grade documents.

---

## Proposed lessons (for 총괄 review — I did not edit the memory file)

### doc-auditor

- **함정**: 문서가 `Last-verified: HEAD <hash>`를 정직하게 달고 있으면 앵커 드리프트를 통과시킨다. 라벨이 정직해도 **독자가 실행하는 것은 지시문**이다 — `CODE_MAP`은 "이 앵커로 `Read(offset, limit)` 하라"고 지시하면서 ±20줄을 약속했고, 실제 드리프트는 +303줄이었다.
  **올바른 방법**: `Last-verified` 해시가 HEAD가 아니면 **그 사이 커밋이 만진 파일 목록을 먼저 뽑고**(`git diff --stat <verified>..HEAD`), 그 파일들의 앵커만 실측하라. 나머지는 건드릴 필요가 없다 — 이번에 서버 앵커 7개는 전부 정확했고 드리프트는 5개 파일에 갇혀 있었다.

- **함정**: "곧 바뀐다 / 진행 중"이라 적힌 배너를 **유예**로 읽는다. 배너는 작성 시점에는 맞았지만, 변경이 **착지한 뒤에는 배너 자체가 가장 위험한 거짓말**이 된다 — 독자에게 "본문은 현재 커밋 상태"라고 보증하기 때문이다.
  **올바른 방법**: 진행-중 배너를 만나면 배너가 가리키는 커밋/보드 항목의 **착지 여부를 먼저 확인**하라. 착지했으면 그 문서는 "부분 최신"이 아니라 **폐기 서술**이며, 등급이 아니라 배너의 모양이 틀린 것이다.

- **함정**: 문서 등급을 중요도·최신성으로 매긴다.
  **올바른 방법**: 읽기 트리거는 **측정 가능하다** — `rg -o "docs/[^ ]+\.md" .claude/agents/*.md`가 A등급의 경험적 정의다. 이번 사이클에서 이 한 줄이 `DOE_STORAGE_MAP`을 "낡은 스펙"에서 "`map-pm`이 매 착수마다 로드하는 문서"로 재분류했고, 그것이 F3의 심각도를 결정했다.

### code-mapper (제안 — 소관 아님이므로 총괄 판단)

- 워킹트리 대신 커밋을 실측한 판단은 옳았다. 그러나 **그 선택의 대가(맵이 커밋 시점에 이미 낡음)가 커밋 메시지에만 남았다.** 문서를 읽는 사람은 커밋 메시지를 읽지 않는다.
  **올바른 방법**: 측정 기준 커밋이 HEAD가 아닐 때는 **해당 절 안에** 배너를 남길 것 — `product_tables.py` 절에는 있었고 ops 5종 절에는 없었다. 차이는 배너 한 줄이었다.

### 공통

- **다른 에이전트가 방금 고친 자리를 먼저 보라.** 이번 사이클에서 실제로 그렇게 나왔다 — `FEATURE_CHECKLIST:100`은 "N종" 함정을 정확히 교정했는데(`4종 + 일반 error`), 같은 함정이 **바로 옆 문서의 health status 어휘에서 8종을 4종으로** 재발했다. 교정은 문서 단위로 착지하고 개념 단위로 착지하지 않는다.
