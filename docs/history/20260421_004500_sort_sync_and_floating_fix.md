# 2026-04-21: Global Sort Synchronization & Floating Logic Stabilization

## 1. 개요
"최신순 끄기" 모드 적용 후 발생하는 예기치 못한 데이터 부상(Floating to top) 현상을 해결하기 위해 모델 간 상태 동기화 및 데이터 처리 로직을 표준화함.

## 2. 변경 사항
### 2.1 글로벌 정렬 상태 주입 (Global State Injection)
- **문제**: 탭 전환 시 새로 활성화된 모델이 기본값(`True`)을 유지하여 전역 필터 바 상태(`False`)와 충돌함. 이로 인해 초기 업데이트 시 데이터가 최상단으로 튀어 오르는 현상 발생.
- **해결**: `FilterToolBar.set_active_proxy` 시점에 현재 필터 바의 `_sort_latest` 상태를 활성 모델에 즉시 주입하도록 수정.

### 2.2 부상 로직 표준화 (Floating Logic Standardization)
- **문제**: `batch_row_upsert` 및 `_on_remote_row_fetched`에서 로컬 캐시에 없는 데이터가 들어올 때 정렬 모드와 상관없이 인덱스 `0`에 삽입함.
- **해결**: 모든 데이터 삽입/이동 로직에 `if self._sort_latest:` 가드 조건을 추가하여, 정렬이 꺼져 있을 때는 데이터의 절대적 위치가 보존되도록 개선.

### 2.3 코드 정제
- 조사 과정에서 사용했던 디버그용 `print` 구문 전수 제거.

## 3. 결과
- 탭 전환 직후 업데이트 시에도 정렬 모드가 즉각 반영됨.
- 정렬 OFF 시나리오에서 데이터 순서가 임의로 변경되는 현상 완벽 차단.
