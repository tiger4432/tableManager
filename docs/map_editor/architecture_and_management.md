# 🗺️ Wafer Map Management & Architecture Guide (`architecture_and_management.md`)

본 문서는 **AssyManager**의 웨이퍼 맵 에디터(Map Editor) 및 백엔드 서버 간의 **웨이퍼 맵 데이터 관리 아키텍처, 메타데이터 구조, 좌표 변환 공식, 보호 정책, 클린 덮어쓰기 파이프라인 및 UI 레이아웃**을 상세히 다룹니다.

---

## 1. 개요 (Overview)

웨이퍼 맵 시스템은 **물리적 웨이퍼 실물 규격(Physical Geometry)**과 **위상적 격자 구조(Grid Topology)**를 명확히 분리하여 관리합니다.

* **Physical Wafer Geometry**: 직경(Diameter), 칩 규격(Chip X/Y), 오프셋(Offset X/Y), 엣지 마진(Edge Exclusion) 등 실물 웨이퍼의 물리적 공간 특성
* **Grid Topology**: 캔버스 상의 시각적 셀(Visual Cells)과 백엔드 DB의 물리 칩 좌표(Physical X/Y) 간 매핑 및 회전/반전 상태

---

## 2. 맵 메타데이터 관리 아키텍처 (`wafer_map_metadata`)

### 2.1 도메인 분리 및 도입 배경
기존에는 `grid_metadata`를 개별 데이터 행/셀(Row/Cell Level)의 컬럼으로 저장하여, 일부 칩(3~5개)만 수정 후 Push할 경우 **수정된 행에만 신규 메타데이터가 기록되고 나머지 기존 행들에는 과거/NULL 메타데이터가 남아 동일 맵(BASE) 내 메타데이터 꼬임 현상**이 발생했습니다.

이를 해결하기 위해 **맵 전체 헤더 관리 전용 테이블(`wafer_map_metadata`)**을 도입하였습니다.

### 2.2 스키마 구조 (`table_config.json`)
`wafer_map_metadata`는 시스템 내 모든 데이터 테이블과 동등한 레벨의 독립 테이블로 관리됩니다:

```json
"wafer_map_metadata": {
  "business_key": "map_pk",
  "composite_key_source": ["target_table", "map_id"],
  "composite_key_separator": "_",
  "column_types": {
    "map_pk": "string",
    "target_table": "string",
    "map_id": "string",
    "grid_metadata": "string"
  },
  "display_columns": ["map_pk", "target_table", "map_id", "grid_metadata"]
}
```

### 2.3 `grid_metadata` JSON 표준 필드 규격

| 필드명 | 데이터 타입 | 설명 | 예시 |
| :--- | :--- | :--- | :--- |
| `phys_wafer_dia` | `number` | 물리적 실물 웨이퍼 직경 (mm) | `300` |
| `phys_chip_x` | `number` | 물리적 칩 가로 크기 (mm) | `12.0` |
| `phys_chip_y` | `number` | 물리적 칩 세로 크기 (mm) | `13.0` |
| `phys_offset_x` | `number` | 물리적 가로 중심 오프셋 (mm) | `1.5` |
| `phys_offset_y` | `number` | 물리적 세로 중심 오프셋 (mm) | `-2.0` |
| `phys_edge_margin` | `number` | 엣지 마진 / Edge Exclusion (mm) | `3.0` |
| `grid_cols` | `number` | 격자 열(Column) 개수 | `25` |
| `grid_rows` | `number` | 격자 행(Row) 개수 | `25` |
| `grid_start_x` | `number` | 유효 영역 시작 X 좌표 offset | `-12` |
| `grid_start_y` | `number` | 유효 영역 시작 Y 좌표 offset | `-12` |
| `grid_y_invert` | `boolean` | Y축 반전 설정 여부 | `false` |
| `rotation` | `number` | 맵 회전 각도 (`0`, `90`, `180`, `270`) | `0` |
| `side` | `string` | 웨이퍼 관찰면 (`'front'`, `'back'`) | `'front'` |

### 2.4 필수 `map_key_columns` 설정 및 테이블 필터링 규칙
웨이퍼 맵을 다루는 모든 테이블은 `table_config.json`에 `map_key_columns` 컬럼 목록을 **무조건 필수 명시**해야 합니다:

```json
"bonding_map": {
  "business_key": "pkg_id",
  "map_key_columns": ["pkg_id", "base"],
  "column_types": {
    "pkg_id": "string",
    "base": "string",
    "x": "number",
    "y": "number",
    "val": "string"
  }
}
```

* **맵 에디터 조회 제한**: 맵 에디터의 Target Table 목록은 `map_key_columns` 속성이 설정된 맵 전용 테이블들만 엄격히 필터링되어 조회/선택이 가능합니다.
* **클린 삭제 덮어쓰기 파이프라인 (`replace_map: true`)**:  
  맵 저장 시 오리진(ORIGIN)이나 규격이 변경되었을 때, `map_key_columns` 조건에 해당하는 기존 DB 맵 행과 셀 소스(`CellSource`, `CellOverwrite`)들을 백엔드에서 먼저 bulk purge(SQL Delete)한 후 신규 활성 칩만 재적재하여 유령 셀(Ghost Chips) 잔존을 100% 원천 차단합니다.

---

## 3. 맵 로딩 & 좌표계 복원 메커니즘 (`loadExistingMap`)

### 3.1 메타데이터 미존재 시 복원 옵션 팝업
* **메타데이터 존재하는 맵**: 팝업 없이 이전 저장 당시의 `grid_start_x`, `grid_start_y`, `grid_cols`, `grid_rows`, `rotation`, `side` 규격으로 100% 자동 복원됩니다.
* **메타데이터 없는 레거시 맵**: 로딩 중 **[맵 좌표계 복원 옵션 팝업]**이 자동으로 표시됩니다:
  1. 🅰️ **표준 좌표계 자동 맞춤 (`standard`)**: DB `(minX ~ maxX, minY ~ maxY)` 영역을 자동 측정하여 `(0, 0)` 오리진 최적 격자로 자동 튜닝
  2. 🅱️ **현재 UI 설정 유지 (`current`)**: 현재 패널 입력값을 유지한 상태로 로딩
  3. ❌ **취소 (`cancel`)**: 로딩 작업 취소

### 3.2 노치 위치 표기 및 Front/Back 미러링 규칙 ('D' Marker)
웨이퍼 기판의 공간적 정렬 상태를 직관적으로 파악할 수 있도록 V-Notch 위치에 선명한 **'D' 마커 뱃지**가 제공됩니다:
* **FRONT (앞면 관찰)**: 회전 $0^\circ$ 기준, 노치가 하단 **살짝 오른쪽 (`calc(50% + 24px)`)**에 배치됨.
* **BACK (뒷면 관찰)**: 회전 $0^\circ$ 기준, 노치가 좌우 반전되어 하단 **살짝 왼쪽 (`calc(50% - 24px)`)**에 배치됨.
* **회전($0^\circ, 90^\circ, 180^\circ, 270^\circ$) 연동**: 맵 회전 각도에 맞추어 상/하/좌/우 외곽선으로 동적으로 뱃지와 V-Notch 화살표가 포지셔닝됩니다.

### 3.3 테이블 간 맵 이월 (Cross-Table Carry-Over)
한 테이블(A)에서 편집한 맵을 다른 테이블(B)로 전환하여 그대로 저장할 수 있습니다. `switchTable()`은 전환 시 **편집 중인 맵(`gridData`)이 존재하면 유지/초기화 확인창**을 띄웁니다:
* **[확인] 맵 유지**: 현재 `gridData`와 레전드(색상)를 보존한 채 테이블만 B로 전환. 저장(`pushMapData`)은 항상 `selectedTable`(=B)을 대상으로 하므로, B의 메타데이터(map 식별자)만 새로 입력하면 편집한 맵이 B에 그대로 적재됩니다.
* **[취소] 맵 초기화**: 기존 동작대로 B의 레전드를 로드하고 격자를 비웁니다.
* 그리드가 비어 있으면 확인창 없이 초기화 경로로 진행합니다. B의 **기존 저장 맵을 불러오려면** `Load Existing Map`(로드 시 `gridData` 초기화 후 적재), 전체 비우기는 `Clear Grid`를 사용합니다.

---

## 4. 외곽층 정밀 자동 추출 알고리즘 (E1 / E2 Distance Transform)

### 4.1 4-Neighbor BFS Distance Transform
원형 웨이퍼 특성상 외곽선에 계단식(Notch Step)이 존재하는데, 대각선 8방향 인접 검사를 할 경우 3칸 안쪽(3rd layer) 셀이 외곽 코너와 대각선으로 접촉하여 E2로 잘못 판정되던 버그를 완벽 교정하였습니다:

1. **거리 0 (`dist = 0`)**: 웨이퍼 외곽 영역 (Outside wafer boundary)
2. **거리 1 (`dist = 1`)**: 외곽 경계선으로부터 직교 1칸 안쪽 셀 ➡️ **정확한 E1 (Outermost 1st Layer)**
3. **거리 2 (`dist = 2`)**: 외곽 경계선으로부터 직교 정확히 2칸 안쪽 셀 ➡️ **정확한 E2 (Exact 2nd Layer)**

---

## 5. 보호 셀 (Fixed 'F' Cells) 관리 정책

### 5.1 'F' 셀 보호 로직
기존 맵 로드 시 **웨이퍼 프레임/고정 무결성 셀('F')**로 입력된 데이터는 편집 중 인적 실수를 방지하기 위해 엄격히 보호됩니다.

1. **자동 등록**: `loadExistingMap()` 수행 시 값(Value)이 `'F'`인 좌표는 전용 물리키 보호 집합(`loadedFCells = new Set()`)에 등록됨.
2. **수정/삭제 차단**:
   * 마우스 클릭, 드래그 페인팅, 우클릭 지우개 동작 거부
   * `Fill Grid`, `Fill Selected`, `E1/E2 Auto Paint`, 범주(Legend) Remap/삭제 대상에서 자동 제외
3. **해제 조건**:
   * 오직 **`ALL CLEAR` (Clear Grid)** 버튼 클릭 또는 **신규 맵 로드** 시에만 보호 집합이 재설정됨.

---

## 6. UI 레이아웃 아키텍처 (4단계 좌측 사이드바)

```text
┌─────────────────────────────────────────────────────────────┐
│ Map Configuration                                           │
├─────────────────────────────────────────────────────────────┤
│ 🔍 1. Map Search & Load                                     │
│   - Target Table 선택 (map_key_columns 보유 테이블 전용)     │
│   - Map ID 핵심 검색어 (pkg_id, base 등)                     │
│   - [📂 Load Existing Map] 버튼                             │
├─────────────────────────────────────────────────────────────┤
│ 📏 2. Physical Wafer Geometry                               │
│   - Geometry Presets (💾 Save / 🗑️ Delete)                  │
│   - Wafer Diameter / Chip X, Y / Offset X, Y / Margin       │
│   - [⚡ Apply Physical Geometry] 적용 버튼                  │
├─────────────────────────────────────────────────────────────┤
│ 🧩 3. Grid & Orientation Settings                           │
│   - Width / Height (계산치 표시)                            │
│   - X Start / Y Start (시작 인덱스)                          │
│   - Map Rotation (0°, 90°, 180°, 270°)                       │
│   - Wafer Side (Front 앞면 / Back 뒷면)                     │
│   - Invert Y / Show Cell Coordinates 체크박스               │
├─────────────────────────────────────────────────────────────┤
│ ⚙️ 4. Advanced Column Mapping (접이식 Details)              │
│   - X Column / Y Column / Value Column 선택                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 7. 성능 및 파이프라인 최적화 (Performance Pipeline)

### 7.1 배치 업데이트 최적화 (`PUT /tables/{table}/data/updates`)
1. **`AuditLog` Bulk Insert (`bulk_insert_audit_logs`)**:
   * Dict 매핑 집합으로 `db.bulk_insert_mappings()` 수행 ➡️ ORM 오버헤드 소거 및 커밋 속도 3배 향상
2. **FastAPI `BackgroundTasks` 비동기 브로드캐스트**:
   * 웹소켓 브로드캐스트를 백그라운드 태스크로 이관 ➡️ 클라이언트에 HTTP `200 OK` **0.05초 즉시 반환**
3. **네트워크 페이로드 90% 절감**:
   * `replace_map: true` 파이프라인 적용으로 빈 셀/NULL 셀은 전송에서 제외하고, 채워진 활성 칩 데이터만 얇게 전송
4. **구조화된 콘솔 & 서버 로깅**:
   * 프론트엔드 콘솔 및 서버 백엔드 로그에 `🔄 [Map Replace Executed]` 정보(테이블, 트랜잭션 ID, 삭제된 구 행 수, 신규 칩 수)를 정밀 기록
