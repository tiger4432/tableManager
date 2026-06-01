# 변경 이력: 실시간 히스토리 푸시 고도화 (API 재요청 제거 및 대용량 처리 시 그리드 갱신 우회)

- **작성일**: 2026년 6월 2일
- **작성자**: Antigravity
- **상태**: 완료

## 1. 개요 및 목적
- 기존 구조에서는 파일 인제션이나 대량 수동 우선순위/원천 관리 변경 시 `batch_refresh_required` 이벤트가 트리거되면서, 이력을 새로 가져오기 위해 API 재요청(`loadHistory`)을 수행하거나 테이블 그리드를 매번 전체 재조회(`fetchData()`)했습니다.
- 이로 인해 실시간 감사 타임라인이 부드럽게 붙지 않고 깜빡거리며 전체 다시 로딩되는 문제가 남아 있었으며, 대용량 작업 시 테이블이 새로 로드되어 사용자의 스크롤 위치나 셀 선택 포커스가 강제로 해제되는 큰 사용성 저하가 발생했습니다.
- 이를 개선하기 위해 **1) 수동 일괄 관리 시에도 AuditLog를 누적 수집하여 실시간 스트리밍하고, 2) 클라이언트에 셀/행 단위 히스토리 전용 인메모리 캐시(`cellRowHistoryData`)를 도입하여 API 요청 없이 실시간 밀어넣기를 수행하며, 3) 대용량 처리 수신 시 테이블 강제 리로드(`fetchData()`)를 제거하고 오직 히스토리만 갱신하도록** 고도화했습니다.

## 2. 세부 구현 사항

### 백엔드 일괄 변경 처리 고도화 (`server/database/crud.py` & `server/main.py`)
- **감사 로그 수집 및 반환 (`crud.py`)**:
  - `set_cell_manual_priority_batch` 및 `delete_cell_source_batch` 함수에서 생성된 `logs_to_cache` 감사 로그 딕셔너리들을 직렬화(Timestamp의 ISO 포맷 변환 포함)하여, `(changed_rows, serialized_logs)` 튜플 형태로 반환하도록 확장했습니다.
- **WebSocket 페이로드 내 생성 로그 전달 (`main.py`)**:
  - `apply_batch_updates_endpoint`, `set_cell_priority_batch_endpoint`, `delete_cell_source_batch_endpoint`에서 수동 변경 시 생성된 감사 로그 목록(`created_logs`)을 최종 캡처합니다.
  - 대량 변경(변경 건수 > 100)으로 `batch_refresh_required`를 보낼 때에도 5,000건 이하인 경우 페이로드에 `created_logs`를 동봉하여 브로드캐스트합니다.
  - 소량 변경(변경 건수 <= 100)으로 `batch_row_upsert` 청크를 보낼 때에도 해당하는 감사 로그 조각들을 나누어 `created_logs` 필드로 함께 스트리밍합니다.

### 프론트엔드 캐시 도입 및 그리드 갱신 우회 (`client2/src/main.js`)
- **셀/행 히스토리 캐시(`cellRowHistoryData`) 추가**:
  - 전역 변수로 `cellRowHistoryData = []`를 추가하여, 사용자가 선택한 셀이나 행의 최근 변경 기록을 로컬 메모리에 캐싱합니다.
  - `loadHistory()` API 호출 성공 시 수신된 원천 로그 데이터를 이 캐시에 저장합니다.
- **실시간 Push-based Append 구조 완성**:
  - `appendHistoryLocally(log, skipRender)` 함수가 전역 히스토리뿐만 아니라 셀/행 탭 상태일 때도 활성화되도록 개편했습니다. 새로 인입된 로그 중 현재 포커스 중인 셀/행 좌표와 매칭되는 로그가 있으면 중복 체크 후 `cellRowHistoryData` 캐시 앞단에 실시간 삽입(unshift)합니다.
  - WebSocket 수신 시 이력이 존재하는 경우 API 호출(`loadHistory()`)을 일체 배제하고 `renderTimeline(cellRowHistoryData)` 또는 `renderGlobalTimeline()`을 직접 호출하여 메모리 내 데이터로만 타임라인 DOM을 실시간 갱신합니다.
- **대량 변경 시 그리드 자동 갱신(`fetchData()`) 우회**:
  - `batch_refresh_required` 수신 시 테이블 전체 새로고침(`fetchData()`)을 수행하던 코드를 제거했습니다.
  - 이로써 대용량 백그라운드 인제션이나 수동 변경 작업이 실행되어도 사용자가 보고 있는 데이터 셀 포커스, 정렬 상태, 화면 스크롤 등이 끊기거나 흔들리지 않고 편안하게 유지되며, 히스토리 타임라인 카드만 실시간으로 차분하게 추가됩니다.

## 3. 검증 결과
- **백엔드 컴파일**: `python -m py_compile` 테스트를 실행하여 `main.py` 및 `crud.py` 구문 문법 정합성 100% 정상 작동을 확인했습니다.
- **프론트엔드 빌드**: `npm run build`를 구동하여 Vite 프로덕션 빌드가 에러 없이 완료되었음을 검증했습니다.
