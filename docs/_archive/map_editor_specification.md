# 🗺️ Map Editor Specifications & Function Reference (`specification.md`)

> 🗄️ **SUPERSEDED** by [spec/MAP_EDITOR_SPEC](../spec/MAP_EDITOR_SPEC.md) on 2026-07-27. 히스토리 추적용으로만 보존됩니다.
>
> **아카이브 근거:** 같은 제목·같은 §1~§3 구조의 선행판이며, 후속 문서가 §4~§6(렌더링 라이프사이클·오버레이 정렬 계약·전사 계획)까지 담습니다. **이 문서에만 있던 `loadedFCells` 상태 변수는 아카이브 전에 후속 문서 §2로 이관했습니다**(설명은 현행 `paint_lock` 선언 기준으로 정정). `initTableSelect`는 코드에도 없는 죽은 심볼이라 이관하지 않았습니다.

본 문서는 `assyManager` 프로젝트의 2세대 격자 맵 에디터([`client2/src/map_editor.js`](file:///c:/Users/kk980/Developments/assyManager/client2/src/map_editor.js))에 구현된 모든 프론트엔드 자바스크립트 함수들의 설계 규격, 변환 공식 및 상세 API 레퍼런스를 정리합니다.

---

## 1. 격자 및 좌표계 아키텍처 (Coordinate System Architecture)

격자 맵 에디터는 **물리(Physical) 좌표계**, **화면 격자 셀 인덱스(Grid Cell Index)**, **시각(Visual/Standard) 좌표계**의 삼원화된 구조를 사용하여 웨이퍼 기판의 3D 공간적 물리 거동(회전, 면 반사)과 화면상의 2D 공간 표시를 매끄럽게 처리합니다.

### 1) 기하 변환 수식 (Geometric Transformation Formulas)

사용자가 설정한 `X Start`, `Y Start` 좌표는 **화면상에 보여지는 격자 내 유효 웨이퍼 영역 Bounding Box의 최소값(`box.minC`, `box.minR`)**의 좌표를 지칭합니다.

#### 화면 기준 웨이퍼 유효 셀 경계 상자 (Wafer Bounding Box)
격자 내부 영역($c \in [0, \text{visualCols}-1]$, $r \in [0, \text{visualRows}-1]$)에 속하는 셀 중, 물리 엔진 상 웨이퍼 유효 반경 내부인 셀들의 스크린 인덱스 최댓값/최소값 범위를 계산합니다.
$$\text{box} = \{ \text{minC}, \text{maxC}, \text{minR}, \text{maxR} \}$$

#### 시각 좌표 (Visual / Standard Coordinates) 계산
화면의 셀 눈금 `(c, r)`로부터 데이터베이스에 기록할 직교 좌표 `(xv, yv)`를 도출하는 수식입니다. 백면(Back Side) 미러링 반사 상태에 따른 X/Y축 축반전을 완벽히 보정합니다.

* **수평(X) 축 변환**:
  $$xv = c - \text{box.minC} + \text{startX}$$

* **수직(Y) 축 변환**:
  * `invertY` (Y축 방향 역전 옵션) 미적용 시 (상->하):
    $$yv = r - \text{box.minR} + \text{startY}$$
  * `invertY` 적용 시 (하->상):
    $$yv = \text{box.maxR} - r + \text{startY}$$

---

## 2. 상태 관리 변수 (State Variables)

| 변수명 | 타입 | 설명 |
| :--- | :--- | :--- |
| `currentRotation` | `number` | 현재 화면 격자의 회전 상태 (`0`, `90`, `180`, `270`) |
| `currentSide` | `string` | 웨이퍼의 앞/뒷면 설정 (`"front"`, `"back"`) |
| `activeBrush` | `string` | 현재 팔레트에서 선택되어 격자에 색칠할 값(Legend Value) |
| `gridData` | `object` | 기판 고유 물리 좌표 키(`"${xp}_${yp}"`)를 기준으로 맵핑된 칩 값 매트릭스 |
| `gridCells2D` | `object` | 스크린 인덱스 `gridCells2D[r][c]` 기준으로 맵핑된 시각/물리 좌표 정보 캐시 |
| `loadedFCells` | `Set` | 로드된 고정 무결성 셀('F') 좌표 키 집합 (수정/삭제 거부) |
| `boundingBoxCache` | `object` | 각 각도/직경/칩 피치 기하 설정별 웨이퍼 Bounding Box 연산 결과 캐시 |

---

## 3. 핵심 함수 명세 (Function Reference)

### Category 1: Initialization & DOM Setup
* **`initDOMElements()`**: 캔버스 및 4단계 좌측 패널 컨트롤 노드 캐싱 및 리스너 바인딩.
* **`initTableSelect()`**: 서버 스키마를 조회하여 `map_key_columns`가 설정된 맵 테이블만 드롭다운에 추가.

### Category 2: Topology & Coordinate Math
* **`getPhysicalCoords(c, r, cols, rows, rotation, side)`**: 스크린 인덱스 $(c, r)$을 기판 고유 물리 위치 $(xp, yp)$로 변환.
* **`getVisualCoords(c, r, cols, rows, rotation, side, invertY, startX, startY)`**: 스크린 인덱스 $(c, r)$을 DB 기입용 시각 좌표 $(xv, yv)$로 변환.
* **`getCellFromVisualCoords(xv, yv, cols, rows, rotation, side, invertY, startX, startY)`**: DB 시각 좌표 $(xv, yv)$를 스크린 인덱스 $(c, r)$로 역변환.

### Category 3: Edge Classification & Distance Transform
* **`getEdgeClassification(c, r, visualCols, visualRows, physConfig, width, height)`**:  
  4-Neighbor BFS Distance Transform 알고리즘을 수행하여 outer boundary로부터 exact Manhattan 거리 1인 셀(E1)과 거리 2인 셀(E2)을 수치해석적으로 판정.

### Category 4: Load & Push Pipeline
* **`loadExistingMap()`**: `wafer_map_metadata` 헤더 조회 후 오리진/규격 자동 동기화. 메타데이터 없을 시 복원 팝업 분기.
* **`pushMapData()`**: 활성 칩 셀만 추출하여 `replace_map: true` 파이프라인으로 백엔드 `PUT /tables/{table}/data/updates`에 Clean Replacement 요청.
