# 2026-04-22: 클립보드 복사 시 헤더(컬럼명) 포함 기능 추가

## 1. 개요
사용자가 테이블 데이터를 복사할 때 데이터만 가져올지, 혹은 컬럼 헤더를 포함할지 선택할 수 있는 기능을 구현함.

## 2. 변경 사항 및 기술적 구현

### 2.1 UI 개정 (`client/ui/panel_filter.py`)
- `FilterToolBar`에 `📋 헤더 포함` 토글 버튼 추가.
- `copyHeaderChanged(bool)` 시그널을 통해 상태 변화 브로드캐스트.
- 버튼 상태에 따른 시각적 피드백 제공 (ON: Cyan, OFF: Dark Grey).

### 2.2 가교(Bridge) 로직 (`client/main.py`)
- `MainWindow`에 `_include_copy_header` 상태 필드 추가.
- 툴바 시그널을 `MainWindow`의 슬롯에 연결하여 전역 복사 옵션 동기화.

### 2.3 복사 알고리즘 고도화 (`client/main.py`)
- `ExcelTableView.copy_selection` 메서드 수정.
- 선택 영역(`selectedIndexes`)에서 중복을 제거한 고속 컬럼 식별 로직 구현.
- `model.headerData()`를 활용하여 데이터 최우선 순위 행(Header Row) 생성 및 클립보드 텍스트 병합.

## 3. 검증 결과
- **데이터만 복사**: 버튼 OFF 시 기존과 동일하게 데이터만 복사됨을 확인.
- **헤더 포함 복사**: 버튼 ON 시 최상단에 탭 구분자로 컬럼명이 정확히 포함됨을 확인.
- **다중 선택 대응**: 비연속적인 컬럼 선택 시에도 선택된 순서에 맞는 헤더 행 구성 확인.

---
**보고자: Agent Excel & Lead PM**
