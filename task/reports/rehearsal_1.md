# 리허설 1 회차 · 10-12 새벽 (판 6d8fb50ea)

```
남은 실패 수     2 — C2 여백 · C3 Long 기록 합침 (둘 다 총괄이 «맞는 실패»로 받음, 고침 대기)
통과한 마지막 판  없음 (이 판은 실패 2) · 앞 회차 0 은 dist 8bb437718 에서 누른 단계만 통과
판              18766 = origin/main 6d8fb50ea 의 server/ 전부 + client2/dist (스크래치 줄 1 만 다름)
                기동 03:11 «[Schema] no drift» · 기동 뒤 오류 0 · 번들 walk-B-XJXTJ5.js
도구            앱 내장 브라우저 · 실제 마우스 클릭 · 글자 입력. 셀렉트(Type · collect)와 Limits 칸 · through 체크만 폼 입력
                ref 클릭은 요소를 화면 안으로 끌어와 스크롤을 바꾼다 — 스크롤을 재는 단계는 좌표 클릭
스크린샷         못 찍음 (창이 그리지 않아 시간 초과) · «본 것»은 화면 글자(innerText)와 DOM 너비에서 읽음
```

| 단계 | 누른 것 | 기대(대본) | 본 것 | 판정 |
|---|---|---|---|---|
| C1 창 | + Add start → Type wafer → «SYN-BW-103» → 목록 SYN-BW-103-11 마우스로 | 창 안 닫힘 | 창 열림 · 칸 SYN-BW-103-11 | 통과 |
| C1 결과 | + Positive · SYN-BW-SPL-400-19 − Negative · collect wafer · Walk (default) | «+ 1 · − 1 → wafer» · 32 · 1650 · wafer 32 | 요청 `id · positive · negative · node_limit=1000 · collect=wafer` · «Nodes 32 (collect: wafer) · Edges 1650 (all) · 1.1 s» · wafer · 32 | 통과 |
| C2 폭 | Wide 146 열 | 노드 한 폭 · 값 같은 폭 | 체크 44 · 노드 176 · 값 96 이 144 | 통과 |
| C2 여백 | 열마다 가장 넓은 글자 ÷ 열 폭 | 0.5 이상 | 값 열 144 중 0.5 아래 138 (0.25 아래 48) · 가장 큰 값 0.71 | **실패** |
| C2 잘림 | 칸 안 글자 scrollWidth > clientWidth | — | 노드 칸 31 (길 줄 «in_container → bonded_from → in_container» 319 px / 161 px 말줄임, 키는 다 보임) · 값 · 머리 0 | 통과 (총괄: 키가 보이면 통과) |
| C2 동작 | ① 판: 가로 스크롤 · 체크 둘 · 정렬 · 거르기 / ③ 판: Add here · 그 × / 400 판: More | 전후 1 px 도 같음 | 매번 바뀐 열 0 (More 의 × 뒤는 안 잼) | 통과 |
| ③ | collect + quantity · 세상 칩 appdemo_vf → default | 81 · 1668 · quantity 49 | default 칩에서 저절로 다시 걸음 · «Nodes 81 (collect: wafer, quantity) · Edges 1668 (all) · 1.0 s» · quantity · 49 | 통과 |
| C3 Long | ③ 판 Long | + 칸 · − 칸 따로 · 기록 수 = 답 | 칸 따로 · 518 줄 · SYN-CW-001-02 + 21 · − 0 — 답은 measures 21 엣지 · 기록 22 (time_s 의 ETCH 90 · 19:32 이 빠짐, CLEAN 300 만) | **실패** |
| C4 More | + SYN-BW-103-11 만 · collect 없음 · node_limit 400 · default → More | 800 · 구역 = 새 답의 타입 수(최대 200) · × 로 되돌아감 · Types 타입이 다 구역에 | 400 판 «Nodes 400 · Edges 437» · «Cut · nodes 400 More» · 구역 = Types(defect 188 · die 179 · quantity 32 · wafer 1). More → 요청 하나 node_limit=800 · «Nodes 738 · Edges 1538» · 잘림 없음 · 구역 wafer 31 · die 200(461) · quantity 46 · defect 199 · defect_kind 1 · 칩 +30 · +21 · +14 · +11 · +1 from More · × → 400 판 그대로 · 새 요청 0 | 통과 |
| C5 바구니 | 결과 300 px 내려 행 체크(좌표 클릭) · 맨 아래(1302)로 | 스크롤 그대로 · +1 · 바구니 보임 | 300 그대로 · Marked · 1 → 2 · 바구니 sticky 589 ~ 691 px (창 720) | 통과 |
| C6 Add here | ③ 판 local_gap 체크 → «measures ← wafer» Add here → × | 32 → 132 → 32 | 요청 하나 `hops=1 · follow=measures · collect=wafer · direction=both` · wafer · 132 · «+100 from walk on · measures ← wafer» · 길 «measures · via shared local_gap» · × → 32 · 새 요청 0 | 통과 |
| C8 | + SYN-BW-103-11 · collect wafer · through in_container + bonded_from · default | 코어 웨이퍼 · 엣지 · claims · 잘림 | 요청 `follow=bonded_from · follow=in_container · collect=wafer` · «Nodes 31 (collect: wafer) · Edges 461 (all) · 0.5 s» · 코어 웨이퍼(SYN-CW) 30 · 3 홉 · claims_scanned 464 · 잘림 없음 | 통과 |
| 복사 | SYN-CW-001-02 칸의 Copy key | 보이는 키 | text/plain «SYN-CW-001-02» · 단추 title «Copied» | 통과 |
| 소유자 7 | 창 닫힘 · 꿀렁임 · 너무 넓음 · Types 불일치 · More +0 · 체크 스크롤 · 스티키 바구니 | — | 통과 · 통과 · **실패(C2 여백)** · 통과 · 통과 · 통과 · 통과 | 실패 1 |
| C7 · 공백 | 고리 · 그림 칸 · 세상별 Re-translate · 초안 보기 200 · 모델링 백필 → 걷기 · 공백 값 | — | 아직 | — |
