# 교훈 파일 — server-pm

> **운영 규칙:** 신규 교훈은 에이전트가 보고서에 **제안** → 총괄 검수 후 이 파일에 반영. (직접 추가 금지)
> 작업 착수 시 이 파일 전체를 로드할 것 (Pre-Flight 항목).

## 공통 (전 에이전트)

- **함정**: 시스템 python으로 실행하면 psycopg2 부재 등으로 거짓 실패한다.
  **올바른 방법**: 모든 Python 실행은 conda `assy_manager` 필수 — `conda run -n assy_manager python <파일>`.
- **함정**: Windows 콘솔은 cp949라 한글/유니코드 출력에서 인코딩 에러가 난다.
  **올바른 방법**: `PYTHONIOENCODING=utf-8`을 앞에 붙여 실행.
- **함정**: `conda run`은 멀티라인 `python -c` 인라인 코드를 처리하지 못한다.
  **올바른 방법**: 코드를 스크립트 파일로 저장 후 파일 실행.
- **함정**: `/tmp`는 Windows python에서 보이지 않는다.
  **올바른 방법**: 세션 스크래치패드 디렉터리를 사용.

## server-pm 전용

- **함정**: outbox JSON 컬럼에 `.astext` 직접 접근이나 `::varchar` 캐스트 인덱스는 `JSON().with_variant` 때문에 불가·불일치한다(인덱스 미사용).
  **올바른 방법**: 인덱스 표현식은 `type_coerce(payload, JSONB)['transaction_id'].astext` 형태로 — 실제 쿼리 식과 정확히 매칭시킬 것.
- **함정**: 공유 커넥션에서 DDL이 실패하면 트랜잭션이 오염되어 이후 쿼리가 전부 실패한다.
  **올바른 방법**: DDL 전 information_schema로 존재 여부 게이트 + 실패 시 즉시 `rollback` 필수.
- **함정**: `asyncio.create_task`로 던진 브로드캐스트는 동기 루프 안에서 굶어(starvation) 전달이 지연/유실된다.
  **올바른 방법**: 커밋 후 inline `await`로 직접 발사.
- **함정**: 동일 값으로 재시딩하면 변경이 없어 outbox가 발화하지 않는다 — 스모크 테스트가 조용히 헛돈다.
  **올바른 방법**: 스모크 시 반드시 값을 변경해서 시딩.
- **함정**: `sync_dynamic_tables_schema`는 이름과 달리 존재 테이블의 ALTER 전용(`has_table` 아니면 continue) — 이 호출만 믿으면 신규 테이블 CREATE가 조용히 누락된다.
  **올바른 방법**: 신규 테이블은 `create_missing_dynamic_tables`(information_schema 게이트 + checkfirst) 경로임을 구분해 배선.
- **함정**: "리로드" 함수가 반환값을 버리는 no-op일 수 있고, watchdog 스레드가 우연히 메워주면 증상이 늦게 드러난다.
  **올바른 방법**: 리로드 경로는 단일 공용 진입점(`refresh_dynamic_models`)으로 수렴시키고 결정적(동기) 경로를 1차로.
- **함정**: 테스트용 가짜 테이블명이 사용자 config(gitignored)의 실제 테이블과 겹치면, import 시점 `init_dynamic_models`가 공유 in-memory sqlite에 실 스키마를 선점해 `create_all(checkfirst)`이 스킵되고 테스트가 `no such column`으로 깨진다(사용자가 나중에 동명 테이블을 추가해도 터짐 — `bonding_log` 사례).
  **올바른 방법**: 테스트 테이블명은 사용자 config에 실존 불가능한 고유 접두 이름(`enrich_test_*` 등)을 사용.
