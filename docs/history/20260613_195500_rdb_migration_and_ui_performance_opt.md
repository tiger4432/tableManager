# 2026-06-13 RDB 마이그레이션 및 Web UI 성능 최적화 완료

## 개요
기존 JSONB 기반 단일 테이블 구조의 DB 병목을 해소하기 위해 개별 관계형(RDB) 테이블 구조로 전면 포팅을 진행하였으며, 대용량(100개 컬럼) 테이블 노출 시 프론트엔드 조작/스크롤/선택 반응 속도를 극대화하는 성능 최적화를 완료했습니다.

---

## 상세 변경 이력

### 1. Database & Backend API 리팩토링 (JSONB ➡️ RDB)
* **동적 모델 팩토리 (`models.py`)**: `table_config.json`을 로드하여 각 테이블과 물리 컬럼 목록을 런타임에 동적으로 매핑 생성하는 `DYNAMIC_TABLES` 선언
* **데이터 이관 및 정리 (`migrate_jsonb_to_rdb.py`, `drop_legacy_table.py`)**: 기존 `data_rows` 데이터를 신규 분할된 물리 테이블에 복사하고 기존 JSONB 레거시 테이블 삭제
* **DB API 데이터 조회 성능 최적화 (`main.py`)**: 
  * `- 'sources'` 연산자로 I/O가 큰 필드를 필터링하여 응답 패킷 크기 최적화
  * 날짜 포맷 연산을 DB 레벨(`to_char`)에서 처리하도록 오프로딩하여 데이터 조회 속도를 0.90초대로 60% 이상 개선
  * `pytest` 테스트 스위트의 SQLite 호환성 유지 및 startup 행(hang) 이슈 예외 처리 완료

### 2. 프론트엔드 UI 렌더링 및 조작 최적화 (`client2/`)
* **컬럼 가상화(Column Virtualization) 활성화**: 
  * `defaultColDef`에서 컬럼 가상화를 방해하던 `flex: 1`을 제거하고 `width: 150` 및 `minWidth: 100`을 명시하여 브라우저가 현재 보이는 10~15개 내외의 컬럼 노드만 그리도록 강제 적용 (조작 및 스크롤 렉 해결)
* **CSS `backdrop-filter` GPU 부하 우회**:
  * 스크롤 시 GPU 연산 부하를 심하게 발생시키는 `.glass-panel` 및 `.app-header`에서 `backdrop-filter: blur(...)` 속성을 제거
  * 대신 불투명도를 보정한 투명 다크 배경색(`rgba(15, 23, 42, 0.95)`)을 적용해 고급스러운 글래스모피즘 디자인 감성을 보존하면서 스크롤 페인팅 렉 해소
* **커스텀 셀 드래그 범위 선택 차분 리프레시 (Differential Refresh)**:
  * 마우스 드래그 오버(`onCellMouseOver`) 시 매번 전체 셀을 다시 그리는 `refreshCells({ force: true })` 호출을 차단
  * 이전 영역과 새 영역의 합집합(Union)을 구해 해당 범위 내의 Row Nodes와 Columns만 선별 갱신하여 렌더링 대상 셀 개수를 획기적으로 축소
  * 드래그 이벤트를 `requestAnimationFrame`과 연계하여 프레임 쓰로틀링(Throttling) 적용
* **드래그 락 및 윈도우 이탈 예외 처리**:
  * 드래그 도중 브라우저 밖이나 스크롤바 등에서 클릭을 해제할 때 감지가 누락되지 않도록 `event.event.buttons !== 1` 조건 시 드래그 모드를 강제 해제하는 예외 방어 구현
  * 그리드 컨테이너 마우스 이탈(`mouseleave`) 감지 시 드래그 상태가 안정적으로 풀리도록 이벤트 리스너 추가
