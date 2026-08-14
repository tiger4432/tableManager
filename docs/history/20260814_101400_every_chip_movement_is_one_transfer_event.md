# Every chip movement is one transfer event

**Date:** 2026-08-14 10:03 / 10:14 · **Domain:** 아키텍처 + Server (원장 넷째 다리) · **Status:** 착지 — 설계 `4dff09f`, 구현 `530fda6`

---

## 일반화 (`4dff09f`) — 걷기는 stage 이름을 모른다

소유자가 한 교환에서 체인 모델을 두 번 일반화했다: DT 적재·본드 배치의 stage별 주장
대신 **모든 칩 이동은 transferred 이벤트 하나**(어느 다이가, 어디서, 어디로) — 랏
수준 이벤트 축의 칩 수준 평행. 선택은 transfer의 유무가 되고, 잔량 재고는 컨테이너별
유입-유출이 되고, 예약돼 있던 `consumed` 술어는 흡수된다(소모는 밖으로의 transfer).
그리고 DT를 N번 지나는 경로가 **공짜로** 추적된다 — 걷기가 stage 이름이 아니라
**위치 연속성과 시간**으로 이벤트를 잇기 때문에. **DT가 한 번이라고 가정하는 조인은
정의상 결함이다.**

## 구현 (`530fda6`) — 125가 그 문장을 증명한다

```python
# from/to는 step 이름이 아니라 구조화된 컨테이너다 —
# 걷기가 «위치»로 조인하므로 컨테이너가 비교 가능해야 하는 그것이다
"transferred": { ... }
```

짓기 전에 검증했다: `bonding_log.dt_lot`과 `dt_log.dt_lot`은 **겹침 0** — DT 다리는
진짜로 끊겨 있었다. 이벤트: wafer_grid→dt_slot 2,500(적재, 구조상 부분적),
dt_slot→dt_slot **279**(둘째 DT hop), dt_slot→package_gate 62,500(소모 — 수량은
심은 게 아니라 `bonding_log`에서 «계수»). 수용 핵심:

```
packages walked 400 | reached the core wafer 400
chains passing TWO dt slots: 125
→ "DT happens once" 조인은 그 125에서 틀린다
```

hop 카운트는 어디에도 없다 — 유일한 정수는 사이클 가드. mutant가 증명을 든다:
패키지에서 한 걸음 물러나는 조인은 정확히 그 125에서 `wafer_grid` 대신 `dt_slot`에
착지한다. `--double-dt-fraction 0`이 판별력을 파괴하는 설정으로 문서화됐다 — 두
규칙이 합의하는 픽스처를 재생성하지 못하게 하는 문장. 잔량은 저장 없이 이벤트 위의
fold(2,779 컨테이너, 음수 0). 멱등은 가정이 아니라 검증이었고 수리가 먼저 필요했다:
`sorted(RECIPES)`가 DT 레시피 추가 시 `SYN-RCP-MOLD`를 밀어 전 MOLD 원자를 중복
삽입했을 것 — `RECIPE_ORDER` 명시적·append-only. 재적용 `inserted=70284
deduped=13554`.

5분 안에 도착한 모델 지시 셋 중 **셋째만 지어졌다** — 앞 둘도 낭비가 아니다: DT
레시피는 그 런의 «조건»으로 `processed_with`에 살아남아 이동 옆에 선다. 레인이 자기
앞 커밋도 교정했다: `population_ctes`는 세 갈래 분할의 유일한 철자가 **아니다** —
`ledger_siblings.py`가 런 윈도잉 때문에 자기 것을 조립한다. 두 docstring이 이제 「두
철자가 존재하고 오늘은 합의하며 어긋나는 날을 감지하는 것은 없다」고 말한다.

## 그때 남아 있던 것

- 구멍 둘이 표면화되고 미수리: `step`의 「닫힌 값 집합」은 실리지 않았다 —
  `check_signature`는 키 존재만 요구하고 아무 문자열이나 수용하므로 오타 step이
  조용히 새 step으로 태어난다; `transferred`의 컨테이너 `type`도 같은 구멍.
- 어휘 7 → 10(핀 테스트가 각 착지마다 실패). 답안지·계급 경계 증명 재실행 무변동.
  169 tests pass. 원장 909 → 84,747.
