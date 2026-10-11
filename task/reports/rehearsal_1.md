# 리허설 1 회차 · 10-12 새벽 (판 6d8fb50ea → 닫은 판 516319b65)

```
통과한 마지막 판  516319b65 (walk-PGYP5dJ-.js · server/ 는 6d8fb50ea 와 같음) — 시연 직전 되돌릴 판
남은 실패 수     0
                (e) 516319b65: ③ 판 quantity 노드 열 217 px · core_cmp_nonuniform 135/135 · tape_adhesion_anomaly 147/147 · 잘림 0
                    400 판 quantity 201 px · core_cmp_nonuniform 다 보임 · defect 326 px(36ch) · 키 59 ~ 69 자 188 개 말줄임 + title 188
                    (b) 새 기준 400 판 46 열 중 걸림 0 · (a) 0 · (c) 0
                한 가지 본 것: «+ Add start» 창이 열린 채면 그 창이 세상 칩 자리를 덮어 칩을 눌러도 창이 받음 — 창을 닫으면 정상
이전 줄 (0da6617b1 에서 남았던 것) — C2 (e) 노드 키 잘림 · 닫은 판 0da6617b1 (walk-DWbl2RU1.js)
                총괄 판정 뒤: (b) 기준 «열 폭 ≤ max(칸 글자, 머리 몫) × 2» — ① 의 5 쌍은 통과(예 core_cmp_nonuniform 99.4 ≤ 135)
                    400 판 die 구역 2 열(폭 52.6)은 머리 ▾ 단추 + 여백을 머리 몫에 넣어 셈(총괄 판정) → 400 판 46 열 중 걸림 0
                (d) Add here · More 는 새 답이라 다시 정하는 것이 설계 — × 뒤 원래 폭: Add here 147 열 · More 54 열 모두 같음 → 통과
                (e) quantity 21 자 키 둘(core_cmp_nonuniform · tape_adhesion_anomaly) 잘림 → 실패, defect 합성 키(59 ~ 69 자) 말줄임은 정상
                통과: C2 (a) Δ 0 · (c) 노드 열 0 · 정렬 · 거르기 · 체크 전후 0 · Graph 를 Walk 전에 눌러도 요청 = 바
                      fanout 재현(76874c4e9): 고리 → Walk on from here → Walk 의 요청 = 바 · C3 · 공백 값
통과한 마지막 판  없음 (실패 3) · 앞 회차 0 은 dist 8bb437718 에서 누른 단계만 통과
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
| C7 고리 | + SYN-BW-103-11 · hops 1 · default → Graph → 고리 노드 마우스로 → Walk on from here | 48 중 47 · + 바구니로 · 요청 0 | 요청 `id · hops=1` · «Nodes 212 · Edges 249 · 0.2 s» · 그려진 48 · 고리 47 · + 칩 «SYN-BW-103-11 / 2 / 3 / Wafer» · 새 요청 0 | 통과 |
| C7 그림 칸 | 세상 칩 rp500g(default + rp500g) · physical_quantity bond_temp + · Walk | ▣ + 참조 · 그릴 때 /api/image 0 · 머무르면 1 · 미리보기 | «Nodes 3 · Edges 2 · 0.2 s» · ▣ 4 «http://127.0.0.1:18766/favicon.svg» · 0 · 머무름 1 · 미리보기 48 px | 통과 (▣ 눌러 새 창은 안 함) |
| C7 모델링 걷기 | 같은 걷기의 답 | plasma_clean → bond_temp → void | leads_to 둘 (plasma_clean → bond_temp dir down · bond_temp → void dir up) · 둘 다 rp500g 에서만 | 통과 (백필은 앞 라운드에 한 것) |
| C7 ⑪ | 메인 그리드 link_candidates 2 행(마우스 · shift) → Re-translate → Open in admin → 줄 8 | 줄 40 · «40 GROUPS FROM THE GRID» · 폼 넷 | 줄 40 (rp500 · rp500e · rp500f · rp500g × 칸) · 어드민 «Re-translate a ledger scope» 밑 «40 GROUPS FROM THE GRID» · 폼 source=link_candidates · scope_column=phenomenon_key · scope_values=bond_temp,void · world=rp500 | 통과 (실행 안 함) |
| C7 초안 보기 | Ontology Explorer → fake_measures → Edit draft / 브랜치 rp500g → link_candidates → Edit draft | 200 | POST drafts 200 · view 200 «Sources 1 · rows not yet translated 0» / view world=rp500g 200 · authoring/plan world=rp500g 200 «Sources 1 · rows not yet translated 1» | 통과 |
| 공백 값 | 메인 그리드 trd_txt 행 T3 value 를 더블클릭 → «a  b»(공백 둘) → Apply → 그 행 Re-translate «default · trd_txt_src · event_id» → 실행(run_queued_once) → 걷기 wafer TRD-W-001 + | 공백 둘이 그대로 보임 | 실행 ok · withdrawn 2 · inserted 2 · 걷기 «Nodes 19 · Edges 18» · 노드 칸 «a  b» (white-space: pre · 21.2 px, 공백 하나면 18.1 px) · 끝나고 «4.5» 로 되돌리고 다시 번역 ok | 통과 |
| C2 다시 (6f64c525f) | ① 판 다시 | 열마다 가장 긴 글자 ÷ 열 폭 ≥ 0.5 | 노드 185.4 · 값 76 이 129 · 91.6 이 15 · 잘림 0 · 0.5 아래 53 (Δ 48 «—» 만 · − 5) — + · Δ · − 같은 폭 규칙 탓 | **실패** → 총괄 기준 a ~ e 로 다시 |
| C3 다시 (6f64c525f) | ③ 판(세상 칩 vf → default) → Long | 기록마다 한 줄 | «Nodes 81 · Edges 1668 · 1.2 s» · Long 571 줄 · SYN-CW-001-02 22 줄 · + 22 · − 0 · time_s 두 줄(CLEAN 300 · ETCH 90) | 통과 |
| Walk on from here 뒤 Walk | default · + SYN-BW-103-11 · hops 1 → Graph → 고리 노드 마우스로 → Walk on from here → Walk | 바의 상한대로 요청 | 바 «Limits · hops 1» (hops=1 · node_limit=1000 · fanout 빈칸) · 요청 `id · positive · positive · fanout_limit=20 · world=default` (hops · node_limit 빠지고 fanout 20 붙음) · «Nodes 42 · Edges 62» | **실패** → 76874c4e9 에서 통과 |
| fanout 다시 (76874c4e9) | 같은 순서 | 요청 = 바 | 첫 Walk `id · node_limit=1000 · hops=1` «Nodes 212 · Edges 249» · 고리 뒤 Walk `id · positive · positive · node_limit=1000 · hops=1` · fanout 없음 · «No walk yet» 없음 | 통과 |
| Graph 먼저 (0da6617b1) | ① 바를 채우고 Walk 전에 Graph | 요청 = 바 | `id · positive · negative · node_limit=1000 · collect=wafer` · 그래프 «Nodes 32 · Edges 0» | 통과 |
| C2 (a ~ e) (0da6617b1) | ① 판 Wide | a Δ · b + · − 넓은 쪽 · c 노드 · e 잘림 | 열 98 (Δ 가 전부 «—» 라 안 그림) · 노드 185.4 · a 0 · b 5 쌍(core_cmp_nonuniform 0.45 · place_accuracy_um · post_bond_queue_h · surface_oxidation · tape_adhesion_anomaly 0.49 — 이름 몫 99 ~ 107 px, 칸 글자 «missing» 44.7 px) · c 0 · e 0 | **b 실패** |
| C2 (d) (0da6617b1) | ① 정렬 · 거르기(«wafer · 2 of 32») · 행 체크(좌표, 스크롤 300 그대로 · Marked 1) | 전후 같음 | 바뀐 열 0 · 0 · 0 | 통과 |
| C2 (d) Add here | ③ 판 local_gap 체크 → measures ← wafer Add here → × | 전후 같음 | 32 → 132 · 열 이름으로 대조: 기존 147 중 3 열 폭이 바뀜(quantity 구역 «wafer measures ← · value» + · − 83.8 → 99.4, Δ 76 → 52.6) · Δ 21 열 새로 · × 뒤는 원래와 같음 | **실패** |
| C2 (d) More | + SYN-BW-103-11 · node_limit 400 · default → More | 전후 같음 | 요청 하나 node_limit=800 · «Nodes 738 · Edges 1538» · 구역 = Types · 기존 54 열 중 1 열 폭이 바뀜(81.6 → 83.8) · 14 열 새로 | **실패** |
| C2 (e) 노드 키 | ③ · 400 판 | 키가 다 보임 | quantity: core_cmp_nonuniform 135/133 px · tape_adhesion_anomaly 147/133 px · defect 구역: 키 59 ~ 69 자(예 «sat\|SYN-BW-103-11\|10\|4\|3\|2026-11-24T03:07:00+09:00» 472/133 px) 전부 말줄임 — 400 판 잘린 칸 189 · More 뒤 200 | **실패** |
