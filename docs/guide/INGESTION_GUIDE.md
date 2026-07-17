# 📥 AssyManager 인제션 파이프라인 가이드 (Ingestion Pipeline Guide)

본 문서는 `assyManager`의 핵심 자동화 모듈인 **Directory Watcher**의 작동 원리와, 새로운 데이터를 DB로 적재하기 위한 **Pandas 기반 파이프라인(Pipeline) 구성 방법**을 설명합니다.

---

## 1. Directory Watcher 작동 원리

`DirectoryWatcher`는 지정된 `ingestion_workspace` 내의 장비/테이블 폴더를 실시간으로 감시하며 다음의 과정을 수행합니다.

1. **자동 탐색 (Discovery)**: `WorkspaceWatcher`가 백그라운드에서 실행되며, 각 테이블 폴더 하위의 `raws/` 폴더에 새로운 파일이 생성(또는 이동)되는 것을 감지합니다.
2. **파이프라인 매칭**: 파일이 감지되면 해당 테이블의 `scripts/` 폴더 내에 있는 모든 파이썬(`.py`) 스크립트를 로드합니다. 각 스크립트 내에 정의된 파서들의 `match(file_path)` 함수를 평가하여 가장 적합한 파서를 동적으로 할당합니다.
3. **실행 및 정제**: 매칭된 파서가 데이터를 Pandas DataFrame으로 로드하고 변환(연산/타입 캐스팅)을 수행합니다. 이후 PostgreSQL에 안전하게 적재될 수 있도록 `NaN`, `NaT` 등의 비정상 수치를 자동으로 정화(None으로 치환)합니다.
4. **아카이빙 및 격리**: 성공적으로 DB에 배치(Batch) 적재가 완료되면, 원본 파일은 `archives/` 폴더로 자동 이동됩니다. 매칭되는 파서가 없을 경우 오류가 발생하여 파일이 `err/` 폴더로 격리되며 데이터베이스에 실패 로그가 기록됩니다.

---

## 2. 파이프라인(Pipeline) 구성 방법

새로운 파일 포맷을 처리하려면 `scripts/` 폴더에 파이썬 파일을 생성하고 `BasePipelineParser`를 상속받는 클래스를 정의하면 됩니다. (파일명은 자유로우며 하나의 파일에 여러 파서 클래스를 두어도 무방합니다.)

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
