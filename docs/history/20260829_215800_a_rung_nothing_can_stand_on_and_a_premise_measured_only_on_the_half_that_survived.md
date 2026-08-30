# 아무도 못 딛는 계단은 «반대 방향의 거짓»이다 — 그리고 삭제의 근거를 «지워진 쪽»에서 재지 않았다

> **커밋:** `c929d7b3` (21:07) · `70c45eb0` (21:41) · `2faa2317` (21:43) · `4b6f3f90` (21:55)
> · `f6f41800` (21:58)
> | **일자:** 2026-08-29 밤
> **레인:** 서버(원장 계급 결의 · 시험 픽스처) + 보드 기록
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**

## 배경 — 빨간 계약 시험이 「오늘의 사상자」가 아니라 «가드가 일한 것»이었다

`c929d7b3`. 읽기 전용으로 진단했다. 두 config(출하 샘플 · 운영자 라이브)의 소스 **열넷**이
그 사이에서 선언하는 도출은 `positional_row` **하나**뿐이라, 어떤 소스도
`job_run_to_confirmed_container` 를 찍을 수 없다. 그런데 `ledger/config.py`·`ledger_trace.py` 가
아직 그 이름을 부르고 시험 파일 셋이 그것을 기대한다.

선언 쪽은 `ac0d8c84` 에서 떠났고 **코드 쪽이 남았다.** 이름을 은퇴시킬지 선언을 되살릴지는
판정이고 `server/ledger` 는 구현자 소관이라, 그때는 **아무것도 안 건드렸다.**

## 소유자 판정 — 이름을 은퇴시킨다

`70c45eb0`. `job_run_to_confirmed_container` 는 **여전히 문법이다** — 컨테이너 관계를 선언하는
transfer 소스는 그것을 찍을 수 있다. 다만 이 상자에서 그런 소스를 선언한 config 가 없다.

```python
# server/ledger_trace.py — DEFAULT_RESOLVER_CONFIG
-    "confirmed_derivations": ["job_run_to_confirmed_container"],
+    "confirmed_derivations": [],
```

**아무도 못 딛는 계단을 계급이라고 주장하는 것은 반대 방향의 같은 거짓이다.**
해결기가 «생길 수 없는 이름»으로 순위를 매기고 있었다.

🔴 **돌아오게 만드는 장치가 이미 반대 방향으로 서 있다.**
`test_every_declared_derivation_is_explicitly_classified` 는 **config 가 찍을 수 «있는데»
어느 목록도 분류하지 않은 도출**을 거부한다. 확인 관계를 가진 transfer 소스를 선언하는 날
그 시험이 빨개지고 이름을 되돌릴 때까지 안 풀린다. **판정이 잊히는 게 아니라 «강제»된다.**

## 이름은 은퇴해도 «기계»는 은퇴하지 않는다

계급 1 시험 셋이 재던 것은 「계급 1 이 타임스탬프가 아니라 «계단»으로 계급 2 를 이긴다」이고,
그건 오늘 어느 config 가 계급 1 도출을 선언하든 말든 덮여 있어야 한다. 그래서 시험이
**자기 픽스처 도출을 직접 만든다.**

```python
# server/tests/test_ledger_trace_contract.py
FIXTURE_CONFIRMED = "fixture_confirmed_container"
FIXTURE_RESOLVER = dict(lt.DEFAULT_RESOLVER_CONFIG,
                        confirmed_derivations=[FIXTURE_CONFIRMED])
```

**진짜 이름을 쓴 것이 바로 그 시험들을 은퇴한 이름에 묶어 놓은 원인이었다.**
`ledger/config.py`·`ledger/source_contract.py` 의 transfer 문법은 안 건드렸다.

## 🔴 「빨강 열여덟은 부류 하나」라고 보고했고, 재 보니 아니었다

`2faa2317` 에 「`pytest -k ledger` 432 passed / **18 failed**, 열여덟이 전부 같은 모양 —
픽스처가 `Lot@1`·`Wafer@1`, 선언은 `lot@1`·`wafer@1`」이라고 적었다.

`4b6f3f90`. 일괄 교체 판정을 받고 **먼저 쟀더니 부류가 내가 보고한 것과 달랐다.**

```
개명이 설명하는 것   «8»   (registration_probe 파일 안)
나머지               «10»  <- 여섯 파일, 여섯 가지 «서로 다른» 원인
```

그리고 **그 파일 안에서도 철자가 두 자리에 있었고 에러에는 «첫째»만 보였다.**

```
실제 번들에 주입하는 프로브 선언   "Lot@1" 9개 · "Wafer@1" 4개     <- 에러에 뜬 것
백필이 내놓기를 기대하는 주어 집합  ("Lot", …) / ("Wafer", …) 5개   <- 안 뜬 것
첫째만 고치면  빨강 9 -> 8
```

파일이 «스스로 선언하는» 대문자 id(`Nope@1`, 미선언 타입 케이스)는 그대로 뒀고, 대문자 id 가
자기 픽스처라 자기 안에서 정합한 다른 일곱 파일도 안 건드렸다.

마지막 빨강 하나는 **같은 색을 입은 다른 결함**이었다.
`test_the_shipped_config_still_loads_without_a_probe` 가 「출하 루트에 프로브가 «없다»」를
단언하고 있었는데, 그건 샘플과 라이브가 둘 다 프로브를 채택한 날 «선택성에 대한 진술»이기를
그만뒀다. 이제 참일 수 있는 유일한 방식으로 주장한다 — **매핑에서 프로브를 «빼고»,
루트가 여전히 검증·컴파일되는지**를 같은 물리 카탈로그에 대고 묻는다.

## 🔴 걷기는 끝났고, 막는 것은 «선언»이었다 — 그리고 그 삭제의 근거는 반쪽이었다

`f6f41800`. 소유자 대표 질문(「보이드 있던 wf 의 cmp rcp 로 진행한 wf 의 보이드」)을
고쳐진 walk 위에서 다시 태웠다.

```
BW 웨이퍼 ─inspected→ 다이 38                                   ✅
다이 ─bonded_from→ 코어 다이 38                                  ✅
코어 다이가 «키»로 든 mat_id = 코어 웨이퍼 16 (SYN-CW-103-*)      ✅ 재료는 있다
그 코어 웨이퍼 ─processed_with→ recipe 5 (SYN-R-CMP-01 포함)      ✅ 답은 저기 있다
🔴 코어 다이 ─?→ 코어 웨이퍼                                      ❌ 술어가 «없다»
```

`die@1.references` 는 null 이고 키는 `[mat_id, x, y, mat_type]`. 따라갈 수 있는 이름 열셋에
die→wafer 가 없고 `in_container` 는 **422**다.

그 엣지는 08-28 합성 엣지 삭제로 나갔고, **그때 내가 적은 근거**는
「`in_container` 가 «유일한 연결»인 쌍이 0 — `inspected` 가 이미 양방향으로 잇는다」였다.

🔴 **그 측정은 BW 쪽에서만 참이었다.** 코어 웨이퍼는 한 번도 `inspected` 되지 않으므로
**거기서는 `in_container` 가 유일한 연결이었다.** 즉 **지운 근거를 «지워진 쪽»에서 재지 않았다.**

이날 저녁의 걷기 규칙 셋은 이 시나리오에서 **아무것도 자르지 않았다.** 알고리즘이 아니라
선언이 멈춘 자리다.

## 스위트

```
2faa2317 시점   pytest -k ledger   432 passed · «18 failed» · 95 skipped
4b6f3f90 뒤     pytest -k ledger   441 passed · «9 failed»  · 95 skipped
                test_ledger_registration_probe  15 green
남은 9 의 갈래  setup_boundary 4 · transfer_unit 1 · source_preparation 1 ·
               admin_setup 1 · skeleton 1 · syn_complex_composite 1
```

## 아키텍처 영향

- 해결기의 **계급 1 목록이 비었다.** 문법은 그대로이고, 되돌리는 것을 강제하는 시험이 그 자리에 있다.
- 계급 1 시험 셋이 **자기 픽스처 도출**을 들고 있어, 어느 config 도 계급 1 을 선언하지 않아도
  랭킹 기계는 계속 채점된다.
- 다이↔웨이퍼 「담김」이 이 시점의 선언에 **없다.** 재료(`mat_id`)는 원자 안에 있는데 엣지가 없다.

## 그때 남아 있던 것

- 이 시점에 `in_container` 는 **422** 다. 술어가 선언에 없다.
- 다른 시나리오 둘도 같은 자리에서 멈췄다 — 「보이드 웨이퍼의 공정 조건」은 recipe «0»
  (BW 에는 `processed_with` 가 없다), 「측정 압력 → 메커니즘」은 `pressure_MPa` 씨앗이 노드 «1»(종점),
  `bond_pressure` 씨앗은 노드 21 · 5홉으로 «돈다» — 이음매 하나가 비어 있고 08-25 부터 알려진 벽이다.
- `pytest -k ledger` 의 남은 빨강 아홉은 **부류가 아니다.** 여섯 갈래이고 보드에 갈래별로 적혔다.
