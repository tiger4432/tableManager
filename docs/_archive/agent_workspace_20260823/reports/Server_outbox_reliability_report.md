# [Server PM 완료 보고서] 체인 outbox 신뢰성 후속수정 (F1/F2/F3)

> **발신:** Server PM | **수신:** 총괄 PM(lead) | **작성:** 2026-07-25
> **계획서:** `agent_workspace/reports/Server_outbox_reliability_plan.md`(승인) | **지시서:** `agent_workspace/tasks/Server_outbox_reliability_task.md`
> **상태:** 구현 완료, **커밋/스테이징 안 함**(총괄 검수 후 lead가 커밋). working tree에 그대로 둠.

## 0. 이어받기 판정 — 무엇이 돼 있었고 무엇을 채웠나
이전 세션이 F1/F2/F3의 **코드 본체는 거의 완성**한 상태로 중단(4개 파일 수정, 문법 정상, 커밋·보고서 없음). 계획서와 전수 대조 결과:

**이미 돼 있던 것 (검증 후 그대로 채택)**
- F1: `broadcast_at` 컬럼(`models.py`), 부분 인덱스 `idx_outbox_undelivered`(`models.py`+`setup_db_performance.py`), 전달확정 스탬프(`_stamp_broadcast_at_sync`), `_dispatch_broadcasts` all-ok 스탬프, no-op 즉시확정, 미전달 스윕(`sweep_undelivered_broadcasts`)·throttle(5s)·grace·LIMIT 500, `post_event_async`→bool.
- F2: `pending_broadcasts` 누적 + 배치 종료 단일 순차 발사. 단위 테스트 2건.
- F3: `type_coerce(payload, JSONB)['transaction_id'].astext` 쿼리 수정 + import.

**빠져 있어 내가 채운 것 (핵심)**
1. **⛔ 백필 마이그레이션 전면 누락** — 계획서 §1.4(d)가 "필수"로 못박은 백필이 어디에도 없었다. 컬럼만 추가되고 기존 처리완료 행은 `broadcast_at=NULL`로 남아, 배포 즉시 스윕이 **outbox 전량을 미전달로 오인해 대량 refresh 오발사(refresh storm)** 하는 상태였다.
   - `server/main.py` 기동 마이그레이션(`processed_chain` ADD COLUMN 선례 옆)에 `broadcast_at` ADD COLUMN + **컬럼 최초생성 시에만** 실행되는 1000행 청킹 백필(`COALESCE(processed_at, created_at)`) 추가.
   - `server/scripts/setup_db_performance.py`에 `information_schema` 게이팅 ADD COLUMN + 동일 청킹 백필을 **인덱스 생성 루프 직전**에 추가(부분 인덱스가 `broadcast_at`을 참조하므로 컬럼 선존재 보장 + 운영 스크립트 단독 실행 안전).
   - **게이팅이 핵심**: ADD COLUMN 성공(=최초 배포)에만 백필. 재기동 시엔 skip → 진짜 미전달 행(NULL)을 백필이 덮어쓰지 않아 **스윕이 회수**(재기동 중 stale 재발 방지).
2. **런타임 크래시 버그** — `sweep_undelivered_broadcasts`가 `func.now() - text("interval '5 seconds'")`로 `text()`를 쓰는데 import에 `type_coerce`만 있고 `text` 누락. 스윕 첫 실행 시 **NameError로 워커 크래시**. 단위테스트가 sweep 경로를 안 타 미검출이었다. `from sqlalchemy import type_coerce, text`로 수정.

## 1. F1/F2/F3 최종 명세 준수
- **F1** = 계획서 승인안 (A) `broadcast_at` 추적 + 복구는 table-level `batch_refresh_required` + 백필. 그대로.
- **F2** = 그룹별 즉발 제거 → 배치 종료 시 group_order 순차 단일 태스크 1회(commit 경로 밖). 그대로.
- **F3** = `type_coerce(payload, JSONB)['transaction_id'].astext`(→`->>`), 기존 `idx_outbox_txid` 재사용, 마이그레이션 무변경. 그대로.

## 2. 경계 계약 불변 확인
WS 이벤트명(`batch_row_upsert`/`batch_row_delete`/`batch_refresh_required`)·페이로드 형태·`/internal/events/broadcast`·REST 시그니처·셀 형태 `{value, is_overwrite, priority_source}`·스키마 계약 **전부 무변경**. 스윕 복구는 기존 `batch_refresh_required` 재사용, **신규 이벤트 없음**.

## 3. 확장성 (1000만행)
- 스윕: 부분 인덱스 `idx_outbox_undelivered`(정상 시 거의 빈 인덱스) + `LIMIT 500` + grace(`created_at < now()-5s`) → O(미전달). 과다/중복 refresh 가드: table당 1건 dedup, no-op/미매핑 행은 확정 스탬프로 무한 재스윕 차단.
- 백필: 1000행 청킹(락/WAL 부담 최소화).
- 스탬프: 짧은 세션 즉시 close(커넥션 풀 즉시 반납).

## 4. 사이드 이펙트 체크리스트 (SDP §1)
- [x] 경계 계약(이벤트/페이로드/REST/셀/스키마) 불변.
- [x] 데이터 무결성: `broadcast_at` append-only nullable, 백필 멱등(`IS NULL`만), 레이어링 무관.
- [x] 시그니처 전파: `process_pending_groups`·`dispatch_broadcasts_bg`·`_dispatch_broadcasts`·`post_event_async` 변경 → Grep 전수(호출부 워커 1곳 + 테스트) 연쇄 갱신. `main.py`/`run_chain_worker.py`는 `start_chain_ingestion_worker`만 임포트 → 무영향.
- [x] 확장성: 부분인덱스+LIMIT+grace+청킹.
- [ ] 커넥션 풀 압박(스윕+bg 스탬프 동시성): 완화책 적용, **런타임 실측 권장**.
- [x] 런타임 크래시(text import) 수정.

## 5. 검증 결과
- **단위 테스트 6/6 통과** (`tests/test_chain_hol_scheduling.py`: 기존 4 + 신규 F1/F2 2). conftest가 psycopg2 부재로 컬렉션 단계에서 막혀(`from main import app`→Postgres 엔진), DB 비의존 순수 단위이므로 **conftest 우회 독립 러너**로 실행. ciw 모듈은 psycopg2 없이 import됨 확인.
- `py_compile`: 수정 4개 파일 정상.

## 6. 미해결 / 런타임 검증 필요 (psycopg2/Postgres 부재로 코드만으로 불가)
1. `EXPLAIN ANALYZE`로 F3 `idx_outbox_txid` + 스윕 `idx_outbox_undelivered` 실사용 확인(대량 SUCCESS 누적 하).
2. `/internal/events/broadcast` 실패 주입 → `broadcast_at` NULL 유지 → grace 후 스윕 재발사·확정 → 재발사 멈춤(eventual delivery). 워커 재시작 복구.
3. 백필 마이그레이션 실행(대량 기존 행) 후 스윕 무-오발사 확인.
4. 커넥션 풀 압박(스윕+bg 스탬프) 실측.
5. `pytest` 정식 실행은 psycopg2/Postgres CI에서(현 환경 부재).

## 7. 다음 단계 (lead)
- 최종 diff 검수 후 커밋. 배포 시 **백필이 컬럼 최초생성 배포에서 반드시 완주**하는지 확인(중단 시 잔여 NULL 행은 스윕이 안전 회수 = over-refresh 1회, stale 아님).
- 운영 반영: `setup_db_performance.py` 실행 또는 앱 기동 마이그레이션 중 하나가 먼저 컬럼+백필+인덱스를 확정.

## 8. 총괄이 특히 볼 리스크 포인트
- **백필 완주 의존성**: 백필은 게이팅상 최초 1회. 중단 시 안전(스윕 회수)하나, 대량 outbox에서 백필 시간이 길면 그동안 스윕이 미백필분을 refresh 발사할 수 있음(정합성 문제 아님, 부하 스파이크). 배포창에서 관찰 권장.
- **커넥션 풀**: 워커 프로세스 풀 크기 대비 스윕 메인세션 + bg 스탬프 짧은세션 동시 소비. 실측 전까진 미확정.
- **`main.py` 백필 except 광범위**: ADD COLUMN 성공 후 백필 루프 예외도 같은 `except: pass`에 흡수됨(잔여 NULL은 스윕 회수라 안전하나 로그 부재). 검수 시 판단 요망.
