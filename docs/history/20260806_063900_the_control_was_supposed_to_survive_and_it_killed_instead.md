# 대조 변이는 살아남기로 돼 있었는데 죽었다 — 그리고 그 죽음이 픽스처가 무력하지 않다는 증거다

> **커밋:** `f11c56c`(2026-08-06 06:39 · **stage 5**) | **일자:** 2026-08-06 아침
> **선행:** [`20260806_001049`](./20260806_001049_the_forwarding_check_sees_the_half_thread_that_changes_nothing_and_therefore_survives_review.md)(`5cba0a1` — stage 4)
> **후속:** [`20260806_081218`](./20260806_081218_the_control_mutant_became_inexpressible_and_that_is_what_ended_the_refactor.md)(S2.2~S2.7 — **이 대조가 표현 불가능해지면서 리팩터가 끝난다**)
> **담당:** map 구현(에디터) · 총괄(기대값을 틀리게 물려준 쪽)
> **대상:** `client2/src/map_editor.js`(+53 / −32) · 하네스·프로브 14종(`valid_die_origin_alignment_harness.mjs` +43 / −21 · `m4_symbol_extractability_probe.mjs` +30 / −15 · `map_key_canonical_harness.mjs` +13 / −10)
> **스위트:** 커밋 메시지 기준 **`getWaferBoundingBox`의 바인딩 읽기 0**, 전환된 피호출자 다섯 전부 인자 수신. ⚠️ 게이트 총수는 이 커밋도 적지 않았다.

## 배경 — 두 함수가 프레임을 받는다

`isValidDieAt`과 `getWaferBoundingBox`. 직접 바인딩 독자 **9 중 4** 전환.
`getWaferBoundingBox`는 이제 **0개를 들고 있다** — **상자 단락도 캐시 태그도** 인자를
읽는다.

```js
-function getWaferBoundingBox(rotation, side, opts) {
+function getWaferBoundingBox(frame, rotation, side, opts) {
+  if (frame === undefined) {
+    throw new Error('getWaferBoundingBox: frame argument missing. Pass the frame that is in '
...
-  if (physFrameOverride && physFrameOverride.box && !(opts && opts.circleOnly)) {
-    return physFrameOverride.box;
+  if (frame && frame.box && !(opts && opts.circleOnly)) {
+    return frame.box;
```

## 🔴 이 커밋에서 읽을 값어치가 있는 것은 대조 결과 하나다

이전 **네 단계 전부**에서 **「인자 대신 바인딩을 읽는다」 변이가 살아남았다.**
그리고 **그것이 옳았다** — 하네스들이 여전히 샌드박스 전역을 몰고 있었으므로
**바인딩과 인자가 같은 값을 실었다.** 같은 값을 읽으면 답이 안 바뀐다.

이 단계가 **창을 모는 하네스 셋을 프레임을 넘기고 대입을 그만두도록** 바꿨다.
그래서 이 함수에 대해 **바인딩이 죽었고, 이제 그것을 읽으면 다른 답이 나온다.**

```js
    // The frame is an ARGUMENT now, so the window IS the argument. `withPhysFrame` would
    // still set the binding, but `getWaferBoundingBox` no longer reads it -- wrapping the
    // call would leave this check driving state nothing consults, i.e. inert and green.
```

> **그래서 대조가 죽는 것이 그 픽스처들이 무력하지 않다는 증거다.**
> 여기서 살아남았다면 그것은 **인자가 장식이고 픽스처가 여전히 상태를 몰고 있다**는
> 뜻이었다.

## ⚠️ 그리고 그 기대값을 틀리게 물려준 것은 나였다

레인이 **총괄의 기대값을 이 단계가 바꾼 것에 대고 다시 유도하지 않고 그대로 들고
갔다.**

> **그 기대값은 네 단계 동안 맞았고, 그것을 안 맞게 만든 바로 그 단계에서 안 맞게
> 됐다.**

「살아남아야 한다」는 **관측이 아니라 앞 단계에서 물려받은 예측**이었다. 예측이
관측처럼 실려 왔다.

## ① 앵커 여섯이 다시 겨눠야 했고, 계획은 다섯이라고 했다 — 그리고 둘은 드리프트가 아니었다

**둘은 레인 자신의 일괄 편집이 망가뜨린 것**이다. 화면 경로 일괄 패스가 함수 이름을
**호출 지점만이 아니라 앵커 *문자열* 안에서도** 다시 썼다.

둘 다 즉시 잡혔고 **서로 다른 기구가** 잡았다.

| | 무엇이 잡았나 | 언제 |
|---|---|---|
| ① | **두 단계 전에 만든 가드** — 스윕 전에 exit 2로 거절 | 즉시 |
| ② | 스윕의 생존자 회계 | **늦게, 그리고 오분류된 채로** |

②가 늦게 잡혔다는 사실 때문에 **그 코퍼스가 이번에 경화됐다.**

> **드리프트를 위해 만든 가드가 자기가 유용하리라고 계획이 예측한 바로 그 단계에서,
> 드리프트가 아니라 자해 편집을 잡았다.**

## ② 존재도 유일성도 없던 코퍼스 둘 — 발명하지 않고 **입양했다**

```js
function once(src, find, repl) {
  const i = src.indexOf(find);
  if (i < 0) die(`mutation anchor not found: ${find.slice(0, 80)}`);
  if (src.indexOf(find, i + 1) >= 0) die(`mutation anchor is not unique: ${find.slice(0, 80)}`);
  return src.slice(0, i) + repl + src.slice(i + find.length);
}
```

**트리에서 가장 오래 이것을 들고 있던 코퍼스**(`geometry_origin_reseat_harness.mjs`)의
검사로 모든 변이를 통과시킨다. **네 번째로 발명하는 대신 입양했다.**
라이브로 증명: **일부러 낡힌 앵커가 exit 2에서 nothing-compared를 낸다.**

## ③ 운영 메모 하나 — 시간 초과한 스윕은 스스로 복원하지 않는다

변이 러너가 스윕 도중 **시간 제한에 걸려 트리를 변이된 상태로 남겼다.**
**md5 검사가 잡았고 바이트 스냅샷이 복원했다.**

## ④ 어느 문장이 거짓이 됐는지도 내가 틀렸다

**「두 인자가 같은 모양을 공유한다」고 주장한 주석은 없었다.** 거짓이었던 텍스트는
**그 위 문단**이었고, **함수가 더 이상 읽지 않는 바인딩**을 서술하고 있었다.
정정하면서 **두 관례가 서로에게 읽히지 않도록 대비를 명시로 적었다.**

## 그때 남아 있던 것

- 이 시점 전환된 것은 **9 중 4**다. `frameChosenFrom` · `withPhysFrame` ·
  `seatingSnapshot`을 포함한 나머지는 뒤 단계의 것이다.
- **대조 변이는 여전히 표현 가능하다** — 읽을 바인딩이 아직 있다. 그것이 표현
  불가능해지는 것이 이 리팩터의 완료 기준이고, 그 자리는 `62520b9`다.
- stage 4가 보드에 올린 **포워딩 검사의 게이트화**는 이 커밋에도 없다.
