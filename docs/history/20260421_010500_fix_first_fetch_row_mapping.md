# 2026-04-21: Root Cause Fix for First-Turn Floating (Missing Row Mapping)

## 1. 개요
"최신순 끄기" 모드에서 탭 생성 직후 발생하는 데이터 부상(Floating) 현상의 최종 근본 원인을 파악하여 해결함.

## 2. 근본 원인 (Root Cause)
- **발견된 문제**: `ApiLazyTableModel._on_fetch_finished` 메소드의 `if self._first_fetch:` 블록 내부에 `self._update_row_id_map()` 호출이 누락됨.
- **영향**: 첫 페칭(skip=0, limit=50) 완료 후 데이터는 로드되었으나, 이를 조회하기 위한 ID-Index 맵이 비어있는 상태로 유지됨.
- **장애 발현**: 이 상태에서 WebSocket 업데이트가 오면, 모델은 데이터를 이미 가지고 있음에도 불구하고 맵에서 찾지 못해(`idx is None`) 이를 "신규 행"으로 간주하고 최상단(0번)으로 삽입(부상)하게 됨.

## 3. 해결 사항
- `_on_fetch_finished` 의 첫 페칭 완료 루틴 끝에 `_update_row_id_map()`을 추가하여 데이터와 인덱스 맵의 동기화를 보장함.
- (사용자 직접 수정 및 검증 완료)

## 4. 교훈
- 데이터 모델의 상태 변경(`_data`)이 일어나는 모든 분기점에서는 인덱스 매핑의 동기화 여부를 반드시 확인해야 함.
