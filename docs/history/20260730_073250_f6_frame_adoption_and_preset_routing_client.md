# F6 프레임 채택 + F5c 규격 라우팅(클라 절반) — 그리고 옳은 축을 잘못 고른 안전 논거

> **일자:** 2026-07-30 07:32 | **커밋:** `73b5925` | **담당:** Map PM | **검수 등급:** T2
> **대상:** `client2/src/map_editor.js`(+225) · `client2/tests/valid_die_frame_adoption_harness.mjs`(신규 623줄)
> **관련:** 서버 절반 `50bddda`(`GET /api/maps/preset-routing`) · 이 커밋의 결함 수리 `ae2811c`

> ⚠️ **이 커밋에는 착지 당시 히스토리 항목이 없었다.** QA가 그 공백을 지적했고, `ae2811c`가 고친 두 P0 무음 손상 중 하나가 여기서 들어왔다. 그래서 이 항목은 소급 기록이며, **당시의 논거를 원문 그대로** 남긴다 — 무엇이 틀렸는지는 논거를 지우면 알 수 없다.

## 현상

유효 다이 맵을 지정하면 참조 맵의 치수가 화면 격자와 다를 때마다 「격자 규격이 다릅니다」로 거절됐다. 사용자 표현: **짜증남.**

거절 지점 실측은 딱 한 줄이었고, **서버가 아니라 클라의 자기 관문**이었다(`map_editor.js`의 `resolveValidDie` 안). `server/map_overlay.py`의 같은 판정은 **손대지 않았다** — 그쪽은 오버레이·이송에서 **저장된** 맵끼리의 정합을 지키고, 거기서는 아무것도 그냥 리사이즈할 수 없다.

사용자 시나리오 답변이 답을 정했다: 회전·면이 다르면 지금처럼 변환해서 맞추고(**이미 구현돼 있었다**), 치수가 다르면 **대상 격자를 참조 맵 크기로 넓힌다.** 즉 F6 전체가 후자 하나로 줄었다.

## 해결 — 채택 경로 하나, 새 컨트롤 0개

`applyPresetObject`(프리셋·영역 선택·표준 프레임이 모두 지나는 그 쓰기 지점)에 **참조가 선언한 물리 키만** 담은 preset을 먹인다.

```js
function adoptFrameSpec(frame) {
  if (!frame) return false;
  const preset = {};
  const physKeys = { phys_wafer_dia: frame.waferDia, phys_chip_x: frame.chipX, /* … 6개 */ };
  Object.keys(physKeys).forEach(k => {
    if (physKeys[k] !== undefined && physKeys[k] !== null) preset[k] = physKeys[k];
  });
  applyPresetObject(preset);
  // 파생 치수를 참조의 **저장 치수**로 덮는다.
  if (el.gridCols && frame.cols !== undefined) el.gridCols.value = frame.cols;
  if (el.gridRows && frame.rows !== undefined) el.gridRows.value = frame.rows;
  boundingBoxCache = {};
  updateLegendCounts();
  return true;
}
```

**`rotation`/`side` 키를 넣지 않은 것이 종전 동작을 보존한다** — `applyPresetObject`는 없는 키를 건드리지 않고, 물리 좌표는 회전 불변인 정준 인덱스라 마스크가 공짜로 함께 돈다. 0도 참조가 90도 화면에서 해석되는 것이 사용자가 요구한 그대로다("그냥 맵 불러오는 거랑 동일").

**명시적 치수 쓰기가 load-bearing인데 그것이 자명하지 않다**: `applyPresetObject` → `applyPhysicalGeometry`는 cols/rows를 물리 규격에서 **파생**하는데, 마스크 키는 **저장된** 치수의 인덱스 공간에서 만들어졌다(`projectCellsToPhys(cells, refFrame)`). 데이터 bbox로 연 맵·인제션 자동 등록 맵에서 그 둘이 갈린다. 그래서 채택 후 프레임을 **다시 읽어** 못 맞췄으면 사유를 대고 거절한다 — 다른 인덱스 공간의 키 집합으로 진행하면 화면은 멀쩡하고 값만 틀리는, 이 도메인의 대표 결함이 된다.

## 두 번째 분류기를 만들지 않았다 — 하네스가 실제로 갈렸다

채택은 이미 칠해진 셀을 새 격자·새 유효 다이 **밖으로** 밀어낼 수 있다. 종전 문구는 "⚡ Push가 이 규격과 셀 좌표를 함께 기록합니다"라고 **약속**했는데 지켜질 수 없었고, 사용자는 원인(지정)에서 멀리 떨어진 Push에서 거절을 만났다.

세는 것은 Push 관문이 쓰는 `classifyUnsavableCells` **하나뿐**으로 했다. 근거는 이 라운드의 실측이다 — 손으로 쓴 "visual 격자 밖" 술어는 **190**을 냈고 실제 출하된 분류기는 **27**을 냈다. 렌더의 정의역이 격자보다 넓다(시야 밖까지 그린다).

그리고 **순서가 규칙의 일부다**: `classifyUnsavableCells`의 정의역은 `gridCells2D`이므로 ① 새 프레임으로 ② 새 마스크를 얹어 한 번 그린 **뒤에만** 정확하다. 그래서 알림을 `announceFrameAdoption`으로 미뤘다.

## catch가 계약을 만족시키던 자리

`resolveValidDie`의 catch가 `e.message`를 운영자용 사유로 그대로 흘려보내고 있었다. 이 라운드에서 하네스가 함수 하나를 추출 목록에서 빠뜨렸을 때 칩의 사유가 **`announceFrameAdoption is not defined`**가 됐다 — 형식상 "비지 않은 사유"라 「거절은 사유를 가진다」를 **스택 트레이스가 만족시켰다.** 운영자에게는 아무것도 설명하지 않으면서 데이터 문제로 오해할 여지를 줘, 프로그램 결함을 고치러 **맵 데이터를 만지게** 만든다.

부류를 `e.name`으로 판정해 내부 오류로 이름 붙이고 원문은 괄호에 남긴다. `instanceof`가 아닌 이유: realm이 다르면(하네스의 vm 샌드박스, iframe) 조용히 거짓이 되어 분류 자체가 꺼진다.

## F5c 라우팅 — 순서를 구조로 보장

`wafer_map_metadata` > 라우팅 > 패널. 첫 부등호는 **묻지도 않는 것**으로 보장한다.

```js
if (!loadedGridMeta) {
  await applyRoutedPreset(selectedTable, loadedMapKey || getCurrentMapKey());
}
```

저장된 규격을 손에 쥔 채로 조회하면 "그 답을 무시한다"는 규율이 코드 한 줄의 성실함에 걸린다. 조회 자체를 하지 않는 것이 구조적 보증이다. `status !== 'ok'`이면 아무것도 적용하지 않는다 — 틀린 규격은 `inside`를 바꾸고 `inside`는 저장 가능 집합을 바꾼다.

**빗나감은 정상 경로지 경고가 아니다.** 제품코드 조회 테이블은 운영에만 있고 불완전하다는 것이 설계 전제라, 미선언·불일치·조회 실패는 `console.info`에만 남긴다.

## 검증 (당시 보고)

하네스 108 assertion, 변이 13/13 red. `classifyUnsavableCells`·`eachSavableCell`·`renderGridCanvas`를 **실제로 추출**해 채점(스텁 아님). 격리 스택 브라우저 E2E: 거절됐던 지정이 해석되고, 원인과 증상이 한 숫자(187)로 일치하며, 세션의 모든 요청이 GET. 순 추가 컨트롤 0개.

## 🔴 여기서 들어온 결함 — 논거가 옳은데 축이 틀렸다

`adoptFrameSpec`에 붙은 안전 논거(INV-F6-2)는 이렇게 적혀 있었다:

> `gridData`는 물리 좌표 키라 프레임이 바뀌면 셀이 화면에서 함께 움직이고, 다음 ⚡ Push가 새 프레임으로 x/y를 다시 쓴다 — **운영자가 회전 버튼을 누를 때와 같은 한 번의 행위다.** 위험한 형태는 메타만 바뀌고 저장된 셀은 그대로인 것이고, 그것은 메타를 직접 쓰는 코드에서만 생긴다.

**회전에 대해서는 참이다. 치수 변경에 대해서는 거짓이다.** `getVisualCoords`가 내는 DB 좌표는 `getWaferBoundingBox`의 `minC`/`minR`을 뺀 값이고, 그 bbox는 격자 치수를 훑어서 만들어진다 — **채택이 바꾸는 바로 그 축이고, 회전 유추가 덮지 못하는 유일한 축이다.** 물리 키는 보존되면서 같은 다이가 다른 x/y로 직렬화된다.

대비 관문(`classifyUnsavableCells`)은 이것을 **원리적으로 볼 수 없다** — 격자·원 **밖으로** 나간 셀만 세는데, 격자가 커지는 채택에서 밖으로 나가는 셀은 0개다.

`ae2811c`의 실측: DB(24,24)였던 셀이 DB(22,22)가 되고, **대비 관문은 0을 보고했으며 토스트는 "아직 저장된 것은 없습니다"라고 말했다.** 51x51 → 55x55에서는 `offGrid=0 · outsideRetained=0 · stray=0`인데 모든 셀이 2다이 이동했다.

교훈은 판정 **단위**에 있다: 물리 키로 "같은 다이인가"를 묻는 검증은 이 결함을 볼 수 없다. 물어야 하는 것은 **Push 페이로드의 좌표**다.

## 그때 남아 있던 것

- 서버의 치수 거절(`map_overlay.py`)은 정직한 백스톱으로 그대로 남았다 — 클라가 채택하지 않은 조합·낡은 저장 조합은 계속 소리 나게 실패해야 한다. 서버 의미 변경 0.
- 이 커밋 시점에 하네스는 **green이었다.** 하네스 샌드박스의 console 스텁에 `debug`가 없었지만, 이때 `announceFrameAdoption`의 무손실 갈래는 `showToast`를 불렀다. 그것이 `console.debug`로 바뀐 것은 **다음 커밋 `c24d47b`**이고, 그 순간부터 F6 하네스의 주경로 3건이 red가 됐다(`ae2811c`가 발견).
- `dist` 번들이 함께 커밋됐다.
