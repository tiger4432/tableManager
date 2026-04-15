# 20260415_resolve_lazy_model_ghosting

## 1. 이슈 개요 (Issue Overview)
`ApiLazyTableModel`에서 행 붙여넣기(Paste) 및 실시간 동기화 시 발생하는 두 가지 형태의 데이터 정합성 오류를 수정하였습니다.

### 1.1 고스트 행 (Ghost Rows)
- **증상**: 특정 행을 수정하면 최상단으로 부상(Floating)하지만, 스크롤을 내리면 원래 위치에 동일한 행이 중복되어 위아래로 2개 표시됨.
- **원인**: WebSocket에 의해 최상단에 추가된 행이, 이후 `fetchMore`가 서버에서 청크를 가져올 때 중복 제거 없이 다시 추가(`extend`)되어 발생.

### 1.2 고스트 밸류 (Ghost Values)
- **증상**: 행이 부상한 후에도, 이전 위치(Row Index)의 셀들에 붙여넣은 값이 그대로 남아있음.
- **원인**: 
  - 배치 업데이트 완료 후 호출되는 로컬 핸들러(`_on_batch_update_finished`)가 요청 시점의 `row_index`를 기준으로 데이터를 덮어씀.
  - 그러나 이미 WebSocket에 의해 행이 이동하여 인덱스가 밀려난 상태이므로, 엉뚱한 행(Stale Index)에 값이 쓰여 잔상이 남게 됨.

## 2. 해결 방안 (Solution Details)

### 2.1 통합 중복 관리 (Strict Deduplication)
- **Fetch 가드**: `_on_fetch_finished`에서 서버 데이터를 캐시에 합치기 전, `row_id` 기반으로 이미 로컬에 부상해 있는 행은 전수 제외 처리함.
- **WebSocket 가드**: WebSocket 수신 시에도 `row_id` 맵을 맹신하지 않고, 삽입 전 선제적으로 기존 ID를 찾아 삭제(Pop)하여 ID 유일성을 보장함.

### 2.2 동기화 권한 일원화 (Centralized Synchronization)
- **로컬 갱신 중단**: `_on_batch_update_finished`에서의 인덱스 기반 수동 데이터 갱신을 제거함.
- **WebSocket 권한**: 모든 데이터 값과 행의 위치 이동은 오직 서버의 공인된 상태를 대변하는 WebSocket 브로드캐스트를 통해서만 처리하도록 변경하여 경합 현상(Race Condition)을 원천 차단함.

### 2.3 데이터 구조 정규화 (Normalization)
- WebSocket 수신 시 시스템 컬럼(`created_at` 등)이 누락되거나 구조가 달라지는 문제를 해결하기 위해 `_normalize_row_data` 헬퍼를 도입하여 페칭 데이터와 구조를 통일함.

## 3. 결론 (Conclusion)
이제 `ApiLazyTableModel`은 비동기 환경에서도 데이터의 정체성(Identity)을 안정적으로 유지하며, 위치 이동과 값 갱신이 원자적으로 이루어집니다.
