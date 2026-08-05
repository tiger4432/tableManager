# 아무것도 채점되지 않은 것이 동점으로 보고됐다 — 사실 둘, 수리 둘, 단어 하나

> **커밋:** `2fb8fc2` (2026-08-05 15:54) | **일자:** 2026-08-05 오후
> **선행:** [`20260805_100000`](./20260805_100000_the_confident_winner_was_noise_because_occupancy_was_the_only_axis.md)(`5120e35` — 판정 순서를 세운 커밋) · [`20260805_074000`](./20260805_074000_a_stored_coordinate_is_bounding_box_relative_and_a_catch_turned_every_failure_into_a_plausible_wafer.md)(`cab8ed9`)
> **담당:** 제품 소유자(신고: 해소되는 참조를 골랐는데 판정이 「동점」) · map 구현
> **대상:** `server/map_alignment.py`(324 / 44) · `client2/src/map2/main.js`(110 / 12) · `verdict.js`(30 / 1) · `docs/spec/MAP_ALIGNMENT_SPEC.md`(36 / 1) · **신규** `server/tests/test_map_alignment_assumption.py`(**+602**) · `test_map_alignment.py`(185 / 5) · `server/enrichment_candidates.py`(145 / 25) + dist
> **스위트:** 커밋 메시지 기준 **서버 2,584.** ⚠️ **이 트리에서는 성립할 수 없다 — 아래 참조.**

## 배경 — 잘못된 단어가 운영자를 잘못된 수리로 보냈다

해소되는 참조를 골랐는데 **소스 맵이 전부 제외됐고, 아무것도 채점되지 않았다.**
그런데 판정이 **`동점`**이었다.

> 그래서 소유자는 **참조를 고치러** 갔다. 진짜 수리는 **소스 맵의 기하를
> 선언하는 것**이었다. **사실 둘, 수리 둘, 단어 하나.**

## 원인은 누락이 아니라 순서다

`score_candidates`가 채점기에 **`None`이 아니라 빈 배열**을 넘겼다. 그래서 상태가
`scored`로 돌아왔다.

```python
    for c in per_candidate:
        if c["keys"] is None:
            c.update(dx=None, dy=None, agreement=0, member=None)
```

그러면 후보 여덟이 **전부 0에서 동의**하고 `len(tops) > 1`이 되어 **`tie`가 아래의
`no_discrimination` 검사보다 먼저 반환된다.**

```python
    if len(tops) > 1:
        return dict(base, winner=None, margin=0, reason_code="tie", ...)
    if (top.get(d_key) or 0) <= 0:
        return dict(base, winner=None, reason_code="no_discrimination")
```

수리는 `scored` 플래그와 순서 재배치다:

```python
        if c["keys"] is None or c["keys"].size == 0:
            c.update(dx=None, dy=None, agreement=0, member=None, scored=False)
```

**구조적 사실이 임계값보다 먼저, 「아무것도 채점 안 됨」이 「전부 같음」보다 먼저:**

```
no_cells_scored → no_candidate_scored → no_overlap → no_discrimination
→ tie → (임계값 사유들)
```

모든 판정이 `placed_cells` · `source_map_count` · `excluded_map_count` ·
`excluded_reason_code`를 달고 나온다. **콘솔에만 있던 수가 판정 안에 들어왔다.**

## ⚠️ 「도달 불가한 죽은 가지」는 그대로는 성립하지 않는다

커밋 메시지는 `build_alignment_view`가 `no_winner`를 골라 **이미 「제외됨」이라고
말할 줄 알던 가지를 건너뛰었고, 그 가지가 죽은 코드였다**고 적는다. diff에서
확인되는 것은 다르다.

- 세 갈래 블록은 **컨텍스트 줄이다 — 앞뒤가 바이트 단위로 같다.**
  ```python
        if ruling.get("winner"):        state = STATE_SCORED
        elif any(c["state"] == STATE_SCORED for c in candidates): state = STATE_NO_WINNER
        else:                           state = STATE_NOT_SCORABLE
  ```
  **동작 변화는 전부 상류의 `scored=False`에서 왔다.**
- 「제외됨을 말할 줄 알던 팔」은 `build_alignment_view`가 아니라 **`compose_refusal`**
  안에 있고, **일반적으로 도달 불가가 아니었다** — 참조가 해소되지 않은 경우
  `STATE_NOT_SCORABLE` 갈래로 정상 도달한다. **죽어 있던 것은 「참조는 해소됐는데
  소스가 전량 제외된」 특정 경우에 한해서**다.

## 같은 계급이 셋 더 떨어져 나왔다

- **대칭 발자국**이 `동점`으로 보고됐다 — 모듈 자신의 문서가 그것을 **참조가
  구별하지 못하는 것**이라 부르는데도.
- **적중 0인 후보**가 `no_overlap`이 아니라 `tie`로 불렸다.
- **거절된 후보들보다 차점이 먼저 뽑혔다.** 그들의 일치 0은 **플레이스홀더**인데,
  그 결과 홀로 살아남은 후보가 **자기 일치 전부를 격차로 보고**했다.

**핀으로 박힌 테스트 둘이 틀린 답을 단언하고 있었고 정정됐다.**

```python
# 이전
    assert ruling["reason_code"] == "tie"
    assert len(ruling["tied"]) > 1
# 이후 (이름도 …a_structural_refusal…로)
    assert ruling["reason_code"] == ma.RULING_NO_DISCRIMINATION
    assert ruling["discriminating"] == 0
```

```python
# 이전
    assert none["ruling"]["reason_code"] in ("no_thresholds", "tie", "no_discrimination")
# 이후
    assert none["ruling"]["reason_code"] == ma.RULING_NO_OVERLAP
    assert none["ruling"]["placed_cells"] > 0, "cells reached the scorer; none of them landed"
```

## 클라 절반 — 게이트 셋이 다 갖춘 화면을 비우고 있었다

① **`no_winner`에 붙은 거절 문장이 거절로 읽혔다.** 뒤집힘 하나가 숫자와 카드
여덟과 바닥을 다 죽였다.

```js
// 지워진 줄
  if (detail) return frozen(VERDICT.NOT_SCORABLE, REASON.SERVER_REFUSED, { refusalDetail: detail });
```

② **후보 격자가 컬럼 쌍이 해소돼야만 열렸다.**

③ **컨트롤 여덟이 아무도 복제하지 않는 `<template>` 안에 살았다 — 라이브 DOM에
0개였다.** 커밋 메시지가 그것을 **「내가 세팅해 놓고 한 번도 확인하지 않은
인계」**라고 적는다.

이제 동점이면 **동일한 점수를 읽는 활성 후보 여덟이 보인다** — **그것들이 같다는
주장은 그것들을 보지 않고는 검증할 수 없기** 때문이다. 바닥은 **참조가 해소되면
항상** 그려진다.

## ⚠️ 이 커밋은 혼자 서지 못한다

- `map_alignment.py`가 `map_overlay.assume_phys_from` · `grid_dims` ·
  `GEOMETRY_ASSUMED`를 부르는데 **이 커밋 시점 `server/map_overlay.py`에 셋 다
  없다.** 그것들은 **다음 커밋 `0947972`**에 들어간다. 신규
  `test_map_alignment_assumption.py`(602줄)와 스키마 드리프트 테스트의
  `geometry_assumed`/`geometry_basis` 컬럼 핀도 마찬가지다.
  **「서버 2,584」는 이 트리에서 초록일 수 없다.**
- `server/enrichment_candidates.py`(+145 / −25)와 그 테스트가 **커밋 메시지가
  한 번도 언급하지 않는 변경**이다. 읽기 상한 절단 보고
  (`_truncation_error` · `cap_declared` · `_record_cap_hit` …)를 넣는데, 그것이
  부르는 `enrichment_config.load_read_caps` · `CAP_PROBE_SCAN_ROWS` 등은
  **이 커밋에 없고 `e3873a0`에 들어간다.**

> 즉 이 라운드에서 **커밋 경계가 세 번 앞뒤로 어긋났다** — `7f0a717`↔`4717429`,
> 여기↔`0947972`, 여기↔`e3873a0`. 세 경우 다 **커밋 메시지의 스위트 숫자가
> 그 커밋의 트리가 아니라 작업 트리에서 나온 것**이다.

## 그때 남아 있던 것

- 커밋된 트리에서 **혼자 초록일 수 없는 상태**다. 짝이 되는 커밋과 함께여야 한다.
- `enrichment_candidates.py`의 상한 보고는 **소비자가 아직 없는 상태**로 들어갔다.
