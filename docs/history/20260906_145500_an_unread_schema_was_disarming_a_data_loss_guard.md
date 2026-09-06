# 못 읽은 스키마는 «화면을 비운» 것이 아니라 «데이터 손실 가드를 해제»하고 있었다

> **커밋:** `b77d4abf` (14:55)
> | **일자:** 2026-09-06
> **레인:** 구현자(클라)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**

## 무엇이 일어났나

`confirmLogShapedPushTarget` 은 `replace_map` 이 «맵 계약 밖의 컬럼»을 파괴하는 것을 막으려고
있다. 그런데 그 판정에 «실패 응답 본문»을 먹이면 —

```
logShapedPushDecision({detail: 'Internal Server Error'}, 'x','y','val')
    -> {"mode":"clean","extras":[]}          <- 🔴 「깨끗하다」고 답하고 push 가 «나간다»
logShapedPushDecision({columns:['x','y','val','note','owner']}, 'x','y','val')
    -> {"mode":"block","extras":["note","owner"]}
```
🔴 **즉 읽기 하나가 떨어지면 «빈 화면»이 그려지는 것이 아니라, «데이터 손실 가드가 해제»된다.**
그리고 그것이 «쓰기가 출발하는 상태»다.

## 🔵 그래서 이 셋이 나머지 다섯보다 «등급이 높다»

같은 `res.ok` 부류의 여덟 중, 이 스키마 셋은 결과가 «화면»이 아니라 «쓰기»에 있다.
그 판정이 «읽어서»가 아니라 «돌려서» 나왔다 — 위 두 줄이 그 실행이다.

```
🔵 「없어서 0」과 「무해해서 0」을 가르는 자리이기도 하다 —
   extras 가 «비었다»는 「추가 컬럼이 없다」가 아니라 「«물어보지 못했다»」였다
```

## 확인한 것 (diff 실측)
```
client2/src/api.js +3 · client2/src/map_editor.js +9
client2/tests/virtual_column_render_harness.mjs +7  (하니스가 그 갈래를 재기 시작한다)
```
📎 큐 등급 0 «L-6». 🔵 이 줄은 「실패하는 것이 무해한 것은 아니다」의 실물이다 —
   거절이 «가만히 있는» 것이 아니라 «가드를 끈다».
