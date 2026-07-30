# P0 두 건 — 채택이 저장 좌표를 움직였고, 지문 없는 붙여넣기가 통과했다

> **일자:** 2026-07-30 10:11 | **커밋:** `ae2811c` | **담당:** Map PM | **검수 등급:** T2(QA 발견 → 수리)
> **대상:** `client2/src/map_editor.js`(+398) · `client2/src/transfer_plan.js`(+59) · `client2/src/transfer_plan.css`(+89/−…) · `client2/map_editor.html` · `client2/tests/valid_die_frame_adoption_harness.mjs`(+436/−…) · `client2/tests/company_roundtrip_harness.mjs`(+325)
> **관련:** 결함이 들어온 커밋 `73b5925`(P0-1) · `c9bf2c7`(P0-2) · 로스터를 넓힌 `5a14e77`(MEDIUM-4) · 하네스를 red로 만든 `c24d47b`

QA가 `73b5925`와 `c9bf2c7`에서 찾아낸 **무음 손상 경로 둘.** 둘 다 평범한 운영자 조작으로 도달하고, 둘 다 **그 파일의 모든 관문에 보이지 않았다.**

## P0-1 — 채택이 이미 로드된 셀의 **저장 좌표**를 움직였다

`73b5925`의 안전 논거는 "`gridData`가 물리 좌표 키이므로 프레임이 바뀌면 셀이 화면에서 함께 움직이고 다음 Push가 x/y를 다시 쓴다 — **회전 버튼을 누르는 것과 같은 한 번의 행위**"였다.

**회전은 키 불변이다. 치수 변경은 아니다.**

```
getVisualCoords:  xv = colVisual - box.minC + startX
getWaferBoundingBox: box는 gridDimNum('cols'/'rows')로 격자를 훑어서 만들어진다
```

즉 bbox는 **치수의 함수**고, 그것이 채택이 바꾸는 바로 그 축이며 **회전 유추가 덮지 못하는 유일한 축**이다. 같은 물리 키가 다른 x/y로 직렬화되고 `replace_map`이 밀린 좌표를 기록한다.

**대비 관문(`classifyUnsavableCells`)은 이것을 원리적으로 볼 수 없다** — 격자·원 **밖으로** 나간 셀만 세는데, 격자가 커지는 채택에서는 밖으로 나가는 셀이 0개다. 실측 51x51 → 55x55: `offGrid=0 · outsideRetained=0 · stray=0`인데 **모든 셀이 2다이 이동**. 그리고 DB(24,24)였던 셀이 DB(22,22)가 되는 동안 **대비 관문은 0을 보고하고 토스트는 "아직 저장된 것은 없습니다"라고 말했다.**

⚠️ **그래서 판정의 단위는 Push 페이로드의 좌표다.** 물리 키로 "같은 다이인가"를 묻는 검증은 이 결함을 **원리적으로** 볼 수 없다.

### 새 변환은 한 줄도 없다

렌더가 셀 하나를 만들 때 쓰는 두 줄을 기존 프레임 창 안에서 같은 순서로 돌린다 — `projectCellsToPhys`가 하는 그 연산의 역방향이다.

```js
function dbCoordsByPhysKey(frame) {
  const rf = resolveFrame(frame);
  ...
  return withPhysFrame(rf, () => {
    const out = new Map();
    for (let r = 0; r < visualRows; r++) for (let c = 0; c < visualCols; c++) {
      const p = getPhysicalCoords(c, r, rf.cols, rf.rows, rf.rotation, rf.side);
      const v = getVisualCoords(c, r, rf.cols, rf.rows, rf.rotation, rf.side,
        rf.invertY, rf.startX, rf.startY);
      out.set(`${p.x}_${p.y}`, `${v.x}_${v.y}`);
    }
    return out;
  });
}
```

`adoptionCoordinateCost`가 `moved`(같은 다이가 다른 x/y로 저장됨 — 결함 본체) · `lost`(새 프레임이 그 다이를 덮지 못함) · `kept`를 센다. 하나라도 움직이거나 잃으면 **채택을 중단하고**, 개수·실제 before/after 표본·📂 Load 경로를 사유에 담는다.

**판정은 치수 비교가 아니라 좌표 비교다.** 좌표가 하나도 움직이지 않는 치수 변경은 통과하고, 셀이 없는 맵(사용자가 물었던 "기존 프레임이 없으면?")에서는 움직일 좌표가 없으므로 기능이 그대로 남는다.

### 픽스처 둘이 load-bearing이고 새것이었다

기존 픽스처 둘은 **모두 셀을 잃는다.** 그래서 어느 쪽도 「움직이기만 하는」 축을 채점할 수 없었다 — `lost`만 보는 가드와 **물리 키로 잰 비용**이 둘 다 green으로 남았고, 같은 규격 45×45→46×46 채택이 **1272개를 움직이고 하나도 잃지 않는** 픽스처가 생긴 뒤에야 red가 됐다.

그리고 45×45→47×47에 직경이 다른 조합은 **아무것도 움직이지 않아 허용된다** — 이것이 가드가 "치수가 다르다"가 아님을 증명하는 음성 대조다.

### 재키잉을 이 커밋에 넣지 않은 이유

채택이 셀이 있는 맵에서도 동작하게 하는 재키잉(`gridData`·`serverCellKeys`·`loadedFCells`가 **함께** 이주해야 하고 하나가 뒤처지면 조용히 낡는다)은 일부러 뺐다. 음성 대조가 다른 assertion이고, 여기 함께 넣으면 **가드의 거부 갈래가 도달 불가능해진다.** 죽은 것이 증명된 가드는 없는 가드보다 나쁘다.

## P0-2 — 지문이 **가장 필요한 맵에서 구조적으로 부재**했다

회전 0의 노치는 `box.maxR + 1`에 앉는다. 그런데 **메타 없는 모든 맵에 적용되는 마스크 없는 프레임**(📐 표준 기본값)에서는 bbox가 격자를 꽉 채우므로 `box.maxR + 1 == visualRows` — **격자 밖**이다. 네 회전이 모두 그렇다(180 → −1, 90 → −1, 270 → visualCols).

종전에는 격자 밖 좌표를 **그대로 돌려주었고**, 호출부는 `notchVerified: false`로 통과시키며 다섯 줄 확인창에 경고 한 줄을 넣었다. 회전·면은 치수를 보존하므로 다른 관문은 **하나도 걸리지 않는다.**

실측: 12x10 격자(마스크 없음, 노치 r10 = 격자 밖)에서 **0°에서 복사 → 180° 클릭 → 붙여넣기**로 **물리 키 120개 전부의 값이 바뀌었다.** 복사·회전·Ctrl+V는 전부 평범한 조작이다.

수리는 둘이다. `computeNotchCell`이 격자 밖이면 `null`을 돌려주고 — **주석이 그렇게 약속해 놨는데 코드가 그러지 않았다** — 그 경계를 **모듈 상태가 아니라 인자 `rotation`으로** 잰다:

```js
const isRot = (rotation === 90 || rotation === 270);
const visualCols = isRot ? rows : cols;
const visualRows = isRot ? cols : rows;
if (cell.r < 0 || cell.r >= visualRows || cell.c < 0 || cell.c >= visualCols) return null;
```

`getVisualGridDimensions()`는 모듈의 `currentRotation`을 읽으므로, 화면과 다른 회전을 물으면 **좌표는 그 회전으로 계산하고 경계는 화면 회전으로 재는 자기모순**이 생긴다(하네스 실측: rot 0 화면에서 rot 270을 물었을 때 격자 밖 좌표가 null이 아니라 좌표로 돌아왔다).

그리고 **지문이 없으면 거부한다.** 노치는 치수 보존 프레임 변경의 유일한 신호이므로, 그 부재는 "괜찮다"가 아니라 **"확인할 수 없다"**다.

> ⚠️ **179개 선언 맵 중 27개만 노치가 격자 안에 있다.** 이 거부는 나머지 152개에서 붙여넣기 왕복을 **제거한다.** 안전 면에서 옳고 기능 면에서 비싸다 — 이 커밋은 그 대가를 그대로 지불했다.

## MEDIUM-4 — 좁히는 수리는 듣지 않았고, 한 줄이 일곱 단어를 함께 고쳤다

`5a14e77`이 ②→① 왕복을 위해 헤더 로스터에 `MAT·BIN·MAP·가용·사용·잔여`를 실은 뒤로, `auxHeaderInLine`의 오른쪽→왼쪽 스캔은 **격자 셀의 값이 그 단어이면 멈추지 않았다.** 실측: 마지막 격자 열이 `BIN`인 맵에서 `gridWidth`가 9 대신 7로 나오고 붙여넣기가 「열 수가 다릅니다」로 거부됐다. 사유가 원인을 가리키지 않으므로 운영자는 **멀쩡한 격자 크기·회전을 만진다.**

**시도했다가 버린 수리**: 로스터를 좁혀 머리글 네 단어만 통과시키기. `COUNT`가 **진짜 머리글 단어**여서 그 방식으로는 `COUNT`로 칠한 격자 셀을 막을 수 없다.

착지한 수리는 한 줄이다:

```js
if (columnIdByHeader(f) === 'value') break;     // VALUE = 보조표의 첫 칸. 왼쪽은 격자다.
```

`VALUE`가 보조표의 첫 칸이므로(쓰는 쪽 배치 그대로) 그 왼쪽은 무조건 격자다 — 그리고 이 종료 조건이 있으면 나머지 여섯 단어도 **전부 함께 막힌다.**

**`isAuxHeadWord` 가드는 유지하지 않고 제거했다.** VALUE 종료가 있으면 그 가드를 되돌리는 변이가 **green으로 남았다** = 채점되지 않는 가드다. 증명되지 않는 두 번째 가드는 두지 않는다.

## 같은 검수에서 나온 넷

**MEDIUM-1 — 거절을 만드는 수는 하나뿐이다.** `pushMapData`는 `offGrid + outsideRetained`로 판정하는데 `announceFrameAdoption`은 `outsideStray`까지 더한 수를 세어 놓고 **같은 문장**("이 상태로는 저장할 수 없어 Push가 거절합니다")을 말했다. 실측 **토스트 4 · Push 알림 2.** 게다가 stray는 거절이 아니라 **정리 제안**이라는 다른 대화상자로 간다. `pushBlockingCount(u)` 하나로 수렴시키고, stray는 자기 문장을 받는다. 옛 픽스처가 `serverCellKeys`를 null로 남겨 **stray를 강제로 0으로 만들었고** 그 기대값은 자기 비교였다.

**MEDIUM-2 — 쓰는 규칙과 읽는 규칙이 달랐다.** 복사가 각 행을 `rowCells.join('\t')`으로 즉시 문자열로 만들고 붙여넣기가 `parseTsv`(엑셀 인용 규칙을 아는 유일한 구현)로 읽었다. 실측 왕복 파괴: DESC `"고온" 조건` → `고온 조건`(인용부호 소실 후 legend에 기록) · DESC `1H<TAB>비교` → `1H`로 절단 · `"`나 줄바꿈을 품은 셀 → 열/행 수가 어긋나 원인과 무관한 사유로 거부. 이제 행 배열의 배열을 만들고 마지막에 `serializeTsv` 한 번 — 계약이 `parseTsv(serializeTsv(g)) === g`다.

**MEDIUM-3 — 노치 술어를 복사와 붙여넣기가 공유한다.** 종전에는 복사가 `isNotchCell && val === ''`일 때만 'D'를 찍고(값 있는 셀을 표식으로 덮지 않는 것은 옳다) 붙여넣기는 격자 안이면 **무조건** 'D'를 요구했다. 그래서 노치 자리가 칠해진 맵 — **M4의 사각 유효 다이 저작 경로가 만드는 바로 그 형태** — 은 복사는 되고 되붙이기는 영구 거부됐다(「회전·면이 다릅니다」라는 원인 무관 사유로). 역방향도 있었다: 값이 진짜 'D'인 셀을 붙여넣기가 표식으로 보고 **조용히 비웠다 — 왕복마다 셀 하나 손실.** 규칙 한 줄로 통일: **지문은 격자 안이고 비어 있는 노치 셀에만 존재한다.**

**모달의 출구가 셋 다 버튼이었다.** 좌표계 선택 모달의 promise에 출구가 버튼 세 개뿐이라, 답하지 않고 떠나면 promise가 **영원히 settle되지 않는다** — 위쪽의 모든 `await openMapFrame(...)`이 pending으로 남고 호출자가 `try`에서 세운 latch의 `finally`가 **절대 돌 수 없다**(`transfer_plan`의 `S.navBusy`: 모든 자재 행이 죽고 아무 말도 하지 않았다). Escape를 capture 단계로 붙였다 — 핵심은 promise가 **항상** settle해서 "버려짐"이 "취소됨"으로 붕괴하는 것이다. **backdrop 클릭은 일부러 배선하지 않았다**(두 선택지를 읽는 중의 오클릭이 결정 도중에 로드를 취소한다).

## 🔴 하네스가 green으로 인용되는 동안 HEAD에서 red였다

F6 하네스의 **주경로 3건이 red였다.** 샌드박스 console 스텁에 `debug`가 없어서, `c24d47b`가 「밀려난 셀 0개」 갈래를 `showToast` → `console.debug`로 바꾼 순간부터 그 경로가 던지고 **내부 오류로 분류**됐다.

즉 **"주경로는 무마찰로 채택된다"는 진술은 그 하네스를 green이라고 인용한 시점에 검증돼 있지 않았다.** red 구간은 `c24d47b`부터 이 커밋까지 — 그 사이에 `01a1353`·`6422326`·`530fdfd`·`e9b3a36`가 지나갔다.

기대값도 함께 교정했다: 밀려난 셀 0개는 **토스트가 아예 없는 것**이 출하된 [1e] 계약이다.

## 회전은? — 기제는 실재하고 모집단이 0이었다

같은 축을 회전에 대해서도 확인했다. `getWaferBoundingBox`는 `getTransformedPhysicalConfig(rotation, side)`를 쓰고 그것이 chipX/chipY를 스왑하므로, **비등방 칩에서는 90/270에서 bbox의 종횡이 뒤집힌다** → `minC`/`minR` 항이 달라지고 **순수 회전만으로도 저장 좌표가 움직인다.** 기제는 그대로 재현됐다.

그런데 **선언된 179개 맵 중 회전 의존 bbox 원점을 보이는 것은 0개**다(총괄 라이브 실측). 즉 실재하는 기제이면서 **모집단이 0**이다.

운영자가 실제로 보는 것은 다르고 더 단순하다: **원점 마커는 화면 위치를 표시한다.** 하이라이트 판정이 `getVisualCoords(...)`의 결과를 `(startX, startY)`와 비교하므로, 회전마다 **서로 다른 다이 네 개**에 앉는다 — 등방 맵도 마찬가지다.

## 검증

- F6 하네스 **121 assertion, 변이 17/17 red**.
- 왕복 하네스 **77 assertion, 변이 18/18 red**.
- 계약 4종, 발산 0.
- 서버 스위트는 이 커밋과 무관하다(클라 전용). 소급 확인 — HEAD에서 `conda run -n assy_manager python -m pytest server/tests/` **1398 passed / 3분 38초**.

## 그때 남아 있던 것

- **152개 맵의 붙여넣기 왕복이 이 거부로 사라진 상태다.** 커밋 메시지가 "format follow-up is queued, not optional"이라고 적었다 — 그 후속은 이 커밋 시점에 착지하지 않았다.
- **채택은 셀이 있는 맵에서 여전히 불가능하다.** 재키잉이 이 커밋에 없으므로, 사용자에게 안내되는 경로는 "격자 크기를 맞춘 뒤 📂 Load로 다시 불러오기"다.
- 같은 라운드에서 트리에 함께 들어온 것들 — STACK 마커 경계 갱신(F4의 형제) · 자녀 수와 어긋날 track 수가 없는 flex `.tp-v-l1` · `S.navBusy` 블록 클릭 사유 + 프레임 모달 Escape 출구 · 기존 `.split-resizer`를 재사용한 사이드바 스플리터(폭 영속화, 더블클릭으로 기억 삭제) — 는 **하네스·파싱 검증만 됐다.** 브라우저 E2E는 P0 작업에 밀려 수행되지 않았고, 커밋도 그렇게 주장하지 않았다.
- `--plan-sidebar-w` 하한·상한(380/760)은 CSS가 소유하고 JS는 계산된 값을 읽는다 — 같은 수를 두 곳에 적지 않기 위해서다. `main.js`의 드래그 블록은 `initEventListeners` 안 클로저이고 `#main-split-resizer`·`state.gridApi`에 묶여 export되지 않아 **호출하지 못했다**(그 파일은 client-pm 소관이라 추출 리팩터를 넣지 않았다).
- `dist` 번들이 함께 커밋됐다.
