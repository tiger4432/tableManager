# 📥 AssyManager 인제션 파이프라인 가이드 (Ingestion Pipeline Guide)

> **Status:** 🟢 Living | **Last-verified:** 2026-07-28 | **Owner:** Ingester | **Source-of-truth:** `server/parsers/directory_watcher.py`, `pipeline_base.py` · 상위 [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md)

본 문서는 `assyManager`의 핵심 자동화 모듈인 **Directory Watcher**의 작동 원리와, 새로운 데이터를 DB로 적재하기 위한 **Pandas 기반 파이프라인(Pipeline) 구성 방법**을 설명합니다.

---

## 1. Directory Watcher 작동 원리

`DirectoryWatcher`는 지정된 `ingestion_workspace` 내의 장비/테이블 폴더를 실시간으로 감시하며 다음의 과정을 수행합니다.

1. **자동 탐색 (Discovery)**: `WorkspaceWatcher`가 백그라운드에서 실행되며, 각 테이블 폴더 하위의 `raws/` 폴더에 새로운 파일이 생성(또는 이동)되는 것을 감지합니다.
2. **파이프라인 매칭**: 파일이 감지되면 해당 테이블의 `scripts/` 폴더 내에 있는 모든 파이썬(`.py`) 스크립트를 로드합니다. 각 스크립트 내에 정의된 파서들의 `match(file_path)` 함수를 평가하여 가장 적합한 파서를 동적으로 할당합니다.
3. **실행 및 정제**: 매칭된 파서가 데이터를 Pandas DataFrame으로 로드하고 변환(연산/타입 캐스팅)을 수행합니다. 이후 PostgreSQL에 안전하게 적재될 수 있도록 `NaN`, `NaT` 등의 비정상 수치를 자동으로 정화(None으로 치환)합니다.
4. **표준 파서 폴백 (Std Parser Fallback, 2026-07-25)**: **어떤 커스텀 스크립트도 파일을 처리하지 않았을 때만** 표준 파서가 시도됩니다(→ §1.5). 스크립트 로드/`match()` 오류가 발생한 경우에는 깨진 스크립트를 은폐하지 않기 위해 폴백 없이 즉시 실패 처리됩니다.
5. **아카이빙 및 격리**: 성공적으로 DB에 배치(Batch) 적재가 완료되면, 원본 파일은 `archives/` 폴더로 자동 이동됩니다. 커스텀 파서와 표준 파서 모두 처리하지 못한 경우 오류가 발생하여 파일이 `err/` 폴더로 격리되며 데이터베이스에 실패 로그가 기록됩니다.
6. **기동/주기 스윕 (이벤트 유실 안전망, 2026-07-25)**: 워처는 파일 생성 이벤트에만 의존하지 않습니다. ① **기동 스윕** — observer 기동 직후(및 신규 워크스페이스 런타임 등록 직후) 각 `raws/` 직속의 기존 파일을 mtime 오름차순으로 이벤트 경로와 동일하게 처리합니다(서버 정지 중 투입된 파일도 기동만으로 적재). ② **주기 스윕** — 300초 주기 백그라운드 스레드가 잔류 파일을 재스캔합니다. 처리 불가로 남은 파일은 (mtime, size) 시그니처로 기억해 같은 상태로는 재시도하지 않으며(무한 재시도 차단), 파일을 수정하면(mtime 변경) 다시 처리됩니다. `err/` 등 형제 폴더는 스윕 대상이 아니고, `raws/` 직속 하위 디렉토리는 스윕되지 않고 평탄화 트리거가 됩니다(→ §1.9). 스윕과 실시간 이벤트의 동시 진입은 락으로 차단됩니다(이중 처리 없음). 구현: `WorkspaceWatcher.sweep_existing_files / _periodic_sweep_loop`.

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

## 1.9 폴더 드롭 평탄화 (Flatten, 2026-07-28)

`raws/`에 파일이 **다중 층위 폴더로 감싸여** 들어와도 파일만 뽑아 파서에 넣고 폴더 계층은 제거합니다. 폴더는 영구 구조로 감시되지 않습니다 — **평탄화 후 폐기**가 계약입니다. 구현: `directory_watcher.IngestionHandler.request_flatten / _flatten_directory` (트리거: 디렉토리 watchdog 이벤트 + 기동/주기 스윕).

| 항목 | 동작 |
|---|---|
| 정온(quiescence) 게이트 | 트리 전체 스냅샷(`{상대경로: (size, mtime)}`)이 폴링 간격(1초, 파일 디바운스와 동일) 동안 **연속 2회 동일**할 때만 평탄화 — 복사 중인 폴더를 반쯤 비운 채 평탄화하지 않습니다. 최대 600초까지 대기 후 미안정이면 손대지 않고 유예(주기 스윕이 재시도) |
| 파일 승격 | 모든 일반 파일을 mtime 오름차순으로 `raws/` 루트로 이동 → **기존 파이프라인 그대로**(레인 라우팅·파서·체크포인트/dedup·archives/·err/ 무변경). 대형 파일은 평탄화된 경로 기준으로 heavy 레인에 정상 분류됩니다 |
| 이름 충돌 | **절대 덮어쓰지 않음** — 루트에 동명 파일이 있거나 배치 내 동명이 있으면 상대 경로 접두로 개명: `drop/lv2/x.csv → drop~lv2~x.csv` (그것도 겹치면 `~2`, `~3`…). 모든 개명은 로그에 남습니다 |
| 구분자 `~`인 이유 | `__` 구분자는 폴더명이 `force`일 때 접합부에서 강제 재처리 토큰 `__force__`를 조작(fabricate)합니다. `~`는 접합부에서 토큰을 만들 수 없고, 폴더명 자체에 든 `__force__`도 중화됩니다(파일명 자신의 토큰은 사용자 의도로 보고 유지). `user(<name>)` 업로더 접두는 개명 시 맨 앞으로 끌어올려 보존됩니다 |
| 숨김/시스템 파일 | `Thumbs.db` · `desktop.ini` · `.DS_Store`(대소문자 무시) 및 macOS AppleDouble `._*`는 **폴더와 함께 폐기**(적재하지 않음) |
| 실패 시 보존 | 빈 폴더만 `os.rmdir`로 제거 — **내용물이 남은 폴더는 절대 삭제하지 않습니다**. 잠긴 파일 등으로 이동 실패 시 해당 파일·폴더를 그대로 두고 warning, 주기 스윕(300초)이 잔여분을 재시도합니다 |
| 멱등/재진입 | 같은 트리에 이벤트+스윕이 중복 발화해도 진행 중 가드로 1회만 수행. zip 등 아카이브 추출은 범위 밖(폴더만) |
| 끄는 법 | `ingestion_settings.json`에 `"flatten_nested_dirs": false` (기본 true, 핫리로드 — 다음 폴더 트리거부터). 끄면 종전 동작(폴더 무시)으로 돌아갑니다 |

> **⚠️ 개명된 파일과 커스텀 파서**: 충돌 개명은 파일명을 바꾸므로, 파일명 패턴에 의존하는 커스텀 파서 `match()`에 걸리지 않을 수 있습니다(std 폴백 또는 err/). dedup·체크포인트는 내용 sha256 기준이라 개명의 영향을 받지 않습니다.

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
