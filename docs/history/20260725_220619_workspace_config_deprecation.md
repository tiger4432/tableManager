# 워크스페이스 config.json 폐지 (레거시 정리)

- **일시**: 2026-07-25
- **작업자**: Server PM (지시: 총괄 PM, 사용자 승인 2026-07-25 "파일 인제션의 CONFIG 기반은 과거 레거시")
- **지시서**: `agent_workspace/tasks/Server_workspace_config_deprecation_task.md`

## 배경

`server/ingestion_workspace/<ws>/config.json`은 레거시 유산으로, 실소비 필드는 `table_name`(폴더↔테이블 별칭)과 `std_parse`(std 파서 옵트아웃) 2개뿐이었다. 스키마 SSOT는 이미 글로벌 `table_config.json`이므로 두 필드를 흡수하고 워크스페이스 config를 폐지한다.

## 변경 내용

### 필드 흡수 (`table_config.json` 테이블 항목)
- `workspace_name` (신규, 선택): 워크스페이스 폴더명↔테이블명 별칭. 부재 시 현행과 동일하게 폴더명=테이블명.
- `std_parse` (신규, 선택, 기본 true — JSON boolean만 유효, 비-bool 값은 무시+1회 경고): std 파서 폴백 옵트아웃. table_config 소관이 되면서 **재기동 없이 핫리로드**(기존 F4 미결 자연 해소). 반영 시점은 **파일 단위** — 파일 처리 시작 시 `(t_name, table_info)` 스냅샷을 잡아 그 파일은 시작 시점 config로 완결(QA D1 수정).

### 우선순위 규칙 (충돌 시)
**table_config.json 승리.** 핸들러 해석 순서:
1. `workspace_name` 명시 별칭 (글로벌 — 파일 단위 스냅샷으로 핫리로드)
2. [deprecated] 레거시 워크스페이스 `config.json`의 `table_name`/`std_parse`
3. 폴더명=테이블명 규약 / 기본 활성(true)

별칭 무효 조건(QA D2/D3): ① 다른 실존 테이블명과 동명(섀도잉) ② 동일 별칭 복수 선언 ③ 워크스페이스 루트의 직속 자식으로 해석되지 않는 경로(드라이브 상대경로 `C:evil` 포함 — 결과 기반 검사). 무효 별칭은 ERROR/WARNING 1회 로그 후 무시.

### 코드
- `server/parsers/directory_watcher.py`
  - 신규 모듈 헬퍼: `find_workspace_alias`(명시 별칭 매칭, 중복 별칭 경고), `resolve_workspace_table`(별칭>폴더명 규약), `warn_legacy_workspace_config`(경로당 1회 deprecation WARNING).
  - `IngestionHandler.table_name`/`std_parse_enabled`: 글로벌 우선 + 레거시 폴백으로 재작성. **글로벌 조회는 캐시하지 않아 핫리로드 반영**(레거시 config 파싱만 캐시). 구 `_cached_table_name`/`_cached_std_parse_enabled` 제거.
  - `_provision_workspaces`: **config.json 신설 중단**(폴더만 보충). `workspace_name` 별칭 폴더명 지원 + 경로 구분자 든 unsafe 별칭 무시(경로 탈출 방지).
  - `_register_workspace`: table_config 기반 폴더 해석(별칭 포함)으로 등록 판정, 레거시 config 발견 시 기동/리로드 1회 경고.
- `server/main.py` `/admin/file-ingestion/workspaces`: 표시 `table_name`에 글로벌 별칭 우선 적용.
- `server/setup/setup_workspace.py`: config.json 안내 문구를 deprecation 안내로 교체.
- 하위호환: 기존 config.json은 **삭제하지 않고 계속 읽는다**(사용자 파일). 실 워크스페이스 14곳 전수 확인 — 전부 폴더명=테이블명이라 동작 변화 없음(`sensor_metrics`는 레거시 폴백 경로로 계속 동작).

### 테스트
- 신규 `server/tests/test_workspace_config_deprecation.py` (12개): 별칭 인제션, std_parse 옵트아웃+핫리로드, 레거시 하위호환+경고 1회, 글로벌 승리, 자동 생성 시 config.json 미생성, unsafe workspace_name 방어.
- `test_std_parser.py` 자동 생성 단언을 "config.json 미생성"으로 갱신.
- 스위트: main 기준선 208 passed / 1 allowed fail → 변경 후 **220 passed / 1 allowed fail**(`test_map_presets_api`, 기존 허용 실패).

### 문서
- `docs/guide/INGESTION_GUIDE.md` §1.5/§1.6: 옵트아웃 위치 이관, 핫리로드 주의 문구 반전(F4 해소), deprecation 블록 추가.

## QA 수정 반영 (GO-WITH-FIXES, 같은 날)

QA 검수(`agent_workspace/reports/QA_workspace_config_deprecation_review.md`) 지적 6건 전부 반영:
- **D1(중)**: 매 호출 재조회가 열었던 "파일 처리 도중 config 변경 → 오배송/무음 0행 SUCCESS" 창 제거 — `_snapshot_table_context()`로 파일당 1회 `(t_name, table_info)` 스냅샷을 잡아 `_resolve_rows`/`_try_std_parse`/`_send_to_upsert`/로그·콜백 전 구간에 전달(`process_with_retry`·`process_archived_file_sync` 양 진입점). 부수 효과로 청크당 디스크 로드도 소멸(파일당 1회).
- **D2(중)**: 별칭 경로 검사를 문자 블랙리스트 → **결과 기반**(`normpath(join)`이 base 직속 자식 + basename 원형 보존)으로 교체 — Windows 드라이브 상대경로(`C:evil`) 탈출 차단, `..foo` 오차단 해소. 공용 함수 `resolve_workspace_root`.
- **D3(중)**: 별칭이 다른 실존 테이블명과 동명(섀도잉)·중복 선언이면 **무효 + ERROR 1회**. 재시도 경로(main.py `retry-failed`·run_watcher 폴러)는 `resolve_workspace_root` 역조회로 별칭 워크스페이스를 정확히 찾는다(오배송 차단).
- **D4(낮)**: 등록 시 [DEPRECATED] 경고를 `config.json` 파일명에 게이트 — sensor_config.json 등 커스텀 규칙 파일 허위 발화 제거.
- **D5(낮)**: 별칭 충돌 로그 키별 1회 dedup(청크당 재발화 → 로그 홍수 방지).
- **D6(낮)**: `std_parse` bool 타입 검증 — 문자열 `"false"` 등 비-bool은 무시 + 1회 경고.

회귀 테스트 9개 추가(D1 스냅샷 정합, D2 드라이브 탈출/오차단 해소, D3 섀도잉·중복·자기별칭·역조회, D4 허위 경고, D6 타입). 스위트 **229 passed / 1 allowed fail**.

## 미해결 / 후속

- 레거시 읽기 경로의 최종 제거 시점(향후 릴리스)은 총괄 결정 사항.
- 사용자 라이브 `table_config.json` 변경은 불필요(별칭·옵트아웃 실사용 0건). 커스텀 변환 의존 워크스페이스에 `std_parse: false` 명시는 선택 권장.
