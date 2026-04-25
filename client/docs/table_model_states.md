# ApiLazyTableModel State Variables (상태 변수) 총정리

`ApiLazyTableModel` 클래스 내에서 관리되는 핵심 상태 변수들의 역할과 주로 사용되는 곳을 그룹별로 정리했습니다.

---

## 1. 📊 데이터 저장소 및 식별 관련 (Data & Mapping)

| 변수명 | 역할 및 특징 | 주요 관련 함수 |
|---|---|---|
| `_data` | **테이블의 실제 데이터를 담는 1차원 리스트.** 화면에 보일 셀 정보를 딕셔너리 형태로 저장하며, 아직 로드되지 않은 공간은 `None`으로 채워집니다. | `_on_fetch_finished`, `data`, `setData` |
| `_row_id_map` | **고속 검색용 해시맵 (`row_id` -> `index`)**. 실시간 웹소켓 이벤트나 특정 ID 점프 시, O(1)의 속도로 `_data` 내의 위치를 찾기 위해 지속적으로 동기화됩니다. | `_build_row_id_map`, `_update_row_id_map` |
| `_columns` | 화면에 표시될 **컬럼명(키 값) 리스트**. 뷰(View)의 인덱스와 매핑되어 올바른 데이터를 꺼내오게 합니다. | `__init__`, `update_columns`, `data` |

## 2. 📏 크기 및 노출 범위 관련 (Size & Exposure)

| 변수명 | 역할 및 특징 | 주요 관련 함수 |
|---|---|---|
| `_total_count` | **서버 DB에 존재하는 해당 테이블의 총 행(Row) 개수**. 스크롤바의 최대 크기를 결정하며, 캐싱 문제 방지를 위해 주기적으로 동기화됩니다. | `_refresh_total_count`, `_set_total_count` |
| `_exposed_rows` | **현재 Qt View포트에 노출하기로 선언한 행의 개수**. `_total_count`보다 클 수 없으며, 스크롤을 내릴 때마다 이 값이 늘어나면서 UI가 확장됩니다. (가짜 빈 공간 `None` 포함) | `fetchMore`, `_on_fetch_finished`, `rowCount` |
| `_loaded_count` | **메모리(`_data`)에 `None`이 아닌 실제 데이터가 들어있는 진짜 개수**. 주로 UI의 상태바(Status Bar) 하단에 '현재 로드된 건수'를 표시하기 위해 쓰입니다. | `_on_fetch_finished`, `_on_websocket_broadcast` |

## 3. 🌐 페칭(로딩) 상태 제어 관련 (Fetch Control)

| 변수명 | 역할 및 특징 | 주요 관련 함수 |
|---|---|---|
| `_fetching` | **네트워크 통신 중임을 나타내는 락(Lock) 플래그**. 이게 `True`일 때는 중복 요청이 발생하지 않도록 `canFetchMore`가 `False`를 반환합니다. | `request_fetch`, `_finalize_fetch`, `canFetchMore` |
| `_first_fetch` | **검색이나 모델 리셋 후 첫 번째 로딩인지 여부**. 첫 페치 시에는 모델 전체를 갈아엎고(`beginResetModel`), 이후부터는 이어붙이는(`beginInsertRows`) 로직 분기를 탑니다. | `set_search_query`, `_on_fetch_finished` |
| `_chunk_size` | **한 번에 서버에 요청하는 데이터 묶음 개수 (Limit)**. 네트워크 응답 속도에 따라 50~3000 사이에서 동적으로 커지거나 작아집니다 (Adaptive Chunk Size). | `fetchMore`, `_on_fetch_finished` |
| `_server_fetched_count` | **순차 로딩(Batch) 시, 끊김 없이 서버에서 받아온 마지막 인덱스(High Water Mark)**. '다음 데이터 가져오기'를 할 때 시작 위치(`skip`)로 사용됩니다. | `fetch_batch`, `_on_fetch_finished` |
| `_active_target_skip` | **현재 통신 중인 요청이 어디(`skip`)를 가리키고 있는지 저장**. 콜백 시 데이터 주입 위치를 결정합니다. | `fetchMore`, `_on_fetch_finished` |

## 4. 🧭 컨텍스트 및 타이머 관련 (Context & Timer)

| 변수명 | 역할 및 특징 | 주요 관련 함수 |
|---|---|---|
| `_active_fetch_ctx` | **현재 실행 중인 페칭 작업의 상세 정보(명령서)**. 일반 스크롤인지, 점프인지, 배치 로딩인지(`source`, `params`)를 담고 있습니다. | `request_fetch`, `fetchMore`, `_on_fetch_finished` |
| `_pending_fetch_ctx` | `data()` 함수에서 빈 셀을 발견했을 때 **임시로 담아두는 대기열 명령서**. 타이머가 돌기 전까지 마지막 요청만 살아남습니다. | `data`, `_on_jump_timer_timeout` |
| `_jump_timer` | Qt View가 1초에 수백 번 빈 셀을 요청할 때, 이를 하나로 모아서 **1ms 후에 한 번만 API를 쏘도록 묶어주는 디바운스(Debounce) 타이머**입니다. | `__init__`, `data`, `_on_jump_timer_timeout` |
| `_search_session_id` | **검색창 입력 시마다 발급되는 고유 난수(UUID)**. 옛날 검색 결과가 늦게 도착해서 현재 화면을 덮어씌우는 것(레이스 컨디션)을 방어합니다. | `set_search_query`, `_on_fetch_finished` |

## 5. 🛠️ 기타 상태 관련 (Misc)

| 변수명 | 역할 및 특징 | 주요 관련 함수 |
|---|---|---|
| `_sort_latest` | **"최신순 정렬" 모드가 켜져 있는지 여부**. 켜져 있으면 웹소켓으로 신규 데이터가 왔을 때 맨 위에 꽂고, 아니면 맨 아래에 꽂습니다. | `set_sort_latest`, `_on_websocket_broadcast` |
| `_is_processing_remote` | 웹소켓 이벤트를 처리 중임을 알리는 플래그. 처리 중일 때는 불필요한 중복 렌더링을 막는 데 쓰일 수 있습니다. | `_on_websocket_broadcast` |
| `_pending_target_row_id`<br>`_last_jump_target` | **최근에 점프를 시도했던 목적지 `row_id`**. 디버깅 및 점프 데이터 정합성 검증 용도로 사용됩니다. | `request_fetch`, `_on_fetch_finished` |
