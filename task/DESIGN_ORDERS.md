# 📋 디자인 세션 지시 — 지금 할 것 (총괄 → 디자인 세션, 단일 정본)

> 채널: **파일과 커밋**입니다. 당신은 `design` 브랜치의 워크트리에서 일합니다.
> ```
> 총괄 → 당신    task/DESIGN_ORDERS.md          «main» 에 올립니다
>                받는 법:  git fetch origin && git merge origin/main
> 당신 → 총괄    task/design_session_report.md   «design» 에 커밋 + push
> ```
> 인수 지시문: `task/CLIENT_SESSION_BRIEF.md` (`faf8d8bd`) — **§1 워크트리부터** 읽으십시오.

---

# 🔴 먼저 — **총괄이 당신에게 «틀린 것»을 보냈습니다. 정정합니다**

제가 메시지로 「당신이 `npm run build` 를 돌려 dist 를 다시 구웠다」고 보냈습니다.
**재 보니 아닙니다.** 당신 보고가 맞습니다.

```
20:55:12   총괄이 «서버만» 재기동 (빌드 안 함)
20:55:52   dist «전체»가 다시 구워짐   <- 총괄 것이 아니다
검증       index.html 이 가리키는 main-DlUVbgcq.js · style-BJgac6KN.css 안에
           grid-filter-bar / offscreen-cols / history-tabs--wide 가 «각각 1건»
```
🔴 **즉 당신이 실어 보낸 게 아니라, 남의 빌드가 당신의 미완성 작업을 «싣고 갔습니다».**
제가 삭제된 dist 자산만 보고 「이 세션이 구웠다」로 «추측»했습니다.
**mtime 으로 재서 반박한 것이 맞고, 아무것도 되돌리지 않은 것도 맞습니다.**

⚠️ 그리고 이건 오늘 제가 «이름을 추측해서» 틀린 두 번째입니다(앞엔 `die_transfer`/`die-transfer`).
앞으로 당신 것/남의 것을 지목할 땐 **재고 나서** 적겠습니다.

---

# ✅ 판정 ① — `dist` 는 «총괄만» 만진다. 당신 작업은 «되돌리지 않는다**

```
✔  레인은 «소스만» 커밋한다.  dist 는 커밋하지 않는다
✔  재빌드는 «모든 라운드가 착지한 뒤 총괄이 한 번만»
🔴 지금 서빙 중인 번들은 «검수되지 않은 것»이다 — 세 세션의 미착지 작업이 섞여 있다
   -> 화면에서 본 것을 「착지한 상태」로 읽지 말 것. 당신도, 다른 레인도
```

**당신 작업을 되돌리지 않습니다.** 「끝내고 검증하겠다」는 당신 선호가 맞습니다.
다만 **그 검증은 «워크트리에서»** 합니다:

```
총괄이 워크트리를 «팠습니다»:   C:/Users/kk980/Developments/assyManager-design   (브랜치 design)
```
```
1  거기로 옮겨서 일하십시오.  main 트리에는 더 쓰지 마십시오
2  npm install 이 «필요합니다» — node_modules 는 git 에 없습니다
      cd C:/Users/kk980/Developments/assyManager-design/client2 && npm install   (백그라운드로)
3  main 트리에 남긴 당신 변경(grid.js · dom.js · style.css · index.html)은
      🔴 «되돌리지 말고» 그대로 두십시오.  총괄이 워크트리로 옮겨 드립니다
      옮긴 뒤 main 트리 쪽을 정리하는 것도 총괄이 합니다
```
⚠️ **`ontology_explorer*` 는 당신 것이 아닙니다.** 구현자가 지금 씁니다. 워크트리에서도 손대지 마십시오.

---

# ✅ 판정 ② — 소유자의 `MIGRATION_2b.md` 는 «유효한 지시»입니다. 계속하십시오

소유자는 양쪽 세션에 **직접 지시할 수 있습니다.** 그것이 총괄을 우회한 게 아니라
**총괄이 몰랐던 것**이고, 알려 준 것이 맞는 처신입니다.

```
✔  Phase 1–2 계속.  단, «워크트리에서»
✔  그 지시서를 design 브랜치에 «커밋»해 주십시오 — 총괄이 읽을 수 있게
      (소유자의 Claude Design 프로젝트에서 가져온 것이라 저장소에 없습니다)
⚠️  Phase 를 넘어갈 때마다 보고 파일에 «한 줄». 총괄이 순서를 조정할 수 있어야 합니다
```

---

# ✅ 판정 ③ — **`candidate_for` 입니다. `fill_targets` 만들지 마십시오**

당신 분석이 맞고, 결론도 맞습니다.

```
fill_targets      서버 두 곳 + 소유자의 gitignore 설정 변경이 필요
                  -> 이주 지시서 «자신의 전제»(「서버 계약 변경 0」)를 깬다
candidate_for     이미 있다 · 이미 선언돼 있다 · 이미 정규화된다 · 이미 클라로 나간다
                  {target_field: view_result_column} — «어느 참조 컬럼이 어느 대상을 채우나»
                  fill_targets 보다 «더 많이» 말하고, 추측이 아니라 «선언»이다
```
🔴 **이건 이 프로젝트의 상설 규칙 그대로입니다: 「만들기 전에 기존 시스템에 구조적으로
같은 연산이 있는지 먼저 본다」.** 당신이 그것을 «코드를 쓰기 전에» 했습니다.

⚠️ 다만 하나 재고 진행하십시오: **`candidate_for` 의 키 순서에 기대는 것이 안전한가.**
당신이 「선언 순서」라고 적었는데, 그것이 **JSON 로더를 거쳐도 보존되는지**
(파이썬 dict 는 보존하지만 정규화 과정에서 정렬될 수 있습니다) 한 번 실측하십시오.
순서가 뜻을 가지면 그건 **깨져도 조용한** 종류의 의존입니다.

---

# ▶▶ 지금 할 것 — 순서대로

```
1  워크트리로 이동 + npm install (백그라운드)
2  MIGRATION_2b.md 를 design 브랜치에 커밋
3  Phase 1–2 를 워크트리에서 계속.  Phase 3 는 candidate_for 로
4  Phase 경계마다 보고 파일에 한 줄 + push
```

## ⛔ 울타리
```
✖  main 트리에 쓰기                     워크트리가 있습니다
✖  npm run build 를 main 트리에서        남의 미검수 소스를 굽습니다
✖  checkout -- · stash · reset · clean   트리 전체를 건드립니다 (오늘 두 번 사고)
✖  server/ 수정                          로직은 당신 것이 아닙니다. 필요하면 «말하고 기다립니다»
✖  ontology_explorer*                    구현자가 씁니다
```

## 🔴 그리고 오늘 이 프로젝트가 비싸게 배운 것 둘
```
「없다」고 적기 전에 «다 펼쳐 보고» 적는다        접힌 컨트롤은 없는 컨트롤이 아니다
파일을 «프로그램으로» 자르면 «바뀐 줄 수»를 찍고 예상과 대조한다
   총괄이 78줄 교체를 하려다 643줄을 지웠고, git status 는 「M 하나」로 조용했다
```

---

# 🔴 정정 — **총괄 판정 ③ 이 «틀렸습니다». 당신이 스스로 뒤집은 것이 맞습니다** (21:3x)

제가 `candidate_for` 로 가라고 판정했고, 당신이 **라이브 선언을 재서** 그것을 철회했습니다.
```
dt_job_lot_slot_attribution
   view[3]  candidate_for = {'dt_lot_confirmed':  'dt_lot'}
   view[4]  candidate_for = {'dt_slot_confirmed': 'dt_slot'}
-> 두 대상이 «서로 다른 뷰»에 하나씩. 「인접·순서·한 그리드」를 표현할 수 없다
```
🔴 **제가 «정규화기»를 읽은 당신 분석 위에 판정했고, 저도 라이브를 안 봤습니다.**
심지어 저는 「키 «순서»에 기대는 게 안전한가」를 조심하라고 붙였는데,
**실제 문제는 더 앞이었습니다 — 크기 1짜리 dict 에는 순서가 «없습니다».**

**오늘 제가 같은 실수를 세 번째 했습니다** — 검증기·라이브 선언에 «먹여 보지 않고» 형태를 골랐습니다.
당신이 「코드를 쓰기 전에」 잡아서 잃은 것이 0입니다.

## 그래서 Phase 3.1 은 «판정 대기»로 되돌립니다
```
후보 다시    ㉮ fill_targets + 서버 통과로 (서버 세션 라운드가 필요 — 소유자 판정 사안)
             ㉯ Phase 3.1 을 «다른 설계»로
```
**당신이 세 번째 안을 지금 내지 않은 것도 맞습니다.** 총괄이 소유자에게 올립니다.

## ④ Phase 3 가 이 환경에서 «걸 화면이 없다» — 받습니다
```
virtual_join_rules   활성 규칙 «없음» (둘 다 _retired_ 접두)
enrichment_rules     reference_views 를 가진 유일한 규칙의 derived_table 이
                     table_config 에 «없어서» 그리드 드롭박스에 안 뜬다 (26표 중 부재, 실측)
```
「실패가 아니라 한계」로 적은 것이 정확합니다. **Phase 3 은 여기서 못 겁니다.**
그 사실 자체가 값이고, 그걸 재서 올린 것이 이 라운드의 산출입니다.

# ✅ 검수 — Phase 1–2 는 «받습니다»
```
파일 8개 전부 client2.  server/ 0.  ontology_explorer* 0   <- 겹침 없음
하네스   virtual_column_render_harness.mjs 2줄 = «앵커 갱신»뿐
         변이는 여전히 1회 적용되고 같은 결함을 지킵니다. 낮춘 것이 아닙니다
Chrome   당신이 «직접» 걸었습니다
```
🔴 **다만 `main` 에 «아직 병합하지 않습니다».** 소유자가 화면으로 먼저 보셔야 하고,
병합·재빌드는 구현자 가족이 끝난 뒤 총괄이 «한 번에» 합니다. 그때 알려 드리겠습니다.

## ▶ 지금 할 것
```
대기.  Phase 3 은 판정 대기이고 Phase 1–2 는 병합 대기입니다
필요하면  `design` 브랜치에서 다듬되, 새 Phase 를 «시작하지 마십시오»
```

---

# ✅ Phase 3 의 «걸 화면»을 만들어 드렸습니다 (소유자 지시, 21:4x)

당신이 「Phase 3 는 이 환경에서 걸 화면이 없다」를 **실측으로** 올렸고, 소유자가
「클라용 enrich 는 몇 개 만들자, 가상조인이랑 시나리오 짜서」로 답했습니다. 총괄이 만들었습니다.

## 이제 «있는» 것 — 전부 8080 API 에 실려 있습니다

### ① 참조 뷰가 달린 enrichment 규칙 «둘» (전에는 0)
```
dt_frame_confrimation    source dt_log        derived dt_inventory   views 3
core_frame_review        source dt_core_view  derived dt_inventory   views 3
```
🔴 **`dt_inventory` 는 table_config 에 «등록돼 있습니다»** — 그리드 표 드롭박스에 «뜹니다».
당신이 「선택 불가라 못 연다」고 재서 올린 그 벽이 이것으로 사라집니다.

각 규칙의 참조 뷰 셋:
```
1  이 job 의 원본 행            dt_log / dt_core_view 에서 그 job 의 행 전부
2  관측된 좌표 범위             x_min·x_max·y_min·y_max·cells   <- 프레임이 «덮어야» 하는 것
3  같은 장비의 다른 job / 쓴 core 웨이퍼
```
⚠️ 뜻을 «지어내지 않았습니다**. `dt_frame`·`core_frame` 은 평범한 값이 아니라
`{"frame_confirmed_from": …}` JSON 이력이라, 뷰는 「이 결정의 원본 행과 그 좌표 범위」까지만 보여줍니다.
그 이상은 좌표 도메인 판정이라 총괄이 만들지 않았습니다.

### ② 가상조인 «하나» (전에는 활성 0)
```
dt_log_frame_from_inventory
   dt_log  ⋈  dt_inventory   on dt_job   (cardinality one)
   expose  dt_x_base · dt_x_sign · dt_x_offset · dt_y_base · dt_y_sign · dt_y_offset
```
**`dt_log` 그리드에 좌표 프레임 6열이 «가상 컬럼»으로 붙습니다.** 126/401 job 에 값이 있습니다
(나머지는 위 enrichment 로 확정되면서 찹니다 — 두 기능이 «서로를 먹입니다»).

## 총괄이 이걸 만들려고 «고친» 것 — 알아 두십시오
```
table_config.dt_inventory   column_types 에 dt_job 추가        (DB 엔 있는데 선언에 없었다)
                            composite_key_source: ["dt_job"] 추가 (upsert 키 계약)
DB                          CREATE UNIQUE INDEX uq_dt_inventory_dt_job  (401/401 distinct 확인 후)
```
🔴 **`server/config/*` 는 gitignore 입니다 — «당신 워크트리에는 없습니다».**
당신이 워크트리에서 서버를 띄우면 이 규칙들이 «없습니다». 8080(메인 트리)으로 보십시오.

## ⚠️ 아직 «안 되는» 것 — 정직하게
```
dt_job_lot_slot_attribution   여전히 skip.  derived_table 'dt_job_attribution' 이 «미등록»
   그 규칙의 참조 뷰 5개가 제일 풍부한데 «못 씁니다»
   되살리려면 target_fields(dt_lot_confirmed·dt_slot_confirmed)를 dt_inventory 컬럼으로 바꿔야 하고
   auto_confirm: true 라 «400행에 자동으로 씁니다» -> 소유자 판정 사안. 총괄이 손대지 않았습니다
```

## ▶ 그러니 지금 할 수 있는 것
```
1  git fetch origin && git merge origin/main   (이 지시를 받는 법)
2  8080 에서 dt_inventory 를 표로 골라 참조 패널을 «연다»  -> Phase 3 를 실제로 걸어 본다
3  dt_log 그리드에서 가상 컬럼 6열이 뜨는지 «본다»
4  Phase 3.1 은 여전히 «판정 대기» — fill_targets 냐 다른 설계냐. 시작하지 마십시오
```
**걸어 보고 «무엇이 안 되는지»를 재서 올려 주십시오.** 그게 다음 라운드의 재료입니다.

---

# ✅ 판정 ⑤⑥ — 둘 다 «처리했습니다». Phase 3.1 착수하십시오 (22:0x)

> 소유자: 「알아서 써, 적당한 시나리오로」 — 총괄이 선언을 썼습니다.

## ⑥ 🔴 **제 잘못이었습니다. 고쳤습니다**
```
전   dt_inventory.display_columns = [dt_job_id, dt_eqp, dt_lot, ...]
     dt_job 은 401/401 채워져 있는데 «그리드에 없다» -> 앞 네 칸이 전부 빈 401행
후   display_columns[0] = "dt_job"     정체를 «맨 앞»에
```
`column_types` 에만 넣고 `display_columns` 에는 「최소 수정」으로 «일부러» 안 넣었습니다.
**그 최소가 틀렸습니다** — 행을 구별할 수단을 안 준 것이고, 당신이 재서 잡았습니다.
`dt_job_id` 가 401/401 비어 있다는 것도 그대로 보입니다. 그건 별개 문제로 남깁니다.

## ⑤ **`candidate_for` 로 갑니다. 반대 근거가 «제 뷰에는 성립하지 않습니다»**

당신이 철회한 이유는 정확했습니다 — «기존» 규칙은 두 대상이 서로 다른 뷰에 하나씩이라
순서를 말할 수 없었습니다. **그건 그 선언의 사실이지 `candidate_for` 의 한계가 아닙니다.**
새 뷰는 제가 모양을 정하므로 **두 대상을 한 뷰에 선언 순서로** 담았습니다.

```
새 규칙   dt_lot_slot_from_log
   source dt_log · derived dt_inventory · decision_key ["dt_job"]
   target_fields  ["dt_lot", "dt_slot"]          <- 순서가 곧 열 순서
   auto_confirm   false                           <- 사람이 확인한다
   view[0]  "관측된 dt_lot / dt_slot"
            candidate_for = {"dt_lot": "dt_lot", "dt_slot": "dt_slot"}
   view[1]  "이 job 의 원본 행 (근거)"
```
**총괄이 클라 투영까지 실측했습니다:**
```
to_public_rule(...)  ->  target_fields ['dt_lot','dt_slot']
                         view[0] candidate_for = {"dt_lot":"dt_lot","dt_slot":"dt_slot"}
                         view[1] EMPTY   (근거 뷰는 후보가 아니다 — 의도한 것)
[Enrichment] Synthesized 3 dedup chain rule(s)      <- 규칙 2 -> 3
```
🔴 **서버 코드 0줄입니다.** 이주 지시서의 전제(「서버 계약 변경 0」)가 지켜집니다.
`fill_targets` 는 «만들지 마십시오».

### 왜 이 시나리오인가 — 지어낸 게 아닙니다
```
dt_inventory.dt_lot / dt_slot   401 중 «400 이 빈칸»       <- 진짜 일거리
dt_log 는 같은 job 의 그 쌍을 «이미» 들고 있다              <- 표본 job: DT-2601-001 / 01 (72셀)
396 / 401 job 이 dt_log 에 행을 가진다
후보가 대개 «1개»  ->  선언 주석 그대로: 「후보가 1개면 판단이 아니라 확인」
```

## ▶ 이제 Phase 3.1 을 착수하십시오
```
읽을 것   view[0].candidate_for 의 «키 순서» = 열 순서
          (선언 순서가 곧 target_fields 순서이고, 둘이 같은 뷰에 있습니다)
⚠️ 다만  당신이 앞서 걱정한 「순서가 로더를 거쳐도 보존되나」는 «여전히 유효한 질문»입니다.
          위 실측에서 순서가 보존됐지만, 그건 «표본 하나»입니다.
          Phase 3.1 이 순서에 «기대기 전에» 그 가정을 코드 주석에 적어 두십시오 —
          깨져도 조용한 종류입니다
```

## ⚠️ 그리고 이건 «남깁니다»
```
dt_job_lot_slot_attribution   여전히 skip (미등록 표) · auto_confirm true · 400행 자동 기록
   -> 소유자 판정 사안. 새 규칙이 그 자리를 대신하므로 «급하지 않습니다»
```

---

# ✅ 「브랜치를 못 띄운다」 — **길이 이미 코드에 있습니다** (22:1x)

`0fcabbb9` 의 막힘(자기 브랜치를 서빙 못 해서 3.1 을 못 걷는다)에 대한 답입니다.
**병합도, 설정 복사도, 두 번째 서버도 필요 없습니다.**

```
client2/src/config.js:1-3
   const isDevServer = window.location.port === '5173';
   API_BASE = isDevServer ? 'http://127.0.0.1:8080' : window.location.origin;
   WS_URL   = 같은 판정
```
```
main.py:157-159   allow_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
총괄 실측         두 Origin 모두 access-control-allow-origin 이 «되돌아옵니다» (curl 로 확인)
```

## 그래서 이렇게 하십시오
```
cd C:/Users/kk980/Developments/assyManager-design/client2
npm install        (아직 안 했으면 — node_modules 는 git 에 없습니다)
npm run dev        -> :5173
```
```
클라 코드   당신 워크트리의 것          <- 당신이 고친 3.1 이 그대로 돕니다
API·설정    메인 트리의 8080            <- enrichment 규칙 3개 · 가상조인 · dt_job 표시열
```
🔴 **포트가 5173 이어야 합니다.** 5173 이 막혀 있으면 vite 가 5174 로 올라가고
`isDevServer` 가 «거짓»이 되어 API 를 자기 자신에게 겁니다. 그러면 전부 404 입니다.
`npm run dev -- --port 5173 --strictPort` 로 «강제»하고, 못 잡으면 그 사실을 보고하십시오.

⚠️ **여전히 `npm run build` 는 하지 마십시오** — dev 서버는 dist 를 안 만듭니다.
빌드는 착지 후 총괄이 메인 트리에서 한 번만 합니다.

## 그리고 방금 바뀐 것 둘 — dev 로 띄우면 바로 보입니다
```
dt_inventory 그리드   맨 앞이 dt_job (⑥ 수정)
enrichment 규칙       3개 — 새 dt_lot_slot_from_log 의 view[0] 에 candidate_for 가 «둘 다»
```
