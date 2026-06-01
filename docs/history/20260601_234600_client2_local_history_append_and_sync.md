# 변경 이력: 셀 수정 시 히스토리 패널 API 전체 재조회 제거 및 로컬 즉각 추가(Prepend) 최적화

- **작성일**: 2026년 6월 1일
- **작성자**: Antigravity
- **상태**: 완료

## 1. 개요 및 목적
- 우측 Audit History 패널 UI에서 셀 값 변경, 셀 일괄 비우기, 또는 WebSocket 실시간 수신 등이 발생할 때마다 매번 서버로부터 전체 이력 목록을 통째로 다시 로드하는 API 호출(`triggerHistoryReloadDebounced`)이 발생했습니다.
- 이로 인해 불필요한 네트워크 트래픽 낭비와 서버 오버헤드가 발생했고, UI 측면에서는 이력 카드 리스트가 번쩍이며 깜빡이고 스크롤 위치가 최상단으로 강제 초기화되어 사용자 경험(UX)을 저해했습니다.
- 이를 해결하기 위해 API 변경 완료 시점에 변경 사항 데이터를 로컬에서 즉시 조립하여 타임라인 DOM의 최상단에 바로 꼽아 넣는(Prepend) 최적화를 구현하고, 필요한 경우에만 명시적으로 서버 이력을 불러올 수 있도록 수동 동기화("Sync") 버튼을 제공합니다.

## 2. 세부 구현 사항

### 프론트엔드 (`client2/index.html` & `client2/src/main.js`)
- **로컬 이력 추가 헬퍼 구현 (`appendHistoryLocally`)**:
  - [client2/src/main.js](file:///c:/Users/kk980/Developments/assyManager/client2/src/main.js#L1870)에 신규 헬퍼 함수를 구축했습니다.
  - 현재 보고 있는 활성 이력 탭(`Cell`, `Row`, `Global` History) 상태 및 포커스된 셀/행 ID를 검사하여 매칭되는 영역의 타임라인 최상단에 새로운 이력 카드를 즉시 삽입(`insertBefore`)합니다.
- **셀 수정/비우기 연동 최적화**:
  - **단일 셀 수정 (`handleCellEdit`)**: 서버 성공 시 API 전체 리로드 트리거를 끄고, 대신 `appendHistoryLocally(rowId, colId, oldValue, finalValue, ...)`를 직접 수행합니다.
  - **다중 셀 비우기 (`clearSelectedCells`)**: 루프가 돌며 로컬 그리드 값을 비우기 직전에 변경 전의 이전 값들을 `oldValuesBackup` 임시 배열에 백업하고, 서버 배치 응답을 수신한 뒤 루프를 순회하며 `appendHistoryLocally`를 일괄 실행하여 로컬 타임라인을 갱신합니다.
- **WebSocket 실시간 동기화 연동**:
  - 타 유저 또는 파서에 의해 들어오는 WS 델타 데이터(`batch_row_upsert`) 수신 시, 내가 현재 열어 보고 있는 관심 셀/행의 컬럼이 수정되었다면 로컬 이력 타임라인에 타 유저가 수정한 이력 사항 카드를 즉시 추가하도록 매핑했습니다.
- **수동 🔄 Sync 버튼 도입**:
  - [client2/index.html](file:///c:/Users/kk980/Developments/assyManager/client2/index.html#L101) Audit History 헤더 타이틀 우측에 깔끔한 유리막 미니 버튼형태의 `Sync` 버튼을 탑재했습니다.
  - `main.js`의 `setupEventListeners` 내부에서 버튼 클릭 시 명시적으로 `loadHistory()`를 직접 타도록 매핑하여 수동 강제 동기화 수단을 지원합니다.

## 3. 검증 결과
- **UI 반응성 향상**: 셀 값을 수정하거나 `Delete` 키로 다량의 셀을 날렸을 때, 우측 이력 패널이 통째로 갱신("Loading...")되면서 깜빡이거나 스크롤이 흔들리지 않고 변경 카드가 최상단에 자연스럽게 노출됨을 확인했습니다.
- **네트워크 대역폭 절감**: 값 변경 작업 발생 시 더 이상 이력 API 서버 요청이 발생하지 않고 로컬 연산으로 처리되며, 우측 상단 `🔄 Sync` 버튼 클릭 시에만 서버로부터 최신 DB 감사 로그를 안전하게 받아와 원본 정합성을 복구함을 검증 완료했습니다.
