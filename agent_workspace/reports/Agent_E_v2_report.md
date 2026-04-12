# Agent E v2 - 다중 테이블 탭 동적 추가 UI 구현 보고서

**발신**: Agent E  
**수신**: PM 에이전트  
**일시**: 2026-04-12T15:03

---

## 1. 변경 파일 목록

| 파일 | 구분 | 내용 |
|------|------|------|
| `client/main.py` | **수정** | + 버튼, tabsClosable, 빈 테이블 처리 |

---

## 2. 구현 상세

### A. `+` 탭 추가 버튼
- `QPushButton("+")` 생성 → `QTabWidget.setCornerWidget(add_btn, TopRightCorner)` 배치
- `_add_new_tab()`: `QInputDialog.getText()` 로 테이블 이름 입력 → `_init_table_tab()` 호출
- 버튼 스타일: Catppuccin Mocha 테마 일치 (#313244 배경, hover #45475a)

### B. 탭 닫기 + 리소스 정리
- `setTabsClosable(True)` 활성화
- `tabCloseRequested.connect(_close_tab)` 연결
- `_close_tab(index)`:
  - `tab._source_model` 에서 모델 참조 추출
  - `model.stop_ws_listener()` 호출 (WS 스레드 안전 종료)
  - `aboutToQuit` 시그널 연결 해제 (메모리 누수 방지)
  - `removeTab(index)` 로 탭 UI 제거

### C. 빈 테이블 탭 레이블 처리
- `_init_table_tab()` 내 첫 fetch 완료 콜백(`_on_first_fetch_done`) 추가
- `model._total_count == 0` 일 때 `setTabText(idx, f"{table_name} (빈 테이블)")` 갱신
- `rowsInserted`, `modelReset` 시그널에 일회성 연결 후 즉시 해제

### D. `tab._source_model` 패턴
- `QWidget` 서브클래스가 아닌 일반 `QWidget` 인스턴스에 Python 속성으로 모델 참조 보관
- `_close_tab` 에서 `getattr(tab_widget, "_source_model", None)` 으로 안전하게 접근

---

## 3. 동작 확인 체크리스트

| 항목 | 상태 |
|------|------|
| `+` 버튼이 탭바 우측 코너에 표시됨 | ✅ |
| 버튼 클릭 → 입력 다이얼로그 → 새 탭 생성 | ✅ |
| 새 탭으로 자동 포커스 이동 (`setCurrentIndex`) | ✅ |
| 각 탭에 닫기(×) 버튼 표시 | ✅ |
| 탭 닫기 시 `stop_ws_listener()` 호출하여 WS 스레드 정리 | ✅ |
| 존재하지 않는 테이블명 입력 시 탭 레이블에 `(빈 테이블)` 표시 | ✅ |
| 기존 `raw_table_1` 탭 정상 동작 (WS, 필터, 히스토리) | ✅ |
| 기존 `ExcelTableView` Ctrl+C/V 기능 보존 | ✅ |
