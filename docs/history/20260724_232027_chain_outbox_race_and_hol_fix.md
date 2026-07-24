# 체인 인제션 Outbox 지연 잔여 수정 (#4 LISTEN 레이스 · #5 실패 head-of-line)

> **도메인:** Server PM · **작성:** 2026-07-24 · **진단서:** `task/chain_outbox_latency.md`
> **선행 이력:** [20260724_230117_chain_outbox_latency_fix.md](20260724_230117_chain_outbox_latency_fix.md) (#2/#1/#3)
> **범위:** 서버 파일만. 경계 계약(이벤트명/페이로드) 불변. 커밋 없음(검수 대기).

## 현상 (진단서 #4/#5)
- **#4 LISTEN-after-check 레이스**: 폴링이 빈 결과일 때 `wait_for_notification`이 **대기마다 새 raw 커넥션으로 `LISTEN outbox_event`를 재등록**했다. 빈 폴링 시점과 LISTEN 등록 사이에 발행된 NOTIFY가 유실되어 최대 2초(timeout) tail latency 발생.
- **#5 실패 head-of-line 블로킹**: 한 그룹 실패 시 `break`로 **배치 전체 중단** + `sleep(1)`. 실패 그룹이 큐 선두(id asc)면 3회 재시도 동안 뒤의 정상 이벤트 전부 정체.

## 조치

### #4 — LISTEN 전용 커넥션 상시 유지 (`OutboxListener`)
`server/chain_ingestion_worker.py`:
- 기존 `blocking_wait` / `wait_for_notification`(대기마다 커넥션 생성·LISTEN 재등록·close)를 **`OutboxListener` 클래스**로 대체. 워커 시작 시 LISTEN 커넥션을 **1회만** 생성·등록하고 워커 수명 동안 재사용한다.
  ```python
  # start_chain_ingestion_worker 루프 밖에서 1회 생성
  listener = OutboxListener(db_session_factory, "outbox_event")
  ...
  if not pending_events:
      await listener.wait(2.0)   # 상시 LISTEN 커넥션에서 대기
      continue
  ```
- **레이스 제거 원리**: LISTEN이 항상 폴링보다 먼저 등록되어 있으므로, 폴링 이후 발행된 NOTIFY는 커넥션 소켓에 버퍼링된다. 대기 진입 직후 버퍼된 통지를 먼저 소비(drain)하여 `select` 이전에 즉시 재폴링을 유도한다.
  ```python
  def _wait_blocking(self, timeout):
      try:
          self._ensure_connection()          # 최초/재생성 시에만 LISTEN 등록
          connection = self._connection
          connection.poll()                  # 등록 전/폴링 이후 버퍼된 통지 먼저 소비
          if connection.notifies:
              while connection.notifies: connection.notifies.pop()
              return True                     # → 즉시 재폴링
          r, w, x = select.select([connection], [], [], timeout)
          if r:
              connection.poll()
              while connection.notifies: connection.notifies.pop()
              return True
          return False
      except Exception as e:                  # 끊김/예외 시 안전 재생성(누수 금지)
          logger.error(f"... resetting listener connection: {e}")
          self._reset_connection(); time.sleep(1.0); return False
  ```
- **가드**: 커넥션 끊김/예외 시 `_reset_connection()`으로 폐기 후 다음 `wait()`에서 새 LISTEN 커넥션 확보(리소스 누수 금지). blocking `select`는 기존대로 `asyncio.to_thread`로 오프로딩(asyncio 루프 비차단). SYSTEM_RELOAD 통지도 같은 채널이라 그대로 공존(깨우기만 하고 판정은 루프 상단 SYSTEM_RELOAD 조회가 담당).

### #5 — 실패 그룹 skip + 동일 target 순서 보존 가드 (`process_pending_groups`)
`server/chain_ingestion_worker.py`:
- 배치 내 그룹 처리 루프를 **`process_pending_groups(db, group_order, groups, rules)`** 로 추출(테스트 가능 seam).
- **`break` 제거**: 실패 그룹은 rollback되어 미처리(`processed_chain=False`)로 남고 `retry_count`만 증가(3회 후 격리 유지). 나머지 그룹은 계속 처리한다.
- **순서 보존 가드(보수적)**: 실패 그룹이 기록하려던 `target_table`을 건드리는 **후속 그룹만** 이번 배치에서 보류한다. 서로 다른 target_table 그룹은 계속 처리된다. target_table은 매퍼 반환값이 아니라 규칙 설정에서 결정되므로 매퍼 실행 없이 정적 추정(`_group_target_tables`)이 정확하다.
  ```python
  blocked_targets = set()
  for tx_id in group_order:
      group_targets = _group_target_tables(groups[tx_id], rules)
      if blocked_targets and (group_targets & blocked_targets):
          continue  # 동일 target 후속 그룹만 보류(retry 미증가, 다음 배치에서 blocker 뒤 재시도)
      success, err, msgs = await process_chain_transaction_group(tx_id, groups[tx_id], db, rules)
      if success:
          ... commit; dispatch_broadcasts_bg(msgs)
      else:
          db.rollback(); ...retry bookkeeping...; db.commit()
          failed_any = True
          blocked_targets |= group_targets   # break 대신 동일 target만 봉쇄
  ```
- **정합성 근거**: 실패 그룹의 매퍼 쓰기는 rollback으로 폐기되어 target에 커밋되지 않는다(유실/중복 없음). 앞선 성공 그룹은 각자 이미 commit되어 rollback 영향 밖. 동일 target을 건드리는 후속 그룹을 보류하므로 "나중 그룹이 먼저 적용되어 순서가 뒤집히는" 회귀가 없다. 보류 그룹은 retry_count를 올리지 않고 다음 배치에서 blocker 뒤에 재시도되며, blocker가 3회 후 격리(quarantine)되면 자연히 진행되어 무한 starvation 없음.

## 사이드 이펙트 분석
- **정합성(#5 skip)**: 실패=rollback→미커밋→재시도. 성공 그룹은 개별 commit. 유실/중복 없음. 동일 target 보류로 순서 역전 방지. ✅
- **커넥션 수명/누수(#4)**: LISTEN 커넥션 1개를 워커 수명 동안 점유(LISTEN/NOTIFY 표준 패턴). 예외/끊김 시 close 후 재생성. 워커 전용 프로세스 풀에서 1커넥션 상시 점유는 허용 범위. ✅
- **레이스(#4)**: LISTEN이 폴링보다 항상 선행 등록 + 대기 진입 시 buffered notify drain → lost-wakeup 창 제거. SYSTEM_RELOAD 동일 채널 공존(깨우기만). ✅
- **경계 계약 불변**: WS 이벤트명(`batch_row_upsert`/`delete`/`batch_refresh_required`)·페이로드·`/internal/events/broadcast` 계약 변경 없음(#2 fire-and-forget 타이밍 그대로). REST/스키마/셀 형태 무관. ✅
- **시그니처 영향**: `blocking_wait`/`wait_for_notification`(모듈 로컬, 호출부 워커 1곳뿐) 제거·대체. 신규 심볼(`OutboxListener`/`process_pending_groups`/`_group_target_tables`)만 추가. `process_chain_transaction_group` 시그니처·반환(3-tuple) 불변. `main.py`/`run_chain_worker.py`는 `start_chain_ingestion_worker`만 임포트하므로 영향 없음. ✅
- **asyncio 블로킹**: `select` 대기는 `to_thread`로 오프로딩 유지. `process_pending_groups`는 그룹당 `await process_chain_transaction_group` 유지. ✅

## 검증
- `cd server && conda run -n assy_manager python -m pytest -q` → **43 passed, 1 failed**.
  - 유일 실패 `tests/test_api.py::test_map_presets_api`는 **본 변경 이전 baseline과 동일**(map preset 무관, 이번 세션 시작 시 동일 실패 확인). 본 수정으로 인한 회귀 **0건**.
  - 체인 관련(`test_api.py::test_chained_ingestion`, `test_chain_payload_resilience.py`) 통과.
- **신규 단위 테스트** `tests/test_chain_hol_scheduling.py`(4건, 모두 통과):
  - 선두 실패 그룹(target_A) 뒤 정상 그룹(target_B)이 같은 배치에서 처리됨(break 없음).
  - 동일 target(target_A) 후속 그룹은 보류(순서 보존), retry 미증가·미처리 유지.
  - 실패→동일 target 보류→다른 target 처리 혼합 순서.
  - `_group_target_tables` 규칙 기반 target 추정 + 순환(source_name)/이벤트타입(CREATE·EDIT) 필터.
- **관찰 이슈**: #4 `OutboxListener`는 SQLite in-memory 테스트에서 실제 LISTEN 경로를 타지 않으므로(라이브 PostgreSQL 폴링 루프 전용) 단위 커버리지 없음. 라이브 검증은 운영 기동 시 필요.

## 수정 파일
| 파일 | 변경 |
|---|---|
| `server/chain_ingestion_worker.py` | #4 `OutboxListener`(상시 LISTEN 커넥션)로 `blocking_wait`/`wait_for_notification` 대체 · #5 `process_pending_groups` 추출(break 제거·동일 target 순서 보존 가드)·`_group_target_tables` 헬퍼 |
| `server/tests/test_chain_hol_scheduling.py` | #5 head-of-line/순서 보존 단위 테스트 4건 신규 |
| `docs/architecture/event_driven_backend.md` | §3.5 Latency 모델에 #4/#5 반영 |
| `docs/process/PROJECT_STATUS.md` | 이슈 #0 상태 갱신 |
| `task/chain_outbox_latency.md` | #4/#5 상태 갱신(보류 → 구현) |
