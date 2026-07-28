# 유령의 형제 — self-frame fail 원천이 좌표 없이 셀 때, 256/256이 '불량'이 됐다

> 커밋 `deed6d2` · 2026-07-28 21:34 · 도메인 Server(transfer_plan 강등 의미론)
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md)
> 원조 항목: [유령 remaining — count_only 강등](./20260728_163810_phantom_remaining_count_only_demotion.md) (`1fefd12`) — 그 항목의 "그때 남아 있던 것"에 **제안 중, 미착수**로 적혀 있던 형제 결함이 이 커밋으로 닫혔다.
> **동반 항목**: [관문 4](./20260728_213436_gate4_log_shaped_push_structural_discriminator.md) · [replace_map 정직한 범위](./20260728_213900_replace_map_honest_scope_400_over_noop.md) · [PM 헌장 등재](./20260728_214100_pm_charters_gain_ops_docs.md)

## 배경 — 같은 유령 계급, 반대쪽 항

`1fefd12`가 닫은 유령은 **감산항(used)이 조용히 죽는 축**이었다. 이 커밋의 형제는 같은
계급의 fail 쪽이다: origin_rows 경로에서 remaining은 집합 기반
(`total − |fail_union ∪ used_set|`)인데, x/y 없이 바인딩된 self-frame fail 원천은
`fail_breakdown`에 카운트를 넣으면서 `fail_union`에는 **아무것도 보태지 못했다.**
감산 집합에서 그 칩들이 빠지니 remaining이 과대보고되는데, 상태는 전부 connected라
화면은 신뢰할 수 있다고 말하고 있었다. 격리 재현: 256칩 전부 'failed'인 원천에서
remaining 209, `reliable: true`.

유령 계급의 정의가 여기서 완성된다 — **"기여해야 할 항이 조용히 0을 기여하면서
상태는 정상을 유지하는 축"**. used 쪽과 fail 쪽이 각각 한 번씩 이 모양으로 터졌다.

## 변경 내용 — 새 기계장치 없이, 기존 어휘에 플래그 하나

```python
# transfer_plan.py — _summarize_inline, 이 커밋 시점
elif origin_rows is not None:
    # ... a self-frame fail source without usable x/y feeds fail_breakdown
    # but nothing into fail_union — the subtraction silently misses these
    # chips and remaining over-reports (same phantom class).
    fail_count_only = True
    status = "connected(count_only)"
# else: fallback path (origin_rows is None) — remaining is the
# count-based total − Σfail − used, so cnt subtracts correctly
# without coordinates: stays plain connected, no demotion.
```

`connected(count_only)`는 `1fefd12`가 만든 어휘 그대로다 — 기존 강등 엔진이 remaining을
null로 만들고 상한을 싣는다. 카운트 자체는 진짜이므로 `fail_breakdown`에는 남는다
(count_only transfer_log 아래 `transferred`가 남는 것의 거울). by_core에서는 fail과
remaining을 null로 — `used`는 `used_set`에서 오므로 무사하다.

### 상한 불변식이 설계를 두 번 결정했다

이 시스템의 강등 불변식 — **"강등된 항은 과소 기여만 할 수 있다"** — 이 이번에도
갈림길마다 답을 줬다:

1. **빠진 점은 합집합을 줄이는 방향뿐**이므로 `total − |union|`은 여전히 진짜 상한이다
   — 감산항을 떨어뜨리면 값은 올라가기만 한다. 그래서 상한 서빙은 유지된다.
2. **cnt를 대신 빼지 않는다** — 칩 정체를 모르므로 used_set·다른 fail 원천과 겹칠 수
   있고, 겹침을 모르고 빼면 과감산으로 상한이 **아래로** 깨진다. 유혹적인 "그래도
   숫자는 있으니까"가 정확히 틀리는 지점이다.

### 폴백 경로는 일부러 손대지 않았다

origin_rows가 없는 폴백 경로의 remaining은 카운트 기반(`total − Σfail − used`)이라
좌표 없는 cnt가 **정확하게 감산된다** — 같은 코드 모양이 경로에 따라 결함이기도 하고
정답이기도 하다. 유령 계급의 판별 기준은 "좌표가 없다"가 아니라 "집합 감산에
기여하지 못한다"이다.

## 검증

- 전체 스위트 893 passed (conda `assy_manager`) — 신규 transfer_plan 테스트 포함
  (`test_transfer_plan.py` +108줄: count_only 강등·상한·by_core null·폴백 무강등).
- 격리 재현(256/256 'failed' → remaining 209 reliable:true)이 수정 후 null + 상한으로
  전환되는 것을 확인.

## 그때 남아 있던 것

- 원조(`1fefd12`)·형제(이 커밋) 두 번 모두 **같은 계급이 사후에 발견**됐다 — 강등
  어휘에 등록되지 않은 "조용한 0 기여" 축이 또 있는지의 전수 조사는 수행된 바 없는
  상태였다.
