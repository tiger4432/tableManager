# 대조가 항목 고르기를 그만두고, 세 관문이 도착했다

**Date:** 2026-08-14 16:15 · **Domain:** Server (원장 읽기 · 대조 엔진 · 기전 관문) · **Status:** 착지 — 미커밋(총괄 검수 대기)

---

## 라운드 중간에 방향이 바뀌었고, 바뀐 쪽이 옳았다

착수 지시는 「기존 contrast에 랏 스코프를 달라」였다. 착수 직후 소유자 정정
(`5cd7593`, §0-quinquies R1 개정): 「대조할 랏 선택은 괜찮은데 **그 안에서 여러 항목
비교하는 게 별로 — 항목에 가정이 들어가잖아.** 다 걷기로 처리하면 양쪽 그룹별로
챔버 차이·레시피 차이 이런 게 **알아서 드러날** 텐데」.

정정이 도착했을 때 이 레인은 아직 실측 단계였고, 그 실측이 정정과 같은 결론에
독립적으로 도달해 있었다: **정답지의 심은 원인 `recipe_rev@BONDING`은 선언된 축
어디에도 없다.** `siblings_axes.json`이 아는 축은 `bonding_log`의 다섯과
`inspection_run`의 둘뿐이고, 심은 인자는 `ledger_events`의 `processed_with` payload
안에만 있다. 옛 설계로는 정답지를 **축 하나를 더 선언해야** 볼 수 있었고 — 그것이
바로 소유자가 없애라고 한 그 가정이다.

## 후보 공간 = 걷기가 닿은 모든 것 (`server/ledger_walk_contrast.py`, 신규)

랏 마킹은 사람 몫으로 남는다. 그 뒤로는 아무것도 고르지 않는다:

    후보 = 마킹된 주어들의 모든 원자를 (술어 × payload 필드 경로 × 값)으로 펼친 것

payload 평탄화는 `jsonb_each` 재귀 CTE 하나다. 실측 73개 필드가 **선언 0줄로**
나왔다 — `processed_with·recipe.rev`, `·chamber`, `·params_actual.pressure_MPa`,
`transferred·to.keys.dt_lot`, `observed·finding_kind` … 챔버·레시피가 축으로 세워져서가
아니라 거기 있어서 나온다.

**비교 방식은 JSON 타입이 정한다** (소유자: 「필드 유형이 비교 방식을 자동 결정」) —
`string`/`boolean`은 점유율 대조, `number`는 분포 요약(순위는 R7), 전부 `null`인
필드는 그렇게 표기. 필드 이름 목록은 이 파일 어디에도 없고, 그 성질을
`test_ledger_walk_contrast.py::test_a_field_no_config_has_ever_heard_of_becomes_a_candidate`가
**이 저장소의 어느 config에도 없는 필드 이름으로 몰아서** 고정한다.

`siblings_axes.json`은 남지만 강등됐다: 모집단 기하 · **마킹 축** · 라벨 장식.
무엇을 비교할지는 이제 결정하지 않는다.

## 비교 단위가 패키지에서 «주어»로 옮겨갔다

`processed_with` 원자는 웨이퍼에 대한 발화다. 그 웨이퍼의 패키지 141개를 독립 관측
141건으로 세면 신뢰구간이 한 자릿수 배로 좁아지고 순위 맨 위가 잡음으로 채워진다.
그래서 대조의 단위는 주어이고, 패키지 수는 **왜 이 랏을 마킹했는가**의 맥락으로 남아
`scope.case`/`scope.control`에 분모와 함께 실린다.

양쪽 어디에도 안 드는 셋째 버킷이 있다: **`mixed`** — 마킹 안팎에 유닛이 걸친 주어.
조용히 한쪽에 붙이면 같은 원자가 대조의 양변에 앉는다.

## 「귀속 N/M」이 장식이 아니라 «비율이 서는 분모»다

총괄이 넘긴 클라 실측(본딩 축이 46,899 중 44,399에만 닿는데 전 인자가 46,899로
나눈다)의 일반형을 이 엔진이 구조로 막는다. 모든 행이 분모를 **둘** 나른다: 쪽
크기(`of`)와 **그 필드가 닿는 주어 수**(`attributed_of`). 농축비는 뒤엣것 위에 서고
`enrichment_basis: "attributed"`가 그렇게 말한다.

**그리고 이 상자에서 즉시 값을 했다.** 엑스커전 3랏은 `observed` 원자를 **하나도**
안 가지고 있다(그 번역이 이 랏들보다 먼저 돌았다). 쪽 크기로 나누면
`observed·finding_kind = void`가 「케이스 0 대 대조군 2,500」이 되어
**「이 랏들엔 보이드가 없다」**로 읽힌다 — 진실의 정확한 역상이다(이 랏들은 found_rate
0.919로 마킹된 랏이다). 귀속 분모로는 0/0이라 나눌 것이 없고, 판정은
`undeterminable`, 커버리지 필드가 이유를 말한다. `null` ≠ `0`.

## 세 관문 (R3) — `server/mechanism_gate.py`, 신규

* **실재** — Katz 하한(기존 규율 재사용)
* **상류** — 원자의 `occurred_at`이 그 주어의 첫 런보다 앞서는가. 원자당 한 번
  해소해 재귀에 3바이트 코드로만 실어 나른다
* **기전** — `mechanism_models.json` BFS. **M4 기전 그래프의 첫 소비자다**
  (`ledger_structure.mechanism_layer`가 「선언만 있고 소비자 0」이라 적어 둔 그 그래프)

**판정은 넷이고 닮은 둘이 서로 다르다**: `pass` · `bias_candidate`(observation_bias
모델에만 닿음 — 원인이 아니라 편향 후보) · `fail`(모델 안에 있는데 경로 없음) ·
`unknown`(아무도 안 물었거나 답할 것이 없음). 🔴 **`unknown`은 절대 `fail`로 접히지
않는다** — 그리고 그것이 「선언 0줄」 약속을 지키는 장치이기도 하다: 새로 번역된 술어는
바인딩 없이 도착해 순위에 들고 기전 칸만 「—」로 남는다.

BFS는 모델 경계를 넘지 않는다. `bond_pressure`는 void 모델과 delam 모델 양쪽에 있고,
모델을 갈아타며 걸으면 아무도 하지 않은 셋째 주장이 만들어진다.

선언 파일에 `role`·`finding_kind`·`target`이 없으면 **이름으로 추측하지 않고**
「사용 불가」로 표기한다 — `*_observation_bias`라는 문자열에서 「원인이냐 편향이냐」를
정하는 것이 정확히 이 관문이 막아야 할 일이다.

**순위 = 관문 통과 사전식, 동률은 효과 크기.** 기전 칸에서 `unknown`이
`bias_candidate`·`fail`보다 위에 앉는다 — 「실재✓ · 상류✓ · 기전 —」이 브리프가 말하는
DOE 후보이고, 모델이 이미 기각한 것 아래에 묻히면 안 된다.

## 정답지 — 축 선언 0개로 통과

`GET /api/ledger/siblings?finding=void&scope=bond_lot:SYN-VOID-101,102,103` (실측):

| 후보 | 상태 | 농축 | 관문 |
|---|---|---|---|
| **`processed_with·recipe.rev = 6`** (심은 원인) | enriched | CI [156.5, 39962] | **실재✓ 상류✓ 기전—** |
| `processed_with·step = BONDING` (미끼) | flat | 1.000 | 실재✗ |
| `processed_with·recipe.id = SYN-RCP-BOND` (미끼) | flat | 1.000 | 실재✗ |
| `processed_with·chamber = CH-B` (미끼) | flat | 1.028 | 실재✗ |
| `processed_with·recipe.id = SYN-RCP-MOLD` (미끼) | flat | 1.000 | 실재✗ |
| `processed_with·step_family = packaging` (미끼) | flat | 1.000 | 실재✗ |

농축비가 아니라 **구간 하한**이 순위를 만든다. 대조군에 하나도 없는 값은 「무한대로
농축」이 아니라 `enrichment: null` + 유한한 하한이다(무계 점추정은 측정된 모든 것 위에
앉는다).

## 실측이 낳은 부산물 셋 — 전부 보고 대상

1. **엑스커전 웨이퍼는 BONDING 리비전 주장을 «둘» 가진다** — rev5(공정 시드) +
   rev6(엑스커전 시드), 웨이퍼 75개 전부. `seed_syn_lot_excursion`의 docstring이
   피하려던 바로 그 상황이 다른 시드의 재실행으로 생겼다. 걷기는 승자를 «해소하지
   않고» 모든 주장을 센다 — `recipe.rev = 5`가 9.19배로 같이 뜬다. 정직하지만,
   해소 후 대조냐 전 주장 대조냐는 판정이 필요하다.
2. **예산 게이트를 «양쪽에서» 재야 한다.** 첫 판은 원자/주어를 케이스 쪽 표본으로만
   쟀고 8배 과소평가했다(엑스커전 웨이퍼 9원자 대 정상 웨이퍼 47원자 — 위 1번과 같은
   이유). 게이트가 안 물어서 요청이 18.5초 걸렸다. **양쪽이 다르다는 것이 이 도구가
   존재하는 상황**이라, 둘이 같다고 가정한 예산은 필요할 때 정확히 틀린다.
3. **10M에 못 간다, 그리고 그렇게 말한다.** 평탄화 실측 ~73µs/원자(선형).
   케이스는 «절대» 표본하지 않고(질문 그 자체), 대조군만 정렬 위치로 결정적으로
   솎아 `walk.gate`가 그 사실을 응답에 싣는다 — 표본했다고 말하지 않는 표본은
   신뢰구간을 단 거짓말이다.

## 변경 파일

* 신규 `server/ledger_walk_contrast.py` · `server/mechanism_gate.py`
* 신규 테스트 `server/tests/test_ledger_walk_contrast.py`(21건) ·
  `server/tests/test_mechanism_gate.py`(11건) — **둘 다 PG 없이 도는 초록**
* `server/ledger_siblings.py` — `_Plan(run_time_as=)` **가산·기본 off**(기본값에서
  SQL 바이트 동일) · `Geometry.ledger_subject`
* `server/ledger_trace_router.py` — `/siblings`에 `scope` 파라미터, **엔진 전환**
  (라우트는 여전히 하나, `engine` 필드가 어느 쪽이 답했는지 말한다)
* `server/config/mechanism_models.json`(+`.sample`) — 모델마다
  `role`/`finding_kind`/`target`, 그리고 `bindings`(필드→물리량)
* `server/config/siblings_axes.json.sample` — `geometry.ledger_subject` ·
  `defaults.walk`
