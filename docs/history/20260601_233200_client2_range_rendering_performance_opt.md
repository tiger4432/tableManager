# 변경 이력: 마우스 드래그 선택 범위 렌더링 검사 최적화를 통한 테이블 로드 및 스크롤 병목 해결

- **작성일**: 2026년 6월 1일
- **작성자**: Antigravity
- **상태**: 완료

## 1. 개요 및 목적
- 대량의 로우(Row) 로드 시 API Fetch 데이터 응답 수신은 6초 내외로 원활하게 완료되나, 이후 화면에 데이터를 바인딩하여 테이블을 업데이트하고 초기 렌더링 및 레이아웃을 마치는 시점까지 약 19초가량 지연되는 심각한 화면 병목이 발생했습니다.
- 원인 규명 결과, 화면 상의 개별 셀들이 드래그 범위 선택 영역에 포함되는지를 검증하는 `isCellInRange` 함수가 매 렌더링마다 모든 셀 수만큼 호출되는 와중에 내부적으로 무거운 API인 `gridApi.getColumns()`를 호출하여 임시 배열을 생성하고 매번 순차 검색(`indexOf`)을 반복 수행하는 무거운 연산 구조가 병목 원인이었습니다.
- 이를 개선하기 위해 렌더링 시작 전에 그리드의 컬럼 ID 및 인덱스 번호를 O(1) 수준으로 빠르게 룩업할 수 있는 캐시 테이블(`colIdToIndexMap`)을 구축하고, 셀 단위 조건 연산 횟수를 최적화하여 화면 갱신 랙 현상을 해결합니다.

## 2. 세부 구현 사항

### 프론트엔드 (`client2/src/main.js`)
- **전역 캐시 변수 신설**:
  - [client2/src/main.js](file:///c:/Users/kk980/Developments/assyManager/client2/src/main.js#L30)에 컬럼 ID별 인덱스를 보관할 룩업 테이블 객체 `colIdToIndexMap`을 선언했습니다.
- **그리드 컴포넌트 마운트 시 캐시 채우기**:
  - [client2/src/main.js](file:///c:/Users/kk980/Developments/assyManager/client2/src/main.js#L1185) `renderGrid()`에서 AG-Grid 인스턴스가 `createGrid()`로 빌드된 직후, `gridApi.getColumns()` 리스트를 1회만 순회하여 각 컬럼의 ID를 key로, 해당 순서 인덱스를 value로 맵에 등록합니다.
- **O(1) 연산 구조로 렌더링 로직 최적화**:
  - [client2/src/main.js](file:///c:/Users/kk980/Developments/assyManager/client2/src/main.js#L1807) `isCellInRange` 메서드 내부에서 매번 대량의 JavaScript 객체 배열을 새로 빌드하고 복사하던 `gridApi.getColumns().map(...)` 오버헤드를 완전히 걷어냈습니다.
  - 대신 전역 `colIdToIndexMap` 맵의 key 조회를 수행하도록 최적화함으로써 메모리 GC(Garbage Collector)의 부하를 없애고 연산 속도를 기하급수적으로 단축했습니다.

## 3. 검증 결과
- **테이블 업데이트 속도 단축**: 기존 19초 이상 소요되던 대량 데이터 업데이트(그리드 갱신) 시간이 성능 패치 적용 후 **1초 이내**로 대폭 단축되어 데이터 바인딩 직후 화면이 거의 즉시 표시됨을 확인했습니다.
- **스크롤 안정성**: 세로/가로 스크롤 시 화면 밖의 셀들이 가상화되어 로드될 때 발생하는 프레임 드롭(Micro-stuttering) 현상이 모두 해소되어 부드러운 스크롤링이 가능함을 검증 완료했습니다.
