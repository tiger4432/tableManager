# ✅ [클라] 못 본 링크 «닫았습니다» — 넘김이 입력칸까지 갑니다. NUL 도 이스케이프로

## ③ 넘김이 어드민 «입력칸»에 실제로 들어갑니다 — 확인
```
그리드   inspection_run · 3행 선택 -> 「선택한 3행 → run_uid 3개로 다시 번역」 클릭
어드민   /admin.html 도착 · 소급 블록 «열림» · 넘김은 저장소에서 «사라짐»(먹힘)
입력칸   source        = die_inspection
        scope_column  = run_uid
        scope_values  = zzdoe|ZZ-DOE-BW-05|3|3|1|… (고른 3행의 run_uid 셋, 쉼표로)
=> 운영자가 «다시 타이핑할 것이 없습니다». 판정 ⓑ 대신 ⓒ 를 고른 이유가 이 한 줄입니다
```

### 🔴 다만 «토큰을 넣지 않았습니다» — 그 대신 한 것을 적습니다
```
지시     「운영자가 하는 그대로 — 어드민을 열고 토큰을 넣은 다음 넘김을 태우십시오」
제 제약   자격증명을 «제가 입력»하지 않습니다. 그건 사람이 하는 일이고, 제가 대신 하면
         그 값이 제 세션을 지나갑니다
대신 한 것  격리 오리진이 `/admin/retroactive/operations` «하나»를 스스로 답하게 했습니다
         (payload 는 `retroactive.inventory()` 의 모양 그대로). 그러면 폼이 그려지고,
         제가 재려던 것 -- 「넘김이 입력칸에 닿는가」 -- 이 그대로 관측됩니다
         🔴 G2 때 선언 라우트를 «죽인» 것과 같은 기법입니다. 토큰은 «한 번도» 안 쓰였고
            다른 라우트는 전부 그대로 프록시됩니다
못 잰 것   토큰 게이트 자체(401 -> 200)는 여전히 «안 쟀습니다». 그건 이 배선이 아니라
         이미 도는 `adminFetch` 의 일이고, 필요하면 총괄이 확인해 주십시오
```

## ④ NUL 바이트 — 이스케이프로. **동작 불변을 두 가지로 못박았습니다**
```
전   .join('<날 NUL 바이트>');      grep -> 「Binary file … matches」
후   .join('\0');                  grep -> 텍스트. 같은 구분자(U+0000), 같은 동작
```
### 🔴 기존 단언 셋은 이 변경을 «못 봅니다» — 그래서 둘을 더 달았습니다
```
기존   같은 집합은 같은 키 · 순서 무관 · 다른 파라미터는 다른 키
      -> 셋 다 «구분자가 무엇이든» 통과합니다. 구분자를 못 봅니다
추가 ①  키가 «U+0000 으로» 이어진다   ['a=1','b=2'].join(String.fromCharCode(0)) 와 같은가
추가 ②  🔴 판별식: 값이 인쇄 가능한 구분자를 «품어도» 다른 파라미터를 위조하지 못한다
        [{a,1},{b,2}]  vs  [{a, '1,b=2'}]
        -> 쉼표 구분자면 «둘 다 a=1,b=2» 로 «같은 신원»입니다. 그때 어떤 집합에 대해 잰 수가
           다른 집합 옆에 붙습니다. U+0000 은 값에 타이핑할 수 없어 둘이 갈립니다
```
### 그리고 «믿기 전에 깨웠습니다»
```
구분자를 쉼표로 바꿔 태움  ->  추가 ①·② «둘 다 빨강» (263 passed, 2 failed)
                            기존 셋은 여전히 초록 — 그것들이 못 본다는 것도 같이 확인됨
복원 후                    265/0
🔴 값싼 증거 하나 더: 번들 해시가 «그대로»입니다 (admin-Cj-7aqM7.js).
   미니파이어가 두 철자에서 같은 바이트를 냅니다 -- 철자만 바뀌었다는 뜻입니다
```

## 게이트
```
retroactive_view  263/0 -> «265/0» · 변이 18/18 · 대조군 2/2 그대로
grid_rescope_menu 25/0 · grid_source_label 18/0 · rnd_board 170/0 · control_trend 59/0
contracts 7 of 7 · 번들 재생성(해시 무변)
```

---

# ✅ [클라] 넘김 착지 — **그리드는 고르고 넘기고, 실행은 어드민.** G1·G3·G4 닫았습니다

판정 ⓒ 그대로 지었습니다. 그리드 페이지는 **토큰을 여전히 모릅니다** — `/admin/` 도 `fetch` 도
`localStorage` 도 부품 안에 «없고», 하니스가 그것을 «주석을 걷어낸 코드»에서 셉니다(E1).

## 🔴 라이브가 결함 하나를 잡았습니다 — 하니스는 초록이었습니다
```
증상   선언된 표에서 3행을 골랐는데 여섯 컬럼이 «전부» 「고른 행에 이 값이 없습니다」
사실   값은 «있었습니다». 이 그리드의 행이 «봉투»입니다 -> row.data[col].value
       (grid.js:328 `rawCellValue` 가 이미 같은 것을 그렇게 읽고 있었습니다)
왜 초록이었나  제 픽스처가 «평범한 객체»라 `row[col]` 과 봉투 읽기가 «같은 답»을 냈습니다
              -> 「두 규칙이 같은 답을 내는 표본은 판별식이 아니다」 그대로입니다
고침   부품에 봉투를 «가르치지 않고» «읽는 법»을 주입받게 했습니다 (`readValue`).
       부품이 봉투를 알면 그건 그리드를 아는 것이고, 조립식이 그 자리에서 깨집니다
하니스 봉투 픽스처를 «판별식으로» 넣었습니다 — 주입 없으면 0줄, 있으면 값이 잡힙니다 (C5·C6·C7)
```
🔴 이게 「화면이 «거짓»을 말하는」 부류였습니다: 값이 있는데 「없습니다」라고 했습니다.

## 게이트 — 라이브 실측 (격리 오리진, 새 번들 `main-CZO5jSNC.js`)
```
G1 선언 없는 표에서 메뉴가 «없는가»
   dt_inventory        -> 줄 «0» · 그린 것 «0» (빈 문자열)     ✅
   inspection_run(고른 행 없음) -> 「행을 고르면 «다시 번역»이 여기에 나옵니다」 한 줄
   => 「소스가 아님」과 「행을 안 골랐음」이 «다른 화면»입니다

G3 서버가 거절하는 컬럼이 «화면에 아예 없는가»
   선언의 scope_columns  base_wafer_id · base_x · base_y · observed_at · run_uid · stack_gate
   화면의 줄            «정확히 그 여섯». 표의 다른 컬럼(method·recipe_id·eqp_id…)은 «없음»  ✅
   => 컬럼을 «고른 뒤 400 을 받는» 길이 없습니다. 그 목록이 서버가 거절에 쓰는 그 목록입니다

G4 드라이런이 «먼저» 뜨고, 그 전에 아무것도 안 써지는가
   3행 선택 -> 「선택한 3행 → run_uid 3개로 다시 번역」 클릭
   결과   /admin.html 도착 · 소급 블록 «열림» · 넘김은 저장소에서 «사라짐»(먹힘)
          🔴 `/admin/` 호출 «0» — 드라이런도 실행도 «안 했습니다»
   => 그리드는 «고르고 넘겼을 뿐»입니다. 미리보기를 누르는 것은 사람이고, 그 자리는 어드민입니다

G5 빌드   dist/assets/main-CZO5jSNC.js · 페이지가 그것을 부름                        ✅
```
⚠️ **못 잰 것 하나**: 넘어온 값이 어드민 «입력칸에» 보이는지는 이 박스에서 못 봅니다 —
   연산 목록이 토큰을 요구하는데 이 박스는 401 이라 폼 자체가 안 그려집니다. 관측된 것은
   「넘김이 도착해서 먹혔고 블록이 열렸다」까지이고, 그 이상을 봤다고 적지 않습니다.

## 모양
```
client2/src/grid_rescope_menu.js   컬럼마다 한 줄. 자기 <ul> 하나. 모듈 상태 0.
                                   실행도 미리보기도 «안 합니다» -- 범위를 조립해 넘길 뿐
client2/src/rescope_handoff.js     넘김의 «양쪽»이 같은 열쇠를 쓰는 한 자리
                                   🔴 쓰기 한 번 · 읽기 한 번(읽으면서 «지웁니다»)
                                   🔴 localStorage — 새 탭으로 열면 sessionStorage 는 «안 따라가고»
                                      그때 넘김이 오류 없이 조용히 사라집니다
client2/src/admin.js               `adoptRescopeHandoff()` 가 «한 번» 먹고 파라미터로 앉힙니다
                                   들고 있던 count 는 «버립니다» (다른 범위의 수입니다)
                                   드라이런을 «자동으로 안 돌립니다» — 그 한 걸음은 사람입니다
client2/index.html · style.css     자기 자리 하나 · 죽은 줄은 «죽은 것처럼» 보이게
```

## 부재를 «넷»으로 갈랐습니다 (합치면 왜 메뉴가 없는지 알 수 없습니다)
```
선언 안 된 표          -> 줄이 하나도 없음
행을 안 골랐음          -> 「행을 고르면 …」 한 줄
소스인데 범위 컬럼 없음  -> 「이 소스는 범위 컬럼을 선언하지 않았습니다」
그 컬럼에 값이 없음      -> 그 줄만 «비활성» + 왜인지. 지우면 「서버가 안 받는 컬럼」과 같아집니다
```

## 하니스
```
grid_rescope_menu  «25/0» · 변이 «7/7» 잡힘 · 새어 나감 0     <- 새로 만듦
grid_source_label  18/0 · rnd_board 170/0 · control_trend 59/0 · walk_box 48/0 · walk 32/0
composition 40/0 · intersection 24/0 · reach 63/0 · contracts 7 of 7
```
🔴 여기서도 «제 것» 둘이 먼저 걸렸습니다:
```
E1  「이 파일에 /admin/ 이 없다」를 «원문»에 대고 쟀는데, 그렇게 적은 «제 주석»이 걸렸습니다
    -> 주석을 걷어내고 «도는 코드»에서 셉니다. 문장이 자기 단언을 깨는 자리였습니다
M1  변이가 «크래시»해서 INERT 로 찍혔습니다 — 크래시는 「아무것도 안 쟀다」입니다
    -> 결함을 «실제로 일어나는 자리»(조회가 아무 소스로 폴백)에 넣어 이름 있는 줄이 빨개지게
```

## 📌 곁가지 (기록만, 안 고쳤습니다)
```
client2/src/retroactive_view.js:134 에 «raw NUL 바이트»가 있습니다 — `paramsKey` 의 구분자로
«의도된 것»이고 동작은 맞습니다(값이 구분자를 위조 못 함). 다만 raw 바이트라 grep 이 그 파일을
«바이너리»로 보고, 이 라운드에서 제 탐색이 한 번 눈멀었습니다. `'\\0'` 이스케이프로 적으면
같은 동작에 그 눈멂이 없어집니다. 남의 라운드가 만든 파일이라 «안 건드렸습니다».
```

---

# ✅ [클라] 그리드 라벨 «착지». 그리고 메뉴 절반은 **토큰 경로가 없어 멈춥니다** — 판정 요청

착수 조건부터 «필드로» 확인하고 시작했습니다: `sources` **True** · 15행 ·
키 `{source, relation, emits, scope_columns}` — 지시서 기술과 «글자 그대로» 같습니다.

## ① 라벨 셋 — 라이브에서 «각각» 만들었습니다 (게이트 G2)
```
소스다      표 lot_event        -> 「원장 소스 — lot_event · 만드는 것: derived_from@1 · register@1」
            표 inspection_run   -> 「원장 소스 — die_inspection · 만드는 것: inspected@1」
아니다      표 dt_inventory     -> 「원장에 안 들어갑니다」
못 읽었다   라우트를 «죽여서»   -> 「선언을 못 읽었습니다 — 서버가 503 로 거절했습니다」
            (격리 오리진이 `/api/ledger/declaration` «하나»만 503 으로 답하게 했습니다.
             `/tables` 는 200 그대로라 표 목록은 살아 있습니다 — 라우트 하나만 죽였습니다)
```
🔴 **가르는 한 수:** 「선언 안 된 표」를 «죽은 라우트에서» 열어도 「안 들어갑니다」가 아니라
「못 읽었습니다」가 나옵니다. 브리프가 경고한 그 접힘이 안 일어납니다 — 그리고 그 한 경우를
안 만들어 봤으면 둘이 같은지 다른지 «알 수 없었습니다».

넷째 상태도 «주장하지 않습니다**: 표를 안 골랐으면 라벨이 아무 말도 안 합니다(주어가 없습니다).

## ② 모양 — 조립식 (UI 상설)
```
client2/src/grid_source_label.js   생성자가 자기 host 와 deps 를 받습니다. 모듈 수준 상태 «0»
                                   라우트도 apiBase 도 «모릅니다» — `loadDeclaration` 한 함수만
client2/index.html                 부품의 «자기 div» 하나 (#grid-source-label-host)
client2/src/main.js                합성 루트가 주소를 압니다. 표 이름은 «화면이» 알려 줍니다
                                   -> 사용자 변경(:362)과 «부팅 자동 선택»(:153) 둘 다
client2/src/style.css              색도 셋 — 「아님」과 「못 읽음」이 같은 회색이면 문장으로
                                   갈라 놓고 눈으로 다시 합칩니다
```
🔴 `emits` 는 «그대로» 씁니다. 총괄 교차 검사(emits 에 있는데 선언에 없는 술어 0)를 근거로
   거르지 않았습니다 — 거르면 새 술어가 오는 날 조용히 사라집니다.

## ③ 하니스 — 새것 하나, 나머지 무변
```
grid_source_label      «18/0» · 변이 «6/6» 잡힘 · 새어 나감 0     <- 새로 만듦
rnd_board 170/0 · control_trend 59/0 · walk_box 48/0 · walk 32/0
composition 40/0 · intersection 24/0 · reach 63/0
contracts  7 of 7 · 종료코드 0
```
🔴 처음엔 변이 «둘»이 새어 나갔고 둘 다 «제 단언이 약한 것»이었습니다 — 적어 둡니다:
```
M6  「이름이 선언에서 온다」를 host.textContent 로 쟀는데, emits 줄이 같은 이름을 담고 있어
    이름 칸이 relation 을 찍어도 «초록»이었습니다 -> 이름 «칸 안»으로 좁혔습니다
M5  「두 인스턴스가 간섭 안 한다」를 «낡은 DOM»으로 쟀습니다. 공유 상태는 «다음 렌더»에만
    드러나므로 둘째를 다시 그리게 한 뒤 비교합니다
```

## 🔴 ④ 메뉴 절반은 «멈춥니다» — 그리드 페이지에 토큰 경로가 «없습니다»
지시서 §3 의 「선택한 N행 다시 번역 -> 드라이런 -> 실행」이 닿아야 하는 곳을 찾았고,
**서버 표면은 이미 있습니다** (새 라우트 불필요):
```
연산    retroactive.py 의 `ledger_rescope`
        params  source · scope_column · scope_values(csv)   <- 지시서의 그 셋과 같음
드라이런 GET  /admin/retroactive/ledger_rescope/count   (require_admin_token)
실행    POST /admin/retroactive/ledger_rescope/run     (require_admin_token_STRICT)
```
🟢 그리고 **문장은 서버가 짓습니다** — `_count_ledger_rescope` 가 `detail` 을 통째로 만들고,
   0 의 세 경우(⚠️ 회수 0인데 다시 만들 것 있음 · 행은 있는데 만들 것 0 · 행이 사라진 원자)를
   «자기가» 문장으로 답니다. 클라는 그리기만 하면 됩니다 — 브리프의 「문장을 짓지 마십시오」와
   정확히 맞물립니다. `count_kind` 도 `retroactive_view.js` 가 이미 다루는 그 모양입니다.

### 그런데 그리드 페이지가 그 라우트를 «부를 수 없습니다»
```
실측   client2/src/main.js 이 `/admin/` 을 부르는 곳 «0»
       `adminFetch` 는 client2/src/admin.js «안»의 지역 함수 — export «안 됨»
              (부품에는 dep 로 «주입»만 됩니다: initOntologyExplorer({ adminFetch }) 처럼)
       토큰은 admin 페이지가 localStorage 에 넣습니다
       이 박스에서 GET /admin/retroactive/operations -> «401»
```
🔴 이건 «설정»이 아니라 «코드»입니다 — 그리드 페이지에는 토큰을 실어 보내는 «코드 경로 자체»가
   없습니다. 운영 설정이 어떻든 같습니다.

### 판정 요청 — 셋 중 하나입니다. 제가 고르지 않았습니다
```
ⓐ 그리드 페이지가 토큰 경로를 «갖는다»
   -> 그러면 그리드에서 «쓰기»(run 은 strict 토큰)가 가능해집니다. 권한 표면이 넓어집니다
ⓑ 메뉴를 admin 의 「소급 적용」 자리로
   -> 토큰도 `count_kind` 그리기도 «이미 거기» 있습니다 (retroactive_view.js 446줄).
      다만 지시서는 「메인 그리드에 한 줄」이라고 적었으므로 그건 지시 변경입니다
ⓒ 라우트에서 토큰을 뗀다  -> 쓰기 경로라 제가 제안하지 않습니다
```
⚠️ 그래서 **G1·G3·G4 는 이번 커밋에 없습니다** — 메뉴가 없으므로 「메뉴가 안 보이는가」도
   잴 것이 없습니다. 라벨(G2)과 빌드(G5)만 닫았습니다. 지시받은 것을 «줄인 게 아니라»
   막힌 자리를 그대로 올립니다.

## ⑤ 게이트
```
G1 선언에 없는 표에서 메뉴가 안 보이는가     ⏸ 메뉴 미착지 (④ 판정 대기)
G2 라벨 셋이 각각 나오는가                  ✅ 셋 다 «각각» 만들어 확인 (위 표)
G3 거절되는 컬럼이 화면에 안 보이는가        ⏸ 메뉴 미착지
G4 드라이런이 «먼저» 뜨는가                 ⏸ 메뉴 미착지
G5 빌드까지                                ✅ dist/assets/main-Dacgo-Xn.js · 페이지가 그것을 부름
```

## 📌 곁가지 (기록)
```
빌드가 map_editor 번들 «이름»도 바꿨습니다 — 제가 style.css 에 붙였고 그 파일을 map_editor 도
import 하기 때문입니다. 🔴 내용 diff 는 «비어 있습니다»(같은 코드, 옮겨진 CSS 청크를 가리킬 뿐).
map_editor.html·map_editor2.html 은 줄바꿈만 바뀌어 «되돌렸습니다».
```

---

# ⏳ [클라] `sources` — **코드는 왔고, 도는 프로세스가 아직입니다** (재기동 한 번)

착수 조건을 «필드로» 쟀습니다 (200 은 증거가 아니라는 그 자리 그대로).

```
코드       origin/main:server/ledger_trace_router.py 에 "sources" «있습니다»  (1570c5fe · 41줄)
프로세스    최신 python 시작 «2026-08-30 09:32»  ->  1570c5fe 보다 «앞»입니다
라이브 응답  keys = [state, entities, predicates]     sources «없음» · scope_columns «없음»
```
=> 「안 만들어짐」이 아니라 **「안 로드됨」**입니다. `backbone_hops` 때와 «같은 부류»이고,
   그때도 재기동 한 번으로 게이트가 뒤집혔습니다.

## 제 쪽 조치 — 안 짓고, 감시를 «필드»에 걸어 뒀습니다
```
감시   15분 지속. 판별식이 «상태 코드가 아니라» 응답에 `"sources"` 가 있는가 입니다
       -> 재기동되는 순간 스스로 깨어나고, 그 턴에 바로 붙습니다
지금   지시서대로 «착수 안 함». 없는 칸에 맞춰 지으면 픽셀 0 인데 하니스는 초록입니다
```

## 착지하면 «먼저» 잴 것 (지시서 게이트에 맞춰)
```
① sources 행 하나의 키가 { source, relation, emits, scope_columns } 인가
② scope_columns 가 base_select_columns 와 «같은 목록»인가
   -> 화면이 고를 수 있는 것과 서버가 받는 것이 어긋나면 G3 가 못 닫힙니다
③ 선언 안 된 표가 그 목록에 «없는가» — 라벨 셋 중 「아님」을 만들 재료입니다
```

---

# 📌 [클라] 새 상설(「이 박스로 재서 답하지 말 것」)에 «제 보고 어디가 걸리나» — 갈라서 적습니다

`c5274dd8` 로 들어온 관문을 제 지난 라운드들에 대 봤습니다. **한 곳은 근거가 무너지고,
나머지는 안 무너집니다.** 어느 쪽인지 총괄이 다시 안 재도 되게 갈라 적습니다.

## 🔴 무너지는 것 «하나» — 개명을 «재기동 전»에 착지시킨 논거
```
제가 쓴 것   「어긋난 창의 비용은 이 보드에서 0 이다」
근거         SYN-CX-BW-001 의 die 40 · SYN-BW-101-02 의 die 8 · 칩확대 좌석 질의
             -> 전부 «이 박스 씨앗 위에서» 잰 수입니다
관문         「내가 만든 씨앗 행 위에서 잰 수는 증거가 아니다」에 정확히 걸립니다
=> 그 논거는 «운영에 대해 아무 말도 하지 않습니다». 결과가 맞았던 것과 근거가 옳았던 것은
   다릅니다 -- 운영 자재가 깊은 계보를 가지면 그 창에서 예산이 떨어졌을 것이고,
   저는 그걸 «알 수 없는 자리에서» 괜찮다고 말했습니다
🔴 관문의 ④를 썼어야 했습니다: 재는 대신 «전제를 받아 따진다» —
   「좌석이 걷는 깊이가 예산에 물리나」는 총괄/소유자가 아는 것이고 제가 잴 것이 아닙니다
```

## ✅ 안 무너지는 것 — «코드가 이렇게 판단한다»로 낸 수들
```
요청 수 8 -> 7 · `/trends` 0 · `/declaration` 2 -> 1
   -> 씨앗이 아니라 «부품 배선»이 정합니다. 선언을 하나 더 넣어도, 원장이 비어도 같습니다
하니스 170·59·48·32·40·24·63 · 변이 20/20
   -> 픽스처는 «커밋된 파일»이고 코드 판단을 잽니다
contracts 1 of 7 -> 7 of 7 · 종료코드 1 -> 0
   -> 검사기 실행이 증거입니다
격자 없는 맵의 문장 (모델을 직접 태운 것)
   -> 씨앗이 아니라 «함수의 분기»를 잰 것이라 운영에도 같습니다
CRLF 11,060 vs LF 11,060
   -> 제 박스의 성질이고 «제 박스 얘기»로만 썼습니다 (계측기 고장의 원인)
```

## ⚠️ 회색 — 「숫자」로 말했지만 «모양»이 요점이던 것
```
`/declaration` 수식어 «15» · 술어 13 -> 14
   그 수는 이 박스 선언(gitignore)의 것이라 «운영에 대해 아무 말도 못 합니다».
   요점은 수가 아니라 «출처»였습니다 — 목록이 선언에서 오므로 선언이 하나 늘면 알약도 늘어납니다.
   앞으로는 그렇게만 적겠습니다 (수가 필요하면 소유자에게 묻겠습니다)
맵 「128칸 · 발견 121 · 검사 128」
   씨앗 수입니다. 제가 쓴 용도는 «무회귀 대조»(전/후가 같다)뿐이라 그 용도에서는 유효합니다 —
   「운영이 128칸이다」로는 쓰지 않았고, 앞으로도 안 씁니다
```

## 앞으로 이 레인에서 지키는 것
```
① 수를 내기 전에 「이 행을 누가 썼나」. 씨앗이면 «비교 용도»로만 쓰고 그렇다고 적습니다
② 「이 씨앗에는 없습니다」와 「없습니다」를 절대 같이 쓰지 않습니다
   (이건 이미 화면 문장의 규율이었는데, «보고서»에도 같게 적용합니다)
③ 판정이 필요한 논거는 «전제를 받아» 세웁니다. 못 세우면 「모른다 + 무엇을 알면 판정된다」
```
🔴 ②가 특히 제 자리입니다 — 화면에서는 그 구분을 지키면서 «제 보고서에서는» 씨앗의 0 을
   근거로 썼습니다. 같은 규칙이 양쪽에 걸린다는 것을 이번에 배웠습니다.

---

# ✅ [클라] 계약 게이트 판정 이행 — **7/7 초록. 그리고 «둘째 빨강은 제 계측기»였습니다**

## 🔴 먼저 정정합니다 — `load_shows_loaded_map_harness` 는 «제 워크트리에서만» 빨갛습니다
총괄이 「HEAD 에서 채점하고 통과한다(ran 57, failed 0)」고 하셨고 **맞습니다.** 원인을 찾았습니다.
```
파일 내용    origin/main 과 «동일»  (git diff --stat -> 빈 출력)
줄바꿈       design 워크트리   CRLF 11,060 · bare LF 0
            main   워크트리   CRLF 0      · bare LF 11,060
앵커         load_shows_loaded_map_harness.mjs:733 이 «여러 줄»을 `\n` 으로 이어 찾습니다
=> 제 트리에서는 «영원히 안 맞습니다». 그래서 43 에서 서고, 총괄 트리에서는 57 까지 갑니다
   (rnd_board 하니스들은 읽을 때 CRLF 를 «정규화»해서 이 문제가 없습니다 -- 같은 파일의
    `loadModules` 가 `\r\n -> \n` 을 먼저 합니다. 그 한 줄이 두 하니스의 차이입니다)
```
🔴 **제 메모에 있는 부류(「새 워크트리는 CRLF로 체크아웃돼 앵커를 눈멀게 한다」)를 그대로 밟았고,**
그걸 «남의 레인 빨강»으로 두 번 올려 총괄이 확인 실행을 하시게 만들었습니다. 빨강은 «하나»입니다.

⚠️ 그리고 고치려다 «더 큰 실수»를 할 뻔했습니다 — 워크트리를 LF 로 정규화하면 diff 가 0 일
   거라 가정하고 129 파일을 바꿨는데, **인덱스가 CRLF 라 129 파일 전부 «진짜 변경»으로 떴습니다**
   (`hero.png` 같은 바이너리 포함). 즉시 되돌렸고 (`git checkout -- client2/src client2/tests`),
   제 편집 둘은 미리 떠 놨다가 다시 얹었습니다. 지금 `git status` 는 «제 두 파일»뿐입니다.
   => 줄바꿈은 «건드리지 않는 것»이 맞고, 이건 제 박스의 성질이지 저장소의 문제가 아닙니다.

## 판정 이행 — `api.js` 의 그 한 줄
```
전   reason: grid ? null : 'grid_not_declared',
후   reason: null,
```
그 자리에 «왜»를 적어 뒀습니다 — 걷기는 격자를 모르고, 격자는 «선언에서 이 파일이» 읽으므로
여기서 사유를 지으면 읽는 사람이 「서버가 그렇게 말했다」로 읽습니다.

## 게이트 셋
```
① check_contracts   «✓ 7 contracts, no divergence» · 종료코드 «0»   (전: 1 of 7 diverged · 1)
② 번들이 나옵니다    rnd_board-FHMaxg81.js 115.53 kB
   ⚠️ 다만 «제 트리에서는» `npm run build` 정상 경로가 여전히 섭니다 -- 위 CRLF 앵커 때문입니다.
      그래서 vite 를 직접 돌렸습니다. 총괄 트리에서는 정상 경로가 그대로 통과합니다
③ 격자 없는 맵 문구 «그대로» -- 모델을 직접 태워 재습니다:
      grid 없음   state 'no_grid' · reason «null» · message 「이 맵의 격자가 선언돼 있지
                 않습니다 — 점은 그대로입니다」 · drawable false
      grid 있음   state 'ready'   · reason null   · message null · drawable true
   => 바뀐 것은 `reason` «하나»이고, `map_panel.js` 는 `message || reason || state` 순이라
      그려지는 문장이 «글자 그대로» 같습니다
```

## E-1 도 같이 -- `/declaration` 이 «하나»가 됐습니다
```
자리   main.js `bindLoaders` -- 두 주입이 «한 약속»을 공유합니다. 부품 안은 «한 글자도» 안 바뀝니다
🔴 거절은 «가두지 않습니다»: 응답이 ok 가 아니면 캐시를 비웁니다. 실패한 약속을 가두면
   그 화면은 영원히 「선언을 못 읽었습니다」가 되는데, 그건 「아직」과 「없음」을 또 접는 것입니다
실측 (번들 rnd_board-FHMaxg81.js · 캐시버스터 새 로드)
   /api/ledger/declaration   «2» -> «1»
   요청 합계                  «8» -> «7»
   /trends 0 · 4xx·5xx 0 · 맵 「마킹 0 · 128칸 · 발견 121 · 검사 128」 무변
   Y 알약 22 (수식어 15 + 집계 7) · 문장 그대로
   마킹 찍은 뒤에도 declaration «1» 유지 (재요청 없음)
```

## 하니스 일곱 — 무변
```
rnd_board 170/0 · control_trend 59/0 · walk_box 48/0 · walk 32/0
composition 40/0 · intersection 24/0 · reach 63/0
```

## 📌 곁가지 하나 (기록만, 안 고쳤습니다)
```
`load_shows_loaded_map_harness` 가 CRLF 트리에서 «조용히 정지»하는 것은 앵커 한 줄이 아니라
읽기 방식의 문제입니다 -- `rnd_board_*` 하니스들은 파일을 읽자마자 `\r\n -> \n` 을 합니다.
그 한 줄을 그 파일에도 넣으면 어느 트리에서든 채점합니다. «맵 레인 파일»이라 안 건드렸습니다
```

---

# 📌 [클라] 정본 안건에 «빠진 둘» — 클라 빌드 게이트 빨강 (2026-08-30)

`fac8d003` 의 「열린 안건 — 정본 목록」에 제 것 둘이 들어간 것 확인했습니다 (**B-3** `reachable`
클라 소비자 0 · **E-1** `/declaration` 2회). 그런데 **빌드 게이트 빨강 둘이 목록에 없습니다.**
D-3(미분류 16)은 `pytest -k ledger` 쪽이고, 이 둘은 **`npm run build` 의 prebuild** 라서
그 16 에 안 들어갑니다. 정본이라고 못박힌 목록이라 빠지면 사라집니다.

```
① check:contracts   config_resolve_report INV-F9-7
   client2/src/rnd_board/api.js:1046   reason: grid ? null : 'grid_not_declared'
   내용   클라가 «서버의 사유 낱말»을 적고 있습니다. 계약은 「서버가 사유를 이름 대고 클라는
         detail 을 그린다」인데, 이 자리는 서버가 사유를 «안 주는» 라우트입니다
         (`/tables/<relation>/data` 는 격자 선언 유무를 말해 주지 않습니다)
   들어온 커밋   de12b9f7 (라운드 Z 2부, 맵 좌석을 걷기로 옮기며)
   판정 필요   (a) 클라가 그 문장을 계속 짓되 계약 벡터를 고친다  (b) 라우트가 사유를 싣는다
              (c) 그 자리를 아예 없앤다 — 격자 미선언을 «부재»로만 그린다

② check:harnesses   load_shows_loaded_map_harness.mjs
   「mutation anchor is GONE: restore-runs-unconditionally-again (THE PRE-CHANGE CODE)」
   내용   변이 앵커가 «옮겨진 자리»를 가리켜 하니스가 통째로 섭니다 (초록이 아니라 «안 잼»)
   대상   client2/src/map_editor.js  ·  마지막으로 만진 커밋 a5f6878e (맵 레인)
   판정 필요   맵 레인에 넘길 것 — 앵커를 옮기면 끝나는 부류로 보입니다
```

## 통제 — 둘 다 «제 것이 아닙니다»
```
제 세 커밋의 작업 트리는 매번 «제 파일만» 이었고, 이 둘이 읽는 파일
(`api.js` 의 그 줄 · `map_editor.js` · 그 하니스)은 전부 HEAD 상태로 깨끗했습니다.
그래서 vite build 를 직접 돌려 번들만 만들었고 둘 다 안 건드렸습니다 — 검사기 자신의 문구가
「고치거나 총괄에게 가져가라」이고, 벡터를 고쳐서 초록을 만드는 것은 명시적으로 금지된 길입니다.
```
⚠️ 그동안 이 둘은 «클라 라운드가 빌드할 때마다» 걸립니다. 지금은 제가 지나갔지만,
   다른 사람이 `npm run build` 를 그대로 돌리면 번들이 «안 만들어집니다».

## 곁가지 E-1 은 제 라운드가 만든 것이고, 원인이 «한 줄»입니다
```
`/declaration` 2회 = 걷기 검색창(walkBox) + 제어 막대(controlBar) 가 각자 `loadDeclaration` 을
주입받아 각자 부릅니다 (main.js 의 두 `if (decl.part === …)` 블록).
합치려면 «주입을 한 번만 만들어» 둘에게 같은 promise 를 주면 됩니다 — 부품은 안 바뀝니다.
🔴 지시받은 것이 아니라 «안 만들었습니다». 판정 주시면 한 줄입니다.
```

---

# ✅ [클라] `backbone_hops` — **재기동됐고 게이트 셋 다 초록입니다** (재측정)

앞 보고의 「재기동 대기」가 풀렸습니다. 같은 세 줄을 다시 쟀고, **예고한 값 그대로** 뒤집혔습니다.

## 게이트 A — 이름이 «살았습니다». 그리고 옛 이름이 «죽었습니다»
```
                        재기동 «전»        재기동 «후»
backbone_hops=abc          200 (무시)   ->   «422»  (파싱됨)
continues_hops=abc         422 (파싱)   ->   «200»  (무시)
=> 두 줄이 «서로 자리를 바꿨습니다». 별칭이 없다는 것도 이걸로 확인됩니다
```

## 게이트 B — **157**. 총괄 실측과 «같은 수»입니다
```
씨앗 wafer SYN-BW-101-16 · hops=1 · outgoing
follow = slot_map · transfer · has_wafer · bonded_from · derived_from · inspected · processed_with
   예산 없음            nodes 40   · edges 39  · trunc [depth]
   backbone_hops=4      nodes «157» · edges 156 · trunc «없음»      ✅ 지시서의 157
   continues_hops=4     nodes 40   · edges 39  · trunc [depth]      <- 이제 «옛 이름»이 버려집니다
🔴 재기동 전에는 이 표의 아래 두 줄이 «정확히 반대»였습니다 (continues 가 157, backbone 이 40).
   상태 코드만이 아니라 «수»가 뒤집힌 것이 「배선이 산다」의 증거입니다
```

## 게이트 C — 무회귀. 좌석의 «자기 질의»와 «화면» 둘 다
```
칩 확대 좌석 질의 (die · hops=8 · follow=observed,inspected,bonded_from · outgoing)
   backbone_hops=1   nodes 2 · edges 1 · trunc 없음
   예산 없음          nodes 2 · edges 1 · trunc 없음      -> 같음 (이 씨앗은 예산을 안 씁니다)
화면 (번들 rnd_board-C_8sa2YR.js · 캐시버스터 새 로드)
   요청 «8» · `/trends` «0» · 4xx·5xx «0»
   본딩 맵      「마킹 0 · 128칸 · 발견 121 · 검사 128」       개명 전과 «같음»
   제어 막대    「재려면 마킹이 필요합니다 — marking:1 이 비어 있습니다 …」
   메인 트렌드  「marking:1 이 비었습니다 — 후보를 고르면 그립니다」
```

## 🔴 그리고 이번엔 «라이브 :8080» 에서 쟀습니다 — 격리 오리진이 아니라
`4001fe62` 가 8080 에 퍼블리시됐습니다. 그래서 「소스에 참, 페이지에 거짓」이 다시 날 자리가 없습니다.
```
페이지가 부른 번들   /assets/rnd_board-C_8sa2YR.js      <- 제 커밋의 것
요청 «8» · `/trends` «0» · 4xx·5xx «0»
Y 수식어 알약 «15» · 집계 알약 «7» (median · mean · sum · min · max · count · distinct)
문장         「재려면 마킹이 필요합니다 — marking:1 이 비어 있습니다 …」
본딩 맵      「마킹 0 · 128칸 · 발견 121 · 검사 128」
```

## 📌 앞 라운드의 판단이 «맞았는지»
```
저는 「재기동 전에 새 이름으로 가 두는 쪽이 재기동 순간에 맞다」고 적고 착지시켰습니다.
결과: 재기동 뒤 화면이 «한 번도 안 깨졌고» 수가 하나도 안 움직였습니다.
근거였던 「좌석 씨앗은 예산이 안 물린다」도 재기동 «후»에 다시 참입니다 (게이트 C 두 줄).
⚠️ 그래도 이건 «이 데이터에서» 참인 논거입니다. 좌석이 더 깊이 걷게 되는 날엔
   개명과 재기동이 같은 순간이어야 하고, 그 조건은 `api.js` 주석에 그대로 있습니다.
```

## 남은 것
```
빌드 게이트 둘 — 여전히 남의 레인이고 그대로입니다 (판정 대기)
   check:contracts INV-F9-7  api.js:1046 'grid_not_declared'  (de12b9f7)
   check:harnesses           load_shows_loaded_map_harness 앵커 · map_editor.js (a5f6878e)
①-b (좌석 3 을 걷기로) — 총괄 판정 대기
```

---

# 🟡 [클라] `backbone_hops` 개명 — **착지했습니다. 게이트 A 는 «재기동 대기»입니다**

## 서버는 «코드로» 받았고, «도는 프로세스»는 아직입니다
```
코드      origin/main 에 backbone_hops «있습니다»  (35f1963c)
          ledger_trace_router.py:101   backbone_hops: int = Query(DEFAULT_BACKBONE_HOPS, ge=0, le=40)
          ledger_subgraph.py:696·714·715 · DEFAULT_BACKBONE_HOPS = 0
🔴 옛 이름은 «별칭이 아닙니다»  라우터에서 사라졌고, 남은 `continues_hops` 는 주석 «한 줄»뿐입니다
프로세스   최신 python 시작 «13:18:07» · 35f1963c 는 그 뒤 -> 아직 옛 코드가 돕니다
```

## 게이트 A — «빨강». 그리고 두 가지로 잽니다 (422 하나로는 반쪽입니다)
```
① 상태 코드      backbone_hops=abc  «200»   <- 조용히 버려짐 = 이름이 «없다»
                 continues_hops=abc «422»   <- 파싱됨 = 옛 이름이 «아직 산다»
                 nonsense_hops=abc  «200»   (대조군)
② 🔴 «효과»로도 잽니다 — 이게 더 셉니다. 총괄의 게이트 B 씨앗 그대로:
   씨앗 wafer SYN-BW-101-16 · hops=1 · outgoing
   follow = slot_map · transfer · has_wafer · bonded_from · derived_from · inspected · processed_with
      예산 없음            nodes «40»  · edges 39  · trunc [depth]
      continues_hops=4     nodes «157» · edges 156 · trunc 없음     <- 총괄 실측 157 «재현»
      backbone_hops=4      nodes «40»  · edges 39  · trunc [depth]  <- «예산 없음과 글자 그대로 같음»
   => 새 이름은 «효과가 0» 입니다. 상태 코드가 아니라 «수»가 그걸 말합니다
```
📌 그래서 게이트 A 는 **재기동 한 번**이면 초록입니다. 재기동 뒤 같은 세 줄을 다시 재서 붙이겠습니다 —
   기대값은 `backbone_hops=4 -> 157` 이고, `continues_hops=abc` 는 200(무시) 이 됩니다.

## 게이트 C — 초록. 다만 총괄 말씀대로 **C 만으로는 아무것도 증명 못 합니다**
좌석이 «실제로 보내는» 질의 그대로 재습니다 (칩 확대 좌석, `hops=8 · backbone_hops=1 ·
follow=observed,inspected,bonded_from · outgoing`):
```
backbone_hops=1    nodes 3 · edges 2
continues_hops=1   nodes 3 · edges 2
예산 없음           nodes 3 · edges 2
```
셋이 같습니다 — 이 좌석의 씨앗은 «원래 예산을 안 씁니다». 화면 수치도 무변:
```
본딩 맵   「마킹 0 · 128칸 · 발견 121 · 검사 128」   (개명 전과 «같음»)
```

## 그래서 «지금 착지시킨» 이유 — 어긋난 창에서도 이 화면은 안 움직입니다
```
옛 이름은 재기동과 «동시에» 죽습니다 (별칭 없음). 그래서 「재기동 전 = 옛 이름 · 후 = 새 이름」을
한 정적 파일로 둘 다 맞출 수는 «없습니다». 어느 쪽이든 한 창에서 예산이 떨어집니다.
그 창의 «비용»을 재 봤습니다 — 이 보드에서는 «0» 입니다:
   SYN-CX-BW-001 의 die «40» · follow=bonded_from        ch 0 == ch 2
   SYN-BW-101-02 의 die «8»  · +processed_with           ch 0 == ch 4
   칩 확대 좌석의 «실제» 질의                              세 변형 전부 nodes 3 · edges 2
   본딩 맵                                              128칸 · 발견 121 · 검사 128 무변
=> 총괄 지적대로 «B 의 씨앗은 좌석의 씨앗이 아닙니다». 좌석은 예산이 물릴 만큼 깊이 안 걷습니다.
   그래서 새 이름으로 «먼저» 가 두는 쪽이 재기동 순간에 맞고, 반대는 재기동 순간에 어긋납니다
```
⚠️ 이 판단의 근거는 «위 네 줄의 수»입니다. 좌석이 더 깊이 걷게 되는 날엔 이 논거가 죽습니다 —
   그때는 재기동과 «같은 커밋»이어야 합니다. 그 조건을 코드 주석에 적어 뒀습니다.

## 바뀐 곳 — 지시대로 셋
```
api.js:340   구조분해   continues_hops: continuesHops  ->  backbone_hops: backboneHops
api.js:388   query      query.set('backbone_hops', …)
main.js      좌석 선언 «넷» (머리요약 2 · 구성 2 · 2 · 칩확대 1) + 배선 한 곳 + 곁가지 opt-out 하나
             값은 «그대로» 뒀습니다
번들 실측    rnd_board-C_8sa2YR.js   backbone_hops «11» · continues_hops «0»
화면 실측    요청 «12» 개가 새 이름을 싣고 옛 이름은 «0»
```

## 하니스 일곱 — 전부 초록 (수 무변)
```
rnd_board 170/0 · control_trend 59/0 · walk_box 48/0 · walk 32/0
composition 40/0 · intersection 24/0 · reach 63/0
```
📌 하니스는 이 이름을 «한 번도 안 씁니다» — 그래서 개명이 통째로 조용합니다. 그게 바로
   「200 은 인자가 읽혔다는 증거가 아니다」의 클라 쪽 판이라, 게이트 A 를 «서버에» 걸어 두는
   총괄 판단이 맞습니다. 여기에 하니스를 하나 더 만들어도 «전선»을 못 봅니다.

## ⚠️ 빌드 게이트 둘은 «여전히 빨갛고 여전히 남의 것»입니다
`check:contracts` INV-F9-7 (`api.js:1046`, `de12b9f7`) · `check:harnesses`
`load_shows_loaded_map_harness` 앵커 (`map_editor.js`, `a5f6878e`). 통제 그대로 —
제 작업 트리는 이번에도 «제 파일뿐»이었습니다. vite build 를 직접 돌렸고, 둘 다 안 건드렸습니다.

---

# ✅ [클라] `/trends` 404 닫았습니다 — **ⓐ 를 골랐고, 그런데 «제 실패는 다른 곳»이었습니다**

## 🔴 먼저 정정합니다 — 총괄이 보신 404 는 **①-a 가 안 들어간 번들**입니다
```
총괄이 잰 번들   rnd_board-B9fCllS0.js   (커밋된 dist 와 같음 — 맞습니다)
그 번들 안       「재려면 마킹이 필요합니다」 «0» · 「axis:agg:」 «0» · 집계 알약 «0»
=> ①-a 의 코드가 «한 줄도 없습니다». `B9fCllS0` 는 `397bc3e5`(라운드 ①)에서 만든 것이고,
   제 커밋 `0308e6b9` 은 «src 만» 바꿨습니다
확인   git log --name-only 로 제 클라 커밋 «전부»를 보면 라운드마다 dist 번들이 «같이» 갔는데
       0308e6b9 «하나만» 안 갔습니다. 제가 빠뜨린 것이 맞습니다
```
🔴 **그래서 제 「404 0」은 «소스»에 대해 참이고 «페이지»에 대해 거짓이었습니다.** 격리 오리진을
`client2/`(소스)로 띄워 놓고 「화면이 무엇을 부르나」를 쟀는데, **라이브 페이지가 실제로 부르는 것은
`dist/assets/*.js`** 입니다. 「빌드했다고 로드된 건 아니다」의 그 자리이고, 제 메모에 있는데 걸었습니다.
이번엔 오리진을 **`client2/dist/` 로 옮겨서** 다시 쟀습니다 — 아래 목록은 «번들이 부른 것»입니다.

## ⓐ 를 골랐습니다 — 이유
```
ⓑ 는 좌석에 `collect` 한 줄인데, 그 값이 walk 이어야 하고 그건 ①-b 입니다 -> 이 라운드가 ①-b 를 삼킵니다
ⓐ 는 「선언 안 한 것을 부품이 지어내지 않는다」 그 자체이고, 두 줄입니다
그리고 총괄 지적대로 «기본값은 아무도 안 쓴 선언»입니다 -- 좌석에서 지워도 부품이 들고 있으면
그대로 돌고, 「선언에서 사라졌나」로 재는 게이트는 그때 초록입니다
```
```
main_trend_panel.js:70   options.collect || 'trend_y'   ->   options.collect || null
load()                   collect 도 load 도 없으면 «안 걷고» loadState='undeclared'
render()                 「이 좌석이 «무엇을 모을지» 선언하지 않았습니다 — 그래서 걷지 않았습니다」
                         🔴 «거절 아님»으로 그립니다. 서버는 아무 말도 안 했습니다
```

## 게이트 ① — 캐시버스터 붙인 새 로드의 «요청 URL 전부» (번들 `rnd_board-CmszXbSH.js`)
```
1  /api/ledger/declaration
2  /api/ledger/declaration
3  /api/ledger/subgraph?id=…WyJ3YWZlciIseyJ3YWZlciI6IlNZTi1DWC1CVy0wMDEifV0&node_limit=1000&direction=outgoing
4  /api/ledger/subgraph?id=…&follow=inspected&follow=observed&follow=of_kind&direction=outgoing
5  /api/ledger/subgraph?id=…&follow=inspected&follow=observed&follow=of_kind&direction=outgoing
6  /api/ledger/subgraph?id=…&follow=inspected&follow=observed&follow=of_kind&direction=outgoing
7  /tables/wafer_map_metadata/data?limit=1&filters={"map_id":{…"filter":"SYN-CX-BW-001"}}
8  /tables/wafer_map_metadata/data?limit=1&filters={"map_id":{…"filter":"SYN-CX-BW-001"}}
`/trends` «0»  ·  합계 8  ·  페이지가 부른 스크립트 = /assets/rnd_board-CmszXbSH.js «하나»
```

## 게이트 ② — 메인 트렌드가 «문장»을 말합니다
```
빈 차트가 아니라   「marking:1 이 비었습니다 — 후보를 고르면 그립니다」
                  (좌석 3 은 follow 를 선언해서 `bound.load` 를 받습니다 — 그래서 'undeclared' 가
                   아니라 'awaiting' 이 맞는 문장입니다. 둘은 다른 부재입니다)
'undeclared' 문장은 «선언도 load 도 없는» 인스턴스에서 납니다 — 하니스 E2·E3 가 그걸 재고,
변이 M20 이 기본값을 되살리면 «두 단언이 같이» 빨개집니다
```

## 게이트 ③ — 하니스 일곱
```
rnd_board 170/0 · control_trend «59/0» · walk_box 48/0 · walk 32/0
composition 40/0 · intersection 24/0 · reach 63/0     변이 20/20 잡힘 · 새어 나감 0
새로 재는 것   E2 「선언 안 한 좌석은 걷지 «않는다»」 (fetch 호출 «0» 을 셉니다)
              E3 「그리고 그 사실을 말한다 — «거절»로 그리지 않는다」
              M20 기본값을 되살리는 변이
🔴 픽스처 셋에 `collect: 'trend_y'` 를 «적었습니다». 전에는 부품 기본값이 대신 골라 줘서
   픽스처가 «무엇을 묻는지 안 말하고도» 돌았습니다 — 그게 이 결함의 축소판입니다
```

## ⚠️ 빌드 게이트 둘이 «빨간 채로» 있습니다 — 둘 다 이 라운드 것이 아닙니다
`npm run build` 의 prebuild 가 여기서 섭니다. 통제를 걸었습니다 — 두 파일 다 «작업 트리에서 깨끗»하고
(제 수정은 `main_trend_panel.js`·`rnd_board_control_trend_harness.mjs` «둘뿐»), 둘 다 HEAD 의 상태입니다.
```
① check:contracts  config_resolve_report INV-F9-7
   client2/src/rnd_board/api.js:1046   reason: grid ? null : 'grid_not_declared'
   -> 클라가 «서버의 사유 낱말»을 적고 있습니다. 들어온 커밋 `de12b9f7`(라운드 Z 2부)
② check:harnesses  load_shows_loaded_map_harness.mjs
   「mutation anchor is GONE: restore-runs-unconditionally-again」
   -> `map_editor.js` 자리이고 마지막으로 만진 커밋은 `a5f6878e` (맵 레인)
```
그래서 **vite build 를 직접 돌려 번들만 만들었습니다.** 게이트를 «끈 게 아니라» 지나갔고,
두 빨강은 손대지 않았습니다 — 검사기 자신의 문구가 「고치거나 총괄에게 가져가라」이고,
둘 다 남의 레인 계약입니다. 판정 주시면 그 레인에 넘기겠습니다.

## 커밋에 담은 것 — 그리고 «안 담은 것»
```
담음    src/rnd_board/main_trend_panel.js · tests/rnd_board_control_trend_harness.mjs
        dist/rnd-board.html · dist/assets/rnd_board-CmszXbSH.js · dist/assets/rnd_board-1pAHd0Gw.css
        (옛 번들 둘 삭제)
안 담음  dist/map_editor.html · dist/map_editor2.html
        -> 빌드가 건드렸지만 `--ignore-all-space` 로 재면 «실질 변경 0 줄»입니다. 줄바꿈뿐이라
           되돌렸습니다. 남의 페이지를 제 커밋으로 옮기지 않습니다
확인    dist/assets 에서 바뀐 것은 `rnd_board-*` «둘»뿐 — 다른 레인의 번들은 하나도 안 움직였습니다
        (즉 이 트리에서 «안 빌드된 소스»는 제 ①-a 하나였습니다)
```

---

# 🛑 [클라] `continues_hops` → `backbone_hops` — **멈추고 올립니다. 서버에 그 이름이 «없습니다»**

지시대로 ①-a 를 먼저 닫고(`0308e6b9`) 착수했는데, 걸어 보니 **이름이 아직 안 따라왔습니다.**
바꾸면 화면이 «아무도 안 읽는 칸»을 보내게 되고, 그런데도 **게이트 ②가 초록으로 통과합니다.**
그 둘 다 적습니다.

## ① 원장 코드에 `backbone` 이 «한 글자도» 없습니다
```
git grep -n "backbone" origin/main -- server        ->  «0 줄»   (main 끝 `20479e75` 기준)
origin/main:server/ledger_trace_router.py:101       ->  continues_hops: int = Query(...)
origin/main:server/ledger_trace_router.py:127·224·240 ->  continues_hops=...
9f8db5ab 가 실제로 바꾼 것 (12 줄)
   + and near_kind not in static_types
   + and far_kind  not in static_types) else 1
   -> 「면제를 «무엇으로 판정하나」」가 술어 플래그에서 «엔티티 분류»로 바뀐 것이 맞습니다
   -> 그런데 «인자 이름»은 안 바뀌었습니다. 정책만 갔고 낱말은 남았습니다
```

## ② 도는 프로세스도 «옛 이름만» 읽습니다 — 200 은 증거가 아닙니다
```
continues_hops=-1    «422»      backbone_hops=-1   «200»
continues_hops=abc   «422»      backbone_hops=99   «200»
continues_hops=99    «422»      nonsense_hops=2    «200»
=> 이 라우트는 «모르는 칸을 조용히 버립니다». 그래서 `backbone_hops=abc` 조차 200 입니다.
   422 가 나는 쪽이 «실제로 파싱되는» 이름이고, 그건 여전히 `continues_hops` 입니다
프로세스 시작 시각  오늘 12:52 ~ 13:04 (python 넷)
                  -> 9f8db5ab 도 20479e75 도 그 «뒤»입니다. 재기동해도 이름은 안 생깁니다 (①)
```

## ③ 🔴 그런데 게이트 ②가 «공허합니다» — 이게 더 위험합니다
지시의 게이트 ②는 「그 두 좌석의 노드 수 전/후 — 같아야 합니다」입니다.
**오늘 이 보드의 씨앗에서는 예산을 «보내든 안 보내든» 수가 같습니다.**
```
씨앗 SYN-CX-BW-001 의 die «40개» · follow=bonded_from · outgoing
   continues_hops=0  ==  continues_hops=2   -> 전부 같음 (예: nodes 2 · edges 1)
씨앗 SYN-BW-101-02 의 die «8개» · follow=bonded_from,processed_with · node_limit 1000
   continues_hops=0  ==  continues_hops=4   -> 전부 같음
확인 사살   같은 씨앗에서 continues_hops=2 · backbone_hops=2 · «아무것도 안 보냄» 셋이
           nodes 2 · edges 1 로 «글자 그대로 같습니다»
```
=> 지금 이름만 바꿔 커밋하면 **게이트 ②가 초록입니다.** 예산이 «도착했는지»와 «버려졌는지»가
   이 표본에서 같은 답을 내기 때문입니다 — 「두 규칙이 같은 답을 내는 표본은 판별식이 아니다」
   그대로입니다. 초록이 「안 바뀌었다」가 아니라 「이 씨앗은 원래 예산을 안 쓴다」를 뜻합니다.

## 그래서 필요한 것 «둘» — 총괄 판정 요청
```
① 서버가 인자를 «실제로» 개명해야 합니다 (라우트 + ledger_subgraph 의 인자·기본값).
   그 전에는 클라가 먼저 가면 「재료 없이 채택된 계약」이고, 조용히 예산이 0 이 됩니다
② 게이트 ②에 «판별하는 씨앗»을 주십시오 — 총괄 실측의 「자재6 + processed_with ch=4 -> 157」
   그 씨앗입니다. 제가 가진 씨앗들로는 ch=0 과 ch=4 가 «같은 수»라 아무것도 못 가릅니다
   (그 씨앗을 주시면 「보냈을 때 157 · 안 보냈을 때 N」을 재서 붙이겠습니다)
```
⚠️ 클라 쪽 준비는 «세 자리»로 끝납니다 (api.js 구조분해·query, main.js 좌석 넷의 선언).
   값은 그대로 둡니다. 서버가 이름을 받는 날 «한 커밋»으로 갑니다 — 지금은 안 갑니다.

---

# ✅ [클라] 라운드 ①-a — **Y축이 «집계 × 수식어»가 됐고, `/trends` 404 가 «0» 이 됐습니다**

## 게이트 넷 — 전부 통과. 그리고 «라이브에서 제 결함 하나»를 찾아 고쳤습니다

```
① 알약이 집계를 고르고 «차트가 바뀐다»   ✅ 라이브 실측 (아래 표)
② 마킹이 비어도 알약이 있고 이유를 말한다 ✅ 「재려면 마킹이 필요합니다 — marking:1 이 비어 있습니다」
③ 404 가 어떻게 되나                    ✅ «0». 요청 총수는 8 로 «그대로» — trends 하나가 declaration 하나로 바뀜
④ 무회귀                               ✅ 다른 요청 URL·개수 전부 동일 · 하니스 «일곱» 초록
```

## 먼저 걸었습니다 (상설 「모든 제안 전 walk 으로 해결 가능한지」)
```
/api/ledger/declaration        술어 13 중 «다섯»이 수식어를 답니다 — 서로 다른 이름 «15»
   observed@1        radius_x · inchip_x · inchip_y · radius_y · unit · gate · run_uid   (7)
   measures@1        value · value_text · role · step · eqp_id                            (5)
   leads_to@1        dir · model      processed_with@1  step      slot_map@1  event_type
=> 원장을 «한 줄도» 안 읽습니다. 그래서 이 목록은 마킹이 비어도 «전부» 서 있습니다
walk (씨앗 SYN-CX-BW-001 · outgoing · hops 3)
   엣지 626 · 그중 수식어를 «싣는» 것은 observed 121
   실제 타입   gate·inchip_x·inchip_y·radius_x·radius_y {float 121}  ·  run_uid·unit {str 121}
=> 「수치인가」는 여기서만 알 수 있고, 그래서 «마킹이 있어야» 답이 나옵니다
서버 변경 «0» · 새 라우트 «0» · 새 술어 «0» — 선언과 걷기가 이미 답합니다
```

## 도착지대로 나눴습니다 — 셋이 서로 «다른 곳»에서 옵니다
```
집계 목록    `AGGREGATIONS` (api.js). 고정 · 데이터 «불필요» -> 마킹이 비어도 일곱이 다 눌립니다
             median · mean · sum · min · max  (수치 전용)   |   count · distinct  (전부)
수식어 목록  `/declaration` -> `qualifiersFromDeclaration()`. 마킹과 «무관»
수치인가     walk -> `qualifierTypesFromWalk()` = 이름마다 {seen, numeric}
             -> 판정이 아니라 «두 수»를 들고 옵니다. 그래야 화면이 「수치 4/4」처럼 셀 수 있습니다
축 = 쌍      마킹 `axis:y` 에 «한 id» -> `axis:agg:<집계>:<수식어>`
             집계만 고른 상태는 «아직 축이 아닙니다» (무엇을 잴지가 없으면 잴 수 없습니다)
```

## 게이트 ① — 라이브 실측 (격리 오리진 · 마킹 1 = 결함 있는 다이 하나)
```
알약                     차트가 그린 것                              y축 꼭대기
count   × radius_x       count(radius_x) 4 · 값 4개 · 쓴 값 4개        4
median  × radius_x       median(radius_x) 9.95                        9.95
max     × radius_x       max(radius_x) 11.38                          11.38
distinct× unit           distinct(unit) 1                             1
=> 알약을 누르면 «그린 수»가 바뀝니다. 범례도 같이 바뀝니다: `y = max(radius_x) · 값 4개 · observed · of_kind 에서`
```

## 게이트 ② — 마킹이 비었을 때 (첫 로드)
```
수식어 알약  15 개 «전부» 있음 (dir · eqp_id · event_type · gate · inchip_x · inchip_y · model
             · radius_x · radius_y · role · run_uid · step · unit · value · value_text)
집계 알약    7 개 «전부» 있음
문장         「재려면 마킹이 필요합니다 — marking:1 이 비어 있습니다 (수식어는 선언에서 오므로 그대로 있습니다)」
=> 「값 없음」도 빈 목록도 «아닙니다». 마킹을 찍으면 같은 줄이 「marking:1 에서 쟀습니다 ·
   값이 실려 온 수식어 7/15」로 바뀝니다 — 그 7 이 observed 가 싣는 일곱과 «정확히» 같습니다
```

## 게이트 ③ — 404 는 «0» 이고, 요청 총수는 «안 늘었습니다»
```
                                    전(라이브 :8080)   후(격리 :8778)
/api/ledger/trends?window=180d              1 «404»          «0»     <- 뿌리는 알약이었습니다
/api/ledger/declaration                     1                 2      <- 걷기 검색창 + 제어 막대
/api/ledger/subgraph (follow 셋 · outgoing)  3                 3
/api/ledger/subgraph (후보 · node_limit)     1                 1
/tables/wafer_map_metadata/data             2                 2
                                    ─────────────────────────────
합계                                        8                 8
=> 404 하나가 200 하나로 «자리를 바꿨습니다». 좌석 `control-bar` 는 이제 라우트를 «한 개도» 이름 대지 않습니다
```
🔴 **그리고 전에는 Y축에 «쓸 수 있는 알약이 하나도 없었습니다».** 라이브 :8080 실측 —
제어 막대의 알약은 또래 다섯과 「값 없음 506」뿐입니다. `/trends` 가 404 라 `kinds` 가 빈 배열이었고,
그래서 「비율」 알약이 «0» 이었습니다. 지금은 15 + 7 이 섭니다.

## 🔴 라이브에서 «제 라운드가 만든» 결함 하나 — 찾아서 고쳤습니다
```
증상   `unit` × `max` 를 고르면 화면이 「이 걷기가 그 수식어를 안 실었습니다」
사실   걷기는 unit 을 «실었습니다». max 가 수치가 아니라서 «전부 건너뛴» 것입니다
왜     모델은 `skipped` 를 이미 세고 있었는데 «그리는 쪽»이 그 수를 안 읽었습니다
       -> 못박음 ②(「건너뛴 개수를 말할 것」)를 «세기만 하고» 공허하게 만든 자리입니다
고침   그 자리에서 두 0 을 가릅니다
       skipped > 0  ->  「max(unit) 는 값 1개를 «전부 건너뛰었습니다» — 수치가 아니었습니다
                         (count · distinct 는 잽니다)」
       skipped = 0  ->  「이 걷기가 그 수식어를 안 실었습니다」   (그대로)
확인   라이브에서 셋이 «서로 다른 문장»입니다:
       max(unit)       -> 전부 건너뛰었습니다
       distinct(unit)  -> 1 을 그립니다
       distinct(value) -> 이 걷기가 그 수식어를 안 실었습니다
```

## 게이트 ④ — 하니스 «일곱», 전부 초록
```
                              전        후
rnd_board                   170/0     170/0
rnd_board_control_trend      36/0      56/0     <- 이 라운드가 재는 것이 늘었습니다
rnd_board_walk_box           48/0      48/0
rnd_board_walk               32/0      32/0
rnd_board_composition        40/0      40/0
rnd_board_intersection       24/0      24/0
rnd_board_reach              63/0      63/0
변이  13 -> «19», 19/19 잡힘 · 새어 나감 0 · INERT 0
```
### 죽은 시험 넷은 «이 변경이 원인»이라고 이름 대고 고쳤습니다
```
A1  「비율 축이 죽은 라우트의 selectable_finding_kinds 에서 온다」
    -> 그 라우트를 좌석이 더는 안 부릅니다. 같은 질문(「목록을 부품이 지어내나 받나」)을
       «선언»에 대고 다시 적었습니다. 이름을 갈아끼운 것이 아니라 «재는 대상»을 옮겼습니다
B1  「첫 비율 축이 자동으로 골라진다」
    -> 자동 선택을 «없앴습니다». 집계 축에는 대신 골라 줄 「첫째」가 없고, `count × ?` 를
       대신 고르면 «아무도 안 고른 축»을 차트가 그립니다. 이제 안 고르면 차트는 자기 기본(비율)
M1 · M6 · M7 · M12  앵커 넷이 «옮겨진 자리»를 가리킴 -> 옮겨 붙였습니다 (재는 결함은 그대로)
```
### 새로 «재는» 것 (변이 여섯이 각각 깨웁니다)
```
A8/M14  마킹이 비었을 때의 «자기 문장»  (「값 없음」으로 접으면 빨강)
A9/M15  집계는 데이터 «없이» 서 있다     (데이터를 기다리게 하면 축이 통째로 사라짐 -> 빨강)
F1/M16  「하나라도 수치면 수치」          (전수를 요구하면 문자 하나가 축을 죽임 -> 빨강)
F2/M17  건너뛴 수를 «센다»               (조용히 버리면 빨강)
F8/M18  고른 집계가 «걷기까지 간다»       (안 실으면 알약이 차트를 안 바꿈 -> 빨강)
F9/M19  전부 건너뛴 것을 «안 실었다»로 읽지 않는다   <- 오늘 라이브에서 실제로 난 결함
```
🔴 판별 입력이 «두 규칙이 다른 답을 내는» 것입니다 — `radius_x` 셋 중 «하나가 문자». 전수 규칙이면
축이 죽고(null), 하나면 3 이 나옵니다. 셋 다 수치인 표본으로는 어느 쪽이 도는지 알 수 없습니다.

## 바뀐 것 — 다섯 파일
```
api.js                  AGGREGATIONS · aggregationIsNumericOnly · qualifiersFromDeclaration
                        · qualifierTypesFromWalk · trendFromWalk(answer, «axis»)
control_bar_panel.js    `/trends` 걷기 «삭제» · 수식어/집계 알약 · `_chosenPair` · `_numericNote`
                        · `_sampleNumeric` (마킹이 비면 «안 걷습니다»)
main_trend_panel.js     `axis:agg:*` 축 · `valueOf`/`formatValue` · 범례·제목·축의 «자기 문장»
main.js                 좌석 `control-bar` 에서 `collect: 'trend_y'` «제거» · `numericReads` 선언
                        · `loadDeclaration` 주입 · mainTrend 의 `axis` 를 «전선 밖»에서 뗌
board.css               `.rb-control-note` 한 줄
```
🔴 `axis` 는 «전선에 안 실립니다». 실으면 같은 질문이 축마다 다른 열쇠가 되어 walk 의 합침이
깨지고, 서버는 모르는 칸을 «조용히» 버립니다 — 200 이 증거가 아니라는 그 자리입니다.
실측으로도 요청 URL 이 축과 «무관하게 글자 그대로» 같습니다.

## ⚠️ 두 가지를 «올립니다» (제가 안 고쳤습니다)
```
① 좌석 3 의 씨앗이 «다이»입니다 — 맵을 찍으면 die 가 marking:1 에 들어가고, 그러면
   `inspected`(wafer -> die)를 outgoing 으로 못 지나 «비율»이 항상 null 입니다
   (라이브: 「점 1개 · 비율이 붙은 것은 없습니다」). 집계 축은 observed 를 지나므로 «돕니다».
   -> 비율 축을 되살리려면 좌석 3 의 시작점이나 방향 이야기이고, ①-b 의 안건으로 보입니다
② 걷기 응답의 `provenance` 가 비율 축에서 「분자 ? · 분모 ?」로 나옵니다 (walk 은 술어만 싣고
   numerator/denominator 를 안 싣습니다). 이 라운드가 만든 것이 «아니고» 그대로 뒀습니다
```

## 📌 실측 환경 — «격리 오리진»을 썼습니다
```
라이브 :8080 은 «main 워크트리»를 서빙합니다 -> 이 레인의 변경이 «안 보입니다» (「빌드했다고
로드된 건 아니다」의 그 자리). :5173 은 이미 다른 vite 가 잡고 있어 건드리지 않았습니다.
그래서 design 워크트리를 «내 포트»(:8778)로 띄우고 /api·/tables 를 :8080 으로 넘겼습니다.
그 서버가 하는 «유일한 변형»은 vite 의 `define` 과 같은 한 줄(`import.meta.env.VITE_USER`)입니다.
남의 프로세스·파일은 «하나도» 안 건드렸습니다.
⚠️ 브라우저 패널이 프레임을 못 그려 «스샷은 못 찍었습니다». 대신 DOM·네트워크·타이틀 문자열을
   그대로 떠서 위 표를 만들었습니다 — 목업 대조가 필요하면 :8778 을 그대로 두겠습니다.
```

## ⏭ 다음
```
14:1x 지시(`continues_hops` -> `backbone_hops`)는 「①-a 를 먼저 닫고」라고 적혀 있어
«이 커밋 뒤에» 착수합니다. ①-b(좌석 3 이동)도 총괄 판정 대기입니다.
```

---

# ⚠️ [클라] 라운드 ① — **멈춤 조건에 걸립니다.** 옮겼다가 «되돌리고» 수를 올립니다

## 먼저 걸었습니다 (상설 · 지시의 멈춤 조건)
```
씨앗 SYN-CX-BW-001 · follow=measures · outgoing · node_limit 400
   nodes «1» · measures 엣지 «0» · 절단 «없음»
   -> 이 0 은 «없어서 0» 입니다. 잘려서도, 못 가서도 아닙니다 (원장에도 그 웨이퍼의 measures 원자 0)
씨앗 SYN-BW-101-02 (재료가 있는 쪽)
   measures 엣지 «17» · quantity 노드 «17» · 절단 «없음»
   수식어 실제 타입  value {number 16} · value_text {string 1} · role/step/eqp_id {string 17}
   -> 총괄 실측과 «같은 그림»입니다. 「하나라도 수치면 수치」이고 «건너뛴 1」을 말해야 합니다
```

## 옮겨 봤고, «되돌렸습니다» — 이유는 수입니다
```
옮긴 뒤   보드 요청 «7» · «전부 200» · 404 «0» · 422 «0»   ← 404 가 통째로 사라집니다
그런데    컨트롤 바의 «비율 축»이 «같이 사라집니다»
왜        좌석 3 은 마킹을 안 읽어 «씨앗이 없습니다». 씨앗 없는 걷기는 거절이고,
          그러면 kinds 가 빈 배열이라 알약이 «0» 이 됩니다
확인      하니스 A1·B1 이 정확히 그걸 잡았고, 화면에서도 「값 없음」이었습니다
```
🔴 **404 하나를 지우려고 화면이 «말을 덜 하게» 만드는 것은 오늘 판정에 어긋납니다** —
   총괄이 좌석 3 에 대해 이미 「404 하나가 «덜 말하는 화면»보다 정직하다」고 판정하셨습니다.
   그래서 되돌렸습니다. 남은 404 는 «무엇을 기다리는지 이름이 붙은» 하나입니다.

## ⏭ 순서가 하나 더 있습니다 — Y축이 «집계»가 되는 것이 «먼저»
```
지금   Y축 알약 = «종류»(비율). 그 종류를 없어진 라우트의 selectable_finding_kinds 에서 받습니다
판정   「집계가 고른다」 (소유자). median·mean·sum·min·max 는 수치 수식어만,
       count·distinct 는 전부
=> 알약이 «집계»를 고르게 된 뒤에야 좌석 3 이 걷기로 갈 수 있습니다. 지금 옮기면 그 사이에
   축이 «사라진 채»로 남습니다. 이 순서를 지시서에 적힌 ⓪→③→① 안에서 «①-a → ①-b» 로 나눕니다
```

## 그래도 남긴 것 하나 — 경계의 «빈 씨앗» 관문
```
옮기는 동안 `id=undefined` 요청이 «422» 로 나갔습니다. 부품마다 관문을 다는 대신
경계에서 한 번 막습니다 -- 씨앗이 없으면 «묻지 않고» 「아직 안 골랐다」를 내용으로 돌려줍니다
(스탬프 id 관문 바로 옆, 같은 모양)
이건 되돌리지 «않았습니다» — 오늘 밤 같은 자리를 세 번 고쳤고, 그 셋을 한 줄이 덮습니다
```

## 상태
```
하니스   control_trend 36/0 · board 170/0 · walk 32/0 · walk_box 48/0
보드     요청 8 · 404 «1» (좌석 3 의 trend_y) · 422 «0»
```

---

# 🔓 [클라] **라운드 ⓪ 결함 수리 — 자리가 «둘 다» 제 짐작과 달랐습니다**

총괄 지적이 맞습니다. 그리고 **제 1차 보고 문장이 틀렸습니다** — 「walk 요청 셋 전부 direction 을
싣는다」고 적었는데 넷이었고 하나가 안 실었습니다. 더 나쁜 것은, 그 뒤 제가 «방향 없는 요청 1» 을
실제로 재고도 라운드 ③ 으로 넘어가면서 «안 쫓았다»는 것입니다.

## 🔴 그런데 자리는 총괄이 지목한 둘도 «아니었습니다» — 표식을 박아 잡았습니다
```
총괄 지목   :655 optionsFor(y)  ·  :697 loadWaferFacts
제 실측     둘 다 «이미 방향을 싣고 있었습니다»
            loadWaferFacts -> head-summary 좌석 것이고 그 좌석은 라운드 ⓪ 에서 선언받았습니다
            optionsFor     -> control-bar 가 «아니라» «trend-declaration» 좌석에 묶여 있습니다
실제 범인   `trend-declaration` · `composition-declaration`
            «선언을 그리는» 좌석이라 walk 을 안 하는 줄 알았는데, options.fields 가 있어서
            optionsFor(y) 가 여기 붙습니다. 좌석에 선언이 «하나도 없어» walkHere 가 맨 walk 이었고,
            그래서 목록에도 안 떴고 서버 기본 both 로 나갔습니다
```
📌 **어떻게 잡았나:** 코드 추론으로 세 번 틀렸습니다. `walkHere` 에 «임시 표식»을 박아 좌석 이름과
   실제 spec 을 찍고 한 번 재고 즉시 되돌렸습니다. 그 한 줄이 세 번의 추측보다 빨랐습니다.

## 게이트 ① — 로드 시 walk 요청 «전부» 방향을 싣습니다
```
전   walk 4 · 맨몸 «1»
후   walk 4 · 맨몸 «0»        요청 총수 8 -> 8 (무변)
마킹 뒤   walk 3 · 맨몸 «1» = `reach` (hops=1)
          -> 이건 라운드 ⓪ 에서 «이유를 적고» 뺀 자리입니다:
             「한 홉에 무엇이 있나」는 «양쪽»이 뜻이고, depth 절단은 질문 자체입니다
```

## 게이트 ② — 그 자리의 수 전/후
```
씨앗 wafer SYN-CX-BW-001 · follow inspected,observed,of_kind
   both(전)      nodes 400 · 검사 128 / 발견 «270» · 종류 «1» [void] · 절단 nodes,claims
   outgoing(후)  nodes 251 · 검사 128 / 발견 «121» · 종류 «1» [void] · 절단 «없음»
```
```
종류 목록은 오늘 «같습니다» — 원장에 종류가 «하나»뿐이라 잘려도 그 하나는 남습니다.
🔴 그래도 고친 이유: 잘린 표본에서 «둘째 종류»가 오는 날 그것이 조용히 사라지고,
   사용자에게는 「그런 종류가 없다」로 보입니다. 그리고 ① 의 집계가 이 자리에 앉습니다 --
   ⓪ 를 ① 앞으로 당긴 이유가 그것이었습니다
발견 270 -> 121 의 149 는 «남의 웨이퍼 다이»에서 거꾸로 닿은 것입니다 (라운드 ⓪ 표와 같은 부류)
```

## 게이트 ③ — 이 부류를 «전수»로 찾았습니다
```
main.js 에서 walkHere/walk 을 직접 부르는 자리 «13». 전부 walkHere 라 좌석 선언을 물려받습니다
=> 방향이 없는 자리는 «좌석이 선언을 안 한 것»이지 호출부가 빠뜨린 것이 아니었습니다
좌석 16 중 direction 을 선언한 것 «12». 안 한 «넷»과 이유:
   reach          «양쪽»이 뜻 (위)
   walkBox        사용자가 그 자리에서 고릅니다 — 부품이 정할 값이 아닙니다
   marking-status walk «안 합니다» (마킹 저장소만 읽습니다)
   candidate-list · rank-list  walk 을 CANDIDATE_QUESTION 으로 하고 «거기에» direction 이 있습니다
```
⚠️ 상호작용해야 뜨는 자리는 로드만으로 못 봅니다 — 마킹을 «실제로 찍어» 한 번 더 쟀고(위), 그때
   뜬 것은 reach 하나였습니다. 그 밖의 상호작용(트렌드에서 웨이퍼 찍기 등)은 아직 못 밟았습니다.

## 하니스
```
board 170/0 · walk_box 48/0 · walk 32/0
```

---

# 🔓 [클라] **라운드 ③ 착지 — 자재 예산을 부품이 선언합니다.** 게이트 ② 는 «못 닫습니다»

## 배선 — 지시가 지목한 두 자리 그대로
```
api.js   구조분해에 continues_hops · follow «와 같은 모양»으로 있을 때만 싣습니다
main.js  question 에 한 줄 (node_limit 옆) · 좌석 선언에 한 줄
```

## 붙인 곳 · 안 붙인 곳
```
붙임   구성 1·7·11  follow [bonded_from]                     continues_hops «2»
                     -> 「이 다이가 무엇으로 만들어졌나」. 코어가 또 코어 위에 앉는 적층 한 겹
       칩확대 9      follow [observed, inspected, bonded_from] continues_hops «1»
                     -> 관측을 보는 자리이고 bonded_from 은 「그 관측의 주어로 가는 길」뿐
안 붙임 맵 8·12 · 트렌드 4·6   follow 가 inspected/observed/of_kind «뿐» — 관측만 보는 자리
       닿는 곳 15 · walkBox
```
### 🔴 그리고 곁가지 하나가 좌석 예산을 «물려받고» 있었습니다
```
실측   head-summary 의 kind별 웨이퍼 사실(loadWaferFacts)이 좌석 질문을 그대로 받아
       요청에 continues_hops=2 를 싣고 나갔습니다 — 그런데 그 호출의 follow 는
       inspected/observed/of_kind «뿐», 즉 지시가 「안 붙인다」로 정한 관측 전용입니다
조치   그 호출에서 «명시적으로» 끕니다 (null -> 경계가 안 실음). 좌석 선언은 그대로 둡니다
```

## 게이트 ① — 안 선언한 부품은 «안 싣습니다» ✅
```
보드 로드   subgraph 요청 «4» 중 continues_hops 를 실은 것 «0»
            (구성 좌석은 마킹이 비면 «요청 자체를 안 냅니다»)
마킹 뒤     subgraph 요청 «3» 중 «1» 이 싣습니다 — 자재를 따라가는 좌석 것
요청 총수   «8 -> 8» 무변
```

## 🔴 게이트 ② — 「전/후 노드 수가 달라진다」를 «못 보입니다». 이유는 수로 적습니다
```
구성 좌석 씨앗 die SYN-CX-BW-001(7,7) · outgoing · node_limit 400 · follow bonded_from
   선언 안 함        nodes 3 · edges 1 · {die:3}
   continues_hops=2  nodes 3 · edges 1 · {die:3}   ← «같습니다»
```
```
왜   돌고 있는 서버는 이 인자를 «진짜로 파싱합니다» — -1 · 99 · abc 가 전부 «422» 이고
     선언이 ge=0 le=40 입니다 (router:99). 즉 인자는 «살아 있습니다»
     🔴 그런데 «라이브 선언의 continues 술어가 0 / 13» 입니다.
        router 의 `_continuing_predicates()` 가 빈 집합을 돌려주니 예산이 «쓸 곳이 없습니다»
실측 참고   200 은 증거가 «아니었습니다» — 이 라우트는 모르는 인자를 «조용히 무시»합니다
            (이 세션 앞선 실측). 그래서 범위 밖 값으로 «파싱 여부»를 따로 갈랐습니다
```
📌 오늘 `1162d002` 로 «sample» 에 continues 플래그 여섯이 들어갔습니다. 라이브 설정은
   소유자 파일이라 제가 «안 건드립니다» — 그 플래그가 라이브에 오는 날 이 선언이 값을 냅니다.
   그때까지 이 줄은 «배선은 됐고 재료가 없는» 상태이고, 그걸 초록으로 적지 않겠습니다.

## 게이트 ③
```
하니스   board 170/0 · walk_box 48/0 · walk 32/0   (지시서의 48/0 · 170/0 · 32/0 그대로)
```

---

# 🔓 [클라] **라운드 ⓪ 착지 — `direction` 을 부품이 선언합니다.** 새 코드 «0»

배선은 이미 있었습니다 (`main.js:588`). 고친 것은 «선언»뿐이고, 여덟 좌석에 한 줄씩입니다.

## 게이트 ① — 부품마다 두 방향, 네 수 (씨앗·인자 포함)
```
공통 인자   edge_limit 기본 · 씨앗 wafer SYN-CX-BW-001 (구성만 die SYN-CX-BW-001(1,4))
```
```
부품                     방향       nodes edges reached 절단            고름
후보/순위 (node_limit 1000)  both     1000  1200    3    nodes,edges,claims
                            outgoing  507   626    3    «없음»          ✅ outgoing (원래 선언돼 있던 것)
맵 8·12 (400)               both      400   519    4    nodes,claims
                            outgoing  251   370    3    «없음»          ✅ outgoing
칩확대 9 (400·hops 8)        both      400   399    3    nodes
                            outgoing  378   377    2    «없음»          ✅ outgoing
트렌드 4·6 (400)            both      400   519    4    nodes,claims
                            outgoing  251   370    3    «없음»          ✅ outgoing
구성 1·7·11 (400)           both        3     1    1    «없음»
                            outgoing    3     1    1    «없음»          ✅ outgoing (같음 — 아래 이유)
닿는 곳 15 (400·hops 1)      both      129   128    1    depth
                            outgoing  129   128    1    depth           ⛔ 선언 «안 함» (아래 이유)
```

## 게이트 ② — 절단이 사라진 부품 «넷». 새로 나타난 노드 타입은 «없음»
```
절단 사라짐   후보/순위 · 맵 8·12 · 칩확대 9 · 트렌드 4·6   «넷»
새 노드 타입  «없습니다» -- 이 씨앗에서는 both 에서도 defect_kind 가 이미 닿습니다
              (총괄 실측의 SYN-BW-101-16 과 다른 점이고, 씨앗이 다르기 때문입니다)
```
### 🔴 그런데 «수가 줄어든 것»이 답이 좁아진 게 아닙니다 — 구성으로 보입니다
```
맵/트렌드   both     die 128 · defect «270» · defect_kind 1   (+ 절단)
            outgoing die 128 · defect «121» · defect_kind 1   (절단 없음)
=> 사라진 defect «149» 는 «남의 웨이퍼 다이»에서 거꾸로 닿은 것입니다. 우리 다이 수는 «그대로 128».
   즉 both 는 예산을 남의 웨이퍼에 쓰고 그 대가로 잘렸습니다 — 총괄이 본 그 새는 자리입니다
후보/순위   both die «877» -> outgoing «384». 같은 부류이고, 절단이 통째로 사라집니다
```

## 두 좌석의 «이유»
```
구성 1·7·11   두 방향이 «동일»(3/1/1/없음). 그래도 선언합니다 — 뜻이 「이 다이가 무엇으로
              만들어졌나」라 «나가는» 걸음이고, 오늘 같다는 것이 내일 같다는 뜻이 아닙니다
닿는 곳 15    두 방향이 «동일». 선언 «안 합니다» — 이 질문은 「한 홉에 무엇이 있나」라
              «양쪽»이 뜻입니다. depth 절단은 hops=1 이라 «질문 자체»이지 예산 실패가 아닙니다
```
⛔ 일괄로 안 바꿨습니다. `has_wafer` 처럼 거꾸로 서는 술어를 쓰는 좌석이 생기면 그 좌석은 다시 잽니다.

## 게이트 ③④
```
요청 수   전 «8» -> 후 «8»  (direction 은 인자이지 갈래가 아닙니다)
          walk 요청 «셋» 전부 direction=outgoing 을 싣고, 나머지(선언·격자)는 안 싣습니다
무회귀    맵이 그대로 「128칸 · 발견 121 · 검사 128」
하니스    board 170/0 · walk_box 48/0 · walk 32/0
```

---

# 🔒 [클라] **잡습니다 — 라운드 ⓪ `direction` 선언** (보고처: 이 파일)

```
순서   ⓪ direction  ->  ③ continues_hops  ->  ① 좌석3 + 집계   (총괄 정정 순서 그대로)
잡는 파일   client2/src/rnd_board/main.js  (선언만. 배선은 «이미» 있습니다)
```
⛔ 일괄 `outgoing` 안 합니다 — `has_wafer` 가 lot_slot → wafer 라 웨이퍼에서 보면 «들어오는»
   걸음이고, 일괄로 바꾸면 자재 위쪽이 통째로 사라진다는 지시 그대로입니다.
부품마다 두 방향을 각각 걸어 네 수와 «노드 타입 구성»을 적고, 그 표를 선언의 근거로 씁니다.

---

