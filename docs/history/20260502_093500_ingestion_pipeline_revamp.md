# Data Ingestion Pipeline Architecture Revamp

## 변경 개요 (Overview)
기존 `DirectoryWatcher`의 단일 `custom_parser.py` 함수 실행 방식을 완전히 폐기하고, Pandas 기반의 강력한 **객체지향 파이프라인 아키텍처(Class-based Pipeline)**로 전면 개편했습니다. 이를 통해 복잡한 데이터 조작(연산, 타입 캐스팅)과 PostgreSQL JSONB 호환성(NaN 처리)을 시스템 수준에서 보장합니다.

## 주요 변경 사항 (Key Changes)
1. **`BasePipelineParser` 도입**:
   - `match(cls, file_path)`: 파서가 특정 파일(파일명 또는 내용 기반)을 처리할지 동적으로 결정.
   - `process_dataframe(self, df)`: Pandas DataFrame을 이용한 강력한 데이터 전처리 및 연산 제공.
   - `clean_for_postgres(self, df)`: NaN, NaT, Inf 등의 비정상 수치를 JSON 표준 `None`으로 자동 치환하는 클렌징 레이어 내장.
2. **`DirectoryWatcher` 동적 탐색(Discovery)**:
   - `scripts/` 폴더 내의 모든 `.py` 파일을 스캔하여, `BasePipelineParser`를 상속받은 하위 클래스들을 찾습니다.
   - 각 클래스의 `match`를 평가하여 적합한 파서를 자동 배정합니다.
3. **기존 스크립트 마이그레이션**:
   - `production_plan` 및 `inventory_master` 워크스페이스의 기존 `custom_parser.py` 스크립트를 신규 클래스 기반 아키텍처로 모두 마이그레이션 하였습니다.
   - 파일 확장자(`.csv`, `.log`)에 따라 하나의 스크립트 파일 안에서도 독립된 파서 클래스가 분기 처리되도록 리팩토링했습니다.

## 코드 스니펫 (Code Snippets)

### 변경 후 파서 구현 예시 (Inventory Master)
```python
import pandas as pd
import random
from pipeline_base import BasePipelineParser

class InventoryMasterCSVParser(BasePipelineParser):
    @classmethod
    def match(cls, file_path: str) -> bool:
        return file_path.lower().endswith('.csv')
        
    def process_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        df['PROD_LINE'] = 1
        return df

class InventoryMasterLogParser(BasePipelineParser):
    @classmethod
    def match(cls, file_path: str) -> bool:
        return file_path.lower().endswith('.log')
        
    def _read_file_to_dataframe(self, file_path: str) -> pd.DataFrame:
        return pd.read_table(file_path, sep='\t')
        
    def process_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        df['unit_price'] = df.get('part_no', pd.Series(dtype=object)).apply(lambda x: random.randint(1, 100))
        return df
```

## 아키텍처 및 시스템 영향 (Architecture Impact)
- **단일 책임 원칙(SRP)**: 파서마다 독립된 클래스를 가짐으로써 거대한 `if/else` 블록이 사라지고 유지보수성이 극대화되었습니다.
- **PostgreSQL 무결성 확보**: `clean_for_postgres`가 모든 데이터를 최종적으로 정화하므로, 데이터 엔지니어가 실수로 NaN 값을 남겨도 시스템이 500 에러를 뱉는 현상이 원천 차단됩니다.
- **데이터 엔지니어링 편의성**: Pandas 통합으로 인해 복잡한 집계나 연산이 가능해졌습니다.
