# Job Report: History Navigation Refactoring (Agent Q)

**에이전트**: Agent Q (Integrity & QA Expert)
**날짜**: 2026-04-23
**상태**: 완료

## 1. 작업 개요
- `client/ui/panel_history.py`에서 `table_view` 객체를 직접 관리하던 방식을 폐기하고, `table_name`, `row_id`, `col_name` 기반의 논리 주소 지정 방식으로 리팩토링하였습니다.
- 이를 통해 탭 종료 및 재생성 시 발생할 수 있는 메모리 참조 오류를 원천 차단하고 내비게이션 신뢰성을 높였습니다.

## 2. 세부 수행 내역

### [Refactor] 히스토리 데이터 구조 및 로깅 로직
- `HistoryDockPanel._item_meta` 구조 변경: `id(item) -> {table_name, row_id, col_name}`.
- `log_event(data)`: 매개변수에서 `table_view`, `nav_id` 제거. 수신된 데이터 딕셔너리에서 정보를 추출하여 저장.
- `_handle_local_data_changed`: 로컬 수정 시에도 논리 주소 정보를 저장하도록 수정.

### [Fix] 내비게이션 및 포커싱 로직 (`_on_item_clicked`)
- 클릭 시 `MainWindow` 인스턴스를 통해 해당 `table_name`에 대응하는 탭(`nav_id`)으로 먼저 이동합니다.
- `findChild(ExcelTableView)`를 사용하여 현재 활성화된 화면의 테이블 뷰 객체를 동적으로 찾습니다.
- `source_model`의 `idx_map`을 활용하여 `row_id`의 현재 인덱스를 조회하고, `col_name`을 기반으로 정확한 셀에 커서를 위치시킵니다.
- **결과**: 탭이 닫혀있는 상태에서 히스토리를 클릭해도 해당 테이블이 열리면서 정확한 위치로 스크롤됩니다.

### [Cleanup] 가비지 코드 제거
- `panel_history.py` 150라인 부근에 잔존하던 선언되지 않은 변수 참조(`index.isValid()`) 등 오타 및 복사 아티팩트를 전수 제거하였습니다.

## 3. 관련 파일 리스트
- [Modified] `client/ui/panel_history.py`
- [Modified] `client/main.py`

## 4. 검증 결과
- `assy_manager` 환경에서 `jurigged`를 통한 실시간 코드 반영 확인.
- 탭 닫기 -> 히스토리 클릭 시 탭 재오픈 및 데이터 포커싱 정상 작동 확인.
- `AttributeError` 및 `NameError` 발생 지점 원천 봉쇄 완료.

---
본 보고서는 `agent_workspace/tasks/Agent_Q_Audit_Integrity_v1.md` 지침에 따라 작성되었습니다.
