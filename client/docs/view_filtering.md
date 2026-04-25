# 뷰 제어 및 필터링

## 1. 정렬 방식 변경
### 📍 트리거 포인트
`MainWindow._on_sort_mode_changed()` (툴바의 최신순/과거순 토글 버튼)

### ⚙️ 동작 방식
1. 사용자가 토글 버튼을 조작하면, 메인 윈도우에서 열려 있는 모든 `_active_models`를 순회하며 `model.set_sort_latest(enabled)`를 호출합니다.
2. 모델 내부에서는 `_sort_latest` 플래그를 갱신하고, 기존 캐시 데이터(`_data`, `_exposed_rows`, `_loaded_count` 등)를 전면 초기화합니다 (`beginResetModel` -> `endResetModel`).
3. 검색 세션 ID(`_search_session_id`)를 갱신하여 이전 요청이 뒤늦게 응답하더라도 폐기되게끔 차단합니다.
4. `_refresh_total_count()`와 `fetchMore()`를 즉시 호출하여 새로운 정렬 기준(예: `order_by=updated_at`, `order_desc=true`)에 따라 첫 청크 데이터부터 다시 서버에서 로드합니다.

## 2. 검색 필터 적용 (Global Search)
### 📍 트리거 포인트
`MainWindow._on_global_search()` (툴바의 검색창 입력 및 엔터)

### ⚙️ 동작 방식
1. 사용자가 입력한 검색어 문자열 및 타겟 컬럼 정보(`cols_str`)를 기반으로 모든 활성 모델의 `set_search_query(query, search_cols)`를 호출합니다.
2. 모델 내부의 `_search_query` 및 `_search_cols` 변수를 갱신하고, 캐시 데이터와 상태 변수들을 모두 비워버립니다.
3. 고속 타이핑 시 이전 검색 결과가 늦게 도착해 화면이 오염되는 레이스 컨디션 현상을 방지하기 위해, 새로운 `_search_session_id`를 발급(`uuid.uuid4()`)합니다.
4. `fetchMore()`가 트리거되어 URL 쿼리 파라미터(`q`, `cols`)에 인코딩된 문자열을 포함시켜 서버에 질의합니다.
5. 서버 응답 결과의 `_session_id`가 현재 모델의 세션 ID와 일치할 때만 데이터 주입을 허용하고 화면에 렌더링합니다. 불일치하는 경우 해당 응답은 조용히 폐기됩니다.
