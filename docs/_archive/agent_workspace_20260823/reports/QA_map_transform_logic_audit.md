# QA 감사: 맵 좌표 변환 로직 (rot / flip(side) / invertY / startX / startY)

- 일자: 2026-07-26 · 검수관: qa-reviewer (읽기 전용 감사, 코드 수정 없음)
- 대상: `server/utils/coordinate_transformer.py`, `server/utils/physical_wafer_engine.py`, `client2/src/map_editor.js` (**git HEAD 커밋본** — 병렬 수정 중이라 working tree 미사용), `/api/map-presets` (`server/main.py:2877-2950`, `server/config/maps.json`)
- 실측: 스크래치패드 `audit_transform.py` — 클라 HEAD 로직을 Python으로 포팅하여 서버 구현과 전수 대조 (29×25 비정방 격자, chip 11×13mm, 4 rot × 2 side × 2 invertY)

## 판정

**조건부 정합 (GO-WITH-FIXES 성격)** — 서버 변환기 단독으로는 수학적으로 건전(왕복·전단사·회전군 전부 PASS)하나, **서버-클라 동치는 "오프셋 0 + 엔진을 특정 규약으로 구성"이라는 문서화되지 않은 조건에서만 성립**한다. 서버 단독 얼라인 변환의 기반으로 쓰려면 아래 F1·F2를 먼저 해소해야 한다. 참고: 서버 transformer/engine의 프로덕션 소비자는 현재 **0곳**(tests만) — 클라 대응 라이브러리로 만들어졌으나 이미 드리프트된 상태.

## 확인된 결함

### F1 [높음] 엔진-변환기 회전 통합 계약 부재 → rot 90/270에서 마스크·visual 좌표 전면 불일치
- `server/utils/coordinate_transformer.py:198-199`는 회전된 visual 치수로 `engine.is_cell_inside_wafer(c, r, visual_cols, visual_rows)`를 호출하지만, `server/utils/physical_wafer_engine.py:46-81`의 chip_size_x/y·offset_x/y는 **비회전 원본 그대로**다. 클라(`getTransformedPhysicalConfig` map_editor.js HEAD:915-948, `getScreenShift`:950-974)는 90/270에서 chipX/chipY를 스왑하고 오프셋을 회전·back에서 offset_x 부호 반전한다.
- 실측(T6, rot=90, chip 11×13): 클라 inside=425셀 bbox=(2,22,2,26) vs 서버 엔진 inside=425셀 bbox=**(0,24,4,24)** — 마스크 자체가 다른 위치. bbox가 다르므로 `cell_to_visual` 결과가 **725/725 전 셀 불일치**(T7). 엔진을 chip 스왑으로 구성하면 정확 일치(T6b: True).
- 실패 시나리오: 서버가 rot=90 규격의 defect 맵을 표준좌표로 변환 → 모든 die가 (±2, ∓2)급으로 밀린 채 EDS 맵과 얼라인됨. "조용히 안 맞음"의 전형.
- 권장: 변환기(또는 엔진)에 회전·side 인지 구성을 내장하고(클라 915-974와 동일 규약), 비등방 칩 + 4회전 대조 테스트 추가. 현행 테스트(`test_coordinate_transformer.py`)는 15×15 정방·엔진 미장착만 커버.

### F2 [높음] 엔진 미장착 시 서버 fallback 마스크는 클라와 원천 불일치 (rot=0에서도)
- `coordinate_transformer.py:194-209` fallback은 "격자 전체에 내접하는 타원"(inside 513셀), 클라는 물리 원(effective radius, inside 425셀). rot=0에서도 bbox (1,27,1,23) vs (2,26,2,22) → visual 좌표 각 축 1씩 어긋남(T6).
- 실패 시나리오: 서버 단독 변환 코드가 물리 규격 없이 transformer만 생성 → startX/startY 기준점이 bbox에서 나오므로 라벨 좌표 전체가 ±1 이동.
- 권장: 얼라인 경로에서는 엔진 장착을 필수로 강제(엔진 없으면 예외)하거나 fallback을 물리 원 모델로 교체.

### F3 [중] 클라 `getPhysicalCoords`는 mm 오프셋을 물리 die 인덱스에 반올림 혼입 — 서버와 정의가 다름
- map_editor.js HEAD:756-760, 787-788: screen-shift(offset/chip)를 더한 뒤 `Math.round`. 서버 `cell_to_physical`은 오프셋 무관(offset은 마스크에만 영향).
- 실측: offset_x=5.5mm(=chip_x/2)에서 **725/725 셀이 서버 대비 +1 이동**(T4), 클라 자기 자신의 forward→inverse 왕복도 725/725 실패(c→c+1, T5 — JS `Math.round` half-up이 forward/inverse 양쪽에서 올림), 물리 x 범위가 1..29로 **격자 범위(0..28) 초과** — 존재하지 않는 die 키(`29_0`) 생성, `0_*` 열은 영구 미기록.
- offset < chip/2이면 반올림으로 상쇄되어 무증상(현재 프리셋 4A는 오프셋 0). 
- 권장: "물리 die 인덱스는 오프셋 불변"을 경계 계약으로 명문화하고 클라의 shift 혼입 제거(오프셋은 렌더/마스크 전용). 얼라인 설계 시 서버 정의(오프셋 불변)를 기준으로 삼을 것.

### F4 [낮음] 클라 내부 원점(0,0) 마커 로직 자기모순 (back side)
- `renderGridCanvas` HEAD:1371-1380은 back(비회전)에서 `c_zero = box.maxC + startX`(미러 인지), `getGridCellObject`:382-383과 `getVisualCoords`:903은 미러 비인지(`visual.x=0`은 `c = minC - startX`). 실측(T10, back rot0 startX=1): hasZeroZero 판정 셀 c=27 vs 실제 visual(0,0) 셀 c=1.
- 영향: back side에서 원점 하이라이트 존재 판정 오류 가능. 표시 전용 — 데이터 좌표는 `getVisualCoords` 일원이라 무결. `handleCellClick` set-origin(1635-1636)은 `getVisualCoords`와 정합.

### F5 [낮음/관찰] `pushMapData`가 렌더 뷰포트 산출물(`gridCells2D`)에 의존
- HEAD:1434의 화면 밖 셀 skip 때문에 |offset| > chip 크기이면 일부 웨이퍼 셀이 `gridCells2D`에 미등록 → push 누락 가능. 현재 오프셋 규모(서브칩)에서는 미발생. 데이터 경로가 렌더 경로에 결합된 구조 자체가 서버 단독 변환 도입의 정당화 근거.

## 반증 시도했으나 안전한 항목 (실측 PASS)

- **T1 왕복·전단사**: 서버 29×25 비정방, 16조합(4rot×2side×2inv) 전 셀 — cell↔physical↔visual 왕복 및 [0,cols)×[0,rows) 전단사 PASS. off-by-one 없음(코너 기준 `size-1-x` 인덱스 회전이라 짝수 치수도 안전).
- **T2 회전군**: 90° 인덱스 회전 2회 == rot180 구성 성립. 방향 실증: rot=90은 물리 맵의 화면상 **시계방향** 90° 회전(phys(0,0) → 화면 우상단 (24,0)).
- **T3 서버=클라 (오프셋 0)**: 4rot×2side 전 셀 `cell_to_physical` 완전 일치 — 회전 방향·back 미러 축·합성 순서(back mirror→rot) 관례 동일.
- **T8 이월 왕복**: A(rot90/back/invY/start 2,-1) → 표준좌표 → B(rot270/front) → 표준 → A 항등 0실패 (동일 물리 규격 하).
- **T9 invertY vs flip**: invertY는 **시각 라벨 전용**(물리 매핑 불변 — 725/725 동일), side=back은 **물리 미러**(700/725 변화, 중앙열 25셀 불변). 독립 축이며 중복 표현 아님. invertY+back 합성 상쇄 함정 없음.
- **startX/startY 의미**: "웨이퍼 bbox 최소셀(invertY 시 Y는 최대셀)의 시각 라벨 값" = 원점 재정의. 서버 `cell_to_visual`(142-148)과 클라 `getVisualCoords`(900-913) 공식 동일. 단 **bbox 의존**이므로 F1/F2의 마스크 불일치가 그대로 라벨 오차로 전파되는 구조.
- 기존 유닛테스트: `test_coordinate_transformer.py`+`test_physical_wafer_engine.py` 5 passed (실행 확인).

## 프리셋/파라미터 소비 지도

- `/api/map-presets`(maps.json): `phys_*` 6종 + `rotation` + `side`만 저장. **startX/startY/invertY/cols/rows는 프리셋에 없음** — 이들은 push 시 grid meta(`grid_start_x/grid_start_y/grid_y_invert/rotation/side/phys_*`, map_editor.js HEAD:2543-2557)로 wafer_map_metadata에 저장되고 로드 시 소비(2273-2289).
- 프리셋 소비자는 **클라 전용**(HEAD:1133-1157, UI 값 주입). 서버는 저장/서빙만 하고 계산에 사용하지 않음. 서버 transformer/engine의 프로덕션 소비자 0 — 무시되는 파라미터 없음(단, 클라 `getPhysicalCoords` 745-752의 지역변수 4개는 데드코드).
- 데이터 저장 공간: push되는 x/y는 **visual 좌표**(cellObj.x/y), 내부 gridData 키는 **물리 좌표** — 얼라인 시 "DB의 맵 데이터 = 해당 grid meta 기준 visual 좌표"임을 전제해야 함.

## 얼라인(서버 단독 변환) 설계에 대한 시사점

1. 서버 변환기의 **인덱스 대수(rot/side/invertY/start)는 신뢰 가능** — 그대로 기반으로 써도 됨.
2. **마스크/bbox 산출이 유일한 지뢰**: F1(엔진 회전 규약) + F2(fallback)를 해소하지 않으면 visual↔표준 변환이 규격별로 조용히 밀린다. 얼라인 경로에서는 "엔진 필수 + 회전 인지 구성"을 강제할 것.
3. 물리 die 인덱스의 오프셋 불변(서버 정의)을 경계 계약으로 채택하고 F3(클라 혼입)을 별도 수정할 것.
4. 프리셋만으로는 좌표계가 완결되지 않음(start/invert 부재) — 얼라인 입력 규격은 wafer_map_metadata의 grid meta 전체를 요구해야 함.

## 런타임 검증 필요 (코드만으로 단정 불가)

- 실 DB(wafer_map_metadata)에 rot≠0 또는 비등방 칩 + 오프셋≠0 규격이 실존하는지 (실존 시 F1/F3 노출 범위 산정).
- 클라 실제 캔버스에서 `Math.floor(rect.width)` 기반 px 반올림이 마스크 경계 셀 판정을 바꾸는 케이스(포팅 검증은 700×700 정수 가정).

## 교훈 제안 (총괄 검수 후 반영)

- 서버-클라 "동일 로직 이중 구현" 자산 검수 시, 한쪽을 스크립트로 포팅해 **전수 대조**하면 문서에 없는 성립 조건(오프셋 0, 엔진 구성 규약)이 드러난다 — diff/육안 대조로는 T6/T7류 회전 통합 불일치를 놓친다.
