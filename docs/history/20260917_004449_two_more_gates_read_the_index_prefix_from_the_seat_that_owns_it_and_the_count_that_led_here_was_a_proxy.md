# 게이트 둘이 색인 접두를 «그것을 소유한 좌석»에서 읽는다 — 그리고 거기까지 데려온 «수»는 대리였다

> **커밋:** `7df50de9` (00:44) — 구현자. 수 정정은 `82a0b6e4`
> **일자:** 2026-09-17
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **앵커는 HEAD blob 에서 다시 쟀다**

## 무엇을 했나

```
종전   from virtual_join.config import INDEX_PREFIX
지금   from chain.join_key_index import INDEX_PREFIX          (:32 에서 정의)
       from chain import join_key_index as vjc
대상   server/tests/test_a_product_index_lives_as_long_as_the_join_that_needs_it.py
       server/tests/test_business_key_conflict_retry.py
```

2단계 이후 `virtual_join.config` 는 그 이름을 **다시 import 할 뿐**이다. 두 파일이
«정의하는 좌석»에서 읽으면 패키지를 지울 때 그 둘이 같이 딸려가지 않는다.
`test_ledger_v2_pg.py` 의 두 줄에는 이미 같은 일이 되어 있었다.

**값은 그대로이고 «같은 객체»이지 사본이 아니다** — `virtual_join.config` 가 여전히
재수출하고, 기존 게이트가 그 «동일성»을 단언한다. 그것이 `uq_vjoin_` 의 둘째 철자가
생기지 않게 막는 것이다.

## 🔴 그런데 여기까지 데려온 «수»가 틀렸다 — 대리를 쟀기 때문이다

```
내가 한 것   패키지를 import 하는 시험 파일 «30» 을 «정규식»으로 분류했다
            (2단계가 옮긴 이름 vs 엔진 이름)  ->  「repointable 5」
실제        다섯을 «전부 열어 보니» repointable 은 «둘»
              하나는 JOIN_MAPPER 를 쓴다
              하나는 _validate_join 과 required_left_index_* 를 쓴다 — «옮겨가지 않은» 것들
              하나는 4단계가 바꿀 «세 파일 배치»를 패치한다
```

🔴 **철자 위의 술어가 «성질의 근사»를 셌다.** 이 저장소가 반복해서 기록하는 그 부류다 —
채널에 올린 보고는 「다섯」이라고 적혀 있고, 이 커밋이 그것을 정정한다.

📌 그리고 이 오류의 «모양»에 주목할 값이 있다: 수가 «틀린 쪽으로» 컸다. 다섯 중 셋이
repointable 이 «아니었다»는 것은, 그 셋이 4단계에서 «다르게» 다뤄져야 한다는 뜻이다 —
옮겨 놓고 끝나는 것이 아니다.

## 게이트

```
두 파일에서 30 passed
```

## 그때 남아 있던 것

- 이것은 **4단계 준비**이고, 4단계(패키지 삭제)는 이 시점에 열리지 않았다.
- `required_left_index_*` 와 `_validate_join` 은 **옮겨가지 않았다** — 색인 좌석이
  옮겨간 것과 별개다. 「2단계가 다 옮겼다」로 읽으면 안 된다.
