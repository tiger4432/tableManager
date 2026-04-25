# 삭제/숨김 데이터 이동 시 무한 로딩 해결 (2026-04-26)

## 1. 개요 (Overview)
과거에 삭제되었거나 중복 처리되어 프록시 모델에서 숨겨진 데이터의 히스토리 로그를 클릭했을 때, "검색 필터 해제 및 재시도" 로직이 무한 루프에 빠지면서 클라이언트가 완전히 먹통(Freezing)되는 현상을 해결했습니다.

## 2. 문제 원인 (Root Cause)
사용자가 삭제된 데이터(또는 UI에 노출되지 않는 상태의 캐시 데이터)의 히스토리 로그를 클릭했을 때 다음 연쇄 작용이 일어났습니다.

1. **캐시의 함정**: 웹소켓 오류나 페치 시점 차이 등으로 인해, 실제로는 삭제된(또는 UI 노출 범위 `_exposed_rows` 밖의) 데이터가 `source_model._data` (로컬 캐시)에는 여전히 존재할 수 있습니다.
2. **잘못된 로컬 히트(Local Hit)**: `idx_map` 검색에서 해당 데이터의 인덱스가 덜컥 찾아지게 되면서 서버 점프(`jump_to_id`)를 건너뛰고 곧바로 로컬 스크롤(`_final_scroll`) 로직으로 넘어갔습니다.
3. **프록시 필터링 무한 루프**: 
   로컬 스크롤 로직은 뷰(View)의 인덱스(`m_idx`)를 구하는데, 이 데이터는 프록시 모델(`DuplicateFilterProxyModel` 등)에 의해 화면에서 필터링되어 유효하지 않은 인덱스(`m_idx.isValid() == False`)를 반환합니다.
   문제는 이 실패를 감지한 로직이 **"아, 사용자가 검색창에 뭘 입력해 놔서 안 보이는구나!"**라고 성급하게 단정 짓고, 검색창을 `clear()` 한 뒤 0.6초 뒤에 처음부터 다시 시도(Retry)했다는 점입니다.
   하지만 검색창이 애초에 비어있었음에도 불구하고 계속 0.6초마다 검색창을 지우고 재시도하는 과정이 영원히 반복되었습니다.

## 3. 해결 방안 (Solution)
`client/ui/history_logic.py`에 두 가지 핵심 방어선을 구축했습니다.

### A. 뷰포트 범위 검증 강화
로컬 캐시에 데이터가 있더라도, 현재 UI 노출 범위(`_exposed_rows`) 밖에 있다면 로컬 스크롤을 포기하고 서버 점프(Fetch)로 넘기도록 변경했습니다.
```python
exposed_limit = getattr(source_model, '_exposed_rows', float('inf'))
if row_idx is not None and row_idx < exposed_limit:
    if self._final_scroll(row_idx): ...
```

### B. 무한 루프 원천 차단 (Abort Condition)
검색 필터를 해제하고 재시도하기 전에, **현재 검색창이 이미 비어있는지** 검사합니다. 비어있다면 이는 검색어 때문이 아니라 데이터 자체가 삭제되었거나 중복 마커(`_is_duplicate`) 등에 의해 숨겨진 것이 명백하므로, 즉시 오류 메시지를 띄우고 락을 해제합니다.
```python
current_text = main_win._filter_bar._search_box.text()
if not current_text:
    print("[Nav] Search box is already empty! Aborting to prevent infinite loop.")
    self.statusRequested.emit("❌ 데이터를 표시할 수 없습니다 (삭제되거나 유효하지 않음).", 3000)
    self._release_guard()
    return False
```

## 4. 검증 및 효과 (Validation)
- 삭제되거나 중복 처리되어 화면에 보이지 않는 행을 추적하려 할 때, 무한 재시도 늪에 빠지지 않고 즉시 "❌ 데이터를 표시할 수 없습니다" 메시지와 함께 탐색이 정상 종료됩니다.
- 네비게이션 락(`_is_navigating`)이 안전하게 해제되어 다른 로그를 클릭할 수 있습니다.
