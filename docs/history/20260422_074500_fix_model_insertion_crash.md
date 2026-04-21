# 2026-04-22: QSortFilterProxyModel 인덱스 오염 크래시 해결 및 확장 로직 안정화

## 1. 개요
가상 로딩 테이블에서 마지막 행 도달 시 발생하는 `QSortFilterProxyModel: invalid inserted rows reported by source model` 크래시 문제를 해결함.

## 2. 문제 원인 (Root Cause)
- `ApiLazyTableModel.data()` 메서드 내부에서 직접 `beginInsertRows() / endInsertRows()`를 호출하여 모델 구조를 변경함.
- `QSortFilterProxyModel`은 데이터 조회(`data()`) 도중 소스 모델의 구조가 변경되는 것을 허용하지 않으며, 이로 인해 내부 매핑이 파괴되어 크래시가 발생함.

## 3. 해결 방안 및 기술적 구현
- **지연 실행(Deferred Execution) 도입**: `data()` 메서드에서는 조건(마지막 10행 도달)만 탐지하고, 실제 행 확장은 `QTimer.singleShot(0, self.fetchMore)`을 통해 이벤트 루프의 다음 순례로 예약함.
- **아키텍처 정규화**: `fetchMore()`가 모든 행 확장과 데이터 페칭을 전담하도록 구조를 단순화하여 로직 중복을 제거함.
- **정적 확장(Shell Expansion) 유지**: 네트워크 요청 없이 UI의 행 개수만 선제적으로 늘려주는 'Passive Expansion' 기능을 안정적으로 유지함.

## 4. 검증 결과
- **스크롤 안정성**: 하단으로 고속 스크롤 시에도 인덱스 오염 없이 부드럽게 행이 추가됨을 확인.
- **크래시 방지**: `QSortFilterProxyModel` 환경에서 더 이상 모델 불일치 에러가 발생하지 않음을 확인.

---
**보고자: Agent Stability & Lead PM**
