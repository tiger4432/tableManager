# 📥 AssyManager 인제션 설정 가이드 (Ingestion Guide)

본 문서는 `assyManager`의 고급 자동화 인제션 시스템을 구축하고 관리하는 방법을 설명합니다.

---

## 1. 아키텍처 개요
인제션 시스템은 **디렉토리 감시(Watcher)**와 **복합 파싱(Advanced Ingester)** 엔진으로 구성됩니다.
- **Watcher**: 특정 폴더에 파일이 생성되면 감지하여 파싱을 트리거합니다. **50행 단위 배치 송신**으로 서버 부하를 최소화합니다.
- **Ingester**: 파일명, 헤더 영역, 본문 테이블 영역에서 데이터를 추출하여 결합합니다.

---

## 2. 워크스페이스 구조
각 테이블은 `server/ingestion_workspace/{table_name}/` 하위에 독립된 공간을 가집니다.

- **`raws/`**: 외부 시스템(설비 등)에서 로그 파일을 복사해 넣는 입력 폴더입니다.
- **`config/`**: 파싱 규칙을 정의한 JSON 설정 파일이 위치합니다. (명칭은 자유로우며 워처가 자동으로 탐색합니다.)
- **`scripts/`**: 테이블별 특화된 인제션 스크립트를 둘 수 있는 공간입니다.
- **`archives/`**: 처리가 완료된 파일이 자동으로 이동되는 보관 폴더입니다.

---

## 3. `config.json` 설정법
가장 핵심이 되는 설정 파일의 주요 섹션 설명입니다.

### header_rules (공통 정보 추출)
파일 상단의 헤더 라인에서 데이터를 추출하여 모든 행에 상수 컬럼으로 주입합니다.
```json
"header_rules": [
  { "column": "equipment_id", "regex": "Equip: ([A-Z0-9-]+)", "type": "str" },
  { "column": "batch_id", "regex": "Batch: (\\d+)", "type": "int" }
]
```

### table_start_pattern & table_end_pattern (경계 제어)
헤더 추출을 중단하고 테이블 파싱으로 전환할 지점(`start`)과, 테이블 파싱을 멈출 지점(`end`)을 지정합니다.
```json
"table_start_pattern": "--- DATA START ---",
"table_end_pattern": "--- DATA END ---"
```

### rules (본문 데이터 추출)
`table_start_pattern`이 발견된 이후의 행들을 파싱하는 규칙입니다.
```json
"rules": [
  { "column": "part_no", "regex": "P/N: ([\\w-]+)", "required": true },
  { "column": "qty", "regex": "Qty: (\\d+)", "type": "int" }
]
```

---

## 4. 운영 가이드
1. 새로운 테이블이 추가되면 `server/setup_workspace.py`를 실행하거나 수동으로 위 구조를 만듭니다.
2. `server/parsers/directory_watcher.py`를 실행하여 실시간 감시를 활성화합니다.
3. 데이터 정합성은 클라이언트의 **히스토리 패널**을 통해 실시간으로 검증할 수 있습니다.

---

> [!TIP]
> 상세 기술 사양은 [TECHNICAL_GUIDE.md](./TECHNICAL_GUIDE.md)를 참조하십시오.
