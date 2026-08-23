# 응용 기획 세션 → 총괄 (단일 정본, 파일·커밋 채널)

> 세션 간 메시지는 쓰지 않습니다. 이 파일이 채널이고 커밋이 초인종입니다.
> 총괄 회신은 `task/` 아래 판정 파일로 받습니다.
> 🔴 **맨 위가 «지금» 요청입니다.** 아래는 시간순 기록이고 철회된 것이 섞여 있습니다.

---

# 🔔 깨어난 총괄에게 — 승인된 라운드에 «레인이 안 걸려» 있습니다 (10:5x)

보드 `컴팩트 인수` 가 제 라운드를 「도는 중 · 착수 승인됨」으로 적었는데,
**아직 구현자에게 안 갔습니다.** 같은 절이 구현자를 「대기 · 새 일감 만들지 말라고 걸어 둠」
으로 적어 두어서, 이대로면 조용히 섭니다.

```
할 일   PROPAGATION 공사 1 -> 공사 3 을 구현자 대기열에 «걸기»
근거    판정 a256ce50 (착수 승인) · 지시서 84ac25f4 (오늘 재료·울타리 반영본)
제 몫   아닙니다 — 「지시서를 총괄에게 올리십시오, 직접 짜지 마십시오」
```

## 그 전에 제가 확인한 것 — 공사 1 의 전제는 «오늘도 참»입니다

§4 가 하루 만에 낡았던 적이 있어서 착수 전에 다시 쟀습니다:

```
config/mechanism_models.json   void_formation 19/18 · delam_formation 5/3
                               · void_observation_bias 2/1     지시서와 «일치»
bindings                       6항목 중 하나가 `__doc` -> 실질 «5»  일치
mechanism_gate.load()          있음. 호출 성공 -> MechanismGraph   일치
```

**공사 1 은 지금 그대로 착수 가능합니다.**

---

# ✅ 요구하신 «닿는다/안 닿는다» 목록 — 파일 단위 실측 (2026-08-23 10:2x)

> 총괄 판정 `d1b86031`: 「8/21 의 «2번부터» 철회 · 글롭 밖에 짓는다 ·
>  **무엇이 닿고 안 닿는지 당신이 목록으로, 파일 단위로, 실측으로**」
> 접수했습니다. 아래가 그 목록이고, 마지막에 ② 첫 라운드를 다시 잡았습니다.

## 1. 서버 파일 — 세 부류로 갈립니다

```
A. 글롭 «안» — 이름이 걸린다                                        4개
   server/ledger_trace.py · ledger_trace_router.py
   server/ledger_admin.py · server/ledger/config.py

B. 글롭 «밖» · ledger_trace 결합 = «SQL 헬퍼 둘»                     6개
   ledger_subgraph.py    import ledger_trace -> `_fetch` 딱 1곳 (:243)
   ledger_catalog.py     from ledger_trace import _fetch
   ledger_composition.py · ledger_selection.py · ledger_siblings.py · ledger_trends.py
                         from ledger_trace import _fetch, relation_exists
   -> `_fetch` 는 「psycopg2든 Session이든 SQL 을 돌린다」는 커넥션 헬퍼이고
      `relation_exists` 는 `to_regclass` 게이트다 (ledger_trace.py:1539·1561).
      «어휘도 계보도 안 들고 있다.» 새 일을 얹는 것과 무관하다

C. 글롭 «밖» · 그러나 해결기·어휘를 «가져간다» — ③ 때 같이 죽는다     4개
   ledger_explorer.py   10심볼  load_resolver_config · traversal_predicate
                                lineage_predicates · claim_class · hop_basis · live_claims ...
   ledger_structure.py   8심볼  load_resolver_config · RESOLVER_CONFIG_FILENAME · coverage ...
   ledger_journey.py     8심볼  Claim · claim_class · claim_rank_key · CLASS_NAMES ...
   ledger_lots.py        1심볼  LINEAGE_PREDICATES
   -> 🔴 이름은 글롭 밖인데 «실질은 안»입니다. 여기에도 새 일을 얹지 마십시오
```

## 2. 제 지시서 둘을 그 목록에 대면

```
PROPAGATION   공사 1  mechanism_gate.py + config/mechanism_models.json
                     -> mechanism_gate 는 «stdlib 만» 임포트한다. ledger 의존 0    ✅ 안 닿음
              공사 3  ledger_subgraph.subgraph() 확장 — B 부류                    ✅ 안 닿음
              공사 2  ledger/vocabulary.py 의 `traversable` 을 읽는다              🔴 닿음 (§3)

ANYWHERE_SEED 공사 A·B  ledger_trace_router.py — A 부류                            ⛔ 보류
              클라 확장  서버 무관                                                 (client-pm)
```

## 3. 🔴 공사 2 는 «두 번» 낡았습니다 — 판정하신 것보다 한 겹 더

```
읽을 선언이 있는 곳    ledger/vocabulary.py   observed 의 traversable: None
                      -> v1 계통. ③ 에서 은퇴. 지금 하면 «은퇴할 것에 새 소비자»

라이브 v5 설정         vocabulary 항목이 가진 키가 {object, status, subjects} «뿐»
                      traversable «없음» · direction «없음»
                      v5 가 선언한 술어 6개에 observed «자체가 없음»
                      (derived_from · has_netdie · has_wafer · register · slot_map · transfer)
```

**즉 v5 세계에는 공사 2 가 읽을 선언이 아예 없습니다.** 은퇴 문제가 아니어도 지금은 못 합니다.

## 4. 그래서 ② 첫 라운드 — 이렇게 제안합니다

```
간다    PROPAGATION 공사 1  ->  공사 3
        브리핑의 «1 없으면 3 의 collect: Quantity 가 빈 답» 의존은 그대로 유효.
        공사 2 는 그 둘과 «독립»입니다 (수락도 「기존 응답이 안 변하는지」였습니다)
보류    PROPAGATION 공사 2      ③ 뒤 · 또는 v5 가 그 축을 선언한 뒤
보류    ANYWHERE_SEED 서버 절반  글롭 안
```

## 5. 오늘 재료가 바꾸는 것 하나 — walk 을 «무엇 위에» 태울까

```
전사 원자        원장에 «0».  ledger_translator_cursor 에 transfer_event 행 «없음»
                 (보드의 199 는 시험 실행값이고 시험 실행은 쓰지 않습니다 — 설계대로)
씨앗 이름 공간    SYN-XFER-CORE-W01~W10 · SYN-XFER-D01~D10
                 원장에 등록된 Wafer/DTJob 과 겹침 «0»
```
**그래서 공사 3 의 수락은 `lot_event` 재료 위에서 받는 것이 맞습니다** —
`has_wafer` 907 · `derived_from` 40 · `slot_map` 226 이 실재하고 서로 이어집니다.

## 6. 적어만 둡니다 (일이 아닙니다)

`_fetch`/`relation_exists` 를 쓰는 모듈이 **여섯**입니다. ③ 때 그 헬퍼 둘의 «갈 곳»이
필요합니다. **지금 옮기면 그게 새 일입니다** — 옮기지 말고 ③ 의 재료로만 적어 둡니다.

---

# ✅ 요청 D — 판정 접수 (`d1b86031`). 이 절은 닫힙니다

총괄이 **자기 8/21 판정을 철회**했습니다. 제 서버 절반은 보류이고, 위 §4 로 대체합니다.

---

# 🔴 지금 총괄 판정 요청 (2026-08-21 갱신)

## 요청 A — 지시서 둘의 «착수 승인»

제 레인 산출물이 나왔습니다. **둘 다 서버 코드를 만지므로 구현자 대기열은 총괄 소관입니다.**

```
1  task/APPLICATION_PROPAGATION_BRIEF.md     전파가 설 땅을 잇고 walk 를 얹는다
      바뀌는 층  server/ledger_subgraph.py  «만»
      그대로     ledger_trace.py · 원장 스키마 · 어휘 · 설정 형식
      크기       공사 셋 (기전 엣지 합성 · observed 선언 판별 · walk start±/collect)

2  task/APPLICATION_ANYWHERE_SEED_BRIEF.md   클릭한 글자가 씨앗이 된다
      바뀌는 층  ledger_trace_router.py · ledger_catalog.py  + 클라 확장
      크기       엔드포인트 하나 + 타입 강제 해제 + 확장
```

🔴 **2 는 1 을 «기다리지 않습니다».** `resolve` 는 `walk` 없이도 기존
`explore_entity` 로 쓸모가 있습니다. `lot_event` 라운드와 병렬 가능합니다.

## 🔴 요청 D — `resolve` 를 «어디에» 놓습니까 (은퇴 글롭과 충돌)

> 🔴 **2026-08-23 10:0x — 이제 «가정»이 아니라 «막는 것»입니다.** 보드 `c51552f3` 로
> ① 이 닫혔고 ② 가 제 차례입니다. 그리고 8/21 판정이 「레인 비는 대로 **2번부터**」로
> 정해 두었는데, 그 2번의 서버 절반이 이 글롭 안에 있습니다.
> ⚠️ 8/21 판정문은 서버 쪽을 「`ledger_trace_router`·`ledger_catalog`」로 **명시**했습니다 —
> 그건 은퇴 규칙이 조여지기 «전»에 쓰인 것입니다. **판정과 규칙이 지금 서로 어긋나 있습니다.**


보드가 `a8c7a5cd` 에서 규칙을 다시 못 박았습니다: **은퇴 대상에 «새 일을 얹지 않는다»,
대상은 `ledger_trace*` · `ledger_admin` · `ledger/config.py` · 그 네 화면.**

**제 `ANYWHERE_SEED` 공사 A·B 가 그 글롭 안에 착지합니다.** 실측:

```
공사 A  GET /api/ledger/resolve  를 «새로» 만든다      -> ledger_trace_router.py
공사 B  /entities 의 타입 강제 해제 (:157 Query("Lot"))  -> ledger_trace_router.py
```

⚠️ **그런데 그 파일은 혈통 전용이 아닙니다.** 실측 — 라우트 17개 중 혈통은 셋뿐:

```
혈통      /trace · /explore · /explore_entity                        3
그 밖     /entities · /subgraph · /subgraph/table · /siblings · /journey · /trends
          /composition · /selection/resolve · /kinds · /structure · /lots
          /lot_map · /coverage                                       14
```

그래서 **글롭이 무엇을 뜻하는지에 따라 제 ② 첫걸음이 갈립니다:**

```
가  파일 통째 은퇴      공사 A·B 를 «새 모듈»에 놓아야 한다 (지시서 한 줄 수정)
나  혈통 라우트만 은퇴   지금 지시서 그대로 착지한다
```

**제가 정할 수 없습니다. 판정 한 줄이면 됩니다.** 그때까지 지시서는 안 건드립니다
(총괄 지시 「다듬지 말고 대기」 + 「버그를 봐도 고치지 말고 적는다」).

📎 곁가지 확인 — 기존 `POST /selection/resolve` 는 **같은 연산이 아닙니다.**
그건 «타입 지정된 UI 마킹»(trend/map/time)을 CHIP 증거로 푸는 것이고
`ledger_selection.py:_identity_unit` 이 `Wafer` 아니면 `None` 을 냅니다.
글자→신원 해소가 아니므로 **중복 제작이 아닙니다.**

## 정정 — 앞서 「제 응용은 은퇴 계통 위에 서지 않습니다」 (아래 절)

**절반만 맞습니다.** 맞는 부분: 런타임 의존이 없다(해결기 config 를 안 탄다).
틀린 부분: **«편집 위치»를 안 봤습니다.** 안 타는 것과 그 파일에 안 쓰는 것은 다릅니다.

## 요청 B — 클라 확장이 어느 레인입니까

브라우저 확장(클릭 잡기 + 패널)은 새 산출물입니다. client-pm 인지, 별도인지 모릅니다.

## 요청 C — ⚠️ 사내 화면 텍스트가 서버로 나갑니다

**클릭한 선택 영역 «하나»만** 보냅니다(전체 스캔 금지를 지시서에 못 박음). 최소이지만
**판단은 제 것이 아닙니다.** 소유자 판정이 필요하면 올려 주십시오.

## ✅ 철회 — 앞서 올린 「`ledger_subgraph.py` 가 어느 레인인가」

**제가 잘못 물었습니다.** 브리핑 §0 이 이 세션의 일을 「지시서를 쓰고 구현자에게 넘긴다」로
정해 두었습니다. 레인 질문은 «구현» 을 물은 것이고, 그건 애초에 제가 할 일이 아니었습니다.
**지시서는 썼고, 남은 것은 착수 승인(요청 A)뿐입니다.**

---

# 산출물 (제 레인, 승인 불요)

```
APPLICATION_VALID_NOW.md              🔴 «지금 유효한 것만» 한 장.
                                      오늘 정정 열두 번이 문서 여섯에 얽혀 있어
                                      죽은 주장을 «이름 붙여» 나열했습니다.
                                      새로 오는 사람은 여기부터
APPLICATION_PROPAGATION_BRIEF.md      지시서
APPLICATION_ANYWHERE_SEED_BRIEF.md    지시서
ontology_declaration_diagnosis_run.md §13 실행 결과 — 원장 없이 돌았고 선언 결함 하나 잡음
```

## 이번에 닫은 미설계 둘

```
관장 엣지      자리는 실재(6개)하나 «필요 미실증». 그리고 새 선언이 아니라
              기존 bindings 키 확장으로 족합니다 -> 판정 대기에서 뺐습니다
경로 요인      대수로는 «불가»(증명). 방문기록 탐색이고, 대부분은 원자 집계로 족합니다
              -> §19.1 이 질량의 순환 대책으로 고른 것과 «같은 장치»입니다
```

⚠️ 그 과정에서 제 앞 주장 하나가 반증됐습니다 — 「멱등이면 순환 안전」이 부족했습니다.
`(max, +)` 는 바깥이 멱등인데도 발산합니다. **안쪽도 누적하지 않아야 합니다.**

---

## ✅ B 확인 완료 — 서버/클라가 분리돼 있습니다

총괄 요청(「분리돼 있는지만 확인해 두라」)에 대한 답입니다.

```
A + B  서버   클라 확장 «없이» 착지·검증된다. 수락 단언 넷 전부 확장 없이 판정 가능
C      클라   A+B 뒤에 열면 된다. 의존은 «단방향»
```
지시서 §4 에 그 한 줄을 명시했습니다(구조는 원래 나뉘어 있었고, 「서버 절반이 혼자
선다」가 안 적혀 있었습니다).

## 대기 상태로 들어갑니다

총괄 지시: 「지시서를 더 다듬지 말고 대기하라 — 아직 안 도는 것을 계속 정교하게
만드는 것이 오늘 지운 것들의 유래다」. **접수했습니다.** 위 한 줄 외에 더 손대지
않습니다. 레인이 열리면 그때 움직입니다.

---

# 🔴🔴 정정 — 제 「trace 가 최우선」을 «되돌립니다» (2026-08-21 23:4x)

소유자가 순서를 정했고(보드 23:2x) **그 순서가 제 앞 보고를 무효로 만듭니다.**

```
① 기반 원장 셋업 완주
② 온톨로지 응용 착수      APPLICATION_{PROPAGATION,ANYWHERE_SEED}_BRIEF  ← 제 것
③ 그때 «은퇴»            혈통 추적 · ledger_trace* · ledger_admin · ledger/config.py
🔴 규칙                  은퇴 대상에 «새 일을 얹지 않는다». 버그를 봐도 «적기만» 한다
```

## 무엇이 틀렸나

앞 절에서 「`trace` 503 은 config 하나 고치면 풀린다 — **제 쪽 최우선**」이라고 올렸습니다.
**그 대상이 은퇴 계통입니다.** 총괄이 이미 두 번 그 자리에 손댈 뻔했다가 되돌렸고
(샘플 반쪽 수리 · 503 수리 지시), **제 보고가 세 번째를 부를 뻔했습니다.**

**우선순위를 내립니다. 수리 요청이 아니라 «적어 둔 사실»로만 두십시오.**

## 그런데 정정하면서 제 지시서의 «전제»가 틀린 것도 나왔습니다 (실측)

```
해결기 config 에 걸리는 라우트   /trace · /explore · /explore_entity · /journey · /structure
안 걸리는 것                    /entities (카탈로그) · ledger_subgraph (=_fetch 만 씀)
```

🔴 `ANYWHERE_SEED_BRIEF` §7 이 **「`resolve` 는 `walk` 없이도 기존 `explore_entity` 로
쓸모가 있다 → 병렬 가능」**이라고 적었습니다. **`explore_entity` 가 지금 503 이고,
게다가 은퇴 대상입니다.** 살아날 것에 기대어 병렬성을 주장했습니다.

### 시정 — 두 지시서의 관계가 바뀝니다

```
이전   ANYWHERE_SEED 가 PROPAGATION 을 «안 기다린다» (explore_entity 로 쓸모)
정정   패널의 «내용»은 PROPAGATION 의 walk 가 준다.
       ANYWHERE_SEED 단독으로 서는 것은 «resolve 까지» — 글자 -> 노드 신원 해소
```
`resolve` 자체는 여전히 독립입니다(`/entities` 계열이라 해결기를 안 탑니다).
**다만 「그래서 패널에 주루륵 뜬다」까지 가려면 `walk` 가 필요합니다.**

⚠️ 소유자 순서 ②에 둘이 «같이» 올라 있으므로 실무상 문제는 아닙니다.
**틀린 것은 제 「병렬 가능」 주장이지 순서가 아닙니다.**

## 그리고 제 응용은 은퇴 계통 위에 서지 «않습니다» — 이건 맞습니다

`PROPAGATION_BRIEF` §2 가 「전파는 걷기 위가 아니라 «투영»(`ledger_subgraph`) 위에 선다,
`ledger_trace` 를 건드리지 말 것」이라고 이미 못 박았습니다. **실측으로 확인됩니다** —
`ledger_subgraph` 는 `ledger_trace._fetch`(SQL 헬퍼)만 쓰고 해결기를 안 탑니다.

**그러므로 ③ 은퇴가 제 응용을 안 깹니다.** 그 판단은 유지합니다.

---

# ✅ 원장이 흐른 뒤 — 제 예측 둘이 맞았고, 하나가 «급해졌습니다» (2026-08-21 21:0x)

보드 §「`lot_event` 이 흐른다 · 원자 1,323 · 계보 40」에 대한 것입니다.

## 예측 ① 술어가 «버전 없이» 저장된다 — 맞음

```
선언   derived_from@1 · has_wafer@1 · Lot@1 · Wafer@1
원자   derived_from   · has_wafer   · Lot   · Wafer      (보드 실측)
```
2026-08-20 에 `roleframe.py:987 _runtime_id` 를 읽고 예측한 그대로입니다
(적용 지점 :1137 객체타입 · :1167 주어타입 · :1169 술어). **실원자로 확인됐습니다.**

## 예측 ② 걷기의 리터럴 목록이 «맞아떨어진다» — 맞음. 그리고 이게 급합니다

```
원자에 있는 술어    has_wafer 907 · slot_map 226 · derived_from 40 · register 150
걷기가 찾는 것      ('derived_from', 'has_wafer', 'register', 'slot_map')
```
🔴 **정확히 일치합니다.** 걷기의 하드코딩된 이름 넷이 «지금 쌓인 원자와 같습니다».

### 따라서 `trace` 판정의 무게가 달라집니다

```
원자        계보 40행이 «원장에 있다» (보드가 원자에서 직접 뽑아 확인)
술어 이름   걷기의 목록과 «맞는다»
남은 것     해결기 config «하나»
```
**「언젠가」가 아니라 「config 하나 고치면 계보가 보인다」입니다.**
제 응용 ①③④⑥ 이 그 위에 서므로, 제 쪽에서는 이 판정이 가장 앞섭니다.

⚠️ 다만 앞 절에서 적은 대로 **「샘플만 고치기」는 가짜 초록**입니다 — 원장은 v3 로 쌓이고
샘플은 v1 이라, 그 경로로는 이 40행을 못 봅니다.

## 브리핑 §6-3 「원장 행 수·predicate 분포를 센다」 — 총괄 실측으로 대체합니다

제가 「운영과 다르니 보류」로 남겨 둔 항목입니다. 총괄이 실측했고 제가 DB 를 안 만져도
됩니다. **다만 이 수치는 여전히 이 박스의 것이고 운영이 아닙니다** — 운영 원장은
수백만 행(총괄 확인). 응용 설계의 «모양» 검증에만 씁니다.

---

# 🔴 보탤 사실 — `trace` 503 은 «샘플 문제가 아니다» (2026-08-21 20:5x)

보드 §「`trace` 원자와 무관하게 전부 거절 — 판정 대기」에 대한 것입니다.
**제 세션이 세션 초반에 같은 구조를 실측해 뒀습니다.** 총괄 1·2차 원인 «위»의 사실입니다.

## 실측 (방금 재확인)

```
v1 이 읽는 파일        server/config/ledger_config.json          🔴 «없다»
v1 어휘 확장 파일      server/config/ledger_vocabulary.json      🔴 «없다»
v3 라이브             server/config/ontology/ledger_config.json  있다 (19:43)

v1 샘플 최상위 절   setup_version · vocabulary · entities · packs ·
                   source_preparers · mappers · profiles · sources   (8절)
v3 라이브 최상위 절  setup_version · vocabulary · entities · sources   (4절)
```

## 🔴 그래서 샘플을 고쳐도 안 됩니다

```
① 파일이 «다르다»       v1 경로와 v3 라이브는 «서로 다른 파일»이다.
                       샘플의 use 를 고치면 v1 이 «샘플»로 돌 뿐, 소유자가 화면에서
                       만드는 v3 선언과 연결되지 않는다
② 샘플이 «오늘 낡았다»   오늘 packs·claims 절을 지웠다(9b6c5da0). 샘플엔 그대로 있다.
                       v1 검증기는 그 절을 «요구»하고 v3 는 «없앴다» — 갈수록 벌어진다
③ 구 어휘도 «비어 있다»  ledger_trace 는 구 vocabulary.py 를 읽고, 그 확장 파일이 없어서
                       코드에 박힌 13술어·6개체만 안다. DTJob 을 «모른다»
```

## 제 세션이 이미 보고한 것과 같은 자리입니다

```
2026-08-20 실측    「쓰기 파이프라인은 v3, 읽기 응용 다섯은 구 어휘. 서로 안 본다」
총괄 회신          「병존이 현재 상태다. 통일 판정은 «내려진 적 없다»」
오늘 20:4x         그 병존이 실제로 trace 를 죽였다
```
근거: `task/ontology_vocab_hardcode_scan.md` §「v3 기준 재측정」

## 판정에 도움이 될 갈래 (제 판단 아님, 재료만)

```
가  v1 경로를 «은퇴»                trace 가 v3 를 읽게. 읽는 응용 다섯이 같이 걸린다
나  v1 라이브 파일을 «만든다»         샘플 폴백을 끊는다. 다만 두 선언을 사람이 «두 번» 쓴다
다  샘플만 고친다                   🔴 이 박스에서만 초록. 소유자 화면의 선언과 무관
```
⚠️ **「다」가 가장 싸 보이지만 «가짜 초록»입니다** — 원장은 v3 로 쌓이는데 trace 는
샘플을 읽습니다. `derived_from@1` 원자가 40행 나와도 그 trace 는 못 봅니다.

## 왜 지금 올리는가

원장이 방금 뚫렸고 **계보 원자가 처음 생깁니다(40행 예정).** 그것을 «볼» 경로가
`trace` 인데 지금 503 입니다. **제 응용 ①③④⑥ 이 그 경로 위에 섭니다.**

---

# ── 이하 시간순 기록 ──

# 사실 보고 — 넘길 것 둘 (판정 아님)

## ① 🔴 기전 선언 결함 — `delam_formation` 에 고아 노드

```
nodes   bond_pressure · die_stress · tape_adhesion_anomaly · backside_damage · delam
edges   bond_pressure -> die_stress -> delam
        backside_damage -> delam
        🔴 tape_adhesion_anomaly 에서 «나가는 엣지가 없다»
```
원인으로 선언됐는데 `delam` 에 닿는 경로가 없습니다. **사람이 읽어서는 안 보입니다** —
노드 목록에 이름이 있으니 「선언돼 있다」로 읽힙니다. 전파가 «활성 0 · 경로 0» 을 내며
드러났습니다.

의도인지 누락인지는 선언 소유자가 압니다. (`void_formation` 에는
`tape_adhesion_anomaly -> backside_damage` 엣지가 있습니다.)
근거: `task/ontology_declaration_diagnosis_run.md`

## ② 일반화 규율 위반 — `ledger_selection.py:542`

```python
if finding_kind == "void" and final_units:
```
`SCENARIO_CONSOLE_BRIEF` §0: 「코드에 기본값 아닌 `finding_kind='void'` 하드코딩이 보이면
일반화가 소실된 것」. kind 는 **지금 이미 여럿**입니다(void · delam 선언됨).

부수 확인: 클라가 보내는 `claim_filter` · `metric_region` 이 `ledger_selection.py` 에
없습니다. 다른 모듈일 수 있어 단정하지 않습니다.

---

# 판정 수신 확인

`task/ontology_predicate_id_ruling.md` 읽었습니다.

```
판정        predicate -> 불변 id 는 «보류». packs 제거만 진행
제 논거     시점 논거는 «약해졌다» — 총괄 실측(792행·계보 원자 0개)이 맞습니다
제 오류     남이 준 «상태» 를 논거 핵심으로 쓰면서 쓰기 직전에 다시 안 쟀습니다
            (b100fb2a 11:26 에 전제가 뒤집혔는데 그 뒤에 보냈습니다)
가장 큰 것  소유자 지적 — 「소스 표는 의미가 있는데 원자만 의미를 숨기면 층이 비대칭」.
            제가 한 층만 보고 층간 대칭을 안 봤습니다
```

**그리고 제 제안이 오늘 지운 것들과 «같은 부류»였습니다** — `profiles`·`claims` 가
「여럿이 쓸 줄 알고」 만든 층이었듯, id 도 「이름이 여럿이 될 줄 알고」 만드는 층이었습니다.
지금 이름은 하나뿐입니다. 이 교훈을 브리핑에 박았습니다.

---

# 내 레인 진행 상황 (승인 불요, 보고만)

```
어휘 하드코딩 전수 스캔     완료. v3 재측정 포함     ontology_vocab_hardcode_scan.md
응용 방향 (A·B 기각/C 채택)  완료                    ontology_application_direction.md
근본 알고리즘 + 수학        완료 §1~22              ontology_application_algorithm.md
임의 질문 설계             완료 §1~13              ontology_arbitrary_question.md
「무한 케이스」 감사        문서 넷 전부 완료
§13 선언 진단 «실행»       완료 — 원장 없이 돌았음   ontology_declaration_diagnosis_run.md
```

**핵심 산출 하나:** 대조가 전파의 «k=1 절단» 임을 유도·실측했습니다(비율 차와 항등,
오차 1e-12). 그래서 대조 엔진이 못 보던 것들(혈통 공통점·경로 요인·기전 연결·미계측)이
«기능 넷»이 아니라 «고차항 하나»입니다. 근거: `ontology_application_algorithm.md` §15~17.

**미설계로 남긴 것 둘:** 관장 엣지(자릿수를 안 세고 제안했음 — 재검토 중) ·
경로 요인(멱등 대수로 원리상 불가, 비면등 축 필요).

---

# 추가 보고 (2026-08-21, 커밋 1a7445c0 이후)

## 「관장 엣지」 제안을 내립니다 — 제가 과했습니다

앞서 공사 목록 5번으로 「관장 엣지 선언 신설」을 올렸습니다. **자릿수를 세고 나서 내립니다.**

```
실측   물리량 노드 23 · 뿌리 10 · 측정 가능 3 · 미측정 «6» (dt_pass_count 은 경로 특징이라 제외)
```
자리는 실재합니다. 그러나:

```
① 없어도 대조가 돈다      「컨트롤은 A 설비, 케이스는 B」까지는 대조가 이미 냅니다.
                         관장 엣지가 더하는 것은 «설명» 이지 «능력» 이 아닙니다
② 새 선언이 아니다        bindings 의 «키를 술어 수준까지 넓히면» 됩니다.
                         지금은 `processed_with:<필드>` 라 값이 있어야만 붙습니다
```
**브리핑의 「선언 신설 3문」 첫 문이 안 닫힙니다** — 기존 선언의 필드로 들어갈 수 있습니다.
그래서 «신설 판정»으로 올릴 사안이 아니었습니다. 총괄 판정 대기에서 뺍니다.

⚠️ 남는 미해결 하나: 「CMP 가 두께를 관장한다」는 **공정 지식**이지 스키마 지식이 아닙니다.
지금 bindings 를 적는 사람이 그것도 적을 수 있는지는 «세지 못했습니다».

## 그래서 지금 총괄 판정 대기는 «하나»입니다

    🔴 `server/ledger_subgraph.py` 가 제 레인입니까, 서버 레인입니까
