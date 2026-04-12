# Agent_C_v2 (QA) Report — 초기 total_count 하드코딩 제거 완료

- **작성자**: Antigravity (Agent C 역할 수행)
- **수정 파일**: `client/models/table_model.py`
- **참조 스킬**: `SubAgentExecution`

---

## 📌 수정 내역

### 1. `ApiLazyTableModel.__init__` 수정
- `self._total_count`의 초기값을 `1000` (하드코딩)에서 `0`으로 변경하였습니다.
- 첫 페치 여부를 추적하기 위해 `self._first_fetch = True` 플래그를 도입하였습니다.

### 2. `canFetchMore` 로직 보완
- `total_count`가 0인 상태에서도 첫 번째 데이터 요청이 정상적으로 트리거될 수 있도록 로직을 수정하였습니다.
- `self._first_fetch`가 `True`이면 `total_count`에 상관없이 `canFetchMore`가 `True`를 반환합니다.

### 3. `_on_fetch_finished` 수정
- 서버로부터 첫 응답을 받으면 `self._first_fetch = False`로 설정하여 이후에는 정상적인 `len(self._data) < self._total_count` 비교 로직이 작동하게 하였습니다.

---

## ✅ 검증 결과

- **"Loading..." 표시 제거**: 앱 시작 직후 `rowCount()`가 `0`이므로 불필요한 빈 행("Loading...")이 보이지 않음을 확인했습니다.
- **초기 로딩**: `main.py`에서 호출하는 `model.canFetchMore()`가 `True`를 반환하여 첫 청크(50개 행)를 정상적으로 가져옵니다.
- **추가 로딩**: 첫 응답에서 서버의 실제 `total` 값을 받아 `_total_count`를 갱신하므로, 스크롤 시 `fetchMore`가 지속적으로 작동하는 구조임을 확인했습니다.
