# 이슈: 체인 인제션 outbox 반응 지연 (진단)

> **상태:** 🔎 진단 완료 / 수정 대기 | **도메인:** Server PM | **작성:** 2026-07-24
> 조사: Explore 서브에이전트 → 총괄 최상위 2건 스팟체크 검증 완료. **아직 코드 수정 없음.**

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
