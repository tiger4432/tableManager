# 세 가지가 `limit`이라는 같은 철자를 썼고, 그중 하나는 표시 설정이었다

> **커밋:** `e3873a0` (2026-08-05 16:11) | **일자:** 2026-08-05 오후
> **담당:** 제품 소유자(`dt_lot`에서 `distinct_truncated`를 맞고, **총괄이 「상한을 올리라」고 답한 뒤 스스로 원인을 찾아냄**) · server 구현
> **대상:** `server/enrichment_config.py`(266) · `server/scripts/enrichment_insights.py`(83) · `enrichment_analysis.py`(56) · `server/config/ingestion_settings.json.sample`(13) · 가이드 2종 · 스펙 · 테스트 3종
> **스위트:** 커밋 메시지에 결과 없음.

## 배경 — 운영자가 닿을 수 있던 상한은 읽기를 자른 상한이 아니었다

그리고 **둘이 아니라 셋이었다.**

| 철자 | 실제로 무엇인가 |
|---|---|
| CLI `--probe-limit` | **키 예산.** 어떤 읽기도 넓히지 않는다 |
| 참조 뷰의 `limit` | **표시 행 수** |
| 그 뷰 `limit`의 재사용 | **프로브의 distinct 값 상한** |

```python
limit = view.get("limit") or DEFAULT_REFERENCE_LIMIT   # 표시 설정이 정확성 상한을 겸했다
```

> **표시 설정이 정확성 상한을 겸직하고 있었다. 운영자가 보이는 것을 조정하면
> 증명할 수 있는 것이 조용히 같이 조정됐다.**

## 다시 헷갈릴 수 없게 이름을 갈랐다

`--max-keys` · `probe_scan_rows` · `probe_distinct_values`.
(`--probe-limit`은 `dest="max_keys"`로 **폐기 예정 별칭**으로 남고, 옛 kwarg로
부르면 경고 후 재할당된다.)

그리고 **두 프로브 상한이 `classify`뿐 아니라 `confirm`에도 존재한다** —
**한 상한으로 재고 다른 상한으로 쓰는 것이 두 표면이 어긋나는 방식**이기 때문이다.
뷰당 `limit`은 원래 뜻으로 남고 **더 이상 프로브를 지배하지 않는다.**

## 상한은 config로 가되, 부재는 거절이 아니라 「오늘 값 유지」다

```python
SHIPPED_READ_CAPS = {
    CAP_REFERENCE_ROWS_DEFAULT: 200,
    CAP_REFERENCE_ROWS_MAX: 1000,
    CAP_PROBE_SCAN_ROWS: 5000,
    CAP_PROBE_DISTINCT_VALUES: None,
}
```

**정렬 임계값과 다르다.** 없는 천장은 **답의 의미를 파괴하지 않고 보호만
없앤다.** 그리고 부재에 거절하면 **config를 손대지 않은 모든 설치가 업그레이드
때 통째로 내려간다 — 버그보다 큰 장애다.**

대신 **부재가 보이게** 만들었다. `load_read_caps`가 `{value, declared}`를 돌려주고,
모든 절단 거절에 `cap_declared`와 `cap_home`이 실린다. CLI는
`<- NOT declared; this is the shipped value`를 인쇄한다.

## 거절이 어느 결말이 나올지 말한다 — 추가 조회 0회로

```python
        "expected_if_raised": (EXPECT_AMBIGUOUS if distinct_so_far >= 2
                               else EXPECT_UNKNOWN),
        "distinct_values_read": distinct_so_far,
```

**잘린 읽기가 이미 읽은 값들이 존재하는 distinct 값 수의 하한**이다. 손에 이미
서로 다른 값이 둘 이상이면 **상한을 올려 봐야 이름만 `ambiguous`로 바뀌고 사람이
판단해야 한다.** 하나 이하면 **그 노브가 실제로 해결할 수 있다.**

> **수리 방법을 이름 대지 않는 거절은 운영자를 사람에게 보낸다** — 그리고
> 여기서 실제로 그렇게 됐다. 그 사람이 나였고, 내 답이 틀렸다.

## 실측은 개발 박스에서 났고, 그렇게 적혔다

선언하는 뷰들은 **키당 한 행으로 완전히 좁혀지므로** 거기서의 절단은 예외적이고
「상한을 올려라」는 틀린 수리다. **76건이 목격된 운영 데이터에 대해서는 아무것도
말하지 않는다.**

## ⚠️ diff가 커밋 메시지와 어긋난 자리

- **이 커밋에는 자기 상한을 소비하는 코드가 없다.** `enrichment_analysis.py`가
  `enrichment_candidates._record_cap_hit(...)`와 `resolve_target_candidate(..., caps=caps)`,
  `confirm_keys(..., caps=caps)`를 부르는데 **`server/enrichment_candidates.py`는
  이 커밋의 10파일 목록에 없다.** 그 심볼들은 **`2fb8fc2`**(제목이 `fix(map2):
  nothing-scored…`인 커밋)에 들어가 있다.
- **`--max-keys`는 `classify`에만 붙었다.** 두 프로브 상한은 `confirm`에도 붙지만
  키 예산은 아니다. 그리고 `analyze_promotions`(`propose` 경로)는 여전히
  `caps=` 없이 호출된다.
- `ingestion_settings.json.sample`이 **「상한 4개」라고 적고 셋만 싣는다**
  (`probe_distinct_values`는 설계상 미선언이라 키가 안 보인다).

## 그때 남아 있던 것

- 상한 소비자와 상한 정의가 **서로 다른 커밋에 있다.**
- `CANDIDATE_PROBE_MAX_ROWS` 상수는 사라졌고, 그 자리에 `🔴 이 상수는 사라졌다.`
  주석이 남아 있다.
- 천장 초과 뷰 `limit`은 이제 **조용히 깎지 않고 클램프 경고를 남긴다.**
