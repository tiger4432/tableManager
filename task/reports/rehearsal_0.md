# 리허설 0 회차 (먼저 누름 — C1 · C6 · C7) · 10-12 새벽

```
남은 실패 수   0 (누른 단계 안에서) · C7 은 고리만 누름, 나머지 넷은 아직 안 누름
통과한 마지막 판  client2/dist = 8bb437718 (걷기 번들 walk-CmqpgvAN.js, 6aba2a1a2 의 창 안 닫힘 포함)
판 상태        ⚠️ 규약의 «server/ 전부 = origin/main» 이 아님 — 18766 의 server/ 는 그동안 갈아 끼운 파일들의 혼합.
               dist 만 main. 1 회차 전에 server/ 전부를 main 으로 갈고 스크래치 줄을 다시 넣는다
도구           앱 내장 브라우저(실제 마우스 클릭 · 글자 입력). 셀렉트 둘(Type · collect)만 폼 입력으로 고름
스크린샷        못 찍음 — 창이 그리지 않아 시간 초과. «본 것»은 화면 글자(innerText)에서 읽음
페이지          walk.html?world=appdemo_vf&world=default (겹친 세상) — 대본 ①은 default 만
```

| 단계 | 누른 것 | 기대(대본) | 본 것 | 판정 |
|---|---|---|---|---|
| C1 창 | + Add start → Type wafer → «SYN-BW-103» 입력 → 목록의 SYN-BW-103-11 을 마우스로 누름 | 창이 안 닫힘 | 창 열림 그대로 · 칸에 SYN-BW-103-11 · +/− 단추 살아 있음 | 통과 |
| C1 칩 | + Positive · 같은 창에서 SYN-BW-SPL-400-19 → − Negative | 칩 생김 | «+1 SYN-BW-103-11 ×» · − 1 | 통과 |
| C1 결과 | collect wafer → Walk | «+ 1 · − 1 → wafer» · Nodes 32 · Edges 1650 · wafer · 32 | «+ 1 · − 1 → wafer» · «Nodes 32 (collect: wafer) · Edges 1668 (all) · 1.0 s» · wafer · 32 | 통과 — Edges 차이는 겹친 세상 URL 탓: 같은 요청을 default 만으로 보내면 32 · 1650 |
| C1 URL | 요청 | 대본 ①의 입력 | `id · positive · negative · node_limit=1000 · collect=wafer · world=appdemo_vf · world=default` 요청 하나 | 통과 (world 둘은 페이지 URL 그대로) |
| ③ | collect + quantity → Walk | Nodes 81 · Edges 1668 · quantity · 49 | «Nodes 81 (collect: wafer, quantity) · Edges 1668 (all) · 1.1 s» · quantity · 49 · wafer · 32 | 통과 |
| C6 Add here | quantity 구역 local_gap 줄 체크 → «measures ← wafer» Add here | 요청 하나 hops=1 · follow=measures · collect=wafer · wafer 32 → 132 · 칩 «+100 from walk on · measures ← wafer ×» · 길 «measures · via shared local_gap» | 요청 하나 `hops=1 · follow=measures · collect=wafer · direction=both` · wafer · 132 · 칩 «+100 from walk on · measures ← wafer×» · 탭 없음 · 길 «measures · via shared local_gap» · base 두 줄 «+ start · − —» 꼴 2 | 통과 |
| C6 × | 칩의 × | wafer · 32 | wafer · 32 · 칩 0 · base 줄 «start» 2 · 새 요청 0 | 통과 |
| C7 고리 | − 칩 · collect 칩 지움 · Limits hops 1 → Walk → Graph | 그려진 노드 48 중 고리 47 | 요청 `id · node_limit=1000 · hops=1` · «Nodes 212 · Edges 249 · 0.3 s» · 그려진 노드 48 · 고리(end) 47 · 범례 «dashed = walked up to here» | 통과 |
| C7 이어 걷기 | 고리 노드 «SYN-BW-103-11 / 2 / 3 / Wafer» 를 마우스로 누름 → «Walk on from here» | 그 노드가 + 바구니로 · 요청 없음 | + 칩 둘(SYN-BW-103-11 · SYN-BW-103-11 / 2 / 3 / Wafer) · 새 요청 0 | 통과 |
| C7 나머지 | 그림 칸 · 세상별 Re-translate · 선언 창 초안 보기 200 · 모델링 브랜치 백필 → 걷기 | — | 안 누름 | 1 회차에 |
