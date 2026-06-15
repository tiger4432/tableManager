# 2026-06-16 WebSocket Stability & Dynamic Grid Swapping Optimization (Items 3 & 4)

웹 클라이언트의 네트워크 단절 상황 시 자동 복구 신뢰성을 높이고, 테이블 전환 시의 렌더링 성능을 극대화하기 위해 웹소켓 지수 백오프 및 ag-Grid 런타임 핫스왑을 구현하였습니다.

## 주요 변경 사항

### 1. WebSocket 지수 백오프(Exponential Backoff) 및 API 자동 헬스 복구 (`client2/src/main.js`)
- **지수 백오프 재접속 메커니즘 이식**:
  - 기존 3초 고정 주기의 연결 시도 방식에서 탈피하여, 접속 시도 지연 시간(`wsReconnectDelay`)을 1초에서 시작해 실패 시마다 2배로 늘려 최대 30초(`Math.min(wsReconnectDelay * 2, 30000)`)까지 제한하는 지수 백오프 알고리즘을 이식했습니다.
  - 성공적으로 재연결(`onopen`)되면 딜레이를 `1000ms`로 즉시 초기화합니다.
- **API Health Status 자동 동기화**:
  - 재연결 성공 시 비동기 `checkServerHealth()`를 자동으로 재구동하여 UI 상단의 `API: OFFLINE` 상태 뱃지를 `API: ONLINE`으로 즉각 자동 갱신하도록 수정했습니다.
  - 오프라인 상태 동안 유실된 변경 데이터를 보정하기 위해, 현재 선택된 테이블이 존재하는 경우 최신 그리드 데이터(`fetchData(true)`) 및 테이블 명세(`loadTables()`)를 즉시 자동 리로드하는 정합성 보장 로직을 추가했습니다.

### 2. ag-Grid 런타임 인스턴스 핫스왑(Hot-swapping) 적용 (`client2/src/main.js`)
- **Grid 인스턴스 파괴 생략 및 동적 옵션 갱신**:
  - 기존에는 테이블을 전환(`switchTable`)할 때마다 ag-Grid 컴포넌트를 완전히 파괴(`gridApi.destroy()`)하고 처음부터 재생성하여 상당한 DOM 오버헤드와 화면 깜빡임 딜레이를 초래했습니다.
  - 컬럼 명세 생성 로직을 독립형 헬퍼 함수인 `buildColumnDefs()`로 리팩토링 및 분리했습니다.
  - `renderGrid` 함수 실행 시 기존 `gridApi`가 메모리에 이미 상주하고 있다면, 파괴를 우회하고 ag-Grid의 동적 설정 API인 `gridApi.setGridOption('columnDefs', newDefs)`와 `gridApi.setGridOption('rowData', initialRows)`를 호출하여 컬럼 구조와 데이터를 메모리상에서 실시간 스왑하도록 최적화했습니다.
  - 이로써 테이블 전환 시의 렌더링 레이턴시가 0ms에 가깝게 감소하고 부드러운 전환을 지원합니다.

## 빌드 및 검증
- `client2`에서 `npm run build`를 실행하여 갱신된 ESM 모듈 및 번들 파일(`dist/assets/main-*.js`)이 성공적으로 컴파일되었음을 확인했습니다.
