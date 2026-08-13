# MI 계측이력 — 원장 스키마 제안 v0

> **Status:** 🟡 제안 (소스 실물 미확인 — 확정은 실물 대조 후) | **Owner:** 온톨로지 포크
> 앵커 목표(브리프 §10.4-bis, 제품 소유자 2026-08-13)의 MI 축.
> [DEFECT_SCHEMA_PROPOSAL](DEFECT_SCHEMA_PROPOSAL.md)(void)과 같은 지위의 문서이고,
> 같은 골격을 재사용한다. 판정 근거는 [CANONICAL_LEDGER_DESIGN](CANONICAL_LEDGER_DESIGN.md).

## 0. 한 줄

**점(point)은 소스 테이블에, 주장(claim)은 원장에.** MI의 원시 계측점 수천 개를
원장에 붓지 않는다 — 원장은 주장의 기록이지 텔레메트리 저장소가 아니다(설계 §5
텔레메트리 경계). 보이드 해석이 필요로 하는 것은 "이 자재의 BLT가 얼마였나"이지
점 하나하나가 아니고, 점이 필요해지면 raw_ref로 소스에 내려간다.

## 1. 소스 계층 — void의 2테이블 골격을 «재사용»한다

- **분모 = 기존 `inspection_run` 재사용.** 그 테이블의 키가 이미
  `(method, base_wafer_id, base_x, base_y, stack_gate, observed_at)`로 **method를 키
  재료로** 갖고 있다 — MI는 새 분모 테이블이 아니라 `method='MI-<종류>'`인 행이다.
  "스캔이 있었다"와 "계측이 있었다"는 같은 문장이다. (분모 없이 관측만 있으면
  「측정 안 함」과 「정상이라 특이값 없음」이 같은 부재가 된다 — void와 같은 이유.)
- **관측 = `mi_obs` 신설** (실물 확인 후 컬럼 확정). 방향은 void_obs와 동일:
  한 행 = 한 run이 본 한 측정값. `(run_uid, metric, site)` 키.
  값·단위는 행에 실린다(단위가 조인 너머에만 있는 숫자는 그리드에서 단위 없이
  보인다 — void §3과 같은 규칙). **판정값(pass/fail)은 저장하지 않는다** — 임계는
  레시피 파라미터고, 저장된 판정은 재심 불가(void의 「등급 금지」와 동일).

## 2. 원장 어휘 — 웨이퍼 내 계측에 «본질적으로 존재하는 것»만 (제품 소유자 지시)

웨이퍼 안에서 무언가를 잴 때 세상에 실재하는 것은 넷뿐이다. 나머지(잡 id·파일명·
장비 코드·측정자)는 전부 방언이거나 출처다.

| 본질 | 내용 | 봉투에서의 자리 |
|---|---|---|
| **① 어디** | 어느 웨이퍼의, 어느 좌표계(frame)의, 어느 위치 (x, y) — 그리고 선택적으로 그 자리의 **구조**(bond_line·film·TSV…) | subject = Wafer, payload의 `{frame, x, y, structure?}` (§5-2: 프레임은 subject 금지) |
| **② 무엇을** | **물리량** — 두께·폭·면적·정렬오차·휨… 단위와 차원은 물리량의 시그니처에 속한다 (µm 없는 「두께」는 없다) | payload의 `quantity` — 어휘 등재 대상, 방언은 번역으로 소멸 |
| **③ 얼마** | 값 (+ 요약이면 stat·n) | payload의 `{value, unit, stat?, n?}` |
| **④ 언제·어떻게** | 계측 행위 자체 — 시각·방법·레시피. **사실이 아니라 사실의 출처다** | `occurred_at` + `source{who, raw_ref=run_uid}` |

```
(Wafer W, measured, {quantity, value, unit, frame, x, y, structure?, stat?, n?},
 occurred_at, source{raw_ref: run_uid})
```

봉투 7필드가 이 넷을 새 구조 없이 그대로 받는다는 것 — 그게 봉투를 그렇게 설계한
이유다. **①이 subject+위치 payload, ②③이 object, ④가 occurred_at+source.**

물리량(②) 규율 둘: 단위는 물리량 시그니처의 일부라 단위 없는 값은 게이트가 거절
(void의 `DEFAULT_UNIT: None`과 같은 자세). 그리고 두 장비가 같은 이름을 쓴다고 같은
물리량이 아니다 — 프레임 검사(dt_x↔core_x 규율) 전 통일 금지.

## 3. 관측이냐 추론이냐 — R-A의 규칙을 그대로 적용

- **소스가 스스로 요약을 발화하면** (per-wafer summary 행이 있는 MI 시스템):
  그 요약은 **관측(2류)** — 소스가 말한 것이다.
- **원시점만 있어서 번역기가 집계하면** (mean/min/max 계산): 그것은 규칙 아래의
  결론 — **`#<derivation>` 접미 강제, 3류.** 예: `#mean_agg`. 어느 쪽인지는
  config에 **선언**하고, `test_every_declared_derivation_is_explicitly_classified`가
  분류를 강제한다 (R-D·상설 규칙의 적용례).

## 4. 번역기 선언 스케치 (`ledger_config.json`에 한 장)

```jsonc
"mi_history": {
  "occurred_at_column": "<실물 확인 후>",
  "occurred_at_timezone": "Asia/Seoul",
  "subject_types": ["Wafer", "Lot"],          // R-D 허용목록 — 게이트가 문다
  "metric_map": { "<소스 방언>": "<개념명>" }, // 방언은 번역으로 소멸
  "summary_provenance": "source | aggregated" // §3의 선언 — aggregated면 #접미 강제
}
```

## 5. 화면 소비 (보이드 해석에서의 자리)

- 추적/패키지 화면에서 자재 홉 옆에 계측 팩트 몇 줄: 「BLT 12.3µm (n=49, #mean_agg)」
  — basis 규율(R-C) 그대로: 가정/집계는 표시가 다르다.
- 형제 공유 요인(2주차)의 입력: 「보이드 난 3자재가 전부 BLT 하위 10%」류의 한 줄이
  이 어휘가 사는 목적이다.

## 6. 판정 대기 (실물이 와야 닫힌다)

1. **MI 소스 실물** — 테이블인가 파일인가, 요약이 있는가 점뿐인가 (§3의 갈래 결정)
2. metric 개념명 목록 — 로컬 선등재로 시작, 장비 2대가 같은 이름을 쓰면 프레임 검사
3. site/좌표의 프레임 선언 (어느 좌표계인가)
4. SEMI 계측 표준 대응 조사 (차용 가능하면 중간층으로)
