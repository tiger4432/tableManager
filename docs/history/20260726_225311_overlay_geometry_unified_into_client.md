# 오버레이 좌표 변환을 클라 단일 구현으로 일원화 (기하 Phase 1)

> 커밋 `7d931dc` · 2026-07-26 22:53 · 도메인 Client / 맵 에디터 오버레이
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) · 계약: [MAP_EDITOR_SPEC §5](../spec/MAP_EDITOR_SPEC.md) · 선행: [M2-v2](./20260726_204344_m2_v2_plan_as_map_redesign.md)

## 배경

사용자 실사용 증상: **"클라에서 변환 수정해도 오버레이는 안 따라오네."**

원인은 버그가 아니라 **설계**였다. 서버가 *가져오는 순간* 저장된 메타로 정렬을 끝내 타깃 프레임 좌표로 내려주고, 클라는 "이중 변환 금지" 규약에 따라 그 좌표를 재변환하지 않았다. 그래서 화면 컨트롤을 고쳐도 그 수정이 서버에 전달될 경로가 없고, **정렬은 데이터를 가져온 시점에 굳었다.**

## 변경 내용

### 설계 — 물리 키가 불변량이다

```
소스 원본 (x,y) ─[소스 자신의 메타 프레임]─▶ 물리 좌표 ─[타깃의 현재 화면 컨트롤]─▶ 셀
```

핵심은 **`gridData`가 이미 물리 키(`${px}_${py}`)로 저장된다**는 사실이다. 렌더는 매 프레임 `(c,r) → getPhysicalCoords → coordKey`로 되짚어 그린다. 오버레이 셀도 **같은 물리 키**로 들고 있으면, 사용자가 화면 컨트롤을 어떻게 돌리든 렌더 단계에서 메인 맵과 똑같은 규칙으로 함께 움직인다. **메인 맵 로드는 "소스 메타 == 현재 화면 컨트롤"인 특수 케이스**가 된다.

### 오버레이 전용 변환 코드는 0줄 — 프레임 창(frame window)

새 기하식을 쓰는 대신 **규격을 읽는 지점만 잠깐 갈아끼운다.** 주입 지점은 `getTransformedPhysicalConfig`와 `getWaferBoundingBox` **두 곳뿐**이다.

```js
let physFrameOverride = null;

function physNum(key, domEl, dflt) { … }   // 프레임에 값이 있으면 그것, 없으면 DOM
function gridDimNum(key, domEl, dflt) { … }

function withPhysFrame(frame, fn) { … }    // 동기 전용 — 내부 await 금지(try/finally 복원)
```

투영은 메인 로드의 셀 루프와 **같은 두 함수·같은 인자 순서**를 소스 프레임을 씌운 채 돌릴 뿐이다:

```js
function projectCellsToPhys(cells, frame) {
  const f = frame || currentFrame();
  const { cols, rows, rotation, side, invertY, startX, startY } = f;
  return withPhysFrame(f, () => {
    const map = new Map();
    (Array.isArray(cells) ? cells : []).forEach(c => {
      …
      const cell = getCellFromVisualCoords(xn, yn, cols, rows, rotation, side, invertY, startX, startY);
      const p = getPhysicalCoords(cell.c, cell.r, cols, rows, rotation, side);
      map.set(`${p.x}_${p.y}`, …);
    });
    return map;
  });
}
```

신규 함수는 프레임 기술자 계열(`frameFromMeta` / `currentFrame` / `resolveFrame` / `frameAxesKey`)과 바인딩 유도(`deriveMapBinding` / `buildKeyFilters` — 서버 `derive_table_binding`·`build_key_filters`와 같은 규약을 `/tables/{t}/schema`에서 유도), 그리고 관문(`probeAlignDeclaration`)뿐이다.

### "확인하지 못했다"와 "선언이 없다"를 가른다

이 파일에는 이미 그 규약이 주석까지 달린 채 있었다(`fetchPaintRules`, `client2/src/map_editor.js:92-123`). **같은 버그가 두 곳에 새로 쓰였고**, 둘 다 규약으로 되돌렸다.

```js
// fetchGridMetaFor
if (res.status === 404 || res.status === 405) return null;              // 규격 테이블 자체가 없다
if (!res.ok) throw new Error(`맵 규격 조회 실패 (HTTP ${res.status})`);   // 확인 못 함 → 호출자 판단

// probeAlignDeclaration
if (res.status === 404 || res.status === 405) return null;   // 구 서버: 선언 경로 없음
if (!res.ok) throw new Error(`HTTP ${res.status}`);
```

500 한 번으로 조용히 identity 폴백해 **틀린 자리에 마커를 찍으면서 칩에는 "무보정 · 규격 미등록"이라는 거짓 사유**를 띄우던 경로가 닫혔다. 셀 조회 실패와 규격 조회 실패는 다른 사유이므로 `Promise.allSettled`로 분리했다(요청은 여전히 병렬 — 왕복 추가 없음).

### 실패 status — 기존 3종 + 신설 2종

`no_data` · `binding_unavailable` · `align_unavailable`에 **`meta_unavailable`** · **`align_unconfirmed`**가 더해졌다. 전부 **그리지 않고** 목록에 행으로 남으며 재시도 버튼을 유지한다. `align_override_declared`(계측 보정이 선언돼 있으면 거절)도 이 라운드의 관문이다. 이 6종과 별개로 스키마·셀 조회 IO 실패는 일반 `error`로 남는다 — 6종은 전부 **"근거가 없으면 그리지 않는다"는 판단**의 결과이고 `error`는 단순 실패라서 구분한다.

### C7 해소 — 기하 서명에 물리 파라미터 편입

`currentGeomSignature`가 `phys_wafer_dia/chip_x/chip_y/offset_x/offset_y/edge_margin` 6종을 포함한다. **다만 정직하게 적으면**: 소스 메타가 완비된 정상 경로에서 재투영은 항등이며, 이 6종이 **실제로 일하는 곳은 소스 물리 규격이 미등록이라 화면 값으로 폴백하는 경로뿐**이다. 그 분기를 강제 실행해(소스 메타 응답을 비워) chip 12x16 → 9x21에서 물리 집합이 153 → 142로 실제 변경되고 복귀 시 완전히 일치함을 확인했다.

## 아키텍처 영향

- **서버는 무수정이고 삭제된 것도 없다.** `/api/maps/overlay`와 `server/map_overlay.py`(정렬 모듈)는 그대로 살아 있고 `test_map_overlay.py`가 계약을 지킨다. **바뀐 것은 클라가 그 좌표를 소비하지 않는다**는 것뿐이며, 클라는 이 엔드포인트를 `limit=1` probe로 호출해 **`align_applied.origin` 한 필드만** 읽는다.
  > ⚠️ 흔한 오해 정정: `server/bonding_plan.py`는 `map_overlay`를 **import하지 않는다**. 자체 정렬 구현(`normalize_align`/`make_align_transform`)을 가진 별개 경로이며, 열린 항목 A2가 바로 그 사본이 A1 수정을 받지 못한 건이다. `map_overlay`를 참조하는 다른 서버 모듈은 `transfer_plan.py`인데 **바인딩·config 헬퍼 3개**(`resolve_binding`/`build_key_filters`/`load_overlay_config`)만 쓴다.
- **UI 순 추가 컨트롤 0.** 패널·모드·모달·버튼·입력 전부 0. 바뀐 것은 정렬 칩의 문구·툴팁(주어가 서버 → 클라)과 실패 사유 문자열뿐이다.
- 페인트 잠금 계약(`from_overlay`)은 불변 — `o.cells`는 여전히 물리 키 Map이다.
- 검증: 항등 오버레이 10상태(회전 4종·back·invertY·START·chip 비등방)에서 물리 집합 불변, 서로 다른 메타 2쌍에서 각 6/5상태 불변, DB 원본에서 독립 재구현한 오라클과 차 0, **서버 `/api/maps/overlay` 응답과도 결함 축이 살아있는 조합에서 완전 일치**(`onlyServer`/`onlyClient` 모두 0). 적대적 검수는 합성 192축 조합 + 라이브 13맵 + 6쌍 실전 오버레이로 반증을 시도해 **차단 결함 0**을 반환했다.

## 남은 것 (해소되지 않음)

- **Phase 2 이관** — 계측 보정(`align_overrides`) 적용은 이 라운드에 넣지 않았다. 선언이 보이면 **적용하지 않고 명시 실패**한다. 좌표 컬럼명이 관례 밖인 `dt_log`/`bonding_log`는 클라가 스키마에서 바인딩을 유도할 수 없어 `binding_unavailable`로 거절된다 — **Phase 1의 한계는 이 두 테이블을 겹칠 수 없다는 것**이다.
- **B3 (미해소)** — `by_eqp`로만 스코프된 선언은 관문에 보이지 않는다(probe가 단일 오버레이 행의 `align_applied.origin`을 읽기 때문). 클라 단독으로 닫을 수 없고 서버 계약 변경이 필요하다. 라이브에 그런 선언이 없어 현재 도달 불가.
- **F1 (미해소·잠복)** — 호환성 관문이 `cols×rows`만 비교하고 소스/타깃의 `phys_chip_*`/`phys_offset_*` 차이는 툴팁 문구로만 드러난다. 반 피치를 넘는 offset 차이는 **전 셀 1다이 이동**을 조용히 만든다(임계에서 불연속). 라이브 등록 9건은 계열별 물리 규격이 같아 **현재 도달성 0**.
- **F2 (미해소)** — 관문의 타깃 기준이 `getCurrentMapKey()`, 즉 **로드된 맵이 아니라 현재 메타 입력 필드**다. 로드 없이 입력만 바꾸면 엉뚱한 맵의 메타로 판정한다.
- **프레임 스택(`openMapFrame`/`popMapFrame`)·실행취소 라이브 회귀는 미실행이다** — 구조상 정합(레이어에 `rawCells`+`frame` 동반 보관, 복원 시 `syncOverlayGeometry` 재투영)이나 실제로 돌려보지 않았다.
- **정렬은 `wafer_map_metadata`가 등록된 맵에서만 실제로 일한다** — 다음 커밋(`251dbfd`)에서 도메인 규칙으로 확정되며, 등록 격차가 열린 문제로 기록된다.
