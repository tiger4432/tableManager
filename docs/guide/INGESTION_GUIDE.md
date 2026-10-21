# 📥 AssyManager 인제션 파이프라인 가이드 (Ingestion Pipeline Guide)

> **Status:** 🟢 Living | **Last-verified:** 2026-10-21 (**§1.8-bis 가 체크리스트가 됐습니다** — «이미 읽었나»의 답은 `(경로, 표)` 로그 행의 도장 하나(소유자 10-21). 옛 두 층 원장 · §1.8-ter · `__force__` · `dedup_by_*` 는 은퇴. 그 앞 2026-09-07: **§1.10 맵 메타 자동 등록이 «은퇴»했습니다** — 소유자 지시 「맵 메타 자동 등록은 없애줘」(S-38). 그 절만 고쳤고 다른 절은 아래 날짜 기준입니다) · 직전 2026-08-17 (§1.12 외부 읽기 전용 voids.json 감시 — 실제 경로 확인, 본문은 0바이트라 합성 계약) | **Previous verification:** 2026-08-13 (2차 배치 — **§1.11 신설: 한 파일이 두 사실을 말할 때(void SAT)**, `346aa88`. 🔴 **워처는 테이블당 핸들러 하나라 같은 파일을 두 `raws/`에 모두 넣는다** · 🔴 **체인으로 대신할 수 없다**(깨끗한 스캔은 파생할 행이 0개다) · 로직은 추적되는 `void_sat_format.py`에 있고 손복사는 세 줄 shim 둘뿐 · **검증이 찾은 결함 둘은 둘 다 오라클 없던 자리에서 나왔다** — 깨끗한 스캔이 런을 하나도 못 만들던 무음 결함과, **어떤 수치 검사도 발화할 수 없는** 소수점 쉼표 칼럼 시프트. 직전 **§1.8-ter 신설 — tier 1을 «어디서» 묻는가**, `831ab68`. tier 1은 `_process_with_retry` 안에 있어서 **HIT조차 파일당 세션 1개 + `table_config.json` 디스크 재독 2회**를 냈다. 지금은 스윕과 트리 워크가 **이미 든 `stat`으로 500개씩 묶어** 묻고(`settle_already_terminal` → `find_terminal_by_path_stat_batch`) 걸러진 파일을 거기서 종결한다. 🔴 **술어는 다시 쓰지 않았고**(같은 `and_` 세 쌍을 OR로) **단일 조회는 무변경**이며 **걸러진 파일도 이동 재시도는 갚는다**. 실측 재스윕 26.432초→0.602초(43.9배), 콜드 스윕 1.0배(= 아무것도 안 건너뛴다는 대조군). ⚠️ **「~92 ms/file·≈35분」은 `assy_manager`에서 잰 «이전» 값**이고 그 격리 측정과 같은 실행이 아니다. 직전 **§1.8-bis 두 층 원장 신설**(`ba664c5`). 직전 2026-07-30 **§1.9 전면 대체 + §1.9-bis 신설** — `600b49d`+`a5eb934` 소스 대조: `directory_watcher.request_tree_ingest`/`_ingest_directory_tree`/`relative_source_path`/`is_managed_source`/`_unique_dest`/`nested_dirs_enabled`, `advanced_ingester.extract_path_metadata`/`_merge_row`/`process_file`/`REASON_*`/`ALLOWED_RULE_KEYS`. ① **평탄화가 사라졌습니다** — 파일은 승격되지 않고 **자기 중첩 경로 그대로** 적재되며 상대 POSIX 경로가 파서에 `self.rel_path`로 전달됩니다. `_build_collision_name`·`_resolve_flatten_dest`·`_sanitize_flatten_component`·`FLATTEN_SEP` 및 `~` 구분자·`__force__` 조작 방어가 **함께 소멸**(접합하는 코드가 없으면 조작할 토큰이 없음). 함께 신설: 조건부 아카이브(`is_managed_source` — 외부 읽기 전용 트리는 이동·삭제 없음), `_unique_dest`(동명 파일 아카이브 충돌 — 종전 `_<epoch>` 1회 시도는 같은 초에 POSIX에서 **덮어썼습니다**). 🔴 **`flatten_nested_dirs`는 뜻이 바뀐 채 이름을 유지**합니다(개명하면 운영자의 off 스위치가 조용히 무력화) — 로그 문구도 "파일이 적재되지 않는다"로 정정됐습니다. ② **§1.9-bis `filename_rules` 선언 규격 신설** — 이 스키마는 **어느 문서에도 없었습니다**: 허용 키 5개(미지 키는 거절)·명명 상태 4종(`no_match`/`ambiguous_reference`/`cast_failed`/**`path_value_discarded`** ← `path_overrides_header`에서 개명)·`required` 기본 false·로드 시점 거절(캡처 그룹 없는 정규식 포함)·대상은 **상대 POSIX 경로**·`^` 앵커 주의(살아 있는 규칙 0건이라 무피해). 🔴 **우선순위는 사용자 판정 `filename < header < row`** — 「파일이 정본」이 경로까지 확장됩니다. ⚠️ `600b49d`의 커밋 메시지는 `header < filename < row`로 적혀 있으나 그것은 `a5eb934`에서 **뒤집혔습니다**. 직전 2026-07-29: §1.10 맵 키 조합 규약 정정 — 7b 공용 캐노니컬라이저가 **같은 커밋에서 착지**해 "예정/TODO" 서술이 낡았음) | **Owner:** Ingester | **Source-of-truth:** `server/parsers/directory_watcher.py`, `pipeline_base.py`, `advanced_ingester.py` · 상위 [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md)

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
| 헤더 검증 | **적재 대상 컬럼(`display_columns`)** 과 대소문자 무시 대조. 🆕 09-26 `749318c9` — 선언 없는 칸은 파서가 빼지 않고 쓰기 고리로 넘기고, 쓰기 고리 «한 자리»가 버리며 셉니다(커스텀 파서와 같은 자리). **쓸 수 있는 칸이 하나도 없는 파일은 FAILED** — 선언 안 된 칸이든 선언됐지만 이 프로세스의 모델이 못 받는 칸이든(d4a949a8c ③) 파일 기록에 한 문장, «다음 행동 먼저»: 「Next: declare the undeclared columns in table_config.json; reload or restart so this process holds the unmapped columns, then Retry the file. Nothing was written to '<표>' - dropped: undeclared_column <칸>; unmapped_column <칸>.」(있는 사유만. 헤더에서 거절하든 쓰기 고리에서 거절하든 같은 문장, `crud.NothingWritten` · `crud.not_written_sentence`). **일부만 버린 파일은 SUCCESS** 그대로, 파일 기록에 「Next: … Not written: undeclared_column <칸>=<값 수>; unmapped_column <칸>=<값 수> over M row(s).」. 버림 자체는 옳은 경우가 흔하므로 표에 칸을 늘리지 않습니다 |
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
| 진행 가시화 | watcher가 QUEUED/PROCESSING/FINISHED를 `POST /internal/events/ingestion-state`로 push → 웹서버 인메모리 레지스트리(`ingestion/activity.py`) → **`GET /admin/file-ingestion/active`**. admin File 탭에 진행 섹션(HEAVY 배지·진행률 바·경과)과 **재기동 경고 배너** 표시. WS 이벤트 계약은 무변경 |
| heavy 워커 수 | 🆕 09-25 `18e54f8a` — 워커 **N**(`config/ingestion_settings.json` 의 `heavy_lane_workers`, 기본 1, 감시자가 뜰 때 읽음). 한 표(워크스페이스 키)는 한 워커가 차례대로, 다른 표끼리는 동시 — 박스 실측: 워커 2 에서 두 표의 11 MB 파일 처리 창이 1.10 초 겹침, 워커 1 에서는 하나 뒤에 하나. 소형은 계속 비차단 |

---

## 1.8 체크포인트 재개 (P2, 2026-07-26)

P1은 대형 파일이 **남을 막지 않게** 했지만, 재기동하면 진행 중이던 파일을 **0행부터 다시** 처리했습니다. P2가 그것을 닫습니다. 구현: `server/ingestion/checkpoint.py` + `directory_watcher.process_with_retry`/`_plan_checkpoint`. 「이미 읽었나」는 §1.8-bis 체크리스트가 답합니다.

**파일 시그니처** = `sha256:<size>:<digest>` — **샘플링이 아니라 전체 해시**입니다. 실측 500MB 0.535초(~935MB/s), 15.6MB 0.016초로 라이브 드릴 총 처리 415초의 0.004%라, 비용보다 정확성을 택했습니다.

| 항목 | 동작 |
|---|---|
| 저장소 | 신규 테이블 **`file_ingestion_checkpoints`**(`UNIQUE(table_name, file_signature)`). `FileIngestionLog`에 컬럼을 붙이지 않은 이유는 `create_all`이 ALTER를 하지 않아 **조회 프로세스보다 먼저 도는 마이그레이션**이 필요해지고 운영 DB에서 `UndefinedColumn` 500이 열리기 때문입니다. 준비: `python server/scripts/setup_ingestion_checkpoint.py`(멱등) |
| 원자성 | 오프셋 갱신(`record_chunk_progress`)은 청크 upsert와 **같은 트랜잭션**에서 일어납니다 → **"커밋된 행 수 == 기록된 오프셋"**이 항상 성립합니다 |
| 재개 조건 | 시그니처 + `total_rows` + `source_kind`(파서 정체성 `std` / `pipeline:<Class>`) + 오프셋 범위(`0 ≤ processed_rows ≤ total_rows`)가 **전부** 일치할 때만. 하나라도 다르면 0부터 재처리하되 **사유를 로그·`FileIngestionLog.detail`·완료 통지에 명시**합니다(조용한 재처리 금지) |
| 다시 넣기 | 어드민 재시도는 내용이 이미 `DONE` 이면 0 부터 다시 넣습니다(`_retry_should_restart`) |
| 적용 범위 | heavy / normal 레인, 기동·주기 스윕, 관리자 재시도 — **4경로 전부 동일 동작** |
| 비활성화 | `resume_from_checkpoint: false`로 재개만 끌 수 있습니다. 시그니처 계산이 `OSError`로 실패하면 체크포인트가 자동으로 비활성화되고 사유가 note에 남습니다 |

---

## 1.8-bis 체크리스트 — «이미 읽었나»의 답은 하나 (소유자 10-21)

> 소유자: 「(파일, 돌려야 할 테이블) 을 키로 넣고 체크리스트 하면 되잖아」 · 「문 나누지 말랬지」.

| 항목 | 동작 |
|---|---|
| 열쇠 | **(경로, 표)** — 경로는 `path_key`(소문자 · 구분자 하나)로 접어서 견줍니다. 양쪽 다 DB 가 접습니다 |
| 체크 | 그 열쇠의 `file_ingestion_logs` 행이 파일의 **(수정 시각, 크기)** 를 들고 있으면(`file_mtime` · `file_size`) 안 읽습니다. 하나라도 다르면 읽습니다 |
| 도장을 적는 곳 | 읽기가 «답을 낸» 자리 — SUCCESS, 그리고 파일 탓의 FAILED. **잠금 대기로 끝난 FAILED 는 도장이 없어** 다음 훑기가 다시 집습니다 |
| 묻는 자리 | 함수 하나 `checkpoint.checked` — raws 훑기 · 외장 훑기 · 폴더 트리 걷기 · 이벤트 · 수집기(소급 backfill)의 기다림. 재시도 문(파일 화면 Retry)은 **묻지 않고** 읽은 뒤 도장을 적습니다 |
| 표 읽기가 바뀌면 | 그 표의 스크립트 · table_config 항목 · 외장 소스 항목(`enabled` · `max_depth` 는 빼고)이 바뀌면 **그 표의 키만** 해제합니다 — 읽은 행의 도장을 비우고(훑기가 제자리 파일을 다시 읽음), 실패 파일은 재시도 문으로 넘깁니다. 상한 없음, 와처가 자기 속도로 읽습니다. 로그 `[Watcher] <표>: its reading changed (<부분>) - N read file(s) unchecked, K failed file(s) handed again` |
| 처음 한 번 | 이 칸이 오기 전의 로그 행은 도장이 비어 있어, 와처의 첫 훑기가 그 훑기의 stat 위에서 **한 번** 채웁니다(디스크를 따로 안 훑음): 최신 행이 SUCCESS 이고 파일이 그대로(행이 수정 시각 이후에 쓰임)면 도장을 적습니다. 로그 `[Watcher] read files stamped N · left for re-read M (failed K · changed since read C)`. 모든 외장 소스에 닿은 훑기가 끝나면 `config/watcher_read_files_stamped` 가 생기고 다시 돌지 않습니다 |
| 실패 방향 | 수정 시각과 크기를 그대로 둔 채 내용만 바꾼 파일은 다시 읽지 않습니다(수정 시각을 보존하는 복사 도구). 다시 읽히려면 파일 화면의 **Retry**, 여럿이면 `scripts/replay_ingestion.py --path … --apply`(그 키 해제 — `reread.uncheck`) |
| 은퇴 | 원장의 경로 tier 1 · 내용 서명 dedup(같은 내용이어도 다른 경로면 읽음, 소유자 10-20 ㄱ) · 훑기의 프로세스 메모리 · 외장 «수정» 이벤트의 해시 우회 · 파일 이름 `__force__` · 설정 `dedup_by_signature` / `dedup_by_path_stat`. 원장(`file_ingestion_checkpoints`)은 **이어 읽기(재개)** 만 맡습니다 |

**파일을 옮기지 않는 모드** — `archive_processed_files: false`. `.sample`의 기본값은 `true`(종전 동작)입니다. 「이 파일은 실패했다」는 `err/` 위치가 아니라 그 파일의 `file_ingestion_logs(status='FAILED')` 행이 듭니다.

⚠️ **`archive_processed_files: false`에서는 `raws/`가 무한히 자랍니다** — 워처는 아무것도 지우지 않으므로 보관 기간 정리는 운영자 몫입니다.

채점: `server/tests/test_a_file_read_is_checked_by_its_path_and_table.py`.

---

## 1.9 폴더 드롭 — **제자리 적재, 그리고 경로가 운반체다** (`600b49d` · 2026-07-30. 종전 「평탄화」 `0c6ac1a` 대체)

`raws/`에 파일이 **다중 층위 폴더로 감싸여** 들어오면, 파일마다 다 써진 뒤 **각 파일을 자기 실제 중첩 경로 그대로** 기존 이벤트 경로에 넣습니다. 파일을 루트로 승격시키지 않습니다. 구현: `directory_watcher.IngestionHandler.request_tree_ingest / _ingest_directory_tree`(트리거: 디렉토리 watchdog 이벤트 + 하위 폴더 다시 보기 — 기동 즉시, 그 뒤 `subfolder_recheck_seconds`(기본 30초)마다. 이미 있는 폴더에 나중에 온 파일은 이벤트가 없어 이것이 찾습니다).

> 🔴 **왜 바뀌었나 — 폴더명이 정보였습니다.** `raws/`의 폴더 이름은 랏·설비·날짜를 나릅니다. 종전 평탄화는 그것을 **버렸습니다**: `_resolve_flatten_dest`가 맨 이름을 **먼저** 시도했으므로 하위 경로 접두는 **이름 충돌이 났을 때만** 붙었고, 평탄화 후 중첩 경로는 `logger.info` 한 줄 말고는 **어디에도 남지 않았습니다.**
>
> 접두를 무조건으로 만들고 구분자를 발명해 다시 디코드하는 대신 **경로 자체를 나릅니다.** 파서는 이미 전체 경로를 받아서 그 뒤에 축약하므로(`advanced_ingester.process_file`), 폴더명을 파일명에 인코딩하는 것은 **호출 대상이 이미 갖고 있는 정보를 문자열로 왕복**시키는 일이었습니다. 그리고 `"/"`는 폴더명 안에 들어갈 수 없으므로 경로는 **발명한 구분자도, 살균도, 경계 표식도 필요 없습니다.**
>
> **사라진 기계장치**: `_build_collision_name` · `_resolve_flatten_dest` · `_sanitize_flatten_component` · `FLATTEN_SEP`. 접두 개명이 없으므로 **`~` 구분자 규칙도 함께 사라졌습니다**.

| 항목 | 동작 |
|---|---|
| 정온(quiescence) 게이트 | 트리 스냅샷(`{상대경로: (size, mtime)}`)을 폴링 간격(1초)마다 찍습니다. **파일 하나**가 두 스냅샷에서 같으면 그 파일은 다 쓴 것이라 **그때** 넣습니다 — 계속 자라는 파일 하나가 옆의 다 쓴 파일을 붙잡지 않습니다(소유자 10-08). 반쯤 쓴 파일은 읽지 않습니다(«다 씀» = 두 스냅샷(1.0초 간격)에서 크기 · 수정 시각이 같음 — 쓰기가 1.0초 넘게 멈추면 다 쓴 것으로 읽힌다. raws/ 맨 위 파일은 고정 지연 뒤 바로 읽는다 · 🆕 600초에는 다 쓴 파일을 «처리하는 시간»도 든다 — 처리 중에 다 쓴 파일은 «still writing» 으로 이름이 불려 다음 다시 보기(30초)까지 남는다(응용 잼)). 비워진 폴더 지우기는 **트리 전체**가 같을 때만입니다. 최대 600초 뒤에도 쓰는 중인 파일이 있으면 그 파일과 폴더는 두고 유예(하위 폴더 다시 보기가 재시도) — 로그 `[<표>] 📂 '<폴더>': N file(s) left - Tree ingestion deferred — K file(s) still being written after 600s (still writing: <이름 몇 개>; M finished file(s) dispatched) - next look in 30 s - #1 for this folder and reason (…)`. 같은 폴더 · 같은 이유는 1 · 10 · 100 번째만 말합니다. 같은 줄이 다른 이유도 말합니다 — 일꾼이 도는 중 · 보관 끔이라 처리 뒤 제자리(`kept in place (archive_processed_files=false)`) · 남은 파일(`Tree ingestion incomplete`) · 중첩 끔 |
| 파일 디스패치 | 모든 일반 파일을 mtime 오름차순으로 **자기 위치에서** 기존 이벤트 경로에 투입(`_handle_event` → 레인 라우팅 → 파서 → 체크포인트 → archives/·err/ **전부 무변경**). 바뀐 것은 **넘겨지는 경로가 중첩됐다는 것 하나**입니다. 그 앞에서 이미 읽은 파일은 체크리스트(`already_checked`, §1.8-bis)가 **묶어서** 묻고 걸러 `_handle_event`에 가지 않습니다. 로그의 「dispatched N」은 **실제 내려간 수**이고, 걸러진 수(`already read`)는 같은 줄에 함께 남습니다 |
| 파서가 받는 것 | 매칭된 파이프라인 파서 인스턴스에 **`self.rel_path`**(POSIX 상대 경로)를 심습니다 — `parse(path)` 시그니처를 넓히지 않습니다(사용자 스크립트가 전부 서브클래스이므로 시그니처 변경은 전수 수정입니다). 이 문자열이 **`filename_rules`가 매칭하는 대상**입니다(→ §1.9-bis) |
| 경로 문자열의 규격 | `relative_source_path(abs, root)` — **상대**(절대 경로는 규칙을 dev↔운영 사이에서 비이식적으로 만듭니다)이고 **POSIX 구분자**(Windows 구분자는 JSON 정규식에서 네 글자가 됩니다). 봉쇄는 **결과 기반**입니다(문자 블랙리스트가 아니라 "다시 join하면 같은 파일인가") — `..` 성분이나 다른 드라이브는 생존할 수 없고, 트리 순회는 이 검사에 실패하는 항목을 **건드리지 않고 남깁니다**(정션이 그 경로입니다) |
| 폴더 제거 | **비게 된 디렉터리만** `os.rmdir` — 내용물이 남은 폴더는 구조적으로 삭제 불가입니다. 처리 못 한 파일은 자기 디렉터리를 살려 두고, 하위 폴더 다시 보기가 나중에 재시도합니다 |
| 아카이브는 **조건부** | `is_managed_source(path)`가 두 이동 프리미티브를 함께 통제하므로 모든 호출부가 한 번에 덮입니다 — 워크스페이스 파일은 종전대로 archives/로, **외부(읽기 전용) 트리의 파일은 옮기지도·err/로 보내지도·삭제하지도 않고** 인제션 기록이 원본 경로를 가리킵니다. 외부 파일의 반복 «이미 읽음»은 **조용합니다**(스윕이 구조적으로 영원히 다시 찾으므로 스윕당 로그 한 줄은 실제 사건을 묻습니다) |
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

## 1.10 ⚰️ 맵 메타 자동 등록 — 은퇴 (M3, 2026-07-29 ~ 2026-09-07)

> 소유자 지시(2026-09-07): 「맵 메타 자동 등록은 없애줘」. 인제션이 `wafer_map_metadata`
> 행을 **지어 넣는 일은 이제 없습니다.** 메타는 맵 에디터 Push(사람)와 확정 기록으로만
> 들어옵니다.

```
운영에서는   맵 메타를 «메타 표»에 적습니다 — 에디터에서 규격을 넣고 Push 하거나 파일로.
            자동으로 지어 넣는 것은 «없습니다».
```

**은퇴 이유**(2026-08-30 판정이 기본값을 끈 그 이유가 끝까지 갔습니다): 합성 행이
`grid_start_x/y` 를 배치의 min x/y 로 박는데, 에디터에서 start x/y 는 shift 가 아니라
**좌표 «기준» 자체**입니다. 그래서 자동 등록 행은 구멍을 메우는 것이 아니라 **이후 모든
편집이 대조될 원점을 고정**했고, 에디터가 그것을 되돌리지 못했습니다.

🔴 **이미 쓰인 행은 그대로 있습니다.** 그 행들은 `auto_registered: true` 표지를 들고 있고,
그 표지를 읽는 쪽(`map_overlay.geometry_declaration` · 정렬의 참조 거절 · 에디터 화면)은
**하나도 바뀌지 않았습니다** — 표지를 지우면 그 행들이 「declared」로 거짓이 됩니다.
운영자의 조치도 종전과 같습니다: **그 맵의 물리 규격을 실제로 선언**하고 Push 하면 표지가
사라집니다. 규율 전문은
[map_editor/architecture_and_management §2.3-ter](../map_editor/architecture_and_management.md).

> **맵 키 조합 규약은 남습니다** — map_id 는 `map_key_columns` 값의 `'_'` 조인이고, 값 정규화는
> 선언 타입 기준 공용 캐노니컬라이저(`map_overlay.canonical_bind_value`)를 경유합니다.
> 등록과 조회가 같은 규칙으로 조합해야 메타가 실제로 발견됩니다. 고정 테스트
> `test_map_id_composition_pinned_for_7b`.

---

## 1.11 한 파일이 두 사실을 말할 때 — void SAT 포맷 (`346aa88` · 2026-08-13)

SAT 보이드 출력 하나가 **두 테이블**을 채웁니다 — `inspection_run`(스캔이 있었다)과 `void_obs`(그 스캔이 본 보이드). 스키마 쪽 서술은 [architecture/data_model §1.2-bis](../architecture/data_model.md), 운영 켜는 순서는 [process/OPERATOR_RUNBOOK §4](../process/OPERATOR_RUNBOOK.md).

- 🔴 **워처는 테이블당 핸들러 하나입니다. 그래서 같은 파일을 «두 `raws/`에 모두» 넣습니다.** 한쪽만 넣으면 절반만 적재되고 아무도 항의하지 않습니다.
- 🔴 **체인으로 대신할 수 없습니다** — 깨끗한 스캔(보이드 0건)은 파생할 행이 **0개**라 `void_obs`에서 `inspection_run`을 만들어 낼 수 없습니다. 이 스키마가 존재하는 이유가 바로 그 행이므로, 이것은 배선 취향이 아니라 구조적 제약입니다.
- **로직은 추적되는 `server/parsers/void_sat_format.py`에 있고, 워크스페이스에 손복사하는 것은 `.sample` 셋 세 줄짜리 shim 둘뿐입니다**(`void_obs_parser.py.sample` · `inspection_run_parser.py.sample`). 수정이 `git pull` 하나로 끝나게 하려는 배치이고, 워처가 `<workspace>/<table>/scripts/*.py`를 스캔하므로 **레지스트리 편집은 필요 없습니다.**
- ⚠️ **단위 없는 파일은 추측하지 않고 거절합니다**(`DEFAULT_UNIT`이 `None`).

### 검증이 찾아낸 결함 둘 — 둘 다 **오라클이 없던 자리**에서 나왔다

- 🔴 **깨끗한 스캔이 런을 «하나도» 만들지 못하고 있었습니다.** `_package_from_header`가 `parse_run_header`가 **쓴 적 없는** 헤더 키 넷을 읽고 있었습니다. 양쪽 절반은 따로 보면 각각 옳아 보이고 실패는 **무음**이었습니다 — 이 두-테이블 설계가 존재하는 이유가 정확히 그 행이므로, 그것을 잃는 결함이 조용한 것이 최악의 조합입니다. 이름 붙은 회귀 테스트로 고정했습니다.
- 🔴 **소수점 쉼표가 그 뒤 모든 컬럼을 한 칸씩 밀었습니다.** CSV에서 `1,25`는 **두 필드**이고, 밀린 값들도 전부 유효한 숫자로 파싱되며, `radius_x`가 `radius_y`의 값을 들게 됩니다. **어떤 수치 검사도 발화할 수 없습니다** — 지금은 **행 arity 검사**가 잡습니다.

> **재사용 관점**: 「한 소스가 여러 테이블을 채운다」·「분모를 자기 행으로 갖는다」의 카탈로그 항목은 [architecture/PRIMITIVES §1·§7](../architecture/PRIMITIVES.md).

---

## 1.12 외부 읽기 전용 `voids.json` — 경로가 웨이퍼를 말한다 (2026-08-17)

`ingestion_settings.json.external_sources`가 다른 시스템 소유 디렉터리를 기존 테이블 핸들러에 연결합니다.

⛔ **연결 대상 경로를 여기 적지 않습니다** (D-1 정정 2026-09-10). 종전 문장은 «이 개발 박스의»
경로 하나를 「현재 연결 대상」이라 적고 있었는데, 그것은 gitignore 된 `ingestion_settings.json`
의 값이라 다른 설치에 대해 아무 말도 하지 않습니다 — 운영자가 자기 경로를 그것으로 «맞추려» 하면
그 자체가 사고입니다. 정본은 그 파일의 `external_sources` 이고, 항목별 판정은 아래 점검 명령이
보여 줍니다. 파일 계약은 다음 하나입니다.

```text
<외부 폴더>/
└── WAFERID/
    └── WORK_YYYYMMDD_HHMMSS/
        └── voids.json
```

- **파서는 전체 `file_path`와 외부 루트 기준 상대 POSIX 경로를 함께 받습니다.** 웨이퍼 ID는 파일명 문자열을 자르지 않고 상대 경로의 첫 구성요소에서 읽습니다. `WORK_DATETIME`은 KST(`+09:00`)의 `observed_at`으로 바뀝니다. 구성요소가 셋이 아니거나 시각이 유효하지 않으면 파일 전체를 거절합니다. 본문 `observed_at`은 경로 시각과 같은 순간인지 확인하는 중복 선언일 뿐이며, 다르면 경로와 본문 중 하나를 고르지 않고 거절합니다.
- **경로 웨이퍼와 본문 `base_wafer_id`가 다르면 거절합니다.** 둘 중 하나를 임의로 고르면 모든 좌표가 그럴듯한 다른 웨이퍼에 붙습니다. 본문에 ID가 없을 때만 경로 값이 채워집니다.
- **한 파일을 두 바인딩이 읽습니다.** `inspection_run`은 스캔 분모를, `void_obs`는 발견을 기록합니다. 한 루트를 서로 다른 테이블에 연결하는 것은 허용하고, 같은 테이블에 겹치는 루트 둘은 상대경로가 둘이 되므로 설정 단계에서 거절합니다.
- **외부 원본은 읽기 전용입니다.** 성공·실패 어느 경우에도 archives/·err/로 이동하거나 삭제하지 않습니다. 로그 행의 `filepath`와 각 셀의 `source_name`은 전체 원본 경로를 보존하므로 모든 파일명이 `voids.json`이어도 웨이퍼·작업시각별 원천을 역추적할 수 있습니다.
- **신규·이동·수정 이벤트를 받으며 300초 재귀 스윕이 안전망입니다.** 네트워크 드라이브에서 watchdog 등록이 실패하거나 이벤트를 잃어도 스윕은 계속됩니다. 이벤트든 스윕이든 «이미 읽었나»는 체크리스트 하나가 답합니다(§1.8-bis — `(경로, 표)` 의 로그 행이 그 `(mtime, size)` 를 들고 있나). ⚠️ 따라서 **크기·mtime을 보존한 덮어쓰기**는 다시 읽히지 않습니다 — 그 파일은 파일 화면 Retry 입니다.
- **업데이트 안전 때문에 대상 테이블에 업무 키가 필수입니다.** 키 없는 legacy `void`는 재전달 때 새 행을 만들 수 있어 설정에서 거절하고, canonical `inspection_run`/`void_obs`만 받습니다.
- **체크리스트 칸은 기동이 보충합니다.** `file_ingestion_logs` 의 `file_mtime` · `file_size` 는 서버 · 와처 · 체인 워커 기동의 스키마 동기화가 더합니다(손으로 먼저: `server/migrations/add_file_ingestion_log_stamp.sql`).

JSON은 최상위 배열(`[{...}]`) 또는 객체(`{"voids": [...], "runs": [...], "unit": "um"}`)입니다. 배열/`voids`의 각 행에는 `base_x`, `base_y`, `gate`(또는 `stack_gate`/`layer`), `inchip_x`, `inchip_y`, `radius_x`, `radius_y`가 필요합니다. `unit`은 행·파일 루트·설정 옵션 중 한 곳에서 `um|px|mm`로 선언해야 하며 추측하지 않습니다. 깨끗한 스캔은 `voids: []`와 함께 `runs`/`scans`에 검사한 `base_x`, `base_y`, `gate`를 적어야 합니다. 빈 0바이트 파일은 정상적인 0건과 복사 중단을 구분할 수 없어 거절합니다.

> ⚠️ **관측과 결측 (2026-08-17):** 실제 경로와 `SAMPLE-01/WORK_20260101_000000/voids.json` 한 건은 확인했지만 그 파일은 **0바이트**였습니다. 따라서 경로·감시·두 테이블 배선은 자동 테스트로 확정했고, 위 JSON 본문 철자는 합성 픽스처 계약입니다. 생산 파일 첫 유효 표본이 도착하면 필드 철자·단위·clean-run 메타가 일치하는지 다시 검증해야 합니다. 현재 상태를 “실파일 형식 검증 완료”라고 보고하면 안 됩니다.

설정 예시는 [config/ingestion_settings](./config/ingestion_settings.md)와 `server/config/sample/ingestion_settings.json.sample`에 있습니다. 바인딩 추가·경로·파서·옵션 변경은 watcher 재기동 후 반영됩니다.

## 1.12-bis 외부 경로도 워크스페이스 파서로 들어간다 — 입구는 하나 (2026-08-18)

§1.12가 처음 착지했을 때 파서를 찾는 입구가 **둘이었고 서로 만나지 않았습니다.** 관리 `raws/`는 그 표의 워크스페이스 `scripts/`를 전부 올려 `match()`가 True인 첫 플러그인을 쓰는데(§2), 외부 소스는 `parser` 문자열을 **코드에 박힌 화이트리스트**와 대조해 내장 모듈만 부를 수 있었습니다. 그래서 「외부 폴더를 내가 쓴 스크립트로 읽기」가 **코드로 표현 불가능**했습니다.

지금은 해석 지점이 하나입니다.

- **`parser`를 적지 않으면**(키를 빼거나 빈 문자열) 대상 표의 워크스페이스 `scripts/`에서 찾습니다. 등록 시점에는 `BasePipelineParser` 하위 클래스가 **실재하는지**만 봅니다 — 파일이 아직 없으므로 `match()`를 물을 수 없고, 어느 플러그인이 그 파일을 받을지는 관리 `raws/`와 **똑같이** 파일 도착 시점의 `match()` 판정입니다. 🆕 10-20(`93dde66d2`, 소유자 «기본 파서도 있는데 왜 파서 없다고 막아») 플러그인이 없어도 막지 않습니다 — 플러그인이 없거나 다 사양하면 그 표의 `std_parse`(기본 켜짐)가 켜져 있으면 표준 파서가 읽습니다. 관리 `raws/`와 같은 함수(`_resolve_rows`)입니다.
- **`parser`를 적으면** 종전대로 화이트리스트(`SUPPORTED_EXTERNAL_PARSERS = {"voids_json"}`)를 봅니다. 기존 선언의 동작은 한 줄도 바뀌지 않았습니다.
- **어느 쪽으로도 못 읽으면 이름을 대고 거절**합니다 — 🆕 10-20 `parser` 를 안 적은 항목은 «플러그인 없음 + `std_parse: false`» 일 때뿐이고, 문장이 어느 표의 어느 `scripts/` 폴더를 봤는지 · std_parse 가 false 라는 것 · import에 실패한 스크립트 파일명을 같이 적습니다.

🔴 **경계는 사라지지 않고 옮겨졌습니다.** 화이트리스트가 지키던 것은 「config가 임의 코드를 부르지 못한다」였고, 지금은 **워크스페이스가 그 경계**입니다 — config는 **표 이름만** 말하고 코드 위치는 말하지 않으며, 그 표의 워크스페이스에 실재하는 플러그인만 돌 수 있습니다(원장의 `trusted_cutover_implementations()`가 손목록을 버리고 저장소 실재로 옮긴 것과 같은 판단).

플러그인은 관리 파일과 **같은 두 속성**을 받습니다: `self.rel_path`(외부 루트 기준 POSIX 상대경로)와 `self.source_root`(외부 루트 절대경로). 체크포인트가 기록하는 파서 정체성도 관리 경로와 같은 `pipeline:<파일>::<클래스>`이고, 셀의 `source_name`은 `external:workspace:<원본 절대경로>`입니다(`parser`를 적은 경우는 종전대로 `external:voids_json:<경로>`).

⚰️ **[10-20 `93dde66d2` 은퇴] 「표준 파서 폴백은 이 경로에 없습니다」** — 소유자가 뒤집었습니다(그 문장은 코드 판단이었고 소유자 판정이 아니었습니다). 지금은 플러그인이 모두 사양하면 `std_parse` 가 켜진 표는 표준 파서로 읽고, 꺼진 표(`table_config.json` 그 표 항목 `"std_parse": false`)만 거절합니다. 🔴 재기동하면 그동안 거절돼 있던 연결이 살아나 그 폴더의 기존 파일을 읽기 시작합니다 — 재기동 전 확인 줄은 RUN.md 10-20 절.

🆕 같은 날: 플러그인이 같은 `scripts/` 의 옆 `.py`(헬퍼)를 import 할 수 있고, 같은 이름이어도 표마다 자기 폴더의 것을 씁니다. 플러그인이 읽다가 낸 예외는 «Plugin <파일>::<클래스> could not read '<파일>': …» 로 그 파일이 FAILED 입니다(전: «Failed to load plugin script» 로 다음 플러그인에 넘어감). 연결이 루트 아래 파일을 보고도 하나도 안 받으면 워처 로그에 WARNING «External source <표>@<루트>: N file(s) under the root, none matched <glob/filename>» 한 줄 — 받는 파일이 생길 때까지 한 번입니다.

⚠️ **받는 파일은 `options.glob` 이 있으면 그 패턴, 없으면 `options.filename` 하나(기본 `voids.json`)입니다.** `glob` 이 있으면 `filename` 은 보지 않고, 받는 쪽에 안 맞는 파일에는 아무 일도 일어나지 않습니다(수집 기록 행도 없음). 🆕 10-11(`053d7858f`) `glob` 은 패턴 하나 또는 목록이고 루트에서의 경로를 견줍니다 — `**` 몇 겹이든(0 포함) 폴더 · `*` 한 겹 안 · `?` `/` 아닌 한 글자 · `/` 없는 패턴은 어느 깊이든 파일 이름. 예 `"options": {"glob": ["**/raw/**/*.jpg"]}`. `/` 로 시작하거나 끝나는 패턴은 거절되지 않지만 아무 파일도 받지 않습니다. 대소문자는 운영체제 규칙대로(윈도우는 무시). ⚠️ `parser: voids_json` 은 경로를 `<웨이퍼>/<작업 시각>/<options.filename>` 으로 다시 보므로, glob 으로 받은 다른 이름 · 다른 깊이의 파일은 FAILED 행으로 남습니다. 빈 패턴 · 빈 목록 · 글자 아닌 값은 «… .options.glob must be one glob string or a list of them, none empty, got <값>.» 으로 그 `external_sources` 항목 전체를 거절합니다(그 폴더는 감시하지 않음). 감시 사건 · 외부 쓸기 · 처리 중 메타 읽기 · 수정 표시가 모두 같은 판정(`IngestionHandler.external_source_context`)을 묻습니다.

**깊이:** 🆕 10-21 외장 소스 항목에 `"max_depth": N` — 적은 path 가 0, 그 아래 폴더 하나가 1. 더 깊은 폴더는 훑기가 들어가지 않고 이벤트 · 재시도도 그 파일을 안 집습니다. 안 적으면 끝까지. `recursive: false` = `max_depth: 0`(둘이 어긋나면 거절). 훑기마다 와처 로그에 소스별 한 줄 `External source <표>@<경로>: N file(s) looked at - outside the root · name not matched · not a file · stat failed · folders not matching · folders below max_depth · folders not listed · already read · dispatched` — 파일이 왜 안 넘어갔는지 사유별 수입니다.

**끈 상태 확인:** 등록 때 워처 로그에 `External sources declared: N (M disabled).` 한 줄이 남습니다. `enabled: false` 항목은 통과도 거절도 아니어서 종전에는 「선언 안 함」과 「꺼 둠」이 로그에서 구분되지 않았습니다. 항목별 판정은 `conda run -n assy_manager python server/scripts/check_external_sources.py`가 그대로 보여 줍니다.

## 1.12-ter 파서를 바꾼 뒤 이미 들어간 파일을 다시 읽기 — 실패 재시도 문의 `statuses` (2026-10-09)

파서(워크스페이스 `scripts/` · 외부 소스의 `options` · `table_config` 의 칸)를 바꾼 뒤, 이미 들어간 파일을 **있던 자리에서**(아카이브든 외부 경로든) 지금 파서로 다시 읽힙니다. 문은 실패 재시도와 같은 하나입니다 — POST `/admin/file-ingestion/retry-failed`(총괄 a4d135a06).

- `statuses`(쉼표 — 들어간 파일까지면 `SUCCESS,FAILED,SKIPPED`, 적지 않으면 FAILED 만 = 실패 재시도) · `folder`(그 폴더 «아래» — `A` 는 `AB` 를 안 잡음) · `since` / `until`(인입 시각, `YYYY-MM-DD` 또는 `YYYY-MM-DD HH:MM`) · `preview`.
- 미리보기(`preview=true`)가 다시 읽힐 파일 수 `count` · 상태별 `by_state` · 바로 아래 폴더별 `by_folder`, 기록이 말하는 자리에 없는 파일 수 `missing` 과 앞 다섯 이름 `missing_files` 를 말합니다. 한 파일을 여러 번 읽었으면 가장 새 기록 하나만 다시 읽힙니다.
- 🆕 10-11 넘길 파일이 `ingestion_settings.json` 의 `reread_max_files`(기본 25)를 넘으면 409 «N files - over the limit M; narrow the folder or raise reread_max_files in ingestion_settings.json» 이고 아무것도 표시하지 않습니다(미리보기는 상한을 안 따지고 답에 `limit` 을 싣습니다).
- 실행하면 요청 안에서 그 기록들을 `PENDING_RETRY` 로 표시하고(«N file(s) handed to the watcher»), 워처가 **하나씩** 읽습니다 — 워처의 그 표 핸들러로, 체크리스트를 묻지 않고(내용이 같아도 다시 읽음) 읽은 뒤 그 행이 파일을 체크하며, 끝나면 보통 인제션과 같은 토스트가 옵니다.
- 소급 관문을 안 잡습니다 — replay 가 돌아도 다시 읽기가 기다리지 않고, 다시 읽기가 replay 를 막지 않습니다.
- 🆕 10-11 되돌리기 — POST `/admin/file-ingestion/cancel-reread?folder=<폴더>[&preview=true]` 가 아직 기다리는 행을 넘기기 전 상태로 돌립니다. 워처가 이미 집은 행(PENDING 이후)은 안 건드립니다. 🆕 10-12 워처는 아직 `PENDING_RETRY` 인 행만 조건부로 집으므로 되돌린 행은 읽히지 않고, 취소 답의 수가 곧 되돌린 수입니다.
- ⚠️ 파서가 업무키를 바꾸면 옛 키의 행은 남습니다(업서트라 새 키 행이 따로 섭니다).
- ⚰️ 소급 «Re-read files»(976defaac)는 은퇴했습니다 — 옛 실행 기록은 목록에 `reread_files (retired)` 로 남습니다.
- 파일 여럿의 «읽었음»을 풀어 다음 훑기에 맡기는 길은 `scripts/replay_ingestion.py --path <파일> [--path …] [--table <표>] --apply` 입니다 — 10-21 부터 체크리스트 키 해제(`reread.uncheck`, 표 읽기가 바뀔 때와 같은 함수)이고 원장 행은 지우지 않습니다.

---

## 1.13 큰 적재 뒤에는 통계를 다시 잰다 — `analyze_after_rows` (S-124 ② · S-130, 2026-09-10)

적재가 끝난 표의 «통계»가 적재 전 모습 그대로면, 플래너가 있는 인덱스를 두고 순차 스캔을
고릅니다. 실측(2026-09-10): 44만 행이 들어간 표의 페이지 질의가 «0.7 s» 를 썼고 원인은
인덱스 부재가 아니라 «낡은 통계»였습니다.

```jsonc
// server/config/ingestion_settings.json
"analyze_after_rows": 10000   // 기본 10,000. 0 이하 = «끔»
```

- **적재 뒤**: 한 파일이 이 수보다 많은 행을 넣으면 그 표를 `ANALYZE` 합니다
  (`directory_watcher.analyze_after_rows` / `_analyze_after_load`). 자기 세션이고 잠금이
  없으며, 실패해도 «적재를 실패로 만들지 않습니다» — 행은 이미 커밋돼 있습니다.
- **기동 때**: 그 «전»에 들어간 표는 위 경로가 닿지 않으므로, 기동이
  `pg_stat_user_tables.n_mod_since_analyze` 를 읽어 이 임계를 넘은 표를 «같은 함수»로
  분석합니다(`chain_ingestion_worker._analyze_stale_tables_sync`). 대상은 「이 애플리케이션이
  선언한 표」 — 동적 카탈로그 ∪ `models.Base.metadata` ∪ 원장 표(`ledger.schema.owns_table`).
  넘지 않는 표는 «건드리지 않고», 그렇게 한 줄로 말합니다.

🔴 **임계와 함수가 «하나»입니다.** 「stale 한가」의 철자가 둘이면 기동에서 도는 쪽이
«아무도 재 본 적 없는» 쪽이 됩니다.

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
