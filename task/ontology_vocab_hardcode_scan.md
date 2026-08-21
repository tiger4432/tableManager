# Vocabulary hardcoding scan — do the existing consumers survive a vocabulary swap?

**Asked by owner, 2026-08-20**, with the caution that follows it:
「지금 원장 및 어휘 설정은 운영 환경과 전혀 다르다」.

That caution is what sets the pass mark. The question is not 「is there a literal」 —
it is **「if every predicate and entity type is renamed, does this code still answer,
refuse loudly, or answer wrongly in silence?」** Only the third is a defect.

## Method

Declared vocabulary read from the module itself, not from memory:

    ENTITY_TYPES  Die · Equipment · Lot · Product · Recipe · Wafer          (6)
    PREDICATES    assigned_to_experiment · derived_from · frame_confirmed ·
                  has_param · has_wafer · measured · observed · pin ·
                  processed_with · register · same_as · slot_map ·
                  transferred                                              (13)
    all_predicates() == PREDICATES today — config declares no extra word yet.

Every quoted occurrence of those 19 names was collected across the five ledger-reading
server modules and all of `client2/src`, then narrowed to **executable lines only**
(Python: tokenizer, docstrings and comments dropped; JS: comment lines dropped).

🔴 **Two classes of false positive were removed by hand, and they are most of the raw
count.** `"measured"` is also a READING STATE (`state: "measured"` vs
`"not_in_population"`), and `"pin"` is also a RESOLUTION CLASS (`pin/confirmed/
observation/inference`). Neither is the predicate of the same spelling. Raw scan: 138
literals. After comment and homonym filtering: **41 real sites.**

## Verdict

### Server — four of five modules are clean, one is not

    ledger_structure.py    CLEAN — both halves generated (vocabulary x all_predicates,
                           plus one GROUP BY). No predicate name decides anything.
    ledger_kinds.py        CLEAN — zero vocab literals on any executable line.
    ledger_journey.py      CLEAN — the one hit is `state: "measured"`, a reading state.
    ledger_walk_contrast.py CLEAN — both hits are a reading state and a comment.
    ledger_trace.py        🔴 NOT CLEAN — see below.

### 🔴 `ledger_trace.py` — the fetch layer honours the declaration, the answer layer does not

The module splits into LOOKUP (fetch) and WALK (answer), and the split is exactly where
the defect lives:

    LOOKUP   declaration-driven. `traversal_predicate()` and `lineage_predicates()`
             read `traversable` / `direction` off the vocabulary; the recursive CTE
             interpolates the DECLARED name (`{"traverse": traversal_predicate()}`,
             lines 1026 / 1096). Rename the lineage word and the CTE follows it.

    WALK     literal. `trace()`'s three questions ask by hardcoded name:
                 has_wafer     1375 · 1379 · 1383   (which wafer sits at this slot)
                 derived_from  1386 · 1394 · 1403 · 1407  (which lot did this come from)
                 register      1368 · 1388          (does this lot exist at all)
                 slot_map      1420 · 1467 · 1474 · 1483 · 1484 · 1493
             plus the sample query at 2018 (`predicate = 'derived_from'`) and 2031
             (`predicate = 'has_wafer'`).

**The guard does not close this.** `traversal_predicate()` (lines 115–147) refuses a
declaration it cannot execute — but it checks the **count** (`len(traversable) != 1`)
and the **direction** (`!= "subject_to_object"`). It never checks the **name**.

**Failure mode on a production vocabulary whose lineage word is not `derived_from`:**

    1. guard passes            — one traversable predicate, subject_to_object. OK.
    2. CTE fetches correctly   — it interpolates the declared name.
    3. `at(cur_lot, "derived_from")` returns []  — the atoms are there under another word.
    4. every trace answers `[root] lot=... · derived_from 없음 — 사슬의 뿌리`

That is a confident, well-worded **false 「this lot has no lineage」** on a ledger that
holds the lineage. Not a crash, not a refusal — the walk reports absence.
This is `a-permanently-false-filter-hides-while-false-is-right` and
`a-guard-goes-wrong-the-day-it-becomes-reachable`, in one function.

### 🔴 Same module — the walk is pinned to `Lot` as a subject type

    936   `if c.subject_type == "Lot" and c.subject_lot in wanted`
    1344  `if c.subject_type != "Lot"`
    964 · 983 · 995 · 1038 · 1701   `subject_type = 'Lot'` inside SQL
    1223 · 1230                     node shapes `{"type": "Lot"}` / `{"type": "Wafer"}`

`rollup_subject_types()` exists in this very module (line 97) precisely so a reader does
not pin a type — its docstring names `subject_type = 'Wafer'` as the anti-pattern — and
`ledger_journey` (613) and `ledger_walk_contrast` (626 · 641) both use it.
`ledger_trace`'s own `claims_for_lots` does not.

### Client — the walk hardcode is mirrored, plus a default subject type

    ledger_trace_core.js   291 · 303  `predicate === 'slot_map'`
                           535        `h.predicate === 'derived_from'`
                           — the client re-derives hop meaning from the same two names.
    rnd_console/api.js     195 · 320  `category === 'processed_with'` branch
    rnd_console/*          11 sites   `subjectType: 'Wafer'` as the default identity type
                           (main.js 220·225·245·300·304·309, api.js 126·144,
                            state.js 30·173·176)
    ledger_graph/main.js   105 `edge.predicate === 'derived_from'` (label rule)
                           239 `{type:'Lot'}`
    entity_catalog.js      46 · 50 · 94  `'Lot'` as the default selected type

    Clean: case_control_core.js · case_control_view.js · surprise_*.js —
    every hit there was a comment. The case-control console branches on no vocab name.

### Lesser: the resolution-class list is spelled four times

`pin · confirmed · observation · inference` appears as its own list in
`ledger_trace.py:410`, `ledger_structure.py:206`, `ontology_structure_core.js:106`,
`ontology_structure_view.js:132`. These are §4.1 canonical and effectively frozen, so
this is drift risk rather than a production break — but it is four lists of one fact.

## What this means for the application session

The five modules were inventoried to ask 「what question does each answer」. The answer
to the owner's question changes which of them can be BUILT ON:

    build on freely     ledger_structure · ledger_kinds · ledger_journey ·
                        ledger_walk_contrast — these already run on a swapped vocabulary
    do not build on yet ledger_trace — and the lineage walk is what `trace`, the graph
                        view, and the case-control console's upstream leg all stand on

**Not proposing a fix here.** Owner decides whether the walk's three questions become
declared roles or stay literal, and the config lane is another session's.

## Not measured

Row counts and predicate distribution in the live ledger (brief §6 step 3) — deferred
the moment the owner said the current ledger is nothing like production, since a
distribution measured on this box would describe a fixture, not the destination.

---

# 후속 — 「읽는 응용에 따라 다르게 해석」은 어디까지 이미 있나

**소유자 예시, 2026-08-20:** 「예를 들어 pin, register 같은 근본 데이터 어휘로 [된]
기록을 읽는 독자 애플리케이션에 따라 다르게 해석」

기존 프리미티브를 먼저 확인했다. **자리는 이미 있고, 소유자가 든 두 낱말은 그 자리의
양쪽에 하나씩 서 있다.** 그게 이 확인의 결론이다.

## `pin` — 해석이 «선언»으로 되어 있다 (자리 있음)

`ledger_trace.DEFAULT_RESOLVER_CONFIG` (210~256) 이 그 자리다:

    "pin_predicates":       ["pin"]              -> 등급 0 (사람의 핀)
    "confirmed_predicates": ["frame_confirmed"]  -> 등급 1
    "inference_derivations": [...]               -> 등급 3

성질을 하나씩 확인했다. 전부 소유자 요건과 같은 방향이다:

    선언 데이터다        `if` 사다리가 아니라 표다. 등급 판정 `claim_class`(436)는
                         `cfg["pin_predicates"]`를 읽지 이름을 안 쓴다
    읽는 시점이다        모듈 자신의 말: 「the class stays a READ-TIME declaration
                         rather than a permanent mark - which is what makes it
                         revisable at all」. 쓸 때 찍는 도장이 아니다
    운영자가 덮는다      `server/config/ledger_resolver.json` (선택 파일).
                         모르는 키는 조용히 무시가 아니라 `ResolverConfigError`
    이미 인자로 흐른다   `claim_class(claim, config=None)` · `resolve(..., config=None)`
                         · `trace(..., config=None)` — 네 소비자 모듈 전부
                         `cfg = config or load_resolver_config()` 꼴

🔴 **막힌 곳은 한 곳뿐이다: «몇 개»가 하나다.** `load_resolver_config()`는 인자가 없고,
`_config_cache`는 모듈 전역 하나이며, 파일도 하나다. 좌석은 파여 있고 배선도 끝났는데
**앉는 사람이 한 명이고, 어느 해석을 원하는지 말할 방법이 없다.**

즉 이 축에서 셋째 가치까지 남은 것은 「기계를 만드는 일」이 아니라
**「좌석에 이름을 붙이는 일」**이다. 소비자 서명은 이미 `config=` 를 받는다.

## `register` — 해석이 «코드»에 있다 (자리 없음)

같은 낱말인데 반대편이다. `register`의 뜻은 두 곳에서 코드가 정한다:

    1388   `registered = bool(at(cur_lot, "register"))`
           -> 「이 랏이 원장에 있다」. 이 불리언이 종료 사유를 `[root]`(뿌리다)와
              `[dead_end]`(원장이 이 랏의 혈통을 모른다)로 가른다
    1701   `WHERE predicate = 'register' AND subject_type = 'Lot'`
           -> `answer["lots"]`. 「랏이 몇 개 있나」의 정의가 이것이다
              (1535의 주석이 자인한다: 「The catalogue is `register`」)

「존재」와 「카탈로그」는 **해석**이지 원자가 말하는 것이 아니다. 그런데 이 둘은
`ledger_resolver.json`에 자리가 없다 — 등급 표는 «누구 말이 이기나»만 선언하고
«이 낱말이 무슨 역할인가»는 선언 대상이 아니기 때문이다.

## 그래서 축이 둘이고, 성숙도가 다르다

    축 A — 신뢰 등급 해석   「누구 말이 이기나」
           pin · frame_confirmed · 추론 파생
           선언 O · 읽는 시점 O · 인자로 흐름 O · 리더별 O   <- 여기만 비었다

    축 B — 역할 해석        「이 낱말이 무슨 일을 하나」
           register(존재/카탈로그) · derived_from(혈통) ·
           has_wafer(용기→멤버) · slot_map(위치 대응)
           선언 X · 읽는 시점 X · 인자 X · 리더별 X          <- 자리 자체가 없다

앞 절에서 잡은 걷기 하드코딩(1368~1493)은 **전부 축 B**다. 그리고 소유자의 셋째 가치는
두 축 모두를 요구한다 — 같은 엣지가 응용에 따라 다른 «역할»로 읽히려면 축 B에도
같은 모양의 좌석이 있어야 한다.

## 판정 대기 (제안하지 않음, 관문 ③)

축 A에 리더 이름을 붙이는 것과, 축 B에 좌석을 새로 파는 것은 크기가 다른 일이다.
어느 쪽부터인지는 소유자가 고른다.

---

# 확장 사다리 — 「완벽한 어휘는 없다」에 이 시스템은 얼마나 답하나

**소유자, 2026-08-20:**
「세상을 표현하기 위한 완벽한 어휘 집합이 존재할까? 그렇지 않다면 계속 확장 가능한
시스템이 필요해」 / 「온톨로지의 첫째 가치는 스키마 제약 없는 데이터베이스」 /
「하지만 현재 구조는 스키마 제약이 좀 큰듯」

**판정: 소유자가 맞다.** 다만 「크다」가 균일하지 않아서, 실행으로 층을 갈랐다.
아래는 전부 실측이다 — 임시 config 디렉터리에 실제로 선언해 보고 얻은 결과이며,
라이브 config는 건드리지 않았다.

## 늘어나는 것 — 코드 0줄로 확인됨

    주석·관측 술어 하나       ✅ config 선언만으로 끝
                              실측: `bonded_onto` 선언 -> 술어 13 -> 14,
                              `origin: "config"`로 병합, `emittable()` 통과(게이트가
                              원자를 받는다), 걷기 fetch 집합 `('bonded_onto',
                              'derived_from', 'has_wafer', 'register', 'slot_map')`
                              까지 도달. 재기동 불필요(`/admin/reload-configs`).

    신뢰 등급 해석            ✅ `ledger_resolver.json` 선언만으로 끝 (앞 절 축 A)

## 안 늘어나는 것 — 천장 넷, 깊이가 다르다

    ① 둘째 혈통 술어          ❌ 선언 시점에 거절. 실측한 거절문:
                                「a second traversable predicate is not executable by
                                 the walk (existing: ['derived_from'])」
                              🔴 조용하지 않다는 점은 좋다 — 질의 시점이 아니라 선언
                              시점에, 파일 전체를 반려한다. 이유도 적혀 있다(재귀
                              CTE가 값 하나에 조인하지 집합에 조인하지 않는다).
                              비용: 질의 한 개 재작성.

    ② 개체 타입                ❌ config 경로 자체가 없다. `ENTITY_TYPES`는 코드 전용이고
                              (`all_predicates()`에 대응하는 `all_entity_types()`가
                              없다), 거절문이 정책을 명시한다:
                                「개체 타입을 늘리는 것은 config가 아니라 어휘 판정입니다」
                              비용: 술어와 같은 병합 경로를 하나 더 내는 일.

    ③ 역할 해석 (축 B)         ❌ 좌석 자체가 없다. 앞 절 참조.

    ④ object_kind              ❌ DB CHECK.
                                `object_kind IN ('value','entity_ref','event_ref')`
                              비용: 마이그레이션.

## 🔴 그리고 가장 깊은 곳 — 낱말 하나가 테이블 정의 안에 있다

    CONSTRAINT ck_ledger_register_has_no_object
      CHECK ((predicate = 'register') = (object_kind IS NULL))

**술어 «이름»이 DB CHECK 제약에 박혀 있다.** `register`를 개명하거나 없애는 것은
선언 변경이 아니라 마이그레이션이다. 운영 어휘가 이 박스와 전혀 다르다는 전제에서,
이것이 이 시스템에서 가장 깊은 스키마 제약이다.

## 층을 갈라 말하면

    데이터 층    제약이 거의 없다. `object_payload`는 JSON이고 아무 모양이나 받는다.
                 원자의 골격(주어타입·주어키·술어·객체·시각)은 5칸짜리 «얇은» 스키마다.
                 소유자의 첫째 가치는 이 층에서는 이미 지켜지고 있다.

    어휘 층      제약이 크다. 술어 13 · 개체 6 · 천장 넷.
                 소유자가 느낀 「스키마 제약」은 여기다. 그리고 고칠 자리도 여기다.

**공정한 기록:** 위 제약들은 부주의가 아니라 «논증된» 것들이다(①은 질의 계획,
④는 설계가 못 박은 enum). 다만 그 논증들은 **어휘가 이 박스의 13개일 때** 쓰였다.
운영 어휘가 전혀 다르고 「완벽한 어휘 집합은 없다」가 전제라면, 그 논증들이 여전히
유효한지는 다시 판정할 사안이다 — 그리고 그 판정은 소유자 몫이다.

## 제안하지 않음 (관문 ③)

천장 넷은 비용이 서로 다르다 — ②는 이미 있는 병합 경로를 하나 더 내는 일,
①은 질의 하나, ④와 CHECK는 마이그레이션. 어디부터인지는 소유자가 고른다.

---

# 절대 안 변하는 어휘 — 「DB를 동작시키기 위한 부품」

**소유자, 2026-08-20:** 「일단 절대 변하지 않을 어휘들을 뽑아봐. 스키마가 아니라
기본적인 동작 부품인 것」 / 「db 동작 시키기 위한 어휘」 / 「db 저장 단에는 그런것만
남아야 해」

## 먼저 — 저장 단은 «이미» 그 규칙을 지키고 있다 (실측)

저장 단 전체를 어휘 이름으로 훑었다. 도메인 낱말이 몇 개 새어 들어갔는지가 규칙 위반의
척도이므로, 그것만 셌다.

    server/ledger/schema.py        기계 낱말 5 (전부 `register`) · 도메인 0 · 개체타입 0
    server/ledger/store.py         기계 낱말 3 (전부 `register`) · 도메인 0 · 개체타입 0
    server/ledger/gate.py          도메인 1 — 주석
    server/ledger/envelope.py      도메인 1 — 주석
    server/migrations/*  (7개)     전부 0

**저장 단이 아는 도메인 낱말은 0개다.** 코드에 실제로 박힌 것은 `register` 하나이고,
그건 기계 부품이므로 규칙 위반이 아니다.

📌 **앞 절 정정.** 앞에서 `ck_ledger_register_has_no_object`를 「가장 깊은 스키마 제약」
으로 적었는데, 소유자가 방금 세운 기준으로는 **적법한 제약**이다 — `register`는 세상의
낱말이 아니라 기계 부품이기 때문이다. 저장 단이 알아도 되는 딱 그런 것이다.

## 부품 목록 (전부 코드에서 뽑음, 기억 아님)

### A. 봉투 — 발화 하나의 골격 (14칸, `schema.py` CREATE)

    id                       이 발화의 신원 (uuid7 — 시간 정렬됨)
    subject_type             누가 (타입)
    subject_keys             누가 (신원)
    predicate                무엇을        <- 칸은 기계, 값은 세상
    object_kind              무엇에 «대해» (종류)
    object_payload           무엇에 «대해» (내용)  <- 여기가 스키마 없는 곳
    occurred_at              언제
    occurred_at_basis        그 시각을 무엇으로 정했나
    source_who               누가 말했나
    source_translator_ver    어느 «선언 세대»가 만들었나
    source_raw_ref           어느 원본 행에서 나왔나
    supersedes               무엇을 철회·대체하나
    source_event_id          어느 수신 사건에서
    source_event_state       그 수신이 어떤 상태인가

🔴 `predicate` 칸 자체는 부품이고, **그 안에 들어가는 값은 부품이 아니다.** 이 구분이
소유자 규칙의 실행 형태다.

### B. 기계 부품 «술어» — 3개 (`layer: canonical`, 실측)

    register    「이 주체가 존재한다」    개체 도입. 객체 없음(∅)이 이 낱말의 정의다
    pin         「사람이 못 박았다」      신뢰 최상단. 세상에 대한 진술이 아니라 «권위»
    same_as     「같은 개체다」           신원 병합. 예약(reserved) 상태

설계 문서는 `action:*`도 이 층에 예약해 두었으나 **어휘 표에는 아직 항목이 없다**
(실측: `vocabulary.py`에 `action:` 은 docstring 한 줄뿐).

### C. 객체 종류 — 3개 + ∅

    value · entity_ref · event_ref        (+ NULL = ∅, `register` 전용)

### D. 신뢰 사다리 — 4단 (`CLASS_NAMES`)

    0 pin · 1 confirmed · 2 observation · 3 inference

🔴 **칸은 기계, 입주자는 선언이다.** 1번 칸에 지금 `frame_confirmed`(도메인 낱말)가
앉아 있는데, 그건 `ledger_resolver.json`이 그렇게 «선언»해서다. 설계가 맞다.

### E. 해소 상태 — 4개 (`STATE_*`)

    resolved · contested · candidate · unresolvable

### F. 커버리지 상태 — 3개 (`COVERAGE_STATES`)

    absent · empty · ready

## 🔴 그리고 «빠진 부품» — 이게 이 질문의 진짜 수확이다

부품 목록을 뽑아 보니 **기계가 하는 일 중에 부품 이름이 없는 것이 넷 있다.**
없어서 안 도는 게 아니라, **도메인 낱말이 대신 그 자리에 앉아 있다.**

    기계의 기능              지금 그 자리에 앉은 것        본래 있어야 할 부품
    ─────────────────────    ─────────────────────────    ────────────────────
    혈통 간선을 «따라간다»    derived_from  (ontology)     「traversal edge」
    용기에서 «멤버를 꺼낸다»   has_wafer     (ontology)     「container -> member」
    «위치를 대응»시킨다        slot_map      (ontology)     「position mapping」
    주체가 «존재하는지» 본다   register      (canonical)    ✅ 이건 제대로 있다

앞의 셋은 `layer: ontology`로 선언돼 있다 — 즉 **시스템 스스로 「이건 세상의 낱말이다」
라고 표시해 놓고, 기계가 그 낱말을 이름으로 직접 부른다.** 걷기 코드가
`at(cur_lot, "derived_from")`이라고 쓰는 순간, 세상의 낱말 하나가 기계 부품으로
징발된다. 그리고 가드는 「탐색 가능한 술어는 정확히 하나」로 그 징발을 «고정»한다.

**앞 절의 「축 B — 역할 해석 좌석 없음」이 이것과 같은 사실이다.** 소유자의 표현으로
바꾸면: **부품 목록에 세 칸이 비어 있고, 그 칸을 세상의 낱말이 메우고 있다.**
`register`만 제대로 된 부품을 갖고 있고, 그래서 `register`만 저장 단에 있어도 괜찮다.

## 판정 대기 (제안 아님, 관문 ③)

빠진 부품 셋에 이름을 주는 것 — 즉 술어 선언이 「나는 혈통 간선 역할이다」를 말하게
하고 걷기가 역할로 묻게 하는 것 — 이 축 B의 내용이다. 크기와 착수 여부는 소유자 판정.

---

# 탐색 관점의 근본 어휘 — 기계가 걷기 위해 «실제로» 묻는 것

**소유자, 2026-08-20:** 「혈통이 뭔데」 / 「혈통이 본질적인 것인가」 /
「기계의 관점에서, 탐색 관점에서 근본 어휘 뽑아봐」

**선행 판정: 「혈통」은 근본 어휘가 아니다.** 선언 전체에 계보·부모·혈통이라는 개념은
없다. `derived_from`에 대해 기계가 아는 것은 `traversable: True` + `direction:
subject_to_object` 뿐이고, 그건 **「이 간선은 재귀해도 된다」**는 말이지 「이것이 혈통이다」
가 아니다. 「혈통」은 그 연산을 반도체 공장에서 부르는 이름이다.

🔴 **결정적 증거 (실측):** `register` · `has_wafer` · `slot_map` 셋이 **전부
`traversable: False`**다. 선언에 그 셋을 가를 정보가 없고, 기계는 이름으로만 구별한다.
역할이 선언에 없다 = 애초에 부품이 아니었다.

## 근본 어휘 — 다섯 묶음 (전부 도는 코드에서 뽑음)

### ① 노드 — 걷기가 서는 자리

    개체 타입 (subject_type)      어떤 종류의 것인가
    개체 키   (subject_keys)      그중 어느 것인가

기계가 노드에 대해 알아야 할 것은 이 둘이 전부다. 「랏」·「웨이퍼」는 이 두 칸에 들어가는
«값»이다.

### ② 간선 — 걷기가 건너는 것

    간선 = object_kind 가 entity_ref 인 원자

    출발    그 원자의 subject 신원
    도착    그 원자의 object 신원

**「간선」의 정의에 술어 이름이 안 들어간다.** 객체가 개체면 간선이고, 값이면 주석이다.
이 한 줄이 탐색의 전부다.

### ③ 간선의 성질 — 선언이 말해야 하는 것 (이미 있음)

    traversable   3-state   재귀함 / 도달만 하고 통과 금지 / 아예 안 봄
    direction               어느 쪽 끝이 출발인가

이 둘은 이미 술어 선언에 있고, `walk_predicates()`·`traversable_predicates()`가 읽는다.
**탐색 어휘 중 유일하게 이미 제대로 선언된 부품이다.**

### ④ 멈춤 어휘 — 6개 (실측, `ledger_trace.py`)

    unknown_subject   이 노드에 원자가 0건이다
    root              나가는 간선이 없다 (그리고 이 노드의 존재는 확인됨)
    dead_end          나가는 간선도 없고 존재도 모른다
    broken            간선은 있는데 도착지를 못 준다
    cycle             이미 지난 노드로 되돌아왔다
    depth_cap         깊이 한도에 걸렸다

🔴 **여섯 개 전부 순수 기계 어휘다. 도메인 낱말이 하나도 없다.** 이 프로젝트가 이미
기계 어휘를 뽑을 줄 안다는 증거다 — 간선에만 적용을 안 했을 뿐.

### ⑤ 고르기 — 한 자리에 후보가 여럿일 때

    등급 4단   pin · confirmed · observation · inference
               (칸은 기계, 입주자는 `ledger_resolver.json` 선언)
    상태 4개   resolved · contested · candidate · unresolvable
    근거       basis{kind,name} · source_who · source_translator_ver ·
               source_raw_ref · n(몇 명이 말했나) · rank

🔴 **이것도 전부 기계 어휘다.** ④와 ⑤가 깨끗한 것이 이 문서의 가장 희망적인 실측이다.

## 🔴 도메인이 새어 들어간 자리 — 탐색 축에 셋

### 누수 1 — 재귀 질의가 노드 타입을 박아 놨다

`_TRACE_CTE` / `_REACH_ONLY_CTE` (957 · 988):

    ON e.subject_type = 'Lot'

걷기는 「개체에서 개체로」인데, 질의는 「랏에서 랏으로」다.

### 누수 2 — 키 이름도 박혀 있다. 그런데 «선언에 이미 있다»

    e.subject_keys->>'lot'
    COALESCE(e.object_payload->'keys'->>'lot', e.object_payload->>'lot')

🔴 **`ENTITY_TYPES`가 타입마다 `keys`를 이미 선언한다** — `Lot: ["lot"]` ·
`Wafer: ["wafer"]` · `Die: ["wafer","x","y"]`. 기계가 키 이름을 «물어볼 곳»이 이미
있는데 질의가 대신 적어 놨다. 여기는 없는 부품을 만드는 게 아니라 **있는 선언을 안 읽는
자리**다.

### 누수 3 — 도달만 하는 간선의 역할이 이름으로 구별된다

`has_wafer`와 `slot_map`은 선언상 구별되지 않는다(둘 다 `traversable: False`).
걷기는 이름으로 구별한다.

## 그래서 남는 질문 (소유자 판정 대기)

「도달만 하는 간선」을 기계가 «구별해야 하는가»가 갈림길이다.

    구별 안 한다   부품이 ①~⑤로 끝난다. 걷기는 개체 간선을 다 따라가고,
                   무슨 뜻인지는 «읽는 응용»이 정한다 (셋째 가치와 정확히 같은 방향)
    구별 한다      「간선 역할」이라는 부품이 하나 더 필요하고, 그건 선언에 없다

앞의 것이 소유자가 세운 세 가치와 모두 맞는다. 다만 이건 **판정 사항이지 제안이 아니다.**

---

# 🔴 정정 — 저장 단 도메인 낱말은 0건이 아니라 1건이다

**소유자 지적, 2026-08-20:** 「지금 has_wafer 이런게 저장되는거 아니야?」

## 먼저 갈라야 하는 것

`has_wafer`는 **`predicate` 칸의 값으로 저장된다.** 그건 위반이 아니다 — 원장은 도메인
사실을 기록하는 물건이다. 「원장이 본질 어휘만 안다」는 **원장 코드가 그 낱말을 아는지**
의 문제이고, `has_wafer`에 대한 CHECK도 인덱스도 분기도 없다. **칸은 부품, 값은 데이터.**

## 그런데 앞 절의 「도메인 0건」은 틀렸다

    CREATE INDEX idx_ledger_subject_lot ON {LEDGER_TABLE}
      ((subject_keys->>'lot'), predicate)          -- schema.py:228

`'lot'`은 `Lot` 타입의 키 이름이고 세상의 낱말이다. **저장 단이 아는 도메인 낱말은 1개다.**

🔴 **계측기 결함이었다.** 스캔의 단어 목록에 `Lot`(대문자 개체 타입)은 있었는데
`'lot'`(소문자 «키 이름»)이 없었다. 개체 타입의 `keys` 값들은 어휘 이름이 아니라서
목록을 만들 때 빠졌고, 그래서 **스캔이 자기를 반증할 것을 먼저 지웠다**
(`the-filter-hides-what-refutes-it`, 같은 실수 재발). 목록에 `ENTITY_TYPES[*]["keys"]`의
값 전부(lot · wafer · product · equipment · recipe · rev · x · y)를 넣었어야 했다.

## 그리고 이 인덱스는 장식이 아니다

주석이 스스로 말한다: 이 인덱스가 없으면 **홉마다 모든 파티션을 훑는다**(파티션은
`occurred_at` 기준이라 걷기 질의는 가지치기가 안 된다). 즉 걷기 성능이 이 인덱스에
걸려 있다.

## 하나의 뿌리

    재귀 질의     ON e.subject_type = 'Lot'  ·  subject_keys->>'lot'   (957 · 988)
    물리 인덱스   ((subject_keys->>'lot'), predicate)                  (schema.py:228)

앞 절에서 「누수 1」과 「누수 2」로 따로 적은 것이 실은 **같은 사실 하나**이고, 그것이
DB 물리 층까지 내려가 있다. **걷기가 랏 전용이라 인덱스도 랏 전용이다.**

## 정정된 층별 그림

    파티션 키      도메인 0   — `occurred_at` 기준, 술어와 무관
    CHECK 제약     도메인 0   — `register` 뿐이고 그건 기계 부품
    인덱스         도메인 1   — `lot`  <- 여기
    게이트         도메인 0   — 서명으로만 검사, 이름을 모름
    개체 타입 표   도메인 6   — Lot · Wafer · Product · Equipment · Recipe · Die

---

# 넷째 가치 — 「마이그레이션 free인 시스템」으로 채점하면

**소유자, 2026-08-20:** 「온톨로지 넷째, 마이그레이션 free인 시스템」

이 가치는 앞의 셋과 성격이 다르다. **앞의 셋을 채점하는 자다.** 세상이 바뀔 때 DDL이
필요하면 그건 「스키마 제약 없음」도 「편하게 쌓기」도 아니다.

## 채점표 — 세상이 바뀌는 일마다 드는 비용 (실측 기반)

    술어 하나 추가              ✅ 선언만. 실측 확인 (`bonded_onto`, 코드 0줄)
    해석(신뢰 등급) 바꾸기      ✅ 선언만 (`ledger_resolver.json`)
    월이 바뀜                   ✅ 파티션 자동 생성 (부모에 선언 → 신규 파티션에 캐스케이드)
    개체 타입 추가 (안 걷는 것)  ⚠️ 코드 수정 + 배포. 선언 검증기가 없어서 config 불가
    개체 타입 추가 (걷는 것)     🔴 코드 + **새 인덱스** = 마이그레이션
    객체 종류 추가              🔴 CHECK 제약 = 마이그레이션
    봉투 칸 추가                🔴 ALTER TABLE = 마이그레이션

## 🔴 그리고 진짜 덫은 인덱스다 — 그런데 설계가 이미 알고 있다

걷기 질의는 이렇게 묻는다:

    subject_keys->>'lot' = :lot

**이 «모양»이 키마다 인덱스를 하나씩 요구한다.** 웨이퍼를 걷고 싶으면
`subject_keys->>'wafer'`가 필요하고, 그건 `idx_ledger_subject_wafer`라는 새 인덱스,
즉 마이그레이션이다. **개체 타입 하나 늘 때마다 DDL 한 번.** 둘째 가치(여러 사람이 편하게
쌓기)와 곱하면 사람마다·개념마다 마이그레이션이 된다.

🔴 **그런데 `schema.py`의 제거된 인덱스 목록(190~209)이 대안을 이미 적어 놨다:**

    idx_ledger_subject_gin  USING gin (subject_keys jsonb_path_ops)   38.3 B/atom
      "Serves `subject_keys @> '{...}'`. Nothing asks that today; the walk asks
       `subject_keys->>'lot' = ...`, which a GIN cannot answer. ADD IT WHEN A CONSUMER
       NEEDS TO LOOK A SUBJECT UP BY A KEY OTHER THAN `lot`."

포함(containment) 질의 `subject_keys @> '{"lot":"A12"}'`는 **키 이름을 안 가린다.**
GIN 인덱스 «하나»가 모든 키를 영원히 덮는다. 개체 타입을 늘려도 DDL이 0이다.

**즉 마이그레이션을 강요하는 것은 스키마가 아니라 «질의의 모양»이다.**
`->>'키'`는 키마다 인덱스 하나, `@> {...}`는 통틀어 인덱스 하나.

## ⚠️ 재지 않은 것 — 주장하지 않는다

GIN 포함 질의가 재귀 CTE에서 **충분히 빠른지는 측정된 적이 없다.** 등치 btree와 GIN은
계획이 다르고, 이 프로젝트가 유일하게 성능을 논증해 둔 질의가 바로 그 걷기다.
「GIN으로 바꾸면 된다」는 **가설이지 진단이 아니며**, 값은 실측으로 치러야 한다
(`a-hypothesis-is-not-a-diagnosis`).

확실한 것만 적으면: 지금 모양은 개체 타입당 인덱스 하나를 «구조적으로» 요구하고,
대안의 모양은 그러지 않는다. 그 대안의 가격은 아직 모른다.

## 네 가치를 한 줄로 묶으면

    ① 스키마 제약 없는 DB      데이터 층은 이미 달성. 어휘 층에 천장 넷
    ② 여러 사람이 편하게       술어는 달성. 개체 타입은 검증기가 없어 미달
    ③ 읽는 응용마다 다른 해석   신뢰 등급 축은 좌석 하나. 역할 축은 좌석 없음
    ④ 마이그레이션 free        ①②③이 어긋나는 «자리»가 전부 여기서 DDL로 청구된다

**넷째가 앞의 셋의 «계산서»다.** 어휘 층 천장 넷이 곧 마이그레이션 넷이다.

## 판정 대기 (제안 아님)

질의 모양을 바꾸는 것(키별 → 포함)은 「인덱스 하나 바꾸기」가 아니라 걷기 질의의
재작성이고, 성능 실측이 선행해야 한다. 착수 여부·순서는 소유자 판정.

---

# 재저장이 필요한가 — 셋째·넷째 가치가 만나는 자리

**소유자, 2026-08-20:** 「만약 특정 관계를 has_wafer에서 다른 것으로 해석하기 위해
다시 저장이 필요한 것 아닌지?」

**답: 해석이 «이름»에 매달려 있으면 필요하다. «선언»에 있으면 필요 없다. 그리고 이
시스템 안에 두 방식이 «둘 다» 있다.**

## 재저장의 실제 값 — 덮어쓰기가 아니라 두 배

`predicate`도 `source_translator_ver`도 **둘 다 `DEDUPE_COLUMNS`에 있다**
(`schema.py:58`). 선언을 고치고 재실행하면 옛 원자를 지우지 않고 옆에 새로 쓴다.
보드에 실측 선례가 있다(`eb1ae8b`):

    커서 리셋 재실행은 878을 1756으로 만든다

소유자가 판정한 append 의미론대로다. 그래서 재저장의 대가는 「고쳐 쓰기」가 아니라
**두 세대 공존 + 해소기 중재**다.

## 같은 시스템의 두 방식

    frame_confirmed -> 등급 1     해석이 `ledger_resolver.json` 선언에 있다
                                  뜻을 바꾸려면: 파일 한 줄. 쓰는 원자 0건
    has_wafer -> 용기→멤버        해석이 걷기 «코드»에 있다 (이름으로 호출)
                                  뜻을 바꾸려면: 이름 변경 + 재번역 + 코드 수정

`frame_confirmed`가 등급 1 칸에 앉은 것은 원자를 다시 써서가 아니라 선언 때문이다.
등급 2로 내리는 데 이미 쌓인 원자는 한 개도 안 건드린다.

## 🔴 축 B의 정확한 정체 — 「구조 정리」가 아니라 「재저장 방지 장치」

앞 절들에서 축 B(역할 선언)를 구조 문제로 적었는데, **정확히는 재저장을 막는 장치다.**
역할이 선언에 있으면 **이름을 바꿀 이유 자체가 사라진다** — 원자는 계속 `has_wafer`라고
말하고, 읽는 응용이 「나에겐 이것이 X 역할」이라고 선언한다. 결과:

    옛 해석으로 읽던 응용   그대로 돈다        <- 셋째 가치
    쓰는 원자               0건                <- 넷째 가치

## 경계 — 재저장이 «불가피한» 경우

    같은 사실, 다른 뜻      선언.   재저장 0
    다른 사실 (틀린 대상·틀린 값)   재번역. 두 세대 공존

`has_wafer`를 다르게 해석하는 것은 **앞쪽**이다. 원자가 말한 사실(이 랏의 이 슬롯에
이 웨이퍼)은 그대로고, 걷기가 그것을 무슨 역할로 쓰느냐만 달라진다.

---

# 🔴🔴 정정 경고 — 이 문서의 어휘·천장 관련 결론은 «구 시스템»을 잰 것이다 (2026-08-20)

소유자 지적으로 발견: 라이브는 **`setup_version: 3`**이고, 개체 타입은
`config/ontology/ledger_config.json`의 **`entities` 블록**에서 선언되며
(`DTJob@1`은 `vocabulary.py`의 6개에 없다), 그 **선언 검증기가 이미 있다**
(`setup_bundle._validate_entities`, `setup_registry._compile_entities`).

**따라서 아래 결론들은 근거가 소실됐다:**

    「개체 타입은 config로 못 늘린다」        틀림 — `entities` 블록에 한 줄
    「개체 타입 선언 검증기가 없다」           틀림 — `_validate_entities`
    「세 요구가 같은 천장 하나에 막혔다」       근거 소실
    「술어는 config로 늘어난다」(bonded_onto)  구 시스템에서만 참

**원인:** 라이브 config를 열어 최상위 키(`setup_version`·`vocabulary`·`entities`·
`packs`·`sources`)를 출력해 놓고 **`sources`만 읽었다.** 그리고 v3 대응물을 찾을 때
`vocabulary.py` 안에서만 이름을 찾았다 — 다른 파일에 다른 이름으로 있었다.

v3 기준 재측정이 진행 중이다. 그때까지 이 문서의 어휘·천장 관련 문장을 인용하지 말 것.
(하드코딩 스캔 자체 — `ledger_trace`가 술어 이름을 리터럴로 부른다는 사실 — 은
소스 코드를 직접 잰 것이므로 별도로 재확인 대상이다.)

---

# 🔴 v3 기준 재측정 — 온톨로지 설정 총괄 답신 + 내 검증 (2026-08-20)

## ① 다리는 «있다» — 버전 축은 안전 (검증 완료)

    server/ledger/roleframe.py:987   _runtime_id(versioned_id) -> versioned_id.rsplit("@",1)[0]
    적용 지점 :1137(객체 타입) · :1167(주어 타입) · :1169(술어)

    선언 register@1 · DTJob@1   ->   원자 register · DTJob

**직접 확인했다.** 걷기의 무버전 리터럴은 v3가 쓴 원자와 «맞는다».
내가 「걷기가 0건을 받는다」고 단정하지 않은 것이 옳았다.

## ② 병존이 현재 상태다 — 은퇴 중이 아니다 (총괄 답신)

구 `ledger/vocabulary.py`를 읽는 곳이 열 군데 이상: `chain_ingestion_worker` ·
`ledger/config.py` · `ledger_admin` · `ledger_catalog` · `ledger_explorer` ·
`ledger_journey` · `ledger_selection` · `enrichment_config` · `config_resolve_report`.

**어느 쪽으로 통일할지는 «판정된 적이 없다».** 응용 기획은 「둘 다 있다」를 전제한다.

## 🔴 ③ 그래서 진짜 벽은 «버전»이 아니라 «이름»이다

다리가 없애는 것은 버전뿐이다. 그리고 두 어휘는 **서로 다른 파일**을 본다:

    v3 선언        server/config/ontology/ledger_config.json      (라이브, 관리 중)
    구 어휘 확장    server/config/ledger_vocabulary.json          🔴 «존재하지 않음»

걷기의 fetch 집합은 구 `walk_predicates()`에서 나오고, 그것은
`코드 PREDICATES + 없는 파일`이다. **따라서 v3가 새 술어를 선언해도 걷기는 그것을
«아예 모른다».** 버전을 떼어 이름이 맞아도, 애초에 목록에 없다.

    v3가 `bonded_onto@1` 선언  ->  원자 `bonded_onto` 적재됨
    걷기의 fetch 집합          ->  ('derived_from','has_wafer','register','slot_map')
    결과                       ->  그 원자는 걷기에 존재하지 않는 것과 같다

**이것이 §5 「경로 특징이 막혀 있다」의 정확한 기전이다.** 총괄 지적대로 `_runtime_id`는
이 벽을 낮추지 않는다.

## ④ 읽는 쪽이 v3 개체 타입을 만나면 — 실측 (내가 추가로 잼)

    rollup_subject_types('DTJob')      -> ('DTJob',)      통과. 예외 없음
    check_subject_keys('DTJob', ...)   -> "subject type 'DTJob' is not a declared entity type"
    ledger_trace                       -> `subject_type == "Lot"` 필터라 «안 보인다»
    ledger_structure                   -> 선언 절반에 없으므로 «undeclared» 엣지로 «보인다»

🔴 **넷 중 하나만 설계대로다.** `ledger_structure`가 `undeclared`로 드러내는 것은
그 모듈이 존재하는 이유의 절반이고, 제대로 돈다. 나머지는 조용하다.

## 총괄이 준 전제 둘 (내 문서에 반영)

    원장이 안 흐르는 이유    커서가 «전역 지문»에 묶여 모든 소스가 막혔다.
                            소유자가 「소스별 지문」으로 판정, 구현 대기열.
                            🔴 갈래 C의 선행조건이 이것이다
    운영 원장 규모           «수백만» 행 (소유자 확인). 이 박스 수치는 픽스처다

## 살아남은 결론 · 죽은 결론

    살아남음   `ledger_trace`가 술어 이름을 리터럴로 부른다 (소스 직접 측정)
               걷기가 `Lot`에 묶여 있다
               인덱스에 `lot` 키 이름이 있다
               축 B(간선 역할 선언)가 없다  ← v3에서 «더» 아프다
    죽음       「개체 타입은 config로 못 늘린다」
               「개체 타입 선언 검증기가 없다」
               「세 요구가 같은 천장 하나에 막혔다」
