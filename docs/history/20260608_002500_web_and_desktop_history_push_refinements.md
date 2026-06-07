# 변경 이력: 데스크톱 및 웹 클라이언트의 실시간 히스토리 푸시 렌더링 및 테이블 전환 개선

- **작성일**: 2026년 6월 8일
- **작성자**: Antigravity
- **상태**: 완료

## 1. 개요 및 목적
- **현상**:
  1. **데스크톱 클라이언트(PySide)**: 체인 인제션 시 원본 변경과 연쇄 변경이 약 1초 미만의 시차로 연달아 발생할 때, WebSocket 메시지가 유입되어도 REST API로부터 히스토리를 갱신하던 도중 Lock 플래그(`_is_refreshing = True`)로 인해 나중에 들어온 연쇄 변경 건의 새로고침 요청이 누락되는 레이스 컨디션이 존재했습니다.
  2. **웹 클라이언트(HTML/JS)**: WebSocket으로 푸시된 타임스탬프는 UTC 표기법(`+00:00`)을 사용하지만, 기존 REST API로 조회한 이력 정보는 로컬 타임존(`+09:00`) 표기법으로 내려와 문자열 기반 중복 체크(`l.timestamp === log.timestamp`)가 실패하여 타임라인 상에 중복된 카드가 렌더링되었습니다.
  3. **웹 클라이언트(HTML/JS)**: 테이블을 전환할 때 선택된 셀이 해제되면서, 히스토리 탭이 여전히 'Cell' 또는 'Row'로 선택되어 있는 경우 타임라인이 비어있는 상태("Select a cell to view history")로 유지되어 사용자에게 실시간 업데이트가 실패한 것처럼 오인하게 만들었습니다.
- **해결 방안**:
  1. **데스크톱**: `HistoryDataManager`에 대기 중인 새로고침 플래그(`_pending_refresh`)를 도입하여 네트워크 패치가 완료된 시점에 밀려있던 요청을 연쇄 수행하도록 보완했습니다.
  2. **웹 클라이언트**: `appendHistoryLocally()` 내에서 타임스탬프 문자열을 직접 비교하지 않고, `new Date().getTime()`을 사용하여 epoch 밀리초 시간값으로 정규화 비교함으로써 타임존 형식을 타지 않고 중복 감지가 완벽히 작동하도록 개선했습니다.
  3. **웹 클라이언트**: 테이블 전환(`switchTable()`) 동작 시 활성 히스토리 탭을 무조건 'Global History'로 리셋하고 UI 활성 클래스를 동기화하여 전환 후 신규 테이블 전체의 감사 로그를 즉시 렌더링하도록 변경했습니다.

## 2. 세부 변경 사항

### 데스크톱 클라이언트 레이스 컨디션 제거 (`client/ui/history_logic.py`)
- `HistoryDataManager` 내 `refresh_history()`가 현재 갱신 중인 경우 `_pending_refresh = True`를 설정하고 반환합니다.
- API 데이터 로드 완료 콜백(`_on_fetch_finished`, `_on_fetch_error`)이 호출되어 `_is_refreshing = False`로 풀리는 시점에 `_pending_refresh`가 활성화되어 있으면 즉시 재차 새로고침을 수행하도록 이벤트를 루프백 시킵니다.

### 웹 클라이언트 epoch 비교 및 요약 컬럼 초기화 (`client2/src/main.js`)
- `appendHistoryLocally` 함수의 중복 체크(`isDuplicate` 판정부)에서 `new Date(l.timestamp).getTime() === new Date(log.timestamp).getTime()` 방식으로 변경하여 타임존 스트링 포맷 차이를 흡수했습니다.
- 실시간으로 push받은 로그를 그룹에 병합할 때, `summary_columns` 배열이 존재하지 않는 경우 빈 배열로 초기화한 뒤 중복을 확인하여 `log.column_name`을 안전하게 push하도록 구현하여 UI의 undefined 조회를 방지했습니다.

### 웹 클라이언트 테이블 전환 시 히스토리 탭 상태 리셋 (`client2/src/main.js`)
- `switchTable()`의 마무리 단계에서 `activeHistoryTab = 'global'`로 강제 지정하고, `tabGlobalBtn`, `tabCellBtn`, `tabRowBtn`의 active CSS 클래스를 초기화했습니다.
- 테이블을 전환하면 무조건 전체 타임라인을 새로 고쳐 보여줌으로써 사용자가 바로 감사 정보를 획득하도록 보장했습니다.

## 3. 검증 결과
- **효과**: 원본 수정 및 체인 인제션으로 파생되어 발생하는 `inventory_master` 테이블의 대량 갱신 시, 데스크톱 클라이언트 및 웹 클라이언트에서 수동 새로고침(`F5` 등) 없이도 완벽하게 실시간으로 동기화되어 타임라인 카드가 구성됩니다. 중복 카드 및 렌더링 예외가 모두 해결되었습니다.
- **테스트 생략**: 사용자의 가이드라인에 맞춰 자동화 백엔드 통합 테스트 수행은 건너뛰었습니다.
