# QA 검수: 워크스페이스 config.json 폐지 (2026-07-25, working tree)

- 검수 대상: `server/parsers/directory_watcher.py`, `server/main.py`, `server/setup/setup_workspace.py`, `server/tests/test_workspace_config_deprecation.py`, `server/tests/test_std_parser.py` (docs/ 변경은 문서 에이전트 소관으로 제외)
- 검수 방법: 전체 diff 정독, 반증 가설별 코드 추적, 스위트 실측 재실행, 경로 탈출·로더 비용 실측 스크립트, gitignored 사용자 영역 전수 grep

## 1. 판정: **GO-WITH-FIXES**

핵심 요구(필드 흡수·신설 중단·하위호환+경고·글로벌 우선)는 전부 실증됐고 기존 14개 워크스페이스는 동작 불변이며 스위트도 기준선 재현(220 passed / 1 allowed fail). 다만 새로 도입된 "매 호출 재조회" 설계가 **파일 처리 도중 config 변경 시 무경고 오배송/전량 드롭** 창을 열었고, Windows 한정 별칭 경로 탈출·별칭-테이블명 충돌 무감지가 확인되어 수정 없이는 커밋 부적합 항목이 있다. 현재 라이브 config에 별칭/옵트아웃이 0건이라 배포 즉시 터지는 결함은 아니다.

## 2. 확인된 결함 (심각도순)

### [중] D1. 파일 처리 도중 config 리로드 시 무경고 오배송·전량 드롭 (인제션 무정지 정합 — 핵심가치 #3)
- 위치: `server/parsers/directory_watcher.py:620` (`_try_std_parse`의 t_name/table_info 스냅샷) vs `:652` (`_send_to_upsert`의 table_config 로드) vs `:655` (별도 `self.table_name` 재해석 — 내부에서 또 한 번 디스크 로드)
- 실패 시나리오 A (오배송): 10만 행 파일이 std parser로 처리 중(스트리밍 이터레이터), 관리자가 다른 테이블 X에 `workspace_name`을 이 폴더명으로 추가 → `_try_std_parse`는 구 테이블 A의 business_key로 헤더를 검증했는데 `_send_to_upsert`(:655)가 X로 재해석 → A용으로 검증된 행들이 X의 `display_columns` 기준으로 정규화되어 **X에 업서트**된다.
- 실패 시나리오 B (전량 드롭, 더 나쁨): `:652`와 `:655` 사이에 config가 바뀌어 `t_name`이 `:652` 스냅샷에 없는 테이블로 해석되면 `table_info={}` → `defined_cols=[]` → 모든 행의 `normalized_row`가 빈 dict → `items` 빈 채 `continue` → **0행 업서트인데 파일은 archives/로 이동, SUCCESS 기록**. "빠르지만 조용히 안 맞음"의 전형.
- 구 코드는 영구 캐시라 이 레이스가 없었다(핫리로드 부재와 맞바꾼 것). 창은 좁지만(사람이 config를 편집하는 순간 × 대용량 파일 처리 중) 결과가 무음이라 심각도 중.
- 권장: `process_with_retry` 진입 시 `(t_name, table_info)`를 **파일당 1회 스냅샷**해 `_resolve_rows`/`_send_to_upsert`에 인자로 전달. 핫리로드는 "파일 경계에서 반영"으로 정의하면 정합·핫리로드 모두 만족.

### [중] D2. Windows 드라이브 상대경로 별칭이 unsafe 검사를 통과해 base_dir 탈출
- 위치: `server/parsers/directory_watcher.py:807` — `os.sep in`/`"/" in`/`".." in` 검사
- 실증(스크립트 실측): `workspace_name: "C:evil"`은 세 검사 모두 통과, `os.path.join("D:\\...\\ingestion_workspace", "C:evil") == "C:evil"` (드라이브 상대경로가 base를 **폐기**) → `_provision_workspaces`의 `os.makedirs`가 C 드라이브 CWD 하위에 폴더 트리를 생성하고 그 raws/가 감시 대상으로 등록된다.
- 부수: `"..evil"`은 안전한 이름인데 `".." in` 부분문자열 검사로 오차단(경미).
- 권장: `os.path.splitdrive(folder_name)[0]` 비어있는지 + `os.path.normpath(os.path.join(base, name))`이 base 하위인지의 **결과 기반 봉쇄**로 교체.

### [중] D3. 별칭이 기존 테이블명과 동명일 때 무경고 섀도잉 + retry 경로 오배송
- 위치: `server/parsers/directory_watcher.py:103-114` (`resolve_workspace_table` 별칭 우선, 충돌 검사 없음), `server/main.py:3204` / `server/run_watcher.py:167` (retry-failed가 `ingestion_workspace/<table_name>`으로 워크스페이스 역산)
- 실패 시나리오 ①: 테이블 X가 `workspace_name: "parts"` 선언(parts는 실존 테이블) → 폴더 `parts/`는 별칭 우선으로 **X로 인제션**되고, 테이블 parts는 파일을 받을 워크스페이스를 잃는다. 경고 0건.
- 실패 시나리오 ②: parts의 FAILED 로그 재시도 → retry 핸들러가 `workspace_path=.../parts`로 생성 → `table_name` 프로퍼티의 별칭 매칭이 X를 반환 → **재시도 결과가 log.table_name(parts)이 아닌 X에 업서트**.
- retry 경로가 별칭 폴더를 역산하지 못하는 문제(폴더≠테이블이면 workspace_root가 허공) 자체는 기존 한계이나, 별칭을 1급 기능으로 승격하면서 미해결로 남았다.
- 권장: `find_workspace_alias`(또는 config 로드 시점)에서 별칭이 다른 table_config 키와 동명이면 WARNING + 무시. retry 경로는 별칭 역매핑(`workspace_name` 역조회) 적용.

### [낮] D4. 비(非)워크스페이스 config JSON에 대한 허위 [DEPRECATED] 경고
- 위치: `server/parsers/directory_watcher.py:849-851` — 등록 시 `config_path` 존재만으로 무조건 경고
- 실패 시나리오: 라이브 `sensor_metrics/config/sensor_config.json`(커스텀 파서 **규칙 파일**, table_name/std_parse 없음)이 대체 config로 잡혀 기동 시 "deprecated — 이관하라" 경고 발생 → 사용자가 규칙 파일을 이관/삭제 대상으로 오인할 수 있다. `_load_legacy_config`(:229)는 소비 필드 존재를 게이트하는데 등록 경로만 무게이트.
- 권장: 등록 경로 경고도 소비 필드 게이트(파일 내용 확인) 또는 최소한 파일명 `config.json` 한정.

### [낮] D5. 중복 별칭 경고가 호출마다 발화 — 로그 홍수
- 위치: `server/parsers/directory_watcher.py:96-99` — `find_workspace_alias`는 `table_name` 프로퍼티 접근마다 실행되고(파일당 ~10회 + 1,000행 청크당 1회, `:745`) 중복 별칭 상태에선 매번 WARNING → 1,000만 행 파일 1개당 경고 ~1만 건.
- 권장: `warn_legacy_workspace_config`처럼 키별 1회 dedup.

### [낮] D6. 신규 필드 값 검증 부재 — `"std_parse": "false"`(문자열)가 조용히 활성으로 해석
- 위치: `server/parsers/directory_watcher.py:261` — `is not False`는 bool False만 인식. 문자열 "false"·0 등은 활성(True) 처리, 경고 없음.
- 참고: 지시서의 "미지 필드 경고 등 기존 밸리데이션과 정합" 전제에 해당하는 table_config 필드 검증기는 현 코드베이스에 존재하지 않음을 확인(전제 자체가 공허) — 타입 경고 1줄 추가 권장.

## 3. 반증 시도했으나 안전한 항목

- **기존 14개 워크스페이스 하위호환**: 사용자 영역 전수 확인 — 13개 config.json 전부 `table_name`=폴더명, 라이브 `table_config.json`에 `workspace_name`/`std_parse` 0건 → 별칭 미스→레거시 폴백→동일 결과. sensor_metrics 스크립트는 sensor_config.json을 자체 경로로 직접 읽음(D4의 경고 문제만 남음).
- **성능 회귀**: 로더 무캐시 실측 0.354ms/호출(10KB, 14테이블). 청크(1,000행)당 1회 호출(`:745`)이라 1,000만 행 ≈ +3.5s — DB 업서트 대비 무시 가능. 단 config 크기에 선형이므로 테이블 수 급증 시 재평가 항목. 보고서의 "mtime 캐시를 넣지 않은" 사유(테스트 monkeypatch 오염)도 타당함을 확인.
- **경고 1회 보장**: 모듈 전역 set(`:61`) — 프로세스 수명 기준 경로별 1회. SYSTEM_RELOAD의 `sync_new_workspaces`는 `watched_raw_paths` 가드(`:830`)로 기존 워크스페이스를 재등록하지 않아 재발화 없음. 재기동 시 재발화(의도된 동작). set 동시 접근은 최악이 중복 경고 1건.
- **임베디드/디커플드 정합**: 양 모드 모두 동일 `WorkspaceWatcher.discover_and_watch`/`sync_new_workspaces` 경로(main.py:230/2774, run_watcher.py:229/149). main.py의 `from directory_watcher import ...`(:2951)는 기동 시 sys.path에 parsers 추가(:91)로 양 모드 모두 임포트 성공.
- **잔존 참조 0**: `_cached_table_name`/`_cached_std_parse` 전수 grep(추적+gitignored 영역) — 코드 잔존 0건(문서 파일 2건뿐).
- **경계 계약**: `/admin/file-ingestion/workspaces` 응답 형태 불변(값만 별칭 우선). WS 이벤트·셀 형태·`/schema` 무접촉 확인.
- **F2 레이스 재유입 여부**: `_register_workspace`는 여전히 `_sync_lock` 하에서만 호출 — 이중 schedule 없음.

## 4. 런타임 검증 필요 (코드만으로 단정 불가)

- 라이브 재기동 시 [DEPRECATED] 경고 실제 출력(13개 정상 + sensor_metrics 허위 1건 — D4 수정 전이면 14건 예상).
- 디커플드 워처 프로세스의 SYSTEM_RELOAD 폴링 경유 실환경 핫리로드 왕복(테스트는 monkeypatch 기반 시뮬레이션).
- D1 레이스는 코드로 확정했으나 실제 창 크기는 대용량 파일 실측에서만 계량 가능.

## 5. 문서 정합

- 구현자 보고서의 사실 주장(우선순위 규칙, 전수 grep, 테스트 수 220/1, 하위호환 무영향)은 전부 실측과 일치.
- **미공개 트레이드오프**: 보고서는 "매 호출 재조회 — 핫리로드 즉시 반영"만 명기하고 **파일 처리 도중 반영이 초래하는 D1 정합 창을 언급하지 않음**. F4 해소 서사가 과장은 아니나 대가가 누락됐다 — D1 수정(파일 경계 스냅샷) 후 문구를 "파일 단위 반영"으로 정정 필요.
- `docs/guide/INGESTION_GUIDE.md`·히스토리 파일은 본 검수 범위 외(문서 에이전트 소관)이나, D1 수정 시 §1.5 핫리로드 문구도 연동 갱신 대상임을 전달 요망.
- CODE_MAP 미갱신은 지시서 준수(총괄 일괄 반영 대기) — 프로퍼티 라인이 이동했으므로 통합 시 갱신 필수.

## 6. 교훈 제안 (qa-reviewer.md 반영 검토용)

- **함정**: "경로 구분자 차단" 류 문자 블랙리스트는 Windows 드라이브 상대경로(`C:foo`)를 놓친다 — join이 base를 통째로 폐기하는 플랫폼 특성.
  **올바른 방법**: 문자 검사 대신 `normpath(join(...))`의 base 포함 여부(결과 기반)로 검증하고, 검수 시엔 실측 스크립트로 join 의미론을 확인.
- **함정**: "영구 캐시 → 매 호출 재조회" 전환 검수에서 핫리로드 성공만 보면, 한 작업 단위(파일) **도중** 값이 바뀌는 정합 창을 놓친다.
  **올바른 방법**: 재조회 지점이 2곳 이상이면 같은 작업 단위 안에서 서로 다른 스냅샷을 볼 수 있는지 호출 그래프로 대조(작업 경계 스냅샷이 정답인지 질문).
