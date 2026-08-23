# 물리 온톨로지 세팅 — WF 공정·RCP 원장, 그리고 불량 모델링→액션 시나리오

> **Status:** 🟠 부분 착지 — **§2·§3은 착지했고(2026-08-14) 나머지는 여전히 제안 v0**
> (제품 소유자 지시 2026-08-13 밤: "wf 단위 공정 프로세스 및 rcp도 원장 만들어") | **Owner:** 온톨로지 포크
> **Last-verified:** 2026-08-14
> 배경: 시스템이 물류(랏·분할)와 관측(계측·보이드)까지만 있고 **물리가 말하는
> 대상 — 구조·공정 조건·메커니즘 — 이 없다**는 소유자 진단. 관측 축은
> [MI_LEDGER_SCHEMA_PROPOSAL](MI_LEDGER_SCHEMA_PROPOSAL.md), 판정 근거는
> [CANONICAL_LEDGER_DESIGN](CANONICAL_LEDGER_DESIGN.md).
>
> ---
>
> ### 🔴 착지 현황 (2026-08-14) — **이 문서는 절마다 상태가 다르다**
>
> | 절 | 상태 | 무엇이 |
> |---|---|---|
> | §1 M1 구조(`BondLine`) | 🟡 **제안** | **착지하지 않았다.** 어휘에 `BondLine`이 없고 구성형 개체는 여전히 `Die` 하나다 |
> | §1 M2 물리량 사전 | 🟡 **제안** | **착지하지 않았다.** 물리량↔구조 종류의 타입 시스템은 코드에 없다 |
> | **§2 WF 공정 원장** | ✅ **착지** | `processed_with` v0 등재 — 아래 §2의 착지 블록 |
> | §2-bis 칩 이동(`transferred`) | ✅ **착지** | 🔴 **[2026-08-15 정정 — 이 행은 「제안」이라 적고 있었고 그것이 낡았다]** `transferred`는 `vocabulary.PREDICATES`에 **있고**(2026-08-15 실측), `dt_log`가 세 번째 문법 `kind: "transfer"`로 선언돼 번역된다. 선언 방법은 [ONTOLOGY_LEDGER_SETUP §3.3](../guide/ONTOLOGY_LEDGER_SETUP.md). ⚠️ **예약 `consumed`는 여전히 없다** |
> | **§3 RCP 원장** | ✅ **착지** | `Recipe`(발급형, `rev`가 키) + `has_param` 등재 — 아래 §3의 착지 블록 |
> | §4 메커니즘 그래프 | ✅ **착지** | 🔴 **[2026-08-15 정정 — 이 행의 아래 서술은 전부 낡았다]** `server/config/mechanism_models.json`이 **라이브·`.sample` 둘 다 실재**하고 소비자가 **셋**이다(3관문 랭킹의 기전 관문 `server/mechanism_gate.py` · `/structure`의 기전 층 · 🔴 **[2026-08-23 `a7b107cb`] 증거 서브그래프**가 이 선언에서 **물리량 노드를 합성**한다 — 원장은 그것을 위해 한 행도 안 읽고, **모델 이름이 노드 정체의 일부**다. [backend §2 `/subgraph`](./backend.md)). 선언 방법과 🔴 **「`models`라는 블록은 없다」**는 실측은 [ONTOLOGY_LEDGER_SETUP §6.1](../guide/ONTOLOGY_LEDGER_SETUP.md). 아래는 그 착지 이전의 기록이다: ~~모델 선언 본문·`validity`는 코드에 없다. 🔴 **[2026-08-14 2차 실측 — 이제 이것을 «재는 도구»가 있다]** `GET /api/ledger/structure`가 기전 층을 `state: "absent"` · `reason: "no_declaration_file"`로 답한다. 부재는 **다섯**이다: config 파일 · 파이썬 dict · 로더 · 라우트 · 어휘의 `Model` 개체 타입 — 그리고 **소비자 0**. 🔴 **엔드포인트는 아래 §4의 제안을 데이터로 «옮겨 적지 않는다»**(그 순간 제안이 선언으로 오독된다). 이음새는 `server/config/mechanism_models.json`이고 **`.sample`은 «일부러» 안 실었다** — 이 저장소에서 `.sample`은 「출하된 선언」이라 제안을 그 자리에 두는 것이 같은 오독이다. **이 행이 ✅로 바뀌는 조건은 문서 수정이 아니라 «그 파일이 놓이고 읽는 것이 생기는 것»이다**~~ — **그 조건이 `f52628f`로 충족됐다.** |
> | §5 시나리오 3종 | 🟡 **제안** | S1~S3의 **재료**(공정 원자·개정 diff·분모)는 이제 있지만 **폴드·액션 산출은 없다** |
> | §5-bis 액션 노드 | 🟡 **제안** | 어휘에 `Action`도 `applies_to`/`based_on`/`released_by`도 **없다** |
> | **§6 가상 소스 결선** | ✅ **착지** | `server/scripts/seed_syn_process_ledger.py` — 정답지와 `--prove` 포함 |
>
> 🔴 **현행 서술의 정본은 이 문서가 아니다** — 어휘 계약은 [spec/LEDGER_TECHNICAL_SPEC §3.7](../spec/LEDGER_TECHNICAL_SPEC.md),
> **「무엇을 어디에 선언하는가」는 [guide/ONTOLOGY_LEDGER_SETUP](../guide/ONTOLOGY_LEDGER_SETUP.md)**(2026-08-15 신설 — 🔴 **이 문서의 어느 절이 오늘 실물이고 어느 절이 제안인지도 그 문서 §8이 «실측으로» 답한다**),
> 번역기 코드 절차는 [guide/LEDGER_GUIDE §3](../guide/LEDGER_GUIDE.md), 저장은 [architecture/data_model §1.1-ter](./data_model.md).
> **이 문서는 계속 설계이고, 착지 블록은 「제안의 무엇이 실제로 무엇이 됐는가」만 적는다.**

## 1. 물리 온톨로지 4계층 (raw함의 처방)

| 층                     | 없던 것                        | 세우는 것                                                                                                                                           |
| ---------------------- | ------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| **M1 구조**            | 물리가 사는 «장소»             | `BondLine(Package, gate)` 등 **구성형 개체** (Die처럼 등록 이벤트 없음). 보이드는 좌표가 아니라 **본드라인 안**에 생기고, BLT는 본드라인의 속성이다 |
| **M2 물리량 사전**     | 양이 «무엇의» 속성인지         | 물리량마다 차원 +**소속 구조 종류** (`BLT → BondLine의 두께`). 모델 입력의 타입 시스템                                                              |
| **M3 공정 조건**       | **원인이 사는 곳 — 최대 구멍** | `processed_with` 술어 개시 (아래 §2)                                                                                                                |
| **M4 메커니즘 그래프** | 인과의 표현                    | 모델 선언의 본문 (아래 §4) — 식 없이 방향만으로도 가동                                                                                              |

## 2. WF 단위 공정 프로세스 원장 어휘

```
(Wafer W, processed_with,
 {step, eqp, recipe: {recipe_id, rev}, chamber?,
  params_actual: {temp?, pressure?, time?, vacuum?, …}},   # 실제 조건 — 있으면
 occurred_at, source{who, raw_ref})
```

- **subject = Wafer** (등재 개체). 패키지 문맥의 공정(본딩)은 base 웨이퍼 신원으로
  건다 — void와 같은 축, 같은 이유.
- **step은 닫힌 값 집합** (추가 전용, E40/E10 대응은 후속). **두 과(科)를 처음부터
  염두에 둔다 (제품 소유자, 2026-08-13)**: ① **반도체 기본 공정** — CMP·ETCH·
  PHOTO·확산·증착·임플란트…, ② **패키징 특수 공정** — DIE_SAWING·DT·BONDING·
  몰딩·그라인딩…. 한 웨이퍼의 `processed_with` 이력이 fab에서 패키징까지 한 축으로
  이어지는 것이 목적이고, v0 초기값은 실소스가 실증하는 것부터 등재하되(현재 dt·
  bonding이 첫 후보) 과의 구분(`step_family: fab|packaging`)을 시그니처에 둔다 —
  메커니즘 그래프의 validity가 과 단위로 걸리는 일이 많아서다(예: 보이드 모델은
  packaging 과에만).
- **`params_actual`은 관측(2류)** — 장비 로그가 발화한 실제 조건. 없으면 이 필드가
  비고, 레시피 설정값(아래)이 3류 폴백으로 선다. **실측>설정의 서열이 자동으로
  성립하는 구조** — 클래스 체계가 공짜로 사준다.
- `processed_with`는 설계가 예약해 둔 술어 — 필요가 실증된 지금 v0 등재 (observed와
  같은 경로).

### ✅ §2 착지 (2026-08-14) — 제안과 실물의 차이

```python
"processed_with": {"status": "active", "since": 2, "layer": "ontology",
                   "subject": ["Wafer"],
                   "object": {"kind": "value",
                              "required": ["step", "step_family", "eqp", "recipe"]}}
```

| 제안이 말한 것 | 실제로 착지한 것 |
|---|---|
| subject = Wafer | **그대로** |
| `step_family: fab\|packaging`을 시그니처에 | **그대로 — 그리고 `required`다**(빠지면 원자가 거절된다) |
| `step`은 **닫힌 값 집합** | 🔴 **닫히지 «않았다».** `step`은 존재가 강제되는 payload 필드일 뿐이고, **어떤 문자열이든 통과한다.** 값 집합은 오늘 생성기(`seed_syn_process_ledger.STEPS`) 안에만 있고 **아무것도 그것을 강제하지 않는다** — 「추가 전용 닫힌 집합」은 여전히 **판정 대기**다 |
| `chamber?` | ✅ **payload 필드로 착지했다 — 선언된 «개체»가 아니다.** `required`에도 없어 **없어도 된다.** 설비 하위 신원을 개체로 세우는 것은 하지 않았다 |
| `params_actual`은 관측(2류), 없으면 레시피 설정값이 3류 폴백 | ✅ **그대로이고, 그것이 이 착지의 가장 큰 값이다** — 🔴 **랭킹 코드가 «한 줄도» 쓰이지 않았다.** `params_setpoint` 원자가 payload에 `inferred: true`를 달아 계급 3이 되고, `claim_rank_key`가 동점 처리를 계급 «안»에 봉인하므로 **설정값이 더 새롭고 더 높은 우선순위 소스에서 와도 실측을 이길 수 없다.** 계약과 뮤턴트 검증은 [spec §4.1-bis](../spec/LEDGER_TECHNICAL_SPEC.md) |
| 목적어 형태 (제안은 명시하지 않음) | **`value` 하나**다. `entity_ref` 셋으로 쪼개면 **어느 것도 홀로 참이 아니다**(원자성 검사 ①) — 「W가 B-3에서 처리됐다」는 홀로는 어느 레시피인지 말하지 않는다. **런 하나 = 원자 하나** |

## 2-bis. 칩 이동 사건 — `transferred` (제품 소유자 일반화, 2026-08-14)

DT 적재·본딩 안착을 단계별로 다른 주장으로 만들지 않는다. **소유자의 일반화**:
"chip의 transfer event를 걸어서 추적되게" — 칩의 모든 이동이 **하나의 사건 술어**다.

```
(Wafer W, transferred,
 {die: {frame, x, y},                    # 어느 다이가 (§5-2: 다이 지정은 payload)
  from: {type, keys, position},          # 어디서  (wafer 격자 | dt_lot slot | …)
  to:   {type, keys, position},          # 어디로  (dt_lot slot | package gate | …)
  qty?},                                 # 묶음 이동이면
 occurred_at, source{who, raw_ref})
```

- **subject는 웨이퍼** — 다이의 영구 신원 뿌리(다이 = 웨이퍼 × 격자, 구성형)라서.
  이동해도 주어는 안 변한다 — 변하는 것은 위치이고 위치는 사건의 내용이다.
- **흐름 전체가 이 술어 하나로**: 웨이퍼→DT 솎음 = transfer, DT→본딩 = transfer,
  미래의 재작업·반송도 같은 문법. 랏 수준의 lot_event(분할·병합)와 정확히 평행한
  **칩 수준 사건 축**이다.
- **파생이 전부 세기(count)가 된다**: 솎음 = 이동 사건의 존재/부재 · **잔량** =
  용기별 유입 − 유출 · 수율 = 도착 대비 출발. "사용 칩 잔량"(소유자의 원래 목표)이
  폴드 하나로.
- 예약 술어 `consumed`는 이 일반화가 흡수한다 — 소비 = 밖으로의 transfer. 별도
  등재는 「이동 아닌 소멸」(스크랩 등)이 실증될 때만.
- 추적 방향: 보이드 → (to가 그 gate인 transfer) → DT slot → (to가 그 slot인
  transfer) → 코어 웨이퍼 격자 — **네 다리가 transfer 사슬 걷기 하나로 통일된다.**
- **DT n회도 자동으로 추적된다 (소유자 요구, 2026-08-14).** 보행이 단계 이름이
  아니라 **위치 연속성**(사건 N의 `to` = 사건 N+1의 `from`) + 시간순으로 잇기
  때문에, DT→DT 재이송·복수 DT 경유·재작업 반송 등 임의 길이의 사슬이 같은 걷기로
  풀린다. 같은 용기를 두 번 지나도 사건마다 id·시각이 달라 갈래가 안 섞인다.
  **단계 수를 아는 코드가 어디에도 없어야 한다** — "DT는 한 번"을 가정한 조인이
  보이면 그 자리가 결함이다.

## 3. RCP(레시피) 원장 어휘

레시피는 **발급형 개체**다 (Lot·Wafer처럼 register 대상 — 3주차 어휘 계획에 이미
`Recipe`가 있었다).

```
(Recipe {recipe_id, rev}, register)                        # 개정마다 새 subject
(Recipe {recipe_id, rev}, has_param, {param, value, unit}) # 설정값 — 파라미터당 1원자
```

- **개정(rev)이 subject 키에 들어간다** — 레시피 수정은 개체 수정이 아니라 **새
  개정의 등록**이다. 원장의 append-only와 정합하고, 개정 전후 비교가 두 subject의
  주장 대조로 끝난다.
- `has_param`은 레시피의 **설정값(선언)**이고, §2의 `params_actual`은 그 실행의
  **실측**이다. 설정 대 실측의 괴리 자체가 질의 가능한 사실이 된다 (센서 드리프트·
  장비 이상의 신호).
- 소스: 레시피 관리 대장/파일 → 번역기 한 장. 가상 소스 단계에서는 생성기가 발급.

### ✅ §3 착지 (2026-08-14) — 제안과 실물의 차이

```python
"Recipe":    {"class": "issued", "keys": ["recipe", "rev"], "semi_ref": "E40 recipe"},
"has_param": {"status": "active", "since": 2, "layer": "ontology",
              "subject": ["Recipe"],
              "object": {"kind": "value", "required": ["param", "value", "unit"]}}
```

| 제안이 말한 것 | 실제로 착지한 것 |
|---|---|
| 레시피는 발급형 개체 | **그대로** — `register`·`pin`·`same_as`의 subject 목록 **셋 다**에 들어갔다(개체를 더하는 것은 그 셋을 함께 손보는 일이다) |
| **개정(rev)이 subject 키에** | **그대로**, 그리고 그것이 append-only의 요구다 — `rev`가 속성이면 rev5를 적는 유일한 방법이 rev4의 원자를 supersede하는 것이고 **rev4로 실제로 돌았던 웨이퍼의 근거가 도달 불가능**해진다 |
| `has_param`은 파라미터당 1원자 | **그대로.** 개정 diff가 **집합 차**가 되고, 시트가 잘못 옮겨 적힌 것이 밝혀지면 **파라미터 하나만** supersede된다 |
| 설정값의 타입 | 🔴 **`value`가 `0`·`False`여도 정당하다** — 서명 검사는 **존재**이지 진리값이 아니다. 진리값으로 썼으면 **가장 기록할 가치가 있는 설정값 둘**을 거절했을 것이다(빈 문자열은 여전히 거절) |
| 소스: 레시피 대장 → 번역기 한 장 | ⏳ **실 번역기는 없다.** 오늘 유일한 발급자는 생성기(§6)이고, 그것은 `ledger_config.json`이 아니라 **자기 안에** 파생·subject 타입을 선언한다([LEDGER_GUIDE §3-bis](../guide/LEDGER_GUIDE.md)) |

## 4. 메커니즘 그래프 (M4) — 모델 선언의 본문

> 🟡 **제안이다. 아래 블록은 «착지한 선언이 아니다»** — 코드가 열 수 있는 선언이 0이고 소비자도 0이다(헤더 착지표의 이 행에 실측 다섯이 적혀 있다).
> 🔴 **이 코드 펜스를 그대로 «파일로 옮기는 것»이 이 절을 착지시키는 절차가 아니다** — 이음새는 `server/config/mechanism_models.json`이고,
> 놓기 전에 「누가 이것을 읽는가」가 먼저 답돼야 한다(오늘의 답은 **아무도**). 부재는 [`GET /api/ledger/structure`](../spec/LEDGER_TECHNICAL_SPEC.md)가
> 화면에 이름 대어 말하고 있으므로, **이 절을 인용해 「기전 그래프가 있다」고 쓰지 말 것.**

```jsonc
"void_formation_v0": {
  "version": "0.1-qualitative",
  "nodes":  ["pressure", "temp", "BLT", "warpage", "void"],
  "edges": [
    {"from": "pressure", "to": "BLT",  "dir": "-", "form": null},   // 식 미상 — 방향만
    {"from": "BLT",      "to": "void", "dir": "+", "form": null},
    {"from": "warpage",  "to": "void", "dir": "+", "form": null},
    {"from": "temp",     "to": "void", "dir": "u", "form": null}    // 비단조 표시
  ],
  "validity": {"step": "bonding"}
}
```

식이 서면 `form`에 꽂는다 — **구조는 그대로, 간선 내용만 진화**. 점수는 투영에서
접고, 지속 결론·액션 근거만 원장에 (§5-bis 규칙 그대로).

## 5. 사용 시나리오 3종 — 불량 모델링 → 액션 산출

### S1. 회귀 조사: 보이드 → 저압 본딩 → 격리 hold

1. SAT가 패키지 P의 gate3에 보이드 관측 (`observed`, finding_kind: void)
2. 추적: gate3의 다이 → base 웨이퍼 W → **W의 본딩 run** (`processed_with`:
   eqp B-3, R-12 rev4, `params_actual.pressure` 하위 10%)
3. 형제 교집합: 이번 주 보이드 6건 중 5건이 (B-3, R-12r4) 공유 + 같은 gate들의
   MI BLT 상위 꼬리 — 메커니즘 그래프의 `압력↓→BLT↑→void↑` 경로와 **정합**
4. **액션**: `(B-3 × R-12r4 × 해당 기간의 미출하 패키지, action:hold, 근거{모델 v0 경로, 투영 세대, 입력 원자 raw_refs})`
5. 소급 의심: 훗날 압력 센서 주장이 supersede되면 **이 근거를 쓴 hold가 자동으로
   의심 목록에 뜬다** — 설계의 액션 스키마가 사주는 것.

### S2. 레시피 개정 판정: rev5 전후 비교 → 롤백/승인

1. R-12 **rev5** 등록 (`register` + `has_param` diff: rev4 대비 temp +5)
2. 폴드: 같은 eqp·같은 제품에서 rev4/rev5 본딩분의 **보이드 발생률 비교** —
   분모는 `inspection_run`(스캔이 있었다)이 제공, "검사 안 함"과 "깨끗함"이
   안 섞인다
3. rev5 발생률 ×2.3 (분모와 함께) + 교란 점검(장비·제품 구성 동일 확인)
4. **액션**: `(R-12 rev5, action:recipe_review, 근거{비교 폴드, 분모, 기간})` —
   메커니즘 그래프의 temp 간선은 이 결과로 지지/기각이 갱신된다 (모델도 판정받는다)

### S3. 선행 예방: MI 조기 경보 → 우선 검사 워크리스트

1. 본딩 직후 MI: 웨이퍼 W의 BLT 하위 10% + warpage 상위 꼬리 (`measured`)
2. 메커니즘 그래프 **순방향** 보행: W를 쓴 gate들의 보이드 위험 ↑ — **SAT 스캔
   전에** 예측이 선다
3. **액션**: `(해당 패키지 목록, action:priority_inspection, 근거{...})` —
   SAT 우선순위 워크리스트가 화면에 뜬다 (조사 화면이 아니라 예방 화면)
4. **효과 회귀 (OODA)**: SAT 결과(`observed` void 또는 깨끗한 run)가 예측과
   대조되어 **모델의 적중/빗나감이 세어진다** — 가상 소스의 정답지 검증과 같은
   구조가 실운영의 모델 채점이 된다.

## 5-bis. 액션 노드 (제품 소유자, 2026-08-13 밤: "액션 노드가 있어야겠네")

**액션은 «기본 액션»과 «메타 액션»으로 분기한다 (제품 소유자, 2026-08-14).**
메타 액션은 온톨로지나 원장 **자체에 대한** 보강·수정을 유발하는 "자기 자신에 대한
액션"이다 — 대상이 세상(자재·레시피)이 아니라 **지식 체계**(수집 간극·결측·관례
선언·모델·어휘)인 액션. 구조는 기본 액션과 완전히 동일하고(같은 Action 노드, 같은
4원자), 갈리는 것은 `applies_to`가 가리키는 곳뿐이다. OODA가 **이중 루프**가 된다:
기본 액션은 세상을 고치고, 메타 액션은 **세상을 보는 눈을 고친다.**

**메타 시나리오 1 — 설명 실패 → 표적 수집 + 수집 대기 모드 (제품 소유자 원안)**
보이드가 발생했으나 **관측된 모든 프로세스·MI에 특이사항 없음** — 현재 증거로는
모델이 설명하지 못한다. 이때 PHYSICS 모델이 거꾸로 일한다: 메커니즘 그래프에서
**아직 관측되지 않은 노드**(이 gate의 실압력 미기록·warpage 미계측·OM 미관찰)를
골라 **어느 추가 MI·직접 관측이 가설을 판별하는지 산출** → 그 목록으로
`(Action, kind: collect_request, applies_to → 계측 대상×물리량, based_on → 설명
실패의 폴드)` 발급 → **조사 건은 「수집 대기 모드」**로 열린 채 남는다. 요구한
관측이 원자로 도착하면 액션이 닫히고 분석이 자동 재개 — 모델이 자기 맹점을 스스로
수집 요구로 바꾸는 능동 관측이다.

**메타 시나리오 2 — 결측치 워크리스트 (제품 소유자 원안)**
시스템이 **자기가 모르는 것의 목록**을 상시 산출한다: 확정 없는 dt_lot, 프레임 없는
맵, 물리량 사전에 있는데 이 자재엔 측정이 없는 값, base 신원 없는 본딩 행 —
결측마다 「채우면 무엇이 풀리는지」(막힌 추적 수·대기 중인 조사)를 근거로 단
워크리스트. 각 행이 곧 메타 액션(`collect_request`/`confirm_request`) 후보이고,
사람이 지우는 만큼 온톨로지의 눈이 밝아진다 — **enrich 화면(E1)의 일반화이자,
V1(최소 공수 교정)의 «무엇부터 고칠지»에 대한 답.** 우선순위는 「푸는 것의 수」로
정렬 — 결측 하나가 조사 셋을 막고 있으면 그게 맨 위다.

**메타 시나리오 3 — 관례·모델의 재판정**
본딩 관측이 `#slot_preserving`을 반복해서 이기면(contested 상승) →
`(Action, kind: revise_convention, applies_to → 선언:split.slot_pairing)` →
config 뒤집고 재번역. S2의 폴드가 temp 간선을 기각하면 →
`(Action, kind: model_revision, applies_to → Model:void_formation_v0)` → v0.2 —
**지식 체계가 판정받고 고쳐지는 과정 자체가 그래프에 남는다.**

어휘 함의: 메타 액션의 `applies_to`는 시스템 개체(Source·선언·Model·결측 슬롯)를
가리켜야 하므로 그들도 가벼운 신원을 갖는다 — config 선언 키+버전이 이미 그
신원이고 등록 이벤트는 불요(구성형 취급). 지금 대기열에 산문으로 사는 수집 질의
3건(본딩 base 신원·실기하 선언·MI 실물)이 메타 액션 노드의 첫 실물 후보다.

### 액션 분류 — 2축 (제품 소유자, 2026-08-14: "RND 주요 액션은 수집·결측 확보·DOE, hold는 양산 관점")

축이 둘이다. **목적 축**(이 액션이 무엇을 위한 것인가): R&D = **지식 획득**(불확실성을
줄인다) 대 양산 = **위험 처분**(제품·고객을 보호한다). **대상 축**(무엇을 건드리나):
세상(자재·공정) 대 지식 체계(기본/메타의 그 분기).

| | 세상 대상 (기본) | 지식 체계 대상 (메타) |
|---|---|---|
| **R&D 목적 — 이 시스템의 주류** | `measure_request` 추가 계측 · `observe_request` OM 직접 관측 · **`doe_request` DOE 생성** | `collect_request` 소스/컬럼 수집 요구 · **`fill_missing` 결측치 확보** (메타 시나리오 2의 워크리스트) · `revise_convention` · `model_revision` · 어휘 등재 요청 |
| **양산 목적 — 부차** | `hold` · 격리 · 재검 · 출하중지 · `recipe_review`/rollback | (드묾 — 판정 기준 개정 정도) |

**이 시스템은 R&D 현장이므로(SSOT §1) 액션 어휘의 v0 주류는 왼쪽 위가 아니라
«지식 획득» 행 전체다** — G3 지시서의 v0 목록(hold·priority_inspection·
recipe_review)은 양산 관점에 치우쳐 있었고, 이 분류로 정정한다: v0 =
`collect_request`·`fill_missing`·`measure_request`·`doe_request` (지식 획득) +
`hold`·`priority_inspection` (처분, 되돌릴 수 있는 것만). kind 등록부가
`{purpose: learn|contain, target: world|system}` 시그니처를 갖는다.

**`doe_request`는 R&D 액션의 완성형이라 따로 적는다.** S1이 찾는 것은 상관(공유
요인)이지 인과가 아니다 — 인과는 실험이 세운다. DOE 액션:
`(Action, kind: doe_request, applies_to → 검증 대상 가설(메커니즘 간선), based_on
→ 상관 증거, payload: {요인·수준 매트릭스, 할당 자재 후보})`. 실행되면 그 run들의
`processed_with`(조건이 곧 실험 설계)와 후속 MI·SAT 관측이 돌아와 폴드가 가설을
채점한다 — **관찰→가설→실험→판정의 R&D 루프 전체가 그래프에 남는다.** 기존 계획
UI의 DOE 축(legend·STACK 구간)이 이 액션의 실행 표면 후보다.

**액션은 발급형 «개체»다** — 대상 행에 붙는 꼬리표가 아니라 자기 신원을 가진 노드.
근거: S1의 hold는 패키지 50개에 걸릴 수 있는데, 꼬리표 50개는 신원이 없어서
한꺼번에 해제할 수도, 참조할 수도("hold #123"), 근거를 공유시킬 수도 없다.

```
(Action {action_id}, register, ∅)                  # 발급 — kind는 subject 등재 시 결정
(Action A, applies_to, entity_ref → Package P)     # 대상마다 1원자
(Action A, based_on,  event_ref → 근거 원자들       # 증거로의 간선 — object kind
                       + {투영 세대, 모델 id·버전})  #   event_ref가 이걸 위해 있었다
(Action A, released_by, event_ref → 해제 사건)      # 수명주기도 추가 전용
```

그래프 뷰에서 액션 노드는 **대상 ↔ 증거를 잇는 허브**로 그려진다 — OODA 폐곡선이
위상으로 보인다. 그리고 소급 의심이 **그래프 질의가 된다**: 어떤 원자가 supersede
되면 `based_on` 간선을 역주행해 닿는 액션들이 의심 목록이다 — S1의 "센서 주장이
뒤집히면 hold가 자동으로 뜬다"의 구현이 조인이 아니라 간선 보행 하나.

어휘 추가: `Action`(발급형) + `applies_to`·`based_on`·`released_by` v0.
3주차의 `action:hold` 표기는 이 구조의 축약 표기로 재해석한다.

## 6. 가상 소스와의 결선

가상 MI 생성기 지시에 편입: **본딩 processed_with(실측 조건 포함)와 Recipe
발급(rev 2개, 파라미터 diff 포함)도 생성**하고, 정답지의 인과를 §4의 정성 그래프와
같은 모양으로 심는다 — S1·S2·S3가 정답지를 찾아내는지가 곧 수락 검증이 된다.

### ✅ §6 착지 (2026-08-14) — `server/scripts/seed_syn_process_ledger.py`

- **같은 문으로 들어간다** — `gate.building_molecule` 스코프 안에서 `gate.screen_molecule`을 지나 `LedgerStore.write_batch`로 쓴다.
  🔴 **픽스처가 게이트를 우회하면 「게이트가 진짜 데이터를 거절하는가」를 그 픽스처로는 영원히 증명할 수 없다.**
- **선언을 `ledger_config.json`에 «넣지 않았다»** — 그 검증기는 `columns` 일곱을 무조건 요구하고 생성기에는 그 컬럼이 하나도 없다.
  빈 값으로 채우는 대신 파생 넷(`first_sight`·`eqp_log`·`recipe_setpoint`·`recipe_book`)과 subject 타입 둘을 **모듈 상수로** 선언하고 게이트에 그대로 넘긴다
  → 절차의 정본은 [LEDGER_GUIDE §3-bis](../guide/LEDGER_GUIDE.md).
- **정답지가 있고 `--prove`가 양방향으로 단언한다** — 심은 요인은 **농축**되고, **미끼(decoy)는 농축되지 않아야** 한다.
  🔴 **미끼는 패딩이 아니라 시험이다**: 보이드 여섯 건의 공통 요인을 찾는 화면은 언제나 무언가를 찾아낸다(전부 BONDING을 지났고, 전부 같은 레시피였다) —
  그리고 그 전부가 **스캔했는데 멀쩡했던 패키지에도 참**이다. 교집합 화면은 둘을 가르지 못하고 대조 화면은 가른다.
- ⚠️ **두 종류를 «반대 방향»으로 지었다** — `void`는 이미 디스크에 있던 결과에서 요인을 배정했고(add-only라 다시 쓸 수 없다),
  `delam`은 요인에서 결과를 생성했다. 검출기가 **각 구성 방식 하나씩**에 채점되도록 한 것이고, 어느 한 경로만 본 적이 없게 된다.
- **걷어내는 술어**는 [LEDGER_GUIDE §4.7](../guide/LEDGER_GUIDE.md)이 소유한다(원장·커서·RDB 관측·셀 레이어 **네 층**).

## 7. 판정 대기

✅ **`processed_with`·`Recipe` v0 등재는 2026-08-14에 «내려졌다»**(§2·§3 착지 블록) — 남은 것:

- 🟡 **`BondLine` v0 등재** — 미착지. M1 구조가 없으면 「보이드는 좌표가 아니라 본드라인 «안»에 생긴다」가 여전히 산문이다.
- 🔴 **step 닫힌 집합의 초기값** — **가장 시급하다.** `step`은 지금 **아무 문자열이나 받는** payload 필드이고,
  값 집합은 생성기 안에만 있어 **오타 난 step이 새 step으로 조용히 태어난다.** 이 문서가 「닫힌 값 집합」이라 적은 것과 코드가 다르다.
- 🟡 params 개념명 사전(M2), E40/E10 대응 조사, §5-bis 액션 어휘(`Action`·`applies_to`·`based_on`·`released_by`) — 전부 미착지.
