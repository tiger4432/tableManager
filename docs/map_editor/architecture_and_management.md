# 🗺️ Wafer Map Management & Architecture Guide (`architecture_and_management.md`)

> **Status:** 🟢 Living | **Last-verified:** 2026-07-30 (**§3.1 📐 표준 분기 정정 + 배지 신설** — ① 종전 §3.1은 `standard` 선택이 *"`(0,0)` 오리진 최적 격자로 자동 튜닝"*한다고 적었고, 실제 코드가 `startX = 0`을 세운 뒤 **모든 저장 좌표에서 `minX`/`minY`를 뺐습니다**(되더하는 곳도 기록도 없었습니다). `019140c`가 이것을 **원점 선언**(`startX = minX`)으로 뒤집었으므로 그 서술은 **폐기된 동작**입니다. ② **이 문서에 Status 배지가 없었습니다** — [MAP_EDITOR_SPEC §5.7](../spec/MAP_EDITOR_SPEC.md)이 필드 규격의 **정본으로 지목**하는 1차 참조인데 신선도를 말하는 줄이 없어 조용히 낡는 경로에 있었습니다) | **Owner:** UI/Map · 좌표 규약의 정본은 [spec/MAP_EDITOR_SPEC §1의 0)](../spec/MAP_EDITOR_SPEC.md)
> 상위: [map_editor/](./README.md) · 개발자 계약: [spec/MAP_EDITOR_SPEC](../spec/MAP_EDITOR_SPEC.md)

본 문서는 **AssyManager**의 웨이퍼 맵 에디터(Map Editor) 및 백엔드 서버 간의 **웨이퍼 맵 데이터 관리 아키텍처, 메타데이터 구조, 좌표 변환 공식, 보호 정책, 클린 덮어쓰기 파이프라인 및 UI 레이아웃**을 상세히 다룹니다.

---

## 1. 개요 (Overview)

웨이퍼 맵 시스템은 **물리적 웨이퍼 실물 규격(Physical Geometry)**과 **위상적 격자 구조(Grid Topology)**를 명확히 분리하여 관리합니다.

* **Physical Wafer Geometry**: 직경(Diameter), 칩 규격(Chip X/Y), 오프셋(Offset X/Y), 엣지 마진(Edge Exclusion) 등 실물 웨이퍼의 물리적 공간 특성
* **Grid Topology**: 캔버스 상의 시각적 셀(Visual Cells)과 백엔드 DB의 물리 칩 좌표(Physical X/Y) 간 매핑 및 회전/반전 상태

---

## 2. 맵 메타데이터 관리 아키텍처 (`wafer_map_metadata`)

> **🔑 도메인 규칙 (사용자 확정 2026-07-26)**: 이 테이블은 스키마 편의가 아니라 **정렬(align)의 유일한 기준**입니다. 맵 데이터를 담는 모든 테이블(defect·EDS·DT·bonding·core)은 **메타 등록이 전제**이며 미등록은 정상이 아니라 **누락**입니다. 오버레이 정렬은 소스·타깃 메타의 델타에서만 유도되고, 셀 레벨 `grid_metadata` 컬럼(§2.1의 구 스킴)은 **폐기**되어 정렬 근거로 쓰이지 않습니다 → [MAP_EDITOR_SPEC §5.0](../spec/MAP_EDITOR_SPEC.md).

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
| `valid_die_ref` | `object`\|`string` | **[M4 phase 1]** 유효 다이 집합을 선언하는 **다른 맵**에 대한 참조. 선택 필드이며 **없으면 종전(원 기하) 동작** | `{"table": "dt_map", "map_id": "TPL_1"}` 또는 `"TPL_1"` |
| `auto_registered` | `boolean` | **[D1]** 이 행의 물리 기하가 **합성값**이라는 표지 — 아무도 재지 않았다는 뜻입니다([INGESTION_GUIDE §1.10](../guide/INGESTION_GUIDE.md), 아래 §2.3-ter) | `true` |

> ℹ️ **선언되지 않은 키는 읽는 쪽이 무시합니다.** 서버(`map_overlay._grid_of`/`_phys_signature`/`frame_axes`)와 클라 모두 **아는 키만** 읽으므로, 위 표에 없는 키를 실어도 기존 경로는 흔들리지 않습니다. `valid_die_ref`가 그렇게 들어온 가산 필드입니다.
>
> 🔴 **`auto_registered`는 더 이상 그 예가 아닙니다(2026-08-04).** 양쪽 다 이 키를 **읽고 판정에 씁니다** — 클라 `physDeclaration`(`cfc09de`), 서버 `map_overlay.geometry_declaration`. 이 문장이 참이던 동안 서버에서는 `auto_registered`의 **독자가 0곳**이었고, 그래서 합성 규격이 선언으로 통과했습니다. 아래 §2.3-ter가 정본입니다.

#### 2.3-ter `auto_registered` — 합성 기하는 선언이 아니다 (D1 · 2026-08-04)

맵에 규격 행이 없으면 두 곳이 **마스크 중립 합성 규격**을 써 넣습니다. 둘 다 "웨이퍼 원 마스크 없음"을 표현할 어휘가 없어 `chip 1x1` / `offset 0` / 격자 반대각선을 외접하는 지름을 씁니다:

- `server/map_meta_registrar.synthesize_grid_meta()` — 인제션 자동 등록([INGESTION_GUIDE §1.10](../guide/INGESTION_GUIDE.md))
- `client2/src/map_editor.js`의 `[fix C]` — 규격 없는 맵의 「표준」 선택

**그 `1`은 1mm 다이라는 주장이 아니라 아무도 재지 않았다는 뜻입니다.** 읽는 쪽이 그것을 몰랐기 때문에, 합성된 1x1 서명은 **존재하고 형식도 온전해서** 정렬 관문("서명이 **없으면** 거절")을 그대로 통과했고, 서버는 합성 소스를 실측 타깃에 1mm 피치로 정렬해 **멀쩡해 보이는 좌표**를 냈습니다.

| 축 | 규칙 |
|---|---|
| 판정의 철자 | **하나뿐입니다.** 서버 `map_overlay.geometry_declaration(meta) -> 'declared' \| 'auto_registered' \| 'absent' \| 'unparsable'`, 클라 `physDeclaration(key, el).source`. **토큰 어휘가 같습니다** — 양측 채점은 `contracts/map_seam/` `geometry_declaration_cases` |
| 무엇을 보나 | **표지이지 값이 아닙니다.** `chip == 1`을 표지로 쓰면 진짜 1mm 다이를 조용히 삼킵니다. 표지를 **값보다 먼저** 읽습니다(값이 먼저면 표지가 아무 일도 하지 않습니다) |
| 레거시 폴백 | **없습니다 — 필요 없다는 것을 셌습니다.** 운영 실측 2026-08-04(읽기 전용): 668행 중 chip 1x1이 320행이고 **그 320행이 전부** 표지를 답니다. 표지 없는 1x1 행은 **0건**입니다 |
| 정렬 | 소스·타깃 어느 쪽이든 합성이면 `make_frame_transform`이 **이름을 대고 거절**합니다 → `align_unavailable` + 한국어 사유(어느 맵을 고쳐야 하는지 포함) |
| 원 마스크 | **거절하지 않습니다.** `circle_die_mask`는 다른 질문("이 기하가 무슨 셀을 인정하나")에 답하고, 합성 규격은 **전 셀 유효**를 말하도록 만들어진 것이라 그 답은 옳습니다. 클라 `isCellInsideWaferFast`도 같은 답을 냅니다 |
| Push 왕복 | 클라 `buildPushGridMetadata`가 표지를 **되실어 줍니다**. 없으면 Push 한 번이 합성 규격을 영구 선언으로 승격시킵니다(등록기는 부재 행만 채우고 기존 행을 다시 보지 않습니다) |

#### 2.3-bis `valid_die_ref` — 유효 다이도 맵이다 (M4 phase 1 · 2026-07-29)

원 기하는 **판정자에서 생성기로 강등**되는 중입니다. 테이프에 붙은 dt 맵은 300mm 제약이 없어 원으로 표현할 수 없는 유효 다이 형상을 가지는데, phase 1은 그것을 **저장된 맵 하나를 가리키는 선언**으로 표현할 수 있게 합니다. phase 2(프리셋=템플릿 생성기)·phase 3(`inside`에서 원 은퇴 + 기존 메타 이관)은 별개 라운드입니다.

**문법** — 서버 `map_overlay.parse_valid_die_ref`와 클라 `parseValidDieRef`가 문자 그대로 같으며, 정본은 `contracts/map_seam/vectors.json`입니다.

| 선언 | 뜻 |
| :--- | :--- |
| 키 없음 / `null` | **선언 없음.** 원 기하 그대로(= 이 필드가 없던 때와 동일) |
| `"TPL_1"` | 맵 키 문자열 |
| `{"table", "map_id"}` | `target_table`/`map_key`도 같은 뜻. `table` 생략 가능, **`map_id`는 필수** |

🔴 **[2026-08-04 · 사용자 확정] 조회 테이블은 선언이 정하지 않습니다 — 언제나 `valid_die_ref`입니다.** 「불러오기는 무조건 valid_die_ref 를 이용하게」. 위 표의 `table`이 무엇을 이름 붙였든, 생략했든, 조회는 그 한 테이블로 갑니다(서버 `map_overlay.VALID_DIE_TABLE` · 클라 `VALID_DIE_TABLE`).

- **이 줄은 종전에 「테이블은 선언한 맵 자신의 것을 승계」였고, 그 서술은 양쪽 코드에서 거짓이 됐습니다.** 승계는 조회 대상을 정하는 규칙이 아니라, 선언이 *원래* 무엇을 뜻했는지를 복원하는 데만 남았습니다.
- **선언이 이름 붙인 테이블은 버려지지 않습니다** — `declared_table`/`declaredTable`로 따라다니며 **거절문에만** 쓰입니다. 「키가 틀렸다」와 「키는 맞는데 그 맵이 여기 없다」는 수리가 다르기 때문입니다. 성공한 조회는 아무 말도 하지 않습니다.
- **저장 바이트는 안 건드립니다**(읽기 고정 · 쓰기 보존). 손대지 않은 저장이 옛 선언을 `valid_die_ref` 쪽으로 조용히 재조준하지 않습니다 — 상세는 [MAP_EDITOR_SPEC §5.7-a](../spec/MAP_EDITOR_SPEC.md).

**판정 규율 3종** (서버 단일 분기점 `map_overlay.resolve_valid_die_basis(meta, resolver) → {basis, source, reason}`):

| `source` | 뜻 |
| :--- | :--- |
| `circle` | 선언이 없다 — 종전 그대로 |
| `ref` | 참조가 풀렸다 — 그 맵이 **유일한** 근거이며 **원과 교집합하지 않는다**(교집합은 보수적으로 보이지만 템플릿이 유효라고 선언한 다이를 조용히 떨어뜨린다) |
| `refused` | 선언은 있는데 풀지 못했다 — `basis` 없음 + 사유. **조용히 원으로 되돌아가지 않는다** |

- ⚠️ **`null`/부재만 "선언 없음"입니다.** 읽을 수 없는 선언(오타·잘못된 타입)을 "선언 없음"으로 접으면 오타 하나가 조용히 원 기하로 되돌아갑니다 — 틀린 답과 맞은 답이 구별되지 않는 상태입니다. 그래서 형태 위반은 **거절**입니다.
- ⚠️ **참조 맵의 셀이 0건이면 "유효 다이 0개"가 아니라 거절**입니다. 거의 언제나 "아직 적재되지 않았다"이고, 0건을 답으로 삼으면 그 맵 전체가 무효가 됩니다.
- ⚠️ **참조 맵의 규격(`wafer_map_metadata`)이 미등록이면 거절**입니다. 선언은 메타 안에 사니 선언한 맵의 프레임은 언제나 아는데 참조 맵의 프레임만 모르는 비대칭이라, identity로 가정하면 회전된 템플릿을 무보정으로 받아들이게 됩니다(`bonding_plan`의 canonical 프레임 규율과 같은 판단). **읽기 고정 이후 이 거절이 「그 키는 `valid_die_ref`에 없다」의 실제 모양입니다** — 거절문은 키와 **원래 가리키던 테이블**을 이름으로 대고, 서버는 `[ValidDie] REFUSED status=… key=… declared_table=…` 한 줄을 로그에 남깁니다(화면에는 개별로 조용하되 로그에서는 집계로 셀 수 있어야 합니다).
- **참조 키는 7b 캐노니컬화를 경유합니다**(`map_overlay.canonical_map_key` → `canonical_key_value`). `number` 선언 slot에 저장된 `1`은 메타가 `LOT_1`로 등록되므로, 선언이 `LOT_01`이어도 찾아냅니다. **두 번째 정규화를 만들지 마십시오.**
- **바운딩 박스는 건드리지 않습니다.** `getWaferBoundingBox`/`get_wafer_bounding_box`는 계속 원으로 계산합니다 — 그것이 **DB에 저장되는 x/y**의 기준이라, 유효 다이 집합을 먹이면 같은 맵의 좌표가 조용히 다른 수로 재해석됩니다. 좌표계는 방향·물리 규격에서만 파생됩니다([MAP_EDITOR_SPEC §5.0](../spec/MAP_EDITOR_SPEC.md)).
- **인제션 자동 등록은 이 선언을 덮지 않습니다** — `map_meta_registrar`는 **부재 시에만** 생성합니다(회귀 시험 2건).

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
  > ⚠️ **적재 대조 게이트 (2026-07-28 · `6db517d`)** — 교체 의미론에서는 페이로드에 담기지 않은 셀이 곧 삭제입니다. 그래서 `pushMapData`는 직렬화된 non-empty 셀 수가 화면의 non-empty 셀 수보다 **적으면 confirm 이전에 적재를 거부**하고 삭제될 셀 수를 메시지에 명시합니다(메타 미등록 맵을 기본 프레임으로 열어 격자·원 밖 셀이 잘리는 경우가 대표 사례). 게이트 3종의 정본은 [MAP_EDITOR_SPEC §6.0-ter](../spec/MAP_EDITOR_SPEC.md)입니다.

---

## 3. 맵 로딩 & 좌표계 복원 메커니즘 (`loadExistingMap`)

### 3.1 메타데이터 미존재 시 복원 옵션 팝업
* **메타데이터 존재하는 맵**: 팝업 없이 이전 저장 당시의 `grid_start_x`, `grid_start_y`, `grid_cols`, `grid_rows`, `rotation`, `side` 규격으로 100% 자동 복원됩니다.
* **메타데이터 없는 레거시 맵**: 로딩 중 **[맵 좌표계 복원 옵션 팝업]**이 자동으로 표시됩니다:
  1. 🅰️ **표준 좌표계 자동 맞춤 (`standard`)**: DB `(minX ~ maxX, minY ~ maxY)` 영역을 자동 측정해 그 크기의 격자를 열고, **오리진을 데이터 자신의 최솟값으로 선언**합니다(`startX = minX`, `startY = minY`).
     > 🔴 **셀 번호를 다시 매기지 않습니다** (`019140c` · 2026-07-30 정정). 종전 이 줄은 *"`(0,0)` 오리진 최적 격자로 자동 튜닝"*이라고 적었고, 실제로 코드가 `startX = 0`을 세운 뒤 **모든 저장 좌표에서 `minX`/`minY`를 뺐습니다** — 되더하는 곳도, 뺐다는 기록도 없었습니다. 표시와 저장은 한 수량이라(`getDbCoords`가 `getCanvasCellFromDb`의 역함수) **재번호된 좌표가 그대로 `⚡ Push`에 실릴 수 있었습니다.** ⚠️ 커밋 메시지는 *"메타 없는 맵 4개, 그려진 셀 1,923개 중 451개가 Push 도달"*이라고 적었으나, **감사 추적 실측(`source_name='user'` 기준 239 에피소드)에서 그 서명을 가진 Push는 발견되지 않았습니다** — 노출은 실재했고 실현은 미확인입니다(대비의 전문은 [MAP_EDITOR_SPEC §4-bis.3-bis](../spec/MAP_EDITOR_SPEC.md)). 지금은 원점을 **선언**하므로 모든 셀이 종전과 같은 캔버스 칸에 앉고, 화면이 말하는 수가 곧 저장된 수입니다. 계약은 [MAP_EDITOR_SPEC §4-bis.3-bis](../spec/MAP_EDITOR_SPEC.md), 좌표 규약은 같은 문서 §1의 0).
     > ⚠️ 물리 기하는 **마스크가 사실상 없는 값**으로 함께 기입됩니다(§4-bis.3 — 원 마스크가 살아 있으면 모서리 셀이 Push 불가가 됩니다).
  2. 🅱️ **현재 UI 설정 유지 (`current`)**: 현재 패널 입력값을 유지한 상태로 로딩
  3. ❌ **취소 (`cancel`)**: 로딩 작업 취소

### 3.2 노치 위치 표기 및 Front/Back 미러링 규칙 ('D' Marker)
웨이퍼 기판의 공간적 정렬 상태를 직관적으로 파악할 수 있도록 V-Notch 위치에 선명한 **'D' 마커 뱃지**가 제공됩니다:
* **FRONT (앞면 관찰)**: 회전 $0^\circ$ 기준, 노치가 하단 **살짝 오른쪽 (`calc(50% + 24px)`)**에 배치됨.
* **BACK (뒷면 관찰)**: 회전 $0^\circ$ 기준, 노치가 좌우 반전되어 하단 **살짝 왼쪽 (`calc(50% - 24px)`)**에 배치됨.
* **회전($0^\circ, 90^\circ, 180^\circ, 270^\circ$) 연동**: 맵 회전 각도에 맞추어 상/하/좌/우 외곽선으로 동적으로 뱃지와 V-Notch 화살표가 포지셔닝됩니다.

#### FRONT / BACK 관찰면 표기 (Side Indicator)
관찰면을 한눈에 구분하도록 **그리드 바깥(그리드 툴바)**에 색상 구분 칩(`#side-indicator`)을 표시합니다. 격자를 가리지 않도록 캔버스가 아닌 DOM 요소로 분리했습니다.
* `FRONT · 앞면` / `BACK · 뒷면` 텍스트, **FRONT = 하늘색(`#38bdf8`)**, **BACK = 앰버(`#f59e0b`)** 배경.
* `updateSideIndicator()`가 side 라디오 변경·`updateOrientationUI()`(맵 로드/프리셋 복원)에서 즉시 갱신(rAF 비의존).
* 추가로 캔버스 중앙에 **대형 반투명 워터마크(표시 전용 오버레이)**를 함께 표기합니다(`renderGridCanvas()` step 9). `FRONT`=하늘색 `rgba(56,189,248,0.13)` / `BACK`=앰버 `rgba(245,158,11,0.13)`, 표시 전용이라 셀 데이터·`gridCells2D`·hit-test에 영향 없음.

#### 반응형 격자 채움 (Responsive Fit)
`fitGridToWorkspace()`가 작업영역(`#map-workspace`)의 가용 공간에 맞춰 격자 래퍼를 **정사각(min(가용W, 가용H))**으로 리사이즈한 뒤 재렌더합니다. 정사각 유지로 원형 웨이퍼의 타원 왜곡을 방지합니다.
* 트리거: `window.resize` + **`ResizeObserver(#map-workspace)`**. 후자는 창 리사이즈가 발생하지 않는 **분할 패널(스플리터) 크기 변경**까지 커버합니다.
* 마우스→셀 매핑(`getGridCellFromMouseEvent`)과 렌더(`renderGridCanvas`)는 **둘 다 live `getBoundingClientRect()`(CSS px)** 로 `cellW`를 계산하고 셀 조회는 인덱스 기반이므로, 크기 변경·DPR/브라우저 줌에도 좌표 정합이 유지됩니다.

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
