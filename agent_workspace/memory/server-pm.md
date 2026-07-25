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
- **함정**: `/graph/neighbors`에 node_id를 넘기면 422 — 파라미터는 `label`+`identity`다.
  **올바른 방법**: 그래프 조회 API 계약은 CODE_MAP §1.5/스펙 §6 확인 후 호출.
- **함정**: 전역 `/schema` 경로는 존재하지 않고, 없는 경로는 정적 catch-all이 **HTML을 200으로** 반환해 성공처럼 보인다.
  **올바른 방법**: 스키마는 `GET /tables/{t}/schema`. API 검증 시 응답이 JSON인지 확인.
- **함정**: 테스트용 가짜 테이블명이 사용자 config(gitignored)의 실제 테이블과 겹치면, import 시점 `init_dynamic_models`가 공유 in-memory sqlite에 실 스키마를 선점해 `create_all(checkfirst)`이 스킵되고 테스트가 `no such column`으로 깨진다(사용자가 나중에 동명 테이블을 추가해도 터짐 — `bonding_log` 사례).
  **올바른 방법**: 테스트 테이블명은 사용자 config에 실존 불가능한 고유 접두 이름(`enrich_test_*` 등)을 사용.
- **함정**: 프로세스 간 통지 페이로드에 CRUD 반환 컬렉션(created_logs 등)을 무절단으로 실으면, 대형 tx(재기동 스윕 등)에서 수신 웹서버의 json.loads/pydantic 검증이 GIL을 점유해 이벤트 루프가 동결된다 — `run_in_threadpool`로 옮겨도 CPU 바운드면 못 막는다(2026-07-25 인시던트: 6.5만 건 ~50MB 페이로드로 :8080 수십 초 동결).
  **올바른 방법**: 절단은 **발신 측·직렬화 이전**에 수행하고 실건수는 별도 카운트 필드(`total_log_count`)로 전달. 상한 상수는 `server/event_constants.py` 단일 정의를 공유.
- **함정**: 동일 결함이 발신자별(워처/체인 워커)로 재발한다 — 한 발신 경로만 고치면 다른 데몬이 같은 내부 이벤트 엔드포인트를 같은 방식으로 오염시킨다.
  **올바른 방법**: `/internal/events/*` 발신·수신 계약을 바꿀 땐 워처·체인 워커(및 향후 데몬) 전 발신 경로를 grep으로 교차 점검.
- **함정**: override 성격의 카운트 필드(total_log_count → audit_cache total_count)는 **SET**이라, 같은 tx로 메시지가 2회 이상 도착하는 경로(멀티 target-table 체인 등)에서 마지막 메시지가 이전 총계를 덮어써 과소 표기된다(QA D-1).
  **올바른 방법**: 카운트 필드를 설계할 땐 "같은 키로 메시지 N회 도착" 경로를 먼저 나열하고 SET/누적 의미론을 명시적으로 선택·문서화.
- **함정**: 기존 테이블 런타임 ALTER의 유일한 경로는 `config_watcher`(on_modified)인데, 에이전트 Edit 같은 **원자적 쓰기(temp+rename)는 on_modified를 발화시키지 않아 ALTER가 조용히 누락**된다. `/tables/{t}/schema`는 config 싱글턴을 읽으므로 200에 컬럼이 보여도 물리 반영 증거가 아니다.
  **올바른 방법**: table_config 수정 후에는 information_schema로 물리 컬럼을 직접 확인하고, watcher 미발화 시 in-place 재기록으로 발화시킨다. (`/admin/reload-configs`는 신규 CREATE 전용 — ALTER 안 함.)
- **함정**: "매 접근 config 재조회"는 핫리로드는 되지만 한 작업(파일 처리) 안에서 스냅샷이 여러 번 갈려 최악엔 0행 업서트가 SUCCESS로 위장한다(QA D1). 반대로 프로퍼티 영구 캐시는 핫리로드를 죽인다(F4).
  **올바른 방법**: **작업 단위(파일) 경계에서 1회 스냅샷**을 잡아 전 구간에 인자로 전달 — 핫리로드(다음 작업부터)와 작업 내 정합을 동시 만족, 디스크 로드도 작업당 1회.
- **함정**: "경로 구분자 차단" 류 문자 블랙리스트는 Windows 드라이브 상대경로(`C:foo`)를 놓친다 — `os.path.join`이 타 드라이브 접두에서 base를 통째로 폐기한다. `..` 부분문자열 검사는 안전한 이름(`..foo`)을 오차단한다.
  **올바른 방법**: 문자 검사 대신 **결과 기반 검증** — `normpath(join(base, name))`이 base의 직속 자식이고 basename이 입력 원형과 일치하는지 확인.
