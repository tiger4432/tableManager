# 보고서: std parser 배치 QA 수정 (GO-WITH-FIXES 후속)

발신: Server PM / 수신: 총괄 PM
지시서: `agent_workspace/tasks/Server_std_parser_qa_fixes_task.md`
작업 위치: 본체 main 트리 (미커밋 배치 위에 직접 수정 — stash/reset 미사용)

## 결과 요약

- **전체 스위트: 115 passed / 1 failed** (`conda run -n assy_manager python -m pytest server/tests/ -q`)
  - 잔여 실패는 **`test_api.py::test_map_presets_api` 1건뿐** (허용된 기존 실패, 본 배치 무관).
  - `test_enrichment.py::test_dedup_new_keys_inserted` **해소됨** (격리 버그 수정). enrichment 스위트 16/16 통과.
  - 신규 `test_std_parser.py`: **37개 전부 통과** (기존 29 + 신규 8).
- 기준선(작업 전 실측): 106 passed / 2 failed → 작업 후 115 passed / 1 failed.
- 경계 계약 불변 확인: WS 이벤트명·페이로드 필드 구조 무변경 (스킵 카운트는 기존 `message` 문자열 텍스트로만 반영, `/internal/events/file-processed`의 기존 optional `error_msg` 필드 재사용).
- 커밋 미수행 (지시대로 총괄 검토 후 커밋). PROJECT_STATUS.md 미접촉.

## 수정 내용

### F1 [중] 키 컬럼 공백 행의 무음 적재 → 고아 행 중복 누적 (완료)

- `server/parsers/std_parser.py`
  - `_resolve_key_groups()` / `_row_has_key()` 신설: 키 그룹 = `(business_key,)` 또는 `tuple(composite_key_source)`. **어느 한 그룹이라도 값이 전부 있으면 keyed** (bk 공백이어도 composite 전체가 있으면 유지 — crud 키 조립 경로와 정합).
  - 1-pass 카운트와 2-pass `_iter_rows` **동일 기준**으로 키 결측 행 스킵+카운트. 파일 전체 거부는 하지 않음.
  - 반환 시그니처 확장: `parse_std_file → (row_iterator, total_rows, skipped_no_key)`. 스킵 발생 시 완료 로그 + warning 로그.
- `server/parsers/directory_watcher.py`
  - `_resolve_rows`/`_try_std_parse` 3-튜플화 (커스텀 파이프라인 경로는 `(rows, None, 0)`).
  - `process_with_retry`·`process_archived_file_sync`: 성공 시 detail `"키 결측으로 N행 스킵"`을 완료 콜백 4번째 인자(기존 error_msg 슬롯)로 전달.
  - 시그니처 변경 전수 Grep 완료(gitignored `config/`, `ingestion_workspace/`, `mappers/` 포함): 호출부는 directory_watcher 내부 2곳 + 테스트뿐 — 전부 연쇄 갱신.
- `server/main.py`: `file_ingestion_completed` 메시지 빌더 **3곳**(임베디드 워처 콜백 / `/admin/retry` sync 콜백 / `/internal/events/file-processed`)의 SUCCESS 분기에서 detail을 메시지 문자열에 덧붙임. 페이로드 키 구성 불변.
- `server/run_watcher.py`: 수정 불요 (기존 `error_msg` 전달 경로가 detail을 그대로 운반).
- 테스트 4종: 단일 bk 공백 스킵 / composite 일부 공백 스킵 / bk·composite 상호 보완 판정 / 완료 detail 메시지(`"키 결측으로 2행 스킵"`) / 재드롭 멱등(2회 드롭에도 `business_key_val=None` 항목이 crud로 전달되지 않음).

### F2 [중] 임베디드 모드 동시 reload 이중 감시 등록 레이스 (완료)

- `WorkspaceWatcher.__init__`에 `self._sync_lock = threading.Lock()` 추가, `sync_new_workspaces` 전체를 `with self._sync_lock:`으로 직렬화.
- 테스트: 느린 fake observer(schedule에 50ms 지연)로 레이스 윈도를 벌린 뒤 2-스레드 동시 호출 — schedule 1회, 결과 `[0, 1]`, watch_count 1 확인. 락 부재 시 결정적으로 실패하는 구조.

### F3 [낮] watch 0건 기동 후 런타임 등록 영구 무동작 (완료)

- `_ensure_observer_running()` 신설: `sync_new_workspaces`에서 신규 등록 발생 시 `observer.is_alive()` 확인 → 미기동이면 기동 시도, stop()된 스레드 재시작 불가(RuntimeError) 시 명시적 warning("file events will NOT fire until process restart").
- `start()`에도 `is_alive()` 가드 추가(이미 기동된 observer 재시작 예외 방지).
- 테스트: 0-watch 기동 → 런타임 테이블 추가 → sync 후 observer 기동 확인.

### F5 [낮] 검증 기준 vs 적재 필터 불일치 (완료 — 통일안 채택)

- `_build_header_map` 검증 기준을 `column_types` → **`display_columns`(적재 필터와 동일 집합)**로 통일. `display_columns`가 빈 비정상 config에서만 `column_types` 폴백(주석으로 전제 명시).
- 테스트: `column_types`에만 있는 컬럼은 미지 컬럼 취급(적재 무음 탈락 불가) 확인.

### 테스트 격리 버그 (별도 커밋 대상, 완료)

- `server/tests/test_enrichment.py`: `ENRICH_TABLES` 테이블명 `bonding_log`/`bonding_job_inventory` → **`enrich_test_src`/`enrich_test_derived`** 전면 치환(fixture·RULES_FILE·SQL·assertion·API 경로 연쇄 갱신, 총 30개소). 충돌 원인·명명 규칙을 픽스처 주석으로 명문화.

### 문서 (완료)

- `docs/history/20260725_113212_std_parser_fallback_and_workspace_autoprovision.md` (본 배치 소유 문서):
  - "22개 테스트" → **37개**, 전체 스위트 수치 → **115 passed / 1 failed**.
  - "기존 무접촉" → "기존 파일·설정은 변경하지 않음(누락분만 보충)" + 빈 config 폴더에 config.json 신설 케이스(bonding_map) 명시.
  - "QA 후속 수정" 섹션 추가(F1/F2/F3/F5 + 격리 버그 별도 커밋 표기), 헤더 검증 서술 display_columns 기준으로 정정.
- `docs/guide/INGESTION_GUIDE.md`:
  - §1.5 헤더 검증 행 display_columns 기준으로 정정 + "키 결측 행 스킵" 행 추가.
  - 옵트아웃 주의 블록 추가: ① `std_parse: false`는 **핫리로드 불가 — 재기동 필요** ② **커스텀 변환 의존 워크스페이스는 `std_parse: false` 명시 권장**(헤더 우연 일치 시 raw 적재 위험).
  - §1.6 "무접촉" 표현 정정(동일 문구).
- `docs/history/README.md`: `gen_index.py` 재생성 실행(184 entries — 파일명 불변이라 내용 변화 없음).

## 커밋 묶음 구분

**커밋 1 — std 배치 본체 (기존 미커밋분 + 이번 F1/F2/F3/F5/문서):**
- `server/parsers/std_parser.py` (신규)
- `server/parsers/directory_watcher.py`
- `server/main.py`
- `server/run_watcher.py` (이번 수정 없음 — 기존 배치분)
- `server/tests/test_std_parser.py` (신규)
- `docs/guide/INGESTION_GUIDE.md`
- `docs/history/20260725_113212_std_parser_fallback_and_workspace_autoprovision.md` (신규)
- `docs/history/README.md`

**커밋 2 — 테스트 격리 (`fix(tests): isolate enrichment test tables from user config collisions`):**
- `server/tests/test_enrichment.py`

(참고: working tree의 `docs/process/PROJECT_STATUS.md` 수정분은 총괄 소유 — 미접촉. `agent_workspace/reports/Design_audit.md`·`design_mockups/`는 타 에이전트 산출물 — 미접촉.)

## 총괄 후속 조치 필요 (PROJECT_STATUS 인용부 — 내가 수정 금지 영역)

- 완료 로그 표(2026-07-25 std parser 행): "테스트 106 통과(신규 22)" → **"테스트 115 통과(신규 37)"**.
- 열린 문제 #4: `test_dedup_new_keys_inserted` **해소됨** — 잔여 기존 실패는 `test_map_presets_api` 1건. "수정 in-flight" → 완료로 갱신.
- in-flight ① 항목 종결 처리.

## 미해결 / 참고

- `test_map_presets_api` 기존 실패는 본 배치 범위 밖(맵 프리셋 도메인) — 열린 문제 #4로 계속 추적.
- F4(옵트아웃 핫리로드 불가)는 코드 수정 없이 문서 명시로 처리(지시서 방침대로). 핫리로드가 필요해지면 `std_parse_enabled` 캐시 무효화를 SYSTEM_RELOAD에 연결하는 후속 작업 필요.
- 라이브 검증(워처 재기동 → auto_update 드롭 → bonding_log 적재 확인)은 기존 배치 계획대로 사용자 확인 절차로 이관.
