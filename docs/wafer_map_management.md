# 🗺️ Wafer Map Management & Architecture Guide

본 문서는 **AssyManager**의 웨이퍼 맵 에디터(Map Editor) 및 백엔드 서버 간의 **웨이퍼 맵 데이터 관리 아키텍처, 메타데이터 구조, 좌표 변환 공식, 보호 정책 및 성능 최적화 파이프라인**을 상세히 다룹니다.

---

## 1. 개요 (Overview)

웨이퍼 맵 시스템은 **물리적 웨이퍼 실물 규격(Physical Geometry)**과 **위상적 격자 구조(Grid Topology)**를 명확히 분리하여 관리합니다.

* **Physical Wafer Geometry**: 직경(Diameter), 칩 규격(Chip X/Y), 오프셋(Offset X/Y), 엣지 마진(Edge Exclusion) 등 실물 웨이퍼의 물리적 특성
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
  맵 저장 시 오리진(ORIGIN)이나 규격이 변경되었을 때, `map_key_columns` 조건에 해당하는 기존 DB 맵 행과 셀 소스(`CellSource`, `CellOverwrite`)들을 백엔드에서 먼저 bulk purge(SQL Delete)한 후 신규 활성 칩들만 재적재하여 유령 셀(Ghost Chips) 잔존을 100% 원천 차단합니다.

---

## 3. 좌표계 변환 및 회전/대칭 통일 공식

### 3.1 visual 좌표 $\leftrightarrow$ physical 좌표 매핑
화면 스크린 상의 시각적 셀 좌표 $(c, r)$과 백엔드 DB 저장 좌표 $(x, y)$ 간의 변환 방정식:

$$xv = c - \text{minC} + \text{startX}$$

$$yv = r - \text{minR} + \text{startY}$$

* $\text{box.minC}, \text{box.minR}$: 현재 회전 각도 및 Front/Back side 상태에서 웨이퍼 영역 내 유효 칩 셀들이 위치한 최소 바운딩 박스(Bounding Box) 인덱스
* **통일 규칙**: 회전 각도($0^\circ, 90^\circ, 180^\circ, 270^\circ$)나 면 상태(Front/Back)에 구애받지 않고, **화면 상 최소 유효 영역 위치가 항상 `startX`, `startY` 매핑 시작점과 직접 결합**되도록 수식 통일.

---

## 4. 보호 셀 (Fixed 'F' Cells) 관리 정책

### 4.1 'F' 셀 보호 로직
기존 맵 로드 시 **웨이퍼 프레임/고정 무결성 셀('F')**로 입력된 데이터는 편집 중 인적 실수를 방지하기 위해 엄격히 보호됩니다.

1. **자동 등록**: `loadExistingMap()` 수행 시 값(Value)이 `'F'`인 좌표는 전용 물리키 보호 집합(`loadedFCells = new Set()`)에 등록됨.
2. **수정/삭제 차단**:
   * 마우스 클릭, 드래그 페인팅, 우클릭 지우개 동작 거부
   * `Fill Grid`, `Fill Selected`, `E1/E2 Auto Paint`, 범주(Legend) 리mapped/삭제 대상에서 자동 제외
3. **해제 조건**:
   * 오직 **`ALL CLEAR` (Clear Grid)** 버튼 클릭 또는 **신규 맵 로드** 시에만 보호 집합이 재설정됨.

---

## 5. 물리 규격 프리셋 (Geometry Presets)

### 5.1 서버 영속화 (`server/config/maps.json`)
자주 사용되는 웨이퍼 칩 사이즈 및 오프셋 조합을 서버 중앙에서 보관 및 관리합니다.

* **API Endpoints**:
  * `GET /api/map-presets`: 저장된 전체 프리셋 목록 수신
  * `POST /api/map-presets`: 커스텀 프리셋 추가 및 `maps.json` 영속화
  * `DELETE /api/map-presets/{preset_key}`: 커스텀 프리셋 삭제

---

## 6. 성능 및 파이프라인 최적화 (Performance Pipeline)

### 6.1 배치 업데이트 최적화 (`PUT /tables/{table}/data/updates`)
대용량(수백~수천 건) 맵 데이터 적재 시 응답 성능을 극대화한 백엔드 파이프라인:

1. **`AuditLog` Bulk Insert (`bulk_insert_audit_logs`)**:
   * ORM 인스턴스 낱개 등록 대신 Dict 매핑 집합으로 `db.bulk_insert_mappings()` 수행 ➡️ ORM 트래킹 오버헤드 소거 및 커밋 속도 3배 향상
2. **FastAPI `BackgroundTasks` 비동기 브로드캐스트**:
   * 웹소켓 브로드캐스트 시리얼라이즈 및 네트워크 전송을 백그라운드 태스크로 이관 ➡️ 클라이언트에 HTTP `200 OK` **0.05초 즉시 반환**
3. **인메모리 메타데이터 병합**:
   * 데이터 수정 직후 캔버스 채색 오버라이드 조회를 DB 추가 쿼리 없이 세션 메모리 내 `overwrites_cache`로 직접 결합 (DB 쿼리 0건)
