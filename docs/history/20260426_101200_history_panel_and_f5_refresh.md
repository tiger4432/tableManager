# 히스토리 패널 Business Key 노출 및 F5 새로고침 기능 추가

## 1. 개요
* **일시**: 2026년 4월 26일
* **목적**: 히스토리 패널의 직관성 개선 및 클라이언트 애플리케이션의 데이터 새로고침 편의성 제공.

## 2. 주요 변경 사항

### A. 히스토리 패널 식별자 개선 (Business Key)
* **문제점**: 기존 히스토리 로그의 대상 행(row) 식별자가 무의미한 난수형 UUID(`row_id`)로만 노출되어 사용자가 어떤 데이터를 수정했는지 즉각적으로 인지하기 어려웠음.
* **개선**: 
  * `AuditLogResponse` 스키마에 `business_key` 필드 추가.
  * 서버 초기 구동 시 캐시 적재 단계(`AuditLogCache.load_initial`)에서 `DataRow`와 Outer Join을 수행하여 기존 `row_id`에 매칭되는 `business_key`를 일괄 획득하여 성능 저하 없이 메모리에 로드.
  * 실시간 셀 조작(`create_audit_log`) 발생 시, 쿼리된 혹은 인메모리의 `business_key_val`을 캡처하여 캐시에 주입.
  * UI(`HistoryItemData.get_display_text`, 확장 상세 뷰)에서 `business_key`가 존재할 경우 우선 노출하며, 공간 제약을 고려해 10자리 이내로 말줄임 처리.

### B. F5 전역 새로고침 기능 (Global Refresh)
* **문제점**: 현재 테이블 필터 조건이나 스크롤 위치를 유지하면서 데이터를 최신화할 수 있는 빠른 단축키 기능이 부재.
* **개선**:
  * `MainWindow`에 전역 QShortcut `F5` 추가.
  * F5 입력 시 우측 `HistoryDockPanel` 데이터 서버 재조회.
  * 현재 보고 있는 화면(Dashboard 또는 특정 Table)의 상태 유지 새로고침 수행.
  * `ApiLazyTableModel`에 `refresh_data()`를 구현하여 기존 검색어(`_search_query`) 및 대상 컬럼 조건은 유지한 채, 세션 무효화 및 페이징 초기화 후 데이터 재페치 동작 구현. 스크롤 0 초기화 지원.

## 3. 관련 파일
* `server/database/schemas.py`
* `server/database/crud.py`
* `server/audit_cache.py`
* `client/ui/history_logic.py`
* `client/ui/panel_history.py`
* `client/main.py`
* `client/models/table_model.py`
