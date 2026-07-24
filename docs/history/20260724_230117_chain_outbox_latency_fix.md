# 체인 인제션 Outbox 반응 지연 수정 (Commit-before-Broadcast + Outbox 부분 인덱스)

> **도메인:** Server PM · **작성:** 2026-07-24 · **진단서:** `task/chain_outbox_latency.md`
> **범위:** 서버 파일만 수정. 클라이언트/경계 계약 변경 없음.

## 현상
체인 인제션 outbox 반응이 **간헐적으로 느린 경우**가 존재. 처리량 버스트 시 폴링 사이클 전체가 느려지고, 특정 그룹 처리 시 최대 수십 초 정체.

## 근본 원인 (진단서 착수 순서)
1. **#2 동기 HTTP 브로드캐스트가 commit 앞에 위치 (간헐 지연 직접 원인)**: `process_chain_transaction_group()`이 내부에서 `/internal/events/broadcast`를 `await`(타임아웃 20초)한 **완료 후에야** 호출부가 `processed_chain=True; commit`. 그룹은 `group_order` 순차 처리 → 웹서버 지연/미응답 시 그룹당 최대 20초(delete+upsert면 ~40초) 대기하며 뒤 그룹 전부 정체.
2. **#1 `event_type` 무인덱스 매-루프 스캔 (상시 저하)**: 폴링 while 루프 매 반복마다 `event_type=='SYSTEM_RELOAD'` 조회를 인덱스 없이(PK 역스캔) 수행.
3. **#3 인덱스 부재**: `processed_chain`가 비부분 boolean 인덱스(전체 행 색인), tx 보완 쿼리의 `payload->>'transaction_id'` 표현식 무인덱스.

## 조치

### #2 — 커밋 우선 → 통지 후행 (fire-and-forget)
`server/chain_ingestion_worker.py`:
- `process_chain_transaction_group()`가 브로드캐스트를 **인라인 전송하지 않고 메시지를 수집**하여 반환하도록 변경. 반환 시그니처를 `(success, error_reason)` → `(success, error_reason, broadcast_messages)`로 확장.
- 호출부는 **데이터 처리 성공 후 `commit`을 먼저 확정**한 뒤에만 통지를 배경 태스크로 발사:
  ```python
  if success:
      for event in events_in_tx:
          event.processed_chain = True
          event.status = "SUCCESS"
      db.commit()
      dispatch_broadcasts_bg(broadcast_messages)  # 커밋 이후 fire-and-forget
  ```
- `dispatch_broadcasts_bg()`는 `asyncio.create_task`로 발사 후 즉시 반환(폴링 루프 비차단). 태스크 참조를 `_background_broadcast_tasks` 셋에 보관해 GC 유실 방지, done 콜백으로 정리.
- 통지 실패는 **로깅만 하고 삼킴**(`_dispatch_broadcasts` + `post_event_async` 내부 try/except). 통지 성공/실패는 `success`/재시도에 **절대 반영되지 않음** → 이미 커밋된 그룹의 재처리/중복 없음.
- HTTP 타임아웃 20초 → **3초**로 축소.
- **경계 계약 불변**: `batch_row_upsert`/`batch_row_delete`/`batch_refresh_required` 이벤트명·페이로드 형식 그대로. 삭제 이벤트를 upsert보다 먼저 큐잉해 순서 보존.

### #1 — SYSTEM_RELOAD 부분 인덱스 + 조회 스로틀
- `server/database/models.py` `DatabaseOutbox`: `idx_outbox_reload` = `(event_type, id) WHERE event_type='SYSTEM_RELOAD'` 부분 인덱스 추가.
- `server/chain_ingestion_worker.py`: SYSTEM_RELOAD 조회를 매 루프가 아니라 **최소 1초 간격(`RELOAD_CHECK_INTERVAL`)으로 스로틀**(`time.monotonic()` 기반). reload 감지 시맨틱은 유지(최대 1초 지연 허용).

### #3 — 미처리/tx 부분·표현식 인덱스
- `server/database/models.py` `DatabaseOutbox`:
  - `processed_chain` 컬럼의 `index=True` 제거 → `idx_outbox_unprocessed` = `(processed_chain, id) WHERE processed_chain=false` 부분 인덱스로 대체.
  - `idx_outbox_txid` = `((payload->>'transaction_id'))` 표현식 인덱스. **PostgreSQL 전용**이므로 `if not is_sqlite` dialect 가드(기존 `DataRow` GIN/trgm 패턴과 동일).
- `server/scripts/setup_db_performance.py`: 위 3개 인덱스를 기존 운영 DB에 멱등 반영하는 `CREATE INDEX CONCURRENTLY IF NOT EXISTS` 스텝 + `ANALYZE database_outbox` 추가.

### #4/#5 — 보류 (분석만)
진단서 지침대로 리스크(타이밍/커넥션 로직 변경)가 있어 **구현하지 않고 분석만 남김**. 상세는 `task/chain_outbox_latency.md` 및 PROJECT_STATUS #0 참조.
- #4 LISTEN-after-check 레이스: 현재 `wait_for_notification`이 대기마다 새 커넥션으로 LISTEN을 재등록 → 빈 폴링과 등록 사이 NOTIFY 유실 시 최대 2초 tail. 개선안: LISTEN 전용 연결 상시 유지 + 등록 직후 re-poll. 커넥션 수명/세션 관리 변경이라 회귀 위험.
- #5 실패 head-of-line 블로킹: 현재 실패 시 `break` + `sleep(1)`로 선두 실패 그룹이 뒤 정상 그룹 정체. 개선안: 실패 그룹만 skip하고 개별 백오프/격리. 그룹 간 커밋 경계·재시도 카운트 상호작용 재설계 필요.

## 사이드 이펙트 분석
- **재시도/정합성**: 재시도는 오직 `apply_batch_updates` 등 실제 처리 실패로만 트리거. 통지 실패는 재큐잉/재처리를 유발하지 않음(커밋 이후 발사). ✅
- **경계 계약**: WS 이벤트명·페이로드 형식 불변, 타이밍만 이동. ✅
- **시그니처 변경**: `process_chain_transaction_group` 반환 2-tuple → 3-tuple. 호출부 전수 갱신 — 워커 루프(반환 언팩), `tests/test_chain_payload_resilience.py`(3-tuple 언팩). `tests/test_api.py`는 반환값을 무시하므로 영향 없음. ✅
- **DB dialect 호환**: 부분 인덱스(`postgresql_where`)는 SQLite에서 조건 무시된 일반 인덱스로 생성되어 create_all 안전. 표현식 인덱스는 `is_sqlite` 가드. ✅
- **타이밍/레이스**: reload 스로틀은 최대 1초 감지 지연만 허용(rare event). fire-and-forget 태스크는 참조 보관으로 GC 유실 방지, HTTP만 사용해 워커 DB 세션과 무관. ✅

## 검증
- `cd server && conda run -n assy_manager python -m pytest` → **39 passed, 1 failed**.
  - 유일 실패 `tests/test_api.py::test_map_presets_api`는 **본 변경 이전 baseline에서도 동일하게 실패**(map preset 무관 이슈). `git stash`로 원본 대조 확인 완료 → **본 수정으로 인한 회귀 0건**.
- 체인 관련 테스트(`test_chain_payload_resilience.py`, `test_api.py::test_chained_ingestion`)는 통과. SQLite in-memory create_all에서 신규 outbox 인덱스 생성 정상.

## 수정 파일
| 파일 | 변경 |
|---|---|
| `server/chain_ingestion_worker.py` | #2 커밋 우선/통지 후행, fire-and-forget 디스패처, 타임아웃 3초, #1 reload 조회 스로틀 |
| `server/database/models.py` | `DatabaseOutbox` #1/#3 부분·표현식 인덱스, `processed_chain` 전체 인덱스 제거 |
| `server/scripts/setup_db_performance.py` | 운영 DB용 멱등 outbox 인덱스 생성 + ANALYZE |
| `server/tests/test_chain_payload_resilience.py` | 3-tuple 반환 언팩 갱신 |
| `docs/architecture/event_driven_backend.md` | §3.5 폴링·브로드캐스트 지연 최적화 추가 |
