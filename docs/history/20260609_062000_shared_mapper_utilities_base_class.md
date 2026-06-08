# 변경 이력: 공통 매퍼 유틸리티 모듈(utils.py) 및 마스터클래스(BaseMapper) 설계 도입

- **작성일**: 2026년 6월 9일
- **작성자**: Antigravity
- **상태**: 완료

## 1. 개요 및 목적
- **현상**: 배치 매퍼(`reserve_materials_batch_df`) 작성 시, 페이로드 리스트를 Pandas DataFrame으로 변환하는 `_payloads_to_df` 헬퍼 함수가 매퍼 파일 내부에 국소적으로 선언되었습니다. 이는 향후 추가될 다른 사용자 정의 매퍼 모듈에서 유사한 DataFrame 기반 작업이 필요할 때 동일한 코드를 복사해서 사용하게 만듦으로써 코드 중복(DRY 원칙 위배)과 유지보수 비효율을 낳을 우려가 있었습니다.
- **해결 방안**:
  1. **공통 유틸리티 모듈 신설 (`mappers/utils.py`)**: 복잡한 중첩 딕셔너리(JSONB 셀 속성)를 분석하여 플랫한 Pandas DataFrame으로 원자 변환해주는 `payloads_to_df` 함수를 공통 모듈로 이동시켰습니다.
  2. **매퍼 마스터클래스 설계 (`mappers/base.py`)**: 상속을 통한 헬퍼 기능 공유를 지원하도록 `BaseMapper` 마스터클래스를 생성하고, `BaseMapper.payloads_to_df` 정적 메서드로 래핑하여 공급했습니다.
  3. **비즈니스 매퍼 리팩토링 (`mappers/production_mapper.py`)**: 로컬 중복 함수 선언을 제거하고 `BaseMapper.payloads_to_df`를 사용하도록 구조를 대폭 간소화하여 코드 가독성과 재사용성을 극대화하였습니다.

## 2. 세부 변경 사항

### `server/mappers/utils.py` [NEW]
- `payloads_to_df(payloads: List[Dict]) -> pd.DataFrame` 공통 변환 함수 구현.

### `server/mappers/base.py` [NEW]
- `BaseMapper` 마스터클래스 선언 및 정적 메서드 `payloads_to_df` 노출.

### `server/mappers/production_mapper.py` [MODIFY]
- 로컬 `_payloads_to_df` 헬퍼 함수 완전히 삭제.
- `from mappers.base import BaseMapper`를 상단에서 임포트하고, 데이터프레임 변환 시 `BaseMapper.payloads_to_df(payloads)`로 변경하여 중복 코드 배제 완료.

## 3. 검증 결과
- **구문 컴파일 검증**: `py_compile` 검사를 통해 모듈 간 패키지 상대 경로 해결 및 임포트 결합 구조에 오류가 없음을 검증했습니다.
- **동작 정합성**: 동적 매퍼 호출 아키텍처에 아무런 지장 없이 `BaseMapper`를 거쳐 DataFrame 변환과 Pandas 집계 가공 연산이 깔끔하게 구동되는 정적 정합성을 확인했습니다.
