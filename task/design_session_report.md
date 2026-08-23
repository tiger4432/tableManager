# Design Session — Report Channel (design session -> lead PM)

---

# 🔵 인수 블록 — 컴팩트 시점 (2026-08-23 밤). **새 세션은 여기부터**

## 환경 — 틀리면 조용히 실패합니다

```
워크트리   C:/Users/kk980/Developments/assyManager-design   브랜치 design
dev 서버   cd <워크트리>/client2 && npm run dev -- --port 5173 --strictPort
API        8080 = 메인 트리 (총괄 관리). 재기동 금지
```
🔴 **포트는 반드시 5173.** `config.js` 가 `location.port === '5173'` 으로 API 를 판별합니다.
5174 로 밀리면 API 를 «자기 자신»에게 걸어 전부 404 인데 **화면은 멀쩡해 보입니다.**

## 채널 — 그리고 이 세션이 두 번 헛돈 이유

```
총괄 -> 나   task/DESIGN_ORDERS.md   (main)
나 -> 총괄   task/design_session_report.md  (design) + push   ← 커밋이 초인종
```
🔴 **라운드를 끝내고 「대기」로 들어가기 «직전»에 반드시:**
```
git fetch origin && git merge origin/main
그리고 task/DESIGN_ORDERS.md 를 «다시» 읽는다. 새 공사가 있으면 그대로 이어서 한다
```
구현자는 총괄과 같은 트리라 지시가 즉시 보이지만 나는 브랜치가 갈려 «병합해야만» 보입니다.
그래서 내가 멈출 때마다 다음 지시가 안 보이는 곳에 쌓였고, 하루에 두 번 그랬습니다.
📌 **대기열이 곧 착수 허가입니다.** 소유자께 「진행할까요」를 묻지 않습니다 (소유자 지시).
   판정이 필요하면 이 파일 맨 위에 「🔴 판정 요청」.

## 착지한 것

```
2b/2c    메인 그리드 · 감사 로그 표 · 헤더 정렬 · 목업 스타일 (전부 main 병합 + dist 구움)
공사1    rnd-console 은퇴 — 14파일 4,330줄. 세고 나서 지웠고 서버 은퇴 하나를 열었음
공사2    task/design/rnd_board_component_spec.md — 부품 7종 시각 명세 (324줄)
공사3    부품 A 머리 요약 · D 구성   (composition 라우트)   harness 26/0
공사4    부품 F 후보 리스트 · G 순위 리스트 (subgraph 라우트) harness 32/0, 8/8 포착
```

## 열려 있는 것

```
🔴 BOARD 에 «자리 안 앉힘»   부품 넷 다 PARTS 에 등록만 됨. 앉히려면 합성 루트의
                            bindLoaders 가 필요한데 그건 골격 = 구현자 소관
🔴 빨강 셋 (내 것 아님)      case_control · ledger_trace · load_shows_loaded_map
                            내 작업 «이전» 트리에서도 같이 실패하는 것을 워크트리로 확인함
⚠️ 3 대 4 판정 났음          measured 는 «걷기»를 세는 내 4 가 맞다고 총괄이 판정
⚠️ 경계 어댑터 하나          measuredFromHops__untilServerServesIt — 서버가 그 필드를
                            내면 «이 함수만» 지우면 되고 부품은 안 건드림
📌 트렌드 부품 붙일 때        /trends 는 grain 을 «반드시» 넘길 것. 없이 부르면 found 0
```

## 🔴 이번 세션에 새로 배운 함정 — 다시 밟지 말 것

```
인라인 스타일이 CSS 를 이긴다        하루에 «세 번» 당했다 (Menu 테두리 · 버튼 패딩 ·
                                    tx display:inline-block). 헤더를 만지면 «마크업의
                                    인라인부터» 본다. 마크업은 의도이고 computed 가 사실
스크린샷이 안 되는 건 페이지 탓이 아닐 수 있다
                                    목업 섹션·스크립트·외부링크를 다 지워도 실패했고
                                    «앱 페이지도» 같이 실패해서 갈렸다 —
                                    visibility:hidden · outerWidth 0, 창이 안 보이는 상태
내 색 변환기가 투명을 검정으로 읽었다  rgba(0,0,0,0) -> #000000. 그대로 썼으면
                                    「패널 배경이 검다」가 명세에 사실로 올라갔다
subgraph 는 ranked 를 propagation 안에 둔다
                                    body.ranked 는 undefined -> 「걷기가 아무것도 못 찾았다」로
                                    보고할 뻔했다. 실제 25건. 그리고 id 는 «노드 id»여야 함
                                    (웨이퍼 이름은 422)
🔴 던진 변이는 «잡힌 게 아니다»       앵커가 썩어 loadModules 가 던지는 것을 러너가
                                    caught 로 찍고 있었다. 이제 INERT = 구멍으로 센다
🔴 변이는 «판별식이 되는 입력»으로 깨운다
                                    marking:1 을 쓰는 인스턴스를 클릭하면 하드코딩
                                    'marking:1' 이어도 수가 같다. 반대쪽을 눌러야 갈린다
부품을 PARTS 에 등록하면 구현자 하네스가 깨진다
                                    main.js 가 새 파일을 임포트하는데 그쪽 로더가 재배선을
                                    안 한다. 등록할 때마다 그 로더에 두 줄 추가
client2/public/ 은 빌드에 실린다      목업을 거기 서빙해서 보는 건 되지만 «커밋 금지»
check_harnesses 는 자동 발견          FLOORS 등록은 선택. 스캔은 tests/*.mjs (하위폴더 제외)
```

## 이 보드의 «성패 조건» — 부품을 더 붙일 때 계속 유효

```
실측 있음 / 이름뿐 을 못 가르면 이 화면은 한 번 쓰이고 버려진다 (라이브: 4 대 21)
   -> 색으로 가르지 말 것. 색은 테마에서 죽는다. «자리»와 «접기»로 가른다
다섯 부재 상태는 서로 «다른 말»이고 어느 것도 오류가 아니다
   contrast:unexamined · complete:false · state:empty · tied · incomparable
   그리고 state:empty 는 「그 종류가 없다」이지 「아무것도 없다」가 아니다 —
   노드·엣지는 있다. 둘 다 말해야 한다
순위는 판정이 아니다. 동률은 서버 번호를 그대로 유지한다 (다시 매기면 없는 순서를 지어냄)
물리량·모델은 «두 줄». 합치면 아무도 하지 않은 세 번째 주장이 생긴다
클라는 후보의 «종류»를 세지 않는다
```

---



---

# ✅ 공사7-bis «추가» — **마킹을 감쇠로 그립니다. 그리고 맵 배지가 정직해졌습니다** (2026-08-23 23:xx)

## 감쇠 — 스팟파이어 실측대로

```
전       누른 것에 파란 링. 나머지는 «그대로»      -> 찾아야 보입니다
지금     누른 것은 그대로, 나머지가 «흐려집니다»    -> 안 찾아도 보입니다
```
```
맵      역할 색은 «그대로» 두고 알파만 내립니다(#rrggbb + 40). 색조가 살아 있어야
        found/scanned 가 계속 읽힙니다
리스트  루트에 is-attenuating 한 클래스. 흐림은 CSS 한 줄 (부품마다 색 계산 없음)
```
🔴 **아무것도 안 골랐으면 아무것도 안 흐려집니다.** 「아직 안 골랐다」를 「전부 아니다」로
그리면 우리가 세운 부재 규칙을 우리가 어깁니다. 그 자리에 단언을 걸었습니다(C29).

### 실측 (라이브)
```
마킹 전       모든 행 opacity 1        «하나도 안 흐림»
행 클릭 후    마킹된 행 1 · 나머지 0.38
```

## 맵 배지 — 총괄이 보신 「표시 1」 고쳤습니다

```
원인   표시 N 이 markings.count(읽는 이름) 이었습니다 — «그 이름 전체»의 크기
       그래서 후보(물리량 노드)를 marking:2 에 찍으면 맵B 가 「표시 1」인데 웨이퍼는 빈 채였습니다
지금   자기 셀 중 마킹된 것만 셉니다 — «세는 것 = 그리는 것»
실측   같은 상황에서 맵B 배지 「표시 0」
```

## 하네스
```
C29  아무것도 안 골랐을 때 «안 흐린다»      M15 (항상 흐림) -> 빨강 ✅
C30  마킹하면 나머지가 흐려진다            M14 (감쇠 제거)  -> 빨강 ✅
C31  마킹된 것은 «온전한» 강도로 남는다
C32  배지가 «자기 셀»을 센다               M16 (이름 전체)  -> 빨강 ✅
결과 rnd_board_harness 125/0 · 변이 16/16
```

⚠️ **아직 «안 한» 것 (다음 라운드 = 공사8 감사에 포함):** 「마킹 종속 차트가 빈 화면」 —
우리 부품 중 마킹으로 «데이터를 거르는» 것은 아직 없습니다. 스팟파이어의 `Data limiting`
자리를 우리 layout 이 담을 수 있는지가 감사 항목이라 거기서 «보고»로 다루겠습니다.

---

# ✅ 공사7-bis 완료 — **클릭은 갈아치우고, Ctrl 은 쌓습니다. 커서 밑은 안 움직입니다** (2026-08-23 23:xx)

## 선택 모델을 «한 자리»에 두었습니다

```
panel.js   mark(nodeId, sign, mode = 'replace')
           replace  이름을 비우고 이것 하나          <- 맨 클릭. «기본값»
           add      더합니다. 같은 걸 또 누르면 뺍니다 <- ctrl/cmd. 토글은 여기«에만» 삽니다
panel.js   markingIntent(event)   ctrl|cmd -> add · shift -> 부호 CONTROL · 둘은 «조합»
```
🔴 **기본값을 replace 로 둔 이유:** 부품이 mode 를 안 넘기면 «다른 부품과 같게» 굴러야 합니다.
기본이 toggle 이면 새 부품이 조용히 옛 결함을 다시 들여옵니다.
🔴 네 부품이 같은 세 키를 읽습니다. 그래서 읽는 함수가 «하나»입니다 — ctrl 이 이 판에선
「더하기」인데 옆 판에선 딴 뜻인 화면은 한 화면이 아닙니다.
⚠️ 골격 파일(`panel.js`)을 건드렸습니다. 지시하신 규칙이 바로 그 계약 메서드에 있어서
   부품 넷에 같은 모델을 «네 번» 적는 것을 피하려면 그 자리뿐이었습니다.

## 커서 밑이 안 움직입니다 — 원인은 «펼침»이 아니라 «다시 그리기»였습니다

```
진짜 원인   클릭 -> render() -> 상자를 통째로 다시 만듦 -> scrollTop 이 0 으로 «리셋»
            그래서 20번째 행을 클릭하면 화면이 맨 위로 튀고, 누르려던 것이 딴 데로 갑니다
고친 것     세 리스트 부품이 «스크롤 위치를 이어받습니다» (rank · candidate · composition)
```
### 브라우저 실측 (라이브 8080, 같은 코드)
```
스크롤 200 -> 클릭 -> 200           «유지»
클릭한 행의 화면 y   411 -> 411      «안 움직임»
증거 펼침 1건, 안쪽에서 스크롤        scrollHeight 1045 / clientHeight 537
다른 패널 좌표                       movedPanels: []   «하나도 안 움직임»
```
지시하신 수락 문장 그대로 재서 붙입니다.

## 선택 모델 실측 (같은 자리, 라이브)

```
행0 클릭        count 1
행1 «클릭»      count 1 · 행0 사라짐 · 행1 있음      -> replace ✅
행0 ctrl+클릭   count 2 · 둘 다 있음                 -> add ✅
행2 ctrl+shift  count 3 · 부호 {+1, −1} 공존         -> 컨트롤 더하기 ✅
```

## 하네스

```
rnd_board_harness   118/0 · 변이 13/13
  C21~C24  add 는 쌓고 · 맨 클릭은 «비우고» 하나 · 맨 클릭은 «자기를 토글하지 않는다»
  C25~C28  수식어 읽기 한 자리 (plain · ctrl · shift · ctrl+shift)
  M12      replace 를 toggle 로 되돌리는 변이  -> C22 빨강  ✅ (지시서의 변이)
  M13      ctrl 을 add 키에서 뗀 변이          -> C26 빨강  ✅
```
🔴 **제 하네스에서 «죽은 변이 셋»이 드러났습니다 — 이번 변경이 들춘 것입니다.**
```
M1 (하드코딩 이름)   toggle 자리에 박고 있었는데 맨 클릭이 그 길을 «안 지나게» 됐습니다.
                     단언은 멀쩡한데 «변이가 안 물던» 상태 -> 클릭이 실제로 지나는 자리로 옮김
M2 (모듈 수준 상태)  세 단계짜리였고 첫 앵커가 썩었는데 «나머지 둘이 텍스트를 바꿔서»
                     「뭔가 바뀌었나」 검사를 통과했습니다. 모듈은 런타임에 죽었고 INERT 로 찍힘
                     -> «한 단계»로 줄임 (globalThis 로 치환)
M6 (쓰기 이름 무시)  B1 이 «개수»를 세고 있었는데, 클릭이 «비우고 쓰기»가 되자 개수가
                     그대로여서 초록. -> 개수 말고 «구성원»을 단언 (누른 행은 없어야 하고,
                     원래 있던 마크는 살아 있어야 한다)
```
`rnd_board_composition_harness` 26/0 · 6/6 회복. walk 32/0 · intersection 24/0 그대로.

---

# ✅ 공사7 완료 — **교집합은 저장소 옆 한 겹. 부품 0줄** (2026-08-23 23:xx)

```
새 파일   client2/src/rnd_board/marking_intersection.js
쓰는 법   intersectMarkings(store, { sources: ['marking:1','marking:2'], target: 'marking:3' })
선언      BOARD.intersections 에 «데이터»로. boot 가 자리 앉힌 «뒤» 설치합니다
부품      한 줄도 안 건드렸습니다. 부품은 reads 에 'marking:3' 이라고 «이름만» 적으면 됩니다
```
🔴 **이름은 이 파일에 한 글자도 없습니다.** `sources`·`target` 은 인자입니다. 마킹이 넷·다섯이
되거나 1∩3 이 또 필요해져도 **분기가 아니라 호출이 하나 더** 생깁니다.

## 부호 — 지시하신 대로 «모순»으로 다룹니다

```
두 이름이 같은 부호   -> 교집합에 «그 부호로» 들어갑니다 (컨트롤끼리도 교집합입니다)
두 이름이 반대 부호   -> 안 들어갑니다. 그리고 conflicts() 로 «셉니다»
```
한쪽이 「여기서 났다」이고 다른 쪽이 「봤는데 안 났다」인데 이걸 적중으로 세면
**대조가 거짓말을 시작합니다.** 그래서 빠지되 «조용히» 빠지지는 않습니다 — 모순을 그냥 버리면
아무도 안 찍은 노드와 구별이 안 됩니다.
📎 정확히는 「두 이름이 반대 부호로 든 노드」입니다(셋 이상일 때 셋째가 그 노드를 아예 안 들고
있어도 앞의 둘이 어긋나면 셉니다). 지시서 문장 그대로입니다.

## 부작용을 막은 자리 하나

목표 이름을 매번 지웠다 다시 쓰면 구독한 부품이 «매 계산마다» 다시 그립니다.
그래서 **차이만 씁니다** — 저장소는 값이 실제로 바뀔 때만 알립니다(A9 가 그것을 잽니다).

## 하네스 — 지시하신 두 변이 포함

```
새 파일   client2/tests/rnd_board_intersection_harness.mjs   18/0 · 변이 6/6 포착
M1 교집합을 «합집합»으로       -> A2 빨강  ✅ (지시서의 첫째 변이)
M2 부호를 무시                 -> A3 빨강  ✅ (지시서의 둘째 변이)
M3 이름을 코드에 박음          -> B1 빨강
M4 빠진 노드를 목표에 남김     -> A8 빨강
M5 모순을 안 셈               -> A4 빨강
M6 구독 안 하고 한 번만 계산    -> A7 빨강
```
그리고 구현자 하네스의 로더에 새 모듈 한 줄을 물렸습니다(안 물리면 합성 루트가 아예 안 뜹니다).
`rnd_board_harness` 108/0 유지.

## ⚠️ 아직 «읽는 부품이 없습니다»

`marking:3` 은 계산돼서 서 있지만 **소비자가 0**입니다 — 그 이름을 읽을 «후보 맵»이 아직
안 만들어졌습니다. 완료로 적지 않고 여기 적습니다. 그 부품이 생기는 날 `reads: 'marking:3'`
한 문자열이면 끝입니다.
📎 지시서 메모대로, 이 연산은 걷기의 「여러 씨앗이 동시에 닿은 것」과 «같은 모양»입니다.

---

# ✅ 공사6 완료 — **맵이 「선언된 프레임」으로 그립니다. 15x15 가 15x15 로** (2026-08-23 22:xx)

## 원인이 하나 더 있었습니다 — `frame.grid` 는 «문자열»입니다

```
서버가 주는 것   frame.grid = '{"grid_cols": 15, "grid_rows": 15, "grid_start_x": 0, ...}'
                 «JSON 문자열». 객체가 아닙니다
그래서           frame.grid.grid_cols 는 조용히 undefined
                 프레임을 읽으려 해도 «읽히지 않는» 모양이었습니다
```
그래서 고친 자리가 둘입니다: **파싱**(문자열이면 JSON.parse, 아니면 조용히 거절) 과
**격자**(`boundsOf(cells)` -> 선언된 `grid_cols/rows` + `grid_start_x/y`).

## 「빈 자리」와 「없는 자리」

```
빈 자리    선언에 있는데 셀이 안 온 자리   -> «테두리만» 그립니다 (채우지 않음)
없는 자리  선언 밖                        -> 아무것도 없습니다. 격자가 거기서 끝납니다
```
소유자 문장 그대로입니다 — 「빈 영역까지 테두리 그려주냐」. 이제 그립니다.
채우지 않는 이유: 빈 자리는 «측정»이 아니라 «자리»입니다. 채우면 안 난 다이가 난 것처럼 보입니다.
⛔ mm 안 씁니다. 좌표는 오리진 기준 칸수 그대로이고 피치를 곱한 곳은 없습니다.

## 브라우저에서 «라이브 서버»로 실측했습니다

창이 숨겨져 `ResizeObserver` 가 안 뜨므로(공사5 보고), 페이지에서 보드를 **한 벌 더 부팅**해
`observeSize` 를 직접 물려 재봤습니다 — 같은 코드, 같은 8080:
```
frame.grid   '{"grid_cols": 15, "grid_rows": 15, "grid_start_x": 0, ...'   ← 문자열 확인
layout       cols 15 · rows 15 · minX 0 · minY 0 · cell 12.5px
lastPaint    cells 141 · vacant 84        141 + 84 = 225 = 15 x 15  ✅
```
📎 **못 본 것:** 빈 자리 테두리의 «색감». 창이 안 보여서 그림 자체는 확인 못 했습니다.
   보이는 창에서 한 번 봐 주십시오 — 톤이 세면 빈 자리가 결함처럼 읽힐 수 있습니다.

## 하네스 — 지시하신 «그 변이»를 넣었습니다

```
B13/B14   선언 15x15 인 맵이 15x15 로 앉는다 (셀 bbox 는 0..13 = 14x14)
B15       빈 자리 84개가 자리를 지킨다
M10       격자를 셀 bbox 로 되돌리는 변이      -> B13 빨강  ✅
M11       grid 를 «객체로만» 읽는 변이         -> B13 빨강  ✅  (오늘의 진짜 결함)
결과      rnd_board_harness 108/0 · 변이 11/11 포착
```
🔴 **부작용 하나를 같이 고쳤습니다.** 마크도 테두리라서 C9/C10/C12/C13 이 「테두리 개수」로
마크를 세고 있었는데, 빈 자리가 테두리를 얻자 85개가 됐습니다. **그 단언들은 마크가 아니라
«획»을 세고 있었습니다.** 마크 «전»의 획 색을 표본으로 잡아, 그때 없던 색의 획만 마크로 셉니다 —
색 값을 하네스에 다시 적지 않습니다.

⚠️ 남는 것: `dt`·`core` 는 여전히 `no_frame` 이라 프레임이 없습니다. 지시대로 그대로 뒀습니다.

---

# ✅ 공사5 완료 — **여섯 자리. 부품 파일 «0줄» 고쳤습니다** (2026-08-23 22:xx)

## 앉혔습니다 — 선언만으로

```
자리   1행 전폭   머리 요약 · SYN-CX-CHIP-001
      2행 전폭   구성 · SYN-CX-CHIP-001
      3열 띠     맵 슬롯07 / 원인 후보 / 순위      (좌열 세로 둘: 슬롯07 · 슬롯03)
                 후보 · 순위는 2행 걸침 (rowSpan 2)
격자   columns 1.7fr 1fr 1fr · rows auto .75fr 1fr 1fr   — 목업 2a 의 899/508/509 비율
```
🔴 **부품 파일은 한 줄도 안 고쳤습니다.** 부품이 답하는 데 필요한 것(`finalChipId` ·
`seedNodeId` · `collect`)은 전부 «선언»에 적었고 셸이 생성자로 펴 줍니다.
합성 루트에서 고친 것은 `bindLoaders` 하나 — `apiBase`·`fetchImpl`·`dpr` 을 **모든** 패널에
주입합니다. **주소는 「이 페이지가 어디서 도는가」라는 사실이라 레이아웃 «데이터»에 넣으면 안 됩니다**
(넣는 순간 그 데이터가 저장·드래그 대상이 못 됩니다).

## 브라우저로 «직접» 열어 봤습니다 (`read_page` + 상자 실측, 1600×900)

```
여섯 다 그립니다   머리 요약 resolved · 웨이퍼 SYN-CX-BW-001 · cardinality variable
                   구성 10행 (resolved 5 · candidate 2 · contested 2 · unresolvable 1)
                   후보 25 · 실측 3 · 이름뿐 22 · 「대조군 없음 — 또래를 안 쟀습니다」
                   순위 25행, 동률 그대로, 증거 접힘
상자              1580×63 / 1580×205 / 717×273 ×2 / 422×556 ×2   겹침 0 · 넘침 0
콘솔              오류 0
```

## 🔴 조립식 규칙이 «화면에서» 증명됐습니다

후보 카드를 클릭하니 **순위표의 같은 행이 같이 켜졌습니다** —
`ledger-quantity:v1:…(void_formation·bond_temp)` 가 두 부품에서 동시에 `is-marked-case`.
두 부품은 서로를 모릅니다. 이어 준 것은 «밖에 있는» `marking:2` 하나뿐입니다.

## 🔴 보고 — 고치지 않고 보고합니다 (수락 조건대로)

```
① 제목을 그리는 부품이 «맵뿐»입니다
   선언에 title 을 적고 셸이 넘겨 주는데 head/구성/후보/순위는 그걸 «안 그립니다».
   그래서 화면에 이름 없는 판이 넷입니다. 고치려면 부품 파일 넷(또는 셸)을 만져야 해서
   손대지 않았습니다.  -> 부품이 그릴지, 셸이 캡션 띠를 그릴지 판정해 주십시오

② 맵의 「표시 N」은 이 맵의 칸이 아니라 «그 이름 전체»를 셉니다
   map_panel.js:193  markings.count(this.reads)
   후보를 marking:2 에 찍었더니 «맵B 가 「표시 1」» 인데 웨이퍼엔 아무것도 안 그려집니다.
   숫자가 틀린 게 아니라 «주어»가 다릅니다 — 이름의 개수를 맵의 개수로 읽히게 씁니다.
   선언으로 피할 수는 있습니다(맵B 를 제3의 이름으로). 다만 마킹 배정은 총괄 지시라
   제가 바꾸지 않았습니다.  -> 판정 요청
```

## ⚠️ 씨앗이 «둘»입니다 — 하나로 못 묶었고, 그래서 제목에 적었습니다

```
composition   SYN-CX-CHIP-001  resolved (components 10)
              SYN-VOID-001 · SYN-CHIP-001 · SYN-BW-001-07  -> 전부 resolution "absent"
walk          맵이 그리는 «그 웨이퍼» SYN-BW-001-07 에서 ranked 25   (맵과 후보는 같은 주어)
```
한 주어로 앉히면 머리·구성 자리에 «거절문»이 서게 됩니다. 목업의 **제어 단**(안 만듦)이
묶어 줄 자리이고, 그때까지는 제목이 주어를 답니다.
📎 실측이 **3**입니다(103-11 에서는 4). 웨이퍼가 달라서지 3대4 판정이 뒤집힌 게 아닙니다 —
`post_bond_queue_h` 가 닿던 `mes_queue:SYN-BW-103-11` 은 그 웨이퍼의 것입니다.

## ⚠️ 새 계측 함정 — **창이 숨겨지면 `ResizeObserver` 가 «한 번도» 안 뜹니다**

맵 캔버스가 300×150(기본값)에 머물고 캔버스 클릭 15발이 전부 안 맞았습니다.
앉히기를 의심하기 전에 **새 RO 를 제가 직접 붙여** 625×259 짜리 판을 관찰시켰습니다 — **0회.**
`document.visibilityState === "hidden"` 인 동안 RO 가 안 옵니다. 스크린샷이 안 찍히는 것과
**같은 뿌리**이고, RO 로 자기 크기를 잡는 부품은 이 상태에서 **죽은 것처럼 보입니다.**
-> 맵의 크기·클릭은 이 창에서는 «판정 불가»입니다. 보이는 창에서 확인해 주십시오.

## 하네스 — 구현자 하니스를 «같은 커밋에서» 고쳤습니다

```
H1  「보드가 맵 둘을 앉힌다」(panels.length === 2)
    -> 이 단언은 «이번 라운드가 고친 결함을 못 보는» 단언이었습니다. 넷이 만들어져
       등록되고 «안 앉아» 있었는데 초록이었습니다.
    -> 「등록된 부품은 전부 화면에 앉아 있다」로 «구성원»을 고정. 등록만 하고 안 앉히면
       그 순간 빨개집니다
H2/H3  「둘 다 맵이다」 -> 「한 부품이 같은 화면에 두 번 선다 · 둘은 다른 이름을 읽는다」
H7     load 를 «질문을 선언한» 패널에만 요구 (전부에 요구하면 「모든 부품은 맵이다」가 됨)
H7b    질문 없는 패널도 «주소»는 받는다  (새 단언)
결과   rnd_board_harness 103/0 · 변이 9/9 포착
       내 하니스 둘 그대로: composition 26/0(6/6) · walk 32/0(8/8)
```

---

# 🔴🔴 작업 요청 — **`origin/main` 으로 병합 + dist 재빌드** (소유자 지시, 2026-08-22 10:2x)

> △소유자: 「origin main 에 해달라해」

소유자가 **운영(8080)을 보고 계시고**, 거기에는 제 수정이 안 들어가 있습니다.
`origin/design` 의 아래 세 커밋을 `origin/main` 으로 병합하고 dist 를 다시 구워 주십시오.

```
a3adb6a0  미저장 알약이 좀은 헤더에서 먼저 찌그러지지 않게
96bb007e  배지 글자 중앙 정렬
21f1a50c  🔴 display 를 CSS 가 갖게 — 이게 진짜 수정입니다
899e0317  (이 보고)
그리고 그 뒤로 이어지는 컬럼 순서 변경도 같이 필요합니다 (아래 ②)
```

① **배지 중앙 정렬** — 운영 번들에 `txPendingBadge.style.display = e>0 ? \`inline-block\` : \`none\`` 이
살아 있습니다. CSS(`.tx-action-group`)는 들어갔는데 인라인이 그것을 이김니다.

② **그리드 컬럼 순서** — △소유자 「table config 의 display col 순서 그대로」.
`applyMockupLayout` 의 재정렬을 걷어냈습니다 — `/schema` 가 이미 config 순서로 답하고 있었고
목업 순서는 그 위에 얹힌 **두 번째 의견**이었습니다. 폭은 이름으로 붙는 것이라 그대로 둡니다.
(virtual_column_render_harness 66/0, 28/28 결함 포착)

---

# 🔴 재빌드 요청 — 운영 번들이 수정 세 개 앞에서 멈췄습니다 (2026-08-22 10:1x)

소유자가 「미저장 라벨이 여전히 가운데 안 온다」고 하셔서 운영(8080) 번들을 직접 열어 보았습니다.

```
운영 JS  /assets/main-D3qStpvX.js
  txPendingBadge.style.display = e>0 ? `inline-block` : `none`   ← 제가 지운 그 줄이 살아 있습니다
운영 CSS /assets/style-DBsbFcEs.css
  .tx-action-group · .audit-filter · .range-readout · .fill-target-header  전부 있음
```
🔴 CSS 는 들어갔는데 인라인 `inline-block` 이 그것을 이깁니다 — 정확히 제가 고친 버그입니다.

```
09:56  a3adb6a0  미저장 알약이 먼저 찌그러지지 않게
09:57  3e52394f  총괄 dist 빌드          ← 운영은 여기서 멈췤습니다
09:58  96bb007e  글자 중앙 정렬
10:07  21f1a50c  display 를 CSS 가 갖게   ← 진짜 수정. 번들에 없습니다
```
세 커밋 모두 `origin/design` 에 올라가 있습니다. **병합 + dist 재빌드 부탁드립니다.**

⚠ 제가 배운 것: 저는 dev(:5173) 만 보고 「고쳐졌다」고 보고했고, 소유자는 운영을 보고 계셨습니다.
앞으로 화면 수정 보고에는 **어느 포트에서 확인했는지**를 같이 적겠습니다.

---


---

# ✅ 2c 착지 — Global 탭이 표가 됐습니다 (`fc70ef0b`, 2026-08-22 02:xx)

```
시각 58 · 사용자 62 · 종류 74 · 대상·컬럼 1fr · 변경 150 · Tx 120
헤더 28px · 행 38px · 하단 범례 34px
```
Row 탭은 카드 그대로입니다 — 항목이 적고 주어가 하나라 카드가 잘하는 일입니다.
`loadHistory` 가 컨테이너에 `.audit-table` 를 붙이고, 탭 핸들러 넷이 아니라 거기 한 자리에서 결정합니다.

## 🔴 걷다가 발견한 결함 둘 — 둘 다 제 것이고 둘 다 고쳐있습니다

```
① 시각이 두 줄로 접힘   toLocaleTimeString() 이 「오후 11:31:31」 을 씁니다 → 58px 초과
                        직접 조립니다: 23:31:31.  실측 후 38px 넘는 행 0개
② ▶ 펼치기가 칸 밖으로 잘림  84px Tx 칸에 필요 폭 120px → «살아있는 컨트롤이 클릭 불가»
                        트랙 120px.  사이드바 640px 에서도 대상·컬럼 117px 안 잘림
```
②은 판정 ②(폭 = max(목업, 안 잘리는 폭))을 그대로 적용한 것입니다. 목업의 Tx 칸엔
아이콘이 없고 우린 건 둘(🔍 필터 · ▶ 펼치기)입니다.

## ⚠ 안 만든 것 — 지어내지 않았습니다

```
목업 상단 필터 줄 (사용자 전체 · 종류 전체 · 오늘)   대응하는 기능이 없습니다
「더 보기」                                     historyUrl 은 cell/row URL 만 만듭니다.
                                                Global 라우트에 페이징 경로가 없습니다
목업의 7종 알약                              감사 행은 6가지만 구분합니다.
                                                색을 고르던 «그 분기 그대로» 알약을 만들었습니다
```
셀 종류가 더 필요하거나 필터가 필요하면 **기능 지시를 받아야** 합니다.

## ▷ 남은 것

```
⑨  서버 400 보행 — 소유자 허락 대기 중 (라이브 표에 쓰기 시도입니다)
```

---


---

# ✅ 2b 완료 + ⑨ 불가 경로를 «실제로» 걸었습니다 (2026-08-22 01:xx)

## 🔴 ⑨ — 「못 재다」가 아니라 **떴습니다**

`dt_inventory` 에서 가상 조인 컬럼 `dt_lot_confirmed` 에 포츠스를 두고
참조 패널에서 셀을 잡았습니다. 띄가 **빨간색으로** 바뀌며:

```
DT_LOT  불가 — 조인 컬럼 dt_lot_confirmed 포함 · 대상에서 빼고 붙여넣기      Ctrl C → Ctrl V
band class = "tx-filter-banner reference-alignment is-blocked"
```
앞 보고에 「NOT MEASURED」로 적었던 항목입니다. 이제 재졌습니다.

🔴 **단, 서버가 실제로 400을 다려주는 것까지는 아직 안 걸었습니다.**
그건 소유자의 «라이브 테이블에 쓰기를 시도»하는 일이고, 소유자가 지금 그 화면을
쓰고 계십니다. **소유자 허락을 받고 걷겠습니다.** 되는 척하지 않겠습니다.

## ✅ 판정 ①② 둘 다 적용 + 실측

```
① Copy Header   둘 다 있음 (Options + 하단 줄).  저장 키는 여전히 copyHeader 하나만
                  어느 쪽을 켜도 반대쪽이 따라옴 (실측: false→true→false 양방향)
                  map_editor.js:706-712 관례 그대로. 새 키 · 이벤트 브리지 없음
② 열 폭        width = max(목업, 라벨 안 잘리는 폭).  낱개 특례 없음
                  🔴 잔린 헤더 0개 — dt_log 15개 중 0, dt_inventory 14개 중 0
                  dt_slot 58→94 · dt_eqp 70→76 · dt_lot 112 그대로(라벨이 이미 들어감)
                  HEADER_CHROME_PX=32 는 감이 아니라 실측 (두 컬럼이 정확히 32 부족이었습니다)
```

## ②에 대해 한 가지 더

`headerLabelWidth` 는 canvas `measureText` 를 씁니다. 하네스 샌드박스엔 canvas 가
없어서 거기선 0을 돌려 **목업 폭으로 폴백**합니다. 하네스는 여전히 초록이지만
«폭 규칙을 덩지는 않습니다». 그건 브라우저 실측으로만 받쳤습니다 — 적어 둡니다.

## ③ LOT_EVENT 근거 표 — **소유자가 이미 지시하셨습니다**

「목업이랑 똑같이해」 + 2b 스크린샷을 직접 주셨고, 그 그림은 근거 표가
«탭이 아니라 아래에 쌓인» 모양입니다. 그래서 쌓았고 `a1de3d86` 으로 올렸습니다.
라이브 확인: 탭 줄 숨김 · 패널 1 · 「이 job 의 원본 행 (근거) 125행」.

## ▶ 2b 남은 것 = **없습니다** (한 가지 단서 제외)

참조 그리드 열 폭은 거터 `#` 32px 만 적용했습니다. 나머지(`dt_job` `x` `y` `신뢰도`)는
**라이브 규칙에 없는 컬럼 이름**이라 적용할 대상이 없습니다 — 열 «이름»이 받은
것과 같은 부류입니다. 만들어내지 않았습니다.

## ▷ 다음

```
2c  Global 탭을 카드 타임라인 → 표로 (timeline.js).  소유자가 2c 스크린샷을 주셨습니다
⑨  서버 400 보행 — 소유자 허락 대기 중
```

---


---

# 🔴 정정 — **소유자는 깨어 계십니다** (2026-08-22 새벽)

야간 지시서(`74f40c20`)가 「소유자 취침 → 승인이 필요한 것은 시작하지 말 것」으로
서 있는데, **그 전제가 틀렸습니다.** 소유자가 지금 이 세션에 직접 지시하고 계십니다:

```
「컴팩트 했음. 2b 남은 것 계속 진행해」
「2c」 + 2c 스크린샷        「2b」 + 2b 스크린샷
「화면 켰어 크롬 mcp 이용해」
```

그래서 저는 **승인된 2b 잔여 작업을 계속합니다.** 야간 지시의 「새 시각 결정 금지」는
그대로 지키고 있습니다 — 아래 폭 건처럼 판정이 필요한 것은 착지시키지 않고 적어 둡니다.

🔴 아침 계획을 「소유자 부재」 위에 세우셨으면 다시 보셔야 합니다.

---

# ▶ 2b 잔여 — 둘 착지, 둘 남음 (2026-08-22 새벽)

## ✅ 착지

```
c2dc64b5  하단 단축키 줄 (30px · 상단선 1px · 10.5px · 우측 Copy Header)
b0ac78cb  메인 그리드 ①② + accent 배경 + inset 0 -2px 0
```
둘 다 브라우저로 직접 걸어 확인했습니다 (`dt_inventory`, :5173).
`DT_LOT ①` / `DT_SLOT ②`, 배경 `rgb(232,240,252)`, 그림자 `inset 0 -2px 0 rgb(26,102,208)`.

## 🔴 판정 요청 ① — Copy Header 를 옳긴 대가

목업이 Copy Header 를 하단 단축키 줄에 둡니다. 둘을 만들지 않고 **기존
`#copy-header-toggle` 을 옷겼습니다** (Options 드롭다운 → 참조 패널 하단).
`clipboard.js` · `main.js` · 참조뷰 셀째 전부 id 로 읽으므로 그대로 됩니다.

**재서 확인한 대가:** 규칙 없는 표에서는 참조 패널이 `display:none` 이라
토글을 **바꿀 방법이 없습니다** (`lot_event` 실측: 탭 숨김 · 패널 숨김 · rect 0×0).
저장된 값은 계속 적용됩니다 — 잃은 건 「바꾸는 능력」만입니다.
→ 드롭다운에도 남길지(둘이 됨) / 이대로 둘지 판정 부탁드립니다.

## 🔴 판정 요청 ② — 목업 열 폭이 실제 이름을 못 담습니다 (**부류**)

```
dt_slot   폭 58   라벨 폭 62 > 가용 26   → 「DT…」 로 잘림
dt_eqp    폭 70   라벨 폭 43 > 가용 38   → 잘림.  🔴 서수가 없는데도 잘립니다
dt_lot    폭 112  라벨 폭 55 ≤ 55        → 정상
```
🔴 **제 ①② 때문이 아닙니다.** 목업은 자기 라벨(`Slot`)로 폭을 재고, 소유자는
이름을 「지금 로직으로」(실제 스키마) 쓰라고 판정하셨습니다. 둘이 동시에 참일 수 없습니다.
**폭은 A등급**이라 임의로 고치지 않았습니다. 후보: 목업 폭을 **최솟값**으로 보고
라벨이 더 길면 라벨에 맞추기(한 규칙, 낱개 특례 없음). 판정 부탁드립니다.

## ▷ 남은 것

```
3  참조 그리드 아래 LOT_EVENT 근거 표   ← 지금 view[1] 이 「탭」인데 목업은 「아래 쌓기」
4  참조 그리드 열 폭                     ← 판정 ②와 같은 부류. 목업 이름 중 살아있는 건 `#`=32 뿐
⑨ 불가 경로 보행                        ← 풀렸다는 지시 받았습니다. 다음으로 걷습니다
```

## ⚠ 오해할 뷰 하나

`dt_inventory` 는 화면이 거의 **빈 칸으로 보입니다.** 결함 아닙니다 —
686칸 중 값이 있는 건 49칸이고 전부 `dt_job` 입니다. API 가 실제로 그렇게 줍니다
(나머지는 null). 렌더러를 의심하기 전에 원본을 재서 확인했습니다.

---


---

# 🔵 인수 블록 — 컴팩트 시점 상태 (2026-08-22 00:xx). **새 세션은 여기부터**

## 환경 — 이걸 안 맞추면 전부 404가 난다

```
워크트리   C:/Users/kk980/Developments/assyManager-design   브랜치 design
dev 서버   cd <워크트리>/client2 && npm run dev -- --port 5173 --strictPort
API        8080 = 메인 트리(총괄 관리). 재기동 금지
```
🔴 **포트가 반드시 5173.** `config.js`가 `location.port === '5173'` 으로 API를 판별한다.
5174로 밀리면 API를 «자기 자신»에게 걸어 전부 404가 되고, 화면은 멀쩡해 보인다.

```
목업 원본  소유자가 zip 으로 준다: C:/Users/kk980/Downloads/데이터 그리드 UI 목업.zip
           풀어서 `Main Grid Mockup.dc.html` (1106줄). 2a=73행 · 2b=270행 · 2c=437행
지시서     task/MIGRATION_2b.md (저장소 사본, Phase 0 + 실측표 포함)
채널       총괄→나 task/DESIGN_ORDERS.md(main) · 나→총괄 task/design_session_report.md(design)
```

## 🔴 판정 규칙 A/B/C — 「목업대로」의 범위 (소유자)

```
A 픽셀까지 똑같이   실측표 수치 · 열 순서와 폭 · 정렬 띠/칩/①② 존재와 배치 ·
                    탭 순서와 기본 활성 · 하단 단축키 줄의 항목과 순서
B 뜻만 같으면 됨    DOM 구조 · 클래스 이름 · 상태 관리 · 렌더 방식
C 목업의 허구       모든 데이터 값 · TL26-*/CW-*/EQP07 · 신뢰도 % · 「미저장 6」·「15,489」·
                    「4,052」 · 규칙 이름 · 참조 그리드 7행 → 전부 실제 API 응답에서 온다
```
애매하면 **A로 간주.** A에서 벗어나려면 지시서를 «먼저» 고친다.

## ✅ 착지 완료 (전부 main 병합됨, 브라우저로 직접 확인함)

```
Phase 1   컬럼별 필터 · 시스템 컬럼 필터 없음 · 칩(⇲ 조인 표시) · 칩 ✕ 개별 해제
Phase 2   사이드바 640px · 폭 영속(+ 복원 시 clamp) · 탭 밑줄형 · 참조 탭 기본 활성
Phase 3.1 열 순서 = 규칙의 target_fields «배열» (candidate_for 키 순서 아님) · ①②
    3.2   참조뷰가 그리드 (거터 · 30/28px · 드래그+Shift방향키 한 모델 · custom-range-selected)
    3.3   copy → tsv.js 재사용 · clipboard.js «import 안 함» · 가드는 clipboard.js 쪽에 이미 있었음
    3.4   정렬 띠 (알린다, 막지 않는다)
Phase 4.1 client2/tests/reference_grid_paste_harness.mjs · FLOORS 22 · 변이 4/4 · 대조군 2/2
    4.3   frontend.md §3.6 신설 + 모듈표 · docs/history/20260821_232730_*.md
밀도     헤더바 52 · 탭 34 · 그리드 헤더 30 · 데이터행 28 · 셀 mono 11.5 ·
         헤더 sans 600 10.5 자간.4 uppercase · 필터칸 3px/1px/r3px/10.5 · 배너 30
형태     칩 → 상단 헤더 바 «안» · 밀린 열 수 → 그리드 헤더 우단 · 정렬 띠 → 탭 아래 30px 플러시
```
🔴 **4.4(빌드·dist 커밋)는 내 것이 아니다.** 총괄이 굽는다. 소스만 커밋한다.

## ▶ 다음에 할 것 — 2b 남은 넷, 그다음 2c

```
1  메인 그리드의 채울 열 두 개에 ①② + accent 배경 + inset 0 -2px 0
   ⚠️ 규칙은 «비동기»로 온다 — buildColumnDefs 시점엔 아직 없다.
      syncReferenceViewRule 이 규칙을 잡은 뒤 setGridOption('columnDefs', buildColumnDefs()) 재적용 필요
2  사이드바 하단 30px 단축키 줄
      Shift+↑↓ 범위 · Ctrl Enter 일괄 · Ctrl Shift V Smart Paste · 우측 Copy Header
   🔴 Copy Header 는 «새로 만들지 말고» 기존 #copy-header-toggle 을 DOM 에서 옮긴다
      (index.html 180행 근처. id 조회라 위치를 옮겨도 JS 는 그대로 돈다)
   `.kbd` 키캡 클래스는 이미 style.css 에 있다
3  참조 그리드 아래 LOT_EVENT 근거 표 (목업은 «탭»이 아니라 아래에 «쌓인» 표)
4  참조 그리드 열 폭  # 32 · dt_job 1fr · x 46 · y 46 · dt_lot 132 · dt_slot 74 · 신뢰도 66
그다음 2c  Global 탭을 카드 타임라인 → «표»로 (timeline.js 전면)
      필터줄: 사용자 전체▾ · 종류 전체▾ · 오늘▾ · 우측 「50건 중 18」
      헤더:  시각58 · 사용자62 · 종류74 · 대상·컬럼 1fr · 변경150 · TX84
      행:    종류 알약(MANUAL/PASTE/INGEST/OVERWRITE/BATCH/DELETE/SYNC) ·
             대상은 두 줄(키+컬럼) · 변경은 「옛값 취소선 → 새값」
      하단:  행 클릭→그 셀로 이동 · Tx 클릭→그 트랜잭션만 · 우측 「더 보기」
```

## ⚠️ 아는 함정 — 다시 밟지 말 것

```
목업 열 이름 13개 중 8개가 «실제 dt_log 에 없다»
   없는 것: dt_cell_key · dt_job · dt_eqp · product · dt_x · dt_y · core_wafer · core_product
   🔴 소유자 판정: 「열순서는 그냥 지금 로직으로 해」 → 이름으로 매칭, 없는 건 건드리지 않는다. 종결됨
Cell 탭은 소유자가 «빼라»고 했다 (목업엔 4탭이지만 3탭이 맞다). 리스너는 가드만 하고 남겨 뒀다
   — activeHistoryTab === 'cell' 을 timeline.js 가 다섯 군데서 읽는다
CSS 는 «#myGrid» 로 건다. theme.js 가 ag-theme-quartz ↔ -dark 를 뒤집어서
   테마 클래스로 걸면 한쪽 모드에서만 맞고 반대쪽에선 «조용히» 없다 (실제로 한 번 당했다)
변이 앵커는 CRLF 를 탄다. 
 으로 적으면 이 체크아웃에서 «아무 데도» 안 맞는다
grid.js 를 참조뷰에서 import 하면 «순환»이다 (grid.js 가 이미 그 모듈을 import 한다)
   → 공용 헬퍼는 state.js 로 (visibleRangeColIds 가 그렇게 갔다)
buildColumnDefs 를 고치면 virtual_column_render_harness 의 «슬라이스»도 같이 고쳐야 한다
   (새 헬퍼/상수를 sandbox 에 안 넣으면 ReferenceError 로 죽는다 — 한 번 그랬다)
```

## 🔴 아직 못 잰 것 (「없다」가 아니라 「못 쟀다」)

```
정렬 띠의 «불가» 판정과 그 뒤 서버 거절
   총괄이 dt_inventory 에 가상조인(dt_lot_confirmed·dt_slot_confirmed)을 «만들어 뒀다».
   그런데 서버가 config 를 아직 «다시 안 읽었다» — 실측: /tables/dt_inventory/schema 의
   virtual_columns 가 여전히 []. 총괄이 리로드를 눌러 주면 그때 걸어서 보고할 것
   (백그라운드 감시 task biobq1eck 가 그 순간을 잡도록 걸려 있었다 — 컴팩트 후엔 다시 걸 것)
```

## 감시

`origin/main` 폴링 모니터(task bgpt8wdma)가 걸려 있고 `task/DESIGN_ORDERS.md` 변경을 따로 표시한다.
컴팩트 후 끊겼으면 다시 건다.

---

> Channel per the 2026-08-21 21:0x brief: lead PM writes `task/DESIGN_ORDERS.md` on **main**;
> this file is committed on the **design** branch and pushed. Commits are the doorbell.

**인수 완료 · 워크트리 `C:/Users/kk980/Developments/assyManager-design` (branch `design`) 에서 대기 중.**

---

## ✅ 2026-08-21 22:0x — Phase 3's screen is real now. Walked it. Three things to rule on.

Orders received (`aa4b5ffc`), merged, acted on. The fixtures work — the wall I measured is gone.

### The fixture holds, and it closed a criterion I could not test before

```
dt_inventory   참조뷰 tab appears · panel opens · 3 views · 176 rows of real data
               "이 job 의 원본 행 (dt_log)" / "관측된 좌표 범위" / "같은 장비의 다른 job 들"
dt_log         all six virtual columns render with 🔗
               🔴 I nearly recorded them ABSENT — AG-Grid virtualizes columns and they are
                  appended last, so the first header read returned nothing. Scrolled, then read.
```

**Phase 1's join-column criterion — previously NOT MEASURED — now PASSES:**

```
DT_X_BASE 🔗 filtered on 미상   Matches 34,939 -> 29,830   (server narrowed on a VIRTUAL column)
chip reads                      "DT_X_BASE⇲ contains 미상"  (the ⇲ mark works, keyed off the announcement)
```

That is the exact round-trip the migration order feared would be dropped. It is not dropped.

### 🔴 ⑤ `candidate_for` is EMPTY on all six new views — Phase 3.1 has no source at all

```
dt_frame_confrimation  view[0..2]  candidate_for = {}
core_frame_review      view[0..2]  candidate_for = {}
```

Neither `fill_targets` nor `candidate_for` exists on the new fixtures, so the column-order
contract has nothing to read from. This is not an objection to the fixtures — the views are
display-only by design and the lead said so. It means ㉮/㉯ is still the live question and
**whichever way it is ruled, a declaration has to be written** before Phase 3.1 can start.

### 🔴 ⑥ The panel's decision key is not on screen, and the grid reads as 401 blank rows

Both new rules key on `dt_job`. Measured against `/schema` and the row payload:

```
dt_job          populated on 401/401 rows   —   NOT in /schema.columns, so no grid column
dt_job_id  🗝️     0/401 non-null            <- the business key column, empty on every row
dt_eqp            0/401
dt_lot / dt_slot  1/401
dt_frame        126/401      core_frame     6/401
dt_x_* / dt_y_* 126/401      core_*         6/401
```

So the operator sees 401 rows whose first four visible columns are blank, the identity of
each row is carried by a column the grid is never told about, and the panel silently keys off
it. The panel WORKS — `valueOf` reads the row payload, not the column list — but the screen
cannot tell you which job you are looking at.

🔴 This is the owner's own rule from the brief: 「사람이 «밖에서» 알아야 하는 것이 있으면
그건 화면이 덜 된 것이다」. Adding `dt_job` to that table's declaration is a server-side
change, so I am reporting it rather than doing it.

### 🔴 ⑦ The order's `suppressFilterButton` line is inert on AG-Grid 35.3.0 — and I think that is lucky

I added `floatingFilterComponentParams: { suppressFilterButton: true }` as instructed.
Measured: **14 funnel buttons are still in the DOM.** In 35.3.0 the key moved to
`colDef.suppressFloatingFilterButton`; the spelling the order specifies is silently ignored.

I did **not** switch to the working spelling, because making it work would break something:

```
the funnel button is the ONLY path to the operator list (contains -> equals)
and joinResolvedFilterDef's own header tooltip tells the operator to use it:
   "미해결 행 보기: 필터를 Equals로 두고 '미상' 입력"
```

Verified by clicking it: the menu opens and shows the operator selector. Suppressing it would
delete the path the app's own instruction depends on — a control that says "do X" next to a
screen where X is unreachable.

**Ruling needed:** leave the button (drop that line from the order), or suppress it and move
the operator choice somewhere reachable. I have left the inert line in place and touched
nothing, so today's behaviour is the safe one either way.

### Watch

A monitor is armed on `origin/main`, flagging `task/DESIGN_ORDERS.md` changes separately from
ordinary commits, so a new order reaches me without polling.

### Standing

Phase 1–2: awaiting the lead's merge. Phase 3: not started, awaiting ㉮/㉯.

---

## ▶ Phase boundary — 3.1 landed (`895658ea`), 3.2 not started

Orders `f41bcef7` received. ⑥ fixed on your side (`dt_job` now leads `display_columns`), ⑤
answered with a declaration that carries both targets in one view. Phase 3.1 is in.

**I did not read the order off `candidate_for`'s keys, and that is deliberate.**

You asked me to weigh whether key order survives the loader and to write the assumption into
a comment if I leaned on it. I measured it end to end — over real HTTP, `target_fields` is
`['dt_lot','dt_slot']` and `view[0].candidate_for` arrives in that same order — and then did
not lean on it. `target_fields` is an **array**: JSON guarantees its order outright. Key order
only survives while no column is named something integer-like, because `Object.keys` hoists
those to the front numerically. Nothing is named `1` today; the day something is, a paste
lands in the wrong column with no error and no refusal. Reading the array removes the
assumption instead of documenting it. `candidate_for` still supplies the mapping — which view
column feeds which target — which is the half `fill_targets` never had.

**Contract verified against real payloads**, not fixtures:

```
view[0]  cols ['dt_lot','dt_slot','cells']   candidate_for {'dt_lot':'dt_lot','dt_slot':'dt_slot'}
         -> renders dt_lot ① · dt_slot ② first and adjacent, cells after.  1 row (the candidate)
view[1]  cols 8, candidate_for {}  -> FALLBACK: original order, 72 rows, untouched
```

One correctness detail worth naming: rows arrive as **positional arrays**, so reordering the
header alone would have shifted every value one column sideways and still looked plausible.
The original index is carried through.

Harnesses: 28 · 59 · 72 · 594, zero failures. ⚠️ A grep for this module's filename found
**zero** harnesses; a wider grep found four. I nearly reported it uncovered.

### 🔴 Blocker for walking it — I cannot serve this branch

```
8080          serves the MAIN tree's bundle — does not contain this branch's client
preview tool  refuses a dev server whose cwd is outside the project root, and the
              worktree is a sibling directory -> tried, "cwd must be a relative path
              within the project root", reverted the config byte-exact
```

So Phase 3.1's **render is not walked**. The data contract is measured; the pixels are not.
Options are yours: merge `design` so 8080 can serve it, or approve a launch entry pointing at
the worktree. I have not touched the shared config beyond the one test above, which I undid.

### ⑦ still open (not blocking)

`floatingFilterComponentParams: { suppressFilterButton: true }` remains inert on AG-Grid
35.3.0 and I have left it inert on purpose — the funnel button is the only route to the
`equals` operator that the join column's own tooltip instructs. Ruling welcome whenever.

---

## ✅ 22:2x — served my own branch, walked it. Two phases verified, one new blocker.

`90a11941` was right and the blocker was mine to clear: `npm run dev -- --port 5173
--strictPort` in the worktree, API resolving to 8080 by port. Held 5173. Confirmed by marker
that the served code is **this branch** (`fillPlan`, `FILL_ORDINALS`, `SIDEBAR_WIDTH_KEY`,
`tabReferenceBtn`, `reference-view-fill` all present) before trusting anything on screen.

### Verified for the first time — both were untestable until now

```
Phase 2.2  selecting dt_inventory auto-selects 참조뷰 and opens the panel
           (no rule -> unchanged, Global stays)
Phase 2.1  drag 640 -> 900, reload -> 900 survives (CSS default is 640)
           corrupt value: stored 99999 -> restored 2269 = the cap, grid still 635px wide.
           The clamp-on-the-way-BACK-IN is what stops a stored width from swallowing the grid
⑥ (yours) dt_job now leads dt_inventory and is populated — the blank grid is gone
```

### 🔴 ⑧ Phase 3.1 is correct and still unreachable — the panel binds to the FIRST rule

The panel rendered the **fallback**, exactly as designed, because it never saw the rule that
declares anything. Measured:

```
rules matching dt_inventory, in API order:
   1  dt_frame_confrimation   3 views   declares [] [] []
   2  core_frame_review       3 views   declares [] [] []
   3  dt_lot_slot_from_log    2 views   declares ['dt_lot','dt_slot'] []      <- the declaration
syncReferenceViewRule uses  rules.find(r => r.derived_table === currentTable && views.length)
   -> picks #1. #3 is unreachable from the screen.
```

So `dt_lot_slot_from_log` cannot be opened at all, and Phase 3.1's ①② ordering has never been
drawn. My renderer is not wrong here — a rule declaring nothing SHOULD fall back, and it did.

🔴 **This is the unordered-representative shape, not a typo.** `find()` was right while a
table had at most one rule; the class grew to three and the representative became arbitrary.
Adding a fourth rule tomorrow could change which panel the operator sees, silently.

**It is a binding contract, not styling, so I have not changed it.** Candidates:

```
㉮  show every matching rule's views          8 tabs — against 「복잡하면 안 된다」
㉯  prefer a rule that declares candidate_for  smallest change; still arbitrary if two declare
㉰  let the operator pick the rule             honest, but it is a new control
```

I lean ㉯ as the immediate unblock and ㉰ as the durable answer, but this is yours to rule.
**With ㉮/㉯/㉰ unruled, Phase 3.1 cannot be demonstrated and 3.2 has nothing to build on.**

### Environment note

A vite dev server is running from this worktree on 5173 (background). It writes no `dist`.

---

## ✅ 22:4x — 판정 ⑧ applied and WALKED. Phase 3.1 is visible on screen (`a808c784`)

```
before   panel bound to rules.find(has views) -> dt_frame_confrimation (declares nothing)
after    a rule that DECLARES wins; otherwise the first, exactly as before
```

**Walked on the dev server against live 8080:**

```
view tabs now   "관측된 dt_lot / dt_slot — 이 job 이 말하는 것"  ·  "이 job 의 원본 행 (근거)"
                -> the panel reaches dt_lot_slot_from_log, which it could not before
view[0]         headers  ["① dt_lot", "② dt_slot", "cells"]
                declared columns FIRST, ADJACENT, numbered in declared order; cells after
                row      SYN-DT-103 · 25 · 125
view[1]         declares nothing -> original 8 columns, 125 rows, no numbering
                view-level FALLBACK intact
```

🔴 The selected cell was `DT_LOT: NULL` while the panel offered `SYN-DT-103` for it — the
empty cell and its candidate on screen together. That is the feature working, not a mock.

No control was added to choose a rule, per the ban.

**The stopgap is in the code comment, not only here**, as instructed: the panel still shows
one rule out of N; this criterion is unique today only because exactly one rule declares; when
a second declares, the arbitrary representative returns just as silently as it did this time.

Harnesses: 28 · 59 · 72 · 65, zero failures.

### NOT walked, and why

```
rule-level fallback (|| forTable[0])   unreachable from a screen here — all three rules sit on
                                       dt_inventory and one of them declares, so `find` never
                                       returns undefined. Reasoned, not observed. Saying so.
```

### Still open

```
⑦   suppressFilterButton inert on AG-Grid 35.3.0, deliberately left inert (not blocking)
3.2 not started — awaiting your go
Phase 1–2  awaiting your merge
```

---

## ▶ Phase 3.2 (`038d7eee`) and 3.3 (`2b257d58`) — both walked

### 3.2 — the panel is a grid you can select a range in

```
gutter + header 30px + rows 28px      the main grid's own metrics, measured on screen
3x2 drag                              6 cells, rgba(26,102,208,0.14) + dashed --accent
Shift+Down, Shift+Right               3x2 -> 4x3 = 12 cells (same model as the drag)
tab switch                            selection cleared (0)
```

**Deviation, stated plainly:** I kept the `<table>` element instead of rebuilding as divs.
Everything 3.2 names — gutter, header, matching heights, fill styling, range selection, the
generation guard — a table does, with far less code than a div grid whose cells would then
need their own layout. If divs were wanted for a reason not written down, say so and I will
convert it.

**A defect the screenshot caught before I committed:** `nowrap` was on the body but not the
header, so narrow columns broke their names one character per line — `c_bn` rendered as four
stacked letters. Header holds its line now; the section scrolls sideways instead.

### 3.3 — the one line you asked for, before choosing a shape

🔴 **What the constraint prevents:** `clipboard.js` drags `grid.js`, `ui.js` and
`effort_meter.js` in behind it, and this panel needs none of them (it already has `config`,
`state`, `dom`). **It is about which way the dependency points, not about avoiding reuse** —
the serializer IS the shared `tsv.js` and the header switch IS the grid's `#copy-header-toggle`.

**And the guard it recommends already exists.** `clipboard.js` has returned early for targets
inside `#reference-view` since the panel was a native-text surface, with a comment saying why.
That is option (b), order-independent, already in place. I added nothing there.

🔴 **Verified it is the guard working, not accidental ordering.** My handler registers later
than `clipboard.js`'s, so winning the clipboard proves nothing on its own. Probed the event in
the capture phase: target resolves inside `#reference-view`, panel holds focus, so
`clipboard.js` takes its early return regardless of registration order.

**Clipboard payload read back, not assumed:**

```
3x2, header off   "SYN-DTE-02	SYN-PRD-A
SYN-DTE-02	SYN-PRD-A
SYN-DTE-02	SYN-PRD-A"
header on         prepends BARE names: "dt_eqp	product"   (not "① dt_lot")
declared view     "dt_lot	dt_slot
SYN-DT-103	25"      in declared order
```

⚠️ My first measurement said the clipboard was empty. **That was the instrument** — the probe
had been registered before the panel's handler existed, so it read `clipboardData` before
anything wrote to it. Re-armed after render and it read correctly.

Convention gate green (no `navigator.clipboard`). Harnesses 28 · 59 · 72 · 151 · 306, zero
failures.

### ⚠️ Fixture limit for 3.3's stated acceptance

The order's acceptance is a **3행×2열** drag on the fill columns. The declared view returns
**one row** (`후보가 대개 1개`, as your declaration comment says), so a 3-row drag on the fill
columns is not possible here. I ran 3×2 on the evidence view and 1×2 on the declared columns.
Not a defect — recording it so nobody reads the missing 3-row case as untested by choice.

### Next: 3.4

Building it as the migration doc specifies — the band **informs** and the SERVER refuses. Your
note said 「거절되는 화면」; the doc says 「막지 않고 알린다」 and lists a blocking gate under
「하지 않을 것」. The one hard verdict is 「불가」 when the target range touches a virtual
column, and the actual refusal there is the server rejecting the batch. I will show both.

---

## ▶ Phase 3.4 landed (`f7bd1dd5`) — and one thing you asked to see, I cannot produce

```
mismatch  "1행 × 2열 · 열 순서 불일치 · 복사 dt_lot → dt_slot / 대상 dt_x_base → dt_x_sign"
          target order read from a range actually drawn in the main grid
match     "1행 × 2열 · 열 순서 일치 · dt_lot → dt_slot"   (green)
```

Built as the migration doc specifies: **the band informs, the server refuses.** A blocking
gate is on that doc's do-not-build list, and the reason holds — pasting one column of a
two-column copy is legitimate, so a screen that refuses it is wrong more often than the paste
is. `불가` is the one hard verdict and even it does not intercept the keystroke; it predicts
the server's batch-level 400 instead of letting the operator discover it after.

**A move worth your attention.** `visibleRangeColIds` went from `grid.js` to `state.js`.
It reads `state.visibleColIndexMap` and `state.gridApi` and nothing else, so `grid.js` was
only ever its first caller. Importing `grid.js` from the panel would have formed a **cycle**
(`grid.js` already imports `refreshReferenceForSelection` from it), and copying the four lines
would have made a second implementation of column order. `grid.js` calls it under the same
name. Verified the move broke no mutation anchor: 65 · 28 · 72 · 151 · 138 · 45, zero failures.

### 🔴 판정/조치 요청 ⑨ — the 불가 state cannot be demonstrated on these fixtures

You asked to see a refusal actually fire. **I cannot produce one here, and it is not the code:**

```
dt_inventory   the ONLY table with a reference panel   virtual_columns = []
dt_log         has the 6 virtual columns              no enrichment rule -> no panel
```

The two fixtures are **disjoint**, so no screen exists where a panel selection can target a
virtual column. The verdict path and the server refusal behind it are therefore **NOT WALKED**
— not passing, not failing.

**What would close it:** a virtual join exposing a column on `dt_inventory` (server config,
yours). One exposed column is enough. If you would rather not, 불가 stays unwalked and I will
say so in the final report rather than let it read as verified.

### ⚠️ Phase 4.4 conflicts with your standing ruling — flagging before I get there

The migration doc's Phase 4.4 says `npm run build` and commit `dist/`. Your ruling ① says
lanes commit **source only**, `dist` is yours, and the rebuild happens once after every lane
lands. **I will not build or commit `dist`.** Phase 4.1–4.3 (harness, fallback scoring, docs)
are mine and I am starting them.

---

## ▶ Phase 4 — harness landed, docs landed (`7f30c9fd`), build NOT done (your ruling)

### 4.1 / 4.2 — the harness scores its own mutants

`client2/tests/reference_grid_paste_harness.mjs`, registered in **`FLOORS` at 22**, not
`KNOWN_RED`. Standalone run:

```
16 passed, 0 failed
4/4 defects CAUGHT   reverse declared order · remove the clipboard guard ·
                     compare only the COUNT · pin isVirtual false
2/2 controls ESCAPED comments stripped · a local renamed
ASSERTIONS 22 0
```

The controls are the part that makes the rest mean anything: if stripping comments or renaming
a local had been *caught*, some check would be reading source text instead of behaviour.

**4.2 fallback is scored** — a view with no `candidate_for` makes no plan, a rule with no
`target_fields` makes no plan, a declared column the query did not return is dropped, and the
fallback copy keeps the payload's own order. That path is operational reality for every rule
that declares nothing.

⚠️ **A mutation anchor died on me mid-build, from CRLF.** The anchor was written with `
`
and this checkout is CRLF, so it matched nowhere and the runner refused — correctly. An anchor
that matches on one machine and vanishes on another is precisely the silent-inert mutant this
file exists to prevent, so the anchors are newline-agnostic now.

### 4.3 — docs

`frontend.md`: module row 119 → 485 with what it now does, plus a new **§3.6** for the paste
contract. And a correction that matters beyond this round: **§3.4 was writing
`state.isVirtualColumn(colId)`**, which is not callable — it is a named export of `state.js`.
🔴 **The migration order I was given had copied that exact form out of this document.** The
wrong name had already travelled once; left in place it travels again.

History entry `20260821_232730_reference_grid_and_column_filters.md`, including the §6 point
you flagged: this work lands on the CURRENT `index.html` grid and its sidebar, which is not in
the retiring set, and I did not put new work on anything that is.

### 4.4 — not done, deliberately

The migration doc says build and commit `dist/`. Your ruling ① says lanes commit source only.
**I built nothing and committed no `dist`.**

⏳ The full `check:harnesses` run is still going as I write this; I have the standalone result
above but not yet the runner's own acceptance of the FLOORS entry. I will not call 4.1 closed
until I have seen the runner score it.

---

## ✅ 답변 ⑪ — **네, 메인 트리의 그 변경은 전부 `design` 에 이미 있습니다. 되돌리셔도 됩니다**

한 줄로 답하라고 하셨지만, 되돌리는 판단이라 **무엇이 어디로 갔는지**까지 재서 붙입니다.
「메인에만 있는 줄」을 전부 세었고 **잃는 것은 0**입니다.

```
index.html   메인에만 있는 줄  0      dom.js   메인에만 있는 줄  0
style.css    메인에만 있는 줄  1      grid.js  메인에만 있는 줄  19
```

**style.css 의 1줄** — `.reference-view-section { margin-bottom: 16px; }`.
`design` 은 같은 규칙에 `overflow-x: auto` 가 **붙은** 형태를 갖고 있습니다(3.2 에서 헤더가
한 글자씩 쪼개지던 것을 고치며 옆스크롤을 켰습니다). 대체됐습니다.

**grid.js 의 19줄 — 셋으로 나뉘고 셋 다 살아 있습니다:**

```
1줄   import 문        design 은 같은 import 에 `visibleRangeColIds` 가 «추가된» 형태
14줄  visibleRangeColIds  design 에서 `state.js` 로 «옮겼습니다» — 지워진 게 아닙니다.
                          그 함수는 state 만 읽고, grid.js 에서 import 하면 참조뷰 패널과
                          «순환»이 됩니다 (3.4 커밋 `f7bd1dd5` 에 사유 기록)
4줄   주석 한 덩이       design 에서 삼항 연산자 «위»로 옮겼습니다. 그 자리에 두면
                          `virtual_column_render_harness` 의 변이 앵커가 셋으로 쪼개져
                          조용히 무력화됩니다 — 실제로 한 번 그렇게 죽었습니다
```

🔴 **되돌려도 되는 이유는 「같아서」가 아니라 「대체돼서」입니다.** 세 덩이 전부 `design`
안에 «더 나은 자리»로 존재합니다. 되돌리지 않았습니다 — 공유 트리는 총괄 몫입니다.

## ✅ ⑦ 적용 — 죽은 줄을 «지웠습니다** (`5b4a0b1` 계열, 아래 커밋)

고쳐서 살리지 않고 **삭제**했습니다. 판정하신 대로 깔때기는 남습니다. 왜 안 넣는지를
주석에 적었습니다 — 「해 봤고 일부러 안 한다」가 빠지면 다음 사람이 다시 넣습니다.

## ⑨ ⑩ 접수

- **⑨** 가상 컬럼 픽스처 감사합니다. 서버가 config 를 다시 읽어 화면에 뜬 뒤에 **불가를
  걸어서** 보고하겠습니다. 그때까지 그 항목은 계속 **「못 쟀다」**로 둡니다.
- **⑩** 병합 보류 접수. 타이밍이라는 것도 접수했습니다. 5173 에서 계속 걷겠습니다.
- **4.4** 빌드·`dist` 가 제게서 빠진 것 확인했습니다.

## ✅ Phase 4.1 CLOSED — the runner scored it, not just the harness itself

```
✓ reference_grid_paste_harness.mjs  (ran 22, failed 0)
```
그리고 러너의 「floor 없음」 목록 5개에 **제 것은 없습니다** — FLOORS 등록이 먹었다는 뜻입니다.
게이트 전체는 여전히 빨강이지만 그 사유는 제 것이 아닌 셋(`case_control` · `ledger_trace` ·
`load_shows_loaded_map`)입니다.

---

## 🔴 요청 — **서버 config 리로드 눌러 주십시오** (소유자 지시)

⑨ 의 가상조인 픽스처가 아직 화면에 없습니다. 방금 실측:

```
GET /tables/dt_inventory/schema   virtual_columns: []   join_resolved_columns: []
```

선언은 만들어 주셨고 서버가 **아직 다시 읽지 않았습니다.** 리로드가 되면 제가 바로
「불가」를 걸어서 보고합니다. 그 전까지 그 항목은 계속 **「못 쟀다」**입니다.

---

## 🔴 Phase 0 자체 감사 — **소유자가 새로 붙였고, 재 봤더니 제가 둘을 어겼습니다**

소유자가 이주 지시서에 **Phase 0(기존 CSS·배너 재사용 체크리스트)** 를 추가했습니다
(저장소 사본 `task/MIGRATION_2b.md` 갱신). 그 문서가 **「배너 마크업 재사용과 토큰 재사용이
«실제 커밋에» 있는지가 우선 확인 대상」** 이라고 못박고 있어서, 제 커밋을 그 기준으로 쟀습니다.

### ✅ 지킨 것

```
색 토큰        내 style.css 추가분에 raw hex·rgb() «0건». 전부 var(--…)
radius         999px · 50% · 6px · 0 — 전부 이 파일에 «이미 있던» 값
헤더/행 높이   30px / 28px, 메인 그리드와 동일 (화면에서 실측 확인)
.custom-range-selected 재사용 (새 색 0)
#copy-header-toggle 재사용 · .history-tabs--wide 변종 — 지시대로
```

### 🔴 어긴 것 ① — 배너를 «복제»하지 않고 «새로 만들었습니다**

Phase 0: 「`.tx-filter-banner` 와 **동일한 마크업·클래스**를 정렬 띠와 필터 칩 바에 재사용,
색만 다르게. **새 배너 컴포넌트를 만들지 않는다**」.

제가 만든 것:
```
.grid-filter-bar      새 클래스 (칩 바)        <- 있어야 할 것: .tx-filter-banner 구조 복제
.reference-alignment  새 클래스 (정렬 띠)      <- 있어야 할 것: 같은 구조 + accent/warning 색
없는 것               banner-icon · banner-text · clear-banner-btn 구조
```
커밋 메시지에 「`#tx-filter-banner` 패턴을 재사용했다」고 적었는데, **패턴을 참고했을 뿐
클래스를 재사용하지 않았습니다.** Phase 0 이 요구하는 것은 후자입니다. 제 기록이 실제보다
후하게 적혀 있었습니다.

### 🔴 어긴 것 ② — 이 스타일시트에 없던 폰트 크기 하나

```
.72rem   이 파일 사용 0건 (제가 넣은 유일한 «새» 크기, 행번호 거터)
```
나머지(`.82` · `0.85` · `0.9`)는 전부 기존 값이었습니다. **`.76rem`(기존값)으로 바꿨습니다** —
이건 되돌릴 것이 없어서 그냥 고쳤습니다.

### ⚠️ 판단이 갈리는 것 — 새 클래스 셋

```
.reference-view-fill · .reference-view-gutter · .filter-chip / -x / .filter-clear-all
```
Phase 0 은 「참조 그리드 셀에 «새 상태 클래스»를 만들지 않는다」고 합니다. 위 셋은 상태가
아니라 «역할» 표시(채울 열 · 거터 · 칩)이고, 칩은 종전에 없던 UI라 재사용할 클래스가
없었습니다. **그래도 `.filter-chip-x` 는 `.clear-banner-btn` 을 쓸 수 있었습니다.**

## 👉 판정 요청 ⑫ — 배너 둘을 «지금» 고칠까요

```
㉮  지금 고친다     .tx-filter-banner 마크업·클래스로 갈아끼우고 색만 변종.
                    이미 «병합된» UI 두 곳이 눈에 띄게 바뀝니다
㉯  다음 라운드로   Phase 0 미준수를 기록으로 남기고, 소유자가 화면을 본 뒤에 함께 정한다
```
🔴 **제가 임의로 안 고칩니다.** 병합된 화면이고 소유자가 그 화면을 보실 수 있습니다.
어느 쪽이든 지시 주시면 그대로 하겠습니다.

---

## 🔴 판정 요청 (2026-08-21 21:0x)

### ① The red build gate is mine, and here is the one line that clears it

The lead's note says the gate is red on someone else's uncommitted `grid.js`. That is mine.
Measured, not guessed — `node tests/virtual_column_render_harness.mjs` in the main tree:

```
HARNESS FAILURE: mutation "old-server" applies 0 time(s), expected 1
```

The mutation searches `grid.js` for this literal source text:

```
    const filterDef = resolvedEntry
      ? joinResolvedFilterDef(resolvedEntry, baseTooltip)
      : { filter: false, headerTooltip: baseTooltip };
```

My edit added `floatingFilter: false` to that last line, so the anchor no longer matches and
the mutation cannot be applied. The harness is right to fail: it cannot prove the defect it
guards is still caught. Only this ONE anchor broke — I re-ran the other two harnesses that
read `grid.js` (`value_suggest_keys` 94/0, `map_key_datalist` 83/0) and both are green, and
the other `grid.js` mutations in the same file anchor on lines I did not touch.

**Two ways out, and it is the lead's call because it depends on whether my work is kept:**

- Keep the change -> the anchor's third line becomes
  `      : { filter: false, floatingFilter: false, headerTooltip: baseTooltip };`
- Drop the change -> the gate goes green by itself, nothing to edit.

I have not touched the main tree since the ruling. I am not editing a harness that scores a
change whose fate has not been decided.

### ①-b The gate was ALREADY red before my change — three more, none of them mine

Measured after moving in: `npm run build` in this worktree, which is a **clean** merge of
`origin/main` with zero local modifications (`git status` empty, verified). It still fails,
at the same prebuild gate, on three harnesses that have nothing to do with me:

```
case_control_harness.mjs         HARNESS BROKEN: mutant `small-rates-round-to-zero` — its anchor moved
ledger_trace_harness.mjs         HARNESS FAILURE: mutant `sentence-overrides-the-field` — its anchor moved
load_shows_loaded_map_harness.mjs HARNESS FAILURE: mutation anchor is GONE: restore-runs-unconditionally-again
```

Their baselines are green (195, 324, 43 assertions, 0 failures). What died is the mutation
corpus: each anchors on literal source text, and the sources moved under them
(`map_key.js`, `ledger_trace.js`, and case-control's core were all touched by recent
console/ledger commits). The runner's own words: *"An anchor that no longer matches makes
the mutant silently inert — this file's corpus is only worth its anchors."*

🔴 **This corrects what I said in ①.** I reported my `grid.js` as the thing blocking the
build. It is *a* red, in the main tree — but the build does not pass without it either, so
dropping my change does **not** turn the gate green. That matters for the ruling in ①: it
was never a choice between "keep my change and fix one anchor" and "drop it and be green".

🔴 **And it is one disease, not four.** Every one of these — mine included — is a mutation
anchored to literal source text that a different lane edited. Four instances in one evening,
in four unrelated files, is the class rather than the incidents. The runner says to bring
this to the Lead PM rather than parking entries in `KNOWN_RED`, so I am bringing it and not
touching any of them. I own exactly one of the four and I am not editing anchors on the
other three.

### ② Correction to my previous report — I attributed the build to the wrong lane

I reported that the ontology session's build swept my uncommitted work into `dist/`. The lead
has since recorded that those assets are their own lane's — three builds, the last an
`npx vite build` that went around the red prebuild gate. I had mtimes and bundle contents,
which established that my unverified source was inside the served bundle; I did not have
who ran the build, and I named a lane anyway. The substance stands, the attribution was mine
to not make. `dist` is the lead's per the owner.

### ③-CORRECTION 🔴 my own alternative does not hold — I proposed it without measuring

I recommended `candidate_for` as a zero-server-change substitute for `fill_targets`. **I was
wrong, and I was wrong because I read the normalizer instead of the live declaration.**

Measured in `server/config/enrichment_rules.json`:

```
dt_job_lot_slot_attribution   derived_table = dt_job_attribution
  target_fields = ['dt_lot_confirmed', 'dt_slot_confirmed']
  view[3]  candidate_for = {'dt_lot_confirmed':  'dt_lot'}
  view[4]  candidate_for = {'dt_slot_confirmed': 'dt_slot'}
  view[0,1,2]  candidate_for = None
```

The two fill targets live in **two different views** — two different tabs of the panel — with
one target each. So `candidate_for` cannot express "these columns, adjacent, in this order,
in one grid", which is the entire job `fill_targets` was invented for. A per-view dict of
size one has no order to read.

The order's own design was right and my shortcut was not. **Ruling still needed, but the
menu has changed: it is `fill_targets` plus its server passthrough, or Phase 3.1 gets a
different design.** I am not proposing a third option before someone rules on that.

### ④ Phase 3 has no reachable screen in this environment — measured, not assumed

Two declarations that the migration depends on are not live here:

```
virtual_join_rules.json    active rules: NONE
                           both are prefixed `_retired_...`, which the loader reads as a
                           comment. Product-owner ruling 2026-08-14: the two right tables
                           were never registered in table_config, so both were rejected on
                           every load.
enrichment_rules.json      the ONLY rule carrying reference_views is
                           dt_job_lot_slot_attribution, whose derived_table is
                           dt_job_attribution — NOT registered in table_config, therefore
                           not selectable in the grid's table dropdown (verified against
                           the live dropdown: 26 tables, that one absent).
```

Consequences, stated as limits rather than as failures:

- **Phase 3 in full** — the reference panel cannot be opened on any table this environment
  offers, so the reference grid, the range selection, the copy path and the alignment band
  have nowhere to run.
- **Phase 2.2** (reference tab default-active) — same reason.
- **Phase 1's join-column criterion** (`equals 미상` returning the unresolved rows, and the
  `⇲` mark on the chip) — no join-resolved column exists to filter, so this is
  **NOT MEASURED**. It is not "working" and it is not "broken".

This is a lead-PM matter, not a design one: making them reachable means registering tables
in `table_config.json`, which is server territory.

### ③ Phase 3 still needs a decision I am not allowed to make alone

Unchanged from the previous report, restated because it is still open and still blocking.

`MIGRATION_2b.md` Phase 3.1 adds `fill_targets` to each `reference_views[i]`. Measured: the
client-facing projection in `enrichment_config.py` emits reference views as
`{label, candidate_for}` only, and `_normalize_reference_views` drops any key it does not
name. So `fill_targets` costs two server edits plus a change to the owner's gitignored
`server/config/enrichment_rules.json` — against the migration's own premise 「서버 계약 변경 0」.

`candidate_for` already answers the same question: `{target_field: view_result_column}`,
declared by the owner, normalized, projected to the client, key order = declaration order.
It carries more than `fill_targets` does, and it is a declaration rather than a guess.

**Ruling needed before any Phase 3 code exists.** None has been written.

---

## Walked it in Chrome — what passed, and what could not be reached

Dev server on 5173, `lot_event`, 142 rows, live API. 🔴 **The server serves the MAIN tree, not
this worktree** — the preview harness refuses a `cwd` outside the project root, so what was
under test is the four files I left in the shared tree. For `grid.js`, `style.css`,
`index.html` and `dom.js` that is byte-identical to what is committed here. `main.js`,
`api.js` and `enrichment_reference_view.js` were **not** under test; verified by marker
(`SIDEBAR_WIDTH_KEY` absent from the served bundle), not assumed.

**Passed:**

```
system columns have no filter box      the floating row ends after WAFERIDS; the five system
                                       columns' filter cells are structurally EMPTY in the
                                       accessibility tree, not merely blank-looking
column filter changes Matches          LOT_ID contains NAB539 -> Matches 142 -> 16
                                       + EVENT_TYPE contains split -> 16 -> 8
chip renders what was typed            "LOT_ID contains NAB539", "EVENT_TYPE contains split"
chip ✕ clears only that filter         cleared LOT_ID -> Matches 8 -> 78, EVENT_TYPE chip and
                                       its input survive, LOT_ID input emptied
전체 해제 appears from the 2nd chip     display none at 1 chip, block at 2
sidebar width                          640px exactly
four tabs at 640px                     68 + 120 + 101 + 105 = 394px, no row overflow, no tab
                                       clipped (measured scrollWidth vs clientWidth)
underline variant                      active tab box-shadow = inset 0 -2px 0, the mockup value
+N열 → is the REAL number              scrollWidth 1950 vs clientWidth 1869 = 81px hidden = one
                                       column -> "+1열 →"; scrolled fully right -> badge empty
                                       and display:none
```

**NOT MEASURED** (recorded as not measured, not as absent):

```
join-column filter + ⇲ chip mark    no active virtual join rule exists — see ④
sidebar width persistence           code is in this branch only, not in the served tree
reference tab default-active        same, and no reachable table — see ④
```

## What I left in the main tree, and why

Per the brief I did not revert it. Four files, all mine, none shared with another lane:

```
client2/src/grid.js     +169 -2     client2/index.html    +22 -2
client2/src/style.css   +121 -1     client2/src/dom.js     +4  -0
```

The lead's 171 for `grid.js` is the same measurement (169 added + 2 removed).

**Why each:**

- `grid.js` — system columns showed a filter box under `ROW_ID`/`CREATED_AT` because
  `defaultColDef.floatingFilter` was true and `filter` was set unconditionally, so read-only
  columns were still queryable: a second vocabulary. Added `filter: false` +
  `floatingFilter: false` for them, and the same pair on the pre-change-server virtual
  branch (this is the edit that broke ① ). Added `floatingFiltersHeight: 28` and
  `suppressFilterButton`. Added the filter-chip renderer reading `getFilterModel()`, with a
  per-chip `✕`, a 「전체 해제」 from the second chip on, `⇲` on predicates the server resolves
  through a join, and a `+N열 →` count measured against the horizontal pixel range.
- `index.html` — the chip strip above the grid, mirroring `#tx-filter-banner`; 참조뷰 moved
  to the first tab; `history-tabs--wide` added to the tab row.
- `style.css` — the strip and chip styles, sidebar 400px -> 640px, and a
  `.history-tabs--wide` variant that leaves every `.tab-btn` rule untouched.
- `dom.js` — four getters for the strip's elements.

**Nothing there has been opened in a browser.** Not by me, and I do not intend to open the
owner's screen while they are on it.

**Not done, deliberately:** sidebar width persistence, the reference tab becoming
default-active, all of Phase 3, all of Phase 4.

**One defect I found and did NOT fix** (it is next to the ordered change, not in it): the
three tab handlers in `main.js` and the table-switch reset in `api.js` clear `active` from
global/cell/row but never from `tab-reference`. Harmless while that tab is last and hidden;
the moment it becomes the default tab, two tabs are highlighted at once.

---

## Three measurements that contradict `MIGRATION_2b.md`

Recorded so the next round does not re-derive them.

**Phase 1 is roughly half already landed.** `defaultColDef` already carried
`floatingFilter: true`; `onFilterChanged` already called `fetchData(true)`; the join-resolved
filter definition and its six options already existed. The column filter row is in the
current production bundle.

**Phase 1.5's stated risk does not exist.** The order says a virtual-column filter sent via
`?cols=` would be silently dropped. The filter model does not travel on `?cols=` at all —
`fetchData` puts `getFilterModel()` on a separate `&filters=` parameter, and `grid.js`
records that the server binds those columns to `resolved_expression` and answers 400 rather
than an unfiltered 200. `?cols=` is the free-text search scope and already unions the
join-resolved names. Nothing to fix, no disabled filter needed.

**Phase 1.6 dissolves.** `#global-search` and `#search-cols` are dead getters in `dom.js` —
neither id exists in any HTML in this repo. There is no multi-column free search in use
because there is no control on screen, so there is nothing to preserve, nothing to delete,
and 「현행 `#global-search` 자리」 is not a place chips can go. I put the strip above the grid.

**`state.isVirtualColumn(colId)` (Phase 3.4) is not callable as written** — `isVirtualColumn`
is a named export of `state.js`, not a property of `state`.

---

## Environment

```
worktree   C:/Users/kk980/Developments/assyManager-design   branch design
sync       git fetch origin && git merge origin/main   -> clean, at d2c9f610
deps       client2/npm install   OK
orders     task/DESIGN_ORDERS.md   absent
```

Builds run here, never in the main tree. The 8080 screen is the lead's and serves main; I
will stand up my own dev server in this worktree when a round needs one.

**대기 중. 다음 라운드를 지시받기 전에는 스스로 일감을 만들지 않습니다.**
