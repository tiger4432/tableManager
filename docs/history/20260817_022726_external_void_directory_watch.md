# External void directory watch: the path now carries wafer identity

**Date:** 2026-08-17 02:27 · **Domain:** Server (file ingestion) · **Status:** implementation complete, production payload validation pending

## 요청과 격리

메인 작업 트리가 Ledger 구현 중이어서 `codex/external-directory-watch` 브랜치와 별도 worktree에서 작업했다. 목표는 `C:/Users/kk980/void/WAFERID/WORK_DATETIME/voids.json`을 계속 감시하고, 파서가 호출 시 받은 파일 경로에서 `WAFERID`를 읽어 재전달·수정 파일을 갱신하는 것이다.

## 관측 / 추론 / 확정

- **관측:** 외부 루트가 존재하고 `SAMPLE-01/WORK_20260101_000000/voids.json` 한 건이 있었으나 파일 크기는 **0바이트**였다.
- **관측:** 종전 `WorkspaceWatcher`는 관리 `raws/`만 등록했고 외부 파일을 이동하지 않는 하단 가드만 있었다. 즉 “외부 파일을 안전하게 처리할 수 있는 이음새”는 있었지만 외부 루트를 발견·감시·스윕하는 상단 배선은 없었다.
- **관측:** 운영 live config의 legacy `void`는 업무 키가 없어 같은 파일의 변경 재전달이 신규 고아 행을 만들 수 있다. 추적 sample과 데이터 모델의 canonical 계약은 `inspection_run` + `void_obs` 두 테이블이다.
- **추론:** 실제 JSON 본문 철자는 0바이트 파일에서 알 수 없으므로 광범위한 별칭/폴백을 발명하면 안 된다. 명시적인 작은 JSON 계약을 합성 테스트로 고정하고 첫 유효 생산 파일 도착 시 다시 검증해야 한다.
- **확정:** 외부 루트는 읽기 전용이다. 성공·실패·중복 어느 경우에도 이동·삭제하지 않는다. created/moved/modified 이벤트와 300초 재귀 스윕을 함께 사용한다.
- **확정:** 상대경로는 정확히 `WAFERID/WORK_YYYYMMDD_HHMMSS/voids.json` 세 구성요소다. 경로 웨이퍼와 본문 웨이퍼가 충돌하면 임의 선택하지 않고 파일 전체를 거절한다.
- **확정:** 같은 파일이 `inspection_run`(분모)과 `void_obs`(관측) 두 바인딩을 각각 통과한다. 캐시는 `(table binding, absolute path)`로 갈라 한쪽의 종결이 다른 쪽을 스킵시키지 않는다.

## 구현

- `directory_watcher.validate_external_source_specs`: 절대경로·테이블·파서·업무 키·경로 중첩 검증.
- `ExternalSourceEventHandler`: 외부 파일의 생성·이동·수정 이벤트를 기존 `_handle_event`에 위임.
- `WorkspaceWatcher.sweep_external_sources`: 재귀 열거, 변경 stat 캐시, 테이블별 tier-1 묶음 조회, 이벤트 등록 실패/경로 일시 부재의 폴링 복구.
- `IngestionHandler._parse_meta_for`: 관리 `raws/` 또는 외부 루트 기준 상대 POSIX 경로를 한 파일 경계에서 확정.
- `voids_json_format.parse_voids_json`: 전체 파일 경로 + 상대경로를 입력으로 받아 웨이퍼 ID·작업 시각을 파싱하고 canonical 두 테이블의 행을 구성.
- 빈 파일·잘못된 JSON·단위 부재·경로/본문 웨이퍼 충돌·비정수 gate·키 충돌은 부분 성공으로 위장하지 않고 거절.
- `json.load` 전 기본 128MB 안전 천장. 실측 없이 대형 JSON을 메모리에 올려 watcher를 죽이는 대신 명시적으로 거절한다.

핵심 배선은 설정 두 항목이 같은 루트를 서로 다른 테이블 핸들러에 연결하는 형태다.

```json
{"external_sources": [
  {"path": "C:/Users/kk980/void", "table_name": "inspection_run", "parser": "voids_json"},
  {"path": "C:/Users/kk980/void", "table_name": "void_obs", "parser": "voids_json"}
]}
```

## 사이드 이펙트 분석

- **기존 관리 `raws/`:** `external_sources` 부재 기본값이 `[]`라 기존 등록·이벤트·아카이브 경로는 불변이다. 관련 회귀가 이를 고정한다.
- **공유 상태/동시성:** 외부 캐시는 source binding을 키에 포함해 두 테이블이 서로를 종결시키지 않는다. 같은 테이블의 기존 직렬화 락은 그대로 쓰고, 서로 다른 두 테이블은 독립 처리될 수 있다.
- **이벤트 흐름:** 외부 파일은 제자리에 남으므로 managed watcher와 달리 `modified`가 필요하다. 수정 이벤트는 coarse `(mtime,size)` tier-1을 1회 우회하고 sha256까지 간다. 이벤트 폭주는 기존 processing lock + 1초 debounce + sha256 dedup으로 흡수된다. watchdog 실패 시 스윕으로 열화한다. 단, 수정 이벤트도 유실되고 크기·mtime도 보존된 변경은 주기 전량 해시 없이는 발견할 수 없고 현재 그 비용 노브는 없다.
- **DB/알림:** 새 쓰기 API는 만들지 않고 기존 `_handle_event → _send_to_upsert → apply_batch_updates`와 outbox/완료 통지를 그대로 탄다. 두 테이블은 각자 트랜잭션이므로 한쪽 성공 뒤 다른 쪽 실패가 원자적으로 롤백되지는 않는다; 실패가 숨겨지지 않고 각 테이블 원장에 따로 남는 기존 void SAT 계약과 같다.
- **성능/규모:** 300초마다 외부 트리를 `stat`으로 재귀 열거하는 O(파일 수) 비용이 생긴다. 대상 filename만 후보로 만들고 동일 stat은 해시 전에 제거하며 tier-1은 테이블별 묶음 조회한다. JSON 본문은 스트리밍이 아니므로 128MB에서 선제 거절한다.
- **설정 변경:** 신규 바인딩 추가는 runtime sync가 시도하지만 기존 바인딩 변경·제거는 프로세스 상태와 observer emitter를 안전하게 교체하지 않으므로 재기동 계약이다.
- **삭제 의미론:** 외부 파일/행 삭제는 DB 사실 철회로 번역하지 않는다. source snapshot 소유권 판정 없이 삭제까지 반영하면 과거 관측을 잘못 지울 수 있어 이번 범위에서 명시적으로 남겼다.

## 검증

- 신규 계약 테스트: **18 passed**.
- 관련 회귀(외부 + 기존 startup sweep/nested dir/workspace config/std parser/error/checkpoint/tier-1/drop visibility): **165 passed**.
- sample JSON 문법 검증 통과.
- 외부 원본 파일이 스윕 뒤에도 존재하고, 같은 파일이 두 테이블에 1회씩 디스패치되며, `(mtime,size)`가 바뀐 뒤에만 다시 디스패치되는 것을 고정했다.

## 남은 운영 조건

1. live `table_config.json`에 canonical `inspection_run`/`void_obs` 선언과 물리 테이블이 있어야 한다. 업무 키 없는 legacy `void` 연결은 설정 검증이 의도적으로 거절한다.
2. `server/config/sample/ingestion_settings.json.sample`의 두 external binding은 안전하게 `enabled:false`로 출하한다. live config에서 둘을 함께 켜고 watcher를 재기동해야 한다.
3. 첫 유효 `voids.json`으로 루트 JSON 형태, 필드 철자, 단위, clean-run 메타를 재검증해야 한다. 현재 “실파일 본문 형식 검증 완료”라고 말할 근거는 없다.
4. 같은 work-datetime 파일에서 행이 삭제되는 경우 과거 관측을 자동 철회하는 snapshot-retraction 계약은 없다. 현재 보장은 같은 키의 추가·수정 업서트와 파일 변경 재감지까지다.
