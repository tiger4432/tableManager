# 🗺️ CODE_MAP — 압축 구조 지도 (파일 전량 읽기 방지용)

> **Status:** 🟡 **부분 검증(PARTIALLY VERIFIED)** | **Owner:** 전 에이전트 공용 | **Source-of-truth:** 각 표의 코드 경로
>
> 🔴 **이 문서에는 문서 전체에 걸친 `Last-verified`가 없다 — 없앤 것이 아니라 *가질 자격이 없다*.** 아래 표에 적힌 절만 실측됐고 **나머지는 미검증**이다. 독립 감사(2026-08-06) 실측: **문서 전체 앵커의 약 55%만 정확하다.**
>
> 🔴 **직전 표지는 거짓이었고, 그 거짓이 이 문서가 고치려는 결함과 같은 계급이었다.** 표지는 「소스 앵커는 `87a944e`의 커밋된 blob 실측」이라 적었지만 그 패스가 실제로 잰 것은 **네 절뿐**이다. 나머지 파일은 **열지도 않은 채** 그 문장이 덮었다. 🔴 **`main.py`·`crud.py`·`admin.js`·`transfer_plan.py`·`map_overlay.py`는 `87a944e`와 HEAD 사이에 바이트 동일한데도 드리프트가 가득하다** — 즉 낡음은 그 측정보다 **앞선다**. **검증 주장이 검증 범위보다 넓으면, 그 주장은 다음 독자가 확인하는 것을 막는다. 그래서 아무 주장도 없느니만 못하다.**

**📍 절별 검증 상태 — 이 표가 이 문서의 유일한 신뢰 기준이다.**

> 🆕 **[2026-08-11 패스의 측정 기준]** 이 패스가 잰 것은 전부 **`7097a67`의 커밋된 blob**이다(`git show 7097a67:<path>` — 워킹트리 아님. 측정 시각에 클라 레인이 `client2/src/`를, 다른 문서 레인 둘이 `docs/history/`·리빙 문서를 동시 편집 중이었다). 🔴 **아래 🆕🆕 행이 이 패스의 범위이고, 그 밖은 이 패스가 열지 않았다.** 이 패스는 **삭제부터 훑었다** — `8d89b98..7097a67`의 `--diff-filter=D`는 `client2/dist/assets/*` 번들 2개뿐이고 **소스 파일 삭제는 0건**이다(사라진 것은 파일이 아니라 **심볼**이었다 → §0 ⑱).
>
> 🔬 **측정 중 HEAD가 `7097a67` → `6cc7a6e`로 움직였고, 그것을 확인한 방법을 남긴다.** 들어온 넷 중 셋은 `docs/`만 건드렸고 하나(`1e29078`)가 `client2/src/`에 참조뷰 기능을 넣었다. 🔴 **그래서 「소스가 안 바뀌었다」를 가정하지 않고 blob 해시로 재확인했다** — 이 패스가 측정한 **서버 10파일과 `map2/` 4파일은 두 리비전에서 바이트 동일**하다(`git rev-parse <rev>:<path>` 대조). ⚠️ **`1e29078`이 바꾼 `client2/src/`의 나머지**(`api.js`·`grid.js`·`main.js`·`clipboard.js`·`dom.js`·`websocket.js`·`style.css`)**는 이 패스가 열지 않았다** — §7의 그 행들은 여전히 미검증이다.
>
> 🆕 🔴 **[2026-08-11] 두 절의 제목에서 줄 수를 걷어냈다 — 제목이 크기를 이고 있으면 파일이 자랄 때마다 앵커가 깨진다.** 실측: 이 문서의 링크 **36개 중 6개가 아무 데도 가지 않았고**, 그중 넷이 `map_alignment.py` 제목의 낡은 줄 수(`#…5961줄…` · `#…5993줄…`)를 가리켰다. 크기는 본문으로 내렸다 — **제목은 이름이지 측정값이 아니다.** 나머지 **셋도 이 패스에서 고쳤다**(`push_columns.js` · `§1.8 column_filter.py` · `§7-A Map Editor 2` — 셋 다 제목의 **끝 토막을 흘린** 링크였다). 🔴 **남은 하나는 `§5-F ①`(`#-훑기walk--순번의-정본`)이고 판정을 보류한다** — 제목의 `①`(U+2460)을 GitHub 슬러거가 지우는지 남기는지에 따라 **맞을 수도 틀릴 수도** 있고, 이 문서 안에서는 확인할 방법이 없다. **모르는 것을 고친 척하지 않는다.**
>
> 🆕🆕🆕 **[2026-08-11 후속 패스의 측정 기준]** 이 패스가 잰 것은 **`2630790`(HEAD)**의 커밋된 blob이다(`git show 2630790:<path>` — 워킹트리 아님. 측정 시각에 `server/scripts/diagnose_slow_after_ingest.py`가 다른 레인에서 동시 편집 중이었으므로 그 파일은 열지 않았다). `7097a67..2630790`(13개 커밋) 중 소스에 손을 댄 것은 다섯이다: `1e29078`(참조뷰 — 직전 패스가 이미 등재) · `5116f67`(enrichment 큐 페이지의 링크 철회, `ui.js` 축소) · `dab9152`(행/셀 이력 페이징 신설 — `audit_history.py`) · `ab36fab`(`enrichment.html`+vite 엔트리 삭제, 하니스 게이트 수리) · `68db020`(맵 좌표 바인딩 키별 상속 — `map_overlay`/`ontology_config`/`config_resolve_report`/`map_alignment`/`frame_confirmation`) · `2630790`(`audit_cache.py` 전면 재작성). 나머지 일곱은 `docs/`·보드 전용이라 이 지도의 대상이 아니다. **삭제부터 훑었다** — 이 구간의 `--diff-filter=D`는 dist 번들과 `client2/dist/enrichment.html` 외 **소스 파일 하나**(`client2/enrichment.html`)뿐이다.
>
> 🔴 **`ui.js`·`admin.js`·`api.js`·`clipboard.js`·`dom.js`·`grid.js`·`style.css`·`main.js`·`websocket.js`는 이번에도 열지 않았다** — `5116f67`·`ab36fab`·`68db020`이 건드렸지만 이 패스의 지시 범위 밖이었다. 이 절들은 여전히 미검증이다(직전 패스의 같은 경고 참조).
>
> 🆕🆕🆕🆕 **[2026-08-11 3차 후속 패스의 측정 기준]** 이 패스가 잰 것은 **`c4a3159`(HEAD)**의 커밋된 blob이다(`git show c4a3159:<path>` — 워킹트리 아님. 측정 시각에 `server/`와 `client2/`가 각각 다른 레인에서 동시 편집 중이었다). `2630790..c4a3159`(11개 커밋) 중 코드에 손을 댄 것은 여섯이다: `2b8a5ab`(진단 스크립트, 이 지도의 등재 대상 밖) · `fde424c`(`/audit_logs/recent`가 봉투로 전환 + `/enrichment` 404 문구 교체) · `1a1947b`(진단 스크립트) · `5b09d69`(신설 `chain_bindings.py` + 맵퍼 6종의 `dt_job` 리터럴 철회) · `3d43a6c`(맵2 확정 키가 규칙의 `decision_key`를 아리티 그대로 따름) · `347de78`(`compute_priority_value` tie-break 신설 + 미선언 컬럼 드롭 가시화). `c5e7bd0`은 직전 코드맵 패스 자신이고 `b0af883`·`b1b7f85`·`2fb1c44`는 `docs/`·보드 전용이라 이 지도의 대상이 아니다. **삭제부터 훑었다** — 이 구간의 `--diff-filter=D`는 `client2/dist/assets/*` 번들 2개뿐이고 **소스 파일 삭제는 0건**이다.
>
> ⚠️ **`client2/src/map2/main.js`는 NUL 바이트를 품고 있다** — 평범한 `grep`은 이 파일을 바이너리로 판정해 0건을 낸다. 이 패스는 `grep -a`(또는 파일을 떠서 `grep -na`)로 다시 훑었다. **직전 패스가 이 파일을 평범한 grep으로 훑었다면 그 결과는 "매치 없음"이 아니라 "질문을 안 한 것"과 같다** — 이번엔 그 경로로 실제 변경분(`decisionKeyColumns` 게이트, `keyFrom` 삭제)을 확인했다.
>
> 🔴 **표지 문장 삼중 사본 정정.** 「`compute_priority_value`는 우선순위 맵만 본다」는 문장이 이 문서에 최소 두 자리(§2 `compute_priority_value` 행, 무변경 쓰기 생략 각주)로 살아 있었고, `347de78`이 실제 동작을 **선언 우선순위 → `ingested_at` 내림차순 → `source_name` 오름차순**의 3단 전 순서로 바꿨다. 같은 문장의 다른 사본 둘은 `347de78`(`data_model.md`)·`2fb1c44`(spec 문서들)에서 이미 고쳐졌다 — 이 파일의 사본만 임자가 없었다. 아래 §2에서 두 자리 모두 3단 순서로 재서술했다.
>
> 🆕🆕🆕🆕 **이 패스가 새로 등재/정정한 것 — 전건**: `server/chain_bindings.py`(신설 244줄) · 맵퍼 6종(`chain_rules` 5종 + `dt_map_mapper.py.sample`)의 job-column 해석 · `crud.compute_priority_value`/`resolution_ingested_at`(3단 tie-break) · `crud._warn_undeclared_column_once`/`undeclared_column_drops()`(드롭 카운트+10의 거듭제곱 재공지) · `chain_ingestion_worker._undeclared_drop_note`+하트비트 `note=` 배선 · `chain_replay.recompute_display_values`(R3)+공유 헬퍼 `_load_cell_state`/`_resolve_cell`+CLI `resolve` 서브커맨드 · `map_alignment.build_alignment_worklist`의 결정키-미충족 행 생존(`REASON_UNIT_KEY_INCOMPLETE`) · `main.fetch_and_merge_metadata`/`get_cell_sources`/`query_cells_sources`(`ORDER BY source_name` 3곳) · `GET /audit_logs/recent`의 `AuditLogGroupPage` 봉투 · `schemas.AuditLogGroupPage`(신설) · 퇴역 `/enrichment` 404 문구 · `client2/src/map2/view_model.js`의 `decisionKeyOf`/`DECISION_KEY`/`RULE_ADOPTION`/`declaredKeyColumns`/`decisionKeyRefusal`(신설, `keyFrom` 대체) · `client2/src/map_editor2.js`의 `keyFrom` 삭제 확인(0건) · `client2/src/map2/main.js`의 `decisionKeyColumns` 확정 전 가드 · `client2/src/timeline.js`의 `readHistoryPage(body, listKey='logs')`(파라미터화) + 전역 이력 탭의 `'groups'` 열기.
>
> ⚠️ **확인 못 한 것**: `server/mappers/dt_map_mapper.py.sample`은 이 문서에 **애초에 등재된 적이 없었다**(별개의 구 체인 계열 `dt_log_to_dt_map`/`dt_job_attribution_to_dt_map`/`eqp_frame_attribution_to_dt_map`) — 이번에 확인한 것은 `chain_bindings.resolve_column` 채택 한 가지뿐이고, 그 파일의 전체 구조는 여전히 미등재·미검증이다(신규 섹션 신설은 이 패스의 지시 범위 밖). `client2/scripts/check_harnesses.mjs`의 하니스 floor 숫자(`fde424c`가 98→117, `3d43a6c`가 193→256으로 올렸다는 커밋 로그의 주장)는 **이 패스가 직접 재지 않았다** — 코드맵은 채점 결과가 아니라 구조를 등재하므로 범위 밖으로 남겼다. `client2/map_editor2.html`은 이 구간에서 무변동이 diff로 확인됐으나 실측 875줄이 이 문서의 기존 등재값(866줄)과 어긋난다 — **이 드리프트는 이번 구간이 만든 것이 아니라 그전부터 있었고**, 지시 범위 밖이라 고치지 않았다(다음 패스 참고용으로 남긴다).

> 🆕⑤ **[2026-08-13 인제션 원장/tier-1 패스의 측정 기준]** 이 패스가 잰 것은 **`831ab68`(HEAD)**의 커밋된 blob이다(`git show 831ab68:<path>` — 워킹트리 아님. 측정 시각에 여섯 레인이 `server/**`·`client2/**`를 동시 편집 중이었으므로 워킹트리는 근거가 될 수 없다). 범위는 `b1dd2f0..831ab68`(12커밋). **삭제부터 훑었다** — 이 구간의 `--diff-filter=D`는 **0건**이다(소스도 dist도 없음). 🔴 **아래 🆕⑤ 행이 이 패스의 범위이고, 그 밖은 이 패스가 열지 않았다.**
>
> 🆕⑤ **이 패스가 새로 등재/정정한 것 — 전건**: `ingestion_checkpoint.py`(258 → **587줄**, 표 전면 재작성 — `find_terminal_by_path_stat`/`find_terminal_by_path_stat_batch`/`TIER1_BATCH_SIZE`/`record_failure`/`adopt_new_location`/`read_file_stat`/`mtime_ns_to_datetime`/`stat_identity_signature`/`STATUS_FAILED`/`TERMINAL_STATUSES`/`STAT_SIGNATURE_PREFIX`) · `directory_watcher.py`(2,293 → **2,681줄** — `settle_already_terminal`/`_settle_terminal_hits`/`_try_path_stat_skip`/`_record_failure`/`_refuse_move_by_retention`/`dedup_by_path_stat_enabled`/`archive_processed_files_enabled`, `sweep_existing_files`·`_ingest_directory_tree`의 후보 튜플·반환 의미 변경) · `db_safety.py`(215 → **453줄** — 읽기 전용 가드 절 신설) · `models.FileIngestionCheckpoint`(컬럼 3종·인덱스 1종 추가, `STATUS_FAILED` 어휘) · `scripts/dev_env/snapshot_db.py`(자체 read-only 구현 철회 → `db_safety` 위임).
>
> ⚠️ **이 패스가 확인 못 했거나 범위 밖으로 남긴 것**: `server/schema_drift.py`(336 → **519줄**, `eb700e5`)는 **이 문서에 애초에 등재된 적이 없다** — 신규 섹션 신설은 이 패스의 지시 범위 밖이라 미등재로 남는다. `server/scripts/audit_schema_canon.py`(1,773 → **1,777줄**)도 마찬가지로 미등재다. `server/migrations/alter_dt_inventory_lot_slot_to_text.sql`(+reverse, `8bdc136`)·`add_ingestion_ledger_path_stat.sql`(+reverse, `ba664c5`)는 신설 확인만 했고 내용은 등재하지 않았다. `models.py`는 **984(구 등재) → 1,041줄**로 이번 구간(+25) 밖의 드리프트도 포함하는데, 이 패스는 `FileIngestionCheckpoint` 절만 실측했고 **나머지 앵커는 재측정하지 않았다 — 밀렸다고 가정하라.**

> 🆕⑥ **[2026-08-13 정본 원장(canonical ledger) 신설 등재 패스의 측정 기준]** 이 패스가 잰 것은 **`aeddac8`(HEAD)**의 커밋된 blob이다(`git show aeddac8:<path>` — 워킹트리 아님). 🔴 **아래 🆕⑥ 행이 이 패스의 범위이고, 그 밖은 이 패스가 열지 않았다.** 이 패스는 **삭제부터 훑었다** — 등재 대상 18파일 중 `--diff-filter=D`에 걸린 것은 **0건**이다.
>
> ⚠️ **측정 시각에 원장 읽기 측 일곱 파일이 워킹트리에서 modified였다** — `server/ledger_trace.py` · `server/ledger_trace_router.py` · `client2/src/ledger_trace.js` · `client2/src/ledger_trace_core.js` · `client2/src/ledger_trace_view.js` · `client2/tests/ledger_trace_harness.mjs` · **`client2/ledger.html`**(두 레인이 동시 편집 중). **그래서 워킹트리는 근거가 될 수 없고 위 값은 전부 커밋된 상태다.** 🔴 **`server/ledger/**` 11파일 · `server/migrations/add_ledger_events.py` · `client2/vite.config.js` · 채점자 5모듈은 `git status`로 워킹트리와 blob 동일함을 확인했다** — 가정하지 않고 물었다.
>
> 🆕⑥ **이 패스가 새로 등재한 것 — 전건**: [§5-H](#5-h-정본-원장-canonical-ledger) 신설 — `server/ledger/` **11파일**(`__init__`/`envelope`/`vocabulary`/`uuid7`/`gate`/`config`/`schema`/`store`/`lot_event_translator`/`backfill`/`observability`, 합 **2,819줄**) · `server/ledger_trace.py`(**1,179**) · `server/ledger_trace_router.py`(**80**) · `server/migrations/add_ledger_events.py`(**96**) · 클라 `ledger_trace_core.js`(**286**)/`ledger_trace_view.js`(**173**)/`ledger_trace.js`(**149**)/`ledger.html`(**393**) · `client2/tests/ledger_trace_harness.mjs`(**674**) · 채점자 5모듈. **§7 도입부의 「6엔트리」도 정정했다**(실측 **7**이고 목록도 틀렸다 — 아래 행).
>
> ⚠️ **이 패스가 확인 못 했거나 범위 밖으로 남긴 것**: `docs/architecture/CANONICAL_LEDGER_DESIGN.md`·`DUPLICATION_LEDGER.md`·`docs/process/LEDGER_RULINGS.md`·`LEDGER_SLICE_1_BRIEF.md`는 **리빙 문서라 이 지도의 등재 대상이 아니다**(참조만). `server/config/ledger_config.json.sample`은 **구조만** 적었다(gitignored 운영자 자산의 `.sample`). `server/config/ledger_resolver.json`은 **선택 파일이고 이 박스에 없어도 정상**이라 존재를 주장하지 않는다. 🔴 **`server/ledger/` 밖에서 이 패스가 연 파일은 `main.py`의 라우터 등록 두 줄과 `paths.py`·`crud.py`의 심볼 존재 확인뿐이다** — §1·§2의 나머지 앵커는 여전히 이 패스의 범위 밖이다.

| 절 / 파일 | 상태 | 기준 리비전 | 비고 |
|---|---|---|---|
| 🆕⑥ §5-H 정본 원장 — `server/ledger/` 패키지 11파일 | 🟢 **심볼 실측 신규 등재(2026-08-13)** | **`aeddac8`**(HEAD) | 종전 등재 **0**. 라인 번호 0개 — 심볼과 시그니처만 |
| 🆕⑥ §5-H 읽기 측 — `ledger_trace.py` · `ledger_trace_router.py` | 🟢 **심볼 실측 신규 등재(2026-08-13)** | **`aeddac8`**(HEAD) | ⚠️ **두 파일 다 측정 시각에 워킹트리 modified** — 커밋된 상태 기준이고 다음 커밋에서 재측정 필요 |
| 🆕⑥ §5-H 클라 3종 + 하니스 + `client2/ledger.html` | 🟢 **export 실측 신규 등재(2026-08-13)** | **`aeddac8`**(HEAD) | 〃 **네 파일 다 측정 시각에 워킹트리 modified**(`client2/vite.config.js`만 blob 동일) |
| 🆕⑥ §7 도입부 — vite 엔트리 개수/목록 | 🟢 **`vite.config.js` 실측 정정(2026-08-13)** | **`aeddac8`**(HEAD) | 「**6**엔트리(index/admin/map_editor/**enrichment**/graph/trace)」 → 실측 **7**(index/admin/map_editor/**map_editor2**/graph/trace/**ledger**). `enrichment`는 `ab36fab`에서 삭제됐는데 이 줄만 임자가 없었고, `map_editor2`는 등재된 적이 없다 |
| 🆕⑤ §5 `server/ingestion_checkpoint.py` — tier-1 원장 + 배치 조회 | 🟢 **심볼 실측(2026-08-13)** | **`831ab68`**(HEAD) | 258 → **587줄**. 표의 라인 번호를 전부 걷어내고 심볼로 재작성했다 |
| 🆕⑤ §3 `server/parsers/directory_watcher.py` — tier-1 hoist + 보존 모드 | 🟢 **심볼 실측(2026-08-13)** | **`831ab68`**(HEAD) | 2,293 → **2,681줄**. 신설 심볼 7종, `sweep_existing_files`의 **반환 의미가 바뀌었다** |
| 🆕⑤ §5-C `server/db_safety.py` — 읽기 전용 가드가 여기로 왔다 | 🟢 **심볼 실측(2026-08-13)** | **`1260c9b`**(범위 내, HEAD와 blob 동일) | 215 → **453줄**. 소비처 7파일 전건 grep 확인 |
| 🆕⑤ §5 `server/database/models.py` — `FileIngestionCheckpoint`만 | 🟠 **한 클래스만 실측(2026-08-13)** | **`831ab68`**(HEAD) | 984(구 등재) → **1,041줄**. **이 클래스 밖 앵커는 재측정하지 않았다** |
| 🆕🆕🆕🆕 §2 `server/database/crud.py` — 3단 tie-break + 드롭 가시화 | 🟢 **심볼 실측(2026-08-11 3차 후속)** | **`347de78`** | 3,980 → **4,172**. `compute_priority_value(sources, manual_priority_source=None, table_name=None, ingested_at_by_source=None)` — 종전 「등재 우선순위만」이 **선언 우선순위 → `ingested_at` 내림차순 → `source_name` 오름차순**의 3단 전 순서로 바뀌었다(신설 `resolution_ingested_at(entry, source_name=None, ingested_at_by_source=None)`). `_warn_undeclared_column_once`는 **프로세스당 1회 경고**에서 **매 드롭 카운트 + 10의 거듭제곱마다 재공지**로 바뀌었고(`_DROP_ANNOUNCE_AT`), 신설 공개 함수 `undeclared_column_drops() -> dict`가 그 카운트를 프로세스 밖(다른 프로세스인 `main.py`)에서 읽게 한다 |
| 🆕🆕🆕🆕 §4 `server/chain_replay.py` — R3 신설 | 🟢 **심볼 실측(2026-08-11 3차 후속)** | **`347de78`** | 712 → **947**. **R3 `recompute_display_values(db, table_name, columns=None, row_ids=None, apply=False, chunk_size=…, limit=None, max_report=DEFAULT_MAX_REPORT, log=…)`** 신설 — 아무 `cell_sources` 행도 건드리지 않고 이미 저장된 레이어 전체에 `compute_priority_value`를 다시 돌려 **이미 잘못 확정된 표시값만** 고친다(2레이어 미만 셀은 절대 손대지 않는다). R2(`withdraw_source`)와 새 공유 헬퍼 **`_load_cell_state(db, table_name, chunk_row_ids)`**(소스+Pin 배치 2질의) / **`_resolve_cell(table_name, col_types, row, col, cell_sources, pin, exclude_source=None)`**(둘의 유일한 판정 지점)로 수렴 — `withdraw_source`가 이 둘로 재배선됐다. CLI `chain_replay_cli.py`(155→**210**줄)에 `resolve <table> [--apply]` 서브커맨드 신설 |
| 🆕🆕🆕🆕 §5 `server/map_alignment.py` — 워크리스트가 나쁜 행 하나로 전멸하지 않는다 | 🟢 **심볼 실측(2026-08-11 3차 후속)** | **`c4a3159`**(HEAD) | 6,468 → **6,528**. `build_alignment_worklist`의 `frame_confirmation.compose_unit_key` 호출이 맨몸 → `try/except ConfirmationRefused`로 바뀌었다: 결정키가 빈 행은 **그 행 하나만** `state=STATE_UNIT_UNSCORABLE, reason=REASON_UNIT_KEY_INCOMPLETE`(신설, `="unit_key_incomplete"`)로 남고 나머지 단위는 살아남는다(종전엔 예외가 `ValueError`가 아니라 라우트까지 올라가 **요청 전체**가 500). 신설 `_worklist_reason_text(code, detail=None)`가 사유에 **비어 있던 컬럼 이름**을 붙인다(`crud.is_blank_value`로 판정 — `compose_unit_key`와 같은 술어, `contracts/blank_predicate` 고정). **정렬 키도 별도 가드가 필요했다** — `unit_key=None`인 행이 하나라도 섞이면 `None < str` 비교가 `TypeError`로 다시 500이 되므로, `_sk`가 `uk = u["unit_key"] or ""`로 정렬 직전에만 치환한다(두 가드는 각각 독립적으로 필요 — 하나만 있으면 다른 경로로 500) |
| 🆕🆕🆕🆕 §1 `server/main.py` — 이력 봉투 확장 + tie-break 읽기 경로 | 🟢 **심볼 실측(2026-08-11 3차 후속)** | **`c4a3159`**(HEAD) | 6,286 → **6,322**. `GET /audit_logs/recent`가 맨 배열에서 **`schemas.AuditLogGroupPage`(신설) 봉투**(`{groups, truncated, next_cursor, limit_groups, returned}`)로 전환(`fde424c`) — 헤더 `X-Audit-Truncated`/`X-Audit-Next-Cursor`는 **그대로 병존**. `fetch_and_merge_metadata`가 `cell_sources.ingested_at`도 선택해 `crud.compute_priority_value(..., ingested_at_by_source=ingested_map.get(key))`로 넘긴다(`347de78` — 안 넘기면 조회 경로가 **알파벳순**으로, 쓰기 경로가 **최신순**으로 갈려 배지가 다른 레이어를 가리킬 수 있었다). `get_cell_sources`·`query_cells_sources`도 같은 커밋에서 `.order_by(models.CellSource.source_name.asc())`를 얻어 `fetch_and_merge_metadata`의 SELECT까지 **3곳 전부**가 순서를 명시한다. 퇴역한 `GET /enrichment`·`/enrichment.html`의 404 문구가 "빌드를 먼저 하라"에서 **"폐지됨 · 참조뷰 → 메인 화면 이력 사이드바 탭"**으로 바뀌었다(`fde424c`) |
| 🆕🆕🆕🆕 신설 `server/chain_bindings.py` | 🟢 **실측 신규 등재(2026-08-11 3차 후속)** | **`5b09d69`** | **244줄, 신설.** job-column 이름의 단일 해석기 — `rule[key]` 선언 > `table_config` 유도(`identity_column`: `map_key_columns` 단일 컬럼 우선, 그다음 `business_key`) > **이름을 대고 거절**(`ColumnBindingRefused(ValueError)`). 리터럴 기본값(`"dt_job"`) 없음. `resolve_column(rule, key, table, purpose)` / `resolve_decision_column(rule, key, decision_key, purpose)`(정렬 규칙의 `decision_key` 소스) / `model_column(model, table, column, purpose)`(로드된 모델에 그 속성이 없으면 거절) / `identity_column(table)` / `declared_columns(table)`. 해석은 **체인이 아니라 테이블 단위** — 트리거·소스·타깃이 각자 다른 이름을 선언할 수 있다. `map_overlay.resolve_binding_parts`(좌표 바인딩)와 **의도적으로 별개**(그쪽은 lot/slot 관습 폴백을 갖고 있어 이 모듈이 피하려는 바로 그것을 한다). ⚠️ `ORIGIN_DECLARED`/`ORIGIN_INHERITED` 중 **`ORIGIN_INHERITED`는 선언만 되고 이 파일 안에서 반환되지 않는다**(`identity_column`이 실제로 돌려주는 origin 문자열은 `"table_config.map_key_columns"`/`"table_config.business_key"`) — 죽은 상수인지 예약값인지는 확인 못 함 |
| 🆕🆕🆕🆕 §5-G 맵퍼 6종 — `dt_job` 리터럴 철회 | 🟢 **심볼 실측(2026-08-11 3차 후속)** | **`5b09d69`** | `chain_rules` 5종(`core_alignment_mapper`·`core_usage_mapper`·`dt_alignment_metadata_mapper`·`dt_inventory_metadata_mapper`·`dt_standard_map_mapper`, 전부 `.py.sample`) **+ 이 문서에 그전까지 등재된 적 없던 `dt_map_mapper.py.sample`**이 전부 `chain_bindings.resolve_column`/`resolve_decision_column`/`model_column`으로 job-column을 해석하도록 바뀌었다 — `DEFAULT_SOURCE_COLUMN = "dt_job"` 같은 리터럴 기본값이 전부 삭제됐다(운영 컬럼은 `dt_job_id`). 트리거·소스·타깃마다 **자기 이름**을 따로 해석한다(같은 맵퍼가 세 테이블을 걸치면 세 이름). 아래 §5-G 표에 규칙별 상세 |
| 🆕🆕🆕🆕 §7-A `map2/view_model.js`·`main.js` · `map_editor2.js`(페이지 엔트리) | 🟢 **심볼 실측(2026-08-11 3차 후속)** | **`3d43a6c`** | `view_model.js` 1,224 → **1,395**(export 5종 신설: `RULE_ADOPTION`·`DECISION_KEY`·`decisionKeyOf(declaration, decision) -> {state,key,columns,missing}`·`declaredKeyColumns(declaration)`·`decisionKeyRefusal(result)`) — 하드코딩 `{dt_eqp, product}`를 매 아리티(1/2/3)에서 규칙의 `decision_key` 그대로 채우는 순수 조립기로 대체. `selectAlignmentRules(rules)`가 `state`/`reason` 필드를 얻어 **"0건 채택됨"과 "로딩 중"을 구분**한다(종전엔 채택 실패가 침묵이라 로딩과 구별 불가). 소비자 `client2/src/map_editor2.js`(412→**470**줄)에서 **`keyFrom` 함수가 완전히 삭제**됐다(실측: HEAD blob grep 0건) — `adoptRule`이 이제 `decisionKeyColumns: declaredKeyColumns(declaration)`을 컨텍스트에 실어 `map2/main.js`(2,454→**2,489**줄)의 확정 버튼 핸들러가 **요청 전송 전에** 미충족 결정키를 거절한다. `map2/api.js`(572→**574**)는 에러 메시지 문구만 정정(시그니처 무변경) |
| 🆕🆕🆕 §6 `server/audit_cache.py` · `audit_history.py`(신설) | 🟢 **심볼 실측(2026-08-11 후속)** | **`2630790`**(HEAD) | `audit_cache.py` **247 → 643줄**(전면 재작성). 「growing OFFSET로 100그룹 찾을 때까지 훑기」가 **config-driven ceiling(`RECENT_DEFAULTS`) + `(timestamp, id)` keyset walk + DB-side aggregate(`_count_by_transaction`) + bounded hydration(`_hydrate`)**로 바뀌었다 — `truncated`/`next_cursor`/**이벤트 크레딧**(`_claim`/`_absorb_one`, `add_logs_batch`가 워터마크를 못 넘기는 경로의 이중 카운트 수정) 신설. `audit_history.py`(신설, 242줄)는 `fetch_page`/`encode_cursor`/`decode_cursor`/`apply_cursor`/`order_desc`/`load_config`/`resolve_settings`/`resolve_limit`을 서버 3곳(`audit_cache`·`main.get_row_history`·`main.get_cell_history`)이 공유 |
| 🆕🆕🆕 §5 `server/map_overlay.py` · `ontology_config.py` · §5-B `config_resolve_report.py` | 🟢 **심볼 실측(2026-08-11 후속)** | **`68db020`** | 좌표·정체성 바인딩이 **블록 단위**(선언 있으면 통째로 채택)에서 **키 단위 상속**(`선언 > table_config 유도 > 이름을 대고 거절`, 키마다 독립)으로 바뀌었다 — `derive_binding_parts`/`resolve_binding_parts`/`BINDING_KEYS`/`ORIGIN_DECLARED`·`_INHERITED`·`_ABSENT`·`_REFUSED` 신설, `resolve_binding`/`resolve_binding_info`는 **위임**으로 강등(`map_overlay.py` 2,526→**2,712**). `ontology_config.py`(463→**531**)는 그래프 노드/엣지 정체성이 같은 유도를 상속하는 토큰 **`INHERIT_MAP_IDENTITY = "@map_key_columns"`**를 얻었다(`_map_identity_columns`/`_expand_identity`가 `map_overlay.derive_binding_parts`에 위임 — 두 번째 유도 구현이 아니다). `config_resolve_report.py`(668→**833**)는 **4번째 도메인** `DOMAIN_BINDING`(`_resolve_binding`, `_RESOLVERS`에 **마지막으로** 등록)으로 그 결과를 테이블·키 단위 문장으로 보고한다 |
| 🆕🆕🆕 §5 `server/map_alignment.py` · `frame_confirmation.py` · §5-G 맵퍼 | 🟢 **심볼 실측(2026-08-11 후속)** | **`68db020`** | `_basis_cells_for`의 **세 번째 손제작 사본**이 하나로 합쳐졌다 — `frame_confirmation._basis_cells_for`(private, **삭제**)와 `mappers/dt_alignment_metadata_mapper._basis_cells_for`(private, **삭제**)가 없어지고 **`map_alignment.basis_cells_for(db, reference, cfg=None)`**(public, 신설)로 대체됐다. `frame_confirmation.py` 837→**798**(-39, 삭제분). `map_alignment.py`는 6,395→**6,468** |
| 🆕🆕🆕 §7 `client2/src/timeline.js` · `state.js` | 🟢 **심볼 실측(2026-08-11 후속, `readHistoryPage` 시그니처는 3차 후속 `fde424c`에서 재정정)** | **`dab9152`** | 행/셀 이력 응답이 **봉투**(`{logs, truncated, next_cursor, limit, returned}`)로 바뀌며 클라에 페이징 3종 신설: `readHistoryPage(body)`(봉투/구 배열 양쪽을 수용) · `beginHistorySession()`(비동기 경합 가드) · `loadMoreHistory(btn)`(「더 보기」 append, 400은 커서 만료로 별도 처리). `state.js`에 세션·커서 필드 4종(`cellRowHistoryCursor`/`_Truncated`/`_Loaded`/`_Session`) 추가. `timeline.js` 722→**899**→**917**줄. 🆕🆕🆕🆕 **[`fde424c`] `readHistoryPage(body, listKey = 'logs')`** — 두 번째 인자가 붙었다(행/셀 이력은 `'logs'` 기본값 그대로, 전역 탭은 `'groups'`를 명시). **반환 필드명은 언제나 `logs`**(호출자가 구조분해로 이름을 바꿔 받는다: `const { logs: groups } = readHistoryPage(body, 'groups')`) — 리더를 갈라 만들지 않고 파라미터화한 것이 요점(§`main.py`/`schemas.AuditLogGroupPage` 참조). `loadHistory()`의 전역 탭 절반이 이제 이 봉투를 연다(`state.globalHistoryData = groups`) |
| 🆕🆕🆕 §7 `client2/enrichment.html`(삭제) · `enrichment.js`(고아) | 🔴 **삭제·고아 확인(2026-08-11 후속)** | **`ab36fab`** | **`client2/enrichment.html`과 그 vite 빌드 엔트리가 삭제됐다.** 🔴 **`server/main.py`의 `serve_enrichment_page`(`GET /enrichment`·`/enrichment.html`) 라우트는 지워지지 않고 남아 있으며 이제 무조건 404다**(`dist`에도 dev 경로에도 파일이 없다 — [§1.4](#14-api-라우트-표--어드민운영그래프맵인리치먼트) 참조). `client2/src/enrichment.js`는 **런타임 소비자가 0**(어느 `.js`도 `import`하지 않는다 — HTML 진입점이 유일한 소비자였다)이지만 파일 자체는 무변동(1,266줄, 삭제하지 않았다)이고, **하니스 4개**가 여전히 그 소스 텍스트를 정규식으로 슬라이스해 채점한다(`enrichment_grid_sort_filter_harness.mjs` · `enrichment_partial_key_reference_harness.mjs` · `enrichment_provenance_harness.mjs` · `enrichment_queue_partition_harness.mjs`) — 이 넷은 배선이 아니라 **텍스트 추출**이라 페이지가 죽어도 계속 돈다 |
| 🆕🆕 §5 `server/map_alignment.py` · §5-F 채점 계열 | 🟢 **심볼 실측(2026-08-11)** | **`7097a67`**(HEAD) | 5,993 → **6,395**. 🔴 **후보 공간의 두 번째 축이 `side`(거울)에서 `start`(시작 모서리)로 *교체*됐다** — `load_alignment_sides`/`SIDES_KEY` **삭제**(→§0 ⑱), `candidate_text`/`parse_candidate`/`candidate_start`/`left_to_right_of` 신설. 🔴 **§5-F ①의 「축은 있는데 아무도 탐색하지 않는다」가 이제 거짓이다** — `left_to_right_of`를 부르는 것은 **`_anchor_shift`와 `score_candidates`**다(개수 대신 이름으로 고정한다). `_solve_shift`·`start_from_placement`·`score_candidates`·`build_alignment_view`·`_anchor_shift`·`direction_judge`·`_index_member` 시그니처 정정 |
| 🆕🆕 §5 `server/map_overlay.py` | 🟢 **심볼 실측(2026-08-11)** | **`7097a67`**(HEAD) | 2,289 → **2,526**. 🔴 **직전 등재는 `87a944e` 기준이었고 `77b4388`이 그 뒤에 원점 상자를 넣었다** — `origin_box` · `die_mask_from_reference` · `_ORIGIN_BOX_CACHE` 신설, `_frame_transformer`/`make_frame_transform`에 **box 인자**. 선형부 계열 `frame_linear_part`/`apply_linear`/`_mat_mul`/`_side_matrix`/`_ROT_FWD`/`_ROT_INV`/`make_physical_transform`도 미등재였다 |
| 🆕🆕 §5 `server/frame_confirmation.py` | 🟢 **심볼 실측(2026-08-11)** | **`7097a67`**(HEAD) | 815 → **837**. **top-level 심볼·시그니처는 `34d2518` 대비 무변동**(전건 대조) — 바뀐 것은 `_placement_of` **본문**이다(`97b29da`: `ruling["by_frame"]` 우선 조회) |
| 🆕🆕 §7-A `map2/candidates.js`·`main.js`·`view_model.js`·`decode.js` | 🟢 **export 실측(2026-08-11)** | **`7097a67`**(HEAD) | `candidates.js` 80 → **103**이고 **export 집합이 바뀐 유일한 map2 모듈**이다(`SIDES`/`SIDE_HEADERS` → `STARTS`/`START_TOKEN`/`CANDIDATE_SIDE`/`START_HEADERS`). 나머지 셋은 **export 무변동**이고 줄 수만 움직였다(main 2,453→**2,454** · view_model 1,226→**1,224** · decode 913→**919**) |
| 🆕🆕 §5/§6 신설 서버 모듈 · 스크립트 · 맵퍼 | 🟢 **실측 신규 등재(2026-08-11)** | **`7097a67`**(HEAD) | `alignment_view_service.py`(**85**) · `dt_frame_transform.py`(**96**) · `scripts/` 3종 · `mappers/*.py.sample` **5종**(DT/core 체인). `chain_replay.py`·`chain_ingestion_worker.py`·`audit_cache.py`·`main.py`의 신설 심볼도 실측 |
| 🆕🆕 §7 `client2/src/enrichment_reference_view.js` | 🟢 **실측 신규 등재(2026-08-11)** | **`1e29078`** | ⚠️ **측정 시작 시점(`7097a67`)에는 untracked였고 import 셋만 modified였다** — 그 상태의 커밋은 빌드를 깨뜨렸을 것이다. `1e29078`이 **파일과 import 셋을 함께** 넣어 그렇게 되지 않았다. 실측 blob은 워킹트리와 바이트 동일 |
| 🆕🆕 인제션·outbox 경로(`database/crud.py` · `database/database.py` · `parsers/directory_watcher.py`) | 🟠 **심볼 무변동 확인만(2026-08-11)** | **`7097a67`**(HEAD) | 🔴 **이 패스는 세 파일의 top-level `def`/`class`/상수 집합이 `34d2518` 대비 *한 글자도* 다르지 않음을 확인했을 뿐이다**(`directory_watcher.py`는 `5609ff0` 대비로도 동일). `528dfcb`·`4738d84`는 `34d2518` **이전**에 착지했으므로 2026-08-08 패스의 범위였다. **산문 서술은 이 패스가 재검증하지 않았다**.<br>🆕⑤ ⚠️ **[2026-08-13] 이 행의 「심볼 집합 무변동」은 `directory_watcher.py`에 대해 더 이상 참이 아니다** — `ba664c5`+`831ab68`이 top-level 심볼 4종·메서드 5종을 추가했다(아래 🆕⑤ 행). `crud.py`·`database.py`는 이번 패스가 열지 않았다 |
| 🆕 §2 `server/database/crud.py` | 🟢 **심볼 실측(2026-08-08)** | **`34d2518`**(HEAD) | 3,209 → **3,980**. `4738d84`·`528dfcb`·`818c9c0`. **[P3] 미착지 블록이 착지해 등재로 전환**했고, 예고에 없던 **두 번째 행당 관문 `_find_business_key_conflict`**를 실측으로 찾아 신설 등재했다. D3 재생 계열 6종 신설. ⚠️ **`apply_batch_updates`는 얇은 래퍼가 됐지만 시그니처·4-튜플·호출부 13곳 전부 무변경** |
| 🆕 §5 `server/map_alignment.py` · §5-F 채점 계열 | 🟢 **심볼 실측(2026-08-08)** | **`34d2518`**(HEAD) | 5,961 → **5,993**. `serpentine_index`/`_rank`에 **`left_to_right`** 축 추가(🔴 **배선 전 — 채점기가 탐색하지 않는다**) · `compose_refusal` 분기 1건 · **`_ConsoleSafeHandler`가 클래스에서 별칭으로 바뀌었다**. 🔴 **지시서가 준 라인 셋(`~665`·`~712`·`~716`)은 전부 정의가 아니었다** — 실측 정의는 `confirmed_meta_for` **547** · `start_for_placement` **748** · `start_from_placement` **808** |
| 🆕 §6 `utils/logger.py` · `event_constants.py` · `database/database.py` · 신설 3모듈 | 🟢 **실측(2026-08-08)** | **`34d2518`**(HEAD) | `logger.py` 145 → **221**(등재 앵커 셋 전부 낡았다) · `event_constants.py` 86 → **223**(outbox **접기** 절 신설) · `database.py`에 `stage_collapsed_event` · 신설 등재 **`outbox_expand.py`** · **`migrations/add_business_key_unique_index.py`** · **`scripts/check_missing_business_key.py`** |
| 🆕 §4 `server/chain_ingestion_worker.py` | 🟠 **라인 앵커만 재측정(2026-08-08)** | **`34d2518`**(HEAD) | 1,086 → **1,198**. 🔴 **밀림이 조각이다 — +4 / +55 / +96 세 구간.** 표의 「라인」 열은 절 머리의 재측정 블록이 대체한다. **산문 서술 자체는 재검증하지 않았다** |
| 🆕 §7-A `map2/main.js`·`view_model.js` · §7 `enrichment.js` | 🟠 **부분(2026-08-08)** | **`34d2518`**(HEAD) | `main.js` 2,437 → **2,453** · `view_model.js` 1,197 → **1,226**(`spellFrame`/`startLabel`/확정 관문). 🔴 **`enrichment.js`의 등재값 905줄은 실측 1,266 — 그 낡음은 이번 라운드보다 앞선다**(`e943e46`에서 이미 1,252). 그 절의 `~NNN` 앵커는 **여전히 미검증** |
| §7 `client2/src/map_editor.js` | 🟢 **심볼 실측** | `5609ff0` | 🔴 **이 절이 이번 판정의 증거다.** 앵커를 `cfa22ce`에서 전건 실측한 직후 `067f312`가 파일을 바꿔 **라인이 또 밀렸다**(+17 × 143). 그런데 **심볼 338개는 하나도 사라지지 않았다**(`5609ff0` 대조, 소실 0). **틀린 것은 심볼이 아니라 숫자였다** — 그래서 숫자를 버리니 절이 다시 맞았다 |
| §5 `server/map_overlay.py` | 🟢 **실측** | `87a944e` (HEAD와 blob 동일) | 근사(`~NNN`) 표기를 전부 실측값으로 교체 |
| §5 `server/map_alignment.py` · `frame_confirmation.py` | 🟢 **심볼 실측(2026-08-07 전면 재측정)** | **`e943e46`**(HEAD) | 🔴 **직전 등재값은 `87a944e` 기준이었고 그 사이에 파일이 배로 늘었다** — `map_alignment.py` **3,272 → 5,961**, `frame_confirmation.py` **688 → 815**. 정렬 **채점 계열**(순번 훑기·방향·그룹·bin 지문·앵커/잔차 배치·진단 로그)이 통째로 미등재였다 → [§5-F](#5-f--정렬-채점-계열-index-scoring-family--servermap_alignmentpy-2026-08-07-등재)에 신설 등재 |
| §5 `server/migrations/add_frame_confirmation.py` | 🟢 **실측(신규 등재)** | `87a944e` (HEAD와 blob 동일) | 이번 라운드 미접촉 |
| §1 `server/main.py` — 라우트·헬퍼 표 | 🟢 **실측** | `87a944e` (HEAD와 blob 동일) | 표 앵커 76개 기계 대조 통과 |
| §2 `server/database/crud.py` | 🟠 **부분(2026-08-07)** | **`e943e46`**(HEAD) | `_get_or_create_row` 행 하나를 HEAD 기준으로 재판정했고, 문서 전역의 벗은 `crud.py` 표기를 **`server/database/crud.py`**로 온전화했다(§2 도입부의 ⚠️ 경로 경고 참조). **표의 나머지 행은 `87a944e` 이후 재측정 안 함.** 🔴 **미착지 변경이 이 절을 다시 바꾼다** — 아래 [P3] 블록 |
| §5 `server/bonding_plan.py` | 🟢 **실측** | `87a944e` (HEAD와 blob 동일) | 〃 |
| §7-A Map Editor 2 (`map_editor2.js` + `map2/` **18**모듈) | 🟢 **심볼 실측(2026-08-07 재측정)** | **`e943e46`**(HEAD) | 🔴 **모듈 수가 17이 아니라 18이다** — `index_ramp.js`가 미등재였다. 줄 수는 **전부** 밀려 있었고(예: `decode.js` 589 → **913** · `main.js` 1,975 → **2,437**), export도 늘었다(`decodeIndexWalk`·`INDEX_WALK_*` · `placeCells`/`FLOOR_PLACEMENT` · `DECIDED_BY_DIRECTION` · `withConfirmFailed` · `seatingFor`/`floorSeating`). 산문 라인 앵커는 **심볼로 교체**했다 |
| §7 `push_columns.js` · `enrichment_queue.js` | 🟢 **실측(신규 등재)** | `87a944e` | |
| §5-E `server/notation_norm.py` | 🟢 **실측 + 정리** | `5609ff0` | 철회된 API 행을 **삭제**하고 현행 API를 전건 실측으로 다시 깔았다. 이 모듈은 이제 **저장하지 않는다** — 접기는 질의 시점 SQL이다 |
| §1.6 `server/admin_auth.py` | 🟠 **부분** | — | **EOF 밖 앵커 1쌍**(`GATE_CHALLENGE_HEADER`/`_GATE_HEADERS`가 463줄 파일에 **5846/5847**로 적혀 있었다 → **100/101**)과 지문 상수 행만 고쳤다. **나머지 미검증** |
| §5 `server/retroactive.py` · `process_supervisor.py` · §3 `parsers/directory_watcher.py` | 🟢 **심볼별 실측** | `5609ff0` | ⚠️ **오프셋은 균일하지 않았다** — 「전건 +23 / +92 / +62」는 틀린 모델이다. 각 절은 **앞부분이 이미 맞고 어느 지점부터 밀린 조각(piecewise)** 이었다(예: `retroactive.py` 16개 중 6개는 이미 정확). 그래서 오프셋을 더하지 않고 **심볼마다 실측값으로 다시 적었다**(54개 정정). 남은 미검증: 표 밖 산문 앵커 |
| 🔴 **그 밖 전부** — `admin.js` · `enrichment_config.py` · `enrichment_candidates.py` · `transfer_plan.py` · `graph_*` · `contracts/*` · 나머지 클라 모듈 | 🔴 **미검증** | — | 감사 실측: `admin.js` 앵커 61개 중 **정확 0** · `enrichment_candidates.py` 36개 중 **0** · `enrichment_config.py` 37개 중 **0** · `directory_watcher.py` 142개 중 **16**. **이 절들의 라인 번호를 믿지 말고 함수명으로 Grep하라** |

> 🔴 **[2026-08-07 이 패스가 실제로 고친 것 — 범위는 위 표의 세 행뿐이고 나머지는 열지 않았다]**
> - 🔴 **경로 하나가 문서 전체에서 벗겨져 있었다.** 이 저장소에 **`server/crud.py`는 없다** — 실제 경로는 **`server/database/crud.py`** 하나다. 그런데 산문은 `crud.py:1623`·`crud.py **1969–1974**`처럼 파일명만 적어 왔고, 그 표기를 그대로 따라간 독자는 **존재하지 않는 파일**을 찾게 된다(2026-08-07에 실제로 그럴 뻔했다). 이번 패스에서 벗은 표기를 전부 온전한 경로로 바꿨다. **모듈 이름으로서의 `crud.xxx`**(파이썬 심볼 참조)는 그대로 둔다 — 그것은 파일명이 아니다.
> - 🔴 **`map_alignment.py`는 등재 이후 3,272 → 5,961줄이 됐고, 늘어난 절반이 통째로 미등재였다.** QA 둘이 독립으로 관찰한 「정렬 채점 계열이 어느 문서에도 없다」가 실측으로 확인된다. → [§5-F](#5-f--정렬-채점-계열-index-scoring-family--servermap_alignmentpy-2026-08-07-등재) 신설.
> - 🔴 **`069b4e9`가 `map_alignment.py`에 +283/-8을 넣어 삽입 지점 뒤의 라인이 전부 밀렸다.** 이 문서의 §5 map_alignment 절은 이미 라인을 걷어낸 뒤였으므로 **표에서는 아무것도 깨지지 않았다** — 깨진 것은 이 문서 밖에서 라인으로 인용하던 쪽이다(실측 예: `direction_violations` **호출부**가 `3079` → **`3167`**로 이동, **정의는 `1513`**에 있다. 「보고서의 3079」는 호출부였고 정의가 아니었다). 🔴 **이것이 라인 인용이 실패하는 두 방식을 한 자리에서 보여 준다** — 숫자가 밀리는 것과, 밀리지 않았어도 **정의가 아니라 호출부**를 가리키는 것.
> - 🔴 **`map2/` 모듈이 17이 아니라 18이었다**(`index_ramp.js` 미등재). 「개수를 적지 않는다」 규율이 절 제목에서 새고 있었다.

> 🔒 **[2026-08-06 총괄 판정] 라인 인용 예외는 폐기됐다 — 🟢 절은 *심볼*로 전환됐다.**
> 위 🟢 절에서는 **라인 번호를 걷어냈다**: 표의 「라인」 열 삭제 · 오프셋 계단표 삭제(라인 장부라 판정과 함께 무의미해졌다) · 산문의 심볼 위치 숫자 삭제. **남긴 숫자는 두 종류뿐**이다 — ① **파일 줄 수**(크기) ② **이름이 없는 덩어리**(주석 블록·리터럴 집합)를 가리키는 범위, 그리고 이 경우 **측정 sha를 함께** 적었다.
>
> 🔬 **전환의 검증 = 심볼 게이트**(라인 앵커 검사를 대체한다). 🟢 절이 인용하는 백틱 식별자를 **그 절의 소스 파일에서 `5609ff0` 기준으로 찾는다**: **1,417개 검사 · 미해결 19개**, 그리고 그 19개는 전부 정당하다 — 라이브러리 이름(`outerjoin`·`requests`) · config JSON 키(`__comment`) · 서술된 반환 모양(`leg_dict`) · **축약 연속 표기**(`GRAPH_CHIP_TRACE_SEED_LABEL` … `_CHIP_LEGS`처럼 앞부분을 생략한 형태). 별도로 **묘비·타 파일 참조 66개**는 면제로 분류된다(그 이름들은 **없는 것이 맞다**).
> 🔴 **이 검사가 라인 앵커보다 나은 이유는 정확도가 아니라 *실패하는 방식*이다** — 낡은 라인은 실재하는 다른 함수를 가리키며 멀쩡해 보이고, 낡은 심볼은 **Grep 0건**으로 자기가 낡았다고 말한다.
>
> 🔬 **그리고 이 세션이 그것을 우연히 실험했다.** 작업 중 HEAD가 **네 번** 움직였고 `map_editor.js`가 **두 번** 바뀌었다(`cfa22ce` → `62502fc` → 그 뒤 또). **라인 앵커는 그때마다 낡았다** — 한 번은 측정을 끝낸 직후에 +17줄 × 143개가 밀렸다. **심볼 게이트는 네 번 모두 같은 답을 냈다**: 1,417개 검사 · 미해결 19개 · **새로 깨진 것 0개.** 🔴 **틀린 적이 없는 것은 심볼이고, 네 번 틀린 것은 숫자다.**
>
> ⚠️ **위 🔴 행의 절을 읽을 때의 규율**: 라인 번호는 **길잡이도 못 된다**(0/61 같은 분포에서는 ±20 오차가 의미 없다). **함수명·시그니처만 1차 식별자로 쓰고 위치는 `git grep -n`으로 직접 확정하라.**
>
> 🔴 **이 문서를 손으로 재측정하지 마라.** 손 패스는 방금 55%에서 끝났고, 그 패스가 스스로를 100%라고 적었다. **재생성이 성립하지 않으면 「CODE_MAP은 라인을 인용해도 된다」는 예외 자체가 성립하지 않는다** — 그 판단은 총괄 소관이다. 재생성기를 쓸 경우 **반드시 알아야 하는 표기 충돌 2종**은 아래 「표기 규약」에 적어 둔다.

**📐 표기 규약 — 재생성기가 반드시 구분해야 하는 것 (2026-08-06 감사 발견)**

- 🔴 **굵은 3자리 숫자가 전부 라인 앵커는 아니다.** HTTP 상태코드(`**503**` · `**401**` · `**400**` · `**404**`)가 **앵커와 글자 모양이 같다.** 상태코드를 앵커로 읽고 "고치면" 그 서술이 파괴된다.
- 🔴 **`` `SYM` **VALUE**(**ANCHOR**) `` 꼴에서 첫 굵은 값은 *상수의 값*이고 라인이 아니다**(예: `` `MAX_VALID_DIE_CELLS` **20_000**(**1690**) ``). 라인처럼 보이는 자리에 값이 앉는다.
- 앵커는 **`**NNNN**`** 또는 **`**A/B**`**(데코레이터/핸들러) 꼴이고, `**A/B**`는 **「심볼 둘」과 뜻이 다르다** — 후자에 `real-1/real`을 적용하면 조용히 틀린다(이 패스에서 21행이 그렇게 깨졌다가 복구됐다).

> 🔴 **[2026-08-06 이 패스가 실제로 고친 것]**
> - **§7 `map_editor.js` 앵커 253개가 *전부* 틀려 있었다 — 예외 0건.** 드리프트 **+8 ~ +185줄**. 직전 패스의 「파일 앞 ~300줄은 무이동」은 **관찰이지 성질이 아니었다.**
> - 🔴 **살아 있는 앵커 다섯이 없는 것을 가리키고 있었다**: `physFrameOverride`(구 1432)·`withPhysFrame`(구 1538)은 **삭제**, `PUSH_SYSTEM_COLUMNS`(구 5760)·`getUnprotectedPushColumns`(구 5782)·`logShapedPushDecision`(구 5801)은 **`push_columns.js`로 이사**. 다섯 다 「그럴듯한 도착지」가 있어 ±20 오차로는 안 잡힌다.
> - 🔴 **`map_editor.js`의 시그니처 10개가 인자를 하나 더 받는다**(`frame` 선두). **이것이 이 문서에서 가장 위험한 낡음이다** — 인자가 앞에 끼면 옛 호출은 **던지지 않고 틀린 답을 낸다.**
> - 🔴 **두 절이 자기 자신과 모순돼 있었다.** ① §5 `map_overlay.py` — 한 블록쿼트는 `apply_valid_die_ref`가 「실재한다」, 아래 문단은 「HEAD에 없다」(실측: 둘 다 실재, **1825**·**1875**). ② §2 `crud.py` — 표 한 행이 `refuse_notation_derived_columns`를 **살아 있는 앵커와 살아 있는 호출부로** 등재하는 동안 바로 아래 행이 「삭제됐다」고 적고 있었다. **독자는 표를 믿는다.**
> - 🔴 **§5-E가 존재하지 않는 API를 등재하고 있었다** — `8d306a5`가 철회한 `apply_derivations`·`rederive`·`derivations_for` 등이 **시그니처 표에 라인 번호를 달고** 앉아 있었고, 같은 절의 각주가 철회 사실을 적고 있었다. **각주는 표를 이기지 못한다. 그래서 주석이 아니라 삭제했다.**
> - 🆕 **신규 등재**: [§7-A Map Editor 2](#7-a--map-editor-2--map_editor2html--client2srcmap2-2026-08-0506-신설) · `push_columns.js` · `enrichment_queue.js` · [`map_alignment.py`](#-servermap_alignmentpy--프레임-정렬의-채점자) · [`frame_confirmation.py`](#-serverframe_confirmationpy--확정의-기록자) · `migrations/add_frame_confirmation.py`.
>
> ⚠️ **개수를 적지 않는 규율.** 「N번째 토큰」·「호출 6곳」류는 **다음 라운드가 하나 더하면 조용히 거짓이 되고, 개수만 맞으면 앵커가 전부 틀려도 통과한다.** 그래서 개수를 **구성원 목록으로** 바꿨다.
>
> 🔬 **소스가 이 지도를 반박하는 자리 — 코드 소관이라 여기서 못 고친다**: `server/map_overlay.py:572`가 `geometry_declaration`의 반환을 **「다섯 토큰」**이라 적는데 실제로 **여섯**을 낼 수 있고, **`:756`은 「네 토큰」**이라 적는다.
>
> ✅ **`map_editor.js` = 11,031줄인데 그중 코드는 6,391줄이다**(`87a944e` 실측: 공백 782 · 주석 3,858 = 비공백의 37.6%). 🔴 **원시 줄 수를 크기로 인용하면 코드를 약 73% 과대 보고한다.** 이 문서의 **「N줄」은 전부 원시 줄 수**(`wc -l`)다.
>
> 상위: [SYSTEM_OVERVIEW (SSOT)](../overview/SYSTEM_OVERVIEW.md)

**⚠️ 사용 규칙 — 이 문서가 존재하는 이유:**

- **소스 파일을 통째로 Read하지 말 것.** 이 지도에서 **파일과 심볼**을 찾은 뒤 `git grep -n "<심볼>" -- <경로>`로 위치를 확정하고 **그 구간만** `Read(offset, limit)`으로 읽는다.
- 🔴 **[2026-08-06 총괄 판정] 이 문서는 라인 번호로 심볼을 지목하지 않는다.** 1차이자 유일한 식별자는 **파일 경로 + 심볼명**이다. 종전의 「라인 앵커 ±20줄 오차 허용」 규율은 **폐기**됐다.
  - **왜**: 이 문서에만 라인 인용 예외가 있었고, 그 예외의 근거는 **「단위로 재생성된다」**였다. 2026-08-06 실측이 그 전제를 반증했다 — 재생성되지 않고, **이 표기법으로는 재생성될 수 없으며**, 손 패스는 **55%에서 끝나면서 스스로를 100%라고 적었다.**
  - ⚠️ **±20 오차 허용이 특히 위험했다**: `_band_to`가 65줄 밀리자 그 앵커 자리에 **`_band_materials`라는 실재하는 다른 함수**가 들어앉았다. 도착지가 멀쩡해 보이므로 **아무것도 이상해 보이지 않는다.** 라인은 틀렸다는 신호를 내지 못하고, 심볼은 Grep 0건으로 낸다.
- **라인 번호를 남기는 경우는 둘뿐이다.**
  1. **심볼이 나를 수 없는 정보일 때** — 함수 안의 특정 덩어리(hunk), 번호 붙은 절, 「이 주석 블록」처럼 이름이 없는 자리. 이때는 **무엇을 기준으로 쟀는지(sha)를 반드시 함께** 적는다.
  2. **생성기가 유지하는 값일 때**(현재 없음).
- 🔒 **예외가 돌아올 조건 — 다시 논쟁하지 말고 이 조건을 만족시켜라.** 라인 인용 예외는 다음 **둘 다** 참일 때만 부활한다:
  1. 앵커가 **산문과 구별되는 기계 판독 형식**을 가질 것. 지금 표기는 그렇지 않아서 재생성이 불가능하다 — 실측된 충돌: ① 굵은 3자리 **HTTP 상태코드**(`**503**`·`**401**`)가 앵커와 글자 모양이 같다 ② `` `SYM` **VALUE**(**ANCHOR**) ``는 **상수의 값**을 라인 자리에 앉힌다 ③ `**A/B**`가 라우트 행에서는 「데코레이터/핸들러」, 다른 행에서는 「심볼 둘」로 **뜻이 다르다**(이 혼동으로 21행이 조용히 깨졌다) ④ 한 백틱 안에 심볼 둘(`` `load_maps_config() / save_maps_config(data)` ``) ⑤ 산문 속 **타 파일 참조**가 EOF 밖 앵커와 구분되지 않는다.
  2. 그 형식을 검사하는 **생성기가 게이트에서 돌 것.** 🔴 **누군가의 성실성이 아니라 게이트가 조건이다** — 지금 폐기되는 예외가 정확히 「성실히 갱신될 것」이라는 가정 위에 서 있었다.
- `client2/*` 인용은 **`client2/src/`**(원본) 기준이다 — `client2/dist/assets/map_editor-*.js`는 vite 산출물이라 파일명 해시가 빌드마다 바뀐다. **dist 번들명을 문서에 고정 인용하지 말 것.**
- 이 문서는 **지도이지 교과서가 아니다** — 구현 설명은 각 리빙 문서([backend](./backend.md)·[data_model](./data_model.md)·[frontend](./frontend.md)·[event_driven_backend](./event_driven_backend.md)) 참조.

**유지보수 규율:** 코드맵 갱신은 **code-mapper 전담**(2026-07-27 문서 에이전트 분할 — 리빙 문서·`PRIMITIVES.md`는 doc-keeper, 히스토리는 doc-historian, 정합 감사는 doc-auditor). code-mapper는 **커밋된 소스와 직접 대조**해 갱신한다(보고서 요약이 아니라 `git show <hash>:<path>` 실측 — 워킹트리는 타 에이전트가 동시 편집 중일 수 있다). 구현 에이전트는 맵을 직접 수정하지 않고 보고서에 변경 함수/시그니처 목록만 남긴다. 라인은 보조 식별자이고 **함수명·시그니처가 1차 식별자**다.

---

## 0. 묘비 목록 — 소스에 **존재하지 않는** 이름

> **이 목록의 존재 이유**: 삭제된 심볼이 문서 어딘가에 살아남으면 **다른 에이전트가 없는 것을 찾으러 간다.** 더 나쁜 실패는 한 절이 "이 이름은 삭제됐다"고 경고하면서 다른 절이 그 이름을 **현행 앵커로 쓰는** 것이다 — 그 경고가 "이 파일은 감사됐다"는 증거로 읽히기 때문이다(2026-07-27 실제 발생: §7이 경고하고 §8이 사용했다).
>
> **그래서 이 목록은 단언이 아니라 검사다.** 아래 명령의 기대 결과까지 적어 둔다 — 결과가 달라지면 **이 절이 낡은 것이다**(명령이 틀린 게 아니라).
>
> ⚠️ **명령에 리비전을 박지 않는다 — 의도적이다.** 초판은 `0f8d35f`에 고정돼 있었고, 그래서 **구조적으로 초록불이었다**: 얼어붙은 스냅샷을 검사하는 명령은 파일이 썩어도 영원히 통과한다. 실제로 그 상태에서 두 라운드가 더 들어와 `_parse_bands`의 시그니처가 3-튜플이 되고 `_band_materials`가 **다른 함수의 앵커 자리(1188)를 차지**했지만 §0은 여전히 초록이었다. **검사는 지금 파일을 읽어야 검사다.** 그 대신 **라인 앵커와 §0은 서로 다른 보증**이라는 점을 알아 둘 것 — 앵커는 아래 "측정 기준"의 스냅샷이고, §0은 실행 시점의 트리다.
>
> ```bash
> # ① 클라 저장 기계장치 — 히트 0건이어야 한다
> git grep -n "putUpdates\|adoptServerDoe\|doeRowKey\|doeSourceRowKey\|doeServerLoaded\|serverRows\|deleteUnsent\|pruneScoped\|serverKeys\|DRAFT_PREFIX" -- client2/src
> # ② 서버 심볼 — 히트 0건이어야 한다
> git grep -n "_doe_get\|def _num\|_band_range" -- server/transfer_plan.py
> # ②-b U6 하드코딩 사본 (`95bf072` config-over-hardcode) — 히트 0건이어야 한다
> #    (서버의 `DEFAULT_VAL_CANDIDATES`는 살아 있는 documented default라 이 검사 대상이 아니다)
> #    ⚠️ 범위에 `client2/tests`가 **없다** — 그래서 이 검사가 초록인 채로
> #       `client2/tests/split_registry_harness.mjs`가 `DEFAULT_LEGEND`를 이름으로 계속
> #       추출하고 있었다(아래 표 3행). 검사 범위 밖은 검사되지 않는다.
> git grep -n "BUILTIN_STAGES\|DEFAULT_LEGEND\|OVERLAY_VAL_CANDIDATES" -- client2/src contracts
> # ③ layer_coverage_gap — 정확히 2건이고 **둘 다 묘비**다 (2026-07-28 재측정: 테스트
> #    주석은 b35bc9f의 테스트 재작성과 함께 사라졌다):
> #    server/transfer_plan.py             삭제 사유 주석(zone 모델에선 구멍이 표현 불가)
> #    client2/src/transfer_plan.js        __HELD_WARN_SEVERITY의 사문 키 (보류 구역, 호출자 없음)
> git grep -c "layer_coverage_gap" -- server client2
> # ④ 이 문서 안 — 히트는 전부 묘비 문맥이어야 한다(살아있는 앵커 0건)
> grep -n "adoptServerDoe\|doeRowKey\|deleteUnsent\|_doe_get\|layer_coverage_gap" docs/architecture/CODE_MAP.md
> # ⑤ [2026-07-30 신설] 코드에서 삭제된 이름 3종 — **선언부** 히트 0건이어야 한다
> #    (주석 히트는 남아 있다: main.py **~2383·~2430**, 둘 다 묘비 문맥 — 구 값 2357/2404는
> #     `9ac2083` 실측이었고 `cde3398`의 +26으로 밀렸다)
> git grep -nE "^\s*def (_escape_like_term|_chip_trace_declared_pairs|is_port_open)" -- server client
> # ⑤-b 그리고 그 셋이 이 문서에서 **앵커로** 쓰이지 않아야 한다.
> #     ~~물결~~이나 "삭제"·"묘비" 없이 `~숫자`가 붙어 있으면 그게 §1.5의 그 실패다.
> grep -n "_escape_like_term\|_chip_trace_declared_pairs\|is_port_open" docs/architecture/CODE_MAP.md
> # ⑥ [2026-07-30 신설] flatten(평탄화) 기계장치 7종 — **선언 히트 0건**이어야 한다.
> #    `600b49d`이 평탄화를 **제자리 인제션**으로 바꾸며 통째로 지웠다. `FLATTEN_*` 상수
> #    **셋은 살아 있다**(정온 폴·최대 대기·잡파일 명부)므로 접두어로 뭉쳐 검사하지 말 것.
> #    🔴 실측 히트 1건: `server/main.py:3328`(`41b17ee` 실측 — `ed9cfdb`의 3469에서 −141) 주석이 `directory_watcher._resolve_flatten_dest`를
> #       "같은 결과 기반 검사 규율의 선례"로 지목한다 — 그 함수는 없다. 이 주석은 `0d4798a`
> #       (업로드 경로 정화)에서 참일 때 쓰였고 **그 뒤 `600b49d`이 대상을 지웠다**. 서버 도메인
> #       소관이라 여기서 고치지 않았다. **히트가 2건 이상이면 새로 생긴 것이다.**
> git grep -nE "FLATTEN_SEP|_build_collision_name|_resolve_flatten_dest|_sanitize_flatten_component|_flatten_directory|_flatten_worker|flatten_nested_dirs_enabled|_flattening_dirs" -- server client2/src
> # ⑥-b 단, config **키** `flatten_nested_dirs`는 의도적으로 그대로다(운영자의 기존
> #     off 스위치를 개명으로 무력화하지 않기 위해) — 아래는 히트가 있어야 정상이다.
> git grep -c "flatten_nested_dirs" -- server/parsers/directory_watcher.py
> # ⑦ [2026-07-30 신설] 프레임 채택(adoption) 일습 8종 — `client2/src` 히트 0건이어야 한다.
> #    `94b9baa`이 채택 자체를 폐지하며 통째로 지웠다([§7 F8](#7-client2src--웹-클라이언트)).
> #    ⚠️ 범위가 `client2/src`인 것이 요점이다 — `client2/tests/`의 두 하니스는 이 이름들을
> #       **묘비 주석으로** 계속 언급하고(그게 옳다), 범위를 넓히면 이 검사가 영원히 빨개진다.
> git grep -nE "storedCoordRepositionPlan|applyStoredCoordReposition|repositionRefusalReason|adoptionCoordinateCost|adoptedFrameOf|dbCoordsByPhysKey|adoptFrameSpec|announceFrameAdoption" -- client2/src
> # ⑧ [2026-07-30 신설] 내부 이벤트 발신자가 자기 HTTP 세션을 만들지 않는다.
> #    유일한 지원 경로는 `internal_event_client.internal_event_session()`이다.
> #    🔴 실측 히트 **정확히 1건**: `chain_ingestion_worker.py:133`(`ed9cfdb` 실측) — 삭제된 코드를 설명하는
> #       **묘비 주석**이다(문자열이 백틱 안에 있다). **2건 이상이면 새 발신자가 생긴 것**이고,
> #       그것이 이 저장소가 같은 엔드포인트에서 이미 세 번 고친 결함이다.
> git grep -nE "requests\.(post|Session)\(" -- server/run_watcher.py server/chain_ingestion_worker.py server/graph_sync_worker.py
> # ⑨ [2026-07-30 신설, F9] config 해석 보고서의 **닫힌 어휘 4종이 클라 소스에 리터럴로**
> #    있으면 안 된다 — 히트 0건이어야 한다. 이 단어들은 응답 안에 실려 오므로
> #    **순회하는 것은 정당**하고 **적어 두는 것**이 금지다(적어 두는 순간 클라가
> #    「무엇이 효과 없음인가」에 대한 자기 의견을 갖고, 서버 테스트는 전부 초록인 채
> #    양쪽이 갈린다 — U6가 6개를 지운 그 계급이다).
> #    ⚠️ 이 검사는 `contracts/config_resolve_report/client_harness.mjs`(INV-F9-7)의
> #       **사본이 아니라 그것의 값싼 미리보기**다. 정본은 계약이고, 그것은 `npm run build`의
> #       `check:contracts`가 돌린다. 여기 적는 이유는 §0이 "없어야 하는 이름"의 목록이라서다.
> git grep -nE "not_declared|mapping_unavailable|scope_unresolved|not_reached" -- client2/src
> # ⑩ [2026-07-30 신설, `da8f390`] `originPhysOf` — **`client2/src` 히트 0건**이어야 한다.
> #    🔴 이 이름은 **직전 지도가 살아 있는 앵커로 등재했던 것**이다(구 §7 "~7487–7494,
> #       함수 안 지역 헬퍼"). `da8f390`이 정렬 판정을 **마스크가 앉은 뒤 한 번**으로 옮기면서
> #       그 헬퍼를 통째로 지웠고, 지금 원점 비교는 참조가 부르는 최솟값(`refMinX/refMinY`,
> #       `resolveValidDie` 안 **9002–9003**)과 이 맵이 선언한 START를 🆕 **`diagnoseDesignationAlignment`(9270) 안 9300**에서 비교한다.
> #       구 헬퍼가 쓰던 "DB (0,0)을 두 프레임으로 투영해 비교"는 마스크 재중심화 **이전**의
> #       인덱스 공간에서 재는 값이라 화면과 무관한 수를 냈다(실측: 화면은 맞아 있는데
> #       「31칸·8행 어긋남」). 사유 주석은 `map_editor.js` **9297–9298**(`diagnoseDesignationAlignment` 안)에 있다.
> #    ⚠️ 범위가 `client2/src`인 것이 ⑦과 같은 이유다 — `client2/tests/`의
> #       `valid_die_frame_adoption_harness.mjs`(1건)·`docs/history/**`(3건)·이 문서(다수)는
> #       전부 **묘비 문맥**이고, 범위를 넓히면 이 검사가 영원히 빨개진다.
> git grep -n "originPhysOf" -- client2/src
> # ⑪ [2026-07-31 신설, `35e84c3`] 좌표 코어 **개명 4종 + 식별자 2종** — `client2/src` 히트 0건이어야 한다.
> #    이 넷은 46개 호출부에서 한 번에 바뀌었다. 옛 이름을 앵커로 들고 있는 문서는
> #    **실재하는 다른 함수를 가리키는 것이 아니라 아예 없는 것을 가리킨다**(그 편이 낫다 —
> #    조용히 그럴듯해 보이지 않으므로).
> #      getVisualCoords           -> getDbCoords                (저장되는 좌표를 만든다)
> #      getCellFromVisualCoords   -> getCanvasCellFromDb
> #      getPhysicalCoords         -> getDieIndex                (셀 인덱스다. 밀리미터가 아니다)
> #      getCellFromPhysicalCoords -> getCanvasCellFromDieIndex
> #      지역 식별자 xv / yv       -> dbX / dbY                  (식별자 17개)
> git grep -nE "getVisualCoords|getCellFromVisualCoords|getPhysicalCoords|getCellFromPhysicalCoords" -- client2/src
> git grep -nE "\b(xv|yv)\b" -- client2/src
> # ⑪-b ⚠️ **`\b` 앵커 치환은 한글에 붙은 이름을 못 잡는다.** 한글은 단어 문자라
> #     `getPhysicalCoords의`에는 `s`와 `의` 사이에 경계가 없다 — 그래서 `§getPhysicalCoords의`
> #     하나가 개명 패스를 **통과해 살아남았다.** 잡은 것은 경계 없는 재스캔이다.
> #     즉 위 두 줄로는 부족하고, 개명 뒤에는 아래처럼 **경계 없이** 한 번 더 훑어야 한다.
> #     🔴 `client2` 히트는 **하니스의 개명 대조표 5건**이다(2026-08-04 전건 재계수 — 종전
> #        표기 "3건"은 낡았다. 신설 `client2/tests/startxy_probe.mjs`가 같은 대조표를 2건
> #        더 들고 왔다): copy_header_count_harness **152·268** · startxy_probe **65·68** ·
> #        valid_die_head_parity_oracle **60**. 옛→새 매핑을 이름으로 들고 있는 것이 옳다.
> #     🔴 `server`는 **2건**이다 — 종전 표기 "1건"은 **틀린 계수**였고, `1dc761b`에서도
> #        이미 2건이었다(2026-08-04 정정, 두 리비전 모두에서 재측정):
> #        `coordinate_transformer.py` **50**(`getPhysicalCoords`) · **138**(`getVisualCoords`).
> #        서버 도메인 소관이라 이 지도가 고치지 않았다. **3건 이상이면 새로 생긴 것.**
> #     ⚠️ 이것이 교훈 파일이 이름 붙인 그 함정의 재발이다 — **지목한 항목은 실재했고 개수만
> #        틀렸다.** 실재하는 앵커 하나가 서술 전체를 통과시킨다. 개수를 주장하는 서술은
> #        표본 확인이 아니라 **전건 계수**로 대조한다.
> git grep -nF -e "getVisualCoords" -e "getPhysicalCoords" -- client2 server
> # ⑫ 🪦 [2026-07-31 신설 → **2026-08-04 폐기**] ~~`mm`은 의도적으로 비어 있는 이름이다~~
> #    🔴 **이 검사의 전제가 코드에 의해 무효화됐다. 되살리지 마라 — 지금 되살리면 정상 코드를
> #       금지한다.** `cd3e0f4`(웨이퍼 mm 기준 오버레이)가 클라에 **진짜 밀리미터 공간**을
> #       들여왔다: `frameDieLattice`/`dieIndexToWaferMm`/`waferMmToDieCell`/
> #       `projectCellsToWaferMm`/`seatWaferMmInFrame`([§7 좌표 코어](#7-client2src--웹-클라이언트)).
> #       `mm`은 이제 **의미를 가진 이름**이고 `projectCellsToWaferMm`이 항목마다
> #       `mm: {mmX, mmY}`를 싣는다(map_editor.js **8749**).
> #    ⚠️ 검사가 막으려던 것은 여전히 옳다 — **밀리미터가 아닌 양이 이 이름을 쓰는 것**.
> #       하지만 그것은 grep으로 판정할 수 없고(이름만으로는 단위를 알 수 없다) 이제
> #       리뷰 규율이다. `isCellInsideWaferFast`가 원을 **700×700 픽셀**에서 시험한다는
> #       사실은 그대로다(map_editor.js **2329**) — mm 공간과 픽셀 공간은 별개다.
> #    🔬 **폐기의 근거는 이 검사가 이미 빨간불이었다는 것이다**: `client2/src/utils.js:8`의
> #       `const mm = pad(date.getMinutes())`(분(minutes)이지 밀리미터가 아니다)가 이 정규식에
> #       걸리는데, `1dc761b`에서도 걸렸고 그때 §0은 "선언 0건"이라고 적었다. **아무도
> #       돌리지 않은 검사는 초록불이 아니라 미실행이다.**
> # ⑬ [2026-08-04 신설] **이전(移轉)한 이름의 지역 재철자 금지 — 묘비가 아니라 이사다.**
> #    `689ebb9`가 맵 정체성 7종을, `636f867`이 registry 행 정규형 10종을 `map_editor.js`에서
> #    **잘라내 각자의 모듈로** 옮겼다. 이름은 살아 있고 소유자만 바뀌었으므로 이 표에
> #    행을 만들지 않는다(§0의 계약은 "있었고 지금은 없다"이다). 대신 검사는 **`map_editor.js`
> #    안에 그 이름의 선언이 다시 생기지 않는 것**이다 — 두 번째 철자가 이 추출이 없앤 결함이다.
> #    🔴 아래 두 줄은 히트 0건이어야 한다(import 문은 `^(export )?function`에 안 걸린다):
> git grep -nE "^(export )?function (canonicalKeyValue|composeMapId|decomposeMapKey|canonicalMapKey|getMapIdFromMeta|canonIntString)\b" -- client2/src/map_editor.js
> git grep -nE "^(export )?function (normalizeBands|normalizeKnobs|normalizeLegendItem|cloneLegend|registryFingerprint|buildLegendRegistryUpdates|parseLegendRegistryRows|getMissingDescValues|formatLegendMetaText|legendRowSignature|legendRowPayload|canonRegistryRow|serializeStack|serializeMaterials|knobsToObject|serializeKnobs|parseJsonCol|buildSplitKey)\b" -- client2/src/map_editor.js
> #    ⚠️ **반대 방향의 함정이 더 크다** — 계약 하니스들이 두 모듈의 **module-private** 이름을
> #       텍스트로 슬라이스한다(`contracts/map_seam/vectors.json`이 `canonIntString`·
> #       `CANON_INT_RE`·`CANON_FLOAT_RE`를, `contracts/legend_map_scope/client_harness.mjs`가
> #       `LEGEND_PAYLOAD_COLUMNS`·`FP_UNIT`·`FP_ROW`·`SPLIT_KEY_SEP`를 이름으로 든다).
> #       **아무도 import하지 않는 private 심볼의 개명이 계약 하니스를 깨뜨린다** — "안 쓰이니
> #       바꿔도 된다"가 이 두 파일에서는 거짓이다.
> # ⑭ [2026-08-04 신설] **서버 모듈은 웹 엔트리포인트를 import하지 않는다.**
> #    `main`은 워커 프로세스에서 **안정된 이름이 아니다** — 스케줄러/워처가 수집기·테이블
> #    스크립트 디렉터리를 `sys.path[0]`에 꽂으므로 그 안의 `main.py`가 먼저 바인딩된다.
> #    실측된 대가: `AttributeError: module 'main' has no attribute
> #    'get_column_filter_condition'`(같은 작업이 CLI에서는 성공했다). 처방은
> #    `server/column_filter.py`([§1.8](#18-servercolumn_filterpy--필터-dsl-번역기가-엔트리포인트-밖으로-나간-자리-신설)).
> #    🔴 히트 0건이어야 한다. 정본 검사는 `server/tests/test_entrypoint_import_isolation.py`
> #       (`os.walk(server/)` 전 트리)이고 아래는 그 값싼 미리보기다.
> #    ⚠️ **범위에서 `server/tests`를 빼는 것이 계약이다** — 테스트는 웹앱을 켜는 것이 일이라
> #       `from main import app`이 정당하다. 빼지 않으면 이 검사가 영원히 빨개진다(실측 10+건).
> git grep -nE "^\s*(import main\b|from main import)" -- server ':!server/tests' ':!server/scratch'
> # ⑭-b 그리고 `get_column_filter_condition`은 **`main.py`에 선언이 없어야** 한다
> #     (재export 한 줄만 남는다 — `from column_filter import …`).
> git grep -nE "^def get_column_filter_condition" -- server/main.py
> # ⑮ [2026-08-04 신설] `validDieRefTableTouched` — **`client2/src` 선언 0건**이어야 한다.
> #    🔴 이 이름은 **직전 지도가 살아 있는 모듈 상태로 등재하던 것**이다(구 §7 "~2005").
> #    지금 남은 것은 map_editor.js **2420의 묘비 주석 1건**뿐이다. **2건 이상이면 부활한 것.**
> git grep -n "validDieRefTableTouched" -- client2/src
> # ⑯ [2026-08-06 신설, S2.1] 프레임이 모듈 상태이던 시절의 이름 2종 —
> #    **`client2/src` 선언 0건**이어야 한다.
> #    🔴 둘 다 **직전 지도가 살아 있는 앵커로 등재하던 것**이다(구 §7 "1432"·"1538").
> #       프레임이 인자가 되면서 지웠다. 남은 히트는 전부 **주석**이다
> #       (map_editor.js 1443·1673·1874·1902·2044·2098·2486, map2/declaration.js 76·78).
> #    ⚠️ 범위가 `client2/src`인 것이 ⑦·⑩과 같은 이유다 — `client2/tests/`의 하니스 여럿이
> #       이 이름들을 **묘비 주석으로** 계속 언급하고(그게 옳다), 범위를 넓히면 영원히 빨개진다.
> git grep -nE "^\s*(let|const|var|function)\s+(physFrameOverride|withPhysFrame)" -- client2/src
> # ⑯-b 그리고 푸시 컬럼 계약 3종이 `map_editor.js` 안에서 **다시 선언되지 않아야** 한다.
> #     이사이지 묘비가 아니다 — 이름은 `client2/src/push_columns.js`에 살아 있다(⑬과 같은 계급).
> #     🔴 종전 지도는 이 셋을 `map_editor.js`의 5760·5782·5801에 등재하고 있었다.
> git grep -nE "^(export )?(const|function) (PUSH_SYSTEM_COLUMNS|getUnprotectedPushColumns|logShapedPushDecision)" -- client2/src/map_editor.js
> # ⑰ [2026-08-06 신설] `refuse_notation_derived_columns` — **선언 0건**이어야 한다.
> #    🔴 이 이름은 **직전 지도가 §2의 표에 살아 있는 앵커(2235)와 살아 있는 호출부(2286)로
> #       등재하던 것**이고, **바로 아래 행이 "이 함수는 삭제됐다"고 적는 동안** 그랬다.
> #       남은 것은 `server/database/crud.py` **2374–2384**(@`e943e46` 재확인 — 이 범위는 밀리지 않았다)의 묘비 주석뿐이다.
> git grep -nE "^\s*def refuse_notation_derived_columns" -- server
> # ⑱ [2026-08-11 신설] 정렬 후보의 **거울 축**이 쓰던 이름 — **선언 0건**이어야 한다.
> #    🔴 넷 다 **직전 지도가 살아 있는 심볼로 등재하던 것**이다(§5 표의 `load_alignment_sides`,
> #       §7-A `candidates.js` 행의 `SIDES`·`SIDE_HEADERS`). 두 번째 후보 축이 `side`에서
> #       **시작 모서리**로 바뀌면서(`c4eaffa`→`db1ee42`) 통째로 사라졌다.
> #    ⚠️ **`declaration.js`의 `SIDES`는 이 검사 대상이 아니다** — 그것은 저장된 *메타*의
> #       어휘(`front`/`back`)이고 여전히 실재한다. 사라진 것은 **후보 축**으로서의 `side`다.
> #       그래서 범위가 `map2/candidates.js` 하나다.
> #    🔴 `client2/tests`를 범위에 넣지 마라 — 하니스 넷이 이 이름들을 아직 import하고 있고
> #       그 넷은 `check_harnesses.mjs`의 `KNOWN_RED`에 **총괄 수용(2026-08-09)** 으로 등재돼 있다.
> git grep -nE "^(SIDES_KEY|def load_alignment_sides)" -- server/map_alignment.py
> git grep -nE "^export const (SIDES|SIDE_HEADERS) " -- client2/src/map2/candidates.js
> ```
>
> **측정 기준 (라인 앵커가 가리키는 상태)**: **전 절이 `41b17ee`의 커밋된 blob 실측**이다(`git show 41b17ee:<path>` 기준, 2026-08-04 여덟 번째 패스). HEAD(`35b03cc`)와의 차이는 `docs/process/PROJECT_STATUS.md`·`client2/scripts/check_harnesses.mjs`뿐이라 **소스 blob은 하나도 다르지 않다** — 아래 게이트 핀만 HEAD 기준이다.
>
> 🆕⑤ ⚠️ **[2026-08-13] 이 핀 목록은 `41b17ee` 기준이고 이 패스는 갱신하지 않았다 — 세 항목만 고치면 목록이 자기 기준을 배신하기 때문이다.** 참고용으로 `831ab68`(HEAD)의 실측 blob 셋만 여기 남긴다: `parsers/directory_watcher.py` = **`d469d15`**(핀의 `0609cfa` 아님) · `database/models.py` = **`9587c13`**(핀의 `cd78e43` 아님) · `db_safety.py` = **`38e6675`**(핀의 `8ee2eb8` 아님). **핀 목록 전체 재생성은 이 패스의 지시 범위 밖이다.**
>
> 검증용 blob 해시(`git rev-parse 41b17ee:<path>` 선두 7자). 🔴 = 이번 범위에서 바뀐 핀:
> **서버** — 🔴 **`main.py` = `454b649`** · 🆕 **`column_filter.py` = `7a9cbca`** · 🔴 **`database/crud.py` = `d637d91`** · `database/models.py` = `cd78e43` · `map_overlay.py` = `01bbe65` · 🔴 **`transfer_plan.py` = `faed7e0`** · 🔴 **`bonding_plan.py` = `9e7b326`** · 🔴 **`product_tables.py` = `f132d6c`** · `effort_metric.py` = `9e3ef4e` · `ontology_config.py` = `851d0f8` · `graph_sync_worker.py` = `79f0a51` · `value_suggest.py` = `a1d7a5e` · `map_preset_routing.py` = `ce5fee0` · 🔴 **`parsers/directory_watcher.py` = `0609cfa`** · `parsers/advanced_ingester.py` = `fa37bba` · 🆕🔴 **`parsers/html_topology_parser.py` = `61dc149`**
> **서버(인리치먼트 F9)** — `enrichment_config.py` = `ff98b8b` · `enrichment_candidates.py` = `956fb02` · 🆕🔴 **`enrichment_analysis.py` = `82df7ea`** · 🔴 **`config_resolve_report.py` = `8d811f5`**
> **서버(내부 이벤트 경계 · 런처)** — `admin_auth.py` = `16e565b` · 🔴 **`chain_ingestion_worker.py` = `175b37f`** · 🔴 **`internal_event_client.py` = `d898971`** · 🔴 **`run_watcher.py` = `4d722d1`** · `run_auto_update.py` = `2fdd00a` · 🔴 **`event_constants.py` = `2fc2679`** · 🆕🔴 **`process_supervisor.py` = `52ab177`** · 🆕🔴 **`run_decoupled_app.py` = `cdf5121`**
> **서버(DB 안전 · 가상 조인)** — `database/database.py` = `cb0fe7d` · `db_safety.py` = `8ee2eb8` · `virtual_join_config.py` = `b58efc8` · 🔴 **`virtual_join_executor.py` = `1c8c8cf`**
> **서버(소급·재생·표기·그래프)** — `retroactive.py` = `d8db501` · `enrichment_backfill.py` = `a2039a3` · `chain_replay.py` = `c824ab7` · `graph_orphans.py` = `30517d6` · 🆕 **`notation_norm.py` = `358ae68`** · 🆕 **`graph_stale_edges.py` = `cdf0108`**
> **클라** — 🔴 **`map_editor.js` = `72f2fb7`** · `map_key.js` = `cb75f24` · `split_registry_row.js` = `b88ecb5` · `retroactive_view.js` = `4a3dcef` · `admin.js` = `966f323` · `config_resolve_view.js` = `b250aa1` · `main.js` = `2be049d` · `clipboard.js` = `6d412d0` · `transfer_plan.js` = `2fd3e54` · `doe_bands.js` = `1ad3f38` · `grid.js` = `6080824` · 🔴 **`api.js` = `5f063f7`** · 🔴 **`state.js` = `1ed9b59`** · `ui.js` = `c9df7f9` · `value_suggest.js` = `6ea9c56` · `client/desktop_wrapper.py` = `f00264a`
> **계약** — `band_arithmetic/vectors.json` = `861a031` · `doe_band_rules/vectors.json` = `47b213c` · 🔴 **`map_seam/vectors.json` = `e9895cf`** · 🔴 **`map_seam/client_harness.mjs` = `3564a2d`** · `config_resolve_report/vectors.json` = `35ba478` · 🔴 **`blank_predicate/vectors.json` = `ab8bc58`**
> **게이트(HEAD `35b03cc` 기준)** — 🔴 **`client2/scripts/check_harnesses.mjs` = `ddaa4a0`**
> (`git hash-object <path>`로 대조). **이 값이 다르면 해당 절의 라인 앵커는 재측정 대상**이고, 함수명으로 Grep해서 쓰라.
>
> 💡 **핀이 50 → 56으로 늘었다.** 새로 들어온 여섯은 전부 **핀 밖에서 밀리고 있던 것 또는 이번 신설**이다: `column_filter.py`·`notation_norm.py`·`graph_stale_edges.py`(신설) · `process_supervisor.py`·`run_decoupled_app.py`·`html_topology_parser.py`·`enrichment_analysis.py`·`product_tables.py`(핀 밖에서 변경됨).
>
> ✅ **이 패스(`ed9cfdb`→`35b03cc`, 37커밋)에서 핀이 일한 기록.** 구 50핀 중 불일치가 **18개**다. 바이트 동일이라 **끝 쪽 표본만 뽑고 넘긴 것**: `map_overlay.py`(1,448줄 무변동, 4패스 연속) · `value_suggest.py`(끝 표본 `classify_seek_plan` **1055** · `index_targets` **1093**) · `enrichment_candidates.py`(끝 표본 `AutoConfirmCollector` **487** · `log_stats` **475**) · `retroactive.py`(`publish` **611** · `OPERATIONS` **425**) · `models.py` · `effort_metric.py` · `ontology_config.py` · `graph_sync_worker.py` · `map_preset_routing.py` · `advanced_ingester.py` · `enrichment_config.py` · `admin_auth.py` · `run_auto_update.py` · `database.py` · `db_safety.py` · `virtual_join_config.py` · `enrichment_backfill.py` · `chain_replay.py` · `graph_orphans.py` · 클라 10종 · 계약 3종.
>
> 🔴 **핀은 변경을 잡지 신설을 잡지 못한다 — 네 패스 연속 참이다.** 이번 신설 5개(소스; 테스트 포함 20)는 전부 `git diff --name-status`의 `A` 라인으로만 보였다. `D` 라인도 같다(이번엔 소스 삭제 0건).
>
> ⚠️ 🔴 **핀이 초록이라고 앵커가 옳은 것은 아니다 — 그리고 이 문서는 그 값을 이미 지불했다.** 직전 패스에서 `crud.py`의 핀은 초록이었고 그래서 그 절이 스팟 체크로 넘어갔는데, **파일 뒤쪽 절반이 통째로 112줄 어긋나 있었다.** 스팟 표본이 하필 맞아 있던 앞쪽 절반에 떨어졌다. **그래서 이번 패스의 규율은 「끝·경계·최근 변경 구역에서 표본을 뽑는다」다** — 위 목록의 무변동 파일들에 적은 표본 라인이 전부 파일 뒷부분인 이유가 그것이다. **핀은 「파일이 안 바뀌었다」만 증명하고 「지도가 이 파일을 옳게 적었다」는 증명하지 않는다.**
>
> 🔴 **이번 패스의 같은 계급 사례 — 핀 밖도 초록불도 아닌 세 번째 실패: 「직전 패스가 재측정했다고 적은 수」.** §0 ⑪-b가 `server` 히트를 **1건**이라고 못박아 두었는데 `1dc761b`에서도 **2건**이었다. 항목(`coordinate_transformer.py:50`)은 실재했고 **개수만 틀렸다** — 그래서 확인하는 사람은 그 줄을 열어 보고 통과시킨다. §0 ⑫는 더 나쁘다: "선언 히트 0건"이라고 적었는데 그 정규식은 `1dc761b`에서 `utils.js:8`을 이미 잡고 있었다. **검사를 적어 두는 것과 돌리는 것은 다르고, 이 문서는 그 차이를 표지로 구분하지 못한다.**
>
> 🔻 **드리프트 분포(구 앵커 → 실측, `ed9cfdb`→`41b17ee`)**:
> - 🔴 **`map_editor.js`** 9,163 → **9,683**(+520). **여전히 계단표를 적지 않는다.** 단계 함수 17종이 파일 **뒤쪽**에 앉았으므로 드리프트가 뒤로 갈수록 커진다: **~300줄 이전 0** · 중반 **+50~+164** · 후반 **+250~+495**. 구 지도에서 가장 크게 틀려 있던 것은 `populateValidDieRefList`(**+495**)·`enterValidDieAuthoring`(**+493**)·오버레이 후반부(**+493**)였고, 지적받은 `resolveValidDie`는 **+299**였다(제보된 "+176"보다 크다). [§7](#7-client2src--웹-클라이언트)은 **심볼 표**가 정본이고 라인은 보조다.
> - 🔴 **`main.py`** 5,595 → **5,488**(−107). **이 파일이 줄어든 첫 범위다.** 구 **1175–1319**(146줄)는 계단이 아니라 **삭제**다(`get_column_filter_condition`이 `column_filter.py`로 이사) — **그 구간의 옛 앵커는 밀린 것이 아니라 없다.** 나머지: 1–1175 **0** · 1320–4053 **−141** · 4054–4372 **−132** · 4373– **−107**.
> - 🔴 **`server/database/crud.py`** 2,612 → **3,209**(+597). 신설 블록 **둘 다 파일 앞쪽**이라 뒤로 갈수록 크게 밀렸다: **+292**(버전 게이트 99–390) → **+500**(텍스트 렌더러 829–1036) → **+547** → **+584** → **+597**. `set_cell_manual_priority_batch` 2,165 → **2,762**.
> - **`transfer_plan.py`** 3,450 → **3,826**(+376) · **`bonding_plan.py`** 562 → **932**(+370). 다시 한 라운드의 두 절반이다 — 이번엔 **역할 바인딩의 유도·거절·선택 역할 효과**([§5](#5-소형-서버-모듈)).
> - **`process_supervisor.py`** 718 → **1,024**(+306). 포트 충돌 판정 + 자식 로그 펌프. `read_status` 711 → **1017**.
> - **`internal_event_client.py`** 235 → **359**(+124) · **`run_watcher.py`** 341 → **367**(+26) · **`chain_ingestion_worker.py`** 1,065 → **1,086**(+21). **셋이 한 복구 경로의 세 조각**이다(미배달 통지 마커).
>
> 💡 **핀 목록이 6→13→19→24→28→34→35로 늘었다(2026-07-30).** 직전 패스가 "해시 6개가 전부 초록이어도 지도의 절반은 재측정 대상일 수 있다"고 적어 놓고도 목록을 그대로 뒀는데, 바로 그 다음 패스에서 드리프트의 **전부**가 핀 밖에서 나왔다(`main.py` +225 · `crud.py` +127 · `models.py` +67 · `map_overlay.py` +413). 핀은 **드리프트가 실제로 일어나는 파일**에 박아야 검사다. 2026-07-30 패스에서 13핀 중 불일치는 8개였고 — `models.py`·`transfer_plan.py`·`effort_metric.py`·`band_arithmetic/vectors.json`은 초록이라 그 절들을 스팟 체크로 끝냈다 — **핀 밖에서 새 파일 8개가 들어왔다**(아래 [§5-A](#5-a-2026-07-30-신설-서버-모듈-8종)). 그래서 이번엔 `grid.js`·`desktop_wrapper.py`·신설 2종까지 핀에 넣었다.
>
> 💡 **이 해시가 실제로 일한 기록**: 한 패스에서는 `vectors.json`이 도중에 바뀌어(`17698dd`→`8696ea7`) 막 적은 서술이 즉시 낡은 것을 잡았고, 한 패스(2026-07-28 오전)에서는 다섯 해시 전부가 불일치로 나와 **다섯 파일 전체 재측정**의 근거가 됐다 — zone 모델 착지(`b35bc9f`)로 `transfer_plan.py`가 1,815→3,019줄, `map_editor.js`가 4,873→5,466줄이 됐고, 같은 날 후속 패스(`2baf9ff` U9 marker + `6db517d` H1/H2)에서는 계약 파일 둘만 일치하고 소스 셋이 전부 불일치라 재측정 범위를 정확히 그 셋(+`doe_bands.js`)으로 좁혀 줬다. 검사는 통과할 때도 실패할 때도 일을 한다. 같은 날 U6 패스(`95bf072`)에서는 소스 셋(`map_editor.js` +81 · `transfer_plan.js` +27 · `doe_bands.js`)이 불일치, 계약 둘이 일치로 나왔다 — 단 `doe_bands.js`의 불일치는 **주석 한 줄 리포인트**였다: 해시는 "변했다"만 말하고 "앵커가 밀렸다"는 재측정이 판정한다. 같은 날 6-fix/backfill/flatten 패스(`0052d76`+`1fefd12`+`0c6ac1a`)에서는 소스 셋(`transfer_plan.py` +56 · `map_editor.js` +79 · `transfer_plan.js` +2)이 불일치, 계약 둘과 `doe_bands.js`가 일치 — 재측정 범위가 정확히 그 셋 + 해시 밖 3파일(`directory_watcher.py` +322 · `bonding_plan.py` +57 · `enrichment_config.py` +11)로 좁혀졌다. gate4/overlay-binding 패스(`17f65bd`+`deed6d2`)에서는 `transfer_plan.py`(+34)·`map_editor.js`(+165)만 불일치 — 클라 zone 코어(`transfer_plan.js`·`doe_bands.js`)와 계약 둘은 무접촉이 해시로 증명됐고, 재측정은 그 둘 + 해시 밖 4파일(`main.py` +37 · `crud.py` +73 · `map_overlay.py` +51 · `schemas.py` +5)이었다. **7b/7c/M3 패스(2026-07-29, `55ddffd`→`b697d34`)에서는 여섯 중 `transfer_plan.py` 하나만 불일치**(+257) — 클라 5파일이 통째로 무접촉임을 해시가 증명해 §7 재측정이 스팟 체크로 끝났다. 그런데 **드리프트의 대부분은 해시 밖에 있었다**: `map_overlay.py` +111 · `directory_watcher.py` +30 · `chain_ingestion_worker.py` +22 · `bonding_plan.py` +15, 그리고 **이번 범위가 건드리지도 않은** `models.py`(+21 — 선언 529줄 대비 실제 550, `DatabaseOutbox` 30 vs **51**)와 `process_supervisor.py`(선언 줄수는 718로 맞는데 앵커는 709줄 시절 값이라 172줄 이후 전부 **+9**). 해시 6개가 전부 초록이어도 지도의 절반은 재측정 대상일 수 있다. **V1/M4①/7c-클라 패스(`b697d34`→`b8307c2`)가 그 경고를 그대로 실증했다**: 구 핀 6개 중 클라 둘(`map_editor.js` +610 · `transfer_plan.js` +289)과 `server/transfer_plan.py`(+36)만 불일치였는데, **정작 제일 크게 밀린 넷은 전부 핀 밖**이었다 — `main.py` +225 · `map_overlay.py` +413 · `crud.py` +127 · `models.py` +67. 그래서 이번 패스에서 핀 목록을 13개로 늘렸다(위).
>
> ⚠️ **해시가 보증하지 않는 것**: 이 여섯 파일 밖의 앵커는 해시로 지켜지지 않으므로 **패스마다 다시 재야 한다.** 실사례(2026-07-27 패스): 그 범위가 **건드리지도 않은** 파일들이 이미 밀려 있었다 — `directory_watcher.py` 최대 +53줄, `process_supervisor.py`는 선언 431줄 대비 실제 **709줄**. 실사례(2026-07-28 패스): `main.py`는 이번 범위(`b35bc9f`·`280ebf0`)에 없지만 앞선 `ec75d4c`·`269b39e`로 **최대 +72줄** 밀려 있었다. 실사례(gate4 패스): `crud.py`가 **직전 pin(`0c6ac1a`) 시점에 이미 +93 밀려 있었다**(선언 1,952줄 vs 실측 2,045줄 — `apply_row_update_internal` 551 vs 644). pin 해시가 맞아도 해시 목록 **밖** 파일의 앵커는 아무것도 보증받지 않는다. 커밋 diff만 따라가는 갱신은 이런 것을 영원히 못 본다.
>
> ⚠️ **왜 "커밋된 blob"이라고 못박는가 — 2026-07-27 패스에서 실제로 일어난 일**: 착수 시점에 워킹트리가 클린이었으나, 그 절을 쓰는 동안 다른 에이전트들이 `server/main.py`·`server/database/crud.py`·`server/database/models.py`·`server/schemas.py`를 **동시 편집**해 트리가 갈라졌다. 앵커를 워킹트리에서 쟀다면 **아무도 리뷰하지 않은 중간 상태**가 지도에 박혔을 것이다. 그래서 이 지도의 모든 앵커는 `git show <Last-verified HEAD>:<path>` 기준이다 — 라인이 아니라 **함수명으로 Grep하라**는 규율이 특히 동시 편집이 잦은 파일들에 적용된다.
>
> 🔴 **그리고 2026-07-29 오후 패스에서 그 규율이 실제로 값을 갈랐다 — 이번엔 반대 방향으로.** 이 패스에 보고된 드리프트 중 **다섯 건이 워킹트리에서만 참**이었다: `crud.load_table_config` 226 · `update_table_config` 245 · `main.startup_event` 226 · `config_watcher` engine 분기 ~151 · `map_overlay.apply_valid_die_ref` 1016. **커밋된 HEAD `b8307c2`에서는 각각 172 · 181 · 189 · 42 · (부재)**다. 워킹트리 값을 받아 적었다면 이 지도는 **커밋된 트리를 여는 모든 에이전트에게 틀린 좌표**를 줬을 것이고, 그 틀림은 "방금 실측했다"는 표지를 달고 있었을 것이다. **보고된 실측이라도 리비전을 확인하라** — 측정 자체는 정직해도 측정 대상이 다르면 값은 거짓이다.
>
> ✅ **후속 (2026-07-30, `ae2811c`) — 그 다섯 건의 결말이 규율을 양방향으로 입증했다.** 라운드가 착지한 뒤 커밋 기준으로 다시 재니 **다섯 중 어느 것도 워킹트리 값과 같지 않았다**: `load_table_config` **274** · `update_table_config` **293**(BOM 배치가 위에 `TableConfigError`·`_parse_position`·`_decode_config_text`·`load_table_config_or_raise` 넷을 끼워 넣어 워킹트리 시절 226/245보다 더 밀렸다) · `startup_event` **227**(워킹트리 226에 +1) · `config_watcher`는 **파일이 66→180줄로 재작성**돼 "engine 분기" 한 줄로 지목할 대상이 아니게 됐다. 유일하게 값이 그대로인 것은 `map_overlay.apply_valid_die_ref` **1016**이다. **즉 워킹트리 값을 베꼈다면 5개 중 4개가 틀렸을 것이다** — 그리고 우연히 맞은 1개도 맞을 이유가 없었다. 미착지 라운드의 좌표는 "곧 맞을 값"이 아니라 **아직 값이 아니다.**
>
> 🚫 **이 목록이 받지 않는 것 — 「한 번도 착지하지 않은 이름」.** 묘비의 계약은 *"이 이름은 **있었고** 지금은 없다"*이고, 그래서 각 행이 **대체물**을 지목할 수 있다. 어떤 커밋에도 존재한 적 없는 이름은 은퇴시킬 앵커도 대체물도 없으므로 여기 넣으면 **일어나지 않은 삭제를 단언**하게 된다 — 목록의 신뢰를 깨는 방향이 정확히 그것이다.
>
> 그런 이름이 실제로 하나 있다: **`isAuxHeadWord`**. `git log --all -S'isAuxHeadWord'`가 돌려주는 커밋은 **전부 문서**이고(2026-07-30 기준 5건 — 이번 주 문서 churn으로 늘었다), 그 뿌리는 **`docs/history/` 항목** 하나이며, 내용은 "존재한 적 없는 심볼의 제거"를 기술한다. 히스토리는 추가 전용(append-only)이라 그 항목은 정정되지 않는다. **올바른 처리는 세 가지다**: ① 이 지도에 행을 만들지 않는다 ② 소스에 있는 실제 이름은 **`auxHeadWords()`**(`map_editor.js` **~6211** — 2026-07-31 재측정, 구 표기 ~5846은 두 세대 낡아 있었다. [§7](#7-client2src--웹-클라이언트) F1ⓑ 블록)이고 그것이 찾던 것이다 ③ **판정에 쓰는 수는 전체 건수가 아니라 경로 한정 소스 건수다** — `isAuxHeadWord`는 **0건**이고(그래서 툼스톤이 아니다), 이번에 삭제된 채택 함수 8개는 각각 **2건**(도입 + 삭제)이라 툼스톤이다. 전체 건수는 문서가 늘면 같이 늘어 판정에 못 쓴다 — **소스 히트가 0인 이름은 삭제된 것이 아니라 착지하지 않은 것**일 수 있고, 그 둘은 `git log --all -S<name> -- server client client2/src`(경로 한정)로 갈린다. 경로를 한정하지 않은 `-S` 검색은 문서 히트를 코드 계보로 읽게 만든다.
>
> ⚠️ **`plan_store.doe`는 예외적으로 소스에 남아 있다** — 폐기된 `map_doe`의 `__comment` 안(`product_tables.py:105` 및 그것이 생성한 `table_config.json.sample`)에서 "historical description" 구간의 일부다. **낡은 주석이 운영자를 능동적으로 오도하는** 바로 그 사례이며, `install_product_tables.py --sync-comments`가 그래서 생겼다(`tests/test_install_product_tables.py:231`이 이 시나리오를 이름으로 기술한다).

| 삭제된 이름 | 있던 곳 | 대체물 (현행) |
|---|---|---|
| `putUpdates` · `scheduleServerSave` · `saveDoeToServer` · `loadDoeFromServer` · **`adoptServerDoe`** · `doeRowKey` · `doeSourceRowKey` · `S.doe` · `S.doeServerLoaded` · **`S.serverRows`** · **`S.deleteUnsent`** · `S.loadSeq` · `DRAFT_PREFIX` · `cannotExpress` · `planTablesSupported` · `blankBand` · `summaryStatusOf` | `client2/src/transfer_plan.js` (구 DOE 저장 기계장치) | **`map_editor.js`의 Split Registry 블록** — 권한은 **`legendReplaceScope`**, 동시성은 **`legendConflict`**(M2.6 추가: upsert로 **강등하지 않고 거부**한다), 쓰기는 `saveLegendToServer`(호출자는 `pushMapData` 하나), 초안은 `saveDoeDraft`/`applyDoeDraftRecord`. 패널 측 관문은 `commitRow` → `controller.updateLegendRow`. (`DRAFT_VERSION`은 `map_editor.js`에 **되살아났다** — 초안 레코드 버전 상수, 현재 `3`) |
| **`scheduleLegendServerSave`** (legend 디바운스 자동 저장) | `client2/src/map_editor.js` | **자동 저장 자체가 삭제**됐다(사용자 지시 2026-07-28) — 서버 쓰기는 **⚡ Push(`pushMapData` → `saveLegendToServer`) 하나**뿐이고, 편집 경로는 전부 `scheduleCellDraft`(로컬 초안)로만 흐른다. 묘비 주석이 **~4274**에 있다(2026-07-31 재측정) |
| `fetchLegendFromServer` · `loadLegend` · `loadLegendFromStorage` · `maybeOfferLegendMigration` | 〃 (구 legend 서버 로드) | `fetchRegistryRows`/`readRegistryScope`/`applyRegistryRowsToLegend` — **map_key 스코프 읽기만** 남았다(`REGISTRY_SCOPES=['map']`). 테이블 전체 어휘 시드는 `269b39e` 결함(남의 맵 DOE 전파)의 원인이라 삭제, 계약은 `contracts/legend_map_scope/`.<br>⚠️ **`client2/tests/split_registry_harness.mjs`(272줄)는 이 4개 + `DEFAULT_LEGEND`를 여전히 이름으로 추출한다**(~49·57·59–62) — 즉 **실행하면 추출 단계에서 죽는 사문 하니스**다. `contracts/` 밑이 아니라 `client2/tests/` 밑이라 §0 검사 ②-b의 범위 밖이었고, 그래서 초록불 옆에서 살아남았다. (현행 대체물은 `contracts/legend_map_scope/client_harness.mjs` — 같은 경로를 끝까지 돌린다.) 이 파일의 처분은 **client 도메인 소관**이라 여기서 고치지 않는다 |
| **`BUILTIN_STAGES`**(transfer_plan.js) · **`DEFAULT_LEGEND`**(map_editor.js) · **`OVERLAY_VAL_CANDIDATES`**(map_editor.js) · 값 컬럼 후보 인라인 배열 `valMatches`(fillColumnDropdowns) · E1/E2 고정 색 · 팔레트 12색 사본 3곳 | 클라 하드코딩 선언 사본들 | **[U6 `95bf072` config-over-hardcode] 선언의 단일 원천은 서버다.** stage 목록은 GET `/api/transfer-plan/stages`뿐(`stageTargetTables()` export — 폴백 사본 없음, 실패는 정직한 강등: `S.stages=[]` + 재시도), 빈 맵 시드·값별 색은 paint-rules 응답의 **`default_legend`**(`overlayContract`→`defaultLegendRows`/`declaredLegendRow`, 미선언 arm은 `EMPTY_DOE_SEED` 1행), 값 컬럼 자동감지는 **`value_column_candidates`**(서버 해석 완료 목록 — 클라 사본 0), 팔레트는 `LEGEND_PALETTE` 하나 + `autoAddLegendValue` 단일 경로. 서버 `map_overlay.VAL_CANDIDATES`는 **`DEFAULT_VAL_CANDIDATES`로 강등**(documented default — 소비는 `resolve_value_column_candidates(cfg)` 경유만) |
| `bandTo` · `bandLayers` · `bandTotal` · `bandShare` · `commitBands` · `commitKnobs` · `bandsOf` · `knobsOf` · `validateBands` · `sortBands` · `nextBandSeq` · `cloneBand` | `client2/src/transfer_plan.js` (구 band 편집기 산술) | **zone 모델로 이전** — 산술은 `doe_bands.js`의 `zoneLayers`/`zoneDemand`/`materialRollupRows`, 쓰기 관문은 `commitRow`. `bandToState`·`prevTo`만 레거시 `bands` 읽기용으로 잔존(export ~256). **`contracts/band_arithmetic/client_harness.mjs`가 앞 4개의 부재를 능동 단언**한다(되살아나면 exit 2) |
| `pruneScoped` · `S.serverKeys` | 〃 (구 클라측 차집합-후-삭제) | `replace_map`(`crud.apply_batch_updates`) — `3ebd38e`에서 제거 |
| **`deriveMapBinding`** · `fetchTableSchemaCached` · `OVERLAY_SYSTEM_COLS` · 대소문자 무시 x/y 매칭기(fillColumnDropdowns 내) | `client2/src/map_editor.js` (구 클라 로컬 좌표 바인딩 유도) | **[F1/F3 `17f65bd`] 바인딩은 서버가 해석해 서빙한다** — paint-rules 응답의 `binding`(`map_overlay.resolve_binding_info`), 클라는 `servedBindingCache`(**~128**)+`fetchServedBinding`(**~148**)로 소비만. 같은 질문의 2·3번째 매칭기가 서버와 어긋나는 것이 결함이었다. `fallback_guess`는 데이터 경로가 거부하는 추측이라 클라가 **경고**한다. ⚠️ **~124·~8351 두 주석**에 묘비 문맥으로 이름이 남아 있다(살아있는 앵커 아님 — `git grep -c "deriveMapBinding" -- client2/src` = **2**, 2026-07-31 `1dc761b` 재측정. 종전 두 번째 앵커 `~8020`은 +331 밀렸다) |
| `_doe_get` · `_num` · `_band_range` | `server/transfer_plan.py` | `_reg_get`(중첩) · (수량이 유도라 저장 수치 파싱 자체가 없다) · `_band_to`/`_prev_to` |
| `WARN_LAYER_COVERAGE_GAP` / `layer_coverage_gap` | 〃 (경고 타입) | **개명이 아니라 삭제.** 커버리지가 정의상 연속이라 공백이 표현 불가. 구조 결함은 `layer_range_invalid`(+`reason`) |
| `plan_store.doe` · `plan_store.doe_source` | `transfer_plan_config.json` 역할키 | **`plan_store.registry`** + **`plan_store.material_identity`** |
| `map_doe` · `map_doe_source` (테이블) | `product_tables.PRODUCT_TABLES` | **`map_split_registry`** — 선언은 DEPRECATED 표기로 남아 있으나(운영자 수동 이관용) **어떤 코드도 읽고 쓰지 않는다.** 새 소비자 금지, 물리 DROP은 승인 대기 |
| ~~`server/run_api.py`~~ | (문서에만 존재했다) | 그런 파일은 **없다** — `run_decoupled_app.py`의 `main()`이 uvicorn을 직접 띄운다([§6](#6-기타-서버-모듈-한줄-요약)) |
| **`_escape_like_term(term)`** | `server/main.py` (LIKE 메타문자 이스케이프) | **[F3 `4e8e867`] LIKE 자체가 사라져서 삭제**됐다 — 유일한 호출자였던 `/graph/nodes/search`의 `identity_key.ilike(term + '%')`가 **`value_suggest.prefix_conditions(col, value_suggest.db_fold(db, term), is_pg)`**(범위 비교)로 교체됐다. 범위 비교에서 `%`·`_`는 그냥 문자라 이스케이프할 것이 없다. 소스에 묘비 주석이 있다(`main.py` **~2430–2432**). ⚠️ **이 지도의 §1.5가 `~2262` 앵커로 이 함수를 살아있는 헬퍼로 등재하고 있었다**(2026-07-30 정정) — §0이 경고하고 다른 절이 앵커로 쓰는 바로 그 실패다 |
| **`_chip_trace_declared_pairs() -> set`** | 〃 (chip-trace 선언 교차검사) | **`_chip_trace_declaration()`**(**~2803** — 2026-07-31 재측정) — 반환이 `set`에서 **`(declared_pairs, report)` 튜플**로 바뀌었다. 추가된 절반이 요점이다: `rejections=[]`를 걷어 `degraded`를 판정하고 그것이 `not_declared` → **`mapping_unavailable`** 강등의 근거다(매핑 파일이 저장 중이라 안 읽히는 순간에 "이 엣지는 선언되지 않았다"고 200으로 단언하던 결함). `8670e3b`에 있었고 `530fdfd`에서 교체. ⚠️ **`main.py` **~2383**의 상수 블록 주석이 아직 죽은 이름을 지목한다** — 서버 도메인 소관이라 여기서 고치지 않았다 |
| **`request_flatten` · `_flatten_worker` · `_flatten_directory` · `_build_collision_name` · `_resolve_flatten_dest` · `_sanitize_flatten_component` · `flatten_nested_dirs_enabled` · `FLATTEN_SEP="~"` · `self._flattening_dirs`** | `server/parsers/directory_watcher.py` (구 [Flatten] 평탄화 일습, `0c6ac1a`) | **[`600b49d`] 평탄화 자체가 폐기됐다 — 파일은 이제 제자리에서 인제션된다.** 대체물은 같은 자리·같은 형태의 8종: **`request_tree_ingest(dir_path)`** · `_tree_ingest_worker` · **`_ingest_directory_tree(abs_dir)`** · **`relative_source_path(abs_path, root)`**(static) · **`_unique_dest(dest_dir, filename, limit=1000)`**(static) · `is_managed_source` · `_refuse_move_of_foreign_source` · **`nested_dirs_enabled()`** · `self._ingesting_dirs`. 🆕⑤ **[2026-08-13 `831ab68` 실측] 이 행의 라인 번호 9개를 걷어냈다** — 전부 `600b49d` 시절 값이라 그 뒤 세 라운드에서 밀렸다(예: `_ingest_directory_tree`는 ~809가 아니라 933). **이름은 전부 살아 있음이 확인됐고**, 위치는 `git grep -n`으로 확정하라. 승격을 없앤 이유가 개명의 이유다: 폴더명을 분리자로 파일명에 **인코딩했다가 정규식으로 다시 뽑는** 왕복이었고, 파서는 애초에 전체 경로를 받는다(`advanced_ingester.process_file(file_path, rel_path=…)`). `/`는 폴더명 안에 못 들어가므로 경로 자체가 이미 모호하지 않다 — 그래서 발명한 분리자(`~`)와 `__force__` 토큰 중화 루프가 **문제째로** 사라졌다.<br>⚠️ **config 키 `flatten_nested_dirs`는 개명하지 않았다**(운영자의 기존 off 스위치를 조용히 무력화하지 않으려고 — 소스 주석 ~239–240). 즉 **함수명과 키명이 의도적으로 어긋나 있고**, 키로 grep하면 살아 있는 것이 맞다. ⚠️ **`main.py` ~3169 주석이 `_resolve_flatten_dest`를 아직 지목한다**(§0 검사 ⑥) — 서버 도메인 소관 |
| 🆕 **`storedCoordRepositionPlan` · `applyStoredCoordReposition` · `repositionRefusalReason` · `adoptionCoordinateCost` · `adoptedFrameOf` · `dbCoordsByPhysKey` · `adoptFrameSpec` · `announceFrameAdoption`** (8종) | `client2/src/map_editor.js` (구 [F6] 프레임 채택 + 저장 좌표 재배치 일습, `ae2811c`→`7873070`+`d4b9660`) | **[F8 `61440e6`+`94b9baa`] 대체물은 함수가 아니라 부재다 — 유효 다이 지정은 이제 아무것도 채택하지 않는다.** 사용자 지시 2026-07-30 「그리드 크기가 달라도 좌표는 db값 그대로 보존하고 화면 표기 밀리게 그냥 보여주기」. 근거는 데이터 모델이다: **셀에 저장된 좌표라는 것이 없다**(`gridData`는 `물리 키 → 값`뿐이고 DB x/y는 Push 시점에 현재 프레임이 유도한다). 그래서 "좌표 보존"의 유일한 구현은 **칸을 그대로 두는 것**이고, 치수를 채택하면 같은 칸이 다른 좌표를 낳는다 — 재배치는 그것을 막으려던 기계장치였고 새 프레임이 만들지 못하는 좌표 앞에서 셀을 **버리거나 번호를 다시 매기는** 수밖에 없었다(둘 다 금지). 지금 남은 것은 `resolveValidDie` 안의 **토스트 1회**(치수가 다르면 "마스크가 밀려 보입니다 — 격자·셀·좌표는 하나도 바뀌지 않았습니다")뿐이다([§7 F8](#7-client2src--웹-클라이언트)).<br>🔬 **이 행은 [`isAuxHeadWord`](#0-묘비-목록--소스에-존재하지-않는-이름) 사례의 정확한 반대다 — 그 대비가 이 목록의 계약이 무엇인지 말해 준다.** 경로 한정 판별식을 8개 전건에 돌린 결과 **각각 소스 커밋 2건**(도입 + 삭제)이다: `git log --all --oneline -S"function <name>" -- client2/src` → 2. `isAuxHeadWord`는 같은 명령이 **0**을 준다(문서 히트만 있다). 즉 **소스 히트 0 + 소스 계보 ≥1 = 묘비**이고 **소스 히트 0 + 소스 계보 0 = 착지한 적 없음**이며, 후자는 이 표에 넣으면 안 된다. 검사는 [§0 ⑦](#0-묘비-목록--소스에-존재하지-않는-이름) |
| 🆕 **`_get_http_session()`** · 모듈 로컬 `_http_local` | `server/chain_ingestion_worker.py` (구 [Warmup #3] 스레드별 세션 저장소, `a82aa47:133`) | **[`23a346d`] `internal_event_client.internal_event_session()`으로 이관**([§1.7](#17-serverinternal_event_clientpy--내부-http-호출의-단일-소유자-23a346d-신설)). keep-alive·스레드 로컬 성질은 그대로이고 **`trust_env = False`가 추가**됐다 — 이 파일이 자기 세션을 만들던 것이 2026-07-30 프로덕션 403의 경위다. 개명이 아니라 **소유권 이전**이고, 그래서 세 발신자(`chain_ingestion_worker`·`graph_sync_worker`·`run_watcher`) 전부가 같은 객체를 쓴다. 소스에 묘비 주석이 있다(`chain_ingestion_worker.py` ~131–136 — [§0 ⑧](#0-묘비-목록--소스에-존재하지-않는-이름)의 실측 히트 1건이 그것이다) |
| 🆕 **`getVisualCoords` · `getCellFromVisualCoords` · `getPhysicalCoords` · `getCellFromPhysicalCoords`** · 지역 식별자 **`xv`/`yv`**(17개) | `client2/src/map_editor.js` (좌표 변환 코어 4종) | **[`35e84c3`] 삭제가 아니라 개명이다 — 46개 호출부가 한 커밋에서 바뀌었다.** 대체물은 **`getDbCoords` · `getCanvasCellFromDb` · `getDieIndex` · `getCanvasCellFromDieIndex`**, 식별자는 **`dbX`/`dbY`**([§7 좌표 코어](#7-client2src--웹-클라이언트)).<br>🔴 **개명의 이유가 곧 옛 이름이 만든 결함이다.** ① `getVisualCoords`는 "화면 표기"처럼 읽히는데 실제로 만드는 것은 **DB에 저장되는 x/y**다 — 그래서 "화면만 밀린다"는 판단이 반복해 나왔고 실제로 밀린 것은 저장값이었다. ② `getPhysicalCoords`는 **밀리미터를 준다고 읽히는데 셀 인덱스를 준다** — 그 오독이 "피치 × 칸수"로 없는 결함을 세운 경위다.<br>⚠️ **그래서 `mm`은 비워 둔다** — [§0 ⑫](#0-묘비-목록--소스에-존재하지-않는-이름).<br>🔬 판별식(경로 한정)은 넷 다 **2**를 준다(`git log --all --oneline -S"function <old>" -- client2/src` = 도입 + 개명), 새 이름 넷은 **1**이다. 즉 묘비 조건을 만족한다.<br>🔴 **`server/utils/coordinate_transformer.py:50`의 docstring이 아직 `getPhysicalCoords`를 짝으로 지목한다** — 서버 도메인 소관이라 여기서 고치지 않았다. §0 ⑪-b의 **경계 없는** 스캔이 이것을 잡는다 |
| 🆕 **`server/scripts/reapply_chain.py`** (파일 전체, 85줄) | `server/scripts/` — 유일한 **소스 파일 삭제**다 (`8f8be4b`, 2026-07-31) | **[R1] `chain_replay.replay_rule`/`replay_all`, 운영자 표면은 `server/scripts/chain_replay_cli.py replay <rule> [--apply]`.** 🔴 **삭제 사유가 [§2 `resolve_priority_map`](#2-serverdatabasecrudpy--레이어링-코어)의 그 계약이다** — 이 스크립트는 `source_name="reapply_chain"`으로 썼는데 그 이름은 `SOURCE_PRIORITY`에 **없어서 99(최하위)로 떨어진다**. 즉 옳은 값을 써도 아무에게나 지고, 회수(R2 `withdraw_source`)하려면 그 이름을 알고 있어야 했다. R1은 라이브 워커와 **같은 provenance**(`chain_ingestion`, 우선순위 4)로 쓴다. 살아 있던 참조는 `backfill_enrichment.py`의 `sys.path` 부트스트랩 주석 하나였고 같은 커밋에서 재지목됐다. 지금은 `retroactive.OPERATIONS['chain_replay']['cli']`가 후계 CLI를 이름으로 등재한다([§5-D](#5-d-2026-08-04-신설-서버-모듈)) |
| **`is_port_open(host, port)`** | `client/desktop_wrapper.py` (`__main__` 안 중첩 함수, `b8307c2:246`) | **[`e9b3a36`] 탐지(probe)를 선언(declaration)으로 교체**하며 삭제. 5173 포트를 열어 보고 dev/통합 모드를 고르려던 함수인데 `b8307c2`에서 **이미 사문**이었다 — 호출자가 없고 바로 다음 줄이 `url`을 하드코딩하면서 "Vite dev server not detected."를 무조건 출력했다. 그 역할은 이제 `resolve_server_target` → `base_url` 우선순위 체인이 맡는다([§6](#6-기타-서버-모듈-한줄-요약)). **HEAD에서 소켓을 열어 대상을 시험하는 코드는 없다** |

> ⚠️ **이 문서 밖의 같은 패턴**: `MAP_EDITOR_SPEC §6.3`이 위 1행의 삭제된 API를 **load-bearing 안전 계약으로** 기술하고 있다(기원은 `cdcddee`). 그 파일은 **doc-keeper 소관**이라 여기서 고치지 않았다.

---

## 목차

| 파일 | 라인수 | 섹션 |
|---|---|---|
| **묘비 목록 (소스에 없는 이름)** | — | [§0](#0-묘비-목록--소스에-존재하지-않는-이름) |
| `server/main.py` | 🆕🆕🆕🆕 **6,322** @`c4a3159`(HEAD)(6,243 → `2630790` 6,286 → **+36**: 🔴 **top-level `def`/`class`/라우트 데코레이터 집합은 여전히 무변동**이고 바뀐 것은 핸들러 본문/시그니처다: 🆕🆕🆕 `get_recent_audit_logs`가 `response: Response` 인자를 얻어 `X-Audit-Truncated`/`X-Audit-Next-Cursor` 헤더를 발행 · 🆕🆕🆕 신설 `_history_page(...)` 공유 헬퍼(행/셀 이력 라우트 둘이 이제 이 하나로 수렴 — 종전엔 `get_cell_history`가 **파일 하단에 도달 불가 중복 정의**로도 있었는데 이번 재작성으로 그 사문이 사라졌다) · `get_map_alignment_view`의 `alignment_view_service` 위임 · 🆕🆕🆕🆕 **[`fde424c`] `get_recent_audit_logs`의 `response_model`이 `list[schemas.AuditLogGroupResponse]`에서 `schemas.AuditLogGroupPage`로**(봉투 전환, 아래 §1.3) · 🆕🆕🆕🆕 **[`347de78`] `fetch_and_merge_metadata`/`get_cell_sources`/`query_cells_sources`의 `cell_sources` SELECT 3곳**(아래 §2 `fetch_and_merge_metadata`, §1.3 route table)) | [§1](#1-servermainpy--api--ws-허브) |
| 🆕 **`server/column_filter.py`** (필터 DSL 번역기 — `main.py`에서 이사) | **181** (신설) | [§1.8](#18-servercolumn_filterpy--필터-dsl-번역기가-엔트리포인트-밖으로-나간-자리-신설) |
| **`server/admin_auth.py`** (어드민 토큰 게이트) | **463** (무변동 — blob 해시 초록) | [§1.6](#16-serveradmin_authpy--어드민내부-토큰-게이트-90e284f-신설) |
| **`server/internal_event_client.py`** (내부 HTTP 호출의 단일 소유자) | **359** (235 → **+124**: 미배달 통지 마커 + `/health` 응답 *모양* 판별자) | [§1.7](#17-serverinternal_event_clientpy--내부-http-호출의-단일-소유자-23a346d-신설) |
| `server/database/crud.py` | 🆕🆕🆕🆕 **4,172** @`347de78`(3,980 → **+192**: `compute_priority_value`의 3단 tie-break 신설 + `resolution_ingested_at` 신설 + `_warn_undeclared_column_once` 재작성 + `undeclared_column_drops()` 신설 — 아래 §2) · 그전 3,980 @`7097a67`(top-level 심볼 집합 `34d2518` 대비 **무변동**) · 종전 등재 3,526 (@`e943e46` 재확인 — `d3ed167` 3,209 → **+317**: 🆕 **[P6] 복합 키 프리페치** · 🆕 **[`87a944e`] `replace_map` 차집합 경로**). ⚠️ **`server/crud.py`는 없다** | [§2](#2-serverdatabasecrudpy--레이어링-코어) |
| `server/parsers/directory_watcher.py` | 🆕⑤ **2,681** @`831ab68`(`ba664c5`+`831ab68`로 2,293에서 **+388**, 신설 top-level 심볼 4종·메서드 5종) · 구 등재 2,293 @`7097a67` | [§3](#3-serverparsersdirectory_watcherpy--파일-인제션) |
| **`server/parsers/advanced_ingester.py`** (선언 검증 + 경로 메타 추출) | **508** (무변동 — blob 해시 초록) | [§3](#3-serverparsersdirectory_watcherpy--파일-인제션) |
| 🆕 **`server/parsers/html_topology_parser.py`** (HTML 표 → 그래프/행렬) | **768** (638 → **+130**: 격자 원점 이중 유도 + 구조적 헤더 술어. **전부 `parse_matrix_to_records` 본체 안**) | [§3-ter](#-3-ter-serverparsershtml_topology_parserpy-768줄-ed9cfdb-638에서-130--html-표--그래프행렬) |
| `server/chain_ingestion_worker.py` | 🆕🆕🆕🆕 **1,328** @`347de78`(종전 등재 1,086 → `34d2518` 1,198 → `7097a67` 1,294 → **+34**: 신설 `_undeclared_drop_note()`/`_DROP_NOTE_TOP_N=5` — `crud.undeclared_column_drops()`의 다이제스트를 하트비트 `note=`로 얹는다) | [§4](#4-serverchain_ingestion_workerpy--체인-워커) |
| 소형 서버 모듈 (models/std_parser/**enrichment_config**/enrichment_mapper/ingestion_activity/ingestion_checkpoint/**bonding_plan**/map_overlay/**transfer_plan**/map_meta_registrar/effort_metric) + 그래프 트랙(graph_sync_worker/graph_materializer/ontology_config) + **운영 6종**(paths/**process_supervisor**/health/heartbeat/**product_tables**/config_backup) | 🔴 **13,499은 낡았다** (2026-08-04 20파일 전건 재측정 합). 🆕⑤ **[2026-08-13] 이 합은 재계산하지 않았다 — 20파일 전건을 다시 재야 유효한 수인데 이 패스는 그중 `ingestion_checkpoint.py` 하나만 열었다**(258 → **587**, 즉 이 합은 최소 **+329** 밀렸고 그 밖의 파일이 얼마나 움직였는지는 **모른다**). 합계를 「+329 했다」고 적으면 안 잰 19파일을 잰 척하게 된다 | [§5](#5-소형-서버-모듈) |
| **[신설] 2026-07-30 서버 모듈 8종** (value_suggest/map_preset_routing/graph_orphans/chain_replay/**enrichment_analysis**/enrichment_candidates/keyset_scan/utils.time_format) | **4,094** (2026-08-04 8파일 전건 재합산, 4,078에서 **+16**). 바뀐 것은 **`enrichment_analysis.py`(532 → 548)** 하나뿐이고 나머지 일곱은 blob 동일 | [§5-A](#5-a-2026-07-30-신설-서버-모듈-8종) |
| **`server/config_resolve_report.py`** (「내 config가 먹었는가」의 답) | 🆕🆕🆕 **833** @`68db020`(668에서 **+165**: 네 번째 도메인 `binding`) | [§5-B](#5-b-serverconfig_resolve_reportpy--내-config가-먹었는가의-답-f3fd785-신설) |
| **`server/db_safety.py`**(#16a 테스트 프로세스 DB 가드 🆕⑤ **+ 운영자 패스 읽기 전용 가드**) + **`server/virtual_join_config.py`**(가상 조인 **선언** 로더/검증) | 🆕⑤ **453** @`831ab68`(215에서 **+238**, `1260c9b`) + **512** (`virtual_join_config.py`는 이번 패스가 재측정하지 않았다 — ⚠️ 이 값은 아래 §5-C 제목의 **687**과도 어긋나 있고, 그 불일치는 이번 구간이 만든 것이 아니다) | [§5-C](#5-c-2026-07-31-신설-서버-모듈-2종) |
| **[신설] 2026-08-04 서버 모듈** — **`virtual_join_executor.py`**(가상 조인 **실행**, 535 → **554**) · `retroactive.py` · `enrichment_backfill.py` · `trace_fixture/` 패키지 6파일 | **554** + **697** + **411** + **1,356** | [§5-D](#5-d-2026-08-04-신설-서버-모듈) |
| 🆕 **[신설] 2026-08-04(2차)** — **`server/notation_norm.py`**(표기 정규화 파생 컬럼) · **`server/graph_stale_edges.py`**(낡은 엣지 스윕) + CLI 2종 | **542** + **549** (+ `graph_stale_edge_sweep.py` 193 — 🪦 `rederive_notation_norm.py`는 `8d306a5`에서 삭제됐다) | [§5-E](#5-e-2026-08-042차-신설-서버-모듈-2종--표기-정규화--낡은-엣지-스윕) |
| 🆕 **[등재] 2026-08-07 정렬 채점 계열** — `serpentine_index`/`serpentine_rank` · `_walk_by_index` · `direction_judge`/`direction_violations` · **`index_group_count`** · **`bin_fingerprint_shift`** · 앵커/잔차 배치 · 순번 축 진단 | (`server/map_alignment.py` 안 — 파일 🆕🆕🆕 **6,468** @`68db020`) | [§5-F](#5-f--정렬-채점-계열-index-scoring-family--servermap_alignmentpy-2026-08-07-등재) |
| 🆕🆕 **[등재] DT·core 프레임 유도 체인** — `dt_map_derivation.py`(**`parse_frame`의 정의**) · `dt_frame_transform.py` · `alignment_view_service.py` · 체인 맵퍼 5종(`mappers/*.py.sample`) · 씨앗/프로브 스크립트 3종 | **849** + **96** + **85** (+ `.sample` 791 · 스크립트 817) | [§5-G](#5-g--dtcore-프레임-유도-체인-2026-08-11-신설-등재) |
| 🆕⑥ **[등재] 정본 원장(canonical ledger)** — `server/ledger/` **11파일**(쓰기 측) + `server/ledger_trace.py`·`ledger_trace_router.py`(읽기 측) + `server/migrations/add_ledger_events.py` + 클라 `client2/ledger.html` · `client2/src/ledger_trace.js` · `ledger_trace_core.js` · `ledger_trace_view.js` + 하니스 | 서버 **2,819** + **1,179** + **80** + **96** / 클라 **393** + **149** + **286** + **173** + 하니스 **674** | [§5-H](#5-h-정본-원장-canonical-ledger) |
| 기타 서버 모듈 (한줄 요약) + 설치·개발환경 스크립트 + **교차 구현 계약 `contracts/` (6계약)** + **빌드 게이트 3종** + **런처 `run_decoupled_app.py`(132 → 228)** | — | [§6](#6-기타-서버-모듈-한줄-요약) |
| 🆕 **`server/map_alignment.py`**(프레임 정렬 채점자) + **`server/frame_confirmation.py`**(확정 기록자) + `migrations/add_frame_confirmation.py` | 🆕🆕🆕 **6,468** + **798** (@`68db020` 실측 — 등재 당시 3,272 + 688. 🔴 **`frame_confirmation`이 처음으로 줄었다** — private `_basis_cells_for`가 `map_alignment.basis_cells_for`로 이사·공개됐다) | [§5](#-servermap_alignmentpy--프레임-정렬의-채점자) · [§5-F](#5-f--정렬-채점-계열-index-scoring-family--servermap_alignmentpy-2026-08-07-등재) |
| 🆕 **Map Editor 2** — `client2/src/map_editor2.js` + `client2/src/map2/` **18**모듈 (구 에디터를 **대체하지 않고 옆에 선다**) | **408** + **8,378** (신설) | [§7-A](#7-a--map-editor-2--map_editor2html--client2srcmap2-2026-08-0506-신설) |
| 🆕 `client2/src/push_columns.js`(푸시 컬럼 계약 — `map_editor.js`에서 이사) + `client2/src/enrichment_queue.js`(큐 술어) | **77** + **94** (신설) | [§7](#7-client2src--웹-클라이언트) |
| `client2/src/*` | **44,400** (js **39,363** + css 4,983 — `d3ed167` 31,301에서 🔴 **+13,099**. 대부분은 🆕 **Map Editor 2**(`map2/` **8,378** + `map_editor2.js` 408 + `map_editor2.css`)와 `map_editor.js` **+165**) | [§7](#7-client2src--웹-클라이언트) |
| 주요 호출 흐름 | — | [§8](#8-주요-호출-흐름-요약) |

> **경로의 단일 원천 (2026-07-27):** `server/config/**`·`server/ingestion_workspace/**`·프로세스 로그는 이제 전부 **`server/paths.py`**([§5](#5-소형-서버-모듈))를 경유한다. 소스에서 `os.path.dirname(__file__)`로 config/워크스페이스 경로를 조립하는 코드를 보면 **누락**이다. 이 맵의 경로 표기는 모두 `paths.*` 기준.

---

## 1. `server/main.py` — API + WS 허브

> 🟢 **심볼 실측 완료** — 이 절의 심볼은 **`5609ff0`의 커밋된 blob에 존재함이 확인됐고, 그 뒤 HEAD가 움직인 다음 재대조에서도 동일했다**(워킹트리 아님). 🔴 **라인 번호는 싣지 않는다** — 위치는 `git grep -n "<심볼>" -- <경로>`로 확정하라. 숫자가 남아 있는 곳은 **파일 줄 수**이거나, 이름이 없는 덩어리를 가리키며 측정 sha가 함께 적힌 자리뿐이다.

FastAPI 웹서버. 모든 REST/WS의 단일 진입점. 워커·워처와는 outbox + `/internal/events/*`로 통신.

> 🔴 **[2026-08-06] 이 파일은 5,488 → **6,128줄**(+640)이다.** 이 범위의 머리기사는 **프레임 정렬·확정 라우트 4종**(`/api/maps/alignment/{view,confirm,worklist,references}`)과 **큐 술어**(`apply_enrichment_queue_predicate`)의 착지다.
>
> 🔴 **`get_column_filter_condition`은 이제 `main.py`에 선언되지 않는다 — [`server/column_filter.py`](#18-servercolumn_filterpy--필터-dsl-번역기가-엔트리포인트-밖으로-나간-자리-신설)로 이사했다.** `main.py`에 남은 것은 **의도적 재export**(`from column_filter import get_column_filter_condition`)이고 주석이 그렇게 못 박아 두었다. **`main.py`에서 이 이름의 `def`를 찾으면 없다.** 사유는 [§1.8](#18-servercolumn_filterpy--필터-dsl-번역기가-엔트리포인트-밖으로-나간-자리-신설).
>
> 🔢 **라우트 데코레이터 실측(`87a944e`) — 파일 최상단 `@app.<verb>(` 기준 **82개**.** 구 표기 **78**은 낡았다. ⚠️ **철자가 답을 바꾼다**: 들여쓰기된 것까지 세면 **91**이다 — `if os.path.exists(client2_dist_path):` 블록 안의 정적 라우트 9개가 최상단 기준에서 빠지기 때문이다. 이 문서의 규율(「파일 최상단 기준」)로는 **82**이고, **어느 쪽 수를 인용하든 철자를 함께 적지 않으면 다음 사람이 다른 수를 재고 지도가 틀렸다고 판단한다.**
>
> 🆕 **신설 라우트 1종**:
>
> | 라우트 | 핸들러 | 게이트 |
> |---|---|---|
> | GET `/admin/transfer-plan/dry-run` | `get_transfer_plan_dry_run()` → `transfer_plan.dry_run(config)` | `require_admin_token` (**strict 아님**) |
>
> 🔴 **「내가 쓴 이 선언이 받아들여지는가, 아니면 왜 거절되는가」 ― 쓰기 없는 계기.** `GET /api/transfer-plan/stages`는 역할마다 `connected`/`missing` **한 단어**를 내는데 그 단어로는 config를 고칠 수 없다. 이 경로는 역할마다 ① 이름 붙은 거절 사유(`bonding_plan.explain_binding_refusal` — 문장 생성기를 두 번 쓰지 않는다) ② 해석된 **실제 컬럼명** ③ 그 컬럼이 **선언에서 왔는지 유도에서 왔는지** ④ 틀린 선언이 유도를 지게 하고 있다면 **지우면 무엇이 유도되는지**를 함께 낸다. **파라미터가 없고 행을 조회하지 않는다** — 그래서 strict가 아니다(선례: `GET /admin/enrichment/auto-confirm/dry-run`).
>
> 🔴 **앵커 재측정 (2026-08-04, `41b17ee` blob `77db6b1` 계열) — 계단 3구간, 재작성 구역 없음.**
>
>
> ⚠️ **계단표는 "줄이 밀렸다"만 말하고 "그 자리에 다른 것이 들어앉았다"는 말하지 못한다.** 이 문서가 반복해 실패한 자리가 정확히 그것이다 — **함수명으로 Grep해 확인하고 나서 읽어라.**
>

### 1.1 기동·미들웨어·공용 헬퍼

| 시그니처 | 역할 |
|---|---|
| `script_dir = …` / `logger.info(f"[paths] {paths.describe()}")` | 부팅 첫 줄에 데이터 루트를 찍는다 — 로그만 보고 이 프로세스가 격리 환경인지 라이브인지 판별 가능. **[`2728bd9`] 바로 아래에서 `[db] url source={env\|config file\|default} target=…`를 `paths.mask_db_password`로 **마스킹해** 찍는다** — 어느 DB URL 원천이 이겼는지의 부팅 증거([§5 paths.py](#5-소형-서버-모듈)) |
| **`from admin_auth import require_admin_token, require_admin_token_strict`** | **[`90e284f` 신설]** `/admin/*`·`/internal/*` 게이트 의존성 import([§1.6](#16-serveradmin_authpy--어드민내부-토큰-게이트-90e284f-신설)). 🆕 그 위가 **[`e1ba99e` #16a] `import db_safety`** — "테스트 프로세스는 진짜 DB를 만지지 못한다"를 **결정으로** 들여오는 자리([§5-C](#5-c-2026-07-31-신설-서버-모듈-2종)) |
| `db_context_middleware(request, call_next)` | 요청별 DB 세션 수명 관리 미들웨어. **읽는 헤더는 `X-User`/`X-Transaction-ID`/`X-Source`뿐** — 토큰 헤더명(`X-Admin-Token`)이 여기와 겹치지 않는 것이 감사 행 유출 차단의 근거([§1.6](#16-serveradmin_authpy--어드민내부-토큰-게이트-90e284f-신설)). ⚠️ **구 지도의 `~65`는 두 세대 낡은 값이었다**(`9ac2083`에서 이미 103) |
| **`bootstrap_database_schema(bind=None)`** | ✅ **[2026-07-30 착지] `create_all`이 함수 안으로 들어왔다.** 종전엔 `models.Base.metadata.create_all(bind=engine)`가 **모듈 import 시점**에 맨몸으로 실행됐다. 이제 이 함수 안에 있고 호출은 `startup_event` 안 한 곳이다.<br>🆕 **[`e1ba99e` #16a] 시그니처가 `bind=None`을 받고, 본체 첫 문장이 `db_safety.require_test_database(str(target.url), context="boot-time DDL (Base.metadata.create_all)", …)`로 바뀌었다.** 🔴 **이 거부는 순수 결정이다** — 커넥션을 열기 **전에** 판정하므로 테스트 프로세스는 DB에 **접촉조차 하지 않고** 돌아선다. pytest 밖에서는 즉시 반환하고 함수는 종전과 글자 그대로 같이 동작한다. **`bind` 인자가 존재하는 이유는 회귀 테스트다** — 프로세스 자신의 엔진을 프로덕션으로 돌리지 않고도 거부를 증명할 수 있어야 한다.<br>**`create_all`은 여전히 의도적으로 무가드**다(소스 주석 **~85·~100**) — DB가 불통이면 웹서버는 **부팅에 실패해야** 하고, 워커 4개는 자기 루프에서 예외를 삼켜 살아남는다([§5 `process_supervisor`](#5-소형-서버-모듈)의 "고립된 자식 1개" 시나리오) |
| `startup_event()` | 기동: `bootstrap_database_schema()`, 워처 스레드, 콜백 배선, 캐시 워밍. **[`90e284f`] `admin_auth.startup_banner()`를 1회만 로깅**(`_admin_auth_banner_logged` 가드 — reload마다 재발화하면 배너가 소음이 된다) |
| ├ `trigger_ws_refresh(table_name, count, created_logs, total_log_count)` | (내부·임베디드 모드 전용) 인제션 완료 → WS 갱신 브로드캐스트 콜백 (⚠️ C-5 절단 미적용 레거시 경로 — 드릴 관찰, 저순위) |
| ├ `trigger_ws_file_processed(table_name, filename, status, error_msg)` | (내부) 파일 처리 상태 → WS 통지 콜백 |
| └ `trigger_ingestion_state(state)` | [P1] 비-DECOUPLED 시 HTTP 없이 `ingestion_activity_registry`에 직접 반영, file-processed 시 제거 |
| `shutdown_event()` | 종료 정리 |
| `class ConnectionManager` — `connect/disconnect/broadcast` | WS 연결 풀 + 전체 브로드캐스트 |
| `invalidate_table_cache(table_name)` | 테이블 count 캐시 무효화 (`TABLE_COUNT_CACHE` |
| `inject_system_columns(row)` | 응답 행에 시스템 컬럼 주입 |
| `fetch_and_merge_metadata(db, table_name, rows, user_cols, include_sources=True) -> list` | 행들에 CellSource/Overwrite 메타 병합 → 셀 객체 `{value,is_overwrite,priority_source}` 생성 (조회 응답의 핵심). 🆕🆕🆕🆕 **[`347de78`] `cell_sources` SELECT가 `.ingested_at`도 뽑고 `.order_by(source_name.asc())`가 붙었다** — `col_srcs`(`{source: value}`, 클라 계약이라 타임스탬프를 못 나른다) 옆에 `ingested_map`을 따로 조립해 `crud.compute_priority_value(col_srcs, manual_pin, table_name, ingested_at_by_source=ingested_map.get(key))`로 넘긴다. **안 넘기면 이 조회 경로가 알파벳순으로, 쓰기 경로가 최신순으로 갈려** 화면의 `priority_source` 배지가 실제로 저장된 값과 다른 레이어를 가리킬 수 있었다(응답 셀 모양 자체는 무변경) |
| `get_deleted_row_business_key(db, table_name, row_id)` / `get_deleted_rows_business_keys_bulk(...) -> dict` | 삭제 행의 비즈니스 키 역추적(감사 표시용) |
| `check_rows_exist(db, row_keys) -> set` | (table,row_id) 존재 일괄 확인 |
| `from ingestion_activity import registry as ingestion_activity_registry` | [P1] 진행 스냅샷 레지스트리 싱글턴 import([§5](#5-소형-서버-모듈)) |
| 🔴 **`from column_filter import get_column_filter_condition`** | **[신설] 이 파일에 함수 선언이 없다 — *의도적 재export*다.** 번역기는 [`server/column_filter.py`](#18-servercolumn_filterpy--필터-dsl-번역기가-엔트리포인트-밖으로-나간-자리-신설)로 이사했고 `main.get_column_filter_condition`은 계속 해석된다. 사유 주석이 바로 위에 있다. **`main.py`에서 `def get_column_filter_condition`을 찾으면 없다** |
| **`class VirtualColumnBinder`** | **[`cd3e0f4`] 가상 조인 컬럼을 쿼리에 물리는 자리.** `__init__`에서 `virtual_join_executor.exposed_columns(db, table_name)`을 한 번 물어 들고 있다가, 노출 컬럼이 필터·검색에 등장하면 `resolved_expression`으로 `outerjoin`+`COALESCE` 식을 만들어 준다. 🔴 **`/schema`가 알리는 목록과 검색이 받아들이는 목록이 같은 함수에서 나온다** — 갈리면 화면에 보이는 컬럼으로 검색이 안 되는데 아무 에러도 안 난다 |
| 🆕 **`apply_enrichment_queue_predicate(query, table_model, table_name, rule_name, scope)`** | **[신설 — 종전 지도에 없던 심볼]** 「아직 일이 남은 행」을 **이름으로** 묻는 서버측 술어. 클라 짝은 [`enrichment_queue.js`](#-enrichment_queuejs-94줄-신설--어느-행이-아직-일이-남았나의-유일한-철자)의 `queueQuery(rule, scope)`이고 스코프 어휘를 공유한다(`queue`/`keyed`/`blank_key`/`resolved`). ⚠️ **이 함수가 `apply_column_filters`와 `apply_search_filter` 사이에 끼어 들어왔다** — 그래서 뒤쪽 함수만 앵커가 더 밀렸다 |
| `apply_column_filters(query, table_model, table_name, filters, binder)` / `apply_search_filter(query, table_model, table_name, q, cols, binder)` | 위 바인더의 두 소비자. `get_table_data`·`export_table_csv`가 **같은 이 둘**을 부른다(종전엔 각자 필터를 조립했다) |
| `reload_local_process_cache()` | 웹서버 config 핫리로드 — `models.refresh_dynamic_models(engine)` 위임(싱글턴·ORM·신규 테이블 물리 CREATE, 이슈 #7) + `crud._ontology_cache` 무효화. 🆕 **`notation_norm.reset_cache()`가 같은 모양·같은 사유로 더해졌다** — 파생 스펙은 워커에 TTL이 있지만 어드민에서 편집된 선언은 **여기서 다음 쓰기부터** 먹어야 한다 |
| `load_maps_config()` / `save_maps_config(data)` | 맵 프리셋 JSON 파일 IO (`MAPS_CONFIG_PATH = paths.config_path("maps.json")` |
| 🆕 **CORS `expose_headers`** | **[`cde3398`] `WWW-Authenticate`가 목록에 추가됐다**(현재 4종: `Content-Disposition` · `X-Estimated-Content-Length` · `X-Total-Rows` · **`WWW-Authenticate`**). 🔴 **없으면 교차 출처에서 게이트를 식별할 수 없다** — 클라의 `isGateRejection`([§7 `admin.js`](#7-client2src--웹-클라이언트))은 401/403에 더해 이 헤더가 `X-Admin-Token`을 지목하는지 보는데, 노출하지 않으면 브라우저가 그 헤더를 지운다. 결과는 **vite dev(:5173)에서 진짜 게이트 거부가 「앞단이 답했다」로 확신 있게 오분류**되는 것이다(2026-07-30 loopback 프록시 인시던트가 그 모양이었다). 같은 출처(:8080/:8081 직접 서빙)에서는 원래 읽혔다. **값은 원하는 헤더의 이름뿐이라 비밀이 없다** |

### 1.1-bis 헬스 블록 (`8117456` 신설 — 파일 상단)

**등록 위치가 계약이다.** FastAPI는 등록 순서로 매칭하므로 이 블록은 파일 맨 아래 SPA catch-all `@app.get("/{file_name:path}")`보다 **위에** 있어야 한다. 이 라우트가 없던 시절 `/health`는 catch-all로 떨어져 **HTML을 200으로** 반환했다 — 외부 모니터가 죽은 서버를 살아 있다고 불렀다. `tests/test_health_endpoint.py`가 양쪽(‌`/health`는 JSON · 엉뚱한 경로는 여전히 HTML)을 단언하므로, 재배치로 라우트가 다시 가려지면 조용히 죽지 않고 테스트가 깨진다.

| 시그니처 | 역할 |
|---|---|
| `_HEALTH_DB_TIMEOUT_SEC=2.0` / `_health_probe_inflight` | DB 프로브 시간 상한 / **동시 프로브 1개 제한** — DB가 멎으면 `wait_for`는 요청만 놓아주고 워커 스레드는 못 놓아준다. 10초 폴링 모니터가 행마다 스레드를 쌓지 않도록 하는 플래그(해제는 대기를 포기한 요청이 아니라 **스레드 자신**이 한다) |
| `_health_probe_db_sync()` / `_health_probe_and_release()` | 동기 DB 프로브(+`health.probe_outbox`) / inflight 해제 래퍼 |
| GET `/health` → `health_check()` | `heartbeat.read_all()` + `process_supervisor.read_status()` + DB/outbox 프로브를 `health.compute_health`에 넘겨 **JSONResponse + 실제 HTTP 상태**(unhealthy면 503)로 반환. ⚠️ **게이트 없음** — 외부 모니터가 토큰 없이 폴링해야 하므로 의도적으로 열려 있다(`/admin/*`이 아니라 `/health`다) |

### 1.1-ter 핵심가치 #1 계측 — 재수정률 + **상호작용 공수 점수** (`2a9f6c4` V1 신설)

**SSOT §1 핵심가치 #1("최소공수교정")의 정본 계기는 `2a9f6c4`에서 교체됐다** — 종전의 재수정률(`ec75d4c`)은 옆에 남아 있고, 새 정본은 **완료된 교정 1건이 사람에게 얼마나 들었는가**(interaction score to completion, 낮을수록 좋다)다. 원시 카운트는 `models.InteractionEffortLog`에 저장하고 **점수는 읽는 시점에 계산**한다(가중치가 바뀌면 과거 tx가 새 가중치로 재해석된다 — [§5 `effort_metric.py`](#5-소형-서버-모듈)).

| 시그니처 | 역할 |
|---|---|
| `_get_recorrection_stat(db)` | 재수정률 통계(`crud.get_recorrection_stats`). **F6**: 실패 사유를 이름으로 말한다(구 문구는 원인을 지어냈다). 캐시 `RECORRECTION_CACHE`/`_TTL` · `RECORRECTION_TIMEOUT_MS` |
| `EFFORT_TIMEOUT_MS = 1500` | 대시보드 1카드가 대시보드 전체를 볼모로 잡지 못하게 하는 집계 시간 상한 (`EFFORT_CACHE`/`_TTL` |
| **`_get_effort_stat(db) -> schemas.EffortStat`** | 지연 import `effort_metric` → `resolve_weights(load_config())` → `crud.get_effort_stats`. 실패는 **카드를 지우지 않고 사유를 싣는다**(타임아웃이면 `idx_effort_window` 인덱스를 이름으로 지목) |
| GET `/api/effort/config` → `get_effort_config()` | 클라가 소비하는 **공개 config**(`effort_metric.get_public_config`) — 가중치와 컨텍스트 보존 전이 허용목록. 클라에 사본을 두지 않기 위한 단일 원천. ⚠️ **게이트 없음**(`/admin`이 아니다) |
| GET `/dashboard/summary` → `get_dashboard_summary` | `recorrection` + **`effort`**를 한 응답에(`schemas.DashboardSummaryResponse.effort`) |
| **`_validate_effort(effort) -> (counts\|None, error\|None)`** | **계측은 계측 대상을 절대 깨뜨리지 않는다.** `GeneralUpdateBatch.effort`는 `Optional[Any]`라 pydantic이 엔드포인트 **전에** 거부하지 못하고, 여기서 파싱한다. 불량 blob은 **버려지고 이름으로 보고**된다(미지 키·`session_id`·정수/음수) — **교정은 그대로 적용된다**. 부재는 합법(“측정 안 됨”) |
| (호출부) `apply_batch_updates_endpoint` 내 | `_validate_effort` 호출 → 최상위 미지 키 합성 → `logger.error("[EffortMetric] …")`. 기록은 **교정 커밋 뒤 별도**로 `crud.record_interaction_effort`, 결과가 응답 `effort_recorded`/`effort_error`. 클라는 `effort_recorded === true`일 때만 카운터를 비운다 |

### 1.2 API 라우트 표 — 데이터 조회/편집

| 메서드 경로 | 핸들러 | 역할 |
|---|---|---|
| GET `/` | `read_root` | index 서빙 |
| GET `/api/download/client` | `download_desktop_client` | 데스크톱 셸 배포 |
| GET `/tables` | `list_tables` | 테이블 목록 |
| GET `/tables/{t}/data` | `get_table_data` | **메인 조회** — 페이지네이션+필터+정렬+메타 병합 |
| GET `/tables/{t}/schema` | `get_table_schema` | 스키마 계약(`table_config.json` 기반). **[gate4 `deed6d2`] `map_push_ok` 필드 동봉** — `config.get("map_push_ok") is True` **엄격 판정**: 문자열 `"true"`·1 등 오타는 잠금 유지, JSON boolean true만 유효. 클라 gate 4의 site 선언 서빙 — [§7 map_editor.js](#7-client2src--웹-클라이언트). 테스트: `tests/test_schema_map_push_ok.py` **3건**(`grep -c "def test_" = 3`) |
| **GET `/tables/{t}/columns/{c}/values`** | **`get_column_unique_values`** | **[F3 `4e8e867` 신설] 입력 제안용 유일값 조회** — `value_suggest.suggest_values` 위임([§5-A](#5-a-2026-07-30-신설-서버-모듈-8종)), `SuggestValidationError` → 그 안의 `status_code`로 변환. 🔴 **등록 위치가 계약이다**: `/tables/{t}/{row_id}`보다 **위**에 있어야 한다 — 아래에 두면 `columns`가 `{row_id}`로 먹혀 단일 행 조회로 떨어진다 |
| GET `/tables/{t}/{row_id}` | `get_row_data` | 단일 행 조회 |
| GET `/tables/{t}/export` | `export_table_csv` | CSV 스트리밍 export |
| POST `/tables/{t}/rows` | `create_row` | 빈 행 N개 생성(+WS 통지) |
| PUT `/tables/{t}/data/updates` | `apply_batch_updates_endpoint` | **메인 편집** — crud.apply_batch_updates 호출 후 병합·브로드캐스트. 배치의 `replace_map:true`는 🆕 **[`87a944e`] 이제 *차집합*이다**(선언된 스코프 − 이번에 청구된 행만 삭제. 종전의 「클린 삭제 후 재기록」은 **정반대 서술이 됐다** — [§2 `apply_batch_updates`](#2-serverdatabasecrudpy--레이어링-코어)) — 맵 Push와 **[M2.6] legend/DOE 저장(`map_split_registry`)**이 이 연산을 쓴다([§7 map_editor.js](#7-client2src--웹-클라이언트)). **[gate4 `deed6d2` 정직한 스코프]** `replace_report` out-param으로 crud가 채운 **실제 purge 필터·삭제 행수**를 받아 응답 `scope`로 되비춘다 — 🔴 **나르는 필드 전건 열거**(종전 지도는 셋만 적었다): **`filters` · `deleted` · `inserted` · 🆕 `adopted` · 🆕 `mode`(`"diff"\|"purge"`) · 🆕 `reason` · 🆕 `delete_ids_omitted`**(비-replace_map은 null) — 스코프 유도 불가는 crud `ValueError` → **400**(종전의 "아무것도 안 지운 200" 폐지). **순수 스코프 wipe(deleted>0, upsert 0)도 count 캐시를 무효화**. **[V1 `2a9f6c4`] 이 핸들러가 공수 계측의 유일한 기록 지점**이다 — `_validate_effort` → 커밋 후 `crud.record_interaction_effort` → 응답 `effort_recorded`/`effort_error`([§1.1-ter](#11-ter-핵심가치-1-계측--재수정률--상호작용-공수-점수-2a9f6c4-v1-신설)). 테스트: `tests/test_replace_map.py`(**7건** — 재측정 `grep -c "def test_" = 7`) |
| DELETE `/tables/{t}/rows/{row_id}` | `delete_row` | 단일 삭제 |
| POST `/tables/{t}/rows/batch_delete` | `delete_rows_batch_endpoint` | 일괄 삭제(+WS) |
| POST `/tables/{t}/row_ids/target` | `get_target_row_ids` | 필터 조건 → row_id 목록(범위 작업용) |
| POST `/tables/{t}/upload` | `upload_file` | 파일 업로드 → 워크스페이스 투입(`paths.workspace_path(table,"raws")`) |

### 1.3 API 라우트 표 — 이력/레이어링(소스·우선순위)

| 메서드 경로 | 핸들러 | 역할 |
|---|---|---|
| GET `/audit_logs/recent` | `get_recent_audit_logs(response: Response, limit_groups=100, db)` | 최근 트랜잭션 그룹 이력. 🆕🆕🆕 **[`2630790`] 응답 헤더 `X-Audit-Truncated`(`"true"`/`"false"`)·`X-Audit-Next-Cursor`(있을 때만)** — 스캔이 상한(`audit_cache.RECENT_DEFAULTS`)에서 잘리면 짧은 목록이 완전한 목록과 구별 안 되던 그 결함. 🆕🆕🆕🆕 **[`fde424c`] 몸통도 봉투로 바뀌었다** — `response_model=schemas.AuditLogGroupPage`, `{groups, truncated, next_cursor, limit_groups, returned}`(리스트 키가 `logs`가 아니라 **`groups`** — 그룹 각각이 자기 `logs`를 갖고 있어 `body.logs[0].logs`가 되는 것을 피했다). 헤더 둘은 **그대로 병존**한다(기존 소비자가 안 깨진다). `client2/src/timeline.js`의 `loadHistory`가 같은 개정에서 `readHistoryPage(await res.json(), 'groups')`로 열도록 함께 배선됐다 — 봉투와 리더가 **한 커밋**에서 같이 움직였다(§`audit_cache.py`) |
| GET `/audit_logs/transaction/{tx_id}` | `get_transaction_logs` | 트랜잭션 상세 로그 |
| GET `/dashboard/summary` | `get_dashboard_summary` | 대시보드 통계 — 재수정률 + **[V1 `2a9f6c4`] 상호작용 공수 점수** 2종 동봉([§1.1-ter](#11-ter-핵심가치-1-계측--재수정률--상호작용-공수-점수-2a9f6c4-v1-신설)) |
| GET `/tables/{t}/rows/{r}/history` | `get_row_history(table_name, row_id, limit=None, cursor=None, db)` | 행 이력 — 페이지 1개(최신순). 🆕🆕🆕 **[`dab9152`] 응답이 봉투 `AuditHistoryPage`(`{logs, truncated, next_cursor, limit, returned}`)로 바뀌었다** — 종전엔 LIMIT 없이 전건을 반환했다(실측 픽스처: 한 행이 300,019건까지 자라 3,462ms/54MB). 두 라우트는 공유 헬퍼 `_history_page(db, table_name, row_id, base_query, limit, cursor)`로 수렴한다 — 🔴 **종전에 이 자리에 있던 「동일 경로·동일 함수명 중복 정의(파일 하단, 도달 불가)」는 이 재작성으로 없어졌다**(실측: HEAD `git grep -c "^def get_cell_history"` = 1). `CursorError`는 400(조용한 재시작 금지) |
| GET `/tables/{t}/rows/{r}/cells/{c}/history` | `get_cell_history(table_name, row_id, col_name, limit=None, cursor=None, db)` | 셀 이력 — 응답 모양은 행 이력과 동일(`_history_page` 공유, `column_name` 필터만 추가) |
| GET `/tables/{t}/{r}/{c}/sources` | `get_cell_sources` | 셀의 레이어(소스) 목록. 🆕🆕🆕🆕 **[`347de78`] `.order_by(models.CellSource.source_name.asc())`가 붙었다** — 이 목록도 `compute_priority_value`를 먹이므로, 순서를 힙 순서에 맡기지 않고 명시한다(아래 `query_cells_sources`·§2 `fetch_and_merge_metadata`와 같은 이유, 같은 커밋) |
| DELETE `/tables/{t}/{r}/{c}/sources/{s}` | `delete_cell_source` | 단일 소스 삭제(+재계산·WS) |
| PUT `/tables/{t}/{r}/{c}/priority` | `set_cell_priority` | 단일 셀 수동 우선순위(Pin) |
| PUT `/tables/{t}/cells/priority/batch` | `set_cell_priority_batch_endpoint` | Pin 일괄 |
| POST `/tables/{t}/cells/sources/delete/batch` | `delete_cell_source_batch_endpoint` | 소스 삭제 일괄 |
| POST `/tables/{t}/cells/sources/query` | `query_cells_sources` | 셀 범위 소스 일괄 조회. 🆕🆕🆕🆕 **[`347de78`] 같은 `.order_by(source_name.asc())`** — 위 `get_cell_sources`와 짝 |

### 1.4 API 라우트 표 — 어드민/운영/그래프/맵·인리치먼트

> 🔒 **[`90e284f`] `/admin/*`개 + `/internal/events/*` 4개 = **23**개 라우트가 데코레이터에 `dependencies=[Depends(require_admin_token)]`을 달고 있다**(2026-07-31 전건 재계수). 그중 **2개만 `..._strict`**(토큰 미설정 시 503). 게이트 자체는 [§1.6](#16-serveradmin_authpy--어드민내부-토큰-게이트-90e284f-신설). **아래 표에서 🔒 = `require_admin_token` · 🔒! = `require_admin_token_strict`.** 새 `/admin` 라우트를 게이트 없이 추가하면 `tests/test_admin_auth.py`가 앱의 라우트 목록을 훑어 실패시킨다(목록을 손으로 관리하지 않는다).

| 메서드 경로 | 핸들러 | 역할 |
|---|---|---|
| POST `/api/graph/sync` | `manual_graph_sync` | 그래프 **백필/복구** 트리거(:8090 프록시 — 주 경로는 materializer). ⚠️ `/admin` 접두어가 아니라 **게이트 대상이 아니다** (`class GraphSyncRequest`. 🔴 **[`23a346d`] `httpx.AsyncClient(trust_env=False)`** — 이것은 워커들의 세션과 **같은 규칙의 네 번째 적용 지점**이고, 종전엔 여기만 빠져 있었다. httpx도 `requests`와 똑같이 기본값이 `HTTP_PROXY`/`ALL_PROXY`를 읽으므로 **한 기계 안의 8080→8090 루프백 홉이 사내 프록시로 나간다**. 증상은 워커가 멀쩡한 채로 "그래프 동기화 서버 에러"이고, 그래서 원인을 그래프 쪽에서 찾게 된다([§1.7](#17-serverinternal_event_clientpy--내부-http-호출의-단일-소유자-23a346d-신설)) |
| 🔒 POST `/admin/outbox/retry-failed` | `retry_failed_outbox_events` | outbox 실패 재시도 |
| 🔒 GET `/admin/outbox/failed` | `get_failed_outbox_events` | outbox 실패 목록(페이징) |
| 🔒 GET `/admin/file-ingestion/logs` · `/failed` | `get_file_ingestion_logs` / `get_failed_file_ingestion_logs` | 파일 인제션 로그/실패 목록 |
| 🔒 GET `/admin/file-ingestion/active` | `get_active_file_ingestions` | **[P1]** 진행 중 인제션 스냅샷(레지스트리 `snapshot()` — 인메모리, TTL 퇴거 포함) — admin File 탭/헬스 스트립 소비 |
| 🔒 POST `/admin/file-ingestion/retry-failed` | `retry_failed_file_ingestion` | 아카이브 파일 재처리(동기 콜백 배선 포함) — 워크스페이스는 `resolve_workspace_root` 역조회(별칭 대응) |
| 🔒 GET `/admin/file-ingestion/workspaces` | `get_ingestion_workspaces` | 워크스페이스 현황 — 표시 table_name에 글로벌 별칭(`find_workspace_alias`) 우선 적용 |
| 🔒 POST `/admin/reload-configs` | `reload_system_configs` | config 핫리로드 — 동기 CREATE(1차 DDL 소유자)가 outbox 발화보다 선행 (+SYSTEM_RELOAD outbox 발화). **[2026-07-30] 그래프 resync도 이제 같은 레버를 쓴다** — `graph_sync_worker.publish_system_reload`([§5](#5-소형-서버-모듈)) |
| 🔒 GET `/admin/chain/rules` · `/admin/mappers/list` | `get_chain_rules` / `get_mappers` | 체인 룰·맵퍼 목록 |
| 🔒 GET `/admin/auto-update/status` | `get_auto_update_status` | 스케줄러 상태 — 항목별 `active` 부가(제어 파일 실시간 계산) |
| 🔒 POST `/admin/auto-update/toggle` | `toggle_auto_update_script` | 수집기 active 토글 — `config/auto_update_control.json` 갱신(핫 반영, 404/400 명시) |
| **🔒! POST `/admin/auto-update/run-now`** | `trigger_auto_update_run_now` | 즉시 실행(**active 무관** — 수동 실행은 명시적 의도). **strict인 이유: 스케줄러에게 임의 파이썬 파일을 실행시킨다**(아래 `scripts/code`와 짝) |
| 🔒 GET `/admin/scripts/list` · GET `/admin/scripts/code` | `list_admin_scripts` / `get_admin_script_code` | Monaco 에디터용 스크립트 조회 (경로 검사 `_resolve_admin_script_path` — 격리 서버가 라이브 트리에 쓰려 하면 **403**. ⚠️ 이 403은 **게이트가 낸 것이 아니라 핸들러가 낸 것**이라 `WWW-Authenticate`가 없다. 클라가 둘을 구분하는 근거 → [§7 `admin.js` `isGateRejection`](#7-client2src--웹-클라이언트)) |
| **🔒! POST `/admin/scripts/code`** | `save_admin_script_code` | 스크립트 저장. **strict인 이유: `mappers/`·`ingestion_workspace/`에 임의 파이썬 파일을 쓴다** |
| GET/POST/DELETE `/map-presets` (+`/api/` 별칭) | `get_map_presets` / `_save_map_preset_impl` / `_delete_map_preset_impl` + 4개 얇은 래퍼 | 맵 프리셋 CRUD (`class MapPresetItem`, `MAPS_CONFIG_PATH` |
| GET `/api/bonding-plan/core-summary` | `get_bonding_plan_core_summary` | **[본딩 M1]** 코어(lot,slot) 역할별 집계 — `bonding_plan.get_core_summary` 위임([§5](#5-소형-서버-모듈)), `region` 파라미터(rects — 현 클라 미사용), 잘못된 region 400 |
| **GET `/api/maps/preset-routing`** | **`get_map_preset_routing(table, map_key, db)`** | **[F5c `50bddda` 신설] `(table, map_key)` → 이 맵을 **열 때** 쓸 기본 물리 규격**. `map_preset_routing.resolve_preset_routing` 위임([§5-A](#5-a-2026-07-30-신설-서버-모듈-8종)) — `map_overlay_config.json`의 `preset_routing` 선언 + `maps.json`의 프리셋 본문을 함께 먹인다. 🔴 **우선순위가 서버에 박혀 있다: 저장된 메타 > 라우팅 > 패널.** `wafer_map_metadata`가 있으면 `status:"meta_present"`로 **프리셋 없이** 답하므로 라우팅이 등록된 규격을 덮을 **구조적** 방법이 없다. 답 못 하면 `preset`은 **null**이고(6종 status) 클라는 종전 동작을 유지한다 — 그럴듯한 추측 금지의 근거는 틀린 규격이 `inside`를 바꾸고 그것이 저장 가능한 셀 집합을 바꾼다는 것 |
| GET `/api/maps/overlay` | `get_map_overlay(target_table, target_key, sources, eqp=None, limit=None)` | **[M2 신설 · 맵 인프라]** 임의의 맵들을 타깃 맵 프레임 좌표로 정렬해 `overlays[]` 반환. `sources`는 `table` 또는 `table:key`의 CSV(키 생략 시 target_key 승계, 최대 8종). `map_overlay.get_overlay` 위임([§5](#5-소형-서버-모듈)), `parse_sources` ValueError → 400, 셀 상한 `MAX_OVERLAY_CELLS=20,000`(초과 시 `truncated:true`). ⚠️ **`eqp` 쿼리 파라미터는 no-op으로 존치** — `map_overlay.get_overlay`의 `eqp` 인자는 `by_eqp` 분기와 함께 삭제됐다(축소는 총괄 승인 사항). **맵 에디터 클라는 이 엔드포인트를 호출하지 않는다** |
| GET `/api/maps/paint-rules` | `get_map_paint_rules(table=None)` |  **[M2 신설]** 페인트 잠금 선언 정본(**기존엔 클라 하드코딩 `'F'`**) — `map_overlay.get_paint_rules`. **[U6 `95bf072`] 맵 기본값 2종을 같은 응답에 동봉해 클라가 사본을 갖지 않게 한다**: `value_column_candidates`(해석 **완료** 목록 — 항상 존재, `resolve_value_column_candidates`) · `default_legend`(선언 그대로 \| **null** = 정직한 부재, `get_default_legend`). **[F1 `17f65bd`] `binding` 동봉** — `table` 지정 시 그 테이블의 **해석 완료 좌표 바인딩** `{x, y, val, key_columns[], source: "declared"\|"derived"\|"fallback_guess"}` \| null(`map_overlay.resolve_binding_info` — 클라 재유도 금지의 단일 원천, [F2] `fallback_guess`는 데이터 경로가 거부하는 추측이라 클라가 **경고해야** 한다). 응답 `{table, rules{…}, binding, default_legend, value_column_candidates}` |
| 🆕 GET `/api/maps/alignment/view` | `get_map_alignment_view(rule, map_table, params=None, reference=None, include_cells=True, x_col=None, y_col=None, value_col=None, assume_reference_geometry=True, db)` | **[신설] 프레임 정렬 채점 뷰** — 🆕🆕 🔴 **[`7097a67`] 위임 대상이 바뀌었다: `map_alignment.build_alignment_view`가 아니라 [`alignment_view_service.resolve_alignment_view`](#5-g--dtcore-프레임-유도-체인-2026-08-11-신설-등재)다.** 규칙 조회·`decision_key` 검증·config 로드가 전부 그 모듈로 갔고, 핸들러에 남은 것은 `params` JSON 파싱과 **예외 → 상태코드** 사상뿐이다(`AlignmentViewRequestError`의 문구로 404/400을 가른다). **왜**: 체인 맵퍼가 같은 뷰를 물어야 하는데 라우트 안에 갇혀 있으면 **두 번째 판정 구현**이 생긴다. Map Editor 2가 소비하는 참조 뷰 페이로드다(클라 세관은 [`map2/decode.js`](#7-a--map-editor-2--map_editor2html--client2srcmap2-2026-08-0506-신설)). 🔴 **백분율을 싣지 않는다** — 클라의 `assertNoRatioInPayload`가 그것을 계약으로 채점한다 |
| 🆕 🔴 **POST `/api/maps/alignment/confirm`** | `confirm_map_alignment(payload: dict = Body(...), db)` | **[신설] 이 사슬에서 유일한 쓰기 경로다 — GET 등가물이 없다.** `frame_confirmation.record_confirmation` → `frame_confirmation.as_payload(db, header)`; `except frame_confirmation.ConfirmationRefused`가 어휘 관문 셋의 거절을 표면화한다([§5 `frame_confirmation.py`](#-serverframe_confirmationpy--확정의-기록자)) |
| 🆕 GET `/api/maps/alignment/worklist` | `get_map_alignment_worklist(rule, map_table, params=None, q=None, sort="unit_key", order="asc", limit=map_alignment.DEFAULT_WORKLIST_LIMIT, offset=0, db)` | **[신설]** 확정 대기 단위 목록. `map_alignment.worklist_sort_keys` · `MAX_WORKLIST_UNITS` · `build_alignment_worklist`. ⚠️ **`limit` 기본값이 모듈 상수다** — 숫자를 여기 베끼지 마라. 🔴 **구 지도의 앵커 `4649`는 이 표의 다른 칸과 뜻이 달라 걷어냈다** — 데코레이터는 **4645**(@`e943e46`)이고 `4649`는 그 핸들러 시그니처 중간이다. 🔴 **`map_table`은 이 라우트의 필수 파라미터**라 화면의 워크리스트는 언제나 정확히 한 테이블에 속한다(클라 쪽 계약은 [§7-A](#7-a--map-editor-2--map_editor2html--client2srcmap2-2026-08-0506-신설)). 🆕🆕🆕🆕 **[`c4a3159`] 이 핸들러는 의도적으로 손대지 않았다** — 파생 표의 한 행이 결정키를 못 채워 `frame_confirmation.ConfirmationRefused`(`ValueError`가 아니다)를 던지면 종전엔 이 라우트까지 올라가 **요청 전체**가 500이었다. 여기서 그 예외를 잡는 것도 고칠 수는 있었지만, 그러면 "데이터 문제"가 "요청 문제"(400)로 둔갑한다 — 수리는 `build_alignment_worklist` 안, 아래 참조 |
| 🆕 GET `/api/maps/alignment/references` | `get_map_alignment_references(table=None, cap=map_alignment.MAX_REFERENCE_CANDIDATES, db)` | **[신설]** 기준 맵 후보 카탈로그. `MAX_REFERENCE_CANDIDATES` · `resolve_reference_catalog`. 클라는 `REFERENCE_CATALOG_SERVED`/`_UNAVAILABLE`로 서빙 여부를 가른다 |
| GET `/api/transfer-plan/stages` | `get_transfer_plan_stages` | **[M2 신설]** 선언된 전사 stage 목록 + 역할 연결 상태(config 해석만 — 행 조회 없음). `transfer_plan.list_stages` |
| GET `/api/transfer-plan/source-summary` | `get_transfer_plan_source_summary(stage, lot, slot=None, ref_table=None, map_key=None, bins=None, scope="slot")` | 단계별 소스 가용 집계 — 미선언 stage 404, **칩 좌표 목록은 반환하지 않는다**(집계만). `(ref_table, map_key)` 지정 시 `region_chips` 동봉. **[`269b39e` BIN 축]** `bins=1,2` → `bins` 블록 동봉(맵에 없는 BIN은 `status:"bin_absent"` — **절대 0이 아니다**), `bins=`(빈 값) → 전 BIN 나열, 생략 → 블록 없음(기존 소비자 무영향). **`scope=lot`**(자재 토큰 `MID1:2` = 로트 전체)은 `slot` 동반 시 400, 응답에 `chips` 없음 — `transfer_plan.get_lot_bin_summary` 위임. `scope=slot`은 `get_stage_source_summary` |
| GET `/api/transfer-plan/validate` | `validate_transfer_plan(ref_table, map_key)` | 계획 검증 — **계획 정체성 = 지금 열어 편집 중인 맵**(`plan_id` 폐기). stage는 `stages.*.target_map.table` 역인덱스로 유도, 미선언 맵은 404가 아니라 `stage_unknown` 경고 + `status:"unverified"`. **`plan_store.registry` 미구성만 404**. **[`b35bc9f` zone 모델] validate는 이제 zone 컬럼(`stack`/`mat_*`)을 읽고 `bands`는 레거시 읽기 전용** — [§5 transfer_plan.py](#5-소형-서버-모듈) |
| GET `/enrichment/rules` · `.../references/{index}` | `get_enrichment_rules` / `get_enrichment_reference` | 인리치먼트 규칙 공개본·참조 뷰 조회. **[F9 `f3fd785`] 응답 계약이 가산적으로 넓어졌다** — `reference_views[]`가 `{label}`에서 **`{label, candidate_for}`**가 됐다(`enrichment_config.to_public_rule`. 노출되는 것은 **뷰 결과 컬럼명**이고 그것은 `.../references/{index}` 응답에 이미 헤더로 나타나므로 **신규 노출 0**이며, 숨겨야 할 것(쿼리 본문·`limit`)은 그대로 숨겨져 있다. 🔴 **`get_enrichment_reference`가 인라인 LIMIT 래핑 사본을 버렸다** — 이제 `enrichment_config.execute_reference_view`가 **유일한 정의**이고 예외도 `ReferenceViewError`로 좁혔다(두 정의가 갈라지면 사람이 보는 표시 행 집합과 후보 해석이 다른 행을 보게 된다) |
| 🆕 **🔒 GET `/admin/config/resolve`** | **`get_config_resolve_report(domain=None)`** | **[F9 `f3fd785` 신설] 「내 config가 먹었는가」의 답** — 등록된 config 도메인의 해석 보고서(`effective`/`ineffective`/`rejected` + `settings` + `vocabulary`). `config_resolve_report.resolve_report(domains)` 위임([§5-B](#5-b-serverconfig_resolve_reportpy--내-config가-먹었는가의-답-f3fd785-신설)). `domain`은 **CSV**(`?domain=enrichment,...`)이고 미지 도메인은 조용히 스킵. 🔴 **DB 질의 0건**(설정 파일만 읽는다)이라 요청 경로에 앉아도 되는 것이 이 라우트가 값싼 이유다. 사유는 **닫힌 어휘**(`REASONS` 4종)이고 사람이 읽을 문장은 **서버가 만든다** — 클라는 `detail`을 그대로 렌더하고 「효과 없음」을 스스로 판정하지 않는다(U6 하드코딩 사본 계급의 재발 방지) |
| 🆕 **🔒 GET `/admin/config/virtual-join/verify`** | **`verify_virtual_join_declarations(db)`** | **[`b6942ec` 신설] 「이 가상 조인 선언이 승인됐는가, 아니면 무엇을 만들어야 하는가」.** `virtual_join_config.verification_report(db, known_tables=crud.TABLE_CONFIG)` 위임([§5-C](#5-c-2026-07-31-신설-서버-모듈-2종)) — **`import`는 함수 안**이다.<br>🔴 **`/admin/config/resolve`가 답하지 못하는 절반이다.** 그 라우트는 **「DB 질의 0건」이 계약**이라 설정 파일만 읽는데, 승인 조건인 「조인 키를 덮는 UNIQUE 인덱스」는 `pg_index`가 아는 사실이라 세션이 필요하다.<br>🔴 **비싸지 않다 — 행을 세지 않고 카탈로그만 읽는다.** 비용이 테이블 크기와 무관하므로 1,000만 행 테이블에서도 요청 경로에 앉을 수 있다. ⚠️ **직전 판(`4e06eec`)의 중복 프로브는 전수 스캔이라 그럴 수 없었고, 그래서 `b6942ec`가 그것을 통째로 삭제했다** — `CREATE UNIQUE INDEX`가 같은 것을 더 잘 말하기 때문이다(중복이 있으면 PostgreSQL이 **그 중복 키 값을 지목하며** 인덱스 생성에 실패한다).<br>**거부된 선언에는 `required_index_ddl`과 사람이 읽을 `detail` 문장이 실린다** — 문장은 `/admin/config/resolve`와 **같은 조립기**(`config_resolve_report.virtual_join_detail`)가 만든다. 갈라 두면 같은 거부가 두 화면에서 다른 문장으로 나오고, 그 순간 「서버가 문장의 정본」이라는 계약이 깨진다 |
| 🆕 **🔒 GET `/admin/enrichment/auto-confirm/dry-run`** | **`get_enrichment_auto_confirm_dry_run(rule, limit=200, db)`** | **[F9 `f3fd785` 신설] 「이 규칙은 사람 없이 몇 건을 확정할 수 있는가」 — 쓰기 없는 계기.** `enrichment_analysis.run_auto_confirm_sweep(db, target, apply=False, limit, ignore_knob=True)`를 그대로 노출한다(그 함수가 이미 읽기 전용이고 끝에서 구조적으로 rollback하므로 **새로 만든 계기는 없다** — CLI에만 닿아 있던 것을 어드민에서 닿게 할 뿐). 🔴 **`apply`는 이 경로에 존재하지 않는다** — 쓰기는 CLI(`enrichment_insights.py`)에만 남는다. **`ignore_knob=True`가 의도**다: 「켜면 무슨 일이 일어나는가」는 켜기 **전에** 답해야 하는 질문이고, `run_auto_confirm_sweep`은 `ignore_knob`+`apply` 조합을 스스로 거부한다. `AnalysisRefused`는 500이 아니라 **보고서와 같은 어휘**(`refused_reason: "not_declared"`)로 200을 준다 — 클라가 두 표면에서 같은 단어를 읽는다. 상한 `ENRICHMENT_DRY_RUN_DEFAULT_LIMIT=200`, **작업 단위 캡과 같은 수**라 "한 작업 단위가 무엇을 했을까"가 그대로 답이 된다)·`ENRICHMENT_DRY_RUN_MAX_LIMIT=2000`, `examined >= limit`이면 `truncated: true` |
| WS `/ws` | `websocket_endpoint` | WS 접속(ConnectionManager). ⚠️ **WS 라우트는 게이트 대상이 아니다** — `Depends`가 HTTP 라우트에만 걸리므로 `test_admin_auth.py`도 WS와 mount는 건너뛴다 |
| 🔒 POST `/internal/events/batch-refresh` · `/broadcast` · `/file-processed` | `internal_event_batch_refresh` / `internal_event_broadcast` / `internal_event_file_processed` | **워커/워처 → 웹서버 브로드캐스트 위임 (경계 계약)** — 수신부는 `total_log_count`(실건수) 우선 + `MAX_NOTIFY_CREATED_LOGS` 방어 절단(인시던트 `cc57b64`, 절단 지점 **~5058·~5106**). [P1] batch-refresh는 msg 재구성 시 `total_log_count` 동봉, broadcast는 `file_ingestion_progress`를 레지스트리에 인터셉트, file-processed는 레지스트리 제거 인터셉트. **[`90e284f`] 게이트 추가 — `/internal`이 `/admin`과 같이 묶인 이유는 `broadcast`가 임의 dict를 전 WS 클라이언트에 중계하고 audit_cache에 주입하기 때문**(읽기 전용 admin은 잠그고 이건 열어 두는 것이 거꾸로였다) |
| 🔒 POST `/internal/events/ingestion-state` | `internal_event_ingestion_state` | **[P1]** watcher → 진행 스냅샷 push(QUEUED/PROCESSING/FINISHED — heavy 파일만 명시 통지). **WS 브로드캐스트 없음** — 레지스트리 전용 내부 이벤트 |
| 🆕 🔒 GET `/admin/retroactive/operations` | `list_retroactive_operations` | **[소급 적용 인벤토리]** `retroactive.inventory()`의 순수 config 투영 — **DB를 건드리지 않는다** |
| 🆕 🔒 GET `/admin/retroactive/{op}/count` | `get_retroactive_count` | 드라이런 미리보기. 🔴 **응답의 `count_kind`가 세 값(`exact`/`sample`/`upper_bound`)인 것이 이 표면의 정직성 계약이다** — 걷지 않고 답한 수를 "N행 스캔"이라고 말하지 않는다 |
| 🆕 🔒 **POST `/admin/retroactive/{op}/run`** | `trigger_retroactive_run` | 🔴 **`require_admin_token_strict`.** 그리고 **여기서 아무것도 실행하지 않는다** — `retroactive.publish`가 outbox 행 1개 + `NOTIFY`만 하고, 실행은 스케줄러 프로세스의 데몬 스레드가 한다([§5-D](#5-d-2026-08-04-신설-서버-모듈)) |
| GET `/admin`·`/admin.html` | `serve_admin_page` | **어드민 HTML 자체는 게이트 없이 서빙된다** — 페이지가 떠야 토큰을 물어볼 수 있다. `test_admin_auth.PUBLIC_ADMIN_PATHS`가 **이 둘만** 면제로 허용한다(이름으로 고정) |
| GET `/map-editor`·`/map_editor.html` | `serve_map_editor_page` | 정적 페이지 서빙 |
| 🆕 GET `/map-editor2`·`/map_editor2.html` | **`serve_map_editor2_page`** | **[신설] Map Editor 2 페이지** — 구 에디터를 **대체하지 않고 옆에 선다**([§7-A](#7-a--map-editor-2--map_editor2html--client2srcmap2-2026-08-0506-신설)) |
| GET `/enrichment`·`/enrichment.html` | `serve_enrichment_page` | 🔴 **[2026-08-11 후속 실측] 라우트는 살아 있지만 서빙할 파일이 없다 — 항상 404.** `ab36fab`가 `client2/enrichment.html`과 그 vite 빌드 엔트리를 지웠는데, **이 핸들러 자체는 지워지지 않았다.** 본문은 여전히 `dist/enrichment.html` → 없으면 dev `client2/enrichment.html` → 둘 다 없으면 3번째 갈래. 🆕🆕🆕🆕 **[`fde424c`] 그 3번째 갈래의 문구가 바뀌었다** — 구 `"Enrichment page not found. Please build frontend first."`(다시 만들 수 없는 파일을 빌드하라고 보냈다)에서 **`"Enrichment 페이지 폐지됨 · 참조뷰 → 메인 화면 이력 사이드바 탭"`**(퇴역 사실과 후계 경로를 말한다)로 |
| GET `/{file_name:path}` | **`serve_static_or_index`** | SPA catch-all. **[`90e284f`] 격리(containment) 경계** — 아래 §1.4-bis. **catch-all이 파일 최하단인 것이 계약** — `/health`가 이보다 위에 등록돼야 한다(§1.1-bis) |

> ⚠️ **위 정적 라우트는 조건부 등록이다** — `serve_admin_page`·`serve_map_editor_page`·🆕 **`serve_map_editor2_page`**·`serve_enrichment_page`·`serve_static_or_index` 전부 **`if os.path.exists(client2_dist_path):` 블록 안에 들여쓰기**돼 있다(`/assets` mount **6004**). ⚠️ **구 지도가 `client2_dist_path` 조립 지점으로 적던 `503–505`는 이 블록이 쓰는 그 변수가 아니다** — 정적 블록이 읽는 조립은 **5997–5999**에 있고, 503–505 부근의 것은 함수 지역의 다른 사본이다. 즉 **빌드 산출물이 없으면 이 네 라우트는 앱에 존재하지 않고** `/admin`은 404가 아니라 **catch-all도 없는 상태**가 된다. 게이트 감사(`test_admin_auth.py`)가 앱의 라우트 목록을 훑는 방식이라, dist 없이 돌린 테스트는 이 넷을 **아예 보지 못한다**.

> ✅ 🔴 **게이트 개수 재측정 (2026-08-04 여덟 번째 패스) — 구 표기 "24 + 4 = 28"은 틀렸다.** 실측(`87a944e`): 게이트 데코레이터 **28개** = `/admin` + `/internal`. 게이트 없는 `/admin` 라우트는 **0개**다. ⚠️ **구 표기 27 = 23 + 4는 낡았고, 같은 문서의 다른 자리가 「24 + 4 = 28」이라 적어 두 값이 공존하고 있었다** — 지금은 실측이 후자와 일치한다. **strict — 전건 열거**(이름으로 고정, 개수에 기대지 않는다): **`POST /admin/retroactive/{op}/run` · `POST /admin/auto-update/run-now` · `POST /admin/scripts/code`**. 🔴 **셋의 공통점이 strict의 정의다 — 서버가 코드를 실행하게 만드는 요청**이다. 소급 실행이 여기 들어온 것은 그것이 데이터를 지우거나(`withdraw`·`graph_orphans`) 되쓰기(`chain_replay`) 때문이고, **조회 두 라우트는 평범한 `require_admin_token`이다.**

### 1.4-bis `serve_static_or_index` — SPA catch-all이자 **파일시스템 격리 경계** (`90e284f`)

⛔ **이것은 "정적 파일 핸들러"가 아니다.** 인증 없이 도달 가능한 이 함수가 곧 **프로세스가 읽을 수 있는 모든 파일과 외부 사이의 유일한 경계**다. 격리 검사가 없던 시절 `os.path.join(client2_dist_path, file_name)`이 그대로 서빙돼 `/../../server/config/table_config.json` · `/../../../../../../Windows/win.ini` · `/../../server/admin_auth.py`가 **전부 200을 반환**했다. 그 상태에서는 `GET /admin/scripts/code`·`/admin/chain/rules`·`/admin/file-ingestion/workspaces`에 건 게이트가 **장식**이다 — 지키려던 바이트를 옆문으로 읽을 수 있었고, 읽히는 파일 어딘가에 토큰이 있었다면 그것까지 함께 나갔다.

| 구간 | 라인 | 내용 |
|---|---|---|
| 접두어 목록 (`tables`/`ws`/`audit_logs`/`dashboard`/`admin`/`map-editor`/`map_editor`/`map-presets`/`enrichment/`/`api`) | **5449–5458** | **API 섀도잉 방지장치이지 보안 경계가 아니다** — 소스 주석이 그렇게 명시한다. 경로 **시작**만 보므로 `../../server/config/table_config.json`은 `admin`과 조금도 닮지 않아 그대로 통과한다 |
| **격리 검사** | **6115–6117** | `dist_base = os.path.abspath(client2_dist_path)` → `target_path = os.path.abspath(os.path.join(dist_base, file_name))` → **`target_path`가 `dist_base` 자신이거나 `dist_base + os.sep`로 시작하지 않으면 거부.** `_resolve_admin_script_path`와 **같은 모양**이다(사유 주석 **6111–6114**) |
| 서빙/폴백 | **5481–5487** | 통과한 실파일만 `FileResponse`, 그 외 `index.html` |

**이 형태를 "단순화"하지 마라 — 세 가지가 전부 의도다:**
- **먼저 resolve하고 나서 검사한다.** 문자 denylist(`..` 금지 등)로는 못 막는다 — `os.path.join`은 두 번째 인자가 절대경로(`/C:/Windows/win.ini`)거나 **윈도우 드라이브 상대경로(`C:foo`)면 base를 통째로 버린다.** 해석된 결과만 검사하는 것이 유일하게 건전한 방법이다.
- **거부는 403이 아니라 404다**(**5478** 주석) — 정적 라우트가 "그 탈출 경로는 파싱됐다"고 확인해 주면 안 된다.
- **접두어 목록을 격리 검사로 착각하지 마라.** 위 표의 첫 줄이 그 오해를 막으려고 소스 주석에 박혀 있다.

`tests/test_admin_auth.py::TestStaticFallbackCannotServeArbitraryFiles`가 이 경계를 지킨다.

### 1.5 그래프 조회 구간 (read-only — `graph_nodes/edges` 직접 조회, 워커 미경유)

| 메서드 경로 | 핸들러 | 역할 |
|---|---|---|
| (상수) | `GRAPH_NEIGHBOR_NODE_CAP=500` / `GRAPH_NEIGHBOR_EDGE_FETCH_CAP=2000` / `GRAPH_SEARCH_LIMIT_CAP=50` / `GRAPH_LABEL_LIST_LIMIT_CAP=200` / `GRAPH_TRACE_NODE_CAP=1000` / `GRAPH_TRACE_DEPTH_CAP=3` / `GRAPH_TRACE_DEFAULT_LIMIT=500` | 하드캡(C-7 무제한 로드 금지) |
| (헬퍼) | `_expand_graph_subgraph(db, seed_nodes, depth, node_cap, edge_types=None, time_from=None, time_to=None)` | 뷰어/추적 **공용 BFS 코어** — 방향별 (from,type)/(to,type) 인덱스 2쿼리, 홉·방향당 엣지 페치 캡 2000, 노드 500청크 IN, 캡 절단 시 dangling 엣지 제외 |
| (헬퍼) | **`_serialize_graph_edge(e, include_props=False) -> dict`** | **[2026-07-30 추출] 엣지 직렬화의 단일 정의** — `{from,to,type,source_name,updated_by,event_time}` + `include_props`면 `props`. **직접 호출부는 2곳**(`_expand_graph_subgraph` 내 **2596** · `get_chip_trace` 내 **3123**)인데 **소비 엔드포인트는 3개**다: 앞의 호출이 공용 BFS 코어 안에 있어 `/graph/neighbors`와 `/graph/trace` 둘이 그것을 타고, `/graph/chip-trace`가 직접 부른다. chip-trace만 `include_props=True`인 이유는 `eventtime`·`dt_eqp`가 **답 자체**라서다(없으면 `BONDED_TO` 3건이 재작업 순서가 아니라 순서 없는 집합이 된다) |
| (헬퍼) | `_serialize_graph_nodes(nodes)` | 노드 `{id,label,identity_key,props}` 직렬화 — 위 3엔드포인트 공용 |
| GET `/graph/stats` | `get_graph_stats` | label/edge_type GROUP BY 카운트 + last_sync |
| GET `/graph/neighbors` | `get_graph_neighbors` | k-hop(1\|2) 서브그래프 — `_expand_graph_subgraph([center])` 위임, truncated |
| GET `/graph/nodes/search` | `search_graph_nodes` | identity 시작일치 자동완성(limit 캡 50) + **빈 q + label = 라벨 전체 리스팅**(identity 오름차순, limit/offset, 캡 200. 전 테이블 덤프 금지 유지). 🔴 **[F3 `4e8e867`] 술어가 교체됐다** — 구 `identity_key.ilike(_escape_like_term(term)+'%')`가 **`value_suggest.prefix_conditions(col, value_suggest.db_fold(db, term), is_pg)`**로 바뀌었다. 이유는 인덱스다: `Korean_Korea.949` PG에서 btree는 `LIKE prefix%` 범위를 못 서빙해 전 엔트리를 Filter로 버렸다. 대소문자 무시 의미론은 양쪽에 `lower()`를 적용해 보존. **`_escape_like_term`은 함께 삭제**([§0](#0-묘비-목록--소스에-존재하지-않는-이름)) — 범위 비교에서 `%`·`_`는 그냥 문자다. ⚠️ **이 라우트에는 술어 뒤에 2차 필터가 없다** — 그래서 `prefix_conditions`는 상위집합이 아니라 **정확한 범위**여야 한다 |
| (헬퍼) | `_parse_trace_time(value, field)` | ISO 8601 파싱(`Z` 허용), 실패 시 400 |
| POST `/graph/trace` | `post_graph_trace(req: GraphTraceRequest, db)` | **[G2]** 멀티 시드 BFS 합집합 — 시드 순서보존 dedup→(label,identity) 인덱스 조회→missing_seeds 분리→공용 BFS. depth 1..3, 시간·타입 필터, 의미 검증 400 (`GraphTraceSeed` · `GraphTraceRequest`. ⚠️ **POST다**(GET 아님) |
| GET `/graph/mapping-summary` | `get_graph_mapping_summary` | `ontology_config.load_ontology_mappings(known_tables=crud.TABLE_CONFIG)` — materializer와 동일 신호원, 요청 시 디스크 로드. **[2026-07-30] `rejections` 수집기를 넘겨 `rejected`+`rejected_count`를 기존 응답에 **추가**한다**(새 엔드포인트를 만들지 않았다 — [§5 `ontology_config`](#5-소형-서버-모듈)) |

#### 1.5-bis `GET /graph/chip-trace` — 칩 1개의 이력, **웨이퍼 범위로 한정** (`aea4700`+`8670e3b`+`530fdfd`)

**BFS가 아니라 고정 형태(fixed-shape) 질의다.** 파라미터는 `identity` **하나뿐**(depth도 limit도 없다), 시드 라벨은 `CoreCell`. 각 홉이 **닫힌 어휘의 status를 정확히 하나** 보고하므로 "조용히 빈 홉"이 존재할 수 없다. 없는 노드는 404.

| 구간 | 시그니처 / 상수 | 내용 |
|---|---|---|
| 선언 상수 | `GRAPH_CHIP_TRACE_SEED_LABEL="CoreCell"` · `_SCOPE_EDGE=("FROM_CORE","Core")` · `_CHIP_LEGS`, `BONDED_TO→BaseCell` · `TRANSFERRED_TO→DtCell`) · `_EVENT_EDGE=("PERFORMED_ON","ProcessEvent")` · `_EVENT_DECLARED=("PERFORMED_ON","Core")` · `_TERMINAL_LEGS`, `USED_KNOB`/`USED_RECIPE`/`EXECUTED_BY`) | 형태 선언 |
| 캡 | `_EVENT_CAP=500`, 라이브 최대 206) · `_TARGET_CAP=200`, 라이브 최대 6) · `_TERMINAL_CAP=4*_EVENT_CAP` · `_ID_CHUNK=500`, assert **2583**) | 🔴 **import 시점 `assert _EVENT_CAP <= _ID_CHUNK`** — 문서화된 절단 순서 `(identity_key, edge id)`는 앵커 집합이 IN-list 한 청크에 들어갈 때만 성립한다 |
| status 어휘 | `CHIP_TRACE_RECORDED` · `_NONE="none_recorded"`, 선언됐고 0행 — 본딩만 있는 8,493칩) · `_NOT_DECLARED` · `_SCOPE_UNRESOLVED`, Core가 0개 또는 2개↑ — **고르지 않는다**) · `_MAPPING_UNAVAILABLE` · `_NOT_REACHED` | "없다"의 다섯 가지를 구분한다 |
| 헬퍼 | `_chip_trace_declaration()` | 반환 `(declared_pairs, report)` — `load_ontology_mappings(..., rejections=[])`를 걷어 `degraded`를 판정하고 `{status, path, exists, rejected}`를 응답 `declaration`에 싣는다. **`degraded`가 바꾸는 status는 정확히 하나**: `not_declared` → `mapping_unavailable`. 그것만이 선언의 **부재**를 주장하는 status이기 때문 — 매핑 파일이 저장 중이라 안 읽히는 순간에 "`BONDED_TO→BaseCell`은 선언되지 않았다"고 200으로 답하던 결함(엣지는 `graph_edges`에 그대로 있었다) |
| 헬퍼 | `_chip_trace_sort_key(pair)` | `event_time` NULL 후순위 → `identity_key` → edge id. **파이썬에서 재정렬하는 이유는 `NULLS LAST`가 SQLite 테스트 경로로 이식되지 않기 때문** |
| 헬퍼 | `_chip_trace_leg(db, anchor_ids, edge_type, other_label, cap, inbound, declared, declared_pair=None, declaration_degraded=False, anchor_leg=None)` | 홉 1개 실행 → `(leg_dict, [(edge,node)…])`. `leg_dict` = `{edge_type,target_label,status,count,node_ids,truncated,capped_at}`(+미도달 시 `blocked_by`). **`anchor_leg`이 핵심**: "앵커가 진짜 0행이었다"(→ `none_recorded`는 건전한 추론)와 "앵커가 `not_declared`라 쿼리가 아예 안 돌았다"(→ `not_reached`)를 가른다 — 이것이 terminal이 "이 웨이퍼는 knob을 안 썼다"고 말하던 것을 막았다. **`count`(엣지 주장 수)와 `node_ids`(구별되는 엔티티 수)는 의도적으로 다르다**: `BONDED_TO` 3건 = 재작업 3회. `limit(cap+1-len)`으로 "정확히 캡"과 "절단"을 구분 |
| 엔드포인트 | `get_chip_trace(identity, db)` | 범위 채택 조건이 엄격하다 — `len(scope_leg["node_ids"]) == 1 and not scope_leg["truncated"]`가 아니면 `wafer.status = scope_unresolved` + `scope_candidates`. 테스트: `server/tests/test_chip_trace_api.py` |

---

## 1.6 `server/admin_auth.py` — 어드민/내부 토큰 게이트 (`90e284f` 신설)

**462줄**(`23a346d`로 219 → **+243**). **로그인 시스템이 아니다** — 사용자도 세션도 비밀번호 저장소도 없다. 환경변수에서 읽는 **비밀 하나**를 요청 헤더로 제시한다. 프로덕션이 소수 인원의 인트라넷 공유라는 전제에서 의도적으로 이 크기다.

**이 모듈이 생긴 이유**: 그전까지 `/admin/*` 전 라우트가 **패킷을 보낼 수 있는 누구에게나** 열려 있었고 그중 둘은 임의 코드 실행으로 이어진다 — `POST /admin/scripts/code`가 `mappers/`·`ingestion_workspace/`에 파이썬 파일을 쓰고 `POST /admin/auto-update/run-now`가 그것을 실행시킨다. `GET`도 단순 정보가 아니다(소스 코드를 반환하고 파이프라인 표면을 열거한다).

> 🆕 **`23a346d`이 더한 절반은 게이트가 아니라 진단이다.** 게이트 로직(`_enforce`·두 의존성·`ADMIN_GATES`)은 **한 줄도 바뀌지 않았고**, 늘어난 243줄은 전부 **"이 403은 누가 낸 것인가"**에 답하는 장치다: 토큰 지문(양쪽 프로세스가 같은 비밀을 쥐었는지) · 데몬 기동 배너(서버 배너 하나로는 비교가 안 된다) · 거부자 판별(`WWW-Authenticate`가 우리 것인지). 프로덕션 403 하나를 귀속시키는 데 소스 읽기와 `git log -S`가 든 것이 이 라운드의 값이다.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `ADMIN_TOKEN_ENV="ASSY_ADMIN_TOKEN"` / `ADMIN_TOKEN_HEADER="X-Admin-Token"` | 운영자가 세팅하는 환경변수명 / 제시 헤더명. **헤더명이 `X-User`/`X-Transaction-ID`/`X-Source`와 다른 것이 계약** — 컨텍스트 미들웨어가 읽는 이름과 겹치지 않아야 토큰이 `AuditLog` 행에 실려 들어가지 못한다 | ~81/85 |
| **`GATE_CHALLENGE_HEADER="WWW-Authenticate"`** / `_GATE_HEADERS` | **게이트 자신이 낸 거부에만 붙는 마커.** 상태코드만으로는 부족하다 — `_resolve_admin_script_path`도 403을 내는데(격리 서버가 라이브 트리에 쓰려 할 때) 그건 토큰과 무관하다. 이 헤더가 없던 시절 어드민 페이지는 그 403을 "토큰이 틀렸다"로 읽고 **멀쩡한 저장 토큰을 덮어썼다**. 🆕 **[`23a346d`] 이제 두 번째 소비자가 있다** — 아래 `internal_event_failure_note`가 **같은 헤더로 "우리 게이트 / 앞단의 무언가"를 가른다** | **100/101** — 🔴 **종전 값 `5846/5847`은 463줄짜리 파일의 **EOF 밖**이었다(`main.py`의 `_resolve_admin_script_path` 줄 번호가 이 심볼 위에 올라암었다). **EOF 밖 앵커는 독자가 스스로 복구할 수 없는 유일한 계급이다** |
| 🆕 **`TOKEN_FINGERPRINT_CHARS=8`** / `FINGERPRINT_NONE="none"` / `FINGERPRINT_UNUSABLE="unusable-non-ascii"` | 지문 길이와 **지문이 없는 두 상태의 대역 문자열**. 둘 다 의도적으로 비-16진이고 **서로 다르다** — 두 로그를 맞춰 보는 운영자가 한쪽에서 아무것도 못 보면 "미설정인가, 줄이 안 돈 건가"를 구분할 수 없고, "설정됐지만 못 쓴다"는 **처방이 다르다**(변수를 추가하는 게 아니라 **교체**해야 한다) | **119/126/127** |
| `_raw_token()` / **`token_is_unusable()`** | env 원문(strip) / **토큰이 설정됐지만 절대 인증될 수 없는 상태**(비-ASCII). HTTP 헤더는 latin-1로 디코딩돼 오므로 비-ASCII 비밀은 왕복에서 살아남지 못한다 — 모든 정답 시도가 "틀렸다"로 답해지는데 기동 배너는 "잠겼다"고 안심시킨다. **토큰이 아예 없는 것보다 나쁜 실패**라 요청 시점에 맡기지 않고 명시적으로 탐지한다 | ~130/134 |
| **`configured_token()`** | 운영자의 비밀 \| **`None`**. import 시점이 아니라 **호출 시점에 읽는다**(테스트가 `main`을 재import하지 않고 env를 monkeypatch할 수 있게). 공백만 있는 값은 미설정 취급 — 빈 문자열을 export한 운영자는 아무것도 설정하지 않은 것이고, 그걸 진짜 토큰으로 치면 **아무 요청이나 맞힐 수 있는 비밀**이 된다. 비-ASCII도 `None`으로 떨어져 **미설정 상태**(코드 실행만 거부, 나머지는 개방)에 착지한다 — 아무도 제시할 수 없는 비밀로 강제하면 **어드민 16개 라우트가 전부 벽돌**이 되고 복구는 변수를 지우고 재시작하는 길뿐이다 | ~147 |
| 🆕 **`token_fingerprint() -> str`** | **로그에 안전한 토큰의 이름** — `sha256(token)`의 앞 8자, 또는 위 두 대역 문자열. 같은 지문 = 같은 토큰이고, **이 게이트의 403이 뜻할 수 있는 유일한 것이 "두 프로세스가 다른 환경에서 떴다"**이므로 이것 하나면 판정이 끝난다.<br>🔴 **소금도 후추도 없는 맨 `sha256`이 의도**다: 운영자가 비밀번호 관리자의 값으로 `python -c "import hashlib;print(hashlib.sha256(b'<token>').hexdigest()[:8])"`를 돌려 **로그에 손대지 않고 재현**할 수 있어야 하고, 인시던트 한복판에서 **독립 검증할 수 없는 진단은 신뢰받지 못한다**. 도메인 분리 다이제스트는 공짜지만 이 성질을 죽인다.<br>🔴 **길이는 보안 다이얼이 아니다 — 직관이 거꾸로 돈다.** 로그 한 줄을 읽을 수 있는 사람은 **어떤 길이의** 다이제스트에도 오프라인으로 후보를 대조할 수 있고, 짧은 접두는 적중을 **모호하게** 만들 뿐(8자면 2³² 후보당 오탐 1건)이라 64자 전문보다 **약한 오라클**이다. 실제 상한은 토큰 자신의 엔트로피다. 8자인 이유는 사람 쪽이다 — 이 저장소가 하루 종일 읽는 커밋 접두 길이이고, 한 배포가 동시에 쥘 만한 토큰 서너 개 사이 충돌은 ~1e-8 | ~169 |
| `_matches(presented, expected)` | **상수 시간 비교**(`secrets.compare_digest`). **절대 raise하지 않고 어느 쪽 피연산자도 노출하지 않는다** — 깨진 헤더 값이 `TypeError` 트레이스백에 값을 실어 나가지 않도록 통째로 감쌌다 | ~201 |
| `_enforce(request, fail_closed)` | 판정 본체 — 미설정 시 `fail_closed`면 **503**, 아니면 통과. 설정 시 헤더 없으면 **401**, 불일치면 **403**(둘 다 `_GATE_HEADERS` 동봉). **거부 detail은 전부 상수 문자열**이라 제시된 값을 되비추지 않는다 | ~213 |
| **`require_admin_token(request)`** | 일반 게이트 — **`/admin/*` 14곳 + `/internal/events/*` 4곳 = 18 라우트**. 토큰 설정 시 강제, 미설정 시 개방 — 이 빌드로 처음 재시작한 운영자가 릴리스 노트를 읽기도 전에 어드민 페이지 전체에서 잠기지 않게 한다 | ~228 |
| **`require_admin_token_strict(request)`** | 코드 실행에 닿는 **2 라우트 전용**(`POST /admin/scripts/code` · `POST /admin/auto-update/run-now`). 토큰 미설정이면 **503으로 거부**한다 — 비밀 설정을 잊은 것이 구멍을 열어 두는 결과가 되면 안 된다. **이 둘은 절대 개방되지 않는다** | ~237 |
| **`ADMIN_GATES = (require_admin_token, require_admin_token_strict)`** | 이 모듈이 제공하는 의존성 전량. `tests/test_admin_auth.py`가 **FastAPI 앱의 라우트를 직접 훑어** 각 `/admin`·`/internal` 라우트가 이 둘 중 하나로 해석되는지 단언한다 — 나중에 추가된 무방비 라우트는 배포되지 않고 스위트에서 깨진다(**손으로 관리하는 목록이 아니다**) | ~249 |
| **`internal_event_headers()`** | 워커가 `/internal/events/*`를 호출할 때 붙일 헤더 dict. 워커는 `run_decoupled_app.py`의 자식이고 `process_supervisor`가 각 자식 env를 `os.environ.copy()`(~366)로 만들므로 **런처에 한 번 세팅하면 충분**하다. 토큰 미설정 시 빈 dict(게이트가 열려 있는 상태와 대칭) | ~252 |
| `startup_banner() -> (level, message)` | **API 서버**의 기동 로그 한 줄. **3상태**: 비-ASCII → `error`(가장 시끄럽다 — 운영자가 잠겼다고 **믿고** 있다) / 설정됨 → `info` / 미설정 → `warning`(**무엇이 멈추는지 이름으로 말한다**). 🆕 **세 문구 전부에 지문이 실린다**. `main.py`가 `_admin_auth_banner_logged`(~249)로 1회만 찍는다 | **249** |
| 🆕 **`worker_token_banner(process_label) -> (level, message)`** | **데몬 쪽 배너 — 위 배너의 나머지 반쪽.** 지문 하나는 비교가 아니므로 서버 배너만으로는 운영자가 실제로 가진 질문("양쪽이 같은 토큰인가")에 답할 수 없다. **실패 시에만이 아니라 무조건 찍는 것이 요점**이다: 아무도 토큰을 안 쥔 트리는 `/internal/events/*`에 200을 계속 내주면서 배포 기록만 "잠김"이라고 말하고, **들여다볼 계기가 되는 실패가 영영 오지 않는다**. 소비는 [§1.7 `startup_lines`](#17-serverinternal_event_clientpy--내부-http-호출의-단일-소유자-23a346d-신설) 한 곳 | ~302 |
| 🆕 `_AUTH_SHAPED_STATUSES=(401,403,407)` / `_UPSTREAM_ID_HEADERS=("Server","Via")` / `_HEADER_ECHO_LIMIT=60` / `_safe_header_echo(value)` | 인증처럼 생긴 상태코드만 주석을 받는다(500·404·502는 무주석 — 평범한 API 실패에 인증 문단이 자라면 안 된다) / 우리가 아닐 때 누가 답했는지 이름 / 에코 상한 / **상류 헤더 값을 인쇄 가능 단일행 ASCII로 접는다** — 자기 `Server` 문자열을 고르는 상류는 개행을 접어 **자기 로그 줄을 쓸 수 있다** | ~343/348/350/353 |
| 🔴 🆕 **`internal_event_failure_note(status_code, response_headers=None) -> str\|None`** | **`/internal/events/*` POST를 거부한 것이 누구인지 한 줄로 말하고 처방까지 준다.** 인증형 상태가 아니면 `None`.<br>**판별식은 `GATE_CHALLENGE_HEADER`다** — `_enforce`가 자기가 내는 모든 거부에 붙이는 그 헤더. **있으면** 이 애플리케이션이 거부한 것이고 처방은 토큰 이야기다. **4xx인데 없으면 FastAPI 앞단의 무언가가 거부한 것이고, 재기동도 토큰 재발급도 아무것도 고치지 못한다.** 비교는 상수와 **대소문자 무시 완전일치**다(프록시 자신의 `WWW-Authenticate: Basic realm=…`이 우리 것으로 읽히면 안 된다).<br>🔴 **이 판별자는 만들어져서 전송까지 되고 있었는데 쓸 자리에서 버려지고 있었다** — 세 발신자가 상태코드만 로그했다. 게이트는 **헤더 없는 요청에 403을 낼 수 없다**(401을 낸다). 그러니 프로덕션의 반복 403은 처음부터 우리 것이 아니었고, 그것을 확정하는 데 소스 고고학이 들었다 | ~370 |

> **두 상태의 분할이 설계의 핵심**: `ASSY_ADMIN_TOKEN` **설정** → `/admin/*`·`/internal/*` 전량이 헤더 필수(읽기 포함). **미설정** → 코드 실행 2종만 503으로 거부(fail closed)하고 나머지 admin 라우트는 계속 서빙. 새 빌드로 재시작한 운영자가 전면 잠금을 당하지 않으면서, **다칠 수 있는 정확히 그 둘만 잃는다.**
>
> **왜 config 파일이 아니라 환경변수인가**: `server/config/`는 gitignored라 커밋 안전성은 같지만, ① 저장소에 이미 운영자 비밀·위치의 관례가 있고(`DATABASE_URL`·`ASSY_DATA_ROOT`·`ASSY_API_PORT`) ② 환경변수만이 **저장소 안 디스크에 전혀 남지 않는** 유일한 선택지이며 ③ `server/config/**`를 격리 데이터 루트로 복제하는 스냅샷 도구(`devenv.py bootstrap`)에 **딸려 가지 않는다**(비밀이 두 번째 트리에 복제되지 않는다).
>
> **누출 규율 (전부 의도)**: 쿼리 파라미터가 아니라 헤더다(uvicorn 액세스 로그에 안 남는다) · 거부 detail은 상수 문자열이다 · 헤더 선언을 `Header(...)`가 아니라 `Request`로 하는 것도 이 규율이다(FastAPI 검증 에러가 **문제의 값을 422 본문에 렌더링**해 버린다).
>
> 🧪 **`server/tests/test_admin_auth.py` — 1,440줄 · 수집 기준 151건**(`23a346d`로 38 → **151**. ⚠️ `grep -c "def test_"`는 **88**이다 — 나머지는 파라미터라이즈이고, 이 저장소의 다른 테스트 계수와 달리 **여기서는 두 수가 다르다**. 수집 수가 실행되는 수다: `pytest <file> --collect-only -q`). `PUBLIC_ADMIN_PATHS={"/admin","/admin.html"}`(허용된 면제는 이 둘뿐, 이름으로 고정) · `GATED_PREFIXES=("/admin","/internal")` · `STRICT_ADMIN_ROUTES={("POST","/admin/scripts/code"),("POST","/admin/auto-update/run-now")}`.
>
> **클래스 19개**(~111부터): 라우트 전수 커버리지 · 토큰 강제 · 미설정 시 fail-closed 범위 · **토큰 무유출** · **정적 폴백 격리**(§1.4-bis) · 비-ASCII 처리 · 거부의 기계 판독성 · `/internal` 게이팅. 🆕 **`23a346d`이 더한 축 7개**: `TestTokenFingerprint`(~660) · `TestNoOutputCarriesTheRawToken`(~723) · **`TestOperatorFacingLinesSurviveTheProductionConsole`(~807)** · `TestGateStatusSemanticsAreUnchanged`(~855, **게이트 의미가 안 바뀌었다는 것을 이름으로 고정**) · `TestTheFailureNoteNamesWhoRefusedAndWhatToDo`(~885) · `TestEverySenderLogsWhoRefused`(~1061) · `TestEveryDaemonAnnouncesItsFingerprintAtStartup`(~1162) · **`TestInternalCallsNeverConsultProxyConfiguration`(~1209)** · `TestTheStartupCheckSaysWhatAFirstBroadcastWouldHaveDiscovered`(~1347).
>
> 🔴 **`TestOperatorFacingLinesSurviveTheProductionConsole`이 잡는 것은 인코딩 버그가 아니라 문장의 소실이다** — 프로덕션 콘솔은 한국어 윈도우(cp949)이고 `run_app.bat`은 `PYTHONIOENCODING`을 세팅하지 않는다. cp949에 없는 문자(em dash U+2014 — 겉보기 같은 U+2015와 다르다) 하나면 로깅 핸들러가 raise하며 **그 줄을 통째로 버린다.** 프록시 인시던트 중에 **프록시를 지목하는 바로 그 한 줄**이 사라지는 것이 그 값이다. 그래서 [§1.7](#17-serverinternal_event_clientpy--내부-http-호출의-단일-소유자-23a346d-신설) 모듈 말미에도 같은 규율이 주석으로 박혀 있다.
>
> 🔴 **`TestInternalCallsNeverConsultProxyConfiguration`은 "네 번째 발신자가 기억해야 하는 규칙"을 테스트로 바꾼 것이다** — 발신자 파일에 `requests.post(`/`requests.Session(`가 나타나면 실패한다([§0 ⑧](#0-묘비-목록--소스에-존재하지-않는-이름)의 grep이 이 테스트의 요약이다). **같은 결함이 이 엔드포인트 하나에서 발신자별로 이미 세 번 고쳐졌다**는 것이 근거로 적혀 있다.

---

## 1.7 `server/internal_event_client.py` — 내부 HTTP 호출의 **단일 소유자** (`23a346d` 신설)

**359줄**(`ed9cfdb` 235에서 **+124**). **표준 라이브러리 + 지연 `requests` import뿐이고 이 저장소의 어떤 애플리케이션 모듈도 import하지 않는다**(`admin_auth`·`event_constants`, 그것도 전부 함수 안에서). 이 모듈이 강제하는 규칙은 한 문장이다 — **「한 기계 안 두 프로세스 사이의 내부 호출은 프록시 설정을 절대 참조해서는 안 된다」.** 취향이 아니다: 워커→서버 IPC 경로에 낀 프록시는 그것을 **깨뜨릴 수만** 있다.

**인시던트(2026-07-30)**: 프로덕션 체인 워커가 `POST /internal/events/broadcast`에 반복 **403**을 받았다. 게이트는 헤더 없는 요청에 403을 **낼 수 없고**(401을 낸다), **게이트가 아예 없는 `/health`**까지 거부당하고 있었다 — 우리 것이 아무것도 답하지 않았다는 뜻이다. 원인: `requests`의 기본값 `trust_env=True`가 `HTTP_PROXY`와 윈도우 WinINET 프록시 레지스트리를 읽는데, `ProxyOverride`의 `<local>` 토큰은 **점 없는 호스트명만** 면제한다 — `localhost`는 우회되고 **`127.0.0.1`은 우회되지 않는다.** 자기 기계로 보내는 통지가 사내 프록시로 나갔고, 프록시는 사설 주소로의 중계를 거절했다. `curl.exe --noproxy "*"`는 같은 URL에 내내 200을 냈다. 재기동에 면역이고, 프록시가 없는 개발 기계에서는 **재현되지 않는다.**

| 시그니처 | 역할 | 라인 |
|---|---|---|
| **`DEFAULT_API_BASE_URL="http://127.0.0.1:8080"`** | **웹서버 주소가 사는 단 한 곳.** 종전엔 세 모듈이 이 리터럴을 각자 복사하고 있어 포트를 옮긴 배포는 고칠 곳이 셋이었고 **어느 것도 실제로 포트를 정하는 값에서 유도되지 않았다** | ~42 |
| `_LOOPBACK_HOSTS` / `_http_local` | 「이 기계」의 호스트 6종(판정이 아니라 **얼마나 시끄럽게 말할지**에만 쓴다) / 스레드 로컬 저장소 | ~46/48 |
| `api_base_url()` | `API_BASE_URL` env \| 기본값. **import 시점이 아니라 호출 시점에 읽는다** — 테스트·격리 스택이 발신자를 재import하지 않고 방향을 틀 수 있게 | ~51 |
| 🔴 **`internal_event_session()`** | **워커→웹서버 호출용 `requests.Session`, 호출 스레드당 하나.** 성질 둘 다 load-bearing이다.<br>**`trust_env = False`** — 프록시 환경변수도, 윈도우 프록시 레지스트리도 안 본다. 요청별 `proxies={'http': None…}` 대신 이것을 고른 이유 둘: ① 요청 수준 오버라이드는 윈도우 레지스트리 경로를 `setdefault` 구현 세부에 기대서야 겨우 덮는다 ② **객체의 성질이라 새 호출 지점이 기억하지 않아도 상속한다.** `trust_env`가 관장하는 나머지는 여기서 전부 무의미하다(루프백에 TLS가 없으니 `REQUESTS_CA_BUNDLE`도, 인증은 `.netrc`가 아니라 명시적 `X-Admin-Token`이다).<br>**스레드 로컬** — `requests.Session`은 스레드 안전이 아니고(쿠키 저장소·커넥션 풀이 변이한다) `run_watcher`는 observer 스레드와 재처리 폴러 **양쪽**에서 부른다. 스레드당 1개면 keep-alive 이득(체인 워커가 애초에 세션을 만든 이유)을 스레드 간 가변 상태 공유 없이 유지한다 | ~60 |
| 🆕 🔴 **`record_undelivered_notification(session_factory, table_name, endpoint, reason, logger=None)`** | **[신설] 배달 못 한 내부 통지의 durable 마커.** 종전 `run_watcher.post_event`는 실패를 **로그하고 버렸다** — 마커도, 재시도도, 복구 경로가 찾을 수 있는 기록도 없었다. 그래서 허브가 불통인 동안 나간 통지는 **영구 소실**됐다: **행은 DB에 앉았고 화면은 끝내 몰랐다.**<br>🔴 **새 큐를 만들지 않고 `database_outbox` 행 하나를 쓴다** — "자기 재시도 정책을 가진 두 번째 큐는 틀릴 곳이 하나 더 생기는 것"이다. 행 모양은 `event_type=event_constants.EVENT_BROADCAST_RECOVERY`(**137**) + `status="SUCCESS", processed_chain=True, broadcast_at=NULL`(**135–142**)이고, **그것이 체인 워커의 미배달 스윕이 이미 걷어 가는 정확한 모양**이다.<br>🔴 **실패한 통지의 페이로드를 복사해 넣지 않는다** — batch-refresh 페이로드는 감사 로그 **최대 500건**을 나르고, **그만큼 큰 마커는 복구 경로가 다음 인시던트가 되는 방법**이다(2026-07-25, ~50MB 페이로드). **절대 raise하지 않는다** | **95** |
| `_redact_proxy(url)` / **`proxy_environment_summary()`** | `user:password@` 제거(프록시 env는 자격증명을 흔히 나르고 이 문자열은 **로그 파일로 간다** — 진단 가치는 호스트이고 자격증명은 남의 비밀번호다) / **이 프로세스가 볼 수 있는 프록시 설정을 로그 안전 문자열로.** 네트워크 호출 0. 🔴 **인시던트를 보이지 않게 만든 사실이 정확히 이것이다** — 어떤 로그도 프록시가 존재한다고 말하지 않아 아무도 의심하지 않았다. 이제 **이상이 있든 없든** 모든 데몬이 기동에 말한다 | **170 / 187** |
| `is_loopback(url)` | 이 URL이 우리 기계를 가리키는가 | **208** |
| 🆕 🔴 **`own_health_payload(response)`** | **「우리 것이 답했는가」의 판별자가 상태 코드에서 *응답 본문의 모양*으로 바뀌었다.** `/health`는 설계상 **어떤 검사든 실패하면 503**을 낸다. 그래서 구 규칙(「200이 아니면 다른 무언가가 답한 것」)은 **스택이 그저 아픈 것뿐일 때마다 프록시를 고발했다.** 2026-07-31에 체인 워커와 그래프 싱크 워커가 나란히 프록시 에세이를 찍었는데 **진짜 원인은 중복 런처**였고, **그 에세이는 그 전에도 이 진단을 한 번 오도한 전과가 있었다.** 판별은 이제 `status` + dict `checks`의 존재로 한다 — 진짜 프록시 탐지는 남고 **발화 조건만 좁혔다** | **218** |
| 🔴 **`check_api_reachable(base_url=None, timeout=3.0) -> (level, message)`** | **`GET /health`를 1회 프로브하고 그 답이 무슨 뜻인지까지 말한다. 절대 raise하지 않는다**(데몬 기동 경로에서 도는 진단이 워커를 죽이면 그건 없느니만 못하다).<br>🔴 **`/health`가 프로브 대상인 것이 설계의 전부다 — 거기엔 게이트가 없다.** 결과 해석: **200** = 웹서버가 우리에게 직접 답했다 · **연결 거부/타임아웃** = 아직 아무도 안 듣는다(부팅 중 정상 — 그래서 **INFO**다) · 🆕 **비-200이지만 `own_health_payload`가 우리 것이라고 답하면 = 우리 서버가 아픈 것**(**294–304**) · **그 외 아무 HTTP 상태** = 무언가 답했는데 그것은 이 애플리케이션이 아니다 → **ERROR + 처방** | **240** |
| **`startup_lines(process_label, base_url=None) -> [(level, message)…]`** | **데몬 하나가 자기 내부 이벤트 경로에 대해 로그해야 할 전부를, 순서대로.** ① `admin_auth.worker_token_banner` ② 대상이 이 기계가 아니면 경고 ③ `check_api_reachable`. **한 함수로 묶은 이유는 세 데몬이 같은 진단의 서로 다른 부분집합으로 갈라지지 못하게** 하려는 것이다.<br>⚠️ **비-루프백은 거부가 아니라 경고다** — 통지 1건 실패의 대가는 그리드 갱신 지연(미확정 브로드캐스트 스윕이 복구한다)이고, 기동 거부의 대가는 **인제션**이다. 어드민 게이트가 같은 방향으로 하는 거래와 같다(fail closed는 코드 실행에만).<br>**호출자 3곳**: `chain_ingestion_worker.start_chain_ingestion_worker` · `graph_sync_worker.startup_event`(자체 `try`로 감쌈) · `run_watcher.main` | **335** |

> 🔴 **미배달 마커의 계약은 심볼이 아니라 *컬럼 값 세 개*라서 이 지도에서 가장 깨지기 쉬운 항목이다.** 쓰는 쪽은 `record_undelivered_notification`(**95**, 행 조립 **135–142**), 걷는 쪽은 `chain_ingestion_worker.sweep_undelivered_broadcasts`(**781**)의 쿼리(**802–807**)이고 그 필터가 **정확히** `processed_chain == True` · `status == "SUCCESS"` · `broadcast_at IS NULL` · `created_at < now() − 5초`다. **공유 상수가 없으므로 한쪽만 바꾸면 아무 테스트도 안 깨진 채 마커가 영원히 안 걷힌다.**
>
> 🔴 **`table_name`이 이 복구 경로 전체의 조인 키다.** `run_watcher._record_undelivered`(**~71**)가 `payload["table_name"]`을 꺼내고 **없으면 마커를 쓰지 않는다** → `internal_event_client`가 `DatabaseOutbox.table_name`으로 저장 → `chain_ingestion_worker:838`이 `source_tables`로 되읽어 그 테이블에 `batch_refresh_required`를 쏜다. **고리 하나만 끊어도 마커는 복구 불능이다.**

> ⚠️ **이 모듈의 모든 로그 문장은 cp949로 인코딩 가능해야 한다** — 소스 말미(**~202–208**)에 그 규율이 주석으로 박혀 있고 `test_admin_auth.py::TestOperatorFacingLinesSurviveTheProductionConsole`이 강제한다([§1.6](#16-serveradmin_authpy--어드민내부-토큰-게이트-90e284f-신설)).
>
> 📌 **`API_BASE_URL` 모듈 속성이 `run_watcher`·`chain_ingestion_worker`에 **남아 있는 것은 의도**다.** 값은 `internal_event_client.api_base_url()`에서 오지만 속성 자체는 존치한다 — **`server/scripts/dev_env/iso_watcher.py:260`이 `run_watcher.API_BASE_URL`을 읽어** 격리 워처가 :8080으로 쏘지 않음을 단언하기 때문이다([§6-1](#6-1-설치개발환경-스크립트-8e80fcc4ba13ae47c20f3-신설)). **속성을 지우면 격리 게이트가 `AttributeError`로 죽는다.**

---

## 1.8 `server/column_filter.py` — 필터 DSL 번역기가 **엔트리포인트 밖으로** 나간 자리 (신설)

**181줄. import는 `from database import crud` 하나뿐**(나머지는 함수 안). AG-Grid 필터 DSL → SQLAlchemy 조건 변환의 **단일 구현**이고, 이 파일의 존재 이유 전체가 모듈 docstring에 적혀 있다.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| **`get_column_filter_condition(table_model, col_name, f_info, col_expr_override=None)`** | 컬럼 필터 → SQLAlchemy 조건(타입별). `col_expr_override`는 **가상 조인 해석식을 필터에 먹이는 주입 지점** — 가상 컬럼은 조회할 저장 컬럼이 없고 표시값이 `COALESCE`이므로, 식을 넘겨 **연산자 어휘 전체**(contains/equals/startsWith/inRange…)를 재사용한다(두 번째 얇은 번역기를 옆에 키우지 않기 위해). 🔴 **override는 언제나 텍스트로 취급된다** — 해석값의 정의역에 `unresolved_label`(`"미상"`)이 들어 있어서 오른쪽 컬럼이 숫자로 선언돼 있어도 문자열 식이다 | **35** |

> 🔴 **[이 절이 `CODE_MAP.md`의 이전 판을 정면으로 뒤집는다]** 구 지도(§5-A `enrichment_analysis` 행)는 이렇게 적고 있었다: *"⚠️ `main` import가 함수 안 **지연 import**인 것이 의도다(워커에서 웹앱을 끌어오지 않기 위해) — 모듈 스코프로 올리면 그 성질이 깨진다."*
>
> **지금 시행되는 규칙은 그 반대다.** 소스의 문장은 *"지연 import는 `main`을 **안전하게** 만든 것이 아니라 **늦게** 만들었을 뿐"*이다. 웹 프로세스에서는 `main`이 이미 로드된 애플리케이션 모듈이라 통하고 CLI에서도 통하지만, **워커 프로세스에서는 통하지 않는다** — `run_auto_update.py`가 컬렉터마다 그 디렉터리를 `sys.path[0]`에 꽂고(`parsers/directory_watcher.py`도 테이블마다 `scripts/`에 같은 짓을 한다), 그래서 그 프로세스에서 `main`은 **안정된 이름이 아니다.** 그 디렉터리 중 아무 데나 `main.py`라는 사용자 파일이 있으면 그것이 먼저 바인딩되고 번역기는 그냥 없다. 증상은 큐 순회 깊은 곳에서 나는 `AttributeError: module 'main' has no attribute 'get_column_filter_condition'`이고, **CLI에서 같은 작업은 성공한다.**
>
> 🔬 **같은 모양의 값을 이 저장소가 지불한 것은 이번이 두 번째다** — `chain_ingestion_worker`의 `from main import to_local_str`가 첫 번째였고 처방도 같았다(**프로세스 엔트리포인트가 아닌 모듈로 공용 헬퍼를 옮긴다**, [`utils/time_format.py`](#5-소형-서버-모듈)). **고친 것은 「지연이냐 즉시냐」가 아니라 「`main`이냐 아니냐」다.**
>
> ✅ **재export는 유지된다** — `main.py` **1176–1179**가 `from column_filter import get_column_filter_condition`이라 `main.get_column_filter_condition`을 그렇게 부르던 코드는 계속 해석된다.
>
> ⚠️ **`blank`/`notBlank` 철자는 여기서 정의하지 않는다** — `crud.blank_sql_condition`/`crud.not_blank_sql_condition`에 위임한다([§2](#2-serverdatabasecrudpy--레이어링-코어)). 그 규칙의 깔때기는 하나다.
>
> 🔴 **소스 규칙으로 못 박혀 있다**: `server/tests/test_entrypoint_import_isolation.py::test_no_server_module_imports_the_web_entrypoint`이 `os.walk(server/)`로 트리 전체를 훑어 **어떤 서버 모듈도 `main`을 import하지 못하게** 한다. 이 테스트가 `process_supervisor`·`internal_event_client`·`chain_ingestion_worker`·`run_watcher`까지 같은 규칙 아래 묶는다.
>
> **소비자 3종**: `main.get_table_data`/`export_table_csv`(공용 쿼리 조립 경유) · `main`의 가상 컬럼 바인더 · **`enrichment_analysis._queue_condition`(**~101**, `import column_filter  # NOT main`)**. 🔴 **셋이 같은 번역기를 써야 워크리스트·배지·어드민 카운트·소급 스윕이 「어느 행이 큐에 있는가」를 두고 갈리지 않는다.**

---

## 2. `server/database/crud.py` — 레이어링 코어

> 🔴 **경로 주의 — 이 문서의 나머지가 이 파일을 `crud.py`라고만 부르는 곳이 있다.** 실제 경로는 **`server/database/crud.py`** 하나이고 **`server/crud.py`는 존재하지 않는다.** 위 표지 블록쿼트와 「핀 해시」 계열 산문에는 `main.py`·`models.py`와 나란히 짧은 이름으로 적힌 **역사 서술**이 남아 있다 — 그 문단들은 과거 패스의 기록이라 손대지 않았으나, **거기서 파일을 찾아 나설 때는 이 줄의 경로를 쓰라.** (파이썬 심볼 참조인 `crud.apply_batch_updates`·`crud.SOURCE_PRIORITY` 꼴은 파일명이 아니라 **모듈명**이므로 그대로다.)

> 🟢 **심볼 실측 완료** — 이 절의 심볼은 **`5609ff0`의 커밋된 blob에 존재함이 확인됐고, 그 뒤 HEAD가 움직인 다음 재대조에서도 동일했다**(워킹트리 아님). 🔴 **라인 번호는 싣지 않는다** — 위치는 `git grep -n "<심볼>" -- <경로>`로 확정하라. 숫자가 남아 있는 곳은 **파일 줄 수**이거나, 이름이 없는 덩어리를 가리키며 측정 sha가 함께 적힌 자리뿐이다.

> 🆕 🟢 **[2026-08-08 재측정 · `34d2518`]** **3,209 → 3,980줄.** 세 커밋이 이 파일을 바꿨다 — `4738d84`(P3 프리페치 착지) · `528dfcb`(D3 비즈니스 키 유일 인덱스 + 충돌 재생) · `818c9c0`(빈 키 컬럼은 아무것도 쓰지 않는다). 🔴 **[P3] 미착지 블록은 착지했다** — 아래 그 절은 「예고」가 아니라 「등재」로 다시 썼다. 🔴 **`apply_batch_updates`는 얇은 래퍼가 됐지만 시그니처도 4-튜플 반환도 그대로다** — 신규 API가 아니므로 그렇게 읽지 마라. 실행 본체는 **`_apply_batch_updates_once`**로 이름만 옮겨졌고 호출부 13곳은 무접촉이다.

셀 단위 소스 레이어링(CellSource/CellOverwrite/priority) + 배치 업서트의 단일 구현. **시그니처 변경 시 전수 Grep 연쇄 갱신 필수**([규율](../guide/data_preservation_and_signature_change.md)).

> 🔬 **측정 출처 고정 (2026-08-04, 이 파스 기준):** 이 절의 모든 앵커는 **`41b17ee:server/database/crud.py` = blob `d637d91`** 실측이다. 이 파일은 측정 시각에 **서버 레인이 워킹트리에서 동시 편집 중**이었고, 그래서 워킹트리가 아니라 이 blob을 쟀다. 나중에 앵커가 밀린 것이 발견되면 **그 blob 이후의 커밋에 귀속시킬 수 있다** — 원인 불명이 되지 않는 것이 이 한 줄의 목적이다.
>
> 🔴 **2,612 → 3,209줄(+597). 신설 블록이 둘이고 둘 다 파일 앞쪽에 꽂혔다 — 그래서 이 절은 이번에도 뒤로 갈수록 크게 밀렸다.**
>
>
> ⚠️ **직전 패스가 이 절에서 112줄을 놓쳤던 실패는 반복되지 않게 이번엔 끝·경계·최근 변경 구역에서 표본을 뽑았다** — `set_cell_manual_priority_batch` · `check_needs_rollback` · `get_row_cell` 셋이 파일 뒤쪽 표본이고 전부 위 계단표와 일치한다. 🔴 **핀은 "파일이 안 바뀌었다"만 말하지 "지도가 이 파일을 옳게 적었다"를 말하지 않는다.** 앞쪽 절반이 전건 일치하는 표는 뒤쪽 절반도 맞아 보인다.
>
> 아래 표에 **없는** 실재 심볼: `SOURCE_PRIORITY` · `USER_SOURCE` · `CONFIG_PATH` · `TABLE_CONFIG` 싱글턴 · 재수정률 블록 `RECORRECTION_WINDOW_DAYS`/`_is_json_null`/**`get_recorrection_stats`** · `EFFORT_WINDOW_DAYS` · `create_empty_row` · `get_row_cell`.

#### 🆕 2026-08-04 신설 블록 ① — 버전 게이트  : 「권위는 버전이지 도착 순서가 아니다」

**`table_config.json`에 `version_column`을 선언한 테이블만 이 게이트를 탄다.** 기계 쓰기가 **기존 행**을 덮으려면 들어온 버전이 저장된 버전보다 **엄격히 커야** 한다. 없으면 이 경로는 last-write-wins라, 이미 대체된 파일을 다시 떨어뜨리는 것만으로 **현재 상태가 아무 기록 없이 퇴행**한다.

🔴 **게이트는 거부권(veto)이지 승격이 아니다.** 통과한 행도 셀마다 `compute_priority_value`를 그대로 지나므로 `user`가 모든 기계 소스를 이긴다 — **버전은 같은 우선순위 계층 *안에서만* 순서를 매기고 계층을 건너뛰지 못한다.** 통과했다고 페이로드를 행에 그냥 써 버리면(「버전이 권위다」의 그럴듯한 오독) 다음 인제션이 사람의 교정을 조용히 되돌린다. `server/tests/test_version_gated_overwrite.py::test_human_correction_survives_a_newer_version`이 그 순간 빨개진다.

⚠️ **선언은 테이블 단위이지 요청 단위가 아니다** — 요청 플래그는 모든 호출자가 기억해야 하는 것이고, 잊은 호출자가 바로 그 last-write-wins로 되돌아간다. 아무것도 선언하지 않은 테이블은 종전과 **바이트 단위로 같이** 동작한다.

| 시그니처 / 상수 | 역할 |
|---|---|
| `REASON_VERSION_MISSING` · `REASON_VERSION_UNORDERABLE` · `REASON_VERSION_OLDER` · `REASON_VERSION_SAME` | **거부 4종의 이름.** `enrichment_candidates.REASON_*`와 **같은 어휘·같은 모양** — 거부는 이름 아래 세어지고 일반 실패로 뭉개지지 않는다 |
| `NOTE_ROW_VERSION_ABSENT` / `NOTE_SAME_VERSION_CONTENT_DIFFERS` | 거부가 **아닌** 두 사건. 전자는 저장된 행에 쓸 만한 버전이 없어 들어온 값을 **채택**했다는 뜻(테이블이 게이트를 도입하는 동안만 나야 한다). 후자는 🔴 **진짜 상류 결함**이다 — 버전은 안 움직였는데 같은 소스가 쓰는 **내용은 움직였다**(쓰기는 버려진다) |
| `_version_gate_announced` / `MAX_VERSION_DIFF_COLUMNS_REPORTED = 8` | 테이블→이미 WARNING으로 알린 사유 집합(사유 이름이 유한 집합이라 예산이 필요 없다 — 미선언 컬럼 레지스트리와 다른 점) / 배치 요약에 실리는 **차이 컬럼명 개수 상한**(컬럼명이 페이로드에서 오므로 깨진 파일이 로그 한 줄에 스키마 전체를 밀어 넣지 못하게) |
| **`_VERSION_OUTCOME_EXPLANATION`** | **결과 6종이 각각 무슨 뜻인지 한 문장씩.** 🔴 **둘은 행을 적용하고 넷은 거부한다** — 일반 문장 하나로 뭉치면 적용된 것까지 거부로 서술되고, 그것이 진단이 거짓말을 시작하는 방식이다 |
| `_naive_utc(value)` / `_parse_temporal_version(text)` / **`parse_version_key(raw, col_type) -> (kind, sortable) \| None`** | 한 순간의 한 철자(aware→UTC, naive는 이미 UTC로 간주 — 두 쪽을 비교 가능하게 만드는 것이 이 함수의 전부다) / ISO-8601 파싱 / **순서를 매길 수 있는 키로의 변환.** 🔴 **비교 종류는 선언이 아니라 *값*에서 고르고, 절대 텍스트 비교가 아니다** — `column_text_sql`/`TEMPORAL_TEXT_FORMAT`을 **의도적으로 쓰지 않는다**(텍스트는 `'10' < '9'`로 버전을 뒤집는 바로 그것이다) |
| `_same_source_content_differs(...)` | 「버전은 그대로인데 같은 소스가 쓰는 값이 다르다」의 판정 — 위 `NOTE_SAME_VERSION_CONTENT_DIFFERS`의 근거 |
| 🔴 **`version_gate_verdict(table_name, config, row, is_new, update_item) -> (applied: bool, reason: str\|None)`** | **행 단위 판정.** 셀 단위로 재지 않는다 — 셀별 검사는 한 행의 일부만 받아들여 **어느 버전에도 존재한 적 없는 행**을 만든다. 호출부는 `apply_row_update_internal` 안 한 곳이고, 직접 호출자 6개 + HTTP가 전부 그 관문으로 수렴한다 |
| **`log_version_gate_summary(table_name, version_col, source_name, stats)`** | **개별은 침묵, 집계는 이름으로** — 인제션 드롭 리포트와 같은 자세. 행마다 한 줄이면 1000만 행에서 진짜 사건이 전부 묻힌다. 호출부는 `apply_batch_updates` 안 한 곳이고, 버전 컬럼 조회가 그 바로 앞이다 |

#### 🆕 2026-08-04 신설 블록 ② — 컬럼→비교 텍스트 렌더러 가족  : 「어떤 타입이 캐스팅이 필요한가」가 아니라 「어떤 타입이 *이미* 텍스트인가」

**[보드 N8]** `virtual_join_executor.resolved_expression`이 `COALESCE(<parts>, '<라벨>')`을 짓는데 라벨이 TEXT라 **모든 part가 텍스트여야 한다.** N7은 그 통찰을 「숫자는 캐스팅이 필요하다」로 출하했고, 같은 문 다음으로 들어온 타입(`datetime`)이 **동일한 실패**로 죽었다(PostgreSQL 18.3 실측 `InvalidDatetimeFormat`). boolean도 죽고(`InvalidTextRepresentation`), SQLite에서는 **죽지도 않는다** — 매칭 안 된 행마다 `True`를 답하는데 그게 더 나쁘다.

🔴 **그래서 `column_text_sql`은 검사를 뒤집는다**: 문자열 계열만 그대로 통과하고 나머지는 전부 렌더되며, 이 파일이 들어 본 적 없는 타입은 500이 아니라 **평범한 CAST로 떨어진다.** 내일 추가되는 타입이 이 결함을 다시 열 수 없다.

🔴 **렌더러마다 파이썬 쌍둥이가 있고 그 짝이 요점이다.** SQL 텍스트는 필터·`?q=`·CSV export가 비교하는 것이고, 쌍둥이는 행 페이로드가 브라우저로 나르는 것이다. **쌍둥이 없이 렌더러를 추가하면 이 블록이 닫은 이음매가 다시 열린다.**

| 시그니처 / 상수 | 역할 |
|---|---|
| **`TEMPORAL_TEXT_FORMAT = "%Y-%m-%d %H:%M:%S.%f"`** / `_PG_TEMPORAL_TEXT_FORMAT` / `_install_temporal_text_construct()` | **정본 시각 텍스트 — UTC · 공백 구분 · 마이크로초 항상 6자리.** 🔴 **방언에서 물려받지 않고 못 박는다**: PG 18.3의 `CAST(timestamptz AS varchar)`는 **세션 TimeZone GUC**로 렌더하고(여기선 `+09`) 소수부가 0이면 **통째로 버린다** — 두 축 다 움직이는 표적이라 같은 행을 든 두 서버가 다른 답을 낸다. 고정폭은 덤을 하나 준다: **사전순 = 시간순**이라 해석된 시각 컬럼의 `lessThan`이 거짓말이 아니다 |
| `temporal_text_sql(col_expr)` / `temporal_text_value(value)` | DATE/TIME 렌더러 SQL/파이썬 쌍 (NULL 전파) |
| `boolean_text_sql(col_expr)` / `boolean_text_value(value)` | BOOLEAN → `'true'`/`'false'` 쌍. ⚠️ **NULL 가지를 먼저 쓴 것이 의도**다(`CASE WHEN col THEN … ELSE …`는 NULL을 false로 접는다) |
| 🔴 **`column_text_sql(col_expr)`** | **THE 관문 — 임의의 컬럼 식을 정본 비교 텍스트로.** 문자열 계열은 그대로, 그 외는 렌더, 미지 타입은 CAST 폴백 |
| `resolved_text_value(value)` / `comparison_text_value(value)` | 행 **페이로드**용 파이썬 쌍둥이 / **필터 값**을 해석된 컬럼의 철자에 맞춰 렌더(`clean_str_value`만으로는 부족하다 — boolean을 `'True'`로 적는데 컬럼은 `'true'`로 적는다). 소비자는 `column_filter.get_column_filter_condition`([§1](#1-servermainpy--api--ws-허브)) |

> 📌 **이 시스템이 실제로 여기 넣을 수 있는 컬럼 타입은 소스 주석에 실측으로 열거돼 있다** — `models.init_dynamic_models`가 `column_types`를 SQLAlchemy 타입 **셋**으로만 사상하고(`number`→Float · `datetime`→DateTime(tz) · 그 외→String), 공용 메타 컬럼이 Boolean·DateTime을 더한다. Numeric/Integer/Enum/JSON/ARRAY/UUID는 **모델 빌더가 만들지 않지만** 방어적으로 처리한다 — 「오늘은 안 생긴다」가 정확히 `datetime`을 깨진 채로 남긴 그 추론이기 때문이다.

| 시그니처 | 역할 |
|---|---|
| `transaction_context(user, tx_id, source)` | 컨텍스트매니저 — 감사·outbox용 트랜잭션 식별 주입 |
| `_warn_audit_truncation_once(table_name, col_name)` | [P2] 감사 값 절단 경고 dedup(테이블·컬럼당 1회). 호출부는 `create_audit_log` 내부 |
| **`_warn_undeclared_column_once(table_name, col_name)`** | **[`08d2b12` 신설, `347de78`에서 "1회"가 아니게 됐다 — 이름은 그대로다.** 미선언 컬럼 드롭의 침묵을 없앤다. `column_types`에 없는 컬럼은 종전대로 **조용히 버려졌다** — 쓰기는 성공을 반환하므로 호출자는 데이터가 사라진 줄 몰랐다. **드롭 동작 자체는 의도적으로 그대로**(거부하면 뒤처진 config가 장애가 된다) — 고친 것은 가시성뿐. 🔴 **[`347de78`] 프로세스당 1회 경고는 그 자체가 결함이었다** — 만 번 같은 컬럼을 드롭해도 부팅 시 한 줄 뒤로는 영원히 침묵이라, 고장난 배포와 고쳐진 배포가 이후 로그가 바이트 단위로 같아졌다(프로덕션 컬럼명 불일치가 하루 종일 안 보인 경위). 지금은 **드롭마다 카운트**하고 `_DROP_ANNOUNCE_AT`(`10**1`~`10**18`)에 걸릴 때마다 재공지한다. 레지스트리 키가 페이로드에서 오므로(깨진 헤더 행·값을 헤더로 뱉는 파서) 테이블당 `_MAX_UNDECLARED_WARNED_PER_TABLE=64`는 그대로고, **포화 넘어선 드롭은 컬럼명 없이 `(table, None)` 키로 계속 세어진다**(`_undeclared_column_drops_over_budget`) — 포화는 귀책만 잃고 총합은 잃지 않는다. 호출부는 `apply_row_update_internal` 내부 |
| 🆕🆕🆕🆕 **`undeclared_column_drops() -> dict`** | **[`347de78` 신설, 공개] `{(table, col): count}` 스냅샷** — `(table, None)`은 그 테이블의 예산 초과분. **드롭은 체인 워커에서 일어나고 "이 배포가 아직 컬럼을 잃고 있나"는 다른 프로세스(웹서버)에서 물어야 하므로 공개다.** `chain_ingestion_worker`가 이 스냅샷의 다이제스트를 하트비트 `note=`로 실어 나른다(§4 `chain_ingestion_worker.py`) — 로그를 grep하지 않아도 `/health`가 이미 읽는 채널로 답이 나온다 |
| `class LightCellSource` / `LightCellOverwrite` | ORM 미경유 경량 메타 객체(성능) |
| `sanitize_to_utf8(data)` | cp949 등 오염 문자열 정화 |
| **`class TableConfigError(RuntimeError)`** | **[`46a67c7` 신설] 부팅 fail-fast의 예외 타입** — 아래 넷이 한 배치다 |
| **`_parse_position(exc) -> str`** | JSON 파싱 실패 위치를 사람이 읽을 문구로 |
| **`_decode_config_text(raw: bytes) -> str`** | 🔴 **BOM 부팅 장애의 수리 지점.** 구 코드는 `open(path, "r", encoding="utf-8")`이라 **UTF-8 BOM 한 개가 웹서버를 아예 못 뜨게 했다** — 그리고 윈도우에서 BOM은 예외가 아니라 **기본값**이다(PowerShell 5.1 `Set-Content -Encoding utf8`·`Out-File`이 BOM을 쓰고, 맨 `>` 리다이렉트는 UTF-16 LE + BOM, 메모장은 "UTF-8 with BOM"을 제공). 파일은 어느 편집기에서도 멀쩡해 보인다. 이제 `"rb"`로 읽고 BOM으로 분기: `BOM_UTF8`→`utf-8-sig`, **UTF-32를 UTF-16보다 먼저 검사**(`ff fe 00 00`의 앞 두 바이트가 `ff fe`라, 순서를 뒤집으면 UTF-32 LE 파일이 전부 UTF-16 쓰레기로 디코드된다), 그 외 **strict `utf-8`**. BOM 없는 바이트는 strict라 진짜 cp949 오인코딩은 여전히 raise |
| **`load_table_config_or_raise()`** | 부팅 경로용 — 디코드/파싱 실패는 `TableConfigError`로 **시끄럽게** 죽는다. 같은 배치에서 **비-매핑 JSON도 거부**하게 됐다: 종전엔 `[]`가 `init_dynamic_models`까지 가서 `AttributeError`로 죽고 main의 광범위 `except`에 삼켜져 **ERROR 한 줄 뒤에 동적 모델 0개로 부팅**했고, `null`은 더 나빠서 `TABLE_CONFIG`가 프로세스 수명 내내 `None`이었다 |
| `load_table_config()` / `update_table_config(new_config)` | table_config.json IO (관용 경로 / 쓰기 — 쓰기는 평범한 `open(w)`라 **원자적이 아니다**, config_watcher의 트레일링 엣지가 그 전제에 걸려 있다) |
| 🆕 **`normalize_stored_text(value) -> Any`** | **[신설] 텍스트의 쓰기 경계 정규화기 — `str`이면 `.strip()`, 그 외는 그대로.** 🔴 **이것이 아래 SQL 술어가 짧아도 되는 이유다.** 파이썬 `str.strip()`은 유니코드 공백 **29종**을 걷어내고 Postgres `btrim(x)`은 인자 없이 부르면 **U+0020 하나만** 걷어낸다 — 즉 저장소가 `"\t"`를 품는 것이 허용되면 파이썬은 "비었다", SQL은 "안 비었다"고 답한다. **처방은 SQL에 파이썬의 공백표를 가르치는 것이 아니라**(두 번째 철자가 되어 갈라진다) **갈라지는 입력이 저장소에 도달하지 못하게 하는 것**이다. `list`/`dict`(JSON 컬럼 — `mat_*`의 자재 토큰은 "글자 자체가 정체성")는 컨테이너이지 텍스트가 아니라 손대지 않는다 |
| `cast_value_by_type(value, col_type, col_name)` / `clean_str_value(val)` | 컬럼 타입 캐스팅 (`clean_str_value`는 trim + 정수형 float 접기 — `enrichment_candidates`의 후보 동일성 판정이 이것을 재사용한다) |
| 🆕 **빈 값 술어 4종** — **`is_blank_value(val) -> bool`** / **`blank_sql_condition(col_expr)`** / `blank_to_null(col_expr)` / `not_blank_sql_condition(col_expr)` | **[신설 · `contracts/blank_predicate` 채점 대상] 「비었다」의 파이썬 철자와 SQL 철자, 그리고 그 둘이 같은 답을 내야 한다는 계약.** `is_blank_value`는 종전에 세 곳에 흩어져 있던 `clean_str_value(x) == ""`에 **이름을 준 것**이고(의미 무변경), 이름이 생겨야 SQL 쪽이 무언가를 **가리킬** 수 있다. `blank_sql_condition`은 `col IS NULL OR col = ''` 그 이상을 하지 않는다 — **`btrim`을 의도적으로 넣지 않는다**(위 `normalize_stored_text` 참조). `blank_to_null`은 `NULLIF`가 아니라 `CASE (blank_sql_condition)`로 쓴다: `NULLIF`는 "비었다"의 **세 번째 철자**라 오늘은 구분이 안 되고 내일 갈라진다.<br>⚠️ **선행조건: `col_expr`가 텍스트 타입이어야 한다** — `''`와 비교하므로 PostgreSQL이 `double precision = ''`를 거부한다. 안에서 `CAST`하지 않는 것은 이미 varchar인 컬럼에 `CAST`를 씌우면 플래너가 인덱스를 잃기 때문이다. 그래서 **호출자가 캐스팅해 넘긴다** |
| 🆕 **`numeric_text_sql(col_expr)`** + `BIGINT_SAFE_NUMERIC_TEXT_BOUND = 9.2e18` | **[N7 신설] `clean_str_value`의 숫자 갈래의 SQL 쌍둥이 — 정수 표기까지 포함해서**(7.0 → `'7'`, 7.5 → `'7.5'`). 존재 이유는 `virtual_join_executor.resolved_expression`이다: **숫자 expose 컬럼은 `COALESCE(…, '<라벨>')`에 숫자인 채로 앉을 수 없다.** 🔴 **평범한 `cast(col, String)`으로 안 되는 이유가 요점이다** — 방언이 서로 다르게 답한다(PostgreSQL은 float8 7.0을 `'7'`로, SQLite는 `'7.0'`으로 렌더한다). 이 식은 `BIGINT` 왕복 동치 검사를 껍데기로 써서 **모든 방언에서** 정수 표기를 만든다. 상한 `9.2e18 < 2**63`은 `CAST(… AS BIGINT)` 갈래가 "bigint out of range"로 절대 raise하지 않게 하는 보수적 가드다.<br>⚠️ **`blank_to_null`로 감싸지 않는다 — 구조상 옳다**: 숫자는 `''`가 될 수 없으므로 숫자의 빈 값 갈래는 `IS NULL` 하나뿐이고, `CASE`의 모든 가지가 NULL을 전파한다.<br>🔴 **[N8 정정] 이 함수는 더는 `virtual_join_executor`의 직접 호출 대상이 아니다** — `_text_part`(`virtual_join_executor.py`가 이제 **`crud.column_text_sql` 하나만** 부르고, `numeric_text_sql`은 그 관문 **안에서** 숫자 갈래로만 불린다. 「어떤 타입이 캐스팅이 필요한가」에서 「어떤 타입이 이미 텍스트인가」로 검사가 뒤집힌 결과다(위 신설 블록 ②) |
| `get_row_by_business_key(db, table_name, key_value)` | 비즈니스 키로 행 조회 |
| `resolve_priority_map(table_name=None) -> dict` / `get_source_priority(source_name, table_name=None) -> int` | **소스 서열 단일 원천**(테이블별 오버라이드 포함) — compute_priority_value·graph materializer 공용. `SOURCE_PRIORITY`에 `chain_ingestion: 4` 등재. 🔴 **여기 없는 이름은 99(최하위)로 떨어지고, 그것이 2026-07-30 신설 3종의 안전 논거다** — `enrichment_auto_confirm`·`enrichment_backfill`·(R1의) 재생 쓰기가 **의도적으로 미등재**라 `user`를 절대 못 이긴다. 이 표에 그 이름을 등록하는 단 한 줄의 편집이 기계 판단을 사람 위에 올린다 |
| 🆕🆕🆕🆕 **`compute_priority_value(sources, manual_priority_source=None, table_name=None, ingested_at_by_source=None)`** | **표시값 결정 — 3단 전 순서(total order), `347de78` 신설.** ① **선언된 우선순위**(`resolve_priority_map`, 미등재 99) — user:0 < collision_merge:1 < pipeline_parser:2 < custom_script:3 < chain_ingestion:4, 수동 Pin은 이 단계를 통째로 우회. ② **동순위 안에서 `ingested_at` 내림차순** — 최신 배달이 그 순간의 사실이고, 타임스탬프 미상은 있는 쪽에 진다(2a: `None`은 `float`와 비교되지 않으므로 먼저 걸러야 한다). ③ **`source_name` 오름차순** — 마지막 전 순서. `idx_sources_lookup_source`가 `(table,row,column,source_name)` 유일이라 한 셀 안에서 `source_name`은 유일하고 ③이 항상 결정한다. 🔴 **`347de78` 이전엔 ①뿐이었다** — 파일명 유래 소스는 전부 미등재(99)라 전부 동순위였고, `sorted`가 안정 정렬이라 승자는 **정렬 안 된 SELECT의 dict 삽입 순서**(선착 소스 = 기존 행이 언제나 이겼다, 실측: `assy_qa`에서 동순위 셀 200/200이 구 값을 표시)로 결정됐었다. 새 4번째 인자 `ingested_at_by_source`는 **오버라이드**로 먼저 확인된다 — `sources` 자체가 `{source: value}`(클라 계약이라 타임스탬프를 못 나른다)인 호출자용(§`main.fetch_and_merge_metadata`). 신설 헬퍼 `resolution_ingested_at(entry, source_name=None, ingested_at_by_source=None)`가 세 철자(오버라이드 dict → `entry["ingested_at"]` → `entry["timestamp"]`)에서 ②의 타임스탬프를 읽는다. `chain_replay.withdraw_source`(R2)가 소스 1개를 지운 뒤 **생존자들로 이 함수를 다시 돌려** 드러난 값을 계산하고, 🆕🆕🆕🆕 **`chain_replay.recompute_display_values`(R3)**는 아무것도 지우지 않고 **이미 저장된 레이어 전체**에 같은 계산을 다시 돌려 구 tie-break로 잘못 확정된 표시값만 고친다(§4 `chain_replay.py` 참조) |
| `create_audit_log(db, ..., transaction_id, business_key, add_to_cache)` | 감사 로그 1건 생성. [P2] `old_val`/`new_val`은 `event_constants.truncate_audit_value`로 **4096자 상한** — 절단본이 DB 저장본과 통지 dict **양쪽에** 동일 적용되고, 절단 사실은 값 내부 마커(`…[truncated: 총 N자]`)로 명시 |
| `bulk_insert_audit_logs(db, logs)` | 감사 로그 벌크 삽입 |
| **`record_interaction_effort(db, transaction_id, session_id, key, mouse, nav, nav_preserved=0) -> bool`** | **[V1 `2a9f6c4`] 원시 카운트 기록 — 점수는 저장하지 않는다.** 교정이 **이미 커밋된 뒤 별도 트랜잭션**으로 호출되고, 실패하면 로그만 남기고 `False`. **계측은 계측 대상을 절대 깨뜨리지 않는다** — 공수 한 건을 잃는 것이 사용자의 교정을 잃는 것보다 언제나 낫다. 유일 호출자: `main.apply_batch_updates_endpoint` 핸들러) |
| **`get_effort_stats(db, weights, window_days=EFFORT_WINDOW_DAYS) -> dict`** | **집계 = 세션별 평균 → 세션 간 평균**(사용자 지정). tx를 통째로 평균하면 500건 처리한 한 세션이 전체를 지배한다 — 재교정률이 `transaction_id`로 사람 행위를 접는 것과 같은 이유. 반환 `{window_days, avg_score, tx_count, session_count, weights, measured_ratio}`이고 **`measured_ratio`는 필수 동반 값**이다(커버리지 1.0을 가정할 수 없으므로, 비율 없는 평균은 측정 안 된 범위까지 대표하는 것처럼 읽힌다). 점수는 **읽는 시점 계산**이라 가중치 재조정이 과거 tx를 재해석한다 |
| 🆕 **`_is_executemany_safe(mappings: list[dict]) -> bool`** + `BULK_CHUNK_SIZE = 1000` / `_chunks(seq, size)` | **[`4738d84` 신설] 「이 매핑 목록을 *컴파일된 문장 하나 + 파라미터 집합 N개*로 보낼 수 있는가」.** `.values(chunk)`는 셀마다 `BindParameter`를 만들고 청크마다 다시 컴파일한다(10만 행 맵 파일 실측: `bulk_upsert_cell_sources` 223.2s 중 **SQL은 60.2s, 조립이 163s**). 요구 성질 **둘**이고 타입 주석이 보증하지 않는다: ① **모든 매핑이 같은 키를 갖는다**(들쭉날쭉한 목록은 어느 경로에서도 거절되는데 — SQLAlchemy 2.0의 `.values(ragged)`가 `CompileError` — 거절의 **모양**을 호출자가 이미 받는 그것으로 유지하려는 검사다) ② **값에 SQL 식이 없다**(`ClauseElement`는 파라미터로 바인드 불가. 충돌 병합 경로가 `func.now()`를 넣던 자리다). 🔴 **[2026-08-12 정정] 이 자리에 「순수 fast path다 — 느릴 수는 있고 틀릴 수는 없다」가 서 있었고 두 절 다 거짓이 됐다.** ① 이 술어가 게이트하는 것은 이제 `.values(chunk)`가 아니라 **`_pg_multirow_upsert`**(아래 행)이고, ② **틀릴 수 있었다** — 기본값이 걸린 컬럼에 `None`이 오면 승인 분기가 폴백과 **다른 값을 저장했다**(`is_overwrite` `true`→NULL, 실측). `ed11590`이 그것을 거절 조건으로 옮겼다. **「틀릴 수 없다」는 이 표에서 다시 쓰지 않는다** — 이 문장이 바로 다음 사람이 더 안 봐도 된다고 판단할 때 읽는 문장이었다 |
| 🆕 **`_pg_multirow_upsert(db, table, mappings, conflict_cols, update_cols, chunk_size) -> bool`** (`False` = 거절) + `_warn_upsert_fastpath_declined_once(table, reason, detail)` | **[`ab008ec` 신설 · `ed11590` 수리] 청크마다 진짜 다중 행 `VALUES` 문장 하나를 `conn.exec_driver_sql`로 보낸다.** 🔴 **왜 있는가: `db.execute(stmt, list_of_dicts)`는 이 문장을 배치로 안 보낸다.** `insertmanyvalues`가 `excluded` 참조 `ON CONFLICT DO UPDATE`를 거절하므로 남는 것은 `cursor.executemany` = **행마다 서버 왕복 1회**(실측 20,000 매핑 = 20,000 왕복 → 문장 20개, −79%). ⚠️ **원시 커서(`execute_values`)가 아니어야 하는 이유는 속도가 아니라 예외 클래스다** — 그쪽은 `psycopg2.errors.NotNullViolation`을 던지고 `main.py` 배치 엔드포인트의 `except IntegrityError`가 **안 잡는다**. **거절 4종**(각각 `(table, reason)`당 한 번 WARNING): PostgreSQL+psycopg2 아님 · 매핑 키가 컬럼 아님 · 파이썬 `default` 컬럼을 매핑이 생략 · **기본값 컬럼에 `None`**. ⚠️ **한 문장에 같은 충돌 키가 둘이면 `ProgrammingError`/21000이고 `IntegrityError`가 아니다**(세 `except IntegrityError` 어디도 안 잡는다) — 두 공개 호출부의 dedup이 유일한 방어. 그물 `server/tests/test_pg_multirow_upsert.py`(**격리 PG 선언 시에만 실행**, `ASSY_PG_TEST_DATABASE_URL`) |
| `bulk_upsert_cell_sources(db, mappings, chunk_size=BULK_CHUNK_SIZE)` / `bulk_upsert_cell_overwrites(db, mappings, chunk_size=BULK_CHUNK_SIZE)` | 메타 테이블 벌크 업서트(ON CONFLICT). 🆕 `chunk_size` 인자가 뒤에 붙었다(기본값 있음). **둘 다 conflict 키로 다시 dedup한 뒤** `_is_executemany_safe` → `_pg_multirow_upsert` → (거절 시) 구 `db.execute(stmt, chunk)` 순으로 내려간다 |
| `bulk_delete_cell_overwrites(db, delete_keys)` | overwrite 벌크 삭제 |
| 🆕 **`class ProbedIdentity(NamedTuple)`** — 필드 **`row_ids`·`business_keys`**(둘 다 `frozenset`) | **[`4738d84` 신설 · P3] 배치 프리페치가 *묻고 아무것도 못 받은* 정체성 값들.** 멤버십 = 「이 테이블에 그런 행이 없다」가 **이미 돈 질의로 증명됐다**는 뜻. 🔴 **`prefetched_row_ids`와 다른 것이고 혼동은 성능 문제가 아니라 데이터 손실이다** — 그쪽은 **돌아온** id(행이 존재한다), 이쪽은 **비어서 돌아온** 값이다. 여집합이므로 각자 자기 질문에만 건전하다. 🔴 **「우리가 물어본 값」도 아니다** — `apply_batch_updates`가 프리페치가 돌려준 행을 **빼고** 나서 만든다. ⚠️ **row_id 집합과 비즈니스 키 집합이 갈려 있는 것이 의도다**(프리페치 필터가 `row_id IN (…) OR business_key_val IN (…)`이므로, 비즈니스 키로 덮인 문자열은 어떤 행이 그것을 `row_id`로 쥐고 있는지에 대해 아무것도 증명하지 않는다). ⚠️ **배치의 `no_autoflush` 루프 안에서만 유효** |
| 🆕 **`_absence_is_proven(value, probed: frozenset) -> bool`** | **[`4738d84` 신설]** 「프리페치가 이 값을 물었고 아무 행도 안 왔다」 한 줄 술어. `probed is not None and value in probed` |
| `_get_or_create_row(db, table_model, update_item, row_cache, table_name, probed_identity: "ProbedIdentity" = None) -> (row, is_new)` | row_id/비즈니스키로 행 확보(캐시 활용). 🆕 ✅ **[`4738d84` 착지] 여섯 번째 인자가 *뒤에* 기본값과 함께 붙었다** — 기존 호출은 조용히 틀려지지 않는다(`map_editor.js`에서 `frame`이 **선두에** 끼었던 것과 반대 성질). 🔴 **두 조회 모두 프리페치가 그 값을 묻고 아무것도 못 받았을 때만 생략된다**, 그 밖의 호출자는 `probed_identity=None`으로 오늘의 두 질의를 그대로 유지한다. 🆕 ⚠️ **비즈니스 키 쪽은 `str(...).strip()`한 철자로 검사한다** — 프리페치 필터가 strip된 값으로 지어졌고 `get_row_by_business_key`도 strip 후 비교하므로, **원시 값을 검사하면 패딩된 키가 영구히 미증명으로 남는다**(느려지지 틀리지는 않는다). 🆕 🔴 **신규 행 INSERT에서 `updated_at`을 일부러 세우지 않는다** — 컬럼이 `server_default=func.now()`라 값은 동일한데, 파라미터 집합에 **SQL 식이 없어지면** SQLAlchemy가 `insertmanyvalues`로 접을 수 있다(종전엔 행마다 `INSERT … RETURNING` 한 문장) |
| 🆕 **`_find_business_key_conflict(db, table_model, new_bk_val, row, row_cache, probed_identity=None)`** | **[`4738d84` 신설 · 등재된 적 없던 두 번째 행당 정체성 관문.** 키 컬럼이 비어 온 맵 파일의 **모든 행**에서 발화한다(키가 행 자기 값에서 조립되므로 행이 생성될 때의 `business_key_val`과 절대 안 맞는다). 🔴 **`_get_or_create_row`만 닫으면 세 왕복 중 하나만 줄고 이것이 그대로 선다.** 생략은 **프리페치가 이 키를 물었고 아무것도 — 이 행조차 — 안 왔을 때만**. `row_cache`에 항목이 하나라도 있으면 무조건 DB로 간다(보수적: 유일 인덱스가 없던 테이블은 `row_cache`가 덮어쓴 두 번째 보유자가 있을 수 있고, 그것을 못 본 병합은 행을 둘 남긴다) |
| 🆕 **`assemble_composite_business_key(table_name, update_item: schemas.GeneralUpdateItem) -> bool`** | **[신설 — 종전 지도에 없던 심볼]** 선언된 조각들로 복합 비즈니스 키를 조립한다. 🔴 **아래 [P6] 프리페치가 적중하는 이유가 이 함수다** — 키가 배치 진입 시점에 이미 알려지므로 한 번의 `IN (…)` 조회로 전 행을 덮을 수 있다 |
| `_update_row_business_key(row, key_col, update_item, row_cache)` | 비즈니스 키 갱신. 🆕 🔴 **[`818c9c0`] 빈 키 컬럼은 `''`를 절대 만들지 않고, 아무것도 쓰지 않는다 — 기존 키를 지우지도 않는다.** 두 철자는 교환 가능하지 않다: `''`는 **값**이라 한 테이블의 모든 무키 행이 **같은 정체성**을 갖고, D3 유일 인덱스 아래서 한 배치의 그런 행들이 **서로** 충돌한다. 그리고 `apply_batch_updates`의 회복은 그것을 못 고친다 — 회복이 「롤백하고 다시 읽어 승자의 행 위에 앉는다」인데 **충돌한 행 중 아무것도 커밋된 적이 없기** 때문이다 → 재생이 같은 충돌을 재현하고 배치가 **거절**된다(실측: 키 컬럼이 빈 5행 페이로드를 세 번 밀어 **매번 0행**). 🔴 **NULL로 지우는 것도 틀리다** — 맵 테이블의 키 컬럼은 **파생**이라 「비었다」는 「파일이 안 줬다」이지 「이 행은 키가 없다」가 아니다. 지우면 재푸시가 복합 키 재계산을 건너뛰고(행이 신규 아님·소스 무변경) 아무것도 키를 되돌려 놓지 않는다 |
| `_load_metadata_row_cell(db, table_name, row_id, col_name, is_new, sources_cache, overwrites_cache, cell_sources_to_upsert, cell_overwrites_to_upsert, prefetched_row_ids: set = None) -> (sources_list, overwrite)` | 셀 메타 로드(캐시·업서트 큐 연동). 🔴 **[P6] 프리페치의 소비 지점** — 아래 블록 |
| `apply_row_update_internal(db, table_name, update_item, row_cache, sources_cache, overwrites_cache, transaction_id, logs_to_cache, cell_sources_to_upsert, cell_overwrites_to_upsert, cell_overwrites_to_delete, deleted_row_ids) -> (row, is_new, changed_cols)` | **[통합 코어]** 단일 행 업데이트 + 레이어링 재계산. 모든 쓰기 경로가 여기로 수렴. 🆕 **버전 게이트 `version_gate_verdict` 호출(값 루프보다 앞 — 거부되면 셀 레이어링에 아예 들어가지 않는다)** · 미선언 컬럼 경고 `_warn_undeclared_column_once` · 🪦 🔴 **표기 정규화 파생은 이 함수에서 사라졌다 — 종전 지도가 등재하던 `notation_norm.apply_derivations` 호출은 없다.** `8d306a5`가 저장되는 파생 컬럼을 철회하면서 **쓰기 경로는 원본만 저장하고**(사유 주석 — `server/database/crud.py` **1969–1974** @`e943e46` 재확인 — 이 범위는 밀리지 않았다), 접기는 **질의 시점 SQL**로 옮겨갔다(`notation_norm.fold_notation_sql` — §5-E) |
| **`derive_replace_map_scope(table_name, batch) -> dict\|None`** | **[gate4 `deed6d2` 신설] replace_map purge 스코프의 단일 원천(순수 함수)** — DELETE 필터와 응답 echo가 **같은 이 함수**를 불러 어긋날 수 없다. 해석 순서: ① `batch.scope`(명시 — **엄격 검증**: 미선언 컬럼·map-key 계약 밖·물리 부재·빈 값은 전부 `ValueError`. 필터 하나가 조용히 빠지면 DELETE가 **넓어진다**) ② `updates[0]` 유도(`map_key_columns` 선언 우선, 없으면 레거시 폴백 — 비좌표 컬럼 전부). **None 반환은 거부로 취급해야 한다**(빈 필터 = 전 테이블 삭제 또는 역사적 결함인 "아무것도 안 지운 200") |
| 🆕 **`refuse_virtual_join_columns(db, table_name, batch)`** | **[신설] 가상 조인의 유일한 쓰기 가드.** `virtual_join_executor.virtual_only_columns(db, table_name)`을 물어 그 컬럼이 배치에 실려 있으면 `ValueError`(API 계층이 400으로 사상). 🔴 **`virtual_only`가 `None`이면 fail-closed**다 — `table_config` 없이 검증된 규칙은 "충돌 컬럼을 모른다"는 뜻이고, 그때 열어 주면 오른쪽 테이블의 값을 왼쪽 테이블에 쓰게 된다. `apply_batch_updates` 안에서 **replace_map purge보다 앞**에 부른다(나쁜 페이로드가 삭제를 먼저 시키지 못하게, 호출) |
| 🪦 ~~`refuse_notation_derived_columns(table_name, batch)`~~ | **[삭제됨 — 이 행은 묘비다]** `8d306a5`가 저장되는 표기-정규화 파생 컬럼 자체를 철회하면서 이 가드를 지웠다. `server/database/crud.py`에 **선언 0건**이고 남은 것은 묘비 주석뿐이다. 🔴 **2026-08-06 실측 전까지 이 행은 살아 있는 앵커(구 2235)와 살아 있는 호출부(구 2286)를 달고 표에 앉아 있었다 — 바로 아래 행이 「이 함수는 삭제됐다」고 적는 동안.** 한 절이 자기를 반박하면 독자는 표를 믿는다(표가 더 구체적으로 보이므로). 그래서 지우지 않고 **묘비로 표시**한다 |
| `apply_batch_updates(db, table_name, batch, replace_report: Optional[dict] = None)` | **배치 진입점** — 🆕 🔴 **[`528dfcb`] 이제 얇은 재시도 래퍼다. 시그니처도 4-튜플 반환도 안 바뀌었고 호출부 13곳은 무접촉이다** — 실행 본체는 아래 `_apply_batch_updates_once`다. 회복은 **정확히 하나**: 비즈니스 키의 **프로세스 간 경합에서 진 경우**. 🔴 **재시도가 아니라 병합인 이유** — 롤백이 실패한 트랜잭션을 끝내므로 재생의 프리페치가 **새 READ COMMITTED 스냅샷**에서 돌아 승자가 커밋한 행을 *본다*. `row_cache`가 그 행으로 채워지고 `_get_or_create_row`가 그 위에 앉는다. **별도 병합 코드가 없다 — 재생이 곧 병합이다.** ⚠️ **회복은 언제나 WARNING으로 이름과 함께 로그된다**(조용한 재시도는 아무도 재지 못하는 경합이 된다). 소진하면 ERROR 후 예외를 **그대로 다시 던진다**. ⚠️ **롤백이 치르는 대가 하나**: `ingestion_checkpoint.record_chunk_progress`가 **같은 세션**에서 바로 앞에 낸 오프셋 UPDATE도 함께 버려진다 → 그 모듈이 이미 문서화한 **강등 모드**(나중 크래시가 이 청크를 재처리, 업서트는 멱등이므로 재인제션이지 손실이 아니다) |
| 🆕 **`_apply_batch_updates_once(db, table_name, batch, replace_report=None)`** | **[`528dfcb`] 종전 `apply_batch_updates`의 본체** — tx 컨텍스트, 캐시 프리로드, 행별 코어 호출, 벌크 flush, outbox 발화. 반환 `(results, changed_cells, created_logs, deleted_row_ids)`. [P2] 워처가 이 함수의 commit에 오프셋 갱신을 동승시킨다. **아래 `replace_map`·무변경 생략·`replace_report`·버전 게이트 요약 서술은 전부 이 함수의 것이다** |
| 🆕 **`BK_UNIQUE_INDEX_PREFIX = "uq_bk_"`** / **`BK_CONFLICT_MAX_RETRIES = 2`** | **[D3 `528dfcb`]** `migrations/add_business_key_unique_index.py`가 쓰는 인덱스명 접두사 — ⚠️ **import가 아니라 리터럴 복제가 의도다**(`crud`는 `server/migrations`가 `sys.path`에 없는 문맥에서도 import되고, 여기의 ImportError는 상수 하나를 아끼려고 모든 쓰기 경로를 죽인다) / 재생 횟수 상한. 🔴 **무한 재시도는 수리가 아니라 행(hang)이다** |
| 🆕 **`_is_business_key_unique_violation(exc) -> bool`** | **[D3] 「다른 라이터가 이미 이 비즈니스 키를 갖고 있다」에만 참.** 🔴 **좁은 것이 요점** — 아무 `IntegrityError`나 재시도하면 진짜 제약 실패(NOT NULL·`cell_sources` 유일 충돌·한 페이로드 안의 진짜 키 충돌)를 삼켜 포기할 때까지 재생한다. **방언 둘을 일부러 인식한다**: PostgreSQL은 SQLSTATE `23505` + 제약 이름(권위 있음), SQLite는 코드도 제약 이름도 없이 `UNIQUE constraint failed: <table>.business_key_val`뿐이라 **메시지의 컬럼명이 유일한 신호**다 — PG만 아는 탐지기는 **테스트가 절대 못 밟는다** |
| 🆕 **`_replay_sensitive_key_column(table_name, batch) -> str\|None`** / **`_snapshot_payload_identity(batch, key_col) -> list`** / **`_restore_payload_identity(snapshot, key_col)`** | **[D3-F1] 재생이 시도 1이 남긴 페이로드를 그대로 쓸 수 없다 — 이 셋이 그 이유다.** `assemble_composite_business_key`가 조립한 키를 `update_item.updates[key_col]`에 **제자리로** 쓰는데, `replace_map` 쓰기에서 `derive_replace_map_scope`의 **레거시 갈래**는 첫 페이로드 행에 있는 비-좌표 컬럼 **전부**로 purge 필터를 만들고 비즈니스 키 컬럼은 그 skip 목록에 없다. 그래서 시도 2의 스코프가 **좁아지고**(맵 전체 purge → 행 하나) 라우트는 여전히 200을 답한다. 🔴 **`None`을 반환해 아무 비용도 안 드는 것이 기본** — `replace_map`이고 **동시에** 테이블이 자기 컬럼에서 키를 조립할 때만 발화한다(오늘 해당: `composite_key_source`가 있고 `map_key_columns`가 없는 넷 — `lot_event`·`wafer_id_status`·`eqp_frame_attribution`·`wafer_map_metadata`). 스냅샷은 **깊은 복사가 아니라** 항목당 참조 셋이다. ⚠️ **`replace_map` 밖에서 페이로드로부터 결정을 유도하는 코드가 생기면 이 술어를 넓혀라** |
| | 🔴 🆕 **[`87a944e`] `replace_map`은 더 이상 「지우고 다시 쓴다」가 아니다 — 이제 *차집합*이다.** 종전 지도의 **「차집합 계산 없는 집합 교체」는 이제 정반대의 서술이다.** 관문 `use_diff = bool(_cfg["map_key_columns"]) and bool(_cfg["composite_key_source"])`를 통과하는 테이블(= 배포된 맵 테이블 전부)은 **diff 경로**를 탄다: `replace_scope_row_ids`를 **비우기 전에** 잡고, 앞에서 아무것도 지우지 않은 채 쓰기 루프를 돈 뒤, `claimed_row_ids = set(unique_results) \| set(deleted_row_ids)`를 만들어 **`removed = [r for r in replace_scope_row_ids if r not in claimed]`**만 지운다. 🔴 **순회의 출처가 *스코프*이지 페이로드가 아닌 것이 요점이다** — 페이로드에서 사라진 셀은 구성상 `스코프 − claimed`에 들어가므로 **부재가 조용히 noop이 될 수 없다** |
| | 🔴 **머리기사는 성능이 아니라 `created_at`이 거짓말을 멈춘 것이다.** 구 purge는 Push마다 모든 행을 재생성했고 그래서 **`created_at`도 재생성**했다 — 그 컬럼은 화면에 보이고 복사·내보내기되며 「최신순 정렬」의 기본 키다. 다시 Push된 셀은 이제 `row_id`를 지키므로 원래 `created_at`을 지킨다. (부수 효과 실측, 2,000셀 무변경 재Push: dead tuple 26,000 → **0** · 문장 ~6,045 → **6** · 감사 행 12,000 → **0** · 12.9s → **0.43s**) |
| | 🆕 **무변경 쓰기 생략 2종** — `source_unchanged`는 값과 `updated_by`가 이미 같은 `cell_sources` 행의 재저장을 막고, `ow_unchanged`가 `cell_overwrites`에 같은 일을 한다. ⚠️ **후자는 전자를 술어의 일부로 *일부러* 요구한다** — 값이 진짜 바뀐 셀은 `updated_at`이 갱신돼야 하기 때문이다. 내주는 대가는 무변경 쓰기에서 `ingested_at`이 안 움직이는 것 — 그 컬럼의 뜻이 "누가 마지막으로 저장을 눌렀나"가 아니라 **"이 소스가 이 값을 마지막으로 바꾼 시각"**이 된다. 🆕🆕🆕🆕 **[`347de78`, 소스 자신의 주석이 정정한 문장] 「값을 타임스탬프로 해석하는 곳은 없다」는 더는 참이 아니다** — `compute_priority_value`가 이제 동순위 tie-break에서 `ingested_at`을 읽으므로(위 §2 `compute_priority_value` 행의 3단 전 순서), **이 무변경 생략 판정 자체가 동순위 승자를 결정한다.** 그래도 동작은 유지된다, 근거는 다르게 서술해야 하지만: 이미 배달한 값을 그대로 다시 배달하는 것은 **새 진술이 아니므로**, 그 사이에 값을 바꿔 말한 다른 소스를 추월하면 안 된다 — "최신"은 "값의 최신 주장"이지 "최신 접촉"이 아니다 |
| | **[gate4] 스코프 유도 불가면 `ValueError`로 거부**(침묵 noop 폐지). `derive_replace_map_scope`. **명시 `scope` + 빈 `updates` = 그 스코프의 의도적 전량 삭제**(erase-all) |
| | 🔴 **`replace_report` out-param이 나르는 키 — 전건 열거**(개수를 적지 않는다. 종전 지도는 `{filters, deleted}` 둘만 적고 있었다): **`filters` · `deleted`, diff 경로에서 재기입) · `mode` — 🆕 `"diff"\|"purge"`, 종전엔 `"purge"` 고정) · `reason` — 🆕 `"unresolvable_row_identity"` 추가: `map_key_columns`는 선언했는데 `composite_key_source`가 없는 테이블) · `adopted` · `adopted_row_ids`**. 선언 |
| | 🆕 ⚠️ **`adopted_row_ids`는 생산되지만 읽는 곳이 없다.** `batch.replace_map`일 때만 채워지며, 뜻은 **이 쓰기가 갱신했지만 자기가 선언한 스코프 밖이던 행** — 즉 다른 맵에서 넘겨받은 셀이다(맵 키가 비즈니스 키 밖에 있는 테이블에서만 도달 가능). `deleted_row_ids`에 이탈로 합류한다. 🔴 **`main.py`는 스칼라 `adopted`만 읽는다** — 목록 자체의 소비자는 0이다 |
| | 🆕 **버전 게이트 요약 로깅은 맨 끝**(`version_col` 조회 → `log_version_gate_summary` 호출, 선언). ⚠️ **구 지도는 조회 2383 / 호출 2411로 적어 소스와 *순서가 반대*였다** |
| `create_empty_row(db, table_name)` / `create_empty_rows_batch(db, table_name, count, user_name)` | 빈 행 생성 |
| `delete_row(db,...)` / `delete_rows_batch(db, table_name, row_ids, user_name)` | 행 삭제(+감사·메타 정리) |
| `delete_cell_source_batch(db, table_name, cells, source_name)` | 소스 레이어 일괄 삭제 + 표시값 재계산 |
| `delete_cell_source(db, ...)` | 단일 소스 삭제(배치 위임) |
| `set_cell_manual_priority_batch(db, table_name, updates, source_name, updated_by)` | 수동 Pin 일괄(§크고 복잡 — 표시값 재계산·감사 포함) |
| `set_cell_manual_priority(db, ...)` | 단일 Pin(배치 위임) |
| `get_ontology_mapping()` / `check_needs_rollback(table_name, modified_cols)` | 그래프 보조 — v2 검증+enrichment 승격 적용 결과 캐시 / v2 매핑 인식 rollback 신호(v1 폴백) |

---

#### 🆕 [P6] 복합 키 프리페치 — 「캐시 미스가 *부재의 증명*이 되는 자리」

**어디서**: `_apply_batch_updates_once`(🆕 종전 `apply_batch_updates` 본체)가 조립하고 → `apply_row_update_internal`(인자로 받아 전달)이 실어 나르고 → `_load_metadata_row_cell`이 소비한다. 적중의 전제는 `assemble_composite_business_key`다.

**무엇을**: 조회 **셋** — ① 데이터 테이블 `SELECT … WHERE row_id IN (…) OR business_key_val IN (…)` ② `cell_sources` ③ `cell_overwrites`, 둘 다 그 row_id들에 한정.

🔴 **`prefetched_row_ids = set(all_row_ids)`가 하중을 진다.** 이것은 「어느 id를 조회가 덮었는가」의 스냅샷이고, `_load_metadata_row_cell`은 **그 집합의 원소에 대한 캐시 미스를 「모름」이 아니라 「없음이 증명됨」으로 읽는다**. 그래서 저장된 메타가 없는 셀이 더는 셀당 `SELECT`로 떨어지지 않는다. ⚠️ **루프 중간에 해석되는 행**(중간에 조립된 복합 키·충돌 병합 행)은 **정당하게 이 집합 밖**이고 여전히 조회된다 — 이 집합을 「행이 존재한다」로 대체할 수 없는 이유가 그것이다.

**채점자**: `server/tests/test_composite_key_prefetch_budget.py`가 고정하는 것 — ① 복합 키 200행 갱신 배치의 데이터 테이블 `SELECT` **정확히 1** ② `cell_sources`·`cell_overwrites` 각 **정확히 1**, 총 문장 **< 500**(종전 2,604) ③ 🆕 ✅ **[`4738d84`에서 고쳐졌다 — 「일부러 안 고친 경우」가 아니다]** `_get_or_create_row`가 이제 `ProbedIdentity`를 읽으므로 신규 행 삽입의 `ROWS + 1` 예산은 더는 참이 아니다. **이 항목의 현행 기댓값은 소스에서 확인하라**(`server/tests/test_composite_key_prefetch_budget.py`는 `818c9c0`에서도 손댔다) ④ 충돌 병합 행은 여전히 읽혀야 한다(`cell_sources` select **≥ 2**). 같은 파일이 `replace_map` 스코프 의미론(`report["filters"] == {"base": "A"}` · `report["deleted"] == 7`)도 고정하고, `87a944e`가 **셀별 행 정체성 생존**을 추가했다. 🆕 **`server/tests/test_replace_map_scope_diff.py`**(신설 280줄)가 diff 경로 전용 채점자다.

---

#### ✅ [P3 · `4738d84` 착지, 2026-08-08 등재] **부재의 증명이 정체성 관문 둘로 배선됐다**

> 🔬 **직전 개정이 「미착지」로 표시해 둔 블록이 그것이다.** 예고된 형태와 착지한 형태가 **한 군데 다르다** — 예고는 `_get_or_create_row` 하나만 말했는데, 실제로는 **두 번째 행당 관문(`_find_business_key_conflict`)이 더 있었고 아무도 그것을 등재한 적이 없었다.** 「닫아야 할 관문이 하나」라는 모델로 갔으면 세 왕복 중 하나만 줄었을 것이다.

**HEAD(`34d2518`)에서 참인 것:**
- `_get_or_create_row(db, table_model, update_item, row_cache, table_name, probed_identity=None)` — 인자 **여섯**.
- `_find_business_key_conflict(db, table_model, new_bk_val, row, row_cache, probed_identity=None)` — 신설.
- 두 관문의 유일한 프리페치 인지 호출부는 `apply_row_update_internal`이고, 나머지 호출자는 `None`을 넘겨 종전 질의를 유지한다.
- 부재 증명의 값 타입은 **`ProbedIdentity(row_ids, business_keys)`**이고, `_load_metadata_row_cell`이 읽는 **`prefetched_row_ids`와 다른 물건**이다(위 표의 `ProbedIdentity` 행).

🔬 **측정 근거(소스 docstring이 싣고 있는 값 — 이 문서가 잰 것이 아니다)**: 10만 행 맵 파일에서 전체 301,222 문장 중 **200,000이 이 두 프로브**였고, 새 행 INSERT는 `updated_at`에 SQL 식을 실어 **10만 문장 / 49.3초**로 나가고 있었다.

## 3. `server/parsers/directory_watcher.py` — 파일 인제션

> 🟢 **심볼 실측 완료** — 이 절의 심볼은 **`5609ff0`의 커밋된 blob에 존재함이 확인됐고, 그 뒤 HEAD가 움직인 다음 재대조에서도 동일했다**(워킹트리 아님). 🔴 **라인 번호는 싣지 않는다** — 위치는 `git grep -n "<심볼>" -- <경로>`로 확정하라. 숫자가 남아 있는 곳은 **파일 줄 수**이거나, 이름이 없는 덩어리를 가리키며 측정 sha가 함께 적힌 자리뿐이다.

워크스페이스별 폴더 감시 → 파서 실행 → **HTTP 아닌 직접 DB**(`crud.apply_batch_updates`) 업서트 → 웹서버에 `/internal/events/*` 콜백. 2026-07-25 std parser(무스크립트 표준 파싱)·기동/주기 스윕 통합, **워크스페이스 config.json 폐지**(`5fac5f0`).

> **경로 (2026-07-27):** config·워크스페이스 루트는 전부 `paths.config_path(...)` / `paths.WORKSPACE_DIR` 경유다.
>
>
> 🆕 🔴 **[신설] 「드롭된 컬럼」의 침묵이 없어졌다.** `display_columns` 필터는 **crud가 행을 보기 전에** 돌기 때문에 `crud._warn_undeclared_column_once`가 그 컬럼에 대해 **영원히 발화할 수 없다** — 드롭은 **아무 기록도 남기지 않고**, 파일은 `error_message`가 빈 채 SUCCESS로 보고된다. **드롭 자체가 옳은 경우가 훨씬 흔하다**(그래서 동작은 그대로다). 고칠 수 없었던 것은 그것을 **새로 생긴 컬럼이나 오타 난 컬럼이 아무 데도 안 가는 것과 구분할 수 없다**는 점이다.
> - **`MAX_DROPPED_COLUMNS_REPORTED = 64`** — `crud._MAX_UNDECLARED_WARNED_PER_TABLE`을 그대로 비춘다. **`_dropped_column_announced`** — 🔴 **crud의 레지스트리를 재사용하지 않은 것이 의도다**: 관문이 다르고 config 키가 다르다(**파일당 `display_columns`** vs **셀당 `column_types`**).
> - **`_announce_dropped_columns(t_name, dropped_value_counts, defined_cols, filename, row_count)`** — 크기 배분이 계약이다: **행·셀 단위로는 아무것도 찍지 않고**, (테이블, 컬럼)당 **프로세스 1회** 첫 목격에 WARNING, **파일당 1회** 이름과 건수를 INFO. 누적은 `_send_to_upsert` 안.
> - 🆕 **`IngestionHandler._compose_detail(skipped_no_key, plan, has_rows=True)`, 호출)** — 세 번째 인자가 **0행 파싱의 같은 침묵**을 닫는다: 「한 셀도 저장되지 않음」과 「정상 처리」가 화면에서 구별되지 않았다.
> - 테스트: 🆕 **`tests/test_ingestion_drop_visibility.py`(257줄)**.
>
>
> 이전 재측정(2026-07-30 후속, `a82aa47` blob `5b65ca2`)의 기록: `600b49d`(평탄화 → **제자리 트리 인제션**)으로 2,116 → 2,182줄이 되며 이동이 구간마다 갈렸다(**~238 이전 무이동 · `nested_dirs_enabled` 부근 +4 · `IngestionHandler` 생성자 이후 +6 · `_ingest_directory_tree` 이후 −20 · `_send_to_upsert` 이후 +6**). 그때 이 파일은 **핀 목록 밖이었고** 그래서 그 앞 패스가 놓쳤다. 개명·삭제가 섞인 라운드에서는 **라인이 아니라 함수명으로 Grep하라** — 구 `request_flatten`/`_flatten_directory` 계열 7종은 [§0 묘비](#0-묘비-목록--소스에-존재하지-않는-이름)로 이관됐다.
>
> 이전 재측정(2026-07-29, `b697d34`)의 기록도 남긴다: [M3] 배선으로 2,086 → 2,116이 되며 이동폭이 5구간으로 갈렸고, 그 앞(2026-07-28 `0c6ac1a`)에서는 [Flatten] 도입으로 1,764 → 2,086이 되며 `_classify_lane` 이후가 **+312** 밀렸다. 그 앞선 패스(2026-07-27)에서는 앞판이 `be58210` 실측인 채로 **+53** 밀려 방치돼 있었다. **이 파일은 세 패스 연속으로 커밋 범위와 무관하게 밀렸다** — 커밋 diff를 따라가는 갱신 방식으로는 영원히 안 잡히는 종류의 드리프트다.
>
> 🫀 **진척 비트가 "루프"가 아니라 "작업 단위"에 걸린다** — `process_with_retry`와 `process_archived_file_sync`는 **얇은 래퍼**이고, 각각 `heartbeat.work_claim(HEARTBEAT_NAME, …)`로 감싼 뒤 실제 본체 `_process_with_retry`·`_process_archived_file_sync`에 위임한다. ⚠️ **2026-07-30 정정: 이 문장의 앵커 여섯 개는 같은 절의 표와도 어긋나 있었다**(산문 1055/1321/1066/1333/1070/1338 vs 표 1035/1046/1050/1318/1335) — 두 곳이 같은 함수를 다른 줄로 말하면 **적어도 하나는 틀렸고 어느 쪽인지는 아무도 모른다**. 여섯 전건을 커밋 blob에서 다시 쟀다. 파일 1건의 인제션 전체가 하나의 claim이고, 그 안에서 찍히는 비트가 claim의 진척을 갱신한다([§5 `heartbeat.py`](#5-소형-서버-모듈)의 `DEFAULT_STALL_AFTER_SEC`). **`_` 접두 본체를 직접 부르면 claim 없이 돌아 `/health`가 그 인제션을 보지 못한다.**

- **[P1] heavy 레인**(`4fd8ac9`+`8b0fd03`) — 크기 임계(기본 10MB, `config/ingestion_settings.json` 파일 경계 핫리로드) 초과 파일을 전용 큐/워커로 이관해 observer 디스패치 스레드 HOL 제거. 워크스페이스 내 FIFO는 backlog 카운터+직렬화 락+논블로킹 재라우팅 3중 장치로 보존.
- **[P2] 체크포인트 재개 + 해시 dedup**(`f78ab0a`) — 파일 전체 sha256 시그니처(`sha256:<size>:<digest>`)를 계산해 ① 동일 시그니처 `DONE`이면 skip ② 미완이면 오프셋 재개. 저장소는 신규 테이블 `file_ingestion_checkpoints`([`ingestion_checkpoint.py` §5](#5-소형-서버-모듈)). **오프셋 갱신은 청크 upsert와 같은 트랜잭션** — "커밋된 행 수 == 기록된 오프셋"이 원자적으로 성립. 재개는 시그니처+`total_rows`+`source_kind`+오프셋 범위가 **전부** 일치할 때만. heavy/normal·스윕·관리자 재시도 4경로 동일 동작.
- 🆕⑤ **[Retention] 「파일을 옮기지 않는다」가 config로 선택 가능해졌고, 그러자 사실 하나가 갈 곳을 잃었다**(`ba664c5`) — 신설 `archive_processed_files_enabled()`(config `archive_processed_files`, 기본 **true = 종전 동작**)가 false면 파일은 떨어진 자리에 그대로 남는다. 🔴 **그러면 `err/`라는 폴더가 들고 있던 「이 파일은 실패했다」가 사라진다** → 원장의 `status="FAILED"` 행(`ingestion_checkpoint.record_failure`, 래퍼 `IngestionHandler._record_failure`)이 그 자리를 받는다. 거절은 **호출부가 아니라 이동 프리미티브 두 곳**(`_move_to_err_folder`·`_archive_file`)에 있다 — 신설 **`_refuse_move_by_retention(action) -> bool`**, `_refuse_move_of_foreign_source`와 같은 자리·같은 사유(호출부에 두면 호출자 수만큼 같은 결함이 재발한다). 파일당 영원히 발화하므로 **의도적으로 조용하다**(DEBUG).
- 🆕⑤ **[Tier 1] 재처리 방지가 2단이 됐다**(`ba664c5`) — 신설 **`dedup_by_path_stat_enabled()`**(config `dedup_by_path_stat`, 기본 true. ⚠️ **`dedup_by_signature: false`가 이것까지 같이 끈다** — 그러지 않으면 「전역 강제 재처리 스위치」가 조용히 무력해진다)와 **`IngestionHandler._try_path_stat_skip(abs_path, basename, t_name, file_stat) -> bool`**. 🔴 **적중이 「아무것도 안 함」이 아니다**: 이동이 켜져 있는데 종결난 파일이 **아직 raws/에 있다면 그 이동이 전에 실패한 것**이므로(잠긴 파일·이름 충돌) 여기서 이동을 **재시도한다** — 안 하면 그 파일은, 중첩 인제션에서는 **그 디렉터리 통째로**, 영원히 raws/를 떠나지 못한다. 🔴 **실패 방향도 적어 둔다**: tier 1은 「mtime과 size가 그대로인 채 내용만 바뀐 파일을 다시 읽지 않는 쪽」으로 진다(mtime 보존 복사 도구로 도달 가능) — 파일을 한 번만 쓰는 fab 피드에서는 스윕 39초→1초를 얻는 옳은 거래지만 **판단이지 공짜가 아니다.**
- 🆕⑤ **[Tier 1, hoisted] 35분은 원장이 아니라 원장까지 가는 걸음이었다**(`831ab68`) — 신설 **`IngestionHandler.settle_already_terminal(entries) -> set`**. 🔴 **`_try_path_stat_skip`은 같은 질문을 하고 같은 답을 얻는데, `_process_with_retry` 안에 앉아 있다** — 그래서 파일마다 거기까지 가는 디스패치 전량을 먼저 낸다: 파일당 `SessionLocal()` 하나 + `_snapshot_table_context()`의 `table_config.json` **디스크 재독**(`_handle_event`의 `self.table_name`까지 세면 2회) + `dedup_by_path_stat_enabled()`의 `ingestion_settings.json` 재독. **이 박스 실측: tier-1 적중 1건당 ~92 ms, 22,626파일 트리에 ≈35분 — 그 파일들을 찾아내는 raw walk는 1.0초다. 92 ms 중 원장은 0이다.** `settle_already_terminal`은 그 비용을 **배치당 1회** 낸다(설정 1독 · config 1독 · 세션 1개 · `find_terminal_by_path_stat_batch`). 반환은 **`_handle_event`에 넘기면 안 되는 abs 경로 집합**이고, 걸러지지 않은 파일은 종전 경로 그대로 내려간다 — 오류 시에도 빈 집합(가용성 우선, `_try_path_stat_skip`과 같은 규율).
  - 🆕⑤ **`_settle_terminal_hits(statuses: dict)`** — tier-1 적중이 **지고 있는 이동 재시도**를 배치당 1회 갚는다. `archive_processed_files_enabled()`가 false면 **즉시 반환**하고(보존 모드에서는 갚을 것이 없다 — 35분이 측정된 것이 바로 이 모드라 이 early return이 hot path다), true면 `status == STATUS_FAILED`는 `_move_to_err_folder`, 그 밖은 `_archive_file`. 🔴 **`self._processing_lock` + `processing_files` 클레임을 `_handle_event`와 똑같이 잡는다** — 안 잡으면 이 배치가 watchdog 스레드가 인제션 중인 파일을 **밑에서 빼내 옮길 수 있다**. 적중은 스윕마다 파일 수만큼 일어나므로 **조용하다**(한 줄씩만 남겨도 22,626줄이 5분마다).
  - 🆕⑤ 소비처 **정확히 둘**(둘 다 이미 `os.stat`을 손에 들고 있어 추가 syscall 0): `WorkspaceWatcher.sweep_existing_files`(핸들러별로 묶어 호출) · `IngestionHandler._ingest_directory_tree`(`to_process` 전량 1회). ⚠️ **트리 쪽이 더 아프다** — 스윕의 `_sweep_attempted` 같은 인메모리 캐시가 없고, 파일이 제자리에 남으면 트리가 비지 않아 **주기 스윕마다 다시 트리거되어 재기동당 1회가 아니라 매 주기 영원히** 92 ms를 다시 낸다.
- **[Tree Ingest] 중첩 폴더 = 제자리 인제션, 경로가 데이터의 운반체**(`600b49d` — **구 [Flatten] `0c6ac1a`를 대체**) — raws/ 직속에 **폴더**(임의 깊이)가 떨어지면 트리 정온(quiescence: 1s 간격 동일 스냅샷 2회) 후 **모든 정규 파일을 자기 실제 중첩 위치 그대로** 기존 이벤트 경로(`_handle_event` → 레인 라우팅 → 파서 → 체크포인트/dedup → archives//err/)로 디스패치하고, 그 결과 비게 된 폴더만 **`os.rmdir`로만** 제거한다(내용물이 남은 폴더는 구조적으로 삭제 불가).
  - 🔴 **승격(promotion)을 없앤 것이 이 라운드의 요점이다.** 종전엔 폴더명을 분리자 `~`로 파일명에 **인코딩**하고 파서 쪽에서 정규식으로 다시 **디코딩**했다 — 호출되는 쪽이 이미 전체 경로를 들고 있는데(파서는 경로를 받아 그 뒤에 축약한다) 문자열을 한 번 왕복시킨 것이다. 경로를 그대로 나르면 분리자 문제가 **문제째로** 사라진다: `/`는 폴더명 안에 들어갈 수 없어 경로가 **본래적으로** 모호하지 않은데, 발명한 분리자는 그렇지 않았다(그래서 `__force__` 토큰 중화 루프가 필요했다).
  - 선언이 보는 문자열은 **`relative_source_path`**(POSIX 구분자·상대경로)이고 그것이 `advanced_ingester.extract_path_metadata`의 `subject`다 — 즉 **`filename_rules`가 폴더명까지 매칭한다**([§3-bis](#3-bis-serverparsersadvanced_ingesterpy--선언-검증--경로-메타-추출)).
  - OS 잡파일(Thumbs.db/desktop.ini/.DS_Store/`._*`)은 폐기(`FLATTEN_DISCARD_NAMES` — 상수 이름은 그대로다). 심볼릭 링크·정션으로 raws/ 밖을 가리키는 walk 항목은 `relative_source_path`가 `None`을 돌려주므로 **거부되고 손대지 않는다**(`refused` 카운트).
  - 토글은 **config 키 `flatten_nested_dirs`가 그대로**(기본 true, `ingestion_settings.json` — 트리거당 1회 읽기 핫리로드)인데 **판독 함수는 `nested_dirs_enabled()`로 개명**됐다. 키를 안 바꾼 이유가 소스 주석에 있다: 개명이 운영자의 기존 off 스위치를 조용히 무력화하면 안 된다. 그래서 **함수명과 키명이 의도적으로 어긋나 있다.**
  - 잠긴 파일·실패한 파일은 자기 디렉터리를 살려 두고(`os.rmdir`가 비지 않은 폴더에서 실패하는 것이 곧 "내용물 있는 폴더는 절대 삭제 안 됨" 보증) → 300s 주기 스윕이 재시도.
  - ✅ **[`152d058` 수리 완료] 직전 지도가 🔴로 적어 둔 `NameError`는 사라졌다.** `_ingest_directory_tree` 말미의 `for _mtime, dest in moved:`가 삭제됐고(`moved`는 평탄화 설계의 지역 변수라 이 함수에 없었다), 그 자리에는 **왜 없는지를 적은 주석**이 들어갔다(~895–898). 🔴 **`to_process`로 "고치지" 않은 것이 요점이다** — 그것이 구미 당기는 수리이고 **틀린 수리**다: 그 파일들은 이미 제자리에서 디스패치됐으므로 두 번째 패스는 전건을 이중 처리한다. 주석이 남은 이유가 정확히 그것이다(다음 독자가 친절하게 되살리지 않도록).<br>**이 결함이 양방향에서 보이지 않았던 것도 기록해 둔다**: 파일은 이미 인제션됐고 폴더도 이미 지워진 **뒤에** raise했으며, `_tree_ingest_worker`의 `except`가 그것을 삼켜 *"directory left in place; periodic sweep will retry"*(두 절 다 거짓)를 남겼다. 예외가 밖으로 나가지 않으므로 **`server/tests/test_nested_dir_ingestion.py` 22건은 내내 초록이었다.** 실행 로그로만 보이는 결함이고, 발견은 무관한 라운드를 보던 server-pm의 곁눈질이었다.
- **[M3] 맵 메타 자동 등록 배선**(`b697d34` 범위) — `import map_meta_registrar`. 파일 1건 = 하나의 작업 단위이므로 컬렉터를 `_send_to_upsert` 진입부에서 **파일당 1회 생성**(~1746, 토글 스냅샷이 D1 config 스냅샷과 같은 경계를 공유한다), 청크마다 정규화된 `items`로 bbox만 누적(~1784 — DB 작업 0), **데이터가 커밋된 뒤** 별도 세션으로 부재분만 등록(~1846). 실패는 인제션을 절대 실패시키지 않는다(이미 들어간 데이터). 모듈 계약은 [§5 `map_meta_registrar.py`](#5-소형-서버-모듈).
- 통지 로그 상한 `MAX_NOTIFY_CREATED_LOGS`는 `event_constants.py` 공용 상수 import(~51).
- 테스트: `tests/test_workspace_config_deprecation.py`(21개) · `tests/test_heavy_lane.py`(27개, `hvy_test_*`) · `tests/test_ingestion_checkpoint.py` · **`tests/test_nested_dir_ingestion.py`(22개, `600b49d` 신설 — 구 ~~`tests/test_flatten_nested_dirs.py`~~(15개)를 **삭제하고 교체**했다)** · **`tests/test_filename_rules_declaration.py`(`600b49d` 신설 — `advanced_ingester` 선언 검증·병합 서열)** · **`tests/test_map_meta_registrar.py`(12개, `grep -c "def test_" = 12`)** · 🆕⑤ **`tests/test_sweep_tier1_hoist.py`(신설 693줄, `grep -c "def test_" = 18` @`831ab68`)** · 🆕⑤ **`tests/test_ingestion_ledger_tier1.py`(신설 428줄, 17개)**.

| 시그니처 | 역할 |
|---|---|
| `load_global_table_config() -> dict` | table_config.json 로드 (`paths.config_path` ~84) |
| `warn_legacy_workspace_config(config_path)` | 레거시 config.json 발견 시 경로당 1회 deprecation WARNING |
| `_log_alias_conflict_once` / `warn_invalid_std_parse_once` | 별칭 충돌·std_parse 비-bool 경고 dedup(키별 1회 — QA D5/D6) |
| **`AUTO_PROVISION_EXCLUDED_TABLES = {"wafer_map_metadata"}`** | 워크스페이스 **자동 스캐폴딩 제외** 목록 — 소비는 `_provision_workspaces` 한 곳. 메타 테이블은 사람이 파일을 떨구는 대상이 아니라 [M3]이 코드로 채우는 저장소라, 빈 raws/ 폴더가 생기면 운영자를 오도한다 |
| `DEFAULT_HEAVY_FILE_MB=10` / `INGESTION_SETTINGS_PATH` | [P1] heavy 임계 기본값·설정 파일 경로 — `paths.config_path("ingestion_settings.json")`(`.sample` tracked) |
| `load_ingestion_settings()` / `warn_invalid_heavy_threshold_once` / `get_heavy_threshold_bytes()` | [P1] 임계 로더 — **파일 이벤트(라우팅 결정)당 1회 디스크 읽기**(파일 경계 핫리로드), 양수만 유효·그 외 기본 10MB+1회 경고 |
| `DEFAULT_DEDUP_BY_SIGNATURE=True` / `DEFAULT_RESUME_FROM_CHECKPOINT=True` / `_bool_setting(key, default)` | [P2] dedup·재개 기본값과 설정 판독기(같은 `ingestion_settings.json`) |
| `dedup_by_signature_enabled()` / `resume_from_checkpoint_enabled()` | [P2] 게이트 — `dedup_by_signature: false`가 **전역 강제 재처리 스위치**(파일명 `__force__`와 관리자 재시도가 나머지 2경로) |
| 🆕⑤ **`dedup_by_path_stat_enabled()`** (+`DEFAULT_DEDUP_BY_PATH_STAT = True`) | **[Tier 1] 게이트** — `(경로, mtime, size)` 일치만으로 **해시 없이** 스킵할지. 🔴 **`dedup_by_signature_enabled()`가 false면 무조건 false를 반환한다**(전역 강제 재처리 스위치가 조용히 무력해지지 않도록 — 게이트가 게이트를 삼키는 것이 의도) |
| 🆕⑤ **`archive_processed_files_enabled()`** (+`DEFAULT_ARCHIVE_PROCESSED_FILES = True`) | **[Retention] 게이트** — 처리된 파일을 `archives/`·`err/`로 **옮길지**. false면 파일은 제자리에 남고 재처리 방지는 전적으로 원장(tier 1 + tier 2)이 맡는다 |
| **`DEFAULT_FLATTEN_NESTED_DIRS=True` / `FLATTEN_STABILITY_INTERVAL_SECONDS=1.0` / `FLATTEN_STABILITY_MAX_WAIT_SECONDS=600` / `FLATTEN_DISCARD_NAMES`** | **[Tree Ingest `600b49d`]** 상수군 — **`FLATTEN_SEP`은 삭제**됐다([§0](#0-묘비-목록--소스에-존재하지-않는-이름)): 승격이 없으니 발명한 구분자도 없고 `__force__` 토큰 조작 차단도 필요 없다. 남은 셋의 의미는 그대로 — 정온 폴 1s·최대 대기 600s(초과 시 존치+스윕 재시도)·잡파일 3종+`._*`. ⚠️ **상수 4개가 `FLATTEN_`/`_FLATTEN_` 접두어를 유지하는 것은 개명 비용을 안 낸 것**이고(config 키와 같은 이유) 그래서 접두어 grep은 여전히 히트한다 — 삭제 검사는 [§0 ⑥](#0-묘비-목록--소스에-존재하지-않는-이름)처럼 **이름 전건**으로 하라 |
| **`nested_dirs_enabled()`** | [Tree Ingest] 토글 판독(기본 true) — 트리거(디렉토리 이벤트/스윕)당 1회 읽기, 핫리로드는 "다음 폴더부터". ⚠️ **읽는 config 키는 여전히 `flatten_nested_dirs`**다(개명이 운영자의 off 스위치를 무력화하지 않게 — 소스 주석 ~239–240·~261). 구 이름 ~~`flatten_nested_dirs_enabled`~~ |
| `get_workspace_serial_lock(workspace_path) -> Lock` | [P1] **워크스페이스 직렬화 락 — 모듈 레벨 경로 키 레지스트리**(핸들러 복수여도 공유). heavy 워커/인라인/run_watcher 재처리 폴러가 공용 |
| `class HeavyIngestionLane` — `submit/_ensure_running/_worker_loop/stop` | [P1] FIFO `queue.Queue` + 데몬 워커 스레드 `watcher-heavy-lane` **1개**(첫 제출 시 지연 기동). WorkspaceWatcher가 1개 생성해 전 핸들러 주입. heavy끼리는 직렬(escalation §6-3) |
| `find_workspace_alias(folder_name, table_config) -> str\|None` | 폴더명↔`workspace_name` 명시 별칭 매칭 — 섀도잉·중복 선언 별칭은 무효+ERROR 1회(QA D3) |
| `resolve_workspace_root(base_dir, table_name, table_config) -> str` | 테이블→워크스페이스 루트 **역조회 공용 함수**(별칭 포함) — 결과 기반 경로 검사(base 직속 자식만, 드라이브 상대경로 탈출 차단, QA D2). main.py `retry-failed`·run_watcher 폴러가 사용 |
| `resolve_workspace_table(folder_name, table_config) -> str\|None` | 폴더→테이블 해석: 별칭 > 폴더명 규약 |
| `_register_legacy_import_shim()` | 구식 사용자 파이프라인 스크립트의 import 호환 shim |
| `class IngestionHandler(FileSystemEventHandler)` | **워크스페이스 1개 담당 핸들러** — 생성자(~504) 말단 kwargs `on_ingestion_state_callback`/`heavy_lane`(기본 None=종전 인라인 경로, 하위호환). **[Tree Ingest] `_ingesting_dirs` 집합(~533, `_processing_lock` 보호)** — 같은 트리에 이벤트+스윕이 겹쳐도 인제션 1회. 구 이름 ~~`_flattening_dirs`~~ |
| ├ `_load_legacy_config()` | [deprecated] 레거시 워크스페이스 config.json 파싱(이것만 캐시) |
| ├ `_resolve_table_name(global_cfg)` | 테이블명 해석: 글로벌 `workspace_name` 별칭 > 레거시 `table_name` > 폴더명 규약 |
| ├ `_snapshot_table_context() -> (t_name, table_info)` | **파일당 1회 config 스냅샷**(QA D1) |
| ├ `_std_parse_enabled_for(t_name, table_info) -> bool` | std_parse 게이트: 글로벌(JSON bool만 유효) > 레거시 폴백 > 기본 true |
| ├ `table_name` / `std_parse_enabled` / `errors_path` (property) | 즉석 해석 래퍼 — **글로벌 조회 비캐시**(핫리로드 반영) |
| ├ `on_created/on_moved` | 이벤트 수신 — **[Tree Ingest] `is_directory`면 `request_tree_ingest`로 분기**(observer `recursive=False`라 raws/ 직속 자식만 발화), 파일이면 `_handle_event` |
| ├ `_handle_event(file_path)` | 파일 처리 진입(processing_files check-then-add 락 원자화) → [P1] `_route_and_process` 위임 |
| ├ **`raws_path` (property) / `request_tree_ingest(dir_path)`** | **[Tree Ingest] 진입점** — raws/ 직속 자식만(결과 기반 경로 검사), `nested_dirs_enabled()` 게이트, `_ingesting_dirs` 멱등 가드 후 **전용 단명 데몬 스레드**(`tree-ingest-<dir>`)로 정온 대기(observer 디스패치 스레드 비차단 — P1 HOL 규율과 동일). **반환은 시작했으면 Thread, 아니면 None** — 테스트가 join할 수 있게 |
| ├ `_tree_ingest_worker(abs_dir, key)` | 예외 격리 래퍼 — 실패 시 폴더 존치 + ERROR(주기 스윕이 재시도), finally에서 가드 해제. ✅ **`152d058` 이전에는 이 except가 `_ingest_directory_tree` 말미의 `NameError`를 매번 삼켰다**(위 [Tree Ingest] 항목의 ✅). 격리 래퍼의 값과 대가가 같은 자리에 있다 — 워커를 살렸고, **그 대가로 결함을 8시간 감췄다** |
| ├ `_snapshot_tree(abs_dir)` (static) / `_wait_tree_quiescent(abs_dir)` | 트리 스냅샷 `{(kind, relpath): (size, mtime)}` — 스윕의 (mtime,size) 시그니처를 트리로 일반화, stat 불가 파일은 never-equal 마커 / **1s 간격 동일 스냅샷 2회 = 정온**(복사 중 폴더를 반쯤 인제션하지 않는 근거), 최대 600s 초과·소멸 시 False |
| ├ `_is_discardable_system_file(name)` | OS 잡파일 판정(Thumbs.db/desktop.ini/.DS_Store/`._*`). 짝이던 ~~`_sanitize_flatten_component`~~는 삭제 — 정화할 파일명 성분 자체가 없어졌다 |
| ├ **`relative_source_path(abs_path, root) -> str\|None`** (static) | **[Tree Ingest] 선언이 보는 문자열의 단일 정의** — `root` 기준 상대경로, **전 플랫폼 `/` 구분자**. `None`이면 `root` 밖(정션·심링크·다른 드라이브). 두 결정이 docstring에 박혀 있다: **절대경로가 아닌 이유**(선언에 개발 머신의 디렉터리 배치가 섞여 환경 간 매칭이 깨진다) · **`/`로 정규화하는 이유**(Windows `os.sep`는 역슬래시라 JSON 정규식에 4자로 써야 한다). 격리는 **결과 기반**(rejoin해서 같은 파일이어야 통과 — 문자 블랙리스트는 `C:foo`를 놓치고 `..foo`를 과도 거부한다). 소비 3곳: `_ingest_directory_tree`의 walk 필터(~841) · `_send_to_upsert`의 `rel_path` 동봉(~1084) · `is_managed_source` |
| ├ **`_ingest_directory_tree(abs_dir)`** | **[Tree Ingest] 본체** — 정온 대기 → walk 수집(mtime 오름차순, 스윕과 같은 순서 규칙 / 잡파일 별도 / `relative_source_path is None`이면 **거부·무접촉**) → 잡파일 먼저 `os.remove`(Thumbs.db만 남은 폴더도 비워질 수 있게) → **파일을 원 위치 그대로 `_handle_event`로 디스패치**(승격 없음) → 빈 폴더 bottom-up **`os.rmdir`만** → 완료/미완 로그. ✅ **말미의 사문 디스패치 루프는 `152d058`에서 삭제**(자리에 사유 주석 — 위치는 `git grep -n "double-process"`로 확정, 구 표기 ~895–898은 `831ab68`에서 낡았다).<br>🆕⑤ **[`831ab68`] `to_process`가 3-튜플이 됐다** — `(st.st_mtime, fp, (mtime_ns_to_datetime(st.st_mtime_ns), int(st.st_size)))`. 세 번째 항은 walk가 이미 뜬 `st`에서 뽑은 tier-1 키다. 정렬·잡파일 제거 후 **디스패치 루프 앞에서** `settle_already_terminal([(abspath, fstat), …])`을 한 번 부르고, 반환된 집합에 든 파일은 `_handle_event`를 건너뛴다. 로그의 카운트도 `dispatched` + `N already concluded (tier-1)` 둘로 갈렸다 |
| ├ `_classify_lane(abs_path)` / `_heavy_backlog_nonzero()` | [P1] 이벤트 시점 `os.stat` 1회 크기 분류 / 워크스페이스 heavy backlog 잔여 확인 |
| ├ `_route_and_process(abs_path, uploader) -> bool` | [P1] **레인 라우팅 본체** — heavy(크기)·backlog(>0이면 크기 무관 큐 후미=FIFO 보존)·인라인은 직렬화 락 **논블로킹 try-acquire**(실패 시 큐 후미 재라우팅 — HOL 방지+순서 보존 동시 만족) |
| ├ `_submit_to_heavy_lane(abs_path, uploader, lane, size_bytes)` | [P1] 큐 제출 — QUEUED 통지를 **submit 이전 선발신**(드릴 결함1: 즉시 픽업 역전 경합 제거), submit 실패 시 FINISHED 정리 통지 후 인라인 폴백. `lane`은 분류 실값(재라우팅 소형은 "normal" — QA F4) |
| ├ `_run_lane_job(...)` / `_notify_ingestion_state(state)` | [P1] heavy 워커 잡 본체(직렬화 락 획득→`process_with_retry`→finally 정리) / 상태 push 콜백 래퍼 |
| ├ **`process_with_retry(file_path, uploader, retries=3, delay=1.0)`** | **`heartbeat.work_claim` 래퍼일 뿐** — 실제 처리는 `_process_with_retry` |
| ├ `_process_with_retry(...)` | 처리 본체 — 스냅샷→파싱→[P2] 시그니처 계산→dedup skip→`_plan_checkpoint`→`_send_to_upsert`→`_finalize_checkpoint`→아카이브/에러 이동, 재시도 |
| ├ `_compose_detail(skipped_no_key, plan)` (staticmethod) | [P2] 완료 통지 `detail` 조립 — 키 결측 스킵 수 + 재개/재시작 사유 |
| ├ `_try_dedup_skip(file_path, basename, t_name, signature, file_stat=None) -> bool` | **[P2 / tier 2]** 동일 시그니처 `DONE`이면 skip — **무음 skip 금지**: WARNING + archive + `FileIngestionLog(status="SKIPPED")` + 콜백 status는 `"SUCCESS"`(수신부가 비-SUCCESS를 실패로 렌더링하므로 오표기 방지) + 사유 detail. 🆕⑤ `file_stat` 인자가 붙었다 — 적중 시 `ingestion_checkpoint.adopt_new_location`으로 **새 경로를 원장에 갱신**해 다음 스윕의 tier 1이 이 파일을 알아보게 한다 |
| ├ 🆕⑤ **`_try_path_stat_skip(abs_path, basename, t_name, file_stat) -> bool`** | **[Tier 1, 단건]** 같은 경로·같은 `(mtime, size)`로 이미 결론이 난 파일을 **해시 없이** 건너뛴다. `_process_with_retry` 안, tier 2보다 **앞**. 🔴 **tier 2와 정반대로 조용하다**(적중이 스윕마다 파일 수만큼 일어나므로 — 내구성 있는 기록은 이 스킵이 찾아낸 **바로 그 원장 행**이다). 🔴 **적중이 no-op이 아니다** — 이동이 켜져 있고 파일이 아직 raws/에 있으면 `status`에 따라 `_move_to_err_folder`/`_archive_file`를 **재시도한다**(전에 실패한 이동을 영영 포기하면 파일이, 중첩 인제션에서는 디렉터리째로 갇힌다). `__force__`와 `dedup_by_path_stat_enabled()` 게이트가 먼저 |
| ├ 🆕⑤ **`settle_already_terminal(entries) -> set`** / **`_settle_terminal_hits(statuses: dict)`** | **[Tier 1, hoisted+batched]** 같은 질문을 **파일 묶음에 한 번**. 상세는 위 [Tier 1, hoisted] 항목 — 반환은 **디스패치하면 안 되는 abs 경로 집합**, 실패·비활성은 전부 **빈 집합**(가용성 우선). `_settle_terminal_hits`가 적중이 지고 있는 이동 재시도를 `_processing_lock`/`processing_files` 클레임 아래 갚는다 |
| ├ 🆕⑤ **`_record_failure(t_name, signature, basename, filepath, error_msg, file_stat)`** | 실패를 **원장에 종결 상태로** 남기는 래퍼(`ingestion_checkpoint.record_failure`). 기록 자체가 실패해도 인제션을 실패시키지 않는다(WARNING 후 다음 스윕이 재시도). 내용을 못 읽어 시그니처가 없는 파일은 `stat_identity_signature`가 키를 대신 만든다 |
| ├ 🆕⑤ **`_refuse_move_by_retention(action) -> bool`** | **[Retention]** 운영자가 「파일은 떨어진 자리에 있어야 한다」를 선언했을 때 이동을 거절한다. **`_refuse_move_of_foreign_source`와 같은 두 프리미티브에 걸린다** — 호출부(성공 archive · dedup-skip archive · err 이동 · 재시도 경로)에 두면 호출자 수만큼 같은 결함이 재발한다. 조용하다(DEBUG): 이것은 예외가 아니라 **설정된 동작**이다 |
| ├ `_plan_checkpoint(...)` / `_finalize_checkpoint(plan, processed_rows)` | [P2] `ingestion_checkpoint.plan_ingestion` 게이트 래퍼(실패 시 `CheckpointPlan.disabled(note=...)`) / `mark_done` — 실패 시 "dedup will not apply" 경고 |
| ├ `_log_ingestion_record(...)` / `_log_ingestion_failure/success(..., t_name=None)` | FileIngestionLog 기록(직접 DB, 스냅샷 테이블명). `error_message`는 SUCCESS/SKIPPED에서 **detail 슬롯**으로 겸용 |
| ├ `_retry_should_restart(t_name, signature) -> bool` | [P2] 재시도 시 완료 체크포인트가 있으면 처음부터 재시작 판정 |
| ├ **`process_archived_file_sync(log_entry, db, uploader)`** | 어드민 재처리 경로. **이것도 `work_claim` 래퍼**이고 본체는 `_process_archived_file_sync` — 스냅샷 진입점, 내부에서 락 안 잡음. [P2] 체크포인트는 태우되 **dedup skip은 미적용**(재시도는 명시적 의도) |
| ├ **`_unique_dest(dest_dir, filename, limit=1000)`** (static) | **[Tree Ingest 신설] 무덮어쓰기 목적지 선정의 단일 구현** — 원명 우선, 충돌 시 접미 번호, `limit` 초과면 `None`. 구 ~~`_resolve_flatten_dest`~~의 역할 중 **살아남은 절반**이고(상대경로 접두 조립은 승격이 없어져 사라졌다) 소비는 `_move_to_err_folder`·`_archive_file` 둘 — **같은 basename이 두 폴더에서 올라와도 archives/에서 서로를 덮지 않는 근거** |
| ├ **`is_managed_source(file_path)` / `_refuse_move_of_foreign_source(file_path, action)`** | **[Tree Ingest 신설] 워크스페이스 소유 파일과 외부 파일을 가른다** — `relative_source_path(file_path, raws_root) is not None`이 소유 판정이고, 외부 소스는 **인제션은 되지만 절대 이동되지 않는다**(archives//err/로 옮기면 남의 트리를 건드린다). 실패도 마찬가지라 재인제션은 dedup이 조용히 흡수한다 |
| ├ `_move_to_err_folder` / `_archive_file` | 파일 이동 — 둘 다 `_unique_dest` 경유, 외부 소스는 `_refuse_move_of_foreign_source`가, 🆕⑤ 보존 모드는 `_refuse_move_by_retention`이 먼저 막는다(**가드 둘 다 이 두 함수 안에 있고 호출부에는 없다**) |
| ├ `_discover_and_execute_pipeline(file_path, meta=None) -> list[dict]\|None` | 사용자 파이프라인 스크립트(pipeline_*.py) 탐색·실행 |
| ├ `_resolve_rows(file_path, t_name=None, table_info=None, ...)` | **파서 라우팅** — 파이프라인 우선, 없으면 std parser 폴백(스냅샷 인자 전파). `source_kind`(`"std"` / `"pipeline:<Class>"`)의 산출처 |
| ├ `_try_std_parse(file_path, t_name, table_info)` / `_extract_user_from_filename(filename)` | std_parser 호출 래퍼(게이트·에러 처리) / 파일명에서 업로더 유도 |
| └ `_send_to_upsert(rows, uploader, filename, total_rows, t_name=None, table_info=None, checkpoint=None)` | list 또는 스트리밍 이터레이터 → 청킹 → `crud.apply_batch_updates` 직접 호출 + 진행률 콜백. [P2] `checkpoint`로 `resume_from` 스킵·오프셋 초과 경고·**청크마다 `record_chunk_progress`(같은 트랜잭션)**, created_logs는 `MAX_NOTIFY_CREATED_LOGS` 잔여분만 누적. **[Tree Ingest] 파이프라인 meta에 `rel_path`(=`relative_source_path`)를 실어 보낸다(~1084)** — 그래서 `filename_rules`가 폴더명을 본다. **[M3] `MapMetaCollector` 생성 → 청크별 `collect` → 커밋 후 별도 세션 `flush`** |
| `class WorkspaceWatcher` | 전체 워크스페이스 관리자 — [P1] `HeavyIngestionLane` 1개 생성·전 핸들러 주입(생성자 kwargs) + `on_ingestion_state_callback` 배선 |
| ├ `_provision_workspaces()` | 폴더 스캐폴딩 — **config.json 신설 중단**(폴더만 보충), `workspace_name` 별칭 폴더명 지원(unsafe 별칭 무시), `AUTO_PROVISION_EXCLUDED_TABLES` 제외 |
| ├ `_register_workspace(raws_root, table_config)` | 핸들러 등록(+`handlers_by_raw_path` 레지스트리, `heavy_lane` 주입) — 레거시 config 발견 시 1회 경고(QA D4) |
| ├ `discover_and_watch()` / `sync_new_workspaces()` | 기동 스캔·신규 워크스페이스 동기화(신규 raws는 등록 직후 스윕) |
| ├ `sweep_existing_files(raw_paths=None) -> int` / `_sweep_safely` / `sweep_existing_files_async(...)` | **[Startup Sweep]** raws/ 직속 기존 파일을 mtime 오름차순으로 `_handle_event` 경로 재사용 처리 — [P1] 스윕도 자동으로 heavy 라우팅을 탐. (mtime,size) 시그니처(`_sweep_attempted`)로 무한 재시도 차단, err/ 형제 폴더 제외. **[Tree Ingest] raws/ 직속 디렉토리는 스윕 후보가 아니라 트리 인제션 트리거** — `handler.request_tree_ingest(fp)`로 넘긴다(다운타임 중 떨어진 폴더·유실 이벤트의 안전망).<br>🆕⑤ **[`831ab68`] 후보 튜플이 넓어졌고 반환의 뜻이 바뀌었다.** 후보는 이제 **`(mtime, file_path, abs_path, handler, sweep_signature, tier1_stat)`** 6원소다 — 마지막 항은 **이미 뜬 `st`에서 뽑은** `(mtime_ns_to_datetime(st.st_mtime_ns), int(st.st_size))`로, 한 디스패치 더 들어가서 같은 질문을 하지 않으려는 것이 전부다. 정렬 후 **핸들러별로 묶어 `handler.settle_already_terminal(entries)`**를 부르고(각 호출은 try/except — 실패하면 그 핸들러 몫은 종전대로 개별 디스패치), `_stop_event`가 서면 그 루프도 끊는다. 🔴 **반환값은 이제 「`_handle_event`로 디스패치한 파일 수」이고 tier 1이 여기서 종결한 파일은 빠진다** — 종전엔 "후보 = 처리"였다. `_sweep_attempted`는 **cleared 여부와 무관하게** 갱신된다. 로그 한 줄이 `후보 / 이미 종결(tier-1, batched) / 디스패치` 셋을 함께 남긴다 |
| ├ `_periodic_sweep_loop()` / `_ensure_periodic_sweep_running()` | 이벤트 유실 안전망 — 300s 주기 잔류 재스캔 데몬(**트리 인제션 재시도 경로이기도 하다** — 잠긴 파일·미정온 트리) |
| └ `_ensure_observer_running()` / `stop()` / `start(blocking)` | watchdog Observer 수명 관리 — start()가 observer 기동 후 기동 스윕+주기 스윕 킥, stop()이 heavy 레인도 정지 |

### 3-bis. `server/parsers/advanced_ingester.py` — 선언 검증 + 경로 메타 추출

**508줄** (`600b49d`로 122 → +386). ⚠️ **이 파일은 종전 지도에 엔트리가 없었다** — 122줄짜리 정규식 파서 헬퍼였을 때는 §6 한줄 요약에도 없었고, 그동안 **선언 스키마 검증기 + 경로 메타 추출기 + 3원 병합 서열의 소유자**가 됐다. [§3](#3-serverparsersdirectory_watcherpy--파일-인제션)의 트리 인제션이 나르는 경로를 **소비하는 쪽**이 여기다.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `ALLOWED_RULE_KEYS` / `ALLOWED_CAST_TYPES` | **선언될 수 있는 것의 단일 원천** — 목록 밖 키는 무시가 아니라 **이유를 대며 거부**(`ontology_config._unknown_keys`와 같은 규율: 오타가 그것이 만들려던 선언을 조용히 끄면 안 된다) | ~15/16 |
| **`REASON_NO_MATCH` · `REASON_AMBIGUOUS` · `REASON_CAST_FAILED` · `REASON_FILE_OVERRIDES_PATH` · `REASON_PATH_VALUE_DISCARDED`** | **"미상 ≠ 빈칸"의 어휘 5종.** 선언했는데 못 뽑은 것은 **전부 이름으로 보고**되고 파일당 카운트된다. `REASON_AMBIGUOUS`는 `enrichment_analysis.CLS_AMBIGUOUS`/`enrichment_candidates.REASON_AMBIGUOUS`와 **같은 단어를 의도적으로 재사용**한다(한 상태에 한 어휘 — 두 번째 동의어를 만들지 않는다) | ~26/32/35/41/52 |
| `class RuleDeclarationError(ValueError)` | 규칙 선언이 잘못됐다 — **로드 시점**에 raise한다(파싱 시점의 `IndexError`가 아니라). 캡처 그룹 없는 정규식은 선언 오류이고, 그걸 `match.group(1)`까지 흘려보내면 운영자의 오타가 **프로그램 크래시**가 된다 | ~55 |
| `_validate_rules(raw_rules, where) -> (rules, errors)` | 세 규칙 계열을 같은 스키마로 검증. 반환이 **에러 리스트**인 이유는 로드 1회에 전건을 보고하기 위해서다(재기동 1회에 오류 1개씩이 아니라) | ~64 |
| `class AdvancedIngester` — `__init__(config_path, server_url=…)` | 세 계열(`rules`·`header_rules`·`filename_rules`)을 검증하고 **겹침을 생성자에서 1회 계산**한다: `_row_overlap` · `_header_overlap` · **`_fill_merge_cols`**(~203 — 함수가 아니라 **집합 속성**이다. 둘 이상의 원천이 만들 수 있는 컬럼만 담고 **정상 상황에서는 빈 집합**이라, 그것이 `_merge_row`의 행당 비용을 오늘 수준으로 묶는 장치다) | ~150/160 |
| `extract_header_metadata(lines)` | 파일 머리 주석/헤더에서 선언 컬럼 추출 | ~254 |
| **`extract_path_metadata(subject, issues=None) -> (data, refusal)`** | **[Tree Ingest의 소비 지점]** `subject`는 인제션 루트 기준 **POSIX 상대경로**(= `directory_watcher.relative_source_path`의 출력, 예 `"batchA/sub2/x.csv"`). 맨 파일명은 디렉터리 0개인 퇴화 사례이고 **그래서 선언 키가 여전히 `filename_rules`다** — 두 채널이 아니라 한 메커니즘·한 subject다. `finditer`로 **구별되는 값 전량**을 모아 2개 이상이면 `REASON_AMBIGUOUS`로 **거부**한다(첫 히트를 고르면 그것은 데이터 컬럼에 기록된 추측이다). `required: true`가 못 뽑히면 `refusal`을 돌려주고 **그 파일은 0행**이다. ⚠️ **`^` 앵커 패턴은 파일명→경로 확장에서 살아남지 못한다**(값 형태·위치 무관 패턴은 살아남는다) — docstring이 명시 | ~269 |
| `parse_line(line)` | 행 단위 정규식 추출. ⚠️ **선언된 모든 컬럼을 매 행에 낸다**(미매치는 `default`, 보통 `None`) — 그 성질이 아래 병합의 fill 패스가 필요한 이유다 | ~345 |
| 🔴 **`_merge_row(header_metadata, filename_data, row_data)`** | **서열은 판정(ruling)이고 dict 순서의 부산물이 아니다** — 사용자 결정 2026-07-30 「파일이 정본」: **`filename_data < header_metadata < row_data`.** 경로는 셋 중 **가장 약하다**(파일 안에 쓰인 값은 그 파일 자신의 주장이고, 폴더명은 누가 파일을 옮기면 바뀌는 외부 문맥이다). 그리고 **원천은 실제로 값을 나를 때만 이긴다** — 평범한 `{**a, **b, **c}`는 그 컬럼에 **침묵한** 행의 `None`이 경로/헤더 값을 덮어써 판정의 fill 절반이 아예 일어나지 않는다. 그래서 `_fill_merge_cols`만 도는 fill 패스가 **내림차순 서열**로 메꾼다(헤더 → 경로). ⚠️ **이 셋의 순서를 새 판정 없이 바꾸지 말 것** — `filename_data`를 `header_metadata` 뒤로 옮기면 파일의 **보관 위치**가 파일 **내용**을 덮는다. `test_merge_order_is_the_declared_ruling`이 양방향으로 고정 | ~364 |
| **`process_file(file_path, rel_path=None, issues=None)`** | 파일 1건 → 행 리스트. **`rel_path`가 트리 인제션의 운반체**이고 생략하면 `basename(file_path)` 폴백이라 **기존 호출자는 무변경**이다. `refusal`이면 0행 + 경고. `_header_overlap`에서 헤더가 경로 값을 눌렀으면 `REASON_PATH_VALUE_DISCARDED`로 **센다**(헤더가 이기는 것은 판정 자체라 경고할 일이 아니지만, 운영자가 선언한 폴더 규칙이 값을 만들고도 **효과가 없었다**는 사실은 침묵하면 "규칙이 매치 안 됐다"로 읽힌다). `_row_overlap` 불일치는 행마다 기록하지 않고 **컬럼당 카운트**해 메모리를 O(overlap)으로 묶는다 | ~416 |

### 🆕 3-ter. `server/parsers/html_topology_parser.py` (**768줄**, `ed9cfdb` 638에서 **+130**) — HTML 표 → 그래프/행렬

**모듈 레벨 심볼은 하나도 안 움직였다**: `class TableNode`(**7**) · `class TableEdge`(**43**) · `class HTMLTableGraphParser`(**73**) · `class HTMLMatrixTableParser`(**516**) · `parse_matrix_to_records`(**524**). **+130 전부가 `parse_matrix_to_records` 본체 안**이다.

> 🔴 **[신설 ①] 격자 원점을 *두 번* 유도하고 일치할 때만 채택한다.**
> - **위 기준**: `_ruler_row(r)`(**568**)가 X축 눈금 행을 **모양으로** 알아본다(숫자를 들고 비교하지 않는다). 앵커 `top_anchor, top_ticks`(**621**).
> - **아래 기준**: Y 눈금의 최상단 라벨 행 − 1 (`bottom_anchor` **630**).
> - 🔴 **두 유도의 맹점이 문서의 반대쪽 끝에 있으므로 *일치는 진짜 증거*이고 불일치는 「이 파서가 이해하는 모양이 아니다」는 뜻이다.** 채택은 **659**(`x_row_idx = top_anchor`), 사유 블록은 **592**.
> - ⚠️ **불일치면 이름 붙은 사유로 *거절*하고 0행을 낸다** — X·Y가 비즈니스 키이므로 **그럴듯해 보이는 틀린 답은 맵의 모든 셀을 존재하지 않는 좌표에 등록**한다.
>
> 🔴 **[신설 ②] 헤더 판정이 어휘가 아니라 *위치*가 됐다**(**697**): `node.is_header = bool(node.value) and node.row_range[1] < x_row_idx and not _is_unmerged(node)`.
> - `_is_unmerged(n)`(**558**)이 실측을 문장으로 들고 있다: **아카이브 19파일 · 헤더 모양 4종 전건에서 모든 코너와 축 눈금은 1×1이고 모든 헤더 밴드 셀은 병합돼 있다 — 양방향 예외 0.**
> - 🔴 **구 `float()`-거부 검사는 실 아카이브에서 *양방향으로* 틀렸다**: 숫자형 `BDIE/LOT/12312`가 헤더 집합에서 빠져 **맵 키가 조용히 `"CDIE"`가 됐고**, 격자 안의 BIN 문자가 헤더로 승격돼 **유령 키 `F_AAA`**로 새어 나갔다.
> - ✅ **`_default_is_header`는 손대지 않았다** — `extract_semantic_tuples`와 호출자가 넘기는 술어는 동작이 그대로다.
> - 테스트: 🆕 **`server/tests/test_html_matrix_header_predicate.py`(429줄)** — 픽스처가 그 19파일 4종의 **기하를 재구성**한다.

---

## 4. `server/chain_ingestion_worker.py` — 체인 워커

outbox LISTEN/NOTIFY 소비 → 체인 룰 매칭 → 맵퍼 실행 → 파생 테이블 업서트 → `/internal/events/broadcast`로 WS 위임. 지연 SLO 100ms(2026-07-25 F1–F3 + warmup 완료).

> 🆕🆕 🔴 **[2026-08-11] 파일이 다시 자랐다: 1,198 → 1,294줄** @`7097a67`. **아래 블록의 라인 값은 `34d2518` 기준이고 이번 패스가 재측정하지 않았다 — 위치는 함수명으로 Grep하라.** 이번 라운드가 더한 것은 **연쇄 그래프 검증** 둘이다(정의 실측 @`7097a67`): **`_rule_accepts_event(rule, event) -> bool`(328)** · **`_validate_chain_cascade_graph(rules)`(335)**. 🔴 **DT/core 체인이 규칙을 사슬로 엮으면서**(`dt_log → wafer_map_metadata → dt_inventory → dt_map`/`core_usage_map`) **어느 규칙이 어느 이벤트를 받는지가 더는 자명하지 않다** — 그 판정을 이름 붙인 자리다([§5-G](#5-g--dtcore-프레임-유도-체인-2026-08-11-신설-등재)). 채점자 `server/tests/test_chain_cascade.py`.
>
> 🆕 🔴 **[2026-08-08 재측정 · `34d2518`] 아래 표의 「라인」 열은 전부 낡았다 — 이 블록이 그것을 대체한다.** 파일은 **1,086 → 1,198줄**이고 밀림은 **균일하지 않다**(조각): 파일 앞머리는 **+4**, `_group_target_tables` 이후는 **+55**, `process_pending_groups` 이후는 **+96**이다. 🔴 **일괄 가산으로 고치지 마라 — 세 구간의 값이 다르다.** 전건 실측(정의 기준, 호출부 아님):
>
> `import enrichment_candidates` **42** · `class OutboxListener` **46** · 🆕 **`import outbox_expand` 34** · `import internal_event_client` **132** / `API_BASE_URL` **134** · `post_event_async` **143** · purge 상수 **186–189** / `purge_expired_outbox_sync` **192** · `_stamp_broadcast_at_sync` **232** · `_dispatch_broadcasts` **253** · `load_chain_rules` **297** · `_mapper_accepts_rule` **326** · `execute_custom_mapper` **337** · `_group_target_tables` **355** · `process_chain_transaction_group` **378** · `reload_worker_process_cache` **655** · `warmup_worker` **671** · `process_pending_groups` **719** · `sweep_undelivered_broadcasts` **877** · `start_chain_ingestion_worker` **976**.
> 함수 **안**의 호출부 — `MapMetaCollector(` **510** · `AutoConfirmCollector(` **529** · broadcast 구성부 **594** · `startup_lines("Chain Worker")` **984** · `heartbeat.beat("chain")` **1027** · `CONTROL_EVENT_TYPES` 멤버십 **1122**.
>
> 🆕 🔴 **[`528dfcb`] 이 워커가 outbox 페이로드를 더는 그대로 먹지 않는다.** `process_chain_transaction_group`이 맵퍼에 먹이기 전에 **`outbox_expand.expand_events(db, valid_events)`(397)** 를 통과시키고, 키는 **`outbox_expand.event_key(e)`(426·438)** 다. 실패한 접힌 청크는 **`outbox_expand.reexpand_collapsed_event(...)`(817)** 로 per-row로 되펴진다. 그리고 배치 예산이 이벤트 수가 아니라 **행 수**로 매겨진다 — **`trim_events_to_row_budget(normalized_events, OUTBOX_GROUP_MAX_ROWS)`(1163)**([§6 `event_constants.py`](#6-기타-서버-모듈-한줄-요약)). 🔴 **구 `LIMIT 20000`을 이벤트로 세면 한 배치가 2천만 행을 끌어온다.**
>
> ✅ **앵커 재측정 (2026-08-04, `41b17ee`)** — 1,065 → **1,086줄**(+21). 🔴 **이동은 딱 한 군데다**: `sweep_undelivered_broadcasts`(**781**) **안**에서 +21이 늘어 `start_chain_ingestion_worker`만 **859 → 880**으로 밀렸다. **그 위 전 앵커는 무이동**이다(`OutboxListener` 42 · `post_event_async` 139 · `purge_expired_outbox_sync` 188 · `_stamp_broadcast_at_sync` 228 · `_dispatch_broadcasts` 249 · `load_chain_rules` 293 · `_mapper_accepts_rule` 322 · `execute_custom_mapper` 333 · `_group_target_tables` 351 · `process_chain_transaction_group` 374 · `reload_worker_process_cache` 600 · `warmup_worker` 616 · `process_pending_groups` 664).
>
> 🔴 **[신설] 이 스윕은 이제 두 번째 역할을 갖는다 — `run_watcher.post_event`가 통지 실패 시 남기는 durable 마커의 *수거자*다**([§1.7](#17-serverinternal_event_clientpy--내부-http-호출의-단일-소유자-23a346d-신설)).
>
> 🔴 **그리고 이 스윕에는 결함이 하나 있었다.** 미배달 행이 어떤 체인 `target_table`로도 사상되지 않으면, 구 코드는 **`broadcast_at`을 찍고 아무것도 브로드캐스트하지 않은 채 반환**했다 — durable 마커는 소비되고 통지는 사라지므로, **체인 룰의 target이 아닌 테이블에 대한 쓰기는 복구 경로가 아예 없었다.** 수리는 두 줄이다: `source_tables = {e.table_name …}`(**838**) · **`refresh_targets = affected_targets | source_tables`(839)** — 이후 **841 · 854 · 876–877**의 소비가 전부 이 합집합을 쓴다.<br>⚠️ **무한 스윕을 막는 것은 「발사 안 함」이 아니라 「확정을 찍는 것」이다** — `table_name`이 NOT NULL이라 합집합은 절대 비지 않고, 그래서 스윕은 언제나 스탬프로 끝난다. 남은 `if not refresh_targets:`(**841**)는 병적인 행에 대한 방어 경로이고 `[Broadcast Recovery]` 경고를 남긴다. 테스트: 🆕 **`tests/test_broadcast_recovery.py`(346줄)** — 🔴 **「재브로드캐스트는 하는데 스탬프를 안 찍는 수리」를 별도로 단언한다**(잃어버린 통지를 무한 스윕과 맞바꾸는 것이므로).
>
> 🔴 **[`f9289f6` 정정] 구 지도가 이 `except`에 대해 적은 문장은 절반이 틀렸고, 소스가 스스로 정정했다.** 구 문장은 *"이미 커밋된 체인 쓰기를 계측/자동화가 깨뜨려선 안 된다"*였다 — **커밋된다는 부분은 참이다**(`crud.apply_batch_updates`의 `transaction_context` 끝 `db.commit()` — 🔴 **구 지도의 `crud.py:1623`은 낡았고 경로도 벗겨져 있었다**: 실측 `server/database/crud.py` **2746** @`e943e46`. 라인 말고 **`apply_batch_updates` 말미**로 읽어라). 틀린 것은 **그래서 `except`가 봉쇄가 된다**는 함의다. PostgreSQL에서 실패한 문장은 트랜잭션을 abort시키고, 그 뒤 이 세션에서 워커가 하는 모든 것 — **`process_pending_groups`의 `processed_chain=True` 커밋 포함** — 이 실패하거나 조용히 롤백된다. 그러면 그룹은 처리됨으로 표시되지 않아 **배치 루프가 영원히 재실행**하고 재시도 격리는 한 발짝도 못 나간다. **봉쇄는 문장이 도는 자리에서 일어나야 하고**, 그 자리가 [`enrichment_config._isolated_execute`](#5-소형-서버-모듈)의 SAVEPOINT다. 정정된 근거 주석은 **~454–466**에 있고 아래 [① 신설] 행이 그것을 가리킨다.
>
> 🔴 **[`23a346d`] 이 워커가 자기 HTTP 세션을 만들지 않게 됐다.** `_get_http_session`은 [§0 묘비](#0-묘비-목록--소스에-존재하지-않는-이름)로 갔고 세션은 `internal_event_client.internal_event_session()`이 소유한다. 이 파일이 세션을 직접 만들던 것(`requests.Session()` 기본값 `trust_env=True`)이 **2026-07-30 프로덕션 403의 경위**이고, 그 403은 이 워커가 받았다. 성질은 그대로 옮겨졌고(keep-alive·스레드 로컬) **`trust_env=False`가 더해졌다.**
>
> 🔴 **`from utils.time_format import to_local_str`가 모듈 최상단으로 올라왔다** — 종전엔 통지 블록 **안에서** `from main import to_local_str`였고 그 블록은 `except Exception: logger.error("Failed to build chained update notification")`로 감싸여 있었다. `main` import는 웹앱 전체를 실행하며 **#13 fail-fast가 손상된 `table_config.json`에 raise**한다. 결과: 체인 배치는 **행을 커밋했고**, import가 raise했고, 예외는 삼켜졌고, **WS 통지는 나가지 않았다** — 행은 있는데 아무 클라도 모르고 로그 한 줄은 엉뚱한 원인을 지목했다([§5-A `utils/time_format.py`](#5-a-2026-07-30-신설-서버-모듈-8종)).

| 시그니처 | 역할 | 라인 |
|---|---|---|
| **`import enrichment_candidates`** | **[① 신설]** 모듈 최상단 import — 자동확정 컬렉터([§5-A](#5-a-2026-07-30-신설-서버-모듈-8종)) | ~37 |
| `class OutboxListener` — `_ensure_connection/_reset_connection/_wait_blocking/wait(timeout)/close` | psycopg2 LISTEN 전용 커넥션 + async 대기 | ~41–123 |
| **`import internal_event_client`** / `API_BASE_URL = internal_event_client.api_base_url()` | **[`23a346d`]** 세션·주소의 단일 소유자 import / **모듈 속성은 존치**(값만 위임 — 종전 리터럴 사본 3개 중 하나였다). 구 `_get_http_session`의 묘비 주석이 바로 아래 ~131–136에 있다([§0 ⑧](#0-묘비-목록--소스에-존재하지-않는-이름)) | ~127/129 |
| **`post_event_async(endpoint, payload) -> bool`** | 웹서버 `/internal/events/*` POST. **[`90e284f`] `headers=admin_auth.internal_event_headers()`** — `/internal/events/*`가 게이트 뒤로 들어갔으므로 이게 없으면 워커의 브로드캐스트가 401로 조용히 죽는다([§1.6](#16-serveradmin_authpy--어드민내부-토큰-게이트-90e284f-신설)). 🔴 **[`23a346d`] 세션은 `internal_event_client.internal_event_session()`에서 받고**, 비-`ok` 응답은 **상태코드만 로그하지 않는다** — `admin_auth.internal_event_failure_note(res.status_code, res.headers)`를 붙여 **누가 거부했는지**까지 한 줄에 넣는다. 판별자(`WWW-Authenticate`)는 응답에 내내 실려 있었고 이 줄이 그것을 버리고 있었다 | ~138 |
| `purge_expired_outbox_sync(db_session_factory, retention_days, ...)` | 처리 완료 outbox 보존기간 청소 (`OUTBOX_RETENTION_DAYS=7`·`OUTBOX_PURGE_INTERVAL=3600`·`OUTBOX_PURGE_CHUNK=1000`·`OUTBOX_PURGE_MAX_CHUNKS=50` ~181–184) | ~187 |
| `_stamp_broadcast_at_sync(db_session_factory, event_ids)` | 브로드캐스트 완료 스탬프(F1 전달 확정) | ~227 |
| `_dispatch_broadcasts(pending_broadcasts, db_session_factory)` | 커밋 후 인라인 브로드캐스트 발사 + 스탬프 | ~248 |
| `load_chain_rules()` | chain_rules 설정 로드(+enrichment 룰 병합). **`chain_replay.load_rules`가 이 함수를 그대로 부른다** — 재생이 라이브 룰 집합을 정확히 그대로 보게 하려는 것 | ~292 |
| `_mapper_accepts_rule(mapper_func) -> bool` | 맵퍼가 rule 인자를 받는지 시그니처 검사 | ~321 |
| `execute_custom_mapper(module_name, function_name, db, payload, rule=None)` | mappers/ 동적 로드·실행 | ~332 |
| `_group_target_tables(events_in_tx, rules)` | tx 내 이벤트 → 타깃 테이블 그룹핑 | ~350 |
| `process_chain_transaction_group(tx_id, events, db, rules) -> (ok, err, broadcast_messages)` | **핵심** — 순환 차단(source=chain_ingestion 제외), 맵퍼 실행, 업서트, 브로드캐스트 큐 반환. broadcast 구성부(**~539**)는 created_logs를 **직렬화 전** `MAX_NOTIFY_CREATED_LOGS`(500)로 절단 + `total_log_count` 동봉(인시던트 `cc57b64`). **[M3] upsert 직후 `MapMetaCollector`(**~468**)로 tx 그룹당 1회 부재 메타 등록.** **[① `~486–497`] 그 옆에 `enrichment_candidates.AutoConfirmCollector(target_table)`(**~487**)** — `ac.active`일 때만 `collect(batch_data.updates)` → `flush(db)`. **전체가 `try/except`이고 실패는 "chain write unaffected"를 명시해 로그**(**~496–497**). **루프가 아닌 근거가 주석에 있다**(**~483–485**) — 쓰기는 **파생** 테이블에 앉고 인리치먼트 룰은 **소스** 테이블에서 발화하며, 부재 전용 관문이 2차 통과를 무조건 no-op으로 만든다.<br>🔴 **[`f9289f6`] 그 두 `except`의 뜻이 정정됐다(**~454–466**).** 체인 쓰기는 **정말로 이미 커밋돼 있다**(`server/database/crud.py`의 `apply_batch_updates` 말미 `db.commit()`) — 그러나 예외를 **잡는 것**은 실패를 **봉쇄하는 것과 다르다**: PG에서 실패한 문장은 트랜잭션을 abort시키고, 그 뒤 이 세션의 모든 것(→ `process_pending_groups`의 `processed_chain=True` 커밋)이 실패하거나 롤백돼 **그룹이 영원히 재생**된다. 봉쇄는 문장이 도는 자리(SAVEPOINT)에서 일어난다 | ~373 |
| `reload_worker_process_cache()` | SYSTEM_RELOAD 수신 시 config 캐시 리로드 | ~599 |
| `warmup_worker(rules, db_session_factory)` | 콜드스타트 제거 — 맵퍼·커넥션 프리로드. **[`23a346d`] 3단계의 HTTP 프리워밍이 `internal_event_client.internal_event_session()` 호출로 교체**(같은 목적: 첫 통지에서 `requests` import 비용 제거) | ~615 |
| `process_pending_groups(db, group_order, groups, rules, db_session_factory, batch_wake_ts=None)` | 배치 내 그룹 순차 처리 — 실패 그룹 skip(HOL 블로킹 제거, F5). 🔴 **이 함수의 `processed_chain=True` 커밋이 위 `except` 정정의 피해자다** — 앞선 훅이 세션을 오염시키면 이 커밋이 조용히 롤백되고 같은 그룹이 다시 온다 | ~663 |
| 🔴 **`sweep_undelivered_broadcasts(db, rules, db_session_factory)`** | 통지 미확정 행 안전망 스윕(F1) **+ 🆕 워처가 남긴 미배달 마커의 수거자.** 쿼리 필터(**802–807**)가 마커 계약의 절반이다: `processed_chain == True` · `status == "SUCCESS"` · `broadcast_at IS NULL` · `created_at < now() − 5초`. 🆕 합집합 두 줄 **838/839** | **781** |
| `start_chain_ingestion_worker(db_session_factory)` | **메인 루프** — LISTEN 대기, 리로드 체크(1s 간격), 스윕, purge 스케줄. SYSTEM_RELOAD 블록에서 `models.refresh_dynamic_models(engine)`(지연 import) 호출 — 신규 테이블 CREATE 보충 안전망(이슈 #7). **[`8117456`] 루프 안에서 `heartbeat.beat("chain")`(**931**)** — `/health`가 "살아 있음"이 아니라 **"진척이 있음"**으로 판정하는 근거(`server/utils/heartbeat.py`, [§5](#5-소형-서버-모듈)). 🆕🆕🆕🆕 **[`347de78`] 그 호출이 `heartbeat.beat("chain", note=_undeclared_drop_note())`가 됐다** — 신설 모듈 함수 `_undeclared_drop_note()`가 `crud.undeclared_column_drops()`를 상위 `_DROP_NOTE_TOP_N=5`건으로 요약한 문자열(드롭 없으면 `None`, 건강한 비트는 바이트 단위로 무변경)을 만든다. `beat`의 `note` 파라미터는 신설이 아니다 — 이미 있던 하트비트 채널에 실은 것이다(§5 `heartbeat.py`의 `beat(name, note=None, force=False)`). 🆕 **[`23a346d`] 함수 첫머리(**888**)에서 `internal_event_client.startup_lines("Chain Worker")`를 로그한다** — 데이터가 흐르기 전에 토큰 지문·프록시 설정·`/health` 도달성을 말한다. **2026-07-30 403을 받은 것이 이 워커이고, 그때 이 프로세스가 기동에 남긴 어떤 줄도 이유를 말할 수 없었다.** 🆕 **제어 이벤트 필터(**1026**)가 `event_constants.CONTROL_EVENT_TYPES` 멤버십인데, 그 frozenset에 `EVENT_BROADCAST_RECOVERY`가 더해진 것이 미배달 마커를 맵퍼 경로 밖으로 지키는 장치다** | **880** |

---

## 5. 소형 서버 모듈

### `server/paths.py` (**165줄** — `2728bd9`로 70→165) — 데이터 루트 + **DB URL 단일 해석 지점**
**`4ba13ae` 신설, `2728bd9`에서 DB URL 해석 흡수.** `DATABASE_URL`이 DB를 갈아끼울 수 있게 하듯, 디스크 위의 사용자 소유 트리를 갈아끼운다. **약 21개 모듈이 각자 `os.path.dirname(__file__)`로 조립하던 경로를 전부 여기로 모았다** — 데이터가 어디 있는지 결정하는 곳이 정확히 하나다. DB URL 해석이 (database.py가 아니라) **여기** 사는 이유: stdlib 전용이라 **sqlalchemy가 import 불가능하게 깨진 배포에서도** `process_supervisor`의 도달성 프로브가 같은 구현을 쓸 수 있다.

| 심볼 | 역할 | 라인 |
|---|---|---|
| `SERVER_DIR` | 이 파일의 위치 = server 패키지 디렉터리 | ~36 |
| **`DATA_ROOT`** | `os.environ["ASSY_DATA_ROOT"]` **또는** `SERVER_DIR`. **미설정이 프로덕션이고 그때 레이아웃은 바이트 단위로 종전과 같다** | ~39 |
| `CONFIG_DIR` / `WORKSPACE_DIR` | `<DATA_ROOT>/config` / `<DATA_ROOT>/ingestion_workspace` | ~41/42 |
| `IS_ISOLATED` | `normcase(DATA_ROOT) != normcase(SERVER_DIR)` — 격리 환경 판별 | ~45 |
| `config_path(*parts)` / `workspace_path(*parts)` | 하위 경로 조립 | ~48/53 |
| `log_path(filename)` | 프로세스 로그는 **데이터 루트 직속**(종전 `server/server.log` 자리 그대로). 격리 프로세스가 사용자의 라이브 로그에 append하지 않게 하는 것이 요점 — 인시던트를 재구성하려고 읽는 파일에 드릴의 줄이 섞이면 안 된다 | ~58 |
| `describe()` | `data_root=… isolated=… db_env=…` 한 줄 — 각 프로세스가 부팅 로그에 찍는다. **[`2728bd9`] env URL도 `mask_db_password`로 마스킹** — 종전엔 원문 비밀번호가 server.log에 남았다 | ~71 |
| **`DB_CONFIG_FILENAME="database.json"`** | **[`2728bd9` 신설]** 사이트 소유 DB 접속 config(`config/database.json`, gitignored — `.sample` tracked). 형태 2종: `{"url": …}`(원문 그대로) 또는 split 필드 `{host,port,database,user,password}`(**`quote_plus` 합성** — 특수문자 비밀번호 생존). 운영 가이드 `docs/guide/config/database.md` | ~85 |
| `mask_db_password(url)` | `user:secret@` → `user:***@` — 로그 안전 표기. 소비: `describe()`·main.py 부팅 로그 | ~88 |
| `_database_url_from_config(path)` | 파일 → URL \| None. **있는데 깨진 파일은 ERROR 로그 후 다음 순위로 폴스루** — 선택 파일이 부팅을 죽이면 안 되지만, 운영자의 접속 설정을 조용히 무시하는 것은 엉뚱한 DB에 쓰는 경위다 | ~98 |
| **`resolve_database_url(default=None) -> (url, source)`** | **우선순위 env `DATABASE_URL` > `config/database.json` > default — 재배열 금지.** env가 파일을 **반드시** 이겨야 한다: `devenv.py bootstrap`이 config 트리(프로덕션을 가리키는 `database.json` 포함)를 격리 루트로 복제하므로, 파일이 이기면 격리 스택이 프로덕션 DB에 조용히 쓴다. `source`는 `"env"`\|`"config file"`\|`"default"`(빈 env는 미설정 취급). 소비자 3곳: `database.py`(import 시 1회 — **핫 리로드 없음**, 접속 문자열은 교체 불가라 변경은 전 프로세스 재기동) · `process_supervisor._database_endpoint` · main.py 부팅 로그. 테스트: **`tests/test_database_url_config.py`(176줄, 신설 — 우선순위·quote_plus·마스킹·프로브 폴스루 고정)** | ~146 |

> **의도적 제외**: `server/mappers/**`는 데이터가 아니라 **코드**이고 `sys.path`의 `mappers` 패키지로 해석되므로 이 모듈이 다루지 않는다.
> import 규약은 `event_constants.py`와 동일 — 모든 엔트리포인트에서 `server/`가 `sys.path`에 있으므로 `import paths`로 해석된다(그렇지 않을 수 있는 호출자는 `server/database/crud.py`·`server/database/database.py`와 같은 try/except 폴백).

### `server/process_supervisor.py` (**1,116줄** — `ed9cfdb` 718에서 **+306**) — 자식 프로세스 감독
> 🟢 **심볼 실측 완료** — 이 절의 심볼은 **`5609ff0`의 커밋된 blob에 존재함이 확인됐고, 그 뒤 HEAD가 움직인 다음 재대조에서도 동일했다**(워킹트리 아님). 🔴 **라인 번호는 싣지 않는다** — 위치는 `git grep -n "<심볼>" -- <경로>`로 확정하라. 숫자가 남아 있는 곳은 **파일 줄 수**이거나, 이름이 없는 덩어리를 가리키며 측정 sha가 함께 적힌 자리뿐이다.

**`8117456` 신설.** 구 `run_decoupled_app.py`는 5프로세스를 띄우고 `while True: time.sleep(1)`을 돌았다 — 워처나 체인 워커가 죽어도 **아무도 탐지하지 않고 아무도 재시작하지 않았다.** 웹서버는 살아 있으니 UI는 멀쩡해 보이고 데이터만 조용히 멎었다. 테스트: `tests/test_process_supervisor.py` · 🆕 **`tests/test_duplicate_launcher.py`(605줄)**.

> ⚠️ **이 절은 세 패스 연속으로 밀려 있었다** — 2026-07-27엔 최대 **+330**(공유원인 실패 축이 지도에 한 줄도 없었다), 2026-07-29엔 **줄수만 갱신되고 앵커는 +9 밀린 채**였다. **줄수 갱신은 앵커 재측정이 아니다.** 이번엔 전건 재측정했다.
>
> 🔴 **2026-08-04 신설 축 ② — 「포트 점유는 위의 둘 중 어느 것도 아니다」.** 실측이 축을 세웠다: 2026-07-25 이후 자식 사망 **74건**의 **100%가 TCP 포트를 바인드하는 유일한 두 자식**이었고(:8080 n=41 · :8090 n=33), **아무것도 바인드하지 않는 자식 셋은 0건**이다. 사망 시점의 uptime은 붙박이로 **3.0–3.1초**. 점유된 포트는 **영구적인 로컬 오설정**이라 재시도가 고칠 수 있는 것이 아니다 — 그래서 `_register_failure` 안에서 **동료 규칙보다도, DB 프로브보다도 먼저** 프로브하고 종단 판정 `VERDICT_PORT_CONFLICT`(점유 PID를 이름으로 댄다)를 낸다.
>
> 🔴 **신설 축 ③ — 「자식 출력은 아무도 안 남긴 콘솔이 아니라 파일로 간다」.** 위 진단이 어려웠던 이유가 이것이다: uvicorn의 바인드 `OSError`가 **디스크의 어느 파일에도 존재하지 않아서**, 원인을 74건의 통계로 재구성해야 했다.
>

| 시그니처 | 역할 |
|---|---|
| `BACKOFF_BASE_SEC=2.0` / `BACKOFF_MAX_SEC=60.0` / `MAX_CONSECUTIVE_FAILURES=5` | **재시도 예산** — 연속 n번째 실패는 `min(base·2^(n-1), max)` 대기, 예산 초과 시 `FAILED`로 **영구 정지**(배너 로그 + `/health` 비-200). 즉사하는 자식을 무한 재시작하면 CPU를 태우고 로그를 덮고 **무엇보다 감독이 동작하는 것처럼 보인다** |
| `HEALTHY_UPTIME_SEC=60.0` / `POLL_INTERVAL_SEC=1.0` / `STATUS_REFRESH_SEC=5.0` / `MAX_EVENTS=100` | 이만큼 살아 있었다면 크래시 루프가 아니므로 **연속 카운터를 리셋**한다 — 이게 없으면 한 달에 한 번 재시작하는 시스템이 결국 아무것도 재시작하지 않게 된다 / 폴 주기·상태파일 갱신 주기·이벤트 링버퍼 상한 |
| **`CORRELATION_WINDOW_SEC=120.0` / `CORRELATED_MIN_CHILDREN=2` / `CORRELATED_BACKOFF_SEC=60.0`** | **공유원인 실패 판정.** 상관은 **exit code가 아니라 시간으로** 정의한다 — 윈도우에선 미처리 파이썬 예외가 전부 exit 1이라 코드 시그니처는 아무 쌍이나 상관으로 부르고 아무것도 증명하지 못한다. 규칙은 **창 안에서 서로 다른 자식 2개 이상이 죽었는가**. 창이 120초인 것은 **예산 1사이클보다 길어야** 하기 때문(2+4+8+16+32초 ≈ 첫 죽음 후 80초에 판정이 나고, 그 시점에 동료들의 마지막 실패는 20–40초 전이다) |
| 🆕 **`PORT_PROBE_TIMEOUT_SEC = 0.5`** / 🆕 **`CHILD_LOG_MAX_BYTES = 20MiB`** | 포트 프로브 상한 / 자식 stdout 로그 회전 임계(백업 `.1` 하나) |
| `STATE_RUNNING\|BACKOFF\|FAILED\|STOPPED` / **`STATE_RETRYING_CORRELATED`** / `_WAITING_STATES` | 자식 상태 어휘. **`retrying_correlated` = 예산은 소진했지만 혼자가 아니다 → 영구 실패시키지 않고 계속 재시도** |
| 🆕 **`VERDICT_BROKEN_CHILD = "broken_child"` / `VERDICT_PORT_CONFLICT = "port_conflict"`** | **종단 판정 어휘 2종.** 스냅샷의 `"terminal_verdict"` 키와 이벤트 스트림(`_record(child, "permanently_failed", verdict=…)`에 실린다. ⚠️ **현재 `main.py`·`health.py`에 이 값으로 분기하는 독자가 없다** — 소비자는 `tests/test_duplicate_launcher.py`뿐이다(선언은 있고 화면이 아직 안 읽는다) |
| `status_path()` | `paths.config_path("supervisor_status.json")` |
| `_database_endpoint(url=None)` / **`shared_dependency_down(url=None, timeout=2.0) -> (down, detail)`** | **[신설] 환경이 깨졌다는 직접 증거.** 왜 동료실패 규칙만으론 부족한가 — PostgreSQL 불통 콜드스타트 실측에서 **죽는 자식은 정확히 하나**, 웹서버다. 워커 4개는 자기 루프에서 에러를 삼키고 살아남는다. 즉 "재부팅 후 DB가 늦게 떴다"의 가장 흔한 실제 형태가 **고립된 자식 1개**이고, 동료만 세는 규칙은 94초 뒤 웹서버를 영구 실패시킨 뒤 DB가 돌아와도 안 살린다.<br>⚠️ **이 규칙의 근거를 `create_all`이 어느 줄에서 도는지에 묶지 마라.** 소스 docstring(~176–180)과 이 지도의 종전 서술은 근거를 "**import**가 `Base.metadata.create_all`을 도는 웹서버"로 적었고 HEAD `b8307c2`에서는 여전히 그렇다(`main.py`, 모듈 최상위 — [§1.1](#11-기동미들웨어공용-헬퍼)). 그런데 **그 줄은 이동 중이다**(미착지 라운드가 기동 함수 안으로 옮긴다). 판정이 실제로 딛고 있는 사실은 두 가지이고 **둘 다 위치와 무관**하다: ① 웹서버는 부팅 경로에서 DB에 무조건 닿고 워커는 안 닿는다 → 불통 시 죽는 자식은 하나 ② **감독자는 종료 코드를 아예 보지 않는다** — `poll_once`가 `code is None`인지만 보고(~569–570) 값은 이벤트 기록용일 뿐, 파일 전체에 exit code 비교가 **0건**이다(`grep -n "exit_code ==\|code ==" = 0`). QA가 죽은 포트에 uvicorn을 물려 실측한 **exit 3**도 이 경로에서는 다른 코드와 구분되지 않는다. 결론은 유효하다 — 바뀔 수 있는 것은 근거 문장의 **메커니즘 절**뿐이다. **TCP 도달성만** 본다(인증·스키마 결손은 재시도가 못 고치는 설정 결함). **모르면 healthy** — 이 프로브는 증거를 **더하기만** 할 뿐 실패시킬 능력을 빼앗지 않는다. **[`2728bd9`] `url=None`이면 `paths.resolve_database_url()`로 해석**(database.py와 같은 우선순위 env > `config/database.json` — 예외 시 env 폴백, 기본값 없음: "아무것도 설정 안 됨"은 종전대로 프로브 대상 없음) |
| 🆕 **`port_owner(port, log=None)` / `port_is_taken(port, host="0.0.0.0", timeout=…)` / `describe_port_conflict(port, host, timeout)` / `port_conflict(spec, timeout)` / `preflight_port_check(ports, host, timeout)`** | **[신설] 포트 점유 판정 5종.** `port_owner`는 점유 PID를 이름으로 대고, `port_conflict`는 `ChildSpec.ports`를 받아 자식 단위로 답하며, **`preflight_port_check`는 런처가 *아무것도 띄우기 전에* 부르는 것**([§6 `run_decoupled_app.py`](#6-기타-서버-모듈-한줄-요약)) |
| `psutil_status()` / `_psutil_or_warn(log=None)` | 손자 정리 무장 여부를 **기동 시 1회 announce**. 정리 경로가 조용히 퇴화하는 것이 고아 수집기 프로세스가 몇 주씩 쌓이는 경위라, 종료 때 발견하지 않고 부팅 때 말한다 |
| `_descendant_pids(pid, log=None)` / `_kill_pids(pids, log=None)` | 종료 시 손자 프로세스까지 수거 |
| 🔴 **`class ChildSpec(name, cmd, cwd, env=None, restartable=True, heartbeat=None, start_delay=0.0, ports=(), port_host=None, log_file=None)`** | 자식 1개의 기동법 + 죽었을 때의 처분. **`restartable=False`는 "이게 죽으면 전체를 멈춘다"**(데스크톱 창 닫기), **`heartbeat=`는 그 자식이 발행하는 비트 이름** — `/health`가 프로세스 관점(감독자)과 진척 관점(비트)을 조인하는 열쇠. 🆕 **키워드 3종이 이번에 추가됐다**: `ports`/`port_host`(포트 충돌 판정의 입력) · **`log_file`**(설정되면 spawn이 `stdout=PIPE, stderr=STDOUT` + `PYTHONUNBUFFERED=1`로 바뀐다) |
| `class _ChildState(spec)` | 자식 1개의 런타임 상태(상태·연속 실패수·시작시각·이벤트). 🆕 `terminal_verdict` · `log_pump` 필드 추가 |
| `class Supervisor(specs, status_file, log, spawn, clock, sleep, environment_probe=None, port_probe=None)` | `spawn`/`clock`/`sleep` 주입 가능 — **실제 프로세스를 띄우지 않고 실제 초를 기다리지 않고** 재시작 정책을 결정론적으로 테스트하기 위함(프로덕션은 아무것도 넘기지 않는다). `environment_probe` 기본값 `shared_dependency_down`, 🆕 **`port_probe` 기본값 `port_conflict`** |
| ├ `_default_spawn` / 🆕 **`_attach_log_pump(child)`** / `_find` / `_record(child, event, **fields)` / `_backoff_for(n)` | 기본 spawn(자식 env를 `os.environ.copy()`로 만든다 — 런처의 `ASSY_ADMIN_TOKEN` 상속 근거) / 🆕 **자식의 병합 stdout을 `sys.stdout.buffer`**와** `spec.log_file` 양쪽에 티(tee)하고 `CHILD_LOG_MAX_BYTES`에서 회전** / 이름 조회 / 이벤트 링버퍼 기록 / 백오프 계산 |
| ├ **`_peers_failed_recently(child, now)`** | 창 안에서 **다른** 자식이 몇이나 실패했는지 — 상관 판정의 계수기 |
| ├ `start_all()` / `_start(child)` | 순차 기동(+`start_delay`). **spawn 예외도 즉사와 동일한 실패로 계산**한다 — 아니면 잘못된 커맨드라인에서 영원히 돈다 |
| ├ 🔴 **`_register_failure(child, exit_code, reason=None)`** | **정책 본체 — 판정 순서가 계약이다.** 🆕 **포트 프로브가 맨 앞이다**: 동료 규칙보다도, DB 프로브보다도 먼저. 점유된 포트는 재시도가 못 고치므로 **즉시 종단 `VERDICT_PORT_CONFLICT`**. 그다음이 종전 정책 — uptime ≥ `healthy_uptime`이면 연속 카운터 리셋, 아니면 +1, 예산 초과 시 **혼자면 `_fail_permanently`, 아니면(동료 실패 ∨ 환경 프로브 down) `_enter_correlated`**. ⚠️ **프로브가 raise하면 아무것도 판정하지 않는다**(`tests/test_duplicate_launcher.py`가 그것을 단언한다) |
| ├ `_fail_permanently(child, exit_code, reason, verdict=VERDICT_BROKEN_CHILD, detail=None)` / **`_enter_correlated(child, now, peers, exit_code, env_detail=None)`** | 영구 정지(🆕 `verdict`·`detail` 인자) / **`STATE_RETRYING_CORRELATED`로 진입해 `CORRELATED_BACKOFF_SEC` 간격으로 계속 재시도** — 이미 힘든 DB를 두들기지 않을 만큼 길고, 원인이 걷히면 1분 안에 자동 복구될 만큼 짧다 |
| ├ `poll_once()` / `run()` | 1틱 점검(종료 감지·백오프 만료 재기동·상태 파일 갱신) / **`run_decoupled_app.py`의 sleep 루프를 대체한 메인 루프** |
| ├ `stop_all(timeout=3.0)` / `snapshot()` | 종료(자손 포함) / `/health`가 읽는 상태 dict(🆕 `terminal_verdict` |
| └ `write_status(force=False)` | `supervisor_status.json` 기록. **`updated_at`이 감독자 자신의 생존 신호** — 감독자가 죽으면 자식들은 계속 비트를 찍지만 이 타임스탬프가 멈추고 `/health`가 그걸 말한다 |
| `read_status(path=None)` | 상태 파일 판독(`main.py` 헬스가 소비) |

> 미드-인제션 워처를 재시작해도 안전하다는 것이 이 설계의 전제다 — P2 체크포인트 재개가 10만 행 중 3만 행 지점 `taskkill /F` 하에서 드릴됐고 커밋된 오프셋이 실제 행수와 정확히 일치했다(`agent_workspace/reports/QA_p2_drills_isolated.md` §2). **자동 재시작이 허용되는 근거는 그것 하나다.**

### `server/health.py` (**384줄**) — `/health` 판정표 (순수 함수 + config 백업 프로브)
**`8117456` 신설, `b35bc9f`에서 `checks.config_backup` 추가.** 테스트: `tests/test_health_endpoint.py`.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `STATUS_OK\|DEGRADED\|UNHEALTHY` / `HTTP_OK=200` / `HTTP_UNHEALTHY=503` | 상태 어휘와 HTTP 사상 | ~45–47/49/50 |
| `STARTUP_GRACE_SEC=60.0` | 갓 뜬 워커는 모듈 import 후 루프에 닿아야 비트를 찍는다. 이 유예가 없으면 부팅마다 503이 나가고, **부팅 때마다 틀리는 헬스체크는 무시당한다** | ~55 |
| `OUTBOX_AGE_DEGRADED_SEC=300` / `OUTBOX_AGE_UNHEALTHY_SEC=900` / `OUTBOX_COUNT_CAP=10000` | **백로그는 크기가 아니라 나이로 잰다.** 정상적인 10만 행 인제션 1건이 outbox 약 11.6만 행을 만든다(P2 드릴 실측) — 멎은 워커를 잡을 만큼 낮은 크기 임계는 대용량 파일마다 오발화한다. "바쁨"과 "멈춤"을 가르는 건 큐가 **빠지는가**이고, 빠지고 있으면 뒤에 몇 행이 쌓였든 가장 오래된 미처리 행은 젊게 유지된다 | ~62/63/66 |
| **`BACKUP_PROBE_CACHE_SEC=60.0` / `probe_config_backups(now=None)`** | **[`b35bc9f` 신설]** `config_backup.probe()`를 60초 캐시로 감싼 래퍼 — 10초 폴링 모니터가 매번 디스크 스캔을 유발하지 않게 한다. import 실패·예외는 `status:"unknown"`으로 보고(확인 불가를 이상 없음으로 내지 않는다) | ~70/80 |
| `_iso(ts)` | 타임스탬프 직렬화 헬퍼 | ~103 |
| **`compute_health(db_result, heartbeats, supervisor_status, outbox_result, stale_after, now=None, backup_result=_PROBE) -> (payload, http_status)`** | **판정표 본체 — I/O 없음**(순수성 유지: 테스트는 `backup_result=None`으로 백업 검사를 스킵. **`backup_result`만은 생략 시 자체 프로브를 돈다** — 순부가 인자라 main.py 호출부 무수정). 내부 `escalate(level)`이 최악 상태를 끌어올린다. 워커 판정은 감독자 뷰 × 비트 뷰의 조인: `not running→down` · `running + 비트 낡음→wedged` · `running + 비트 없음 + 어림→starting` · `running + 비트 신선→ok`. **비트의 pid가 감독 대상 pid와 다르면 비트를 없는 것으로 친다** — 유령 워커/제2 스택이 wedged된 진짜 워커를 가리는 것이 실제로 관측됐다. **[`b35bc9f`] `checks.config_backup`**: `missing`/`stale`/`unknown` → **degraded, 절대 503 아님**(백업 부재는 "다음 인시던트가 어려워진다"이지 "지금 장애"가 아니다 — 503이면 모니터가 멀쩡한 스택을 재시작한다) | ~107 |
| `probe_outbox(db)` | 백로그 나이 + (상한된) 크기. 둘 다 부분 인덱스 `idx_outbox_unprocessed`를 타고, 나이는 `ORDER BY id ASC LIMIT 1`로 **테이블 크기와 무관한 O(1)**, 카운트는 `LIMIT cap+1`로 감싸 1천만 행 테이블에서도 ~1만 인덱스 엔트리를 넘지 않는다 | ~354 |

### `server/config_backup.py` (**379줄**) — 주간 config 스냅샷 + FIFO 보존 (`b35bc9f` 신설)
**C3 — 롤백 절차(B4)의 빠져 있던 의존성.** `server/config/*.json`을 파일별로 `config_<yymmdd>.json.bak`(동일 날짜 2회째부터 `b`,`c`,… 접미)으로 스냅샷. **신선도는 cron 슬롯이 아니라 디스크의 최신 스냅샷 나이로 판정**한다(놓친 주가 다음 틱에 자가 치유). 소비자 3곳: `run_auto_update.MultiDiscoveryScheduler.maybe_backup_configs`(주기 실행) · `health.probe_config_backups`(`/health` 프로브) · `server/scripts/backup_config.py`(CLI). 테스트: `tests/test_config_backup.py`(370줄).

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `INTERVAL_DAYS=7` / `STALE_AFTER_DAYS=10` / `RETENTION_DAYS=31` / **`RETENTION_MIN_KEEP=4`** / `CHECK_INTERVAL_SEC=1800` | 주기·신선 임계·FIFO 보존창·**최신 4개 바닥**(31일 FIFO가 어떤 이유로든 몰아서 지워도 최근 4개는 남는다) / 스케줄러 틱 게이트 | ~96–109 |
| `RUNTIME_FILES` / `SUFFIX=".json.bak"` / `_SNAPSHOT_RE` | 스냅샷 제외 런타임 파일 목록 / 스냅샷 이름 문법(`<stem>_<yymmdd><seq>.json.bak`) | ~114/119/122 |
| `snapshot_name` / `source_files` / `list_snapshots` / `newest` | 이름 조립 / 대상 열거 / 스냅샷 열거(오래된 순) / 파일별 최신 | ~131/137/167/188 |
| `_same_bytes(a, b)` / `_prune(entries, config_dir, now)` | 바이트 동일하면 새 스냅샷 무쓰기 / FIFO 퇴거(+4개 바닥) | ~202/212 |
| **`take_snapshot(config_dir=None, now=None)`** / `due` / **`probe`** / **`run_scheduled`** | 스냅샷 1회 실행 / 디스크 기준 기한 판정 / `/health`용 상태(`ok\|missing\|stale\|unknown`) / 스케줄러용 due-체크+실행 래퍼 | ~234/297/306/350 |

### `server/utils/heartbeat.py` (**303줄** — 종전 지도의 174줄은 낡은 값) — 워커 진척 비트 + **작업 단위 claim**
**`8117456` 신설.** 프로덕션 인시던트는 이벤트 루프 프리즈였다 — 프로세스는 내내 살아 있었고 수십 초간 아무것도 서빙하지 못했다. **pid 점검은 그걸 healthy라고 답한다.** 그래서 워커는 **자기 루프 안에서** 진척을 발행한다.

> **[신설] "루프가 돈다"와 "일이 진척된다"는 다른 사실이라 따로 잰다.** 비트는 전자, `work_claim`은 후자다. 파일 1건의 인제션처럼 **한 번에 몇 분씩 걸리는 작업 단위**는 루프 비트만으로는 진척을 증명하지 못한다.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `HEARTBEAT_DIRNAME="worker_heartbeats"` / `heartbeat_dir()` / `heartbeat_path(name)` | 저장 위치 — **`paths.config_path("worker_heartbeats")/<name>.json`** | ~79/137/141 |
| `MIN_WRITE_INTERVAL_SEC=1.0` | 워커당 초당 1회 초과 디스크 접촉 금지(비트 1건 ≈ 200바이트 원자 replace) | **83** |
| `DEFAULT_STALE_AFTER_SEC=60.0` | **감으로 고른 숫자가 아니다** — 자연 루프 주기(워처 3.0s · 체인 2.0s · 그래프 2.0s · 스케줄러 5.0s) 기준 **가장 느린 루프로도 연속 12회 이상 결번**. 1회 결번으로 알람이 울리면(GC 정지·느린 디스크) 헬스체크는 음소거되고, 그건 없느니만 못하다 | ~102 |
| **`DEFAULT_STALL_AFTER_SEC=300.0`** | **[신설] claim된 작업이 진척 없이 버틸 수 있는 상한.** `STALE`보다 의도적으로 훨씬 크다 — **두 수가 다른 것을 재기 때문**이다. 비트 결번은 2–5초 루프가 안 돌았다는 뜻이지만, claim 진척 결번은 **실제 작업 청크가 안 끝났다**는 뜻이고 청크는 균일하지 않다. 라이브 10만 행 heavy 인제션 실측(35MB·893초)에서 청크 간격 p50 9.20s · p95 9.70s · **max 12.50s**(단일청크 구간 42건). 바닥을 정한 건 **계측할 수 없는 쪽**이다 — 커스텀 파이프라인 파서는 파일 하나를 불투명한 한 번의 호출로 읽고 그동안 아무 보고도 하지 않는 사용자 스크립트라, 큰 워크북에서 몇 분이 정당하게 걸리고 그 안에서는 비트를 찍을 수단이 없다. 300s는 실측 청크 케이던스의 24배이면서 진짜 멈춘 인제션은 5분 안에 드러낸다. **편향은 침묵 쪽이고 그것이 의도다** — 이건 운영자 대시보드에 503을 띄우고, 사람들이 가장 신경 쓰는 바로 그 작업 중에 늑대를 외치는 헬스체크는 음소거된다 | ~125 |
| `_state` / **`_claims` / `_claim_seq`** | 워커별 비트 상태 / claim 레지스트리 — **시간이 아니라 진행 중 작업 수로 유계**(레인당 1개, 모든 claim이 finally에서 제거된다) | ~128/133/134 |
| `beat(name, note=None, force=False)` | **워커의 실제 작업 루프 안에서 반복마다 호출.** 반환값은 테스트용이고 호출자는 무시한다. 고정 temp 파일명 + `os.replace`로 **원자적**(독자가 부분 파일을 보지 않는다). **모니터링 기능이 새 장애 모드가 되면 안 되므로 모든 디스크 오류는 삼키고 카운트만 한다** — 워커 루프로 예외를 올리지 않는다 | ~145 |
| `_work_snapshot_locked(name)` | 그 워커의 **가장 오래 진척 없는 claim**. **나이가 아니라 절대 타임스탬프를 publish**한다 — 독자가 비트가 쓰인 시점이 아니라 **지금**에서 stall을 재게 하기 위함 | ~198 |
| **`work_claim(name, what)` (contextmanager)** | **작업 단위 1건 선언.** 파일 1건의 인제션 전체를 감싸고 그 안에서 `beat(name)`을 부르면 같은 스레드의 비트가 claim 진척을 갱신한다. **실패 경로 포함 항상 해제**된다 — 크래시한 잡이 남긴 claim은 영원한 stall과 구분되지 않는다. 진입 시 `force=True` 비트를 한 번 찍어 **다음 폴러 틱을 기다리지 않고** 즉시 보이게 한다. 소비자 **2곳, 둘 다 `with` 진입 줄이 앵커다**: `directory_watcher.process_with_retry`(함수 ~1033, claim **~1044**)·`process_archived_file_sync`(함수 ~1316, claim **~1328**) — 구 표기 1062/1329는 §3의 표(1046/1335)와도 어긋나 있었다([§3](#3-serverparsersdirectory_watcherpy--파일-인제션)) | ~217 |
| `open_claims()` | 이 프로세스의 열린 claim 전량(테스트·진단용) | ~242 |
| `read_all(stale_after=DEFAULT_STALE_AFTER_SEC, now=None, stall_after=DEFAULT_STALL_AFTER_SEC)` | 전 비트 판독(+`age_seconds`/`stale`). **읽을 수 없거나 깨진 파일은 건너뛰지 않고 `error` 필드를 단 stale로 보고한다** — 침묵은 헬스체크가 절대 주면 안 되는 답이다 | ~248 |

> 🔴 **비트 이름 4종 — 2026-07-30 전건 재측정.** 이 문단은 `280ebf0`(2026-07-28) 실측 이후 두 라운드 동안 갱신되지 않았고, **넷 중 셋이 틀려 있었다.** 아래가 `8cf9455` 실측이다:
>
> | 비트 | 발행 함수 | 발행 줄 | 구 표기 → 실측 |
> |---|---|---|---|
> | `watcher` | `run_watcher.poll_pending_retries`(**~167**) | **~183** | 151/167 → **167/183**(`23a346d`의 +16) |
> | `chain` | `chain_ingestion_worker.start_chain_ingestion_worker`(**~844**) | **~895** | 785/827 → **844/895** (구 표기가 −59·−68 낡아 있었다) |
> | `graph` | `graph_sync_worker.run_graph_materializer_loop`(**~639**)의 `while True`(**~706**) | **~709** | 555/622/625 → **639/706/709**. 🔴 **구 `~555`는 `publish_system_reload`를 가리켰다** — 실재하는 다른 함수이고, 그래서 도착지가 멀쩡해 보인다 |
> | `scheduler` | `run_auto_update.MultiDiscoveryScheduler.run`(**~703**) | **~734** | 644/675 → **703/734**(`4aae627`의 +59) |
>
> 이 이름이 `run_decoupled_app.py`의 `ChildSpec(heartbeat=…)`와 짝을 이룬다.
>
> ⚠️ **`scheduler` 앵커는 이제 네 번 밀렸다**(`~515`→`600`→`636`→`675`→**734**). 이것이 이 문서 상단이 경고하는 함정의 **교과서적 실례**다 — 낡은 앵커 자리에는 늘 실재하는 다른 함수가 들어앉아 도착지가 멀쩡해 보인다. 🔴 **그리고 이번 이동은 직전 패스가 이 수를 막 고쳐 놓은 다음 라운드에 일어났다** — `4aae627`이 `_apply_proxy_policy`(~25–81, 59줄)를 **파일 머리**에 넣었기 때문이다. **앵커의 수명은 문서 패스가 아니라 커밋이 정한다.** 다른 셋(`watcher` 167/183 · `chain` 844/895 · `graph` 639/706/709)은 이 범위에서 blob이 초록이라 무이동이다.
>
> ⚠️ **`graph` 비트는 `_run_one_batch`(**~670**) 안이 아니라 그 바깥 `while True`(**~706**) 안이다** — 배치 본체는 `asyncio.to_thread`로 격리돼 있고, 비트는 **루프가 도는 것**을 증명해야 하므로 격리된 스레드 안에 있으면 안 된다.

### `server/product_tables.py` (**232줄**, `ed9cfdb` 201에서 **+31**) — 제품 소유 테이블 선언 정본
**`8e80fcc` 신설.** 소유권 경계: **제품 소유**(assyManager 자신의 저장소 — 이름·컬럼을 제품이 정하고 사이트가 바꿀 이유가 없다)는 여기 선언, **사이트 소유**(고객 공장 데이터 — 배포마다 이름이 다르다)는 여기 절대 등재하지 않고 설치기도 건드리지 않는다.

| 심볼 | 역할 | 라인 |
|---|---|---|
| `ANNOTATION_KEYS = ("__comment",)` | 문서용 키. `models.init_dynamic_models`가 읽지 않으므로 런타임 동작을 바꿀 수 없다 → 설치기는 이 키의 차이를 **drift가 아니라 note**로 처리한다(주석 한 줄 고친다고 기존 사이트 전부가 drift로 뜨면 안 된다) | ~35 |
| **`PRODUCT_TABLES`** | 🆕 **5종**(4 → 5): `wafer_map_metadata`(**39**, 맵 격자 규격 정본 — bk `target_table_map_id`) · **`map_split_registry`(**60** — legend 행 = DOE 1건. bk `ref_table\|map_key\|value`, 분리자 `\|`. `split_desc`·`knobs`는 온톨로지 소비 대상이라 **플랫 컬럼 유지**. [`269b39e`+`b35bc9f` ZONE 모델] `stack`·`mat_1h`·`mat_mid`·`mat_top` 컬럼 추가, `bands`는 **폐기됐지만 여전히 선언**(아래). `map_key_columns=(ref_table, map_key)`가 `replace_map` 스코프)** · ~~`map_doe`~~(~104) · ~~`map_doe_source`~~(~145) — **뒤 둘은 `0f8d35f`에서 DEPRECATED 표기**(`__comment` 선두에 명시). 아무 코드도 쓰지 않으며 선언만 남은 이유는 운영자가 손으로 데이터를 옮기는 동안 읽을 수 있게 하기 위함이다. **새 소비자를 붙이지 마라.** 물리 DROP은 사용자 승인 대기. 딕셔너리 순서가 config 파일에 append되는 순서다.<br>🆕 🔴 **다섯 번째: `valid_die_ref`(**188–219**)** — 2026-08-04 사용자 판정으로 **제품 소유로 승격**됐다(유효 다이 저장 테이블 이름을 고치면서 같은 변경에서 **맵 에디터의 테이블 선택기를 없앴다** — 클라는 이제 이 테이블에서만 저장·로드한다). 🔴 **제품 소유라는 사실이 「모든 사이트에 존재한다」를 만들고, 동시에 「누군가의 픽스처 테이블처럼 지워지는 것」을 막는다.** ⚠️ **행 하나가 셀 하나다**(bk `product_type_x_y` · `map_key_columns=(product, type)`) — **행의 존재 자체가 「이 다이가 유효한가」의 답**이고, 별도 컬럼을 두면 그 둘이 어긋날 수 있다 | **38** |
| `PRODUCT_TABLE_NAMES` | `tuple(PRODUCT_TABLES.keys())` | **221** |
| `effective_declaration(entry)` | 주석을 걷어낸 **동작 유발 부분**만 남긴다(drift 판정용) | **224** |

> **왜 두 번째 JSON이 아니라 Python 모듈인가**: `server/config/**`는 gitignored(`*.sample`만 tracked)라 그 안의 정본 JSON은 배포되지 않는다. 이 모듈은 코드이고 tracked이며 소비자는 정확히 둘 — ① `server/scripts/install_product_tables.py` ② `config/table_config.json.sample`(같은 설치기가 `--sample --apply`로 **생성**하고 `tests/test_install_product_tables.py`가 둘의 일치를 단언하므로 샘플이 조용히 어긋날 수 없다).
>
> ✅ **ZONE 모델 착지 (`269b39e` 선언 + `b35bc9f` 엔드투엔드)** — 값 하나의 층 구조는 **숫자 하나가 함의하는 고정 3구역**이다: `stack` = 총 층수, `mat_1h` = 1층, `mat_top` = `stack`층, `mat_mid` = 그 사이 전부. FROM도 TO도 구간 행도 없다 — **세 구역이 `1..stack`을 구성적으로 덮으므로 겹침·구멍 검사는 옮겨진 게 아니라 어길 방법이 없어졌다.** 정본 서술은 `map_split_registry.__comment`, 스펙은 [`MAP_EDITOR_SPEC.md` **§6.0-bis**](../spec/MAP_EDITOR_SPEC.md)(⚠️ ~~`docs/spec/DOE_ZONE_MODEL.md`~~는 **존재한 적 없는 경로**다 — 코드 주석의 유령 인용도 `95bf072`에서 §6.0-bis로 리포인트됐다), 클라 미러는 `client2/src/map_editor.js` ~301–320 주석.
> - **`stack`은 `string` 선언이고 그것이 load-bearing이다** (`b35bc9f` — number였던 것을 **첫 실데이터 전에** 정정): number 선언은 물리 컬럼이 `double precision`으로 나왔고, `crud.cast_value_by_type`가 `'0x10'`엔 raise(읽을 수 없는 STACK 하나가 계획 전체 저장을 막았다), `'7.5'`는 조용히 수리 후 다음 읽기에서 **7로 절단**했다 — 화면은 멀쩡하고 숫자만 모자라는 바로 그 결함. 읽을 수 없는 STACK은 왕복에서 **살아남아야** 한다(V5가 차단하고, 패널이 원문을 보여 주고, Excel로 원문이 돌아간다). 가독성 판정은 컬럼 타입이 아니라 **단일 정수 판독기**(`transfer_plan._int_state` / 클라 `bandToState`)가 한다.
> - **세 `mat_*` 컬럼은 원문 토큰의 JSON 배열**(`["MID1:1","MID3:1"]`)이다 — 분리자로 이어붙이지 않는다: lot 이름에 `:`도 `_`도 합법이라 안전한 문자가 없고, 분리자를 가정했다가 서로 다른 두 풀이 한 행으로 합쳐진 사고가 있다(`doe_bands.js`의 `materialPoolKey` 주석). 토큰 문자열 자체가 정체이고 `lot[_slot][:BIN]` 파싱은 나중의 **선언된** 단계다.
> - **파생값은 저장하지 않는다.** 특히 자재당 수치는 **배분이 아니라 충분성 검사**다 — 웨이퍼는 아무도 기록하지 않는 순서로 한 장씩 소모되므로 균등 나눗셈은 "이 풀로 충분한가"만 답한다.
> - **`bands`는 폐기됐지만 여전히 선언돼 있다(의도)** — `transfer_plan.REGISTRY_LEGACY_ROLE`이 폐기 계획을 읽는 데 쓰고, 이 컬럼만 먼저 빼면 리더가 갱신되기 전까지 validate가 전 사이트 404가 된다. 새 writer 금지.
> - **`updated_by` 컬럼이 없는 것은 의도**다 — `server/database/crud.py`의 `system_cols`에 들어 있어 제네릭 테이블 API로는 영원히 쓰이지 않는다(구 `map_doe`의 전 행이 NULL이었다). '누가'는 `cell_sources`/`cell_overwrites.updated_by`가 이미 나른다.
>
> ⚠️ zone 규칙(V1–V6)·토큰 문법·수요 산술은 **양쪽 구현이 공유 벡터로 고정**돼 있다 — [§6-2 `contracts/doe_band_rules/`](#6-2-교차-구현-계약-contracts) 참조 (레거시 `bands` 산술은 `contracts/band_arithmetic/`). **[`2baf9ff` U9] `stack`의 명시적 `'0'`은 marker(상태 표시 값)** — 층·구역·수요 없는 조건 선언이고, 구역 자재와 공존하면 V6이 차단한다(blank와 다르다 — blank는 V5).

### `server/database/models.py` (**636줄** — 종전 지도의 550줄은 낡은 값) — ORM + 동적 모델/런타임 DDL
정적 ORM 클래스(`AuditLog` ~11 / **`InteractionEffortLog` ~51** / `DatabaseOutbox` ~118 / `FileIngestionLog` ~186 / `FileIngestionCheckpoint` ~200 / `CellOverwrite` ~247 / `CellSource` ~264)와 **그래프 3모델**, config 주도 동적 테이블 관리 함수.

> ⚠️ **두 패스 연속으로 이 절이 밀렸다.** 2026-07-29 오전: `AuditLog`를 뺀 전 앵커가 `+21`(범위가 이 파일을 건드리지도 않았다). 같은 날 오후 `2a9f6c4`가 **`InteractionEffortLog`(~51–116)를 `AuditLog` 바로 뒤에 끼워 넣어** `DatabaseOutbox` 이하가 다시 `+67`. 구 앵커 `~51`은 이제 **실재하는 다른 클래스**를 가리킨다 — 도착지가 멀쩡해 보이는 바로 그 함정이다.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| **`class InteractionEffortLog`** | **[V1 `2a9f6c4` 신설]** 교정 1건의 **원시 상호작용 카운트**(`transaction_id`·`session_id`·`key`·`mouse`·`nav`·`nav_preserved`). **점수 컬럼이 없는 것이 설계다** — 가중치는 config이고 점수는 읽는 시점에 계산되므로, 가중치를 재조정하면 과거 tx가 전부 새 가중치로 재해석된다(선언 절반은 이 절 아래 `server/effort_metric.py`) | ~51 |
| `class GraphNode` | 그래프 노드 — `(label, identity_key)` UNIQUE, props JSONB | ~286 |
| `class GraphEdge` | 그래프 엣지 — (from,type)/(to,type) 인덱스, `(from,type,to,source_name)` UNIQUE, `idx_graph_edges_row_ref(source_row_ref)` | ~303 |
| `class GraphSyncState` | materializer outbox 소비 커서(id=1 단일 행, `last_outbox_id`) | ~331 |
| `DYNAMIC_TABLES` | 동적 테이블 싱글턴(`sys._dynamic_tables_singleton`) | ~347 |
| `init_dynamic_models(config_dict)` | config → 동적 ORM 클래스 생성·등록. `column_types`/`business_key`/`composite_key_*`만 읽는다(그 외 키는 무시 — `product_tables.ANNOTATION_KEYS`의 근거). 테이블당 인덱스 2종 부착(~416–417) | ~352 |
| `sync_dynamic_tables_schema(engine)` | ⚠️ 이름과 달리 **존재하는 테이블의 ALTER 전용**(`has_table` 아니면 skip — 신규 CREATE 안 함). 부팅 경로에서만 호출 | ~439 |
| `_runtime_ddl_lock` | in-process DDL 직렬화 락(watchdog 스레드 vs reload-configs 요청 스레드) | ~476 |
| `create_missing_dynamic_tables(engine) -> list[str]` | **신규 테이블 한정 물리 CREATE**(이슈 #7) — information_schema 게이트 + `checkfirst=True` + 테이블별 독립 트랜잭션(실패 자체 rollback). 기존 테이블 런타임 ALTER는 범위 밖(C-8) | ~479 |
| `ensure_graph_tables(engine) -> list` | 그래프 3테이블 생성(#7 패턴: 게이트+checkfirst+락+실패 격리) | ~520 |
| `ensure_ingestion_checkpoint_table(engine)` | [P2] `file_ingestion_checkpoints` 생성(동일 패턴) | ~557 |
| `refresh_dynamic_models(engine=None) -> list[str]` | **핫리로드 공용 진입점** — config 디스크 재로드 → `crud.TABLE_CONFIG` 싱글턴 갱신(빈/손상 config 시 기존 보존) → `init_dynamic_models` → engine 지정 시 물리 CREATE(+그래프 테이블 보장). 호출처: main `reload_local_process_cache` / config_watcher(간접) / run_watcher·chain worker·graph worker SYSTEM_RELOAD | ~590 |

### `server/ontology_config.py` (**531줄**, `b8307c2` ~305에서 **+226**, 그중 🆕🆕🆕 **`68db020`이 +68**) — 온톨로지 매핑 v2 로더/검증

> 🔑 **이 라운드의 주제는 "스킵이 로그 한 줄에만 존재했다"는 것이다.** 컬럼 하나가 개명되면 그 테이블의 온톨로지가 **통째로** 사라지는데, 성공 건수만 세는 표면에서는 "안 자랐다"와 "죽었다"가 구별되지 않았다. `rejections` 수집기가 그 구별을 데이터로 만든다.
>
> 🆕🆕🆕 **[2026-08-11 후속 · `68db020`] 그래프 노드/엣지 정체성이 맵 정체성을 상속하는 토큰이 생겼다.** `identity`나 `edges[].target_identity_from`에 리터럴 **`"@map_key_columns"`**(=`INHERIT_MAP_IDENTITY`)를 넣으면 `_expand_identity`가 그 자리를 `map_overlay.derive_binding_parts(table)["key_columns"]`로 치환한다. 🔴 **토큰이 명시적인 이유**: 노드 정체성은 흔히 "맵 정체성 + 무언가"라서(셀 = 맵 + 좌표) "키를 생략하면 상속"이라는 암묵 규칙으로는 합성을 표현할 수 없다. `identity` 자체를 통째로 생략하면 여전히 "맵 정체성 그대로"를 뜻한다. `target_identity_from`은 토큰을 받아도 **부재는 그대로 에러**다 — 엣지는 다른 테이블의 노드를 가리키므로 이 매핑이 상속할 "그" 정체성이 없다.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `_unknown_keys(raw, allowed, where)` | 미지 키 거부 — 허용목록 `_ALLOWED_TABLE_KEYS`(~63)/`_ALLOWED_NODE_KEYS`(~64)/`_ALLOWED_EDGE_KEYS`(~65)/`_ALLOWED_PROP_KEYS`(~69)/`_ALLOWED_SPATIAL_KEYS`(~70)/`_NODE_CLASSES`(~75, `{static,dynamic}`). `__` 접두 키는 어디서나 주석으로 허용 | 96 |
| 🆕🆕🆕 **`_as_col_list(value)`** | **[`68db020` 신설]** 컬럼명 문자열 또는 리스트를 리스트로 정규화하는 헬퍼 — `identity`/`target_identity_from` 파싱이 공유 | 111 |
| 🆕🆕🆕 **`INHERIT_MAP_IDENTITY = "@map_key_columns"`** | **[`68db020` 신설]** 정체성 상속 토큰 리터럴 — config가 쓰는 유일한 어휘 | 138 |
| 🆕🆕🆕 **`_map_identity_columns(table_name) -> list\|None`** | **[`68db020` 신설]** `map_overlay.derive_binding_parts(table_name)["key_columns"]`를 그대로 되돌린다 — **두 번째 `table_config` 리더가 아니다.** 맵 레이어가 상속하는 바로 그 함수를 그래프도 부르므로 "웨이퍼가 무엇으로 불리는가"를 두 계층이 다르게 답할 수 없다. 실패(유도 불가)는 예외를 삼키고 경고 후 None | 141 |
| **`_expand_identity(cols, table_name, where) -> (expanded\|None, err\|None)`** | **[`68db020` 신설]** `cols`에서 `INHERIT_MAP_IDENTITY`를 `_map_identity_columns`의 결과로 치환(중복 제거). 유도 불가면 테이블명·사유를 댄 에러 문자열 | 160 |
| **`_normalize_props(raw_props, where, allow_spatial=True)`** | props → `[{"col": str, "spatial": dict\|None}]` + `(list, error)`. ⚠️ 노드는 기본값으로, **엣지는 `allow_spatial=False`**로 부른다 | 178 |
| **`_EDGE_SPATIAL_REFUSAL`** (상수) | 🔴 **엣지 prop의 `spatial` 선언을 이름으로 거부하는 메시지.** 근거는 실제 구현이다: `graph_materializer.extract_graph_items`는 `spatial_meta`를 **`node_cfg["props"]`에서만** 만들고 엣지 루프는 `p["col"]` 외에 아무것도 읽지 않는다. 그래서 종전엔 엣지 spatial이 **검증 통과 → 저장 → 조용히 폐기**됐다(선언의 침묵사 — 미지 키 거부가 닫는 것과 같은 계급의 결함). 안내는 "노드를 소유한 테이블의 node prop으로 선언하거나 `spatial` 키를 빼라"이고, 엣지 좌표를 진짜 원하게 되면 **그것을 구현하는 같은 커밋에서 이 거부를 지운다**고 주석이 못박는다 | 86 |
| `_validate_table_mapping(table_name, raw, known_tables)` | 테이블 1건 검증 — 정규화 노드에 `node_class`, 테이블에 `event_time_column`이 실린다. 🆕🆕🆕 **[`68db020`] 노드 `identity`와 엣지별 `target_identity_from`을 `_expand_identity`에 통과시킨 뒤** 나머지 검증(컬럼 존재 등)을 이어간다 | 227 |
| **`_record(rejections, scope, table, reason)`** | 수집기에 `{scope, table, reason}` 1건 누적 — **`rejections is None`이면 no-op**. scope 어휘: `"file"`(파일 자체가 안 읽힘·객체 아님·v1 키) · `"table"`(테이블 1건 거부) · `"enrichment"`(RESOLVED_AS 승격이 룰 로딩 실패로 안 돌았다) | 355 |
| **`validate_ontology_mapping(raw_config, known_tables=None, rejections=None) -> dict`** | v2 검증 — description 필수, 컬럼 존재 검증, 테이블 단위 스킵, 공간 속성 파싱, v1/`__`키 무시. **반환 형태는 수집기 유무와 무관하게 동일**하고 파라미터는 키워드 옵션이라 기존 호출자(`graph_sync_worker._load_graph_mappings`·`graph_materializer`·`crud`)는 호출도 비용도 그대로다 | 371 |
| `synthesize_enrichment_mappings(mappings, enrichment_rules) -> dict` | enrichment rule → `RESOLVED_AS` 엣지 자동 승격(`source_override="user"`, 사용자 정의 우선) | 427 |
| **`load_ontology_mappings(path=None, known_tables=None, include_enrichment=True, rejections=None) -> dict`** | 로드 진입점. 수집기를 넘기는 소비자 **3곳**: `GET /graph/mapping-summary`(기존 응답에 `rejected`+`rejected_count` **추가** — 새 엔드포인트 안 만들었다) · `main._chip_trace_declaration` · `graph_orphans.load_declaration` | 494 |

### `server/graph_orphans.py` — [신설] → [§5-A](#5-a-2026-07-30-신설-서버-모듈-8종)

### `server/graph_materializer.py` (**602줄**, +27) — 그래프 승격 코어

> **이 라운드의 변경은 시그니처가 아니라 `extract_graph_items` 안의 [INV-O-2] `event_time_column` 동작이다** — 선언 컬럼에서 행별 `row_event_time`을 뽑고, 그 컬럼이 해석되지 않을 때 **인제션 시각으로 폴백하는 것을 명시적으로 거부**한다(NULL은 "시각 미상"이고 시간 필터를 항상 통과한다). `unresolved_event_times/len(rows)`를 세어 경고하므로 "선언됐으나 해석 불가"가 조용할 수 없다.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `compose_identity(values) -> str\|None` | identity 조립 — `"\|"` 조인 + 이스케이프(`\`→`\\`, `\|`→`\\\|`) + float 정수 안정화. **`graph_orphans`가 생산 가능성 판정에 이 함수를 재사용한다**(두 번째 identity 구현 방지) | ~54 |
| `flatten_payload_data(data)` / `extract_graph_items(table_name, rows, mapping, ...)` | 이벤트 행 → 노드/엣지 산출. 엣지 소스 = source_override 또는 식별 컬럼 winner들의 **최저 서열(보수적)**. `spatial_meta`는 **node props에서만** 만든다(위 `_EDGE_SPATIAL_REFUSAL`의 근거) | ~89/100 |
| `bulk_upsert_nodes(db, node_map, chunk_size=CHUNK_SIZE) -> dict` | 방언별 ON CONFLICT + props shallow-merge(PG `\|\|`) | ~235 |
| `_retarget_stale_edges(db, rows, chunk_size=CHUNK_SIZE, ...) -> int` | 재교정 시 `(from_node, type, source_row_ref)` 스코프 stale 타깃 삭제. 🔴 **엣지만 지우고 남은 노드는 아무것도 지우지 않는다** — 그것이 `graph_orphans` 스윕이 생긴 이유다([§5-A](#5-a-2026-07-30-신설-서버-모듈-8종)) | **276** |
| `bulk_upsert_edges(db, edges, node_ids, chunk_size=CHUNK_SIZE, ...) -> int` | 엣지 벌크 UPSERT | ~328 |
| `materialize_rows(...)` / `materialize_events(db, events, mappings, chunk_size) -> stats` | 증분 소비 본체(DELETE 스킵+카운트) | ~385/400 |
| `_edge_provenance_cols(mapping)` / `_load_best_cell_sources(...)` / `attach_col_sources(db, table_name, rows, mapping)` | provenance 결정 단일 지점 — CellSource winner 로드(crud 서열, row_id IN 청킹). 증분·resync 공용 | ~459/468/500 |
| `resync_table(db, table_name, mappings, chunk_size=CHUNK_SIZE, row_ids=None, chunk_hook=None, stamp_synced=True) -> stats` | 백필/복구 — 키셋 청킹(C-7), row_ids 슬라이스 모드, Neo4j 청크 훅. ⚠️ **`keyset_scan`을 쓰지 않고 자체 순회 사본을 유지한다**(동시 라운드가 이 파일을 잡고 있었고, 그 유보가 `keyset_scan` docstring에 명시돼 있다) | ~518 |

### `server/graph_sync_worker.py` (**1,120줄**, `a82aa47` 1,097에서 **+23**) — 그래프 워커 (materializer 루프 + 백필 API :8090)

> ⚠️ **앵커 재측정 (2026-07-30 세 번째, `8cf9455` blob `79f0a51`)** — 이동 두 구간: **구 앵커 484 이전은 무이동**(`post_event_async` 본문이 자란 것이라 `to_local_str` ~455·`post_event_async` ~459는 제자리) **· 484–1078 +11 · `startup_event` 본문의 배너 블록 이후 +23**.
>
> 🔴 **이 절에는 blob 해시가 초록이던 시절에도 틀려 있던 앵커가 있었다** — 아래 `execute_manual_sync`가 `~940`으로 적혀 있었으나 `a82aa47` 실측은 **931**이었고, `run_graph_materializer_loop`는 `~630` vs 실측 **628**이었다. 둘 다 ±20 허용 안이라 아무도 걸리지 않았다. **허용 오차는 "재측정을 건너뛰어도 된다"가 아니다.**

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `ONTOLOGY_PATH` / **`VIRTUAL_GRAPH_PATH`** | `paths.config_path("ontology_mapping.json")` / **`<paths.DATA_ROOT>/database/virtual_graph.json`**. 후자가 `paths` 경유인 것은 이 파일이 **쓰기 대상**이기 때문 — `save_virtual_graph()`(~293)가 통째로 덮어쓰므로, `__file__`에서 조립하던 종전 코드로는 격리 워커가 **라이브 파일을 덮어썼다** | ~16/282 |
| **`post_event_async(endpoint, payload)`** | 🔴 **[`23a346d`] 두 번째 발신자, 같은 수리.** 맨 `requests.post`가 `internal_event_client.internal_event_session().post(...)`로 바뀌었고(`trust_env=False`), 비-`ok`는 `admin_auth.internal_event_failure_note`를 붙여 **누가 거부했는지**를 로그한다. 소스 주석이 근거를 명시한다 — **한 발신자에만 적용한 수리는 이 저장소가 이 엔드포인트 하나에서 이미 출하한 결함이다** | ~459 |
| `_load_graph_mappings()` / `_get_or_init_graph_cursor(db)` / `_advance_graph_cursor(db, last_id)` / `_lag_ms_from(created_at)` / `_reload_graph_worker_configs()` | 매핑 로드 / 커서 초기화(최초=현재 최대 outbox id) / 커서 전진 / 지연 계산 / SYSTEM_RELOAD 리로드(이슈 #8) | ~495/503/526/534/542 |
| **`publish_system_reload(reason: str) -> bool`** | 🔴 **[`530fdfd` 신설] "resync가 자기 자신을 알린다".** `DatabaseOutbox` 1행(`event_type="SYSTEM_RELOAD"`, `table_name="system"`, payload `{transaction_id: "graph_resync_<hex8>", timestamp, msg: reason, trigger: "graph_resync"}`)을 쓰고 **PG에서는 그 insert와 같은 트랜잭션 안에서 `NOTIFY outbox_event;`**를 발화한다(커밋 후 NOTIFY는 새 트랜잭션에 앉아 `Session.close()`가 롤백해 버려 **전 소비자를 조용히 2초 폴링 폴백으로 강등**시킨다 — `database.create_outbox_event`와 같은 모양). 실패는 로그 + `False`(이미 쓰인 resync를 실패시키지 않는다).<br>**고친 문제**: `execute_manual_sync`는 호출마다 `ontology_mapping.json`을 디스크에서 다시 읽는데 `run_graph_materializer_loop`는 **자기 인메모리 매핑 사본**을 outbox 배치에 `SYSTEM_RELOAD`가 나타날 때만 교체한다(이슈 #8). 그래서 "매핑 편집 후 resync"는 둘을 어긋난 채 남겼다 — resync는 **새** 선언으로 그래프를 쓰고 루프는 들어오는 행을 **옛** 선언으로 계속 승격했다(라이브 실측 2026-07-30: 40분간, 이미 파일에서 사라진 타입의 엣지가 그 뒤로 생성됐다). 이제 `/admin/reload-configs`와 **같은 레버**로 수렴한다.<br>**호출자는 프로덕션에 정확히 하나** — `execute_manual_sync` 안의 클로저 `_announce(reason)`가 `asyncio.to_thread`로 부르고, 발화 경로는 **3곳**(단일 테이블 `no_mapping` 반환 · 매핑 테이블 없음 `no_mapping` 반환 · 성공 resync 후 — 테이블별 `batch_refresh_required` 브로드캐스트보다 **먼저**). 잘못된 테이블명(400)은 부르지 않는다(발효된 것이 없다). 테스트: `test_ontology_reload_and_sweep.py::test_publish_system_reload_writes_one_outbox_row` | **~566** |
| `run_graph_materializer_loop()` | **메인 루프** — LISTEN/NOTIFY + keyset 커서, 배치 본체 `_run_one_batch`(**~670**)를 `asyncio.to_thread` 격리, `[GraphLatency]` 계측. `GRAPH_BATCH_LIMIT=1000`(~492) | **~639** |
| `get_row_data_for_sync(db, table_name, row_ids)` | ⚠️ DEPRECATED(신규 배선 금지) | ~739 |
| `_neo4j_chunk_hook_factory(table_name)` | Neo4j 병행 경로 청크 훅(G3 인터페이스 보존) | ~919 |
| `execute_manual_sync(table_name, row_ids) -> dict` | `/sync` 백필 — 키셋 청킹 + 테이블당 `batch_refresh_required` 1건 + to_thread, `"all"` 지원. **`_announce` 클로저로 `publish_system_reload`를 3경로에서 발화** | **~942**(구 지도의 `~940`은 `a82aa47` 실측 931과도 달랐다) |
| `to_local_str(dt)` | ⚠️ **`utils/time_format.to_local_str`의 중복 사본이고 tz 처리가 없다** — 맨 `strftime`이라 naive UTC를 로컬 시각으로 보고한다. 통합 미착지([§5-A](#5-a-2026-07-30-신설-서버-모듈-8종)) | ~455 |
| `startup_event()` (`:8090` FastAPI 앱) | 🆕 **[`23a346d`] 첫 줄이 `internal_event_client.startup_lines("GraphSync Worker")`이고 자체 `try/except`로 감싸여 있다** — 모델 초기화에 실패하는 프로세스도 **자기가 무엇을 제시했을지는 말해야** 하고, 반대로 **진단이 워커의 기동을 막는 것이 되어서는 안 된다**. 세 데몬 중 이 하나만 `try`를 두른 것은 여기가 FastAPI 이벤트 훅이라 raise가 앱 기동을 죽이기 때문 | ~1078 |

### `server/parsers/std_parser.py` (~222줄) — 무스크립트 표준 파서
| 시그니처 | 역할 | 라인 |
|---|---|---|
| `is_std_supported(file_path) -> bool` | 확장자 게이트(csv/tsv/txt) | ~31 |
| `_resolve_delimiter` / `_build_header_map` / `_resolve_key_groups` / `_row_has_key` / `_map_record` | 구분자 추정·헤더↔컬럼 매핑·키 검증 | ~36–127 |
| `_iter_rows(file_path, encoding, delimiter, header_map, key_groups)` | 스트리밍 행 이터레이터 | ~144 |
| `parse_std_file(file_path, table_info, table_name) -> (row_iter, total_rows, skipped_no_key)` | **진입점** — 키 결측 행은 스킵 카운트(파일 전체 거부 안 함), 헤더 실패 시 ValueError | ~155 |

### `server/enrichment_config.py` (**676줄**, `c520012` 585에서 **+63** — `f9289f6`) — 인리치먼트 규칙 로더/검증

> 🔴 **하나의 선언, 두 개의 실행 형태 — 이 절에서 제일 잘못 읽히기 쉬운 자리다.** `execute_reference_view`와 `execute_candidate_probe`는 **같은 `view` dict를 받고 같은 바인드를 요구하지만 다른 질문에 답한다.** 잘못 고르면 예외도 경고도 없이 **답이 조용히 바뀐다** — 아래 표의 두 행을 반드시 함께 읽어라.
>
> 🆕 **[`f9289f6`] 그리고 이제 그 둘이 **같은 실행 래퍼**를 공유한다 — `_isolated_execute`(**~470**).** 사용자 SQL을 도는 자리는 이 파일에 정확히 둘(`~543` · `~597`)이고 **양쪽 다 이 함수를 통과한다.** 세 번째 자리를 만들면 이 규율이 즉시 깨지므로, 새 실행 형태가 필요하면 **여기를 다시 부르는 형태로** 만들어라.
>
> 📐 **앵커 주의 — 구 지도 대비 이동폭이 여섯 구간이다**(`_isolated_execute` 51줄이 `ReferenceViewError` 바로 뒤에 들어왔다): **구 443 이전 무이동 · 444–462 +6 · 463–485 +57 · 486–508 +55 · 509–535 +57 · 536–540 +61 · 541–546 +60 · 547 이후 +63.** 즉 **로더 절반(~68–420)은 한 줄도 안 움직였고** 실행 절반만 통째로 밀렸다.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| **`_record(rejections, scope, subject, detail)`** | **[F9 신설] 무효 선언 1건을 선택적 수집기에 남긴다** — `{scope, subject, detail}`. `ontology_config._record`와 같은 자세이고 같은 이유다(로그에만 있는 스킵은 아무도 못 보는 스킵이다). 🔴 **명명된 사유는 여기서 싣지 않는다** — 닫힌 어휘로의 사상은 **보고서 계층**([§5-B](#5-b-serverconfig_resolve_reportpy--내-config가-먹었는가의-답-f3fd785-신설))의 책임이고 로더는 사람이 읽을 구체적 사유만 만든다. 수집기 미제공이면 **기존 동작 그대로**(로그만)라 기존 호출자는 무영향 | **~68** |
| `_is_str_list` / `_resolve_view_query` / **`_validate_view_sql(sql, decision_key)`** | 참조 뷰 SQL 검증(SELECT 전용 등). ⚠️ **`enrichment_analysis.analyze_promotions`가 제안 생성 시 이 private 함수를 이름으로 부른다** — 통과 못 한 뷰는 제안이 아니라 **conflict**로 보고된다 | **~83/89/111** |
| `required_bind_params(sql) -> set` | 바인드 파라미터 추출(`_BIND_PARAM_RE` ~59) | **~133** |
| **`_normalize_candidate_for(rule_name, label, raw, target_fields, rejections=None) -> dict`** | **[① `candidate_for: {target_field: view_column}` 정규화]** — 자동확정의 후보 컬럼은 **선언되고, 유도되지 않는다**. 이름 매칭으로 했다면 이 config에서 바로 쓰레기를 확정한다(두 뷰가 `wafer_id`를 노출하는데 하나는 (lot,slot) 키라 후보 1개, 하나는 lot 단독이라 N개). **무효 항목은 그 항목만 버리고 뷰 자체는 표시용으로 살린다.** 🔴 **형태 검증(`_CANDIDATE_COLUMN_RE` ~65, `^[A-Za-z_][A-Za-z0-9_]*$`)이 실행보다 먼저 오는 것이 계약이다** — 이 이름은 아래 `CANDIDATE_GROUP_WRAP_SQL`에 **보간**된다(바인딩할 수 없는 식별자다). **존재** 여부는 SQL을 돌려야 알 수 있으므로 로드 시점에 검증하지 않고 해석 시점의 이름 있는 거절(`candidate_column_missing`)로 다룬다 | **~144** |
| `_normalize_reference_views(rule_name, raw_views, decision_key, target_fields=None, rejections=None)` / `_validate_rule(name, raw, known_tables, rejections=None) -> tuple` | 규칙 정규화·검증. **[F9] `_validate_rule`이 `auto_confirm_declared`(bool, **~330**)를 정규화 결과에 싣는다** — "노브를 false로 **선언**했다"와 "노브가 **없다**"는 같은 동작이지만 다른 문장이고, 보고서가 그 둘을 다르게 말하는 근거가 이 한 필드다 | **~194/242** |
| `validate_enrichment_rules(raw_config, known_tables=None, rejections=None) -> list` | 전체 검증 진입점. **반환값 형태는 수집기 유무와 무관하게 동일** | **~344** |
| `load_enrichment_rules(path=None, known_tables=None, rejections=None)` / `load_enrichment_chain_rules(path=None, known_tables=None)` | 로드 / **체인 룰 형태로 변환**(rule["enrichment"] 내장). 🔴 **파일 부재는 거부가 아니다** — 빈 목록을 돌려주고 **수집기에 남기지 않는다**(`/graph/mapping-summary`가 `source.exists`로 하는 것과 같은 규율). 읽기 실패·형태 오류만 `_record`로 남는다 | **~373/396** |
| 🆕 **`_isolated_execute(db, stmt, params) -> (columns, rows)`** | **[`f9289f6` 신설] 사용자가 쓴 참조 문장 1건을 SAVEPOINT 안에서 실행한다** — `db.begin_nested()` → 실패면 `nested.rollback()` 후 re-raise, 성공이면 `nested.commit()`. **호출자 둘뿐이고 그 둘이 이 파일의 SQL 실행 전부다**(`execute_reference_view` 안 **~543** · `execute_candidate_probe` 안 **~597**).<br>🔴 **왜 `try/except`가 아니라 SAVEPOINT인가 — docstring(**~471–507**)에 라이브 읽기 전용 실측이 있다.** PG에서 실패한 문장은 **둘러싼 트랜잭션을 abort**시키고, 그 뒤 같은 커넥션의 모든 문장이 `InFailedSqlTransaction`을 낸다. 조용해지는 지점은 그다음이다: **abort된 트랜잭션에서 `COMMIT`은 정상 반환하고** 서버는 그것을 ROLLBACK으로 바꾼다. 즉 **드라이버 예외를 잡는 것은 봉쇄가 아니다** — 세션은 이미 죽었고 호출자도 로그도 그것을 알 수 없다. 실측 4줄: 나쁜 SELECT → `ProgrammingError` / 다음 SELECT → `InternalError`(세션 오염) / `db.commit()` → **정상 반환**(서버는 롤백) / 같은 것을 SAVEPOINT 안에서 → 다음 SELECT **성공**.<br>🔴 **그 위에 두 가지가 얹혀 있었고 둘 다 깨져 있었다**: ① `enrichment_candidates._diagnose_probe_failure`가 **같은 세션에서** 뷰를 재조회해 `candidate_column_missing`과 `view_error`를 가른다 — abort된 세션에선 그 재조회가 실패밖에 못 하므로 **PG에서 `candidate_column_missing`은 도달 불가**였다(진단이 존재하는 유일한 이유가 그 사유다). ② 체인 워커가 훅의 예외를 삼키므로 **오염된 세션이 `process_pending_groups`로 탈출**해 `processed_chain=True` 커밋이 롤백되고 그룹이 영원히 재생됐다([§4](#4-serverchain_ingestion_workerpy--체인-워커)).<br>⚠️ **pysqlite에는 그 규칙이 없다**(SELECT에 트랜잭션을 열지도 않는다) — 그래서 스위트가 **프로덕션이 도달할 수 없는 거절을 인증**할 수 있었다. 규칙을 테스트에 복원하는 폴트 인젝션은 `server/tests/test_enrichment_candidates.py`의 `pg_abort_semantics`다. 비용은 참조 문장당 왕복 2회(SAVEPOINT+RELEASE) | **~470** |
| **`execute_reference_view(db, view, bind_params=None) -> (columns, rows)`** / `class ReferenceViewError` | **① 표시(display) 실행 형태 — 사람에게 보여줄 「행」을 만든다.** `REFERENCE_LIMIT_WRAP_SQL`(**~421**)로 감싸 **뷰가 선언한 `limit`**(기본 `DEFAULT_REFERENCE_LIMIT` 200 ~55, 상한 `MAX_REFERENCE_LIMIT` 1000 ~56)을 서버가 강제한다. 바인드는 `_probe_params`(**~549**)가 **SQL이 실제로 요구하는 이름만** 추려 넘기고, 요구 바인드가 빠졌으면 실행하지 않고 `ReferenceViewError`(**~466**)를 올린다(드라이버 예외를 삼켜 "후보 없음"으로 위장하지 않는다). **실행은 `_isolated_execute` 경유**(**~543**). 소비: `GET /enrichment/rules/{r}/references/{i}`([§1.4](#14-api-라우트-표--어드민운영그래프맵인리치먼트)) · `enrichment_candidates._diagnose_probe_failure` | **~521/466** |
| **`execute_candidate_probe(db, view, column, bind_params=None) -> dict`** | **② 후보 프로브(probe) 실행 형태 — 「이 컬럼의 distinct 값이 몇 개인가」에 답한다.** `CANDIDATE_GROUP_WRAP_SQL`(**~451**)로 **뷰 결과 전체에 GROUP BY**를 걸고 반환은 `{"pairs": [(value, count)…], "scanned", "row_truncated", "distinct_truncated"}`. 실행은 `_isolated_execute` 경유(**~597**).<br>🔴 **왜 형제 정의가 필요한가 (2026-07-30 실측)**: 라이브 뷰 `공정 이력(wafer_process)`는 `limit: 50`인데 (lot,slot) 하나당 행이 최소 69·평균 135.4·최대 217이라 **80개 키 전부가 상한을 넘는다.** distinct 계산이 서버가 행을 자른 **뒤** 파이썬에서 일어나면 51번째 행이 다른 `wafer_id`를 날라도 보이지 않고 **`ambiguous`가 영영 발화하지 않는다** — 오늘의 `single` 판정이 아무도 검사하지 않는 가정 위에 있었다는 뜻이다. **뷰를 고치지 않는 이유는 두 번째 소비자(사람의 표시)가 시간순 행을 필요로 하기 때문**이고, 그래서 선언은 하나로 두고 실행 형태만 갈랐다.<br>🔴 **컬럼 참조를 반드시 별칭으로 한정한다**(`__enrichment_ref."{column}"`) — SQLite는 큰따옴표 안의 이름이 컬럼으로 안 풀리면 **문자열 리터럴로 강등**하므로 `SELECT "not_a_column"`이 에러가 아니라 값 1개를 돌려주고, 프로브는 그것을 **후보 1개로 읽어 컬럼명 자체를 자동 확정**한다(이 모듈이 절대 하지 말아야 할 거짓말이 정확히 그것이다). 한정하면 SQLite도 `no such column`으로 실패해 `candidate_column_missing` 진단으로 흘러간다.<br>🆕 **[`f9289f6`] `scanned`는 이제 창 함수 `SUM(COUNT(*)) OVER ()`에서 온다**(SQL 본문 **~452**, 언팩 **~605**: `raw[0][2]`). 창 함수는 GROUP BY **뒤**·LIMIT **앞**에 평가되므로 바깥 LIMIT이 그룹을 잘라내도 이 값은 **잘리기 전 전체 합**이다. 🔴 **종전엔 반환된(=잘린) 그룹의 count만 합산**해 `scanned`가 과소 보고됐고, 그 값이 `CANDIDATE_PROBE_MAX_ROWS`와 비교되던 탓에 **진짜로 잘린 읽기가 `row_truncated=False`로 읽힐 수 있었다.** 그룹 절단과 행 절단은 별개 사실이므로 별개로 센다(PG는 numeric을 돌려주므로 호출부에서 int로 접는다).<br>🔴 **절단 둘을 구분해서 보고하되 「둘 다 잘린 읽기」다**: `distinct_truncated`(distinct 값이 `limit`을 넘음 — `limit+1`을 요청해 증명) · `row_truncated`(스캔이 `CANDIDATE_PROBE_MAX_ROWS`에 닿음). ⚠️ **구 지도가 「`distinct_truncated`는 이미 2개 이상이라 호출자의 `ambiguous`로 자연히 흘러간다」고 적은 것은 틀렸다** — 호출자가 `clean_str_value`로 값을 **접기** 때문이다([§5-A `enrichment_candidates`](#5-a-2026-07-30-신설-서버-모듈-8종)). 지금은 **둘 다 이름 있는 거절**이다 | **~555** |
| **`CANDIDATE_PROBE_MAX_ROWS = 5000`** | 프로브가 훑을 **행** 상한. 뷰의 `limit`(표시용)과 **별개이고 운영 노브가 아니다.** GROUP BY는 상위 LIMIT으로 조기 종료할 수 없으므로 **바인드 없는 뷰**(`required_binds == []`)가 선언되면 키마다 전체 테이블을 훑는다 — 1,000만 행 규율의 유일한 방어선. 실측 최대 217행의 약 23배 | **~463** |
| `to_public_rule(rule) -> dict` | 클라이언트 공개용 필드만 추출. **[F9 `f3fd785`] `reference_views[]`가 `{label}` → `{label, candidate_for}`로 넓어졌다**(가산적, 총괄 승인) — 「어느 뷰가 어느 `target_field`의 후보 원천인가」를 클라가 **스스로 유도하지 않게 하는 유일한 길**이고, 노출되는 컬럼명은 참조뷰 응답 헤더에 이미 나타나므로 **신규 노출 0**이다(쿼리 본문·`limit`은 그대로 비노출). **[`1fefd12`] `queue_filters` 동봉** — "큐 항목"의 **서버 단일 정의**: 전 decision_key `notBlank` AND 전 target_field `blank`(제네릭 `/tables/{t}/data` 필터 DSL 형태). 판단키가 빈 행은 사람이 해소할 수 없으므로 워크리스트에 절대 안 뜬다 — 워크리스트(`enrichment.js`)·어드민 결손 카운트(`admin.js`)·메인 그리드 배지(`ui.js`) 3소비처가 **같은 객체**를 소비해 수치가 어긋날 수 없다. **[2026-07-30] 소비처가 4번째로 늘었다** — `enrichment_analysis._queue_condition`이 이 `queue_filters`를 받아 `main.get_column_filter_condition`으로 번역하므로 **리포트도 같은 정의를 쓴다**([§5-A](#5-a-2026-07-30-신설-서버-모듈-8종)) | **~614** |

### `server/enrichment_mapper.py` (~177줄) — 인리치먼트 dedup 맵퍼
| 시그니처 | 역할 | 라인 |
|---|---|---|
| `_recount_affected_keys(db, source_table, decision_key, key_raw_values) -> dict` | 영향 키의 소스 행 재집계 | ~33 |
| `map_enrichment_dedup(db, payloads, rule=None)` | **진입점**(체인 워커가 호출) — 배치 payload → decision_key당 1행 upsert 목록 생성 | ~64 |

### `server/ingestion_activity.py` (~149줄) — [P1 신규] 인제션 진행 스냅샷 레지스트리
웹서버 인메모리(스레드 안전). 유입 3종: ① `/internal/events/ingestion-state`(heavy 명시 통지) ② `file_ingestion_progress` 브로드캐스트 인터셉트(normal 엔트리는 이 경로로만 생성 — lane 비오염) ③ file-processed 시 제거. 파일명 키는 `get_basename` 정규화로 일치. 모듈 싱글턴 `registry`.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `STALE_ENTRY_TTL_SECONDS=30분` / `STALE_QUEUED_TTL_SECONDS=24h` | 고아 퇴거 TTL — 상태별 차등(QA F1: QUEUED는 24h, watcher 재기동 스윕이 자가 치유) | ~25/33 |
| `class IngestionActivityRegistry` | 레지스트리 본체(생성자에 ttl 주입 가능 — 테스트용) | ~36 |
| ├ `apply_state(state)` | QUEUED/PROCESSING/FINISHED 상태 반영(FINISHED=제거, 멱등) | ~67 |
| ├ `apply_progress(table_name, filename, progress, processed_rows, total_rows)` | 진행률 병합(없으면 normal 엔트리 생성) | ~95 |
| ├ `remove(table_name, filename)` | 멱등 제거 | ~115 |
| └ `_ttl_for(entry)` / `snapshot() -> list` / `clear()` | 상태별 TTL / **조회 스냅샷(+TTL 퇴거)** — `/admin/file-ingestion/active`가 서빙 / 초기화 | ~122/126/143 |

### `server/bonding_plan.py` (**1,049줄**, `d3ed167` 932에서 **+117**) — [본딩 M1] 역할 바인딩 config 로더 + 집계 코어
> 🟢 **심볼 실측 완료** — 이 절의 심볼은 **`5609ff0`의 커밋된 blob에 존재함이 확인됐고, 그 뒤 HEAD가 움직인 다음 재대조에서도 동일했다**(워킹트리 아님). 🔴 **라인 번호는 싣지 않는다** — 위치는 `git grep -n "<심볼>" -- <경로>`로 확정하라. 숫자가 남아 있는 곳은 **파일 줄 수**이거나, 이름이 없는 덩어리를 가리키며 측정 sha가 함께 적힌 자리뿐이다.

`paths.config_path("bonding_plan_config.json")`(gitignored, `.sample` tracked) — 역할(process_history/defect/eds_fail/used_chips/total_chips)→실테이블·컬럼 바인딩. 테스트: `tests/test_bonding_plan.py` · 🆕 `tests/test_optional_role_absence.py`(400줄) · 🆕 `tests/test_binding_refusal.py`(339줄) · 🆕 `tests/test_transfer_plan_derivation.py`(423줄).


> 🆕 🔴 **[신설 축 ①] N14 — 「어디서 읽는지 모르면 그 질문은 답할 수 없고, 답할 수 없음은 YES가 아니다」.**
> `fail_values`는 **어느 값이 fail인가**를 말하고 `val`은 **어디서 읽는가**를 말한다. `val` 없이 세면 **풀 전체가 fail로 표시**되고 상한 불변식이 깨진다(실측: `val` 한 줄을 지우자 fail 칩이 0 → **144**가 됐는데 `remaining_reliable`은 여전히 `true`였다). 그래서 모듈은 **거부하고, 0을 서빙하고, 강등한다.**
> - **`compose_status_marker(status, marker)`** — `connected(...)` 어휘의 **단일 조립기**. 두 번째 강등 사유가 같은 문자열 수술의 두 번째 철자를 키우지 못하게 뽑아냈다.
> - **`FAIL_VALUE_COLUMN_ABSENT = "fail_value_column_absent"`** / 🔴 **`fail_filter_status(src_cfg, cols, status)` — 술어 하나, fail을 세는 모든 독자가 이것을 부른다.** `transfer_plan._fail_filter_status`는 **호출 시점에 속성을 읽는 얇은 통과**라, 이 함수를 다시 가리키면 모든 독자가 한 번에 무장 해제된다.
>
> 🆕 🔴 **[신설 축 ②] 유도 — 같은 사실의 세 번째 철자를 없앤다.**
> `map_overlay_config.json`이 이미 테이블마다 `x`/`y`/`val`을 선언하는데 계획 config가 운영자에게 **다시 타이핑을 요구**하고 있었다. 2026-08-04의 오타(`dt_x`인 테이블에 `"x": "x"`)가 정확히 거기 떨어졌다.
> - **`DERIVED_ROLE_OF = {"x":"x","y":"y","val":"val","bin":"val"}`** · `DERIVATION_DECLARED`/`DERIVATION_DERIVED`/`DERIVATION_UNAVAILABLE` · `_OVERLAY_MEMO`/`_overlay_config_snapshot()`, `(path, mtime_ns, size)`로 메모) · **`_map_binding_for(table)` — `fallback_guess` 값 컬럼은 value 역할에 대해 *거부*한다.**
> - 🔴 **`resolve_effective_columns(source_cfg, required)` — 명시 선언이 언제나 이긴다.** 전부 선언된 config는 **같은 객체를 그대로** 돌려받는다(무회귀).
> - ⚠️ **선택 역할은 절대 유도하지 않는다** — 부재가 곧 거절이 되는 자리에서만 부재를 메운다.
>
> 🆕 🔴 **[신설 축 ③] 거절이 자기 원인을 말한다.** *"두 주에 세 번, 멀쩡해 보이는 선언이 조용히 먹지 않았다."* 화면은 언제나 「선언돼 있지 않습니다」였다 — 선언은 있었는데도.
> - `BINDING_NOT_DECLARED`·`BINDING_MAPPING_UNAVAILABLE`·`BINDING_COLUMN_MISSING`·`BINDING_NOT_REACHED` / `BINDING_REFUSALS` — 🔴 **각 이름이 `config_resolve_report`/`enrichment_candidates`의 정본과 **같은 값임을 테스트가 핀**한다**(상류 개명이 두 번째 철자를 남기지 못하게).
> - `_REFUSAL_COLUMN_HINTS = 24` · `_model_column_names(model)` · **`explain_binding_refusal(src_cfg, required, label, where=None) -> tuple`** · `deletion_hints(src_cfg, roles, model)`, 「이 줄을 지우면 무엇이 유도되는가」).

> 🆕 🔴 **[`2c2a777` 2026-08-04] 이 파일이 「보조 감산은 선언 자체가 선택」 어휘의 정본이다 — `transfer_plan.py`가 여기서 import한다.**
> - **`STATUS_NOT_DECLARED = "not_declared"`** · **`role_is_declared(block, key) -> bool`** — 본문은 한 줄(`isinstance(block, dict) and key in block`)이고 그 한 줄이 계약 전부다: **키가 진짜로 없을 때만** 미선언이다. 키가 있는데 값이 쓰레기면(오타 바인딩·null) 그것은 **선언이고 종전대로 `missing`으로 강등**된다. 🔴 **이 구분이 요점이다** — 「선언하지 않았다」와 「선언했는데 깨졌다」를 같은 상태로 뭉개면 오타가 조용한 면제가 된다.
> - **`SUBTRACTION_ROLES = ("defect", "eds_fail", "used_chips")`** — `remaining = total − defect − eds_fail − used`의 감산항 목록. 응답의 `inactive_subtractions`는 이 셋 중 `STATUS_NOT_DECLARED`인 것만 걷는다(**비었으면 필드 자체를 세우지 않는다** — 전 역할 선언 사이트의 페이로드는 바이트 동일).
> - ⚠️ **`total_chips`는 명시적으로 예외다**(맵 역할 루프) — 분모는 여전히 필수다. 분모가 미선언이면 셀 수 자체를 모르므로 완화할 것이 없다.
> - ⚠️ **`map_overlay.py:953`과 `map_preset_routing.py:90`이 각자 `STATUS_NOT_DECLARED = "not_declared"`를 따로 선언한다** — 같은 리터럴이지만 **import한 것이 아니라 우연히 일치하는 별개 어휘**다. 이 파일의 상수를 고쳐도 그 둘은 따라오지 않는다.

> **좌표 변환은 이 모듈에 없다 (2026-07-27 일원화).** 구 `normalize_align`/`make_align_transform`/`align_status_label`은 **삭제**됐고 정렬은 `map_overlay.resolve_map_transform`(메타 델타 유도)을 경유한다. `sources[].align` config 선언도 폐기 — 정렬의 근거는 `wafer_map_metadata` 하나뿐이다.

| 시그니처 | 역할 |
|---|---|
| `CONFIG_PATH` / `ROLES` / `HISTORY_LIMIT=50` / `MAX_REGION_RECTS=50` / `MAX_REGION_POINTS=100k` | 역할 어휘·이력 상한·region 하드캡 |
| `CANONICAL_FRAME_ROLES` (상수) | canonical(CORE) 프레임 후보 순서 `("total_chips","defect","eds_fail")` — **좌표를 바인딩한 첫 역할**이 기준을 정의하며 그 역할에 메타가 없으면 canonical은 None(뒤 역할로 넘어가지 않는다 — 넘어가면 회전된 계측 맵이 기준을 참칭해 조용히 identity가 된다) |
| `load_bonding_plan_config(path=None) -> dict` / `_valid_source(src)` | config 로드·검증(미연결 역할은 부분 가동) |
| `parse_region(region_str)` / `clamp_rects(rects, grid)` / `_point_in_rects(x, y, rects)` | region rects 파서(잘못된 형식 → 400 소재) / canonical 메타 치수로 클램프(완전 밖 rect 제거) / 점 포함 판정 |
| `load_map_meta(db, config, target_table, map_id, cache=None)` | wafer_map_metadata의 **grid_metadata 원본 dict** 조회(config `map_metadata` 바인딩 경유). 정렬 유도의 근거이므로 격자 치수만 잘라 쓰면 안 된다. `cache`는 요청 경계 스냅샷(N+1 금지) |
| `load_grid_meta(db, config, target_table, map_id, cache=None)` | 격자 규격만 필요한 호출자용 축약(region rect 클램프 전용) |
| 🆕 `declared_map_pairs(sources_cfg, map_id_for) -> list` | 선언된 `(table, map_id)` 쌍 |
| 🆕 **`canonical_basis(db, config, map_pairs, meta_cache: dict = None)`** | **[신설 — 종전 지도에 없던 심볼]** 정준 프레임의 근거를 고른다. 짝 상수 `CANONICAL_FRAME_ROLES` · `BASIS_CONFIRMATION` · `BASIS_ROLE_ORDER` |
| **`class _ResolvedColumns(dict)` / `_unresolved_roles(cols)` / `_demote_for_unresolved(status, cols)`** | **[`1fefd12` 신설] 선언-미해석 컬럼의 침묵 제거.** 종전엔 선언됐지만 모델에 없는 **옵션** 컬럼(config 오타)이 조용히 skip돼 집계가 무음으로 오염됐다. `_resolve_model_columns`가 미해석 역할키를 `.unresolved` 튜플로 실어 나르고, 각 status 기록 지점이 `connected` → **`connected(column_unresolved:<roles>)`**로 합성한다(기존 강등 어휘 `connected(area_only)`·`connected(align_unavailable)`와 같은 문법. required 미해석은 종전대로 바인딩 전체 실패). **`transfer_plan.py`도 이 셋을 재사용**(공유 기계장치는 resolver 옆에 산다) |
| `_resolve_model_columns(source_cfg, required)` / `_fetch_points(db, cols, filters, distinct_pairs=False)` | 바인딩 해석 — **반환 cols는 `_ResolvedColumns`** / 좌표 페치(하드캡 적용) |
| `get_core_summary(db, lot, slot, rects=None, config=None) -> dict` | **집계 진입점** — 역할별 카운트(맵 모드 fail_values 필터, used_chips distinct), `remaining = total − defect − eds_fail − used`(음수 가능 — 과도기), history 50건+warnings, region 교차(좌표 하드캡 100k, 응답 미포함). 좌표 정렬은 `map_overlay.resolve_map_transform` + `map_overlay.align_status_label` 위임. **[`1fefd12`] `fail_values` 선언 + `val` 미해석이면 필터 없는 카운트를 거부**하고 0 + 강등 status(전 행을 fail로 세는 반대 방향 오염 차단, align_unavailable과 같은 규율) |
| **[7b `b697d34`] 맵 정체성·조회 키의 정규화 위임** | 이 모듈은 map_id 합성기도 lot/slot 필터 생성기도 **자체 구현하지 않는다**: 합성은 `map_overlay.compose_map_id`, "no second implementation" 주석), 풀 바인드 필터는 `map_overlay.canonical_role_value`. 근거는 **선언 컬럼 타입**이다 — `slot`이 number 선언이면 `'01'`과 `1`이 같은 키여야 하고, 그 판정은 값이 아니라 `table_config`가 한다([§5 `map_overlay.py`](#5-소형-서버-모듈)) |

> ✅ **A2 해소 (2026-07-27)** — bbox 항 없는 사본은 삭제됐다. 착수 전제였던 "휴면"은 사실이 아니었다 — `bonding_plan_config.json`·`transfer_plan_config.json` 둘 다 `eds_fail`에 `rotation:180`을 라이브로 선언하고 있었고, 그 값은 `eds_fail_map` 메타의 rotation과 동일했다(선언이 메타의 중복). 라이브 규격(40×40)은 bbox가 0이라 두 구현 결과가 1288셀 전건 일치 → **가용량 수치 변화 없음**. [히스토리](../history/20260727_004500_align_consolidation_meta_single_source.md)

### `server/ingestion_checkpoint.py` (🆕⑤ **587줄** @`831ab68` — 종전 등재 ~258에서 **+329**) — [P2] 오프셋 체크포인트 + 2-tier 재처리 방지 원장

> 🆕⑤ 🔴 **[2026-08-13 실측] 이 표에서 라인 번호를 전부 걷어냈다** — 위치는 `git grep -n "<심볼>" -- server/ingestion_checkpoint.py`로 확정하라. 낡은 라인은 **실재하는 다른 함수**를 가리키며 멀쩡해 보이고, 낡은 심볼은 Grep 0건으로 자기가 낡았다고 말한다.

저장소는 테이블 **`file_ingestion_checkpoints`**(유일 키는 여전히 `(table_name, file_signature)` = `idx_fic_identity` **하나뿐**). `FileIngestionLog`에 컬럼을 붙이지 않은 이유는 `create_all`이 ALTER를 하지 않아 **조회 프로세스보다 먼저 도는 마이그레이션**이 필요해지기 때문(운영 DB `UndefinedColumn` 500 회피 — 총괄 승인 판단).

🆕⑤ 🔴 **[`ba664c5`·`831ab68`] 재처리 방지가 2단이 됐다 — 그리고 그것이 「파일을 옮기지 않기로 한 것」의 대가다.** 종전에 「이 파일은 처리했다/실패했다」는 사실은 **파일의 위치**(`archives/`·`err/`)가 들고 있었다. 보존 모드(`archive_processed_files: false`)에서는 그 표현 수단이 사라지므로 사실이 **원장으로** 이사한다.
- **tier 1 = 경로 + stat** — `(table_name, filepath, file_mtime, file_size)`가 전부 일치하고 상태가 종결이면 **해시를 아예 계산하지 않고** 결론이 난다. 전용 인덱스 `idx_fic_path_stat`.
- **tier 2 = 내용 시그니처** — 종전의 `sha256:` dedup. tier 1이 miss하면 여기로 떨어진다(**miss가 안전한 방향**).
- **NULL 계약** — 세 컬럼은 `nullable=True`를 유지한다. SQL `=`는 NULL에 참이 될 수 없으므로 **이 컬럼들이 없던 시절에 적힌 행은 tier 1에 절대 걸리지 않는다.**
- **유일성 계약** — `(table_name, filepath)`는 **UNIQUE가 아니다**(한 경로가 시간에 따라 여러 내용을 담는다). 그래서 tier-1 조회는 여러 행을 만날 수 있고 **전순서로 하나를 고른다**(`updated_at desc, id desc`, SCHEMA_CANON R7).

테스트: `tests/test_ingestion_checkpoint.py`(**26개** @`831ab68`) · 🆕⑤ **`tests/test_ingestion_ledger_tier1.py`(신설 428줄, `grep -c "def test_" = 17`)**.

| 시그니처 / 상수 | 역할 |
|---|---|
| `SIGNATURE_ALGO="sha256"` / `STATUS_IN_PROGRESS` / `STATUS_DONE` / `FORCE_REINGEST_TOKEN="__force__"` | 시그니처 알고리즘·상태 어휘·강제 재처리 파일명 토큰 |
| 🆕⑤ **`STATUS_FAILED = "FAILED"`** / **`TERMINAL_STATUSES = (STATUS_DONE, STATUS_FAILED)`** | **종결이되 성공이 아닌 상태**와 「이 파일에 대해 이미 결론이 났다」 집합. 🔴 **tier 1은 이 집합으로 스킵하고, tier 2(내용 dedup)는 여전히 `DONE`만으로 스킵한다** — 두 tier의 술어가 일부러 다르다 |
| 🆕⑤ **`STAT_SIGNATURE_PREFIX = "stat"`** | **내용을 읽지 못한 파일**의 실패를 기록할 때 쓰는 원장 키의 접두. 접두가 `sha256:`과 다르므로 내용 시그니처와 **충돌할 수 없다**. 없던 시절엔 그런 파일의 실패는 적힐 곳이 없어(유일 키가 `file_signature`) `err/` 이동도 없이 **재기동마다 영원히 재시도**됐다 |
| `compute_file_signature(file_path) -> str\|None` | **전체 파일** 1MB 스트리밍 해시(`_HASH_CHUNK_BYTES`) → `sha256:<size>:<digest>`. 샘플링 아님 — 500MB 0.535초 실측(드릴 총 415초의 0.004%)이라 정확성을 택했다. `OSError`면 경고 후 None(체크포인트·dedup 비활성), `PermissionError`는 **재raise**(호출자 재시도 경로로) |
| `is_force_reingest(filename) -> bool` | 파일명에 `__force__` 토큰(대소문자 무시). 🔴 **tier 1도 tier 2와 똑같이 이 검사를 먼저 통과해야 한다** |
| 🆕⑤ **`mtime_ns_to_datetime(mtime_ns) -> datetime`** | `st_mtime_ns` → **마이크로초로 절삭된** tz-aware UTC. 🔴 **정수 연산이 의도다** — `datetime.fromtimestamp(st.st_mtime)`은 float를 거치고 tier 1은 이 값을 `=`로 비교하므로, 비트 단위로 재현되지 않는 값은 **조용히 miss**하고 fast path가 소리 없이 사라진다. 반올림이 아니라 절삭인 이유는 `timestamptz`가 저장하는 정밀도가 그것이기 때문(쓴 값 = 다음 스윕이 다시 유도한 값) |
| 🆕⑤ **`read_file_stat(file_path) -> (datetime, int) \| None`** | tier-1 키를 만드는 `os.stat` **1회**. `None`(사라짐·stat 불가)이면 tier 1이 miss → 기존 전체 해시 경로 |
| 🆕⑤ **`stat_identity_signature(file_stat) -> str \| None`** | `stat:<size>:<micros>`. **오직 실패 기록에만** 쓰인다 — dedup 판정에는 절대 쓰이지 않는다 |
| `class CheckpointPlan` (+`disabled(note)` classmethod, `is_resume` property) | 파일 1건의 계획 값 객체 — 비활성 사유(note)도 detail·이력에 노출 |
| `find_checkpoint(db, table_name, file_signature)` / `find_completed_ingestion(...)` | UNIQUE 인덱스 단일행 조회 / 동일 내용 `DONE` 여부(tier-2 dedup 판정) |
| 🆕⑤ **`find_terminal_by_path_stat(db, table_name, filepath, file_stat)`** | **tier 1(단건).** 같은 경로·같은 `(mtime, size)`로 이미 종결된 행 하나, 없으면 `None`. `idx_fic_path_stat`를 그대로 탄다. **전순서**(`updated_at desc, id desc`) 후 `.first()` |
| 🆕⑤ **`TIER1_BATCH_SIZE = 500`** | 한 tier-1 질의가 답하는 파일 수. 🔴 **추측이 아니라 실측이다** — 격리 `assy_qa`에서 2,001파일 / 52,001행 원장, 3회 중앙값(2026-08-13): batch **50→0.37 · 100→0.46 · 250→0.41 · 500→0.41 · 1000→0.59 · 2000→1.26** ms/file. 50~500이 평평하고 그 뒤 열화 — **전 2,001파일을 한 질의로 묶으면 500짜리 다섯 번보다 3배 나쁘다.** 한계는 PostgreSQL의 바인드 파라미터 상한(65,535; 파일당 3개 → 청크당 ~1,500)이 아니라 **OR 아리티에 따라 커지는 플래닝**이다. 22,626파일 트리를 **46질의**로 유지 |
| 🆕⑤ **`find_terminal_by_path_stat_batch(db, table_name, entries, batch_size=None) -> {filepath: row}`** | **tier 1(배치).** `entries`는 `(filepath, file_stat)` 이터러블. 🔴 **술어를 파이썬으로 재유도하지 않는다** — 파일마다 단건 질의와 **글자 그대로 같은** `and_(filepath==, file_mtime==, file_size==)` 삼중항을 만들어 `or_`로 묶고, 같은 `table_name` + `status IN (TERMINAL)` 아래 둔다. 파이썬에서 stat을 비교하면 `DateTime(timezone=True)`가 백엔드마다 **어떻게 돌아오는지**(SQLite는 naive, PostgreSQL은 세션 타임존)를 다시 유도하게 되고, 틀리면 **전부 지우거나 하나도 못 지우거나** 둘 다 무음이다. 승자 선정도 단건과 같은 전순서를 청크 전체에 걸고 경로당 첫 행을 취한다(전역 정렬 스트림을 한 경로로 제한해도 그 경로의 내부 순서는 보존된다). 🔴 **「예/아니오」가 아니라 `row`를 돌려주는 이유는 `status`가 호출부에서 `archives/` vs `err/`를 가르기 때문이다.** 경로 중복은 먼저 제거한다(중복 OR 항 + 늦은 청크가 이른 청크의 승자를 덮는 것 방지) |
| `plan_ingestion(db, table_name, file_signature, filename, filepath, total_rows, source_kind, force_restart=False, file_stat=None) -> CheckpointPlan` | **재개 판정** — `force_restart` 아님 ∧ `status != DONE` ∧ `source_kind` 일치 ∧ `total_rows` 일치 ∧ `0 ≤ processed_rows ≤ total_rows`가 **전부** 성립할 때만 `resume_from = processed_rows`. 하나라도 어긋나면 0부터 + `[resume-abort] … 사유:` note를 WARNING·`row.note`에 남긴다(조용한 재처리 금지). 🆕⑤ **`file_stat`이 오면 tier-1 조회 키를 같이 심는다** — 심는 값은 **적재를 시작한 시점의 파일 모습**이라, 도중에 파일이 바뀌면 다음 스윕의 tier 1이 miss해 재적재로 떨어진다(안전한 방향) |
| 🆕⑤ **`record_failure(db, table_name, file_signature, filename, filepath, reason, file_stat=None) -> bool`** | 실패를 **원장에 종결 상태로**(`status=FAILED`) 남긴다 — `err/`라는 **위치**의 대체물. 없으면 ⓐ 운영자가 '무엇이 왜 실패했나'를 못 묻고 ⓑ 스윕이 재기동마다 같은 파일을 영원히 재시도한다. 사람이 읽는 사유·트레이스는 종전대로 `FileIngestionLog(status="FAILED")`에 남고 **둘은 `filepath`로 이어진다** |
| 🆕⑤ **`adopt_new_location(db, row, filepath, file_stat) -> bool`** | tier-2 적중 시 **새 경로를 원장에 기록**한다. 유일 키가 `(table_name, file_signature)` 하나뿐이라 **한 내용은 경로를 하나만 기억할 수 있다** — 그래서 tier 1이 다음번에 무엇을 볼지가 여기서 정해진다 |
| `record_chunk_progress(db, plan, processed_rows, chunk_index)` | **청크 적재와 같은 세션·같은 트랜잭션**에서 오프셋 Core UPDATE — "커밋된 행 수 == 기록된 오프셋" 원자성의 근거 |
| `mark_done(db, plan, processed_rows=None, note=None)` | 성공 확정(`status=DONE`) — 이후 dedup skip 대상 |

### `server/map_overlay.py` (**2,712줄** @`68db020` — 직전 등재 2,526에서 **+186**) — [M2 신규] 범용 맵 오버레이 (계획 전용 아님 — 맵 인프라)

> 🆕🆕🆕 🔴 **[2026-08-11 후속 재측정 · `68db020`] 바인딩 해석이 블록 단위에서 키 단위로 다시 설계됐다.** 종전 `resolve_binding_parts`(당시엔 없었다 — 종전은 `_derive_table_binding_full`/`derive_table_binding`이 바인딩 전체를 all-or-nothing으로 풀었다)는 `map_overlay_config.table_bindings.<t>.columns`가 **하나라도 있으면 그 블록 전체**를 그대로 채택했다. 그래서 운영자가 `core_wafer_map`의 `key_columns`만 지우고 `table_config`를 따르게 하려 하면 `map_key_columns`를 상속하는 대신 **은퇴된 관례값 `["lot","slot"]`**로 조용히 채워졌다(2026-08-10 사고의 기전). 지금은 **키마다 독립으로** `선언 > table_config 유도(`derive_binding_parts`) > 이름을 대고 거절` 순으로 풀린다 — `derive_table_binding`은 하위호환 별칭으로 남았고 내부에서 `_derive_table_binding_full`을 그대로 쓴다.
>
> 🆕🆕🆕 신설: **`BINDING_KEYS = ("x", "y", "val", "index", "key_columns")`** · **`ORIGIN_DECLARED`/`ORIGIN_INHERITED`/`ORIGIN_ABSENT`/`ORIGIN_REFUSED`**(각각 `"declared"`/`"inherited"`/`"absent"`/`"refused"`) · **`derive_binding_parts(table, val_candidates=None, allow_guess=False) -> (parts: dict, guessed: bool)`**(`table_config` 단독에서 **키별로** 유도 — `index`는 절대 유도하지 않는다, 이름 관례가 없다) · **`resolve_binding_parts(cfg, table, allow_guess=False) -> (binding|None, provenance: dict, guessed: bool)`**(유일한 해석기 — `provenance`는 `BINDING_KEYS` 전량에 대해 `{value, origin, from}`을 채운다. 선언된 컬럼이 `table_config`에 없으면 그 **키만이 아니라 바인딩 전체를 거절**하고 로그 한 줄로 이름을 댄다) · `_known_columns(table)`(내부 헬퍼).
>
> 🔴 **`resolve_binding`/`resolve_binding_info`는 이제 `resolve_binding_parts`에 위임하는 얇은 래퍼다.** `resolve_binding_info`(반환 계약 무변경 — `{x,y,val,index,key_columns[],source}`)만 `allow_guess=True`로 부른다. ⚠️ **`val`은 선언이 하나라도 있는 블록에서는 상속되지 않는다** — `val` 부재는 "이 맵은 값이 없다(occupancy-only)"는 **적극적 진술**이라, 상속하면 선언하지 않은 값 컬럼을 조용히 얹혀 채점 성격이 바뀐다(`test_map_alignment_columns`가 고정). 순수 유도(선언 0건)에서는 종전처럼 `val` 무매칭 시 거절.

> 🟢 **심볼 실측(2026-08-11 후속 재측정)** — 이 절의 심볼은 **`68db020`의 커밋된 blob**에서 `def`/`class` 정의를 grep해 확인했다(호출부 아님, 워킹트리 아님). 🔴 **라인 번호는 싣지 않는다** — 위치는 `git grep -n "<심볼>" -- <경로>`로 확정하라. 숫자가 남아 있는 곳은 **파일 줄 수**이거나, 이름이 없는 덩어리를 가리키며 측정 sha가 함께 적힌 자리뿐이다.

> 🔴 **[2026-08-06] 이 절은 라인 앵커를 걷어냈다.** 걷어내기 전에 전건 실측했는데 **근사(`~NNN`) 표기가 최대 1,000줄 이상 어긋나 있었다** — 그 측정이 심볼 목록이 옳다는 근거이고, 그래서 **심볼만 남기고 숫자를 버렸다.**

> 🆕 🔴 **[D7] 출처 어휘가 확장됐다 — 그리고 이 파일에는 *목록이 없다*.** 토큰은 **개별 모듈 상수**로 선언되며 얼려진 튜플·집합·리스트가 **한 곳도 없다.** 그래서 「N번째 토큰」식 서술은 여기서 검증할 대상이 없다 — **전건 열거만이 검증 가능한 형태다**:
>
> | 상수 | 값 |
> |---|---|
> | `GEOMETRY_DECLARED` | `"declared"` — 누군가 쟀다 |
> | `GEOMETRY_AUTO_REGISTERED` | `"auto_registered"` — 값은 있지만 선언이 아니다 |
> | `GEOMETRY_ABSENT` | `"absent"` — 여섯 phys 키 중 하나 이상이 없다 |
> | `GEOMETRY_UNPARSABLE` | `"unparsable"` — 키는 있는데 수가 아니다 |
> | `GEOMETRY_ASSUMED` | `"assumed"` — 값은 바닥에서 빌려 왔다 |
> | 🆕 **`GEOMETRY_CONFIRMED`** | `"confirmed"` — **확정 아래 파생됐다. 선언은 아니다** |
> | `ORIENTATION_INDETERMINATE` | `"indeterminate"` — 값은 있으나 선언의 증거가 없다 |
>
> ⚠️ **두 함수가 서로 다른 부분집합을 낸다** — 이 구분을 접으면 서술이 조용히 거짓이 된다. `geometry_declaration(meta)`는 `indeterminate`를 **절대 내지 않고**, `orientation_declaration(meta)`만이 축별 `"source"`로 `indeterminate`를 낸다.
>
> 🔴 **소스 안의 주석 둘이 이미 거짓이다**(이 지도가 고칠 수 없는 자리 — 코드 소관): **`map_overlay.py:572`가 반환을 「다섯 토큰」이라 적는데 실제로 여섯을 낼 수 있고**, **`:756`은 「`geometry_declaration`의 네 토큰」이라 적는다.** 개수를 적은 서술이 낡는 그 방식 그대로다.
>
> 🆕 **확정 마커 키**: **`PHYS_CONFIRMED_KEY`, `"phys_confirmed_from"`)** · **`FRAME_CONFIRMED_KEY`, `"frame_confirmed_from"`)**. 둘에 실리는 값은 `{table, map_id, confirmation_uid, confirmed_by, confirmed_at}`이고 **조성 지점은 `frame_confirmation.py`**다. 클라 짝은 [`map2/declaration.js`](#7-a--map-editor-2--map_editor2html--client2srcmap2-2026-08-0506-신설)의 동명 키.
>
> **메타 접근 상태**: `META_ACCESS_OK`/`_UNDECLARED`/`_QUERY_FAILED`/`_PROBE_BROKEN` · `meta_access_state(db)` · `_probe_key_fault` · `_meta_select`.
> **기하 판정·차용**: `geometry_declaration` · `geometry_refusal` · `geometry_computable` · `assume_phys_from(meta, basis_meta, basis=None)` · `assume_grid_from(meta, basis_meta, basis=None)` · `AUTO_REGISTERED_KEY`/`PHYS_ASSUMED_KEY`/`GRID_ASSUMED_KEY`.
> **방위 선언**: `_read_rotation`/`_read_side`/`_read_y_invert`/`_read_grid_start` · `orientation_declaration` · `orientation_refusal` · `ORIENTATION_KEYS`.
> **격자 치수**: `grid_dims(meta)` · `grid_box(meta)`.

> ✅ **`apply_valid_die_ref(meta, ref) -> dict`는 실재한다.** 짝: `parse_valid_die_ref` · **`valid_die_chain_error(ref, ref_meta, home)` — [M4② INV-6] 2단 체인 거부: 참조된 맵이 **자기 `valid_die_ref`를 또 갖고 있으면** 조용히 중간 맵의 저장 셀로 해석되는데 그것은 운영자가 선언한 집합이 아니다)** · `valid_die_redirect_note` · `valid_die_ref_display` · `resolve_valid_die_basis` · `resolve_valid_die_set` · `_resolve_valid_die_uncached` · `circle_die_mask` · `load_map_meta_cached` · `_valid_die_refused`. 상수 `VALID_DIE_REF_KEY` · `VALID_DIE_TABLE` · `MAX_VALID_DIE_CELLS=20_000` · `STATUS_NOT_DECLARED`, **실패가 아니다**)/`STATUS_REF_UNAVAILABLE` · `SOURCE_CIRCLE`/`SOURCE_REF`/**`SOURCE_REFUSED` — 선언은 있는데 못 풀었다: **원으로 되돌아가지 않는다**)**.
`paths.config_path("map_overlay_config.json")`(gitignored, `.sample` tracked) — 키 구조만: `table_bindings.{table}.columns{x,y,val,key_columns}`, `paint_lock.{"*"|table}{enabled,blocking_values,from_overlay,message}`, **[U6] `value_column_candidates`(순서 있는 배열 — 선언은 기본값을 **통째로 대체**)** · **[U6] `default_legend`(행 형태 `{value,desc,color,locked}` — 미선언 = 기본 의미론 없음)**. `APIRouter` 없음 — `main.py`가 `@app.get`으로 직접 등록해 위임한다. 테스트: `tests/test_map_overlay.py`.

> **삭제된 선언 레이어 (2026-07-27, `4ba13ae`)** — `align_overrides`(config 선언)·`by_eqp` 분기·`align_override_declared` status·`_frame_grid_of`가 **전부 제거**됐다. 정렬의 근거는 이제 `wafer_map_metadata` 하나뿐이며 `resolve_align`은 **메타만** 받는다. config에 `align_overrides`나 `sources[].align`을 다시 쓰는 코드를 보면 그것은 부활이 아니라 **오류**다.

| 시그니처 | 역할 |
|---|---|
| `MAX_OVERLAY_CELLS=20,000` / `MAX_OVERLAY_SOURCES=8` | 오버레이 1종당 셀 상한(초과 시 `truncated:true`) / 요청당 소스 상한 |
| `STATUS_OK` / `STATUS_ALIGN_UNAVAILABLE` / `STATUS_SOURCE_MISSING` / `STATUS_NO_DATA` | 엔트리 status 어휘 |
| `ALIGN_ORIGIN_DERIVED` / `ALIGN_ORIGIN_IDENTITY` | align 결정 출처 마커 — **둘뿐이다.** `DECLARED`/`DEFAULT`는 선언 레이어와 함께 삭제됐다 |
| `ALIGN_ORIGIN_UNRESOLVABLE` | 구 QA-B3 가드 유물 — **프레임 합성(A1) 도입 후 더 이상 발화하지 않는다**(상수만 잔존) |
| `load_overlay_config(path=None)` | config 로드(부재·손상 시 `{}` — 에러 아님) |
| **[7b `b697d34` 신설] 키 정규화 블록 ** — `_CANON_INT_RE` / **`canonical_key_value(value, col_type)`** / **`declared_column_type(table, column)`** / **`canonical_bind_value(table, column, value)`** / `canonical_role_value(src_cfg, role, value)` / **`compose_map_id(identity_cols, values, binding=None)`** | **맵 정체성·조회 키가 "선언된 컬럼 타입"으로 정규화되는 단일 지점.** `col_type == "number"`면 `'01'`·`' 1 '`·`1.0`이 전부 `'1'`이고(프로젝트의 단일 정수 판독기 의미론), 읽을 수 없는 값은 **원문 trim 그대로** 남아 조회가 정직하게 빗나간다(키를 지어내지 않는다). 비-number 선언에서도 **float 값**은 `3.0 → '3'`으로 접는다(repr 산물이지 데이터가 아니다 — `crud.clean_str_value`가 등록 경로에서 이미 고정하던 동작). 타입 조회는 **호출 시점**에 `crud.TABLE_CONFIG`를 읽는다(핫리로드가 dict를 제자리 변조하므로 스냅샷 금지). 소스 주석이 **"Do NOT write a second implementation"**을 명시하고, 실제로 `bonding_plan`·`transfer_plan`·`map_meta_registrar`·`build_key_filters`가 전부 여기로 위임한다 |
| `load_map_meta(db, target_table, map_id)` | `wafer_map_metadata`(`META_TABLE`의 `grid_metadata` 조회 |
| `_rotation_of` / `_grid_of` / `_side_of` / `_y_invert_of` / `PHYS_KEYS` / `_phys_signature` | 메타 정규화 헬퍼 — `_grid_of`는 메타 선언 그대로의 **물리(canonical) 격자 규격**, `_phys_signature`는 `phys_*` 6값 튜플(하나라도 없으면 None = bbox 재현 불가) |
| `frame_axes(meta)` | 프레임 정의 8축 튜플 `(rot, side, y_invert, start_x, start_y, cols, rows, phys_sig)` — identity 지름길 판정·transformer 캐시 키 |
| **`_frame_phys_params(meta)`** | **[A1]** 물리 규격 → **프레임 축 규격**. `is_cell_inside_wafer(c, r, …)`는 프레임 인덱스를 받으므로 rot 90/270에서 **칩 피치를 스왑**하고 back에서 `off_x` 부호를 뒤집는다. 유일 호출자는 `_frame_transformer`. **보정을 이 모듈 안에 가둔 것이 계약** — `WaferMapCoordinateTransformer`·`PhysicalWaferEngine`은 무수정(`bonding_plan.py`가 같은 클래스를 공유) |
| `_FRAME_TF_CACHE` / 🆕🆕 **`_frame_transformer(meta, grid, box=None)`** | transformer(+engine) 생성 후 `frame_axes`(+ 상자) 키로 캐시(상한 512 초과 시 전체 clear). 🔴 **[`77b4388`] `box`가 뒤에 붙었다 — 두 번째 상자 *정의*가 아니라 밖에서 정해진 상자를 받는 자리다.** 상자가 무엇인가는 `origin_box` 하나만 답한다 |
| 🆕🆕 **`die_mask_from_reference(ref_meta, ref_cells) -> frozenset`** | 참조(유효 다이) 맵의 **저장 좌표 → 물리 다이 인덱스 집합**, 못 풀면 **빈 집합**. 클라의 `projectCellsToPhys(cells, refFrame)`와 같은 연산이고, 같은 이유로 참조를 **참조 자신의 프레임**으로 읽는다. 🔴 **물리 공간이어야 한다** — 저장(시각) 공간은 상자와 start의 함수인데 **상자야말로 지금 구하려는 것**이라 그 공간에 마스크를 두면 순환한다 |
| 🆕🆕 🔴 **`origin_box(meta, die_mask=None)`** / `_ORIGIN_BOX_CACHE`/`_ORIGIN_BOX_CACHE_MAX` | **[`77b4388`] 저장 좌표가 상대적으로 표현되는 그 사각형** — 클라 `getWaferBoundingBox`의 서버 짝이고 **근거가 둘인 것도 거기와 같다**: `die_mask`가 있으면 마스크가 프레임을 선언한 것, 없으면 **원**이 정한다(판정 술어는 `resolve_valid_die_basis(...)["source"] == SOURCE_REF`, 클라 술어는 `!circleOnly && !frame && validDieBasis() === 'ref'` — 두 구현이 `contracts/map_seam`의 `valid_die_basis_cases`로 함께 채점된다). 🔴 **왜 필요한가**: 확정이 소스 맵에 `valid_die_ref`를 적기 시작하면서 클라의 마스크 갈래가 실데이터에서 켜졌고, **부분 마스크에서 여덟 프레임 전부 상자가 갈렸다** — 그 차이가 그대로 `grid_start_x/y`의 오차다. ⚠️ **마스크가 이 격자에 한 칸도 안 앉으면 경고 후 원으로 되돌아간다**(빈 상자는 `(0,0,0,0)`으로 무너져 좌표계를 조용히 옮긴다 — **미상은 0이 아니다**). 캐시 키는 `(frame_axes(meta), die_mask)` |
| 🆕🆕 **`make_frame_transform(source_meta, target_meta, source_box=None, target_box=None)`** | **소스 프레임 → 물리 → 타깃 프레임** 합성 변환기(내부 `to_target(x, y)`. 메타/격자/phys 부재·물리 치수 불일치 시 `ValueError`. 🔴 **상자 둘이 뒤에 붙었다** — 각 맵의 원점 상자를 밖에서 준다(§`origin_box`) |
| 🆕🆕 `frame_linear_part(source_meta, target_meta)` / `apply_linear(mat, dx, dy)` / `_mat_mul` / `_side_matrix(side, rotated)` / `_ROT_FWD`/`_ROT_INV` | **프레임 변환의 선형(회전·거울) 부분만** 떼어 낸 2×2 행렬 계열. 평행이동과 상자를 빼고 나면 남는 것이 이것이고, `map_alignment`의 배치 페이로드(`linear`)가 이 값을 나른다 |
| 🆕🆕 `make_physical_transform(source_meta)` | 저장 좌표 → **물리 다이 인덱스** 단방향 변환기. `die_mask_from_reference`가 쓰는 것이 이것이다(원 상자 변환기 — 프레임 창 안에서는 참조가 자기를 마스크로 재단하지 않는다는 사실의 서버 쪽 철자) |
| `_align_summary(rotation, flip)` / `align_status_label(align)` | 표시용 요약 dict(변환에는 안 쓰인다) / 상태 문자열 마커 `aligned:180` 등 — **`bonding_plan`에서 이관**(변환 소유 모듈이 마커도 소유). 소비자: `bonding_plan.get_core_summary` · `transfer_plan._canonical_fail_set` |
| `resolve_align(source_meta, target_meta) -> (align\|None, origin, note)` | **align 결정 규율 — 인자는 메타 둘뿐이다.** 메타 델타 유도 > **identity**(메타 부재는 실패가 아니라 등록 누락 신호). origin은 `derived`/`identity` 둘뿐 |
| **`resolve_map_transform(source_meta, target_meta) -> (transform\|None, align, origin, note)`** | **서버의 단일 좌표 변환 진입점.** 오버레이(그리기)와 가용량 산출(`bonding_plan`/`transfer_plan`)이 **같은 이 함수**를 쓴다. transform None = identity, 계산 불가 시 `ValueError`(호출자가 `align_unavailable`로 표면화) |
| `_pure_translation(source_meta, target_meta, origin)` / `align_applied_payload(align, origin, note=None, translation=None)` | derived이고 rot/side/y_invert/격자/phys가 전부 같을 때만 `(dx,dy)` / 클라 표시용 `{rotation, flip, offset, origin, note?}` |
| `parse_sources(spec) -> [(table, key\|None)]` | `"table"` / `"table:key"` CSV 파싱 — 8종 초과·빈 값은 `ValueError`(→400) |
| **`DEFAULT_VAL_CANDIDATES`** / **`resolve_value_column_candidates(cfg) -> list`** / **`get_default_legend(cfg)`** | **[U6 `95bf072`]** 구 ~~`VAL_CANDIDATES`~~는 **documented default로 강등** — 튜플을 직접 읽으면 이 기본값이 대체하려던 하드코딩의 재생산이라, 소비는 반드시 `resolve_value_column_candidates(cfg)`(선언 > 기본값, 비어 있거나 불량이면 기본값) 경유 / 선언된 `default_legend` **그대로** \| None — 서버는 사용자가 선언하지 않은 행을 지어내지 않는다 |
| `_SYSTEM_COLUMNS` / **`_derive_table_binding_full(table, val_candidates=None) -> (binding\|None, guessed)`** | 순수 유도 코어(선언 0건 가정) — `guessed=True`는 값 컬럼이 후보 매칭이 아니라 **추측**(첫 비-키/비-좌표/비-시스템 컬럼)이라는 표지. **`resolve_binding_parts`의 `base`는 이제 이것이 아니라 `derive_binding_parts`가 만든다** — 이 함수는 `derive_table_binding`의 구현으로만 남았다 |
| 🆕🆕🆕 **`derive_binding_parts(table, val_candidates=None, allow_guess=False) -> (parts: dict, guessed: bool)`** | **[`68db020` 신설] `table_config` 단독 유도의 정본, 키별로 ABSENT를 허용한다.** `derive_table_binding`(all-or-nothing)과 달리 `core_x`/`core_y`처럼 좌표가 이름공간을 타는 테이블도 `key_columns`(`map_key_columns` 정본)는 유도해 낸다 — 정체성은 좌표와 별개로 상속 가능해야 한다는 것이 요점. `index`는 절대 유도하지 않는다(이름 관례가 없다 — 없는 컬럼을 "선언됐다"로 내보내면 그 축은 0건을 맞히고 화면은 "안 맞았다"로 읽는다). `allow_guess=True`는 `resolve_binding_info` 전용(값 컬럼 추측을 `fallback_guess`로 표기해 내보낸다) |
| `derive_table_binding(table, val_candidates=None)` | `_derive_table_binding_full`의 얇은 래퍼(`guessed=True`면 None으로 강등) — **[F2] 공개 유도는 추측을 거부한다** |
| 🆕🆕🆕 **`resolve_binding_parts(cfg, table, allow_guess=False) -> (binding\|None, provenance: dict, guessed: bool)`** | **[`68db020` 신설] 유일한 해석기 — 우선순위는 키마다 `선언 > table_config 유도(derive_binding_parts) > 이름을 대고 거절`.** `provenance`는 `BINDING_KEYS` 전량에 `{value, origin, from}`을 채운다(`config_resolve_report.DOMAIN_BINDING`이 그대로 렌더). 🔴 **선언된 컬럼이 `table_config`에 없으면 그 키만이 아니라 바인딩 전체를 거절**하고 `logger.warning`이 테이블·키·컬럼명을 댄다(고쳐도 소용없다 — 선언이 유도를 이기므로 **지워야** 상속된다). ⚠️ **`val`은 선언이 하나라도 있으면 상속되지 않는다** — 부재는 "이 맵은 occupancy-only"라는 진술이라, 상속하면 채점 성격이 조용히 바뀐다(`test_map_alignment_columns` 고정) |
| `resolve_binding(cfg, table) -> dict\|None` | 🔴 **[`68db020`] `resolve_binding_parts`에 위임하는 얇은 래퍼로 강등** — 반환 계약(바인딩 dict 또는 None) 무변경. [M3] `MapMetaCollector`의 **"이 테이블이 맵인가" 게이트**이기도 하다(None = 맵 아님 → 메타 등록 안 함) |
| **`resolve_binding_info(cfg, table) -> dict\|None`** | **[F1 `17f65bd` 신설, `68db020`에서 `resolve_binding_parts(allow_guess=True)`로 재구현] 클라 전달용 RESOLVED 바인딩 + 출처** — `GET /api/maps/paint-rules`가 서빙. 반환 계약 무변경: `{x, y, val, index, key_columns[], source: "declared"\|"derived"\|"fallback_guess"}`. `source`는 바인딩 전체를 대표하는 값(한 키라도 `declared`면 `"declared"`) — 키별 출처는 `resolve_binding_parts`의 `provenance`에만 있다. [F2] 추측은 여기서만 나가되 **반드시 `fallback_guess`로 표기** |
| **`map_key_parts(binding, map_key)`** | 복합 map_key를 key_columns 수만큼 조각내는 순수 분해기(마지막 컬럼이 나머지 흡수). `build_key_filters`·`canonical_map_key`가 공유 |
| `build_key_filters(model, binding, map_key)` | `_` 조인 복합 map_key를 key_columns로 분해해 ORM equality 필터 생성. **[7b] 각 조각은 `canonical_bind_value`를 통과** — 패딩된 `'01'`이 number 선언 컬럼에서 여전히 찾아진다 |
| **`canonical_map_key(table, binding, map_key) -> str`** | **[7b] 맵 키 문자열 자체의 캐노니컬 형태** — 조각별 `canonical_bind_value` 후 재조립. 클라 `map_editor.canonicalMapKey`와 **같은 벡터로 채점**된다(`contracts/map_seam`) |
| `get_overlay(db, cfg, target_table, target_key, sources, cell_cap=MAX_OVERLAY_CELLS) -> dict` | **메인 진입점** — 소스별 바인딩·align 해결 → 셀 조회 → 타깃 프레임 좌표 변환 → `{target, overlays[], cell_cap}`. **`eqp` 인자는 `by_eqp` 분기와 함께 삭제됐다**(엔드포인트 쿼리 파라미터만 no-op으로 존치 — 축소는 총괄 승인 사항) |
| `get_paint_rules(cfg, table=None) -> dict` | `paint_lock`의 `"*"` 기본 + 테이블별 선언 머지 → `{enabled, blocking_values, from_overlay, message}`. **[U6] main.py `/api/maps/paint-rules`가 이것과 U6 2종 + [F1] `binding`을 한 응답에 묶는다** |

#### `map_overlay.py` 안의 **[M4] 유효 다이 블록** 

**무엇이 유효 다이인가의 근거가 둘이 됐다** — 종전에는 **원 기하**(웨이퍼 마스크) 하나뿐이었고, 이제 `wafer_map_metadata.valid_die_ref`가 선언돼 있으면 **참조된 맵**이 근거다. ⭐ **가산적 공존이 수용 기준이다**: 선언이 없는 맵은 `2a9f6c4` 이전과 **바이트 단위로 같이** 동작해야 한다. 클라 짝은 `map_editor.js`의 `parseValidDieRef`/`validDieBasis`/`isValidDieAt`/`resolveValidDie`([§7](#7-client2src--웹-클라이언트))이고 양쪽은 `contracts/map_seam`의 **M4①** 계열로 같은 벡터에 채점된다. 테스트: **`server/tests/test_valid_die_ref.py`(709줄, 33건 — `grep -c "def test_" = 33`)**.

| 시그니처 | 역할 |
|---|---|
| `VALID_DIE_REF_KEY="valid_die_ref"` / **`MAX_VALID_DIE_CELLS=20,000`** / `_VALID_DIE_CACHE_MAX=64` | 메타 키 이름 / 셀 상한 — **초과 시 자르지 않고 거절한다**: 잘린 유효 다이 집합은 "맞아 보이는 틀린 집합"이라 절단이 곧 오답이다(오버레이의 `truncated:true`와 **다른 처분**) / 작업 단위 캐시 상한(넘치면 비운다 — 최악이 중복 해석 1회) |
| `STATUS_NOT_DECLARED` / `STATUS_REF_UNAVAILABLE` | **선언이 없다**(실패가 아니다) / **참조는 찾았으나 신뢰할 집합을 못 만들었다**(실패다) — 이 둘을 한 값으로 접으면 "선언 안 함"이 "고장"으로 보고된다 |
| `load_map_meta_cached(db, target_table, map_id, cache=None)` | 작업 단위 스냅샷 캐시를 낀 메타 조회(N+1 금지) |
| **`parse_valid_die_ref(meta, default_table=None)`** | 메타의 선언 원문 → `{table, map_id}` \| None \| 거부. **키 자체가 없으면 None(선언 없음)**, 있는데 못 읽으면 사유를 문자열로 — 클라 `parseValidDieRef`(`map_editor.js`의 미러 |
| `SOURCE_CIRCLE` / `SOURCE_REF` / **`SOURCE_REFUSED`** | 근거 3상태. **`refused`가 `circle`로 되돌아가지 않는 것이 계약**이다 — 선언이 있는데 못 풀었으면 원 기하는 답이 아니라 **다른 답**이고, 조용히 대체하면 사용자가 선언한 적 없는 마스크로 계획이 계산된다 |
| **`circle_die_mask(meta)`** | 선언이 없을 때의 근거 — 종전 원 기하 판정을 **이름 붙여 꺼낸 것**(동작 무변경) |
| `_basis_from_resolver(result)` / **`resolve_valid_die_basis(meta, resolver=None, table=None) -> dict`** | resolver 반환 정규화 / **판정 본체** — `{basis, source, reason}`. `resolver=None`이면 순수 함수로 동작(테스트·계약 하니스가 DB 없이 채점한다) |
| `_valid_die_refused(ref, status, detail)` / **`resolve_valid_die_set(db, cfg, target_table, target_key, …, cell_cap=MAX_VALID_DIE_CELLS) -> dict`** | 거부 페이로드 조성 / **DB 경로 진입점** — 미선언은 `{declared: False, …, status: not_declared}`로 **조용히** 답한다 |
| `_resolve_valid_die_uncached(db, cfg, ref, target_meta, cell_cap)` | 실제 해석 — 참조 맵 조회 → 프레임 정렬 → 셀 집합. 상한 초과·정렬 불가·행 부재는 전부 `ref_unavailable` |

> `resolve_binding`·`build_key_filters`는 **`transfer_plan.py`도 재사용**한다(모듈 간 공용 헬퍼 2개).
>
> **[7b] 정규화 소비자 지도 (`b697d34`)** — `canonical_*`/`compose_map_id`를 부르는 곳은 전부 **여기 위임**이고 사본이 없다: `bonding_plan` · `transfer_plan`(`_identity_filters` · `_origin_map_id` → `compose_map_id`) · `map_meta_registrar.compose_map_id` · 이 모듈의 `build_key_filters` / `canonical_map_key`. ⚠️ **소비자 쪽 라인은 적지 않는다** — 이 목록의 요점은 「사본이 없다」이지 「몇 번째 줄인가」가 아니고, 종전에 적혀 있던 8개 근사 앵커는 전부 낡아 있었다. 테스트: **`tests/test_key_canonicalization.py`(351줄, 10건 — `grep -c "def test_" = 10`)**.
>
> ✅ **[M4 phase 2]는 착지했다 — 종전 지도의 「HEAD에 없다」는 이제 거짓이다.** `apply_valid_die_ref`와 `valid_die_chain_error` 둘 다 실재한다. 🔴 **그 문장은 같은 절 첫 블록쿼트의 「`apply_valid_die_ref`는 이제 실재한다」와 정면으로 모순된 채 함께 실려 있었다** — 한 절이 자기 자신을 반박하고 있으면 **뒤에 오는 문장이 이겼다고 읽히지 않는다.** 두 서술 중 어느 쪽을 믿을지 독자가 고르게 두면 지도가 아니다.
>
> **소비자 지도 (2026-07-27 정렬 일원화 이후)**: 이 모듈의 정렬 함수군을 쓰는 것은 ① `/api/maps/overlay` 엔드포인트 ② **`bonding_plan.get_core_summary`** ③ **`transfer_plan._canonical_fail_set`** ④ `test_map_overlay.py`다. ②③이 이번에 배선됐고(구 A2), 그 결과 **정확한 구현이 운영 소비자를 갖게 됐다** — 종전에는 맞는 구현이 엔드포인트에서만 돌고 가용량은 안 고쳐진 사본으로 계산됐다. **맵 에디터 클라는 이 엔드포인트를 더 이상 호출하지 않는다**(변환은 클라 단일 구현 — [§7 `map_editor.js`](#7-client2src--웹-클라이언트)). `transfer_plan.py`는 정렬 함수 외에 바인딩·config 헬퍼 3개(`resolve_binding`/`build_key_filters`/`load_overlay_config`)도 쓴다.
>
> **구현 개수**: 서버 1(이 모듈) + 클라 1(렌더) = **2**. 가용량이 서버에서 계산되는 한 이것이 하한이다.

### 🆕 `server/map_alignment.py` — 프레임 정렬의 **채점자**

**크기: 6,528줄** @`c4a3159`(`68db020` 6,468에서 **+60** — `build_alignment_worklist`가 결정키 미충족 행을 살리는 가드 2종, 아래 표 참조. 그전 `7097a67` 6,395에서 **+73**). ⚠️ **제목에서 줄 수를 걷어냈다** — 제목에 박아 두니 파일이 자랄 때마다 **문서 안 링크가 통째로 깨졌다**(실측: 이 절을 가리키는 링크 넷이 전부 죽어 있었다).

> 🆕🆕🆕 🔴 **[2026-08-11 후속 · `68db020`] `basis_cells_for`가 이 파일로 이사해 공개됐다.** 종전엔 `frame_confirmation._basis_cells_for`가 **private**이었는데, 그 후계 체인(`mappers/dt_inventory_metadata_mapper`)이 손을 뻗어 그 private 함수를 부르고 있었다 — `frame_confirmation`을 은퇴시키면 자기 후계를 죽이는 모순이었다. 이 함수는 애초에 `frame_confirmation`이 아니라 여기 속했다: `_cells_of`를 감싸고 그 출력을 이 파일의 `confirmed_meta_for(basis_cells=...)`에 먹인다. **`mappers/dt_alignment_metadata_mapper`의 세 번째 손제작 사본도 이참에 없어지고 여기를 부른다** — 세 곳에서 같은 읽기를 다시 쓰지 않는다는 규율. |
> - **`basis_cells_for(db, reference: dict, cfg: dict = None) -> list \| None`** — 참조(유효 다이) 맵의 **셀 좌표 목록**, 못 읽으면 None(이름을 대고 경고 로그). **판 하나에 한 번 읽는다**(기여자 수와 무관) · **두 번째 셀 로더가 아니다** — `_cells_of`는 `/view`의 기준 맵 해석이 쓰는 바로 그 함수. `cfg` 미지정이면 1회 로드(호출자가 작업 경계에서 스냅샷을 이미 쥐고 있으면 그것을 전달) |

> 🆕🆕 🔴 **[2026-08-11 재측정 · `7097a67`] 두 번째 후보 축이 *교체*됐다 — 이 절에서 가장 위험한 낡음이다.** 종전 축은 `side`(거울, `front`/`back`)였고 지금은 **시작 모서리**(`top_left`/`top_right`, 철자는 `tl`/`tr`)다. `db1ee42`가 「두 번째 축은 거울이 아니라 걸음 방향」을 확정했고, `c4eaffa`·`014b5d3`·`3dc79e6`·`1fbd4b1`·`8d37cd1`이 그 축을 앵커·시작점·확정 원점까지 배선했다. 🔴 **후보 수는 여전히 8이다 — 4 회전 × 2 시작 모서리이고 면은 전부 `front`다**(`CANDIDATE_SIDE`). 거울 넷 위에 걸음 축을 *더하면* 16이 되고 모든 후보가 자기 쌍둥이와 동점이 된다(소스 주석이 실측으로 못박는다). 🔴 **`rot90_back` ≡ `rot270`@우상단**이므로 이것은 **개명이 아니라 다시 채점되는 축**이다.
>
> 🆕🆕 🔴 **삭제된 심볼 둘**: `load_alignment_sides(cfg)` · `SIDES_KEY`. 직전 지도가 아래 표에 **살아 있는 행으로** 등재하고 있었다 → [§0 ⑱](#0-묘비-목록--소스에-존재하지-않는-이름). `score_candidates`의 `sides=` 인자도 함께 사라졌다.
>
> 🔴 **`_ConsoleSafeHandler`는 이 파일이 정의하는 클래스가 아니다** — `utils/logger.ConsoleSafeHandler`에 대한 **모듈 레벨 별칭**(`_ConsoleSafeHandler = ConsoleSafeHandler`)이다. 이름을 남긴 것은 두 참조와 채점 블록 docstring이 그대로 읽히게 하기 위해서고, **여기서 클래스 정의를 찾으면 못 찾는다**([§6 `server/utils/logger.py`](#6-기타-서버-모듈-한줄-요약)).

> 🟢 **심볼 실측 완료(2026-08-11 재측정)** — 아래 표의 심볼과 시그니처는 **`7097a67`의 커밋된 blob**에서 **`def` 정의를 grep해** 확인했다(호출부 아님, 워킹트리 아님). 🔴 **라인 번호는 싣지 않는다** — 위치는 `git grep -n "^def <심볼>" -- server/map_alignment.py`로 확정하라.

> 🔴 **이 파일은 등재 시점(3,272줄) 이후 배로 늘었다.** 늘어난 것은 **정렬 채점 계열**이고 그 계열은 이 문서에도, 다른 어느 문서에도 없었다(QA 둘의 독립 관찰). 아래 표는 **좌표계·메타·기준 해석·워크리스트** 절반이고, 채점 계열은 별도 절 → **[§5-F](#5-f--정렬-채점-계열-index-scoring-family--servermap_alignmentpy-2026-08-07-등재)**.
>
> ⚠️ **이 파일의 라인은 세 라운드 연속으로 밀렸고, 같은 이름 하나가 그것을 매번 증명했다.** `direction_violations`의 **정의**는 `e943e46`에서 `1513` → `34d2518`에서 `1550` → 🆕🆕 **`7097a67`에서 `1653`**이다. 그동안 그 **호출부**는 `3079` → `3167` → … 로 따로 움직였다. 🔴 **이 문단의 숫자는 「그때 이랬다」는 *역사 서술*이지 앵커가 아니다** — 라인 인용이 실패하는 두 방식(밀리는 것 · **정의가 아니라 호출부**를 가리키는 것)이 한 이름에 다 들어 있어서 남겨 둔다. 위치는 언제나 `git grep -n "^def direction_violations" -- server/map_alignment.py`로 확정하라.

> **측정 기준**: `e943e46`의 커밋된 blob. `d3ed167`에는 **이 파일이 없었다.**
>
> 🔴 **출처 토큰을 하나도 선언하지 않는다** — 전부 `map_overlay.GEOMETRY_*`를 **한정 참조**로 소비한다. 사본을 만들지 않은 것이 계약이다.
>
> `frame_confirmation`은 **지연 import**다(`build_alignment_worklist` 안) — 두 모듈이 서로를 부르기 때문.

| 함수 | 시그니처 |
|---|---|
| `frame_text` | `frame_text(rotation: int, side: str) -> str` — 🆕🆕 **메타의 어휘**다(저장된 `rot*_front`/`rot*_back`). **후보의 어휘가 아니다** |
| 🆕🆕 **`candidate_text` / `parse_candidate`** | `candidate_text(rotation: int, start: str) -> str`(→ `rot90_tr`) / `parse_candidate(text) -> (rot, start) \| None` — 🔴 **레거시 `rot90_front`는 좌상단 시작으로 읽고, `rot90_back`은 후보가 *아니다***(거울은 탐색 공간에서 빠졌고, 저장된 그 값은 여전히 `parse_frame`이 **면**으로 읽는다) |
| `candidate_frames` | `candidate_frames() -> tuple` — 🆕🆕 **정확히 8** = `FRAME_ROTATIONS` × `CANDIDATE_STARTS`. **리터럴 목록을 만들지 않고 `parse_frame`(수용기)에 통과시켜 조립**하며, 수용기가 거부하면 `ValueError`로 죽는다 |
| 🆕🆕 **`candidate_start` / `left_to_right_of`** | `candidate_start(frame: str) -> str` / `left_to_right_of(frame: str) -> bool` — 🔴 **후보 철자 → `serpentine_index`의 `left_to_right` 대응은 여기 한 곳뿐이다.** 두 곳에서 적으면 채점과 진단이 다른 걸음을 잰다 |
| 🪦 ~~`load_alignment_sides` / `SIDES_KEY`~~ | **삭제됐다**(`db1ee42`) — 거울 축이 후보 공간에서 빠지면서 config의 `sides` 선언도 함께 사라졌다. §0 ⑱ |
| `meta_absence_reason` | `meta_absence_reason(db, cache: dict = None)` |
| `meta_access_block` | `meta_access_block(code: str, detail: str = None)` |
| `stamp_meta_refusal` | `stamp_meta_refusal(db, source_maps, cache: dict = None)` |
| `assumed_meta_for_unregistered` | `assumed_meta_for_unregistered(cells, basis_meta: dict, basis: dict = None)` |
| 🔴 **`phys_needs_basis`** | **`phys_needs_basis(meta: dict \| None) -> bool`** |
| `grid_needs_basis` | `grid_needs_basis(meta: dict \| None, basis_meta: dict \| None) -> bool` |
| `borrowed_meta_for` | `borrowed_meta_for(meta, basis_meta, basis=None, need_phys=True, need_grid=True)` |
| 🆕 🔴 **`confirmed_meta_for`** | **`confirmed_meta_for(meta, basis_meta, basis, frame, mark, shift=None, placement=None, basis_cells=None) -> dict \| None`** — 🔴 **인자 셋이 뒤에 늘었다**(구 지도는 `mark`에서 끝났다). 전부 기본값이 있어 옛 호출은 던지지 않는다 |
| `compose_basis_refusal` | `compose_basis_refusal(map_ids, basis: dict = None, why: str = None)` |
| `declared_frame_of` | `declared_frame_of(meta: dict \| None) -> dict` |
| `_solve_shift` / `_membership` | 🆕🆕 `_solve_shift(placed_keys, ref_sorted, window: int, base=(0, 0))` — **`base`가 뒤에 붙었다**(탐색 창의 중심을 앵커가 준 자리로 옮긴다) / `_membership(placed_keys, ref_sorted, dx, dy)` |
| 🆕 `_encode` / `_residual_shift` | `_encode(pairs)`(좌표쌍 → 단일 정수, `_KEY_STRIDE`/`_KEY_BIAS` 편향) / `_residual_shift(placed_keys, ref_sorted, seats, at, walk_rank=None)` — **창이 아니라 좌석 열거**. 사유 어휘는 `RESIDUAL_*` |
| 🆕🆕 **`first_die_of`** | `first_die_of(cells, left_to_right: bool = True)` — **훑기가 1번을 매기는 셀** `(x, y)`, 없으면 None. 맨 위 행(y 최소)에서 `left_to_right`면 왼쪽 끝, 아니면 오른쪽 끝. **좌표만 읽는다**(순번 컬럼도 메타도 안 본다). ⚠️ **실측 호출부는 전부 진단 로그다** — 채점은 이것을 부르지 않는다. 🔴 **그런데 이 함수의 존재 이유가 채점의 결함이다**: docstring이 라이브 실측을 인용한다 — `rot0_tl`과 `rot0_tr`이 **시프트도 배치도 완전히 같았다**(기준점을 양쪽 다 좌상단으로 골랐기 때문). **보행 순서만 바꾸고 기준점을 안 바꾸면 두 후보는 정의상 쌍둥이다** |
| 🆕 `start_for_placement` / `start_from_placement` | `start_for_placement(framed_meta, target_meta, shift)` / 🆕🆕 `start_from_placement(framed_meta, floor_meta, anchor_src, anchor_ref, source_box=None, floor_box=None)` — **확정 메타의 격자 시작점**을 채점된 배치에서 만든다. 🔴 **[`1fbd4b1`] 뒤의 두 상자 인자가 없으면 확정 원점이 편집기가 쓰는 상자와 다른 상자 위에서 풀려 맵이 열 몇 칸 밀린다** — 상자는 `map_overlay.origin_box`가 만든다. `frame_confirmation._placement_of`가 이 계열의 유일한 짝이다 |
| 🆕 **`serpentine_index` / `serpentine_rank`** | **`(cells, top_is_min_y: bool = True, left_to_right: bool = True) -> dict`** — 🆕🆕 **세 번째 인자는 이제 채점기가 실제로 흔든다**([§5-F ①](#-훑기walk--순번의-정본)) |
| 🔴 **`score_candidates`** | 🆕🆕 `score_candidates(source_maps, reference_cells, reference_meta, shift_window=SHIFT_WINDOW, cell_cap=MAX_SCORED_CELLS, reference_values=None, thresholds=None, assume_reference_geometry=True, reference_ref=None, value_weights=None, index_thresholds=None, diag=None)` — 🔴 **`sides=`가 사라지고 `diag=`가 붙었다**(진단 줄을 반환값 대신 호출자가 준 리스트에 쌓는다) |
| 🆕🆕 **`search_pivot_of` / `_placement_payload`** | `search_pivot_of(usable)` — 앵커가 안 선 갈래에서 **배치를 그릴 재료**(점수·시프트·판정은 이것을 읽지 않는다) / `_placement_payload(linear, anchor_src, anchor_placed, dx, dy)` — 후보별 배치 페이로드의 **단일 조성 지점**. 🔴 **앵커 갈래와 탐색 갈래가 *같은 함수*로 페이로드를 만든다** |
| 🆕🆕 `_allows_synthetic_reference_geometry` | `(table: str) -> bool` — `_SYNTHETIC_GEOMETRY_REFERENCE_TABLES`(현재 `core_wafer_map` 하나)에 든 기준 테이블만 **합성 기하로 기준을 세우는 것**을 허용한다 |
| `load_alignment_thresholds` / `_read_thresholds` | `(cfg: dict) -> dict` / `(raw: dict, where: str) -> dict` |
| `load_index_thresholds` / `index_thresholds_complete` | `(cfg: dict) -> dict` / `(th: dict) -> bool` |
| `load_alignment_value_weights` / `_fit_weights` | `(cfg: dict) -> dict` / `(vec, n)` |
| `_rule_on` | `_rule_on(candidates, thresholds=None, metric=METRIC_OCCUPANCY, scoring=None) -> dict` |
| `compose_refusal` | `compose_refusal(state, reference, excluded: _Excluded, ruling, source_map_count, candidates=None) -> str` |
| `compose_assumption_offer` | `(state: str, count: int, basis: dict) -> str \| None` |
| `geometry_basis_of` | `geometry_basis_of(meta, excluded_reason=None, basis_meta=None) -> str` |
| `resolve_source_columns` | `resolve_source_columns(cfg, table, model, x_col=None, y_col=None, value_col=None, index_col=None) -> dict` |
| `comparison_kind` | `comparison_kind(reference_kind: str, source_value_column) -> str` |
| `_resolve_reference` / `_load_reference` | `(db, cfg, spec, source_maps, cap, cache=None)` / `(db, cfg, table, map_id, origin, cap, cache=None)` |
| `_no_cell_refusal` / `_meta_row_exists` | `(db, cfg, table, map_id)` / `(db, table, map_id) -> bool` |
| `compose_map_id` | `compose_map_id(values) -> str` |
| 🆕🆕🆕 **`basis_cells_for`** | **`basis_cells_for(db, reference: dict, cfg: dict = None) -> list \| None`** — **[`68db020`, `frame_confirmation._basis_cells_for`에서 이사(public화)] 참조(유효 다이) 맵의 셀 좌표 목록.** `_cells_of`를 감싼다(두 번째 셀 로더가 아니다). 소비자: 이 파일의 `confirmed_meta_for(basis_cells=...)` · `frame_confirmation._write_confirmed_meta` · `mappers/dt_alignment_metadata_mapper`(체인) |
| 🔴 **`build_alignment_view`** | 🆕🆕 `build_alignment_view(db, cfg, rule, key_values, map_table, reference_spec=None, include_cells=True, cell_cap=MAX_PAYLOAD_CELLS, x_col=None, y_col=None, value_col=None, index_col=None, assume_reference_geometry=True, source_filters=None, ignore_source_metadata=False) -> dict` — 🔴 **셋이 늘었다**(`index_col`은 **중간에** 끼었다: `value_col`과 `assume_reference_geometry` 사이). ⚠️ **위치 인자로 부르던 호출은 던지지 않고 틀린 답을 낸다.** 🆕🆕 `main.py`는 이제 이 함수를 직접 부르지 않고 [`alignment_view_service.resolve_alignment_view`](#6-기타-서버-모듈-한줄-요약)를 거친다 |
| `worklist_sort_keys` / `map_table_catalog` | `(rule: dict) -> list` / `(src_model, src_table: str) -> list` |
| `coordinate_column_catalog` / `binding_ambiguity` | `(cfg, src_table) -> dict` / `(rule, coord) -> list` |
| `floor_tables` / `resolve_reference_catalog` | `() -> list` / `(db, cfg, table=None, cap=MAX_REFERENCE_CANDIDATES) -> dict` |
| `_live_confirmations` / `_unit_maps` | `(db, rule_name, unit_keys)` / `(db, src_model, decision_key, map_key_cols, narrow, cap)` |
| 🔴 **`build_alignment_worklist`** | `build_alignment_worklist(db, cfg, rule, map_table, key_values=None, q=None, sort="unit_key", order="asc", limit=DEFAULT_WORKLIST_LIMIT, offset=0, unit_cap=MAX_WORKLIST_UNITS) -> dict` — 🆕🆕🆕🆕 **[`c4a3159`] 결정키를 못 채우는 파생 행 하나가 목록 전체를 500으로 끌고 내려가지 않는다.** 종전엔 `frame_confirmation.compose_unit_key(rule, u["key"])`가 맨몸으로 불렸고, 결정키 컬럼이 빈 행을 만나면 `ConfirmationRefused`를 던졌다(`ValueError`가 아니라 라우트의 `except ValueError`도 못 잡는다) — 건강한 단위 다섯이 나쁜 행 하나에 딸려 사라졌다. 지금은 `try/except frame_confirmation.ConfirmationRefused`로 감싸 **그 단위 하나만** `unit_key=None`으로 표시하고 나머지는 그대로 판정한다. 신설 사유 **`REASON_UNIT_KEY_INCOMPLETE = "unit_key_incomplete"`**(`_WORKLIST_REASON_TEXT["결정키 빈 값 - 단위 이름 없음"]`)가 `header is not None` 분기보다 **먼저** 검사된다(이름이 없으면 확정 여부를 물을 열쇠가 없다 — 그 뒤로 흘리면 "맵 없음"·"기준 없음" 같은 재 본 적 없는 사유가 붙는다). 신설 헬퍼 **`_worklist_reason_text(code, detail=None) -> str`**이 사유 표찰에 **비어 있던 컬럼 이름**(들)을 붙인다 — 어느 컬럼이 비었는지는 `crud.is_blank_value`로 판정한다(거절 쪽 `compose_unit_key`의 `clean_str_value(x) == ""`와 동치임이 `contracts/blank_predicate`로 고정돼 있다 — 여기서 "비었다"를 다시 정의하면 목록과 확정이 서로 다른 행을 빈 행이라 부를 수 있다). 🔴 **가드가 둘이고 독립적으로 필요하다** — 위 try/except만 있으면 정렬 단계의 `_sk`가 `unit_key=None`을 문자열과 비교하려다 `TypeError`로 **다시** 500이 된다. 그래서 `_sk`는 정렬 직전에만 `uk = u["unit_key"] or ""`로 치환한다(저장은 여전히 `None` — `"" `로 영구 치환하면 빈 이름과 못 지은 이름이 같아진다) |

- 🔴 **`parse_frame`은 이 파일이 정의하지 않는다** — `server/dt_map_derivation.py`에서 `source_meta_for_frame`과 함께 import한다. `map_alignment.parse_frame`으로 닿는 것은 참이지만 **정의를 여기서 찾으면 못 찾는다**.
- 🆕🆕 **후보 프레임 — 전건 열거**(개수를 적지 않는다): `FRAME_ROTATIONS`, `(0, 90, 180, 270)`) × **`CANDIDATE_STARTS`**, `(START_TOP_LEFT, START_TOP_RIGHT)`) → `CANDIDATE_FRAMES`, 각 항이 `parse_frame`으로 검증된다). 철자 사전은 **`START_TOKEN`**(`top_left→tl` · `top_right→tr`)과 그 역 `_START_OF_TOKEN`, 면은 **`CANDIDATE_SIDE = "front"`** 고정.
- 🆕🆕 🔴 **`FRAME_SIDES`, `("front", "back")`)는 살아 있지만 후보 축이 아니다** — 저장된 **메타**가 쓰는 낱말이고, `declared_frame_of`가 그 낱말로 「이 맵이 적어 둔 것」을 철자한다. **후보 축과 메타 어휘를 한 이름으로 접으면** 우상단 시작 설비가 「물리적으로 뒤집힌 웨이퍼」로 저장된다(그것이 방금 고친 결함이다).
- **판정 상태**: `STATE_SCORED`/`STATE_NO_WINNER`/`STATE_NOT_SCORABLE`/`STATE_COMPUTING` · `STATE_NOT_CONSIDERED`.
- **지표**: `METRIC_OCCUPANCY`/`METRIC_VALUES`/`METRIC_VALUES_WEIGHTED`/`METRIC_INDEX` · `VALUE_METRICS`.
- **판결 사유**: `RULING_NO_CELLS_SCORED`/`_NO_CANDIDATE_SCORED`/`_NO_OVERLAP`/`_NO_DISCRIMINATION`/`_TIE` · `THRESHOLD_KEYS`, `("min_margin_dies", "min_discriminating_dies")`).
- **상한**: `MAX_SCORED_CELLS`/`MAX_PAYLOAD_CELLS` **20_000** · `SHIFT_WINDOW` · `MAX_WORKLIST_UNITS` **2_000**/`MAX_WORKLIST_MAP_ROWS` **100_000**/`DEFAULT_WORKLIST_LIMIT` · 🆕🆕 `MAX_REFERENCE_CANDIDATES` **50 → 500**(10배 — 기준 카탈로그가 잘려 나가면 조작자가 **고를 수 없는 기준**을 못 보고, 그 절단은 화면에서 「없다」와 얼굴이 같다).
- 🔴 **`phys_needs_basis`의 술어가 바뀌었다** — 본문은 `geometry_declaration(meta) not in (GEOMETRY_DECLARED, GEOMETRY_CONFIRMED)`다. 즉 **`confirmed`도 「빌리지 않는다」쪽**이다. 사유: 확정된 행을 다시 빌리면 **숫자는 하나도 안 바뀌면서** `phys_confirmed_from`이 `phys_assumed_from`으로 덮여, 확정 전후를 구분할 수 없게 된다.
- ⚠️ **의도된 비대칭**(소스 주석 🆕🆕 **660–664** @`7097a67` — `confirmed_meta_for` 본문 안, `need_phys` 대입 바로 위. 🔴 **직전 등재의 `622–626` @`34d2518`는 이번 라운드의 +402줄에 밀렸다. 그전의 `621–625`·`559–565`도 각각 낡았거나 한 줄 위로 잘못 잡혀 있었다 — 이름이 없는 주석 블록이라 라인 말고 부를 방법이 없고, 그래서 이 자리는 매 라운드 재측정 대상이다**): `confirmed_meta_for`는 `phys_needs_basis`를 **재사용하지 않고** 더 엄격한 `geometry_declaration(meta) != GEOMETRY_DECLARED`를 쓴다. **채점은 「빌려야 하나」를 묻고 쓰기는 「여기 써도 되나」를 묻는다.**

### 🆕 `server/frame_confirmation.py` — 확정의 **기록자**

**크기: 798줄** @`68db020`(`7097a67` 837에서 **-39**). ⚠️ **제목에서 줄 수를 걷어냈다** — `map_alignment.py`와 같은 이유다(제목 앵커가 크기와 함께 깨진다).

> 🟢 **심볼 실측(2026-08-11 후속 재측정 · `68db020`)** — 아래 심볼과 시그니처는 **`68db020`의 커밋된 blob**에서 `def`/`class` 정의를 grep해 확인했다. 🔴 **`_basis_cells_for`가 삭제됐다** — `map_alignment.basis_cells_for`로 이사·공개됐다(위 [§5 `map_alignment.py`](#-servermap_alignmentpy--프레임-정렬의-채점자) 참조). 삭제 지점에 남은 것은 그 사실을 적은 주석 하나뿐이다. **나머지 top-level 심볼 집합과 시그니처는 무변동.** 🔴 **라인 번호는 싣지 않는다** — 위치는 `git grep -n "<심볼>" -- <경로>`로 확정하라.

| 함수 | 시그니처 |
|---|---|
| `accepted_ruling_states` | `accepted_ruling_states() -> set` |
| `__getattr__` | PEP 562 — `ACCEPTED_RULING_STATES`를 **속성 접근 시점에** 합성한다(모듈 레벨 대입이 **아니다**) |
| `class ConfirmationRefused` | `Exception` |
| `weakest_contributor` | `weakest_contributor(contributors: list, table_name: str = None) -> tuple` |
| `compose_unit_key` | `compose_unit_key(rule: dict, decision_key: dict) -> str` |
| `live_confirmation` / `live_confirmation_for_maps` | `(db, rule_name, unit_key)` / `(db, maps)` |
| `warrant_of` | `warrant_of(header) -> str` |
| `_load_metas_and_basis` / `_geometry_bases` | `(db, contributors, reference=None) -> tuple` / `(metas, contributors, basis_meta=None) -> dict` |
| 🆕 🔴 **`_write_confirmed_meta`** | **`_write_confirmed_meta(db, contributors, metas, basis_meta, reference, frame, mark, ruling=None) -> list`** — 🔴 **`ruling`이 뒤에 늘었다**(기본값 있음). 🆕🆕🆕 **[`68db020`] 판 하나에 한 번 `map_alignment.basis_cells_for(db, ref)`를 불러 `basis_cells`를 만들고** 그것을 기여자 루프 밖에서 한 번만 계산해 나른다(§`map_alignment.basis_cells_for` 참조 — **왜 확정이 이것을 읽는가**는 그 항목에) |
| 🆕 `_placement_of` / `_priority_of` / `_as_int` | `_placement_of(contributor, ruling)` — 이 기여자의 **채점된 배치** `{"dx","dy"}`(+ 있으면 `anchor_src`/`anchor_ref`/`linear`), 없으면 None이고 **None은 (0,0)이 아니다**. 🔴 **철자는 이것 하나다** — 소스 행(`shift_dx/dy`)과 확정 메타의 원점(`map_alignment.start_for_placement`)이 같은 배치를 써야 한다 / `_priority_of(source_name, table_name=None) -> int` 소스 서열 조회 / int 파싱 |
| 🆕🆕 🔴 **`_placement_of`가 `ruling["by_frame"]`를 먼저 본다** | **[`97b29da`]** 종전 갈래는 「**이긴 프레임**에 선 기여자만 배치를 갖는다」였고 그 근거를 「다른 프레임에서 채점된 배치는 존재하지 않는다」로 적었다 — 🔴 **그 문장이 거짓이었다.** 채점기는 **여덟 후보 전부**에 시프트와 배치를 푼다. 없었던 것은 배치가 아니라 **그것을 여기까지 나르는 키**다. 증상: 추천이 아닌 후보를 확정하면 배치가 None이라 `confirmed_meta_for`가 원점을 손대지 않고, 같은 맵의 확정 셋이 **`rotation`만 0/90/180으로 다르고 `grid_start`는 전부 같았다**(제품 소유자 실측 2026-08-08) — 편집기는 그 메타대로 **같은 맵을 각도만 돌려** 그렸다. 지금은 `ruling["by_frame"][applied_frame]`을 먼저 읽고, 없을 때만 종전의 승자 스코프 갈래로 물러선다. ⚠️ **클라 변경 0건** — 클라는 `ruling`을 키를 들여다보지 않고 그대로 복사한다 |
| `resolve_ruling_state` | `resolve_ruling_state(ruling: dict, state=None) -> str` |
| 🆕 `_reject_unreadable_frame` | `_reject_unreadable_frame(where: str, value)` |
| `_resolve_frames` | `_resolve_frames(rule: dict, frames: dict, frame: str) -> dict` |
| 🔴 **`record_confirmation`** | `record_confirmation(db, rule, decision_key, contributors, confirmed_by, frames=None, ruling=None, reference=None, enrichment_row_id=None, commit=True, frame=None, map_table=None, columns=None, state=None)` |
| `as_payload` / `derived_cell_scope` | `(db, header) -> dict` / `(db, confirmation_uid: str)` |

- 상수: `MIN_CONTRIBUTORS=1` · `UNRANKED=99` · `WARRANT_CONFIRMED`/`WARRANT_NOT_DECLARED` · `_ASSUMED` — `map_overlay.GEOMETRY_ASSUMED`의 **의도적 두 번째 철자**, `test_map_alignment_assumption.py`가 고정) · `STATE_NOT_TRANSPORTED` · `META_SOURCE_NAME`, `"user"`).
- **`_write_confirmed_meta`가 하는 일**: 실제로 쓴 `(target_table, map_id)` 쌍의 목록을 돌려준다. `excluded_reason`이 있는 기여자는 건너뛰고, **기여자 자신의 `applied_frame`**(없으면 라운드의 `frame`)을 쓰며, **내용 결정은 통째로 `map_alignment.confirmed_meta_for`에 위임**한다. 쓰기는 `crud.apply_batch_updates` → `map_meta_registrar.META_TABLE`, `transaction_id=mark["confirmation_uid"]`. 메타 테이블이 선언된 동적 테이블이 아니면 **경고 후 `[]`**. 호출부는 `record_confirmation`. ⚠️ **`commit=False`와 `frame`을 함께 주면 `ValueError`**.
- 🔴 **어휘 관문은 이름이 하나가 아니다 — 셋이고 서로 다른 것을 막는다**:

| 관문 | 무엇을 막나 | 허용 어휘의 정본 |
|---|---|---|
| **`resolve_ruling_state`** | 선언되지 않은 **판정 상태** | `{STATE_SCORED, STATE_NO_WINNER, STATE_NOT_SCORABLE}` — 🔴 **리터럴이 아니라 `map_alignment`의 상수 참조**이고 조성 지점은 **`accepted_ruling_states()`** 하나다(어휘의 정본을 두 번 적지 않는 규율). ⚠️ **`STATE_NOT_TRANSPORTED`는 일부러 이 집합 밖이다**(폴백 반환일 뿐 입력으로 받지 않는다) · **`STATE_NOT_CONSIDERED`도 밖이다**(후보 하나의 상태이지 판정의 상태가 아니다) |
| **`_reject_unreadable_frame`** | 프레임이 아닌 **프레임 문자열** | 🔴 **자기 어휘가 없다** — `map_alignment.parse_frame`에 위임한다(소스 docstring: 어휘의 정본은 `map_alignment` 하나다). 축 리터럴은 `map_alignment.py` |
| **`_resolve_frames`** | 규칙이 선언하지 않은 **확정 대상 키** | 🔴 **리터럴이 아니라 데이터** — `rule["target_fields"]` |

### 🆕 `server/migrations/add_frame_confirmation.py` — 확정 스키마 (append-only)

**안전 계약**: `DROP` 없음 · `ALTER TYPE` 없음 · 기존 데이터를 건드리는 문장 없음. 추가 컬럼은 전부 `NULL` 허용 + 기본값 없음이라 PostgreSQL이 **카탈로그만** 고친다(테이블 재작성 없음). `cell_sources`는 크므로 그 인덱스만 **`CONCURRENTLY`**로 트랜잭션 밖(AUTOCOMMIT 연결)에서 만든다 — 인제션·체인·그래프 라이터를 막지 않기 위해서다.

- **`frame_confirmation`**(헤더, 확정 1버전 = 1행): `confirmation_uid`·`version`·`ruling_state`·`weakest_source`·`weakest_priority`·`confirmed_by`·`confirmed_at`가 `NOT NULL`. 나머지 — `dt_eqp`·`product`(둘 다 나중에 `DROP NOT NULL`로 후퇴)·`core_frame`·`dt_frame`·`reference_table`·`reference_map_id`·`ruling_reason`·`winner_frame`·`margin`·`discriminating`·`superseded_by`·`supersedes_uid`·`rule_name`·`unit_key`·`decision_key JSONB`·`enrichment_row_id`·`geometry_assumed BOOLEAN`([D3] **NULL = 미상, 기본값을 일부러 안 준다**)·`confirmed_frame`·`map_table`·`x_col`·`y_col`·`value_col`·`frames JSONB`.
- **`frame_confirmation_source`**(기여자별): `confirmation_uid`·`role`·`source_table`·`map_id`(기본 `''`)·`source_name`·`source_priority`가 `NOT NULL`, + `applied_frame`·`shift_dx`·`shift_dy`·`agreement`·`discriminating`·`excluded_reason`·`geometry_basis`.
- **`cell_sources`**: `confirmation_uid TEXT` 추가(**NULL = 확정된 좌표계에서 파생되지 않았다**) + `idx_sources_confirmation` `CONCURRENTLY` on `(confirmation_uid, table_name, row_id) WHERE confirmation_uid IS NOT NULL`.

### `server/map_meta_registrar.py` (**367줄**, `b697d34` 신설) — [M3] 인제션 맵의 `wafer_map_metadata` 자동 등록
**왜 생겼나**: `wafer_map_metadata`는 정렬의 단일 원천인데 **등록하는 곳이 맵 에디터 Push 하나뿐**이었다. 인제션 두 경로(파일 워처·체인 워커)는 맵을 만들면서 메타를 남기지 않았고, 그 맵들은 전부 "화면기준" 폴백으로 그려졌다(**모듈 docstring이 인용하는 실측: `bonding_map`의 서로 다른 맵 키 약 39만 개 대 메타 9행** — 이 수치의 출처는 소스 주석이지 이 지도의 재측정이 아니다). 이 모듈이 그 구멍을 **쓰기 경로에서** 막는다. 테스트: `tests/test_map_meta_registrar.py`(416줄, **12건**).

> **계약 (전부 의도 — 축소 금지)**
> - **부재분만 만든다.** 기존 메타 행은 **바이트 무접촉**이다. 사용자/에디터 등록이 정본이고 이 모듈은 구멍만 채운다. 레이어링으로도 이중 방어된다 — `SOURCE_NAME="auto_map_meta"`(~69)는 `crud.SOURCE_PRIORITY`에 **의도적 미등재**라 기본 99로 떨어져 나중의 사용자 편집을 절대 못 이긴다.
> - **트리거는 선언이다.** `table_config`에 `map_key_columns`를 선언했고 **동시에** `map_overlay.resolve_binding`이 좌표 바인딩을 내놓는 테이블만 대상. `map_split_registry`처럼 키는 있지만 좌표가 없는 **레지스트리는 자연히 걸러진다**(별도 제외 목록이 아니다).
> - **정직한 최소 규격.** 합성 메타는 에디터의 「표준」 선택과 **필드 단위로 같은** 마스크 중립 어휘다 — 배치 x/y bbox 격자, 회전 0, front, chip 1×1 / offset 0 / edge margin 3 / 격자 반대각선을 외접하는 웨이퍼 지름. **실제 웨이퍼 기하를 추측하지 않는다.** 에디터와 **딱 하나 다른 점**: `grid_start_x/y`가 0이 아니라 **배치의 min x/y**다(에디터는 대화형 '표준' 선택에서만 좌표를 시프트하지만, 인제션 행은 원좌표를 유지하므로 프레임이 데이터가 있는 곳에서 시작해야 한다).
> - **재귀 차단 이중화**: `META_TABLE` 자체를 명시 거부(~벨트) + 메타 테이블은 `map_key_columns`를 선언하지 않는다(~멜빵). 메타 쓰기가 자기 자신을 다시 트리거할 수 없다.
> - **10M행 규율**: 행당이 아니라 **배치 내 distinct 맵 키당 1회** 존재 확인(인덱스 컬럼 `business_key_val`의 청크 IN) + **프로세스 수명 known-present 캐시**(같은 맵 재적재는 추가 쿼리 0). bbox 누적은 O(rows) 정수 비교.
> - 쓰기는 **정상 경로**(`crud.apply_batch_updates`, `silent=True`)를 탄다 — outbox가 발화하고 체인 워커의 미전달 스윕이 클라 갱신을 배달한다.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `META_TABLE` / **`SOURCE_NAME="auto_map_meta"`** / `SETTINGS_KEY="auto_register_map_meta"` / `DEFAULT_ENABLED=True` / `INGESTION_SETTINGS_PATH` / `CHUNK_SIZE=1000` / `_KNOWN_CACHE_MAX=200,000` | 대상 테이블·provenance·토글 키·기본값(ON)·설정 파일(`paths.config_path`)·청크·캐시 상한 | ~68–83 |
| `reset_known_cache()` / `_load_ingestion_settings()` / **`auto_register_enabled()`** | 테스트용 캐시 리셋 / 설정 판독 / **토글 게이트 — 작업 단위(파일·tx 그룹)당 1회 읽기**(핫리로드는 "다음 단위부터", 한 단위 안에서는 일관 — D1 스냅샷 규율) | ~90/96/114 |
| **`compose_map_id(key_columns, row, table_name=None)`** | 행 → 맵 키 문자열. **정규화는 `map_overlay.canonical_bind_value`(~149)** — 선언 컬럼 타입이 지배한다. 키 성분이 하나라도 없으면 **None**(정체성을 지어내지 않는다) | ~132 |
| `_to_grid_int(v)` | 좌표 1개를 **정수 격자 인덱스**로 판독 — 정수가 아니면 None(그 행은 bbox에 기여하지 않는다) | ~156 |
| **`synthesize_grid_meta(min_x, min_y, max_x, max_y) -> dict`** | 마스크 중립 합성 프레임. 반환 키 14종(`grid_cols/rows`·`grid_start_x/y`·`grid_y_invert`·`rotation`·`side`·`phys_wafer_dia`·`phys_chip_x/y`·`phys_offset_x/y`·`phys_edge_margin`·**`auto_registered: true`**). 지름은 `max(300, ceil(2*(half_diag+4)))` — 모든 셀 모서리가 마스크 타원 **안**에 들어와 맵 전체가 Push 가능해야 한다(에디터 [fix C]와 같은 근거). `auto_registered`는 가산 필드라 기존 소비자는 아는 키만 읽는다 | ~168 |
| **`class MapMetaCollector(table_name, table_info=None)`** | 작업 단위 1개용 수집기. **생성 시점에 게이트 전부를 통과하지 못하면 `active=False`로 불활성**(collect/flush가 no-op) — 생성이 곧 작업 단위 경계라 토글 스냅샷이 그 단위 전체에서 일관된다 | ~198/208 |
| ├ `collect(rows)` | 평범한 `{column: value}` dict들에서 **맵 키별 bbox만** 누적. DB 작업 0. 키 불완전·비정수 좌표 행은 기여하지 않는다 | ~251 |
| ├ `pending()` / **`flush(db) -> int`** | 등록할 게 있나 / **부재분 생성 본체** — ① known-present 캐시로 후보 선별 ② `business_key_val IN (…)` 청크 존재 확인(bk 조성은 `crud`의 복합키 관례 `[target_table, map_id]` 미러) ③ 없는 것만 `apply_batch_updates`로 생성. 반환은 생성 건수 | ~282/285 |
| └ `_remember(map_ids)` | 프로세스 수명 캐시 갱신(상한 초과 시 전체 clear — 무한 성장 금지) | ~362 |

> **호출 지점은 정확히 둘**(둘 다 "데이터가 커밋된 뒤, 실패해도 인제션/체인 쓰기를 실패시키지 않는다"): `directory_watcher._send_to_upsert`(생성 ~1686 · collect ~1724 · flush ~1783, [§3](#3-serverparsersdirectory_watcherpy--파일-인제션)) · `chain_ingestion_worker.process_chain_transaction_group`(~445–450, [§4](#4-serverchain_ingestion_workerpy--체인-워커)). 토글 문서는 `ingestion_settings.json.sample`의 `_auto_register_map_meta_doc`.

### `server/effort_metric.py` (**165줄**, `2a9f6c4` 신설) — 핵심가치 #1 계기의 **선언 절반**
**SSOT §1 핵심가치 #1("최소공수교정")의 정본 계기 = 상호작용 공수 점수**(사용자 2026-07-29). `score(tx) = key·w_key + mouse·w_mouse + nav·w_nav`. 이 모듈이 소유하는 것은 **선언된 절반**(가중치 + 내비 페널티를 물리지 않는 화면 전이 허용목록)이고, 원시 카운트는 `models.InteractionEffortLog`(이 절 위), 집계는 [`crud.get_effort_stats`](#2-serverdatabasecrudpy--레이어링-코어)에 있다. config는 `paths.config_path("effort_metric.json")`(gitignored, **`.sample` tracked**), 운영 문서는 `docs/guide/config/effort_metric.md`. 테스트: **`server/tests/test_effort_metric.py`(704줄, 39건 — `grep -c "def test_" = 39`)**.

> **두 가지가 왜 config인가 (소스 docstring이 근거를 갖고 있다)**
> - **가중치가 상수가 아닌 이유**: 원시 카운트를 저장하고 **점수는 읽을 때 계산**한다. 가중치를 재조정하면 과거 전 트랜잭션이 새 가중치로 재해석되고, 하드코딩이면 누가 그 값에 이의를 다는 순간 **역사적 기준선이 판독 불가**가 된다 — UI 개편 전후를 비교하는 것이 이 계기의 존재 이유다.
> - **전이 허용목록이 빈 채로 시작하는 이유**: 선언되지 않은 전이는 **내비 페널티 전액**을 문다. 허용목록은 능동적 선언("이 점프는 컨텍스트를 보존한다 — 예: DOE → dt 맵 라우팅")이지 추론이 아니다. 추측으로 채우면 계기가 소유자가 바라는 방향으로 낙관 편향되고, 그 순간 계기이기를 그만둔다. 항목은 라우팅 소유자(클라)가 제안하고 총괄이 승인한다.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `CONFIG_PATH` | `paths.config_path("effort_metric.json")` | ~43 |
| **`DEFAULT_WEIGHTS = {"key":1, "mouse":3, "nav":5, "nav_preserved":0}`** / `WEIGHT_KEYS` | 기본 가중치(문서화된 기본값) / 허용 키 4종 — 그 외 키는 config에서 거부 | ~60/62 |
| `load_config(path=None)` | config 로드(부재·손상은 `{}` — 에러 아님, 기본값으로 동작) | ~65 |
| **`resolve_weights(config=None) -> dict`** | 선언 > 기본값. **소비는 반드시 이 함수 경유** — `DEFAULT_WEIGHTS`를 직접 읽으면 선언이 무시된다(`map_overlay.DEFAULT_VAL_CANDIDATES`와 같은 규율) | ~79 |
| **`resolve_context_preserving_transitions(config=None) -> list`** | 페널티 면제 전이 목록. **미선언이면 빈 목록**(= 전 전이가 페널티 대상) | ~112 |
| **`get_public_config(path=None) -> dict`** | 클라가 소비하는 공개본 — `GET /api/effort/config`가 서빙([§1.1-ter](#11-ter-핵심가치-1-계측--재수정률--상호작용-공수-점수-2a9f6c4-v1-신설)). 클라에 가중치·전이 사본을 두지 않게 하는 단일 원천 | ~159 |

### `server/transfer_plan.py` (**3,826줄**, `ed9cfdb` 3,450에서 **+376**) — [M2] Universal Transfer Plan 엔진 (v2 = 계획 정체성이 곧 맵 정체성, **`b35bc9f` zone 모델 · `2baf9ff` U9 marker · `1fefd12` count_only/column_unresolved 강등 · `deed6d2` self-frame fail count_only · `b697d34` 키 정규화 위임 + 7c 선언된 untracked**)
`paths.config_path("transfer_plan_config.json")`(gitignored, `.sample` tracked) — `stages.{name}.{source_kind, target_kind, target_map{table,preset}, source{...} \| source_config_ref}` + **`plan_store.{registry, material_identity, source_region?}`**. 테스트: `tests/test_transfer_plan.py` + **`tests/test_doe_zone_model.py`(471줄, `b35bc9f` 신설·`2baf9ff` 확장 — V1–V6을 `contracts/doe_band_rules` 벡터로 채점, 뮤테이션 런 29/30 킬 + marker 축 9/9 킬)** + **`tests/test_transfer_untracked.py`(208줄, **10건** — 7c 축)**.

> 🔴 **앵커 재측정 (2026-08-04)** — 3,312 → **3,450줄**. 이동은 **계단이지 균일 오프셋이 아니다**: `_stage_role_statuses` **+30** · `list_stages` **+31** · `_reshape_m1_summary` **+43** · `_summarize_inline` **+54** · `get_stage_source_summary` **+105** · `_band_to`/`_prev_to`/`validate_plan` **+114** · `_reg_get` **+117**. **파일 앞쪽 값을 뒤쪽에 적용하면 60줄 이상 빗나간다.**
>
> 🔴 **이 절은 앞선 패스에서 이 지도의 대표적 함정을 그대로 재연했다** — 구 지도의 `_resolve` 앵커가 `~276`이었는데 그 자리는 신설된 `transfer_log_is_declared_none`이 차지했다. `def`도 있고 docstring도 있고 7c 문맥까지 맞아서 **도착지가 완벽하게 멀쩡해 보인다.** 함수명 Grep이 1차, 라인은 보조다.
>
> 🆕 🔴 **[`2c2a777`+`784a07d` 2026-08-04] 보조 감산 역할은 「선언하지 않아도 된다」 — 그리고 그 사실이 응답에 실린다.**
> - 어휘의 정본은 [`bonding_plan.py`](#5-소형-서버-모듈)이고 이 파일은 **import한다**(**~117**: `from bonding_plan import STATUS_NOT_DECLARED, role_is_declared`). 🔴 **두 번째 철자를 만들지 않은 것이 요점이다** — 같은 리터럴을 각자 선언한 `map_overlay.py`·`map_preset_routing.py`가 그 반례로 옆에 있다.
> - **`_aux_role_status(block, key, required=("lot","slot"))`(**404**)** — 키가 없으면 `not_declared`, 있으면 종전 `_binding_status`. `_stage_role_statuses`(**414**)의 역할 판독 6곳이 이 함수로 갈아탔다.
> - **`_status_is_degraded`(**785**)에서 `not_declared`가 강등에서 빠졌다** — `""`·`"connected"`와 같은 편이다. 🔴 **선언하지 않은 것은 고장이 아니다**: 사이트가 그 로그를 갖지 않기로 한 상태이고, 그것을 강등으로 세면 수가 미상으로 붕괴하는데 사이트는 그 수를 **쓰기로 결정한 상태**다.
> - **하지만 총량이 순량 행세를 하면 안 된다** — 그래서 빠진 감산의 **이름**이 응답에 실린다. 생산은 `_summarize_inline`(**1653**), 로트 축은 `get_lot_bin_summary`(**2280**)의 `inactive_union`(**~2355–2361**, 배출 **~2394–2397**).
>   - ⚠️ **`process_history`는 의도적으로 이 목록에 없다** — 감산항이 아니다.
> - **`validate_plan`(**3307**)의 누적**: 🔴 **누적 지점이 `available = int(chips_block.get("remaining") or 0)` **바로 뒤**인 것이 계약이다** — 판정 게이트를 통과해 **실제로 판정에 수가 먹인 소스만** 기여한다. 그리고 **비었으면 필드 자체를 세우지 않는다** — 전 역할 선언 사이트의 페이로드는 바이트 동일이다.
> - ⚠️ **`≤`(`remaining_upper_bound`)를 빌려 쓰지 않는다** — 그것은 7c의 **선언된 미추적** 전용이고 서버는 이 갈래에서 그 필드를 **의도적으로 세우지 않는다**. 같은 기호를 쓰면 서로 다른 두 상태가 화면에서 같아진다(클라 쪽 짝은 [§7 `transfer_plan.js`](#7-client2src--웹-클라이언트)의 `GROSS_MARK`).

> 🆕 🔴 **[2026-08-04 신설] 역할 카탈로그 + 드라이런 — 「내가 쓴 선언이 받아들여지는가」를 쓰기 없이 답한다.**
> - **역할 튜플이 상수가 됐다**: `IDENTITY_ROLES`(**175**) · `ORIGIN_LOG_ROLES`(**176**) · `ORIGIN_AREA_MAP_ROLES`(**178**) · `SOURCE_REGION_ROLES`(**179**) · `MAP_METADATA_ROLES`(**180**) · `BIN_AXIS_ROLES`(**181**) · `LOT_MEMBERSHIP_ROLES`(**182**) + 위치 문구 `BIN_AXIS_WHERE`(**185**)/`LOT_MEMBERSHIP_WHERE`(**186**). 🔴 **종전엔 호출부마다 인라인으로 다시 철자했다** — 드라이런은 **판정자와 똑같은 `required`**를 봐야 하고, **두 번째 철자는 곧 두 개의 진실이 된다.**
> - **`_STAGE_SOURCE_ROLES`(**529**)** — 역할 카탈로그. **`FAIL_SOURCE_ROLE`(**555**)** · 🔴 **`_OPTIONAL_ROLE_EFFECTS`(**556**) — 「없어도 거절되지 않지만, 없으면 무엇이 꺼지는가」.** 필수 역할은 유도가 메워 주는데 **선택 역할은 절대 유도되지 않으므로**, 한 줄을 지우면 기능이 조용히 꺼지고 **이번 라운드 전까지 그 부재는 어디에도 나타나지 않았다**(QA F5).
> - **`_role_dry_run(src, required, label, where, optional=())`(**591**)** / 🔴 **`dry_run(cfg)`(**682**) — 읽기 전용, 행 조회 0건, 파라미터 0개.** 라우트는 `GET /admin/transfer-plan/dry-run`([§1](#1-servermainpy--api--ws-허브), `main.py` **4241/4242**).
> - **거절 문장 헬퍼**: `_refusal(src, roles, label, where)`(**1102**, 🔴 **거절 문장이 `None`으로 나가지 않게 정규화한다**) · `_bin_axis_source`(**1074**)/`_bin_axis_refusal`(**1117**) · `_lot_membership_refusal`(**1403**) · `_bins_unavailable(detail, scope, requested=None, reason=None)`(**1130**, 🆕 `reason` 인자). 문장 생성기는 **`bonding_plan.explain_binding_refusal` 하나**이고 여기서 두 번 쓰지 않는다.
>
> 📐 **주요 앵커 재측정(`41b17ee`)** — **`REGISTRY_LEGACY_ROLE`(구 169)까지 무이동**, 그 뒤 **+17**, `_status_is_degraded` 이후 **+297**, `_merge_bins_over_slots` 이후 **+349~+376**: `WARN_QTY_SHORTAGE` **189** · `TRANSFER_LOG_NONE` **257** · `load_transfer_plan_config` **282** · `get_stages` **299** · `transfer_log_is_declared_none` **313** · `_resolve` **348** · `_unresolved_of` **364** · `_identity_filters` **382** · `_binding_status` **397** · `_plan_store_statuses` **450** · `stage_of_table` **479** · `list_stages` **496** · `_status_is_degraded` **785** · `assess_degradation` **827** · `build_chips_block` **866** · `load_source_region` **907** · `parse_bin_request` **1052** · `_merge_bins_over_slots` **1318** · `_lot_slots` **1414** · `_origin_map_id` **1513** · `_collect_history` **1606** · `_summarize_inline` **1653** · `_bin_warnings` **2197** · `get_stage_source_summary` **2227** · `get_lot_bin_summary` **2280** · `_parse_bands` **2411** · `_band_materials` **2480** · `_band_to` **2591** · `parse_material_list` **2642** · `stack_state` **2718** · `zone_layers` **2766** · `zone_demand` **2789** · `material_pool_key` **2862** · `validate_zone_plan` **2897** · `material_rollup_rows` **3064** · `remaining_state` **3117** · `bands_to_zones` **3141** · `_painted_values` **3257** · **`validate_plan` 3307**.

> **[`7c` `b697d34`] "전사 기록이 없다"는 선언이지 강등이 아니다** — `source.transfer_log`에 **정확히 문자열 `"none"`**(`TRANSFER_LOG_NONE` **257**)을 선언하면 status가 `missing`이 아니라 **`STATUS_TRANSFER_UNTRACKED = "connected(untracked)"`**(**~241**)가 되고, `assess_degradation`은 이것을 **강등으로 세지 않는다**(사유 주석 **~494**). 대신 `transferred`는 **가짜 0이 아니라 null**, `remaining`도 null이되 **`remaining_upper_bound`(= total − fail)**와 전용 경고 `WARN_TRANSFER_UNTRACKED`(**259**, effect `EFFECT_REMAINING_UPPER_BOUND` **260**)가 나가 클라가 「≤N」으로 그릴 수 있다. **JSON `null`·키 삭제·`"None"`은 전부 종전대로 `missing`** — null은 실수로 지운 키와 구분이 불가능하므로 선언으로 인정하지 않는다. **[`91386f0`] 판정이 순수 술어 `transfer_log_is_declared_none(src)`(**313**)로 추출**돼 호출자 **2곳**이 같은 답을 쓴다(`grep -c` 기준 정의 1 + 호출 2): `_stage_role_statuses` 안 **~407** · `_summarize_inline` 안 **~1362**. 적용 **~1362–1371** · 경고 발행 **~1739–1750** · `transferred=None` **~1757** · BIN 상한 **~934–948**(`_bins_block`의 `untracked` 갈래, 호출 **~1817**) · unverified 사유 편입 **~3310**/**~3368**. `used_count_only`와 다른 점: **저 쪽은 결함이고 이 쪽은 사실**이라 `base_reliable`을 깎지 않는다.
>
> **[`b35bc9f`] validate가 zone 컬럼을 읽는다** — `REGISTRY_ROLES`(**~166**). **하나라도 빠지면 `validate`가 404**다. **`bands`는 `REGISTRY_LEGACY_ROLE`(**~169**)로 강등** — 선택 역할이라 미선언 사이트도 404가 되지 않고, 선언돼 있으면 폐기 band 계획을 계속 읽어 `bands_to_zones`로 zone에 사상한다(마이그레이션 창).
> - **`material_identity`** — 테이블 바인딩이 **아니라** 문자열 해석 규칙. 자재 ID 원문을 소스로 푸는 **선언된** 관례이며 코드에 박힌 관례는 없다. 미선언이면 모든 자재가 `source_unresolved` → 계획 전체 `unverified`.
> - `source_region` — 선택·**휴면**(라이브 config 미선언. 미선언은 결함이 아니다).
>
> **수량은 저장되지 않고 유도된다** — `zone_layers`(1H=1층·TOP=1층·MID=`stack−이웃 수`) × `painted(값)` = `zone_demand`, 자재당 = `ceil(total / n)`(**배분이 아니라 충분성 검사**). 그래서 페인팅 분포 읽기(`_painted_values`)가 **load-bearing**이고, 실패 시 모든 required가 0이 되어 부족이 영원히 발화하지 않는다 → `painted_reliable`(**~3085**)이 유도 전체를 게이트한다.
>
> **[`1fefd12`] 유령 잔여(phantom remaining) 수정 — 강등 어휘 2종 추가**: ① **`connected(count_only)`** — `transfer_log`가 x/y 없이 바인딩되면 카운트는 실값이되 칩 정체 미상이라 집합 감산이 불가능하다(used_set이 비어 `remaining`이 과대). 강등 엔진이 remaining을 null + 상한(upper bound)으로 내리고, `by_core`의 used/remaining도 **log·area_map 양 경로 모두 null**(가짜 0 금지 — `used_count_only` 플래그 ~1289/~1324). ② **`connected(column_unresolved:<roles>)`** — 선언-미해석 컬럼(config 오타)의 침묵 제거, 기계장치는 `bonding_plan._ResolvedColumns` 공유(`_demote_unresolved`/`_unresolved_of` **356/364**가 위임 래퍼). `fail_values` 선언 + `val` 미해석은 필터 없는 카운트를 **거부**(0 + 강등 — 감산항 과대는 상한 불변식 위반).
>
> **[`deed6d2`] 유령류(phantom class) 마감 — `used_count_only`의 형제 `fail_count_only`(~1365)**: origin_rows(집합 감산) 경로에서 **self-frame fail 원천이 x/y 없이** 바인딩되면 `fail_breakdown`엔 카운트가 실리되 `fail_union`엔 아무것도 안 실려 감산이 그 칩들을 조용히 놓친다(remaining 과대 — 같은 유령류). 판정 지점 ~1397: `connected(count_only)`로 강등해 remaining을 null + 상한으로 내린다. **cnt를 대신 빼지 않는 것이 의도** — 칩 정체 미상이라 used_set·타 fail 원천과 겹칠 수 있고, 과감산은 상한을 **아래로** 깨뜨린다(놓친 점은 union을 줄일 뿐이라 `total − |union|`은 진짜 잔여의 상한으로 유지된다). 폴백 경로(origin_rows 없음 — 카운트 감산)는 좌표 없이도 올바르므로 **강등하지 않는다**. `by_core` used/remaining null은 ~1546–1549/~1596–1597. 테스트: `tests/test_transfer_plan.py` count_only §의 self-frame 4건.
>
> **[`2baf9ff` U9] STACK 0 = marker(상태 표시 값)** — 명시적 `0`은 층수가 아니라 **조건 선언**(예: BASE FAIL)이다. `stack_state`만 `marker`로 승격하고(`_int_state`는 무수정 — band `to`·BIN은 여전히 0 거부), marker 행은 구역 전부 `[]`(구성적 0층)·수요 0·롤업 부재·V3 풀 스캔 제외이며 **V6 하나에만 답한다**(구역에 자재가 있으면 그 모순을 차단으로 보고). blank는 marker로 접히지 않는다 — blank는 "아직 안 적음"(V5), 0은 선언이다.
>
> **좌표 변환 사본 없음** — 이 모듈은 `map_overlay.resolve_map_transform` **하나만** 쓴다(**~1231**). **[7b] 맵 키 정규화 사본도 없다** — 정체성 필터는 `_identity_filters`(**382**) 하나로 모였고 그 안은 `map_overlay.canonical_role_value` 위임이며(**~360–361**), 다른 바인드 지점(**~629–631** · **~1082**)과 origin 맵 정체성 합성(`_origin_map_id` **1513** → `map_overlay.compose_map_id` **~1161**)도 같다. 소스 주석이 **"`map_overlay.canonical_key_value` is THE implementation — do not fork it"**(**~356**)이라고 못박는다. **zone 산술·규칙은 클라 `doe_bands.js`와 공유 벡터로 고정** — [§6-2 `contracts/doe_band_rules/`](#6-2-교차-구현-계약-contracts). 레거시 `bands` 산술(`to` 3상태, prevTo 걷기)은 종전대로 [`contracts/band_arithmetic/`](#6-2-교차-구현-계약-contracts).

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `MAX_*` 하드캡 **15종** + `CORE_ID_SEP="\|"` | `MAX_ORIGIN_POINTS/MAX_FAIL_POINTS=100k` · `MAX_BY_CORE=500` · `MAX_DOE_PER_PLAN=500` · `MAX_PLAN_VALUES=1000` · `MAX_SOURCES_PER_DOE=64` · `MAX_BANDS_PER_PLAN=2000` · `MAX_DEMANDS_PER_PLAN=5000` · `MAX_SOURCES_PER_PLAN=200` · `MAX_BANDS_BLOB_BYTES=256KiB`(**`json.loads`보다 먼저** 재는 유일한 캡) · `MAX_LAYER=2^53` · `MAX_REGION_CELLS=100k` + **[`269b39e` BIN 축] `MAX_BIN_VALUES=200` · `MAX_BIN_CELLS=200k` · `MAX_LOT_SLOTS=50`**. 팬아웃 차단: 수요 총량과 서로 다른 소스 수를 따로 묶는다(실측: 1.53MB blob 1행이 128,000 수요를 냈다) | ~124–145 |
| **`REGISTRY_ROLES` / `REGISTRY_LEGACY_ROLE="bands"`** | 필수 역할 7종(zone) / 폐기 모델 읽기 전용 선택 역할 | ~166/169 |
| `WARN_*` **23종** | validate·강등 경고 타입(`grep -c "^WARN_" = 23` — 2026-07-29 실측, 7c의 `transfer_untracked` 추가로 22→23) — `qty_shortage`(~152) · **`layer_range_invalid`(~167 — 이제 **폐기 모델(`bands`)에서만** 나온다. zone 컬럼엔 "구조를 못 읽는" 상태가 없다. **`reason` 3종**: `unreadable` \| `not_a_band` \| **`not_convertible`(세 구역으로 표현 불가 — 구간 4개·`to` 불량·역전·1층 미시작, `detail` 동봉. 🔴 접어서 통과시키지 않는다** — 뭉갠 읽기를 `replace_map`으로 되쓰면 서버의 진짜 계획이 덮인다). 구 reason `incomplete`/`not_increasing`은 **거부(`not_convertible`)로 승격**)** · **`zone_rule_violation`(~170 — V1–V6 차단, `rule` 필드. 클라 `doe_bands.validateZonePlan`과 같은 판정)** · **`zone_rule_advisory`(~173 — 차단 아님: W-DUP-MAT 등 파생 수치를 움직이는 것)** · **`source_scope_unpriced`(~178 — `MID1`=로트 전체 토큰: 해석 실패가 아니라 "판정 안 함". 0으로 접으면 "다 썼다"로 읽힌다)** · `undefined_doe_value` · `painted_unavailable`(~183 — [B2] 페인팅 분포를 못 읽었다. 유도 모델의 새 의존) · `doe_value_unpainted` · `source_fail_chips` · `source_history_fail` · `stage_unknown` · `source_unresolved` · `source_degraded` · `availability_unreliable` · `source_overallocated` · `result_truncated` · `negative_remaining` · **[BIN 축] `bin_axis_unavailable`(~200) · `bin_population_mismatch`(~202)** · **[로트 전개] `lot_membership_unknown`(~205) · `lot_membership_degraded`(~207) · `lot_slot_map_missing`(~209)** · **[7c] `transfer_untracked`(~222 — 선언된 상태이지 결함이 아니다. 위 7c 문단)**. ⚠️ **~~`layer_coverage_gap`~~은 개명이 아니라 삭제** — zone은 구성적으로 `1..stack`을 덮어 구멍이 **표현 불가**(근거 주석 ~165) | ~172–242 |
| `EFFECT_*` **8종** | 효과 분류(`grep -c "^EFFECT_" = 8` — 2026-07-29 실측, 7c로 7→8) — `population_mismatch`(~198) / `bin_axis_unavailable`(~203) / `lot_expansion_partial`(~210) / **`remaining_upper_bound`(~223, 7c)** / `remaining_overstated`(~235) / `total_unknown`(~236) / `by_core_degraded`(~237) / `history_incomplete`(~238) | ~218–258 |
| **[7c] `TRANSFER_LOG_NONE="none"` / `STATUS_TRANSFER_UNTRACKED="connected(untracked)"`** | 선언 토큰과 그 결과 status — **정확히 이 문자열만** 선언으로 인정한다 | **257/258** |
| **`BIN_OK/BIN_ABSENT/BIN_UNKNOWN` · `BIN_SCOPE_SLOT/LOT`** | BIN 항목 status 어휘 — **`0`은 이 셋 중 어느 것도 대신할 수 없다**(`0`="다 썼다", `bin_absent`="그 BIN이 여기 없다" — 사용자 행동이 다르다. DOE_BAND_MODEL §4-bis) | ~248–252 |
| `load_transfer_plan_config(path=None)` / `get_stages(cfg)` / `_valid_binding(src)` | config 로드(부재·손상 시 부분 가동) / stages dict 추출 | ~265/282/287 |
| **`transfer_log_is_declared_none(src) -> bool`** | **[7c `91386f0` 추출] "전사 기록 없음" 선언 판정의 단일 술어.** 정확히 문자열 `"none"`만 True — `null`·키 삭제·`"None"`은 False(= 종전대로 `missing`). **호출자 2곳**: `_stage_role_statuses`(**414**) · `_summarize_inline`(**1653**) | **313** |
| `_resolve(src_cfg, required)` / **`_demote_unresolved(status, cols)` / `_unresolved_of(cols)`** / **`_identity_filters(src_cfg, cols, lot, slot)`** / `_binding_status(...)` / `_stage_role_statuses(stage_cfg)` / `_plan_store_statuses(cfg)` | 바인딩 → (model, 컬럼맵 — `bonding_plan._ResolvedColumns`) / **[`1fefd12`] `column_unresolved` 강등 위임 래퍼 2종**(기계장치는 bonding_plan) / **[7b 신설] lot/slot 필터 생성의 단일 지점** — 안은 `map_overlay.canonical_role_value` 위임(~340–341) / `connected`\|`missing`(+미해석 마커 합성) / stage 역할별 상태(**[7c] `transfer_log == "none"`이면 `connected(untracked)` ~375–376**)·plan_store 역할별 상태(`registry` + `material_identity` 고정 + `source_region` 선언 시에만) | ~331/339/347/353/368/385/421 |
| **`stage_of_table(cfg, ref_table)`** | **[v2 핵심] `stages.*.target_map.table` 역인덱스** — 열린 테이블에서 stage를 유도한다 | ~450 |
| `list_stages(cfg)` | `GET /api/transfer-plan/stages` 응답 `{stages[], plan_store}` | ~467 |
| `_status_is_degraded` / `_degradation_effect(role, fail_roles)` / `assess_degradation(statuses, fail_roles)` | **[QA F1 1층]** 역할 강등 탐지 → `(경고 리스트, remaining_reliable, total_reliable)`. **[`1fefd12`] `connected(count_only)`·`connected(column_unresolved:…)`도 강등으로 판정**. **[7c] `connected(untracked)`는 강등이 아니다**(사유 주석 **~494**) | ~488/511/525 |
| `build_chips_block(...)` | **[QA F1 3층]** chips 블록 조립 + **음수 remaining 불변식**. 신뢰불가면 `remaining: null`(오표시 구조 차단), `total_reliable ∧ remaining≥0`일 때만 `remaining_upper_bound` | ~564 |
| `load_source_region(...)` / `_region_block(...)` / `_core_region_counts(...)` | 소스 사용 영역 로드(**현재 휴면**) / 영역 내 집계 / core-kind 어댑터 | ~605/643/669 |
| **[BIN 축 `269b39e`]** `parse_bin_request(raw)` / `_bin_axis_binding` / `_bins_unavailable` / `_bin_universe` / `_bin_cell_sets` / **`_bins_block(..., scope=BIN_SCOPE_SLOT, untracked=False)`** / `_merge_bins_over_slots` / `_lot_slots` | `bins=` 파라미터 파싱 / stage의 BIN 축 바인딩 / 불가 블록(`bin_axis_unavailable`) / 맵의 distinct BIN 열거(캡 200, ORDER BY로 재현성) / BIN별 좌표 집합 / **BIN별 total·fail·used·remaining 분해**(requested BIN은 전부 답을 받는다 — 부재는 `bin_absent`, 절대 0 아님. **[7c] `untracked=True`면 used_set이 비어 있으므로 항목마다 `remaining` 대신 상한 + `transfer_untracked` 플래그** ~903–913) / `scope=lot` 슬롯 합산 / 로트→슬롯 전개(대장 조회, 캡 50) | ~751/773/791/801/836/863/969/1054 |
| `_reshape_m1_summary(m1, stage_name, stage_cfg)` | M1 `bonding_plan.get_core_summary` 응답을 M2 공통 형태로 재성형 | ~1090 |
| `_fetch_pairs(...)` / **`_origin_map_id(source_cfg, origin_lot, origin_slot, binding=None)`** | 좌표쌍 페치(캡 적용) / origin map_id 조립 — **[7b] `binding` 인자 추가**: 메타 행이 등록된 **그 테이블의 선언 타입**으로 정규화해야 `'LOT'+'01'`이 `'LOT_1'`로 합성된다. 본체는 `map_overlay.compose_map_id` 위임(~1071) | ~1137/1153 |
| `_canonical_origin_meta(...)` / `_canonical_fail_set(...)` | origin-frame 원천의 canonical 맵 메타(첫 원천이 기준, 메타 없으면 None — 뒤로 넘어가지 않는다) / fail 좌표를 `map_overlay.resolve_map_transform`(~1177)으로 canonical 프레임에 사상 | ~1165/1203 |
| `_collect_history(db, source_cfg, lot, slot)` | process_history 최근 N건 + result fail 경고 | ~1246 |
| **`_summarize_inline(db, stage_name, stage_cfg, lot, slot, region=None, want_bins=False, bin_request=None, bin_refused=None)`** | **가용 엔진 정본(tape-kind)** — ⚠️ **시그니처 정정(2026-07-29)**: 종전 지도의 `bins=None` 단일 인자는 소스에 없다. BIN 축은 **`want_bins`(요청 여부) + `bin_request`(파싱된 목록) + `bin_refused`(거부 사유)** 3분할이고, 이 분할이 "요청 안 함 / 요청했으나 거부 / 요청했고 답함"을 구분한다. — `origin_log` 연결 시 `remaining = total − \|fail_union ∪ used_set\|`, 미해석 시 M1식 감산 폴백. `by_core` 7키 + `by_core_origin` 마커 `"log"`\|`"area_map"`(`fail=None`으로 0 위장 금지). **[`1fefd12`] `transfer_log`가 x/y 없이 바인딩되면 `connected(count_only)` 강등**(`used_count_only` ~1289/~1324). **[`deed6d2`] self-frame fail 원천의 x/y 부재도 같은 강등**(`fail_count_only` ~1365/~1433). **[7c] `transfer_log == "none"` 선언은 `used_untracked`**(~1254/~1256–1265) — 강등이 아니라 선언이라 `base_reliable`을 깎지 않고, `transferred=None`(~1624) + `remaining_upper_bound` + `transfer_untracked` 경고(~1608–1614)로 나간다. fail 소스의 `val` 미해석은 카운트 거부(0 + 강등) | ~1293 |
| `_bin_warnings(bins)` / `get_stage_source_summary(db, cfg, stage_name, lot, slot, bp_config=None, ref_table=None, map_key=None, bins=None)` / **`get_lot_bin_summary(db, cfg, stage_name, lot, bins=None, bp_config=None)`** | BIN 블록 경고 승격 / **핸들러 진입점(scope=slot)** — 미선언 stage `KeyError`(→404) / **[`269b39e`] scope=lot 진입점** — 슬롯 전개 후 BIN 합산, **`chips` 없음**(로트 단위 헤드라인 잔여를 지어내지 않는다) | ~1826/1856/1909 |
| `_plan_store_binding(cfg, role, required)` | plan_store 역할 바인딩 (⚠️ `_num`은 삭제된 채 유지 — 저장 수치 파싱 없음) | ~2029 |
| **`_parse_bands(raw) -> (밴드[], 읽었는가, 거부된_원소_수)`** | **[레거시 `bands` 경로]** 3-튜플(호출부 `bands, readable, dropped = …` ~2913). **"못 읽음"과 "구간 없음"을 절대 합치지 않는다.** 객체가 아닌 원소는 거부하되 조용히 버리지 않는다(세어서 `layer_range_invalid reason:"not_a_band"`로 표면화). 크기 검사가 `json.loads`보다 **먼저** | ~2035 |
| `_band_seq(raw)` / `_band_materials(band)` / `_assign_band_seqs(bands)` | [레거시] 선언 `seq` 판독(정수값 float 허용 — `JSON.parse`가 먼저 접으므로 클라는 물리적으로 거부 불가) / 자재 목록 정규화(문자열 아님 거부) / 계획 내 `seq` 유일화 | ~2072/2104/2133 |
| `BAND_TO_OK/BLANK/INVALID` · **`STACK_MARKER`** · **`_int_state(raw)`** · `_band_to(band)` · **`_bin_of(raw)`** · `_prev_to(bands, i)` | 판정 어휘 3종(~2048–2050) + **[`2baf9ff` U9] `STACK_MARKER="marker"`(~2054 — STACK 전용 제4상태.** `_int_state`에서 절대 나오지 않고 **`stack_state`만 명시적 0을 승격**한다 — band `to`·BIN은 여전히 0 거부. 클라 `stackState`의 `'marker'` 미러) · **[`b35bc9f` 신설] 단일 정수 판독기** — `stack`과 `to`가 **같은 판독기**를 쓴다(클라 `bandToState` 미러. `'7.5'`→invalid — 컬럼 타입이 아니라 이것이 가독성을 결정) · `to` 판정(_int_state 위임) · BIN 라벨 판독 · prevTo 걷기(blank·invalid 동일 스킵, invalid는 보고) | ~2162–2168/2173/2215/2225/2244 |
| **[zone 코어 `b35bc9f`·`2baf9ff` — `doe_bands.js` 미러, 정본은 `contracts/doe_band_rules`]** `parse_material_list(raw)` / `_zone_tokens` / `_zone_row_get` / `stack_state(row)` / `mid_zone(row)` / `zone_layers(row, zone)` / `zone_demand(row, zone, painted)` / `parse_material_token(raw)` / **`material_pool_key(tok)`** / `_zone_raw_items` / `validate_zone_plan(rows)` / `_format_layer_runs` / `material_rollup_rows(rows, painted_of)` / `REMAINING_UNKNOWN_REASON` / `remaining_state(availability, used)` / **`bands_to_zones(bands)`** | mat_* JSON 배열 판독 / 행별 토큰 수집(비문자열 거부) / 행 키 접근자 / **`stack` 4상태(ok·blank·invalid·marker — 명시적 0만 marker, 음수는 invalid로 값 보존)** / MID 구간 유도(marker는 `{size:0, known:true}` — E행의 0층과 같은 "진짜 0") / 구역 층수(1H=1·TOP=1·MID=stack−이웃, **marker는 전 구역 `[]`**) / 구역 수요 = painted×layers / 토큰 → `{lot, slot?, bin?, scope}` 문법 / **풀 정체 키 — 분리자 조인이 아니라 `json.dumps([lot, bin])`**(U+001F 조인이 디스크에서 분리자를 잃고 두 풀을 합산한 사고의 재발 방지) / 원소 판독 / **V1–V6 차단 규칙**(+W-DUP-MAT advisory ~2516 — **marker 행은 V6 하나에만 답한다**: V6 블록 ~2448–2463, V3 풀 스캔 제외 ~2534) / 층 구간 표시 / MAT×BIN 롤업 행(**marker 행은 부재** ~2588 — "사용 0" 행이 아니라 아예 없음) / 미상 사유 어휘 / 잔여 판정(신뢰 불가 가용은 잔여를 억제) / **레거시 band 계획 → zone 사상**(불가하면 `not_convertible`로 거부 — 손실 접기 금지) | ~2266/2292/2337/2342/2366/2390/2413/2433/2486/2521/2688/2765 |
| **`_material_identity_rule(cfg)` / `_split_material(material_id, rule)`** | 자재 ID → 소스 `(lot, slot)`. 규칙은 **`plan_store.material_identity` 선언으로만** 성립. 분해는 뒤에서부터(클라 `splitMaterialId`와 방향 동일, `map_overlay.build_key_filters`는 반대). **분리자가 없으면 거부** | ~2829/2848 |
| `_painted_values(db, ref_table, map_key, overlay_cfg)` | 대상 맵 자신의 셀 값 분포 group-by(`ORDER BY` — 절단 재현성, 근거 주석 **~2891**). 반환 `({값: 셀수}, 상태, 절단여부)` — 세 번째 값이 [B2]의 핵심 | ~2881 |
| `validate_plan(db, cfg, ref_table, map_key, overlay_cfg=None)` | **핸들러 진입점** — **`plan_store.registry` 미구성은 `LookupError`(→404)**. 레지스트리 1회 조회(`ORDER BY value` — 절단 재현성, 근거 주석 **~3353**). **[zone] 행별로 `stack`/`mat_*`를 먼저 읽고**(내부 `_reg_get` **3361**, zone_row 조립 **3379**), zone이 비어 있으면 레거시 `bands`를 `bands_to_zones`로 사상(~2913 — `REGISTRY_LEGACY_ROLE` 미선언이면 그마저 없음). **`validate_zone_plan` 호출 ~2994이 V1–V6을 채점**하고 위반은 `zone_rule_violation`으로. marker 행은 수요 유도에서도 자연 소멸(`zone_layers`가 `[]` — 자재 해석·조회·수요 0, 주석 ~3111). **[B2] `painted_reliable`(~2968)이 유도 전체를 게이트**(소비 ~3008/3024/3070). `remaining_reliable=False`면 부족·fail 판정 전부 생략 + `availability_unreliable`만. 캡 절단은 `result_truncated`를 역할·캡별로 각각 발행. **`structural_refusal`(~2877, 세트 ~2895/2919/2951)이 `availability_checked`에 AND로 물린다**(~3273). 최종 `status`는 `ok`/`warnings`/**`unverified`**(~3293–3299) 3값 — "검사 안 함"과 "이상 없음"을 같은 값으로 내지 않는다. **[7c] `transfer_untracked`도 unverified 사유로 이름을 갖는다**(~3185–3191) | ~2931 |

---

---

## 5-A. 2026-07-30 신설 서버 모듈 8종

**한 세션에 서버 파일 8개가 새로 들어왔다(신설 당시 3,654줄 → 현재 **4,094줄**. 2026-08-04 전건 재합산 `41b17ee`: value_suggest 1,154 + map_preset_routing 536 + graph_orphans 481 + chain_replay 635 + **enrichment_analysis 548** + enrichment_candidates 613 + keyset_scan 89 + time_format 38 — **이번 범위에서 바뀐 것은 `enrichment_analysis`(532 → 548) 하나뿐이고 나머지 일곱은 blob 동일이다**).** 계보가 셋이다 — **인리치먼트/체인 재생**(4종) · **온톨로지 고아 스윕**(1종) · **입력 제안·프리셋 라우팅·시간 포맷**(3종).

> 🔎 **도달 경로를 먼저 읽어라.** `main.py`는 여전히 `chain_replay`·`enrichment_candidates`·`keyset_scan`을 import하지 않는다. `enrichment_analysis`만이 예외로, `GET /admin/enrichment/auto-confirm/dry-run`이 **함수 안 지연 import**로 `run_auto_confirm_sweep(apply=False, ignore_knob=True)`를 부른다([§1.4](#14-api-라우트-표--어드민운영그래프맵인리치먼트)).
>
> ⚠️ **blob 동일은 「지도가 이 파일을 옳게 적었다」가 아니다.** 그래서 이번 패스는 무변동 일곱 개에 대해 **파일 끝 쪽에서** 표본을 뽑아 대조했다 — `value_suggest.classify_seek_plan` **1055** · `index_targets` **1093** · `_index_state` **993** / `enrichment_candidates.AutoConfirmCollector` **487** · `log_stats` **475** · `confirm_keys` **396**. 전건 일치라 아래 앵커를 그대로 둔다.
>
> 🔴 **"아직 UI 표면이 없다"는 이제 절반만 참이다.** 어드민에서 도달 가능해진 것은 **측정 둘**(해석 보고서 + 드라이런)뿐이고, **쓰기(`--apply`)는 여전히 CLI에만 있다** — 자동확정의 실제 쓰기는 체인 워커(`AutoConfirmCollector`)와 `server/scripts/enrichment_insights.py`가 유일한 경로다. ①의 **원클릭 확정 버튼**은 아직 없다.

| 파일 | 줄 | 역할 · 앵커 |
|---|---|---|
| **`server/keyset_scan.py`** | 89 | **[전 테이블 순회의 단일 구현]** `iter_pages(db, model, columns=None, condition=None, chunk_size=DEFAULT_CHUNK_SIZE, limit=None, max_row_id=None)`(~38, **행이 아니라 페이지(list)를 yield** — 호출자가 페이지당 묶음 쿼리 1회를 하게 해 N+1을 막는다) · `current_max_row_id(db, model)`(~85) · `DEFAULT_CHUNK_SIZE=1000`(~35). `row_id > last` 시크이고 **OFFSET을 쓰지 않는다**. ⚠️ **`columns`에 `row_id`를 넣지 마라** — 순회가 커서를 소유해 **맨 앞에 끼워 넣으므로**(`row[0]`이 항상 커서) 중복 지정은 하류 인덱스를 조용히 밀어낸다(`enrichment_analysis`·`chain_replay` 둘 다 `row[1:]`을 위치로 언팩한다). **`max_row_id`는 최적화가 아니라 정확성 요건**이다: 타깃 테이블이 곧 트리거 테이블인 재생은 이 스냅샷 없이는 자기가 방금 쓴 행을 만나 **끝나지 않는다**. ✅ **"백필의 수제 루프 2개를 대체했다"는 주장 검증됨** — `6422326` diff에서 `_load_existing_business_keys`·`run_backfill`의 `while True` 커서 루프 둘이 삭제됐고, 현 소비자는 백필(2곳)·`enrichment_analysis.iter_derived_rows`·`chain_replay.replay_rule`이다. ❌ **다만 "서버 유일의 순회"는 아니다** — `graph_materializer.resync_table`은 자체 사본을 유지하고(동시 라운드가 그 파일을 잡고 있었다) 그 유보가 docstring에 **명시**돼 있다 |
| **`server/chain_replay.py`** | 🆕🆕🆕🆕 **947** @`347de78`(712 → **+235**) 🆕🆕🆕🆕 **R3 신설 — `recompute_display_values(db, table_name, columns=None, row_ids=None, apply=False, chunk_size=…, limit=None, max_report=DEFAULT_MAX_REPORT, log=…) -> dict`.** R1·R2는 **저장된 것을 바꾸지만** R3는 아무 `cell_sources` 행도 만들거나 지우거나 고치지 않는다 — `compute_priority_value`가 「어느 저장된 레이어가 이기는가」를 다시 답하고, 그 답이 움직인 셀만 **표시 컬럼을 재기록**한다. 존재 이유는 `compute_priority_value`의 tie-break 수정이 **미래의 쓰기만** 고치기 때문(과거에 잘못 확정된 값은 재배달이 없으면 영원히 그대로). **안전장치는 최적화가 아니다** — 레이어 2개 미만인 셀은 절대 건드리지 않는다(1개는 동률이 없고, 0개는 다른 쓰기 경로가 소유한 컬럼을 `(None, None)`으로 지울 수 있다). 바뀐 셀마다 `AuditLog`(`source_name=R3_AUDIT_SOURCE="resolution_recompute"`, `updated_by="resolved:<승자 소스>"`)를 남겨 클라 이력 타임라인이 그대로 설명한다. `keyset_scan.iter_pages`로 페이지당 커밋(대형 실행은 재시작 가능). 반환 `changes`(최대 `max_report`)+`changes_truncated`, `changed_by_tiebreak`/`changed_by_stale_materialisation`/`pinned_changed`/`pinned_examined` 카운터 분리.<br>🔴 **R2·R3가 판정 로직을 공유하도록 추출된 헬퍼 둘** — **`_load_cell_state(db, table_name, chunk_row_ids) -> (sources, pins)`**(청크 전체를 배치 질의 2개로, 셀당 질의 아님. `sources[(row_id,col)][source_name] = {"value","ingested_at"}` — `ingested_at`이 함께 실리는 것이 `compute_priority_value`의 tie-break 입력이다) / **`_resolve_cell(table_name, col_types, row, col, cell_sources, pin, exclude_source=None) -> dict`**(저장된 레이어에서 "무엇을 보여줘야 하는가"를 다시 답하되 **쓰지 않는다** — dry-run과 apply가 같은 계산을 돈다. `exclude_source`가 R2를 "레이어 하나 뺀 R3"로 만드는 유일한 차이). **`withdraw_source`(R2)는 이번에 이 둘로 재배선됐다** — 종전엔 자기 안에서 남은 레이어를 조립했다. 🆕🆕 **[DT/core 체인이 재생 경로에 요구한 것 셋]** `_map_metadata_outputs(result, rule, target_table)` · `_scoped_batch_outputs(result, rule, target_table)` · `_apply_replay_batch(db, schemas, crud, table_name, items, run_id, stats, page, replace_map=False, scope=None)` — 🔴 **맵퍼가 이제 한 규칙에서 *여러 타깃 모양*을 낸다**(메타 행 · 스코프된 배치). 재생이 라이브 경로와 같은 쓰기를 하려면 그 분해가 여기에도 있어야 한다([§5-G](#5-g--dtcore-프레임-유도-체인-2026-08-11-신설-등재)).<br>🆕 **`count_withdrawable(db, table_name, source_name, columns=None) -> {cells_claimed, pinned}`**(집계 2개, 요청 경로 안전 — R2 미리보기) + `_claimed_filter(...)` 추출로 `withdraw_source` 1단계가 같은 술어를 쓴다. 🔴 **비용 주석이 실측으로 정정됐다**: 구 인덱스 `idx_sources_lookup_source`는 `source_name`이 **마지막**이라 Seq Scan(861ms / 263,369 buffers / 13.1M행)이었고, `idx_sources_by_source`는 **10.9ms / 1,106 buffers**다 | **[R1 규칙 소급 재적용 / R2 소스 철회]** "기계 판단은 철회할 수 있어야 안전하다"의 두 절반. `load_rules`(~94)·`find_rule`(~105)·`order_rules`(~114, 생산자→소비자 위상 정렬)·`is_self_triggering`(~159)·**`replay_rule(db, rule, apply=False, limit=None, chunk_size=…, log=…)`(~201)**·`replay_all`(~378)·**`withdraw_source(db, table_name, source_name, columns=None, row_ids=None, apply=False, chunk_size=…, log=…)`(~404)**·`class ReplayRefused`(~86). 상수 `WRITE_CHUNK=1000`(~65)·`SAMPLE_LIMIT=20`(~66)·`R1_SOURCE_NAME="chain_ingestion"`(~71)·`R2_AUDIT_SOURCE="chain_replay_withdraw"`(~74)·**`SKIP_BLANK=True`(~78)**·**`PROTECTED_SOURCES=frozenset({"user"})`(~83)**.<br>🔴 **R1은 공백을 절대 쓰지 않는다** — `SKIP_BLANK`은 **파라미터가 아니라 모듈 상수**다. 맵퍼가 빈 값을 돌려주면 `skipped_blank_cells`로 세고 **R2 후보로 보고**한다("규칙이 여기서 아무것도 못 만든다"는 R1이 아니라 R2의 문장이다). 끄면 부재가 조용히 "쓰인 빈 값"이 된다.<br>🔴 **R1이 `source_name="chain_ingestion"`으로 쓰는 것이 의도다** — 라이브 워커 자신의 provenance라서 ① 사용자 레이어(0)가 특별 분기 0줄로 이긴다 ② 워커의 `source_name != "chain_ingestion"` 루프 필터가 재생의 outbox 이벤트를 떨어뜨린다. **개명하면 루프 가드와 사람 보호 논거가 동시에 깨진다.**<br>**R2의 이중 거부**: `PROTECTED_SOURCES`면 raise, 사람이 Pin한 셀(`manual_priority_source`가 철회 대상)은 skip + `pinned_skipped`. ⚠️ **표시값이 안 바뀌어도 provenance는 지운다** — `value_unchanged`로 센 셀은 그 `cell_sources` 행을 잃고 **감사 항목이 남지 않는다**(카운트가 유일한 흔적). 도달: CLI `server/scripts/chain_replay_cli.py`(155→**210**줄). 🆕🆕🆕🆕 **[`347de78`] `resolve <table> [--columns a,b] [--row-ids …] [--limit N] [--apply]` 서브커맨드 신설**(R3 노출) — 기존 `replay`/`replay-all`/`withdraw`/`list`와 나란히 |
| **`server/enrichment_analysis.py`** | **548** (532 → **+16**: 큐 술어의 번역기 출처가 `main`에서 **`column_filter`**로 바뀌고, 그 사유가 모듈 docstring **~16–40**에 기록됐다. 앵커는 **전건 +16~+20** 이동) | **[④ 원인 분류 / ② 규칙 승격 제안 / ① 스윕의 드라이런]** 전부 읽기 전용(①의 `--apply` 제외). `iter_derived_rows`(**110**)·**`classify_queue(db, rule, probe_limit=200, limit=None, log=…)`(**217**)**·`_human_resolved_cells`(**336**)·**`analyze_promotions(db, rule, min_support=3, limit=None, log=…)`(**361**)**·`_proposed_reference_view`(**475**)·`run_auto_confirm_sweep(db, rule, apply=False, limit=None, ignore_knob=False, log=…)`(**500**)·`class AnalysisRefused`(**72**)·`_source_target_presence`(**171**). 분류 어휘 `CLS_MAPPING_GAP`(**61**, **버그 계급**)·`CLS_NO_SOURCE_ROWS`·`CLS_RESOLVABLE`·`CLS_AMBIGUOUS`·`CLS_NO_EVIDENCE`·`CLS_UNPROBED`(**66**) + `BUG_CLASSES`(**68**)/`REAL_WORK_CLASSES`(**69**).<br>🔴 **큐 술어를 여기서 다시 정의하지 않는다** — `_queue_condition`(**80**)이 `enrichment_config.to_public_rule(rule)["queue_filters"]`를 받아 **`column_filter.get_column_filter_condition`**(즉 `GET /tables/{t}/data`와 **같은 번역기**)로 변환한다(호출 **~101**). 그래서 워크리스트·배지·어드민 카운트·이 리포트가 어긋날 수 없다. 번역 불가 필터는 폴백이 아니라 `AnalysisRefused`.<br>🔴 **⚠️ 여기 있던 서술은 지금 시행되는 규칙의 정반대였다 — 정정.** 구 지도: *"`main` import가 함수 안 지연 import인 것이 의도다(워커에서 웹앱을 끌어오지 않기 위해) — 모듈 스코프로 올리면 그 성질이 깨진다."* **틀렸다.** 소스가 그 문장을 이름으로 반박한다(**~32–40**): *"지연 import는 `main`을 안전하게 만든 것이 아니라 늦게 만들었을 뿐이다."* 스케줄러가 컬렉터 디렉터리를 `sys.path[0]`에 꽂으므로 그 프로세스에서 `import main`은 **엉뚱한 파일에 바인딩**되고, 결과는 `module 'main' has no attribute 'get_column_filter_condition'`인데 **같은 작업을 CLI에서 돌리면 성공**했다. 지금 이 파일이 부르는 것은 **`import column_filter  # NOT main`**(**~88**)이고, 소스 주석이 그 `# NOT main`을 그대로 달고 있다. 전문은 [§1.8](#18-servercolumn_filterpy--필터-dsl-번역기가-엔트리포인트-밖으로-나간-자리-신설).<br>**②는 `source_name == 'user'` 셀만 채굴한다** — 넓히면 기계 추측(백필·이전 자동확정)이 config 규칙으로 세탁된다. 선행절은 `decision_key`의 **진부분집합**이어야 하고(단일 컬럼 키는 `refused: "no_proper_subset"`), 생성된 뷰는 전부 `enrichment_config._validate_view_sql`을 통과해야 제안이 된다. 도달: CLI `server/scripts/enrichment_insights.py`(200줄)뿐 |
| **`server/enrichment_candidates.py`** | **613** (591 → **+22**, `f9289f6`) | **[① "후보가 하나면 그것은 판단이 아니라 동의다"]** 📐 **앵커 이동 다섯 구간**(구 39 이전 무이동 · 40–136 +6 · 137–320 +19 · 321–322 +23 · 323–327 +20 · 328 이후 +22).<br>**`resolve_target_candidate(db, rule, key_values, target_field)`(**~281** — THE 술어)**·`find_unresolved_cells`(**~371**, **부재 전용 관문**)·**`confirm_keys(db, rule, keyed_rows, apply=False, stats=None, tx_prefix=None)`(**~396**)**·`declaring_views`(**~240**)·`candidate_target_fields`(**~246**)·`rule_auto_confirm_enabled`(**~220**)·`global_auto_confirm_enabled`(**~191**)·`max_keys_per_unit`(**~205**)·`_refused`(**~251**)·`log_stats`(**~475**)·`reset_warnings`(**~186**)·`_warn_once`(**~179**)·`_load_ingestion_settings`(**~161**)·**`class AutoConfirmCollector`(**~487** — `__init__(derived_table, rules=None, settings=None)` **~502**(「`candidate_for` 0건」 경고는 **~522**의 `_warn_once` 호출) · `collect(items)` **~534** · `pending()` **~563** · `flush(db)` **~566**)**.<br>**[F9] `_diagnose_probe_failure(db, view, column, key_values) -> str`(**~258**) — 「컬럼이 없는 건가, 뷰가 깨진 건가」의 판별자.** 구 행 기반 경로는 결과의 컬럼 목록을 읽어 이 둘을 **공짜로** 갈랐지만, 그룹 프로브는 컬럼명을 **SQL에 보간**하므로 없는 이름이 다른 드라이버 오류와 구분되지 않는다. 둘을 `view_error`로 뭉개면 **「`candidate_for`가 뷰에 없는 컬럼을 지목한다」는 유일한 사유가 사라진다**. 그래서 **실패했을 때만** 평범한 표시 래핑(`execute_reference_view`)을 한 번 더 돌려 컬럼 유무를 묻는다 — **행복 경로의 비용은 정확히 쿼리 1회 그대로.** 🔴 **[`f9289f6`] 이 판별자는 그때까지 PG에서 도달 불가였다** — 재조회가 **같은 세션**에서 일어나는데 앞선 실패가 트랜잭션을 abort시켜 두었기 때문이다. `enrichment_config._isolated_execute`의 SAVEPOINT가 그것을 고쳤다([§5](#5-소형-서버-모듈)).<br>**[F9] `REASON_PROBE_TRUNCATED = "probe_truncated"`(**~143**)** — 프로브가 `enrichment_config.CANDIDATE_PROBE_MAX_ROWS`에 닿아 **읽기가 잘렸다**는 뜻.<br>🆕 **[`f9289f6`] `REASON_DISTINCT_TRUNCATED = "distinct_truncated"`(**~156**) — 이름 있는 거절이 하나 늘었다.** 🔴 **구 지도가 이 사실을 정반대로 적고 있었다**: *"이미 2개 이상이라 호출자의 `ambiguous`로 자연히 흘러간다"*. **틀렸고, 소스가 그 이유를 주석(**~144–155**)에 적어 두었다** — 이 함수는 `crud.clean_str_value`로 값을 **접는다**(**~332**). 잘려 돌아온 `limit+1`개 그룹이 전부 같은 정규값으로 접히면 distinct는 **1개**가 되고 판정은 `single`이 된다. 실증(`limit: 1`): `pairs=[('WF01',1), ('WF01 ',1)]` → 접으면 `{WF01}` → `single`, 그러나 잘려나간 곳에 **WF02**가 있었다. **절단은 접기 이전의 사실**이므로 그 자체가 거절이고, 두 절단은 **같은 자세로 나란히** 세워진다(**~345–350**: `row_truncated` → `probe_truncated`, `distinct_truncated` → 동명 사유).<br>🔴 **`resolve_target_candidate`의 실행 형태 — 시그니처는 그대로다.** `enrichment_config.execute_candidate_probe`(뷰 결과 **전체**에 GROUP BY)를 부른다. `support`는 GROUP BY의 count 합이고 `evidence[]`(**~337–340**)에 `rows`(= 창 함수가 센 `scanned`)/`distinct_values`/`candidate_rows`/`distinct_truncated`가 실린다.<br>🔴 **`SOURCE_NAME="enrichment_auto_confirm"`(~97)은 `crud.SOURCE_PRIORITY`에 의도적으로 없다** → 99(최하위) → 사용자 편집(0)이 언제나 이긴다. **등록하는 단 한 줄이 기계 확정을 사람 위에 올린다.**<br>🔴 **뷰 하나가 실패하면 판정 전체가 오염된다**(**~355–359**) — 선언 뷰 중 **아무거나** 에러면(`view_error`/`missing_bind`/`candidate_column_missing`/`probe_truncated`/**`distinct_truncated`**) 생존 뷰들이 **정확히 한 값에 합의해도** 결과는 `refused`다. 부분 발견은 UI용으로 `value`/`support`에 실리지만 쓰기를 관장하는 것은 `status`뿐.<br>🔴 **`DEFAULT_ENABLED=False`(~104)** — 형태가 같은 M3 등록기는 기본 ON인데 여기만 OFF다. 이 모듈이 쓰는 필드의 **공백이 곧 큐 소속의 정의**라서, 잘못된 확정은 항목을 워크리스트에서 **빼내 다시 검토되지 않게** 만든다. 이중 관문(전역 킬 스위치 `GLOBAL_KILL_SWITCH_KEY` ~109 + 규칙별 `RULE_KNOB` ~103) 둘 다 필요. `REASON_CELL_HAS_PROVENANCE`(~137)는 행 부재보다 엄격하다 — **누가 썼든** 타깃 셀에 `CellSource`가 있으면 차단. 캡 `DEFAULT_MAX_KEYS_PER_UNIT=200`(~118) — 키마다 선언 뷰 수만큼 쿼리가 나가므로 **1000만 행 인제션과 쿼리 폭풍 사이의 유일한 방벽**이고, 초과 키는 조용히 버려지지 않고 `REASON_OVER_CAP`으로 세어 워크리스트에 남는다.<br>**도달: 워커 호출자 1곳** — `chain_ingestion_worker.process_chain_transaction_group`(~373) 안 **~487**에서 `AutoConfirmCollector(target_table)` 생성→`collect`→`flush`, `crud.apply_batch_updates` **직후** M3 `MapMetaCollector`와 나란히. 전체가 `try/except`(**~486–497**). ⚠️ **그 `except`가 무엇을 사지 못하는지는 [§4](#4-serverchain_ingestion_workerpy--체인-워커)를 보라** — 체인 쓰기는 정말 커밋돼 있지만(`server/database/crud.py`의 `apply_batch_updates` 말미 `db.commit()`) 오염된 세션은 이 블록을 **탈출한다**. 그리고 **[F9]로 읽기 경로가 하나 늘었다** — `config_resolve_report._rule_fields`가 `declaring_views`를 불러 「어느 뷰가 어느 필드의 후보를 나르는가」를 보고서에 싣는다([§5-B](#5-b-serverconfig_resolve_reportpy--내-config가-먹었는가의-답-f3fd785-신설)) |
| **`server/graph_orphans.py`** | **481** (449 → **+32**) 🆕 **`count_zero_edge_nodes(db, labels=None) -> int`** + `_zero_edge_condition(db)` 추출 — 미리보기와 스윕이 **「차수 0」의 정의 하나**를 공유한다. ⚠️ **상한(upper bound)으로 문서화돼 있다**: 생산 가능성 검사와 예산 가드가 비싼 절반이고 이 집계는 그것을 돌지 않는다 | **[그래프 고아 노드 스윕 — 프로덕션 유일의 `graph_nodes` DELETE 경로]** `sweep_enabled`(~94)·`load_declaration(known_tables=None)`(~101)·**`declaration_blockers(mappings, rejections)`(~125)**·`find_orphans(db, mappings, labels=None)`(~213)·`report_duplicate_source_edges(db)`(~242, 읽기 전용·스윕 대상 아님)·**`plan_sweep(db, mappings, labels=None, max_fraction=…, min_population=…)`(~264)**·`apply_sweep(db, plan)`(~318)·`format_plan_summary(plan, blockers=None, applied=None)`(~332)·`due(last_run_monotonic, now_monotonic=None)`(~362)·**`run_scheduled(known_tables=None, apply_deletions=True, …)`(~375)**. 상수 `CHUNK=1000`(~75)·`DEFAULT_MAX_FRACTION=0.5`(~78)·`DEFAULT_MIN_POPULATION=10`(~81)·`SWEEP_INTERVAL_SEC=86400.0`(~85)·`CHECK_INTERVAL_SEC=1800.0`(~89)·`ENABLE_ENV="GRAPH_ORPHAN_SWEEP_ENABLED"`(~91).<br>**왜 필요한가**: `graph_materializer._retarget_stale_edges`는 **엣지**를 지우고 남은 노드를 지우는 것은 아무것도 없다 → **정체성을 바꾸는 셀 편집마다 노드가 누출**된다. 라이브 실측 2026-07-30: 반복 resync를 견딘 **차수 0 노드 12,761개**.<br>🔴 **고아 정의는 두 조건 AND**다: ① 엣지 0개 ② **현 매핑 중 어느 것도 그 `(label, identity_key)`를 생산할 수 없다**. 차수 0 단독은 불충분하다 — `SplitCondition`은 평균 차수 0.2가 정상이라 차수 0 스윕은 **DOE 어휘를 지운다**. 생산 가능성은 `graph_materializer.compose_identity`로 판정해 **두 번째 identity 구현이 생기지 않게** 한다. 안전 4층: 생산가능성 / **라벨별 예산 관문**(모집단의 `max_fraction` 초과 손실은 삭제가 아니라 `declined` — 매핑 오타는 은퇴한 라벨과 겉모습이 같다. `min_population` 미만 라벨은 비율 검사 면제) / **깨끗한 선언 전제**(`rejections`가 하나라도 있으면 스윕 전체 거부) / 가역성(노드는 RDB 유도물이라 resync가 복원).<br>⚠️ **격리 데이터루트 관문은 CLI에만 있다** — `run_scheduled`는 `apply_deletions=True`가 기본이고 스케줄러가 가리키는 DB에 대해 그냥 지운다(env 스위치와 blockers만이 방벽). ✅ **`server/scripts/graph_orphan_sweep.py`(160줄)는 진짜 CLI 껍데기로 축소됐다** — `530fdfd` 이전 263줄에 있던 탐지·삭제 로직(`CHUNK`·`_zero_edge_nodes`·`_producible_identities`·인라인 delete 루프)이 **전부** 사라지고 플래그·격리 게이트(`--apply`+비격리+`--allow-production` 없음 → exit 2)·blocker 게이트(exit 3)·출력만 남았다 |
| **`server/value_suggest.py`** | **1,154** (902 → +252, `a5eb934`) | **[F3 유일값 조회 + 프로젝트의 단일 프리픽스 술어]** ⚠️ **`a5eb934`로 이 모듈의 앵커는 전부 밀렸다** — 아래는 `a82aa47` blob `a1d7a5e` 실측이다. `load_config`(~214)·`resolve_settings`(~228)·`_resolve_column_map`(~268)·**`prefix_upper_bound(prefix)`(~298)**·`byte_order(expr, is_postgres)`(~331)·**`db_fold(db, prefix)`(~341)**·**`prefix_conditions(col, folded, is_postgres)`(~373)**·`_short_hash`(~403)/`suggest_index_name`(~408)/`suggest_index_definition`(~431)·`_mirror_negative`(~456)/`numeric_prefix_ranges`(~483)·`_resolve_target`(~536)·`_canonical`(~573)·`_stop_reason`(~585)·**`text_seek_query`(~610)**·`_text_values`(~635)/`_numeric_values`(~671)·**`suggest_values(db, table, column, prefix="", limit=None, settings=None)`(~715)**·**`_slow_reason`(~842)**·`_diagnose`(~868)·**`_index_advice`(~896)**·`_why_not_a_target`(~927)·`_approx_row_count`(~967)·`_index_state`(~993)·**`classify_seek_plan`(~1055)**·`index_targets`(~1093)·`class SuggestValidationError`(~201). 정책 기본값은 `DEFAULTS`(~120) 한 dict: `default_limit`50·`max_limit`200·`min_prefix_length`0·**`max_probe_values`400**·**`timeout_ms`1500**(요청 `statement_timeout`과 시크 루프 데드라인 **양쪽**)·`index_min_rows`10000. `LIST_MAP_KEYS`(~179)·`SYSTEM_PREFIX_INDEX_TARGETS`(~184)·`INDEX_PREFIX="idx_suggest_"`(~186)·`_MAX_IDENTIFIER=63`(~187)·`_MAX_MAGNITUDE=15`(~198)·`_MAX_CODE_POINT`(~295)·`_INDEX_USABLE/_INVALID/_ABSENT`(~988–990)·`PLAN_OK`/`PLAN_NO_INDEX_COND`/`PLAN_PREFIX_NOT_A_RANGE`/`PLAN_FILTER_DISCARDS`(~1039–1042)·`_MAX_DISCARDED=100`(~1052).<br>**왜 `SELECT DISTINCT … LIKE 'p%'`가 아닌가** 둘: ① `Korean_Korea.949` PG에서 평범한 btree는 `LIKE prefix%` 범위를 못 서빙해 인덱스를 고른 뒤 전 엔트리를 Filter로 버린다 → 그래서 이 모듈이 **정렬이 곧 바이트 순서인** 인덱스 `(lower(col) COLLATE "C", col COLLATE "C")`를 소유한다 ② `DISTINCT`는 스캔 행수에 비례하므로 **loose index scan(skip scan)**을 한다: 첫 값을 시크하고 "마지막보다 큰 다음 값"을 반복 시크 → 비용이 **반환 값 1개당 인덱스 시크 1회**.<br>🔴 **`STOP_DEADLINE`(~582)은 절단이 아니다** — 시간이 다한 것은 프리픽스 인덱스 부재가 취하는 모양이고, 살아남은 값들을 주면 "짧지만 완전한 목록"으로 읽힌다(INV-F3-6 금지). 그래서 **값 없이 `unavailable_reason`**을 준다. 반대로 `STOP_BUDGET`(~581)은 진짜 첫 N개라 값을 유지하고 `truncated: true`. 절단 증명은 `limit+1`을 요청해서 한다. ⚠️ **[`a5eb934` 기록] `timeout_ms`는 지연 상한이 아니다** — `_stop_reason`이 시계를 **프로브 발행 전에** 보므로 데드라인 1μs 전에 시작한 프로브는 세션 `statement_timeout`(같은 `timeout_ms`)까지 완주한다. 실제 최악은 **`2 × timeout_ms`**이고 실측 1,901ms/선언 1,500ms(1.27배). 고치지 **않은** 이유가 docstring에 있다: 프로브마다 남은 예산으로 `statement_timeout`을 다시 세우면 핫패스에 왕복이 프로브당 1회(20값 답변이면 21회) 붙는다 — 이미 degrade된 상태에서만 나는 최악을 줄이려고 건강한 요청 전부에 세금을 매기는 것이다. 대신 **`elapsed_ms`를 모든 응답에 실어** 호출자가 이 수를 믿지 않아도 되게 했다.<br>🆕 **`a5eb934`가 더한 것 넷.** ① **`text_seek_query(col, folded, is_pg, cursor=None)`(~610) — 시크 문장의 단일 정의.** public으로 뽑아낸 이유가 하나뿐이다: **쿼리를 스스로 재조립하는 플랜 검사는 아무도 실행하지 않는 쿼리를 검사한다.** `COLLATE "C"` 사건이 그 비용이었다 — 인덱스가 존재하고 플래너가 그것을 고르고도 비용이 테이블 크기에 선형일 수 있으며, 증거는 **이 문장의** 플랜뿐이다. ② **`classify_seek_plan(plan_text, expect_range=True, max_discarded=100)`(~1055) — 플랜 모양의 판정자.** 순수 텍스트 in / `(verdict, reasons, discarded)` out이라 실패 플랜이 **1.7M행 없이 재현되는 회귀 픽스처**가 된다. 판정 근거 두 축: `Index Cond`에 범위 비교(`>=`/`<`)가 있는가 · `Rows Removed by Filter`가 `_MAX_DISCARDED`를 넘는가. ⚠️ **`Filter` 줄의 존재 자체는 아무것도 증명하지 않는다**(건강한 플랜에도 `base <> ''`가 있고 0행을 버린다) — 가르는 것은 **버린 행 수**와 **`Index Cond`에 프리픽스 경계가 없는 것**이고, 그 둘은 노드 타입 검사로는 보이지 않는다. ③ **`_index_advice(db, table, column, settings)`(~896)가 `_diagnose`에서 분리**됐다 — 같은 조언을 **느리지만 성공한** 경로도 쓸 수 있게. 종전엔 모든 문장이 "조회 시간 초과"로 시작해 도착한 답변은 거짓말을 하거나 침묵해야 했고, 침묵했다. ④ **`_slow_reason`(~842)** — 성공한 답이 이미 느릴 때만 도는 카탈로그 조회라 **빠른 경로의 요청당 비용은 정확히 0**이고, 경고는 `_slow_warned` 집합으로 **(table, column)당 프로세스 1회**다(17자 입력 = 17요청이므로 요청당 경고는 실행 가능한 문장을 자기 사본 16개 밑에 묻는다).<br>**소비 배선**: `classify_seek_plan`+`text_seek_query`는 빌더 `server/scripts/setup_db_performance.py`의 **`_verify_plan_shapes(conn, targets)`(~10)** = **Step 3.9 "Verifying suggestion index PLAN SHAPE"**(~370)가 함께 쓴다 — 대상은 **TEXT 타깃만**(`number`는 평범한 btree라 collation 함정이 성립하지 않는다), 프리픽스는 `'a'` 한 글자(빈 프리픽스는 검증할 범위가 없어 `expect_range=False`가 존재하는 이유), 컬럼 객체는 `models.DYNAMIC_TABLES`가 아니라 **`Base.metadata.tables`**에서 뽑는다(정적 모델까지 덮어야 `graph_nodes.identity_key`가 검사된다 — 그것이 실제 구멍이었다). **스킵은 세지 않고 항목별로 나열**한다("33/33 range-shaped" 옆의 맨 "15 skipped"는 완전한 커버리지로 읽힌다). 검사 0건은 **FAILED로 취급하라고 명시**한다.<br>**거부**: `datetime` 선언 컬럼은 **400**(답하려면 datetime 캐노니컬화를 발명해야 하고 그것이 INV-F3-4가 금지하는 두 번째 정규화다 — `map_overlay.canonical_key_value`가 유일 정규화기). 미선언 테이블 404 · `column_types` 밖 400 · 모델 미등록 404 · 선언됐으나 물리 부재 400. **`table_config`가 권위이고 물리 스키마가 아니다**(INV-F3-3), 호출자 문자열은 SQL 텍스트에 절대 닿지 않는다. `_index_state`는 **INVALID 인덱스**(취소된 `CREATE INDEX CONCURRENTLY`)를 부재와 따로 지목한다 — `to_regclass`는 잘 풀리는데 플래너는 영원히 안 쓰고 빌더의 `IF NOT EXISTS`가 계속 건너뛴다. **서버 소비 3곳**(구 지도의 2곳은 낡았다): `GET /tables/{t}/columns/{c}/values`([§1.2](#12-api-라우트-표--데이터-조회편집)) · **`/graph/nodes/search`의 술어**([§1.5](#15-그래프-조회-구간-read-only--graph_nodesedges-직접-조회-워커-미경유)) · **빌더 Step 3.9**. 이음매의 **클라 절반**은 같은 이름의 **`client2/src/value_suggest.js`**다([§7](#7-client2src--웹-클라이언트)) — 두 반쪽이 서로에게서 찾아지도록 일부러 같은 이름이다 |
| **`server/map_preset_routing.py`** | 536 | **[F5c `(table, map_key)` → 기본 물리 규격]** **`resolve_preset_routing(db, cfg, table, map_key, presets=None)`(~454)**·**`resolve_routing_config(cfg, table)`(~213)**·`resolve_preset(presets, ref)`(~261)·**`_lookup_product_code(db, lookup, lot_raw)`(~353)**·**`_resolve_answer(table, map_key, canonical_key, presets, preset_ref, matched_by, lookup)`(~310)**·`_normalize_lookup`(~130)/`_normalize_rules`(~157)·`_rule_matches`(~409)·`_lot_token(binding, routing, map_key)`(~430)·`_note_lookup_scan`(~336). status 6종 `STATUS_OK`~`STATUS_PRESET_MISSING`(~89–94), lookup 결과 8종(~101–108), `MATCH_KINDS`(~110)·`MAX_RULES=200`(~112)·`MAX_PATTERN_LEN=200`(~113).<br>**해석 순서가 계약이다**: 맵 키를 `map_overlay.map_key_parts`(셀 필터·정체성 문자열이 이미 공유하는 분해 규칙)로 쪼개 **lot 토큰**을 얻고 → ① **제품코드 조회**(선언된 테이블/`key_column`에서 코드를 얻어 `product_presets[code]`) → ② **순서 있는 텍스트 패턴 규칙**(첫 매치 승, **대소문자 구분**) → ③ 없으면 종전 동작. **`resolve_routing_config`이 4가지 부재(블록 없음·테이블 엔트리 없음·`enabled:false`·정규화 결과 무용)를 단일 `None`으로 접는 것이 의도**다 — 네 모양이 리졸버로 새지 않게.<br>🔴 **조회 테이블은 프로덕션에만 있고 불완전하다.** 그래서 ① 부재는 그냥 스킵이고 **환경 분기가 의도적으로 없다**(프로덕션에서만 도는 팔은 검증 불가) ② **miss는 에러가 아니다** — debug 위로 로그하지 않고 결과는 `lookup.status`로 나른다. 쿼리 실패(`LOOKUP_ERROR`)만 경고한다. `_note_lookup_scan`이 프로세스당 `(table,column)`당 1회 "동적 테이블은 `business_key_val`/`updated_at`만 인덱싱하므로 이 등가 필터는 순차 스캔"이라고 알린다.<br>🔴 **매달린 프리셋 참조는 다음 규칙으로 흐르지 않는다** — `STATUS_PRESET_MISSING`으로 유령 이름을 대며 멈춘다(흘려보내면 아무 규칙도 고르지 않은 프리셋으로 답하고 오타가 영원히 안 보인다). `business_key_val`을 인덱스 미러로 대체하지 **않은** 이유도 명시돼 있다: 그것은 `str(v).strip()`이라 `canonical_key_value`와 **다른 정규화**이고, 둘의 불일치가 miss를 제조하는데 이 설계는 그 miss를 의도적으로 안 보이게 만든다. 테스트 `server/tests/test_map_preset_routing.py`(591줄) |
| **`server/utils/time_format.py`** | 38 | **[표준 라이브러리만 import하는 타임스탬프 포맷터]** `LOCAL_TIMEZONE`(~26, `astimezone()`의 호출당 시스템 조회를 피하려 캐시)·`to_local_str(dt)`(~29 — falsy면 `""`, naive는 UTC로 간주, `"%Y-%m-%d %H:%M:%S"`).<br>🔴 **왜 별 파일이 됐는가**: `chain_ingestion_worker`가 통지 블록 **안에서** `from main import to_local_str`를 했고 그 블록은 `except Exception: logger.error("Failed to build chained update notification")`으로 감싸여 있었다. `main` import는 웹앱 모듈 전체를 실행하며 **#13 fail-fast가 손상된 `table_config.json`에 `TableConfigError`를 raise**한다. 결과: 체인 배치는 **행을 커밋했고**, import가 raise했고, 예외는 삼켜졌고, WS 통지는 나가지 않았다 — **행은 존재하는데 아무 클라이언트도 모르고 로그 한 줄은 엉뚱한 원인을 지목**했다. 규칙: **"통지 경로가 거부할 권리를 가진 애플리케이션 모듈의 import에 의존해서는 안 된다."** import처: `chain_ingestion_worker`(모듈 최상단) · `main`(재export해 `main.to_local_str` 기존 호출자 보존) · `tests/test_config_reload_integrity.py`(워커가 더는 `main`을 경유하지 않음을 단언). ⚠️ **`graph_sync_worker`는 여전히 자체 `to_local_str`(~455)을 갖고 있고 tz 처리가 없다**(맨 `strftime` — naive UTC를 로컬로 보고한다). 통합은 미착지 |

---

## 5-B. `server/config_resolve_report.py` — 「내 config가 먹었는가」의 답 (`f3fd785` 신설)

**833줄**(`ed9cfdb` 556에서 **+277**, 그중 **`68db020`이 +165**). import는 `json`·`logging`·`os` **셋뿐**이고 나머지(`enrichment_config`·`enrichment_candidates`·**`virtual_join_config`**·**`notation_norm`**·**`map_overlay`**·`database.crud`)는 **전부 함수 안 지연 import**다 — 이 모듈을 import하는 것만으로는 아무 애플리케이션 모듈도 끌려오지 않는다.

> 📐 **앵커는 `_resolve_virtual_join`(**445**)까지 전부 무이동이고, 그 뒤에 세 번째·네 번째 도메인이 통째로 붙었다.** `DOMAIN_NOTATION`~`_resolve_notation`(**531–692**), 이어서 🆕🆕🆕 **`DOMAIN_BINDING`(**695**)~`_resolve_binding`(**706–801**, `68db020` 신설)**, 그 아래 `_RESOLVERS`(**803**)·`resolve_report`(**811**)만 밀렸다.
>
> 🔴 **도메인이 3개에서 4개가 됐다** — `enrichment` · `virtual_join` · `notation` · 🆕🆕🆕 **`binding`**(`_RESOLVERS`에 **마지막으로** 등록 — `contracts/config_resolve_report`의 하네스가 `domains[0]`을 enrichment로 고정 인용하므로 새 도메인은 뒤에 붙는다).
>
> 🆕🆕🆕 **`_resolve_binding() -> dict`(`68db020` 신설)** — **DB를 건드리지 않는다.** `crud.TABLE_CONFIG`와 `map_overlay_config.table_bindings`에 등장하는 테이블을 합집합으로 훑어 테이블마다 `map_overlay.resolve_binding_parts(cfg, table)`를 부르고, `BINDING_KEYS`(`x`/`y`/`val`/`index`/`key_columns`) 각각을 **키 단위 문장**으로 보고한다: `origin==ORIGIN_REFUSED`면 `rejected`(사유는 **"고치지 말고 지우십시오"** — 선언이 유도를 이기므로 편집으로는 못 살아난다) · `ORIGIN_DECLARED`/`ORIGIN_INHERITED`면 `effective` · `ORIGIN_ABSENT`면 `ineffective`(`reason=REASON_NOT_DECLARED`). 바인딩 자체가 None이고 거절도 없으면(선언도 없고 맵도 아닌 테이블) **그 테이블은 통째로 스킵**된다 — 「맵이 아니다」가 95줄의 소음이 되어 진짜 거절을 덮지 않도록. `_BINDING_KEY_MEANING`(dict)이 키 5종의 한국어 뜻을 붙인다.
>
> 🆕 🔴 **[2026-08-14 · R-2026-08-14-A F3] `ORIGIN_DECLARED` 갈래가 둘로 갈렸다 — 선언이 «유도를 이겼는가» 아니면 «유도와 같은 말을 했는가».** 종전 문장은 *"table_config가 같은 답을 낸다면 이 선언은 지워도 됩니다"*라는 **가정법**이었고, 그 조건이 참인지는 화면에서 확인할 방법이 없었다 — `key_columns` 사본이 갈라질 때까지 살아남은 기전이 그것이다. 이제 테이블마다 `map_overlay.derive_binding_parts(table, candidates)`를 함께 불러 **유도가 무엇이라 했을지**를 얻고, `fields`에 `derived_would_be`·`restates_derivation`을 싣는다. 같으면 문장이 **「지우십시오」로 확정**되고, 다르면 오버라이드로 보고한다. 오버라이드가 `key_columns`인데 그 테이블 블록에 **`__reason`이 없으면** `fields.reason_declared=False`와 함께 문장에 경고가 붙는다(있으면 `fields.override_reason`에 원문 — 봉투의 `reason`은 닫힌 어휘라 **이름을 공유하지 않는다**). 🔴 **모집단은 안 바꿨다**: 사본도 오버라이드도 값을 내므로 `effective`에 남는다 — `ineffective`로 옮기려면 `REASONS`에 새 낱말이 필요하고 그것은 경계 계약이다.

**왜 있는가 (사용자 2026-07-30)**: 어드민의 config 라우트는 `POST /admin/reload-configs` 하나뿐이고, **캐시를 갱신하고 워커에 이벤트를 뿌린 뒤 무엇이 먹었는지 아무것도 반환하지 않는다.** 서버가 읽는 config는 10개인데 **쓰기 전용 버튼 하나가 전부**였다. 그 공백은 이미 실제 결함을 숨기고 있었다 — `auto_confirm: true`를 `candidate_for` 선언 없이 켜면 컬렉터는 경고 한 줄을 남기고 조용히 비활성이 되는데, **2026-07-30 라이브가 정확히 그 상태였다**(어떤 뷰도 `candidate_for`를 선언하지 않았다). 노브는 켜진 것처럼 읽히고 아무 일도 하지 않으며, 목격자는 아무도 안 보는 데몬 로그뿐이었다.

> 🔴 **세 모집단이 이 모듈의 전부다 (총괄 확정 경계 계약)** — `effective`(효과 있음) · `ineffective`(선언은 있는데 효과 없음, **반드시 명명된 사유 동반**) · `rejected`(파싱/검증 실패로 아예 미반영, 사유 동반).
>
> 🔴 **어휘를 새로 만들지 않았다.** 런타임 열화 어휘(`main.CHIP_TRACE_*`, [§1.5-bis](#15-bis-get-graphchip-trace--칩-1개의-이력-웨이퍼-범위로-한정-aea47008670e3b530fdfd))를 **그대로 재사용**한다 — 같은 구분이 config 로드 시점으로 한 층 올라온 것뿐이라 어휘가 갈라질 이유가 없다.
>
> 🔴 **사람이 읽을 문장은 전부 서버가 만든다.** 클라이언트는 `detail`을 **그대로 렌더**하고 「효과 없음」을 자기 규칙으로 판정하지 않는다. 클라가 사유를 유도하기 시작하면 [U6](#0-묘비-목록--소스에-존재하지-않는-이름)에서 6종을 삭제한 하드코딩 사본 계급이 그대로 재발한다. 계약이 이것을 **능동 단언**한다 — `contracts/config_resolve_report/client_harness.mjs`가 `client2/src` 전역에서 4개 사유 단어를 **소스 리터럴로** 찾아 하나라도 있으면 divergence다([§6-2](#6-2-교차-구현-계약-contracts)).

| 시그니처 / 상수 | 역할 | 라인 |
|---|---|---|
| 🆕 **`_names(seq, sep=", ") -> str`** / 🆕 **`_as_json(value) -> str`** | **[`f9289f6` 신설] 운영자 문장 조립의 두 헬퍼 — 이 모듈에서 「가독성은 기능이다」가 코드가 되는 자리.** `detail`은 클라이언트가 **그대로 렌더**하는 문장이므로(모듈 상단 계약) 그 안에 Python repr이 들어가면 **고칠 하류가 없다.** 🔴 초판이 실제로 출하한 것: `이 뷰는 ['lot'](으)로만 조회하므로 판단키 ['slot']을(를)…`(리스트 repr)과 `**아무 효과가 없습니다.**`(생 별표). `_names`는 대괄호·따옴표를 없애고, `_as_json`은 **운영자가 편집한 그 파일의 문법(JSON)**으로 값을 되돌린다 — `!r`을 쓰면 `"true"`가 `'true'`로 적혀 운영자가 자기 파일을 못 알아본다. 소비: `_view_report`의 범위 문장(**~206–207**) · `_resolve_enrichment`의 비-boolean 노브·캡 문장(**~310·316·335**) · `_rule_fields` 소비부의 후보 필드 문장(**~359·364**). 계약이 이것을 **INV-F9-8로 능동 단언**한다([§6-2](#6-2-교차-구현-계약-contracts)) | **~56 / ~67** |
| **`REASON_NOT_DECLARED` · `REASON_MAPPING_UNAVAILABLE` · `REASON_SCOPE_UNRESOLVED` · `REASON_NOT_REACHED`** / **`REASONS`** | **닫힌 어휘 4종이 정본이다.** 뜻은 런타임과 같은 축의 한 층 위 — 효과에 필요한 선언이 없음 / 선언이 파싱·검증에 실패 / 선언의 범위가 판단키를 고정하지 못함 / **상위 스위치가 꺼져 이 선언까지 도달하지 않음**. `contracts/config_resolve_report/vectors.json`이 pytest·node 양쪽을 같은 기댓값에 채점한다 | ~80–83 / **~84** |
| `POPULATIONS` / `SCOPES`(`file`·`setting`·`rule`·`reference_view`) / `ORIGIN_FILE`·`ORIGIN_DEFAULT` | 모집단 3종 / 항목의 주체 4종 / 값의 출처 2종 | ~87 / **~93** / ~95–96 |
| **`entry(scope, subject, detail, reason=None, warnings=None, fields=None) -> dict`** | **모집단 항목 1건 — `detail`이 클라가 그대로 렌더할 문장이다.** 🔴 **어휘 밖 단어는 `ValueError`로 즉사한다**(`reason`·`warnings`·`scope` 전부 검증). 조용히 통과시키면 클라가 못 읽는 사유가 흘러가고, 닫힌 어휘는 그 순간 열린 어휘가 된다 | **~99** |
| `source(key, path, detail, exists=None, degraded=False)` | 설정 파일 1개의 상태. 🔴 **부재는 거부가 아니다**(`exists: false`) — `/graph/mapping-summary`와 **같은 규율**이고, 둘을 뭉개면 건강한 시스템에서 rejection 목록이 비지 않게 되어 목록 자체가 무시당한다 | **~120** |
| **`setting(key, value, origin, path, declared=None, detail="")`** | **모집단이 답하지 못하는 질문의 자리.** 모집단은 **선언**에 대한 이야기이고 "그래서 서버가 지금 쓰는 값이 뭔데"는 다른 질문이다 — 선언이 아예 없을 때(파일 부재 → 전부 기본값)에도 답이 있어야 한다. 그래서 각 항목이 **값(`value`)과 그 값이 온 자리(`origin`/`path`/`declared`)를 함께** 말한다 | **~133** |
| `build_domain(domain, title, sources, settings, effective, ineffective, rejected)` | 도메인 봉투. `counts`는 **세 목록의 길이에서 계산**된다(INV-F9-5: 목록과 어긋나는 카운트로 만든 배지는 가장 값싼 거짓말이다) | **~146** |
| **`_view_report(rule, view) -> dict`** | **참조뷰 1건 — 함정을 「켜기 전에」 보이게 하는 자리.** `required_binds ⊊ decision_key`면 `scope_narrow`를 세운다. 실증된 함정: `core_wafer_attribution`의 뷰가 **lot 하나로만** 조회하는데 판단키는 (lot, slot)이라, 결과가 `ambiguous`가 아니라 **`single`**로 나오고 그 하나의 `wafer_id`가 23개 슬롯 전부에 쓰인다. 🔴 **선언 여부와 무관하게 문장으로 말하되 `warnings`(규칙 수준으로 올라가는 신호)에는 선언된 뷰만 넣는다** — 아무 일도 하지 않는 표시 전용 뷰가 규칙에 경고를 달면 그 경고는 곧 무시당하고, 진짜 위험할 때 아무도 안 본다 | **~171** |
| `_rule_fields(rule, views, knob_on, raw_knob, max_keys)` | 규칙별 사실 묶음. **`candidate_fields`**(`{target_field: [뷰 라벨…]}`)가 핵심이다 — `enrichment_candidates.declaring_views`로 만들고 **비어 있으면 노브는 무력**이다 | **~221** |
| **`_resolve_enrichment() -> dict`** | **첫 도메인 등록기. 🔴 DB를 건드리지 않는다 — config만 읽는다.** `/enrichment/rules`와 **같은 인자로** 로드한다(`known_tables=crud.TABLE_CONFIG`, `rejections=[]`) — 보고서와 라우트가 다른 답을 내면 보고서가 답하려던 질문 자체가 무의미해진다. 판정 순서가 곧 어휘다: 로더 거부 → `mapping_unavailable` · 노브 비-boolean → `mapping_unavailable`(**무시가 아니라 거부로 보고**) · 노브 없음/false → `not_declared` · 전역 스위치 off → **`not_reached`** · `candidate_for` 0건 → `not_declared` · 그 외 → `effective`. 드라이런 숫자(「몇 건이 사람 없이 확정 가능한가」)는 **여기 없다** — 큐를 걷는 분석 질의라 `GET /admin/enrichment/auto-confirm/dry-run`이 따로 답한다 | **~242** |
| 🆕 **`DOMAIN_VIRTUAL_JOIN`** / **`_VJ_CODE_TO_REASON`** / **`_VJ_CODE_LEAD`** | **[`4e06eec`+`b6942ec`] 두 번째 도메인.** 🔴 **새 사유 단어를 만들지 않았다** — 로더의 내부 코드 3종을 기존 닫힌 어휘로 사상한다: `no_unique_index` → **`scope_unresolved`**(런타임 어휘에서 그 단어의 뜻이 「0개 또는 2개 이상이 주장 ― 고르지 않음」이고, 조인 키가 오른쪽 행 하나를 지목한다는 보장이 없는 상태가 정확히 그것이다) · `fanout_declared`/`shape` → **`mapping_unavailable`**. **어휘 추가는 계약 변경이다.** `_VJ_CODE_LEAD`는 코드별 한국어 앞머리로, 로더의 영문 사유를 그대로 붙이는 대신 **운영자가 무엇을 고쳐야 하는지 먼저 말한다** | **~396** / **~405** / **~413** |
| 🆕 **`virtual_join_detail(code, facts=None, loader_detail="") -> str`** | **거부 1건의 운영자가 읽는 최종 문장 — 서버가 짓는다.** 🔴 **보고서와 `GET /admin/config/virtual-join/verify`가 같은 함수를 쓴다**([§1.4](#14-api-라우트-표--어드민운영그래프맵인리치먼트)). 갈라 두면 같은 거부가 두 화면에서 다른 문장으로 나오고, 그 순간 「서버가 문장의 정본」이라는 계약이 깨진다. ⚠️ **`no_unique_index`는 세션이 있어야 나오는 코드라 보고서 경로에서는 발화하지 않는다** — 그래서 이 함수가 **라우트에서도 불려야** 그 분기가 살아 있다.<br>**유일성 거부만 온전한 한국어 문장을 짓는다**(**~436–441**): 필요한 UNIQUE 인덱스가 없다는 사실 + `required_index_ddl` 실행 문구 + **"만드는 중 중복 오류가 나면 그 값이 실제로 둘 이상 있다는 뜻"**. 사실이 없는 거부만 영어 `loader_detail`을 이어 붙인다(INV-F9-8: `detail`이 반쯤 영어가 되면 안 된다) | **~423** |
| 🆕 **`_resolve_virtual_join() -> dict`** | 두 번째 도메인 등록기. 🔴 **DB를 건드리지 않는다** — 그래서 이 보고서가 답하는 것은 **모양이 유효한가**까지이고, 승인(=조인 키를 덮는 UNIQUE 인덱스의 존재)은 `pg_index`가 아는 사실이라 세션이 필요해 **라우트가 따로 답한다.** 이 라우트의 「DB 질의 0건」은 테스트로 고정돼 있다(`test_the_report_issues_no_database_queries`) | **~445** |
| **`DOMAIN_NOTATION`** / **`_NOTATION_CODE_TO_REASON`** / **`_NOTATION_CODE_LEAD`** | **세 번째 도메인.** 🔴 **여기서도 새 사유 단어를 만들지 않았다** — `notation_norm`의 내부 코드를 기존 닫힌 어휘로 사상한다: `zero_pad_unimplemented` → **`not_reached`**(선언은 읽혔는데 그 규칙까지 실행이 도달하지 않는다) · `unknown_rule`/`would_rewrite_raw`/`key_column`/`shape` → **`mapping_unavailable`** · `undeclared` → **`not_declared`**. `_NOTATION_CODE_LEAD`는 코드별 한국어 앞머리(`_VJ_CODE_LEAD`와 같은 자세) | **531** / **533** / **549** |
| **`_resolve_notation() -> dict`** | 세 번째 도메인 등록기. 🔴 **DB를 건드리지 않는다** — config만 읽는다. 앞의 둘과 **다른 점 하나**: 유효한 표기 정규화 선언은 곧 `effective`다(파생이 쓰기 경로에서 실제로 돌아 값을 남긴다). 그러나 **Phase 1이라 아직 아무도 그 값을 읽지 않는다**는 사실을 **선언마다 문장으로 달아** 보고한다 — 🔴 **「먹었다」와 「쓰이고 있다」는 다른 질문이고, 둘을 붙여 두지 않으면 다음 사람이 맵 키가 이미 정규화된 값으로 조회된다고 읽는다.** `zero_pad: true`가 조용히 무시되는 노브가 아니라 **이름 붙은 거절**로 화면에 뜨는 것도 이 등록기 때문이다 | **602** |
| 🆕🆕🆕 **`DOMAIN_BINDING`** / **`_BINDING_KEY_MEANING`** | **[`68db020` 신설] 네 번째 도메인.** `BINDING_KEYS` 5종의 한국어 뜻 사전(`x`=가로 좌표 · `y`=세로 좌표 · `val`=셀 값 · `index`=순번(유도되지 않는다) · `key_columns`=맵 정체성) | **695** / **697** |
| 🆕🆕🆕 **`_resolve_binding() -> dict`** | 네 번째 도메인 등록기. **DB를 건드리지 않는다.** `crud.TABLE_CONFIG ∪ table_bindings 선언 테이블`을 훑어 테이블마다 `map_overlay.resolve_binding_parts(cfg, table)`를 부르고 `BINDING_KEYS` 각 키를 출처별로 문장화한다: `ORIGIN_REFUSED`→`rejected`("고치지 말고 지우십시오") · `ORIGIN_DECLARED`/`ORIGIN_INHERITED`→`effective` · `ORIGIN_ABSENT`→`ineffective`(`REASON_NOT_DECLARED`). 맵도 아니고 선언도 없는 테이블은 스킵(95줄의 소음 방지). 🆕 **[2026-08-14] `derive_binding_parts`를 함께 불러 «유도가 무엇이라 했을지»를 얻고**(`fields.derived_would_be`) 선언이 그것을 **되풀이한 사본인지**(`fields.restates_derivation` → 「지우십시오」 확정) 진짜 **오버라이드인지**를 가른다. `key_columns` 오버라이드에 블록 `__reason`이 없으면 `fields.reason_declared=False`와 경고 문장 | **706** |
| `_RESOLVERS` / **`resolve_report(domains=None) -> dict`** | 도메인 등록기 dict — **현재 4개**(`enrichment` · `virtual_join` · `notation` · 🆕🆕🆕 **`binding`**, 나머지 config는 여기에 한 줄씩 붙는다) / 진입점. 🔴 **한 도메인의 실패가 나머지를 삼키지 않는다** — 예외는 잡아 그 도메인만 `rejected` 1건(`mapping_unavailable`)으로 강등한다. 응답에 **`vocabulary`를 함께 싣는 것이 계약**이다: 클라가 라벨·필터를 하드코딩하지 않게 | **803** / **811** |

> ⚠️ **소스 주석의 앵커 1건이 HEAD에서 여전히 어긋난다(2회 연속 실측).** 모듈 docstring **~10**이 그 경고를 `enrichment_candidates:456`으로 지목하는데, HEAD의 456행은 `resolve_target_candidate` 본문이고 **실제 그 `_warn_once` 호출은 `enrichment_candidates:522`**다(`AutoConfirmCollector.__init__` 안). `f9289f6`이 그 파일을 +22 밀었으므로 **격차는 오히려 벌어졌다.** 코드·주석 수정은 서버 도메인 소관이라 여기서 고치지 않았다.

---

## 5-C. 2026-07-31 신설 서버 모듈 2종

**한 라운드에 서버 파일 2개가 들어왔다(합 690줄).** 계보가 서로 무관하다 — **테스트 프로세스의 DB 격리**(#16a) 하나와 **가상 조인 선언 검증** 하나.

### `server/db_safety.py` (🆕⑤ **453줄** @`831ab68` — `e1ba99e` 신설 215줄에서 **+238**) — 「이 프로세스는 만지면 안 되는 것에 닿지 못한다」 가드 **둘**

🔴 **왜 프로덕션 코드이고 fixture가 아닌가 — 이것이 이 파일의 존재 이유 전부다.** `server/tests/conftest.py`가 앱 import 전에 `DATABASE_URL`을 격리 DB로 고정하고 있었고, **그 핀이 구 누출을 무해하게 만들고 있었다.** 그런데 핀은 **테스트 트리가 하는 일**이라 지우면 보호까지 함께 지워진다. 그래서 가드를 **검사 대상 모듈 안**에 둔다 — 이제 핀을 지워도 무장 해제되지 않고 스위트가 시끄럽게 실패한다.

**인시던트**: `Base.metadata.create_all`이 **모듈 import 시점**에 돌던 시절, 앱을 import하기만 해도(=pytest가 스위트를 수집하기만 해도) 해석된 `DATABASE_URL`에 DDL이 나갔다. 미설정 시 그 기본값이 **프로덕션 PostgreSQL**이고, **실제로 일어났다** — 테스트를 돌린 것만으로 프로덕션에 빈 테이블이 생겼다.

🔴 **규칙은 blocklist가 아니라 allowlist다.** *"`assy_manager`만 빼고 다"*는 두 번째 프로덕션 DB가 생기는 날, 혹은 누가 이 DB를 개명하는 날 **fail-open** 한다. 그래서 `check_test_database`는 **허용되는 것을 이름으로 댄다** — sqlite, 또는 운영자가 `ASSY_TEST_DATABASE_URL`에 선언한 **정확히 그 URL** — 나머지는 무해해 보여도 전부 거부한다. **격리를 증명하지 못하는 것 자체가 거부**다(`server/scripts/dev_env/iso_watcher.py`와 같은 자세·같은 사유).

| 시그니처 / 상수 | 역할 | 라인 |
|---|---|---|
| **`TEST_DATABASE_URL_ENV = "ASSY_TEST_DATABASE_URL"`** | `conftest.py`가 읽는 env 이름. **테스트 프로세스 안에서 non-sqlite 타깃이 합법이 되는 유일한 길**이 이 선언이다.<br>🆕 ⚠️ **[2026-08-12] 그 선언을 세우는 문이 하나 더 생겼고, 이 파일을 읽는 사람은 그것을 알아야 한다.** `server/tests/conftest.py`의 `pg_engine`/`pg_session` 픽스처는 운영자가 **`ASSY_PG_TEST_DATABASE_URL`**에 선언한 URL을 이 이름 아래에 **픽스처가 도는 동안만** 세운다(setup·테스트 본문·teardown, 그 밖에서는 원복). **가드를 끄지 않는다** — 같은 `check_test_database`를 `production_url`과 함께 먼저 통과해야 하므로 **운영 DB를 적으면 여전히 거절**이고, 넓어지는 것은 운영자가 지목한 그 한 DB뿐이다. 창이 좁아야 하는 이유는 `test_dev_env_isolation.py`가 **자기 실행 시점의** 이 변수와 엔진 URL을 대조하기 때문이다 | **~57** |
| **`REFUSAL_MARKER = "[#16a] REFUSED"`** | 모든 거부 문구에 들어간다 — 테스트가 **예외 타입이 아니라 사유를 핀**할 수 있게. 🔴 없으면 도달 불가 호스트의 `OperationalError`가 맨 `pytest.raises`를 만족시켜 **가드가 죽어도 테스트가 초록**이다 | **~62** |
| **`under_pytest()`** | 이 프로세스(또는 테스트가 띄운 자식 프로세스)가 테스트 프로세스인가. **신호 셋**이고 환경변수 둘이 목록에 있는 것이 의도다 — 그것들은 **자식에게 상속**되므로 테스트가 shell out한 프로브도 여전히 테스트 프로세스이고 여전히 거부된다 | **~65** |
| `_parts(url)` | 자격증명을 뺀 `(backend, host, port, database)` \| None | **~79** |
| **`check_test_database(url, *, production_url=None, opt_in=None) -> list`** | **위반 목록. `[]`이면 허용.** allowlist 판정의 단일 지점 | **~100** |
| **`require_test_database(url, *, context, production_url=None, opt_in=None)`** | **그물 3 — 순수 결정.** 커넥션을 하나도 열지 않고 raise한다. **#16a에 직접 답하는 것이 이것**이고, 소비처가 `main.bootstrap_database_schema`다([§1.1](#11-기동미들웨어공용-헬퍼)). pytest 밖에서는 no-op | **~144** |
| **`install_test_database_guard(engine, *, production_url=None)`** | **그물 1 — `do_connect` 훅.** 프로덕션 자격증명을 실은 **그 하나의 엔진**에 건다. **소켓이 열리기 전에** 거부하므로 테스트 프로세스는 진짜 DB에 접촉조차 하지 않는다. 설치 지점: `server/database/database.py`의 엔진 생성 **직후** | **~167** |
| **`install_global_test_database_guard(*, production_url=None)`** (+`_GLOBAL_GUARD_INSTALLED` **~187**) | **그물 2 — Engine **클래스**의 `engine_connect` 훅.** 테스트가 **스스로 만든** 엔진까지 덮는다. 문장이 실행되기 전에 발화하지만 그 시점엔 소켓이 이미 열려 있을 수 있다 — 그것을 막는 것이 그물 1이다. 설치 지점: `database.py` **모듈 상단**, 이 프로세스에 엔진이 존재하기 **전** | **~190** |

⚠️ **이 파일이 일부러 하지 **않는** 것**: pytest 밖에서 위 진입점은 전부 **아무것도 보지 않고 즉시 반환**한다. 특히 `bootstrap_database_schema`의 `create_all`은 **무가드 그대로** 남는다 — DB가 불통인 프로덕션 웹서버는 스키마 없는 앱을 서빙하는 대신 **부팅에서 시끄럽게 죽어야** 한다. 여기 있는 어떤 것도 그 문장을 `try/except`로 감싸거나 실패를 부드럽게 만들지 않는다. **가드는 그 앞에서 거부하고, 오직 테스트 프로세스 안에서만 그렇게 한다.**

**회귀 테스트**: `server/tests/test_ddl_never_reaches_production.py`(417줄) · `server/tests/test_dev_env_isolation.py`(수정).

#### 🆕⑤ 같은 파일의 **두 번째 가드** — 「이 운영자 패스는 쓰지 못한다」 (`1260c9b`)

🔴 **왜 별도 모듈이 아니라 여기인가 — 소스가 직접 답한다.** 같은 계급의 속성(독자가 믿어야 하는 문장이 아니라 서버가 강제하는 거절)을 다른 질문에 겨눈 것이고, 이 파일은 이미 「무엇이 이 프로세스가 만지면 안 되는 것을 막는가」를 찾아오는 자리다. 그리고 **대안은 이미 시도됐다**: 그 속성이 **운영자 스크립트 7개에 걸쳐 세 가지 철자**로 살아 있었고 **그중 하나가 틀렸다** — 그리고 그것은 안전 속성이 퍼진 것과 **같은 기전**(복사)으로 퍼졌다.

🔴 **틀렸던 철자, 가정이 아니라 실측(격리 `assy_qa` / PostgreSQL 18.3 / SQLAlchemy 2.0.49 / psycopg2 2.9.11, 2026-08-13).** `conn.execute(text("SET SESSION default_transaction_read_only = on"))` — `engine.connect()`가 주는 **평범한** 격리 수준의 커넥션에서:

| 읽은 것 | 값 |
|---|---|
| `default_transaction_read_only` | **on** ← 확인하고 싶어지는 변수 |
| `transaction_read_only` | **off** ← PostgreSQL이 실제로 강제하는 변수 |
| CREATE / INSERT / UPDATE | **셋 다 통과** |

`SET` 자체가 암묵 트랜잭션을 **시작**해 버리므로 그 트랜잭션은 옛 기본값 아래 열려 그대로 유지되고, `rollback()`은 `SET`을 통째로 버린다. ⚠️ **이미 AUTOCOMMIT으로 전환된 커넥션에서는 같은 두 줄이 실제로 걸린다** — 그런데 그게 **더 나쁘다**: 속성이 **무관한 이유로 켜져 있던 설정 위에서 우연히** 성립했다는 뜻이고, 두 배치는 **플래그를 되읽지 않는 스크립트 안에서는 구별이 불가능하다.** 어느 스크립트도 되읽지 않았다.

| 시그니처 / 상수 | 역할 |
|---|---|
| **`READONLY_REFUSAL = "[read-only guard] REFUSED"`** | 모든 거부 문구에 들어간다 — 호출자가 **예외 타입이 아니라 사유를 핀**하도록(위 `REFUSAL_MARKER`와 같은 규율). 없으면 도달 불가 호스트의 `OperationalError`가 맨 `pytest.raises(RuntimeError)`를 만족시킨다 |
| **`CONNECT_TIME = "connect_time"` / `PER_TRANSACTION = "per_transaction"`** | 🔴 **작동하는 철자는 둘이고, 서로 대체 불가라 둘 다 노출한다.** **`CONNECT_TIME`** = `connect_args`의 `-c default_transaction_read_only=on` + **우리가 지은** `NullPool` 엔진 — 서버가 이 세션의 첫 트랜잭션이 존재하기 **전에** 적용하고 이후 모든 트랜잭션에 재적용한다. 가장 강하고 격리 수준과 무관하지만 **엔진을 지어야 하므로 URL을 가진 호출자만** 쓸 수 있다. **`PER_TRANSACTION`** = SQLAlchemy 자신의 `postgresql_readonly=True`(begin마다 트랜잭션 플래그). **빌려온 엔진**(앱 풀, `--url`로 남이 지은 것)에서 두 번째 엔진·두 번째 풀 없이 작동한다 — `scripts/audit_schema_canon.py`가 필요로 하는 것이 이것이다(진입점들이 `engine` 파라미터를 받고, 자기가 안 지은 것을 받아야 한다). 양쪽 다 실측: `transaction_read_only=on`, CREATE/INSERT/UPDATE 전부 `ReadOnlySqlTransaction`, 명시 `rollback()` **후에도**, 그다음 트랜잭션에서도 |
| **`READONLY_OPTIONS`** (`-c default_transaction_read_only=on -c client_encoding=utf8`) / **`readonly_options(statement_timeout_ms=None)`** | 기본 connect 옵션 문자열과, 타임아웃만 얹는 **빌더**(상수 7개가 아니라 함수인 이유: 호출자마다 정당하게 다른 부분이 타임아웃 하나뿐이다). ⚠️ **일부러 안 들어 있는 것**: `lock_timeout`·`idle_in_transaction_session_timeout` — 14 GB DB에서 `business_key_val`을 가진 전 테이블에 GROUP BY를 도는 패스에 타임아웃을 붙이면 **오늘 되는 프리플라이트가 실패하게 된다**(가드를 무장하는 것과 별개의 결정) |
| **`open_readonly_engine(url=None, *, application_name="assy_readonly_pass", statement_timeout_ms=None)`** | 모든 트랜잭션이 connect 시점부터 읽기 전용인 엔진. 🔴 **`NullPool`은 정리정돈이 아니라 하중을 진다** — 이 커넥션들은 다른 무엇에도 넘겨져선 안 되고, 우리 엔진에는 오염시킬 다음 체크아웃이 없다. 구 코드가 필요로 하던 `invalidate()` 춤을 은퇴시킨 것도 이것이다(구 패턴은 **애플리케이션 풀**에서 빌린 커넥션에 세션 변수를 걸었고, 같은 프로세스에서 check 다음에 돈 apply가 모든 CREATE를 `ReadOnlySqlTransaction`으로 실패시켰다). `application_name`은 운영자가 `pg_stat_activity`에서 읽는 값이라 호출자마다 정하는 것이 맞다. `url=None`이면 `database.database.SQLALCHEMY_DATABASE_URL` |
| **`readonly_state(conn) -> str`** | `SHOW transaction_read_only`의 값. **판정 없음** — 운영자에게 플래그를 **출력**하려는 스크립트가 이 문장을 두 번째로 철자하지 않게 한다. 리터럴이 정확히 한 파일에만 나타나는 것이 「되읽기가 옳은 변수를 보고 있나?」를 **답이 하나인 질문**으로 만든다 |
| **`assert_readonly(conn)`** | 🔴 **PostgreSQL **자신이** 「이 커넥션은 쓸 수 없다」고 말할 때까지 거절한다.** 답이 옵션 문자열을 넘겼다는 사실이나 어느 분기를 탔다는 사실이 아니라 **서버**에서 온다 — 자기를 검증하지 못하는 가드가 이 파일이 끝내려는 결함이기 때문. 🔴 **`default_transaction_read_only`는 일부러 보지 않는다 — 쓰기를 받아들이는 배치에서 `on`을 읽는 바로 그 거짓말이다.** 되읽기 자체가 실패해도(`Exception`) 거절한다 |
| **`assert_writable(conn)`** | 거울상, `--apply`용. **첫 문장 전에** 실패한다 — 풀에서 물려받은 읽기 전용 플래그가 개별 CREATE/DROP마다 `ReadOnlySqlTransaction`으로 터지며 **카탈로그를 이미 절반 바꾼 뒤** 드러났던 실제 사고의 직접적 그물 |
| **`open_readonly_connection(engine, *, mode=CONNECT_TIME)`** | 🔴 **읽기 전용 패스로 가는 유일한 문: 붙고, 그다음 증명하고, 아니면 거절.** `CONNECT_TIME`은 `open_readonly_engine`의 엔진을 기대하며 여기서 거는 AUTOCOMMIT은 **가드를 무장시키는 것이 아니다**(그것은 connect 옵션이고, 없이도 성립함이 확인됐다) — 큰 카탈로그를 세는 패스가 스냅샷 하나와 `idle in transaction` 슬롯 하나를 실행 내내 물고 있지 않게 하려는 것. `PER_TRANSACTION`은 빌린 엔진의 **이 커넥션만** 무장시키고 엔진은 건드리지 않으며, **일부러 AUTOCOMMIT이 아니다**(이 모드의 호출자는 예상된 문장별 오류에서 rollback으로 회복하고, 플래그는 그 뒤 트랜잭션에 재적용된다 — 실측). 모드 문자열이 틀리면 `ValueError`. 🔴 **모드를 잘못 고르는 것은 구멍이 아니라 거절이다** — 무장되지 않은 커넥션이 나오고 `assert_readonly`가 그것을 거절한다. 실패 시 `conn.close()` 후 재raise |
| **`close_readonly_connection(conn)`** | 균일한 teardown(어느 모드로 열었는지 기억하지 않아도 되도록). ⚠️ **`invalidate()`는 다층 방어이고 이 주석은 그 이상을 주장하지 않는다** — 「풀에 남은 세션 설정이 다음 체크아웃의 문제가 된다」는 **아무도 재지 않은 문장**이었다. 실측(SQLAlchemy 2.0.49 + `QueuePool`, 2026-08-13): `close()`만으로도 다음 체크아웃은 `transaction_read_only=off`를 읽고 쓰기를 받았다 — `postgresql_readonly` 갈래와 raw `SET SESSION` 갈래 **둘 다**. 유지하는 이유는 소켓 하나 버리는 값이고 그 버전별 리셋 동작이 계속 참이라는 데 기대지 않기 때문이지, 위험이 커서가 아니다 |

**소비처 — 전건 grep(`831ab68`), 7파일**: `server/migrations/add_business_key_unique_index.py` · `server/migrations/drop_redundant_layering_indexes.py` · `server/scripts/audit_schema_canon.py`(**유일한 `PER_TRANSACTION` 소비자** — 빌린 엔진) · `server/scripts/check_missing_business_key.py` · `server/scripts/dedupe_business_key_rows.py` · `server/scripts/rebuild_blank_business_keys.py` · `server/scripts/dev_env/snapshot_db.py`. **회귀 테스트**: `server/tests/test_readonly_guard.py`(779줄, `grep -c "def test_" = 22` @`831ab68`).

### `server/virtual_join_config.py` (**687줄**, `4e06eec` 신설 540줄 → `b6942ec`로 **475**) — 가상 조인 선언 로더/검증

**Virtual join은 두 테이블을 저장하지 않고 조회 시점에 잇는다** — `/api/maps/overlay`가 좌표로 하는 일을 **행(row) 모양으로** 하는 것이고, 잇는 기준은 좌표가 아니라 선언된 조인 키다. **이 파일은 선언만 다룬다 — 조인 실행은 여기 없다.**

🔴 **왜 가드가 먼저인가 (운영 DB read-only 실측 2026-07-31, 소스 docstring에 표로 있다)**: `core_defect_map ⋈ eds_fail_map`을 `(lot,slot,x,y)`로 잇면 103,040 → 103,040(x1)인데 `(lot,slot)`으로 잇면 **103,040 → 132,715,520(x1288)**이다. `bonding_log ⋈ wafer_process (lot,slot)`은 14,436 → 2,552,624(x177). **두 선언은 컬럼 두 개 차이인데 결과는 10만 행과 1억 3천만 행이다.** 문법도 맞고 컬럼도 존재하므로 **선언을 읽는 시점에 거부하지 않으면 거부할 자리가 없다.**

🔴 **유일성의 근거는 하나다 — UNIQUE 인덱스 (사용자 확정 2026-07-31: 「인덱스 없으면 거절해」·「유니크 INDEX 걸면 그냥 DB 영속 아닌가」).** 그 지적이 설계를 바꿨다: UNIQUE 인덱스는 **이미 영속**이고 config가 아니라 데이터베이스에 살며 이후의 어떤 쓰기도 그 성질을 깰 수 없다. `pg_index`를 읽는 것은 정책 노브가 아니라 **살아 있는 사실의 조회**다. 그래서 **등급도, 스냅샷도, 예산도 없다.**

🪦 **`b6942ec`가 삭제한 것 — 「만들기 전에 이미 있는지 본다」의 실사례.** 직전 판에는 `GROUP BY … HAVING count(*)>1` 중복 프로브 + `statement_timeout` 예산 + **`incomplete` 상태** + **3등급 모델**이 있었고, 그것들은 **전수 스캔을 게이트로 쓰기 위한** 장치였다(실측 859행/ms → 1,000만 행 ≈ 11.6초). 게이트가 UNIQUE 인덱스로 바뀌자 소비자가 사라졌고, **아무도 보지 않는 안전장치는 없느니만 못하다**(다음 읽는 사람이 무언가 검사되고 있다고 가정한다). 중복 진단을 잃는 것도 아니다 — 운영자가 인덱스를 만들려 하면 **PostgreSQL이 같은 진단을 더 정확하게, 행동하는 바로 그 순간에** 내놓는다(`DETAIL: Key (lot, slot)=(LOT-A, 01) is duplicated.`). **같은 연산이 이미 있는데 열등한 사본을 두지 않는다.**

| 시그니처 / 상수 | 역할 | 라인 |
|---|---|---|
| `VIRTUAL_JOIN_RULES_PATH` (`paths.CONFIG_DIR/virtual_join_rules.json`) · `_IDENT_RE` | 선언 파일 경로 / 식별자 형태 강제 — 이름은 `table_config`에서 오지만 **인덱스 DDL 문장에 보간**되므로 검증이 조립보다 먼저 온다(`enrichment_config._CANDIDATE_COLUMN_RE`와 같은 자세). 실값은 gitignored이고 `.sample`만 tracked | **~82** / **~86** |
| **`CODE_NO_UNIQUE_INDEX` · `CODE_FANOUT_DECLARED` · `CODE_SHAPE`** | **내부 거부 코드 3종** — `config_resolve_report._VJ_CODE_TO_REASON`이 닫힌 사유 어휘로 사상한다([§5-B](#5-b-serverconfig_resolve_reportpy--내-config가-먹었는가의-답-f3fd785-신설)). **여기서 새 사유 단어를 만들지 않는 것이 요점** | **~89–91** |
| `INDEX_PREFIX="uq_vjoin_"` · `_MAX_IDENTIFIER=63` · `DEFAULT_UNRESOLVED_LABEL="미상"` · `MAX_EXPOSE_COLUMNS=32` | 인덱스 이름 규약(63바이트 초과 시 해시로 접는다 — `value_suggest.suggest_index_name`과 같은 규율·같은 상한) / 해소되지 않은 값의 표시 / 조인 하나가 왼쪽 테이블 폭을 통째로 두 배로 만들지 않게 하는 상한 | **~95/96/99/103** |
| `_record(rejections, scope, subject, detail, code=CODE_SHAPE, facts=None)` · `_is_str_list` | 무효 선언 수집기 — `enrichment_config._record`와 같은 형태이고 **`code`·`facts`가 늘어난 것이 유일한 차이**다 | **~106** / **~127** |
| **`required_index_name(table, columns)` / `required_index_ddl(table, columns)`** | **거부가 운영자에게 할 일을 준다.** 「UNIQUE 인덱스가 없다」만 말하고 어느 컬럼인지 말하지 않는 거부는 **행동할 수 없는 거부**다. `b6942ec`의 삭제 후에도 이 둘은 남았다 | **~136** / **~146** |
| `_validate_join(name, raw, known_tables, rejections=None) -> tuple` | 선언 1건의 **모양** 검증(테이블·컬럼 존재, 식별자 형태, 노출 컬럼 수) | **~163** |
| **`validate_virtual_join_rules(raw_config, known_tables=None, ...)`** / **`load_virtual_join_rules(path=None, ...)`** | **세션 없이 부르는 경로 — 모양만 검증하며 아무것도 승인하지 않는다** | **~291** / **~315** |
| `_dialect_of(db)` / **`unique_index_covering(db, table, columns) -> str\|None`** | 조인 키를 **덮는** UNIQUE 인덱스의 이름. **부분집합이면 충분하다**(`(a)`에 UNIQUE가 있으면 `(a,b)`로도 당연히 유일). 🔴 **행을 세지 않고 `pg_index`만 읽는다** — 비용이 테이블 크기와 무관하고 답이 스냅샷이 아니라 **제약의 존재**다. ⚠️ **PostgreSQL이 아니면 `None`**(= 모른다 = 거부). **안전한 방향의 무지** | **~346** / **~353** |
| **`verify_uniqueness(db, rule) -> dict`** | 선언 1건의 유일성 판정 → `{"unique_index", "refused", "code"}`. **통과 조건은 하나다** — 조인 키를 덮는 **유효한** UNIQUE 인덱스의 존재 | **~389** |
| **`load_verified_rules(db, path=None, ...)`** | **이 파일이 보장하는 것**: 여기서 돌려준 선언은 **오른쪽이 조인 키로 유일함이 데이터베이스에 의해 강제된다.** 스냅샷이 아니라 제약이므로 이후의 쓰기가 깰 수 없다 | **~401** |
| **`verification_report(db, path=None, known_tables=None) -> dict`** | `GET /admin/config/virtual-join/verify`의 본체([§1.4](#14-api-라우트-표--어드민운영그래프맵인리치먼트)) | **~432** |

🔴 **판정이 명시적으로 배제하는 인덱스 3종**(모듈 상단 ~44–49): `indisvalid = false`(취소된 `CREATE INDEX CONCURRENTLY`의 잔해 — `to_regclass`로는 잘 풀리는데 플래너는 영원히 안 쓰고 제약도 강제되지 않는다) · `indpred IS NOT NULL`(부분 인덱스 — 술어 안에서만 유일) · `indexprs IS NOT NULL`(표현식 인덱스 — 컬럼이 아니라 식에 대한 유일성). **셋 다 「UNIQUE 인덱스가 있다」로 읽히지만 유일성을 보장하지 않는다.**

🔴 **검사는 오른쪽에만 적용된다 — 왼쪽의 중복은 팬아웃이 아니라 이 기능의 목적이다.** 사용자 시나리오 `dt_log → core_wafer_map (core_lot, core_slot)`는 왼쪽이 키당 128행, 오른쪽이 키당 1행이라 768 → 768(x1.00)이다. 로그 여러 줄이 같은 웨이퍼를 가리키는 것이 곧 조인의 용도이므로, **이 가드가 그것을 잡으면 기능 자체를 잡는 것**이다.

⚠️ **「미상」의 정의는 경계 계약이다** — **두 경우를 모두 덮는다**: ① 오른쪽에 맞는 행이 없다 ② **맞는 행은 있는데 값이 비어 있다**. LEFT 조인만으로는 ②가 보이지 않는다(실측: `bonding_log → core_wafer_map.wafer_id`는 14,436행 **전부**가 행을 찾지만 3,792행 26.27%의 값이 비어 있고, `core_defect_map → core_wafer_map.wafer_id`는 103,040행 전부가 행을 찾지만 **86.25%**가 비어 있다). ②를 미상에서 빼면 분석가는 「값이 있다」고 읽는다. **INNER 조인은 ①을 조용히 지우므로 금지다.**

**테스트**: `server/tests/test_virtual_join_guard.py`(596줄). **선언 샘플**: `server/config/virtual_join_rules.json.sample`(40줄, tracked — 실값 `virtual_join_rules.json`은 gitignored이므로 **구조만** 여기 적는다).

---

## 5-D. 2026-08-04 신설 서버 모듈

> 🔎 **이번 라운드의 서버 신설은 두 갈래다** — ① 가상 조인이 **선언**(`virtual_join_config`)과 **실행**(`virtual_join_executor`)으로 갈렸다 ② 「이미 지나간 데이터에 지금 규칙을 먹인다」는 조작이 산발적 CLI에서 **하나의 레지스트리**(`retroactive`)로 모였다.

### `server/virtual_join_executor.py` (**584줄**, `ed9cfdb` 535에서 **+19**) — 가상 조인의 **실행** 절반

**선언은 [`virtual_join_config`](#5-c-2026-07-31-신설-서버-모듈-2종), 승인은 `pg_index`, 실행은 여기다.** 이 파일은 규칙을 **검증하지 않는다** — `vjc.load_verified_rules`가 통과시킨 것만 받는다.

| 심볼 | 역할 | 라인 |
|---|---|---|
| `SOURCE_NAME="virtual_join"` · `CHUNK_SIZE=1000` · `RULES_CACHE_TTL=5.0` · `_RULES_CACHE` · `KIND_COLLIDE`/`KIND_VIRTUAL_ONLY` | provenance는 `cell_sources.source_name`과 **같은 이름 공간**을 쓴다 · `row_id IN (…)` 청킹 · 검증된 선언의 TTL 캐시 | ~74/77/86/88/220–221 |
| `reset_cache()` / `_verified_by_left_table(db)` / `rules_for(db, left_table)` | 캐시 무효화(호출자 `main.reload_local_process_cache`) / TTL 캐시 + `left_table` 버킷팅 — **예외는 빈 dict로 삼킨다**(선언을 못 읽으면 조인이 없는 것이지 요청이 죽는 것이 아니다) / 해당 테이블 규칙 사본 | ~91/97/126 |
| 🔴 **`virtual_only_columns(db, left_table) -> set`** | **쓰기 거부의 대상 집합 — 유일 소비자는 [`crud.refuse_virtual_join_columns`](#2-serverdatabasecrudpy--레이어링-코어)**. `collide`(왼쪽에 실재하는 컬럼)는 **포함하지 않는다**: 그쪽은 평범한 저장 컬럼이고 그 쓰기가 absent-only 규칙의 "왼쪽 값 있음"을 만든다. 🔴 **`virtual_only`가 `None`(= `table_config` 없이 검증된 선언)이면 `expose` 전체를 대상으로 본다 — 모르면 막는다** | ~131 |
| `announced_columns(db, left_table)` / **`resolved_column_announcements(db, left_table)`** / `exposed_columns(db, left_table)` | `/schema`가 덧붙여 알리는 컬럼(virtual_only만) / **노출 컬럼 전량 + `kind`를 명시**(collide·virtual_only 둘 다) / 위 함수에서 **유도**한 이름 집합 — 검색과 `/schema`가 어긋날 수 없게 | ~148/224/287 |
| **`resolved_expression(db, left_model, left_table, col_name, query)`** | 기여 규칙마다 `outerjoin` 1개(오른쪽은 `aliased`) + `func.coalesce(*parts, label)`. 반환 `(query, expr, label)` \| `(query, None, None)`.<br>🔴 **[N8 정정] 중첩 헬퍼 `_text_part(col)`(**381**)는 더는 숫자만 분기하지 않는다** — 본문이 **`crud.column_text_sql(col)`(**356**) 한 줄**이 됐다. 구 코드는 `isinstance(col.type, (Numeric, Float, Integer))`로 **「어떤 타입이 캐스팅이 필요한가」**를 물었고, **같은 문으로 들어온 다음 타입이 똑같이 죽었다**: `datetime`은 `InvalidDatetimeFormat`, `boolean`은 `InvalidTextRepresentation`(둘 다 프로덕션 방언 실측), **SQLite에서는 죽지도 않고 매칭 안 된 행마다 `True`를 답한다.** 새 관문은 **「이 타입이 *이미* 텍스트인가」**를 묻고 미지 타입은 500이 아니라 CAST로 떨어진다([§2 신설 블록 ②](#2-serverdatabasecrudpy--레이어링-코어)) | **300** |
| `execute_rule(db, rule, row_ids, chunk_size=CHUNK_SIZE)` / `_resolve_one(joined_value, left_value, has_left_column, label)` / **`attach(db, table_name, data_list) -> int`** | 청크 LEFT OUTER JOIN(`matched`는 오른쪽 `row_id` non-NULL) / absent-only 판정(`crud.clean_str_value(...) != ""`): 왼쪽 값 우선 → 조인 값 → 라벨 / **2패스**: 전 규칙의 제안을 `(row_id, col)`별로 모은 뒤(첫 비공백 승) 셀을 쓴다 — **1패스면 뒤 규칙이 앞 규칙의 라벨을 값으로 오독한다.** 🆕 **뒤의 둘은 조인된 값을 `crud.resolved_text_value`로 렌더해 페이로드에 싣는다**(**471** · **545**) — 🔴 **SQL 절반과 페이로드 절반이 구성적으로 같은 문자열이 되어야 「보이는 대로 검색」이 두 답을 가질 수 없다.** ⚠️ **왼쪽 값은 일부러 손대지 않는다**(조인이 *진* 셀은 바이트 동일이어야 한다) — 그 결과 **pinned-text 타입의 `collide` 컬럼에 문서화된 발산 1건**이 남아 있고 총괄 판단 대기다 | **390 / 440 / 475** |

**소비자(전건, `41b17ee`)**: `main.fetch_and_merge_metadata`(**~782**) · `main.VirtualColumnBinder`(**1193** — `apply_column_filters` **1233** / `apply_search_filter` **1271**이 소비) · `main.export_table_csv`(**1688**) · `main.get_table_schema`(**1924**) · `main.reload_local_process_cache`(**3883**) · `crud.refuse_virtual_join_columns`(**2187**). **테스트**: 🆕 **`server/tests/test_virtual_join_types.py`(436줄)** — 🔴 **expose 가능한 타입 우주 전체(String/Float/DateTime/Boolean)를 단언으로 열거해, 네 번째 타입이 들어오면 프로덕션 읽기가 500이 되는 대신 이 파일이 빨개진다.**

### `server/retroactive.py` (**697줄**, 신설) — 소급 적용의 **레지스트리**

> 🟢 **심볼 실측 완료** — 이 절의 심볼은 **`5609ff0`의 커밋된 blob에 존재함이 확인됐고, 그 뒤 HEAD가 움직인 다음 재대조에서도 동일했다**(워킹트리 아님). 🔴 **라인 번호는 싣지 않는다** — 위치는 `git grep -n "<심볼>" -- <경로>`로 확정하라. 숫자가 남아 있는 곳은 **파일 줄 수**이거나, 이름이 없는 덩어리를 가리키며 측정 sha가 함께 적힌 자리뿐이다.

> 🔴 **이 파일은 아무것도 계산하지 않는다 — 이미 있는 다섯 개의 조작에 공통 표면을 씌운다.** 각 op는 `count`(드라이런 미리보기)와 `run`(실행)의 **함수 쌍**이고, 둘 다 기존 모듈을 부른다. **여기에 여섯 번째 집계 구현이 생기면 그것이 이 파일의 실패다.**

- 상수: `RUN_EVENT_TYPE = event_constants.EVENT_RETROACTIVE_RUN` · `RUN_EVENT_TABLE = "__retroactive__"` · `COUNT_EXACT`/`COUNT_SAMPLE`/`COUNT_UPPER_BOUND` · `DEFAULT_SCAN_LIMIT=200`/`MAX_SCAN_LIMIT=2000` · `class RetroactiveRefused(Exception)`.
- **`OPERATIONS` — 5종**: `chain_replay` · `withdraw` · `enrichment_backfill` · `enrichment_confirm` · `graph_orphans`. 항목마다 `label`·`what_is_missing`·`params`·`count`·`run`·`cli`·`deletes`·`restartable`·`commit_granularity`를 든다. **`graph_orphans`만 `restartable: False`**(끝에 한 번 커밋 — 중단되면 통째로 롤백).
- 🔴 **`count_kind`가 세 값인 것이 이 표면의 정직성 계약이다**: `exact` / `sample`(스캔 상한까지만 봤다) / `upper_bound`(집계 두 개로 답했고 행을 걷지 않았다). `_count_withdraw`는 `scan_limit`을 **의도적으로 무시**하고 `scanned=None`을 돌려준다 — 걷지 않은 것을 "N행 스캔"이라고 말하지 않기 위해서다.
- 카운터 5종: `_count_chain_replay` · `_count_withdraw` · `_count_enrichment_backfill` · `_count_enrichment_confirm`(~261 — **노브가 꺼져 있어도 측정은 되게** `ignore_knob=True`로 드라이런하고 `blocked_reason="auto_confirm_off"`를 세운다) · `_count_graph_orphans`.
- 실행기 5종: `_run_chain_replay` · `_run_withdraw` · `_run_enrichment_backfill` · `_run_enrichment_confirm`(~364 — **여기서는 노브가 동의 게이트라 `ignore_knob=False`**) · `_run_graph_orphans`.
  - ⚠️ **`_run_chain_replay`는 `limit`을 넘기지 않는다** — 카운트는 표본이고 실행은 무제한이다. 미리보기의 수가 실행의 수와 같다고 읽으면 안 된다.
- 표면: `operation(op)` · **`inventory()`(~511 — 순수 config 투영, DB 접근 0. 그래서 요청 경로에서 안전하다)** · `validate(op, params)`(~533 — 미선언 param 이름을 **먼저** 거부, `withdraw`의 `source`가 `chain_replay.PROTECTED_SOURCES`면 거부. 🔴 **리터럴을 베끼지 않고 그 상수를 읽는다**) · `clamp_scan_limit(limit)` · **`count(db, op, params, scan_limit)`(~585 — `finally: db.rollback()`)** · **`publish(db, op, params, requested_by=None)`** · **`execute(payload, log)`**.
- 🔴 **`publish`와 `execute`가 갈린 것이 토폴로지 계약이다**: 웹 프로세스는 outbox 행 하나를 쓰고 `NOTIFY`만 한다(**아무것도 실행하지 않는다**), 실제 실행은 스케줄러 프로세스가 자기 데몬 스레드에서 한다([§6 `run_auto_update.py`](#6-기타-서버-모듈-한줄-요약)). `execute`는 **어떤 예외도 raise하지 않고** `status="error"`로 접는다 — 소급 실행 하나가 스케줄러 데몬을 죽이면 안 된다.
- **호출자**: `main.py`의 라우트 3종 · `run_auto_update.MultiDiscoveryScheduler.start_retroactive_run`. ⚠️ **실행 라우트만 `require_admin_token_strict`이고 조회 둘은 `require_admin_token`이다.**

### `server/enrichment_backfill.py` (**411줄**, 신설) — 룰 도입 **이전** 소스 행의 파생 행 생성

⚠️ **`server/scripts/backfill_enrichment.py`(CLI)와 다른 파일이다** — CLI는 이 모듈의 얇은 호출자다([§6](#6-기타-서버-모듈-한줄-요약)).

- `SOURCE_NAME="enrichment_backfill"`(~66) — 🔴 **`SOURCE_PRIORITY`에 의도적 미등재 = 99(최하위)라 `user`(0)를 절대 못 이긴다**([§2](#2-serverdatabasecrudpy--레이어링-코어)). 상수 `DEFAULT_CHUNK_SIZE=1000`(~67) · `EXISTING_BK_FETCH_CHUNK=5000`(~68) · `BK_PROBE_CHUNK=1000`(~73) · `PROGRESS_EVERY_CHUNKS=50`(~74) · `SAMPLE_NEW_KEYS=20`(~75) · `class BackfillRefused`(~78).
- **`load_rule(rule_name, known_tables, force_disabled=False)`(~82)** — ⚠️ **공개 검증기가 아니라 private `enrichment_config._validate_rule`을 부른다. 의도적이다**: 공개 쪽은 거절 **사유**를 삼킨다.
- 🔴 **존재 조회기 2종이 이 모듈의 설계 축이다**: **`_PreloadedKeys`(~163, `kind="preload"`)** — 파생 테이블 business key 전량을 미리 뜬다(전체 실행용) · **`_ProbedKeys`(~177, `kind="probe"`)** — 청크마다 `in_()`으로 묻고 **부재까지 메모**한다. **부재 캐시가 요점이다**: 1번 청크에서 만든 키가 5번 청크에서 "신규"로 다시 세어지지 않는다. 어느 쪽을 썼는지는 `stats["existing_lookup"]`으로 **응답에 실린다**.
- **`run_backfill(db, rule, apply=False, limit=None, chunk_size=…, log=print, scan_limit=None)`(~221)** — 조회기 선택은 **`scan_limit is not None`**(표본 미리보기면 probe, 전체 실행이면 preload). 드라이런은 rule에서 `aggregations`를 떼어내 맵퍼 재집계 쿼리를 건너뛴다(**정체성 diff와 카운트는 무관하다 — 이걸 "고치면" 드라이런이 훨씬 비싸진다**). `limit`은 **신규 정체성에만** 건다. 쓰기는 실제 맵퍼(`map_enrichment_dedup`) + 실제 경로(`crud.apply_batch_updates`)를 탄다 — outbox가 정상 발화해 그래프도 머티리얼라이즈된다.

### `server/trace_fixture/` 패키지 (6파일 **1,356줄**) + 스크립트 2종 — 추적 시나리오 픽스처와 그 채점자

> 🔎 **오라클이 딸린 합성 데이터셋이다** — "이 시스템이 다이 하나의 계보를 실제로 추적할 수 있는가"를 **채점 가능한 형태로** 묻는다. 스펙은 `docs/spec/TRACE_FIXTURE_SPEC.md`.

| 파일 | 줄 | 소유 |
|---|---|---|
| `__init__.py` | 21 | 재export 표면만 — `GeneratorConfig`·`generate_batch`(from `world`) · `emit_batch`(from `emit`) |
| `world.py` | 689 | **생성기.** `GeneratorConfig`(~45, seed 기본 `20260801 * batch`) · `class World`(~71, private 빌더 ~20종) · `World.build()`(~653) · `generate_batch(cfg)`(~688). 스펙 불변식 7종을 **assert로** 들고 있고, 결측 3종(`NEVER_EXISTED`/`PIPELINE_DROPPED`/`PRESENT_BUT_WRONG`)을 구분해 심는다 |
| `frames.py` | 110 | **8프레임(4회전 × 2면).** 🔴 **자체 산술이 없다** — `utils.coordinate_transformer.WaferMapCoordinateTransformer`에 위임한다. `parse_frame`(~41) · `class FrameGrid`(~49) · `circular_mask`(~102). **`FrameGrid.invariant_frames`가 「이 맵이 판정 가능한가」의 형식적 시험**이다(점유 셀 집합의 stabilizer) |
| `emit.py` | 144 | **출력.** `ORDER`(~30)/`ORACLE_ORDER`(~45) · `PREFIX="trace_fixture"`(~63) · `_atomic_write_csv`(~66, `.tmp` + `os.replace`) · **`oracle_dir`(~86 — 🔴 `ingestion_workspace` **밖**이다: 정답 파일이 인제션될 수 없게)** · `staging_dir`(~92) · `emit_batch(...)`(~96). **비즈니스 키 컬럼을 쓰지 않는다** — 합성은 `crud.apply_batch_updates`의 몫 |
| `baseline_trace.py` | 192 | **소비자(추론기).** `UNRESOLVED = "미상"`(~32) · `class PositionHistory`(~49, bisect 색인) · `class BaselineTracer`(~102). 🔴 **추측하지 않는다** — 풀 수 없는 단계는 `UNRESOLVED` + `stop` 사유 |
| `scoring.py` | 200 | **채점자.** `is_unresolved`(~26) · **`norm`(~30 — 정수형 float를 접는다. 이 한 줄이 없어서 5,296행에 recall 0%를 보고한 적이 있다)** · `load_oracle`(~56) · `score_frames`(~67)/`score_die_lineage`(~100)/`score_missing`(~143)/`score_ambiguous`(~169) · `summarise`(~189). 🔴 **모호한 케이스에서 정직한 `미상`은 CORRECT로 세고, 자신 있는 답은 `false_confidence`로 센다** |

- **`server/scripts/generate_trace_fixture.py`(88줄)** — argparse만. `--to-raws`는 **opt-in**이고 기본 착지는 `trace_fixture_staging/`이라 라이브 워처가 리뷰 전에 인제션하지 못한다.
- **`server/scripts/score_trace_fixture.py`(298줄)** — 실 DB 세션으로 `lot_event`/`dt_log`/`bonding_log`를 읽고 **출하 중인 `enrichment_candidates.resolve_target_candidate`**에 물어 채점한다(단일 후보가 아니면 `UNRESOLVED`). ⚠️ **네 절 중 3·4절만 `scoring`을 경유하고 1·2절(앵커 밴드·대칭)은 스크립트가 직접 집계한다** — 채점자가 둘이다.
- ⚠️ **`ed9cfdb` 시점에 auto-update 수집기는 이 패키지를 import하지 않는다.** docstring의 "수집기와 CLI가 둘 다 얇은 호출자"는 **의도이지 현황이 아니고**, 실제 importer는 스크립트 2종과 `server/tests/test_trace_fixture.py`뿐이다.

---

## 5-E. 2026-08-04(2차) 신설 서버 모듈 2종 — 표기 정규화 · 낡은 엣지 스윕

**계보가 무관한 둘이 한 범위에 들어왔다.** 하나는 **쓰기 경로의 파생 컬럼**(`notation_norm`), 하나는 **재유도가 지우지 못하는 그래프 엣지**(`graph_stale_edges`). 공통점은 하나뿐이다 — **둘 다 「원본을 고치지 않고 파생물로 답한다」**.

### 🆕 `server/notation_norm.py` (**808줄**) — WF/lot/slot 표기 정규화 — 🔴 **읽기 시점의 접기이지 저장되는 파생 컬럼이 아니다**

> 🟢 **심볼 실측 완료** — 이 절의 심볼은 **`5609ff0`의 커밋된 blob에 존재함이 확인됐고, 그 뒤 HEAD가 움직인 다음 재대조에서도 동일했다**(워킹트리 아님). 🔴 **라인 번호는 싣지 않는다** — 위치는 `git grep -n "<심볼>" -- <경로>`로 확정하라. 숫자가 남아 있는 곳은 **파일 줄 수**이거나, 이름이 없는 덩어리를 가리키며 측정 sha가 함께 적힌 자리뿐이다.

> 🔴 **[2026-08-06] 이 절은 존재하지 않는 API를 등재하고 있었다 — 각주가 아니라 시그니처 표에서.** `8d306a5`가 **저장되는 파생 컬럼 자체를 철회**했는데, 이 절의 표는 `apply_derivations`·`rederive`·`derivations_for`·`derivations_by_table`·`derived_columns_for`·`normalized_value`와 상수 `REDERIVE_CHUNK_SIZE`/`REDERIVE_SAMPLES`를 **살아 있는 라인 번호를 달고** 계속 나열하고 있었다. 같은 절의 각주가 철회 사실을 적고 있었지만 **각주는 표를 이기지 못한다 — 독자는 표를 믿는다.** 그래서 주석이 아니라 **삭제**했다. 묘비가 필요하면 자리는 [§0](#0-묘비-목록--소스에-존재하지-않는-이름)이다.
>
> 🔴 **이 절이 서술하던 아키텍처 자체가 틀려 있었다.** 「원본은 안 건드리고 `<col>_norm`에 정규값을 앉힌다」는 **더 이상 이 모듈이 하는 일이 아니다.** 지금 이 모듈은 **아무것도 저장하지 않는다** — 접기는 **질의 시점에 SQL에서** 일어난다(`fold_sql_text`·`fold_notation_sql`, 조인이 쓰는 바로 그 식). 그래서 「폴딩 규칙이 틀렸으면 다시 유도하면 된다」는 문장도 대상이 없다: 다시 유도할 저장분이 없다.
>
> **측정 기준**: 아래 표는 `5609ff0`의 커밋된 blob 전건 실측이다.

| 시그니처 / 상수 | 역할 |
|---|---|
| `NOTATION_RULES_PATH = paths.config_path("notation_rules.json")` | 선언 파일 경로(`paths` 경유 — `__file__`로 조립하지 않는다) |
| `RULE_SEPARATOR`·`RULE_CASE`·`RULE_ZERO_PAD` / `KNOWN_RULES` / **`IMPLEMENTED_RULES`** / `DEFAULT_RULES` | 규칙 이름 / 아는 것 / **실제로 구현된 것(`separator`·`case`)** / 기본값(`separator` on · `case` on · **`zero_pad` off**) |
| **`SEPARATOR_TARGET = "-"`** / `SEPARATOR_CODEPOINTS` / `SEPARATOR_PATTERN` / `_SEPARATOR_RUN_RE` | 🔴 **`_`가 아니라 `-`인 것이 요점이다** — `_`는 복합 맵 키를 잇는 글자다. `.`·`_`·`-`·공백의 연속을 `-` 하나로 |
| `CASE_SOURCE_ALPHABET`/`CASE_TARGET_ALPHABET`/`_CASE_TABLE` · `_check_pattern_shape()` | 대소문자 접기 테이블 / 패턴 모양 자체 검사(import 시점) |
| 🔴 **거절 어휘 — 전건 열거**(개수를 적지 않는다): `CODE_SHAPE` · `CODE_ZERO_PAD_UNIMPLEMENTED` · `CODE_UNKNOWN_RULE` · `CODE_UNDECLARED` · `CODE_NOT_TEXT` | ⚠️ **종전 지도는 이 목록을 「6종」이라 적으면서 `CODE_WOULD_REWRITE_RAW`·`CODE_KEY_COLUMN`을 들었는데 둘 다 소스에 없고, 실재하는 `CODE_NOT_TEXT`는 빠져 있었다.** 개수도 구성원도 틀린 전형이다. `config_resolve_report._NOTATION_CODE_TO_REASON`이 이 어휘를 닫힌 집합으로 받는다 |
| `SCOPE_FILE`·`SCOPE_TABLE`·`SCOPE_COLUMN` | 거절의 스코프 |
| `RULES_CACHE_TTL = 5.0` / `_RULES_CACHE` / `reset_cache()` | `virtual_join_executor`와 **같은 규율**의 TTL / 웹서버 config 핫리로드 훅(`main.py` |
| **`fold_notation(text, rules: dict)`** | **규칙마다 독립 분기다** — `{}`를 주면 입력이 그대로 나온다. 그 성질이 「각 규칙이 혼자 켜지고 꺼지는가」를 **진짜 테스트로** 만든다. 비-문자열은 통과 |
| `enabled_rule_names(rules) -> list` / `folds_anything(rules) -> bool` | 켜진 규칙 이름 / 이 규칙 집합이 무언가를 실제로 바꾸는가 |
| 🔴 **`SQL_FOLD_FUNCTION = "assy_fold_notation"`** / **`fold_sql_text(inner_sql, rules) -> str`** / `_install_notation_fold_construct()` / **`fold_notation_sql(text_expr, rules)`** | **접기가 실제로 일어나는 자리 — 질의 시점의 SQL이다.** 저장된 파생 컬럼이 아니라 **조인·비교가 쓰는 바로 그 식**이 접는다 |
| `_SQLITE_FOLD_INSTALLED` / `install_sqlite_fold()` | SQLite에 같은 함수를 심는다 — ⚠️ **PG와 SQLite가 같은 답을 내야 하는 자리**(테스트가 PG가 거절하는 것을 받으면 운영만 터진다) |
| `_record(rejections, scope, subject, detail, code=CODE_SHAPE)` / `_normalize_rules(raw, subject, rejections=None)` | `enrichment_config._record`와 같은 자세(데몬 로그에만 사는 스킵은 아무도 못 보는 스킵이다) / 🔴 **미지 규칙명과 `zero_pad: true`는 조용히 버려지지 않고 거절로 보고된다** |
| 🔴 **`_validate_column(table, column, spec, table_rules, …)`** | 컬럼 선언 검증 |
| `validate_notation_rules(raw_config, known_tables=None, …)` / `load_notation_rules(path=None, known_tables=None, …)` | `known_tables`는 `crud.TABLE_CONFIG` / **파일 부재는 거절이 아니다** |
| **`normalized_by_table() -> dict`** / `rules_for_column(table, column)` / `is_normalized(table, column) -> bool` | TTL 캐시를 낀 조회 3종 — **읽기 경로의 입구**. 🔴 **읽지 못한 선언은 「정규화 없음」이지 장애가 아니다** |
| 🔴 **`join_pair_rules(left_table, left_column, …)`** | 조인 양쪽의 규칙이 **같을 때만** 접는다 — 한쪽만 접으면 조인이 조용히 어긋난다 |
| `PREVIEW_GROUP_LIMIT=500`/`PREVIEW_VARIANT_LIMIT=20` / **`fold_preview(db, table, column, rules=None, …)`** / `declared_previews(db, limit=PREVIEW_GROUP_LIMIT)` | 「이 규칙을 켜면 무엇이 합쳐지는가」의 미리보기. ⚠️ **요청 경로에 상주하는 종류의 질의가 아니다**(`main.py`가 그 사유를 적는다) |

> ⚠️ **Phase 1 — 파생값을 소비하는 저장 컬럼은 없다.** 맵 키·필터·조인을 접힌 값으로 돌리는 것은 **별도의 opt-in 결정**이고, `config_resolve_report._resolve_notation`이 그 사실을 선언마다 문장으로 붙여 보고한다.
>
> 🔴 **`zero_pad`는 선언돼 있으면서 거절된다 — 조용히 무시되는 노브가 아니다.** `WF010`/`WF10`의 오합병 위험이 있고 그 인구 조사(census)가 아직 돌지 않았다. 켜면 `GET /admin/config/resolve`에 **`zero_pad_unimplemented`**가 이름으로 뜬다.
>
> 🪦 **철회된 것들** — 되살리려 하기 전에 이 줄을 읽을 것: 쓰기 거부 `crud.refuse_notation_derived_columns`(묘비 주석 `server/database/crud.py` · CLI `server/scripts/rederive_notation_norm.py` · 이 모듈의 파생 API 일습. ⚠️ **종전 지도가 적던 「`canonical_bind_value`를 모듈 최상단에서 import한다」도 거짓이다 — 지금 이 파일에 그 import가 없다.**
>
> 📌 **`server/config/notation_rules.json.sample`(**48줄**)의 구조만 기술한다** — `server/config/*`는 gitignored라 라이브 값은 문서화 대상이 아니다. 최상위 키: `__comment` · `__how_to_enable` · **`rules`**(파일 수준 기본 규칙 집합) · **`tables`**(테이블별 override + 컬럼 선언).

### 🆕 `server/graph_stale_edges.py` (**549줄**, 신설) — 재유도의 **지울 수 있는 절반**

**재유도는 교정이어야 하는데 일부는 축적이다**(보드 O2). 재유도를 견디고 살아남는 엣지 모집단이 셋이고, 셋 다 실측이다:
- **(A) 소유 행이 삭제됨** — `materialize_events`는 `skipped_deletes`를 세기만 하고, `resync_table`은 **존재하는 행만** 순회한다.
- **(B) 테이블의 매핑이 통째로 은퇴함** — `mappings.get(table)`이 `None`이면 `resync_table`은 빈 통계만 돌려준다.
- **(C) 여전히 생산되는 triple의 `source_name`이 대체됨** — 🔴 **스윕하지 않고 보고만 한다.**

🔴 **소유권 모델이 이 모듈의 전부다.** `graph_edges.source_row_ref`는 `cell_sources`의 그래프판이고 **한 자리에서만 쓰인다**(`graph_materializer.bulk_upsert_edges`, `f"{table}:{row_id}"`). 엣지가 유도 소유인지는 **그 문자열이 `(table, row_id)`로 파싱되는가**로만 판정하며 `type`·라벨·끝점에서 **추론하지 않는다.**

| 시그니처 / 상수 | 역할 | 라인 |
|---|---|---|
| `CHUNK=1000` / `DEFAULT_MAX_FRACTION=0.5` / `DEFAULT_MIN_POPULATION=10` | 순회 단위 / 한 타입이 이보다 많이 잃으면 삭제가 아니라 **`declined`** / 비율 검사 면제 하한 | **142 / 145 / 148** |
| 🔴 **`from config_resolve_report import REASON_MAPPING_UNAVAILABLE, REASON_NOT_DECLARED, REASON_NOT_REACHED`** | **불능(inability) 어휘를 다시 철자하지 않고 import한다** | **153–157** |
| `VERDICT_ROW_GONE`·`VERDICT_LIVE`·`VERDICT_NOT_DECLARED`·`VERDICT_NOT_REACHED` / **`SWEEPABLE_VERDICTS`** | 판정 4종 / **스윕 대상은 둘뿐**(`row_gone`·`not_declared`). `not_reached`는 **절대 스윕되지 않고 언제나 세어진다** | **162–167 / 170** |
| **`parse_row_ref(ref)`** | `"table:row_id"` → `(table, row_id)`. 🔴 **`None`은 진짜 답이다**(「소유권을 모른다」) — 「행이 사라졌다」와 절대 뭉치지 않는다 | **175** |
| `classify_refs(db, refs, mappings)` | 행 존재 여부를 **선언이 매핑하고 이 프로세스가 들고 있는 테이블에 대해서만** 묻는다 | **194** |
| **`is_human_confirmed(source_name)`** | 🔴 **사람이 확정한 엣지는 삭제 집합에서 빼고 `protected`로 보고한다.** 판정은 `crud.USER_SOURCE`를 **양성으로 고르는 것**이지 자동 소스를 블랙리스트하는 것이 아니다(라이브의 자동 소스 값이 **10,750종**이다) | **236** |
| `iter_edges(db, scan_limit=None, chunk=CHUNK)` / `edge_population(db)` / `report_superseded_source_edges(db)` | 키셋 스캔 / 집계 1회(언제나 정확) / **(C) 모집단의 읽기 전용 진단**(`graph_orphans.report_duplicate_source_edges`에 위임) | **249 / 277 / 288** |
| 🔴 **`plan_sweep(db, mappings, max_fraction=…, min_population=…, scan_limit=None)`** | **아무것도 쓰지 않는다.** 반환에 `population`/`per_type`/`sweepable`/`declined`/`protected`/`not_reached`/`delete_ids`/`count_kind`/`scanned`/`scan_limit`/`truncated`/`elapsed_ms`. 🔴 **절단된 스캔은 아무것도 지우지 않는다** — 예산 가드의 분자가 표본에서 오는데 분모는 전 모집단이라 비율이 거짓이 된다 | **301** |
| `apply_sweep(db, plan)` | 🔴 **`plan["delete_ids"]`를 정확히 그것만 지우고 아무것도 다시 유도하지 않는다** — 여기서 모집단을 재계산하면 **드라이런이 보여 주지 않은 것을 지울 수 있다** | **432** |
| **`format_plan_summary(plan, blockers=None, applied=None)`** | 🔴 **삭제만 보고하는 스윕은 「전부 거절됐다」를 「할 일이 없었다」와 똑같이 읽히게 만든다** | **451** |
| **`run_sweep(known_tables=None, apply_deletions=False, …)`** | ⚠️ **기본이 드라이런이고, 이것은 `graph_orphans.run_scheduled(apply_deletions=True)`와 의도적으로 다르다.** `graph_orphans.declaration_blockers`가 하나라도 있으면 **전체 거부**. raise하지 않고 로그한다 | **485** |

> **도달: CLI `server/scripts/graph_stale_edge_sweep.py`(193줄)뿐.** 🔴 **형제 스크립트와의 순서가 문서화돼 있다** — `graph_orphan_sweep.py`는 **차수 0 노드**를 지우는데, **엣지가 살아 있으면 그 두 끝점은 고아 스윕의 사정거리 밖**이다. **이쪽을 먼저 돌린다.** exit `0`=할 일 없음/보고·적용 완료 · `2`=거부(비격리 데이터루트에 `--apply`) · **`3`=예산 가드가 무언가를 `declined`했거나 선언이 깨끗하지 않거나 스캔이 절단됨** — 🔴 **「작업이 미완이다」는 운영자가 놓치면 안 되는 상태라 종료코드가 따로 있다.**

---

## 5-F. 🆕 정렬 채점 계열 (index scoring family) — `server/map_alignment.py` (2026-08-07 등재)

> 🟢 **심볼 실측** — 아래 전부 **`e943e46`의 커밋된 blob** 실측. 위치는 `git grep -n "<심볼>" -- server/map_alignment.py`.
>
> 🔴 **이 계열은 어느 문서에도 없었다.** QA 둘이 독립으로 같은 것을 관찰했고 실측이 그것을 확인한다 — `map_alignment.py`가 3,272 → **5,961**줄이 되는 동안 늘어난 것의 대부분이 이 계열인데, [§5 map_alignment 표](#-servermap_alignmentpy--프레임-정렬의-채점자)는 등재 당시의 좌표계·메타·워크리스트 절반만 담고 있었다.
>
> 🔴 **이 계열의 지표 둘은 「작을수록 좋다」이고, 이 파일의 다른 모든 지표와 방향이 반대다**(`direction_violations` · `index_group_count`). 소스 주석이 그것을 명시적으로 경고한다 — **점수 문턱에 섞어 넣으면 같은 이름이 반대 방향을 뜻하게 된다.**

### ① 훑기(walk) — 순번의 정본

| 심볼 | 무엇인가 |
|---|---|
| **`serpentine_index(cells, top_is_min_y=True, left_to_right=True) -> dict`** | 유효 다이 집합 → `{순번: (x, y)}`, 1부터. **phys도 메타도 안 읽는다.** 🆕 규칙이 **셋이 아니라 넷**이고 **넷 다** 명시적으로 고정한다: ① 행 순서(맨 위 행부터) ② 방향 교대(**셀이 있는 행에서만** — 통째로 빈 행은 방향을 뒤집지 않는다) ③ **행 안의 빈칸은 번호를 먹지 않는다** ④ 🆕 **시작 모서리**(`c4eaffa`, 2026-08-07) |
| 🆕🆕 **④ 시작 모서리 축 — `left_to_right`** | **[`c4eaffa` 신설 · `db1ee42`에서 후보 축으로 배선]** 참이면 첫 행이 왼→오, 거짓이면 **오른쪽부터**. 🔴 **우상단부터 뽑는 설비가 실재한다**(제품 소유자 2026-08-07). ⚠️ **교대 규칙(②)은 안 바뀐다 — 위상만 반 칸 밀린다**: `reverse` 판정이 `(r % 2 == 1) == left_to_right`가 된다.<br>🆕🆕 🟢 **[2026-08-11] 「축은 있는데 아무도 탐색하지 않는다」는 이제 거짓이다 — 배선됐다.** 두 번째 후보 축이 `side`(거울)에서 이 축으로 **교체**됐고, 대응의 유일한 철자는 **`left_to_right_of(frame)`**이다. 🔴 **호출자를 세지 말고 이름으로 고정한다** — `map_alignment.py` 안 실측 히트는 `_anchor_shift`(앵커 모서리 선택 + 진단 줄) · `score_candidates`(후보 루프의 `cand_l2r`) · 진단 블록이고, `candidate_start`를 거쳐 `serpentine_index`/`serpentine_rank`의 세 번째 인자로 들어간다.<br>🔴 **`c959368`이 「거울 프레임 위에 축을 *더하는*」 배선을 시도했다가 되돌렸다** — 후보 공간에 거울 절반이 남아 있으면 두 축이 **중복**이라 모든 후보가 자기 쌍둥이와 동점이 된다(10 빨강). **축은 거울 절반의 *대체*이고, 그 교체가 `db1ee42`에서 일어났다.** 후보 수는 여전히 8이다 |
| **`serpentine_rank(cells, top_is_min_y=True, left_to_right=True) -> dict`** | 같은 훑기의 **역**: `{(x, y): 순번}`. 🔴 **훑기를 두 번 구현하지 않는다 — `serpentine_index`를 뒤집는다**(🆕 `left_to_right`도 그대로 전달한다). 좌표 중복 시 **먼저 훑힌 번호가 남는다** |
| 🔴 **`_walk_by_index(phys, cell_owner, idx_k, idx_has) -> {owner: [(k, y, x, i), …]}`** | **[`069b4e9` 신설] 순번 순 걸음 순서의 공유 정본.** 🔴 **순서는 배열의 성질이 아니라 *맵*의 성질이다** — 중복 `dt_index`는 정준 위치 `(y, x)`로 깨고 **그다음에야** 배열 위치로 깬다. 🔴 **헬퍼가 하나인 것이 요점이다**: `direction_violations`와 `index_group_count`는 **함께 읽히는 한 쌍**이라 「걸음 순서」의 두 번째 철자가 생기면 같은 맵의 서로 다른 두 걸음을 재게 된다. **배선된 코드를 건드리는 변경**이고 그 반경은 **한 맵 안의 중복 `dt_index`**다(구 순서는 `ORDER BY` 없는 DB 반환 순서였다). 실측(QA-1 F3): 한 맵, 두 행 순서 → `groups` **2 vs 1** |
| `_normalised_indices(source_indices, cell_owner)` | 저장된 순번 → **맵마다 1부터 다시 시작하는** 정수 배열 + 「번호가 있는가」 진리값. `0..255`와 `1..266`이 둘 다 실재하므로 **관측 최솟값을 1로** 옮긴다. 🔴 **base는 맵마다 잡는다** — 전역 최솟값으로 맞추면 한쪽이 통째로 밀리고 **그 오답은 개수로 안 잡힌다** |
| 🆕🆕 `_index_member(phys, cell_owner, idx_k, idx_has, left_to_right: bool = True)` | 셀마다 「훑기에서 몇 번째인가 == 저장된 순번인가」. 🔴 **번호가 없는 셀도 훑기에는 들어간다** — 빼면 그 뒤가 전부 한 칸씩 당겨진다. 채점은 번호가 있는 셀에서만. 🆕🆕 **다섯 번째 인자가 뒤에 기본값과 함께 붙었다** — 후보의 시작 모서리가 여기까지 흘러야 두 걸음이 실제로 다르게 채점된다 |

### ② 방향 — 순서가 못 가르는 자리

| 심볼 | 무엇인가 |
|---|---|
| 🆕🆕 **`direction_judge(ref_phys, left_to_right: bool = True) -> (rows, dir_of, next_row)`** | 기준 바닥(정준 좌표) → 서펜타인의 **규칙 자체**. 🔴 **판사는 기준이지 소스가 아니다** — 소스 자신의 범위로 판정하면 「행이 한 칸 만에 끝났다」가 되어 회전된 프레임이 정답과 구별되지 않는다. 🆕🆕 **두 번째 인자가 붙었다** — 판사도 시작 모서리를 알아야 우상단 걸음을 위반으로 세지 않는다 |
| 🔴 **`direction_violations(phys, cell_owner, idx_k, idx_has, judge) -> (위반수, 잰 걸음수)`** | 연속 순번 사이 걸음 중 **서펜타인을 벗어난 것**의 수. 규칙 넷: ① 같은 행 안에서는 걸음 부호 = 행 방향 ② 행 바꿈은 **두 조건 다** 참일 때만(진행 방향으로 바닥 다이가 안 남았고, 옮긴 행이 바닥 기준 바로 다음 행) ③ **거리는 안 센다, 방향만 센다**(부분 맵의 구멍은 위반이 아니다) ④ **바닥 밖 셀은 판정하지 않는다**(점유 축이 이미 센다). 🔴 **작을수록 좋다** — 호출부는 `score_candidates` 안이다. ⚠️ **시그니처는 안 바뀌었다** — 걸음 방향은 `judge`가 이미 지고 온다 |

### ③ 그룹 — dt-to-core 축 (배선 전)

| 심볼 | 무엇인가 |
|---|---|
| 🆕 **`index_group_count(phys, cell_owner, idx_k, idx_has) -> (groups, measured_steps)`** | **[`069b4e9` 신설 · 호출자 0]** 순번이 오르는 동안 **y가 내려가는** 걸음의 수 → 맵마다 `groups = boundaries + 1`, 맵 합. 인자는 `direction_violations`가 이미 나르는 넷과 **같은 것을 같은 순서로** 받는다(둘이 함께 읽히므로). 🔴 **작을수록 좋다 — 점수 문턱에 먹이지 마라.** 🔴 **번호를 실은 셀이 없으면 `(None, 0)`** — **부재는 0이 아니다**(0이면 「한 그룹」 = 만점으로 읽힌다). **y가 같으면 경계가 아니다**(서펜타인 행 안에서 y는 상수다) |
| ⚠️ **그룹 최소화만으로는 프레임이 안 정해진다** | 🔴 **앞/뒤 거울에서 항상 2중 동점이고 이것은 구조적이다** — 뒤집기는 `x → -x`이고 그룹 경계는 **y 사건**이라 뒤집어도 경계가 안 바뀐다. 정면 전용 판정이 그것을 **푸는 것이 아니라 도메인 밖으로 내보낸다** |
| 🔬 **88/88 vs 4/88은 모순이 아니다** | 같은 순번이 DT 훑기에서 88/88, core 훑기에서 4/88이 나온 실측이 반박처럼 읽혔으나 **둘은 애초에 같은 것을 묻지 않았다.** 배포된 술어는 「이것이 **전역** 서펜타인의 k번째 칸인가」를 묻고 **core 픽은 bin-major**라, **참 프레임 아래에서 거짓인 것이 구성상 당연하다**(생성기에서 증명되며 측정이 필요 없다). 4는 실재하지만 **라벨이 틀렸다** — 88다이 바닥에 대해 **틀린 프레임이 쥔 여덟 중 최선**이다. 🔴 **그 위에 선 문턱-20 유도는 옳고, 「정정」해서 없애면 안 된다** |
| 채점자 | `server/tests/test_index_group_count.py` · `server/tests/test_dt_index_walk_core_axis.py` · 씨앗 스크립트 `server/scripts/seed_dt_index_walk.py` |

### ④ bin 지문 — 앵커가 못 서는 자리의 평행이동

| 심볼 | 무엇인가 |
|---|---|
| 🆕 **`bin_fingerprint_shift(phys, bin_labels, reference_bins, seat_cap=_RESIDUAL_SEAT_CAP, min_support=_BINFP_MIN_SUPPORT) -> (dx, dy, matched, seats, reason)`** | **[`069b4e9` 신설 · 호출자 0]** **원본 core bin 맵**이 함의하는 평행이동. 🔴 **왜 앵커가 아니라 지문인가** — 작업이 bin 일부만 쓰면 첫 픽은 **웨이퍼가 아니라 그 부분집합**의 좌상단이라 앵커 규칙(`_anchor_shift`: 최소 순번 → 기준 좌상단)이 거짓을 말하고 맵이 통째로 밀린다. bin 라벨은 **모서리가 아니라 패턴**이다. **창이 아니라 좌석 열거**(`_residual_shift`와 같은 논거) — 후보 평행이동은 데이터에서 뽑고, 기준에 선형이지 반경에 이차가 아니다 |
| 거절 어휘 | `BINFP_NO_SOURCE_BINS` · `BINFP_NO_REFERENCE_BINS` · `BINFP_NO_SEAT`(= `RESIDUAL_NO_QUALIFYING_SEAT`) · `BINFP_NOT_UNIQUE`(= `RESIDUAL_NOT_UNIQUE`) · **`BINFP_SEAT_CAP`**(🔴 **`RESIDUAL_SEAT_CAP`의 별칭이 아니라 자기 이름을 갖는다** — 이쪽은 자리를 하나도 안 보고 **먼저 거절**하고, 잔차 탐색 쪽은 「거기까지 훑었다」는 진행 사실이다. 한 철자에 두 계약을 얹으면 문자열로 분기하는 호출자가 절반의 경우 틀린 계약을 읽고 **어떤 테스트도 그것을 못 잡는다**) · **`BINFP_LOW_SUPPORT`**(「못 골랐다」가 아니라 「골랐는데 근거가 모자란다」 — 운영자의 수리가 다르다: 기준 맵의 리비전을 의심하라) |
| `_BINFP_MIN_SUPPORT = 3` | 평행이동 하나를 **몇 개의 다이가 받쳐야 답이라 부르는가.** 1이면 우연 하나로 웨이퍼 반경만큼 밀린 맵이 `reason=None`으로 나간다(QA-1 F1 실측: 40다이 중 1 일치가 `(9, 9, 1, 1, None)`). 🔴 **절대 수인 것이 의도다** — 비율 바닥은 이 함수가 존재하는 이유인 **부분 맵**에서 가장 먼저 거절된다. ⚠️ **하드코딩은 인지된 미결이다**: 배선 라운드에서 config로 뽑아 올린다(§config-over-hardcode). 🔴 **그리고 이 바닥은 실제 bin 카디널리티에서 발화하지 않는다 — 커밋이 「배선 전에 결판나야 한다」고 명시한 미수리 항목이다** |
| 채점자 | `server/tests/test_bin_fingerprint_shift.py` |

### ⑤ 배치(placement) — 무엇이 맵을 앉혔는가

- `PLACEMENT_ANCHOR`(`"anchor"` — 최소 순번 다이 → 기준 좌상단, **데이터가 정했다**) / `PLACEMENT_SEARCH`(`"shift_search"` — 겹침 최대화 탐색, 포화하면 동점 규칙이 정한다) · 스위치 `ANCHOR_PLACEMENT_ENABLED`.
- **앵커가 왜 안 걸렸는가 — 전건 열거**(「안 걸렸다」 하나로 접으면 조작자가 고칠 곳을 못 찾는다): `ANCHOR_NO_INDEX` · `ANCHOR_NO_REFERENCE` · `ANCHOR_MULTI_MAP` · `ANCHOR_MIN_NOT_UNIQUE` · `ANCHOR_DISABLED` · `ANCHOR_NO_PLACEMENT` · `ANCHOR_SEAT_CORRECTED`. **`None`이면 걸렸다는 뜻이다.**
- **잔차 탐색의 사유**: `RESIDUAL_ANCHOR_HELD` · `RESIDUAL_NO_QUALIFYING_SEAT` · `RESIDUAL_NOT_UNIQUE` · `RESIDUAL_NO_WALK_RANKS` · `RESIDUAL_SEAT_CAP` · 상한 `_RESIDUAL_SEAT_CAP = 4096`.
- 함수: `anchor_cell_of(usable)` · 🆕🆕 **`_anchor_shift(per_candidate, source_indices, cell_owner, reference_top_left, anchor_cell=None, reference_top_right=None)`** · 🆕🆕 `search_pivot_of(usable)` · 🆕🆕 `_placement_payload(linear, anchor_src, anchor_placed, dx, dy)` · 🆕🆕 `first_die_of(cells, left_to_right=True)` · `_residual_shift(...)` · `_CANONICAL_AXES`.
- 🆕🆕 🔴 **[`3dc79e6`·`014b5d3`] 앵커 모서리는 더 이상 좌상단 고정이 아니다 — 후보의 시작 모서리를 따라간다.** 종전에는 평행이동 `t`를 **한 번** 계산해 여덟 후보에 나눠 줬고 기준점이 언제나 좌상단이었다. 🔴 **그래서 `tl`과 `tr`이 *같은 시프트*를 받았고 우상단 시작은 보행 순서만 바꾸는 빈 축이었다**(라이브 실측: 여덟 후보 시프트가 전부 `(-13,-11)`로 동일 — 「시작 모서리 축을 넣었는데 화면이 안 바뀐다」의 원인이 이것이다). 지금은 후보마다 `left_to_right_of(frame)`으로 `reference_top_left` / `reference_top_right`를 고른다. ⚠️ **소스 쪽 앵커(`anchor_cell`)는 안 바뀐다** — 1번 다이가 어느 것인지는 **설비의 번호가 정하는 데이터의 사실**이지 후보의 선택이 아니다. 후보가 정하는 것은 그 다이가 기준의 **어느 모서리**에 앉느냐뿐이다.
- 🆕🆕 **[`8d37cd1`] 앵커 갈래도 자기 모서리를 로그로 말한다** — 후보당 한 줄 `[Align] <frame> ltr=<bool> | SRC#1=<셀> -> REF corner=<셀> | t=<평행이동>`. 🔴 **시프트가 여덟에서 같을 때 그 이유를 바로 말하는 것이 이 줄의 존재 이유다**(위 결함이 로그 없이 이틀 살아남았다).
- 🔬 **소스가 스스로 적어 둔 미해결 어긋남(코드 소관이라 여기서 못 고친다)**: `_RESIDUAL_SEAT_CAP` 주석은 상한에 걸려도 최선을 돌려주는 것처럼 읽히는데, `_residual_shift`가 `RESIDUAL_SEAT_CAP`을 내는 **유일한 가지**는 `if best is None:` 안이라 반환이 `0, 0, 0, obs`다. 자격 자리를 이미 찾은 경우엔 짝을 주지만 **그때는 이 토큰을 내지 않아 「다 못 봤다」가 조용히 사라진다.**

### ⑥ 순번 축의 선언과 진단

- **지표**: `METRIC_INDEX`(= `"index"`)가 `METRIC_OCCUPANCY`/`METRIC_VALUES`/`METRIC_VALUES_WEIGHTED` 옆에 선다. 🔴 **`VALUE_METRICS`에는 안 들어간다.**
- **순번 축 상태 — 전건 열거**: `INDEX_AXIS_ABSENT`(잰 것이 없다) · `INDEX_AXIS_REPORTED`(쟀고 실어 보내되 **순위는 안 냈다** — 문턱 미선언) · `INDEX_AXIS_RANKING`(이 판정의 순위 축이다). 로더 `load_index_thresholds(cfg)` / 완비 술어 `index_thresholds_complete(th)` / config 블록 키 `INDEX_THRESHOLD_BLOCK = "index"`.
- **진단 로그**: `_diag_index_block(per_candidate, out, ruling, source_indices, cell_owner, …)`가 순번 축 전용 블록을 쓴다(`_diag_scoring_block`과 나란히). 파일은 `align.log`(테스트는 `align_test.log`), 회전 상한 `_DIAG_MAX_BYTES` · 백업 `_DIAG_BACKUPS` · 셀 표본 `_DIAG_INDEX_CELLS`. 빌드 신원은 `build_identity()`(`_git_sha`·`_feature_tokens`).
- 🆕 🔴 **[`34d2518`] `compose_refusal`의 `STATE_NO_WINNER` 갈래가 분기 하나를 얻었다** — `ruling["index_axis"] == INDEX_AXIS_ABSENT` **그리고** `ruling["anchor_reason"] == ANCHOR_NO_INDEX`일 때만 마진 문장 대신 *「순번 컬럼에 값이 없어 값 축으로 채점했습니다 …」*를 낸다. 🔴 **「컬럼이 선언됐다」와 「컬럼에 값이 있다」는 다른 사실이고, 마진만 보고하면 조작자가 *안전하지 않은 수리*(문턱 낮추기)로 간다.** ⚠️ **컬럼 이름을 대지 않는 것이 의도다** — 이 함수는 `columns["index"]["column"]`을 받지 않으므로 이름을 적으면 그것은 추측이고, 없는 컬럼을 대며 조작자를 엉뚱한 곳으로 보낸다. 그 밖의 no-winner는 종전 `_ruling_text(ruling)` 그대로.
- 🆕🆕 🔴 **[`97b29da`] `ruling`이 후보별 배치를 나른다 — `ruling["by_frame"]`.** 모양은 `{프레임: {"shift", "anchor", "placement_basis"}}`이고 **`state == STATE_SCORED`인 후보만** 들어간다. **왜 생겼나**: `21209d7`이 「추천이 아닌 후보도 확정할 수 있다」는 문을 일부러 열었는데, `ruling`이 **승자 스코프**라 그 경로가 배치를 못 찾았다. 🔴 **채점기는 여덟 후보 전부에 시프트와 배치를 푼다 — 없었던 것은 배치가 아니라 그것을 나르는 키다.** 소비자는 [`frame_confirmation._placement_of`](#-serverframe_confirmationpy--확정의-기록자). ⚠️ **클라 변경 0건**(클라는 `ruling`을 키를 가리지 않고 얕은 복사한다).
- 🆕🆕 **후보 축 선언이 판정에 실린다 — 네 키 전건 열거**: `sides_considered`(**언제나 `[CANDIDATE_SIDE]`**) · `sides_narrowed`(**언제나 `False`**) · `starts_considered`(순번 모드면 좌·우 둘 다, 아니면 좌상단만) · 후보 행의 `start_corner`. 🔴 **없는 키와 「안 좁혔다」는 받는 쪽에서 같아 보인다** — 그래서 두 `sides_*` 키는 은퇴한 뒤에도 값을 싣고 나간다.
- 🔴 **클라 절반이 있다** — `client2/src/map2/decode.js`의 `INDEX_WALK_READY`/`_ABSENT`/`_TRUNCATED`/`_POOLED`/`_INCONSISTENT` + `decodeIndexWalk`, 색 램프는 `client2/src/map2/index_ramp.js`([§7-A](#7-a--map-editor-2--map_editor2html--client2srcmap2-2026-08-0506-신설)).

---

## 5-G. 🆕🆕 DT·core 프레임 유도 체인 (2026-08-11 신설 등재)

> 🟢 **실측 신규 등재(2026-08-11)** — 아래 전부 **`7097a67`의 커밋된 blob**에서 `def`/`class`/선언을 grep해 확인했다. 🔴 **이 트랙은 이 문서에 한 줄도 없었다** — `a501d6d`·`2ec8e24`·`7097a67`이 서버 파일 둘과 맵퍼 다섯을 새로 들였고, 그중 `dt_map_derivation.py`는 **그전부터** 미등재였다(§5의 `parse_frame` 각주 한 줄이 이 파일을 가리키는 유일한 언급이었다).
>
> 🔴 **`server/mappers/*.py`는 gitignored다 — 추적되는 것은 `.sample`뿐이다.** 아래는 **구조**(모듈·함수 이름과 계약)이고 운영 인스턴스의 값이 아니다. 리빙 문서는 [`DT_CORE_FRAME_CHAINS.md`](./DT_CORE_FRAME_CHAINS.md)(doc-keeper 소관).

### `server/dt_map_derivation.py` (**849줄**) — 프레임 **어휘**와 DT 맵 유도

🔴 **`parse_frame`의 정의가 여기다.** `map_alignment`가 `source_meta_for_frame`과 함께 import하므로 `map_alignment.parse_frame`으로 닿기는 하지만 **정의를 거기서 찾으면 못 찾는다.**

- 🆕🆕 **`_SIDE_OF_TOKEN = {"front": "front", "back": "back", "tl": "front", "tr": "front"}`** — **두 번째 토큰 → 물리 면**의 유일한 사전. 🔴 **`tl`/`tr`은 둘 다 `front`로 푼다**(번호 시작 모서리는 웨이퍼가 뒤집혔다는 주장이 아니다). ⚠️ **`front`/`back`은 계속 받아야 한다** — 걸음 축 이전에 확정된 행이 그 철자를 쥐고 있고 `confirmed_meta_for`가 그것을 읽어 `rotation`/`side`를 쓴다. **시작 모서리 자체는 여기서 안 읽는다** — 그것은 `map_alignment.parse_candidate` 소관이다.
- 어휘·식별: `parse_frame(text)` · `source_meta_for_frame(target_meta, frame_text)` · `identity_columns(target_table)` · `coordinate_columns(target_table)` · `resolve_identity_sources(target_table, confirmed_rule)` · `_forbidden_fallback_columns` · `join_rule(db, name)` / `join_pairs(rule)`.
- 유도·보류·철회: `derive_cells(db, rows, source_table, target_table, source_column, value_columns=None, origin_columns=None, meta_loader=None) -> dict` · `class HoldBack` / `format_holdback_summary(held, derived, elapsed_ms=None)` · `resolve_frame(attribution_row)` / `resolve_frame_candidates(values)` / `load_attribution(...)` / `frame_trigger_scope(db, source_table, filters)` · `plan_retraction(db, target_table, source_column, source_value, derived_keys, max_fraction=DEFAULT_MAX_RETRACT_FRACTION, min_population=DEFAULT_MIN_RETRACT_POPULATION)` / `apply_retraction(db, plan)` / `format_retraction_summary(plan)` · `class DerivationRefused` · `_human_touched_row_ids(db, table_name, row_ids)`.

### 🆕🆕 `server/dt_frame_transform.py` (**96줄**, `a501d6d` 신설) — 프레임을 **축 방정식**으로

**왜 있나**: 확정된 프레임을 매 좌표마다 변환기로 돌리는 대신 **축당 `(base, sign, offset)` 셋**으로 접어 두고 하류(맵퍼·SQL)가 그것을 곱셈 한 번으로 적용한다.

| 심볼 | 시그니처 / 계약 |
|---|---|
| `standard_meta` | `standard_meta(frame_meta: dict) -> dict` — 같은 격자의 **표준(회전 0·front)** 메타 |
| `_axis_equation` | `_axis_equation(transform, origin_x: int, origin_y: int, output_index: int)` — 변환기를 두 점에 먹여 **한 축의 1차식**을 되읽는다 |
| `dt_equations` / `core_equations` | `(frame_meta, basis_meta=None, basis_cells=None) -> dict` — 🔴 **둘 다 `map_overlay.die_mask_from_reference` → `map_overlay.origin_box`로 상자를 세운 뒤** `make_frame_transform(…, source_box, target_box)`를 만든다. **상자를 안 주면 방정식이 다른 원점 위에서 풀린다**(§`origin_box`) |
| `apply_dt_equations` | `apply_dt_equations(x, y, equations: dict) -> tuple[int, int]` — 적용 절반. 필드 이름은 `core_usage_mapper._EQUATION_FIELDS`(`core_x_base`/`core_x_sign`/`core_x_offset` …)와 짝이다 |

### 🆕🆕 `server/alignment_view_service.py` (**85줄**, `7097a67` 신설) — 정렬 뷰 요청의 **해석 절반**

**`main.py`에서 잘려 나온 자리다.** 종전에는 `GET /api/maps/alignment/view` 핸들러가 규칙 조회·`decision_key` 검증·config 로드를 직접 하고 `map_alignment.build_alignment_view`를 불렀다. 지금 라우트는 이 모듈 하나를 부르고 예외를 상태코드로 옮길 뿐이다.

- `class AlignmentViewRequestError(ValueError)` — 🔴 **라우트가 이 예외의 *문자열*로 404/400을 가른다**(`"Enrichment rule '…' not found"`이면 404, 아니면 400). ⚠️ **문구가 계약이다** — 메시지를 고치면 상태코드가 조용히 바뀐다.
- `declared_alignment_rule(rule_name: str) -> dict` — `enrichment_config.load_enrichment_rules(known_tables=crud.TABLE_CONFIG)`에서 이름으로 찾는다.
- `resolve_alignment_view(db, rule_name, key_values, map_table, *, reference_spec=None, include_cells=True, x_col=None, y_col=None, value_col=None, index_col=None, assume_reference_geometry=True, alignment_thresholds=None, source_filters=None, source_table=None, ignore_source_metadata=False) -> dict` — 🔴 **키워드 전용(`*`)이다.** 라우트와 맵퍼가 **같은 진입점**을 쓰는 것이 요점이고, 그래서 체인 맵퍼가 화면과 다른 답을 받을 수 없다.

### 🆕🆕🆕🆕 `server/chain_bindings.py` (**244줄**, `5b09d69` 신설, 추적됨) — job-column 이름의 단일 해석기

**왜 있나 — 6개 맵퍼가 전부 `"dt_job"`을 리터럴로 썼다.** 어떤 것은 `_value(payload, "dt_job")`처럼 맨 문자열로, 어떤 것은 `rule.get("job_column", "dt_job")`처럼 기본값의 절반으로. 운영 컬럼은 **`dt_job_id`**다. 실패는 **양끝 다 침묵**이다 — 읽기 쪽은 `_value(payload, "dt_job")`이 `None`을 돌려주고 맵퍼가 그 행을 건너뛰어 빈 배치+SUCCESS를 기록하고(뒤쪽의 시끄러운 `source.dt_job` `AttributeError`엔 도달조차 안 한다), 쓰기 쪽은 `crud.apply_batch_updates`가 `column_types`에 없는 `updates` 키를 드롭하고 프로세스당 1회 경고 후 200을 반환한다. 스펠링이 다른 배포는 **예외 없이 죽은 체인 셋과 200**을 받는다 — 이 저장소의 어떤 픽스처도 그것을 재현 못 한다(모든 픽스처가 `dt_job`을 쓰므로).

**규칙**: `rule 선언 > table_config 유도 > 이름을 대고 거절`. 리터럴 폴백 없음. `68db020`이 맵 좌표 바인딩에 세운 것과 **같은 전 순서**이고 같은 이유로 관습 폴백을 지웠다 — 아무도 선언한 적 없는 이름이 관습으로 풀리면, 그것은 설정된 답의 탈을 쓴 틀린 답이다.

**테이블 단위이지 체인 단위가 아니다.** 맵퍼 하나가 트리거 payload를 읽고 소스 테이블을 질의하고 타깃 테이블에 쓴다 — 세 테이블이 job column을 **각자 다르게** 부를 수 있고, 그것이 단일 리터럴로는 표현 못 하던 바로 그 경우다. 각 테이블에 자기 이름을 따로 묻고, 규칙이 그 각각을 독립적으로 오버라이드할 수 있다.

**왜 기존 프리미티브를 재사용하지 않는가**: `map_key_columns` 읽기 자체는 기존 프리미티브고 재사용한다 — `dt_map_derivation.identity_columns`가 이미 그것을 읽고 이름을 대고 거절한다. 이 모듈은 그것을 **감싸지, 다시 읽지 않는다**(체인과 dt_map 유도가 "이 테이블의 정체성이 뭔가"에 대해 서로 다른 답을 낼 수 없게). 이 모듈이 더하는 것은 ① 규칙-선언 계층(유도 엔진이 몰라도 되는 체인 config) ② 단일 컬럼 `business_key` 상속(`dt_inventory`처럼 맵이 아닌 행 단위 테이블용). `map_overlay.resolve_binding_parts`(다른 바인딩 해석기)는 **의도적으로 재사용하지 않는다** — 그쪽의 우선순위 기반은 `map_overlay_config.table_bindings`이고 맵 좌표를 답하며, 이 변경이 피하려는 **lot/slot 관습 폴백**을 그대로 갖고 있다.

| 시그니처 | 역할 |
|---|---|
| `class ColumnBindingRefused(ValueError)` | 이름이 무엇이 빠졌는지 **본문에 말하는** 예외. `ValueError`를 상속하는 것이 의도 — 체인 워커는 예외면 무조건 트랜잭션을 중단하고, API 계층은 이미 `ValueError`를 400으로 사상한다(`replace_map` 스코프 거절과 같은 처리) |
| `declared_columns(table) -> set \| None` | `table_config`가 `table`에 선언한 컬럼 이름들, 아무것도 선언 안 했으면 `None`("판단할 수 없다" — 그래서 `table_config`에 없는 테이블은 계속 동작한다) |
| `identity_column(table) -> (column, from) \| (None, why_not)` | ① `map_key_columns`가 **정확히 컬럼 하나**를 이름하면 그 컬럼(맵/단위 소속) ② `map_key_columns`가 없고 `business_key`가 선언 컬럼이며 `composite_key_source`가 없으면 그 business_key(`dt_inventory`처럼 행 1개=job 1개인 테이블) ③ 그 외엔 추측하지 않고 `None` |
| **`resolve_column(rule, key, table, purpose) -> str`** | **주 해석기.** `rule[key]`(선언, 있고 `table_config`에 있으면 승) → 없으면 `identity_column(table)` 유도 → 그래도 없으면 `ColumnBindingRefused`(규칙명·키·테이블·purpose를 문장에 실어 조작자가 코드를 안 읽어도 고칠 수 있게) |
| `resolve_decision_column(rule, key, decision_key, purpose) -> str` | 같은 전 순서이지만 유도 소스가 테이블이 아니라 **정렬 규칙의 `decision_key`** — `len(decision_key) == 1`일 때만 유도 성공(`dt_alignment_metadata_mapper`가 참조 스펙을 job으로 매칭할 때 사용) |
| `model_column(model, table, column, purpose)` | 로드된 ORM 모델에서 그 속성을 찾아 돌려주거나 거절 — 종전의 `hasattr(...) → return {}` 패턴을 대체(그 패턴은 `table_config`와 물리 테이블이 어긋났을 때 **빈 배치를 조용히 성공으로** 기록했다) |
| `ORIGIN_DECLARED` / `ORIGIN_INHERITED` | provenance 어휘(`map_overlay`의 바인딩 provenance와 같은 낱말) — ⚠️ **`ORIGIN_INHERITED`는 선언만 되고 이 파일 안에서 실제로 반환되지 않는다**(`identity_column`이 실제로 돌려주는 origin 문자열은 `_FROM_MAP_KEY_COLUMNS`/`_FROM_BUSINESS_KEY`, 즉 `"table_config.map_key_columns"`/`"table_config.business_key"`) — 죽은 상수인지 예약값인지는 이 패스가 확인하지 못했다 |

### 🆕🆕 체인 맵퍼 5종 (`server/mappers/*.py.sample`) — 선언은 `chain_rules.json`

🔴 **맵퍼 본체는 gitignored**(`server/mappers/*.py`). 아래는 `.sample`이 선언하는 **구조**다. 규칙 이름·트리거·타깃은 `server/config/chain_rules.json.sample` 기준.

| 규칙 (`chain_rules`) | 트리거 → 타깃 | 맵퍼 모듈 / 함수 | 무엇을 하나 |
|---|---|---|---|
| `dt_log_to_dt_alignment_metadata` | `dt_log` → `wafer_map_metadata` | `mappers.dt_alignment_metadata_mapper` / `build_dt_alignment_metadata_batch(db, payloads, rule=None)` | **[`a501d6d`] DT 정렬 메타의 자동화된 절반.** `_automatic_gate(view, rule, …)`가 자동 확정의 문턱을 쥐고, `_reference_geometry_bootstrap_allowed`가 「기준 기하를 합성해도 되는가」를 판정한다(서버 짝은 `map_alignment._allows_synthetic_reference_geometry`). `_placement_for(ruling, winner)` · `_fingerprint(...)`(같은 답을 두 번 쓰지 않기 위한 지문). 🔴 **[`68db020`] 로컬 `_basis_cells_for(db, cfg, reference)`가 삭제됐다 — `_cells_of`를 같은 조건으로 다시 부르는 세 번째 손제작 사본이었다.** 이제 `map_alignment.basis_cells_for(db, reference, cfg)`를 그대로 부른다(인자 순서가 `reference, cfg`로 바뀐 것에 유의 — 옛 로컬 함수는 `cfg, reference`였다). 부수 효과: 읽기 실패가 배치를 통째로 죽이지 않고 그 판만 None으로 건너뛴다(공유 함수의 예외 처리를 그대로 물려받음). 🆕🆕🆕🆕 **[`5b09d69`] `_reference_spec_for(rule, key_values, job_column)`가 세 번째 인자를 얻었다** — 호출자가 `chain_bindings.resolve_decision_column(rule, "reference_job_column", decision_key, …)`로 해석해 넘긴다. 구 리터럴 `rule.get("reference_job_column", "dt_job")`은 다른 철자에서 `None`을 읽어 **모든 job이 폴백 `reference_spec`으로 조용히 떨어졌었다**(어떤 기준으로 채점하는지가 바뀌는 것이지 눈에 보이는 실패가 아니다) |
| `dt_metadata_to_dt_inventory` | `wafer_map_metadata` → `dt_inventory` | `mappers.dt_inventory_metadata_mapper` / `copy_dt_metadata_to_inventory_batch` | 🔴 **`dt_inventory`가 기록의 정본이 되는 자리.** `_reference_geometry(db, metadata, cache)` · `_core_wafer_lists(db, source_table, job_ids, job_column)`. 🔴 **[`68db020`] 이 맵퍼가 바로 `frame_confirmation._basis_cells_for`(당시 private)에 손을 뻗던 그 후계 체인이다** — `frame_confirmation`을 은퇴시키려면 이 맵퍼가 부르던 함수를 먼저 옮겨야 했다. 지금은 `map_alignment.basis_cells_for(db, reference)`를 부른다. 🆕🆕🆕🆕 **[`5b09d69`] `source_job_column`/`target_job_column`을 각각 `chain_bindings.resolve_column`으로 해석** — `_core_wafer_lists`가 4번째 인자 `job_column`을 얻어 `chain_bindings.model_column`으로 거절하고(구 `hasattr` 관용 게이트는 `dt_job`이 없으면 조용히 `{}`를 반환해 모든 job의 `core_wafer_list`가 `[]`로 쓰였다), 출력 키 `updates["dt_job"]`도 `updates[target_job_column]`으로 |
| `dt_inventory_to_standard_dt_map` | `dt_inventory` → `dt_map` | `mappers.dt_standard_map_mapper` / `build_standard_dt_map_batches` | 확정된 프레임의 **축 방정식**(`_EQUATION_FIELDS`)으로 표준 DT 맵을 낸다. 🆕🆕🆕🆕 **[`5b09d69`] 세 테이블, 세 이름** — 트리거(`trigger_job_column`)·소스(`source_job_column`)·타깃(`target_job_column`)을 각각 `chain_bindings.resolve_column`으로 해석해, 타깃 컬럼명이 `replace_map`의 `scope`(`{target_job_column: job_id}`)까지 결정한다. 🔴 **타깃 쪽이 위험한 쪽이다** — 타깃이 선언 안 한 키는 `crud.apply_batch_updates`가 경고 1줄과 함께 드롭하고 200을 반환하므로, 이름이 틀리면 **job 없는 맵**이 조용히 쓰인다 |
| `dt_log_to_primary_core_frame` | `dt_log` → `dt_inventory` | `mappers.core_alignment_mapper` / `build_core_frame_confirmation_batch` | **[`2ec8e24`] core 프레임 유도.** `_primary_group(rows, selector)`(어느 관측을 정본으로 볼 것인가) · `_reference_spec(rule, identity)` · `_automatic_gate(view, rule)` · `_placement(ruling, winner)` · `_equation_basis(ruling, basis_meta, basis_cells)`. 🆕🆕🆕🆕 **[`5b09d69`] `job_column`(소스=트리거, `dt_log`)과 `target_job_column`(타깃, `dt_inventory`)이 갈렸다** — 구 코드는 한 이름을 양쪽에 다 썼다. `chain_bindings.model_column`이 소스 모델의 필터 컬럼을 해석 시점에 확보(`hasattr` 게이트 대체) |
| `dt_inventory_to_core_usage_map` · `dt_log_to_core_usage_map` | `dt_inventory`/`dt_log` → `core_usage_map` | `mappers.core_usage_mapper` / `build_core_usage_map_batches` | **[`7097a67`] 사용 맵.** `_apply_core_equations(x, y, equation)` · `_usage_batches(rows, equations_by_job, source_job_column, target_table="core_usage_map")`(🆕🆕🆕🆕 `source_job_column` 인자 추가) · `_usage_metadata_updates(wafers, frames_by_job, target_table)` · `_canonical_wafer(value)`. 🆕🆕🆕🆕 **[`5b09d69`] 세 테이블 세 이름** — 이 맵퍼는 **두 규칙**(트리거 `dt_inventory` 또는 `dt_log`)을 공유하므로 payload의 job 컬럼명조차 상수가 아니다: `trigger_job_column`(규칙의 `rule.get("trigger_table")`에서 유도) · `source_job_column`(`dt_log` 소스 롤업) · `inventory_job_column`(`dt_inventory` 필터) 셋 다 `chain_bindings.resolve_column` |

- 공통 provenance: `SOURCE_NAME = "chain_ingestion"`(라이브 워커와 **같은 이름** — 사용자 레이어 0이 특별 분기 0줄로 이긴다), `UPDATED_BY`는 규칙별(`chain_alignment` · `chain_core_alignment` · `chain_core_usage`).
- 🆕🆕 **연쇄가 깊어져 워커가 그래프를 검증한다** — `chain_ingestion_worker._validate_chain_cascade_graph(rules)` · `_rule_accepts_event(rule, event)`. 테스트 `server/tests/test_chain_cascade.py`.
- 🆕🆕🆕🆕 ⚠️ **여섯 번째 맵퍼가 이 표 밖에 있다 — `server/mappers/dt_map_mapper.py.sample`.** 이 문서에 **애초에 등재된 적이 없다**(별개의 구 체인 계열: 규칙 `dt_log_to_dt_map`/`dt_job_attribution_to_dt_map`/`eqp_frame_attribution_to_dt_map`이 전부 이 한 맵퍼·한 타깃 `dt_map`을 공유 — 트리거만 셋). `5b09d69`에서 이 파일도 `DEFAULT_SOURCE_COLUMN = "dt_job"` 리터럴 기본값을 지우고 `_rule_source_column(rule)`이 `chain_bindings.resolve_column(rule, "derivation_source_column", _rule_source_table(rule), …)`으로 해석하도록 바뀌었다(그 밖의 함수 전부는 `server/dt_map_derivation.py`로 이미 빠져 있다 — 이 맵퍼 자신은 "어느 행이 이 트리거에 속하는가"만 답한다). **이번에 확인한 것은 이 사실 하나뿐이고, 파일의 나머지 구조(3규칙 공유 이유·`derivation_source_table`)는 여전히 미등재·미검증이다** — 신규 섹션 신설은 이 패스의 지시 범위 밖이었다.

### 🆕🆕 씨앗·프로브 스크립트 3종

| 스크립트 | 줄 | 무엇인가 |
|---|---|---|
| `server/scripts/seed_syn_dt_alignment_samples.py` | **327** | PRD 유효 다이 맵에서 **재현 가능한 DT 정렬 표본 둘**을 만든다 — `SYN-TL-R<rot>-<seed>`(좌상단 시작) / `SYN-TR-R<rot>-<seed>`(우상단 시작), 회전 4종 각각. 🔴 **두 변종의 면은 같은 `front`다 — 우상단 시작은 *순서 규칙*이지 좌표를 거울로 만들지 않는다** |
| `server/scripts/seed_syn_core_defect_jobs.py` | **378** | 뭉친 CORE_DT 결함 맵 하나를 **서로 겹치지 않는 DT 잡 조각들**로 쪼갠다. 🔴 **core 기록 프레임은 DT 회전에서 유도되지 않는 *숨은* 진실이다** — 파생 core 맵을 여기서 쓰지 않는 것이 의도이고, 그래야 정렬이 결함/bin 지문으로 프레임과 오프셋을 **풀어야** 한다 |
| `server/scripts/probe_core_occupancy_alignment.py` | **112** | **읽기 전용** 점유 프로브. 🔴 **체인 맵퍼가 아니고 프레임을 쓰지 않는다** — 자동 확정 계약을 켜기 **전에** 부분/덤프된 core 관측의 수용 근거를 증명하는 자리다 |

---

## 5-H. 정본 원장 canonical ledger

> 🆕⑥ **[2026-08-13 신설 등재]** `server/ledger/` 패키지(11파일) + 읽기 측(`ledger_trace.py`·`ledger_trace_router.py`) + 클라 3종 + 하니스 + 마이그레이션. 설계는 [`docs/architecture/CANONICAL_LEDGER_DESIGN.md`](./CANONICAL_LEDGER_DESIGN.md), 슬라이스 범위는 `docs/process/LEDGER_SLICE_1_BRIEF.md`, 판정은 `docs/process/LEDGER_RULINGS.md`. **이 지도는 그 문서들을 요약하지 않는다 — 소스에 실재하는 심볼만 싣는다.**
>
> 🔬 **측정 기준: `aeddac8`(HEAD)의 커밋된 blob**(`git show aeddac8:<path>` — 워킹트리 아님). ⚠️ **측정 시각에 `server/ledger_trace.py` · `server/ledger_trace_router.py` · `client2/src/ledger_trace.js` · `client2/src/ledger_trace_core.js` · `client2/src/ledger_trace_view.js` · `client2/tests/ledger_trace_harness.mjs` **여섯 파일이 워킹트리에서 modified 상태**였다(다른 두 레인이 편집 중). 아래 값은 전부 **커밋된 상태**이므로, 그 여섯의 다음 커밋이 들어오면 재측정이 필요하다. `server/ledger/**` 11파일은 워킹트리와 blob이 동일했다.
>
> 🔴 **라인 번호는 이 절에 하나도 없다.** 남긴 숫자는 **파일 줄 수**뿐이다. 위치는 `git grep -n "<심볼>" -- <경로>`로 확정하라.

**무엇인가.** `lot_event` 같은 기존 소스 테이블을 **읽어** 봉투 7필드짜리 원자(atom)로 번역해 `ledger_events`에 **추가만** 하는 계보 원장. 쓰기 경로(`crud.apply_batch_updates`·`cell_sources`·체인·그래프)는 **한 줄도 바뀌지 않았다** — 원장은 기존 시스템의 **소비자**로 태어난다.

**결합(실측 · `aeddac8` 전건 grep).** `server/ledger/`를 import하는 곳은 **`server/migrations/add_ledger_events.py`(`from ledger import schema`)와 테스트 5모듈뿐이고, 상시 도는 프로세스는 하나도 없다.** 읽기 측은 별개다 — `server/main.py`가 `import ledger_trace_router` + `app.include_router(...)`를 **CORS 미들웨어 직후·SPA catch-all `@app.get("/{file_name:path}")`보다 한참 위**에서 하고(등록 순서가 계약이다 — 아래로 가면 index.html이 200으로 서빙된다), `ledger_trace_router`가 `ledger_trace`를 import한다. 🔴 **`ledger_trace.py`는 `server/ledger/` 패키지를 import하지 않는다** — 읽기 측은 테이블 이름과 컬럼 이름만 알고 번역기 코드는 모른다.

### `server/ledger/` — 쓰기 측

| 파일 | 줄 | 한 줄 |
|---|---|---|
| `__init__.py` | **27** | 코드 0줄, docstring만. 읽는 순서를 선언한다(vocabulary → envelope → gate → schema → config → lot_event_translator → backfill → observability). ⚠️ 결합 서술 1건이 실측과 어긋난다 — 아래 「소스가 이 절을 반박하는 자리」 |
| `envelope.py` | **264** | 봉투 7필드의 파이썬 표현 + 타입 보존 |
| `vocabulary.py` | **265** | 닫힌 어휘 **7종**과 기계 검사 가능한 시그니처 |
| `uuid7.py` | **123** | 단조 UUIDv7 — `id`이자 워터마크이자 기록 시각 |
| `gate.py` | **306** | 문 앞에서 거절하고 **센다**. 단위는 행이 아니라 **분자(molecule)** |
| `config.py` | **221** | `ledger_config.json` 로더/검증 + 번역기 버전 해시 |
| `schema.py` | **288** | 물리 DDL — **첫날부터 시간 파티션**. 유일한 철자 |
| `store.py` | **349** | 원자 append와 커서 전진을 **한 트랜잭션**으로 |
| `lot_event_translator.py` | **436** | 첫 소스. 두 행 = 한 분자 |
| `backfill.py` | **360** | 커서 루프 + CLI. **분자를 반으로 자르지 않는다** |
| `observability.py` | **180** | 하트비트 note + **2계층 lag 보고** |

#### `envelope.py`

| 심볼 | 무엇인가 |
|---|---|
| `class PayloadNotPreservable(ValueError)` | 왕복에서 타입이 살아남지 못하는 페이로드 |
| `freeze_payload(payload)` | 🔴 **강제 변환이 아니라 거절이다.** 그대로 돌려주거나 raise. 거절 대상 — NaN/Inf(`json.dumps`가 맨 토큰으로 써서 jsonb가 거부) · dict의 **비문자열 키** · JSON 철자가 없는 타입. 「고쳐 주는」 함수는 `"0"`을 `0`으로 만들고 아무도 소스가 뭘 말했는지 못 말하게 만든다 |
| `assert_type_preserving(before, after) -> int` | 스칼라마다 **타입까지** 같은지. 🔴 `==`로는 안 된다 — 파이썬에서 `0 == False`·`1.0 == 1`이라 잡으려는 혼동에서 정확히 통과한다. **검사 개수를 반환**하는 이유는 빈 구조를 훑고 공허하게 성공하는 가드를 호출자가 개수로 잡게 하려는 것 |
| `canonical_keys(keys) -> str` | 구조적 정체성을 **메모 키 하나**로 접는다. 🔴 **저장용 아님** — `subject_keys`는 jsonb로 구조인 채 간다. 값은 프로세스를 나가지 않는다 |
| `entity_ref(entity_type, keys, **qualifiers)` | `{type, keys{...}[, qualifiers{...}]}`. 🔴 **정체성(`keys`)과 서술(`qualifiers`)을 평평하게 만들지 않는다** — `has_wafer`의 `slot`은 qualifier이고, 접으면 다음 사람이 `slot`을 웨이퍼 정체성의 일부로 읽는다 |
| `@dataclasses.dataclass class Atom` | 한 주장. 필드 — `subject_type`/`subject_keys`/`predicate`/`object_kind`/`object_payload`/`occurred_at`/`source_who`/`source_translator_ver`/`source_raw_ref`/`supersedes` + **컬럼이 되지 않는 셋** `molecule_ref`(비의미 상관 마커 — 게이트만 읽고 버린다) · `derivation`(선언된 규칙 이름 — 원자성 검사 ③의 기계 형태) · `id` |
| `Atom.ensure_id()` | 워터마크를 찍는다. 🔴 **`__post_init__`이 아닌 것이 의도** — 구성 시각에 채번하면 「번역기가 만든 순서」로 정렬되고 거절된 분자가 id를 태운다. **쓰기 직전에** 한 번 |
| `Atom.identity() -> tuple` | 「같은 주장인가」 — `schema.DEDUPE_COLUMNS`의 **파이썬 측 거울**이지 키 자체가 아니다. 해시 키를 쓰지 않는 이유는 파이썬과 jsonb의 JSON 철자가 달라 **조용히** 안 맞기 때문 |
| `Atom.describe() -> str` | 운영자 로그용 한 줄. **소비자가 파싱할 것 아님** |
| `ROW_COLUMNS` | 물리 insert의 컬럼 순서 **11개**(`id`…`supersedes`) 한 튜플. writer와 마이그레이션이 같은 것을 쓰므로 한쪽에만 컬럼을 더하면 **문법 오류**가 되지 조용히 밀리지 않는다 |
| `check_envelope(atom) -> list` | 어휘와 무관하게 **모든** 원자에 묻는 것 — 세계 시각이 있는가(aware `datetime`인가) · 출처가 있는가 · 원 발화로 돌아갈 경로가 있는가 · 페이로드가 보존 가능한가 |

#### `vocabulary.py`

| 심볼 | 무엇인가 |
|---|---|
| `OBJECT_KINDS` | `frozenset({"value","entity_ref","event_ref"})` — 이 슬라이스에 핀된 목적어 종류 |
| `ENTITY_TYPES` | **5종** — `Lot`/`Wafer`/`Product`/`Equipment`(전부 `class="issued"`) + `Die`(`class="composed"`, keys `wafer,x,y`). 🔴 **`Die`는 register를 받지 않는다** — 구성으로 존재하므로 등록하면 원자가 1.6억 개 |
| `ISSUED_TYPES` | `ENTITY_TYPES`에서 유도(파생값이지 두 번째 목록이 아니다) |
| `PREDICATES` | 🔴 **v0는 일곱이고 그 수가 통제다.** canonical — `register`(목적어 ∅) · `pin` · `same_as`(reserved). ontology — `derived_from` · `slot_map`(qualifiers `from`/`to`/**`wafer`**) · `has_wafer`(qualifier `slot`) · `frame_confirmed`(reserved). 각 항목이 `status`/`since`/`layer`/`subject`/`object`/`qualifiers`/`unit`/`semi_ref`/`superseded_by`를 든다 |
| `EMITTABLE` | `status == "active"`인 것만. `reserved` 둘(`same_as`·`frame_confirmed`)을 오늘 방출하면 **미선언 어휘 거절** |
| `PROJECTION_ONLY_WORDS` | `{resolved, contested, candidate, unresolvable, pinned}` — 프로젝션의 상태어. 🔴 **게이트가 이름을 대고 거절하라고** 여기 적혀 있다 |
| `is_declared(predicate)` / `signature(predicate)` | 조회 둘 |
| `check_signature(predicate, subject_type, object_kind, object_payload) -> list` | 위반 목록. **순수** — 연결도 상태도 로그도 없다. 세는 것과 알리는 것은 게이트 소관 |
| `check_subject_keys(subject_type, subject_keys) -> list` | 주어 정체성이 **구조적·완전·비공백**인가. 문자열은 거부. 설계 §3의 사건(접합 키가 한 조각이 비자 `a_b`→`a`로 붕괴, 17만 행) |
| `requires_register(entity_type) -> bool` | issued면 참 |
| `register`의 `object_kind IS NULL` | 🔴 **이 구현이 핀된 계약이 안 정한 것을 정한 유일한 자리.** enum에 ∅ 철자가 없어서 네 번째 값을 만들지 않고 NULL을 쓰며, DDL의 CHECK가 `register`에만 그것을 허용한다 |

#### `uuid7.py`

| 심볼 | 무엇인가 |
|---|---|
| `uuid7() -> uuid.UUID` | 🔴 **구성으로 단조**(희망이 아니라). `rand_a` 12비트를 밀리초 내 카운터로 쓰고(`_COUNTER_BITS = 12`), 넘치면 **미래에서 빌려** `_last_ms`를 하나 전진, **벽시계가 뒤로 가면 이전 밀리초를 유지**한다. 스레드 안전(난수도 락 안에서 뽑는다 — 밖에서 뽑으면 두 스레드가 같은 `(ms, counter)` 접두를 임의 꼬리 순서로 낸다) |
| `timestamp_ms(value) -> int` | 박힌 48비트 밀리초. 🔴 **`recorded_at` 컬럼이 없는 이유가 이것** — 있으면 한 질문에 답이 둘 |
| `assert_monotonic(values) -> int` | 엄격 증가가 아니면 raise, **검사 개수 반환**. 빈 시퀀스를 훑고 공허하게 통과하는 가드는 이 프로젝트가 이미 한 번 출하했다 |

#### `gate.py`

| 심볼 | 무엇인가 |
|---|---|
| 거절 어휘 **11종** | `REFUSE_UNDECLARED_SOURCE`(`"undeclared_source"`) · `REFUSE_UNDECLARED_VOCABULARY` · `REFUSE_NO_TIME_DECLARATION` · `REFUSE_MISSING_OCCURRED_AT` · `REFUSE_NO_IDENTITY` · `REFUSE_NOT_TRUE_ALONE` · `REFUSE_ATOMICITY` · `REFUSE_UNDECLARED_DERIVATION` · `REFUSE_NO_RAW_REF` · `REFUSE_PAYLOAD_NOT_PRESERVABLE` · `REFUSE_AMBIGUOUS_PAIR`. **번호가 아니라 이름인 것**은 `chain_key_gate.REFUSAL_UNKEYED_ROW`와 같은 이유 |
| `REFUSAL_REASONS` | 위 11종의 frozenset. **닫힌 집합**이고 `refuse()`가 밖의 사유를 `ValueError`로 거부한다 — 호출부에서 지어낸 사유는 아무도 도표로 못 그린다 |
| `MAX_REFUSAL_SAMPLES = 20` · `_ANNOUNCE_AT` · `_NOTE_TOP_N = 5` | 상세는 상한, **카운트는 무제한**. 공지는 1·10·100·…번째에서 WARNING, 그 밖은 INFO |
| `refusals()` / `atoms_lost()` / `rows_refused()` / `incomplete_molecules()` / `samples()` | 프로세스 수명 카운터의 **사본**. 🔴 **`atoms_lost`만으로는 거짓말이 된다** — 원자가 만들어지기 **전에** 거절된 분자(미선언 event_type·파싱 불가 시각·모호한 짝)는 여기 0을 보태고 그 행이 낼 것을 전부 잃는다. 그래서 **거절된 소스 행 수**를 따로 센다. 이 모듈 자신의 첫 결함이 그것이었다(실측 1행 거절 · 26원자 미기록 · `atoms_lost=0`) |
| `note()` | 하트비트 다이제스트, **깨끗하면 `None`**. 🔴 `None`이 하중을 진다 — 건강한 배포의 하트비트는 조용하므로 **줄이 나타나는 것 자체가 신호**다(`chain_key_gate.note()`와 같은 규약) |
| `record_incomplete(source, count=1)` | 🔴 **거절이 아니다.** 소스 행 일부만 도착한 분자 — 도착한 행은 참을 말하므로 버리면 증거가 사라진다. 「사슬에 구멍이 있다」를 설명하는 수 |
| `reset_counters()` | 테스트 전용 |
| `refuse(source, reason, detail, atoms=0, rows=1)` | 원자가 **아예 안 생긴** 것의 거절. 가짜 원자를 지어 거절받게 하는 것보다 진입점 둘이 낫다는 판단 |
| `screen_molecule(source, atoms, declared_derivations, molecule_ref=None, source_rows=1) -> (kept, report)` | 🔴 **전부 아니면 전무.** 나쁜 원자 하나가 **분자 전체**를 거절시키고, writer는 원자가 아니라 분자를 받으므로 **조각을 쓸 수 있는 호출 경로가 없다.** 검사 순서 — derivation 선언 여부 → 주어 정체성 → 시그니처 → 봉투 → `molecule_ref` 소속. `declared_derivations`가 비면 전부 거절되고 **그 방향이 옳다**(규칙을 하나도 선언 안 한 소스는 원자를 못 만들어야 한다). 원자 0개는 거절이 아니다(빈 wafer 컬럼의 `track_in`은 정당하게 아무것도 안 낸다) |

#### `config.py`

| 심볼 | 무엇인가 |
|---|---|
| `CONFIG_FILENAME = "ledger_config.json"` | `server/config/`(gitignored). `.sample`이 tracked이고 **실값은 이 문서에 옮기지 않는다** |
| `SLOT_PAIRING_STRATEGIES` | `{shared_wafer, slot_preserving, none}`. 🔴 오타가 조용히 `none`으로 떨어지면 **slot 사슬 없는 원장 + 무민원**이 되므로 기동 오류로 만든다 |
| `LINEAGE_STRATEGIES` | `{parent_child, none}` |
| `DEFAULT_OCCURRED_AT_FORMAT = "%Y-%m-%dT%H:%M:%S"` | 제품 소유자 판정(2026-08-13) — fab 타임스탬프는 `T` 구분자 ISO 8601. 리터럴을 호출부마다 두지 않는 이유는 번역기와 lag 보고가 **둘 다** 이 기본값으로 떨어지기 때문 |
| `class LedgerConfigError(ValueError)` | **로드 시점에만** raise |
| `config_path(filename=CONFIG_FILENAME)` / `_config_dir()` | `paths.CONFIG_DIR` 경유, import 실패 시 파일 기준 폴백 |
| `load(path=None) -> dict` | 라이브 파일이 없으면 `<name>.sample`로 폴백(운영자 config의 프로젝트 관례). `__origin__`을 심어 거절 문장이 어느 파일을 말하는지 밝힌다 |
| `validate(cfg, origin="<memory>")` | 번역기가 **추측해야 할 것**을 전부 거절한다 — `occurred_at_column` 미선언 거절(도착 시각으로 대체 금지) · `occurred_at_timezone` 미선언 거절 · `subject_type ∈ vocabulary.ENTITY_TYPES` · `vocabulary` 빈 맵 거절 · 규칙별 `lineage`/`slot_pairing` 어휘 검사 + **`slot_pairing != none`인데 `lineage == none`이면 거절**(짝이 될 두 랏이 없다) · `columns`에 **`lot`·`event_type`·`slots`·`wafers`·`parent_lot`·`child_lot`·`row_identity` 7종** 필수 · `batch.molecules_per_transaction >= 1` |
| `source_config(cfg, source)` | 없으면 `None`이고 **`None`은 기본값이 아니라 거절 신호** |
| `translator_version(cfg, source) -> str` | `<source>/<config version>/rules:<8 hex>`. 🔴 해시가 **그 소스 선언 전체**를 덮으므로 `slot_pairing` 규칙이 다른 두 박스는 **출처가 눈에 보이게** 다른 원자를 낸다 |
| `declared_derivations(cfg, source) -> frozenset` | 선언**으로부터 조립**한다(옆에 나열하지 않는다) — 항상 `positional_row`, `lineage=="parent_child"`면 `pair_field`, `slot_pairing != none`이면 그 전략 이름 자체, `emit_register`면 `first_sight` |

#### `schema.py`

| 심볼 | 무엇인가 |
|---|---|
| `LEDGER_TABLE = "ledger_events"` · `CURSOR_TABLE = "ledger_translator_cursor"` | |
| `DEDUPE_COLUMNS` | 유일 인덱스가 비교하는 **7컬럼**(`occurred_at`, `predicate`, `subject_type`, `subject_keys`, `coalesce(object_payload,'{}'::jsonb)`, `source_translator_ver`, `source_raw_ref`). 🔴 **해시 키가 아니라 컬럼인 이유** — 해시는 파이썬(쓰기)과 PostgreSQL(인덱스 식)이 같게 계산해야 하는데 둘의 JSON 철자가 다르고, 어긋나면 **모든 행이 새것으로 보이며 조용히** 실패한다. `coalesce(...)`인 이유는 PG 15 이전에서 인덱스의 NULL이 서로 **구별**되기 때문(동일한 `register` 둘이 다 통과한다) |
| `CREATE_LEDGER` | 11컬럼 + CHECK **5종**(`ck_ledger_object_kind` · `ck_ledger_register_has_no_object`(양방향) · `ck_ledger_objectless_has_no_payload` · `ck_ledger_subject_keys_is_object` · `ck_ledger_no_self_supersede`) + `PRIMARY KEY (id, occurred_at)` + **`PARTITION BY RANGE (occurred_at)`** |
| `CREATE_CURSOR` | `source`(PK) · `translator_ver` · `cursor_value`(jsonb) · `molecules_done`/`atoms_written`/`atoms_deduped`/`molecules_refused`/`incomplete_molecules`(BIGINT) · `source_head`(jsonb) · `head_probed_at` · `started_at` · `updated_at` |
| `INDEXES` | **3종, 그리고 소비자 이름이 있는 것만 넣는다는 것이 admission rule이다.** `uq_ledger_atom`(멱등성 — `store.insert_atoms`의 `ON CONFLICT DO NOTHING`) · `idx_ledger_subject_lot`(`(subject_keys->>'lot'), predicate` — **`server/ledger_trace.py`의 walk**. 🔴 부모에 선언해 아직 없는 파티션까지 cascade) · `idx_ledger_register`(PARTIAL, `WHERE predicate='register'` — `store.existing_registrations`). 🔴 **소스 주석이 기각된 후보 3종을 가격과 함께 남긴다**(`idx_ledger_type_pred_time` · `idx_ledger_subject_gin` · `idx_ledger_id`) — 되살리는 것이 새 추측이 아니라 숫자 붙은 결정이 되도록 |
| `month_bounds(when)` / `partition_name(when)` / `create_partition_sql(when)` | UTC로만 계산하고 경계에 **명시 오프셋**을 쓴다. 오프셋 없는 경계는 **세션의 TimeZone**으로 해석돼 두 프로세스가 안 맞는 파티션을 만들고, 틈에 떨어진 행은 insert 자체가 실패한다 |
| `ensure_schema(connection)` | 테이블 둘 + 인덱스. **DROP 없음, 기존 것의 ALTER 없음**, 끝에 한 번 commit |
| `ensure_partition(connection, when, known=None)` | 🔴 **자기 트랜잭션에서 돌고 반환 전에 commit한다** — 원자 트랜잭션 안에서 실패하면 분자까지 롤백돼 운영자가 DDL 문제를 **원자성 거절**로 읽는다. `SET LOCAL lock_timeout='20s'`가 두 번째 그물이다: `CREATE TABLE … PARTITION OF`는 **부모에 ACCESS EXCLUSIVE**를 잡으므로 같은 프로세스의 열린 리더 뒤에 줄을 선다(이 레인의 첫 실행이 실제로 자기 자신에 막혀 몇 분을 섰다). 자기 차단은 **매달리지 말고 실패해야** 한다 |
| `ensure_partitions_for_range(connection, first, last)` / `partitions(connection)` | 월 범위 일괄 · 파티션 목록(보고와 헬스체크용) |
| `_relation_exists(cursor, name)` | DDL 전 카탈로그 관문. 실패한 DDL은 트랜잭션을 오염시켜 **그 뒤 모든 질의가 무관한 이유로** 실패한다 |

#### `store.py`

| 심볼 | 무엇인가 |
|---|---|
| `INSERT_PAGE_SIZE = 1000` | `crud.py`가 쓰기 경로에서 이미 잰 청크 상수와 같은 값 |
| `class LedgerStore(engine, who="ledger")` | 🔴 **연결은 `engine.raw_connection()`에서만 온다.** `database.database`가 Engine 클래스에 `db_safety` 가드를 설치하고, **raw `psycopg2.connect`는 그 가드를 그냥 지나친다** |
| `LedgerStore.connection()` / `ensure_schema()` / `ensure_partitions(connection, occurred_ats)` | |
| `LedgerStore.existing_registrations(connection, subjects)` | `(subject_type, canonical_keys_json)` 집합 → 같은 모양의 집합. **페이지당 1질의**(엔터티당 조회는 1천만 행 백필을 2차식으로 만든다). `idx_ledger_register`가 존재하는 이유 |
| `LedgerStore.insert_atoms(connection, atoms) -> (attempted, inserted)` | `execute_values` 다중행 INSERT + `ON CONFLICT DO NOTHING`. 🔴 **두 수를 절대 합치지 않는다** — `attempted > inserted`는 「커서가 이미 끝난 일을 통과시켰고 인덱스가 알아봤다」는 뜻이고 운영자가 그걸 볼 수 있어야 한다. **commit하지 않는다** |
| `LedgerStore.read_cursor(connection, source)` | 커서 행을 dict로 |
| `LedgerStore.write_batch(source, translator_ver, atoms, cursor_value, molecules, refused=0, incomplete=0)` | 🔴 **원자 단위.** 원자 append + 커서 전진 + **commit 한 번**, 아니면 전무. 카운터는 **SET이 아니라 누적**이다(SET은 이 시스템에서 이미 결함이었다 — QA D-1) |
| `LedgerStore.atom_count()` / `census()` | `{predicate: count}` — 보고와 백필 로그가 인용하는 수 |
| `LedgerStore.record_source_head(source, head_value)` | **자기만의 작은 트랜잭션.** lag 프로브가 원자 배치를 롤백시킬 수 있으면 안 된다 |
| `_candidate_formats(fmt)` | `@lru_cache(maxsize=32)`. 선언된 형식 하나에 대해 읽어 줄 모양들 — **넓히는 것은 둘뿐이다**: ① 날짜/시각 **구분자**(`T` ↔ 공백, RFC 3339 §5.6). 🔴 문법이 아니라 구분자를 넓히는 것이고, 이 목록 아래에서 **두 가지로 읽히는 문자열은 없다** ② 후행 오프셋(`%z`는 `strptime`에서 선택적이지 않아 두 모양이 **서로소** — 그래서 선호 순서가 아니라 조회다) |
| `parse_occurred_at(raw, fmt, tzname)` | 실패는 `None`이고 **`None`은 호출자에게 거절 신호이지 `now()`로 대체할 면허가 아니다**. 🔴 **소스가 든 명시 오프셋이 이기고, 선언된 zone은 naive 값에만 적용된다** |
| `_zone(tzname)` | 해석 불가 zone은 raise. **UTC로 조용히 폴백하지 않는다** — 모든 `occurred_at`이 오프셋만큼 밀린다 |

#### `lot_event_translator.py`

| 심볼 | 무엇인가 |
|---|---|
| `SOURCE = "lot_event"` | |
| `class Molecule` | `__slots__ = ("event_type","event_time","parent","child","ambiguous","rows")`. 🔴 **한 split/merge는 소스 행 *둘*이고 그 쌍이 분자이자 트랜잭션 단위다** — 소스에 이벤트 id가 없어 `(event_type, event_time, parent, child)` **넷 전부**로 짝짓는다(두 랏이 같은 순간에 움직일 수 있다). `ref`(비의미 상관 마커) · `is_complete` · `parent_row()` / `child_row()` |
| `molecule_key(row)` | `(event_type, event_time, parent, child, ambiguous)`. 한 행은 짝의 **한쪽**을 대고 다른 쪽을 유도한다. 🔴 **양쪽을 다 채운 행은 자기 행 정체성을 키에 실어 아무 분자에도 못 낀다** — 라이브 DB에 실재한다(그리드 손편집으로 `child_lot`이 들어갔다). 「parent 먼저 보고 없으면 child」류 순서는 그 행의 웨이퍼 25장을 **소스가 주장한 적 없는 계보에** 조용히 붙인다 |
| `group_molecules(rows)` | 커서 순서를 보존한 채 분자로 묶는다 |
| `class LotEventTranslator(source_cfg, translator_ver, declared_derivations, who=SOURCE)` | 등록 메모(`registered`)만 런 스코프 캐시. `store.existing_registrations`로 배치마다 씨를 받고 런 중에 자란다 |
| `LotEventTranslator.translate(molecule) -> (atoms, report)` | 🔴 **게이트를 통과하기 *전*의 원자다.** `(None, report)`는 원자가 생기기 전에 거절됐다는 뜻(모호한 짝 · 미선언 `event_type` · 파싱 불가 시각 · 정체성 없음). 방출 순서 — `register`(정렬된 lot) → `has_wafer`(행의 위치쌍) → `derived_from`(행 자신의 parent/child 필드) → `slot_map`(선언된 전략) |
| `LotEventTranslator._positional_pairs(row)` | `[(slot, wafer)]`, 길이가 다르면 **분자 전체 거절**. 🔴 방어적 정돈이 아니다 — 불균등 짝짓기는 아무 데서도 raise하지 않고 **웨이퍼를 틀린 슬롯에 재배정한 채 형태만 멀쩡**하다 |
| `LotEventTranslator._slot_map(molecule, strategy, occurred_at)` | `slot_preserving` — 선언된 **관습**. 자식 행의 `(slot, wafer)`마다 `from == to`. split에서도 도는 유일한 갈래. `shared_wafer` — **추론 0**. 양쪽 행이 **같은 웨이퍼 id를 발화한 자리에만** 짝. 소스가 침묵하면 아무것도 안 낸다 |
| `raw_ref(rows) -> str` | `lot_event:["<row id>", …]` — 재번역으로 가는 **유일한** 경로. 🔴 구분자 join이 아니라 **JSON 배열**인 이유는 소스 행 정체성(`business_key_val`)이 이미 `lot\|event_type\|event_time`이라 뻔한 구분자를 품고 있어서다. 정렬하므로 매 실행 동일 → 유일 인덱스가 재번역을 알아본다 |
| `source_translator_ver`의 `#<derivation>` 접미 | 🔴 **열두 번째 컬럼을 만들지 않고 관습을 질의 가능하게 만든 자리.** `WHERE source_translator_ver LIKE '%#slot_preserving'`이 「선언된 관습에 기대는 원자」와 「소스가 대놓고 발화한 원자」를 가른다. **읽기 측 `ledger_trace.claim_basis`가 정확히 이 접미를 읽는다** |

#### `backfill.py`

| 심볼 | 무엇인가 |
|---|---|
| CLI | `conda run -n assy_manager python -m ledger.backfill --source lot_event` · `--reset-cursor` · `--from` · `--fetch-rows` · `--max-batches` · `--config` |
| `DEFAULT_FETCH_ROWS = 2000` · `class BackfillResult(dict)` · `_bootstrap_path()` | |
| `fetch_page(connection, source, columns, after, limit)` / `fetch_group(connection, source, columns, event_time)` | 논리 이름으로 별칭한 dict를 낸다 — **번역기는 물리 컬럼명을 못 본다**. 두 번째 함수는 한 페이지보다 큰 `event_time` 그룹의 탈출구 |
| `_cut_on_group_boundary(rows, page_limit)` | 🔴 **커서는 행 오프셋이 아니라 `event_time`이고, 배치는 언제나 `event_time` 그룹의 정수 개다.** 페이지가 찼으면 **마지막 그룹을 버린다**(잘렸을 수 있고 페이지 안에서는 알 방법이 없다). 반환은 `(complete_rows, trailing_event_time_or_None)` |
| `run(engine, cfg, source="lot_event", fetch_rows=DEFAULT_FETCH_ROWS, reset_cursor=False, start_from=None, max_batches=None, probe_lag=True)` | 🔴 **쓰기 전에 읽기 트랜잭션을 끝낸다(`read.rollback()`)** — psycopg2가 첫 SELECT에서 암묵 트랜잭션을 열고 유지하므로 이 연결이 `ledger_events`에 ACCESS SHARE를 쥔 채 idle-in-transaction으로 앉고, 루프의 첫 쓰기가 `CREATE TABLE … PARTITION OF`(ACCESS EXCLUSIVE)라서 **프로세스가 자기 자신에 영원히 막힌다.** 이 레인의 첫 실행에서 실제로 발생 |
| `_forget_registers(translator, atoms)` | 🔴 거절된 분자는 **등록 메모를 남기면 안 된다** — 아무것도 안 쓰였으므로 같은 lot을 말하는 다음 분자가 등록할 수 있어야 한다 |
| `_flush(store, source, translator_ver, atoms, cursor_value, molecules, refused, incomplete, result)` | `store.write_batch` 한 번 = 배치 하나 |
| `beat(result)` | `utils.heartbeat.beat("ledger", note=observability.note(...), force=True)`. `force`인 이유는 스로틀이 빠른 루프를 막으려는 것이지 **한 런이 내는 유일한 비트를 버리라는 것이 아니기** 때문 |
| 멱등성 그물 **둘** | ① **커서** — 두 번째 런은 0행을 읽는다 ② **`uq_ledger_atom`** — 커서를 리셋하면 행은 읽히고 원자도 만들어지지만 DB가 하나도 받지 않는다. 🔴 **한쪽만 고치고 성공을 보고한 전례**가 있어 `test_ledger_l1_pg.py`가 둘을 **따로** 채점한다 |
| ⚠️ 커서가 `event_time`인 대가 | **세계 시각이라 늦게 도착한 오래된 행은 커서 뒤에 떨어지고 이 백필이 못 본다.** 일회성 백필에는 허용, **뒤따르는 라이브 구독에는 허용 안 됨**(그쪽은 outbox 구동이어야 한다). `--from`이 임의 구간을 다시 돌린다 |

#### `observability.py`

| 심볼 | 무엇인가 |
|---|---|
| `note(extra=None)` | `gate.note()` + 추가분. 조용하면 `None` |
| `lag_note(lag)` | 🔴 **거절 note와 달리 항상 낸다** — 「0만큼 뒤처졌다」는 운영자가 봐야 할 정보이고, **그 부재**가 그래프 워커의 결함 모양이었다 |
| `lag_report(store, source, source_cfg, cursor_row, probe_interval=60, now=None, force_probe=False)` | **2계층이고 그것이 규모 결정이다.** Tier 1(항상, **질의 0**) — `world_time_lag_seconds` · `cursor_age_seconds`, 둘 다 호출자가 이미 든 커서 행에서 나온다. Tier 2(스로틀, 질의 1) — 진짜 소스 head와 그 뒤 행 수. 🔴 명백해 보이는 「내 커서 뒤 소스 행 수」는 `lot_event`에 `event_time` 인덱스가 없고 이 레인은 **그것을 추가할 수 없어서**(§6: 기존 스키마 무접촉) 1천만 행에서 순차 스캔이다. **`probe_allowed`를 숫자와 함께 보고**하는 이유는 「안 뒤처졌다」와 「안 물어봤다」를 접으면 lag 보고가 누락으로 거짓말을 시작하기 때문 |
| `probe_source_head(store, source, source_cfg, position)` | `(head_event_time, rows_behind)` — **한 문장**에서 둘 다(두 문장은 인덱스를 못 거는 테이블의 두 스캔이다) |
| `reset_probe_throttle()` | 테스트 전용 |
| `cursor_row is None` | 🔴 **`never_started=True`** — 「무한히 뒤처짐」이고, 이것을 0 lag로 보고하는 것이 첫날에 재현한 그래프 워커의 결함이 된다 |

### `server/migrations/add_ledger_events.py` (**96줄**)

운영자 진입점. `main(argv=None)` · `report(connection)` · 플래그 `--report`(아무것도 안 바꾸고 존재만 출력) · `--months N`(파티션 미리 생성). 🔴 **DDL은 여기 없다** — `ledger.schema`의 함수를 부른다(테스트가 스크래치 스키마에 **같은** 테이블을 지을 수 있어야 하고, 마이그레이션에 DDL 사본이 있으면 테스트가 **닮은 것**을 검증하게 된다). `report`의 인덱스 질의가 `pg_indexes.tablename`이 아니라 **`to_regclass`가 실제로 해석한 스키마로 한정**한다 — 안 하면 같은 이름의 테이블을 가진 모든 스키마의 인덱스가 나와 독자가 중복이라 결론짓는다(이 박스에 스크래치 스키마가 실제로 있다).

### `server/ledger_trace.py` (**1,179줄**) — 읽기 측

🔴 **셋이 살고 그중 둘은 서로를 몰라야 한다.** ① **RESOLUTION** — `claim_class`/`claim_rank_key`/`resolve`. `Claim` 객체 위의 순수 파이썬, **SQL도 테이블 이름도 연결도 없다.** ② **LOOKUP** — `ClaimLookup`과 하위 클래스. 가져오기만 하고 **순위도 판정도 계급도 모른다.** ③ **WALK** — `trace`. 룩업에 한 번 묻고 홉마다 해결기에 한 번씩 묻는다.

**분리가 취향이 아니라 구조 요구인 이유(실측 2026-08-12, 1000랏 합성 프로브 — 운영 증거 아님):** 질의 시점 해결은 **랏 단위**에서는 성립하고(0.95 ms/홉) **슬롯 단위**에서는 무너진다(인라인 452 ms 대 머티리얼라이즈 0.58 ms). 이 슬라이스는 랏 단위라 질의 시점으로 가고 **아무것도 머티리얼라이즈하지 않는다.** 그래서 룩업이 교체 가능한 객체다 — 클로저 테이블 기반 룩업으로 바꾸는 것은 **생성자 인자 하나**이고 해결기는 한 줄도 안 고친다.

| 심볼 | 무엇인가 |
|---|---|
| `LINEAGE_PREDICATES` | `("derived_from","slot_map","has_wafer","register")` — walk가 읽는 v0 어휘. **개수 대신 이름으로 고정한다** |
| `DEFAULT_MAX_DEPTH = 20` | 멈추고 **멈췄다고 말하는** 깊이. `terminal_reason` 없는 상한은 뿌리와 구별 불가 |
| `@dataclass(frozen=True) class Claim` | `ledger_events` **컬럼명 그대로**. 🔴 confidence도 priority도 processed 플래그도 **더하지 않는다** — 우선순위는 해결기 config 소관이고 실제로 거기 있다. 프로퍼티 `subject_lot` |
| `DEFAULT_RESOLVER_CONFIG` | 계급표는 `if` 사다리가 아니라 **선언 데이터**. 키 — `pin_predicates` · `confirmed_predicates` · `confirmed_sources` · `confirmed_payload_flag` · `inference_sources` · `inference_payload_flag` · **`inference_derivations`**(기본 `["slot_preserving"]`) · **`display_timezone`**(기본 `"Asia/Seoul"`) |
| `RESOLVER_CONFIG_FILENAME = "ledger_resolver.json"` · `load_resolver_config(force_reload=False)` · `set_resolver_config(config)` | 파일은 **선택**이고 없으면 기본값. 🔴 **모르는 키가 있으면 `ResolverConfigError`** — 반만 적용하지 않는다. `set_resolver_config`는 테스트용 |
| `class ResolverConfigError(RuntimeError)` | 라우터가 **503**으로 번역한다 |
| `CLASS_PIN=0` · `CLASS_CONFIRMED=1` · `CLASS_OBSERVATION=2` · `CLASS_INFERENCE=3` · `CLASS_NAMES` | 설계 §6의 네 계급 |
| `is_convention_backed(claim, config=None)` | 이 원자의 내용이 **선언된 가정**에 기대는가. `source_translator_ver`의 `#<derivation>` 접미를 읽어 판정 — 열두 번째 컬럼도, 사실이 사는 두 번째 자리도 없다 |
| `claim_class(claim, config=None)` | 🔴 **선언된 관습 아래 내려진 결론은 관습이 아무리 좋아도 INFERENCE다.** 그래야 나중의 진짜 관측이 **자동으로** 이긴다 — 아무도 pin을 풀지 않고. 관습을 관측으로 매기면 config 가정이 실측을 앞서고, 그것이 레이어링 가치가 막으려는 바로 그 역전이다(수동 > 자동의 일반형: 실측 > 가정) |
| `claim_rank_key(claim, config=None)` | 🔴 **`crud.compute_priority_value`와 *같은 연산이고 일부러 같은 모양*이다** — 최외곽이 권위 계급이고 tie-break는 전부 **그 안쪽에 봉인**된 사전식 튜플. 「tie-break가 낮은 권위를 높은 권위 위로 올릴 수 없다」가 검토자의 기억이 아니라 **구성으로** 참이 된다. 5레벨 — 0 계급 · 1 등록 우선순위(**`crud.get_source_priority`를 *부른다*** — 두 번째 서열 맵을 만들지 않는다) · 2a 날짜 있는 것이 없는 것을 이긴다 · 2b `occurred_at` 내림차순 · 3 event id 오름차순. 🔴 **(2b, 3)이 함께 전순서인 근거가 「id가 유일 PK라서」가 아니다** — 파티션 테이블은 파티션 키가 모든 유일 제약에 있어야 해서 PK는 `(id, occurred_at)`뿐이다. 둘 다에서 비기면 PK 위반이므로 **전순서가 DB가 강제하는 것에 기댄다** |
| `claim_basis(claim)` | `source_translator_ver`의 `#<derivation>` 접미를 **그대로** 돌려준다. 🔴 **여기서 분류하지 않는다** — 어느 derivation이 관습인지는 번역기 config의 지식이고, 목록을 이 모듈에 복사하면 소스가 하나 늘 때 낡는 두 번째 철자가 된다 |
| `_crud()` / `_registration_priority(source_who)` / `_occurred_epoch(claim)` | `database.crud`를 **지연 import**한다(ORM 세션 없는 워커도 이 모듈을 import할 수 있어야 한다). 🔴 **철자 하나, `except ImportError` 폴백 없음** — top-level `crud` 모듈은 없으므로(`server/database/crud.py`뿐) 폴백 팔은 첫 ImportError 핸들러 안에서 **두 번째** ImportError만 낸다 |
| `@dataclass class Resolution` | `state`(`"resolved"`\|`"candidate"`\|`"unresolvable"`) · `winner` · `answer` · `rank` · `n` · `reason` · `top_class=None` · `competing=()` |
| `resolve(claims, answer_of, config=None, subject_label="", predicate="")` | **THE 해결기** — 모든 홉 상태가 여기서 나온다. 🔴 **경쟁은 claim 수가 아니라 *답*으로 잰다** — 같은 부모 랏을 대는 원자 셋은 증인 셋이 동의한 것이지 다툼이 아니고, 그걸 `candidate`라 부르면 화면이 늑대를 외치게 된다. 🔴 **`n`은 계급을 가로질러 *경합한 서로 다른 답*의 수다** — 계급은 어느 답을 따를지 정하지 불일치가 일어났는지를 정하지 않는다. 그래서 하위 계급이 다른 답을 대면 순위는 흔들리지 않아도 홉은 `candidate`로 읽힌다. **동의는 경합이 아니다**(계급을 가로지른 동의는 `resolved` 유지) |
| `_basis_label(claim, config=None)` / `_with_basis(reason, winner, config=None)` | `convention:<name>` 대 `basis=<name>` — 🔴 **낱말이 요점이다.** `basis=`를 읽은 운영자는 규칙 이름을 배우고 `convention:`을 읽은 운영자는 **이 홉이 측정이 아님**을 배운다. `_with_basis`가 **이긴 주장의** 라벨을 reason **끝에** 붙인다 |
| `live_claims(claims)` | 나중 원자가 supersede한 주장을 버린다. 🔴 **룩업이 아니라 여기서** — 「어느 주장이 현재인가」의 일부라서, 룩업에 두면 모든 룩업 구현이 다시 철자한다 |
| `@dataclass class Neighbourhood` | `claims` · `lots` · `truncated` · `truncation_reason`. **아직 어떤 순서 결정도 내리지 않았다** |
| `class ClaimLookup` | 프리미티브 **둘**(`reachable_lots(lot, max_depth)` / `claims_for_lots(lots, predicates=LINEAGE_PREDICATES)`)과 그 둘로 쓴 `neighbourhood(lot, max_depth=DEFAULT_MAX_DEPTH, predicates=LINEAGE_PREDICATES)` |
| `class InMemoryClaimLookup(ClaimLookup)` | 리스트 위의 룩업. **기본 `neighbourhood` 경로를 태우므로** SQL 룩업과 같은 답이 나오는 것이 두 프리미티브와 one-shot CTE가 같은 집합을 계산한다는 증거가 된다 |
| `_TRACE_CTE` / `_REACH_ONLY_CTE` | 🔴 **순위를 매기지 않고 superseded를 거르지 않는다** — 둘 다 해결기 몫이다. `CYCLE lot SET is_cycle USING path`(PG 14+)가 순환 가드이고 `UNION`은 가드가 **아니다**(같은 lot의 다른 깊이는 다른 행이라 진짜 순환이 깊이 상한까지 돌고 `depth_cap`으로 보고된다). `reached`가 **PATH당이 아니라 lot당 한 행**으로 접는다 — 다이아몬드 계보에서 증인 하나가 둘로 세어지지 않게 |
| `class SqlClaimLookup(ClaimLookup)` | `__init__(connection, relation="ledger_events")`. 🔴 **`relation`이 이음매다** — 머티리얼라이즈 프로젝션으로 화면을 돌리려면 이 문자열 하나. SQL에 보간되므로 **맨 식별자 정규식으로 검증**한다(바운드 파라미터는 관계 이름을 못 준다). `_execute(sql, params)`가 DBAPI 연결과 SQLAlchemy Connection 양쪽을 받는다 |
| `class OneShotSqlClaimLookup(SqlClaimLookup)` | 🔴 **측정으로 기각된 대안이고, 발견이 재현 가능하도록 남겨 둔 것이지 기본값이 아니다.** 원장 18,000에서 8.63 ms 대 2.22 ms(4배 나쁨), 360,000에서 2.07 대 2.15(동일). 이유 — **PostgreSQL은 재귀 CTE의 출력을 추정하지 못하고 고정 추측을 쓴다**(149–200행 추정, 실제 5). 그 허구가 **파티션 전체 seq scan**을 인덱스 탐침 다섯보다 싸 보이게 만들어 한 trace의 비용이 O(원장)이 된다. 2단계는 두 번째 질의가 `= ANY(<5개 배열>)`이라 플래너가 배열을 세므로 면역. 🔴 **위험은 「작은 원장이 느리다」가 아니라 조인 방식이 데이터에서 오지 않은 수로 정해진다는 것** — 원장이 교차점을 넘으면 코드 변경 없이 trace당 O(원장)으로 뒤집힌다 |
| `_claim_from_row(row)` | 행 → `Claim`. 문자열로 온 jsonb도 받는다 |
| 페이로드 리더 | `_object_key(claim, name)`(정체성) · `_object_qualifier(claim, name)`(서술) · `_payload_lot` · `_payload_wafer` · `_payload_slot` · `_slot_text(value)` · `_slot_map_pair(claim)` · `_as_text`. 🔴 **`keys`/`qualifiers` 분리가 읽기 측에서도 살아남아야 한다** — 평평한 페이로드는 `slot`을 웨이퍼 정체성으로 읽는다. 평평한 철자도 **받아 주는** 것은 관용이 아니라 **룩업 교체 가능성의 조건**이다(머티리얼라이즈 프로젝션·손픽스처가 자연히 그 모양을 낸다). `_slot_text`는 `3`/`"3"`/`"03"` 세 출처를 선행 0을 떼고 텍스트로 비교한다 |
| `_iso(dt, zone)` | 🔴 **응답의 모든 순간이 여기와 `zone`을 통과한다** — 출력이 PostgreSQL 세션의 TimeZone에도, 서버 프로세스의 주변 zone에도, 보는 사람의 기계에도 의존하지 않는다. naive 값은 **선언된 zone으로 해석**한다(기계 zone이 아니라) |
| `resolve_display_zone(config=None)` | 선언된 렌더 zone을 tzinfo로. **UTC 폴백도 기계 zone 폴백도 없고 크게 거절한다** — 틀린 zone으로 렌더된 fab 기록은 완전히 정상으로 보인다. Windows에서 `tzdata` 부재를 지목한다 |
| `_hop(frm, to, resolution, predicate, zone)` | 핀된 홉 모양 — `from`·`to`·**`predicate`**·`state`·`rank`·`n`·`reason`·`occurred_at`·`event_id`. `predicate`는 핀된 dict에 **더해진** 한 필드다(개명도 삭제도 아니다) |
| `trace(lot, slot=None, lookup=None, config=None, max_depth=DEFAULT_MAX_DEPTH)` | 🔴 **`hops`가 빈 리스트인 것은 구성상 불가능하고 그것이 기능 전부다.** 빈 원장에도 원자 0인 lot을 지목하는 `unresolvable` 홉 하나 + `terminal_reason`을 낸다(끝에서 `assert hops`). `lookup=None`은 `ValueError` — 해결과 룩업은 일부러 분리돼 있다. 홉은 **질문**의 열이다: `has_wafer(lot, slot)` → `derived_from(lot)` → `slot_map(lot→parent, slot)`. 반환 `{hops, terminal_reason, generated_at}`이고 **`generated_at`도 같은 선언 zone**이다(다른 시계면 눈으로 9시간을 빼게 된다). terminal 태그 — `[unknown_subject]` · `[root]` · `[dead_end]` · `[broken]` · `[cycle]` · `[depth_cap]` |
| `_map_slot(index, cur_lot, parent, cur_slot, cfg)` | 한 계보 홉을 건너 슬롯을 나른다. **양방향을 다 찾는다** — §4.2가 `from`이 어느 쪽인지 핀하지 않으므로 **어느 랏이 주어인가**라는 원자의 사실로 방향을 정한다. 둘 다 안 맞는 원자는 **읽지 않는다** — 틀린 슬롯이 화면에 가느니 정직한 `unresolvable`(`[no_slot_map]`) |

### `server/ledger_trace_router.py` (**80줄**)

| 심볼 | 무엇인가 |
|---|---|
| `router = APIRouter(prefix="/api/ledger", tags=["ledger"])` | 자족적 라우터 — `main.py` 등록이 두 줄 |
| `LEDGER_RELATION = "ledger_events"` | 인라인이 아니라 이름 붙인 이유가 **이음매**라서 |
| `_lookup_for(db)` | `ledger_trace.SqlClaimLookup(db.connection(), relation=LEDGER_RELATION)`. 🔴 **여기서 클래스를 갈아 끼우는 것이 머티리얼라이즈 룩업으로의 이주 전부** |
| `@router.get("/trace") trace_lineage(lot: str = Query(...), slot: str = Query(None), db: Session = Depends(get_db))` | 🔴 **빈 `hops`의 200은 가능한 답이 아니다.** 비-200은 둘뿐 — 잘못된 요청(**422**, 빈 `lot`은 손으로 422) 과 **503** 둘(`ResolverConfigError` / `ledger_events` 관계 부재. 후자는 「관계 없음」이 **이 박스의 운영 사실**이라 500이 아니라 503 + 관계 이름으로 보고한다) |

### 클라 3종 + 하니스

| 파일 | 줄 | 무엇인가 |
|---|---|---|
| `client2/ledger.html` | **393** | 페이지. 훅은 `#lt-query`(**input 정확히 하나**) · `#lt-result`. **`<button>` 0개** |
| `client2/src/ledger_trace.js` | **149** | 페이지 엔트리 |
| `client2/src/ledger_trace_core.js` | **286** | **순수** — DOM도 네트워크도 import도 없다. bare node에서 돈다 |
| `client2/src/ledger_trace_view.js` | **173** | DOM만 |
| `client2/tests/ledger_trace_harness.mjs` | **674** | 채점자 + 변이 |
| 픽스처 | — | `client2/tests/fixtures/ledger_trace_live.json` · `ledger_trace_probe.json` — 🔴 **지어낸 것이 아니라 라우트가 실제로 낸 답의 캡처**다 |

**`ledger_trace_core.js` export 18종** — 상수 `PREDICATE_QUESTION`(술어 → 그 술어가 **묻는 질문**. 술어 이름을 렌더하면 운영자가 번역해야 한다) · `GAP_LABEL` · `TERMINAL_VERDICT`; 질문 파싱 `parseQuery(text)`(`"LOT"`/`"LOT/02"`/`"LOT 02"` → `{lot, slot}`) · `traceQuery({lot,slot})` · `queryText({lot,slot})`; 홉 읽기 `reasonTag(reason)` · `hopBasis(reason)` · `basisLabel(basis)` · `hopVerdict(hop)` · `terminalVerdict(terminalReason)`; 노드/답 `nodeId(node)` · `nodeText(node)` · `hopQuestion(hop)` · `hopAnswer(hop)` · `hopAnswerContext(hop)` · `instantText(iso)`; 요약 `summarize(trace)`.
🔴 **이 모듈은 원장에 대해 아무것도 결정하지 않는다** — 서버가 모든 홉을 해결했고 `state`/`reason`/`predicate`를 실어 보냈다. 어느 주장이 이기는가에 대한 규칙이 이 파일에 나타나면 그것은 **두 번째 해결기**이고 틀린 것이다.
🔴 **module-private `BASIS_SUFFIX` 정규식은 `$`에 앵커돼 있고 그것이 세부가 아니다.** `_with_basis`가 **이긴** 주장의 라벨을 접미로 붙이는데, `candidate` reason은 **진 쪽의** 라벨도 인라인으로 담는다(`… 하위 계급 반대 1종 (LOT-B(convention:slot_preserving)) · 1순위 LOT-A`). anywhere-match는 그 홉을 「가정에 기댄다」로 읽고, 그것은 화면의 존재 이유를 **정확히 뒤집는다** — 가정은 **뒤집힌 쪽**이다. 인라인 라벨은 항상 ` · 1순위 …`가 뒤따라 `$`에 못 닿는다.
🔴 `hopVerdict`의 default 갈래는 `'gap'`이지 `'ok'`가 아니다 — 와이어가 다섯 번째 상태를 얻어도 **자신을 자신 있게 칠할 수 없다**.
🔴 `instantText(iso)`는 `T`를 공백으로 바꾸고 소수점 이하만 버린다. **`new Date(iso).toLocaleString()`을 절대 쓰지 않는다** — 서버가 선언 zone으로 렌더한 것을 보는 사람의 기계 zone으로 다시 렌더하면 정확성이 남의 노트북으로 옮겨 가고 **오프셋은 화면에서 사라져 아무도 알 수 없다**.

**`ledger_trace_view.js` export 2종** — `renderTrace(doc, mount, trace, subjectText)` · `renderNotice(doc, mount, {tone, title, detail})`. private `el`/`clear`/`renderSummary`/`renderHop`/`renderTerminal`. 🔴 **`document`가 전역이 아니라 인자다** — 그래서 하니스가 bare node에서 **진짜 렌더러**를 몰아 화면에 실제로 닿는 것을 단언한다(함수가 존재한다는 단언이 아니라). `innerHTML` 계열을 쓰지 않으므로 원장에서 나온 lot id가 마크업이 될 수 없다. DOM 훅 — `data-state`/`data-tone`/`data-predicate`/`data-basis`(홉) · `data-verdict`(뱃지) · `data-answer` · `data-basis-kind` · `data-terminal-tone` · `data-answer-kind`. 🔴 **요약 칩 `가정 N`은 `확정`에 절대 접히지 않는다** — 선언된 가정 아래서만 믿는 홉은 소스가 발화한 사실과 같은 것이 아니다.

**`ledger_trace.js`(엔트리)** — `subjectOf(trace, asked)`(제목은 **서버가 이해한 것**이지 입력된 것이 아니다) · `refusalText(res)`(FastAPI `{"detail": …}`를 **그대로** 보여 준다 — 여기서 지어낸 문장은 진짜 진단과 구별되지 않으면서 아무것도 아니다) · `run(asked, {pushUrl = true})` · `boot()`. 🔴 **세션 가드 `let session` — 중단점 *전부* 뒤에서 검사한다**(fetch 응답, 거절 본문, JSON 본문). 첫 await에서만 검사하면 본문을 지연시키지 않는 모든 테스트를 통과하면서 **느린 첫 답이 빠른 둘째 답 위에 얹힌다**. 입력은 `keydown`(Enter)에만 붙는다 — `change`는 blur에서도 발화해 딴 데를 클릭하면 묻지 않은 질문을 다시 던진다.

**`ledger_trace_harness.mjs`** — 방어하는 주장 셋: **P1** 관습에 기댄 홉이 측정에 기댄 홉처럼 보이면 안 된다 · **P2** `unresolvable`은 에러가 아니라 **내용**이다 · **P3** `candidate`는 무언가 이견을 냈다는 뜻이고 개수가 진술의 일부다. 구성 — `suite(coreSource, viewSource)`(섹션 C/D/E/G) + `census()`(**H1–H14**, 페이지 엔트리는 bare node에서 import 불가라 **텍스트로** 배선을 센다: import 2종 · 핀된 라우트 · 렌더 경로 · **세션 가드 발생 횟수** · 쓰기 0 · keydown 전용 · 세 모듈 통틀어 `toLocale*` 0 · view의 `innerHTML` 0 · 페이지 훅 · vite 엔트리 등재 · **input 정확히 1 · button 0**) + `DEFECTS` **5종**(전부 **잡혀야** 한다) + `CONTROLS` **2종**(전부 **빠져나가야** 한다 — 잡히면 어떤 검사가 동작이 아니라 소스 텍스트를 읽고 있다는 뜻). 🔴 **모든 변이가 소스를 실제로 바꿨는지 단언한다** — 상류 개명이 코퍼스를 조용히 은퇴시키는 대신 **빨갛게** 만든다. 마지막 줄 `ASSERTIONS <ran> <failed>`가 H1 프로토콜.

### 채점자 (`server/tests/`)

| 파일 | 줄 | `def test_` |
|---|---|---|
| `test_ledger_l1_unit.py` | **894** | **44** |
| `test_ledger_l1_pg.py` | **676** | **16** |
| `test_ledger_trace.py` | **642** | **30** |
| `test_ledger_trace_contract.py` | **419** | **13** |
| `test_ledger_trace_pg.py` | **971** | **24** |

`test_ledger_trace_contract.py::test_every_declared_derivation_is_explicitly_classified`가 **번역기 config가 낼 수 있는 모든 derivation을 열거해 해결기가 명시적으로 분류하지 않은 것에서 실패한다** — 새 관습이 조용히 class 2로 해결되는 대신 스위트를 빨갛게 만드는 장치다.

### ⚠️ 소스가 이 절을 반박하는 자리 — 코드 소관이라 여기서 못 고친다

- 🔴 **`server/ledger/__init__.py`의 「Nothing in `server/` imports this package」는 글자 그대로는 거짓이다.** `aeddac8` 전건 grep 실측 — `server/migrations/add_ledger_events.py`가 `from ledger import schema`를, 테스트 5모듈이 `from ledger import …`를 한다. **의도한 뜻(상시 도는 프로세스는 부팅에 이 패키지를 import하지 않는다)은 참이고** `add_ledger_events.py` 자신의 docstring이 그 형태로 적고 있다(「no process imports `server/ledger` at boot」). **어느 쪽도 사실로 등재하지 않고 실측한 import 자리만 적는다.**
- 같은 문장의 뒷부분 「`database.database`와 `utils.heartbeat`가 결합의 전부」도 **하나 빠졌다** — `config._config_dir()`이 `import paths`를 한다(실패 시 파일 기준 폴백).
- 🔴 **`ledger_trace.py`의 `DISPLAY_TIMEZONE_RULING = __doc__`과 `CONVENTION_DERIVATIONS_RULE = __doc__`은 둘 다 *모듈 docstring*에 바인딩된다** — 모듈 스코프의 `__doc__`이 그것이기 때문이다. 즉 **두 상수는 같은 문자열이고, 이름이 가리키는 판정문(바로 위 `#:` 주석)은 어느 쪽에도 들어 있지 않다.** 판정문 자체는 주석으로만 존재한다(파이썬 런타임에 없다). 의도가 「이름 붙은 참조점」인지 「그 텍스트를 담는 상수」인지는 소스에서 판정할 수 없어 **어느 쪽도 사실로 적지 않는다.**
- `server/config/ledger_config.json.sample`이 **`partitioning` 블록을 선언하는데 저장소 어디에도 읽는 코드가 없다**(전건 grep 0건 — `server/ledger/`도 마이그레이션도). `sources.<name>.columns.equipment`도 마찬가지로 **선언만 되고 읽히지 않는다**(`config.validate`의 필수 7종에 없고 `backfill.fetch_page`의 SELECT에도 없다).

---

## 6. 기타 서버 모듈 (한줄 요약)

라인 앵커 미수록 — 필요 시 해당 파일에서 Grep.

| 파일 | 책임 |
|---|---|
| `server/database/models.py` (🆕⑤ **1,041줄** @`831ab68`(HEAD) — 구 등재 984(`2630790`)에서 **+57**, 그중 25가 이번 구간(`ba664c5`)이고 **나머지 32는 이 패스가 열지 않은 커밋들**이다. 🔴 **아래 `FileIngestionCheckpoint` 절 말고는 이 패스도 재측정하지 않았다 — 라인 앵커는 밀렸다고 가정하라**) | ORM — 정적 + `DYNAMIC_TABLES` + 런타임 DDL(핫리로드 CREATE) — **함수 앵커는 [§5](#5-소형-서버-모듈)**. 🆕⑤ **[P2 · `831ab68` 실측] `class FileIngestionCheckpoint`** (`__tablename__="file_ingestion_checkpoints"`) — `table_name/file_signature/filename/`**`filepath`**`/`🆕⑤**`file_mtime`**`/`🆕⑤**`file_size`**`/source_kind/total_rows/processed_rows/chunk_index/status/note/started_at/updated_at`. 🆕⑤ **신설 컬럼 둘은 `file_mtime = DateTime(timezone=True)`(R5)·`file_size = BigInteger`(R1 — 수량이므로 수치형이 맞고, 종전에는 시그니처 **문자열** 안에 갇혀 질의가 불가능했다)**이고 셋 다 `nullable=True`를 **유지한다**(NULL 계약: SQL `=`가 NULL에 참이 될 수 없으므로 **구 행은 tier 1에 절대 안 걸린다** = 전체 해시로 떨어지는 안전한 방향. `SET NOT NULL`로 조이지 않는 이유는 운영에 NULL 행이 하나만 있어도 마이그레이션이 멈추는데 얻는 것은 이미 `=`가 주는 보장뿐이라서). 인덱스: `Index("idx_fic_identity", table_name, file_signature, unique=True)` + `idx_fic_signature` + 🆕⑤ **`Index("idx_fic_path_stat", table_name, filepath, file_mtime, file_size)`** — 🔴 **UNIQUE 아니다**(한 경로가 시간에 따라 여러 내용을 담으므로 UNIQUE를 걸면 정당한 갱신이 충돌한다 → tier-1 조회는 여러 행을 만나고 전순서로 하나를 고른다, R7). `status` 어휘에 🆕⑤ **`"FAILED"`** 추가(「실패」를 `err/`라는 **위치**로만 표현하던 것의 대체). `file_signature`에 예외 하나 — 내용을 못 읽은 파일의 실패는 `"stat:<size>:<micros>"` 키를 쓴다(`ingestion_checkpoint.STAT_SIGNATURE_PREFIX`, 접두가 달라 내용 시그니처와 충돌 불가). 준비 함수 `ensure_ingestion_checkpoint_table(engine)`(information_schema 게이트 + `checkfirst` + `_runtime_ddl_lock`). ⚠️ **기존 DB는 `create_all`이 ALTER를 하지 않으므로 `server/migrations/add_ingestion_ledger_path_stat.sql`(+`_reverse.sql`)을 별도 실행해야 한다.**<br>🆕🆕🆕 **`AuditLog.__table_args__`에 인덱스 3종 추가**(§`audit_cache.py`/`audit_history.py`의 재작성이 근거) — `idx_audit_row_history`(`table_name, row_id, timestamp, id`) · `idx_audit_cell_history`(`table_name, row_id, column_name, timestamp, id`) · `idx_audit_recent_groups`(`timestamp, id` **INCLUDE**`(transaction_id)` — leading column이 `timestamp`뿐인 유일한 인덱스라 `/audit_logs/recent`의 무조건 스캔을 받을 수 있는 유일한 인덱스). ⚠️ **`create_all`은 이미 있는 테이블에 인덱스를 추가하지 않는다** — 신규 DB만 이 선언으로 인덱스를 받고, 기존 DB(프로덕션 포함)는 `server/migrations/add_audit_history_keyset_indexes.sql` + `add_audit_recent_groups_index.sql`을 **별도 실행**해야 한다 |
| 🆕🆕🆕 `server/audit_cache.py` (**643줄** @`2630790`(HEAD) — 🔴 **직전 등재 247줄은 전면 재작성 전 값. 종전 지도의 `prepend_transaction` 메서드는 실재하지 않는다 — 이번 재작성 전에도 없었다, 묘비로 승격하지 않고 그냥 삭제**) | `GET /audit_logs/recent`가 서빙하는 최근 감사 로그 인메모리 프로젝션. 🆕🆕🆕 **[`2630790` 전면 재작성] "growing OFFSET로 100 tx 그룹을 찾을 때까지 5,000행씩 훑기"(무한정 — 대량 인제션은 파일당 tx 1개라 200,000행이 그룹 2개일 수 있다)가 4단계로 갈렸다.**<br>① **DISCOVERY** `_discover_groups(db, limit_groups, settings)` — `(timestamp, id)` **keyset walk**(`_chunk_edge`가 `audit_history.apply_cursor`/`order_desc`를 그대로 재사용 — 커서 어휘의 두 번째 철자가 아니다), 각 청크는 `_count_by_transaction`(**DB 집계** `GROUP BY transaction_id` — Python으로 행마다 세지 않는다, 실측 0.64–1.11 µs/행 대 종전 5.4 µs/행) · 상한은 `RECENT_DEFAULTS["recent_max_scan_rows"]`(**기본 500,000**, config-driven — `resolve_recent_settings`가 `audit_history_config.json`을 공유 해석). 걸음이 상한에서 멈추면 **`self.truncated=True` + `self.next_cursor`**(라우트가 `X-Audit-Truncated`/`X-Audit-Next-Cursor` 헤더로 흘린다 — 아래 `main.py` 참조)를 발행한다.<br>② **HYDRATION** `_hydrate(db, order, counts, tops, bottom, watermark, per_group)` — discovery가 지목한 그룹만 **`limit_groups × recent_logs_per_group`로 상한**된 pydantic 변환.<br>③ **워터마크·이벤트 크레딧** — `_db_max_id`(walk 시작 전에 읽는다 — 진행 중 커밋된 행이 워터마크 아래로 들어가 다음 화해 때 잡히도록). 🔴 **`add_logs_batch`는 워터마크를 전진시킬 수 없다**(받는 log dict의 `id`가 전부 리터럴 `0` — `crud.create_audit_log`가 그렇게 쓰고 `bulk_insert_mappings`는 채번된 키를 되돌려주지 않는다). 그래서 이 경로가 센 건수는 **`_claim(group, n)`으로 선불(credit)** 기록되고, 같은 행을 DB에서 다시 읽는 `refresh_if_stale`이 `_absorb_one(group)`으로 그 선불에서 **상계**한다(안 하면 300행이 600으로 읽힌다 — 실측된 결함). `refresh_if_stale`은 델타가 `recent_refresh_max_delta_rows`(기본 2,000) 이하면 증분 병합, 넘으면 **상한 있는 재구축**으로 낙하.<br>④ **정적 헬퍼** — `resolve_recent_settings(config=None)`(불리언이 정수로 조용히 통과하지 않도록 방어) · `_ordered_rows(query, floor)`(**`timestamp IS NOT NULL`이 하중 조건** — row-value 비교는 NULL과 비교하면 NULL이라 필터링이 아니라 진짜 이 문장이 없으면 null-스탬프 행이 첫 청크에서만 살고 이후 청크에서 조용히 사라진다) · `_cursor_token(cursor)`(`audit_history.encode_cursor` 위임).<br>클래스 나머지 메서드: `class AuditLogCache.__init__` · `load_initial(db, limit_groups=100, force=False, refresh_above=None)` · `add_log(log_dict)` · `add_logs_batch(logs_list, message_total_count=None)`(P2/이슈 #10 — 절단 전 실건수를 `_claim`으로 누적, tx 2종 이상 혼재 시 `len(logs)` 폴백+1회 경고) · `remove_deleted_rows`(no-op, 삭제 행 이력 보존). 모듈 싱글턴 `audit_cache = AuditLogCache()`. 채점자: `server/tests/test_audit_cache_cross_process.py` · 🆕🆕🆕 **`server/tests/test_audit_cache_recent_scan.py`**(신설 — 9종 주입 결함 각각의 채점) |
| 🆕🆕🆕 **`server/audit_history.py`**(**242줄**, `dab9152` 신설) | **행/셀 이력 페이징의 공유 프리미티브 — `GET /tables/{t}/rows/{r}/history`·`.../cells/{c}/history`와 `audit_cache`가 함께 쓴다.** 종전엔 두 라우트 모두 `.order_by(timestamp.desc()).all()`로 **LIMIT 없이 전건**을 읽었다(실측: 어느 한 행이 300,019건까지 불어난 픽스처에서 3,462 ms·54 MB). 🔴 **정렬 술어는 row-value 비교(`sa.tuple_`)여야 한다** — 논리적으로 동치인 `OR` 전개는 PostgreSQL이 btree에 bound를 못 박아 인덱스 조건 대신 **Filter**로 떨어진다(같은 페이지 실측: 18버퍼/0.114ms 대 2,311버퍼/4.949ms). `load_config(path=None)`(`audit_history_config.json`, 파일 부재는 정상=`{}`) · `resolve_settings(config=None)`(`default_limit=200`/`max_limit=1000`, `default>max`는 clamp+경고) · `resolve_limit(requested, settings=None)`(범위 밖은 **거부가 아니라 clamp**) · **`encode_cursor(timestamp, log_id) -> str`**/**`decode_cursor(token) -> (datetime, int)`**(base64url, `CursorError`는 400 — 조용한 재시작 대신 명시 실패) · `order_desc(model)`(`(timestamp.desc(), id.desc())` — 이 프로젝트에서 "이력 페이지 정렬"을 말하는 **유일한 철자**) · `apply_cursor(query, model, cursor)` · **`fetch_page(query, model, limit, cursor=None) -> (rows, truncated, next_cursor)`**(`limit+1`행을 물어 has-more를 정확히 판정 — `count(*)`로 다시 훑지 않는다). `class CursorError(ValueError)`. 채점자: `server/tests/test_audit_history_paging.py`(신설) |
| `server/database/schemas.py` (🆕🆕🆕🆕 **315줄** @`fde424c` — 277에서 **+38**) | Pydantic — `GeneralUpdateItem`(~76)/`GeneralUpdateBatch`(**~128**) 등 API·배치 계약. 🆕🆕🆕 **`class AuditHistoryPage(BaseModel)`(신설)** — `GET /tables/{t}/rows/{r}/history`·`.../cells/{c}/history`의 응답 봉투: `logs: list[AuditLogResponse]` · `truncated: bool` · `next_cursor: str\|None` · `limit: int` · `returned: int`. **봉투이지 배열이 아닌 것이 요점**이다 — 종전엔 두 라우트 모두 셀/행이 누적한 이력 전체를 반환해 "이게 전부"와 "서버가 보내주고 싶은 만큼"을 클라가 구분할 방법이 없었다. 🆕🆕🆕🆕 **`class AuditLogGroupPage(BaseModel)`(신설, `fde424c`)** — `GET /audit_logs/recent`의 같은 계열 봉투이지만 **리스트 필드명이 다르다**: `groups: list[AuditLogGroupResponse]`(그룹마다 자기 `logs`를 갖고 있어 `logs`로 부르면 `body.logs[0].logs`가 된다) · `truncated: bool` · `next_cursor: str\|None` · `limit_groups: int` · `returned: int`. ⚠️ **`AuditHistoryPage`보다 짝이 약하다 — 의도적이다**: 그쪽은 `next_cursor`가 non-null ⟺ `truncated`지만, 여기는 `add_logs_batch`의 실시간 병합이 프로젝션 꼬리를 잘라내 **`truncated=true`인데 `next_cursor=null`**인 3번째 상태가 실재한다("더 있지만 재개 위치를 잃었다" — 클라는 이걸 "안 잘렸다"로 접는다, 전역 탭이 페이저를 안 그리는 동안만 옳다) | `GeneralUpdateBatch.silent`(**~137** — [M3] 메타 자동 등록이 쓰는 무브로드캐스트 플래그) · `replace_map`(**~138**) + **[gate4 `deed6d2`] `scope: Optional[Dict]`(**~143**)** — 명시 purge 스코프 `{column: value}`. 지정 시 유도 대신 이것을 쓰며(엄격 검증 — [§2 `derive_replace_map_scope`](#2-serverdatabasecrudpy--레이어링-코어)), **명시 scope + 빈 `updates`는 그 스코프의 의도적 전량 삭제**.<br>**[V1 `2a9f6c4`] 공수 계측 3종**: **`EffortReport`(~83)** — 클라가 보내는 카운트 블록. **`extra="allow"`인 것이 의도**다(오타 키를 pydantic이 조용히 떨어뜨리는 대신 `main._validate_effort`가 **문제의 키 이름과 함께** 사유를 응답·로그에 남긴다) · **`GeneralUpdateBatch.effort: Optional[Any]`(~153)** — 타입을 느슨하게 둔 이유도 같다(`"effort": 5` 같은 오용이 엔드포인트 **전에** 422로 거부되면 사유가 사용자에게 안 간다) · **`EffortStat`(~223)** / `DashboardSummaryResponse.effort`(~253) — 대시보드 응답 필드 |
| `server/database/database.py` (🆕 **333줄** @`34d2518`) | 엔진·SessionLocal·outbox 발화(`database_outbox` + NOTIFY). 🆕 🔴 **[`528dfcb`] outbox 스테이징이 두 갈래가 됐다** — `stage_event(session, event_type, table_name, data_row)`(per-row, 한 행의 값을 나른다)와 🆕 **`stage_collapsed_event(session, event_type, table_name, row_ids)`**(접힌 이벤트 — **행을 가리킨다**). 갈래를 고르는 것은 `auto_stage_database_outbox`이고, 모드는 🆕 **`server/database/context.py`의 `outbox_mode(mode)` 컨텍스트매니저**가 선언한다(기본 `OUTBOX_MODE_PER_ROW`). 🔴 **DELETE는 어느 모드에서도 접히지 않는다 — 지워진 행은 다시 읽을 수 없다.** 그 밖: `_outbox_envelope()` · `_notify_outbox_once(session)` / `_clear_outbox_notify_latch(session, transaction)`(트랜잭션당 NOTIFY 1회 래치). **[`2728bd9`] 접속 URL은 `paths.resolve_database_url(DEFAULT_PG_URL)`을 **import 시 1회** 소비** — `SQLALCHEMY_DATABASE_URL, DB_URL_SOURCE`. 우선순위 env `DATABASE_URL` > `config/database.json` > 기본값(테스트 `tests/test_database_url_config.py`가 고정 — env가 져야 하는 순간이 없다: 격리 스택의 프로덕션 오접속 방지). **핫 리로드 없음이 의도** — 접속 문자열은 교체 불가, `database.json` 변경은 전 프로세스 재기동.<br>🆕 **[`e1ba99e` #16a] 테스트 프로세스 가드 설치 지점 2곳이 여기다**([§5-C](#5-c-2026-07-31-신설-서버-모듈-2종)) — 순서가 계약이다: ① **모듈 상단**, 이 프로세스에 엔진이 존재하기 **전에** `db_safety.install_global_test_database_guard(production_url=DEFAULT_PG_URL)`(**`engine_connect` 훅 · Engine 클래스**에 걸어 테스트가 스스로 만든 엔진까지 덮는다) ② **엔진 생성 직후** `db_safety.install_test_database_guard(engine, production_url=DEFAULT_PG_URL)`(**`do_connect` 훅** — 해석된 URL로 지어진 **유일한** 엔진, 즉 자격증명을 손으로 입력받지 않고 **주변 환경변수만으로** 프로덕션을 가리킬 수 있는 그 엔진에 더 엄격한 훅을 건다. **소켓이 열리기 전에** 거부하므로 테스트 프로세스는 진짜 DB에 접촉조차 하지 않는다). ⚠️ **pytest 밖에서는 둘 다 즉시 반환하는 리스너**라 프로덕션 접속 경로는 무변경이다 |
| `server/database/config_watcher.py` (**180줄** — `b8307c2` 66줄에서 재작성) | ✅ **[`46a67c7` 착지 — 구 지도가 "워킹트리 값이니 재측정하라"고 표시했던 항목이고, 커밋 기준으로 다시 재니 예고된 형태와도 달랐다.]** `CONFIG_FILENAME`(~10)·`DEBOUNCE_SEC=1.0`(~14)·`class ConfigChangeHandler`(~17)·`__init__(engine=None)`(~51)·**`on_moved`(~59)**·`on_modified`(~65)·**`on_created`(~70)**·**`_maybe_reload(path)`(~75)**·**`_fire(path)`(~90)**·**`cancel_pending()`(~97)**·**`wait_for_idle(timeout=None)`(~104)**·`_reload(path)`(~126)·`start_config_watcher(engine=None)`(~164).<br>🔴 **리딩 엣지 → 트레일링 엣지 + 재무장.** 구 코드는 `last_triggered`로 "창의 첫 이벤트가 이기고 나머지는 무시"였고, 그것이 **0.3초 간격 두 번의 저장 중 두 번째를 통째로 버렸다** — 디스크는 `[col_a, col_b, lot_id]`, 물리 테이블은 `[col_a, lot_id]`, 로그는 성공. 느린 비원자적 쓰기의 **완료**도 버렸다(첫 이벤트는 파일이 아직 잘린 상태에 도착해 부분 JSON을 읽고 중단한 뒤, "끝났다"를 뜻하는 `modified`를 폐기). 그리고 그것이 **제품 자신의 쓰기 경로**다 — `crud.update_table_config`는 평범한 `open(w)`다. 이제 모든 이벤트가 `threading.Timer(DEBOUNCE_SEC, _fire)`를 `_timer_lock` 아래 취소·재무장한다.<br>**도착 형태 3종 전부 처리**: `on_modified`(제자리) · `on_moved`(같은 디렉터리 temp+rename — config가 **rename 목적지**라 `src_path`가 아니라 `dest_path`를 본다) · `on_created`(디렉터리를 넘는 rename은 `deleted`+`created`를 내고 **`moved`가 없다** — `tempfile.mkstemp()`가 시스템 temp에 만드므로 이상한 경우가 아니다). watchdog 6.0.0/Windows 실측. QA의 진단이 docstring에 남아 있다: **`on_created`에 대한 반론은 실은 리딩 엣지에 대한 반론이었고, 트레일링 엣지가 `created`를 안전하게 만든다.**<br>**빈 config 중단이 더는 조용하지 않다** — 구 `if new_config:`에 else가 없어 파싱 불가 config가 적용도 **로그도** 없이 지나갔다(장애 보고의 증거가 빈 로그였다). 중단은 여전히 옳지만(빈 config가 라이브 싱글턴을 지워선 안 된다) 이제 "in-memory config와 물리 스키마는 **변경되지 않았다**"를 명시한다. + 리로드 직렬화 `_reload_lock`, 핫스왑 실패에 `exc_info=True`, `observer.config_handler` 노출(디바운스가 `observer.stop()`이 모르는 자기 타이머 스레드에서 발화하므로 폐기된 engine에 대고 돌 수 있었다).<br>⚠️ **BOM 부팅 장애 자체는 이 파일이 아니라 `crud._decode_config_text`에서 고쳐졌다**([§2](#2-serverdatabasecrudpy--레이어링-코어)) |
| `server/graph_sync_worker.py` · `graph_materializer.py` · `ontology_config.py` | 온톨로지 그래프 트랙 — **함수 앵커는 [§5](#5-소형-서버-모듈)** |
| **`server/run_auto_update.py`** (**882줄**, 801 → **+81**) | 스케줄 기반 사용자 스크립트 자동 실행.<br>🆕 🔴 **[신설] 소급 실행의 실행 절반이 여기다** — `MultiDiscoveryScheduler.__init__`의 필드 2종 `_retroactive_thread`/`_retroactive_last`(**~412/413**) + **`retroactive_busy()`(~707)** / **`start_retroactive_run(payload)`(~711)**. 🔴 **데몬 스레드로 도는 것이 계약이다**: 인라인 실행은 60초 하트비트를 멈추고 그러면 `/health`가 이 데몬을 **WEDGED로 보고한다**. outbox 폴 블록이 가장 오래된 미처리 `RETROACTIVE_RUN` 행 하나를 집어 **스레드가 끝나기 전에** `processed_chain=True`로 표시하고(at-most-once), 이미 실행 중이면 행을 **큐에 남긴다**.<br>🆕 **[`4aae627`] `_apply_proxy_policy()`(**~25**) — 모듈 스코프에서 즉시 1회 실행된다(**~80**).** 수집 스크립트는 사용자가 쓰고 `exec`로 도는 코드라 각자 프록시를 다룰 수 없고, 그것들이 치는 곳은 **사내 인트라넷**이라 프록시를 **우회**해야 한다(2026-07-30 실측: 경유하면 403). 🔴 **개별 변수를 지우는 것으로는 반대 결과가 난다** — `urllib.request.getproxies()`는 `getproxies_environment() or getproxies_registry()`이고, 환경 dict가 **비면** 뒤의 **레지스트리**로 넘어가 운영 머신의 사내 프록시가 되살아난다. 그래서 `*_proxy` 계열을 전부 걷어낸 뒤 **`no_proxy="*"` 하나를 남겨 dict를 비지 않게** 만든다(`requests`도 같은 함수를 타므로 두 라이브러리에 동시에 듣는다). 끄는 스위치는 `auto_update_control.json`의 **`bypass_proxy`**(기본 **true = 직결**, boolean 아니면 경고 후 기본값). 제거한 변수는 **이름만** 로그한다(프록시 URL에 자격증명이 실릴 수 있다). ⚠️ **전역 `NO_PROXY` 환경변수와 혼동하지 말 것** — 그것을 프로세스 밖에 세우는 것은 [§1.7](#17-serverinternal_event_clientpy--내부-http-호출의-단일-소유자-23a346d-신설)이 **명시적으로 금지**하는 조치다.<br>🔴 **이 삽입이 파일 머리에 있어서 83행 이후 앵커가 전부 균일 +59다** — 아래 값은 전부 `c520012` 재측정이다.<br>**[`530fdfd` 신설] `MultiDiscoveryScheduler.maybe_sweep_graph_orphans(self, now=None)`(**~668**)** — ⚠️ **모듈 함수가 아니라 메서드다.** `run()`의 5초 틱에서 `maybe_backup_configs()`(3단계) 바로 뒤 **4단계**로 호출(**~792**). 상태는 `__init__`의 `_last_orphan_check`/`_last_orphan_sweep = 0.0`("첫 틱에 실행" 규약 — 장애 후 올라온 프로세스가 놓친 유지보수를 부팅 때 한다, `_last_backup_check`와 같은 관례). **JSON config 키가 없다** — 주기는 전부 `graph_orphans`에서 온다(스로틀 `CHECK_INTERVAL_SEC` 1800초, 실제 주기는 `due()`가 `SWEEP_INTERVAL_SEC` 86400초로 판정). 끄는 스위치는 **환경변수 `GRAPH_ORPHAN_SWEEP_ENABLED=false`**. 가드 순서: 스로틀 미달이면 `None` → `_last_orphan_check` 스탬프 → `due()` 아니면 `None` → **`_last_orphan_sweep`을 실행 전에 스탬프**(raise하는 스윕이 재시도 루프를 못 돌게) → `try/except`로 감싸 실패는 로그만(**스윕 실패가 수집기를 절대 멈추지 않는다**). ⚠️ 사소한 두 가지: `now` 인자를 받지만 **쓰지 않는다**(`maybe_backup_configs`는 전달한다), 그리고 `_last_orphan_check`는 wall-clock(`time.time()`)인데 `_last_orphan_sweep`은 monotonic이다(`due()`의 계약상 의도적이나 한 메서드에 두 시계가 섞여 있다). docstring이 "수집기가 아니라 유지보수 작업"임을 근거로 든다 — 테이블이 없고 인제션돼선 안 되며, 지금 아무것도 생산하지 않는 수집기는 설계상 FAIL을 보고한다. 매 틱 제어 파일(`auto_update_control.json`)을 읽어 disabled 수집기는 실행 스킵+`last_status="SKIPPED"`+next_run 전진(핫 반영, 재활성화 시 백로그 폭주 없음). run-now는 active 무관 실행. 함수 앵커: `class GenericScriptRunnerCollector`(**~138**)·**`execute()`(**~165**)**·`parse_script_comments`(**~362**)·`class MultiDiscoveryScheduler`(**~391**)·`discover_and_load_collectors`(**~411**)·`_load_collector_from_script`(**~455**)·`_collector_key`(**~516**)·`_write_status_file`(**~521**)·`run_collector_on_demand`(**~553**)·`execute_collector`(**~567**)·`check_and_run_schedules`(**~594**)·**`maybe_backup_configs()`(**~637** — [`b35bc9f` C3] 틱마다 30분 게이트(`config_backup.CHECK_INTERVAL_SEC`)로 `config_backup.run_scheduled()` 호출. cron식이 아니라 `due()`가 디스크의 최신 스냅샷 나이로 판정 — 놓친 주가 다음 틱에 자가 치유. 백업 실패는 절대 수집기 실행을 멈추지 않는다)**·**`run()`(**~703**, 루프 안 `heartbeat.beat("scheduler")` **~734**)**.<br>🔴 **[2026-07-30 기록] 직전 패스가 이 파일의 앵커 셋을 막 고쳐 놓았는데 다음 라운드가 그것을 다시 밀었다** — `maybe_backup_configs` 578→**637** · `run()` 644→**703** · beat 675→**734**. 직전 밀림(39줄)은 `530fdfd`의 `maybe_sweep_graph_orphans`가, 이번 밀림(59줄)은 `4aae627`의 `_apply_proxy_policy`가 만들었다. **두 번 다 "파일에 함수 하나가 들어왔다"이고 두 번 다 그 옆의 앵커는 아무도 안 쟀다.**<br>**[`512dca7` 재작성 — `execute()`의 실패 계약] "확인할 수 없었다"를 "이상 없다"로 보고하지 않는다.** 판정은 세 로컬(`out_data`·**`out_declared`**(**~208**)·**`exec_error`**(**~209**))의 조합이고 **함수 밖에 헬퍼가 없다** — 4상태: ① `out` 미정의 + 무예외 → stdout 수집기이며 폴백이 **정상 경로**(INFO) ② `out = None` **대입** → 스크립트가 줄 게 없다고 선언한 것이므로 **즉시 FAIL, stdout 재실행 없음**(**~260**, 이런 스크립트는 네트워크 페치의 에러 핸들러라 재실행하면 외부 호출만 반복한다) ③ `out`은 있는데 비었음 → 이번 주기에 수집할 게 없다, SUCCESS ④ 실행이 **raise** → ERROR + 트레이스백, 폴백은 시도하되 **그것도 비면 raise해서 FAIL**(**~344**). ①과 ④가 종전엔 같은 WARNING 한 줄로 뭉개져 **크래시해서 0행을 모은 실행이 깨끗한 성공으로 보고됐다**. ②가 ①과 구분 불가였던 것은 `.get("out")`이 "None 대입"과 "미정의"를 구분하지 못하기 때문이다.<br>**`SystemExit` 처리(**~237**)**: `sys.exit(0)`으로 끝나는 수집기는 정상 완료이므로 `out`을 존중한다. `SystemExit`는 `BaseException`이라 잡지 않으면 `execute_collector`·`check_and_run_schedules`(둘 다 `Exception`만 잡는다)를 **관통해 스케줄러 데몬을 종료시킨다**. 0/None이 아닌 코드는 `exec_error`로 강등 후 폴백 시도.<br>**`exec(code_content, script_ns)` — globals/locals에 같은 dict 하나(**~231**)**: 서로 다른 두 dict를 넘기면 클래스 바디 스코핑이 돼 모듈 레벨 `def`/`import`가 locals에만 바인딩되고 **함수 본문은 `LOAD_GLOBAL`이라 그것을 못 본다** → 다른 함수에서 호출된 헬퍼가 `NameError`로 죽고 수집기는 조용히 아무것도 못 모은다(모듈 레벨 호출은 `LOAD_NAME`이라 locals를 보므로 **일부 수집기만 고장 나 보였다**). 테스트: `tests/test_auto_update_script_exec.py`(21건 — `TestSingleNamespace`·`TestStdoutFallback`·`TestFailuresAreLoud`·`TestOutAssignedNone`·`TestOutFormattingFailure`·`TestSystemExitContainment`) |
| `server/event_constants.py` (🆕 **223줄** @`34d2518` — 종전 86줄에서 **+137**) | 🆕 🔴 **[`528dfcb`] 이 모듈에 outbox *접기(collapse)* 절이 통째로 생겼다 — outbox 이벤트가 스냅샷에서 *포인터*로 바뀐 자리다.** 종전엔 인제션이 데이터 행마다 outbox 행 하나에 컬럼 전량을 실었다(실측 2,113.5 B/행 → 1천만 행 파일에 19.7 GiB). 이제 이벤트는 **트리거 row_id들과 테이블 이름**을 나르고 파생 쪽이 행을 **다시 읽는다**(20,000행 → 20 이벤트, 36.0 B/행).<br>**선언 — 전건 열거**: `OUTBOX_MODE_PER_ROW`(**기본값** — 옵트인 안 한 호출자는 종전 그대로. 🔴 **사람/교정 경로는 여기 머물러야 한다**) · `OUTBOX_MODE_COLLAPSED`(**대량 인제션만, 명시 옵트인.** ⚠️ **`request_source`로 추론하지 않고**(그건 인제션 경로에서 *파일명*이지 채널이 아니다) **행 수로도 추론하지 않는다**(사람의 맵 Push가 수천 행이다)) · `OUTBOX_COLLAPSE_CHUNK_ROWS = 1000`(이벤트 하나가 나르는 row_id 상한) · `OUTBOX_GROUP_MAX_ROWS = 20000`(🔴 **새 손잡이가 아니라 구 `LIMIT 20000`이 뜻을 지킨 것** — 접힌 뒤에도 이벤트로 세면 한 배치가 2천만 행을 끌어와 **1,000배 증폭**된다. 그래서 예산은 **행**으로 매긴다) · `OUTBOX_PAYLOAD_EXCLUDED_COLUMNS`(frozenset — 생산자가 안 쓰는 컬럼과 **정확히** 같아야 확장기가 같은 페이로드를 다시 짓는다).<br>**함수**: `is_collapsed_payload(payload)`(🔴 **`event_type`이 아니라 판별 키(`row_ids`) 멤버십으로 판정한다** — 접기가 `event_type`을 CREATE/EDIT로 **일부러 유지**하므로 「테이블 T의 데이터 변경인가」만 묻는 소비자는 전부 무접촉이고, `payload['data']`를 실제로 **읽는** 소비자만 여기서 분기한다) · `payload_row_count(payload)`(per-row는 1) · `trim_events_to_row_budget(events, budget, payload_of=None)`(🔴 **필터가 아니라 id 순 *접두사*다** — 꼬리는 `processed_chain=False`로 남아 다음 반복이 **같은 순서로** 집는다. **항상 최소 하나는 돌려준다**, 예산보다 큰 청크 하나가 배수를 영구히 막지 않도록).<br>⚠️ **DELETE는 접히지 않는다** — 지워진 행은 다시 읽을 수 없다(`database.auto_stage_database_outbox`).<br>기존 절 — 프로세스 간 내부 이벤트(`/internal/events/*`) 공용 상수.<br>🆕 **[신설] outbox 제어 이벤트 절**: `EVENT_SCHEDULER_RUN_NOW`(**21**) · **`EVENT_RETROACTIVE_RUN`(25)** · **`CONTROL_EVENT_TYPES` frozenset(🔴 **40** @`34d2518` — 구 `~28`은 낡았다)**. 🔴 **체인 워커가 제어 행을 리터럴 `"SCHEDULER_RUN_NOW"` 비교가 아니라 이 집합의 멤버십으로 거른다** — 제어 이벤트가 둘이 되는 순간 리터럴 비교는 새 종류를 **데이터 이벤트로 오인해 체인에 먹인다**.<br>`MAX_NOTIFY_CREATED_LOGS=500`(🔴 **49** @`34d2518`, 구 `~36`) · [P2] `MAX_AUDIT_VALUE_CHARS=4096`(🔴 **69**, 구 `~44`)과 `truncate_audit_value(value, max_chars)`(🔴 **197**, 구 `~47` — 반환 `(값, 절단여부)`, str은 `…[truncated: 총 N자]` 마커, dict/list는 타입·길이 플레이스홀더)를 `crud.create_audit_log`가 소비.<br>🔴 **소비처 앵커는 매 패스 다시 잰다 — 한 패스에서 4개 중 3개가 틀린 적이 있다.** 🆕 **실측(`34d2518`, 전건 grep — 이번엔 넷 중 셋이 또 밀렸고 하나는 *늘었다*)** — 🔴 **`directory_watcher:1917`**(구 1813, **+104**) · 🔴 **`chain_ingestion_worker:594`**(구 540) · 🔴 **`main.py`는 소비처가 둘이 아니라 셋이다**: **2714–2715 · 5790 · 5838**(구 `5165/5213`은 낡았고 개수도 틀렸다) · ✅ **`server/database/crud.py` `create_audit_log` 안 1117–1118 — 이번엔 밀리지 않았다**(구 지도의 `613–614`가 낡았던 그 자리). `CONTROL_EVENT_TYPES` 멤버십 소비는 🔴 **`chain_ingestion_worker:1122`**(구 1005). ⚠️ **`retroactive.py:124` · `run_auto_update.py:836`는 이번 패스에서 재측정하지 않았다 — 낡았다고 가정하라.** **"재측정했다"는 표지가 붙은 수를 다시 재는 것이 이 행의 존재 이유다** — 표지는 측정이 아니다 |
| 🆕 **`server/outbox_expand.py`** (**303줄**, `528dfcb` 신설) | **접힌 outbox 이벤트를 다시 행으로 펴는 유일한 자리 — 소비자 쪽 절반.** 🔴 **세 번째 페이로드 모양을 만들지 않는다**: `chain_replay`가 이미 하던 재구성을 **재사용**하고, 그래서 라이브 트리거 경로도 「페이로드를 먹는 유일한 소비자」이기를 그만둔다. 함수 — `_data_columns(model)` · `_synthesize_payload(row, columns, envelope)` · `load_rows_by_ids(db, table_name, row_ids, chunk_size=OUTBOX_COLLAPSE_CHUNK_ROWS)` · `event_key(event)` · **`expand_events(db, events) -> dict`**(체인 워커의 소비 지점) · **`reexpand_collapsed_event(db, event, payload, error_reason=None) -> int`**. 🔴 **실패한 접힌 청크는 per-row로 다시 펴지되 *per-row transaction id* 아래로 간다** — 워커의 실패 단위가 이벤트가 아니라 **그룹**이라, 원래 id로 다시 펴면 그 행들이 **다시 함께 실패하도록** 묶인다 |
| 🆕 **`server/migrations/add_business_key_unique_index.py`** (**606줄**, `528dfcb`+`818c9c0`) | **[D3] `business_key_val`에 테이블별 UNIQUE 인덱스.** 「비즈니스 키당 한 행」은 **가정이었지 불변식이 아니었다** — 25개 테이블에 걸쳐 `business_key_val`을 덮는 인덱스가 50개인데 **유일한 것이 하나도 없었다**(데이터는 이미 도처에서 만족: 52,725행, 잉여 0). 인덱스명 접두사는 `crud.BK_UNIQUE_INDEX_PREFIX`(`"uq_bk_"`)와 **리터럴로 짝을 이룬다**(import 아님 — 위 [§2](#2-serverdatabasecrudpy--레이어링-코어) 참조). 같은 스크립트가 **primary_key 컬럼에 선언된 `index=True`에서 나온 중복 인덱스**도 걷어낸다(실측 29개·382.3 MB, 그중 26개가 공유 동적 테이블 `row_id` 하나에서 나온다). 🔴 **목록을 박아 두지 않고 매 실행 `pg_index`에서 다시 발견한다** |
| 🆕 **`server/scripts/check_missing_business_key.py`** (**123줄**, `b2ceb55` 신설) | **읽기 전용 사전 점검** — 비즈니스 키가 끝내 조립되지 않은 행을 D3 유일 인덱스 **설치 전에** 센다. 쓰기 0건. 엔트리는 `main()` 하나 |
| `server/scripts/setup_ingestion_checkpoint.py` | [P2] `file_ingestion_checkpoints`를 **프로세스 재기동 없이** 미리 생성(멱등) — 직접 SQL 없이 `models.ensure_ingestion_checkpoint_table(engine)` 호출 후 컬럼·인덱스 출력 |
| **`server/scripts/backfill_enrichment.py`** (399줄, `1fefd12` 신설) | **[소급 인리치먼트 백필 CLI — 드라이런 기본, 쓰기는 `--apply`]** 룰 도입 **이전**의 소스 행에서 파생 행이 없는 decision_key 조합만 생성한다 — **기존 파생 행은 바이트 무접촉**(값 공백은 큐 소관, 행 부재만 백필 소관). 두 번째 집계 구현이 아니라 **실제 맵퍼(`map_enrichment_dedup`)와 실제 쓰기 경로(`crud.apply_batch_updates`)에 먹인다** — outbox가 정상 발화해 그래프도 머티리얼라이즈되고, 파생 테이블 이벤트는 체인 룰에 무매치라 루프 없음(라이브 검증). provenance `SOURCE_NAME="enrichment_backfill"`(`SOURCE_PRIORITY` **의도적 미등재** = 기본 99: user 0·chain_ingestion 4를 절대 못 이긴다). 멱등: 재실행은 신규 0 보고. ⚠️ **[`6422326`] 줄 수가 399→388로 줄었다 — 수제 커서 루프 2개가 `keyset_scan.iter_pages`로 대체됐기 때문**이다(`_load_existing_business_keys`·`run_backfill` 각 1곳, [§5-A](#5-a-2026-07-30-신설-서버-모듈-8종)). `import keyset_scan`은 두 곳 모두 **함수 지역 import**라 "직접 import해도 side-effect 없음" 규약이 보존된다. 플래그·stats 키·리포트 형식은 그 커밋에서 **무변경**. 상수 `EXISTING_BK_FETCH_CHUNK=5000`·`PROGRESS_EVERY_CHUNKS=50`·`SAMPLE_NEW_KEYS=20`. **드라이런은 rule에서 `aggregations`를 떼어낸다**(맵퍼 재집계 쿼리를 건너뛴다 — 카운트는 정체성 diff와 무관하다. 이걸 "고치면" 드라이런이 훨씬 비싸진다). 테스트: `tests/test_backfill_enrichment.py` |
| `server/scripts/setup_transfer_plan_indexes.py` (68줄) | [M2] 전사 계획 엔진 진입 필터용 인덱스 **9종**(`INDEXES` 리스트 ~30) `CREATE INDEX IF NOT EXISTS`(테이블별 information_schema 존재 게이트) — `dt_log(tape_lot,tape_slot)`·`dt_log(core_lot,core_slot)`·`dt_map(lot,slot)`·**`map_split_registry(ref_table,map_key)`([M2.6 신설] `validate_plan`이 계획을 통째로 읽는 진입점. 행 수가 맵 수 × legend 값 수로 자란다)**·~~`map_doe(ref_table,map_key)`~~·~~`map_doe_source(ref_table,map_key)`~~(**둘 다 폐기 테이블용 — 물리 DROP과 함께 이 두 줄도 지운다**)·`map_source_region(...)`(휴면)·**`bonding_map(base)`**(Seq Scan 214ms → 0.345ms)·`sample_map(base)`. 뒤 둘은 단일 컬럼이라 "복합"이 아니다. M1 인덱스는 `setup_bonding_plan_indexes.py` 담당 |
| `server/utils/auto_update_control.py` | auto-update 수집기 active 제어 파일(`config/auto_update_control.json`, gitignored) 공용 IO — `read_disabled_scripts`(fail-open)/`set_script_active`(tmp+`os.replace` 원자적 쓰기)/`validate_script_key`(경로 탈출 차단)/`resolve_script_file`. 웹서버 toggle·스케줄러 공유 |
| **`run_decoupled_app.py`(루트, 132 → 228줄)** / `server/run_watcher.py` / `run_chain_worker.py` / `run_graph_sync.py` / `run_auto_update.py` | 프로세스 런처(5-프로세스 토폴로지). **API 서버는 전용 런처 파일이 없다** — `run_decoupled_app.py`의 `main()`(**86**)이 uvicorn을 직접 띄우며, 포트는 **`ASSY_API_PORT`**(기본 `"8080"`), 호스트는 `ASSY_API_HOST`(기본 `"0.0.0.0"`), 🆕 **그래프 싱크 포트는 `GRAPH_SYNC_PORT`(기본 `"8090"`, **107**)이고 바인드 호스트는 `GRAPH_BIND_HOST = "127.0.0.1"`(**34**)** — `run_graph_sync.py`가 루프백에 붙고 API는 `0.0.0.0`에 붙기 때문에 값이 갈린다. ~~`server/run_api.py`~~는 **존재하지 않는다**(2026-07-26 정정).<br>🆕 🔴 **`refuse_if_ports_are_taken(api_host, api_port, graph_port)`(**37**) — 아무것도 띄우기 전에 도는 관문.** 종전엔 **다른 런처가 아직 도는 중에 시작해도 다섯 자식을 다 띄웠고**, 포트를 무는 둘이 3초쯤 뒤 `OSError`로 죽었다. 감독자는 바인드 충돌과 환경 장애를 구분하지 못해 **공유원인으로 분류하고 60초 타이머로 무한 재시도**했으며, `/health`는 **옛 서버가** 503을 답해 운영자는 「중복 기동」이 아니라 「아픈 새 서버」를 읽었다. 🔴 **"Starting AssyManager…" 배너가 관문 *뒤*(**121–124**)로 옮겨졌다** — 기동 선언 다음에 오는 거절은 운영자가 멈춰서 다시 읽어야 하는 종류의 모순이다. 🆕 **`--preflight-only`(**118–131**, `sys.exit(0 if ports_clear else 1)`)** 는 E2E 테스트가 임시 포트로 거절 경로를 몰 수 있게 하는 모드다.<br>**[`8117456`] sleep 루프가 `Supervisor`로 대체됐다** — `specs`는 `ChildSpec(..., heartbeat=…)` 5개(+ 비-server-only일 때 `restartable=False`인 데스크톱 셸), 🆕 **이제 전부 `log_file=paths.log_path("*_stdout.log")`(**156·160·164·167·170·177**)를 달고**, 포트를 무는 둘은 추가로 `ports=`/`port_host=`(**163** 등)를 단다. 🔴 **`paths`를 명시 import(**14**)하는 것이 의도**다 — `ASSY_DATA_ROOT` 단일 오버라이드 지점. **[`90e284f`] `ASSY_ADMIN_TOKEN`은 여기서 상속된다**([§1.6](#16-serveradmin_authpy--어드민내부-토큰-게이트-90e284f-신설)). 테스트: 🆕 **`server/tests/test_duplicate_launcher.py`** — **관문이 어떤 spawn보다도 앞이라는 것과 모든 spec이 `ports=`/`log_file=`을 선언한다는 것을 소스 수준에서 단언**한다.<br>**`run_watcher.py`(341 → 367줄)**: `import internal_event_client`(**44**) · **`API_BASE_URL = internal_event_client.api_base_url()`(**48** — 🔴 모듈 속성 존치는 의도다: `scripts/dev_env/iso_watcher.py:260`이 이 속성을 읽어 격리 워처가 :8080으로 쏘지 않음을 단언한다)** · 🆕 🔴 **`_record_undelivered(endpoint, payload, reason)`(**54**)** · `post_event`(**78** — 🔴 세션은 `internal_event_client.internal_event_session()`, **인증형 거부는 WARNING이 아니라 ERROR로 승격**한다. 🆕 **비-2xx(**103**)와 예외(**106**) 두 갈래 모두에서 마커를 남긴다** — 종전엔 로그하고 반환했고 **「통지를 빚졌다」는 사실이 디스크 어디에도 남지 않았다**) · `trigger_ws_refresh`(**108**) · `trigger_ws_file_processed`(**130**) · `trigger_ws_progress`(**141**) · `trigger_ws_ingestion_state`(**160**) · `reload_watcher_cache`(**176**) · 재처리 폴러 `poll_pending_retries`(**193**) · `main()`(**306**). 🔴 **마커 모양은 체인 워커의 스윕이 이미 걷어 가는 그것과 정확히 같다 — 새 테이블도, 새 재시도 정책도 만들지 않았다**([§1.7](#17-serverinternal_event_clientpy--내부-http-호출의-단일-소유자-23a346d-신설) · [§4](#4-serverchain_ingestion_workerpy--체인-워커)) |
| **`client/desktop_wrapper.py`** (**514줄**, `e9b3a36`) | **[데스크톱 셸 — PySide6/QtWebEngine. 서버 주소를 하드코딩 대신 해석한다.]** `DEFAULT_SERVER_HOST="127.0.0.1"`(~51)·`DEFAULT_SERVER_PORT=8080`(~52)·`SETTINGS_FILENAME="client_settings.json"`(~53)·`class ServerTargetError`(~56)·`settings_file_path`(~60)·`_coerce_port`(~78)·`_parse_host_port`(~99)·`_target_from_settings`(~126)·`_server_arg`(~164)·**`resolve_server_target(argv=None, env=None, settings_path=None)`(~183)**·**`base_url(host, port)`(~216)**·**`extend_no_proxy(host)`(~227)**·`class HybridDesktopClient`(~279)·`register_uri_scheme`(~433).<br>**우선순위 (높은 것부터)**: ① **`--server VALUE`**(`_server_arg`가 손으로 스캔한다 — argparse가 아닌 이유는 `register_uri_scheme()`이 설치한 HKCU 핸들러가 클릭된 `assymanager://` URL을 `argv[1]`로 넘기고 argparse는 그 미지 위치인자에 `exit(2)`하기 때문) ② **`ASSY_SERVER`** 환경변수(**빈 값은 미설정으로 센다** — `set ASSY_SERVER=`가 윈도우에서 변수를 지우는 방법이다) ③ `client_settings.json`(사람이 편집하는 자리지만 **git에 추적**되므로 repo 사본을 고치면 워킹트리가 더러워진다 — 그래서 인자와 env가 위다) ④ 기본값 `127.0.0.1:8080`(대체된 하드코딩과 동일 동작 = 무회귀). 반환은 **`(host, port, source)`**이고 `source`가 있는 이유는 **해석된 주소만으로는 운영자가 자기 편집이 무시됐다는 것을 알 수 없기** 때문이다. 세 인자 전부 주입 가능해 프로세스 기동 없이 우선순위를 채점한다.<br>🔴 **선언이 있는데 무효면 거부하고, 기본값으로 조용히 강등하지 않는다**("미상 != 0"). `_coerce_port`는 `int` 분기 **전에** `bool`을 거부하고(`True`가 포트 1이 되지 않게) 비숫자·`1-65535` 밖·`0`을 거부한다. `_parse_host_port`는 `http` 아닌 스킴을 **벗기지 않고 거부**하고(https를 조용히 http로 강등하면 선언과 다른 것에 붙는다) IPv6 리터럴을 거부한다. 거부 문구가 **의도적으로 ASCII**인 이유: `run_decoupled_app.py`가 감독할 때 이 프로세스의 stdout은 cp949 파이프라 비-ASCII `print`가 `UnicodeEncodeError`를 내고 **거부를 트레이스백으로 바꿔 버린다**. `__main__`에서 해석이 **가장 먼저** 돌아(HKCU 쓰기·네트워크 스택 전에) 거부에 부작용이 없고, 패키징된 exe는 `console=False`라 stderr가 아무 데도 안 가므로 `QMessageBox.critical`도 띄운다. `--print-target`은 GUI·HKCU 없이 우선순위만 검증하는 헤드리스 모드.<br>**`extend_no_proxy(host)`**: 모듈 헤더가 httpx·Qt import **전에** `NO_PROXY="127.0.0.1,localhost"`를 박는데(둘 다 프록시 설정을 즉시 읽는다) 해석된 호스트가 LAN 주소가 되는 순간 그 루프백 기준선이 커버를 멈춘다 — 그리고 프록시가 연결을 먹는 모습은 "서버가 죽었다"와 똑같이 보인다. ⚠️ **한계가 docstring에 명시돼 있다**: httpx 업로드 경로는 커버하지만 **윈도우 QtWebEngine은 확실히 커버하지 못한다**(Chromium이 OS 설정을 본다). ~~`is_port_open`~~은 삭제([§0](#0-묘비-목록--소스에-존재하지-않는-이름)) |
| `server/utils/physical_wafer_engine.py` · `coordinate_transformer.py` | 웨이퍼 물리 좌표 엔진(맵 에디터 서버측) |
| `server/utils/logger.py` (🆕 **221줄** @`34d2518` — 종전 지도의 145줄은 낡은 값) | 프로세스별 로거. **함수 앵커는 라인이 아니라 이름으로**: `class ColoredProcessFormatter` · `get_process_logger(process_name, log_filename)`의 파일 핸들러가 **`paths.log_path(log_filename)`**을 쓴다(격리 프로세스가 사용자의 라이브 로그에 append하지 않는 근거).<br>🆕 🔴 **[`17d8d00`] 콘솔 안전 핸들러가 여기로 왔다 — `class ConsoleSafeHandler(logging.StreamHandler)`가 이 저장소의 유일한 정의다.** `map_alignment._ConsoleSafeHandler`는 이제 **이것에 대한 별칭**이다([§5](#-servermap_alignmentpy--프레임-정렬의-채점자)). 🔴 **구 철자는 실제로 아무 일도 하지 않았다** — `super().emit()`을 `except UnicodeEncodeError`로 감쌌는데 `StreamHandler.emit`이 그 예외를 **자기가 잡아** `handleError`로 보내므로 그 갈래는 **도달 불가**였다(실측: cp949 스트림에 U+2014 → 콘솔 **0바이트**, stderr에 819자 트레이스백, 스톡 핸들러와 동일). 그래서 쓰기를 **여기서 직접** 하고 구조 코드가 그 쓰기를 감싼다. ⚠️ **스트림 *자신의* 인코딩으로 재인코딩하는 것이 의도** — cp949 콘솔에 utf-8 바이트를 밀면 잃는 줄 하나를 **모든 한글 문장의 모지바케**와 맞바꾼다. 파일 절반(utf-8)은 무관.<br>🆕 **`make_console_safe(handler)`** — 남이 만든 콘솔 핸들러에 그 `emit`을 **바인드**한다(uvicorn은 `main:app`을 import하기 전에 자기 핸들러 한 쌍을 설치한다). 객체를 갈아 끼우면 그 소유자가 붙인 포매터·필터까지 버리게 된다. ⚠️ **파일 핸들러는 일부러 건드리지 않는다** — `FileHandler`가 `StreamHandler`의 하위 클래스라 호출부의 `isinstance` 검사가 그것들까지 내민다.<br>🆕 **`NOISY_THIRD_PARTY`** — 루트 로거에 핸들러가 붙으므로 WARNING으로 핀하는 서드파티 로거 목록(전건 열거는 소스). 🔴 **핸들러는 이름 붙은 프로세스 로거가 아니라 *루트*에 붙는다 — 그것이 이 함수의 요점이다**(그러지 않으면 `crud.py`의 미선언 컬럼 경고가 **워처 프로세스의 로그 파일 어디에도 안 남는다**. 블로커 B3) |
| `server/mappers/*` (gitignored) | 사용자 커스텀 체인 맵퍼 — **전수 Grep 시 반드시 포함**. ⚠️ **`paths.py`가 의도적으로 다루지 않는 트리**(데이터가 아니라 코드 — `sys.path`의 패키지로 해석) |
| `server/config/*.json` (gitignored) | table_config·chain_rules·enrichment_rules·ontology_mapping·🆕 **virtual_join_rules**(v2 — `.sample`은 tracked) 등 사용자 설정. 실값을 이 문서에 옮겨 적지 말 것 — 구조만 기술한다.<br>🆕 **[`4e06eec`] `virtual_join_rules.json`**(`.sample` 40줄 tracked) — 선언 1건은 왼쪽 테이블·오른쪽 테이블·양쪽 조인 컬럼·노출 컬럼 목록으로 이뤄진다. **승인은 이 파일이 아니라 `pg_index`가 준다**([§5-C](#5-c-2026-07-31-신설-서버-모듈-2종)).<br>**2026-07-29에 추가된 선언 키 2종(구조만)**: `ingestion_settings.json`의 **`auto_register_map_meta`**(bool, 기본 true — [M3] 인제션 맵 메타 자동 등록 토글, 문서 키 `_auto_register_map_meta_doc`) · `transfer_plan_config.json`의 `stages.*.source.**`transfer_log`**에 문자열 `"none"`**을 허용(7c — "전사 기록 없음"의 **선언**. 문서 키 `__transfer_log_none_comment`). 둘 다 `.sample`에 주석과 함께 tracked |

### 6-1. 설치·개발환경 스크립트 (`8e80fcc`·`4ba13ae`·`47c20f3` 신설)

| 파일 | 책임 |
|---|---|
| `server/scripts/install_product_tables.py` (661줄) | **[제품 소유 테이블 설치기]** `product_tables.PRODUCT_TABLES`를 사이트의 라이브 `table_config.json`에 설치한다. 대상이 **gitignored 사용자 자산**이라 규칙 전부가 그 파일을 지키기 위해 존재한다 — 사이트 소유 엔트리는 **재직렬화하지 않고 바이트 단위 스플라이스**로만 편집해(키 순서·들여쓰기·개행까지 보존) 스크립트가 추가하지 않은 것은 바이트 동일하게 나온다. 부재→추가 / 동일→**무쓰기** / 다름→drift 보고 후 방치(`--overwrite-drift` 필요). **드라이런이 기본**이고 쓰기는 `--apply`, 쓰기 전 타임스탬프 백업, 쓴 뒤 재스캔해 미변경 멤버를 원본과 바이트 비교하고 어긋나면 **백업 복원**. DDL·DB 접속·재기동은 하지 않는다(어느 리로드 경로가 적용되는지 안내만 출력). 종료코드 `0` 할 일 없음 / `1` 조치 필요 / `2` 오류. 핵심 함수: `scan_top_level_members`(~141) `detect_style`(~197) `apply_edits`(~221) `diff_declaration`(~258) **`evaluate(parsed, definitions=None, strict=False)`(~295)** **`build_edits(text, scan, statuses, overwrite_drift, definitions=None)`(~330)** `verify_untouched`(~521) **`run(path, apply_mode=False, overwrite_drift=False, out=None, strict=False)`(~544)** `main(argv=None)`(~617). `--sample --apply`는 tracked 템플릿 `config/table_config.json.sample`을 **생성**한다.<br>**[`0f8d35f` 신설] `--sync-comments`(~637)** — `__comment` 차이도 drift로 취급한다(**실행하려면 `--overwrite-drift`가 함께 필요**). 기본 off인 이유는 주석이 운영자가 손댈 수 있는 유일한 부분이라서이고, 그럼에도 스위치가 필요한 이유는 **낡은 주석이 능동적으로 오도**하기 때문이다(예: 폐기된 바인딩을 여전히 지목). 구현상 `strict = args.sample or args.sync_comments`(~657)이고 `strict`는 정확히 "주석 포함 엔트리 전체 비교"를 뜻한다 — `.sample`이 늘 요구하던 그 판정이다 |
| **`server/scripts/backup_config.py`** (162줄, `b35bc9f` 신설) | **[config 백업 CLI]** `config_backup.py`([§5](#5-소형-서버-모듈))의 운영자 표면 — 서브커맨드 **4종**: `list`(~40, 전 스냅샷 오래된 순) · `check`(~57, 최신 스냅샷 신선도 — 낡았으면 **exit 1**, 모니터링 훅용) · `snapshot`(~73, 즉시 1회) · **`restore`(~90, 스냅샷을 라이브 config 위로 복원 — 덮기 전 현재본을 자동 스냅샷)**. `main()`(~139) |
| **`server/scripts/list_undeclared_tables.py`** (301줄, `b35bc9f` 신설) | **[롤백 진단 — 읽기 전용]** `table_config.json`이 더는 선언하지 않는 **물리 스키마 잔재**를 보고한다. 선언은 one-way door다 — config 워처는 CREATE/ALTER만 하고 **아무것도 DROP하지 않으므로**, 선언을 되돌리면 물리 객체가 어디에도 선언되지 않은 채 남는다(실사례: 폐기 모델의 `map_band_registry`가 빈 테이블로 잔존). 보고 3종: `UNDECLARED TABLE`(빈 것=되돌린 선언 / 채워진 것=레거시 — 함부로 DROP 금지) · `UNDECLARED COLUMN` · `DECLARED BUT MISSING`. DROP문은 **출력만** 하고 실행하지 않는다. `run(db_url, schema, out)`(~172)·`main`(~283). 테스트: `tests/test_undeclared_schema_report.py`(168줄) |
| `server/scripts/dev_env/devenv.py` (372줄) | **[격리 개발환경 CLI]** `DEV_ROOT=<repo>/dev_env`, `isolated_env()`(~71)가 `ASSY_DATA_ROOT`+격리 DB URL을 조립한다. 포트는 `ASSY_DEV_API_PORT`(기본 8081)·`ASSY_DEV_GRAPH_PORT`(기본 8091). 동사: `cmd_bootstrap`(~108, config/워크스페이스 복제 — `SKIP_CONTENT_DIRS={raws,archives,err}`는 구조만 뜨고 내용은 안 뜬다) `cmd_snapshot`(~145) `cmd_up`/`cmd_down`(~217/249) **`cmd_watcher_up`/`cmd_watcher_down`(~256/311 — 워처만 별도 기동)** `cmd_status`(~316) `cmd_env`(~335) |
| `server/scripts/dev_env/iso_watcher.py` (308줄) | **[격리 게이트]** 워처를 띄우기 **전에** 격리를 단언하고, 어긋나면 기동을 거부한다(`EXIT_REFUSED=9`, `REFUSED_MARKER` ~51). `check_static_isolation(...)`(~94, data_root·config·workspace 경로가 `server/` 밖인지) + `check_live_isolation(live_database, engine_url)`(~146, 실제 접속된 DB 이름이 `PRODUCTION_DB_NAMES={"assy_manager"}` ~55에 걸리는지 · 포트가 `PRODUCTION_API_PORTS={"8080","8090"}` ~58인지). 통과 시에만 `GATE_PASSED_MARKER`(~50)를 찍고 `_start_watcher`(~250) |
| `server/scripts/dev_env/snapshot_db.py` (🆕⑤ **437줄** @`831ab68`, 구 등재 420) | **[DB 스냅샷]** 라이브 → QA DB 복제. `open_source_readonly(url)`로 **소스는 읽기 전용 세션**, `CHUNK=1000` 라운드트립(10M행 규율 — 테이블 전량 로드 금지), `EMPTY_TABLES={"database_outbox"}`는 스키마만, `ROW_SCOPED`는 행 한정 복제. `build_target_schema` `copy_rows` `fix_sequences` `run`. 🆕⑤ **[`1260c9b`] `open_source_readonly`는 이제 자기 구현을 갖지 않는다** — `db_safety.open_readonly_engine(...)` + `db_safety.open_readonly_connection(engine)`(기본 `CONNECT_TIME`)를 부르고 해제는 `db_safety.close_readonly_connection`. 남은 것은 **모드 선택뿐**이고 가드 자체는 [§5-C `db_safety.py`](#5-c-2026-07-31-신설-서버-모듈-2종)에 산다. 🔴 **구 등재의 라인 앵커 8개를 걷어냈다 — 전부 밀려 있었다**(예: `open_source_readonly` ~65 → **67**, `build_target_schema` ~153 → **170**, `run` ~242 → **259**) |
| `server/scripts/dev_env/manifest.py` (188줄) | **[변경 매니페스트]** 드릴 전후 파일·DB 상태를 떠서 비교 — `capture_files(root, label)`(~41, `CHURN_DIR_NAMES={raws,archives,err}` ~30 제외) `capture_db(db_url)`(~68) `cmd_capture`(~93) `cmd_diff`(~115) |

### 6-2. 교차 구현 계약 (`contracts/`)

**`0f8d35f` 신설 — 루트 최상위 디렉터리, 현재 **6계약**(`f3fd785`로 `config_resolve_report`, 🆕 `5be96f5`로 **`blank_predicate`**). `server/`도 `client2/`도 아닌 곳에 있는 이유가 곧 정의다: **어느 한쪽의 테스트 자산이 아니라 양쪽이 각각 대조당하는 명세**다. 서버와 클라를 서로 대조하면 둘 다 틀렸을 때 통과한다. 하니스 공통 규율: 대상 함수가 module-private이므로 소스 텍스트에서 함수 선언을 잘라내 `node:vm` 샌드박스에서 평가하고, **추출 실패는 exit 2로 시끄럽게 죽는다**(함수를 못 찾고도 조용히 통과하는 하니스의 초록불은 "양쪽이 일치한다"는 증거로 인용되기 때문). 종료코드 `0` 일치 / `1` divergence / `2` 하니스 자체 실패.

> ✅ **[`5a14e77`] 계약 빌드 게이트 — `client2/scripts/check_contracts.mjs`(73줄).** `pytest server/tests/`는 서버 절반만 채점하고 `client2/package.json`에는 하니스용 스크립트가 없었다. **아무도 돌리지 않는 계약은 주석이다.**
> - **목록이 아니라 발견(discovery)이다** — `contracts/*/client_harness.mjs`를 `readdirSync`로 스캔한다(~41–45). 하드코딩 목록은 이 게이트가 닫는 바로 그 버그를 재생산한다("계약 6호가 착지, 아무도 여기 추가 안 함, 빌드는 초록인 채 사망").
> - 🔴 **빈 스캔은 실패다** — `contracts/` 디렉터리 부재(~36–39)와 **하니스 0개**(~47–50) 둘 다 `fail()` → **exit 1**. 사유가 명시돼 있다: "0 harnesses, all green"은 그것이 대체한 미배선 상태보다 **더 나쁘다**(존재하지 않는 커버리지를 보고한다).
> - **판정은 종료코드만 읽는다** — `map_seam`은 "DECLARED DIVERGENCES"를 출력하고도 exit 0인데, 그것은 벡터가 핀으로 고정한 **이름 붙은 예상 divergence**(헌장 규칙 5: 익명 영구 red 금지)다. 하니스 산문을 여기서 해석하면 파이프라인에 두 번째 채점자가 생긴다.
> - **발견되는 것은 6개**(2026-08-04 실측 — `contracts/*/client_harness.mjs`를 `readdirSync`로 스캔): `band_arithmetic` · 🆕 **`blank_predicate`** · `config_resolve_report` · `doe_band_rules` · `legend_map_scope` · `map_seam`.
> - 🆕 🔴 **`contracts/blank_predicate/`(`5be96f5` 신설) — 「비었다」와 「숫자를 텍스트로 어떻게 쓰는가」의 파이썬/SQL 대조.** 채점 대상은 [`crud.is_blank_value`/`blank_sql_condition`/`blank_to_null`/`not_blank_sql_condition`/`numeric_text_sql`](#2-serverdatabasecrudpy--레이어링-코어)이고, 벡터가 **방언 사실(`dialect_facts`)까지 핀한다**(PostgreSQL은 float8 7.0을 `'7'`로, SQLite는 `'7.0'`으로 렌더한다 — 2026-07-31 실측). 🔴 **선언된 divergence `FLOAT_EXPONENT`가 있다**: `str(1e16)`이 파이썬에서 `'10000000000000000'`, Postgres에서 `'1e+16'`이다. **BIGINT 안전 상한 밖에서만 드러나므로 쫓지 않기로 이름 붙여 고정했다**(헌장 규칙 5: 익명 영구 red 금지). 계약은 파이썬 절반(`test_predicate_contract.py`)과 클라 절반(`client_harness.mjs`)을 **같은 `vectors.json`에 채점**한다.
>
> ✅ 🆕 **[`5656fa7`] 두 번째 빌드 게이트가 생겼다 — `client2/scripts/check_harnesses.mjs`(120줄).** **직전 지도가 "총괄 결정 사항(보드 F10)"으로 남겨 둔 구멍이 닫혔다.**
> - **`package.json` 실측(HEAD)**: `"check:clipboard"` · `"check:contracts"` · **`"check:harnesses": "node scripts/check_harnesses.mjs"`** · `"prebuild": "npm run check:clipboard && npm run check:contracts && npm run check:harnesses"` · `"build": "vite build"`. 🔴 **`check:suggest-keys`는 prebuild 체인에서 빠졌다** — 스크립트 정의는 남아 있지만(손으로 부를 수 있다) `value_suggest_keys_harness.mjs`는 이제 **이름이 아니라 발견으로** 실행된다. 직전 지도가 "세 번째는 발견이 아니라 이름이다"라고 지적한 그 형태가 사라진 것이다.
> - **여기도 목록이 아니라 발견이다** — `client2/tests/*.mjs`를 `readdirSync`로 스캔한다(~61–64). 러너 헤더가 그 이유를 적어 두었다: "하니스 #16이 착지하고 아무도 여기 추가하지 않으면 그것은 도착 즉시 죽은 것"(DISCOVERY, NOT A LIST).
> - 🔴 **`KNOWN_RED`는 스킵 목록이 아니라 부채 목록이다**(~43–54). 빨간 하니스도 **실행되고 실패로 보고**되며, 다만 빌드를 막지 않는다 — 기존 red 위에 빌드를 세우는 것은 게이트가 아니라 장애이기 때문이다. 각 항목이 사유를 달고 있고, **초록이 되는 순간 러너가 소리 내어 말한다**(`recovered` → "목록에서 빼라"). 조용한 스킵은 게이트가 없는 것과 같은 결함이다.
> - 🔴 **초록이었다가 빨개진 하니스는 빌드를 막는다**(`blocking`) — 그리고 실패 시 **그 하니스 자신의 출력을 그대로 흘린다**(어느 단언이 어떤 값으로 실패했는지는 하니스만 안다. 여기서 재요약하면 정확히 그것을 잃는다).
>
> 🔢 **하니스 전수 채점 (2026-07-31 실측, `node client2/scripts/check_harnesses.mjs` 실행 — 워킹트리 `client2`가 HEAD와 바이트 동일임을 `git hash-object`로 확인한 뒤)**: 러너 요약은 **`16 harnesses ― 11 gated, 5 on the known-red debt list (5 still red, 0 recovered)` + `✓ every gated harness is green.`**(exit 0)
>
> ⚠️ **파일 수 ≠ 하니스 수다.** `client2/tests/`에는 **17개 파일**이 있고 그중 `seam_7b_oracle.py`(187줄)는 **Python이라 스캔 대상이 아니다.** 그래서 러너가 세는 것은 **`.mjs` 16개**다. 구 지도의 "15"는 `geometry_origin_reseat_harness.mjs` 신설로 낡았다.
>
> ✅ **게이트 초록 11** (괄호는 줄 수, 값은 전부 2026-07-31 개별 실행 실측):
> - `company_roundtrip_harness.mjs`(1,065) — **77 passed / 0 failed**, 뮤테이션 **18/18**. 🆕 **직전 패스의 red가 고쳐졌다**(당시 사인은 `getGridCellObject`가 부르는 좌표 함수가 `SHARED_FNS`에 없어 나던 `ReferenceError`).
> - `copy_header_count_harness.mjs`(**1,168**, 1,076에서 +92) — **107 passed / 0 failed**, 뮤테이션 **12/12**. 🆕 **역시 고쳐졌다.** 이 파일은 개명 대조표를 **이름으로** 들고 있다(`['getDieIndex','getPhysicalCoords'], ['getDbCoords','getVisualCoords']` ~152) — 옛 이름이 여기 남아 있는 것이 옳다([§0 ⑪-b](#0-묘비-목록--소스에-존재하지-않는-이름)).
> - `effort_meter_harness.mjs`(757) — **131 passed / 0 failed**
> - 🆕 **`geometry_origin_reseat_harness.mjs`(760, `4761a3a` 신설)** — baseline **31 assertions / 0 실패**, 뮤테이션 **7/7**. **`reseatCellsToStoredCoords`의 채점자**다([§7](#7-client2src--웹-클라이언트)).
> - `m4_symbol_extractability_probe.mjs`(258) — **15 checks / 0 failed**
> - `map_key_canonical_harness.mjs`(425) — **116 passed / 0 failed**
> - `push_gate_harness.mjs`(147) — **15 passed / 0 failed**
> - `standard_frame_origin_harness.mjs`(**477**, 469에서 +8) — baseline **19 assertions / 0 실패**, 뮤테이션 **7선언/7적용/7명명포착/미탐지 0**
> - `valid_die_head_parity_oracle.mjs`(**211**, 185에서 +26) — **24 프레임 · 17,496셀 비교 / 0 차이**, 음성 대조 28셀 · red-proof 139셀. 이 파일도 개명 대조표를 들고 있다(~60).
> - `valid_die_origin_alignment_harness.mjs`(**715**, 707에서 +8) — baseline **153 comparisons / 0 실패**, 뮤테이션 **10/10**
> - `value_suggest_keys_harness.mjs`(1,901) — 뮤테이션 **34선언/34적용/34포착**
>
> 🔴 **known-red 5** — **전부 실행되고 전부 실패로 보고되며 아무것도 빌드를 막지 않는다.** 각 항목의 **러너 라벨**과 **실측**을 나란히 적는다:
> - `effort_instrument_harness.mjs`(474) — 라벨 *"throws during setup"* / 실측 **`ReferenceError: pushBlockingCount is not defined`**(0개 채점). 그 함수는 지금도 소스에 실재한다(`map_editor.js` **~3075**) — **하니스의 추출 목록이 원인이고 애플리케이션이 아니다.**
> - `reposition_regime_probe.mjs`(205) — 라벨 *"ERR_INVALID_ARG_TYPE ― a path/arg it reads has moved"* / 실측 동일. ⚠️ **이것은 하니스가 아니라 측정 프로브다** — `node … <cells.json> <frames.json>`이 계약이라 인자 없이 돌면 죽는 것이 정상이다. **`KNOWN_RED`에 들어간 것은 그 정상을 게이트가 red로 읽기 때문**이고, 러너가 `*.mjs` 전량 발견 방식인 한 이 항목은 구조적으로 여기 남는다.
> - `split_registry_harness.mjs`(272) — 라벨 *"symbols it slices were renamed"* / 실측 **`Error: const DEFAULT_LEGEND not found`**([§0](#0-묘비-목록--소스에-존재하지-않는-이름) ②-b). 몇 주째 사문이다.
> - `valid_die_authoring_harness.mjs`(681) — 라벨 *"98 passed / 1 failed"* / 실측 **일치**(뮤테이션은 **19/19** 포착). 실패 단언은 `[INV-6] resolveValidDie runs the chain check before projecting the cells`이고 판정식이 **소스 텍스트의 등장 순서**(`indexOf`)다. 🔴 **실행 순서 불변식은 지켜지고 있고 빨간 것은 그 불변식의 대리 측정치다** — `indexOf`는 주석과 코드를 구분하지 못한다.
> - `valid_die_frame_adoption_harness.mjs`(**1,700**, 1,692에서 +8) — 🔴 **라벨은 *"28 of 228"*인데 실측은 `baseline: 228 assertions, 41 failure(s)`다.** ⚠️ **라벨은 정적 문자열이지 살아 있는 점수가 아니다** — `check_harnesses.mjs`의 `KNOWN_RED` 맵에 손으로 적힌 값이고, 하니스가 더 빨개져도 그 문자열은 따라오지 않는다. **이 수를 인용해야 하면 라벨이 아니라 실행에서 가져와라**(3회 반복 실행 모두 41로 결정적). 실패는 `F6/*`(F8 알림·저장 좌표 보존 계열) · `O/specimen`·`O/aligned`·`O/rot-only`(원점 경보 계열)에 몰려 있고, 대부분이 **`da8f390` 이전 계약을 붙들고 있는 픽스처**다. **어느 쪽이 옳은지는 이 지도가 판정하지 않는다** — 처분은 맵 도메인 소관이다.
>
> 🔴 **`map_editor.js`의 소스 주석이 이 실패 양식을 미리 적어 두었고, 개명 라운드가 그 경고를 그대로 이어받았다**(**1438–1440**, `getDieIndex` 헤더): *"이 두 함수를 슬라이스해 실행하는 하네스가 넷이고, 모듈 전역 의존이 하나 늘 때마다 넷이 전부 `ReferenceError`로 죽는다."* 그래서 패리티 항은 **인라인**이다. 같은 경고가 `waferMmToDieCell` 위(**1558**)와 `getWaferBoundingBox`(**1702**)에도 있다. 🆕 **`resolveValidDie`의 격자 확장 블록에 있던 같은 경고는 이번에 `fitGridToMask`(8283)의 헤더 주석으로 옮겨졌다** — 그 함수가 **모듈 상태를 0으로** 유지하는 것이 정확히 이 경고에 대한 답이다.
>
> 🔬 **직전 지도가 "F10 결정 사항"으로 남긴 여섯 가지 사실 중 다섯이 이 라운드에 해소됐다.** 남은 하나는 **`reposition_regime_probe.mjs`**다 — 발견 방식이 `*.mjs` 전량이면 **인자를 받는 프로브가 새 거짓 실패가 된다**고 직전 지도가 정확히 예측했고, 지금 그것이 `KNOWN_RED`의 한 줄로 살아 있다. 예측은 맞았고 처분은 "부채 목록에 이름을 달아 둔다"였다.

| 파일 | 책임 |
|---|---|
| **`contracts/config_resolve_report/vectors.json`** (**295줄**, 290에서 **+5**, `"version": 1`) | **[「내 config가 먹었는가」의 정본 명세 — [§5-B](#5-b-serverconfig_resolve_reportpy--내-config가-먹었는가의-답-f3fd785-신설)와 클라 렌더러가 같은 답을 내야 하는 지점.]** 최상위 키: `vocabulary`(**`reasons` 4 · `populations` 3 · `scopes` 4 · `origins` 2**) · `reason_meanings`(5) · `envelope`(6 — `top`/`domain`/`entry`/`source`/`setting` 형태 선언) · **`invariants`(8)** · `forbidden_client_literals` · **`cases`(8)** · **`settings_cases`(3)** = **케이스 11건**(2026-07-30 다섯 번째 패스 재계수 — 케이스 수는 그대로다). 케이스 이름이 곧 명세다 — `live_production_state_2026_07_30` · `declared_on_a_view_that_cannot_see_the_whole_key` · `knob_absent_reads_the_same_class_but_not_the_same_sentence` · `non_boolean_knob_is_rejected_not_merely_ignored` 등.<br>🔴 **불변식이 7 → 8로 늘었다**(`f9289f6`): INV-F9-1 모든 `ineffective`/`rejected`는 사유를 이름으로 댄다 · **-2** 모든 `effective`는 `reason == null` · **-3** 모든 사유·경고는 `vocabulary.reasons`에서 온다 · **-4** 모든 항목은 비어 있지 않은 `detail`을 갖는다 · **-5** `counts`는 목록 길이와 같다 · **-6** 파일 부재는 `exists: false`이지 rejection이 아니다 · **-7** 클라는 `forbidden_client_literals`를 하나도 갖지 않는다 · 🆕 **-8 모든 `detail`은 완성된 문장이다 — Python repr도, 생 마크업도 안 된다.** 사유가 벡터에 그대로 적혀 있다: INV-F9-4는 `detail`이 **비어 있지 않을** 것만 요구했고, 초판은 `['lot'](으)로만`·`**아무 효과가 없습니다.**`를 출하했다 — **계약이 클라가 그대로 렌더한다고 못박은 텍스트 안에서** Python 리스트 repr과 생 별표다. 클라는 자기 문장을 조립하는 것이 금지돼 있으므로 **서버가 내보낸 것이 곧 운영자가 읽는 것**이고, 반쯤 포맷된 문자열은 하류에서 고칠 두 번째 기회가 없다. 되돌려 보여 주는 값은 **운영자가 편집한 파일의 문법(JSON)**으로 적는다([§5-B `_names`/`_as_json`](#5-b-serverconfig_resolve_reportpy--내-config가-먹었는가의-답-f3fd785-신설)).<br>**`forbidden_client_literals.literals` = 사유 4단어**(`allow_paths`는 **빈 배열** — 예외가 없다). 이 어휘는 응답 안에 실려 오므로 클라가 **순회하는 것은 정당**하고, **적어 두는 것**이 금지다 |
| **`contracts/config_resolve_report/test_report_contract.py`** (**517줄, 23건** — 460/21에서 **+57줄/+2건**, `grep -c "def test_"` = 23) | 서버 측. `contracts/` 밑에 있는 이유는 `map_seam`과 같다(라운드 중 여러 에이전트가 같은 트리를 연다). **기본 스위트 편입은 `server/tests/test_config_resolve_report_contract.py` 심(shim, 61줄)이 한다** — `map_seam`과 **같은 형태·같은 사유**(커맨드라인에 경로를 주면 pytest가 `testpaths`를 무시한다). 🔴 **심은 계약 파일이 없으면 skip이 아니라 `RuntimeError`로 죽는다** — 조용히 아무것도 안 덮는 심은 심이 없는 것보다 나쁘다. 심 자신의 단언은 하나(`test_shim_reexports_every_contract_test`): 재수출 집합이 **개수가 아니라 집합**으로 일치하는가. 라우트 쪽 테스트는 별개로 `server/tests/test_config_resolve_routes.py`(**256줄, 10건**) |
| **`contracts/config_resolve_report/client_harness.mjs`** (**353줄**, 153에서 **+200**, `93610cb`) | **클라 측 — 이제 절반이 아니라 전부를 채점한다.** 🔴 **INV-F9-7은 구현의 존재를 필요로 하지 않는다**: `client2/src` 전역을 훑어(2026-07-31 실행 시 **29파일 스캔**) 사유 4단어가 **소스 리터럴로** 있는지 본다. 클라가 그 단어를 적어 두는 순간 「무엇이 효과 없음인가」에 대한 자기 의견을 갖게 되고, **양쪽이 어긋나도 서버 테스트는 전부 초록**이다 — U6가 6개를 삭제한 그 계급이며 grep은 클라 코드 첫 줄부터 잡는다.<br>🆕 **직전 지도가 `PENDING`으로 이름 붙여 두었던 나머지 절반(INV-F9-4의 「렌더된 문장 == 서버 `detail`」)이 채점되기 시작했다** — 렌더러가 착지했기 때문이다. 하니스가 `client2/src/config_resolve_view.js`를 **직접 import해**(~142) 뷰 모델을 돌리고, **그것이 내보내는 모든 문자열의 출처를 4종으로 분류**한다(`server`/`value`/`chrome`/`count`, `scoreTexts` ~228). 2026-07-31 실행: **`159 rendered string(s)`가 전부 payload 또는 클라의 frozen label table로 추적된다**, exit **0**.<br>⚠️ **이 채점이 가능한 것은 렌더러가 DOM-free 모듈로 분리돼 있기 때문**이다 — DOM을 인라인으로 짓는 렌더러는 node에서 채점할 수 없다([§7 `config_resolve_view.js`](#7-client2src--웹-클라이언트)) |
| `contracts/band_arithmetic/vectors.json` (243줄) | **[레거시 `bands` 산술의 정본 명세.]** 폐기 모델이지만 `map_split_registry.bands`에 실계획이 남아 있고 서버가 여전히 이 규칙으로 읽는다(`bands_to_zones` 마이그레이션 경로 포함). 벡터 **37건 / 5그룹**: `to_cases`(7) `sequence_cases`(7) `normalization_cases`(5) `materials_cases`(7) `material_split_cases`(11). **의도적으로 좁힌 계약이며 JS 강제변환의 이식이 아니다.** `NaN`/`Infinity`는 JSON이 표현하지 못해 저장 컬럼으로 도달 불가라 일부러 빠져 있다. 소비자 둘: **pytest** `server/tests/test_transfer_plan.py` · **node 하니스**(아래). ⚠️ `material_split_cases.no_separator`에 **`$superseded` 마커**가 붙었다(`269b39e`) — `splitMaterialId`에는 여전히 맞지만 후속 토큰 문법(doe_band_rules)에서는 맨 식별자가 로트 전체다. **`splitMaterialId`를 지우는 같은 커밋에서 지워야 한다** |
| `contracts/band_arithmetic/client_harness.mjs` (288줄) | **클라 측 대조기 — 읽기 전용.** **[`b35bc9f` 재편]** 추출 대상 **4종**: `transfer_plan.js`의 `bandToState`·`prevTo`·`splitMaterialId` + `map_editor.js`의 `normalizeBands`. **은퇴 4종(`bandTo`·`bandLayers`·`bandTotal`·`bandShare`)은 이제 부재를 능동 단언한다**(`RETIRED_CLIENT_FNS` ~75 — transfer_plan.js에 되살아나면 exit 2. 층 산술의 두 번째 구현이 곧 이 계약이 막는 divergence다 — 그 커버리지는 `doe_band_rules`의 `demand_cases`로 이전됐다). 실행: `node contracts/band_arithmetic/client_harness.mjs [--json]` |
| **`contracts/doe_band_rules/vectors.json`** (**762줄**, `269b39e` 신설 · `b35bc9f` 확장 · `2baf9ff` v3 = marker 축) | **[ZONE 모델의 정본 명세, `"version": 3`.]** **132건 / 11그룹**(2026-07-30 전건 재계수 — 구 지도의 131은 낡았다, `paste_cases`가 15→**16**): `stack_cases`(13 — 0/`'0'`→`marker` 포함) `zone_extent_cases`(8) `plan_cases`(17 — **차단 규칙 V1–V6**) `material_token_cases`(21 — `lot[_slot][:BIN]` 문법) `demand_cases`(9 — ceil을 round·floor 양쪽과 대조해 고정) `rollup_cases`(6) `remaining_cases`(7) `tsv_cases`(15) **`paste_cases`(16)** **`roundtrip_cases`(9 — Excel 왕복)** `legacy_band_cases`(11). 소비자 둘: **pytest** `server/tests/test_doe_zone_model.py` · **node 하니스**(아래) |
| **`contracts/doe_band_rules/client_harness.mjs`** (**597줄**) | 클라 zone 모델 대조기 — `doe_bands.js`에서 잘라낸 함수들 + `transfer_plan.js`의 `bandToState`·`prevTo`(단일 정수 판독기·단일 레거시 걷기를 **재타이핑하지 않고 추출** — 사본 하니스는 앱과 어긋나도 통과한다). V1–V6, zone 기하, 토큰 문법, 수요 산술, **Excel 왕복**을 채점. **[`2baf9ff`] fixture 불활성 가드**: `plan_cases`에 bare-marker SILENT 케이스와 V6 모순 케이스가 **둘 다** 없으면 exit 2 |
| **`contracts/legend_map_scope/client_harness.mjs`** (651줄, `269b39e` 신설 · **U6 `95bf072` 추출 대상 교체**) | **[legend map-key 스코프 계약 — 벡터 파일 없음, 하니스 단독.]** 단언: 맵이 열려 있을 때 화면의 legend와 **특히 그것으로 지은 `replace_map` 페이로드**는 이 맵이 보증하는 값만 담는다. 기원 결함: 테이블 전체 읽기(map_key 필터 없음, 값 dedup)로 legend를 시드해 **남의 맵 값이 이 맵의 계획으로 저장**됐다(프로덕션에서 `elle` 1값이 bonding_map 4키로 전파). **시드는 삭제됐다**(2026-07-28) — 패널 오픈은 이 맵의 registry 행 \| 빈 DOE 1행(`vocab: true` 플레이스홀더) 두 갈래뿐. 하니스는 `map_editor.js`에서 const(`SPLIT_KEY_SEP`·`FP_UNIT`·`FP_ROW`·`SPLIT_REGISTRY_TABLE`·`REGISTRY_SCOPES`·`ZONE_COLUMNS`·`LEGEND_PAYLOAD_COLUMNS`)와 쓰기 경로 함수들을 추출해 **실제 페이로드 조립을 끝까지 돌려** 검사한다. **[U6] 추출 대상 교체**: ~~`DEFAULT_LEGEND`~~ → **`EMPTY_DOE_SEED` + `defaultLegendRows`**(하니스는 `overlayContract = null` 프리앰블로 돌린다 — 시딩 2갈래 계약이 다루는 것이 바로 그 "선언 없음" arm이다) |
| **`contracts/map_seam/vectors.json`** (**3,613줄**, **`"version": 4`**, M4② 착지로 확장) | **[맵 이음매(seam)의 정본 명세 — 클라의 답과 서버의 답이 같은 답이어야 하는 지점.]** 3개 불변식 계열 한 파일: **7b** 맵 정체성 키 · **7c** `transfer_log:"none"`과 상한 `≤N` · **M4①②** `valid_die_ref`(원 기하가 아니라 **참조된 맵**이 근거). 모든 케이스가 `$source`를 달고 있다 — **먼저 읽은 구현에서 베낀 기대값은 하나도 없다**. **166건 / 20그룹**(2026-07-30 전건 재계수 — 구 지도의 127/17은 낡았다): 7b `canonical_value_cases`(17)·`canonical_value_server_only_cases`(3)·`compose_cases`(12)·`compose_divergence_cases`(3)·`decompose_cases`(5)·`decompose_lossy_cases`(3)·`canonical_map_key_cases`(6) · 7c `chips_bound_cases`(6)·`transfer_log_declaration_cases`(8)·`remaining_display_cases`(8)·`untracked_flag_cases`(7) · M4① `mask_baseline_cases`(16)·`valid_die_ref_parse_cases`(15)·`valid_die_ref_home_divergence_cases`(3)·`valid_die_basis_cases`(8)·`valid_die_refused_render_divergence_cases`(4)·`valid_die_ref_canonical_cases`(3) · **M4② 신설 3그룹 `valid_die_authoring_cases`(14)·`valid_die_chain_cases`(14)·`valid_die_push_decision_cases`(11)**.<br>✅ **`pending` 심볼이 0개다** — `client_symbols` 25종·`server_symbols` 14종 전부 `live`. 구 지도가 "현재 M4 phase 2 계열이 `pending`에 있다"고 적은 상태는 **해소됐다**(클라 쪽 `applyValidDieRef`·`validDieChainError`·`validDieRefDisplay`가 착지했다 — [§7](#7-client2src--웹-클라이언트)). `client_consts`(3).<br>🔴 **`known_defects`는 여전히 `D1` 하나**(블록의 다른 키는 `$comment`다) — `physNum`의 `v \|\| dflt`가 선언된 `0`을 기본값으로 바꾼다. 핀은 **strict xfail**: 오늘 실패해야 하고 결함이 고쳐지면 **반대 방향으로 빨개진다**(STALE_PIN), 그리고 **자기충족 금지**(양 채점자가 모든 `client_actual`이 계약값과 **다름**을 단언한다 — 계약값과 같은 핀은 아무것도 단언하지 않으면서 어떤 벡터든 영구 초록으로 만드는 방법이 된다). ⚠️ **D1의 `site`가 `map_editor.js:1541-1548`로 적혀 있으나 HEAD 실제 `physNum`은 **~1728**다**(+187, 2026-07-31 재측정) — contract-keeper 소관이라 여기서 고치지 않았다 |
| **`contracts/map_seam/client_harness.mjs`** (**1,286줄**) | 클라 측 대조기 — `map_editor.js`·`transfer_plan.js`에서 함수를 추출해 **실제 파스 체인을 끝까지** 돌린다(마스크는 손으로 지은 physConfig가 아니라 `physNum`→`getTransformedPhysicalConfig`→`getScreenShift`→`isCellInsideWaferFast` 경유). **`FN`은 Proxy** — 매니페스트에 없는 심볼을 부르면 "이건 하니스 버그지 클라 divergence가 아니다"라고 밝히며 exit 2. **`unscoreable` 배열**(~224)로 **이 하니스가 채점을 거부하는 축**을 이름과 함께 출력한다(~1108–1112) — 예: 쓰기 방향은 리더만으로 채점 불가라 "meta after unset"을 손으로 적으면 `parse(null)`을 재검사할 뿐이다. 실행: `node contracts/map_seam/client_harness.mjs [--json]` |
| **`contracts/map_seam/test_seam_contract.py`** (**1,544줄, 58건** — 2026-08-05 재계수 `grep -c "def test_" = 58`, 구 지도의 1,372줄/52건은 낡았다) | 서버 측. `contracts/` 밑에 있는 이유는 라운드 중 세 에이전트가 같은 트리를 여는데 계약 착지가 남의 머지 컨플릭트가 되면 안 되기 때문. **기본 스위트 편입은 `server/tests/test_map_seam_contract.py` 심(shim)이 한다** — `testpaths`가 아니라 심인 이유: **커맨드라인에 경로를 주면 pytest는 `testpaths`를 무시한다**(`_pytest/config`: `if args: result = args`). 이 repo의 문서화된 명령은 전부 `server/tests/`를 명시하므로 testpaths 수정은 배선처럼 보이고 아무것도 안 덮었을 것이다. 심은 자기 건강검진 하나만 갖는다(재수출 집합 비교 — **개수가 아니라 집합**).<br>🔴 **실행은 `-rs`까지가 명령이다** — `conda run -n assy_manager python -m pytest server/tests/ -q -rs`. 계약은 심볼 상태 3종을 쓰는데(`symbol_status`, vectors.json) 그중 **`pending`만 조용하다**(구현보다 먼저 쓴 벡터 = 아직 채점할 게 없는 게 정상. 착지하는 즉시 자동 채점되고, 착지 후에도 `pending`으로 남아 있으면 **STALE PENDING 하드 실패**). 총괄 규칙이 "**pending은 스위트를 막지 않고 라운드 종료를 막는다**"인데 그 규칙은 pending이 **이름과 수로 보일 때만** 성립한다 — 맨 `-q`는 "10 skipped" 숫자만 주고 무엇이·누구 것이·무엇을 막는지는 안 준다. ⚠️ 플래그는 빠뜨릴 수 있다: 못 잊게 하려면 `pyproject.toml`의 `[tool.pytest.ini_options] addopts = "-rs"`가 견고한 형태이고, 그건 repo 전역 변경이라 총괄 결정 사항 |

> **왜 이 계약들이 존재하는가 (실제 사고)**: ① 같은 JSON에서 클라와 서버가 다른 숫자를 유도했다 — `Number("  ")`는 0이라 `prevTo` 걷기를 멈췄고 `float("  ")`는 예외라 건너뛰어서, `[10, "  ", 20]`이 화면에서 20층·서버에서 10층이 됐다. ② 클라 `normalizeBands`가 자체 `Number()`를 돌려 `"0x10"`을 16으로 고쳐 저장했다(오류가 이미 데이터가 돼 화면에 안 보였다). ③ zone 모델에서도 같은 계열이 재발했다 — U+001F로 조인한 자재 풀 키가 디스크에서 분리자를 잃어 `MID1_12:3`과 `MID11_2:3`이 한 롤업 행으로 합산됐다(230 assertion이 아니라 **뮤테이션 테스트**가 잡았다).

---

## 7. `client2/src/` — 웹 클라이언트

Vite + Vanilla ESM + AG-Grid. 상태는 `state.js` 싱글턴(리액티브 아님 — 변조 후 명시적 리프레셔 호출).

> 🆕⑥ 🔴 **[2026-08-13 `vite.config.js` 실측 정정] 멀티페이지 엔트리는 6이 아니라 7이고, 종전 목록은 없는 것 하나를 담고 있고 있는 것 둘을 빠뜨렸다.** 실측(`aeddac8`의 `build.rollupOptions.input`) — `main`(index.html) · `admin` · `map_editor` · **`map_editor2`** · `graph` · `trace` · **`ledger`**. ~~`enrichment`~~는 `ab36fab`이 페이지와 함께 걷어 갔다(위 표의 해당 행). 🔴 **`trace`와 `ledger`는 서로 다른 화면이다** — 앞은 `/graph/trace`(G2 지식그래프 보고서, [§7 `trace.js`](#7-client2src--웹-클라이언트)), 뒤는 `/api/ledger/trace`(정본 원장 계보 walk, [§5-H](#5-h-정본-원장-canonical-ledger)). 소스 주석이 합치지 않은 이유를 적고 있다: 「어느 주장이 왜 이겼는가」를 보여 주는 화면을 「무엇이 연결돼 있는가」를 보여 주는 화면 뒤에 두게 된다.

> 🔴 **[2026-08-04] `map_editor.js`가 이음매를 따라 쪼개지는 중이다 — 이 절을 읽는 방식이 그래서 바뀌었다.**
> - 이번 라운드에 **두 모듈이 그 파일에서 잘려 나왔다**: 🆕 `map_key.js`(158줄) · 🆕 `split_registry_row.js`(366줄). **여섯 건이 더 예정돼 있다.**
> - **추출의 성립 조건은 「모듈 상태 0」이었다.** 두 파일 다 top-level `let`이 하나도 없고 필요한 것을 **인자로 받는다** — 상태를 가진 절반(`legendReplaceScope`·`legendConflict`·IO)은 `map_editor.js`에 남았다. 그 선이 다음 여섯 건의 경계선이기도 하다.
> - ⚠️ **그래서 **아래 `map_editor.js` 절**에는 라인 계단표가 없다.** 계단표는 다음 추출에서 통째로 거짓이 되는데 **거짓이 됐다는 신호를 내지 않는다.** 심볼명이 1차 식별자이고 라인은 보조다.
> - ⚠️ **두 신설 모듈의 module-private 심볼을 개명하지 마라** — 계약 하니스들이 그 이름들을 텍스트로 슬라이스한다. **import하는 곳이 없어도 개명하면 계약이 깨진다**([§0 ⑬](#0-묘비-목록--소스에-존재하지-않는-이름)).

### `state.js` (**187줄** @`dab9152` — 162에서 **+25**) — 전역 싱글턴

> 🆕🆕🆕 **[2026-08-11 후속 · `dab9152`] 셀/행 이력 페이징 세션 필드 4종 신설**: **`cellRowHistoryCursor`**(null이면 무커서 — 다음 페이지 없음) · **`cellRowHistoryTruncated`**(bool) · **`cellRowHistoryLoaded`**(로드된 건수 — `cellRowHistoryData.length`가 아니다: 그 배열은 라이브 WebSocket append도 같이 받으므로 페이지 카운트와 어긋난다) · **`cellRowHistorySession`**(매 `loadHistory()` 호출마다 `+=1` — `timeline.js`의 `beginHistorySession()`이 이것을 건드리는 유일한 지점, 진행 중인 「더 보기」 응답이 늦게 와도 세션 불일치로 버려진다). 🔴 **`cellRowHistoryData` 자신은 평범한 배열로 남아야 한다**는 것이 소스 주석의 명시적 계약이다 — `renderTimelineIncremental`/`appendHistoryLocally`(둘 다 `timeline.js`)가 WebSocket 도착 시 그 배열에 직접 `unshift`/`some`한다.
>
> 🔴 **[정정] `currentColumns`의 소비자 목록이 넷에서 셋으로 줄었다.** `api.js`의 검색 드롭다운이 **그 목록에서 빠졌다** — 이제 그 드롭다운은 `join_resolved_columns`까지 제안한다(아래 `api.js` 참조). 남은 셋: `clipboard.js`의 복사 술어 · `grid.js`의 편집 가능성 · (`/schema.columns` 경유) `map_editor.js:getUnprotectedPushColumns`.
- `state` 객체: gridApi, currentTable/Columns/Types, 비즈니스키(`currentBusinessKey`/`currentCompositeKeySources`), ws, 셀 선택(`selectedCell`/`selectedCellsMap`/드래그), 이력 탭 데이터, 페이징(`currentSkip`/`pageCache`/`viewMode`), 트랜잭션 모드(`txModeActive`/`pendingTxEdits`), `isDesktop`.
- 🆕 **[`c3a5239`] 스마트 페이스트 래치 2필드(~34–43)**: **`smartPasteArmedUntil`**(타임스탬프, `0` = 미무장 — 다음 `paste` 이벤트를 **파서로** 보낼 창) · **`smartPasteArmedTable`**(무장 시점의 테이블). 🔴 **상태가 `state.js`에 있는 것이 계약이다** — 무장은 `main.js`가 하고 소비는 `clipboard.js`의 `paste` 리스너가 하므로 둘 사이에 공유 자리가 필요하다. 두 번째 필드가 있는 이유: 이 경로는 **인제션**이라 붙여넣기가 도착하기 전에 테이블이 바뀌었으면 **거부**해야 한다(엉뚱한 테이블에 들어간 파일은 미관 문제가 아니라 데이터 오류다).
- 🆕 **[`cd3e0f4`] 가상 컬럼의 클라 절반이 여기서 시작한다**: **`currentVirtualColumns`(~19)** — `/schema`가 덧붙여 알린 컬럼(`{name, type, editable:false, right_table, rule, unresolved_label}`) · **`currentJoinResolvedColumns`(~35)** — 노출 컬럼 전량 + `kind`(`collide`/`virtual_only`). 🔴 **둘이 갈린 것이 계약이다**: 앞은 「저장 컬럼이 아니다」(편집 금지 판정), 뒤는 「이 값은 조인으로 해석됐다」(표시·필터 판정). 하나로 합치면 collide 컬럼이 편집 불가로 잠긴다.
- export: **`isVirtualColumn(colId)`(~89)** · **`joinResolvedColumn(colId)`(~109)** · `updateVisibleColIndexMap()`(**~115**). 🔴 **판정 구현은 이 둘뿐이다** — `grid.js`도 `main.js`도 `state.currentVirtualColumns`를 직접 훑지 않는다.

### `effort_meter.js` (**599줄** @`ab36fab` — 580에서 **+19**, 주석만) — **핵심가치 #1 계기의 유일한 수집기**
무DOM 상태·무UI(배지도 토스트도 없다). 6엔트리 **전부**가 이 한 모듈을 import한다 — 페이지마다 카운터를 두면 그 순간 계기가 아니라 페이지별 추정치가 된다.

> 🆕🆕🆕 **[2026-08-11 후속 · `ab36fab`] `ROUTE_IDS`의 `ROUTES.ENRICHMENT`·`'enrichment:rule'`은 이제 살아 있는 호출부가 0인 채로 일부러 남아 있다** — `ROUTE_BY_PATH`의 `'/enrichment.html'` **키만** 지워졌다(그건 평범한 flat lookup이라 국소적으로 지워도 다른 경로 해석에 영향 없음). 두 id를 지우지 않은 이유: **이 목록은 서빙되는 라우트의 화이트리스트를 검증하는 것이지 실제 내비게이션 인구조사가 아니다** — id를 지운다고 그 id를 세는 일이 멈추는 게 아니라, `context_preserving_transitions` 선언이 그 이름을 대면 UNKNOWN으로 보고되며 **여전히 카운트된다.** `enrichment.js`(§7 — 이제 고아)가 `ROUTES.ENRICHMENT`를 아직 이름 대는 유일한 모듈이라, 이 죽은 id 둘을 치우는 결정은 그 파일 자체를 치우는 결정과 **한 번에** 내려야 한다(따로 안 한다). 저장은 `sessionStorage`(`STORAGE_KEY='assy.effort'` ~69)이고 서버 선언은 `GET /api/effort/config`([§5 `effort_metric.py`](#servereffort_metricpy-165줄-2a9f6c4-신설--핵심가치-1-계기의-선언-절반))에서 받아 **클라 사본 0**. 하니스: `client2/tests/effort_meter_harness.mjs`(757줄, 통과) · **`client2/tests/effort_instrument_harness.mjs`(474줄 — 구 지도의 440은 `91386f0` 시절 값이다. 🔴 **HEAD에서 죽어 있다**: `pushBlockingCount is not defined`로 **그룹 A 첫 케이스에서 즉사해 0건 채점**, [§6-2](#6-2-교차-구현-계약-contracts))**.

- 라우트 어휘: **`ROUTES`(~76 export)** / **`ROUTE_IDS`(~100 export — 선언된 라우트 id 전량)** / `KNOWN_ROUTE_IDS`(~114, 소문자 집합) / `normRoute`(~125) / `ROUTE_BY_PATH`(~499) / `routeFromHref`(~509) / `currentRoute`(~521).
- 서버 선언 소비: `parseTransitions`(~148) / `transitionKey(from,to)`(~187) / **`reportRejected`(~199 — 알 수 없는 라우트 id가 섞인 선언은 조용히 버리지 않고 진단으로 표면화)** / `loadConfig`(~211) / `publishDiagnostics`(~257) / **`getConfig`(~269 export)**.
- 수집: `newSessionId`(~286) / `safeGet`/`safeSet`(~323/331, storage 비활성도 견딘다) / `toCount`(~337) / `ensure`(~342) / `flush`(~368) / **`startSession`(~376 export)** / **`countKey(n=1)`(~383)** / **`countMouse(n=1)`(~390)** / **`countNav(fromRoute, toRoute)`(~412)** — 세 개가 점수의 세 항이다.
- 배출: **`snapshot()`(~439 export — 쓰기 요청 본문의 `effort` 블록)** / `commit()`(~456) / **`commitIfRecorded(resBody)`(~479 — 서버가 `effort_recorded: true`로 답했을 때만 카운터를 비운다.** 낙관적 초기화는 실패한 교정의 공수를 지워 버리고, 그건 계기를 조용히 낙관 편향시킨다).
- 자동 배선: **`installGlobalListeners()`(~565)** / **`installNavLinkCounting(fromRoute)`(~538)**.
- **소비 지도(6엔트리 + 3보조, 실측)**: 세션 시작 4곳 — `main.js`(~102–104, `ROUTES.GRID`) · `admin.js`(~295–297) · `enrichment.js`(~751–753) · `graph_viewer.js`(~1206–1208) · `trace.js`(~432–434). 쓰기에 `snapshot()`을 싣는 곳 4곳 — `api.js`(~307) · `clipboard.js`(~522·~766) · `ui.js`(~219) · `enrichment.js`(~475, 배출은 ~496). `countNav`만 쓰는 곳 — `timeline.js`(~517 로그 점프) · `trace_launch.js`(~95) · `map_editor.js`(~929/~1010/~5575/~5605).

### `main.js` (**2,047줄**, 1,816 → **+207**, `c3a5239` 스마트 페이스트 래치) — index 페이지 오케스트레이터
- 진입 `init()`(**~77**, `initTraceEntry()` 호출 포함 · **~112**에서 `registerSmartPasteHandler(smartPasteFromPasteEvent)`) → `setupEventListeners()`(**~120**, 거대 — 툴바·모달·키보드 전체 배선), `setupDragAndDrop()`(**~1083**).
- 셀 범위 `getSelectedCells()`(**~1168**), 소스 모달 `openSourcesModal/refreshSourcesList`(**~1215/1240**).
- 트랜잭션 모드 커밋/롤백 `applyPendingTxEdits()`/`discardPendingTxEdits()`(**~1917/1997**).
- export 없음(엔트리) — 다른 모듈을 소비만 한다.
- 🆕 **[`c3a5239`] 스마트 페이스트 — 「버튼이 클립보드를 읽을 수 없다」는 물리적 제약 위에 다시 지었다**(사유 블록 **~1489–1506**).
  - 🔴 **프로덕션은 평문 HTTP = 비보안 컨텍스트라 `navigator.clipboard`가 `undefined`다.** 클립보드로 가는 문은 **네이티브 `paste` 이벤트의 `e.clipboardData` 하나뿐**이고, 버튼 클릭은 그것을 만들어내지 못한다(`document.execCommand('paste')`는 웹 콘텐츠에서 차단). 즉 **종전 버튼 경로는 이 배포에서 한 번도 동작한 적이 없다.**
  - 상수 `SMART_PASTE_KEY_LABEL='Ctrl+Shift+V'`(~1507) · `SMART_PASTE_FALLBACK_KEY_LABEL='Ctrl+V'`(~1508) · `SMART_PASTE_KEY_TTL_MS=1500`(~1511) · `SMART_PASTE_ARM_TTL_MS=15000`(~1513) · `SMART_PASTE_ESCALATE_MS=600`(~1516) · `SMART_PASTE_ARM_TOAST_KEY`(~1529).
  - **`armSmartPaste(ttlMs)`(~1520)** — `state.smartPasteArmedUntil` + `state.smartPasteArmedTable`을 세운다(래치 필드는 [`state.js`](#7-client2src--웹-클라이언트)). 해제(~1532)는 플래그·타이머·안내 토스트를 **함께** 내린다(`utils.dismissToasts`).
  - **`smartPasteFromPasteEvent(e)`(~1607) — THE 프로덕션 리더.** `paste` 이벤트 디스패치 **안에서** 도는 유일한 코드라 `e.clipboardData`가 읽힌다. 🔴 **첫 검사가 `smartPasteArmedTable !== currentTable`이면 취소**(~1614)다 — 무장과 붙여넣기 사이에 테이블이 바뀌었으면 그 업로드는 거부한다.
  - **`smartPasteViaIngestion()`(~1662)** — 버튼/메뉴 경로. `navigator.clipboard.read`(~1663) → `readText`(~1714) → **평문 HTTP 낙하(~1728)** 순으로 시도하고, **어느 실패든 `armSmartPaste` + "이어서 Ctrl+V를 눌러 주세요" 토스트로 끝난다**(거절을 막다른 길로 만들지 않는다).
  - **키보드 경로(~444–471)**: `Ctrl+Shift+V`는 1.5초 무장 → 브라우저가 그 코드를 붙여넣기로 바꿔 주면 바로 소비되고, **600ms 안에 아무 `paste`도 안 오면**(`smartPasteEscalationTimer`) 15초 무장으로 승격하고 `Ctrl+V`를 안내한다. **Esc는 무장을 취소한다**(~476). ⚠️ **`Ctrl+Shift+V`를 붙여넣기로 볼지는 브라우저의 재량**이라 승격 경로가 폴백이 아니라 **정규 경로의 절반**이다.
  - `showClipboardTypeModal`(**~1743**). `client2/index.html`의 메뉴 항목이 **단축키를 라벨에 적는다**(~185) — 클릭만으로는 클립보드를 못 읽으므로 그 항목은 **다음 붙여넣기를 예약할 뿐**이고, 단축키가 본동선이다.
- ⛔ **[`90e284f`] 키보드 배선에서 Ctrl+C 분기가 삭제됐다 — 되돌리지 마라**(**~489–492**에 그 자리를 지키는 주석이 있다). 복사는 `clipboard.js`의 `copy` 리스너(~290 내부)가 `e.clipboardData`로 처리하므로 **`navigator.clipboard`가 없는 비보안 컨텍스트(평문 HTTP)에서도 동작한다.** 구 분기는 `navigator.clipboard.writeText`를 썼고 사내 평문 HTTP 배포에서는 그것이 `undefined`다 — 즉 삭제된 코드가 하던 일은 **작동하는 경로를 가로채 아무 일도 안 하는 것**이었다. `getRangeSelectedTSV` import도 함께 빠졌다(이 파일에서 더는 안 쓴다 — 여전히 `clipboard.js`가 export한다).

### `api.js` (**533줄**, `ed9cfdb` 456에서 **+29**) — REST 소비 계층 (경계 계약의 클라이언트측)

> 🆕 🔴 **[신설] 검색 컬럼 드롭다운이 조인 해석 컬럼까지 제안한다**(`loadSchema` 안, **~148–175**). **저장 컬럼 먼저, 그다음 조인 해석 이름**이고 라벨에만 `🔗`가 붙는다(`option.value`는 서버로 보내는 맨 이름 그대로 — `grid.js`가 이미 쓰는 헤더 어휘를 재사용한 것이지 같은 뜻의 두 번째 표기를 만든 것이 아니다).
> - 🔴 **목록은 *알림에서 읽지 여기서 조립하지 않는다*.** `?cols=`의 범위는 서버의 `apply_search_filter`가 정하고 그 가상 어휘는 `virtual_join_executor.exposed_columns` — **`/schema`가 `join_resolved_columns`로 발행하는 바로 그 집합**이다. 클라가 지어낸 이름은 서버에 식이 없는 이름이고 **서버는 그런 스코프를 400으로 거절한다**(테이블 전체로 답하지 않는다). 알림이 없거나 비면 저장 컬럼만 제안 = 변경 전 서버 전부와 정확히 같은 동작.
> - 🔴 **`virtual_columns`가 아니라 `join_resolved_columns`를 키로 쓴다** — `grid.js`의 컬럼 필터와 같은 선택이고 같은 이유다. 질문이 「**서버가** 이 이름으로 검색할 수 있는가」이고 그 답은 넓은 쪽 알림만 준다. `virtual_columns`는 「이 컬럼을 더해라」만 말하고 **모든 `collide` 이름에 대해 침묵**한다.
> - 🔴 **검색 전용이다 — 쓰기 경로가 아니다.** 이 엘리먼트를 읽는 곳은 정확히 넷(`fetchData` · `main.js`의 export 2곳 · `timeline.js`)이고 전부 **읽기**의 `?cols=`에 넣는다. 편집 가능성은 쓰기 깔때기 안의 `isVirtualColumn`이 정하고 **그것은 이 select를 보지 않으므로**, 넓혀도 읽기 전용 컬럼이 어디서도 편집 가능해 보이지 않는다.
> - ⚠️ **`collide` 이름은 저장 컬럼이라 앞 루프가 이미 제안했다** — 그대로 덧붙이면 **같은 쿼리를 만드는 동일 옵션이 둘** 생기므로, 알림을 이미 제안한 것과 **차집합**해서 붙인다.
- export **8종**: `checkServerHealth`(~14) · `loadTables`(~31) · `switchTable`(~59, 말미에 `refreshTraceEntry()` fire-and-forget) · **`loadSchema`(~102 — 🆕 `virtual_columns`·`join_resolved_columns`를 `state`에 싣는 지점)** · `fetchData(resetSkip)`(**~156**, 메인 조회+세션가드) · `handleCellEdit(event)`(**~249**, 셀 편집→PUT updates) · `addRows`(**~402**) · `deleteSelectedRows`(**~421**).
- 소비 API: `/tables*`, `/tables/{t}/data`, `/schema`, PUT `/data/updates`, POST `rows`, `batch_delete`.
- 🔴 **[F3 `d5f75a8`] `loadSchema`가 첫 줄에서 `resetSuggestLearning()`을 부른다(**~110**)** — `import { resetSuggestLearning } from './value_suggest.js'`(~10). 이유가 배선의 전부다: 제안 모듈이 붙드는 부정 사실(비대상 컬럼·프리픽스 바닥·불가 쿨다운)은 **서버의 거절**에서 배웠고 그 거절은 `table_config`에서 나오는데, **`table_config`는 핫리로드**다. `/schema` 재조회는 클라가 그 선언을 다시 읽는 **유일한 신호 지점**이므로, 여기서 비우지 않으면 새로 제안 대상이 된 컬럼이 이미 열린 탭에서 `LEARNED_TTL_MS`(60초) 동안 죽어 있다. 래치들은 시간으로도 만료되지만 **이 호출이 신호가 있는 경로에서 즉시 반영시킨다**([§7 `value_suggest.js`](#7-client2src--웹-클라이언트)).

### `grid.js` (**869줄**, `1dc761b` 671에서 **+198** — 가상 컬럼 렌더·필터) — AG-Grid 구성

> ⚠️ **구 지도에 이 절의 export 목록이 두 벌 있었고 뒤엣것이 낡아 있었다**(2026-07-30 정정). `~17/~42/~66/~74/~94/~112/~254` 세트는 `883b680`(+117) **이전** 값이라 전 항목이 **+91~+102** 어긋나 있었는데, 바로 위 줄의 올바른 세트와 나란히 있어서 어느 쪽도 틀려 보이지 않았다. 중복 목록은 **오차 허용 범위 안에 있는 쪽이 정답처럼 읽히는 것이 아니라, 둘 다 그럴듯해서 아무 검사도 통과시킨다.** 한 벌만 남긴다.

- **[`883b680`] 마우스 없이 범위 선택** — `RANGE_ARROW_DELTA`(~35, `Object.freeze`) · **`visibleRangeColIds()`(~47)** · **`extendRangeByKeyboard(api, key)`(~61)**. 목적은 **Ctrl+Enter 일괄 채우기를 키보드만으로 완결**시키는 것이다(종전엔 범위를 만들려면 반드시 마우스를 잡아야 했다). ⚠️ **둘 다 `export`가 아니다**(모듈 내부) — 외부에서 이름으로 부르려 하면 없다.
- export **7종**: `updateGridSortState`(~108) · `updateLoadedCount`(~133) · `updateViewModeUI`(~157) · `updatePaginationUI`(~165) · **`ensureCellObject(dataObj, colId)`**(~185, 셀 형태 `{value,is_overwrite,priority_source}` 정규화 — 셀 계약의 단일 관문) · **`buildColumnDefs`(**~282**)** · `renderGrid(initialRows)`(**~554**).
- 🆕 **[`cd3e0f4`] 가상 컬럼 3종**: `rawCellValue(rowData, colId)`(~207) · **`numericDisplayValue(val)`(~224 — 🔴 서버 `crud.numeric_text_sql`의 화면 쪽 짝이다: 정수형은 정수로 찍는다. slot이 `3.0`으로 보이면 운영자가 config에서 찾는 토큰과 화면의 토큰이 갈린다)** · `JOIN_RESOLVED_FILTER_OPTIONS`(~261)/`joinResolvedFilterDef(entry, baseTooltip)`(~265). ⚠️ **편집 금지 판정은 `state.isVirtualColumn`에 위임한다 — 여기에 사본이 없다.**
- **[F3 `77a2c15`] 값 제안 에디터의 배선 2곳 — 이 파일이 이음매의 클라 쪽 접합부다**(모듈 본체는 [`value_suggest.js`](#7-client2src--웹-클라이언트)):
  - `import { SuggestCellEditor, handleEditorKey, isSuggestEditorActive } from './value_suggest.js'`(~15).
  - **`buildColumnDefs` 안에서 `colDef.cellEditor = SuggestCellEditor`(~323)** — **`string` 컬럼에만, 시스템 컬럼 제외**. 범위가 좁은 것이 의도다: `number`는 `agNumberCellEditor`가 나르는 숫자 검증을 이 그리드의 `valueSetter`가 의존하고, `datetime`은 엔드포인트 자신이 거부한다. 서버는 숫자 프리픽스를 **지원하므로**(`_numeric_values`) 넓히는 것은 이 술어 한 줄의 변경이지만 에디터 안에 숫자 검증을 다시 구현하는 별도 라운드다.
  - 🔴 **`renderGrid`의 `defaultColDef.suppressKeyboardEvent`(~389) 안, 다른 어떤 분기보다 먼저**(~402): `if (params.editing && isSuggestEditorActive())` → `handleEditorKey(event)`의 3값 판정을 그대로 옮긴다 — `'suppress'`면 `true`(리스트가 키를 먹었다), **`'accepted'`면 `false`**(="이 이벤트가 커밋하게 두라"), `'pass'`면 아래 기존 분기로 낙하. **`false`를 돌려주는 것이 포기가 아니라 커밋이다**: AG-Grid의 `processCellKeyboardEvent`가 `suppressKeyboardEvent`를 `cellCtrl.onKeyDown`**보다 먼저** 보고, `onKeyDown`의 Enter 분기가 `stopEditing` → `cellEditor.getValue()`를 부른다. 그래서 후보는 **같은 이벤트 디스패치가 커밋하는 시점에 이미 input 안에 있다** — 수락과 커밋이 한 번의 Enter이고, 그 순서는 타이머도 마이크로태스크도 아닌 **프레임워크 자신의 시퀀스**가 보장한다.

### `value_suggest.js` (**1,003줄**, `77a2c15`+`847ceaf`+`e14b1d0`+`d5f75a8` 신설) — **F3 값 제안의 클라 절반**

⚠️ **이 모듈은 종전 지도에 통째로 없었다**(2026-07-30 신설). 서버 절반 `server/value_suggest.py`만 [§5-A](#5-a-2026-07-30-신설-서버-모듈-8종)에 등재돼 있었고, 흐름 [8-ter](#8-주요-호출-흐름-요약)는 클라 쪽을 "클라 입력 → GET …"이라고만 적어 **모듈 이름도 원-Enter 순서도 요청 상한도** 말하지 않았다. ⚠️ **줄 수를 인용할 때 주의**: `e14b1d0` 시점 **692줄**이었고 `d5f75a8`(Escape 계약 + limit-12)이 1,003줄로 키웠다 — 692는 3커밋 전의 값이다.

**이름이 계약이다.** `server/value_suggest.py`와 **같은 이름**인 것은 우연이 아니라 이음매의 두 반쪽이 서로에게서 찾아지게 하려는 것이다. 서버가 조회(프리픽스 술어·`db_fold` collation·loose index scan·절단 보고)를 **전부** 소유하고 이 파일은 **입력 표면만** 갖는다 — 어느 것도 다시 유도하지 않는다. import는 `config.js`의 `API_BASE`와 `state.js`뿐.

**🔴 수용 기준은 부등식 하나다.** V1 공수 계기에서 키 입력 1회 = 1점. 값을 다 치면 `N`, 프리픽스 `P`자 + Enter면 `P + 1`. 따라서 제안은 `P ≤ N − 2`에서 이기고 `P = N − 1`에서 비기며 **지는 경우가 없다** — **단 후보를 수락하는 Enter가 셀을 커밋하는 그 Enter일 때만.** 수락과 커밋이 두 번이면 비용이 `P + 2`가 되어 매 사용이 +1을 물고 짧은 값은 진짜로 퇴행한다. 그 성질을 얻는 방법은 [§7 `grid.js`](#7-client2src--웹-클라이언트)의 `suppressKeyboardEvent` 항목에 있다.

| 구분 | 시그니처 / 상수 | 내용 |
|---|---|---|
| 노브 | `MIN_PREFIX_LEN=1`(~85) · `DEBOUNCE_MS=90`(~93) · **`REQUEST_LIMIT=12`(~136)** · `MAX_VISIBLE_ROWS=8`/`ROW_HEIGHT_PX=26`(~144/145) · `MAX_REJECTS_BEFORE_DISABLE=4`(~152) · **`LEARNED_TTL_MS=60000`(~178)** · **`UNAVAILABLE_COOLDOWN_MS=15000`(~198)** | 아래 세 항목이 각각의 근거 |
| 🔴 **빈 프리픽스는 여기서 거부한다** | `MIN_PREFIX_LEN = 1` | 서버의 `min_prefix_length` 기본값은 **0**이라 빈 프리픽스는 서버에서 **허용**되고 loose scan 덕에 싸기까지 하다. 그래도 클라가 막는 이유가 수용 기준이다: 프리픽스가 없으면 목록은 컬럼 전체 값 집합에 대한 임의의 `limit` 창이라 **첫 후보가 임의값**이고, 그러면 "Enter가 옳다"가 "Enter가 동전 던지기"로 강등된다. ⚠️ **방향이 중요하다 — 서버보다 항상 더 엄격하고 절대 느슨하지 않다.** 운영상 `min_prefix_length`를 올리면 그것은 여전히 지켜진다(`columnFloor`) |
| 🔴 **`REQUEST_LIMIT = 12`가 두 가지를 동시에 산다** | ~136 | ① **산술이 유용한 목록 길이를 스스로 묶는다**: k번째 후보에 닿는 비용은 k키(화살표 k−1 + Enter)이고 전타는 N키이므로 **N−1번째 이후 후보는 원리적으로 무의미**하다(프리픽스를 한 자 더 치는 게 항상 싸다). ② **엔드포인트를 10ms 예산 안에 넣는다** — 실측(2026-07-30, warm, PG 18.3) `t = 0.84ms + 0.61ms × (limit+1)`이고 프로브당 0.61ms 중 **97%가 Python/SQLAlchemy/프로토콜**이라 테이블 크기와 거의 무관(n 136배 범위에서 편차 12.4%, 지수 −0.02). limit 20 = 중앙값 15.3ms(모든 크기에서 초과), limit 12 = 약 8.7ms. ⚠️ **꼬리는 예산 밖이고 그것을 말하는 것이 예산을 말하는 것의 일부다** — limit 20의 실측 p95가 20.7ms(중앙값의 1.35배)라 같은 비율이면 limit 12의 p95는 **약 11.8ms로 10ms를 넘는다**. ⚠️ **2차 비용이 나중에 적혔다**: `truncated` 응답은 캐시되지 않으므로(→ 로컬 좁히기 불가) 절단 국면에서는 **대부분의 키 입력마다** 요청이 미결 상태가 되고, 그것이 아래 Escape 결함을 드물던 것에서 흔한 것으로 만들었다 |
| 🔴 **모든 부정 사실에 만료가 있다** | `nowMs()`(~208) / `learn(map, key, value)`(~217) / `recall(map, key, ttlMs)`(~221) | 이 모듈이 배우는 부정 사실은 **전부 실패 1회 관측**에서 오는데 실패는 규칙의 증거가 아니다 — 404는 라우트가 아니라 **프록시**에서, 뒤에서 재기동된 백엔드에서, `switchTable` 중 잠깐 낡은 (테이블,컬럼) 쌍에서도 온다. 클라는 그 셋을 서버 자신의 거절과 **구분할 수 없다**(프록시 404와 미선언 컬럼 404는 같은 바이트다). TTL 이전에는 6자 입력에서 온 일시적 404 하나가 바닥을 7로 올리고 **그 세션 내내** 그것을 반증할 요청 자체를 `suggestible()`이 막았다 — 틀릴 수 있는 증거에 걸린 단방향 래치는 **구조적으로 복구 불가**다. 둘째 이유는 배포 성질: `table_config`가 **핫리로드**인데 만료 없는 래치는 거기서 스스로를 면제한다. `nowMs()`는 `Date`가 없으면 0을 돌려 **만료 이전의 단방향 동작으로 강등될 뿐 틀린 답으로는 가지 않는다** |
| 세션 메모리 (키 = `(table, column)`) | `colKey`(~201) · **`disabledColumns`(~229 — Map)** · `columnFloor`(~242) · `columnRejects`(~243) · **`columnCooldown`(~248 — Map, 신설)** · `completeResults`(~274) · `stats`(~277) | 🔴 **`disabledColumns`는 `Set`에서 `Map`으로 바뀌었다** — 값이 아니라 **학습 시각**을 담아야 `recall`이 만료를 판정할 수 있기 때문이고, 그것이 위 항목의 구현이다. **`columnCooldown`은 신설**: 4스트라이크 래치는 4xx(서버에 거의 공짜인 경로)를 지키는데 **`unavailable_reason`은 비싼 경로인데도 백오프가 하나도 없었다**(17자 입력 = 17요청, 세션 내내). 엔드포인트가 동기 `def`라 호출마다 anyio 워커 스레드 + 풀 커넥션을 점유하고, fetch abort는 브라우저 소켓만 닫을 뿐 `db.execute` 안의 핸들러를 취소하지 못한다 — 느린 컬럼(217ms~1.9s)에서 타이피스트 1명이 커넥션 ~9개를 동시 점유해 3명이면 `pool_size=20, max_overflow=10`을 고갈시키고, **드러나는 증상은 무관한 요청의 `pool_timeout`이라 아무것도 여기를 가리키지 않는다.** 15초 쿨다운이 ~0.13개로 낮춘다(약 70배) |
| export | **`resetSuggestLearning()`(~313)** · `getSuggestStats()`(~294) · `resetSuggestStats()`(~321) · `isSuggestEditorActive()`(~484) · **`handleEditorKey(event)`(~495)** · **`class SuggestCellEditor`(~502)** | `resetSuggestLearning`의 **유일한 호출자는 `api.loadSchema`**(~110) — 다섯 Map을 전부 비운다(`completeResults` 포함: 좁히기의 건전성이 컬럼의 값 집합에 기대는데 스키마 변경이 그것을 재정의할 수 있다). `handleEditorKey`의 판정은 **의도적으로 3값**이다: `'suppress'`(리스트가 먹음) · `'accepted'`(후보가 이미 input에 있으니 AG-Grid가 **작동해야** 한다 = 원-Enter 경로) · `'pass'`(우리 것 아님) |
| 진단 | `liveEntries(map, ttlMs)`(~285) · **`window.__assySuggest`(~343)** | 🔴 **`window`에 붙이는 이유는 프로덕션 빌드에서 살아남기 위해서다** — `getSuggestStats`/`resetSuggestStats`는 `client2/src` 안에 호출자가 없어 번들러가 **트리셰이킹으로 지운다**(실측: 이 라운드 브라우저 E2E에서 `window.__assySuggest`가 undefined라 요청 수를 `fetch` 수동 래핑으로 셌다). `effort_meter.publishDiagnostics`와 **같은 덫·같은 처방**이다. 래치 맵은 **`recall`을 통과시켜** 내보낸다 — 원본을 덤프하면 아무것도 막지 않는 만료된 바닥까지 보여 주어 **묻는 것과 다른 질문에 답하게** 된다 |
| 로컬 좁히기 | `ASCII_ONLY`(~356) / `canNarrowLocally(cached, prefix)`(~358) | 완전한(`truncated: false`) 결과는 더 긴 프리픽스의 답을 **포함**하므로 요청 0회로 좁힐 수 있다 — **단 ASCII에서만**. `db_fold`가 존재하는 이유가 이 DB의 `lower()`와 JS `toLowerCase()`가 **ASCII 밖에서 다른 함수**이기 때문이고, 그 밖은 서버로 돌려보낸다. ⚠️ **캐시 수명은 셀 편집 1회**(`destroy`에서 폐기) — 실측 결함이었다: `inventory_master.category`에 "DEV"를 커밋한 직후 다음 셀에서 "DEV"를 쳤는데 목록이 그것을 되주지 않았다(커밋 이전 스냅샷을 서빙). 새 값을 넣은 그 순간이 조작자가 기능이 알기를 가장 기대하는 순간이다 |
| 요청 | `abortInflight`(~375) / **`requestValues(table, column, prefix, limit)`(~386)** | `AbortController` 1개를 모듈 싱글턴으로 공유(+`requestSeq` 세대). 400/404 = "제안 대상 아님 또는 프리픽스가 서버 최소 미만" → **산문을 파싱하지 않고 경계를 배운다**(길이 L에서 거절 = "L로는 부족" → 바닥 L+1, 그리고 거절 카운트). `unavailable_reason` 본문 = 값 없는 명명된 부재 → 쿨다운. **진짜 답 하나가 바닥을 제외한 모든 부정 사실을 반증**한다(바닥은 그 이상에서의 성공이 말해 줄 수 없다) |
| 에디터 | `SuggestCellEditor` — `init`(~503) `getGui`(~602) `afterGuiAttached`(~606) `getValue`(~613) `isPopup`(~617) `destroy`(~633) **`suggestible()`(~658)** **`scheduleQuery()`(~669)** `setPending(on)`(~722) **`runQuery(prefix)`(~733)** `applyValues`(~754) `openList`(~769) `closeList`(~821) **`dismissSuggestions()`(~847, 신설)** `positionList`(~856) `scrollHighlightIntoView`(~895) `moveHighlight`(~901) `acceptHighlight`(~914) **`onKeyDown(event)`(~922)** | `runQuery`의 **가드 넷**이 각각 다른 "늦은 답이 낡은 의도에 작용하는 길"을 닫는다: 에디터 소멸 · 더 새 요청 발행 · 그 사이 입력 변경 · **그리고 조작자가 제안을 물렸다**. 마지막 것은 앞 셋이 못 덮는다 — Escape는 입력도 시퀀스도 건드리지 않으므로 그 전에는 늦은 답이 셋을 통과해 **닫은 목록을 0번 행 하이라이트로 되열었다.** `dismissSuggestions`가 넷을 함께 내린다(플래그·타이머·목록·abort) |
| 🔴 **Escape는 한 가지만 뜻한다 — 시계에 투표권이 없다** | `onKeyDown`의 Escape 분기 · `suppressUntilInput` · **`suggestionsEngaged`** | 이 모듈의 **두 번째 불변식**이고 초판이 깨뜨린 그것이다. 종전 술어는 `this.listOpen`이었는데 **누른 순간 목록이 떠 있었는지는 `DEBOUNCE_MS` + 왕복시간의 함수**다. 결과가 정반대였다 — 목록을 닫고 친 글자를 **유지**하거나, AG-Grid 취소로 떨어져 그것을 **버리거나**. 그리고 화면에는 둘을 구분할 것이 아무것도 없다(스피너가 **의도적으로** 없다 — `setPending` 주석). 현 계약: **Escape #1, 제안이 engaged된 셀에서 → 물림**(친 글자 유지 · 목록 닫힘 · 예약 질의 취소 · 진행 중 요청 abort **+ 플래그**로 늦은 답의 부활 차단). **Escape #2, 또는 engaged된 적 없는 셀의 #1 → `'pass'`**(= 평범한 텍스트 에디터의 취소, 그런 셀이 실제로 그것이다). **`suggestionsEngaged`는 이 에디터가 이 프리픽스를 묻기로 정한 첫 순간에 서고 편집 내내 안 내려간다** — 명백해 보이는 술어("지금 질의가 진행/예약 중인가")는 그 자체가 RTT의 함수라 이음매를 없애는 게 아니라 **옮길 뿐**이다("답이 Escape보다 먼저 왔는가"로). 되열기는 **ArrowDown 전용**(ArrowUp은 절대 부활시키지 않는다 — 자기 글자를 지키려는 조작자에게 안전한 방향을 남긴다) |
| IME | `onKeyDown` 첫 분기 | **무조건 먼저.** 조합 중 Enter는 IME의 것이다(한글 음절을 확정한다). 가로채면 조작자가 글자를 닫기만 하는데 후보가 대입된다 — **이 제품은 한국어로 입력된다.** 조건은 `event.isComposing === true` 또는 `event.keyCode === 229`(후자가 `isComposing` 이전의 같은 조건) |

- 하니스: **`client2/tests/value_suggest_keys_harness.mjs`(1,901줄)** — `client2/tests/` 밑에서 **유일하게 빌드 게이트에 배선된** 하니스다(`npm run check:suggest-keys`, `prebuild`). 실제 `SuggestCellEditor`와 실제 `suppressKeyboardEvent` 훅을 소스에서 그대로 들어 올려 AG-Grid 키보드 파이프라인의 **모델**에 물린다(재구현은 그 모델 하나뿐이고, 결과를 가르는 네 지점이 `ag-grid-community` 소스 인용과 함께 인라인으로 적혀 있다). 모든 검사가 **핸들러 반환값이 아니라 키 입력 수**로 서술되고 `effort_meter.installGlobalListeners`와 **같은 계수 규칙**을 쓴다. 뮤테이션 스윕은 **무조건 실행**(`process.argv`를 읽지 않는다 — 잊을 수 있는 `--mutate` 플래그가 없다)이고 APPLIED와 CAUGHT를 **따로** 보고한다(`cb8f01a`: 뮤테이션 18개 중 8개가 적용조차 안 되는데 베이스라인은 초록이었다).
- CSS: 목록은 `style.css`의 `.value-suggest-*`(이 라운드 +132줄). `document.body`의 기존 드롭다운 층(z 1000, `#custom-context-menu`와 같은 단)에 `position: fixed`로 산다 — AG-Grid 셀이 `overflow: hidden`이고 그리드 루트가 클립하기 때문. **수평 클램프가 나중에 붙었고 그 비대칭이 생존 불가였다**: 컨테이너가 `overflow-x: hidden`이라 오른쪽 끝 컬럼에서 긴 값의 꼬리가 **어떤 수단으로도** 도달 불가였다(고정 요소로는 페이지가 스크롤되지 않고 드래그할 스크롤바도 없다) — 조작자가 Enter가 쓸 값을 읽을 수 없는 상태이고, 그것이 하이라이트가 존재하는 유일한 이유다. CSS에서 `min-width`가 `max-width`를 **이기므로** 최소폭도 함께 클램프한다.

### `websocket.js` (~255줄) — 실시간 수신
- export: `initWebSocket`(~11, 재접속 백오프) `handleWebSocketMessage(msg)`(~72).
- 소비 이벤트: `file_ingestion_progress`(~73) `file_ingestion_completed`(~84) `batch_row_create`(~131) `batch_row_upsert`(~147) `batch_row_delete`(~229) `batch_refresh_required`(~244) → 델타 반영(`applyTransaction`)·페이지캐시 갱신.

### `ui.js` (**426줄**, +11) — 그리드 밖 UI 갱신
- export: `setupBeforeUnloadWarning`(~9) `updateSelectedCellUI`(~19) `updateTxModeUI`(**~40**) `setTransactionFilter`(**~86**) `applyValueToSelectedRange(newValue)`(**~113**, 범위 일괄 적용→배치 PUT) `updatePageCacheOnUpsert`(**~277**) `updateEnrichmentBadge`(**~348** — **[`1fefd12`] 배지 카운트 필터도 `rule.queue_filters` 우선**(~356): 워크리스트·어드민과 세 수치가 어긋날 수 없다) `notifyEnrichmentTableEvent`(**~399**) `updatePageCacheOnDelete`(**~409**). 보조: `ENRICHMENT_COUNT_TTL=5000`(**~330**, 서버측 카운트 캐시와 같은 주기)/`loadEnrichmentRules`(**~332**)/`findEnrichmentRule`(**~342**).

### `clipboard.js` (**858줄**, `1dc761b` 829에서 **+29**) — 엑셀형 범위 선택/복붙
- export: `isCellInRange`(~14) `refreshRange`(~35) `refreshSelectedRangeDiff`(~63) `clearRangeSelection`(~98) `commitDragSelection`(~150) `getRangeSelectedTSV`(~178) **`registerSmartPasteHandler(fn)`(**~302**)** `setupClipboardHandlers`(**~306**, copy/paste 이벤트 본체) `clearSelectedCells`(**~679**).
- 🆕 **[`c3a5239`] 스마트 페이스트의 소비 지점** — 모듈 로컬 `smartPasteHandler`(**~300**)를 `main.js`가 1회 등록하고, `paste` 리스너 **첫 분기**(**~317**)가 `smartPasteHandler && state.smartPasteArmedUntil > Date.now()`면 **래치를 즉시 소비(0으로 리셋)한 뒤** 그 핸들러로 이벤트를 넘긴다 — 그 외에는 종전 셀 범위 붙여넣기 그대로. 🔴 **두 번째 `paste` 리스너를 만들지 않은 것이 요점이다**: 리스너가 둘이면 어느 쪽이 먼저 이벤트를 소비하는지가 등록 순서에 달리고, 그 순서는 엔트리 파일의 import 순서라 보이지 않는다.
- **[`b35bc9f`]** TSV 인용/파싱은 자체 구현 대신 **`tsv.js`의 `parseTsv`/`serializeTsv`** import(~11).

### `timeline.js` (**899줄** @`dab9152` — 722에서 **+177**) — 이력 타임라인 + 내비게이션

> 🆕🆕🆕 **[2026-08-11 후속 · `dab9152`] 행/셀 이력이 무한정 배열에서 서버 봉투(`{logs, truncated, next_cursor}`) 기반 페이징으로 바뀌었다** — 서버 짝은 [`audit_history.py`](#6-기타-서버-모듈-한줄-요약)의 `fetch_page`. **전역(global) 이력 탭은 이번에 손대지 않았다** — 그쪽은 여전히 `/audit_logs/recent`의 맨 배열을 그대로 순회한다(그 라우트가 헤더로만 truncation을 흘리는 이유이기도 하다, §`audit_cache.py`).

- **export**: `loadHistory()`(전역/셀·행 두 탭 분기 — 셀 탭은 매 로드마다 `beginHistorySession()`으로 **새 페이징 세션**을 연다) · 🆕🆕🆕 **`readHistoryPage(body)`**(서버 응답을 `{logs, truncated, nextCursor}`로 정규화 — **맨 배열도 받는다**: 그 경우 `not truncated, no cursor`가 「이것이 완전한 응답」이라는 참인 서술이다. `truncated`는 `nextCursor`가 있을 때만 참으로 접는다 — 커서 없는 truncated는 "클릭할 수 있어 보이는데 아무 데도 안 가는" 상태라 표현 불가능하게 만든다) · DOM 빌더 `createTimelineItemDom`/`createGlobalTimelineItemDom` · 증분 렌더 `renderTimeline`/`renderTimelineIncremental`/`renderGlobalTimelineIncremental`/`renderGlobalTimeline` · `createHistoryMoreDom()`(「더 보기」 컨트롤 — **완전한 목록은 이 컨트롤을 달지 않는다**, 그 부재 자체가 사실을 말한다) · 🆕🆕🆕 **`loadMoreHistory(btn)`**(다음 페이지를 **append**, 교체하지 않는다. `400`은 커서 만료로 별도 처리 — `markMoreLost`가 "위치 만료·새로고침"으로 안내, 일반 실패는 `markMoreFailed`가 "조회 실패·재시도") · `renderSubDetails` · `appendHistoryLocally` · 로그→셀 점프 `navigateToLog`+`navigatorStep2/3`/`navigatorFinalScroll`/`releaseNavigationGuard`.
- **module-private**: `historyUrl(rowId, colId, cursor=null)`(행/셀 URL 조립의 유일한 철자 — `loadHistory`와 `loadMoreHistory`가 공유, 갈라지면 페이저가 사이드바와 다른 탭을 조회할 수 있다) · 🆕🆕🆕 **`beginHistorySession()`**(세션 토큰 `+=1` — 매 `await` 뒤 토큰 비교로 stale 응답을 버린다: 다른 셀을 고르거나 탭을 바꾼 사이에 도착한 이전 요청이 화면을 덮지 않도록) · `renderHistoryMore`/`historyMoreLabel`/`markMoreFailed`/`markMoreLost`.
- 소비 API: `/audit_logs/recent`, `/audit_logs/transaction/{tx}`, `/tables/{t}/rows/{r}/history`, `/tables/{t}/rows/{r}/cells/{c}/history`.

### `map_editor.js` (**11,031줄** — `d3ed167` 10,866에서 **+165**. 🔴 **코드는 6,391줄이다** — 주석 3,858 + 공백 782) — 웨이퍼 맵 에디터 (단일 페이지 스크립트, export 없음)

> 🟢 **심볼 실측 완료** — 이 절의 심볼은 **`5609ff0`의 커밋된 blob에 존재함이 확인됐고, 그 뒤 HEAD가 움직인 다음 재대조에서도 동일했다**(워킹트리 아님). 🔴 **라인 번호는 싣지 않는다** — 위치는 `git grep -n "<심볼>" -- <경로>`로 확정하라. 숫자가 남아 있는 곳은 **파일 줄 수**이거나, 이름이 없는 덩어리를 가리키며 측정 sha가 함께 적힌 자리뿐이다.

> 🔴 **이 절에는 구간별 라인 계단표가 없다 — 삭제한 것이 아니라 성립하지 않는다.** 이 파일은 **이음매를 따라 쪼개지는 중**이다. 직전 라운드는 **파일 밖으로** 잘라냈고(`map_key.js`·`split_registry_row.js`), 이번 라운드는 **파일 안에서** 쪼갰다 — 세 거대 함수(`loadExistingMap` R4 · `resolveValidDie` R5 · `pushMapData` R6)의 몸통이 **이름 붙은 단계 함수 17개**로 뽑혀 나왔다. 추출은 함수를 파일 뒤쪽에 앉히므로 **뒤로 갈수록 앵커가 크게 밀린다**(파일 앞 ~300줄은 무이동, 중반 +50~+164, 후반 **+250~+495**).
>
> **그래서 이 절의 1차 식별자는 함수명이고 라인은 보조다.** 계단표는 다음 추출에서 **통째로 거짓이 되면서 거짓이 됐다는 신호를 내지 않는다** — 계단표는 자기가 낡았음을 말할 수 없다. 심볼 표는 적어도 Grep 0건으로 낡음을 드러낸다.
>
> 🔴 **[2026-08-06] 이 절의 앵커 253개가 *전부* 틀려 있었다 — 예외 0건.** 드리프트는 **+8 ~ +185줄**(파일 앞 ~400줄도 +8~+9로 밀렸다. **「앞쪽은 무이동」이라던 직전 서술은 이제 거짓이다** — 프레임 인자화가 파일 최상단부터 줄을 넣었기 때문이다). 이번 갱신은 **전건 `cfa22ce` blob 실측**이고 더할 값은 없다.
>
> 🔴 **그리고 살아 있는 앵커 다섯이 없는 것을 가리키고 있었다**: `physFrameOverride`(구 1432) · `withPhysFrame`(구 1538) — S2.1 리팩터로 삭제. `PUSH_SYSTEM_COLUMNS`(구 5760) · `getUnprotectedPushColumns`(구 5782) · `logShapedPushDecision`(구 5801) — **`push_columns.js`로 이사**. 다섯 모두 「그럴듯한 도착지」가 있어 ±20 오차로는 잡히지 않는다.
>
> **재측정 트리거**: `git rev-parse HEAD:client2/src/map_editor.js`가 **`cfa22ce`**(= `cd8bfc9`의 blob)이 아니면 이 절 전체가 재측정 대상이다. **직전 지도의 트리거 값 `7ff066d`은 만료됐다.**
>
> 📐 **실측 규모**(`cd8bfc9`): 총 **11,031줄** · 공백 **782** · 비공백 **10,249** · **주석 3,858(비공백의 37.6%)** · **코드 6,391**. 톱레벨 함수 선언 **249개**(`function` 216 + `async function` 33) · 모듈 레벨 `let` **47개**(`var` 0 — 직전 48에서 `physFrameOverride` 삭제분 1). ⚠️ **「11,031줄짜리 파일」이라고 인용하면 코드 규모를 73% 과대 보고한다.**
>
> 🆕 **좌표표 붙여넣기 4종**: **`coordRulerTicks(line)`** · **`readCoordTableBlock(text)`** · **`currentCoordFrame()`** · **`planCoordPaste(coord, cf)`** — 엑셀 모양의 **2D 좌표표를 화면 위치가 아니라 DB 좌표로** 읽는 붙여넣기 경로(축은 표의 헤더에서 읽는다). 그리고 **`renderValidDieKeyControl()`** — 유효 다이 **읽기**를 `valid_die_ref`에 고정하고 없으면 **이름으로 거절**하는 컨트롤.


#### 🆕 2026-08-04 이음매 분해 — 단계 함수 **17종** (R4·R5·R6)

🔴 **세 거대 함수가 *같은 규율로* 쪼개졌다**: 단계 함수는 **읽는 모든 바인딩을 인자로 받아 모듈 상태를 읽지 않고**(`el`·`currentRotation`·`currentSide`를 **일부러 같은 이름의 인자로 가려** 본문을 인라인 시절과 바이트 단위로 같게 유지한다), **모듈 상태에 쓰지 않으며**(대입·거절·`boundingBoxCache` 무효화는 전부 오케스트레이터가 한다), **거절을 *취하지* 않고 사유로 *돌려준다*.** 그 셋이 추출의 성립 조건이었다.

| 부모 | 단계 함수 | 무엇인가 |
|---|---|---|
| **R4 `loadExistingMap`** | `collectMapKeyFilterModel()` | ① 메타 입력칸 → 조회 필터. 값이 하나도 없으면 `hasFilter === false`이고 **판정은 호출부가 한다** |
| | `scanCoordinateBounds(result, xCol, yCol)` | ② 응답 행 → 저장 좌표 bbox. 🔴 **센티넬(`minX 9999`)이 계약의 일부다** — 파싱된 셀이 0개면 그대로 돌아가고 호출부가 그 값으로 「해석된 셀 0개」를 가른다 |
| | `resolveDeclaredGridMeta(selectedTable, tableSchema, filterModel, result)` | ③ `wafer_map_metadata` 해석 → `{ok:true, gridMeta, mapKey}` \| `{ok:false, refusal}`. 🔴 **「확인 못 했다」는 「선언이 없다」가 아니다** — `fetchGridMetaFor`의 404/405-만-null 규율이 여기서 끝나지 않도록 한 자리에 모았다 |
| | `promptCoordinateChoice(el)` | ④ 선언 없는 맵의 좌표계 선택 모달 → `'standard'\|'current'\|'cancel'`. ⚠️ **`el`을 인자로 받는 것이 시그니처의 말이다** — 이 단계가 손대는 유일한 바깥 것 |
| | **`resolveGridFrame(userChoice, loadedGridMeta, minX, minY, maxX, maxY, el, currentRotation, currentSide)`** | ⑤ 선택 → 격자·원점·회전·면. 🔴 **셋 중 정확히 하나가 프레임을 정한다**가 이 함수의 전부. `boundingBoxCache` 무효화는 **호출부**가 한다 |
| | `deriveLegendFromCellValues(uniqueVals, legend, predefinedColors)` | ⑥ 셀 값 집합 → legend 배열을 **돌려줄 뿐 대입은 호출부**가 한다(「어느 시점에 화면의 legend가 바뀌는가」가 한 줄로 읽혀야 한다) |
| | **`restoreDoeDraftWithPrecedence(selectedTable, loadedMapKey, serverFp, serverCellsFp)`** | ⑦ 초안 우선순위. 기반 지문이 같으면 초안이 더 새 것 · 어긋나면 **누가 썼다** → 적용하면 남의 저장을 지운다. 🔴 **적용하지 않고, 버리지도 않고, 사실을 드러낸다**(`restoredUnsavedEdits` → `legendDirty` · `staleDraftKept` → persist 보류) |
| **R6 `pushMapData`** | `confirmLogShapedPushTarget(tableSchema, el, selectedTable)` | 로그형 타깃의 손실 인지 확인창. **어느 모드가 거절하고 무엇을 말하는가는 `logShapedPushDecision`의 답 그대로** |
| | `collectMetaFieldValues(tableSchema)` | 메타 패널을 있는 그대로 읽는다. `ok:false`는 **선언된 메타 필드가 있는데 하나도 안 채웠을 때**뿐 — 필드가 아예 없는 테이블은 막지 않는다(공백 검사에 둘째 항이 있는 이유) |
| | `buildPushGridMetadata(cols, rows, startX, startY, invertY, el, currentRotation, currentSide, validDie)` | 저장될 `grid_metadata` 조립. 🔴 **무엇을 쓸지는 여기서 정하지 않는다** — `validDieRefForPush()`(바꿨는가) + `applyValidDieRef()`(무엇을 쓰는가) + `validDieRefPayload()`(페이로드로), 셋 다 이음매 벡터가 채점한다. 선언 없고 사용자가 안 건드린 맵의 페이로드는 `2a9f6c4`와 **바이트 단위로 같다**(INV-1) |
| | `confirmMissingSplitDescriptions(updates, valCol, legend)` | split 서술이 빈 값에 대한 확인. **판정이 아니라 보고**다 — 예라고 하면 계획은 불완전한 채 저장된다 |
| | `outsideCircleNoteForPush(cols, rows, currentRotation, gridCells2D, gridData)` | [M4②] 원 밖으로 나가는 셀을 **이미 있는 확인문의 한 줄로** 말한다. 🔴 **말할 것이 없으면 `''`를 돌려주므로 확인문이 글자 하나 안 바뀐다**(INV-1) |
| **R5 `resolveValidDie`** | `fitGridToMask(keys, el, currentRotation, currentSide)` | ① 파생 격자가 마스크를 온전히 담는가. `set` 클로저에서 **글자 그대로** 들어냈고 진단 로그 문구를 돌려준다(대입은 호출부) |
| | `summariseReseat(seatsBefore, placed, nc, nr, gridData, loadedFCells, serverCellKeys)` | ② **넷 이동량을 물리 좌석 키의 집합 차이로** 잰다. `netMoved > 0` 분기는 호출부가 그대로 갖고 있어 제어 흐름 무변경 |
| | `resolveReferenceSpec(ref)` | ③ 참조 맵의 키 스펙·좌표 바인딩·메타·프레임. await 사슬 하나, 거절 셋, **모듈 상태 0**. `ref.mapKey`는 종전대로 **제자리에서** 캐노니컬화된다. 🔴 **거절은 취하지 않고 사유로 돌려준다** — `refuse`는 모듈 상태를 쓰므로 오케스트레이터에 남는다 |
| | `deriveMaskKeys(rawKeys)` | ④ 마스크 키 집합과 그 중심. 🔴 **0으로 둔 평행이동 항과 「왜 0이어야 하는가」의 경고가 함께 옮겨졌다** — 수와 사유를 떼어 놓은 것이 그 항을 한 번 되살렸던 경위다 |
| | `diagnoseDesignationAlignment(refResolved, hereResolved, refMinX, refMinY, hereInvertY, el, currentRotation, currentSide)` | ⑤ 지정 **뒤** 참조 맵과 이 맵이 무엇이 다른가. **두 축(원점·크기)은 독립**이라 각각 재고 성립할 때만 보고한다. 🔴 **지정이 끝난 뒤의 격자로 푼다** — 옛 치수로 푼 진단은 사용자가 보고 있지 않은 화면을 설명한다 |

#### 이 파일이 더는 소유하지 않는 것 (2026-08-04 추출 2건)

🔴 **아래 이름들을 이 파일 안에서 Grep하면 `import` 문만 나온다. 지역에서 다시 철자하지 마라** — 두 번째 의견이 이 추출이 없앤 결함이다([§0 ⑬](#0-묘비-목록--소스에-존재하지-않는-이름)).

| 나간 것 | 간 곳 |
|---|---|
| `canonicalKeyValue` · `composeMapId` · `decomposeMapKey` · `canonicalMapKey` · `getMapIdFromMeta` (+ private `canonIntString` · `CANON_INT_RE` · `CANON_FLOAT_RE`) | 🆕 **`map_key.js`** |
| `normalizeBands` · `normalizeKnobs` · `normalizeLegendItem` · `cloneLegend` · `registryFingerprint` · `buildLegendRegistryUpdates` · `parseLegendRegistryRows` · `getMissingDescValues` · `formatLegendMetaText` · `legendRowSignature` (+ private `LEGEND_PAYLOAD_COLUMNS` · `legendRowPayload` · `canonRegistryRow` · `FP_UNIT`/`FP_ROW` · `SPLIT_KEY_SEP` · `buildSplitKey` · `parseJsonCol` · `knobsToObject` · `serializeKnobs` · `serializeStack` · `serializeMaterials`) | 🆕 **`split_registry_row.js`** |

**남은 import**: `transfer_plan.js`의 `initTransferPlan`·`notifyMapContext`·`notifyLegendChanged`·`notifyPaintCounts`·`stageTargetTables` · `doe_bands.js`의 `parseMaterialList`·`bandsToZones`·`ZONES`·`ZONE_LABEL`·`DOE_COLUMNS`·`columnIdByHeader`·`looksLikeHeader`·`mapPastedGrid` · `tsv.js` · `effort_meter.js`.

#### 🪦 죽은 모듈 레벨 선언 2종 — **의도적으로 남겨 둔 것**이므로 「없는 이름」으로 읽지 마라

| 이름 | 상태 | 실측 |
|---|---|---|
| **`let tables = []`** | 🪦 **참조 0건.** 선언 외에 이 식별자를 읽거나 쓰는 곳이 없다 | `git grep -nw tables -- client2/src/map_editor.js`의 나머지 히트는 전부 `data.tables`·URL 문자열·주석이다 |
| **`let isMouseDown = false`** | 🪦 **쓰기 전용.** 대입 2곳(true 1 · false 1)뿐이고 **읽는 곳이 0건** | 조건식·반환·전달 인자 어디에도 등장하지 않는다 |
| ~~`validDieRefTableTouched`~~ | 🪦 **[신설 묘비] 삭제됐다.** 종전 지도가 모듈 상태로 등재하던 이름이고, 지금 이 파일에 남은 것은 **2420의 묘비 주석 1건**뿐이다 | `git grep -n "validDieRefTableTouched" -- client2/src` → **주석 히트 1건, 선언 0건** |

⚠️ **둘 다 제거가 보드에 올라 있어 남겨 뒀다.** 지우는 것이 옳지만 그 판단은 client/map 도메인 소관이고, **여기서 행을 삭제하면 다음 사람이 "이 지도가 못 봤나 보다"라고 읽는다.** 죽은 것은 지우는 것이 아니라 **죽었다고 표시**한다.

#### 🔴 [2026-08-06 `92e60ca` S2.1] **프레임은 모듈 상태가 아니라 첫 번째 인자다** — 이 절의 모든 시그니처가 바뀌었다

> **`let physFrameOverride`와 `withPhysFrame(frame, fn)`은 삭제됐다.** 종전 지도가 `1432`·`1538`에 **살아 있는 앵커로** 등재하던 두 이름이고, 지금 이 파일에 남은 것은 **주석 히트뿐**이다(`1443`·`1673`·`1874`·`1902`·`2044`·`2098`·`2486`). 모듈 바인딩을 읽던 함수들은 이제 **프레임을 선두 인자로 받는다.**
>
> 🔴 **이것이 이 문서에서 가장 위험한 종류의 낡음이다.** 인자가 하나 앞에 끼면 옛 호출은 **던지지 않고 틀린 답을 낸다** — `getDbCoords(colVisual, rowVisual, …)`로 부르면 `colVisual`이 `frame` 자리에 앉고 나머지가 한 칸씩 밀린 채 **캔버스는 멀쩡히 그려지고 저장 좌표만 갈린다.** 이 파일이 존재하는 결함 계급 그대로다.
>
> ⚠️ **`null`과 `undefined`는 다른 답이다** — 소스에 명시된 계약이다. `null` = "프레임 없음, 화면 컨트롤을 읽어라"(메인 로드의 경우, **의도된 답**). `undefined` = **호출자가 빠뜨렸다** → `physNum`·`gridDimNum`이 **throw**한다(`1459`·`1473` 부근). 모듈 바인딩 시절엔 창이 자동 적용돼 빠뜨리는 것이 불가능했으므로, 인자화가 그 실수를 처음으로 가능하게 만들었다. **던지는 것은 백스톱이지 보호가 아니다** — 보호는 전 호출부를 열거해 명시 인자를 준 것이다.

| 함수 | 현행 시그니처 (**`cfa22ce`** blob 실측) |
|---|---|
| `physNum` | **`physNum(frame, key, domEl, dflt)`** |
| `gridDimNum` | **`gridDimNum(frame, key, domEl, dflt)`** |
| `geometryIsAutoRegistered` | **`geometryIsAutoRegistered(frame)`** 🆕 |
| `physDeclaration` | **`physDeclaration(frame, key, domEl)`** |
| `frameChosenFrom` | **`frameChosenFrom(frame)`** 🆕 |
| `getDieIndex` | **`getDieIndex(frame, colVisual, rowVisual, cols, rows, rotation, side)`** |
| `getCanvasCellFromDieIndex` | **`getCanvasCellFromDieIndex(frame, xp, yp, cols, rows, rotation, side)`** |
| `getCanvasCellFromDb` | **`getCanvasCellFromDb(frame, dbX, dbY, cols, rows, rotation, side, invertY, startX, startY)`** |
| `getWaferBoundingBox` | **`getWaferBoundingBox(frame, rotation, side, opts)`** |
| `getDbCoords` | **`getDbCoords(frame, colVisual, rowVisual, cols, rows, rotation, side, invertY, startX, startY)`** |
| `seatingSnapshot` | **`seatingSnapshot(frame)`** |
| `getTransformedPhysicalConfig` | **`getTransformedPhysicalConfig(frame, currentRotation, currentSide)`** |
| `isValidDieAt` | **`isValidDieAt(frame, physX, physY, circleInside, state)`** |

- 🔴 **`physNum`의 기지 결함 D1은 살아 있다** — `if (Number.isFinite(ov)) return ov \|\| dflt;`도, 화면 폴백의 `return v \|\| dflt`도 **falsy 검사**라 선언된 `0`이 기본값으로 치환된다. 이 함수가 읽는 키는 **`waferDia`(기본 300) · `chipX`(2.5) · `chipY`(2.5) · `offsetX`(0.0) · `offsetY`(0.0) · `edgeMargin`(3.0)** — 기본값이 0인 `offsetX`/`offsetY`는 0을 0으로 돌려주므로 무해하고, **선언 `0`이 의미를 갖는데 기본값이 0이 아닌 것은 `edgeMargin`**이다. `phys_edge_margin: 0`이 조용히 3.0mm가 되고 유효 반지름에서 유도된 기하 전부가 함께 움직인다. **서버(`map_overlay._frame_phys_params`)는 0을 0으로 읽으므로 이것은 이음매 결함이다.**

#### 좌표 변환 코어 — 변환 구현은 하나다

- **`getDieIndex(frame, colVisual, rowVisual, cols, rows, rotation, side)`** / **`getCanvasCellFromDieIndex(frame, xp, yp, cols, rows, rotation, side)`** — 서로의 **정확한 역함수**. 물리 키의 원점은 **웨이퍼 중심**이지 격자 중심이 아니다. 되기준 항에서 남긴 것은 크기가 아니라 **패리티**다(짝수 격자면 웨이퍼 중심이 칸 경계에, 홀수면 칸 한가운데에 앉는다 — 운영 데이터 214개 맵 중 **163개가 짝수 치수**). ⚠️ **헬퍼로 빼지 않는다** — 이 둘을 슬라이스해 실행하는 하니스가 넷이라 모듈 전역 의존이 하나 늘 때마다 넷이 전부 `ReferenceError`로 죽는다.
- **`getCanvasCellFromDb(frame, dbX, dbY, cols, rows, rotation, side, invertY, startX, startY)`** / **`getDbCoords(frame, colVisual, rowVisual, cols, rows, rotation, side, invertY, startX, startY)`** — 저장 좌표 ↔ 캔버스 칸. **같은 상자에서만** 역함수다. ⚠️ **종전 지도의 「…같은 인자…」는 거짓이었다** — 둘은 역함수라 **입력이 서로 반대**다(`dbX, dbY` ↔ `colVisual, rowVisual`). 인자 이름을 생략한 서술이 그 반대를 숨겼다.
- **`getWaferBoundingBox(frame, rotation, side, opts)`** — **좌표계의 원점 상자.** 기준은 **유효 다이 영역**이다(원 bbox는 회전·반전에 거의 불변인데 유효 다이 영역은 아니다 — 「회전할 때마다 origin이 틀어지네」의 정체). 판정을 새로 쓰지 않는다: 원은 `isCellInsideWaferFast`, 마스크는 `isValidDieAt`, 렌더 루프가 부르는 그 둘을 **같은 순회 안에서** 누적한다(두 번째 전수 순회를 만들지 않기 위해). 캐시 `boundingBoxCache`, 캐시 키 첫 항은 **근거 태그**(`'C'` = 원 기하 / `V<validDieResolveSeq>` = 해석된 마스크 — 셀 **개수**로 태그를 만들면 같은 크기의 다른 참조가 서로의 상자를 덮어쓴다). `opts.circleOnly`의 **유일한 소비자는 `computeNotchCell`**. ⚠️ **마스크가 격자 안에 한 칸도 없으면 원 상자로 돌아간다** — 빈 상자는 `{0,0,0,0}`으로 무너져 좌표계 전체를 조용히 옮긴다. **미상은 0이 아니다.**
- 🆕 🔴 **[`cd3e0f4`] 진짜 밀리미터 공간이 들어왔다 — 「규칙 6」 오버레이의 좌표계다.** 아래 셋이 mm 변환의 전부이고 **회전·반전·오프셋은 한 줄도 없다**(전부 `getDieIndex` 안에서 끝난다 — 여기서 더하는 것은 **단위 환산 하나**뿐):
  - **`frameDieLattice(frame)`** — 격자 기준점을 `getDieIndex`**에게 묻는다**(캔버스 칸 (0,0) 하나를 그 함수에 넣어 얻은 답). 다이 격자는 간격 1의 정수 격자이므로 **기준점 하나가 격자 전체를 정한다** — 패리티·회전 부호표·오프셋 부호표가 여기 한 줄도 없는 이유가 그것이다. `ix0`는 반올림된 인덱스, **`ux0`는 반올림 전 연속값**.
  - **`dieIndexToWaferMm(ix, iy, L)`** — 다이 인덱스 → 그 다이 **중심**의 절대 웨이퍼 mm.
  - **`waferMmToDieCell(mmX, mmY, L)`** — 위의 역함수, **단 나머지를 버리지 않는다**: 몫 = 그 점을 담는 다이 인덱스, 나머지(`rx`/`ry`) = 그 다이 **안에서의** `[0, 피치)` 밀리미터. 🔴 **나머지는 절대 길이라 피치에 의존한다** — 7mm 칩 안의 3mm와 15mm 칩 안의 3mm는 다른 자리다. 그래서 칩 내 좌표는 맵 사이를 그대로 건널 수 없고 **반드시 절대 mm를 거쳐 다시 나눠야** 한다.
  - ⚠️ **곱하는 피치는 선언된(회전 전) 물리 피치**다. `getTransformedPhysicalConfig`가 90/270에서 스왑한 화면 피치가 **아니다** — `getDieIndex`가 이미 화면을 물리 축으로 되돌려 놓았다.
  - ⚠️ **`isCellInsideWaferFast`는 여전히 700×700 픽셀 공간이다**. **mm 공간과 픽셀 공간은 별개**이고 둘을 섞으면 안 된다. ([§0 ⑫](#0-묘비-목록--소스에-존재하지-않는-이름)의 「`mm`은 비어 있는 이름」 검사는 이 블록이 착지하면서 **폐기됐다.**)
- `getTransformedPhysicalConfig` · `getScreenShift` · `isCellInsideWafer`.
- **프레임 규격 독법** — `physNum(frame, key, domEl, dflt)`/`gridDimNum(frame, key, domEl, dflt)`/`physDeclaration(frame, key, domEl)`. 🪦 **`physFrameOverride`와 `withPhysFrame`은 삭제됐다**(위 S2.1 표) — 「창을 열었다 닫는다」는 서술은 더는 성립하지 않는다. **프레임은 인자로 흐른다**: 규격을 읽어야 하는 함수가 자기 프레임을 받아 그대로 아래로 넘긴다. 종전의 「주입 지점 두 곳」(`getTransformedPhysicalConfig`·`getWaferBoundingBox`)은 이제 **그 둘이 `frame`을 첫 인자로 받는다**는 뜻이다. `withPhysFrame`의 「동기 전용(내부 `await` 금지)」 제약도 함께 사라졌다 — 복원할 전역이 없다.
  - 🔴 **`physNum`은 계약이 이름 붙인 기지 결함 D1의 현장이다** — `return v || dflt`가 **falsy 검사**라 선언된 `0`이 기본값으로 치환된다. 6개 호출부 중 기본값이 0이 아닌 것은 `edgeMargin`(3.0) 하나뿐이라 `phys_edge_margin: 0`이 조용히 3.0mm가 되고 유효 반지름에서 유도된 기하 전부가 함께 움직인다. **서버(`map_overlay._frame_phys_params`)는 0을 0으로 읽으므로 이것은 이음매 결함이다.**
- 🔴 **`isValidDieAt` 호출부 — 감싸는 함수로 전건 열거**(개수를 적지 않는다. 개수는 다음 라운드가 하나 더하면 조용히 거짓이 되고, **개수만 맞으면 위치가 전부 틀려도 통과한다**). 확인: `git grep -n "isValidDieAt" -- client2/src/map_editor.js`:

  | 감싸는 함수 | 첫 인자 |
  |---|---|
  | `getGridCellObject` — 셀 객체 조립 | `null` |
  | `getWaferBoundingBox` — 마스크 누적 루프 | **`frame`** |
  | `renderGridCanvas` — 캔버스 | `null` |
  | `fillGrid` | `null` |
  | `getEdgeClassification` — 엣지 분류 | `null` |
  | `canvasSeatKeys` | `null` |

  🔴 **두 번째가 요점이다** — 마스크 판정이 **좌표계 자신**의 입력이고, **실제 프레임을 넘기는 유일한 호출부**이기도 하다. 나머지 다섯은 `null`(= 「화면을 읽어라」, 의도된 답)이다. ⚠️ **`null`을 빠뜨려 인자를 하나 앞당기면 `physX`가 `frame` 자리에 앉는다 — 던지지 않고 틀린 답을 낸다.**

#### 규칙 ④ — 「원점 상자가 셀 밑에서 움직였을 때」의 유일한 반응

- 🔴 **붙드는 것은 저장 좌표이고 움직이는 것은 캔버스 칸이다**(사용자 확정: 「db 좌표 보존이야」). 셀이 칸을 붙들면 근거가 바뀔 때 읽는 번호가 바뀌고 ⚡ Push가 그 새 번호를 쓴다 — **화면은 한 픽셀도 안 움직인 채 DB의 좌표가 갈리는**, 이 도메인이 존재하는 그 결함이다.
- **`cellsSeatedUnder`, `let … = null`)** — 셀이 **마지막으로 앉은** 좌표계 기록. 🔴 **상자에 대한 두 번째 진실이 아니다**: 상자가 무엇인가는 `getWaferBoundingBox` 하나만 답하고, 여기 담기는 것은 **그 함수가 이미 내놓은 답**이다. 뜻은 "무엇이 옳은가"가 아니라 **"셀이 마지막으로 어디에 앉았는가"**다. 둘을 대조해 화해시켜야 하는 상황이 생기면 **설계가 틀린 것이므로 화해시키지 말고 보고할 것.**
- **`seatingSnapshot(frame)`** — 그 기록을 만드는 순수 수집기. ⚠️ **키 이름이 `currentFrame`·`frameFromMeta`가 쓰는 그 이름이어야 한다** — 이 객체를 그대로 `withPhysFrame`에 넘겨 **옛 좌표계를 다시 열기** 때문이다. 🔴 **프레임 창 안에서는 `null`을 돌려준다**(소스 맵의 좌석을 이 화면의 좌석으로 기록하지 않기 위해).
- **`reseatCellsToStoredCoords(was)`** — **반응 그 자체.** 반환 `null`(반응 없음) | `{moved, offGrid, visC, visR, held}`.
  - ① 옛 좌표계를 `withPhysFrame(was, …)`로 다시 열어 각 셀이 그때 말하던 저장 좌표를 되찾고 ② 그 좌표가 새 좌표계에서 가리키는 칸으로 다시 앉힌다. 🔴 **새 변환식은 한 줄도 없다** — 도는 것은 로드·렌더가 쓰는 바로 그 함수들이고 되앉히는 것은 그 둘의 역함수다.
  - ③ **`gridData`·`loadedFCells`·`serverCellKeys.keys`를 함께 리키잉한다.** 🔴 **서버 셀 집합을 같이 옮기지 않으면** 서버에서 온 셀이 「보낸 적 없음」으로 읽혀 정리 경로가 **실재하는 행을 지우자고 제안한다.**
  - 🔴 **방향(회전·반전·Y반전)과 START는 반대 연산이다**(규칙 ⑤: 다이를 붙들고 번호를 옮긴다). 그 축이 하나라도 다르면 **이 반응은 아무것도 하지 않는다** — 기하 반응이 회전에서 뜨면 규칙 ④가 규칙 ⑤를 덮어쓴다.
- 🔴 **호출 지점 — 전건 열거**(정의. 개수는 적지 않는다):
  1. **격자 치수(cols/rows) 편집 리스너**(`initDOMElements` 안) — 「격자 치수도 기하 편집이다」. 「격자 치수도 기하 편집이다 — 물리 규격 한 칸을 고치는 것과 같은 연산」. 치수가 바뀌면 ① 원점 상자(원의 반지름은 칸 수로 고정인데 중심이 `visualCols / 2`라 격자가 넓어지면 원 전체가 미끄러진다)와 ② 다이 인덱스 자체가 **함께** 움직이고, 저장 좌표가 갈리는 것은 그 **차이**다. 실측(생산 프레임 3개 × 각 축 ±1~±3): **36건 중 16건이 어긋났고, 어긋난 16건은 예외 없이 셀의 100%였다**(261/261 · 273/273 · 461/461). ⚠️ **"상자가 안 움직였으면 반응할 것도 없다"는 참이 아니다** — QERWER 23→22열은 `box.minC`가 2에서 그대로인데 261칸 전부가 다시 번호를 받았다.
  2. **`onPhysicalGeometryEdit`** — ⚠️ **`initDOMElements` 안의 지역 화살표 함수이지 모듈 레벨 함수가 아니다.** 모듈 레벨에서 이 이름을 Grep하면 없다. `input`/`change`는 DOM 값이 **이미 바뀐 뒤** 뜨므로 이 리스너는 변경 전 상태를 스스로 잡을 수 없다 — 그래서 직전 렌더가 남긴 `cellsSeatedUnder`가 옛 좌표계다. **이 기록이 필요한 이유가 정확히 이것이다.**
  3. **`applyPhysicalGeometry`**(`applyPresetObject` 안에서 호출된다) — 파생 치수가 자리를 잡은 **뒤**, 렌더보다 **앞**. 순서가 전부다: 옛 치수로 앉히면 렌더가 새 치수로 좌표를 되만들어 저장 좌표가 옮겨가고, 렌더 뒤에 물으면 비교할 옛 좌표계가 이미 갱신돼 있다.
  4. **`resolveValidDie`의 `set()` 안**.
- ⚠️ **호출자는 기록을 캐시하지 않는다** — 반드시 **부르는 시점에** `cellsSeatedUnder`를 읽어야 한다. 이 함수가 끝날 때마다 기록을 갱신하므로 한 번의 조작이 반응을 두 번 타도 두 걸음이 이어 붙는다. **미리 잡아 둔 옛 기록을 두 번째 걸음에 넘기면 같은 이동을 두 번 적용한다.**
- 🔴 **근거가 무엇이든 같은 반응이다** — 유효 다이 선언이 없는 맵에서 유효 다이 영역은 곧 웨이퍼 원이므로, **기하 프리셋을 바꾸는 것과 참조를 지정하는 것은 같은 연산이지 닮은 연산이 아니다.** 그래서 함수도 하나다.
- **채점자**: `client2/tests/geometry_origin_reseat_harness.mjs`, 게이트 배선([§6-2](#6-2-교차-구현-계약-contracts)).

#### 유효 다이(valid die)

- 모듈 상태 `validDie` · **`validDieResolveSeq` — 경쟁 해소 세대 카운터이자 `getWaferBoundingBox`의 캐시 태그)**. 🪦 **`validDieRefTableTouched`는 삭제됐다**(위 묘비 표) — 구 지도가 `~2005`에 등재하던 이름이고 **지금 이 파일에는 선언이 없다.**
- `parseValidDieRef(meta, currentTable)` · `validDieBasis(state)` · **`isValidDieAt(frame, physX, physY, circleInside, state)` — 판정이 갈리는 유일한 지점. 참조가 없으면 인자로 받은 원 판정을 그대로 돌려준다)** · `buildValidDieTemplate(shape)` · `validDieRefDisplay` · `applyValidDieRef` · `validDieRefFromControls` · `validDieRefForPush` · `validDieRefPayload` · `validDieChainError`. 상수 `VALID_DIE_TEMPLATE_PREFIX` · `VALID_DIE_TEMPLATE_OPTIONS` · `VALID_DIE_LIST_LIMIT=500`.
- 🔴 **`resolveValidDie(meta, targetTable, homeMapKey)`** — ⚠️ **시그니처는 3인자 그대로.** 세 번째는 선언 맵 자신의 키이고 **자기참조 체인 관문** 전용이다. 지역 클로저 `set(basis, keys, reason, ref, physPreset)`의 **순서가 계약**이다:
  1. **좌석 기록 확보** — 한 번도 그리지 않았으면 지금 잡는다. ⚠️ **여기서 지역 변수에 캐시하면 안 된다**(아래 `applyPresetObject`가 같은 반응을 먼저 한 걸음 돌린다).
  2. **`validDie` 대입.**
  3. **[규칙 ①] 기하 재로드** — `applyPresetObject(physPreset)`(호출, 선언)으로 참조의 **규격**을 갈아끼우고, 그 안의 `applyPhysicalGeometry`가 **새 규격에서 cols/rows를 다시 파생**한다. 🔴 **치수는 인자로 넘기지 않는다 — 규격에서 파생시킨다.** 삭제된 프레임 채택 함수가 거절당한 것은 참조가 **선언한** cols/rows를 베끼면서 셀은 칸에 그대로 둬 **273칸 전부의 좌표를 움직였기** 때문이다. **파생과 재배치는 한 쌍이고 한쪽만 하면 그것이 거절당한 그 동작이다.**
  4. **마스크 적합 격자 확장** — 파생 격자가 마스크를 온전히 담지 못할 때만, 담을 때까지만 **한 번에 한 칸**. 상한은 편집기의 치수 정의역(`frameDimBounds`에서 온다. 상한에 닿으면 **더 넓히지 않고 멈추고 사유를 남긴다.** 🆕 ⚠️ **이 블록은 더는 인라인이 아니다 — `fitGridToMask`로 뽑혀 나왔다.** 슬라이스 하니스가 죽지 않는 이유는 그 함수가 **읽는 모든 바인딩을 인자로 받아 모듈 상태를 0으로** 유지하기 때문이고(본문은 인라인 시절과 바이트 동일), 그것이 이 추출의 성립 조건이었다.
  5. 🔴 **`boundingBoxCache = {}`** — 세대 카운터는 **진입 시** 오르는데 `validDie` 대입은 그 뒤다. **그 사이에 상자를 한 번이라도 물으면 옛 마스크로 만든 상자가 새 번호의 키에 실린다.**
  6. **`reseatCellsToStoredCoords(cellsSeatedUnder)`(호출)** — 기하 프리셋 편집이 타는 것과 **같은 함수**. 🔴 **인자는 지금 읽는다.**
  7. **넷 이동량은 좌석 집합의 차이로 잰다**(🆕 `summariseReseat` — 걸음마다 세면 서로 상쇄되는 두 걸음이 「N칸 이동 후 N칸 이동」으로 읽혀 **사용자에게 거짓 수를 준다.**
  - 🔴 **마스크 재중심화(평행이동)는 삭제 상태 그대로다 — 되살리지 마라.** 평행이동은 마스크의 bbox 중점을 격자 중심에 끌어다 놓는데, 웨이퍼 위에서 실제로 치우쳐 앉은 유효 다이 영역은 그 조작으로 자기 다이에서 벗어난다. **실측(`bonding_map/DTWWER ← BASE_4E`, 독립 오라클 대조): 평행이동이 (0,1)을 만들어 262칸 중 21칸이 틀린 다이에 앉았고, 0으로 두면 262칸이 오라클과 정확히 일치한다.**
  - 🔴 **START X,Y는 편집기가 바꾸지 않는다**(사용자 확정: 「START X,Y는 바뀌면 안됨」). 그래서 오리진 셀은 `box.minC − startX`에 선다.
  - 🔴 **토스트가 말하는 두 수는 다른 것을 잰다**: `originDiffer`는 **프레임 정렬의 사실**이고 데이터를 움직이는 양이 **아니다**. `screenShift`는 **이번 지정으로 셀과 마스크가 화면에서 실제로 움직인 칸 수**다. 발화는 `console.info` 1줄 + **토스트 1회**(`dedupeKey:'valid_die_frame_differs'`) — **확인창이 아니라 토스트인 것이 UI 규율**이다.
  - ⚠️ **`[유효다이]` 콘솔 줄에 em dash(U+2014)·이모지를 쓰지 않는다** — 운영 콘솔이 한국어 Windows(cp949)라 한 글자에 로깅 핸들러가 **줄 전체를 버린다**(U+2015 `―`를 쓴다).
  - **`catch`는 예상된 실패의 자리가 아니다** — 조회·데이터·계약 실패는 전부 위에서 `refuse`가 저자의 문구로 거절했다. 여기까지 오는 것은 대개 **프로그래머 오류**이고, `e.message`를 그대로 사유로 흘리면 **"거절은 사유를 가진다"는 계약을 스택 트레이스가 만족시킨다.** 판정은 `e.name`으로 한다(`instanceof`는 realm이 다르면 조용히 거짓이 된다).
  - `frameDimError` · 저작·표시: `renderValidDieChip` · `syncValidDieRefControls` · `onValidDieRefChanged` · `populateValidDieRefList` · `enterValidDieAuthoring(shape)`.
  - 🪦 **`saveValidDieRefDeclaration()`은 삭제됐다**(`5b15c24` — 유효 다이 블록의 🎯 APPLY·💾 SAVE 버튼과 함께). 구 지도가 **살아 있는 앵커 `8560`으로 등재**하던 이름이고, 지금 이 파일에 **선언도 주석도 0건**이다. 삭제 사유: 그 함수는 `valid_die_ref` **한 필드**만 썼는데 그 필드는 ⚡ Push가 이미 함께 실어 나른다.
  - 🆕 **그 자리를 받은 것은 `saveMapSpecOnly()` — 「📐 규격만 저장」이고, 한 필드가 아니라 *규격 블록 전체*를 셀 없이 쓴다**(격자·START·회전·면·물리 규격). 배선 `el.btnSaveMapSpec`, 리스너).
    - 🔴 **새 라우트는 없다** — 구 SAVE가 쓰던 그 PUT(`wafer_map_metadata/data/updates`)이고 `business_key_val` upsert라 **없는 행을 만드는 것도 같은 호출**이다.
    - 🔴 **규격 객체의 조립기는 하나다**: `buildPushGridMetadata` — ⚡ Push가 부르는 그 함수. 컨트롤 독법도 `readGridFrameControls` 하나를 공유하고, 병합은 순수 함수 `mergeStoredGridMeta(stored, gridMetaOut)`다.
    - 🔴 **정체성은 `loadedIdentity`가 아니라 *지금 화면의 컨트롤*이다**(사용자 지시 — 맵을 열고 키를 바꿔 새 정체성으로 기하를 등록하는 것이 이 기능의 쓰임이다). ⚠️ **구 지도의 「서버본에서 유래한 화면만 저장 권한을 가진다(`loadedIdentity` 없으면 거절)」는 이제 거짓이다.** 대신 오타 하나가 **없던 맵을 등록**할 수 있으므로 확인문이 대상과 신규/갱신을 이름으로 말하고, 그 신규/갱신은 추정이 아니라 **`fetchGridMetaFor`로 읽어서** 정한다.
    - `getCurrentMapKey()`가 null이면 거절한다 — ⚡ Push는 그 자리에서 `'default_map'`으로 물러서지만 **규격 등록은 자리 표시자 정체성에 행을 만드는 일**이라 물러서지 않는다.
    - **`fetchGridMetaFor`의 「선언 없음(null)」/「확인 못 함(throw)」 구분을 그대로 쓴다**: 확인 못 한 규격 위에 되쓰면 cols/rows/START/회전/물리가 **한 번의 저장으로 사라진다**. **UI 규율 — 읽기는 무마찰, 쓰기는 확인창 정확히 1회.**
- 🪦 **프레임 채택 함수 8개는 여전히 삭제 상태다**([§0 ⑦](#0-묘비-목록--소스에-존재하지-않는-이름)). **이 라운드가 그 경계를 다시 시험했다** — `resolveValidDie`가 참조의 **물리 규격**을 들여오지만 **치수를 베끼지는 않는다**(규격에서 파생시킨다). **채택이 거절당한 이유는 "참조의 값을 쓰는 것"이 아니라 "셀을 칸에 둔 채 치수를 바꾸는 것"**이었다.

#### 프레임 스택 · 오버레이

- 프레임: `editorFrames` · `snapshotEditorState`/`restoreEditorState` · `openMapFrame(spec)` · `popMapFrame` · `frameFromMeta(meta)` · `frameDimBounds` · `currentFrame` · `resolveFrame` · `frameAxesKey`.
- 🔴 **[`cd3e0f4`] 오버레이 투영이 mm를 경유한다** — **`projectCellsToWaferMm(cells, frame)`**가 실제 계산이고, **`projectCellsToPhys(cells, frame)`는 그 결과에서 키만 옮기는 얇은 래퍼**다(시그니처·의미는 종전 그대로 — 유효 다이 해석의 입력이다). 🔴 **같은 수를 두 번 계산하지 않는다.**
  - 🔴 **`mm`은 반올림 전 연속값(`p.xCells`)에서 만든다** — 반올림된 `p.x`에서 되만들면 오프셋의 칸 미만 잔여가 빠져 **모든 셀이 그만큼 밀린다**(실측: 이 fixture에서 1836칸 중 **1789칸**이 틀린 타깃 칸에 앉았다).
  - ⚠️ **피치가 없으면 `mm`이 null인 항목이 나오고 여기서 거절하지 않는다** — 거절 문구를 쓰는 자리는 호출자(오버레이)이고, 유효 다이 해석은 mm를 아예 보지 않는다.
- **`seatWaferMmInFrame(items, frame)`** — [규칙 6] 물리 mm 항목을 **타깃 프레임의 칸에 앉힌다.** 반환 `Map(다이키 → 항목 **배열**)`. 🔴 **대표값을 고르지 않는다**(사용자 확정 「전부 나열」): 타깃 피치가 소스보다 굵으면 한 칸이 소스 여러 칸을 받는데(실측 최대 6) 대표를 고르면 나머지를 조용히 버리면서 **한 값을 자신 있게** 보여 준다. 단 **같은 물리 위치의 같은 값은 접어 넣는다**(정보가 아니라 소스에 같은 행이 두 번 있을 뿐 — 접지 않으면 피치가 **같은** 맵도 fanout 2가 되어 「여러 값」 가져오기에서 제외된다). 위치가 같은데 값이 다르면 그것은 중복이 아니라 **충돌**이라 둘 다 남긴다. ⚠️ **앉히는 기준은 지금 화면의 프레임이다.**
- `canvasSeatKeys()`, 캐시 `seatKeyCache` · `reseatOverlayLayer(o)` · `overlayGeomSig`/`currentGeomSignature()`/**`syncOverlayGeometry()`** — ⚠️ **mm 좌석은 피치의 함수라 화면 규격이 바뀌면 다시 앉혀야 한다**(종전 다이 인덱스 키는 화면에 불변이었다). `overlayAlignChip`/`overlayFanChip`.
- 오버레이 본체: `OVERLAY_COLORS` · `overlayLayers`/`activeOverlayLayers`, 렌더 루프에서 재계산 금지용 캐시)/`overlaySeq`/`recomputeActiveOverlays()` · `drawOverlayMarkers` · `pushFailedOverlay` · `OVERLAY_CELL_LIMIT=2000` · `buildKeyFilters` · `addOverlayLayer` · `removeOverlayLayer`/`toggleOverlayLayer`/`clearOverlayLayers`.

#### 🆕 오버레이 점의 색 — **선언된 색이거나 아니면 색이 없다**

**[2026-08-04 신설 5종]** 오버레이 점이 **자기 값이 선언한 색**을 입는다. 색이 **두 번째 뜻을 나르게 됐으므로**(레이어 소속 + 값) 그 둘이 서로를 지우지 않게 하는 규율이 함께 들어왔다.

| 함수 | 계약 |
|---|---|
| 🔴 **`legendColorForValue(val)`** | 값 → 색. 근거는 둘뿐이다: ① 지금 열린 맵 자신의 `legend` 행(= 화면의 범례표가 지금 보여 주는 그 색) ② 없으면 서빙된 `map_overlay_config.default_legend`(`declaredLegendRow`). 🔴 **둘 다 없으면 `null`이고 그 `null`은 사실이다 — 이 값에 색을 선언한 사람이 없다.** 🔴 **`pickUnusedColor()`를 여기서 절대 부르지 않는다** — 그 함수는 색을 **지어내므로**, 미선언 값에 자신 있는 색을 입혀 **화면은 멀쩡하고 뜻은 틀린** 상태를 만든다. 이 도메인이 존재하는 결함 계급이 정확히 그것이다 |
| **`overlayMarkerFill(list)`** | 점 하나의 채움. 🔴 **답할 값이 정확히 하나일 때만 채운다.** 셀이 소스 칩을 여럿 받았는데 작아서 구분해 보일 수 없을 때 `list[0]`의 색을 쓰는 것은 **사용자가 거부한 그 「대표값」**이다 — 나머지를 버리면서 자신 있어 보인다. 그래서 **속 빈 점은 뜻이 정확히 하나**다: *이 점은 선언된 색 하나를 지목하지 않는다* |
| `paintOverlayDot(ctx, cx, cy, radX, fill, ringColor, radY)` | 점 하나를 그린다. **테두리(ring)가 레이어 색**이라 채움이 무엇이 되든 **어느 오버레이의 점인지는 여전히 읽힌다**(위치는 그것을 나를 수 없다 — 1:1 분기의 슬롯 인덱스는 그 셀에 실제로 그린 레이어만 소비한다). 흰 후광이 둘 사이에 앉아 **자기 값과 같은 색으로 칠해진 셀에 점이 사라지지 않게** 한다 |
| 🔴 **`overlayUnlistedValues(o)`** | **[N2] 속 빈 점 하나로는 두 사유를 구분할 수 없다**(「미선언 값」 vs 「한 셀에 여러 값」). 그래서 **말로** 가른다 — 여러 값 쪽은 `overlayFanChip`이 이미 말하고, 미선언 쪽이 이것이다. 🔴 **추가 시점에 캐시하지 않고 라이브 legend에서 다시 센다** — 사용자가 그 값을 범례에 추가하는 순간 칩이 줄어야 하는데, **잡아 둔 수는 조용히 낡고 낡은 수는 결함과 구분되지 않는다** |
| `overlayLegendChip(o)` | 위 목록을 칩 문구로(최대 8개 + `...`) |

#### 서빙된 선언 — 클라 사본 0

- **[U6] 맵 기본값**: `overlayContract` · `EMPTY_DOE_SEED` · `defaultLegendRows()` · `declaredLegendRow(value)` · **`LEGEND_PALETTE`** · `pickUnusedColor` · **`autoAddLegendValue(value, fallbackDesc)` — 값이 legend에 자동 추가되는 유일 경로)**. ⚠️ **`pickUnusedColor`는 색을 *지어내는* 함수라 오버레이 점 경로에서 부르면 안 된다**(위 `legendColorForValue` 참조).
- **[F1/F3] 좌표 바인딩도 서빙받는다 — 클라 매칭기 0**: `servedBindingCache` · `normalizeServedBinding` · `fetchServedBinding(table)` · `fetchPaintRules(table)`. `fillColumnDropdowns`의 드롭다운 preselect가 소비 지점. **`source:'fallback_guess'`는 경고**. ⚠️ ~~`deriveMapBinding`~~은 묘비이고 이 파일에 **주석으로만** 남아 있다.
- **페인트 잠금(config 주입형 — `'F'` 하드코딩 금지)**: `NO_PAINT_LOCK`/`paintLockConfig`/`isLockedValue`/`isOverlayLocked`/`paintLockMessage`/`isProtectedFCell`/`applyPaintLockConfig`/`updatePaintLockIndicator`/`recomputeLockedCells`.

#### Split Registry = DOE의 유일한 기록자

⚠️ **정규화 순수 함수는 전부 [`split_registry_row.js`](#7-client2src--웹-클라이언트)로 나갔다**(위 추출 표). 이 파일에 남은 것은 **상태와 IO**다 — 그것이 추출의 경계선이었다.

- 남은 상태: `SPLIT_REGISTRY_TABLE` · `legendMeta` · **`legendReplaceScope`** · **`legendVocabularySeed`** · **`legendConflict` — M2.6: upsert로 강등하지 않고 거부한다)** · `legendSaveState`.
- 서버 IO: `REGISTRY_SCOPES=['map']` · `fetchRegistryRows` · `readRegistryScope` · `reconcileVocabClaims` · `applyRegistryRowsToLegend` · **`saveLegendToServer(mapKeyOverride)` — 호출자는 `pushMapData` 하나)** · `zoneColumnsPresent`/`ZONE_COLUMNS`/`probeZoneColumns()` · `LEGEND_SAVE_MESSAGE` · `applyLegendSaveResult` · `legendDirty` · `getPlanSaveState` · `persistLegend` · **`scheduleCellDraft`** · `renderLegendMetaOnly`.
  - 🔢 **`scheduleCellDraft`(정의) 호출부 — 전건 열거**(개수를 적지 않는다): **1136 · 3777 · 4750 · 4879 · 4941 · 5886 · 5934 · 6100 · 6675 · 6709 · 6731 · 7921 · 10213 · 10806.** ⚠️ **개수만 확인하고 통과시키면 앵커가 전부 틀린 채로 남는다** — 2026-08-06 실측에서 정확히 그랬다.
- 로컬 초안: `seedEmptyDoe` · `saveLegendToStorage` · `doeDraftKey` · 🔴 **`DRAFT_VERSION = 4`** · `cellsDigest` · `draftBase` · **`serverCellKeys`/`serverCellKeySet()`** · **`saveDoeDraft`** · `readDoeDraft` · `clearDoeDraft` · `applyDoeDraftRecord` · `applyDraftCells`.
- last-open 복원: `LAST_OPEN_KEY` · `recordLastOpenMap` · `restoreLastOpenMap`.
- 패널 관문: `addLegendRowForPanel` · **`updateLegendRowForPanel(value, patch)`** · `deleteLegendRowForPanel`. + `mapKeyColumnCache`/`fetchMapKeySpec`/`fetchMapKeyColumns` · `probeMapExists` · `remapGridValues`.
- 레전드/브러시: `renderLegendTable` · `selectBrush` · `getCurrentMapKey` — **로드된 맵이 아니라 현재 메타 입력 필드**를 읽는다) · `computeLegendCounts`/`updateLegendCounts`.

#### 데이터 IO · 렌더 · 편집 도구

- **`loadExistingMap(opts={})`** — 🔴 **「유효 다이맵 → 오리진 → 셀 위치」가 이 함수의 순서 계약이다**(단계 7종은 [분해 표](#7-client2src--웹-클라이언트) 참조): 회전·면·격자 컨트롤 동기화 → **`await resolveValidDie(…)`** → `boundingBoxCache = {}` → **[규칙 ①-b] 치수를 되읽는다**(유효 다이 해석이 참조 규격에서 치수를 다시 파생시켰을 수 있다) → **그다음에** 셀 루프. ⚠️ **여기서 START X,Y는 되읽지 않는다.** 🔴 **로드 경로에서 재배치는 무비용이다** — `gridData`·`loadedFCells`·`serverCellKeys`를 `resolveValidDie`보다 **먼저** 비우므로 순회할 것이 없다. 사용자 취소는 `{count:0, cancelled:true}`.
  - **📐 표준 로드는 데이터의 원점을 선언한다 — 셀 번호를 다시 매기지 않는다**: `startX = minX`/`startY = minY` + 셀 루프의 뺄셈 삭제. `getDbCoords`(⚡ Push가 `cellObj.x`로 직렬화하는 그것)가 `getCanvasCellFromDb`(로드가 배치에 쓰는 그것)의 **정확한 역함수**라서 **두 줄은 한 양(quantity)**이다. 하니스: `standard_frame_origin_harness.mjs`.
  - `fetchGridMetaFor(table, mapId)`는 **404/405만 "규격 미등록"(null)**로 읽고 그 외 실패는 **throw**한다.
- **`pushMapData()`** — 저장 본체이자 **legend/DOE 저장의 유일한 트리거**(단계 5종은 [분해 표](#7-client2src--웹-클라이언트) 참조). 🆕 🪦 **관문 3종은 이 파일을 떠났다 — `logShapedPushDecision` · `PUSH_SYSTEM_COLUMNS` · `getUnprotectedPushColumns`는 [`push_columns.js`](#-push_columnsjs-77줄-신설--푸시-컬럼-계약-데이터-보호-관문-4)에 있다**. 종전 지도가 `5801`·`5760`·`5782`에 **살아 있는 앵커로** 등재하던 세 이름이고, 지금 이 파일에 **선언 0건**이다(`5953`에 이전 사실을 적은 주석 1건). 저장 가능성 술어 3종 `eachSavableCell(fn)`/`classifyUnsavableCells()`/**`pushBlockingCount(u)`** — 🔴 **소비자는 `pushMapData`의 관문 하나다.**
- 렌더: **`getGridCellObject`** · `getGridCellFromMouseEvent` · `scheduleRenderGridCanvas` · `updateSideIndicator` · `fitGridToWorkspace` · `renderGridCanvas` · `handleCellClick` · `updateCellStyles` · `updateNotchPosition`. 테마·색: `rebuildThemeColorCache`/`getThemeColors`/`UNLISTED_VALUE_FILL`/`cellFillColor`/`parseCssColor`/`toExcelHex`.
  - 🔴 **`getGridCellObject`는 `getCanvasCellFromDb`를 부르지 않는다 — 식을 인라인한다**(`isOriginCell` 판정). 사유: **이 함수를 슬라이스해 실행하는 하니스가 둘**(`company_roundtrip`·`copy_header_count`)이고 모듈 전역 의존이 하나 늘 때마다 그 둘이 `ReferenceError`로 죽는다. 상자도 같은 `getWaferBoundingBox` 하나이므로 **새 유도가 아니라 같은 식의 특수값**이고 두 갈래로 갈릴 수 없다.
  - `renderGridCanvas` 쪽은 **호출을 쓴다**(`isOriginCell`, 사용) — 이 함수는 슬라이스 대상이 아니기 때문이다. 🆕 **그리고 이 함수가 좌석 기록의 원천이다**: `cellsSeatedUnder = seatingSnapshot(null) || cellsSeatedUnder` — 🔴 **`null`은 「화면을 읽어라」라는 의도된 답이지 빠뜨린 인자가 아니다**.
- 프리셋: **`applyPresetObject(preset)`** — 🔴 **호출자 전부의 관문이고 이번에도 5곳 그대로다**(2026-08-05 재계수): **3044 · 3073 · 5723 · 8359 · 8941**. `declaredRot`/`declaredSide`가 화면과 다르면 **info 토스트 1회**로 "규격만 적용했습니다"라고 말하고 **일치하면 침묵**한다. · `applyRoutedPreset(table, mapKey)` · `fetchAndRenderPresets`/`renderPresetDropdown`/`loadSelectedPreset`/`saveCustomPreset`/`deleteCustomPreset` · `applyPhysicalGeometry` · `updateOrientationUI` · `serverPresets`.
- 편집 도구: `clearGrid` · `fillGrid` · `getEdgeClassification` · `getVisualGridDimensions` · `selectEdgeCells` · `autoPaintE1E2` · **`fillSelectedCells`/`clearSelectedCells`** · `writeClipboardRich` · `copyGridToExcel`.
- **[F1ⓑ] COPY HEADER MODE**: `COPY_HEADER_KEY` · `colHeaderWord` · **`auxHeadWords()`** · `copyHeaderEnabled` · `mapKeyGroupLabel` · `copyHeaderGroups` · 픽셀 상수 `HDR_COL_PX`/`HDR_PAD_PX`/`HDR_CHAR_PX`/`HDR_MIN_SPAN`/`HDR_MAX_SPAN` · **`HDR_GAP_COLS=1`** · `headerSpanFor` · `distributeSpans` · **`auxColumnSpans`** · `copyHeaderAuxRows` · **`copyTitleText()`**.
- **[MEDIUM-3] 노치 지문 술어 2종**: `computeNotchCell(rotation, side)` — bbox를 `circleOnly: true`로 묻는다, **이 옵션의 유일한 소비자**) · **`notchMarkCell(rotation, side)`**.
- **[F1ⓑ] 회사 본딩맵 시트 왕복 붙여넣기**: `pasteBlank`/`pasteAt` · **`auxHeaderInLine(line)`** · **`readCompanyMapBlock(text)`** · **`checkPasteAgainstFrame(parsed, frame)`** · `applyPastedGridRows` · `pastedCellCount` · `applyPastedAuxRows` · **`onMapGridPaste(e)`**. ⚠️ **이것은 `transfer_plan.js`의 패널 붙여넣기와 다른 경로다** — 이쪽은 `e.defaultPrevented`를 먼저 보고 **패널이 이미 처리했으면 양보한다**. 그리고 회사 시트 쪽은 **VALUE로 주소를 매기고**(개명 없음) 패널 쪽은 **위치 기반**이다.
- **메타 입력칸의 값 제안(datalist) 블록** — `KEY_SUGGEST_DEBOUNCE_MS=120`/`COLUMN_VALUE_LIST_LIMIT=50` · `markSuggestState` · `listFillSeq`/`claimListFill`/`fillDatalist` · `mapKeyListCache`/`populateMapKeyDatalist` · `populateOverlayKeyList` · 캐시 3종 `columnValueComplete`/`columnValueRefused`/`columnValueTruncated` · `colValueKey`/`dropColumnValueCache`/`canReuseComplete`/`populateColumnValueDatalist` · `onMetaInputSuggest`, 배선). 하니스: `client2/tests/map_key_datalist_harness.mjs`. ⚠️ **그리드 셀의 값 제안(`value_suggest.js`)과 별개 구현이다** — 이쪽은 네이티브 `<datalist>`이고 저쪽은 AG-Grid 커스텀 에디터다.
- 프레임·정체성 보조: `loadedIdentity`/`framePushed`/`frameTouched` · `applyGridMetaObject` · `findPresetByKind` · `applyCellsToGrid` · `collectPlanCells` · `currentIdentityMismatch`/`setLoadedIdentity` · `frameTitle`/`currentFrameTitle`/`renderBreadcrumb` · `switchTableQuiet`.
- 진입·테이블: `debounce` · `el` · `initDOMElements` · `initPlanSidebarResizer` · `initMouseDragEvents` · `loadTablesList` · `switchTable` · `renderMetadataInputs` · `getBaseColumnName` · `fillColumnDropdowns`. 공수 계기: `ROUTE_MAIN`/`ROUTE_MATERIAL`/`effortRoute()`.

### 🆕 `push_columns.js` (**77줄**, 신설) — 푸시 컬럼 계약 (데이터 보호 관문 4)

> 🟢 **심볼 실측 완료** — 이 절의 심볼은 **`5609ff0`의 커밋된 blob에 존재함이 확인됐고, 그 뒤 HEAD가 움직인 다음 재대조에서도 동일했다**(워킹트리 아님). 🔴 **라인 번호는 싣지 않는다** — 위치는 `git grep -n "<심볼>" -- <경로>`로 확정하라. 숫자가 남아 있는 곳은 **파일 줄 수**이거나, 이름이 없는 덩어리를 가리키며 측정 sha가 함께 적힌 자리뿐이다.

**`map_editor.js`에서 뽑혀 나온 세 심볼.** 종전 지도는 이 셋을 `map_editor.js`의 **5760·5782·5801**에 등재하고 있었고 **그 앵커는 이제 아무것도 가리키지 않는다.**

| export | 시그니처 |
|---|---|
| `PUSH_SYSTEM_COLUMNS` | `const` 배열 — 페이로드가 **절대** 실을 수 없거나 서버가 스스로 관리하는 컬럼 |
| `getUnprotectedPushColumns` | **`getUnprotectedPushColumns(schema, xCol, yCol, valCol)`** |
| `logShapedPushDecision` | **`logShapedPushDecision(schema, xCol, yCol, valCol)`** |

- 🔴 **의도적으로 leaf다 — `import`가 한 줄도 없다.** `push_gate_harness`·`virtual_column_render_harness`가 이 모듈의 **텍스트를 `data:` URL로** 불러 변이체를 만드는데, 상대 경로 import는 그 안에서 해석되지 않는다. **여기에 import를 하나 넣으면 모든 변이체가 throw가 되고, throw는 kill로 채점된다** — 아무것도 실행되지 않은 채 완벽한 변이 보고서가 나온다.
- 추출 사유: 이 셋은 `map_editor.js`에서 **모듈 가변 의존이 0이고 `el`을 읽지 않는** 유일한 그룹으로 측정됐다. 그래서 슬라이스가 아니라 **진짜 모듈 객체를 import**해서 채점할 수 있다(`push_gate`·`virtual_column_render`·`map_key_datalist` 셋이 그렇게 바뀌었다).
- 소비자: `map_editor.js`가 import한다(`git grep -n "push_columns" -- client2/src`).

### 🆕 `enrichment_queue.js` (**94줄**, 신설) — 「어느 행이 아직 일이 남았나」의 **유일한 철자**

> 🟢 **심볼 실측 완료** — 이 절의 심볼은 **`5609ff0`의 커밋된 blob에 존재함이 확인됐고, 그 뒤 HEAD가 움직인 다음 재대조에서도 동일했다**(워킹트리 아님). 🔴 **라인 번호는 싣지 않는다** — 위치는 `git grep -n "<심볼>" -- <경로>`로 확정하라. 숫자가 남아 있는 곳은 **파일 줄 수**이거나, 이름이 없는 덩어리를 가리키며 측정 sha가 함께 적힌 자리뿐이다.

세 호출부가 각각 필터 dict를 재구성하던 것을 **이름으로 묻는 질문** 하나로 바꾼 모듈([기억: 질문은 이름으로 내보낸다](#7-client2src--웹-클라이언트)).

- 스코프 상수: **`QUEUE_SCOPE_QUEUE`**(`'queue'` — 타깃 중 **아무거나** 비어 있음) · **`QUEUE_SCOPE_KEYED`**(`'keyed'` — queue **그리고** 결정 키 전부 존재) · **`QUEUE_SCOPE_BLANK_KEY`**(`'blank_key'` — queue **그리고** 결정 키 최소 하나 공백) · **`QUEUE_SCOPE_RESOLVED`**(`'resolved'` — 타깃 전부 채워짐 **그리고** 키 전부 존재).
- `hasQueuePredicate(rule)` · ⚠️ **`queueQuery(rule, scope = QUEUE_SCOPE_QUEUE)` — 기본 인자가 있어 1인자로도 2인자로도 호출된다.**
- import 없음 (leaf).

### 🆕🆕 `enrichment_reference_view.js` (**118줄**, `1e29078` 신설) — 인덱스 사이드바의 **참조뷰 탭**

> ⚠️ **이 절은 측정 도중에 상태가 바뀌었고, 그 사실을 남긴다.** 측정 시작 시점(`7097a67`)에 이 파일은 **untracked**였고 그것을 import하는 `api.js`·`grid.js`·`main.js`는 modified였다 — **그 상태로 커밋됐으면 세 모듈이 없는 파일을 import해 빌드가 죽는다.** 🟢 **그렇게 되지 않았다**: `1e29078`이 **파일과 세 import를 한 커밋에** 넣었다. 아래 서술은 **커밋된 blob 실측**이고(워킹트리와 바이트 동일), 줄 수·export 다섯은 그대로다.

인덱스 페이지 사이드바의 **네 번째 탭(참조뷰)** — 선택된 행의 `decision_key`로 `GET /enrichment/rules/{name}/references/{index}`를 물어 표로 그린다.

- export: `refreshReferenceForSelection()` · `syncReferenceViewRule()` · `hideReferenceView()` · `installReferenceKeyboardIsolation()` · `showReferenceView()`. 소비자 — `api.js`(rule sync) · `grid.js`(선택 변경) · `main.js`(탭 배선 + 키보드 격리).
- 모듈 상태 넷: `rulesPromise`(규칙 목록 1회 fetch) · `activeRule` · `requestSequence`(**늦게 도착한 응답이 새 선택을 덮지 않게 하는 시퀀스 관문**) · `keyboardIsolationInstalled`.
- 🔴 **탭이 보일 조건은 선언이다** — `rule.derived_table === state.currentTable` **그리고** `rule.reference_views`가 비지 않음. 아니면 탭 자체를 `display:none`으로 숨긴다.
- 🔴 **행 변경이 이 사이드바를 갱신하는 것은 조작자가 실제로 그것을 보고 있을 때뿐이다**(`state.activeHistoryTab === 'reference'`). 평소 이력 내비게이션은 조용하고 무변경이다.
- ⚠️ **`installReferenceKeyboardIsolation`은 이벤트를 *막지 않고* 전파만 멈춘다** — 브라우저 텍스트 선택과 Ctrl/Cmd+C의 기본 동작을 그대로 두는 것이 의도다(이 패널은 **읽기·복사 표면**이지 두 번째 그리드 편집기가 아니다).

---

## 7-A. 🆕 Map Editor 2 — `map_editor2.html` + `client2/src/map2/` (2026-08-05~06 신설)

> 🆕🆕 **[2026-08-11 부분 재측정 · `7097a67`]** 이 패스가 연 것은 **`candidates.js` · `main.js` · `view_model.js` · `decode.js` 넷뿐**이다(그 넷이 `8d89b98..7097a67`에서 바뀐 map2 모듈 전부다 — `git diff --name-status` 실측). 🔴 **그중 export 집합이 바뀐 것은 `candidates.js` 하나이고, 나머지 셋은 export 무변동에 줄 수만 움직였다.** **나머지 14개 모듈의 줄 수와 export는 아래 `e943e46` 측정 그대로이고 이 패스가 열지 않았다.**
>
> 🟢 **심볼 실측(2026-08-07 재측정)** — 아래 심볼과 줄 수는 **`e943e46`의 커밋된 blob** 실측이다(워킹트리 아님). 🔴 **라인 번호는 싣지 않는다** — 위치는 `git grep -n "<심볼>" -- client2/src/map2/<모듈>.js`로 확정하라.
>
> 🔴 **직전 등재(`87a944e`)의 줄 수는 전부 낡았고, 모듈 하나가 아예 빠져 있었다** — `index_ramp.js`. 절 제목의 「17모듈」이 그래서 틀렸다(**18** — 🆕🆕 `7097a67`에서 `git ls-tree`로 재확인, 추가·삭제 0). 그리고 이 절의 산문에 남아 있던 라인 앵커(`250`·`1377`·`1413`·`1061`·`1350`·`1514`·`1525-1526`·`1561-1574`·`572`·`586`·`750` 등)는 **`e943e46`에서 전부 밀렸으므로 심볼·함수 스코프로 교체했다.** 위 🔒 판정과 같은 이유다.

> 🔴 **구 에디터를 대체하지 않는다 — 옆에 선다.** `map_editor.html`/`src/map_editor.js`는 **그대로 돌아간다**(11,031줄, 여전히 vite 엔트리이자 살아 있는 페이지). `vite.config.js`의 주석이 그 의도를 못박는다: *새 화면이 실제로 프레임을 확정할 수 있게 될 때까지 구 엔트리는 변경 없이 계속 배포된다.*
>
> **vite 엔트리 — 전건 열거**(개수를 적지 않는다): `main`(index.html) · `admin` · `map_editor` · **`map_editor2`** · `enrichment` · `graph` · `trace`.
>
> ⚠️ **왜 아직 병렬인가**: 이 화면이 모는 것은 **정렬·확정 루프**다. 저작·엑셀 절반은 모듈로 존재하지만(`authoring.js`·`brush.js`·`excel_io.js`), **`artifact_gateway.js`는 선언된 미구현 이음매**라 함수들이 `NOT_IMPLEMENTED`를 던진다 — 구 에디터에서 맵이 바깥에서 들어오는 **유일한 경로**가 아직 안 열려 있다.
>
> **측정 기준**: 아래 전부 **`e943e46`의 커밋된 blob** 실측이다.

### `map_editor2.js` (🆕🆕🆕🆕 **470줄** @`3d43a6c`, 412에서 **+58**) — 페이지 엔트리

**export 0건 — 부수효과 엔트리 모듈.** `map_editor2.html`(**866줄** — ⚠️ 실측 875, 이 구간이 만든 드리프트가 아니라 미해결로 남겨둔다)이 이것 하나만 로드한다.

- 모듈 내부(비-export): `createResilientClient()` · `isOutage(err)` · `start()` · `adoptRule(app, api, declaration)` · `discover(api)` · `buildCatalog(api, declaration)`. 🔴 **[`3d43a6c`] `keyFrom(rule, decision)`은 삭제됐다**(실측: HEAD blob grep 0건) — 아리티 2에서만 규칙의 `decision_key`를 존중하고 그 외엔 하드코딩 `{dt_eqp, product}`를 냈던 함수. 결정키를 **한 컬럼**만 선언한 규칙은 이 함수 때문에 확정이 애초에 불가능했다(서버가 `빠진 결정키: <컬럼>`으로 답했지만, 그 사유는 페이로드에 대해서만 참이고 원인에 대해서는 오도였다). 대체는 `map2/view_model.js`의 순수 조립기 `decisionKeyOf`·`declaredKeyColumns`(import) — `adoptRule`이 `decisionKeyColumns: declaredKeyColumns(declaration)`을 컨텍스트에 실어 `toDecisionKey: (d) => decisionKeyOf(declaration, d).key`로 위임한다. `start()`의 로더도 `unit = decisionKeyOf(...)`을 먼저 묻고 `unit.key`가 없으면 **요청을 아예 안 보내고** 콘솔에 거절을 남긴다(빈 컬럼을 보내면 서버가 "under-filled"로 답하는데, 그건 클라가 만든 서버의 불평이다).
- 🔴 **실패를 종류별로 가른다** — 라우트/모양 실패는 **다시 던져 화면에 이름으로** 말하고, **네트워크 장애만** `/map2_dev_reference.json`으로 물러선다(그 폴백은 **화면에 자기를 표시한다**).
- 🔴 **규칙 이름도 테이블 이름도 하드코딩이 없다**: 규칙은 `GET /enrichment/rules`를 `alignment: true`로 엄격 필터, 맵 테이블은 **선언된 `map_key_columns`로** 발견한다.
- 🆕 🔴 **[`e943e46`] 워크리스트 로더가 abort 신호를 통과시킨다** — `app.setWorklistLoader((query, signal) => api.loadWorklist(query, signal))`. **두 번째 인자를 흘리는 로더는 셸에게 아무것도 취소하지 않는 컨트롤러를 쥐여 준다**(§`map2/main.js`의 `fetchWorklist`).
- 🆕🆕🆕🆕 **[`3d43a6c`] 채택 실패가 침묵에서 이름으로** — `discover(api)`가 서버 미응답(`WORDS_RULES_UNREACHABLE = '규칙 조회 실패'`, 종전 이름 `WORDS_NO_RULE`에서 **개명**·별도 사유로 분리)과 `alignment` 선언 0/여러건(`selectAlignmentRules(rules).reason`)을 이제 구분해서 화면에 보낸다. 종전엔 후자가 `declaration = null`을 조용히 돌려줘 `map_editor2.js`가 `refreshWorklist()` 전에 리턴했다 — **요청이 실패한 게 아니라 아예 시작되지 않았다**, 그런데 화면은 "로딩 안 끝남"과 구분이 안 됐다.

### `client2/src/map2/` — 레이어 모듈

⚠️ **arrow-function export가 0건이고 여러 줄 시그니처가 0건이다** — 아래 시그니처는 전부 소스 한 줄과 글자 그대로 같다. `export class`는 `RouteNotServedError`·`RatioInPayloadError` 둘뿐이고(@`e943e46` 재확인), 기본 인자를 가진 export 시그니처는 **`createMapSession(init = {})`·`rampStops(rankMax, band, count = 96)`** 둘뿐이다. 🔴 **구 지도는 후자를 `createMapSession`·`queueQuery`라 적었는데 `queueQuery`는 `map2/`에 없다** — `client2/src/enrichment_queue.js`의 export다(실측: map2 안 히트 0).

| 모듈 | 줄 | 무엇인가 | 주요 export |
|---|---|---|---|
| **`api.js`** | 🆕🆕🆕🆕 **574**<br>(572 · 구 505) | 전송 계층. **서버와 말하는 유일한 모듈**이고 GET과 쓰기를 타입 수준에서 가르는 유일한 자리. **export 무변동** — `3d43a6c`는 `loadReferenceView`의 `params` 누락 에러 메시지 문구만 고쳤다(그 문구가 마지막으로 남은 decision-key 컬럼명 예시였다) | `ROUTES`, `Object.freeze`) · `class RouteNotServedError` · **`createApiClient(opts)`** · `REFERENCE_CATALOG_SERVED`/`REFERENCE_CATALOG_UNAVAILABLE` · `normaliseReferenceCatalog(body)` |
| **`declaration.js`** | **870** | 레이어 ③ — **「이 맵이 자기 좌표계를 무엇이라 *말하는가*」를 값으로**, 축마다 출처 토큰을 달아서 | 아래 별도 표 |
| **`seating.js`** | **468**<br>(구 337) | 레이어 ④ — 선언 + 증거 → 모든 셀의 공통 공간 좌석. **등록만 하고 뷰포트가 스코프에 없어** `continue` 하나가 셀을 흘릴 수 없다 | `seatOf(frame, c, r)` · `seatKey(x, y)` · `physOf(frame)` · `visualExtent(frame)` · `isCellInsideWafer(c, r, cols, rows, phys)` · `boundingBoxOf(frame)` · `localIndex(frame, box, x, y)` · `computeSeating(cells, frame)` · 🆕 **`placeCells(...)`** · 🆕 **`FLOOR_PLACEMENT`** · `unionBounds(a, b)` · `compareSeatings(floorSeating, sourceSeating)` |
| **`verdict.js`** | **403**<br>(구 335) | 레이어 ⑦ — 점수 in, 결정 out. 🔴 **마진이 작으면 순위를 매기기를 거부한다** | `REF_NONE`/`REF_OCCUPANCY`/`REF_VALUES` · `STATE_SCORED`/`STATE_NO_WINNER` · `VERDICT` · 🆕 **`DECIDED_BY_DIRECTION`** · `REASON` · `DEGRADATION` · `degradationFor(verdict)` · **`decideVerdict(scorings, thresholds, context)`** · `decideForSources(scoringResult, thresholds, context)` |
| **`verdict_bridge.js`** | **32** | 레이어 ⑤↔⑦의 한 줄 이음매 — **판정 구현을 이름으로 부르는 유일한 파일** | `export { decideVerdict, VERDICT, REASON } from './verdict.js'` |
| **`verdict_placeholder.js`** | **108** | 🪦 **선언된 죽은 코드.** `alignment_verdict_harness.mjs`가 `verdict.js`를 **그것이 대체한 물건과 대조 채점**하기 위해서만 디스크에 남아 있고, **결함(`finiteOrNull` 대신 맨 `Number(v)`)을 의도적으로 보존한다.** `src/` 안에서 이것을 import하는 곳은 0건 | `VERDICT` · `REASON` · `decideVerdict(scorings, thresholds, context)` |
| **`decode.js`** | 🆕🆕 **919**<br>(`34d2518` 913 · 구 589) | 세관 — 참조 뷰 페이로드가 값 레이어와 뷰모델 읽기가 되는 자리. 🔴 **백분율은 통과하지 못한다**. 🆕🆕 **export 집합 무변동**(`34d2518` 전건 대조) | `ASSUMPTION_APPLIED`/`_AVAILABLE`/`_UNAVAILABLE` · `KIND_DECLARED`/`_INFERRED`/`_ABSENT` · `METRIC_OCCUPANCY`/`_VALUES`/`_VALUES_WEIGHTED`/`_INDEX` · `CAND_SCORED`/`_NOT_CONSIDERED`/`_NOT_SCORABLE` · `scoringKeysFor(metric)` · `class RatioInPayloadError` · `assertNoRatioInPayload(payload)` · `decodeReferenceView(payload)` · `verdictContext(decoded)` · `isAssumedGeometry(source)`/`isDeclaredGeometry(source)`/`isConfirmedGeometry(source)` · 🆕 **`decodeIndexWalk(payload)`** + 상태 어휘 **`INDEX_WALK_READY`/`_ABSENT`/`_TRUNCATED`/`_POOLED`/`_INCONSISTENT`** — 순번 훑기 축의 클라 절반([§5-F](#5-f--정렬-채점-계열-index-scoring-family--servermap_alignmentpy-2026-08-07-등재)) |
| **`session.js`** | **485**<br>(구 466) | 현재 상태를 **만들어 넘기는 레코드**로 — 모듈 전역이 아니다. 🔴 **모든 `with*`가 새 frozen 사본을 돌려준다** | `PHASE` · `EMPTY_COLUMNS`/`EMPTY_QUESTION`/`EMPTY_CATALOG`/`EMPTY_WORKLIST` · `BINDING_DECLARED`/`_DERIVED`/`_FALLBACK_GUESS`/`_NONE` · **`createMapSession(init = {})`** · `withDecision`/`withPayload`/`withError`/`withSelectedCandidate`/`withCatalog`/`withQuestion`/`withWorklistQuery`/`withWorklist`/`withWorklistError`/`withConfirmed`/🆕 **`withConfirmFailed`**/`withFocusedSource`/`withConfig` · `columnKey`/`resolveQuestion`/`columnsOf`/`isAskable`/`isUnset`/`isExploringOnly` |
| **`view_model.js`** | 🆕🆕🆕🆕 **1,395**<br>(1,224 · `34d2518` 1,226 · `e943e46` 1,197 · 구 1,073) | 세션+페이로드+판정 → **화면이 보여 줄 문자열과 플래그 정확히 그것**. 순수, DOM 무지. 🆕🆕🆕🆕 **[`3d43a6c`] export 5종 신설**(2026-08-11 3차 후속 — 이번 라운드 전까지는 무변동이었다) | `VIEW_STATE` · `UNKNOWN`(`'미상'`) · `WORDS`/`ATTRIBUTION`/`EVIDENCE`/`REFERENCE_KIND_WORD` · `referenceOptionLabel(item)` · **`buildViewModel(input)`** · `agreementText(agree, discriminating)` · `marginText(marginDies)` · `HEADLINE`/`CAUSE` · `selectAlignmentRules(rules)`(🆕🆕🆕🆕 이제 `{rules, declaration, proposed, capable, declared, state, reason}` — `state`/`reason` 신설, 아래) · `CROSS_SOURCE_ROW_ID` · `countCoordinatePairs(columnNames)` · `assertNoRatio(vm)` · 🆕🆕🆕🆕 **`RULE_ADOPTION`**(`{ADOPTED, NONE_CAPABLE, SEVERAL_CAPABLE}`) · 🆕🆕🆕🆕 **`DECISION_KEY`**(`{STATED, INCOMPLETE, UNDECLARED}`) · 🆕🆕🆕🆕 **`decisionKeyOf(declaration, decision) -> {state, key, columns, missing}`**(순수 조립기 — 규칙의 `decision_key`를 아리티 그대로 채운다. `key`는 **선언된 컬럼 전부가 채워졌을 때만** non-null — 빈 컬럼을 보내는 대신 거절한다. 값 우선순위: `decision.__key[col]`(서버가 워크리스트 행에 실어 준 것, 컬럼별로 읽어 상속 규칙이 바뀌어도 stale 키가 안 따라온다) → `decision[col]` → **레거시 위치 브리지**(`decision.eqp`/`decision.product`가 인덱스 0/1 — 어느 컬럼명도 아니고 이 프로그램이 만든 슬롯) → 없으면 `missing`에 등재) · 🆕🆕🆕🆕 **`declaredKeyColumns(declaration)`**(`decision_key`를 정리 — 비문자열·공백·중복 제거) · 🆕🆕🆕🆕 **`decisionKeyRefusal(result)`**(거절 문구 한 곳) |
| 🆕🆕 **`candidates.js`** | 🆕🆕 **103**<br>(구 80) | 후보 집합 — 여덟 방위를 **한 번만** 이름 짓고, 컨트롤과 채점자가 공유하는 **2열(시작 모서리) × 4행(회전)** 배치까지. 🔴 **이번 라운드에 export 집합이 바뀐 유일한 map2 모듈이다** | `ROTATIONS`(`[0,90,180,270]`) · 🆕🆕 **`STARTS`**(`['top_left','top_right']`) · 🆕🆕 **`START_TOKEN`**(`{top_left:'tl', top_right:'tr'}`) · 🆕🆕 **`CANDIDATE_SIDE`**(`'front'`) · 🆕🆕 `candidateId(rotation, start)` · `parseCandidateId(id)` · `candidateList()` · `candidateGrid()` · 🆕🆕 **`START_HEADERS`**(`{top_left:'좌상단 시작', top_right:'우상단 시작'}`) · `INVERSION_FOOTNOTE` · `BADGE_WINNER`(`'추천'`)/`BADGE_STORED`(`'현재 선언'`)<br>🪦 **`SIDES` · `SIDE_HEADERS`는 삭제됐다** → [§0 ⑱](#0-묘비-목록--소스에-존재하지-않는-이름). ⚠️ **`declaration.js`의 `SIDES`는 남아 있고 그것은 옳다** — 저장된 **메타**의 어휘이지 후보 축이 아니다 |
| **`main.js`** | 🆕🆕🆕🆕 **2,489**<br>(2,454 · `34d2518` 2,453 · `e943e46` 2,437 · 구 1,975) | **합성 루트 — DOM이 존재한다는 것을 아는 유일한 모듈**. **export 집합 무변동**(`3d43a6c`는 `import`만 늘렸다: `decisionKeyRefusal`·`DECISION_KEY`) | `ELEMENT_IDS` · `normaliseWorklist(res)` · **`bootstrap(deps)`** · `adaptPayload(raw)` · `framesFor(payload, candidateId)` · **`seatingFor(payload, candidateId, cells)`** · **`floorSeating(payload)`** · `paintCandidateThumbs(surfaceFor, payload, source, viewport, palette)` · 재수출 `{ VIEW_STATE, createApiClient, spellFrame }`.<br>⚠️ **`spellFrame`·`placementFor`·`pickSource`·`gridSpan`은 모듈 private이다 — `export`가 아니다**(재수출 목록에 `spellFrame`이 이름으로 들어갈 뿐).<br>🆕🆕 🔴 **`spellFrame`은 이제 시작 모서리를 읽는다** — `rot270_tr` → **`270° · 우상단 시작`**(술어는 `axes.start === 'top_right'`, **`side === 'back'`이 아니다**). 아래 별도 블록.<br>🆕🆕🆕🆕 **[`3d43a6c`] `bootstrap`의 `context`가 `decisionKeyColumns`를 얻었다**(기본값 `null` — "아무 페이지 엔트리도 선언한 적 없다"이지 `[]`("이 규칙은 키 컬럼이 없다고 선언했다")가 아니다, 둘을 접으면 배선 안 된 셸이 고장난 규칙과 구분 안 된다). 확정 버튼 핸들러가 `confirmInFlight` 가드보다 **먼저** `context.toDecisionKey(session.decision)`로 결정키를 조립해 미충족 컬럼이 있으면 **요청을 보내지 않고** `withConfirmFailed(session, decisionKeyRefusal(...))`로 기존 `#me2-confirm-note` 슬롯에 사유를 남긴다(새 패널·새 컨트롤 없음) |
| **`painter.js`** | **176** | 레이어 ⑩ — 좌석을 받아 **그리기만** 한다. 만드는 것이 없고 **경계 검사가 없어서 셀을 잃을 수 없다** | `createCanvasSurface(ctx)` · `createRecordingSurface()` · `layoutFor(bounds, viewport)` · `pxPerDie(layout)` · `paintSeating(surface, seating, layout, color, mode)` · `paintComparison(surface, parts, viewport, palette)` · `paintSkeleton(surface, viewport, palette)` |
| **`legend.js`** | **161** | 값 → 색·라벨. 🔴 **`colorOf`의 `null`은 「아무도 색을 선언하지 않았다」는 사실이지 빠뜨린 반환이 아니다** | `NO_COLOUR_DECLARED`(`'색 선언 없음'`)/`NO_LABEL_DECLARED`(`'설명 없음'`) · `isValue`/`valueKey`/`normalizeLegend`/`resolveLegend`/`rowOf`/`colorOf`/`labelOf`/`legendEntries`/`brushableValues`/`isDeclaredValue` |
| 🆕 **`index_ramp.js`** | **259** | **[미등재였다]** 순번 → 색. OKLCH 램프의 유일 구현이고 **`tokens.css`의 명도 대역 두 값과 짝을 이룬다**. leaf(= map2 내부 import 0건), 소비자는 `main.js` 하나 | `INDEX_RAMP_PERIOD`(61) · `INDEX_RAMP_CHROMA_CAP`(0.30)/`INDEX_RAMP_CHROMA_SLOPE`(0.0015)/`INDEX_RAMP_CHROMA` · `INDEX_RAMP_BAND_FALLBACK`(`{l0:0.46, l1:0.58}`) · `indexColor(rank, rankMax, band)` · `rampStops(rankMax, band, count = 96)` · `rampGradientCss(rankMax, band, count)` · `chromaAt(hueDeg, band)` |
| **`brush.js`** | **316** | 레이어 ④ 좌석 위의 셀 저작. 🔴 **역함수를 다시 유도하지 않고 기존 변환을 정방향으로 돌린다** | `BRUSH_REFUSAL` · `MAX_AUTHORABLE_CELLS` · `authorableSeats(frame)` · `seatAt(authorable, seatX, seatY)` · `cellKey(x, y)` · `createCellTable(cells)` · `tableCells(table)` · `brushStroke(table, authorable, coords, value)` · `eraseStroke(table, coords)` · `expressible(authorable, x, y)` |
| **`authoring.js`** | **394** | 유효 다이 맵의 **저장 계약** — 순수. 요청을 만들고 관문을 세우되 **보내지는 않는다** | `FLOOR_TABLE`(`'valid_die_ref'`)/`META_TABLE`(`'wafer_map_metadata'`) · `WRITE_ROUTES` · `SAVE_REFUSAL` · `GEOMETRY_KEYS` · `geometryDelta(storedMeta, nextMeta)` · `decomposeFloorKey(mapKey, keyColumns, columnTypes)` · `checkSaveGate(input)` · `buildSaveRequest(gate, input)` · `writeIntent(gate, opts)` |
| **`excel_io.js`** | **758** | 문지기 — 운영자의 엑셀 서식을 말하는 **유일한 모듈**. 🔴 **구 에디터에서 베낀 것이 아니라 운영 인제션 포맷에서 다시 썼다** | `SECTION_WIDE_RATIO`(0.7) · `MIN_AXIS_TICKS` · `META_KEY_JOIN`/`META_CHAIN_LEN` · `INGESTION_RENAME`(`{BDIE_LOT:'base', VALUE:'leg'}`) · `UNKNOWN_DISPLAY`(`'미상'`) · `REJECTION_CODES`(`['not_declared','mapping_unavailable']`) · `FORM_SURFACES`(`['rich','plain']`) · `detectFormSurface(source)` · `readMapForm(source, opts)` · `writeMapForm(declaration, cells, opts)` · `ingestionRecords(declaration, cells)` |
| **`artifact_gateway.js`** | **203** | 🪦 **선언된 미구현 이음매** — 엑셀 서식 in/out의 이름 붙은 자리. **함수들이 일부러 `NOT_IMPLEMENTED`를 던진다** | `NOT_IMPLEMENTED` · `SURFACES`(= `FORM_SURFACES`) · `REJECTED`/`REJECTED_WORDS` · `readArtifact(text, opts)` · `unmappedRejectionCodes()` · `writeArtifact(cells, declaration, opts)` · `isImplemented()` · `rejectionSummary(rejected)` |

**모듈 의존**: leaf(= map2 내부 import 0건)는 **`api.js` · `candidates.js` · `declaration.js` · 🆕 **`index_ramp.js`** · `legend.js` · `seating.js` · `session.js` · `verdict.js` · `verdict_placeholder.js`**. 나머지 — `brush`→`seating` · `painter`→`seating` · `verdict_bridge`→`verdict` · `decode`→`verdict`·`declaration` · `view_model`→`candidates`·`verdict_bridge`·`session` · `excel_io`→`declaration` · `artifact_gateway`→`excel_io` · `authoring`→`brush`·`legend` · `main`→`session`·`seating`·`painter`·`view_model`·`verdict_bridge`·`candidates`·`api`·`decode`·`declaration`·`artifact_gateway`·🆕 `index_ramp`.

#### `declaration.js` — 출처 토큰의 정본 목록

🔴 **저장소에서 출처 토큰이 *얼려진 목록*으로 존재하는 곳은 여기 하나다.** 서버(`map_overlay.py`)는 같은 어휘를 **개별 상수로** 선언하고 목록을 만들지 않는다 — 그래서 「N번째 토큰」식 서술은 서버 쪽에서 검증할 대상이 없다.

```js
// declaration.js:152–153 @`e943e46` (재측정: 밀리지 않았다)  — 전건 열거, 개수를 적지 않는다
export const DECLARATION_TOKENS = Object.freeze([
  DECLARED, AUTO_REGISTERED, ABSENT, UNPARSABLE, INDETERMINATE, ASSUMED, CONFIRMED]);
// declaration.js:168 @`e943e46`
export const COMPUTABLE_TOKENS = Object.freeze([DECLARED, ASSUMED, CONFIRMED]);
```

- 토큰 상수는 **144–150에 연속으로** 앉아 있다(@`e943e46` 재측정: 밀리지 않았다): `DECLARED` · `AUTO_REGISTERED` · `ABSENT` · `UNPARSABLE` · `INDETERMINATE` · `ASSUMED` · **`CONFIRMED`, `'confirmed'`)**.
- 메타 키: `AUTO_REGISTERED_KEY` · `PHYS_ASSUMED_KEY` · **`PHYS_CONFIRMED_KEY`** · **`FRAME_CONFIRMED_KEY`** · `FRAME_CHOSEN_KEY` · `FRAME_CHOSEN_FROM`(`['data','panel']`) · `PHYS_KEYS` · `FRAME_DEFAULTS` · `AXIS_META_KEY`/`AXIS_NAMES` · `VALUE_CAN_INDICATE_PROVENANCE`(`['rotation','side','invertY']`) · `START_AXES`(`['startX','startY']`) · `ORIENTATION_AXES`.
- 함수: `geometryDeclaration(meta)` · `visualDimensions(frame)` · `visualDimensionsLegacy(frame)` · `frameFromDeclaration(meta, opts)` · `noEvidenceValue(axisName, opts)` · `axesWithSource(frame, tokens)` · `frameDimBounds()` · `isFrameUsable(frame)` · `foldedAxes(frame)`.
- ⚠️ **`markerPresent(raw)`는 모듈 private이다 — `export`가 아니다.** 호출부는 파일 안 셋(**572**·**586**·**750** @`e943e46` — 재측정: 셋 다 밀리지 않았다. 정의는 **397**). 진리성만 읽으므로 빈 객체/배열/문자열은 무력하고(파이썬의 `bool({}) is False`와 맞춘 것), **`confirmation_uid` 적격성은 일부러 다시 검사하지 않는다 — 그것은 서버의 규칙이다.**

#### 🪦 `main.js`의 **확정 무장(arming) 상태는 삭제됐다**

> 🔴 **[2026-08-07 재측정] 이 블록의 라인 앵커는 전부 낡아 심볼·함수 스코프로 교체했다.** `e943e46`에서 파일이 1,975 → **2,437**줄이 됐고, 이 블록이 인용하던 `250`·`1053–1054`·`1061`·`1350`·`1377`·`1413`·`1514`·`1525–1526`·`1561–1574`가 그만큼 밀렸다. **아래는 감싸는 함수 이름으로 적는다 — 그것이 다음 라운드에도 살아남는 식별자다.**

**`main.js`에는 모듈 레벨 가변 상태가 0건이다**(`^let `/`^var ` 히트 **0**, `e943e46` 실측). `armed`/`arming`/`confirmArm`/`disarm` 식별자도 0건 — 남은 히트 **여섯 개는 전부 삭제를 설명하는 주석**이다. 확정은 이제 **한 동작**이다: 클릭 또는 Enter가 즉시 `api.confirmFrame({...})`로 쓴다. **취소 분기도 함께 사라졌다** — 취소할 것이 남아 있지 않다.

그 자리를 받은 것 — 전부 `bootstrap` 안의 함수 스코프다:

| 무엇 | 어디 (감싸는 함수) | 계약 |
|---|---|---|
| **`let confirmInFlight = false`** | `bootstrap` 본문 상단 선언부 | 🔴 **세션 필드가 *아닌 것*이 요점이다** — 세션 필드는 행이 바뀌어도 요청보다 오래 살아남아 버튼을 잠가 버린다. `true`로 세우고 다시 푸는 곳은 **`onConfirm`** 하나, 렌더가 읽는 곳은 **`renderConfirm`**(`btn.disabled = !vm.confirm.enabled \|\| confirmInFlight`) |
| **`takesEnter(target)`** | `bootstrap` 스코프 함수 | 🔴 **무장이 지고 있던 보호를 지금 지는 것이 이것이다 — LOAD-BEARING**(Enter 키 핸들러의 주석이 명시한다). 확정 버튼만이 유일한 예외 |
| `vm.confirm.enabled` / `vm.confirm.confirmed` | **`renderConfirm`** | `'확정됨'` 또는 `vm.confirm.inertHint \|\| 'Enter 확정'` |
| 🆕 **`let worklistInflight = null`** | `bootstrap` 본문 상단 선언부(`confirmInFlight` 바로 아래) | **[`e943e46` 신설]** 진행 중인 워크리스트 요청. **`confirmInFlight`와 같은 이유로 함수 스코프다 — 세션이 아니라 *요청 하나*에 대한 사실이다** |

⚠️ **`api.confirmFrame`은 레코드로 부른다 — 위치 인자가 아니다**(`onConfirm` 안 주석이 종전의 위치 호출을 결함으로 표시한다).

#### 🆕 🔴 [`e943e46`] **대상 테이블 select가 질문을 바꿔 놓고 워크리스트를 다시 묻지 않았다**

**증상은 낡은 목록이 아니라 한 화면에 두 테이블이었다.** `tableSelect`가 컬럼 피커를 새 테이블 스키마로 다시 채우고 `/view`도 다시 물었는데, **`fetchWorklist`의 호출자는 부트스트랩과 검색창 둘뿐**이었다. 실측(2026-08-06, 브라우저 한 세션): 워크리스트 요청 **셋 전부** `map_table=core_wafer_map`이고 `dt_log`는 **한 번도 없었다**. 두 모집단은 실제로 다르다(191/160/97/96/1 vs 40/40/20/20/6).

- 🔴 **서버 변경 0건** — 라우트는 **클라가 묻지 않은 질문**에 이미 옳은 답을 내고 있었다.
- 재발화 판정은 **`resolveQuestion` 정규화 이후**의 값끼리 한다(`bindSelect(el.tableSelect, …)` 안에서 `session.question.mapTable`의 전/후 비교). 그래서 **같은 테이블 재선택은 요청을 만들지 않는다.** 🔴 **컨트롤의 원시 값으로 비교하면 안 된다** — 카탈로그가 안 나르는 테이블을 `resolveQuestion`이 거절할 수 있다.
- 진행 중 요청은 **`AbortController`로 대체(supersede)** 된다: `fetchWorklist`가 `worklistInflight.abort()` 후 새 컨트롤러를 세우고 로더에 `signal`을 넘긴다 — `map_editor2.js`의 `setWorklistLoader((query, signal) => api.loadWorklist(query, signal))`가 그 인자를 **통과시켜야** 성립한다. 🔴 **`value_suggest.js`가 이미 쓰는 그 모양이고, 두 번째 기계장치를 만들지 않은 것이 요점이다.**
- ⚠️ **`AbortError`는 실패가 아니다** — `withWorklistError`로 가지 않고 `return`한다. 조작자가 **자기 질문을 스스로 대체**한 것이라, 여기서 장애를 그리면 **일어나지 않은 실패를 보고**하는 것이다.
- 🔴 **다른 세 set-up 컨트롤은 일부러 여기 없다** — x/y/value는 **한 단위를 어떻게 읽는가**를 바꾸고, 기준은 **무엇에 대고 채점하는가**를 바꾼다. 둘 다 **어느 단위가 존재하는가**를 바꾸지 못한다(`/api/maps/alignment/worklist`는 `reference` 파라미터를 **아예 받지 않는다**). 대칭은 바꿀 이유가 되지 못한다.
- **컨트롤 추가 0 / 제거 0.** 새로고침 버튼을 옆에 두는 것은 **첫 컨트롤이 안 먹는다는 자백**이다.
- 채점자: `client2/tests/map_editor2_shell_harness.mjs` 섹션 **R**(16 단언, 바닥 등록됨). 변이 측정 — 재발화를 빼면 **6 빨강**, abort를 빼면 **2 빨강**.
- 🔬 **같은 라운드에서 진단만 하고 안 고친 것**: `dt_log`의 스키마가 **자기 `core_x`/`core_y`를 갖고 있어** `resolveQuestion`이 선언된 바인딩을 채택하는 대신 **들고 있던 픽을 유지**하고, `/view`가 `dt_log`에 대고 `x_col=core_x`로 나간다. **무엇이 채점되는지가 바뀌므로 자기 판정이 필요하다.**

#### 🆕🆕 🔴 [`c4eaffa`→`c959368`→`db1ee42`, 2026-08-11 재측정] **후보의 두 번째 축은 `back`이 아니라 시작 모서리다 — 낱말이 아니라 축이 교체됐다**

🔴 **직전 등재(2026-08-08)는 「`back`은 물리 뒷면이 아니라 우상단 시작을 *뜻한다*」였다. 그 서술은 이제 두 번 틀렸다** — ① 후보 공간에 `back`이 없고(철자는 `rot*_tl`/`rot*_tr`, 면은 전부 `front`) ② **그 동등성 자체가 4분의 1 회전에서 거짓이었다**: 거울은 90°/270°에서 **행 축**을 뒤집으므로 `rot90_back` ≡ `rot270`@우상단이다. 그래서 개명이 아니라 **다시 채점되는 축**이어야 했다.

- **`candidates.js`가 그 사실의 정본이다** — `STARTS`·`START_TOKEN`·`CANDIDATE_SIDE`·`START_HEADERS`. `INVERSION_FOOTNOTE`가 조작자에게 **뒤집기는 후보가 아니라고 명시**하고, 진짜 물리 뒷면은 **한 클릭 옆의 맵 에디터**에서 선언한다고 가리킨다.
- 🆕🆕 **`view_model.js` — `buildCandidateCard`의 `startLabel`**: 술어가 **`a.candidate.start === 'top_right'`**다(구 `candidate.side === 'back'`). 🔴 **`storedLabel`을 대체하지 않는다 — 둘 다 렌더된다.** 화면은 DB가 쥔 것을 **숨겨선** 안 되지만 그 뜻을 말하지 말라는 규칙은 없다.
- 🆕🆕 **`main.js` — `spellFrame(candidateId)`**: 술어가 **`axes.start === 'top_right'`**이고 예시는 `rot270_tr` → `270° · 우상단 시작`. 저장된 철자는 그 옆에 mono로 남는다. 렌더 지점은 후보 카드의 `me2-cand-start` span.
- 🆕🆕 **`parseCandidateId`는 레거시 철자를 계속 읽되 *뜻을 지어내지 않는다*** — `_front`는 좌상단 걸음(`{side:'front', start:'top_left'}`), **`_back`은 `{side:'back', start:null}`**로 읽는다. 🔴 **`back`에 시작 모서리를 붙이지 않는 것이 이번 라운드의 수정 그 자체다** — 그것이 틀렸던 동등성이다.
- ⚠️ **확정은 여전히 `side`를 저장한다** — `map_alignment.confirmed_meta_for`가 `parse_frame`으로 읽고, 후보 철자 `tl`/`tr`은 **둘 다 `front`**로 풀린다(`dt_map_derivation._SIDE_OF_TOKEN`). 🔴 **`side=front`를 *거울 후보에* 내리려던 시도는 `51e4068`에서 되돌려졌다**(거울이 `grid_start_*`에 흡수됐다는 근거가 거짓 — 실측: start는 같은데 셀이 x로 4칸 밀린다). [§5 `map_alignment.py`](#-servermap_alignmentpy--프레임-정렬의-채점자)
- 🆕🆕 🔴 **하니스 넷이 이 교체로 빨개졌고 그것은 총괄 수용(2026-08-09) 상태다** — `check_harnesses.mjs`의 `KNOWN_RED`에 사유가 이름으로 등재돼 있다: `alignment_verdict_harness.mjs`(163 ran / 6 failed — 은퇴한 front/back 후보 공간과 8-of-16 거울 동등성) · `map_editor2_shell_harness.mjs`(**ESM import 단계에서 죽는다** — 은퇴한 `SIDE_HEADERS`를 이름으로 import) · `map_editor2_question_harness.mjs`(픽스처가 `rot180_back`을 고른다) · `map2_placement_seat_harness.mjs`(`rot*_front/back` id 파싱). **넷 다 「고쳐야 할 코드」가 아니라 「다시 써야 할 픽스처」다.**
- 🆕 🔴 **[`21209d7`] 확정 버튼의 관문이 「무언가 선택돼 있다」 하나로 줄었다** — `view_model.confirmModel`의 `enabled = !!selectedId`. **제거된 둘은 이제 강제가 아니라 *고지*된다**: ① `not_scorable`(채점기가 못 쟀다는 것은 **사람이 유일한 답인 바로 그 경우**이고 서버는 그 상태를 언제나 받아 왔다 — `frame_confirmation.accepted_ruling_states`) ② `restsOnGuess`(추측된 x/y 바인딩·미진술 귀속 — 여전히 note로 표면화된다: 「추측된 쌍 위에서 답하고 있다」는 **누르기 전에** 가져야 하는 사실이고 이 쓰기는 되돌릴 수 없다). `selectedId`는 남는다 — **아무것도 확정하지 않는 것은 행위가 아니라 빈 쓰기다.**

### 🆕 `map_key.js` (**158줄**, `689ebb9` 신설) — 맵 정체성 정규화의 **유일 구현**

**`map_editor.js`에서 잘려 나온 순수 잎(leaf)이다** — 이 파일은 아무것도 import하지 않고 **모듈 상태가 0**이며, 그것이 추출의 성립 조건이었다. 서버 절반(`map_overlay.canonical_key_value`/`compose_map_id`/`build_key_filters`)과 **값 대 값으로** 채점된다(`client2/tests/seam_7b_oracle.py` · `contracts/map_seam/`).

| export | 시그니처 | 내용 | 라인 |
|---|---|---|---|
| ✅ | `canonicalKeyValue(value, colType)` | null/undefined → `null`. **`number` 선언**이면 정수 정규화(`'01'`→`'1'`, `'1.0'`→`'1'`), 못 읽으면 trim한 원문. 그 외는 trim한 문자열. 단 **정수형 유한 JS number는 선언 타입과 무관하게** 정수로 문자열화된다 | ~58 |
| ✅ | `composeMapId(keyColumns, values, columnTypes)` | 컬럼별 `canonicalKeyValue` → null은 `''` → `join('_')` | ~84 |
| ✅ | `decomposeMapKey(keyColumns, mapKey, columnTypes)` | `'_'` 분할, **마지막 컬럼이 나머지를 흡수**. 조각이 컬럼보다 적으면 `cols[0]`에만 전체를 배정 | ~95 |
| ✅ | `canonicalMapKey(keyColumns, mapKey, columnTypes)` | 분해 후 재합성(멱등). 분해 불가 갈래에서는 **재합성하지 않고** 첫 컬럼의 정규값을 돌려준다 — 빈 꼬리를 발명하지 않기 위해서다 | ~115 |
| ✅ | 🔴 **`getMapIdFromMeta(metaDict, tableSchema)`** | **[이동 중 유일하게 형태가 바뀐 시그니처] 스키마를 모듈 상태에서 읽지 않고 인자로 받는다.** `tableSchema.map_key_columns` 우선, 없으면 `composite_key_source`에서 `x/y/val/die_id/code/grid_metadata`를 뺀다. 전부 비면 `'default_map'` | ~130 |

- module-private: `CANON_INT_RE`(~37) · `CANON_FLOAT_RE`(~41 — **10진수만, `0x10`을 의도적으로 거부**) · `canonIntString(s)`(~44 — `parseInt` 없이 부호·선행 0을 제거하므로 임의 길이 숫자열에 정확하다).
- ⚠️ **`contracts/map_seam/vectors.json`이 그 private 3종을 이름으로 핀한다**(~221–228 · ~292–293) — **import하는 곳이 없어도 개명하면 계약이 깨진다.** "안 쓰이니 바꿔도 된다"가 이 파일에서는 거짓이다.
- **소비자**: `map_editor.js`(**~42–44**, 5개 전부)가 유일한 ES import. 그 밖은 텍스트 슬라이스 소비자다(`map_key_canonical_harness.mjs` · `valid_die_authoring_harness.mjs` · `seam_7b_oracle.py` · `contracts/map_seam/client_harness.mjs`).

### 🆕 `split_registry_row.js` (**366줄**, `636f867` 신설) — `map_split_registry` 행의 정규형

**역시 `map_editor.js`에서 잘려 나왔고 모듈 상태가 0이다** — 🔴 **상태를 가진 절반(`legendReplaceScope`·`legendConflict`·`legendSaveState`·서버 IO)은 남겨 뒀다.** 그 경계가 추출을 가능하게 한 선이다. import는 `transfer_plan.js`의 `bandToState`(~23)와 `doe_bands.js`의 `parseMaterialList`·`bandsToZones`(~24)뿐.

- export **10종**: `normalizeBands`(~59) · `normalizeKnobs`(~92) · **`normalizeLegendItem`(~146 — legend 행의 단일 정규형)** · `cloneLegend`(~167) · **`registryFingerprint(rows)`(~222 — 동시성 지문)** · **`buildLegendRegistryUpdates(refTable, mapKey, legendArr, user, nowStr)`(~237)** · **`parseLegendRegistryRows(result, dedupeByValue)`(~286)** · `getMissingDescValues`(~346) · `formatLegendMetaText`(~353) · **`legendRowSignature(item)`(~361)**.
- 🔴 **`LEGEND_PAYLOAD_COLUMNS`(~192)가 이 파일의 심장이다** — **쓰기 페이로드 · 동시성 지문 · 어휘 서명 셋이 전부 같은 이 투영을 쓴다.** 저장되는 필드와 비교되는 필드가 갈리면 **화면에 보이는 편집이 저장에서 조용히 빠진다.** `legendRowSignature`만 `eventtime`을 **제외**한다(서버 기장 값이라 사용자의 어휘 주장과 무관하다).
- 🔴 **`buildLegendRegistryUpdates`는 `vocab === true` 행을 걸러낸다** — 주장되지 않은 어휘 브러시가 `replace_map` 쓰기에 들어가면 안 된다. 빈 `value`도 거른다.
- 🔴 **`parseLegendRegistryRows`의 마이그레이션 실패는 추측하지 않는다** — zone 컬럼이 없으면 레거시 `bands`를 `bandsToZones`로 옮기되, **실패하면 원본을 `legacyBands`+`legacyReason`에 담아 저장을 막는다.** 뭉갠 읽기를 `replace_map`으로 되쓰면 서버의 진짜 계획이 덮인다.
- module-private **12종**: `SPLIT_KEY_SEP='|'`(~27) · `buildSplitKey`(~29) · `parseJsonCol`(~53) · `knobsToObject`(~106) · `serializeKnobs`(~115) · `serializeStack`(~123) · `serializeMaterials`(~132) · `LEGEND_PAYLOAD_COLUMNS`(~192) · `legendRowPayload`(~196) · `canonRegistryRow`(~213) · **`FP_UNIT`(~220) · `FP_ROW`(~221)** (ASCII US/RS — **화면에 보이지 않는 문자**라 눈으로 검증할 수 없다).
- ⚠️ **`contracts/legend_map_scope/client_harness.mjs`가 private 4종을 이름으로 슬라이스**하고(~139–142), `contracts/doe_band_rules/client_harness.mjs`가 `LEGEND_PAYLOAD_COLUMNS`의 존재를 **능동 단언**한다(~126–127). `server/tests/test_install_product_tables.py`도 `updates:` 리터럴을 정적으로 읽는다.
- **소비자**: `map_editor.js`(**~50–54**, 10개 전부)가 유일한 ES import.

### 🆕 `retroactive_view.js` (**446줄**, 신설) — 소급 적용 화면의 **뷰 모델**(DOM 없음)

`config_resolve_view.js`와 같은 계열이다 — **DOM을 만들지 않고 렌더 가능한 객체만 만든다.** 모듈 상태 0이고, 파생 상태는 전부 호출자의 오퍼레이션별 레코드에 살며 **인자로 들어온다**. import는 `config_resolve_view.js`의 `CHROME`·`srv`·`val`·`chrome`·`count`(~28).

- **`CHROME` 재export(~35)** — 공용 실패 문구는 다시 저작하지 않는다. **`RETRO_CHROME`(~43, `Object.freeze`)** = 클라가 저작하는 것은 **구조 슬롯 라벨뿐**(제목·버튼 문구·"삭제 대상"·"커밋 단위"·stale/truncated 슬롯명·확인 질문 1개). **`RETRO_CHROME_STRINGS`(~86)** = 그 값 목록 — 🔴 **하니스가 "화면의 모든 문자열은 chrome이거나 서버가 보낸 것"을 단언하기 위해 존재하는 export**다.
- `paramsKey(entries)`(~130 — 순서 무관 안정 정체성) · **`resolveCount(record, operation)`(~142 — `{count, stale}`. 행·버튼·확인창의 stale 판정이 여기 하나로 모인다)** · `paramEntries(record, operation)`(~156 — **오퍼레이션이 선언한 키**로만 만든다: 서버에서 이름이 바뀌거나 사라진 param이 미선언 키로 새어 나가지 못한다).
- `buildOperationsView(payload)`(~233) · **`buildCountView(payload)`(~281 — `affected`는 `affected_label`이 있을 때만 낸다(없으면 `null`). `count_kind`는 단어 그대로 나르고 `kindTone`만 덧붙인다 — 모르는 값이면 `''`)** · `buildRunView(payload)`(~325 — 서버의 param **에코**를 원소 단위로 나른다. 배열을 join하지 않는다) · **`buildActionsView(operation, record)`(~359 — `busy` 하나가 둘 다 막고 `blocked`는 실행만 막는다. 🔴 **stale은 아무것도 막지 않는다** — 그 거절은 다른 파라미터에 대해 측정된 것이다)** · **`buildConfirmLines(operation, record, params)`(~406 — 확인창을 출처 태그가 붙은 줄 객체의 순서 있는 목록으로. `role:'question'`은 정확히 하나이고 맨 끝이다. stale한 수는 여기 뷰 모델에서 떨어뜨린다)**.
- module-private **9종**: `KIND_TONE`(~101) · `list`(~119) · `text`(~164) · `integer`(~168) · `operationTone`(~179) · `buildFacts`(~187) · `buildParam`(~197) · `buildOperation`(~208) · `buildExtras`(~261).
- ⚠️ **`resolveCount` 안의 지역 `const count`(~143)가 ~28에서 import한 `count` 헬퍼를 가린다.** 오늘은 무해하지만(그 함수는 숫자를 포맷하지 않는다) 그 안에서 `count(...)`를 부르는 순간 조용히 틀린다.
- **소비자**: `admin.js`(**~25–28**) — 11개 중 **9개만** 가져간다(`RETRO_CHROME_STRINGS`와 재export된 `CHROME`은 안 쓴다. 후자는 `config_resolve_view.js`에서 직접 받는다). 나머지 둘은 **하니스 전용 export**다(`client2/tests/retroactive_view_harness.mjs`).

### `transfer_plan.js` (**1,875줄**, `1dc761b` 1,772에서 **+103**) — 「2. Legend & DOE」 패널 (map_editor.html에서 소비)

> 🔴 **구 지도는 이 절에 앵커 세트를 두 벌 들고 있었고 서로 어긋났다**(2026-08-04 정정). `notifyMapContext`가 한 줄에서는 `~1603`, 다른 줄에서는 `~1520`이었고 `UNTRACKED_REASON`은 `~498`과 `~464`였다. **실측은 각각 1706과 504다 — 두 벌 다 틀렸다.** `grid.js`가 같은 형태로 실패했을 때 적어 둔 진단이 여기에도 그대로 적용된다: **중복 목록은 오차 허용 범위 안에 있는 쪽이 정답처럼 읽히는 것이 아니라, 둘 다 그럴듯해서 아무 검사도 통과시킨다.** 아래는 **한 벌**이고 전건 `ed9cfdb` 실측이다.

**「계획 = 지금 열어 편집 중인 그 맵」.** 계획 정체성은 `(ref_table, map_key)`이며 `plan_id`도 계획 맵 사본도 없다. 스타일은 `transfer_plan.css`. (구 M1 `bonding_plan.js`/`.css`는 삭제 — 파일 자체가 없으므로 앵커를 달지 말 것.)

> ⭐ **이 파일은 서버에 쓰지 않는다.** 값 하나 = `map_split_registry` 행 하나 = DOE 하나이고, 그 행의 **유일한 기록자는 `map_editor.js`**다. 이 파일은 `controller.getLegend()`로 읽고 `controller.updateLegendRow(value, patch)`로만 쓴다 — 저장·삭제·동시성 가드는 전부 그 한 경로에 있다. 순수 산술·규칙·TSV 계약은 전부 **`doe_bands.js`**에 있고 이 파일은 렌더·바인딩·서버 요약 조회만 한다.
> ⭐ **파생값은 저장하지 않는다** — 구역 총 소요 = 칠한 셀 수 × 구역 층수, 자재당 = `ceil(총 소요 / 자재 수)`(충분성 검사이지 배분이 아니다).

#### 🆕 🔴 [`784a07d`] 감산 미적용 표시 — `≤`를 빌려 쓰지 않는다

서버의 [`inactive_subtractions`](#5-소형-서버-모듈) 필드가 이 화면에 도달하는 자리다. **사이트가 보조 감산 소스를 선언조차 하지 않은 상태**이고, 서버는 그 감산을 빼지 않은 수를 **강등 없이** 내보내며 빠진 종류를 이 필드로 밝힌다.

- **`inactiveSubtractionsOf(data)`(~538)** — 필드 부재는 **빈 배열**(= 전 역할 선언 사이트, 오늘과 같다). 🔴 **서버의 어휘를 그대로 쓴다** — 역할 이름을 한국어로 번역해 두 번째 철자를 만들지 않는다. 운영자가 config에서 찾아야 하는 토큰이 화면의 토큰과 달라지는 순간 이 표시는 조회 동선을 **늘리기만** 한다.
- **`GROSS_MARK = '*'`(~548)** — 각주 기호, **한 글자**다. 58px 폭의 수 열에 문장이 들어갈 자리는 없고, 그래서 **의미를 기호가 나르지 않는다.** 기호는 같은 화면의 각주를 가리키고 빠진 감산의 이름은 거기와 tooltip에 **본문 크기로** 적힌다 — 작은 글씨로 이름을 우겨 넣으면 아무도 못 읽는 표시가 되고, 그건 **공시 없는 공시의 외양**이다(핵심가치: 가독성 = 기능).
- `grossReason(inactive)`(~550) · `isGross(av)`(~555) · **`grossRolesOf(avs)`(~563 — 이 화면이 밝혀야 할 「빠진 감산」의 합집합. **구현은 하나다**: 각주와 [↻ 가용] 토스트가 각자 모으면 두 곳이 서로 다른 목록을 말한다. 서버가 준 **순서를 유지한다** — 정렬하면 운영자가 config를 읽는 순서와 어긋난다)** · `grossNoteHtml(grossRoles)`(~575 — 역할이 없으면 빈 문자열이라 전 역할 선언 사이트의 각주는 **바이트 단위로 오늘과 같다**).
- 🔴 **`≤`를 빌려 쓰지 않는다.** `≤`는 `remaining_upper_bound`(**선언된 미추적**, 7c) 전용이고 서버는 이 갈래에서 그 필드를 **의도적으로 세우지 않는다.** 같은 기호를 쓰면 서로 다른 두 상태가 화면에서 같아진다.
- 🔴 **`reliable`에 묶지 않는다.** 완화 이후 이 갈래의 `remaining_reliable`는 `true`다 — 신뢰도 축은 여전히 서버 소관이고 여기서 다시 판정하지 않는다. 섞으면 이 숫자가 미상으로 붕괴하는데, **사이트는 그 숫자를 쓰기로 결정한 상태다**(완화의 목적 그 자체).
- 하니스: `client2/tests/availability_gross_marker_harness.mjs`.

#### 앵커 (전건 `ed9cfdb` 실측)

- 상태·상수: `SOURCE_TABLE_FALLBACK`(~62) · `SOURCE_OVERLAY_SUGGESTIONS`(~65) · **`S`(~70–91)** · `elp`(~92) · `controller`(~93) · `warnedFallback`(~144) · `stagesPromise`(~168) · `matKickTimer`(~366) · `doeListShape`(~873) · `renameHint`(~877).
  - `S`: `stages`(**[U6] 초기값 `[]`** — 서빙된 선언만)/`stagesStatus` · `ctx{table,mapKey,loaded,depth,parent}` · **`legendRows`(= DOE 그 자체의 **읽기 전용 미러**)** · `blocks` · `counts` · `activeBrush` · `summaries` · `matMapState` · `keyColumns` · `matSeq` · `flash` · `navBusy`.
- 유틸: `esc`(~96) · `hhmm`(~103) · `fmtChips`(~110).
- stage 유도(**[U6] 선언의 단일 원천 = 서버**): `normalizeStage`(~116) · `stageOfTable`(~133, 서버 `stage_of_table`의 클라 미러) · `sourceTableOf`(~146) · `sourceTableOfStage`(~162) · `fetchStages`(~170 — GET `/api/transfer-plan/stages`. **부재 2종을 가른다**: 404/405·빈 선언 = "선언 없음"(확정, `stages=[]`) vs 그 외 실패 = "확인 불가"(**마지막으로 안 선언 유지** + 다음 맵 전환 시 재시도). 내장 목록은 절대 아니다) · `ensureStages`(~192) · **`stageTargetTables()`(~200, export — 선언된 stage 타깃 테이블 목록, 선언 순. `map_editor.loadTablesList`의 초기 테이블 선택이 소비. 불가면 `[]`)**.
- **레거시 band 판독기 2종 — [§6-2 계약](#6-2-교차-구현-계약-contracts) 추출 대상**: **`bandToState(b)`(~226 — 유일한 정수 분류기 `{state:'blank'|'ok'|'invalid', value}`. **`split_registry_row.normalizeBands`와 `doe_bands.stackState`가 모듈 경계를 넘어 이것을 쓴다**)** · `prevTo(bands, i)`(~275 — `doe_bands.bandsToZones`가 걷는 유일한 레거시 걷기). export 지점 ~260. ⚠️ ~~`bandTo`/`bandLayers`/`bandTotal`/`bandShare`~~ 등 band 산술 일습은 **부재가 하니스로 단언**된다([§0](#0-묘비-목록--소스에-존재하지-않는-이름)).
- legend 접근·변조: `paintedOf`(~283) · `splitMaterialId(id)`(~299 — 분리자 없으면 `{lot:null, slot:null}`, **추측하지 않는다**) · `rowOf`(~310) · `isMarkerStack`(~341)/`stackCrossesMarkerBoundary`(~345) · **쓰기 관문 하나 — `commitRow(value, patch)`(~350)** → `controller.updateLegendRow` 위임, 실패 시 토스트만. **이 파일에 저장 코드는 없다.** · `kickMaterialRefresh`(~367).
- 소스 요약(**풀 단위**): `poolCacheId`(~384) · `summaryKeyFor`(~388) · `getPoolSummary(pool, force)`(~393 — GET `/api/transfer-plan/source-summary`, BIN·scope 파라미터 포함) · **`availabilityOfPool(pool)`(~438)** · `isPlainNotFound`(~584) · `matMapCacheKey`(~589) · `materialKeySpec`(~595) · `canonKey`(~606) · `materialMetaValues`(~612) · **`matMapCacheHit(ck)`(~648)** · `probeMaterialMap`(~652) · `refreshMaterials(force=false)`(~1601) · `rewardAfterReturn`(~1574).
  - 🔴 **`availabilityOfPool`의 반환 형태에 `bound`와 `inactive`가 **항상** 있다**(없으면 각각 `null`·`[]`). 어떤 갈래에서만 빠지면 소비자가 `undefined`와 "상한 없음"을 구분하려 들게 되고, **그 순간 판정이 둘로 갈린다.**
  - **[F4] 자재 맵 존재 캐시는 긍정 답만 신뢰한다** — `matMapCacheHit`은 `S.matMapState.get(ck) === true`일 때만 true. 호출자 `probeMaterialMap`이 `false`("그런 맵 없음")와 `null`("확인 불가")에는 **재조회**한다. 구 판정은 `.has(ck)`였고 그것이 **사용자가 실제로 행동하는 두 답에 대해 요청을 영구 차단**했다(실측: 서버에 261행이 있고 리로드 후에도 X). 규칙은 형제 캐시 `getPoolSummary`에서 **그대로 베꼈다**.
- **[7c] 「≤N」 상한 표기 — 이 파일에 폴백 산술은 없다**: `UNTRACKED_REASON`(~504) · **`untrackedBoundOf(entry)`(~506 — `transfer_untracked === true`일 때만, 그리고 **`remaining_upper_bound` 필드 그 자체만** 읽는다. 상한은 서버가 준 수이지 클라가 계산한 수가 아니다)** · `boundText(bound)`(~515 — `` `≤${bound}` ``). 🔴 **선언은 정확히 boolean `true`뿐이다** — `'true'`·`1`·`'none'`·`null`·`''`은 전부 사고성 미상으로 남는다(서버가 `"none"` **문자열만** 선언으로 받는 것과 같은 규율. 클라가 느슨하게 받으면 그 엄격함이 이 화면에서 무효가 된다).
- 렌더(zone 그리드): `renderPlanHead`(~666) · `zoneCellHtml`(~755) · `ZONE_PLACEHOLDER`(~790) · `zoneIsInapplicable`(~802 — **[U9] marker 행(STACK 0)은 전 구역 `inapplicable`**) · `materialChipHtml`(~830) · `planOf`(~844) · `rowNodesOf`(~879)/`captureEditFocus`(~886)/`restoreEditFocus`(~902) · `blockMsgsHtml`(~921) · `patchDoeList`(~930) · `renderDoeList`(~966) · `colHeader`(~1060) · `refreshRowZones`(~1071 — **행 단위 갱신**: 전체 리스트 재구성이 입력 랙의 원인이었다) · `focusedRowValue`/`focusedColumnId`(~1126/1132) · `bindDoeList`(~1141) · `rollupRows`(~1244) · `unknownCellHtml`(~1252)/`availCellHtml`(~1261)/`remainingCellHtml`(~1282)/`remainingIsNegative`(~1301) · `renderMaterialPane`(~1309) · `knobChipsFor`(~1419) · `renderAll`(~1648)/`buildWorkspace`(~1654).
- **Excel 클립보드(6열 TSV 계약 — `tsv.js` + `doe_bands.js` 소비)**: `planClipboardActive`(~1444) · `onPlanPaste`(~1451 — `parseTsv`→`mapPastedGrid`→행별 `commitRow`) · `onPlanCopy`(~1509 — `planToGrid`→`serializeTsv`). 왕복 동일성은 `contracts/doe_band_rules`의 `roundtrip_cases`가 고정한다. ⚠️ **`map_editor.js`의 `onMapGridPaste`(회사 시트 왕복)와 다른 경로다** — 후자는 `e.defaultPrevented`를 먼저 보고 **이 패널이 이미 처리했으면 양보한다**. 그리고 패널 붙여넣기는 **위치 기반**이라 VALUE 변경을 개명으로 취급하는데, 회사 시트 쪽은 **VALUE로 주소를 매긴다**.
- 이동 허브: **`openMaterial(id)`(~1526)** — **맵 간 이동의 유일 지점**(프레임 스택). `(lot, slot)`으로 분해되지 않는 id도 **라우팅한다**(첫 키 컬럼 필터 폴백). 행 없는 키는 빈 그리드로 열리고 ⚡ Push에서 생성된다. **`probeMaterialMap`은 이런 id에 계속 null(미상)을 반환한다** — 내비게이션 추측은 되지만 존재 주장은 안 된다.
- 진입/통지 export: **`notifyMapContext(info = {})`(~1706)** — **`info.serverRead`를 읽는 유일한 지점**(`if (changed || info.serverRead)`). 그 분기 안에서 실패한 stages 재조회 + `refreshMaterials()`를 **`force = false`로** 부른다(사용자가 소리 내어 요청한 게 아니라 토스트 없음 — **읽기는 무마찰**. `force`는 `↻ 가용` 버튼 전용으로 남는다) + `info.returnedFrom`이면 `rewardAfterReturn`. · `notifyLegendChanged()`(~1732) · `notifyPaintCounts(counts)`(~1744, **`textContent`만 패치**) · **`initTransferPlan(paintController)`(~1772)**.
- ⚠️ **`__held_*` 함수군(~1794–1875)은 명시적 보류 구역** — 호출자 없음. 검증/경고 UI는 사용자 지시로 미구현. ⚠️ `__HELD_WARN_SEVERITY`(~1844)에 **`layer_coverage_gap` 키가 남아 있으나 서버에서 삭제된 경고 타입이라 사문**이다([§0 ③](#0-묘비-목록--소스에-존재하지-않는-이름)의 실측 2건 중 하나가 이것이다).

### `doe_bands.js` (**753줄**, +31) — DOE ZONE 모델 순수 코어
**앵커 (2026-07-30 실측)**: `ZONES`(~50)/`ZONE_LABEL`(~55) · `boundState`(~60) · `stackState`(~73) · `formatLayerRuns`(~83) · **`parseMaterialList`(~103)**/`serializeMaterialList`(~125)/`parseMaterialToken`(~153)/`materialPoolKey`(~201) · `midZone`(~212) · **`zoneLayers`(~229)**/`zoneLabel`(~247) · **`validateZonePlan`(~270 — V1–V6)** · **`zoneDemand`(~405)**/**`materialRollupRows`(~427)** · `REMAINING_UNKNOWN_REASON`(~473)/`remainingState`(~478) · **`DOE_COLUMNS`(~494)**/`IGNORED_HEADERS`(~539)/`columnIdByHeader`(~544)/`looksLikeHeader`(~555)/`leadingBlankColumnDropped`(~584)/**`mapPastedGrid`(~610)**/`planRowToRecord`(~651)/`planToGrid`(~669) · `ROLLUP_COLUMNS`(~676)/`ROLLUP_UNKNOWN`(~677)/`rollupToGrid`(~678) · **`bandsToZones`(~712)**.
⚠️ **[F1ⓑ] `IGNORED_HEADERS`에 `COUNT`가 있는 것이 계약이다** — 회사 시트 붙여넣기가 COUNT를 **인식하고 나서 버린다**(칠한 셀 수는 격자에서 다시 센다). 그리고 `5a14e77`이 `MAT·BIN·MAP·가용·사용·잔여`를 명부에 올린 것이 `map_editor.auxHeaderInLine`의 VALUE 정지 조건을 필요하게 만든 원인이다.

계보: `269b39e` 신설, `b35bc9f` 확장, **`2baf9ff` U9 marker** — 무DOM, `contracts/doe_band_rules` 채점 대상. `95bf072`는 **주석 리포인트만**(규칙 번호 정본 인용을 유령 경로 ~~DOE_ZONE_MODEL.md~~에서 `MAP_EDITOR_SPEC §6.0-bis`로).
**서버 `transfer_plan.py`의 zone 블록(~2048–2610)과 짝을 이루는 클라 측 정본.** export(~713): `ZONES`/`ZONE_LABEL`(~50/55) · `boundState`(~60)/**`stackState`(~73 — `bandToState` 위임 위에 **4상태**: 명시적 0만 `'marker'` 승격(~76), 음수는 invalid로 값 보존. 서버 `stack_state`+`STACK_MARKER`의 미러)** · `formatLayerRuns`(~83) · **`parseMaterialList`(~103 — 유일한 자재 목록 정규화기: 패널 입력도 저장 계층도 이것을 쓴다. 화면의 자재 수와 `ceil(total/n)`의 분모가 두 숫자가 될 수 없게)** · `serializeMaterialList`(~125) · `parseMaterialToken`(~153, `lot[_slot][:BIN]` 문법) · **`materialPoolKey`(~201 — ⚠️ 분리자 조인 금지의 실사례 주석: U+001F 조인 키가 디스크에서 분리자를 잃어 두 풀이 합산됐다)** · `midZone`(~212 — marker는 `{size:0, known:true}` ~219)/`zoneLayers`(~229 — **marker는 전 구역 `[]`** ~234)/`zoneLabel`(~247) · **`validateZonePlan`(~270 — V1–V6 차단 + advisory. **marker 행은 V6 하나에만 답한다**: V6 블록 ~287–302, V3 풀 스캔 제외 ~372)** · `zoneDemand`(~405 — **은퇴한 `bandTotal`/`bandShare`의 후계**) · `materialRollupRows`(~427 — marker 행은 롤업에 **부재** ~435) · `remainingState`(~478) · **6열 TSV/Excel 계약**: `DOE_COLUMNS`(~494) `IGNORED_HEADERS`(~511) `columnIdByHeader`(~513) `looksLikeHeader`(~524) `leadingBlankColumnDropped`(~553) `mapPastedGrid`(~579) `planRowToRecord`(~620 — 읽을 수 없는 STACK도 **원문 그대로** Excel로 돌려보내되, **marker는 판독 가능이라 canonical `'0'`으로 export** ~627) `planToGrid`(~638) `rollupToGrid`(~647) · **`bandsToZones`(~681 — 레거시 band 계획 → zone 사상. 표현 불가면 거부)**.

### `tsv.js` (~121줄) — TSV 파서/직렬화기 (`b35bc9f` 신설)
Excel 클립보드 왕복의 공용 저층 — export `parseTsv`/`serializeTsv`/`quoteField`(~121). 소비자 둘: `clipboard.js`(그리드 복붙) · `transfer_plan.js`(DOE 6열 계약). 인용부호·개행 처리를 한 곳으로 모은 것이 존재 이유다.

### `admin.js` (**3,704줄** — `1dc761b` 3,202에서 **+502**, 소급 적용 패널) — 어드민 페이지 (2026-07-25 전면 재작성 — 파이프라인 5탭, export 없음)

> 📐 **이동은 두 계단뿐이다**(2026-07-31 실측): **구 1–18 무이동** · **구 19–1,567 +6**(`config_resolve_view.js` import 블록 3줄 + 상수) · **구 1,568 이후 +330**(config-resolve 패널 한 덩어리, `initConfigResolveLine` **~1598**부터 `runAutoConfirmDryRun` **~1839**까지).
>
> 🔑 **[`90e284f`] 파일 최상단이 토큰 블록이다(**~28–156**).** 서버가 `/admin/*`을 공유 비밀 뒤로 옮겼으므로([§1.6](#16-serveradmin_authpy--어드민내부-토큰-게이트-90e284f-신설)) 이 페이지는 **로그인 화면도 사용자 모델도 없이** 토큰 하나를 묻고, 보관하고, 헤더로 붙인다. 서버에 토큰이 설정돼 있지 않으면 게이트 라우트가 정상 응답하므로 **아무것도 묻지 않고 이 장치는 보이지 않는다** — 프롬프트는 **게이트가 낸 거부**에만 뜬다.
>
> ⚠️ **`grep "fetch(\`${API_BASE}/admin/"`가 0건이어야 한다.** 히트가 있으면 그 호출부는 `adminFetch`를 우회한 것이고, 미설정 서버에선 잘 돌다가 **프로덕션에서만 401**이 된다.

| 심볼 | 역할 | 라인 |
|---|---|---|
| `ADMIN_TOKEN_HEADER='X-Admin-Token'` / `ADMIN_TOKEN_KEY='assy.adminToken'` | 헤더명(서버 `admin_auth.ADMIN_TOKEN_HEADER`와 짝) / localStorage 키 | **~40/41** |
| `getAdminToken()` / `storeAdminToken(value)` | localStorage 읽기·쓰기. **둘 다 try/catch** — 프라이빗 모드·스토리지 비활성이면 토큰이 이 페이지 수명만큼만 산다 | **~43/47** |
| **`adminTokenGeneration`** | **토큰이 바뀔 때마다 증가.** 토큰 교체 시점에 이미 날아가 있던 응답은 **낡은 증거**라 새 토큰에 대해 아무것도 말하지 않으므로 두 번째 프롬프트를 띄우면 안 된다. 이것이 없으면 "동시 7요청에 프롬프트 1회"가 타이밍 운에 좌우되고, 실제로 모달이 몇 초 열려 있는 동안 도착한 응답들이 **멀쩡한 토큰을 틀렸다고 몰아세웠다** | **~60** |
| `adminTokenDeclined` / `tokenPromptInFlight` | 운영자가 취소했음(30초 리프레시마다 영원히 다시 묻는 것은 수정이 아니라 함정 — 새로고침하면 다시 묻는다) / 진행 중 프롬프트 1개 공유 | **~63/64** |
| **`isGateRejection(res)`** | **게이트가 낸 거부만 true.** 상태코드만으론 부족하다 — `_resolve_admin_script_path`도 403을 내는데 토큰과 무관하다. 그것을 인증 실패로 취급했더니 페이지가 토큰을 요구하고 **맞는 저장 토큰을 덮어썼다.** 판정 근거는 **`WWW-Authenticate: X-Admin-Token` 헤더**.<br>🔴 **[`cde3398`] 이 술어는 서버가 그 헤더를 CORS `expose_headers`에 올려야만 교차 출처에서 동작한다**([§1.1](#11-기동미들웨어공용-헬퍼)) — 올리지 않으면 브라우저가 헤더를 지워 **vite dev(:5173)에서 진짜 게이트 거부가 「앞단이 답했다」로 오분류**된다. **소비자가 하나 더 생겼다**: `failureFactOf`(아래) | **~74** |
| `askForAdminToken(message)` | `window.prompt` 1회(진행 중이면 공유). **`setTimeout(…, 0)`로 한 틱 미룬다** — 같은 `Promise.all`의 형제 핸들러들이 모달이 스레드를 막기 전에 이 프라미스에 붙게 하기 위함. **취소는 저장 토큰을 지우지 않는다**(구 코드는 취소를 `storeAdminToken('')`로 바꿔 **작동하던 토큰을 삭제했다**) | **~81** |
| `withAdminToken(init)` | fetch init에 헤더 주입. **쿼리 파라미터가 아니라 헤더인 이유는 쿼리스트링이 서버 액세스 로그에 남기 때문** | **~109** |
| **`adminFetch(url, init)`** | **`/admin/*` 전용 fetch — 이 파일의 모든 어드민 호출이 여기를 지난다.** ① **503이면 본문 `detail`을 토스트로 띄우고 그대로 반환**(**~129**) ② 게이트 거부가 아니면 통과 ③ **세대가 바뀌었으면 조용히 새 토큰으로 1회 재시도**(**~141**) ④ 프롬프트 후 **딱 한 번만 재시도**(두 번째 거부는 호출자에게 돌려줘 운영자를 모달에 가두지 않는다) | **~121** |

#### 🆕 config-resolve 패널 (`93610cb` 신설 · `1dc761b` 수정) — 「내 config가 먹었는가」의 화면 절반

> 🔴 **새 영역·모드·모달이 아니다** — Overview에 **줄 하나**(`#config-resolve-summary`)가 서고, 펼치면 도메인 카드가 나온다. 자동 펼침은 **tone이 있을 때 1회뿐**(`configResolveAutoOpened` **~1578**).
>
> 🔴 **문장은 하나도 여기서 만들지 않는다.** 뷰 모델은 **DOM-free 모듈**(`config_resolve_view.js`, 아래)이 만들고 이 파일은 그것을 DOM으로 옮기기만 한다 — 그 분리가 곧 **계약이 node에서 채점될 수 있는 이유**다([§6-2](#6-2-교차-구현-계약-contracts)).

| 심볼 | 역할 | 라인 |
|---|---|---|
| `CONFIG_RESOLVE_MIN_INTERVAL_MS = 60_000` | 재조회 하한. 어드민의 30초 리프레시가 이 보고서를 매번 다시 끌어오지 않게 한다 | **~1568** |
| `configResolveLastAt` · `configResolveTokenGeneration` · `configResolveView` · `configResolveRaw` · `configResolveAutoOpened` · `dryRunByRule` | 조회 시각 / **토큰 세대 스냅샷**(토큰이 바뀌면 하한을 무시하고 다시 묻는다) / 뷰 모델 / **원문 문자열**(같으면 재렌더 자체를 건너뛴다) / 1회 자동 펼침 플래그 / 규칙별 드라이런 캐시 | **~1570–1581** |
| `initConfigResolveLine()` | Overview 배선. 호출은 초기화 경로 **~306** | **~1598** |
| 🆕 **`failureFactOf(res)`** | **[`1dc761b`] 실패한 응답이 자기 자신에 대해 말하는 사실** → `{status, gate, server}`. 🔴 **`isGateRejection`이 load-bearing이고 재유도하지 않고 재사용한다**(주석 **~1603–1606**) — 401을 게이트 거부로 부르는 판정은 **이 파일에 이미 하나 있고 두 번째를 만들면 갈라진다** | **~1610** |
| **`refreshConfigResolve(force=false)`** | `GET /admin/config/resolve`(**~1636** 부근) → `buildConfigResolveView(JSON.parse(raw))`. 🔴 **원문이 같으면 재렌더도 캐시 무효화도 하지 않는다**(**~1641**). 실패는 `fetchFailureLine(failure, CHROME.FETCH_FAILED)`로 **한 줄 진단**이 된다 | **~1618** |
| `renderConfigResolveFailure(text)` / `renderConfigResolve()` / `cfgDomainEl(domain)` | 실패 줄 / 요약 줄 + 도메인 카드 / 도메인 카드 1개 | **~1661 / ~1673 / ~1705** |
| `cfgDryRunEl(cached)` / **`runAutoConfirmDryRun(rule, btn, host)`** | 드라이런 결과 조각 / `GET /admin/enrichment/auto-confirm/dry-run` 호출 — **쓰기 없는 계기**([§1.4](#14-api-라우트-표--어드민운영그래프맵인리치먼트)) | **~1812 / ~1839** |

- 라우팅: `parseRoute`(**~385**) `applyRoute`(**~397**) — `#overview/#file/#chain/#autoupdate/#enrichment` + 구 별칭 + `#editor=<path>`. `switchTab(tabName, opts)`(**~442**). `setSectionCount`(**~368**).
- 탭 데이터: `fetchData(options)`(**~762**, 탭당 병렬 fetch를 한 seq로 묶어 stale 렌더 차단) → 각 `render*Table` + 섹션 카운트 배지, `clearSelections`(**~2139**)/`clearRowHighlights`(**~2151**).
- [P1] File 탭 진행 중 섹션: `renderActiveIngestions`(**~1070**) `scheduleActiveRefresh`(**~1052**) `formatElapsed`(**~1040**).
- Overview: `fetchOverview`(**~1868**) `renderOverview`(**~2000**) + **[`ec75d4c`] `renderRecorrection`(**~1457**)** + **[V1 `2a9f6c4`] `renderEffort`(**~1488**)**.
- 유기 연계: `renderLinkedFailTable`(**~1357**) `showEventDiagnostics`(**~2571**) `selectFileRow`(**~2348**).
- AutoUpdate 토글: `renderAutoUpdateTable`(**~1276**) `toggleCollectorActive`(**~2244**) `runAutoUpdateNow`(**~2217** — **strict 게이트 라우트라 토큰 미설정 서버에선 503 토스트가 뜬다**).
- Enrichment 탭: `renderEnrichmentTable`(**~1386**) `fetchEnrichmentStatus`(**~3022**, 15s TTL 캐시 — 스트립·탭·Overview 3소비처 공용).
- 에디터(공용 뷰): `initMonacoEditor`(**~2741**) `populateEditorPicker`(**~2798**) `selectEditorFile`(**~2844**) `openInlineEditor`(**~2924**, 저장은 **strict 게이트** POST `/admin/scripts/code`).
- 소비 API: `/admin/*` 전역(**전부 `adminFetch` 경유**) + `/enrichment/rules` + `/tables/{t}/data`(결손 카운트).

### 🆕 `config_resolve_view.js` (**324줄**, +7) — config 해석 보고서의 **뷰 모델**(DOM 없음)

🔴 **왜 별 모듈이고 왜 DOM이 없는가 — 이 파일의 존재 이유 전부다.** 이 이음매의 load-bearing 절반은 **부정형**이다: 서버가 운영자용 문장을 조립하고 **클라는 `detail`을 그대로 렌더한다.** 클라가 「이 선언은 효과가 없다」를 스스로 판정하는 순간 [U6](#0-묘비-목록--소스에-존재하지-않는-이름)가 6개를 삭제한 하드코딩 사본 계급이 재발한다. **그런데 DOM을 인라인으로 짓는 렌더러는 node에서 그 성질을 채점할 수 없다.** 그래서 뷰 모델을 여기로 뽑았고, `contracts/config_resolve_report/client_harness.mjs`가 **이 파일을 import해** 내보내는 문자열을 전수 채점한다([§6-2](#6-2-교차-구현-계약-contracts)).

- **`TEXT_SOURCES = ['server','value','chrome','count']`(**~50**) — 채점의 축이다.** 이 모듈이 내보내는 모든 문자열은 넷 중 하나여야 한다: `server`(페이로드 안에 **글자 그대로** 존재) · `value`(정확히 `JSON.stringify(<페이로드 값>)`) · `chrome`(아래 frozen 표에서 옴) · `count`(클라가 센 정수를 그 자체로 적은 것). **config의 상태에 대한 문장이 여기서 조립되는 순간 그것은 페이로드에도 CHROME에도 없고, 하니스가 파일과 줄을 대며 말한다.**
- **`CHROME`(**~26**, `Object.freeze`) / `CHROME_STRINGS`(**~47**)** — **클라가 소유한 문자열의 전부.** 구조 라벨뿐이고 **판정도, 사유별 문구도 아니다**(`설정 반영`·`자세히 보기`·`설정 파일`·`현재 값`·`선언값`·`참조뷰`·`드라이런`·`보류 사유`·`조회 실패` 등).
- 🆕 **[`1dc761b`] 실패 진단 3종 — `fetchFailureText(failure, fallback)`(**~95**) / `fetchFailureEvidence(failure)`(**~114**) / `fetchFailureLine(failure, fallback)`(**~123**).** 🔴 **상태코드는 진단이지 실패 플래그가 아니다** — `CHROME`에 그 결론 4종이 문자열로 있다: `FETCH_OLD_SERVER`(구버전 서버 → 재시작) · `FETCH_UNREACHABLE`(연결 불가 → 서버 실행 확인) · `FETCH_UNAUTHORIZED`(토큰 거부 → 새로고침 후 재입력) · **`FETCH_INTERCEPTED`(관리자 게이트가 아닌 응답 → 앞단에 무엇이 있는지 확인)**. **문구가 원인이 아니라 할 일을 말한다.** 마지막 항목이 `isGateRejection`(=`WWW-Authenticate` 헤더)에 의존하므로 [§1.1의 CORS `expose_headers`](#11-기동미들웨어공용-헬퍼)가 그 판정의 전제다.
- **`POPULATION_TONE`(**~135**)** — `effective`/`ineffective`/`rejected` → `ok`/`warn`/`danger`. ⚠️ **표시 전용 색 표이고, 모르는 모집단은 추측하지 않고 중립으로 그린다.**
- 조립기: `srv`(**~148**)/`val`(**~154**)/`chrome`(**~158**)/`count`(**~162**) — **네 출처에 각각 대응하는 태깅 헬퍼**다. `buildView`(**~170**)·`buildEntry`(**~179**)·`buildSource`(**~200**)·`buildSetting`(**~212**)·`buildDomain`(**~225**) · **`buildConfigResolveView(report)`(**~251**)** · **`buildDryRunView(payload)`(**~288**)** · `collectTexts(node, out=[])`(**~303** — 하니스가 부르는 순회기).
- **`MEASURABLE_DOMAIN='enrichment'` / `MEASURABLE_FIELD='auto_confirm'`(**~144–145**)** — 드라이런 버튼이 **어디에** 붙는가. 지금 계기가 있는 자리가 하나뿐이라는 사실이 상수 둘로 적혀 있다.
- 🔢 **2026-07-31 계약 실행 실측**: `client2/src` **29파일 스캔**, 사유 4단어의 소스 리터럴 **0건**, 이 모듈이 내보낸 **159개 문자열 전부**가 페이로드 또는 CHROME으로 추적됨, exit **0**.

### `enrichment.js` (**1,266줄**, 무변동 — 🔴 **런타임 소비자 0**, 아래 참조) — 인리치먼트 컨베이어 페이지, **고아 모듈** (export 없음)

> 🆕🆕🆕 **[2026-08-11 후속 · `ab36fab`] 이 페이지의 진입점이 없어졌다 — 파일 자체는 삭제하지 않았다.** `client2/enrichment.html`과 vite 빌드 엔트리가 지워지면서(§7 [`client2/enrichment.html`(삭제)](#7-client2src--웹-클라이언트) 참조) 이 모듈을 로드할 HTML이 더는 없다. **실측(2026-08-11): `client2/src/**/*.js`·`*.html` 전체에서 `import ... from './enrichment.js'` 0건** — 어느 페이지도 이 파일을 부르지 않는다. 🔴 **그렇다고 이 행을 지우지 않는다** — 하니스 4개가 여전히 이 파일의 **소스 텍스트를 정규식으로 슬라이스**해 함수/상수를 추출·채점한다(배선이 아니라 텍스트 추출이라 페이지가 죽어도 계속 돈다): `enrichment_grid_sort_filter_harness.mjs` · `enrichment_partial_key_reference_harness.mjs` · `enrichment_provenance_harness.mjs` · `enrichment_queue_partition_harness.mjs`. 처분(삭제·재배선·현행 유지)은 이 지도가 판정하지 않는다 — 클라 도메인 소관.
>
> 아래 `~NNN` 앵커는 여전히 미검증이고 함수명으로 Grep하라(이 패스는 재측정하지 않았다 — 소비자가 없으므로 우선순위 밖).
- 🆕 **`GRID_SHARED_OPTIONS`**(`15a2b39`) — 두 그리드가 공유하는 AG-Grid 옵션 리터럴: `theme:'legacy'` · `localeText.noMatchingRows` · 🆕 **`enableCellTextSelection: true`** · 🆕 **`ensureDomOrder: true`**. **AG-Grid는 기본적으로 셀 텍스트 선택을 막아 드래그 자체가 안 됐다.** 🔴 **`clipboard.js`를 쓰지 않는 이유**: 그 모듈이 `grid.js`·`state.js`·`dom.js`·`ui.js`를 직접 import하므로, 여기서 부르면 **이 파일이 피하려고 통째로 다시 쓴 모듈 그래프가 그대로 딸려 온다.** ⚠️ **이것은 브라우저 기본 복사이지 범위 선택 복사가 아니다** — AG-Grid의 범위 복사는 Enterprise 기능이고 이 페이지는 Community로 돈다. `ensureDomOrder`는 가상 스크롤이 DOM을 재배치한 순서로 붙어 나가는 것을 막는다.
- 규칙: `loadRules`(~77) `selectRule`(~124) `rebuildGrid`(~159). 워크리스트: **`buildBlankFilters`(~192 — [`1fefd12`] 큐 술어는 `rule.queue_filters` 서버 조성 우선**(판단키 notBlank AND target blank), 구버전 서버 폴백만 target-blank 수제) `fetchWorklist`(~202) `fetchTotalAll`(~253) `refillIfNeeded`(~269).
- 입력 흐름: `renderDetail`(~322) `onInputKeydown`(~396) `moveSelection`(~414) `saveCurrent`(~439, PUT `/data/updates`).
- 참조 패널: `initReferencePanel`(~539) `loadActiveReference`(~602) `renderRefTable`(~659).
- 소비 API: `/enrichment/rules`, `/enrichment/rules/{r}/references/{i}`, `/tables/{t}/data`, PUT `/data/updates`.

### `graph_viewer.js` (**1,254줄**) — 지식그래프 서브그래프 뷰어 (graph.html 엔트리, 무라이브러리)
- 조회·URL: `syncUrl`(~349, `?label=&identity=` pushState — 동일 URL 중복 push 방지) `explore(label, identity, opts)`(~360, `/graph/neighbors` 조회→BFS 동심원 레이아웃. `opts.history: 'push'|'replace'|'none'`) `renderStats`(~164, `/graph/stats` 카운트 카드+라벨 색 팔레트 — **라벨 카드 클릭 → 노드 리스트**).
- **라벨 노드 리스트**(`df63f3a` 신설): `openLabelNodes`(~226) `closeLabelNodes`(~234, back → Stats 복귀) `fetchLabelNodesPage`(~240, 빈 q + label 서버 리스팅 — `LABEL_LIST_PAGE=200`(~30, 서버 캡과 동일)·offset "더 보기"·seq 가드) `renderLabelNodesBlock`(~270, 로드수/총수 헤더·행 클릭 → `explore` 연동). `showStatsView/showGraphView`(~321/327).
- 렌더: `layoutGraph`(~438) `renderCanvas`(~543, 캔버스 본체 — 테마 색 1회 캐싱+`themechange` 재캐싱, 상시 rAF 없음).
- **Connections 테이블**(`18218da` 신설): `connectionRows(nodeId, edges, nodesById)`(~713) `propsSummary`(~737) `selectNode(node, opts)`(~751, 선택 확립+`connSeq` stale 가드) `fetchNodeConnections`(~772, 비중심 노드 depth-1 재조회 보강 — label+identity 파라미터) `renderConnBlock`(~802, `CONN_PAGE=80` 단위 "더 보기"·행 클릭 시드 연동) `renderNodePanel`(~870) `setPanelCollapsed`(~939, 패널 접기).
- 이벤트: `onNodeClick`(~969, **선택만** — 중심 이동은 더블클릭/시드 버튼) `initCanvasEvents`(~973, 팬·줌·dblclick 재중심) `exploreFromInput`(~1135) `initSearchBar`(~1167, `/graph/nodes/search` 자동완성+200ms debounce+seq 가드) `init`(~1203, popstate 복원·접기 버튼·초기 쿼리 replaceState — trace 크로스링크).
- user provenance 엣지는 `--overwrite` 색 강조(테이블은 `.conn-user`). truncated 배지. 소비 API: `/graph/stats·neighbors·nodes/search`.

### `trace_core.js` (~234줄) — G2 추적 순수 로직 (무의존, node 테스트 가능)
- export: `SEED_CAP=20`(~10) `composeIdentity`(~38, 서버 G1 `compose_identity` 미러 — `|` 조인+이스케이프+float 안정화) `capSeeds`(~57) `parseSeedsParam`(~73) `normalizeMissingSeeds`(~98) `buildTraceRequest`(~128) `groupNodesByLabel`(~146) `splitTimeline`(~187) 표시 헬퍼(`propsSummary`/`fmtEventTime` 등, ~211–228).

### `trace.js` (**462줄**) — 추적 리포트 (trace.html 엔트리)
- `runTrace`(~107, POST `/graph/trace`, seq 가드, 실패 시 기존 리포트 유지+토스트) → `renderReport`(~217, 라벨별 그룹 테이블 100행 청크 + event_time 타임라인 300건 청크, user provenance 강조, 구조 엣지 접이식) `initControls`(~407, 시드 칩·depth 즉시 재실행·시간범위 재실행 버튼) `init`(~429, URL `replaceState` 동기화).

### `trace_launch.js` (**111줄**) — index 「🕸️ 추적」 진입점
- export: `updateTraceEntryVisibility`(~26) `refreshTraceEntry`(~36, `GET /graph/mapping-summary`로 활성 판정) `openTraceForSelection`(~55, 선택 행→identity 조립 시드, 상한 20 토스트, 새 탭) `initTraceEntry`(~100).

### 보조 모듈
| 파일 | 책임 |
|---|---|
| `theme.js` (~92) | 라이트/다크 토큰 전환 — export `getTheme/applyTheme/toggleTheme/syncAgGridThemeClasses/initTheme` |
| `tokens.css` (**308**) | 디자인 토큰(색·타이포·간격) — 듀얼 테마 CSS 변수의 SSOT. 2026-07-25 다크 세트 심화(Ground L* 9.2, WCAG AA 유지). **[`a98dc72`] `#toast-container`가 하단 중앙 배너로 전환** — 우하단 고정이 맵 에디터 자재 목록을 가리던 문제와 그 회피 장치(`--toast-inset-right` 변수)를 함께 제거, 모션은 opacity 전용 |
| `style.css` (~1,848) | index 페이지 스타일 본체(맵 에디터와 공유). app-header는 `position:relative; z-index:200` — split-resizer(z:100) 위 스태킹 보장. **[`280ebf0`] `.glass-input` transition을 `all 0.3s`→`border-color/box-shadow 0.1s`로 국소화**(DOE 입력 랙의 2차 원인 — 토큰은 무변경) |
| `transfer_plan.css` (**832**) | 전사 계획 사이드바 스타일 — tokens.css 시맨틱 토큰만 사용(듀얼 테마 자동 대응). **[`b35bc9f`] zone 편집기용으로 전면 재작성**(826→593줄) — 그 재작성이 룰셋들을 떨어뜨렸고 두 번에 걸쳐 복원됐다: **[`280ebf0`]** `.overlay-box`/`.ov-*`, **[`a98dc72`]** `.map-breadcrumb`/`.bc-*`(~620–, 프레임 브레드크럼)·`.plock-chip`(페인트 잠금 상태 칩 — "확인 불가"는 보여야 한다) 원문 복원 + 50/50 패널 분할 주석 정정(`flex-basis: 0`이 근거). 마크업은 내내 그 클래스들을 쓰고 있었다 — **재작성이 CSS만 떨어뜨리는 패턴 2회째**. **[`0052d76`] `.main-layout{overflow-x:auto}`(~29)** — 에디터 행의 자연 최소폭 ≈1540px이 1366/1440 뷰포트에서 계획 사이드바를 **무스크롤바로 잘라내던** 문제: body `overflow:hidden` 규약(style.css)은 건드리지 않고 맵 에디터 페이지에서만(이 시트는 map_editor 경유 로드) 행 자체가 가로 스크롤. 토스트는 `position:fixed`라 보이는 뷰포트 중앙 유지 |
| `utils.js` (**347**, 337 → **+10**) | `getLocalTimeString`(~2) / **전역 토스트 재작성**(~29–174) / 🆕 **[`c3a5239`] `dismissToasts(dedupeKey)`(**~54** export — 지시형 토스트("Ctrl+V를 누르세요")는 그 지시가 참이 아니게 되는 순간 사라져야 한다. 안 그러면 **이미 실행된 동작을 반복하라고 말하고 있는 것**이다. 소비: `main.js`의 스마트 페이스트 해제·소비 경로 3곳)** / `getCleanFilename`(**~176**) / **[`269b39e`] 인제션 진행 카드 상한** — `MAX_VISIBLE_PROGRESS_CARDS=3`(**~197**)·`collapseProgressOverflow`(**~204**, 초과분은 숨기고 "…N건" 한 줄로 집계 — 숨은 카드도 계속 갱신되며 앞 카드가 끝나면 표면화)·`dismissProgressCard`(**~229**, 카드 제거 로직 단일화) / 진행 토스트 `showIngestionProgress`(**~247**)·`finishIngestionProgress`(**~308**). **토스트 규율(전 페이지 영향)**: 만료는 **벽시계 `expireAt`** 기준(`sweepToasts`가 `now >= expireAt` 비교 — 백그라운드 탭 `setTimeout` 스로틀링으로 무한 누적되던 원인 제거, 타이머는 스윕을 깨우는 힌트일 뿐) · 상한 `TOAST_MAX_VISIBLE=4`(~29)이고 퇴거는 **비-에러 오래된 것 우선**, 방금 삽입분은 `keep` 인자로 면제 · TTL `{info:5s, success:5s, warning:9s, error:15s}`(~30 — **에러 15초는 성공 알림에 밀려나지 않게 하는 의도적 예외**) · 스윕 트리거는 타이머 + `visibilitychange` + `window.focus` + 삽입 전후(~101–105) · `dedupeKey` 합치기는 **에러 제외**(건별 원인이 중요), 같은 키+타입이면 `count+=1`·만료 연장·`… · N건` 표기 · 본문은 `textContent`(HTML 해석 금지) |
| `dom.js` (~57) | DOM 참조 일원화 — `elements` 게터 객체(+`traceBtn`/`menuTrace`) |
| `config.js` (~5) | `API_BASE`/`CURRENT_USER`/`pageLimit` |
| `clipboard.js`·`counter.js` | counter.js는 Vite 템플릿 잔재(미사용) |

---

## 8. 주요 호출 흐름 요약

> 🔒 **[`90e284f`] 아래 흐름 중 `/internal/events/*`를 지나는 것(1·3·8)은 전부 `X-Admin-Token` 헤더를 실어 나른다** — 워커측은 `admin_auth.internal_event_headers()`, 서버측은 `Depends(require_admin_token)`. 토큰 미설정이면 양쪽 다 무동작이라 흐름이 종전과 동일하다. **토큰을 웹서버에만 설정하고 런처에 안 하면 워커의 브로드캐스트가 전부 401이 되어 WS 갱신이 조용히 멎는다**(데이터는 계속 들어가고 화면만 안 바뀐다).

1. **파일 인제션**: raws/ 투입 → (**[Tree Ingest `600b49d`] 폴더가 떨어지면** `on_created`/스윕 → `request_tree_ingest` → 트리 정온 대기 → **파일을 제자리(중첩 경로 그대로)에서** 아래 경로로 디스패치 → 비게 된 폴더만 `os.rmdir`) → `IngestionHandler._handle_event` → **[P1] `_route_and_process`**(임계 초과·backlog 잔여 → heavy 큐 / 인라인은 직렬화 락 try-acquire, 실패 시 큐 재라우팅) → `process_with_retry` → `_snapshot_table_context`(파일당 1회 config 스냅샷 — 테이블 해석은 글로벌 별칭 > 레거시 config.json > 폴더명) → `_resolve_rows`(파이프라인 우선 → std parser 폴백. **[Tree Ingest] `rel_path`=`relative_source_path`가 여기까지 따라가 `advanced_ingester.extract_path_metadata`의 subject가 된다** — 폴더명이 곧 `filename_rules`가 보는 문자열이다. 병합 서열은 **경로 < 헤더 < 행**(「파일이 정본」, [§3-bis](#3-bis-serverparsersadvanced_ingesterpy--선언-검증--경로-메타-추출))) → **[P2] `compute_file_signature` → `_try_dedup_skip`(동일 시그니처 `DONE`이면 skip+archive+`SKIPPED` 로그) → `_plan_checkpoint`(재개 오프셋 결정)** → `_send_to_upsert` → **`crud.apply_batch_updates` 직접 호출**(HTTP 아님, 청크마다 `record_chunk_progress`가 **같은 트랜잭션**에 동승) → `_finalize_checkpoint(mark_done)` → **[M3 `b697d34`] `MapMetaCollector.flush`**(적재 테이블이 `map_key_columns`를 선언하고 좌표 바인딩이 해석되면, 이 파일이 만든 **맵 키 중 메타 행이 없는 것만** `wafer_map_metadata`에 합성 등록 — 기존 행 무접촉, 실패는 로그만) → 웹서버 `/internal/events/batch-refresh|file-processed` → WS 브로드캐스트.
   - [P1] 진행 가시화(push-캐시-서빙): watcher `_notify_ingestion_state` → `run_watcher.trigger_ws_ingestion_state` → POST `/internal/events/ingestion-state` → `IngestionActivityRegistry`(+ 기존 progress/file-processed 인터셉트) → GET `/admin/file-ingestion/active` → admin File 탭 진행 섹션·재기동 경고. WS 이벤트 계약 무변경.
2. **수동 편집**: client `handleCellEdit`/`applyValueToSelectedRange` → **본문에 `effort: snapshot()` 동승**(아래 13) → PUT `/tables/{t}/data/updates` → `apply_batch_updates_endpoint` → `crud.apply_batch_updates` → outbox 발화 + WS `batch_row_upsert` → 전 클라이언트 `handleWebSocketMessage` 델타 반영. 응답의 `effort_recorded`가 true면 클라가 카운터를 비운다.
3. **체인 인제션**: `apply_batch_updates`의 outbox 발화 → NOTIFY → `start_chain_ingestion_worker` 루프 → `process_pending_groups` → `process_chain_transaction_group`(맵퍼 실행, 예: `map_enrichment_dedup`) → 파생 테이블 `apply_batch_updates`(source=chain_ingestion, 순환 차단) → **[M3] `MapMetaCollector`**(tx 그룹당 1회 부재 메타 등록 — 재귀는 등록기가 `wafer_map_metadata` 자신을 거부해 차단) → `_dispatch_broadcasts` → `/internal/events/broadcast`(created_logs 500건 절단 + `total_log_count` 실건수) → WS.
4. **조회**: client `fetchData` → GET `/tables/{t}/data` → `get_table_data` → `get_column_filter_condition` + `fetch_and_merge_metadata`(셀 객체 병합) → client `ensureCellObject` 정규화 → AG-Grid.
5. **레이어링 조작**: 소스 모달/Pin → `/tables/{t}/cells/*` 라우트 → `crud.delete_cell_source_batch`/`set_cell_manual_priority_batch` → `compute_priority_value` 재계산 → WS 반영.
6. **설정 핫리로드**: 어드민 `reloadSystemConfigs` → POST `/admin/reload-configs` → 웹서버 `reload_local_process_cache` → `models.refresh_dynamic_models(engine)`(싱글턴·ORM·**신규 테이블 물리 CREATE** — 1차 DDL 소유자, outbox 발화보다 선행) → SYSTEM_RELOAD outbox → 워커들 `reload_worker_process_cache` + `refresh_dynamic_models`(게이트+checkfirst로 무해한 보충 안전망). 직접 파일 편집 시엔 `config_watcher`가 동일 CREATE 수행. graph 워커도 배치 내 SYSTEM_RELOAD 감지로 매핑·테이블 리로드(이슈 #8 해소).
7. **맵 에디터**: (부트 시 **[`280ebf0`] `restoreLastOpenMap`**이 `map_editor_last_open` localStorage를 읽어 **수동 LOAD 경로 그대로** 마지막 맵을 재오픈) → `loadExistingMap`(**[`6db517d` H1] 로드 시점에 초안을 덮어쓰지 않는다** — 초안 우선순위 판정 후 1회만 저장) → GET `/tables/{t}/data`(REST) → 편집 → `pushMapData`(**[gate4 `deed6d2`] 적재 대상이 로그형(맵 계약 밖 데이터 컬럼 보유)이면 모든 다이얼로그보다 앞에서 거부** — `/schema`의 site 선언 `map_push_ok: true`가 있을 때만 1회 손실 인지 confirm으로 강등. **[`6db517d` H2] 프레임이 화면의 비어 있지 않은 셀을 전부 못 담으면 confirm 전에 거부** — replace_map 절단 방지) → PUT `/data/updates`(**[gate4] 서버는 purge 스코프 유도 불가 시 400으로 거부하고, 응답 `scope: {filters, deleted, inserted}`로 실제 지운 범위를 되비춘다** — 침묵 noop 폐지). 🆕 **[`019140c`] 📐 표준 로드는 이제 데이터의 원점을 프레임에 **선언**한다**(`startX = minX`) — 셀에서 `minX`를 빼던 종전 코드는 삭제됐다. 두 줄은 한 양이라 화면은 하나도 안 움직이고, 바뀌는 것은 **화면이 말하는 좌표 = Push가 쓰는 좌표 = 저장된 좌표**가 됐다는 것뿐이다(실측: 메타 없는 맵 4개, 1,923셀 중 451셀이 밀린 좌표로 Push까지 갔다). 🆕 **[`02a72c6`] 프리셋은 규격만 기입하고 회전·면은 건드리지 않는다** — 저장된 프리셋이 전부 rot 0/front를 선언하므로 종전엔 **아무 프리셋 적용이나** 회전·뒷면 맵의 좌표를 통째로 재번호했고(표본: 187 중 173) 대비 관문은 격자·원을 떠난 셀이 0이라 아무 말도 하지 않았다. 지금은 선언을 **읽고 적용하지 않으며 info 토스트로 그 사실을 말한다**. 프리셋은 `/map-presets` CRUD. 페인트 잠금은 기동 시 GET `/api/maps/paint-rules` → `applyPaintLockConfig` → 전 편집 경로가 `isProtectedFCell` 단일 관문 통과 — **[U6 `95bf072`] 같은 응답이 `value_column_candidates`·`default_legend`를, [F1 `17f65bd`] `binding`(서버 해석 좌표 바인딩)을 나른다**(`overlayContract`·`servedBindingCache` 캐시 → 드롭다운 preselect·빈 맵 시드·자동 추가 값 색. 클라 사본 0). (WS 미사용)
   - **[7d931dc] 오버레이(맵 인프라 — 계획 전용 아님) — 변환은 클라 단일 구현**: `handleAddOverlayClick`/`addOverlayForSource` → `addOverlayLayer` → ① `fetchServedBinding(src)`(**[F1] paint-rules `binding` — 클라 유도 없음**, null이면 `binding_unavailable`+선언 안내) → ②③ GET `/tables/{src}/data`(**원본 좌표**) + `wafer_map_metadata` 소스/타깃 2건 병렬 → ④ `frameFromMeta`로 프레임 확정(부재 시 현재 화면 = identity 폴백) → ⑤ `cols×rows` 관문 → ⑥ `projectCellsToPhys`(소스 프레임 → 물리 키) → 캔버스 마커. 화면 규격이 바뀌면 `syncOverlayGeometry`가 `rawCells`에서 재투영. `importOverlayToGrid`만 `gridData`로 넘어온다(서버 쓰기 없음).
     - ⚠️ **구 선행 단계였던 GET `/api/maps/overlay?…&limit=1`(보정 **선언** 관문 `probeAlignDeclaration`)은 삭제됐다**(2026-07-27) — 서버 선언 레이어가 없어져 물어볼 대상이 사라졌다. 오버레이 추가 경로에서 이 엔드포인트를 호출하는 코드를 보면 그것은 되살아난 것이 아니라 **오류**다.
     - **서버 경로는 삭제되지 않았다** — `map_overlay.get_overlay`(`resolve_map_transform` + `make_frame_transform` + `_frame_phys_params`)는 엔드포인트에서 그대로 살아 있고 `test_map_overlay.py`가 계약을 지킨다. 바뀐 것은 **맵 에디터가 그 좌표를 소비하지 않는다**는 것뿐이다. 2026-07-27부터 `bonding_plan.py`·`transfer_plan.py`의 **가용량 산출이 이 서버 구현을 소비**한다(자체 사본은 삭제) — 서버 구현은 하나뿐이다.
   - **[zone 모델 `b35bc9f`] 전사 계획(계획 = 그 맵 자체, DOE = legend 행)**: 맵 로드(`loadExistingMap`) → `readRegistryScope`가 GET `/tables/map_split_registry/data`를 **map_key 필터로** 읽고(`REGISTRY_SCOPES=['map']` — 테이블 전체 어휘 시드는 `269b39e` 결함으로 삭제, 행이 없으면 `seedEmptyDoe` — **[U6] 서빙된 `default_legend` \| 빈 DOE 1행**) `applyRegistryRowsToLegend` + `legendReplaceScope{table, mapKey, fingerprint}` 확립 → `notifyMapContext` → `transfer_plan.js`가 `stage_of_table` 역인덱스로 stage 유도 → GET `/api/transfer-plan/{stages,source-summary}` → 패널에서 STACK·1H/MID/TOP·자재 편집 → `commitRow` → `controller.updateLegendRow` → **`scheduleCellDraft`(로컬 초안만 — 자동 서버 저장 없음)** → 사용자가 **⚡ Push**(`pushMapData`) → `saveLegendToServer` → **PUT `/tables/map_split_registry/data/updates` with `replace_map: true`**(맵 하나의 **값 전체 집합 1회 쓰기** — 지운 값·구역·자재는 집합에 없다는 것만으로 삭제된다. 별도 삭제 단계 없음).
     - ⚠️ **구 `PUT /tables/map_doe|map_doe_source/data/updates`는 클라의 쓰기 경로가 아니다** — 두 테이블은 `0f8d35f`에서 폐기됐고 `transfer_plan.js`에는 **저장 코드 자체가 없다**. 이 경로를 호출하는 코드를 보면 되살아난 것이 아니라 **오류**다.
     - 쓰기를 막는 장치: **권한**(`legendReplaceScope` — 이 맵의 행에서 온 legend만 그 행을 대체할 수 있고, 페이로드 단계에서 `reconcileVocabClaims`가 미변조 플레이스홀더를 걸러낸다 — `contracts/legend_map_scope`가 이 경로를 끝까지 돌려 검사) · **절단**(부분 읽기는 읽은 게 아니라 `throw` — 미확인 화면에서의 upsert는 못 본 계획을 덮는다) · **동시성**(쓰기 직전 재조회 → 지문 불일치면 `legendConflict`로 **거부**) · **스키마**(`probeZoneColumns` — 물리 zone 컬럼이 없으면 거부: crud가 zone을 떨어뜨린 replace_map은 계획을 층 구조 없이 대체한다).
     - **[M3 `b697d34`] `wafer_map_metadata` 행의 출처가 둘이 됐다** — ① 사람: 맵 에디터 ⚡ Push ② 기계: 인제션(파일 워처·체인 워커)의 `MapMetaCollector`가 **부재분만** 합성 등록. ②는 마스크 중립 최소 규격이고 `source="auto_map_meta"`(서열 99)라, 나중에 사람이 등록/수정하면 언제나 그쪽이 이긴다. 오버레이·가용량의 정렬 근거가 여전히 **메타 하나**라는 계약은 바뀌지 않았다 — 바뀐 것은 **메타가 비어 있는 맵의 수**다([§5 `map_meta_registrar.py`](#5-소형-서버-모듈)).
     - **[M4 phase 1+2] 유효 다이의 근거가 둘이 됐다** — 맵 메타에 `valid_die_ref`가 선언돼 있으면 **참조된 맵**이 근거이고, 없으면 종전 그대로 **원 기하**다(`isValidDieAt`이 인자로 받은 원 판정을 그대로 돌려준다 — 가산적 공존). 선언이 있는데 못 풀면 `refused`이고 **원으로 되돌아가지 않는다**. 서버 짝은 `map_overlay.resolve_valid_die_basis`/`resolve_valid_die_set`이며 양쪽은 `contracts/map_seam`의 M4 계열로 채점된다.
       - ✅ **phase 2가 착지했다(2026-07-30)** — 구 문장 "phase 2는 아직 착지하지 않았다"는 **틀렸다**. 쓰기 절반은 클라 `applyValidDieRef`·`validDieRefPayload`·`enterValidDieAuthoring`, 서버 `map_overlay.apply_valid_die_ref`(~1016)이고 **1홉 제한**은 `valid_die_chain_error`(~1066)/클라 `validDieChainError`(~2316)가 판정한다 — 참조된 맵이 자기 `valid_die_ref`를 또 가지면 거부한다(안 막으면 조용히 **중간 맵의 저장 셀**로 해석되고 그건 운영자가 선언한 집합이 아니다). 계약도 `valid_die_authoring_cases`(14)·`valid_die_chain_cases`(14)·`valid_die_push_decision_cases`(11)로 착지해 `pending` 심볼이 **0개**다.
       - 🔴 **쓰기가 위험한 이유가 이 흐름의 요점이다**: 메타 객체는 Push마다 **화면 컨트롤에서 재조립**되므로 **컨트롤이 없는 선언은 저장 한 번에 파괴된다.** phase 1은 passthrough 한 줄로 덮어 뒀고, phase 2가 필드에 컨트롤을 주는 순간 그 파괴 경로가 UI로 **도달 가능**해졌다.
     - 🪦 **[F8 `61440e6`+`94b9baa`] 유효 다이 지정은 이제 아무것도 채택하지 않는다 — 채택 기계장치 8종이 삭제됐다.** 사용자 결정 2026-07-30 「그리드 크기가 달라도 좌표는 db값 그대로 보존하고 화면 표기 밀리게 그냥 보여주기」. 흐름에서 **분기 하나만 남았다**: 참조 프레임이 이 격자와 정렬되지 않으면 지정이 성립한 **뒤에** `console.info` 1줄 + 토스트 1회로 "마스크가 밀려 보인다, 좌표는 하나도 바뀌지 않았다"를 말한다. 서버 쓰기 0, 좌표 변경 0, 행 삭제 0.
       - 🆕 **[`da8f390`] 그 위에 세 가지가 더해졌다**(자세히는 [§7](#7-client2src--웹-클라이언트)): ① **좌표계의 원점 상자가 원 기하가 아니라 유효 다이 영역에서 나온다** — `getWaferBoundingBox`가 마스크 상자를 함께 누적하고, 그래서 `start_x/start_y`가 **모든 회전·면·Y반전에서** 마스크의 최소 열·행이다 ② `resolveValidDie`가 **화면에 이미 앉아 있는 셀을 자기 저장 좌표가 가리키는 칸으로 다시 앉힌다**(로드 경로는 셀이 아직 없어 무비용) ③ 정렬 경보의 축이 **원점**이다. **⚡ Push가 쓰는 x/y는 여전히 「화면이 말하는 좌표」이고, 이 라운드는 그 좌표가 회전마다 달라지던 것을 고쳤다.**
       - 🆕 **[2026-07-31 `35e84c3`+`4761a3a`] 그 흐름이 다시 세 군데 바뀌었다**(전부 [§7](#7-client2src--웹-클라이언트)): ① **좌표 함수 4개가 개명됐다** — 흐름 서술에 옛 이름이 남아 있으면 그것은 이제 **없는 함수**를 가리킨다([§0 ⑪](#0-묘비-목록--소스에-존재하지-않는-이름)) ② **물리 키의 원점이 격자 중심에서 웨이퍼 중심으로 옮겨져** 참조 맵의 마스크 재중심화(`shiftX/shiftY`)가 **필요 없어졌고 삭제됐다**(실측: 평행이동이 262칸 중 21칸을 틀린 다이에 앉혔다) ③ **「원점 상자가 셀 밑에서 움직였다」에 대한 반응이 `reseatCellsToStoredCoords` 하나로 통합**돼, **기하 프리셋 편집·물리 규격 한 칸 수정·유효 다이 지정이 전부 같은 함수를 탄다.** 사용자 확정 2026-07-31: 유효 다이 선언이 없는 맵에서 유효 다이 영역은 곧 웨이퍼 원이므로 **그 셋은 닮은 연산이 아니라 같은 연산**이다.
       - 🔴 **왜 채택 자체가 답이 아니었나** — DB의 x/y는 **Push 시점에** 현재 프레임이 유도한다(`gridData`는 `물리 키 → 값`뿐이다). 치수를 채택하면 **같은 칸이 다른 좌표를 낳고**, 그러면 새 프레임이 만들지 못하는 좌표 앞에서 셀을 **버리거나 번호를 다시 매기는** 수밖에 없다. `ae2811c`는 그것을 **거부**로 막았고, `7873070`은 **재배치**로 바꿨고, `94b9baa`는 **행위를 지웠다**. 기계장치가 0줄이 되는 답이 세 번째에 나왔다.
       - 마스크는 무관하게 옳다 — 마스크 키는 `projectCellsToPhys(cells, refFrame)`이 **참조 자신의 프레임**으로 만들고 화면 컨트롤을 읽지 않는다. **[H5]** 참조 치수는 여전히 `frameDimError`가 1~100 정수로 가두고, 그 가드의 근거는 `61440e6`에서 "채택 비용"에서 **"`projectCellsToPhys`가 여는 프레임 창의 `visualCols × visualRows` 순회 비용 + 0/음수/비정수 거부"**로 교체됐다([§7 H5](#7-client2src--웹-클라이언트)).
     - **[F5c `50bddda`] 저장된 메타가 없는 맵은 기본 규격을 라우팅받는다** — `loadExistingMap`이 `!loadedGridMeta`일 때만 GET `/api/maps/preset-routing` → `map_preset_routing.resolve_preset_routing` → `applyRoutedPreset`. 순서 **메타 > 라우팅 > 패널**이 서버에 박혀 있어(메타가 있으면 `meta_present`로 프리셋 **없이** 답한다) 라우팅이 등록된 규격을 덮을 구조적 방법이 없다. 답 못 하면 **아무것도 적용하지 않는다** — 틀린 규격은 `inside`를 바꾸고 그것이 저장 가능한 셀 집합을 바꾼다.
     - **[F1ⓑ `c9bf2c7`] 회사 시트 왕복**: 📋 Copy(헤더 모드) → 운영자가 엑셀에서 편집 → Ctrl+V → document 레벨 `onMapGridPaste` → `readCompanyMapBlock`(순수) → `checkPasteAgainstFrame`(순수) → confirm 1회 → `applyPastedGridRows`+`applyPastedAuxRows` → `scheduleCellDraft`. **서버 쓰기 0**. 거부 6종 중 마지막이 **[P0-2] 지문 부재**다 — 노치 `D`의 화면 위치가 (회전, 면, bbox)의 함수라서 **치수를 보존하는 프레임 변경**(0↔180, front↔back)을 잡는 **유일한** 신호이고, 다른 관문은 전부 개수만 비교하는데 그 개수는 그런 변경에서 동일하다. ⚠️ **역량 비용이 있다**: 선언된 179맵 중 노치가 격자 안인 것은 **27개**뿐이라 나머지 152개에서는 왕복이 **불가**하다(포맷 후속 라운드 대기).
     - **[7b `91386f0`] 맵 키는 선언된 컬럼 타입으로 캐노니컬화된다** — 서버 `map_overlay.canonical_map_key`, 클라 `map_editor.canonicalMapKey`. `slot`이 number 선언이면 `'01'`과 `1`이 **같은 맵**이고, string이면 **다른 맵**이다. 판정 근거는 값이 아니라 `table_config`다.
     - 검증은 GET `/api/transfer-plan/validate?ref_table=&map_key=` → `status: ok|warnings|unverified`. 수량은 **저장에서 읽지 않고** `painted × zone_layers`로 유도된다. **[7c] `transfer_log: "none"` 선언 사이트**에서는 소모 기록이 없다는 것이 **사실로 취급**되어 강등이 아니라 `connected(untracked)` + `remaining_upper_bound`(≤N)로 나간다 — `null`이나 키 삭제는 종전대로 `missing`이다. V1–V6 차단 규칙은 서버 `validate_zone_plan` ↔ 클라 `doe_bands.validateZonePlan`이 공유 벡터(`contracts/doe_band_rules`)로 고정(**STACK 0 = marker**: 구역·수요·롤업 없음, V6만 답한다 — `2baf9ff` U9).
     - ⚠️ **배포 순서 위험(`0f8d35f` 기록, zone 컬럼에도 동일)**: `stack`·`mat_*` 컬럼은 `install_product_tables.py --apply`로 라이브 `table_config`에 선언되고 config 워처가 재기동 없이 ALTER를 적용하지만, **웹서버는 코드를 다시 읽으려면 재기동이 필요**하다 — 그전까지 `validate`는 404다. config를 먼저 바꿨으므로 **코드만 되돌려서는 복구되지 않는다.**
8. **그래프 자동 승격**: `apply_batch_updates`의 outbox 발화 → `run_graph_materializer_loop`(keyset 커서) → `materialize_events` → `attach_col_sources`(provenance=식별 컬럼 winner 최저 서열) → `extract_graph_items` → 노드/엣지 UPSERT + `_retarget_stale_edges` → 커서 전진. 백필은 POST `/api/graph/sync` → `execute_manual_sync` → `resync_table`.
    - 🔴 **[`530fdfd`] resync는 이제 자기 자신을 알린다** — `execute_manual_sync`는 호출마다 매핑을 **디스크에서** 다시 읽는데 materializer 루프는 **인메모리 사본**을 `SYSTEM_RELOAD` 이벤트에서만 교체한다(이슈 #8). 그래서 "매핑 편집 후 resync"는 둘을 어긋난 채 뒀다 — resync는 **새** 선언으로 쓰고 루프는 들어오는 행을 **옛** 선언으로 승격했다(라이브 40분, 이미 파일에서 사라진 타입의 엣지가 그 뒤로 생성됐다). 이제 `_announce` → **`publish_system_reload`**(outbox 1행 + **같은 트랜잭션 안** NOTIFY)가 `/admin/reload-configs`와 같은 레버로 수렴시킨다.
    - 🔴 **[`530fdfd`] 그리고 누출된 노드를 쓸어낸다** — `_retarget_stale_edges`가 **엣지만** 지우고 남은 노드는 아무것도 지우지 않으므로 **정체성을 바꾸는 셀 편집마다 노드가 누출**됐다(라이브 실측: 차수 0 노드 **12,761개**). 스케줄러가 `MultiDiscoveryScheduler.maybe_sweep_graph_orphans`(30분 스로틀 → `due()` 일 1회)로 `graph_orphans.run_scheduled`를 부른다. 고아 = **엣지 0개 AND 현 매핑이 생산 불가**(차수 0 단독은 `SplitCondition` 같은 정상 저차수 라벨을 지운다). 라벨별 예산 관문(모집단 절반 초과 손실은 `declined`)·깨끗한 선언 전제(`rejections` 있으면 전체 거부)·`GRAPH_ORPHAN_SWEEP_ENABLED` 스위치. [§5-A](#5-a-2026-07-30-신설-서버-모듈-8종)
8-bis. **[2026-07-30] 인리치먼트 ① 자동확정 + 체인 재생 R1/R2 — ⚠️ 쓰기 표면은 여전히 CLI뿐이고, 측정 표면만 어드민에 생겼다**: 체인 워커가 파생 테이블에 쓴 **직후**(`process_chain_transaction_group` 안 **~487**) `AutoConfirmCollector`가 그 작업 단위의 decision_key들을 걷어 `resolve_target_candidate`로 **선언된 참조 뷰가 후보를 정확히 1개 남기는가**를 묻고, 그럴 때만 **`enrichment_auto_confirm`**(서열 미등재 = 99) 소스로 쓴다. 관문 넷: 전역 킬 스위치 · 규칙별 opt-in(**기본 OFF**) · `candidate_for` 선언 · **부재 전용**(타깃 셀에 provenance가 하나라도 있으면 차단). 체인 쓰기는 훅이 돌기 전에 이미 커밋돼 있다(`server/database/crud.py`의 `apply_batch_updates` 말미 `db.commit()`).
    - 🔴 **[F9 `f3fd785`] 판정의 실행 형태가 바뀌었다 — 시그니처는 그대로다.** `resolve_target_candidate`는 이제 `enrichment_config.execute_candidate_probe`(뷰 결과 **전체**에 GROUP BY)로 후보를 세고, 사람에게 보여줄 **표시** 경로만 뷰의 행 상한 래핑(`execute_reference_view`)을 유지한다. **한 선언, 두 실행 형태.** 종전처럼 서버가 자른 행 위에서 파이썬이 distinct를 세면 `ambiguous`가 그 경계 너머에서 **도달 불가**가 된다(라이브 실측: `limit: 50` 뷰에 키당 69–217행 → 80/80 키가 초과).
    - 🆕 **[`f9289f6`] 그 위에 두 가지가 고쳐졌다.** ① **절단 둘이 나란한 이름 있는 거절이 됐다** — `probe_truncated`(행 절단)와 **`distinct_truncated`(그룹 절단)**. 후자를 "어차피 2개 이상이니 `ambiguous`가 잡는다"로 흘려보내던 것이 틀렸다: 호출자가 `clean_str_value`로 값을 **접으므로** 잘린 결과가 1개로 접혀 `single`이 될 수 있다(실증: `[('WF01',1),('WF01 ',1)]` → `{WF01}` → `single`, 잘려나간 곳에 WF02). ② **사용자 SQL 실행이 SAVEPOINT 안으로 들어갔다**(`enrichment_config._isolated_execute`) — 예외를 **잡는 것**은 봉쇄가 아니다. PG에서 실패한 문장은 트랜잭션을 abort시키고 그 뒤의 `COMMIT`은 **정상 반환하면서 롤백된다.** 그래서 ⓐ `candidate_column_missing` 진단이 PG에서 도달 불가였고 ⓑ 오염된 세션이 워커의 `except`를 탈출해 `processed_chain=True` 커밋을 롤백시켜 **그룹이 영원히 재생**됐다.
8-quater. **[F9 `f3fd785`] 「내 config가 먹었는가」 — `POST /admin/reload-configs`가 남긴 공백을 두 라우트가 메운다**: 운영자가 어드민에서 ① **`GET /admin/config/resolve`** → `config_resolve_report.resolve_report()` → 도메인마다 `_RESOLVERS`의 등록기(현재 `enrichment` 하나) → **config만 읽고 DB는 건드리지 않는다** → `{domains: [{sources, settings, effective, ineffective, rejected, counts}], vocabulary}`. ② **`GET /admin/enrichment/auto-confirm/dry-run?rule=`** → `enrichment_analysis.run_auto_confirm_sweep(apply=False, ignore_knob=True)` → 큐 표본(기본 200, 최대 2000)에 대해 「몇 건이 사람 없이 확정 가능한가」 → **쓰기 0, 끝에서 구조적 rollback**.
    - 🔴 **사유는 닫힌 어휘 4종**(`not_declared`·`mapping_unavailable`·`scope_unresolved`·`not_reached`)이고 **런타임 열화 어휘(`/graph/chip-trace`)를 그대로 재사용**한다 — 같은 구분이 config 로드 시점으로 한 층 올라온 것뿐이다. 드라이런이 측정 불가일 때도 **같은 단어**(`refused_reason: "not_declared"`)로 200을 준다: 클라가 두 표면에서 같은 어휘를 읽는다.
    - 🔴 **사람이 읽을 문장은 전부 서버가 만들고 클라는 `detail`을 그대로 렌더한다.** `contracts/config_resolve_report/client_harness.mjs`가 `client2/src`에서 그 4단어를 **소스 리터럴로** 찾아 하나라도 있으면 divergence로 신고한다(INV-F9-7) — 렌더러가 없는 지금도 채점되는 상설 금지이고, U6가 6개를 삭제한 하드코딩 사본 계급의 재발 방지다.
    - **이 라운드가 실제로 드러낸 상태**: 라이브에서 `auto_confirm: true`가 `candidate_for` 선언 **0건**으로 켜져 있었고, 그 사실의 유일한 목격자는 데몬 로그 한 줄이었다 — 보고서는 그것을 `ineffective` + `not_declared`로 **이름을 대며** 답한다.
8-quinquies. **[`c3a5239`] 스마트 페이스트 — 평문 HTTP에서 클립보드를 읽는 유일한 경로**: `Ctrl+Shift+V`(또는 메뉴/버튼) → `armSmartPaste`가 `state.smartPasteArmedUntil`/`ArmedTable`을 세운다 → 네이티브 `paste` 이벤트 → `clipboard.js`의 **단일** `paste` 리스너가 래치를 보고 **즉시 소비한 뒤** `main.js`의 `smartPasteFromPasteEvent(e)`로 넘긴다 → `e.clipboardData`에서 이미지/텍스트를 꺼내 인제션 업로드. 🔴 **`navigator.clipboard`는 프로덕션(비보안 컨텍스트)에서 `undefined`이고 `execCommand('paste')`는 차단**이라, 버튼 클릭이 만들어낼 수 없는 것이 **바로 그 이벤트**다 — 그래서 버튼은 "읽기"가 아니라 **"다음 붙여넣기 예약"**이 됐다. 무장 후 600ms 안에 `paste`가 안 오면 15초 무장으로 승격하고 `Ctrl+V`를 안내하며, **Esc가 취소**하고 **테이블이 바뀌었으면 도착한 붙여넣기를 거부**한다(이 경로는 인제션이라 엉뚱한 테이블은 데이터 오류다). 안내 토스트는 `utils.dismissToasts(dedupeKey)`로 **지시가 참이 아니게 되는 순간 사라진다**.
    - **철회 경로(R2)**: `chain_replay.withdraw_source` → 셀별 `cell_sources` 1행 삭제 → **생존자로 `crud.compute_priority_value` 재실행** → 드러난 값을 컬럼에 기록 + 철회 소스를 이름으로 감사 로그. `PROTECTED_SOURCES={"user"}`는 raise, 사람이 Pin한 셀은 skip. ⚠️ **철회는 이전 상태로의 복귀가 아니다** — 셀에 provenance가 남아 있을 수 있고 그러면 `cell_has_provenance` 관문이 재확정을 계속 막는다.
    - **소급 재적용(R1)**: `chain_replay.replay_rule`이 실제 맵퍼와 실제 쓰기 경로(`crud.apply_batch_updates`)에 먹인다. 루프 가드 3층 — 자기 트리거 규칙에는 `max_row_id` 스냅샷 · `replay_all`은 규칙당 정확히 1회 · 워커의 source-name 필터. **공백은 절대 쓰지 않고**(`SKIP_BLANK`) R2 후보로 보고한다.
    - **도달 경로는 전부 CLI다** — `server/scripts/enrichment_insights.py`(classify/propose/confirm) · `server/scripts/chain_replay_cli.py`(replay/replay-all/withdraw/list) · `server/scripts/backfill_enrichment.py`. **`main.py`는 이 넷을 import하지 않는다.**
8-ter. **[F3 `4e8e867` 서버 → `77a2c15`+`847ceaf`+`e14b1d0`+`d5f75a8` 클라] 입력 제안 (유일값 조회)**: AG-Grid의 `string` 컬럼 셀 편집 진입 → **`client2/src/value_suggest.js`의 `SuggestCellEditor`**(배선은 `grid.js`의 `buildColumnDefs` ~323) → 90ms 트레일링 디바운스 → **프리픽스 1자 이상일 때만**(빈 프리픽스는 클라가 거부한다 — 첫 후보가 임의값이 되면 "Enter가 옳다"가 "Enter가 동전 던지기"가 된다) GET `/tables/{t}/columns/{c}/values?prefix=&limit=12` → `value_suggest.suggest_values` → **loose index scan**(값 1개당 인덱스 시크 1회, `DISTINCT` 아님)으로 `idx_suggest_*`(`(lower(col) COLLATE "C", col COLLATE "C")`)를 걷는다. **`STOP_BUDGET`은 절단(값 유지 + `truncated`)이고 `STOP_DEADLINE`은 정직한 부재(값 없음 + `unavailable_reason`)** — 시간이 다한 것은 프리픽스 인덱스 부재의 모양이고, 살아남은 값들은 "짧지만 완전한 목록"으로 읽히기 때문이다. 같은 술어(`prefix_conditions`+`db_fold`)를 `/graph/nodes/search`가 쓰며 그 교체로 **`_escape_like_term`이 삭제**됐다([§0](#0-묘비-목록--소스에-존재하지-않는-이름)).
    - 🔴 **한 번의 Enter가 수락이자 커밋이다 — 그것이 이 기능의 수용 기준이다.** 전타 비용 `N`키 vs 제안 `P + 1`키이므로 수락과 커밋이 두 번이면 `P + 2`가 되어 **매 사용이 +1을 물고 짧은 값은 퇴행한다**. 성립 근거는 프레임워크 순서다: AG-Grid의 `processCellKeyboardEvent`가 `colDef.suppressKeyboardEvent`를 `cellCtrl.onKeyDown`**보다 먼저** 보므로, `grid.js`의 훅이 `handleEditorKey`를 불러 후보를 input에 **동기로** 써 넣은 뒤 `'accepted'`(=`false`)를 돌려주면 **같은 이벤트**가 `stopEditing → getValue()`로 그 값을 커밋한다. 타이머도 마이크로태스크도 개입하지 않는다.
    - **요청 상한은 12**(`REQUEST_LIMIT`)이고 이유가 둘이다: k번째 후보에 닿는 비용이 k키라 **N−1 이후 후보는 원리적으로 무의미**하고, 실측 `t = 0.84ms + 0.61ms × (limit+1)`에서 limit 20은 중앙값 15.3ms·limit 12는 8.7ms다(꼬리 p95는 약 11.8ms로 **예산 밖이며 그 사실도 함께 선언한다**).
    - **거절은 조용하다.** 4xx(미선언·datetime·프리픽스 미달)든 `unavailable_reason`(인덱스 부재/INVALID·타임아웃)이든 에디터는 **평범한 텍스트 에디터처럼 행동한다** — 목록도 토스트도 에러도 없다. 다만 학습에는 만료가 붙는다: 4xx 래치는 `LEARNED_TTL_MS`(60초), `unavailable_reason`은 **`UNAVAILABLE_COOLDOWN_MS`(15초) 부하 차단기**(이 경로만이 anyio 워커 스레드 + 풀 커넥션을 점유한다 — 무백오프였을 때 타이피스트 3명이 `pool_size=20, max_overflow=10`을 고갈시킬 수 있었고 증상은 **무관한 요청의 `pool_timeout`**이라 아무것도 여기를 가리키지 않았다). `api.loadSchema`가 매 스키마 재조회마다 `resetSuggestLearning()`으로 전부 비운다 — `table_config`가 핫리로드라 만료만으로는 이미 열린 탭이 최대 1분 뒤처진다.
    - **Escape는 한 가지만 뜻한다**: 제안이 engaged된 셀에서 첫 Escape = **목록만 물림**(친 글자 유지), 두 번째 또는 engaged된 적 없는 셀 = AG-Grid의 편집 취소. 판정 술어 `suggestionsEngaged`는 **조작자의 타이핑이 세우고 어떤 응답도 내리지 못한다** — 종전 술어 `listOpen`은 `DEBOUNCE_MS` + 왕복시간의 함수라 **같은 키가 정반대 결과**(글자 유지 vs 폐기)를 냈고 화면에 구분할 것이 없었다.
    - 계약 하니스는 **`client2/tests/value_suggest_keys_harness.mjs`(1,901줄)**이고 `npm run check:suggest-keys`로 **`prebuild`에 배선돼 있다** — `client2/tests/` 밑에서 유일하다([§6-2](#6-2-교차-구현-계약-contracts)).
9. **그래프 조회/추적**: index 그리드 선택 → `openTraceForSelection`(`composeIdentity` 시드) → `trace.html` `runTrace` → POST `/graph/trace`(`_expand_graph_subgraph` 공용 BFS) → 그룹+타임라인 렌더. 뷰어는 `graph.html` `explore` → GET `/graph/neighbors`. 양방향 크로스링크(`?label=&identity=`).
10. **[`8117456`] 감독 + 헬스 (프로세스 생존 ≠ 진척)**: `run_decoupled_app.main()` → `ChildSpec(…, heartbeat=)` 5종 → `Supervisor.start_all()` → `Supervisor.run()` 폴 루프 → 자식 종료 감지 시 `_register_failure`(백오프 재기동, 예산 초과 시 `FAILED` 영구 정지) → `write_status()`가 `config/supervisor_status.json` 갱신.
    - 병렬로 각 워커가 **자기 루프 안에서** `heartbeat.beat(name)` → `config/worker_heartbeats/<name>.json` 원자적 replace.
    - GET `/health` → `heartbeat.read_all()` + `process_supervisor.read_status()` + DB/outbox 프로브 → **`health.compute_health`(순수 함수)** → `{status, problems[], checks{database,workers,outbox,supervisor,config_backup}}` + unhealthy면 **503**. 워커 판정은 두 신호의 조인이므로 `down`/`wedged`/`starting`/`foreign_beat`/`ok`를 구분해 이름 붙일 수 있다. **[`b35bc9f`] `config_backup` 검사는 compute_health 내부에서 `probe_config_backups`(60초 캐시)로 채워지며 `missing`/`stale`/`unknown` → degraded, 절대 503 아님.**
11. **[`4ba13ae`] 격리 개발환경**: `devenv.py bootstrap`(config·워크스페이스 **구조만** 복제) → `snapshot_db.py`(라이브 → QA DB, 읽기 전용 소스·1000행 청크) → `devenv.py up`이 `ASSY_DATA_ROOT=<repo>/dev_env` + QA DB URL로 프로세스 기동(API :8081, graph :8091) → 모든 모듈이 `paths.py`를 통해 격리 트리를 읽고 쓴다. 워처만은 `iso_watcher.py` 게이트를 지나며, **정적(경로)·라이브(실접속 DB 이름·포트) 단언에 하나라도 걸리면 기동을 거부**한다(exit 9). 드릴 전후 비교는 `manifest.py capture|diff`.
12. **[`90e284f`] 어드민 접근 (공유 비밀 1개 — 로그인 아님)**: 운영자가 `ASSY_ADMIN_TOKEN`을 **런처 프로세스 환경에** 설정 → `run_decoupled_app.main()` → `process_supervisor`가 자식 env를 `os.environ.copy()`로 상속 → 5자식 전부가 같은 토큰을 본다.
    - **기동**: `main.startup_event` → `admin_auth.startup_banner()` 1회 로깅(설정=info / 미설정=warning **무엇이 멈추는지 명시** / 비-ASCII=error **잠긴 줄 알고 있는 상태라 가장 시끄럽다**).
    - **사람 경로**: 브라우저가 `/admin`(게이트 없음 — 페이지가 떠야 물어볼 수 있다) → `admin.js`의 `adminFetch`가 저장 토큰을 `X-Admin-Token`으로 첨부 → 게이트 거부(401/403 + `WWW-Authenticate`)면 `askForAdminToken` 1회 → **한 번만** 재시도. 503이면 프롬프트가 아니라 **서버 본문을 그대로 토스트**(토큰 미설정 + 코드 실행 라우트).
    - **워커 경로**: 워처·체인·그래프 워커가 `admin_auth.internal_event_headers()`를 `/internal/events/*` POST에 붙인다.
    - **거부 지점 3종**: 미설정+strict → **503** · 설정+헤더없음 → **401** · 설정+불일치 → **403**(constant-time 비교, 세 detail 모두 상수 문자열).
    - **이 흐름과 무관하게 항상 열려 있는 것**: `/health`(외부 모니터) · `/admin`·`/admin.html` 페이지 HTML · `/api/*`·`/tables/*`(데이터 평면 — 이번 범위의 대상이 아니다).
13. **[V1 `2a9f6c4`] 핵심가치 #1 계측 (상호작용 공수 점수 — 계측이 계측 대상을 깨뜨리지 않는다)**: 페이지 로드 → `effort_meter.startSession()` + `installGlobalListeners()`(키·마우스) + `installNavLinkCounting(route)` → 화면 이동마다 `countNav(from, to)` → 사용자가 교정을 저장하면 그 요청 본문에 **`effort: snapshot()`** 동승(`api.js`·`ui.js`·`clipboard.js`·`enrichment.js` 4곳).
    - 서버: `apply_batch_updates_endpoint` → **`_validate_effort`**(불량 blob은 **버리고 이름으로 보고**, 교정은 그대로 진행) → 교정 커밋 → **별도 트랜잭션**으로 `crud.record_interaction_effort` → 응답 `{effort_recorded, effort_error}`.
    - 클라: **`commitIfRecorded(res)`** — 서버가 `effort_recorded: true`라고 답했을 때만 카운터를 비운다. `res.ok`로 비우면 저장에 실패한 시도의 공수가 사라져 계기가 조용히 낙관 편향된다.
    - 읽기: `GET /dashboard/summary` → `_get_effort_stat` → `effort_metric.resolve_weights()` × `crud.get_effort_stats`(**세션별 평균 → 세션 간 평균**, `measured_ratio` 동반) → admin Overview `renderEffort`. **점수는 저장되지 않고 읽을 때 계산**되므로 가중치 재조정이 과거 전 tx를 재해석한다.
    - 선언: `GET /api/effort/config` → `effort_metric.get_public_config()`(가중치 + 컨텍스트 보존 전이 허용목록). **미선언 전이는 내비 페널티 전액** — 허용목록은 추론이 아니라 능동적 선언이다.
