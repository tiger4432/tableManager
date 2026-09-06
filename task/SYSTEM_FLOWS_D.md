# 실측 묶음 D — 파일 인제션 · HTML 토폴로지 · 인제션 진행 · 실패 관리

> 2차 실측 (2026-09-06) · 대상 흐름 **① 파일 인제션 · ② HTML 토폴로지 파서 · ㉖ 인제션 진행 → 화면 · ⑱ 실패 관리·재시도**
> 칸 정의·규칙은 [`docs/architecture/SYSTEM_FLOWS.md`](../docs/architecture/SYSTEM_FLOWS.md) §1·§3 그대로. 이 파일은 총괄이 §5 에 병합한다.
>
> 🔴 **측정 기준 커밋: `907c8995`** (2026-09-06 10:45). ⚠️ **측정 «중»에 트리가 움직였다** — `bffa792b`
> (「one place builds the batch_refresh_required payload, nine wrote it」)가 `server/main.py` 에서 18줄을
> 걷어내 `/admin/file-ingestion/active` 라우트가 **4087 → 4069** 로 밀렸다. 이 파일의 모든 주소는
> **줄 번호가 아니라 «심볼»**이다. 그 커밋에 걸리는 칸은 HEAD 에서 재측정했다.
> ⚠️ 라운드 «끝»에 HEAD 가 한 번 더 움직였다(`327ace8a`). 그 커밋은 열지 않았다 — 위 표는
> **`907c8995` 기준**이고, 그 뒤 변경이 이 넷을 건드렸는지는 **확인하지 않았다.**

---

## ① 파일 인제션 (파일 도착 → 워처 → 파서 → 표 → 인제션 로그)

**한 줄:** 파이프 자체는 촘촘하게 지어져 있다 — 그런데 **「워처가 아무것도 감시하지 않는 상태」가
`/health` 에서 «정상 박동»으로, 어드민에서 «워크스페이스 0개»로 그려진다.** 그리고 그 사실을 말하는
유일한 문장은 아무도 안 읽는 파일에 한 번 찍히는 ERROR 한 줄이다.

| # | 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 (실측) | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|---|
| F-1 | `run_decoupled_app.py` | `run_watcher.py::main` | **런처의 `ChildSpec("File Ingestion Watcher", [python, "run_watcher.py"], heartbeat="watcher")`** | 자식 프로세스 | `internal_event_client.startup_lines("File Ingestion Watcher")` 로 토큰 지문·프록시·`/health` 도달성 3종 배너 | 1 | 🔊 감독자가 재시작·`supervisor_status.json` | ✅ |
| F-2 | `WorkspaceWatcher.start()` | watchdog Observer + 기동 스윕 + 주기 스윕 | `main()` 이 `start(blocking=True)` | 스레드 3종 | 정상: `observer.start()` → `sweep_existing_files_async(reason="startup")` → `_ensure_periodic_sweep_running()` | 1 | 🔴 **`watch_count == 0 and not external_targets` 면 «셋 다 안 뜬다»** — `logger.error("No valid 'raws' folders found to watch.")` 후 **early return**. 그 ERROR 는 `watcher_stdout.log` 로만 간다(㉔: 읽는 화면 0) | 🔴 |
| F-3 | `run_watcher.poll_pending_retries` | `worker_heartbeats/watcher.json` | **3초 루프** (데몬 스레드, `watcher.start()` «이전»에 기동) | 심박 파일 | `heartbeat.beat("watcher")` — **note 없음, work claim 없음** | 1 (`health.py`) | 🔴 **F-2 가 죽어도 이 비트는 계속 뛴다** → `/health` 의 `checks.workers.watcher.status = ok` · `beats` 증가. 「살아 있다」와 「일하고 있다」가 여기서 갈리지 않는다 | 🔴 §D-① 참조 |
| F-4 | raws/ 에 파일 도착 | `IngestionHandler.on_created` / `on_moved` | **watchdog 이벤트** (`recursive=False` — raws/ **직속 자식만** 발화). `on_modified` 는 **일부러 없다**(Windows 중복) | 파일시스템 이벤트 | `event.is_directory` 면 `request_tree_ingest(src_path/dest_path)`, 아니면 `_handle_event(...)` | 2 갈래 | 🔇 이벤트 유실은 안 울린다 — 300초 `_periodic_sweep_loop` 이 그물(단, F-2 가 죽으면 **그 그물도 없다**) | ✅ |
| F-5 | `_handle_event` | `_route_and_process` | F-4 또는 스윕/트리 디스패치 | 함수 인자 | `_processing_lock` 아래 check-then-add. `logger.info("New file detected: …")` ×2 | 1 | 🔇 **두 갈래가 «맨 return»이다 — 로그 0줄**: ① 이미 `processing_files` 에 있음 ② `os.path.exists` 가 거짓(도중 소멸). 둘이 서로 구분 안 된다 | ⚠️ |
| F-6 | `_route_and_process` | heavy 큐 / 인라인 | 크기(`get_heavy_threshold_bytes`, 기본 10MB) · backlog>0 · 직렬화 락 논블로킹 실패 | `queue.Queue` 또는 직접 호출 | `_submit_to_heavy_lane` 은 **submit «이전»에** QUEUED 통지 발신(경합 제거). `lane` 은 **크기 분류 실값**(재라우팅 소형은 `"normal"`) | 1 | 🔊 submit 실패는 ERROR + QUEUED 정리 통지(FINISHED) + 인라인 폴백 | ✅ |
| F-7 | `process_with_retry` | `heartbeat.work_claim` | 파일 1건 = 클레임 1건 | 심박 파일의 `work` 블록 | `work_claim(HEARTBEAT_NAME, f"ingest {basename}")` → `{open, what, no_progress_seconds, held_seconds, stalled, stall_after_seconds}` | 1 (`health.py`) | 🔊 `stalled` 면 `/health` UNHEALTHY. ⚠️ 다만 「일이 없다」와 「감시를 안 한다」가 이 축에서도 같은 값 | ✅ |
| F-8 | `_process_with_retry` | (즉시 반환) | ① `read_file_stat` 이 None ② 디바운스 중 소멸 ③ tier-1 `(path,mtime,size)` 적중 | — | ①②는 `logger.debug(...)`, ③은 `_try_path_stat_skip` 내부 | — | 🔇 **찍히지 않는다** — `utils/logger.py` 가 `logger.setLevel(logging.INFO)` + `root_logger.setLevel(logging.INFO)`. `directory_watcher.py` 의 `logger.debug` **10곳 전부** 출력 불가 | ⚰️ (10줄) |
| F-9 | `_resolve_rows` | 사용자 파이프라인 (`<ws>/scripts/*.py`, gitignored) | `_discover_and_execute_pipeline` — `BasePipelineParser` 하위 클래스 중 `match()` 가 True 인 **첫** 것 | 함수 인자 | 파서에 `self.rel_path`(raws 기준 POSIX 상대경로) · `self.source_root` 주입. 반환 `(list[dict], None, 0)`, `meta["source_kind"] = "pipeline:<파일>::<클래스>"` | 1 | 🔊 스크립트 로드/`match()` 오류는 **std 폴백 없이** 즉시 실패(깨진 스크립트 은폐 금지) | ✅ |
| F-10 | `_resolve_rows` | `std_parser` | F-9 가 **None** 이고 `std_parse` 가 꺼져 있지 않을 때 | 함수 인자 | 반환 `(row_iterator, int, int)` 스트리밍. `meta["source_kind"] = "std"` | 1 | 🔊 아무 것도 안 받으면 `ValueError` + `render_resolution_probe(probe)` 가 **어느 표·어느 워크스페이스·std 가 왜 안 됐는지**를 문장으로 | ✅ |
| F-11 | `advanced_ingester.extract_path_metadata` | 행 dict | `process_file(file_path, rel_path=…)` | 함수 반환 | `(data, refusal)`. 미상 5종은 이름으로: `REASON_NO_MATCH`·`REASON_AMBIGUOUS`·`REASON_CAST_FAILED`·`REASON_FILE_OVERRIDES_PATH`·`REASON_PATH_VALUE_DISCARDED`. 병합 서열 **`filename < header < row`**(사용자 판정) | 1 | 🔊 `required: true` 미충족은 `refusal` → 그 파일 0행 | ✅ |
| F-12 | `_send_to_upsert` | `database_outbox` 모드 | 파일 전체 루프를 감싼다 | ContextVar | `request_outbox_mode.set(OUTBOX_MODE_COLLAPSED)` … `finally: reset(_outbox_token)` | 옵트인 2곳 중 1(나머지 1은 체인 워커) | 🔊 토큰 누수는 `finally` 가 막는다 | ✅ |
| F-13 | `_send_to_upsert` | `crud.apply_batch_updates` | 1000행 청크마다, 청크당 `SessionLocal()` | 함수 인자 | `GeneralUpdateBatch(updates=[GeneralUpdateItem(business_key_val, updates, source_name, updated_by)], transaction_id=file_tx_id, silent=True)` | 1 | 🔊 청크 실패는 `db.rollback()` + `_db_error_brief(e)` ERROR + **re-raise** → 파일 전체 실패 경로 | ✅ |
| F-14 | `GeneralUpdateBatch.silent=True` | — | — | — | 워처는 `crud.apply_batch_updates` 를 **직접** 부른다 | 🔴 **이 경로 소비자 0** — `batch.silent` 를 읽는 곳은 `main.py` 의 `PUT /data/updates` 두 자리뿐(`items_have_a_consumer`, `if not batch.silent`). `crud.py` 는 이 필드를 안 본다 | — | ⚰️ (이 경로 한정. 다른 경로엔 독자 2) |
| F-15 | 청크 커밋 | `ingestion_checkpoint.record_chunk_progress` | 청크마다, **`apply_batch_updates` «이전»에 같은 세션** | DB UPDATE, 한 커밋 | 「커밋된 행 수 == 기록된 오프셋」이 원자적으로 성립 | 1 | 🔊 실패는 청크 예외와 같은 경로 | ✅ |
| F-16 | 청크 커밋 | `heartbeat.beat(note=…)` | 청크마다 | 심박 파일 | `note=f"{filename} {processed_rows}/{total_rows}"` — **진행 수치 그 자체** | 🔴 **`/health` 소비자 0** — `heartbeat.py` 가 `beat` 에서 쓰고(`"note": note`) `read_all` 이 돌려주는데(`"note": data.get("note")`), **`server/health.py` 전건에 `note` 가 한 번도 안 나온다** | 🔇 무음 — 읽혀서 dict 에 담기고 그다음 칸에서 조용히 떨어진다 | 🔴 |
| F-17 | 파일 완결 | `_archive_file` | `_process_with_retry` 성공 말미 | 파일 이동 | `_unique_dest` → `shutil.move`. 거절 둘이 **프리미티브 안**: `_refuse_move_of_foreign_source`(외부 소스) · `_refuse_move_by_retention`(`archive_processed_files=false`) | 1 | 🔴 **실패와 「일부러 안 옮김」이 같은 문장이 된다** — 셋 다 `None` 을 돌려주고 호출부가 `or abs_path` 로 접으면 완료 로그가 똑같이 `left in place` 다. §D-② 참조 | ⚠️ |
| F-18 | `_log_ingestion_success` / `_log_ingestion_failure` | **`file_ingestion_logs`** | 파일 1건 종결마다 | DB INSERT (자기 세션) | `FileIngestionLog(filename=basename(원본), filepath=abspath(dest), table_name, status ∈ SUCCESS\|FAILED\|SKIPPED, error_message, retry_count=0)` — `error_message` 는 FAILED 에선 **`traceback.format_exc()` 전문**, SUCCESS/SKIPPED 에선 **detail 슬롯** 겸용 | 1 (`_log_ingestion_record`) | 🔴 **쓰기 실패를 삼킨다** — `except → logger.error(...)` 후 진행. 화면(`/admin/file-ingestion/logs`)에는 **그 파일이 아예 없다** | ⚠️ |
| F-19 | 0행 파싱 | `_compose_detail(…, has_rows=False)` | `total_rows == 0` | 문자열 → 통지 detail + 로그 `error_message` | `"파싱 결과 0행 ― 저장된 셀 없음(파서가 형식을 거부했을 수 있음, 워처 로그 확인)"` | 2 (`file_ingestion_completed.message` · `FileIngestionLog.error_message`) | 🔊 **이 칸이 「한 셀도 안 들어갔다」와 「정상 처리」를 가른다** — 없었으면 둘 다 SUCCESS + 빈 error_message | ✅ |
| F-20 | `on_refresh_callback` | `POST /internal/events/batch-refresh` | **`total_changed > 0` 일 때만** | HTTP (admin 토큰, `timeout=5`, `trust_env=False`) | `{table_name, change_count, created_logs?[≤500], total_log_count?}` | 1 라우트 | 🔊 실패는 WARNING/ERROR + **`_record_undelivered` 가 durable 마커 행**(`BROADCAST_RECOVERY`)을 남겨 체인 워커 스윕이 재발사. ⚠️ `table_name` 이 없으면 **말없이 bail** | ✅ |
| F-21 | `internal_event_batch_refresh` | 브라우저 | 위 POST | HTTP → WS | 🆕 `event_constants.batch_refresh_message(table_name, change_count)` — **오늘(`bffa792b`) 아홉 자리가 한 자리로 모였다.** ⚠️ 다만 이 라우트는 그 «뒤에» `msg["created_logs"]`·`msg["total_log_count"]` 를 **직접 대입**한다(빌더가 그 kwargs 를 받는데도) | 1 (`manager.broadcast`) | 🔊 게이트 있음 | ✅ / ⚠️ §D-③ |
| F-22 | `on_file_processed_callback` | `POST /internal/events/file-processed` | 파일 1건 종결마다(성공·실패·dedup-skip) | HTTP | `{table_name, filename, status, error_msg?}` — `status` 는 **dedup-skip 도 `"SUCCESS"`**(수신부가 비-SUCCESS 를 전부 「처리 실패」로 렌더하므로 오표기 방지) | 1 라우트 | 🔊 위와 같은 실패 경로 | ✅ |
| F-23 | `internal_event_file_processed` | 브라우저 | 위 POST | WS | `{event:"file_ingestion_completed", table_name, filename, status, message}` — **5칸.** `error_msg` 는 `message` 문자열 안에 `f" ({error_msg[:100]})"` 로 접힌다 | 위 F-24·F-25 | 🔊 | ⚠️ |
| F-24 | `msg.error_msg` | `finishIngestionProgress` | `websocket.js` 의 `file_ingestion_completed` 가지 | WS 필드 | 🔴 **그런 칸이 없다.** `"file_ingestion_completed"` 를 만드는 자리 **셋 전부**(`main.py` 임베디드 · 재시도 sync 콜백 · 내부 라우트)가 `error_msg` 를 **`message` 에만 접고 키로는 안 싣는다** | 읽는 쪽 **1** (`websocket.js` 가 `msg.error_msg` 를 넘김) · 쓰는 쪽 **0** | 🔇 무음 — `errorMsg` 가 항상 `undefined` 라 실패 카드의 통계줄이 **언제나 하드코딩 `'처리 중 예외 발생'`**. 출하본에도 그 읽기가 들어 있다(`dist/assets/main-M6juM_wA.js` 에 `error_msg` 1건) | 🔴 §D-④ |
| F-25 | 같은 메시지 | 토스트 + 그리드 | 같은 이벤트 | DOM | `showToast(message, …)` — 성공은 `dedupeKey` 로 한 줄 집계, 실패는 집계 안 함(개별 사유 보존). `msg.table_name === state.currentTable` 이면 `pageCache.clear()` + 이력 리로드 | 1 | 🔊 | ✅ |
| F-26 | `file_ingestion_logs` | 화면 | **`GET /admin/file-ingestion/logs?status=&page=&limit=`** | HTTP JSON | 서버가 보내는 **9칸**: `id, filename, filepath, table_name, status, error_message, retry_count, created_at, updated_at` + 봉투 `{status,total,page,limit,data}` | `admin.js` File 탭 1 | 🔊 실패면 `markSectionUnread('file-log-count')` — **「못 읽음」과 「비어 있음」을 가른다**(이 저장소가 이미 닫은 자리) | ✅ |
| F-27 | `paths.WORKSPACE_DIR` | **`GET /admin/file-ingestion/workspaces`** | 어드민 File 탭 | HTTP JSON | 🔴 `if not os.path.exists(workspace_base): return {"status": "success", "data": []}` — **경로 부재가 «성공 + 빈 배열»** | `admin.js` 1 (`if (ws) { workspaceData = ws.data \|\| []; renderWorkspaceTable(); }`) | 🔴 **무음** — 데이터 루트를 못 찾은 것이 화면에서 「워크스페이스 0개」로 그려진다. `markSectionUnread` 갈래는 **200 이 아닐 때만** 탄다 | 🔴 §D-① |
| F-28 | 300초 주기 스윕 | `_handle_event` | `_periodic_sweep_loop` (`_stop_event.wait(300)`) | 함수 인자 | 후보 6원소 `(mtime, file_path, abs_path, handler, sweep_signature, tier1_stat)` → 핸들러별 `settle_already_terminal` 배치 → 남은 것만 디스패치. 반환은 「디스패치한 수」(tier-1 종결분 제외) | 1 | 🔊 `_sweep_safely` 가 ERROR 로 감싼다 | ✅ |
| F-29 | raws/ 직속 **폴더** 드롭 | `_ingest_directory_tree` | `request_tree_ingest` → 단명 데몬 스레드 `tree-ingest-<dir>` | 파일시스템 | 정온(1s 간격 동일 스냅샷 2회, 최대 600s) → mtime 오름차순 walk → 잡파일 `os.remove` → **제자리 `_handle_event`** → 빈 폴더 bottom-up `os.rmdir` **만** | 1 | 🔊 `_tree_ingest_worker` 가 ERROR 로 감싸고 폴더 존치(스윕 재시도) | ✅ |

### 🔴 ① 안에 «다른 물음에 답하는 경로»가 하나 더 있다 — 외부 읽기 전용 소스

`docs/guide/INGESTION_GUIDE.md` §1.12 · §1.12-bis 가 2026-08-17/18 에 «선언»한 경로다. 이건 ① 의 변형이 아니라
**다른 질문에 답한다** — 「누가 이 파일을 소유하나」. 그래서 다섯 칸이 전부 다르다:

```
트리거     ExternalSourceEventHandler — on_created·on_moved «그리고 on_modified»  (관리 raws/ 는 on_modified 가 «없다»)
파서 해석   std 폴백이 «없다». 모든 플러그인이 사양하면 «거절»하고 이름을 댄다
이동       성공·실패·스킵 어느 경우에도 archives//err/ 로 «안 옮긴다» (is_managed_source 가 False)
dedup      mark_external_modified → _consume_external_force_hash 가 tier-1 을 «한 번 우회»하고 내용 sha256 까지
source_name  external:workspace:<절대경로>  또는  external:voids_json:<경로>
스윕       sweep_external_sources — 관리 스윕과 «별도 함수·별도 스레드»
```

🔴 **그리고 이 경로는 `CODE_MAP.md` §3 에 «한 글자도» 없다.** 전건 실측(문서 전체 grep):

| 심볼 | 소스 | `CODE_MAP.md` |
|---|---|---|
| `ExternalSourceEventHandler` · `register_external_source` · `external_source_context` | 있음 | **0** |
| `validate_external_source_specs` · `SUPPORTED_EXTERNAL_PARSERS` · `sweep_external_sources` | 있음 | **0** |
| `mark_external_modified` · `_consume_external_force_hash` · `_parse_meta_for` · `_external_cell_source_name` | 있음 | **0** |
| `scan_workspace_pipeline_parsers` · `workspace_pipeline_parser_names` · `render_resolution_probe` | 있음 | **0** |
| 문자열 `external_sources` | 있음 | **0** |

즉 **한 파일 안에서 두 흐름이 도는데 지도는 하나만 그려져 있다.** §2 의 판별식(「한 기능 안에서 다른 물음에
답하는 경로는 따로 세어야 흐름이 된다」)에 그대로 걸린다.

### D-① 핵심 발견 — 「**감시할 것이 없는 워처가 «건강하게» 뛴다**」

이 흐름에서 가장 무거운 자리다. 세 사실이 한 자리에서 만난다.

```
① WorkspaceWatcher.start()  watch_count == 0 and not external_targets
                            -> logger.error("No valid 'raws' folders found to watch.") 후 «early return»
                            -> observer «없음» · 기동 스윕 «없음» · 🔴 «주기 스윕도 없음»
                               (_ensure_periodic_sweep_running() 이 그 return «뒤»에 있다)
② run_watcher.poll_pending_retries   3초마다 heartbeat.beat("watcher")
                            이 스레드는 start() «이전»에 뜨고 daemon 이라 계속 돈다
                            -> /health 의 checks.workers.watcher = { status: "ok", beats: 증가 }
③ GET /admin/file-ingestion/workspaces  WORKSPACE_DIR 부재 -> HTTP 200 {"status":"success","data":[]}
                            -> 어드민 File 탭이 「워크스페이스 0개」로 그린다
```

🔴 **그래서 「데이터 루트를 못 찾았다」가 두 화면 모두에서 «정상»으로 읽힌다.**
그것을 말하는 유일한 문장은 부팅에 한 번 찍히는 ERROR 한 줄이고, 그 줄은 `watcher_stdout.log` 로 간다 —
1차 실측이 ㉔ 로 등재한 **「읽는 화면 0」** 인 바로 그 파일이다.

복구 경로는 **있다** — `poll_pending_retries` 가 `SYSTEM_RELOAD` 를 줍고 `sync_new_workspaces()` 를 부르며,
`added > 0` 이면 `_ensure_observer_running()` + 스윕 둘을 다시 세운다. 즉 **자가 치유가 «리로드 이벤트에
의존»한다.** 이벤트가 안 오면 프로세스는 살아서, 박동하며, 아무것도 적재하지 않는다.

⚠️ `work_claim` 축(`checks.workers.watcher.work`)도 이 사각을 못 메운다 — 클레임은 «파일을 처리할 때만»
열리므로 「일이 없다」와 「감시를 안 한다」가 같은 값이다.

### D-② 「left in place」가 **세 가지 다른 사실**을 같은 문장으로 말한다

`_archive_file` 은 셋 다 `None` 을 돌려준다:
```
✅ 판정   _refuse_move_by_retention   archive_processed_files=false — «설정된 동작»
✅ 판정   _refuse_move_of_foreign_source  외부 읽기 전용 소스 — «남의 트리를 안 건든다»
🔴 고장   shutil.move 예외 · _unique_dest 가 1000회 충돌로 None
```
호출부는 `dest_path = self._archive_file(file_path) or abs_path` 로 접고, 완료 로그는
`{'archived' if dest_path != abs_path else 'left in place'}` 다 — **셋이 같은 낱말**.
`FileIngestionLog` 도 셋 다 `status="SUCCESS"`, `filepath=<raws 경로>` 로 같은 행이 된다.

고장 쪽은 `logger.error` 가 따로 울리므로 **완전 무음은 아니다**. 다만 «완료 기록»에서는 구별할 수 없고,
그 기록이 화면이 읽는 것이다. 자가 치유는 있다 — 다음 스윕의 tier-1 이 원장 행을 찾아 이동을 **다시 시도**한다
(`_try_path_stat_skip` / `_settle_terminal_hits`).

### D-③ 오늘 착지한 「한 자리에서 만든다」가 **자기 도입 자리에서 한 번 새고 있다**

`bffa792b` 가 `event_constants.batch_refresh_message(...)` 를 만들고 아홉 자리를 모았다. 그런데
`internal_event_batch_refresh` 는 빌더를 부른 **뒤에** `msg["created_logs"]` · `msg["total_log_count"]` 를
직접 대입한다 — 빌더가 그 둘을 `created_logs=` · `total_log_count=` kwargs 로 **받는데도**.

```
결과 객체는 «동일»하다 (키도 값도). 그래서 결함이 아니다
그런데 커밋의 게이트는 「손으로 쓴 리터럴 0」이고, 사후 대입은 «리터럴이 아니다» -> 통과한다
```
🔴 **「내 게이트는 내가 떠올린 것만 잰다」의 교과서적 사례**다. 지금은 무해하고, 다음 사람이 여기에
칸을 하나 더 붙이는 날 「한 자리」가 깨진다.

### D-④ 실패 사유가 **화면의 자기 칸에 못 닿는다** (F-24)

```
쓰는 쪽   directory_watcher  ->  on_file_processed_callback(t_name, basename, "FAILED", str(e))
경계      POST /internal/events/file-processed   body 에 error_msg 가 «있다» (Body(None, embed=True))
접기      라우트가 그것을 message 문자열에 f" ({error_msg[:100]})" 로 «접는다»
WS 페이로드  {event, table_name, filename, status, message}   <- error_msg 칸 «없음»
읽는 쪽   websocket.js  ->  finishIngestionProgress(…, msg.error_msg)  <- 언제나 undefined
화면      failStats: errorMsg ? errorMsg.slice(0,50) : '처리 중 예외 발생'  <- «항상» 뒤쪽
```
`"file_ingestion_completed"` 를 만드는 자리는 **셋**(`main.py` 임베디드 콜백 · 재시도 sync 콜백 ·
`/internal/events/file-processed` 라우트)이고 **셋 다 같은 모양**이다 — 즉 한 자리를 고쳐서 되는 게 아니다.

⚠️ **가르는 물음(「이 칸이 없으면 무엇을 말할 수 없게 되나」)의 답은 «아무것도»다** — 사유는 `message` 로
이미 토스트에 간다. 그러므로 이건 «퍼뜨리기»가 아니라 **읽는 쪽을 지우거나 쓰는 쪽을 채우거나** 둘 중 하나다.
그리고 그 읽기는 **출하본에 들어 있다**(`dist/assets/main-M6juM_wA.js`).

### ① 에서 나온 문서 정정

| 자리 | 적혀 있는 것 | 실측 |
|---|---|---|
| `SYSTEM_FLOWS.md` ⑦ C-5 행 | 축약 outbox 를 켜는 곳이 「`directory_watcher._upsert_to_local_db`」 | 🔴 **그 심볼은 «없다»**. 살아 있는 자리는 **`_send_to_upsert`** (`request_outbox_mode.set(OUTBOX_MODE_COLLAPSED)` → `finally: reset`). 「둘뿐」이라는 개수는 여전히 참 |
| `CODE_MAP.md` §3 | 외부 소스 경로에 대한 서술 **없음** | 심볼 12종 전부 CODE_MAP 히트 **0** (위 표) — `INGESTION_GUIDE.md` §1.12/§1.12-bis 는 «있다». 지도만 낡았다 |
| `CODE_MAP.md` §3 | `_compose_detail(skipped_no_key, plan, has_rows=True)`, 호출) | 시그니처는 맞다. ⚠️ 표기에 닫는 괄호가 하나 남아 있다(오타) |
| `FAILURE_MANAGEMENT_SPEC.md` §3.1 | 「Watcher가 에러를 캐치한 즉시 해당 파일을 `err/` 폴더로 **강제 이동**」 | 🔴 **`archive_processed_files=false` 면 «안 옮긴다»**(`_refuse_move_by_retention`). 스펙이 그 모드를 모른다 — 상세는 ⑱ |

### ① 못 밝힌 것

- 사용자 파이프라인 스크립트(`<ws>/scripts/*.py`)와 `server/mappers/` 는 gitignored 라 **이 박스의 것만** 보인다. 「운영에 파이프라인이 몇 개인가」는 여기서 답할 수 없다.
- `_ensure_observer_running` 이 `RuntimeError` 로 실패했을 때(이미 `stop()` 된 observer) **`sync_new_workspaces` 가 스윕은 세우는데 observer 는 못 세우는** 조합이 실제로 도달 가능한지는 재현하지 않았다 — 코드상 가능해 보이지만 실행으로 확인하지 않았다.

---

## ㉖ 인제션 진행 → 화면 (워처 → 내부 브로드캐스트 → 레지스트리 → WS → 화면)

**한 줄:** 한 번의 청크 커밋이 **세 곳으로** 나간다 — 그리드의 진행 카드 · 어드민의 진행 목록 · 심박의 `note`.
앞의 둘은 이어져 있고 **셋째는 `/health` 경계에서 조용히 떨어진다.** 그리고 임베디드 모드에는 **첫째와 둘째가 아예 없다.**

| # | 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 (실측) | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|---|
| P-1 | `_send_to_upsert` 청크 커밋 | `self.on_progress_callback` | **청크(1000행)마다** — `processed_rows += len(chunk)` 직후 | 함수 인자 | `(t_name, filename, progress_pct, processed_rows, total_rows)`. `progress_pct = min(int(processed/total*100), 100) if total_rows else 100` | 1 | 🔊 콜백 예외는 `logger.warning("Progress callback failed: …")` — 인제션은 안 죽인다 | ✅ |
| P-2 | `WorkspaceWatcher(…)` 생성 (**분리 모드**) | `run_watcher.trigger_ws_progress` | 부팅 | 생성자 kwarg | `on_progress_callback=trigger_ws_progress` | 1 | — | ✅ |
| P-3 | `WorkspaceWatcher(…)` 생성 (**임베디드 모드**) | — | `main.py::startup_event`, `DECOUPLED != "True"` 일 때만 | 생성자 kwarg | 🔴 **`on_progress_callback` 을 «안 넘긴다»** — 넘기는 것은 `on_refresh_callback` · `on_file_processed_callback` · `on_ingestion_state_callback` 셋뿐 | 0 | 🔇 완전 무음 — 진행 카드도, normal 레인 레지스트리 엔트리도 «생기지 않는다» | 🔴 (비운영 모드) |
| P-4 | `trigger_ws_progress` | `POST /internal/events/broadcast` | P-1 | HTTP (admin 토큰, `timeout=5`, `trust_env=False`) | `{"event":"file_ingestion_progress", table_name, filename(=`get_basename`), progress, processed_rows, total_rows, "status":"PROCESSING"}` — **7칸.** + `logger.info(f"Ingestion progress for … {progress}% ({processed}/{total})")` | 1 라우트 | 🔊 실패는 WARNING/ERROR + `_record_undelivered` durable 마커 | ✅ |
| P-5 | `"status": "PROCESSING"` | — | — | WS 필드 | 페이로드에 «실린다» | 🔴 **소비자 0** — `apply_progress` 는 이 칸을 인자로 안 받고 `entry["status"] = "PROCESSING"` 을 **하드코딩**한다. `websocket.js` 의 progress 가지도 `msg.status` 를 안 읽는다 | — | ⚰️ (가르는 물음의 답: 없어도 «아무것도» 못 말하게 되지 않는다) |
| P-6 | `internal_event_broadcast` | `ingestion_activity_registry.apply_progress` | `payload.get("event") == "file_ingestion_progress"` (**맨 문자열 비교** — 상수 아님) | 함수 인자 | `(table_name, filename, progress=, processed_rows=, total_rows=)` — **5칸.** 엔트리가 없으면 `_new_entry(lane="normal")` 로 «생성»한다(normal 레인의 유일한 유입 경로) | 1 | ⚠️ `except → print("[Main Server] Failed to update ingestion activity from progress: …")` — `logger` 가 아니라 **`print`**. uvicorn stdout 으로만 간다 | ✅ |
| P-7 | 같은 라우트 | `manager.broadcast` | 같은 POST | HTTP → WS | **페이로드를 그대로 릴레이** — 검증도 재작성도 없음(`payload: dict = Body(...)`, 모델 없음) | N (접속 클라) | 게이트 있음(`require_admin_token`). ⚠️ 나가는 `/ws` 에는 인증이 없다 | ✅ |
| P-8 | WS 메시지 | `websocket.js` `handleWebSocketMessage` | `onmessage` | WS JSON | `msg.event === 'file_ingestion_progress'` 가 **함수의 첫 분기**이고 `return` 한다 — 즉 **`msg.table_name === state.currentTable` 관문 «앞»에서 소비된다**(다른 표를 보고 있어도 카드가 뜬다) | 1 | 🔊 파싱 실패는 `console.error` | ✅ |
| P-9 | `showIngestionProgress` | `progress_card.js::showProgressCard` | 위 | DOM | `{key: ingestionKey(table,filename), title:'📤 파일 파싱 및 적재 중', subtitle:getCleanFilename, progress, processed, total, statsSuffix:' 행 처리됨', doneTitle, doneStats}` — 표/파일 낱말은 **신원 조립에만** 쓰이고 부품은 그 낱말을 모른다 | 1 | 🔇 카드 상한 초과분은 `collapseOverflow` 로 «가려진다»(갱신은 계속 받음) | ✅ |
| P-10 | `file_ingestion_completed` | `finishIngestionProgress` → `finishProgressCard` | 파일 종결 | DOM | `key` 로 카드를 찾고 **없으면 no-op**(`if (!card \|\| isDone(card)) return;`) | 1 | 🔇 조용 — 0행 파일·즉시 실패는 카드가 애초에 없어 무해 | ✅ |
| P-11 | 레지스트리 | **`GET /admin/file-ingestion/active`** (`require_admin_token`) | 어드민 File 탭 fetch(30s/수동) + 활성 시 5초 경량 타이머 | HTTP JSON | 엔트리 **13칸**: `table_name, filename, lane, status, progress, processed_rows, total_rows, size_bytes, queued_at, started_at, first_seen, updated_at, elapsed_seconds` + 봉투 `{status,total,data}` | `admin.js` **2** (`renderActiveIngestions` · ⚰️`refreshFileAndAutoHealth`) | 🔊 File 탭 경로는 실패를 «가른다» — `markSectionUnread('active-ingestion-count')` (「못 읽음」 ≠ 「없음」) | ✅ |
| P-12 | 같은 응답 | 화면 픽셀 | `renderActiveIngestions` | DOM | 읽는 칸 **4** — `lane`(HEAVY/normal 배지 + heavy 카운트) · `progress`(`maxProg`) · 목록 길이. 🔴 **`processed_rows`·`total_rows`·`elapsed_seconds`·`queued_at`·`started_at`·`size_bytes`·`status` 는 이 함수에서 안 읽힌다**(행 렌더 나머지는 미확인 — 아래 「못 밝힌 것」) | 1 | — | ⚠️ |
| P-13 | `scheduleActiveRefresh` 5초 타이머 | 같은 라우트 | `renderActiveIngestions` 가 자기 안에서 «자기를 다시 건다» | HTTP | `if (res.ok) { … renderActiveIngestions(); }` | 1 | 🔴 **`res.ok` 가 거짓이면 `renderActiveIngestions()` 가 안 불리고 → 타이머 사슬이 «끊긴다»**. 마지막 성공 목록이 그대로 남아 「진행 중」으로 계속 그려진다. 30초 탭 갱신이 복구하지만 그 사이 화면은 **멈춘 값을 살아 있는 값으로** 보여준다 | ⚠️ |
| P-14 | 청크 커밋 | `heartbeat.beat(HEARTBEAT_NAME, note=…)` | P-1 과 **같은 자리·같은 줄 옆** | 심박 파일 | `note = f"{filename} {processed_rows}/{total_rows}"` — **P-4 가 HTTP 로 보내는 것과 같은 수** | 🔴 **`/health` 소비자 0** (F-16 과 같은 칸) | 🔇 무음 | 🔴 |
| P-15 | heavy 레인 | `POST /internal/events/ingestion-state` → `apply_state` | `_submit_to_heavy_lane`(QUEUED, submit 이전) · `_run_lane_job`(PROCESSING) · `finally`(FINISHED) | HTTP | `{table_name, filename, lane, status, size_bytes?, queued_at?, started_at?}` — **WS 브로드캐스트 없음**(어드민 전용) | 1 (레지스트리) | ⚠️ `except → print(...)` (logger 아님) | ✅ |
| P-16 | 인라인(normal) 레인 | FINISHED 통지 | — | — | 🔴 **없다** — `_run_lane_job` 의 `finally` 는 **heavy 전용**이다. 인라인 경로(`_route_and_process` 의 `process_with_retry`)에는 그런 `finally` 가 없다 | — | ✅ **결함 아님** — normal 엔트리는 P-6 이 만들고 `file-processed` 가 지운다. 제거 없이 끝나는 갈래(F-8 의 조기 반환 셋)는 **진행 이벤트를 내기 «전»에** 끝나므로 만들 엔트리 자체가 없다. 프로세스 사망은 `STALE_ENTRY_TTL_SECONDS=30분` 이 퇴거 | ✅ |

### D-⑤ 핵심 발견 — 「**같은 수가 셋으로 갈라지고, 하나만 끊긴다**」

```
청크 하나가 커밋되면 «같은 줄 옆»에서 둘이 나간다
  heartbeat.beat(note=f"{filename} {processed}/{total}")     -> 심박 파일 -> read_all 이 돌려줌 -> 🔴 health.py 가 «안 복사»
  on_progress_callback(t, f, pct, processed, total)          -> HTTP -> 레지스트리 «와» WS 둘로 갈림 -> ✅ 둘 다 닿음
```
🔴 **`server/health.py` 전건에 `note` 라는 낱말이 «한 번도» 안 나온다.** `heartbeat.py` 는 `beat()` 에서
`{"note": note}` 로 쓰고 `read_all` 이 `"note": data.get("note")` 로 돌려주는데, `compute_health` 의 워커 항목
조립이 그 칸을 안 집는다.

이건 1차 실측 §2-bis 가 **「청중이 바깥 모니터로 판정된 뒤에도 여전히 열려 있다」**고 적어 둔 세 칸 중 하나다.
㉖ 이 더하는 것은 **그 `note` 를 «누가 쓰는가»** 다 — 파일 인제션의 진행 그 자체다. 즉 바깥 모니터는
「워처가 살아 있다」는 알 수 있어도 **「이 파일이 12,000/340,000 행에서 서 있다」는 못 본다**.
그 수는 존재하고, 매 청크 갱신되고, 파일에 있다.

### D-⑥ 임베디드 모드에는 이 흐름이 **통째로 없다** (P-3)

```
분리 모드(운영)   run_watcher.main()    on_progress_callback=trigger_ws_progress   ✅
임베디드 모드      main.py::startup_event  «인자 자체가 없음»                        🔴
```
`DECOUPLED != "True"` 일 때만 도는 갈래이고, `run_decoupled_app.py` 와 `server/scripts/dev_env/devenv.py`
**둘 다** `DECOUPLED="True"` 를 넣는다. 즉 **저장소 안의 어떤 런처로도 이 갈래에 도달하지 않는다** —
`main.py` 를 손으로 띄웠을 때만이다. `directory_watcher.py` 의 모듈 주석이 그 모드를 지원 대상으로
명시하고 있으므로 ⚰️ 로 접지 않고 🔴(비운영)로 둔다.

증상은 조용하다: 진행 카드가 안 뜨고, 어드민 「진행 중」 절이 heavy 파일만 보여 준다.
오류는 하나도 안 난다.

### ㉖ 못 밝힌 것

- `renderActiveIngestions` 의 행 렌더 본문(`items.forEach` 안)을 **끝까지 읽지 않았다**. `lane`·`progress`·목록 길이 셋은 확인했고, 나머지 아홉 칸 중 몇이 행 안에서 읽히는지는 **못 셌다**. P-12 의 「4칸」은 **하한**이다.
- `/ws` 무인증이 이 흐름에서 실제로 무엇을 노출하는지(진행 이벤트에 파일명·표 이름이 실린다)는 접근 통제 흐름 ㉑ 의 소관이라 여기서 판정하지 않았다.

---

## ② HTML 토폴로지 파서 (HTML 표 → 격자 → 표 → 화면)

**한 줄:** 파서 «자체»는 살아서 옳게 돈다 — 두 유도가 어긋나면 **이름 붙은 사유로 거절하고 0행을 낸다**.
끊긴 것은 그 «사유»가 로그 밖으로 못 나가는 것, 그리고 768줄 중 **그래프 팔 전체의 비시험 소비자가 0**이라는 것이다.

| # | 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 (실측) | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|---|
| H-1 | raws/ 에 `.html` | `_discover_and_execute_pipeline` | **①의 F-4/F-28 그대로** (전용 트리거 없음) | 파일 | ①의 경로를 그대로 탄다 — 이 흐름에 자기 입구는 없다 | 1 | ①과 동일 | ✅ |
| H-2 | `_discover_and_execute_pipeline` | `scan_workspace_pipeline_parsers` | 위 | 함수 인자 (`self.scripts_path`) | 🔴 **`pipeline_*.py` 가 아니라 `scripts/` 의 «모든» `.py`** (`endswith(".py") and != "__init__.py"`). `probe` 에 `plugin_files`·`parser_classes`·`declined` 를 실측으로 채운다 | 2 | 🔊 로드 실패는 `load_errors` 에 트레이스백 → `render_resolution_probe` 가 파일명까지 문장으로 | ✅ |
| H-3 | `_register_legacy_import_shim` | `sys.modules["server.parsers.html_topology_parser"]` | 첫 스캔 1회 | `sys.modules` 별칭 | `import html_topology_parser` 를 **`try/except` 로 감싸고 실패 시 WARNING 후 «별칭 스킵»** | 1 (구식 dotted import 를 쓰는 사용자 스크립트) | ⚠️ shim 실패는 WARNING 한 줄. 진짜 파열은 **세 홉 뒤** 플러그인 로드에서 나고 그건 `load_errors` 로 시끄럽다 | ⚠️ |
| H-4 | 사용자 플러그인 | `HTMLMatrixTableParser.parse_matrix_to_records(html)` | `match()` 가 True (`file_path.lower().endswith('.html')`) | 함수 인자 (str) | 이 박스 실측: 아카이브 HTML **16건 전수 파싱 → 16/16 성공 · 거절 0** | **비시험 소비자 1** (이 디스크 기준) | 🔊 예외는 `parse()` 밖으로 전파 → ①의 실패 경로 | ✅ |
| H-5 | 격자 원점 유도 «둘» | `x_row_idx` 채택 | 위 | 함수 지역 | 위 기준 `_ruler_row(r)` → `(top_anchor, top_ticks)` · 아래 기준 `min(y_label_rows) - 1` → `bottom_anchor`. **둘이 같을 때만 채택** | 1 | 🔊 **불일치 4갈래를 각각 다른 문장으로**: 둘 다 없음 / 위만 없음 / 아래만 없음 / 서로 다름(양쪽 행 번호와 눈금 값까지). `logger.warning("[matrix] REFUSED to parse: …")` 는 루트 INFO 라 **실제로 찍힌다** | ✅ |
| H-6 | 그 거절 사유 | 화면 | — | — | ASCII 한 줄, 호출당 1회 | 🔴 **프로그램 소비자 0** — `REFUSED` 문자열을 읽는 코드 0건. 사유는 `watcher_stdout.log` / `watcher.log` 에만 | ⚠️ **조용하지 않은데 «닿지도» 않는다** — 로그엔 정확한 문장이 있고 화면엔 그것이 없다 | ⚠️ |
| H-7 | 0행 반환 | `_compose_detail(has_rows=False)` | ①의 F-19 | 문자열 | `"파싱 결과 0행 ― 저장된 셀 없음(파서가 형식을 거부했을 수 있음, **워처 로그 확인**)"` | 2 (WS `message` · `FileIngestionLog.error_message`) | 🔊 **이 문장이 H-6 의 사각을 «가리키기는 한다»** — 사유 대신 「어디를 보라」를 준다. 사유 자체는 안 나른다 | ⚠️ |
| H-8 | `_default_is_header` | `TableNode.is_header` | `_reconstruct_2d_grid` 의 셀 순회 | 객체 속성 | 셀마다 계산된다 | 🔴 **매트릭스 경로 소비자 0** — `node.is_header = (bool(node.value) and node.row_range[1] < x_row_idx and not _is_unmerged(node))` 가 **전량 덮는다**. `_build_adjacency_graph` 는 `is_header` 를 읽지 않는다 | 🔇 계산되고 버려진다. 아무것도 안 울린다 | ⚰️ |
| H-9 | 생성자 kwarg `is_header_fn` | 판정 | — | 인자 | `HTMLMatrixTableParser(is_header_fn=…)` → `HTMLTableGraphParser(is_header_fn=…)` | 🔴 **커스텀을 넘기는 비시험 호출자 0**. 넘겨도 매트릭스 경로에선 H-8 이 무시한다 — **표시 없이** | 🔇 | ⚰️ |
| H-10 | 그래프 팔 공개 API | — | — | — | `extract_semantic_tuples` · `parse_to_directed_graph` · `generate_adjacency_matrix` · `find_all_paths*` · `TableEdge` | 🔴 **비시험 소비자 0** (전건) | 🔇 | ⚰️ |
| H-11 | 파서 반환 | `pd.DataFrame` → `clean_for_postgres` → `_send_to_upsert` | 사용자 플러그인이 `_read_file_to_dataframe` 를 오버라이드 | list[dict] | 이 박스 실측 키 **8**: `TITLE, BDIE_LOT, BDIE_WF, CDIE_LOT, CDIE_WF, X, Y, VALUE` → rename+lower 후 `title, base, bdie_wf, cdie_lot, cdie_wf, x, y, leg` | 1 | ①의 F-13 | ✅ |
| H-12 | 그 8칸 | `display_columns` 필터 | `_send_to_upsert` 의 정규화 루프 | 함수 내부 | ⚠️ **이 박스 선언 기준** — 커밋된 `.sample` 의 `bonding_map.display_columns = [base_wafer_id, base_x, base_y, leg]` 와 대소문자 무시 «완전 일치»만 통과 → 8칸 중 `leg` 하나만 남는다 | 1 | 🔊 `_announce_dropped_columns` 가 (표,컬럼)당 프로세스 1회 WARNING + 파일당 1회 INFO | ⚠️ 이 박스 |
| H-13 | 남은 칸 | `crud.assemble_composite_business_key` | 청크 업서트 | DB | ⚠️ **이 박스 선언 기준** — `composite_key_source = [base_wafer_id, base_x, base_y]` 셋 중 **하나도 payload 에 없다** → `_unfilled_composite_parts` 가 셋을 돌려주고 함수는 **조용히 `False`** | 1 (인제션 경로) | 🔴 **무음** — 예외 0 · 로그 0. 그리고 **`unfilled_key_columns` 게이트를 부르는 곳은 `chain_key_gate`·`mapper_sdk`·`void_sat_format` 셋이고 «파일 인제션은 없다»** | 🔴 이 박스 |
| H-14 | 계약 하니스 | 사용자 스크립트 텍스트 | `contracts/map2_seam/` 스위트 | 파일 텍스트 | `assert "HTMLMatrixTableParser" in src` — **텍스트가 «주어»인 드리프트 오라클**(CLAUDE.md 의 잘라쓰기 예외에 해당) | 1 (시험) | 🔊 위임이 끊기면 빨개진다 | ✅ |

### D-⑦ 핵심 발견 — 「**파서는 정확한 문장을 쓰고, 그 문장이 파일 밖으로 안 나간다**」

```
파서    거절 사유를 «네 갈래»로 갈라 행 번호·눈금 값까지 넣어 문장을 만든다   <- 이 저장소에서 드문 품질
경계    그 문장은 logger.warning 으로 나간다 — 루트 INFO 라 «실제로 찍힌다»
화면    0행이 되어 「파싱 결과 0행 ― … 워처 로그 확인」 이라는 «포인터»가 간다
=> 사유는 «있고», 화면은 «어디를 보라»까지 말한다. 없는 것은 그 사이 한 홉이다
```
🔴 그리고 그 「워처 로그」가 1차 실측 ㉔ 의 **「읽는 화면 0」** 인 파일이다. 이 흐름의 마지막 홉은
**「운영자가 서버에 붙어 파일을 연다」**를 전제한다.

⚠️ 이건 D-④(실패 사유가 자기 칸에 못 닿음)와 **같은 병의 다른 지점**이다 — ①은 «칸이 없어서»,
②는 «칸에 넣을 생각을 안 해서». 둘 다 「사유는 만들어졌다」에서 멈춘다.

### D-⑧ 768줄 중 **그래프 팔이 통째로 ⚰️**

```
살아 있는 것  HTMLMatrixTableParser · parse_matrix_to_records · TableNode · _ruler_row · _is_unmerged
소비자 0     HTMLTableGraphParser 의 공개 API 넷 · TableEdge · is_header_fn 주입 축 ·
            _default_is_header 의 매트릭스 경로 결과
```
🔴 **가르는 물음(「없으면 무엇을 말할 수 없게 되나」)의 답은 «아무것도»다** — 매트릭스 경로가 자기
인접 그래프를 따로 만든다. 즉 «퍼뜨리기»가 아니라 «빼기» 쪽이다.
⚠️ 다만 소스 주석은 `_default_is_header` 를 **`extract_semantic_tuples` 를 위해 남긴다**고 말하는데,
그 `extract_semantic_tuples` 의 소비자가 0이다 — **보호 대상이 없는 보호**다.

### ② 에서 나온 문서 정정

| 자리 | 적혀 있는 것 | 실측 |
|---|---|---|
| `docs/guide/HTML_TOPOLOGY_PARSER_GUIDE.md` 헤더 | `Last-verified: 2026-07-24` | 파일은 **2026-08-04 `419cd8fa`** 로 +130줄 바뀌었다. 격자 원점 이중 유도 · 거절 경로 · 구조적 헤더 술어 — 가이드에 **한 글자도 없다**(`REFUSED`·「격자 원점」 grep 0) |
| 같은 가이드 §2 예시 | `is_header_fn=lambda tag: …` (**인자 1개**) | 코드는 `self.is_header_fn(cell, row_idx, col_idx)` (**인자 3개**). 문서 그대로 쓰면 `TypeError` |
| 같은 가이드 §1.4 | 「숫자가 아닌 텍스트 + `c < max_cols-1` 이면 Row Header」 | 매트릭스 경로에서 **폐기된 규칙**. 소스 주석이 그 규칙을 「양방향으로 틀렸다」고 적고 위치 술어로 갈아치웠다 |
| 같은 가이드 §4 연동 예시 | `HTMLTableGraphParser` + `extract_semantic_tuples`, `parse()` 오버라이드 | 살아 있는 스크립트는 `HTMLMatrixTableParser` + `parse_matrix_to_records`, **`_read_file_to_dataframe`** 오버라이드. 가이드대로 `parse()` 를 갈면 `clean_for_postgres`(NaN/Inf → None)를 **건너뛴다** |
| `CODE_MAP.md` §3-ter 라인 앵커 | `_is_unmerged`(558)·`_ruler_row`(568)·사유(592)·top(621)·bottom(630)·채택(659)·헤더 술어(697)·768줄·시험 429줄 | 🟢 **전부 정확.** §3-ter 는 낡지 «않았다» — 이 라운드에서 안 틀린 유일한 절이다 |
| `CODE_MAP.md` §3-ter | 「`_default_is_header` 는 손대지 않았다 — `extract_semantic_tuples` 와 호출자가 넘기는 술어는 동작이 그대로다」 | 문장은 **참인데 오도한다**: 보호되는 대상(비시험 호출자)이 **양쪽 다 0**이다 |
| `CODE_MAP.md` §3-ter | 「아카이브 **19파일** · 헤더 모양 4종」 | 이 박스 `bonding_map/archives/` 는 HTML **16건**(+`err/` 3 = 19). 원 측정이 그 합집합이었는지는 **확인 못 함** |

⚠️ **한 가지는 정정으로 «올리지 않는다»**: `html_topology_parser.py` 의 주석
「`composite_key_source: [base, x, y]`」와 `.sample` 의 `[base_wafer_id, base_x, base_y]` 를
「커밋된 것끼리의 모순」으로 세울 수 있어 보이지만, 그 주석은 **산문 축약**으로 읽는 것이 자연스럽다.
근거가 약한 정정은 올리지 않는다.

### ② 못 밝힌 것

- **운영의 워크스페이스 스크립트 수.** `<ws>/scripts/` 는 gitignored 다. 이 디스크에서 스크립트 7개 중 **1개**가 이 파서를 쓴다. H-4 의 「소비자 1」은 **이 디스크에 대한 수**다.
- **H-12·H-13 은 이 박스 선언 위의 측정이다** — 커밋된 `.sample` 이 같은 세 칸을 선언하므로 «모양»은 저장소가 뒷받침하지만, 「운영에서도 7칸이 떨어진다」로 **승격하지 않는다**.
- **거절 경로가 운영에서 발화한 적이 있는가.** 이 박스의 마지막 HTML 적재(2026-07-12)가 이 코드 착지(2026-08-04)보다 **앞선다** — 여기서는 새 코드가 실파일을 만난 적이 «없다».
- `business_key_val = NULL` 행이 실제로 쌓였는지는 **DB에 묻지 않았다**(이 박스 얘기 부류). 기제만 코드로 확정했다.

---

## ⑱ 실패 관리·재시도 (실패 → 로그/아웃박스 → 재시도 → 화면)

**한 줄:** 운영 기동(`DECOUPLED=True`)에서 **「Retry」 버튼은 재시도를 «실행»하지 않는다** — 상태를
`PENDING_RETRY` 로 바꾸고 200을 돌려준다. 그 값은 실패 목록에서 «사라지는» 값이고, 그것을 그리는 화면은 없다.

### A) 아웃박스 팔

| # | 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 (실측) | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|---|
| R-1 | `process_chain_transaction_group` | `process_pending_groups` | 매퍼/벌크업데이트 예외 (2초 LISTEN 타임아웃 폴) | 함수 반환 | `return False, error_msg, []` — **정확히 2곳**(매퍼 · 배치업데이트), 둘 다 `error_msg = traceback.format_exc()` | 1 | 🔊 `logger.error("Failed to execute mapper in tx …")` | ✅ |
| R-2 | `process_pending_groups` | `database_outbox` | `success=False` | DB UPDATE | `retry_count += 1`; **≥3** 이면 `mark_processed(event,"FAILED")`(= `status=FAILED` · `processed_chain=True` · `processed_at=now()`) + `payload["error_log"] = {failed_at, reason}` (+ 붕괴청크 재확장이면 `reexpanded_into`) | 1 | 🔊 `logger.error("Transaction … permanently failed: N events moved to FAILED status.")` | ✅ **스펙 §2.1 대로 트레이스백이 `payload.error_log.reason` 에 들어간다** |
| R-3 | `database_outbox` | **`GET /admin/outbox/failed?page=&limit=`** | 사람 클릭 · 30초 `AUTO_REFRESH_MS` | HTTP JSON | 봉투 **6칸** `status·total·page·limit·oldest_failed_at·data[]` · 그룹 `transaction_id·table_names·event_types·retry_count·failed_at·events[]` · 이벤트 **9칸** `id·event_uuid·event_type·table_name·payload·status·retry_count·created_at·processed_at`. 🟢 **`try/except` 가 «없다»** — DB 오류는 500이지 200+빈 배열이 아니다. ⚠️ 그룹화는 `query.all()` 전수 후 인메모리(`page/limit` 은 «그룹» 기준) | 3 (`fetchData`·`fetchOverview`·⚰️`refreshChainHealth`) | 🔊 500/401 → `markSectionUnread('chain-fail-count')` + 토스트 | ✅ |
| R-4 | 위 응답 | `renderOutboxTable` / `showEventDiagnostics` | 응답 도착 | DOM | 읽는 칸: 그룹 5 + 이벤트의 `id·event_type·table_name·payload.error_log.reason·payload` | 🔴 **떨어뜨리는 칸 2** — `event_uuid` · `processed_at`. 후자는 `mark_processed` 주석이 「이 컬럼을 발행하는 유일한 자리」라고 적어 둔 바로 그 칸 | 🔇 트레이스백이 없으면 `'No error traceback log captured.'` 로 대체 | ⚠️ |
| R-5 | 사람 Retry 클릭 | **`POST /admin/outbox/retry-failed`** | 버튼 | HTTP **쿼리스트링** `?transaction_id=` (바디 아님 — `event_id`/`transaction_id` 는 FastAPI 쿼리 파라미터) | 리셋: `status="PENDING"` · `retry_count=0` · `processed_chain=False` · `payload.error_log.resolved_at`. 응답 3칸 `status·message·skipped_reexpanded` | 2 (`retryTransaction`·`retryAllFailed`) | 🔊 `!res.ok` → 토스트 | ✅ |
| R-6 | `skipped_reexpanded` | 화면 | — | 응답 칸 | 「이미 재확장된 붕괴청크는 리셋하지 않았다」 | 🔴 **소비자 0** — `retryTransaction` 은 `message` 조차 안 읽고 무조건 「🔄 재시도 발행」 토스트. `retryAllFailed` 만 `result.message` 를 읽는다 | 🔇 **아무것도 리셋 안 됐어도 단건 경로는 성공처럼 보인다** | 🔴 |
| R-7 | `POST /admin/outbox/retry-failed` | 체인 워커 | — | — | 🔴 **`NOTIFY outbox_event` 를 «발행하지 않는다»** — 같은 파일의 `trigger_auto_update_run_now`·`reload_system_configs` 는 발행한다 | — | 🔇 **무해** — LISTEN 2초 타임아웃 폴이 ≤2초에 줍고 클라는 3초 뒤 재조회한다. 비일관이지 결함은 아니다 | ⚠️ |

### B) 파일 인제션 팔

| # | 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 (실측) | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|---|
| R-8 | `_process_with_retry` `except` | `file_ingestion_checkpoints` | 파서 예외 | DB 행 | `record_failure(...)` → `table_name·file_signature(sha256 또는 `stat:` 폴백)·filename·filepath·file_mtime·file_size·processed_rows=0·chunk_index=0·status="FAILED"·note="[failed] <트레이스 마지막 줄 500자>"` | 1 (`find_terminal_by_path_stat[_batch]` — 재처리 차단) | 🔊 실패는 `logger.warning("Could not seal the failure in the ingestion ledger …")` | ✅ |
| R-9 | 같은 `except` | **`file_ingestion_logs`** | 같은 예외 | DB INSERT | `filename=basename(원본)·filepath=abspath(dest)·table_name·status="FAILED"·error_message=traceback.format_exc()·retry_count=0`(**하드코딩**) | 1 (`get_file_ingestion_logs`) | 🔴 **쓰기 실패를 삼킨다** — ERROR 한 줄 후 진행 (①의 F-18 과 같은 칸) | ⚠️ |
| R-10 | `file_ingestion_logs` | **`GET /admin/file-ingestion/failed`** | 사람 · 30초 | HTTP JSON | `get_file_ingestion_logs(status="FAILED", …)` **위임 한 줄**. 봉투 5 + `data[]` **9칸**. 🟢 `try/except` 없음 → 500 | 4 (File 탭은 `/logs`, autoupdate·overview·⚰️health 는 `/failed`) | 🔊 `markSectionUnread` + 「상태 조회 실패」 | ✅ |
| R-11 | 위 응답 | `buildFileLogRow` / `selectFileRow` | 응답 | DOM | **9칸 전부 읽는다** — 떨어뜨리는 칸 **0** | 1 | — | ✅ |
| R-12 | 사람 Retry 클릭 | **`POST /admin/file-ingestion/retry-failed?log_id=`** | 버튼 | HTTP 쿼리 | 서버는 `status == "FAILED"` 행만 조회 | 2 | 🔊 | ✅ |
| R-13 | 그 라우트, **DECOUPLED 분기** | `file_ingestion_logs.status = "PENDING_RETRY"` | `os.getenv("DECOUPLED") == "True"` — **`run_decoupled_app.py` 가 API 자식에 `env={"DECOUPLED":"True"}` 를 박는다** | DB UPDATE + 즉시 200 | `{"status":"success","message":"Decoupled mode: Marked N logs as PENDING_RETRY. Standalone watcher will process them."}` — **워처가 살아 있는지 «묻지 않는다»** | 1 | 🔴 **무음** — §D-⑨ ① | 🔴 |
| R-14 | 같은 라우트, `asyncio.to_thread` 분기 | `process_archived_file_sync` | 비-DECOUPLED 에서만 | 함수 인자 | `sync_refresh_callback`(= `event_constants.batch_refresh_message`) · `sync_file_processed_callback` 주입 · `resolve_workspace_root(...)` 로 별칭 역조회 | 0 (운영) · 1 (임베디드) | — | ⚰️ **운영에서 죽은 갈래** (근거: 런처의 `env`, 그리고 라우트 최상단 early return) |
| R-15 | `file_ingestion_logs`(PENDING_RETRY) | `run_watcher.poll_pending_retries` | **3초 폴러 스레드** | DB 조회 → 선점 → 처리 | 🔴 **선점이 «처리 전에 커밋»된다**: `log.status = "PENDING"; db.commit()` → 그다음 핸들러 생성·처리. 핸들러는 콜백 **셋 다** 받는다(`refresh`·`file_processed`·**`progress`** — 즉 ㉖의 P-3 사각이 여기엔 «없다») | 1 (운영의 유일한 실행자) | 🔊 `logger.info("Detected PENDING_RETRY log ID #N")` | ⚠️ §D-⑨ ② |
| R-16 | `_process_archived_file_sync` | `file_ingestion_logs` | 위 | DB UPDATE | 성공: `status="SUCCESS"` + `error_message = detail`(**대개 `None` → 트레이스백이 지워진다**). 실패: `status="FAILED"` + traceback + `retry_count += 1`. 파일은 **`log_entry.filepath` 를 그대로** 연다 | 1 | 🔊 | ✅ |
| R-17 | 재시도 성공 | `on_refresh_callback` → WS | `total_changed > 0` **일 때만** | HTTP → WS | ①의 F-20/F-21 | — | 🔇 **행이 0이면 리프레시 이벤트가 아예 안 난다** | ⚠️ |
| R-18 | `batch_refresh_required` / `file_ingestion_completed` | **어드민 화면** | 위 | WebSocket | — | 🔴 **어드민 소비자 0** — `admin.html` 이 로드하는 스크립트는 `./src/admin.js` 하나(+Monaco CDN 로더 + 테마 인라인). `admin.js` 소스에 `WebSocket` **0건**, 출하본 `admin-eErqdtgQ.js` 에 `WebSocket`·`file_ingestion_completed`·`batch_refresh_required` **각 0건**. 받는 것은 그리드 페이지(`main-M6juM_wA.js`)뿐 | 🔇 어드민은 30초 폴링 + 재시도 직후 명시 재조회로만 갱신 | 🔴 §D-⑩ |

### D-⑨ 핵심 발견 — 「**Retry 가 200을 돌려주는데 아무것도 재시도되지 않을 수 있고, 그 실패는 «목록에서 사라진다»**」

이 흐름의 상태 낱말은 **넷**이고, **화면이 아는 것은 둘뿐**이다.

```
FAILED         /admin/file-ingestion/failed 가 «본다»                        화면에 뜬다
SUCCESS        File 탭 목록이 «본다»                                         화면에 뜬다
PENDING_RETRY  🔴 어느 라우트도 필터에 «안 넣는다»                             화면에서 «사라진다»
PENDING        🔴 폴러(=="PENDING_RETRY")도 라우트(=="FAILED")도 안 본다       «영원히» 사라진다
```

**① 워처가 죽어 있으면 Retry 는 성공처럼 보인다.**
DECOUPLED 분기는 상태만 바꾸고 200을 돌려준다 — **워처 프로세스가 살아 있는지 묻지 않는다.**
클라(`admin.js::retryFileIngestion`)의 사후 판정은 `f.status === 'FAILED'` 하나뿐이라
`PENDING_RETRY` 는 **「해제됨」으로 읽힌다** → 「✅ 재시도 완료」 토스트. `/failed` 에서도 빠지므로
File 카드는 **「실패 0건」**. 아무것도 안 했는데 화면이 완전히 정상이다.

**② 선점이 처리보다 «먼저» 커밋된다.**
`poll_pending_retries` 가 `log.status = "PENDING"` 을 커밋한 «뒤» 처리를 시작한다. 그 창에서 워처가
죽으면 행은 `PENDING` 에 영구 고착된다 — `PENDING_RETRY` 쿼리도 `FAILED` 쿼리도 그 행을 안 본다.
**되살릴 경로가 코드에 없다**(수동 SQL 뿐).

**③ 아웃박스 쪽도 같은 모양의 낙관 판정.**
`retryTransaction` 은 `setTimeout(…, 3000)` 뒤 「목록에 없으면 성공」으로 읽는다. 리셋된 tx 는
PENDING/RETRYING 이라 3초 뒤엔 **정상적으로** 없다 — 다시 3회 실패해 재격리될 예정이어도
**「✅ 실패 목록에서 해제되었습니다」**.

🔴 **셋의 공통 모양:** 화면이 「실패가 목록에 없다」를 「고쳐졌다」로 읽는다. 그런데 그 목록은
**한 상태만** 보고, 그 사이 상태 둘은 아무 목록에도 안 뜬다.

### D-⑩ 어드민 대시보드는 **WebSocket 클라이언트가 아니다**

`FAILURE_MANAGEMENT_SPEC §4.2` 는 재시도 성공 시 「실시간 WebSocket 리프레시 이벤트를 UI
클라이언트에 전송」한다고 적고, 같은 스펙 §5 는 그 UI 를 **어드민 대시보드**로 명시한다.

```
admin.html <script>       ./src/admin.js  (+ Monaco CDN 로더 + 테마 인라인)   그것뿐
admin.js 소스              WebSocket  0건
admin-eErqdtgQ.js (출하)   WebSocket 0 · file_ingestion_completed 0 · batch_refresh_required 0
main-M6juM_wA.js (그리드)  셋 다 있음
```
🔴 **이벤트는 «만들어져 브로드캐스트되고», 스펙이 지목한 청중은 그것을 «받지 않는다».**
「양끝이 다 있는데 가운데가 없다」의 변형이다 — 가운데는 있는데 **끝이 다른 페이지**다.

### ⑱ 에서 나온 문서 정정

| 자리 | 적혀 있는 것 | 실측 |
|---|---|---|
| `FAILURE_MANAGEMENT_SPEC.md` §4.2 · §3.1 mermaid | 「백그라운드 스레드(`asyncio.to_thread`)를 기동하여 `err/` 내 격리 파일을 재수행」 | 🔴 **운영 기동에서는 그 코드에 «도달하지 않는다».** 실제 실행자는 `run_watcher.poll_pending_retries`(3초 폴러). 스펙에 `PENDING_RETRY` 도 `DECOUPLED` 도 **한 글자 없다** |
| 같은 §4.2 | 「실시간 WebSocket 리프레시 이벤트를 UI 클라이언트에 전송」 | ⚠️ 전송은 된다. **다만 §5 가 지목한 어드민 화면은 WS 클라가 아니다**(§D-⑩). 게다가 `total_changed > 0` 일 때만 발화 |
| 같은 §3.1 | 「에러를 캐치한 즉시 `err/` 폴더로 **강제 이동**」 | ⚠️ 거절 둘(`_refuse_move_by_retention` · `_refuse_move_of_foreign_source`)이 있고 그때 파일은 제자리에 남는다. 스펙에 두 갈래 모두 없다 |
| 같은 §3.2 | 「`filepath`: 격리 보관된 `err/` 폴더 내의 절대 경로」 | ⚠️ 이동이 거절되면 `raws/`(또는 외부 소스) 절대 경로가 들어간다. **동작은 옳다** — 재시도가 그 경로를 그대로 열기 때문. 문장만 좁다 |
| 같은 §4.1 GET 응답 예시 | 키 5 (`status·total·page·limit·data`) | ⚠️ 실제는 **`oldest_failed_at` 하나 더** |
| 같은 §4.1 POST 응답 | 미기재 | ⚠️ 실제 `skipped_reexpanded` 칸과 「이미 재확장된 붕괴청크는 리셋 안 함」 규칙이 스펙에 없다 |
| 같은 §4.1 | 「워커가 **즉시** 재처리하도록 유도」 | ⚠️ `NOTIFY` 없음. 실제는 LISTEN 2초 폴에 걸려 ≤2초 |
| 같은 §2.2 | 「우측 진단 뷰어에 개별 이벤트 목록이 배지로」 | ⚠️ `tx.events.length > 1` 일 때만 배지 블록이 뜬다 |
| 같은 §3.2 | 「`retry_count`: 사용자가 수동 재시도를 호출한 누적 횟수」 | ✅ 맞다. ⚠️ 다만 **재시도가 성공하면 `error_message`(트레이스백)가 `detail`(대개 `None`)로 덮여 지워진다** — 「에러 필드를 초기화」와 일치하지만 사후 추적 불가라는 점이 어디에도 없다 |
| `CODE_MAP.md` §1.4 라우트 표 | `GET /admin/outbox/failed` = 「outbox 실패 목록(페이징)」 | ⚠️ `page/limit` 은 **그룹 기준**이고 서버는 매 호출 `query.all()` 로 FAILED 전수를 메모리에 올린다 — SQL 페이징이 아니다. `/admin/file-ingestion/failed`·`/retry-failed` 는 표에 **행이 아예 없다** |
| `CODE_MAP.md` §3 🆕⑤ [Retention] | 「`err/` 가 들고 있던 『이 파일은 실패했다』가 사라진다 → 원장의 `status="FAILED"` 행이 그 자리를 받는다」 | ⚠️ **화면 쪽은 안전한데 문장이 그렇게 안 읽힌다.** 원장이 받는 것은 「재처리 차단」이고, **어드민이 읽는 것은 `file_ingestion_logs` 이지 원장이 아니다** — 그 FAILED 행은 retention 모드에서도 그대로 써지고 `filepath` 가 파일이 실제로 있는 자리를 가리키므로 `/failed` 도 `/retry-failed` 도 **정상 동작한다** |

### ⑱ 못 밝힌 것

- **`archive_processed_files` 의 운영 값.** 이 박스는 `false`, 커밋된 `.sample` 은 `true`. 둘 다 운영에 대해 아무 말도 안 한다. 위 정정은 **두 값 모두에서 참인 것만** 적었다.
- **운영이 `run_decoupled_app.py` 로 뜨는지.** 근거는 커밋된 `env={"DECOUPLED":"True"}` 하나다. 다른 방식으로 띄운다면 R-13/R-14 의 🔴/⚰️ 가 **뒤집힌다** — 그때는 `asyncio.to_thread` 경로가 살고 `poll_pending_retries` 가 죽는다.
- **재시도 성공 후 원장 행의 전이.** 실패 시 `signature` 가 `None` 이었다면 원장 키가 `stat:` 형이고 재시도 때는 `sha256:` 형이라 **다른 행이 될 가능성**이 있는데, 이 왕복은 실측하지 않았다.
- **같은 파일이 반복 실패하면 `file_ingestion_logs` 행이 누적되는지.** `_log_ingestion_record` 가 매번 `retry_count=0` 인 **새 행**을 만드는 것은 확인했으나, 목록에서 병합되는지는 안 봤다.
- Monaco CDN 로더가 런타임에 받아오는 코드는 검사하지 않았다(어드민 실패 목록과 무관해 보이나 미확인).

---

## 🔴 목록이 놓친 흐름 **둘** — 「흐름은 «기능»이 아니라 «물음»이다」

§2 의 판별식(「한 기능 안에서 다른 물음에 답하는 경로는 따로 세어야 흐름이 된다」)을 이 넷에 걸었다.

| 이름 | 어디 접혀 있었나 | 왜 «별도» 흐름인가 |
|---|---|---|
| **㉗ 외부 읽기 전용 소스 인제션** | ① 안 | 「이 파일을 누가 «소유»하나」에 답한다. 트리거(`on_modified` 포함)·파서 해석(std 폴백 «없음»)·이동(**절대 안 옮김**)·dedup(강제 내용 해시)·`source_name`·스윕 함수가 **다섯 칸 전부 다르다**. `INGESTION_GUIDE §1.12/§1.12-bis` 는 선언했는데 **`CODE_MAP §3` 에 심볼 12종이 전부 0** |
| **㉘ 런타임 워크스페이스 등록** | ⑱ 의 재시도 폴러 안 | 같은 3초 루프가 «두 물음»에 답한다 — 「재시도할 파일이 있나」와 「**설정이 바뀌어 새 표가 생겼나**」. 후자는 `SYSTEM_RELOAD` → `reload_watcher_cache` → `refresh_dynamic_models` → `sync_new_workspaces` → `_ensure_observer_running` + 스윕 둘이다. 🔴 **그리고 이것이 D-① 의 «유일한 복구 경로»다** — 그 사실이 어느 흐름에도 안 들어가 있으면 「워처가 아무것도 안 본다」의 회복 가능성을 아무도 못 잰다 |

⚠️ 반대로 **따로 세지 «않은» 것**도 적어 둔다: 트리 인제션(F-29)·기동/주기 스윕(F-28)·heavy 레인(F-6)은
전부 **같은 물음에 다른 트리거**다 — 셋 다 `_handle_event` 로 합류한다. 트리거가 다르다고 흐름이 되지는 않는다.

---

## 🔴 「**실패가 «건강한 상태»로 렌더된다**」 — 이 넷에서 센 것

체크리스트의 최대 열린 군이다. 다섯 «모양»으로 갈렸다.
🟢 **전제 재확인:** `server/utils/logger.py` 의 `logger.setLevel(logging.INFO)` 와 `root_logger.setLevel(logging.INFO)`
둘 다 HEAD 에 그대로 있고, 저장소 전건에 `setLevel(logging.DEBUG)`·`LOG_LEVEL` **0건**.
`Watcher.DirectoryWatcher` 는 `Watcher` 의 자식이라 유효 레벨 INFO 를 상속한다 → **아래 `logger.debug` 는 전부 출력 불가.**

### ⓐ 읽기 오류·전제 부재가 **HTTP 200 + 빈 컬렉션** — 화면이 「없음」을 그린다 (**6**)

| # | file:symbol | 화면이 보여 주는 것 |
|---|---|---|
| 1 | `main.py::get_ingestion_workspaces` — `if not os.path.exists(workspace_base): return {"status":"success","data":[]}` | 🔴 **`"success"` 라고 말한다.** 데이터 루트를 못 찾은 것이 어드민 File 탭에서 **「워크스페이스 0개」**. `markSectionUnread` 갈래는 200이 아닐 때만 탄다 |
| 2 | `main.py::get_auto_update_status` — 상태 파일 부재 → `{"status":"success","data":[],"last_updated":null}` | 같은 모양. 스케줄러가 한 번도 안 돈 것과 파일이 사라진 것이 같은 값 |
| 3 | `main.py::get_auto_update_status` — `except` → `{"status":"error", "message":…, "data":[]}` **HTTP 200** | `admin.js` 는 `res.ok`(=200)만 보고 진짜 데이터로 취급 → `autoTables` 빈 집합 → `linkedFailLogs=[]` → **「산출물 인제션 연계 실패 없음」**. `status:"error"`·`message` 를 읽는 클라 코드 **0건** (1차 실측 ⑧ A-15 와 같은 칸, 소비 쪽을 추가로 확인) |
| 4 | `html_topology_parser.parse_matrix_to_records` — `<table>` 부재 / 격자 비었음 (**2자리**) | `return []` — **사유 로그 없이**. 같은 함수의 거절 경로는 사유를 문장으로 내는데 이 둘은 안 낸다 |
| 5 | `html_topology_parser.parse_to_graph` (**2자리**) | `return [], []` 무언 |
| 6 | `html_topology_parser.find_all_paths` | 시작 노드를 못 찾아도 `return []` — 「경로가 없다」와 「그 노드가 없다」가 같은 값 (⚰️ 소비자 0이라 **지금은** 무해) |

🟢 **이 부류에 «속하지 않는» 것도 확인했다**: `get_failed_outbox_events`·`get_file_ingestion_logs`·
`get_failed_file_ingestion_logs` 는 **`try/except` 가 없어** DB 오류가 500으로 나가고 클라가
`markSectionUnread` 로 「모름」을 그린다. 이 저장소가 이미 옳게 닫아 둔 자리다.

### ⓑ 상태가 **모든 목록에서 빠져** 화면이 「실패 0」을 그린다 (**4**)

| # | file:symbol | 화면이 보여 주는 것 |
|---|---|---|
| 7 | `main.py::retry_failed_file_ingestion` (DECOUPLED 분기) | `PENDING_RETRY` 는 어느 라우트 필터에도 없다. 클라 판정이 `f.status === 'FAILED'` 뿐이라 **「✅ 재시도 완료」** + File 카드 **「실패 0건」**. 워처가 죽어 있어도 같다 |
| 8 | `run_watcher.py::poll_pending_retries` | 선점 `status="PENDING"` 을 **처리 전에 커밋**. 그 창에서 워처가 죽으면 폴러도 라우트도 그 행을 안 본다 — **영구 소실**, 되살릴 코드 없음 |
| 9 | `admin.js::retryTransaction` | `setTimeout(…,3000)` 뒤 「목록에 없으면 성공」. 리셋된 tx 는 3초 뒤 **정상적으로** 없다 → 재격리될 예정이어도 「✅ 해제되었습니다」 |
| 10 | `directory_watcher::_log_ingestion_record` | DB 쓰기 실패를 ERROR 후 **삼킨다**. 인제션은 실패했는데 `file_ingestion_logs` 행이 없어 `/failed` 에 안 뜬다. 원장 FAILED 행은 남아 재처리는 막히므로 **파일은 영원히 안 들어오고 화면은 「실패 없음」** |

### ⓒ `logger.debug` 가 침묵을 만든다 — 루트 INFO 라 **한 줄도 안 찍힌다** (**10**)

`server/parsers/directory_watcher.py` 의 `logger.debug` **10곳 전부**. 뜻이 다른 넷만 표로:

| # | symbol | 안 찍히는 사실 | 결과 |
|---|---|---|---|
| 11 | `_process_with_retry` ×2 | 「File vanished before processing」 / 「vanished during debounce」 | 이벤트가 왔는데 아무 기록 없이 사라진다 |
| 12 | `_move_to_err_folder` ×2 · `_archive_file` ×2 | 「File already gone」 / 「File vanished during move」 | `None` 반환 → 호출부가 **원본 경로로 폴백** → `FileIngestionLog.filepath` 가 **없는 파일**을 가리킨다. Retry 를 눌러야 새 트레이스백이 뜬다 |
| 13 | `_refuse_move_by_retention` | 「File left in place (… skipped)」 — 파일당 영원히, **의도된 침묵** | 로그만 보는 운영자는 실패 파일이 `err/` 에 없는 이유를 알 길이 없다 (화면 자체는 안전 — ⑱ 정정 참조) |
| 14 | `_try_dedup_skip` 의 retention/외부 갈래 | 「동일 내용 이미 적재 — 재처리 생략(repeat skip)」 | 파일은 계속 `raws/` 에 있는데 아무 일도 안 일어나고, 그 사실을 말하는 줄이 «영원히» 없다. (내구 기록은 **첫 적재의 SUCCESS 행**이라 설계상 정당) |

⚠️ 나머지 넷(`_consume_external_force_hash` · `_try_path_stat_skip` · `_refuse_move_of_foreign_source` 등)도
같은 이유로 죽어 있다. **「의도된 조용함」과 「출력 불가」는 다른 것이다** — 지금은 둘이 같은 값이라
로그 레벨을 올려도 의도한 것만 나오리라는 보장이 없다.

### ⓓ 「실패 0」을 **「건강」으로 주장** (**3** — 그중 **2는 ⚰️**)

| # | file:symbol | 판정 |
|---|---|---|
| 15 | `WorkspaceWatcher.start()` early return + `poll_pending_retries` 의 무조건 비트 | 🔴 **살아 있음.** 감시 대상 0인 워처가 `/health` 에서 `status:"ok"` · `beats` 증가 (§D-①) |
| 16 | `admin.js::refreshChainHealth` — `total === 0` → 「체인 파이프라인 정상」 | ⚰️ **도달 불가** — `refreshHealthStrip` 호출자 0(정의 1줄 + 주석 1줄뿐), 스트립은 `healthStripEl.style.display='none'`(소유자 판정 「띄 다 빼」). ⚠️ 다만 **같은 파일의 `fetchOverview` 는 주석으로 이 주장을 명시 거부**한다 — 한 화면 안에 같은 0을 다르게 읽는 부품 둘 |
| 17 | `admin.js::refreshFileAndAutoHealth` — `setHealthCard('file','ok','실패 0건','파일 인제션 정상')` | ⚰️ 같은 이유(호출자는 `refreshHealthStrip` 하나, 그 함수의 호출자가 0) |

🔴 **16·17 을 «살아 있는 결함으로 세지 않는다»** — 규칙 ③(도달 불가는 ⚰️ 로 표시)의 자리다.
grep 으로는 살아 보이고, 실제로는 소유자가 내려 둔 화면이다.

### ⓔ 읽는 쪽이 **쓰는 쪽이 안 쓰는 칸**을 읽어 «일반 문구»로 떨어진다 (**2**)

| # | file:symbol | 판정 |
|---|---|---|
| 18 | `websocket.js` → `finishIngestionProgress(…, msg.error_msg)` | 🔴 `file_ingestion_completed` 를 만드는 **세 자리 전부** `error_msg` 를 키로 안 싣는다 → 실패 카드가 **언제나 `'처리 중 예외 발생'`** (§D-④). 출하본에 그 읽기가 들어 있다 |
| 19 | `utils.js::finishIngestionProgress` 의 `okStats` | ⚠️ 성공 쪽 문구가 **`'적재 성공 및 정합성 검증 완료'` 로 하드코딩**돼 `detail` 을 못 받는다. 그래서 **키 결측으로 N행이 버려진 파일**이나 **오프셋에서 재개된 파일**의 카드가 「정합성 검증 완료」로 뜬다(사유는 토스트에만) |

🔴 **19 에 대한 정정 하나** — 「0행 파일이 «정합성 검증 완료»로 뜬다」로 적고 싶어지지만 **틀렸다**:
0행 파일은 `_send_to_upsert` 를 안 타므로 진행 이벤트가 없고, 카드가 «애초에 생기지 않는다»
(`finishProgressCard` 는 `if (!card) return`). 실제로 해당하는 것은 **카드가 이미 있는 SUCCESS-with-caveat**
(키 결측 스킵 · 재개)이다. 위 문장은 그렇게 좁혀 적었다.

### 합계

```
ⓐ 200+빈 컬렉션        6   (그중 3은 html 파서 내부, 소비자 0이라 지금은 무해)
ⓑ 목록에서 빠지는 상태   4   🔴 이 군이 가장 무겁다 — 둘은 «영구 소실»
ⓒ 안 찍히는 debug      10   (directory_watcher 전건)
ⓓ 「0 = 건강」          3   (살아 있는 것 «1», ⚰️ 2)
ⓔ 안 채워지는 칸을 읽음  2
────────────────────────────
살아 있는 것 «23» · 그중 ⚰️ 로 접히는 것 «2» · 「지금은 무해」 «3»
```

---

## 체크리스트 — §4 규칙 그대로 (발명 없음)

### ㉠ 선언된 것이 «실제로» 지나가나 — 아니오
```
🔴 실패 사유가 file_ingestion_completed 의 «칸»에 안 실린다 — 세 발신 자리 전부 (읽는 쪽은 살아 있고 출하됐다)
🔴 인제션 진행 수치(note)가 심박 파일까지 가고 /health 복사 목록에 «없다»
🔴 임베디드 모드는 on_progress_callback 을 «안 넘긴다» — 진행 이벤트가 아예 안 생긴다
⚠️ batch_refresh_message 를 도입한 그 라우트가 두 칸을 «빌더 밖에서» 대입한다 (객체는 동일)
⚠️ 진행 페이로드의 status:"PROCESSING" 이 두 소비자 «모두»에게 무시된다
```
### ㉡ 받는 쪽이 «있나» — 아니오
```
🔴 어드민 대시보드가 WS 클라가 «아니다» — 재시도가 쏘는 이벤트 둘을 아무도 안 받는다
🔴 outbox 진단이 event_uuid · processed_at 을 버린다 · skipped_reexpanded 소비자 0
🔴 HTML 파서의 그래프 팔 전체(공개 API 넷 + TableEdge + is_header_fn 축) 비시험 소비자 0
🔴 격자 거절 사유를 읽는 «프로그램» 0 — 로그 파일뿐이고 그 파일을 읽는 화면이 0 (㉔)
⚰️ GeneralUpdateBatch.silent 는 «이 경로에서» 소비자 0 (다른 경로엔 2)
⚠️ 가르는 물음의 답: 위 넷은 전부 «빼기» 쪽이다 — 없어도 «못 말하게 되는 것»이 없다
```
### ㉢ 끊기면 «시끄러운가» — 아니오(조용함)
```
🔴 감시 대상 0인 워처가 /health 에서 «정상 박동» — 유일한 문장은 아무도 안 읽는 파일의 ERROR 한 줄
🔴 Retry 200 인데 아무것도 재시도 안 됨 — PENDING_RETRY 가 어느 목록에도 안 뜬다
🔴 선점 후 워처 사망 -> PENDING 영구 고착, 되살릴 코드 «없음»
🔴 데이터 루트 부재가 HTTP 200 "success" + 빈 배열 -> 「워크스페이스 0개」
🔴 인제션 로그 DB 쓰기 실패를 삼킨다 -> 실패한 파일이 실패 목록에 «없다»
🔴 directory_watcher 의 logger.debug 10줄이 «한 줄도 안 찍힌다»
⚠️ archive 이동 실패가 「일부러 안 옮김」과 같은 문장·같은 행이 된다
⚠️ 진행 목록 5초 폴이 !res.ok 에서 «타이머 사슬째» 끊기고 멈춘 값이 계속 그려진다
```
### ⚰️ 도달 불가
```
운영 기동의 asyncio.to_thread 재시도 경로 · refreshHealthStrip 계열 카드 둘 ·
HTML 그래프 팔(공개 API 넷 + TableEdge) · _default_is_header 의 매트릭스 결과 · is_header_fn 주입 축 ·
GeneralUpdateBatch.silent(인제션 경로) · 진행 페이로드의 status 칸 · directory_watcher 의 debug 10줄
```

### 🔴 우선순위 — 「운영을 멈추는 것」 > 「거짓을 말하는 것」 > 「안 들리는 것」
```
🔴 멈춤     PENDING 영구 고착 (되살릴 코드가 «없다» — 이 라운드에서 유일하게 «되돌릴 수 없는» 것)
🔴 거짓     감시 0인 워처가 «정상» · Retry 200 인데 무동작 · 데이터루트 부재가 「0개」 ·
           실패 카드가 항상 '처리 중 예외 발생'
🔴 안 들림  격자 거절 사유 · 진행 note · 어드민의 WS 부재 — 값은 있는데 «볼 자리»가 없다
```

---

## 이 라운드가 «측정 방법»에 대해 남기는 것 (제안 — 총괄 판정)

1. **측정 중에 트리가 움직인다.** `bffa792b` 가 측정 도중 `main.py` 를 18줄 줄였고, 같은 라우트를 두 번 잰
   두 수(4087 · 4069)가 «둘 다 맞았다». 2차 실측의 모든 주소를 **심볼로** 적은 이유다.
   → 3차 지시서에 「기준 커밋을 적고, 줄 번호를 인용하지 말 것」을 명시할 것.
2. **`logger.debug` 는 이 저장소에서 «주석과 같다».** 루트가 INFO 로 못 박혀 있어 어느 `debug` 도 안 찍힌다.
   → 「끊기면」 칸을 채울 때 `logger.debug` 를 본 순간 **자동으로 🔇** 로 적어도 된다. 남은 흐름에도 같은 규칙.
3. **「소비자 0」의 가르는 물음이 이번엔 «전부 빼기»로 답했다** (칸 다섯 · API 넷). 1차의 「퍼뜨리기 vs 빼기」
   판별식이 실제로 갈랐다 — 다만 «퍼뜨리기» 사례가 아직 하나도 안 나왔다는 것 자체가 관측이다.
4. **상태 낱말의 «전수»를 세는 칸이 표에 없다.** ⑱ 의 결함 둘은 「이 상태를 «보는» 라우트가 있나」로만
   나왔다. → 3차부터 상태 기계가 있는 흐름은 **「상태 낱말 N개 중 화면이 보는 것 M개」**를 한 줄로 적을 것.

