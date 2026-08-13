# 물리 온톨로지 세팅 — WF 공정·RCP 원장, 그리고 불량 모델링→액션 시나리오

> **Status:** 🟡 제안 v0 (제품 소유자 지시 2026-08-13 밤: "wf 단위 공정 프로세스 및
> rcp도 원장 만들어") | **Owner:** 온톨로지 포크
> 배경: 시스템이 물류(랏·분할)와 관측(계측·보이드)까지만 있고 **물리가 말하는
> 대상 — 구조·공정 조건·메커니즘 — 이 없다**는 소유자 진단. 관측 축은
> [MI_LEDGER_SCHEMA_PROPOSAL](MI_LEDGER_SCHEMA_PROPOSAL.md), 판정 근거는
> [CANONICAL_LEDGER_DESIGN](CANONICAL_LEDGER_DESIGN.md).

## 1. 물리 온톨로지 4계층 (raw함의 처방)

| 층 | 없던 것 | 세우는 것 |
|---|---|---|
| **M1 구조** | 물리가 사는 «장소» | `BondLine(Package, gate)` 등 **구성형 개체** (Die처럼 등록 이벤트 없음). 보이드는 좌표가 아니라 **본드라인 안**에 생기고, BLT는 본드라인의 속성이다 |
| **M2 물리량 사전** | 양이 «무엇의» 속성인지 | 물리량마다 차원 + **소속 구조 종류** (`BLT → BondLine의 두께`). 모델 입력의 타입 시스템 |
| **M3 공정 조건** | **원인이 사는 곳 — 최대 구멍** | `processed_with` 술어 개시 (아래 §2) |
| **M4 메커니즘 그래프** | 인과의 표현 | 모델 선언의 본문 (아래 §4) — 식 없이 방향만으로도 가동 |

## 2. WF 단위 공정 프로세스 원장 어휘

```
(Wafer W, processed_with,
 {step, eqp, recipe: {recipe_id, rev}, chamber?,
  params_actual: {temp?, pressure?, time?, vacuum?, …}},   # 실제 조건 — 있으면
 occurred_at, source{who, raw_ref})
```

- **subject = Wafer** (등재 개체). 패키지 문맥의 공정(본딩)은 base 웨이퍼 신원으로
  건다 — void와 같은 축, 같은 이유.
- **step은 닫힌 값 집합** (bonding·dt·grinding·…, 추가 전용, E40/E10 대응은 후속).
- **`params_actual`은 관측(2류)** — 장비 로그가 발화한 실제 조건. 없으면 이 필드가
  비고, 레시피 설정값(아래)이 3류 폴백으로 선다. **실측>설정의 서열이 자동으로
  성립하는 구조** — 클래스 체계가 공짜로 사준다.
- `processed_with`는 설계가 예약해 둔 술어 — 필요가 실증된 지금 v0 등재 (observed와
  같은 경로).

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

## 4. 메커니즘 그래프 (M4) — 모델 선언의 본문

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
4. **액션**: `(B-3 × R-12r4 × 해당 기간의 미출하 패키지, action:hold,
   근거{모델 v0 경로, 투영 세대, 입력 원자 raw_refs})`
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

## 6. 가상 소스와의 결선

가상 MI 생성기 지시에 편입: **본딩 processed_with(실측 조건 포함)와 Recipe
발급(rev 2개, 파라미터 diff 포함)도 생성**하고, 정답지의 인과를 §4의 정성 그래프와
같은 모양으로 심는다 — S1·S2·S3가 정답지를 찾아내는지가 곧 수락 검증이 된다.

## 7. 판정 대기

`processed_with`·`Recipe`·`BondLine` v0 등재 (이 문서로 필요 실증 — 어휘 성장 규율
충족), step 닫힌 집합 초기값, params 개념명 사전, E40/E10 대응 조사.
