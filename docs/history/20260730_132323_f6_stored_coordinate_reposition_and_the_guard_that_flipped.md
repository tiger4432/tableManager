# F6 — 치수는 참조 맵이 이기고, 저장 좌표는 한 개도 움직이지 않는다 (그리고 가드가 방향을 바꿨다)

> **일자:** 2026-07-30 13:23 | **커밋:** `7873070` | **담당:** Map PM | **검수 등급:** T2
> **대상:** `client2/src/map_editor.js`(+205/−…) · `client2/tests/valid_die_frame_adoption_harness.mjs`(+285/−…) · `client2/tests/reposition_regime_probe.mjs`(신규 174줄)
> **선행:** 격자를 참조 맵 크기로 여는 `73b5925` · P0-1 가드를 세운 `ae2811c` · 홀짝 편향 부존재를 측정한 `ddfffc9`
> **보드:** `82114da`(F6·1ⓗ 종료 처리) — 그 판단 근거는 거기에 있고 여기서 복제하지 않는다

## 배경 — 앞 커밋의 가드는 **반대 방향**을 지키고 있었다

`ae2811c`(P0-1)는 "셀이 들어 있는 맵에서는 채택하지 않는다"를 세웠다. 근거는 옳았다:
치수가 바뀌면 `getVisualCoords`의 bbox 항(`− box.minC`)이 바뀌고, 같은 물리 키가 **다른 x/y로
직렬화**된다. 화면은 멀쩡하고 대비 관문은 0을 보고하는데 `replace_map`이 밀린 좌표를 쓴다.

사용자가 설계를 확정하면서 불변식이 뒤집혔다 — **원을 유지하고, 회전·면은 현재 메타데이터에서,
치수는 참조 맵에서 가져오고, 기존 셀은 원점에 맞춰 옮긴다.** 즉 보존 대상이 "화면 위치"에서
"저장 좌표"로 바뀐다.

```
before : 화면 c_old,  저장 x = c_old − minC_old + startX
after  : 저장 x 보존  ⇒  c_new = c_old + (minC_new − minC_old)
```

**그래서 저장 좌표의 의미가 바뀌지 않는다.** (5,7)에 있던 셀은 여전히 (5,7)이고 캔버스가 그
셀 주위로 커졌으니 화면 위치만 움직인다. 마이그레이션도 재해석도 없다 — P0-1이 막던 손상은
**원리적으로** 일어날 수 없게 된다.

**다이가 보존되는 데는 구조적 이유가 있다.** 저장 좌표는 이미 웨이퍼 상대다 —
`− box.minC` 항이 정확히 그것을 산다. 원이 격자에 온전히 들어가 있으면
`minC == (vC−1)/2 − R/chipX`이므로 저장 x는 "웨이퍼 원 왼쪽 끝에서 몇 칸"이고 격자 치수와
무관하다. **bbox 규약이 값을 하는 유일한 자리**다.

## 변경 — 새 변환은 한 줄도 없다

`storedCoordRepositionPlan(fromFrame, toFrame)`이 쓰는 것은 기존 프리미티브
`dbCoordsByPhysKey` 하나다. 한 프레임에서 `물리 키 → 저장 좌표` 사상을 만들고, **새 프레임의
같은 사상을 뒤집어** `저장 좌표 → 물리 키`로 쓴다. 재배치는 두 사상의 합성일 뿐이다.

```js
const before = dbCoordsByPhysKey(fromFrame);
const after  = dbCoordsByPhysKey(toFrame);

const keyByCoord = new Map();
let collision = '';
after.forEach((coord, key) => {
  if (keyByCoord.has(coord)) { if (!collision) collision = coord; return; }
  keyByCoord.set(coord, key);
});
```

**패리티 공식으로 유도하지 않는다.** 답은 새 프레임의 상(image) 안에 실제로 그 좌표가
있는지를 **키 단위로 물어서** 나온다. 그것이 이 도메인이 존재하는 이유("조용히 틀린 값")를
피하는 유일한 방법이고, `ddfffc9`가 산술 추론으로 한 번 틀린 뒤에 정해진 규율이다.

계획과 적용은 **일부러 둘로 쪼개져 있다.** 거절 경로에서 캔버스가 한 글자도 바뀌지 않아야
하므로, 계획은 채택 **전에** 세우고(두 프레임을 인자로 받는 순수 계산이라 가능하다)
적용은 격자가 새 치수로 열린 **뒤에** 부른다.

```js
const plan = storedCoordRepositionPlan(currentFrame(), adoptedFrameOf(refFrame));
if (plan.unrepresentable.length > 0 || plan.stranded.length > 0 || plan.collision) { /* refuse */ }
const wouldHaveMoved = adoptionCoordinateCost(refFrame);   // 효과를 주장이 아니라 측정값으로
adoptFrameSpec(refFrame);
...
applyStoredCoordReposition(plan);
```

**연관 캐시가 함께 움직인다** — `gridData`·`serverCellKeys`·`loadedFCells`. 하나만 옮기면
`serverCellKeySet()`이 옛 키로 대조해 서버가 보낸 셀을 '보낸 적 없음'으로 읽고, 정리 제안이
살아 있는 행을 지운다. 서버가 보낸 키는 **실재하는 행**이므로, 그 좌표를 새 프레임이 만들지
못하면 값 있는 셀과 **같은 등급으로** 거절 사유가 된다(`replace_map`이 그 행을 지운다).

빈 값 셀은 옮기되 표현 불가일 때 거절 사유가 되지 않는다 — 빈 값은 나르는 것이 없다.

## 가드는 살아남았고 판정 기준이 바뀌었다

이제 "좌표가 움직이는가"가 아니다 — 이 절 뒤로 좌표는 **정확히 보존되거나 아예 보존 불가**
둘뿐이므로, 가드는 **표현 가능성**으로 거절한다.

**그리고 그 가드는 실데이터에서 살아 있다**(커밋이 측정한 값):

| 대상 | 참조 | 결과 |
|---|---|---|
| `4MAIN_TRIM` | 29×25 | 저장 좌표 **11개**가 새 프레임의 상에 없음 → 거절 |
| `4MAIN_TRIM` | 27×21 | **53개** → 거절 |
| `AAA` | `4B13` | **22개** → 거절 (실표본 포함) |

측정한 다섯 쌍 중 둘은 깨끗하게 채택·재키잉된다. **죽은 것이 증명된 가드는 없는 가드보다
나쁘다** — 그 판정을 위해 거절 갈래가 실데이터에 도달함을 먼저 보였다.

알림도 갈래를 얻었다. 셀을 실제로 옮겼으면 **말한다**("저장된 좌표를 그대로 유지한 채 화면
위치만 옮겼습니다 … 재배치가 없었다면 N개가 밀렸습니다"). 옮긴 것이 0개면(빈 맵) 종전 [1e]
계약대로 침묵한다 — 아무것도 일어나지 않은 일에 토스트를 붙이지 않는다.

## 🔴 내가 경고한 두 국면은 이 데이터에서 구조적으로 도달 불가였다

주석은 등식이 깨지는 두 국면을 적어 두었다 — ① **절단**(격자가 원보다 작아 `minC`가 0으로
clamp되면 저장 x가 캔버스 끝을 가리킨다) ② **패리티**(`minC`는 정수인데
`(vC−1)/2 − R/chipX`는 아니어서 격자 홀짝이 바뀌면 반 칸 잔차가 남는다).

`reposition_regime_probe.mjs`가 **선언된 `bonding_map` 프레임 14개 전체**를 실측했다:
모든 bbox가 `(2,2,…)`로 — clamp된 0이 **한 번도** 나오지 않고 — 모든 패리티 항이 정수였다.
이유는 기하 자체에 있다. `applyPhysicalGeometry`가 `cols = ceil(2R/chip) + 2`로 유도하고
홀수로 강제하므로, `+2`가 원이 가장자리에 닿지 않음을 보장하고 홀수 강제가 반 칸 항을
정수로 만든다.

**즉 `4B12`의 y축이 원에 잘린다는 내 경고는 틀렸다.** 두 국면에 도달하려면 유도값에서
손으로 격자를 줄여야 하고 선언된 맵 중 그런 것은 없다. 그래도 픽스처 C가
45×45 → 46×46(**홀수 → 짝수**)로 잡혀 있어 패리티 경로는 어쨌든 채점된다.

## 검증 — 이 항목을 쓰며 HEAD에서 다시 돌렸다

```
node client2/tests/valid_die_frame_adoption_harness.mjs           → 148 assertion, 0 실패
node client2/tests/valid_die_frame_adoption_harness.mjs --mutate  → 변이 22/22 red
```

커밋이 주장한 수와 일치한다. 신규 변이 9건에는 **이 결함을 원리적으로 볼 수 없는 단위 둘**이
들어 있다 — 물리 키로 잰 비용, 그리고 자기 자신과 비교되는 계획.

하네스 실측이 남긴 대조가 셋 있다.

- **F6/C** 45×45→46×46(동일 물리 규격): 재배치 없이는 **1272개**가 밀리고 41개가 사라진다.
  재배치 후 **2025개 저장 좌표가 바이트 단위로 보존**되고 2025개 화면 위치가 다시 유도되며
  `serverCellKeys` 40개·`loadedFCells` 5개가 함께 이주했다.
- **F6/D** 45×45→47×47(직경 320): 채택되고 **하나도 움직이지 않는다** — 치수가 달라도 허용되는
  음성 대조.
- **F6/E** 33×25 ← 29×25(`4MAIN_TRIM` 형상): 825셀 중 725개는 옮길 수 있는데 **100개**의 저장
  좌표에 새 프레임의 칸이 없다 → 거절, 아무것도 바뀌지 않음.

브라우저 E2E는 격리 스택에서 **모든 비-GET을 가로챈 상태로** 돌았다. `Q1 ← 4B13`에서 Push
페이로드를 통째로 잡아 셀이 채택 전후 `-2,-9=elle`로 **바이트 동일**하고 메타데이터가
`grid_start_x: -10, rotation: 0, side: back`을 유지함(원점·회전·면은 채택하지 않음,
`INV-F6-4` 유지)을 확인했다. 양쪽 DB 모두 수정 행 0, 운영 `assy_manager`는 건드리지 않았다.

## ⚠️ 커밋 메시지가 자기 diff보다 넓게 주장한 자리

메시지 마지막 절이 이렇게 적혀 있다 — *"Also in this commit: the five items from the earlier
round all survived the frame-authority revert — the STACK marker-boundary refresh, the flex
`.tp-v-l1`, the dead-CSS removal, the `S.navBusy` blocked-click reason with an Escape exit,
and the sidebar splitter with a persisted width."*

**이 커밋의 diff에는 그 다섯 중 아무것도 없다.** 만진 파일은 `map_editor.js`와 하네스 둘,
합쳐 세 개다. `transfer_plan.js`·`transfer_plan.css`·`main.js`·`map_editor.html`은 이 커밋에
없고, 다섯 항목은 모두 **`ae2811c`에서 이미 착지했다**(그 기록은
`20260730_101144_p0_adoption_coordinates_and_paste_fingerprint.md`에 있다).

읽을 수 있는 뜻은 "되돌림으로 잃지 않았다"이고 그것은 사실이다. 문장이 주장하는 "이 커밋에
들어 있다"는 사실이 아니다. 1ⓗ 사이드바 스플리터도 마찬가지다 — 보드(`82114da`)는 그 행을
F6과 함께 닫았지만, **코드는 `ae2811c`에 있다.** 기존 `.split-resizer` 기계장치를 재사용했다는
서술은 그 커밋에 대해 참이다.

## 그때 남아 있던 것

- **거절 경로는 실데이터에서 살아 있다** — `4MAIN_TRIM`을 29×25/27×21 참조로 여는 조작은 이
  커밋 시점에 여전히 거절되고, 안내되는 우회로는 "격자 크기를 맞춘 뒤 📂 Load로 다시 불러오기"다.
- **코드맵의 F6 채택 블록은 "재측정 필요"로 표시된 상태다**(`b132091`) — 그 커밋이 측정한
  in-flight 트리에 이 커밋의 함수 둘이 아직 없었기 때문이다.
- 재배치는 `boundingBoxCache`를 스스로 비운다. `adoptFrameSpec`도 비우지만 두 곳이 서로의
  부수효과에 기대지 않도록 중복을 남겨 두었다.
- `client2/dist`는 이 커밋에 없다 — 같은 시각 공유 트리에 다른 라운드 둘의 작업이 함께
  있었다(`77a2c15`의 같은 판단).
