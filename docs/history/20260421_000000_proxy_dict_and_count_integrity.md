# 2026-04-21: Proxy Dictionary Refactor & Total Count Integrity

## 1. 개요
프록시 모델 관리 체계를 리스트에서 딕셔너리로 전환하고, 데이터 개수(Total Count) 업데이트 로직을 서버 중심으로 단일화하여 시스템 아키텍처의 안정성을 극대화함.

## 2. 변경 사항
### 2.1 프록시 관리 구조 현대화 (FilterToolBar)
- **변경 전**: `list[QSortFilterProxyModel]` 구조로 인덱스 기반 접근. 탭 전환 시 정합성 유지에 취약함.
- **변경 후**: `dict[str, QSortFilterProxyModel]` (Key: table_name) 구조로 전환. 탭 순서와 상관없이 테이블 명으로 정확한 프록시 식별 가능.

### 2.2 카운트 형상성 통합 (ApiLazyTableModel)
- **중앙화**: `_set_total_count(new_total)` 메소드를 구현하여 카운트 할당, 뷰포트 축소(`beginRemoveRows`), 시그널 발생 로직을 통합함.
- **Ground Truth**: 삭제/생성 시 클라이언트의 낙관적 계산을 제거하고, 항상 서버의 최신 개수 응답(`_refresh_total_count`)을 기준으로 업데이트하도록 수정함.

### 2.3 안정화 조치 (MainWindow)
- 네비게이션 ID(`table:name`) 처리 로직 보완을 통해 탭 전환 시 UI 실종 문제를 해결함.

## 3. 영향도
- 다중 사용자 환경에서 데이터 개수 불일치 현상 근본적 해결.
- 탭 관리 복잡도 증가에도 안정적인 상태 전이 보장.
