# 이슈: 체인 인제션 outbox 반응 지연 (진단 + 조치)

> **상태:** ✅ **SLO 구조수정 구현 완료(통지 인라인화·계측·기동 마이그레이션 회귀 수정), 총괄 검수·커밋 대기** — F1~F3 위에 통지 기아(starvation) 제거(배경 태스크 → 배치 직후 인라인 발사) + [Latency] 구간 계측 + `main.py` 기동 마이그레이션 information_schema 게이팅. 단위 7/7 통과·런타임 SLO 실측 필요. 이력: [20260725_063000](../docs/history/20260725_063000_chain_latency_slo_inline_dispatch.md). | **도메인:** Server PM | **작성:** 2026-07-24 | **검수:** 2026-07-24 | **후속:** 2026-07-25

## 🎯 SLO (공식)

**값 변경 commit → 클라이언트 통지 도착 100ms 이내 (체인 파생 통지 포함).**

- **실측 이력**: 인덱스 생성 전 ~10s(스윕이 정상 경로를 유실로 오인 → 전체 리프레시 오발사 동반) → `setup_db_performance.py` 실행 후 ~1.4s(편집 PUT → 체인 실행 +0.63s → 브로드캐스트 도착 +0.78s).
- **1.4s의 원인(확정)**: 워커 asyncio 루프가 동기 DB 쿼리·매퍼에 블로킹되는 동안 `asyncio.create_task`로 예약한 통지 태스크가 기아(starvation) 상태 — 루프가 다음 `await`에 닿을 때까지 발사 불가.
- **이번 수정 후 기대치**: 통지가 commit 직후 **인라인 await**로 발사되므로 기아 구간 제거. 잔여 지연 = LISTEN wake(수 ms) + 매퍼 실행 + commit + POST 왕복(로컬 ~수 ms) → 경량 체인 기준 **수십 ms 수준** 예상. 워커 로그의 `[Latency] tx=... wake=..ms mapper=..ms commit=..ms notify=..ms total=..ms` 1줄로 tx별 검증한다(병목 구간 즉시 특정 가능).
- **주의**: mapper 구간은 체인 규칙의 커스텀 매퍼 비용에 비례한다(SLO 위반 시 mapper_ms부터 확인).
> 조사: Explore 서브에이전트 → 총괄 최상위 2건 스팟체크 검증 완료. 수정 이력: [docs/history/20260724_230117_chain_outbox_latency_fix.md](../docs/history/20260724_230117_chain_outbox_latency_fix.md)(#1~#3) · [docs/history/20260724_232027_chain_outbox_race_and_hol_fix.md](../docs/history/20260724_232027_chain_outbox_race_and_hol_fix.md)(#4/#5).
>
> **처리 현황**
> - ✅ **#2** commit 우선 → 통지 fire-and-forget(타임아웃 3s), 이벤트 형식 불변 — `chain_ingestion_worker.py`
> - ✅ **#1** SYSTEM_RELOAD 부분 인덱스 `idx_outbox_reload` + 조회 1s 스로틀 — `models.py`, `chain_ingestion_worker.py`
> - ✅ **#3** `idx_outbox_unprocessed`(부분) + `idx_outbox_txid`(PG 표현식) — `models.py`, `setup_db_performance.py`
> - ✅ **#4** LISTEN-after-check 레이스 — `OutboxListener`로 LISTEN 전용 커넥션 상시 유지 + 대기 진입 시 buffered notify drain(재폴링). 끊김 시 안전 재생성, `to_thread` 유지 — `chain_ingestion_worker.py`
> - ✅ **#5** 실패 head-of-line — `process_pending_groups`로 추출, `break` 제거(실패 그룹 skip·rollback·재시도) + **동일 target_table 후속 그룹만 보류**하는 보수적 순서 보존 가드(`_group_target_tables`). 단위 테스트 4건 추가 — `chain_ingestion_worker.py`, `tests/test_chain_hol_scheduling.py`
> - ⛔ **#6/#7** 본 작업 범위 밖(미착수)

## 증상
체인 인제션 outbox 반응이 **간헐적으로 느린 경우** 존재.

## 원인 (우선순위)

### ★1. `event_type` 무인덱스 매-루프 스캔 (심각도: 높음, 상시 저하)
- `server/chain_ingestion_worker.py:285` — 폴링 while 루프 **매 반복**마다
  `db.query(DatabaseOutbox).filter(event_type=="SYSTEM_RELOAD").order_by(id.desc()).first()` 실행.
- `server/database/models.py:66` — `event_type` **인덱스 없음**(부분 인덱스는 `idx_outbox_pending`(status='PENDING')뿐, :76). → PK 역스캔으로 SYSTEM_RELOAD 만날 때까지 훑음. outbox 누적 시 폴링 사이클 전체가 느려짐.
- **조치**: `event_type` 인덱스(또는 SYSTEM_RELOAD 부분 인덱스) 추가 + 이 조회를 매 루프가 아닌 NOTIFY/주기적으로 분리.

### ★2. 동기 HTTP 브로드캐스트가 commit 앞에 위치 (심각도: 높음, 간헐 지연 직접 원인)
- `server/chain_ingestion_worker.py:372-378` — `process_chain_transaction_group()`(내부에서 `/internal/events/broadcast`를 `await`, 호출 :233, 구현 :59 `requests.post(..., timeout=20)`) **완료 후에야** `processed_chain=True; commit`.
- 그룹은 `group_order` **순차** 처리 → 웹서버 지연/미응답 시 그룹당 최대 20초(delete+upsert면 ~40초) 대기하며 뒤 그룹 전부 정체.
- **조치**: 먼저 processed 표시·commit → 이후 fire-and-forget 통지. 타임아웃 2~3초로 축소, 통지 실패와 처리 성공 분리.

## 기타 (중간~낮음)
- **#3 인덱스 부재(중~높)**: `processed_chain`(비부분 boolean idx, models.py:71) → 부분 인덱스 권장. tx 보완 쿼리(worker:336)의 `payload->>'transaction_id'` 표현식 인덱스 없음 → 매 배치 무인덱스 JSON 조회.
- **#4 폴링 2초 + LISTEN-after-check 레이스(중)**: worker:312 `wait_for_notification(2.0)`; :17-44 매 대기마다 새 커넥션 LISTEN 재등록 → 빈 폴링과 등록 사이 NOTIFY 유실 시 최대 2초 tail. **조치**: LISTEN 전용 연결 상시 유지 + 등록 후 re-poll.
- **#5 실패 head-of-line 블로킹(중)**: worker:379-416 실패 시 `break`+`sleep(1)`×최대 3회 → 선두 실패 그룹이 뒤 정상 이벤트 정체. **조치**: 실패 그룹만 skip, 개별 백오프/격리.
- **#6 SYSTEM_RELOAD NOTIFY commit 누락(낮)**: `main.py:2305-2310`,`2954-2959` NOTIFY 뒤 commit 없어 유실 가능(데이터 경로 아님). **조치**: NOTIFY 뒤 `db.commit()`.
- **#7 리로드 시 mapper 재임포트(낮)**: 상시 요인 아님.

## 추가 실측 필요 (코드만으로 단정 불가)
- outbox 테이블 규모·처리완료 행 누적량 → `EXPLAIN ANALYZE`로 #1/#3 스캔 비용 실측.
- `/internal/events/broadcast` 평균 응답시간 → #2 영향 실측.
- `config/chain_rules.json`가 가리키는 커스텀 mapper 내부 DB 조회 비용(조사 범위 밖).

## 권장 착수 순서
1. #2(commit 후 통지로 순서 변경 + 타임아웃 축소) — 간헐 지연 즉효, 코드 국소.
2. #1 + #3(인덱스 추가) — 마이그레이션 1건.
3. #4/#5(레이스·head-of-line) — 로직 개선.

---

## 🔎 총괄 검수 결과 (2026-07-24) — 후속 수정 필요

> 적대적 검수(서브에이전트) + 총괄 스팟체크. 판정: **GO-WITH-FIXES**. 기계적 부분(인덱스·#4 LISTEN·#5 실패격리)은 건전하나, **#2가 지연을 줄이며 전달 신뢰성을 맞바꿔 핵심가치 #3(실시간 신뢰 전파)를 훼손**. 두 고위험 결함 모두 버스트 인제션에서 발생.

### 수정 대상 (Server PM)

| # | 심각도 | 결함 | 근거(파일:라인) | 실패 시나리오 | 권장 조치 |
|---|---|---|---|---|---|
| F1 | **높음** | 통지 유실 → 그리드 영구 stale, 복구 경로 전무 | `chain_ingestion_worker.py:124`(삼킴)·`:111`(timeout=3)·`:403`(재시도 안 함) | commit 성공 후 웹서버 재시작/3s 초과 → 통지 삼켜짐, `processed_chain=True`라 재발사 없음 → DB는 맞지만 화면 영영 구값 | 통지 전달상태 추적(`broadcast_at`) + 미통지 행 주기 재발사, **또는** 워커가 안전망으로 주기적 `batch_refresh_required` 발사 |
| F2 | 중~높 | 그룹 간 브로드캐스트 순서 역전 | `:404` 그룹마다 `dispatch_broadcasts_bg` 독립 태스크 | 동일 target 두 성공 그룹 통지 병렬 → 늦게 커밋된 최종값이 먼저 도착 시 화면이 구값으로 굳음 | 배치 브로드캐스트를 그룹 순서대로 **단일 순차 태스크**로 묶어 발사(여전히 commit 경로 밖 → 지연 이득 유지) |
| F3 | 중 | `idx_outbox_txid` 표현식 인덱스 미매칭 | `models.py:92`·`setup_db_performance.py:64` vs 쿼리 `:531` | 쿼리는 `CAST(..AS VARCHAR)`, 인덱스는 `->>`만 → 플래너가 다른 식 취급, 인덱스 미사용(미처리 대량 누적 시 방어선 상실) | 쿼리를 `.astext`로(→`->>` 유지) **또는** 인덱스를 `((payload->>'transaction_id')::varchar)`로 정렬 |

### 문서화만 (코드 수정 대신 한계 명시)

| # | 결함 | 조치 |
|---|---|---|
| F4 | HOL 가드 교차테이블 사각 — 매퍼가 다른 테이블을 read해 계산하면 "동일 target만 보류"가 순서 못 지킴 | history/가이드에 "교차 테이블 read 의존은 순서 보장 안 됨" 명시. 필요 시 규칙에 선언적 `depends_on` 검토 |
| F5 | 격리(3회 실패) 후 후속이 "적용된 적 없는 선행" 위에서 계산 | 무결성 문서에 격리의 순서 함의 명시 |

### 히스토리 정정 필요
- `docs/history/20260724_230117...:31`의 "순서 보존" 주장은 **그룹 내부** 한정 — **그룹 간 역전(F2)** 미기재. 정정.
- 통지 유실 시 **복구 부재(F1)**를 "재시도 안 함"으로만 서술 → #3 대비 위험 미고지. 보강.

### 런타임 검증 필요 (코드만으로 단정 불가)
1. 테스트 4건(`test_chain_hol_scheduling.py`) 실 Postgres/psycopg2 CI에서 실행·통과 확인 + "1 pre-existing failure" 무관성 확인.
2. `EXPLAIN ANALYZE`로 F3(인덱스 미사용) 확인 + tx 보완 쿼리 1000만행·대량누적 비용 실측.
3. 실 커넥션 드롭 시 `OutboxListener` 재생성·재폴링.
4. `/internal/events/broadcast` 실측 응답시간·실패율 → F1·F2 노출도 정량화.

### 권장 처리 순서 (재개 후)
1. **F1**(안전망) — 신뢰성 회복, 가장 중요. 2. **F2**(순차 발사) — 국소. 3. **F3**(인덱스 정렬) — 저비용 즉시. 4. **F4·F5** 문서화 + 히스토리 정정. 5. 런타임 검증.
