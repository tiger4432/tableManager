# 유령 remaining — 셀 수는 있는데 뺄 수 없는 칩이 +101을 만들었다

> 커밋 `1fefd12` · 2026-07-28 16:38 · 도메인 Server(transfer_plan·bonding_plan 강등 의미론, 5c)
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md)
> **동반 항목** (같은 커밋의 다른 두 반쪽): [인리치먼트 소급 백필](./20260728_163000_enrichment_backfill_script.md) · [빈 판단키 큐 필터](./20260728_170000_enrichment_queue_blank_key_filter.md) — 이 항목은 커밋 메시지 셋째 단락, **유령 remaining(5c)** 만 다룬다.

## 배경

사용자 보고 "remaining이 이상하다"를 트리아지한 결과 **REAL** — 격리 재현에서 remaining이
실제보다 정확히 전사 수만큼(+101) 부풀어 있었다. 원인은 강등 어휘의 구멍: `transfer_log`가
바인딩은 되는데 **쓸 수 있는 x/y가 없으면**, 행 수(count)는 진짜지만 칩 정체는 알 수 없다.
`used_set`은 비어 있는 채 `transferred`에는 카운트가 표시되고, 집합 감산 기반 remaining은
그 칩들을 **빼지 못한다** — 화면은 "101개 전사했다"와 "그 101개가 아직 남아 있다"를
동시에 말하고 있었다.

## 변경 내용

### `connected(count_only)` — 기존 강등 엔진에 새 어휘 하나

좌표 없는 카운트 경로를 새 상태로 강등하고, 판정자 `_status_is_degraded`에 등록했다:

```python
# transfer_plan.py — 이 커밋 시점
used_count = int(db.query(model).filter(*filters).count())
used_count_only = True
status = "connected(count_only)"
```

그 뒤는 **기존 QA F1 강등 엔진이 전부 처리한다** — remaining은 null(소비자가 분기 없이는
표시조차 못 하게), 대신 진짜 상한 `remaining_upper_bound`를 싣고, `transferred` 카운트는
진짜이므로 그대로 남는다. 새 산출 경로를 만들지 않고 어휘 하나를 보탠 것이 수리의 전부다.

per-core 분해도 같은 논리: `used_set`이 비어 있으니 코어별 used와 거기서 파생되는
remaining은 **알 수 없는 값**이라 null이다 — 가짜 0도, 가짜 total도 아니다. 이것은
transfer_log 경로와 area_map 경로 **양쪽** 모두이며, 최초 패치는 area_map 쪽만 null이고
log 경로에 맨 숫자가 남아 있었다 — **퀵 QA가 잡아서 마감 전에 닫혔다.**

### `column_unresolved` — config 오타가 조용히 사라지지 않게

선언됐지만 모델에 없는 옵션 컬럼(예: `"x": "cxx"` 오타)을 리졸버가 **조용히 스킵**하고
있었다 — 오타 하나가 무경고 집계 왜곡이 되는 축. `_ResolvedColumns`가 미해석 역할 키를
`.unresolved`로 실어 나르고, 상태를 세우는 각 지점이 `_demote_for_unresolved`로
`connected(column_unresolved:<roles>)` 마커를 합성한다 — `connected(area_only)`,
`connected(align_unavailable)`과 같은 기존 강등 어휘의 문법이다. 공유 역학은 리졸버 옆
`bonding_plan`에 살고 `transfer_plan`은 위임한다. **선언 자체를 생략한** 옵션 컬럼은
종전대로 정상이다 — 강등되는 것은 선언-후-미해석뿐이다.

### val 오타는 카운트를 거부한다 — 상한 불변식

`fail_values`가 선언됐는데 `val` 컬럼이 미해석이면, 필터 없이 세는 순간 **모든 행이
fail로 집계**된다 — 다른 강등들과 반대 방향의 왜곡이다. 이 시스템의 강등 불변식은
"강등된 항은 **과소 기여만** 할 수 있다"(그래야 remaining 상한이 상한으로 성립한다)이므로,
이 경우는 세지 않고 0 + 강등으로 거부한다. bonding_plan의 fail 카운트, transfer_plan의
fail_breakdown·origin 투영 세 지점 모두.

## 검증

| 무엇을 | 어떻게 | 결과 |
|---|---|---|
| 신규 테스트 | transfer_plan 10 + bonding_plan 11 (count_only 상한 서빙 · by_core 양 경로 null · 이중 마커 합성 · val 오타 거부 · 생략 컬럼 무강등 등) | 전부 통과 |
| 뮤테이션 | 바이트 수준 결함 주입, 서로소 부분집합으로 격리 | 전멸(killed) |
| 전체 스위트 | conda `assy_manager`, 통합 후 총괄 재실행 | 860 passed |

## 그때 남아 있던 것

- **형제 결함 제안 중, 미착수**: self-frame fail 소스가 x/y 미바인딩인 경우 — 같은
  유령 계급(감산항이 조용히 죽는 축)으로 판단돼 별건 승인 대기 상태였다.
- `count_only`는 클라이언트가 이미 소비하는 강등 문법(`connected(...)`)에 실렸으므로
  클라 변경 없이 경고·null 표시가 동작했다 — 이 커밋의 클라 diff는 동반 항목(큐 필터)
  몫이며 5c의 클라 절반은 존재하지 않는다.
