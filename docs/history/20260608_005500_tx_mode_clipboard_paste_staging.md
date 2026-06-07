# 변경 이력: Tx Mode 기본 활성화 및 클립보드 붙여넣기(Paste) 스테이징 적용

- **작성일**: 2026년 6월 8일
- **작성자**: Antigravity
- **상태**: 완료

## 1. 개요 및 목적
- **현상**: 
  1. Tx Mode(트랜잭션 편집 일괄 처리 모드) 상태에서 여러 셀을 복사한 뒤 붙여넣기(Paste)할 때, 즉각 서버 API로 데이터가 전송되면서 일괄 적용(Apply) 및 되돌리기(Discard) 정합성이 깨지고 행이 튀는 문제가 발생했었습니다.
  2. 사용자의 일괄 편집 편의성을 극대화하기 위해 웹 클라이언트 로딩 시와 테이블 전환(Switch Table) 시 기본적으로 Tx Mode가 켜진 상태(Enabled by default)로 유지되어야 하는 요구사항이 존재했습니다.
- **해결 방안**:
  1. 클립보드 붙여넣기 핸들러(`setupClipboardHandlers()`) 내부에서 트랜잭션 모드 활성화 여부(`txModeActive === true`)를 판단하도록 인터셉트 흐름을 추가했습니다.
  2. 트랜잭션 모드가 활성화된 상태라면, 서버로의 전송을 차단하고 복사 대상 셀들의 오리지널 값(`oldValue` 및 `oldIsOverwrite`)을 `pendingTxEdits` 상태 맵에 `${rowId}_${col}` 키로 꼼꼼하게 기록하여 이후 'Discard' 기능이 정상 작동하도록 설계했습니다.
  3. 로컬 Ag-Grid 상에서만 셀 데이터가 업데이트되도록 `gridApi.applyTransaction`을 수행하되, 정렬 조건이 흔들리지 않도록 `updated_at` 값은 수정하지 않았습니다.
  4. 붙여넣기가 완료된 영역은 강제로 리프레시(`refreshCells({ force: true })`)하여 `.cell-dirty-tx`(점선 테두리) 스타일이 실시간으로 사용자에게 노출되도록 구현했습니다.
  5. 웹 클라이언트 진입 시 `txModeActive = true`를 기본값으로 갖도록 선언부를 수정하고, UI 체크박스(`tx-mode-toggle`)에 `checked` 속성을 추가하였습니다.
  6. 테이블을 변경하는 `switchTable` 함수가 호출될 때에도 Tx Mode가 강제로 풀리지 않고 `txModeActive = true` 및 체크박스 활성화 상태를 유지하도록 리셋 로직을 수정했습니다.

## 2. 세부 변경 사항

### `client2/index.html`
- `tx-mode-toggle` 체크박스 엘리먼트에 `checked` 속성을 추가하여 기본적으로 선택된 상태로 렌더링되게 했습니다.

### `client2/src/main.js`
- `txModeActive` 변수의 초기값을 `false`에서 `true`로 변경했습니다.
- `switchTable` 함수 내부의 대기 수정 초기화 영역에서 `txModeActive = true;` 및 `txModeToggle.checked = true;`를 대입하여 테이블을 이동하더라도 Tx Mode가 항상 기본 켜짐을 유지하도록 보장했습니다.
- `setupClipboardHandlers` 내 붙여넣기 파싱 루프 수정:
  - `txModeActive` 상태 분기를 생성했습니다.
  - 스테이징 대상이 되는 변경사항에 대해 기존 오리지널 데이터를 백업한 뒤, `pendingTxEdits`에 저장합니다.
  - 로컬 업데이트 배열(`localUpdates`)을 수집한 뒤 서버 전송 API를 타지 않고 그리드에만 로컬 트랜잭션을 적용한 뒤 `return` 합니다.
  - 붙여넣기 상태 변경 후 UI 컴포넌트(`updateTxModeUI`)를 호출하고 수정 유실 알림 경고(`setupBeforeUnloadWarning()`)를 동작시킵니다.

## 3. 검증 결과
- **효과**:
  - 웹 페이지를 새로고침하거나 새로운 테이블을 선택해도 최상단 툴바의 Tx Mode가 활성화 상태(체크 상태)를 유지합니다.
  - 이 상태에서 임의의 단건 수정 및 복사-붙여넣기 진행 시 즉각 서버 통신 없이 로컬 점선 테두리(`.cell-dirty-tx`) 스타일로 스테이징되며 행의 튐 없이 부드럽게 정렬이 고정됩니다.
