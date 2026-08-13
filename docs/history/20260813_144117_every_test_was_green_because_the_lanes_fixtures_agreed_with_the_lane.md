# Every test was green because the lane's fixtures agreed with the lane

**Date:** 2026-08-13 14:41 · **Domain:** Server (원장 추적 / ledger slice 1 L2) · **Status:** 착지 — `01452d5`

> ⚠️ **비용 수치는 이 박스의 합성 원장이다.** 운영의 증거가 아니다.

---

## 배경 — 두 번째 층

`GET /api/ledger/trace?lot=&slot=`이 웨이퍼의 계보를 걷고 `hops[]`를
`state: resolved|candidate|unresolvable` + `reason` + `terminal_reason`으로 답한다.
`main.py`에서 일곱 줄이고, SPA catch-all **위에** 앉는다 — `/health`가 그런 것과 같은
이유이고, 그 라우트가 `index.html`이 아니라 JSON을 돌려주는지 테스트가 단언한다.

## 거의 출하될 뻔한 버그가 헤드라인이다

**이 레인의 모든 테스트가 초록인 동안 통합은 끝에서 끝까지 깨져 있었다.** 픽스처가
평평했고(`{"lot": ...}`), 실제 payload는 `entity_ref`(`{type, keys, qualifiers}`)다.
그래서 **모든 리더가 `None`을 돌려줬고 첫 실제 질의에서 모든 hop이
`[unusable_payload]`로 돌아왔을 것이다.**

**레인이 직접 쓴 픽스처는 그 레인에 동의한다. 초록의 양은 아무것도 반증하지 않는다.**

`test_ledger_trace_contract.py`는 이제 픽스처를 손으로 쓰지 않고 **번역기 자신의
`entity_ref`를 «호출해서»** 짓고, 실제 번역기를 구동한다.

```python
from ledger.envelope import Atom, entity_ref

def test_the_payload_readers_read_the_translators_own_entity_ref():
    ... predicate="has_wafer", object_kind="entity_ref",
        object_payload=entity_ref("Wafer", {"wafer": "WF.01"}, slot="07")
```

## 해소기는 기존 프리미티브를 다시 만들지 않고 부른다

`claim_rank_key`는 `crud.compute_priority_value`의 모양이다 — **권위가 바깥쪽인 사전순
튜플**이라 동점 처리는 한 계층 안에서 닫히고 계층을 넘지 못한다. 두 계층은 재구현이 아니라
**호출**된다(`crud.get_source_priority`, `crud.resolution_ingested_at`), 그리고 같은 질문에
대해 둘이 **같은 레이어를 고른다**는 것을 테스트가 못 박는다.

## 전순서성이 «뻔한» 논증에 기대지 않는다

「`id`가 유니크 PK이므로 마지막 계층이 언제나 결정한다」는 **쓸 수 없다**: PostgreSQL은
`occurred_at`으로 파티션된 테이블에 `PRIMARY KEY (id)`를 **거부한다**(18.3에서 확인).
키는 `(id, occurred_at)`일 수밖에 없으므로 **계층 2b와 3이 «함께» 기본 키**이고, 전순서성은
데이터베이스가 강제하는 제약에 기댄다 — 다른 시각의 같은 `id`는 PG가 **받아 주는** 행이고,
이제 그것이 결정적으로 해소된다.

## 온톨로지 소유자의 판정이 «테스트»가 됐다

관례에 기댄 원자는 자기 `#<derivation>` 접미사를 읽고 **클래스 3**으로 해소되며,
`basis=shared_wafer`에 맞서 `convention:slot_preserving`으로 렌더된다 — **단어가 구별을
나른다.** 그리고 상시 규칙이 테스트다:
`test_every_declared_derivation_is_explicitly_classified`가 번역기 config가 낼 수 있는 모든
derivation을 열거하고, 이 해소기가 자리를 정해 주지 않은 것이 하나라도 있으면 실패한다 —
**새 관례는 조용히 클래스 2로 해소되는 대신 스위트를 빨갛게 만든다.** 아무도 무엇을 뽑지
않은 채 본딩 로그 관측이 관례에서 hop을 뺏는 장면이 보여진다.

## 시간대는 운에 기대지 않고 «선언»으로 닫혔다

`display_timezone: "Asia/Seoul"`, 못 쓰는 존은 기본값으로 떨어지지 않고 **거절**된다.
「UTC로 내보내고 클라가 지역화하게 하자」가 아니다 — 그것은 fab 기록의 정확성을 **보는
사람의 기계로** 옮기는 일이다. 테스트가 PostgreSQL 세션을 UTC · America/Los_Angeles ·
Asia/Seoul로 강제하고, psycopg2가 **정말로 세 개의 다른 오프셋을 돌려줬는지** 단언한 뒤,
렌더된 문자열이 **한 번도 안 움직인다**고 단언한다.

## 🔴 추적 비용은 원장 크기가 아니라 «파티션 개수»를 따른다

원장 크기에 대해서는 평평하다 — 20배 원장에서 0.986 → 0.997 ms/hop. 그런데 **같은 18,000
원자**에서 파티션 1개일 때 2.34 ms/trace, 60개일 때 **16.47 ms — 7.0배**, 파티션 하나당
+0.24 ms. 걷기가 `occurred_at` 술어를 **안 들고 다니므로 pruning이 발화할 수 없고** 매 hop이
모든 파티션을 방문한다.

이것은 총괄이 판정한 **월별 grain의 직접적 결과**다 — 10년 원장이면 ~120 파티션, 이 박스에서
~30 ms/trace. 월별을 뒤집지는 않는다(pruning과 detach는 다른 질의들이 결정한다). 다만
week 2의 슬롯 단위 머티리얼라이제이션에 대한 **둘째, 독립적인 논증**이고, 각주가 아니라
**그 판정 옆에** 기록될 자리다 — 같은 날 `7cc5ed7`이 그것을
`CANONICAL_LEDGER_DESIGN §7-bis ④`로 옮겼다(첫째 논증은 ③의 780배).

한 방짜리 CTE는 유지됐지만 **기본값이 아니다** — 작은 원장에서 20.2 ms로 퇴화한다.
PostgreSQL이 재귀 CTE의 출력 크기를 추정하지 못해 계획이 **전체 파티션 스캔 위의 Hash Join**으로
뒤집히기 때문이다.

## 그때 남아 있던 것

- 6파일 +3,298/-0. 그중 테스트가 2,032줄.
- 검증: 커밋되는 트리에서 189 passed, 2 skipped(게이트된 비용 프로브). 격리 `assy_qa`에서
  L1의 재백필된 878 원자에 대고 **읽기 전용** 실제 체인: 계보 3 hop, 총 11 hop,
  `[root] ... derived_from 주장 없음`으로 종료. 끊긴 체인 시연은 **버리는 스키마의 사본**에서
  돌았다 — `has_wafer` 하나를 지우면 그 hop이 `[no_claim]`이 되고 hop 수는 11로 유지된다.
- 결함 주입 17종 전부 빨강. **둘이 처음엔 초록으로 돌아왔고 둘 다 진짜 커버리지 구멍이었다** —
  CTE dedup에 다이아몬드 계보 픽스처가 없었고(그것이 바로 merge가 만드는 모양이다),
  그리고 payload 리더들.
- 열어 둔 것: `slot_map` 방향은 원자의 주어가 어느 lot이냐에서 **양방향으로** 읽는다.
  L1의 관례는 이제 테스트가 못 박지만 **설계가 그것을 못 박은 적은 없어서**, 문서화되지 않은
  관례를 하드코딩하는 대신 양방향 읽기가 남았다.
