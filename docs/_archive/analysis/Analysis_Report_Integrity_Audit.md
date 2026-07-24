# 🧐 데이터 무결성 및 Row ID 타겟팅 전수 감사 리포트 (Integrity Audit)

## 📌 요약 (Executive Summary)
본 리포트는 AssyManager의 실시간 데이터 동기화 및 동적 정렬 환경에서 발생할 수 있는 데이터 오염(Index Drift) 가능성을 차단하기 위해, 시스템 전반의 수정/삭제 로직을 전수 조사한 결과를 기록합니다. 

**검사 결과**: 모든 핵심 작업 도메인에서 취약한 '행 번호(Index)' 대신 **고유 식별자(Row ID)**를 100% 사용하여 작업을 수행하고 있음을 확인 및 보완 완료하였습니다.

---

## 🔍 상세 점검 내역

### 1. 데이터 삭제 (Deletion Pathway)
- **점검 항목**: `ExcelTableView.delete_selected_rows`
- **검증 내용**: 
    - UI 상의 선택 인덱스를 즉시 소스 모델의 인덱스로 매핑(`mapToSource`).
    - 직후 데이터 캐시(`_data`)에서 `row_id`를 추출하여 서버로 전송.
- **결과**: **SAFE** (사용자가 클릭한 시점과 서버 요청 시점 사이에 데이터 순서가 바뀌어도 엉뚱한 행이 삭제되지 않음)

### 2. 데이터 수정 (Update Pathway)
- **단일 셀 수정 (`setData`)**:
    - 수정 시점에 모델 캐시에서 `row_id`를 조회하여 API 파라미터로 주입함.
- **대량 붙여넣기 (`paste_selection`)**:
    - 붙여넣기 영역의 각 행에 대해 개별적인 `row_id`를 실시간 추출하여 타겟팅함.
- **결과**: **SAFE** (전 구간 Row ID Direct Targeting 적용됨)

### 3. 실시간 동기화 (WebSocket Sync)
- **점검 항목**: `_on_websocket_broadcast`
- **검증 내용**: 
    - 서버에서 수신된 모든 브로드캐스트 이벤트는 `row_id`를 키로 하여 클라이언트 로컬 캐시 맵(`_build_row_id_map`)을 검색함.
- **결과**: **SAFE** (Index에 의존하지 않고 ID 기반으로 위치 변화를 추적함)

### 4. 사용자 인터페이스 (Side Panels & Dialogs)
- **데이터 원천 관리 (`CellSourceManageDialog`)**: 
    - **[Bug Found]**: 호출 시점(`_open_source_manager`)에서 프록시 인덱스를 소스 인덱스로 변환하지 않아 정렬 시 엉뚱한 Row ID를 참조하던 결함 발견.
    - **[Fixed]**: `mapToSource`를 적용하여 사용자가 시각적으로 선택한 행의 실제 Row ID를 정확히 추출하도록 보강 완료.
- **데이터 계보 조회 (`_fetch_cell_lineage`)**: 
    - **[Bug Found]**: 히스토리 조회 요청 시 프록시 인덱스를 그대로 사용하여 데이터 불일치가 발생하던 결함 발견.
    - **[Fixed]**: 전달받은 인덱스를 내부적으로 소스 모델 인덱스로 강제 변환하여 정확한 변경 이력을 노출하도록 수정 완료.
- **결과**: **SAFE (After Fixes)**

### 5. 데이터베이스 엔진 전환 (DB Engine Transition)
- **점검 항목**: SQLite -> PostgreSQL (JSONB) 마이그레이션 품질
- **검증 내용**: 
    - 11,000여 건의 데이터 이관 후에도 `Row ID` 식별 체계가 유실 없이 유지됨을 확인.
    - PostgreSQL의 `JSONB` 타입과 `GIN` 인덱스 하에서도 동일한 `Targeting` 로직이 완벽히 동작함.
- **결과**: **SAFE** 

---

## 🛡️ 향후 유지보수 가이드라인
1. **Index 의존 금지**: 하위 모델이나 UI 컴포넌트 간에 데이터를 주고받을 때 `int row` 형태의 인덱스를 식별자로 사용하지 마십시오. 반드시 `row_id` 문자열을 넘겨야 합니다.
2. **Proxy-Source 분리**: `QSortFilterProxyModel` 사용 시 반드시 `mapToSource`를 거쳐 원본 데이터에 접근해야 하며, 가능한 한 `Row ID` 기반의 절대 좌표 조회를 생활화하십시오.
3. **Audit Log 활용**: 모든 수정 내역은 `row_id`를 기준으로 AuditLog와 연결되므로, ID 정합성이 깨지면 시스템 전체의 계보(Lineage)가 붕괴됨을 주의하십시오.

---
*AssyManager Integrity Audit Report | 2026.04.18 (PostgreSQL Finalized)*
