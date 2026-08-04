# 📥 AssyManager 인제션 파이프라인 가이드 (Ingestion Pipeline Guide)

> **Status:** 🟢 Living | **Last-verified:** 2026-07-30 (**§1.9 전면 대체 + §1.9-bis 신설** — `600b49d`+`a5eb934` 소스 대조: `directory_watcher.request_tree_ingest`/`_ingest_directory_tree`/`relative_source_path`/`is_managed_source`/`_unique_dest`/`nested_dirs_enabled`, `advanced_ingester.extract_path_metadata`/`_merge_row`/`process_file`/`REASON_*`/`ALLOWED_RULE_KEYS`. ① **평탄화가 사라졌습니다** — 파일은 승격되지 않고 **자기 중첩 경로 그대로** 적재되며 상대 POSIX 경로가 파서에 `self.rel_path`로 전달됩니다. `_build_collision_name`·`_resolve_flatten_dest`·`_sanitize_flatten_component`·`FLATTEN_SEP` 및 `~` 구분자·`__force__` 조작 방어가 **함께 소멸**(접합하는 코드가 없으면 조작할 토큰이 없음). 함께 신설: 조건부 아카이브(`is_managed_source` — 외부 읽기 전용 트리는 이동·삭제 없음), `_unique_dest`(동명 파일 아카이브 충돌 — 종전 `_<epoch>` 1회 시도는 같은 초에 POSIX에서 **덮어썼습니다**). 🔴 **`flatten_nested_dirs`는 뜻이 바뀐 채 이름을 유지**합니다(개명하면 운영자의 off 스위치가 조용히 무력화) — 로그 문구도 "파일이 적재되지 않는다"로 정정됐습니다. ② **§1.9-bis `filename_rules` 선언 규격 신설** — 이 스키마는 **어느 문서에도 없었습니다**: 허용 키 5개(미지 키는 거절)·명명 상태 4종(`no_match`/`ambiguous_reference`/`cast_failed`/**`path_value_discarded`** ← `path_overrides_header`에서 개명)·`required` 기본 false·로드 시점 거절(캡처 그룹 없는 정규식 포함)·대상은 **상대 POSIX 경로**·`^` 앵커 주의(살아 있는 규칙 0건이라 무피해). 🔴 **우선순위는 사용자 판정 `filename < header < row`** — 「파일이 정본」이 경로까지 확장됩니다. ⚠️ `600b49d`의 커밋 메시지는 `header < filename < row`로 적혀 있으나 그것은 `a5eb934`에서 **뒤집혔습니다**. 직전 2026-07-29: §1.10 맵 키 조합 규약 정정 — 7b 공용 캐노니컬라이저가 **같은 커밋에서 착지**해 "예정/TODO" 서술이 낡았음) | **Owner:** Ingester | **Source-of-truth:** `server/parsers/directory_watcher.py`, `pipeline_base.py`, `advanced_ingester.py` · 상위 [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md)

본 문서는 `assyManager`의 핵심 자동화 모듈인 **Directory Watcher**의 작동 원리와, 새로운 데이터를 DB로 적재하기 위한 **Pandas 기반 파이프라인(Pipeline) 구성 방법**을 설명합니다.

---

## 1. Directory Watcher 작동 원리

`DirectoryWatcher`는 지정된 `ingestion_workspace` 내의 장비/테이블 폴더를 실시간으로 감시하며 다음의 과정을 수행합니다.

1. **자동 탐색 (Discovery)**: `WorkspaceWatcher`가 백그라운드에서 실행되며, 각 테이블 폴더 하위의 `raws/` 폴더에 새로운 파일이 생성(또는 이동)되는 것을 감지합니다.
2. **파이프라인 매칭**: 파일이 감지되면 해당 테이블의 `scripts/` 폴더 내에 있는 모든 파이썬(`.py`) 스크립트를 로드합니다. 각 스크립트 내에 정의된 파서들의 `match(file_path)` 함수를 평가하여 가장 적합한 파서를 동적으로 할당합니다.
3. **실행 및 정제**: 매칭된 파서가 데이터를 Pandas DataFrame으로 로드하고 변환(연산/타입 캐스팅)을 수행합니다. 이후 PostgreSQL에 안전하게 적재될 수 있도록 `NaN`, `NaT` 등의 비정상 수치를 자동으로 정화(None으로 치환)합니다.
4. **표준 파서 폴백 (Std Parser Fallback, 2026-07-25)**: **어떤 커스텀 스크립트도 파일을 처리하지 않았을 때만** 표준 파서가 시도됩니다(→ §1.5). 스크립트 로드/`match()` 오류가 발생한 경우에는 깨진 스크립트를 은폐하지 않기 위해 폴백 없이 즉시 실패 처리됩니다.
5. **아카이빙 및 격리**: 성공적으로 DB에 배치(Batch) 적재가 완료되면, 원본 파일은 `archives/` 폴더로 자동 이동됩니다. 커스텀 파서와 표준 파서 모두 처리하지 못한 경우 오류가 발생하여 파일이 `err/` 폴더로 격리되며 데이터베이스에 실패 로그가 기록됩니다.
6. **기동/주기 스윕 (이벤트 유실 안전망, 2026-07-25)**: 워처는 파일 생성 이벤트에만 의존하지 않습니다. ① **기동 스윕** — observer 기동 직후(및 신규 워크스페이스 런타임 등록 직후) 각 `raws/` 직속의 기존 파일을 mtime 오름차순으로 이벤트 경로와 동일하게 처리합니다(서버 정지 중 투입된 파일도 기동만으로 적재). ② **주기 스윕** — 300초 주기 백그라운드 스레드가 잔류 파일을 재스캔합니다. 처리 불가로 남은 파일은 (mtime, size) 시그니처로 기억해 같은 상태로는 재시도하지 않으며(무한 재시도 차단), 파일을 수정하면(mtime 변경) 다시 처리됩니다. `err/` 등 형제 폴더는 스윕 대상이 아니고, `raws/` 직속 하위 디렉토리는 스윕되지 않고 **트리 적재 트리거**가 됩니다(→ §1.9 — `600b49d` 이후 승격이 아니라 **제자리 적재**). 스윕과 실시간 이벤트의 동시 진입은 락으로 차단됩니다(이중 처리 없음). 구현: `WorkspaceWatcher.sweep_existing_files / _periodic_sweep_loop`.

---

## 1.5 표준 파서 (Std Parser) — 무스크립트 기본 경로

파일 헤더가 테이블의 적재 대상 컬럼(`table_config.json`의 `display_columns`)과 일치하는 CSV/TXT/TSV는 **커스텀 스크립트 없이도 바로 적재**됩니다. 구현: `server/parsers/std_parser.py`, 진입점: `directory_watcher.IngestionHandler._resolve_rows`.

| 항목 | 동작 |
|---|---|
| 대상 확장자 | `.csv`(콤마) · `.tsv`(탭) · `.txt`(`csv.Sniffer`로 감지, 실패 시 탭→콤마 순) |
| 인코딩 | `utf-8-sig` 시도 → 실패 시 `cp949` 폴백 |
| 헤더 검증 | **적재 대상 컬럼(`display_columns`)** 과 대소문자 무시 대조 — 알려진 컬럼만 채택, **미지 컬럼은 warning 후 무시**. 적재 필터(`_send_to_upsert`)와 동일 집합이므로 "검증 통과 후 적재 무음 탈락"이 없습니다 |
| 처리 거부 | `business_key` 컬럼(또는 `composite_key_source` 전체)이 헤더에 없으면 거부 → `err/` 이동 + `FileIngestionLog` FAILED |
| 키 결측 행 스킵 | 키 컬럼(단일 bk 또는 composite 소스 전체) **값이 공백/결측인 행은 적재하지 않고 스킵+카운트** — 소계/각주 행 때문에 파일 전체를 거부하지 않되, 키 없는 고아 행(재드롭마다 중복 신규 행)이 생기는 것을 차단합니다. 스킵 수는 완료 메시지에 "키 결측으로 N행 스킵"으로 표시됩니다 |
| 빈 파일 | 빈 파일/헤더만 있는 파일은 적재 없이 안전하게 `archives/`로 이동 |
| 적재 경로 | 기존 통합 경로(`_send_to_upsert` → `crud.apply_batch_updates`) 그대로 — 1000행 청킹, 진행률/완료 WS 이벤트, 소스 계보(`source_name`=원본 파일명) 모두 커스텀 파이프라인과 동일 |
| 확장성 | 스트리밍 2-pass(카운트→yield)로 수십만 행 파일도 전량 메모리 로드 없음 |
| 옵트아웃 | `table_config.json` 테이블 항목에 `"std_parse": false` 지정 시 폴백 비활성 (기본 활성 — JSON **boolean**만 유효, 문자열 `"false"`는 무시+경고. **파일 단위 핫리로드**: 다음 파일부터 반영) |

워크스페이스는 기본적으로 **폴더명=테이블명 규약**으로 동작하며, 폴더명≠테이블명인 경우 `table_config.json` 테이블 항목의 `"workspace_name": "<폴더명>"` 별칭으로 매핑합니다. 별칭이 **다른 실존 테이블명과 동명**이거나 **복수 테이블이 같은 별칭을 선언**하면 해당 별칭은 무시되고 ERROR 로그가 남습니다(섀도잉 차단). 경로 구분자·드라이브 접두 등 워크스페이스 루트의 직속 자식으로 해석되지 않는 별칭도 무시됩니다.

> **⚠️ 옵트아웃 주의사항**
> - `"std_parse": false`는 `table_config.json` 소관이므로 **재기동 없이 핫리로드**됩니다 (2026-07-25 F4 해소). 반영 시점은 **파일 단위**입니다 — 파일 처리 시작 시 config 스냅샷을 잡아 그 파일은 시작 시점 기준으로 완결되고, 변경은 **다음 파일부터** 적용됩니다(처리 도중 config 변경에 의한 오배송/무음 드롭 차단).
> - **커스텀 변환(컬럼 연산·정규화 등)에 의존하는 워크스페이스는 `"std_parse": false` 명시를 권장**합니다. 헤더가 스키마와 우연히 일치하는 파일이 커스텀 파서의 `match()`에 걸리지 않으면, 변환 없이 raw 값 그대로 적재될 수 있습니다.

> **🗑️ [Deprecated 2026-07-25] 워크스페이스 `config/config.json`**
> 과거 워크스페이스별 `config.json`의 `table_name`/`std_parse` 필드는 **글로벌 `table_config.json`의 `workspace_name`/`std_parse` 필드로 흡수**되었습니다. 기존 파일은 계속 읽히지만(하위호환 폴백) 기동 시 deprecation WARNING이 남으며, **두 원천이 충돌하면 `table_config.json`이 승리**합니다. 신규 워크스페이스에는 더 이상 생성되지 않습니다.

## 1.6 테이블 온보딩 = config 등록이 전부

`table_config.json`에 테이블을 등록하면 워처가 **누락된 워크스페이스 구조를 자동 생성**합니다 (`WorkspaceWatcher._provision_workspaces`):

```text
server/ingestion_workspace/<table 또는 workspace_name>/
└── raws/  archives/  err/  auto_update/  scripts/  config/
```

- **생성 시점**: ① 워처 부팅 시(`discover_and_watch`) ② `SYSTEM_RELOAD` 시(`sync_new_workspaces` — watchdog 런타임 `schedule()`로 **재기동 없이** 즉시 감시 시작).
- **폴더명**: 기본은 테이블명, 테이블 항목에 `workspace_name` 별칭이 있으면 그 이름으로 생성합니다.
- **기존 파일·설정은 변경하지 않음(누락 폴더만 보충)**: 없는 폴더만 새로 만들며 기존 내용은 절대 덮어쓰지 않습니다. [Deprecated 2026-07-25] 워크스페이스 `config.json`은 **더 이상 생성하지 않습니다** (§1.5 참조).
- 시스템 내부 테이블은 제외 목록(`directory_watcher.AUTO_PROVISION_EXCLUDED_TABLES`, 현재 `wafer_map_metadata`)으로 관리합니다.

즉, **"config에 테이블 추가 → 폴더 자동 생성 → 스키마와 같은 헤더의 CSV를 raws/에 드롭 → 적재"** 가 무스크립트로 완결됩니다.

---

## 1.7 대형 파일 Heavy 레인 (P1, 2026-07-26)

watchdog Observer는 모든 워크스페이스의 이벤트를 **단일 디스패치 스레드**에서 실행하므로, 종전에는 대형 파일 1개(예: 10만 행 ≈ 7분)가 처리되는 동안 **모든 테이블**의 후속 파일이 대기했습니다(HOL). P1은 크기 임계를 초과하는 파일을 전용 큐/워커로 격리합니다. 구현: `directory_watcher.HeavyIngestionLane` / `_route_and_process`.

| 항목 | 동작 |
|---|---|
| 임계 설정 | `server/config/ingestion_settings.json`(gitignored, `.sample` tracked)의 `heavy_file_mb` — **기본 10MB**(파일 부재/무효값 시 기본 + 경고 1회). 예: `{ "heavy_file_mb": 10 }` |
| 핫리로드 | 임계는 **파일 이벤트(라우팅 결정)당 1회** 디스크에서 읽음 — 변경은 **다음 파일부터** 반영(재기동 불필요, 파일 경계 스냅샷 규율과 동일 의미론) |
| 교차 격리 | heavy 파일은 큐 제출 후 라우팅 스레드 즉시 반환 — A 테이블 대형 파일이 B 테이블 소형 파일을 막지 않음(라이브 드릴 실측: 2.3s vs 종전 최악 415s, **약 180배**) |
| 순서 보존 | 같은 워크스페이스는 FIFO 유지 — ① heavy backlog 잔여 시 후속 파일은 크기 무관 큐 후미 ② 워크스페이스 직렬화 락(heavy/인라인/재처리 폴러 공용) ③ 인라인은 논블로킹 try-acquire 실패 시 큐 재라우팅 |
| 스윕 경로 | 기동/주기 스윕도 동일 라우팅을 탐 — 재기동 캐치업이 대형 파일에 직렬 블로킹되지 않음 |
| 진행 가시화 | watcher가 QUEUED/PROCESSING/FINISHED를 `POST /internal/events/ingestion-state`로 push → 웹서버 인메모리 레지스트리(`ingestion_activity.py`) → **`GET /admin/file-ingestion/active`**. admin File 탭에 진행 섹션(HEAVY 배지·진행률 바·경과)과 **재기동 경고 배너** 표시. WS 이벤트 계약은 무변경 |
| 알려진 제약 | heavy 워커는 1개 — heavy 파일끼리는 직렬 처리(소형은 계속 비차단) |

---

## 1.8 체크포인트 재개 & 파일 dedup (P2, 2026-07-26)

P1은 대형 파일이 **남을 막지 않게** 했지만, ① 재기동하면 진행 중이던 파일을 **0행부터 다시** 처리했고 ② 같은 파일이 다시 떨어지면 그대로 다시 적재했습니다. P2가 둘 다 닫습니다. 구현: `server/ingestion_checkpoint.py` + `directory_watcher.process_with_retry`/`_try_dedup_skip`/`_plan_checkpoint`.

**파일 시그니처** = `sha256:<size>:<digest>` — **샘플링이 아니라 전체 해시**입니다. 실측 500MB 0.535초(~935MB/s), 15.6MB 0.016초로 라이브 드릴 총 처리 415초의 0.004%라, 비용보다 정확성을 택했습니다.

| 항목 | 동작 |
|---|---|
| 저장소 | 신규 테이블 **`file_ingestion_checkpoints`**(`UNIQUE(table_name, file_signature)`). `FileIngestionLog`에 컬럼을 붙이지 않은 이유는 `create_all`이 ALTER를 하지 않아 **조회 프로세스보다 먼저 도는 마이그레이션**이 필요해지고 운영 DB에서 `UndefinedColumn` 500이 열리기 때문입니다. 준비: `python server/scripts/setup_ingestion_checkpoint.py`(멱등) |
| 원자성 | 오프셋 갱신(`record_chunk_progress`)은 청크 upsert와 **같은 트랜잭션**에서 일어납니다 → **"커밋된 행 수 == 기록된 오프셋"**이 항상 성립합니다 |
| 재개 조건 | 시그니처 + `total_rows` + `source_kind`(파서 정체성 `std` / `pipeline:<Class>`) + 오프셋 범위(`0 ≤ processed_rows ≤ total_rows`)가 **전부** 일치할 때만. 하나라도 다르면 0부터 재처리하되 **사유를 로그·`FileIngestionLog.detail`·완료 통지에 명시**합니다(조용한 재처리 금지) |
| dedup | 동일 시그니처가 이미 `DONE`이면 skip + `archives/` 이동 + `FileIngestionLog(status="SKIPPED", 사유)`. ⚠️ **WS 통지의 `status`는 `SUCCESS`**입니다 — 수신부(클라)가 비-SUCCESS를 일괄 "실패"로 렌더링하므로 오표기를 막기 위함이고, 사유는 `detail`에 담깁니다 |
| 강제 재처리 3경로 | ① 파일명에 `__force__` 토큰 ② `ingestion_settings.json`의 `dedup_by_signature: false`(전역 스위치) ③ 어드민 재시도(재시도는 명시적 의도이므로 dedup skip 미적용) |
| 적용 범위 | heavy / normal 레인, 기동·주기 스윕, 관리자 재시도 — **4경로 전부 동일 동작** |
| 비활성화 | `resume_from_checkpoint: false`로 재개만 끌 수 있습니다. 시그니처 계산이 `OSError`로 실패하면 체크포인트·dedup이 자동으로 비활성화되고 사유가 note에 남습니다 |
| ⚠️ 검증 상태 | 스위트(307 passed)는 통과했으나 **라이브 드릴 3종(체크포인트 재개·dedup·이슈 #10)은 재기동 대기 중으로 미검증**입니다 |

---

## 1.9 폴더 드롭 — **제자리 적재, 그리고 경로가 운반체다** (`600b49d` · 2026-07-30. 종전 「평탄화」 `0c6ac1a` 대체)

`raws/`에 파일이 **다중 층위 폴더로 감싸여** 들어오면, 트리가 정온해진 뒤 **각 파일을 자기 실제 중첩 경로 그대로** 기존 이벤트 경로에 넣습니다. 파일을 루트로 승격시키지 않습니다. 구현: `directory_watcher.IngestionHandler.request_tree_ingest / _ingest_directory_tree`(트리거: 디렉토리 watchdog 이벤트 + 기동/주기 스윕).

> 🔴 **왜 바뀌었나 — 폴더명이 정보였습니다.** `raws/`의 폴더 이름은 랏·설비·날짜를 나릅니다. 종전 평탄화는 그것을 **버렸습니다**: `_resolve_flatten_dest`가 맨 이름을 **먼저** 시도했으므로 하위 경로 접두는 **이름 충돌이 났을 때만** 붙었고, 평탄화 후 중첩 경로는 `logger.info` 한 줄 말고는 **어디에도 남지 않았습니다.**
>
> 접두를 무조건으로 만들고 구분자를 발명해 다시 디코드하는 대신 **경로 자체를 나릅니다.** 파서는 이미 전체 경로를 받아서 그 뒤에 축약하므로(`advanced_ingester.process_file`), 폴더명을 파일명에 인코딩하는 것은 **호출 대상이 이미 갖고 있는 정보를 문자열로 왕복**시키는 일이었습니다. 그리고 `"/"`는 폴더명 안에 들어갈 수 없으므로 경로는 **발명한 구분자도, 살균도, 경계 표식도 필요 없습니다.**
>
> **사라진 기계장치**: `_build_collision_name` · `_resolve_flatten_dest` · `_sanitize_flatten_component` · `FLATTEN_SEP`. 접두 개명이 없으므로 **`~` 구분자 규칙과 `__force__` 조작 방어도 함께 사라졌습니다**(폴더명을 파일명에 접합하는 코드가 없으면 토큰을 조작할 방법이 없습니다).

| 항목 | 동작 |
|---|---|
| 정온(quiescence) 게이트 | **무변경.** 트리 전체 스냅샷(`{상대경로: (size, mtime)}`)이 폴링 간격(1초, 파일 디바운스와 동일) 동안 **연속 2회 동일**할 때만 진행 — 복사 중인 폴더를 반쯤 처리하지 않습니다. 최대 600초 대기 후 미안정이면 손대지 않고 유예(주기 스윕이 재시도) |
| 파일 디스패치 | 모든 일반 파일을 mtime 오름차순으로 **자기 위치에서** 기존 이벤트 경로에 투입(`_handle_event` → 레인 라우팅 → 파서 → 체크포인트/dedup → archives/·err/ **전부 무변경**). 바뀐 것은 **넘겨지는 경로가 중첩됐다는 것 하나**입니다 |
| 파서가 받는 것 | 매칭된 파이프라인 파서 인스턴스에 **`self.rel_path`**(POSIX 상대 경로)를 심습니다 — `parse(path)` 시그니처를 넓히지 않습니다(사용자 스크립트가 전부 서브클래스이므로 시그니처 변경은 전수 수정입니다). 이 문자열이 **`filename_rules`가 매칭하는 대상**입니다(→ §1.9-bis) |
| 경로 문자열의 규격 | `relative_source_path(abs, root)` — **상대**(절대 경로는 규칙을 dev↔운영 사이에서 비이식적으로 만듭니다)이고 **POSIX 구분자**(Windows 구분자는 JSON 정규식에서 네 글자가 됩니다). 봉쇄는 **결과 기반**입니다(문자 블랙리스트가 아니라 "다시 join하면 같은 파일인가") — `..` 성분이나 다른 드라이브는 생존할 수 없고, 트리 순회는 이 검사에 실패하는 항목을 **건드리지 않고 남깁니다**(정션이 그 경로입니다) |
| 폴더 제거 | **비게 된 디렉터리만** `os.rmdir` — 내용물이 남은 폴더는 구조적으로 삭제 불가입니다. 처리 못 한 파일은 자기 디렉터리를 살려 두고, 주기 스윕(300초)이 나중에 재시도합니다 |
| 아카이브는 **조건부** | `is_managed_source(path)`가 두 이동 프리미티브를 함께 통제하므로 모든 호출부가 한 번에 덮입니다 — 워크스페이스 파일은 종전대로 archives/로, **외부(읽기 전용) 트리의 파일은 옮기지도·err/로 보내지도·삭제하지도 않고** 인제션 기록이 원본 경로를 가리킵니다. 내용 시그니처는 그대로 dedup에 답하며, 외부 파일의 반복 dedup-skip은 **조용합니다**(스윕이 구조적으로 영원히 다시 찾으므로 스윕당 로그 한 줄은 실제 사건을 묻습니다) |
| 아카이브 이름 충돌 | `_unique_dest`: 원래 이름 → `name_<epoch>`(종전 형태) → `name_<epoch>_2..`. **제자리 적재는 다른 폴더의 동명 파일을 일상적으로 아카이브**하므로, `_<epoch>` 한 번만 시도하던 종전 방식은 같은 초에 끝난 두 파일에서 충돌했습니다 — POSIX에서는 **먼저 온 아카이브를 덮어쓰고** Windows에서는 예외가 나서 파일이 `raws/`에 영구 잔류했습니다 |
| 숨김/시스템 파일 | `Thumbs.db` · `desktop.ini` · `.DS_Store`(대소문자 무시) 및 macOS AppleDouble `._*`는 **폐기**(적재하지 않음) |
| 멱등/재진입 | 같은 트리에 이벤트+스윕이 중복 발화해도 진행 중 가드로 1회만. zip 등 아카이브 추출은 범위 밖(폴더만) |
| 끄는 법 | `ingestion_settings.json`에 `"flatten_nested_dirs": false` (기본 true, 핫리로드 — 다음 폴더 트리거부터). 🔴 **키 이름은 뜻이 바뀌었는데도 그대로 뒀습니다** — 개명하면 운영자가 이미 넣어 둔 off 스위치가 **조용히 무력화**됩니다. `false`면 디렉터리를 손대지 않고, **그 안의 파일은 적재되지 않습니다**(로그 문구도 그렇게 말합니다 — 종전 문구가 오해를 만드는 부분이었습니다) |

> **⚠️ 커스텀 파서의 `match()`**: 이제 파일명이 **개명되지 않으므로**, 종전 「충돌 개명 때문에 `match()`가 안 걸릴 수 있다」는 함정은 사라졌습니다. 대신 `match()`가 받는 것이 무엇인지는 그대로이고, **경로를 보고 싶으면 `self.rel_path`를 쓰십시오**.

## 1.9-bis `filename_rules` — 폴더 이름을 컬럼으로 (선언 규격 · `600b49d` + `a5eb934`)

`AdvancedIngester` 계열 파서 설정(`ingestion_workspace/<table>/config/*.json`)의 **세 번째 규칙 가족**입니다. `rules`(행) · `header_rules`(헤더)와 **같은 스키마**를 쓰고, 다른 것은 **매칭 대상**뿐입니다.

- **대상은 `rel_path`** — 인제션 루트 기준 **상대 POSIX 경로**(`2026-07/EQP_03/lot_A1.csv`). 형제 채널 `path_rules`를 따로 만들지 않은 이유: **경로가 파일명을 포함**하므로 같은 문자열에 두 채널을 두면 부재·모호·`required` 기계장치를 **두 벌** 만들게 됩니다. `rel_path`가 없으면(직접 호출 등) `basename`으로 폴백해 **종전 동작 그대로**입니다.
- ⚠️ **`^` 앵커 주의.** 패턴은 값 모양·위치 무관(`re.search` 의미론)이라 폴더 구조가 드롭마다 달라도 쓸 수 있습니다. 그런데 **맨 파일명에 `^`로 앵커한 패턴은 경로로 넓혀지면 살아남지 못합니다**(앞에 폴더가 붙으므로). 값 모양 패턴은 살아남습니다. 📌 **실측: 저장소에 살아 있는 `filename_rules`는 0건**이므로(테스트가 `filename_rules == []`로 고정) 이 확장으로 깨진 선언은 없습니다.

**허용 키** (`ALLOWED_RULE_KEYS`) — 그 밖의 키는 **무시하지 않고 거절**합니다(오타가 조용히 무효 규칙이 되지 않도록):

| 키 | 뜻 |
|---|---|
| `column` | 채울 컬럼명 |
| `regex` | **캡처 그룹 1개 필수**. `group(1)`이 값 |
| `type` | `str`·`int`·`float`·`bool` 중 하나 |
| `default` | 미매치 시 값(보통 생략 = None) |
| `required` | **기본 `false`** — 기존 선언은 아무것도 바뀌지 않습니다. `true`면 값을 신뢰할 수 없을 때 **파일 전체를 거절**(0행) |

**명명된 상태 4종** — 🔴 **미상 ≠ 빈칸.** 선언이 요구했는데 만들지 못한 추출은 파일당 세어 로그로 남깁니다(종전에는 조용히 None):

| 상태 | 언제 | 처리 |
|---|---|---|
| `no_match` | 선언했는데 아무것도 매치 안 됨 | **보고**(빈칸으로 두지 않음). 고정 폴더 구조에서는 나지 않지만, 구조가 섞이면 절반이 컬럼을 잃은 실행이 전부 매치된 실행과 **똑같이 보여서는 안 됩니다** |
| `ambiguous_reference` | 패턴이 **서로 다른 값을 2개 이상** 매치(`finditer` + distinct — 같은 토큰이 두 층에 반복된 것은 모호가 아닙니다) | **거부, 해결하지 않음.** 동점을 깰 권위가 없으므로 `re.search`의 첫 히트를 쓰는 것은 **추측을 데이터 컬럼에 쓰는 것**입니다. 어휘는 `enrichment_analysis.CLS_AMBIGUOUS`와 **같은 단어**(한 상태에 한 어휘 — 동의어를 만들지 않습니다) |
| `cast_failed` | 매치했지만 선언 `type`으로 표현 불가 | **보고**(종전에는 None으로 저장 = 같은 침묵 계급) |
| `path_value_discarded` | 경로가 낸 값이 **파일 자신의 헤더**가 같은 컬럼을 나르는 바람에 버려짐 | **보고, 차단 안 함.** ⚠️ 이 방향만 이름을 붙입니다 — **헤더가 이기는 것이 곧 규칙**이므로 정상이고 경고할 것이 없습니다. 운영자가 볼 수 없는 것은 *"내가 선언한 폴더 규칙이 값을 만들었는데 아무 효과가 없었다"*이고, 침묵은 그것을 "규칙이 매치 안 됐다"로 읽히게 합니다. (`a5eb934`에서 `path_overrides_header`에서 **개명**됐습니다 — 뜻이 뒤집혔기 때문입니다) |

`file_overrides_path`는 상태가 아니라 **카운터**입니다 — 행이 자기 값을 나르면 행이 이기고(규칙), 그 불일치는 **세지만 막지 않습니다**(파일이 엉뚱한 폴더에 있거나 패턴이 다른 토큰을 잡았다는 뜻이라 둘 다 알 가치가 있고, 둘 다 막을 가치는 없습니다).

**선언 오류는 로드 시점에 이름 붙여 거절합니다** (`RuleDeclarationError`, `ontology_config`의 미지 키 거절과 같은 형태). 특히 **캡처 그룹 없는 정규식은 선언 오류**입니다 — `match.group(1)`까지 흘려보내면 운영자의 오타가 **파싱 시점 `IndexError`**가 됩니다. 검사는 `rules`·`header_rules`에도 **똑같이** 걸립니다(같은 구멍이 거기에도 있었습니다). 오류는 **전부 모아 한 번에** 보고합니다(재기동당 하나가 아니라 config 한 번에 고칠 수 있게).

### 🔴 우선순위는 **사용자 판정**이고, 그렇게 적어 둡니다 (2026-07-30)

```
filename  <  header  <  row
```

**「파일이 정본」이 경로까지 확장됩니다.** 파일 **안에** 쓰인 값은 그 파일이 스스로 주장하는 것이고, **폴더 이름은 누가 파일을 옮기는 순간 바뀌는 외부 맥락**입니다. 그래서 헤더와 경로 사이에서는 **경로가 약한 주장**입니다 — 경로 값은 **파일 안의 어떤 출처도 나르지 않는 컬럼을 채우고**, 파일이 말하는 곳(헤더든 행이든)에서는 파일이 이깁니다.

- ⚠️ **이 세 개의 순서를 새 판정 없이 바꾸지 마십시오.** `filename_data`를 `header_metadata` **뒤로** 옮기면 파일의 **보관 위치**가 파일의 내용을 덮게 되고, 그것이 이 판정이 금지하는 역전입니다. `test_merge_order_is_the_declared_ruling`이 **양방향으로** 고정합니다.
- **출처는 자기가 실제로 값을 나르는 곳에서만 이깁니다.** `parse_line`은 선언된 **모든** 컬럼을 매 행에 내보내며 미매치 규칙에는 `default`(보통 None)를 씁니다 — 그래서 평범한 dict 병합만으로는 **행의 None이 경로 값을 조용히 덮었습니다**(`_merge_row`가 채우기 절반을 함께 고쳤습니다). 채우기 순회도 **내림차순 우선순위**(헤더 → 파일명)로 돕니다. 이것이 **헤더 캐스트 실패를 구제**하는 부분입니다: 캐스트가 실패한 헤더 규칙은 None을 저장하고 그 None이 dict 병합에서 경로 값 **위**에 앉으므로, 이 절이 없으면 헤더 규칙의 잘못된 `type:` 하나가 **온전한 경로 값을 조용히 지웁니다.**
- 비용은 O(중복 컬럼)입니다 — 겹치는 컬럼이 두 가족에 선언되지 않으면 **집합이 비어 있어 평범한 dict 병합 그대로**입니다.

> 계약 테스트: `server/tests/test_filename_rules_declaration.py` · 제자리 적재 쪽은 `server/tests/test_nested_dir_ingestion.py`(종전 `test_flatten_nested_dirs.py`).

## 1.10 맵 메타 자동 등록 (M3, 2026-07-29)

인제션(파일 워처 **및** 체인 워커)이 `map_key_columns`가 선언된 테이블에 맵 셀을 적재하면, 배치가 건드린 **각 distinct 맵 키**에 대해 `wafer_map_metadata` 행의 존재를 보장합니다. 미등록 맵이 화면에 '화면기준' 칩으로 열화되는 공백(수동 에디터 push만 메타를 등록하던 문제)을 닫는 기능입니다. 구현: `server/map_meta_registrar.py`의 `MapMetaCollector` (워처 훅 `directory_watcher._send_to_upsert`, 체인 훅 `chain_ingestion_worker.process_chain_transaction_group`).

| 항목 | 동작 |
|---|---|
| 발동 조건 | 대상 테이블에 `map_key_columns` 선언 **그리고** 좌표 바인딩 해석 가능(`map_overlay.resolve_binding` — 선언 > 유도). 좌표 없는 registry형 테이블(`map_split_registry` 등)은 자연 제외 |
| 등록 내용 | **정직한 최소치** — 배치 x/y 범위(bbox) 격자(`grid_cols/rows`, `grid_start_x/y` = 데이터 최소 좌표), 회전 0, front, 마스크 중립 물리 어휘(chip 1×1 / offset 0 / margin 3 / 격자 반대각선 외접 dia) = 에디터 '표준' 선택과 동일한 합성 규격. 실제 웨이퍼 지오메트리(원)는 **추측하지 않습니다**. `auto_registered: true` 필드로 출처 표기 |
| 그 표지가 하는 일 (**D1 · 2026-08-04**) | 🔴 **그 `chip 1×1`은 1mm 다이가 아니라 "아무도 재지 않았다"입니다.** 그래서 자동 등록된 맵은 **오버레이 정렬의 근거가 되지 못하고**, 소스·타깃 어느 쪽이 그런 맵이면 서버가 `align_unavailable` + 한국어 사유로 **이름을 대고 거절**합니다(`map_overlay.geometry_declaration` — 판정의 유일한 철자, 클라 `physDeclaration`과 같은 토큰 어휘). 원 마스크 판정은 **그대로**입니다(합성 규격은 전 셀 유효를 말하도록 만들어졌고 그 답은 옳습니다). 운영자의 조치는 **그 맵의 물리 규격을 실제로 선언하는 것**이고, 에디터에서 규격을 넣고 Push하면 표지가 사라집니다. 규율 전문은 [map_editor/architecture_and_management §2.3-ter](../map_editor/architecture_and_management.md) |
| 절대 불변식 | **absent-only** — 이미 존재하는 메타 행은 어떤 경우에도 덮어쓰지 않습니다(사용자/에디터 등록이 정본). 생성 행의 소스는 `auto_map_meta`(최하위 우선순위)라 이후 사용자 편집이 항상 이깁니다 |
| 확장성 | 존재 확인은 행이 아니라 **distinct 키당 1회**, 인덱스 컬럼(`business_key_val`) IN 조회(1000키 청킹). 프로세스 수명 내 확인-완료 키 캐시로 동일 맵 재적재는 추가 쿼리 0회 |
| 이벤트 | 메타 행은 `crud.apply_batch_updates`(정상 쓰기 경로)로 생성 — outbox 이벤트가 흐르고 워커 스윕이 클라 갱신을 전달합니다. 재귀 가드: `wafer_map_metadata` 자신은 명시 거부(+ 메타 테이블엔 `map_key_columns`도 없음) |
| 끄는 법 | `ingestion_settings.json`에 `"auto_register_map_meta": false` (기본 true, 핫리로드 — 다음 파일/체인 트랜잭션 그룹부터) |
| 실패 격리 | 메타 등록 실패는 로그만 남기고 **파일/체인 적재는 정상 완료**됩니다(데이터가 먼저 커밋됨) |

> **맵 키 조합 규약**: map_id는 `map_key_columns` 값의 `'_'` 조인(에디터 `getMapIdFromMeta`와 동일)입니다. 키 컬럼이 하나라도 비면 그 행은 등록에 기여하지 않습니다(부분 정체성 추측 금지 — 에디터는 빈 조각을 버리고 나머지를 잇지만, 인제션은 자기가 메타까지 등록할 정체성을 추측해서는 안 되므로 의도적으로 다릅니다).
> **[2026-07-29 7b 착지 — 같은 커밋]** 값 정규화는 이제 **선언 타입 기준 공용 캐노니컬라이저**(`map_overlay.canonical_bind_value`)를 경유합니다. 종전 `clean_str_value` 핀은 테이블/컬럼 선언을 못 찾을 때의 동작(트림 + 정수형 float 접기)으로만 남습니다. **등록과 조회가 같은 규칙으로 조합해야** 메타가 실제로 발견됩니다 — `number` 선언 키 컬럼에 pre-cast `'01'`이 오면 등록은 `LOT_01`인데 저장된 셀은 `1`로 캐스팅돼 모든 소비자가 `LOT_1`을 찾던 것이 이 함수가 막는 결함입니다(규율 전문은 [MAP_EDITOR_SPEC §5.0](../spec/MAP_EDITOR_SPEC.md)). 고정 테스트 `test_map_id_composition_pinned_for_7b`.

---

## 2. 파이프라인(Pipeline) 구성 방법

새로운 파일 포맷을 처리하려면 `scripts/` 폴더에 파이썬 파일을 생성하고 `BasePipelineParser`를 상속받는 클래스를 정의하면 됩니다. (파일명은 자유로우며 하나의 파일에 여러 파서 클래스를 두어도 무방합니다.)

> **📌 Import 규칙 (2026-07-25, C-2)**: 신규 스크립트는 **top-level import를 사용**하세요 — `from pipeline_base import BasePipelineParser`, `from html_topology_parser import HTMLMatrixTableParser`. 과거 일부 스크립트가 쓰던 `from server.parsers.pipeline_base import ...` 구식 경로는 **하위호환 shim**(`directory_watcher._register_legacy_import_shim`)이 동일 모듈 객체 별칭으로 계속 동작시키므로 기존 스크립트를 고칠 필요는 없지만, 신규 작성에는 권장하지 않습니다. (`server.*` 접두 import는 과거 동일 모듈 이중 로드 → outbox 이벤트 ×2 중복 발행 사고의 원인이었습니다 — shim은 구식 import가 top-level과 **같은 객체**를 받도록 보장해 이 문제를 원천 차단합니다.)

### 2.1 폴더 구조 예시

```text
server/ingestion_workspace/my_table/
├── archives/       # 처리 완료된 원본 파일 보관소
├── raws/           # 워처가 감시하는 파일 드롭(Drop) 존
└── scripts/
    └── my_custom_parser.py  # 파이프라인 스크립트
```

### 2.2 파이프라인 클래스 작성 템플릿

다음은 `my_custom_parser.py`의 기본 작성 예시입니다. `match`와 `process_dataframe` 두 개의 메서드만 오버라이딩하면 됩니다.

```python
import pandas as pd
from pipeline_base import BasePipelineParser

class MyEquipmentLogParser(BasePipelineParser):
  
    @classmethod
    def match(cls, file_path: str) -> bool:
        """
        이 파서가 해당 파일을 처리할지 결정합니다.
        파일명의 확장자, 특정 문자열 포함 여부, 또는 파일의 첫 줄을 읽어 판단할 수 있습니다.
        """
        # 예시: 파일명이 .csv로 끝나고 'equipment_A'를 포함할 때만 처리
        return file_path.lower().endswith('.csv') and 'equipment_A' in file_path

    def process_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        데이터 변환 로직을 작성합니다. (Pandas 문법 사용)
        """
        # 1. 컬럼명 정규화 (DB의 컬럼명과 일치해야 함)
        df.rename(columns={'P/N': 'part_no', 'QTY': 'stock_qty'}, inplace=True)
      
        # 2. 파생 컬럼 생성 또는 연산
        df['PROD_LINE'] = 1
      
        # 3. 데이터 타입 강제 지정 (안전성 확보)
        df['stock_qty'] = df['stock_qty'].fillna(0).astype(int)
        df['part_no'] = df['part_no'].astype(str)
      
        return df
```

### 2.3 고급 기능 (커스텀 리더 구현)

기본적으로 `.csv`는 `pd.read_csv()`, `.xlsx`는 `pd.read_excel()`로 읽힙니다. 만약 구분자가 탭(`\t`)이거나 인코딩이 다를 경우 `_read_file_to_dataframe` 메서드를 직접 오버라이딩하십시오.

```python
    def _read_file_to_dataframe(self, file_path: str) -> pd.DataFrame:
        # 예시: 탭으로 구분된 로그 파일, EUC-KR 인코딩 처리
        return pd.read_csv(file_path, sep='\t', encoding='euc-kr')
```

---

## 3. 로그 확인 및 디버깅

인제션 파이프라인의 실행 결과는 터미널 로그를 통해 직관적으로 확인할 수 있습니다.

```text
[my_table] 📥 New file detected: equipment_A_2026.csv
[my_table] 🚀 Pipeline Matched: MyEquipmentLogParser in my_custom_parser.py
[my_table] 💾 Local batch update success (100 rows). Changed cells: 300
[my_table] ✅ Successfully processed and archived: equipment_A_2026.csv
```

파이프라인이 정상적으로 매칭되었는지, 성공적으로 적재(Changed cells) 되었는지 위 로그들을 통해 즉각적인 파악이 가능합니다.

---

> [!TIP]
> **PostgreSQL NaN 에러 걱정 NO!**
> 파이프라인은 Pandas 연산 중 생길 수 있는 골치 아픈 `NaN`, `Infinity` 값들을 내부 시스템(부모 클래스의 `clean_for_postgres`)에서 안전한 JSON `null`로 자동 변환하여 DB에 넣습니다.
