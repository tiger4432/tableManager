# 표준 파서(Std Parser) 폴백 + 테이블 워크스페이스 자동 생성

## 현상 (사용자 페인포인트, 실측)

auto_update가 `ingestion_workspace/bonding_log/raws/`에 CSV를 주기적으로 드롭했지만, 해당 워크스페이스에 `scripts/` 커스텀 파서가 없어 모든 파일이 `err/`로 격리되고 인제션이 전혀 되지 않았다(실측: `err/eqp_bonding_log_*.csv` 4건 누적). 기존 구조는 파일 헤더가 테이블 스키마와 완전히 일치하는 단순 CSV조차 **테이블마다 커스텀 파서 스크립트를 강제**했다.

## 근본 원인

`directory_watcher.IngestionHandler.process_with_retry`가 `_discover_and_execute_pipeline()` 반환이 `None`(매칭 스크립트 없음)이면 무조건 `ValueError`를 던져 실패 처리했다 — 스키마 동형 파일을 위한 기본(default) 적재 경로가 부재.

## 해결

### 1. 표준 파서 폴백 — `server/parsers/std_parser.py` (신규)

- **폴백 순서**: 커스텀 파이프라인 디스커버리가 항상 우선(하위호환 보장). `_resolve_rows()`에서 디스커버리 반환이 `None`일 때만 std 시도. 스크립트 로드/`match()` 오류 시에는 기존대로 즉시 실패(깨진 스크립트 은폐 방지 — 폴백 미발동).
- **판별**: 확장자 `.csv`(콤마)/`.tsv`(탭)/`.txt`(Sniffer→탭→콤마), 인코딩 `utf-8-sig`→`cp949` 폴백.
- **헤더 검증**: 적재 대상 컬럼(`display_columns`)과 대소문자 무시 대조 — 알려진 컬럼만 채택, 미지 컬럼 warning 후 무시. 적재 필터(`_send_to_upsert`의 display_columns 교집합)와 **동일 집합**으로 검증해 "검증 통과 후 적재 무음 탈락" 불일치를 차단(QA F5). `business_key`(또는 `composite_key_source` 전체) 부재 시 `ValueError`로 거부 → 기존 실패 경로(err/ 이동 + FileIngestionLog FAILED) 재사용.
- **키 결측 행 스킵 (QA F1)**: 키 컬럼(단일 bk 또는 composite 소스 전체) 값이 공백/결측인 행은 **스킵+카운트**. 무음 적재 시 `business_key_val=None` 항목이 `_get_or_create_row`에서 매번 신규 행으로 생성되어 재드롭마다 고아 행이 중복 누적되는 경로를 원천 차단. 파일 전체는 거부하지 않으며(소계 행 하나로 정상 데이터를 막지 않음), 스킵 수는 완료 로그와 `file_ingestion_completed` 메시지 문자열에 "키 결측으로 N행 스킵"으로 반영(기존 SUCCESS 콜백의 4번째 인자 슬롯 재사용 — 페이로드 구조 불변).
- **[확장성]** 스트리밍 2-pass(1-pass 행수 카운트 겸 전체 디코딩 검증 → 2-pass 행 dict yield). `_send_to_upsert`가 이터러블 + `total_rows` 인자를 수용하도록 확장(`itertools.islice` 1000행 청킹) — 기존 list 호출부는 시그니처 그대로 동작(전 호출부 Grep 확인: `process_with_retry`/`process_archived_file_sync`/테스트 2종).

  ```python
  # directory_watcher._send_to_upsert — list/iterator 겸용 청킹
  if total_rows is None:
      total_rows = len(rows)
  row_iter = iter(rows)
  while True:
      chunk = list(islice(row_iter, batch_size))
      if not chunk:
          break
  ```
- **경계 계약 불변**: 적재는 기존 통합 경로(`crud.apply_batch_updates`) 그대로 → 진행/완료 WS 이벤트·C-5 상한(created_logs 500)·소스 계보(`source_name`=원본 파일명, get_basename) 모두 커스텀 파이프라인 경로와 동일.
- **옵트아웃**: 워크스페이스 `config.json`의 `"std_parse": false` (기본 활성).

### 2. 테이블 워크스페이스 자동 생성 — `WorkspaceWatcher`

- `_provision_workspaces()`: `table_config.json` 등록 테이블마다 `raws/archives/err/auto_update/scripts/config` + 최소형 `config/config.json`(`{"table_name": ...}`)을 **보충 생성**. **기존 파일·설정은 변경하지 않음(누락분만 보충)** — 기존 내용을 덮어쓰지 않고, config 폴더에 `.json`이 하나라도 있으면 config.json을 추가 생성하지 않는다(단, config 폴더가 비어 있으면 최소형 config.json이 신설될 수 있음 — 예: bonding_map). 제외 목록: `AUTO_PROVISION_EXCLUDED_TABLES = {"wafer_map_metadata"}`.
- 호출 지점: ① 워처 부팅(`discover_and_watch` 선두) ② SYSTEM_RELOAD(`sync_new_workspaces` — `run_watcher.poll_pending_retries` 폴러 및 임베디드 모드 `main.py /admin/reload-configs`). watchdog은 `start()` 이후에도 `schedule()` 가능하므로 **재기동 없이 런타임 감시 등록**된다(`watched_raw_paths` set으로 중복 등록 방지).
- **동시 reload 직렬화 (QA F2)**: 임베디드 모드에서 `/admin/reload-configs`가 sync def(스레드풀)라 동시 실행될 수 있고, `watched_raw_paths`의 check-then-add가 비원자여서 같은 raws/가 이중 schedule될 수 있었다 → `sync_new_workspaces` 전체를 인스턴스 `threading.Lock`으로 직렬화.
- **0-watch 기동 후 런타임 등록 (QA F3)**: 기동 시 watch 0건이면 `start()`가 observer를 띄우지 않아 이후 런타임 `schedule()`이 영구 무동작이었다 → 신규 등록 발생 시 `observer.is_alive()` 확인 후 미기동이면 기동 시도(`_ensure_observer_running`), 재시작 불가(stop된 스레드)면 명시적 warning.
- 감시 등록 로직을 `_register_workspace()`로 단일화: config 존재 → 기존과 동일, config 부재 + 스크립트 존재 → 기존과 동일(Pipeline-only), **config·스크립트 모두 부재 + 폴더명이 등록 테이블 → 신규 허용(std 규약)**.

## 수정 파일

- `server/parsers/std_parser.py` (신규): 표준 파서 본체 (키 결측 행 스킵 카운트, display_columns 기준 헤더 검증 포함).
- `server/parsers/directory_watcher.py`: `_resolve_rows`/`_try_std_parse`/`std_parse_enabled`, `_send_to_upsert` 이터러블화, `load_global_table_config` 모듈 함수화, `WorkspaceWatcher` 자동 생성·런타임 동기화 + `_sync_lock` 직렬화(F2) + `_ensure_observer_running`(F3), 완료 콜백 detail 슬롯(F1).
- `server/run_watcher.py`: SYSTEM_RELOAD 폴러 → `workspace_watcher.sync_new_workspaces()` 훅.
- `server/main.py`: `/admin/reload-configs`에서 임베디드 워처 동기화 훅, `file_ingestion_completed` 메시지 빌더 3곳(임베디드 콜백/재시도 콜백/내부 이벤트 엔드포인트)에 SUCCESS detail("키 결측으로 N행 스킵") 문자열 반영 — 페이로드 구조 불변.
- `server/tests/test_std_parser.py` (신규): 37개 테스트.
- `docs/guide/INGESTION_GUIDE.md`: §1.5 표준 파서 / §1.6 테이블 온보딩 절 추가 (+ 옵트아웃 핫리로드 불가·변환 의존 워크스페이스 옵트아웃 권장 주의사항).

## QA 후속 수정 (GO-WITH-FIXES 반영, 커밋 전 통합)

- **F1 [중]** 키 컬럼 공백 행 무음 적재 → 고아 행 중복 누적: 스킵+카운트+완료 메시지 반영 (위 §1).
- **F2 [중]** 임베디드 모드 동시 reload 시 이중 감시 등록 레이스: `sync_new_workspaces` threading.Lock 직렬화 (위 §2).
- **F3 [낮]** watch 0건 기동 후 런타임 등록 영구 무동작: observer 생존 확인 + 기동 시도 (위 §2).
- **F5 [낮]** 검증 기준(column_types) vs 적재 필터(display_columns) 불일치 잠재: 검증 기준을 적재 기준(display_columns)으로 통일 (위 §1).
- (별도 커밋) `test_enrichment.py` 격리 버그: 픽스처 테이블명이 사용자 실 config의 실제 `bonding_log`와 충돌해 공유 in-memory sqlite에 실 스키마가 선점 → `test_dedup_new_keys_inserted` 기존 실패의 원인. 테이블명을 실존 불가능한 `enrich_test_src`/`enrich_test_derived`로 변경.

## 검증

- 신규 37개 테스트: 정상 CSV / cp949 / BOM / tsv / txt sniff(탭·콤마) / 미지 컬럼 무시 / 대소문자 무시 헤더 / bk 누락 거부 / composite 키 수용·부분 누락 거부 / 빈 파일·헤더만 / 빈 행 스킵 / **키 결측 행 스킵(단일 bk·composite 일부 공백·bk/composite 상호 보완·완료 메시지·재드롭 멱등)** / display_columns 기준 검증 / **커스텀 스크립트 우선순위(스크립트가 처리하면 std 미발동)** / 옵트아웃 / 미등록 테이블 스킵 / process_with_retry 전체 흐름(archives 이동·progress 100%·SUCCESS 콜백·err 격리) / 이터레이터 1000행 청킹·진행률(2500행→40/80/100%) / 워크스페이스 자동 생성·기존 파일 무변경·제외 목록·런타임 동기화 멱등성 / **동시 sync 직렬화(이중 schedule 없음)** / **0-watch 기동 후 observer 런타임 기동** — 전부 통과.
- 전체 스위트: **115 passed, 1 failed** — 잔여 실패 1건(`test_map_presets_api`)은 clean tree에서도 재현되는 기존 실패(본 변경과 무관). 종전 기존 실패였던 `test_dedup_new_keys_inserted`는 위 격리 버그 수정으로 해소.
- 라이브 검증(워처 재기동 필요)은 사용자 확인 절차로 이관: 재기동 → auto_update 드롭 대기(2분) → bonding_log 적재 + 체인 투영 + 배지 증가 확인.
