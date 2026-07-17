# 그리드 셀 스타일링 심플화 및 Silent Merge 실시간 동기화 정합성 확보

- **일시**: 2026-07-17
- **작성자**: Antigravity (AI Coding Assistant)

## 1. 개요
* 그리드 내 오버라이트(주황색) 및 병합 충돌(빨간색) 색상 표시가 특정 조건 하에서 작동하지 않거나, 실시간 동기화 및 병합 시 정합성이 깨지던 현상을 해소했습니다.
* 112K+ 데이터 원천 조회 시의 지연 병목을 완벽히 회피하면서도 색상을 정확하고 실시간으로 표출해주는 고속 아키텍처 튜닝을 수행했습니다.

## 2. 세부 변경 사항

### A. 그리드 셀 스타일링 판정 단순화 (Client)
* `is_overwrite`와 `is_collision_merge`의 복잡한 논리 조합을 걷어내고, 데이터의 최종 대표 원천 명칭인 **`priority_source`** 단일 필드만을 직렬 매핑하도록 단순화했습니다:
  * `priority_source === 'collision_merge'` ➡️ 빨간색 (`cell-collision-merge`)
  * `priority_source === 'user'` ➡️ 주황색 (`cell-overwrite`)
* 그리드 내 직접 값 수정 시 및 에러 롤백 시에도 `priority_source` 상태가 즉각 연동 및 복구되도록 사이클을 보완했습니다.

### B. CellOverwrite 기반 priority_source 고속 판정 및 핀 고정 (Server)
* 대량 조회 시 병목(2.4초 지연)을 유발하던 `CellSource` 전체 쿼리(`include_sources=False`) 상태를 온전히 복구/보존했습니다.
* 대신, 가벼운 덮어쓰기 테이블(`CellOverwrite`)의 메타데이터를 사용하여 서버 단에서 `priority_source` 정보를 즉시 조립해 내는 최적화 코드를 추가했습니다.
* 자동 배치 인제션 병합 및 수동 변경 병합 시, `CellSource`에 `"collision_merge"`를 저장함과 동시에 `CellOverwrite`에도 `updated_by = "collision_merge"`와 `manual_priority_source = "collision_merge"` 핀을 고정하도록 동기화 가드를 이식했습니다.

### C. Silent Merge 삭제 행 실시간 제거 지원 (Client & Server)
* 중복 키 검출에 의해 삭제되는 껍데기 행 ID(`row_to_delete.row_id`)를 `deleted_row_ids` 목록에 수집하여 API 응답에 얹어 반환하게 구성했습니다.
* 변경 완료 시, 지워진 행 목록이 존재할 경우 실시간 웹소켓으로 **`batch_row_delete`** 이벤트를 쏘아주어, 브라우저 새로고침 없이 그리드 상에서 병합되어 버려진 행이 즉시 사라지게 처리했습니다.

### D. 수동 수정 시 행 내 다른 컬럼의 오버라이트 스타일 해제 방어 (Server)
* 단건/다건 업데이트 API 브로드캐스트 전송 시, 변경된 row 객체들에 대해 `fetch_and_merge_metadata(..., include_sources=False)`를 강제로 돌려 **해당 행에 남아있는 다른 컬럼들의 오버라이트 스타일 정보를 온전히 보존한 뒤 웹소켓으로 쏘도록** 수정했습니다.

### E. 테스트 코드 언패킹 불일치 해결
* `apply_batch_updates` 리턴 시 `deleted_row_ids`를 추가 4분할 반환함에 따라, `test_composite_business_key.py` 내의 언패킹 구조를 갱신하고 `pytest` 29건이 모두 정상 작동하도록 조치했습니다.

### F. 충돌 병합 시 진짜 데이터 원천 소스명 보존 및 껍데기 소스 계승
* 기존 병합 시점에 `CellSource` 의 `source_name` 을 일괄 `"collision_merge"` 로 하드코딩 교체하던 방식을 완전히 탈피했습니다.
* 이제 복합 비즈니스 키 중복 충돌로 병합(Silent Merge)이 일어날 때, **`_load_metadata_row_cell` 헬퍼 함수를 통해 삭제되는 껍데기 행이 해당 셀에 원래 가지고 있던 오리지널 데이터 원천 소스명(예: `file.txt`)을 추적하여 그대로 물려받아(계승)** `CellSource` 에 이식 적재하도록 고도화했습니다.
* 충돌 및 덮어쓰기 이력 자체는 `CellOverwrite.updated_by = "collision_merge"` 와 `manual_priority_source = "collision_merge"` 를 통해 `CellOverwrite` 에 정밀 보존하여, 화면의 붉은색 스타일 및 이중 추적 정합성을 완벽하게 만족시킵니다.

### G. 병합 시 기존 충돌 대상 행의 오버라이트(수동 수정값) 보호 정책 도입
* 비즈니스 키 충돌에 의한 병합 시, 사용자가 수동 수정하지 않은 일반 셀의 값들이 무분별하게 덮어써지면서 기존 충돌 대상 행에 이미 안전하게 기입되어 있던 사용자 수동 수정(user) 값이 파괴(유실)되는 부작용을 해결하기 위해 **병합 보호 정책 가드**를 마련했습니다.
* 충돌 대상 행(`conflict_row`)에 이미 유효한 사용자 오버라이트(`CellOverwrite.is_overwrite = True` 또는 핀 고정) 정보가 존재하고, 이번 변경 요청(`update_item.updates`)에서 해당 셀을 명시적으로 직접 수정하지 않은 경우에는, 충돌 행에 들어있던 기존 값(`old_val`)을 철저히 보존(덮어쓰기 생략)하도록 제어 흐름을 설계했습니다.

