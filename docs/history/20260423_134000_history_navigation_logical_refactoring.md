# 📜 Technical History: History Navigation Logical Refactoring

**날짜**: 2026-04-23
**작성자**: Agent Q (Lead PM Oversight)

## 1. 문제 현상 (Phenomenon)
- `HistoryDockPanel`에서 로그 항목 클릭 시, 해당 로그가 생성될 당시의 `table_view` 객체 참조를 사용하여 내비게이션을 수행함.
- **부작용**: 사용자가 테이블 탭을 닫았다가 다시 열거나, 시스템에 의해 탭이 갱신될 경우 기존 객체 참조가 무효화되어 `RuntimeError` 또는 내비게이션 실패가 발생함.
- **기타**: `panel_history.py` 내부에 개발 중 잔존한 `index.isValid()` 등 미정의 변수 참조 코드가 포함되어 시스템 불안정성을 유발함.

## 2. 기술적 원인 분석 (Root Cause)
- **객체 생명주기 불일치**: UI 객체(`QTableView`)의 생명주기와 영구적인 히스토리 로그의 생명주기가 직접 결합되어 발생한 'Strong Coupling' 문제.
- **병합 아티팩트**: 최근의 히스토리 중앙화 작업 중 디버깅 코드가 삭제되지 않고 릴리스됨.

## 3. 해결 방안 (Solution)
- **논리 주소 지정(Logical Addressing)**: 히스토리 아이템에 UI 객체 대신 `table_name`, `row_id`, `col_name` 문자열을 저장하도록 구조 변경.
- **Dynamic Resolver 도입**: 
    - 클릭 시점에 `MainWindow`를 통해 현재 활성화된 탭 스택에서 해당 `table_name`을 가진 위젯을 검색.
    - 위젯 내의 `ExcelTableView`를 `findChild`로 해제하여 객체의 최신 인스턴스를 확보.
- **정밀 포커싱**: 행 단위 이동에서 `col_name` 정보를 활용한 셀 단위 커서 정밀 타겟팅 지원.

## 4. 코드 변경 핵심 요약
- `client/ui/panel_history.py`:
    - `log_event()`, `_handle_local_data_changed()`: `_item_meta`에 논리 정보 저장.
    - `_on_item_clicked()`: `MainWindow`와 연동하여 탭 전환 및 테이블 객체 동적 탐색 로직 구현.
- `client/main.py`:
    - `_dispatch_ws_message()`: 호출 시 불필요한 `table_view` 계산 로직 제거 및 인터페이스 간소화.

## 5. 검증 결과 (Validation)
- 탭 종료 후 히스토리 클릭 시 탭 재오픈 및 정확한 셀 위치로의 스크롤 작동 확인.
- `assy_manager` 콘다 환경에서의 무결성 테스트 통과.

---
*AssyManager Technical History | Phase 1-1*
