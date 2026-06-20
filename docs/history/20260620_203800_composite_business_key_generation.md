# 2026-06-20 설정 기반 복합 비즈니스 키(Composite Business Key) 자동 생성 기능 구현

실시간 인제션 스크립트 작성 시 비즈니스 키(예: `pkg_id`)를 직접 파싱하고 조립하는 보일러플레이트 코드를 줄이고 설정 중심으로 데이터 관리를 일원화하기 위해, `table_config.json` 메타데이터에 기반한 **복합 비즈니스 키 동적 조립 기능**을 설계하고 백엔드에 안전하게 구현했습니다.

## 주요 변경 사항

### 1. `table_config.json` 복합 키 메타데이터 사양 확장 및 데이터 설정 추가
- **설정 추가**: `composite_key_source` 및 `composite_key_separator` 설정을 신설했습니다.
- **예시 (bonding_map)**:
  ```json
  "bonding_map": {
      "business_key": "pkg_id",
      "composite_key_source": ["base", "x", "y"],
      "composite_key_separator": "_",
      ...
  }
  ```
- 이 설정을 통해 각 컬럼의 물리 데이터(`base_x_y`) 조합이 비즈니스 키 필드(`pkg_id`)에 자동으로 매핑되도록 지원합니다.

### 2. `DirectoryWatcher` 내 복합 비즈니스 키 동적 조립 파이프라인 구축
- **대상 파일**: `server/parsers/directory_watcher.py`의 `_send_to_upsert`
- **구현 방식**:
  - 파싱 결과가 업서트 버퍼(`_send_to_upsert`)로 유입될 때, 대상 행 데이터 내에 정의된 비즈니스 키(예: `pkg_id`)가 누락되었는지를 선제 검사합니다.
  - 비즈니스 키가 없고 `composite_key_source` 메타데이터가 존재할 경우, 해당 소스 컬럼들의 값을 조회하여 설정된 구분자(기본값 `_`)로 이어붙여 비즈니스 키 값을 자동 생성 및 주입합니다.
  - 이 기능은 기존 파서가 명시적인 고유 키를 넘겨주었을 때의 하위 호환성을 100% 유지하도록 설계되었습니다.

### 3. 다중 모듈 로드 경로에 따른 `TABLE_CONFIG` 인스턴스 분리 문제 방어
- **대상 파일**: `server/database/crud.py`
- **문제 현상**:
  - 테스트 및 디렉토리 와처 기동 시 서로 다른 sys.path 검색 경로로 인해 `database.crud`와 `server.database.crud`가 독립된 모듈로 이중 임포트되어 전역 `TABLE_CONFIG` 딕셔너리가 메모리에서 분리되는 현상이 발생했습니다. 이로 인해 테스트 코드에서 런타임에 주입한 모의 테이블 메타데이터가 와처 데이터 가공 흐름에 도달하지 못해 컬럼 업데이트가 무시되는 버그가 확인되었습니다.
- **해결 방안**:
  - `models.DYNAMIC_TABLES`에 적용된 sys 공유 싱글톤 캐시 방식을 적용하여, `TABLE_CONFIG`를 `sys._table_config_singleton`으로 중앙화했습니다. 이로써 임포트 경로가 다르더라도 물리적으로 동일한 캐시 설정을 공유하도록 완벽하게 수정했습니다.

### 4. 단위 테스트(`test_composite_business_key.py`) 구축 및 백엔드 회귀 검증
- **신규 테스트**: `server/tests/test_composite_business_key.py`
  - 복합 키 설정을 모의로 선언하고, `pkg_id` 없이 `base`, `x`, `y` 컬럼값만 담긴 인제션 데이터가 자동으로 `base_x_y` 키(예: `CHIPA_1_2`)를 조립하여 SQLite 메모리 DB에 정상 적재 및 업서트되는지 검증하는 시나리오를 작성했습니다.
- **검증**:
  - `pytest server/tests -v` 테스트 스위트를 실행하여, 신규 시나리오를 포함한 **총 27개 백엔드 전체 테스트 케이스가 100% 정상 통과(100% Passed)**함을 확인했습니다.
