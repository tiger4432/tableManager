# 구 graph sync 실행 갈래 제거

## 현상

R-2026-08-14-H로 프로세스와 저장소는 이미 은퇴했지만
`graph_sync_worker.py`, `ontology_config.py`, materializer·sweep 코드,
`ontology_mapping.json.sample`과 도달 불가 API 몸통이 실행 트리에 남아 있었다.
설정 목록에는 고쳐도 읽히지 않는 파일이 계속 노출됐다.

## 근본 원인

첫 은퇴 라운드는 저장소 재생성을 막고 옛 주소를 410으로 거절하는 데 집중했으며,
코드·설정·전용 테스트의 물리 제거는 후속 라운드로 남겼다.

## 해결

- worker/runner, 매핑 로더, materializer, orphan/stale sweep 및 전용 스크립트·테스트를 제거했다.
- `main.py`의 옛 그래프 API 몸통은 공통 410 거절 함수만 남겼다.
- 쓰기 경로의 `ontology_mapping` 캐시·`needs_graph_rollback` 판정을 제거했다.
- 스케줄러·소급 등록부에 남은 고아 스윕 코드와 테스트 참조를 제거했다.
- 설정 예시·참조본·옛 가이드는 `docs/_archive/retired_graph_sync/`로 옮겼다.
- 리빙 설정/백엔드/개요/소유 문서를 원장 기반 후계 경로로 갱신했다.

## 사이드 이펙트 분석

- **API:** 옛 `/graph/*`와 `/api/graph/sync`는 삭제하지 않아 SPA catch-all의
  HTML 200으로 떨어지지 않는다. 410, `Cache-Control: no-store`,
  `successor=/api/ledger/trace` 계약을 유지한다.
- **프로세스:** `run_decoupled_app.py`의 활성 child 목록은 바뀌지 않는다.
  삭제 대상은 이미 등록 해제된 코드다.
- **DB:** `graph_nodes`·`graph_edges`·`graph_sync_state`는 앞선 라운드에서
  DROP됐다. 동적 행의 과거 `is_graph_synced` 등 호환 컬럼은 별도 스키마
  마이그레이션 범위라 이번 변경에서 제거하지 않았다.
- **원장:** `server/ledger/*`와 `/api/ledger/*` 계약은 변경하지 않았다.
- **설정:** `ontology_mapping.json`은 live/sample 설정 목록에서 사라졌고,
  과거 예시는 archive에서만 열람한다.

## 검증

- `python -m compileall -q server` 통과.
- 삭제 모듈에 대한 runtime/test import 역검색 0건.
- `server/tests/prod_import_check.py`는 삭제 모듈 때문이 아닌 기존 환경 의존성
  6건(`croniter`, `psycopg2`, 일부 `server` import)으로 실패했다.
- 410 계약·관리자 인증·스케줄러·outbox 관련 집중 pytest **254건 통과**.
- `git diff --check`, sample/reference `table_config.json` JSON 파싱 통과.
- active runtime/test의 삭제 모듈 import는 0건이며, 남은 이름은 archive·history·410 묘비 설명뿐이다.
