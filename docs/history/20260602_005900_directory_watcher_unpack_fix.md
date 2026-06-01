# 변경 이력: DirectoryWatcher 내 crud.apply_batch_updates 반환값 unpacking 에러 해결

- **작성일**: 2026년 6월 2일
- **작성자**: Antigravity
- **상태**: 완료

## 1. 개요 및 목적
- 수집된 원천 CSV 파일을 처리하는 도중 `DirectoryWatcher`가 백엔드 DB 배치 업데이트를 수행할 때 다음과 같은 예외와 함께 파이프라인 처리에 실패하는 버그가 발견되었습니다:
  `Failed to apply local batch update: too many values to unpack (expected 2)`
- 원인은 이전 감사 로그(AuditLog) 개선 과정에서 `crud.apply_batch_updates`의 반환값 개수가 2개(`results, total_changed_cells`)에서 3개(`results, total_changed_cells, serialized_logs`)로 확장되었으나, `DirectoryWatcher`가 이를 반영하지 않고 2개만 unpack하도록 하드코딩되어 있었기 때문입니다.
- 이를 해결하기 위해 `DirectoryWatcher` 내 호출 지점을 3개 변수 대응으로 올바르게 수정합니다.

## 2. 세부 구현 사항

### 백엔드 인제스터 (`server/parsers/directory_watcher.py`)
- **Unpacking 수정**:
  - `IngestionHandler._send_to_upsert` 메서드 내부에서 `crud.apply_batch_updates`를 호출하여 반환 값을 매핑할 때, 세 번째 감사 로그 리턴 인자(`_`)를 명시적으로 무시하고 받아들일 수 있도록 수정했습니다.
  - 변경 전: `results, changed_cells = crud.apply_batch_updates(db, t_name, batch_obj)`
  - 변경 후: `results, changed_cells, _ = crud.apply_batch_updates(db, t_name, batch_obj)`

## 3. 검증 결과
- 수정 후 `server/parsers/directory_watcher.py`에 대한 파이썬 소스 컴파일 테스트가 성공적으로 완료되었습니다.
