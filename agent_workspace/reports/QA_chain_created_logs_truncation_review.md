# QA 검수 보고: 체인 워커 created_logs 절단 (C-5 계약 확장)

- 검수 대상: working tree 미커밋 변경 (`server/event_constants.py` 신규, `chain_ingestion_worker.py`, `main.py`, `parsers/directory_watcher.py`, `tests/test_chain_created_logs_truncation.py` 신규)
- 검수자: qa-reviewer / 2026-07-25
- 테스트 실측: `1 failed, 208 passed` — 기준선 정확히 일치 (실패는 허용된 `test_map_presets_api`뿐)

## 1. 판정: **GO-WITH-FIXES**

인시던트 원인(전량 전송)은 올바르게, 전 발신 경로에 대해 제거됐고 계약·호환성·테스트 모두 실증됐다.
단, **멀티 target-table tx에서 total_count가 마지막 메시지 값으로 덮어써지는(clobber) 과소 표기 결함**이
현재 사용자 config로 실제 도달 가능함을 확인했다 — 기존 결함(이번 diff가 도입한 회귀 아님)이므로
병합은 막지 않되 백로그 수정을 권고한다.

## 2. 확인된 결함

### [중] D-1. 멀티 target-table tx에서 audit_cache total_count 덮어쓰기 과소 표기
- 위치: `server/chain_ingestion_worker.py:414-502` (target_table 루프, 공유 `chain_tx_id`) ×
  `server/audit_cache.py:131-132` (`group["total_count"] = override_total_count` — SET, 누적 아님) ×
  `server/main.py:3378` (메시지별 override 전달)
- 실패 시나리오 (현재 config로 도달 가능): `production_plan` 편집 tx 하나가
  체인 룰 `production_to_inventory_reservation_batch`(→`inventory_master`)와
  enrichment 파생 룰 `line_model_owner_attribution`(→`line_model_registry`)을 **동시에** 트리거
  (`server/config/chain_rules.json`, `server/config/enrichment_rules.json` 모두 enabled 확인).
  두 broadcast는 같은 `transaction_id = chain_{tx}`를 가지며 각자 자기 테이블 분량의
  `total_log_count`만 실는다. 예: A테이블 600건(override 600) → B테이블 50건(override 50) 순서로
  도착하면 audit_cache 그룹의 `total_count`가 600 → **50으로 덮어써짐** (실제 650).
  캐시에는 로그가 최대 500건 쌓여 있는데 total_count=50 — 히스토리 패널 총계/페이지네이션 표기 모순.
- 성격: **기존 결함** — 변경 전에도 `actual_count = len(created_logs)`를 메시지별 override로
  전달했으므로 동일하게 발생했다. 이번 diff는 의미론을 고착시켰을 뿐 도입하지 않았다.
- 권장 조치(백로그 P2): (a) 워커가 tx 단위 누적 총계를 마지막 메시지에만 싣거나,
  (b) `add_logs_batch` override를 `max(기존, override)` 또는 가산(additive) 의미론으로 바꾸거나,
  (c) target_table별 sub-tx id 분리. 어느 쪽이든 워처 경로(파일당 단일 통지라 미영향)와의 정합 확인 필요.

### [낮] D-2. 수신부 방어 절단이 리터럴 500 하드코딩 (상수 미공유)
- 위치: `server/main.py:3345, 3375` (`created_logs[:500]`), `server/audit_cache.py:95,137,150` (캡 500)
- 시나리오: `MAX_NOTIFY_CREATED_LOGS`를 상향하면 발신은 늘고 수신·캐시는 500에 머물러
  조용한 불일치. `event_constants.py` docstring이 이를 인지하고 경고 주석은 있으나 코드 강제는 없음.
- 성격: 기존 코드(수신부는 이번 diff에서 로직만 수정, 리터럴은 종전대로). 권장: main.py도
  공용 상수 import (수정 규모 2줄, 다음 변경 시 편승 가능).

## 3. 반증 시도했으나 안전한 항목

1. **다른 created_logs 발신 경로 잔존?** — 전수 추적 결과 체인 워커의 구성 지점은
   `chain_ingestion_worker.py:458-502` 단일(양 분기 모두 절단 적용). F1 복구 스윕(`:750-764`)과
   graph 워커(`graph_sync_worker.py:926`)는 created_logs 없는 table-level refresh만 전송.
   워처(`run_watcher.py:51-70`)는 C-5에서 기절단. main.py 내 자체 WS 경로(1200/1670/2381/3149 등)는
   내부 HTTP가 아닌 in-process 브로드캐스트로 ≤5000 캡/청크 분할 — 본 인시던트 경로 아님.
2. **gitignored 사용자 영역 발신자?** — `server/config/`, `server/ingestion_workspace/`,
   `server/mappers/` 전수 grep: `created_logs`/`total_log_count`/`internal/events` 참조 0건 (직접 실측).
3. **구버전 호환 폴백** — 필드 부재 시 `len(created_logs)` + 서버측 500 절단 유지
   (`main.py:3373-3375`), 테스트로 실증(`test_internal_broadcast_falls_back_to_len_without_total_log_count`).
   구 워커+신 main / 신 워커+구 main 어느 조합도 크래시 경로 없음(dict payload, 미지 필드 무시).
4. **directory_watcher 상수 교체** — `from event_constants import ...`는 sys.path에 server_dir 삽입
   (`directory_watcher.py:16-18`) **이후**라 안전하며 모듈 속성으로 그대로 노출 —
   `directory_watcher.py:663` 사용부와 `test_contention_fixes.py:197` 모두 통과(스위트 실측).
5. **절단 위치** — 직렬화 루프 앞 슬라이스(`chain_ingestion_worker.py:463-472`)로 6.5만 건
   dict copy/isoformat 낭비 제거 확인. total_log_count는 슬라이스 전에 계산되어 레이스 없음.
6. **빈 로그 경계** — created_logs 빈 리스트면 `total_log_count=0` 동봉되나 수신부
   `if created_logs:` 가드로 캐시 미접근 — 무해.
7. **클라이언트 계약** — `client2/src/websocket.js:101`은 `created_logs`를 배열로만 소비,
   `total_log_count` 미참조(순수 추가 필드). 체인 경로 절단으로 클라이언트가 받는 로그가
   전량→500이 되지만 워처 경로에서 기승인된 C-5 계약과 동일 형태이며 히스토리 총계는
   audit API가 담당 — 회귀 아님.

## 4. 잔여 병목 판단 (중점 항목: 500건이어도 페이로드가 수 MB인가)

- **현재 config 기준 안전**: 체인/enrichment 대상 테이블의 컬럼은 전부 소형 스칼라
  (`core_wafer_map` = core_key/core_lot/core_slot/wafer_id/chip_count/eventtime — `table_config.json` 실측,
  대형 맵 문자열 컬럼 없음). 로그 1건 수백 바이트 × 500 ≈ 수백 KB/메시지 수준으로 인시던트 재발 없음.
- **구조적 잔여 리스크 (P2~P3 백로그 이관 권고)**:
  - P2: `created_logs`의 `old_value`/`new_value`는 길이 무제한(`crud.py:224-236`,
    `sanitize_to_utf8`은 인코딩 정제만). 향후 대형 텍스트 셀(맵 문자열류)을 가진 테이블이
    체인/워처 대상이 되면 500건 × 2값으로 다시 수십 MB 가능 — 값 길이 캡(예: 4KB) 검토.
  - P3: `batch_row_upsert` 분기의 `items`(≤100행)는 행 전체 데이터를 실음
    (`chain_ingestion_worker.py:434-454`) — 행당 크기 무제한. 동일 조건에서 MB급 가능.

## 5. 런타임 검증 필요 (코드만으로 단정 불가)

- 라이브 재기동 후 대형 tx(수만 건) 재현 시 :8080 이벤트 루프 비동결 실측 (SLO 로그 `[Latency] notify=` 확인).
- 재기동 순서: 워커 먼저 재기동 시 구 main이 total을 500으로 표시하는 과도기 존재
  (하위 호환이라 무해하나 보고서의 "순서 무관 안전"은 표기 정확도 한정으로 약간 과장) — 양쪽 재기동 권장.

## 6. 문서 정합

- 구현자 보고서(`Server_chain_created_logs_truncation_report.md`)의 주장(변경 라인·grep 전수·테스트 수치)은
  전부 재실측과 일치. 과장 1건: "워커만 먼저 재기동해도 안전" — 기능상 안전하나 과도기 총계 과소 표시 존재(§5).
- CODE_MAP/FEATURE_CHECKLIST/히스토리 미수정은 지시서 준수(doc-keeper 전담). 통합 시 보고서의
  이력 초안과 함께 **D-1(멀티 타깃 total_count clobber)을 PROJECT_STATUS 백로그에 등재**할 것.

## 7. 교훈 제안 (qa-reviewer.md 반영 검토)

- **함정**: 카운트 override 계약 검수에서 메시지 1건만 보면, 한 트랜잭션이 여러 메시지로 나뉘는
  경로(멀티 target-table 등)에서 SET 의미론이 이전 값을 덮어쓰는 과소/과대 표기를 놓친다.
  **올바른 방법**: override성 필드는 "같은 키(tx id)로 메시지가 2번 이상 도착하는 경로가 있는가"를
  먼저 찾고, 수신부 갱신이 SET인지 누적인지 대조한다.
