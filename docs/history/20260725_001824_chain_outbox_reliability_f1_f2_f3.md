# 체인 인제션 Outbox 신뢰성 후속수정 (F1 전달확정·스윕 · F2 순서보존 · F3 인덱스정렬)

> **도메인:** Server PM · **작성:** 2026-07-25 · **진단서:** `task/chain_outbox_latency.md §총괄 검수 결과`
> **선행 이력:** [20260724_230117](20260724_230117_chain_outbox_latency_fix.md)(#2/#1/#3) · [20260724_232027](20260724_232027_chain_outbox_race_and_hol_fix.md)(#4/#5)
> **계획서(승인):** `agent_workspace/reports/Server_outbox_reliability_plan.md`
> **범위:** 서버 파일 + 문서만. 경계 계약(이벤트명/페이로드/REST 시그니처) 불변, 신규 이벤트 없음. 커밋 없음(총괄 검수 대기).

## 배경 — 총괄 검수(GO-WITH-FIXES)
#2 커밋 우선(commit-before-broadcast) 설계가 지연을 없애는 대가로 통지 신뢰성을 맞바꿔 **핵심가치 #3(실시간 신뢰 전파)** 를 훼손하는 고위험 결함 2건 + 인덱스 버그 1건이 확인됨.
- **F1(높음)**: 통지 유실(웹서버 재시작/타임아웃 3s 초과/HTTP 실패) → `processed_chain=True`라 재발사 경로 전무 → DB는 교정됐으나 그리드가 **영구 stale**.
- **F2(중~높)**: 성공 그룹마다 독립 배경 태스크로 통지 발사 → 동일 `target_table` 두 그룹 통지가 병렬 도착·**역전**(늦게 커밋된 최종값이 먼저 도착 시 화면이 구값으로 굳음).
- **F3(중)**: tx 보완 쿼리 `.as_string()`(→`CAST(payload -> 'transaction_id' AS VARCHAR)`)가 표현식 인덱스 `idx_outbox_txid`(`payload ->> 'transaction_id'`)와 식이 달라 **인덱스 미사용**.

## 조치

### F1 — 전달 확정 추적(`broadcast_at`) + 미전달 안전망 스윕
`server/database/models.py` · `server/chain_ingestion_worker.py` · `server/main.py` · `server/scripts/setup_db_performance.py`
- **`broadcast_at`(nullable timestamptz) 컬럼 추가**(`DatabaseOutbox`). 커밋 직후: 통지할 메시지가 있는 그룹은 `NULL`(미확정), 통지할 것이 없는 no-op 그룹(순환 필터 등)은 즉시 `func.now()` 스탬프(스윕 무한재발사 방지).
- **전달 확정 스탬프**: 배경 통지 태스크 `_dispatch_broadcasts`가 그룹의 **모든** 메시지 HTTP 성공 시에만 별도 짧은 세션(`_stamp_broadcast_at_sync`)으로 `broadcast_at`을 찍는다. 일부라도 실패 시 `NULL` 유지 → 스윕이 회수. `post_event_async`는 전달 확정 여부(`bool`)를 반환하도록 시그니처 확장(반환값은 스탬프 판정에만 사용, **처리 성공/재시도 판정엔 절대 불반영**).
- **미전달 스윕(`sweep_undelivered_broadcasts`)**: 워커 메인 루프에서 최소 5초 간격(throttle)으로 `processed_chain=true AND status='SUCCESS' AND broadcast_at IS NULL AND created_at < now()-5s`인 행을 `id asc LIMIT 500`으로 감지 → `_group_target_tables`로 영향 `target_table` 유도 → **table당 1건 dedup**된 `batch_refresh_required` 재발사 → 전부 성공 시 해당 행 `broadcast_at` 확정. `broadcast_at IS NULL` durable 마커라 **워커 재시작에도 복구**(eventual delivery).
- **부분 인덱스 `idx_outbox_undelivered`**(`(id) WHERE processed_chain=true AND status='SUCCESS' AND broadcast_at IS NULL`): 정상 상태에선 거의 빈 인덱스 → 1000만행 누적에도 스윕이 **O(미전달)**. `models.py`(create_all)와 `setup_db_performance.py`(운영 멱등) 양쪽 반영.
- **백필 마이그레이션(필수)**: 컬럼 **최초 생성 시에만**(ADD COLUMN 성공/`information_schema` 부재 게이팅) 기존 처리완료 행을 `COALESCE(processed_at, created_at)`로 **1000행 청킹 백필**. `main.py` 기동 마이그레이션(`processed_chain` 선례 옆) + `setup_db_performance.py` 양쪽. 백필 없으면 기존 outbox 전량이 미확정으로 오인돼 스윕이 **대량 오발사(refresh storm)**. 게이팅으로 재기동 시엔 백필 skip → 진짜 미전달 행을 덮어쓰지 않아 재기동 중 stale 재발 방지.

### F2 — 그룹 간 브로드캐스트 순서 보존(F1과 통합)
`server/chain_ingestion_worker.py` `process_pending_groups`
- 성공 그룹마다 즉발하던 `dispatch_broadcasts_bg`를 제거하고, 배치 내 성공 그룹 통지를 `group_order` 순서의 `pending_broadcasts: List[(event_ids, messages)]`로 누적 → 배치 종료 시 **단일 순차 태스크** 1회 발사. `_dispatch_broadcasts`가 그룹 간·그룹 내(삭제→upsert) 모두 직렬 전송하여 도착 역전 제거. 여전히 commit 경로 밖 fire-and-forget(#2 지연 이득 유지).
- `process_pending_groups`/`dispatch_broadcasts_bg`/`_dispatch_broadcasts` 시그니처에 `db_session_factory`/`pending_broadcasts` 추가. 호출부(`start_chain_ingestion_worker` 1곳)·테스트 연쇄 갱신.

### F3 — `idx_outbox_txid` 실사용(쿼리 단독 수정)
`server/chain_ingestion_worker.py:~532`
- `DatabaseOutbox.payload['transaction_id'].as_string()` → **`type_coerce(DatabaseOutbox.payload, JSONB)['transaction_id'].astext`**(→ `payload ->> 'transaction_id'`로 컴파일, 인덱스식과 일치). 컬럼 타입이 `JSON().with_variant(JSONB)`라 제네릭 JSON comparator엔 `.astext`가 없어 `type_coerce(..., JSONB)` 경유 필수. import `type_coerce`·`text`·`JSONB`·`func` 추가. **인덱스·마이그레이션 변경 없음**(기존 인덱스 재사용).

## 이전 이력 정정 (요구사항)
- [20260724_232027](20260724_232027_chain_outbox_race_and_hol_fix.md)의 "**순서 보존**" 주장(§#5, line 50·65)은 **동일 `target_table` 후속 그룹 보류에 한정**된 것이며, **그룹 간 통지 도착 순서 자체는 보장하지 않았다**(그룹마다 독립 태스크 발사 → 병렬 도착 역전 = F2). 본 수정(F2 단일 순차 발사)으로 그룹 간 도착 순서를 group_order로 직렬화하여 비로소 보장한다.
- 같은 이력의 #2 서술은 통지 유실 시 "재시도 안 함"으로만 적어 #3(실시간 신뢰 전파) 대비 **복구 부재(F1)** 위험을 미고지했다. 본 수정(broadcast_at + 스윕)으로 eventual delivery 복구 경로를 추가했다.

## F4/F5 — 문서화(코드 수정 없음)
`docs/architecture/event_driven_backend.md §3.6`에 명시:
- **F4**: 순서 보존은 "동일 `target_table`" 정적 추정 기반 → **매퍼가 다른 테이블을 read해 계산하는 교차 테이블 의존은 순서 보장 안 됨**. 필요 시 규칙 스키마에 선언적 `depends_on` 검토.
- **F5**: 3회 실패 격리 후 후속 그룹이 "적용된 적 없는 선행" 위에서 계산될 수 있음(교차 의존 시 산출물 부정확 가능, 단 실패 그룹 쓰기는 rollback이라 유실/중복은 없음).

## 사이드 이펙트 분석 (SDP §1)
- **경계 계약 불변**: WS 이벤트명(`batch_row_upsert`/`batch_row_delete`/`batch_refresh_required`)·페이로드·`/internal/events/broadcast`·REST 시그니처·셀 형태 전부 무변경. 스윕 복구는 기존 `batch_refresh_required`(`table_name`, `change_count`) 재사용, 신규 이벤트 없음. ✅
- **데이터 무결성**: `broadcast_at`은 append-only nullable, 기존 행 NULL 허용. 백필은 `broadcast_at IS NULL`만 대상(멱등). 레이어링(CellSource/priority) 무관. ✅
- **확장성(1000만행)**: 스윕은 부분 인덱스 + `LIMIT 500` + grace(5s)로 O(미전달). 백필은 1000행 청킹. 스탬프는 짧은 세션 즉시 close(풀 즉시 반납). ✅
- **시그니처 전파**: `process_pending_groups`(+`db_session_factory`)·`dispatch_broadcasts_bg`(+`db_session_factory`, `messages`→`pending_broadcasts`)·`_dispatch_broadcasts`·`post_event_async`(→`bool`) 변경. Grep 결과 호출부는 워커 내부 1곳 + 테스트뿐, 전수 연쇄 갱신 완료. `main.py`/`run_chain_worker.py`는 `start_chain_ingestion_worker`만 임포트 → 영향 없음. ✅
- **커넥션 풀**: 스윕(메인 세션) + bg 스탬프(짧은 세션) 동시성 → 짧은 세션 즉시 close·grace/throttle로 완화. 워커 전용 프로세스 풀 여유는 **런타임 실측 권장**. ⚠️
- **런타임 버그 수정**: 반제품에 `sweep_undelivered_broadcasts`가 `text()`를 쓰는데 import 누락(NameError, 단위테스트가 sweep 미커버라 미검출) → `text` import 추가로 해소. ✅

## 검증
- **단위 테스트** `tests/test_chain_hol_scheduling.py` — 기존 4건 + **신규 2건**(F1/F2) = **6/6 통과**(독립 러너, conftest가 psycopg2 부재로 컬렉션 실패하므로 우회 실행).
  - `test_broadcasts_dispatched_once_in_group_order`(F2): 성공 그룹 통지가 그룹마다 독립 발사되지 않고 group_order 순서로 단일 발사에 누적.
  - `test_noop_group_stamped_and_message_group_deferred`(F1): no-op 그룹은 즉시 `broadcast_at` 확정(스윕 제외), 메시지 그룹은 커밋 시 NULL 유지.
- `py_compile` — 수정 4개 파일 정상.
- **런타임 검증 필요(코드만으로 불가, psycopg2/Postgres 부재)**:
  1. `EXPLAIN ANALYZE`로 F3 `idx_outbox_txid` 사용 + 스윕 `idx_outbox_undelivered` 사용 확인(대량 SUCCESS 누적 하).
  2. `/internal/events/broadcast` 실패 주입 → `broadcast_at` NULL 유지 → grace 후 스윕이 `batch_refresh_required` 재발사·확정 → 재발사 멈춤(eventual delivery 실측). 워커 재시작 복구.
  3. 백필 마이그레이션 실행(기존 outbox 대량 행) 후 스윕이 전량 오발사하지 않음 확인.
  4. 커넥션 풀 압박(스윕 + bg 스탬프) 실측.

## 수정 파일
| 파일 | 변경 |
|---|---|
| `server/chain_ingestion_worker.py` | F1 `broadcast_at` 스탬프(`_stamp_broadcast_at_sync`)·미전달 스윕(`sweep_undelivered_broadcasts`)·no-op 즉시확정 · F2 배치 단일 순차 발사(`pending_broadcasts`) · F3 `type_coerce(JSONB).astext` · `post_event_async`→bool · import(`type_coerce`,`text`,`JSONB`,`func`) |
| `server/database/models.py` | `broadcast_at` 컬럼 + 부분 인덱스 `idx_outbox_undelivered` |
| `server/scripts/setup_db_performance.py` | `idx_outbox_undelivered` + `broadcast_at` 컬럼 게이팅 보정·1회 청킹 백필 |
| `server/main.py` | 기동 마이그레이션에 `broadcast_at` ADD COLUMN + 최초생성 1회 청킹 백필 |
| `server/tests/test_chain_hol_scheduling.py` | F1/F2 단위 테스트 2건 + `FakeEvent.id`/`broadcast_at` · 시그니처 반영 |
| `docs/architecture/event_driven_backend.md` | §3.6 신뢰성 모델(F1/F2/F3) + F4/F5 한계 명시 |
| `docs/process/PROJECT_STATUS.md` · `task/chain_outbox_latency.md` | 이슈 #0 상태 갱신 |
