# 인시던트: 체인 워커 created_logs 무절단 전송 → :8080 이벤트 루프 동결 (수정: 발신측 500건 절단, C-5 계약 확장)

- **일시:** 2026-07-25 21:29 발생 / 21:55 수정 커밋
- **주체:** Server PM 구현 → qa-reviewer 검수(GO-WITH-FIXES) → 총괄 병합
- **영역:** server (`event_constants.py` 신설 + `chain_ingestion_worker.py` + `main.py` + `parsers/directory_watcher.py` + tests)
- **커밋:** `cc57b64`
- **근거 문서:** [구현 보고서](../../agent_workspace/reports/Server_chain_created_logs_truncation_report.md) · [QA 리뷰](../../agent_workspace/reports/QA_chain_created_logs_truncation_review.md)

## 배경 — 무엇이 터졌나

2026-07-25 21:29, 재기동 스윕이 만든 대형 outbox 트랜잭션(최대 64,999 이벤트)을 체인 워커가
처리하면서 **created_logs(감사 로그) 전량을 단일 HTTP POST(~50MB JSON)로
`/internal/events/broadcast`에 전송**했다. 수신측 main(:8080)의 `json.loads`/pydantic 검증이
GIL을 점유해 **이벤트 루프가 수십 초 동결**되었고, 전 워커의 내부 통지(read timeout)가 연쇄
실패했다. 워처 발신 경로는 C-5(경합 수정 배치 1, `4329c29`)에서 이미 500건 절단이 적용됐지만,
**같은 결함이 체인 워커 발신 경로에 그대로 남아 있었다** — 발신자별 재발 사례.

## 변경 내용

### 1) `server/event_constants.py` 신설 — 공용 상수 승격

워처 로컬 정의였던 `MAX_NOTIFY_CREATED_LOGS = 500`을 의존성 없는 독립 상수 모듈로 승격.
워처 모듈 직접 import는 watchdog 등 무거운 의존을 끌고 오므로 부적절하다는 판단.
`directory_watcher.py`는 `from event_constants import MAX_NOTIFY_CREATED_LOGS`로 전환
(모듈 속성으로 그대로 노출 — 기존 참조·테스트 무변경 호환).

### 2) `chain_ingestion_worker.py` — 직렬화 **앞** 절단 + `total_log_count` 동봉

`process_chain_transaction_group`의 broadcast 구성부(~458). 절단을 직렬화 루프 앞에서 수행해
6.5만 건 dict copy/isoformat 낭비 자체를 제거하고, 실건수는 절단 전에 확보한다:

```python
total_log_count = len(created_logs) if created_logs else 0
serialized_logs = []
if created_logs:
    for log in created_logs[:MAX_NOTIFY_CREATED_LOGS]:
        log_copy = dict(log)
        ...  # timestamp isoformat
        serialized_logs.append(log_copy)
```

`batch_refresh_required`(>100 items)·`batch_row_upsert`(≤100 items) **두 분기 모두**
`"total_log_count": total_log_count` 필드를 추가. 이벤트명·기존 필드 형태는 불변이며
`total_log_count`는 워처→batch-refresh 계약(C-5)과 동일 형태의 **순수 추가 필드**(계약 확장).

### 3) `main.py` `/internal/events/broadcast` 수신부 — 실건수 우선 + 방어 절단 상수화

```python
total_log_count = payload.get("total_log_count")
actual_count = total_log_count if total_log_count is not None else len(created_logs)
sliced_logs = created_logs[:MAX_NOTIFY_CREATED_LOGS] if len(created_logs) > MAX_NOTIFY_CREATED_LOGS else created_logs
```

audit_cache의 `total_count`가 절단 후에도 실건수(예: 65,000)를 표기. 필드 부재(구버전 발신자) 시
`len(created_logs)` 폴백 — 구 워커+신 main / 신 워커+구 main 어느 조합도 크래시 경로 없음.
수신부 방어 절단의 리터럴 500 하드코딩은 공용 상수 import로 교체(QA D-2 편승 적용).

## 검증

- 신규 `server/tests/test_chain_created_logs_truncation.py` 5건: 상수 단일성, 양 분기 절단+실건수,
  수신부 total_log_count 우선, 필드 부재 폴백(구버전 호환).
- 전체 스위트 208 passed / 1 failed(기허용 `test_map_presets_api`) — 기준선 정확 일치.
- QA 판정 **GO-WITH-FIXES**: 인시던트 원인은 전 발신 경로에 대해 제거 확인
  (F1 복구 스윕·graph 워커는 created_logs 없는 refresh만 전송, main 내부 WS 경로는 별도 캡 존재).
- 라이브 반영은 체인 워커·웹서버 **양쪽 재기동** 필요(하위 호환이라 순서 무관하되, 워커 먼저
  재기동 시 구 main이 총계를 500으로 표시하는 무해한 과도기 존재 — QA 지적으로 양쪽 재기동 권장).

## 아키텍처 영향 / 남긴 것

- **경계 계약(C-5) 확장:** `/internal/events/*`의 created_logs 상한·`total_log_count` 규약이
  워처·체인 워커 공통 규약이 됨. 상한의 단일 정의는 `server/event_constants.py`.
- **부분 보존임을 명시:** 클라이언트·audit_cache가 받는 로그는 트랜잭션당 최대 500건이다
  (전량 아님). 히스토리 패널 총계는 `total_log_count`/audit API가 실건수를 담당.
- **잔여 결함(기존, 미수정):**
  - **D-1 (P2 백로그, 이슈 #10):** 멀티 target-table tx에서 audit_cache `total_count`가 메시지별
    SET 덮어쓰기로 과소 표기 — 현재 config로 도달 가능(chain+enrichment 동시 트리거).
  - **P2~P3:** `old/new_value` 길이 무제한(대형 텍스트 셀이면 500건으로도 수십 MB 재발 여지,
    `crud.py:224-236`) · `batch_row_upsert` items 행 데이터 무제한 — 대형 파일 인제션 전략
    (PROJECT_STATUS 백로그 P2)에 동승.

## 다음 단계

- 운영 반영 시 체인 워커 + 웹서버 재기동(사용자 협의).
- 대형 tx 재현으로 :8080 비동결 실측(`[Latency] notify=` 로그).
- D-1은 대형 파일 인제션 P2 단계에서 수정.
