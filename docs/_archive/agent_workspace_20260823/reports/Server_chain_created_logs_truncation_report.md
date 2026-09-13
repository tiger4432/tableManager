# 보고서: 체인 워커 created_logs 무절단 전송 결함 수정 (C-5 계약 확장)

- 지시서: `agent_workspace/tasks/Server_chain_created_logs_truncation_task.md`
- 작업 위치: 메인 트리 (커밋하지 않음 — 총괄 검수 대기)
- 라이브 서버 재기동: 하지 않음

## 1. 변경 요약

인시던트(2026-07-25 21:29) 원인인 "체인 워커의 created_logs 전량(최대 6.5만 건, ~50MB JSON)
단일 페이로드 전송"을 제거했다. 발신 측(체인 워커)에서 500건 절단 + `total_log_count`(실건수) 동봉,
수신 측(main `/internal/events/broadcast`)에서 `total_log_count` 우선 사용. 이벤트명·기존 필드
형태는 불변이며 `total_log_count`는 순수 추가 필드(워처→batch-refresh 계약과 동일 형태).

## 2. 변경 파일·라인

### 신규: `server/event_constants.py`
- `MAX_NOTIFY_CREATED_LOGS = 500` 공용 상수 승격 (워처·체인 워커 공유, 중복 정의 제거).
- 워처 모듈 직접 import는 watchdog Observer 등 무거운 의존을 끌고 오므로 부적절 →
  의존성 없는 독립 상수 모듈로 신설. `server/`가 모든 프로세스의 sys.path에 있어
  `from event_constants import ...`로 양쪽에서 동일하게 접근.

### `server/parsers/directory_watcher.py` (라인 28~31)
- 로컬 정의 `MAX_NOTIFY_CREATED_LOGS = 500` → `from event_constants import MAX_NOTIFY_CREATED_LOGS`.
- 모듈 속성으로 그대로 노출되므로 기존 참조(라인 663, 테스트 `directory_watcher.MAX_NOTIFY_CREATED_LOGS`) 전부 무변경 호환.

### `server/chain_ingestion_worker.py`
- 라인 21~22: `from event_constants import MAX_NOTIFY_CREATED_LOGS` 최상단 import 추가.
- 라인 459~470 (`process_chain_transaction_group` 내 broadcast 메시지 구성부):
  - `total_log_count = len(created_logs) if created_logs else 0` — 절단 **전** 실건수 확보.
  - 직렬화 루프를 `for log in created_logs[:MAX_NOTIFY_CREATED_LOGS]:`로 변경 —
    절단을 직렬화(dict copy + isoformat) **앞**에서 수행(지시서 요구: 6.5만 건 변환 낭비 제거).
- 라인 472~492: `batch_refresh_required`(>100 items) / `batch_row_upsert`(≤100 items)
  **두 분기 모두** `"total_log_count": total_log_count` 필드 추가.

### `server/main.py` (`/internal/events/broadcast`, 라인 ~3367)
- `actual_count = payload.get("total_log_count") if ... is not None else len(created_logs)` —
  batch-refresh 핸들러(라인 3344)와 동일한 우선순위 규칙. 필드 부재(구버전 발신자) 시
  기존 `len(created_logs)` 폴백 + 서버측 500건 방어 절단은 그대로 유지.
- 결과: audit_cache의 `total_count`가 절단 후에도 실건수(예: 65,000)를 표기.

### 신규 테스트: `server/tests/test_chain_created_logs_truncation.py` (5건)
- `test_truncation_constant_is_shared_single_definition` — 워처·체인·공용 모듈 상수 단일성(=500).
- `test_chain_broadcast_upsert_branch_truncates_created_logs` — ≤100 items 분기: 501건 모의 →
  `created_logs` 500건 + `total_log_count=501` + isoformat 직렬화 형태·기존 필드 불변 검증.
- `test_chain_broadcast_refresh_branch_truncates_created_logs` — >100 items 분기 동일 검증.
- `test_internal_broadcast_respects_total_log_count` — `/internal/events/broadcast`에
  logs 3건 + `total_log_count=65000` POST → audit_cache group `total_count==65000`.
- `test_internal_broadcast_falls_back_to_len_without_total_log_count` — 필드 부재 시 `len` 폴백(구버전 호환).
- 테스트 테이블명은 지시대로 `chtrunc_test_*` 접두(교훈 파일: 사용자 config 충돌 방지).

## 3. 테스트 결과 (전문)

신규 파일 단독:
```
5 passed, 6 warnings in 0.27s
```

전체 스위트 (`conda run -n assy_manager python -m pytest server/tests/ -q`, PYTHONIOENCODING=utf-8):
```
=========================== short test summary info ===========================
FAILED server/tests/test_api.py::test_map_presets_api - AssertionError: asser...
1 failed, 208 passed, 13 warnings in 11.44s
```
기준선 충족: 기존 203 passed + 신규 5 = **208 passed / 1 failed(`test_map_presets_api`, 허용된 기존 실패)**.

## 4. 영향 범위 전수 확인 (gitignored 영역 포함)

`MAX_NOTIFY_CREATED_LOGS` / `total_log_count` repo 전체 grep (`config/*.json`, `ingestion_workspace/`,
`mappers/`, `client2/` 포함):
- 서버 측 소비자: `run_watcher.py`(발신, 기존), `main.py` batch-refresh/broadcast(수신) — 전부 정합.
- 클라이언트: `client2/src/websocket.js:101`이 `created_logs`를 배열로 소비할 뿐 총계로 쓰지 않음.
  `total_log_count`는 미참조(순수 추가 필드) — 워처 경로는 C-5 이후 이미 절단본을 받고 있었으므로
  체인 경로 절단도 클라이언트 동작 변화 없음. 히스토리 패널 총계는 audit_cache API가 담당(실건수 유지).
- 사용자 영역(`mappers/`, `ingestion_workspace/`, `config/`): 해당 심볼 참조 없음.
- 잔존 매치는 `.claude/worktrees/`의 과거 에이전트 워크트리 사본뿐(비대상).

경계 계약: 이벤트명·기존 필드 무변경, `total_log_count`는 기승인된 워처 계약과 동일 형태의
추가 필드 — 지시서가 승인 범위를 명시했으므로 추가 에스컬레이션 불요.

## 5. 미해결·다음 단계

- 커밋: 하지 않음 — 총괄 diff 검수 후 커밋 요망.
- 라이브 반영: 체인 워커(`run_chain_worker.py`)와 웹서버(main) **양쪽 재기동 필요**
  (수신부는 하위 호환이므로 순서 무관, 워커만 먼저 재기동해도 안전). 총괄이 사용자와 협의.
- 문서: CODE_MAP/FEATURE_CHECKLIST/history는 지시대로 미수정 — 아래 이력 초안 참조 (doc-keeper 전담).

### 히스토리 이력 초안 (통합 시 사용)
> fix(chain): 체인 워커 created_logs 전량 전송 제거 — 500건 절단 + total_log_count 동봉 (C-5 계약 확장).
> 재기동 스윕 대형 tx(6.5만 이벤트, ~50MB JSON)가 :8080 이벤트 루프를 수십 초 동결시키던 인시던트
> (2026-07-25 21:29) 수정. 상수는 `server/event_constants.py`로 승격(워처와 공유),
> `/internal/events/broadcast`는 total_log_count를 audit_cache 총계로 우선 사용(구버전 폴백 유지).
> 테스트: test_chain_created_logs_truncation.py 5건 신규, 208 passed / 1 allowed fail.

## 6. 교훈 제안 (server-pm.md 반영 검토 요청)

- **함정**: 프로세스 간 통지 페이로드에 CRUD 반환 컬렉션(created_logs 등)을 무절단으로 실으면,
  대형 tx(재기동 스윕 등)에서 수신 웹서버의 json.loads/pydantic 검증이 GIL을 점유해 이벤트 루프가
  동결된다 — `run_in_threadpool`로 옮겨도 CPU 바운드면 못 막는다.
  **올바른 방법**: 절단은 **발신 측·직렬화 이전**에 수행하고 실건수는 별도 카운트 필드
  (`total_log_count`)로 전달. 상한 상수는 `server/event_constants.py` 단일 정의를 공유.
- **함정**: 동일 결함이 발신자별(워처/체인 워커)로 재발한다 — 한 발신 경로만 고치면
  다른 데몬이 같은 내부 이벤트 엔드포인트를 같은 방식으로 오염시킨다.
  **올바른 방법**: `/internal/events/*` 발신자를 수정할 땐 `run_watcher.py`·`chain_ingestion_worker.py`
  (및 향후 데몬) 전 발신 경로를 grep으로 교차 점검.
