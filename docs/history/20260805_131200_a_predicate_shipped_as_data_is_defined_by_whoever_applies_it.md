# 데이터로 출하한 술어는 그것을 적용하는 쪽이 뜻을 정한다 — 아무도 규칙을 안 고쳤는데 뜻이 바뀌었다

> **커밋:** `7f0a717` (2026-08-05 13:12) | **일자:** 2026-08-05 오후
> **담당:** 제품 소유자(운영 신고: 한 칸 채웠더니 행이 큐에서 빠졌다) · server + client 구현
> **대상:** **32파일 +2,029 / −332.** `server/enrichment_config.py`(148) · `enrichment_analysis.py`(166) · `enrichment_candidates.py`(124) · `server/main.py`(62) · **신규** `client2/src/enrichment_queue.js`(**+94**) · `client2/src/enrichment.js`(114) · `ui.js`(13) · `admin.js`(34) · **신규 하네스** `enrichment_queue_partition_harness.mjs`(331) · `docs/spec/ENRICHMENT_QUEUE_SPEC.md`(45) + dist
> **스위트:** 커밋 메시지 기준 **서버 2,544 passed.** ⚠️ **이 트리에서는 성립할 수 없다 — 아래 참조.**

## 배경 — 반쯤 채운 행이 큐에서 빠져나갔고, 아무도 규칙을 안 고쳤다

`queue_filters`는 **컬럼당 `{대상: 공백}`** 형태로 출하됐고 **모든 소비자가
그것을 AND로 묶었다.**

```python
    if scope == SCOPE_QUEUE:
        return and_(*[translate(col, spec)
                      for col, spec in public["queue_filters"].items()])
```

클라에도 같은 사본이 둘 있었다:

```js
      const filters = rule.queue_filters
        || Object.fromEntries((rule.target_fields || []).map(f => [f, { type: 'blank' }]));
```

대상이 둘인 규칙에서 그것은 조용히 **「모든 대상이 공백」**을 뜻한다. 그래서
**한 칸을 채우면 형제 칸이 아직 비었는데도 행이 큐에서 빠졌다.**

**살아 있는 규칙 둘 다 대상을 둘씩 선언한다** — `dt_job_job_lot_slot_attribution`이
`["dt_lot_confirmed", "dt_slot_confirmed"]`, `eqp_product_frame_attribution`이
`["core_frame", "dt_frame"]`. 그리고 쓰기 쪽은 이미 **컬럼 단위로** 썼다. 즉
이번 라운드 이전에 이미 도달 가능한 결함이었지 **새 결과가 아니다.**

## 재사용 가능한 모양

> **아무도 규칙을 편집하지 않았는데 뜻이 바뀌었다. 바뀐 것은 config가 대상을 몇 개
> 선언하는가였다.**
>
> **데이터로 출하한 술어는 그것을 적용하는 쪽이 정의한다.**

## 그래서 질문을 **이름으로** 내보낸다

`enrichment_config.queue_predicate_condition`이 **규칙 자신의 `target_fields`에
대한 OR-of-blank**를 계산하고, `GET /tables/{t}/data?enrichment_queue=<rule>`이
그것을 요청한다.

```python
    if scope == QUEUE_SCOPE_RESOLVED:
        return and_(*[cond(t, "notBlank") for t in targets],
                    *[cond(k, "notBlank") for k in keys])
    any_target_blank = or_(*[cond(t, "blank") for t in targets])
    if scope == QUEUE_SCOPE_QUEUE:
        return any_target_blank
    if scope == QUEUE_SCOPE_KEYED:
        return and_(any_target_blank, *[cond(k, "notBlank") for k in keys])
    return and_(any_target_blank, or_(*[cond(k, "blank") for k in keys]))
```

```
queue     = 대상 중 하나라도 공백
keyed     = queue AND 결정 키 전부 비공백
blank_key = queue AND 결정 키 중 하나라도 공백
resolved  = 대상 전부 비공백 AND 결정 키 전부 비공백
```

`keyed` + `blank_key`가 `queue`를 **분할**하고, `resolved`의 대상 절반이 `queue`의
**정확한 여집합**이다. **옛 철자에서는 반쯤 채운 행이 어느 쪽에도 없었고, 결함이
정확히 거기 살았다.**

소비자 전부가 이 함수 **하나**에 닿는다 — 워크리스트 행 · 진행 잔여 · 배지 ·
어드민 개수 · `classify_queue` · 스윕.

## DSL은 일부러 넓히지 않았다

컬럼을 가로지르는 OR을 DSL에 넣으면 **그 표면을 기존 호출자 전부가 물려받는다.**
**질문 하나, 구현 하나.**

## 클라는 컴포저 하나로 한 번에 갈아탔다 — 그리고 배지의 뺄셈이 사라졌다

배지가 총계 둘의 차로 계산되던 것(`fetchKeyedTotal` → `S.totalKeyed` →
`remaining - S.totalKeyed`)이 **삭제**됐다. 그것은 **DSL이 이 질문을 표현할 수
없어서 존재했던 것**이고, **숫자의 사본은 그 숫자가 틀릴 수 있는 두 번째 자리**다.

`queue_predicate`의 **부재가 구버전 서버 신호**다. 그러면 배지는 **0을 지어내지
않고 숨는다.**

```js
export function hasQueuePredicate(rule) {
  const p = rule && rule.queue_predicate;
  return !!(p && p.param && p.value);
}
```

## 같이 착지한 것 — 컬럼 단위 후보 해소와, 안 세어지던 사실 하나

다중 후보 결과가 **행 전체를 거절하는 대신 모든 후보가 동의하는 컬럼만 채운다**
(새 계급 `partially_resolvable`, 새 결과 키 `target_verdicts`).

세 사실이 **따로** 유지된다:

| 토큰 | 뜻 |
|---|---|
| `ambiguous` | **비교했고**, 후보들이 어긋났다 |
| `no_candidate` | **물었고**, 선언된 뷰들이 아무것도 안 줬다 |
| `not_declared` | **아예 안 물었다** |

그리고 **선언되지 않은 대상**은 그전까지 조용히 건너뛰어져 **그 공백이 판정된
공백과 똑같이 읽혔다.** 이제 세어진다:

```python
        for field in sorted(blanks - declared):
            _bump_target(st, field, REASON_NOT_DECLARED)
```

## ⚠️ diff가 커밋 메시지와 어긋난 자리 — 이 트리는 초록일 수 없다

이 커밋은 `server/tests/test_mapper_sample_cross_table_lookup.py`(**+478**)를
추가한다. 그 테스트는 `server/mappers/cross_table_lookup_mapper.py.sample`을
`SourceFileLoader`로 **존재 확인도 skip도 없이** 적재한다.

**그 `.sample` 파일은 다음 커밋 `4717429`에서 추가된다.** 이 커밋 시점에는
존재하지 않으므로 그 모듈의 모든 테스트가 에러가 난다. **「서버 2,544 passed」는
커밋된 그대로의 트리에서 성립할 수 없다.**

(뒤집힌 짝도 있다 — `4717429`는 「테스트가 바로 그 `.sample` 텍스트를 적재해
`execute_custom_mapper`로 돌린다」고 적지만 **그 커밋의 diff에는 테스트가 없다.**)

## 그때 남아 있던 것

- **반쯤 채운 행을 큐에 남기는 결정이 다음 결함을 도달 가능하게 만들었다** —
  25분 뒤 `a565db1`이 그것을 닫는다
  ([`20260805_133700`](./20260805_133700_retyping_a_machine_value_must_not_sign_it_as_yours.md)).
- `queue_filters` / `keyed_queue_filters`는 **여전히 페이로드에 실려 나간다.**
  새 `queue_predicate`가 그 옆에 추가된 것이지 옛 키가 빠진 것이 아니다.
