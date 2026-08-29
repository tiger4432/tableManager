# 트렌드의 0에는 «어느 하나만으로도 충분한» 원인이 셋 있었고, 동률은 이제 「모른다」로 답한다

> **커밋:** `8dcf8ed5` (20:31) · `0912c69a` (21:36) · `38e9125c` (21:58)
> | **일자:** 2026-08-27 저녁
> **레인:** 서버(트렌드 · 신원)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**

## 배경 — 씨앗의 노드 id 가 «선언이 모르는 낱말»로 철자돼 있었다

`8dcf8ed5`. `ledger_identity.identity()`가 `node_id`를 `subject_type`에서 철자했는데
그 값은 **집계의 이름 `WaferLeg`** 이고 **선언은 그것을 모른다.** 그래서 그 id 는 맵이나
후보 목록과 **같은 문자열 위에서 만날 수가 없었다.**

## 🔴 그리고 트렌드의 0에는 원인이 «셋»이었다 — 하나씩만으로도 0이 된다

`0912c69a`:

```
① observed CTE 가 «호출자가 말한 subject type»으로 매치한다
   -> 어떤 원자도 WaferLeg 가 아니다
② 축 바인딩이 subject_keys 에서 wafer 와 bonding_leg 를 찾는다
   -> die 는 mat_id · x · y · mat_type 을 든다
③ die 식이 object_payload->'die' 를 읽는다
   -> 어떤 observed 원자도 그것을 안 든다  =>  count(DISTINCT die) 는 0 «밖에» 못 낸다
```

수리는 **발견을 die 로 세고, 축을 자기 분모 관계에서 푸는 것**이었다:

```python
# server/ledger_api/ledger_trends.py
FINDING_SOURCE = {
    "subject_type": "die",
    "wafer_key": "mat_id",
    "cell_keys": ("x", "y"),
    "plan": {"relation": "bonding_map", "alias": "p",
             "base_column": "base", "x_column": "x", "y_column": "y"},
}
```

`_finding_axis_sql`이 축마다 자기 분모 관계에서 풀기 때문에 **축 «이름»을 읽는 자리가 없다.**

## 동률이면 «모른다» — 선언 순서가 이름을 정하지 않는다

`38e9125c`. `_declared_entity(keys)`가 마킹의 키 집합과 신원 키가 같은 선언 엔터티를 고르는데
**첫 매치**를 돌려주고 있었다 — 즉 **선언 파일의 순서가 이름을 정했다.**

```python
# server/ledger_api/ledger_identity.py
hits = [name for name in entity_references.declared_types()
        if set(entity_references.identity_keys(name)) == wanted]
return hits[0] if len(hits) == 1 else None
```

동률이면 `None`이고 `identity()`는 **호출자의 낱말을 그대로 둔다.**
안전 근거가 함께 적혔다 — 오늘 선언된 엔터티 여섯의 키 집합이 전부 달라서 **이 가드는
오늘은 발화하지 않는다.**

## 아키텍처 영향

- 발견을 **die 로 센다.** 축이 자기 분모 관계에서 풀리므로 **코드에 축 이름이 없다.**
- 마크의 노드 id 가 **선언된 엔터티 이름**으로 철자된다 — 집계의 이름이 아니라.
- 신원 해석에서 **동률은 답이지 실패가 아니다.** 증거 아닌 축(선언 순서)이 답을 못 정한다.

## 그때 남아 있던 것

- `tests/test_syn_complex_composite.py`가 **혼자 돌면 통과(28)하고 넓은 `-k` 아래서는 실패**한다.
  `38e9125c`가 그것을 **아직 자리 못 잡았다**고 다시 적고 어느 쪽으로도 주장하기를 거부했다.
- `38e9125c`가 `test_declared_measurement_without_selected_evidence_is_explicit_absent`의
  기대를 옮겼다 — facet 이 이제 `measured_predicate_not_declared`로 답한다. v1 낙진이고
  `state`는 안 바뀐다.
- 🔴 `8dcf8ed5`이 `d77fa131`의 폭발 반경 주장을 철회했다 —
  `tests/test_ledger_declared_kind.py`는 **결정적으로** 15 실패 / 5 통과였다.
