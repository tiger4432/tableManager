# 흐름 실측 A — ⑩ 원장 적재 · ⑦ 체인 인제션 · ⑧ 스케줄·소급

> **측정 기준 커밋:** `3db82f0e` (측정 중 HEAD 가 **세 번** 움직였다 — §0 참조)
> **칸 정의:** `docs/architecture/SYSTEM_FLOWS.md` §1 그대로. 발명하지 않았다.
> **작성:** Server PM · 2026-09-06

---

## 0. 착수 전에 — 🔴 이 라운드 중에 «지시서가 낡았다»

### ① 번호가 바뀌었다
지시서는 옛 번호(①인제션→원장 · ③체인 · ⑧스케줄)로 왔는데, 측정 중에 `3ea3729e` 가
흐름 목록을 인벤토리에서 다시 뽑아 **열 → 스물둘**로 갈았다. 대응:

```
지시서 ①  인제션 → 원장     ->  «둘로 쪼개졌다»:  새 ①(파일→표) + 새 ⑩(표→원자)
                              이 문서는 «⑩» 을 채운다. 새 ①은 「남은 것 열셋」 소속이라
                              지나가며 잰 것만 §4 에 남긴다
지시서 ③  체인             ->  새 ⑦
지시서 ⑧  스케줄·소급       ->  새 ⑧ (그대로)
```
현재 문서의 「1차 실측 착수 ⑩⑦⑧」 과 정확히 일치한다.

### ② 지시서의 「알려진 이음매」 하나가 측정 중에 «고쳐졌다»
```
지시서:  「uvicorn 에서 체인 워커는 create_task 로 띄우고 아무도 안 보므로
          실패해도 「spawned」가 찍힌다」
실측:    ✅ 였다가 → afc7a7ab (09:59:24, 이 세션 «중») 이 고쳤다
         지금은 chain_task.add_done_callback(_log_chain_worker_exit) 가 달려 있다
```
그래서 아래 표의 C-1 은 **오늘 아침의 그 결함이 아니라 오늘 낮의 상태**다.
🔴 다른 세션과 같은 트리를 쓰는 중이므로 **줄 번호는 유통기한이 있다** — 아래 표는
전부 «심볼»로 적었고, 줄 번호는 인용이 꼭 필요한 자리에만 달았다.

---

## ⑩ 정준 원장 — 적재 (표 → 소스 선언 → 번역기 → 원자)

> 🔴 **먼저 알아야 할 것 하나: 이 흐름에는 «타이머가 없다».** 부팅 호출도 없다.
> `server/migrations/add_ledger_events.py` 가 자기 주석에 적어 둔 그대로 —
> 「부팅에 `server/ledger` 를 import 하는 프로세스가 없다」. 쓰기 경로의 모든 실행은
> **사람이 누른 admin POST 이거나 CLI** 다. 스케줄러는 «나르기만» 한다(⑧과 만나는 자리).

| # | 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 (실측) | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|---|
| L-1 | 브라우저/curl | `main.py::trigger_retroactive_run` | **`POST /admin/retroactive/{op}/run`** (`op=ledger_backfill`), `Depends(require_admin_token_strict)` | HTTP 바디 | 바디 키 `{"params":{...}}` — `params` 는 `retroactive.validate` 가 검사 | 데코레이터 등록 핸들러 1 (규칙상 제외) → **비라우트 호출자 0** | 🔊 `RetroactiveRefused` → HTTP 4xx (`main.py` 의 `except`) | ✅ |
| L-2 | `retroactive.publish` | `database_outbox` + `retroactive_runs` | L-1 과 «같은 요청», 동기 | DB 행 ×2, **한 커밋** | `DatabaseOutbox(event_uuid, table_name="__retroactive__", event_type="RETROACTIVE_RUN", payload={run_id,op,params,requested_by}, processed_chain=False)` + `RetroactiveRun(run_id,op,params,requested_by,state="queued")` → `NOTIFY outbox_event;` | 1 (`retroactive.publish` 가 유일한 writer) | 행은 🔊(durable). **NOTIFY 실패는 🔇** — `except → logger.debug` | ✅ |
| L-3 | outbox 행 | `run_auto_update.start_retroactive_run` → `retroactive.execute` | **outbox `event_type == EVENT_RETROACTIVE_RUN`** (스케줄러 틱이 줍는다) | outbox 이벤트 | `payload` dict → `spec["run"](db, params, log, control)` | 1 (`run_auto_update.py`) | 🔊 이미 실행 중이면 `logger.warning("[Retroactive] a run is already in flight …")` + **행을 미처리로 남김**(다음 틱 재시도). 실패는 `state=RUN_FAILED` + 로그 | ✅ |
| L-4 | `retroactive._run_ledger_backfill` | `ledger.backfill.run` | `OPERATIONS["ledger_backfill"]["run"]` 디스패치 | 함수 인자 | `backfill.run(db.get_bind(), source=params["source"], checkpoint=_checkpoint(control), pace=params.get("pace"))` — 🔴 **`retranslate` 는 안 넘긴다** | 비시험 호출자 2 (`retroactive.py`, `backfill.main()`) · 설정문자열 1(`"ledger_backfill"`) | 🔊 예외가 `retroactive.execute` 의 `except` 로 → 실행 행 `FAILED` | ✅ |
| L-5 | CLI | `backfill.run` | **`python -m ledger.backfill --source <id>`** | argv | `--source --fetch-rows --max-batches --pace --ontology-root --scope-column --scope-values --apply` (`--reset-cursor`/`--from` 은 `destructive_approval_required` 로 거절) | 1 (`__main__`) | 🔊 traceback + `basicConfig(INFO)` | ✅ |
| L-6 | 소스 릴레이션 (예: `lot_event`) | `backfill._fetch_v2_lineage_page` | `_run_v2_lineage` 의 `walk_group_pages` 루프 | DB SELECT | 컬럼은 `v2_base_select_columns(snapshot, source_id)`, 페이징 `WHERE page_key > cursor` | 1 | 🔊 psycopg 예외 → 실행 `FAILED` | ✅ |
| L-7 | `backfill._run_v2_lineage` | `runtime_v2.execute_cursor_batch` | 페이지마다 | 함수 인자 | `execute_selected_cursor_batch(setup, source, frame, next_cursor, _no_join_reader(), store, known_registrations=known, retranslate_approved=approved)` | 각각 비시험 호출자 **1** | 🔊 `LedgerV2RuntimeError(code, path, message)` | ✅ |
| L-8 | `runtime_v2` | `source_preparation.prepare_source_batch` | `preview_cursor_batch` 안 | 함수 인자 | `SourcePreparationContext(snapshot, source_plan)` + frame + reader + implementations — 선언의 `prepare`/`read`/`map`/`bind` 가 몰고 간다 | 비시험 호출자 1 | 🔊 `SourcePreparationError` | ✅ |
| L-9 | `runtime_v2._screened_atoms` | `gate.screen_compiled_molecule` | `with gate.building_molecule(source_id)` 안에서 호출 | 함수 인자 | `(source_id, atoms, declared_derivations, declared_subject_types, molecule_ref=…, source_rows=…)` → `(kept, _report)`, 🔴 **`_report` 는 «버린다»** | 비시험 호출자 1 | 🔊 **하고 «치명적»**: `gate.refuse` 가 로그 후 `MoleculeRefused` 를 raise 하고, 이 경로엔 잡는 곳이 없어 **배치·실행이 통째로 죽는다** | ⚠️ |
| L-10 | `runtime_v2.execute_cursor_batch` | `LedgerStore.write_batch` | L-7 | 함수 인자 | `write_batch(source_id, translator_version, kept_all, dict(cursor_value), molecule_count, refused=0, incomplete=…, reasons={}, enforce_translator_version=not retranslate_approved)` 🔴 **`refused` 와 `reasons` 는 «리터럴»** | 정당 호출자 **2**(`runtime_v2` 두 자리) · 🔴 **두 번째 문 7**(`server/scripts/seed_syn_*.py`) · 시험 6 | 🔊 kwarg 누락 시 `TypeError` → `LedgerV2RuntimeError("unsupported_store_contract","store.write_batch")` | ✅ |
| L-11 | `LedgerStore.insert_atoms` | **`ledger_events`** | `write_batch` 안 | DB INSERT | `envelope.ROW_COLUMNS` **14칸 전부** — `id, subject_type, subject_keys, predicate, object_kind, object_payload, occurred_at, source_who, source_translator_ver, source_raw_ref, supersedes, source_event_id, source_event_state, occurred_at_basis` · `ON CONFLICT DO NOTHING` · `execute_values(page_size=1000)` · 기본값에 맡기는 칸 **0** | 1 (`write_batch`) | 🔇 **행 유실은 조용하다** — `ON CONFLICT DO NOTHING` 이 무표적이라, 반환값의 `attempted > inserted` 차이(`deduped`)로만 보인다 | ✅ |
| L-12 | `LedgerStore._advance_cursor` | **`ledger_translator_cursor`** | `write_batch` 안, `advance_cursor=True` 일 때 | DB UPSERT, **같은 커넥션·같은 커밋** | `(source, translator_ver, cursor_value, molecules_done, atoms_written, atoms_deduped, molecules_refused, incomplete_molecules, refusal_reasons, updated_at)` + `ON CONFLICT (source) DO UPDATE` + 선택 가드 `WHERE …translator_ver = EXCLUDED.translator_ver RETURNING source` | 1 (`write_batch`) | 🔊 `CursorVersionConflict` (RETURNING 이 빈 행일 때) | ✅ |
| L-13 | `ledger_translator_cursor` | 화면 | **`GET /admin/ledger/sources`** (`require_admin_token`) → `ledger_admin.sources_view` | HTTP 응답 JSON | `_CURSOR_FIELDS = (translator_ver, molecules_done, atoms_written, atoms_deduped, molecules_refused, refusal_reasons, updated_at)` + 파생 `refusals_unaccounted` | 라우트 핸들러 1 = **살아 있는 유일한 독자** | 🔊 컬럼 부재 시 500(코드가 카탈로그를 먼저 프로브) | ✅ |
| L-14 | `store.read_cursor` | `backfill._run_v2_lineage` | 실행 시작 시 | DB read | `{source, translator_ver, cursor_value, molecules_done, atoms_written, atoms_deduped, molecules_refused, incomplete_molecules, source_head, head_probed_at, updated_at, refusal_reasons}` | 비시험 호출자 **3** (`_run_v2_lineage`, `rows_past_cursor`, `scripts/ledger_restamp_cursor.py`) | 🔊 모양 불일치 → `LedgerSetupError("legacy_cursor_reset_required"/"cursor_snapshot_reset_required")` | ✅ |
| L-15 | `server/scripts/seed_syn_*.py` (**7**) | `LedgerStore.write_batch` | **CLI**, 각자 `--apply` | 함수 인자 | 예: `write_batch(SOURCE, TRANSLATOR, accepted, cursor_value={"fixture":"complete"}, molecules=len(groups), refused=0, incomplete=0, reasons={})` — 🔴 **선언이 이 원자를 «본 적이 없다»** | 스크립트 7, 공용 호출자 0 | — (CLAUDE.md 가 이미 판정한 «두 번째 문») | ⚠️ |
| L-16 | `gate` 프로세스 카운터 | `retroactive_runs.result` JSON | `_run_v2_lineage` 끝 | 함수 반환 → DB 행 → HTTP | `result["refused_total"] = sum(gate.refusals().values())`, `result["refused_samples"]`, `result["refused_samples_capped"]` | 비시험 호출자 1 | — | ⚰️ **도달 불가** (근거는 §3-①) |
| L-17 | `ledger_events` + 커서 | `ledger_trace.coverage()` | — | — | `CURSOR_FIELDS`, `refusals_unaccounted` | **운영 호출자 0** (시험 4) | 🔇 아무도 안 부른다 | ⚰️ (라우트가 2026-08-28 은퇴하며 독자를 데려갔다) |

### ⑩ 의 핵심 발견 — 「**거절이 «자기 칸»에 못 닿는다**」

```
쓰는 쪽   ledger_translator_cursor.molecules_refused · refusal_reasons
          + _merge_reasons_sql() 의 FULL JOIN 누적 · {reason:{count,last_at}} 모양
읽는 쪽   GET /admin/ledger/sources 가 «살아서» 그 값을 그리고
          refusals_unaccounted 로 REFUSALS_NONE / _NAMED / _UNKNOWABLE 까지 가른다
가운데    🔴 «비어 있다» — 선언 경로에서 그 값이 0 이 아닐 수 있는 코드 경로가 «없다»
```
실측 근거 셋:
1. `runtime_v2` 의 write_batch 두 자리 **둘 다** `refused=0, reasons={}` 가 **리터럴**이다.
2. 거절은 `gate.refuse` 가 `MoleculeRefused` 를 **raise** 해서 나가고, 운영 코드에서
   그것을 잡는 곳은 **seed 스크립트 셋뿐**(`seed_syn_journey_atoms` · `_process_ledger` ·
   `_split_merge_pressure`). 선언 경로엔 **없다** → 배치가 죽고 `write_batch` 는 **안 불린다**.
3. 그래서 `backfill` 이 루프 «뒤»에서 채우는 `refused_total`·`refused_samples` 는
   **거절이 하나도 없었던 실행에서만** 채워진다 → 항상 0. (⚰️ L-16)

⚠️ 이건 「없어서 0」이 아니라 **「구조적으로 0」**이다. 화면은 정상으로 보인다.
📎 그리고 **⑩ 은 이 저장소의 「반쪽」 중 «드문 방향»이다** — 보통은 쓰는 쪽이 살고 읽는 쪽이
   없는데, 여기는 **읽는 쪽이 살아 있고 쓰는 쪽이 닿지 못한다.**
   `ledger_admin.py` 가 이미 절반은 자백하고 있다: 「이걸 읽던 유일한 코드는
   `ledger_trace.coverage` 에 매달려 있었고 그 라우트가 2026-08-28 에 은퇴하며 읽기를
   데려갔다」 — **라우트는 복구됐는데 «쓰기»는 복구되지 않았다.**

---

## ⑦ 체인 인제션 (표 쓰기 → outbox → 규칙 → 맵퍼 → 다른 표 → 다시 outbox)

| # | 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 (실측) | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|---|
| C-1 | `main.py::startup_event` | `chain_ingestion_worker.start_chain_ingestion_worker` | **부팅** (uvicorn startup, 무조건) | `create_task` + **done 콜백** | `chain_task = main_loop.create_task(...)` → `chain_task.add_done_callback(_log_chain_worker_exit)` → INFO `"Chained Ingestion Worker background task spawned."` | 1 (부팅 1회) | 🔊 **이제 시끄럽다**: 콜백이 ERROR `"Chained Ingestion Worker did NOT start - the line above saying it was spawned is about a task that is already gone. Reason: %s: %s"` + `exc_info`. 취소(정상 종료)는 침묵, 무예외 반환은 WARNING | ✅ **(오늘 `afc7a7ab` 이 고쳤다 — 지시서엔 결함으로 적혀 있었다)** |
| C-2 | `run_decoupled_app.py` | `run_chain_worker.py` (별도 프로세스) | **런처의 `ChildSpec("Chained Ingestion Worker", …, heartbeat="chain")`** | 자식 프로세스 | 같은 `start_chain_ingestion_worker` | 1 | 🔊 `except Exception as e: logger.error(f"Exception occurred: {e}")` → `chain_worker.log` | ⚠️ **둘이 «같은 큐»를 노린다** — C-3 이 가른다 |
| C-3 | 심박 파일 | `another_chain_loop_is_running()` | C-1/C-2 진입 직후 | 파일 read (`utils/heartbeat.read_all`) | 셋이 **모두** 참이어야 「돌고 있다」: 비트가 fresh · pid ≠ 자기 · `psutil.pid_exists(pid)` | 1 | 🔊 WARNING `"[Chain Worker] NOT starting: another chain loop is already running (%s). …"` | ✅ (일부러 관대 — 판정 못 하면 «시작»한다) |
| C-4 | `crud.apply_batch_updates` (사람 편집·인제션·체인 자기 쓰기) | `database_outbox` | **행 쓰기** — `@event.listens_for(Session,"before_flush")` | DB 행 + `NOTIFY` | **per-row**: `payload={row_id, business_key, data{col:{value,is_overwrite,updated_by}}, transaction_id, updated_by, source_name, timestamp}` · **collapsed**: `payload={row_ids[≤1000], row_count, table_name, transaction_id, updated_by, source_name, timestamp}` · 행 칸: `event_uuid, event_type, table_name, payload, status="PENDING"` (나머지는 기본값) | 리스너 등록 1 (전역 Session) | 🔇 **`NOTIFY` 실패는 통째로 삼킨다** (`except: pass`). 대가는 유실이 아니라 «2초 폴백 폴링» | ✅ |
| C-5 | `request_outbox_mode` | `stage_collapsed_event` | 축약 **옵트인** | ContextVar | 켜는 곳 **정확히 둘**: `directory_watcher._upsert_to_local_db`(파일 전체 루프) · `chain_ingestion_worker`(파생 쓰기 «한 호출»만) | 2 | — | ✅ (문서 §2.4 의 「둘뿐」 **여전히 참**) |
| C-6 | `database_outbox` | `OutboxListener` / 폴링 | **`LISTEN outbox_event`** (워커 수명 내내 1회 등록) + 2초 타임아웃 폴링 | 소켓 통지 / SELECT | `processed_chain == False` 를 `id asc LIMIT 200`. `SYSTEM_RELOAD` 는 별도 스로틀 질의(1초) | 1 | 🔊 큐 머리가 `heartbeat.DEFAULT_STALE_AFTER_SEC` 동안 안 움직이면 `QueueHeadWatch` 가 ERROR 한 줄(그 간격당 1회) | ✅ |
| C-7 | `chain_rules.json` | `load_chain_rules()` | **워커 기동 1회** + **`SYSTEM_RELOAD` 이벤트** | 파일 read | `data["rules"]` 원문 + `enrichment_config.load_enrichment_chain_rules()` 파생분 병합 → **끝에 `_validate_chain_cascade_graph(rules)`** | 운영 호출자 **3** (기동 · SYSTEM_RELOAD · `chain_replay`) · 시험 3 | 🔴 §3-② 참조 — **기동과 리로드가 서로 다르게 실패한다** | ⚠️ |
| C-8 | 규칙 집합 | 순환 그래프 검증 | `load_chain_rules` 끝 · **그리고** `ledger_admin.save_chain_rule_raw` | 함수 인자 | 규칙 하나가 **엣지 «둘»**: `trigger_table→target_table`, 그리고 `allow_map_metadata_upsert` 면 `trigger_table→map_meta_registrar.META_TABLE`(=`wafer_map_metadata`) | 2 (`load_chain_rules`, `ledger_admin`) | 🔊 `ValueError("allow_chain_trigger cycle: …")` | ✅ |
| C-9 | 운영자 | `chain_rules.json` | **`POST /admin/chain/rules/raw`** → `ledger_admin.save_chain_rule_raw` | HTTP 바디 | `{name, declaration, base}`; `base` 는 fingerprint(낙관적 잠금) · 신규 규칙은 **`enabled=False` 로 착지** · 저장 «전»에 순환 검증 | 라우트 1 + 클라 `admin.js` | 🔊 `chain_cycle` / `stale_base` / `declaration_rejected` refusal 로 거절 | ✅ |
| C-10 | 이벤트 그룹 | `process_chain_transaction_group` | `transaction_id` 로 묶은 그룹 | 함수 인자 | `valid_events = [e for e in events if e.event_type in ["CREATE","EDIT"] and any(rule.trigger_table == e.table_name and enabled and _rule_accepts_event(r,e))]` — 🔴 `DELETE`·`SYSTEM_RELOAD` 는 여기서 **빠진다**(그리고 no-op 그룹으로 `SUCCESS` 확정된다) | 1 | 🔊 실패 시 rollback + `retry_count += 1`, 3회 후 `FAILED` 격리 | ✅ |
| C-11 | 축약 이벤트 | `outbox_expand.expand_events` | C-10 안, 규칙이 붙은 뒤 | DB 재조회 | 본 테이블을 다시 읽어 per-row 와 **같은 중첩 페이로드** 합성 | **운영 호출자 1** (체인 워커 자신) | 🔊 미해결 `row_id` 를 세어 WARNING (표·tx·표본 동봉) | ⚠️ §3-③ |
| C-12 | 워커 | 사용자 맵퍼 (`server/mappers/*.py`, gitignored) | `execute_custom_mapper(module, function, db, payload, rule)` | 함수 인자 | 반환은 `GeneralUpdateBatch` dict — `updates[].{row_id` 또는 `business_key_val, updates{}, source_name="chain_ingestion", updated_by}` | 활성 규칙 **5** 개가 맵퍼 5종을 지목 | 🔊 예외 → 그룹 실패 → 재시도/격리 | ✅ |
| C-13 | 맵퍼 결과 | `crud.apply_batch_updates` | `write_batches` 루프 | 함수 인자 | 순서 고정: **맵 메타데이터 먼저** → 일반 target → scoped/retract. 각 배치는 `chain_key_gate.screen()` 을 **반드시** 통과 | 1 (유일한 통로) | 🔊 키 없는 행은 `key_gate_report["refused_rows"]` 로 걸러지고 심박 note 로 나간다 · 드롭 셀은 WARNING `"⚠️ [Chain Write Discard] …"` | ✅ |
| C-14 | 파생 쓰기 | `database_outbox` (**다시**) | C-13 의 flush | outbox 이벤트 (축약) | `source_name="chain_ingestion"` 이 실린다 → 하류 `_rule_accepts_event` 가 **옵트인 규칙만** 통과시킨다 | 순환 필터 1 | — | ✅ |
| C-15 | 워커 | 웹서버 | **커밋 «후» 인라인 `await`** (`_dispatch_broadcasts`) | `POST /internal/events/broadcast` (admin 토큰, timeout 3s, `trust_env=False`) | `{"event": "batch_row_upsert" / "batch_row_delete" / "batch_refresh_required", …}` | 1 라우트 → `manager.broadcast` | 🔊 실패는 **삼키되** `broadcast_at` 을 NULL 로 남겨 스윕이 재발사 · `[Latency] tx=… wake=…ms mapper=…ms commit=…ms notify=…ms total=…ms ok=<bool>` INFO 1줄 | ✅ |
| C-16 | 웹서버 | 브라우저 | `manager.broadcast(json.dumps(payload))` | WebSocket | 같은 dict 그대로 (릴레이) | `client2/src/websocket.js` 가 **셋 다** 처리 (`batch_row_upsert` · `batch_row_delete` · `batch_refresh_required`) | 🔇 WS 끊김은 이 층에서 안 울린다 | ✅ |
| C-17 | `broadcast_at IS NULL` | `sweep_undelivered_broadcasts` | 워커 루프 `finally`, **5초 스로틀** | DB read + POST | `refresh_targets = affected_targets ∪ source_tables`, 표당 `batch_refresh_required` 1건 dedup, `LIMIT 500` + grace 5s, 부분 인덱스 `idx_outbox_undelivered` | 1 | 🔊 실패는 `[Chain Worker] maintenance pass failed: …` ERROR | ✅ |
| C-18 | `database_outbox` | 운영자 | **`GET /admin/chain/queue`** (`require_admin_token`) | HTTP 응답 | 대기 깊이·나이를 **소유자별로** 가름(`event_constants.outbox_owner`), 자리표시자 표이름(`__retroactive__`)은 표로 안 셈, tx 로 접은 목록 | 클라 `admin.js` → `chain_queue_panel.js` **1** | 🔊 404 면 화면이 「이 서버 프로세스에 … 없습니다 (404) — 재기동이 필요합니다」 | ✅ |

### ⑦ 의 핵심 발견 — 「**가운데 홉을 켜면 «지금은» 거절당한다. 그리고 거절 방식이 «자리마다 다르다»**」

지시서가 확인을 요청한 건. **확인됐고, 통제군으로 기제까지 갈랐다.**

```
실측 (커밋된 .sample 로 재측정 — 라이브와 규칙 플래그가 «동일»하다)
  현행 그대로               ACCEPTED  (엣지 둘: dt_inventory→dt_map · dt_inventory→wafer_map_metadata)
  dt_metadata_to_dt_inventory 를 enabled=true 로 (메모리 안에서만)
                           REFUSED: allow_chain_trigger cycle:
                                    wafer_map_metadata -> dt_inventory -> wafer_map_metadata
  통제군: 같은 플립 + allow_map_metadata_upsert 를 «전부 제거»
                           ACCEPTED   <- 🔴 즉 «둘째 엣지»가 순환을 만든다
```
🔴 **`trigger_table` 이 엣지이고 `source_table` 은 아니다** — 지시서 문장 그대로 참이다.
`dt_inventory_to_standard_dt_map` 은 `source_table="dt_log"` 인데 그래프는 `dt_inventory` 에서
나간다. 뜻이 겹치는 칸이 둘일 때 **코드가 걷는 쪽**을 고르는 그 자리다.

---

## ⑧ Auto-Update 스케줄러 · 소급 (크론/수동 → 수집기 → 표 → 큐)

> **타이머는 «있다» — 다만 OS 크론이 아니라 «프로세스 안의 5초 틱»이다.**
> `MultiDiscoveryScheduler(check_interval=5)` → `time.sleep(self.check_interval)`.
> 크론식은 config 가 아니라 **수집기 스크립트의 첫 20줄 주석**(`# schedule:`)에서 파싱한다.
> 프로세스는 `process_supervisor.py` 가 아니라 **`run_decoupled_app.py`** 의
> `ChildSpec("Auto Update Scheduler", ["run_auto_update.py"], heartbeat="scheduler")` 다.

| # | 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 (실측) | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|---|
| A-1 | `MultiDiscoveryScheduler.run()` | `check_and_run_schedules` → `start_collector` → 데몬 스레드 → `execute_collector` | **`time.sleep(5)` 틱**; 수집기별 만기는 `croniter(cron_expression).get_next()` | 함수 인자 → `threading.Thread` | 크론식은 스크립트 주석에서 파싱(`parse_script_comments`) | 프로세스 내 호출자 1 · 라우트 0 · 시험 4 | 🔊 `logger.error("Collector Execution Failed for table '…'")` **와** `scheduler_status.json` 의 `last_status="FAIL"`+`last_error` → 화면 traceback 뷰어 | ✅ |
| A-2 | `GenericScriptRunnerCollector.execute()` | `<DATA_ROOT>/ingestion_workspace/<table>/raws/` | A-1 수집기 본문 완료 | **파일** (`.tmp` 쓰기 + `os.replace` 원자 rename) | `f"{prefix}_{YYYYmmdd_HHMMSS}.csv"` | 1 (디렉터리 워처 — 흐름 ① 소속) | 🔊 `"Successfully transferred '…' to ingestion queue."` / 실패 시 ERROR 후 re-raise | ✅ |
| A-3 | 사람 클릭 (`admin.js` `.btn-run-now`) | `main.py::trigger_auto_update_run_now` | **`POST /admin/auto-update/run-now`** (STRICT 토큰; 토큰 미설정이면 503) | HTTP 바디 → DB 행 + NOTIFY | 바디 `{table_name, script_name}` (둘 다 `Body(..., embed=True)`) · 행: `event_uuid`, `table_name`=**진짜 표 이름**, `event_type="SCHEDULER_RUN_NOW"` (🔴 **리터럴** — 상수 참조 아님), `payload={table_name,script_name}`, `processed_chain=False` | 라우트 1 + UI 1 | 🔊 200 + INFO. ⚠️ 다만 ack 는 «발행»만 증명한다 — 스케줄러가 사는지 확인하지 않는다 | ✅ |
| A-4 | outbox (`SCHEDULER_RUN_NOW`) | `run_collector_on_demand` → `start_collector` | **5초 폴링** (🔴 `LISTEN` 없음 — A-6) | outbox 이벤트 | `event_type == EVENT_SCHEDULER_RUN_NOW AND processed_chain == False ORDER BY id ASC LIMIT 1`; 읽는 것 `payload.table_name/script_name`; 쓰는 것 `processed_chain=True` | 1 | 🔴 **조용하고, 큐를 막는다** — §3-③ 참조 | 🔴 |
| A-5 | 사람 클릭 (`admin.js` · **그리고** `main.js::runRetroactive` 의 그리드 RedoBanner) | `retroactive.publish` | **`POST /admin/retroactive/{op}/run`** (STRICT 토큰) | HTTP 바디 → **DB 행 둘, 한 커밋** | `database_outbox`: `table_name="__retroactive__"`, `event_type="RETROACTIVE_RUN"`, `payload={run_id(12-hex),op,params,requested_by}` · `retroactive_runs`: `run_id, op, params, requested_by(없으면 NULL 유지 — 지어내지 않는다), state="queued"` · `db.commit()` 하나 | 라우트 1 · **UI 2** · `publish` 비시험 호출자 1 | 🔊 `RetroactiveRefused`→400, 그 외 500 + ERROR; 성공은 INFO + 토스트 | ✅ |
| A-6 | `NOTIFY outbox_event;` (`retroactive.publish` · `trigger_auto_update_run_now`) | *(의도: 스케줄러)* | A-3/A-5 와 같은 커밋 | PostgreSQL NOTIFY | 채널 `outbox_event`, 페이로드 없음 | 🔴 **이 흐름의 소비자 0** — `grep -c LISTEN server/run_auto_update.py` = **0**. 트리에서 `LISTEN outbox_event` 하는 곳은 체인 워커뿐이고 그것은 두 이벤트를 `CONTROL_EVENT_TYPES` 로 **즉시 건너뛴다** | 🔇 무해(5초 폴링이 덮는다). 다만 **주석 둘이 거짓** | ⚰️ |
| A-7 | outbox (`RETROACTIVE_RUN`) | `handle_retroactive_trigger` | 5초 폴링, `if not self.retroactive_busy():` 로 감쌈 | outbox 이벤트 | 같은 필터 모양; `processed_chain=True` 를 **실행 시작 «전»에** 찍는다(at-most-once); 핸들러 실패 시 `status="FAILED"` **와** `processed_chain=True` 를 함께 | 1 | 🔊 ERROR 로 outbox#·run_id·op 를 이름 붙여 남긴다. 2차 실패도 별도 ERROR(「큐가 아직 이 행 뒤에 막혀 있다」) | ✅ |
| A-8 | `handle_retroactive_trigger` | `retroactive.execute` | `threading.Thread(name="retroactive-run", daemon=True)` | 함수 인자 → 스레드 | payload 그대로 + `log=logger.info`(**`Scheduler`** 로거) | `retroactive.execute` 비시험 호출자 **1** · 시험 7 | 🔊 `logger.error("[Retroactive] runner thread raised: …", exc_info=True)` | ✅ |
| A-9 | `retroactive.execute` | `retroactive_runs` (`_mark_run`, **자기 세션**) | 연산 시작/종료 | DB 행 | 시작: `state="running"`, `started_at`, `last_progress_at`, `runner=name/host/pid` · 종료: `finished_at`, `state∈{done,cancelled,failed}`, `result=json(...)`, `error=str(e)[:2000]` | 모듈 내 독자 5 (`runs`·`in_flight`·`queue_view`·`request_cancel`·`RunControl`) | 🔊 실패해도 죽지 않고, **값으로도** 나간다 — `record_failures()` → `/admin/chain/queue` | ✅ |
| A-10 | 연산의 checkpoint 훅 | `retroactive_runs.last_progress_at/processed_rows/total_rows` | 배치 경계 | DB 행 (자기 세션) | `last_progress_at` 은 항상; `processed_rows`/`total_rows` 는 값이 있을 때만(**NULL=모름, 0 으로 안 적는다**) | 등록된 연산 6 중 **4** 만 `_checkpoint(control)` 를 넘긴다(`chain_replay`·`withdraw`·`enrichment_backfill`·`ledger_backfill`) | 🔇 `except → logger.debug` 인데 **루트가 INFO** (`utils/logger.py:251 root_logger.setLevel(logging.INFO)`) → **그 줄은 안 찍힌다.** 보이는 것은 `in_flight()` 의 `moving="unreported"` 뿐 | ⚠️ |
| A-11 | `retroactive_runs` | 화면 | **`GET /admin/retroactive/runs?limit=50`** → `admin.js::refreshRunning` → `retroactive_view.buildRunsView` | HTTP JSON | 서버는 **13칸**을 보낸다: `run_id, op, label, params, requested_by, state, processed_rows, total_rows, result, error, queued_at, started_at, last_progress_at, finished_at` — **클라는 9칸만 읽는다** | 라우트 1 · UI 1 | 🔊 비정상 응답은 화면의 `failedSources` 에 「실행 목록」으로 남긴다(빈 목록으로 접지 않는다) | ⚠️ §3-④ |
| A-12 | `retroactive_runs` | **`GET /admin/chain/queue`** → `chain_queue_panel.js` + `pickup_state.js` | 어드민 「체인」 탭 갱신 | HTTP JSON, `owners["scheduler"]` 밑 | `blocked_by{run_id,op,params,requested_by,queued_at,state,moving∈{progressing,stalled,unreported},runner,gate_blocked,no_progress_seconds,stall_after_seconds=300.0,processed_rows,total_rows,cancel_reaches∈{at_next_batch,unknown,never},recovery}` · `queue{last_pickup_at,last_pickup_age_seconds,picker_interval_seconds=5,stall_after_seconds=60.0,waiting_count,waiting[]+ahead,orphaned[],record_failures[]}` | 라우트 1 · **UI 2** | ⚠️ **실패 경로가 조용하다**: `except → logger.debug(...)` (안 찍힘) → `blocked_by=null` + `queue` 키 «부재» → 패널이 「막는 것 없음」으로 그린다. 404 는 반대로 시끄럽다 | ✅ / 실패 경로 ⚠️ |
| A-13 | 사람 클릭 | `retroactive_runs.state="cancel_requested"` → `RunControl.stop_requested` (**교차 프로세스**) | **`POST /admin/retroactive/runs/{run_id}/cancel`** | HTTP → DB 행 → 폴링 | `state` 만 쓰고, 연산의 checkpoint 훅이 되읽는다. 한 번 True 면 sticky | 라우트 1 · UI 1 (`cancellable !== true` 면 × 를 감춘다) | 🔊 이미 끝난 실행/모르는 id 는 400 + 이름 붙은 거절 | ✅ |
| A-14 | `heartbeat.beat("scheduler")` | `run_decoupled_app.py` 명부 → `server/health.py` | 매 틱(5초) | 심박 파일 | `note` 없음; `DEFAULT_STALE_AFTER_SEC=60.0` | 1 writer · 1 명부 · 1 reader | 🔊 `/health` 가 stale/wedged 로 보고. ⚠️ 다만 §3-⑤ | ⚠️ |
| A-15 | `_write_status_file` | `<DATA_ROOT>/config/scheduler_status.json` → **`GET /admin/auto-update/status`** | 로드 시 · 수집기 시작/종료마다 · SKIP 마다 | 파일 → HTTP JSON | 수집기별 `table_name, script_name, script_path, cron_expression(또는 "Manual-only"), next_run, last_run, last_status, last_error, active` — `active` 는 라우트가 `auto_update_control.json` 에서 **라이브로 재계산**(토글이 즉시 보이도록) | 라우트 1 · UI 1 | 🔊 화면 traceback 뷰어. ⚠️ 읽기 실패는 `{"status":"error","data":[]}` **HTTP 200** → 화면이 「수집기 없음」으로 그린다 | ✅ |
| A-16 | outbox (`SYSTEM_RELOAD`) | `discover_and_load_collectors()` | 5초 폴링 | outbox 이벤트 | `event_type == "SYSTEM_RELOAD"` (🔴 **리터럴**), `ORDER BY id DESC LIMIT 1`, **`processed_chain` 필터 없음** — 진도는 **메모리 안** `last_reload_event_id` | 1 | 🔊 INFO 두 줄(감지·재스캔 완료) | ✅ / ⚠️ 커서가 프로세스 로컬이라 **스케줄러가 죽어 있던 동안의 리로드는 조용히 삼켜진다** |
| A-17 | `run()` | `config_backup.run_scheduled` | 벽시계 게이트 `CHECK_INTERVAL_SEC = 1800.0` | 함수 인자 → 파일 | `server/config/` 스냅샷 | 1 | 🔊 `[ConfigBackup] maintenance cycle raised: …` ERROR, 수집기를 안 죽인다 | ✅ |

### 「큐」라는 낱말이 이 흐름에서 «넷»을 가리킨다 — 둘만 큐다
```
✅ 진짜 픽업 큐   database_outbox 의 processed_chain=false + event_type ∈ SCHEDULER_OWNED_EVENT_TYPES
                 체인 워커도 같은 행을 보지만 CONTROL_EVENT_TYPES 로 «표시 없이» 건너뛴다
                 -> 이 행을 비우는 것은 스케줄러 «하나»다
✅ 보이는 큐      retroactive_runs 의 state='queued'  — (1) 과 «같은 커밋»에 쓰이는 거울
                 ⚠️ 둘은 어긋날 수 있다: _mark_run 이 실패하면 outbox 행은 소비되는데
                    실행 행은 영원히 queued 로 남는다. 그래서 record_failures() 가
                    로그가 아니라 «큐 옆의 값»으로 나간다
❌ 큐 아님        _collectors_running(set) · _retroactive_thread — 둘 다 «거절»하지 «적재»하지 않는다
❌ 큐 아님        "…to ingestion queue." 로그의 그 큐 = raws/ «디렉터리»
```

---

## 3. 🔴 이 라운드의 발견 — 「끊긴 자리」 여섯

### ① ⑩ — 거절이 자기 칸에 못 닿는다 (⚠️ 반쪽, «드문 방향»)
위 ⑩ 절 참조. 읽는 쪽이 살아 있고 **쓰는 쪽이 구조적으로 0**이다.

### ② ⑦ — `load_chain_rules` 의 거절이 «자리마다 다르게» 끝난다 (⚠️)
지시서는 「기동과 SYSTEM_RELOAD 둘 다 무가드 — 설계된 동작」이라 했다. **절반만 맞다.**
```
기동   start_chain_ingestion_worker 안의 `rules = load_chain_rules()` — 무가드가 «맞다»
       -> 코루틴이 죽고, 이제는 add_done_callback 이 사유를 ERROR 로 꺼낸다 (오늘 afc7a7ab)
리로드  SYSTEM_RELOAD 갈래의 `rules = load_chain_rules()` 는 «루프의 try 안»이다
       -> ValueError 가 `except Exception as e: db.rollback();
          logger.error("Error in Chain Worker execution loop: …"); await asyncio.sleep(3)` 로 잡힌다
       -> 🔴 그리고 `last_reload_event_id` 는 «그 앞에서» 이미 올라갔다
          => 재시도가 «없다». 워커는 «옛 규칙»으로 계속 돌고, 에러는 «한 줄»뿐이다
          => `mark_processed(latest_reload,"SUCCESS")` 도 안 돌지만, 그 행은
             CREATE/EDIT 가 아니라 no-op 그룹으로 SUCCESS 확정되므로 큐는 안 막힌다
```
⚠️ 즉 **운영자가 순환을 만드는 규칙을 저장하고 리로드하면, 화면엔 아무 일도 안 일어나고
   규칙은 «옛 것»이 계속 돈다.** 로그 한 줄이 유일한 신호다.
✅ 다만 그 앞에 문이 하나 더 있다 — `POST /admin/chain/rules/raw` 는 저장 «전»에
   같은 검증기를 돌려 `chain_cycle` 로 **거절**한다(C-9). 손으로 파일을 고칠 때만 위 경로가 열린다.

### ③ ⑧ — 🔴 `SCHEDULER_RUN_NOW` 핸들러가 큐를 «영원히» 막는다 (**이 라운드 최악**)
```python
                        self.run_collector_on_demand(table_name, script_name)
                        latest_trigger.processed_chain = True
                        db.commit()
                    except Exception as trig_err:
                        logger.error(f"Failed to handle SCHEDULER_RUN_NOW trigger: {trig_err}")
```
`except` 가 **rollback 도, `processed_chain` 도, `status="FAILED"` 도 안 쓴다.** 질의는
`ORDER BY id ASC ... .first()` 라 **같은 행이 5초마다 영원히 다시 뽑힌다** — 그 뒤의
모든 on-demand 요청이 그 행 뒤에 선다. 화면에는 아무것도 안 뜬다(로그 ERROR 한 줄이 5초마다).

🔴 **그리고 이건 «이미 판정된 결함»이다.** 바로 아래 형제인 `RETROACTIVE_RUN` 갈래는
같은 파일 안에서 그 수리를 **이미 받았고**, 자기 주석에 이렇게 적어 두었다 —
「A REQUEST THAT THREW IS FINISHED, NOT PENDING, AND LEAVING IT UNMARKED STOPPED PRODUCTION.」
**수리가 두 감시자 중 «하나»에만 적용됐다.**
⚠️ 부수: `run_collector_on_demand` 가 `False` 를 돌려줘도(수집기 없음/이미 실행 중)
반환값을 «안 보고» 행을 처리 완료로 찍는다 → 트리거가 `logger.warning` 하나만 남기고 사라진다.

### ④ ⑧ — 소급 실행의 «결과»가 화면에 안 닿는다 (⚠️ 반쪽)
지시서의 「재적재 시각은 로그 문장 속 글자로만」을 **갈라서** 판정한다.
```
시각    ✅ 배선돼 있다. 다만 화면이 그리는 것은 «경과 분»이지 시각 자체가 아니다
        (`finished_at` 과 `started_at || queued_at` 으로 elapsedMinutes 만 계산)
        `last_progress_at` 은 서버가 보내는데 «읽는 화면이 0»
결과    🔴 «안 닿는다». _mark_run 이 result(cells_written·rows_scanned·inserted·cursor_after…)와
        error 를 쓰고, GET /admin/retroactive/runs 가 실어 보내는데
        buildRunsView 가 만드는 행 객체가 그 둘을 «안 건드린다»
        -> 사람이 읽을 수 있는 유일한 자리는 auto_update.log 의
           `[Retroactive] run_id=… op=… DONE: {result}` 한 줄 = 지시서 문장 그대로
「큐가 막힌 뒤에만」  ⚰️ 그 조건절이 가리키는 갈래는 «아예 못 들어간다» (아래 ⑤)
```

### ⑤ ⑧ — ⚰️ 도달 불가 갈래: `start_retroactive_run` 안의 `if self.retroactive_busy():`
무엇이 도달 불가를 증명하나 — **구조로**:
1. `start_retroactive_run` 의 **비시험 호출자는 `run_auto_update.py:851` 하나**.
2. 그 호출은 `if not self.retroactive_busy():` **안**에 있다.
3. `retroactive_busy()` 는 `self._retroactive_thread` 만 읽고, 그 유일한 대입은
   `start_retroactive_run` **자신** 안에 있다.
4. 둘 사이는 같은 스레드(틱 스레드)이고 동기 질의 + `json.loads` 뿐 — 양보 지점이 없다.

⇒ 그 안의 `logger.warning`, `retroactive_moving_state()`, `return False` 가 전부 죽어 있다.
⇒ 따라서 `_retroactive_last` 는 **쓰기만 있고 읽는 곳이 없다**(§4-①).
⚠️ **행동은 여전히 약속대로 배달된다** — 바깥 게이트(2번)가 질의 자체를 건너뛴다.
   즉 결함이 아니라 **읽는 사람이 기제로 오해할 죽은 코드**다.
📎 라이브 `auto_update.log` 에 그 경고가 55줄 있는데 **55/55 가 `run_id=b`**(시험 픽스처의 리터럴,
   지금은 `OPERATIONS` 에 없는 `graph_orphans`) — 이건 «이 박스»의 수이므로 근거가 아니라
   위 구조 증명의 **방증**으로만 싣는다.

### ⑥ 계측기가 자기 침묵을 만든다 — `logger.debug` 는 «안 찍힌다»
`utils/logger.py` 가 `root_logger.setLevel(logging.INFO)` 로 못 박는다. 그래서 아래 셋은
「실패를 로그한다」고 «쓰여 있지만» 실제로는 아무 줄도 안 남긴다:
```
A-10  RunControl.progress 의 except -> logger.debug("progress write failed …")
A-12  main.py 의 except -> logger.debug("in-flight retroactive unreadable for the queue view")
A-13  cancel 읽기 실패의 debug 줄
```
🔴 A-12 가 특히 나쁘다 — 실패하면 `blocked_by=null` + `queue` 키 «부재»가 되고,
패널은 그것을 **「막는 것 없음」**으로 그린다. 「모른다」가 「괜찮다」로 렌더된다.

---

## 4. 「양끝은 있는데 가운데가 없는」 이음매 — 여덟

| # | 흐름 | 한쪽 끝 | 다른 쪽 끝 | 가운데 |
|---|---|---|---|---|
| 1 | ⑧ | `_retroactive_last` 쓰기 (`:800`) | 읽기 (`:790`) | ⚰️ 읽는 자리가 도달 불가 갈래 안 |
| 2 | ⑧ | `NOTIFY outbox_event` 발행 둘 | 「스케줄러가 소비한다」는 주석 둘 | ⚰️ `run_auto_update.py` 에 `LISTEN` **0** |
| 3 | ⑧ | `retroactive_runs.result`/`error`/`last_progress_at` 쓰기 + 라우트 | `buildRunsView` | 🔴 클라가 그 셋을 **한 번도 안 읽는다** |
| 4 | ⑧ | `health.py` 의 `work.stalled` 승격 로직 | `heartbeat.work_claim` | 🔴 이 경로에 **writer 가 없다**(`work_claim` 은 워처 둘뿐) → 소급 실행이 끼어도 `/health` 는 «영원히» 못 말한다 |
| 5 | ⑩ | `molecules_refused`·`refusal_reasons` 컬럼 + 병합 SQL | `GET /admin/ledger/sources` 의 렌더 | 🔴 0 이 아닌 값을 만들 코드 경로가 **없다** |
| 6 | ⑩ | `LedgerStore.who` 대입 (`store.py:88`) | — | ⚰️ **읽는 곳 0**. seed 7종이 전부 `LedgerStore(engine, who=SOURCE)` 로 부르는데 «아무 일도 안 한다»(원자는 `atom.source_who` 를 쓴다) |
| 7 | ⑩ | `gate` 의 refusal `addresses`(code/path) | 화면 | ⚠️ **preview 에서만** 닿는다(`POST /admin/ontology-explorer/test-run` 은 `except Exception` 으로 잡는다). 진짜 실행에서는 절대 안 닿는다 |
| 8 | ⑦ | `server/mappers/ledger_dt_job_mapper.py` 의 `class MyMapper(BaseLedgerMapper)` | 발견자 | ⚰️ **어느 쪽으로도 안 닿는다** — `chain_rules.json` 에 없고, `implementations._IMPLEMENTATION_MODULE_PREFIX = "ledger_v2_"` 라 import 되지 않는다. ⚠️ 그리고 **그 죽음이 하중을 받고 있다**: 같은 `implementation_id="dt-job-role"` 을 `ledger_v2_dt_job_mapper.py` 도 선언하므로, import 되면 `ImplementationDeclarationError`(id 중복)가 난다 |

⚠️ 8번은 gitignored 사용자 영역(`server/mappers/*`) 파일이라 **「이 박스」 관측**이다.
   다만 «기제»는 커밋된 코드다 — `server/mappers/ledger_*.py` 중 `_v2_` 접두가 없는 것은
   **`chain_rules.json` 을 통해서만** 닿을 수 있다. 그건 어느 박스에서나 참이다.

---

## 5. 지시서의 목록에 «없던» 흐름 — 그리고 번호 밖의 것

- **⑦↔⑧ 은 이음매를 «공유»한다.** `database_outbox` 한 표를 둘이 비우고, 어느 쪽이
  비우는지는 `event_constants.outbox_owner()` 하나가 정한다. `/admin/chain/queue` 는
  이름이 「체인」인데 **스케줄러 버킷도 같이 그린다**. 흐름을 따로 그리면 이 표는
  두 흐름 «사이»에 있어서 어느 표에도 안 들어간다 — **⑦ 과 ⑧ 의 «경계 행»으로 명시해 두는 편이 낫다.**
- **⑩ 의 트리거는 «⑧ 의 몸통»이다.** 원장 적재는 자기 타이머가 없고
  `POST /admin/retroactive/ledger_backfill/run` → outbox → 스케줄러가 실어 나른다.
  즉 **⑩ 의 L-1~L-3 은 ⑧ 의 A-5·A-7·A-8 과 «같은 이음매»다.** 중복이 아니라 «접점»이다.
- **흐름 ① (파일→표) 에서 지나가며 잰 것** — 2차 라운드에 넘긴다:
  `IngestionHandler.on_created/on_moved` → `_handle_event` → 파서 → `_upsert_to_local_db`
  (1,000행 청크, 청크마다 `ingestion_checkpoint.record_chunk_progress` 를 **같은 트랜잭션**에
  실어 원자 커밋, `heartbeat.beat` 는 커밋된 청크마다) → `crud.apply_batch_updates`.
  워처의 HTTP 콜백 넷은 `/internal/events/batch-refresh`(+`created_logs` 500 절단 + `total_log_count`)
  · `/broadcast`(`file_ingestion_progress`) · `/file-processed` · `/ingestion-state` 이고,
  실패하면 `_record_undelivered` 가 `BROADCAST_RECOVERY` 마커를 남긴다.
- **⑧ 의 A-2 가 흐름 ① 의 입력을 만든다** (`raws/` 에 파일을 떨어뜨린다) — 두 흐름의 접점.

---

## 6. 문서가 낡은 자리 (규칙 ①: 「낡았으면 그것이 발견이다」)

| 문서/주석 | 무엇이 낡았나 |
|---|---|
| `chain_ingestion_worker.py` 의 축약 정당화 주석 | 「The graph materializer is their one real consumer」 — 🔴 `graph_materializer.py`·`graph_sync_worker.py` 는 **트리에 없다**. 살아 있는 소비자는 `outbox_expand.expand_events` **하나**(체인 워커 자신)뿐 |
| `event_driven_backend.md` §2.4 | 같은 이유로 「그래프: `resync_table(row_ids=...)` 로 보낸다」가 낡음. ✅ 반면 **「축약을 켜는 곳은 둘뿐」은 실측으로 여전히 참** |
| `retroactive.publish` docstring · `main.py` 의 NOTIFY 주석 | 「`NOTIFY outbox_event`, 스케줄러가 소비」 — 스케줄러엔 `LISTEN` 이 **0** |
| `CODE_MAP.md` 의 `run_auto_update.py` 행 | **840줄**로 적혀 있는데 실제 **1,004줄**; `retroactive_busy()`/`start_retroactive_run` 앵커도 어긋남(668/672 → 724/758). CODE_MAP 자신이 바로 아래 줄에서 「재측정 안 함」이라 경고하고 있다. ✅ **행동 서술**(데몬 스레드 · at-most-once · 이미 실행 중이면 행을 남긴다)은 코드와 일치 |
| `ledger_trace.py` 의 `refusal_reasons` 주석 | 「이것이 존재하는 유일한 named refusal 읽기다」 — **양쪽으로 거짓**: 이 읽기는 죽었고(운영 호출자 0), 살아 있는 것은 `ledger_admin.sources_view` 다 |
| 지시서의 「알려진 이음매」 | 「create_task 를 아무도 안 본다」 — `afc7a7ab`(이 세션 중)이 고쳤다 |

---

## 7. 못 밝힌 것 (추측 금지 — 무엇이 있으면 판정되는지 같이 적는다)

```
① SCHEDULER_RUN_NOW 의 독행이 «같은 틱»의 RETROACTIVE_RUN 까지 막나
   `:980` 의 except 가 db.rollback() 을 안 하고, 바로 다음 줄이 같은 세션으로
   handle_retroactive_trigger(db) 를 부른다. DB 오류였다면 세션이 abort 라 둘 다 서고,
   json.loads 오류였다면 세션은 깨끗해 run-now 만 선다
   -> 판정: payload 는 유효 JSON 인데 처리에서 DBAPIError 를 내는 행을 주입해 보거나,
      그 지점의 session.is_active 를 읽으면 갈린다
② 라이브 retroactive_runs 에 은퇴한 op 를 든 행이 있나 (있으면 in_flight 의
   RetroactiveRefused 갈래가 «살아 있는» 갈래가 된다)
   -> 판정: SELECT DISTINCT op, state, count(*) FROM retroactive_runs GROUP BY 1,2
      (DB 를 안 건드렸다)
③ 라이브 ledger_events 가 schema.CREATE_LEDGER 와 실제로 같나
   schema.py 자신이 「라이브와 신규 배포가 같은 이름으로 «다른» uq_ledger_atom 을 만들었다」를
   기록해 두었다 -> 판정: 라이브에 대고 `\d+ ledger_events`
④ client2/dist 번들이 client2/src 와 일치하나
   위의 «UI 소비자 수»는 전부 src 기준이다. dist 가 낡았으면 그 수는 소스에 대한 참일 뿐
   -> 판정: dist/assets 의 빌드 해시/시각을 src 와 대조
⑤ ⑧ 의 A-15 에서 `bonding_map/fetch_data copy.py` 의 크론 출처
   status 파일은 */60 을 보고하는데 파일명 공백 때문에 주석을 못 읽었다
   -> 판정: 그 파일의 첫 20줄을 읽으면 끝
```

---

## 8. 체크리스트로 나가는 「아니오」 (문서 §4 규칙 그대로, 발명 없음)

```
㉡ 받는 쪽 = 0        ⑧-2 NOTIFY · ⑧-1 _retroactive_last · ⑩ LedgerStore.who ·
                     ⑩ ledger_trace.coverage · ⑦ ledger_dt_job_mapper
㉡ 실질 0 (안 읽힘)   ⑧ result/error/last_progress_at · ⑩ molecules_refused/refusal_reasons
㉢ 끊겨도 조용        🔴 ⑧ SCHEDULER_RUN_NOW 독행(큐 영구 정지) ·
                     ⚠️ ⑦ SYSTEM_RELOAD 순환 거절(옛 규칙으로 계속 돎, 로그 한 줄) ·
                     ⚠️ ⑧ A-12 의 debug 침묵(「모름」이 「괜찮음」으로 렌더) ·
                     ⚠️ ⑩ ledger_events 의 ON CONFLICT DO NOTHING 무표적 유실 ·
                     ⚠️ ⑧ A-15 읽기 실패가 HTTP 200 + 빈 배열(=「수집기 없음」) ·
                     🔇 ⑦ NOTIFY 실패 삼킴(대가는 2초 폴백) ·
                     ⚠️ ⑧ A-16 리로드 커서가 프로세스 로컬(죽어 있던 동안의 리로드 소실)
㉠ 선언 ≠ 실물        ⑩ refused/reasons 가 리터럴 · ⑦ 축약 주석이 없는 소비자를 지목
```
🔴 **우선순위 하나만 고른다면 ⑧-③** — 유일하게 «운영을 멈추는» 것이고,
그 수리는 **같은 파일 안에 이미 있다**(형제 갈래). 부류로 고치면 둘 다 닫힌다.
