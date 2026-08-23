# 지시서 — 전파가 설 땅을 잇고, 질의 하나를 얹는다

> # 🔴 착수 상태 (2026-08-23 10:3x) — 이 절이 본문보다 «우선»한다
>
> 총괄 판정 `a256ce50`: **공사 1 → 3 착수 승인 · 공사 2 보류.**
>
> ```
> ✔  공사 1   mechanism_gate.py + config/mechanism_models.json — ledger 의존 0
> ⛔ 공사 2   보류.  «두 번» 낡았다 —
>            읽으려던 선언(`ledger/vocabulary.py` 의 traversable)은 v1 계통이고,
>            라이브 v5 어휘엔 traversable·direction 이 «없고» observed 술어도 «없다»
>            (v5 술어 6: derived_from · has_netdie · has_wafer · register · slot_map · transfer)
> ✔  공사 3   ledger_subgraph.subgraph() 확장.  공사 1 → 3 의존은 그대로
> ```
>
> ### 울타리 — «이름»이 아니라 «목록»이다 (총괄이 이 목록으로 갱신)
> ```
> ✖ 얼음  A  ledger_trace.py · ledger_trace_router.py · ledger_admin.py · ledger/config.py
> ✖ 얼음  C  ledger_explorer.py · ledger_structure.py · ledger_journey.py · ledger_lots.py
>            (이름은 글롭 밖인데 해결기·어휘·계보 술어를 «가져간다»)
> ✔ 가능  B  ledger_subgraph · ledger_catalog · ledger_composition
>            ledger_selection · ledger_siblings · ledger_trends
>            (`ledger_trace` 에서 `_fetch`·`relation_exists` «둘만» 쓴다)
> ```
> **A·C 에서 버그를 보면 «적고 지나간다».** 고치지 않는다.
> 수락 D 가 `/api/ledger/trace` 를 부르는 것은 «읽기»이므로 괜찮다 — 고치지는 말 것.
>
> ### 수락을 «무엇 위에서» 받나 — 오늘 실측으로 바뀐 것
> ```
> 전사(transfer) 원자   원장에 «0».  ledger_translator_cursor 에 transfer_event 행 «없음»
>                      (시험 실행은 쓰지 않는다 — 설계대로. 백필은 «총괄 소관»)
> 씨앗 이름 공간        SYN-XFER-CORE-W01~W10 · SYN-XFER-D01~D10
>                      원장에 등록된 Wafer/DTJob 과 겹침 «0»
>
> 그래서 수락은 lot_event 재료 위에서 받는다:
>   has_wafer 907 · derived_from 40 · slot_map 226 · register 546
> ```


> **작성:** 응용 기획 세션 (2026-08-21) · **수신:** 구현자
> **유효 결론 한 장:** `task/APPLICATION_VALID_NOW.md` — 착수 전 이것부터 읽는다
> **근거:** `ontology_application_algorithm.md` §15~23 · `ontology_arbitrary_question.md`

---

## 0. 🔴 착수 전 관문 (`CLAUDE.md` 상설)

    ① 최소 수정   바뀌는 층만. 주변 인터페이스·호출자·이름은 그대로
    ② 단순 로직   지금 필요 없는 일반화·추상·설정 축을 만들지 않는다
    ③ 안 시킨 것 금지   가드·테스트·헬퍼·「나중을 위한」 훅 전부 포함

**이 지시서에도 걸린다.** 아래 「하지 말 것」(§5)을 지시의 일부로 읽는다.

---

## 1. 도착지 — 한 문장

**`walk { start: 노드 ids ±, collect: 노드 타입 }` 하나로 응용 여섯이 «설정만» 으로
나온다.** 새 응용이 새 코드가 아니게 되는 것이 이 라운드의 전부다.

---

## 2. 바뀌는 층 / 그대로인 것

    바뀐다     server/ledger_subgraph.py        투영이 «무엇을 노드로 내는가» + 씨앗·산출
    그대로     server/ledger_trace.py           «건드리지 않는다». 전파는 걷기 위가 아니라
                                               투영 위에 선다
    그대로     원장 스키마 · 어휘 · 설정 형식      다른 레인. 원자도 선언도 안 늘린다
    그대로     ledger_trace_router.py 의 기존 호출  시그니처를 «깨지 않는다»

🔴 **`ledger_trace` 의 Lot 고정·술어 이름 하드코딩은 이 라운드의 범위가 아니다.**
알고 있고, 고칠 필요가 없다(§근거 §8). 손대지 말 것.

---

## 3. 공사 셋

### 공사 1 — 투영이 «기전·바인딩» 엣지를 낸다

지금 `ledger_subgraph.subgraph()` 는 원자에서 `Event · Claim · Entity · Value` 를
합성한다. **같은 방식으로 물리량 노드를 하나 더 합성한다.**

    입력   server/config/mechanism_models.json   (이미 라이브. `mechanism_gate.load()` 가 읽는다)
    낼 것  Value 노드 --(binding)--> Quantity 노드
           Quantity  --(mechanism)--> Quantity        방향은 선언의 `dir` 그대로

    노드 id  기존 `*_node_id` 규약을 따른다 — 불투명·타입 있음·«씨앗으로 되먹임 가능»

⚠️ **원자를 쓰지 않는다. 어휘를 늘리지 않는다.** 물리량은 선언에서 «합성» 되는 노드이지
원장에 앉는 개체가 아니다. (`Model` 개체 타입은 «필요 없다» — 그건 구조뷰의 요구다.)

### 공사 2 — `observed` 를 «이름» 이 아니라 «선언» 으로 판별한다

> ⛔ **보류 (총괄 `a256ce50`).** 아래 근거의 `traversable` 축이 v5 어휘에 «없다».
> 착수하지 말 것. 본문은 ③ 뒤 재검토용으로 남긴다.

`ledger_subgraph.py` 가 `observed` 를 이름으로 14곳에서 부른다. **그 규칙은 이미 어휘에
선언돼 있다:**

    ledger/vocabulary.py   observed 의 `traversable` 이 `None`
                           = 「걷기가 아예 안 가져온다. 범위 지정 요청에만」

    시정   `predicate == "observed"` -> 「이 술어의 `traversable` 이 `None` 인가」
           같은 자리에 `processed_with`·`measured` 도 이름으로 불린다(속성 추출).
           그 둘은 «부류가 다르다» — 아래 참조

🔴 **`processed_with`·`measured` 는 이번에 «건드리지 않는다».** 그 둘은 「무엇을 걸을까」가
아니라 「이 payload 에서 무엇을 뽑을까」이고, 그 판별을 무엇이 대신할지는 «아직 정해지지
않았다». 이름으로 남겨 두고 주석으로 표시만 한다. 지어내지 말 것.

### 공사 3 — `walk { start ±, collect }`

`subgraph()` 가 이미 `seed_id` · `hops` · `direction` 을 받는다. **두 가지를 넓힌다.**

    start     하나의 `seed_id` -> «부호 있는 노드 집합»
              { positive: [ids], negative: [ids] }
              단일 id 도 계속 받는다 (기존 호출자 안 깨짐)

    collect   산출을 «노드 타입 하나» 로 좁힌다. 없으면 지금처럼 전부

**부호의 뜻 (§근거 §S2):**

    +        관측됐다
    −        «봤는데 안 났다» / 대조군
    씨앗 없음  미검사        <- «−» 와 다른 상태다. 뭉개지 말 것

**전파 규칙 — 두 가지만 지킨다:**

    첫 홉(씨앗 -> 요인)   차수로 «나누지 않는다»    <- 나누면 차이 0 인 요인이 −0.06 이 된다
    그다음                차수로 나눈다
    감쇠 상수             «없다». damping factor 를 기본값으로 끌고 오지 말 것

**산출 (§근거 §21):**

    최상위 집합       1등이 하나가 아니다. «지배당하지 않는 것 전부»
    비교 불가 표시     「정도가 아니라 종류가 다르다」
    근거 경로         홉마다 원자 ref — 기존 evidence 구조 그대로
    숫자를 «내지 않는다»   순위와 최상위 집합만. 소유자 판정

---

## 4. 🔴 수락 단언 — 이것으로 합격을 판정한다

    A  선언 진단이 «인스턴스 층» 에서 돈다
       `task/ontology_declaration_diagnosis_run.md` 가 선언만으로 낸 답을,
       표시한 웨이퍼에 대해 낸다

    B  응용 둘이 «코드 0줄» 로 갈린다
       collect: Quantity  ->  원인 후보
       collect: Entity    ->  혈통 공통 조상
       **분기가 하나라도 필요하면 공사 3 이 미완이다**

    C  기전 선언에 노드를 하나 더해도 코드가 «안» 바뀐다
       (`mechanism_models.json` 에 노드/엣지 추가 -> 화면에 나타남)

    D  기존 `/api/ledger/trace` · subgraph 호출이 «그대로 돈다»
       시그니처를 안 깬 것의 확인

---

## 5. 하지 말 것

    ✗ `ledger_trace.py` 수정               범위 밖. 전파는 투영 위에 선다
    ✗ 원장 스키마·어휘·설정 형식 변경        다른 레인
    ✗ `Model`·`Action` 개체 타입 신설       이번에 필요 없다
    ✗ damping factor 기본값 도입            §근거 §10·§17 — 인공물이다
    ✗ 홉·개수 «임계값» 도입                 순위가 그 자리를 대신한다
    ✗ 확률·퍼센트 산출                      온톨로지는 숫자를 못 낸다 (소유자 판정)
    ✗ `processed_with`·`measured` 이름 판별 «수정»   판별 대체가 미정. 주석만
    ✗ 테스트 전면 추가                      고친 자리의 것만 (`CLAUDE.md` 상설)

---

## 6. 순서 제안

    1  공사 1 (기전 엣지 합성)          -> 수락 C 로 확인
    2  공사 3 (walk start±/collect)     -> 수락 A·B·D
    ⛔ 공사 2 는 «이번 라운드에 없다» (보류)

**1 이 없으면 3 의 `collect: Quantity` 가 빈 답을 낸다.** 순서를 바꾸지 말 것.

---

## 7. ✅ 착수 판정 — 받았다 (`a256ce50`, 2026-08-23 10:3x)

**공사 1 → 3 승인.** 아래는 판정 «전»의 질문이고 답이 났으므로 기록으로만 남긴다.


**이 지시서를 구현자 대기열에 넣어도 되는가** — `server/ledger_subgraph.py` 는
서버 코드이고, 지금 총괄 라인이 `lot_event` 라운드를 돌고 있다. **파일이 겹치지 않으나
같은 원장을 읽는다.** 총괄 판정 후 착수.

(지시서를 «쓰는 것»은 응용 기획 세션의 일이다 — 브리핑 §0. 착수 승인만 총괄 소관.)
