# 📥 AssyManager 인제션 파이프라인 가이드 (Ingestion Pipeline Guide)

> **Status:** 🟢 Living | **Last-verified:** 2026-08-17 (§1.12 외부 읽기 전용 voids.json 감시 — 실제 경로 확인, 본문은 0바이트라 합성 계약) | **Previous verification:** 2026-08-13 (2차 배치 — **§1.11 신설: 한 파일이 두 사실을 말할 때(void SAT)**, `346aa88`. 🔴 **워처는 테이블당 핸들러 하나라 같은 파일을 두 `raws/`에 모두 넣는다** · 🔴 **체인으로 대신할 수 없다**(깨끗한 스캔은 파생할 행이 0개다) · 로직은 추적되는 `void_sat_format.py`에 있고 손복사는 세 줄 shim 둘뿐 · **검증이 찾은 결함 둘은 둘 다 오라클 없던 자리에서 나왔다** — 깨끗한 스캔이 런을 하나도 못 만들던 무음 결함과, **어떤 수치 검사도 발화할 수 없는** 소수점 쉼표 칼럼 시프트. 직전 **§1.8-ter 신설 — tier 1을 «어디서» 묻는가**, `831ab68`. tier 1은 `_process_with_retry` 안에 있어서 **HIT조차 파일당 세션 1개 + `table_config.json` 디스크 재독 2회**를 냈다. 지금은 스윕과 트리 워크가 **이미 든 `stat`으로 500개씩 묶어** 묻고(`settle_already_terminal` → `find_terminal_by_path_stat_batch`) 걸러진 파일을 거기서 종결한다. 🔴 **술어는 다시 쓰지 않았고**(같은 `and_` 세 쌍을 OR로) **단일 조회는 무변경**이며 **걸러진 파일도 이동 재시도는 갚는다**. 실측 재스윕 26.432초→0.602초(43.9배), 콜드 스윕 1.0배(= 아무것도 안 건너뛴다는 대조군). ⚠️ **「~92 ms/file·≈35분」은 `assy_manager`에서 잰 «이전» 값**이고 그 격리 측정과 같은 실행이 아니다. 직전 **§1.8-bis 두 층 원장 신설**(`ba664c5`). 직전 2026-07-30 **§1.9 전면 대체 + §1.9-bis 신설** — `600b49d`+`a5eb934` 소스 대조: `directory_watcher.request_tree_ingest`/`_ingest_directory_tree`/`relative_source_path`/`is_managed_source`/`_unique_dest`/`nested_dirs_enabled`, `advanced_ingester.extract_path_metadata`/`_merge_row`/`process_file`/`REASON_*`/`ALLOWED_RULE_KEYS`. ① **평탄화가 사라졌습니다** — 파일은 승격되지 않고 **자기 중첩 경로 그대로** 적재되며 상대 POSIX 경로가 파서에 `self.rel_path`로 전달됩니다. `_build_collision_name`·`_resolve_flatten_dest`·`_sanitize_flatten_component`·`FLATTEN_SEP` 및 `~` 구분자·`__force__` 조작 방어가 **함께 소멸**(접합하는 코드가 없으면 조작할 토큰이 없음). 함께 신설: 조건부 아카이브(`is_managed_source` — 외부 읽기 전용 트리는 이동·삭제 없음), `_unique_dest`(동명 파일 아카이브 충돌 — 종전 `_<epoch>` 1회 시도는 같은 초에 POSIX에서 **덮어썼습니다**). 🔴 **`flatten_nested_dirs`는 뜻이 바뀐 채 이름을 유지**합니다(개명하면 운영자의 off 스위치가 조용히 무력화) — 로그 문구도 "파일이 적재되지 않는다"로 정정됐습니다. ② **§1.9-bis `filename_rules` 선언 규격 신설** — 이 스키마는 **어느 문서에도 없었습니다**: 허용 키 5개(미지 키는 거절)·명명 상태 4종(`no_match`/`ambiguous_reference`/`cast_failed`/**`path_value_discarded`** ← `path_overrides_header`에서 개명)·`required` 기본 false·로드 시점 거절(캡처 그룹 없는 정규식 포함)·대상은 **상대 POSIX 경로**·`^` 앵커 주의(살아 있는 규칙 0건이라 무피해). 🔴 **우선순위는 사용자 판정 `filename < header < row`** — 「파일이 정본」이 경로까지 확장됩니다. ⚠️ `600b49d`의 커밋 메시지는 `header < filename < row`로 적혀 있으나 그것은 `a5eb934`에서 **뒤집혔습니다**. 직전 2026-07-29: §1.10 맵 키 조합 규약 정정 — 7b 공용 캐노니컬라이저가 **같은 커밋에서 착지**해 "예정/TODO" 서술이 낡았음) | **Owner:** Ingester | **Source-of-truth:** `server/parsers/directory_watcher.py`, `pipeline_base.py`, `advanced_ingester.py` · 상위 [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md)

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

## 1.8-bis 두 층 원장 — **파일을 옮기지 않고 재처리를 막는다** (2026-08-13)

§1.8의 dedup은 「이 내용을 적재했나」를 **파일 전체를 읽어야만** 답합니다. 그게 감당됐던 이유는 처리된 파일이 `archives/`로 **옮겨져** 스윕이 훑는 트리가 늘 비어 있었기 때문입니다. 파일을 제자리에 두기로 하면 그 전제가 사라지고, 스윕 비용이 **트리의 파일 수만큼의 해시**가 됩니다.

이 박스에서 잰 값(오늘 `archives/`가 든 22,626 파일 · 194.6MB — 옮기기를 멈추면 `raws/`에 쌓일 바로 그 집합):

| | |
|---|---|
| `listdir` + `stat` 1회 | **1.0초** |
| 전체 sha256 | **39.4초** (4.9MB/s · 575파일/s — 바이트가 아니라 **파일당 열기·읽기 오버헤드**가 지배합니다) |

그래서 앞에 싼 층을 하나 답니다.

| 층 | 열쇠 | 판정 |
|---|---|---|
| **Tier 1** | `(table_name, filepath, file_mtime, file_size)` | 원장에 **종결(`DONE` 또는 `FAILED`)** 행이 있으면 **읽지 않고** 스킵. stat 1회 |
| **Tier 2** | `sha256:<size>:<digest>` | 하나라도 다르면 종전대로 해시. **내용 시그니처가 여전히 최종 권위**이고, 같은 내용이 새 경로로 오면 그 위치를 원장에 남긴 뒤 스킵합니다 |

🔴 **Tier 1의 실패 방향을 알고 켜십시오.** tier 1은 **「mtime과 size가 그대로인 채 내용만 바뀐 파일을 다시 읽지 않는 쪽」**으로 집니다 — mtime을 보존하는 복사 도구가 있고, 같은 길이로 같은 마이크로초에 덮어써도 그렇게 됩니다. 파일을 한 번만 쓰는 fab 피드에는 맞는 거래(스윕 39초→1초)지만 **판단이지 공짜가 아닙니다**. 되돌리는 스위치가 `dedup_by_path_stat: false`이고, `dedup_by_signature: false`(전역 강제 재처리)는 **tier 1까지 같이 끕니다**.

**파일을 옮기지 않는 모드** — `archive_processed_files: false`. `.sample`의 기본값은 `true`(종전 동작)이고, 운영 전환은 운영자의 결정입니다.

| 옮길 때 「위치」가 들던 사실 | 안 옮길 때 그 사실이 사는 곳 |
|---|---|
| 「이 파일은 처리됐다」 = `archives/`에 있음 | 원장의 `status='DONE'` 행 (+ tier-1 열쇠) |
| **「이 파일은 실패했다」 = `err/`에 있음** | 원장의 **`status='FAILED'` 행** — `filepath`가 **어느 파일**인지, `note`가 **왜**인지를 듭니다. 트레이스는 종전 그대로 `file_ingestion_logs(status='FAILED')` |

🔴 **`FAILED` 행은 「다시 시도하지 않는다」까지 뜻합니다** — `err/`로 옮긴 파일이 자동 재시도되지 않던 것과 같은 의미론입니다. 파일을 고치면 `mtime`이 바뀌어 tier 1이 miss하고 자동으로 다시 걸립니다. 강제하려면 `__force__` 또는 어드민 재시도.

⚠️ **`archive_processed_files: false`에서는 `raws/`가 무한히 자랍니다** — 워처는 이제 아무것도 지우지 않으므로 보관 기간 정리는 운영자 몫입니다.
⚠️ **`__force__` 파일을 제자리에 두면 스윕마다 재적재됩니다**(실측). 토큰은 「항상 다시 넣어라」는 뜻이고, 옮기지 않으면 그것을 멈출 것이 없습니다 — 1회 재처리 뒤 **파일명에서 토큰을 빼거나 파일을 치우십시오**.

🔴 **스키마 선행 조건**: `server/migrations/add_ingestion_ledger_path_stat.sql`. `create_all`도 `ensure_ingestion_checkpoint_table`도 **기존 테이블에 컬럼을 추가하지 않으므로**, 이미 `file_ingestion_checkpoints`가 있는 DB는 이 파일을 한 번 돌려야 합니다. 안 돌리면 원장 **읽기부터** `UndefinedColumn`으로 실패하고(실측), 워처는 살아남되 **체크포인트·dedup이 통째로 꺼진 채**로 삽니다 = 파일을 안 옮기는 모드와 겹치면 **모든 파일이 매 스윕 재적재**됩니다.

---

## 1.8-ter Tier 1을 **어디서** 묻는가 — 이미 `stat`을 든 호출부에서, **묶어서** (`831ab68` · 2026-08-13)

§1.8-bis는 tier 1이 **무엇을** 묻는지를 정합니다. 이 절은 **어디서** 묻는지이고, **그 자리가 tier 1 자체보다 컸습니다.**

tier 1은 원래 `_process_with_retry` **안**에 있었습니다 — 스윕과 트리 워크가 이미 `os.stat`을 들고 있는 지점보다 **디스패치 한 단계 아래**입니다. 그래서 **HIT조차 거기까지 가는 파이프라인 전액을 냈습니다**: 파일당 `SessionLocal()` 하나, 파일당 `table_config.json` **디스크 재독 2회**, 파일당 `ingestion_settings.json` 재독.

| | |
|---|---|
| 이미 결론 난 파일 1개가 그 자리까지 가는 비용 | **~92 ms** — ⚠️ **이 수는 `assy_manager`에서 잰 «이전» 값**이고, 아래 격리 측정과 **같은 실행에서 나온 수가 아닙니다** |
| 22,626 파일 트리에 그 값을 곱하면 | **≈35분** (같은 출처 · 같은 단서) |
| 그 파일들을 **찾는** `listdir + stat` | **1.0초** |

🔴 **35분 중 원장 몫은 0이었습니다.** 느렸던 것은 질문이 아니라 **질문에 도달하는 길**입니다.

**지금**: `IngestionHandler.settle_already_terminal(entries)`가 `(abs_path, (mtime, size))` 목록을 받아 `ingestion_checkpoint.find_terminal_by_path_stat_batch(db, table_name, entries)`로 **`TIER1_BATCH_SIZE = 500`개씩 한 질의에** 묻고, 걸러진 파일을 **거기서 종결**합니다. 부르는 곳은 **둘**입니다 — `WorkspaceWatcher.sweep_existing_files`(기동·주기 스윕)와 `IngestionHandler._ingest_directory_tree`(§1.9 폴더 드롭). 걸러지지 않은 파일은 `_handle_event`로 **종전 경로 그대로** 내려갑니다.

- 🔴 **술어를 다시 쓰지 않았습니다.** 배치는 파일마다 단일 조회가 만드는 `and_(filepath, file_mtime, file_size)` **바로 그 세 쌍**을 기여하고 같은 `table_name` + 종결 상태 필터 아래 OR로 묶습니다 — 비교는 **SQL 안에** 남습니다. 파이썬에서 stat을 비교하면 `DateTime(timezone=True)`가 백엔드마다 **어떻게 돌아오는지**(SQLite는 naive, PostgreSQL은 세션 타임존)를 다시 유도해야 하고, 그걸 틀리면 **전부 걸러지거나 하나도 안 걸러지고 둘 다 조용합니다.**
- **단일 조회 `find_terminal_by_path_stat` / `_try_path_stat_skip`은 무변경**입니다. 배치가 걸러 주지 않는 것 전부를 **여전히 그쪽이** 답합니다 — 배치는 빠른 답이 **더 일찍 도착**하게 할 뿐입니다.
- 🔴 **걸러진 파일은 no-op이 아닙니다.** 파일을 옮기는 모드에서 종결된 파일이 아직 `raws/`에 있다면 **그 이동이 실패한 것**이고, 재시도를 빼면 그 파일이 — 중첩 인제션이면 **그 디렉터리 통째로** — 영구히 남습니다. `_settle_terminal_hits`가 그 이동 재시도를 `_handle_event`와 **같은 `processing_files` 클레임** 아래에서 갚습니다. `archive_processed_files: false`(옮기지 않는 모드)에서는 갚을 것이 없으므로 조기 반환합니다.
- **실패 방향은 「종전 경로」입니다.** 원장을 못 읽으면 빈 집합을 돌려주고 **모든 파일이 예전처럼 개별 디스패치**됩니다(가용성 우선 — `_try_path_stat_skip`과 같은 규칙).
- **끄는 스위치는 새로 생기지 않았습니다** — `dedup_by_path_stat: false`와 `dedup_by_signature: false`가 이 배치도 함께 끕니다(계약을 `dedup_by_path_stat_enabled()`에서 그대로 상속합니다).

**실측** (격리 `assy_qa` · 후보 파일 2,001개 · 원장 52,001행 · 두 팔을 번갈아 실행 · 중앙값):

| 시나리오 | 이전 | 이후 | |
|---|---|---|---|
| 재기동 후 **변경 없는 트리** 재스윕 | 26.432초 (13.21 ms/file) | **0.602초** (0.30 ms/file) | **43.9배** |
| **콜드 스윕**(전부 신규) | 21.140초 | 20.964초 | **1.0배 — 이것이 「아무것도 건너뛰지 않았다」는 대조군입니다** |
| 그중 새 파일 1개 | 31.0초 | 1.81초 | |
| 그중 변경된 파일 1개 | 31.2초 | 1.96초 | |
| 그중 `__force__` 파일 1개 | 28.5초 | 1.81초 | |

**배치 크기 500은 고른 것이 아니라 잰 것입니다** (같은 2,001 파일, ms/file):

| batch | 50 | 100 | 250 | **500** | 1000 | 2000 |
|---|---|---|---|---|---|---|
| ms/file | 0.37 | 0.46 | 0.41 | **0.41** | 0.59 | 1.26 |

50~500이 평평하고 그 뒤로 나빠집니다 — **2,001개를 한 질의로 묻는 것이 500짜리 다섯 질의보다 3배 나쁩니다.** 파일당 바인드는 3개라 500 청크가 ~1,500개로 PostgreSQL의 65,535 상한과는 거리가 멀고, **먼저 무너지는 것은 OR arity에 따라 자라는 «계획 비용»**입니다. 500 = 평평한 구간의 꼭대기(계획 비용이 아직 0인 채로 왕복이 가장 적은 지점)이고, 22,626 파일 트리를 **46 질의**로 유지합니다.

⚠️ **트리 워크 쪽이 스윕보다 더 아픕니다.** `_ingest_directory_tree`는 트리거마다 트리의 **모든 파일을 다시 디스패치**하고 스윕의 `_sweep_attempted` 같은 인메모리 캐시가 없습니다 — 파일을 안 옮기는 모드에서는 트리가 영원히 안 비므로 **재기동당 1회가 아니라 매 사이클** 그 비용을 냅니다.

채점: `server/tests/test_sweep_tier1_hoist.py`(18) + `test_nested_dir_ingestion.py`(22).

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
| 파일 디스패치 | 모든 일반 파일을 mtime 오름차순으로 **자기 위치에서** 기존 이벤트 경로에 투입(`_handle_event` → 레인 라우팅 → 파서 → 체크포인트/dedup → archives/·err/ **전부 무변경**). 바뀐 것은 **넘겨지는 경로가 중첩됐다는 것 하나**입니다. 🔴 **[`831ab68`] 그 앞에 tier-1 배치 관문이 하나 섭니다** — 이미 결론 난 파일은 `settle_already_terminal`이 **묶어서** 원장에 묻고 여기서 종결하므로 `_handle_event`에 가지 않습니다(§1.8-ter). 이 루프는 트리거마다 트리 전체를 다시 디스패치하고 인메모리 캐시가 없어 **스윕보다 이 관문이 더 필요한 자리**입니다. 로그의 「dispatched N」은 이제 **후보 수가 아니라 실제 내려간 수**이고, 걸러진 수는 같은 줄에 함께 남습니다 |
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

`ingestion_settings.json.external_sources`가 다른 시스템 소유 디렉터리를 기존 테이블 핸들러에 연결합니다. 현재 연결 대상은 `C:/Users/kk980/void`이고 파일 계약은 다음 하나입니다.

```text
C:/Users/kk980/void/
└── WAFERID/
    └── WORK_YYYYMMDD_HHMMSS/
        └── voids.json
```

- **파서는 전체 `file_path`와 외부 루트 기준 상대 POSIX 경로를 함께 받습니다.** 웨이퍼 ID는 파일명 문자열을 자르지 않고 상대 경로의 첫 구성요소에서 읽습니다. `WORK_DATETIME`은 KST(`+09:00`)의 `observed_at`으로 바뀝니다. 구성요소가 셋이 아니거나 시각이 유효하지 않으면 파일 전체를 거절합니다.
- **경로 웨이퍼와 본문 `base_wafer_id`가 다르면 거절합니다.** 둘 중 하나를 임의로 고르면 모든 좌표가 그럴듯한 다른 웨이퍼에 붙습니다. 본문에 ID가 없을 때만 경로 값이 채워집니다.
- **한 파일을 두 바인딩이 읽습니다.** `inspection_run`은 스캔 분모를, `void_obs`는 발견을 기록합니다. 한 루트를 서로 다른 테이블에 연결하는 것은 허용하고, 같은 테이블에 겹치는 루트 둘은 상대경로가 둘이 되므로 설정 단계에서 거절합니다.
- **외부 원본은 읽기 전용입니다.** 성공·실패·중복 스킵 어느 경우에도 archives/·err/로 이동하거나 삭제하지 않습니다. 기록의 `filepath`는 원본 위치입니다.
- **신규·이동·수정 이벤트를 받으며 300초 재귀 스윕이 안전망입니다.** 수정 이벤트는 `(mtime,size)`가 우연히 그대로여도 tier-1을 한 번 우회하고 내용 sha256까지 확인합니다. 네트워크 드라이브에서 watchdog 등록이 실패하거나 이벤트를 잃어도 스윕은 계속됩니다. 스윕만 놓고 보면 `(table binding, path, mtime, size)`가 같은 잔류 파일은 다시 보내지 않습니다. ⚠️ 따라서 **수정 이벤트까지 유실되고 크기·mtime도 보존된 덮어쓰기**는 다음 스윕이 발견하지 못합니다. 이 실패 방향을 없애려면 전 파일 주기 해시 비용을 지불하는 별도 노브 판정이 필요하며 현재는 없습니다.
- **업데이트 안전 때문에 대상 테이블에 업무 키가 필수입니다.** 키 없는 legacy `void`는 재전달 때 새 행을 만들 수 있어 설정에서 거절하고, canonical `inspection_run`/`void_obs`만 받습니다.

JSON은 최상위 배열(`[{...}]`) 또는 객체(`{"voids": [...], "runs": [...], "unit": "um"}`)입니다. 배열/`voids`의 각 행에는 `base_x`, `base_y`, `gate`(또는 `stack_gate`/`layer`), `inchip_x`, `inchip_y`, `radius_x`, `radius_y`가 필요합니다. `unit`은 행·파일 루트·설정 옵션 중 한 곳에서 `um|px|mm`로 선언해야 하며 추측하지 않습니다. 깨끗한 스캔은 `voids: []`와 함께 `runs`/`scans`에 검사한 `base_x`, `base_y`, `gate`를 적어야 합니다. 빈 0바이트 파일은 정상적인 0건과 복사 중단을 구분할 수 없어 거절합니다.

> ⚠️ **관측과 결측 (2026-08-17):** 실제 경로와 `SAMPLE-01/WORK_20260101_000000/voids.json` 한 건은 확인했지만 그 파일은 **0바이트**였습니다. 따라서 경로·감시·두 테이블 배선은 자동 테스트로 확정했고, 위 JSON 본문 철자는 합성 픽스처 계약입니다. 생산 파일 첫 유효 표본이 도착하면 필드 철자·단위·clean-run 메타가 일치하는지 다시 검증해야 합니다. 현재 상태를 “실파일 형식 검증 완료”라고 보고하면 안 됩니다.

설정 예시는 [config/ingestion_settings](./config/ingestion_settings.md)와 `server/config/sample/ingestion_settings.json.sample`에 있습니다. 바인딩 추가·경로·파서·옵션 변경은 watcher 재기동 후 반영됩니다.

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
