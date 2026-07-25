# 📥 AssyManager 인제션 파이프라인 가이드 (Ingestion Pipeline Guide)

> **Status:** 🟢 Living | **Last-verified:** 2026-07-25 | **Owner:** Ingester | **Source-of-truth:** `server/parsers/directory_watcher.py`, `pipeline_base.py` · 상위 [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md)

본 문서는 `assyManager`의 핵심 자동화 모듈인 **Directory Watcher**의 작동 원리와, 새로운 데이터를 DB로 적재하기 위한 **Pandas 기반 파이프라인(Pipeline) 구성 방법**을 설명합니다.

---

## 1. Directory Watcher 작동 원리

`DirectoryWatcher`는 지정된 `ingestion_workspace` 내의 장비/테이블 폴더를 실시간으로 감시하며 다음의 과정을 수행합니다.

1. **자동 탐색 (Discovery)**: `WorkspaceWatcher`가 백그라운드에서 실행되며, 각 테이블 폴더 하위의 `raws/` 폴더에 새로운 파일이 생성(또는 이동)되는 것을 감지합니다.
2. **파이프라인 매칭**: 파일이 감지되면 해당 테이블의 `scripts/` 폴더 내에 있는 모든 파이썬(`.py`) 스크립트를 로드합니다. 각 스크립트 내에 정의된 파서들의 `match(file_path)` 함수를 평가하여 가장 적합한 파서를 동적으로 할당합니다.
3. **실행 및 정제**: 매칭된 파서가 데이터를 Pandas DataFrame으로 로드하고 변환(연산/타입 캐스팅)을 수행합니다. 이후 PostgreSQL에 안전하게 적재될 수 있도록 `NaN`, `NaT` 등의 비정상 수치를 자동으로 정화(None으로 치환)합니다.
4. **표준 파서 폴백 (Std Parser Fallback, 2026-07-25)**: **어떤 커스텀 스크립트도 파일을 처리하지 않았을 때만** 표준 파서가 시도됩니다(→ §1.5). 스크립트 로드/`match()` 오류가 발생한 경우에는 깨진 스크립트를 은폐하지 않기 위해 폴백 없이 즉시 실패 처리됩니다.
5. **아카이빙 및 격리**: 성공적으로 DB에 배치(Batch) 적재가 완료되면, 원본 파일은 `archives/` 폴더로 자동 이동됩니다. 커스텀 파서와 표준 파서 모두 처리하지 못한 경우 오류가 발생하여 파일이 `err/` 폴더로 격리되며 데이터베이스에 실패 로그가 기록됩니다.

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
| 옵트아웃 | 워크스페이스 `config/config.json`에 `"std_parse": false` 지정 시 폴백 비활성 (기본 활성) |

`config.json`이 없는 워크스페이스도 **폴더명=테이블명 규약**으로 동작합니다(폴더명이 `table_config.json`에 등록된 테이블이면 감시 대상 포함).

> **⚠️ 옵트아웃 주의사항**
> - `"std_parse": false`는 **핫리로드되지 않습니다** — 핸들러가 값을 캐시하므로 config 변경 후 워처(또는 임베디드 모드의 웹 서버) **재기동이 필요**합니다. `SYSTEM_RELOAD`(/admin/reload-configs)로는 반영되지 않습니다.
> - **커스텀 변환(컬럼 연산·정규화 등)에 의존하는 워크스페이스는 `"std_parse": false` 명시를 권장**합니다. 헤더가 스키마와 우연히 일치하는 파일이 커스텀 파서의 `match()`에 걸리지 않으면, 변환 없이 raw 값 그대로 적재될 수 있습니다.

## 1.6 테이블 온보딩 = config 등록이 전부

`table_config.json`에 테이블을 등록하면 워처가 **누락된 워크스페이스 구조를 자동 생성**합니다 (`WorkspaceWatcher._provision_workspaces`):

```text
server/ingestion_workspace/<table>/
├── raws/  archives/  err/  auto_update/  scripts/
└── config/config.json      # {"table_name": "<table>"} 최소형
```

- **생성 시점**: ① 워처 부팅 시(`discover_and_watch`) ② `SYSTEM_RELOAD` 시(`sync_new_workspaces` — watchdog 런타임 `schedule()`로 **재기동 없이** 즉시 감시 시작).
- **기존 파일·설정은 변경하지 않음(누락분만 보충)**: 없는 폴더/파일만 새로 만들며 기존 내용은 절대 덮어쓰지 않습니다. config 폴더에 어떤 `.json`이라도 이미 있으면 `config.json`을 추가 생성하지 않지만, **config 폴더가 비어 있으면 최소형 `config.json`이 신설**될 수 있습니다(예: `bonding_map`).
- 시스템 내부 테이블은 제외 목록(`directory_watcher.AUTO_PROVISION_EXCLUDED_TABLES`, 현재 `wafer_map_metadata`)으로 관리합니다.

즉, **"config에 테이블 추가 → 폴더 자동 생성 → 스키마와 같은 헤더의 CSV를 raws/에 드롭 → 적재"** 가 무스크립트로 완결됩니다.

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
