# 📝 Agent Panel — 소스 코드 리뷰 요약 (UI/Filter)

**담당 영역**: 사이드 패널, 툴바 및 필터링 프록시 모델
**주요 파일**: `client/ui/`, `client/main.py`

---

## 1. 클래스 구조 및 핵심 역할
### `HistoryDockPanel (QDockWidget)`
- **역할**: 모든 값 변경 사항을 시간순으로 로깅하고, 클릭 시 해당 셀로 점프.
- **핵심 메서드**:
  - `_log_ws_event`: 원격 수정 건을 하늘색(`89dceb`)으로 표시.
  - `_handle_data_changed`: 로컬 수정 건을 노란색(`f9e2af`)으로 표시.
  - `_on_item_clicked`: `id(QListWidgetItem)`를 키로 사용하여 저장된 모델 인텍스로 `scrollTo()` 실행.

### `FilterToolBar (QToolBar)`
- **역할**: 실시간 정규표현식 필터링 인터페이스 제공.
- **핵심 모델**: `QSortFilterProxyModel`
  - 원본 `ApiLazyTableModel`을 래핑하여 데이터 파괴 없이 뷰만 필터링.
  - `setFilterKeyColumn(-1)`로 모든 열을 대상으로 검색합니다.

---

## 2. 클래스 간 상호작용 (IO)
- **Input**: `ApiLazyTableModel`의 `dataChanged`, `ws_data_changed` 시그널.
- **Output**: `QTableView`의 `scrollTo`, `setCurrentIndex` 메서드 제어.

---

## 3. 유지보수 포인트
- **테마 유지**: 모든 UI는 `Catppuccin Mocha` 테마 색상을 따릅니다.
- **메모리 관리**: 탭이 닫힐 때 모델과 패널 간의 시그널 연결이 적절히 해제되지 않으면 메모리 누수나 고스트 로그가 발생할 수 있으므로 `disconnect` 로직 주의가 필요합니다.
