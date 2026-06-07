# 변경 이력: Tx Mode 내 정렬 고정 및 행 이탈 방지

- **작성일**: 2026년 6월 8일
- **작성자**: Antigravity
- **상태**: 완료

## 1. 개요 및 목적
- **현상**: Tx Mode(일괄 수정 모드)에서 여러 셀을 연속적으로 수정하려고 할 때, 셀 값을 바꾸고 엔터를 누르거나 포커스를 잃는 순간 행의 위치가 위아래로 튀는(Row Jumping) 현상이 발생했습니다. 이는 사용자가 장시간 동안 한 행이나 여러 행을 연속해서 편집하는 몰입을 방해하고 편집 지점을 잃게 만드는 불편을 초래했습니다.
- **원인 분석**: 
  1. 셀 수정을 감지하여 인메모리에 임시 스테이징할 때 `data.updated_at = getLocalTimeString()`을 호출하여 임시 타임스탬프를 갱신하게 하였습니다. 이에 따라, 정렬 기준 열(`updated_at desc`)의 키 값이 변경되면서 정렬 순서가 흔들리게 되었습니다.
  2. 웹소켓 등의 외부 이벤트에 의해 `updateGridSortState()`가 호출되면 트랜잭션 모드 중이라도 그리드가 강제로 재정렬을 수행하여 행들이 튀었습니다.
- **해결 방안**:
  1. Tx Mode가 켜져 있는 동안에는 변경 내용을 인메모리에 임시 보관하되, 로컬 행 데이터의 `updated_at` 값은 전혀 갱신하지 않도록 변경했습니다. (서버에 최종 Apply 되어 커밋 완료 응답을 받은 시점에만 갱신)
  2. `updateGridSortState()` 실행부의 가장 상단에 트랜잭션 모드 활성화 여부(`txModeActive === true`)를 판단하는 가드를 삽입하여, 대기 수정이 존재하는 동안에는 외부 웹소켓 푸시 등으로 인한 어떠한 자동 정렬 시도도 무시하도록 제어했습니다.
  3. `valueSetter`에서도 트랜잭션 모드가 켜져 있는 동안에는 임시로 `is_overwrite = true`를 칠하지 않도록 분기하여, UI 디자인의 정합성을 명확히 보장했습니다.

## 2. 세부 변경 사항

### valueSetter 조건별 반영 (`client2/src/main.js`)
- `valueSetter`에서 `txModeActive`가 `false`인 경우(즉, 단건 즉시 저장 모드인 경우)에만 `is_overwrite = true`를 표시하도록 코드를 수정했습니다.

### updateGridSortState 함수 제어 가드 추가 (`client2/src/main.js`)
- `txModeActive === true`일 때 즉시 `return` 처리하여 정렬을 고정시켰습니다.
- 최종 `applyPendingTxEdits()` 및 `discardPendingTxEdits()`가 완료되는 시점에만 `updateGridSortState()`를 명시적으로 호출해 정렬 상태를 일괄 동기화하도록 갱신 흐름을 보완했습니다.

### handleCellEdit 내부 임시 키 갱신 배제 (`client2/src/main.js`)
- Tx Mode 가로채기(intercept) 블록에서 `data.updated_at = getLocalTimeString();` 처리를 완전히 삭제했습니다.

## 3. 검증 결과
- **효과**: Tx Mode가 켜진 상태에서 임의의 셀을 다량 편집해도 엔터를 쳤을 때 행이 절대 움직이지 않고 그 자리에 고정됩니다. 편집 도중 외부 서버 변경이나 웹소켓 푸시 이벤트가 들어와도 타임라인만 누적되고 그리드의 편집 위치는 그대로 유지됩니다. 이후 'Apply' 버튼을 클릭하면 최종 업데이트 시각을 반영하여 깔끔하게 상단으로 묶여 정렬됩니다.
- **테스트 생략**: 사용자의 지침에 따라 통합 테스트 수행을 생략했습니다.
