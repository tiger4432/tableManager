# 지시서 — F-19 「같은 맵을 두 화면이 다르게 부른다」의 «읽는 쪽»

> 총괄 판정 29(변수 가름) · 32(나르개 ㉡) 이행. **작성: 응용 레인. 코드 0줄.**
> ⛔ 토큰(`GEOMETRY_CONFIRMED`)을 «가르지 않습니다» — 판정 29 가 막았습니다
> (`map_alignment.py:516·4751` 이 그것을 «신뢰 토큰»으로 읽어, 건드리면 정렬 동작이 움직입니다).

## 닫으려는 «한 문장»
> **같은 맵을 오버레이는 「확정됨」이라 그리는데 확정 워크리스트는 「pending」이라 그립니다.**
> 표지를 «찍은 것»과 확정 «행»을 만드는 것이 다른 경로이기 때문입니다. 오류는 «안 납니다».

## 이미 서 있는 것 (다시 짓지 마십시오)
```
서버   map_overlay.orientation_declaration 의 축 dict 가 `confirmed_by_person` 을 «답니다»
       (83e86115). 표지 안에 `confirmation_uid`(확정 «행»의 열쇠)가 있으면 참입니다.
       사람 경로만 그것을 싣고(frame_confirmation.py:638), 체인 맵퍼 둘은 «안 싣습니다»
       (dt_alignment_metadata_mapper.py:203 · core_alignment_mapper.py:221)
🔴 그런데 그 칸이 «클라에 안 닿습니다» — 아래 ①이 그 구멍입니다
```

## ① 나르개 — `maps[]` 에 «불리언 한 칸»  (서버)
```
어디    map_alignment.py:1060  axes = {"rotation": rot["source"], "side": side["source"]}
        -> 여기서 `confirmed_by_person` 이 «떨어집니다». 축 dict 에서 source 만 골라 담습니다
무엇    맵별 응답(`maps[]`, 지금 `declared_frame_source` 를 싣는 그 행)에 «불리언 하나».
        이름이 「사람이 확정했나」로 읽히게 (예: `frame_confirmed_by_person`)
🔴 «한 칸»입니다   dict 아님 · 사유 문자열 아님 · 사람 이름 아님
```
🔵 **`map_alignment.py:6057` 의 주석이 이 모양을 «지시»합니다** — 그 주석이 막는 것은
   「맵마다 «축 dict»」이고(40맵에서 6.5KB -> 11.2KB, +72%), 마지막 줄이 「어느 맵인지는
   `maps[].declared_frame_source` 가 이미 말한다」고 «맵별 사실의 자리»를 지목합니다.
⛔ `axis_sources` 집계는 «그대로» 두십시오. 그건 단위 수준이고 F-19 는 «맵 단위»라 안 닫힙니다.

## ② 읽는 쪽 — `client2/src/map2/**`  (클라·맵)
```
자리    map2/decode.js:386   `declaredFrameSource` 를 푸는 그 줄 «옆»
        map2/main.js:2249    confirmed_candidate_id = declaredFrameSource === CONFIRMED ? … : null
무엇    「확정」 배지를 «사람이 확정한 맵»에만 답니다.
        체인 표지 맵은 배지를 «안 답니다» — 프레임 «값»은 그대로 그립니다(값은 참입니다)
```
🔵 **그릴 자리가 «이미 있습니다»** — `main.js:2241-2247` 주석이 「its own field, read only by
   the label」이라 적어 두었습니다. 새 칸도, 새 화면도 필요 없습니다.
⛔ `stored_candidate_id` 로 접지 마십시오 — 같은 주석이 「그러면 그리는 자리가 옮겨간다」고 적습니다.

## 게이트
```
① 가름     사람 표지 맵 -> 「확정」 배지 «있음» · 체인 표지 맵 -> «없음»
           (두 표본이 «다른 갈래로만» 잡히게 — 같은 답을 내는 표본은 판별식이 아닙니다)
🔴 ② 무회귀  `GEOMETRY_CONFIRMED` 가 «오늘과 같은 맵»에 붙는다 —
           🔴 사람 표지 맵 «과» 체인 표지 맵 «둘 다»로 확인. 한쪽만 보면 못 봅니다
🔴 ③ 페이로드 그 칸이 «불리언»이고 «맵당 하나»다. dict 로 자라면 :6057 이 막는 모양이 됩니다
④ 읽는 쪽   «수»를 보고에 적으십시오 (오늘: `confirmed_by_person` 독자 «0»)
```
🔴 **멈춤** — 화면이 배지를 그리는 자리가 «생각과 다르면» 거기서 멈추고 올리십시오.
   그건 「읽기」가 아니라 「만들기」이고 크기가 다릅니다.

## 안 하는 것
```
토큰 가르기 · axis_sources 확장 · 체인 맵퍼 손대기 · 표지 개명 · 설명 문구
```
