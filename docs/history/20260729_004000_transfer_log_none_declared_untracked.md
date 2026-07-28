# "전사 기록이 없다"는 고장이 아니다 — 사이트가 선언할 수 있게 됐다

> 커밋 `ab6ac02` · 2026-07-29 00:38 · 도메인 Server(transfer_plan 가용 엔진 · source-summary 계약)
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) · 선언: [transfer_plan_config](../guide/config/transfer_plan_config.md)
> **동반 항목**: [캐노니컬 맵 키](./20260729_003843_canonical_map_key_by_declared_type.md) · [인제션 맵 메타 자동 등록](./20260729_004200_ingestion_map_meta_auto_registration.md)
> 형제 사례: [유령 잔여와 count_only 강등](./20260728_163810_phantom_remaining_count_only_demotion.md)

## 배경 — 정상 상태가 결함으로 표시되고 있었다

전사(소모) 기록 자체가 존재하지 않는 사이트가 있다. 종전 코드는 `transfer_log` 바인딩이
해석되지 않으면 무조건 `missing` — 강등이었다. 그런데 "바인딩이 깨졌다"와 "기록이 애초에
없다"는 다른 사실이다. 전자는 고쳐야 할 결함이고 후자는 **정상 운영 형태**다. 둘을 같은
코드로 표시하면 정상 사이트가 영원히 경고를 달고 살고, 진짜 결함이 그 소음에 묻힌다.

## 변경 내용

### 선언은 정확한 문자열 하나뿐이다

```python
# server/transfer_plan.py — _summarize_inline, 이 커밋 시점
if src == TRANSFER_LOG_NONE:
    # 소모가 기록되지 않는다고 사이트가 **선언**했다("none" — 정확한 문자열.
    # JSON null은 종전대로 missing으로 남는다: null은 키를 실수로 지운 것과
    # 구분할 수 없다). 강등이 아니다 — 바인딩이 깨진 게 아니라 사실이 진술됐다.
    used_untracked = True
    statuses["transfer_log"] = STATUS_TRANSFER_UNTRACKED
else:
    model, cols = _resolve(src, required=("lot", "slot"))
    ...
```

`"none"`이라는 **정확한 문자열만** 선언이다. JSON `null`·키 삭제·`"None"`은 전부 종전
동작 그대로 `missing`이다. 이유는 방향성 때문이다: 오타 하나가 **깨진 바인딩을 자신
있는 숫자로 바꾸면** 안 된다. `null`은 실수로 지운 것과 구분이 불가능하므로 선언으로
인정하지 않는다.

### 산술이 상한임을 증명하고, 상한을 제 이름으로 내보낸다

선언되면 `used_set`이 빈 집합으로 남는다. 그러면 계산된 remaining은 정확히
`총 − |fail 합집합|`으로 퇴화한다. **감산항이 빠지면 값은 커질 수만 있다** — 따라서
이것은 진짜 상한이다. 상한이라는 사실이 이름에 드러나게 내보낸다:

```python
# server/transfer_plan.py — 이 커밋 시점
bins_base_reliable = remaining_reliable      # untracked 강등 **이전**의 신뢰도 스냅샷
if used_untracked:
    remaining_reliable = False               # remaining은 null, 상한은 별도 이름으로
    deg_warnings.append({
        "type": WARN_TRANSFER_UNTRACKED, "role": "transfer_log",
        "status": STATUS_TRANSFER_UNTRACKED,
        "effect": EFFECT_REMAINING_UPPER_BOUND,
        "detail": ("전사(소모) 기록이 '없음'으로 선언됨(transfer_log: \"none\") — "
                   "잔여는 확정치가 아니라 상한이다. remaining_upper_bound를 "
                   "'≤N'으로 표시하라(미상이 아니다)"),
    })
...
    transferred=None if used_untracked else used_count,   # 0이 아니라 미상
```

`transferred`가 `None`인 것이 이 단락의 핵심이다. `used_set`이 비어 있으므로 자연히 0이
나오는데, 그 0은 "한 칩도 안 썼다"로 읽힌다 — 사실은 "기록이 없다"다. 가짜 0을 내보내느니
미상이 낫다.

`bins_base_reliable`을 **강등 이전에** 스냅샷하는 순서도 의도적이다. 이 덕분에 BIN별
상한은 **untracked가 유일한 사유일 때만** 주장된다. 다른 강등이 겹치면 상한의 성립조차
주장하지 않고 기존 unknown 처리로 떨어진다.

```python
# server/transfer_plan.py — _bins_block, 이 커밋 시점
if untracked:
    entry["transfer_untracked"] = True
    if reliable:
        entry["remaining_upper_bound"] = block["remaining"]
        entry["reason"] = ("전사 기록이 '없음'으로 선언됨(transfer_log: none) — "
                           "잔여는 상한(≤)만 제공")
    # else: 다른 강등이 겹쳤다 — 상한의 성립도 주장하지 않는다
```

### count_only의 선언된 형제

이 상태는 [count_only 강등](./20260728_163810_phantom_remaining_count_only_demotion.md)과
구조적으로 같다 — 둘 다 칩 단위 `used`를 알 수 없다는 뜻이다. 다른 것은 출처다: count_only는
**발견된 결함**이고 untracked는 **선언된 사실**이다. 그래서 코드에서도 둘이 같은 자리에서
같은 null을 만든다(`used`, `remaining`, `region_chips.transferred`).

## 아키텍처 영향

강등 어휘에 "정상인데 값이 없다"는 축이 처음 생겼다. 종전 어휘는 이분법이었다 —
`connected`(믿을 수 있다) 아니면 `missing`/`degraded`(고장). `connected(untracked)`는
셋째 축이다: 바인딩은 멀쩡하고, 값은 원리적으로 없으며, 그래도 **상한은 말할 수 있다**.
클라는 `미상` 대신 `≤N`을 그릴 수 있게 됐다.

또 하나: 이 커밋은 config의 오타 내성 방향을 다시 확인했다. 같은 규율이 `map_push_ok`
(JSON boolean만 유효)에도 있다 — **파괴적인 쪽으로 실수가 흐르지 않게** config를 읽는다.

## 검증

| 무엇을 | 어떻게 | 결과 |
|---|---|---|
| 신규 테스트 | `test_transfer_untracked.py` | 11건 |
| 선언 오인 방지 | `test_absent_key_stays_missing` · `test_json_null_stays_missing_not_untracked` · `test_case_variant_is_not_a_declaration` | 3축 전부 종전 동작 |
| 뮤테이션 | `untracked=False` / `transferred=used_count` / 상수 재지정 | 전부 검출 |
| 전체 스위트 | conda `assy_manager` | 944 passed |

상한 테스트가 vacuous하지 않음을 증명하는 장치가 있다: 상한(4)이 총(8)과 다르게 나오도록
fail 축을 살려 두고, 시드된 `bonding_log` 행은 **무시돼야** 통과한다 — 바인딩을 해석해
버리는 뮤턴트는 `transferred=3`을 내보내며 죽는다.

## 그때 남아 있던 것

- **lot 스코프는 상한을 합산하지 않았다.** `_merge_bins_over_slots`가 untracked 항목을
  unreliable로 취급해, lot 스코프 BIN은 `≤N`이 아니라 `unknown`으로 읽혔다. 상한의 합은
  유효한 상한이지만 이 커밋 시점 그 배선은 없었고, 처리 여부는 총괄 판단으로 남아 있었다.
- **M1 경로에는 선언 자리가 없었다.** `bonding_plan_config.used_chips`에는 `"none"`
  선언이 없다(스펙이 인라인 `transfer_log` 키만 지목했다) — 소모 로그가 없는 core 종류
  사이트는 여전히 강등으로 읽혔다.
